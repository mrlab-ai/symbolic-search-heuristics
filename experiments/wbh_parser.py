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
import re
import stat
from pathlib import Path

from lab.parser import Parser

try:
    from validate_wbh_log import load_json_line, validate_v2_events
except ImportError:
    # Supports importing this module from the repository root in focused tests.
    from experiments.validate_wbh_log import load_json_line, validate_v2_events


METRICS_VALIDATION_PROTOCOL = "wbh-exact-schema-semantic-v3"


_PLAN_COST_LINE_RE = re.compile(
    r"^\[t=\d+\.\d{6}s, \d+ KB\] Plan cost: (0|[1-9][0-9]*)$",
    re.MULTILINE,
)
_PLAN_FILE_COST_RE = re.compile(
    r"^; cost = (0|[1-9][0-9]*) \((?:unit|general) cost\)$"
)
_SEARCH_RAW_EXIT_RE = re.compile(r"^search raw exit code: (-?[0-9]+)$")
_SEARCH_EFFECTIVE_EXIT_RE = re.compile(r"^search exit code: (-?[0-9]+)$")
_SEARCH_RECONCILIATION_RE = re.compile(
    r"^search resource-limit exit with complete plan: "
    r"raw_exit_code=(-?[0-9]+) effective_exit_code=(-?[0-9]+)$"
)
_MAPPED_RESOURCE_EXITS = {22: 1, 23: 2, 24: 3}


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


