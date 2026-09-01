#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pdb_terminal_incidence_confirmation_a_protocol as P


def _write(path: Path, value: dict) -> bytes:
    raw = P.canonical_json_line(value)
    path.write_bytes(raw)
    return raw


def _task(index: int) -> dict:
    family = "family-{:02d}".format(index % 30)
    directory = "directory-{:02d}".format(index % 60)
    digest = hashlib.sha256("problem-{}".format(index).encode()).hexdigest()
    domain_digest = hashlib.sha256(directory.encode()).hexdigest()
    return {
        "candidate_index": index,
        "directory": directory,
        "family": family,
        "problem": "p{:04d}.pddl".format(index),
        "domain_file": "{}/domain.pddl".format(directory),
        "problem_file": "{}/p{:04d}.pddl".format(directory, index),
        "domain_sha256": domain_digest,
        "problem_sha256": digest,
        "canonical_path": "{}/p{:04d}.pddl".format(directory, index),
        "is_shadow_family": index % 2 == 0,
        "is_shadow_unrepresented": index % 2 == 1,
        "is_all_prior_represented": index % 3 != 0,
        "is_all_prior_unrepresented": index % 3 == 0,
        "aliases": [],
        "selection_role": "confirmation-a",
        "selection_rank_sha256": hashlib.sha256(
            "rank-{}".format(index).encode()
        ).hexdigest(),
        "source_audit_evidence_sha256": hashlib.sha256(
            "evidence-{}".format(index).encode()
        ).hexdigest(),
    }


