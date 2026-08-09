#!/usr/bin/env python3
"""Validate, summarize, and rank the 20x50 Arrhenius pilot.

This analyzer is deliberately read-only and fail-closed.  It accepts exactly
the tasks, options, revisions, resource limits, and scheduler protocol declared
by :mod:`exp_arrhenius_pilot`.  Every expected algorithm-task cell must have a
well-formed, explained Fast Downward outcome, and solved costs must agree within
each task.

The predeclared selection rule is applied globally to all 20 configurations:
maximize coverage, minimize micro-PAR2 (600 seconds for every unsolved cell),
then minimize total image time only if every one of the 1000 cells has complete
schema-v2 certified metrics, then use the configuration label.

``--emit-selection-artifact`` prints deterministic JSON to stdout and never
writes a file. The planner revision, launch-protocol revision, and cached
binary hash are pinned independently below. ``--self-test`` injects synthetic
values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Reuse the mature, read-only properties/archive loader, exact manifest reader,
# numeric helpers, and table renderer.  Do not change the frozen analyzer.
import analyze_ms_caps_pilot as analyzer_utils
import exp_arrhenius_pilot as runner
import suite_cost_manifest
import wbh_parser


class AnalysisError(RuntimeError):
    pass


# The cached planner is intentionally older than the protocol commit: the
# runner pins this exact source commit while recording its clean launch HEAD in
# the separate ``protocol_revision`` property.  This avoids cache self-reference.
EXPECTED_PLANNER_REVISION = "d889d1f73876592e1c91b7781a58affac6bf22f2"

# Exact clean launch worktree revision. The analyzer lives in a descendant
# commit so this pin does not create a commit-hash self-reference.
EXPECTED_PROTOCOL_REVISION = "e7b0e4495d6722fdbae9461ea0be24e5484f1a5b"
EXPECTED_CACHE_BINARY_SHA256 = (
    "b0dac83910508b1089979ca7a16463cf2f3de72f30590af1c5e3c43dd4805d9e"
)

EXPECTED_PYTHON_VERSION = "3.9.25"
EXPECTED_LAB_VERSION = "8.0"
EXPECTED_CACHE_NAME_SUFFIX = "_61a748e5"
EXPECTED_TASK_SOURCES_SHA256 = (
    "d58d8539be8f03d4a1ff9fdf93d24903d424c47ec33ab2c7ffd47fbc37e9c482"
)
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168"
)
EXPECTED_MATRIX_SHA256 = (
    "f4e270633e2686be399351b91dfc674eb1a13e130d52a61f4ce38994d3267b15"
)
EXPECTED_BASELINE_SHA256 = (
    "a2ff5aa8d4f49e3b85f2338a3fc7e2844536c5eb7d354d9989eb20b06bacca41"
)
EXPECTED_CANDIDATE_SHA256 = (
    "6a11f7651583680e4d4da6e06959cc2adbb2f92b2155f55e40f6f3c488b494c0"
)

EXPECTED_TASKS = 50
EXPECTED_CONFIGS = 20
EXPECTED_CELLS = EXPECTED_TASKS * EXPECTED_CONFIGS
TIME_LIMIT_SECONDS = 300.0
PAR2_UNSOLVED_SECONDS = 600.0
MEMORY_LIMIT_MIB = 8192.0
BLIND = "blind_fw"
MS_EXACT = "ms_exact"
ARTIFACT_SCHEMA = "symbolic-search-heuristics/arrhenius-pilot-selection/v1"

CONFIGS = tuple(runner.BASELINE_CONFIGS) + tuple(runner.CANDIDATE_CONFIGS)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)

SCHEMA_V2_CONVENTIONS = {
    "wbh_schema_version": 2,
    "node_count_convention": "inner_nodes_per_piece",
    "image_count_convention": "per_piece_attempted_completed",
    "expansion_count_convention": "completed_with_attempts",
}
EMPTY_LEGACY_CONVENTIONS = {
    "wbh_schema_version": 1,
    "node_count_convention": "legacy_cudd_dag_size",
    "image_count_convention": "legacy_expand_event_count",
    "expansion_count_convention": "legacy_attempts_unmarked",
}
SCHEMA_V2_INTEGER_METRICS = (
    "expanded_bdd_nodes",
    "expanded_bdd_pieces",
    "attempted_bdd_nodes",
    "attempted_bdd_pieces",
    "bucket_expansions",
    "bucket_expansion_attempts",
    "image_events",
    "bucket_images",
    "image_source_buckets",
    "image_source_pieces",
    "image_calls_attempted",
    "image_calls_completed",
    "batched_images",
)
SCHEMA_V2_REAL_METRICS = (
    "expanded_states",
    "attempted_states",
    "image_time",
)

# Current Fast Downward exit-code outcomes accepted by this prospective
# protocol.  Unexplained/critical/signal outcomes are rejected rather than
# silently charged as an ordinary timeout.
EXPLAINED_OUTCOMES = {
    0: ("success", 1, 0),
    1: ("search-plan-found-and-out-of-memory", 1, 0),
    2: ("search-plan-found-and-out-of-time", 1, 0),
    3: ("search-plan-found-and-out-of-memory-and-time", 1, 0),
    10: ("translate-unsolvable", 0, 1),
    11: ("search-unsolvable", 0, 1),
    12: ("search-unsolvable-incomplete", 0, 0),
    20: ("translate-out-of-memory", 0, 0),
    21: ("translate-out-of-time", 0, 0),
    22: ("search-out-of-memory", 0, 0),
    23: ("search-out-of-time", 0, 0),
    24: ("search-out-of-memory-and-time", 0, 0),
}
PRESEARCH_EXIT_CODES = frozenset((10, 20, 21))


def canonical_json(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as err:
        raise AnalysisError("value is not canonical finite JSON: {}".format(err))


def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def option_records():
    return [{"label": label, "search": search} for label, search in CONFIGS]


def logical_properties_sha256(records):
    """Hash logical records without packaging-dependent properties keys."""
    normalized = []
    for record in records:
        item = {key: value for key, value in record.items() if key != "_source_key"}
        normalized.append(item)
    normalized.sort(
        key=lambda record: (
            str(record.get("algorithm", "")),
            str(record.get("domain", "")),
            str(record.get("problem", "")),
            canonical_json(record),
        )
    )
    return sha256_json(normalized)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate and rank the exact 20x50 Arrhenius pilot."
    )
    parser.add_argument(
        "properties",
        nargs="?",
        help=(
            "Lab properties JSON, evaluation directory, tar archive, or '-' "
            "for JSON on stdin."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=runner.MANIFEST,
        help="Exact frozen 50-task manifest (default: %(default)s).",
    )
    parser.add_argument(
        "--emit-selection-artifact",
        action="store_true",
        help="Print only deterministic selection JSON; never write a file.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run comprehensive deterministic synthetic tests and exit.",
    )
    args = parser.parse_args(argv)
    if args.self_test and (args.properties is not None or args.emit_selection_artifact):
        parser.error("--self-test does not accept properties or artifact output")
    return args


def _reviewed_hex(value, digits, name):
    if not isinstance(value, str) or not re.fullmatch(
        "[0-9a-f]{{{}}}".format(digits), value
    ):
        raise AnalysisError(
            "{} is unset; replace its reviewed None placeholder with {} hex digits"
            .format(name, digits)
        )
    if len(set(value)) == 1:
        raise AnalysisError("{} still looks like a synthetic placeholder".format(name))
    return value


def require_reviewed_pins(protocol_revision=None, binary_sha256=None):
    planner_revision = _reviewed_hex(
        EXPECTED_PLANNER_REVISION, 40, "EXPECTED_PLANNER_REVISION"
    )
    if protocol_revision is None:
        protocol_revision = EXPECTED_PROTOCOL_REVISION
    if binary_sha256 is None:
        binary_sha256 = EXPECTED_CACHE_BINARY_SHA256
    return (
        planner_revision,
        _reviewed_hex(protocol_revision, 40, "EXPECTED_PROTOCOL_REVISION"),
        _reviewed_hex(binary_sha256, 64, "EXPECTED_CACHE_BINARY_SHA256"),
    )


def validate_runner_contract(check_cache_pin=True, expected_cache_hash=None):
    """Guard the analyzer's copied constants against runner drift."""
    failures = []
    exact = {
        "planner revision": (
            runner.PLANNER_REVISION,
            EXPECTED_PLANNER_REVISION,
        ),
        "protocol": (runner.PROTOCOL, "arrhenius-current-no-lp-pilot-v1"),
        "selection rule": (
            runner.SELECTION_RULE,
            "valid-costs-max-coverage-min-micro-par2-"
            "min-certified-image-time-label/v1",
        ),
        "manifest digest": (runner.MANIFEST_DIGEST, analyzer_utils.MANIFEST_DIGEST),
        "baseline digest": (runner.BASELINE_CONFIGS_DIGEST, EXPECTED_BASELINE_SHA256),
        "candidate digest": (
            runner.CANDIDATE_CONFIGS_DIGEST,
            EXPECTED_CANDIDATE_SHA256,
        ),
        "benchmark revision": (
            runner.BENCHMARK_REVISION,
            suite_cost_manifest.EXPECTED_BENCHMARK_REVISION,
        ),
        "benchmark repository": (
            runner.BENCHMARK_REPOSITORY,
            suite_cost_manifest.EXPECTED_BENCHMARK_REPOSITORY,
        ),
    }
    for name, (actual, expected) in exact.items():
        if type(actual) is not type(expected) or actual != expected:
            failures.append("{}={!r}, expected {!r}".format(name, actual, expected))
    if len(runner.BASELINE_CONFIGS) != 14 or len(runner.CANDIDATE_CONFIGS) != 6:
        failures.append("runner matrix is not exactly 14 baseline + 6 candidate configs")
    if len(CONFIGS) != EXPECTED_CONFIGS or len(set(LABELS)) != EXPECTED_CONFIGS:
        failures.append("analyzer matrix is not exactly 20 unique labels")
    if sha256_json(option_records()) != EXPECTED_MATRIX_SHA256:
        failures.append("combined 20-option matrix digest changed")
    tasks = runner.read_manifest()
    matrix = runner.validate_config_matrix(tasks)
    if matrix.get("matrix_digest") != EXPECTED_MATRIX_SHA256:
        failures.append("runner combined option-matrix digest changed")
    if matrix.get("run_count") != EXPECTED_CELLS:
        failures.append("runner does not declare exactly 1000 cells")
    if matrix.get("layout") != {
        "raw_runs": 1000,
        "array_tasks": 1000,
        "runs_per_array_task": 1,
        "scheduler_time_limit_seconds": 600,
    }:
        failures.append("runner one-run-per-array scheduler layout changed")
    if suite_cost_manifest.EXPECTED_MANIFEST_SHA256 != EXPECTED_SOURCE_MANIFEST_SHA256:
        failures.append("frozen source-manifest digest changed")
    if check_cache_pin:
        if runner.CACHE_BINARY_SHA256 != expected_cache_hash:
            failures.append(
                "runner CACHE_BINARY_SHA256={!r}, expected analyzer pin {!r}".format(
                    runner.CACHE_BINARY_SHA256, expected_cache_hash
                )
            )
    if failures:
        raise AnalysisError("runner/analyzer contract mismatch: " + "; ".join(failures))


