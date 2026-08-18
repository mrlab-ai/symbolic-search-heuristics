#!/usr/bin/env python3
"""Prospective focused full evaluation of the promoted cap-aware selector.

The matrix is exactly 1,377 tasks by five configurations.  The K=8
development promotion gate is recomputed from a digest-pinned complete screen
before start; K=32 is never eligible to substitute.  Build and start are
separate, and this initial protocol commit is intentionally launch-blocked by
unset protocol-revision, screen-properties, and prospective-job pins.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import re
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import exp_arrhenius_common as C
import exp_arrhenius_selector_full as Full
import exp_arrhenius_selector_validation as V
import exp_pdb_cap_grid_pilot as ScreenRunner
import pdb_cap_grid_full_protocol as P
import pdb_cap_selector_parser as CapParser
import suite_cost_manifest


ProtocolError = P.ProtocolError
EXPERIMENT_DATA_PATH = SCRIPT_DIR / "data" / Path(__file__).stem
EXPECTED_JOB_PIN = P.EXPECTED_PROSPECTIVE_JOB_SHA256

PROTOCOL_FILES = tuple(
    dict.fromkeys(
        (
            Path(__file__).resolve(),
            SCRIPT_DIR / "pdb_cap_grid_full_protocol.py",
            SCRIPT_DIR / "analyze_pdb_cap_grid_full.py",
            Path(Full.__file__).resolve(),
            Path(V.__file__).resolve(),
            Path(ScreenRunner.__file__).resolve(),
            Path(ScreenRunner.__file__).with_name(
                "analyze_pdb_cap_grid_pilot.py"
            ).resolve(),
            Path(C.__file__).resolve(),
            Path(CapParser.__file__).resolve(),
            Path(C.__file__).with_name("wbh_parser.py").resolve(),
            Path(suite_cost_manifest.__file__).resolve(),
            SCRIPT_DIR / "suite_wbh_operator_costs.json",
            SCRIPT_DIR / "suite_wbh_operator_costs.json.sha256",
            SCRIPT_DIR / "selector_pilot_suite.txt",
            SCRIPT_DIR / "requirements.txt",
        )
    )
)

PIN_MUTABLE_PROTOCOL_PATH = "experiments/pdb_cap_grid_full_protocol.py"
PIN_ASSIGNMENTS = (
    "PROTOCOL_IMPLEMENTATION_REVISION",
    "EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256",
    "EXPECTED_PROSPECTIVE_JOB_SHA256",
)
def _expected_limited_run_script(argv):
    return ScreenRunner.Base._expected_run_script(
        argv,
        soft_stdout_limit=P.PLANNER_SOFT_STDOUT_LIMIT_KIB,
        hard_stdout_limit=P.PLANNER_HARD_STDOUT_LIMIT_KIB,
    )


def _absolute_run_loop_blocks(experiment_name):
    """Seal Lab 8.0's absolute experiment-path run-loop template."""
    if experiment_name != EXPERIMENT_DATA_PATH.name:
        raise ProtocolError("focused full experiment name changed in run loop")
    legacy = '''# Execute runs in shuffled order.
for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID); do
    run_dir=$(print_run_dir ${run_id})
    (cd "__EXPERIMENT__/$run_dir" && execute_run ${run_id})
done
'''.replace("__EXPERIMENT__", str(EXPERIMENT_DATA_PATH))
    full = '''# Execute runs in deterministic order and retain every wrapper failure.
ARRAY_RETCODE=0
for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID); do
    run_dir=$(print_run_dir ${run_id})
    (cd "__EXPERIMENT__/$run_dir" && execute_run ${run_id}) || ARRAY_RETCODE=1
done
exit "$ARRAY_RETCODE"
'''.replace("__EXPERIMENT__", str(EXPERIMENT_DATA_PATH))
    return legacy, full


