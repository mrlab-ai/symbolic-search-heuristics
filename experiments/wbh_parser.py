"""Downward Lab parser for width-bounded-heuristics JSON-lines logs.

Schema-v2 raw metrics are certified only after exact schema/type validation,
event-level invariant checks, and independent summary reconstruction. On any
inconsistency, summary values are ignored, event-derived values remain
available for diagnosis, and raw_metrics_complete/piece_metrics_certified are
both false. Legacy logs retain their historical conventions but are never
piece-metric certified.
"""
import json
import math

try:
    from validate_wbh_log import validate_v2_events
except ImportError:
    # Supports importing this module from the repository root in focused tests.
    from experiments.validate_wbh_log import validate_v2_events


METRICS_VALIDATION_PROTOCOL = "wbh-exact-schema-semantic-v1"


_METRIC_KEYS = (
    "expanded_bdd_nodes", "expanded_states", "expanded_bdd_pieces",
    "attempted_bdd_nodes", "attempted_states", "attempted_bdd_pieces",
    "bucket_expansions", "bucket_expansion_attempts", "image_events",
    "bucket_images", "image_source_buckets", "image_source_pieces",
    "image_calls_attempted", "image_calls_completed", "batched_images",
    "image_time",
)


def _events_of_kind(events, kind):
    return [
        event for event in events
        if isinstance(event, dict) and event.get("event") == kind
    ]


def _only(events, kind):
    matches = _events_of_kind(events, kind)
    return matches[0] if len(matches) == 1 else None


def _partition_ratios(partitions):
    ratios = []
    for event in partitions:
        layer_nodes = event.get("layer_nodes")
        bucket_nodes = event.get("sum_bucket_nodes")
        if (type(layer_nodes) is not int or type(bucket_nodes) is not int
                or layer_nodes <= 0 or bucket_nodes < 0):
            continue
        try:
            ratio = bucket_nodes / layer_nodes
        except OverflowError:
            continue
        if math.isfinite(ratio):
            ratios.append(ratio)
    return ratios


def _append_validation_error(props, message):
    old = props.get("metrics_validation_error")
    props["metrics_validation_error"] = (
        message if not old else old + " | " + message)


def _invalidate_outcome(props, messages):
    """Make a planner/WBH solved-cost disagreement ineligible as an outcome."""
    props["coverage"] = None
    add_error = getattr(props, "add_unexplained_error", None)
    if callable(add_error):
        add_error("WBH outcome validation failed: " + " | ".join(messages))


def _set_schema_properties(props, schema):
    if schema is None:
        # Archives produced before schema v2 logged Cudd_DagSize (including a
        # terminal per BDD) and did not record blind frontier piece counts.
        props["wbh_schema_version"] = 1
        props["node_count_convention"] = "legacy_cudd_dag_size"
        props["image_count_convention"] = "legacy_expand_event_count"
        props["expansion_count_convention"] = "legacy_attempts_unmarked"
        return
    props["wbh_schema_version"] = schema.get("version", "invalid")
    props["node_count_convention"] = schema.get(
        "node_count_convention", "missing")
    props["image_count_convention"] = schema.get(
        "image_count_convention", "missing")
    props["expansion_count_convention"] = schema.get(
        "expansion_count_convention", "missing")


def _set_common_event_properties(
        props, expands, partitions, heuristic, construction, done, pruned):
    if expands:
        props["peak_bdd_nodes"] = max(
            event["bdd_nodes"] for event in expands)
    if done is not None:
        props["effort"] = done["effort"]
        props["solution_cost"] = done["solution_cost"]
    if heuristic is not None:
        props["width_upper_bound"] = heuristic["width_upper_bound"]
        props["num_values"] = heuristic["num_values"]
        props["num_terminals"] = heuristic["num_terminals"]
        props["add_nodes"] = heuristic["add_nodes"]
    if construction is not None:
        props["heuristic_kind"] = construction["heuristic"]
        props["construction_time"] = construction["seconds"]
        props["heuristic_size_bound"] = construction["size_bound"]
        props["value_cap"] = construction["value_cap"]
        props["construction_completed"] = construction["completed"]

    props["num_pruned_deadends"] = len(pruned)
    props["pruned_deadend_states"] = sum(
        event["states"] for event in pruned)
    props["pruned_deadend_bdd_nodes"] = sum(
        event["bdd_nodes"] for event in pruned)

    ratios = _partition_ratios(partitions)
    if ratios:
        ratio_max = max(ratios)
        if any(ratio == 0 for ratio in ratios):
            ratio_geomean = 0
        else:
            ratio_geomean = math.exp(
                sum(math.log(ratio) for ratio in ratios) / len(ratios))
        props["partition_ratio_max"] = ratio_max
        props["partition_ratio_geomean"] = ratio_geomean
        # Backward-compatible aliases for archived report scripts.
        props["frag_ratio_max"] = ratio_max
        props["frag_ratio_geomean"] = ratio_geomean


