#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import unittest
from types import SimpleNamespace
from unittest import mock

import pdb_terminal_metric_choice_calibration as Calibration
import pdb_terminal_metric_choice_protocol as P


SHA = "a" * 64


def fake_tasks():
    return [
        {
            "directory": "domain-{:03d}".format(index // 10),
            "problem": "p{:03d}.pddl".format(index),
            "family": "family-{:02d}".format(index // 10),
            "domain_file": "benchmarks/d{:03d}/domain.pddl".format(index),
            "problem_file": "benchmarks/d{:03d}/p.pddl".format(index),
            "domain_sha256": "b" * 64,
            "problem_sha256": "c" * 64,
        }
        for index in range(P.COHORT_TASKS)
    ]


def fake_snapshot():
    tasks = fake_tasks()
    tasks_sha = P.cohort_digest(tasks)
    planner = fake_planner()
    base_source_files = P.BASE_B_EXPERIMENT_SOURCE_FILES
    v6_tracked = {relative: "4" * 64 for relative in P.V6_SCOPED_FILES}
    v6_tracked[P.V6_CODE_MANIFEST_PATH.relative_to(P.REPO).as_posix()] = (
        "1" * 64
    )
    v6_tracked[P.V6_SLURM_PATH.relative_to(P.REPO).as_posix()] = "3" * 64
    v6_tracked[P.V6_DIAGNOSTIC_PATH.relative_to(P.REPO).as_posix()] = "7" * 64
    return {
        "schema": P.BASE_SNAPSHOT_SCHEMA,
        "base_b_freeze_path": P.BASE_B_FREEZE_PATH.relative_to(P.REPO).as_posix(),
        "base_b_freeze_sha256": "1" * 64,
        "base_b_freeze_repository_revision": "1" * 40,
        "base_b_experiment_source_sha256": {
            relative: v6_tracked.get(relative, SHA)
            for relative in base_source_files
        },
        "base_b_planner": P.planner_identity(planner),
        "benchmark_revision": "2" * 40,
        "confirmation_a_authorization": {
            "guided_study_authorized": True,
            "receipt_sha256": "3" * 64,
            "first_output_sha256": "4" * 64,
            "second_output_sha256": "5" * 64,
            "input_properties_sha256": "6" * 64,
            "fetch_receipt_sha256": "7" * 64,
            "execution_receipt_sha256": "0" * 64,
            "hardware": {
                "hardware_attestation_schema": (
                    "symbolic-search-heuristics/execution-hardware/v1"
                ),
                "hardware_attestation_files": P.BASE_A_CELL_COUNT,
                "hardware_records_sha256": "1" * 64,
                "processor_model_counts": {
                    "Synthetic CPU": P.BASE_A_CELL_COUNT,
                },
                "architecture_counts": {
                    "x86_64": P.BASE_A_CELL_COUNT,
                },
            },
            "receipt_schema": P.BASE_A_RECEIPT_SCHEMA,
            "analysis_protocol": P.BASE_A_ANALYSIS_PROTOCOL,
            "benchmark_revision": "2" * 40,
            "cost_attestation_sha256": "8" * 64,
            "source_audit_launch_receipt_sha256": "9" * 64,
            "source_audit_execution_receipt_sha256": "a" * 64,
            "receipt_path": P.BASE_A_RECEIPT_PATH.relative_to(P.REPO).as_posix(),
            "receipt_pin_path": P.BASE_A_RECEIPT_PIN_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "first_output_path": P.BASE_A_FIRST_OUTPUT_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "second_output_path": P.BASE_A_SECOND_OUTPUT_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "confirmation_a_cohort_manifest_sha256": "f" * 64,
            "planner_identity": P.planner_identity(planner),
        },
        "source_audit_v6": {
            "campaign": "v6-selective-repair",
            "attestation_path": P.V6_ATTESTATION_PATH.relative_to(P.REPO).as_posix(),
            "terminal_diagnostic_path": P.V6_DIAGNOSTIC_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "execution_receipt_path": P.V6_EXECUTION_RECEIPT_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "launch_receipt_path": P.V6_LAUNCH_RECEIPT_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "launch_intent_path": P.V6_INTENT_PATH.relative_to(P.REPO).as_posix(),
            "attestation_sha256": "8" * 64,
            "terminal_diagnostic_sha256": "7" * 64,
            "execution_receipt_sha256": "a" * 64,
            "launch_receipt_sha256": "9" * 64,
            "launch_intent_sha256": "b" * 64,
            "cohort_manifest_sha256": tasks_sha,
            "confirmation_a_cohort_manifest_sha256": "f" * 64,
            "attestation_records_sha256": "d" * 64,
            "translator_source_sha256": "e" * 64,
            "job_id": "12345", "code_manifest_sha256": "1" * 64,
            "repository_commit_id": "3" * 40,
            "union_tree_sha256": "2" * 64,
            "union_sources_sha256": "5" * 64,
            "v6_output_tree_sha256": "6" * 64,
            "v5_launch_receipt_sha256": "7" * 64,
            "v5_code_manifest_sha256": "0" * 64,
            "slurm_template_sha256": "3" * 64,
            "seal_recovery_protocol": (
                "deterministic-exclusive-hash-chain-v1"
            ),
            "pre_diagnosis_repository_commit_id": "4" * 40,
            "pre_diagnosis_files_sha256": "4" * 64,
            "seal_plan_path": P.V6_SEAL_PLAN_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "seal_plan_sha256": "5" * 64,
            "union_root_stage_path": P.V6_UNION_ROOT_STAGE_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "union_root_stage_sha256": "6" * 64,
            "union_stage_path": P.V6_UNION_STAGE_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "union_stage_sha256": "7" * 64,
            "candidate_stage_path": P.V6_CANDIDATE_STAGE_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "candidate_stage_sha256": "8" * 64,
            "attestation_stage_path": P.V6_ATTESTATION_STAGE_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "attestation_stage_sha256": "9" * 64,
            "tracked_file_sha256": v6_tracked,
        },
        "confirmation_a_cohort": {
            "role": "confirmation-a", "full_tasks_sha256": "f" * 64,
            "identities": [{
                "directory": "confirmation-a-domain",
                "problem": "confirmation-a-problem.pddl",
                "domain_sha256": "d" * 64,
                "problem_sha256": "e" * 64,
            }],
            "identities_sha256": hashlib.sha256(P.canonical_json([{
                "directory": "confirmation-a-domain",
                "problem": "confirmation-a-problem.pddl",
                "domain_sha256": "d" * 64,
                "problem_sha256": "e" * 64,
            }])).hexdigest(),
        },
        "cohort": {
            "role": "source-disjoint-universal-confirmation-b",
            "tasks": tasks, "tasks_sha256": tasks_sha,
            "task_name_sha256": P.task_name_digest(tasks),
        },
    }


def fake_calibration(planner=None):
    rows = []
    for task_id, _ in P.CALIBRATION_TASK_SPECS:
        for mode in P.MODES:
            row = {"task_id": task_id, "mode": mode, "trace_status": "complete",
                   "probe_completed_layers": 16}
            for field in Calibration.EXPOSED_FIELDS:
                if field not in row:
                    if field.endswith("before_kb"):
                        row[field] = 100
                    elif field.endswith("after_kb"):
                        row[field] = 105
                    elif field.endswith("delta_kb"):
                        row[field] = 5
                    else:
                        row[field] = 0.1
            rows.append(row)
    return Calibration.build_receipt(rows, planner or fake_planner())


def fake_planner():
    return {
        "schema": P.PLANNER_MANIFEST_SCHEMA,
        "revision": P.REQUIRED_PLANNER_REVISION,
        "selector_base_revision": P.REQUIRED_SELECTOR_COMMIT,
        "cache_name": "dual-selector-ccc93bed",
        "downward_sha256": "1" * 64,
        "preprocess_sha256": "2" * 64,
        "tree_manifest_sha256": "3" * 64,
        "build_options": list(P.BUILD_OPTIONS),
        "driver_path": "fast-downward.py", "driver_sha256": "4" * 64,
        "downward_path": "builds/release_no_lp/bin/downward",
        "preprocess_path": "builds/release_no_lp/bin/preprocess",
        "option_matrix_sha256": P.option_matrix_digest(),
        "searches": [
            {"mode": mode, "search": P.SEARCHES[mode]} for mode in P.MODES
        ],
        "dual_trace_schema": P.DUAL_TRACE_SCHEMA,
    }


def fake_standalone(snapshot=None):
    snapshot = snapshot or fake_snapshot()
    pool = [
        {"pattern_index": 0, "sources": ["empty"], "pattern": [],
         "abstract_states": 1, "within_state_budget": True},
        {"pattern_index": 1, "sources": ["bdd_prefix"], "pattern": [0],
         "abstract_states": 2, "within_state_budget": True},
        {"pattern_index": 2, "sources": ["goal_prefix"], "pattern": [1],
         "abstract_states": 100001, "within_state_budget": False},
        {"pattern_index": 3, "sources": ["goal_fill"], "pattern": [2],
         "abstract_states": 100001, "within_state_budget": False},
        {"pattern_index": 4, "sources": ["cegar"], "pattern": [3],
         "abstract_states": 100001, "within_state_budget": False},
    ]
    pool_sha = hashlib.sha256(P.canonical_json(pool)).hexdigest()
    representatives = [{
        "pattern_index": 0, "sources": ["empty"], "pattern": [],
        "value_cap": None, "initial_dead_end": False, "initial_h": 0,
        "finite_sum": 0, "finite_count": 1, "dead_count": 0,
        "abstract_states": 1, "cofactor_width": 1,
        "reference_feasible": True,
    }, {
        "pattern_index": 1, "sources": ["bdd_prefix"], "pattern": [0],
        "value_cap": 0, "initial_dead_end": False, "initial_h": 0,
        "finite_sum": 0, "finite_count": 2, "dead_count": 0,
        "abstract_states": 2, "cofactor_width": 1,
        "reference_feasible": True,
    }]
    records = [{
        "domain": row["directory"], "problem": row["problem"],
        "family": row["family"],
        "reference_identity": {
            "pattern_index": 0, "sources": ["empty"], "pattern": [],
            "value_cap": None,
        },
        "reference_representatives": representatives,
        "reference_representatives_sha256": hashlib.sha256(
            P.canonical_json(representatives)
        ).hexdigest(),
        "normalized_pool": pool, "normalized_pool_sha256": pool_sha,
    } for row in snapshot["cohort"]["tasks"]]
    return {
        "schema": P.STANDALONE_SCHEMA,
        "base_b_freeze_sha256": snapshot["base_b_freeze_sha256"],
        "cohort_manifest_sha256": snapshot["cohort"]["tasks_sha256"],
        "producer": {
            "planner_manifest": fake_planner(),
            "planner_manifest_sha256": hashlib.sha256(
                P.canonical_json_line(fake_planner())
            ).hexdigest(),
            "option_matrix_sha256": P.option_matrix_digest(),
            "reference_rule": (
                "strongest-K32-feasible-cap-per-pattern-then-score-v1"
            ),
        },
        "sealed_b_input": fake_standalone_source_binding(),
        "records": records,
        "records_sha256": hashlib.sha256(P.canonical_json(records)).hexdigest(),
    }


def fake_standalone_source_binding():
    return {
        "parse_receipt_path": P.BASE_B_PARSE_RECEIPT_PATH.relative_to(
            P.REPO
        ).as_posix(),
        "parse_receipt_sha256": "5" * 64,
        "fetch_receipt_path": P.BASE_B_FETCH_RECEIPT_PATH.relative_to(
            P.REPO
        ).as_posix(),
        "fetch_receipt_sha256": "6" * 64,
        "properties_path": P.BASE_B_PROPERTIES_PATH.relative_to(P.REPO).as_posix(),
        "properties_sha256": "7" * 64,
    }


def fake_freeze():
    snapshot = fake_snapshot()
    calibration = fake_calibration()
    standalone = fake_standalone(snapshot)
    return P.build_freeze(
        freeze_repository_revision="4" * 40,
        base_snapshot=snapshot, calibration_receipt=calibration,
        calibration_receipt_path=P.CALIBRATION_RECEIPT_PATH.relative_to(
            P.REPO
        ).as_posix(),
        calibration_receipt_sha256=hashlib.sha256(
            P.canonical_json_line(calibration)
        ).hexdigest(),
        planner_manifest=fake_planner(), standalone_evidence=standalone,
        standalone_evidence_path=P.STANDALONE_K32_PATH.relative_to(
            P.REPO
        ).as_posix(),
        standalone_evidence_sha256=hashlib.sha256(
            P.canonical_json_line(standalone)
        ).hexdigest(),
        source_hashes={path: SHA for path in P.SOURCE_FILES},
        scheduler_time_limit="01:40:00", scheduler_memory="26G",
    )


class ProtocolTest(unittest.TestCase):
    def test_static_design_pins_base_a_cell_count(self):
        with mock.patch.object(P, "BASE_A_CELL_COUNT", 2599):
            with self.assertRaisesRegex(P.ProtocolError, "static design changed"):
                P.validate_static_design()

    def test_analysis_v4_consumes_confirmation_a_v4_namespace(self):
        self.assertEqual(
            P.ANALYSIS_PROTOCOL,
            "pdb-terminal-metric-choice-analysis-v4",
        )
        self.assertEqual(
            P.BASE_A_RECEIPT_PATH.name, "analysis-execution-receipt-v4.json"
        )
        self.assertEqual(
            P.BASE_A_RECEIPT_PIN_PATH.name,
            "analysis-execution-receipt-v4.sha256",
        )
        self.assertEqual(P.BASE_A_FIRST_OUTPUT_PATH.name, "analysis-v4.json")
        self.assertEqual(P.BASE_A_SECOND_OUTPUT_PATH.name, "analysis-v4-repeat.json")

    def test_exact_task_major_cyclic_triads(self):
        tasks = fake_tasks()
        rows = P.task_major_cell_mapping(tasks)
        self.assertEqual(len(rows), 900)
        self.assertEqual({row["array_task"] for row in rows}, set(range(1, 301)))
        for task in range(1, 301):
            triad = [row for row in rows if row["array_task"] == task]
            self.assertEqual([row["run_id"] for row in triad], list(P.triad_cells(task)))
            self.assertEqual(set(row["algorithm"] for row in triad), set(P.MODES))
        family_zero = [row for row in rows if row["family"] == "family-00"]
        starts = [
            row["algorithm"] for row in family_zero if row["triad_position"] == 0
        ]
        self.assertEqual(starts[:4], [P.MODES[0], P.MODES[1], P.MODES[2], P.MODES[0]])

    def test_freeze_binds_all_inputs(self):
        freeze = fake_freeze()
        P.validate_freeze(freeze, verify_live_sources=False)
        self.assertEqual(freeze["design"]["cell_count"], 900)
        self.assertEqual(freeze["design"]["array_throttle"], 0)
        mutated = copy.deepcopy(freeze)
        mutated["planner"]["selector_base_revision"] = "0" * 40
        with self.assertRaises(P.ProtocolError):
            P.validate_freeze(mutated, verify_live_sources=False)

    def test_requires_a_authorization(self):
        snapshot = fake_snapshot()
        snapshot["confirmation_a_authorization"]["guided_study_authorized"] = False
        with self.assertRaisesRegex(P.ProtocolError, "does not authorize"):
            P.validate_base_snapshot(snapshot)

    def test_requires_exact_a_v4_authorization_metadata(self):
        mutations = {
            "receipt_schema": P.BASE_A_RECEIPT_SCHEMA.replace("/v4/", "/v2/"),
            "analysis_protocol": P.BASE_A_ANALYSIS_PROTOCOL.replace("v4", "v2"),
        }
        for field, value in mutations.items():
            snapshot = fake_snapshot()
            snapshot["confirmation_a_authorization"][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(
                P.ProtocolError, "authorization metadata"
            ):
                P.validate_base_snapshot(snapshot)

    def test_requires_a_execution_and_hardware_provenance(self):
        snapshot = fake_snapshot()
        snapshot["confirmation_a_authorization"][
            "execution_receipt_sha256"
        ] = "not-a-digest"
        with self.assertRaises(P.ProtocolError):
            P.validate_base_snapshot(snapshot)

        snapshot = fake_snapshot()
        snapshot["confirmation_a_authorization"]["hardware"][
            "hardware_attestation_files"
        ] -= 1
        with self.assertRaisesRegex(P.ProtocolError, "hardware"):
            P.validate_base_snapshot(snapshot)

    def test_snapshot_requires_exact_confirmation_b_source_closure(self):
        snapshot = fake_snapshot()
        base_sources = snapshot["base_b_experiment_source_sha256"]
        self.assertEqual(
            set(base_sources),
            set(P.BASE_B_EXPERIMENT_SOURCE_FILES),
        )
        base_sources.pop(next(iter(base_sources)))
        with self.assertRaisesRegex(P.ProtocolError, "source closure"):
            P.validate_base_snapshot(snapshot)

    def test_snapshot_authorized_import_guards_static_b_source_contract(self):
        drifted = SimpleNamespace(
            EXPERIMENT_SOURCE_FILES=P.BASE_B_EXPERIMENT_SOURCE_FILES[:-1]
        )
        with mock.patch.object(
            P, "_lazy_base_protocol", return_value=drifted
        ), self.assertRaisesRegex(P.ProtocolError, "contract drifted"):
            P.snapshot_sealed_b(fake_calibration())

    def test_six_field_planner_identity_is_exactly_shared(self):
        mutations = {
            "revision": "0" * 40,
            "cache_name": "different-cache",
            "build_options": ["different-build"],
            "downward_sha256": "0" * 64,
            "preprocess_sha256": "0" * 64,
            "tree_manifest_sha256": "0" * 64,
        }
        for field, value in mutations.items():
            snapshot = fake_snapshot()
            snapshot["base_b_planner"][field] = value
            with self.subTest(field=field), self.assertRaises(P.ProtocolError):
                P.validate_base_snapshot(snapshot)
        planner = fake_planner()
        planner["revision"] = "0" * 40
        with self.assertRaisesRegex(P.ProtocolError, "planner manifest"):
            P.validate_planner_manifest(planner)

    def test_v6_paths_scope_and_authorization_links_are_exact(self):
        path_fields = (
            "attestation_path", "terminal_diagnostic_path", "execution_receipt_path",
            "launch_receipt_path", "launch_intent_path",
        )
        for field in path_fields:
            snapshot = fake_snapshot()
            snapshot["source_audit_v6"][field] = "experiments/elsewhere.json"
            with self.subTest(path=field), self.assertRaises(P.ProtocolError):
                P.validate_base_snapshot(snapshot)
        link_fields = (
            "attestation_sha256", "launch_receipt_sha256",
            "execution_receipt_sha256", "confirmation_a_cohort_manifest_sha256",
            "cohort_manifest_sha256",
        )
        for field in link_fields:
            snapshot = fake_snapshot()
            snapshot["source_audit_v6"][field] = "0" * 64
            with self.subTest(link=field), self.assertRaises(P.ProtocolError):
                P.validate_base_snapshot(snapshot)
        snapshot = fake_snapshot()
        snapshot["source_audit_v6"]["tracked_file_sha256"].pop(
            P.V6_SCOPED_FILES[0]
        )
        with self.assertRaisesRegex(P.ProtocolError, "tracked source"):
            P.validate_base_snapshot(snapshot)

    def test_standalone_sealed_b_paths_are_exact(self):
        evidence = fake_standalone()
        for field in (
            "parse_receipt_path", "fetch_receipt_path", "properties_path",
        ):
            mutated = copy.deepcopy(evidence)
            mutated["sealed_b_input"][field] = "experiments/elsewhere"
            with self.subTest(field=field), self.assertRaises(P.ProtocolError):
                P.validate_standalone_evidence(
                    mutated, fake_snapshot(), fake_planner()
                )

    def test_freeze_repository_revision_is_mandatory(self):
        freeze = fake_freeze()
        del freeze["freeze_repository_revision"]
        with self.assertRaises(P.ProtocolError):
            P.validate_freeze(freeze, verify_live_sources=False)

    def test_scheduler_resources_are_post_calibration_and_cover_triads(self):
        recommendation = fake_calibration()["resource_recommendation"]
        P.validate_frozen_resources("01:30:00", "24G", recommendation)
        for time_limit, memory in (("01:29:59", "26G"), ("01:40:00", "23G")):
            with self.assertRaises(P.ProtocolError):
                P.validate_frozen_resources(time_limit, memory, recommendation)

        high = {
            "minimum_selector_wall_seconds": 2000,
            "minimum_selector_peak_delta_kb": 30 * 1024 * 1024,
        }
        with self.assertRaises(P.ProtocolError):
            P.validate_frozen_resources("01:40:00", "26G", high)
        P.validate_frozen_resources("01:40:00", "30G", high)

    def test_calibration_recommendation_is_exactly_reconstructed(self):
        receipt = fake_calibration()
        receipt["resource_recommendation"][
            "minimum_selector_wall_seconds"
        ] += 1
        with self.assertRaisesRegex(P.ProtocolError, "recommendation changed"):
            P.validate_calibration_receipt(receipt)

    def test_calibration_rejects_outcome_identity(self):
        receipt = fake_calibration()
        receipt["observations"][0]["selected_identity"] = {"pattern": []}
        receipt["observations_sha256"] = hashlib.sha256(
            P.canonical_json(receipt["observations"])
        ).hexdigest()
        with self.assertRaisesRegex(P.ProtocolError, "forbidden"):
            P.validate_calibration_receipt(receipt)


if __name__ == "__main__":
    unittest.main()
