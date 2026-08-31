#!/usr/bin/env python3
"""Focused tests for outcome-blind shadow auditing and recovery."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audit_pdb_terminal_incidence_shadow as Audit
import pdb_terminal_incidence_shadow_protocol as P
import recover_pdb_terminal_incidence_shadow as Recovery


class TerminalIncidenceShadowRecoveryTest(unittest.TestCase):
    @staticmethod
    def launch_receipt() -> dict:
        digest = "a" * 64
        attestation = {
            "revision": P.PLANNER_REVISION,
            "build_options": list(P.BUILD_OPTIONS),
            "downward_sha256": P.PLANNER_BINARY_SHA256,
            "preprocess_sha256": P.PREPROCESS_BINARY_SHA256,
            "tree_manifest_sha256": P.PLANNER_TREE_MANIFEST_SHA256,
        }
        return {
            "schema": Audit.LAUNCH_RECEIPT_SCHEMA,
            "job_id": "1234",
            "job_name": Audit.EXPECTED_JOB_NAME,
            "partition": "fat",
            "qos": "normal",
            "account": P.ACCOUNT,
            "slurm_array": "1-767",
            "array_throttle": 0,
            "array_tasks": 767,
            "runs_per_array_task": 3,
            "cells": 2300,
            "time_limit": "00:20:00",
            "memory_per_cpu": "9G",
            "cpus_per_task": 1,
            "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
            "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
            "protocol_sha256": P.PROTOCOL_SHA256,
            "planner_revision": P.PLANNER_REVISION,
            "benchmark_revision": P.BENCHMARK_REVISION,
            "planner_cache_name": P.PLANNER_CACHE_NAME,
            "translator_source_sha256": P.TRANSLATOR_SOURCE_SHA256,
            "cost_attestation_sha256": P.COST_ATTESTATION_SHA256,
            "cost_attestation_records_sha256": (
                P.COST_ATTESTATION_RECORDS_SHA256
            ),
            "source_audit_job_id": P.SOURCE_AUDIT_JOB_ID,
            "source_audit_launch_receipt_sha256": (
                P.SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256
            ),
            "source_audit_execution_receipt_sha256": (
                P.SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256
            ),
            "source_audit_slurm_sha256": P.SOURCE_AUDIT_SLURM_SHA256,
            "revision_cache_attestation": attestation,
            "experiment_code_path": "code-pinned",
            "experiment_code_attestation": attestation,
            "job_file_sha256": digest,
            "launch_intent_sha256": digest,
            "build_receipt_sha256": digest,
            "generated_run_input_tree_sha256": digest,
            "static_experiment_properties_sha256": digest,
            "generated_run_files": 2300,
            "generated_static_property_files": 2300,
            "materialized_pddl_inputs": True,
            "generated_pddl_input_files": 4600,
            "source_file_sha256": {"runner.py": digest},
            "lab_version": P.REQUIRED_LAB_VERSION,
            "python_version": "3.12.13",
            "python_executable": str(Path(sys.executable).resolve()),
            "python_executable_sha256": digest,
            "python_environment_sha256": digest,
            "python_distributions": {"lab": P.REQUIRED_LAB_VERSION},
            "python_requirements_sha256": digest,
        }

    def test_frozen_array_partition_covers_each_cell_once(self):
        self.assertEqual(P.CELL_COUNT, 2300)
        self.assertEqual(Audit.EXPECTED_CELLS, 2300)
        self.assertEqual(Audit.RUNS_PER_ARRAY_TASK, 3)
        self.assertEqual(Audit.EXPECTED_ARRAY_TASKS, 767)
        cells = [
            run
            for task in range(1, Audit.EXPECTED_ARRAY_TASKS + 1)
            for run in Recovery._task_cells(task)
        ]
        self.assertEqual(cells, list(range(1, 2301)))
        self.assertEqual(list(Recovery._task_cells(767)), [2299, 2300])
        self.assertEqual(
            Audit._run_dir(2300).parent.name,
            "runs-02201-02300",
        )

    def test_launch_receipt_is_byte_pinned_and_semantically_exact(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "launch.json"
            intent_path = Path(tmp) / "launch-intent-v1.json"
            build_path = Path(tmp) / "build-receipt-v1.json"
            launch = self.launch_receipt()
            shared = (
                "cells",
                "planner_revision",
                "cohort_manifest_sha256",
                "option_matrix_sha256",
                "protocol_sha256",
                "lab_version",
                "python_version",
                "python_executable",
                "python_executable_sha256",
                "python_environment_sha256",
                "python_distributions",
                "python_requirements_sha256",
                "revision_cache_attestation",
                "experiment_code_path",
                "experiment_code_attestation",
                "static_experiment_properties_sha256",
                "generated_run_input_tree_sha256",
                "generated_run_files",
                "generated_static_property_files",
                "materialized_pddl_inputs",
                "generated_pddl_input_files",
                "source_file_sha256",
            )
            build = {
                "schema": "{}/build".format(Audit.LAUNCH_RECEIPT_SCHEMA),
                "recorded_utc": "2026-08-31T20:00:00+00:00",
                **{field: launch[field] for field in shared},
            }
            build_raw = json.dumps(
                build, sort_keys=True, separators=(",", ":")
            ).encode("ascii") + b"\n"
            build_path.write_bytes(build_raw)
            launch["build_receipt_sha256"] = hashlib.sha256(
                build_raw
            ).hexdigest()
            prepared = {
                key: value for key, value in launch.items()
                if key not in {"job_id", "launch_intent_sha256"}
            }
            intent = {
                "schema": "{}/intent".format(Audit.LAUNCH_RECEIPT_SCHEMA),
                "prepared_receipt_without_job_id": prepared,
            }
            intent_raw = json.dumps(
                intent, sort_keys=True, separators=(",", ":")
            ).encode("ascii") + b"\n"
            intent_path.write_bytes(intent_raw)
            launch["launch_intent_sha256"] = hashlib.sha256(
                intent_raw
            ).hexdigest()
            raw = json.dumps(
                launch,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii") + b"\n"
            path.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            cached = mock.Mock()
            cached.name = P.PLANNER_CACHE_NAME
            cached.attest.return_value = launch["revision_cache_attestation"]
            cached.attest_path.return_value = launch[
                "experiment_code_attestation"
            ]
            with (
                mock.patch.object(Audit, "LAUNCH_RECEIPT", path),
                mock.patch.object(Audit, "LAUNCH_INTENT", intent_path),
                mock.patch.object(Audit, "BUILD_RECEIPT", build_path),
                mock.patch.object(Audit, "LAUNCH_RECEIPT_SHA256", digest),
                mock.patch.object(Audit, "_validate_live_sources"),
                mock.patch.object(
                    Audit, "_validate_static_experiment_properties"
                ),
                mock.patch(
                    "exp_pdb_profile_certificate_holdout."
                    "_environment_attestation",
                    return_value={
                        "python_executable_sha256": launch[
                            "python_executable_sha256"
                        ],
                        "python_environment_sha256": launch[
                            "python_environment_sha256"
                        ],
                        "python_distributions": launch[
                            "python_distributions"
                        ],
                        "python_requirements_sha256": launch[
                            "python_requirements_sha256"
                        ],
                    },
                ),
                mock.patch.object(
                    Audit.JJ,
                    "JjCachedFastDownwardRevision",
                    return_value=cached,
                ),
            ):
                self.assertEqual(Audit.load_launch_receipt()["job_id"], "1234")
                path.write_bytes(raw + b"\n")
                with self.assertRaisesRegex(
                    Audit.ExecutionAuditError, "bytes changed"
                ):
                    Audit.load_launch_receipt()

    def test_unpinned_launch_receipt_fails_closed(self):
        with self.assertRaisesRegex(Audit.ExecutionAuditError, "not pinned"):
            Audit.load_launch_receipt()

    def test_scheduler_audit_requires_exact_fat_task_set(self):
        output = (
            "7_2|702|RUNNING|0:0|n2|4|fat\n"
            "7_1|701|COMPLETED|0:0|n1|3|fat\n"
        )
        with mock.patch.object(
            Audit.subprocess, "check_output", return_value=output
        ):
            rows = Audit.scheduler_rows("7", {1, 2})
        self.assertEqual([row["array_task"] for row in rows], [1, 2])
        self.assertEqual([row["state"] for row in rows], ["COMPLETED", "RUNNING"])

        with mock.patch.object(
            Audit.subprocess,
            "check_output",
            return_value=output.replace("|fat\n", "|thin\n", 1),
        ):
            with self.assertRaisesRegex(Audit.ExecutionAuditError, "non-fat"):
                Audit.scheduler_rows("7", {1, 2})

    def test_cell_audit_reads_only_terminal_driver_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shard = root / "runs-00001-00100"
            for run_id in (1, 2):
                (shard / "{:05d}".format(run_id)).mkdir(parents=True)
            terminal = (
                "2026-08-31 20:00:00,000 "
                "INFO     planner exit code: 0"
            )
            (shard / "00001" / "driver.log").write_text(
                "arbitrary outcome text\n{}\n".format(terminal),
                encoding="utf-8",
            )
            (shard / "00002" / "driver.log").write_text(
                "{}\ntrailing partial write\n".format(terminal),
                encoding="utf-8",
            )
            with (
                mock.patch.object(Audit, "EXPERIMENT_PATH", root),
                mock.patch.object(Audit, "EXPECTED_CELLS", 2),
            ):
                counts, incomplete = Audit.cell_completeness()
            self.assertEqual(counts, {"complete": 1, "interrupted": 1})
            self.assertEqual(incomplete, [2])

    def test_source_job_hash_is_checked_directly(self):
        launch = self.launch_receipt()
        with tempfile.TemporaryDirectory() as tmp:
            grid = Path(tmp)
            source = grid / Audit.EXPECTED_JOB_NAME
            source.write_bytes(b"frozen job\n")
            launch["job_file_sha256"] = hashlib.sha256(
                source.read_bytes()
            ).hexdigest()
            with mock.patch.object(Audit, "GRID_DIR", grid):
                self.assertEqual(Recovery._verify_source_job(launch), source)
                source.write_bytes(b"changed job\n")
                with self.assertRaisesRegex(Recovery.RecoveryError, "changed"):
                    Recovery._verify_source_job(launch)

    def test_failed_task_is_recovered_even_if_its_cells_finished(self):
        launch = self.launch_receipt()
        scheduler = [
            {"array_task": 1, "state": "TIMEOUT"},
            {"array_task": 2, "state": "COMPLETED"},
        ]
        status = {"scheduler_terminal": True, "incomplete_cells": []}
        with (
            mock.patch.object(
                Audit,
                "make_status",
                return_value=(launch, scheduler, [], status),
            ),
            mock.patch.object(Audit, "EXPECTED_ARRAY_TASKS", 2),
            mock.patch.object(Audit, "EXPECTED_CELLS", 6),
        ):
            _, tasks, cells = Recovery._recovery_plan()
        self.assertEqual(tasks, [1])
        self.assertEqual(cells, [])

    def test_audit_rejects_unresolved_recovery_intent(self):
        launch = self.launch_receipt()
        with tempfile.TemporaryDirectory() as tmp:
            artifact = Path(tmp) / "launch-receipt-v1.json"
            wave_dir = artifact.parent / "recovery" / "wave-0001"
            wave_dir.mkdir(parents=True)
            (wave_dir / "launch-intent.json").write_text(
                "{}\n", encoding="ascii"
            )
            with mock.patch.object(Audit, "LAUNCH_RECEIPT", artifact):
                with self.assertRaisesRegex(
                    Audit.ExecutionAuditError, "unresolved launch intent"
                ):
                    Audit.recovery_executions(launch)

    def test_recovery_defaults_to_preview_without_mutation(self):
        launch = self.launch_receipt()
        source = Path("/tmp/frozen-shadow-job")
        output = io.StringIO()
        with (
            mock.patch.object(
                Recovery, "_recovery_plan", return_value=(launch, [2], [4, 5])
            ),
            mock.patch.object(
                Recovery, "_verify_source_job", return_value=source
            ) as verify,
            mock.patch.object(Recovery, "_next_wave") as next_wave,
            mock.patch.object(Recovery, "_archive_interrupted") as archive,
            mock.patch.object(Recovery.subprocess, "check_output") as submit,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(Recovery.main([]), 0)
        verify.assert_called_once_with(launch)
        next_wave.assert_not_called()
        archive.assert_not_called()
        submit.assert_not_called()
        preview = json.loads(output.getvalue())
        self.assertEqual(preview["mode"], "preview")
        self.assertEqual(preview["array_spec"], "2")
        self.assertEqual(preview["array_throttle"], 0)

    def test_submit_verifies_source_before_creating_or_archiving(self):
        launch = self.launch_receipt()
        order = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source-job"
            source.write_bytes(b"job")
            wave_dir = root / "recovery" / "wave-0001"

            def verify(_launch):
                order.append("verify")
                self.assertFalse(wave_dir.exists())
                return source

            def next_wave(_root):
                order.append("next-wave")
                return 1, wave_dir

            def plan(cells):
                order.append("plan")
                self.assertEqual(cells, [4, 5])
                return []

            def archive(items, path):
                order.append("archive")
                self.assertTrue(path.is_dir())
                self.assertEqual(items, [])
                self.assertTrue((path / "launch-intent.json").is_file())
                self.assertFalse((path / "launch-receipt.json").exists())
                return []

            def submit(command, **_kwargs):
                order.append("submit")
                self.assertIn("--array=2", command)
                array_option = next(
                    option for option in command if option.startswith("--array=")
                )
                self.assertNotIn("%", array_option)
                self.assertIn("--partition=fat", command)
                self.assertIn("--qos=normal", command)
                return "9876\n"

            with (
                mock.patch.object(
                    Recovery,
                    "_recovery_plan",
                    return_value=(launch, [2], [4, 5]),
                ),
                mock.patch.object(Recovery, "_verify_source_job", side_effect=verify),
                mock.patch.object(Recovery, "_next_wave", side_effect=next_wave),
                mock.patch.object(Recovery, "_archive_plan", side_effect=plan),
                mock.patch.object(
                    Recovery, "_archive_interrupted", side_effect=archive
                ),
                mock.patch.object(
                    Recovery.subprocess, "check_output", side_effect=submit
                ),
                mock.patch.object(
                    Audit, "LAUNCH_RECEIPT", root / "launch-receipt-v1.json"
                ),
                mock.patch.object(Audit, "GRID_DIR", root),
                mock.patch.object(Audit, "LAUNCH_RECEIPT_SHA256", "b" * 64),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(Recovery.main(["--submit"]), 0)
            self.assertEqual(
                order, ["verify", "next-wave", "plan", "archive", "submit"]
            )
            receipt = json.loads(
                (wave_dir / "launch-receipt.json").read_text(encoding="ascii")
            )
            intent_raw = (wave_dir / "launch-intent.json").read_bytes()
            self.assertEqual(receipt["job_id"], "9876")
            self.assertEqual(
                receipt["launch_intent_sha256"],
                hashlib.sha256(intent_raw).hexdigest(),
            )
            self.assertEqual(receipt["runs_per_array_task"], 3)
            self.assertEqual(receipt["cells"], 2300)
            self.assertEqual(receipt["array_throttle"], 0)


if __name__ == "__main__":
    unittest.main()