def expected_component_options(search):
    open_paren = search.index("(")
    inner = search[open_paren + 1 : -1].strip()
    separator = "," if inner else ""
    configured = '{}({}{}wbh_log="wbh.jsonl")'.format(
        search[:open_paren], inner, separator
    )
    return ["--search", configured]


def expected_protocol_metadata(planner_revision, protocol_revision, binary_sha256):
    return {
        "planner_revision": planner_revision,
        "protocol_revision": protocol_revision,
        "planner_revision_is_protocol_ancestor": True,
        "planner_build_options": ["release_no_lp"],
        "planner_build_config": "release_no_lp",
        "planner_binary_sha256": binary_sha256,
        "planner_revision_cache_name": (
            planner_revision + EXPECTED_CACHE_NAME_SUFFIX
        ),
        "cofactor_width_property": "cofactor_width",
        "cofactor_width_parser_protocol": (
            "run.log/unique-wbh-heuristic-cofactor-width/v1"
        ),
        "python_version": EXPECTED_PYTHON_VERSION,
        "lab_version": EXPECTED_LAB_VERSION,
        "required_lab_version": EXPECTED_LAB_VERSION,
        "task_order_seed": (
            "symbolic-search-heuristics/arrhenius-task-order/v1"
        ),
        "task_order_method": (
            "sha256(seed-nul-array-count-nul-array-id)-sort;"
            "ascending-run-id-within-array-task/v1"
        ),
        "driver_time_limit": "300s",
        "driver_memory_limit": "8G",
        "scheduler_environment": "arrhenius-slurm",
        "scheduler_cluster": "arrhenius",
        "scheduler_cpu_model": "AMD EPYC 9755 128-Core Processor",
        "scheduler_partition": "cpu",
        "scheduler_qos": "normal",
        "scheduler_account": "naiss2025-5-382-cpu",
        "scheduler_time_limit_per_task": "00:10:00",
        "scheduler_memory_per_cpu": "9G",
        "scheduler_cpus_per_task": 1,
        "scheduler_array_task_throttle": 5,
        "scheduler_max_array_tasks": 1000,
        "scheduler_array_tasks": 1000,
        "scheduler_runs_per_array_task": 1,
        "declared_run_count": EXPECTED_CELLS,
        "repetitions": 1,
        "protocol": runner.PROTOCOL,
        "selection_rule": runner.SELECTION_RULE,
        "task_manifest": "ms_caps_pilot_suite.txt",
        "task_manifest_sha256": analyzer_utils.MANIFEST_DIGEST,
        "task_count": EXPECTED_TASKS,
        "domain_count": 25,
        "baseline_config_count": 14,
        "candidate_config_count": 6,
        "config_count": EXPECTED_CONFIGS,
        "baseline_configs_sha256": EXPECTED_BASELINE_SHA256,
        "candidate_configs_sha256": EXPECTED_CANDIDATE_SHA256,
        "option_matrix_sha256": EXPECTED_MATRIX_SHA256,
        "benchmark_revision": suite_cost_manifest.EXPECTED_BENCHMARK_REVISION,
        "benchmark_repository": suite_cost_manifest.EXPECTED_BENCHMARK_REPOSITORY,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
    }


