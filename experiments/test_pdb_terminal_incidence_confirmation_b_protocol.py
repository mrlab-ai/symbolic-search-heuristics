#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audit_pdb_terminal_incidence_confirmation_sources as SourceAudit
import pdb_terminal_incidence_confirmation_b_protocol as P
import test_pdb_terminal_incidence_confirmation_a_protocol as AFixtures
import freeze_pdb_terminal_incidence_confirmation_b as Freeze


def _write(path: Path, value: dict) -> bytes:
    raw = P.canonical_json_line(value)
    path.write_bytes(raw)
    return raw


def _tree(records: list[dict]) -> dict:
    records = sorted(records, key=lambda record: record["path"])
    digest = hashlib.sha256()
    for record in records:
        digest.update(
            record["path"].encode("ascii") + b"\0"
            + bytes.fromhex(record["sha256"])
        )
    return {
        "sha256": digest.hexdigest(),
        "files_count": len(records),
        "files": records,
    }


def _source_execution_environment():
    cache = (
        "/tmp/symk-confirmation-source-audit-v3-"
        "{array_job_id}-{array_task_id}"
    )
    controlled_path = "/usr/bin:/bin"
    return {
        "submission_export": "NONE",
        "slurm_export": "NONE",
        "unset_variables": ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"],
        "python_no_user_site": "1",
        "python_no_user_site_flag": 1,
        "python_dont_write_bytecode": "1",
        "python_dont_write_bytecode_flag": True,
        "python_pycache_prefix_template": cache,
        "outer_python_flag": "-B",
        "path": controlled_path,
        "translator_child_environment": {
            "PATH": controlled_path,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": cache,
            "PYTHONPATH": str(P.REPO / "src"),
        },
        "python_command": str(
            P.SCRIPT_DIR / "data" / "pdb-terminal-incidence-shadow-venv" /
            "bin" / "python"
        ),
        "python_executable": "/pinned/python3.12",
        "python_executable_sha256": "a" * 64,
        "sha256sum_command": "/usr/bin/sha256sum",
        "sha256sum_executable": "/usr/bin/sha256sum",
        "sha256sum_executable_sha256": "b" * 64,
    }


def _task(index: int, *, guided: bool) -> dict:
    source = (
        AFixtures._guided_task(index)
        if guided else AFixtures._task(index)
    )
    return json.loads(json.dumps(source))