def validate_fixed_environment():
    actual = {
        "time_limit": C.TIME_LIMIT,
        "memory_limit": C.MEMORY_LIMIT,
        "build_options": C.BUILD_OPTIONS,
        "cache_build_name": C.CACHE_BUILD_NAME,
        "scheduler_cluster": C.SCHEDULER_CLUSTER,
        "scheduler_cpu_model": C.SCHEDULER_CPU_MODEL,
        "scheduler_partition": C.SCHEDULER_PARTITION,
        "scheduler_qos": C.SCHEDULER_QOS,
        "scheduler_account": C.SCHEDULER_ACCOUNT,
        "scheduler_time_limits": {P.EXPECTED_CELLS: P.SCHEDULER_TIME_LIMIT},
        "scheduler_memory_per_cpu": C.SCHEDULER_MEMORY_PER_CPU,
        "scheduler_cpus_per_task": C.SCHEDULER_CPUS_PER_TASK,
        "array_task_throttle": C.ARRAY_TASK_THROTTLE,
        "max_array_tasks": C.MAX_ARRAY_TASKS,
        "wrapper_allowance_seconds_per_run": (
            C.SCHEDULER_WRAPPER_ALLOWANCE_SECONDS
        ),
    }
    expected = {
        "time_limit": "300s",
        "memory_limit": "8G",
        "build_options": ["release_no_lp"],
        "cache_build_name": "release_no_lp",
        "scheduler_cluster": "arrhenius",
        "scheduler_cpu_model": "AMD EPYC 9755 128-Core Processor",
        "scheduler_partition": "cpu",
        "scheduler_qos": "normal",
        "scheduler_account": "naiss2025-5-561-cpu",
        "scheduler_time_limits": {P.EXPECTED_CELLS: "00:45:00"},
        "scheduler_memory_per_cpu": "9G",
        "scheduler_cpus_per_task": 1,
        "array_task_throttle": 5,
        "max_array_tasks": 1000,
        "wrapper_allowance_seconds_per_run": 60,
    }
    if actual != expected:
        raise ProtocolError(
            "focused full environment differs from frozen contract: {}".format(
                actual
            )
        )


def configure_completion_base():
    """Bind P6's audited completion/recovery machinery to this one matrix."""
    Full.__file__ = str(Path(__file__).resolve())
    Full.EXPERIMENT_DATA_PATH = EXPERIMENT_DATA_PATH
    Full.P6_FULL_PLANNER_REVISION = P.PLANNER_REVISION
    Full.P6_FULL_CACHE_BINARY_SHA256 = P.CACHE_BINARY_SHA256
    Full.P6_FULL_CACHE_PREPROCESS_SHA256 = P.CACHE_PREPROCESS_SHA256
    Full.P6_FULL_CACHE_NAME_SUFFIX = P.CACHE_NAME_SUFFIX
    Full.PLANNER_REVISION = P.PLANNER_REVISION
    Full.CACHE_BINARY_SHA256 = P.CACHE_BINARY_SHA256
    Full.CACHE_PREPROCESS_SHA256 = P.CACHE_PREPROCESS_SHA256
    Full.EXPECTED_UNBATCHED_RUNS = P.EXPECTED_CELLS
    Full.EXPECTED_BATCHED_RUNS = P.EXPECTED_CELLS
    Full.EXPECTED_WRAPPER_ALLOWANCE_SECONDS_PER_RUN = (
        P.WRAPPER_ALLOWANCE_SECONDS_PER_RUN
    )
    Full.FULL_SCHEDULER_TIME_LIMITS = {
        P.EXPECTED_CELLS: P.SCHEDULER_TIME_LIMIT
    }
    Full.FULL_SCHEDULER_TIME_LIMIT_SECONDS = {
        P.EXPECTED_CELLS: P.SCHEDULER_TIME_LIMIT_SECONDS
    }
    Full.EXPECTED_ARRAY_ASSIGNMENT_SHA256 = {
        P.EXPECTED_CELLS: P.EXPECTED_ARRAY_ASSIGNMENT_SHA256
    }
    Full.EXPECTED_FINAL_LOGICAL_GROUP_SLURM_ID = {
        P.EXPECTED_CELLS: P.EXPECTED_FINAL_LOGICAL_GROUP_SLURM_ID
    }
    Full.EXPECTED_PROSPECTIVE_JOB_SHA256 = {
        P.EXPECTED_CELLS: P.EXPECTED_PROSPECTIVE_JOB_SHA256
    }
    Full.EXPECTED_MATERIALIZED_PDDL_FILES = {
        P.EXPECTED_CELLS: P.EXPECTED_MATERIALIZED_PDDL_FILES
    }
    Full.EXPECTED_MATERIALIZED_PDDL_BYTES = {
        P.EXPECTED_CELLS: P.EXPECTED_MATERIALIZED_PDDL_BYTES
    }
    Full.EXPECTED_PDDL_BYTES_PER_CONFIG = P.EXPECTED_PDDL_BYTES_PER_CONFIG
    Full.EXPECTED_UNIQUE_PDDL_SOURCE_FILES = P.EXPECTED_UNIQUE_PDDL_SOURCE_FILES
    Full.EXPECTED_UNIQUE_PDDL_SOURCE_BYTES = P.EXPECTED_UNIQUE_PDDL_SOURCE_BYTES
    Full.MATERIALIZED_PDDL_PROTOCOL = P.MATERIALIZED_PDDL_PROTOCOL
    Full.PROTOCOL_FILES = PROTOCOL_FILES
    Full.validate_full_layout = P.validate_layout
    Full.validate_fixed_environment = validate_fixed_environment
    Full._run_loop_blocks = _absolute_run_loop_blocks
    Full.FULL_FIXED_ENVIRONMENT = {
        "time_limit": "300s",
        "memory_limit": "8G",
        "build_options": ["release_no_lp"],
        "cache_build_name": "release_no_lp",
        "scheduler_cluster": "arrhenius",
        "scheduler_cpu_model": "AMD EPYC 9755 128-Core Processor",
        "scheduler_partition": "cpu",
        "scheduler_qos": "normal",
        "scheduler_account": "naiss2025-5-561-cpu",
        "scheduler_time_limits": {P.EXPECTED_CELLS: "00:45:00"},
        "scheduler_memory_per_cpu": "9G",
        "scheduler_cpus_per_task": 1,
        "array_task_throttle": 5,
        "max_array_tasks": 1000,
        "wrapper_allowance_seconds_per_run": 60,
    }
    # The cap trace can exceed Lab's ordinary stdout envelope.  Both build and
    # start-grid attestation use the same reviewed bounded wrapper.
    Full.V._expected_run_script = _expected_limited_run_script


