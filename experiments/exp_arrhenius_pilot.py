#!/usr/bin/env python3
"""Preliminary current-revision no-LP pilot for Arrhenius.

The checked-in matrix has 14 controls and six predeclared candidates over the
frozen 50-task screening manifest (1000 runs). Each array element executes
exactly one planner run.

This script is deliberately launch-incomplete until ``CACHE_BINARY_SHA256``
is set to the reviewed, stripped Lab revision-cache binary.  The cache must be
built separately on an Arrhenius compute node with the exact Lab version in
``requirements.txt``; neither ``build`` nor ``start`` will create it.

Read-only checks::

    python experiments/exp_arrhenius_pilot.py --self-test
    python experiments/exp_arrhenius_pilot.py --check

After the candidate list, current revision, benchmark worktree, requirements,
and cache hash have been reviewed, keep build and submission separate::

    experiments/.venv/bin/python experiments/exp_arrhenius_pilot.py build
    experiments/.venv/bin/python experiments/exp_arrhenius_pilot.py start
    experiments/.venv/bin/python experiments/exp_arrhenius_pilot.py parse fetch report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from downward import suites

import exp_arrhenius_common as C
import suite_cost_manifest


class ProtocolError(RuntimeError):
    pass


PROTOCOL = "arrhenius-current-no-lp-pilot-v3"
SELECTION_RULE = (
    "valid-costs-max-coverage-min-micro-par2-"
    "min-certified-image-time-label/v1"
)

MANIFEST = Path(__file__).with_name("ms_caps_pilot_suite.txt")
MANIFEST_DIGEST = (
    "c63a59ee2096b40c24f80db895ee2c0d22aabc2630c823b882e7f50f529a481b"
)
EXPECTED_TASKS = 50
EXPECTED_DOMAINS = 25

BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
BENCHMARK_REPOSITORY = "https://github.com/aibasel/downward-benchmarks.git"
# Keep the planner/cache identity independent of later protocol and cache-hash
# commits. Launch requires this commit to be an ancestor of clean protocol HEAD.
PLANNER_REVISION = "d889d1f73876592e1c91b7781a58affac6bf22f2"

# Fill this only after the explicit release_no_lp Lab cache has been built on
# an Arrhenius compute node, stripped by CachedFastDownwardRevision, inspected,
# and hashed.  None is an intentional launch gate, not a wildcard.
CACHE_BINARY_SHA256 = (
    "b0dac83910508b1089979ca7a16463cf2f3de72f30590af1c5e3c43dd4805d9e"
)


BASELINE_CONFIGS = [
    ("blind_fw", "sym_fw()"),
    (
        "ms_exact",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false)",
    ),
    (
        "ms_cap2",
        "sym_fw_ms(max_states=10000,value_cap=2,align_merge_order=false)",
    ),
    (
        "ms_cap4",
        "sym_fw_ms(max_states=10000,value_cap=4,align_merge_order=false)",
    ),
    (
        "ms_cap8",
        "sym_fw_ms(max_states=10000,value_cap=8,align_merge_order=false)",
    ),
    (
        "ms_cap16",
        "sym_fw_ms(max_states=10000,value_cap=16,align_merge_order=false)",
    ),
    (
        "ms_cap32",
        "sym_fw_ms(max_states=10000,value_cap=32,align_merge_order=false)",
    ),
    (
        "ms_exact_w4",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false,"
        "batch_f_window=4)",
    ),
    (
        "ms_exact_w16",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false,"
        "batch_f_window=16)",
    ),
    (
        "ms_cap32_w4",
        "sym_fw_ms(max_states=10000,value_cap=32,align_merge_order=false,"
        "batch_f_window=4)",
    ),
    (
        "ms_cap32_w16",
        "sym_fw_ms(max_states=10000,value_cap=32,align_merge_order=false,"
        "batch_f_window=16)",
    ),
    (
        "pdb_bdd_b100k",
        "sym_fw_pdb(budget=100000,goal_directed=false)",
    ),
    (
        "pdb_goal_b100k",
        "sym_fw_pdb(budget=100000,goal_directed=true)",
    ),
    (
        "pdb_goal_w16",
        "sym_fw_pdb(budget=100000,goal_directed=true,batch_f_window=16)",
    ),
]
BASELINE_CONFIGS_DIGEST = (
    "a2ff5aa8d4f49e3b85f2338a3fc7e2844536c5eb7d354d9989eb20b06bacca41"
)

# Reviewed current-revision candidates. The matrix deliberately isolates the
# two new ingredients (pattern synthesis and adaptive batching), their CEGAR
# combination, and a construction-budget safeguard for the strongest legacy
# heuristic. Six candidates is the hard maximum:
# (14 controls + 6 candidates) * 50 tasks = 1000 runs.
CANDIDATE_CONFIGS = [
    (
        "pdb_goal_fill_b100k",
        "sym_fw_pdb(budget=100000,pattern_selection=goal_fill)",
    ),
    (
        "pdb_cegar_b100k",
        "sym_fw_pdb(budget=100000,pattern_selection=cegar,"
        "cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "ms_exact_adapt_w64_r1_n1m",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false,"
        "batch_f_window=64,batch_max_union_ratio=1.0,"
        "batch_max_union_nodes=1000000)",
    ),
    (
        "ms_cap32_adapt_w64_r1_n1m",
        "sym_fw_ms(max_states=10000,value_cap=32,align_merge_order=false,"
        "batch_f_window=64,batch_max_union_ratio=1.0,"
        "batch_max_union_nodes=1000000)",
    ),
    (
        "pdb_cegar_adapt_w64_r1_n1m",
        "sym_fw_pdb(budget=100000,pattern_selection=cegar,"
        "cegar_max_time=10,cegar_seed=2011,batch_f_window=64,"
        "batch_max_union_ratio=1.0,batch_max_union_nodes=1000000)",
    ),
    (
        "ms_exact_budget30",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false,"
        "build_time_limit=30)",
    ),
]
CANDIDATE_CONFIGS_DIGEST = (
    "6a11f7651583680e4d4da6e06959cc2adbb2f92b2155f55e40f6f3c488b494c0"
)
MAX_CANDIDATE_CONFIGS = 6
MINIMUM_PILOT_RUNS = len(BASELINE_CONFIGS) * EXPECTED_TASKS


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate or run the fail-closed current-revision Arrhenius pilot."
        )
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Attest benchmark sources, matrix, cache state, and generated "
            "header without building or submitting."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run in-memory protocol tests without requiring benchmarks.",
    )
    parser.add_argument(
        "steps",
        nargs="*",
        help="Lab steps; build and start must be separate invocations.",
    )
    args = parser.parse_args(argv)
    if args.check and args.self_test:
        parser.error("--check and --self-test are mutually exclusive")
    if (args.check or args.self_test) and args.steps:
        parser.error("read-only checks cannot be combined with Lab steps")
    return args


def _sha256_configs(configs) -> str:
    payload = [
        {"label": label, "search": search} for label, search in configs
    ]
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
    ).hexdigest()


def read_manifest():
    tasks = []
    for raw_line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            fields = line.split(":")
            if len(fields) != 2 or not all(fields):
                raise ProtocolError(
                    "invalid domain:problem manifest entry {!r}".format(line)
                )
            tasks.append(line)
    payload = "".join("{}\n".format(task) for task in tasks)
    actual_digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if actual_digest != MANIFEST_DIGEST:
        raise ProtocolError(
            "pilot manifest digest changed: expected {}, got {}".format(
                MANIFEST_DIGEST, actual_digest
            )
        )
    if len(tasks) != EXPECTED_TASKS or len(set(tasks)) != EXPECTED_TASKS:
        raise ProtocolError(
            "pilot manifest must contain {} unique tasks".format(
                EXPECTED_TASKS
            )
        )
    domains = {task.partition(":")[0] for task in tasks}
    if len(domains) != EXPECTED_DOMAINS:
        raise ProtocolError(
            "pilot manifest must contain {} domains; got {}".format(
                EXPECTED_DOMAINS, len(domains)
            )
        )
    return tasks


def validate_config_matrix(tasks):
    baseline_digest = _sha256_configs(BASELINE_CONFIGS)
    if baseline_digest != BASELINE_CONFIGS_DIGEST:
        raise ProtocolError(
            "no-LP baseline matrix changed: expected {}, got {}".format(
                BASELINE_CONFIGS_DIGEST, baseline_digest
            )
        )
    candidate_digest = _sha256_configs(CANDIDATE_CONFIGS)
    if candidate_digest != CANDIDATE_CONFIGS_DIGEST:
        raise ProtocolError(
            "candidate matrix changed; review and pin digest {}".format(
                candidate_digest
            )
        )
    if len(BASELINE_CONFIGS) != 14:
        raise ProtocolError("baseline matrix must contain exactly 14 configs")
    if len(CANDIDATE_CONFIGS) > MAX_CANDIDATE_CONFIGS:
        raise ProtocolError(
            "at most {} candidate configs fit one Arrhenius array".format(
                MAX_CANDIDATE_CONFIGS
            )
        )

    configs = list(BASELINE_CONFIGS) + list(CANDIDATE_CONFIGS)
    labels = [label for label, _ in configs]
    searches = [search for _, search in configs]
    if len(labels) != len(set(labels)):
        raise ProtocolError("configuration labels must be unique")
    if len(searches) != len(set(searches)):
        raise ProtocolError("search expressions must be unique")
    for label, search in configs:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", label):
            raise ProtocolError("invalid configuration label {!r}".format(label))
        try:
            C.search_config(search)
        except ValueError as err:
            raise ProtocolError(
                "invalid search expression for {}: {}".format(label, err)
            ) from err
        lowered = search.lower()
        if any(
            forbidden in lowered
            for forbidden in ("lpsolver", "sym_fw_pot", "potential")
        ):
            raise ProtocolError(
                "no-LP pilot contains forbidden config {}={!r}".format(
                    label, search
                )
            )

    run_count = len(tasks) * len(configs)
    if run_count < MINIMUM_PILOT_RUNS:
        raise ProtocolError("pilot dropped a required baseline run")
    layout = C.validate_run_layout(
        run_count, require_one_run_per_array_task=True
    )
    return {
        "configs": configs,
        "baseline_digest": baseline_digest,
        "candidate_digest": candidate_digest,
        "matrix_digest": _sha256_configs(configs),
        "run_count": run_count,
        "layout": layout,
    }


def _git_output(repository: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as err:
        detail = (err.stderr or err.stdout or str(err)).strip()
        raise ProtocolError(
            "git check failed for {}: {}".format(repository, detail)
        ) from err


def _normalized_repository_url(url: str) -> str:
    return url.rstrip("/").removesuffix(".git")


def require_pinned_benchmark_worktree() -> Path:
    raw_root = os.environ.get("DOWNWARD_BENCHMARKS")
    if not raw_root:
        raise ProtocolError(
            "set DOWNWARD_BENCHMARKS to a dedicated benchmark worktree at {}".
            format(BENCHMARK_REVISION)
        )
    root = Path(raw_root).expanduser().resolve()
    if not root.is_dir():
        raise ProtocolError("benchmark worktree is not a directory: {}".format(root))
    top_level = Path(_git_output(root, "rev-parse", "--show-toplevel")).resolve()
    if top_level != root:
        raise ProtocolError(
            "DOWNWARD_BENCHMARKS must name the worktree root: {} != {}".
            format(root, top_level)
        )
    revision = _git_output(root, "rev-parse", "HEAD")
    if revision != BENCHMARK_REVISION:
        raise ProtocolError(
            "benchmark worktree is at {}, expected {}".format(
                revision, BENCHMARK_REVISION
            )
        )
    dirty = _git_output(root, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise ProtocolError(
            "benchmark worktree has tracked modifications:\n{}".format(dirty)
        )
    origin = _git_output(root, "remote", "get-url", "origin")
    if _normalized_repository_url(origin) != _normalized_repository_url(
        BENCHMARK_REPOSITORY
    ):
        raise ProtocolError(
            "benchmark origin is {!r}, expected {!r}".format(
                origin, BENCHMARK_REPOSITORY
            )
        )
    return root


def attest_task_sources(benchmark_root: Path, descriptions):
    resolved = suites.build_suite(str(benchmark_root), descriptions)
    by_description = {
        "{}:{}".format(task.domain, task.problem): task for task in resolved
    }
    if len(resolved) != len(descriptions) or len(by_description) != len(
        descriptions
    ):
        raise ProtocolError(
            "{} manifest entries resolved to {} tasks ({} unique)".format(
                len(descriptions), len(resolved), len(by_description)
            )
        )
    unsupported = sorted(
        set(by_description) - {
            "{}:{}".format(domain, problem)
            for domain, problem in suite_cost_manifest.supported_tasks()
        }
    )
    if unsupported:
        raise ProtocolError(
            "pilot manifest contains tasks outside the positive-cost, "
            "axiom-free supported population: {}".format(
                ", ".join(unsupported)
            )
        )
    ordered = []
    for description in descriptions:
        try:
            ordered.append(by_description[description])
        except KeyError as err:
            raise ProtocolError(
                "manifest task did not resolve: {}".format(description)
            ) from err
    task_sources_sha256 = suite_cost_manifest.validate_task_sources(
        (
            (
                task.domain,
                task.problem,
                Path(task.domain_file),
                Path(task.problem_file),
            )
            for task in ordered
        ),
        benchmark_root,
    )
    source_manifest_sha256 = suite_cost_manifest.sha256_file(
        suite_cost_manifest.MANIFEST_PATH
    )
    if source_manifest_sha256 != suite_cost_manifest.EXPECTED_MANIFEST_SHA256:
        raise ProtocolError("frozen source-manifest bytes changed")
    return {
        "task_sources_sha256": task_sources_sha256,
        "source_manifest_sha256": source_manifest_sha256,
    }


def validate_cache_pin(required=False) -> None:
    if CACHE_BINARY_SHA256 is None and not required:
        return
    if not isinstance(CACHE_BINARY_SHA256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", CACHE_BINARY_SHA256
    ):
        raise ProtocolError(
            "CACHE_BINARY_SHA256 must be the reviewed 64-digit cache hash"
        )


def make_protocol_metadata(matrix, benchmark_root, source_attestation):
    metadata = C.common_protocol_metadata(
        PLANNER_REVISION, CACHE_BINARY_SHA256, matrix["run_count"]
    )
    additions = {
        "protocol": PROTOCOL,
        "selection_rule": SELECTION_RULE,
        "task_manifest": MANIFEST.name,
        "task_manifest_sha256": MANIFEST_DIGEST,
        "task_count": EXPECTED_TASKS,
        "domain_count": EXPECTED_DOMAINS,
        "baseline_config_count": len(BASELINE_CONFIGS),
        "candidate_config_count": len(CANDIDATE_CONFIGS),
        "config_count": len(matrix["configs"]),
        "baseline_configs_sha256": matrix["baseline_digest"],
        "candidate_configs_sha256": matrix["candidate_digest"],
        "option_matrix_sha256": matrix["matrix_digest"],
        "benchmark_revision": BENCHMARK_REVISION,
        "benchmark_repository": BENCHMARK_REPOSITORY,
        "benchmark_worktree": str(benchmark_root),
        "source_manifest_sha256": source_attestation[
            "source_manifest_sha256"
        ],
        "task_sources_sha256": source_attestation["task_sources_sha256"],
    }
    overlap = set(metadata) & set(additions)
    if overlap:
        raise ProtocolError(
            "duplicate protocol metadata keys: {}".format(
                ", ".join(sorted(overlap))
            )
        )
    metadata.update(additions)
    C.validate_common_protocol_metadata(metadata)
    return metadata


def exact_header_assertions(job: str, num_runs: int):
    environment = C.get_environment()
    C.assert_exact_run_header(environment, job, num_runs)
    layout = C.validate_run_layout(num_runs)
    return [
        "#! /bin/bash",
        "#SBATCH --partition=cpu",
        "#SBATCH --qos=normal",
        "#SBATCH --time={}".format(C.SCHEDULER_TIME_LIMIT),
        "#SBATCH --mem-per-cpu={}".format(C.SCHEDULER_MEMORY_PER_CPU),
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --array=1-{}%{}".format(
            layout["array_tasks"], C.ARRAY_TASK_THROTTLE
        ),
        "#SBATCH --account={}".format(C.SCHEDULER_ACCOUNT),
    ]


def inspect_launch_blockers():
    """Return launch-gate failures without changing the worktree or cache."""
    checks = (
        (
            "committed planner/protocol revision",
            lambda: C.require_clean_committed_revision(
                PLANNER_REVISION, protocol_files=[Path(__file__)]
            ),
        ),
        ("requirements Lab version", C.require_pinned_lab_version),
        (
            "release_no_lp revision cache",
            lambda: C.require_revision_cache(
                PLANNER_REVISION, CACHE_BINARY_SHA256
            ),
        ),
    )
    blockers = []
    for label, check in checks:
        try:
            check()
        except RuntimeError as err:
            blockers.append(
                "{}: {}".format(label, str(err).replace("\n", " | "))
            )
    return blockers


def self_test():
    C.self_test_scheduler_headers()
    C.self_test_cofactor_width_parser()
    C.self_test_plan_file_parser()
    tasks = read_manifest()
    C.require_revision_ancestor_of_head(PLANNER_REVISION)
    matrix = validate_config_matrix(tasks)
    validate_cache_pin(required=False)
    _, job = C.make_in_memory_run_job(matrix["run_count"])
    expected_headers = exact_header_assertions(job, matrix["run_count"])
    job_lines = job.splitlines()
    for line in expected_headers:
        if job_lines.count(line) != 1:
            raise AssertionError(
                "generated job does not contain one exact {!r}".format(line)
            )
    if matrix["run_count"] != 1000 or matrix["layout"] != {
        "raw_runs": 1000,
        "array_tasks": 1000,
        "runs_per_array_task": 1,
        "scheduler_time_limit_seconds": 600,
    }:
        raise AssertionError(
            "prospective 20x50 layout changed: {!r}".format(matrix["layout"])
        )
    print(
        "Arrhenius pilot self-test: PASS "
        "({} tasks x {} configs = {} one-run array elements)".format(
            len(tasks), len(matrix["configs"]), matrix["run_count"]
        )
    )
    print("candidate configs SHA-256: {}".format(matrix["candidate_digest"]))
    print("exact generated header assertions:")
    for line in expected_headers:
        print("  " + line)


def check_protocol(tasks, matrix):
    benchmark_root = require_pinned_benchmark_worktree()
    source_attestation = attest_task_sources(benchmark_root, tasks)
    validate_cache_pin(required=False)
    cache_info = C.inspect_revision_cache(PLANNER_REVISION)
    launch_blockers = inspect_launch_blockers()
    _, job = C.make_in_memory_run_job(matrix["run_count"])
    expected_headers = exact_header_assertions(job, matrix["run_count"])

    print("Arrhenius pilot read-only check: PASS")
    print("planner revision: {}".format(PLANNER_REVISION))
    print("protocol revision: {}".format(C.REV))
    print("benchmark revision: {}".format(BENCHMARK_REVISION))
    print("benchmark worktree: {}".format(benchmark_root))
    print("task sources SHA-256: {}".format(
        source_attestation["task_sources_sha256"]
    ))
    print("source manifest SHA-256: {}".format(
        source_attestation["source_manifest_sha256"]
    ))
    print(
        "tasks: {}; configs: {} baseline + {} candidates; runs: {}".format(
            len(tasks),
            len(BASELINE_CONFIGS),
            len(CANDIDATE_CONFIGS),
            matrix["run_count"],
        )
    )
    print("option matrix SHA-256: {}".format(matrix["matrix_digest"]))
    print("revision cache: {}".format(cache_info["path"]))
    print("cached binary SHA-256: {}".format(cache_info["binary_sha256"]))
    if launch_blockers:
        print("launch gate: BLOCKED")
        for blocker in launch_blockers:
            print("  " + blocker)
    else:
        print("launch gate: READY")
    print("exact generated header assertions:")
    for line in expected_headers:
        print("  " + line)
    return benchmark_root, source_attestation


def main(argv=None):
    raw_args = list(sys.argv[1:] if argv is None else argv)
    C.reject_unsafe_combined_steps(raw_args)
    args = parse_args(raw_args)
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

    validate_cache_pin(required=True)
    benchmark_root = require_pinned_benchmark_worktree()
    source_attestation = attest_task_sources(benchmark_root, tasks)
    C.require_launch_prerequisites(
        PLANNER_REVISION,
        CACHE_BINARY_SHA256,
        args=args.steps,
        protocol_files=[Path(__file__)],
    )
    _, job = C.make_in_memory_run_job(matrix["run_count"])
    exact_header_assertions(job, matrix["run_count"])

    metadata = make_protocol_metadata(
        matrix, benchmark_root, source_attestation
    )
    experiment = C.new_experiment(metadata)
    C.add_suite(experiment, benchmark_root, tasks)
    for label, search in matrix["configs"]:
        C.add_algorithm(
            experiment, label, search, revision=PLANNER_REVISION
        )
    C.add_standard_steps(experiment)
    sys.argv = [sys.argv[0]] + args.steps
    experiment.run_steps()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ProtocolError, RuntimeError) as err:
        print("protocol error: {}".format(err), file=sys.stderr)
        sys.exit(2)
