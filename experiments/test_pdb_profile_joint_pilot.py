#!/usr/bin/env python3
"""Tests for the co-occurring-residual development pilot."""

from __future__ import annotations

import copy
import unittest
from fractions import Fraction

import analyze_pdb_profile_joint_pilot as Analysis
import pdb_profile_joint_pilot_protocol as P
from test_pdb_profile_order_intervention import OrderInterventionTest


class JointPilotTest(unittest.TestCase):
    @staticmethod
    def eligible_record():
        record = OrderInterventionTest(
            "test_exact_certificate_arithmetic"
        ).eligible_record()
        record["wbh_profile_schema_version"] = 2
        record["wbh_profile_layer_profiles"][0][
            "joint_cofactor_counts"
        ] = [1, 4, 2]
        return record

    def test_exact_joint_certificate_chain(self):
        status, item = Analysis._joint_observation(
            self.eligible_record(), ("d", "p"), P.LABELS[0]
        )
        self.assertEqual(status, "eligible")
        self.assertEqual(item["B_joint"], 10)
        self.assertEqual(item["R_joint"], Fraction(10, 3))
        self.assertEqual(item["inverse_union"], Fraction(1, 3))
        self.assertLessEqual(item["actual_effort"], item["B_joint"])
        self.assertLessEqual(item["B_joint"], item["B_profile"])

    def test_joint_profile_bounds_are_fail_closed(self):
        record = copy.deepcopy(self.eligible_record())
        record["wbh_profile_layer_profiles"][0][
            "joint_cofactor_counts"
        ] = [1, 3, 2]
        with self.assertRaisesRegex(
            Analysis.JointPilotAnalysisError, "cut bounds"
        ):
            Analysis._joint_observation(record, ("d", "p"), P.LABELS[0])


if __name__ == "__main__":
    unittest.main()