def prospective_job():
    configure_completion_base()
    _, job = Full.make_in_memory_full_run_job(
        P.EXPECTED_CELLS, EXPERIMENT_DATA_PATH
    )
    Full.exact_header_assertions(job, P.EXPECTED_CELLS)
    return job, hashlib.sha256(job.encode("utf-8")).hexdigest()


def _common_metadata(protocol_revision):
    layout = P.validate_layout()
    cache = C.cached_revision(P.PLANNER_REVISION)
    return {
        "planner_revision": P.PLANNER_REVISION,
        "protocol_revision": protocol_revision,
        "planner_revision_is_protocol_ancestor": True,
        "planner_build_options": list(C.BUILD_OPTIONS),
        "planner_build_config": C.CACHE_BUILD_NAME,
        "planner_binary_sha256": P.CACHE_BINARY_SHA256,
        "planner_revision_cache_name": cache.name,
        "external_plan_validation": False,
        "plan_validation_protocol": C.PLAN_VALIDATION_PROTOCOL,
        "plan_file_parser_protocol": C.PLAN_FILE_PARSER_PROTOCOL,
        "outcome_reconciliation_protocol": C.OUTCOME_RECONCILIATION_PROTOCOL,
        "cofactor_width_property": C.COFACTOR_WIDTH_PROPERTY,
        "cofactor_width_parser_protocol": C.COFACTOR_WIDTH_PARSER_PROTOCOL,
        "metrics_validation_protocol": C.wbh_parser.METRICS_VALIDATION_PROTOCOL,
        "python_version": C.platform.python_version(),
        "lab_version": C.INSTALLED_LAB_VERSION,
        "required_lab_version": C.REQUIRED_LAB_VERSION,
        "task_order_seed": C.TASK_ORDER_SEED,
        "task_order_method": C.TASK_ORDER_METHOD,
        "driver_time_limit": C.TIME_LIMIT,
        "driver_memory_limit": C.MEMORY_LIMIT,
        "planner_limit_basis": "aggregate-process-cpu",
        "per_cell_wall_limit_enforced": False,
        "outer_per_cell_watchdog": False,
        "scheduler_environment": "arrhenius-slurm",
        "scheduler_cluster": C.SCHEDULER_CLUSTER,
        "scheduler_cpu_model": C.SCHEDULER_CPU_MODEL,
        "scheduler_partition": C.SCHEDULER_PARTITION,
        "scheduler_qos": C.SCHEDULER_QOS,
        "scheduler_account": C.SCHEDULER_ACCOUNT,
        "scheduler_time_limit_per_task": P.SCHEDULER_TIME_LIMIT,
        "scheduler_memory_per_cpu": C.SCHEDULER_MEMORY_PER_CPU,
        "scheduler_cpus_per_task": C.SCHEDULER_CPUS_PER_TASK,
        "scheduler_array_task_throttle": C.ARRAY_TASK_THROTTLE,
        "scheduler_max_array_tasks": C.MAX_ARRAY_TASKS,
        "scheduler_array_tasks": layout["array_tasks"],
        "scheduler_runs_per_array_task": layout["runs_per_array_task"],
        "scheduler_wrapper_allowance_seconds_per_run": (
            P.WRAPPER_ALLOWANCE_SECONDS_PER_RUN
        ),
        "scheduler_envelope_protocol": (
            "fixed-45m-using-7-times-300plus60-accounting/v1"
        ),
        "scheduler_timeout_invalidates_census": True,
        "scheduler_envelope_is_wall_worst_case_guarantee": False,
        "declared_run_count": P.EXPECTED_CELLS,
        "repetitions": 1,
    }


