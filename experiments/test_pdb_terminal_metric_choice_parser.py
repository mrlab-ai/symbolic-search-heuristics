#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import json
import unittest
from unittest import mock

import pdb_terminal_metric_choice_parser as T
import pdb_terminal_metric_choice_protocol as P


def _identity(prefix, candidate):
    return {
        prefix + key: candidate[key] for key in (
            "pattern_index", "sources", "pattern", "value_cap",
            "terminal_incidence", "masked_joint",
        )
    }


def valid_events(mode=P.INCIDENCE_MODE):
    variable = {
        "event": "variable_order", "manager_variables": 1, "state_bits": 1,
        "cudd_indices": [0], "cudd_levels": [0], "fd_variables": [0],
        "fd_bit_positions": [0],
    }
    probe = {
        "event": "probe", "target_layers": 16, "completed_layers": 16,
        "attempts": 16, "complete": True, "g_values": list(range(16)),
        "bdd_nodes": [1] * 16, "cpu_seconds": 0.2, "wall_seconds": 0.3,
        "peak_memory_before_kb": 100, "peak_memory_after_kb": 103,
        "peak_memory_delta_kb": 3,
    }
    profiles = [[1, 1] for _ in range(16)]
    state_text = "".join(
        "{}|g={}|bdd_nodes=1|cofactor_counts=1,1\n".format(layer, layer)
        for layer in range(16)
    )
    state_sha = hashlib.sha256(state_text.encode("ascii")).hexdigest()
    state_event = {
        "event": "probe_state_profiles", "state_profiles_sha256": state_sha,
        "cofactor_counts_by_layer": profiles,
    }
    patterns = [
        {"pattern_index": 0, "sources": ["empty"], "pattern": [],
         "abstract_states": 1, "within_state_budget": True},
        {"pattern_index": 1, "sources": ["bdd_prefix"], "pattern": [0],
         "abstract_states": 100001, "within_state_budget": False},
        {"pattern_index": 2, "sources": ["goal_prefix"], "pattern": [1],
         "abstract_states": 100001, "within_state_budget": False},
        {"pattern_index": 3, "sources": ["goal_fill"], "pattern": [2],
         "abstract_states": 100001, "within_state_budget": False},
        {"pattern_index": 4, "sources": ["cegar"], "pattern": [3],
         "abstract_states": 100001, "within_state_budget": False},
    ]
    pool_text = "".join(
        "{}|sources={}|pattern={}|abstract_states={}|within_state_budget={}\n".format(
            row["pattern_index"], ",".join(row["sources"]),
            ",".join(map(str, row["pattern"])), row["abstract_states"],
            int(row["within_state_budget"]),
        ) for row in patterns
    )
    pool_sha = hashlib.sha256(pool_text.encode("ascii")).hexdigest()
    pool = {
        "event": "pool", "protocol": P.DUAL_TRACE_PROTOCOL,
        "state_budget": 100000, "pool_sha256": pool_sha,
        "patterns": patterns,
    }
    candidate = {
        "event": "candidate", "protocol": P.DUAL_TRACE_PROTOCOL,
        "score_version": T.SCORE_VERSION, "pattern_index": 0,
        "sources": ["empty"], "pattern": [], "abstract_states": 1,
        "value_cap": None, "initial_dead_end": False, "initial_h": 0,
        "finite_sum": 0, "finite_count": 1, "dead_count": 0,
        "cofactor_width": 1, "width_upper_bound": 1,
        "raw_max_finite_value": 0, "raw_value_histogram": "AQEB",
        "heuristic_cofactor_counts": [1, 1],
        "dead_end_value": -1,
        "terminal_incidence_by_layer": [1] * 16, "terminal_incidence": 16,
        "masked_add_nodes_by_layer": [1] * 16,
        "active_finite_values_by_layer": [[0] for _ in range(16)],
        "dead_end_active_by_layer": [False] * 16,
        "active_terminal_count_by_layer": [1] * 16,
        "joint_cofactor_counts_by_layer": [[1, 1] for _ in range(16)],
        "joint_cofactor_sum_by_layer": [1] * 16,
        "masked_joint_by_layer": [1] * 16, "masked_joint": 16,
        "incidence_node_kinds_by_layer": [[0, 2] for _ in range(16)],
        "incidence_then_children_by_layer": [[1, -1] for _ in range(16)],
        "incidence_else_children_by_layer": [[1, -1] for _ in range(16)],
        "incidence_terminal_values_by_layer": [[-1, 0] for _ in range(16)],
        "reference_feasible": True, "incidence_feasible": True,
        "masked_joint_feasible": True,
        "incidence_retained_for_pattern": True,
        "masked_joint_retained_for_pattern": True,
    }
    incidence_sha = hashlib.sha256(
        T._incidence_projection_line(candidate).encode("ascii")
    ).hexdigest()
    pre_sha = hashlib.sha256(T._dual_line(candidate).encode("ascii")).hexdigest()
    hashes = {
        "pool_sha256": pool_sha, "state_profiles_sha256": state_sha,
        "incidence_projection_sha256": incidence_sha,
        "preselection_sha256": pre_sha,
    }
    preselection = {
        "event": "preselection", **hashes, "candidate_count": 1,
    }
    reference = {
        "event": "reference", **hashes, **_identity("reference_", candidate),
        "reference_cofactor_width_budget": 32, "incidence_budget": 16,
        "masked_joint_budget": 16,
    }
    winners = {
        "event": "metric_winners", **hashes, "incidence_budget": 16,
        "masked_joint_budget": 16,
        **_identity("incidence_winner_", candidate),
        **_identity("masked_joint_winner_", candidate),
    }
    decision = {
        P.INCIDENCE_MODE: "incidence_guided",
        P.MJ_MODE: "masked_joint_guided",
        P.MATCHED_MODE: "matched_control",
    }[mode]
    selected = {
        "event": "selected", "decision_mode": decision, **hashes,
        **_identity("selected_", candidate), "incidence_budget": 16,
        "masked_joint_budget": 16,
    }
    accounting = {
        "event": "selection_accounting", "candidate_count": 1,
        "probe_state_profile_count": 16,
        "probe_state_profile_cut_entries": 32,
        "terminal_incidence_layer_measurements": 16,
        "joint_profile_layer_measurements": 16,
        "joint_profile_cut_entries": 32,
        "joint_summed_cut_entries": 16,
        "cpu_seconds": 0.4, "wall_seconds": 0.5,
        "peak_memory_before_kb": 103, "peak_memory_after_kb": 108,
        "peak_memory_delta_kb": 5,
    }
    return [
        copy.deepcopy(T.SCHEMA_EVENT), variable, probe, state_event, pool,
        candidate, preselection, reference, winners, selected, accounting,
    ]


