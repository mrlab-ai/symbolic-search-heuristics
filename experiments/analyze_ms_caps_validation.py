#!/usr/bin/env python3
"""Frozen read-only analysis of the 92-task cap-v2 validation.

The primary K is derived only from the separately frozen 50-task cap pilot.
On cap-v2, selected-K versus exact M&S is the sole primary contrast;
selected-K versus blind is secondary and every nonselected K is exploratory.
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_heuristic_choices_pilot as screen_analyzer
import analyze_heuristic_finalists_validation as analysis_common
import analyze_ms_caps_pilot as cap_pilot_analyzer
import exp_ms_caps_validation as cap_v2
import suite_cost_manifest
import wbh_parser


TIME_LIMIT = 300.0
MEMORY_LIMIT_MIB = 8192.0


class AnalysisError(Exception):
    pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze the frozen 92-task cap-v2 experiment.")
    parser.add_argument(
        "properties", nargs="?",
        help="Cap-v2 Lab properties JSON, evaluation directory, tar, or '-'.")
    parser.add_argument(
        "--cap-properties",
        help="Frozen ec839 50-task cap-pilot properties used to derive K.")
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run deterministic synthetic selection/analysis tests and exit.")
    return parser.parse_args(argv)


def validate_records(
        records, tasks, task_sources_sha256, source_manifest_sha256,
        expected_run_count=None):
    labels = [label for label, _ in cap_v2.CONFIGS]
    searches = dict(cap_v2.CONFIGS)
    expected_cells = expected_run_count or len(tasks) * len(labels)
    matrix, structural_errors, structural_warnings = (
        cap_pilot_analyzer.build_matrix(
            records, tasks, labels, allow_incomplete=False))
    errors = list(structural_errors) + list(structural_warnings)
    warnings = []
    if len(records) != expected_cells:
        errors.append(
            "properties contain {} records; expected exactly {}".format(
                len(records), expected_cells))
    if len(matrix) != expected_cells:
        errors.append(
            "matrix contains {} cells; expected exactly {}".format(
                len(matrix), expected_cells))

    static_expected = {
        "protocol": "ms-caps-validation-v2",
        "task_manifest_sha256": cap_v2.MANIFEST_DIGEST,
        "declared_run_count": expected_cells,
        "option_matrix_sha256": cap_v2.OPTION_MATRIX_DIGEST,
        "cap_selection_rule": cap_v2.CAP_SELECTION_RULE,
        "source_manifest_sha256": source_manifest_sha256,
        "task_sources_sha256": task_sources_sha256,
        "task_order_seed": screen_analyzer.TASK_ORDER_SEED,
        "task_order_method": screen_analyzer.TASK_ORDER_METHOD,
        "driver_time_limit": "300s",
        "driver_memory_limit": "8G",
        "scheduler_environment": "tetralith-slurm",
        "scheduler_account": "naiss2025-5-382",
        "scheduler_cpus_per_task": 1,
        "scheduler_array_task_throttle": 5,
        "repetitions": 1,
        "metrics_validation_protocol":
            wbh_parser.METRICS_VALIDATION_PROTOCOL,
    }
    solved_costs = defaultdict(list)
    outer_envelopes = set()
    for label in labels:
        for task in tasks:
            record = matrix.get((label, task))
            if record is None:
                continue
            prefix = "{} {}".format(
                label, cap_pilot_analyzer.task_label(task))
            outcome = cap_pilot_analyzer.outcome(record)
            if outcome is None:
                errors.append(prefix + " has invalid or missing coverage")
            cost = cap_pilot_analyzer.solution_cost(record)
            if outcome is True:
                if cost is None:
                    errors.append(prefix + " is solved without numeric solution_cost")
                else:
                    solved_costs[task].append((label, cost))
                runtime = cap_pilot_analyzer.number(record.get("planner_time"))
                if runtime is None or runtime < 0:
                    errors.append(prefix + " is solved without planner_time")
            elif outcome is False and cost is not None:
                warnings.append(prefix + " is unsolved but records solution_cost")

            wanted = screen_analyzer.expected_component_options(searches[label])
            if record.get("component_options") != wanted:
                errors.append(
                    "{} has component_options {!r}; expected {!r}".format(
                        prefix, record.get("component_options"), wanted))
            for field in ("global_revision", "local_revision"):
                if str(record.get(field)) != cap_v2.FROZEN_REVISION:
                    errors.append(
                        "{} has {}={!r}; expected {}".format(
                            prefix, field, record.get(field),
                            cap_v2.FROZEN_REVISION))
            for field, expected in (
                    ("planner_time_limit", TIME_LIMIT),
                    ("planner_memory_limit", MEMORY_LIMIT_MIB)):
                value = cap_pilot_analyzer.number(record.get(field))
                if value is None or not cap_pilot_analyzer.equal_values(
                        value, expected):
                    errors.append(
                        "{} has {}={!r}; expected {}".format(
                            prefix, field, record.get(field), expected))
            for option, expected in (
                    ("--overall-time-limit", "300s"),
                    ("--overall-memory-limit", "8G")):
                value = screen_analyzer.last_driver_option(record, option)
                if value != expected:
                    errors.append(
                        "{} has driver {} {!r}; expected {!r}".format(
                            prefix, option, value, expected))
            for field, expected in static_expected.items():
                if record.get(field) != expected:
                    errors.append(
                        "{} has {}={!r}; expected {!r}".format(
                            prefix, field, record.get(field), expected))
            outer = (
                record.get("scheduler_qos"),
                record.get("scheduler_time_limit_per_task"),
                record.get("scheduler_memory_per_cpu"),
            )
            outer_envelopes.add(outer)
            if not isinstance(outer[0], str) or not outer[0]:
                errors.append(prefix + " lacks scheduler_qos")
            duration = screen_analyzer.parse_duration_seconds(outer[1])
            if duration is None or duration < TIME_LIMIT:
                errors.append(prefix + " has inadequate scheduler time")
            memory = screen_analyzer.parse_memory_mib(outer[2])
            if memory is None or memory < MEMORY_LIMIT_MIB:
                errors.append(prefix + " has inadequate scheduler memory")

    if len(outer_envelopes) > 1:
        errors.append("records disagree on the outer scheduler envelope")
    for task, entries in sorted(solved_costs.items()):
        distinct = []
        for _, cost in entries:
            if not any(cap_pilot_analyzer.equal_values(cost, old)
                       for old in distinct):
                distinct.append(cost)
        if len(distinct) > 1:
            errors.append(
                "solved-cost disagreement on {}: {}".format(
                    cap_pilot_analyzer.task_label(task),
                    ", ".join("{}={}".format(label, cost)
                              for label, cost in entries)))
    return matrix, errors, warnings


def comparisons(selected_cap):
    selected = "ms_cap{}".format(selected_cap)
    result = [
        {"name": "selected-cap-vs-exact", "candidate": selected,
         "reference": "ms_exact", "status": "PRIMARY on cap-v2"},
        {"name": "selected-cap-vs-blind", "candidate": selected,
         "reference": "blind_fw", "status": "secondary"},
    ]
    for cap in cap_v2.CAPS:
        if cap == selected_cap:
            continue
        result.append({
            "name": "nonselected-cap{}-vs-exact".format(cap),
            "candidate": "ms_cap{}".format(cap),
            "reference": "ms_exact", "status": "exploratory",
        })
    return result


def print_subset(name, matrix, tasks, selected_cap, population_counts):
    configs = [
        {"label": label, "search": search}
        for label, search in cap_v2.CONFIGS]
    analysis_common.print_subset(
        name, matrix, configs, comparisons(selected_cap), tasks,
        population_counts)


def synthetic_record(
        label, search, task, coverage, cost, runtime, run_count):
    domain, problem = task
    return {
        "_source_key": "{}-{}-{}".format(label, domain, problem),
        "algorithm": label, "domain": domain, "problem": problem,
        "coverage": coverage,
        "solution_cost": cost if coverage else None,
        "planner_time": runtime if coverage else None,
        "component_options": screen_analyzer.expected_component_options(search),
        "global_revision": cap_v2.FROZEN_REVISION,
        "local_revision": cap_v2.FROZEN_REVISION,
        "planner_time_limit": TIME_LIMIT,
        "planner_memory_limit": MEMORY_LIMIT_MIB,
        "driver_options": ["--overall-time-limit", "300s",
                           "--overall-memory-limit", "8G"],
        "protocol": "ms-caps-validation-v2",
        "task_manifest_sha256": cap_v2.MANIFEST_DIGEST,
        "declared_run_count": run_count,
        "option_matrix_sha256": cap_v2.OPTION_MATRIX_DIGEST,
        "cap_selection_rule": cap_v2.CAP_SELECTION_RULE,
        "source_manifest_sha256": "3" * 64,
        "task_sources_sha256": "4" * 64,
        "task_order_seed": screen_analyzer.TASK_ORDER_SEED,
        "task_order_method": screen_analyzer.TASK_ORDER_METHOD,
        "driver_time_limit": "300s", "driver_memory_limit": "8G",
        "scheduler_environment": "tetralith-slurm",
        "scheduler_account": "naiss2025-5-382",
        "scheduler_cpus_per_task": 1,
        "scheduler_array_task_throttle": 5, "scheduler_qos": "devel",
        "scheduler_time_limit_per_task": "00:10:00",
        "scheduler_memory_per_cpu": "9G", "repetitions": 1,
        "metrics_validation_protocol":
            wbh_parser.METRICS_VALIDATION_PROTOCOL,
    }


def self_test():
    tasks = [("d1", "p1"), ("d1", "p2"), ("d2", "p1"), ("d2", "p2")]
    run_count = len(tasks) * len(cap_v2.CONFIGS)
    records = []
    for label, search in cap_v2.CONFIGS:
        for index, task in enumerate(tasks):
            # Give cap 4 one unique solve; all solved costs remain equal.
            solved = index < 2 or (label == "ms_cap4" and index == 2)
            records.append(synthetic_record(
                label, search, task, int(solved), 9, 10 + index, run_count))
    matrix, errors, _ = validate_records(
        records, tasks, "4" * 64, "3" * 64,
        expected_run_count=run_count)
    assert not errors, errors

    # Exercise the frozen cap-pilot rule without reading real pilot outcomes.
    pilot_matrix = {}
    for label in cap_pilot_analyzer.ALGORITHMS:
        for index, task in enumerate(tasks):
            coverage = int(index < 2 or (label == "ms_cap4" and index == 2))
            pilot_matrix[(label, task)] = {
                "coverage": coverage,
                "planner_time": 10 + index if coverage else None,
            }
    selected, _ = cap_pilot_analyzer.select_primary_cap(
        pilot_matrix, tasks, TIME_LIMIT)
    assert selected == 4
    metric = analysis_common.coverage_metrics(
        matrix, "ms_cap4", "ms_exact", tasks, {"d1": 3, "d2": 1},
        "cap-v2-synthetic")
    repeated = analysis_common.coverage_metrics(
        matrix, "ms_cap4", "ms_exact", tasks, {"d1": 3, "d2": 1},
        "cap-v2-synthetic")
    assert (metric["wins"], metric["losses"]) == (1, 0)
    assert (metric["ci_low"], metric["ci_high"]) == (
        repeated["ci_low"], repeated["ci_high"])

    target = next(record for record in records
                  if record["algorithm"] == "ms_cap4"
                  and record["domain"] == "d1" and record["problem"] == "p1")
    target["solution_cost"] = 10
    _, errors, _ = validate_records(
        records, tasks, "4" * 64, "3" * 64,
        expected_run_count=run_count)
    assert any("solved-cost disagreement" in error for error in errors)
    target["solution_cost"] = 9

    records[0]["scheduler_array_task_throttle"] = 4
    _, errors, _ = validate_records(
        records, tasks, "4" * 64, "3" * 64,
        expected_run_count=run_count)
    assert any("scheduler_array_task_throttle" in error for error in errors)
    records[0]["scheduler_array_task_throttle"] = 5

    del records[0]["metrics_validation_protocol"]
    _, errors, _ = validate_records(
        records, tasks, "4" * 64, "3" * 64,
        expected_run_count=run_count)
    assert any("metrics_validation_protocol" in error for error in errors)
    records[0]["metrics_validation_protocol"] = (
        wbh_parser.METRICS_VALIDATION_PROTOCOL)
    print("synthetic cap-v2 analysis tests: PASS "
          "(pilot selection, provenance, costs, wins/losses, deterministic CI)")


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if args.properties is None or args.cap_properties is None:
        raise AnalysisError("properties and --cap-properties are required")

    selected_cap, pilot_digest, pilot_source, pilot_warnings = (
        screen_analyzer.validate_cap_source(args.cap_properties))
    task_labels, task_sources_sha256, source_manifest_sha256 = (
        cap_v2.validate_manifest())
    tasks = [tuple(task.split(":", 1)) for task in task_labels]
    records, source = cap_pilot_analyzer.load_properties(args.properties)
    matrix, errors, warnings = validate_records(
        records, tasks, task_sources_sha256, source_manifest_sha256,
        expected_run_count=cap_v2.EXPECTED_RUNS)
    if errors:
        raise AnalysisError(
            "cap-v2 validation failed ({} errors): {}".format(
                len(errors), "; ".join(errors)))

    supported = suite_cost_manifest.supported_tasks()
    if not set(tasks) <= supported:
        raise AnalysisError(
            "cap-v2 contains tasks outside the frozen supported positive-cost, "
            "axiom-free population")

    print("Cap-v2 validation: {}".format(source))
    print("cap-pilot source: {}".format(pilot_source))
    print("cap-pilot canonical properties SHA-256: {}".format(pilot_digest))
    print("pilot-derived primary cap: K={}".format(selected_cap))
    print("domain CI: {} replicates, seed={!r}, method={}".format(
        analysis_common.BOOTSTRAP_REPLICATES,
        analysis_common.BOOTSTRAP_SEED,
        analysis_common.BOOTSTRAP_METHOD))
    print_subset(
        "supported positive-cost, axiom-free cap-v2 set (PRIMARY)",
        matrix, tasks, selected_cap,
        analysis_common.population_domain_counts("supported"))
    print("\nPASS: pilot selection, exact cap-v2 matrix/provenance/source bytes "
          "and solved costs validated.")
    for warning in pilot_warnings + warnings:
        print("WARNING: " + warning)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AnalysisError, cap_pilot_analyzer.AnalysisError, RuntimeError) as err:
        print("analysis error: {}".format(err), file=sys.stderr)
        sys.exit(2)