def make_protocol_metadata(
    benchmark_root,
    source_attestation,
    promotion_certificate,
    *,
    protocol_revision=None,
    prospective_job_sha256=P.EXPECTED_PROSPECTIVE_JOB_SHA256,
):
    if protocol_revision is None:
        protocol_revision = C.require_revision_ancestor_of_head(
            P.PLANNER_REVISION
        )
    metadata = _common_metadata(protocol_revision)
    additions = {
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "analysis_predeclaration": copy.deepcopy(P.ANALYSIS_PREDECLARATION),
        "promotion_rule": copy.deepcopy(P.PROMOTION_RULE),
        "promotion_evidence_protocol": (
            "digest-pinned-properties-revalidated-before-start-not-embedded/v1"
        ),
        "screen_protocol": P.SCREEN_PROTOCOL,
        "screen_protocol_revision": P.SCREEN_PROTOCOL_REVISION,
        "screen_planner_revision": P.SCREEN_PLANNER_REVISION,
        "screen_properties_canonical_sha256": (
            promotion_certificate["screen_properties_canonical_sha256"]
        ),
        "screen_k32_may_substitute": False,
        "task_selection_protocol": Full.TASK_SELECTION_PROTOCOL,
        "task_manifest": "suite_wbh_operator_costs.json#supported",
        "task_manifest_sha256": P.EXPECTED_TASK_MANIFEST_SHA256,
        "task_count": P.EXPECTED_TASKS,
        "domain_count": P.EXPECTED_DOMAINS,
        "domain_sequence_sha256": P.EXPECTED_DOMAIN_SEQUENCE_SHA256,
        "domain_task_counts_sha256": P.EXPECTED_DOMAIN_TASK_COUNTS_SHA256,
        "source_manifest_sha256": source_attestation["source_manifest_sha256"],
        "task_sources_sha256": source_attestation["task_sources_sha256"],
        "primary_task_count": P.EXPECTED_PRIMARY_TASKS,
        "primary_domain_count": P.EXPECTED_PRIMARY_DOMAINS,
        "primary_task_manifest_sha256": (
            P.EXPECTED_PRIMARY_TASK_MANIFEST_SHA256
        ),
        "primary_task_sources_sha256": (
            P.EXPECTED_PRIMARY_TASK_SOURCES_SHA256
        ),
        "development_task_manifest_sha256": P.SCREEN_MANIFEST_SHA256,
        "config_count": P.EXPECTED_CONFIGS,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "config_order": list(P.LABELS),
        "completion_policy": copy.deepcopy(P.COMPLETION_POLICY),
        "completion_marker_name": Full.FULL_COMPLETION_MARKER,
        "completion_marker_schema": Full.FULL_COMPLETION_MARKER_SCHEMA,
        "completion_marker_protocol": Full.FULL_COMPLETION_MARKER_PROTOCOL,
        "restart_count_file": Full.FULL_RESTART_COUNT_FILE,
        "dynamic_output_recovery": copy.deepcopy(Full.FULL_DYNAMIC_OUTPUT_POLICY),
        "materialized_pddl_protocol": P.MATERIALIZED_PDDL_PROTOCOL,
        "materialized_pddl_files": P.EXPECTED_MATERIALIZED_PDDL_FILES,
        "materialized_pddl_bytes": P.EXPECTED_MATERIALIZED_PDDL_BYTES,
        "pddl_bytes_per_config": P.EXPECTED_PDDL_BYTES_PER_CONFIG,
        "unique_pddl_source_files": P.EXPECTED_UNIQUE_PDDL_SOURCE_FILES,
        "unique_pddl_source_bytes": P.EXPECTED_UNIQUE_PDDL_SOURCE_BYTES,
        "pdb_selector_parser_protocol": CapParser.PARSER_PROTOCOL,
        "selector_pool_protocol": CapParser.PROTOCOL,
        "selector_score_version": CapParser.SCORE_VERSION,
        "selector_source_order": list(C.PDB_SELECTOR_SOURCES),
        "selector_value_caps": list(ScreenRunner.CAP_GRID),
        "selector_width_budgets": [8],
        "raw_pdb_materializations_per_pattern": 1,
        "finite_value_transform": "min(d,kappa);infinity-retained/v1",
        "per_pattern_choice": "strongest-feasible-cap-before-score/v1",
        "planner_soft_stdout_limit_kib": P.PLANNER_SOFT_STDOUT_LIMIT_KIB,
        "planner_hard_stdout_limit_kib": P.PLANNER_HARD_STDOUT_LIMIT_KIB,
        "scheduler_requeue_requested": True,
        "scheduler_open_mode": "append",
        "scheduler_requeue_scope": (
            "eligible-node-failure-preemption-admin-events-only;"
            "timeout-cancel-oom-and-arbitrary-exit-remain-fail-closed"
        ),
        "array_task_run_distribution": copy.deepcopy(
            P.validate_layout()["array_task_run_distribution"]
        ),
        "array_assignment": P.array_assignment(),
        "prospective_start_job_sha256": prospective_job_sha256,
        "planner_preprocess_sha256": P.CACHE_PREPROCESS_SHA256,
        "experiment_data_directory": "data/{}".format(Path(__file__).stem),
        "benchmark_revision": Full.BENCHMARK_REVISION,
        "benchmark_repository": Full.BENCHMARK_REPOSITORY,
        "benchmark_worktree": str(Path(benchmark_root).resolve()),
    }
    overlap = set(metadata) & set(additions)
    if overlap:
        raise ProtocolError(
            "focused full metadata key overlap: {}".format(sorted(overlap))
        )
    metadata.update(additions)
    return metadata


