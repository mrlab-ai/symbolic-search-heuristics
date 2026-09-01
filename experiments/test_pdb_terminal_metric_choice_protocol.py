#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import unittest

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
    return {
        "schema": P.BASE_SNAPSHOT_SCHEMA,
        "base_b_freeze_path": "experiments/fake-base-b.json",
        "base_b_freeze_sha256": "1" * 64,
        "benchmark_revision": "2" * 40,
        "confirmation_a_authorization": {
            "guided_study_authorized": True,
            "receipt_sha256": "3" * 64,
            "first_output_sha256": "4" * 64,
            "second_output_sha256": "5" * 64,
            "input_properties_sha256": "6" * 64,
            "fetch_receipt_sha256": "7" * 64,
            "receipt_path": P._lazy_base_protocol().CONFIRMATION_A_RECEIPT_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "receipt_pin_path": P._lazy_base_protocol().CONFIRMATION_A_RECEIPT_PIN_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "first_output_path": P._lazy_base_protocol().CONFIRMATION_A_FIRST_OUTPUT_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "second_output_path": P._lazy_base_protocol().CONFIRMATION_A_SECOND_OUTPUT_PATH.relative_to(
                P.REPO
            ).as_posix(),
            "confirmation_a_cohort_manifest_sha256": "f" * 64,
        },
        "source_audit_v4": {
            "campaign": "v4", "attestation_sha256": "8" * 64,
            "launch_receipt_sha256": "9" * 64,
            "execution_receipt_sha256": "a" * 64,
            "code_manifest_sha256": "b" * 64,
            "repository_commit_id": "c" * 40,
            "output_tree_sha256": "d" * 64,
            "translator_source_sha256": "e" * 64,
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
            "tasks": tasks, "tasks_sha256": P.cohort_digest(tasks),
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
        "revision": P.REQUIRED_SELECTOR_COMMIT,
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
        "records": records,
        "records_sha256": hashlib.sha256(P.canonical_json(records)).hexdigest(),
    }


def fake_freeze():
    snapshot = fake_snapshot()
    calibration = fake_calibration()
    standalone = fake_standalone(snapshot)
    return P.build_freeze(
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

    def test_scheduler_resources_are_post_calibration_and_cover_triads(self):
        P.validate_frozen_resources("01:30:00", "24G")
        for time_limit, memory in (("01:29:59", "26G"), ("01:40:00", "23G")):
            with self.assertRaises(P.ProtocolError):
                P.validate_frozen_resources(time_limit, memory)

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
