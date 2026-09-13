#!/usr/bin/env python3
"""Focused tests for the scheduler-only V9 terminal-failure recorder."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import record_pdb_terminal_incidence_confirmation_source_audit_v9_failure as R


RECORDER_REVISION = "c" * 40


def _scheduler_output(
    *, failure_index: int = 819, failure_state: str = "OUT_OF_MEMORY",
) -> bytes:
    lines = []
    for index in range(R.EXPECTED_ARRAY_TASKS):
        state = failure_state if index == failure_index else "COMPLETED"
        exit_code = "0:125" if index == failure_index else "0:0"
        reason = "OutOfMemory" if index == failure_index else "None"
        elapsed = "2400" if index == failure_index else str(10 + index)
        lines.append(
            "{}_{}|{}|{}|{}|{}|fat|0\n".format(
                R.EXPECTED_JOB_ID,
                index,
                state,
                exit_code,
                reason,
                elapsed,
            )
        )
    return "".join(lines).encode("ascii")


def _authenticated() -> dict:
    launch_materials = [
        {"path": path, "bytes": 1, "sha256": str(index) * 64}
        for index, path in enumerate(R.LAUNCH_ARTIFACT_PATHS, start=1)
    ]
    source_files = [
        {"path": "experiments/source-{}.py".format(index), "sha256": "a" * 64}
        for index in range(R.EXPECTED_SOURCE_FILES)
    ]
    return {
        "launch_receipt": launch_materials[-1],
        "launch_materials": launch_materials,
        "launch_materials_sha256": R._digest(launch_materials),
        "source_manifest": {
            "path": R.SOURCE_MANIFEST_PATH,
            "bytes": 1,
            "sha256": R.EXPECTED_CODE_MANIFEST_SHA256,
        },
        "source_files": source_files,
        "source_files_sha256": R._digest(source_files),
    }


class FailureRecorderTests(unittest.TestCase):
    def _context(self, root: Path):
        artifact_dir = root / "experiments" / "artifacts" / "campaign"
        artifact_dir.mkdir(parents=True, mode=0o700)
        receipt = artifact_dir / "failure.json"
        query_intent = artifact_dir / "query-intent.json"
        scheduler_stdout = artifact_dir / "scheduler-stdout.bin"
        seal = tuple(artifact_dir / "seal-{}.json".format(i) for i in range(7))
        stack = ExitStack()
        stack.enter_context(mock.patch.object(R, "REPO", root))
        stack.enter_context(mock.patch.object(R, "ARTIFACT_DIR", artifact_dir))
        stack.enter_context(mock.patch.object(R, "FAILURE_RECEIPT", receipt))
        stack.enter_context(mock.patch.object(R, "QUERY_INTENT", query_intent))
        stack.enter_context(mock.patch.object(R, "SCHEDULER_STDOUT", scheduler_stdout))
        stack.enter_context(mock.patch.object(R, "FORBIDDEN_SEAL_ARTIFACTS", seal))
        stack.enter_context(
            mock.patch.object(
                R, "_require_committed_recorder", return_value=RECORDER_REVISION
            )
        )
        stack.enter_context(
            mock.patch.object(
                R, "_load_authenticated_launch_materials",
                return_value=_authenticated(),
            )
        )
        stack.enter_context(mock.patch.object(R, "_require_lineage"))
        stack.enter_context(
            mock.patch.object(
                R,
                "_load_prior_query_attempt",
                return_value={
                    "path": R.PRIOR_QUERY_ATTEMPT_RELATIVE,
                    "bytes": 1,
                    "sha256": R.EXPECTED_PRIOR_QUERY_ATTEMPT_SHA256,
                },
            )
        )
        stack.enter_context(
            mock.patch.object(R, "_utc_now", return_value="2026-09-13T18:01:00+00:00")
        )
        return stack, receipt, seal, query_intent, scheduler_stdout

    def test_records_one_scheduler_census_and_one_exclusive_artifact(self):
        with tempfile.TemporaryDirectory(prefix="v9-failure-record-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            stack, path, _seal, query_intent, scheduler_stdout = self._context(root)
            calls = []

            def query(command):
                calls.append(command)
                return _scheduler_output()

            with stack, mock.patch.object(
                R.subprocess,
                "run",
                side_effect=AssertionError("default sacct path used"),
            ), mock.patch.object(
                Path,
                "iterdir",
                side_effect=AssertionError("runtime namespace enumerated"),
            ):
                digest, receipt = R.record_failure(scheduler_query=query)

            self.assertEqual(calls, [R._sacct_command()])
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(path.read_bytes(), R._canonical_json(receipt))
            self.assertEqual(receipt["scheduler_query_count"], 1)
            self.assertEqual(len(receipt["scheduler_rows"]), 820)
            self.assertEqual(receipt["scheduler_aggregate"]["failed_rows"], 1)
            self.assertEqual(
                receipt["scheduler_aggregate"]["state_counts"],
                {"COMPLETED": 819, "OUT_OF_MEMORY": 1},
            )
            self.assertEqual(
                receipt["scheduler_stdout_sha256"],
                hashlib.sha256(_scheduler_output()).hexdigest(),
            )
            self.assertTrue(receipt["scheduler_raw_stdout_recorded"])
            self.assertEqual(scheduler_stdout.read_bytes(), _scheduler_output())
            self.assertEqual(
                receipt["scheduler_query_intent"]["sha256"],
                hashlib.sha256(query_intent.read_bytes()).hexdigest(),
            )
            self.assertFalse(receipt["v9_runtime_namespace_enumerated"])
            self.assertFalse(receipt["v9_payload_reused"])
            self.assertTrue(receipt["v9_burned"])
            created = [entry.name for entry in path.parent.iterdir()]
            self.assertEqual(
                created, [query_intent.name, scheduler_stdout.name, path.name]
            )

    def test_rejects_active_missing_duplicate_malformed_and_all_success_rows(self):
        valid = _scheduler_output().decode("ascii").splitlines()
        cases = {
            "active": valid[:-1] + [
                valid[-1].replace("OUT_OF_MEMORY", "RUNNING")
            ],
            "missing": valid[:-1],
            "duplicate": valid + [valid[-1]],
            "malformed": valid[:-1] + [valid[-1] + "|extra"],
            "all-success": [
                "{}_{}|COMPLETED|0:0|None|{}|fat|0".format(
                    R.EXPECTED_JOB_ID, index, 10 + index
                )
                for index in range(R.EXPECTED_ARRAY_TASKS)
            ],
        }
        for label, lines in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory(
                prefix="v9-failure-invalid-"
            ) as tmp:
                root = Path(tmp) / "repo"
                root.mkdir(mode=0o700)
                stack, path, _seal, query_intent, scheduler_stdout = self._context(root)
                calls = []

                def query(command, payload=("\n".join(lines) + "\n").encode("ascii")):
                    calls.append(command)
                    return payload

                with stack, self.assertRaises(R.FailureRecorderError):
                    R.record_failure(scheduler_query=query)
                self.assertEqual(len(calls), 1)
                self.assertFalse(path.exists())
                self.assertTrue(query_intent.exists())
                self.assertTrue(scheduler_stdout.exists())

    def test_accepts_exact_all_failed_publication_exit_census(self):
        raw = "".join(
            "{}_{}|FAILED|2:0|NonZeroExitCode|{}|fat|0\n".format(
                R.EXPECTED_JOB_ID, index, 20 + index
            )
            for index in range(R.EXPECTED_ARRAY_TASKS)
        ).encode("ascii")

        rows, aggregate = R._parse_terminal_rows(raw)

        self.assertEqual(len(rows), 820)
        self.assertEqual(aggregate["successful_rows"], 0)
        self.assertEqual(aggregate["failed_rows"], 820)
        self.assertEqual(aggregate["state_counts"], {"FAILED": 820})
        self.assertEqual(
            aggregate["state_exit_code_counts"],
            [{"state": "FAILED", "exit_code": "2:0", "count": 820}],
        )
        self.assertTrue(aggregate["all_terminal"])
        self.assertFalse(aggregate["all_success"])

    def test_parser_accepts_sacct_width_padding_without_changing_values(self):
        padded = []
        for line in _scheduler_output().decode("ascii").splitlines():
            padded.append("|".join("  " + field + "  " for field in line.split("|")))
        rows, aggregate = R._parse_terminal_rows(
            ("\n".join(padded) + "\n").encode("ascii")
        )
        self.assertEqual(len(rows), R.EXPECTED_ARRAY_TASKS)
        self.assertEqual(aggregate["failed_rows"], 1)

    def test_hourly_boundary_blocks_before_intent_or_scheduler_query(self):
        with tempfile.TemporaryDirectory(prefix="v9-failure-cadence-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            stack, path, _seal, query_intent, scheduler_stdout = self._context(root)
            query = mock.Mock(side_effect=AssertionError("scheduler queried"))
            with (
                stack,
                mock.patch.object(
                    R, "_utc_now", return_value="2026-09-13T18:00:35+00:00"
                ),
                self.assertRaisesRegex(R.FailureRecorderError, "hourly cadence"),
            ):
                R.record_failure(scheduler_query=query)
            query.assert_not_called()
            self.assertFalse(path.exists())
            self.assertFalse(query_intent.exists())
            self.assertFalse(scheduler_stdout.exists())

    def test_existing_failure_or_seal_blocks_scheduler_query(self):
        for kind in ("failure", "seal"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory(
                prefix="v9-failure-collision-"
            ) as tmp:
                root = Path(tmp) / "repo"
                root.mkdir(mode=0o700)
                stack, path, seal, _query_intent, _scheduler_stdout = self._context(root)
                target = path if kind == "failure" else seal[0]
                target.write_bytes(b"existing")
                query = mock.Mock(side_effect=AssertionError("scheduler queried"))
                with stack, self.assertRaises(R.FailureRecorderError):
                    R.record_failure(scheduler_query=query)
                query.assert_not_called()
                self.assertEqual(target.read_bytes(), b"existing")

    def test_scheduler_command_has_only_required_scheduler_fields(self):
        command = R._sacct_command()
        self.assertEqual(command.count(str(R.SACCT_COMMAND)), 1)
        self.assertIn(R.EXPECTED_JOB_ID, command)
        field = next(value for value in command if value.startswith("--format="))
        self.assertNotIn("%", field)
        for required in (
            "JobID", "State", "ExitCode", "Reason", "ElapsedRaw",
            "Partition", "Restarts",
        ):
            self.assertIn(required, field)
        self.assertNotIn("NodeList", field)

    def test_committed_prior_attempt_is_exactly_hash_bound(self):
        material = R._load_prior_query_attempt()
        self.assertEqual(material["path"], R.PRIOR_QUERY_ATTEMPT_RELATIVE)
        self.assertEqual(
            material["sha256"], R.EXPECTED_PRIOR_QUERY_ATTEMPT_SHA256
        )

    def test_authenticates_temporary_committed_launch_and_source_closures(self):
        with tempfile.TemporaryDirectory(prefix="v9-committed-fixture-") as tmp:
            root = Path(tmp)
            source_paths = sorted(R.REQUIRED_SOURCE_PATHS) + [
                "src/source-{:02d}.py".format(index)
                for index in range(
                    R.EXPECTED_SOURCE_FILES - len(R.REQUIRED_SOURCE_PATHS)
                )
            ]
            source_bytes = {
                path: ("source " + path).encode("ascii") for path in source_paths
            }
            manifest = b"".join(
                hashlib.sha256(source_bytes[path]).hexdigest().encode("ascii")
                + b"  " + path.encode("ascii") + b"\n"
                for path in source_paths
            )

            stdout = (R.EXPECTED_JOB_ID + "\n").encode("ascii")
            stderr = b""
            intent = {
                "campaign": "v9-full-census",
                "repository_commit_id": R.EXPECTED_SOURCE_REVISION,
                "resource_profile": R.EXPECTED_RESOURCE_PROFILE,
                "code_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                "source_inventory_sha256": "f" * 64,
            }
            intent_raw = R._canonical_json(intent)
            result = {
                "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
                "parsed_job_id": R.EXPECTED_JOB_ID,
                "accepted_by_launcher": True,
                "raw_streams_preserved": True,
                "stdout": {
                    "bytes": len(stdout),
                    "sha256": hashlib.sha256(stdout).hexdigest(),
                },
                "stderr": {
                    "bytes": len(stderr),
                    "sha256": hashlib.sha256(stderr).hexdigest(),
                },
            }
            result_raw = R._canonical_json(result)
            receipt = {
                "campaign": "v9-full-census",
                "job_id": R.EXPECTED_JOB_ID,
                "repository_commit_id": R.EXPECTED_SOURCE_REVISION,
                "resource_profile": R.EXPECTED_RESOURCE_PROFILE,
                "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
                "sbatch_result_sha256": hashlib.sha256(result_raw).hexdigest(),
                "code_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                "source_inventory_sha256": "f" * 64,
                "launch_recovered": False,
                "recovery_evidence": None,
                "whole_campaign_fresh": True,
                "selective_recovery_authorized": False,
                "prior_runtime_payloads_read": 0,
                "prior_runtime_payload_bytes_read": 0,
                "prior_runtime_payloads_reused": 0,
            }
            receipt_raw = R._canonical_json(receipt)
            launch_raw = {
                R.LAUNCH_ARTIFACT_PATHS[0]: intent_raw,
                R.LAUNCH_ARTIFACT_PATHS[1]: stdout,
                R.LAUNCH_ARTIFACT_PATHS[2]: stderr,
                R.LAUNCH_ARTIFACT_PATHS[3]: result_raw,
                R.LAUNCH_ARTIFACT_PATHS[4]: receipt_raw,
            }
            for revision, values in (
                (R.EXPECTED_LAUNCH_REVISION, launch_raw),
                (
                    R.EXPECTED_SOURCE_REVISION,
                    {R.SOURCE_MANIFEST_PATH: manifest, **source_bytes},
                ),
            ):
                for path, raw in values.items():
                    destination = root / revision / path
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    destination.write_bytes(raw)

            requested = []

            def snapshot(revision, paths):
                requested.extend((revision, path) for path in paths)
                return {
                    path: (root / revision / path).read_bytes() for path in paths
                }

            hashes = {
                path: hashlib.sha256(raw).hexdigest()
                for path, raw in launch_raw.items()
            }
            with (
                mock.patch.object(R, "EXPECTED_LAUNCH_ARTIFACT_SHA256", hashes),
                mock.patch.object(
                    R,
                    "EXPECTED_LAUNCH_RECEIPT_SHA256",
                    hashlib.sha256(receipt_raw).hexdigest(),
                ),
                mock.patch.object(
                    R,
                    "EXPECTED_CODE_MANIFEST_SHA256",
                    hashlib.sha256(manifest).hexdigest(),
                ),
                mock.patch.object(R, "EXPECTED_SOURCE_INVENTORY_SHA256", "f" * 64),
            ):
                authenticated = R._load_authenticated_launch_materials(snapshot)

            self.assertEqual(len(authenticated["source_files"]), 54)
            self.assertEqual(len(authenticated["launch_materials"]), 5)
            self.assertTrue(all("experiments/data/" not in path for _, path in requested))
            self.assertTrue(all("NodeList" not in path for _, path in requested))

    def test_temporary_launch_mutation_is_rejected(self):
        def snapshot(revision, paths):
            self.assertEqual(revision, R.EXPECTED_LAUNCH_REVISION)
            return {path: b"mutated" for path in paths}

        with self.assertRaisesRegex(
            R.FailureRecorderError, "launch artifact changed"
        ):
            R._load_authenticated_launch_materials(snapshot)

    def test_default_sacct_runner_is_one_binary_call_and_rejects_stderr(self):
        command = R._sacct_command()
        completed = mock.Mock(
            returncode=0,
            stdout=b"scheduler bytes",
            stderr=b"",
        )
        with mock.patch.object(R.subprocess, "run", return_value=completed) as run:
            self.assertEqual(R._run_sacct(command), b"scheduler bytes")
        run.assert_called_once_with(
            command,
            cwd=R.REPO,
            env=R.CONTROLLED_ENVIRONMENT,
            check=False,
            stdout=R.subprocess.PIPE,
            stderr=R.subprocess.PIPE,
        )

        completed.stderr = b"warning"
        with mock.patch.object(R.subprocess, "run", return_value=completed):
            with self.assertRaises(R.FailureRecorderError):
                R._run_sacct(command)


if __name__ == "__main__":
    unittest.main()
