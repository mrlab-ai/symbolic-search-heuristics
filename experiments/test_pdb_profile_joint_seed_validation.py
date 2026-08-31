#!/usr/bin/env python3
"""Adversarial tests for the unseen Gamer-seed validation."""

from __future__ import annotations

import copy
import unittest
from fractions import Fraction

import analyze_pdb_profile_joint_seed_validation as Analysis
import audit_pdb_profile_joint_seed_validation as Audit
import exp_pdb_profile_joint_seed_validation as E
import pdb_profile_joint_seed_validation_protocol as P
import recover_pdb_profile_joint_seed_validation as Recovery
from test_pdb_profile_order_intervention import OrderInterventionTest


class JointSeedValidationTest(unittest.TestCase):
    @staticmethod
    def eligible_record(order):
        record = OrderInterventionTest(
            "test_exact_certificate_arithmetic"
        ).eligible_record(order=order)
        record["wbh_profile_schema_version"] = 2
        record["wbh_profile_layer_profiles"][0][
            "joint_cofactor_counts"
        ] = [1, 4, 2]
        return record

    def test_protocol_and_runner_are_frozen_unthrottled_fat(self):
        P.validate_protocol_without_archive()
        self.assertEqual(P.SEEDS, (1, 2, 3, 4))
        self.assertEqual(P.CELL_COUNT, 4208)
        E.configure()
        self.assertEqual(E.Base.PARTITION, "fat")
        self.assertEqual(E.Base.RUNS_PER_ARRAY_TASK, 5)
        self.assertEqual(E.Base.EXPECTED_ARRAY_TASKS, 842)
        self.assertEqual(E.Base.SCHEDULER_TIME_LIMIT, "00:30:00")
        E.Base.self_test()

    def test_audit_and_recovery_pin_the_unthrottled_launch(self):
        Audit.configure()
        receipt = Audit.Audit.load_launch_receipt()
        self.assertEqual(receipt["job_id"], "1812576")
        self.assertEqual(receipt["partition"], "fat")
        self.assertEqual(receipt["array_throttle"], 0)
        Recovery.configure()
        self.assertEqual(
            Recovery.Recovery.RECOVERY_SCHEMA,
            Audit.Audit.RECOVERY_RECEIPT_SCHEMA,
        )
        self.assertEqual(
            Recovery.Recovery.E.SCHEDULER_TIME_LIMIT,
            "01:00:00",
        )
        cells = [
            cell
            for task in range(1, E.Base.EXPECTED_ARRAY_TASKS + 1)
            for cell in Recovery.Recovery._task_cells(task)
        ]
        self.assertEqual(cells, list(range(1, P.CELL_COUNT + 1)))

    def test_group_requires_semantically_identical_seed_cells(self):
        task = ("d", "p")
        matrix = {
            (label, task): self.eligible_record(
                "{:064x}".format(index + 1)
            )
            for index, label in enumerate(P.LABELS)
        }
        rows, grouped, statuses = Analysis.grouped_observations(
            matrix, [task]
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(grouped[task]), 4)
        self.assertEqual(statuses["seed_pair_distinct_order"], 6)

        changed = copy.deepcopy(matrix)
        changed[(P.LABELS[-1], task)]["expanded_states"] = 5
        with self.assertRaisesRegex(
            Analysis.SeedValidationAnalysisError,
            "changed semantic field expanded_states",
        ):
            Analysis.grouped_observations(changed, [task])

    @staticmethod
    def summary(predictors, *, comparable=150, tasks=75, domains=45):
        domain_names = ["d{:02d}".format(index) for index in range(45)]
        rows = {}
        for name, value in predictors.items():
            record = Analysis.Order._fraction_record(value)
            rows[name] = {
                "equal_domain_macro": record,
                "leave_one_domain_out": {
                    "values": {
                        domain: record for domain in domain_names
                    }
                },
            }
        return {
            "support": {
                "comparable": comparable,
                "tasks_with_comparable_pairs": tasks,
                "eligible_domains": domains,
            },
            "predictors": rows,
        }

    def test_gates_use_exact_frozen_thresholds_and_complete_lodo(self):
        primary = self.summary({
            "joint": Fraction(7, 10),
            "inverse_union": Fraction(2, 3),
        })
        absolute = self.summary({"joint": Fraction(13, 20)})
        gates = Analysis.decision_gates(primary, absolute)
        self.assertTrue(gates["joint_beyond_denominator_null"]["pass"])
        self.assertTrue(gates["absolute_joint_certificate"]["pass"])

        below_margin = copy.deepcopy(primary)
        below_margin["predictors"]["inverse_union"][
            "equal_domain_macro"
        ] = Analysis.Order._fraction_record(Fraction(69, 100))
        gates = Analysis.decision_gates(below_margin, absolute)
        self.assertFalse(
            gates["joint_beyond_denominator_null"]["pass"]
        )

        missing_lodo = copy.deepcopy(primary)
        missing_lodo["predictors"]["joint"]["leave_one_domain_out"][
            "values"
        ].pop("d00")
        gates = Analysis.decision_gates(missing_lodo, absolute)
        self.assertFalse(
            gates["joint_beyond_denominator_null"]["pass"]
        )


if __name__ == "__main__":
    unittest.main()