def _parse_v2(events, parse_errors, props):
    report = validate_v2_events(events, parse_errors)
    errors = report["errors"]
    valid_events = report["valid_events"]
    totals = report["event_totals"]
    done = report["done"]
    outcome_errors = []
    coverage = props.get("coverage")
    summary = report["summary"]
    if (summary is not None and coverage in (0, 1)
            and bool(coverage) != summary["solved"]):
        outcome_errors.append(
            "summary.solved={} != planner coverage {}".format(
                summary["solved"], coverage))
    if (done is not None and "solution_cost" in props
            and props["solution_cost"] != done["solution_cost"]):
        outcome_errors.append(
            "done.solution_cost={} != planner output {}".format(
                done["solution_cost"], props["solution_cost"]))
    if done is not None and coverage == 0:
        outcome_errors.append("done event present for unsolved planner output")
    if done is not None and coverage == 1 and "solution_cost" not in props:
        outcome_errors.append(
            "done event present but planner output has no solution cost")
    errors.extend(outcome_errors)
    if outcome_errors:
        _invalidate_outcome(props, outcome_errors)

    # Canonical parser metrics always come from events. A consistent summary
    # certifies completeness but is never allowed to overwrite its evidence.
    for key in _METRIC_KEYS:
        props[key] = totals[key]
    props["raw_metrics_complete"] = (
        report["summary_present"] and not errors)
    props["piece_metrics_certified"] = not errors
    if errors:
        _append_validation_error(props, " | ".join(errors))

    expands = _events_of_kind(valid_events, "expand")
    partitions = _events_of_kind(valid_events, "partition")
    pruned = _events_of_kind(valid_events, "pruned_deadends")
    _set_common_event_properties(
        props, expands, partitions,
        _only(valid_events, "heuristic"),
        _only(valid_events, "construction"),
        done if not errors else None, pruned)


