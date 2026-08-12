#!/usr/bin/env python3
"""Adversarial tests for :mod:`pdb_cap_selector_parser`."""

import base64
import copy
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_arrhenius_common as C
import pdb_cap_selector_parser as P


PREFIX = "[t=0.071340s, 534048 KB] "


def record(
    sources,
    pattern,
    states,
    cap,
    width,
    upper,
    raw_width,
    raw_upper,
    raw_values,
    values,
    initial_h,
    finite_sum,
    finite_count,
    dead_count,
    budget=8,
    raw_max=None,
    raw_initial_h=None,
    raw_finite_sum=None,
):
    terminals = values + int(dead_count > 0)
    raw_terminals = raw_values + int(dead_count > 0)
    raw_max_value = raw_values - 1 if raw_max is None else raw_max
    raw_initial_value = raw_max_value if raw_initial_h is None else raw_initial_h
    raw_sum = (
        raw_max_value * finite_count
        if raw_finite_sum is None
        else raw_finite_sum
    )
    if sources == ["empty"]:
        raw_counts = [[0, 1]]
    elif "cegar" in sources:
        raw_counts = [[0, 2], [1, 1], [2, 1], [3, 4]]
    else:
        raw_counts = [[0, 1], [1, 2], [2, 1]]
    return {
        "protocol": P.PROTOCOL,
        "score_version": P.SCORE_VERSION,
        "sources": sources,
        "pattern": pattern,
        "abstract_states": states,
        "initial_dead_end": False,
        "initial_h": initial_h,
        "finite_sum": finite_sum,
        "finite_count": finite_count,
        "dead_count": dead_count,
        "cofactor_width": width,
        "width_upper_bound": upper,
        "cofactor_width_budget": budget,
        "value_cap": cap,
        "add_nodes": upper - terminals,
        "num_terminals": terminals,
        "raw_add_nodes": raw_upper - raw_terminals,
        "raw_num_terminals": raw_terminals,
        "raw_cofactor_width": raw_width,
        "raw_width_upper_bound": raw_upper,
        "raw_num_values": raw_values,
        "raw_max_finite_value": raw_max_value,
        "raw_finite_sum": raw_sum,
        "raw_finite_count": finite_count,
        "raw_dead_count": dead_count,
        "raw_initial_dead_end": False,
        "raw_initial_h": raw_initial_value,
        "raw_initial_value_count": dict(raw_counts)[raw_initial_value],
        "raw_value_histogram": P.encode_raw_value_histogram(raw_counts),
        "transformed_num_values": values,
        "feasible": width <= budget,
        "rejection_reason": None if width <= budget else "cofactor_width_budget",
    }


def fixture():
    empty = record(
        ["empty"], [], 1, -1, 1, 1, 1, 1, 1, 1, 0, 0, 1, 0,
        raw_initial_h=0, raw_finite_sum=0,
    )
    prefix0 = record(
        ["bdd_prefix", "goal_prefix", "goal_fill"],
        [0], 4, 0, 1, 1, 9, 15, 3, 1, 0, 0, 4, 0,
        raw_initial_h=1, raw_finite_sum=4,
    )
    prefix1 = record(
        ["bdd_prefix", "goal_prefix", "goal_fill"],
        [0], 4, 1, 4, 7, 9, 15, 3, 2, 1, 3, 4, 0,
        raw_initial_h=1, raw_finite_sum=4,
    )
    prefix_exact = record(
        ["bdd_prefix", "goal_prefix", "goal_fill"],
        [0], 4, -1, 9, 15, 9, 15, 3, 3, 1, 4, 4, 0,
        raw_initial_h=1, raw_finite_sum=4,
    )
    cegar0 = record(
        ["cegar"], [1], 10, 0, 4, 9, 16, 30, 4, 1, 0, 0, 8, 2,
        raw_initial_h=3, raw_finite_sum=15,
    )
    cegar1 = record(
        ["cegar"], [1], 10, 1, 5, 12, 16, 30, 4, 2, 1, 6, 8, 2,
        raw_initial_h=3, raw_finite_sum=15,
    )
    cegar2 = record(
        ["cegar"], [1], 10, 2, 9, 19, 16, 30, 4, 3, 2, 11, 8, 2,
        raw_initial_h=3, raw_finite_sum=15,
    )
    cegar_exact = record(
        ["cegar"], [1], 10, -1, 16, 30, 16, 30, 4, 4, 3, 15, 8, 2,
        raw_initial_h=3, raw_finite_sum=15,
    )
    candidates = [
        empty,
        prefix0,
        prefix1,
        prefix_exact,
        cegar0,
        cegar1,
        cegar2,
        cegar_exact,
    ]
    previous_pattern = None
    for candidate in candidates:
        pattern_key = tuple(candidate["pattern"])
        if pattern_key == previous_pattern:
            candidate["raw_value_histogram"] = None
        previous_pattern = pattern_key
    selected = copy.deepcopy(cegar1)
    selected["raw_value_histogram"] = None
    final = {
        "pattern_size": 1,
        "selected_source": "cegar",
        "abstract_states": 10,
        "cofactor_width_budget": 8,
        "value_cap": 1,
        "num_values": 2,
        "cofactor_width": 5,
        "width_upper_bound": 12,
    }
    return candidates, selected, final


