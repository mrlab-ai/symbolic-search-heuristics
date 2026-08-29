#!/usr/bin/env python3

from __future__ import annotations

import unittest
from collections import defaultdict

import analyze_pdb_profile_predictors as A


class PredictorProtocolTests(unittest.TestCase):
    def test_frozen_protocol_hash(self):
        A.require_frozen_protocol()


class ObservationTests(unittest.TestCase):
    def record(self):
        return {
            "coverage": 1,
            "solution_cost": 4,
            "effort": 10,
            "wbh_solved_summary_certified": True,
            "wbh_expansion_profile_complete": True,
            "wbh_profile_certified": True,
            "wbh_profile_complete": True,
            "wbh_profile_done": {
                "solution_cost": 4,
                "layer_union_effort": 5,
            },
            "pdb_profile_selector_selected": {
                "pattern": [0],
                "value_cap": 2,
                "abstract_states": 6,
                "initial_dead_end": False,
                "initial_h": 1,
                "finite_sum": 7,
                "finite_count": 5,
                "dead_count": 1,
                "cofactor_width": 3,
                "width_upper_bound": 7,
            },
            "wbh_profile_heuristic_profile": {
                "add_nodes": 4,
                "num_values": 3,
                "num_terminals": 3,
                "cofactor_counts": [1, 2, 3],
                "cofactor_width": 3,
            },
        }

    def test_fragmentation_observation_is_exact(self):
        status, observation = A._fragmentation_observation(
            self.record(), ("d", "p"), "pdb_cap_width_k2"
        )
        self.assertEqual(status, "eligible")
        self.assertEqual(observation["_fragmentation"], (10, 5))
        self.assertEqual(observation["total_add_nodes"], 7)
        self.assertEqual(observation["finite_values"], 3)

    def test_invalid_union_and_profile_identity_fail_closed(self):
        record = self.record()
        record["wbh_profile_done"]["layer_union_effort"] = -1
        with self.assertRaisesRegex(A.PredictorAnalysisError, "union effort"):
            A._fragmentation_observation(
                record, ("d", "p"), "pdb_cap_width_k2"
            )
        record = self.record()
        record["pdb_profile_selector_selected"]["cofactor_width"] = 2
        with self.assertRaisesRegex(A.PredictorAnalysisError, "width mismatch"):
            A._fragmentation_observation(
                record, ("d", "p"), "pdb_cap_width_k2"
            )


class PairwiseTests(unittest.TestCase):
    def observation(self, domain, problem, semantic, width, effort, union):
        return {
            "domain": domain,
            "problem": problem,
            "task": (domain, problem),
            "semantic_id": semantic,
            "cofactor_width": width,
            "_fragmentation": (effort, union),
        }

    def test_domain_macro_and_loo_are_fixed(self):
        grouped = defaultdict(dict)
        grouped[("d1", "p")]["a"] = self.observation(
            "d1", "p", "a", 1, 1, 1
        )
        grouped[("d1", "p")]["b"] = self.observation(
            "d1", "p", "b", 2, 2, 1
        )
        grouped[("d2", "p")]["c"] = self.observation(
            "d2", "p", "c", 1, 2, 1
        )
        grouped[("d2", "p")]["d"] = self.observation(
            "d2", "p", "d", 2, 1, 1
        )
        result = A._pairwise_summary(
            grouped, "cofactor_width", "_fragmentation", "same"
        )
        self.assertEqual(result["concordant"], 1)
        self.assertEqual(result["discordant"], 1)
        self.assertEqual(result["equal_domain_macro"]["value"], 0.5)
        self.assertEqual(
            result["leave_one_domain_out"]["minimum"]["value"], 0.0
        )
        self.assertEqual(
            result["leave_one_domain_out"]["maximum"]["value"], 1.0
        )

    def test_ties_do_not_enter_concordance_denominator(self):
        grouped = defaultdict(dict)
        grouped[("d", "p")]["a"] = self.observation(
            "d", "p", "a", 1, 1, 1
        )
        grouped[("d", "p")]["b"] = self.observation(
            "d", "p", "b", 1, 2, 1
        )
        result = A._pairwise_summary(
            grouped, "cofactor_width", "_fragmentation", "same"
        )
        self.assertEqual(result["predictor_tied"], 1)
        self.assertEqual(result["comparable"], 0)
        self.assertIsNone(result["micro_concordance"])


