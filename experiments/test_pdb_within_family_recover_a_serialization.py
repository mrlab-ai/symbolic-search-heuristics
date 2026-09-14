"""Synthetic tests for the bounded, analysis-only A serialization recovery."""

import contextlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import pdb_within_family_a_analysis as A
import pdb_within_family_cohort as C
import pdb_within_family_recover_a_serialization as R


class RecoveryFixture:
    def __init__(self):
        self.stack = contextlib.ExitStack()

    def __enter__(self):
        self.temporary = self.stack.enter_context(tempfile.TemporaryDirectory(prefix="recover-a-test-"))
        self.root = Path(self.temporary)
        self.experiment = self.root / "experiment"
        self.output = self.root / "confirmation-a"
        self.grid = Path(str(self.experiment) + "-grid-steps")
        self.output.mkdir()
        self.grid.mkdir()
        self.freeze_path = self.root / "freeze.json"
        self.properties = self.root / "properties"
        self.launch_path = self.output / "launch.json"
        self.poll_path = self.output / "poll.json"
        self.properties.write_bytes(C.G.canonical({}))
        analysis_sha = C.W.file_sha(R.ANALYSIS)
        self.freeze = {
            "scope": "synthetic-test-only",
            "families": ["blocks"],
            "code_commit": "1" * 40,
            "code_sha256": {R.ANALYSIS.name: analysis_sha},
        }
        self.freeze_path.write_bytes(C.G.canonical(self.freeze))
        elements = {
            "01-build": 1,
            "02-start": 867,
            "03-parse": 1,
            "04-fetch": 1,
            "05-report": 1,
            "06-analyze": 1,
        }
        self.launch = {"schema": "pdb-within-family-launch/v1",
                       "experiment": str(self.experiment), "jobs": [],
                       "poll_interval_seconds": 3600}
        self.accounting = []
        for step, count in elements.items():
            job_id = R.EXPECTED_JOB_IDS[step]
            name = self.experiment.name + "-" + step
            job_file = self.grid / name
            script = ("#SBATCH --time=01:45:00\n"
                      "#SBATCH --job-name={}\n".format(name))
            job_file.write_text(script)
            self.launch["jobs"].append({
                "job_id": job_id,
                "job_file": str(job_file),
                "job_sha256": C.W.file_sha(job_file),
                "array_elements": count,
                "accepted_utc": "2026-09-14T15:12:29+00:00",
                "script": script,
            })
            for index in range(1, count + 1):
                state, exit_code = (("FAILED", "1:0") if step == "06-analyze"
                                    else ("COMPLETED", "0:0"))
                self.accounting.append(
                    f"{job_id}_{index}|{name}|{state}|{exit_code}|fat|"
                    "naiss2025-5-561-cpu|normal|9|3Gc|01:45:00|node|1")
        self.launch_path.write_bytes(C.G.canonical(self.launch))
        self.error_tail = (
            "Traceback (most recent call last):\n"
            "    versions.append(C.G.canonical(result))\n" + R.SERIALIZATION_ERROR + "\n"
            "aborting\n")
        (self.grid / "slurm.err").write_text(self.error_tail)
        (self.grid / "slurm.log").write_text("synthetic pipeline log\n")
        self._write_poll(self.accounting)

        self.stack.enter_context(mock.patch.object(R.Runner, "OUTPUT", self.experiment))
        self.stack.enter_context(mock.patch.object(A, "OUTPUT", self.output))
        self.stack.enter_context(mock.patch.object(C, "FREEZE", self.freeze_path))
        self.stack.enter_context(mock.patch.object(C, "load_freeze", return_value=self.freeze))
        self.stack.enter_context(mock.patch.object(A, "verify_run_evidence"))
        self.stack.enter_context(mock.patch.object(A, "validate_matrix"))
        self.stack.enter_context(mock.patch.object(A, "configured",
                                                  return_value=contextlib.nullcontext()))
        self.stack.enter_context(mock.patch.object(R, "EXPECTED_LAUNCH_SHA256",
                                                  C.W.file_sha(self.launch_path)))
        self.stack.enter_context(mock.patch.object(R, "EXPECTED_POLL_SHA256",
                                                  C.W.file_sha(self.poll_path)))
        self.stack.enter_context(mock.patch.object(R, "EXPECTED_FREEZE_SHA256",
                                                  C.W.file_sha(self.freeze_path)))
        self.stack.enter_context(mock.patch.object(R, "EXPECTED_PROPERTIES_SHA256",
                                                  C.W.file_sha(self.properties)))
        self.stack.enter_context(mock.patch.object(R, "EXPECTED_PYTHON_SHA256",
                                                  C.W.file_sha(R.PYTHON)))
        wrapper = {"path": str(R.WRAPPER), "sha256": C.W.file_sha(R.WRAPPER),
                   "committed_revision": "2" * 40}
        self.stack.enter_context(mock.patch.object(R, "_committed_wrapper_identity",
                                                  return_value=wrapper))
        self.stack.enter_context(mock.patch.object(R, "_validate_committed_wrapper"))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)

    def _write_poll(self, accounting, *, queue="", error_tail=None):
        if error_tail is not None:
            self.error_tail = error_tail
            (self.grid / "slurm.err").write_text(error_tail)
        ids = ",".join(R.EXPECTED_JOB_IDS.values())
        stdout = "\n".join(accounting)
        validation = C.Monitor.check_accounting(self.launch, stdout)
        self.poll = {
            "schema": "pdb-within-family-poll/v1",
            "started_utc": "2026-09-14T21:15:29+00:00",
            "launch_sha256": C.W.file_sha(self.launch_path),
            "queries": {
                "queue": {"command": ["squeue", "--noheader", "--jobs", ids,
                                      "--format=%i|%T|%R"],
                          "returncode": 0, "stdout": queue, "stderr": ""},
                "accounting": {"command": [
                    "sacct", "--noheader", "--parsable2", "--allocations", "--jobs", ids,
                    "--format=JobID%80,JobName%128,State%40,ExitCode,Partition,Account,QOS,"
                    "ReqCPUS,ReqMem,Timelimit,NodeList%200,ElapsedRaw"],
                    "returncode": 0, "stdout": stdout, "stderr": ""},
            },
            "validation": validation,
            "pipeline_logs": {
                name: {"sha256": C.W.file_sha(self.grid / name),
                       "tail": (self.grid / name).read_bytes()[-12000:].decode("utf-8", "replace")}
                for name in ("slurm.log", "slurm.err")
            },
        }
        self.poll_path.write_bytes(C.G.canonical(self.poll))

    def update_expected_poll_hash(self):
        R.EXPECTED_POLL_SHA256 = C.W.file_sha(self.poll_path)

    def write_analysis(self):
        result = {
            "schema": A.SCHEMA,
            "scope": self.freeze["scope"],
            "freeze_sha256": C.W.file_sha(self.freeze_path),
            "input": {
                "properties_path": str(self.properties.resolve()),
                "properties_sha256": R.EXPECTED_PROPERTIES_SHA256,
                "code_commit": self.freeze["code_commit"],
                "code_sha256": self.freeze["code_sha256"],
            },
            "matrix": {"tasks": 650, "configs": 4, "cells": 2600, "families": 1,
                       "outcome_classes": {}},
            "gates": {"decision": "PASS", "pass": True,
                      "primary": {"pass": True}, "unseen_family_gate": False},
            "statistical_selector_gate_passed": True,
        }
        raw = C.G.canonical(result)
        (self.output / "analysis.json").write_bytes(raw)
        (self.output / "analysis-repeat.json").write_bytes(raw)
        receipt = {
            "schema": A.SCHEMA + "/double-execution",
            "byte_identical": True,
            "analysis_sha256": C.G.sha(raw),
            "repeat_sha256": C.G.sha(raw),
            "properties_sha256": R.EXPECTED_PROPERTIES_SHA256,
            "freeze_sha256": C.W.file_sha(self.freeze_path),
            "scheduler_audit_required_before_selector_launch": True,
        }
        (self.output / "analysis-receipt.json").write_bytes(C.G.canonical(receipt))

    def successful_runner(self, command, **kwargs):
        self.write_analysis()
        return SimpleNamespace(returncode=0, stdout=b"synthetic stdout\n", stderr=b"")

    def recover(self, runner=None):
        return R.recover(self.launch_path, self.poll_path, self.properties,
                         self.output, R.PYTHON, runner or self.successful_runner)