def encode(events):
    return "".join(json.dumps(row, separators=(",", ":")) + "\n" for row in events)


def differing_events(mode=P.INCIDENCE_MODE):
    events = valid_events(mode)
    variable, probe, state, pool = events[1:5]
    variable.update({
        "manager_variables": 2, "state_bits": 2, "cudd_indices": [0, 1],
        "cudd_levels": [0, 1], "fd_variables": [0, 1],
        "fd_bit_positions": [0, 0],
    })
    profiles = [[1, 1, 1] for _ in range(16)]
    state["cofactor_counts_by_layer"] = profiles
    state["state_profiles_sha256"] = hashlib.sha256("".join(
        "{}|g={}|bdd_nodes=1|cofactor_counts=1,1,1\n".format(layer, layer)
        for layer in range(16)
    ).encode("ascii")).hexdigest()
    pool["patterns"][1].update({"abstract_states": 2, "within_state_budget": True})
    pool["pool_sha256"] = hashlib.sha256("".join(
        "{}|sources={}|pattern={}|abstract_states={}|within_state_budget={}\n".format(
            row["pattern_index"], ",".join(row["sources"]),
            ",".join(map(str, row["pattern"])), row["abstract_states"],
            int(row["within_state_budget"]),
        ) for row in pool["patterns"]
    ).encode("ascii")).hexdigest()
    empty = events[5]
    empty.update({
        "heuristic_cofactor_counts": [1, 1, 1],
        "joint_cofactor_counts_by_layer": profiles,
        "joint_cofactor_sum_by_layer": [2] * 16,
        "masked_joint_by_layer": [2] * 16, "masked_joint": 32,
    })
    cap0 = copy.deepcopy(empty)
    cap0.update({
        "pattern_index": 1, "sources": ["bdd_prefix"], "pattern": [0],
        "abstract_states": 2, "value_cap": 0, "finite_count": 2,
        "raw_max_finite_value": 1, "raw_value_histogram": None,
        "incidence_retained_for_pattern": False,
    })
    exact = copy.deepcopy(cap0)
    exact.update({
        "value_cap": None, "initial_h": 1, "finite_sum": 1,
        "cofactor_width": 33, "width_upper_bound": 34,
        "raw_value_histogram": "AgEBAQE",
        "heuristic_cofactor_counts": [1, 33, 2],
        "active_finite_values_by_layer": [[1] for _ in range(16)],
        "joint_cofactor_counts_by_layer": [[1, 33, 2] for _ in range(16)],
        "joint_cofactor_sum_by_layer": [34] * 16,
        "masked_joint_by_layer": [34] * 16, "masked_joint": 544,
        "reference_feasible": False, "masked_joint_feasible": False,
        "masked_joint_retained_for_pattern": False,
        "incidence_retained_for_pattern": True,
        "incidence_terminal_values_by_layer": [[-1, 1] for _ in range(16)],
    })
    candidates = [empty, cap0, exact]
    incidence_sha = hashlib.sha256("".join(
        T._incidence_projection_line(row) for row in candidates
    ).encode("ascii")).hexdigest()
    pre_sha = hashlib.sha256("".join(
        T._dual_line(row) for row in candidates
    ).encode("ascii")).hexdigest()
    hashes = {
        "pool_sha256": pool["pool_sha256"],
        "state_profiles_sha256": state["state_profiles_sha256"],
        "incidence_projection_sha256": incidence_sha,
        "preselection_sha256": pre_sha,
    }
    preselection = {"event": "preselection", **hashes, "candidate_count": 3}
    reference = {
        "event": "reference", **hashes, **_identity("reference_", empty),
        "reference_cofactor_width_budget": 32, "incidence_budget": 16,
        "masked_joint_budget": 32,
    }
    winners = {
        "event": "metric_winners", **hashes, "incidence_budget": 16,
        "masked_joint_budget": 32, **_identity("incidence_winner_", exact),
        **_identity("masked_joint_winner_", empty),
    }
    chosen = {
        P.INCIDENCE_MODE: exact, P.MJ_MODE: empty, P.MATCHED_MODE: empty,
    }[mode]
    decision = {
        P.INCIDENCE_MODE: "incidence_guided",
        P.MJ_MODE: "masked_joint_guided",
        P.MATCHED_MODE: "matched_control",
    }[mode]
    selected = {
        "event": "selected", "decision_mode": decision, **hashes,
        **_identity("selected_", chosen), "incidence_budget": 16,
        "masked_joint_budget": 32,
    }
    accounting = {
        "event": "selection_accounting", "candidate_count": 3,
        "probe_state_profile_count": 16,
        "probe_state_profile_cut_entries": 48,
        "terminal_incidence_layer_measurements": 48,
        "joint_profile_layer_measurements": 48,
        "joint_profile_cut_entries": 144, "joint_summed_cut_entries": 96,
        "cpu_seconds": 0.4, "wall_seconds": 0.5,
        "peak_memory_before_kb": 103, "peak_memory_after_kb": 108,
        "peak_memory_delta_kb": 5,
    }
    return [
        events[0], variable, probe, state, pool, *candidates, preselection,
        reference, winners, selected, accounting,
    ]


