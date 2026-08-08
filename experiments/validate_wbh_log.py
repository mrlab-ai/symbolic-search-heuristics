#!/usr/bin/env python3
"""Syntactic and semantic validator for WBH JSON-lines logs (schema v2).

The exact event schema is shared with wbh_parser. In addition to checking keys
and JSON value types, validate_v2_events checks the producer invariants and
independently rebuilds every summary metric from the event stream. Absence of
a summary is accepted here as an externally killed partial stream; its parser
metrics remain uncertified.

Usage: python3 experiments/validate_wbh_log.py <log-file> [<log-file> ...]
"""
import json
import math
import sys


SCHEMA = {
    "schema": {"version": int, "node_count_convention": str,
               "image_count_convention": str,
               "expansion_count_convention": str},
    "expand": {"g": int, "h": int, "completed": bool, "piece_count": int,
               "bdd_nodes": int, "states": float, "image_time": float},
    "image": {"g": int, "min_h": int, "max_h": int,
              "source_buckets": int, "source_pieces": int,
              "calls_attempted": int, "calls_completed": int,
              "zero_cost": bool, "bdd_nodes": int, "states": float,
              "image_time": float},
    "partition": {"g": int, "layer_nodes": int, "sum_bucket_nodes": int,
                  "num_buckets": int},
    "heuristic": {"add_nodes": int, "num_values": int,
                  "num_terminals": int, "add_level_nodes": list,
                  "width_upper_bound": int},
    "pruned_deadends": {"g": int, "states": float, "bdd_nodes": int},
    "construction": {"heuristic": str, "seconds": float, "size_bound": int,
                     "value_cap": int, "completed": bool},
    "summary": {"expanded_bdd_nodes": int, "expanded_states": float,
                "expanded_bdd_pieces": int,
                "attempted_bdd_nodes": int, "attempted_states": float,
                "attempted_bdd_pieces": int, "bucket_expansions": int,
                "bucket_expansion_attempts": int, "image_events": int,
                "bucket_images": int, "image_source_buckets": int,
                "image_source_pieces": int, "image_calls_attempted": int,
                "image_calls_completed": int, "batched_images": int,
                "image_time": float, "solved": bool},
    "done": {"effort": int, "solution_cost": int},
}

SCHEMA_V2_CONVENTIONS = {
    "version": 2,
    "node_count_convention": "inner_nodes_per_piece",
    "image_count_convention": "per_piece_attempted_completed",
    "expansion_count_convention": "completed_with_attempts",
}

SUMMARY_INTEGER_KEYS = tuple(
    key for key, typ in SCHEMA["summary"].items() if typ is int
)
SUMMARY_FLOAT_KEYS = tuple(
    key for key, typ in SCHEMA["summary"].items() if typ is float
)

# The C++ logger uses ostream's default six significant digits independently
# for events and for the accumulated summary. Re-summing parsed event values
# can therefore differ slightly from the separately rounded summary value.
_FLOAT_REL_TOL = 2e-5
_FLOAT_ABS_TOL = 1e-9


def _value_has_type(value, expected_type):
    """Use JSON types, rejecting bool where Python considers it an int."""
    if expected_type is int:
        return type(value) is int
    if expected_type is float:
        if type(value) is not int and type(value) is not float:
            return False
        try:
            return math.isfinite(value)
        except OverflowError:
            return False
    return type(value) is expected_type


def validate_object(path, lineno, obj):
    if not isinstance(obj, dict):
        raise ValueError(
            f"{path}:{lineno}: JSON value is not an event object")
    event = obj.get("event")
    if event not in SCHEMA:
        raise ValueError(f"{path}:{lineno}: unknown event {event!r}")
    expected = SCHEMA[event]
    keys = set(obj.keys()) - {"event"}
    if keys != set(expected):
        raise ValueError(
            f"{path}:{lineno}: {event} keys {sorted(keys)} != "
            f"{sorted(expected)}")
    for key, typ in expected.items():
        value = obj[key]
        if not _value_has_type(value, typ):
            raise ValueError(
                f"{path}:{lineno}: {event}.{key}={value!r} is not "
                f"{typ.__name__}")
    return event


def validate_line(path, lineno, line):
    return validate_object(path, lineno, json.loads(line))


def _close(left, right):
    try:
        return (
            math.isfinite(left)
            and math.isfinite(right)
            and math.isclose(
                left, right, rel_tol=_FLOAT_REL_TOL,
                abs_tol=_FLOAT_ABS_TOL))
    except OverflowError:
        return False


