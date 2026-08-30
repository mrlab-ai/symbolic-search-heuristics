#!/usr/bin/env python3
"""Adversarial tests for the prospective certificate holdout."""

from __future__ import annotations

import copy
import unittest
from collections import defaultdict
from fractions import Fraction
from unittest import mock

import analyze_pdb_profile_certificate_holdout as Analysis
import audit_pdb_profile_certificate_holdout as Audit
import exp_pdb_profile_certificate_holdout as E
import pdb_profile_certificate_holdout_protocol as P
import recover_pdb_profile_certificate_holdout as Recovery


class CertificateHoldoutAnalysisTest(unittest.TestCase):
    def test_launch_receipt_seals_unthrottled_fat_submission(self):
        receipt = Audit.load_launch_receipt()
        self.assertEqual(receipt["job_id"], "1807967")
        self.assertEqual(receipt["partition"], "fat")
        self.assertEqual(receipt["array_throttle"], 0)
        self.assertEqual(receipt["cells"], P.CELL_COUNT)

    def test_scheduler_audit_checks_exact_tasks_and_partition(self):
        output = (
            "7_2|702|RUNNING|0:0|n2|4|fat\n"
            "7_1|701|COMPLETED|0:0|n1|3|fat\n"
        )
        with mock.patch.object(
            Audit.subprocess, "check_output", return_value=output
        ):
            rows = Audit.scheduler_rows("7", {1, 2})
        self.assertEqual([row["array_task"] for row in rows], [1, 2])
        self.assertEqual([row["state"] for row in rows], ["COMPLETED", "RUNNING"])

        non_fat = output.replace("|fat\n", "|thin\n", 1)
        with mock.patch.object(
            Audit.subprocess, "check_output", return_value=non_fat
        ):
            with self.assertRaisesRegex(Audit.ExecutionAuditError, "non-fat"):
                Audit.scheduler_rows("7", {1, 2})

    def test_recovery_task_partition_covers_every_cell_once(self):
        cells = [
            cell
            for task in range(1, E.EXPECTED_ARRAY_TASKS + 1)
            for cell in Recovery._task_cells(task)
        ]
        self.assertEqual(cells, list(range(1, P.CELL_COUNT + 1)))
        self.assertEqual(
            Audit._run_dir(P.CELL_COUNT).parent.name,
            "runs-17801-17900",
        )

    def test_runner_is_full_unthrottled_fat_array(self):
        self.assertEqual(E.PARTITION, "fat")
        self.assertEqual(E.RUNS_PER_ARRAY_TASK, 18)
        self.assertEqual(E.EXPECTED_ARRAY_TASKS, 994)
        self.assertEqual(
            (P.CELL_COUNT + E.RUNS_PER_ARRAY_TASK - 1)
            // E.RUNS_PER_ARRAY_TASK,
            E.EXPECTED_ARRAY_TASKS,
        )
        E.self_test()

    def presearch_record(self, label):
        return {
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
            "local_revision": P.PLANNER_REVISION,
            "global_revision": P.PLANNER_REVISION,
            "planner_exit_code": 10,
            "error": "translate-unsolvable",
            "coverage": 0,
            "unsolvable": 1,
            "unexplained_errors": [],
            "construction_completed": None,
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
            "planner_revision": P.PLANNER_REVISION,
            "planner_binary_sha256": P.PLANNER_BINARY_SHA256,
            "preprocess_binary_sha256": P.PREPROCESS_BINARY_SHA256,
            "planner_preprocess_sha256": P.PREPROCESS_BINARY_SHA256,
            "required_lab_version": P.REQUIRED_LAB_VERSION,
            "planner_time_limit": float(P.TIME_LIMIT_SECONDS),
            "planner_memory_limit": P.MEMORY_LIMIT_MIB,
            "external_validation_requested": False,
            "slurm_partition": "fat",
            "array_throttle": 0,
        }

    def one_task_matrix(self):
        return [self.presearch_record(label) for label in P.LABELS]

    def eligible_record(self, *, effort=6):
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
            "pdb_profile_selector_trace_certified": True,
            "wbh_profile_state_bits": 2,
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

    def test_protocol_identity_and_exact_holdout_subtraction(self):
        P.validate_protocol_without_archive()
        cohort = P.load_cohort()
        self.assertEqual(len(cohort), 1052)
        self.assertEqual(len({task.domain for task in cohort}), 45)
        self.assertEqual(P.option_matrix_digest(), P.OPTION_MATRIX_SHA256)

    def test_matrix_accepts_exact_unthrottled_fat_identity(self):
        matrix, tasks, outcomes = Analysis.validate_matrix(
            self.one_task_matrix(), expected_tasks=1
        )
        self.assertEqual(tasks, [("d", "p.pddl")])
        self.assertEqual(len(matrix), P.CONFIG_COUNT)
        self.assertEqual(set(outcomes.values()), {"presearch"})

    def test_matrix_rejects_throttle_and_duplicate(self):
        records = self.one_task_matrix()
        records[0]["array_throttle"] = 2
        with self.assertRaisesRegex(
            Analysis.CertificateHoldoutAnalysisError, "array_throttle"
        ):
            Analysis.validate_matrix(records, expected_tasks=1)
        records = self.one_task_matrix()
        records[-1] = copy.deepcopy(records[0])
        with self.assertRaisesRegex(
            Analysis.CertificateHoldoutAnalysisError, "duplicate"
        ):
            Analysis.validate_matrix(records, expected_tasks=1)

    def test_exact_cut_aligned_formula_and_normalization(self):
        status, observation = Analysis._certificate_observation(
            self.eligible_record(), ("d", "p"), P.PDB_LABELS[0]
        )
        self.assertEqual(status, "eligible")
        # V_0 * [(1 * 1) + (3 * 4)] = 2 * 13.
        self.assertEqual(observation["B_profile"], 26)
        self.assertEqual(observation["B_width"], 32)
        self.assertEqual(observation["B_add"], 54)
        self.assertEqual(observation["R_profile"], Fraction(26, 3))
        self.assertEqual(observation["_fragmentation"], (6, 3))

    def test_terminal_cut_is_excluded(self):
        original = self.eligible_record()
        changed = copy.deepcopy(original)
        changed["wbh_profile_layer_profiles"][0]["cofactor_counts"][-1] = 1
        changed["wbh_profile_heuristic_profile"]["cofactor_counts"][-1] = 1
        _, before = Analysis._certificate_observation(
            original, ("d", "p"), P.PDB_LABELS[0]
        )
        _, after = Analysis._certificate_observation(
            changed, ("d", "p"), P.PDB_LABELS[0]
        )
        self.assertEqual(before["B_profile"], after["B_profile"])
        self.assertEqual(before["B_width"], after["B_width"])

    def test_certificate_violation_aborts(self):
        record = self.eligible_record(effort=55)
        with self.assertRaisesRegex(
            Analysis.CertificateHoldoutAnalysisError,
            "exceeds a theorem certificate",
        ):
            Analysis._certificate_observation(
                record, ("d", "p"), P.PDB_LABELS[0]
            )

    def test_duplicate_semantics_require_identical_measurements(self):
        task = ("d", "p")
        matrix = {
            (label, task): self.eligible_record()
            for label in P.PDB_LABELS
        }
        changed = matrix[(P.PDB_LABELS[-1], task)]
        changed["effort"] = 7
        changed["wbh_expansion_profile"][0]["effort"] = 7
        with self.assertRaisesRegex(
            Analysis.CertificateHoldoutAnalysisError,
            "different deterministic evidence",
        ):
            Analysis.observations(matrix, [task])

    @staticmethod
    def shared(macros):
        domains = ["d{:02d}".format(index) for index in range(P.COHORT_DOMAINS)]
        predictors = {}
        for name, value in macros.items():
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

    def test_mechanism_gates_pass_only_the_frozen_story(self):
        representation = self.shared({
            "profile": Fraction(4, 5),
            "width": Fraction(79, 100),
            "add": Fraction(39, 50),
        })
        profile_quality = self.shared({
            "profile": Fraction(4, 5), "quality": Fraction(2, 5)
        })
        guidance = self.shared({
            "profile": Fraction(3, 10), "quality": Fraction(9, 10)
        })
        gates = Analysis.mechanism_gates(
            representation, profile_quality, guidance, guidance
        )
        self.assertTrue(gates["useful_fragmentation_certificate"]["pass"])
        self.assertTrue(gates["sharper_representation_predictor"]["pass"])
        self.assertTrue(gates["two_effect_separation"]["pass"])

        failed = copy.deepcopy(profile_quality)
        failed["predictors"]["profile"]["leave_one_domain_out"][
            "values"
        ].pop("d00")
        gates = Analysis.mechanism_gates(
            representation, failed, guidance, guidance
        )
        self.assertFalse(gates["useful_fragmentation_certificate"]["pass"])
        self.assertFalse(gates["two_effect_separation"]["pass"])

    def test_selector_gates_use_all_five_budgets(self):
        def contrast(ratio=Fraction(9, 10), coverage=0):
            return {
                "conditional_effort": {
                    "eligible_pairs": P.MIN_TASKS_WITH_COMPARABLE_PAIRS,
                    "candidate_total": ratio.numerator,
                    "reference_total": ratio.denominator,
                    "candidate_over_reference": Analysis._fraction_record(ratio),
                },
                "coverage": {"candidate_minus_reference": coverage},
                "by_domain": [
                    {"effort_eligible_pairs": 1}
                    for _ in range(P.MIN_DOMAINS)
                ],
            }

        contrasts = {
            "matched_width_vs_add": [contrast() for _ in range(5)],
            "cap_width_vs_exact_width": [contrast() for _ in range(5)],
        }
        gates = Analysis.selector_gates(contrasts)
        self.assertTrue(gates["width_vs_matched_add"]["pass"])
        self.assertTrue(gates["cap_width_vs_exact_width"]["pass"])
        contrasts["matched_width_vs_add"][0] = contrast(Fraction(11, 10), -3)
        contrasts["matched_width_vs_add"][1] = contrast(Fraction(11, 10))
        gates = Analysis.selector_gates(contrasts)
        self.assertFalse(gates["width_vs_matched_add"]["pass"])


if __name__ == "__main__":
    unittest.main()