def _parse_legacy(events, props):
    """Preserve archived schema-v1 parsing without certifying piece metrics."""
    expands = _events_of_kind(events, "expand")
    images = _events_of_kind(events, "image")
    partitions = _events_of_kind(events, "partition")
    pruned = _events_of_kind(events, "pruned_deadends")
    heuristic = _only(events, "heuristic")
    construction = _only(events, "construction")
    done = _only(events, "done")
    summaries = _events_of_kind(events, "summary")
    summary = summaries[-1] if summaries else None

    props["raw_metrics_complete"] = summary is not None
    props["piece_metrics_certified"] = False
    if done is not None:
        planner_cost = props.get("solution_cost")
        logged_cost = done.get("solution_cost")
        if planner_cost is not None and planner_cost != logged_cost:
            message = (
                "legacy done.solution_cost={} != planner output {}".format(
                    logged_cost, planner_cost))
            _append_validation_error(props, message)
            _invalidate_outcome(props, [message])
        else:
            props["effort"] = done.get("effort")
            if planner_cost is None:
                props["solution_cost"] = logged_cost
    if expands:
        completed = [event for event in expands
                     if event.get("completed", True)]
        props["peak_bdd_nodes"] = max(e["bdd_nodes"] for e in expands)
        props["attempted_bdd_nodes"] = sum(
            e["bdd_nodes"] for e in expands)
        props["attempted_states"] = sum(e["states"] for e in expands)
        props["bucket_expansion_attempts"] = len(expands)
        if all("piece_count" in e for e in expands):
            props["attempted_bdd_pieces"] = sum(
                e["piece_count"] for e in expands)
        props["expanded_bdd_nodes"] = sum(
            e["bdd_nodes"] for e in completed)
        props["expanded_states"] = sum(e["states"] for e in completed)
        props["bucket_expansions"] = len(completed)
        if all("piece_count" in e for e in completed):
            props["expanded_bdd_pieces"] = sum(
                e["piece_count"] for e in completed)
        props["bucket_images"] = len(expands)
        props["image_time"] = sum(e["image_time"] for e in expands)
    if images:
        props["image_events"] = len(images)
        props["bucket_images"] = sum(
            e.get("calls_completed", 1) for e in images)
        props["image_source_buckets"] = sum(
            e["source_buckets"] for e in images)
        props["image_source_pieces"] = sum(
            e.get("source_pieces", 1) for e in images)
        props["image_calls_attempted"] = sum(
            e.get("calls_attempted", 1) for e in images)
        props["image_calls_completed"] = sum(
            e.get("calls_completed", 1) for e in images)
        props["batched_images"] = sum(
            e["source_buckets"] > 1 for e in images)
        props["image_time"] = sum(e["image_time"] for e in images)
    if summary is not None:
        for key in _METRIC_KEYS:
            if key in summary:
                props[key] = summary[key]
        if "bucket_expansions" not in summary and "bucket_images" in summary:
            props["bucket_expansions"] = summary["bucket_images"]
        if "image_events" not in summary and "bucket_images" in summary:
            props["image_events"] = summary["bucket_images"]
        if ("image_source_buckets" not in summary
                and "bucket_images" in summary):
            props["image_source_buckets"] = summary["bucket_images"]

    # Legacy event shapes predate exact validation, so use their optional
    # fields defensively rather than passing them to the v2 common helper.
    if heuristic is not None:
        props["width_upper_bound"] = heuristic.get("width_upper_bound")
        props["num_values"] = heuristic.get("num_values")
        if "num_terminals" in heuristic:
            props["num_terminals"] = heuristic["num_terminals"]
        props["add_nodes"] = heuristic.get("add_nodes")
    if construction is not None:
        props["heuristic_kind"] = construction.get("heuristic")
        props["construction_time"] = construction.get("seconds")
        props["heuristic_size_bound"] = construction.get("size_bound")
        props["value_cap"] = construction.get("value_cap")
        props["construction_completed"] = construction.get("completed")
    props["num_pruned_deadends"] = len(pruned)
    props["pruned_deadend_states"] = sum(
        event.get("states", 0) for event in pruned)
    props["pruned_deadend_bdd_nodes"] = sum(
        event.get("bdd_nodes", 0) for event in pruned)
    ratios = _partition_ratios(partitions)
    if ratios:
        props["partition_ratio_max"] = max(ratios)
        props["partition_ratio_geomean"] = (
            0 if any(ratio == 0 for ratio in ratios)
            else math.exp(sum(math.log(ratio) for ratio in ratios)
                          / len(ratios)))
        props["frag_ratio_max"] = props["partition_ratio_max"]
        props["frag_ratio_geomean"] = props["partition_ratio_geomean"]


def parse_wbh_log(content, props):
    props["metrics_validation_protocol"] = METRICS_VALIDATION_PROTOCOL
    events = []
    parse_errors = []
    for lineno, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except (json.JSONDecodeError, ValueError) as err:
            # A killed run can leave a truncated line. Keep parsing diagnostics,
            # but never certify a v2 stream after silently dropping that line.
            parse_errors.append(f"wbh.jsonl:{lineno}: malformed JSON: {err}")
            continue
        events.append(event)

    schemas = _events_of_kind(events, "schema")
    schema = schemas[-1] if schemas else None
    _set_schema_properties(props, schema)
    # "Legacy" means schema-less. Any explicit schema is a certification
    # claim and must match the frozen v2 contract; an unknown/corrupt version
    # must never fall through to summary-trusting legacy parsing.
    if schemas:
        _parse_v2(events, parse_errors, props)
    else:
        _parse_legacy(events, props)
        if parse_errors:
            _append_validation_error(props, " | ".join(parse_errors))

    if (props["piece_metrics_certified"]
            and "expanded_bdd_pieces" in props
            and "bucket_expansions" in props):
        # This certifies when the stored piece-sum equals a single BDD per
        # logical expansion. It does not claim sharing across expansions.
        props["expanded_buckets_single_piece"] = (
            props["expanded_bdd_pieces"] == props["bucket_expansions"])


def parse_coverage(content, props):
    props["coverage"] = 1 if "Solution found" in content else 0


def get_parser():
    from lab.parser import Parser
    parser = Parser()
    parser.add_pattern(
        "solution_cost", r"Plan cost: (\d+)", type=int, required=False)
    parser.add_pattern(
        "total_time", r"Total time: (.+)s", type=float, required=False)
    parser.add_function(parse_coverage, file="run.log")
    parser.add_function(parse_wbh_log, file="wbh.jsonl")
    return parser