def _synthetic_promotion_certificate():
    return {
        "protocol": P.PROMOTION_RULE["protocol"],
        "rule": copy.deepcopy(P.PROMOTION_RULE),
        "screen_protocol": P.SCREEN_PROTOCOL,
        "screen_protocol_revision": P.SCREEN_PROTOCOL_REVISION,
        "screen_planner_revision": P.SCREEN_PLANNER_REVISION,
        "screen_properties_canonical_sha256": hashlib.sha256(
            b"synthetic-screen-properties"
        ).hexdigest(),
        "checks": {
            "complete_300_cell_screen": True,
            "all_k8_raw_pools_match": True,
            "solved_costs_agree": True,
            "cap_k8_has_strictly_more_semantic_nontrivial_selections": True,
            "cap_k8_coverage_wins_minus_losses_nonnegative": True,
            "k32_not_substituted": True,
        },
        "k8": {
            "coverage_wins": 1,
            "coverage_losses": 1,
            "coverage_net": 0,
            "cap_semantic_nontrivial": 2,
            "exact_semantic_nontrivial": 1,
            "matching_raw_pool_pairs": 50,
        },
        "k32_consulted_for_promotion": False,
        "promoted": True,
    }


def validate_metadata(metadata, benchmark_root, source_attestation, promotion):
    expected = make_protocol_metadata(
        benchmark_root,
        source_attestation,
        promotion,
        protocol_revision=metadata.get("protocol_revision"),
        prospective_job_sha256=metadata.get("prospective_start_job_sha256"),
    )
    if P.canonical_json(metadata) != P.canonical_json(expected):
        raise ProtocolError("focused full protocol metadata changed")


