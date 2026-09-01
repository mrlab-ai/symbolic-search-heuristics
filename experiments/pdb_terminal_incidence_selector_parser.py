#!/usr/bin/env python3
"""Certify the prospective guided/matched terminal-incidence trace."""

from __future__ import annotations

import hashlib
import base64
import binascii
import json
import math
import re


TRACE_SCHEMA = "symbolic-search-heuristics/terminal-incidence-selector-trace/v3"
TRACE_PROTOCOL = "terminal_incidence_fixed_pool_v1"
SCORE_VERSION = (
    "strongest_incidence_feasible_cap_then_"
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
)
GUIDED = "pdb_terminal_incidence_guided"
MATCHED = "pdb_terminal_incidence_matched"
SELECTOR_ALGORITHMS = {GUIDED, MATCHED}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
INT_MAX = 2**31 - 1
LONG_MAX = 2**63 - 1
CAP_GRID = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, None]
SCHEMA_EVENT = {
    "event": "schema",
    "schema": TRACE_SCHEMA,
    "version": 3,
    "probe_layers": 16,
    "reference_cofactor_width_budget": 32,
    "candidate_sources": [
        "empty", "bdd_prefix", "goal_prefix", "goal_fill", "cegar",
    ],
    "value_cap_grid": [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, "exact"],
    "pool_hash_encoding": "sources-pattern-states-feasible-lines-v1",
    "preselection_hash_encoding": "candidate-structural-lines-v3",
    "incidence_budget": (
        "sum-first-16-completed-blind-layers-of-reference-v1"
    ),
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
    "cofactor_width", "width_upper_bound", "terminal_incidence_by_layer",
    "raw_max_finite_value", "raw_value_histogram", "terminal_incidence",
    "reference_feasible",
    "incidence_feasible", "retained_for_pattern",
}


class TraceError(RuntimeError):
    pass


def _same_json_value(actual, expected) -> bool:
    """Compare parsed JSON recursively without numeric type coercion."""
    if type(actual) is not type(expected):
        return False
    if isinstance(expected, dict):
        return set(actual) == set(expected) and all(
            _same_json_value(actual[key], value)
            for key, value in expected.items()
        )
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(
            _same_json_value(left, right)
            for left, right in zip(actual, expected)
        )
    return actual == expected


def _duplicate_safe_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise TraceError("selector trace JSON object has a duplicate key")
        value[key] = item
    return value


def _load_events(content: str) -> list[dict]:
    if not content:
        return []
    if not content.endswith("\n") or "\r" in content:
        raise TraceError("selector trace is not newline-terminated UTF-8 JSONL")
    events = []
    for number, line in enumerate(content.splitlines(), 1):
        if not line:
            raise TraceError("selector trace contains an empty line")
        try:
            event = json.loads(line, object_pairs_hook=_duplicate_safe_object)
        except (json.JSONDecodeError, TraceError) as err:
            raise TraceError(
                "selector trace line {} is invalid JSON".format(number)
            ) from err
        if not isinstance(event, dict):
            raise TraceError("selector trace event is not an object")
        events.append(event)
    return events


def _finite_nonnegative(value, label: str) -> None:
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise TraceError("{} is not finite and nonnegative".format(label))


def _int_list(
    value, label: str, *, nonnegative: bool = True, maximum: int | None = None
) -> None:
    if not isinstance(value, list) or any(
        type(item) is not int
        or (nonnegative and item < 0)
        or (maximum is not None and item > maximum)
        for item in value
    ):
        raise TraceError("{} is not an integer list".format(label))


