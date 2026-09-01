#!/usr/bin/env python3
"""Regression tests for the campaign-v3 source-audit resource amendment."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audit_pdb_terminal_incidence_confirmation_sources_v3 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v3 as Launch
import recover_pdb_terminal_incidence_confirmation_source_audit_v3 as Recovery


class SourceAuditV3Test(unittest.TestCase):
    def test_resource_amendment_is_exact(self) -> None:
        self.assertEqual(Source.TASK_TIMEOUT_SECONDS, 7200)
        self.assertEqual(Launch.MEMORY_PER_CPU, "512G")
        self.assertEqual(Launch.TIME_LIMIT, "04:10:00")
        self.assertEqual(Launch.ARRAY_TASKS, 820)
        self.assertIn("source_audit_v3", str(Source.DEFAULT_SHARDS))
        self.assertIn(
            "experiments/"
            "pdb_terminal_incidence_confirmation_source_audit_v3_protocol.md",
            Source.CODE_MANIFEST_FILES,
        )
        self.assertIn(
            "experiments/"
            "test_pdb_terminal_incidence_confirmation_source_audit_v3.py",
            Source.CODE_MANIFEST_FILES,
        )
        expected_scoped = {
            *Source.CODE_MANIFEST_FILES,
            Launch.SLURM_SCRIPT.relative_to(Launch.REPO).as_posix(),
            Launch.CODE_MANIFEST.relative_to(Launch.REPO).as_posix(),
        }
        self.assertEqual(set(Launch.SCOPED_COMMIT_FILES), expected_scoped)
        self.assertEqual(
            len(Launch.SCOPED_COMMIT_FILES), len(expected_scoped)
        )

    def test_submit_command_and_environment_are_closed(self) -> None:
        command = Launch._submit_command(
            Launch.V2_SOURCE_INVENTORY_SHA256,
            Launch.OUTPUT_DIR,
            "a" * 24,
        )
        self.assertEqual(command[0], "/usr/bin/sbatch")
        for option in (
            "--parsable", "--export=NONE", "--account=" + Launch.ACCOUNT,
            "--partition=fat", "--qos=normal", "--array=0-819",
            "--nodes=1", "--ntasks=1", "--cpus-per-task=1",
            "--mem-per-cpu=512G", "--time=04:10:00", "--nice=0",
            "--no-requeue", "--chdir=" + str(Launch.REPO),
        ):
            self.assertEqual(command.count(option), 1)
        self.assertFalse(any("%" in arg for arg in command if arg.startswith(
            "--array="
        )))
        self.assertEqual(
            Launch.SUBMISSION_ENVIRONMENT,
            {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
        self.assertFalse(any(
            key.startswith(("SBATCH_", "SLURM_"))
            for key in Launch.SUBMISSION_ENVIRONMENT
        ))

    def test_wrong_inventory_hash_is_rejected_before_submission(self) -> None:
        with self.assertRaises(Launch.LaunchAuditError):
            Launch._submit_command("0" * 64, Launch.OUTPUT_DIR, "a" * 24)

    def test_stale_v3_namespace_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix="source-audit-v3-namespace-test-"
        ) as tmp:
            stale = Path(tmp) / "output"
            with mock.patch.object(Launch, "OUTPUT_DIR", stale):
                Launch._assert_launch_namespace_empty()
                stale.mkdir()
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._assert_launch_namespace_empty()

    @staticmethod
    def _successful_rows() -> list[dict]:
        return [
            {
                "array_task": index,
                "state": "COMPLETED",
                "exit_code": "0:0",
                "elapsed": "00:00:01",
                "partition": "fat",
            }
            for index in range(Launch.ARRAY_TASKS)
        ]

    def test_only_original_all_success_rows_are_accepted(self) -> None:
        rows = self._successful_rows()
        Launch._validate_original_success_rows(rows)
        for field, value in (
            ("state", "NODE_FAIL"),
            ("exit_code", "1:0"),
            ("array_task", False),
        ):
            mutated = [dict(row) for row in rows]
            mutated[7][field] = value
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._validate_original_success_rows(mutated)

    def test_recovery_cli_is_disabled(self) -> None:
        for function in (
            Recovery.preview, Recovery.launch, Recovery.recover_launch,
            Recovery.status, Recovery.seal,
        ):
            with self.assertRaises(Recovery.RecoveryError):
                function()
        with self.assertRaises(Recovery.RecoveryError):
            Recovery.main(["preview"])

    def test_launch_receipt_recovery_accepts_blank_child_comments(self) -> None:
        token = "a" * 24
        command = Launch._submit_command(
            Launch.V2_SOURCE_INVENTORY_SHA256, Launch.OUTPUT_DIR, token
        )
        name = "confirmation-source-audit-v3-" + token
        submit_line = " ".join([Path(command[0]).name, *command[1:]])
        payload = (
            "999|other||unterminated '\n"
            "998|other||sbatch --wrap=a|b\n"
        ) + "\n".join(
            "1869998_{i}|{name}||{submit_line}".format(
                i=index, name=name, submit_line=submit_line
            )
            for index in range(Launch.ARRAY_TASKS)
        ) + "\n"
        intent = {
            "submission_token": token,
            "recorded_utc": "2026-09-01T00:00:00+00:00",
            "submit_command": command,
        }
        calls = []

        def fake_check_output(sacct_command, **kwargs):
            calls.append((sacct_command, kwargs))
            return payload

        with mock.patch.object(
            Launch.subprocess, "check_output", side_effect=fake_check_output
        ):
            self.assertEqual(Launch._journal_job_ids(intent), ["1869998"])
        self.assertEqual(calls[0][0][0], "/usr/bin/sacct")
        self.assertIn("--name=" + name, calls[0][0])
        self.assertEqual(
            calls[0][1]["env"], dict(Launch.SUBMISSION_ENVIRONMENT)
        )

    def test_actual_scheduler_resources_are_revalidated(self) -> None:
        rows = self._successful_rows()
        name = "confirmation-source-audit-v3-" + "a" * 24
        payload = "\n".join(
            "1869999_{i}|{account}|fat|normal|1|512G|04:10:00|"
            "COMPLETED|0:0|{name}".format(
                i=index, account=Launch.ACCOUNT, name=name
            )
            for index in range(Launch.ARRAY_TASKS)
        ) + "\n"
        calls = []

        def fake_check_output(command, **kwargs):
            calls.append((command, kwargs))
            return payload

        with mock.patch.object(
            Launch.subprocess, "check_output", side_effect=fake_check_output
        ):
            contract = Launch._scheduler_contract_rows(
                "1869999", {"submission_token": "a" * 24}, rows
            )
        self.assertEqual(len(contract), Launch.ARRAY_TASKS)
        self.assertEqual(calls[0][0][0], "/usr/bin/sacct")
        self.assertEqual(
            calls[0][1]["env"], dict(Launch.SUBMISSION_ENVIRONMENT)
        )

        bad_payload = payload.replace("|512G|", "|511G|", 1)
        with mock.patch.object(
            Launch.subprocess, "check_output", return_value=bad_payload
        ):
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._scheduler_contract_rows(
                    "1869999", {"submission_token": "a" * 24}, rows
                )

    def test_basic_scheduler_query_is_absolute_and_sanitized(self) -> None:
        payload = "\n".join(
            "1869999_{i}|COMPLETED|0:0|00:00:01|fat".format(i=index)
            for index in range(Launch.ARRAY_TASKS)
        ) + "\n"
        calls = []

        def fake_check_output(command, **kwargs):
            calls.append((command, kwargs))
            return payload

        with mock.patch.object(
            Launch.subprocess, "check_output", side_effect=fake_check_output
        ):
            rows = Launch._scheduler_rows("1869999")
        self.assertEqual(len(rows), Launch.ARRAY_TASKS)
        self.assertEqual(calls[0][0][0], "/usr/bin/sacct")
        self.assertEqual(
            calls[0][1]["env"], dict(Launch.SUBMISSION_ENVIRONMENT)
        )

    def test_v2_diagnostic_rejects_nonterminal_scheduler_rows(self) -> None:
        _, receipt = Launch.Base._load_json(
            Launch.V2_LAUNCH_RECEIPT, "v2 test launch receipt"
        )
        rows = self._successful_rows()
        rows[0]["state"] = "RUNNING"
        with (
            mock.patch.object(
                Launch, "_v1_failure_diagnostic",
                return_value=receipt["v1_failure_diagnostic"],
            ),
            mock.patch.object(Launch.Base, "_scheduler_rows", return_value=rows),
        ):
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._v2_failure_diagnostic()

    def test_current_slurm_file_passes_exact_preflight(self) -> None:
        slurm_sha256, manifest_sha256, _ = Launch._slurm_preflight()
        self.assertTrue(Source._is_sha256(slurm_sha256))
        self.assertTrue(Source._is_sha256(manifest_sha256))

    def _reject_mutated_slurm(self, mutate) -> None:
        original_path = Launch.SLURM_SCRIPT
        original = original_path.read_text(encoding="ascii")
        with tempfile.TemporaryDirectory(prefix="source-audit-v3-test-") as tmp:
            candidate = Path(tmp) / "campaign-v3.slurm"
            candidate.write_text(mutate(original), encoding="ascii")
            Launch.SLURM_SCRIPT = candidate
            try:
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._slurm_preflight()
            finally:
                Launch.SLURM_SCRIPT = original_path

    def test_slurm_directive_after_executable_is_rejected(self) -> None:
        def mutate(text: str) -> str:
            directive = "#SBATCH --partition=fat\n"
            return text.replace(directive, "", 1).replace(
                "set -euo pipefail\n",
                "set -euo pipefail\n" + directive,
                1,
            )

        self._reject_mutated_slurm(mutate)

    def test_early_success_exit_is_rejected(self) -> None:
        self._reject_mutated_slurm(
            lambda text: text.replace(
                'exec "${python_executable}" -B \\\n',
                'exit 0\nexec "${python_executable}" -B \\\n',
                1,
            )
        )

    def test_execution_body_change_is_rejected(self) -> None:
        self._reject_mutated_slurm(
            lambda text: text.replace("--task-timeout 7200", "--task-timeout 7199")
        )


if __name__ == "__main__":
    unittest.main()
