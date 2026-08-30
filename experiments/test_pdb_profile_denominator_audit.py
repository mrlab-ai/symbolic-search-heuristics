#!/usr/bin/env python3
"""Adversarial tests for the prospective denominator audit."""

from __future__ import annotations

import copy
import unittest
from fractions import Fraction

import analyze_pdb_profile_certificate_holdout as Primary
import analyze_pdb_profile_denominator_audit as Analysis
import pdb_profile_certificate_holdout_protocol as Holdout
import pdb_profile_denominator_audit_protocol as P


class DenominatorAuditTest(unittest.TestCase):
    @staticmethod
    def observation():
        return {
            "domain": "d",
            "problem": "p.pddl",
            "semantic_id": ["fixed", 1],
            "semantic_union_effort": 2,
            "actual_effort": 6,
            "B_profile": 10,
            "B_width": 12,
            "B_add": 14,
            "fragmentation": Primary._fraction_record(Fraction(3, 1)),
            "R_profile": Primary._fraction_record(Fraction(5, 1)),
        }

    @staticmethod
    def shared(values):
        domains = [
            "d{:02d}".format(index)
            for index in range(Holdout.COHORT_DOMAINS)
        ]
        predictors = {}
        for name, value in values.items():
            record = Primary._fraction_record(value)
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

    def test_frozen_protocol(self):
        P.validate_protocol()

    def test_observation_arithmetic_is_exact(self):
        grouped = Analysis._group_observations({
            "observations": [self.observation()]
        })
        item = next(iter(grouped[("d", "p.pddl")].values()))
        self.assertEqual(item["R_profile"], Fraction(5, 1))
        self.assertEqual(item["_inverse_union"], Fraction(1, 2))
        self.assertEqual(item["_fragmentation"], (3, 1))

        changed = copy.deepcopy(self.observation())
        changed["R_profile"] = Primary._fraction_record(Fraction(9, 2))
        with self.assertRaisesRegex(
            Analysis.DenominatorAuditError, "R_profile arithmetic"
        ):
            Analysis._group_observations({"observations": [changed]})

    def test_both_frozen_robustness_gates(self):
        denominator = self.shared({
            "profile": Fraction(4, 5),
            "inverse_union": Fraction(1, 2),
        })
        absolute = self.shared({
            "profile": Fraction(4, 5),
            "width": Fraction(79, 100),
            "add": Fraction(39, 50),
        })
        gates = Analysis.decision_gates(denominator, absolute)
        self.assertTrue(gates["denominator_artifact_robustness"]["pass"])
        self.assertTrue(gates["absolute_certificate_robustness"]["pass"])

        failed = copy.deepcopy(denominator)
        failed["predictors"]["inverse_union"]["equal_domain_macro"] = (
            Primary._fraction_record(Fraction(7, 10))
        )
        gates = Analysis.decision_gates(failed, absolute)
        self.assertFalse(gates["denominator_artifact_robustness"]["pass"])


if __name__ == "__main__":
    unittest.main()
