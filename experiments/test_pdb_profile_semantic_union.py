#!/usr/bin/env python3
"""Focused adversarial tests for the semantic-union follow-up analysis."""

from __future__ import annotations

import copy
import unittest
from collections import defaultdict

import analyze_pdb_profile_semantic_union as Analysis
import exp_pdb_profile_semantic_union as E
import pdb_profile_semantic_union_protocol as P


class SemanticUnionAnalysisTest(unittest.TestCase):
    def presearch_record(self, label):
        record = {
            "algorithm": label,
            "domain": "d",
            "problem": "p.pddl",
            "id": [label, "d", "p.pddl"],
            "component_options": ["--search", P.SEARCHES[label]],
            "driver_options": [
                "--overall-time-limit",
                "{}s".format(P.TIME_LIMIT_SECONDS),
                "--overall-memory-limit",
                "{}M".format(P.MEMORY_LIMIT_MIB),
                "--build",
                "release_no_lp",
            ],
            "build_options": list(P.BUILD_OPTIONS),
            "local_revision": E.PLANNER_REVISION,
            "global_revision": E.PLANNER_REVISION,
            "planner_exit_code": 10,
            "error": "translate-unsolvable",
            "coverage": 0,
            "unsolvable": 1,
            "unexplained_errors": [],
            "construction_completed": None,
        }
        record.update({
            "protocol": P.PROTOCOL,
            "analysis_protocol": P.ANALYSIS_PROTOCOL,
            "cohort_role": P.COHORT_ROLE,
            "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
            "cohort_task_count": P.COHORT_TASKS,
            "cohort_domain_count": P.COHORT_DOMAINS,
            "config_count": P.CONFIG_COUNT,
            "declared_run_count": P.CELL_COUNT,
            "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
            "protocol_sha256": P.PROTOCOL_SHA256,
            "source_protocol": P.Source.PROTOCOL,
            "planner_revision": E.PLANNER_REVISION,
            "planner_binary_sha256": E.PLANNER_BINARY_SHA256,
            "preprocess_binary_sha256": E.PREPROCESS_BINARY_SHA256,
            "planner_preprocess_sha256": E.PREPROCESS_BINARY_SHA256,
            "required_lab_version": P.REQUIRED_LAB_VERSION,
            "planner_time_limit": float(P.TIME_LIMIT_SECONDS),
            "planner_memory_limit": P.MEMORY_LIMIT_MIB,
            "external_validation_requested": False,
            "slurm_partition": "fat",
            "array_throttle": 0,
        })
        return record

    def one_task_matrix(self):
        return [self.presearch_record(label) for label in P.LABELS]

    def eligible_record(self, *, effort=9, union=6):
        return {
            "coverage": 1,
            "solution_cost": 2,
            "effort": effort,
            "wbh_solved_summary_certified": True,
            "wbh_expansion_profile_complete": True,
            "wbh_expansion_profile_certified": True,
            "wbh_profile_complete": True,
            "wbh_profile_certified": True,
            "pdb_profile_selector_trace_certified": True,
            "wbh_profile_done": {
                "solution_cost": 2,
                "layer_union_effort": union,
            },
            "wbh_profile_layer_profiles": [
                {
                    "g": 0,
                    "completed": True,
                    "piece_count": 1,
                    "bdd_nodes": union,
                }
            ],
            "wbh_profile_layer_profile_attempts": 1,
            "wbh_profile_completed_layer_profiles": 1,
            "wbh_expansion_profile": [{"g": 0, "effort": effort}],
            "wbh_profile_heuristic_profile": {
                "add_nodes": 3,
                "num_terminals": 2,
                "num_values": 2,
                "cofactor_width": 4,
                "cofactor_counts": [1, 2, 4],
            },
            "pdb_profile_selector_selected": {
                "pattern": [0],
                "value_cap": -1,
                "abstract_states": 2,
                "initial_dead_end": False,
                "initial_h": 1,
                "finite_sum": 1,
                "finite_count": 2,
                "dead_count": 0,
                "cofactor_width": 4,
                "width_upper_bound": 5,
                "add_nodes": 3,
                "num_terminals": 2,
                "transformed_num_values": 2,
            },
            "add_nodes": 3,
            "num_terminals": 2,
            "num_values": 2,
            "width_upper_bound": 5,
        }

    def test_matrix_accepts_exact_unthrottled_fat_identity(self):
        matrix, tasks, outcomes = Analysis.validate_matrix(
            self.one_task_matrix(), expected_tasks=1
        )
        self.assertEqual(tasks, [("d", "p.pddl")])
        self.assertEqual(len(matrix), P.CONFIG_COUNT)
        self.assertEqual(set(outcomes.values()), {"presearch"})

    def test_matrix_rejects_throttle_partition_and_driver_changes(self):
        for field, value, pattern in (
            ("array_throttle", 2, "array_throttle"),
            ("slurm_partition", "main", "slurm_partition"),
        ):
            records = self.one_task_matrix()
            records[0][field] = value
            with self.assertRaisesRegex(
                Analysis.SemanticUnionAnalysisError, pattern
            ):
                Analysis.validate_matrix(records, expected_tasks=1)
        records = self.one_task_matrix()
        records[0]["driver_options"].insert(0, "--validate")
        with self.assertRaisesRegex(
            Analysis.SemanticUnionAnalysisError, "driver options"
        ):
            Analysis.validate_matrix(records, expected_tasks=1)

    def test_matrix_rejects_unexplained_error_and_duplicate(self):
        records = self.one_task_matrix()
        records[0]["unexplained_errors"] = ["synthetic"]
        with self.assertRaisesRegex(
            Analysis.SemanticUnionAnalysisError, "unexplained"
        ):
            Analysis.validate_matrix(records, expected_tasks=1)
        records = self.one_task_matrix()
        records[-1] = copy.deepcopy(records[0])
        with self.assertRaisesRegex(
            Analysis.SemanticUnionAnalysisError, "duplicate"
        ):
            Analysis.validate_matrix(records, expected_tasks=1)

    def test_corrected_observation_allows_ratio_below_one(self):
        status, observation = Analysis._observation(
            self.eligible_record(effort=3, union=6),
            ("d", "p"),
            P.LABELS[0],
        )
        self.assertEqual(status, "eligible")
        self.assertEqual(observation["_fragmentation"], (3, 6))

    def test_zero_union_is_reported_not_divided(self):
        record = self.eligible_record(effort=0, union=0)
        record["wbh_profile_layer_profiles"][0]["bdd_nodes"] = 0
        status, observation = Analysis._observation(
            record, ("d", "p"), P.LABELS[0]
        )
        self.assertEqual(status, "zero_union_effort")
        self.assertIsNone(observation)

    def test_layer_and_effort_conservation_are_fail_closed(self):
        changed = self.eligible_record()
        changed["wbh_profile_layer_profiles"][0]["piece_count"] = 2
        with self.assertRaisesRegex(
            Analysis.SemanticUnionAnalysisError, "layer is invalid"
        ):
            Analysis._observation(changed, ("d", "p"), P.LABELS[0])
        changed = self.eligible_record()
        changed["wbh_expansion_profile"][0]["effort"] += 1
        with self.assertRaisesRegex(
            Analysis.SemanticUnionAnalysisError, "event conservation"
        ):
            Analysis._observation(changed, ("d", "p"), P.LABELS[0])
        changed = self.eligible_record()
        changed["wbh_expansion_profile"][0]["g"] = 1
        with self.assertRaisesRegex(
            Analysis.SemanticUnionAnalysisError, "different g layers"
        ):
            Analysis._observation(changed, ("d", "p"), P.LABELS[0])

    def test_duplicate_semantics_require_identical_measurements(self):
        task = ("d", "p")
        records = {
            (label, task): self.eligible_record()
            for label in P.LABELS
        }
        records[(P.LABELS[-1], task)]["effort"] = 10
        records[(P.LABELS[-1], task)]["wbh_expansion_profile"][0]["effort"] = 10
        with self.assertRaisesRegex(
            Analysis.SemanticUnionAnalysisError, "deterministic evidence"
        ):
            Analysis.observations(records, [task])

    def shared_pass_fixture(self):
        grouped = defaultdict(dict)
        for index in range(P.MIN_TASKS_WITH_COMPARABLE_PAIRS):
            domain = "d{:02d}".format(index % P.MIN_DOMAINS)
            task = (domain, "p{:03d}".format(index))
            grouped[task] = {
                "left": {
                    "cofactor_width": 1,
                    "total_add_nodes": 2,
                    "_quality": (0,),
                    "_fragmentation": (1, 1),
                },
                "right": {
                    "cofactor_width": 2,
                    "total_add_nodes": 3,
                    "_quality": (1,),
                    "_fragmentation": (2, 1),
                },
            }
        domains = {"d{:02d}".format(index) for index in range(P.COHORT_DOMAINS)}
        return Analysis.Predictor._shared_pairwise_comparison(
            grouped,
            Analysis.PREDICTOR_SPECS,
            "_fragmentation",
            domains,
        )

    def test_exact_gate_passes_only_all_frozen_criteria(self):
        shared = self.shared_pass_fixture()
        gate = Analysis.decision_gate(shared)
        self.assertTrue(gate["pass"])
        self.assertTrue(all(gate["criteria"].values()))

        failed = copy.deepcopy(shared)
        failed["predictors"]["cofactor_width"]["equal_domain_macro"] = {
            "numerator": 13,
            "denominator": 20,
            "value": 0.65,
        }
        failed["predictors"]["quality"]["equal_domain_macro"] = {
            "numerator": 13,
            "denominator": 20,
            "value": 0.65,
        }
        gate = Analysis.decision_gate(failed)
        self.assertFalse(gate["pass"])
        self.assertFalse(gate["criteria"]["width_beats_quality"])
        self.assertEqual(gate["consequence"], "do_not_tune_a_rescue_selector")

    def test_gate_checks_full_lodo_universe(self):
        shared = self.shared_pass_fixture()
        values = shared["predictors"]["cofactor_width"][
            "leave_one_domain_out"
        ]["values"]
        values.pop(next(iter(values)))
        gate = Analysis.decision_gate(shared)
        self.assertFalse(
            gate["criteria"]["every_width_lodo_at_least_0_60"]
        )


if __name__ == "__main__":
    unittest.main()