class SourceFixture:
    def __init__(self, root: Path, **overrides):
        tasks = [_task(index) for index in range(P.COHORT_TASKS)]
        shadow = sorted({
            task["family"] for task in tasks
            if task["is_shadow_unrepresented"]
        })
        all_prior = sorted({
            task["family"] for task in tasks
            if task["is_all_prior_unrepresented"]
        })
        cohort_sha = hashlib.sha256(P.canonical_json_line(tasks)).hexdigest()
        gate = {"passed": True, "clauses": {}}
        schema = P.SOURCE_AUDIT_SCHEMA
        source_inventory_sha = "8" * 64
        code_manifest_sha = "3" * 64
        diagnostic = {
            "schema": schema + "/campaign-v2/v1-infrastructure-diagnostic",
            "rerun_scope": "all-820-shards",
            "reused_v1_shards": 0,
            "successful_shard_contents_used_for_v2_design": False,
            "source_support_outcomes_used_for_v2_design": False,
        }
        self.attestation = root / "attestation.json"
        self.launch = root / "launch.json"
        self.execution = root / "execution.json"
        attestation = {
            "schema": schema,
            "benchmark_revision": P.BENCHMARK_REVISION,
            "translator_source_sha256": "1" * 64,
            "records_sha256": "2" * 64,
            "source_inventory_sha256": source_inventory_sha,
            "code_manifest_sha256": code_manifest_sha,
            "confirmation_prelaunch_authorized": True,
            "prelaunch_gate": gate,
            "split_strata": {
                "shadow_unrepresented": {"families": shadow},
                "all_prior_unrepresented": {"families": all_prior},
            },
            "cohorts": {
                "confirmation_a": {
                    "role": "confirmation-a",
                    "tasks": tasks,
                    "tasks_sha256": cohort_sha,
                },
            },
        }
        attestation_raw = _write(self.attestation, attestation)
        launch = {
            "schema": schema + "/campaign-v2/launch",
            "campaign": "v2",
            "whole_campaign_rerun": True,
            "reused_v1_shards": 0,
            "memory_per_cpu": "256G",
            "partition": "fat",
            "qos": "normal",
            "account": P.ACCOUNT,
            "array": "0-819",
            "array_throttle": 0,
            "array_tasks": 820,
            "tasks_per_array_task": 2,
            "candidates": 1640,
            "cpus_per_task": 1,
            "time_limit": "01:40:00",
            "task_timeout_seconds": 2700,
            "benchmark_revision": P.BENCHMARK_REVISION,
            "job_id": "123456",
            "code_manifest_sha256": code_manifest_sha,
            "source_inventory_sha256": source_inventory_sha,
            "translator_source_sha256": "1" * 64,
            "repository_commit_id": "4" * 40,
            "slurm_script_sha256": "5" * 64,
            "launch_intent_sha256": "6" * 64,
            "v1_failure_diagnostic": diagnostic,
        }
        launch.update(overrides.get("launch", {}))
        launch_raw = _write(self.launch, launch)
        scheduler_rows = [{
            "array_task": index,
            "state": "COMPLETED",
            "exit_code": "0:0",
            "elapsed": "00:01:00",
            "partition": "fat",
        } for index in range(820)]
        execution = {
            "schema": schema + "/campaign-v2/execution",
            "campaign": "v2",
            "whole_campaign_rerun": True,
            "reused_v1_shards": 0,
            "memory_per_cpu": "256G",
            "partition": "fat",
            "array_throttle": 0,
            "shards": 820,
            "candidates": 1640,
            "scheduler_rows": scheduler_rows,
            "scheduler_state_counts": {"COMPLETED": 820},
            "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
            "job_id": "123456",
            "source_audit_complete": True,
            "confirmation_prelaunch_authorized": True,
            "prelaunch_gate": gate,
            "attestation_sha256": hashlib.sha256(attestation_raw).hexdigest(),
            "attestation_records_sha256": "2" * 64,
            "cohort_manifest_sha256": {"confirmation_a": cohort_sha},
            "code_manifest_sha256": code_manifest_sha,
            "source_inventory_sha256": source_inventory_sha,
            "union_tree": {"sha256": "7" * 64},
            "v1_failure_diagnostic": diagnostic,
        }
        execution.update(overrides.get("execution", {}))
        _write(self.execution, execution)

    def load(self):
        return P.load_source_materials(
            self.attestation, self.execution, self.launch
        )

    def freeze(self, path: Path) -> dict:
        materials = self.load()
        value = {
            "schema": P.FREEZE_SCHEMA,
            "source_audit": {
                "attestation_path": self.attestation.relative_to(
                    P.REPO
                ).as_posix(),
                "execution_receipt_path": self.execution.relative_to(
                    P.REPO
                ).as_posix(),
                "launch_receipt_path": self.launch.relative_to(
                    P.REPO
                ).as_posix(),
                "attestation_sha256": materials.attestation_sha256,
                "execution_receipt_sha256": (
                    materials.execution_receipt_sha256
                ),
                "launch_receipt_sha256": materials.launch_receipt_sha256,
                "cohort_manifest_sha256": materials.cohort_manifest_sha256,
                "attestation_records_sha256": materials.records_sha256,
                "translator_source_sha256": (
                    materials.translator_source_sha256
                ),
            },
            "planner": {
                "revision": "a" * 40,
                "cache_name": "synthetic-confirmation-a-cache",
                "build_options": list(P.BUILD_OPTIONS),
                "downward_sha256": "b" * 64,
                "preprocess_sha256": "c" * 64,
                "tree_manifest_sha256": "d" * 64,
            },
            "design": {
                "protocol_sha256": P.sha256_file(P.PROTOCOL_PATH),
                "option_matrix_sha256": P.option_matrix_digest(),
                "cohort_tasks": P.COHORT_TASKS,
                "configs": P.CONFIG_COUNT,
                "cells": P.CELL_COUNT,
                "horizon": P.HORIZON,
                "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
                "bootstrap_seed": P.BOOTSTRAP_SEED,
            },
            "experiment_source_sha256": {
                relative: P.sha256_file(P.REPO / relative)
                for relative in P.EXPERIMENT_SOURCE_FILES
            },
        }
        _write(path, value)
        return value


