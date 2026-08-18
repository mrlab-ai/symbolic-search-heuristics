#!/usr/bin/env python3
"""Fail-closed analysis for the prospective PDB cap-grid development screen.

This analyzer is frozen before the 300-cell screen is launched.  It is a
descriptive mechanism-screen analyzer, not an inferential or confirmatory
analysis.  Ordinary analysis refuses before reading properties until the
clean launch revision, cached binaries, and canonical properties digest have
all been independently reviewed and pinned.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_arrhenius_selector_pilot as legacy
import analyze_arrhenius_selector_validation as safe_loader
import analyze_ms_caps_pilot as analyzer_utils
import exp_arrhenius_common as common
import exp_pdb_cap_grid_pilot as runner
import pdb_cap_selector_parser as cap_parser
import suite_cost_manifest


class AnalysisError(RuntimeError):
    pass


ANALYSIS_SCHEMA = (
    "symbolic-search-heuristics/pdb-cap-grid-development-analysis/v3"
)
ANALYSIS_PROTOCOL = "pdb-cap-grid-fixed-development-screen-analysis/v3"
DECISION_ROLE = "development-mechanism-screen-no-population-inference/v1"

# These five pins are deliberately all unset at the prospective boundary.
# A descendant analysis commit may set them only after independent review of
# the immutable launch and canonical 300-record properties file.
EXPECTED_PROTOCOL_REVISION = None
EXPECTED_PLANNER_REVISION = None
EXPECTED_CACHE_BINARY_SHA256 = None
EXPECTED_CACHE_PREPROCESS_SHA256 = None
EXPECTED_PROPERTIES_CANONICAL_SHA256 = None

EXPECTED_PROTOCOL = "pdb-cap-grid-development-screen-v3"
EXPECTED_SELECTION_RULE = "fixed-k8-primary-k32-sensitivity-no-promotion/v1"
EXPECTED_TASKS = 50
EXPECTED_DOMAINS = 25
EXPECTED_CONFIGS = 6
EXPECTED_CELLS = 300
TIME_LIMIT_SECONDS = 300.0
PAR2_UNSOLVED_SECONDS = 600.0
MEMORY_LIMIT_MIB = 8192.0
EXPECTED_CACHE_NAME_SUFFIX = "_61a748e5"
EXPECTED_PYTHON_VERSION = "3.9.25"
EXPECTED_LAB_VERSION = "8.0"
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168"
)
EXPECTED_TASK_MANIFEST_SHA256 = (
    "3195dac7e62a34e5ac4cbeb715ab7f9b99e2ee64341082dd7d718ea2820751ca"
)
EXPECTED_TASK_SOURCES_SHA256 = (
    "dbb7730c257472c07f7946f0434949449169e06d1faa2174a92a6d13c48cb8ba"
)
EXPECTED_BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
EXPECTED_BENCHMARK_REPOSITORY = (
    "https://github.com/aibasel/downward-benchmarks.git"
)
EXPECTED_MATERIALIZED_PDDL_PROTOCOL = (
    "per-cell-independent-manual-byte-copy-temp-digest-atomic-replace-readonly/v1"
)
EXPECTED_RAW_POOL_PROTOCOL = "fixed_pool_v1"
EXPECTED_RAW_POOL_SCORE = (
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
)

CONFIGS = (
    ("blind_fw", "sym_fw()"),
    (
        "pdb_cegar_b100k",
        "sym_fw_pdb(budget=100000,pattern_selection=cegar,"
        "cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k8",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=8,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_cap_grid_k8",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=8,cegar_max_time=10,cegar_seed=2011,"
        "select_value_cap=true)",
    ),
    (
        "pdb_selector_k32",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=32,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_cap_grid_k32",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=32,cegar_max_time=10,cegar_seed=2011,"
        "select_value_cap=true)",
    ),
)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
BLIND = "blind_fw"
CEGAR = "pdb_cegar_b100k"
EXACT_LABELS = {8: "pdb_selector_k8", 32: "pdb_selector_k32"}
CAP_LABELS = {8: "pdb_cap_grid_k8", 32: "pdb_cap_grid_k32"}

EXPECTED_ANALYSIS_CONTRACT = {
    "status": "prospective-before-any-300-cell-matrix-outcome-inspection",
    "population": "development-selected-p4-50-task-manifest",
    "inference": "none",
    "primary_width_budget": 8,
    "sensitivity_width_budget": 32,
    "sensitivity_may_replace_primary": False,
    "primary_performance_estimand": (
        "paired-cap-grid-minus-exact-k8-coverage-wins-minus-losses-over-50/v1"
    ),
    "primary_mechanism_estimand": (
        "paired-semantic-nontrivial-selection-rate-difference-over-50/v1"
    ),
    "primary_mechanism_missingness": (
        "requires-both-complete-certified-traces-and-equal-raw-pool-"
        "fingerprints-on-all-50-otherwise-not-estimable-no-imputation/v1"
    ),
    "raw_pool_isolation": (
        "requires-equal-exact-vs-cap-grid-raw-pool-fingerprints-on-all-50-"
        "otherwise-cap-attribution-not-certified-and-no-promotion/v1"
    ),
    "semantic_nontrivial": "finite_sum-positive-or-dead_count-positive/v1",
    "ordered_secondary": [
        "construction-charged-micro-par2-seconds",
        "jointly-solved-planner-cpu-geometric-mean-ratio",
        "paired-raw-complete-certified-image-time-ratio",
        "paired-raw-complete-certified-effort-ratio",
        "construction-time-seconds",
        "effective-cap-source-pattern-size-W-A-T-U-V-distributions",
    ],
    "secondary_pair_rules": {
        "ratio_direction": "cap-grid-over-same-k-exact/v1",
        "planner_cpu": "jointly-solved-positive-planner-time-pairs/v1",
        "image_time": "both-raw-complete-piece-certified-pairs/v1",
        "effort": (
            "expanded-bdd-node-totals-on-both-raw-complete-"
            "piece-certified-pairs/v1"
        ),
        "construction": "both-completed-observed-construction-pairs/v1",
        "denominators": "report-every-eligible-pair-count-no-substitution/v1",
    },
    "confirmation_policy": (
        "screen-cannot-support-population-confirmation-or-pivot-alone"
    ),
}
EXPECTED_CAP_GRID = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, "exact"]
EXPECTED_FINITE_CAP_GRID = tuple(EXPECTED_CAP_GRID[:-1])
EXPECTED_SELECTOR_SOURCES = (
    "empty",
    "bdd_prefix",
    "goal_prefix",
    "goal_fill",
    "cegar",
)
EXPECTED_CAP_SCORE_VERSION = (
    "per_pattern_strongest_feasible_cap_then_"
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
)
EXPECTED_CAP_RECORD_KEYS = (
    "protocol", "score_version", "sources", "pattern", "abstract_states",
    "initial_dead_end", "initial_h", "finite_sum", "finite_count",
    "dead_count", "cofactor_width", "width_upper_bound",
    "cofactor_width_budget", "value_cap", "add_nodes", "num_terminals",
    "raw_add_nodes", "raw_num_terminals", "raw_cofactor_width",
    "raw_width_upper_bound", "raw_num_values", "raw_max_finite_value",
    "raw_finite_sum", "raw_finite_count", "raw_dead_count",
    "raw_initial_dead_end", "raw_initial_h", "raw_initial_value_count",
    "raw_value_histogram", "transformed_num_values", "feasible",
    "rejection_reason",
)
EXPECTED_CAP_STATISTIC_KEYS = (
    "initial_dead_end", "initial_h", "finite_sum", "finite_count",
    "dead_count", "cofactor_width", "width_upper_bound", "add_nodes",
    "num_terminals", "raw_add_nodes", "raw_num_terminals",
    "raw_cofactor_width", "raw_width_upper_bound", "raw_num_values",
    "raw_max_finite_value", "raw_finite_sum", "raw_finite_count",
    "raw_dead_count", "raw_initial_dead_end", "raw_initial_h",
    "raw_initial_value_count", "raw_value_histogram",
    "transformed_num_values",
)

COMMON_METADATA_KEYS = (
    "planner_revision",
    "protocol_revision",
    "planner_revision_is_protocol_ancestor",
    "planner_build_options",
    "planner_build_config",
    "planner_binary_sha256",
    "planner_revision_cache_name",
    "external_plan_validation",
    "plan_validation_protocol",
    "plan_file_parser_protocol",
    "outcome_reconciliation_protocol",
    "cofactor_width_property",
    "cofactor_width_parser_protocol",
    "metrics_validation_protocol",
    "python_version",
    "lab_version",
    "required_lab_version",
    "task_order_seed",
    "task_order_method",
    "driver_time_limit",
    "driver_memory_limit",
    "scheduler_environment",
    "scheduler_cluster",
    "scheduler_cpu_model",
    "scheduler_partition",
    "scheduler_qos",
    "scheduler_account",
    "scheduler_time_limit_per_task",
    "scheduler_memory_per_cpu",
    "scheduler_cpus_per_task",
    "scheduler_array_task_throttle",
    "scheduler_max_array_tasks",
    "scheduler_array_tasks",
    "scheduler_runs_per_array_task",
    "declared_run_count",
    "repetitions",
)

SELECTOR_TRACE_FIELDS = (
    common.PDB_SELECTOR_CANDIDATES_PROPERTY,
    common.PDB_SELECTOR_SELECTED_PROPERTY,
    common.PDB_SELECTOR_FINAL_PROPERTY,
    common.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY,
    common.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY,
    common.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY,
    common.PDB_SELECTOR_TRACE_SHA256_PROPERTY,
    common.PDB_SELECTOR_POOL_SHA256_PROPERTY,
    cap_parser.RAW_POOL_SHA256_PROPERTY,
    "pdb_cap_selector_parser_protocol",
)
PDB_FINAL_FIELDS = (
    "pdb_final_format",
    "pdb_pattern_size",
    "pdb_selected_source",
    "pdb_abstract_states",
    "pdb_cofactor_width_budget",
    "pdb_selected_value_cap",
    "pdb_final_num_values",
    "pdb_final_cofactor_width",
    "pdb_final_width_upper_bound",
)


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


def _same(actual, expected):
    return type(actual) is type(expected) and actual == expected


def _number(value):
    if type(value) not in (int, float):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _require_sha(value, label, digits):
    if not isinstance(value, str) or len(value) != digits:
        raise AnalysisError("{} must be {} lowercase hex digits".format(label, digits))
    if any(char not in "0123456789abcdef" for char in value):
        raise AnalysisError("{} must be lowercase hexadecimal".format(label))
    if len(set(value)) == 1:
        raise AnalysisError("{} still looks synthetic".format(label))


def _append(errors, prefix, message):
    errors.append("{}: {}".format(prefix, message))


def _prefix(label, task):
    return "{} {}:{}".format(label, task[0], task[1])


def load_tasks():
    try:
        text = runner.MANIFEST.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as err:
        raise AnalysisError("cannot read cap-grid task manifest: {}".format(err))
    labels = []
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        label = raw_line.strip()
        if not label or label.startswith("#"):
            continue
        fields = label.split(":")
        if len(fields) != 2 or not all(fields):
            raise AnalysisError(
                "cap-grid task manifest line {} is not DOMAIN:PROBLEM".format(
                    lineno
                )
            )
        labels.append(label)
    payload = "".join("{}\n".format(label) for label in labels)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if digest != EXPECTED_TASK_MANIFEST_SHA256:
        raise AnalysisError(
            "cap-grid task manifest digest changed: {} != {}".format(
                digest, EXPECTED_TASK_MANIFEST_SHA256
            )
        )
    tasks = [tuple(label.split(":", 1)) for label in labels]
    domain_counts = defaultdict(int)
    for domain, _ in tasks:
        domain_counts[domain] += 1
    if (
        len(tasks) != EXPECTED_TASKS
        or len(set(tasks)) != EXPECTED_TASKS
        or len(domain_counts) != EXPECTED_DOMAINS
        or set(domain_counts.values()) != {2}
    ):
        raise AnalysisError("cap-grid task manifest shape changed")
    unsupported = sorted(set(tasks) - suite_cost_manifest.supported_tasks())
    if unsupported:
        raise AnalysisError(
            "cap-grid manifest contains unsupported tasks: {}".format(
                ", ".join("{}:{}".format(*task) for task in unsupported)
            )
        )
    return tasks


def expected_protocol_metadata(
    planner_revision,
    protocol_revision,
    binary_sha256,
    preprocess_sha256,
    benchmark_worktree,
):
    # The accepted P4 analyzer holds the reviewed common Lab-8.0 execution
    # constants.  Select only the common fields, then replace the run-layout
    # fields and add this prospectively frozen protocol's exact identity.
    legacy_static = legacy.expected_protocol_metadata(
        planner_revision, protocol_revision, binary_sha256
    )
    metadata = {key: copy.deepcopy(legacy_static[key]) for key in COMMON_METADATA_KEYS}
    metadata.update(
        {
            "scheduler_array_tasks": EXPECTED_CELLS,
            "scheduler_runs_per_array_task": 1,
            "declared_run_count": EXPECTED_CELLS,
            "planner_preprocess_sha256": preprocess_sha256,
            "protocol": EXPECTED_PROTOCOL,
            "selection_rule": EXPECTED_SELECTION_RULE,
            "analysis_contract": copy.deepcopy(EXPECTED_ANALYSIS_CONTRACT),
            "task_manifest": "selector_pilot_suite.txt",
            "task_manifest_sha256": runner.MANIFEST_DIGEST,
            "task_count": EXPECTED_TASKS,
            "domain_count": EXPECTED_DOMAINS,
            "experiment_data_directory": "data/exp_pdb_cap_grid_pilot",
            "pdb_selector_parser_protocol": cap_parser.PARSER_PROTOCOL,
            "selector_pool_protocol": cap_parser.PROTOCOL,
            "selector_score_version": cap_parser.SCORE_VERSION,
            "selector_source_order": list(common.PDB_SELECTOR_SOURCES),
            "selector_value_caps": list(runner.CAP_GRID),
            "selector_width_budgets": [8, 32],
            "selector_state_budget": 100000,
            "selector_cegar_max_time": 10,
            "selector_cegar_seed": 2011,
            "selector_dynamic_reordering": False,
            "raw_pdb_materializations_per_pattern": 1,
            "selector_trivial_domain_variables": "removed-before-pool-dedup/v1",
            "selector_trace_encoding": (
                "exact-uvarint-delta-count-histogram-once-per-pattern/v3"
            ),
            "selector_histogram_max_decoded_bytes_per_pattern": (
                cap_parser.MAX_HISTOGRAM_BYTES
            ),
            "selector_histogram_max_base64_bytes_per_pattern": (
                cap_parser.MAX_HISTOGRAM_BASE64
            ),
            "selector_histogram_max_materialized_patterns": (
                runner.MAX_MATERIALIZED_PATTERN_GROUPS
            ),
            "selector_histogram_max_total_base64_bytes": (
                runner.MAX_HISTOGRAM_TOTAL_BASE64_BYTES
            ),
            "planner_soft_stdout_limit_kib": (
                runner.PLANNER_SOFT_STDOUT_LIMIT_KIB
            ),
            "planner_hard_stdout_limit_kib": (
                runner.PLANNER_HARD_STDOUT_LIMIT_KIB
            ),
            "finite_value_transform": "min(d,kappa);infinity-retained/v1",
            "per_pattern_choice": "strongest-feasible-cap-before-score/v1",
            "config_count": EXPECTED_CONFIGS,
            "option_matrix_sha256": runner.OPTION_MATRIX_SHA256,
            "benchmark_revision": runner.BENCHMARK_REVISION,
            "benchmark_repository": runner.BENCHMARK_REPOSITORY,
            "benchmark_worktree": benchmark_worktree,
            "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "task_sources_sha256": runner.EXPECTED_TASK_SOURCES_SHA256,
            "materialized_pddl_protocol": runner.MATERIALIZED_PDDL_PROTOCOL,
            "materialized_pddl_files": runner.EXPECTED_MATERIALIZED_PDDL_FILES,
            "materialized_pddl_bytes": runner.EXPECTED_MATERIALIZED_PDDL_BYTES,
            "pddl_bytes_per_config": runner.EXPECTED_PDDL_BYTES_PER_CONFIG,
            "unique_pddl_source_files": runner.EXPECTED_UNIQUE_PDDL_SOURCE_FILES,
            "unique_pddl_source_bytes": runner.EXPECTED_UNIQUE_PDDL_SOURCE_BYTES,
        }
    )
    return metadata


def validate_runner_contract(check_reviewed_pins=True):
    errors = []
    exact_pairs = (
        (runner.PROTOCOL, EXPECTED_PROTOCOL, "protocol"),
        (runner.SELECTION_RULE, EXPECTED_SELECTION_RULE, "selection rule"),
        (tuple(runner.CONFIGS), CONFIGS, "configuration matrix"),
        (runner.OPTION_MATRIX_SHA256, "70a34cc1804f542c8911bd5de4c44e5b820772832dda73e426fb2081366455fa", "matrix digest"),
        (runner.EXPECTED_TASKS, EXPECTED_TASKS, "task count"),
        (runner.EXPECTED_DOMAINS, EXPECTED_DOMAINS, "domain count"),
        (runner.EXPECTED_MATERIALIZED_PDDL_FILES, 600, "PDDL file count"),
        (runner.EXPECTED_MATERIALIZED_PDDL_BYTES, 15106272, "PDDL byte count"),
        (cap_parser.PROTOCOL, "fixed_pool_cap_grid_v6", "cap-grid trace protocol"),
        (cap_parser.PARSER_PROTOCOL, "run.log/pdb-cap-grid-whole-trace/v4", "cap-grid parser protocol"),
        (runner.CAP_GRID, EXPECTED_CAP_GRID, "cap grid"),
        (cap_parser.GRID, EXPECTED_FINITE_CAP_GRID, "parser finite cap grid"),
        (cap_parser.SCORE_VERSION, EXPECTED_CAP_SCORE_VERSION, "cap-grid score"),
        (cap_parser.RECORD_KEYS, EXPECTED_CAP_RECORD_KEYS, "cap-grid record schema"),
        (cap_parser.STATISTIC_KEYS, EXPECTED_CAP_STATISTIC_KEYS, "cap-grid statistic schema"),
        (cap_parser.MAX_ABSTRACT_STATES, 100000, "cap-grid state bound"),
        (cap_parser.INT_MAX, 2147483647, "cap-grid producer int bound"),
        (cap_parser.INT64_MAX, 9223372036854775807, "cap-grid producer int64 bound"),
        (cap_parser.HISTOGRAM_DIGEST_RE.pattern, r"^sha256:[0-9a-f]{64}$", "histogram digest grammar"),
        (cap_parser.HISTOGRAM_DIGEST_RE.flags, int(re.UNICODE), "histogram digest flags"),
        (cap_parser.HISTOGRAM_WIRE_RE.pattern, r"^[A-Za-z0-9_-]+$", "histogram wire grammar"),
        (cap_parser.HISTOGRAM_WIRE_RE.flags, int(re.UNICODE), "histogram wire flags"),
        (cap_parser.MAX_HISTOGRAM_BYTES, 800003, "histogram decoded-byte bound"),
        (cap_parser.MAX_HISTOGRAM_BASE64, 1066671, "histogram base64 bound"),
        (runner.MAX_MATERIALIZED_PATTERN_GROUPS, 5, "histogram pattern bound"),
        (runner.MAX_HISTOGRAM_TOTAL_BASE64_BYTES, 5333355, "histogram total bound"),
        (runner.PLANNER_SOFT_STDOUT_LIMIT_KIB, 7168, "planner stdout soft bound"),
        (runner.PLANNER_HARD_STDOUT_LIMIT_KIB, 16384, "planner stdout hard bound"),
        (common.PDB_SELECTOR_SOURCES, EXPECTED_SELECTOR_SOURCES, "selector source order"),
        (common.PDB_SELECTOR_POOL_PROTOCOL, EXPECTED_RAW_POOL_PROTOCOL, "raw-pool protocol"),
        (common.PDB_SELECTOR_SCORE_VERSION, EXPECTED_RAW_POOL_SCORE, "raw-pool score"),
        (runner.MANIFEST_DIGEST, EXPECTED_TASK_MANIFEST_SHA256, "task manifest digest"),
        (runner.EXPECTED_TASK_SOURCES_SHA256, EXPECTED_TASK_SOURCES_SHA256, "task-source digest"),
        (runner.BENCHMARK_REVISION, EXPECTED_BENCHMARK_REVISION, "benchmark revision"),
        (runner.BENCHMARK_REPOSITORY, EXPECTED_BENCHMARK_REPOSITORY, "benchmark repository"),
        (runner.MATERIALIZED_PDDL_PROTOCOL, EXPECTED_MATERIALIZED_PDDL_PROTOCOL, "PDDL protocol"),
        (suite_cost_manifest.EXPECTED_MANIFEST_SHA256, EXPECTED_SOURCE_MANIFEST_SHA256, "source manifest digest"),
    )
    for actual, expected, label in exact_pairs:
        if not _same(actual, expected):
            errors.append("{} changed".format(label))
    if canonical_json(runner.ANALYSIS_CONTRACT) != canonical_json(
        EXPECTED_ANALYSIS_CONTRACT
    ):
        errors.append("prospective analysis contract changed")
    for field in (
        "raw_max_finite_value",
        "raw_initial_value_count",
        "raw_value_histogram",
    ):
        if field not in cap_parser.RECORD_KEYS:
            errors.append("cap-grid trace lacks {}".format(field))
    if check_reviewed_pins:
        runner_pins = (
            runner.PLANNER_REVISION,
            runner.CACHE_BINARY_SHA256,
            runner.CACHE_PREPROCESS_SHA256,
        )
        analyzer_pins = (
            EXPECTED_PLANNER_REVISION,
            EXPECTED_CACHE_BINARY_SHA256,
            EXPECTED_CACHE_PREPROCESS_SHA256,
        )
        if runner_pins != analyzer_pins:
            errors.append("runner/analyzer launch pins differ")
    if errors:
        raise AnalysisError("runner/analyzer contract mismatch: " + "; ".join(errors))


def require_reviewed_pins(properties_sha256):
    pins = (
        EXPECTED_PROTOCOL_REVISION,
        EXPECTED_PLANNER_REVISION,
        EXPECTED_CACHE_BINARY_SHA256,
        EXPECTED_CACHE_PREPROCESS_SHA256,
        EXPECTED_PROPERTIES_CANONICAL_SHA256,
    )
    if any(value is None for value in pins):
        if not all(value is None for value in pins):
            raise AnalysisError("cap-grid analysis pins are only partially set")
        raise AnalysisError(
            "cap-grid analysis pins are unset; refusing to read pilot outcomes"
        )
    _require_sha(EXPECTED_PROTOCOL_REVISION, "protocol revision", 40)
    _require_sha(EXPECTED_PLANNER_REVISION, "planner revision", 40)
    _require_sha(EXPECTED_CACHE_BINARY_SHA256, "planner binary SHA-256", 64)
    _require_sha(EXPECTED_CACHE_PREPROCESS_SHA256, "preprocess SHA-256", 64)
    _require_sha(EXPECTED_PROPERTIES_CANONICAL_SHA256, "properties SHA-256", 64)
    if properties_sha256 != EXPECTED_PROPERTIES_CANONICAL_SHA256:
        raise AnalysisError(
            "canonical properties digest changed: expected {}, got {}".format(
                EXPECTED_PROPERTIES_CANONICAL_SHA256, properties_sha256
            )
        )
    validate_runner_contract(check_reviewed_pins=True)


def _selector_budget(label):
    if label.endswith("k8"):
        return 8
    if label.endswith("k32"):
        return 32
    raise AnalysisError("not a selector label: {}".format(label))


def _validate_static_record(record, label, task, expected_static, errors):
    prefix = _prefix(label, task)
    if record.get("algorithm") != label:
        _append(errors, prefix, "algorithm identity changed")
    if record.get("domain") != task[0] or record.get("problem") != task[1]:
        _append(errors, prefix, "domain/problem identity changed")
    if record.get("id") not in (None, [label, task[0], task[1]]):
        _append(errors, prefix, "id is not the exact cell identity")
    expected_options = legacy.expected_component_options(SEARCHES[label])
    if record.get("component_options") != expected_options:
        _append(errors, prefix, "component_options changed")
    expected_driver = [
        "--overall-time-limit",
        "30m",
        "--overall-memory-limit",
        "3584M",
        "--build",
        "release_no_lp",
        "--overall-time-limit",
        "300s",
        "--overall-memory-limit",
        "8G",
    ]
    if record.get("driver_options") != expected_driver:
        _append(errors, prefix, "driver_options changed")
    for field, expected in expected_static.items():
        if not _same(record.get(field), expected):
            _append(
                errors,
                prefix,
                "{}={!r}, expected {!r}".format(field, record.get(field), expected),
            )
    for field, expected in (
        ("planner_time_limit", TIME_LIMIT_SECONDS),
        ("planner_memory_limit", MEMORY_LIMIT_MIB),
    ):
        actual = _number(record.get(field))
        if actual is None or actual != expected:
            _append(errors, prefix, "{} changed".format(field))


def _validate_heuristic_stats(record, label, prefix, errors):
    fields = ("cofactor_width", "width_upper_bound", "num_values", "num_terminals", "add_nodes")
    construction_fields = (
        "construction_completed",
        "construction_time",
        "heuristic_kind",
        "heuristic_size_bound",
        "value_cap",
    )
    if label == BLIND:
        unexpected = [field for field in fields + construction_fields if field in record]
        if unexpected:
            _append(errors, prefix, "blind record contains heuristic fields")
        return

    completed_present = "construction_completed" in record
    completed = record.get("construction_completed")
    if completed_present and type(completed) is not bool:
        _append(errors, prefix, "construction_completed must be boolean")
        return
    if completed is False:
        _append(errors, prefix, "this matrix has no construction fallback")
        return
    if not completed_present:
        stray = [field for field in construction_fields[1:] if field in record]
        if stray:
            _append(errors, prefix, "unobserved construction has outcome fields")
        if record.get("coverage") == 1:
            _append(errors, prefix, "solved heuristic run lacks construction outcome")
        if record.get("planner_exit_code") not in (10, 20, 21, 22, 23, 24):
            _append(
                errors,
                prefix,
                "non-resource heuristic outcome lacks completed construction",
            )
        heuristic_present = [field for field in fields if field in record]
        if heuristic_present and record.get("planner_exit_code") not in (22, 23, 24):
            _append(
                errors,
                prefix,
                "pre-search outcome contains heuristic statistics",
            )
        if heuristic_present and len(heuristic_present) not in (1, len(fields)):
            _append(errors, prefix, "resource-prefix heuristic fields are partial")
        if len(heuristic_present) == 1 and (
            heuristic_present != ["cofactor_width"]
            or label not in set(EXACT_LABELS.values()) | set(CAP_LABELS.values())
        ):
            _append(errors, prefix, "invalid width-only resource prefix")
        if not heuristic_present:
            return

    # A resource interruption may leave either the selected width alone or a
    # complete schema+heuristic prefix before the construction-complete event.
    if completed is not True:
        observed = {field for field in fields if field in record}
        if observed == {"cofactor_width"}:
            width = record.get("cofactor_width")
            if type(width) is not int or width < 1:
                _append(errors, prefix, "resource-prefix cofactor_width is invalid")
            return
        if observed == set(fields):
            values_valid = True
            for field in fields:
                value = record.get(field)
                if type(value) is not int or value < (
                    1 if field != "add_nodes" else 0
                ):
                    _append(errors, prefix, "{} is invalid".format(field))
                    values_valid = False
            if values_valid:
                w, u, v, t, a = (record[field] for field in fields)
                if (
                    u != a + t
                    or v > t
                    or w > u
                    or w < t
                    or a < t - 1
                    or (t == 1) != (a == 0)
                ):
                    _append(errors, prefix, "W/A/T/U/V identities do not hold")
            return

    seconds = _number(record.get("construction_time"))
    if seconds is None or seconds < 0:
        _append(errors, prefix, "construction_time is invalid")
    if record.get("heuristic_size_bound") != 100000:
        _append(errors, prefix, "PDB size bound changed")
    expected_kind = {
        CEGAR: "pdb_cegar",
        "pdb_selector_k8": "pdb_exact_width_filter",
        "pdb_selector_k32": "pdb_exact_width_filter",
        "pdb_cap_grid_k8": "pdb_exact_width_cap_filter",
        "pdb_cap_grid_k32": "pdb_exact_width_cap_filter",
    }[label]
    if record.get("heuristic_kind") != expected_kind:
        _append(errors, prefix, "heuristic_kind changed")
    for field in fields:
        value = record.get(field)
        if type(value) is not int or value < (1 if field != "add_nodes" else 0):
            _append(errors, prefix, "{} is invalid".format(field))
    w = record.get("cofactor_width")
    u = record.get("width_upper_bound")
    v = record.get("num_values")
    t = record.get("num_terminals")
    a = record.get("add_nodes")
    if all(type(value) is int for value in (w, u, v, t, a)):
        if (
            u != a + t
            or v > t
            or w > u
            or w < t
            or a < t - 1
            or (t == 1) != (a == 0)
        ):
            _append(errors, prefix, "W/A/T/U/V identities do not hold")


def _old_trace_record_error(item, kind, budget):
    return legacy._selector_record_error(item, kind, budget)


def _validate_old_trace(record, label, prefix, errors):
    initial_error_count = len(errors)
    for field in (
        cap_parser.RAW_POOL_SHA256_PROPERTY,
        "pdb_cap_selector_parser_protocol",
        "pdb_selected_value_cap",
    ):
        if field in record:
            _append(errors, prefix, "exact selector contains cap-only {}".format(field))
    budget = _selector_budget(label)
    candidates = record.get(common.PDB_SELECTOR_CANDIDATES_PROPERTY)
    selected = record.get(common.PDB_SELECTOR_SELECTED_PROPERTY)
    final = record.get(common.PDB_SELECTOR_FINAL_PROPERTY)
    complete = record.get(common.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY)
    certified = record.get(common.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY)
    resource = record.get("planner_exit_code") in (22, 23, 24)
    constructed = record.get("construction_completed") is True

    if candidates is None:
        if any(field in record for field in PDB_FINAL_FIELDS):
            _append(
                errors, prefix,
                "exact selector without candidates has projected final fields",
            )
        if any(field in record for field in SELECTOR_TRACE_FIELDS):
            _append(errors, prefix, "selector trace fields are only partially present")
        if constructed:
            _append(errors, prefix, "completed exact selector lacks a trace")
        return None
    if type(candidates) is not list or not 1 <= len(candidates) <= 5:
        _append(errors, prefix, "exact selector candidate count is invalid")
        return None
    valid = True
    for kind, item in [("candidate", item) for item in candidates]:
        error = _old_trace_record_error(item, kind, budget)
        if error:
            _append(errors, prefix, error)
            valid = False
    if not valid:
        return None
    provenance = [source for item in candidates for source in item["sources"]]
    source_owner = {}
    for item in candidates:
        for source in item["sources"]:
            if source in source_owner:
                _append(errors, prefix, "exact selector source occurs in multiple patterns")
            source_owner[source] = tuple(item["pattern"])
    first_positions = [
        common.PDB_SELECTOR_SOURCES.index(item["sources"][0])
        for item in candidates
    ]
    patterns = [canonical_json(item.get("pattern")) for item in candidates]
    if len(patterns) != len(set(patterns)) or len(provenance) != len(set(provenance)):
        _append(errors, prefix, "exact selector pool is not deduplicated")
        valid = False
    if first_positions != sorted(first_positions) or len(first_positions) != len(
        set(first_positions)
    ):
        _append(errors, prefix, "exact selector pool violates fixed first-source order")
        valid = False
    if candidates and "empty" not in candidates[0]["sources"]:
        _append(errors, prefix, "exact selector prefix does not start with empty")
    if source_owner:
        latest = max(first_positions)
        if any(
            common.PDB_SELECTOR_SOURCES[position] not in source_owner
            for position in range(latest)
        ):
            _append(errors, prefix, "exact selector prefix skips earlier sources")

    if complete is True or constructed:
        if complete is not True or certified is not True:
            _append(errors, prefix, "completed exact selector is not certified")
        if record.get(common.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY) is not None:
            _append(errors, prefix, "certified exact selector has diagnostics")
        if set(source_owner) != set(common.PDB_SELECTOR_SOURCES):
            _append(errors, prefix, "complete exact selector lacks the fixed pool")
        error = _old_trace_record_error(selected, "selected", budget)
        if error:
            _append(errors, prefix, error)
            return None
        feasible = [item for item in candidates if item.get("feasible") is True]
        if valid and feasible:
            winner = feasible[0]
            for item in feasible[1:]:
                if legacy._selector_candidate_is_better(item, winner):
                    winner = item
            if selected != winner:
                _append(errors, prefix, "exact selector winner is not recomputed winner")
        elif not feasible:
            _append(errors, prefix, "exact selector has no feasible candidate")
        expected_final_keys = {
            "pattern_size",
            "selected_source",
            "abstract_states",
            "cofactor_width_budget",
            "num_values",
            "cofactor_width",
            "width_upper_bound",
        }
        if type(final) is not dict or set(final) != expected_final_keys:
            _append(errors, prefix, "complete exact selector lacks final/selected")
        else:
            if (
                type(final["pattern_size"]) is not int
                or final["pattern_size"] < 0
                or type(final["selected_source"]) is not str
                or type(final["abstract_states"]) is not int
                or final["abstract_states"] < 1
                or final["cofactor_width_budget"] != budget
                or any(
                    type(final[field]) is not int or final[field] < 1
                    for field in (
                        "num_values",
                        "cofactor_width",
                        "width_upper_bound",
                    )
                )
            ):
                _append(errors, prefix, "exact selector final values are invalid")
                return None
            expected_terminals = final["num_values"] + int(
                selected.get("dead_count", 0) > 0
            )
            expected_final = {
                "pattern_size": len(selected["pattern"]),
                "selected_source": selected["sources"][0],
                "abstract_states": selected["abstract_states"],
                "cofactor_width_budget": budget,
                "num_values": final["num_values"],
                "cofactor_width": selected["cofactor_width"],
                "width_upper_bound": selected["width_upper_bound"],
            }
            if final != expected_final:
                _append(errors, prefix, "exact selector final disagrees with winner")
            final_cross = {
                "pdb_final_format": "exact_width_filter",
                "pdb_pattern_size": final["pattern_size"],
                "pdb_selected_source": final["selected_source"],
                "pdb_abstract_states": final["abstract_states"],
                "pdb_cofactor_width_budget": budget,
                "pdb_final_num_values": final["num_values"],
                "pdb_final_cofactor_width": final["cofactor_width"],
                "pdb_final_width_upper_bound": final["width_upper_bound"],
                "cofactor_width": selected["cofactor_width"],
            }
            for field, expected in final_cross.items():
                if not _same(record.get(field), expected):
                    _append(
                        errors,
                        prefix,
                        "{} disagrees with exact selector winner".format(field),
                    )
            if constructed or all(
                field in record
                for field in (
                    "width_upper_bound",
                    "num_values",
                    "num_terminals",
                    "add_nodes",
                )
            ):
                heuristic_cross = {
                    "width_upper_bound": selected["width_upper_bound"],
                    "num_values": final["num_values"],
                    "num_terminals": expected_terminals,
                    "add_nodes": selected["width_upper_bound"] - expected_terminals,
                }
                if constructed:
                    heuristic_cross["value_cap"] = -1
                for field, expected in heuristic_cross.items():
                    if not _same(record.get(field), expected):
                        _append(
                            errors,
                            prefix,
                            "{} disagrees with exact selector winner".format(field),
                        )
            if (
                type(final["num_values"]) is not int
                or final["num_values"] < 1
                or final["num_values"] > selected.get("finite_count", -1)
                or expected_terminals > selected["width_upper_bound"]
            ):
                _append(errors, prefix, "exact selector terminal/value census is invalid")
        expected_pool_hash = legacy.sha256_json(legacy._normalized_selector_pool(candidates))
        expected_trace_hash = legacy.sha256_json(
            {"candidates": candidates, "selected": selected, "final": final}
        )
        if record.get(common.PDB_SELECTOR_POOL_SHA256_PROPERTY) != expected_pool_hash:
            _append(errors, prefix, "exact selector pool hash changed")
        if record.get(common.PDB_SELECTOR_TRACE_SHA256_PROPERTY) != expected_trace_hash:
            _append(errors, prefix, "exact selector trace hash changed")
        return expected_pool_hash if len(errors) == initial_error_count else None

    if not resource:
        _append(errors, prefix, "incomplete exact selector is not a resource outcome")
    if complete is not False or certified is not False:
        _append(errors, prefix, "interrupted exact selector flags changed")
    if record.get(common.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY) != "selector trace is incomplete":
        _append(errors, prefix, "interrupted exact selector diagnostic changed")
    if final is not None:
        _append(errors, prefix, "interrupted exact selector has a final")
    unexpected_final = [field for field in PDB_FINAL_FIELDS if field in record]
    if unexpected_final:
        _append(errors, prefix, "interrupted exact selector has projected final fields")
    unexpected_heuristic = [
        field
        for field in (
            "cofactor_width",
            "width_upper_bound",
            "num_values",
            "num_terminals",
            "add_nodes",
        )
        if field in record
    ]
    if unexpected_heuristic:
        _append(errors, prefix, "interrupted exact selector has WBH heuristic fields")
    if record.get(common.PDB_SELECTOR_TRACE_SHA256_PROPERTY) is not None or record.get(common.PDB_SELECTOR_POOL_SHA256_PROPERTY) is not None:
        _append(errors, prefix, "interrupted exact selector has certified hashes")
    if selected is not None:
        error = _old_trace_record_error(selected, "selected", budget)
        if error:
            _append(errors, prefix, error)
            return None
        if set(source_owner) != set(common.PDB_SELECTOR_SOURCES):
            _append(errors, prefix, "selected interrupted exact trace lacks full pool")
        feasible = [item for item in candidates if item.get("feasible") is True]
        if feasible:
            winner = feasible[0]
            for item in feasible[1:]:
                if legacy._selector_candidate_is_better(item, winner):
                    winner = item
            if selected != winner:
                _append(
                    errors,
                    prefix,
                    "interrupted exact selected record is not recomputed winner",
                )
        else:
            _append(errors, prefix, "interrupted exact trace has no feasible candidate")
    return None


def _cap_pool_details(candidates, pool_must_be_complete, prefix, errors):
    valid = True
    for item in candidates:
        error = cap_parser._validate_record(
            item, "candidate", retained=True
        )
        if error:
            _append(errors, prefix, error)
            valid = False
    if not valid:
        return [], {}, []
    group_errors, representatives, source_owner = cap_parser._validate_groups(
        candidates, pool_must_be_complete
    )
    for error in group_errors:
        _append(errors, prefix, error)
    seen = set()
    first_source_positions = []
    groups = []
    for item in candidates:
        pattern = tuple(item["pattern"])
        if pattern not in seen:
            seen.add(pattern)
            first_source_positions.append(
                common.PDB_SELECTOR_SOURCES.index(item["sources"][0])
            )
            groups.append(item)
    if (
        first_source_positions != sorted(first_source_positions)
        or len(first_source_positions) != len(set(first_source_positions))
    ):
        _append(errors, prefix, "cap-grid groups violate fixed first-source order")
    if candidates and "empty" not in candidates[0]["sources"]:
        _append(errors, prefix, "cap-grid prefix does not start with empty")
    if first_source_positions:
        latest = max(first_source_positions)
        if any(
            common.PDB_SELECTOR_SOURCES[position] not in source_owner
            for position in range(latest)
        ):
            _append(errors, prefix, "cap-grid prefix skips an earlier fixed-pool source")
    if pool_must_be_complete and set(source_owner) != set(
        common.PDB_SELECTOR_SOURCES
    ):
        _append(errors, prefix, "complete cap-grid trace lacks fixed source pool")
    return representatives, source_owner, groups


def _normalize_fetched_cap_record(value, kind, prefix, errors):
    """Restore protocol order after Lab serializes JSON objects by key."""
    if type(value) is not dict:
        return value
    if set(value) != set(cap_parser.RECORD_KEYS):
        _append(errors, prefix, "{} cap-grid payload keys changed".format(kind))
        return value
    return {key: value[key] for key in cap_parser.RECORD_KEYS}


def _validate_cap_trace(record, label, prefix, errors):
    initial_error_count = len(errors)
    budget = _selector_budget(label)
    candidates = record.get(common.PDB_SELECTOR_CANDIDATES_PROPERTY)
    selected = record.get(common.PDB_SELECTOR_SELECTED_PROPERTY)
    final = record.get(common.PDB_SELECTOR_FINAL_PROPERTY)
    complete = record.get(common.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY)
    certified = record.get(common.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY)
    resource = record.get("planner_exit_code") in (22, 23, 24)
    constructed = record.get("construction_completed") is True

    if candidates is None:
        if any(field in record for field in PDB_FINAL_FIELDS):
            _append(
                errors, prefix,
                "cap-grid selector without candidates has projected final fields",
            )
        if any(field in record for field in SELECTOR_TRACE_FIELDS):
            _append(errors, prefix, "cap-grid trace fields are only partially present")
        if constructed:
            _append(errors, prefix, "completed cap-grid selector lacks a trace")
        return None
    if record.get("pdb_cap_selector_parser_protocol") != cap_parser.PARSER_PROTOCOL:
        _append(errors, prefix, "cap-grid dynamic parser protocol changed")
    if type(candidates) is not list or not candidates:
        _append(errors, prefix, "cap-grid candidate list is empty/malformed")
        return None
    candidates = [
        _normalize_fetched_cap_record(item, "candidate", prefix, errors)
        for item in candidates
    ]
    selected = _normalize_fetched_cap_record(
        selected, "selected", prefix, errors
    )
    pool_must_be_complete = selected is not None or final is not None or constructed
    representatives, source_owner, _ = _cap_pool_details(
        candidates, pool_must_be_complete, prefix, errors
    )
    if len(errors) != initial_error_count:
        return None
    if any(
        cap_parser._validate_record(
            item, "candidate", retained=True
        ) is not None
        for item in candidates
    ):
        return None
    budgets = {item.get("cofactor_width_budget") for item in candidates}
    if budgets != {budget}:
        _append(errors, prefix, "cap-grid candidate budget differs from config")
    if selected is not None:
        error = cap_parser._validate_record(
            selected, "selected", retained=True
        )
        if error:
            _append(errors, prefix, error)
            return None
        if selected["cofactor_width_budget"] != budget:
            _append(errors, prefix, "cap-grid selected budget differs from config")
        if set(source_owner) != set(common.PDB_SELECTOR_SOURCES):
            _append(errors, prefix, "selected cap-grid trace lacks fixed pool")
        if representatives:
            winner = min(representatives, key=common._selector_score_key)
            if selected != winner:
                _append(errors, prefix, "cap-grid winner is not independently recomputed")
        else:
            _append(errors, prefix, "cap-grid selector has no feasible transform")

    if complete is True or constructed:
        if complete is not True or certified is not True:
            _append(errors, prefix, "completed cap-grid selector is not certified")
        if record.get(common.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY) is not None:
            _append(errors, prefix, "certified cap-grid trace has diagnostics")
        expected_final_keys = {
            "pattern_size",
            "selected_source",
            "abstract_states",
            "cofactor_width_budget",
            "value_cap",
            "num_values",
            "cofactor_width",
            "width_upper_bound",
        }
        if type(selected) is not dict or type(final) is not dict or set(final) != expected_final_keys:
            _append(errors, prefix, "complete cap-grid trace lacks selected/final")
            return None
        else:
            expected_final = {
                "pattern_size": len(selected["pattern"]),
                "selected_source": selected["sources"][0],
                "abstract_states": selected["abstract_states"],
                "cofactor_width_budget": budget,
                "value_cap": selected["value_cap"],
                "num_values": selected["transformed_num_values"],
                "cofactor_width": selected["cofactor_width"],
                "width_upper_bound": selected["width_upper_bound"],
            }
            if final != expected_final:
                _append(errors, prefix, "cap-grid final disagrees with winner")
            final_cross = {
                "pdb_final_format": "exact_width_cap_filter",
                "pdb_pattern_size": final["pattern_size"],
                "pdb_selected_source": final["selected_source"],
                "pdb_abstract_states": final["abstract_states"],
                "pdb_cofactor_width_budget": budget,
                "pdb_selected_value_cap": final["value_cap"],
                "pdb_final_num_values": final["num_values"],
                "pdb_final_cofactor_width": final["cofactor_width"],
                "pdb_final_width_upper_bound": final["width_upper_bound"],
                "cofactor_width": selected["cofactor_width"],
            }
            for field, expected in final_cross.items():
                if not _same(record.get(field), expected):
                    _append(errors, prefix, "{} disagrees with cap-grid winner".format(field))
            if constructed or all(
                field in record
                for field in (
                    "width_upper_bound",
                    "num_values",
                    "num_terminals",
                    "add_nodes",
                )
            ):
                heuristic_cross = {
                    "width_upper_bound": selected["width_upper_bound"],
                    "num_values": selected["transformed_num_values"],
                    "num_terminals": selected["num_terminals"],
                    "add_nodes": selected["add_nodes"],
                }
                if constructed:
                    heuristic_cross["value_cap"] = selected["value_cap"]
                for field, expected in heuristic_cross.items():
                    if not _same(record.get(field), expected):
                        _append(errors, prefix, "{} disagrees with cap-grid winner".format(field))
        pool_hash = cap_parser._canonical_sha(
            [
                {
                    key: value
                    for key, value in item.items()
                    if key not in {"cofactor_width_budget", "feasible", "rejection_reason"}
                }
                for item in candidates
            ]
        )
        trace_hash = cap_parser._canonical_sha(
            {"candidates": candidates, "selected": selected, "final": final}
        )
        if record.get(common.PDB_SELECTOR_POOL_SHA256_PROPERTY) != pool_hash:
            _append(errors, prefix, "cap-grid pool hash changed")
        if record.get(common.PDB_SELECTOR_TRACE_SHA256_PROPERTY) != trace_hash:
            _append(errors, prefix, "cap-grid trace hash changed")
        raw_pool_hash = cap_parser._canonical_sha(
            cap_parser._raw_pool_core(candidates)
        )
        if record.get(cap_parser.RAW_POOL_SHA256_PROPERTY) != raw_pool_hash:
            _append(errors, prefix, "cap-grid raw-pool hash changed")
        return pool_hash if len(errors) == initial_error_count else None

    if not resource:
        _append(errors, prefix, "incomplete cap-grid trace is not a resource outcome")
    if complete is not False or certified is not False:
        _append(errors, prefix, "interrupted cap-grid flags changed")
    if record.get(common.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY) != "cap-grid selector trace is incomplete":
        _append(errors, prefix, "interrupted cap-grid diagnostic changed")
    if final is not None:
        _append(errors, prefix, "interrupted cap-grid trace has final")
    unexpected_final = [field for field in PDB_FINAL_FIELDS if field in record]
    if unexpected_final:
        _append(errors, prefix, "interrupted cap-grid trace has projected final fields")
    unexpected_heuristic = [
        field
        for field in (
            "cofactor_width",
            "width_upper_bound",
            "num_values",
            "num_terminals",
            "add_nodes",
        )
        if field in record
    ]
    if unexpected_heuristic:
        _append(errors, prefix, "interrupted cap-grid trace has WBH heuristic fields")
    if any(
        record.get(field) is not None
        for field in (
            common.PDB_SELECTOR_TRACE_SHA256_PROPERTY,
            common.PDB_SELECTOR_POOL_SHA256_PROPERTY,
            cap_parser.RAW_POOL_SHA256_PROPERTY,
        )
    ):
        _append(errors, prefix, "interrupted cap-grid trace has certified hashes")
    return None


def _validate_cegar_final(record, prefix, errors):
    legacy_fields = {
        "pdb_final_format",
        "pdb_pattern_size",
        "pdb_final_num_values",
        "pdb_final_cofactor_width",
        "pdb_final_width_upper_bound",
    }
    unexpected = [
        field
        for field in PDB_FINAL_FIELDS
        if field not in legacy_fields and field in record
    ]
    if unexpected:
        _append(errors, prefix, "legacy CEGAR contains selector-only final fields")
    has_final = any(
        field in record
        for field in legacy_fields
    )
    if record.get("construction_completed") is True:
        expected = {
            "pdb_final_format": "legacy",
            "pdb_final_num_values": record.get("num_values"),
            "pdb_final_cofactor_width": record.get("cofactor_width"),
            "pdb_final_width_upper_bound": record.get("width_upper_bound"),
        }
        for field, value in expected.items():
            if not _same(record.get(field), value):
                _append(errors, prefix, "legacy CEGAR final changed")
                break
        if type(record.get("pdb_pattern_size")) is not int or record["pdb_pattern_size"] < 0:
            _append(errors, prefix, "legacy CEGAR pattern size is invalid")
    elif has_final:
        _append(errors, prefix, "unconstructed CEGAR has a final")


def _raw_pool_identity(record, is_cap):
    candidates = record.get(common.PDB_SELECTOR_CANDIDATES_PROPERTY)
    if not isinstance(candidates, list):
        return None
    result = []
    if is_cap:
        seen = set()
        for item in candidates:
            pattern = tuple(item.get("pattern", []))
            if pattern in seen:
                continue
            seen.add(pattern)
            if item.get("raw_num_values") is None:
                result.append(
                    {
                        "sources": item.get("sources"),
                        "pattern": item.get("pattern"),
                        "abstract_states": item.get("abstract_states"),
                        "unmaterialized": True,
                    }
                )
                continue
            exact = next(
                candidate
                for candidate in candidates
                if candidate.get("pattern") == item.get("pattern")
                and candidate.get("value_cap") == -1
            )
            result.append(
                {
                    "sources": exact["sources"],
                    "pattern": exact["pattern"],
                    "abstract_states": exact["abstract_states"],
                    "initial_dead_end": exact["initial_dead_end"],
                    "initial_h": exact["initial_h"],
                    "finite_sum": exact["finite_sum"],
                    "finite_count": exact["finite_count"],
                    "dead_count": exact["dead_count"],
                    "cofactor_width": exact["raw_cofactor_width"],
                    "width_upper_bound": exact["raw_width_upper_bound"],
                }
            )
    else:
        for item in candidates:
            if item.get("cofactor_width") is None:
                result.append(
                    {
                        "sources": item.get("sources"),
                        "pattern": item.get("pattern"),
                        "abstract_states": item.get("abstract_states"),
                        "unmaterialized": True,
                    }
                )
            else:
                result.append(
                    {
                        key: item.get(key)
                        for key in (
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
                        )
                    }
                )
    return result


def validate_records(records, tasks, planner_revision, protocol_revision, binary_sha256, preprocess_sha256):
    matrix, structural_errors, structural_warnings = analyzer_utils.build_matrix(
        records, tasks, LABELS, allow_incomplete=False
    )
    errors = list(structural_errors) + list(structural_warnings)
    if len(records) != EXPECTED_CELLS:
        errors.append("properties contain {} records; expected 300".format(len(records)))
    if len(matrix) != EXPECTED_CELLS:
        errors.append("matrix contains {} cells; expected 300".format(len(matrix)))
    worktrees = {
        record.get("benchmark_worktree")
        for record in records
        if isinstance(record.get("benchmark_worktree"), str)
    }
    if len(worktrees) != 1 or not Path(next(iter(worktrees), "")).is_absolute():
        errors.append("records need one consistent absolute benchmark_worktree")
        worktree = "/invalid"
    else:
        worktree = next(iter(worktrees))
    expected_static = expected_protocol_metadata(
        planner_revision,
        protocol_revision,
        binary_sha256,
        preprocess_sha256,
        worktree,
    )
    costs = defaultdict(list)
    proofs = defaultdict(list)
    pool_hashes = defaultdict(dict)
    for label in LABELS:
        for task in tasks:
            record = matrix.get((label, task))
            if record is None:
                continue
            prefix = _prefix(label, task)
            _validate_static_record(record, label, task, expected_static, errors)
            legacy._validate_outcome(record, prefix, errors)
            legacy._validate_metrics(record, prefix, errors)
            planner_time = _number(record.get("planner_time"))
            if record.get("coverage") == 1 and (
                planner_time is None or planner_time <= 0
            ):
                _append(
                    errors,
                    prefix,
                    "solved planner_time must be finite and strictly positive",
                )
            _validate_heuristic_stats(record, label, prefix, errors)
            if label in EXACT_LABELS.values():
                pool_hash = _validate_old_trace(record, label, prefix, errors)
                if pool_hash:
                    pool_hashes[task][label] = pool_hash
                if record.get("construction_completed") is True and record.get("value_cap") != -1:
                    _append(errors, prefix, "exact selector construction must be uncapped")
            elif label in CAP_LABELS.values():
                pool_hash = _validate_cap_trace(record, label, prefix, errors)
                if pool_hash:
                    pool_hashes[task][label] = pool_hash
            elif label == CEGAR:
                _validate_cegar_final(record, prefix, errors)
                unexpected = [field for field in SELECTOR_TRACE_FIELDS if field in record]
                if unexpected:
                    _append(errors, prefix, "CEGAR contains selector trace fields")
                if record.get("construction_completed") is True and record.get("value_cap") != -1:
                    _append(errors, prefix, "CEGAR must be uncapped")
            else:
                if any(field in record for field in SELECTOR_TRACE_FIELDS):
                    _append(errors, prefix, "blind contains selector trace fields")
                if any(field in record for field in PDB_FINAL_FIELDS):
                    _append(errors, prefix, "blind contains PDB final fields")

            if record.get("coverage") == 1 and type(record.get("solution_cost")) is int:
                costs[task].append((label, record["solution_cost"]))
            if record.get("coverage") == 0 and record.get("unsolvable") == 1:
                proofs[task].append(label)

    for task in tasks:
        distinct = {cost for _, cost in costs.get(task, [])}
        if len(distinct) > 1:
            errors.append("solved-cost disagreement on {}:{}".format(*task))
        if distinct and proofs.get(task):
            errors.append("solved/proved-unsolvable disagreement on {}:{}".format(*task))
        for budget in (8, 32):
            exact = matrix.get((EXACT_LABELS[budget], task))
            capped = matrix.get((CAP_LABELS[budget], task))
            if exact is None or capped is None:
                continue
            exact_hash = pool_hashes.get(task, {}).get(EXACT_LABELS[budget])
            cap_hash = pool_hashes.get(task, {}).get(CAP_LABELS[budget])
            if exact_hash is not None and cap_hash is not None:
                exact_identity = _raw_pool_identity(exact, False)
                cap_identity = _raw_pool_identity(capped, True)
                if exact_identity != cap_identity:
                    errors.append(
                        "raw selector pool disagreement at K={} on {}:{}".format(
                            budget, *task
                        )
                    )
                if (
                    exact_hash
                    != capped.get(cap_parser.RAW_POOL_SHA256_PROPERTY)
                ):
                    errors.append(
                        "raw selector pool fingerprint disagreement at K={} on {}:{}".
                        format(budget, *task)
                    )
        exact_hashes = [
            pool_hashes.get(task, {}).get(EXACT_LABELS[budget]) for budget in (8, 32)
        ]
        cap_hashes = [
            pool_hashes.get(task, {}).get(CAP_LABELS[budget]) for budget in (8, 32)
        ]
        if all(exact_hashes) and len(set(exact_hashes)) != 1:
            errors.append("exact selector pool differs across K on {}:{}".format(*task))
        if all(cap_hashes) and len(set(cap_hashes)) != 1:
            errors.append("cap-grid selector pool differs across K on {}:{}".format(*task))
    return matrix, errors


def raise_validation_errors(errors):
    if not errors:
        return
    shown = errors[:60]
    tail = "" if len(errors) <= 60 else "\n... {} more".format(len(errors) - 60)
    raise AnalysisError(
        "cap-grid pilot validation failed ({} errors):\n{}{}".format(
            len(errors), "\n".join("- " + error for error in shown), tail
        )
    )


def _summary(values):
    values = list(values)
    if not values:
        return {
            "observed": 0,
            "minimum": None,
            "median": None,
            "maximum": None,
            "mean": None,
            "total": None,
        }
    return {
        "observed": len(values),
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
        "mean": statistics.fmean(values),
        "total": sum(values),
    }


def _fraction(numerator, denominator):
    fraction = Fraction(numerator, denominator)
    return {
        # The denominator is part of the frozen estimand (all 50 task pairs),
        # not merely a presentation of the reduced rational value.
        "numerator": numerator,
        "denominator": denominator,
        "value": float(fraction),
    }


def _ratio(candidate_total, reference_total):
    if reference_total == 0:
        return None
    return candidate_total / reference_total


def _certified_complete_trace(record):
    return (
        record.get(common.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY) is True
        and record.get(common.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY) is True
        and record.get(common.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY) is None
        and isinstance(record.get(common.PDB_SELECTOR_SELECTED_PROPERTY), dict)
    )


def _semantic_nontrivial(record):
    selected = record[common.PDB_SELECTOR_SELECTED_PROPERTY]
    return selected["finite_sum"] > 0 or selected["dead_count"] > 0


def _par2(record):
    if record.get("coverage") == 1:
        value = _number(record.get("planner_time"))
        if value is None:
            raise AnalysisError("solved record lacks planner time after validation")
        return value
    return PAR2_UNSOLVED_SECONDS


def _gm_ratio(candidate_values, reference_values):
    if not candidate_values:
        return None
    if any(value <= 0 for value in candidate_values + reference_values):
        return None
    return math.exp(
        statistics.fmean(
            math.log(candidate) - math.log(reference)
            for candidate, reference in zip(candidate_values, reference_values)
        )
    )


def _selected_summary(records):
    selected_pairs = [
        (record, record[common.PDB_SELECTOR_SELECTED_PROPERTY])
        for record in records
        if _certified_complete_trace(record)
    ]
    selected = [item for _, item in selected_pairs]
    return {
        "eligible_cells": len(records),
        "certified_complete_traces": len(selected),
        "semantic_nontrivial": sum(
            item["finite_sum"] > 0 or item["dead_count"] > 0 for item in selected
        ),
        "effective_cap": _summary(item.get("value_cap", -1) for item in selected),
        "pattern_size": _summary(len(item["pattern"]) for item in selected),
        "W": _summary(item["cofactor_width"] for item in selected),
        "U": _summary(item["width_upper_bound"] for item in selected),
        "A": _summary(
            item.get("add_nodes", record.get("add_nodes"))
            for record, item in selected_pairs
            if type(item.get("add_nodes", record.get("add_nodes"))) is int
        ),
        "T": _summary(
            item.get("num_terminals", record.get("num_terminals"))
            for record, item in selected_pairs
            if type(item.get("num_terminals", record.get("num_terminals")))
            is int
        ),
        "V": _summary(
            item.get("transformed_num_values", record.get("num_values"))
            for record, item in selected_pairs
            if type(
                item.get("transformed_num_values", record.get("num_values"))
            )
            is int
        ),
        "selected_sources": {
            source: sum(item["sources"][0] == source for item in selected)
            for source in common.PDB_SELECTOR_SOURCES
        },
    }


def _config_summary(label, records):
    solved = [record for record in records if record.get("coverage") == 1]
    constructed = [
        record for record in records if record.get("construction_completed") is True
    ]
    result = {
        "label": label,
        "cells": len(records),
        "solved": len(solved),
        "micro_par2_seconds": statistics.fmean(_par2(record) for record in records),
        "solved_planner_cpu_seconds": _summary(record["planner_time"] for record in solved),
        "construction_seconds": _summary(record["construction_time"] for record in constructed),
        "raw_complete_certified_cells": sum(
            legacy.certified_image_cell(record) for record in records
        ),
    }
    if label in EXACT_LABELS.values() or label in CAP_LABELS.values():
        result["selection"] = _selected_summary(records)
    else:
        result["selection"] = None
    return result


def _paired_ratio(matrix, tasks, candidate, reference, field, predicate):
    pairs = [
        (matrix[(candidate, task)], matrix[(reference, task)])
        for task in tasks
        if predicate(matrix[(candidate, task)]) and predicate(matrix[(reference, task)])
    ]
    candidate_total = sum(pair[0][field] for pair in pairs)
    reference_total = sum(pair[1][field] for pair in pairs)
    return {
        "paired_cells": len(pairs),
        "candidate_total": candidate_total,
        "reference_total": reference_total,
        "candidate_over_reference": _ratio(candidate_total, reference_total),
    }


def _comparison(matrix, tasks, budget):
    candidate = CAP_LABELS[budget]
    reference = EXACT_LABELS[budget]
    pairs = [(matrix[(candidate, task)], matrix[(reference, task)]) for task in tasks]
    wins = sum(left["coverage"] == 1 and right["coverage"] == 0 for left, right in pairs)
    losses = sum(left["coverage"] == 0 and right["coverage"] == 1 for left, right in pairs)
    both_solved = [(left, right) for left, right in pairs if left["coverage"] == right["coverage"] == 1]
    trace_pairs = [
        (left, right)
        for left, right in pairs
        if _certified_complete_trace(left) and _certified_complete_trace(right)
    ]
    raw_pool_pairs = [
        (left, right)
        for left, right in trace_pairs
        if left.get(cap_parser.RAW_POOL_SHA256_PROPERTY)
        == right.get(common.PDB_SELECTOR_POOL_SHA256_PROPERTY)
    ]
    cap_nontrivial = sum(_semantic_nontrivial(left) for left, _ in trace_pairs)
    exact_nontrivial = sum(_semantic_nontrivial(right) for _, right in trace_pairs)
    mechanism_estimable = len(trace_pairs) == EXPECTED_TASKS
    raw_pool_certified = len(raw_pool_pairs) == EXPECTED_TASKS
    complete_metric = legacy.certified_image_cell
    construction_predicate = lambda record: (
        record.get("construction_completed") is True
        and _number(record.get("construction_time")) is not None
    )
    return {
        "candidate": candidate,
        "reference": reference,
        "task_pairs": len(pairs),
        "coverage": {
            "wins": wins,
            "losses": losses,
            "both_solved": len(both_solved),
            "both_unsolved": EXPECTED_TASKS - wins - losses - len(both_solved),
            "candidate_minus_reference": _fraction(wins - losses, EXPECTED_TASKS),
        },
        "semantic_nontrivial_selection": {
            "status": (
                "estimable"
                if mechanism_estimable and raw_pool_certified
                else "not-estimable"
            ),
            "paired_certified_traces": len(trace_pairs),
            "candidate_nontrivial": cap_nontrivial,
            "reference_nontrivial": exact_nontrivial,
            "candidate_minus_reference": (
                _fraction(cap_nontrivial - exact_nontrivial, EXPECTED_TASKS)
                if mechanism_estimable and raw_pool_certified
                else None
            ),
        },
        "raw_pool_isolation": {
            "matching_complete_cross_protocol_fingerprints": len(raw_pool_pairs),
            "required": EXPECTED_TASKS,
            "status": (
                "certified"
                if raw_pool_certified
                else "not-certified-no-cap-attribution-or-promotion"
            ),
        },
        "micro_par2_seconds": {
            "candidate": statistics.fmean(_par2(left) for left, _ in pairs),
            "reference": statistics.fmean(_par2(right) for _, right in pairs),
            "candidate_minus_reference": statistics.fmean(
                _par2(left) - _par2(right) for left, right in pairs
            ),
        },
        "jointly_solved_planner_cpu": {
            "pairs": len(both_solved),
            "candidate_over_reference_geometric_mean": _gm_ratio(
                [left["planner_time"] for left, _ in both_solved],
                [right["planner_time"] for _, right in both_solved],
            ),
        },
        "paired_complete_image_time": _paired_ratio(
            matrix, tasks, candidate, reference, "image_time", complete_metric
        ),
        "paired_complete_expanded_bdd_nodes": _paired_ratio(
            matrix, tasks, candidate, reference, "expanded_bdd_nodes", complete_metric
        ),
        "paired_observed_construction_time": _paired_ratio(
            matrix,
            tasks,
            candidate,
            reference,
            "construction_time",
            construction_predicate,
        ),
    }


def make_analysis(records, matrix, tasks, properties_sha256, pins):
    protocol_revision, planner_revision, binary_sha256, preprocess_sha256 = pins
    by_label = {
        label: [matrix[(label, task)] for task in tasks] for label in LABELS
    }
    result = {
        "schema": ANALYSIS_SCHEMA,
        "analysis_protocol": ANALYSIS_PROTOCOL,
        "decision_policy": {
            "role": DECISION_ROLE,
            "population": "same-development-selected-50-task-P4-manifest",
            "reranking": False,
            "primary_width_budget": 8,
            "sensitivity_width_budget": 32,
            "sensitivity_may_replace_primary": False,
            "confidence_intervals": None,
            "p_values": None,
            "population_inference": None,
        },
        "execution": {
            "protocol": EXPECTED_PROTOCOL,
            "protocol_revision": protocol_revision,
            "planner_revision": planner_revision,
            "planner_binary_sha256": binary_sha256,
            "planner_preprocess_sha256": preprocess_sha256,
            "task_manifest_sha256": runner.MANIFEST_DIGEST,
            "task_sources_sha256": runner.EXPECTED_TASK_SOURCES_SHA256,
            "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "option_matrix_sha256": runner.OPTION_MATRIX_SHA256,
            "properties_canonical_sha256": properties_sha256,
            "analysis_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "task_count": EXPECTED_TASKS,
            "domain_count": EXPECTED_DOMAINS,
            "config_count": EXPECTED_CONFIGS,
            "cell_count": EXPECTED_CELLS,
        },
        "configs": [_config_summary(label, by_label[label]) for label in LABELS],
        "primary": _comparison(matrix, tasks, 8),
        "fixed_sensitivity": _comparison(matrix, tasks, 32),
    }
    return json.loads(canonical_json(result))


def analyze_with_pins(records, tasks, pins, properties_sha256):
    protocol_revision, planner_revision, binary_sha256, preprocess_sha256 = pins
    matrix, errors = validate_records(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        preprocess_sha256,
    )
    raise_validation_errors(errors)
    return make_analysis(records, matrix, tasks, properties_sha256, pins)


def _synthetic_cap_record(sources, pattern, states, cap, width, upper, raw_width, raw_upper, raw_values, raw_max, values, initial_h, finite_sum, finite_count, dead_count, budget):
    terminals = values + int(dead_count > 0)
    raw_terminals = raw_values + int(dead_count > 0)
    if list(sources) == ["empty"]:
        raw_initial_h, raw_finite_sum = 0, 0
        raw_value_counts = [[0, 1]]
    elif "cegar" in sources:
        raw_initial_h, raw_finite_sum = 3, 15
        raw_value_counts = [[0, 2], [1, 1], [2, 1], [3, 4]]
    else:
        raw_initial_h, raw_finite_sum = 0, 3
        raw_value_counts = [[0, 2], [1, 1], [2, 1]]
    raw_histogram_wire = cap_parser.encode_raw_value_histogram(raw_value_counts)
    _, raw_histogram_digest = cap_parser.decode_raw_value_histogram(
        raw_histogram_wire
    )
    return {
        "protocol": cap_parser.PROTOCOL,
        "score_version": cap_parser.SCORE_VERSION,
        "sources": list(sources),
        "pattern": list(pattern),
        "abstract_states": states,
        "initial_dead_end": False,
        "initial_h": initial_h,
        "finite_sum": finite_sum,
        "finite_count": finite_count,
        "dead_count": dead_count,
        "cofactor_width": width,
        "width_upper_bound": upper,
        "cofactor_width_budget": budget,
        "value_cap": cap,
        "add_nodes": upper - terminals,
        "num_terminals": terminals,
        "raw_add_nodes": raw_upper - raw_terminals,
        "raw_num_terminals": raw_terminals,
        "raw_cofactor_width": raw_width,
        "raw_width_upper_bound": raw_upper,
        "raw_num_values": raw_values,
        "raw_max_finite_value": raw_max,
        "raw_finite_sum": raw_finite_sum,
        "raw_finite_count": finite_count,
        "raw_dead_count": dead_count,
        "raw_initial_dead_end": False,
        "raw_initial_h": raw_initial_h,
        "raw_initial_value_count": dict(raw_value_counts)[raw_initial_h],
        "raw_value_histogram": raw_histogram_digest,
        "transformed_num_values": values,
        "feasible": width <= budget,
        "rejection_reason": None if width <= budget else "cofactor_width_budget",
    }


def _synthetic_exact_candidate(
    sources,
    pattern,
    states,
    initial_h,
    finite_sum,
    finite_count,
    dead_count,
    width,
    upper,
    budget,
):
    feasible = width <= budget
    return {
        "protocol": common.PDB_SELECTOR_POOL_PROTOCOL,
        "score_version": common.PDB_SELECTOR_SCORE_VERSION,
        "sources": list(sources),
        "pattern": list(pattern),
        "abstract_states": states,
        "initial_dead_end": False,
        "initial_h": initial_h,
        "finite_sum": finite_sum,
        "finite_count": finite_count,
        "dead_count": dead_count,
        "cofactor_width": width,
        "width_upper_bound": upper,
        "cofactor_width_budget": budget,
        "feasible": feasible,
        "rejection_reason": None if feasible else "cofactor_width_budget",
    }


def _attach_synthetic_exact_trace(record, budget):
    candidates = [
        _synthetic_exact_candidate(
            ["empty"], [], 1, 0, 0, 1, 0, 1, 1, budget
        ),
        _synthetic_exact_candidate(
            ["bdd_prefix", "goal_prefix", "goal_fill"],
            [0], 4, 0, 3, 4, 0, 9, 15, budget,
        ),
        _synthetic_exact_candidate(
            ["cegar"], [1], 10, 3, 15, 8, 2, 16, 30, budget
        ),
    ]
    feasible = [item for item in candidates if item["feasible"]]
    selected = copy.deepcopy(min(feasible, key=common._selector_score_key))
    if selected["sources"] == ["empty"]:
        num_values, num_terminals = 1, 1
    elif selected["sources"] == ["cegar"]:
        num_values, num_terminals = 4, 5
    else:
        num_values, num_terminals = 3, 3
    add_nodes = selected["width_upper_bound"] - num_terminals
    final = {
        "pattern_size": len(selected["pattern"]),
        "selected_source": selected["sources"][0],
        "abstract_states": selected["abstract_states"],
        "cofactor_width_budget": budget,
        "num_values": num_values,
        "cofactor_width": selected["cofactor_width"],
        "width_upper_bound": selected["width_upper_bound"],
    }
    record.update(
        {
            "heuristic_kind": "pdb_exact_width_filter",
            "value_cap": -1,
            "cofactor_width": selected["cofactor_width"],
            "width_upper_bound": selected["width_upper_bound"],
            "num_values": num_values,
            "num_terminals": num_terminals,
            "add_nodes": add_nodes,
            "pdb_final_format": "exact_width_filter",
            "pdb_pattern_size": final["pattern_size"],
            "pdb_selected_source": final["selected_source"],
            "pdb_abstract_states": final["abstract_states"],
            "pdb_cofactor_width_budget": budget,
            "pdb_final_num_values": final["num_values"],
            "pdb_final_cofactor_width": final["cofactor_width"],
            "pdb_final_width_upper_bound": final["width_upper_bound"],
            common.PDB_SELECTOR_CANDIDATES_PROPERTY: candidates,
            common.PDB_SELECTOR_SELECTED_PROPERTY: selected,
            common.PDB_SELECTOR_FINAL_PROPERTY: final,
            common.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY: True,
            common.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY: True,
            common.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY: None,
        }
    )
    record[common.PDB_SELECTOR_POOL_SHA256_PROPERTY] = legacy.sha256_json(
        legacy._normalized_selector_pool(candidates)
    )
    record[common.PDB_SELECTOR_TRACE_SHA256_PROPERTY] = legacy.sha256_json(
        {"candidates": candidates, "selected": selected, "final": final}
    )


def _attach_synthetic_cap_trace(record, budget):
    candidates = [
        _synthetic_cap_record(["empty"], [], 1, -1, 1, 1, 1, 1, 1, 0, 1, 0, 0, 1, 0, budget),
        _synthetic_cap_record(["bdd_prefix", "goal_prefix", "goal_fill"], [0], 4, 0, 1, 1, 9, 15, 3, 2, 1, 0, 0, 4, 0, budget),
        _synthetic_cap_record(["bdd_prefix", "goal_prefix", "goal_fill"], [0], 4, 1, 4, 7, 9, 15, 3, 2, 2, 0, 2, 4, 0, budget),
        _synthetic_cap_record(["bdd_prefix", "goal_prefix", "goal_fill"], [0], 4, -1, 9, 15, 9, 15, 3, 2, 3, 0, 3, 4, 0, budget),
        _synthetic_cap_record(["cegar"], [1], 10, 0, 4, 9, 16, 30, 4, 3, 1, 0, 0, 8, 2, budget),
        _synthetic_cap_record(["cegar"], [1], 10, 1, 5, 12, 16, 30, 4, 3, 2, 1, 6, 8, 2, budget),
        _synthetic_cap_record(["cegar"], [1], 10, 2, 9, 19, 16, 30, 4, 3, 3, 2, 11, 8, 2, budget),
        _synthetic_cap_record(["cegar"], [1], 10, -1, 16, 30, 16, 30, 4, 3, 4, 3, 15, 8, 2, budget),
    ]
    group_errors, representatives, _ = cap_parser._validate_groups(candidates, True)
    if group_errors:
        raise AssertionError(group_errors)
    selected = copy.deepcopy(min(representatives, key=common._selector_score_key))
    final = {
        "pattern_size": len(selected["pattern"]),
        "selected_source": selected["sources"][0],
        "abstract_states": selected["abstract_states"],
        "cofactor_width_budget": budget,
        "value_cap": selected["value_cap"],
        "num_values": selected["transformed_num_values"],
        "cofactor_width": selected["cofactor_width"],
        "width_upper_bound": selected["width_upper_bound"],
    }
    record.update(
        {
            "heuristic_kind": "pdb_exact_width_cap_filter",
            "value_cap": selected["value_cap"],
            "cofactor_width": selected["cofactor_width"],
            "width_upper_bound": selected["width_upper_bound"],
            "num_values": selected["transformed_num_values"],
            "num_terminals": selected["num_terminals"],
            "add_nodes": selected["add_nodes"],
            "pdb_final_format": "exact_width_cap_filter",
            "pdb_pattern_size": final["pattern_size"],
            "pdb_selected_source": final["selected_source"],
            "pdb_abstract_states": final["abstract_states"],
            "pdb_cofactor_width_budget": budget,
            "pdb_selected_value_cap": final["value_cap"],
            "pdb_final_num_values": final["num_values"],
            "pdb_final_cofactor_width": final["cofactor_width"],
            "pdb_final_width_upper_bound": final["width_upper_bound"],
            common.PDB_SELECTOR_CANDIDATES_PROPERTY: candidates,
            common.PDB_SELECTOR_SELECTED_PROPERTY: selected,
            common.PDB_SELECTOR_FINAL_PROPERTY: final,
            common.PDB_SELECTOR_TRACE_COMPLETE_PROPERTY: True,
            common.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY: True,
            common.PDB_SELECTOR_VALIDATION_ERROR_PROPERTY: None,
            "pdb_cap_selector_parser_protocol": cap_parser.PARSER_PROTOCOL,
        }
    )
    normalized = [
        {
            key: value
            for key, value in item.items()
            if key not in {"cofactor_width_budget", "feasible", "rejection_reason"}
        }
        for item in candidates
    ]
    record[common.PDB_SELECTOR_POOL_SHA256_PROPERTY] = cap_parser._canonical_sha(normalized)
    record[common.PDB_SELECTOR_TRACE_SHA256_PROPERTY] = cap_parser._canonical_sha(
        {"candidates": candidates, "selected": selected, "final": final}
    )
    record[cap_parser.RAW_POOL_SHA256_PROPERTY] = cap_parser._canonical_sha(
        cap_parser._raw_pool_core(candidates)
    )


def synthetic_records(tasks, pins):
    protocol_revision, planner_revision, binary_sha256, preprocess_sha256 = pins
    worktree = "/synthetic/downward-benchmarks"
    new_static = expected_protocol_metadata(
        planner_revision, protocol_revision, binary_sha256, preprocess_sha256, worktree
    )
    old_static_keys = set(
        legacy.expected_protocol_metadata(planner_revision, protocol_revision, binary_sha256)
    )
    records = []
    for task_index, task in enumerate(tasks):
        cost = 10 + task_index
        for label, search in CONFIGS:
            if label == "pdb_selector_k8":
                solved = task_index % 10 != 0
            elif label == "pdb_cap_grid_k8":
                solved = task_index % 13 != 0
            elif label == "pdb_selector_k32":
                solved = task_index % 11 != 0
            elif label == "pdb_cap_grid_k32":
                solved = task_index % 12 != 0
            elif label == CEGAR:
                solved = task_index % 9 != 0
            else:
                solved = task_index % 8 != 0
            base_label = (
                EXACT_LABELS[_selector_budget(label)]
                if label in CAP_LABELS.values()
                else label
            )
            record = legacy.synthetic_record(
                base_label,
                legacy.SEARCHES[base_label],
                task,
                planner_revision,
                protocol_revision,
                binary_sha256,
                1.0 + task_index / 100.0 if solved else None,
                cost,
            )
            for field in old_static_keys:
                record.pop(field, None)
            record.update(copy.deepcopy(new_static))
            record.update(
                {
                    "_source_key": "synthetic-{}-{}-{}".format(label, *task),
                    "id": [label, task[0], task[1]],
                    "algorithm": label,
                    "component_options": legacy.expected_component_options(search),
                }
            )
            # The historical synthetic fixture predates the exact terminal
            # level invariant and used W=4,T=5 for its CEGAR ADD.  Real ADD
            # statistics necessarily have W>=T; keep the prospective fixture
            # itself producer-realizable.
            if label == CEGAR and record.get("construction_completed") is True:
                record["cofactor_width"] = record["num_terminals"]
                record["pdb_final_cofactor_width"] = record["num_terminals"]
            if label in CAP_LABELS.values():
                _attach_synthetic_cap_trace(record, _selector_budget(label))
            elif label in EXACT_LABELS.values():
                _attach_synthetic_exact_trace(record, _selector_budget(label))
            records.append(record)
    return records


def _test_pins():
    return (
        "0123456789abcdef0123456789abcdef01234567",
        "123456789abcdef0123456789abcdef012345678",
        "23456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef0",
        "3456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef01",
    )


def self_test():
    validate_runner_contract(check_reviewed_pins=False)
    tasks = load_tasks()
    pins = _test_pins()
    records = synthetic_records(tasks, pins)
    digest = legacy.logical_properties_sha256(records)
    result = analyze_with_pins(records, tasks, pins, digest)
    if result["execution"]["cell_count"] != 300:
        raise AssertionError("synthetic cell count changed")
    if result["primary"]["candidate"] != "pdb_cap_grid_k8":
        raise AssertionError("primary contrast changed")
    if result["fixed_sensitivity"]["candidate"] != "pdb_cap_grid_k32":
        raise AssertionError("fixed sensitivity changed")
    if canonical_json(result) != canonical_json(
        analyze_with_pins(copy.deepcopy(records), tasks, pins, digest)
    ):
        raise AssertionError("analysis is nondeterministic")
    bad = copy.deepcopy(records)
    target = next(item for item in bad if item["algorithm"] == "pdb_cap_grid_k8")
    target[common.PDB_SELECTOR_SELECTED_PROPERTY]["value_cap"] = 0
    _, errors = validate_records(bad, tasks, pins[1], pins[0], pins[2], pins[3])
    if not errors:
        raise AssertionError("weaker-cap mutation was not rejected")
    bad = copy.deepcopy(records[:-1])
    _, errors = validate_records(bad, tasks, pins[1], pins[0], pins[2], pins[3])
    if not errors:
        raise AssertionError("missing cell was not rejected")
    print("PDB cap-grid analyzer self-test: PASS (300 synthetic cells)")
    print("synthetic properties SHA-256: {}".format(digest))
    print("synthetic analysis SHA-256: {}".format(sha256_json(result)))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--properties", help="exact Lab properties JSON/file/directory")
    parser.add_argument("--emit-json", action="store_true", help="emit canonical analysis JSON")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    # The pin gate intentionally precedes properties loading: an ordinary run
    # cannot inspect outcomes while any prospective identity remains unset.
    require_reviewed_pins(EXPECTED_PROPERTIES_CANONICAL_SHA256)
    # Validate and hash the actual task/source manifests before opening any
    # outcome-bearing properties input.
    tasks = load_tasks()
    if not args.properties:
        raise AnalysisError("--properties is required")
    try:
        records = safe_loader.load_properties(args.properties)
    except safe_loader.AnalysisError as err:
        raise AnalysisError(str(err)) from err
    digest = legacy.logical_properties_sha256(records)
    require_reviewed_pins(digest)
    pins = (
        EXPECTED_PROTOCOL_REVISION,
        EXPECTED_PLANNER_REVISION,
        EXPECTED_CACHE_BINARY_SHA256,
        EXPECTED_CACHE_PREPROCESS_SHA256,
    )
    result = analyze_with_pins(records, tasks, pins, digest)
    if args.emit_json:
        print(canonical_json(result))
    else:
        print("PDB cap-grid development analysis: PASS")
        print("canonical analysis SHA-256: {}".format(sha256_json(result)))
        print(canonical_json(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AnalysisError as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