def _git_bytes(*args):
    try:
        return subprocess.run(
            ["git", "-C", str(C.REPO), *args],
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as err:
        raise ProtocolError(
            "could not attest focused implementation bytes: {}".format(
                " ".join(args)
            )
        ) from err


def _pin_literal(name):
    value = getattr(P, name)
    if name == "PROTOCOL_IMPLEMENTATION_REVISION":
        if type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None:
            raise ProtocolError("focused implementation pin is not a full revision")
    elif value is not None and (
        type(value) is not str or re.fullmatch(r"[0-9a-f]{64}", value) is None
    ):
        raise ProtocolError("{} is not None or a SHA-256".format(name))
    if value is None:
        return b"None"
    return ('"{}"'.format(value)).encode("ascii")


def _expected_pinned_protocol_source(reviewed):
    """Construct the only permitted descendant blob, byte for byte."""
    expected = reviewed
    for name in PIN_ASSIGNMENTS:
        old = (name + " = None").encode("ascii")
        if expected.count(old) != 1:
            raise ProtocolError(
                "reviewed implementation must contain exactly one unset {}".
                format(name)
            )
        new = name.encode("ascii") + b" = " + _pin_literal(name)
        expected = expected.replace(old, new, 1)
    return expected


def require_implementation_seal(head):
    """Allow descendants to change only the three reviewed pin literals."""
    try:
        changed_output = C._git_output(
            "diff",
            "--name-only",
            P.PROTOCOL_IMPLEMENTATION_REVISION + ".." + head,
        )
    except Exception as err:
        raise ProtocolError("could not attest focused descendant paths") from err
    changed = set(changed_output.splitlines()) if changed_output else set()
    if changed != {PIN_MUTABLE_PROTOCOL_PATH}:
        raise ProtocolError(
            "focused launch descendant changed files outside the pin module: {}".
            format(", ".join(sorted(changed)) if changed else "none")
        )
    try:
        reviewed_tree = C._git_output(
            "ls-tree",
            P.PROTOCOL_IMPLEMENTATION_REVISION,
            "--",
            PIN_MUTABLE_PROTOCOL_PATH,
        )
        current_tree = C._git_output(
            "ls-tree", head, "--", PIN_MUTABLE_PROTOCOL_PATH
        )
    except Exception as err:
        raise ProtocolError("could not attest focused protocol tree entries") from err
    tree_pattern = re.compile(
        r"100644 blob [0-9a-f]{40}\t" + re.escape(PIN_MUTABLE_PROTOCOL_PATH)
    )
    if tree_pattern.fullmatch(reviewed_tree) is None or (
        tree_pattern.fullmatch(current_tree) is None
    ):
        raise ProtocolError("focused protocol pin module mode or type changed")
    reviewed = _git_bytes(
        "show",
        P.PROTOCOL_IMPLEMENTATION_REVISION + ":" + PIN_MUTABLE_PROTOCOL_PATH,
    )
    current = _git_bytes("show", head + ":" + PIN_MUTABLE_PROTOCOL_PATH)
    if current != _expected_pinned_protocol_source(reviewed):
        raise ProtocolError(
            "focused launch descendant changed outcome-independent protocol bytes"
        )


def require_protocol_and_job_pins():
    P.require_revision(
        P.PROTOCOL_IMPLEMENTATION_REVISION,
        "focused protocol implementation revision",
    )
    P.require_sha256(
        P.EXPECTED_PROSPECTIVE_JOB_SHA256,
        "focused prospective job SHA-256",
    )
    C.require_clean_committed_revision(P.PLANNER_REVISION, PROTOCOL_FILES)
    head = C.require_revision_ancestor_of_head(P.PLANNER_REVISION)
    try:
        C._git_output(
            "merge-base",
            "--is-ancestor",
            P.PROTOCOL_IMPLEMENTATION_REVISION,
            head,
        )
    except Exception as err:
        raise ProtocolError(
            "focused implementation revision {} is not an ancestor of launch "
            "HEAD {}".format(P.PROTOCOL_IMPLEMENTATION_REVISION, head)
        ) from err
    require_implementation_seal(head)
    if C.cached_revision(P.PLANNER_REVISION).name != (
        P.PLANNER_REVISION + P.CACHE_NAME_SUFFIX
    ):
        raise ProtocolError("focused revision-cache name changed")
    _, digest = prospective_job()
    if digest != P.EXPECTED_PROSPECTIVE_JOB_SHA256:
        raise ProtocolError(
            "focused prospective job SHA-256 changed: expected {}, got {}".format(
                P.EXPECTED_PROSPECTIVE_JOB_SHA256, digest
            )
        )


def require_revision_cache():
    configure_completion_base()
    return Full.require_full_revision_cache()


def new_experiment(metadata):
    configure_completion_base()
    experiment = C.ProtocolFastDownwardExperiment(
        environment=Full.get_full_environment(P.EXPECTED_CELLS),
        revision_cache=str(C.REVISION_CACHE),
    )
    experiment.protocol_run_properties.update(metadata)
    experiment.planner_stdout_limits_kib = (
        P.PLANNER_SOFT_STDOUT_LIMIT_KIB,
        P.PLANNER_HARD_STDOUT_LIMIT_KIB,
    )
    experiment.add_parser(experiment.EXITCODE_PARSER)
    experiment.add_parser(experiment.TRANSLATOR_PARSER)
    experiment.add_parser(experiment.SINGLE_SEARCH_PARSER)
    experiment.add_parser(experiment.PLANNER_PARSER)
    experiment.add_parser(C.wbh_parser.get_parser())
    experiment.add_parser(C.get_cofactor_width_parser())
    experiment.add_parser(CapParser.get_parser())
    experiment.add_parser(C.get_run_log_plan_cost_parser())
    experiment.add_parser(C.get_plan_file_parser())
    experiment.add_parser(Full.get_full_completion_parser())
    experiment.add_parser(C.get_outcome_reconciliation_parser())
    return experiment


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--screen-properties",
        type=Path,
        help="Canonical complete 300-cell development-screen properties.",
    )
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("steps", nargs="*", help="Lab steps; build/start run alone")
    args = parser.parse_args(argv)
    if args.check and args.self_test:
        parser.error("--check and --self-test are mutually exclusive")
    if (args.check or args.self_test) and args.steps:
        parser.error("read-only checks cannot be combined with Lab steps")
    if args.self_test and args.screen_properties is not None:
        parser.error("--self-test does not consume outcomes")
    args.steps = V.normalize_lab_steps(args.steps)
    return args