def _validate_probe(event: dict) -> dict:
    if set(event) != PROBE_KEYS or event.get("event") != "probe":
        raise TraceError("selector probe field set changed")
    completed = event["completed_layers"]
    attempts = event["attempts"]
    complete = event["complete"]
    if any((
        type(event["target_layers"]) is not int,
        event["target_layers"] != 16,
        type(completed) is not int,
        not 0 <= completed <= 16,
        type(attempts) is not int,
        attempts < completed,
        attempts > INT_MAX,
        type(complete) is not bool,
        complete != (completed == 16),
    )):
        raise TraceError("selector probe cardinality changed")
    _int_list(event["g_values"], "probe g values", maximum=INT_MAX)
    _int_list(event["bdd_nodes"], "probe BDD nodes", maximum=LONG_MAX)
    if (
        len(event["g_values"]) != completed
        or len(event["bdd_nodes"]) != completed
        or any(left >= right for left, right in zip(
            event["g_values"], event["g_values"][1:]
        ))
    ):
        raise TraceError("selector probe layer sequence changed")
    for field in ("cpu_seconds", "wall_seconds"):
        _finite_nonnegative(event[field], "probe {}".format(field))
    for field in (
        "peak_memory_before_kb", "peak_memory_after_kb",
        "peak_memory_delta_kb",
    ):
        if (
            type(event[field]) is not int
            or not 0 <= event[field] <= INT_MAX
        ):
            raise TraceError("selector probe memory is invalid")
    if event["peak_memory_delta_kb"] != max(
        0, event["peak_memory_after_kb"] - event["peak_memory_before_kb"]
    ):
        raise TraceError("selector probe memory delta changed")
    return {
        key: value for key, value in event.items()
        if key not in {
            "cpu_seconds", "wall_seconds", "peak_memory_before_kb",
            "peak_memory_after_kb", "peak_memory_delta_kb",
        }
    }


def _sha256_text(payload: str) -> str:
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


def _decode_raw_value_histogram(value: str) -> list[tuple[int, int]]:
    if (
        not isinstance(value, str)
        or not value
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
        or len(value) % 4 == 1
    ):
        raise TraceError("selector raw value histogram encoding changed")
    padded = value + "=" * (-len(value) % 4)
    try:
        raw = base64.b64decode(
            padded.encode("ascii"), altchars=b"-_", validate=True
        )
    except (ValueError, binascii.Error) as err:
        raise TraceError("selector raw value histogram encoding changed") from err
    if base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii") != value:
        raise TraceError("selector raw value histogram is not canonical")

    index = 0

    def read_varint() -> int:
        nonlocal index
        start = index
        result = 0
        shift = 0
        while True:
            if index >= len(raw) or shift >= 63:
                raise TraceError("selector raw value histogram varint changed")
            byte = raw[index]
            index += 1
            result |= (byte & 0x7f) << shift
            if not byte & 0x80:
                encoded = []
                remainder = result
                while True:
                    item = remainder & 0x7f
                    remainder >>= 7
                    encoded.append(item | (0x80 if remainder else 0))
                    if not remainder:
                        break
                if bytes(encoded) != raw[start:index]:
                    raise TraceError(
                        "selector raw value histogram varint is not canonical"
                    )
                return result
            shift += 7

    entries = read_varint()
    if entries > 100000:
        raise TraceError("selector raw value histogram cardinality changed")
    histogram = []
    previous = -1
    total_count = 0
    for _ in range(entries):
        delta = read_varint()
        count = read_varint()
        distance = previous + delta
        if (
            delta <= 0
            or count <= 0
            or distance < 0
            or distance > 2147483646
        ):
            raise TraceError("selector raw value histogram entry changed")
        histogram.append((distance, count))
        total_count += count
        if total_count > 100000:
            raise TraceError("selector raw value histogram count changed")
        previous = distance
    if index != len(raw):
        raise TraceError("selector raw value histogram has trailing bytes")
    return histogram


def _transformed_terminal_count(
    histogram: list[tuple[int, int]], dead_count: int, cap: int | None
) -> int:
    """Reconstruct the number of terminals in the transformed reduced ADD."""
    finite_values = {
        value if cap is None else min(value, cap)
        for value, _ in histogram
    }
    return len(finite_values) + int(dead_count > 0)


