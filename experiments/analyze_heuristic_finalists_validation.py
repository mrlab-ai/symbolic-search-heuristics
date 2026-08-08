#!/usr/bin/env python3
"""Read-only analysis of the prospective reserved finalist validation.

This analysis is frozen before launch.  It performs no held-out selection and
does not rank configurations.  Its primary reserved-set statistic for every
predeclared finalist/control contrast is the paired domain-macro coverage
difference.  Suite-micro and full-suite-domain-post-stratified coverage are
descriptive; PAR2 and runtime are one-repetition screening summaries.
"""

import argparse
import hashlib
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_heuristic_choices_pilot as screen_analyzer
import analyze_ms_caps_pilot as cap_analyzer
import exp_heuristic_finalists_validation as runner
import suite_cost_manifest
import wbh_parser


TIME_LIMIT = 300.0
MEMORY_LIMIT_MIB = 8192.0
BOOTSTRAP_SEED = "symbolic-search-heuristics/domain-cluster-bootstrap/v1"
BOOTSTRAP_REPLICATES = 10000
BOOTSTRAP_METHOD = "sha256-seeded-splitmix64-percentile/v1"


class AnalysisError(Exception):
    pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze the frozen reserved finalist validation.")
    parser.add_argument(
        "properties", nargs="?",
        help="Lab properties JSON, evaluation directory, tar archive, or '-'.")
    parser.add_argument(
        "--selection", type=Path,
        help="The exact reviewed selection artifact used by the runner.")
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run deterministic synthetic analysis/provenance tests and exit.")
    return parser.parse_args(argv)


def expected_component_options(search):
    return screen_analyzer.expected_component_options(search)


def task_tuple(task):
    return tuple(task.split(":", 1))