class SourceFixture(AFixtures.SourceFixture):
    def __init__(self, root: Path, *, tasks=300, launch=None, execution=None):
        super().__init__(
            root,
            launch=launch or {},
            execution=execution or {},
        )
        attestation = json.loads(self.attestation.read_text())
        frozen_guided = attestation["cohorts"]["guided_b"]["tasks"]
        if tasks <= len(frozen_guided):
            guided = frozen_guided[:tasks]
        else:
            guided = [*frozen_guided]
            while len(guided) < tasks:
                guided.append(json.loads(json.dumps(frozen_guided[-1])))
        self.asserted_cross_module_bytes = SourceAudit.canonical_json(guided)
        assert self.asserted_cross_module_bytes == P.canonical_json_line(guided)
        if tasks == len(frozen_guided):
            return
        guided_sha = hashlib.sha256(
            self.asserted_cross_module_bytes
        ).hexdigest()
        confirmation = attestation["cohorts"]["confirmation_a"]
        attestation["cohorts"] = {
            "confirmation_a": confirmation,
            "guided_b": {
                "role": "guided-b",
                "top_up_role": "guided-b-topup",
                "target_tasks": 300,
                "max_tasks_per_family": 12,
                "tasks": guided,
                "tasks_sha256": guided_sha,
            },
        }
        shadow = attestation["split_strata"][
            "shadow_unrepresented"
        ]["families"]
        all_prior = attestation["split_strata"][
            "all_prior_unrepresented"
        ]["families"]
        attestation["prelaunch_gate"] = AFixtures._prelaunch_gate(
            confirmation["tasks"], guided, shadow, all_prior
        )
        attestation_raw = _write(self.attestation, attestation)
        execution_value = json.loads(self.execution.read_text())
        execution_value["attestation_sha256"] = hashlib.sha256(
            attestation_raw
        ).hexdigest()
        execution_value["cohort_manifest_sha256"] = {
            "confirmation_a": confirmation["tasks_sha256"],
            "guided_b": guided_sha,
        }
        execution_value["prelaunch_gate"] = attestation["prelaunch_gate"]
        _write(self.execution, execution_value)

    def load(self):
        with self.patch():
            return P.load_source_materials(
                self.attestation, self.execution, self.launch
            )

    @contextlib.contextmanager
    def patch(self):
        with super().patch(), mock.patch.multiple(
                P,
                SOURCE_V4_REPO=self.repo,
                SOURCE_V4_ATTESTATION_PATH=self.attestation,
                SOURCE_V4_ARTIFACT_DIR=self.artifact_dir,
                SOURCE_V4_INTENT_PATH=self.intent,
                SOURCE_V4_LAUNCH_RECEIPT_PATH=self.launch,
                SOURCE_V4_LAUNCH_RECEIPT_SHA256=self.launch_sha,
                SOURCE_V4_LAUNCH_INTENT_SHA256=self.intent_sha,
                SOURCE_V4_EXECUTION_RECEIPT_PATH=self.execution,
                SOURCE_V4_SLURM_PATH=self.slurm,
                SOURCE_V4_CODE_MANIFEST_PATH=self.manifest,
                SOURCE_V4_AMENDMENT_PATH=self.amendment,
                SOURCE_V4_INVENTORY_PATH=self.inventory,
                SOURCE_V4_OUTPUT_DIR=self.output_dir,
                SOURCE_V4_CANDIDATE_PATH=self.candidate,
                SOURCE_V4_SLURM_SHA256=self.slurm_sha,
                SOURCE_V4_CODE_MANIFEST_SHA256=self.manifest_sha,
                SOURCE_V4_AMENDMENT_SHA256=self.amendment_sha,
                SOURCE_V4_INVENTORY_SHA256=self.inventory_sha,
                SOURCE_V4_FIXED_HASHES=self.fixed_hashes,
                SOURCE_V4_V3_DIAGNOSTIC_SHA256=self.diagnostic_sha,
                SOURCE_V4_PRODUCER_COMMIT_ID="4" * 40,
                SOURCE_V4_JOB_ID="123456",
        ):
            yield


