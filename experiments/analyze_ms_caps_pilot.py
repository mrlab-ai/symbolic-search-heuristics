#!/usr/bin/env python3
"""Analyze the predeclared merge-and-shrink value-cap pilot.

The script is deliberately read-only: it reads a Downward Lab ``properties``
JSON file (or an evaluation tarball containing one) and writes a deterministic
report to stdout.  By default it expects the frozen 50-task manifest and the
algorithms from ``exp_ms_caps_pilot.py``.

Examples:
  python3 experiments/analyze_ms_caps_pilot.py \
      experiments/data/exp_ms_caps_pilot-eval/properties
  python3 experiments/analyze_ms_caps_pilot.py \
      experiments/data/exp_ms_caps_pilot-eval.tar.gz

Expected properties come from the standard Fast Downward Lab parsers plus
``wbh_parser.py``.  In particular, ``planner_time`` is preferred for PAR2;
construction metadata, terminal statistics, and raw symbolic-search metrics
come from ``wbh.jsonl``.  A killed run can have useful partial raw metrics while
``raw_metrics_complete`` is false.
"""

import argparse
import hashlib
import json
import math
import statistics
import sys
import tarfile
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_MANIFEST = SCRIPT_DIR / "ms_caps_pilot_suite.txt"
DEFAULT_PROPERTIES = SCRIPT_DIR / "data" / "exp_ms_caps_pilot-eval" / "properties"
DEFAULT_ARCHIVE = SCRIPT_DIR / "data" / "exp_ms_caps_pilot-eval.tar.gz"

FROZEN_REVISION = "ec8399257de93e0739046a187af4bed0b85e19ce"
MANIFEST_DIGEST = "c63a59ee2096b40c24f80db895ee2c0d22aabc2630c823b882e7f50f529a481b"
TIME_LIMIT = 300.0
MEMORY_LIMIT_MIB = 8192.0
BLIND = "blind_fw"
EXACT = "ms_exact"
CAPS = [2, 4, 8, 16, 32]
ALGORITHMS = [BLIND, EXACT] + ["ms_cap{}".format(cap) for cap in CAPS]
EXPECTED_SEARCHES = {
    BLIND: "sym_fw()",
    EXACT: "sym_fw_ms(max_states=10000,value_cap=-1)",
}
EXPECTED_SEARCHES.update({
    "ms_cap{}".format(cap):
        "sym_fw_ms(max_states=10000,value_cap={})".format(cap)
    for cap in CAPS
})

RAW_FIELDS = (
    "expanded_bdd_nodes",
    "expanded_states",
    "bucket_images",
    "image_time",
)
HEURISTIC_EQUIVALENCE_FIELDS = (
    "num_values",
    "num_terminals",
    "add_nodes",
    "width_upper_bound",
)
COMPLETE_SEARCH_EQUIVALENCE_FIELDS = (
    "effort",
    "peak_bdd_nodes",
    "expanded_bdd_nodes",
    "expanded_states",
    "bucket_images",
    "partition_ratio_max",
    "partition_ratio_geomean",
    "num_pruned_deadends",
    "pruned_deadend_states",
    "pruned_deadend_bdd_nodes",
)
MAX_VALUE_FIELDS = (
    "max_heuristic_value",
    "heuristic_max_value",
    "max_value",
)


class AnalysisError(Exception):
    pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze the 50-task M&S terminal-cap Lab experiment.")
    parser.add_argument(
        "properties", nargs="?",
        help=("Lab properties JSON, evaluation directory, tar archive, or '-' "
              "for JSON on stdin. Defaults to the expected pilot output."))
    parser.add_argument(
        "--manifest", type=Path, default=DEFAULT_MANIFEST,
        help="Frozen task manifest (default: %(default)s).")
    parser.add_argument(
        "--time-limit", type=float, default=300.0,
        help=("PAR2 limit; must equal the frozen 300-second run limit "
              "(default: %(default)s)."))
    parser.add_argument(
        "--allow-incomplete", action="store_true",
        help=("Allow missing cells and dynamic output fields while inspecting "
              "unfinished runs; frozen configuration metadata on existing "
              "cells remains mandatory."))
    return parser.parse_args(argv)


def _load_json_stream(stream, source):
    try:
        data = json.load(stream)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise AnalysisError("invalid JSON in {}: {}".format(source, err))
    return _normalize_properties_container(data, source)


def _normalize_properties_container(data, source):
    if isinstance(data, dict):
        items = list(data.items())
    elif isinstance(data, list):
        items = [(str(index), value) for index, value in enumerate(data)]
    else:
        raise AnalysisError(
            "{} has a {} top level; expected object or list".format(
                source, type(data).__name__))
    records = []
    for source_key, value in items:
        if not isinstance(value, dict):
            raise AnalysisError(
                "property entry {!r} in {} is not an object".format(
                    source_key, source))
        record = dict(value)
        record["_source_key"] = source_key
        records.append(record)
    return records


