#!/usr/bin/env python3
"""Focused adversarial tests for the terminal-incidence analyzer."""

from __future__ import annotations

import copy
import unittest
from fractions import Fraction
from unittest import mock

import analyze_pdb_terminal_incidence_shadow as Analysis
import pdb_fixed_pattern_parser as PatternParser
import pdb_profile_comparison_parser as ProfileParser
import pdb_terminal_incidence_shadow_protocol as P


class TerminalIncidenceAnalysisTest(unittest.TestCase):
    task = ("agricola-opt18-strips", "p01.pddl")

    def test_terminal_messages_match_pinned_lab(self):
        from downward.outcomes import get_outcome

        for code, (message, _coverage, _unsolvable, _kind) in (
            Analysis.OUTCOME_SPECS.items()
        ):
            self.assertEqual(get_outcome(code, False).msg, message)

    def base_record(self, label):
        domain, problem = self.task
        record = {
            "algorithm": label,
            "domain": domain,
            "problem": problem,
            "id": [label, domain, problem],
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
            "local_revision": P.PLANNER_REVISION,
            "global_revision": P.PLANNER_REVISION,
            "wbh_profile_parser_protocol": ProfileParser.PROFILE_PARSER_PROTOCOL,
            "wbh_expansion_parser_protocol": ProfileParser.EXPANSION_PARSER_PROTOCOL,
            "pdb_profile_selector_parser_protocol": (
                ProfileParser.SELECTOR_PARSER_PROTOCOL
            ),
            "pdb_profile_selector_present": False,
            "pdb_fixed_pattern_parser_protocol": PatternParser.PARSER_PROTOCOL,
            "domain_source_path": "agricola-opt18-strips/domain.pddl",
            "problem_source_path": "agricola-opt18-strips/p01.pddl",
            "domain_source_sha256": "a" * 64,
            "problem_source_sha256": "b" * 64,
        }
        record.update(Analysis._fixed_properties())
        return record

    def presearch_record(self, label):
        record = self.base_record(label)
        record.update({
            "planner_exit_code": 10,
            "error": "translate-unsolvable",
            "coverage": 0,
            "unsolvable": 1,
            "unexplained_errors": [],
            "wbh_profile_present": False,
            "wbh_expansion_profile_present": False,
            "construction_completed": None,
        })
        return record

    def solved_record(
        self,
        label,
        *,
        pattern=None,
        active_value=1,
        partition=1,
        incidence=2,
    ):
        record = self.base_record(label)
        pattern = [P.LABELS.index(label)] if pattern is None else pattern
        mode = Analysis.REQUESTED_MODES[label]
        value_cap = 8 if label == P.INTERVENTION_LABEL else None
        layers = []
        expansions = []
        for g in range(2):
            counts = [1, 2, 2]
            layers.append({
                "g": g,
                "completed": True,
                "piece_count": 1,
                "bdd_nodes": 3,
                "cofactor_width": 2,
                "cofactor_counts": counts,
                "cofactor_counts_sha256": Analysis._sha(counts),
                "joint_cofactor_counts": [1, 3, 2],
                "joint_cofactor_counts_sha256": Analysis._sha([1, 3, 2]),
                "masked_add_nodes": 2,
                "active_value_count": 1,
                "active_values": [active_value],
                "bottom_reachable": True,
                "masked_cofactor_counts": [1, 2, 2],
                "masked_cofactor_sum": 3,
                "terminal_incidence": incidence,
                "partition_audit_effort": partition,
                "masked_seconds": 0.5,
                "partition_audit_seconds": 0.25,
            })
            expansions.append({
                "g": g,
                "active_h_values": [0],
                "active_value_count": 1,
                "effort": 3,
                "buckets": 1,
                "pieces": 1,
            })
        record.update({
            "planner_exit_code": 0,
            "error": "success",
            "coverage": 1,
            "unsolvable": 0,
            "solution_cost": 2,
            "unexplained_errors": [],
            "wbh_schema_version": 2,
            "raw_metrics_complete": True,
            "piece_metrics_certified": True,
            "wbh_expansion_profile_present": True,
            "wbh_expansion_trailing_fragment_discarded": False,
            "wbh_expansion_profile_certified": True,
            "wbh_expansion_profile_complete": True,
            "wbh_expansion_profile": expansions,
            "wbh_solved_summary_certified": True,
            "wbh_profile_present": True,
            "wbh_profile_trailing_fragment_discarded": False,
            "wbh_profile_prefix_certified": True,
            "wbh_profile_complete": True,
            "wbh_profile_certified": True,
            "wbh_profile_schema_version": 3,
            "wbh_profile_state_bits": 2,
            "wbh_profile_variable_order_sha256": "a" * 64,
            "wbh_profile_layer_profiles": layers,
            "wbh_profile_heuristic_profile": {
                "add_nodes": 1,
                "num_terminals": 2,
                "num_values": 2,
                "cofactor_width": 2,
                "cofactor_counts": [1, 2, 2],
            },
            "wbh_profile_done": {
                "solution_cost": 2,
                "layer_union_effort": 6,
                "masked_add_effort": 4,
                "terminal_incidence_effort": 2 * incidence,
                "partition_audit_effort": 2 * partition,
            },
            "construction_completed": True,
            "pdb_fixed_pattern_present": True,
            "pdb_fixed_pattern_certified": True,
            "pdb_fixed_pattern_validation_error": None,
            "pdb_fixed_pattern": pattern,
            "pdb_fixed_pattern_size": len(pattern),
            "pdb_fixed_pattern_sha256": Analysis._sha(pattern),
            "pdb_fixed_pattern_mode": mode,
            "pdb_fixed_pattern_requested_mode": mode,
            "pdb_fixed_pattern_observed_mode": mode,
            "pdb_fixed_pattern_fallback": False,
            "pdb_fixed_pattern_final": {
                "mode": mode,
                "state_budget": 100000,
                "pattern": pattern,
                "pattern_size": len(pattern),
                "pattern_sha256": Analysis._sha(pattern),
                "num_values": 2,
                "value_cap": value_cap,
                "cofactor_width": 2,
                "width_upper_bound": 3,
            },
            "add_nodes": 1,
            "num_terminals": 2,
            "num_values": 2,
            "width_upper_bound": 3,
        })
        return record

    def solved_matrix(self, **goal_fill_options):
        records = []
        for label in P.LABELS:
            options = (
                goal_fill_options
                if label in {Analysis.GOAL_FILL_LABEL, P.INTERVENTION_LABEL}
                else {}
            )
            records.append(self.solved_record(label, **options))
        return records

    @staticmethod
    def add_active_infinity(record, infinity_marker):
        record["wbh_profile_heuristic_profile"].update({
            "num_values": 1,
            "num_terminals": 2,
        })
        record["pdb_fixed_pattern_final"]["num_values"] = 1
        record["num_values"] = 1
        record["num_terminals"] = 2
        for layer in record["wbh_profile_layer_profiles"]:
            layer.update({
                "active_value_count": 2,
                "active_values": [0, infinity_marker],
                "bottom_reachable": False,
            })

    def test_matrix_accepts_exact_static_identity_and_rejects_throttle(self):
        records = [self.presearch_record(label) for label in P.LABELS]
        matrix, tasks, outcomes = Analysis.validate_matrix(
            records, expected_tasks=1
        )
        self.assertEqual(tasks, [self.task])
        self.assertEqual(len(matrix), 5)
        self.assertEqual(
            set(outcomes.values()),
            {"presearch", "deferred_until_primary_gate"},
        )
        records[0]["array_throttle"] = 1
        with self.assertRaisesRegex(
            Analysis.TerminalIncidenceAnalysisError, "array_throttle"
        ):
            Analysis.validate_matrix(records, expected_tasks=1)

    def test_early_solution_fixed_frontier_and_exact_formulas(self):
        matrix, tasks, _ = Analysis.validate_matrix(
            self.solved_matrix(), expected_tasks=1
        )
        primary = Analysis.primary_observations(matrix, tasks)
        self.assertEqual(primary["frontier_statuses"], {"eligible": 1})
        observation = primary["by_cell"][(P.PRIMARY_LABELS[0], self.task)]
        self.assertEqual(observation["E"], 2)
        self.assertEqual(observation["I"], 4)
        self.assertEqual(observation["kD"], 4)
        self.assertEqual(observation["mQ"], 6)
        self.assertEqual(observation["mJ"], 8)
        self.assertEqual(observation["Cartesian"], 10)
        self.assertEqual(observation["width"], 12)
        self.assertEqual(observation["ADD"], 26)
        self.assertEqual(observation["U"], 6)
        diagnostics = Analysis.secondary_diagnostics(
            primary["observations"]
        )
        self.assertEqual(
            diagnostics["tightness"]["I"]["equal_family_macro"][
                "value"
            ],
            0.5,
        )
        self.assertEqual(
            diagnostics["computation_time"][
                "pooled_masked_over_partition_ratio"
            ],
            2.0,
        )

    def test_metric_cost_horizon_uses_completed_g_sequence_not_range(self):
        records = self.solved_matrix()
        for record in records:
            record["solution_cost"] = 4
            record["wbh_profile_done"]["solution_cost"] = 4
            record["wbh_profile_layer_profiles"][1]["g"] = 3
            record["wbh_expansion_profile"][1]["g"] = 3
        matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
        primary = Analysis.primary_observations(matrix, tasks)
        self.assertEqual(
            primary["frontiers"][self.task]["retained_g"], (0, 3)
        )

    def test_frontier_mismatch_and_certificate_violation_abort(self):
        records = self.solved_matrix()
        changed = records[1]["wbh_profile_layer_profiles"][0]
        changed["bdd_nodes"] = 4
        records[1]["wbh_expansion_profile"][0]["effort"] = 4
        changed["cofactor_counts"] = [1, 2, 2]
        with self.assertRaisesRegex(
            Analysis.TerminalIncidenceAnalysisError, "fixed-frontier"
        ):
            matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
            Analysis.primary_observations(matrix, tasks)

        records = self.solved_matrix()
        records[0]["wbh_profile_layer_profiles"][0]["terminal_incidence"] = 3
        with self.assertRaisesRegex(
            Analysis.TerminalIncidenceAnalysisError, "certificate chain"
        ):
            matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
            Analysis.primary_observations(matrix, tasks)

    def test_terminal_incidence_must_satisfy_add_apply_bound(self):
        records = self.solved_matrix()
        for record in records:
            for layer in record["wbh_profile_layer_profiles"]:
                layer.update({
                    "cofactor_counts": [1, 14, 2],
                    "cofactor_counts_sha256": Analysis._sha([1, 14, 2]),
                    "joint_cofactor_counts": [1, 14, 2],
                    "joint_cofactor_counts_sha256": Analysis._sha(
                        [1, 14, 2]
                    ),
                    "masked_add_nodes": 14,
                    "masked_cofactor_counts": [1, 14, 2],
                    "masked_cofactor_sum": 15,
                    "terminal_incidence": 14,
                })
            record["wbh_profile_done"].update({
                "masked_add_effort": 28,
                "terminal_incidence_effort": 28,
            })
        with self.assertRaisesRegex(
            Analysis.TerminalIncidenceAnalysisError,
            "terminal incidence exceeds the ADD apply certificate",
        ):
            matrix, tasks, _ = Analysis.validate_matrix(
                records, expected_tasks=1
            )
            Analysis.primary_observations(matrix, tasks)

    def test_incomplete_primary_stream_excludes_whole_task(self):
        records = self.solved_matrix()
        records[0]["wbh_profile_complete"] = False
        records[0]["wbh_profile_certified"] = False
        matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
        primary = Analysis.primary_observations(matrix, tasks)
        self.assertEqual(
            primary["frontier_statuses"], {"insufficient_completed_layers": 1}
        )
        self.assertEqual(primary["observations"], [])

    def test_primary_construction_failure_excludes_whole_task(self):
        matrix, tasks, _ = Analysis.validate_matrix(
            self.solved_matrix(), expected_tasks=1
        )
        matrix[(P.PRIMARY_LABELS[0], self.task)][
            "construction_completed"
        ] = False
        primary = Analysis.primary_observations(matrix, tasks)
        self.assertEqual(
            primary["frontier_statuses"],
            {"primary_construction_failure": 1},
        )
        self.assertEqual(primary["observations"], [])

    def test_active_dead_end_terminal_uses_terminal_not_finite_value_bound(self):
        records = self.solved_matrix()
        self.add_active_infinity(records[0], 9)
        matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
        primary = Analysis.primary_observations(matrix, tasks)
        self.assertEqual(primary["frontier_statuses"], {"eligible": 1})
        self.assertIn((P.PRIMARY_LABELS[0], self.task), primary["by_cell"])

    def test_malformed_primary_prefix_is_a_task_exclusion(self):
        records = self.solved_matrix()
        records[0]["wbh_profile_prefix_certified"] = False
        records[0]["wbh_profile_validation_error"] = "torn tail"
        records[0]["unexplained_errors"] = ["torn tail"]
        matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
        primary = Analysis.primary_observations(matrix, tasks)
        self.assertEqual(
            primary["frontier_statuses"],
            {"invalid_or_missing_primary_prefix": 1},
        )
        self.assertEqual(primary["observations"], [])

    def test_inconsistent_primary_cost_is_a_task_exclusion(self):
        records = self.solved_matrix()
        records[0]["solution_cost"] = 3
        matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
        primary = Analysis.primary_observations(matrix, tasks)
        self.assertEqual(
            primary["frontier_statuses"],
            {"inconsistent_primary_solution_cost": 1},
        )

    def test_parser_invalidated_primary_outcome_is_a_task_exclusion(self):
        records = self.solved_matrix()
        records[0]["coverage"] = None
        records[0]["unexplained_errors"] = [
            "WBH outcome validation failed: done.solution_cost=3 "
            "!= planner output 2"
        ]
        matrix, tasks, outcomes = Analysis.validate_matrix(
            records, expected_tasks=1
        )
        self.assertEqual(
            outcomes[(P.PRIMARY_LABELS[0], self.task)], "invalid_outcome"
        )
        primary = Analysis.primary_observations(matrix, tasks)
        self.assertEqual(
            primary["frontier_statuses"],
            {"invalid_primary_terminal_outcome": 1},
        )

    def test_two_discarded_log_tails_in_one_cell_are_not_eligible(self):
        records = self.solved_matrix()
        records[0]["wbh_profile_trailing_fragment_discarded"] = True
        records[0]["wbh_expansion_trailing_fragment_discarded"] = True
        matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
        primary = Analysis.primary_observations(matrix, tasks)
        self.assertEqual(
            primary["frontier_statuses"],
            {"invalid_or_missing_primary_prefix": 1},
        )

    def test_valid_resource_prefix_after_horizon_is_eligible(self):
        records = self.solved_matrix()
        for record in records[:4]:
            record.update({
                "planner_exit_code": 23,
                "error": "search-out-of-time",
                "coverage": 0,
                "unsolvable": 0,
                "raw_metrics_complete": False,
                "piece_metrics_certified": False,
                "wbh_expansion_profile_complete": False,
                "wbh_profile_complete": False,
                "wbh_profile_certified": False,
                "wbh_profile_done": None,
            })
        with mock.patch.object(P, "HORIZON", 2):
            for record in records:
                record["analysis_horizon"] = 2
            matrix, tasks, _ = Analysis.validate_matrix(
                records, expected_tasks=1
            )
            primary = Analysis.primary_observations(matrix, tasks)
        self.assertEqual(primary["frontier_statuses"], {"eligible": 1})
        self.assertEqual(len(primary["observations"]), 4)

    @staticmethod
    def comparison_observation(task, semantic, e, i, controls=None):
        controls = controls or (i, i, i, i, i, i)
        return {
            "task": task,
            "semantic_id": semantic,
            "E": e,
            "I": i,
            "kD": controls[0],
            "mQ": controls[1],
            "mJ": controls[2],
            "Cartesian": controls[3],
            "width": controls[4],
            "ADD": controls[5],
            "U": 10,
        }

    def test_concordance_is_task_first_not_pair_pooled(self):
        task1 = ("agricola-opt18-strips", "a")
        task2 = ("agricola-opt18-strips", "b")
        grouped = {
            task1: {
                "a": self.comparison_observation(task1, "a", 1, 1),
                "b": self.comparison_observation(task1, "b", 2, 2),
                "c": self.comparison_observation(task1, "c", 3, 0),
            },
            task2: {
                "a": self.comparison_observation(task2, "a", 1, 1),
                "b": self.comparison_observation(task2, "b", 2, 2),
            },
        }
        comparison = Analysis.grand_shared_comparison(grouped)
        macro = comparison["predictors"]["I"]["equal_family"]["macro"]
        self.assertEqual(
            Fraction(macro["numerator"], macro["denominator"]),
            Fraction(2, 3),
        )
        self.assertEqual(comparison["support"]["grand_shared_strict"], 4)
        self.assertTrue(
            comparison["target_orientations"]["orders_identical"]
        )

    def test_gates_require_bootstrap_and_every_lodo_difference(self):
        grouped = {}
        directories = (
            "agricola-opt18-strips",
            "barman-mco14-strips",
            "caldera-opt18-adl",
        )
        for index, directory in enumerate(directories):
            task = (directory, "p{}".format(index))
            grouped[task] = {
                "a": self.comparison_observation(
                    task, "a", 1, 1, (2, 2, 2, 2, 2, 2)
                ),
                "b": self.comparison_observation(
                    task, "b", 2, 2, (1, 1, 1, 1, 1, 1)
                ),
            }
        with mock.patch.multiple(
            P,
            MIN_ELIGIBLE_TASKS=3,
            MIN_ELIGIBLE_FAMILIES=3,
            MIN_COMPARISON_TASKS=3,
            MIN_COMPARISON_FAMILIES=3,
            MIN_SHARED_STRICT_PAIRS=3,
            BOOTSTRAP_REPLICATES=200,
        ):
            comparison = Analysis.grand_shared_comparison(grouped)
            gates = Analysis.primary_gates(comparison, 3, 3)
        self.assertTrue(gates["pass"])
        for row in gates["controls"].values():
            self.assertTrue(row["all_leave_one_family_out_positive"])
            self.assertGreater(row["bootstrap"]["lower_95"]["numerator"], 0)

        failed = copy.deepcopy(comparison)
        failed["predictors"]["mQ"]["_family_lodo"]["agricola"] = (
            failed["predictors"]["I"]["_family_lodo"]["agricola"]
        )
        with mock.patch.multiple(
            P,
            MIN_ELIGIBLE_TASKS=3,
            MIN_ELIGIBLE_FAMILIES=3,
            MIN_COMPARISON_TASKS=3,
            MIN_COMPARISON_FAMILIES=3,
            MIN_SHARED_STRICT_PAIRS=3,
            BOOTSTRAP_REPLICATES=20,
        ):
            gates = Analysis.primary_gates(failed, 3, 3)
        self.assertFalse(gates["controls"]["mQ"]["pass"])
        self.assertFalse(gates["pass"])

        concentrated = copy.deepcopy(comparison)
        concentrated["support"]["families_with_shared_pairs"] = 2
        with mock.patch.multiple(
            P,
            MIN_ELIGIBLE_TASKS=3,
            MIN_ELIGIBLE_FAMILIES=3,
            MIN_COMPARISON_TASKS=3,
            MIN_COMPARISON_FAMILIES=3,
            MIN_SHARED_STRICT_PAIRS=3,
            BOOTSTRAP_REPLICATES=20,
        ):
            gates = Analysis.primary_gates(concentrated, 3, 3)
        self.assertFalse(gates["support"]["pass"])
        self.assertFalse(gates["pass"])

    def test_cap8_certificates_decrease_but_partition_effort_may_rise(self):
        records = []
        for label in P.LABELS:
            active = 8 if label == P.INTERVENTION_LABEL else 9
            pattern = [2] if label in {
                Analysis.GOAL_FILL_LABEL, P.INTERVENTION_LABEL
            } else None
            records.append(self.solved_record(
                label,
                pattern=pattern,
                active_value=active,
                partition=1,
                incidence=2,
            ))
        matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
        primary = Analysis.primary_observations(matrix, tasks)
        intervention = Analysis.cap8_intervention(
            matrix, tasks, primary
        )
        self.assertTrue(
            intervention["observed_terminal_map_consequences_hold"]
        )
        self.assertEqual(intervention["eligible_pairs"], 1)

        records[-1] = self.solved_record(
            P.INTERVENTION_LABEL,
            pattern=[2],
            active_value=8,
            partition=2,
            incidence=2,
        )
        matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
        primary = Analysis.primary_observations(matrix, tasks)
        intervention = Analysis.cap8_intervention(matrix, tasks, primary)
        self.assertTrue(
            intervention["observed_terminal_map_consequences_hold"]
        )
        self.assertEqual(
            intervention["sum_deltas"]["partition_effort_delta"], 2
        )

    def test_cap8_preserves_reencoded_infinity_terminal(self):
        records = self.solved_matrix(pattern=[2])
        uncapped = next(
            record for record in records
            if record["algorithm"] == Analysis.GOAL_FILL_LABEL
        )
        capped = next(
            record for record in records
            if record["algorithm"] == P.INTERVENTION_LABEL
        )
        self.add_active_infinity(uncapped, 100)
        self.add_active_infinity(capped, 9)
        matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
        primary = Analysis.primary_observations(matrix, tasks)
        intervention = Analysis.cap8_intervention(matrix, tasks, primary)
        self.assertTrue(
            intervention["observed_terminal_map_consequences_hold"]
        )
        self.assertEqual(intervention["eligible_pairs"], 1)

    def test_parser_invalidated_cap8_outcome_excludes_intervention_pair(self):
        records = self.solved_matrix(pattern=[2])
        capped = next(
            record for record in records
            if record["algorithm"] == P.INTERVENTION_LABEL
        )
        capped["coverage"] = None
        capped["unexplained_errors"] = [
            "run-log coverage validation failed: exact cost disagrees"
        ]
        matrix, tasks, _ = Analysis.validate_matrix(records, expected_tasks=1)
        primary = Analysis.primary_observations(matrix, tasks)
        intervention = Analysis.cap8_intervention(matrix, tasks, primary)
        self.assertEqual(intervention["eligible_pairs"], 0)
        self.assertEqual(
            intervention["outcome_classes"], {"invalid_outcome": 1}
        )
        self.assertEqual(intervention["cell_statuses"], {"invalid_outcome": 1})

    def test_failed_gate_does_not_validate_intervention_outcomes(self):
        records = self.solved_matrix()
        capped = next(
            record for record in records
            if record["algorithm"] == P.INTERVENTION_LABEL
        )
        capped["planner_exit_code"] = "outcome remains blinded"
        capped["wbh_profile_parser_protocol"] = "unread-after-failed-gate"
        result = Analysis.analyze_records(records, expected_tasks=1)
        self.assertFalse(result["gates"]["pass"])
        self.assertEqual(
            result["intervention"]["status"],
            "not_analyzed_primary_gate_failed",
        )

    def test_failed_primary_gate_keeps_intervention_unanalyzed(self):
        result = Analysis.analyze_records(
            self.solved_matrix(), expected_tasks=1
        )
        self.assertFalse(result["gates"]["pass"])
        self.assertEqual(
            result["intervention"]["status"],
            "not_analyzed_primary_gate_failed",
        )
        Analysis._canonical(result)


if __name__ == "__main__":
    unittest.main()