class ConfirmationBProtocolTest(unittest.TestCase):
    def test_analysis_v3_consumes_confirmation_a_v4_namespace(self):
        self.assertEqual(
            P.ANALYSIS_PROTOCOL,
            "pdb-terminal-incidence-confirmation-b-analysis-v3",
        )
        self.assertEqual(
            P.CONFIRMATION_A_RECEIPT_PATH.name,
            "analysis-execution-receipt-v4.json",
        )
        self.assertEqual(
            P.CONFIRMATION_A_RECEIPT_PIN_PATH.name,
            "analysis-execution-receipt-v4.sha256",
        )
        self.assertEqual(P.CONFIRMATION_A_FIRST_OUTPUT_PATH.name, "analysis-v4.json")
        self.assertEqual(
            P.CONFIRMATION_A_SECOND_OUTPUT_PATH.name,
            "analysis-v4-repeat.json",
        )

    def test_b_uses_the_v11_adapter_and_8148_planner(self):
        self.assertIn(
            "experiments/pdb_terminal_incidence_confirmation_v11_adapter.py",
            P.EXPERIMENT_SOURCE_FILES,
        )
        self.assertIn(
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v11.py",
            P.EXPERIMENT_SOURCE_FILES,
        )
        self.assertFalse(any(
            "source_consumer_v7" in relative
            for relative in P.EXPERIMENT_SOURCE_FILES
        ))
        self.assertEqual(
            P.PLANNER_REVISION_REQUIRED,
            "8148f798f13059ee881ad2471bd20cdd61d2ec18",
        )

    def test_v4_local_byte_chain_tampering_is_rejected(self):
        targets = (
            lambda fixture: fixture.intent,
            lambda fixture: fixture.slurm,
            lambda fixture: fixture.manifest,
            lambda fixture: fixture.amendment,
            lambda fixture: fixture.inventory,
            lambda fixture: fixture.repo / P.SOURCE_V4_MANIFEST_FILES[4],
        )
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                path = target(fixture)
                path.write_bytes(path.read_bytes() + b"tamper\n")
                with self.assertRaises(P.ProtocolError):
                    fixture.load()

    def test_shared_v4_consumer_constants_cannot_drift(self):
        P._validate_shared_v4_constants()
        with mock.patch.object(P, "SOURCE_V4_JOB_ID", "999999"):
            with self.assertRaisesRegex(P.ProtocolError, "bindings diverged"):
                P._validate_shared_v4_constants()

    def test_symlinked_sealed_source_artifacts_are_rejected(self):
        for attribute in ("attestation", "execution", "launch"):
            with self.subTest(attribute=attribute), \
                    tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                path = getattr(fixture, attribute)
                target = path.with_name(path.name + ".target")
                path.rename(target)
                path.symlink_to(target.name)
                with self.assertRaisesRegex(
                    P.ProtocolError, "canonical regular JSON"
                ):
                    fixture.load()

    def test_v4_intent_and_repository_snapshot_are_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            fixture.mutate_intent(lambda intent: intent.update(
                submit_command=["sbatch", "mutated"]
            ))
            with self.assertRaises(P.ProtocolError):
                fixture.load()

    def test_v4_attestation_and_execution_receipt_are_both_required(self):
        for missing in ("attestation", "execution"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                getattr(fixture, missing).unlink()
                with self.assertRaisesRegex(P.ProtocolError, "cannot load"):
                    fixture.load()
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            with fixture.patch():
                scoped = sorted({
                    *P.SOURCE_V4_MANIFEST_FILES,
                    P.SOURCE_V4_SLURM_RELATIVE,
                    P.SOURCE_V4_MANIFEST_RELATIVE,
                })
                snapshot = {
                    relative: (fixture.repo / relative).read_bytes()
                    for relative in scoped
                }
                snapshot[P.SOURCE_V4_MANIFEST_FILES[2]] += b"tamper\n"
                with mock.patch.object(
                    P.SourceValidation, "_repository_snapshot_files",
                    return_value=snapshot
                ), self.assertRaisesRegex(P.ProtocolError, "snapshot"):
                    P.load_source_materials(
                        fixture.attestation, fixture.execution, fixture.launch
                    )

    def test_freeze_clean_parent_uses_live_working_copy_snapshot(self):
        revision = "4" * 40
        with mock.patch.object(
            Freeze.JJ, "live_working_copy_diff_summary", return_value="",
        ) as live, mock.patch.object(
            Freeze.JJ, "parent_commit", return_value=revision,
        ) as parent:
            self.assertEqual(Freeze._require_clean_parent(None), revision)
        live.assert_called_once_with(Freeze.REPO)
        parent.assert_called_once_with(Freeze.REPO)
        with mock.patch.object(
            Freeze.JJ, "live_working_copy_diff_summary", return_value="M source",
        ), mock.patch.object(
            Freeze.JJ, "parent_commit",
        ) as parent, self.assertRaisesRegex(Freeze.FreezeError, "clean empty"):
            Freeze._require_clean_parent(None)
        parent.assert_not_called()

    def test_source_snapshot_rechecks_jj_after_each_subprocess(self):
        shared = P.SourceValidation
        with mock.patch.object(
                shared, "sha256_file",
                side_effect=[shared.SOURCE_V4_JJ_EXECUTABLE_SHA256, "9" * 64],
        ), mock.patch.object(
                shared.subprocess, "check_output", return_value="file\n"
        ) as query, self.assertRaisesRegex(
                shared.ProtocolError, "Jujutsu executable identity"
        ):
            shared._repository_snapshot_files("4" * 40, ["file"])
        query.assert_called_once()

    def test_freeze_rejects_live_tamper_and_symlink_for_sealed_artifact(self):
        for mutation in ("tamper", "symlink"):
            with self.subTest(mutation=mutation), \
                    tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                materials = fixture.load()
                path = materials.attestation_path
                if mutation == "tamper":
                    path.write_bytes(path.read_bytes() + b"tamper\n")
                else:
                    target = path.with_name(path.name + ".target")
                    path.rename(target)
                    path.symlink_to(target.name)
                with mock.patch.object(Freeze, "REPO", fixture.repo), \
                        self.assertRaises(Freeze.FreezeError):
                    Freeze._attest_tracked_file(
                        path, materials.attestation_sha256, "4" * 40,
                        "sealed source artifact",
                    )

    def test_static_nine_configuration_design(self):
        P.validate_static_design()
        self.assertEqual(len(P.CONFIGS), 9)
        self.assertEqual(P.SEARCHES["blind_fw"], "sym_fw()")
        self.assertFalse(any(
            "shadow_partition=true" in search for _, search in P.CONFIGS
        ))
        self.assertEqual(
            P.NON_GATING_REFERENCE_LABELS,
            (
                "blind_fw", "pdb_bdd_prefix", "pdb_goal_prefix",
                "pdb_goal_fill", "pdb_cegar_deterministic",
                "pdb_exact_width_k32",
            ),
        )
        self.assertIn(
            "pattern_selection=terminal_incidence_guided",
            P.SEARCHES[P.GUIDED_LABEL],
        )
        self.assertIn(
            "pattern_selection=terminal_incidence_matched_control",
            P.SEARCHES[P.MATCHED_LABEL],
        )

    def test_executed_source_manifest_covers_reused_runtime_modules(self):
        self.assertIn(
            "experiments/analyze_pdb_terminal_incidence_shadow.py",
            P.EXPERIMENT_SOURCE_FILES,
        )
        self.assertIn(
            "experiments/pdb_fixed_pattern_parser.py",
            P.EXPERIMENT_SOURCE_FILES,
        )
        self.assertIn(
            "experiments/pdb_cap_selector_parser.py",
            P.EXPERIMENT_SOURCE_FILES,
        )
        self.assertIn(
            "experiments/exp_arrhenius_common.py",
            P.EXPERIMENT_SOURCE_FILES,
        )

    def test_dynamic_cardinality_contract_requires_exactly_300(self):
        tasks = 300
        cells = 9 * tasks
        with mock.patch.multiple(
            P,
            COHORT_TASKS=tasks,
            CELL_COUNT=cells,
            EXPECTED_ARRAY_TASKS=(cells + 2) // 3,
            RUN_CELL_MAPPING_SHA256="a" * 64,
        ):
            P.validate_protocol_design()

    def test_dynamic_cardinality_contract_rejects_out_of_range(self):
        for tasks in (299, 301):
            with mock.patch.multiple(
                P,
                COHORT_TASKS=tasks,
                CELL_COUNT=9 * tasks,
                EXPECTED_ARRAY_TASKS=3 * tasks,
                RUN_CELL_MAPPING_SHA256="a" * 64,
            ):
                with self.assertRaisesRegex(P.ProtocolError, "cardinalities"):
                    P.validate_protocol_design()

    def test_real_source_canonical_hash_convention_is_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            materials = fixture.load()
        self.assertEqual(len(materials.tasks), 300)
        self.assertEqual(
            fixture.asserted_cross_module_bytes,
            P.canonical_json_line(list(materials.tasks)),
        )

    def test_source_scheduler_contract_is_bound(self):
        cases = (
            ({"campaign": "v2"}, None),
            ({"reused_v1_shards": 1}, None),
            ({"reused_v2_shards": 1}, None),
            ({"reused_v2_shards": False}, None),
            ({"memory_per_cpu": "256G"}, None),
            ({"partition": "cpu"}, None),
            ({"qos": "short"}, None),
            ({"account": "other"}, None),
            ({"array": "0-819%10"}, None),
            ({"array_tasks": 819}, None),
            ({"array_throttle": 1}, None),
            ({"array_throttle": False}, None),
            ({"tasks_per_array_task": 1}, None),
            ({"candidates": 1639}, None),
            ({"cpus_per_task": 2}, None),
            ({"cpus_per_task": True}, None),
            ({"time_limit": "01:00:00"}, None),
            ({"task_timeout_seconds": 2600}, None),
            (None, {"partition": "cpu"}),
            (None, {"reused_v2_shards": 1}),
            (None, {"reused_v2_shards": False}),
            (None, {"memory_per_cpu": "256G"}),
            (None, {"array_throttle": 1}),
            (None, {"array_throttle": False}),
            (None, {"shards": 819}),
            (None, {"candidates": 1639}),
        )
        for launch, execution in cases:
            with self.subTest(launch=launch, execution=execution):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(
                        Path(tmp), launch=launch, execution=execution
                    )
                    with self.assertRaises(P.ProtocolError):
                        fixture.load()

    def test_source_scheduler_resource_rows_are_bound(self):
        for field, value in (
            ("array_task", False), ("account", "other"),
            ("partition", "thin"), ("qos", "short"),
            ("req_cpus", True), ("req_mem", "511G"),
            ("time_limit", "04:09:59"), ("state", "FAILED"),
            ("exit_code", "1:0"), ("job_name", "wrong"),
        ):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                execution = json.loads(fixture.execution.read_text())
                execution["scheduler_contract_rows"][0][field] = value
                _write(fixture.execution, execution)
                with self.assertRaisesRegex(P.ProtocolError, "resource accounting"):
                    fixture.load()

    def test_v3_failure_diagnostic_is_identical_and_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            execution = json.loads(fixture.execution.read_text())
            execution["v3_infrastructure_diagnostic"][
                "successful_v3_log_contents_inspected"
            ] = True
            _write(fixture.execution, execution)
            with self.assertRaisesRegex(P.ProtocolError, "diagnostic"):
                fixture.load()

    def test_v3_failure_diagnostic_rejects_self_rehashed_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            fixture.mutate_intent(lambda intent: intent[
                "v3_infrastructure_diagnostic"
            ].update(successful_v3_shard_contents_inspected=True))
            with self.assertRaises(P.ProtocolError):
                fixture.load()

    def test_source_scheduler_rows_and_state_counts_are_bound(self):
        rows = [{
            "array_task": index,
            "state": "COMPLETED",
            "exit_code": "0:0",
            "elapsed": "00:01:00",
            "partition": "fat",
        } for index in range(820)]
        cases = (
            {"scheduler_rows": rows[:-1]},
            {"scheduler_rows": [
                {**row, "array_task": 18 if index == 17 else index}
                for index, row in enumerate(rows)
            ]},
            {"scheduler_rows": [
                {**row, "array_task": False if index == 0 else index}
                for index, row in enumerate(rows)
            ]},
            {"scheduler_rows": [
                {**row, "partition": "thin" if index == 17 else "fat"}
                for index, row in enumerate(rows)
            ]},
            {"scheduler_rows": [
                {**row, "extra": True} if index == 17 else row
                for index, row in enumerate(rows)
            ]},
            {"scheduler_state_counts": {"COMPLETED": 819}},
            {
                "scheduler_rows": [
                    {
                        **row,
                        "state": "FAILED" if index == 17 else "COMPLETED",
                        "exit_code": "1:0" if index == 17 else "0:0",
                    }
                    for index, row in enumerate(rows)
                ],
                "scheduler_state_counts": {"COMPLETED": 819, "FAILED": 1},
            },
        )
        for execution in cases:
            with self.subTest(execution=str(execution)[:100]):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(
                        Path(tmp), execution=execution
                    )
                    with self.assertRaisesRegex(
                        P.ProtocolError, "scheduler rows"
                    ):
                        fixture.load()

    def test_source_execution_environment_is_bound(self):
        changed_export = _source_execution_environment()
        changed_export["submission_export"] = "ALL"
        boolean_flag = _source_execution_environment()
        boolean_flag["python_no_user_site_flag"] = True
        cases = (
            ({"execution_environment": None}, None),
            ({"execution_environment": changed_export}, None),
            ({"execution_environment": boolean_flag}, None),
            ({"python_environment_sha256": "invalid"}, None),
            (None, {"execution_environment": {"unexpected": True}}),
        )
        for launch, execution in cases:
            with self.subTest(launch=launch, execution=execution):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(
                        Path(tmp), launch=launch, execution=execution
                    )
                    with self.assertRaisesRegex(
                        P.ProtocolError, "execution environment"
                    ):
                        fixture.load()

    def test_actual_family_cap_is_enforced(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            attestation = json.loads(fixture.attestation.read_text())
            guided = attestation["cohorts"]["guided_b"]
            for task in guided["tasks"][:13]:
                task["family"] = "family-00"
                task["aliases"][0]["family"] = "family-00"
                task["selection_rank_sha256"] = hashlib.sha256(b"\0".join(
                    value.encode("utf-8") for value in (
                        P.COHORT_SEED, task["selection_role"], task["family"],
                        task["problem_sha256"], task["canonical_path"],
                    )
                )).hexdigest()
            cohort_sha = hashlib.sha256(
                P.canonical_json_line(guided["tasks"])
            ).hexdigest()
            guided["tasks_sha256"] = cohort_sha
            attestation_raw = _write(fixture.attestation, attestation)
            execution = json.loads(fixture.execution.read_text())
            execution["attestation_sha256"] = hashlib.sha256(
                attestation_raw
            ).hexdigest()
            execution["cohort_manifest_sha256"]["guided_b"] = cohort_sha
            _write(fixture.execution, execution)
            with self.assertRaises(P.ProtocolError):
                fixture.load()

    def test_guided_task_schema_rank_aliases_and_candidate_ids_are_exact(self):
        def missing_fields(tasks):
            for field in ("candidate_index", "canonical_path", "aliases"):
                tasks[0].pop(field)

        def boolean_index(tasks):
            tasks[0]["candidate_index"] = False

        def duplicate_index(tasks):
            tasks[1]["candidate_index"] = tasks[0]["candidate_index"]

        def out_of_range_index(tasks):
            tasks[0]["candidate_index"] = 1640

        def inconsistent_shadow_flags(tasks):
            tasks[0]["is_shadow_family"] = not tasks[0]["is_shadow_family"]

        def wrong_rank(tasks):
            tasks[0]["selection_rank_sha256"] = "9" * 64

        def empty_aliases(tasks):
            tasks[0]["aliases"] = []

        for mutation in (
            missing_fields, boolean_index, duplicate_index,
            out_of_range_index, inconsistent_shadow_flags, wrong_rank,
            empty_aliases,
        ):
            with self.subTest(mutation=mutation.__name__), \
                    tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                attestation = json.loads(fixture.attestation.read_text())
                cohort = attestation["cohorts"]["guided_b"]
                mutation(cohort["tasks"])
                cohort_sha = hashlib.sha256(
                    P.canonical_json_line(cohort["tasks"])
                ).hexdigest()
                cohort["tasks_sha256"] = cohort_sha
                attestation_raw = _write(fixture.attestation, attestation)
                execution = json.loads(fixture.execution.read_text())
                execution["attestation_sha256"] = hashlib.sha256(
                    attestation_raw
                ).hexdigest()
                execution["cohort_manifest_sha256"]["guided_b"] = cohort_sha
                _write(fixture.execution, execution)
                with self.assertRaises(P.ProtocolError):
                    fixture.load()

    def test_v4_original_output_and_environment_tree_are_exact(self):
        def recovery(execution):
            execution["recovery"] = {"unexpected": True}

        def wrong_environment_hash(execution):
            execution["task_environment_manifest"]["records"][17][
                "sha256"
            ] = "9" * 64

        def boolean_task_index(execution):
            execution["task_environment_manifest"]["records"][0][
                "array_task"
            ] = False

        def wrong_tree_count(execution):
            execution["original_output_tree"]["files_count"] = 819

        for mutation in (
            recovery, wrong_environment_hash, boolean_task_index,
            wrong_tree_count,
        ):
            with self.subTest(mutation=mutation.__name__):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp))
                    execution = json.loads(fixture.execution.read_text())
                    mutation(execution)
                    _write(fixture.execution, execution)
                    with self.assertRaises(P.ProtocolError):
                        fixture.load()

    def test_source_task_bounds_are_binding(self):
        for tasks in (199, 301):
            with self.subTest(tasks=tasks):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp), tasks=tasks)
                    with self.assertRaises(P.ProtocolError):
                        fixture.load()

    def test_source_a_and_b_overlap_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            attestation = json.loads(fixture.attestation.read_text())
            guided = attestation["cohorts"]["guided_b"]["tasks"]
            confirmation = attestation["cohorts"]["confirmation_a"]["tasks"]
            confirmation[0]["problem_sha256"] = guided[0]["problem_sha256"]
            confirmation_sha = hashlib.sha256(
                P.canonical_json_line(confirmation)
            ).hexdigest()
            attestation["cohorts"]["confirmation_a"][
                "tasks_sha256"
            ] = confirmation_sha
            attestation_raw = _write(fixture.attestation, attestation)
            execution = json.loads(fixture.execution.read_text())
            execution["attestation_sha256"] = hashlib.sha256(
                attestation_raw
            ).hexdigest()
            execution["cohort_manifest_sha256"][
                "confirmation_a"
            ] = confirmation_sha
            _write(fixture.execution, execution)
            with self.assertRaises(P.ProtocolError):
                fixture.load()

    def test_mutated_confirmation_a_cohort_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            attestation = json.loads(fixture.attestation.read_text())
            attestation["cohorts"]["confirmation_a"]["tasks"][0][
                "problem"
            ] = "mutated.pddl"
            attestation_raw = _write(fixture.attestation, attestation)
            execution = json.loads(fixture.execution.read_text())
            execution["attestation_sha256"] = hashlib.sha256(
                attestation_raw
            ).hexdigest()
            _write(fixture.execution, execution)
            with self.assertRaises(P.ProtocolError):
                fixture.load()

    def test_confirmation_a_authorization_paths_are_fixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(P.ProtocolError, "paths changed"):
                P.load_confirmation_a_authorization(
                    root / "receipt.json", root / "receipt.sha256",
                    root / "analysis.json", root / "repeat.json",
                )

    def test_confirmation_a_authorization_recomputes_full_input_provenance(self):
        import analyze_pdb_terminal_incidence_confirmation_a as ConfirmationA

        properties_sha = "1" * 64
        fetch_sha = "2" * 64
        execution_sha = "3" * 64
        hardware = {
            "hardware_attestation_schema": (
                "symbolic-search-heuristics/execution-hardware/v1"
            ),
            "hardware_attestation_files": ConfirmationA.P.CELL_COUNT,
            "hardware_records_sha256": "4" * 64,
            "processor_model_counts": {
                "Synthetic CPU": ConfirmationA.P.CELL_COUNT,
            },
            "architecture_counts": {
                "x86_64": ConfirmationA.P.CELL_COUNT,
            },
        }
        base_analysis = {"guided_study_authorized": True}
        output = {
            **base_analysis,
            "input": {
                "path": str(ConfirmationA.Audit.EVAL_PROPERTIES.resolve()),
                "sha256": properties_sha,
                "fetch_receipt_sha256": fetch_sha,
                "execution_receipt_sha256": execution_sha,
                "hardware": hardware,
            },
        }
        receipt = {
            "first_output_sha256": "5" * 64,
            "second_output_sha256": "5" * 64,
            "input_properties_sha256": properties_sha,
            "fetch_receipt_sha256": fetch_sha,
            "execution_receipt_sha256": execution_sha,
            "hardware": hardware,
            "schema": ConfirmationA.RECEIPT_SCHEMA,
            "analysis_protocol": ConfirmationA.P.ANALYSIS_PROTOCOL,
            "planner_identity": {"revision": "6" * 40},
        }
        with (
            mock.patch.object(
                ConfirmationA,
                "load_analysis_receipt",
                return_value=("7" * 64, receipt, output),
            ),
            mock.patch.object(
                ConfirmationA,
                "_load_sealed_input",
                return_value=(
                    [{"record": 1}], properties_sha, fetch_sha,
                    execution_sha, hardware,
                ),
            ),
            mock.patch.object(
                ConfirmationA,
                "analyze_records",
                return_value=base_analysis,
            ),
            mock.patch.object(
                ConfirmationA.P,
                "v11_run_provenance",
                return_value={
                    "source_audit_campaign": "v11-full-census",
                    "confirmation_a_freeze_sha256": "8" * 64,
                },
            ),
            mock.patch.object(
                ConfirmationA.P,
                "FREEZE_REPOSITORY_REVISION",
                "9" * 40,
            ),
        ):
            authorization = P.load_confirmation_a_authorization(
                P.CONFIRMATION_A_RECEIPT_PATH,
                P.CONFIRMATION_A_RECEIPT_PIN_PATH,
                P.CONFIRMATION_A_FIRST_OUTPUT_PATH,
                P.CONFIRMATION_A_SECOND_OUTPUT_PATH,
            )
        self.assertEqual(
            authorization["execution_receipt_sha256"], execution_sha
        )
        self.assertEqual(authorization["hardware"], hardware)
        self.assertEqual(
            authorization["source_audit_provenance"]["source_audit_campaign"],
            "v11-full-census",
        )

    def test_missing_freeze_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(P.ProtocolError):
                P._load_freeze(Path(tmp) / "missing.json")


if __name__ == "__main__":
    unittest.main()
