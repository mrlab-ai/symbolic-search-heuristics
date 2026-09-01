#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

import pdb_terminal_incidence_selector_parser as S


class Props(dict):
    def add_unexplained_error(self, message):
        self.setdefault("unexplained_errors", []).append(message)


def _line(value):
    return json.dumps(value, separators=(",", ":")) + "\n"


def _rehash_preselection(events):
    candidates = [item for item in events if item.get("event") == "candidate"]
    digest = hashlib.sha256(
        "".join(S._candidate_line(item) for item in candidates).encode("ascii")
    ).hexdigest()
    preselection = next(
        item for item in events if item.get("event") == "preselection"
    )
    preselection["preselection_sha256"] = digest
    preselection["candidate_count"] = len(candidates)
    for item in events:
        if item.get("event") in {"reference", "selected"}:
            item["preselection_sha256"] = digest


def _full_trace(*, mode="guided", selected_cap=None, timing=1.0):
    schema = dict(S.SCHEMA_EVENT)
    probe = {
        "event": "probe",
        "target_layers": 16,
        "completed_layers": 16,
        "attempts": 16,
        "complete": True,
        "g_values": list(range(16)),
        "bdd_nodes": [1] * 16,
        "cpu_seconds": timing,
        "wall_seconds": timing + 0.1,
        "peak_memory_before_kb": 100,
        "peak_memory_after_kb": 120,
        "peak_memory_delta_kb": 20,
    }
    nonempty_sources = list(schema["candidate_sources"][1:])
    patterns = [
        {
            "pattern_index": 0,
            "sources": ["empty"],
            "pattern": [],
            "abstract_states": 1,
            "within_state_budget": True,
        },
        {
            "pattern_index": 1,
            "sources": nonempty_sources,
            "pattern": [0, 1],
            "abstract_states": 64,
            "within_state_budget": True,
        },
    ]
    pool_payload = (
        "0|sources=empty|pattern=|abstract_states=1|within_state_budget=1\n"
        "1|sources=bdd_prefix,goal_prefix,goal_fill,cegar|"
        "pattern=0,1|abstract_states=64|within_state_budget=1\n"
    )
    pool_sha = hashlib.sha256(pool_payload.encode("ascii")).hexdigest()
    pool = {
        "event": "pool",
        "protocol": S.TRACE_PROTOCOL,
        "state_budget": 100000,
        "pool_sha256": pool_sha,
        "patterns": patterns,
    }
    candidates = [{
        "event": "candidate",
        "protocol": S.TRACE_PROTOCOL,
        "score_version": S.SCORE_VERSION,
        "pattern_index": 0,
        "sources": ["empty"],
        "pattern": [],
        "abstract_states": 1,
        "value_cap": None,
        "initial_dead_end": False,
        "initial_h": 0,
        "finite_sum": 0,
        "finite_count": 1,
        "dead_count": 0,
        "cofactor_width": 1,
        "width_upper_bound": 1,
        "raw_max_finite_value": 0,
        "raw_value_histogram": "AQEB",
        "terminal_incidence_by_layer": [1] * 16,
        "terminal_incidence": 16,
        "reference_feasible": True,
        "incidence_feasible": True,
        "retained_for_pattern": True,
    }]
    variants = (
        # The exact histogram {0: 16, 1: 16, 2: 32} makes the C++ cap grid
        # the exact prefix 0, 1 followed by the exact transform. Width selects
        # cap 1 as the reference; incidence retains the stronger exact form.
        # Each tuple holds cap, initial h, finite sum, cofactor width, total
        # ADD nodes, terminal incidence, reference feasibility, and retention.
        (0, 0, 0, 1, 1, 16, True, False),
        (1, 1, 48, 2, 3, 18, True, False),
        (None, 2, 80, 40, 64, 18, False, True),
    )
    for (
        cap, initial_h, finite_sum, width, upper, incidence, ref_ok, retained
    ) in variants:
        candidate = {
            "event": "candidate",
            "protocol": S.TRACE_PROTOCOL,
            "score_version": S.SCORE_VERSION,
            "pattern_index": 1,
            "sources": nonempty_sources,
            "pattern": [0, 1],
            "abstract_states": 64,
            "value_cap": cap,
            "initial_dead_end": False,
            "initial_h": initial_h,
            "finite_sum": finite_sum,
            "finite_count": 64,
            "dead_count": 0,
            "cofactor_width": width,
            "width_upper_bound": upper,
            "raw_max_finite_value": 2,
            "raw_value_histogram": None if cap is not None else "AwEQARABIA",
            "terminal_incidence_by_layer": (
                [1] * 16 if incidence == 16 else [2, 2] + [1] * 14
            ),
            "terminal_incidence": incidence,
            "reference_feasible": ref_ok,
            "incidence_feasible": True,
            "retained_for_pattern": retained,
        }
        candidates.append(candidate)
    pre_sha = hashlib.sha256(
        "".join(S._candidate_line(item) for item in candidates).encode("ascii")
    ).hexdigest()
    preselection = {
        "event": "preselection",
        "pool_sha256": pool_sha,
        "preselection_sha256": pre_sha,
        "candidate_count": len(candidates),
    }
    reference = {
        "event": "reference",
        "pool_sha256": pool_sha,
        "preselection_sha256": pre_sha,
        "reference_pattern_index": 1,
        "reference_sources": nonempty_sources,
        "reference_pattern": [0, 1],
        "reference_value_cap": 1,
        "reference_terminal_incidence": 18,
        "reference_cofactor_width_budget": 32,
        "incidence_budget": 18,
    }
    selected_incidence = 16 if selected_cap == 0 else 18
    selected = {
        "event": "selected",
        "decision_mode": mode,
        "pool_sha256": pool_sha,
        "preselection_sha256": pre_sha,
        "selected_pattern_index": 1,
        "selected_sources": nonempty_sources,
        "selected_pattern": [0, 1],
        "selected_value_cap": selected_cap,
        "selected_terminal_incidence": selected_incidence,
        "incidence_budget": 18,
    }
    accounting = {
        "event": "selection_accounting",
        "cpu_seconds": timing + 1,
        "wall_seconds": timing + 1.1,
        "peak_memory_before_kb": 120,
        "peak_memory_after_kb": 140,
        "peak_memory_delta_kb": 20,
    }
    return "".join(_line(event) for event in (
        schema, probe, pool, *candidates, preselection, reference, selected,
        accounting,
    ))


