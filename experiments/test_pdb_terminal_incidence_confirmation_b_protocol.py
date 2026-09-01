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
                SOURCE_V3_REPO=self.repo,
                SOURCE_V3_ATTESTATION_PATH=self.attestation,
                SOURCE_V3_ARTIFACT_DIR=self.artifact_dir,
                SOURCE_V3_INTENT_PATH=self.intent,
                SOURCE_V3_LAUNCH_RECEIPT_PATH=self.launch,
                SOURCE_V3_LAUNCH_RECEIPT_SHA256=self.launch_sha,
                SOURCE_V3_EXECUTION_RECEIPT_PATH=self.execution,
                SOURCE_V3_SLURM_PATH=self.slurm,
                SOURCE_V3_CODE_MANIFEST_PATH=self.manifest,
                SOURCE_V3_AMENDMENT_PATH=self.amendment,
                SOURCE_V3_INVENTORY_PATH=self.inventory,
                SOURCE_V3_OUTPUT_DIR=self.output_dir,
                SOURCE_V3_CANDIDATE_PATH=self.candidate,
                SOURCE_V3_SLURM_SHA256=self.slurm_sha,
                SOURCE_V3_CODE_MANIFEST_SHA256=self.manifest_sha,
                SOURCE_V3_AMENDMENT_SHA256=self.amendment_sha,
                SOURCE_V3_INVENTORY_SHA256=self.inventory_sha,
                SOURCE_V3_FIXED_HASHES=self.fixed_hashes,
                SOURCE_V3_V2_DIAGNOSTIC_SHA256=self.v2_diagnostic_sha,
                SOURCE_V3_V2_SCHEDULER_STATE_COUNTS=self.v2_state_counts,
                SOURCE_V3_V2_SCHEDULER_ROWS_SHA256=self.v2_rows_sha,
                SOURCE_V3_V2_FAILURE_LOGS_SHA256=self.v2_logs_sha,
                SOURCE_V3_V1_DIAGNOSTIC_SHA256=self.v1_diagnostic_sha,
                _repository_snapshot_files=lambda commit, relatives: {
                    relative: (self.repo / relative).read_bytes()
                    for relative in relatives
                },
        ):
            yield


