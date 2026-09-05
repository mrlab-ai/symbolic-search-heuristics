#!/usr/bin/env python3
"""Adversarial tests for scheduler-only V8 selective repair."""

from __future__ import annotations

import ast
import copy
import hashlib
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import audit_pdb_terminal_incidence_confirmation_sources_v6 as PublicV6Source
import audit_pdb_terminal_incidence_confirmation_sources_v8 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v6 as PublicV6
import launch_pdb_terminal_incidence_confirmation_source_audit_v8 as Launch
import pdb_terminal_incidence_confirmation_safe_io_v8 as SelectedIO


def _row(index: int, state="COMPLETED", exit_code="0:0"):
    return {
        "array_task": index, "state": state,
        "exit_code": exit_code, "partition": "fat",
    }


def _diagnostic(rows):
    reusable = [
        row["array_task"] for row in rows
        if row["state"] == "COMPLETED" and row["exit_code"] == "0:0"
    ]
    repair = [row["array_task"] for row in rows if row["array_task"] not in reusable]
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
        "v8_design_timing_disclosure": Launch._design_timing_disclosure(),
    }


class SourceAuditV8Test(unittest.TestCase):
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

    def test_manifest_closure_binds_v8_and_imported_helpers(self):
        required = {
            "experiments/audit_pdb_terminal_incidence_confirmation_sources_v8.py",
            "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v8.py",
            "experiments/pdb_terminal_incidence_confirmation_safe_io_v7.py",
            "experiments/pdb_terminal_incidence_confirmation_safe_io_v8.py",
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v8.py",
            "experiments/pdb_terminal_incidence_confirmation_source_scan_v8.slurm",
            "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v8.py",
            "experiments/test_pdb_terminal_incidence_confirmation_source_consumer_v8.py",
            "experiments/test_pdb_terminal_incidence_confirmation_safe_io_v8.py",
            "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v6.py",
            "experiments/pdb_terminal_incidence_confirmation_safe_io_v6.py",
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v6.py",
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v5.py",
            "experiments/audit_pdb_terminal_incidence_confirmation_sources_v7.py",
            "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v7.py",
            "experiments/pdb_terminal_incidence_confirmation_source_audit_v7_code.sha256",
            "experiments/artifacts/pdb-terminal-incidence-confirmation-v7/source-audit-repair-launch-intent-v7.json",
            "experiments/artifacts/pdb-terminal-incidence-confirmation-v7/source-audit-repair-launch-failure-v7.json",
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
                        self.assertIn(imported, Source.CODE_MANIFEST_FILES)
                        if "_v8" not in imported:
                            self.assertIn(imported, Launch.PRE_DIAGNOSIS_FILES)

    def test_private_runtime_does_not_mutate_public_v6(self):
        self.assertEqual(PublicV6.SCHEMA, PublicV6Source.Base.SCHEMA + "/campaign-v6")
        self.assertIn("confirmation-v6", str(PublicV6.DIAGNOSTIC))
        self.assertEqual(Launch.Runtime.DIAGNOSTIC, Launch.V7Launch.DIAGNOSTIC)
        self.assertIs(Launch.Runtime.Source, Source)
        self.assertIs(Launch.Runtime._exclusive_bytes, Launch._exclusive_bytes)
        self.assertIs(Launch.Runtime._load_intent_only, Launch._load_intent_only)
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
            self.assertIn("v8", str(path))

    def test_controller_publisher_creates_missing_campaign_parent_exclusively(self):
        with tempfile.TemporaryDirectory(prefix="v8-publish-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            target = root / "artifacts" / "campaign-v8" / "receipt.json"
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
        with tempfile.TemporaryDirectory(prefix="v8-publish-link-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="v8-publish-swap-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="v8-root-create-") as tmp:
            base = Path(tmp)
            root = base / "repo"
            data = root / "data"
            outside = base / "outside"
            data.mkdir(mode=0o700, parents=True)
            outside.mkdir(mode=0o700)
            target = data / "union-v8"
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
            escaped = escape_root / "data" / "union-v8"
            with (
                mock.patch.object(Launch, "REPO", escape_root),
                self.assertRaises(Launch.LaunchAuditError),
            ):
                Launch.Runtime._create_private_directory(
                    escaped, "escaped union root"
                )
            self.assertFalse((outside / "union-v8").exists())

    def test_private_directory_creation_rejects_leaf_swap_at_fsync(self):
        with tempfile.TemporaryDirectory(prefix="v8-root-swap-") as tmp:
            base = Path(tmp)
            root = base / "repo"
            parent = root / "data"
            outside = base / "outside"
            parent.mkdir(mode=0o700, parents=True)
            outside.mkdir(mode=0o700)
            target = parent / "tmp-v8"
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
        with mock.patch.object(Launch, "_base_prepare_manifest") as prepare:
            Launch.prepare_manifest()
        prepare.assert_called_once_with()

    def test_design_timing_discloses_exact_known_aggregate_and_v6_row(self):
        exact_summary = (
            "aggregate V5 terminal scheduler-state counts: 795 COMPLETED, "
            "15 FAILED, 10 OUT_OF_MEMORY"
        )
        timing = Launch._design_timing_disclosure()
        history_key = (
            "historical_operational_information_known_before_v8_freeze"
        )
        self.assertIn(exact_summary, timing[history_key])
        self.assertIn(
            "V6 classifier rejected scheduler array row 2 as FAILED 2:0",
            timing[history_key],
        )
        self.assertIn(
            exact_summary.replace("scheduler-state counts", "scheduler states"),
            Launch._resource_mapping()[
                "historical_operational_information_known_before_v8_freeze"
            ],
        )
        self.assertEqual(
            timing["v7_launch_failure_record_sha256"],
            Launch.V7_LAUNCH_FAILURE_SHA256,
        )
        self.assertFalse(timing["v7_original_submission_stderr_preserved"])
        self.assertTrue(
            timing["scheduler_cause_reconstructed_post_hoc_with_non_submitting_tests"]
        )
        self.assertFalse(timing["v5_scheduler_diagnosis_repeated_by_v8"])
        self.assertEqual(
            timing["v8_scheduler_profile_change_from_v7"],
            ["memory 3000G to 2950G"],
        )

    def test_resource_profile_is_fixed_uniform_and_has_exact_headroom(self):
        value = Launch._resource_mapping()
        self.assertEqual(value["memory"]["option"], "--mem=2950G")
        self.assertEqual(value["v8_total_memory_mib"], 3020800)
        self.assertEqual(value["fat_node_mem_spec_limit_mib"], 65536)
        self.assertEqual(value["fat_node_allocatable_memory_mib"], 3030277)
        self.assertEqual(value["fat_node_allocatable_memory_headroom_mib"], 9477)
        self.assertEqual(value["scheduler_profile_change_from_v7"], [
            "memory 3000G to 2950G"
        ])
        self.assertFalse(
            value["post_failure_test_only_validation"][
                "original_v7_submission_stderr_preserved"
            ]
        )
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
        v8_accepted = {
            1: [
                {"translation": {
                    "status": task["translation"]["status"],
                    "timeout_seconds": Launch.V8_TASK_TIMEOUT_SECONDS,
                }}
                for task in accepted[0]
            ],
        }
        Launch._validate_accepted_translation_records(
            v8_accepted, [1], Launch.V8_TASK_TIMEOUT_SECONDS, "fixture"
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
            "timeout_seconds": Launch.V8_TASK_TIMEOUT_SECONDS,
        }}
        with self.assertRaises(Launch.LaunchAuditError):
            Launch._validate_accepted_translation_records(
                changed_timeout, [0], Launch.V5_TASK_TIMEOUT_SECONDS, "fixture"
            )
        with self.assertRaises(Launch.LaunchAuditError):
            Launch._validate_accepted_translation_records(
                accepted, [0], Launch.V8_TASK_TIMEOUT_SECONDS, "fixture"
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
            "--cpus-per-task=1", "--mem=2950G", "--time=3-00:00:00",
            "--nice=0", "--no-requeue", "--export=NONE",
        ):
            self.assertIn(item, command)

    def test_direct_launch_redirects_to_preintent_retained_fds(self):
        events = []
        records = {"stdout": {"fixture": 1}, "stderr": {"fixture": 2}}
        payloads = {"stdout": b"123\n", "stderr": b"binary\x00\xff"}

        class Captures:
            stdout_fd = 51
            stderr_fd = 52
            initial_identities = {"stdout": {}, "stderr": {}}

            def __enter__(self):
                events.append("enter-captures")
                return self

            def __exit__(self, *_args):
                events.append("close-captures")

            def verify_initial(self):
                events.append("verify-before-sbatch")

            def finalize(self):
                events.append("fsync-read-captures")
                return records, payloads

        def open_captures(*_args, **_kwargs):
            events.append("open-captures")
            return Captures()

        def publish_intent(*_args, **_kwargs):
            events.append("publish-intent")
            return "a" * 64

        def run_sbatch(*_args, **kwargs):
            events.append("sbatch")
            self.assertEqual(kwargs["stdout"], 51)
            self.assertEqual(kwargs["stderr"], 52)
            self.assertIsNot(kwargs["stdout"], subprocess.PIPE)
            self.assertIsNot(kwargs["stderr"], subprocess.PIPE)
            return SimpleNamespace(returncode=0)

        def publish_result(*args, **kwargs):
            events.append("publish-result")
            self.assertIs(args[3], records)
            self.assertIs(args[4], payloads)
            return "b" * 64, {
                "accepted_by_launcher": True, "parsed_job_id": "123",
            }

        diagnostic = {
            "pre_diagnosis_freeze": {}, "repair_v5_shard_indices": [1],
        }
        with (
            mock.patch.object(Launch.os.path, "lexists", return_value=False),
            mock.patch.object(
                Launch, "_load_diagnostic", return_value=("d" * 64, diagnostic)
            ),
            mock.patch.object(
                Launch.Runtime, "_scoped_repository_commit",
                return_value="c" * 40,
            ),
            mock.patch.object(Launch.Runtime, "_sha256", return_value="m" * 64),
            mock.patch.object(Source, "configure"),
            mock.patch.object(Source, "validate_code_manifest"),
            mock.patch.object(Launch.Runtime, "_validate_freeze_against_manifest"),
            mock.patch.object(Launch.Runtime, "_render_slurm", return_value=b"program"),
            mock.patch.object(Launch, "_rebuilt_inventory", return_value=b"inventory"),
            mock.patch.object(
                Launch.Runtime, "_create_private_directory", return_value={}
            ),
            mock.patch.object(Launch.Runtime, "_exclusive_bytes"),
            mock.patch.object(
                Launch.SelectedIO, "open_exclusive_capture_pair",
                side_effect=open_captures,
            ),
            mock.patch.object(
                Launch, "_launch_materials",
                return_value={
                    "slurm_program_sha256": hashlib.sha256(b"program").hexdigest(),
                    "slurm_program_bytes": len(b"program"),
                },
            ),
            mock.patch.object(Launch, "_submit_command", return_value=["sbatch"]),
            mock.patch.object(
                Launch.Runtime, "_exclusive_json", side_effect=publish_intent
            ),
            mock.patch.object(Launch.Runtime, "_executable_identity"),
            mock.patch.object(Launch.subprocess, "run", side_effect=run_sbatch),
            mock.patch.object(
                Launch, "_publish_sbatch_result", side_effect=publish_result
            ),
            mock.patch.object(
                Launch, "_write_launch_receipt",
                side_effect=lambda *_args, **_kwargs: (
                    events.append("publish-receipt") or "e" * 64
                ),
            ),
        ):
            Launch.launch()
        self.assertLess(events.index("open-captures"), events.index("publish-intent"))
        self.assertLess(events.index("publish-intent"), events.index("sbatch"))
        self.assertLess(events.index("verify-before-sbatch"), events.index("sbatch"))
        self.assertLess(events.index("sbatch"), events.index("fsync-read-captures"))
        self.assertLess(events.index("publish-result"), events.index("close-captures"))
        self.assertLess(events.index("close-captures"), events.index("publish-receipt"))
        self.assertNotIn(
            "subprocess.PIPE", Path(Launch.__file__).read_text("utf-8")
        )

    def test_v8_never_rediagnoses_v5(self):
        self.assertFalse(hasattr(Launch, "_v5_scheduler_rows"))
        self.assertFalse(hasattr(Launch.Runtime, "_v5_scheduler_rows"))
        self.assertFalse(hasattr(
            Launch.Runtime, "_load_v5_launch_without_output_access"
        ))
        self.assertIs(Launch.Runtime.diagnose_v5, Launch.diagnose_v5)
        self.assertNotIn(
            "def _v5_scheduler_rows",
            Path(Launch.__file__).read_text("utf-8"),
        )
        with (
            mock.patch.object(
                Launch.Runtime, "_sacct",
                side_effect=AssertionError("V5 scheduler queried"),
            ),
            mock.patch.object(
                Launch.SelectedIO, "read_selected_flat_tree",
                side_effect=AssertionError("V5/V7 output opened"),
            ),
        ):
            digest, diagnostic = Launch._load_recorded_diagnostic()
        self.assertEqual(digest, Launch.V7_DIAGNOSTIC_SHA256)
        self.assertEqual(len(diagnostic["reusable_v5_shard_indices"]), 795)
        self.assertEqual(len(diagnostic["repair_v5_shard_indices"]), 25)
        with self.assertRaisesRegex(Launch.LaunchAuditError, "diagnosis is disabled"):
            Launch.diagnose_v5()

    def test_private_runtime_has_no_alternate_command_entry_point(self):
        self.assertIs(Launch.Runtime.prepare_manifest, Launch.prepare_manifest)
        self.assertIs(Launch.Runtime.launch, Launch.launch)
        self.assertIs(Launch.Runtime.recover_launch, Launch.recover_launch)
        self.assertIs(Launch.Runtime.status, Launch.status)
        self.assertIs(Launch.Runtime.seal, Launch.seal)
        self.assertIs(Launch.Runtime.recover_seal, Launch.recover_seal)
        self.assertIs(Launch.Runtime.main, Launch.main)

    def test_sbatch_result_preserves_raw_streams_on_rejection(self):
        published = {}

        def publish(_path, value, _label):
            published.update(value)
            return Launch._digest(value)

        payloads = {
            "stdout": b"not-a-job\xff\n",
            "stderr": b"allocation failure\x00exact\n",
        }
        initial = {
            stream: {
                "path": str(path), "canonical_path": str(path),
                "device": 2, "inode": inode, "mode": "0400",
                "uid": os.getuid(), "gid": 3, "link_count": 1,
                "bytes_at_intent": 0,
            }
            for stream, path, inode in (
                ("stdout", Launch.SBATCH_STDOUT, 101),
                ("stderr", Launch.SBATCH_STDERR, 102),
            )
        }
        intent = {
            "submit_command": ["/usr/bin/sbatch", "--mem=2950G"],
            "slurm_program_sha256": hashlib.sha256(b"program").hexdigest(),
            "sbatch_capture_initial_identities": initial,
        }
        intent_raw = Launch._canonical_json(intent)
        records = {
            stream: {
                "path": str(path), "bytes": len(payloads[stream]),
                "sha256": hashlib.sha256(payloads[stream]).hexdigest(),
                "initial_identity": initial[stream],
                "final_identity": {
                    **{
                        key: value for key, value in initial[stream].items()
                        if key != "bytes_at_intent"
                    },
                    "bytes": len(payloads[stream]),
                },
            }
            for stream, path in (
                ("stdout", Launch.SBATCH_STDOUT),
                ("stderr", Launch.SBATCH_STDERR),
            )
        }
        completed = SimpleNamespace(returncode=1)
        with (
            mock.patch.object(
                Launch.Runtime, "_exclusive_json", side_effect=publish
            ),
        ):
            digest, result = Launch._publish_sbatch_result(
                intent_raw, intent, b"program", records, payloads,
                completed=completed, error=None, recovered=False,
            )
        self.assertEqual(result, published)
        self.assertEqual(digest, Launch._digest(result))
        self.assertEqual(result["stdout"], records["stdout"])
        self.assertEqual(result["stderr"], records["stderr"])
        self.assertEqual(result["process_observation"]["returncode"], 1)
        self.assertIsNone(result["parsed_job_id"])
        self.assertFalse(result["accepted_by_launcher"])
        self.assertTrue(result["raw_streams_preserved"])

    def test_direct_result_binds_retained_files_and_rejects_path_swap(self):
        with tempfile.TemporaryDirectory(
            prefix="v8-direct-result-", dir=Launch.REPO
        ) as tmp:
            directory = Path(tmp)
            stdout_path = directory / "stdout.bin"
            stderr_path = directory / "stderr.bin"
            result_path = directory / "result.json"
            receipt_path = directory / "receipt.json"
            rendered = b"program\x00bytes"
            with (
                mock.patch.object(Launch, "SBATCH_STDOUT", stdout_path),
                mock.patch.object(Launch, "SBATCH_STDERR", stderr_path),
                mock.patch.object(Launch, "SBATCH_RESULT", result_path),
                mock.patch.object(Launch, "LAUNCH_RECEIPT", receipt_path),
            ):
                with SelectedIO.open_exclusive_capture_pair(
                    stdout_path, stderr_path, root=Launch.REPO,
                    label="direct fixture",
                ) as captures:
                    intent = {
                        "submit_command": ["/usr/bin/sbatch", "--parsable"],
                        "slurm_program_sha256": hashlib.sha256(
                            rendered
                        ).hexdigest(),
                        "sbatch_capture_initial_identities": copy.deepcopy(
                            captures.initial_identities
                        ),
                    }
                    intent_raw = Launch._canonical_json(intent)
                    os.write(captures.stdout_fd, b"314159;cluster\n")
                    os.write(captures.stderr_fd, b"warning\x00\xff\n")
                    records, payloads = captures.finalize()
                    result_sha, result = Launch._publish_sbatch_result(
                        intent_raw, intent, rendered, records, payloads,
                        completed=SimpleNamespace(returncode=0),
                        error=None, recovered=False,
                    )
                    self.assertEqual(result["parsed_job_id"], "314159")
                    self.assertTrue(result["accepted_by_launcher"])

                loaded_sha, loaded = Launch._load_sbatch_result(
                    intent_raw, intent
                )
                self.assertEqual((loaded_sha, loaded), (result_sha, result))
                Launch._write_launch_receipt(
                    intent_raw, intent, "314159", recovered=False
                )

                moved = stdout_path.with_name("moved-stdout.bin")
                stdout_path.rename(moved)
                descriptor = os.open(
                    stdout_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o400,
                )
                os.close(descriptor)
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._load_sbatch_result(intent_raw, intent)

    def test_crash_recovery_binds_partial_streams_before_receipt(self):
        with tempfile.TemporaryDirectory(
            prefix="v8-recovered-result-", dir=Launch.REPO
        ) as tmp:
            directory = Path(tmp)
            stdout_path = directory / "stdout.bin"
            stderr_path = directory / "stderr.bin"
            result_path = directory / "result.json"
            receipt_path = directory / "receipt.json"
            rendered = b"program"
            with (
                mock.patch.object(Launch, "SBATCH_STDOUT", stdout_path),
                mock.patch.object(Launch, "SBATCH_STDERR", stderr_path),
                mock.patch.object(Launch, "SBATCH_RESULT", result_path),
                mock.patch.object(Launch, "LAUNCH_RECEIPT", receipt_path),
            ):
                captures = SelectedIO.open_exclusive_capture_pair(
                    stdout_path, stderr_path, root=Launch.REPO,
                    label="recovery fixture",
                )
                identities = copy.deepcopy(captures.initial_identities)
                os.write(captures.stdout_fd, b"271828\n")
                os.write(captures.stderr_fd, b"crash-left\x00\xff")
                captures.close()
                intent = {
                    "submit_command": ["/usr/bin/sbatch", "--parsable"],
                    "slurm_program_sha256": hashlib.sha256(rendered).hexdigest(),
                    "sbatch_capture_initial_identities": identities,
                }
                intent_raw = Launch._canonical_json(intent)
                result_sha, result = Launch._ensure_recovery_sbatch_result(
                    intent_raw, intent, rendered
                )
                self.assertEqual(
                    result["process_observation"]["kind"],
                    "controller-crash-returncode-unavailable",
                )
                self.assertEqual(result["parsed_job_id"], "271828")
                self.assertFalse(result["accepted_by_launcher"])
                receipt_sha = Launch._write_launch_receipt(
                    intent_raw, intent, "271828", recovered=True
                )
                self.assertRegex(result_sha, r"^[0-9a-f]{64}$")
                self.assertRegex(receipt_sha, r"^[0-9a-f]{64}$")
                _raw, receipt = Launch.Runtime._load_json(
                    receipt_path, "recovery fixture receipt"
                )
                self.assertEqual(receipt["sbatch_result_sha256"], result_sha)
                self.assertTrue(receipt["launch_recovered_from_journal"])

    def test_sbatch_stdout_parser_is_strict(self):
        self.assertEqual(Launch._parse_sbatch_job_id(b"12345\n"), "12345")
        self.assertEqual(
            Launch._parse_sbatch_job_id(b"12345;arrhenius\n"), "12345"
        )
        for invalid in (
            b"", b"123 extra\n", b"123\n456\n", b"job 123\n", b"123;bad/name\n",
            b"\xff",
        ):
            with self.subTest(invalid=invalid):
                self.assertIsNone(Launch._parse_sbatch_job_id(invalid))

    def test_intent_capture_identity_schema_is_exact(self):
        with tempfile.TemporaryDirectory(
            prefix="v8-intent-capture-", dir=Launch.REPO
        ) as tmp:
            directory = Path(tmp)
            stdout_path = directory / "stdout.bin"
            stderr_path = directory / "stderr.bin"
            with (
                mock.patch.object(Launch, "SBATCH_STDOUT", stdout_path),
                mock.patch.object(Launch, "SBATCH_STDERR", stderr_path),
                SelectedIO.open_exclusive_capture_pair(
                    stdout_path, stderr_path, root=Launch.REPO,
                    label="intent fixture",
                ) as captures,
            ):
                identities = copy.deepcopy(captures.initial_identities)
                self.assertEqual(
                    Launch._validate_capture_initial_identities(identities),
                    identities,
                )
                mutations = []
                changed = copy.deepcopy(identities)
                changed["stdout"]["mode"] = "0600"
                mutations.append(changed)
                changed = copy.deepcopy(identities)
                changed["stdout"]["bytes_at_intent"] = 1
                mutations.append(changed)
                changed = copy.deepcopy(identities)
                changed["stdout"]["link_count"] = True
                mutations.append(changed)
                changed = copy.deepcopy(identities)
                changed["stdout"]["extra"] = 0
                mutations.append(changed)
                changed = copy.deepcopy(identities)
                changed["stdout"]["inode"] = changed["stderr"]["inode"]
                changed["stdout"]["device"] = changed["stderr"]["device"]
                mutations.append(changed)
                for changed in mutations:
                    with self.subTest(changed=changed), self.assertRaises(
                        Launch.LaunchAuditError
                    ):
                        Launch._validate_capture_initial_identities(changed)

    def test_recovery_never_resubmits(self):
        with mock.patch.object(Launch, "ARRAY_TASKS", 2):
            diagnostic = _diagnostic([_row(0), _row(1, "FAILED", "2:0")])
        intent = {"fixture": True, "code_manifest_sha256": "c" * 64}
        events = []
        with tempfile.TemporaryDirectory(prefix="v8-recover-") as tmp:
            with (
                mock.patch.object(
                    Launch, "LAUNCH_RECEIPT", Path(tmp) / "missing.json"
                ),
                mock.patch.object(
                    Launch, "_load_intent_only",
                    return_value=(b"intent\n", intent, "a" * 64, diagnostic),
                ),
                mock.patch.object(
                    Launch.Runtime, "_render_slurm", return_value=b"program"
                ),
                mock.patch.object(
                    Launch, "_ensure_recovery_sbatch_result",
                    side_effect=lambda *_args: (
                        events.append("capture-result") or ("b" * 64, {})
                    ),
                ) as capture_result,
                mock.patch.object(
                    Launch.Runtime, "_journal_job_ids",
                    side_effect=lambda *_args: (events.append("journal") or []),
                ),
                mock.patch.object(
                    Launch.subprocess, "run",
                    side_effect=AssertionError("recovery invoked sbatch"),
                ),
                self.assertRaisesRegex(
                    Launch.LaunchAuditError, "refusing resubmission"
                ),
            ):
                Launch._recover_launch()
        capture_result.assert_called_once()
        self.assertEqual(events, ["capture-result", "journal"])

    def test_selected_reader_never_lists_or_opens_unselected_leaf(self):
        with tempfile.TemporaryDirectory(prefix="v8-selected-") as tmp:
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
        with tempfile.TemporaryDirectory(prefix="v8-selected-race-") as tmp:
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
            mock.patch.object(Launch.Runtime, "_v6_output_tree") as v8_tree,
            self.assertRaisesRegex(Launch.LaunchAuditError, "not entirely successful"),
        ):
            Launch._seal_context()
        accounting.assert_not_called()
        v5_triplets.assert_not_called()
        v8_tree.assert_not_called()

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
        v8 = {"files": [record(1)]}
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
                diagnostic, v5, v8, "d" * 64, recovery=False
            )
        self.assertEqual(
            [item["origin"] for item in stage["sources"]],
            ["v5-completed", "v8-repair", "v5-completed"],
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
