#!/usr/bin/env python3
"""Adversarial tests for the fixed-heuristic order intervention."""

from __future__ import annotations

import copy
import unittest
from fractions import Fraction

import analyze_pdb_profile_order_intervention as Analysis
import exp_pdb_profile_order_intervention as E
import pdb_fixed_pattern_parser as Pattern
import pdb_profile_order_intervention_protocol as P


class OrderInterventionTest(unittest.TestCase):
    def eligible_record(self, *, effort=6, order="a" * 64):
        return {
            "coverage": 1,
            "solution_cost": 2,
            "effort": effort,
            "expanded_states": 4,
            "wbh_solved_summary_certified": True,
            "wbh_expansion_profile_complete": True,
            "wbh_expansion_profile_certified": True,
            "wbh_profile_complete": True,
            "wbh_profile_certified": True,
            "wbh_profile_state_bits": 2,
            "wbh_profile_variable_order_sha256": order,
            "pdb_fixed_pattern_parser_protocol": Pattern.PARSER_PROTOCOL,
            "pdb_fixed_pattern_present": True,
            "pdb_fixed_pattern_certified": True,
            "pdb_fixed_pattern": [0],
            "pdb_fixed_pattern_size": 1,
            "wbh_profile_done": {
                "solution_cost": 2,
                "layer_union_effort": 3,
            },
            "wbh_profile_layer_profiles": [
                {
                    "g": 0,
                    "completed": True,
                    "piece_count": 1,
                    "bdd_nodes": 3,
                    "cofactor_width": 3,
                    "cofactor_counts": [1, 3, 2],
                }
            ],
            "wbh_profile_layer_profile_attempts": 1,
            "wbh_profile_completed_layer_profiles": 1,
            "wbh_expansion_profile": [
                {
                    "g": 0,
                    "effort": effort,
                    "active_value_count": 2,
                    "buckets": 2,
                    "pieces": 2,
                }
            ],
            "wbh_profile_heuristic_profile": {
                "add_nodes": 3,
                "num_terminals": 2,
                "num_values": 2,
                "cofactor_width": 4,
                "cofactor_counts": [1, 4, 2],
            },
            "add_nodes": 3,
            "num_terminals": 2,
            "num_values": 2,
            "width_upper_bound": 5,
        }

    def test_protocol_and_runner_are_frozen_unthrottled_fat(self):
        P.validate_protocol_without_archive()
        self.assertEqual(len(P.load_cohort()), 1052)
        E.configure()
        self.assertEqual(E.Base.PARTITION, "fat")
        self.assertEqual(E.Base.RUNS_PER_ARRAY_TASK, 3)
        self.assertEqual(E.Base.EXPECTED_ARRAY_TASKS, 702)
        E.Base.self_test()

    def test_goal_fill_pattern_parser_is_exact(self):
        line = (
            "[t=1.000000s, 200 KB] PDB pattern selection=goal_fill "
            "(3 vars, <= 100000 abstract states): [0, 2, 5]"
        )
        self.assertEqual(Pattern.parse_pattern(line), [0, 2, 5])
        props = {}
        Pattern.parse_goal_fill_pattern(line, props)
        self.assertTrue(props["pdb_fixed_pattern_certified"])
        self.assertEqual(props["pdb_fixed_pattern_size"], 3)

    def test_goal_fill_pattern_parser_rejects_noncanonical_identity(self):
        line = (
            "PDB pattern selection=goal_fill "
            "(2 vars, <= 100000 abstract states): [2, 0]"
        )
        with self.assertRaisesRegex(
            Pattern.PatternParseError, "invalid"
        ):
            Pattern.parse_pattern(line)
        props = {}
        Pattern.parse_goal_fill_pattern(line + "\n" + line, props)
        self.assertFalse(props["pdb_fixed_pattern_certified"])
        self.assertTrue(props["unexplained_errors"])

    def test_exact_certificate_arithmetic(self):
        status, item = Analysis._observation(
            self.eligible_record(), ("d", "p"), P.LABELS[0]
        )
        self.assertEqual(status, "eligible")
        self.assertEqual(item["B_profile"], 26)
        self.assertEqual(item["B_width"], 32)
        self.assertEqual(item["B_add"], 54)
        self.assertEqual(item["R_profile"], Fraction(26, 3))

    def test_pair_aborts_if_order_changes_search_semantics(self):
        task = ("d", "p")
        gamer = self.eligible_record(order="a" * 64)
        fd = self.eligible_record(order="b" * 64)
        matrix = {
            (P.LABELS[0], task): gamer,
            (P.LABELS[1], task): fd,
        }
        pairs, _, status = Analysis.paired_observations(matrix, [task])
        self.assertEqual(len(pairs), 1)
        self.assertEqual(status["pair_distinct_order"], 1)

        changed = copy.deepcopy(matrix)
        changed[(P.LABELS[1], task)]["expanded_states"] = 5
        with self.assertRaisesRegex(
            Analysis.OrderInterventionAnalysisError,
            "changed semantic field expanded_states",
        ):
            Analysis.paired_observations(changed, [task])

    @staticmethod
    def shared(profile, width, add):
        domains = ["d{:02d}".format(index) for index in range(P.COHORT_DOMAINS)]
        predictors = {}
        for name, value in (
            ("profile", profile), ("width", width), ("add", add)
        ):
            record = Analysis._fraction_record(value)
            predictors[name] = {
                "equal_domain_macro": record,
                "leave_one_domain_out": {
                    "values": {domain: record for domain in domains}
                },
            }
        return {
            "support": {
                "eligible_domains": P.MIN_DOMAINS,
                "tasks_with_comparable_pairs": (
                    P.MIN_TASKS_WITH_COMPARABLE_PAIRS
                ),
            },
            "predictors": predictors,
        }

    def test_gates_require_complete_lodo_and_frozen_effects(self):
        summary = self.shared(
            Fraction(4, 5), Fraction(79, 100), Fraction(39, 50)
        )
        gates = Analysis.decision_gates(summary)
        self.assertTrue(gates["predicts_order_sensitivity"]["pass"])
        self.assertTrue(gates["sharper_order_predictor"]["pass"])

        failed = copy.deepcopy(summary)
        failed["predictors"]["profile"]["leave_one_domain_out"][
            "values"
        ].pop("d00")
        gates = Analysis.decision_gates(failed)
        self.assertFalse(gates["predicts_order_sensitivity"]["pass"])
        self.assertFalse(gates["sharper_order_predictor"]["pass"])


if __name__ == "__main__":
    unittest.main()
