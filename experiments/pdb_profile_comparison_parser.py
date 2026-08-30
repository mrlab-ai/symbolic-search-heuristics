#!/usr/bin/env python3
"""Parsers for the new profile stream and total-ADD selector trace."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
import re
from collections import defaultdict
from fractions import Fraction


PROFILE_PARSER_PROTOCOL = "wbh-complete-cofactor-profile-jsonl-v1"
SELECTOR_PARSER_PROTOCOL = "pdb-width-or-total-add-selector-trace-v1"
EXPANSION_PARSER_PROTOCOL = "wbh-schema-v2-active-values-by-g-v1"
PROFILE_FILE = "wbh-profile.jsonl"
SOURCE_ORDER = ("empty", "bdd_prefix", "goal_prefix", "goal_fill", "cegar")
WIDTH_PROTOCOLS = {
    "fixed_pool_v1",
    "fixed_pool_value_cap_v2",
    "fixed_pool_cap_grid_v6",
}
ADD_PROTOCOLS = {
    "fixed_pool_total_add_v1",
    "fixed_pool_total_add_value_cap_v1",
    "fixed_pool_total_add_cap_grid_v1",
}
CAP_GRID_PROTOCOLS = {
    "fixed_pool_cap_grid_v6",
    "fixed_pool_total_add_cap_grid_v1",
}
WIDTH_SCORE = "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
CAPPED_WIDTH_SCORE = (
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_value_cap_v2"
)
CAP_GRID_SCORE = (
    "per_pattern_strongest_feasible_cap_then_"
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
)
PROTOCOL_SCORES = {
    "fixed_pool_v1": WIDTH_SCORE,
    "fixed_pool_value_cap_v2": CAPPED_WIDTH_SCORE,
    "fixed_pool_cap_grid_v6": CAP_GRID_SCORE,
    "fixed_pool_total_add_v1": WIDTH_SCORE,
    "fixed_pool_total_add_value_cap_v1": CAPPED_WIDTH_SCORE,
    "fixed_pool_total_add_cap_grid_v1": CAP_GRID_SCORE,
}
_LOG_PREFIX = r"(?:\[t=(?:0|[1-9]\d*)\.\d{6}s, (?:0|[1-9]\d*) KB\] )?"
SELECTOR_RE = re.compile(
    r"^" + _LOG_PREFIX
    + r"PDB (width|add)-selector v1 (candidate|selected): (\{.*\})$"
)
FINAL_RE = re.compile(
    r"^" + _LOG_PREFIX
    + r"wbh PDB heuristic: pattern_size=(0|[1-9]\d*), "
    r"selected_source=([a-z_]+), abstract_states=(0|[1-9]\d*), "
    r"(cofactor_width_budget|total_add_node_budget)=(0|[1-9]\d*)"
    r"(?:, value_cap=(0|[1-9]\d*|-[1-9]\d*))?, "
    r"values=(0|[1-9]\d*), cofactor_width=(0|[1-9]\d*), "
    r"width_upper_bound=(0|[1-9]\d*)$"
)
CAP_GRID = (0, 1, 2, 4, 8, 16, 32, 64, 128, 256)
INT_MAX = 2147483647
INT64_MAX = 9223372036854775807
MAX_ABSTRACT_STATES = 100000
MAX_HISTOGRAM_BYTES = 800003
MAX_HISTOGRAM_BASE64 = (MAX_HISTOGRAM_BYTES * 4 + 2) // 3
HISTOGRAM_WIRE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
HISTOGRAM_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
BASE_SELECTOR_KEYS = (
    "protocol",
    "score_version",
    "sources",
    "pattern",
    "abstract_states",
    "initial_dead_end",
    "initial_h",
    "finite_sum",
    "finite_count",
    "dead_count",
    "cofactor_width",
    "width_upper_bound",
    "feasible",
    "rejection_reason",
)
CAP_SELECTOR_KEYS = (
    "value_cap",
    "add_nodes",
    "num_terminals",
    "raw_add_nodes",
    "raw_num_terminals",
    "raw_cofactor_width",
    "raw_width_upper_bound",
    "raw_num_values",
    "raw_max_finite_value",
    "raw_finite_sum",
    "raw_finite_count",
    "raw_dead_count",
    "raw_initial_dead_end",
    "raw_initial_h",
    "transformed_num_values",
)
CAP_GRID_ONLY_KEYS = ("raw_initial_value_count", "raw_value_histogram")


class ParseError(RuntimeError):
    pass


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ParseError("duplicate JSON key {!r}".format(key))
        result[key] = value
    return result


def _load_json(text: str, label: str):
    def reject_constant(token):
        raise ParseError("{} contains nonfinite {}".format(label, token))

    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=reject_constant,
        )
    except ParseError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError, RecursionError) as err:
        raise ParseError("{} is invalid JSON: {}".format(label, err)) from err


def _int(value, label, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        raise ParseError("{} must be an integer{}".format(
            label, " >= {}".format(minimum) if minimum is not None else ""
        ))
    return value


def _number(value, label, minimum=None):
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ParseError("{} must be a finite number".format(label))
    if minimum is not None and value < minimum:
        raise ParseError("{} must be >= {}".format(label, minimum))
    return value


def _sha(value) -> str:
    raw = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _exact_keys(value, expected, label):
    if set(value) != set(expected):
        raise ParseError("{} keys changed".format(label))


def _profile_vector(value, state_bits, label):
    if (
        not isinstance(value, list)
        or len(value) != state_bits + 1
        or any(type(item) is not int or item < 1 for item in value)
    ):
        raise ParseError(
            "{} must have {} positive integer cuts".format(label, state_bits + 1)
        )
    if any(right > 2 * left for left, right in zip(value, value[1:])):
        raise ParseError("{} grows by more than one binary cut".format(label))
    return value


def parse_profile_stream(content: str) -> dict:
    if not content:
        raise ParseError("profile log is missing or empty")
    if len(content.encode("utf-8")) > 1024 * 1024 * 1024:
        raise ParseError("profile log exceeds 1 GiB")
    events = []
    for line_number, line in enumerate(content.splitlines(), 1):
        if not line:
            raise ParseError("profile log contains an empty line")
        event = _load_json(line, "profile line {}".format(line_number))
        if not isinstance(event, dict) or type(event.get("event")) is not str:
            raise ParseError("profile event is not an object with an event name")
        events.append(event)
    if not events:
        raise ParseError("profile stream is too short")
    schema = events[0]
    expected_schema = {
        "event": "schema",
        "version": 1,
        "cut_convention": (
            "unprimed_state_bits_in_cudd_level_order_including_terminal"
        ),
        "node_count_convention": "regular_cudd_inner_nodes_of_semantic_union",
        "residual_identity": (
            "canonical_signed_cudd_pointer_with_complement_polarity"
        ),
    }
    if schema != expected_schema:
        raise ParseError("profile schema event changed")
    if len(events) == 1:
        # The schema is flushed by the logger constructor.  A hard resource
        # exit before manager initialization may leave exactly this valid,
        # explicitly incomplete prefix.
        return {
            "complete": False,
            "schema_version": 1,
            "state_bits": None,
            "manager_variables": None,
            "variable_order_sha256": None,
            "heuristic_profile": None,
            "heuristic_paper_cuts": None,
            "layer_profiles": [],
            "layer_profile_attempts": 0,
            "completed_layer_profiles": 0,
            "done": None,
            "summary": None,
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        }
    order = events[1]
    if order.get("event") != "variable_order":
        raise ParseError("variable_order must be the second event")
    _exact_keys(
        order,
        {
            "event",
            "manager_variables",
            "state_bits",
            "cudd_indices",
            "cudd_levels",
            "fd_variables",
            "fd_bit_positions",
        },
        "variable_order",
    )
    state_bits = _int(order.get("state_bits"), "state_bits", 1)
    manager_variables = _int(
        order.get("manager_variables"), "manager_variables", 2 * state_bits
    )
    arrays = {}
    for field in ("cudd_indices", "cudd_levels", "fd_variables", "fd_bit_positions"):
        value = order.get(field)
        if (
            not isinstance(value, list)
            or len(value) != state_bits
            or any(type(item) is not int or item < 0 for item in value)
        ):
            raise ParseError("variable_order.{} is invalid".format(field))
        arrays[field] = value
    if len(set(arrays["cudd_indices"])) != state_bits:
        raise ParseError("CUDD indices are not unique")
    if (
        arrays["cudd_levels"] != sorted(arrays["cudd_levels"])
        or len(set(arrays["cudd_levels"])) != state_bits
        or any(level >= manager_variables for level in arrays["cudd_levels"])
    ):
        raise ParseError("state-bit CUDD levels are not unique increasing levels")
    if any(index >= manager_variables for index in arrays["cudd_indices"]):
        raise ParseError("CUDD index exceeds manager size")
    if len(set(zip(arrays["fd_variables"], arrays["fd_bit_positions"]))) != state_bits:
        raise ParseError("FD variable/bit identities are not unique")
    seen_fd_variables = set()
    previous_fd_variable = None
    positions_by_variable = {}
    for fd_variable, bit_position in zip(
        arrays["fd_variables"], arrays["fd_bit_positions"]
    ):
        if fd_variable != previous_fd_variable:
            if fd_variable in seen_fd_variables:
                raise ParseError("FD variable bits are not contiguous")
            seen_fd_variables.add(fd_variable)
            previous_fd_variable = fd_variable
        positions_by_variable.setdefault(fd_variable, []).append(bit_position)
    if any(
        positions != list(range(len(positions)))
        for positions in positions_by_variable.values()
    ):
        raise ParseError("FD bit positions are not canonical within variables")

    heuristic = None
    layers = []
    done = None
    summary = None
    phase = "body"
    for event in events[2:]:
        kind = event["event"]
        if summary is not None:
            raise ParseError("event follows profile summary")
        if kind == "heuristic_profile":
            if phase != "body" or heuristic is not None:
                raise ParseError("heuristic profile is duplicated or out of order")
            counts = _profile_vector(
                event.get("cofactor_counts"), state_bits, "heuristic profile"
            )
            _exact_keys(
                event,
                {
                    "event",
                    "add_nodes",
                    "num_values",
                    "num_terminals",
                    "cofactor_counts",
                    "cofactor_width",
                    "cofactor_seconds",
                },
                "heuristic_profile",
            )
            add_nodes = _int(event.get("add_nodes"), "heuristic add_nodes", 0)
            num_values = _int(event.get("num_values"), "heuristic num_values", 1)
            num_terminals = _int(
                event.get("num_terminals"), "heuristic num_terminals", 1
            )
            width = _int(event.get("cofactor_width"), "heuristic width", 1)
            if width != max(counts):
                raise ParseError("heuristic width disagrees with its profile")
            if (
                counts[0] != 1
                or counts[-1] != num_terminals
                or width > add_nodes + num_terminals
                or not 1 <= num_values <= num_terminals
                or num_terminals > add_nodes + 1
                or (add_nodes == 0) != (num_terminals == 1)
            ):
                raise ParseError("heuristic profile violates ADD residual identities")
            _number(event.get("cofactor_seconds"), "heuristic cofactor time", 0)
            heuristic = event
        elif kind == "layer_profile":
            if phase != "body":
                raise ParseError("layer profile follows done")
            counts = _profile_vector(
                event.get("cofactor_counts"), state_bits, "layer profile"
            )
            _exact_keys(
                event,
                {
                    "event",
                    "g",
                    "completed",
                    "piece_count",
                    "bdd_nodes",
                    "cofactor_counts",
                    "cofactor_width",
                    "union_seconds",
                    "cofactor_seconds",
                },
                "layer_profile",
            )
            _int(event.get("g"), "layer g", 0)
            _int(event.get("piece_count"), "layer piece_count", 1)
            bdd_nodes = _int(event.get("bdd_nodes"), "layer bdd_nodes", 0)
            width = _int(event.get("cofactor_width"), "layer width", 1)
            if width != max(counts):
                raise ParseError("layer width disagrees with its profile")
            if (
                counts[0] != 1
                or counts[-1] not in (1, 2)
                or width > bdd_nodes + 2
                or bdd_nodes > sum(counts[:-1])
                or (bdd_nodes == 0) != all(count == 1 for count in counts)
            ):
                raise ParseError("layer profile violates Boolean residual identities")
            if type(event.get("completed")) is not bool:
                raise ParseError("layer completed must be Boolean")
            _number(event.get("union_seconds"), "layer union time", 0)
            _number(event.get("cofactor_seconds"), "layer cofactor time", 0)
            layers.append(event)
        elif kind == "done":
            if phase != "body" or done is not None:
                raise ParseError("done event is duplicated or out of order")
            phase = "done"
            _exact_keys(
                event,
                {"event", "layer_union_effort", "solution_cost"},
                "done",
            )
            _int(event.get("solution_cost"), "solution cost", 0)
            _int(event.get("layer_union_effort"), "layer union effort", 0)
            done = event
        elif kind == "summary":
            if summary is not None:
                raise ParseError("profile summary is duplicated")
            _exact_keys(
                event,
                {
                    "event",
                    "profiled_layer_attempts",
                    "profiled_layers",
                    "sum_layer_bdd_nodes",
                    "heuristic_profiled",
                    "union_seconds",
                    "cofactor_seconds",
                    "heuristic_cofactor_seconds",
                    "serialization_seconds",
                    "output_seconds",
                    "solved",
                },
                "summary",
            )
            summary = event
        else:
            raise ParseError("unknown profile event {!r}".format(kind))
    complete = summary is not None
    if complete and events[-1]["event"] != "summary":
        raise ParseError("profile summary is not terminal")
    completed_layers = [event for event in layers if event["completed"]]
    completed_g = [event["g"] for event in completed_layers]
    if len(completed_g) != len(set(completed_g)):
        raise ParseError("profile has duplicate completed g layers")
    if complete:
        expected_summary = {
            "profiled_layer_attempts": len(layers),
            "profiled_layers": len(completed_layers),
            "sum_layer_bdd_nodes": sum(
                event["bdd_nodes"] for event in completed_layers
            ),
            "heuristic_profiled": heuristic is not None,
            "solved": done is not None,
        }
        for field, expected in expected_summary.items():
            if (
                summary.get(field) != expected
                or type(summary.get(field)) is not type(expected)
            ):
                raise ParseError(
                    "summary.{} changed or is inconsistent".format(field)
                )
        for field in (
            "union_seconds",
            "cofactor_seconds",
            "heuristic_cofactor_seconds",
            "serialization_seconds",
            "output_seconds",
        ):
            _number(summary.get(field), "summary {}".format(field), 0)
    if done is not None:
        expected_effort = sum(
            event["bdd_nodes"]
            for event in completed_layers
            if event["g"] < done["solution_cost"]
        )
        if done["layer_union_effort"] != expected_effort:
            raise ParseError("done effort disagrees with completed layer profiles")
    heuristic_paper_cuts = None
    if heuristic is not None:
        counts = heuristic["cofactor_counts"]
        heuristic_paper_cuts = {
            # The final entry is the terminal residual census after all n
            # bits. It certifies completeness but is not one of the paper's
            # i=0,...,n-1 cut-product summands.
            "paper_cut_width": max(counts[:-1]),
            # In contrast, Def. width ranges over cuts i=0,...,n and must
            # include the final terminal cut.
            "cofactor_width": max(counts),
            "cut_product_sum": sum(counts[:-1]),
            "terminal_residuals": counts[-1],
        }
    return {
        "complete": complete,
        "schema_version": 1,
        "state_bits": state_bits,
        "manager_variables": manager_variables,
        # The numerical certificate is meaningful only when the state-set and
        # heuristic vectors use the identical bit/cut order.  Keep a compact
        # identity for that cross-run check instead of duplicating this order
        # object in every analysis record.
        "variable_order_sha256": _sha(order),
        "heuristic_profile": heuristic,
        "heuristic_paper_cuts": heuristic_paper_cuts,
        "layer_profiles": [
            {
                "g": event["g"],
                "completed": event["completed"],
                "piece_count": event["piece_count"],
                "bdd_nodes": event["bdd_nodes"],
                "cofactor_width": event["cofactor_width"],
                "paper_cut_width": max(event["cofactor_counts"][:-1]),
                "paper_cut_product_sum": sum(event["cofactor_counts"][:-1]),
                "terminal_residuals": event["cofactor_counts"][-1],
                # Required to instantiate C_pi(L_g, h).  The final entry is
                # retained for validation/order completeness but excluded by
                # the analyzer from i=0,...,n-1 products.
                "cofactor_counts": event["cofactor_counts"],
                "cofactor_counts_sha256": _sha(event["cofactor_counts"]),
            }
            for event in layers
        ],
        "layer_profile_attempts": len(layers),
        "completed_layer_profiles": len(completed_layers),
        "done": done,
        "summary": summary,
        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
    }


def parse_profile_log(content, props) -> None:
    expected = props.get("algorithm") != "blind_fw"
    props["wbh_profile_expected"] = expected
    props["wbh_profile_present"] = bool(content)
    props["wbh_profile_parser_protocol"] = PROFILE_PARSER_PROTOCOL
    if not content:
        props["wbh_profile_prefix_certified"] = False
        props["wbh_profile_complete"] = False
        props["wbh_profile_certified"] = not expected
        props["wbh_profile_validation_error"] = (
            None if not expected else "expected profile log is missing"
        )
        return
    try:
        parsed = parse_profile_stream(content)
    except ParseError as err:
        props["wbh_profile_prefix_certified"] = False
        props["wbh_profile_complete"] = False
        props["wbh_profile_certified"] = False
        props["wbh_profile_validation_error"] = str(err)
        _add_error(props, str(err))
        return
    props["wbh_profile_prefix_certified"] = True
    props["wbh_profile_complete"] = parsed["complete"]
    props["wbh_profile_certified"] = parsed["complete"]
    props["wbh_profile_validation_error"] = None
    props.update({"wbh_profile_" + key: value for key, value in parsed.items()})


def parse_expansion_details(content, props) -> None:
    """Retain the g/h detail that the frozen aggregate parser discards."""
    props["wbh_expansion_parser_protocol"] = EXPANSION_PARSER_PROTOCOL
    props["wbh_expansion_profile_present"] = bool(content)
    if not content:
        props["wbh_expansion_profile_certified"] = False
        props["wbh_expansion_profile_complete"] = False
        props["wbh_expansion_profile_validation_error"] = "wbh.jsonl is missing"
        return
    try:
        from validate_wbh_log import load_json_line, validate_v2_events

        events = [
            load_json_line(line)
            for line in content.splitlines()
            if line.strip()
        ]
        report = validate_v2_events(events)
    except (ImportError, TypeError, ValueError, json.JSONDecodeError) as err:
        props["wbh_expansion_profile_certified"] = False
        props["wbh_expansion_profile_complete"] = False
        props["wbh_expansion_profile_validation_error"] = str(err)
        _add_error(props, "expansion-detail parser: {}".format(err))
        return
    if report["errors"]:
        message = " | ".join(report["errors"])
        props["wbh_expansion_profile_certified"] = False
        props["wbh_expansion_profile_complete"] = False
        props["wbh_expansion_profile_validation_error"] = message
        return
    valid = report["valid_events"]
    completed = [
        event
        for event in valid
        if event.get("event") == "expand" and event["completed"]
    ]
    done = report["done"]
    active = completed
    if done is not None:
        active = [
            event
            for event in completed
            if event["g"] < done["solution_cost"]
            and event["g"] + event["h"] <= done["solution_cost"]
        ]
    if len({(event["g"], event["h"]) for event in completed}) != len(completed):
        message = "completed expansion trace repeats a (g,h) bucket"
        props["wbh_expansion_profile_certified"] = False
        props["wbh_expansion_profile_validation_error"] = message
        _add_error(props, message)
        return
    by_g = {}
    for event in active:
        item = by_g.setdefault(
            event["g"],
            {"h_values": [], "effort": 0, "buckets": 0, "pieces": 0},
        )
        item["h_values"].append(event["h"])
        item["effort"] += event["bdd_nodes"]
        item["buckets"] += 1
        item["pieces"] += event["piece_count"]
    profile = []
    for g, item in sorted(by_g.items()):
        values = sorted(item.pop("h_values"))
        profile.append(
            {
                "g": g,
                "active_h_values": values,
                "active_value_count": len(values),
                **item,
            }
        )
    heuristics = [event for event in valid if event.get("event") == "heuristic"]
    if heuristics:
        declared_values = heuristics[0]["num_values"]
        if any(item["active_value_count"] > declared_values for item in profile):
            message = "active V_g exceeds the selected heuristic's V"
            props["wbh_expansion_profile_certified"] = False
            props["wbh_expansion_profile_validation_error"] = message
            _add_error(props, message)
            return
    elif any(item["active_h_values"] != [0] for item in profile):
        message = "blind expansion profile contains a nonzero h value"
        props["wbh_expansion_profile_certified"] = False
        props["wbh_expansion_profile_validation_error"] = message
        _add_error(props, message)
        return
    if done is not None and sum(item["effort"] for item in profile) != done["effort"]:
        message = "per-g expansion effort disagrees with the done event"
        props["wbh_expansion_profile_certified"] = False
        props["wbh_expansion_profile_validation_error"] = message
        _add_error(props, message)
        return
    props["wbh_expansion_profile_certified"] = True
    props["wbh_expansion_profile_complete"] = report["summary_present"]
    props["wbh_expansion_profile_validation_error"] = None
    props["wbh_expansion_profile"] = profile
    props["wbh_expansion_profile_sha256"] = _sha(profile)


def _selector_record_keys(protocol, budget_field):
    keys = list(BASE_SELECTOR_KEYS[:-2])
    keys.append(budget_field)
    if protocol in CAP_GRID_PROTOCOLS:
        cap_keys = list(CAP_SELECTOR_KEYS)
        cap_keys[-1:-1] = CAP_GRID_ONLY_KEYS
        keys.extend(cap_keys)
    elif protocol in {
        "fixed_pool_value_cap_v2",
        "fixed_pool_total_add_value_cap_v1",
    }:
        keys.extend(CAP_SELECTOR_KEYS)
    keys.extend(BASE_SELECTOR_KEYS[-2:])
    return tuple(keys)


def _bounded_int(value, label, minimum=0, maximum=INT64_MAX):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ParseError(
            "{} must be an integer in [{}, {}]".format(
                label, minimum, maximum
            )
        )
    return value


def _validate_selector_record(record, marker, kind, *, retained=False):
    """Validate one wire or histogram-normalized selector record."""
    if not isinstance(record, dict):
        raise ParseError("selector record is not an object")
    protocol = record.get("protocol")
    if marker == "width" and protocol not in WIDTH_PROTOCOLS:
        raise ParseError("width selector has an unexpected protocol")
    if marker == "add" and protocol not in ADD_PROTOCOLS:
        raise ParseError("ADD selector has an unexpected protocol")
    if record.get("score_version") != PROTOCOL_SCORES.get(protocol):
        raise ParseError("selector score version changed for its protocol")
    budget_field = (
        "total_add_node_budget" if marker == "add" else "cofactor_width_budget"
    )
    expected_keys = _selector_record_keys(protocol, budget_field)
    if tuple(record) != expected_keys:
        raise ParseError("selector record keys/order changed for its protocol")

    sources = record["sources"]
    pattern = record["pattern"]
    if (
        not isinstance(sources, list)
        or not sources
        or any(type(source) is not str for source in sources)
        or len(sources) != len(set(sources))
        or any(source not in SOURCE_ORDER for source in sources)
        or [SOURCE_ORDER.index(source) for source in sources]
        != sorted(SOURCE_ORDER.index(source) for source in sources)
        or not isinstance(pattern, list)
        or any(type(var) is not int or not 0 <= var <= INT_MAX for var in pattern)
        or pattern != sorted(set(pattern))
    ):
        raise ParseError("selector sources or pattern are invalid")
    abstract_states = _bounded_int(
        record["abstract_states"], "abstract_states", 1, INT_MAX
    )
    budget = _bounded_int(record[budget_field], budget_field, 1, INT_MAX)
    feasible = record["feasible"]
    if type(feasible) is not bool:
        raise ParseError("selector feasible is not Boolean")

    capped = protocol in {
        "fixed_pool_value_cap_v2",
        "fixed_pool_total_add_value_cap_v1",
    }
    cap_grid = protocol in CAP_GRID_PROTOCOLS
    statistic_fields = list(BASE_SELECTOR_KEYS[5:-2])
    if capped or cap_grid:
        statistic_fields.extend(CAP_SELECTOR_KEYS[1:])
        if cap_grid:
            statistic_fields.extend(CAP_GRID_ONLY_KEYS)
    all_null = all(record[field] is None for field in statistic_fields)
    if all_null:
        if (
            kind != "candidate"
            or abstract_states <= MAX_ABSTRACT_STATES
            or feasible
            or record["rejection_reason"] != "abstract_state_budget"
            or sources != ["cegar"]
            or len(pattern) != 1
            or (cap_grid and record["value_cap"] != -1)
        ):
            raise ParseError("unmaterialized selector outcome is invalid")
        return budget_field, budget
    if any(
        record[field] is None
        for field in statistic_fields
        if field not in {
            "initial_h",
            "raw_initial_h",
            "raw_initial_value_count",
            "raw_value_histogram",
        }
    ):
        raise ParseError("selector statistics are only partially present")
    if abstract_states > MAX_ABSTRACT_STATES:
        raise ParseError("materialized selector candidate exceeds its state budget")
    if cap_grid and len(pattern) > 16:
        raise ParseError("cap-grid materialized pattern exceeds its encoding bound")

    if type(record["initial_dead_end"]) is not bool:
        raise ParseError("initial_dead_end is not Boolean")
    if record["initial_dead_end"]:
        if record["initial_h"] is not None:
            raise ParseError("dead selector record has non-null initial_h")
    else:
        _bounded_int(record["initial_h"], "initial_h", 0, INT_MAX - 1)
    for field in ("finite_count", "dead_count"):
        _bounded_int(record[field], field, 0, INT_MAX)
    for field in ("finite_sum", "cofactor_width", "width_upper_bound"):
        _bounded_int(
            record[field], field, 1 if field == "cofactor_width" else 0
        )
    if (
        record["finite_count"] < 1
        or record["finite_count"] + record["dead_count"] != abstract_states
        or (
            not record["initial_dead_end"]
            and record["finite_sum"] < record["initial_h"]
        )
        or (record["initial_dead_end"] and record["dead_count"] < 1)
        or record["cofactor_width"] > record["width_upper_bound"]
    ):
        raise ParseError("selector common statistics violate their identities")

    if capped or cap_grid:
        cap = _bounded_int(record["value_cap"], "value_cap", -1, INT_MAX - 1)
        if capped and cap < 0:
            raise ParseError("fixed-cap selector has no finite value cap")
        if cap_grid and cap != -1 and cap not in CAP_GRID:
            raise ParseError("cap-grid value cap is outside the producer grid")
        for field in (
            "num_terminals",
            "raw_num_terminals",
            "raw_num_values",
            "raw_max_finite_value",
            "raw_finite_count",
            "raw_dead_count",
            "transformed_num_values",
        ):
            _bounded_int(record[field], field, 0, INT_MAX)
        for field in (
            "add_nodes",
            "raw_add_nodes",
            "raw_cofactor_width",
            "raw_width_upper_bound",
            "raw_finite_sum",
        ):
            _bounded_int(record[field], field, 0, INT64_MAX)
        if type(record["raw_initial_dead_end"]) is not bool:
            raise ParseError("raw_initial_dead_end is not Boolean")
        if record["raw_initial_dead_end"]:
            if (
                record["raw_initial_h"] is not None
                or (cap_grid and record["raw_initial_value_count"] is not None)
                or record["raw_dead_count"] < 1
            ):
                raise ParseError("raw initial-dead evidence is invalid")
        else:
            _bounded_int(
                record["raw_initial_h"], "raw_initial_h", 0, INT_MAX - 1
            )
            if cap_grid:
                _bounded_int(
                    record["raw_initial_value_count"],
                    "raw_initial_value_count",
                    1,
                    MAX_ABSTRACT_STATES,
                )
        if cap_grid:
            histogram = record["raw_value_histogram"]
            if retained:
                if (
                    type(histogram) is not str
                    or HISTOGRAM_DIGEST_RE.fullmatch(histogram) is None
                ):
                    raise ParseError("retained raw histogram digest is invalid")
            elif histogram is not None and (
                type(histogram) is not str
                or not histogram
                or len(histogram) > MAX_HISTOGRAM_BASE64
                or HISTOGRAM_WIRE_RE.fullmatch(histogram) is None
            ):
                raise ParseError("wire raw histogram is malformed")

        expected_terminals = record["transformed_num_values"] + int(
            record["dead_count"] > 0
        )
        expected_raw_terminals = record["raw_num_values"] + int(
            record["raw_dead_count"] > 0
        )
        if (
            record["raw_finite_count"] != record["finite_count"]
            or record["raw_dead_count"] != record["dead_count"]
            or record["raw_finite_count"] + record["raw_dead_count"]
            != abstract_states
            or record["raw_initial_dead_end"] is not record["initial_dead_end"]
            or record["num_terminals"] != expected_terminals
            or record["raw_num_terminals"] != expected_raw_terminals
            or record["width_upper_bound"]
            != record["add_nodes"] + record["num_terminals"]
            or record["raw_width_upper_bound"]
            != record["raw_add_nodes"] + record["raw_num_terminals"]
            or not 1
            <= record["transformed_num_values"]
            <= record["finite_count"]
            or not 1 <= record["raw_num_values"] <= record["raw_finite_count"]
            or record["num_terminals"] > record["add_nodes"] + 1
            or record["raw_num_terminals"] > record["raw_add_nodes"] + 1
            or (record["add_nodes"] == 0) != (record["num_terminals"] == 1)
            or (record["raw_add_nodes"] == 0)
            != (record["raw_num_terminals"] == 1)
            or record["cofactor_width"] < record["num_terminals"]
            or record["raw_cofactor_width"] < record["raw_num_terminals"]
            or record["raw_cofactor_width"] > record["raw_width_upper_bound"]
            or record["raw_cofactor_width"] < record["cofactor_width"]
            or record["raw_add_nodes"] < record["add_nodes"]
            or record["raw_num_terminals"] < record["num_terminals"]
            or record["raw_width_upper_bound"] < record["width_upper_bound"]
            or record["raw_num_values"] < record["transformed_num_values"]
            or record["raw_finite_sum"] < record["finite_sum"]
            or record["raw_max_finite_value"] >= INT_MAX
            or record["raw_num_values"] > record["raw_max_finite_value"] + 1
            or record["raw_finite_sum"] < record["raw_max_finite_value"]
            or record["raw_finite_sum"]
            > record["raw_max_finite_value"]
            * (record["raw_finite_count"] - 1)
            or (record["finite_sum"] == 0)
            != (record["transformed_num_values"] == 1)
            or (record["raw_finite_sum"] == 0)
            != (record["raw_num_values"] == 1)
            or (
                not record["raw_initial_dead_end"]
                and record["raw_initial_h"] > record["raw_max_finite_value"]
            )
            or (
                cap_grid
                and not record["raw_initial_dead_end"]
                and record["raw_initial_value_count"]
                > record["raw_finite_count"]
            )
        ):
            raise ParseError("cap selector A/T/U/V or transform identity is invalid")
        if cap >= 0:
            if (
                record["transformed_num_values"] > cap + 1
                or record["finite_sum"] > cap * record["finite_count"]
                or (
                    not record["initial_dead_end"]
                    and record["initial_h"] != min(record["raw_initial_h"], cap)
                )
            ):
                raise ParseError("cap transform contradicts its value cap")
        elif any(
            record[field] != record["raw_" + field]
            for field in (
                "add_nodes",
                "num_terminals",
                "cofactor_width",
                "width_upper_bound",
                "finite_sum",
                "finite_count",
                "dead_count",
                "initial_dead_end",
                "initial_h",
            )
        ) or record["transformed_num_values"] != record["raw_num_values"]:
            raise ParseError("exact cap transform differs from raw")

    metric = (
        record["width_upper_bound"]
        if budget_field == "total_add_node_budget"
        else record["cofactor_width"]
    )
    expected_feasible = metric <= budget
    if feasible is not expected_feasible:
        raise ParseError("selector feasibility disagrees with its budget")
    expected_reason = None if feasible else budget_field
    if record["rejection_reason"] != expected_reason:
        raise ParseError("selector rejection reason disagrees with feasibility")
    if kind == "selected" and not feasible:
        raise ParseError("selected record is infeasible")

    if "empty" in sources:
        expected_empty = {
            "pattern": [],
            "abstract_states": 1,
            "initial_dead_end": False,
            "initial_h": 0,
            "finite_sum": 0,
            "finite_count": 1,
            "dead_count": 0,
            "cofactor_width": 1,
            "width_upper_bound": 1,
            "feasible": True,
            "rejection_reason": None,
        }
        if capped or cap_grid:
            expected_empty.update(
                {
                    "add_nodes": 0,
                    "num_terminals": 1,
                    "raw_add_nodes": 0,
                    "raw_num_terminals": 1,
                    "raw_cofactor_width": 1,
                    "raw_width_upper_bound": 1,
                    "raw_num_values": 1,
                    "raw_max_finite_value": 0,
                    "raw_finite_sum": 0,
                    "raw_finite_count": 1,
                    "raw_dead_count": 0,
                    "raw_initial_dead_end": False,
                    "raw_initial_h": 0,
                    "transformed_num_values": 1,
                }
            )
            if cap_grid:
                expected_empty.update(
                    {"value_cap": -1, "raw_initial_value_count": 1}
                )
        if any(record[key] != value for key, value in expected_empty.items()):
            raise ParseError("empty-pattern selector invariants changed")
    return budget_field, budget


def _append_uvarint(result, value):
    while True:
        byte = value & 0x7F
        value >>= 7
        result.append(byte | (0x80 if value else 0))
        if not value:
            return


def encode_raw_value_histogram(pairs):
    """Encode a producer-canonical finite-value census (used by tests)."""
    data = bytearray()
    _append_uvarint(data, len(pairs))
    previous = -1
    for distance, count in pairs:
        if (
            type(distance) is not int
            or type(count) is not int
            or not 0 <= distance < INT_MAX
            or not 1 <= count <= MAX_ABSTRACT_STATES
            or distance <= previous
        ):
            raise ValueError("invalid raw histogram pair")
        _append_uvarint(data, distance - previous)
        _append_uvarint(data, count)
        previous = distance
    return base64.urlsafe_b64encode(bytes(data)).rstrip(b"=").decode("ascii")


def _read_uvarint(data, offset, maximum):
    value = 0
    shift = 0
    start = offset
    while offset < len(data) and offset - start < 5:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if offset - start > 1 and byte == 0:
                raise ValueError("noncanonical raw histogram varint")
            if value > maximum:
                raise ValueError("raw histogram integer exceeds producer type")
            return value, offset
        shift += 7
    raise ValueError("unterminated raw histogram varint")


def decode_raw_value_histogram(payload):
    if (
        type(payload) is not str
        or not payload
        or len(payload) > MAX_HISTOGRAM_BASE64
        or len(payload) % 4 == 1
        or HISTOGRAM_WIRE_RE.fullmatch(payload) is None
    ):
        raise ValueError("raw histogram base64 is malformed")
    try:
        data = base64.b64decode(
            payload + "=" * (-len(payload) % 4),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError) as err:
        raise ValueError("raw histogram base64 is malformed") from err
    if len(data) > MAX_HISTOGRAM_BYTES:
        raise ValueError("raw histogram exceeds its byte bound")
    canonical = base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")
    if canonical != payload:
        raise ValueError("raw histogram base64 is noncanonical")
    count, offset = _read_uvarint(data, 0, MAX_ABSTRACT_STATES)
    if count < 1:
        raise ValueError("raw histogram has no finite values")
    pairs = []
    previous = -1
    total = 0
    for _ in range(count):
        delta, offset = _read_uvarint(data, offset, INT_MAX)
        frequency, offset = _read_uvarint(
            data, offset, MAX_ABSTRACT_STATES
        )
        if delta < 1 or frequency < 1:
            raise ValueError("raw histogram uses zero delta/count")
        distance = previous + delta
        if distance >= INT_MAX:
            raise ValueError("raw histogram distance uses the infinity sentinel")
        total += frequency
        if total > MAX_ABSTRACT_STATES:
            raise ValueError("raw histogram exceeds state budget")
        pairs.append((distance, frequency))
        previous = distance
    if offset != len(data):
        raise ValueError("raw histogram has trailing bytes")
    if pairs[0][0] != 0:
        raise ValueError("raw histogram omits the zero-valued goal")
    return pairs, "sha256:" + hashlib.sha256(data).hexdigest()


def _histogram_matches_raw(record, pairs):
    counts = dict(pairs)
    return (
        len(pairs) == record["raw_num_values"]
        and pairs[-1][0] == record["raw_max_finite_value"]
        and sum(counts.values()) == record["raw_finite_count"]
        and sum(value * count for value, count in pairs)
        == record["raw_finite_sum"]
        and (
            record["raw_initial_dead_end"]
            or counts.get(record["raw_initial_h"])
            == record["raw_initial_value_count"]
        )
    )


def _histogram_matches_transform(record, pairs):
    cap = record["value_cap"]
    transformed = defaultdict(int)
    for value, count in pairs:
        transformed[value if cap < 0 else min(value, cap)] += count
    expected_initial = (
        None
        if record["raw_initial_dead_end"]
        else (
            record["raw_initial_h"]
            if cap < 0
            else min(record["raw_initial_h"], cap)
        )
    )
    return (
        len(transformed) == record["transformed_num_values"]
        and sum(value * count for value, count in transformed.items())
        == record["finite_sum"]
        and record["initial_h"] == expected_initial
    )


def _with_histogram_digest(record, digest):
    normalized = dict(record)
    normalized["raw_value_histogram"] = digest
    return normalized


def _group_candidates(candidates):
    groups = []
    seen = set()
    for record in candidates:
        pattern = tuple(record["pattern"])
        if not groups or groups[-1][0] != pattern:
            if pattern in seen:
                raise ParseError("selector candidate pattern is noncontiguous")
            seen.add(pattern)
            groups.append((pattern, []))
        groups[-1][1].append(record)
    return groups


def _raw_common_core(record):
    cap_protocol = record["protocol"] in CAP_GRID_PROTOCOLS or record[
        "protocol"
    ] in {"fixed_pool_value_cap_v2", "fixed_pool_total_add_value_cap_v1"}
    materialized = record["cofactor_width"] is not None
    if cap_protocol and materialized:
        values = {
            "initial_dead_end": record["raw_initial_dead_end"],
            "initial_h": record["raw_initial_h"],
            "finite_sum": record["raw_finite_sum"],
            "finite_count": record["raw_finite_count"],
            "dead_count": record["raw_dead_count"],
            "cofactor_width": record["raw_cofactor_width"],
            "width_upper_bound": record["raw_width_upper_bound"],
        }
    elif materialized:
        values = {
            key: record[key]
            for key in (
                "initial_dead_end",
                "initial_h",
                "finite_sum",
                "finite_count",
                "dead_count",
                "cofactor_width",
                "width_upper_bound",
            )
        }
    else:
        values = {
            key: None
            for key in (
                "initial_dead_end",
                "initial_h",
                "finite_sum",
                "finite_count",
                "dead_count",
                "cofactor_width",
                "width_upper_bound",
            )
        }
    return {
        "protocol": "fixed_pool_v1",
        "score_version": WIDTH_SCORE,
        "sources": record["sources"],
        "pattern": record["pattern"],
        "abstract_states": record["abstract_states"],
        **values,
    }


def _raw_extended_core(record):
    common = _raw_common_core(record)
    if record["protocol"] not in CAP_GRID_PROTOCOLS:
        return None
    if record["cofactor_width"] is None:
        extra = {
            key: None
            for key in (
                "raw_add_nodes",
                "raw_num_terminals",
                "raw_num_values",
                "raw_max_finite_value",
                "raw_initial_value_count",
                "raw_value_histogram",
            )
        }
    else:
        extra = {
            key: record[key]
            for key in (
                "raw_add_nodes",
                "raw_num_terminals",
                "raw_num_values",
                "raw_max_finite_value",
                "raw_initial_value_count",
                "raw_value_histogram",
            )
        }
    return {**common, **extra}


def _normalize_candidate_groups(candidates, require_complete):
    groups = _group_candidates(candidates)
    normalized = []
    representatives = []
    source_owner = {}
    common_pool = []
    extended_pool = []
    histogram_by_pattern = {}
    for group_index, (pattern, variants) in enumerate(groups):
        first = variants[0]
        protocol = first["protocol"]
        budget_field = (
            "total_add_node_budget"
            if protocol in ADD_PROTOCOLS
            else "cofactor_width_budget"
        )
        for source in first["sources"]:
            if source in source_owner:
                raise ParseError("fixed-pool source occurs in two patterns")
            source_owner[source] = pattern
        if any(
            record["sources"] != first["sources"]
            or record["abstract_states"] != first["abstract_states"]
            or record["protocol"] != protocol
            or record["score_version"] != first["score_version"]
            or record[budget_field] != first[budget_field]
            for record in variants
        ):
            raise ParseError("selector pattern identity changes across variants")

        if protocol in CAP_GRID_PROTOCOLS:
            unmaterialized = first["cofactor_width"] is None
            if any((record["cofactor_width"] is None) != unmaterialized for record in variants):
                raise ParseError("cap-grid group mixes materialized and null records")
            if unmaterialized:
                if (
                    len(variants) != 1
                    or first["value_cap"] != -1
                    or first["raw_value_histogram"] is not None
                    or group_index != len(groups) - 1
                ):
                    raise ParseError("unmaterialized cap-grid group has invalid form")
                group_records = variants
            else:
                histograms = [record["raw_value_histogram"] for record in variants]
                if type(histograms[0]) is not str or any(
                    histogram is not None for histogram in histograms[1:]
                ):
                    raise ParseError(
                        "raw histogram must occur only on a cap group's first record"
                    )
                try:
                    pairs, digest = decode_raw_value_histogram(histograms[0])
                except ValueError as err:
                    raise ParseError("raw histogram is invalid: {}".format(err)) from err
                if any(not _histogram_matches_raw(record, pairs) for record in variants):
                    raise ParseError("raw histogram contradicts raw candidate statistics")
                if any(
                    not _histogram_matches_transform(record, pairs)
                    for record in variants
                ):
                    raise ParseError("cap transform contradicts the raw histogram")
                group_records = [
                    _with_histogram_digest(record, digest) for record in variants
                ]
                histogram_by_pattern[pattern] = digest

                caps = [record["value_cap"] for record in variants]
                expected_caps = [
                    cap
                    for cap in CAP_GRID
                    if cap < first["raw_max_finite_value"]
                ] + [-1]
                group_complete = require_complete or group_index < len(groups) - 1
                if group_complete:
                    if caps != expected_caps:
                        raise ParseError(
                            "complete cap group omits, duplicates, or reorders a variant"
                        )
                elif caps != expected_caps[: len(caps)]:
                    raise ParseError("partial cap group skips or reorders a variant")

                raw_fields = (
                    "raw_add_nodes",
                    "raw_num_terminals",
                    "raw_cofactor_width",
                    "raw_width_upper_bound",
                    "raw_num_values",
                    "raw_max_finite_value",
                    "raw_finite_sum",
                    "raw_finite_count",
                    "raw_dead_count",
                    "raw_initial_dead_end",
                    "raw_initial_h",
                    "raw_initial_value_count",
                    "raw_value_histogram",
                )
                raw_identity = tuple(group_records[0][field] for field in raw_fields)
                if any(
                    tuple(record[field] for field in raw_fields) != raw_identity
                    for record in group_records[1:]
                ):
                    raise ParseError("raw candidate identity changes across cap variants")
                monotone_fields = (
                    "finite_sum",
                    "transformed_num_values",
                    "cofactor_width",
                    "add_nodes",
                    "num_terminals",
                    "width_upper_bound",
                )
                for field in monotone_fields:
                    values = [record[field] for record in group_records]
                    if values != sorted(values):
                        raise ParseError(
                            "cap-grid {} decreases under refinement".format(field)
                        )
                if not first["initial_dead_end"]:
                    initial_values = [record["initial_h"] for record in group_records]
                    if initial_values != sorted(initial_values):
                        raise ParseError("cap-grid initial value decreases under refinement")
                flags = [record["feasible"] for record in group_records]
                if flags != sorted(flags, reverse=True):
                    raise ParseError("cap-grid feasibility is nonmonotone")
        else:
            if len(variants) != 1:
                raise ParseError("non-grid selector repeats a candidate pattern")
            group_records = variants

        normalized.extend(group_records)
        materialized = [record for record in group_records if record["cofactor_width"] is not None]
        feasible = [record for record in materialized if record["feasible"]]
        if feasible:
            representatives.append(feasible[-1])
        common_pool.append(_raw_common_core(group_records[0]))
        extended = _raw_extended_core(group_records[0])
        if extended is not None:
            extended_pool.append(extended)
    return {
        "candidates": normalized,
        "representatives": representatives,
        "source_owner": source_owner,
        "common_pool": common_pool,
        "extended_pool": extended_pool,
        "histogram_by_pattern": histogram_by_pattern,
    }


def _score(record):
    dead = record["initial_dead_end"]
    initial_h = 0 if dead else record["initial_h"]
    finite_count = record["finite_count"]
    mean = Fraction(record["finite_sum"], finite_count) if finite_count else Fraction(10**30)
    dead_fraction = Fraction(record["dead_count"], record["abstract_states"])
    return (
        not dead,
        -initial_h,
        -mean,
        -dead_fraction,
        record["cofactor_width"],
        record["abstract_states"],
        tuple(record["pattern"]),
    )


def _same_selected(left, right):
    return left == right


def parse_selector_trace(content: str) -> dict | None:
    events = []
    event_order = []
    final_matches = []
    malformed_final_lines = []
    for line in content.splitlines():
        has_selector_marker = any(
            marker in line
            for marker in ("PDB width-selector", "PDB add-selector")
        )
        if has_selector_marker:
            selector = SELECTOR_RE.fullmatch(line)
            if selector is None:
                raise ParseError("selector marker line is malformed")
            marker, kind, payload = selector.groups()
            events.append((marker, kind, _load_json(payload, "selector record")))
            event_order.append(kind)
        if "wbh PDB heuristic:" in line:
            final_match = FINAL_RE.fullmatch(line)
            if final_match is None:
                malformed_final_lines.append(line)
            else:
                final_matches.append(final_match)
                event_order.append("final")
    if not events:
        if final_matches:
            raise ParseError("selector PDB final exists without selector records")
        # Direct PDB configurations emit a shorter heuristic summary with no
        # selector fields.  It belongs to their dedicated parser and is not a
        # malformed selector trace.
        return None
    if malformed_final_lines:
        raise ParseError("selector PDB final line is malformed")
    markers = {marker for marker, _, _ in events}
    if len(markers) != 1:
        raise ParseError("trace mixes width and ADD selectors")
    marker = next(iter(markers))
    wire_candidates = [record for _, kind, record in events if kind == "candidate"]
    wire_selected = [record for _, kind, record in events if kind == "selected"]
    if not wire_candidates:
        raise ParseError("selector trace has no candidates")
    identities = {
        _validate_selector_record(record, marker, "candidate", retained=False)
        for record in wire_candidates
    }
    if len(identities) != 1:
        raise ParseError("selector records do not share one budget")
    budget_field, budget = next(iter(identities))
    protocols = {record["protocol"] for record in wire_candidates}
    if len(protocols) != 1:
        raise ParseError("selector candidates mix protocol variants")
    protocol = next(iter(protocols))
    if len(wire_selected) > 1:
        raise ParseError("trace must contain at most one selected record")
    if wire_selected and [kind for _, kind, _ in events][-1] != "selected":
        raise ParseError("selected record is not the last selector event")
    if len(final_matches) > 1:
        raise ParseError("selector trace has multiple PDB final lines")
    expected_order = ["candidate"] * len(wire_candidates)
    if wire_selected:
        expected_order.append("selected")
    if final_matches:
        expected_order.append("final")
    if event_order != expected_order:
        raise ParseError("selector and final events are out of order")
    if final_matches and not wire_selected:
        raise ParseError("selector PDB final exists without a selected record")

    normalized = _normalize_candidate_groups(
        wire_candidates, require_complete=bool(wire_selected or final_matches)
    )
    candidates = normalized["candidates"]
    representatives = normalized["representatives"]
    source_owner = normalized["source_owner"]
    complete_pool = set(source_owner) == set(SOURCE_ORDER)
    groups = _group_candidates(candidates)
    first_source_positions = [
        SOURCE_ORDER.index(records[0]["sources"][0]) for _, records in groups
    ]
    if (
        first_source_positions != sorted(first_source_positions)
        or len(first_source_positions) != len(set(first_source_positions))
    ):
        raise ParseError("selector groups violate fixed first-source order")
    if "empty" not in candidates[0]["sources"]:
        raise ParseError("selector candidate prefix does not start with empty")
    if first_source_positions:
        latest = max(first_source_positions)
        missing_prefix = [
            SOURCE_ORDER[index]
            for index in range(latest)
            if SOURCE_ORDER[index] not in source_owner
        ]
        if missing_prefix:
            raise ParseError("selector prefix skips an earlier fixed-pool source")

    selected = None
    if wire_selected:
        selected_wire = wire_selected[0]
        selected_identity = _validate_selector_record(
            selected_wire, marker, "selected", retained=False
        )
        if selected_identity != (budget_field, budget):
            raise ParseError("selected record changes the selector budget")
        if selected_wire["protocol"] != protocol:
            raise ParseError("selected record changes the selector protocol")
        if not complete_pool:
            raise ParseError("selected trace lacks the complete fixed source pool")
        if protocol in CAP_GRID_PROTOCOLS:
            if selected_wire["raw_value_histogram"] is not None:
                raise ParseError("selected record repeats the raw histogram payload")
            digest = normalized["histogram_by_pattern"].get(
                tuple(selected_wire["pattern"])
            )
            if digest is None:
                raise ParseError("selected record lacks a certified raw histogram")
            selected = _with_histogram_digest(selected_wire, digest)
            _validate_selector_record(selected, marker, "selected", retained=True)
        else:
            selected = selected_wire
        if not representatives:
            raise ParseError("selector has no feasible candidate")
        expected = min(representatives, key=_score)
        if not _same_selected(selected, expected):
            raise ParseError("selected record disagrees with the frozen selector score")

    final = None
    if final_matches:
        (
            pattern_size,
            source,
            abstract_states,
            final_budget_field,
            final_budget,
            value_cap,
            num_values,
            width,
            upper,
        ) = final_matches[0].groups()
        numeric = [
            int(pattern_size),
            int(abstract_states),
            int(final_budget),
            int(num_values),
            int(width),
            int(upper),
        ]
        if any(value < 0 or value > INT_MAX for value in numeric):
            raise ParseError("selector PDB final numeric field is out of range")
        final = {
            "pattern_size": numeric[0],
            "selected_source": source,
            "abstract_states": numeric[1],
            "budget_field": final_budget_field,
            "budget": numeric[2],
            "value_cap": None if value_cap is None else int(value_cap),
            "num_values": numeric[3],
            "cofactor_width": numeric[4],
            "width_upper_bound": numeric[5],
        }
        expected_final = {
            "pattern_size": len(selected["pattern"]),
            "selected_source": selected["sources"][0],
            "abstract_states": selected["abstract_states"],
            "budget_field": budget_field,
            "budget": budget,
            "value_cap": selected.get("value_cap"),
            "num_values": selected.get("transformed_num_values"),
            "cofactor_width": selected["cofactor_width"],
            "width_upper_bound": selected["width_upper_bound"],
        }
        if "transformed_num_values" not in selected:
            if not 1 <= final["num_values"] <= selected["finite_count"]:
                raise ParseError("PDB final value count is impossible")
            expected_final["num_values"] = final["num_values"]
        if final != expected_final:
            raise ParseError("PDB final line disagrees with selected record")

    complete = final is not None
    common_sha = _sha(normalized["common_pool"])
    extended_sha = (
        _sha(normalized["extended_pool"])
        if protocol in CAP_GRID_PROTOCOLS
        else None
    )
    full_pool_hashes = selected is not None and complete_pool
    trace_core = {
        "marker": marker,
        "candidates": candidates,
        "selected": selected,
        "final": final,
    }
    return {
        "complete": complete,
        "marker": marker,
        "protocol": protocol,
        "budget_field": budget_field,
        "budget": budget,
        "candidates": candidates,
        "selected": selected,
        "final": final,
        "trace_sha256": _sha(trace_core),
        # Cap-grid records expose a strong identity containing raw A/T/V,
        # maximum value, and the decoded histogram digest.  The companion
        # common identity deliberately uses only fields serialized by frozen
        # fixed_pool_v1, enabling exact-vs-cap same-pool comparisons without
        # pretending the old protocol logged unavailable ADD metadata.
        "raw_pool_sha256": (
            (extended_sha or common_sha) if full_pool_hashes else None
        ),
        "raw_pool_common_sha256": common_sha if full_pool_hashes else None,
        "raw_pool_extended_sha256": (
            extended_sha if full_pool_hashes else None
        ),
        "partial_raw_pool_sha256": extended_sha or common_sha,
        "partial_raw_pool_common_sha256": common_sha,
        "partial_fixed_source_count": len(source_owner),
    }


def parse_selector_log(content, props) -> None:
    props["pdb_profile_selector_parser_protocol"] = SELECTOR_PARSER_PROTOCOL
    props["pdb_profile_selector_present"] = any(
        marker in content
        for marker in ("PDB width-selector", "PDB add-selector")
    )
    try:
        parsed = parse_selector_trace(content)
    except ParseError as err:
        props["pdb_profile_selector_prefix_certified"] = False
        props["pdb_profile_selector_trace_complete"] = False
        props["pdb_profile_selector_trace_certified"] = False
        props["pdb_profile_selector_validation_error"] = str(err)
        _add_error(props, str(err))
        return
    if parsed is None:
        props["pdb_profile_selector_prefix_certified"] = False
        props["pdb_profile_selector_trace_complete"] = False
        props["pdb_profile_selector_trace_certified"] = False
        props["pdb_profile_selector_validation_error"] = None
        return
    props["pdb_profile_selector_prefix_certified"] = True
    props["pdb_profile_selector_trace_complete"] = parsed["complete"]
    props["pdb_profile_selector_trace_certified"] = parsed["complete"]
    props["pdb_profile_selector_validation_error"] = None
    props.update({"pdb_profile_selector_" + key: value for key, value in parsed.items()})


def _add_error(props, message):
    try:
        from lab import tools
    except ImportError:
        props.setdefault("unexplained_errors", []).append(message)
    else:
        tools.add_unexplained_error(props, message)


def get_parser():
    from lab.parser import Parser

    parser = Parser()
    parser.add_function(parse_expansion_details, file="wbh.jsonl")
    parser.add_function(parse_profile_log, file=PROFILE_FILE)
    parser.add_function(parse_selector_log, file="run.log")
    return parser