def _same_json_scalar(actual, expected):
    return type(actual) is type(expected) and actual == expected


def _cell_label(label, task):
    return "{} {}".format(label, analyzer_utils.task_label(task))


def _append(errors, prefix, message):
    errors.append("{}: {}".format(prefix, message))


def _json_number(value):
    """Return a finite JSON number, rejecting bool and numeric strings."""
    if type(value) not in (int, float):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except (OverflowError, TypeError, ValueError):
        return None


def _validate_outcome(record, prefix, errors):
    coverage = record.get("coverage")
    if type(coverage) is not int or coverage not in (0, 1):
        _append(errors, prefix, "coverage must be integer 0 or 1")
        return

    exit_code = record.get("planner_exit_code")
    if type(exit_code) is not int or exit_code not in EXPLAINED_OUTCOMES:
        _append(
            errors,
            prefix,
            "planner_exit_code must be a predeclared explained outcome; got {!r}".
            format(exit_code),
        )
    else:
        expected_error, expected_coverage, expected_unsolvable = EXPLAINED_OUTCOMES[
            exit_code
        ]
        if coverage != expected_coverage:
            _append(
                errors,
                prefix,
                "coverage {} contradicts planner_exit_code {} ({})".format(
                    coverage, exit_code, expected_error
                ),
            )
        if record.get("error") != expected_error:
            _append(
                errors,
                prefix,
                "error={!r}, expected {!r} for planner_exit_code {}".format(
                    record.get("error"), expected_error, exit_code
                ),
            )
        if record.get("unsolvable") != expected_unsolvable:
            _append(
                errors,
                prefix,
                "unsolvable={!r}, expected {} for planner_exit_code {}".format(
                    record.get("unsolvable"), expected_unsolvable, exit_code
                ),
            )

    unexplained = record.get("unexplained_errors")
    if unexplained not in (None, []):
        _append(errors, prefix, "contains unexplained_errors={!r}".format(unexplained))

    cost = record.get("solution_cost")
    planner_time = _json_number(record.get("planner_time"))
    if coverage == 1:
        if type(cost) is not int or cost < 0:
            _append(errors, prefix, "solved outcome needs a nonnegative integer cost")
        if planner_time is None or planner_time < 0:
            _append(errors, prefix, "solved outcome needs finite nonnegative planner_time")
    else:
        if cost is not None:
            _append(errors, prefix, "unsolved outcome must not contain solution_cost")
        if "planner_time" in record and (planner_time is None or planner_time < 0):
            _append(errors, prefix, "planner_time is malformed")


def _validate_metrics(record, prefix, errors):
    if record.get("metrics_validation_protocol") != wbh_parser.METRICS_VALIDATION_PROTOCOL:
        _append(
            errors,
            prefix,
            "metrics_validation_protocol={!r}, expected {!r}".format(
                record.get("metrics_validation_protocol"),
                wbh_parser.METRICS_VALIDATION_PROTOCOL,
            ),
        )
    # A driver outcome before search construction has no wbh.jsonl.  The Lab
    # parser sees empty content and emits this exact schema-less legacy marker;
    # it is a valid censored cell but can never participate in the image-time
    # criterion. No other outcome may use this exception.
    if (
        record.get("planner_exit_code") in PRESEARCH_EXIT_CODES
        and record.get("wbh_schema_version") == 1
    ):
        for field, expected in EMPTY_LEGACY_CONVENTIONS.items():
            if not _same_json_scalar(record.get(field), expected):
                _append(
                    errors,
                    prefix,
                    "{}={!r}, expected empty-log value {!r}".format(
                        field, record.get(field), expected
                    ),
                )
        if record.get("raw_metrics_complete") is not False:
            _append(errors, prefix, "empty pre-search log must have incomplete metrics")
        if record.get("piece_metrics_certified") is not False:
            _append(errors, prefix, "empty pre-search log cannot certify piece metrics")
        if record.get("metrics_validation_error") is not None:
            _append(errors, prefix, "empty pre-search log carries validation diagnostics")
        unexpected = [
            field
            for field in SCHEMA_V2_INTEGER_METRICS + SCHEMA_V2_REAL_METRICS
            if field in record
        ]
        if unexpected:
            _append(
                errors,
                prefix,
                "empty pre-search log unexpectedly has raw metrics {}".format(
                    ", ".join(unexpected)
                ),
            )
        return

    for field, expected in SCHEMA_V2_CONVENTIONS.items():
        if not _same_json_scalar(record.get(field), expected):
            _append(
                errors,
                prefix,
                "{}={!r}, expected {!r}".format(field, record.get(field), expected),
            )

    raw_complete = record.get("raw_metrics_complete")
    piece_certified = record.get("piece_metrics_certified")
    if type(raw_complete) is not bool:
        _append(errors, prefix, "raw_metrics_complete must be boolean")
    if type(piece_certified) is not bool:
        _append(errors, prefix, "piece_metrics_certified must be boolean")
    validation_error = record.get("metrics_validation_error")
    if validation_error is not None and (
        not isinstance(validation_error, str) or not validation_error
    ):
        _append(errors, prefix, "metrics_validation_error must be absent or nonempty")
    if raw_complete is True and piece_certified is not True:
        _append(errors, prefix, "complete raw metrics are not piece-certified")
    if raw_complete is True and validation_error is not None:
        _append(errors, prefix, "complete raw metrics carry a validation error")
    if piece_certified is True and validation_error is not None:
        _append(errors, prefix, "piece-certified metrics carry a validation error")
    if piece_certified is False and validation_error is None:
        _append(errors, prefix, "uncertified piece metrics lack validation diagnostics")

    for field in SCHEMA_V2_INTEGER_METRICS:
        value = record.get(field)
        if type(value) is not int or value < 0:
            _append(
                errors,
                prefix,
                "{} must be a nonnegative integer schema-v2 metric".format(field),
            )
    for field in SCHEMA_V2_REAL_METRICS:
        value = _json_number(record.get(field))
        if value is None or value < 0:
            _append(
                errors,
                prefix,
                "{} must be a finite nonnegative JSON-number schema-v2 metric".
                format(field),
            )

    # These relations are independently implied by the validated event stream
    # and protect the certification flags against malformed/tampered properties.
    relations = (
        ("attempted_bdd_nodes", "expanded_bdd_nodes"),
        ("attempted_states", "expanded_states"),
        ("attempted_bdd_pieces", "expanded_bdd_pieces"),
        ("bucket_expansion_attempts", "bucket_expansions"),
        ("attempted_bdd_pieces", "bucket_expansion_attempts"),
        ("expanded_bdd_pieces", "bucket_expansions"),
        ("image_source_buckets", "image_events"),
        ("image_source_pieces", "image_events"),
        ("image_source_pieces", "image_calls_attempted"),
        ("image_calls_attempted", "image_calls_completed"),
        ("image_events", "batched_images"),
    )
    for larger, smaller in relations:
        left = _json_number(record.get(larger))
        right = _json_number(record.get(smaller))
        if left is not None and right is not None and left < right:
            _append(errors, prefix, "{} is smaller than {}".format(larger, smaller))
    if (
        type(record.get("bucket_images")) is int
        and type(record.get("image_calls_completed")) is int
        and record["bucket_images"] != record["image_calls_completed"]
    ):
        _append(errors, prefix, "bucket_images differs from image_calls_completed")