class SelectorParserTest(unittest.TestCase):
    def test_literal_cpp_emitter_schema_and_hash_encoding_match_parser(self):
        repo = Path(__file__).resolve().parent.parent
        emitter = (
            repo / "src" / "search" / "symbolic" /
            "wbh_incidence_selector.cc"
        ).read_text(encoding="utf-8")
        levels = (
            repo / "src" / "search" / "symbolic" / "wbh_pdb_levels.cc"
        ).read_text(encoding="utf-8")
        self.assertIn("terminal-incidence-selector-trace/v3", emitter)
        self.assertIn('\\"version\\":3', emitter)
        self.assertIn("candidate-structural-lines-v3", emitter)
        self.assertEqual(S.SCHEMA_EVENT["version"], 3)
        self.assertEqual(
            S.SCHEMA_EVENT["preselection_hash_encoding"],
            "candidate-structural-lines-v3",
        )
        self.assertIn('<< "|raw_value_histogram="', levels)
        self.assertIn('<< ",\\\"raw_value_histogram\\\":"', levels)
        self.assertIn('preselection_canonical << "null"', levels)

    def test_fixed_cpp_numeric_constants_require_exact_json_integer_types(self):
        def schema_version(events):
            events[0]["version"] = 3.0

        def schema_cap(events):
            events[0]["value_cap_grid"][0] = 0.0

        def schema_bool_cap(events):
            events[0]["value_cap_grid"][0] = False

        def probe_layers(events):
            events[1]["target_layers"] = 16.0

        def pool_budget(events):
            events[2]["state_budget"] = 100000.0

        def reference_budget(events):
            reference = next(
                item for item in events if item.get("event") == "reference"
            )
            reference["reference_cofactor_width_budget"] = 32.0

        for mutation in (
            schema_version, schema_cap, schema_bool_cap, probe_layers,
            pool_budget, reference_budget,
        ):
            with self.subTest(mutation=mutation.__name__):
                events = [
                    json.loads(line) for line in _full_trace().splitlines()
                ]
                mutation(events)
                props = Props(
                    algorithm=S.GUIDED, coverage=1, planner_exit_code=0
                )
                S.parse_selector_trace(
                    "".join(_line(item) for item in events), props
                )
                self.assertFalse(
                    props["incidence_selector_trace_certified"]
                )

    def test_rehashed_signed_long_overflows_are_rejected(self):
        huge = 10**100

        incidence_events = [
            json.loads(line) for line in _full_trace().splitlines()
        ]
        for item in incidence_events:
            if (
                item.get("event") == "candidate"
                and item["pattern_index"] == 1
                and item["value_cap"] in (1, None)
            ):
                item["terminal_incidence_by_layer"] = [huge] + [1] * 15
                item["terminal_incidence"] = huge + 15
        reference = next(
            item for item in incidence_events
            if item.get("event") == "reference"
        )
        selected = next(
            item for item in incidence_events
            if item.get("event") == "selected"
        )
        reference["reference_terminal_incidence"] = huge + 15
        reference["incidence_budget"] = huge + 15
        selected["selected_terminal_incidence"] = huge + 15
        selected["incidence_budget"] = huge + 15
        _rehash_preselection(incidence_events)

        width_events = [
            json.loads(line) for line in _full_trace().splitlines()
        ]
        exact = next(
            item for item in width_events
            if item.get("event") == "candidate"
            and item["pattern_index"] == 1
            and item["value_cap"] is None
        )
        exact["cofactor_width"] = huge
        exact["width_upper_bound"] = huge + 2
        _rehash_preselection(width_events)

        for events in (incidence_events, width_events):
            with self.subTest(kind=(
                "incidence" if events is incidence_events else "width"
            )):
                props = Props(
                    algorithm=S.GUIDED, coverage=1, planner_exit_code=0
                )
                S.parse_selector_trace(
                    "".join(_line(item) for item in events), props
                )
                self.assertFalse(
                    props["incidence_selector_trace_certified"]
                )

    def test_frozen_cpp_candidate_comparator_order(self):
        base = {
            "initial_dead_end": False,
            "initial_h": 2,
            "finite_sum": 8,
            "finite_count": 4,
            "dead_count": 0,
            "abstract_states": 4,
            "cofactor_width": 8,
            "pattern": [2],
        }
        better = (
            {**base, "initial_dead_end": True, "initial_h": None},
            {**base, "initial_h": 3},
            {**base, "finite_sum": 9},
            {**base, "dead_count": 1},
            {**base, "cofactor_width": 7},
            {**base, "abstract_states": 3, "finite_count": 3,
             "finite_sum": 6},
            {**base, "pattern": [1]},
        )
        for candidate in better:
            with self.subTest(candidate=candidate):
                self.assertTrue(S._candidate_is_better(candidate, base))
        infinite_mean = {**base, "finite_sum": 0, "finite_count": 0}
        self.assertTrue(S._candidate_is_better(infinite_mean, base))

    def test_guided_and_matched_have_identical_structural_trace(self):
        guided = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        matched = Props(algorithm=S.MATCHED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace(
            _full_trace(mode="guided", selected_cap=None, timing=1.0), guided
        )
        S.parse_selector_trace(
            _full_trace(
                mode="matched_control", selected_cap=1, timing=9.0
            ),
            matched,
        )
        self.assertTrue(guided["incidence_selector_trace_certified"])
        self.assertTrue(matched["incidence_selector_trace_certified"])
        self.assertEqual(
            guided["incidence_selector_structural_trace"],
            matched["incidence_selector_structural_trace"],
        )
        self.assertEqual(
            guided["incidence_selector_structural_trace_sha256"],
            matched["incidence_selector_structural_trace_sha256"],
        )
        self.assertTrue(
            guided["incidence_selector_selected_differs_from_reference"]
        )
        self.assertEqual(
            guided["incidence_selector_probe_peak_memory_delta_kb"], 20
        )
        self.assertEqual(
            guided["incidence_selector_selection_peak_memory_delta_kb"], 20
        )
        self.assertFalse(
            matched["incidence_selector_selected_differs_from_reference"]
        )

    def test_wrong_guided_winner_is_rejected(self):
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace(
            _full_trace(mode="guided", selected_cap=0), props
        )
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "frozen C++ winner",
            props["incidence_selector_trace_validation_error"],
        )

    def test_wrong_reference_winner_is_rejected(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        reference = next(item for item in events if item["event"] == "reference")
        reference["reference_value_cap"] = 0
        reference["reference_terminal_incidence"] = 16
        reference["incidence_budget"] = 16
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "reference is not the frozen C++ winner",
            props["incidence_selector_trace_validation_error"],
        )

    def test_skipped_cap_is_rejected(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        cap_one = next(
            item for item in events
            if item["event"] == "candidate" and item["value_cap"] == 1
        )
        cap_one["value_cap"] = 2
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "cap prefix", props["incidence_selector_trace_validation_error"]
        )

    def test_truncated_prefix_inconsistent_with_exact_values_is_rejected(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        events = [
            item for item in events
            if not (
                item["event"] == "candidate" and item["value_cap"] == 1
            )
        ]
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "cap prefix", props["incidence_selector_trace_validation_error"]
        )

    def test_raw_max_requires_every_grid_cap_below_endpoint(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        for item in events:
            if item["event"] == "candidate" and item["pattern_index"] == 1:
                item["raw_max_finite_value"] = 100
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "cap prefix", props["incidence_selector_trace_validation_error"]
        )

    def test_boolean_pool_pattern_index_is_rejected(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        events[2]["patterns"][0]["pattern_index"] = False
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "pool pattern", props["incidence_selector_trace_validation_error"]
        )

    def test_duplicate_pool_pattern_is_rejected_after_rehashing(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        pool = next(item for item in events if item.get("event") == "pool")
        duplicate = dict(pool["patterns"][1])
        duplicate["pattern_index"] = 2
        pool["patterns"].append(duplicate)
        payload = "".join(
            "{}|sources={}|pattern={}|abstract_states={}|"
            "within_state_budget={}\n".format(
                item["pattern_index"], ",".join(item["sources"]),
                ",".join(map(str, item["pattern"])),
                item["abstract_states"], int(item["within_state_budget"]),
            )
            for item in pool["patterns"]
        )
        pool_sha = hashlib.sha256(payload.encode("ascii")).hexdigest()
        pool["pool_sha256"] = pool_sha
        candidates = [
            item for item in events if item.get("event") == "candidate"
        ]
        insert_at = next(
            index for index, item in enumerate(events)
            if item.get("event") == "preselection"
        )
        clones = [
            {**item, "pattern_index": 2}
            for item in candidates if item["pattern_index"] == 1
        ]
        events[insert_at:insert_at] = clones
        for item in events:
            if item.get("event") in {"preselection", "reference", "selected"}:
                item["pool_sha256"] = pool_sha
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "duplicate pattern",
            props["incidence_selector_trace_validation_error"],
        )

    def test_duplicate_generator_source_is_rejected_after_rehashing(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        pool = next(item for item in events if item.get("event") == "pool")
        pool["patterns"][0]["sources"].append("bdd_prefix")
        payload = "".join(
            "{}|sources={}|pattern={}|abstract_states={}|"
            "within_state_budget={}\n".format(
                item["pattern_index"], ",".join(item["sources"]),
                ",".join(map(str, item["pattern"])),
                item["abstract_states"], int(item["within_state_budget"]),
            )
            for item in pool["patterns"]
        )
        pool_sha = hashlib.sha256(payload.encode("ascii")).hexdigest()
        pool["pool_sha256"] = pool_sha
        for item in events:
            if item.get("event") == "candidate" and item["pattern_index"] == 0:
                item["sources"] = list(pool["patterns"][0]["sources"])
            if item.get("event") in {"preselection", "reference", "selected"}:
                item["pool_sha256"] = pool_sha
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "generator source",
            props["incidence_selector_trace_validation_error"],
        )

    def test_empty_candidate_is_bound_to_probe_bdd_nodes(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        empty = next(
            item for item in events
            if item.get("event") == "candidate" and item["pattern_index"] == 0
        )
        empty["terminal_incidence_by_layer"][0] = 2
        empty["terminal_incidence"] += 1
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "mandatory empty candidate",
            props["incidence_selector_trace_validation_error"],
        )

    def test_every_candidate_incidence_dominates_probe_frontier(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        capped = next(
            item for item in events
            if item.get("event") == "candidate"
            and item["pattern_index"] == 1
            and item["value_cap"] == 0
        )
        capped["terminal_incidence_by_layer"][0] = 0
        capped["terminal_incidence"] -= 1
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "below the probe frontier",
            props["incidence_selector_trace_validation_error"],
        )

    def test_mandatory_empty_pattern_identity_is_rejected_after_rehashing(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        pool = next(item for item in events if item.get("event") == "pool")
        pool["patterns"][0]["sources"] = ["bdd_prefix"]
        pool["patterns"][1]["sources"] = [
            "empty", "goal_prefix", "goal_fill", "cegar",
        ]
        payload = "".join(
            "{}|sources={}|pattern={}|abstract_states={}|"
            "within_state_budget={}\n".format(
                item["pattern_index"], ",".join(item["sources"]),
                ",".join(map(str, item["pattern"])),
                item["abstract_states"], int(item["within_state_budget"]),
            )
            for item in pool["patterns"]
        )
        pool_sha = hashlib.sha256(payload.encode("ascii")).hexdigest()
        pool["pool_sha256"] = pool_sha
        for item in events:
            if item.get("event") == "candidate":
                item["sources"] = pool["patterns"][item["pattern_index"]][
                    "sources"
                ]
            if item.get("event") in {"preselection", "reference", "selected"}:
                item["pool_sha256"] = pool_sha
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "mandatory empty pattern",
            props["incidence_selector_trace_validation_error"],
        )

    def test_candidate_width_cap_and_cross_cap_invariants_are_rejected(self):
        def mutate(field, value, *, cap=0, extra=None):
            events = [json.loads(line) for line in _full_trace().splitlines()]
            candidate = next(
                item for item in events
                if item["event"] == "candidate" and item["value_cap"] == cap
            )
            candidate[field] = value
            if extra is not None:
                extra(candidate)
            props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
            S.parse_selector_trace(
                "".join(_line(item) for item in events), props
            )
            self.assertFalse(props["incidence_selector_trace_certified"])

        mutate("cofactor_width", 0)
        mutate("width_upper_bound", 0, cap=1)
        mutate("finite_sum", 1, cap=0)
        mutate(
            "finite_count", 3, cap=1,
            extra=lambda item: item.update(dead_count=1),
        )

    def test_cross_cap_terminal_incidence_must_be_monotone(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        cap_one = next(
            item for item in events
            if item.get("event") == "candidate" and item["value_cap"] == 1
        )
        cap_one["terminal_incidence_by_layer"] = [5, 6] + [1] * 14
        cap_one["terminal_incidence"] = 25
        cap_one["incidence_feasible"] = False
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "terminal incidence is not monotone",
            props["incidence_selector_trace_validation_error"],
        )

    def test_cross_cap_widths_must_be_monotone_after_rehashing(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        cap_one = next(
            item for item in events
            if item.get("event") == "candidate" and item["value_cap"] == 1
        )
        cap_one["cofactor_width"] = 50
        cap_one["width_upper_bound"] = 51
        cap_one["reference_feasible"] = False
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "widths are not monotone",
            props["incidence_selector_trace_validation_error"],
        )

    def test_rehashed_widths_must_match_reconstructed_terminal_count(self):
        mutations = (
            # The exact histogram has three terminals, so W >= 3.
            {"cofactor_width": 2, "width_upper_bound": 4,
             "reference_feasible": True},
            # With W=40 and three terminals, A+T >= W+T-1 = 42.
            {"width_upper_bound": 41},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                events = [
                    json.loads(line) for line in _full_trace().splitlines()
                ]
                exact = next(
                    item for item in events
                    if item.get("event") == "candidate"
                    and item["pattern_index"] == 1
                    and item["value_cap"] is None
                )
                exact.update(mutation)
                _rehash_preselection(events)
                props = Props(
                    algorithm=S.GUIDED, coverage=1, planner_exit_code=0
                )
                S.parse_selector_trace(
                    "".join(_line(item) for item in events), props
                )
                self.assertFalse(
                    props["incidence_selector_trace_certified"]
                )
                self.assertIn(
                    "ADD widths are impossible for its terminals",
                    props["incidence_selector_trace_validation_error"],
                )

    def test_rehashed_constant_transform_has_constant_add_structure(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        cap_zero = next(
            item for item in events
            if item.get("event") == "candidate"
            and item["pattern_index"] == 1
            and item["value_cap"] == 0
        )
        cap_zero.update({
            "cofactor_width": 2,
            "width_upper_bound": 2,
            "terminal_incidence_by_layer": [2, 2] + [1] * 14,
            "terminal_incidence": 18,
        })
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "constant candidate ADD structure changed",
            props["incidence_selector_trace_validation_error"],
        )

    def test_finite_sums_must_materialize_raw_max_and_initial_value(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        for item in events:
            if item.get("event") == "candidate" and item["value_cap"] == 1:
                item["finite_sum"] = 0
            elif (
                item.get("event") == "candidate"
                and item["pattern_index"] == 1
                and item["value_cap"] is None
            ):
                item["finite_sum"] = 1
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "cap prefix", props["incidence_selector_trace_validation_error"]
        )

    def test_impossible_capped_sum_is_rejected_after_rehashing(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        cap_one = next(
            item for item in events
            if item.get("event") == "candidate"
            and item["pattern_index"] == 1
            and item["value_cap"] == 1
        )
        # Histogram {0: 16, 1: 16, 2: 32} forces capped sum 48.
        cap_one["finite_sum"] = 47
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "reconstruct from raw histogram",
            props["incidence_selector_trace_validation_error"],
        )

    def test_add_widths_bind_reconstructed_terminal_count(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        cap_one = next(
            item for item in events
            if item.get("event") == "candidate"
            and item["pattern_index"] == 1
            and item["value_cap"] == 1
        )
        # Two transformed terminals require U >= W + T - 1 == 3.
        cap_one["width_upper_bound"] = 2
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "ADD widths are impossible",
            props["incidence_selector_trace_validation_error"],
        )

    def test_all_dead_candidate_requires_zero_finite_sum(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        exact = next(
            item for item in events
            if item.get("event") == "candidate"
            and item["pattern_index"] == 1
            and item["value_cap"] is None
        )
        events = [
            item for item in events
            if item.get("event") != "candidate" or item is exact
        ]
        exact.update({
            "initial_dead_end": True,
            "initial_h": None,
            "finite_sum": 99,
            "finite_count": 0,
            "dead_count": 4,
            "cofactor_width": 1,
            "width_upper_bound": 1,
            "raw_max_finite_value": 0,
            "reference_feasible": True,
            "retained_for_pattern": True,
        })
        reference = next(
            item for item in events if item.get("event") == "reference"
        )
        reference["reference_value_cap"] = None
        selected = next(
            item for item in events if item.get("event") == "selected"
        )
        selected["selected_value_cap"] = None
        _rehash_preselection(events)
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "candidate identity or scalar changed",
            props["incidence_selector_trace_validation_error"],
        )

    def test_short_probe_is_certified_only_with_exit_34(self):
        probe = {
            "event": "probe",
            "target_layers": 16,
            "completed_layers": 3,
            "attempts": 3,
            "complete": False,
            "g_values": [0, 1, 2],
            "bdd_nodes": [1, 2, 3],
            "cpu_seconds": 1.0,
            "wall_seconds": 1.1,
            "peak_memory_before_kb": 100,
            "peak_memory_after_kb": 100,
            "peak_memory_delta_kb": 0,
        }
        content = _line(S.SCHEMA_EVENT) + _line(probe)
        good = Props(algorithm=S.GUIDED, coverage=0, planner_exit_code=34)
        S.parse_selector_trace(content, good)
        self.assertEqual(
            good["incidence_selector_trace_status"], "short_probe"
        )
        self.assertTrue(good["incidence_selector_trace_certified"])
        self.assertEqual(
            good["incidence_selector_probe_peak_memory_before_kb"], 100
        )
        self.assertNotIn(
            "incidence_selector_selection_cpu_seconds", good
        )
        bad = Props(algorithm=S.GUIDED, coverage=0, planner_exit_code=23)
        S.parse_selector_trace(content, bad)
        self.assertEqual(bad["incidence_selector_trace_status"], "invalid")
        self.assertTrue(bad["unexplained_errors"])
        for coverage, exit_code in ((False, 34), (0.0, 34), (0, 34.0)):
            with self.subTest(coverage=coverage, exit_code=exit_code):
                malformed = Props(
                    algorithm=S.GUIDED,
                    coverage=coverage,
                    planner_exit_code=exit_code,
                )
                S.parse_selector_trace(content, malformed)
                self.assertFalse(
                    malformed["incidence_selector_trace_certified"]
                )

    def test_complete_trace_with_exit_34_is_rejected(self):
        props = Props(algorithm=S.GUIDED, coverage=0, planner_exit_code=34)
        S.parse_selector_trace(_full_trace(), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn(
            "complete selector trace is paired with exit code 34",
            props["incidence_selector_trace_validation_error"],
        )

    def test_hash_tampering_is_rejected(self):
        events = [json.loads(line) for line in _full_trace().splitlines()]
        events[2]["pool_sha256"] = "0" * 64
        props = Props(algorithm=S.GUIDED, coverage=1, planner_exit_code=0)
        S.parse_selector_trace("".join(_line(item) for item in events), props)
        self.assertFalse(props["incidence_selector_trace_certified"])
        self.assertIn("pool SHA-256", props["incidence_selector_trace_validation_error"])

    def test_nonselector_must_not_produce_trace(self):
        absent = Props(algorithm="blind_fw", coverage=0, planner_exit_code=23)
        S.parse_selector_trace("", absent)
        self.assertEqual(
            absent["incidence_selector_trace_status"], "not_applicable"
        )
        unexpected = Props(algorithm="blind_fw", coverage=0, planner_exit_code=23)
        S.parse_selector_trace(_line(S.SCHEMA_EVENT), unexpected)
        self.assertFalse(unexpected["incidence_selector_trace_certified"])


if __name__ == "__main__":
    unittest.main()
