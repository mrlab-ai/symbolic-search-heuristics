#!/usr/bin/env python3
"""Validate and rank the frozen 1050-cell heuristic-choice screen.

The analyzer is read-only.  It validates every static run field before using
outcomes, rejects solved-cost disagreements, treats every unsolved run as the
frozen 600-second PAR2 penalty, and never treats partial work counters as
complete.  One finalist is selected independently in each of the M&S, PDB,
and potential families.

After both pilots finish, ``--emit-selection-artifact`` combines this screen
with the independently selected M&S cap and prints the complete prospective
validation artifact to stdout.  Redirect that output to a new, reviewed file;
this script never creates or modifies it.
"""

import argparse
import hashlib
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_ms_caps_pilot as cap_analyzer
import exp_heuristic_choices_pilot as screen_runner
import wbh_parser


FROZEN_REVISION = "c2800d7e65abb61d4b94b08a5487f701ceb41d6b"
CAP_PILOT_REVISION = "ec8399257de93e0739046a187af4bed0b85e19ce"
MANIFEST = SCRIPT_DIR / "ms_caps_pilot_suite.txt"
MANIFEST_DIGEST = "c63a59ee2096b40c24f80db895ee2c0d22aabc2630c823b882e7f50f529a481b"
VALIDATION_MANIFEST_DIGEST = (
    "fc63d4eed62816a2e065cb89f89483999a7b51067b7077969d10b2a338f19760")
VALIDATION_MANIFEST = SCRIPT_DIR / "heuristic_finalists_validation_suite.txt"
TASK_ORDER_SEED = "symbolic-search-heuristics/c280-task-order/v1"
TASK_ORDER_METHOD = "sha256(seed-nul-count-nul-task-id)-sort/v1"
TIME_LIMIT = 300.0
MEMORY_LIMIT_MIB = 8192.0
EXPECTED_CELLS = 1050

SCHEMA = "symbolic-search-heuristics/finalist-selection/v1"
SCREEN_RULE_ID = "family-max-solved-min-micro-par2-min-complete-calls-label/v1"
CAP_RULE_ID = "max-solved-min-micro-par2-smaller-k/v1"

CONFIGS = [
    ("blind_fw", "sym_fw()"),
    ("ms_exact",
     "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false)"),
    ("ms_cap8",
     "sym_fw_ms(max_states=10000,value_cap=8,align_merge_order=false)"),
    ("ms_cap16",
     "sym_fw_ms(max_states=10000,value_cap=16,align_merge_order=false)"),
    ("ms_exact_prune",
     "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false,prune_only=true)"),
    ("ms_exact_w4",
     "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false,batch_f_window=4)"),
    ("ms_exact_w16",
     "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false,batch_f_window=16)"),
    ("ms_cap8_w4",
     "sym_fw_ms(max_states=10000,value_cap=8,align_merge_order=false,batch_f_window=4)"),
    ("ms_cap8_w16",
     "sym_fw_ms(max_states=10000,value_cap=8,align_merge_order=false,batch_f_window=16)"),
    ("ms_cap16_w4",
     "sym_fw_ms(max_states=10000,value_cap=16,align_merge_order=false,batch_f_window=4)"),
    ("ms_cap16_w16",
     "sym_fw_ms(max_states=10000,value_cap=16,align_merge_order=false,batch_f_window=16)"),
    ("pdb_bdd_b100k",
     "sym_fw_pdb(budget=100000,goal_directed=false)"),
    ("pdb_goal_b100k",
     "sym_fw_pdb(budget=100000,goal_directed=true)"),
    ("pdb_goal_w4",
     "sym_fw_pdb(budget=100000,goal_directed=true,batch_f_window=4)"),
    ("pdb_goal_w16",
     "sym_fw_pdb(budget=100000,goal_directed=true,batch_f_window=16)"),
    ("pot_rect_m8",
     "sym_fw_pot(m=8,all_states_objective=false,lpsolver=cplex)"),
    ("pot_rect_m8_w4",
     "sym_fw_pot(m=8,all_states_objective=false,lpsolver=cplex,batch_f_window=4)"),
    ("pot_rect_m8_w16",
     "sym_fw_pot(m=8,all_states_objective=false,lpsolver=cplex,batch_f_window=16)"),
    ("pot_rect_m16",
     "sym_fw_pot(m=16,all_states_objective=false,lpsolver=cplex)"),
    ("pot_rect_m16_w4",
     "sym_fw_pot(m=16,all_states_objective=false,lpsolver=cplex,batch_f_window=4)"),
    ("pot_rect_m16_w16",
     "sym_fw_pot(m=16,all_states_objective=false,lpsolver=cplex,batch_f_window=16)"),
]