def _expected_ms_value_cap(label):
    match = re.search(r"(?:^|,)value_cap=(-?\d+)(?:,|\))", SEARCHES[label])
    if not match:
        raise AnalysisError("cannot derive value_cap for {}".format(label))
    return int(match.group(1))


def _validate_heuristic(record, label, prefix, errors):
    construction_fields = (
        "construction_completed",
        "construction_time",
        "heuristic_kind",
        "heuristic_size_bound",
        "value_cap",
    )
    heuristic_fields = (
        "cofactor_width",
        "width_upper_bound",
        "num_values",
        "num_terminals",
        "add_nodes",
    )
    if label == BLIND:
        unexpected = [
            field for field in construction_fields + heuristic_fields if field in record
        ]
        if unexpected:
            _append(
                errors,
                prefix,
                "blind run unexpectedly has heuristic fields {}".format(
                    ", ".join(unexpected)
                ),
            )
        return

    completed_present = "construction_completed" in record
    completed = record.get("construction_completed")
    if completed_present and type(completed) is not bool:
        _append(errors, prefix, "construction_completed must be boolean when present")
        return
    if not completed_present:
        stray_construction = [
            field for field in construction_fields[1:] if field in record
        ]
        if stray_construction:
            _append(
                errors,
                prefix,
                "construction outcome is absent but fields {} are present".format(
                    ", ".join(stray_construction)
                ),
            )
    if record.get("coverage") == 1 and not completed_present:
        _append(errors, prefix, "solved heuristic run lacks construction outcome")

    if completed_present:
        construction_time = _json_number(record.get("construction_time"))
        if construction_time is None or construction_time < 0:
            _append(errors, prefix, "construction_time must be finite and nonnegative")
        size_bound = record.get("heuristic_size_bound")
        value_cap = record.get("value_cap")
        kind = record.get("heuristic_kind")
        if label.startswith("ms_"):
            if kind != "merge_and_shrink":
                _append(errors, prefix, "unexpected M&S heuristic_kind={!r}".format(kind))
            if type(size_bound) is not int or size_bound != 10000:
                _append(errors, prefix, "M&S heuristic_size_bound must equal 10000")
            expected_cap = _expected_ms_value_cap(label)
            if type(value_cap) is not int or value_cap != expected_cap:
                _append(
                    errors,
                    prefix,
                    "M&S value_cap={!r}, expected {}".format(value_cap, expected_cap),
                )
        elif label.startswith("pdb_"):
            if not isinstance(kind, str) or not kind.startswith("pdb_"):
                _append(errors, prefix, "unexpected PDB heuristic_kind={!r}".format(kind))
            if type(size_bound) is not int or size_bound != 100000:
                _append(errors, prefix, "PDB heuristic_size_bound must equal 100000")
            if type(value_cap) is not int or value_cap != -1:
                _append(errors, prefix, "PDB value_cap must equal -1")

    if completed is False:
        if label != "ms_exact_budget30":
            _append(errors, prefix, "construction fallback is only valid for ms_exact_budget30")
        if any(field in record for field in heuristic_fields):
            _append(errors, prefix, "construction fallback unexpectedly logged a heuristic")
        return

    width_present = "cofactor_width" in record
    stray_heuristic = [field for field in heuristic_fields[1:] if field in record]
    if not width_present and stray_heuristic:
        _append(
            errors,
            prefix,
            "cofactor_width is absent but heuristic fields {} are present".format(
                ", ".join(stray_heuristic)
            ),
        )
    if completed is True and not width_present:
        _append(errors, prefix, "completed construction lacks exact cofactor_width")
    if not width_present:
        return

    width = record.get("cofactor_width")
    upper = record.get("width_upper_bound")
    if type(width) is not int or width < 0:
        _append(errors, prefix, "cofactor_width must be a nonnegative integer")
    if type(upper) is not int or upper < 0:
        _append(errors, prefix, "width_upper_bound must be a nonnegative integer")
    elif type(width) is int and width > upper:
        _append(errors, prefix, "cofactor_width exceeds width_upper_bound")
    for field in ("num_values", "num_terminals"):
        value = record.get(field)
        if type(value) is not int or value <= 0:
            _append(errors, prefix, "{} must be a positive integer".format(field))
    add_nodes = record.get("add_nodes")
    if type(add_nodes) is not int or add_nodes < 0:
        _append(errors, prefix, "add_nodes must be a nonnegative integer")
    if (
        type(upper) is int
        and type(add_nodes) is int
        and type(record.get("num_terminals")) is int
        and upper != add_nodes + record["num_terminals"]
    ):
        _append(errors, prefix, "width_upper_bound != add_nodes + num_terminals")
    if (
        type(record.get("num_values")) is int
        and type(record.get("num_terminals")) is int
        and record["num_values"] > record["num_terminals"]
    ):
        _append(errors, prefix, "num_values exceeds num_terminals")


