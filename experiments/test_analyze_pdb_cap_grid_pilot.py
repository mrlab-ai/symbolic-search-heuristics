#!/usr/bin/env python3
"""Adversarial tests for the prospective cap-grid pilot analyzer."""

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import analyze_pdb_cap_grid_pilot as A
import exp_arrhenius_common as C


class CapGridAnalyzerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tasks = A.load_tasks()
        cls.pins = A._test_pins()
        cls.records = A.synthetic_records(cls.tasks, cls.pins)
        cls.digest = A.legacy.logical_properties_sha256(cls.records)

    def analyze(self, records=None):
        records = copy.deepcopy(self.records if records is None else records)
        return A.analyze_with_pins(records, self.tasks, self.pins, self.digest)

    def errors(self, records):
        return A.validate_records(
            records,
            self.tasks,
            self.pins[1],
            self.pins[0],
            self.pins[2],
            self.pins[3],
        )[1]

    def target(self, records, label, task_index=0):
        task = self.tasks[task_index]
        return next(
            record
            for record in records
            if record["algorithm"] == label
            and (record["domain"], record["problem"]) == task
        )

    def test_valid_contract_and_primary_identity(self):
        result = self.analyze()
        self.assertEqual(result["schema"], A.ANALYSIS_SCHEMA)
        self.assertEqual(result["execution"]["cell_count"], 300)
        self.assertEqual(result["primary"]["candidate"], "pdb_cap_grid_k8")
        self.assertEqual(result["primary"]["reference"], "pdb_selector_k8")
        self.assertEqual(
            result["primary"]["raw_pool_isolation"]["status"], "certified"
        )
        self.assertEqual(
            result["primary"]["semantic_nontrivial_selection"]["status"],
            "estimable",
        )
        self.assertEqual(
            result["fixed_sensitivity"]["candidate"], "pdb_cap_grid_k32"
        )
        self.assertFalse(
            result["decision_policy"]["sensitivity_may_replace_primary"]
        )
        self.assertIsNone(result["decision_policy"]["confidence_intervals"])
        self.assertIsNone(result["decision_policy"]["p_values"])
        exact = next(
            row for row in result["configs"] if row["label"] == "pdb_selector_k8"
        )
        for field in ("A", "T", "V"):
            self.assertEqual(
                exact["selection"][field]["observed"],
                exact["selection"]["certified_complete_traces"],
            )

    def test_order_independent_determinism(self):
        forward = self.analyze()
        backward = self.analyze(list(reversed(self.records)))
        self.assertEqual(A.canonical_json(forward), A.canonical_json(backward))

    def test_missing_and_duplicate_cells_reject(self):
        missing = copy.deepcopy(self.records[:-1])
        self.assertTrue(any("missing" in error for error in self.errors(missing)))
        duplicate = copy.deepcopy(self.records)
        duplicate.append(copy.deepcopy(duplicate[0]))
        self.assertTrue(any("duplicate" in error for error in self.errors(duplicate)))

    def test_static_protocol_and_matrix_drift_reject(self):
        for field, value in (
            ("protocol", "wrong"),
            ("option_matrix_sha256", "0" * 64),
            ("analysis_contract", {}),
        ):
            records = copy.deepcopy(self.records)
            self.target(records, "pdb_cap_grid_k8")[field] = value
            self.assertTrue(any(field in error for error in self.errors(records)))

    def test_outcome_reconciliation_drift_rejects(self):
        records = copy.deepcopy(self.records)
        self.target(records, "blind_fw")["outcome_reconciliation_certified"] = False
        self.assertTrue(
            any("outcome reconciliation" in error for error in self.errors(records))
        )

    def test_solved_runtime_must_be_strictly_positive(self):
        records = copy.deepcopy(self.records)
        target = self.target(records, "blind_fw", 1)
        self.assertEqual(target["coverage"], 1)
        target["planner_time"] = 0.0
        self.assertTrue(
            any("strictly positive" in error for error in self.errors(records))
        )

    def test_solved_nonblind_requires_construction_and_trace(self):
        for label in ("pdb_cegar_b100k", "pdb_selector_k8", "pdb_cap_grid_k8"):
            records = copy.deepcopy(self.records)
            target = self.target(records, label, 1)
            self.assertEqual(target["coverage"], 1)
            for field in list(A.SELECTOR_TRACE_FIELDS) + [
                "construction_completed",
                "construction_time",
                "heuristic_kind",
                "heuristic_size_bound",
                "value_cap",
                "cofactor_width",
                "width_upper_bound",
                "num_values",
                "num_terminals",
                "add_nodes",
                "pdb_final_format",
                "pdb_pattern_size",
                "pdb_selected_source",
                "pdb_abstract_states",
                "pdb_cofactor_width_budget",
                "pdb_selected_value_cap",
                "pdb_final_num_values",
                "pdb_final_cofactor_width",
                "pdb_final_width_upper_bound",
            ]:
                target.pop(field, None)
            self.assertTrue(
                any(
                    "lacks construction outcome" in error
                    for error in self.errors(records)
                ),
                label,
            )

    def test_exact_selected_statistics_are_cross_bound(self):
        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_selector_k8", 1)
        target.update(
            {
                "cofactor_width": 2,
                "width_upper_bound": 3,
                "num_values": 2,
                "num_terminals": 2,
                "add_nodes": 1,
                "pdb_final_num_values": 2,
            }
        )
        target[C.PDB_SELECTOR_FINAL_PROPERTY]["num_values"] = 2
        target[C.PDB_SELECTOR_TRACE_SHA256_PROPERTY] = A.legacy.sha256_json(
            {
                "candidates": target[C.PDB_SELECTOR_CANDIDATES_PROPERTY],
                "selected": target[C.PDB_SELECTOR_SELECTED_PROPERTY],
                "final": target[C.PDB_SELECTOR_FINAL_PROPERTY],
            }
        )
        self.assertTrue(
            any(
                "disagrees with exact selector winner" in error
                for error in self.errors(records)
            )
        )

    def test_exact_selector_rejects_cap_only_trace_fields(self):
        for field in (
            A.cap_parser.RAW_POOL_SHA256_PROPERTY,
            "pdb_cap_selector_parser_protocol",
            "pdb_selected_value_cap",
        ):
            records = copy.deepcopy(self.records)
            self.target(records, "pdb_selector_k8")[field] = "wrong"
            self.assertTrue(
                any("cap-only" in error for error in self.errors(records)), field
            )

    def test_primary_fractions_retain_frozen_denominator(self):
        result = self.analyze()
        for comparison in (result["primary"], result["fixed_sensitivity"]):
            self.assertEqual(
                comparison["coverage"]["candidate_minus_reference"]["denominator"],
                50,
            )
            mechanism = comparison["semantic_nontrivial_selection"]
            if mechanism["candidate_minus_reference"] is not None:
                self.assertEqual(
                    mechanism["candidate_minus_reference"]["denominator"], 50
                )

    def test_malformed_trace_objects_fail_closed_without_crashing(self):
        mutations = []
        records = copy.deepcopy(self.records)
        self.target(records, "pdb_selector_k8")[
            C.PDB_SELECTOR_CANDIDATES_PROPERTY
        ] = [None]
        mutations.append(records)
        records = copy.deepcopy(self.records)
        self.target(records, "pdb_selector_k8")[C.PDB_SELECTOR_FINAL_PROPERTY] = {}
        mutations.append(records)
        records = copy.deepcopy(self.records)
        self.target(records, "pdb_cap_grid_k8")[C.PDB_SELECTOR_SELECTED_PROPERTY] = []
        mutations.append(records)
        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_cap_grid_k8")
        target[C.PDB_SELECTOR_CANDIDATES_PROPERTY] = [
            item
            for item in target[C.PDB_SELECTOR_CANDIDATES_PROPERTY]
            if not (item["sources"] == ["cegar"] and item["value_cap"] == -1)
        ]
        mutations.append(records)
        for mutated in mutations:
            self.assertTrue(self.errors(mutated))

    def test_trace_absence_cannot_hide_projected_final_fields(self):
        for label in ("pdb_selector_k32", "pdb_cap_grid_k32"):
            with self.subTest(label=label):
                records = copy.deepcopy(self.records)
                target = self.target(records, label)
                for field in list(A.SELECTOR_TRACE_FIELDS) + list(
                    A.PDB_FINAL_FIELDS
                ) + [
                    "construction_completed", "construction_time",
                    "heuristic_kind", "heuristic_size_bound", "value_cap",
                    "cofactor_width", "width_upper_bound", "num_values",
                    "num_terminals", "add_nodes",
                ]:
                    target.pop(field, None)
                target["pdb_final_format"] = "forged-final"
                target.update(
                    raw_metrics_complete=False,
                    wbh_summary_solved=None,
                    wbh_done_solution_cost=None,
                    wbh_solved_summary_certified=False,
                )
                self.assertTrue(
                    any(
                        "projected final fields" in error
                        for error in self.errors(records)
                    )
                )

    def test_nonselector_configs_reject_selector_final_provenance(self):
        records = copy.deepcopy(self.records)
        self.target(records, "blind_fw")["pdb_final_format"] = (
            "exact_width_cap_filter"
        )
        self.assertTrue(
            any("blind contains PDB final fields" in error for error in self.errors(records))
        )

        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_cegar_b100k")
        target.update(
            pdb_selected_source="cegar",
            pdb_selected_value_cap=1,
            pdb_cofactor_width_budget=8,
            pdb_abstract_states=10,
        )
        self.assertTrue(
            any(
                "selector-only final fields" in error
                for error in self.errors(records)
            )
        )

    def test_interrupted_exact_late_dedup_does_not_extend_prefix(self):
        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_selector_k32")
        first = copy.deepcopy(
            target[C.PDB_SELECTOR_CANDIDATES_PROPERTY][0]
        )
        first["sources"] = ["empty", "cegar"]
        target[C.PDB_SELECTOR_CANDIDATES_PROPERTY] = [first]
        target[C.PDB_SELECTOR_SELECTED_PROPERTY] = None
        target[C.PDB_SELECTOR_FINAL_PROPERTY] = None
        target[C.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY] = False
        target[C.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY] = False
        target[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY] = (
            "selector trace is incomplete"
        )
        target[C.PDB_SELECTOR_TRACE_SHA256_PROPERTY] = None
        target[C.PDB_SELECTOR_POOL_SHA256_PROPERTY] = None
        for field in list(A.PDB_FINAL_FIELDS) + [
            "construction_completed", "construction_time", "heuristic_kind",
            "heuristic_size_bound", "value_cap", "cofactor_width",
            "width_upper_bound", "num_values", "num_terminals", "add_nodes",
        ]:
            target.pop(field, None)
        target.update(
            raw_metrics_complete=False,
            wbh_summary_solved=None,
            wbh_done_solution_cost=None,
            wbh_solved_summary_certified=False,
        )
        self.assertFalse(self.errors(records))

    def test_certified_resource_final_accepts_full_or_width_only_prefix(self):
        for label in ("pdb_selector_k8", "pdb_cap_grid_k8"):
            for width_only in (False, True):
                with self.subTest(label=label, width_only=width_only):
                    records = copy.deepcopy(self.records)
                    target = self.target(records, label)
                    target.update(
                        {
                            "raw_metrics_complete": False,
                            "wbh_summary_solved": None,
                            "wbh_done_solution_cost": None,
                            "wbh_solved_summary_certified": False,
                        }
                    )
                    for field in (
                        "construction_completed",
                        "construction_time",
                        "heuristic_kind",
                        "heuristic_size_bound",
                        "value_cap",
                    ):
                        target.pop(field, None)
                    if width_only:
                        for field in (
                            "width_upper_bound",
                            "num_values",
                            "num_terminals",
                            "add_nodes",
                        ):
                            target.pop(field, None)
                    self.assertFalse(self.errors(records))

    def test_interrupted_exact_selected_must_be_winner(self):
        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_selector_k32")
        target[C.PDB_SELECTOR_SELECTED_PROPERTY] = copy.deepcopy(
            target[C.PDB_SELECTOR_CANDIDATES_PROPERTY][0]
        )
        target[C.PDB_SELECTOR_FINAL_PROPERTY] = None
        target[C.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY] = False
        target[C.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY] = False
        target[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY] = "selector trace is incomplete"
        target[C.PDB_SELECTOR_TRACE_SHA256_PROPERTY] = None
        target[C.PDB_SELECTOR_POOL_SHA256_PROPERTY] = None
        for field in (
            "construction_completed",
            "construction_time",
            "heuristic_kind",
            "heuristic_size_bound",
            "value_cap",
            "cofactor_width",
            "width_upper_bound",
            "num_values",
            "num_terminals",
            "add_nodes",
            "pdb_final_format",
            "pdb_pattern_size",
            "pdb_selected_source",
            "pdb_abstract_states",
            "pdb_cofactor_width_budget",
            "pdb_final_num_values",
            "pdb_final_cofactor_width",
            "pdb_final_width_upper_bound",
        ):
            target.pop(field, None)
        target.update(
            raw_metrics_complete=False,
            wbh_summary_solved=None,
            wbh_done_solution_cost=None,
            wbh_solved_summary_certified=False,
        )
        self.assertTrue(
            any("not recomputed winner" in error for error in self.errors(records))
        )

    def test_interrupted_cap_prefix_cannot_skip_fixed_sources(self):
        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_cap_grid_k32")
        target[C.PDB_SELECTOR_CANDIDATES_PROPERTY] = [
            item
            for item in target[C.PDB_SELECTOR_CANDIDATES_PROPERTY]
            if item["sources"] == ["empty"] or item["sources"] == ["cegar"]
        ]
        target[C.PDB_SELECTOR_SELECTED_PROPERTY] = None
        target[C.PDB_SELECTOR_FINAL_PROPERTY] = None
        target[C.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY] = False
        target[C.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY] = False
        target[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY] = (
            "cap-grid selector trace is incomplete"
        )
        target[C.PDB_SELECTOR_TRACE_SHA256_PROPERTY] = None
        target[C.PDB_SELECTOR_POOL_SHA256_PROPERTY] = None
        target[A.cap_parser.RAW_POOL_SHA256_PROPERTY] = None
        for field in (
            "construction_completed",
            "construction_time",
            "heuristic_kind",
            "heuristic_size_bound",
            "value_cap",
            "cofactor_width",
            "width_upper_bound",
            "num_values",
            "num_terminals",
            "add_nodes",
            "pdb_final_format",
            "pdb_pattern_size",
            "pdb_selected_source",
            "pdb_abstract_states",
            "pdb_cofactor_width_budget",
            "pdb_selected_value_cap",
            "pdb_final_num_values",
            "pdb_final_cofactor_width",
            "pdb_final_width_upper_bound",
        ):
            target.pop(field, None)
        target.update(
            raw_metrics_complete=False,
            wbh_summary_solved=None,
            wbh_done_solution_cost=None,
            wbh_solved_summary_certified=False,
        )
        self.assertTrue(
            any("skips an earlier" in error for error in self.errors(records))
        )

    def test_interrupted_cap_prefix_cannot_claim_raw_pool_hash(self):
        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_cap_grid_k32")
        candidates = target[C.PDB_SELECTOR_CANDIDATES_PROPERTY]
        first_pattern = candidates[0]["pattern"]
        target[C.PDB_SELECTOR_CANDIDATES_PROPERTY] = [
            item for item in candidates if item["pattern"] == first_pattern
        ]
        target[C.PDB_SELECTOR_SELECTED_PROPERTY] = None
        target[C.PDB_SELECTOR_FINAL_PROPERTY] = None
        target[C.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY] = False
        target[C.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY] = False
        target[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY] = (
            "cap-grid selector trace is incomplete"
        )
        target[C.PDB_SELECTOR_TRACE_SHA256_PROPERTY] = None
        target[C.PDB_SELECTOR_POOL_SHA256_PROPERTY] = None
        target[A.cap_parser.RAW_POOL_SHA256_PROPERTY] = "f" * 64
        for field in list(A.PDB_FINAL_FIELDS) + [
            "construction_completed", "construction_time", "heuristic_kind",
            "heuristic_size_bound", "value_cap", "cofactor_width",
            "width_upper_bound", "num_values", "num_terminals", "add_nodes",
        ]:
            target.pop(field, None)
        target.update(
            raw_metrics_complete=False,
            wbh_summary_solved=None,
            wbh_done_solution_cost=None,
            wbh_solved_summary_certified=False,
        )
        self.assertTrue(
            any("certified hashes" in error for error in self.errors(records))
        )

    def test_literal_runner_contract_rejects_cap_and_score_drift(self):
        cases = (
            (A.runner, "CAP_GRID", [0, 1, "exact"]),
            (A.cap_parser, "GRID", (0, 1)),
            (A.cap_parser, "SCORE_VERSION", "wrong"),
            (
                A.cap_parser,
                "RECORD_KEYS",
                A.cap_parser.RECORD_KEYS + ("future_unpinned_field",),
            ),
            (A.cap_parser, "MAX_ABSTRACT_STATES", 200000),
            (
                A.cap_parser,
                "HISTOGRAM_DIGEST_RE",
                A.re.compile(r"^.*$"),
            ),
            (
                A.cap_parser,
                "HISTOGRAM_WIRE_RE",
                A.re.compile(r"^.*$"),
            ),
            (A.cap_parser, "MAX_HISTOGRAM_BYTES", 1),
            (A.runner, "PLANNER_SOFT_STDOUT_LIMIT_KIB", 2),
            (A.common, "PDB_SELECTOR_SOURCES", ("empty", "cegar")),
        )
        for owner, field, value in cases:
            with self.subTest(field=field), mock.patch.object(owner, field, value):
                with self.assertRaisesRegex(A.AnalysisError, "changed"):
                    A.validate_runner_contract(check_reviewed_pins=False)

    def test_cross_configuration_cost_disagreement_rejects(self):
        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_cap_grid_k8", 1)
        for field in (
            "solution_cost",
            "plan_file_cost",
            "run_log_plan_cost",
            "wbh_done_solution_cost",
        ):
            target[field] += 1
        self.assertTrue(
            any("solved-cost disagreement" in error for error in self.errors(records))
        )

    def test_weaker_cap_winner_rejects(self):
        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_cap_grid_k8")
        candidates = target[C.PDB_SELECTOR_CANDIDATES_PROPERTY]
        weaker = copy.deepcopy(
            next(
                item
                for item in candidates
                if item["sources"] == ["cegar"] and item["value_cap"] == 0
            )
        )
        target[C.PDB_SELECTOR_SELECTED_PROPERTY] = weaker
        self.assertTrue(any("winner" in error for error in self.errors(records)))

    def test_cap_raw_census_tamper_rejects(self):
        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_cap_grid_k8")
        candidate = target[C.PDB_SELECTOR_CANDIDATES_PROPERTY][5]
        candidate["raw_finite_sum"] += 1
        self.assertTrue(
            any(
                "raw identity" in error
                or "raw-pool" in error
                or "exact profile" in error
                for error in self.errors(records)
            )
        )

    def test_cross_protocol_raw_pool_mismatch_rejects(self):
        records = copy.deepcopy(self.records)
        target = self.target(records, "pdb_selector_k8")
        candidates = target[C.PDB_SELECTOR_CANDIDATES_PROPERTY]
        candidates[1]["finite_sum"] += 1
        target[C.PDB_SELECTOR_POOL_SHA256_PROPERTY] = A.legacy.sha256_json(
            A.legacy._normalized_selector_pool(candidates)
        )
        target[C.PDB_SELECTOR_TRACE_SHA256_PROPERTY] = A.legacy.sha256_json(
            {
                "candidates": candidates,
                "selected": target[C.PDB_SELECTOR_SELECTED_PROPERTY],
                "final": target[C.PDB_SELECTOR_FINAL_PROPERTY],
            }
        )
        self.assertTrue(
            any("raw selector pool" in error for error in self.errors(records))
        )

    def test_missing_trace_makes_mechanism_and_isolation_nonestimable(self):
        records = copy.deepcopy(self.records)
        matrix, errors = A.validate_records(
            records,
            self.tasks,
            self.pins[1],
            self.pins[0],
            self.pins[2],
            self.pins[3],
        )
        self.assertFalse(errors)
        target = matrix[("pdb_cap_grid_k8", self.tasks[0])]
        target[C.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY] = False
        comparison = A._comparison(matrix, self.tasks, 8)
        self.assertEqual(
            comparison["semantic_nontrivial_selection"]["status"],
            "not-estimable",
        )
        self.assertIsNone(
            comparison["semantic_nontrivial_selection"]["candidate_minus_reference"]
        )
        self.assertEqual(
            comparison["raw_pool_isolation"]["status"],
            "not-certified-no-cap-attribution-or-promotion",
        )

    def test_pin_gate_precedes_properties_read(self):
        with mock.patch.object(
            A.safe_loader,
            "load_properties",
            side_effect=AssertionError("properties must not be read"),
        ) as loader:
            with self.assertRaisesRegex(A.AnalysisError, "pins are unset"):
                A.main(["--properties", "/does/not/matter"])
            loader.assert_not_called()

    def test_manifest_validation_precedes_properties_read(self):
        # Use obviously well-formed literals so this test reaches the actual
        # task-manifest read instead of depending on the synthetic fixture
        # identities used by analyze_with_pins().
        protocol = A.hashlib.sha1(b"manifest-order-protocol").hexdigest()
        planner = A.hashlib.sha1(b"manifest-order-planner").hexdigest()
        binary = A.hashlib.sha256(b"manifest-order-binary").hexdigest()
        preprocess = A.hashlib.sha256(b"manifest-order-preprocess").hexdigest()
        properties = A.hashlib.sha256(b"manifest-order-properties").hexdigest()
        with mock.patch.multiple(
            A,
            EXPECTED_PROTOCOL_REVISION=protocol,
            EXPECTED_PLANNER_REVISION=planner,
            EXPECTED_CACHE_BINARY_SHA256=binary,
            EXPECTED_CACHE_PREPROCESS_SHA256=preprocess,
            EXPECTED_PROPERTIES_CANONICAL_SHA256=properties,
        ), mock.patch.multiple(
            A.runner,
            PLANNER_REVISION=planner,
            CACHE_BINARY_SHA256=binary,
            CACHE_PREPROCESS_SHA256=preprocess,
        ), mock.patch.object(
            A,
            "load_tasks",
            side_effect=A.AnalysisError("manifest validation failed"),
        ), mock.patch.object(
            A.safe_loader,
            "load_properties",
            side_effect=AssertionError("properties must not be read"),
        ) as loader:
            with self.assertRaisesRegex(A.AnalysisError, "manifest validation failed"):
                A.main(["--properties", "/does/not/matter"])
            loader.assert_not_called()

    def test_task_manifest_is_bound_to_analyzer_literal(self):
        with mock.patch.object(A, "EXPECTED_TASK_MANIFEST_SHA256", "0" * 64):
            with self.assertRaisesRegex(A.AnalysisError, "manifest digest changed"):
                A.load_tasks()

    def test_properties_loader_deep_json_fails_closed(self):
        raw = ("[" * 2000 + "0" + "]" * 2000).encode("ascii")
        with self.assertRaises(A.safe_loader.AnalysisError):
            A.safe_loader._parse_json_bytes(raw, "deep-properties")

    def test_partial_pin_gate_rejects(self):
        with mock.patch.object(A, "EXPECTED_PROTOCOL_REVISION", self.pins[0]):
            with self.assertRaisesRegex(A.AnalysisError, "partially set"):
                A.require_reviewed_pins(None)

    def test_config_summary_conserves_cells(self):
        result = self.analyze()
        self.assertEqual([row["label"] for row in result["configs"]], list(A.LABELS))
        self.assertTrue(all(row["cells"] == 50 for row in result["configs"]))
        for comparison in (result["primary"], result["fixed_sensitivity"]):
            coverage = comparison["coverage"]
            self.assertEqual(
                coverage["wins"]
                + coverage["losses"]
                + coverage["both_solved"]
                + coverage["both_unsolved"],
                50,
            )


if __name__ == "__main__":
    unittest.main()
