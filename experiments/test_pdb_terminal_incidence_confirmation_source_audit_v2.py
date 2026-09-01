#!/usr/bin/env python3
"""Focused adversarial tests for independent source-audit campaign v2."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources as V1Source
import launch_pdb_terminal_incidence_confirmation_source_audit as V1Launch
import recover_pdb_terminal_incidence_confirmation_source_audit as V1Recovery
import audit_pdb_terminal_incidence_confirmation_sources_v2 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v2 as Launch
import recover_pdb_terminal_incidence_confirmation_source_audit_v2 as Recovery
import test_pdb_terminal_incidence_confirmation_source_audit as V1Tests


V1_FROZEN_SHA256 = {
    "experiments/artifacts/pdb-terminal-incidence-confirmation/"
    "source-audit-launch-intent-v1.json": (
        "fde4af4b6d5834eb05d1f4cd92a86140b2f7b802a516f748faad0b35a94ee80a"
    ),
    "experiments/artifacts/pdb-terminal-incidence-confirmation/"
    "source-audit-launch-receipt-v1.json": (
        "3c7b830c181faa21a8f95c648dd15103dfdd6cf69111b07cc7eb01aa1b2817e2"
    ),
    "experiments/audit_pdb_terminal_incidence_confirmation_sources.py": (
        "8f20228e6d4df2c2486e720be35ad5d9040224981e5b3161e0fa130efd5803e5"
    ),
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit.py": (
        "55c96558f03356612b96375a24628856c3f5f4482332b1c1b3113265eb1874b9"
    ),
    "experiments/pdb_terminal_incidence_confirmation_inventory.py": (
        "3e68099771bae7e0424889d0e3aa7e0f732cc5006f7c92491a8135daa9093377"
    ),
    "experiments/pdb_terminal_incidence_confirmation_source_audit_code.sha256": (
        "281aab0344095d7d81f74349916d616bb3cee730e5be095822ed37574ea258a3"
    ),
    "experiments/pdb_terminal_incidence_confirmation_source_scan.slurm": (
        "82be051851dca4951ec5df0f43b8938ce9bd15a25a65bf2660cfc1eedaac5557"
    ),
    "experiments/pdb_terminal_incidence_shadow_cost_attestation.json": (
        "bf2c42860fad91c56620c90a41657ab472f4d58acd184a7580c7b5994aa72d04"
    ),
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit.py": (
        "38d954140dff985c37b87b79b6ad07f42d260f171ec3c4d11ef8354ff664fc71"
    ),
    "experiments/requirements-pdb-terminal-incidence-shadow.txt": (
        "9176e14c79ca81d624fd5eca3c6eb79b799ecb8f08b39301c7c250b97d526422"
    ),
    "experiments/suite_wbh_operator_costs.json": (
        "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168"
    ),
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _row(index: int, state: str, exit_code: str) -> dict:
    return {
        "array_task": index,
        "state": state,
        "exit_code": exit_code,
        "elapsed": "00:20:00",
        "partition": "fat",
    }


class ConfirmationSourceAuditV2Test(unittest.TestCase):
    def test_v1_frozen_launch_provenance_is_byte_identical(self):
        self.assertEqual(
            {
                relative: _sha256(REPO / relative)
                for relative in V1_FROZEN_SHA256
            },
            V1_FROZEN_SHA256,
        )
        self.assertEqual(V1Launch.MEMORY_PER_CPU if hasattr(
            V1Launch, "MEMORY_PER_CPU"
        ) else "26G", "26G")
        self.assertNotEqual(Source.DEFAULT_SHARDS, V1Source.DEFAULT_SHARDS)
        self.assertNotEqual(Launch.OUTPUT_DIR, V1Launch.OUTPUT_DIR)
        self.assertNotEqual(Recovery.OUTPUT_DIR, V1Recovery.OUTPUT_DIR)

    def test_v2_is_full_unthrottled_256g_campaign_on_separate_paths(self):
        lines = Launch.SLURM_SCRIPT.read_text(encoding="ascii").splitlines()
        for line in (
            "#SBATCH --job-name=confirmation-source-audit-v2",
            "#SBATCH --partition=fat",
            "#SBATCH --qos=normal",
            "#SBATCH --array=0-819",
            "#SBATCH --cpus-per-task=1",
            "#SBATCH --mem-per-cpu=256G",
            "#SBATCH --time=01:40:00",
            "#SBATCH --export=NONE",
            "    --num-shards 820 \\",
            "    --task-timeout 2700 \\",
        ):
            self.assertEqual(lines.count(line), 1)
        array = next(line for line in lines if line.startswith("#SBATCH --array="))
        self.assertNotIn("%", array)
        self.assertFalse(any("--nice" in line for line in lines))
        self.assertEqual(Launch.MEMORY_PER_CPU, "256G")
        self.assertEqual(Launch.ARRAY_TASKS, 820)
        self.assertEqual(Source.TASKS_PER_SHARD, 2)
        self.assertIn("audit_v2", str(Launch.OUTPUT_DIR))
        self.assertIn("recovery_v2", str(Recovery.OUTPUT_DIR))
        self.assertIn("union_v2", str(Recovery.UNION_DIR))

    def test_v2_execution_environment_requires_per_array_pycache(self):
        environment = {
            "SLURM_ARRAY_JOB_ID": "987",
            "SLURM_ARRAY_TASK_ID": "41",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": (
                "/tmp/symk-confirmation-source-audit-v2-987-41"
            ),
            "PATH": Source.CONTROLLED_PATH,
        }
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(Source.sys, "flags", mock.Mock(no_user_site=1)),
            mock.patch.object(Source.sys, "dont_write_bytecode", True),
        ):
            Source.validate_execution_environment()
            os.environ["PYTHONPYCACHEPREFIX"] = "/tmp/shared-cache"
            with self.assertRaisesRegex(
                Source.SourceAuditError, "execution environment changed"
            ):
                Source.validate_execution_environment()

    def test_v2_inventory_eligibility_and_split_are_identical_to_v1(self):
        inventory = Source.Inventory.load_inventory()
        v1_manifest = V1Source.build_inventory_manifest(inventory)
        v2_manifest = Source.build_inventory_manifest(inventory)
        self.assertEqual(v2_manifest, v1_manifest)
        raw = Source.canonical_json(v2_manifest)
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            Launch.V1_SOURCE_INVENTORY_SHA256,
        )
        records = V1Tests._supported_inventory_records()
        self.assertEqual(
            Source.split_supported(records),
            V1Source.split_supported(records),
        )

    def test_v1_diagnostic_refuses_active_rows_and_binds_terminal_oom(self):
        active = [
            *[_row(index, "COMPLETED", "0:0") for index in range(819)],
            _row(819, "RUNNING", "0:0"),
        ]
        with (
            mock.patch.object(Launch.Base, "_scheduler_rows", return_value=active),
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "not fully terminal"
            ),
        ):
            Launch._v1_failure_diagnostic()
        terminal = [
            *[_row(index, "COMPLETED", "0:0") for index in range(819)],
            _row(819, "OUT_OF_MEMORY", "0:125"),
        ]
        with mock.patch.object(
            Launch.Base, "_scheduler_rows", return_value=terminal
        ):
            diagnostic = Launch._v1_failure_diagnostic()
        self.assertEqual(len(diagnostic["v1_scheduler_rows"]), 820)
        self.assertEqual(
            diagnostic["v1_scheduler_state_counts"],
            {"COMPLETED": 819, "OUT_OF_MEMORY": 1},
        )
        self.assertEqual(diagnostic["failure_class"], "scheduler-out-of-memory")
        self.assertFalse(
            diagnostic["successful_shard_contents_used_for_v2_design"]
        )
        self.assertFalse(
            diagnostic["source_support_outcomes_used_for_v2_design"]
        )
        self.assertEqual(diagnostic["reused_v1_shards"], 0)

    def test_launch_refuses_nonterminal_v1_before_publishing_v2(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {
                "INTENT": root / "intent.json",
                "LAUNCH_RECEIPT": root / "launch.json",
                "EXECUTION_RECEIPT": root / "execution.json",
                "OUTPUT_DIR": root / "output",
                "CANDIDATE": root / "candidate.json",
                "ATTESTATION": root / "attestation.json",
            }
            with (
                mock.patch.multiple(Launch, **paths),
                mock.patch.object(Launch.Inventory, "load_inventory", return_value=object()),
                mock.patch.object(
                    Launch.Source, "build_inventory_manifest", return_value={}
                ),
                mock.patch.object(Launch, "_fixed_materials", return_value={}),
                mock.patch.object(
                    Launch, "_v1_failure_diagnostic",
                    side_effect=Launch.LaunchAuditError("v1 still active"),
                ),
                mock.patch.object(Launch.Base, "_exclusive_json") as publish,
                mock.patch.object(Launch.subprocess, "check_output") as submit,
                self.assertRaisesRegex(Launch.LaunchAuditError, "still active"),
            ):
                Launch.launch()
            publish.assert_not_called()
            submit.assert_not_called()
            self.assertFalse(any(path.exists() for path in paths.values()))

    def test_scoped_commit_attestation_ignores_unrelated_work(self):
        tracked = "\n".join(Launch.SCOPED_COMMIT_FILES) + "\n"
        commit = "a" * 40 + "\n"
        with (
            mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}),
            mock.patch.object(
                Launch.subprocess,
                "check_output",
                side_effect=("", tracked, commit),
            ) as command,
        ):
            self.assertEqual(Launch._scoped_repository_commit(), "a" * 40)
        calls = [call.args[0] for call in command.call_args_list]
        self.assertTrue(all(
            call[0] == str(Launch.JJ_COMMAND) for call in calls
        ))
        self.assertIn("--", calls[0])
        self.assertEqual(
            set(calls[0][calls[0].index("--") + 1:]),
            set(Launch.SCOPED_COMMIT_FILES),
        )
        with (
            mock.patch.object(
                Launch.subprocess,
                "check_output",
                side_effect=("A experiments/x-v2.py\n", tracked, commit),
            ),
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "every bound file committed"
            ),
        ):
            Launch._scoped_repository_commit()

    def test_fixed_materials_exposes_pinned_jj_identity(self):
        code = {
            "python_version": "test",
            "python_executable": "/test/python",
            "python_executable_sha256": "1" * 64,
            "python_environment_sha256": "2" * 64,
            "python_distributions": {},
            "python_requirements_sha256": "3" * 64,
        }
        with (
            mock.patch.object(
                Launch, "_slurm_preflight",
                return_value=("4" * 64, "5" * 64, code),
            ),
            mock.patch.object(
                Launch.Base, "_execution_environment", return_value={}
            ),
            mock.patch.dict(os.environ, {"PATH": "/usr/bin:/bin"}),
        ):
            materials = Launch._fixed_materials(
                "6" * 64, repository_commit_id="7" * 40
            )
        self.assertEqual(materials["jj_executable"], str(Launch.JJ_COMMAND))
        self.assertEqual(
            materials["jj_executable_sha256"],
            Launch.JJ_EXECUTABLE_SHA256,
        )
        with (
            mock.patch.object(Launch.Base, "_sha256", return_value="0" * 64),
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "jj executable bytes changed"
            ),
        ):
            Launch._jj_executable_identity()

    def test_recovery_uses_only_v2_outputs_and_identical_resources(self):
        plan = {
            "recoverable_shards": [2, 7],
            "source_inventory_sha256": "a" * 64,
        }
        command = Recovery._submit_command(plan, "b" * 24)
        self.assertIn("--array=2,7", command)
        self.assertIn("--partition=fat", command)
        self.assertIn("--qos=normal", command)
        self.assertIn("--cpus-per-task=1", command)
        self.assertIn("--mem-per-cpu=256G", command)
        self.assertIn("--time=01:40:00", command)
        self.assertFalse(any("nice" in item for item in command))
        self.assertEqual(command[-3], str(Launch.SLURM_SCRIPT))
        self.assertEqual(command[-1], str(Recovery.OUTPUT_DIR.resolve()))
        self.assertNotIn(str(V1Launch.OUTPUT_DIR), " ".join(command))
        self.assertIs(Recovery.Base.Launch, Launch)
        self.assertIs(Recovery.Base.Source, Source)

    def test_v2_manifest_and_slurm_preflight_are_exact(self):
        slurm_sha, manifest_sha, _ = Launch._slurm_preflight()
        self.assertEqual(slurm_sha, _sha256(Launch.SLURM_SCRIPT))
        self.assertEqual(
            manifest_sha, _sha256(Source.DEFAULT_CODE_MANIFEST)
        )
        Source.validate_code_manifest(
            Source.DEFAULT_CODE_MANIFEST, manifest_sha
        )


if __name__ == "__main__":
    unittest.main()
