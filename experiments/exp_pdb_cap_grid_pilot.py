#!/usr/bin/env python3
"""Prospective development screen for cap-aware exact-width PDB selection.

This is a new 300-cell run over the already development-selected 50-task P4
manifest.  It is a mechanism screen, not confirmatory evidence and not an
independent population estimate.  Before any outcome from this matrix is read,
the script freezes:

* the raw pattern pool (empty, BDD prefix, goal prefix/fill, seeded CEGAR);
* caps ``0,1,2,4,8,16,32,64,128,256,exact`` and exact width budgets 8 and 32;
* one raw PDB materialization per pattern, infinity retention, and selection of
  the strongest feasible transform per pattern before the frozen score;
* K=8 as the primary comparison and K=32 as a non-promotable sensitivity;
* paired cap-grid-minus-exact K=8 coverage and semantic-nontrivial selection
  (``finite_sum > 0 or dead_count > 0``) as the primary endpoints; and
* construction-charged PAR2, jointly solved CPU, certified image/effort,
  construction time, and cap/source/pattern/W/A/T/U/V as ordered descriptive
  secondary endpoints.

All six configurations are rerun under one immutable planner/protocol revision;
no P4 runtime or coverage record is reused.  Build and start remain separate.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_arrhenius_common as C
import exp_arrhenius_selector_pilot as Base
import pdb_cap_selector_parser as CapParser
import suite_cost_manifest


ProtocolError = Base.ProtocolError
BASE_RUNNER_PATH = Path(Base.__file__).resolve()
PROTOCOL = "pdb-cap-grid-development-screen-v3"
SELECTION_RULE = "fixed-k8-primary-k32-sensitivity-no-promotion/v1"
ANALYSIS_CONTRACT = {
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

CAP_GRID = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, "exact"]
PLANNER_SOFT_STDOUT_LIMIT_KIB = 7168
PLANNER_HARD_STDOUT_LIMIT_KIB = 16384
MAX_MATERIALIZED_PATTERN_GROUPS = 5
MAX_HISTOGRAM_TOTAL_BASE64_BYTES = (
    MAX_MATERIALIZED_PATTERN_GROUPS * CapParser.MAX_HISTOGRAM_BASE64
)
CONFIGS = [
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
]
OPTION_MATRIX_SHA256 = (
    "70a34cc1804f542c8911bd5de4c44e5b820772832dda73e426fb2081366455fa"
)

MANIFEST = Path(__file__).with_name("selector_pilot_suite.txt")
MANIFEST_DIGEST = Base.MANIFEST_DIGEST
EXPECTED_TASKS = 50
EXPECTED_DOMAINS = 25
EXPECTED_TASK_SOURCES_SHA256 = Base.EXPECTED_TASK_SOURCES_SHA256
EXPECTED_PDDL_BYTES_PER_CONFIG = Base.EXPECTED_PDDL_BYTES_PER_CONFIG
EXPECTED_UNIQUE_PDDL_SOURCE_FILES = Base.EXPECTED_UNIQUE_PDDL_SOURCE_FILES
EXPECTED_UNIQUE_PDDL_SOURCE_BYTES = Base.EXPECTED_UNIQUE_PDDL_SOURCE_BYTES
EXPECTED_MATERIALIZED_PDDL_FILES = 600
EXPECTED_MATERIALIZED_PDDL_BYTES = 15106272
EXPERIMENT_DATA_PATH = (
    Path(__file__).resolve().parent / "data" / Path(__file__).stem
)

BENCHMARK_REVISION = Base.BENCHMARK_REVISION
BENCHMARK_REPOSITORY = Base.BENCHMARK_REPOSITORY
MATERIALIZED_PDDL_PROTOCOL = Base.MATERIALIZED_PDDL_PROTOCOL
FIXED_ENVIRONMENT = dict(Base.FIXED_ENVIRONMENT)

# These are an all-or-none post-build pin gate.  The launch runner is first
# committed, then its clean revision cache is independently built/smoked and
# these values are reviewed in a descendant protocol-pin commit.
PLANNER_REVISION = "e04d56cc61d00c954f2369e9fb74bd469277d52e"
CACHE_BINARY_SHA256 = (
    "77cf4950563be2d2a60aded13783a3ffe26c0c8391ac9d626f3bd618231941fa"
)
CACHE_PREPROCESS_SHA256 = (
    "fc3233bfd260210cf4d0cce11146fe6f3198820d6e19a8b56740c1240039378b"
)

PROTOCOL_FILES = (
    Path(__file__).resolve(),
    Path(__file__).with_name("analyze_pdb_cap_grid_pilot.py").resolve(),
    BASE_RUNNER_PATH,
    Path(C.__file__).resolve(),
    Path(CapParser.__file__).resolve(),
    Path(__file__).with_name("wbh_parser.py").resolve(),
    Path(__file__).with_name("validate_wbh_log.py").resolve(),
    MANIFEST.resolve(),
    Path(suite_cost_manifest.__file__).resolve(),
    Path(__file__).with_name("suite_wbh_operator_costs.json").resolve(),
    Path(__file__).with_name("suite_wbh_operator_costs.json.sha256").resolve(),
    Path(__file__).with_name("requirements.txt").resolve(),
)


def _sha256_configs(configs):
    payload = [{"label": label, "search": search} for label, search in configs]
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
    ).hexdigest()


def configure_base_module():
    """Bind the reviewed P4 grid attestor to this smaller new protocol."""
    Base.__file__ = str(Path(__file__).resolve())
    Base.PROTOCOL = PROTOCOL
    Base.SELECTION_RULE = SELECTION_RULE
    Base.PROTOCOL_FILES = PROTOCOL_FILES
    Base.MANIFEST = MANIFEST
    Base.MANIFEST_DIGEST = MANIFEST_DIGEST
    Base.EXPECTED_TASKS = EXPECTED_TASKS
    Base.EXPECTED_DOMAINS = EXPECTED_DOMAINS
    Base.EXPECTED_TASK_SOURCES_SHA256 = EXPECTED_TASK_SOURCES_SHA256
    Base.EXPECTED_PDDL_BYTES_PER_CONFIG = EXPECTED_PDDL_BYTES_PER_CONFIG
    Base.EXPECTED_UNIQUE_PDDL_SOURCE_FILES = EXPECTED_UNIQUE_PDDL_SOURCE_FILES
    Base.EXPECTED_UNIQUE_PDDL_SOURCE_BYTES = EXPECTED_UNIQUE_PDDL_SOURCE_BYTES
    Base.EXPECTED_MATERIALIZED_PDDL_FILES = EXPECTED_MATERIALIZED_PDDL_FILES
    Base.EXPECTED_MATERIALIZED_PDDL_BYTES = EXPECTED_MATERIALIZED_PDDL_BYTES
    Base.EXPERIMENT_DATA_PATH = EXPERIMENT_DATA_PATH
    Base.PLANNER_REVISION = PLANNER_REVISION
    Base.CACHE_BINARY_SHA256 = CACHE_BINARY_SHA256
    Base.CACHE_PREPROCESS_SHA256 = CACHE_PREPROCESS_SHA256
    Base.BENCHMARK_REVISION = BENCHMARK_REVISION
    Base.BENCHMARK_REPOSITORY = BENCHMARK_REPOSITORY
    Base.FIXED_ENVIRONMENT = FIXED_ENVIRONMENT


def read_manifest():
    configure_base_module()
    return Base.read_manifest()


def validate_config_matrix(tasks):
    configure_base_module()
    Base.validate_fixed_environment()
    if len(tasks) != EXPECTED_TASKS:
        raise ProtocolError("cap-grid pilot task count changed")
    if len(CONFIGS) != 6:
        raise ProtocolError("cap-grid pilot must contain exactly six configs")
    labels = [label for label, _ in CONFIGS]
    searches = [search for _, search in CONFIGS]
    if len(labels) != len(set(labels)) or len(searches) != len(set(searches)):
        raise ProtocolError("cap-grid labels/searches must be unique")
    for label, search in CONFIGS:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", label):
            raise ProtocolError("invalid cap-grid label {!r}".format(label))
        C.search_config(search)
    digest = _sha256_configs(CONFIGS)
    if digest != OPTION_MATRIX_SHA256:
        raise ProtocolError(
            "cap-grid matrix changed: expected {}, got {}".format(
                OPTION_MATRIX_SHA256, digest
            )
        )
    run_count = len(tasks) * len(CONFIGS)
    if run_count != 300:
        raise ProtocolError("cap-grid screen must contain exactly 300 cells")
    layout = C.validate_run_layout(
        run_count, require_one_run_per_array_task=True
    )
    return {
        "configs": list(CONFIGS),
        "matrix_digest": digest,
        "run_count": run_count,
        "layout": layout,
    }


def make_protocol_metadata(
    matrix,
    benchmark_root,
    source_attestation,
    *,
    planner_revision=PLANNER_REVISION,
    cache_binary_sha256=CACHE_BINARY_SHA256,
    cache_preprocess_sha256=CACHE_PREPROCESS_SHA256,
):
    metadata = C.common_protocol_metadata(
        planner_revision, cache_binary_sha256, matrix["run_count"]
    )
    additions = {
        "protocol": PROTOCOL,
        "selection_rule": SELECTION_RULE,
        "analysis_contract": ANALYSIS_CONTRACT,
        "task_manifest": MANIFEST.name,
        "task_manifest_sha256": MANIFEST_DIGEST,
        "task_count": EXPECTED_TASKS,
        "domain_count": EXPECTED_DOMAINS,
        "planner_preprocess_sha256": cache_preprocess_sha256,
        "experiment_data_directory": "data/exp_pdb_cap_grid_pilot",
        "pdb_selector_parser_protocol": CapParser.PARSER_PROTOCOL,
        "selector_pool_protocol": CapParser.PROTOCOL,
        "selector_score_version": CapParser.SCORE_VERSION,
        "selector_source_order": list(C.PDB_SELECTOR_SOURCES),
        "selector_value_caps": list(CAP_GRID),
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
            CapParser.MAX_HISTOGRAM_BYTES
        ),
        "selector_histogram_max_base64_bytes_per_pattern": (
            CapParser.MAX_HISTOGRAM_BASE64
        ),
        "selector_histogram_max_materialized_patterns": (
            MAX_MATERIALIZED_PATTERN_GROUPS
        ),
        "selector_histogram_max_total_base64_bytes": (
            MAX_HISTOGRAM_TOTAL_BASE64_BYTES
        ),
        "planner_soft_stdout_limit_kib": PLANNER_SOFT_STDOUT_LIMIT_KIB,
        "planner_hard_stdout_limit_kib": PLANNER_HARD_STDOUT_LIMIT_KIB,
        "finite_value_transform": "min(d,kappa);infinity-retained/v1",
        "per_pattern_choice": "strongest-feasible-cap-before-score/v1",
        "config_count": len(CONFIGS),
        "option_matrix_sha256": matrix["matrix_digest"],
        "benchmark_revision": BENCHMARK_REVISION,
        "benchmark_repository": BENCHMARK_REPOSITORY,
        "benchmark_worktree": str(benchmark_root),
        "source_manifest_sha256": source_attestation[
            "source_manifest_sha256"
        ],
        "task_sources_sha256": source_attestation["task_sources_sha256"],
        "materialized_pddl_protocol": MATERIALIZED_PDDL_PROTOCOL,
        "materialized_pddl_files": EXPECTED_MATERIALIZED_PDDL_FILES,
        "materialized_pddl_bytes": EXPECTED_MATERIALIZED_PDDL_BYTES,
        "pddl_bytes_per_config": EXPECTED_PDDL_BYTES_PER_CONFIG,
        "unique_pddl_source_files": EXPECTED_UNIQUE_PDDL_SOURCE_FILES,
        "unique_pddl_source_bytes": EXPECTED_UNIQUE_PDDL_SOURCE_BYTES,
    }
    if set(metadata) & set(additions):
        raise ProtocolError("cap-grid metadata overlaps common protocol")
    metadata.update(additions)
    C.validate_common_protocol_metadata(metadata)
    return metadata


def self_test():
    configure_base_module()
    C.self_test_scheduler_headers()
    C.self_test_cofactor_width_parser()
    C.self_test_plan_file_parser()
    C.self_test_outcome_reconciliation_parser()
    tasks = read_manifest()
    matrix = validate_config_matrix(tasks)
    pins = (PLANNER_REVISION, CACHE_BINARY_SHA256, CACHE_PREPROCESS_SHA256)
    if any(value is None for value in pins) and not all(
        value is None for value in pins
    ):
        raise AssertionError("cap-grid launch pins are only partially set")
    Base.validate_cache_pin(required=all(value is not None for value in pins))
    metadata = make_protocol_metadata(
        matrix,
        C.REPO,
        {
            "source_manifest_sha256": suite_cost_manifest.EXPECTED_MANIFEST_SHA256,
            "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
        },
        planner_revision=C.REV,
        cache_binary_sha256=hashlib.sha256(b"cap-grid binary").hexdigest(),
        cache_preprocess_sha256=hashlib.sha256(
            b"cap-grid preprocess"
        ).hexdigest(),
    )
    if metadata["analysis_contract"] != ANALYSIS_CONTRACT:
        raise AssertionError("prospective cap-grid analysis contract changed")
    if matrix["layout"] != {
        "raw_runs": 300,
        "array_tasks": 300,
        "runs_per_array_task": 1,
        "scheduler_time_limit_seconds": 600,
    }:
        raise AssertionError("cap-grid 300-cell layout changed")
    histogram_kib = (MAX_HISTOGRAM_TOTAL_BASE64_BYTES + 1023) // 1024
    if 1024 + histogram_kib >= PLANNER_SOFT_STDOUT_LIMIT_KIB:
        raise AssertionError("histogram census can exceed the planner soft-output bound")
    if 10240 + histogram_kib >= PLANNER_HARD_STDOUT_LIMIT_KIB:
        raise AssertionError("histogram census can exceed the planner hard-output bound")
    expected_wrapper = Base._expected_run_script(
        ["planner"],
        soft_stdout_limit=PLANNER_SOFT_STDOUT_LIMIT_KIB,
        hard_stdout_limit=PLANNER_HARD_STDOUT_LIMIT_KIB,
    )
    for literal in (
        "soft_stdout_limit={}".format(PLANNER_SOFT_STDOUT_LIMIT_KIB),
        "hard_stdout_limit={}".format(PLANNER_HARD_STDOUT_LIMIT_KIB),
    ):
        if literal not in expected_wrapper:
            raise AssertionError("reviewed run wrapper lost {}".format(literal))
    _, job = C.make_in_memory_run_job(300)
    Base.exact_header_assertions(job, 300)
    parser = CapParser.get_parser()
    if len(parser.functions) != 1 or parser.functions[0].filename != "run.log":
        raise AssertionError("cap-grid parser is not bound to run.log")
    print(
        "PDB cap-grid pilot self-test: PASS "
        "(50 tasks x 6 configs = 300 one-run array elements)"
    )
    print("option matrix SHA-256: {}".format(matrix["matrix_digest"]))
    print("primary K: 8; frozen sensitivity K: 32")


def check_protocol(tasks, matrix):
    configure_base_module()
    benchmark_root = Base.require_pinned_benchmark_worktree()
    source_attestation = Base.attest_task_sources(benchmark_root, tasks)
    Base.validate_cache_pin(required=False)
    blockers = Base.inspect_launch_blockers()
    _, job = C.make_in_memory_run_job(matrix["run_count"])
    Base.exact_header_assertions(job, matrix["run_count"])
    print("PDB cap-grid development screen read-only check: PASS")
    print("planner revision: {}".format(PLANNER_REVISION))
    print("protocol revision: {}".format(C.REV))
    print("tasks/configs/cells: 50/6/300")
    print("option matrix SHA-256: {}".format(matrix["matrix_digest"]))
    print("primary endpoint: {}".format(
        ANALYSIS_CONTRACT["primary_performance_estimand"]
    ))
    print("launch gate: {}".format("BLOCKED" if blockers else "READY"))
    for blocker in blockers:
        print("  " + blocker)
    return benchmark_root, source_attestation


def main(argv=None):
    configure_base_module()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args = Base.parse_args(raw_args)
    if args.self_test:
        self_test()
        return 0
    tasks = read_manifest()
    matrix = validate_config_matrix(tasks)
    if args.check:
        check_protocol(tasks, matrix)
        return 0
    if not args.steps:
        raise ProtocolError("provide Lab steps, --check, or --self-test")

    Base.validate_cache_pin(required=True)
    benchmark_root = Base.require_pinned_benchmark_worktree()
    source_attestation = Base.attest_task_sources(benchmark_root, tasks)
    cache_info = C.require_launch_prerequisites(
        PLANNER_REVISION,
        CACHE_BINARY_SHA256,
        args=args.steps,
        protocol_files=PROTOCOL_FILES,
    )
    if cache_info is not None:
        Base.require_selector_revision_cache()
    _, job = C.make_in_memory_run_job(matrix["run_count"])
    Base.exact_header_assertions(job, matrix["run_count"])
    metadata = make_protocol_metadata(
        matrix, benchmark_root, source_attestation
    )
    if "build" in args.steps:
        C.require_fresh_experiment_build(EXPERIMENT_DATA_PATH)
    if "start" in args.steps:
        attestation = Base.attest_existing_start_grid(
            metadata, benchmark_root, tasks, matrix
        )
        print(
            "start grid attestation: PASS "
            "({} cells; binary {}; preprocess {}; job {})".format(
                attestation["run_count"],
                attestation["binary_sha256"],
                attestation["preprocess_sha256"],
                attestation["job_sha256"],
            )
        )
    experiment = C.new_experiment(
        metadata, pdb_selector_parser=CapParser.get_parser()
    )
    experiment.planner_stdout_limits_kib = (
        PLANNER_SOFT_STDOUT_LIMIT_KIB,
        PLANNER_HARD_STDOUT_LIMIT_KIB,
    )
    if Path(experiment.path).resolve() != EXPERIMENT_DATA_PATH:
        raise ProtocolError("cap-grid experiment data path changed")
    C.add_suite(experiment, benchmark_root, tasks)
    for label, search in matrix["configs"]:
        C.add_algorithm(experiment, label, search, revision=PLANNER_REVISION)
    C.add_standard_steps(experiment)
    sys.argv = [sys.argv[0]] + args.steps
    experiment.run_steps()
    if "build" in args.steps:
        materialized = Base.materialize_grid_pddl_inputs(
            benchmark_root, tasks, matrix
        )
        cleanup = C.strip_copied_python_bytecode(EXPERIMENT_DATA_PATH)
        attestation = Base.attest_existing_start_grid(
            metadata, benchmark_root, tasks, matrix
        )
        print(
            "built grid normalization/attestation: PASS "
            "({} PDDL files/{} bytes; {} bytecode files and {} cache "
            "directories removed; job {})".format(
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
        sys.exit(main())
    except (ProtocolError, RuntimeError) as err:
        print("protocol error: {}".format(err), file=sys.stderr)
        sys.exit(2)