def same_pool_events(mode=P.INCIDENCE_MODE):
    events = differing_events(mode)
    empty, cap0, exact = events[5:8]
    exact.update({
        "terminal_incidence_by_layer": [2] * 16,
        "terminal_incidence": 32, "masked_add_nodes_by_layer": [2] * 16,
        "incidence_node_kinds_by_layer": [[0, 0, 2] for _ in range(16)],
        "incidence_then_children_by_layer": [[1, 2, -1] for _ in range(16)],
        "incidence_else_children_by_layer": [[1, 2, -1] for _ in range(16)],
        "incidence_terminal_values_by_layer": [[-1, -1, 1] for _ in range(16)],
        "incidence_feasible": False, "incidence_retained_for_pattern": False,
    })
    cap0["incidence_retained_for_pattern"] = True
    candidates = [empty, cap0, exact]
    incidence_sha = hashlib.sha256("".join(
        T._incidence_projection_line(row) for row in candidates
    ).encode("ascii")).hexdigest()
    pre_sha = hashlib.sha256("".join(
        T._dual_line(row) for row in candidates
    ).encode("ascii")).hexdigest()
    hashes = {
        "pool_sha256": events[4]["pool_sha256"],
        "state_profiles_sha256": events[3]["state_profiles_sha256"],
        "incidence_projection_sha256": incidence_sha,
        "preselection_sha256": pre_sha,
    }
    events[8] = {"event": "preselection", **hashes, "candidate_count": 3}
    events[9] = {
        "event": "reference", **hashes, **_identity("reference_", empty),
        "reference_cofactor_width_budget": 32, "incidence_budget": 16,
        "masked_joint_budget": 32,
    }
    events[10] = {
        "event": "metric_winners", **hashes, "incidence_budget": 16,
        "masked_joint_budget": 32, **_identity("incidence_winner_", empty),
        **_identity("masked_joint_winner_", empty),
    }
    decision = {
        P.INCIDENCE_MODE: "incidence_guided",
        P.MJ_MODE: "masked_joint_guided",
        P.MATCHED_MODE: "matched_control",
    }[mode]
    events[11] = {
        "event": "selected", "decision_mode": decision, **hashes,
        **_identity("selected_", empty), "incidence_budget": 16,
        "masked_joint_budget": 32,
    }
    return events