def inspect_launch_blockers():
    checks = (
        ("prospective protocol/job pins", require_protocol_and_job_pins),
        ("requirements Lab version", C.require_pinned_lab_version),
        ("pinned revision cache", require_revision_cache),
        ("screen properties pin", P._require_screen_properties_pin),
    )
    blockers = []
    for label, function in checks:
        try:
            function()
        except (ProtocolError, RuntimeError, V.ProtocolError) as err:
            blockers.append("{}: {}".format(label, str(err).replace("\n", " | ")))
    return blockers


def self_test():
    configure_completion_base()
    P.validate_prospective_contract()
    validate_fixed_environment()
    tasks, attestation = P.load_full_tasks()
    matrix = P.validate_matrix(tasks)
    if matrix["run_count"] != 6885 or matrix["layout"]["array_tasks"] != 984:
        raise AssertionError("focused matrix/layout changed")
    benchmark = Path("/synthetic/downward-benchmarks")
    source = {
        "source_manifest_sha256": P.EXPECTED_SOURCE_MANIFEST_SHA256,
        "task_sources_sha256": P.EXPECTED_TASK_SOURCES_SHA256,
    }
    metadata = make_protocol_metadata(
        benchmark,
        source,
        _synthetic_promotion_certificate(),
        protocol_revision="0123456789abcdef0123456789abcdef01234567",
        prospective_job_sha256=hashlib.sha256(b"synthetic-job").hexdigest(),
    )
    validate_metadata(
        metadata, benchmark, source, _synthetic_promotion_certificate()
    )
    job, digest = prospective_job()
    headers = Full.exact_header_assertions(job, P.EXPECTED_CELLS)
    for required in (
        "#! /bin/bash",
        "#SBATCH --time=00:45:00",
        "#SBATCH --array=1-984%5",
        "#SBATCH --requeue",
    ):
        if headers.count(required) != 1:
            raise AssertionError("focused job header lost {}".format(required))
    if Full._parse_full_completion_marker(
        Full._full_completion_marker_bytes(17, 2), 17
    )["completion_slurm_restart_count"] != 2:
        raise AssertionError("reused completion marker parser changed")
    if attestation["screen_excluded_task_manifest_sha256"] != (
        P.EXPECTED_PRIMARY_TASK_MANIFEST_SHA256
    ):
        raise AssertionError("primary complement attestation changed")
    print("Focused cap-grid full runner self-test: PASS")
    print("matrix: 1,377 tasks x 5 configs = 6,885 cells")
    print("layout: 984 array tasks x at most 7 cells; requested 00:45:00")
    print("option matrix SHA-256: {}".format(P.OPTION_MATRIX_SHA256))
    print("prospective job SHA-256 (to review/pin): {}".format(digest))