def validate_records(
    records, tasks, planner_revision, protocol_revision, binary_sha256
):
    matrix, structural_errors, structural_warnings = analyzer_utils.build_matrix(
        records, tasks, LABELS, allow_incomplete=False
    )
    # This input is the pilot itself, not a pooled properties database.
    errors = list(structural_errors) + list(structural_warnings)
    if len(records) != EXPECTED_CELLS:
        errors.append(
            "properties contain {} records; expected exactly {}".format(
                len(records), EXPECTED_CELLS
            )
        )
    if len(matrix) != EXPECTED_CELLS:
        errors.append(
            "matrix contains {} cells; expected exactly {}".format(
                len(matrix), EXPECTED_CELLS
            )
        )

    static_expected = expected_protocol_metadata(
        planner_revision, protocol_revision, binary_sha256
    )
    costs_by_task = defaultdict(list)
    proved_unsolvable_by_task = defaultdict(list)
    benchmark_worktrees = set()
    for label in LABELS:
        for task in tasks:
            record = matrix.get((label, task))
            if record is None:
                continue
            prefix = _cell_label(label, task)
            if record.get("algorithm") != label:
                _append(errors, prefix, "algorithm identity field changed")
            if record.get("domain") != task[0] or record.get("problem") != task[1]:
                _append(errors, prefix, "domain/problem identity fields changed")
            run_id = record.get("id")
            if run_id is not None and run_id != [label, task[0], task[1]]:
                _append(errors, prefix, "id={!r} is not the exact cell identity".format(run_id))

            expected_options = expected_component_options(SEARCHES[label])
            if record.get("component_options") != expected_options:
                _append(
                    errors,
                    prefix,
                    "component_options={!r}, expected {!r}".format(
                        record.get("component_options"), expected_options
                    ),
                )
            expected_driver = [
                "--validate",
                "--overall-time-limit",
                "30m",
                "--overall-memory-limit",
                "3584M",
                "--overall-time-limit",
                "300s",
                "--overall-memory-limit",
                "8G",
            ]
            if record.get("driver_options") != expected_driver:
                _append(
                    errors,
                    prefix,
                    "driver_options={!r}, expected {!r}".format(
                        record.get("driver_options"), expected_driver
                    ),
                )
            for field in ("global_revision", "local_revision"):
                if record.get(field) != planner_revision:
                    _append(
                        errors,
                        prefix,
                        "{}={!r}, expected {!r}".format(
                            field, record.get(field), planner_revision
                        ),
                    )
            for field, expected in (
                ("planner_time_limit", TIME_LIMIT_SECONDS),
                ("planner_memory_limit", MEMORY_LIMIT_MIB),
            ):
                actual = _json_number(record.get(field))
                if actual is None or not analyzer_utils.equal_values(actual, expected):
                    _append(
                        errors,
                        prefix,
                        "{}={!r}, expected {}".format(field, record.get(field), expected),
                    )
            for field, expected in static_expected.items():
                actual = record.get(field)
                if not _same_json_scalar(actual, expected):
                    _append(
                        errors,
                        prefix,
                        "{}={!r}, expected {!r}".format(field, actual, expected),
                    )

            worktree = record.get("benchmark_worktree")
            if not isinstance(worktree, str) or not worktree or not Path(worktree).is_absolute():
                _append(errors, prefix, "benchmark_worktree must be a nonempty absolute path")
            else:
                benchmark_worktrees.add(worktree)

            _validate_outcome(record, prefix, errors)
            _validate_metrics(record, prefix, errors)
            _validate_heuristic(record, label, prefix, errors)
            if record.get("coverage") == 1 and type(record.get("solution_cost")) is int:
                costs_by_task[task].append((label, record["solution_cost"]))
            if record.get("coverage") == 0 and record.get("unsolvable") == 1:
                proved_unsolvable_by_task[task].append(label)

    if len(benchmark_worktrees) != 1:
        errors.append(
            "records do not contain one consistent absolute benchmark_worktree"
        )
    for task, entries in sorted(costs_by_task.items()):
        distinct = sorted({cost for _, cost in entries})
        if len(distinct) > 1:
            errors.append(
                "solved-cost disagreement on {}: {}".format(
                    analyzer_utils.task_label(task),
                    ", ".join("{}={}".format(label, cost) for label, cost in entries),
                )
            )
        if proved_unsolvable_by_task.get(task):
            errors.append(
                "solved/proved-unsolvable disagreement on {}: solved by {}; "
                "reported unsolvable by {}".format(
                    analyzer_utils.task_label(task),
                    ", ".join(label for label, _ in entries),
                    ", ".join(proved_unsolvable_by_task[task]),
                )
            )
    return matrix, errors


def raise_validation_errors(errors):
    if not errors:
        return
    shown = errors[:50]
    suffix = ""
    if len(errors) > len(shown):
        suffix = "\n... {} additional validation errors".format(
            len(errors) - len(shown)
        )
    raise AnalysisError(
        "pilot validation failed ({} errors):\n{}{}".format(
            len(errors), "\n".join("- " + error for error in shown), suffix
        )
    )


def certified_image_cell(record):
    return (
        record.get("raw_metrics_complete") is True
        and record.get("piece_metrics_certified") is True
        and record.get("metrics_validation_error") is None
        and all(
            _same_json_scalar(record.get(field), expected)
            for field, expected in SCHEMA_V2_CONVENTIONS.items()
        )
        and all(
            type(record.get(field)) is int and record[field] >= 0
            for field in SCHEMA_V2_INTEGER_METRICS
        )
        and all(
            _json_number(record.get(field)) is not None
            and _json_number(record.get(field)) >= 0
            for field in SCHEMA_V2_REAL_METRICS
        )
    )


def width_summary(records):
    widths = [record["cofactor_width"] for record in records if "cofactor_width" in record]
    if not widths:
        return {"observed": 0, "minimum": None, "median": None, "maximum": None}
    return {
        "observed": len(widths),
        "minimum": min(widths),
        "median": statistics.median(widths),
        "maximum": max(widths),
    }


def construction_summary(records):
    kinds = [
        record.get("heuristic_kind")
        for record in records
        if isinstance(record.get("heuristic_kind"), str)
    ]
    return {
        "completed": sum(record.get("construction_completed") is True for record in records),
        "fallbacks": sum(record.get("construction_completed") is False for record in records),
        "unobserved": sum("construction_completed" not in record for record in records),
        "pattern_fallbacks": sum("fallback" in kind for kind in kinds),
    }


def analyze_scores(matrix, tasks):
    records_by_label = {
        label: [matrix[(label, task)] for task in tasks] for label in LABELS
    }
    all_cells_certified = all(
        certified_image_cell(record)
        for records in records_by_label.values()
        for record in records
    )
    scores = []
    for label in LABELS:
        records = records_by_label[label]
        solved = sum(record["coverage"] == 1 for record in records)
        penalties = [
            float(record["planner_time"])
            if record["coverage"] == 1
            else PAR2_UNSOLVED_SECONDS
            for record in records
        ]
        config_certified = all(certified_image_cell(record) for record in records)
        total_image_time = (
            math.fsum(float(record["image_time"]) for record in records)
            if config_certified
            else None
        )
        score = {
            "label": label,
            "search": SEARCHES[label],
            "coverage": solved,
            "micro_par2": math.fsum(penalties) / len(tasks),
            "total_image_time": total_image_time,
            "image_metrics_complete": config_certified,
            "construction": construction_summary(records),
            "cofactor_width": width_summary(records),
        }
        key = (-solved, score["micro_par2"])
        if all_cells_certified:
            key += (total_image_time,)
        key += (label,)
        score["_key"] = key
        scores.append(score)
    scores.sort(key=lambda item: item["_key"])
    for rank, score in enumerate(scores, 1):
        score["rank"] = rank
    return {
        "image_time_tiebreak_available": all_cells_certified,
        "ranking": scores,
        "selected": scores[0],
    }


