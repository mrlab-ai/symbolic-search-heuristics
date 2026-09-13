#!/usr/bin/env python3
"""Adversarial tests for the V11 source-audit seal boundary."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import audit_pdb_terminal_incidence_confirmation_sources_v11 as V11


class V11SealTest(unittest.TestCase):
    def _fixture(self, root: Path):
        artifacts = root / "artifacts"
        output = root / "output"
        temporary = root / "tmp"
        logs = root / "logs"
        for directory in (artifacts, output, temporary, logs):
            directory.mkdir(mode=0o700)
            directory.chmod(0o700)
        paths = {
            "ARTIFACT_DIR": artifacts,
            "DEFAULT_OUTPUT": output,
            "DEFAULT_INVENTORY": output / "source-inventory-v11.json",
            "TMP_ROOT": temporary,
            "LOG_ROOT": logs,
            "LAUNCH_RECEIPT": artifacts / "source-audit-launch-receipt-v11.json",
            "SEAL_PLAN": artifacts / "source-audit-seal-plan-v11.json",
            "TREE_STAGE": artifacts / "source-audit-tree-stage-v11.json",
            "CENSUS_STAGE": artifacts / "source-audit-census-stage-v11.json",
            "SPLIT_STAGE": artifacts / "source-audit-split-stage-v11.json",
            "ATTESTATION_STAGE": artifacts / "source-audit-attestation-stage-v11.json",
            "ATTESTATION": artifacts / "source-audit-attestation-v11.json",
            "EXECUTION_RECEIPT": artifacts / "source-audit-execution-receipt-v11.json",
        }
        return paths

    def _launch(self, paths: dict, job_id: str = "123") -> tuple[dict, str]:
        roots = {
            "artifact_dir": V11._live_launch_root(
                paths["ARTIFACT_DIR"], "fixture artifacts"
            ),
            "log_root": V11._live_launch_root(paths["LOG_ROOT"], "fixture logs"),
            "output_dir": V11._live_launch_root(
                paths["DEFAULT_OUTPUT"], "fixture output"
            ),
            "tmpdir_root": V11._live_launch_root(
                paths["TMP_ROOT"], "fixture tmp"
            ),
        }
        launch = {
            "schema": V11.SCHEMA + "/launch/v1",
            "campaign": "v11-full-census",
            "job_id": job_id,
            "submission_token": "a" * 24,
            "accepted_utc": "2026-09-13T17:00:00+00:00",
            "repository_commit_id": "b" * 40,
            "source_inventory_sha256": "c" * 64,
            "code_manifest_sha256": "d" * 64,
            "launch_intent_sha256": "e" * 64,
            "sbatch_result_sha256": "f" * 64,
            "resource_profile": V11._launch_resource_profile(),
            "root_identities": roots,
            "slurm_program": {
                "template_path": str(V11.SLURM_PROGRAM),
                "template_sha256": "1" * 64,
                "rendered_sha256": "2" * 64,
                "rendered_bytes": 123,
                "submission_mode": "stdin",
                "path_argument": False,
            },
            "launch_recovered": False,
            "recovery_evidence": None,
            "prior_runtime_payloads_read": 0,
            "prior_runtime_payload_bytes_read": 0,
            "prior_runtime_payloads_reused": 0,
            "selective_recovery_authorized": False,
            "whole_campaign_fresh": True,
            "preflight_authorization": {
                "seal_repository_commit_id": "b" * 40,
                "authorization_sha256": "3" * 64,
                "compute_canary_attestation_sha256": "4" * 64,
                "controller_publisher_canary_receipt_sha256": "5" * 64,
                "code_manifest_sha256": "d" * 64,
                "snapshot_consumed": True,
                "full_launch_authorized": True,
            },
        }
        raw = V11.canonical_json(launch)
        paths["LAUNCH_RECEIPT"].write_bytes(raw)
        paths["LAUNCH_RECEIPT"].chmod(0o400)
        return launch, hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _scheduler(job_name: str):
        rows = [{
            "array_task": index,
            "state": "COMPLETED",
            "exit_code": "0:0",
            "partition": "fat",
            "restarts": 0,
        } for index in range(2)]
        contracts = [{
            "array_task": index,
            "account": "naiss2025-5-561-cpu",
            "partition": "fat",
            "qos": "normal",
            "req_cpus": 1,
            "req_mem": "26G",
            "time_limit": "01:10:00",
            "state": "COMPLETED",
            "exit_code": "0:0",
            "restarts": 0,
            "job_name": job_name,
        } for index in range(2)]
        return rows, contracts

    @staticmethod
    def _records():
        return [{
            "candidate_index": index,
            "candidate_origin": "v11-fresh",
            "family": "family-{}".format(index),
            "status": "success",
            "translation_attempted": True,
            "support_determined": True,
            "supported": True,
            "eligible_for_cohort": True,
            "support_exclusion_reasons": [],
            "resource_exclusion_kind": None,
        } for index in range(4)]

    @staticmethod
    def _tree_file(path: Path, relative_path: str) -> dict:
        raw, identity = V11._read_regular(path, "fixture output-tree file")
        return V11._output_tree_file_record(
            relative_path, raw, identity, path.lstat()
        )

    def _run_fixture(self, root: Path, *, failed_row: bool = False):
        paths = self._fixture(root)
        inventory = {"records_sha256": "9" * 64}
        inventory_raw = V11.canonical_json(inventory)
        paths["DEFAULT_INVENTORY"].write_bytes(inventory_raw)
        paths["DEFAULT_INVENTORY"].chmod(0o400)
        for index in range(2):
            shard = paths["DEFAULT_OUTPUT"] / "shard-{:04d}-of-0002".format(index)
            shard.mkdir(mode=0o700)
            shard.chmod(0o500)
        launch, launch_sha = self._launch(paths)
        launch["source_inventory_sha256"] = hashlib.sha256(inventory_raw).hexdigest()
        paths["LAUNCH_RECEIPT"].chmod(0o600)
        launch_raw = V11.canonical_json(launch)
        paths["LAUNCH_RECEIPT"].write_bytes(launch_raw)
        paths["LAUNCH_RECEIPT"].chmod(0o400)
        launch_sha = hashlib.sha256(launch_raw).hexdigest()
        rows, contracts = self._scheduler("pdb-source-v11-" + "a" * 24)
        if failed_row:
            rows[1]["state"] = "FAILED"
            rows[1]["exit_code"] = "1:0"
        records = self._records()
        environment = {
            "manifest_evidence": {"translator_files_sha256": "8" * 64}
        }
        loader = mock.Mock(side_effect=[
            (
                records[0:2], copy.deepcopy(environment),
                [{
                    "path": "shard-0000-of-0002/result.json",
                    "device": 1,
                    "inode": 10,
                    "uid": 1,
                    "gid": 1,
                    "mode": "0400",
                    "nlink": 1,
                    "bytes": 1,
                    "sha256": "3" * 64,
                }],
                V11._output_tree_directory_record(
                    "shard-0000-of-0002",
                    (paths["DEFAULT_OUTPUT"] / "shard-0000-of-0002").lstat(),
                ),
            ),
            (
                records[2:4], copy.deepcopy(environment),
                [{
                    "path": "shard-0001-of-0002/result.json",
                    "device": 1,
                    "inode": 11,
                    "uid": 1,
                    "gid": 1,
                    "mode": "0400",
                    "nlink": 1,
                    "bytes": 1,
                    "sha256": "4" * 64,
                }],
                V11._output_tree_directory_record(
                    "shard-0001-of-0002",
                    (paths["DEFAULT_OUTPUT"] / "shard-0001-of-0002").lstat(),
                ),
            ),
        ])
        gate = {
            "passed": True,
            "cohort_disjointness": {"passed": True},
        }
        cohorts = {
            "confirmation_a": {"candidate_indices": [0]},
            "guided_b": {"candidate_indices": [1]},
        }
        patches = {
            **paths,
            "ARRAY_TASKS": 2,
            "CANDIDATE_COUNT": 4,
        }
        with ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(V11, name, value))
            stack.enter_context(mock.patch.object(
                V11, "validate_inventory_manifest", return_value=[{}] * 4,
            ))
            stack.enter_context(mock.patch.object(
                V11, "_load_shard_directory", loader,
            ))
            stack.enter_context(mock.patch.object(
                V11, "split_supported", return_value=(gate, cohorts),
            ))
            stack.enter_context(mock.patch.object(V11, "_verify_output_tree_stable"))
            if failed_row:
                with self.assertRaisesRegex(V11.SourceAuditError, "scheduler"):
                    V11.seal_campaign(
                        launch_sha=launch_sha,
                        launch_receipt=launch,
                        scheduler_rows=rows,
                        scheduler_contract_rows=contracts,
                        scheduler_terminal_receipt_sha256="6" * 64,
                        terminal_poll_receipt_sha256="7" * 64,
                    )
                self.assertFalse(paths["SEAL_PLAN"].exists())
                loader.assert_not_called()
                return paths, None

            def require_plan(*args, **kwargs):
                self.assertTrue(paths["SEAL_PLAN"].exists())
                return loader(*args, **kwargs)

            with mock.patch.object(V11, "_load_shard_directory", side_effect=require_plan):
                summary = V11.seal_campaign(
                    launch_sha=launch_sha,
                    launch_receipt=launch,
                    scheduler_rows=rows,
                    scheduler_contract_rows=contracts,
                    scheduler_terminal_receipt_sha256="6" * 64,
                    terminal_poll_receipt_sha256="7" * 64,
                )
        return paths, summary

    def test_scheduler_failure_prevents_plan_and_all_payload_reads(self):
        with tempfile.TemporaryDirectory(prefix="v11-seal-failed-") as tmp:
            self._run_fixture(Path(tmp), failed_row=True)

    def test_seal_is_five_stage_hash_chain_and_gate_precedes_payload(self):
        with tempfile.TemporaryDirectory(prefix="v11-seal-pass-") as tmp:
            paths, summary = self._run_fixture(Path(tmp))
            self.assertTrue(summary["confirmation_prelaunch_authorized"])
            plan = json.loads(paths["SEAL_PLAN"].read_bytes())
            execution = json.loads(paths["EXECUTION_RECEIPT"].read_bytes())
            attestation = json.loads(paths["ATTESTATION"].read_bytes())
            self.assertTrue(plan["scheduler_gate_passed_before_payload_read"])
            self.assertNotIn("output_tree_sha256", plan)
            self.assertEqual(plan["log_payloads_read"], 0)
            self.assertEqual(plan["prior_runtime_payloads_read"], 0)
            self.assertEqual(
                execution["seal_recovery_protocol"],
                "exclusive-five-stage-hash-chain-v1",
            )
            self.assertEqual(
                execution["attestation_sha256"],
                hashlib.sha256(paths["ATTESTATION"].read_bytes()).hexdigest(),
            )
            self.assertEqual(
                attestation["translator_source_sha256"], "8" * 64
            )
            self.assertEqual(
                attestation["split_role_labels"], {
                    "confirmation_a": V11.CONFIRMATION_ROLE,
                    "guided_b_base": V11.GUIDED_ROLE,
                    "guided_b_top_up": V11.GUIDED_TOP_UP_ROLE,
                },
            )
            for path in (
                paths["SEAL_PLAN"], paths["TREE_STAGE"],
                paths["CENSUS_STAGE"], paths["SPLIT_STAGE"],
                paths["ATTESTATION_STAGE"], paths["ATTESTATION"],
                paths["EXECUTION_RECEIPT"],
            ):
                self.assertEqual(path.stat().st_mode & 0o777, 0o400)

    def test_scheduler_contract_job_name_is_token_bound(self):
        launch = {"submission_token": "a" * 24}
        rows, contracts = self._scheduler("unbound")
        with (
            mock.patch.object(V11, "ARRAY_TASKS", 2),
            self.assertRaisesRegex(V11.SourceAuditError, "scheduler"),
        ):
            V11._validate_scheduler_evidence(launch, rows, contracts)

    def test_launch_hash_and_every_root_identity_are_bound(self):
        with tempfile.TemporaryDirectory(prefix="v11-launch-bind-") as tmp:
            paths = self._fixture(Path(tmp))
            launch, launch_sha = self._launch(paths)
            with ExitStack() as stack:
                for name, value in paths.items():
                    stack.enter_context(mock.patch.object(V11, name, value))
                with self.assertRaisesRegex(V11.SourceAuditError, "receipt"):
                    V11._validate_launch_receipt("0" * 64, launch)

                moved = Path(tmp) / "old-output"
                paths["DEFAULT_OUTPUT"].rename(moved)
                paths["DEFAULT_OUTPUT"].mkdir(mode=0o700)
                paths["DEFAULT_OUTPUT"].chmod(0o700)
                with self.assertRaisesRegex(V11.SourceAuditError, "root"):
                    V11._validate_launch_receipt(launch_sha, launch)

    def test_launch_acceptance_timestamp_is_exact_canonical_utc(self):
        with tempfile.TemporaryDirectory(prefix="v11-launch-time-") as tmp:
            paths = self._fixture(Path(tmp))
            launch, _launch_sha = self._launch(paths)
            for invalid in (
                None,
                "2026-09-13T17:00:00",
                "2026-09-13T18:00:00+01:00",
                "2026-09-13T17:00:00.000+00:00",
            ):
                with self.subTest(invalid=invalid):
                    changed = copy.deepcopy(launch)
                    changed["accepted_utc"] = invalid
                    raw = V11.canonical_json(changed)
                    paths["LAUNCH_RECEIPT"].chmod(0o600)
                    paths["LAUNCH_RECEIPT"].write_bytes(raw)
                    paths["LAUNCH_RECEIPT"].chmod(0o400)
                    with ExitStack() as stack:
                        for name, value in paths.items():
                            stack.enter_context(mock.patch.object(V11, name, value))
                        with self.assertRaisesRegex(
                            V11.SourceAuditError, "timestamp"
                        ):
                            V11._validate_launch_receipt(
                                hashlib.sha256(raw).hexdigest(), changed
                            )

    def test_output_tree_second_pass_detects_byte_and_mode_mutation(self):
        with tempfile.TemporaryDirectory(prefix="v11-tree-bind-") as tmp:
            paths = self._fixture(Path(tmp))
            shard = paths["DEFAULT_OUTPUT"] / "shard-0000-of-0001"
            shard.mkdir(mode=0o700)
            inventory = paths["DEFAULT_OUTPUT"] / "source-inventory-v11.json"
            inventory.write_bytes(b"inventory")
            inventory.chmod(0o400)
            payload = shard / "result.json"
            payload.write_bytes(b"result")
            payload.chmod(0o400)
            shard.chmod(0o500)
            root_identity = V11._live_launch_root(
                paths["DEFAULT_OUTPUT"], "fixture output"
            )
            launch = {"root_identities": {"output_dir": root_identity}}
            directories = [V11._output_tree_directory_record(
                shard.name, shard.lstat()
            )]
            files = [
                self._tree_file(inventory, "source-inventory-v11.json"),
                self._tree_file(payload, shard.name + "/result.json"),
            ]
            tree = {
                "directories": directories,
                "files": files,
            }
            with (
                mock.patch.object(V11, "DEFAULT_OUTPUT", paths["DEFAULT_OUTPUT"]),
                mock.patch.object(V11, "ARRAY_TASKS", 1),
            ):
                V11._verify_output_tree_stable(tree, launch)
                payload.chmod(0o600)
                with self.assertRaisesRegex(V11.SourceAuditError, "file"):
                    V11._verify_output_tree_stable(tree, launch)

    def test_output_tree_second_pass_detects_same_byte_directory_swap(self):
        with tempfile.TemporaryDirectory(prefix="v11-tree-dir-swap-") as tmp:
            root = Path(tmp)
            paths = self._fixture(root)
            shard = paths["DEFAULT_OUTPUT"] / "shard-0000-of-0001"
            shard.mkdir(mode=0o700)
            payload = shard / "result.json"
            payload.write_bytes(b"result")
            payload.chmod(0o400)
            shard.chmod(0o500)
            inventory = paths["DEFAULT_OUTPUT"] / "source-inventory-v11.json"
            inventory.write_bytes(b"inventory")
            inventory.chmod(0o400)
            tree = {
                "directories": [V11._output_tree_directory_record(
                    shard.name, shard.lstat()
                )],
                "files": [
                    self._tree_file(inventory, "source-inventory-v11.json"),
                    self._tree_file(payload, shard.name + "/result.json"),
                ],
            }
            launch = {"root_identities": {"output_dir": V11._live_launch_root(
                paths["DEFAULT_OUTPUT"], "fixture output"
            )}}
            shard.chmod(0o700)
            shard.rename(root / "replaced-shard")
            shard.mkdir(mode=0o700)
            replacement = shard / "result.json"
            replacement.write_bytes(b"result")
            replacement.chmod(0o400)
            shard.chmod(0o500)
            with (
                mock.patch.object(V11, "DEFAULT_OUTPUT", paths["DEFAULT_OUTPUT"]),
                mock.patch.object(V11, "ARRAY_TASKS", 1),
                self.assertRaisesRegex(V11.SourceAuditError, "directory"),
            ):
                V11._verify_output_tree_stable(tree, launch)

    def test_output_tree_second_pass_detects_same_byte_file_swap(self):
        with tempfile.TemporaryDirectory(prefix="v11-tree-file-swap-") as tmp:
            paths = self._fixture(Path(tmp))
            shard = paths["DEFAULT_OUTPUT"] / "shard-0000-of-0001"
            shard.mkdir(mode=0o700)
            payload = shard / "result.json"
            payload.write_bytes(b"result")
            payload.chmod(0o400)
            shard.chmod(0o500)
            inventory = paths["DEFAULT_OUTPUT"] / "source-inventory-v11.json"
            inventory.write_bytes(b"inventory")
            inventory.chmod(0o400)
            tree = {
                "directories": [V11._output_tree_directory_record(
                    shard.name, shard.lstat()
                )],
                "files": [
                    self._tree_file(inventory, "source-inventory-v11.json"),
                    self._tree_file(payload, shard.name + "/result.json"),
                ],
            }
            launch = {"root_identities": {"output_dir": V11._live_launch_root(
                paths["DEFAULT_OUTPUT"], "fixture output"
            )}}
            shard.chmod(0o700)
            payload.unlink()
            payload.write_bytes(b"result")
            payload.chmod(0o400)
            shard.chmod(0o500)
            with (
                mock.patch.object(V11, "DEFAULT_OUTPUT", paths["DEFAULT_OUTPUT"]),
                mock.patch.object(V11, "ARRAY_TASKS", 1),
                self.assertRaisesRegex(V11.SourceAuditError, "file"),
            ):
                V11._verify_output_tree_stable(tree, launch)

    def test_seal_prefix_cannot_skip_or_mutate_a_stage(self):
        with tempfile.TemporaryDirectory(prefix="v11-seal-prefix-") as tmp:
            paths = self._fixture(Path(tmp))
            paths["TREE_STAGE"].write_bytes(V11.canonical_json({"bad": True}))
            paths["TREE_STAGE"].chmod(0o400)
            with ExitStack() as stack:
                for name, value in paths.items():
                    stack.enter_context(mock.patch.object(V11, name, value))
                with self.assertRaisesRegex(V11.SourceAuditError, "not a prefix"):
                    V11._existing_seal_prefix_is_valid()


if __name__ == "__main__":
    unittest.main()