def check_protocol(screen_properties=None):
    configure_completion_base()
    P.validate_prospective_contract()
    tasks, record_attestation = P.load_full_tasks()
    benchmark_root = Full.require_pinned_benchmark_worktree()
    source_attestation = Full.attest_task_sources(benchmark_root, tasks)
    if source_attestation["task_sources_sha256"] != record_attestation[
        "task_sources_sha256"
    ]:
        raise ProtocolError("source-record and source-byte attestations differ")
    blockers = inspect_launch_blockers()
    promotion = None
    promotion_error = None
    if screen_properties is not None:
        if blockers:
            promotion_error = (
                "committed launch identity is not ready; refusing to read "
                "screen outcomes"
            )
        else:
            try:
                promotion = P.load_and_evaluate_promotion(screen_properties)
            except ProtocolError as err:
                promotion_error = str(err)
    _, job_digest = prospective_job()
    print("Focused cap-grid full read-only check: PASS")
    print("tasks/configs/cells: 1377/5/6885")
    print("primary complement tasks/domains: 1327/46")
    print("option matrix SHA-256: {}".format(P.OPTION_MATRIX_SHA256))
    print("prospective job SHA-256: {}".format(job_digest))
    print("promotion input read: {}".format(promotion is not None))
    if promotion is not None:
        print("frozen K8 promotion: PASS")
    if promotion_error is not None:
        print("promotion gate: BLOCKED ({})".format(promotion_error))
    print("launch gate: {}".format("BLOCKED" if blockers else "READY"))
    for blocker in blockers:
        print("  " + blocker)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_test:
        self_test()
        return 0
    if args.check:
        check_protocol(args.screen_properties)
        return 0
    if not args.steps:
        raise ProtocolError("provide Lab steps, --check, or --self-test")

    configure_completion_base()
    P.validate_prospective_contract()
    # This clean committed identity gate must precede any inspection or load
    # of the outcome-bearing development-screen properties.
    require_protocol_and_job_pins()
    tasks, record_attestation = P.load_full_tasks()
    matrix = P.validate_matrix(tasks)
    benchmark_root = Full.require_pinned_benchmark_worktree()
    source_attestation = Full.attest_task_sources(benchmark_root, tasks)
    if source_attestation["task_sources_sha256"] != record_attestation[
        "task_sources_sha256"
    ]:
        raise ProtocolError("source-record and source-byte attestations differ")

    promotion = None
    if "start" in args.steps:
        if args.screen_properties is None:
            raise ProtocolError("start requires --screen-properties")
        promotion = P.load_and_evaluate_promotion(args.screen_properties)
    elif args.screen_properties is not None:
        raise ProtocolError("--screen-properties is accepted only by --check/start")
    # Every Lab action, including parse/fetch/report, is tied to the reviewed
    # launch revision and exact prospective job bytes.
    cache_info = C.require_launch_prerequisites(
        P.PLANNER_REVISION,
        P.CACHE_BINARY_SHA256,
        args=args.steps,
        protocol_files=PROTOCOL_FILES,
    )
    if cache_info is not None:
        require_revision_cache()

    if promotion is None:
        # Build is outcome-independent.  It records the frozen rule and exact
        # properties pin, but no derived decision; start later reattests all.
        if "build" in args.steps:
            P._require_screen_properties_pin()
            promotion = {
                "protocol": P.PROMOTION_RULE["protocol"],
                "rule": copy.deepcopy(P.PROMOTION_RULE),
                "screen_protocol": P.SCREEN_PROTOCOL,
                "screen_protocol_revision": P.SCREEN_PROTOCOL_REVISION,
                "screen_planner_revision": P.SCREEN_PLANNER_REVISION,
                "screen_properties_canonical_sha256": (
                    P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256
                ),
                "checks": None,
                "k8": None,
                "k32_consulted_for_promotion": False,
                "promoted": None,
            }
        else:
            # Parse/fetch/report preserve the outcome-independent static
            # promotion identity embedded at build time.
            P._require_screen_properties_pin()
            promotion = {
                "screen_properties_canonical_sha256": (
                    P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256
                )
            }

    metadata = make_protocol_metadata(
        benchmark_root, source_attestation, promotion
    )
    if "build" in args.steps:
        C.require_fresh_experiment_build(EXPERIMENT_DATA_PATH)
    if "start" in args.steps:
        attestation = Full.attest_existing_start_grid(
            metadata, benchmark_root, tasks, matrix
        )
        print(
            "start grid attestation: PASS ({} cells; binary {}; preprocess {}; "
            "job {})".format(
                attestation["run_count"],
                attestation["binary_sha256"],
                attestation["preprocess_sha256"],
                attestation["job_sha256"],
            )
        )

    experiment = new_experiment(metadata)
    if Path(experiment.path).resolve() != EXPERIMENT_DATA_PATH.resolve():
        raise ProtocolError("focused experiment data path changed")
    C.add_suite(experiment, benchmark_root, tasks)
    for label, search in P.CONFIGS:
        C.add_algorithm(experiment, label, search, revision=P.PLANNER_REVISION)
    C.add_standard_steps(
        experiment, extra_attributes=Full.FULL_COMPLETION_ATTRIBUTES
    )
    sys.argv = [sys.argv[0]] + args.steps
    experiment.run_steps()
    if "build" in args.steps:
        materialized = Full.materialize_grid_pddl_inputs(
            benchmark_root, tasks, matrix
        )
        cleanup = C.strip_copied_python_bytecode(EXPERIMENT_DATA_PATH)
        attestation = Full.attest_existing_start_grid(
            metadata, benchmark_root, tasks, matrix
        )
        print(
            "built focused grid normalization/attestation: PASS "
            "({} PDDL files/{} bytes; {} bytecode files; {} cache dirs; job {})".
            format(
                materialized["files"],
                materialized["bytes"],
                cleanup["removed_bytecode_files"],
                cleanup["removed_cache_directories"],
                attestation["job_sha256"],
            )
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ProtocolError, RuntimeError, V.ProtocolError) as err:
        print("protocol error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