CONTROLS = {"blind_fw", "ms_exact"}
FAMILIES = {
    "ms": tuple(label for label, _ in CONFIGS
                if label.startswith("ms_") and label not in CONTROLS),
    "pdb": tuple(label for label, _ in CONFIGS if label.startswith("pdb_")),
    "potential": tuple(
        label for label, _ in CONFIGS if label.startswith("pot_")),
}

CAP_PILOT_OPTIONS = [
    {"label": label, "search": cap_analyzer.EXPECTED_SEARCHES[label]}
    for label in cap_analyzer.ALGORITHMS
]


class AnalysisError(Exception):
    pass


def canonical_json(value):
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def option_records(configs=CONFIGS):
    return [{"label": label, "search": search} for label, search in configs]


OPTION_MATRIX_DIGEST = "5341ab3b6594687c9a7d483f39d087ba5c9baa56321928f0bd92c67bf4590ece"
CAP_OPTION_MATRIX_DIGEST = (
    "071ea4fcd0259ea320b93409b02d9687fc348f7ffb4a2486ac33ec6afb5536e6")
if sha256_json(option_records()) != OPTION_MATRIX_DIGEST:
    raise RuntimeError("frozen 21-option matrix changed")
if sha256_json(CAP_PILOT_OPTIONS) != CAP_OPTION_MATRIX_DIGEST:
    raise RuntimeError("frozen cap-pilot option matrix changed")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate and rank the frozen heuristic-choice screen.")
    parser.add_argument(
        "properties", nargs="?",
        help=("Lab properties JSON, evaluation directory, tar archive, or '-' "
              "for JSON on stdin."))
    parser.add_argument(
        "--manifest", type=Path, default=MANIFEST,
        help="Frozen 50-task screen manifest (default: %(default)s).")
    parser.add_argument(
        "--emit-selection-artifact", action="store_true",
        help=("Print only a complete finalist-validation artifact; requires "
              "--cap-properties and fully valid inputs."))
    parser.add_argument(
        "--cap-properties",
        help=("Frozen ec839 cap-pilot properties used only for the independent "
              "primary-cap selection."))
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run deterministic synthetic validation/ranking tests and exit.")
    return parser.parse_args(argv)


def logical_source_sha256(records):
    """Hash the normalized logical records, independent of archive packaging."""
    ordered = sorted(
        (dict(record) for record in records),
        key=lambda record: (
            str(record.get("algorithm", "")),
            str(record.get("domain", "")),
            str(record.get("problem", "")),
            str(record.get("_source_key", "")),
            canonical_json(record),
        ))
    return sha256_json(ordered)


def expected_component_options(search):
    open_paren = search.index("(")
    inner = search[open_paren + 1:-1].strip()
    separator = "," if inner else ""
    configured = '{}({}{}wbh_log="wbh.jsonl")'.format(
        search[:open_paren], inner, separator)
    return ["--search", configured]


def last_driver_option(record, option):
    options = record.get("driver_options")
    if not isinstance(options, list):
        return None
    result = None
    for index, token in enumerate(options[:-1]):
        if token == option:
            result = options[index + 1]
    return result


def parse_memory_mib(value):
    if not isinstance(value, str) or len(value) < 2:
        return None
    try:
        amount = float(value[:-1])
    except ValueError:
        return None
    suffix = value[-1].lower()
    if suffix == "g":
        return amount * 1024
    if suffix == "m":
        return amount
    return None