def _validate_pool(event: dict) -> tuple[str, list[dict]]:
    if set(event) != {
        "event", "protocol", "state_budget", "pool_sha256", "patterns"
    } or any((
        event.get("event") != "pool",
        event.get("protocol") != TRACE_PROTOCOL,
        type(event.get("state_budget")) is not int,
        event.get("state_budget") != 100000,
        SHA256_RE.fullmatch(event.get("pool_sha256", "")) is None,
        not isinstance(event.get("patterns"), list),
        not event.get("patterns"),
    )):
        raise TraceError("selector pool header changed")
    payload = []
    source_occurrences = []
    pattern_vectors = set()
    for index, pattern in enumerate(event["patterns"]):
        if not isinstance(pattern, dict) or set(pattern) != {
            "pattern_index", "sources", "pattern", "abstract_states",
            "within_state_budget",
        }:
            raise TraceError("selector pool pattern field set changed")
        sources = pattern["sources"]
        variables = pattern["pattern"]
        states = pattern["abstract_states"]
        within = pattern["within_state_budget"]
        if any((
            type(pattern["pattern_index"]) is not int,
            pattern["pattern_index"] != index,
            not isinstance(sources, list),
            not sources,
            any(source not in SCHEMA_EVENT["candidate_sources"]
                for source in sources),
            sources != sorted(set(sources), key=(
                SCHEMA_EVENT["candidate_sources"].index
            )),
            not isinstance(variables, list),
            any(
                type(var) is not int or not 0 <= var <= INT_MAX
                for var in variables
            ),
            variables != sorted(set(variables)),
            type(states) is not int,
            not 1 <= states <= INT_MAX,
            type(within) is not bool,
            within != (states <= 100000),
        )):
            raise TraceError("selector pool pattern is invalid")
        vector = tuple(variables)
        if vector in pattern_vectors:
            raise TraceError("selector pool contains a duplicate pattern")
        pattern_vectors.add(vector)
        source_occurrences.extend(sources)
        payload.append(
            "{}|sources={}|pattern={}|abstract_states={}|"
            "within_state_budget={}\n".format(
                index, ",".join(sources),
                ",".join(map(str, variables)), states, int(within),
            )
        )
    if (
        len(source_occurrences) != len(SCHEMA_EVENT["candidate_sources"])
        or any(
            source_occurrences.count(source) != 1
            for source in SCHEMA_EVENT["candidate_sources"]
        )
    ):
        raise TraceError("selector fixed pool omitted a generator source")
    empty_patterns = [
        pattern for pattern in event["patterns"] if pattern["pattern"] == []
    ]
    if (
        len(empty_patterns) != 1
        or empty_patterns[0]["pattern_index"] != 0
        or empty_patterns[0]["abstract_states"] != 1
        or empty_patterns[0]["within_state_budget"] is not True
        or "empty" not in empty_patterns[0]["sources"]
        or any(
            "empty" in pattern["sources"] and pattern["pattern"] != []
            for pattern in event["patterns"]
        )
    ):
        raise TraceError("selector fixed pool mandatory empty pattern changed")
    if _sha256_text("".join(payload)) != event["pool_sha256"]:
        raise TraceError("selector pool SHA-256 does not match its records")
    return event["pool_sha256"], event["patterns"]


def _candidate_line(event: dict) -> str:
    cap = "exact" if event["value_cap"] is None else str(event["value_cap"])
    initial_h = "null" if event["initial_h"] is None else str(event["initial_h"])
    histogram = (
        "null" if event["raw_value_histogram"] is None
        else event["raw_value_histogram"]
    )
    return (
        "{pattern_index}|cap={cap}|initial_dead_end={initial_dead_end}|"
        "initial_h={initial_h}|finite_sum={finite_sum}|"
        "finite_count={finite_count}|dead_count={dead_count}|"
        "cofactor_width={cofactor_width}|width_upper_bound={width_upper_bound}|"
        "raw_max_finite_value={raw_max_finite_value}|"
        "raw_value_histogram={raw_value_histogram}|"
        "incidence={incidence}|incidence_total={terminal_incidence}|"
        "reference_feasible={reference_feasible}\n"
    ).format(**{
        **event,
        "cap": cap,
        "initial_h": initial_h,
        "raw_value_histogram": histogram,
        "initial_dead_end": int(event["initial_dead_end"]),
        "incidence": ",".join(map(str, event["terminal_incidence_by_layer"])),
        "reference_feasible": int(event["reference_feasible"]),
    })