def _properties_in_directory(path):
    direct = [path / "properties", path / "properties.json"]
    matches = [candidate for candidate in direct if candidate.is_file()]
    if not matches:
        matches = sorted(
            candidate for candidate in path.glob("*-eval/properties")
            if candidate.is_file())
    if len(matches) != 1:
        raise AnalysisError(
            "{} contains {} candidate properties files: {}".format(
                path, len(matches), ", ".join(map(str, matches)) or "none"))
    return matches[0]


def _load_archive(path):
    try:
        archive = tarfile.open(str(path), mode="r:*")
    except (tarfile.TarError, OSError) as err:
        raise AnalysisError("cannot open archive {}: {}".format(path, err))
    with archive:
        members = [
            member for member in archive.getmembers()
            if member.isfile() and Path(member.name).name == "properties"
        ]
        if len(members) != 1:
            raise AnalysisError(
                "{} contains {} properties members: {}".format(
                    path, len(members),
                    ", ".join(member.name for member in members) or "none"))
        extracted = archive.extractfile(members[0])
        if extracted is None:
            raise AnalysisError(
                "cannot read {} from {}".format(members[0].name, path))
        try:
            data = json.loads(extracted.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise AnalysisError("invalid JSON in {}: {}".format(path, err))
    return _normalize_properties_container(data, str(path))


def load_properties(raw_path):
    if raw_path == "-":
        return _load_json_stream(sys.stdin, "stdin"), "stdin"

    if raw_path is None:
        if DEFAULT_PROPERTIES.is_file():
            path = DEFAULT_PROPERTIES
        elif DEFAULT_ARCHIVE.is_file():
            path = DEFAULT_ARCHIVE
        else:
            raise AnalysisError(
                "no properties path supplied and neither {} nor {} exists".format(
                    DEFAULT_PROPERTIES, DEFAULT_ARCHIVE))
    else:
        path = Path(raw_path).expanduser().resolve()

    if path.is_dir():
        path = _properties_in_directory(path)
    if not path.is_file():
        raise AnalysisError("properties input does not exist: {}".format(path))

    try:
        is_archive = tarfile.is_tarfile(str(path))
    except OSError:
        is_archive = False
    if is_archive:
        return _load_archive(path), str(path)
    try:
        with path.open(encoding="utf-8") as stream:
            records = _load_json_stream(stream, str(path))
    except OSError as err:
        raise AnalysisError("cannot read {}: {}".format(path, err))
    return records, str(path)


def load_manifest(path):
    try:
        lines = path.expanduser().resolve().read_text(encoding="utf-8").splitlines()
    except OSError as err:
        raise AnalysisError("cannot read manifest {}: {}".format(path, err))
    tasks = []
    for lineno, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            domain, problem = line.split(":", 1)
        else:
            fields = line.split()
            if len(fields) != 2:
                raise AnalysisError(
                    "{}:{} is not DOMAIN:PROBLEM or DOMAIN PROBLEM".format(
                        path, lineno))
            domain, problem = fields
        domain = domain.strip()
        problem = problem.strip()
        if not domain or not problem:
            raise AnalysisError(
                "{}:{} has an empty domain or problem".format(path, lineno))
        tasks.append((domain, problem))
    duplicates = sorted(task for task in set(tasks) if tasks.count(task) > 1)
    if duplicates:
        raise AnalysisError(
            "duplicate manifest tasks: {}".format(
                ", ".join(task_label(task) for task in duplicates)))
    if not tasks:
        raise AnalysisError("manifest contains no tasks: {}".format(path))
    domain_counts = defaultdict(int)
    for domain, _ in tasks:
        domain_counts[domain] += 1
    if (len(tasks) != 50 or len(domain_counts) != 25 or
            set(domain_counts.values()) != {2}):
        raise AnalysisError(
            "frozen pilot manifest must contain 50 tasks, two in each of "
            "25 domains; found {} tasks in {} domains".format(
                len(tasks), len(domain_counts)))
    payload = "".join("{}:{}\n".format(domain, problem)
                      for domain, problem in tasks)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if digest != MANIFEST_DIGEST:
        raise AnalysisError(
            "pilot manifest digest changed: {} != {}".format(
                digest, MANIFEST_DIGEST))
    return tasks


def task_label(task):
    return "{}:{}".format(task[0], task[1])


def identity(record):
    algorithm = record.get("algorithm")
    domain = record.get("domain")
    problem = record.get("problem")
    run_id = record.get("id")
    if isinstance(run_id, (list, tuple)) and len(run_id) >= 3:
        algorithm = algorithm or run_id[0]
        domain = domain or run_id[1]
        problem = problem or run_id[2]
    if not all(isinstance(value, str) and value for value in
               (algorithm, domain, problem)):
        raise AnalysisError(
            "entry {!r} lacks algorithm/domain/problem identity".format(
                record.get("_source_key")))
    return algorithm, (domain, problem)


def number(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    elif isinstance(value, str):
        try:
            result = float(value)
        except ValueError:
            return None
    else:
        return None
    return result if math.isfinite(result) else None


def outcome(record):
    if record is None:
        return None
    value = record.get("coverage")
    if value is True or value == 1:
        return True
    if value is False or value == 0:
        return False
    return None


def solution_cost(record):
    return number(record.get("solution_cost")) if record is not None else None


def runtime(record):
    if record is None:
        return None, None
    for field in ("planner_time", "planner_wall_clock_time", "total_time"):
        value = number(record.get(field))
        if value is not None and value >= 0:
            return value, field
    return None, None


def equal_values(left, right):
    left_number = number(left)
    right_number = number(right)
    if left_number is not None and right_number is not None:
        return math.isclose(
            left_number, right_number, rel_tol=1e-10, abs_tol=1e-9)
    return left == right


def format_number(value, digits=4):
    if value is None:
        return "NA"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return ("{:." + str(digits) + "g}").format(value)


def percentage(value):
    return "NA" if value is None else "{:.1f}%".format(100 * value)


def print_table(headers, rows):
    rendered = [[str(value) for value in row] for row in rows]
    widths = [len(str(header)) for header in headers]
    for row in rendered:
        for index, value in enumerate(row):
            widths[index] = max(widths[index], len(value))
    print("  ".join(str(header).ljust(widths[index])
                    for index, header in enumerate(headers)))
    print("  ".join("-" * width for width in widths))
    for row in rendered:
        print("  ".join(value.ljust(widths[index])
                        for index, value in enumerate(row)))


def build_matrix(records, tasks, expected_algorithms, allow_incomplete):
    task_set = set(tasks)
    expected_set = set(expected_algorithms)
    matrix = {}
    errors = []
    warnings = []
    unknown_algorithms = set()
    outside_tasks = set()
    for record in records:
        algorithm, task = identity(record)
        if algorithm not in expected_set:
            unknown_algorithms.add(algorithm)
            continue
        if task not in task_set:
            outside_tasks.add(task)
            continue
        key = (algorithm, task)
        if key in matrix:
            errors.append(
                "duplicate cell {} {}".format(algorithm, task_label(task)))
        else:
            matrix[key] = record
    if unknown_algorithms:
        warnings.append(
            "ignored unexpected algorithms: {}".format(
                ", ".join(sorted(unknown_algorithms))))
    if outside_tasks:
        warnings.append(
            "ignored {} records outside the frozen manifest".format(
                len(outside_tasks)))
    missing = [
        (algorithm, task)
        for algorithm in expected_algorithms
        for task in tasks
        if (algorithm, task) not in matrix
    ]
    if missing:
        message = "missing {} of {} expected algorithm-task cells".format(
            len(missing), len(expected_algorithms) * len(tasks))
        (warnings if allow_incomplete else errors).append(message)
        warnings.append(
            "first missing cells: {}".format(
                ", ".join("{} {}".format(algorithm, task_label(task))
                          for algorithm, task in missing[:10])))
    return matrix, errors, warnings


def expected_component_options(algorithm):
    search = EXPECTED_SEARCHES[algorithm]
    inner = search[search.index("(") + 1:-1].strip()
    separator = "," if inner else ""
    configured = "{}({}{}wbh_log=\"wbh.jsonl\")".format(
        search[:search.index("(")], inner, separator)
    return ["--search", configured]


def last_driver_option(record, option):
    options = record.get("driver_options")
    if not isinstance(options, list):
        return None
    value = None
    for index, token in enumerate(options[:-1]):
        if token == option:
            value = options[index + 1]
    return value


def report_missing(message, errors):
    errors.append(message)


def report_output_missing(
        message, allow_incomplete, errors, warnings):
    (warnings if allow_incomplete else errors).append(message)


def validate_records(
        matrix, tasks, algorithms, blind, cap_by_algorithm, allow_incomplete):
    errors = []
    warnings = []
    cost_by_task = defaultdict(list)
    for algorithm in algorithms:
        expected_cap = cap_by_algorithm.get(algorithm)
        for task in tasks:
            record = matrix.get((algorithm, task))
            if record is None:
                continue
            solved = outcome(record)
            if solved is None:
                report_output_missing(
                    "{} {} has invalid/missing coverage {!r}".format(
                        algorithm, task_label(task), record.get("coverage")),
                    allow_incomplete, errors, warnings)
            cost = solution_cost(record)
            if solved is True and cost is None:
                report_output_missing(
                    "{} {} is solved but lacks a numeric solution_cost".format(
                        algorithm, task_label(task)),
                    allow_incomplete, errors, warnings)
            elif solved is True:
                cost_by_task[task].append((algorithm, cost))
            elif solved is False and cost is not None:
                warnings.append(
                    "{} {} is unsolved but has solution_cost={}".format(
                        algorithm, task_label(task), format_number(cost)))
            if solved is True and runtime(record)[0] is None:
                report_output_missing(
                    "{} {} is solved but lacks a numeric planner runtime".format(
                        algorithm, task_label(task)),
                    allow_incomplete, errors, warnings)

            logged_cap = number(record.get("value_cap"))
            if algorithm == blind:
                if logged_cap is not None:
                    warnings.append(
                        "blind record {} unexpectedly logs value_cap={}".format(
                            task_label(task), format_number(logged_cap)))
            elif logged_cap is not None and expected_cap is not None:
                if not equal_values(logged_cap, expected_cap):
                    errors.append(
                        "{} {} logs value_cap={} instead of {}".format(
                            algorithm, task_label(task),
                            format_number(logged_cap), expected_cap))

            expected_options = expected_component_options(algorithm)
            actual_options = record.get("component_options")
            if actual_options is None:
                report_missing(
                    "{} {} lacks component_options".format(
                        algorithm, task_label(task)),
                    errors)
            elif actual_options != expected_options:
                errors.append(
                    "{} {} has component_options {!r}; expected {!r}".format(
                        algorithm, task_label(task), actual_options,
                        expected_options))

            for field in ("global_revision", "local_revision"):
                revision = record.get(field)
                if revision is None:
                    report_missing(
                        "{} {} lacks {}".format(
                            algorithm, task_label(task), field),
                        errors)
                elif str(revision) != FROZEN_REVISION:
                    errors.append(
                        "{} {} has {}={}; expected {}".format(
                            algorithm, task_label(task), field, revision,
                            FROZEN_REVISION))

            for field, expected in (
                    ("planner_time_limit", TIME_LIMIT),
                    ("planner_memory_limit", MEMORY_LIMIT_MIB)):
                value = number(record.get(field))
                if value is None:
                    report_missing(
                        "{} {} lacks numeric {}".format(
                            algorithm, task_label(task), field),
                        errors)
                elif not equal_values(value, expected):
                    errors.append(
                        "{} {} has {}={}; expected {}".format(
                            algorithm, task_label(task), field,
                            format_number(value), format_number(expected)))

            for option, expected in (
                    ("--overall-time-limit", "300s"),
                    ("--overall-memory-limit", "8G")):
                value = last_driver_option(record, option)
                if value is None:
                    report_missing(
                        "{} {} lacks driver option {}".format(
                            algorithm, task_label(task), option),
                        errors)
                elif value != expected:
                    errors.append(
                        "{} {} has {} {}; expected {}".format(
                            algorithm, task_label(task), option, value,
                            expected))

    for task, entries in sorted(cost_by_task.items()):
        distinct = []
        for _, cost in entries:
            if not any(equal_values(cost, prior) for prior in distinct):
                distinct.append(cost)
        if len(distinct) > 1:
            errors.append(
                "solved-cost disagreement on {}: {}".format(
                    task_label(task), ", ".join(
                        "{}={}".format(algorithm, format_number(cost))
                        for algorithm, cost in entries)))

    revisions = sorted({
        str(record.get("global_revision"))
        for record in matrix.values()
        if record.get("global_revision") is not None
    })
    return errors, warnings, revisions


def score_algorithm(matrix, algorithm, tasks, time_limit):
    records = [matrix.get((algorithm, task)) for task in tasks]
    observed = sum(record is not None for record in records)
    known_outcomes = sum(outcome(record) is not None for record in records)
    solved = sum(outcome(record) is True for record in records)
    complete = observed == len(tasks) and known_outcomes == len(tasks)
    coverage = solved / len(tasks) if complete else None
    par2_values = []
    runtime_sources = defaultdict(int)
    for record in records:
        solved_outcome = outcome(record)
        if solved_outcome is None:
            par2_values = None
            break
        if solved_outcome:
            elapsed, source = runtime(record)
            if elapsed is None:
                par2_values = None
                break
            par2_values.append(elapsed)
            runtime_sources[source] += 1
        else:
            par2_values.append(2 * time_limit)
    par2 = statistics.mean(par2_values) if par2_values is not None else None
    return {
        "observed": observed,
        "known_outcomes": known_outcomes,
        "solved": solved,
        "coverage": coverage,
        "par2": par2,
        "runtime_sources": runtime_sources,
    }


def select_primary_cap(matrix, tasks, time_limit):
    """Apply the frozen pilot-only rule for the primary held-out cap.

    Rank caps lexicographically by (1) larger solved count, (2) smaller
    micro-task PAR2 with construction charged, and (3) smaller K.  The final
    tie-break favors the tighter symbolic interface.  Selection is unavailable
    until all cap cells have known outcomes and every solved cell has runtime.
    Exact M&S and blind search are comparators, not selection candidates.
    """
    candidates = []
    for cap in CAPS:
        algorithm = "ms_cap{}".format(cap)
        score = score_algorithm(matrix, algorithm, tasks, time_limit)
        if score["coverage"] is None or score["par2"] is None:
            return None, []
        candidates.append((
            -score["solved"], score["par2"], cap, algorithm,
            score["solved"]))
    candidates.sort()
    return candidates[0][2], candidates


def print_primary_cap_selection(matrix, tasks, time_limit, valid):
    print("\nPredeclared primary held-out cap selection")
    print("rule: maximize pilot solved count; then minimize micro PAR2; "
          "then choose smaller K")
    if not valid:
        print("selected cap: UNAVAILABLE (pilot validation failed)")
        return
    selected, ranking = select_primary_cap(matrix, tasks, time_limit)
    if selected is None:
        print("selected cap: UNAVAILABLE (matrix or runtime data incomplete)")
        return
    print("ranking: " + ", ".join(
        "K={} (solved={}, PAR2={})".format(
            cap, solved, format_number(par2))
        for _, par2, cap, _, solved in ranking))
    print("selected cap: K={}".format(selected))
    print("Only this cap's comparison with exact M&S and blind search is the "
          "primary held-out test; other held-out caps are exploratory.")


def compare_pair(matrix, algorithm, reference, tasks):
    result = {
        "paired": 0,
        "wins": [],
        "losses": [],
        "both_solved": 0,
        "both_unsolved": 0,
        "cost_mismatches": [],
    }
    for task in tasks:
        candidate = matrix.get((algorithm, task))
        baseline = matrix.get((reference, task))
        candidate_outcome = outcome(candidate)
        baseline_outcome = outcome(baseline)
        if candidate_outcome is None or baseline_outcome is None:
            continue
        result["paired"] += 1
        if candidate_outcome and not baseline_outcome:
            result["wins"].append(task)
        elif baseline_outcome and not candidate_outcome:
            result["losses"].append(task)
        elif candidate_outcome:
            result["both_solved"] += 1
            if not equal_values(solution_cost(candidate), solution_cost(baseline)):
                result["cost_mismatches"].append(task)
        else:
            result["both_unsolved"] += 1
    return result


def comparison_pairs():
    pairs = [(EXACT, BLIND)]
    pairs.extend(("ms_cap{}".format(cap), BLIND) for cap in CAPS)
    pairs.extend(("ms_cap{}".format(cap), EXACT) for cap in CAPS)
    return pairs


def geometric_mean(values):
    if not values:
        return None
    return math.exp(math.fsum(math.log(value) for value in values) / len(values))


def raw_metric_comparability(
        candidate, baseline, algorithm, reference, field):
    convention_field = {
        "expanded_bdd_nodes": "node_count_convention",
        "bucket_images": "image_count_convention",
    }.get(field)
    if convention_field is None:
        return "comparable"
    candidate_convention = candidate.get(convention_field)
    baseline_convention = baseline.get(convention_field)
    if (not isinstance(candidate_convention, str) or
            not candidate_convention or
            candidate_convention != baseline_convention):
        return "uncertified"
    # Legacy M&S runs have one search bucket per layer and can be compared to
    # each other under the same convention. Legacy blind frontiers can have
    # multiple pieces whose counts were not logged, so those comparisons are
    # only valid with the v2 piece-count certification on both records.
    if BLIND in (algorithm, reference):
        if (candidate.get("piece_metrics_certified") is not True or
                baseline.get("piece_metrics_certified") is not True):
            return "uncertified"
    if candidate_convention.startswith("legacy_"):
        return "legacy"
    return "comparable"


def paired_metric_ratio(
        matrix, algorithm, reference, tasks, field, eligibility):
    ratios = []
    uncertified = 0
    legacy = 0
    for task in tasks:
        candidate = matrix.get((algorithm, task))
        baseline = matrix.get((reference, task))
        if candidate is None or baseline is None:
            continue
        if eligibility == "solved":
            if outcome(candidate) is not True or outcome(baseline) is not True:
                continue
        elif eligibility == "construction":
            if (candidate.get("construction_completed") is not True or
                    baseline.get("construction_completed") is not True):
                continue
        elif eligibility == "raw":
            if (candidate.get("raw_metrics_complete") is not True or
                    baseline.get("raw_metrics_complete") is not True):
                continue
            comparability = raw_metric_comparability(
                candidate, baseline, algorithm, reference, field)
            if comparability == "uncertified":
                uncertified += 1
                continue
        else:
            raise AssertionError(
                "unknown metric eligibility: {}".format(eligibility))
        candidate_value = number(candidate.get(field))
        baseline_value = number(baseline.get(field))
        # Multiplicative ratios are undefined at zero. Exclude those pairs and
        # expose n rather than applying an arbitrary offset.
        if (candidate_value is None or baseline_value is None or
                candidate_value <= 0 or baseline_value <= 0):
            continue
        ratios.append(candidate_value / baseline_value)
        if eligibility == "raw" and comparability == "legacy":
            legacy += 1
    return geometric_mean(ratios), len(ratios), uncertified, legacy


def equivalence_threshold(exact_record):
    for field in MAX_VALUE_FIELDS:
        value = number(exact_record.get(field))
        if value is not None and value >= 0:
            return value, field
    return None, None


def compare_stable_fields(exact_record, cap_record):
    fields = list(HEURISTIC_EQUIVALENCE_FIELDS)
    if (exact_record.get("raw_metrics_complete") is True and
            cap_record.get("raw_metrics_complete") is True):
        fields.extend(COMPLETE_SEARCH_EQUIVALENCE_FIELDS)
    checked = []
    mismatches = []
    for field in fields:
        if field not in exact_record or field not in cap_record:
            continue
        checked.append(field)
        if not equal_values(exact_record[field], cap_record[field]):
            mismatches.append(
                "{}:{}!={}".format(
                    field, format_number(number(exact_record[field])
                                         if number(exact_record[field]) is not None
                                         else exact_record[field]),
                    format_number(number(cap_record[field])
                                  if number(cap_record[field]) is not None
                                  else cap_record[field])))
    return checked, mismatches


def exact_equivalence(matrix, exact, cap_algorithm, cap, tasks):
    summary = {
        "eligible": 0,
        "outcome_equal": 0,
        "outcome_mismatch": 0,
        "stable_equal": 0,
        "stable_mismatch": 0,
        "indeterminate": 0,
        "details": [],
    }
    for task in tasks:
        exact_record = matrix.get((exact, task))
        if exact_record is None:
            continue
        threshold, source = equivalence_threshold(exact_record)
        if threshold is None or cap < threshold:
            continue
        summary["eligible"] += 1
        cap_record = matrix.get((cap_algorithm, task))
        exact_outcome = outcome(exact_record)
        cap_outcome = outcome(cap_record)
        prefix = "{} (threshold {} from {})".format(
            task_label(task), format_number(threshold), source)
        if cap_record is None or exact_outcome is None or cap_outcome is None:
            summary["indeterminate"] += 1
            summary["details"].append(prefix + ": missing outcome metadata")
            continue
        outcome_matches = exact_outcome == cap_outcome
        if outcome_matches and exact_outcome:
            outcome_matches = equal_values(
                solution_cost(exact_record), solution_cost(cap_record))
        if outcome_matches:
            summary["outcome_equal"] += 1
        else:
            summary["outcome_mismatch"] += 1
            summary["details"].append(prefix + ": outcome/cost mismatch")
            continue
        checked, mismatches = compare_stable_fields(exact_record, cap_record)
        if not checked:
            summary["indeterminate"] += 1
        elif mismatches:
            summary["stable_mismatch"] += 1
            summary["details"].append(
                prefix + ": stable fields " + ", ".join(mismatches))
        else:
            summary["stable_equal"] += 1
    return summary


def print_header(source, records, tasks, algorithms, matrix, revisions, time_limit):
    print("M&S terminal-cap pilot analysis")
    print("source: {}".format(source))
    print("records: {} ({} expected cells found)".format(len(records), len(matrix)))
    print("manifest: {} tasks in {} domains".format(
        len(tasks), len({task[0] for task in tasks})))
    print("algorithms: {}".format(", ".join(algorithms)))
    print("frozen revision: {}".format(FROZEN_REVISION))
    print("resource envelope: {} seconds, {} MiB".format(
        format_number(time_limit), format_number(MEMORY_LIMIT_MIB)))
    print("observed global revision(s): {}".format(
        ", ".join(revisions) if revisions else "NA"))


def print_scores(matrix, algorithms, tasks, time_limit):
    print("\nMicro scores (complete-matrix scores are NA while cells are missing)")
    rows = []
    for algorithm in algorithms:
        score = score_algorithm(matrix, algorithm, tasks, time_limit)
        source_text = ",".join(
            "{}={}".format(field, count)
            for field, count in sorted(score["runtime_sources"].items())) or "-"
        rows.append((
            algorithm,
            "{}/{}".format(score["observed"], len(tasks)),
            "{}/{}".format(score["known_outcomes"], len(tasks)),
            score["solved"],
            percentage(score["coverage"]),
            format_number(score["par2"]),
            source_text,
        ))
    print_table(
        ("algorithm", "runs", "outcomes", "solved", "coverage", "PAR2 s",
         "solved-time source"), rows)

def print_pairs(matrix, algorithms, caps, blind, exact, tasks):
    comparisons = [(exact, blind)]
    comparisons.extend(("ms_cap{}".format(cap), blind) for cap in caps)
    comparisons.extend(("ms_cap{}".format(cap), exact) for cap in caps)
    print("\nPaired coverage comparisons")
    rows = []
    details = []
    for algorithm, reference in comparisons:
        if algorithm not in algorithms or reference not in algorithms:
            continue
        comparison = compare_pair(matrix, algorithm, reference, tasks)
        rows.append((
            algorithm, reference, comparison["paired"],
            len(comparison["wins"]), len(comparison["losses"]),
            len(comparison["wins"]) - len(comparison["losses"]),
            comparison["both_solved"], comparison["both_unsolved"],
        ))
        if comparison["wins"]:
            details.append(
                "{} over {} wins: {}".format(
                    algorithm, reference,
                    ", ".join(task_label(task)
                              for task in comparison["wins"])))
        if comparison["losses"]:
            details.append(
                "{} vs {} losses: {}".format(
                    algorithm, reference,
                    ", ".join(task_label(task)
                              for task in comparison["losses"])))
    print_table(
        ("algorithm", "reference", "paired", "wins", "losses", "net",
         "both solved", "both failed"), rows)
    if details:
        print("\nOutcome-changing tasks")
        for detail in details:
            print("- " + detail)


def print_instrumentation(matrix, algorithms, tasks, blind):
    print("\nConstruction and instrumentation completeness")
    rows = []
    expected = len(tasks)
    for algorithm in algorithms:
        records = [
            matrix[(algorithm, task)] for task in tasks
            if (algorithm, task) in matrix
        ]
        construction_logged = sum(
            number(record.get("construction_time")) is not None
            for record in records)
        construction_completed = sum(
            record.get("construction_completed") is True for record in records)
        raw_complete = sum(
            record.get("raw_metrics_complete") is True for record in records)
        raw_present = sum(
            all(number(record.get(field)) is not None for field in RAW_FIELDS)
            for record in records)
        schema_present = sum(
            number(record.get("wbh_schema_version")) is not None and
            isinstance(record.get("node_count_convention"), str) and
            isinstance(record.get("image_count_convention"), str)
            for record in records)
        piece_certified = sum(
            record.get("piece_metrics_certified") is True for record in records)
        terminal_metadata = sum(
            number(record.get("num_values")) is not None or
            number(record.get("num_terminals")) is not None
            for record in records)
        cap_metadata = sum(
            number(record.get("value_cap")) is not None for record in records)
        construction_cell = "-" if algorithm == blind else "{}/{}".format(
            construction_completed, construction_logged)
        rows.append((
            algorithm,
            "{}/{}".format(len(records), expected),
            construction_cell,
            "{}/{}".format(terminal_metadata, expected),
            "{}/{}".format(cap_metadata, expected) if algorithm != blind else "-",
            "{}/{}".format(raw_complete, expected),
            "{}/{}".format(raw_present, expected),
            "{}/{}".format(schema_present, expected),
            "{}/{}".format(piece_certified, expected),
        ))
    print_table(
        ("algorithm", "runs", "construction done/logged", "terminal metadata",
         "cap metadata", "raw complete", "raw fields", "schema", "piece cert"),
        rows)

    print("\nPaired common-task metric ratios (candidate / reference)")
    rows = []
    metric_specs = (
        ("planner_time", "solved"),
        ("construction_time", "construction"),
        ("expanded_bdd_nodes", "raw"),
        ("bucket_images", "raw"),
        ("image_time", "raw"),
    )
    for algorithm, reference in comparison_pairs():
        cells = []
        for field, eligibility in metric_specs:
            ratio, count, uncertified, legacy = paired_metric_ratio(
                matrix, algorithm, reference, tasks, field, eligibility)
            if ratio is None and uncertified:
                cells.append("UNCERT [n=0,u={}]".format(uncertified))
            else:
                suffix = ""
                if legacy:
                    suffix += ",L={}".format(legacy)
                if uncertified:
                    suffix += ",u={}".format(uncertified)
                cells.append("{} [n={}{}]".format(
                    format_number(ratio), count, suffix))
        rows.append((
            algorithm, reference,
            cells[0], cells[1], cells[2], cells[3], cells[4],
        ))
    print_table(
        ("candidate", "reference", "planner s", "construction s",
         "expanded BDD", "bucket images", "image s"), rows)
    print("Ratios are geometric means over the same eligible tasks; lower favors "
          "the candidate. Planner time uses jointly solved tasks, construction "
          "time requires construction_completed=true for both runs, and raw "
          "metrics require raw_metrics_complete=true for both. Nonpositive or "
          "missing values are excluded and n is always shown. For expanded-BDD "
          "and bucket-image work, matching count conventions are required; any "
          "blind comparison additionally requires piece_metrics_certified=true "
          "on both runs. L counts ratios retained under the same legacy "
          "convention; u counts complete pairs rejected as uncertified.")


def print_equivalence(matrix, exact, caps, tasks, validation_errors):
    print("\nConditional exact-equivalence checks")
    rows = []
    all_details = []
    for cap in caps:
        algorithm = "ms_cap{}".format(cap)
        summary = exact_equivalence(matrix, exact, algorithm, cap, tasks)
        rows.append((
            algorithm,
            summary["eligible"],
            "{}/{}".format(summary["outcome_equal"],
                            summary["outcome_mismatch"]),
            "{}/{}".format(summary["stable_equal"],
                            summary["stable_mismatch"]),
            summary["indeterminate"],
        ))
        all_details.extend("{}: {}".format(algorithm, detail)
                           for detail in summary["details"])
        if summary["outcome_mismatch"] or summary["stable_mismatch"]:
            validation_errors.append(
                "{} violates an equivalence check backed by max-value metadata".format(
                    algorithm))
    if any(row[1] for row in rows):
        print_table(
            ("algorithm", "eligible", "outcome eq/mismatch",
             "stable eq/mismatch", "indeterminate"), rows)
    else:
        print("Unavailable: frozen logs do not record the maximum finite heuristic "
              "value. No num_values-1 proxy is used because weighted M&S values "
              "may be gapped.")
    if all_details:
        print("Equivalence discrepancies/unknowns")
        for detail in all_details:
            print("- " + detail)


def print_caveats():
    print("\nInterpretation caveats")
    print("- The manifest is outcome-enriched from the earlier 30-minute "
          "blind/exact experiment (archived blind-only and exact-only coverage "
          "cases, plus jointly solved controls). The evaluation archive does "
          "not establish why an unsolved row failed. Coverage and PAR2 are "
          "diagnostic pilot scores, not unbiased population estimates.")
    print("- The pilot limit is 5 minutes whereas enrichment outcomes came from "
          "30-minute runs. Historical labels need not reproduce at this limit.")
    print("- There are no repetitions. Treat runtime and PAR2 differences as "
          "screening evidence; paired coverage and convention-compatible, "
          "certified BDD-work counts are more reliable promotion criteria.")
    print("- Runtime ratios use jointly solved tasks only. Raw-work ratios use only "
          "tasks with raw_metrics_complete=true for both algorithms; killed or "
          "partially logged runs are censored and excluded. Every ratio reports n.")
    print("- Legacy logs use CUDD DagSize and expansion-event image counts. Their "
          "M&S-to-M&S work is comparable only under matching conventions; blind "
          "frontier piece counts are unrecoverable, so blind expanded-BDD and "
          "bucket-image comparisons are printed UNCERT rather than as ratios.")
    print("- Construction ratios require completed construction on both runs. "
          "Missing construction events and zero-valued metrics are excluded.")


def main(argv=None):
    args = parse_args(argv)
    if (not math.isfinite(args.time_limit) or
            not equal_values(args.time_limit, TIME_LIMIT)):
        raise AnalysisError(
            "--time-limit must equal the frozen {} seconds".format(
                format_number(TIME_LIMIT)))

    records, source = load_properties(args.properties)
    tasks = load_manifest(args.manifest)
    caps = CAPS
    algorithms = ALGORITHMS
    cap_by_algorithm = {EXACT: -1}
    cap_by_algorithm.update({
        "ms_cap{}".format(cap): cap for cap in caps
    })

    matrix, structural_errors, structural_warnings = build_matrix(
        records, tasks, algorithms, args.allow_incomplete)
    validation_errors, validation_warnings, revisions = validate_records(
        matrix, tasks, algorithms, BLIND, cap_by_algorithm,
        args.allow_incomplete)
    errors = structural_errors + validation_errors
    warnings = structural_warnings + validation_warnings

    print_header(
        source, records, tasks, algorithms, matrix, revisions, args.time_limit)
    print_scores(matrix, algorithms, tasks, args.time_limit)
    print_pairs(matrix, algorithms, caps, BLIND, EXACT, tasks)
    print_instrumentation(matrix, algorithms, tasks, BLIND)
    print_equivalence(matrix, EXACT, caps, tasks, errors)
    print_primary_cap_selection(
        matrix, tasks, args.time_limit, valid=not errors)
    print_caveats()

    print("\nValidation")
    if errors:
        print("FAIL ({} error{})".format(
            len(errors), "" if len(errors) == 1 else "s"))
        for message in errors:
            print("- ERROR: " + message)
    else:
        print("PASS: solved costs agree and all available metadata is consistent.")
    for message in warnings:
        print("- WARNING: " + message)
    return 1 if errors else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except AnalysisError as err:
        print("analysis error: {}".format(err), file=sys.stderr)
        sys.exit(2)