def _summary_totals(expands, images, done):
    completed = [event for event in expands if event["completed"]]
    return {
        "expanded_bdd_nodes": sum(e["bdd_nodes"] for e in completed),
        "expanded_states": sum(e["states"] for e in completed),
        "expanded_bdd_pieces": sum(e["piece_count"] for e in completed),
        "attempted_bdd_nodes": sum(e["bdd_nodes"] for e in expands),
        "attempted_states": sum(e["states"] for e in expands),
        "attempted_bdd_pieces": sum(e["piece_count"] for e in expands),
        "bucket_expansions": len(completed),
        "bucket_expansion_attempts": len(expands),
        "image_events": len(images),
        "bucket_images": sum(e["calls_completed"] for e in images),
        "image_source_buckets": sum(e["source_buckets"] for e in images),
        "image_source_pieces": sum(e["source_pieces"] for e in images),
        "image_calls_attempted": sum(
            e["calls_attempted"] for e in images),
        "image_calls_completed": sum(
            e["calls_completed"] for e in images),
        "batched_images": sum(e["source_buckets"] > 1 for e in images),
        "image_time": sum(e["image_time"] for e in images),
        "solved": done is not None,
    }


def _add_nonnegative_errors(errors, label, event, keys):
    for key in keys:
        if event[key] < 0:
            errors.append(f"{label}.{key} must be nonnegative")


