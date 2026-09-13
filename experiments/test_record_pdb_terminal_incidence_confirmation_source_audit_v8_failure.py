#!/usr/bin/env python3
"""Tests for the scheduler-only V8 terminal-failure recorder."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import launch_pdb_terminal_incidence_confirmation_source_audit_v8 as V8
import record_pdb_terminal_incidence_confirmation_source_audit_v8_failure as R


TASKS = list(range(25))
RECORDER_REVISION = "b" * 40
LAUNCH_REVISION = "a" * 40


def _row(index: int, state: str, exit_code: str) -> dict:
    return {
        "array_task": index,
        "state": state,
        "exit_code": exit_code,
        "partition": "fat",
    }


def _failure_rows() -> list[dict]:
    return [
        *[_row(index, "COMPLETED", "0:0") for index in TASKS[:8]],
        *[_row(index, "OUT_OF_MEMORY", "0:125") for index in TASKS[8:]],
    ]


def _launch() -> dict:
    return {
        "job_id": "2068461",
        "repository_commit_id": LAUNCH_REVISION,
        "repair_v5_shard_indices": TASKS,
        "array": "0-24",
        "array_throttle": 0,
        "partition": V8.PARTITION,
        "qos": V8.QOS,
        "account": V8.ACCOUNT,
        "cpus_per_task": V8.CPUS_PER_TASK,
        "resource_mapping": V8._resource_mapping(),
        "submission_token": "must-not-appear-in-failure-receipt",
    }


def _authenticated() -> dict:
    return {
        "launch": _launch(),
        "diagnostic": {"repair_v5_shard_indices": TASKS},
        "launch_materials": [
            {"path": "experiments/intent.json", "bytes": 7, "sha256": "1" * 64},
            {"path": "experiments/stdout.bin", "bytes": 8, "sha256": "2" * 64},
        ],
        "source_inventory_record_count": V8.Source.CANDIDATE_COUNT,
    }


class FailureRecorderTest(unittest.TestCase):
    def _record_context(self, root: Path, rows):
        receipt = root / "artifacts" / "failure.json"
        forbidden = tuple(root / "forbidden" / str(index) for index in range(4))
        stack = ExitStack()
        stack.enter_context(mock.patch.object(R, "REPO", root))
        stack.enter_context(mock.patch.object(R, "FAILURE_RECEIPT", receipt))
        stack.enter_context(
            mock.patch.object(R, "FORBIDDEN_SEAL_ARTIFACTS", forbidden)
        )
        stack.enter_context(
            mock.patch.object(
                R, "_require_clean_parent", return_value=RECORDER_REVISION
            )
        )
        stack.enter_context(
            mock.patch.object(
                R, "_load_authenticated_launch_materials",
                return_value=_authenticated(),
            )
        )
        stack.enter_context(mock.patch.object(R, "_require_launch_lineage"))
        stack.enter_context(
            mock.patch.object(
                R,
                "_successor_record",
                return_value={
                    "campaign": "v9-full-census",
                    "candidate_count": R.EXPECTED_SUCCESSOR_CANDIDATES,
                    "frozen_before_v8_scheduler_query": True,
                    "candidate_set_independent_of_v8_scheduler_rows": True,
                    "v1_through_v8_runtime_payload_reuse_authorized": False,
                },
            )
        )
        stack.enter_context(
            mock.patch.object(R, "_utc_now", return_value="2026-09-13T12:00:00+00:00")
        )
        scheduler = stack.enter_context(
            mock.patch.object(V8, "_v8_scheduler_rows", return_value=rows)
        )
        return stack, scheduler, receipt

    def test_records_exact_failure_with_one_query_and_no_payload_access(self):
        with tempfile.TemporaryDirectory(prefix="v8-failure-record-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            stack, scheduler, path = self._record_context(root, _failure_rows())
            with (
                stack,
                mock.patch.object(
                    V8, "_seal_context", side_effect=AssertionError("seal entered")
                ),
                mock.patch.object(
                    V8, "_read_v5_reusable_triplets",
                    side_effect=AssertionError("V5 payload opened"),
                ),
                mock.patch.object(
                    V8.Runtime, "_v6_output_tree",
                    side_effect=AssertionError("V8 payload opened"),
                ),
                mock.patch.object(
                    V8, "_scheduler_contract_rows",
                    side_effect=AssertionError("detailed accounting queried"),
                ),
                mock.patch.object(
                    V8.SelectedIO, "read_selected_flat_tree",
                    side_effect=AssertionError("output tree opened"),
                ),
            ):
                digest, receipt = R.record_failure()

            scheduler.assert_called_once_with("2068461", TASKS)
            self.assertEqual(digest, hashlib.sha256(path.read_bytes()).hexdigest())
            self.assertEqual(
                receipt["scheduler_state_counts"],
                {"COMPLETED": 8, "OUT_OF_MEMORY": 17},
            )
            self.assertEqual(receipt["scheduler_query_count"], 1)
            self.assertFalse(receipt["scheduler_all_success"])
            self.assertTrue(receipt["v8_burned"])
            self.assertFalse(receipt["confirmation_prelaunch_authorized"])
            self.assertFalse(receipt["confirmation_a_prelaunch_authorized"])
            self.assertFalse(receipt["v8_partial_output_reuse_authorized"])
            self.assertEqual(
                receipt["frozen_successor"]["candidate_count"],
                R.EXPECTED_SUCCESSOR_CANDIDATES,
            )
            self.assertTrue(
                receipt["frozen_successor"]
                ["frozen_before_v8_scheduler_query"]
            )
            self.assertTrue(
                receipt["frozen_successor"]
                ["candidate_set_independent_of_v8_scheduler_rows"]
            )
            self.assertFalse(
                receipt["frozen_successor"]
                ["v1_through_v8_runtime_payload_reuse_authorized"]
            )
            self.assertFalse(
                receipt[
                    "v5_or_v8_payload_log_environment_or_scientific_output_read"
                ]
            )
            self.assertFalse(
                receipt[
                    "v5_or_v8_payload_log_environment_or_scientific_output_reused"
                ]
            )
            raw = path.read_bytes()
            self.assertEqual(raw, R._canonical_json(receipt))
            self.assertNotIn(b"must-not-appear-in-failure-receipt", raw)

    def test_freezes_successor_before_the_sole_scheduler_query(self):
        with tempfile.TemporaryDirectory(prefix="v8-failure-order-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            events = []
            stack, scheduler, _path = self._record_context(root, _failure_rows())

            def freeze_successor(revision):
                self.assertEqual(revision, RECORDER_REVISION)
                events.append("freeze-successor")
                return {
                    "campaign": "v9-full-census",
                    "frozen_before_v8_scheduler_query": True,
                }

            def query_scheduler(job_id, tasks):
                self.assertEqual((job_id, tasks), ("2068461", TASKS))
                events.append("query-scheduler")
                return _failure_rows()

            stack.enter_context(
                mock.patch.object(
                    R, "_successor_record", side_effect=freeze_successor
                )
            )
            scheduler.side_effect = query_scheduler
            with stack:
                R.record_failure()

            self.assertEqual(events, ["freeze-successor", "query-scheduler"])
            scheduler.assert_called_once()

    def test_rejects_malformed_rows_after_one_query(self):
        rows = _failure_rows()
        rows[0] = {key: value for key, value in rows[0].items() if key != "partition"}
        with tempfile.TemporaryDirectory(prefix="v8-failure-malformed-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            stack, scheduler, path = self._record_context(root, rows)
            with stack, self.assertRaisesRegex(
                R.FailureRecorderError, "census is malformed"
            ):
                R.record_failure()
            scheduler.assert_called_once()
            self.assertFalse(path.exists())

    def test_rejects_active_rows_after_one_query(self):
        rows = _failure_rows()
        rows[-1] = _row(TASKS[-1], "RUNNING", "0:0")
        with tempfile.TemporaryDirectory(prefix="v8-failure-active-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            stack, scheduler, path = self._record_context(root, rows)
            with stack, self.assertRaisesRegex(
                R.FailureRecorderError, "census is malformed"
            ):
                R.record_failure()
            scheduler.assert_called_once()
            self.assertFalse(path.exists())

    def test_rejects_all_success_after_one_query(self):
        rows = [_row(index, "COMPLETED", "0:0") for index in TASKS]
        with tempfile.TemporaryDirectory(prefix="v8-failure-success-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            stack, scheduler, path = self._record_context(root, rows)
            with stack, self.assertRaisesRegex(
                R.FailureRecorderError, "all-success"
            ):
                R.record_failure()
            scheduler.assert_called_once()
            self.assertFalse(path.exists())

    def test_rejects_wrong_terminal_aggregate_after_one_query(self):
        rows = _failure_rows()
        rows[8] = _row(TASKS[8], "COMPLETED", "0:0")
        with tempfile.TemporaryDirectory(prefix="v8-failure-counts-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            stack, scheduler, path = self._record_context(root, rows)
            with stack, self.assertRaisesRegex(
                R.FailureRecorderError, "aggregate changed"
            ):
                R.record_failure()
            scheduler.assert_called_once()
            self.assertFalse(path.exists())

    def test_rejects_existing_receipt_without_query(self):
        with tempfile.TemporaryDirectory(prefix="v8-failure-collision-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            stack, scheduler, path = self._record_context(root, _failure_rows())
            path.parent.mkdir(parents=True)
            path.write_bytes(b"existing\n")
            with stack, self.assertRaisesRegex(
                R.FailureRecorderError, "already exists"
            ):
                R.record_failure()
            scheduler.assert_not_called()
            self.assertEqual(path.read_bytes(), b"existing\n")

    def test_rejects_existing_seal_artifact_without_query(self):
        with tempfile.TemporaryDirectory(prefix="v8-failure-sealed-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            stack, scheduler, path = self._record_context(root, _failure_rows())
            stage = root / "forbidden" / "0"
            stage.parent.mkdir(parents=True)
            stage.write_bytes(b"existing stage\n")
            with stack, self.assertRaisesRegex(
                R.FailureRecorderError, "seal, attestation, stage"
            ):
                R.record_failure()
            scheduler.assert_not_called()
            self.assertFalse(path.exists())

    def test_atomic_publisher_rejects_postcheck_collision(self):
        with tempfile.TemporaryDirectory(prefix="v8-failure-race-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            stack, scheduler, path = self._record_context(root, _failure_rows())

            def collide():
                path.parent.mkdir(parents=True)
                path.write_bytes(b"racing writer\n")
                return "2026-09-13T12:00:00+00:00"

            stack.enter_context(mock.patch.object(R, "_utc_now", side_effect=collide))
            with stack, self.assertRaisesRegex(
                R.FailureRecorderError, "overwrite"
            ):
                R.record_failure()
            scheduler.assert_called_once()
            self.assertEqual(path.read_bytes(), b"racing writer\n")

    def test_clean_parent_is_required_and_source_is_bound(self):
        source_sha = "d" * 64
        with (
            mock.patch.object(R.JJ, "live_working_copy_diff_summary", return_value=""),
            mock.patch.object(R.JJ, "parent_commit", return_value=RECORDER_REVISION),
            mock.patch.object(
                R, "_safe_file", return_value=SimpleNamespace(sha256=source_sha)
            ),
            mock.patch.object(
                R.JJ, "tracked_file_sha256", return_value=source_sha
            ) as tracked,
        ):
            self.assertEqual(R._require_clean_parent(), RECORDER_REVISION)
        self.assertEqual(
            tracked.call_args_list,
            [
                mock.call(
                    R.REPO, RECORDER_REVISION, R._relative(Path(R.__file__))
                ),
                mock.call(
                    R.REPO,
                    RECORDER_REVISION,
                    R._relative(R.SUCCESSOR_PROTOCOL),
                ),
            ],
        )

        with (
            mock.patch.object(
                R.JJ, "live_working_copy_diff_summary", return_value="changed"
            ),
            self.assertRaisesRegex(R.FailureRecorderError, "clean empty"),
        ):
            R._require_clean_parent()

    def test_successor_record_binds_full_census_protocol(self):
        with tempfile.TemporaryDirectory(prefix="v8-successor-record-") as tmp:
            root = Path(tmp) / "repo"
            root.mkdir(mode=0o700)
            protocol = root / "experiments" / "protocol.md"
            protocol.parent.mkdir()
            protocol.write_bytes(b"frozen full-census protocol\n")
            protocol_sha = hashlib.sha256(protocol.read_bytes()).hexdigest()
            with (
                mock.patch.object(R, "REPO", root),
                mock.patch.object(R, "SUCCESSOR_PROTOCOL", protocol),
                mock.patch.object(
                    R.JJ, "tracked_file_sha256", return_value=protocol_sha
                ) as tracked,
            ):
                record = R._successor_record(RECORDER_REVISION)

            tracked.assert_called_once_with(
                root,
                RECORDER_REVISION,
                "experiments/protocol.md",
            )
            self.assertEqual(record["campaign"], "v9-full-census")
            self.assertEqual(record["protocol"]["sha256"], protocol_sha)
            self.assertEqual(record["candidate_index_first"], 0)
            self.assertEqual(
                record["candidate_index_last"],
                R.EXPECTED_SUCCESSOR_CANDIDATES - 1,
            )
            self.assertEqual(
                record["candidate_count"], R.EXPECTED_SUCCESSOR_CANDIDATES
            )
            self.assertEqual(
                record["candidate_indices_sha256"],
                R._digest(list(range(R.EXPECTED_SUCCESSOR_CANDIDATES))),
            )
            self.assertTrue(
                record["frozen_before_v8_scheduler_query"]
            )
            self.assertTrue(
                record["candidate_set_independent_of_v8_scheduler_rows"]
            )
            self.assertFalse(
                record["v1_through_v8_runtime_payload_reuse_authorized"]
            )

    def test_successor_record_rejects_imported_candidate_count_change(self):
        protocol_sha = "e" * 64
        with (
            mock.patch.object(
                R,
                "_safe_file",
                return_value=SimpleNamespace(sha256=protocol_sha),
            ),
            mock.patch.object(
                R.JJ, "tracked_file_sha256", return_value=protocol_sha
            ),
            mock.patch.object(
                V8.Source,
                "CANDIDATE_COUNT",
                R.EXPECTED_SUCCESSOR_CANDIDATES - 1,
            ),
            self.assertRaisesRegex(
                R.FailureRecorderError, "candidate count changed"
            ),
        ):
            R._successor_record(RECORDER_REVISION)

    def test_authenticated_loader_hashes_launch_files_but_returns_no_raw_stream(self):
        with tempfile.TemporaryDirectory(
            prefix="v8-failure-materials-", dir=R.REPO
        ) as tmp:
            directory = Path(tmp)
            paths = {
                "intent": directory / "intent.json",
                "receipt": directory / "receipt.json",
                "result": directory / "result.json",
                "manifest": directory / "manifest.sha256",
                "inventory": directory / "inventory.json",
                "stdout": directory / "stdout.bin",
                "stderr": directory / "stderr.bin",
            }
            stdout = b"2068461;cluster secret-stream-token\n"
            stderr = b"private warning bytes\x00\xff"
            paths["stdout"].write_bytes(stdout)
            paths["stderr"].write_bytes(stderr)
            intent = {"submission_token": "secret-intent-token"}
            paths["intent"].write_bytes(R._canonical_json(intent))
            inventory = {"fixture": "secret-inventory-value"}
            paths["inventory"].write_bytes(R._canonical_json(inventory))
            manifest_raw = b"0" * 64 + b"  experiments/fixture.py\n"
            paths["manifest"].write_bytes(manifest_raw)
            result = {
                "stdout": {
                    "path": str(paths["stdout"]), "bytes": len(stdout),
                    "sha256": hashlib.sha256(stdout).hexdigest(),
                },
                "stderr": {
                    "path": str(paths["stderr"]), "bytes": len(stderr),
                    "sha256": hashlib.sha256(stderr).hexdigest(),
                },
            }
            paths["result"].write_bytes(R._canonical_json(result))
            launch = {
                **_launch(),
                "launch_intent_sha256": hashlib.sha256(
                    paths["intent"].read_bytes()
                ).hexdigest(),
                "sbatch_result_sha256": hashlib.sha256(
                    paths["result"].read_bytes()
                ).hexdigest(),
                "code_manifest_sha256": hashlib.sha256(manifest_raw).hexdigest(),
                "source_inventory_sha256": hashlib.sha256(
                    paths["inventory"].read_bytes()
                ).hexdigest(),
            }
            paths["receipt"].write_bytes(R._canonical_json(launch))
            launch_sha = hashlib.sha256(paths["receipt"].read_bytes()).hexdigest()
            patches = {
                "INTENT": paths["intent"],
                "LAUNCH_RECEIPT": paths["receipt"],
                "SBATCH_RESULT": paths["result"],
                "CODE_MANIFEST": paths["manifest"],
                "SOURCE_INVENTORY": paths["inventory"],
                "SBATCH_STDOUT": paths["stdout"],
                "SBATCH_STDERR": paths["stderr"],
            }
            with ExitStack() as stack:
                for name, value in patches.items():
                    stack.enter_context(mock.patch.object(V8, name, value))
                stack.enter_context(
                    mock.patch.object(
                        V8, "_load_launch",
                        return_value=(
                            launch_sha, launch,
                            {"repair_v5_shard_indices": TASKS},
                        ),
                    )
                )
                validate_inventory = stack.enter_context(
                    mock.patch.object(
                        V8.Source, "validate_inventory_manifest",
                        return_value=[{}] * V8.Source.CANDIDATE_COUNT,
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        V8, "_read_v5_reusable_triplets",
                        side_effect=AssertionError("V5 payload opened"),
                    )
                )
                stack.enter_context(
                    mock.patch.object(
                        V8.Runtime, "_v6_output_tree",
                        side_effect=AssertionError("V8 payload opened"),
                    )
                )
                authenticated = R._load_authenticated_launch_materials()

            validate_inventory.assert_called_once_with(inventory)
            self.assertEqual(
                authenticated["source_inventory_record_count"],
                V8.Source.CANDIDATE_COUNT,
            )
            self.assertEqual(len(authenticated["launch_materials"]), 7)
            exposed = R._canonical_json(authenticated["launch_materials"])
            for secret in (
                b"secret-stream-token", b"private warning bytes",
                b"secret-intent-token", b"secret-inventory-value",
            ):
                self.assertNotIn(secret, exposed)


if __name__ == "__main__":
    unittest.main()
