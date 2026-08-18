#!/usr/bin/env python3

import sys
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_pdb_cap_grid_full as analyzer
import pdb_cap_grid_full_protocol as P
import pdb_cap_grid_full_secondary_contract as secondary


class FocusedFullAnalysisTests(unittest.TestCase):
    def test_secondary_contract_is_frozen(self):
        self.assertEqual(
            secondary.validate_contract(),
            "1df86a1255cb301ffe2b6eb0db52ba81ca7f8c511e5a011cd028d8eff2dfc862",
        )

    def test_count_summary_preserves_exact_integer_total(self):
        summary = analyzer._count_summary([1, 2, 3])
        self.assertIs(type(summary["total"]), int)
        self.assertEqual(summary["total"], 6)
        self.assertIsNone(analyzer._count_summary([])["total"])
        with self.assertRaisesRegex(
            analyzer.AnalysisError, "exact nonnegative integers"
        ):
            analyzer._count_summary([1, 2.0])

    def test_self_test(self):
        analyzer.self_test()

    def test_analysis_pin_gate_precedes_properties_read(self):
        old = (
            analyzer.EXPECTED_PROTOCOL_REVISION,
            analyzer.EXPECTED_PROPERTIES_CANONICAL_SHA256,
            analyzer.EXPECTED_PROSPECTIVE_JOB_SHA256,
            P.PROTOCOL_IMPLEMENTATION_REVISION,
            P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256,
        )
        analyzer.EXPECTED_PROTOCOL_REVISION = None
        analyzer.EXPECTED_PROPERTIES_CANONICAL_SHA256 = None
        analyzer.EXPECTED_PROSPECTIVE_JOB_SHA256 = None
        P.PROTOCOL_IMPLEMENTATION_REVISION = None
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
                P.PROTOCOL_IMPLEMENTATION_REVISION,
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

    def test_secondary_descriptive_scope_directions_and_denominators(self):
        tasks = [("d", "p1"), ("d", "p2")]
        matrix = {}
        for index, task in enumerate(tasks):
            exact, cap = analyzer._synthetic_pool_records(False, True)
            exact["pdb_selector_selected"].update(
                {
                    "sources": ["empty"],
                    "pattern": [],
                    "cofactor_width": 1,
                    "width_upper_bound": 1,
                }
            )
            exact.update(
                {
                    "add_nodes": 0,
                    "num_terminals": 1,
                    "num_values": 1,
                }
            )
            cap["pdb_selector_selected"].update(
                {
                    "sources": ["goal_prefix"],
                    "pattern": [1, 2],
                    "value_cap": 2,
                    "cofactor_width": 4,
                    "width_upper_bound": 9,
                    "add_nodes": 6,
                    "num_terminals": 3,
                    "transformed_num_values": 3,
                }
            )
            for record, time, image, nodes, construction in (
                (exact, 4.0 + index, 10.0, 100, 2.0),
                (cap, 2.0 + index, 20.0, 80, 3.0),
            ):
                record.update(
                    {
                        "coverage": 1,
                        "planner_time": time,
                        "image_time": image,
                        "expanded_bdd_nodes": nodes,
                        "construction_completed": True,
                        "construction_time": construction,
                        "test_complete_image": True,
                    }
                )
            matrix[(P.EXACT, task)] = exact
            matrix[(P.CAP, task)] = cap

        with mock.patch.object(
            analyzer.cap_analysis.legacy,
            "certified_image_cell",
            side_effect=lambda record: record["test_complete_image"],
        ):
            result = analyzer.secondary_descriptive_scope(matrix, tasks)

        cap_summary = result["selector_summary"][P.CAP]
        self.assertEqual(cap_summary["effective_cap_histogram"], {"2": 2})
        self.assertEqual(
            cap_summary["selected_first_provenance_source"]["goal_prefix"], 2
        )
        paired = result["paired_operational"]
        self.assertEqual(
            paired["micro_par2_seconds"],
            {
                "fixed_task_denominator": 2,
                "candidate_solved": 2,
                "reference_solved": 2,
                "candidate_solved_planner_cpu_total_seconds": 5.0,
                "reference_solved_planner_cpu_total_seconds": 9.0,
                "candidate": 2.5,
                "reference": 4.5,
                "candidate_minus_reference": -2.0,
            },
        )
        self.assertEqual(
            paired["complete_certified_image_time"]["eligible_pair_count"], 2
        )
        self.assertEqual(
            paired["complete_certified_image_time"]["candidate_over_reference"],
            2.0,
        )
        self.assertEqual(
            paired["complete_certified_expanded_bdd_nodes"][
                "candidate_over_reference"
            ],
            0.8,
        )
        self.assertEqual(
            paired["observed_completed_construction_time"][
                "candidate_over_reference"
            ],
            1.5,
        )
        self.assertEqual(
            paired["jointly_solved_planner_cpu"]["eligible_pair_count"], 2
        )

    def test_secondary_par2_carries_exact_solved_runtime_identity(self):
        tasks = [("d", "solved"), ("d", "unsolved")]
        matrix = {
            (P.CAP, tasks[0]): {"coverage": 1, "planner_time": 2.0},
            (P.CAP, tasks[1]): {"coverage": 0},
            (P.EXACT, tasks[0]): {"coverage": 1, "planner_time": 4.0},
            (P.EXACT, tasks[1]): {"coverage": 0},
        }
        with mock.patch.object(
            analyzer,
            "selector_summary",
            side_effect=lambda *args: {"synthetic": True},
        ), mock.patch.object(
            analyzer.cap_analysis.legacy,
            "certified_image_cell",
            return_value=False,
        ):
            result = analyzer.secondary_descriptive_scope(matrix, tasks)
        par2 = result["paired_operational"]["micro_par2_seconds"]
        self.assertEqual(par2["candidate_solved"], 1)
        self.assertEqual(par2["reference_solved"], 1)
        self.assertEqual(
            par2["candidate_solved_planner_cpu_total_seconds"], 2.0
        )
        self.assertEqual(
            par2["reference_solved_planner_cpu_total_seconds"], 4.0
        )
        self.assertEqual(par2["candidate"], 301.0)
        self.assertEqual(par2["reference"], 302.0)

    def test_width_only_certified_trace_has_fieldwise_denominators(self):
        task = ("d", "p")
        exact, _ = analyzer._synthetic_pool_records(False, True)
        exact["pdb_selector_selected"].update(
            {
                "sources": ["empty"],
                "pattern": [],
                "cofactor_width": 1,
                "width_upper_bound": 1,
            }
        )
        summary = analyzer.selector_summary(
            {(P.EXACT, task): exact}, [task], P.EXACT
        )
        self.assertEqual(summary["complete_certified_traces"], 1)
        self.assertEqual(summary["W"]["observed"], 1)
        self.assertEqual(summary["U"]["observed"], 1)
        self.assertEqual(summary["A"]["observed"], 0)
        self.assertEqual(summary["T"]["observed"], 0)
        self.assertEqual(summary["V"]["observed"], 0)

    def test_cpu_geomean_excludes_and_discloses_zero_time_pairs(self):
        tasks = [("d", "p1"), ("d", "p2")]
        matrix = {}
        for index, task in enumerate(tasks):
            exact = {
                "coverage": 1,
                "planner_time": 0.0 if index == 0 else 4.0,
            }
            cap = {"coverage": 1, "planner_time": 0.0 if index == 0 else 2.0}
            matrix[(P.EXACT, task)] = exact
            matrix[(P.CAP, task)] = cap
        result = analyzer._jointly_solved_cpu_ratio(matrix, tasks)
        self.assertEqual(result["jointly_solved_pair_count"], 2)
        self.assertEqual(result["eligible_pair_count"], 1)
        self.assertEqual(result["excluded_nonpositive_pair_count"], 1)
        self.assertAlmostEqual(result["candidate_over_reference"], 0.5)


if __name__ == "__main__":
    unittest.main()
