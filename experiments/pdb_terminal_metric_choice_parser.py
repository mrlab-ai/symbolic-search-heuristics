#!/usr/bin/env python3
"""Fail-closed parser for the dual I/mJ selector trace.

The parser treats the trace as an untrusted certificate.  It independently
reconstructs the incidence-v3 projection, joint metric, two budgets, K32
reference, both metric winners, per-pattern retained caps, work counts, and all
hashes before exposing a certified record to the campaign analyzer.
"""

from __future__ import annotations

import base64
import binascii
import copy
import hashlib
import json
import math
import re

import pdb_terminal_metric_choice_protocol as P


class TraceError(RuntimeError):
    pass


TRACE_SCHEMA = P.DUAL_TRACE_SCHEMA
TRACE_PROTOCOL = P.DUAL_TRACE_PROTOCOL
SCORE_VERSION = (
    "strongest_metric_feasible_cap_then_"
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
INT_MAX = 2**31 - 1
LONG_MAX = 2**63 - 1
MAX_RAW_DAG_NODES = 1_000_000
MAX_RAW_DAG_TRAVERSAL_STEPS = 10_000_000
CAP_GRID = list(P.VALUE_CAP_GRID)

SCHEMA_EVENT = {
    "event": "schema",
    "schema": TRACE_SCHEMA,
    "version": 2,
    "probe_layers": 16,
    "reference_cofactor_width_budget": 32,
    "candidate_sources": list(P.CANDIDATE_SOURCES),
    "value_cap_grid": [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, "exact"],
    "cut_convention": (
        "unprimed_state_bits_in_cudd_level_order_including_terminal_cut_"
        "but_excluding_terminal_from_sums"
    ),
    "joint_residual_identity": (
        "cooccurring_signed_bdd_and_regular_add_pointer_pair"
    ),
    "active_terminal_semantics": (
        "finite_values_plus_semantic_dead_end_excluding_fresh_bottom"
    ),
    "incidence_budget": (
        "sum-first-16-completed-blind-layers-of-reference-v1"
    ),
    "masked_joint_budget": (
        "sum-active-terminal-count-times-joint-cofactor-sum-excluding-"
        "terminal-cut-of-reference-v1"
    ),
    "pool_hash_encoding": "sources-pattern-states-feasible-lines-v1",
    "state_profile_hash_encoding": (
        "layer-g-bdd-nodes-cofactor-counts-lines-v1"
    ),
    "preselection_hash_encoding": "dual-candidate-structural-lines-v2",
    "incidence_raw_certificate": (
        "breadth-first-regular-masked-add-dag-node-kinds-children-"
        "terminal-values-v1"
    ),
    "incidence_projection_hash_encoding": "candidate-structural-lines-v3",
    "required_invariants": [
        "exactly-16-completed-probe-layers",
        "raw-terminal-ancestor-incidence-replay",
        "joint-projection-and-product-bounds",
        "terminal-cut-excluded-from-joint-cofactor-sums",
        "semantic-dead-end-agrees-with-numeric-sentinel",
        "cap-refinement-monotonicity",
        "common-K32-reference-feasible-under-both-derived-budgets",
        "identical-I-and-mJ-measurement-work-in-all-three-modes",
    ],
}

VARIABLE_KEYS = {
    "event", "manager_variables", "state_bits", "cudd_indices",
    "cudd_levels", "fd_variables", "fd_bit_positions",
}
PROBE_KEYS = {
    "event", "target_layers", "completed_layers", "attempts", "complete",
    "g_values", "bdd_nodes", "cpu_seconds", "wall_seconds",
    "peak_memory_before_kb", "peak_memory_after_kb", "peak_memory_delta_kb",
}
CANDIDATE_KEYS = {
    "event", "protocol", "score_version", "pattern_index", "sources",
    "pattern", "abstract_states", "value_cap", "initial_dead_end",
    "initial_h", "finite_sum", "finite_count", "dead_count",
    "cofactor_width", "width_upper_bound", "raw_max_finite_value",
    "raw_value_histogram", "heuristic_cofactor_counts",
    "dead_end_value",
    "terminal_incidence_by_layer", "terminal_incidence",
    "masked_add_nodes_by_layer", "active_finite_values_by_layer",
    "dead_end_active_by_layer", "active_terminal_count_by_layer",
    "joint_cofactor_counts_by_layer", "joint_cofactor_sum_by_layer",
    "masked_joint_by_layer", "masked_joint", "reference_feasible",
    "incidence_node_kinds_by_layer", "incidence_then_children_by_layer",
    "incidence_else_children_by_layer", "incidence_terminal_values_by_layer",
    "incidence_feasible", "masked_joint_feasible",
    "incidence_retained_for_pattern", "masked_joint_retained_for_pattern",
}


def _same_json(actual, expected) -> bool:
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            _same_json(actual[key], value) for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same_json(left, right) for left, right in zip(actual, expected)
        )
    return actual == expected


def _duplicate_safe_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise TraceError("dual selector JSON object has a duplicate key")
        value[key] = item
    return value


def _load_events(content: str) -> list[dict]:
    if not isinstance(content, str) or not content:
        return []
    if not content.endswith("\n") or "\r" in content:
        raise TraceError("dual selector trace is not newline-terminated JSONL")
    events = []
    for number, line in enumerate(content.splitlines(), 1):
        if not line:
            raise TraceError("dual selector trace contains an empty line")
        try:
            event = json.loads(line, object_pairs_hook=_duplicate_safe_object)
        except TraceError:
            raise
        except json.JSONDecodeError as err:
            raise TraceError(
                "dual selector trace line {} is invalid JSON".format(number)
            ) from err
        if not isinstance(event, dict):
            raise TraceError("dual selector trace event is not an object")
        events.append(event)
    return events


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _is_sha256(value) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _finite_nonnegative(value, label: str) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise TraceError("{} is not finite and nonnegative".format(label))


def _int_list(value, label: str, *, length=None, maximum=LONG_MAX) -> None:
    if not isinstance(value, list) or any(
        type(item) is not int or not 0 <= item <= maximum for item in value
    ) or (length is not None and len(value) != length):
        raise TraceError("{} is not the required nonnegative integer list".format(label))


def _exact_int(value, label: str, *, minimum=0, maximum=LONG_MAX) -> None:
    if type(value) is not int or not minimum <= value <= maximum:
        raise TraceError("{} is not the required integer".format(label))