def _recover_mapped_resource_plan(run_dir, props):
    """Recover coverage when post-solution profiling consumes the time limit.

    The direct driver promotes a raw resource exit only after a complete plan
    has been written.  Usually the search log also contains a timestamped
    ``Plan cost`` line.  That line is emitted after terminal profiling,
    however, so a resource signal during profiling can leave the canonical
    plan and exact raw/effective mapping without the later line.  Accept only
    that narrow case, using one stable, single-link regular ``sas_plan`` with
    one canonical final cost footer.  The WBH parser subsequently checks the
    recovered cost against its done event and solved summary.
    """
    effective = props.get("planner_exit_code")
    if props.get("coverage") != 0 or effective not in (1, 2, 3):
        return

    root = Path(run_dir).resolve()
    try:
        run_log = (root / "run.log").read_text(encoding="utf-8")
        entries = list(root.iterdir())
    except (OSError, UnicodeError):
        return
    lines = run_log.splitlines()
    raw = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := _SEARCH_RAW_EXIT_RE.fullmatch(line)) is not None
    ]
    final = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := _SEARCH_EFFECTIVE_EXIT_RE.fullmatch(line)) is not None
    ]
    mapped = [
        (index, match)
        for index, line in enumerate(lines)
        if (match := _SEARCH_RECONCILIATION_RE.fullmatch(line)) is not None
    ]
    if not (len(raw) == len(final) == len(mapped) == 1):
        return
    raw_index, raw_match = raw[0]
    marker_index, marker_match = mapped[0]
    final_index, final_match = final[0]
    raw_code = int(raw_match.group(1))
    final_code = int(final_match.group(1))
    marker_codes = (int(marker_match.group(1)), int(marker_match.group(2)))
    if not (
        raw_index < marker_index < final_index
        and _MAPPED_RESOURCE_EXITS.get(raw_code) == effective
        and final_code == effective
        and marker_codes == (raw_code, effective)
    ):
        return

    candidates = [
        path
        for path in entries
        if path.name == "sas_plan"
        or (
            path.name.startswith("sas_plan.")
            and path.name[len("sas_plan."):].isdigit()
        )
    ]
    if len(candidates) != 1 or candidates[0].name != "sas_plan":
        return
    plan = candidates[0]
    try:
        before = plan.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            return
        content = plan.read_text(encoding="utf-8")
        after = plan.lstat()
    except (OSError, UnicodeError):
        return
    identity = lambda value: (
        value.st_dev,
        value.st_ino,
        value.st_mode,
        value.st_nlink,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
    if identity(before) != identity(after) or not content.endswith("\n"):
        return
    cost_lines = [
        match
        for line in content.splitlines()
        if (match := _PLAN_FILE_COST_RE.fullmatch(line)) is not None
    ]
    if len(cost_lines) != 1 or not _PLAN_FILE_COST_RE.fullmatch(
        content.splitlines()[-1]
    ):
        return

    props["coverage"] = 1
    props["solution_cost"] = int(cost_lines[0].group(1))
    props["wbh_resource_plan_recovered"] = True


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
    props["wbh_summary_solved"] = (
        summary["solved"] if summary is not None else None
    )
    props["wbh_done_solution_cost"] = (
        done["solution_cost"] if done is not None else None
    )
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
    props["wbh_solved_summary_certified"] = bool(
        report["summary_present"]
        and summary is not None
        and summary["solved"] is True
        and done is not None
        and not errors
    )
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
    props["wbh_log_nonempty"] = any(
        line.strip() for line in content.splitlines()
    )
    events = []
    parse_errors = []
    for lineno, line in enumerate(content.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            event = load_json_line(line)
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
            props["raw_metrics_complete"] = False
            _append_validation_error(props, " | ".join(parse_errors))

    if (props["piece_metrics_certified"]
            and "expanded_bdd_pieces" in props
            and "bucket_expansions" in props):
        # This certifies when the stored piece-sum equals a single BDD per
        # logical expansion. It does not claim sharing across expansions.
        props["expanded_buckets_single_piece"] = (
            props["expanded_bdd_pieces"] == props["bucket_expansions"])


def parse_coverage(content, props):
    """Preserve Lab's coverage while requiring exact unique plan evidence.

    A direct symbolic search can save and print a complete plan immediately
    before a resource-limit exit.  Such a run has a canonical ``Plan cost``
    line but never reaches the later ``Solution found`` message, so that
    message cannot define coverage.  The standard single-search parser runs
    first and derives coverage from its parsed cost; this function verifies
    that result against the stricter run-log grammar instead of overwriting it.
    """
    plan_cost_mentions = [
        line for line in content.splitlines() if "Plan cost:" in line
    ]
    matches = list(_PLAN_COST_LINE_RE.finditer(content))
    errors = []
    if not plan_cost_mentions:
        derived_coverage = (
            1 if props.get("wbh_resource_plan_recovered") is True else 0
        )
    elif len(plan_cost_mentions) == 1 and len(matches) == 1:
        derived_coverage = 1
        exact_cost = int(matches[0].group(1))
        parsed_cost = props.get("solution_cost")
        if type(parsed_cost) is not int or parsed_cost != exact_cost:
            errors.append(
                "exact run-log Plan cost {} disagrees with parsed solution_cost "
                "{!r}".format(exact_cost, parsed_cost)
            )
    else:
        derived_coverage = None
        errors.append(
            "expected zero or one exact timestamped Plan cost line; got {} "
            "mentions and {} exact matches".format(
                len(plan_cost_mentions), len(matches)
            )
        )

    existing_coverage = props.get("coverage")
    if type(existing_coverage) is int and existing_coverage in (0, 1):
        if (derived_coverage is not None
                and existing_coverage != derived_coverage):
            errors.append(
                "single-search coverage {} disagrees with exact Plan cost "
                "coverage {}".format(existing_coverage, derived_coverage)
            )
    elif existing_coverage is not None:
        errors.append(
            "single-search coverage is not the integer 0 or 1: {!r}".format(
                existing_coverage
            )
        )

    if errors:
        props["coverage"] = None
        message = "run-log coverage validation failed: " + " | ".join(errors)
        add_error = getattr(props, "add_unexplained_error", None)
        if callable(add_error):
            add_error(message)
        else:
            props.setdefault("unexplained_errors", []).append(message)
    else:
        props["coverage"] = derived_coverage


class WbhParser(Parser):
    """Lab parser that materializes the exact missing/empty WBH convention."""

    def parse(self, run_dir, props):
        _recover_mapped_resource_plan(run_dir, props)
        super().parse(run_dir, props)
        # Lab deliberately skips functions for missing and zero-byte files.
        # Those are meaningful pre-search outcomes in this protocol, so emit
        # the same explicit empty-log properties as parse_wbh_log("").  The
        # second read also handles a file that appeared after Lab's first read.
        # metrics_validation_protocol is also a static run property, so the
        # parser-owned presence marker is the only reliable completion flag.
        if "wbh_log_nonempty" not in props:
            path = Path(run_dir).resolve() / "wbh.jsonl"
            try:
                content = path.read_text()
            except FileNotFoundError:
                content = ""
            parse_wbh_log(content, props)


def get_parser():
    parser = WbhParser()
    parser.add_pattern(
        "solution_cost", r"Plan cost: (\d+)", type=int, required=False)
    parser.add_pattern(
        "total_time", r"Total time: (.+)s", type=float, required=False)
    parser.add_function(parse_coverage, file="run.log")
    parser.add_function(parse_wbh_log, file="wbh.jsonl")
    return parser