def _validate_candidate(event: dict, patterns: list[dict]) -> None:
    if set(event) != CANDIDATE_KEYS or any((
        event.get("event") != "candidate",
        event.get("protocol") != TRACE_PROTOCOL,
        event.get("score_version") != SCORE_VERSION,
        type(event.get("pattern_index")) is not int,
        not 0 <= event.get("pattern_index", -1) < len(patterns),
    )):
        raise TraceError("selector candidate header changed")
    pattern = patterns[event["pattern_index"]]
    if any((
        not isinstance(event["sources"], list),
        any(not isinstance(source, str) for source in event["sources"]),
        event["sources"] != pattern["sources"],
        event["pattern"] != pattern["pattern"],
        type(event["abstract_states"]) is not int,
        event["abstract_states"] != pattern["abstract_states"],
        event["value_cap"] is not None
        and type(event["value_cap"]) is not int,
        event["value_cap"] not in CAP_GRID,
        type(event["initial_dead_end"]) is not bool,
        event["initial_h"] is not None
        and (type(event["initial_h"]) is not int or event["initial_h"] < 0),
        event["initial_dead_end"] != (event["initial_h"] is None),
        any(type(event[field]) is not int or event[field] < 0 for field in (
            "finite_sum", "finite_count", "dead_count", "cofactor_width",
            "width_upper_bound", "raw_max_finite_value",
            "terminal_incidence",
        )),
        event["finite_sum"] > LONG_MAX,
        any(event[field] > INT_MAX for field in (
            "finite_count", "dead_count", "raw_max_finite_value",
        )),
        any(event[field] > LONG_MAX for field in (
            "cofactor_width", "width_upper_bound", "terminal_incidence",
        )),
        event["cofactor_width"] < 1,
        event["cofactor_width"] > event["width_upper_bound"],
        any(type(event[field]) is not bool for field in (
            "reference_feasible", "incidence_feasible",
            "retained_for_pattern",
        )),
        event["reference_feasible"] != (event["cofactor_width"] <= 32),
        event["finite_count"] + event["dead_count"]
        != event["abstract_states"],
        event["finite_count"] == 0 and event["finite_sum"] != 0,
        event["finite_count"] == 0 and not event["initial_dead_end"],
        event["initial_dead_end"] and event["dead_count"] == 0,
        event["initial_h"] is not None and event["finite_count"] == 0,
    )):
        raise TraceError("selector candidate identity or scalar changed")
    _int_list(event["pattern"], "candidate pattern", maximum=INT_MAX)
    _int_list(
        event["terminal_incidence_by_layer"],
        "candidate terminal-incidence layers",
        maximum=LONG_MAX,
    )
    if (
        len(event["terminal_incidence_by_layer"]) != 16
        or sum(event["terminal_incidence_by_layer"])
        != event["terminal_incidence"]
    ):
        raise TraceError("selector candidate incidence total changed")
    if event["raw_value_histogram"] is not None:
        histogram = _decode_raw_value_histogram(event["raw_value_histogram"])
        if sum(count for _, count in histogram) > event["abstract_states"]:
            raise TraceError("selector raw value histogram exceeds state count")


def _identity(event: dict, prefix: str) -> dict:
    value = {
        "pattern_index": event[prefix + "pattern_index"],
        "sources": event[prefix + "sources"],
        "pattern": event[prefix + "pattern"],
        "value_cap": event[prefix + "value_cap"],
        "terminal_incidence": event[prefix + "terminal_incidence"],
    }
    if any((
        type(value["pattern_index"]) is not int,
        not isinstance(value["sources"], list),
        not value["sources"],
        any(not isinstance(source, str) or not source
            for source in value["sources"]),
        value["value_cap"] is not None
        and type(value["value_cap"]) is not int,
        value["value_cap"] not in CAP_GRID,
        type(value["terminal_incidence"]) is not int,
        not 0 <= value["terminal_incidence"] <= LONG_MAX,
    )):
        raise TraceError("selector logged identity has invalid scalar fields")
    _int_list(
        value["pattern"], "selector logged identity pattern", maximum=INT_MAX
    )
    return value


def _candidate_identity(event: dict) -> dict:
    return {
        "pattern_index": event["pattern_index"],
        "sources": event["sources"],
        "pattern": event["pattern"],
        "value_cap": event["value_cap"],
        "terminal_incidence": event["terminal_incidence"],
    }


def _compare_ratio(
    lhs_num: int,
    lhs_den: int,
    rhs_num: int,
    rhs_den: int,
    *,
    zero_denominator_is_infinity: bool,
) -> int:
    """Return the exact sign of the frozen C++ ratio comparison."""
    if zero_denominator_is_infinity and (lhs_den == 0 or rhs_den == 0):
        if lhs_den == rhs_den:
            return 0
        return 1 if lhs_den == 0 else -1
    lhs = lhs_num * rhs_den
    rhs = rhs_num * lhs_den
    return (lhs > rhs) - (lhs < rhs)


