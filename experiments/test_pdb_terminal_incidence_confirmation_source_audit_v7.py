#!/usr/bin/env python3
"""Adversarial tests for scheduler-only V7 selective repair."""

from __future__ import annotations

import ast
import copy
import hashlib
import os
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import audit_pdb_terminal_incidence_confirmation_sources_v6 as PublicV6Source
import audit_pdb_terminal_incidence_confirmation_sources_v7 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v6 as PublicV6
import launch_pdb_terminal_incidence_confirmation_source_audit_v7 as Launch
import pdb_terminal_incidence_confirmation_safe_io_v7 as SelectedIO


def _row(index: int, state="COMPLETED", exit_code="0:0"):
    return {
        "array_task": index, "state": state,
        "exit_code": exit_code, "partition": "fat",
    }


def _diagnostic(rows):
    reusable, repair = Launch._partition_terminal_rows(rows)
    return {
        "v5_launch_receipt": {
            "job_id": "111",
            "benchmark_revision": Source.Base.Inventory.BENCHMARK_REVISION,
        },
        "v5_launch_receipt_sha256": "a" * 64,
        "v5_source_inventory_sha256": "b" * 64,
        "v5_scheduler_rows_sha256": Launch._digest(rows),
        "reusable_v5_shard_indices": reusable,
        "repair_v5_shard_indices": repair,
        "reuse_eligibility_rule": "scheduler state COMPLETED with exit 0:0 only",
        "resource_mapping": Launch._resource_mapping(),
        "pre_diagnosis_freeze": {},
        "v7_design_timing_disclosure": Launch._design_timing_disclosure(),
    }