def _memory_fields(event: dict, label: str) -> dict:
    for field in ("cpu_seconds", "wall_seconds"):
        _finite_nonnegative(event[field], "{} {}".format(label, field))
    for field in (
        "peak_memory_before_kb", "peak_memory_after_kb",
        "peak_memory_delta_kb",
    ):
        if type(event[field]) is not int or not 0 <= event[field] <= INT_MAX:
            raise TraceError("{} memory is invalid".format(label))
    if event["peak_memory_delta_kb"] != max(
        0, event["peak_memory_after_kb"] - event["peak_memory_before_kb"]
    ):
        raise TraceError("{} memory delta changed".format(label))
    return {
        key: event[key] for key in (
            "cpu_seconds", "wall_seconds", "peak_memory_before_kb",
            "peak_memory_after_kb", "peak_memory_delta_kb",
        )
    }


def _validate_variable_order(event: dict) -> dict:
    if set(event) != VARIABLE_KEYS or event.get("event") != "variable_order":
        raise TraceError("dual selector variable-order field set changed")
    manager = event["manager_variables"]
    state_bits = event["state_bits"]
    if type(manager) is not int or type(state_bits) is not int or not (
        0 <= state_bits <= manager <= INT_MAX
    ):
        raise TraceError("dual selector variable-order cardinality changed")
    for field in (
        "cudd_indices", "cudd_levels", "fd_variables", "fd_bit_positions",
    ):
        _int_list(event[field], "variable order {}".format(field),
                  length=state_bits, maximum=INT_MAX)
    if (
        len(set(event["cudd_indices"])) != state_bits
        or event["cudd_levels"] != sorted(set(event["cudd_levels"]))
        or any(value >= manager for value in event["cudd_indices"])
        or any(value >= manager for value in event["cudd_levels"])
    ):
        raise TraceError("dual selector state-cut certificate changed")
    return event


def _validate_probe(event: dict) -> tuple[dict, dict]:
    if set(event) != PROBE_KEYS or event.get("event") != "probe":
        raise TraceError("dual selector probe field set changed")
    completed = event["completed_layers"]
    if any((
        type(event.get("target_layers")) is not int,
        event.get("target_layers") != 16,
        type(completed) is not int,
        not 0 <= completed <= 16,
        type(event.get("attempts")) is not int,
        not completed <= event["attempts"] <= INT_MAX,
        type(event.get("complete")) is not bool,
        event["complete"] != (completed == 16),
    )):
        raise TraceError("dual selector probe cardinality changed")
    _int_list(event["g_values"], "probe g values", length=completed,
              maximum=INT_MAX)
    _int_list(event["bdd_nodes"], "probe BDD nodes", length=completed)
    if any(left >= right for left, right in zip(
        event["g_values"], event["g_values"][1:]
    )):
        raise TraceError("dual selector completed layers are not increasing")
    overhead = _memory_fields(event, "probe")
    structural = {
        key: value for key, value in event.items() if key not in overhead
    }
    return structural, overhead


