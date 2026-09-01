#!/usr/bin/env python3

from __future__ import annotations

import unittest

import pdb_terminal_metric_choice_analyzer as Analyzer
import pdb_terminal_metric_choice_protocol as P
from test_pdb_terminal_metric_choice_execution import FREEZE_SHA, fake_records
from test_pdb_terminal_metric_choice_protocol import fake_freeze, fake_standalone


class AnalyzerTest(unittest.TestCase):
    def analyze(self, records):
        freeze = fake_freeze()
        return Analyzer.analyze(
            records, freeze, FREEZE_SHA,
            fake_standalone(freeze["base_confirmation_b"]),
            bootstrap_replicates=500,
        )

    def test_primary_and_differing_subset_gate_pass(self):
        result = self.analyze(fake_records(differing_tasks=100))
        self.assertTrue(result["pass"])
        self.assertTrue(result["primary_i_vs_mj"]["pass"])
        subset = result["differing_winner_subset_i_vs_mj"]
        self.assertEqual(subset["tasks"], 100)
        self.assertEqual(subset["families"], 10)
        self.assertTrue(all(subset["support_clauses"].values()))
        self.assertTrue(all(subset["clauses"].values()))

    def test_macro_threshold_is_exactly_gating(self):
        records = fake_records()
        for row in records:
            if row["algorithm"] == P.INCIDENCE_MODE:
                row["total_time"] = 290.0
        result = self.analyze(records)
        self.assertFalse(result["pass"])
        self.assertFalse(result["primary_i_vs_mj"]["clauses"][
            "equal_family_normalized_par2_at_least_0_02"
        ])

    def test_differing_subset_support_is_gating(self):
        result = self.analyze(fake_records(differing_tasks=40))
        self.assertFalse(result["pass"])
        subset = result["differing_winner_subset_i_vs_mj"]
        self.assertFalse(subset["support_clauses"]["tasks_at_least_50"])
        self.assertFalse(subset["support_clauses"]["families_at_least_10"])

    def test_incidence_coverage_must_be_nonlower(self):
        records = fake_records()
        first = next(
            row for row in records if row["algorithm"] == P.INCIDENCE_MODE
        )
        first["coverage"] = 0
        result = self.analyze(records)
        self.assertFalse(result["primary_i_vs_mj"]["clauses"][
            "coverage_nonlower"
        ])
        self.assertFalse(result["pass"])

    def test_matched_contrast_is_secondary_only(self):
        records = fake_records()
        for row in records:
            if row["algorithm"] == P.MATCHED_MODE:
                row["total_time"] = 50.0
        result = self.analyze(records)
        self.assertTrue(result["pass"])
        self.assertFalse(result["secondary_i_vs_matched"]["pass"])
        self.assertFalse(result["secondary_i_vs_matched"][
            "affects_primary_gate"
        ])


if __name__ == "__main__":
    unittest.main()