class ConfirmationAProtocolTest(unittest.TestCase):
    def test_design_and_cegar_bound(self):
        P.validate_protocol_design()
        cegar = P.SEARCHES["pdb_cegar_shadow"]
        self.assertIn("cegar_max_time=infinity", cegar)
        self.assertIn("cegar_max_refinements=128", cegar)
        prose = " ".join(P.PROTOCOL_PATH.read_text().split())
        self.assertIn("at most 128 refinement calls", prose)

    def test_exact_v2_campaign_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            materials = SourceFixture(Path(tmp)).load()
        self.assertEqual(len(materials.tasks), 650)
        self.assertEqual(materials.launch_receipt["memory_per_cpu"], "256G")

    def test_cohort_hash_matches_source_audit_canonical_line_convention(self):
        tasks = [_task(index) for index in range(P.COHORT_TASKS)]
        source_audit_canonical_json = P.canonical_json(tasks) + b"\n"
        self.assertEqual(
            P.canonical_json_line(tasks), source_audit_canonical_json
        )
        self.assertEqual(
            hashlib.sha256(P.canonical_json_line(tasks)).hexdigest(),
            hashlib.sha256(source_audit_canonical_json).hexdigest(),
        )

    def test_v1_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SourceFixture(root)
            launch = json.loads(fixture.launch.read_text())
            launch["schema"] = launch["schema"].replace(
                "/campaign-v2/launch", "/launch"
            )
            launch_raw = _write(fixture.launch, launch)
            execution = json.loads(fixture.execution.read_text())
            execution["schema"] = execution["schema"].replace(
                "/campaign-v2/execution", "/execution"
            )
            execution["launch_receipt_sha256"] = hashlib.sha256(
                launch_raw
            ).hexdigest()
            _write(fixture.execution, execution)
            with self.assertRaisesRegex(P.ProtocolError, "schema chain"):
                fixture.load()

    def test_nonexact_attestation_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            data = json.loads(fixture.attestation.read_text())
            data["schema"] = P.SOURCE_AUDIT_SCHEMA + "-lookalike"
            att_raw = _write(fixture.attestation, data)
            execution = json.loads(fixture.execution.read_text())
            execution["attestation_sha256"] = hashlib.sha256(att_raw).hexdigest()
            _write(fixture.execution, execution)
            with self.assertRaisesRegex(P.ProtocolError, "schema chain"):
                fixture.load()

    def test_mismatched_v1_failure_diagnostic_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            execution = json.loads(fixture.execution.read_text())
            execution["v1_failure_diagnostic"] = {
                **execution["v1_failure_diagnostic"],
                "rerun_scope": "selected-shards",
            }
            _write(fixture.execution, execution)
            with self.assertRaisesRegex(P.ProtocolError, "diagnostic chain"):
                fixture.load()

    def test_non_full_v2_rerun_diagnostic_is_rejected_even_when_matched(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            launch = json.loads(fixture.launch.read_text())
            diagnostic = {
                **launch["v1_failure_diagnostic"],
                "rerun_scope": "selected-shards",
            }
            launch["v1_failure_diagnostic"] = diagnostic
            launch_raw = _write(fixture.launch, launch)
            execution = json.loads(fixture.execution.read_text())
            execution["v1_failure_diagnostic"] = diagnostic
            execution["launch_receipt_sha256"] = hashlib.sha256(
                launch_raw
            ).hexdigest()
            _write(fixture.execution, execution)
            with self.assertRaisesRegex(P.ProtocolError, "diagnostic chain"):
                fixture.load()

    def test_v1_reuse_and_low_memory_are_rejected(self):
        cases = (
            {"launch": {"campaign": "v1"}},
            {"execution": {"campaign": "v1"}},
            {"launch": {"reused_v1_shards": 1}},
            {"execution": {"reused_v1_shards": 1}},
            {"launch": {"whole_campaign_rerun": False}},
            {"execution": {"whole_campaign_rerun": False}},
            {"launch": {"memory_per_cpu": "26G"}},
            {"execution": {"memory_per_cpu": "26G"}},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp), **overrides)
                    with self.assertRaisesRegex(
                        P.ProtocolError, "did not authorize"
                    ):
                        fixture.load()

    def test_v1_diagnostic_must_attest_a_full_outcome_blind_rerun(self):
        cases = (
            ("schema", P.SOURCE_AUDIT_SCHEMA + "/wrong-diagnostic"),
            ("rerun_scope", "selected-shards"),
            ("reused_v1_shards", 1),
            ("successful_shard_contents_used_for_v2_design", True),
            ("source_support_outcomes_used_for_v2_design", True),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp))
                    launch = json.loads(fixture.launch.read_text())
                    diagnostic = {
                        **launch["v1_failure_diagnostic"], field: value,
                    }
                    launch["v1_failure_diagnostic"] = diagnostic
                    launch_raw = _write(fixture.launch, launch)
                    execution = json.loads(fixture.execution.read_text())
                    execution["v1_failure_diagnostic"] = diagnostic
                    execution["launch_receipt_sha256"] = hashlib.sha256(
                        launch_raw
                    ).hexdigest()
                    _write(fixture.execution, execution)
                    with self.assertRaisesRegex(
                        P.ProtocolError, "diagnostic chain"
                    ):
                        fixture.load()

    def test_source_provenance_chain_must_match(self):
        cases = (
            {"launch": {"source_inventory_sha256": "9" * 64}},
            {"execution": {"source_inventory_sha256": "9" * 64}},
            {"launch": {"code_manifest_sha256": "9" * 64}},
            {"execution": {"code_manifest_sha256": "9" * 64}},
            {"execution": {"job_id": "654321"}},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp), **overrides)
                    with self.assertRaisesRegex(
                        P.ProtocolError, "provenance chain"
                    ):
                        fixture.load()

    def test_source_v2_scheduler_contract_is_exact(self):
        cases = (
            {"launch": {"partition": "thin"}},
            {"launch": {"qos": "low"}},
            {"launch": {"array": "0-818"}},
            {"launch": {"array_throttle": 10}},
            {"launch": {"array_tasks": 819}},
            {"launch": {"tasks_per_array_task": 1}},
            {"launch": {"candidates": 1639}},
            {"launch": {"cpus_per_task": 2}},
            {"launch": {"time_limit": "01:00:00"}},
            {"launch": {"task_timeout_seconds": 2600}},
            {"execution": {"partition": "thin"}},
            {"execution": {"array_throttle": 10}},
            {"execution": {"shards": 819}},
            {"execution": {"candidates": 1639}},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp), **overrides)
                    with self.assertRaisesRegex(
                        P.ProtocolError, "scheduler contract"
                    ):
                        fixture.load()

    def test_source_v2_scheduler_row_identity_is_exact(self):
        cases = (
            {"scheduler_rows": []},
            {"scheduler_rows": [{
                "array_task": index,
                "state": "COMPLETED",
                "exit_code": "0:0",
                "elapsed": "00:01:00",
                "partition": "thin" if index == 17 else "fat",
            } for index in range(820)]},
            {"scheduler_rows": [{
                "array_task": 18 if index == 17 else index,
                "state": "COMPLETED",
                "exit_code": "0:0",
                "elapsed": "00:01:00",
                "partition": "fat",
            } for index in range(820)]},
        )
        for execution in cases:
            with self.subTest(first=str(execution)[:80]):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(
                        Path(tmp), execution=execution
                    )
                    with self.assertRaisesRegex(
                        P.ProtocolError, "scheduler rows"
                    ):
                        fixture.load()

    def test_executed_source_manifest_covers_reused_runtime_modules(self):
        self.assertIn(
            "experiments/audit_pdb_terminal_incidence_shadow.py",
            P.EXPERIMENT_SOURCE_FILES,
        )
        self.assertIn(
            "experiments/pdb_terminal_incidence_shadow_protocol.py",
            P.EXPERIMENT_SOURCE_FILES,
        )

    def test_missing_freeze_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(P.ProtocolError):
                P._load_freeze(Path(tmp) / "missing.json")

    def test_synthetic_complete_freeze_is_accepted_and_source_tamper_rejected(self):
        with tempfile.TemporaryDirectory(
            prefix=".confirmation-a-fixture-", dir=P.SCRIPT_DIR
        ) as tmp:
            root = Path(tmp)
            fixture = SourceFixture(root)
            freeze_path = root / "freeze.json"
            value = fixture.freeze(freeze_path)
            freeze, materials = P._load_freeze(freeze_path)
            self.assertEqual(freeze, value)
            self.assertEqual(len(materials.tasks), P.COHORT_TASKS)
            with mock.patch.object(P, "FREEZE_PATH", freeze_path):
                installed = P._installed_values()
            self.assertEqual(
                installed["DIRECTORY_FAMILY_JSON_SHA256"],
                hashlib.sha256(P.canonical_json(
                    materials.directory_to_family
                )).hexdigest(),
            )
            relative = P.EXPERIMENT_SOURCE_FILES[0]
            value["experiment_source_sha256"][relative] = "9" * 64
            _write(freeze_path, value)
            with self.assertRaisesRegex(P.ProtocolError, "source changed"):
                P._load_freeze(freeze_path)

    def test_stratum_flag_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            data = json.loads(fixture.attestation.read_text())
            task = data["cohorts"]["confirmation_a"]["tasks"][0]
            task["is_all_prior_unrepresented"] = not task[
                "is_all_prior_unrepresented"
            ]
            tasks = data["cohorts"]["confirmation_a"]["tasks"]
            data["cohorts"]["confirmation_a"]["tasks_sha256"] = hashlib.sha256(
                P.canonical_json_line(tasks)
            ).hexdigest()
            att_raw = _write(fixture.attestation, data)
            execution = json.loads(fixture.execution.read_text())
            execution["attestation_sha256"] = hashlib.sha256(att_raw).hexdigest()
            execution["cohort_manifest_sha256"]["confirmation_a"] = data[
                "cohorts"
            ]["confirmation_a"]["tasks_sha256"]
            _write(fixture.execution, execution)
            with self.assertRaises(P.ProtocolError):
                fixture.load()


if __name__ == "__main__":
    unittest.main()