def parse_duration_seconds(value):
    if not isinstance(value, str) or not value:
        return None
    fields = value.split(":")
    try:
        numbers = [int(field) for field in fields]
    except ValueError:
        return None
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
        return 3600 * hours + 60 * minutes + seconds
    if len(numbers) == 2:
        minutes, seconds = numbers
        return 60 * minutes + seconds
    return None


def validate_screen(
        records, tasks, task_sources_sha256, source_manifest_sha256):
    algorithms = [label for label, _ in CONFIGS]
    matrix, structural_errors, structural_warnings = cap_analyzer.build_matrix(
        records, tasks, algorithms, allow_incomplete=False)
    # A frozen screen is an exact matrix, not a filter over a pooled properties
    # file: extra algorithms/tasks are therefore errors rather than warnings.
    errors = list(structural_errors) + list(structural_warnings)
    warnings = []
    searches = dict(CONFIGS)
    costs_by_task = defaultdict(list)
    outer_envelopes = set()

    if len(records) != EXPECTED_CELLS:
        errors.append(
            "properties contain {} records; expected exactly {}".format(
                len(records), EXPECTED_CELLS))
    if len(matrix) != EXPECTED_CELLS:
        errors.append(
            "screen has {} cells; expected {}".format(
                len(matrix), EXPECTED_CELLS))

    for algorithm in algorithms:
        for task in tasks:
            record = matrix.get((algorithm, task))
            if record is None:
                continue
            task_name = cap_analyzer.task_label(task)
            prefix = "{} {}".format(algorithm, task_name)
            coverage = cap_analyzer.outcome(record)
            if coverage is None:
                errors.append(prefix + " has invalid or missing coverage")
            cost = cap_analyzer.solution_cost(record)
            if coverage is True:
                if cost is None:
                    errors.append(prefix + " is solved without numeric cost")
                else:
                    costs_by_task[task].append((algorithm, cost))
                planner_time = cap_analyzer.number(record.get("planner_time"))
                if planner_time is None or planner_time < 0:
                    errors.append(
                        prefix + " is solved without nonnegative planner_time")
            elif coverage is False and cost is not None:
                warnings.append(prefix + " is unsolved but records a cost")

            actual_options = record.get("component_options")
            wanted_options = expected_component_options(searches[algorithm])
            if actual_options != wanted_options:
                errors.append(
                    "{} has component_options {!r}; expected {!r}".format(
                        prefix, actual_options, wanted_options))
            for field in ("global_revision", "local_revision"):
                if str(record.get(field)) != FROZEN_REVISION:
                    errors.append(
                        "{} has {}={!r}; expected {}".format(
                            prefix, field, record.get(field), FROZEN_REVISION))
            for field, expected in (
                    ("planner_time_limit", TIME_LIMIT),
                    ("planner_memory_limit", MEMORY_LIMIT_MIB)):
                actual = cap_analyzer.number(record.get(field))
                if actual is None or not cap_analyzer.equal_values(actual, expected):
                    errors.append(
                        "{} has {}={!r}; expected {}".format(
                            prefix, field, record.get(field), expected))
            for option, expected in (
                    ("--overall-time-limit", "300s"),
                    ("--overall-memory-limit", "8G")):
                actual = last_driver_option(record, option)
                if actual != expected:
                    errors.append(
                        "{} has driver {} {!r}; expected {!r}".format(
                            prefix, option, actual, expected))
            static_expected = {
                "protocol": "heuristic-choices-screen-v1",
                "task_manifest_sha256": MANIFEST_DIGEST,
                "declared_run_count": EXPECTED_CELLS,
                "option_matrix_sha256": OPTION_MATRIX_DIGEST,
                "selection_rule": SCREEN_RULE_ID,
                "source_manifest_sha256": source_manifest_sha256,
                "task_sources_sha256": task_sources_sha256,
                "task_order_seed": TASK_ORDER_SEED,
                "task_order_method": TASK_ORDER_METHOD,
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
            outer_time = parse_duration_seconds(outer[1])
            if outer_time is None or outer_time < TIME_LIMIT:
                errors.append(prefix + " has an inadequate scheduler time envelope")
            outer_memory = parse_memory_mib(outer[2])
            if outer_memory is None or outer_memory < MEMORY_LIMIT_MIB:
                errors.append(prefix + " has an inadequate scheduler memory envelope")

    if len(outer_envelopes) > 1:
        errors.append("screen records disagree on the outer scheduler envelope")

    for task, entries in sorted(costs_by_task.items()):
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


def score(matrix, label, tasks):
    solved = 0
    penalties = []
    for task in tasks:
        record = matrix[(label, task)]
        if cap_analyzer.outcome(record) is True:
            solved += 1
            penalties.append(float(record["planner_time"]))
        else:
            penalties.append(2 * TIME_LIMIT)
    return solved, statistics.mean(penalties)


def complete_calls(matrix, labels, tasks):
    """Return suite totals only when every cell has certified final counters."""
    totals = {}
    for label in labels:
        total = 0
        for task in tasks:
            record = matrix[(label, task)]
            calls = cap_analyzer.number(record.get("image_calls_completed"))
            certified = (
                record.get("raw_metrics_complete") is True
                and record.get("piece_metrics_certified") is True
                and cap_analyzer.number(record.get("wbh_schema_version")) == 2
                and record.get("image_count_convention")
                == "per_piece_attempted_completed"
                and calls is not None and calls >= 0
                and calls.is_integer())
            if not certified:
                return None
            total += int(calls)
        totals[label] = total
    return totals


def rank_families(matrix, tasks):
    results = {}
    for family in ("ms", "pdb", "potential"):
        labels = FAMILIES[family]
        call_totals = complete_calls(matrix, labels, tasks)
        ranking = []
        for label in labels:
            solved, par2 = score(matrix, label, tasks)
            calls = call_totals[label] if call_totals is not None else None
            key = (-solved, par2)
            if call_totals is not None:
                key += (calls,)
            key += (label,)
            ranking.append({
                "label": label,
                "solved": solved,
                "micro_par2": par2,
                "completed_image_calls": calls,
                "key": key,
            })
        ranking.sort(key=lambda item: item["key"])
        results[family] = {
            "calls_tiebreak_available": call_totals is not None,
            "ranking": ranking,
            "selected": ranking[0]["label"],
        }
    return results


def validate_cap_source(raw_path):
    records, source = cap_analyzer.load_properties(raw_path)
    tasks = cap_analyzer.load_manifest(cap_analyzer.DEFAULT_MANIFEST)
    matrix, errors, warnings = cap_analyzer.build_matrix(
        records, tasks, cap_analyzer.ALGORITHMS, allow_incomplete=False)
    if len(records) != len(tasks) * len(cap_analyzer.ALGORITHMS):
        errors.append("cap-pilot properties do not contain exactly 350 records")
    # Artifact generation accepts the cap pilot itself, not a pooled file.
    errors += warnings
    warnings = []
    cap_by_algorithm = {cap_analyzer.EXACT: -1}
    cap_by_algorithm.update({
        "ms_cap{}".format(value): value for value in cap_analyzer.CAPS})
    record_errors, record_warnings, _ = cap_analyzer.validate_records(
        matrix, tasks, cap_analyzer.ALGORITHMS, cap_analyzer.BLIND,
        cap_by_algorithm, allow_incomplete=False)
    errors += record_errors
    warnings += record_warnings
    if errors:
        raise AnalysisError(
            "cap-pilot validation failed: {}".format("; ".join(errors)))
    selected, _ = cap_analyzer.select_primary_cap(
        matrix, tasks, cap_analyzer.TIME_LIMIT)
    if selected is None:
        raise AnalysisError("cap-pilot selection is unavailable")
    return selected, logical_source_sha256(records), source, warnings


def finalist_records(rankings):
    searches = dict(CONFIGS)
    return {
        family: {
            "label": rankings[family]["selected"],
            "search": searches[rankings[family]["selected"]],
        }
        for family in ("ms", "pdb", "potential")
    }


def validation_configs(selected_cap, finalists):
    configs = [
        {"role": "control", "family": "blind", "label": "blind_fw",
         "search": "sym_fw()"},
        {"role": "control", "family": "ms", "label": "ms_exact",
         "search": dict(CONFIGS)["ms_exact"]},
        {"role": "primary-cap", "family": "ms",
         "label": "ms_cap{}".format(selected_cap),
         "search": "sym_fw_ms(max_states=10000,value_cap={},align_merge_order=false)".format(
             selected_cap)},
    ]
    seen = {item["search"] for item in configs}
    for family in ("ms", "pdb", "potential"):
        item = finalists.get(family)
        if item is None or item["search"] in seen:
            continue
        configs.append({
            "role": "family-finalist", "family": family,
            "label": item["label"], "search": item["search"],
        })
        seen.add(item["search"])
    return configs


def make_artifact(
        screen_records, rankings, cap_path, screen_task_sources_sha256,
        screen_source_manifest_sha256):
    import suite_cost_manifest as cost_manifest

    selected_cap, cap_source_digest, _, _ = validate_cap_source(cap_path)
    finalists = finalist_records(rankings)
    configs = validation_configs(selected_cap, finalists)
    cost_data = cost_manifest.load_manifest()
    record_by_key = {
        "{}:{}".format(record["domain"], record["problem"]): record
        for record in cost_data["tasks"]
    }
    validation_tasks = [
        line.strip()
        for line in VALIDATION_MANIFEST.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    validation_digest = hashlib.sha256(
        "".join("{}\n".format(task) for task in validation_tasks).encode(
            "utf-8")).hexdigest()
    if (len(validation_tasks) != 92
            or len(set(validation_tasks)) != 92
            or validation_digest != VALIDATION_MANIFEST_DIGEST):
        raise AnalysisError("reserved finalist manifest changed")
    try:
        selected_cost_records = [record_by_key[task] for task in validation_tasks]
    except KeyError as err:
        raise AnalysisError(
            "reserved task is absent from cost manifest: {}".format(err))
    supported = cost_manifest.supported_tasks()
    if not {
            tuple(task.split(":", 1)) for task in validation_tasks
            } <= supported:
        raise AnalysisError(
            "reserved finalist manifest is not wholly inside the frozen "
            "supported positive-cost, axiom-free population")
    selected_cost_records.sort(
        key=lambda record: (record["domain"], record["problem"]))
    source_manifest_sha256 = cost_manifest.sha256_file(
        cost_manifest.MANIFEST_PATH)
    task_sources_sha256 = hashlib.sha256(
        cost_manifest.canonical_records_bytes(selected_cost_records)).hexdigest()
    return {
        "schema": SCHEMA,
        "screen": {
            "planner_revision": FROZEN_REVISION,
            "manifest_sha256": MANIFEST_DIGEST,
            "properties_canonical_sha256": logical_source_sha256(screen_records),
            "time_limit_seconds": int(TIME_LIMIT),
            "memory_limit_mib": int(MEMORY_LIMIT_MIB),
            "task_order_seed": TASK_ORDER_SEED,
            "task_order_method": TASK_ORDER_METHOD,
            "selection_rule": SCREEN_RULE_ID,
            "option_matrix_sha256": OPTION_MATRIX_DIGEST,
            "source_manifest_sha256": screen_source_manifest_sha256,
            "task_sources_sha256": screen_task_sources_sha256,
            "options": option_records(),
        },
        "cap_pilot": {
            "planner_revision": CAP_PILOT_REVISION,
            "manifest_sha256": cap_analyzer.MANIFEST_DIGEST,
            "properties_canonical_sha256": cap_source_digest,
            "time_limit_seconds": int(cap_analyzer.TIME_LIMIT),
            "memory_limit_mib": int(cap_analyzer.MEMORY_LIMIT_MIB),
            "selection_rule": CAP_RULE_ID,
            "option_matrix_sha256": CAP_OPTION_MATRIX_DIGEST,
            "options": CAP_PILOT_OPTIONS,
            "selected_label": "ms_cap{}".format(selected_cap),
        },
        "family_finalists": finalists,
        "validation": {
            "planner_revision": FROZEN_REVISION,
            "manifest_sha256": VALIDATION_MANIFEST_DIGEST,
            "time_limit_seconds": int(TIME_LIMIT),
            "memory_limit_mib": int(MEMORY_LIMIT_MIB),
            "task_order_seed": TASK_ORDER_SEED,
            "task_order_method": TASK_ORDER_METHOD,
            "source_manifest_sha256": source_manifest_sha256,
            "task_sources_sha256": task_sources_sha256,
            "configs": configs,
            "expected_run_count": 92 * len(configs),
        },
    }


def print_report(source, source_digest, rankings, warnings):
    print("Heuristic-choice screen: {}".format(source))
    print("canonical properties SHA-256: {}".format(source_digest))
    print("selection rule: {}".format(SCREEN_RULE_ID))
    for family in ("ms", "pdb", "potential"):
        result = rankings[family]
        print("\n{} family (completed-call tie-break: {})".format(
            family, "available" if result["calls_tiebreak_available"]
            else "omitted: at least one counter is incomplete or uncertified"))
        for rank, item in enumerate(result["ranking"], 1):
            calls = ("NA" if item["completed_image_calls"] is None else
                     str(item["completed_image_calls"]))
            print("  {:2d}. {:20s} solved={:2d} micro-PAR2={:.6f} calls={}".format(
                rank, item["label"], item["solved"],
                item["micro_par2"], calls))
        print("  selected: {}".format(result["selected"]))
    print("\nPASS: 1050 cells, exact options/revision/limits, solved costs, "
          "and scheduler protocol validated.")
    print("Unsolved rows receive PAR2=600; partial work counters are never "
          "used in the image-call tie-break.")
    for warning in warnings:
        print("WARNING: " + warning)


def synthetic_record(label, search, task, planner_time, calls):
    domain, problem = task
    return {
        "_source_key": "{}-{}-{}".format(label, domain, problem),
        "algorithm": label,
        "domain": domain,
        "problem": problem,
        "coverage": 1,
        "solution_cost": 1,
        "planner_time": planner_time,
        "component_options": expected_component_options(search),
        "global_revision": FROZEN_REVISION,
        "local_revision": FROZEN_REVISION,
        "planner_time_limit": TIME_LIMIT,
        "planner_memory_limit": MEMORY_LIMIT_MIB,
        "driver_options": ["--overall-time-limit", "300s",
                           "--overall-memory-limit", "8G"],
        "protocol": "heuristic-choices-screen-v1",
        "task_manifest_sha256": MANIFEST_DIGEST,
        "declared_run_count": EXPECTED_CELLS,
        "option_matrix_sha256": OPTION_MATRIX_DIGEST,
        "selection_rule": SCREEN_RULE_ID,
        "source_manifest_sha256": "3" * 64,
        "task_sources_sha256": "4" * 64,
        "task_order_seed": TASK_ORDER_SEED,
        "task_order_method": TASK_ORDER_METHOD,
        "driver_time_limit": "300s",
        "driver_memory_limit": "8G",
        "scheduler_environment": "tetralith-slurm",
        "scheduler_account": "naiss2025-5-382",
        "scheduler_cpus_per_task": 1,
        "scheduler_array_task_throttle": 5,
        "scheduler_qos": "devel",
        "scheduler_time_limit_per_task": "00:10:00",
        "scheduler_memory_per_cpu": "9G",
        "repetitions": 1,
        "metrics_validation_protocol":
            wbh_parser.METRICS_VALIDATION_PROTOCOL,
        "raw_metrics_complete": True,
        "piece_metrics_certified": True,
        "wbh_schema_version": 2,
        "image_count_convention": "per_piece_attempted_completed",
        "image_calls_completed": calls,
    }


def self_test():
    tasks = cap_analyzer.load_manifest(MANIFEST)
    preferred = {"ms": "ms_cap8", "pdb": "pdb_goal_w4",
                 "potential": "pot_rect_m16_w16"}
    times = {label: 20.0 for label, _ in CONFIGS}
    for family, label in preferred.items():
        times[label] = {"ms": 3.0, "pdb": 4.0, "potential": 5.0}[family]
    records = [
        synthetic_record(label, search, task, times[label], index + 1)
        for index, (label, search) in enumerate(CONFIGS)
        for task in tasks
    ]
    assert logical_source_sha256(records) == logical_source_sha256(
        list(reversed(records)))
    matrix, errors, _ = validate_screen(
        records, tasks, "4" * 64, "3" * 64)
    assert not errors, errors
    rankings = rank_families(matrix, tasks)
    assert {family: rankings[family]["selected"] for family in preferred} == preferred
    assert all(rankings[family]["calls_tiebreak_available"] for family in preferred)

    # With solved count and PAR2 tied, certified completed calls decide.
    for record in records:
        if record["algorithm"] in FAMILIES["pdb"]:
            record["planner_time"] = 10.0
            record["image_calls_completed"] = (
                1 if record["algorithm"] == preferred["pdb"] else 100)
    rankings = rank_families(matrix, tasks)
    assert rankings["pdb"]["selected"] == preferred["pdb"]

    records[0]["solution_cost"] = 2
    _, errors, _ = validate_screen(
        records, tasks, "4" * 64, "3" * 64)
    assert any("solved-cost disagreement" in error for error in errors)
    records[0]["solution_cost"] = 1

    records.append(dict(records[0], algorithm="unexpected"))
    _, errors, _ = validate_screen(
        records, tasks, "4" * 64, "3" * 64)
    assert any("expected exactly" in error for error in errors)
    records.pop()

    records[0]["scheduler_array_task_throttle"] = None
    _, errors, _ = validate_screen(
        records, tasks, "4" * 64, "3" * 64)
    assert any("scheduler_array_task_throttle" in error for error in errors)
    records[0]["scheduler_array_task_throttle"] = 5

    del records[0]["metrics_validation_protocol"]
    _, errors, _ = validate_screen(
        records, tasks, "4" * 64, "3" * 64)
    assert any("metrics_validation_protocol" in error for error in errors)
    records[0]["metrics_validation_protocol"] = (
        wbh_parser.METRICS_VALIDATION_PROTOCOL)

    records[-1]["raw_metrics_complete"] = False
    matrix, errors, _ = validate_screen(
        records, tasks, "4" * 64, "3" * 64)
    assert not errors, errors
    rankings = rank_families(matrix, tasks)
    assert rankings["potential"]["calls_tiebreak_available"] is False
    print("synthetic analyzer tests: PASS (1050 cells, cost gate, ranking, censoring)")


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    if args.properties is None:
        raise AnalysisError("properties input is required")
    tasks = cap_analyzer.load_manifest(args.manifest)
    task_labels = [cap_analyzer.task_label(task) for task in tasks]
    task_sources_sha256, source_manifest_sha256 = (
        screen_runner.validate_task_sources(task_labels))
    records, source = cap_analyzer.load_properties(args.properties)
    matrix, errors, warnings = validate_screen(
        records, tasks, task_sources_sha256, source_manifest_sha256)
    if errors:
        raise AnalysisError(
            "screen validation failed ({} errors): {}".format(
                len(errors), "; ".join(errors)))
    rankings = rank_families(matrix, tasks)
    if args.emit_selection_artifact:
        if not args.cap_properties:
            raise AnalysisError(
                "--emit-selection-artifact requires --cap-properties")
        artifact = make_artifact(
            records, rankings, args.cap_properties, task_sources_sha256,
            source_manifest_sha256)
        print(json.dumps(artifact, indent=2, sort_keys=True))
    else:
        print_report(
            source, logical_source_sha256(records), rankings, warnings)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AnalysisError, cap_analyzer.AnalysisError, RuntimeError) as err:
        print("analysis error: {}".format(err), file=sys.stderr)
        sys.exit(2)