class ParserTest(unittest.TestCase):
    def test_complete_all_modes_same_structure(self):
        certificates = [
            T.certify_trace(encode(valid_events(mode)), mode) for mode in P.MODES
        ]
        self.assertTrue(all(row["status"] == "complete" for row in certificates))
        self.assertEqual(
            {row["structural_trace_sha256"] for row in certificates},
            {certificates[0]["structural_trace_sha256"]},
        )

    def test_replays_terminal_cut_and_mj_formula(self):
        events = valid_events()
        events[5]["joint_cofactor_sum_by_layer"][0] = 2
        with self.assertRaisesRegex(T.TraceError, "I/mJ layer formula"):
            T.certify_trace(encode(events), P.INCIDENCE_MODE)

    def test_replays_raw_terminal_ancestor_incidence(self):
        events = valid_events()
        events[5]["incidence_then_children_by_layer"][0] = [0, -1]
        with self.assertRaisesRegex(T.TraceError, "incidence DAG"):
            T.certify_trace(encode(events), P.INCIDENCE_MODE)

    def test_raw_certificate_does_not_change_incidence_v3_projection(self):
        candidate = valid_events()[5]
        before = T._incidence_projection_line(candidate)
        candidate["incidence_node_kinds_by_layer"][0].append(1)
        self.assertEqual(T._incidence_projection_line(candidate), before)

    def test_rejects_semantic_dead_end_mutation(self):
        events = valid_events()
        events[5]["dead_end_active_by_layer"][0] = True
        with self.assertRaises(T.TraceError):
            T.certify_trace(encode(events), P.INCIDENCE_MODE)

    def test_rejects_hash_pointer_work_and_extra_field(self):
        mutations = []
        events = valid_events()
        events[6]["preselection_sha256"] = "0" * 64
        mutations.append(events)
        events = valid_events()
        events[9]["selected_pattern_index"] = 7
        mutations.append(events)
        events = valid_events()
        events[10]["joint_summed_cut_entries"] = 17
        mutations.append(events)
        events = valid_events()
        events[7]["unexpected"] = 1
        mutations.append(events)
        for events in mutations:
            with self.subTest(event=events[-1].get("event")):
                with self.assertRaises(T.TraceError):
                    T.certify_trace(encode(events), P.INCIDENCE_MODE)

    def test_short_probe_has_no_trailing_fallback(self):
        events = valid_events()[:3]
        events[2].update({
            "completed_layers": 8, "attempts": 8, "complete": False,
            "g_values": list(range(8)), "bdd_nodes": [1] * 8,
        })
        certificate = T.certify_trace(encode(events), P.INCIDENCE_MODE)
        self.assertEqual(certificate["status"], "short_probe")
        events.append({"event": "fallback"})
        with self.assertRaisesRegex(T.TraceError, "trailing"):
            T.certify_trace(encode(events), P.INCIDENCE_MODE)

    def test_duplicate_keys_fail_closed(self):
        content = encode(valid_events()).replace(
            '{"event":"schema"', '{"event":"schema","event":"schema"', 1
        )
        with self.assertRaisesRegex(T.TraceError, "duplicate"):
            T.certify_trace(content, P.INCIDENCE_MODE)

    def test_malformed_scalar_is_translated_fail_closed(self):
        events = valid_events()
        events[5]["masked_joint"] = {"not": "an integer"}
        with self.assertRaisesRegex(T.TraceError, "malformed value"):
            T.certify_trace(encode(events), P.INCIDENCE_MODE)

    def test_every_integer_class_rejects_float_and_bool_aliases(self):
        mutations = (
            ("manager count", 1, lambda rows, value: rows[1].__setitem__(
                "manager_variables", value)),
            ("probe target", 16, lambda rows, value: rows[2].__setitem__(
                "target_layers", value)),
            ("pool state budget", 100000, lambda rows, value: rows[4].__setitem__(
                "state_budget", value)),
            ("pool pattern id", 0, lambda rows, value: rows[4]["patterns"][0].__setitem__(
                "pattern_index", value)),
            ("candidate pattern id", 0, lambda rows, value: rows[5].__setitem__(
                "pattern_index", value)),
            ("candidate state count", 1, lambda rows, value: rows[5].__setitem__(
                "abstract_states", value)),
            ("candidate scalar", 1, lambda rows, value: rows[5].__setitem__(
                "finite_count", value)),
            ("candidate layer count", 1, lambda rows, value: rows[5][
                "terminal_incidence_by_layer"].__setitem__(0, value)),
            ("inner sentinel", -1, lambda rows, value: rows[5][
                "incidence_terminal_values_by_layer"][0].__setitem__(0, value)),
            ("terminal child sentinel", -1, lambda rows, value: rows[5][
                "incidence_then_children_by_layer"][0].__setitem__(1, value)),
            ("candidate count", 1, lambda rows, value: rows[6].__setitem__(
                "candidate_count", value)),
            ("K32 budget", 32, lambda rows, value: rows[7].__setitem__(
                "reference_cofactor_width_budget", value)),
            ("incidence budget", 16, lambda rows, value: rows[7].__setitem__(
                "incidence_budget", value)),
            ("winner budget", 16, lambda rows, value: rows[8].__setitem__(
                "masked_joint_budget", value)),
            ("selected budget", 16, lambda rows, value: rows[9].__setitem__(
                "incidence_budget", value)),
            ("winner identity id", 0, lambda rows, value: rows[8].__setitem__(
                "incidence_winner_pattern_index", value)),
            ("accounting count", 1, lambda rows, value: rows[10].__setitem__(
                "candidate_count", value)),
        )
        for label, expected, mutate in mutations:
            for value in (float(expected), bool(expected)):
                with self.subTest(field=label, value=repr(value)):
                    events = valid_events()
                    mutate(events, value)
                    with self.assertRaises(T.TraceError):
                        T.certify_trace(encode(events), P.INCIDENCE_MODE)

    def test_deep_raw_dag_is_iterative(self):
        candidate = valid_events()[5]
        inner_count = 1601
        candidate["incidence_node_kinds_by_layer"][0] = (
            [0] * inner_count + [2]
        )
        candidate["incidence_then_children_by_layer"][0] = (
            list(range(1, inner_count + 1)) + [-1]
        )
        candidate["incidence_else_children_by_layer"][0] = (
            list(range(1, inner_count + 1)) + [-1]
        )
        candidate["incidence_terminal_values_by_layer"][0] = (
            [-1] * inner_count + [0]
        )
        candidate["terminal_incidence_by_layer"][0] = inner_count
        candidate["masked_add_nodes_by_layer"][0] = inner_count
        T._replay_incidence_layer(candidate, 0)

    def test_raw_dag_cycle_unreachable_and_work_overflow_fail_closed(self):
        cycle = valid_events()[5]
        cycle["incidence_node_kinds_by_layer"][0] = [0]
        cycle["incidence_then_children_by_layer"][0] = [0]
        cycle["incidence_else_children_by_layer"][0] = [0]
        cycle["incidence_terminal_values_by_layer"][0] = [-1]
        with self.assertRaisesRegex(T.TraceError, "cycle"):
            T._replay_incidence_layer(cycle, 0)

        unreachable = valid_events()[5]
        for field, value in (
            ("incidence_node_kinds_by_layer", 2),
            ("incidence_then_children_by_layer", -1),
            ("incidence_else_children_by_layer", -1),
            ("incidence_terminal_values_by_layer", 7),
        ):
            unreachable[field][0].append(value)
        with self.assertRaisesRegex(T.TraceError, "reachability"):
            T._replay_incidence_layer(unreachable, 0)

        bounded = valid_events()[5]
        with mock.patch.object(T, "MAX_RAW_DAG_TRAVERSAL_STEPS", 1):
            with self.assertRaisesRegex(T.TraceError, "traversal is too large"):
                T._replay_incidence_layer(bounded, 0)

    def test_integer_overflow_is_rejected(self):
        events = valid_events()
        events[5]["terminal_incidence"] = T.LONG_MAX + 1
        with self.assertRaises(T.TraceError):
            T.certify_trace(encode(events), P.INCIDENCE_MODE)


if __name__ == "__main__":
    unittest.main()