def _candidate_is_better(candidate: dict, incumbent: dict) -> bool:
    """Mirror wbh_pdb_levels.cc::candidate_is_better byte-for-byte in order."""
    if candidate["initial_dead_end"] != incumbent["initial_dead_end"]:
        return candidate["initial_dead_end"]
    if (
        not candidate["initial_dead_end"]
        and candidate["initial_h"] != incumbent["initial_h"]
    ):
        return candidate["initial_h"] > incumbent["initial_h"]
    mean_comparison = _compare_ratio(
        candidate["finite_sum"], candidate["finite_count"],
        incumbent["finite_sum"], incumbent["finite_count"],
        zero_denominator_is_infinity=True,
    )
    if mean_comparison:
        return mean_comparison > 0
    dead_fraction_comparison = _compare_ratio(
        candidate["dead_count"], candidate["abstract_states"],
        incumbent["dead_count"], incumbent["abstract_states"],
        zero_denominator_is_infinity=False,
    )
    if dead_fraction_comparison:
        return dead_fraction_comparison > 0
    if candidate["cofactor_width"] != incumbent["cofactor_width"]:
        return candidate["cofactor_width"] < incumbent["cofactor_width"]
    if candidate["abstract_states"] != incumbent["abstract_states"]:
        return candidate["abstract_states"] < incumbent["abstract_states"]
    return candidate["pattern"] < incumbent["pattern"]


def _best_candidate(candidates: list[dict]) -> dict:
    if not candidates:
        raise TraceError("selector candidate set is unexpectedly empty")
    winner = candidates[0]
    for candidate in candidates[1:]:
        if _candidate_is_better(candidate, winner):
            winner = candidate
    return winner