class SerializationRecoveryTests(unittest.TestCase):
    def test_recovers_locally_and_builds_eight_role_seal(self):
        with RecoveryFixture() as fixture:
            receipt, seal = fixture.recover()
            self.assertEqual(receipt["integer_max_str_digits"], 100000)
            self.assertEqual(receipt["scientific_runs_repeated"], 0)
            self.assertEqual(receipt["scheduler_queries_made_by_recovery"], 0)
            self.assertEqual(receipt["original_analysis_failure"]["job_id"], "2418268")
            self.assertEqual(set(seal["evidence"]), {
                "freeze", "launch", "poll", "analysis", "repeat", "receipt",
                "properties", "recovery"})
            self.assertEqual(seal["original_scheduler_analysis"],
                             receipt["original_analysis_failure"])
            loaded, _ = R.load_seal(fixture.output / "completion-seal.json")
            self.assertEqual(loaded, seal)

    def test_large_integer_round_trip_and_finite_upper_bound(self):
        previous = sys.get_int_max_str_digits()
        try:
            R.configure_integer_serialization()
            encoded = json.dumps({"value": 10 ** 5000})
            self.assertEqual(json.loads(encoded)["value"], 10 ** 5000)
            with self.assertRaisesRegex(ValueError, "limit"):
                json.dumps({"value": 10 ** 101000})
        finally:
            sys.set_int_max_str_digits(previous)

    def test_rejects_altered_input_and_code_hashes(self):
        with RecoveryFixture() as fixture:
            fixture.launch_path.write_bytes(fixture.launch_path.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "launch/poll identity"):
                fixture.recover()
        with RecoveryFixture() as fixture:
            fixture.freeze["code_sha256"][R.ANALYSIS.name] = "0" * 64
            with self.assertRaisesRegex(ValueError, "analysis code identity"):
                fixture.recover()

    def test_rejects_unrelated_analysis_error(self):
        with RecoveryFixture() as fixture:
            fixture._write_poll(fixture.accounting,
                                error_tail="Traceback\nValueError: unrelated\naborting\n")
            fixture.update_expected_poll_hash()
            with self.assertRaisesRegex(ValueError, "different reason"):
                fixture.recover()

    def test_rejects_nonterminal_or_failed_scientific_jobs(self):
        for state, exit_code, queue in (("RUNNING", "0:0", "2418263_1|RUNNING|node\n"),
                                        ("FAILED", "1:0", "")):
            with self.subTest(state=state), RecoveryFixture() as fixture:
                changed = list(fixture.accounting)
                fields = changed[0].split("|")
                fields[2:4] = [state, exit_code]
                changed[0] = "|".join(fields)
                fixture._write_poll(changed, queue=queue)
                fixture.update_expected_poll_hash()
                with self.assertRaises(ValueError):
                    fixture.recover()

    def test_retains_nonzero_recovery_diagnostics_without_success_receipt(self):
        with RecoveryFixture() as fixture:
            runner = mock.Mock(return_value=SimpleNamespace(
                returncode=1, stdout=b"out", stderr=b"serialization failed"))
            with self.assertRaisesRegex(ValueError, "returned nonzero"):
                fixture.recover(runner)
            self.assertFalse((fixture.output / "serialization-recovery.json").exists())
            self.assertFalse((fixture.output / "completion-seal.json").exists())
            self.assertEqual((fixture.output / R.STDOUT.name).read_bytes(), b"out")
            self.assertEqual((fixture.output / R.STDERR.name).read_bytes(),
                             b"serialization failed")
            invocation = json.loads(
                (fixture.output / R.INVOCATION.name).read_bytes())
            self.assertEqual(invocation["returncode"], 1)
            self.assertFalse(invocation["timed_out"])
            with self.assertRaisesRegex(ValueError, "refusing existing"):
                fixture.recover(runner)

    def test_retains_timeout_diagnostics_without_success_receipt(self):
        with RecoveryFixture() as fixture:
            error = subprocess.TimeoutExpired(["python"], R.TIMEOUT_SECONDS,
                                              output=b"partial out", stderr=b"partial err")
            runner = mock.Mock(side_effect=error)
            with self.assertRaisesRegex(ValueError, "timed out"):
                fixture.recover(runner)
            self.assertFalse((fixture.output / "serialization-recovery.json").exists())
            self.assertFalse((fixture.output / "completion-seal.json").exists())
            self.assertEqual((fixture.output / R.STDOUT.name).read_bytes(),
                             b"partial out")
            self.assertEqual((fixture.output / R.STDERR.name).read_bytes(),
                             b"partial err")
            invocation = json.loads(
                (fixture.output / R.INVOCATION.name).read_bytes())
            self.assertIsNone(invocation["returncode"])
            self.assertTrue(invocation["timed_out"])

    def test_rejects_mismatched_repeats_and_receipts(self):
        with RecoveryFixture() as fixture:
            fixture.recover()
            repeat = fixture.output / "analysis-repeat.json"
            repeat.write_bytes(repeat.read_bytes() + b" ")
            with self.assertRaisesRegex(ValueError, "analyses differ"):
                R.validate_recovery_receipt(fixture.output / "serialization-recovery.json",
                                            fixture.launch_path, fixture.poll_path,
                                            fixture.properties, fixture.output)
        with RecoveryFixture() as fixture:
            fixture.recover()
            receipt_path = fixture.output / "analysis-receipt.json"
            receipt = json.loads(receipt_path.read_bytes())
            receipt["byte_identical"] = False
            receipt_path.write_bytes(C.G.canonical(receipt))
            with self.assertRaisesRegex(ValueError, "double-execution receipt"):
                R.validate_recovery_receipt(fixture.output / "serialization-recovery.json",
                                            fixture.launch_path, fixture.poll_path,
                                            fixture.properties, fixture.output)

    def test_rejects_properties_changed_during_recovery(self):
        with RecoveryFixture() as fixture:
            def changing_runner(command, **kwargs):
                fixture.write_analysis()
                fixture.properties.write_bytes(b"{}\n ")
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

            with self.assertRaisesRegex(ValueError, "properties changed"):
                fixture.recover(changing_runner)

    def test_rejects_altered_limit_in_retained_receipt(self):
        with RecoveryFixture() as fixture:
            fixture.recover()
            path = fixture.output / "serialization-recovery.json"
            receipt = json.loads(path.read_bytes())
            receipt["integer_max_str_digits"] = 0
            path.write_bytes(C.G.canonical(receipt))
            with self.assertRaisesRegex(ValueError, "recovery receipt changed"):
                R.validate_recovery_receipt(path, fixture.launch_path, fixture.poll_path,
                                            fixture.properties, fixture.output)

    def test_refuses_existing_outputs_or_logs(self):
        for name in ("analysis.json", R.STDERR.name):
            with self.subTest(name=name), RecoveryFixture() as fixture:
                (fixture.output / name).write_bytes(b"existing")
                with self.assertRaisesRegex(ValueError, "refusing existing"):
                    fixture.recover()

    def test_preserves_failed_attempt_logs_under_the_old_prefix(self):
        with RecoveryFixture() as fixture:
            retained = {
                "serialization-recovery-invocation.json": b"failed invocation\n",
                "serialization-recovery.stdout": b"failed stdout\n",
                "serialization-recovery.stderr": b"failed stderr\n",
            }
            for name, raw in retained.items():
                (fixture.output / name).write_bytes(raw)
            fixture.recover()
            for name, raw in retained.items():
                self.assertEqual((fixture.output / name).read_bytes(), raw)

    def test_exact_venv_command_imports_lab_dependencies(self):
        command = [str(R.PYTHON.absolute()), "-X", "int_max_str_digits=100000", "-B",
                   "-c", "import downward, lab"]
        self.assertNotEqual(command[0], str(R.PYTHON.resolve()))
        completed = subprocess.run(command, cwd=C.G.ROOT, env=R._child_environment(),
                                   capture_output=True, timeout=30, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
