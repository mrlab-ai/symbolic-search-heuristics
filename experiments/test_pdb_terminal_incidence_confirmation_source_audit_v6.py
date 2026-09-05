#!/usr/bin/env python3
"""Adversarial tests for prospective source-audit V6 selective repair."""

from __future__ import annotations

import hashlib
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


import audit_pdb_terminal_incidence_confirmation_sources_v6 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v6 as Launch
import pdb_terminal_incidence_confirmation_safe_io_v6 as SafeTreeIO


def _row(index: int, state: str = "COMPLETED", exit_code: str = "0:0") -> dict:
    return {
        "array_task": index,
        "state": state,
        "exit_code": exit_code,
        "elapsed": "00:01:00",
        "partition": "fat",
    }


class SourceAuditV6Test(unittest.TestCase):
    def test_private_v6_producer_accepts_only_frozen_timeout_profiles(self):
        for timeout in (
            Source.V5_TIMEOUT_SECONDS, Source.AMENDED_TIMEOUT_SECONDS,
        ):
            Source.configure(timeout)
            self.assertEqual(Source.V5.TASK_TIMEOUT_SECONDS, timeout)
            self.assertEqual(Source.Base.TASK_TIMEOUT_SECONDS, timeout)
            self.assertEqual(Source.V5.TMP_ROOT, Source.TMP_ROOT)
            self.assertEqual(
                Source.V5.SOURCE_SNAPSHOT_SCHEMA,
                Source.SOURCE_SNAPSHOT_SCHEMA,
            )
        for invalid in (0, 57600, True, "115200"):
            with self.assertRaises(Source.SourceAuditError):
                Source.configure(invalid)

    def test_v6_manifest_expands_v5_and_binds_new_boundary(self):
        self.assertTrue(set(Source.V5_CODE_MANIFEST_FILES) <= set(
            Source.CODE_MANIFEST_FILES
        ))
        for relative in (
            "experiments/audit_pdb_terminal_incidence_confirmation_sources_v6.py",
            "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v6.py",
            "experiments/pdb_terminal_incidence_confirmation_source_audit_v6_protocol.md",
            "experiments/pdb_terminal_incidence_confirmation_safe_io_v6.py",
            "experiments/pdb_terminal_incidence_confirmation_source_scan_v6.slurm",
            "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v6.py",
            "experiments/artifacts/pdb-terminal-incidence-confirmation-v6/"
            "v5-infrastructure-failure-diagnostic-v6.json",
        ):
            self.assertIn(relative, Source.CODE_MANIFEST_FILES)

    def test_launch_materials_carry_exact_v5_benchmark_revision(self):
        revision = Source.Base.Inventory.BENCHMARK_REVISION
        diagnostic = {
            "resource_mapping": {
                "task_timeout_seconds": Source.AMENDED_TIMEOUT_SECONDS,
            },
            "pre_diagnosis_freeze": {},
            "v5_launch_receipt": {"benchmark_revision": revision},
            "v5_launch_receipt_sha256": "b" * 64,
            "v5_source_inventory_sha256": "c" * 64,
            "reusable_v5_shard_indices": [0, 1],
            "repair_v5_shard_indices": [2],
            "reuse_eligibility_rule": (
                "scheduler state COMPLETED with exit 0:0 only"
            ),
        }

        def root_identity(path, _label):
            return {"path": str(path)}

        with (
            mock.patch.object(Launch.Source, "configure"),
            mock.patch.object(
                Launch.Source, "validate_code_manifest", return_value={}
            ),
            mock.patch.object(Launch, "_validate_freeze_against_manifest"),
            mock.patch.object(Launch, "_render_slurm", return_value=b"slurm\n"),
            mock.patch.object(Launch, "_sha256", return_value="d" * 64),
            mock.patch.object(
                Launch, "_root_identity", side_effect=root_identity
            ),
            mock.patch.object(Launch, "ARRAY_TASKS", 3),
        ):
            materials = Launch._launch_materials(
                "a" * 64, diagnostic, repository_commit_id="e" * 40
            )
            self.assertEqual(materials["benchmark_revision"], revision)
            changed = {
                **diagnostic,
                "v5_launch_receipt": {"benchmark_revision": "f" * 40},
            }
            with self.assertRaisesRegex(
                Launch.LaunchAuditError, "benchmark revision"
            ):
                Launch._launch_materials(
                    "a" * 64, changed, repository_commit_id="e" * 40
                )

    def test_private_wrapper_does_not_mutate_public_v5_producer(self):
        self.assertEqual(
            Launch.V5Source.TASK_TIMEOUT_SECONDS,
            Launch.V5_TASK_TIMEOUT_SECONDS,
        )
        self.assertNotEqual(Launch.V5Source.TMP_ROOT, Source.TMP_ROOT)
        self.assertNotEqual(
            Launch.V5Source.DEFAULT_SHARDS, Source.DEFAULT_SHARDS
        )

    def test_diagnosis_freeze_is_first_and_blocks_all_v5_access_on_failure(self):
        order = []

        def freeze():
            order.append("freeze")
            raise Launch.LaunchAuditError("dirty design")

        with (
            mock.patch.object(Launch, "_pre_diagnosis_freeze", side_effect=freeze),
            mock.patch.object(Launch.V5Launch, "_load_launch") as load,
            mock.patch.object(Launch, "_scheduler_rows") as scheduler,
            mock.patch.object(Launch, "_safe_tree") as tree,
            self.assertRaisesRegex(Launch.LaunchAuditError, "dirty design"),
        ):
            Launch.diagnose_v5()
        self.assertEqual(order, ["freeze"])
        load.assert_not_called()
        scheduler.assert_not_called()
        tree.assert_not_called()

    def test_pre_diagnosis_freeze_requires_clean_tracked_at_parent(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-freeze-") as tmp:
            root = Path(tmp)
            (root / "a").write_bytes(b"a\n")
            (root / "b").write_bytes(b"b\n")
            files = ("a", "b")
            identity = {
                "path": str(Launch.V5Launch.Generic.JJ_COMMAND),
                "sha256": Launch.V5Launch.Generic.JJ_EXECUTABLE_SHA256,
            }
            with (
                mock.patch.multiple(
                    Launch,
                    REPO=root,
                    PRE_DIAGNOSIS_FILES=files,
                    DIAGNOSTIC_RELATIVE_PATH="diagnostic.json",
                ),
                mock.patch.object(
                    Source, "CODE_MANIFEST_FILES",
                    ("a", "b", "diagnostic.json"),
                ),
                mock.patch.object(
                    Launch, "_executable_identity", return_value=identity
                ),
                mock.patch.object(
                    Launch.subprocess,
                    "check_output",
                    # `jj file list` uses repository tree order, which need
                    # not match Python's lexical ordering of the exact path
                    # set (notably around a directory and a `-vN` sibling).
                    side_effect=["", "b\na\n", "a" * 40] * 2,
                ) as run,
            ):
                freeze = Launch._pre_diagnosis_freeze()
            self.assertEqual(freeze["repository_commit_id"], "a" * 40)
            self.assertEqual([item["path"] for item in freeze["files"]], ["a", "b"])
            commands = [call.args[0] for call in run.call_args_list]
            self.assertIn("@", commands[0])
            self.assertIn("@-", commands[1])
            self.assertIn("@-", commands[2])
            self.assertEqual(len(commands), 6)

    def test_pre_diagnosis_bytes_must_match_later_manifest(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-freeze-manifest-") as tmp:
            root = Path(tmp)
            paths = ("a", "b")
            for name, payload in (("a", b"a\n"), ("b", b"b\n")):
                (root / name).write_bytes(payload)
            diagnostic_name = "diagnostic.json"
            (root / diagnostic_name).write_bytes(b"diagnostic\n")
            manifest_path = root / "manifest.sha256"
            with (
                mock.patch.multiple(
                    Launch,
                    REPO=root,
                    PRE_DIAGNOSIS_FILES=paths,
                    DIAGNOSTIC_RELATIVE_PATH=diagnostic_name,
                ),
                mock.patch.object(
                    Source, "CODE_MANIFEST_FILES",
                    ("a", "b", diagnostic_name),
                ),
            ):
                records = Launch._pre_diagnosis_file_records()
                freeze = {
                    "schema": Launch.DIAGNOSTIC_SCHEMA
                    + "/pre-diagnosis-freeze/v1",
                    "repository_commit_id": "a" * 40,
                    "working_copy_revision": "@",
                    "committed_revision": "@-",
                    "scoped_diff_empty": True,
                    "diagnostic_excluded": True,
                    "jj": {
                        "path": str(Launch.V5Launch.Generic.JJ_COMMAND),
                        "sha256": Launch.V5Launch.Generic.JJ_EXECUTABLE_SHA256,
                    },
                    "files": records,
                    "files_sha256": hashlib.sha256(
                        Launch._canonical_json(records)
                    ).hexdigest(),
                }
                manifest_path.write_text("".join(
                    "{}  {}\n".format(
                        hashlib.sha256((root / name).read_bytes()).hexdigest(),
                        name,
                    )
                    for name in ("a", "b", diagnostic_name)
                ), encoding="ascii")
                manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
                Launch._validate_freeze_against_manifest(
                    freeze, manifest_path, manifest_sha
                )
                (root / "a").write_bytes(b"changed\n")
                with self.assertRaisesRegex(
                    Launch.LaunchAuditError, "freeze changed"
                ):
                    Launch._validate_freeze_against_manifest(
                        freeze, manifest_path, manifest_sha
                    )

    def test_pre_diagnosis_freeze_rejects_dirty_or_untracked_design(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-dirty-freeze-") as tmp:
            root = Path(tmp)
            (root / "a").write_bytes(b"a\n")
            identity = {
                "path": str(Launch.V5Launch.Generic.JJ_COMMAND),
                "sha256": Launch.V5Launch.Generic.JJ_EXECUTABLE_SHA256,
            }
            for answers in (
                ["M a\n", "a\n", "a" * 40] * 2,
                ["", "", "a" * 40] * 2,
                ["", "a\na\n", "a" * 40] * 2,
                ["", "a\n", "not-a-commit"] * 2,
            ):
                with (
                    mock.patch.multiple(
                        Launch,
                        REPO=root,
                        PRE_DIAGNOSIS_FILES=("a",),
                        DIAGNOSTIC_RELATIVE_PATH="diagnostic.json",
                    ),
                    mock.patch.object(
                        Source, "CODE_MANIFEST_FILES", ("a", "diagnostic.json")
                    ),
                    mock.patch.object(
                        Launch, "_executable_identity", return_value=identity
                    ),
                    mock.patch.object(
                        Launch.subprocess, "check_output", side_effect=answers
                    ),
                    self.assertRaisesRegex(
                        Launch.LaunchAuditError, "clean and tracked"
                    ),
                ):
                    Launch._pre_diagnosis_freeze()

    def test_only_completed_zero_is_reusable_and_complement_is_repaired(self):
        rows = [
            _row(0),
            _row(1, "FAILED", "75:0"),
            _row(2, "OUT_OF_MEMORY", "0:125"),
            _row(3, "NODE_FAIL", "0:9"),
        ]
        with mock.patch.object(Launch, "ARRAY_TASKS", 4):
            reusable, repair = Launch._partition_terminal_rows(rows)
        self.assertEqual(reusable, [0])
        self.assertEqual(repair, [1, 2, 3])

    def test_active_unknown_and_application_rows_fail_closed(self):
        for state, exit_code, pattern in (
            ("RUNNING", "0:0", "not terminal"),
            ("FAILED", "2:0", "non-infrastructure"),
            ("CANCELLED", "0:15", "non-infrastructure"),
            ("COMPLETED", "1:0", "non-infrastructure"),
        ):
            with (
                mock.patch.object(Launch, "ARRAY_TASKS", 1),
                self.assertRaisesRegex(Launch.LaunchAuditError, pattern),
            ):
                Launch._partition_terminal_rows([_row(0, state, exit_code)])

    def test_row_set_must_be_ordered_complete_and_exact(self):
        rows = [_row(0), _row(1)]
        with mock.patch.object(Launch, "ARRAY_TASKS", 2):
            changed = [dict(row) for row in rows]
            changed.reverse()
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._partition_terminal_rows(changed)
            changed = [dict(row) for row in rows]
            changed[1]["partition"] = "cpu"
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._partition_terminal_rows(changed)
            for field, value in (
                ("state", None), ("exit_code", 0), ("elapsed", 60)
            ):
                changed = [dict(row) for row in rows]
                changed[0][field] = value
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._partition_terminal_rows(changed)

    def test_raw_scheduler_parser_rejects_normalized_or_malformed_fields(self):
        good = (
            "42_0|COMPLETED|0:0|00:01:00|fat\n"
            "42_2|FAILED|75:0|1-00:00:00|fat\n"
        )
        with (
            mock.patch.object(Launch, "ARRAY_TASKS", 3),
            mock.patch.object(Launch, "_sacct", return_value=good),
        ):
            rows = Launch._scheduler_rows("42", [0, 2])
        self.assertEqual([row["array_task"] for row in rows], [0, 2])
        for changed in (
            good.replace("COMPLETED", "COMPLETED+"),
            good.replace("0:0", "00:0", 1),
            good.replace("00:01:00", "0:01:00"),
            good.replace("42_2", "42_1"),
            good + "42|COMPLETED|0:0|00:01:00|fat\n",
        ):
            with (
                mock.patch.object(Launch, "ARRAY_TASKS", 3),
                mock.patch.object(Launch, "_sacct", return_value=changed),
                self.assertRaises(Launch.LaunchAuditError),
            ):
                Launch._scheduler_rows("42", [0, 2])

    def test_failure_accounting_is_exact_and_parent_correlated(self):
        row = _row(1, "FAILED", "75:0")
        parent = "42_1|42_1|FAILED|75:0|00:01:00|2T|1G|2G|node1\n"
        batch = "42_1.batch|42_1.batch|FAILED|75:0|00:01:00||1G|2G|node1\n"
        records = Launch._parse_failure_accounting(parent + batch, "42", row)
        self.assertEqual([item["job_id"] for item in records], [
            "42_1", "42_1.batch",
        ])
        digit_parent = parent.replace("|42_1|FAILED", "|9001|FAILED")
        digit_batch = batch.replace(
            "|42_1.batch|FAILED", "|9001.batch|FAILED"
        )
        digit_extern = (
            "42_1.extern|9001.extern|COMPLETED|0:0|00:01:00|||"
            "|node1\n"
        )
        digit_records = Launch._parse_failure_accounting(
            digit_parent + digit_batch + digit_extern, "42", row
        )
        self.assertEqual(
            [item["job_id_raw"] for item in digit_records],
            ["9001", "9001.batch", "9001.extern"],
        )
        for changed in (
            parent.replace("00:01:00", "00:02:00"),
            parent.replace("FAILED", "FAILED+"),
            parent.replace("2T", "2048Q"),
            parent.replace("42_1|42_1|", "42_1|99.batch|"),
            parent + parent,
            parent + "42_1.0|42_1.0|FAILED|75:0|00:01:00|||2G|node1\n",
            parent + batch.replace("42_1.batch|42_1.batch|", "42_1.batch|99|"),
            parent + batch.replace("|42_1.batch|FAILED", "|42_2.batch|FAILED"),
            digit_parent + digit_batch.replace(
                "|9001.batch|FAILED", "|9002.batch|FAILED"
            ),
            batch + parent,
        ):
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._parse_failure_accounting(changed, "42", row)

    def test_diagnostic_reload_rechecks_common_job_id_raw_root(self):
        row = _row(0, "FAILED", "75:0")
        accounting = Launch._parse_failure_accounting(
            "42_0|9001|FAILED|75:0|00:01:00|2T|1G|2G|node1\n"
            "42_0.batch|9001.batch|FAILED|75:0|00:01:00||1G|2G|node1\n",
            "42",
            row,
        )
        failure = {
            "array_task": 0,
            "state": "FAILED",
            "exit_code": "75:0",
            "failure_class": "translator-wallclock-timeout",
            "task_name": "d:p",
            "log_inspected": True,
            "path": str(Launch.V5_OUTPUT_DIR / "slurm-42_0.out"),
            "bytes": 1,
            "sha256": "a" * 64,
            "accounting_rows": accounting,
        }
        self.assertEqual(
            Launch._validate_failure_records([failure], [row], [0], "42"),
            ["translator-wallclock-timeout"],
        )
        changed_accounting = [dict(record) for record in accounting]
        changed_accounting[1]["job_id_raw"] = "9002.batch"
        changed = {**failure, "accounting_rows": changed_accounting}
        with self.assertRaises(Launch.LaunchAuditError):
            Launch._validate_failure_records([changed], [row], [0], "42")

    def test_v6_resource_accounting_is_raw_ordered_and_elapsed_correlated(self):
        token = "a" * 24
        name, _comment = Launch._submission_identity(token)
        row = _row(2)
        diagnostic = {
            "repair_v5_shard_indices": [2],
            "resource_mapping": Launch._resource_mapping({
                "scheduler-out-of-memory"
            }),
        }
        output = (
            "42_2|{}|fat|normal|1|3000G|16:40:00|00:01:00|"
            "COMPLETED|0:0|{}\n"
        ).format(Launch.ACCOUNT, name)
        with mock.patch.object(Launch, "_sacct", return_value=output):
            contract = Launch._scheduler_contract_rows(
                {"job_id": "42", "submission_token": token},
                diagnostic,
                [row],
            )
        self.assertEqual(contract[0]["elapsed"], row["elapsed"])
        for changed in (
            output.replace("COMPLETED", "COMPLETED+"),
            output.replace("00:01:00", "00:02:00"),
            output.replace("42_2", "42_1"),
            output + output,
        ):
            with (
                mock.patch.object(Launch, "_sacct", return_value=changed),
                self.assertRaises(Launch.LaunchAuditError),
            ):
                Launch._scheduler_contract_rows(
                    {"job_id": "42", "submission_token": token},
                    diagnostic,
                    [row],
                )

    def test_normalized_partition_is_sorted_unique_disjoint_exact_union(self):
        with mock.patch.object(Launch, "ARRAY_TASKS", 4):
            Launch._validate_shard_partition([0, 2], [1, 3])
            for reusable, repair in (
                ([2, 0], [1, 3]),
                ([0, 0, 2], [1, 3]),
                ([0, 2], [2, 3]),
                ([0, 2], [1]),
                ([0, 1, 2, 3], []),
                ([False, 2], [1, 3]),
            ):
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._validate_shard_partition(reusable, repair)

    def test_resource_mapping_is_class_only_uniform_and_at_fixed_ceiling(self):
        timeout = Launch._resource_mapping({"translator-wallclock-timeout"})
        self.assertEqual(timeout["task_timeout_seconds"], 115200)
        self.assertEqual(timeout["time_limit"], "3-00:00:00")
        self.assertEqual(timeout["memory"]["requested"], "2T")
        oom = Launch._resource_mapping({"scheduler-out-of-memory"})
        self.assertEqual(oom["task_timeout_seconds"], 28800)
        self.assertEqual(oom["memory"]["requested"], "3000G")
        self.assertEqual(oom["memory"]["option"], "--mem=3000G")
        both = Launch._resource_mapping({
            "translator-wallclock-timeout", "scheduler-out-of-memory",
        })
        self.assertTrue(both["uniform_for_every_repair_shard"])
        self.assertEqual(both["outcome_fields_consulted"], [])
        ceiling = both["resource_ceiling_policy"]
        self.assertFalse(ceiling["child_level_exclusion_allowed"])
        self.assertFalse(ceiling["partial_repair_shards_usable"])
        self.assertTrue(ceiling["seal_requires_every_repair_shard_completed_0_0"])

    def test_resource_mapping_rejects_empty_or_unclassified_set(self):
        for classes in (set(), {"application-error"}):
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._resource_mapping(classes)

    def test_recovery_array_is_exact_sparse_and_unthrottled(self):
        self.assertEqual(Launch._array_spec([2, 7, 11]), "2,7,11")
        for invalid in ([], [7, 2], [2, 2], [-1], [820]):
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._array_spec(invalid)

    def test_submit_command_uses_only_complement_and_uniform_mapping(self):
        diagnostic = {
            "repair_v5_shard_indices": [2, 7],
            "resource_mapping": Launch._resource_mapping({
                "translator-wallclock-timeout", "scheduler-out-of-memory",
            }),
        }
        command = Launch._submit_command(diagnostic, "a" * 24)
        self.assertIn("--array=2,7", command)
        self.assertIn("--mem=3000G", command)
        self.assertIn("--time=3-00:00:00", command)
        self.assertIn("--nice=0", command)
        self.assertIn("--no-requeue", command)
        self.assertFalse(any(
            "%" in item for item in command if item.startswith("--array=")
        ))
        self.assertTrue(all(item.startswith("--") for item in command[1:]))

    def test_failure_log_classifies_only_exact_empty_stderr_timeout(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-timeout-") as tmp:
            root = Path(tmp)
            path = root / "slurm-42_0.out"
            path.write_bytes(
                b"[1/2] d:p\n"
                b"infrastructure error: translator exceeded 28800s for d:p; "
                b"stderr_sha256=" + Launch.EMPTY_SHA256.encode("ascii")
                + b"; stderr_tail=''\n"
            )
            with mock.patch.object(Launch, "V5_OUTPUT_DIR", root):
                record = Launch._failure_log_record(
                    "42", _row(0, "FAILED", "75:0"),
                    [{"directory": "d", "problem": "p"}],
                )
                self.assertEqual(
                    record["failure_class"], "translator-wallclock-timeout"
                )
                path.write_bytes(path.read_bytes().replace(
                    Launch.EMPTY_SHA256.encode("ascii"), b"f" * 64
                ))
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._failure_log_record(
                        "42", _row(0, "FAILED", "75:0"),
                        [{"directory": "d", "problem": "p"}],
                    )
                path.write_bytes(
                    b"[1/2] wrong:p\n"
                    b"infrastructure error: translator exceeded 28800s for "
                    b"wrong:p; stderr_sha256="
                    + Launch.EMPTY_SHA256.encode("ascii")
                    + b"; stderr_tail=''\n"
                )
                with self.assertRaisesRegex(
                    Launch.LaunchAuditError, "identity changed"
                ):
                    Launch._failure_log_record(
                        "42", _row(0, "FAILED", "75:0"),
                        [{"directory": "d", "problem": "p"}],
                    )

    def test_failure_log_classifies_only_scheduler_oom_evidence(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-oom-") as tmp:
            root = Path(tmp)
            path = root / "slurm-42_0.out"
            path.write_bytes(
                b"[1/2] d:p\ntranslator critical exit -9\noom_kill\n"
            )
            with mock.patch.object(Launch, "V5_OUTPUT_DIR", root):
                record = Launch._failure_log_record(
                    "42", _row(0, "OUT_OF_MEMORY", "0:125"),
                    [{"directory": "d", "problem": "p"}],
                )
                self.assertEqual(
                    record["failure_class"], "scheduler-out-of-memory"
                )
                path.write_bytes(b"[1/2] d:p\ntranslator critical exit -9\n")
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._failure_log_record(
                        "42", _row(0, "OUT_OF_MEMORY", "0:125"),
                        [{"directory": "d", "problem": "p"}],
                    )

    def test_scheduler_interruption_never_opens_a_log(self):
        with mock.patch.object(Launch, "_safe_file") as read:
            record = Launch._failure_log_record(
                "42", _row(0, "NODE_FAIL", "0:9")
            )
        read.assert_not_called()
        self.assertFalse(record["log_inspected"])
        self.assertEqual(record["failure_class"], "scheduler-interruption")

    def test_classified_failure_log_is_bound_to_opaque_tree_record(self):
        failure = {
            "log_inspected": True,
            "path": str(Launch.V5_OUTPUT_DIR / "slurm-42_7.out"),
            "bytes": 17,
            "sha256": "a" * 64,
        }
        manifest = {"files": [{
            "path": "slurm-42_7.out", "bytes": 17, "sha256": "a" * 64,
        }]}
        Launch._validate_failure_logs_against_tree([failure], manifest)
        for key, value in (("bytes", 18), ("sha256", "b" * 64)):
            changed = dict(failure)
            changed[key] = value
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._validate_failure_logs_against_tree([changed], manifest)
        escaped = dict(failure, path="/tmp/slurm-42_7.out")
        with self.assertRaises(Launch.LaunchAuditError):
            Launch._validate_failure_logs_against_tree([escaped], manifest)

    def test_diagnose_freezes_scheduler_partition_without_outcome_fields(self):
        rows = [
            _row(0),
            _row(1, "FAILED", "75:0"),
            _row(2, "OUT_OF_MEMORY", "0:125"),
        ]
        launch = {
            "job_id": "42",
            "code_manifest_sha256": "a" * 64,
            "source_inventory_sha256": "b" * 64,
        }

        def failure(_job_id, row, expected):
            self.assertEqual(len(expected), 2)
            failure_class = {
                "FAILED": "translator-wallclock-timeout",
                "OUT_OF_MEMORY": "scheduler-out-of-memory",
            }[row["state"]]
            return {
                "array_task": row["array_task"],
                "state": row["state"],
                "exit_code": row["exit_code"],
                "failure_class": failure_class,
                "log_inspected": True,
                "task_name": "d:p",
                "path": str(
                    Launch.V5_OUTPUT_DIR /
                    "slurm-42_{}.out".format(row["array_task"])
                ),
                "bytes": 1,
                "sha256": "c" * 64,
            }

        def accounting(_job_id, row):
            return [{
                "job_id": "42_{}".format(row["array_task"]),
                "state": row["state"],
                "exit_code": row["exit_code"],
                "job_id_raw": "42_{}".format(row["array_task"]),
                "elapsed": row["elapsed"],
                "requested_memory": "2T",
                "max_rss": None,
                "max_vm_size": None,
                "node_list": "node",
            }]

        opaque = {
            "sha256": "d" * 64,
            "root_identity": {},
            "files_count": 0,
            "files": [],
            "successful_files_parsed": False,
            "successful_files_opaque_hashed": True,
            "noncompleted_partial_files_quarantined": [],
            "noncompleted_partial_files_used": False,
        }
        freeze = {"synthetic_pre_diagnosis_freeze": True}
        with tempfile.TemporaryDirectory(prefix="source-v6-diagnose-") as tmp:
            root = Path(tmp)
            intent = root / "v5-intent.json"
            intent.write_bytes(b"intent\n")
            absent = [root / "absent-{}".format(index) for index in range(12)]
            with (
                mock.patch.object(Launch, "ARRAY_TASKS", 3),
                mock.patch.object(Launch, "SEAL_STAGE_ARTIFACTS", ()),
                mock.patch.object(Launch, "DIAGNOSTIC", absent[0]),
                mock.patch.object(
                    Launch, "_pre_diagnosis_freeze", return_value=freeze
                ),
                mock.patch.multiple(
                    Launch,
                    INTENT=absent[1], LAUNCH_RECEIPT=absent[2],
                    EXECUTION_RECEIPT=absent[3], OUTPUT_DIR=absent[4],
                    TMP_ROOT=absent[5], UNION_DIR=absent[6],
                    CANDIDATE=absent[7], ATTESTATION=absent[8],
                    CODE_MANIFEST=absent[9], V5_EXECUTION_RECEIPT=absent[10],
                    V5_CANDIDATE=absent[11], V5_ATTESTATION=root / "absent-v5",
                    V5_INTENT=intent,
                ),
                mock.patch.object(
                    Launch.V5Launch, "_load_launch", return_value=("e" * 64, launch)
                ),
                mock.patch.object(Launch, "_scheduler_rows", return_value=rows),
                mock.patch.object(
                    Launch.V5Source, "load_inventory_manifest",
                    return_value=("b" * 64, [{} for _ in range(6)]),
                ),
                mock.patch.object(Launch, "_failure_log_record", side_effect=failure),
                mock.patch.object(
                    Launch, "_failure_accounting_rows", side_effect=accounting
                ),
                mock.patch.object(
                    Launch, "_opaque_v5_output_manifest", return_value=opaque
                ),
                mock.patch.object(Launch, "_validate_opaque_v5_manifest"),
                mock.patch.object(Launch, "_validate_failure_logs_against_tree"),
                mock.patch.object(
                    Launch, "_exclusive_json", return_value="f" * 64
                ) as publish,
            ):
                with redirect_stdout(io.StringIO()):
                    Launch.diagnose_v5()
        diagnostic = publish.call_args.args[1]
        self.assertEqual(set(diagnostic), Launch.DIAGNOSTIC_FIELDS)
        self.assertIs(diagnostic["pre_diagnosis_freeze"], freeze)
        self.assertEqual(diagnostic["reusable_v5_shard_indices"], [0])
        self.assertEqual(diagnostic["repair_v5_shard_indices"], [1, 2])
        self.assertEqual(diagnostic["logical_shards"], 3)
        self.assertEqual(diagnostic["candidates"], Source.CANDIDATE_COUNT)
        self.assertEqual(diagnostic["reused_v5_shards"], 1)
        self.assertEqual(diagnostic["repaired_v5_shards"], 2)
        self.assertFalse(diagnostic["whole_campaign_rerun"])
        self.assertTrue(diagnostic["outcome_blind_selective_repair"])
        self.assertFalse(diagnostic["noncompleted_v5_shards_used"])
        self.assertFalse(diagnostic["source_support_outcomes_used_for_v6_design"])
        self.assertFalse(diagnostic["successful_v5_shard_contents_parsed"])
        self.assertEqual(
            diagnostic["resource_mapping"]["outcome_fields_consulted"], []
        )

    def test_opaque_manifest_requires_completed_triplet_without_json_parse(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-tree-") as tmp:
            root = Path(tmp)
            root.chmod(0o700)
            inventory = root / "source-inventory-v5.json"
            inventory.write_bytes(b"not json; integrity only\n")
            shard = root / "shard-0000-of-0820.json"
            environment = root / "environment-0000-of-0820.json"
            log = root / "slurm-42_0.out"
            shard.write_bytes(b"opaque outcome bytes\n")
            environment.write_bytes(b"opaque environment bytes\n")
            log.write_bytes(b"opaque completed log\n")
            launch = {
                "job_id": "42",
                "source_inventory_sha256": hashlib.sha256(
                    inventory.read_bytes()
                ).hexdigest(),
            }
            with (
                mock.patch.object(Launch, "ARRAY_TASKS", 1),
                mock.patch.object(Launch, "V5_OUTPUT_DIR", root),
                mock.patch.object(Launch, "V5_SOURCE_INVENTORY", inventory),
            ):
                launch["launch_root_identities"] = {
                    "output_dir": Launch._root_identity(root, "test root")
                }
                manifest = Launch._opaque_v5_output_manifest(
                    launch, [0], []
                )
                self.assertFalse(manifest["successful_files_parsed"])
                self.assertTrue(manifest["successful_files_opaque_hashed"])
                environment.unlink()
                with self.assertRaisesRegex(
                    Launch.LaunchAuditError, "lacks a reusable triplet"
                ):
                    Launch._opaque_v5_output_manifest(launch, [0], [])

    def test_v6_tree_hash_streams_bounded_chunks_without_payload_retention(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-stream-") as tmp:
            root = Path(tmp)
            payload = b"x" * (2 * SafeTreeIO.CHUNK_BYTES + 17)
            (root / "large").write_bytes(payload)
            chunks = []
            tree = SafeTreeIO.read_streaming_tree(
                root,
                label="synthetic streaming tree",
                expected_path=root,
                chunk_callback=lambda _path, size: chunks.append(size),
            )
        self.assertEqual(tree.files[0].sha256, hashlib.sha256(payload).hexdigest())
        self.assertFalse(hasattr(tree.files[0], "raw"))
        self.assertTrue(chunks)
        self.assertLessEqual(max(chunks), SafeTreeIO.CHUNK_BYTES)

    def test_v6_tree_hash_rejects_symlinks_mutation_and_replacement_races(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-tree-race-") as tmp:
            root = Path(tmp)
            target = root / "target"
            target.write_bytes(b"target\n")
            link = root / "link"
            link.symlink_to(target.name)
            with self.assertRaises(SafeTreeIO.SafeTreeError):
                SafeTreeIO.read_streaming_tree(root, label="symlink tree")
            link.unlink()
            data = root / "data"
            data.write_bytes(b"before\n")

            def mutate(_path, _fd):
                data.write_bytes(b"after!\n")

            with self.assertRaises(SafeTreeIO.SafeTreeError):
                SafeTreeIO.read_streaming_tree(
                    root, label="mutated tree", read_callback=mutate
                )
            data.write_bytes(b"stable\n")

            def replace(_path, _fd):
                data.unlink()
                data.symlink_to(target.name)

            with self.assertRaises(SafeTreeIO.SafeTreeError):
                SafeTreeIO.read_streaming_tree(
                    root, label="replaced tree", read_callback=replace
                )

    def test_v6_tree_hash_final_sweep_catches_early_leaf_mutation(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-late-race-") as tmp:
            root = Path(tmp)
            early = root / "a"
            late = root / "z"
            early.write_bytes(b"before\n")
            late.write_bytes(b"stable\n")
            visits = {"z": 0}

            def mutate_after_early_second_pass(relative, _size):
                if relative == "z":
                    visits["z"] += 1
                    if visits["z"] == 2:
                        early.write_bytes(b"definitely changed after rehash\n")

            with self.assertRaises(SafeTreeIO.SafeTreeError):
                SafeTreeIO.read_streaming_tree(
                    root,
                    label="late mutation tree",
                    chunk_callback=mutate_after_early_second_pass,
                )

    def test_noncompleted_partial_shard_is_quarantined_never_selected(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-quarantine-") as tmp:
            root = Path(tmp)
            root.chmod(0o700)
            inventory = root / "source-inventory-v5.json"
            inventory.write_bytes(b"inventory\n")
            (root / "shard-0001-of-0820.json").write_bytes(b"partial\n")
            (root / "slurm-42_1.out").write_bytes(b"failure\n")
            launch = {
                "job_id": "42",
                "source_inventory_sha256": hashlib.sha256(
                    inventory.read_bytes()
                ).hexdigest(),
            }
            with (
                mock.patch.object(Launch, "ARRAY_TASKS", 2),
                mock.patch.object(Launch, "V5_OUTPUT_DIR", root),
                mock.patch.object(Launch, "V5_SOURCE_INVENTORY", inventory),
            ):
                launch["launch_root_identities"] = {
                    "output_dir": Launch._root_identity(root, "test root")
                }
                manifest = Launch._opaque_v5_output_manifest(
                    launch, [], [0, 1]
                )
        self.assertEqual(
            [item["path"] for item in manifest[
                "noncompleted_partial_files_quarantined"
            ]],
            ["shard-0001-of-0820.json"],
        )
        self.assertFalse(manifest["noncompleted_partial_files_used"])

    def test_union_topology_retains_root_and_rejects_extras_or_replacement(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-union-") as tmp:
            parent = Path(tmp)
            root = parent / "union"
            root.mkdir(mode=0o700)
            with (
                mock.patch.object(Launch, "ARRAY_TASKS", 1),
                mock.patch.object(Launch, "UNION_DIR", root),
            ):
                identity = Launch._root_identity(root, "synthetic union")
                expected = Launch._expected_union_names()[0]
                (root / expected).write_bytes(b"shard\n")
                first = Launch._union_tree(identity, complete=True)
                self.assertEqual(first, Launch._union_tree(identity, complete=True))
                (root / "extra").write_bytes(b"extra\n")
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._union_tree(identity, complete=True)
                (root / "extra").unlink()
                old = parent / "old"
                root.rename(old)
                root.mkdir(mode=0o700)
                (root / expected).write_bytes(b"shard\n")
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._union_tree(identity, complete=True)

    def test_union_parse_must_match_frozen_source_sequence_before_publication(self):
        candidate = {"records_sha256": "a" * 64}
        raw = Launch._canonical_json(candidate)
        with (
            mock.patch.object(
                Launch, "_expected_candidate_from_union",
                return_value=(raw, candidate),
            ),
            mock.patch.object(Launch, "_publish_or_validate_bytes") as publish,
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "frozen source sequence"
            ),
        ):
            Launch._prepare_candidate({}, "c" * 64, "b" * 64)
        publish.assert_not_called()

    def test_interrupted_seal_boundaries_resume_only_identical_artifacts(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-seal-stages-") as tmp:
            root = Path(tmp)
            for boundary in ("union", "candidate", "attestation"):
                path = root / boundary
                raw = (boundary + "\n").encode("ascii")
                digest = Launch._publish_or_validate_bytes(path, raw, boundary)
                inode = path.stat().st_ino
                self.assertEqual(
                    Launch._publish_or_validate_bytes(path, raw, boundary),
                    digest,
                )
                self.assertEqual(path.stat().st_ino, inode)
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._publish_or_validate_bytes(
                        path, raw + b"changed\n", boundary
                    )
            receipt = root / "receipt.json"
            value = {"schema": "synthetic", "sha256": "a" * 64}
            digest = Launch._publish_or_validate_json(
                receipt, value, "receipt boundary"
            )
            self.assertEqual(
                Launch._publish_or_validate_json(
                    receipt, value, "receipt boundary"
                ),
                digest,
            )
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._publish_or_validate_json(
                    receipt, {**value, "sha256": "b" * 64},
                    "receipt boundary",
                )

    def test_recover_seal_accepts_unmarked_union_root_only_when_empty(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-root-window-") as tmp:
            parent = Path(tmp)
            union = parent / "union"
            marker = parent / "union-root-stage.json"
            union.mkdir(mode=0o700)
            with mock.patch.multiple(
                Launch, UNION_DIR=union, UNION_ROOT_STAGE=marker
            ):
                with self.assertRaisesRegex(
                    Launch.LaunchAuditError, "predates its stage"
                ):
                    Launch._ensure_union_root("a" * 64, recovery=False)
                stage_sha, stage = Launch._ensure_union_root(
                    "a" * 64, recovery=True
                )
                self.assertEqual(stage["seal_plan_sha256"], "a" * 64)
                self.assertEqual(
                    stage_sha, hashlib.sha256(marker.read_bytes()).hexdigest()
                )

            marker.unlink()
            (union / "unexpected-partial").write_bytes(b"partial\n")
            with (
                mock.patch.multiple(
                    Launch, UNION_DIR=union, UNION_ROOT_STAGE=marker
                ),
                self.assertRaises(Launch.LaunchAuditError),
            ):
                Launch._ensure_union_root("a" * 64, recovery=True)

    def test_recover_seal_resumes_each_publication_boundary(self):
        real_publish_json = Launch._publish_or_validate_json
        for boundary in ("union", "candidate", "attestation", "receipt"):
            with self.subTest(boundary=boundary), tempfile.TemporaryDirectory(
                prefix="source-v6-recover-boundary-"
            ) as tmp:
                root = Path(tmp)
                paths = {
                    "plan": root / "plan.json",
                    "union_root": root / "union-root.json",
                    "union": root / "union.json",
                    "candidate": root / "candidate.json",
                    "candidate_stage": root / "candidate-stage.json",
                    "attestation": root / "attestation.json",
                    "attestation_stage": root / "attestation-stage.json",
                    "receipt": root / "receipt.json",
                    "union_dir": root / "union-dir",
                }
                interrupted = {boundary: False}
                context = {
                    "plan": {
                        "schema": "synthetic-seal-plan",
                        "source_record_sequence_sha256": "b" * 64,
                    },
                    "diagnostic": {},
                    "v6_output_tree": {},
                }

                def maybe_interrupt(name):
                    if name == boundary and not interrupted[name]:
                        interrupted[name] = True
                        raise RuntimeError("synthetic {} interruption".format(name))

                def prepare_union(_diagnostic, _tree, plan_sha, *, recovery):
                    root_stage = {
                        "schema": Launch.UNION_ROOT_STAGE_SCHEMA,
                        "seal_plan_sha256": plan_sha,
                        "root_identity": {"synthetic": True},
                    }
                    root_sha = Launch._publish_or_validate_json(
                        paths["union_root"], root_stage, "synthetic union root"
                    )
                    stage = {
                        "schema": Launch.UNION_STAGE_SCHEMA,
                        "seal_plan_sha256": plan_sha,
                        "union_root_stage_sha256": root_sha,
                        "sources": [],
                        "sources_sha256": hashlib.sha256(
                            Launch._canonical_json([])
                        ).hexdigest(),
                        "tree": {"sha256": "a" * 64},
                    }
                    stage_sha = Launch._publish_or_validate_json(
                        paths["union"], stage, "synthetic union"
                    )
                    maybe_interrupt("union")
                    return stage_sha, stage

                candidate_value = {
                    "records_sha256": "b" * 64,
                    "confirmation_prelaunch_authorized": True,
                }
                candidate_raw = Launch._canonical_json(candidate_value)

                def prepare_candidate(_diagnostic, union_sha, expected_records):
                    self.assertEqual(expected_records, "b" * 64)
                    candidate_sha = Launch._publish_or_validate_bytes(
                        paths["candidate"], candidate_raw,
                        "synthetic candidate",
                    )
                    stage = {
                        "schema": Launch.CANDIDATE_STAGE_SCHEMA,
                        "union_stage_sha256": union_sha,
                        "candidate_path": str(paths["candidate"]),
                        "candidate_bytes": len(candidate_raw),
                        "candidate_sha256": candidate_sha,
                        "records_sha256": candidate_value["records_sha256"],
                    }
                    stage_sha = Launch._publish_or_validate_json(
                        paths["candidate_stage"], stage,
                        "synthetic candidate stage",
                    )
                    maybe_interrupt("candidate")
                    return stage_sha, stage, candidate_raw, candidate_value

                def prepare_attestation(candidate_stage_sha, raw):
                    attestation_sha = Launch._publish_or_validate_bytes(
                        paths["attestation"], raw, "synthetic attestation"
                    )
                    stage = {
                        "schema": Launch.ATTESTATION_STAGE_SCHEMA,
                        "candidate_stage_sha256": candidate_stage_sha,
                        "attestation_path": str(paths["attestation"]),
                        "attestation_bytes": len(raw),
                        "attestation_sha256": attestation_sha,
                    }
                    stage_sha = Launch._publish_or_validate_json(
                        paths["attestation_stage"], stage,
                        "synthetic attestation stage",
                    )
                    maybe_interrupt("attestation")
                    return stage_sha, stage, attestation_sha

                def publish_json(path, value, label):
                    digest = real_publish_json(path, value, label)
                    if path == paths["receipt"]:
                        maybe_interrupt("receipt")
                    return digest

                stage_paths = (
                    paths["plan"], paths["union_root"], paths["union"],
                    paths["candidate_stage"], paths["attestation_stage"],
                )
                with (
                    mock.patch.multiple(
                        Launch,
                        SEAL_PLAN=paths["plan"],
                        UNION_ROOT_STAGE=paths["union_root"],
                        UNION_STAGE=paths["union"],
                        CANDIDATE=paths["candidate"],
                        CANDIDATE_STAGE=paths["candidate_stage"],
                        ATTESTATION=paths["attestation"],
                        ATTESTATION_STAGE=paths["attestation_stage"],
                        EXECUTION_RECEIPT=paths["receipt"],
                        UNION_DIR=paths["union_dir"],
                        SEAL_STAGE_ARTIFACTS=stage_paths,
                    ),
                    mock.patch.object(Launch, "_seal_context", return_value=context),
                    mock.patch.object(
                        Launch, "_prepare_union", side_effect=prepare_union
                    ),
                    mock.patch.object(
                        Launch, "_prepare_candidate", side_effect=prepare_candidate
                    ),
                    mock.patch.object(
                        Launch, "_attestation_stage", side_effect=prepare_attestation
                    ),
                    mock.patch.object(
                        Launch, "_execution_receipt",
                        return_value={"schema": "synthetic-receipt"},
                    ),
                    mock.patch.object(Launch, "_final_tree_rehash"),
                    mock.patch.object(
                        Launch, "_publish_or_validate_json",
                        side_effect=publish_json,
                    ),
                    self.assertRaisesRegex(RuntimeError, "synthetic"),
                ):
                    Launch._run_seal(recovery=False)
                self.assertTrue(interrupted[boundary])

                # Recovery reuses every already-published byte and creates
                # only the missing suffix of the deterministic hash chain.
                with (
                    mock.patch.multiple(
                        Launch,
                        SEAL_PLAN=paths["plan"],
                        UNION_ROOT_STAGE=paths["union_root"],
                        UNION_STAGE=paths["union"],
                        CANDIDATE=paths["candidate"],
                        CANDIDATE_STAGE=paths["candidate_stage"],
                        ATTESTATION=paths["attestation"],
                        ATTESTATION_STAGE=paths["attestation_stage"],
                        EXECUTION_RECEIPT=paths["receipt"],
                        UNION_DIR=paths["union_dir"],
                        SEAL_STAGE_ARTIFACTS=stage_paths,
                    ),
                    mock.patch.object(Launch, "_seal_context", return_value=context),
                    mock.patch.object(
                        Launch, "_prepare_union", side_effect=prepare_union
                    ),
                    mock.patch.object(
                        Launch, "_prepare_candidate", side_effect=prepare_candidate
                    ),
                    mock.patch.object(
                        Launch, "_attestation_stage", side_effect=prepare_attestation
                    ),
                    mock.patch.object(
                        Launch, "_execution_receipt",
                        return_value={"schema": "synthetic-receipt"},
                    ),
                    mock.patch.object(Launch, "_final_tree_rehash"),
                ):
                    with redirect_stdout(io.StringIO()):
                        Launch.recover_seal()
                self.assertEqual(
                    paths["receipt"].read_bytes(),
                    Launch._canonical_json({"schema": "synthetic-receipt"}),
                )

    def test_recover_seal_requires_state_and_uses_recovery_mode(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-recover-seal-") as tmp:
            root = Path(tmp)
            stage = root / "stage.json"
            absent = [root / "absent-{}".format(i) for i in range(4)]
            with (
                mock.patch.multiple(
                    Launch,
                    EXECUTION_RECEIPT=absent[0], UNION_DIR=absent[1],
                    CANDIDATE=absent[2], ATTESTATION=absent[3],
                    SEAL_STAGE_ARTIFACTS=(stage,),
                ),
                self.assertRaisesRegex(
                    Launch.LaunchAuditError, "no interrupted seal state"
                ),
            ):
                Launch.recover_seal()
            stage.write_bytes(b"partial\n")
            with (
                mock.patch.multiple(
                    Launch,
                    EXECUTION_RECEIPT=absent[0], UNION_DIR=absent[1],
                    CANDIDATE=absent[2], ATTESTATION=absent[3],
                    SEAL_STAGE_ARTIFACTS=(stage,),
                ),
                mock.patch.object(Launch, "_run_seal") as run,
            ):
                Launch.recover_seal()
            run.assert_called_once_with(recovery=True)

    def test_invalid_completed_shard_aborts_instead_of_joining_repair(self):
        diagnostic = {
            "v5_launch_receipt": {
                "code_manifest_sha256": "a" * 64,
                "source_inventory_sha256": "b" * 64,
                "job_id": "42",
            },
            "reusable_v5_shard_indices": [0],
            "repair_v5_shard_indices": [1],
            "v5_output_manifest": {
                "files": [
                    {"path": "shard-0000-of-0820.json", "sha256": "c" * 64},
                    {"path": "environment-0000-of-0820.json", "sha256": "d" * 64},
                    {"path": "slurm-42_0.out", "sha256": "e" * 64},
                ]
            },
        }
        inventory = [{}, {}]
        with (
            mock.patch.object(
                Launch, "_opaque_v5_output_manifest",
                return_value=diagnostic["v5_output_manifest"],
            ),
            mock.patch.object(
                Launch.V5Source, "validate_code_manifest", return_value={}
            ),
            mock.patch.object(
                Launch.V5Source, "load_inventory_manifest",
                return_value=("b" * 64, inventory),
            ),
            mock.patch.object(
                Launch.V5Source, "_load_shard",
                side_effect=Launch.V5Source.SourceAuditError("bad shard"),
            ),
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "invalid reusable triplet"
            ),
        ):
            Launch._validate_v5_reusable_triplets(diagnostic)
        self.assertEqual(diagnostic["repair_v5_shard_indices"], [1])

    def test_slurm_template_has_only_runtime_identity_tokens(self):
        raw = Launch._slurm_template()
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(), Launch.NORMALIZED_SLURM_SHA256
        )
        self.assertEqual(raw.count(Launch.TIMEOUT_PLACEHOLDER), 1)
        self.assertEqual(raw.count(Launch.MANIFEST_PLACEHOLDER), 1)
        rendered = Launch._render_slurm("a" * 64, 115200)
        self.assertNotIn(Launch.TIMEOUT_PLACEHOLDER, rendered)
        self.assertNotIn(Launch.MANIFEST_PLACEHOLDER, rendered)
        self.assertIn(b'--task-timeout "${task_timeout_seconds}"', rendered)

    def test_slurm_template_rejects_any_whole_program_change(self):
        with tempfile.TemporaryDirectory(prefix="source-v6-slurm-") as tmp:
            root = Path(tmp)
            template = root / "template.slurm"
            template.write_bytes(
                Path(Launch.SLURM_TEMPLATE).read_bytes() + b"# mutation\n"
            )
            with (
                mock.patch.multiple(Launch, REPO=root, SLURM_TEMPLATE=template),
                self.assertRaisesRegex(
                    Launch.LaunchAuditError, "template contract changed"
                ),
            ):
                Launch._slurm_template()

    def test_seal_has_no_resource_ceiling_exclusion_path(self):
        source = Path(Launch.__file__).read_text(encoding="utf-8")
        self.assertNotIn("unsupported-resource", source)
        self.assertNotIn("resource-ceiling-exclusion", source)
        self.assertIn("V6 repair array is not entirely successful", source)
        self.assertIn('"recover-seal"', source)
        self.assertIn('"slurm_log_sha256"', source)


if __name__ == "__main__":
    unittest.main()