def render(candidates, selected, final):
    lines = []
    for candidate in candidates:
        lines.append(
            PREFIX + "PDB width-selector v1 candidate: "
            + json.dumps(candidate, separators=(",", ":"))
        )
    if selected is not None:
        lines.append(
            PREFIX + "PDB width-selector v1 selected: "
            + json.dumps(selected, separators=(",", ":"))
        )
    if final is not None:
        lines.append(
            PREFIX
            + "wbh PDB heuristic: pattern_size={pattern_size}, "
              "selected_source={selected_source}, "
              "abstract_states={abstract_states}, "
              "cofactor_width_budget={cofactor_width_budget}, "
              "value_cap={value_cap}, values={num_values}, "
              "cofactor_width={cofactor_width}, "
              "width_upper_bound={width_upper_bound}".format(**final)
        )
    return "\n".join(lines) + "\n"


class CapSelectorParserTest(unittest.TestCase):
    def parse(self, candidates=None, selected=None, final=None):
        base_candidates, base_selected, base_final = fixture()
        props = {}
        P.parse_cap_selector_log(
            render(
                base_candidates if candidates is None else candidates,
                base_selected if selected is None else selected,
                base_final if final is None else final,
            ),
            props,
        )
        return props

    def parse_with_props(self, props, candidates=None, selected=None, final=None):
        base_candidates, base_selected, base_final = fixture()
        P.parse_cap_selector_log(
            render(
                base_candidates if candidates is None else candidates,
                base_selected if selected is None else selected,
                base_final if final is None else final,
            ),
            props,
        )
        return props

    def test_valid_complete_trace(self):
        props = self.parse()
        self.assertNotIn("unexplained_errors", props)
        self.assertTrue(props[C.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY])
        self.assertTrue(props[C.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY])
        self.assertEqual(props["pdb_selected_value_cap"], 1)
        self.assertEqual(props["pdb_final_cofactor_width"], 5)
        self.assertRegex(props[C.PDB_SELECTOR_TRACE_SHA256_PROPERTY], r"^[0-9a-f]{64}$")
        self.assertRegex(props[P.RAW_POOL_SHA256_PROPERTY], r"^[0-9a-f]{64}$")

    def test_legacy_delegation(self):
        text = (
            PREFIX + "wbh PDB heuristic: pattern_size=0, values=1, "
            "cofactor_width=1, width_upper_bound=1\n"
        )
        props = {}
        P.parse_cap_selector_log(text, props)
        self.assertEqual(props["pdb_final_format"], "legacy")
        self.assertNotIn("pdb_cap_selector_parser_protocol", props)

    def test_clean_incomplete_prefix(self):
        candidates, _, _ = fixture()
        props = {}
        P.parse_cap_selector_log(render(candidates[:3], None, None), props)
        self.assertFalse(props[C.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY])
        self.assertFalse(props[C.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY])
        self.assertNotIn("unexplained_errors", props)

    def test_weaker_selected_cap_rejected(self):
        candidates, _, final = fixture()
        weaker = copy.deepcopy(candidates[4])
        final = dict(final, value_cap=0, num_values=1, cofactor_width=4,
                     width_upper_bound=9)
        self.assertIn("unexplained_errors", self.parse(candidates, weaker, final))

    def test_width_nonmonotonicity_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[5]["cofactor_width"] = 3
        candidates[5]["feasible"] = True
        self.assertIn("unexplained_errors", self.parse(candidates, selected, final))

    def test_non_grid_cap_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[5]["value_cap"] = 3
        self.assertIn("unexplained_errors", self.parse(candidates, selected, final))

    def test_transform_increase_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[5]["cofactor_width"] = 17
        candidates[5]["feasible"] = False
        candidates[5]["rejection_reason"] = "cofactor_width_budget"
        self.assertIn("unexplained_errors", self.parse(candidates, selected, final))

    def test_final_cap_mismatch_rejected(self):
        candidates, selected, final = fixture()
        self.assertIn(
            "unexplained_errors",
            self.parse(candidates, selected, dict(final, value_cap=2)),
        )

    def test_wrong_protocol_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[0]["protocol"] = "fixed_pool_v1"
        self.assertIn("unexplained_errors", self.parse(candidates, selected, final))

    def test_missing_producer_cap_rejected(self):
        candidates, _, final = fixture()
        candidates = copy.deepcopy(candidates)
        del candidates[5]  # CEGAR cap 1 must precede cap 2 and exact.
        weaker = copy.deepcopy(candidates[4])
        final = dict(
            final,
            value_cap=0,
            num_values=1,
            cofactor_width=4,
            width_upper_bound=9,
        )
        self.assertIn(
            "unexplained_errors", self.parse(candidates, weaker, final)
        )

    def test_mixed_width_budgets_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        for item in candidates[:4]:
            item["cofactor_width_budget"] = 2
            item["feasible"] = item["cofactor_width"] <= 2
            item["rejection_reason"] = (
                None if item["feasible"] else "cofactor_width_budget"
            )
        self.assertIn(
            "unexplained_errors", self.parse(candidates, selected, final)
        )

    def test_group_order_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        groups = [candidates[:1], candidates[1:4], candidates[4:]]
        reordered = groups[2] + groups[0] + groups[1]
        self.assertIn(
            "unexplained_errors", self.parse(reordered, selected, final)
        )

    def test_final_before_selector_records_rejected(self):
        candidates, selected, final = fixture()
        canonical = render(candidates, selected, final).splitlines()
        props = {}
        P.parse_cap_selector_log(
            "\n".join([canonical[-1]] + canonical[:-1]) + "\n", props
        )
        self.assertIn("unexplained_errors", props)

    def test_oversized_final_integer_fails_closed(self):
        candidates, selected, final = fixture()
        text = render(candidates, selected, final).replace(
            "pattern_size=1,", "pattern_size={},".format("9" * 5000)
        )
        props = {}
        P.parse_cap_selector_log(text, props)
        self.assertIn("unexplained_errors", props)
        self.assertIn(
            "final line is malformed",
            props[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY],
        )

    def test_noncanonical_final_integer_fails_closed(self):
        candidates, selected, final = fixture()
        for old, new in (("pattern_size=1,", "pattern_size=01,"), ("value_cap=1,", "value_cap=-0,")):
            with self.subTest(new=new):
                props = {}
                P.parse_cap_selector_log(
                    render(candidates, selected, final).replace(old, new), props
                )
                self.assertIn("unexplained_errors", props)

    def test_malformed_record_does_not_crash(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        del candidates[0]["raw_num_values"]
        props = self.parse(candidates, selected, final)
        self.assertIn("unexplained_errors", props)

    def test_deeply_nested_json_fails_closed(self):
        payload = (
            '{"protocol":"' + P.PROTOCOL + '","x":'
            + "[" * 2000 + "0" + "]" * 2000 + "}"
        )
        props = {}
        P.parse_cap_selector_log(
            PREFIX + "PDB width-selector v1 candidate: " + payload + "\n",
            props,
        )
        self.assertIn("unexplained_errors", props)
        self.assertIn(
            "JSON is malformed",
            props[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY],
        )

    def test_whitespace_protocol_dispatch_with_deep_json_fails_closed(self):
        payload = (
            '{"protocol": "' + P.PROTOCOL + '","x":'
            + "[" * 2000 + "0" + "]" * 2000 + "}"
        )
        props = {}
        P.parse_cap_selector_log(
            PREFIX + "PDB width-selector v1 candidate: " + payload + "\n",
            props,
        )
        self.assertIn("unexplained_errors", props)
        self.assertEqual(
            props.get("pdb_cap_selector_parser_protocol"), P.PARSER_PROTOCOL
        )

    def test_non_string_source_does_not_crash(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[0]["sources"] = [[]]
        self.assertIn(
            "unexplained_errors", self.parse(candidates, selected, final)
        )

    def test_cross_cap_census_mutation_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[5]["finite_count"] = 9
        candidates[5]["dead_count"] = 1
        candidates[5]["num_terminals"] = 3
        candidates[5]["add_nodes"] = 9
        selected = copy.deepcopy(candidates[5])
        self.assertIn(
            "unexplained_errors", self.parse(candidates, selected, final)
        )

    def test_incomplete_group_cannot_skip_to_exact_or_next_group(self):
        candidates, _, _ = fixture()
        broken = [candidates[0], candidates[1], candidates[3], candidates[4]]
        props = self.parse(broken, None, None)
        self.assertIn("unexplained_errors", props)

    def test_valid_late_source_dedup_topology(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        for item in candidates[1:4]:
            item["sources"] = ["bdd_prefix", "cegar"]
        for item in candidates[4:]:
            item["sources"] = ["goal_prefix", "goal_fill"]
        selected = copy.deepcopy(candidates[5])
        final = dict(final, selected_source="goal_prefix")
        props = self.parse(candidates, selected, final)
        self.assertNotIn("unexplained_errors", props)

    def test_wbh_property_disagreement_rejected(self):
        props = {
            "cofactor_width": 999,
            "width_upper_bound": 999,
            "num_values": 999,
            "num_terminals": 999,
            "add_nodes": 0,
            "value_cap": 999,
            "heuristic_kind": "wrong",
            "heuristic_size_bound": 999,
        }
        self.parse_with_props(props)
        self.assertIn("unexplained_errors", props)

    def test_materialization_status_mix_rejected_without_crash(self):
        candidates, _, _ = fixture()
        candidates = copy.deepcopy(candidates)
        item = copy.deepcopy(candidates[4])
        for key in P.STATISTIC_KEYS:
            item[key] = None
        item["value_cap"] = -1
        item["feasible"] = False
        item["rejection_reason"] = "abstract_state_budget"
        broken = candidates[:5] + [item]
        props = self.parse(broken, None, None)
        self.assertIn("unexplained_errors", props)

    def test_impossible_cap_sum_rejected(self):
        candidates, _, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[5]["finite_sum"] = 8
        selected = copy.deepcopy(candidates[5])
        self.assertIn(
            "unexplained_errors", self.parse(candidates, selected, final)
        )

    def test_empty_source_cannot_name_nonempty_pattern(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[0]["pattern"] = [999999]
        self.assertIn(
            "unexplained_errors", self.parse(candidates, selected, final)
        )

    def test_late_dedup_source_is_valid_in_interrupted_first_group(self):
        candidates, _, _ = fixture()
        first = copy.deepcopy(candidates[0])
        first["sources"] = ["empty", "cegar"]
        props = {}
        P.parse_cap_selector_log(render([first], None, None), props)
        self.assertFalse(props[C.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY])
        self.assertFalse(props[C.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY])
        self.assertEqual(
            props[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY],
            "cap-grid selector trace is incomplete",
        )
        self.assertNotIn("unexplained_errors", props)

    def test_prefix_cannot_skip_an_earlier_source(self):
        candidates, _, _ = fixture()
        broken = [copy.deepcopy(candidates[0]), copy.deepcopy(candidates[1])]
        broken[1]["sources"] = ["goal_prefix"]
        props = {}
        P.parse_cap_selector_log(render(broken, None, None), props)
        self.assertIn("unexplained_errors", props)

    def test_duplicate_exact_transform_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates.insert(1, copy.deepcopy(candidates[0]))
        self.assertIn(
            "unexplained_errors", self.parse(candidates, selected, final)
        )

    def test_raw_width_cannot_exceed_raw_upper_bound(self):
        candidates, _, _ = fixture()
        candidates = copy.deepcopy(candidates[:2])
        candidates[1]["raw_cofactor_width"] = 100
        props = {}
        P.parse_cap_selector_log(render(candidates, None, None), props)
        self.assertIn("unexplained_errors", props)

    def test_materialized_candidate_cannot_exceed_state_budget(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[4]["abstract_states"] = 100001
        self.assertIn(
            "unexplained_errors", self.parse(candidates, selected, final)
        )

    def test_unmaterialized_cegar_requires_oversized_singleton(self):
        candidates, _, _ = fixture()
        item = copy.deepcopy(candidates[4])
        for key in P.STATISTIC_KEYS:
            item[key] = None
        item["value_cap"] = -1
        item["pattern"] = [1, 2]
        item["abstract_states"] = 10
        item["feasible"] = False
        item["rejection_reason"] = "abstract_state_budget"
        props = {}
        P.parse_cap_selector_log(render([candidates[0], item], None, None), props)
        self.assertIn("unexplained_errors", props)

    def test_histogram_recomputes_score_driving_sum(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[5]["finite_sum"] += 1
        selected = copy.deepcopy(candidates[5])
        selected["raw_value_histogram"] = None
        props = self.parse(candidates, selected, final)
        self.assertIn("unexplained_errors", props)
        self.assertIn(
            "transform contradicts exact raw histogram",
            props[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY],
        )

    def test_histogram_recomputes_value_count(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[5]["transformed_num_values"] = 1
        candidates[5]["num_terminals"] = 2
        candidates[5]["add_nodes"] = candidates[5]["width_upper_bound"] - 2
        props = self.parse(candidates, selected, final)
        self.assertIn("unexplained_errors", props)

    def test_histogram_recomputes_raw_census(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        for item in candidates[4:]:
            item["raw_finite_sum"] += 1
        props = self.parse(candidates, selected, final)
        self.assertIn("unexplained_errors", props)
        self.assertIn(
            "raw histogram contradicts raw statistics",
            props[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY],
        )

    def test_histogram_binds_initial_value_and_multiplicity(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        for item in candidates[4:]:
            item["raw_initial_h"] = 2
            item["raw_initial_value_count"] = 4
            item["initial_h"] = 2 if item["value_cap"] < 0 else min(2, item["value_cap"])
        props = self.parse(candidates, selected, final)
        self.assertIn("unexplained_errors", props)
        self.assertIn(
            "raw histogram contradicts raw statistics",
            props[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY],
        )

    def test_histogram_occurs_only_on_first_candidate_per_pattern(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[2]["raw_value_histogram"] = candidates[1]["raw_value_histogram"]
        props = self.parse(candidates, selected, final)
        self.assertIn("unexplained_errors", props)
        self.assertIn(
            "only on a pattern's first candidate",
            props[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY],
        )

    def test_missing_first_histogram_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[4]["raw_value_histogram"] = None
        self.assertIn("unexplained_errors", self.parse(candidates, selected, final))

    def test_noncanonical_histogram_base64_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[4]["raw_value_histogram"] += "="
        self.assertIn("unexplained_errors", self.parse(candidates, selected, final))

    def test_nonminimal_histogram_varint_rejected(self):
        # The canonical payload for one (distance=0,count=1) pair is
        # 01 01 01.  Encode the leading 1 redundantly as 81 00.
        payload = base64.urlsafe_b64encode(b"\x81\x00\x01\x01").rstrip(
            b"="
        ).decode("ascii")
        with self.assertRaisesRegex(ValueError, "noncanonical"):
            P.decode_raw_value_histogram(payload)

    def test_histogram_declared_count_above_state_bound_rejected(self):
        data = bytearray()
        P._append_uvarint(data, P.MAX_ABSTRACT_STATES + 1)
        payload = base64.urlsafe_b64encode(bytes(data)).rstrip(b"=").decode(
            "ascii"
        )
        with self.assertRaisesRegex(ValueError, "exceeds producer type"):
            P.decode_raw_value_histogram(payload)

    def test_histogram_total_frequency_above_state_bound_rejected(self):
        payload = P.encode_raw_value_histogram(
            [[0, P.MAX_ABSTRACT_STATES], [1, 1]]
        )
        with self.assertRaisesRegex(ValueError, "exceeds state budget"):
            P.decode_raw_value_histogram(payload)

    def test_selected_record_cannot_repeat_histogram(self):
        candidates, selected, final = fixture()
        selected = copy.deepcopy(selected)
        selected["raw_value_histogram"] = candidates[4]["raw_value_histogram"]
        props = self.parse(candidates, selected, final)
        self.assertIn("unexplained_errors", props)
        self.assertIn(
            "selected record repeats the raw histogram",
            props[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY],
        )

    def test_histogram_trailing_bytes_rejected(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        payload = candidates[4]["raw_value_histogram"]
        data = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        candidates[4]["raw_value_histogram"] = base64.urlsafe_b64encode(
            data + b"\x01"
        ).rstrip(b"=").decode("ascii")
        self.assertIn("unexplained_errors", self.parse(candidates, selected, final))

    def test_histogram_must_include_zero_goal(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[4]["raw_value_histogram"] = P.encode_raw_value_histogram(
            [[1, 2], [2, 1], [3, 5]]
        )
        self.assertIn("unexplained_errors", self.parse(candidates, selected, final))

    def test_histogram_rejects_integer_infinity_sentinel(self):
        with self.assertRaises(ValueError):
            P.encode_raw_value_histogram([[0, 1], [P.INT_MAX, 1]])
        data = bytearray()
        P._append_uvarint(data, 2)
        P._append_uvarint(data, 1)  # -1 -> 0
        P._append_uvarint(data, 1)
        P._append_uvarint(data, P.INT_MAX)  # 0 -> INT_MAX
        P._append_uvarint(data, 1)
        payload = base64.urlsafe_b64encode(bytes(data)).rstrip(b"=").decode(
            "ascii"
        )
        with self.assertRaisesRegex(ValueError, "infinity sentinel"):
            P.decode_raw_value_histogram(payload)

    def test_retained_records_replace_histogram_with_digest(self):
        props = self.parse()
        for item in props[C.PDB_SELECTOR_CANDIDATES_PROPERTY]:
            if item["raw_num_values"] is not None:
                self.assertRegex(item["raw_value_histogram"], r"^sha256:[0-9a-f]{64}$")
        self.assertRegex(
            props[C.PDB_SELECTOR_SELECTED_PROPERTY]["raw_value_histogram"],
            r"^sha256:[0-9a-f]{64}$",
        )

    def test_zero_heuristic_initial_multiplicity_covers_finite_states(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[0]["raw_initial_value_count"] = 0
        props = self.parse(candidates, selected, final)
        self.assertIn("unexplained_errors", props)

    def test_native_width_budget_bound(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        for item in candidates:
            item["cofactor_width_budget"] = P.INT_MAX + 1
        selected = copy.deepcopy(selected)
        selected["cofactor_width_budget"] = P.INT_MAX + 1
        final = dict(final, cofactor_width_budget=P.INT_MAX + 1)
        self.assertIn("unexplained_errors", self.parse(candidates, selected, final))

    def test_width_covers_terminals_and_reduced_add_census(self):
        candidates, selected, final = fixture()
        candidates = copy.deepcopy(candidates)
        candidates[2]["cofactor_width"] = 1
        candidates[2]["feasible"] = True
        candidates[2]["rejection_reason"] = None
        props = self.parse(candidates, selected, final)
        self.assertIn("unexplained_errors", props)
        self.assertIn(
            "A/T/U/V identity is invalid",
            props[C.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY],
        )


if __name__ == "__main__":
    unittest.main()