class SourceAuditV7Test(unittest.TestCase):
    def test_recorded_prediagnosis_freeze_is_structural_and_read_free(self):
        files = [
            {"path": "a", "bytes": 1, "sha256": hashlib.sha256(b"a").hexdigest()},
            {"path": "b", "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest()},
        ]
        freeze = {
            "schema": Launch.DIAGNOSTIC_SCHEMA + "/pre-diagnosis-freeze/v1",
            "repository_commit_id": "a" * 40,
            "working_copy_revision": "@",
            "committed_revision": "@-",
            "scoped_diff_empty": True,
            "diagnostic_excluded": True,
            "jj": {
                "path": str(Launch.V5Launch.Generic.JJ_COMMAND),
                "sha256": Launch.V5Launch.Generic.JJ_EXECUTABLE_SHA256,
            },
            "files": files,
            "files_sha256": Launch._digest(files),
        }
        with (
            mock.patch.object(Launch, "PRE_DIAGNOSIS_FILES", ("a", "b")),
            mock.patch.object(
                Launch.Runtime, "_safe_file",
                side_effect=AssertionError("recorded validation read live bytes"),
            ),
        ):
            Launch._validate_recorded_pre_diagnosis_freeze(freeze)
            for changed in (
                {**freeze, "files": list(reversed(files))},
                {**freeze, "files_sha256": "0" * 64},
                {**freeze, "repository_commit_id": "not-a-commit"},
            ):
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._validate_recorded_pre_diagnosis_freeze(changed)

    def test_source_wrapper_accepts_only_fixed_ceiling(self):
        Source.configure(115200)
        self.assertEqual(Source.V5.TASK_TIMEOUT_SECONDS, 115200)
        self.assertEqual(Launch.V5Source.TASK_TIMEOUT_SECONDS, 28800)
        self.assertEqual(Launch.V5Source.Base.TASK_TIMEOUT_SECONDS, 28800)
        for invalid in (28800, 57600, 0, True, "115200"):
            with self.assertRaises(Source.SourceAuditError):
                Source.configure(invalid)

    def test_historical_v5_lf_diagnostic_compatibility_is_exact_and_restored(self):
        _raw, launch = Launch.V5Consumer._read_json(
            Launch.V5_LAUNCH_RECEIPT,
            Launch.V5_LAUNCH_RECEIPT,
            "V5 launch receipt fixture",
        )
        manifest = Launch.V5Consumer._manifest(launch)
        original_encoder = Launch.V5Consumer._canonical_json
        line_encoder = Launch.V5Consumer._canonical_json_line

        # This is the historical defect: the unchanged no-LF consumer rejects
        # the authentic diagnostic whose producer included the line feed.
        with self.assertRaises(Launch.V5Consumer.SourceConsumerError):
            Launch.V5Consumer._validate_diagnostic(launch, manifest)
        self.assertIs(Launch.V5Consumer._canonical_json, original_encoder)

        Source.validate_with_historical_v5_diagnostic_encoding(
            Launch.V5Consumer,
            Launch.V5Consumer._validate_diagnostic,
            launch,
            manifest,
        )
        self.assertIs(Launch.V5Consumer._canonical_json, original_encoder)

        def no_line_feed(value):
            return line_encoder(value)[:-1]

        with (
            mock.patch.object(
                Launch.V5Consumer, "_canonical_json_line", no_line_feed
            ),
            self.assertRaises(Launch.V5Consumer.SourceConsumerError),
        ):
            Source.validate_with_historical_v5_diagnostic_encoding(
                Launch.V5Consumer,
                Launch.V5Consumer._validate_diagnostic,
                launch,
                manifest,
            )
        self.assertIs(Launch.V5Consumer._canonical_json, original_encoder)

        diagnostic_path = Path(
            launch["v4_infrastructure_diagnostic_path"]
        )
        _diagnostic_raw, diagnostic = Launch.V5Consumer._read_json(
            diagnostic_path, diagnostic_path, "V5 diagnostic fixture"
        )
        relative = diagnostic_path.relative_to(Launch.REPO).as_posix()
        list_digest_pairs = (
            ("v4_scheduler_rows", "v4_scheduler_rows_sha256"),
            ("v4_failure_logs", "v4_failure_logs_sha256"),
            (
                "v4_oom_scheduler_resource_rows",
                "v4_oom_scheduler_resource_rows_sha256",
            ),
            (
                "v4_timeout_scheduler_resource_rows",
                "v4_timeout_scheduler_resource_rows_sha256",
            ),
        )
        for field, digest_field in list_digest_pairs:
            no_lf_diagnostic = copy.deepcopy(diagnostic)
            no_lf_diagnostic[digest_field] = hashlib.sha256(
                original_encoder(no_lf_diagnostic[field])
            ).hexdigest()
            no_lf_raw = line_encoder(no_lf_diagnostic)
            no_lf_launch = copy.deepcopy(launch)
            no_lf_launch["v4_infrastructure_diagnostic"] = no_lf_diagnostic
            no_lf_launch["v4_infrastructure_diagnostic_sha256"] = (
                hashlib.sha256(no_lf_raw).hexdigest()
            )
            no_lf_manifest = dict(manifest)
            no_lf_manifest[relative] = hashlib.sha256(no_lf_raw).hexdigest()
            with (
                self.subTest(digest_field=digest_field),
                mock.patch.object(
                    Launch.V5Consumer, "_read_json",
                    return_value=(no_lf_raw, no_lf_diagnostic),
                ),
                self.assertRaises(Launch.V5Consumer.SourceConsumerError),
            ):
                Source.validate_with_historical_v5_diagnostic_encoding(
                    Launch.V5Consumer,
                    Launch.V5Consumer._validate_diagnostic,
                    no_lf_launch,
                    no_lf_manifest,
                )
            self.assertIs(Launch.V5Consumer._canonical_json, original_encoder)

        altered = copy.deepcopy(diagnostic)
        altered["v4_scheduler_rows"] = list(
            reversed(altered["v4_scheduler_rows"])
        )
        altered["v4_scheduler_rows_sha256"] = hashlib.sha256(
            line_encoder(altered["v4_scheduler_rows"])
        ).hexdigest()
        with (
            mock.patch.object(
                Launch.V5Consumer, "_read_json",
                return_value=(
                    line_encoder(altered), altered
                ),
            ),
            self.assertRaises(Launch.V5Consumer.SourceConsumerError),
        ):
            Source.validate_with_historical_v5_diagnostic_encoding(
                Launch.V5Consumer,
                Launch.V5Consumer._validate_diagnostic,
                launch,
                manifest,
            )
        self.assertIs(Launch.V5Consumer._canonical_json, original_encoder)

        changed_launch = dict(launch)
        changed_launch["v4_infrastructure_diagnostic_path"] = "/invalid/path"
        with self.assertRaises(Launch.V5Consumer.SourceConsumerError):
            Source.validate_with_historical_v5_diagnostic_encoding(
                Launch.V5Consumer,
                Launch.V5Consumer._validate_diagnostic,
                changed_launch,
                manifest,
            )
        self.assertIs(Launch.V5Consumer._canonical_json, original_encoder)

    def test_manifest_closure_binds_v7_and_imported_helpers(self):
        required = {
            "experiments/audit_pdb_terminal_incidence_confirmation_sources_v7.py",
            "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v7.py",
            "experiments/pdb_terminal_incidence_confirmation_safe_io_v7.py",
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v7.py",
            "experiments/pdb_terminal_incidence_confirmation_source_scan_v7.slurm",
            "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v7.py",
            "experiments/test_pdb_terminal_incidence_confirmation_source_consumer_v7.py",
            "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v6.py",
            "experiments/pdb_terminal_incidence_confirmation_safe_io_v6.py",
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v6.py",
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v5.py",
            "experiments/pdb_confirmation_safe_io.py",
            "paper/check_submission_ready.py",
            "paper/paper.tex",
            "paper/render_terminal_incidence_results.py",
            "paper/supplement.tex",
            "paper/test_render_terminal_incidence_results.py",
        }
        self.assertTrue(required <= set(Source.CODE_MANIFEST_FILES))
        self.assertEqual(len(Source.DOWNSTREAM_PRE_DIAGNOSIS_FILES), 64)
        self.assertEqual(
            tuple(sorted(set(Source.DOWNSTREAM_PRE_DIAGNOSIS_FILES))),
            Source.DOWNSTREAM_PRE_DIAGNOSIS_FILES,
        )
        self.assertTrue(
            set(Source.DOWNSTREAM_PRE_DIAGNOSIS_FILES)
            <= set(Source.CODE_MANIFEST_FILES)
        )
        self.assertTrue(
            set(Source.DOWNSTREAM_PRE_DIAGNOSIS_FILES)
            <= set(Launch.PRE_DIAGNOSIS_FILES)
        )
        self.assertIn(Launch.DIAGNOSTIC_RELATIVE_PATH, Source.CODE_MANIFEST_FILES)
        self.assertNotIn(Launch.DIAGNOSTIC_RELATIVE_PATH, Launch.PRE_DIAGNOSIS_FILES)

        def frozen_source_files(relative):
            module = ast.parse((Launch.REPO / relative).read_text("utf-8"))
            for statement in module.body:
                if not isinstance(statement, ast.Assign):
                    continue
                if any(
                    isinstance(target, ast.Name)
                    and target.id == "EXPERIMENT_SOURCE_FILES"
                    for target in statement.targets
                ):
                    return set(ast.literal_eval(statement.value))
            self.fail("missing literal EXPERIMENT_SOURCE_FILES in " + relative)

        downstream_protocol_sources = set()
        for relative in (
            "experiments/pdb_terminal_incidence_confirmation_a_protocol.py",
            "experiments/pdb_terminal_incidence_confirmation_b_protocol.py",
        ):
            downstream_protocol_sources.update(frozen_source_files(relative))
        self.assertTrue(
            downstream_protocol_sources <= set(Launch.PRE_DIAGNOSIS_FILES)
        )

        local_modules = {}
        for directory in (Launch.REPO / "experiments", Launch.REPO / "paper"):
            for path in directory.glob("*.py"):
                local_modules.setdefault(path.stem, []).append(path)
        for relative in Source.CODE_MANIFEST_FILES:
            path = Launch.REPO / relative
            if path.suffix != ".py":
                continue
            module = ast.parse(path.read_text("utf-8"))
            for statement in ast.walk(module):
                names = []
                if isinstance(statement, ast.Import):
                    names = [
                        alias.name.split(".", 1)[0]
                        for alias in statement.names
                    ]
                elif (
                    isinstance(statement, ast.ImportFrom)
                    and statement.level == 0
                    and statement.module
                ):
                    names = [statement.module.split(".", 1)[0]]
                for name in names:
                    choices = local_modules.get(name, [])
                    if len(choices) == 1:
                        imported = choices[0].relative_to(
                            Launch.REPO
                        ).as_posix()
                        self.assertIn(imported, Launch.PRE_DIAGNOSIS_FILES)

    def test_private_runtime_does_not_mutate_public_v6(self):
        self.assertEqual(PublicV6.SCHEMA, PublicV6Source.Base.SCHEMA + "/campaign-v6")
        self.assertIn("confirmation-v6", str(PublicV6.DIAGNOSTIC))
        self.assertIn("confirmation-v7", str(Launch.Runtime.DIAGNOSTIC))
        self.assertIs(Launch.Runtime.Source, Source)
        self.assertIs(Launch.Runtime._exclusive_bytes, Launch._exclusive_bytes)
        self.assertIs(
            Launch.Runtime._create_private_directory,
            Launch._create_private_directory,
        )
        self.assertIs(Source.Base.atomic_exclusive_bytes, Source.atomic_exclusive_bytes)
        self.assertIsNot(
            PublicV6Source.Base.atomic_exclusive_bytes,
            Source.atomic_exclusive_bytes,
        )
        for path in (
            Launch.Runtime.INTENT, Launch.Runtime.LAUNCH_RECEIPT,
            Launch.Runtime.EXECUTION_RECEIPT, Launch.Runtime.OUTPUT_DIR,
            Launch.Runtime.TMP_ROOT, Launch.Runtime.UNION_DIR,
            Launch.Runtime.CANDIDATE, Launch.Runtime.ATTESTATION,
        ):
            self.assertIn("v7", str(path))

    def test_controller_publisher_creates_missing_campaign_parent_exclusively(self):
        with tempfile.TemporaryDirectory(prefix="v7-publish-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            target = root / "artifacts" / "campaign-v7" / "receipt.json"
            with mock.patch.object(Launch, "REPO", root):
                digest = Launch.Runtime._exclusive_bytes(
                    target, b"sealed\n", "fixture receipt"
                )
                self.assertEqual(digest, hashlib.sha256(b"sealed\n").hexdigest())
                self.assertEqual(target.read_bytes(), b"sealed\n")
                self.assertEqual(stat.S_IMODE(target.parent.stat().st_mode), 0o700)
                with self.assertRaisesRegex(
                    Launch.LaunchAuditError, "refusing to overwrite"
                ):
                    Launch.Runtime._exclusive_bytes(
                        target, b"changed\n", "fixture receipt"
                    )

    def test_controller_publisher_rejects_symlink_parent_escape(self):
        with tempfile.TemporaryDirectory(prefix="v7-publish-link-") as tmp:
            base = Path(tmp)
            root = base / "repo"
            outside = base / "outside"
            root.mkdir(mode=0o700)
            outside.mkdir(mode=0o700)
            (root / "published").symlink_to(outside, target_is_directory=True)
            target = root / "published" / "receipt.json"
            with (
                mock.patch.object(Launch, "REPO", root),
                self.assertRaises(Launch.LaunchAuditError),
            ):
                Launch.Runtime._exclusive_bytes(
                    target, b"sealed\n", "fixture receipt"
                )
            self.assertFalse((outside / "receipt.json").exists())

    def test_controller_publisher_rejects_temp_name_swap(self):
        with tempfile.TemporaryDirectory(prefix="v7-publish-swap-") as tmp:
            root = Path(tmp) / "repo"
            parent = root / "published"
            parent.mkdir(mode=0o700, parents=True)
            target = parent / "receipt.json"
            original_link = SelectedIO.os.link

            def swapped_link(
                source, destination, *, src_dir_fd, dst_dir_fd,
                follow_symlinks,
            ):
                os.unlink(source, dir_fd=src_dir_fd)
                descriptor = os.open(
                    source, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600, dir_fd=src_dir_fd,
                )
                try:
                    os.write(descriptor, b"attacker bytes\n")
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                return original_link(
                    source, destination,
                    src_dir_fd=src_dir_fd, dst_dir_fd=dst_dir_fd,
                    follow_symlinks=follow_symlinks,
                )

            with (
                mock.patch.object(Launch, "REPO", root),
                mock.patch.object(
                    SelectedIO.os, "link", side_effect=swapped_link
                ),
                self.assertRaisesRegex(
                    Launch.LaunchAuditError, "temporary link changed"
                ),
            ):
                Launch.Runtime._exclusive_bytes(
                    target, b"sealed\n", "fixture receipt"
                )
            self.assertFalse(target.exists())

    def test_private_directory_creation_is_descriptor_relative_and_contained(self):
        with tempfile.TemporaryDirectory(prefix="v7-root-create-") as tmp:
            base = Path(tmp)
            root = base / "repo"
            data = root / "data"
            outside = base / "outside"
            data.mkdir(mode=0o700, parents=True)
            outside.mkdir(mode=0o700)
            target = data / "union-v7"
            with mock.patch.object(Launch, "REPO", root):
                identity = Launch.Runtime._create_private_directory(
                    target, "fixture union root"
                )
            self.assertEqual(identity["path"], str(target))
            self.assertEqual(identity["mode"], "0700")
            self.assertTrue(target.is_dir())

            escape_root = base / "escape-repo"
            escape_root.mkdir(mode=0o700)
            (escape_root / "data").symlink_to(
                outside, target_is_directory=True
            )
            escaped = escape_root / "data" / "union-v7"
            with (
                mock.patch.object(Launch, "REPO", escape_root),
                self.assertRaises(Launch.LaunchAuditError),
            ):
                Launch.Runtime._create_private_directory(
                    escaped, "escaped union root"
                )
            self.assertFalse((outside / "union-v7").exists())

    def test_private_directory_creation_rejects_leaf_swap_at_fsync(self):
        with tempfile.TemporaryDirectory(prefix="v7-root-swap-") as tmp:
            base = Path(tmp)
            root = base / "repo"
            parent = root / "data"
            outside = base / "outside"
            parent.mkdir(mode=0o700, parents=True)
            outside.mkdir(mode=0o700)
            target = parent / "tmp-v7"
            moved = parent / "moved-original"
            original_fsync = SelectedIO.os.fsync
            swapped = False

            def swap_at_first_fsync(descriptor):
                nonlocal swapped
                result = original_fsync(descriptor)
                if not swapped:
                    swapped = True
                    target.rename(moved)
                    target.symlink_to(outside, target_is_directory=True)
                return result

            with (
                mock.patch.object(Launch, "REPO", root),
                mock.patch.object(
                    SelectedIO.os, "fsync", side_effect=swap_at_first_fsync
                ),
                self.assertRaisesRegex(
                    Launch.LaunchAuditError, "changed after creation"
                ),
            ):
                Launch.Runtime._create_private_directory(
                    target, "fixture TMPDIR root"
                )
            self.assertTrue(target.is_symlink())
            self.assertTrue(moved.is_dir())
            self.assertEqual(list(outside.iterdir()), [])

    def test_prepare_manifest_delegates_exactly_once(self):
        with mock.patch.object(Launch.Runtime, "prepare_manifest") as prepare:
            Launch.prepare_manifest()
        prepare.assert_called_once_with()

    def test_partition_is_exact_scheduler_complement_for_any_terminal_exit(self):
        rows = [
            _row(0), _row(1, "FAILED", "2:0"),
            _row(2, "OUT_OF_MEMORY", "0:125"),
            _row(3, "CANCELLED", "17:9"),
        ]
        with mock.patch.object(Launch, "ARRAY_TASKS", 4):
            reusable, repair = Launch._partition_terminal_rows(rows)
        self.assertEqual(reusable, [0])
        self.assertEqual(repair, [1, 2, 3])

    def test_design_timing_discloses_exact_known_aggregate_and_v6_row(self):
        exact_summary = (
            "aggregate V5 terminal scheduler-state counts: 795 COMPLETED, "
            "15 FAILED, 10 OUT_OF_MEMORY"
        )
        timing = Launch._design_timing_disclosure()
        history_key = (
            "historical_operational_information_known_before_v7_freeze"
        )
        self.assertIn(exact_summary, timing[history_key])
        self.assertIn(
            "V6 classifier rejected scheduler array row 2 as FAILED 2:0",
            timing[history_key],
        )
        self.assertIn(
            exact_summary.replace("scheduler-state counts", "scheduler states"),
            Launch._resource_mapping()[
                "historical_operational_information_known_before_v7_freeze"
            ],
        )
        failed = timing["failed_v7_prediagnosis_attempt"]
        self.assertEqual(
            failed["revision"],
            "9c06f962627739d40d00cb2ef19525a80b2ca97f",
        )
        self.assertIn(
            "38 V5 code-manifest dependency checks",
            failed["completed_before_failure"],
        )
        self.assertEqual(failed["sacct_queries"], 0)
        self.assertEqual(failed["v5_scheduler_rows_read"], 0)
        self.assertFalse(failed["v5_output_namespace_accessed"])
        self.assertFalse(
            failed["v5_shards_environment_logs_or_support_read"]
        )
        self.assertFalse(
            failed["v7_diagnostic_manifest_intent_receipt_job_or_output_created"]
        )
        self.assertTrue(
            timing[
                "amended_v7_frozen_before_first_scheduler_reaching_diagnosis"
            ]
        )

    def test_active_unknown_malformed_missing_and_step_rows_abort(self):
        with mock.patch.object(Launch, "ARRAY_TASKS", 1):
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._partition_terminal_rows([_row(0, "RUNNING", "0:0")])
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._partition_terminal_rows([_row(0, "MYSTERY", "0:0")])
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._partition_terminal_rows([_row(0, "FAILED", "bad")])
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._partition_terminal_rows([])
            output = "123_0.batch|FAILED|2:0|fat\n"
            with mock.patch.object(Launch.Runtime, "_sacct", return_value=output):
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._v5_scheduler_rows("123")

    def test_scheduler_diagnostic_query_has_only_minimum_fields(self):
        output = "123_0|COMPLETED|0:0|fat\n123_1|FAILED|2:0|fat\n"
        with (
            mock.patch.object(Launch, "ARRAY_TASKS", 2),
            mock.patch.object(Launch.Runtime, "_sacct", return_value=output) as query,
        ):
            rows = Launch._v5_scheduler_rows("123")
        self.assertEqual(rows, [_row(0), _row(1, "FAILED", "2:0")])
        command = query.call_args.args[0]
        self.assertIn("--format=JobID,State,ExitCode,Partition", command)
        self.assertFalse(any("Elapsed" in item or "RSS" in item for item in command))

    def test_full_diagnose_issues_only_one_four_field_scheduler_query(self):
        output = "123_0|COMPLETED|0:0|fat\n123_1|FAILED|2:0|fat\n"
        launch = {
            "job_id": "123", "code_manifest_sha256": "c" * 64,
            "source_inventory_sha256": "d" * 64,
        }
        with (
            mock.patch.object(Launch, "ARRAY_TASKS", 2),
            mock.patch.object(Source, "CANDIDATE_COUNT", 4),
            mock.patch.object(Launch.Runtime, "_pre_diagnosis_freeze", return_value={}),
            mock.patch.object(Launch.os.path, "lexists", return_value=False),
            mock.patch.object(
                Launch, "_load_v5_launch_without_output_access",
                return_value=("a" * 64, launch),
            ),
            mock.patch.object(
                Launch.Runtime, "_safe_file",
                return_value=SimpleNamespace(raw=b"intent\n"),
            ),
            mock.patch.object(Launch.Runtime, "_sacct", return_value=output) as sacct,
            mock.patch.object(Launch.Runtime, "_exclusive_json", return_value="e" * 64),
            mock.patch.object(Launch.V5Launch, "_journal_job_ids") as journal,
            mock.patch.object(Launch.SelectedIO, "read_selected_flat_tree") as tree,
        ):
            Launch.diagnose_v5()
        sacct.assert_called_once()
        command = sacct.call_args.args[0]
        self.assertIn("--format=JobID,State,ExitCode,Partition", command)
        self.assertFalse(any(
            field in item
            for item in command
            for field in ("Elapsed", "MaxRSS", "NodeList", "SubmitLine")
        ))
        journal.assert_not_called()
        tree.assert_not_called()

    def test_invalid_v5_diagnostic_cannot_reach_scheduler_or_output(self):
        intent = {"submission_token": "a" * 24}
        launch = {
            "job_id": "123", "launcher_sha256": "l" * 64,
            "python_requirements_sha256": "r" * 64,
        }
        manifest = {
            "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py": "l" * 64,
            "experiments/requirements-pdb-terminal-incidence-shadow.txt": "r" * 64,
        }
        files = iter(((b"intent\n", intent), (b"launch\n", launch)))
        original_encoder = Launch.V5Consumer._canonical_json
        with (
            mock.patch.object(
                Launch.Runtime, "_pre_diagnosis_freeze", return_value={}
            ),
            mock.patch.object(Launch.os.path, "lexists", return_value=False),
            mock.patch.object(
                Launch.V5Consumer, "_read_json",
                side_effect=lambda *_: next(files),
            ),
            mock.patch.object(Launch.V5Consumer, "_validate_launch"),
            mock.patch.object(
                Launch.V5Consumer, "_manifest", return_value=manifest
            ),
            mock.patch.object(
                Launch.V5Consumer, "_validate_diagnostic",
                side_effect=Launch.V5Consumer.SourceConsumerError("bad digest"),
            ),
            mock.patch.object(Launch.V5Consumer, "_slurm") as slurm,
            mock.patch.object(Launch.Runtime, "_sacct") as sacct,
            mock.patch.object(Launch.Runtime, "_exclusive_json") as publish,
            mock.patch.object(
                Launch.SelectedIO, "read_selected_flat_tree"
            ) as selected,
            mock.patch.object(
                Launch.V5Source, "load_inventory_manifest"
            ) as inventory,
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "V5 launch provenance is invalid"
            ),
        ):
            Launch.diagnose_v5()
        self.assertIs(Launch.V5Consumer._canonical_json, original_encoder)
        slurm.assert_not_called()
        sacct.assert_not_called()
        publish.assert_not_called()
        selected.assert_not_called()
        inventory.assert_not_called()

    def test_valid_v5_compatibility_path_reaches_one_intended_query(self):
        output = "123_0|COMPLETED|0:0|fat\n123_1|FAILED|2:0|fat\n"
        intent = {"submission_token": "a" * 24}
        launch = {
            "job_id": "123", "launcher_sha256": "l" * 64,
            "python_requirements_sha256": "r" * 64,
            "code_manifest_sha256": "c" * 64,
            "source_inventory_sha256": "d" * 64,
        }
        manifest = {
            "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py": "l" * 64,
            "experiments/requirements-pdb-terminal-incidence-shadow.txt": "r" * 64,
        }
        files = iter(((b"intent\n", intent), (b"launch\n", launch)))
        original_encoder = Launch.V5Consumer._canonical_json
        observed_encoders = []

        def validate_diagnostic(*_args):
            observed_encoders.append(Launch.V5Consumer._canonical_json)

        with (
            mock.patch.object(Launch, "ARRAY_TASKS", 2),
            mock.patch.object(Source, "CANDIDATE_COUNT", 4),
            mock.patch.object(
                Launch.Runtime, "_pre_diagnosis_freeze", return_value={}
            ),
            mock.patch.object(Launch.os.path, "lexists", return_value=False),
            mock.patch.object(
                Launch.V5Consumer, "_read_json",
                side_effect=lambda *_: next(files),
            ),
            mock.patch.object(Launch.V5Consumer, "_validate_launch"),
            mock.patch.object(
                Launch.V5Consumer, "_manifest", return_value=manifest
            ),
            mock.patch.object(
                Launch.V5Consumer, "_validate_diagnostic",
                side_effect=validate_diagnostic,
            ) as diagnostic_validator,
            mock.patch.object(Launch.V5Consumer, "_slurm"),
            mock.patch.object(
                Launch.Runtime, "_safe_file",
                return_value=SimpleNamespace(raw=b"intent\n"),
            ),
            mock.patch.object(
                Launch.Runtime, "_sacct", return_value=output
            ) as sacct,
            mock.patch.object(
                Launch.Runtime, "_exclusive_json", return_value="e" * 64
            ),
        ):
            Launch.diagnose_v5()
        diagnostic_validator.assert_called_once_with(launch, manifest)
        self.assertEqual(
            observed_encoders, [Launch.V5Consumer._canonical_json_line]
        )
        self.assertIs(Launch.V5Consumer._canonical_json, original_encoder)
        sacct.assert_called_once()
        command = sacct.call_args.args[0]
        self.assertIn("--format=JobID,State,ExitCode,Partition", command)
        self.assertFalse(any(
            field in item
            for item in command
            for field in ("Elapsed", "MaxRSS", "NodeList", "SubmitLine")
        ))

    def test_raw_scheduler_rejects_duplicate_out_of_order_and_compressed_rows(self):
        invalid_outputs = (
            "123_0|COMPLETED|0:0|fat\n123_0|FAILED|2:0|fat\n",
            "123_1|FAILED|2:0|fat\n123_0|COMPLETED|0:0|fat\n",
            "123_[0-1]|COMPLETED|0:0|fat\n123_1|FAILED|2:0|fat\n",
        )
        for output in invalid_outputs:
            with (
                self.subTest(output=output),
                mock.patch.object(Launch, "ARRAY_TASKS", 2),
                mock.patch.object(Launch.Runtime, "_sacct", return_value=output),
                self.assertRaises(Launch.LaunchAuditError),
            ):
                Launch._v5_scheduler_rows("123")

    def test_freeze_failure_precedes_v5_scheduler_and_output_access(self):
        with (
            mock.patch.object(
                Launch.Runtime, "_pre_diagnosis_freeze",
                side_effect=Launch.LaunchAuditError("dirty"),
            ),
            mock.patch.object(Launch, "_load_v5_launch_without_output_access") as load,
            mock.patch.object(Launch, "_v5_scheduler_rows") as scheduler,
            mock.patch.object(Launch.SelectedIO, "read_selected_flat_tree") as tree,
            self.assertRaisesRegex(Launch.LaunchAuditError, "dirty"),
        ):
            Launch.diagnose_v5()
        load.assert_not_called()
        scheduler.assert_not_called()
        tree.assert_not_called()

    def test_diagnosis_records_no_elapsed_log_task_or_output_manifest(self):
        rows = [_row(0), _row(1, "FAILED", "2:0")]
        captured = {}
        launch_receipt = {
            "job_id": "123", "code_manifest_sha256": "c" * 64,
            "source_inventory_sha256": "d" * 64,
        }

        def publish(_path, value, _label):
            captured.update(value)
            return "e" * 64

        with (
            mock.patch.object(Launch, "ARRAY_TASKS", 2),
            mock.patch.object(Source, "SHARD_COUNT", 2),
            mock.patch.object(Source, "CANDIDATE_COUNT", 4),
            mock.patch.object(Launch.Runtime, "_pre_diagnosis_freeze", return_value={}),
            mock.patch.object(Launch.os.path, "lexists", return_value=False),
            mock.patch.object(
                Launch, "_load_v5_launch_without_output_access",
                return_value=("a" * 64, launch_receipt),
            ),
            mock.patch.object(Launch, "_v5_scheduler_rows", return_value=rows),
            mock.patch.object(
                Launch.Runtime, "_safe_file",
                return_value=SimpleNamespace(raw=b"intent\n"),
            ),
            mock.patch.object(Launch.Runtime, "_exclusive_json", side_effect=publish),
            mock.patch.object(Launch.SelectedIO, "read_selected_flat_tree") as selected,
            mock.patch.object(Launch.Runtime, "_safe_tree") as complete,
        ):
            Launch.diagnose_v5()
        selected.assert_not_called()
        complete.assert_not_called()
        self.assertEqual(captured["repair_v5_shard_indices"], [1])
        self.assertEqual(captured["scheduler_snapshot_fields"], [
            "JobID", "State", "ExitCode", "Partition",
        ])
        self.assertTrue(all(
            set(row) == {"array_task", "state", "exit_code", "partition"}
            for row in captured["v5_scheduler_rows"]
        ))
        for key in (
            "failure_records", "failure_classes", "v5_output_manifest",
            "elapsed", "max_rss", "node_list", "task_name",
        ):
            self.assertNotIn(key, captured)
        self.assertFalse(captured["v5_output_namespace_enumerated_by_v7"])
        self.assertFalse(
            captured[
                "v5_output_triplet_bytes_read_before_v7_all_success_gate"
            ]
        )
        self.assertEqual(
            captured["v5_reusable_triplet_read_policy"],
            "only-during-seal-after-v7-all-success-gate",
        )
        self.assertFalse(
            captured[
                "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion"
            ]
        )
        self.assertEqual(
            captured["v5_reusable_selected_tree_commitment_policy"],
            "first-separate-record-at-v7-seal",
        )
        self.assertNotIn(
            "v5_reusable_triplet_bytes_read_during_seal_after_v7_all_success_gate",
            captured,
        )
        self.assertNotIn(
            "v5_reusable_selected_tree_first_separately_recorded_at_v7_seal",
            captured,
        )

        v5_launch_raw = b"launch\n"
        captured["v5_launch_receipt_sha256"] = hashlib.sha256(
            v5_launch_raw
        ).hexdigest()
        diagnostic_raw = Launch._canonical_json(captured)
        loaded = iter((
            (diagnostic_raw, captured),
            (v5_launch_raw, launch_receipt),
        ))
        with (
            mock.patch.object(Launch, "ARRAY_TASKS", 2),
            mock.patch.object(Source, "CANDIDATE_COUNT", 4),
            mock.patch.object(
                Launch.Runtime, "_load_json", side_effect=lambda *_: next(loaded)
            ),
            mock.patch.object(
                Launch, "_validate_recorded_pre_diagnosis_freeze"
            ),
            mock.patch.object(Launch.Runtime, "_validate_pre_diagnosis_freeze"),
            mock.patch.object(
                Launch.Runtime, "_sha256",
                side_effect=lambda path: (
                    captured["v5_launch_intent_sha256"]
                    if path == Launch.V5_INTENT
                    else captured["v5_code_manifest_sha256"]
                ),
            ),
        ):
            loaded_sha, loaded_value = Launch._load_diagnostic()
        self.assertEqual(loaded_sha, hashlib.sha256(diagnostic_raw).hexdigest())
        self.assertEqual(loaded_value, captured)

    def test_resource_profile_is_fixed_uniform_and_has_exact_headroom(self):
        value = Launch._resource_mapping()
        self.assertEqual(value["memory"]["option"], "--mem=3000G")
        self.assertEqual(value["v7_total_memory_mib"], 3072000)
        self.assertEqual(value["fat_node_memory_headroom_mib"], 23813)
        self.assertEqual(value["maximum_candidate_seconds_per_shard"], 230400)
        self.assertEqual(value["job_limit_seconds"], 259200)
        self.assertEqual(value["wrapper_headroom_seconds"], 28800)
        self.assertEqual(value["per_task_difficulty_fields_consulted_for_resource_selection"], [])
        self.assertEqual(value["source_support_fields_consulted_for_resource_selection"], [])

    def test_resource_ceiling_does_not_create_an_accepted_outcome_class(self):
        accepted = {
            0: [
                {"translation": {
                    "status": "success",
                    "timeout_seconds": Launch.V5_TASK_TIMEOUT_SECONDS,
                }},
                {"translation": {
                    "status": "input-rejected",
                    "timeout_seconds": Launch.V5_TASK_TIMEOUT_SECONDS,
                }},
            ],
        }
        Launch._validate_accepted_translation_records(
            accepted, [0], Launch.V5_TASK_TIMEOUT_SECONDS, "fixture"
        )
        v7_accepted = {
            1: [
                {"translation": {
                    "status": task["translation"]["status"],
                    "timeout_seconds": Launch.V7_TASK_TIMEOUT_SECONDS,
                }}
                for task in accepted[0]
            ],
        }
        Launch._validate_accepted_translation_records(
            v7_accepted, [1], Launch.V7_TASK_TIMEOUT_SECONDS, "fixture"
        )
        for invalid_status in ("timeout", "application-failure", "failed"):
            changed = {0: [*accepted[0]]}
            changed[0][0] = {"translation": {
                "status": invalid_status,
                "timeout_seconds": Launch.V5_TASK_TIMEOUT_SECONDS,
            }}
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._validate_accepted_translation_records(
                    changed, [0], Launch.V5_TASK_TIMEOUT_SECONDS, "fixture"
                )
        changed_timeout = {0: [dict(task) for task in accepted[0]]}
        changed_timeout[0][0] = {"translation": {
            "status": "success",
            "timeout_seconds": Launch.V7_TASK_TIMEOUT_SECONDS,
        }}
        with self.assertRaises(Launch.LaunchAuditError):
            Launch._validate_accepted_translation_records(
                changed_timeout, [0], Launch.V5_TASK_TIMEOUT_SECONDS, "fixture"
            )
        with self.assertRaises(Launch.LaunchAuditError):
            Launch._validate_accepted_translation_records(
                accepted, [0], Launch.V7_TASK_TIMEOUT_SECONDS, "fixture"
            )
        self.assertEqual(
            list(Launch.ACCEPTED_TRANSLATION_STATUSES),
            ["input-rejected", "success"],
        )

    def test_attestation_rejects_nonsemantic_timeout_status(self):
        with mock.patch.object(Source, "CANDIDATE_COUNT", 2):
            Launch._validate_attestation_translation_statuses({
                "translation_status_counts": {
                    "input-rejected": 1, "success": 1,
                },
            })
            for counts in (
                {"success": 1, "timeout": 1},
                {"success": 1},
                {"success": 1, "input-rejected": -1},
            ):
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._validate_attestation_translation_statuses({
                        "translation_status_counts": counts,
                    })

    def test_success_log_is_bound_to_manifest_inventory_and_output(self):
        inventory = [
            {"directory": "d1", "problem": "p1"},
            {"directory": "d2", "problem": "p2"},
        ]
        expected = (
            "a: OK\n"
            "b: OK\n"
            "[1/2] d1:p1\n"
            "[2/2] d2:p2\n"
            "wrote {}\n".format(
                Launch.V5Source.shard_path(Launch.V5_OUTPUT_DIR, 0)
            )
        ).encode("ascii")
        self.assertEqual(
            Launch._expected_success_log(
                inventory, 0, Launch.V5_OUTPUT_DIR, ("a", "b")
            ),
            expected,
        )
        self.assertNotEqual(
            Launch._expected_success_log(
                inventory, 0, Launch.V5_OUTPUT_DIR, ("b", "a")
            ),
            expected,
        )

    def test_submit_command_is_unthrottled_sparse_fixed_maximum(self):
        rows = [_row(0), _row(1, "FAILED", "2:0"), _row(2)]
        with mock.patch.object(Launch, "ARRAY_TASKS", 3), mock.patch.object(
            Launch.Runtime, "ARRAY_TASKS", 3
        ):
            command = Launch.Runtime._submit_command(
                _diagnostic(rows), "a" * 24
            )
        self.assertIn("--array=1", command)
        self.assertFalse(any("%" in item for item in command if item.startswith("--array")))
        for item in (
            "--partition=fat", "--qos=normal", "--nodes=1", "--ntasks=1",
            "--cpus-per-task=1", "--mem=3000G", "--time=3-00:00:00",
            "--nice=0", "--no-requeue", "--export=NONE",
        ):
            self.assertIn(item, command)

    def test_selected_reader_never_lists_or_opens_unselected_leaf(self):
        with tempfile.TemporaryDirectory(prefix="v7-selected-") as tmp:
            root = Path(tmp) / "root"
            root.mkdir(mode=0o700)
            (root / "selected").write_bytes(b"selected\n")
            (root / "forbidden").write_bytes(b"do not read\n")
            original_open = SelectedIO.os.open
            opened = []

            def guarded_open(path, *args, **kwargs):
                opened.append(os.fspath(path))
                if os.fspath(path) == "forbidden":
                    raise AssertionError("unselected leaf opened")
                return original_open(path, *args, **kwargs)

            with (
                mock.patch.object(SelectedIO.os, "listdir", side_effect=AssertionError),
                mock.patch.object(SelectedIO.os, "open", side_effect=guarded_open),
            ):
                tree = SelectedIO.read_selected_flat_tree(
                    root, ("selected",), label="fixture", expected_path=root
                )
            self.assertEqual([item.path for item in tree.files], ["selected"])
            self.assertNotIn("forbidden", opened)

    def test_selected_reader_rejects_mutation_between_hash_and_parse(self):
        with tempfile.TemporaryDirectory(prefix="v7-selected-race-") as tmp:
            root = Path(tmp) / "root"
            root.mkdir(mode=0o700)
            selected = root / "selected"
            selected.write_bytes(b"before\n")

            def mutate(read_selected):
                self.assertEqual(read_selected("selected"), b"before\n")
                selected.write_bytes(b"after\n")

            with self.assertRaises(SelectedIO.SelectedTreeError):
                SelectedIO.read_selected_flat_tree(
                    root, ("selected",), label="fixture",
                    expected_path=root, read_callback=mutate,
                )

    def test_launch_rebuilds_inventory_without_v5_output_access(self):
        diagnostic = {"v5_source_inventory_sha256": hashlib.sha256(b"inv\n").hexdigest()}
        with (
            mock.patch.object(Launch.Inventory, "load_inventory", return_value="inventory"),
            mock.patch.object(Source, "build_inventory_manifest", return_value={"x": 1}),
            mock.patch.object(Source, "canonical_json", return_value=b"inv\n"),
            mock.patch.object(Launch.Runtime, "_safe_file") as read,
            mock.patch.object(Launch.SelectedIO, "read_selected_flat_tree") as tree,
        ):
            self.assertEqual(Launch._rebuilt_inventory(diagnostic), b"inv\n")
        read.assert_not_called()
        tree.assert_not_called()

    def test_v5_launch_authentication_never_uses_v5_output_loader(self):
        intent = {"submission_token": "a" * 24}
        launch_receipt = {
            "job_id": "123", "launcher_sha256": "l" * 64,
            "python_requirements_sha256": "r" * 64,
        }
        manifest = {
            "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py": "l" * 64,
            "experiments/requirements-pdb-terminal-incidence-shadow.txt": "r" * 64,
        }
        files = iter(((b"intent\n", intent), (b"launch\n", launch_receipt)))
        with (
            mock.patch.object(Launch.V5Consumer, "_read_json", side_effect=lambda *_: next(files)),
            mock.patch.object(Launch.V5Consumer, "_validate_launch"),
            mock.patch.object(Launch.V5Consumer, "_manifest", return_value=manifest),
            mock.patch.object(Launch.V5Consumer, "_validate_diagnostic"),
            mock.patch.object(Launch.V5Consumer, "_slurm"),
            mock.patch.object(Launch.V5Launch, "_journal_job_ids") as journal,
            mock.patch.object(Launch.V5Launch, "_load_launch") as forbidden_load,
            mock.patch.object(Launch.V5Source, "load_inventory_manifest") as inventory,
            mock.patch.object(Launch.SelectedIO, "read_selected_flat_tree") as selected,
        ):
            digest, value = Launch._load_v5_launch_without_output_access()
        self.assertEqual(value, launch_receipt)
        self.assertEqual(digest, hashlib.sha256(b"launch\n").hexdigest())
        forbidden_load.assert_not_called()
        journal.assert_not_called()
        inventory.assert_not_called()
        selected.assert_not_called()

    def test_seal_aborts_before_any_output_read_if_one_repair_failed(self):
        diagnostic = {"repair_v5_shard_indices": [1]}
        with (
            mock.patch.object(
                Launch, "status",
                return_value=("a" * 64, {}, diagnostic,
                              [_row(1, "FAILED", "2:0")]),
            ),
            mock.patch.object(Launch, "_scheduler_contract_rows") as accounting,
            mock.patch.object(
                Launch, "_read_v5_reusable_triplets"
            ) as v5_triplets,
            mock.patch.object(Launch.Runtime, "_v6_output_tree") as v7_tree,
            self.assertRaisesRegex(Launch.LaunchAuditError, "not entirely successful"),
        ):
            Launch._seal_context()
        accounting.assert_not_called()
        v5_triplets.assert_not_called()
        v7_tree.assert_not_called()

    def test_resource_accounting_is_unreachable_before_success_gate(self):
        diagnostic = {"repair_v5_shard_indices": [1]}
        launch_receipt = {"job_id": "222", "submission_token": "a" * 24}
        for rows in (
            [_row(1, "FAILED", "2:0")],
            [_row(1, "COMPLETED", "1:0")],
            [],
        ):
            with (
                self.subTest(rows=rows),
                mock.patch.object(Launch.Runtime, "_sacct") as accounting,
                self.assertRaisesRegex(
                    Launch.LaunchAuditError, "success gate"
                ),
            ):
                Launch._scheduler_contract_rows(
                    launch_receipt, diagnostic, rows
                )
            accounting.assert_not_called()

    def test_malformed_reusable_triplet_aborts_without_changing_partition(self):
        diagnostic = {
            "reusable_v5_shard_indices": [0],
            "repair_v5_shard_indices": [1],
            "v5_launch_receipt": {
                "job_id": "1", "code_manifest_sha256": "a" * 64,
                "source_inventory_sha256": "b" * 64,
                "launch_root_identities": {"output_dir": {}, "tmpdir_root": {}},
            },
        }
        original = list(diagnostic["repair_v5_shard_indices"])

        def malformed_tree(_diagnostic, *, read_callback):
            read_callback(lambda _name: b"not-json\n")
            raise AssertionError("malformed callback should have aborted")

        with (
            mock.patch.object(Launch.V5Source, "validate_code_manifest", return_value={}),
            mock.patch.object(
                Launch.V5Source, "load_inventory_manifest",
                return_value=("b" * 64, [{}, {}]),
            ),
            mock.patch.object(Launch, "_v5_reusable_tree", side_effect=malformed_tree),
            self.assertRaisesRegex(Launch.LaunchAuditError, "JSON is malformed"),
        ):
            Launch._read_v5_reusable_triplets(diagnostic)
        self.assertEqual(diagnostic["repair_v5_shard_indices"], original)

    def test_reusable_triplet_rejects_inconsistent_success_log(self):
        diagnostic = {
            "reusable_v5_shard_indices": [0],
            "repair_v5_shard_indices": [1],
            "v5_launch_receipt": {
                "job_id": "1", "code_manifest_sha256": "a" * 64,
                "source_inventory_sha256": "b" * 64,
            },
        }
        manifest_raw = b"".join(
            b"0" * 64 + b"  " + path.encode("ascii") + b"\n"
            for path in Launch.V5Source.CODE_MANIFEST_FILES
        )
        inventory = [
            {"directory": "d1", "problem": "p1"},
            {"directory": "d2", "problem": "p2"},
        ]

        def inconsistent_tree(_diagnostic, *, read_callback):
            names = {
                Launch.V5Source.shard_path(
                    Launch.V5_OUTPUT_DIR, 0
                ).name: b"{}\n",
                Launch.V5Source.task_environment_path(
                    Launch.V5_OUTPUT_DIR, 0
                ).name: b"{}\n",
                "slurm-1_0.out": b"not the deterministic success log\n",
            }
            read_callback(names.__getitem__)
            raise AssertionError("inconsistent log should have aborted")

        with (
            mock.patch.object(
                Launch.V5Source, "validate_code_manifest", return_value={}
            ),
            mock.patch.object(
                Launch.V5Source, "_safe_file",
                return_value=SimpleNamespace(raw=manifest_raw),
            ),
            mock.patch.object(
                Launch.V5Source, "load_inventory_manifest",
                return_value=("b" * 64, inventory),
            ),
            mock.patch.object(
                Launch, "_v5_reusable_tree", side_effect=inconsistent_tree
            ),
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "success log is inconsistent"
            ),
        ):
            Launch._read_v5_reusable_triplets(diagnostic)

    def test_union_has_exact_two_origins_and_index_conservation(self):
        rows = [_row(0), _row(1, "FAILED", "2:0"), _row(2)]
        with mock.patch.object(Launch, "ARRAY_TASKS", 3):
            diagnostic = _diagnostic(rows)
        def record(index):
            name = "shard-{:04d}-of-0820.json".format(index)
            return {"path": name, "bytes": 1, "sha256": str(index) * 64}
        v5 = {"files": [record(0), record(2)]}
        v7 = {"files": [record(1)]}
        root_stage = {"root_identity": {}}
        with (
            mock.patch.object(Launch, "ARRAY_TASKS", 3),
            mock.patch.object(Launch.Runtime, "ARRAY_TASKS", 3),
            mock.patch.object(Launch.Runtime, "_ensure_union_root",
                              return_value=("a" * 64, root_stage)),
            mock.patch.object(Launch.Runtime, "_union_tree",
                              side_effect=[{"files": []}, {"files": [], "sha256": "b" * 64}]),
            mock.patch.object(Launch.Runtime, "_copy_or_validate_union_shard",
                              side_effect=lambda _s, _t, frozen: frozen["sha256"]),
            mock.patch.object(Launch.Runtime, "_publish_or_validate_json",
                              return_value="c" * 64),
        ):
            _sha, stage = Launch._prepare_union(
                diagnostic, v5, v7, "d" * 64, recovery=False
            )
        self.assertEqual(
            [item["origin"] for item in stage["sources"]],
            ["v5-completed", "v7-repair", "v5-completed"],
        )
        self.assertNotIn("v6-repair", str(stage))

    def test_template_has_only_two_identity_tokens_and_no_throttle(self):
        raw = Launch._slurm_template()
        self.assertEqual(raw.count(Launch.TIMEOUT_PLACEHOLDER), 1)
        self.assertEqual(raw.count(Launch.MANIFEST_PLACEHOLDER), 1)
        self.assertNotIn(b"#SBATCH", raw)
        rendered = Launch.Runtime._render_slurm("a" * 64, 115200)
        self.assertNotIn(Launch.TIMEOUT_PLACEHOLDER, rendered)
        self.assertNotIn(Launch.MANIFEST_PLACEHOLDER, rendered)


if __name__ == "__main__":
    unittest.main()
