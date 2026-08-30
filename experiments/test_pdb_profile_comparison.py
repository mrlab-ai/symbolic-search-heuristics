#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


import jj_cached_revision as JJ
import analyze_pdb_profile_comparison as Analysis
import pdb_profile_comparison_parser as Parser
import pdb_profile_comparison_protocol as P


def line(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


class ProtocolTests(unittest.TestCase):
    def test_matrix(self):
        P.validate_config_matrix()
        self.assertEqual(len(P.CONFIGS), 18)
        self.assertEqual(P.CELL_COUNT, 23886)
        for label, search in P.CONFIGS:
            self.assertEqual(search.count('wbh_log="wbh.jsonl"'), 1, label)
            self.assertEqual("wbh_profile_log=" in search, label != "blind_fw")

    def test_add_and_width_budgets_are_exclusive(self):
        changed = list(P.CONFIGS)
        label, search = changed[12]
        changed[12] = (
            label,
            search.replace(
                "total_add_node_budget=8",
                "total_add_node_budget=8,cofactor_width_budget=2",
            ),
        )
        with self.assertRaises(P.ProtocolError):
            P.validate_config_matrix(tuple(changed))

    def test_acceptance_matched_budget_provenance(self):
        P.validate_matched_budget_provenance()


class ProfileParserTests(unittest.TestCase):
    def profile(self):
        events = [
            {
                "event": "schema",
                "version": 1,
                "cut_convention": "unprimed_state_bits_in_cudd_level_order_including_terminal",
                "node_count_convention": (
                    "regular_cudd_inner_nodes_of_semantic_union"
                ),
                "residual_identity": (
                    "canonical_signed_cudd_pointer_with_complement_polarity"
                ),
            },
            {
                "event": "variable_order",
                "manager_variables": 4,
                "state_bits": 2,
                "cudd_indices": [0, 2],
                "cudd_levels": [0, 2],
                "fd_variables": [0, 1],
                "fd_bit_positions": [0, 0],
            },
            {
                "event": "heuristic_profile",
                "add_nodes": 3,
                "num_values": 2,
                "num_terminals": 4,
                "cofactor_counts": [1, 2, 4],
                "cofactor_width": 4,
                "cofactor_seconds": 0.1,
            },
            {
                "event": "layer_profile",
                "g": 1,
                "completed": True,
                "piece_count": 2,
                "bdd_nodes": 3,
                "cofactor_counts": [1, 2, 2],
                "cofactor_width": 2,
                "union_seconds": 0.2,
                "cofactor_seconds": 0.3,
            },
            {"event": "done", "layer_union_effort": 3, "solution_cost": 5},
            {
                "event": "summary",
                "profiled_layer_attempts": 1,
                "profiled_layers": 1,
                "sum_layer_bdd_nodes": 3,
                "heuristic_profiled": True,
                "union_seconds": 0.2,
                "cofactor_seconds": 0.3,
                "heuristic_cofactor_seconds": 0.1,
                "serialization_seconds": 0.01,
                "output_seconds": 0.01,
                "solved": True,
            },
        ]
        return "\n".join(map(line, events)) + "\n"

    def test_terminal_cut_is_validation_only_for_paper_sums(self):
        parsed = Parser.parse_profile_stream(self.profile())
        self.assertTrue(parsed["complete"])
        self.assertEqual(parsed["heuristic_paper_cuts"]["paper_cut_width"], 2)
        self.assertEqual(parsed["heuristic_paper_cuts"]["cofactor_width"], 4)
        self.assertEqual(parsed["heuristic_paper_cuts"]["cut_product_sum"], 3)
        self.assertEqual(parsed["heuristic_paper_cuts"]["terminal_residuals"], 4)
        layer = parsed["layer_profiles"][0]
        self.assertEqual(layer["paper_cut_width"], 2)
        self.assertEqual(layer["paper_cut_product_sum"], 3)
        self.assertEqual(layer["terminal_residuals"], 2)
        self.assertEqual(layer["cofactor_counts"], [1, 2, 2])

    def test_truncated_prefix_is_incomplete(self):
        prefix = "\n".join(self.profile().splitlines()[:-1]) + "\n"
        parsed = Parser.parse_profile_stream(prefix)
        self.assertFalse(parsed["complete"])
        self.assertIsNone(parsed["summary"])

    def test_impossible_residual_profiles_are_rejected(self):
        lines = self.profile().splitlines()
        heuristic = json.loads(lines[2])
        heuristic["cofactor_counts"][0] = 2
        lines[2] = line(heuristic)
        with self.assertRaisesRegex(Parser.ParseError, "residual identities"):
            Parser.parse_profile_stream("\n".join(lines) + "\n")

        lines = self.profile().splitlines()
        layer_event = json.loads(lines[3])
        layer_event["cofactor_counts"][-1] = 3
        layer_event["cofactor_width"] = 3
        lines[3] = line(layer_event)
        with self.assertRaisesRegex(Parser.ParseError, "Boolean residual"):
            Parser.parse_profile_stream("\n".join(lines) + "\n")

    def test_profile_growth_node_and_add_invariants_are_fail_closed(self):
        mutations = []

        lines = self.profile().splitlines()
        event = json.loads(lines[2])
        event["cofactor_counts"] = [1, 3, 4]
        lines[2] = line(event)
        mutations.append((lines, "binary cut"))

        lines = self.profile().splitlines()
        event = json.loads(lines[3])
        event["bdd_nodes"] = 4
        lines[3] = line(event)
        mutations.append((lines, "Boolean residual"))

        lines = self.profile().splitlines()
        event = json.loads(lines[3])
        event["bdd_nodes"] = 0
        lines[3] = line(event)
        mutations.append((lines, "Boolean residual"))

        for field, value in (
            ("add_nodes", 2),
            ("add_nodes", 0),
            ("num_values", 5),
        ):
            lines = self.profile().splitlines()
            event = json.loads(lines[2])
            event[field] = value
            lines[2] = line(event)
            mutations.append((lines, "ADD residual"))

        for lines, message in mutations:
            with self.subTest(message=message, event=lines[2:4]):
                with self.assertRaisesRegex(Parser.ParseError, message):
                    Parser.parse_profile_stream("\n".join(lines) + "\n")

        lines = self.profile().splitlines()
        order = json.loads(lines[1])
        order.update({
            "manager_variables": 6,
            "state_bits": 3,
            "cudd_indices": [0, 2, 4],
            "cudd_levels": [0, 2, 4],
            "fd_variables": [0, 1, 2],
            "fd_bit_positions": [0, 0, 0],
        })
        lines[1] = line(order)
        heuristic = json.loads(lines[2])
        heuristic["cofactor_counts"] = [1, 2, 4, 4]
        lines[2] = line(heuristic)
        layer_event = json.loads(lines[3])
        layer_event.update({
            "bdd_nodes": 1,
            "cofactor_counts": [1, 2, 4, 2],
            "cofactor_width": 4,
        })
        lines[3] = line(layer_event)
        with self.assertRaisesRegex(Parser.ParseError, "Boolean residual"):
            Parser.parse_profile_stream("\n".join(lines) + "\n")

    def test_variable_order_rejects_duplicate_levels_and_fd_bits(self):
        lines = self.profile().splitlines()
        order = json.loads(lines[1])
        order["cudd_levels"] = [0, 0]
        lines[1] = line(order)
        with self.assertRaisesRegex(Parser.ParseError, "CUDD levels"):
            Parser.parse_profile_stream("\n".join(lines) + "\n")

        lines = self.profile().splitlines()
        order = json.loads(lines[1])
        order["fd_variables"] = [0, 0]
        order["fd_bit_positions"] = [0, 0]
        lines[1] = line(order)
        with self.assertRaisesRegex(Parser.ParseError, "FD variable"):
            Parser.parse_profile_stream("\n".join(lines) + "\n")

        lines = self.profile().splitlines()
        order = json.loads(lines[1])
        order["fd_bit_positions"] = [1, 0]
        lines[1] = line(order)
        with self.assertRaisesRegex(Parser.ParseError, "FD bit positions"):
            Parser.parse_profile_stream("\n".join(lines) + "\n")

        lines = self.profile().splitlines()
        order = json.loads(lines[1])
        order.update({
            "manager_variables": 6,
            "state_bits": 3,
            "cudd_indices": [0, 2, 4],
            "cudd_levels": [0, 2, 4],
            "fd_variables": [0, 1, 0],
            "fd_bit_positions": [0, 0, 1],
        })
        lines[1] = line(order)
        with self.assertRaisesRegex(Parser.ParseError, "not contiguous"):
            Parser.parse_profile_stream("\n".join(lines) + "\n")


def selector_record(
    *, sources, pattern, cap, stats, raw, histogram=None, selected=False
):
    feasible = stats["width_upper_bound"] <= 8
    return {
        "protocol": "fixed_pool_total_add_cap_grid_v1",
        "score_version": Parser.CAP_GRID_SCORE,
        "sources": list(sources),
        "pattern": list(pattern),
        "abstract_states": raw["finite_count"],
        "initial_dead_end": False,
        "initial_h": stats["initial_h"],
        "finite_sum": stats["finite_sum"],
        "finite_count": raw["finite_count"],
        "dead_count": 0,
        "cofactor_width": stats["cofactor_width"],
        "width_upper_bound": stats["width_upper_bound"],
        "total_add_node_budget": 8,
        "value_cap": cap,
        "add_nodes": stats["add_nodes"],
        "num_terminals": stats["num_terminals"],
        "raw_add_nodes": raw["add_nodes"],
        "raw_num_terminals": raw["num_terminals"],
        "raw_cofactor_width": raw["cofactor_width"],
        "raw_width_upper_bound": raw["width_upper_bound"],
        "raw_num_values": raw["num_values"],
        "raw_max_finite_value": raw["max_finite_value"],
        "raw_finite_sum": raw["finite_sum"],
        "raw_finite_count": raw["finite_count"],
        "raw_dead_count": 0,
        "raw_initial_dead_end": False,
        "raw_initial_h": raw["initial_h"],
        "raw_initial_value_count": raw["initial_value_count"],
        "raw_value_histogram": None if selected else histogram,
        "transformed_num_values": stats["num_values"],
        "feasible": feasible,
        "rejection_reason": None if feasible else "total_add_node_budget",
    }


class SelectorParserTests(unittest.TestCase):
    def records(self, histogram_pairs=((0, 1), (1, 4), (2, 1))):
        histogram_counts = dict(histogram_pairs)
        raw = {
            "add_nodes": 7,
            "num_terminals": 3,
            "cofactor_width": 3,
            "width_upper_bound": 10,
            "num_values": 3,
            "max_finite_value": 2,
            "finite_sum": 6,
            "finite_count": 6,
            "initial_h": 1,
            "initial_value_count": histogram_counts[1],
        }
        empty_raw = {
            "add_nodes": 0,
            "num_terminals": 1,
            "cofactor_width": 1,
            "width_upper_bound": 1,
            "num_values": 1,
            "max_finite_value": 0,
            "finite_sum": 0,
            "finite_count": 1,
            "initial_h": 0,
            "initial_value_count": 1,
        }
        empty_stats = {
            "add_nodes": 0,
            "num_terminals": 1,
            "cofactor_width": 1,
            "width_upper_bound": 1,
            "num_values": 1,
            "finite_sum": 0,
            "initial_h": 0,
        }
        cap0 = dict(empty_stats)
        cap1 = {
            "add_nodes": 5,
            "num_terminals": 2,
            "cofactor_width": 2,
            "width_upper_bound": 7,
            "num_values": 2,
            "finite_sum": sum(
                min(value, 1) * count for value, count in histogram_pairs
            ),
            "initial_h": 1,
        }
        exact = {
            "add_nodes": raw["add_nodes"],
            "num_terminals": raw["num_terminals"],
            "cofactor_width": raw["cofactor_width"],
            "width_upper_bound": raw["width_upper_bound"],
            "num_values": raw["num_values"],
            "finite_sum": raw["finite_sum"],
            "initial_h": raw["initial_h"],
        }
        candidates = [
            selector_record(
                sources=("empty",),
                pattern=(),
                cap=-1,
                stats=empty_stats,
                raw=empty_raw,
                histogram=Parser.encode_raw_value_histogram(((0, 1),)),
            ),
            selector_record(
                sources=Parser.SOURCE_ORDER[1:],
                pattern=(0,),
                cap=0,
                stats=cap0,
                raw=raw,
                histogram=Parser.encode_raw_value_histogram(histogram_pairs),
            ),
            selector_record(
                sources=Parser.SOURCE_ORDER[1:],
                pattern=(0,),
                cap=1,
                stats=cap1,
                raw=raw,
            ),
            selector_record(
                sources=Parser.SOURCE_ORDER[1:],
                pattern=(0,),
                cap=-1,
                stats=exact,
                raw=raw,
            ),
        ]
        selected = selector_record(
            sources=Parser.SOURCE_ORDER[1:],
            pattern=(0,),
            cap=1,
            stats=cap1,
            raw=raw,
            selected=True,
        )
        return candidates, selected

    def trace(self, score=Parser.CAP_GRID_SCORE, histogram_pairs=None):
        candidates, selected = self.records(
            histogram_pairs or ((0, 1), (1, 4), (2, 1))
        )
        for record in candidates + [selected]:
            record["score_version"] = score
        return "\n".join(
            [
                "PDB add-selector v1 candidate: " + line(record)
                for record in candidates
            ]
            + [
                "PDB add-selector v1 selected: " + line(selected),
                "wbh PDB heuristic: pattern_size=1, "
                "selected_source=bdd_prefix, abstract_states=6, "
                "total_add_node_budget=8, value_cap=1, values=2, "
                "cofactor_width=2, width_upper_bound=7",
            ]
        )

    def test_add_cap_grid_uses_unchanged_ranker_and_score(self):
        parsed = Parser.parse_selector_trace(self.trace())
        self.assertEqual(parsed["marker"], "add")
        self.assertEqual(parsed["budget"], 8)
        self.assertEqual(parsed["selected"]["value_cap"], 1)
        self.assertEqual(
            parsed["selected"]["score_version"], Parser.CAP_GRID_SCORE
        )

    def test_add_specific_score_label_is_rejected(self):
        with self.assertRaisesRegex(Parser.ParseError, "score version"):
            Parser.parse_selector_trace(self.trace("changed-for-add"))

    def test_well_formed_candidate_prefix_is_incomplete_not_malformed(self):
        prefix = "\n".join(self.trace().splitlines()[:2]) + "\n"
        parsed = Parser.parse_selector_trace(prefix)
        self.assertFalse(parsed["complete"])
        self.assertEqual(parsed["partial_fixed_source_count"], 5)
        self.assertIsNone(parsed["selected"])

    def test_selected_without_final_is_a_certified_incomplete_prefix(self):
        prefix = "\n".join(self.trace().splitlines()[:-1]) + "\n"
        parsed = Parser.parse_selector_trace(prefix)
        self.assertFalse(parsed["complete"])
        self.assertIsNotNone(parsed["selected"])
        self.assertRegex(parsed["raw_pool_sha256"], r"^[0-9a-f]{64}$")

    def test_omitted_cap_and_bad_histogram_are_rejected(self):
        lines = self.trace().splitlines()
        with self.assertRaisesRegex(Parser.ParseError, "omits"):
            Parser.parse_selector_trace("\n".join(lines[:2] + lines[3:]))

        lines = self.trace().splitlines()
        record = json.loads(lines[1].split(": ", 1)[1])
        record["raw_value_histogram"] = Parser.encode_raw_value_histogram(
            ((0, 2), (1, 2), (2, 1))
        )
        lines[1] = "PDB add-selector v1 candidate: " + line(record)
        with self.assertRaisesRegex(Parser.ParseError, "histogram contradicts"):
            Parser.parse_selector_trace("\n".join(lines))

    def test_bad_add_identity_key_order_and_marker_are_rejected(self):
        lines = self.trace().splitlines()
        record = json.loads(lines[2].split(": ", 1)[1])
        record["width_upper_bound"] = 8
        lines[2] = "PDB add-selector v1 candidate: " + line(record)
        with self.assertRaisesRegex(Parser.ParseError, "A/T/U/V"):
            Parser.parse_selector_trace("\n".join(lines))

        lines = self.trace().splitlines()
        record = json.loads(lines[0].split(": ", 1)[1])
        reordered = {"score_version": record.pop("score_version"), **record}
        lines[0] = "PDB add-selector v1 candidate: " + line(reordered)
        with self.assertRaisesRegex(Parser.ParseError, "keys/order"):
            Parser.parse_selector_trace("\n".join(lines))

        malformed = self.trace().replace(
            "PDB add-selector v1 candidate:",
            "PDB add-selector v2 candidate:",
            1,
        )
        with self.assertRaisesRegex(Parser.ParseError, "marker line"):
            Parser.parse_selector_trace(malformed)

    def test_strong_pool_digest_covers_raw_histogram(self):
        first = Parser.parse_selector_trace(self.trace())
        second = Parser.parse_selector_trace(
            self.trace(histogram_pairs=((0, 2), (1, 2), (2, 2)))
        )
        self.assertNotEqual(first["raw_pool_sha256"], second["raw_pool_sha256"])
        self.assertEqual(
            first["raw_pool_common_sha256"],
            second["raw_pool_common_sha256"],
        )


class AnalyzerEvidenceTests(unittest.TestCase):
    def resource_prefix(self):
        return {
            "planner_exit_code": 23,
            "error": "search-out-of-time",
            "coverage": 0,
            "unsolvable": 0,
            "unexplained_errors": [],
            "wbh_expansion_profile_present": True,
            "wbh_expansion_profile_certified": True,
            "wbh_expansion_profile_complete": False,
            "wbh_profile_present": True,
            "wbh_profile_prefix_certified": True,
            "wbh_profile_complete": False,
            "pdb_profile_selector_present": True,
            "pdb_profile_selector_prefix_certified": True,
        }

    def test_timeout_prefix_and_construction_timeout_are_classified(self):
        record = self.resource_prefix()
        self.assertEqual(Analysis._outcome_class(record, "pdb_exact_k2"), "search_resource")
        record["construction_completed"] = False
        self.assertEqual(Analysis._outcome_class(record, "pdb_exact_k2"), "search_resource")

    def test_translation_failure_needs_no_search_logs(self):
        record = {
            "planner_exit_code": 21,
            "error": "translate-out-of-time",
            "coverage": 0,
            "unsolvable": 0,
            "unexplained_errors": [],
            "construction_completed": None,
        }
        self.assertEqual(Analysis._outcome_class(record, "pdb_exact_k2"), "presearch")

    def test_plan_found_resource_exit_can_have_incomplete_metrics(self):
        record = self.resource_prefix()
        record.update({
            "planner_exit_code": 2,
            "error": "search-plan-found-and-out-of-time",
            "coverage": 1,
        })
        self.assertEqual(
            Analysis._outcome_class(record, "pdb_exact_k2"),
            "solved_resource",
        )
        self.assertIsNone(Analysis._target_effort(record, "pdb_exact_k2"))

    def test_present_malformed_timeout_prefix_is_rejected(self):
        record = self.resource_prefix()
        record["wbh_expansion_profile_certified"] = False
        with self.assertRaisesRegex(Analysis.AnalysisError, "schema-v2"):
            Analysis._outcome_class(record, "pdb_exact_k2")

    def test_unprofiled_blind_rejects_profile_evidence(self):
        record = self.resource_prefix()
        with self.assertRaisesRegex(Analysis.AnalysisError, "unprofiled blind"):
            Analysis._outcome_class(record, "blind_fw")

    def solved_missing_validator_record(self):
        return {
            "planner_exit_code": 36,
            "error": "driver-input-error",
            "coverage": 1,
            "unsolvable": 0,
            "unexplained_errors": list(Analysis.MISSING_VALIDATOR_ERRORS),
            "wbh_expansion_profile_present": True,
            "wbh_expansion_profile_certified": True,
            "wbh_expansion_profile_complete": True,
            "wbh_solved_summary_certified": True,
            "wbh_profile_present": False,
            "wbh_profile_prefix_certified": False,
            "wbh_profile_complete": False,
            "pdb_profile_selector_present": False,
            "pdb_profile_selector_prefix_certified": False,
        }

    def test_only_sealed_missing_validator_outcome_is_solved(self):
        record = self.solved_missing_validator_record()
        self.assertEqual(
            Analysis._outcome_class(record, "blind_fw", True),
            "solved",
        )
        with self.assertRaisesRegex(Analysis.AnalysisError, "unauthorized"):
            Analysis._outcome_class(record, "blind_fw", False)
        for errors in (
            ["driver-input-error"],
            list(reversed(Analysis.MISSING_VALIDATOR_ERRORS)),
            Analysis.MISSING_VALIDATOR_ERRORS + ["synthetic"],
        ):
            changed = copy.deepcopy(record)
            changed["unexplained_errors"] = errors
            with self.subTest(errors=errors), self.assertRaises(
                Analysis.AnalysisError
            ):
                Analysis._outcome_class(changed, "blind_fw", True)

    def test_lab_slurm_sentinel_is_the_only_generic_exception(self):
        record = self.resource_prefix()
        record["unexplained_errors"] = [Analysis.LAB_SLURM_ERROR]
        self.assertEqual(
            Analysis._outcome_class(record, "pdb_exact_k2"),
            "search_resource",
        )
        record["unexplained_errors"].append("synthetic")
        with self.assertRaisesRegex(Analysis.AnalysisError, "unexplained"):
            Analysis._outcome_class(record, "pdb_exact_k2")

    def test_runtime_receipt_is_byte_and_semantics_pinned(self):
        self.assertTrue(Analysis.load_validator_unavailable_policy())
        receipt = json.loads(Analysis.RUNTIME_RECEIPT.read_text(encoding="ascii"))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "receipt.json"
            changed = copy.deepcopy(receipt)
            changed["hostname"] = "different"
            path.write_text(json.dumps(changed), encoding="ascii")
            with self.assertRaisesRegex(Analysis.AnalysisError, "bytes changed"):
                Analysis.load_validator_unavailable_policy(path)

            changed = copy.deepcopy(receipt)
            changed["validator"]["available"] = True
            raw = json.dumps(changed, sort_keys=True).encode("ascii")
            path.write_bytes(raw)
            with self.assertRaisesRegex(Analysis.AnalysisError, "absent validator"):
                Analysis.load_validator_unavailable_policy(
                    path,
                    hashlib.sha256(raw).hexdigest(),
                )

    def certificate_pair(self):
        order = "a" * 64
        heuristic = {
            "event": "heuristic_profile",
            "add_nodes": 3,
            "num_values": 2,
            "num_terminals": 4,
            "cofactor_counts": [1, 2, 4],
            "cofactor_width": 4,
            "cofactor_seconds": 0.1,
        }
        candidate = {
            "coverage": 1,
            "solution_cost": 3,
            "effort": 6,
            "wbh_solved_summary_certified": True,
            "wbh_profile_certified": True,
            "wbh_profile_complete": True,
            "wbh_expansion_profile_certified": True,
            "wbh_expansion_profile_complete": True,
            "wbh_profile_state_bits": 2,
            "wbh_profile_variable_order_sha256": order,
            "wbh_profile_done": {"solution_cost": 3, "layer_union_effort": 0},
            "wbh_profile_heuristic_profile": heuristic,
            "wbh_profile_heuristic_paper_cuts": {
                "paper_cut_width": 2,
                "cofactor_width": 4,
                "cut_product_sum": 3,
                "terminal_residuals": 4,
            },
            # fixed_pool_v1 intentionally has no serialized A/T/V fields.
            "pdb_profile_selector_selected": {
                "protocol": "fixed_pool_v1",
                "cofactor_width": 4,
                "width_upper_bound": 7,
            },
            "pdb_profile_selector_trace_certified": True,
            "pdb_profile_selector_raw_pool_sha256": "b" * 64,
            "pdb_profile_selector_raw_pool_common_sha256": "b" * 64,
            "pdb_profile_selector_raw_pool_extended_sha256": None,
            "add_nodes": 3,
            "num_values": 2,
            "num_terminals": 4,
            "width_upper_bound": 7,
            "wbh_expansion_profile": [
                {"g": 0, "active_value_count": 2, "buckets": 2, "pieces": 2},
                {"g": 2, "active_value_count": 1, "buckets": 1, "pieces": 1},
            ],
        }
        blind = {
            "coverage": 1,
            "solution_cost": 3,
            "wbh_profile_certified": True,
            "wbh_profile_complete": True,
            "wbh_profile_state_bits": 2,
            "wbh_profile_variable_order_sha256": order,
            "wbh_profile_done": {"solution_cost": 3, "layer_union_effort": 6},
            "wbh_profile_layer_profiles": [
                {"g": 0, "completed": True, "bdd_nodes": 3, "cofactor_counts": [1, 2, 2]},
                {"g": 1, "completed": True, "bdd_nodes": 0, "cofactor_counts": [1, 1, 1]},
                {"g": 2, "completed": True, "bdd_nodes": 3, "cofactor_counts": [1, 2, 2]},
            ],
        }
        return candidate, blind

    def test_exact_cell_certificate_uses_inner_cuts_and_allows_zero_vg_layer(self):
        candidate, blind = self.certificate_pair()
        result = Analysis._profile_certificate(
            candidate, blind, ("d", "p"), "pdb_exact_k4"
        )
        self.assertEqual(result["status"], "eligible")
        self.assertEqual(result["B_profile"], 15)
        self.assertEqual(result["B_width"], 36)
        self.assertEqual(result["B_add_apply_cudd_safe"], 81)

    def test_certificate_fails_on_order_or_missing_active_layer(self):
        candidate, blind = self.certificate_pair()
        changed = copy.deepcopy(blind)
        changed["wbh_profile_variable_order_sha256"] = "c" * 64
        with self.assertRaisesRegex(Analysis.AnalysisError, "order"):
            Analysis._profile_certificate(candidate, changed, ("d", "p"), "pdb_exact_k2")
        changed = copy.deepcopy(blind)
        changed["wbh_profile_layer_profiles"] = changed["wbh_profile_layer_profiles"][:-1]
        changed["wbh_profile_done"]["layer_union_effort"] = 3
        with self.assertRaisesRegex(Analysis.AnalysisError, "absent"):
            Analysis._profile_certificate(candidate, changed, ("d", "p"), "pdb_exact_k2")

        changed_candidate = copy.deepcopy(candidate)
        changed_candidate["wbh_expansion_profile"][0]["pieces"] = 3
        with self.assertRaisesRegex(Analysis.AnalysisError, "bucket/piece"):
            Analysis._profile_certificate(
                changed_candidate, blind, ("d", "p"), "pdb_exact_k2"
            )

    def test_certificate_classifies_solved_resource_prefix_as_incomplete(self):
        candidate, blind = self.certificate_pair()
        candidate["wbh_profile_complete"] = False
        self.assertEqual(
            Analysis._profile_certificate(
                candidate, blind, ("d", "p"), "pdb_exact_k2"
            )["status"],
            "candidate_metrics_incomplete",
        )

    def test_blind_overhead_skips_plan_found_resource_prefix(self):
        task = ("d", "p")
        matrix = {
            ("blind_fw_profiled", task): {
                "planner_exit_code": 2,
                "coverage": 1,
                "wbh_solved_summary_certified": False,
                "wbh_expansion_profile_complete": False,
                "wbh_profile_complete": False,
                "wbh_profile_certified": False,
            },
            ("blind_fw", task): {
                "planner_exit_code": 2,
                "coverage": 1,
                "wbh_solved_summary_certified": False,
                "wbh_expansion_profile_complete": False,
            },
        }
        result = Analysis.blind_profile_overhead_summary(matrix, [task])
        self.assertEqual(result["jointly_solved_same_cost_pairs"], 0)
        self.assertEqual(
            result["jointly_solved_incomplete_evidence_pairs"], 1
        )

    def test_pool_matching_uses_common_cross_protocol_and_strong_cap_to_cap(self):
        task = ("d", "p")

        def record(extended):
            return {
                "coverage": 1,
                "solution_cost": 2,
                "effort": 3,
                "wbh_solved_summary_certified": True,
                "wbh_expansion_profile_complete": True,
                "pdb_profile_selector_trace_certified": True,
                "pdb_profile_selector_raw_pool_common_sha256": "a" * 64,
                "pdb_profile_selector_raw_pool_extended_sha256": extended,
            }

        matrix = {
            ("pdb_cap_width_k2", task): record("b" * 64),
            ("pdb_exact_k2", task): record(None),
        }
        result = Analysis.paired_summary(
            matrix, [task], "pdb_cap_width_k2", "pdb_exact_k2"
        )
        self.assertEqual(result["same_raw_pool"]["identical_pairs"], 1)

        matrix[("pdb_cap_add_u8", task)] = record("c" * 64)
        result = Analysis.paired_summary(
            matrix, [task], "pdb_cap_width_k2", "pdb_cap_add_u8"
        )
        self.assertEqual(result["same_raw_pool"]["different_pairs"], 1)

    def presearch_matrix(self):
        records = []
        driver = [
            "--validate",
            "--overall-time-limit",
            "{}s".format(P.TIME_LIMIT_SECONDS),
            "--overall-memory-limit",
            "{}M".format(P.MEMORY_LIMIT_MIB),
            "--build",
            "release_no_lp",
        ]
        for label, search in P.CONFIGS:
            records.append({
                "algorithm": label,
                "domain": "d",
                "problem": "p",
                "id": [label, "d", "p"],
                "protocol": P.PROTOCOL,
                "analysis_protocol": P.ANALYSIS_PROTOCOL,
                "cohort_role": P.COHORT_ROLE,
                "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
                "cohort_task_count": P.COHORT_TASKS,
                "config_count": P.CONFIG_COUNT,
                "declared_run_count": P.CELL_COUNT,
                "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
                "matched_budget_archive_sha256": P.MATCH_ARCHIVE_SHA256,
                "matched_budget_candidates": P.MATCH_CANDIDATES,
                "add_match_role": P.ADD_MATCH_ROLE,
                "planner_revision": Analysis.E.PLANNER_REVISION,
                "planner_binary_sha256": Analysis.E.PLANNER_BINARY_SHA256,
                "preprocess_binary_sha256": Analysis.E.PREPROCESS_BINARY_SHA256,
                "planner_preprocess_sha256": Analysis.E.PREPROCESS_BINARY_SHA256,
                "required_lab_version": P.REQUIRED_LAB_VERSION,
                "planner_time_limit": P.TIME_LIMIT_SECONDS,
                "planner_memory_limit": P.MEMORY_LIMIT_MIB,
                "local_revision": Analysis.E.PLANNER_REVISION,
                "global_revision": Analysis.E.PLANNER_REVISION,
                "component_options": ["--search", search],
                "driver_options": driver,
                "build_options": list(P.BUILD_OPTIONS),
                "cohort_stratum": "primary_other",
                "coverage": 0,
                "planner_exit_code": 21,
                "error": "translate-out-of-time",
                "unsolvable": 0,
                "unexplained_errors": [],
                "construction_completed": None,
                "wbh_profile_expected": label != "blind_fw",
            })
        return records

    def test_matrix_rejects_mixed_revision_and_mislabeled_search(self):
        records = self.presearch_matrix()
        Analysis.validate_matrix(records, expected_tasks=1)
        changed = copy.deepcopy(records)
        changed[0]["local_revision"] = "c" * 40
        with self.assertRaisesRegex(Analysis.AnalysisError, "local_revision"):
            Analysis.validate_matrix(changed, expected_tasks=1)
        changed = copy.deepcopy(records)
        changed[0]["component_options"] = ["--search", P.SEARCHES[P.LABELS[1]]]
        with self.assertRaisesRegex(Analysis.AnalysisError, "component options"):
            Analysis.validate_matrix(changed, expected_tasks=1)

    def test_matrix_accepts_only_exact_lab_time_limit_float(self):
        records = self.presearch_matrix()
        for record in records:
            record["planner_time_limit"] = float(P.TIME_LIMIT_SECONDS)
        Analysis.validate_matrix(records, expected_tasks=1)
        for value in (
            float(P.TIME_LIMIT_SECONDS) + 0.5,
            str(P.TIME_LIMIT_SECONDS),
            True,
        ):
            changed = copy.deepcopy(records)
            changed[0]["planner_time_limit"] = value
            with self.subTest(value=value), self.assertRaisesRegex(
                Analysis.AnalysisError, "planner_time_limit"
            ):
                Analysis.validate_matrix(changed, expected_tasks=1)

    def test_matrix_accepts_profile_parser_omission_only_before_search(self):
        records = self.presearch_matrix()
        for record in records:
            del record["wbh_profile_expected"]
        Analysis.validate_matrix(records, expected_tasks=1)

        changed = copy.deepcopy(records)
        profiled = next(
            record for record in changed if record["algorithm"] != "blind_fw"
        )
        profiled.update(self.resource_prefix())
        with self.assertRaisesRegex(Analysis.AnalysisError, "parser contract"):
            Analysis.validate_matrix(changed, expected_tasks=1)


class ExpansionParserTests(unittest.TestCase):
    def test_active_values_are_grouped_by_g_and_cutoff(self):
        events = [
            {
                "event": "schema",
                "version": 2,
                "node_count_convention": "inner_nodes_per_piece",
                "image_count_convention": "per_piece_attempted_completed",
                "expansion_count_convention": "completed_with_attempts",
            },
            {
                "event": "heuristic",
                "add_nodes": 1,
                "num_values": 3,
                "num_terminals": 3,
                "add_level_nodes": [1],
                "width_upper_bound": 4,
            },
            {
                "event": "construction",
                "heuristic": "pdb_x",
                "seconds": 0.1,
                "size_bound": 1,
                "value_cap": -1,
                "completed": True,
            },
            {"event": "expand", "g": 0, "h": 2, "completed": True, "piece_count": 1, "bdd_nodes": 5, "states": 1.0, "image_time": 0.1},
            {"event": "expand", "g": 0, "h": 4, "completed": True, "piece_count": 1, "bdd_nodes": 7, "states": 1.0, "image_time": 0.1},
            {"event": "done", "effort": 5, "solution_cost": 3},
            {
                "event": "summary",
                "expanded_bdd_nodes": 12,
                "expanded_states": 2.0,
                "expanded_bdd_pieces": 2,
                "attempted_bdd_nodes": 12,
                "attempted_states": 2.0,
                "attempted_bdd_pieces": 2,
                "bucket_expansions": 2,
                "bucket_expansion_attempts": 2,
                "image_events": 0,
                "bucket_images": 0,
                "image_source_buckets": 0,
                "image_source_pieces": 0,
                "image_calls_attempted": 0,
                "image_calls_completed": 0,
                "batched_images": 0,
                "image_time": 0.0,
                "solved": True,
            },
        ]
        props = {"algorithm": "pdb_exact_k2"}
        Parser.parse_expansion_details("\n".join(map(line, events)) + "\n", props)
        self.assertTrue(props["wbh_expansion_profile_certified"])
        self.assertEqual(props["wbh_expansion_profile"][0]["active_h_values"], [2])
        self.assertEqual(props["wbh_expansion_profile"][0]["effort"], 5)


class JjExporterTests(unittest.TestCase):
    def test_git_backend_full_id_is_40_hex(self):
        self.assertIsNotNone(JJ.COMMIT_RE.fullmatch("a" * 40))
        self.assertIsNone(JJ.COMMIT_RE.fullmatch("a" * 64))

    def test_current_commit_requires_one_conflict_free_full_id(self):
        revision = "a" * 40
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".jj").mkdir()
            with mock.patch.object(
                JJ, "_run_jj", return_value=(revision + "\t0\n").encode("ascii")
            ):
                self.assertEqual(JJ.current_commit(repo), revision)
            for raw in (b"", (revision + "\t1\n").encode("ascii"), b"short\t0\n"):
                with self.subTest(raw=raw), mock.patch.object(
                    JJ, "_run_jj", return_value=raw
                ):
                    with self.assertRaises(JJ.JjCacheError):
                        JJ.current_commit(repo)

    def test_parent_commit_uses_the_same_fail_closed_identity_parser(self):
        revision = "b" * 40
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            (repo / ".jj").mkdir()
            with mock.patch.object(
                JJ, "_run_jj", return_value=(revision + "\t0\n").encode("ascii")
            ) as run:
                self.assertEqual(JJ.parent_commit(repo), revision)
            self.assertIn("@-", run.call_args.args[1])

    def test_ancestor_and_tracked_file_queries_fail_closed(self):
        ancestor = "a" * 40
        descendant = "b" * 40
        with mock.patch.object(
            JJ, "resolve_pinned_commit", side_effect=(ancestor, descendant)
        ), mock.patch.object(
            JJ, "_run_jj", return_value=(ancestor + "\t0\n").encode("ascii")
        ):
            JJ.require_ancestor(Path("/repo"), ancestor, descendant)
        with mock.patch.object(JJ, "_run_jj", return_value=b""):
            self.assertFalse(JJ.file_is_tracked_at(Path("/repo"), ancestor, "x.py"))
        with mock.patch.object(JJ, "_run_jj", return_value=b"x.py\n"):
            self.assertTrue(JJ.file_is_tracked_at(Path("/repo"), ancestor, "x.py"))
        with self.assertRaises(JJ.JjCacheError):
            JJ.file_is_tracked_at(Path("/repo"), ancestor, "../x.py")

    def test_tracked_file_digest_reads_the_pinned_tree_not_the_worktree(self):
        revision = "a" * 40
        with mock.patch.object(JJ, "file_is_tracked_at", return_value=True), mock.patch.object(
            JJ, "_file_bytes", return_value=b"pinned bytes"
        ):
            self.assertEqual(
                JJ.tracked_file_sha256(Path("/repo"), revision, "x.py"),
                "977d59924a4dfd9d4e93c74467f3253786327c8c28e69a75f30cf0429dab77c7",
            )

    def test_export_excludes_unsupported_ancillary_symlinks(self):
        revision = "a" * 40
        entries = (
            JJ.TreeEntry("build.py", "file", True),
            JJ.TreeEntry("fast-downward.py", "file", True),
            JJ.TreeEntry("src/CMakeLists.txt", "file", False),
            JJ.TreeEntry("baselines/x/latest", "symlink", False),
        )
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "export"
            with mock.patch.object(JJ, "resolve_pinned_commit", return_value=revision), mock.patch.object(JJ, "list_tree", return_value=entries), mock.patch.object(JJ, "_file_bytes", return_value=b"#!/bin/sh\n"):
                digest = JJ.export_revision(Path(directory), revision, destination)
            self.assertEqual(len(digest), 64)
            self.assertTrue((destination / "build.py").is_file())
            self.assertTrue((destination / "fast-downward.py").is_file())
            self.assertTrue((destination / "src/CMakeLists.txt").is_file())
            self.assertFalse((destination / "baselines").exists())

    def test_unexcluded_symlink_fails_closed(self):
        revision = "a" * 40
        entries = (JJ.TreeEntry("src/link", "symlink", False),)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "export"
            with mock.patch.object(JJ, "resolve_pinned_commit", return_value=revision), mock.patch.object(JJ, "list_tree", return_value=entries):
                with self.assertRaisesRegex(JJ.JjCacheError, "symlink"):
                    JJ.export_revision(Path(directory), revision, destination)
            self.assertFalse(destination.exists())


class SourceContractTests(unittest.TestCase):
    def test_cpp_add_protocol_keeps_width_score_versions(self):
        source = (P.SCRIPT_DIR.parent / "src/search/symbolic/wbh_pdb_levels.cc").read_text()
        self.assertNotIn("ADD_CAP_GRID_SELECTOR_SCORE", source)
        self.assertIn("cap_grid ? CAP_GRID_SELECTOR_SCORE", source)
        self.assertIn("candidate_is_better(*pattern_winner, *winner)", source)


if __name__ == "__main__":
    unittest.main()