def validate_records(
        records, tasks, configs, artifact, artifact_sha256,
        task_sources_sha256, source_manifest_sha256,
        expected_run_count=None):
    labels = [config["label"] for config in configs]
    searches = {config["label"]: config["search"] for config in configs}
    expected_cells = expected_run_count or len(tasks) * len(configs)
    matrix, structural_errors, structural_warnings = cap_analyzer.build_matrix(
        records, tasks, labels, allow_incomplete=False)
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

    solved_costs = defaultdict(list)
    outer_envelopes = set()
    static_expected = {
        "protocol": "heuristic-finalists-validation-v1",
        "task_manifest_sha256": runner.MANIFEST_DIGEST,
        "selection_artifact_sha256": artifact_sha256,
        "screen_properties_canonical_sha256":
            artifact["screen"]["properties_canonical_sha256"],
        "cap_properties_canonical_sha256":
            artifact["cap_pilot"]["properties_canonical_sha256"],
        "source_manifest_sha256": source_manifest_sha256,
        "task_sources_sha256": task_sources_sha256,
        "declared_run_count": expected_cells,
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

    for label in labels:
        for task in tasks:
            record = matrix.get((label, task))
            if record is None:
                continue
            prefix = "{} {}".format(label, cap_analyzer.task_label(task))
            outcome = cap_analyzer.outcome(record)
            if outcome is None:
                errors.append(prefix + " has invalid or missing coverage")
            cost = cap_analyzer.solution_cost(record)
            if outcome is True:
                if cost is None:
                    errors.append(prefix + " is solved without numeric solution_cost")
                else:
                    solved_costs[task].append((label, cost))
                planner_time = cap_analyzer.number(record.get("planner_time"))
                if planner_time is None or planner_time < 0:
                    errors.append(prefix + " is solved without planner_time")
            elif outcome is False and cost is not None:
                warnings.append(prefix + " is unsolved but records solution_cost")

            wanted_options = expected_component_options(searches[label])
            if record.get("component_options") != wanted_options:
                errors.append(
                    "{} has component_options {!r}; expected {!r}".format(
                        prefix, record.get("component_options"), wanted_options))
            for field in ("global_revision", "local_revision"):
                if str(record.get(field)) != runner.FROZEN_REVISION:
                    errors.append(
                        "{} has {}={!r}; expected {}".format(
                            prefix, field, record.get(field),
                            runner.FROZEN_REVISION))
            for field, expected in (
                    ("planner_time_limit", TIME_LIMIT),
                    ("planner_memory_limit", MEMORY_LIMIT_MIB)):
                value = cap_analyzer.number(record.get(field))
                if value is None or not cap_analyzer.equal_values(value, expected):
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
            if not any(cap_analyzer.equal_values(cost, old) for old in distinct):
                distinct.append(cost)
        if len(distinct) > 1:
            errors.append(
                "solved-cost disagreement on {}: {}".format(
                    cap_analyzer.task_label(task),
                    ", ".join("{}={}".format(label, cost)
                              for label, cost in entries)))
    return matrix, errors, warnings


def validation_label_for_search(configs, search):
    matches = [config["label"] for config in configs
               if config["search"] == search]
    if len(matches) != 1:
        raise AnalysisError(
            "selected search has {} validation labels".format(len(matches)))
    return matches[0]


def frozen_comparisons(artifact, configs):
    comparisons = []
    primary_cap = next(
        config["label"] for config in configs
        if config["role"] == "primary-cap")
    comparisons.append({
        "name": "reserved-context-cap-vs-exact",
        "candidate": primary_cap,
        "reference": "ms_exact",
        "status": "descriptive; primary cap estimand is on cap-v2",
    })
    for family in ("ms", "pdb", "potential"):
        finalist = artifact["family_finalists"].get(family)
        if finalist is None:
            continue
        candidate = validation_label_for_search(configs, finalist["search"])
        for reference in ("blind_fw", "ms_exact"):
            comparisons.append({
                "name": "{}-finalist-vs-{}".format(family, reference),
                "candidate": candidate,
                "reference": reference,
                "status": "secondary family-wise",
            })
    return comparisons


def bootstrap_ci(domain_means, tag):
    """Deterministic percentile CI from domain-cluster resampling.

    Domains (not tasks) are sampled with replacement.  SplitMix64 is seeded by
    SHA-256 of the frozen seed and subset tag.  The reported endpoints are the
    floor(.025*(R-1)) and ceil(.975*(R-1)) ordered replicates.
    """
    values = [domain_means[domain] for domain in sorted(domain_means)]
    if not values:
        raise AnalysisError("cannot bootstrap an empty domain set")
    state = int.from_bytes(hashlib.sha256(
        "{}\0{}".format(BOOTSTRAP_SEED, tag).encode("utf-8")).digest()[:8],
        "big")
    mask = (1 << 64) - 1

    def next_uint64():
        nonlocal state
        state = (state + 0x9E3779B97F4A7C15) & mask
        value = state
        value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & mask
        value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & mask
        return value ^ (value >> 31)

    estimates = []
    for _ in range(BOOTSTRAP_REPLICATES):
        estimates.append(statistics.mean(
            values[next_uint64() % len(values)] for _ in values))
    estimates.sort()
    lower_index = math.floor(0.025 * (BOOTSTRAP_REPLICATES - 1))
    upper_index = math.ceil(0.975 * (BOOTSTRAP_REPLICATES - 1))
    return estimates[lower_index], estimates[upper_index]


def coverage_metrics(
        matrix, candidate, reference, tasks, population_counts,
        bootstrap_tag):
    differences = []
    by_domain = defaultdict(list)
    wins = 0
    losses = 0
    for task in tasks:
        cand = cap_analyzer.outcome(matrix[(candidate, task)])
        base = cap_analyzer.outcome(matrix[(reference, task)])
        if cand is None or base is None:
            raise AnalysisError("coverage matrix is incomplete after validation")
        difference = int(cand) - int(base)
        wins += difference == 1
        losses += difference == -1
        differences.append(difference)
        by_domain[task[0]].append(difference)
    domain_means = {
        domain: statistics.mean(values) for domain, values in by_domain.items()}
    domain_macro = statistics.mean(domain_means.values())
    ci_low, ci_high = bootstrap_ci(domain_means, bootstrap_tag)
    suite_micro = statistics.mean(differences)
    represented_weight = sum(population_counts.get(domain, 0)
                             for domain in domain_means)
    if represented_weight <= 0:
        poststratified = None
    else:
        poststratified = sum(
            population_counts.get(domain, 0) * value
            for domain, value in domain_means.items()) / represented_weight
    return {
        "tasks": len(tasks),
        "domains": len(domain_means),
        "domain_macro": domain_macro,
        "ci_low": ci_low,
        "ci_high": ci_high,
        "wins": wins,
        "losses": losses,
        "suite_micro": suite_micro,
        "poststratified": poststratified,
    }


def par2(matrix, label, tasks):
    values = []
    solved = 0
    for task in tasks:
        record = matrix[(label, task)]
        if cap_analyzer.outcome(record) is True:
            solved += 1
            values.append(float(record["planner_time"]))
        else:
            values.append(2 * TIME_LIMIT)
    return solved, statistics.mean(values)


def runtime_ratio(matrix, candidate, reference, tasks):
    ratios = []
    for task in tasks:
        cand = matrix[(candidate, task)]
        base = matrix[(reference, task)]
        if (cap_analyzer.outcome(cand) is not True
                or cap_analyzer.outcome(base) is not True):
            continue
        cand_time = cap_analyzer.number(cand.get("planner_time"))
        base_time = cap_analyzer.number(base.get("planner_time"))
        if cand_time is None or base_time is None or cand_time <= 0 or base_time <= 0:
            continue
        ratios.append(cand_time / base_time)
    if not ratios:
        return None, 0
    return math.exp(sum(math.log(value) for value in ratios) / len(ratios)), len(ratios)


def population_domain_counts(population=None):
    data = suite_cost_manifest.load_manifest()
    counts = defaultdict(int)
    for record in data["tasks"]:
        include = (
            population is None
            or (population == "supported"
                and record["cost_class"] == "positive-cost"
                and record["num_normalized_axioms"] == 0)
            or (population not in (None, "supported")
                and record["cost_class"] == population))
        if include:
            counts[record["domain"]] += 1
    return counts


def print_subset(name, matrix, configs, comparisons, tasks, population_counts):
    print("\n{} ({} tasks)".format(name, len(tasks)))
    print("configuration screening summaries (one repetition)")
    for config in configs:
        solved, value = par2(matrix, config["label"], tasks)
        print("  {:22s} solved={:3d} micro-PAR2={:.6f}".format(
            config["label"], solved, value))
    print("paired coverage contrasts")
    for comparison in comparisons:
        metrics = coverage_metrics(
            matrix, comparison["candidate"], comparison["reference"],
            tasks, population_counts,
            "{}\0{}".format(name, comparison["name"]))
        ratio, ratio_n = runtime_ratio(
            matrix, comparison["candidate"], comparison["reference"], tasks)
        post = ("NA" if metrics["poststratified"] is None else
                "{:.6f}".format(metrics["poststratified"]))
        runtime = "NA" if ratio is None else "{:.6f}".format(ratio)
        print(
            "  {name}: domain-macro={macro:.6f} "
            "95%-cluster-CI=[{low:.6f},{high:.6f}] [D={domains}], "
            "discordant wins/losses={wins}/{losses}, "
            "suite-micro(desc)={micro:.6f}, poststratified(desc)={post}, "
            "runtime-geomean(screen)={runtime} [n={n}] -- {status}".format(
                name=comparison["name"], macro=metrics["domain_macro"],
                low=metrics["ci_low"], high=metrics["ci_high"],
                domains=metrics["domains"], micro=metrics["suite_micro"],
                wins=metrics["wins"], losses=metrics["losses"],
                post=post, runtime=runtime, n=ratio_n,
                status=comparison["status"]))


def synthetic_record(label, search, task, coverage, cost, planner_time,
                     artifact, artifact_sha256, run_count):
    domain, problem = task
    return {
        "_source_key": "{}-{}-{}".format(label, domain, problem),
        "algorithm": label, "domain": domain, "problem": problem,
        "coverage": coverage,
        "solution_cost": cost if coverage else None,
        "planner_time": planner_time if coverage else None,
        "component_options": expected_component_options(search),
        "global_revision": runner.FROZEN_REVISION,
        "local_revision": runner.FROZEN_REVISION,
        "planner_time_limit": TIME_LIMIT,
        "planner_memory_limit": MEMORY_LIMIT_MIB,
        "driver_options": ["--overall-time-limit", "300s",
                           "--overall-memory-limit", "8G"],
        "protocol": "heuristic-finalists-validation-v1",
        "task_manifest_sha256": runner.MANIFEST_DIGEST,
        "selection_artifact_sha256": artifact_sha256,
        "screen_properties_canonical_sha256":
            artifact["screen"]["properties_canonical_sha256"],
        "cap_properties_canonical_sha256":
            artifact["cap_pilot"]["properties_canonical_sha256"],
        "source_manifest_sha256": "3" * 64,
        "task_sources_sha256": "4" * 64,
        "declared_run_count": run_count,
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
    configs = [
        {"label": "blind_fw", "search": "sym_fw()"},
        {"label": "ms_exact", "search": dict(screen_analyzer.CONFIGS)["ms_exact"]},
        {"label": "pdb_goal_w4", "search": dict(screen_analyzer.CONFIGS)["pdb_goal_w4"]},
    ]
    artifact = runner.template_artifact()
    artifact["screen"]["properties_canonical_sha256"] = "1" * 64
    artifact["cap_pilot"]["properties_canonical_sha256"] = "2" * 64
    artifact_sha256 = "5" * 64
    coverage = {
        "blind_fw": [1, 0, 1, 0],
        "ms_exact": [1, 1, 1, 1],
        "pdb_goal_w4": [1, 1, 0, 1],
    }
    run_count = len(tasks) * len(configs)
    records = []
    for config in configs:
        for index, task in enumerate(tasks):
            records.append(synthetic_record(
                config["label"], config["search"], task,
                coverage[config["label"]][index], 7, 10 + index,
                artifact, artifact_sha256, run_count))
    matrix, errors, _ = validate_records(
        records, tasks, configs, artifact, artifact_sha256,
        "4" * 64, "3" * 64, expected_run_count=run_count)
    assert not errors, errors
    metric = coverage_metrics(
        matrix, "pdb_goal_w4", "blind_fw", tasks, {"d1": 3, "d2": 1},
        "synthetic")
    assert math.isclose(metric["domain_macro"], 0.25)
    assert math.isclose(metric["suite_micro"], 0.25)
    assert math.isclose(metric["poststratified"], 0.375)
    assert (metric["wins"], metric["losses"]) == (2, 1)
    repeated = coverage_metrics(
        matrix, "pdb_goal_w4", "blind_fw", tasks, {"d1": 3, "d2": 1},
        "synthetic")
    assert (metric["ci_low"], metric["ci_high"]) == (
        repeated["ci_low"], repeated["ci_high"])

    records[0]["scheduler_qos"] = ""
    _, errors, _ = validate_records(
        records, tasks, configs, artifact, artifact_sha256,
        "4" * 64, "3" * 64, expected_run_count=run_count)
    assert any("scheduler_qos" in error for error in errors)
    records[0]["scheduler_qos"] = "devel"

    records[0]["scheduler_array_task_throttle"] = 0
    _, errors, _ = validate_records(
        records, tasks, configs, artifact, artifact_sha256,
        "4" * 64, "3" * 64, expected_run_count=run_count)
    assert any("scheduler_array_task_throttle" in error for error in errors)
    records[0]["scheduler_array_task_throttle"] = 5

    del records[0]["metrics_validation_protocol"]
    _, errors, _ = validate_records(
        records, tasks, configs, artifact, artifact_sha256,
        "4" * 64, "3" * 64, expected_run_count=run_count)
    assert any("metrics_validation_protocol" in error for error in errors)
    records[0]["metrics_validation_protocol"] = (
        wbh_parser.METRICS_VALIDATION_PROTOCOL)

    # A disagreement on a jointly solved task must stop all reporting.
    target = next(record for record in records
                  if record["algorithm"] == "ms_exact"
                  and record["domain"] == "d1" and record["problem"] == "p1")
    target["solution_cost"] = 8
    _, errors, _ = validate_records(
        records, tasks, configs, artifact, artifact_sha256,
        "4" * 64, "3" * 64, expected_run_count=run_count)
    assert any("solved-cost disagreement" in error for error in errors)
    print("synthetic reserved-analysis tests: PASS "
          "(provenance, cost gate, domain-macro, wins/losses, "
          "deterministic CI, micro, poststratification)")


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if args.properties is None or args.selection is None:
        raise AnalysisError("properties and --selection are required")

    task_labels, task_sources_sha256, source_manifest_sha256 = (
        runner.validate_manifest_and_paths())
    _, screen_task_sources_sha256, screen_source_manifest_sha256 = (
        runner.validate_screen_manifest_and_paths())
    artifact, artifact_sha256 = runner.load_artifact(args.selection)
    configs = runner.validate_artifact(
        artifact,
        expected_task_sources_sha256=task_sources_sha256,
        expected_source_manifest_sha256=source_manifest_sha256,
        expected_screen_task_sources_sha256=screen_task_sources_sha256,
        expected_screen_source_manifest_sha256=screen_source_manifest_sha256)
    records, source = cap_analyzer.load_properties(args.properties)
    tasks = [task_tuple(task) for task in task_labels]
    matrix, errors, warnings = validate_records(
        records, tasks, configs, artifact, artifact_sha256,
        task_sources_sha256, source_manifest_sha256,
        expected_run_count=artifact["validation"]["expected_run_count"])
    if errors:
        raise AnalysisError(
            "reserved validation failed ({} errors): {}".format(
                len(errors), "; ".join(errors)))

    supported = suite_cost_manifest.supported_tasks()
    if not set(tasks) <= supported:
        raise AnalysisError(
            "reserved set contains tasks outside the frozen supported "
            "positive-cost, axiom-free population")
    comparisons = frozen_comparisons(artifact, configs)

    print("Reserved finalist validation: {}".format(source))
    print("selection artifact SHA-256: {}".format(artifact_sha256))
    print("No held-out selection or ranking is performed by this analyzer.")
    print("The cap-vs-exact primary estimand remains the independent cap-v2 set.")
    print("domain CI: {} replicates, seed={!r}, method={}".format(
        BOOTSTRAP_REPLICATES, BOOTSTRAP_SEED, BOOTSTRAP_METHOD))
    print_subset(
        "supported positive-cost, axiom-free reserved set (PRIMARY)",
        matrix, configs, comparisons, tasks,
        population_domain_counts("supported"))
    print("\nPASS: exact matrix/artifact/revision/limits/source bytes and solved "
          "cost agreement validated.")
    for warning in warnings:
        print("WARNING: " + warning)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AnalysisError, runner.ProtocolError, cap_analyzer.AnalysisError,
            RuntimeError) as err:
        print("analysis error: {}".format(err), file=sys.stderr)
        sys.exit(2)