def paired_delta(matrix, tasks, label, reference, image_time_tiebreak_available):
    candidate_penalties = []
    reference_penalties = []
    wins = 0
    losses = 0
    both_solved = 0
    both_unsolved = 0
    for task in tasks:
        candidate = matrix[(label, task)]
        baseline = matrix[(reference, task)]
        candidate_solved = candidate["coverage"] == 1
        baseline_solved = baseline["coverage"] == 1
        candidate_penalties.append(
            float(candidate["planner_time"])
            if candidate_solved
            else PAR2_UNSOLVED_SECONDS
        )
        reference_penalties.append(
            float(baseline["planner_time"])
            if baseline_solved
            else PAR2_UNSOLVED_SECONDS
        )
        if candidate_solved and not baseline_solved:
            wins += 1
        elif baseline_solved and not candidate_solved:
            losses += 1
        elif candidate_solved:
            both_solved += 1
        else:
            both_unsolved += 1
    image_delta = None
    if image_time_tiebreak_available:
        image_delta = math.fsum(
            float(matrix[(label, task)]["image_time"])
            - float(matrix[(reference, task)]["image_time"])
            for task in tasks
        )
    return {
        "label": label,
        "reference": reference,
        "coverage_delta": wins - losses,
        "micro_par2_delta": (
            math.fsum(
                candidate - baseline
                for candidate, baseline in zip(candidate_penalties, reference_penalties)
            )
            / len(tasks)
        ),
        "wins": wins,
        "losses": losses,
        "both_solved": both_solved,
        "both_unsolved": both_unsolved,
        "total_image_time_delta": image_delta,
    }


def all_paired_deltas(matrix, tasks, image_time_tiebreak_available):
    return [
        paired_delta(matrix, tasks, label, reference, image_time_tiebreak_available)
        for label in LABELS
        for reference in (BLIND, MS_EXACT)
    ]


def _public_score(score):
    return {key: value for key, value in score.items() if key != "_key"}


def make_selection_artifact(
    records,
    scores,
    paired,
    planner_revision,
    protocol_revision,
    binary_sha256,
):
    validation_configs = [
        {"role": "control", "label": BLIND, "search": SEARCHES[BLIND]},
        {"role": "control", "label": MS_EXACT, "search": SEARCHES[MS_EXACT]},
    ]
    if scores["selected"]["label"] not in (BLIND, MS_EXACT):
        validation_configs.append(
            {
                "role": "pilot-selected",
                "label": scores["selected"]["label"],
                "search": scores["selected"]["search"],
            }
        )
    return {
        "schema": ARTIFACT_SCHEMA,
        "pilot": {
            "protocol": runner.PROTOCOL,
            "selection_rule": runner.SELECTION_RULE,
            "planner_revision": planner_revision,
            "protocol_revision": protocol_revision,
            "planner_revision_is_protocol_ancestor": True,
            "planner_binary_sha256": binary_sha256,
            "planner_build_config": "release_no_lp",
            "benchmark_revision": suite_cost_manifest.EXPECTED_BENCHMARK_REVISION,
            "benchmark_repository": suite_cost_manifest.EXPECTED_BENCHMARK_REPOSITORY,
            "task_manifest": "ms_caps_pilot_suite.txt",
            "task_manifest_sha256": analyzer_utils.MANIFEST_DIGEST,
            "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
            "option_matrix_sha256": EXPECTED_MATRIX_SHA256,
            "options": option_records(),
            "task_count": EXPECTED_TASKS,
            "config_count": EXPECTED_CONFIGS,
            "expected_run_count": EXPECTED_CELLS,
            "time_limit_seconds": int(TIME_LIMIT_SECONDS),
            "memory_limit_mib": int(MEMORY_LIMIT_MIB),
            "par2_unsolved_seconds": int(PAR2_UNSOLVED_SECONDS),
            "properties_canonical_sha256": logical_properties_sha256(records),
        },
        "selection": {
            "image_time_tiebreak_used": scores["image_time_tiebreak_available"],
            "selected": _public_score(scores["selected"]),
            "ranking": [_public_score(score) for score in scores["ranking"]],
        },
        "paired_deltas": paired,
        "validation": {
            "requires_disjoint_tasks": True,
            "configs": validation_configs,
            "selected_config": {
                "label": scores["selected"]["label"],
                "search": scores["selected"]["search"],
            },
            "controls": [
                {"label": BLIND, "search": SEARCHES[BLIND]},
                {"label": MS_EXACT, "search": SEARCHES[MS_EXACT]},
            ],
        },
    }


def _fmt(value, digits=6):
    if value is None:
        return "NA"
    if type(value) is int:
        return str(value)
    return ("{:." + str(digits) + "g}").format(value)


def print_report(source, records, scores, paired):
    print("Arrhenius 20x50 pilot: {}".format(source))
    print("canonical properties SHA-256: {}".format(logical_properties_sha256(records)))
    print("selection rule: {}".format(runner.SELECTION_RULE))
    if scores["image_time_tiebreak_available"]:
        print("image-time tie-break: available (all 1000 cells schema-v2 certified)")
    else:
        print(
            "image-time tie-break: omitted (at least one cell lacks complete "
            "schema-v2 certified metrics)"
        )

    ranking_rows = []
    for score in scores["ranking"]:
        construction = score["construction"]
        width = score["cofactor_width"]
        ranking_rows.append(
            (
                score["rank"],
                score["label"],
                "{}/{}".format(score["coverage"], EXPECTED_TASKS),
                _fmt(score["micro_par2"]),
                _fmt(score["total_image_time"]),
                construction["fallbacks"],
                construction["pattern_fallbacks"],
                construction["unobserved"],
                width["observed"],
                _fmt(width["median"]),
                _fmt(width["maximum"]),
            )
        )
    print("\nPer-configuration ranking and construction/width summary")
    analyzer_utils.print_table(
        (
            "rank",
            "config",
            "coverage",
            "micro-PAR2",
            "image_time",
            "construct_fb",
            "pattern_fb",
            "construct_NA",
            "width_n",
            "width_med",
            "width_max",
        ),
        ranking_rows,
    )

    print("\nExact cofactor-width summaries")
    width_rows = []
    by_label = {score["label"]: score for score in scores["ranking"]}
    for label in LABELS:
        width = by_label[label]["cofactor_width"]
        width_rows.append(
            (
                label,
                width["observed"],
                _fmt(width["minimum"]),
                _fmt(width["median"]),
                _fmt(width["maximum"]),
            )
        )
    analyzer_utils.print_table(
        ("config", "observed", "minimum", "median", "maximum"), width_rows
    )

    print("\nPaired deltas (candidate minus reference; negative PAR2 is better)")
    paired_rows = [
        (
            item["label"],
            item["reference"],
            item["coverage_delta"],
            _fmt(item["micro_par2_delta"]),
            item["wins"],
            item["losses"],
            item["both_solved"],
            _fmt(item["total_image_time_delta"]),
        )
        for item in paired
    ]
    analyzer_utils.print_table(
        (
            "config",
            "reference",
            "d-coverage",
            "d-PAR2",
            "wins",
            "losses",
            "both-solved",
            "d-image-time",
        ),
        paired_rows,
    )
    print(
        "\nPASS: exact 1000-cell matrix, options, tasks, provenance, revision/cache, "
        "limits, scheduler fields, explained outcomes, and solved costs validated."
    )
    print("selected: {}".format(scores["selected"]["label"]))