class ConfirmationBProtocolTest(unittest.TestCase):
    def test_v3_manifest_contract_has_exact_order_and_cardinality(self):
        self.assertEqual(len(P.SOURCE_V3_MANIFEST_FILES), 14)
        self.assertEqual(len(set(P.SOURCE_V3_MANIFEST_FILES)), 14)
        self.assertEqual(
            P.SOURCE_V3_MANIFEST_FILES[-1],
            "experiments/"
            "test_pdb_terminal_incidence_confirmation_source_audit_v3.py",
        )

    def test_committed_v3_launch_byte_chain_is_accepted(self):
        raw, launch = P._load_canonical(
            P.SOURCE_V3_LAUNCH_RECEIPT_PATH, "v3 launch receipt"
        )
        self.assertEqual(
            hashlib.sha256(raw).hexdigest(),
            P.SOURCE_V3_LAUNCH_RECEIPT_SHA256,
        )
        _, _, manifest = P._load_source_v3_byte_chain(launch)
        self.assertEqual(len(manifest), 14)
        self.assertEqual(
            len(P._source_v3_tracked_file_sha256(launch, manifest)), 18
        )

    def test_v3_local_byte_chain_tampering_is_rejected(self):
        targets = (
            lambda fixture: fixture.intent,
            lambda fixture: fixture.slurm,
            lambda fixture: fixture.manifest,
            lambda fixture: fixture.amendment,
            lambda fixture: fixture.inventory,
            lambda fixture: fixture.repo / P.SOURCE_V3_MANIFEST_FILES[4],
        )
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                path = target(fixture)
                path.write_bytes(path.read_bytes() + b"tamper\n")
                with self.assertRaises(P.ProtocolError):
                    fixture.load()

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

    def test_v3_intent_and_repository_snapshot_are_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            fixture.mutate_intent(lambda intent: intent.update(
                submit_command=["sbatch", "mutated"]
            ))
            with self.assertRaisesRegex(P.ProtocolError, "local byte chain"):
                fixture.load()
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            with fixture.patch():
                scoped = sorted({
                    *P.SOURCE_V3_MANIFEST_FILES,
                    P.SOURCE_V3_SLURM_RELATIVE,
                    P.SOURCE_V3_MANIFEST_RELATIVE,
                })
                snapshot = {
                    relative: (fixture.repo / relative).read_bytes()
                    for relative in scoped
                }
                snapshot[P.SOURCE_V3_MANIFEST_FILES[2]] += b"tamper\n"
                with mock.patch.object(
                    P, "_repository_snapshot_files", return_value=snapshot
                ), self.assertRaisesRegex(P.ProtocolError, "snapshot"):
                    P.load_source_materials(
                        fixture.attestation, fixture.execution, fixture.launch
                    )

    def test_freeze_revision_tracks_all_v3_bound_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            materials = fixture.load()
            with mock.patch.object(Freeze, "REPO", fixture.repo), \
                    mock.patch.object(
                        Freeze.JJ,
                        "tracked_file_sha256",
                        side_effect=lambda repo, revision, relative: (
                            materials.tracked_file_sha256[relative]
                        ),
                    ):
                self.assertEqual(
                    Freeze._tracked_source_v3_hashes(materials, "4" * 40),
                    materials.tracked_file_sha256,
                )
            first = next(iter(materials.tracked_file_sha256))
            with mock.patch.object(Freeze, "REPO", fixture.repo), \
                    mock.patch.object(
                        Freeze.JJ,
                        "tracked_file_sha256",
                        side_effect=lambda repo, revision, relative: (
                            "9" * 64 if relative == first
                            else materials.tracked_file_sha256[relative]
                        ),
                    ), self.assertRaisesRegex(Freeze.FreezeError, "freeze revision"):
                Freeze._tracked_source_v3_hashes(materials, "4" * 40)

    def test_freeze_requires_source_revision_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            materials = SourceFixture(Path(tmp)).load()
        with mock.patch.object(
                Freeze.JJ, "require_ancestor",
                side_effect=Freeze.JJ.JjCacheError("divergent"),
        ), self.assertRaisesRegex(Freeze.FreezeError, "not an ancestor"):
            Freeze._require_source_ancestor(materials, "4" * 40)

    def test_source_snapshot_rechecks_jj_after_each_subprocess(self):
        with mock.patch.object(
                P, "sha256_file",
                side_effect=[P.SOURCE_V3_JJ_EXECUTABLE_SHA256, "9" * 64],
        ), mock.patch.object(
                P.subprocess, "check_output", return_value="file\n"
        ) as query, self.assertRaisesRegex(
                P.ProtocolError, "Jujutsu executable identity"
        ):
            P._repository_snapshot_files("4" * 40, ["file"])
        query.assert_called_once()

    def test_freeze_rechecks_live_bytes_around_revision_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            materials = fixture.load()
            first = next(iter(materials.tracked_file_sha256))
            target = fixture.repo / first
            changed = []

            def mutate_during_lookup(repo, revision, relative):
                if relative == first and not changed:
                    target.write_bytes(target.read_bytes() + b"swap\n")
                    changed.append(True)
                return materials.tracked_file_sha256[relative]

            with mock.patch.object(Freeze, "REPO", fixture.repo), \
                    mock.patch.object(
                        Freeze.JJ, "tracked_file_sha256",
                        side_effect=mutate_during_lookup,
                    ), self.assertRaisesRegex(
                        Freeze.FreezeError, "changed during revision check"
                    ):
                Freeze._tracked_source_v3_hashes(materials, "4" * 40)

    def test_freeze_reloads_source_after_mocked_planner_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))

            def mocked_cache():
                fixture.attestation.write_bytes(
                    fixture.attestation.read_bytes() + b"changed-in-cache\n"
                )

            with fixture.patch(), mock.patch.object(
                    Freeze, "REPO", fixture.repo
            ), mock.patch.object(
                    Freeze, "_require_clean_parent", return_value="4" * 40
            ), mock.patch.object(
                    Freeze, "_require_source_ancestor", return_value=None
            ):
                mocked_cache()
                with self.assertRaises(P.ProtocolError):
                    Freeze._revalidate_before_write(
                        {},
                        attestation=fixture.attestation,
                        execution_receipt=fixture.execution,
                        launch_receipt=fixture.launch,
                        confirmation_a_receipt=P.CONFIRMATION_A_RECEIPT_PATH,
                        confirmation_a_receipt_pin=(
                            P.CONFIRMATION_A_RECEIPT_PIN_PATH
                        ),
                        confirmation_a_first_output=(
                            P.CONFIRMATION_A_FIRST_OUTPUT_PATH
                        ),
                        confirmation_a_second_output=(
                            P.CONFIRMATION_A_SECOND_OUTPUT_PATH
                        ),
                        revision="4" * 40,
                    )

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

    def test_dynamic_cardinality_contract_accepts_200_and_300(self):
        for tasks in (200, 300):
            cells = 9 * tasks
            with mock.patch.multiple(
                P,
                COHORT_TASKS=tasks,
                CELL_COUNT=cells,
                EXPECTED_ARRAY_TASKS=(cells + 2) // 3,
            ):
                P.validate_protocol_design()

    def test_dynamic_cardinality_contract_rejects_out_of_range(self):
        for tasks in (199, 301):
            with mock.patch.multiple(
                P,
                COHORT_TASKS=tasks,
                CELL_COUNT=9 * tasks,
                EXPECTED_ARRAY_TASKS=3 * tasks,
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

    def test_v2_failure_diagnostic_is_identical_and_consistent(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            execution = json.loads(fixture.execution.read_text())
            execution["v2_failure_diagnostic"]["reused_v2_shards"] = 1
            _write(fixture.execution, execution)
            with self.assertRaisesRegex(P.ProtocolError, "diagnostic"):
                fixture.load()

    def test_v2_failure_diagnostic_rejects_self_rehashed_substitution(self):
        def add_failure(intent):
            diagnostic = intent["v2_failure_diagnostic"]
            row = diagnostic["v2_scheduler_rows"][2]
            row["state"] = "FAILED"
            row["exit_code"] = "75:0"
            diagnostic["v2_scheduler_rows_sha256"] = hashlib.sha256(
                P.canonical_json_line(diagnostic["v2_scheduler_rows"])
            ).hexdigest()
            diagnostic["v2_scheduler_state_counts"] = {
                "COMPLETED": 817, "FAILED": 2, "OUT_OF_MEMORY": 1,
            }
            diagnostic["v2_failure_logs"].append({
                "array_task": 2, "state": "FAILED", "sha256": "9" * 64,
            })
            diagnostic["v2_failure_logs_sha256"] = hashlib.sha256(
                P.canonical_json_line(diagnostic["v2_failure_logs"])
            ).hexdigest()

        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            fixture.mutate_intent(add_failure)
            with self.assertRaisesRegex(P.ProtocolError, "diagnostic"):
                fixture.load()
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            fixture.mutate_intent(lambda intent: intent[
                "v2_failure_diagnostic"
            ].update(v2_scheduler_state_counts={"COMPLETED": 820}))
            with self.assertRaisesRegex(P.ProtocolError, "diagnostic"):
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

    def test_unrecovered_source_union_and_tree_are_exact(self):
        def recovery(execution):
            execution["recovery"] = {"unexpected": True}

        def recovered_origin(execution):
            execution["union_sources"][17]["origin"] = "recovery"

        def wrong_source_path(execution):
            execution["union_sources"][17]["source"] = "wrong/shard.json"

        def wrong_union_hash(execution):
            execution["union_sources"][17]["union_sha256"] = "9" * 64

        def boolean_shard_index(execution):
            execution["union_sources"][0]["shard_index"] = False

        def wrong_tree_count(execution):
            execution["union_tree"]["files_count"] = 819

        for mutation in (
            recovery, recovered_origin, wrong_source_path,
            wrong_union_hash, boolean_shard_index, wrong_tree_count,
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

    def test_confirmation_a_authorization_is_linked_to_same_source_chain(self):
        with tempfile.TemporaryDirectory() as tmp:
            materials = SourceFixture(Path(tmp)).load()
        authorization = {
            "benchmark_revision": P.BENCHMARK_REVISION,
            "cost_attestation_sha256": materials.attestation_sha256,
            "source_audit_launch_receipt_sha256": (
                materials.launch_receipt_sha256
            ),
            "source_audit_execution_receipt_sha256": (
                materials.execution_receipt_sha256
            ),
            "confirmation_a_cohort_manifest_sha256": (
                materials.confirmation_a_cohort_manifest_sha256
            ),
        }
        P._validate_confirmation_a_source_link(authorization, materials)
        for field in tuple(authorization):
            with self.subTest(field=field):
                changed = dict(authorization)
                changed[field] = (
                    "wrong" if field == "benchmark_revision" else "9" * 64
                )
                with self.assertRaisesRegex(P.ProtocolError, "not linked"):
                    P._validate_confirmation_a_source_link(changed, materials)

    def test_confirmation_a_authorization_paths_are_fixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaisesRegex(P.ProtocolError, "paths changed"):
                P.load_confirmation_a_authorization(
                    root / "receipt.json", root / "receipt.sha256",
                    root / "analysis.json", root / "repeat.json",
                )

    def test_missing_freeze_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(P.ProtocolError):
                P._load_freeze(Path(tmp) / "missing.json")


if __name__ == "__main__":
    unittest.main()
