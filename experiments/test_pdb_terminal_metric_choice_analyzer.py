#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import pdb_terminal_metric_choice_analyzer as Analyzer
import pdb_confirmation_run_cell as RunCell
import pdb_terminal_metric_choice_protocol as P
from test_pdb_terminal_metric_choice_execution import FREEZE_SHA, fake_records
from test_pdb_terminal_metric_choice_protocol import fake_freeze, fake_standalone


HARDWARE = {
    "hardware_attestation_schema": RunCell.HARDWARE_ATTESTATION_SCHEMA,
    "hardware_attestation_files": P.CELL_COUNT,
    "hardware_records_sha256": "d" * 64,
    "processor_model_counts": {"Synthetic CPU": P.CELL_COUNT},
    "architecture_counts": {"x86_64": P.CELL_COUNT},
}


class AnalyzerTest(unittest.TestCase):
    def test_analysis_v4_schema_and_paths(self):
        self.assertEqual(
            Analyzer.ANALYSIS_SCHEMA,
            P.FREEZE_SCHEMA + "/analysis/v4",
        )
        self.assertEqual(Analyzer.DEFAULT_OUTPUT.name, "analysis-v4.json")
        self.assertEqual(
            Analyzer.DEFAULT_REPEAT_OUTPUT.name, "analysis-v4-repeat.json"
        )
        self.assertEqual(
            Analyzer.DEFAULT_RECEIPT.name,
            "analysis-execution-receipt-v4.json",
        )

    def analyze(self, records):
        freeze = fake_freeze()
        return Analyzer.analyze(
            records, freeze, FREEZE_SHA,
            fake_standalone(freeze["base_confirmation_b"]),
            bootstrap_replicates=500,
        )

    @staticmethod
    def mechanism(records):
        freeze = fake_freeze()
        task_families = {
            (row["directory"], row["problem"]): row["family"]
            for row in P.guided_b_tasks(freeze["base_confirmation_b"])
        }
        matrix = {
            (row["algorithm"], (row["domain"], row["problem"])): row
            for row in records
        }
        return Analyzer._mechanism_diagnostics(
            matrix, sorted(task_families), task_families
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

    def test_par2_rejects_coverage_exit_contradictions(self):
        for record in (
            {"coverage": 1, "planner_exit_code": 23, "total_time": 1},
            {"coverage": 0, "planner_exit_code": 0},
        ):
            with self.subTest(record=record), self.assertRaises(
                Analyzer.AnalysisError
            ):
                Analyzer._par2(record)

    def test_contrast_reports_paired_coverage_and_common_solved_time(self):
        tasks = [("domain", "p{}.pddl".format(index)) for index in range(4)]

        def row(coverage, total_time=None):
            value = {
                "coverage": coverage,
                "planner_exit_code": 0 if coverage else 23,
                "family": "family",
            }
            if total_time is not None:
                value["total_time"] = total_time
            return value

        matrix = {
            (mode, task): row(1, 100 if mode == P.INCIDENCE_MODE else 200)
            for task in tasks for mode in (P.INCIDENCE_MODE, P.MJ_MODE)
        }
        matrix[(P.MJ_MODE, tasks[1])] = row(0)
        matrix[(P.INCIDENCE_MODE, tasks[2])] = row(0)
        matrix[(P.INCIDENCE_MODE, tasks[3])] = row(0)
        matrix[(P.MJ_MODE, tasks[3])] = row(0)
        result = Analyzer.contrast(
            matrix, tasks, P.INCIDENCE_MODE, P.MJ_MODE,
            replicates=100, seed=1,
        )
        decomposition = result["outcome_decomposition"]
        self.assertFalse(decomposition["gating"])
        self.assertEqual(decomposition["solve_pair_counts"], {
            "both_solved": 1,
            "intervention_only_solved": 1,
            "reference_only_solved": 1,
            "neither_solved": 1,
        })
        common = decomposition["common_solved"]
        self.assertEqual(common["tasks"], 1)
        self.assertEqual(common["families"], 1)
        self.assertEqual(
            common["equal_family_normalized_time_improvement"],
            Analyzer._fraction(Fraction(1, 18)),
        )

    def test_common_solved_time_uses_equal_family_weight(self):
        tasks = [("domain", "p{}.pddl".format(index)) for index in range(3)]
        matrix = {}
        for index, task in enumerate(tasks):
            family = "large" if index < 2 else "small"
            left_time, right_time = (
                (100, 200) if index < 2 else (200, 100)
            )
            matrix[(P.INCIDENCE_MODE, task)] = {
                "coverage": 1, "planner_exit_code": 0,
                "total_time": left_time, "family": family,
            }
            matrix[(P.MJ_MODE, task)] = {
                "coverage": 1, "planner_exit_code": 0,
                "total_time": right_time, "family": family,
            }
        result = Analyzer.contrast(
            matrix, tasks, P.INCIDENCE_MODE, P.MJ_MODE,
            replicates=100, seed=1,
        )
        common = result["outcome_decomposition"]["common_solved"]
        self.assertEqual(
            common["equal_family_normalized_time_improvement"],
            Analyzer._fraction(Fraction(0)),
        )

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
        first["planner_exit_code"] = 23
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

    def test_short_triads_are_conservative_full_cohort_ties_only(self):
        result = self.analyze(fake_records(
            differing_tasks=300, short_probe_tasks=10
        ))
        primary = result["primary_i_vs_mj"]
        secondary = result["secondary_i_vs_matched"]
        subset = result["differing_winner_subset_i_vs_mj"]
        self.assertEqual(primary["tasks"], 300)
        self.assertEqual(secondary["tasks"], 300)
        self.assertEqual(subset["tasks"], 290)
        self.assertEqual(result["audit"]["status_counts"], {
            "complete": 290, "short_probe": 10,
        })
        self.assertEqual(result["probe_support"], {
            "complete_tasks": 290,
            "short_probe_tasks": 10,
            "complete_families": 29,
            "short_probe_families": 1,
        })
        short_key = "domain-029:p299.pddl"
        self.assertEqual(primary["task_normalized_improvements"][short_key][
            "numerator"
        ], 0)
        self.assertEqual(secondary[
            "task_normalized_improvements"
        ][short_key]["numerator"], 0)
        self.assertEqual(primary[
            "equal_family_normalized_par2_improvement"
        ]["numerator"], 29)
        self.assertEqual(primary[
            "equal_family_normalized_par2_improvement"
        ]["denominator"], 540)
        mechanism = result["mechanism_diagnostics"]
        self.assertFalse(mechanism["gating"])
        self.assertEqual(mechanism["support"], {
            "all_tasks": 300,
            "complete_tasks": 290,
            "short_probe_tasks": 10,
            "complete_families": 29,
            "short_probe_families": 1,
        })
        self.assertEqual(len(mechanism["short_probe_rows"]), 10)
        self.assertNotIn("budgets", mechanism["short_probe_rows"][0])
        differing_score = mechanism["frozen_selection_score_relation"][
            "differing_incidence_mj_winners"
        ]
        self.assertEqual(
            set(differing_score["relation"]), set(Analyzer.SCORE_RELATIONS)
        )
        self.assertEqual(differing_score["relation"]["higher"], 290)
        self.assertEqual(sum(differing_score["relation"].values()), 290)
        self.assertEqual(
            set(differing_score["decisive_criterion"]),
            set(Analyzer.SCORE_CRITERIA),
        )
        self.assertEqual(differing_score["decisive_criterion"]["initial_h"], 290)
        self.assertEqual(
            sum(differing_score["decisive_criterion"].values()), 290
        )
        uptake = mechanism["treatment_uptake"]["incidence_differs_from_mj"]
        self.assertNotIn("fraction_of_all_tasks", uptake)
        self.assertIn("families_with_at_least_one_task", uptake)
        self.assertEqual(
            set(mechanism["candidate_work"]), set(Analyzer.WORK_FIELDS)
        )
        self.assertEqual(
            set(mechanism["budget_geometry"]["binding_tasks"]),
            set(Analyzer.BUDGET_MODES),
        )
        self.assertEqual(
            set(mechanism["budget_geometry"]["cross_feasibility_counts"]),
            set(Analyzer.CROSS_GEOMETRY_OUTCOMES),
        )

    def test_mechanism_taxonomy_and_cap_order_are_fixed(self):
        base = {
            "pattern_index": 1, "sources": ["bdd_prefix"],
            "pattern": [0], "value_cap": 8,
            "terminal_incidence": 1, "masked_joint": 1,
        }
        same = copy.deepcopy(base)
        cap = {**base, "value_cap": None}
        pattern = {
            **base, "pattern_index": 2, "sources": ["goal_fill"],
            "pattern": [1],
        }
        self.assertEqual(Analyzer._change_class(base, same), "same_candidate")
        self.assertEqual(
            Analyzer._change_class(base, cap), "same_pattern_different_cap"
        )
        self.assertEqual(Analyzer._cap_direction(base, cap), "lower")
        self.assertEqual(Analyzer._cap_direction(cap, base), "higher")
        self.assertEqual(Analyzer._change_class(base, pattern), "different_pattern")
        self.assertIsNone(Analyzer._cap_direction(base, pattern))
        self.assertIsNone(Analyzer._ratio(0, 0))

    def test_score_relation_reports_every_frozen_decisive_criterion(self):
        base = {
            "initial_dead_end": False, "initial_h": 1,
            "finite_sum": 1, "finite_count": 1,
            "dead_count": 0, "abstract_states": 2,
            "cofactor_width": 2, "pattern": [1],
        }
        cases = {
            "initial_dead_end": ({**base, "initial_dead_end": True}, base),
            "initial_h": ({**base, "initial_h": 2}, base),
            "mean_finite": ({**base, "finite_sum": 2}, base),
            "dead_fraction": ({**base, "dead_count": 1}, base),
            "cofactor_width": ({**base, "cofactor_width": 1}, base),
            "abstract_states": (
                {**base, "abstract_states": 1},
                {**base, "abstract_states": 2},
            ),
            "pattern_tiebreak": ({**base, "pattern": [0]}, base),
            "tied": (base, copy.deepcopy(base)),
        }
        for criterion, (left, right) in cases.items():
            expected_relation = "tied" if criterion == "tied" else "higher"
            with self.subTest(criterion=criterion):
                self.assertEqual(
                    Analyzer._score_relation(left, right),
                    (expected_relation, criterion),
                )
                if criterion != "tied":
                    self.assertEqual(
                        Analyzer._score_relation(right, left),
                        ("lower", criterion),
                    )

    def test_mechanism_panel_exact_fixture(self):
        mechanism = self.mechanism(fake_records(differing_tasks=100))
        uptake = mechanism["treatment_uptake"]
        self.assertEqual(uptake["incidence_differs_from_mj"]["tasks"], 100)
        self.assertEqual(
            uptake["incidence_differs_from_mj"][
                "families_with_at_least_one_task"
            ],
            10,
        )
        self.assertEqual(
            uptake["incidence_differs_from_mj"][
                "fraction_of_complete_tasks"
            ]["numerator"],
            1,
        )
        self.assertEqual(
            uptake["incidence_differs_from_mj"][
                "fraction_of_complete_tasks"
            ]["denominator"],
            3,
        )
        self.assertEqual(uptake["all_same"]["tasks"], 200)
        self.assertEqual(uptake["both_differ_from_reference"]["tasks"], 0)

        taxonomy = mechanism["change_taxonomy"]["incidence_vs_mj"]
        self.assertEqual(taxonomy["classes"], {
            "same_candidate": 200,
            "same_pattern_different_cap": 0,
            "different_pattern": 100,
        })
        self.assertEqual(
            taxonomy["cap_direction_within_same_pattern"],
            {"lower": 0, "higher": 0},
        )
        identity = mechanism["selected_candidate_distributions"]["incidence"]
        self.assertEqual(identity["cap_histogram"], {"exact": 300})
        self.assertEqual(
            identity["pattern_cardinality_histogram"], {"0": 200, "1": 100}
        )
        self.assertEqual(
            identity["source_set_histogram"], {"bdd_prefix": 100, "empty": 200}
        )

        budget = mechanism["budget_geometry"]
        self.assertEqual(budget["zero_budget_tasks"], {"incidence": 0, "mj": 0})
        self.assertEqual(
            budget["binding_tasks"], {"incidence": 300, "mj": 300}
        )
        self.assertEqual(budget["incidence_own_utilization"]["task_mean"][
            "numerator"
        ], 1)
        self.assertEqual(budget["incidence_own_utilization"]["task_mean"][
            "denominator"
        ], 1)
        cross = budget["cross_feasibility_counts"]
        self.assertEqual(cross["incidence_mj_feasible"], 200)
        self.assertEqual(cross["incidence_mj_infeasible"], 100)
        self.assertEqual(cross["mj_incidence_feasible"], 300)
        self.assertEqual(cross["mj_incidence_infeasible"], 0)
        self.assertEqual(cross["incidence_mj_retained"], 200)
        self.assertEqual(cross["incidence_mj_not_retained"], 100)
        self.assertEqual(cross["mj_incidence_retained"], 300)
        self.assertEqual(cross["mj_incidence_not_retained"], 0)

        self.assertEqual(set(mechanism["candidate_work"]), set(
            Analyzer.WORK_FIELDS
        ))
        self.assertEqual(
            mechanism["candidate_work"]["candidate_count"]["task_mean"][
                "numerator"
            ],
            3,
        )
        incidence_overhead = mechanism["overhead_by_mode"][P.INCIDENCE_MODE]
        self.assertEqual(
            incidence_overhead["probe"]["cpu_seconds"]["task_mean"][
                "decimal"
            ],
            0.2,
        )
        self.assertEqual(
            incidence_overhead["selection_complete_tasks"]["cpu_seconds"][
                "task_mean"
            ]["decimal"],
            0.4,
        )
        self.assertEqual(
            incidence_overhead["total_complete_tasks"]["cpu_seconds"][
                "task_mean"
            ]["numerator"],
            3,
        )
        self.assertEqual(
            incidence_overhead["total_complete_tasks"]["cpu_seconds"][
                "task_mean"
            ]["denominator"],
            5,
        )
        for comparison in mechanism[
            "paired_recorded_probe_selection_time"
        ].values():
            for field in ("cpu_seconds", "wall_seconds"):
                self.assertEqual(
                    comparison[field]["task_mean"]["numerator"], 0
                )
                self.assertEqual(
                    comparison[field]["minimum"]["numerator"], 0
                )
        self.assertNotIn(
            "sum",
            incidence_overhead["probe"]["peak_memory_after_kb"],
        )

    def test_mechanism_is_search_outcome_independent_and_nongating(self):
        records = fake_records(differing_tasks=100)
        first = self.analyze(copy.deepcopy(records))
        for row in records:
            row["total_time"] = {
                P.INCIDENCE_MODE: 120.0,
                P.MJ_MODE: 320.0,
                P.MATCHED_MODE: 420.0,
            }[row["algorithm"]]
        second = self.analyze(records)
        self.assertEqual(
            first["mechanism_diagnostics"],
            second["mechanism_diagnostics"],
        )
        self.assertEqual(first["pass"], second["pass"])
        self.assertFalse(second["mechanism_diagnostics"]["gating"])

    def test_downstream_provenance_is_v12_only_and_closed(self):
        freeze = fake_freeze()
        properties = Analyzer.Runner.build_manifest_properties(
            freeze, FREEZE_SHA
        )
        keys = set(properties)
        expected_v12 = set(Analyzer.Runner.V12_PROVENANCE_PROPERTY_FIELDS)
        self.assertTrue(expected_v12.issubset(keys))
        self.assertEqual(
            {key for key in keys if key.startswith("source_audit")},
            {key for key in expected_v12 if key.startswith("source_audit")},
        )
        self.assertEqual(
            properties["source_audit_v12_schema"], P.V12_SOURCE_SCHEMA
        )
        self.assertEqual(
            properties["source_audit_campaign"], "v12-full-census"
        )
        provenance = Analyzer._analysis_provenance(freeze, FREEZE_SHA)
        self.assertEqual(
            set(provenance), set(Analyzer.ANALYSIS_PROVENANCE_FIELDS)
        )
        self.assertEqual(
            provenance,
            {key: properties[key] for key in Analyzer.ANALYSIS_PROVENANCE_FIELDS},
        )

    def test_double_execution_publishes_identical_outputs_and_pin(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        inputs = (
            fake_records(), freeze, FREEZE_SHA, standalone, "a" * 64,
            "b" * 64, "experiments/artifacts/execution-receipt-v1.json",
            "c" * 64, HARDWARE,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output, repeat, receipt, pin = (
                root / "analysis.json", root / "analysis-repeat.json",
                root / "receipt.json", root / "receipt.sha256",
            )
            with mock.patch.object(
                Analyzer, "_load_inputs",
                side_effect=[copy.deepcopy(inputs), copy.deepcopy(inputs)],
            ):
                published = Analyzer.run_twice(
                    output, repeat, receipt, pin, bootstrap_replicates=500
                )
            self.assertEqual(output.read_bytes(), repeat.read_bytes())
            receipt_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
            self.assertEqual(pin.read_text(), receipt_sha + "\n")
            self.assertEqual(published["analysis_receipt_sha256"], receipt_sha)
            self.assertTrue(published["outputs_byte_identical"])
            self.assertEqual(published["execution_receipt_sha256"], "c" * 64)
            self.assertEqual(
                published["execution_receipt_path"],
                "experiments/artifacts/execution-receipt-v1.json",
            )
            analysis_value = json.loads(output.read_text())
            receipt_value = json.loads(receipt.read_text())
            analysis_provenance = analysis_value["input"]["frozen_provenance"]
            receipt_provenance = receipt_value["frozen_provenance"]
            self.assertEqual(analysis_value["input"]["hardware"], HARDWARE)
            self.assertEqual(receipt_value["hardware"], HARDWARE)
            self.assertEqual(analysis_provenance, receipt_provenance)
            self.assertTrue(set(
                Analyzer.Runner.V12_PROVENANCE_PROPERTY_FIELDS
            ).issubset(analysis_provenance))

    def test_second_pass_input_drift_publishes_nothing(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        base = [
            [], freeze, FREEZE_SHA, standalone, "a" * 64, "b" * 64,
            "experiments/artifacts/execution-receipt-v1.json", "c" * 64,
            HARDWARE,
        ]
        mutations = {
            "freeze": lambda value: value[1].update({"nonce": 1}),
            "standalone": lambda value: value[3].update({"nonce": 1}),
            "properties": lambda value: value.__setitem__(4, "0" * 64),
            "fetch": lambda value: value.__setitem__(5, "0" * 64),
            "execution_path": lambda value: value.__setitem__(6, "elsewhere"),
            "execution_sha": lambda value: value.__setitem__(7, "0" * 64),
            "hardware": lambda value: value[8]["processor_model_counts"].update(
                {"Other CPU": 1}
            ),
        }
        for label, mutate in mutations.items():
            first = copy.deepcopy(base)
            second = copy.deepcopy(base)
            mutate(second)
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = (
                    root / "analysis.json", root / "analysis-repeat.json",
                    root / "receipt.json", root / "receipt.sha256",
                )
                with mock.patch.object(
                    Analyzer, "_load_inputs", side_effect=[first, second],
                ), mock.patch.object(
                    Analyzer, "analyze",
                    return_value={"schema": Analyzer.ANALYSIS_SCHEMA, "pass": True},
                ), self.assertRaisesRegex(Analyzer.AnalysisError, "input changed"):
                    Analyzer.run_twice(*paths, bootstrap_replicates=500)
                self.assertFalse(any(path.exists() for path in paths))

    def test_nondeterministic_analysis_publishes_nothing(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        inputs = (
            [], freeze, FREEZE_SHA, standalone, "a" * 64, "b" * 64,
            "experiments/artifacts/execution-receipt-v1.json", "c" * 64,
            HARDWARE,
        )
        first = {"schema": Analyzer.ANALYSIS_SCHEMA, "pass": True, "nonce": 1}
        second = {**first, "nonce": 2}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = (
                root / "analysis.json", root / "analysis-repeat.json",
                root / "receipt.json", root / "receipt.sha256",
            )
            with mock.patch.object(
                Analyzer, "_load_inputs",
                side_effect=[copy.deepcopy(inputs), copy.deepcopy(inputs)],
            ), mock.patch.object(
                Analyzer, "analyze", side_effect=[first, second]
            ), self.assertRaisesRegex(Analyzer.AnalysisError, "byte-identical"):
                Analyzer.run_twice(*paths)
            self.assertFalse(any(path.exists() for path in paths))


if __name__ == "__main__":
    unittest.main()
