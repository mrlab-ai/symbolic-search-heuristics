#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_pdb_cap_grid_full as analyzer
import pdb_cap_grid_full_protocol as P


class FocusedFullAnalysisTests(unittest.TestCase):
    def test_self_test(self):
        analyzer.self_test()

    def test_analysis_pin_gate_precedes_properties_read(self):
        old = (
            analyzer.EXPECTED_PROTOCOL_REVISION,
            analyzer.EXPECTED_PROPERTIES_CANONICAL_SHA256,
            analyzer.EXPECTED_PROSPECTIVE_JOB_SHA256,
            P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256,
        )
        analyzer.EXPECTED_PROTOCOL_REVISION = None
        analyzer.EXPECTED_PROPERTIES_CANONICAL_SHA256 = None
        analyzer.EXPECTED_PROSPECTIVE_JOB_SHA256 = None
        P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256 = None
        try:
            with mock.patch.object(
                analyzer.full_analysis,
                "load_properties",
                side_effect=AssertionError("properties loader must not run"),
            ) as loader:
                with self.assertRaisesRegex(
                    analyzer.AnalysisError, "refusing to read outcomes"
                ):
                    analyzer.main(["--properties", "/outcome/path"])
                loader.assert_not_called()
        finally:
            (
                analyzer.EXPECTED_PROTOCOL_REVISION,
                analyzer.EXPECTED_PROPERTIES_CANONICAL_SHA256,
                analyzer.EXPECTED_PROSPECTIVE_JOB_SHA256,
                P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256,
            ) = old

    def test_mechanism_requires_all_raw_pool_pairs(self):
        tasks = [("d", "p1"), ("d", "p2")]
        matrix = {}
        for index, task in enumerate(tasks):
            exact, cap = analyzer._synthetic_pool_records(False, index == 0)
            exact.update({"coverage": 1, "planner_time": 1.0})
            cap.update({"coverage": 1, "planner_time": 1.0})
            matrix[(P.EXACT, task)] = exact
            matrix[(P.CAP, task)] = cap
        self.assertEqual(
            analyzer.contrast(matrix, tasks, "test")["mechanism"]["status"],
            "certified",
        )
        matrix[(P.CAP, tasks[1])]["pdb_selector_candidates"][0][
            "raw_width_upper_bound"
        ] = 2
        mechanism = analyzer.contrast(matrix, tasks, "test")["mechanism"]
        self.assertEqual(mechanism["status"], "not-certified")
        self.assertEqual(mechanism["same_k_raw_pool_identity_pairs"], 1)


if __name__ == "__main__":
    unittest.main()