def _validate_complete(events: list[dict], algorithm: str, probe: dict) -> dict:
    kinds = [event.get("event") for event in events]
    if (
        len(events) < 8
        or kinds[:3] != ["schema", "probe", "pool"]
        or kinds[-4:] != [
            "preselection", "reference", "selected", "selection_accounting"
        ]
        or any(kind != "candidate" for kind in kinds[3:-4])
    ):
        raise TraceError("complete selector trace event order changed")
    pool_sha, patterns = _validate_pool(events[2])
    candidates = events[3:-4]
    for candidate in candidates:
        _validate_candidate(candidate, patterns)
        if any(
            incidence < frontier_nodes
            for incidence, frontier_nodes in zip(
                candidate["terminal_incidence_by_layer"], probe["bdd_nodes"]
            )
        ):
            raise TraceError(
                "selector candidate incidence is below the probe frontier"
            )
    by_pattern = {}
    for candidate in candidates:
        by_pattern.setdefault(candidate["pattern_index"], []).append(candidate)
    expected_pattern_indexes = {
        pattern["pattern_index"] for pattern in patterns
        if pattern["within_state_budget"]
    }
    if set(by_pattern) != expected_pattern_indexes:
        raise TraceError("selector candidate coverage of the pool changed")
    empty_variants = by_pattern.get(0, [])
    if len(empty_variants) != 1:
        raise TraceError("selector mandatory empty candidate changed")
    empty = empty_variants[0]
    empty_expected = {
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
        "terminal_incidence_by_layer": probe["bdd_nodes"],
        "terminal_incidence": sum(probe["bdd_nodes"]),
        "reference_feasible": True,
        "incidence_feasible": True,
        "retained_for_pattern": True,
    }
    if any(empty.get(field) != value for field, value in empty_expected.items()):
        raise TraceError("selector mandatory empty candidate changed")
    if [item["pattern_index"] for item in candidates] != sorted(
        item["pattern_index"] for item in candidates
    ):
        raise TraceError("selector candidates are not in pool-pattern order")
    for pattern_index, variants in by_pattern.items():
        caps = [item["value_cap"] for item in variants]
        exact = variants[-1]
        raw_max = exact["raw_max_finite_value"]
        histogram = _decode_raw_value_histogram(
            exact["raw_value_histogram"]
        )
        histogram_count = sum(count for _, count in histogram)
        histogram_sum = sum(value * count for value, count in histogram)
        histogram_max = histogram[-1][0] if histogram else 0
        expected_caps = [
            cap for cap in CAP_GRID[:-1] if cap < raw_max
        ] + [None]
        if (
            len(caps) != len(set(caps))
            or caps != expected_caps
            or any(
                variant["raw_max_finite_value"] != raw_max
                for variant in variants
            )
            or any(
                (variant["value_cap"] is None)
                != isinstance(variant["raw_value_histogram"], str)
                for variant in variants
            )
            or exact["finite_count"] != histogram_count
            or exact["dead_count"]
            != exact["abstract_states"] - histogram_count
            or exact["finite_sum"] != histogram_sum
            or raw_max != histogram_max
            or (
                exact["initial_h"] is not None
                and exact["initial_h"] not in dict(histogram)
            )
        ):
            raise TraceError("selector candidate cap prefix changed")
        raw_invariants = (
            exact["finite_count"],
            exact["dead_count"],
            exact["initial_dead_end"],
            exact["raw_max_finite_value"],
        )
        previous_incidence_by_layer = None
        previous_cofactor_width = None
        previous_width_upper_bound = None
        for variant in variants:
            if (
                (
                    variant["finite_count"],
                    variant["dead_count"],
                    variant["initial_dead_end"],
                    variant["raw_max_finite_value"],
                ) != raw_invariants
            ):
                raise TraceError("selector cross-cap raw invariants changed")
            incidence_by_layer = variant["terminal_incidence_by_layer"]
            if (
                previous_incidence_by_layer is not None
                and any(
                    current < previous
                    for current, previous in zip(
                        incidence_by_layer, previous_incidence_by_layer
                    )
                )
            ):
                raise TraceError(
                    "selector cross-cap terminal incidence is not monotone"
                )
            previous_incidence_by_layer = incidence_by_layer
            if (
                previous_cofactor_width is not None
                and (
                    variant["cofactor_width"] < previous_cofactor_width
                    or variant["width_upper_bound"]
                    < previous_width_upper_bound
                )
            ):
                raise TraceError(
                    "selector cross-cap widths are not monotone"
                )
            previous_cofactor_width = variant["cofactor_width"]
            previous_width_upper_bound = variant["width_upper_bound"]
            cap = variant["value_cap"]
            expected_finite_sum = sum(
                (value if cap is None else min(value, cap)) * count
                for value, count in histogram
            )
            expected_initial_h = (
                None if exact["initial_dead_end"]
                else exact["initial_h"] if cap is None
                else min(exact["initial_h"], cap)
            )
            num_terminals = _transformed_terminal_count(
                histogram, variant["dead_count"], cap
            )
            if (
                variant["finite_count"] != histogram_count
                or variant["dead_count"]
                != variant["abstract_states"] - histogram_count
                or variant["finite_sum"] != expected_finite_sum
                or variant["initial_h"] != expected_initial_h
            ):
                raise TraceError(
                    "selector capped candidate does not reconstruct from raw histogram"
                )
            if (
                variant["cofactor_width"] < num_terminals
                or variant["width_upper_bound"]
                < variant["cofactor_width"] + num_terminals - 1
            ):
                raise TraceError(
                    "selector candidate ADD widths are impossible for its terminals"
                )
            if num_terminals == 1 and (
                variant["cofactor_width"] != 1
                or variant["width_upper_bound"] != 1
                or incidence_by_layer != probe["bdd_nodes"]
            ):
                raise TraceError(
                    "selector constant candidate ADD structure changed"
                )
            if cap is None:
                continue

    preselection, reference, selected, accounting = events[-4:]
    if set(preselection) != {
        "event", "pool_sha256", "preselection_sha256", "candidate_count"
    } or any((
        preselection["event"] != "preselection",
        preselection["pool_sha256"] != pool_sha,
        SHA256_RE.fullmatch(preselection.get("preselection_sha256", ""))
        is None,
        type(preselection["candidate_count"]) is not int,
        preselection["candidate_count"] != len(candidates),
        _sha256_text("".join(map(_candidate_line, candidates)))
        != preselection["preselection_sha256"],
    )):
        raise TraceError("selector preselection attestation changed")
    pre_sha = preselection["preselection_sha256"]
    reference_keys = {
        "event", "pool_sha256", "preselection_sha256",
        "reference_pattern_index", "reference_sources", "reference_pattern",
        "reference_value_cap", "reference_terminal_incidence",
        "reference_cofactor_width_budget", "incidence_budget",
    }
    selected_keys = {
        "event", "decision_mode", "pool_sha256", "preselection_sha256",
        "selected_pattern_index", "selected_sources", "selected_pattern",
        "selected_value_cap", "selected_terminal_incidence",
        "incidence_budget",
    }
    if set(reference) != reference_keys or any((
        reference["event"] != "reference",
        reference["pool_sha256"] != pool_sha,
        reference["preselection_sha256"] != pre_sha,
        type(reference["reference_cofactor_width_budget"]) is not int,
        reference["reference_cofactor_width_budget"] != 32,
        type(reference["incidence_budget"]) is not int,
        not 0 <= reference["incidence_budget"] <= LONG_MAX,
    )):
        raise TraceError("selector reference event changed")
    reference_identity = _identity(reference, "reference_")
    matches = [item for item in candidates
               if _candidate_identity(item) == reference_identity]
    if len(matches) != 1 or not matches[0]["reference_feasible"]:
        raise TraceError("selector reference does not identify one candidate")
    reference_representatives = []
    for variants in by_pattern.values():
        feasible = [
            item for item in variants if item["reference_feasible"]
        ]
        if feasible:
            reference_representatives.append(feasible[-1])
    expected_reference = _best_candidate(reference_representatives)
    if reference_identity != _candidate_identity(expected_reference):
        raise TraceError("selector reference is not the frozen C++ winner")
    budget = reference["incidence_budget"]
    if reference_identity["terminal_incidence"] != budget:
        raise TraceError("selector reference incidence budget changed")
    guided_representatives = []
    for pattern_index, variants in by_pattern.items():
        feasible = [item for item in variants
                    if item["terminal_incidence"] <= budget]
        if any(item["incidence_feasible"] != (
            item["terminal_incidence"] <= budget
        ) for item in variants):
            raise TraceError("selector incidence-feasibility flag changed")
        retained = [item for item in variants if item["retained_for_pattern"]]
        if retained != ([feasible[-1]] if feasible else []):
            raise TraceError("selector per-pattern retained cap changed")
        if feasible:
            guided_representatives.append(feasible[-1])
    expected_guided = _best_candidate(guided_representatives)

    expected_mode = "guided" if algorithm == GUIDED else "matched_control"
    if set(selected) != selected_keys or any((
        selected["event"] != "selected",
        selected["decision_mode"] != expected_mode,
        selected["pool_sha256"] != pool_sha,
        selected["preselection_sha256"] != pre_sha,
        type(selected["incidence_budget"]) is not int,
        selected["incidence_budget"] != budget,
    )):
        raise TraceError("selector selected event changed")
    selected_identity = _identity(selected, "selected_")
    selected_matches = [item for item in candidates
                        if _candidate_identity(item) == selected_identity]
    if len(selected_matches) != 1 or not selected_matches[0][
        "incidence_feasible"
    ]:
        raise TraceError("selector selected identity is not feasible")
    if algorithm == MATCHED and selected_identity != reference_identity:
        raise TraceError("matched control did not select its reference")
    if (
        algorithm == GUIDED
        and selected_identity != _candidate_identity(expected_guided)
    ):
        raise TraceError("guided selector did not select the frozen C++ winner")
    if set(accounting) != {
        "event", "cpu_seconds", "wall_seconds", "peak_memory_before_kb",
        "peak_memory_after_kb", "peak_memory_delta_kb",
    } or accounting.get("event") != "selection_accounting":
        raise TraceError("selector accounting field set changed")
    for field in ("cpu_seconds", "wall_seconds"):
        _finite_nonnegative(accounting[field], "selection {}".format(field))
    for field in (
        "peak_memory_before_kb", "peak_memory_after_kb",
        "peak_memory_delta_kb",
    ):
        if (
            type(accounting[field]) is not int
            or not 0 <= accounting[field] <= INT_MAX
        ):
            raise TraceError("selector accounting memory is invalid")
    if accounting["peak_memory_delta_kb"] != max(
        0, accounting["peak_memory_after_kb"]
        - accounting["peak_memory_before_kb"]
    ):
        raise TraceError("selector accounting memory delta changed")
    structural = [events[0], probe, events[2], *candidates,
                  preselection, reference]
    structural_sha = hashlib.sha256(
        json.dumps(
            structural, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    ).hexdigest()
    return {
        "status": "complete",
        "pool_sha256": pool_sha,
        "preselection_sha256": pre_sha,
        "structural_trace": structural,
        "structural_trace_sha256": structural_sha,
        "reference_identity": reference_identity,
        "selected_identity": selected_identity,
        "selected_differs_from_reference": (
            selected_identity != reference_identity
        ),
        "probe_completed_layers": 16,
        "probe_cpu_seconds": events[1]["cpu_seconds"],
        "probe_wall_seconds": events[1]["wall_seconds"],
        "probe_peak_memory_before_kb": events[1]["peak_memory_before_kb"],
        "probe_peak_memory_after_kb": events[1]["peak_memory_after_kb"],
        "probe_peak_memory_delta_kb": events[1]["peak_memory_delta_kb"],
        "selection_cpu_seconds": accounting["cpu_seconds"],
        "selection_wall_seconds": accounting["wall_seconds"],
        "selection_peak_memory_before_kb": accounting[
            "peak_memory_before_kb"
        ],
        "selection_peak_memory_after_kb": accounting[
            "peak_memory_after_kb"
        ],
        "selection_peak_memory_delta_kb": accounting[
            "peak_memory_delta_kb"
        ],
    }


def _set_result(props, result: dict, *, certified: bool, error=None) -> None:
    props["incidence_selector_trace_schema"] = TRACE_SCHEMA
    props["incidence_selector_trace_status"] = result.get("status")
    props["incidence_selector_trace_certified"] = certified
    props["incidence_selector_trace_validation_error"] = error
    for key, value in result.items():
        if key != "status":
            props["incidence_selector_" + key] = value


def parse_selector_trace(content, props) -> None:
    algorithm = props.get("algorithm")
    selector = algorithm in SELECTOR_ALGORITHMS
    if not selector:
        if content:
            message = "non-selector run produced a selector trace"
            _set_result(props, {"status": "unexpected"}, certified=False,
                        error=message)
            add_error = getattr(props, "add_unexplained_error", None)
            if callable(add_error):
                add_error(message)
        else:
            _set_result(props, {"status": "not_applicable"}, certified=True)
        return
    try:
        events = _load_events(content)
        if not events or not _same_json_value(events[0], SCHEMA_EVENT):
            raise TraceError("selector schema event changed or is absent")
        if len(events) < 2:
            result = {"status": "partial", "event_count": len(events)}
            _set_result(props, result, certified=False,
                        error="selector trace ended before the probe")
            return
        probe = _validate_probe(events[1])
        if not events[1]["complete"]:
            if len(events) != 2:
                raise TraceError("incomplete probe has trailing selector events")
            result = {
                "status": "short_probe",
                "structural_trace": [events[0], probe],
                "structural_trace_sha256": hashlib.sha256(json.dumps(
                    [events[0], probe], sort_keys=True, separators=(",", ":"),
                    ensure_ascii=True, allow_nan=False,
                ).encode("ascii")).hexdigest(),
                "probe_completed_layers": events[1]["completed_layers"],
                "probe_cpu_seconds": events[1]["cpu_seconds"],
                "probe_wall_seconds": events[1]["wall_seconds"],
                "probe_peak_memory_before_kb": events[1][
                    "peak_memory_before_kb"
                ],
                "probe_peak_memory_after_kb": events[1][
                    "peak_memory_after_kb"
                ],
                "probe_peak_memory_delta_kb": events[1][
                    "peak_memory_delta_kb"
                ],
                "pool_sha256": None,
                "preselection_sha256": None,
                "reference_identity": None,
                "selected_identity": None,
                "selected_differs_from_reference": False,
            }
            if any((
                type(props.get("planner_exit_code")) is not int,
                props.get("planner_exit_code") != 34,
                type(props.get("coverage")) is not int,
                props.get("coverage") != 0,
            )):
                raise TraceError("short probe is not paired with exit code 34")
            _set_result(props, result, certified=True)
            return
        if (
            type(props.get("planner_exit_code")) is not int
            or type(props.get("coverage")) is not int
            or props.get("coverage") not in (0, 1)
        ):
            raise TraceError("complete selector trace has malformed outcome metadata")
        if props.get("planner_exit_code") == 34:
            raise TraceError("complete selector trace is paired with exit code 34")
        result = _validate_complete(events, algorithm, probe)
        _set_result(props, result, certified=True)
    except TraceError as err:
        message = str(err)
        _set_result(props, {"status": "invalid"}, certified=False,
                    error=message)
        add_error = getattr(props, "add_unexplained_error", None)
        if callable(add_error):
            add_error("terminal-incidence selector trace: " + message)


def get_parser():
    from lab.parser import Parser

    parser = Parser()
    parser.add_function(parse_selector_trace, file="incidence-selector.jsonl")
    return parser