def _decode_histogram(value: str) -> list[tuple[int, int]]:
    if (
        not isinstance(value, str)
        or not value
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
        or len(value) % 4 == 1
    ):
        raise TraceError("dual selector raw histogram encoding changed")
    try:
        raw = base64.b64decode(
            (value + "=" * (-len(value) % 4)).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (ValueError, binascii.Error) as err:
        raise TraceError("dual selector raw histogram encoding changed") from err
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value:
        raise TraceError("dual selector raw histogram is not canonical")
    index = 0

    def varint() -> int:
        nonlocal index
        start = index
        result = 0
        shift = 0
        while True:
            if index >= len(raw) or shift >= 63:
                raise TraceError("dual selector histogram varint changed")
            byte = raw[index]
            index += 1
            result |= (byte & 0x7F) << shift
            if not byte & 0x80:
                encoded = []
                remainder = result
                while True:
                    item = remainder & 0x7F
                    remainder >>= 7
                    encoded.append(item | (0x80 if remainder else 0))
                    if not remainder:
                        break
                if bytes(encoded) != raw[start:index]:
                    raise TraceError("dual selector histogram varint is not canonical")
                return result
            shift += 7

    entries = varint()
    if entries > 100000:
        raise TraceError("dual selector histogram cardinality changed")
    histogram = []
    previous = -1
    total = 0
    for _ in range(entries):
        delta = varint()
        count = varint()
        distance = previous + delta
        if delta <= 0 or count <= 0 or not 0 <= distance < INT_MAX:
            raise TraceError("dual selector histogram entry changed")
        histogram.append((distance, count))
        previous = distance
        total += count
        if total > 100000:
            raise TraceError("dual selector histogram count changed")
    if index != len(raw):
        raise TraceError("dual selector histogram has trailing bytes")
    return histogram


def _validate_state_profiles(event, probe, state_bits) -> tuple[str, list[list[int]]]:
    if set(event) != {
        "event", "state_profiles_sha256", "cofactor_counts_by_layer",
    } or event.get("event") != "probe_state_profiles" or (
        not _is_sha256(event.get("state_profiles_sha256"))
    ):
        raise TraceError("dual selector state-profile event changed")
    profiles = event["cofactor_counts_by_layer"]
    if not isinstance(profiles, list) or len(profiles) != 16:
        raise TraceError("dual selector state-profile cardinality changed")
    lines = []
    for layer, profile in enumerate(profiles):
        _int_list(profile, "probe state profile", length=state_bits + 1)
        if any(value < 1 for value in profile):
            raise TraceError("dual selector state profile contains zero")
        lines.append("{}|g={}|bdd_nodes={}|cofactor_counts={}\n".format(
            layer,
            probe["g_values"][layer],
            probe["bdd_nodes"][layer],
            ",".join(map(str, profile)),
        ))
    digest = _sha256_text("".join(lines))
    if digest != event["state_profiles_sha256"]:
        raise TraceError("dual selector state-profile hash changed")
    return digest, profiles


def _validate_pool(event: dict) -> tuple[str, list[dict]]:
    if set(event) != {
        "event", "protocol", "state_budget", "pool_sha256", "patterns",
    } or any((
        event.get("event") != "pool",
        event.get("protocol") != TRACE_PROTOCOL,
        type(event.get("state_budget")) is not int,
        event.get("state_budget") != 100000,
        not _is_sha256(event.get("pool_sha256")),
        not isinstance(event.get("patterns"), list),
        not event.get("patterns"),
    )):
        raise TraceError("dual selector pool header changed")
    lines = []
    sources_seen = []
    vectors = set()
    for index, pattern in enumerate(event["patterns"]):
        if not isinstance(pattern, dict) or set(pattern) != {
            "pattern_index", "sources", "pattern", "abstract_states",
            "within_state_budget",
        }:
            raise TraceError("dual selector pool pattern changed")
        sources = pattern["sources"]
        variables = pattern["pattern"]
        states = pattern["abstract_states"]
        within = pattern["within_state_budget"]
        if (
            not isinstance(sources, list)
            or not sources
            or any(source not in SCHEMA_EVENT["candidate_sources"] for source in sources)
        ):
            raise TraceError("dual selector pool source is invalid")
        if any((
            type(pattern.get("pattern_index")) is not int,
            pattern["pattern_index"] != index,
            sources != sorted(set(sources), key=SCHEMA_EVENT[
                "candidate_sources"
            ].index),
            not isinstance(variables, list),
            any(type(var) is not int or not 0 <= var <= INT_MAX for var in variables),
            variables != sorted(set(variables)),
            type(states) is not int,
            not 1 <= states <= INT_MAX,
            type(within) is not bool,
            within != (states <= 100000),
            tuple(variables) in vectors,
        )):
            raise TraceError("dual selector pool pattern is invalid")
        vectors.add(tuple(variables))
        sources_seen.extend(sources)
        lines.append(
            "{}|sources={}|pattern={}|abstract_states={}|"
            "within_state_budget={}\n".format(
                index, ",".join(sources), ",".join(map(str, variables)),
                states, int(within),
            )
        )
    if sources_seen != SCHEMA_EVENT["candidate_sources"]:
        raise TraceError("dual selector pool generator coverage changed")
    first = event["patterns"][0]
    if first["pattern"] != [] or first["sources"] != ["empty"] or (
        first["abstract_states"] != 1 or first["within_state_budget"] is not True
    ):
        raise TraceError("dual selector mandatory empty pattern changed")
    digest = _sha256_text("".join(lines))
    if digest != event["pool_sha256"]:
        raise TraceError("dual selector pool hash changed")
    return digest, event["patterns"]


def _csv(values) -> str:
    return ",".join(map(str, values))


def _nested_csv(values) -> str:
    return ";".join(_csv(row) for row in values)


def _incidence_projection_line(candidate: dict, *, newline=True) -> str:
    cap = "exact" if candidate["value_cap"] is None else candidate["value_cap"]
    initial_h = "null" if candidate["initial_dead_end"] else candidate["initial_h"]
    histogram = candidate["raw_value_histogram"]
    histogram = "null" if histogram is None else histogram
    values = dict(candidate)
    values.update({
        "cap": cap,
        "initial_dead_end": int(candidate["initial_dead_end"]),
        "initial_h": initial_h,
        "histogram": histogram,
        "incidence": _csv(candidate["terminal_incidence_by_layer"]),
        "reference_feasible": int(candidate["reference_feasible"]),
    })
    line = (
        "{pattern_index}|cap={cap}|initial_dead_end={initial_dead_end}|"
        "initial_h={initial_h}|finite_sum={finite_sum}|"
        "finite_count={finite_count}|dead_count={dead_count}|"
        "cofactor_width={cofactor_width}|width_upper_bound={width_upper_bound}|"
        "raw_max_finite_value={raw_max_finite_value}|"
        "raw_value_histogram={histogram}|incidence={incidence}|"
        "incidence_total={terminal_incidence}|"
        "reference_feasible={reference_feasible}"
    ).format(**values)
    return line + ("\n" if newline else "")


def _dual_line(candidate: dict) -> str:
    return "".join((
        _incidence_projection_line(candidate, newline=False),
        "|heuristic_cofactor_counts=", _csv(candidate["heuristic_cofactor_counts"]),
        "|dead_end_value={}".format(candidate["dead_end_value"]),
        "|masked_add_nodes=", _csv(candidate["masked_add_nodes_by_layer"]),
        "|active_finite_values=", _nested_csv(candidate["active_finite_values_by_layer"]),
        "|dead_end_active=", _csv(int(value) for value in candidate["dead_end_active_by_layer"]),
        "|active_terminal_count=", _csv(candidate["active_terminal_count_by_layer"]),
        "|joint_cofactor_counts=", _nested_csv(candidate["joint_cofactor_counts_by_layer"]),
        "|joint_cofactor_sum=", _csv(candidate["joint_cofactor_sum_by_layer"]),
        "|masked_joint=", _csv(candidate["masked_joint_by_layer"]),
        "|masked_joint_total={}".format(candidate["masked_joint"]),
        "|incidence_node_kinds=",
        _nested_csv(candidate["incidence_node_kinds_by_layer"]),
        "|incidence_then_children=",
        _nested_csv(candidate["incidence_then_children_by_layer"]),
        "|incidence_else_children=",
        _nested_csv(candidate["incidence_else_children_by_layer"]),
        "|incidence_terminal_values=",
        _nested_csv(candidate["incidence_terminal_values_by_layer"]),
        "\n",
    ))


def _replay_incidence_layer(candidate: dict, layer: int) -> None:
    kinds = candidate["incidence_node_kinds_by_layer"][layer]
    then_children = candidate["incidence_then_children_by_layer"][layer]
    else_children = candidate["incidence_else_children_by_layer"][layer]
    terminal_values = candidate["incidence_terminal_values_by_layer"][layer]
    count = len(kinds) if isinstance(kinds, list) else -1
    if count < 1 or count > MAX_RAW_DAG_NODES or any(
        not isinstance(row, list) or len(row) != count
        for row in (then_children, else_children, terminal_values)
    ):
        raise TraceError("dual selector incidence DAG cardinality changed")
    if any(type(kind) is not int or kind not in (0, 1, 2) for kind in kinds):
        raise TraceError("dual selector incidence DAG node kind changed")
    next_new = 1
    discovered = {0}
    parents = [[] for _ in range(count)]
    active = []
    bottom_count = 0
    for node in range(count):
        kind = kinds[node]
        children = (then_children[node], else_children[node])
        value = terminal_values[node]
        if kind == 0:
            if type(value) is not int or value != -1 or any(
                type(child) is not int or not 0 <= child < count
                for child in children
            ):
                raise TraceError("dual selector incidence DAG inner node changed")
            for child in children:
                if child not in discovered:
                    if child != next_new:
                        raise TraceError(
                            "dual selector incidence DAG is not canonical BFS"
                        )
                    discovered.add(child)
                    next_new += 1
                parents[child].append(node)
        else:
            if any(type(child) is not int or child != -1 for child in children):
                raise TraceError("dual selector incidence DAG terminal edge changed")
            if kind == 1:
                bottom_count += 1
                if type(value) is not int or value != -1:
                    raise TraceError("dual selector fresh bottom value changed")
            elif type(value) is not int or not 0 <= value <= INT_MAX:
                raise TraceError("dual selector active terminal value changed")
            else:
                active.append((node, value))
    if discovered != set(range(count)) or bottom_count > 1:
        raise TraceError("dual selector incidence DAG reachability changed")
    colors = [0] * count
    traversal_steps = 0
    # The explicit stack makes adversarial deep certificates deterministic:
    # they either certify or hit the fixed work bound, never Python recursion.
    stack = [(0, 0)]
    colors[0] = 1
    while stack:
        traversal_steps += 1
        if traversal_steps > MAX_RAW_DAG_TRAVERSAL_STEPS:
            raise TraceError("dual selector incidence DAG traversal is too large")
        node, next_edge = stack[-1]
        if kinds[node] != 0 or next_edge == 2:
            colors[node] = 2
            stack.pop()
            continue
        child = (then_children[node], else_children[node])[next_edge]
        stack[-1] = (node, next_edge + 1)
        if colors[child] == 1:
            raise TraceError("dual selector incidence DAG contains a cycle")
        if colors[child] == 0:
            colors[child] = 1
            stack.append((child, 0))
    values = sorted(value for _, value in active)
    if len(values) != len(set(values)) or not values:
        raise TraceError("dual selector active terminal identity changed")
    expected_values = list(candidate["active_finite_values_by_layer"][layer])
    if candidate["dead_end_active_by_layer"][layer]:
        expected_values.append(candidate["dead_end_value"])
    if values != sorted(expected_values):
        raise TraceError("dual selector semantic dead-end normalization changed")
    incidence = 0
    for terminal, _ in active:
        seen = set()
        stack = [terminal]
        while stack:
            traversal_steps += 1
            if traversal_steps > MAX_RAW_DAG_TRAVERSAL_STEPS:
                raise TraceError("dual selector incidence DAG traversal is too large")
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            if kinds[node] == 0:
                if incidence == LONG_MAX:
                    raise TraceError("dual selector raw incidence overflows")
                incidence += 1
            stack.extend(parents[node])
    if incidence != candidate["terminal_incidence_by_layer"][layer] or (
        sum(kind == 0 for kind in kinds)
        != candidate["masked_add_nodes_by_layer"][layer]
    ):
        raise TraceError("dual selector raw incidence replay changed")


def _validate_candidate(candidate, patterns, profiles, probe, state_bits) -> None:
    if set(candidate) != CANDIDATE_KEYS or any((
        candidate.get("event") != "candidate",
        candidate.get("protocol") != TRACE_PROTOCOL,
        candidate.get("score_version") != SCORE_VERSION,
        type(candidate.get("pattern_index")) is not int,
        not 0 <= candidate.get("pattern_index", -1) < len(patterns),
    )):
        raise TraceError("dual selector candidate header changed")
    pattern = patterns[candidate["pattern_index"]]
    if any((
        not _same_json(candidate["sources"], pattern["sources"]),
        not _same_json(candidate["pattern"], pattern["pattern"]),
        type(candidate["abstract_states"]) is not int,
        candidate["abstract_states"] != pattern["abstract_states"],
        candidate["value_cap"] is not None
        and type(candidate["value_cap"]) is not int,
        candidate["value_cap"] not in CAP_GRID,
        type(candidate["initial_dead_end"]) is not bool,
        candidate["initial_dead_end"] != (candidate["initial_h"] is None),
        candidate["initial_h"] is not None and (
            type(candidate["initial_h"]) is not int
            or not 0 <= candidate["initial_h"] <= INT_MAX
        ),
        any(type(candidate[field]) is not int or candidate[field] < 0 for field in (
            "finite_sum", "finite_count", "dead_count", "cofactor_width",
            "width_upper_bound", "raw_max_finite_value", "terminal_incidence",
            "masked_joint",
        )),
        candidate["finite_sum"] > LONG_MAX,
        any(candidate[field] > INT_MAX for field in (
            "finite_count", "dead_count", "raw_max_finite_value",
        )),
        type(candidate.get("dead_end_value")) is not int,
        not -1 <= candidate.get("dead_end_value", -2) <= INT_MAX,
        candidate["dead_end_value"] == -1 and candidate["dead_count"] != 0,
        candidate["dead_end_value"] >= 0 and candidate["dead_count"] == 0,
        any(candidate[field] > LONG_MAX for field in (
            "cofactor_width", "width_upper_bound", "terminal_incidence",
            "masked_joint",
        )),
        candidate["finite_count"] + candidate["dead_count"]
        != candidate["abstract_states"],
        candidate["finite_count"] == 0 and candidate["finite_sum"] != 0,
        candidate["finite_count"] == 0 and not candidate["initial_dead_end"],
        candidate["initial_dead_end"] and candidate["dead_count"] == 0,
        candidate["cofactor_width"] < 1,
        candidate["cofactor_width"] > candidate["width_upper_bound"],
        candidate["reference_feasible"]
        != (candidate["cofactor_width"] <= 32),
        any(type(candidate[field]) is not bool for field in (
            "reference_feasible", "incidence_feasible", "masked_joint_feasible",
            "incidence_retained_for_pattern", "masked_joint_retained_for_pattern",
        )),
    )):
        raise TraceError("dual selector candidate scalar changed")
    _int_list(candidate["heuristic_cofactor_counts"], "heuristic profile",
              length=state_bits + 1)
    if any(value < 1 for value in candidate["heuristic_cofactor_counts"]):
        raise TraceError("dual selector heuristic profile contains zero")
    layer_fields = (
        "terminal_incidence_by_layer", "masked_add_nodes_by_layer",
        "active_finite_values_by_layer", "dead_end_active_by_layer",
        "active_terminal_count_by_layer", "joint_cofactor_counts_by_layer",
        "joint_cofactor_sum_by_layer", "masked_joint_by_layer",
        "incidence_node_kinds_by_layer", "incidence_then_children_by_layer",
        "incidence_else_children_by_layer", "incidence_terminal_values_by_layer",
    )
    if any(not isinstance(candidate[field], list) or len(candidate[field]) != 16
           for field in layer_fields):
        raise TraceError("dual selector candidate layer cardinality changed")
    if sum(candidate["terminal_incidence_by_layer"]) != candidate[
        "terminal_incidence"
    ] or sum(candidate["masked_joint_by_layer"]) != candidate["masked_joint"]:
        raise TraceError("dual selector aggregate metric changed")
    possible_values = None
    if candidate["raw_value_histogram"] is not None:
        possible_values = {
            value for value, _ in _decode_histogram(candidate["raw_value_histogram"])
        }
    for layer in range(16):
        finite = candidate["active_finite_values_by_layer"][layer]
        dead = candidate["dead_end_active_by_layer"][layer]
        active = candidate["active_terminal_count_by_layer"][layer]
        joint = candidate["joint_cofactor_counts_by_layer"][layer]
        joint_sum = candidate["joint_cofactor_sum_by_layer"][layer]
        masked_joint = candidate["masked_joint_by_layer"][layer]
        incidence = candidate["terminal_incidence_by_layer"][layer]
        masked_nodes = candidate["masked_add_nodes_by_layer"][layer]
        _int_list(finite, "active finite values", maximum=INT_MAX)
        _int_list(joint, "joint cofactor profile", length=state_bits + 1)
        if any((
            finite != sorted(set(finite)),
            type(dead) is not bool,
            candidate["dead_count"] == 0 and dead,
            type(active) is not int,
            active != len(finite) + int(dead),
            active < 1,
            any(type(value) is not int or value < 1 for value in joint),
            type(joint_sum) is not int,
            joint_sum != sum(joint[:-1]),
            type(masked_joint) is not int,
            not 0 <= masked_joint <= LONG_MAX,
            masked_joint != active * joint_sum,
            type(incidence) is not int,
            type(masked_nodes) is not int,
            not 0 <= incidence <= LONG_MAX,
            not 0 <= masked_nodes <= LONG_MAX,
            not 0 <= masked_nodes <= incidence <= active * masked_nodes,
            incidence < probe["bdd_nodes"][layer],
            incidence > masked_joint,
        )):
            raise TraceError("dual selector I/mJ layer formula changed")
        if possible_values is not None and not set(finite) <= possible_values:
            raise TraceError("dual selector active finite value is not attainable")
        _replay_incidence_layer(candidate, layer)
        for state_count, heuristic_count, joint_count in zip(
            profiles[layer], candidate["heuristic_cofactor_counts"], joint
        ):
            if not max(state_count, heuristic_count) <= joint_count <= (
                state_count * heuristic_count
            ):
                raise TraceError("dual selector joint projection bound changed")


def _compare_ratio(a_num, a_den, b_num, b_den, *, zero_infinity):
    if zero_infinity and (a_den == 0 or b_den == 0):
        if a_den == b_den:
            return 0
        return 1 if a_den == 0 else -1
    left = a_num * b_den
    right = b_num * a_den
    return (left > right) - (left < right)


def _better(candidate, incumbent):
    if candidate["initial_dead_end"] != incumbent["initial_dead_end"]:
        return candidate["initial_dead_end"]
    if not candidate["initial_dead_end"] and (
        candidate["initial_h"] != incumbent["initial_h"]
    ):
        return candidate["initial_h"] > incumbent["initial_h"]
    comparison = _compare_ratio(
        candidate["finite_sum"], candidate["finite_count"],
        incumbent["finite_sum"], incumbent["finite_count"],
        zero_infinity=True,
    )
    if comparison:
        return comparison > 0
    comparison = _compare_ratio(
        candidate["dead_count"], candidate["abstract_states"],
        incumbent["dead_count"], incumbent["abstract_states"],
        zero_infinity=False,
    )
    if comparison:
        return comparison > 0
    for field in ("cofactor_width", "abstract_states"):
        if candidate[field] != incumbent[field]:
            return candidate[field] < incumbent[field]
    return candidate["pattern"] < incumbent["pattern"]


def _best(candidates):
    if not candidates:
        raise TraceError("dual selector candidate set is empty")
    winner = candidates[0]
    for candidate in candidates[1:]:
        if _better(candidate, winner):
            winner = candidate
    return winner


def _candidate_identity(candidate):
    return {
        "pattern_index": candidate["pattern_index"],
        "sources": candidate["sources"],
        "pattern": candidate["pattern"],
        "value_cap": candidate["value_cap"],
        "terminal_incidence": candidate["terminal_incidence"],
        "masked_joint": candidate["masked_joint"],
    }


def _event_identity(event, prefix):
    keys = (
        "pattern_index", "sources", "pattern", "value_cap",
        "terminal_incidence", "masked_joint",
    )
    try:
        return {key: event[prefix + key] for key in keys}
    except KeyError as err:
        raise TraceError("dual selector identity field is absent") from err


def _normalize_pool(patterns):
    return [
        {
            "pattern_index": row["pattern_index"],
            "sources": row["sources"],
            "pattern": row["pattern"],
            "abstract_states": row["abstract_states"],
            "within_state_budget": row["within_state_budget"],
        }
        for row in patterns
    ]


def _validate_complete(events, mode, variable, probe, probe_overhead):
    kinds = [event.get("event") for event in events]
    tail = [
        "preselection", "reference", "metric_winners", "selected",
        "selection_accounting",
    ]
    if (
        len(events) < 10
        or kinds[:5] != [
            "schema", "variable_order", "probe", "probe_state_profiles", "pool",
        ]
        or kinds[-5:] != tail
        or any(kind != "candidate" for kind in kinds[5:-5])
    ):
        raise TraceError("dual selector complete event order changed")
    state_sha, profiles = _validate_state_profiles(
        events[3], probe, variable["state_bits"]
    )
    pool_sha, patterns = _validate_pool(events[4])
    candidates = events[5:-5]
    for candidate in candidates:
        _validate_candidate(
            candidate, patterns, profiles, probe, variable["state_bits"]
        )
    by_pattern = {}
    for candidate in candidates:
        by_pattern.setdefault(candidate["pattern_index"], []).append(candidate)
    expected_indexes = {
        row["pattern_index"] for row in patterns if row["within_state_budget"]
    }
    if set(by_pattern) != expected_indexes or [
        candidate["pattern_index"] for candidate in candidates
    ] != sorted(candidate["pattern_index"] for candidate in candidates):
        raise TraceError("dual selector candidate pool coverage changed")
    empty_variants = by_pattern.get(0, [])
    if len(empty_variants) != 1:
        raise TraceError("dual selector mandatory empty candidate changed")
    empty = empty_variants[0]
    empty_expected = {
        "abstract_states": 1, "value_cap": None,
        "initial_dead_end": False, "initial_h": 0,
        "finite_sum": 0, "finite_count": 1, "dead_count": 0,
        "cofactor_width": 1, "width_upper_bound": 1,
        "raw_max_finite_value": 0, "raw_value_histogram": "AQEB",
        "heuristic_cofactor_counts": [1] * (variable["state_bits"] + 1),
        "active_finite_values_by_layer": [[0] for _ in range(16)],
        "dead_end_active_by_layer": [False] * 16,
        "active_terminal_count_by_layer": [1] * 16,
        "joint_cofactor_counts_by_layer": profiles,
        "joint_cofactor_sum_by_layer": [sum(row[:-1]) for row in profiles],
        "masked_joint_by_layer": [sum(row[:-1]) for row in profiles],
        "masked_joint": sum(sum(row[:-1]) for row in profiles),
        "reference_feasible": True,
    }
    if any(empty.get(field) != value for field, value in empty_expected.items()):
        raise TraceError("dual selector mandatory empty candidate changed")
    for variants in by_pattern.values():
        exact = variants[-1]
        if exact["raw_value_histogram"] is None:
            raise TraceError("dual selector exact cap lacks raw histogram")
        histogram = _decode_histogram(exact["raw_value_histogram"])
        raw_max = histogram[-1][0] if histogram else 0
        finite_count = sum(count for _, count in histogram)
        histogram_count = sum(count for _, count in histogram)
        histogram_sum = sum(value * count for value, count in histogram)
        if any(
            row["raw_max_finite_value"] != raw_max
            or row["finite_count"] != finite_count
            or row["dead_count"] != exact["dead_count"]
            or row["raw_value_histogram"] is not None
            for row in variants[:-1]
        ) or any((
            exact["raw_max_finite_value"] != raw_max,
            exact["finite_count"] != histogram_count,
            exact["dead_count"] != exact["abstract_states"] - histogram_count,
            exact["finite_sum"] != histogram_sum,
            exact["initial_h"] is not None
            and exact["initial_h"] not in dict(histogram),
        )):
            raise TraceError("dual selector raw finite histogram changed")
        expected_caps = [cap for cap in CAP_GRID[:-1] if cap < raw_max] + [None]
        if [row["value_cap"] for row in variants] != expected_caps:
            raise TraceError("dual selector cap grid changed")
        dead_vector = exact["dead_end_active_by_layer"]
        previous = None
        for row in variants:
            cap = row["value_cap"]
            possible = {
                value if cap is None else min(value, cap) for value, _ in histogram
            }
            if any(not set(values) <= possible
                   for values in row["active_finite_values_by_layer"]):
                raise TraceError("dual selector capped active values changed")
            if row["dead_end_active_by_layer"] != dead_vector:
                raise TraceError("dual selector semantic dead end changed across caps")
            expected_sum = sum(
                (value if cap is None else min(value, cap)) * count
                for value, count in histogram
            )
            if row["finite_sum"] != expected_sum or row["finite_count"] != sum(
                count for _, count in histogram
            ):
                raise TraceError("dual selector cap transform changed")
            if not row["initial_dead_end"]:
                raw_initial = exact["initial_h"]
                expected_initial = (
                    raw_initial if cap is None else min(raw_initial, cap)
                )
                if row["initial_h"] != expected_initial:
                    raise TraceError("dual selector initial value cap changed")
            terminal_values = {
                value if cap is None else min(value, cap) for value, _ in histogram
            }
            terminal_count = len(terminal_values) + int(row["dead_count"] > 0)
            if any((
                row["cofactor_width"] < terminal_count,
                row["width_upper_bound"]
                < row["cofactor_width"] + terminal_count - 1,
                row["heuristic_cofactor_counts"][0] != 1,
                row["heuristic_cofactor_counts"][-1] != terminal_count,
                max(row["heuristic_cofactor_counts"])
                != row["cofactor_width"],
            )):
                raise TraceError("dual selector ADD profile is impossible")
            if terminal_count == 1 and any((
                row["cofactor_width"] != 1,
                row["width_upper_bound"] != 1,
                row["heuristic_cofactor_counts"]
                != [1] * (variable["state_bits"] + 1),
                row["joint_cofactor_counts_by_layer"] != profiles,
            )):
                raise TraceError("dual selector constant ADD structure changed")
            if previous is not None:
                monotone_fields = (
                    "heuristic_cofactor_counts", "terminal_incidence_by_layer",
                    "masked_add_nodes_by_layer", "active_terminal_count_by_layer",
                    "joint_cofactor_sum_by_layer", "masked_joint_by_layer",
                )
                if any(any(left > right for left, right in zip(
                    previous[field], row[field]
                )) for field in monotone_fields) or any(
                    any(left > right for left, right in zip(old, new))
                    for old, new in zip(
                        previous["joint_cofactor_counts_by_layer"],
                        row["joint_cofactor_counts_by_layer"],
                    )
                ):
                    raise TraceError("dual selector cap refinement is not monotone")
                if row["cofactor_width"] < previous["cofactor_width"] or (
                    row["width_upper_bound"] < previous["width_upper_bound"]
                ):
                    raise TraceError("dual selector cap widths are not monotone")
            previous = row

    preselection, reference, winners, selected, accounting = events[-5:]
    incidence_canonical = "".join(
        _incidence_projection_line(candidate) for candidate in candidates
    )
    dual_canonical = "".join(_dual_line(candidate) for candidate in candidates)
    incidence_sha = _sha256_text(incidence_canonical)
    pre_sha = _sha256_text(dual_canonical)
    hash_fields = {
        "pool_sha256": pool_sha,
        "state_profiles_sha256": state_sha,
        "incidence_projection_sha256": incidence_sha,
        "preselection_sha256": pre_sha,
    }
    if set(preselection) != {
        "event", *hash_fields, "candidate_count",
    } or preselection.get("event") != "preselection" or (
        type(preselection.get("candidate_count")) is not int
    ) or (
        preselection.get("candidate_count") != len(candidates)
    ) or any(preselection.get(key) != value for key, value in hash_fields.items()):
        raise TraceError("dual selector preselection hashes changed")
    for event, label in (
        (reference, "reference"), (winners, "metric_winners"),
        (selected, "selected"),
    ):
        if event.get("event") != label or any(
            event.get(key) != value for key, value in hash_fields.items()
        ):
            raise TraceError("dual selector hash chain changed")

    identity_suffixes = {
        "pattern_index", "sources", "pattern", "value_cap",
        "terminal_incidence", "masked_joint",
    }
    reference_keys = {
        "event", *hash_fields,
        *("reference_" + key for key in identity_suffixes),
        "reference_cofactor_width_budget", "incidence_budget",
        "masked_joint_budget",
    }
    winners_keys = {
        "event", *hash_fields, "incidence_budget", "masked_joint_budget",
        *("incidence_winner_" + key for key in identity_suffixes),
        *("masked_joint_winner_" + key for key in identity_suffixes),
    }
    selected_keys = {
        "event", "decision_mode", *hash_fields,
        *("selected_" + key for key in identity_suffixes),
        "incidence_budget", "masked_joint_budget",
    }
    if set(reference) != reference_keys or set(winners) != winners_keys or (
        set(selected) != selected_keys
    ):
        raise TraceError("dual selector decision event field set changed")

    reference_reps = []
    for variants in by_pattern.values():
        feasible = [row for row in variants if row["reference_feasible"]]
        if feasible:
            reference_reps.append(feasible[-1])
    expected_reference = _best(reference_reps)
    reference_identity = _event_identity(reference, "reference_")
    for field in (
        "reference_cofactor_width_budget", "incidence_budget",
        "masked_joint_budget",
    ):
        _exact_int(reference.get(field), "dual selector reference " + field)
    if not _same_json(
        reference_identity, _candidate_identity(expected_reference)
    ) or any((
        reference.get("reference_cofactor_width_budget") != 32,
        reference.get("incidence_budget") != expected_reference["terminal_incidence"],
        reference.get("masked_joint_budget") != expected_reference["masked_joint"],
    )):
        raise TraceError("dual selector K32 reference changed")
    incidence_budget = reference["incidence_budget"]
    mj_budget = reference["masked_joint_budget"]
    metric_specs = (
        (
            "incidence", "terminal_incidence", incidence_budget,
            "incidence_feasible", "incidence_retained_for_pattern",
        ),
        (
            "masked_joint", "masked_joint", mj_budget,
            "masked_joint_feasible", "masked_joint_retained_for_pattern",
        ),
    )
    expected_winners = {}
    for name, metric, budget, feasible_field, retained_field in metric_specs:
        reps = []
        for variants in by_pattern.values():
            feasible = [row for row in variants if row[metric] <= budget]
            for row in variants:
                if row[feasible_field] != (row[metric] <= budget):
                    raise TraceError("dual selector metric feasibility changed")
                if row[retained_field] != (
                    bool(feasible) and row is feasible[-1]
                ):
                    raise TraceError("dual selector retained-cap flag changed")
            if feasible:
                reps.append(feasible[-1])
        expected_winners[name] = _best(reps)
    for field in ("incidence_budget", "masked_joint_budget"):
        _exact_int(winners.get(field), "dual selector winner " + field)
    if any((
        winners.get("incidence_budget") != incidence_budget,
        winners.get("masked_joint_budget") != mj_budget,
        not _same_json(
            _event_identity(winners, "incidence_winner_"),
            _candidate_identity(expected_winners["incidence"]),
        ),
        not _same_json(
            _event_identity(winners, "masked_joint_winner_"),
            _candidate_identity(expected_winners["masked_joint"]),
        ),
    )):
        raise TraceError("dual selector metric winner reconstruction changed")
    expected_modes = {
        P.INCIDENCE_MODE: ("incidence_guided", expected_winners["incidence"]),
        P.MJ_MODE: ("masked_joint_guided", expected_winners["masked_joint"]),
        P.MATCHED_MODE: ("matched_control", expected_reference),
    }
    decision, expected_selected = expected_modes[mode]
    selected_identity = _event_identity(selected, "selected_")
    for field in ("incidence_budget", "masked_joint_budget"):
        _exact_int(selected.get(field), "dual selector selected " + field)
    if any((
        selected.get("decision_mode") != decision,
        selected.get("incidence_budget") != incidence_budget,
        selected.get("masked_joint_budget") != mj_budget,
        not _same_json(selected_identity, _candidate_identity(expected_selected)),
    )):
        raise TraceError("dual selector final pointer changed")

    accounting_keys = {
        "event", "candidate_count", "probe_state_profile_count",
        "probe_state_profile_cut_entries",
        "terminal_incidence_layer_measurements",
        "joint_profile_layer_measurements", "joint_profile_cut_entries",
        "joint_summed_cut_entries", "cpu_seconds", "wall_seconds",
        "peak_memory_before_kb", "peak_memory_after_kb", "peak_memory_delta_kb",
    }
    state_cuts = variable["state_bits"] + 1
    layer_measurements = len(candidates) * 16
    expected_work = {
        "candidate_count": len(candidates),
        "probe_state_profile_count": 16,
        "probe_state_profile_cut_entries": 16 * state_cuts,
        "terminal_incidence_layer_measurements": layer_measurements,
        "joint_profile_layer_measurements": layer_measurements,
        "joint_profile_cut_entries": layer_measurements * state_cuts,
        "joint_summed_cut_entries": layer_measurements * variable["state_bits"],
    }
    if set(accounting) != accounting_keys or accounting.get("event") != (
        "selection_accounting"
    ) or any(
        type(accounting.get(key)) is not int
        or accounting.get(key) != value
        for key, value in expected_work.items()
    ):
        raise TraceError("dual selector work accounting changed")
    selection_overhead = _memory_fields(accounting, "selection")
    accounting_structural = {"event": "selection_accounting", **expected_work}
    structural = [
        events[0], variable, probe, events[3], events[4], *candidates,
        preselection, reference, winners, accounting_structural,
    ]
    structural_sha = hashlib.sha256(P.canonical_json(structural)).hexdigest()
    normalized_pool = _normalize_pool(patterns)
    return {
        "status": "complete",
        "structural_trace": structural,
        "structural_trace_sha256": structural_sha,
        "pool_sha256": pool_sha,
        "normalized_pool": normalized_pool,
        "normalized_pool_sha256": hashlib.sha256(
            P.canonical_json(normalized_pool)
        ).hexdigest(),
        "state_profiles_sha256": state_sha,
        "incidence_projection_sha256": incidence_sha,
        "incidence_v3_projection_sha256": incidence_sha,
        "preselection_sha256": pre_sha,
        "reference_identity": reference_identity,
        "incidence_winner_identity": _candidate_identity(
            expected_winners["incidence"]
        ),
        "masked_joint_winner_identity": _candidate_identity(
            expected_winners["masked_joint"]
        ),
        "selected_identity": selected_identity,
        "selected_differs_from_reference": selected_identity != reference_identity,
        "incidence_and_mj_winners_differ": _candidate_identity(
            expected_winners["incidence"]
        ) != _candidate_identity(expected_winners["masked_joint"]),
        "work_signature": expected_work,
        "probe_completed_layers": 16,
        **{"probe_" + key: value for key, value in probe_overhead.items()},
        **{"selection_" + key: value for key, value in selection_overhead.items()},
    }


def _certify_trace(content: str, mode: str) -> dict:
    if mode not in P.MODES:
        raise TraceError("dual selector mode is invalid")
    events = _load_events(content)
    if not events or not _same_json(events[0], SCHEMA_EVENT):
        raise TraceError("dual selector schema event changed or is absent")
    if len(events) < 3:
        raise TraceError("dual selector trace ended before the probe")
    variable = _validate_variable_order(events[1])
    probe, probe_overhead = _validate_probe(events[2])
    if not events[2]["complete"]:
        if len(events) != 3:
            raise TraceError("short probe has trailing dual selector events")
        structural = [events[0], variable, probe]
        return {
            "status": "short_probe",
            "structural_trace": structural,
            "structural_trace_sha256": hashlib.sha256(
                P.canonical_json(structural)
            ).hexdigest(),
            "probe_completed_layers": events[2]["completed_layers"],
            **{"probe_" + key: value for key, value in probe_overhead.items()},
        }
    return _validate_complete(
        events, mode, variable, probe, probe_overhead
    )


def certify_trace(content: str, mode: str) -> dict:
    try:
        return _certify_trace(content, mode)
    except TraceError:
        raise
    except (IndexError, KeyError, OverflowError, TypeError, ValueError) as err:
        raise TraceError("dual selector trace contains a malformed value") from err


def certify_short_structural_trace(
    structural_trace: list[dict], mode: str,
) -> dict:
    """Re-run the short-probe parser from its stored outcome-free structure."""
    if not isinstance(structural_trace, list) or len(structural_trace) != 3:
        raise TraceError("dual selector short structural trace is incomplete")
    structural = copy.deepcopy(structural_trace)
    if any(not isinstance(event, dict) for event in structural):
        raise TraceError(
            "dual selector short structural trace contains a non-object"
        )
    structural[2].update({
        "cpu_seconds": 0.0, "wall_seconds": 0.0,
        "peak_memory_before_kb": 0, "peak_memory_after_kb": 0,
        "peak_memory_delta_kb": 0,
    })
    content = "".join(
        json.dumps(event, separators=(",", ":"), ensure_ascii=True) + "\n"
        for event in structural
    )
    result = certify_trace(content, mode)
    if result["status"] != "short_probe" or not _same_json(
        result["structural_trace"], structural_trace
    ):
        raise TraceError("dual selector short structural replay changed")
    return result


def certify_structural_trace(
    structural_trace: list[dict], mode: str, selected_identity: dict,
) -> dict:
    """Re-run the complete parser from the outcome-free stored structure."""
    if not isinstance(structural_trace, list) or len(structural_trace) < 10:
        raise TraceError("dual selector structural trace is incomplete")
    structural = copy.deepcopy(structural_trace)
    if any(not isinstance(event, dict) for event in structural):
        raise TraceError("dual selector structural trace contains a non-object")
    if [event.get("event") for event in structural[-4:]] != [
        "preselection", "reference", "metric_winners", "selection_accounting",
    ]:
        raise TraceError("dual selector structural trace tail changed")
    probe = structural[2]
    accounting = structural[-1]
    probe.update({
        "cpu_seconds": 0.0, "wall_seconds": 0.0,
        "peak_memory_before_kb": 0, "peak_memory_after_kb": 0,
        "peak_memory_delta_kb": 0,
    })
    accounting.update({
        "cpu_seconds": 0.0, "wall_seconds": 0.0,
        "peak_memory_before_kb": 0, "peak_memory_after_kb": 0,
        "peak_memory_delta_kb": 0,
    })
    reference = structural[-3]
    identity_keys = {
        "pattern_index", "sources", "pattern", "value_cap",
        "terminal_incidence", "masked_joint",
    }
    if not isinstance(selected_identity, dict) or set(selected_identity) != (
        identity_keys
    ):
        raise TraceError("dual selector selected identity is incomplete")
    decision = {
        P.INCIDENCE_MODE: "incidence_guided",
        P.MJ_MODE: "masked_joint_guided",
        P.MATCHED_MODE: "matched_control",
    }.get(mode)
    if decision is None:
        raise TraceError("dual selector mode is invalid")
    hash_fields = {
        key: reference[key] for key in (
            "pool_sha256", "state_profiles_sha256",
            "incidence_projection_sha256", "preselection_sha256",
        )
    }
    selected = {
        "event": "selected", "decision_mode": decision, **hash_fields,
        **{"selected_" + key: selected_identity[key] for key in identity_keys},
        "incidence_budget": reference["incidence_budget"],
        "masked_joint_budget": reference["masked_joint_budget"],
    }
    events = [*structural[:-1], selected, accounting]
    content = "".join(
        json.dumps(event, separators=(",", ":"), ensure_ascii=True) + "\n"
        for event in events
    )
    result = certify_trace(content, mode)
    if not _same_json(result["structural_trace"], structural_trace):
        raise TraceError("dual selector structural replay changed")
    return result


def _set_result(props, result: dict, *, certified: bool, error=None) -> None:
    props["dual_selector_trace_schema"] = TRACE_SCHEMA
    props["dual_selector_trace_status"] = result.get("status")
    props["dual_selector_trace_certified"] = certified
    props["dual_selector_trace_validation_error"] = error
    for key, value in result.items():
        if key != "status":
            props["dual_selector_" + key] = value


def parse_selector_trace(content, props) -> None:
    mode = props.get("algorithm")
    if mode not in P.MODES:
        if content:
            message = "non-dual run produced a dual selector trace"
            _set_result(props, {"status": "unexpected"}, certified=False,
                        error=message)
            add_error = getattr(props, "add_unexplained_error", None)
            if callable(add_error):
                add_error(message)
        else:
            _set_result(props, {"status": "not_applicable"}, certified=True)
        return
    try:
        result = certify_trace(content, mode)
        if result["status"] == "short_probe":
            if any((
                type(props.get("planner_exit_code")) is not int,
                props.get("planner_exit_code") != 34,
                type(props.get("coverage")) is not int,
                props.get("coverage") != 0,
            )):
                raise TraceError(
                    "short probe is not paired with unsupported exit 34"
                )
        elif any((
            type(props.get("planner_exit_code")) is not int,
            type(props.get("coverage")) is not int,
            props.get("coverage") not in (0, 1),
            props.get("planner_exit_code") == 34,
            props.get("coverage") == 1
            and props.get("planner_exit_code") != 0,
            props.get("coverage") == 0
            and props.get("planner_exit_code") == 0,
        )):
            raise TraceError("complete trace has malformed outcome metadata")
        _set_result(props, result, certified=True)
    except TraceError as err:
        message = str(err)
        _set_result(props, {"status": "invalid"}, certified=False,
                    error=message)
        add_error = getattr(props, "add_unexplained_error", None)
        if callable(add_error):
            add_error("dual selector trace: " + message)


def get_parser():
    from lab.parser import Parser

    parser = Parser()
    parser.add_function(parse_selector_trace, file=P.SELECTOR_TRACE)
    return parser
