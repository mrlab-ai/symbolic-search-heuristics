#!/usr/bin/env python3
"""Focused tests for the terminal-incidence source-audit v3 seal."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_pdb_terminal_incidence_sources as Source
import launch_pdb_terminal_incidence_source_audit as Launch


class SourceAuditLaunchTest(unittest.TestCase):
    def test_v3_paths_and_environment_isolation_are_explicit(self):
        self.assertTrue(Launch.OUTPUT_DIR.name.endswith("_v3"))
        self.assertIn("_v3_candidate", Launch.CANDIDATE.name)
        self.assertTrue(Launch.INTENT.name.endswith("-v3.json"))
        self.assertTrue(Launch.LAUNCH_RECEIPT.name.endswith("-v3.json"))
        self.assertTrue(Launch.EXECUTION_RECEIPT.name.endswith("-v3.json"))
        self.assertTrue(Launch.LAUNCH_SCHEMA.endswith("/v3"))
        self.assertTrue(Launch.EXECUTION_SCHEMA.endswith("/v3"))
        self.assertEqual(
            Launch._submit_command()[:3],
            ["sbatch", "--parsable", "--export=NONE"],
        )
        script = Launch.SLURM_SCRIPT.read_text(encoding="ascii")
        for line in (
            "#SBATCH --export=NONE",
            "unset PYTHONPATH PYTHONHOME VIRTUAL_ENV",
            'export PYTHONNOUSERSITE="1"',
            'export PATH="/usr/bin:/bin"',
            'sha256sum_executable="/usr/bin/sha256sum"',
            'exec "${python_executable}" \\',
        ):
            self.assertEqual(script.splitlines().count(line), 1)

    def test_scan_rejects_an_inherited_pythonpath(self):
        with mock.patch.dict(os.environ, {"PYTHONPATH": "/uncontrolled"}):
            with self.assertRaisesRegex(
                Source.SourceAuditError, "environment is not clean"
            ):
                Source.validate_execution_environment()

    def test_source_audit_launch_requires_a_clean_committed_tree(self):
        with mock.patch.object(
            Launch.subprocess,
            "check_output",
            side_effect=("M experiments/x.py\n", "a" * 40 + "\n"),
        ):
            with self.assertRaisesRegex(
                Launch.LaunchAuditError, "clean committed working copy"
            ):
                Launch._clean_repository_commit()
        with mock.patch.object(
            Launch.subprocess,
            "check_output",
            side_effect=("", "a" * 40 + "\n"),
        ):
            self.assertEqual(Launch._clean_repository_commit(), "a" * 40)

    def test_slurm_preflight_enforces_the_v3_environment_contract(self):
        python_resolved = Launch.PYTHON_COMMAND.resolve(strict=True)
        code = {
            "python_executable": str(python_resolved),
            "python_executable_sha256": Launch._sha256(python_resolved),
        }
        with mock.patch.object(
            Launch.Source, "validate_code_manifest", return_value=code
        ):
            slurm_sha, manifest_sha, actual_code = Launch._slurm_preflight()
        self.assertEqual(slurm_sha, Launch._sha256(Launch.SLURM_SCRIPT))
        self.assertRegex(manifest_sha, r"^[0-9a-f]{64}$")
        self.assertIs(actual_code, code)

    def test_seal_rehashes_and_rejects_a_changed_output_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate.json"
            attestation = root / "attestation.json"
            execution_receipt = root / "execution.json"
            attestation.write_text("{}\n", encoding="ascii")

            def assemble(argv):
                output = Path(argv[argv.index("--output") + 1])
                output.write_bytes(attestation.read_bytes())

            launch_receipt = {
                "job_id": "123",
                "code_manifest_sha256": "a" * 64,
                "execution_environment": {"submission_export": "NONE"},
            }
            rows = [
                {"state": "COMPLETED", "exit_code": "0:0"}
                for _ in range(Launch.ARRAY_TASKS)
            ]
            with (
                mock.patch.object(Launch, "CANDIDATE", candidate),
                mock.patch.object(
                    Launch, "EXECUTION_RECEIPT", execution_receipt
                ),
                mock.patch.object(
                    Launch.P, "COST_ATTESTATION_PATH", attestation
                ),
                mock.patch.object(
                    Launch, "status", return_value=("b" * 64, launch_receipt, rows)
                ),
                mock.patch.object(
                    Launch,
                    "_output_tree",
                    side_effect=(("c" * 64, 92), ("d" * 64, 92)),
                ) as output_tree,
                mock.patch.object(Launch.Source, "main", side_effect=assemble),
            ):
                with self.assertRaisesRegex(
                    Launch.LaunchAuditError, "changed while assembling"
                ):
                    Launch.seal()
            self.assertEqual(output_tree.call_count, 2)
            self.assertFalse(execution_receipt.exists())

    def test_execution_receipt_binds_environment_and_stable_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate.json"
            attestation = root / "attestation.json"
            execution_receipt = root / "execution.json"
            value = {"counts": {"tasks": 460}, "records_sha256": "e" * 64}
            raw = json.dumps(
                value, sort_keys=True, separators=(",", ":")
            ).encode("ascii") + b"\n"
            attestation.write_bytes(raw)

            def assemble(argv):
                output = Path(argv[argv.index("--output") + 1])
                output.write_bytes(raw)

            environment = {
                "submission_export": "NONE",
                "slurm_export": "NONE",
                "path": "/usr/bin:/bin",
            }
            launch_receipt = {
                "job_id": "123",
                "code_manifest_sha256": "a" * 64,
                "execution_environment": environment,
            }
            rows = [
                {"state": "COMPLETED", "exit_code": "0:0"}
                for _ in range(Launch.ARRAY_TASKS)
            ]
            with (
                mock.patch.object(Launch, "CANDIDATE", candidate),
                mock.patch.object(
                    Launch, "EXECUTION_RECEIPT", execution_receipt
                ),
                mock.patch.object(
                    Launch.P, "COST_ATTESTATION_PATH", attestation
                ),
                mock.patch.object(
                    Launch, "status", return_value=("b" * 64, launch_receipt, rows)
                ),
                mock.patch.object(
                    Launch, "_output_tree", return_value=("c" * 64, 92)
                ) as output_tree,
                mock.patch.object(Launch.Source, "main", side_effect=assemble),
            ):
                Launch.seal()
            self.assertEqual(output_tree.call_count, 2)
            receipt = json.loads(execution_receipt.read_text(encoding="ascii"))
            self.assertEqual(receipt["execution_environment"], environment)
            self.assertEqual(receipt["output_tree_sha256"], "c" * 64)
            self.assertEqual(receipt["output_tree_files"], 92)


if __name__ == "__main__":
    unittest.main()