def synthetic_record(
    label,
    search,
    task,
    planner_revision,
    protocol_revision,
    binary_sha256,
    planner_time,
    cost,
):
    domain, problem = task
    solved = planner_time is not None
    record = {
        "_source_key": "{}-{}-{}".format(label, domain, problem),
        "id": [label, domain, problem],
        "algorithm": label,
        "domain": domain,
        "problem": problem,
        "coverage": 1 if solved else 0,
        "planner_exit_code": 0 if solved else 23,
        "error": "success" if solved else "search-out-of-time",
        "unsolvable": 0,
        "component_options": expected_component_options(search),
        "driver_options": [
            "--validate",
            "--overall-time-limit",
            "30m",
            "--overall-memory-limit",
            "3584M",
            "--overall-time-limit",
            "300s",
            "--overall-memory-limit",
            "8G",
        ],
        "global_revision": planner_revision,
        "local_revision": planner_revision,
        "planner_time_limit": TIME_LIMIT_SECONDS,
        "planner_memory_limit": MEMORY_LIMIT_MIB,
        "benchmark_worktree": "/synthetic/downward-benchmarks",
        "metrics_validation_protocol": wbh_parser.METRICS_VALIDATION_PROTOCOL,
        "raw_metrics_complete": True,
        "piece_metrics_certified": True,
        "expanded_bdd_nodes": 40,
        "expanded_states": 100.0,
        "expanded_bdd_pieces": 10,
        "attempted_bdd_nodes": 50,
        "attempted_states": 120.0,
        "attempted_bdd_pieces": 12,
        "bucket_expansions": 8,
        "bucket_expansion_attempts": 10,
        "image_events": 6,
        "bucket_images": 6,
        "image_source_buckets": 7,
        "image_source_pieces": 8,
        "image_calls_attempted": 7,
        "image_calls_completed": 6,
        "batched_images": 1,
        "image_time": 10.0,
    }
    record.update(
        expected_protocol_metadata(
            planner_revision, protocol_revision, binary_sha256
        )
    )
    record.update(SCHEMA_V2_CONVENTIONS)
    if solved:
        record["solution_cost"] = cost
        record["planner_time"] = planner_time
    if label != BLIND:
        if label.startswith("ms_"):
            record.update(
                {
                    "heuristic_kind": "merge_and_shrink",
                    "heuristic_size_bound": 10000,
                    "value_cap": _expected_ms_value_cap(label),
                }
            )
        else:
            kind = "pdb_cegar" if "cegar" in label else "pdb_goal_directed"
            if "bdd" in label:
                kind = "pdb_bdd_order"
            if "goal_fill" in label:
                kind = "pdb_goal_fill"
            record.update(
                {
                    "heuristic_kind": kind,
                    "heuristic_size_bound": 100000,
                    "value_cap": -1,
                }
            )
        record.update(
            {
                "construction_completed": True,
                "construction_time": 0.25,
                "cofactor_width": 4,
                "width_upper_bound": 25,
                "num_values": 5,
                "num_terminals": 5,
                "add_nodes": 20,
            }
        )
    return record


def _expect_error(
    records,
    tasks,
    planner_revision,
    protocol_revision,
    binary_sha256,
    fragment,
):
    _, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    if not any(fragment in error for error in errors):
        raise AssertionError(
            "synthetic mutation did not produce {!r}: {!r}".format(fragment, errors[:8])
        )