class ContrastTests(unittest.TestCase):
    def record(self, coverage, effort, pool="a"):
        record = {
            "coverage": coverage,
            "solution_cost": 3 if coverage else None,
            "pdb_profile_selector_trace_certified": True,
            "pdb_profile_selector_raw_pool_common_sha256": pool * 64,
            "pdb_profile_selector_raw_pool_extended_sha256": pool * 64,
        }
        if coverage:
            record.update({
                "effort": effort,
                "wbh_solved_summary_certified": True,
                "wbh_expansion_profile_complete": True,
            })
        return record

    def test_selector_contrast_preserves_full_coverage_denominator(self):
        tasks = [("d1", "p1"), ("d2", "p2")]
        candidate = "pdb_cap_width_k2"
        reference = "pdb_cap_add_u8"
        matrix = {
            (candidate, tasks[0]): self.record(1, 8),
            (reference, tasks[0]): self.record(1, 10),
            (candidate, tasks[1]): self.record(1, 7),
            (reference, tasks[1]): self.record(0, 0),
        }
        result = A.selector_contrast(matrix, tasks, candidate, reference)
        self.assertEqual(result["fixed_task_denominator"], 2)
        self.assertEqual(result["coverage"]["candidate_minus_reference"], 1)
        self.assertEqual(result["conditional_effort"]["eligible_pairs"], 1)
        self.assertEqual(
            result["conditional_effort"]["candidate_over_reference"]["value"],
            0.8,
        )

    def test_different_strong_pools_are_effort_ineligible(self):
        task = ("d", "p")
        candidate = "pdb_cap_width_k2"
        reference = "pdb_cap_add_u8"
        matrix = {
            (candidate, task): self.record(1, 8, "a"),
            (reference, task): self.record(1, 10, "b"),
        }
        result = A.selector_contrast(matrix, [task], candidate, reference)
        self.assertEqual(result["conditional_effort"]["eligible_pairs"], 0)
        self.assertEqual(result["coverage"]["pool_ineligible"], 1)


class DecisionGateTests(unittest.TestCase):
    def rank(self, macro, loo):
        return {
            "equal_domain_macro": {"value": macro},
            "leave_one_domain_out": {
                "minimum": {"value": min(loo.values())},
                "values": {
                    domain: {"value": value}
                    for domain, value in loo.items()
                },
            },
        }

    def contrast(self, candidate, reference, ratio=0.8, coverage=0):
        rows = []
        for domain in ("d1", "d2"):
            rows.append({
                "domain": domain,
                "candidate_effort": 8,
                "reference_effort": 10,
                "candidate_only": max(coverage, 0),
                "reference_only": max(-coverage, 0),
            })
        return {
            "candidate": candidate,
            "reference": reference,
            "coverage": {"candidate_minus_reference": 2 * coverage},
            "conditional_effort": {
                "candidate_total": 16,
                "reference_total": 20,
                "candidate_over_reference": {"value": ratio},
            },
            "by_domain": rows,
        }

    def test_all_positive_preregistered_gates_pass(self):
        fragmentation = {
            "cofactor_width": self.rank(0.70, {"d1": 0.69, "d2": 0.71}),
            "quality": self.rank(0.55, {"d1": 0.54, "d2": 0.56}),
            "total_add_nodes": self.rank(
                0.71, {"d1": 0.70, "d2": 0.72}
            ),
        }
        certificates = {
            "B_profile": self.rank(0.80, {"d1": 0.79, "d2": 0.81}),
            "B_width": self.rank(0.75, {"d1": 0.74, "d2": 0.76}),
            "B_add": self.rank(0.76, {"d1": 0.75, "d2": 0.77}),
        }
        width_add = []
        cap_exact = []
        selector_blind = []
        for k, u in A.P.MATCHED_BUDGETS:
            width = "pdb_cap_width_k{}".format(k)
            width_add.append(self.contrast(
                width, "pdb_cap_add_u{}".format(u), coverage=0
            ))
            cap_exact.append(self.contrast(
                width, "pdb_exact_k{}".format(k), coverage=1
            ))
            selector_blind.append(self.contrast(
                width, "blind_fw_profiled", coverage=1
            ))
        contrasts = {
            "matched_width_vs_add": width_add,
            "cap_width_vs_exact_width": cap_exact,
            "selector_vs_profiled_blind": selector_blind,
        }
        gates = A.decision_gates(fragmentation, certificates, contrasts)
        self.assertTrue(all(item["pass"] for item in gates.values()))


if __name__ == "__main__":
    unittest.main()