def validate_v2_events(events, external_errors=()):
    """Validate a schema-v2 stream and return canonical event-derived totals.

    external_errors lets callers pass malformed-line diagnostics that could
    not be represented in events. Absence of a summary is not a semantic error
    because an externally killed run is a valid partial stream; callers must
    separately require summary_present before certifying complete raw metrics.
    """
    errors = list(external_errors)
    valid_events = []
    for lineno, event in enumerate(events, 1):
        try:
            validate_object("wbh.jsonl", lineno, event)
        except (TypeError, ValueError) as err:
            errors.append(str(err))
        else:
            valid_events.append(event)

    schemas = [e for e in valid_events if e["event"] == "schema"]
    expands = [e for e in valid_events if e["event"] == "expand"]
    images = [e for e in valid_events if e["event"] == "image"]
    partitions = [e for e in valid_events if e["event"] == "partition"]
    heuristics = [e for e in valid_events if e["event"] == "heuristic"]
    pruned = [e for e in valid_events if e["event"] == "pruned_deadends"]
    constructions = [e for e in valid_events if e["event"] == "construction"]
    summaries = [e for e in valid_events if e["event"] == "summary"]
    dones = [e for e in valid_events if e["event"] == "done"]

    if len(schemas) != 1:
        errors.append(f"expected exactly one schema event, got {len(schemas)}")
    elif any(schemas[0][key] != value
             for key, value in SCHEMA_V2_CONVENTIONS.items()):
        errors.append("schema event does not declare the frozen v2 conventions")
    if events and (not isinstance(events[0], dict)
                   or events[0].get("event") != "schema"):
        errors.append("schema event must be first")
    if len(summaries) > 1:
        errors.append(f"expected at most one summary event, got {len(summaries)}")
    if summaries and (not isinstance(events[-1], dict)
                      or events[-1].get("event") != "summary"):
        errors.append("summary event must be last")
    if len(dones) > 1:
        errors.append(f"expected at most one done event, got {len(dones)}")
    if len(heuristics) > 1:
        errors.append(
            f"expected at most one heuristic event, got {len(heuristics)}")
    if len(constructions) > 1:
        errors.append(
            f"expected at most one construction event, got "
            f"{len(constructions)}")

    for index, event in enumerate(expands):
        label = f"expand[{index}]"
        _add_nonnegative_errors(
            errors, label, event,
            ("g", "h", "bdd_nodes", "states", "image_time"))
        if event["piece_count"] < 1:
            errors.append(f"{label}.piece_count must be positive")

    for index, event in enumerate(images):
        label = f"image[{index}]"
        _add_nonnegative_errors(
            errors, label, event,
            ("g", "min_h", "max_h", "bdd_nodes", "states", "image_time",
             "calls_attempted", "calls_completed"))
        if event["min_h"] > event["max_h"]:
            errors.append(f"{label}.min_h exceeds max_h")
        if event["source_buckets"] < 1:
            errors.append(f"{label}.source_buckets must be positive")
        if event["source_pieces"] < 1:
            errors.append(f"{label}.source_pieces must be positive")
        if event["calls_completed"] > event["calls_attempted"]:
            errors.append(
                f"{label}.calls_completed exceeds calls_attempted")
        if event["calls_attempted"] > event["source_pieces"]:
            errors.append(
                f"{label}.calls_attempted exceeds source_pieces")

    for index, event in enumerate(partitions):
        label = f"partition[{index}]"
        _add_nonnegative_errors(
            errors, label, event,
            ("g", "layer_nodes", "sum_bucket_nodes", "num_buckets"))
        if event["layer_nodes"] > 0:
            try:
                ratio = event["sum_bucket_nodes"] / event["layer_nodes"]
                finite = math.isfinite(ratio)
            except OverflowError:
                finite = False
            if not finite:
                errors.append(f"{label} ratio is not finite")

    for index, event in enumerate(pruned):
        _add_nonnegative_errors(
            errors, f"pruned_deadends[{index}]", event,
            ("g", "states", "bdd_nodes"))

    for index, event in enumerate(heuristics):
        label = f"heuristic[{index}]"
        _add_nonnegative_errors(
            errors, label, event,
            ("add_nodes", "num_values", "num_terminals",
             "width_upper_bound"))
        if event["num_terminals"] < 1:
            errors.append(f"{label}.num_terminals must be positive")
        if any(type(value) is not int or value < 0
               for value in event["add_level_nodes"]):
            errors.append(
                f"{label}.add_level_nodes must contain nonnegative ints")
        elif sum(event["add_level_nodes"]) != event["add_nodes"]:
            errors.append(f"{label}.add_level_nodes do not sum to add_nodes")
        if (event["width_upper_bound"]
                != event["add_nodes"] + event["num_terminals"]):
            errors.append(
                f"{label}.width_upper_bound != add_nodes + num_terminals")
        if event["num_values"] > event["num_terminals"]:
            errors.append(f"{label}.num_values exceeds num_terminals")

    for index, event in enumerate(constructions):
        label = f"construction[{index}]"
        _add_nonnegative_errors(
            errors, label, event, ("seconds", "size_bound"))
        if event["value_cap"] < -1:
            errors.append(f"{label}.value_cap must be -1 or nonnegative")
    if heuristics and (len(constructions) != 1
                       or not constructions[0]["completed"]):
        errors.append(
            "heuristic event requires one completed construction event")
    if (len(constructions) == 1 and constructions[0]["completed"]
            and not heuristics):
        errors.append(
            "completed construction event requires one heuristic event")

    done = dones[0] if len(dones) == 1 else None
    if done is not None:
        _add_nonnegative_errors(
            errors, "done", done, ("effort", "solution_cost"))
        expected_effort = sum(
            event["bdd_nodes"] for event in expands
            if event["completed"]
            and event["g"] + event["h"] <= done["solution_cost"]
            and event["g"] < done["solution_cost"])
        if done["effort"] != expected_effort:
            errors.append(
                f"done.effort={done['effort']} != event total "
                f"{expected_effort}")

    totals = _summary_totals(expands, images, done)
    for key in SUMMARY_FLOAT_KEYS:
        try:
            finite = math.isfinite(totals[key])
        except OverflowError:
            finite = False
        if not finite:
            errors.append(f"event total {key} is not finite")
    summary = summaries[0] if len(summaries) == 1 else None
    if summary is not None:
        for key in SUMMARY_INTEGER_KEYS:
            if summary[key] < 0:
                errors.append(f"summary.{key} must be nonnegative")
            if summary[key] != totals[key]:
                errors.append(
                    f"summary.{key}={summary[key]} != event total "
                    f"{totals[key]}")
        for key in SUMMARY_FLOAT_KEYS:
            if summary[key] < 0:
                errors.append(f"summary.{key} must be nonnegative")
            if not _close(summary[key], totals[key]):
                errors.append(
                    f"summary.{key}={summary[key]} != event total "
                    f"{totals[key]}")
        if summary["solved"] != totals["solved"]:
            errors.append(
                f"summary.solved={summary['solved']} != done presence "
                f"{totals['solved']}")

        # Redundant aggregate identities make a corrupted summary fail closed
        # even if a caller later extends event aggregation incorrectly.
        inequalities = (
            ("expanded_bdd_nodes", "attempted_bdd_nodes"),
            ("expanded_states", "attempted_states"),
            ("expanded_bdd_pieces", "attempted_bdd_pieces"),
            ("bucket_expansions", "bucket_expansion_attempts"),
            ("image_calls_completed", "image_calls_attempted"),
            ("image_calls_attempted", "image_source_pieces"),
            ("image_events", "image_source_buckets"),
            ("image_events", "image_source_pieces"),
            ("batched_images", "image_events"),
        )
        for lower, upper in inequalities:
            if summary[lower] > summary[upper] and not (
                    lower == "expanded_states"
                    and _close(summary[lower], summary[upper])):
                errors.append(f"summary.{lower} exceeds {upper}")
        if summary["bucket_images"] != summary["image_calls_completed"]:
            errors.append(
                "summary.bucket_images != image_calls_completed")

    return {
        "errors": errors,
        "valid_events": valid_events,
        "event_totals": totals,
        "summary": summary,
        "done": done,
        "summary_present": summary is not None,
    }


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    total = 0
    for path in sys.argv[1:]:
        counts = {}
        events = []
        with open(path) as stream:
            for lineno, line in enumerate(stream, 1):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                event = validate_object(path, lineno, obj)
                events.append(obj)
                counts[event] = counts.get(event, 0) + 1
                total += 1
        if any(event.get("event") == "schema" for event in events):
            report = validate_v2_events(events)
            if report["errors"]:
                raise ValueError(
                    f"{path}: semantic validation failed: "
                    + " | ".join(report["errors"]))
        print(f"OK {path}: {counts}")
    print(f"Validated {total} lines.")


if __name__ == "__main__":
    main()