def self_test():
    planner_revision = EXPECTED_PLANNER_REVISION
    protocol_revision = "0123456789abcdef0123456789abcdef01234567"
    binary_sha256 = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
    assert require_reviewed_pins(protocol_revision, binary_sha256) == (
        planner_revision,
        protocol_revision,
        binary_sha256,
    )
    validate_runner_contract(check_cache_pin=False)
    tasks = analyzer_utils.load_manifest(runner.MANIFEST)
    if [analyzer_utils.task_label(task) for task in tasks] != runner.read_manifest():
        raise AssertionError("runner/analyzer task order differs")

    base_times = {label: 30.0 + index for index, label in enumerate(LABELS)}
    base_times[BLIND] = 20.0
    base_times[MS_EXACT] = 15.0
    base_times["ms_cap2"] = 10.0
    base_times["ms_cap4"] = 10.0
    base_times["pdb_cegar_b100k"] = 5.0
    records = []
    for label, search in CONFIGS:
        for task_index, task in enumerate(tasks):
            planner_time = base_times[label]
            # Coverage dominates runtime: this nearly-free 49/50 config must
            # still rank below every 50/50 configuration.
            if label == "pdb_goal_fill_b100k":
                planner_time = 0.01 if task_index else None
            record = synthetic_record(
                label,
                search,
                task,
                planner_revision,
                protocol_revision,
                binary_sha256,
                planner_time,
                task_index + 1,
            )
            record["image_time"] = 2.0
            if label == "ms_cap2":
                record["image_time"] = 9.0
            if label == "ms_cap4":
                record["image_time"] = 1.0
            records.append(record)

    # Exercise the new construction-budget fallback without losing a solved
    # outcome or schema-v2 search metrics.
    budget_record = next(
        record
        for record in records
        if record["algorithm"] == "ms_exact_budget30"
        and record["domain"] == tasks[0][0]
        and record["problem"] == tasks[0][1]
    )
    for field in (
        "cofactor_width",
        "width_upper_bound",
        "num_values",
        "num_terminals",
        "add_nodes",
    ):
        budget_record.pop(field)
    budget_record["construction_completed"] = False

    matrix, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    assert not errors, errors[:10]
    scores = analyze_scores(matrix, tasks)
    assert scores["image_time_tiebreak_available"] is True
    assert scores["selected"]["label"] == "pdb_cegar_b100k"
    rank = {item["label"]: item["rank"] for item in scores["ranking"]}
    assert rank["ms_cap4"] < rank["ms_cap2"]
    assert rank["pdb_goal_fill_b100k"] > rank[MS_EXACT]
    budget_score = next(
        score for score in scores["ranking"] if score["label"] == "ms_exact_budget30"
    )
    assert budget_score["construction"]["fallbacks"] == 1
    assert budget_score["cofactor_width"]["observed"] == 49

    paired = all_paired_deltas(
        matrix, tasks, scores["image_time_tiebreak_available"]
    )
    assert len(paired) == EXPECTED_CONFIGS * 2
    winner_vs_blind = next(
        item
        for item in paired
        if item["label"] == "pdb_cegar_b100k" and item["reference"] == BLIND
    )
    assert winner_vs_blind["coverage_delta"] == 0
    assert math.isclose(winner_vs_blind["micro_par2_delta"], -15.0)

    artifact = make_selection_artifact(
        records,
        scores,
        paired,
        planner_revision,
        protocol_revision,
        binary_sha256,
    )
    first_json = canonical_json(artifact)
    second_json = canonical_json(
        make_selection_artifact(
            list(reversed(records)),
            scores,
            paired,
            planner_revision,
            protocol_revision,
            binary_sha256,
        )
    )
    assert first_json == second_json
    assert artifact["validation"]["requires_disjoint_tasks"] is True
    assert [item["label"] for item in artifact["validation"]["configs"]] == [
        BLIND,
        MS_EXACT,
        "pdb_cegar_b100k",
    ]
    assert artifact["selection"]["selected"]["label"] == "pdb_cegar_b100k"

    # One incomplete but semantically valid schema-v2 timeout suppresses the
    # image-time criterion for the entire ranking.  The tied configs then use
    # their labels, as the predeclared rule requires.
    incomplete = next(
        record
        for record in records
        if record["algorithm"] == "pdb_goal_fill_b100k"
        and record["coverage"] == 0
    )
    incomplete["raw_metrics_complete"] = False
    matrix, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    assert not errors, errors[:10]
    no_image_scores = analyze_scores(matrix, tasks)
    assert no_image_scores["image_time_tiebreak_available"] is False
    no_image_rank = {
        item["label"]: item["rank"] for item in no_image_scores["ranking"]
    }
    assert no_image_rank["ms_cap2"] < no_image_rank["ms_cap4"]
    incomplete["raw_metrics_complete"] = True

    # A translation-stage explained resource outcome legitimately has no WBH
    # file. It remains an unsolved PAR2 cell but cannot certify image time.
    saved_presearch = dict(incomplete)
    incomplete["planner_exit_code"] = 20
    incomplete["error"] = "translate-out-of-memory"
    incomplete["unsolvable"] = 0
    incomplete.update(EMPTY_LEGACY_CONVENTIONS)
    incomplete["raw_metrics_complete"] = False
    incomplete["piece_metrics_certified"] = False
    for field in (
        SCHEMA_V2_INTEGER_METRICS
        + SCHEMA_V2_REAL_METRICS
        + (
            "construction_completed",
            "construction_time",
            "heuristic_kind",
            "heuristic_size_bound",
            "value_cap",
            "cofactor_width",
            "width_upper_bound",
            "num_values",
            "num_terminals",
            "add_nodes",
        )
    ):
        incomplete.pop(field, None)
    matrix, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    assert not errors, errors[:10]
    assert analyze_scores(matrix, tasks)["image_time_tiebreak_available"] is False
    incomplete.clear()
    incomplete.update(saved_presearch)

    # Fail-closed matrix, metadata, revision/cache, option, resource, scheduler,
    # outcome, metric, construction, and solved-cost mutations.
    mutations = (
        ("protocol", "wrong", "protocol="),
        ("planner_revision", "f" * 40, "planner_revision="),
        ("protocol_revision", "e" * 40, "protocol_revision="),
        ("planner_binary_sha256", "e" * 64, "planner_binary_sha256="),
        ("driver_time_limit", "301s", "driver_time_limit="),
        ("scheduler_partition", "gpu", "scheduler_partition="),
        ("scheduler_array_tasks", 999, "scheduler_array_tasks="),
        ("task_sources_sha256", "d" * 64, "task_sources_sha256="),
        ("metrics_validation_protocol", "wrong", "metrics_validation_protocol="),
        ("coverage", 2, "coverage must be integer 0 or 1"),
    )
    target = records[0]
    for field, bad_value, fragment in mutations:
        old_value = target[field]
        target[field] = bad_value
        _expect_error(
            records,
            tasks,
            planner_revision,
            protocol_revision,
            binary_sha256,
            fragment,
        )
        target[field] = old_value

    old_options = target["component_options"]
    target["component_options"] = ["--search", "sym_fw()"]
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "component_options=",
    )
    target["component_options"] = old_options

    old_cost = target["solution_cost"]
    target["solution_cost"] = old_cost + 1
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "solved-cost disagreement",
    )
    target["solution_cost"] = old_cost

    old_exit = target["planner_exit_code"]
    target["planner_exit_code"] = 32
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "explained outcome",
    )
    target["planner_exit_code"] = old_exit

    old_image_time = target["image_time"]
    target["image_time"] = -1
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "image_time",
    )
    target["image_time"] = old_image_time

    target["image_time"] = str(old_image_time)
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "JSON-number schema-v2 metric",
    )
    target["image_time"] = old_image_time

    old_planner_time = target["planner_time"]
    target["planner_time"] = str(old_planner_time)
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "finite nonnegative planner_time",
    )
    target["planner_time"] = old_planner_time

    saved_counter = target.pop("image_calls_completed")
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "image_calls_completed must be a nonnegative integer",
    )
    target["image_calls_completed"] = saved_counter

    unsolved = next(record for record in records if record["coverage"] == 0)
    unsolved["solution_cost"] = 1
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "must not contain solution_cost",
    )
    del unsolved["solution_cost"]

    old_outcome = (
        unsolved["planner_exit_code"],
        unsolved["error"],
        unsolved["unsolvable"],
    )
    unsolved["planner_exit_code"] = 11
    unsolved["error"] = "search-unsolvable"
    unsolved["unsolvable"] = 1
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "solved/proved-unsolvable disagreement",
    )
    (
        unsolved["planner_exit_code"],
        unsolved["error"],
        unsolved["unsolvable"],
    ) = old_outcome

    duplicate = dict(records[0])
    records.append(duplicate)
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "duplicate cell",
    )
    records.pop()

    removed = records.pop()
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "missing 1 of 1000 expected algorithm-task cells",
    )
    records.append(removed)

    completed_heuristic = next(
        record
        for record in records
        if record["algorithm"] == MS_EXACT
        and record.get("construction_completed") is True
    )
    saved_width = completed_heuristic.pop("cofactor_width")
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "completed construction lacks exact cofactor_width",
    )
    completed_heuristic["cofactor_width"] = saved_width

    assert require_reviewed_pins() == (
        EXPECTED_PLANNER_REVISION,
        EXPECTED_PROTOCOL_REVISION,
        EXPECTED_CACHE_BINARY_SHA256,
    )

    print(
        "synthetic Arrhenius analyzer tests: PASS "
        "(1000 cells, exact protocol, outcomes/costs, ranking, censoring, artifact)"
    )


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    planner_revision, protocol_revision, binary_sha256 = require_reviewed_pins()
    validate_runner_contract(
        check_cache_pin=True, expected_cache_hash=binary_sha256
    )
    if args.properties is None:
        raise AnalysisError("properties input is required")
    tasks = analyzer_utils.load_manifest(args.manifest)
    if [analyzer_utils.task_label(task) for task in tasks] != runner.read_manifest():
        raise AnalysisError("analyzed task sequence differs from the exact runner manifest")
    records, source = analyzer_utils.load_properties(args.properties)
    matrix, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    raise_validation_errors(errors)
    scores = analyze_scores(matrix, tasks)
    paired = all_paired_deltas(
        matrix, tasks, scores["image_time_tiebreak_available"]
    )
    if args.emit_selection_artifact:
        artifact = make_selection_artifact(
            records,
            scores,
            paired,
            planner_revision,
            protocol_revision,
            binary_sha256,
        )
        # This mode has no other stdout output and performs no writes.
        print(canonical_json(artifact))
    else:
        print_report(source, records, scores, paired)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AnalysisError, analyzer_utils.AnalysisError, RuntimeError) as err:
        print("analysis error: {}".format(err), file=sys.stderr)
        sys.exit(2)
