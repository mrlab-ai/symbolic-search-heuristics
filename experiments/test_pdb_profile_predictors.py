#!/usr/bin/env python3

from __future__ import annotations

import copy
import unittest
from collections import defaultdict
from fractions import Fraction

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

    def test_shared_comparison_cannot_select_different_tie_subsets(self):
        grouped = defaultdict(dict)
        grouped[("d1", "p")]["a"] = {
            "cofactor_width": 1,
            "total_add_nodes": 1,
            "_quality": (1,),
            "_fragmentation": (1, 1),
        }
        grouped[("d1", "p")]["b"] = {
            "cofactor_width": 2,
            "total_add_nodes": 1,
            "_quality": (2,),
            "_fragmentation": (2, 1),
        }
        grouped[("d2", "p")]["a"] = {
            "cofactor_width": 1,
            "total_add_nodes": 1,
            "_quality": (1,),
            "_fragmentation": (1, 1),
        }
        grouped[("d2", "p")]["b"] = {
            "cofactor_width": 1,
            "total_add_nodes": 2,
            "_quality": (2,),
            "_fragmentation": (2, 1),
        }
        result = A.fragmentation_gate_comparison(grouped, {"d1", "d2"})
        self.assertEqual(result["support"]["comparable"], 0)
        self.assertEqual(result["support"]["any_predictor_tied"], 2)
        self.assertTrue(all(
            summary["comparable"] == 0
            for summary in result["predictors"].values()
        ))


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
    def fraction(self, value):
        if not isinstance(value, Fraction):
            value = Fraction(str(value))
        return A._fraction_record(value)

    def rank(self, macro, loo):
        values = {
            "d{}".format(index): loo.get("d{}".format(index), macro)
            for index in range(1, A.P.COHORT_DOMAINS + 1)
        }
        return {
            "eligible_domains": A.P.COHORT_DOMAINS,
            "tasks_with_comparable_pairs": A.MIN_STRONG_CLAIM_TASKS,
            "equal_domain_macro": self.fraction(macro),
            "leave_one_domain_out": {
                "minimum": self.fraction(min(values.values())),
                "values": {
                    domain: self.fraction(value)
                    for domain, value in values.items()
                },
            },
        }

    def contrast(self, candidate, reference, ratio=0.8, coverage=0):
        ratio = ratio if isinstance(ratio, Fraction) else Fraction(str(ratio))
        candidate_total = ratio.numerator * 1000
        reference_total = ratio.denominator * 1000

        def distribute(total):
            quotient, remainder = divmod(total, A.P.COHORT_DOMAINS)
            return [
                quotient + (index < remainder)
                for index in range(A.P.COHORT_DOMAINS)
            ]

        candidate_by_domain = distribute(candidate_total)
        reference_by_domain = distribute(reference_total)
        eligible_by_domain = distribute(A.MIN_STRONG_CLAIM_TASKS)
        rows = []
        for index in range(A.P.COHORT_DOMAINS):
            rows.append({
                "domain": "d{}".format(index + 1),
                "candidate_effort": candidate_by_domain[index],
                "reference_effort": reference_by_domain[index],
                "effort_eligible_pairs": eligible_by_domain[index],
                "candidate_only": max(coverage, 0),
                "reference_only": max(-coverage, 0),
            })
        return {
            "candidate": candidate,
            "reference": reference,
            "coverage": {
                "candidate_minus_reference": A.P.COHORT_DOMAINS * coverage
            },
            "conditional_effort": {
                "eligible_pairs": A.MIN_STRONG_CLAIM_TASKS,
                "candidate_total": candidate_total,
                "reference_total": reference_total,
                "candidate_over_reference": self.fraction(ratio),
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

    def test_gate_directions_use_exact_rationals_at_float_resolution(self):
        tiny = Fraction(1, 10**18)
        fragmentation = {
            "cofactor_width": self.rank(
                Fraction(7, 10),
                {"d1": Fraction(7, 10), "d2": Fraction(7, 10)},
            ),
            "quality": self.rank(
                Fraction(11, 20),
                {"d1": Fraction(11, 20), "d2": Fraction(11, 20)},
            ),
            "total_add_nodes": self.rank(
                Fraction(71, 100),
                {"d1": Fraction(71, 100), "d2": Fraction(71, 100)},
            ),
        }
        certificates = {
            "B_profile": self.rank(
                Fraction(4, 5),
                {"d1": Fraction(1, 2) + tiny, "d2": Fraction(4, 5)},
            ),
            "B_width": self.rank(
                Fraction(3, 4),
                {"d1": Fraction(1, 2), "d2": Fraction(3, 4)},
            ),
            "B_add": self.rank(
                Fraction(19, 25),
                {"d1": Fraction(1, 2), "d2": Fraction(19, 25)},
            ),
        }
        near_one = Fraction(10**18 - 1, 10**18)
        width_add = []
        cap_exact = []
        selector_blind = []
        for k, u in A.P.MATCHED_BUDGETS:
            width = "pdb_cap_width_k{}".format(k)
            width_add.append(self.contrast(
                width, "pdb_cap_add_u{}".format(u), ratio=near_one
            ))
            cap_exact.append(self.contrast(
                width, "pdb_exact_k{}".format(k), ratio=near_one
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
        self.assertTrue(
            gates["cut_aligned_profile_sharper_explanation"]["criteria"][
                "positive_every_loo"
            ]
        )
        self.assertTrue(
            gates["width_filter_materially_lower_effort_than_matched_add"]["criteria"][
                "effort_wins_at_least_4_of_5"
            ]
        )
        self.assertFalse(
            gates["width_filter_materially_lower_effort_than_matched_add"][
                "criteria"
            ]["all_budget_effort_reduction_at_least_0_02"]
        )

    def test_sparse_support_and_missing_loo_fail_closed(self):
        fragmentation = {
            "cofactor_width": self.rank(0.70, {}),
            "quality": self.rank(0.55, {}),
            "total_add_nodes": self.rank(0.71, {}),
        }
        certificates = {
            "B_profile": self.rank(0.80, {}),
            "B_width": self.rank(0.75, {}),
            "B_add": self.rank(0.76, {}),
        }
        contrasts = self.positive_contrasts()
        sparse = copy.deepcopy(fragmentation)
        for summary in sparse.values():
            summary["eligible_domains"] = 2
            summary["tasks_with_comparable_pairs"] = 2
        gates = A.decision_gates(sparse, certificates, contrasts)
        self.assertFalse(
            gates["cofactor_width_useful_fragmentation_predictor"]["pass"]
        )

        missing = copy.deepcopy(certificates)
        missing["B_add"]["leave_one_domain_out"]["values"].pop("d46")
        gates = A.decision_gates(fragmentation, missing, contrasts)
        self.assertFalse(
            gates["cut_aligned_profile_sharper_explanation"]["pass"]
        )

        truncated = self.positive_contrasts()
        for item in truncated["matched_width_vs_add"]:
            item["by_domain"].pop()
        with self.assertRaisesRegex(
            A.PredictorAnalysisError, "domain universe is incomplete"
        ):
            A.decision_gates(fragmentation, certificates, truncated)

    def positive_contrasts(self):
        width_add = []
        cap_exact = []
        selector_blind = []
        for k, u in A.P.MATCHED_BUDGETS:
            width = "pdb_cap_width_k{}".format(k)
            width_add.append(self.contrast(
                width, "pdb_cap_add_u{}".format(u)
            ))
            cap_exact.append(self.contrast(
                width, "pdb_exact_k{}".format(k), coverage=1
            ))
            selector_blind.append(self.contrast(
                width, "blind_fw_profiled", coverage=1
            ))
        return {
            "matched_width_vs_add": width_add,
            "cap_width_vs_exact_width": cap_exact,
            "selector_vs_profiled_blind": selector_blind,
        }

    def test_blind_gate_is_coverage_only_and_requires_construction(self):
        fragmentation = {
            "cofactor_width": self.rank(0.70, {}),
            "quality": self.rank(0.55, {}),
            "total_add_nodes": self.rank(0.71, {}),
        }
        certificates = {
            "B_profile": self.rank(0.80, {}),
            "B_width": self.rank(0.75, {}),
            "B_add": self.rank(0.76, {}),
        }
        contrasts = self.positive_contrasts()
        for item in contrasts["cap_width_vs_exact_width"]:
            failed = self.contrast(item["candidate"], item["reference"], ratio=1.2)
            item.clear()
            item.update(failed)
        gates = A.decision_gates(fragmentation, certificates, contrasts)
        self.assertNotIn("cap_aware_width_generally_better_than_blind", gates)
        self.assertFalse(
            gates["cap_aware_width_higher_coverage_than_profiled_blind"]["pass"]
        )

    def test_cap_gate_rejects_catastrophic_budget_coverage_losses(self):
        fragmentation = {
            "cofactor_width": self.rank(0.70, {}),
            "quality": self.rank(0.55, {}),
            "total_add_nodes": self.rank(0.71, {}),
        }
        certificates = {
            "B_profile": self.rank(0.80, {}),
            "B_width": self.rank(0.75, {}),
            "B_add": self.rank(0.76, {}),
        }
        contrasts = self.positive_contrasts()
        replacements = []
        for index, item in enumerate(contrasts["cap_width_vs_exact_width"]):
            replacements.append(self.contrast(
                item["candidate"],
                item["reference"],
                coverage=-2 if index < 2 else 3,
            ))
        contrasts["cap_width_vs_exact_width"] = replacements
        gates = A.decision_gates(fragmentation, certificates, contrasts)
        gate = gates["cap_aware_width_materially_lower_effort_than_exact_width"]
        self.assertFalse(
            gate["criteria"]["no_budget_coverage_loss_below_minus_2"]
        )
        self.assertFalse(gate["pass"])


if __name__ == "__main__":
    unittest.main()
