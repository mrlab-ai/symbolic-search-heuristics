#!/usr/bin/env python3
"""Fail-closed exact-width-selector screening pilot for Arrhenius.

The checked-in matrix has five controls and fifteen exact-width-selector
configurations over the frozen 50-task screening manifest (1000 runs). Each
array element executes exactly one planner run in deterministic shuffled task
order.

The cached binary hash is pinned independently of the clean protocol HEAD,
which is recorded at launch and pinned later by the read-only analyzer.

Read-only checks::

    python experiments/exp_arrhenius_selector_pilot.py --self-test
    python experiments/exp_arrhenius_selector_pilot.py --check

After the candidate list, current revision, benchmark worktree, requirements,
and cache hash have been reviewed, keep build and submission separate::

    experiments/.venv/bin/python experiments/exp_arrhenius_selector_pilot.py build
    experiments/.venv/bin/python experiments/exp_arrhenius_selector_pilot.py start
    experiments/.venv/bin/python experiments/exp_arrhenius_selector_pilot.py parse fetch report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from downward import suites

import exp_arrhenius_common as C
import suite_cost_manifest


class ProtocolError(RuntimeError):
    pass


PROTOCOL = "arrhenius-exact-width-selector-screening-v1"
SELECTION_RULE = (
    "valid-costs-max-coverage-min-micro-par2-"
    "min-certified-image-time-label/v1"
)
PDB_SELECTOR_PARSER_PROTOCOL = C.PDB_SELECTOR_PARSER_PROTOCOL
EXPERIMENT_DATA_PATH = (
    Path(__file__).resolve().parent / "data" / Path(__file__).stem
)
PROTOCOL_FILES = (
    Path(__file__).resolve(),
    Path(C.__file__).resolve(),
    Path(__file__).with_name("wbh_parser.py").resolve(),
    Path(__file__).with_name("validate_wbh_log.py").resolve(),
    Path(__file__).with_name("selector_pilot_suite.txt").resolve(),
)

MANIFEST = Path(__file__).with_name("selector_pilot_suite.txt")
MANIFEST_DIGEST = (
    "3195dac7e62a34e5ac4cbeb715ab7f9b99e2ee64341082dd7d718ea2820751ca"
)
EXPECTED_TASK_SOURCES_SHA256 = (
    "dbb7730c257472c07f7946f0434949449169e06d1faa2174a92a6d13c48cb8ba"
)
EXPECTED_TASKS = 50
EXPECTED_DOMAINS = 25

BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
BENCHMARK_REPOSITORY = "https://github.com/aibasel/downward-benchmarks.git"
# Keep the planner/cache identity independent of later protocol and cache-hash
# commits. Launch requires this commit to be an ancestor of clean protocol HEAD.
PLANNER_REVISION = "8e56de8862c9449246596e779177cc9e6a7bcf8e"

# Reviewed, stripped ``release_no_lp`` Lab cache built on Arrhenius and hashed
# independently of the protocol commit.
CACHE_BINARY_SHA256 = (
    "21ea6aff991b4f8196ee8642ff0534bebae67ee3d13f3bd9c7f6f9b3b1fe8cb9"
)
CACHE_PREPROCESS_SHA256 = (
    "c62df391a1e760aa3c2f353056d1f63c8a9958d93c7f1dc4c12f98cc57e5f987"
)


CONTROL_CONFIGS = [
    ("blind_fw", "sym_fw()"),
    (
        "ms_exact",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false)",
    ),
    (
        "ms_cap32",
        "sym_fw_ms(max_states=10000,value_cap=32,align_merge_order=false)",
    ),
    (
        "pdb_goal_fill_b100k",
        "sym_fw_pdb(budget=100000,pattern_selection=goal_fill)",
    ),
    (
        "pdb_cegar_b100k",
        "sym_fw_pdb(budget=100000,pattern_selection=cegar,"
        "cegar_max_time=10,cegar_seed=2011)",
    ),
]
CONTROL_CONFIGS_DIGEST = (
    "ee40b07516ba1f2a3f562a2ec20f617e7eb1f742bf51aa67e9fb8db3d7ac9c89"
)

SELECTOR_CONFIGS = [
    (
        "pdb_selector_k1",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=1,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k2",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=2,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k4",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=4,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k8",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=8,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k16",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=16,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k32",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=32,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k64",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=64,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k128",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=128,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k256",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=256,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_kinf",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=infinity,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k32_adapt_w64_r1_n1m",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=32,cegar_max_time=10,cegar_seed=2011,"
        "batch_f_window=64,batch_max_union_ratio=1.0,"
        "batch_max_union_nodes=1000000)",
    ),
    (
        "pdb_selector_k64_adapt_w64_r1_n1m",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=64,cegar_max_time=10,cegar_seed=2011,"
        "batch_f_window=64,batch_max_union_ratio=1.0,"
        "batch_max_union_nodes=1000000)",
    ),
    (
        "pdb_selector_k128_adapt_w64_r1_n1m",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=128,cegar_max_time=10,cegar_seed=2011,"
        "batch_f_window=64,batch_max_union_ratio=1.0,"
        "batch_max_union_nodes=1000000)",
    ),
    (
        "pdb_selector_kinf_adapt_w64_r1_n1m",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=infinity,cegar_max_time=10,cegar_seed=2011,"
        "batch_f_window=64,batch_max_union_ratio=1.0,"
        "batch_max_union_nodes=1000000)",
    ),
    (
        "pdb_selector_k32_w16",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=32,cegar_max_time=10,cegar_seed=2011,"
        "batch_f_window=16)",
    ),
]
SELECTOR_CONFIGS_DIGEST = (
    "7d44b160de438b32c385e95d4b3b48df9433d9f1c42397b4be5341f3937edf92"
)
OPTION_MATRIX_SHA256 = (
    "e16f6e34af5101a3549bfbf98ebaba23371c645f9166c884bfdf07b3b65e7442"
)

FIXED_ENVIRONMENT = {
    "time_limit": "300s",
    "memory_limit": "8G",
    "build_options": ["release_no_lp"],
    "cache_build_name": "release_no_lp",
    "scheduler_cluster": "arrhenius",
    "scheduler_cpu_model": "AMD EPYC 9755 128-Core Processor",
    "scheduler_partition": "cpu",
    "scheduler_qos": "normal",
    "scheduler_account": "naiss2025-5-382-cpu",
    "scheduler_time_limit": "00:10:00",
    "scheduler_memory_per_cpu": "9G",
    "scheduler_cpus_per_task": 1,
    "array_task_throttle": 5,
    "max_array_tasks": 1000,
}

LAB_STEP_NAMES = ("build", "start", "parse", "fetch", "report")
LAB_STEP_ALIASES = {
    str(index): name for index, name in enumerate(LAB_STEP_NAMES, start=1)
}


def normalize_lab_steps(steps):
    """Return exact Lab step names, rejecting aliases that are ambiguous.

    Lab accepts any digit string as a one-based step index (including forms
    such as ``02``) and otherwise resolves names by prefix.  A launch protocol
    must not inherit either permissive behavior: only the five exact names and
    the canonical aliases ``1`` through ``5`` are accepted here.
    """
    normalized = []
    for raw_step in steps:
        if raw_step in LAB_STEP_NAMES:
            step = raw_step
        elif raw_step in LAB_STEP_ALIASES:
            step = LAB_STEP_ALIASES[raw_step]
        else:
            raise ProtocolError(
                "unknown Lab step {!r}; use one of {} or canonical aliases "
                "1..5".format(raw_step, ", ".join(LAB_STEP_NAMES))
            )
        if step in normalized:
            raise ProtocolError(
                "duplicate Lab step {!r} (possibly via a numeric alias)".
                format(step)
            )
        normalized.append(step)
    launch_steps = [step for step in ("build", "start") if step in normalized]
    if launch_steps and len(normalized) != 1:
        raise ProtocolError(
            "Arrhenius protocol step {!r} must run in its own invocation".
            format(launch_steps[0])
        )
    return normalized


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate or run the fail-closed selector-screening Arrhenius pilot."
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
        help="Lab steps; build and start must each run alone.",
    )
    args = parser.parse_args(argv)
    if args.check and args.self_test:
        parser.error("--check and --self-test are mutually exclusive")
    if (args.check or args.self_test) and args.steps:
        parser.error("read-only checks cannot be combined with Lab steps")
    args.steps = normalize_lab_steps(args.steps)
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


def validate_fixed_environment() -> None:
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
        "scheduler_time_limit": C.SCHEDULER_TIME_LIMIT,
        "scheduler_memory_per_cpu": C.SCHEDULER_MEMORY_PER_CPU,
        "scheduler_cpus_per_task": C.SCHEDULER_CPUS_PER_TASK,
        "array_task_throttle": C.ARRAY_TASK_THROTTLE,
        "max_array_tasks": C.MAX_ARRAY_TASKS,
    }
    if actual != FIXED_ENVIRONMENT:
        raise ProtocolError(
            "Arrhenius environment/limits differ from the frozen protocol: "
            "{}".format(actual)
        )


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
    validate_fixed_environment()
    control_digest = _sha256_configs(CONTROL_CONFIGS)
    if control_digest != CONTROL_CONFIGS_DIGEST:
        raise ProtocolError(
            "control matrix changed: expected {}, got {}".format(
                CONTROL_CONFIGS_DIGEST, control_digest
            )
        )
    selector_digest = _sha256_configs(SELECTOR_CONFIGS)
    if selector_digest != SELECTOR_CONFIGS_DIGEST:
        raise ProtocolError(
            "selector matrix changed: expected {}, got {}".format(
                SELECTOR_CONFIGS_DIGEST, selector_digest
            )
        )
    if len(CONTROL_CONFIGS) != 5 or len(SELECTOR_CONFIGS) != 15:
        raise ProtocolError(
            "matrix must contain exactly 5 controls + 15 selector configs"
        )

    configs = list(CONTROL_CONFIGS) + list(SELECTOR_CONFIGS)
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
                "no-LP selector screen contains forbidden config {}={!r}".format(
                    label, search
                )
            )

    matrix_digest = _sha256_configs(configs)
    if matrix_digest != OPTION_MATRIX_SHA256:
        raise ProtocolError(
            "combined option matrix changed: expected {}, got {}".format(
                OPTION_MATRIX_SHA256, matrix_digest
            )
        )
    run_count = len(tasks) * len(configs)
    if run_count != 1000:
        raise ProtocolError("selector screen must contain exactly 1000 runs")
    layout = C.validate_run_layout(
        run_count, require_one_run_per_array_task=True
    )
    return {
        "configs": configs,
        "control_digest": control_digest,
        "selector_digest": selector_digest,
        "matrix_digest": matrix_digest,
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


def _resolve_ordered_tasks(benchmark_root: Path, descriptions):
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
    ordered = []
    for description in descriptions:
        try:
            ordered.append(by_description[description])
        except KeyError as err:
            raise ProtocolError(
                "manifest task did not resolve: {}".format(description)
            ) from err
    _require_supported_tasks(ordered)
    return ordered


def attest_task_sources(benchmark_root: Path, descriptions):
    ordered = _resolve_ordered_tasks(benchmark_root, descriptions)
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
    if task_sources_sha256 != EXPECTED_TASK_SOURCES_SHA256:
        raise ProtocolError(
            "selector task-source bytes changed: expected {}, got {}".format(
                EXPECTED_TASK_SOURCES_SHA256, task_sources_sha256
            )
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


def _require_supported_tasks(tasks) -> None:
    supported = suite_cost_manifest.supported_tasks()
    rejected = sorted(
        (task.domain, task.problem)
        for task in tasks
        if (task.domain, task.problem) not in supported
    )
    if rejected:
        raise ProtocolError(
            "selector manifest contains unsupported (zero-cost or normalized-"
            "axiom) tasks: {}".format(
                ", ".join("{}:{}".format(*task) for task in rejected)
            )
        )


def validate_cache_pin(required=False) -> None:
    if CACHE_BINARY_SHA256 is None and not required:
        return
    if not isinstance(CACHE_BINARY_SHA256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", CACHE_BINARY_SHA256
    ):
        raise ProtocolError(
            "CACHE_BINARY_SHA256 must be the reviewed 64-digit cache hash"
        )
    if not isinstance(CACHE_PREPROCESS_SHA256, str) or not re.fullmatch(
        r"[0-9a-f]{64}", CACHE_PREPROCESS_SHA256
    ):
        raise ProtocolError(
            "CACHE_PREPROCESS_SHA256 must be the reviewed 64-digit cache hash"
        )


def require_selector_revision_cache():
    info = C.require_revision_cache(PLANNER_REVISION, CACHE_BINARY_SHA256)
    preprocessor = (
        Path(info["path"])
        / "builds"
        / C.CACHE_BUILD_NAME
        / "bin"
        / "preprocess"
    )
    preprocess_sha256 = _require_file_sha256(
        preprocessor,
        CACHE_PREPROCESS_SHA256,
        "revision-cache preprocess binary",
    )
    if not os.access(preprocessor, os.X_OK):
        raise ProtocolError(
            "revision-cache preprocess binary is not executable: {}".format(
                preprocessor
            )
        )
    return {**info, "preprocess_sha256": preprocess_sha256}


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
        "planner_preprocess_sha256": CACHE_PREPROCESS_SHA256,
        "experiment_data_directory": "data/exp_arrhenius_selector_pilot",
        "pdb_selector_parser_protocol": PDB_SELECTOR_PARSER_PROTOCOL,
        "selector_pool_protocol": C.PDB_SELECTOR_POOL_PROTOCOL,
        "selector_score_version": C.PDB_SELECTOR_SCORE_VERSION,
        "selector_source_order": list(C.PDB_SELECTOR_SOURCES),
        "selector_width_budgets": [
            1, 2, 4, 8, 16, 32, 64, 128, 256, "infinity"
        ],
        "selector_state_budget": 100000,
        "selector_cegar_max_time": 10,
        "selector_cegar_seed": 2011,
        "selector_dynamic_reordering": False,
        "selector_adaptive_f_window": 64,
        "selector_adaptive_max_union_ratio": 1.0,
        "selector_adaptive_max_union_nodes": 1000000,
        "selector_static_f_window": 16,
        "control_config_count": len(CONTROL_CONFIGS),
        "selector_config_count": len(SELECTOR_CONFIGS),
        "config_count": len(matrix["configs"]),
        "control_configs_sha256": matrix["control_digest"],
        "selector_configs_sha256": matrix["selector_digest"],
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_regular_file(path: Path, label: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ProtocolError(
            "{} must be one regular non-symlink file: {}".format(label, path)
        )


def _require_file_sha256(path: Path, expected: str, label: str) -> str:
    _require_regular_file(path, label)
    actual = _sha256_file(path)
    if actual != expected:
        raise ProtocolError(
            "{} SHA-256 changed: expected {}, got {} ({})".format(
                label, expected, actual, path
            )
        )
    return actual


def _load_json_object(path: Path, label: str):
    _require_regular_file(path, label)

    def reject_duplicate_keys(pairs):
        counts = Counter(key for key, _ in pairs)
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        if duplicates:
            raise ProtocolError(
                "{} has duplicate JSON keys: {}".format(
                    label, ", ".join(duplicates)
                )
            )
        return dict(pairs)

    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as err:
        raise ProtocolError("cannot read {} {}: {}".format(label, path, err)) from err
    if not isinstance(value, dict):
        raise ProtocolError("{} must be a JSON object: {}".format(label, path))
    return value


def _require_exact_mapping(actual, expected, label: str) -> None:
    if not isinstance(actual, dict):
        raise ProtocolError("{} must be a mapping".format(label))
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatches = [
        (key, actual[key], expected[key])
        for key in sorted(set(actual) & set(expected))
        if actual[key] != expected[key]
    ]
    if missing or extra or mismatches:
        details = []
        if missing:
            details.append("missing={}".format(missing))
        if extra:
            details.append("extra={}".format(extra))
        details.extend(
            "{}={!r}, expected {!r}".format(key, got, wanted)
            for key, got, wanted in mismatches[:8]
        )
        if len(mismatches) > 8:
            details.append(
                "{} additional value mismatches".format(len(mismatches) - 8)
            )
        raise ProtocolError("{} mismatch: {}".format(label, "; ".join(details)))


def _run_relative_path(run_id: int) -> Path:
    lower = ((run_id - 1) // 100) * 100 + 1
    upper = ((run_id + 99) // 100) * 100
    return Path("runs-{:05d}-{:05d}".format(lower, upper)) / "{:05d}".format(
        run_id
    )


def _require_pristine_run_directory(run_dir: Path, run_id: int) -> None:
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ProtocolError(
            "missing regular run directory {}".format(run_dir)
        )
    expected_entries = {
        "domain.pddl",
        "problem.pddl",
        "run",
        "static-properties",
    }
    actual_entries = {path.name for path in run_dir.iterdir()}
    if actual_entries != expected_entries:
        raise ProtocolError(
            "run {} is not pristine: expected {}, got {}".format(
                run_id, sorted(expected_entries), sorted(actual_entries)
            )
        )


def _expected_static_properties(
    metadata, label: str, search: str, task, run_id: int
):
    generated = {
        "id": [label, task.domain, task.problem],
        "algorithm": label,
        "domain": task.domain,
        "problem": task.problem,
        "repo": str(C.REPO),
        "local_revision": PLANNER_REVISION,
        "global_revision": PLANNER_REVISION,
        "build_options": list(C.BUILD_OPTIONS),
        "driver_options": list(C.LAB_DEFAULT_DRIVER_PREFIX[1:])
        + [
            "--build",
            C.CACHE_BUILD_NAME,
            "--overall-time-limit",
            C.TIME_LIMIT,
            "--overall-memory-limit",
            C.MEMORY_LIMIT,
        ],
        "component_options": ["--search", C.search_config(search)],
        "experiment_name": Path(__file__).stem,
        "run_dir": _run_relative_path(run_id).as_posix(),
    }
    overlap = set(metadata) & set(generated)
    if overlap:
        raise ProtocolError(
            "protocol metadata overlaps Lab cell fields: {}".format(
                ", ".join(sorted(overlap))
            )
        )
    return {**generated, **metadata}


def _expected_run_script(argv) -> str:
    """Render the exact Lab 8.0 run wrapper reviewed by this protocol."""
    template = '''#! /usr/bin/env python

import logging
import os
import platform

from lab.calls.call import Call
from lab import tools

tools.configure_logging()

logging.info(f"node: {platform.node()}")

run_log = open("run.log", "w")
run_err = open("run.err", "w", buffering=1)  # line buffering
redirects = {"stdout": run_log, "stderr": run_err}

# Make sure we're in the run directory.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

Call(__ARGV__, hard_stderr_limit=10240, hard_stdout_limit=10240, memory_limit=None, name='planner', soft_stderr_limit=64, soft_stdout_limit=1024, time_limit=None, **redirects).wait()


for f in [run_log, run_err]:
    f.close()
    if os.path.getsize(f.name) == 0:
        os.remove(f.name)
'''
    return template.replace("__ARGV__", repr(argv))


def _git_tree_python_files(revision: str, prefix: str):
    try:
        output = subprocess.run(
            [
                "git",
                "-C",
                str(C.REPO),
                "ls-tree",
                "-r",
                "--name-only",
                revision,
                "--",
                prefix,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError as err:
        detail = (err.stderr or err.stdout or str(err)).strip()
        raise ProtocolError(
            "cannot enumerate runtime sources at {}: {}".format(
                revision, detail
            )
        ) from err
    return sorted(
        line for line in output.splitlines() if line.endswith(".py")
    )


def _git_blob(revision: str, relative: str) -> bytes:
    try:
        return subprocess.run(
            ["git", "-C", str(C.REPO), "show", "{}:{}".format(revision, relative)],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as err:
        detail = err.stderr.decode("utf-8", errors="replace").strip()
        raise ProtocolError(
            "cannot read reviewed runtime source {}:{}: {}".format(
                revision, relative, detail
            )
        ) from err


def _attest_runtime_tree(code_dir: Path) -> None:
    """Bind all Python runtime components to the planner Git revision."""
    reviewed_root_files = ("fast-downward.py", "build_configs.py")
    for relative in reviewed_root_files:
        actual_path = code_dir / relative
        _require_regular_file(actual_path, "copied runtime source")
        if actual_path.read_bytes() != _git_blob(PLANNER_REVISION, relative):
            raise ProtocolError(
                "copied runtime source differs from {}: {}".format(
                    PLANNER_REVISION, actual_path
                )
            )

    expected_driver = _git_tree_python_files(PLANNER_REVISION, "driver")
    actual_driver = sorted(
        path.relative_to(code_dir).as_posix()
        for path in (code_dir / "driver").rglob("*.py")
        if "__pycache__" not in path.parts
    )
    if actual_driver != expected_driver:
        raise ProtocolError(
            "copied driver Python file set differs from planner revision"
        )
    for relative in expected_driver:
        actual_path = code_dir / relative
        _require_regular_file(actual_path, "copied driver source")
        if actual_path.read_bytes() != _git_blob(PLANNER_REVISION, relative):
            raise ProtocolError(
                "copied driver source differs from {}: {}".format(
                    PLANNER_REVISION, relative
                )
            )

    expected_translator_sources = _git_tree_python_files(
        PLANNER_REVISION, "src/translate"
    )
    expected_translator = [
        relative.removeprefix("src/")
        for relative in expected_translator_sources
    ]
    translator_root = (
        code_dir / "builds" / C.CACHE_BUILD_NAME / "bin" / "translate"
    )
    actual_translator = sorted(
        path.relative_to(translator_root.parent).as_posix()
        for path in translator_root.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    if actual_translator != expected_translator:
        raise ProtocolError(
            "copied translator Python file set differs from planner revision"
        )
    for source_relative, built_relative in zip(
        expected_translator_sources, expected_translator
    ):
        actual_path = translator_root.parent / built_relative
        _require_regular_file(actual_path, "copied translator source")
        if actual_path.read_bytes() != _git_blob(
            PLANNER_REVISION, source_relative
        ):
            raise ProtocolError(
                "copied translator source differs from {}: {}".format(
                    PLANNER_REVISION, source_relative
                )
            )


def _make_expected_grid_job(grid_path: Path, num_runs: int) -> str:
    class FakeBuildStep:
        name = "build"
        _funcname = "build"

    class FakeStartStep:
        name = "start"
        _funcname = "start_runs"

    class FakeExperiment:
        name = grid_path.name
        path = str(grid_path)

        def __init__(self):
            self.runs = [None] * num_runs
            self.steps = [FakeBuildStep(), FakeStartStep()]

    environment = C.get_environment()
    environment.exp = FakeExperiment()
    environment.job_dir = grid_path.parent / "{}-grid-steps".format(
        grid_path.name
    )
    return environment._get_job(environment.exp.steps[1], True)


def _attest_fresh_start_job(grid_path: Path, num_runs: int):
    """Certify Lab's prospective start job and reject any resubmission state."""
    job_dir = grid_path.parent / "{}-grid-steps".format(grid_path.name)
    if job_dir.exists() or job_dir.is_symlink():
        raise ProtocolError(
            "refusing start because the grid-steps directory already exists: "
            "{}".format(job_dir)
        )
    eval_dir = Path(str(grid_path) + "-eval")
    if eval_dir.exists() or eval_dir.is_symlink():
        raise ProtocolError(
            "refusing start because the evaluation directory already exists: "
            "{}".format(eval_dir)
        )
    expected_job = _make_expected_grid_job(grid_path, num_runs)
    exact_header_assertions(expected_job, num_runs)
    return expected_job, hashlib.sha256(
        expected_job.encode("utf-8")
    ).hexdigest()


def attest_existing_start_grid(
    metadata, benchmark_root: Path, task_descriptions, matrix
):
    """Fail closed unless the already-built grid is exactly launchable."""
    grid_path = EXPERIMENT_DATA_PATH
    if grid_path.is_symlink() or not grid_path.is_dir():
        raise ProtocolError(
            "start requires an existing regular experiment grid: {}".format(
                grid_path
            )
        )

    expected_experiment_properties = {
        "algorithms": [label for label, _ in matrix["configs"]],
        "experiment_file": Path(__file__).name,
        "runs": matrix["run_count"],
        "suite": {str(benchmark_root): list(task_descriptions)},
    }
    experiment_properties = _load_json_object(
        grid_path / "static-experiment-properties",
        "static experiment properties",
    )
    _require_exact_mapping(
        experiment_properties,
        expected_experiment_properties,
        "static experiment properties",
    )

    cache_name = metadata["planner_revision_cache_name"]
    expected_code_name = "code-{}".format(cache_name)
    code_entries = sorted(
        path.name for path in grid_path.iterdir() if path.name.startswith("code-")
    )
    if code_entries != [expected_code_name]:
        raise ProtocolError(
            "grid must contain exactly one copied code directory {!r}; got {}".
            format(expected_code_name, code_entries)
        )
    code_dir = grid_path / expected_code_name
    if code_dir.is_symlink() or not code_dir.is_dir():
        raise ProtocolError(
            "copied code entry must be a regular directory: {}".format(code_dir)
        )
    _require_file_sha256(
        code_dir / "build_successful",
        C.CACHE_SENTINEL_SHA256,
        "copied cache success sentinel",
    )
    binary_path = (
        code_dir / "builds" / C.CACHE_BUILD_NAME / "bin" / "downward"
    )
    binary_sha256 = _require_file_sha256(
        binary_path, CACHE_BINARY_SHA256, "copied planner binary"
    )
    if not os.access(binary_path, os.X_OK):
        raise ProtocolError(
            "copied planner binary is not executable: {}".format(binary_path)
        )
    preprocess_path = (
        code_dir / "builds" / C.CACHE_BUILD_NAME / "bin" / "preprocess"
    )
    preprocess_sha256 = _require_file_sha256(
        preprocess_path,
        CACHE_PREPROCESS_SHA256,
        "copied preprocess binary",
    )
    if not os.access(preprocess_path, os.X_OK):
        raise ProtocolError(
            "copied preprocess binary is not executable: {}".format(
                preprocess_path
            )
        )
    _attest_runtime_tree(code_dir)

    ordered_tasks = _resolve_ordered_tasks(benchmark_root, task_descriptions)
    configs = matrix["configs"]
    expected_run_groups = {
        _run_relative_path(run_id).parent.name
        for run_id in range(1, matrix["run_count"] + 1)
    }
    actual_run_groups = {
        path.name
        for path in grid_path.iterdir()
        if path.name.startswith("runs-")
    }
    if actual_run_groups != expected_run_groups:
        raise ProtocolError(
            "run-group directories differ: expected {}, got {}".format(
                sorted(expected_run_groups), sorted(actual_run_groups)
            )
        )
    expected_grid_entries = expected_run_groups | {
        expected_code_name,
        "static-experiment-properties",
    }
    actual_grid_entries = {path.name for path in grid_path.iterdir()}
    if actual_grid_entries != expected_grid_entries:
        raise ProtocolError(
            "experiment-grid entries differ: expected {}, got {}".format(
                sorted(expected_grid_entries), sorted(actual_grid_entries)
            )
        )

    expected_static_paths = {
        grid_path / _run_relative_path(run_id) / "static-properties"
        for run_id in range(1, matrix["run_count"] + 1)
    }
    actual_static_paths = set(grid_path.glob("runs-*/*/static-properties"))
    if actual_static_paths != expected_static_paths:
        raise ProtocolError(
            "grid must contain exactly {} static-properties files; got {}".
            format(len(expected_static_paths), len(actual_static_paths))
        )

    seen_ids = set()
    for config_index, (label, search) in enumerate(configs):
        for task_index, task in enumerate(ordered_tasks):
            run_id = config_index * len(ordered_tasks) + task_index + 1
            run_relative = _run_relative_path(run_id)
            run_dir = grid_path / run_relative
            _require_pristine_run_directory(run_dir, run_id)
            properties = _load_json_object(
                run_dir / "static-properties",
                "static properties for run {}".format(run_id),
            )
            expected_properties = _expected_static_properties(
                metadata, label, search, task, run_id
            )
            _require_exact_mapping(
                properties,
                expected_properties,
                "static properties for run {}".format(run_id),
            )
            cell_id = tuple(properties["id"])
            if cell_id in seen_ids:
                raise ProtocolError(
                    "duplicate static cell identity: {}".format(cell_id)
                )
            seen_ids.add(cell_id)

            for link_name, source in (
                ("domain.pddl", Path(task.domain_file).resolve()),
                ("problem.pddl", Path(task.problem_file).resolve()),
            ):
                link = run_dir / link_name
                if not link.is_symlink() or not link.exists():
                    raise ProtocolError(
                        "run {} {} must be a live PDDL symlink".format(
                            run_id, link_name
                        )
                    )
                if link.resolve() != source or not link.samefile(source):
                    raise ProtocolError(
                        "run {} {} targets {}, expected {}".format(
                            run_id, link_name, link.resolve(), source
                        )
                    )

            argv = [
                sys.executable,
                str(code_dir / "fast-downward.py"),
                *expected_properties["driver_options"],
                "domain.pddl",
                "problem.pddl",
                *expected_properties["component_options"],
            ]
            run_script = run_dir / "run"
            _require_regular_file(run_script, "run wrapper")
            try:
                actual_script = run_script.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as err:
                raise ProtocolError(
                    "cannot read run wrapper {}: {}".format(run_script, err)
                ) from err
            expected_script = _expected_run_script(argv)
            if actual_script != expected_script:
                raise ProtocolError(
                    "run {} wrapper differs from the reviewed Lab 8.0 "
                    "template/options".format(run_id)
                )

    if len(seen_ids) != matrix["run_count"]:
        raise ProtocolError(
            "grid has {} unique cell identities; expected {}".format(
                len(seen_ids), matrix["run_count"]
            )
        )
    for group_name in sorted(expected_run_groups):
        group = grid_path / group_name
        if group.is_symlink() or not group.is_dir():
            raise ProtocolError("invalid run-group directory {}".format(group))
        expected_children = {
            _run_relative_path(run_id).name
            for run_id in range(1, matrix["run_count"] + 1)
            if _run_relative_path(run_id).parent.name == group_name
        }
        actual_children = {path.name for path in group.iterdir()}
        if actual_children != expected_children:
            raise ProtocolError(
                "run directories in {} differ from exact grid".format(group_name)
            )

    # Lab 8 renders this job inside SlurmEnvironment.run_steps(), immediately
    # before submission. Certify that deterministic rendering in advance and
    # require pristine resubmission state.
    _, expected_job_sha256 = _attest_fresh_start_job(
        grid_path, matrix["run_count"]
    )

    return {
        "grid_path": str(grid_path),
        "run_count": len(seen_ids),
        "code_directory": expected_code_name,
        "binary_sha256": binary_sha256,
        "preprocess_sha256": preprocess_sha256,
        "job_sha256": expected_job_sha256,
    }


def inspect_launch_blockers():
    """Return launch-gate failures without changing the worktree or cache."""
    checks = (
        (
            "committed planner/protocol revision",
            lambda: C.require_clean_committed_revision(
                PLANNER_REVISION,
                protocol_files=PROTOCOL_FILES,
            ),
        ),
        ("requirements Lab version", C.require_pinned_lab_version),
        (
            "release_no_lp revision cache",
            require_selector_revision_cache,
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


def _expect_protocol_error(function, expected_fragment: str) -> None:
    try:
        function()
    except ProtocolError as err:
        if expected_fragment not in str(err):
            raise AssertionError(
                "expected protocol error containing {!r}, got {!r}".format(
                    expected_fragment, str(err)
                )
            ) from err
    else:
        raise AssertionError(
            "expected protocol error containing {!r}".format(expected_fragment)
        )


def self_test_start_preflight_helpers() -> None:
    if normalize_lab_steps(["parse", "4", "report"]) != [
        "parse",
        "fetch",
        "report",
    ]:
        raise AssertionError("read-only Lab step normalization changed")
    _expect_protocol_error(
        lambda: normalize_lab_steps(["start", "2"]), "duplicate Lab step"
    )
    _expect_protocol_error(
        lambda: normalize_lab_steps(["start", "start"]),
        "duplicate Lab step",
    )
    _expect_protocol_error(
        lambda: normalize_lab_steps(["build", "start"]),
        "must run in its own invocation",
    )
    _expect_protocol_error(
        lambda: normalize_lab_steps(["start", "parse"]),
        "must run in its own invocation",
    )
    _expect_protocol_error(
        lambda: normalize_lab_steps(["build", "report"]),
        "must run in its own invocation",
    )
    _expect_protocol_error(
        lambda: normalize_lab_steps(["02"]), "unknown Lab step"
    )

    expected_static = {
        "protocol_revision": "a" * 40,
        "algorithm": "selector",
        "component_options": ["--search", "exact"],
    }
    stale = dict(expected_static, protocol_revision="b" * 40)
    _expect_protocol_error(
        lambda: _require_exact_mapping(
            stale, expected_static, "synthetic stale protocol"
        ),
        "protocol_revision=",
    )
    changed_static = dict(expected_static, component_options=["--search", "blind"])
    _expect_protocol_error(
        lambda: _require_exact_mapping(
            changed_static, expected_static, "synthetic changed static property"
        ),
        "component_options=",
    )

    with tempfile.TemporaryDirectory(prefix="selector-grid-preflight-") as raw:
        temporary_root = Path(raw)
        copied_binary = temporary_root / "downward"
        copied_binary.write_bytes(b"reviewed copied planner")
        expected_hash = hashlib.sha256(copied_binary.read_bytes()).hexdigest()
        _require_file_sha256(
            copied_binary, expected_hash, "synthetic copied planner"
        )
        copied_binary.write_bytes(b"changed copied planner")
        _expect_protocol_error(
            lambda: _require_file_sha256(
                copied_binary, expected_hash, "synthetic copied planner"
            ),
            "SHA-256 changed",
        )
        fresh_grid = temporary_root / "fresh-grid"
        fresh_grid.mkdir()
        prospective_job, prospective_hash = _attest_fresh_start_job(
            fresh_grid, 1000
        )
        if hashlib.sha256(prospective_job.encode("utf-8")).hexdigest() != (
            prospective_hash
        ):
            raise AssertionError("prospective start-job hash changed")
        stale_job_dir = fresh_grid.parent / "fresh-grid-grid-steps"
        stale_job_dir.mkdir()
        _expect_protocol_error(
            lambda: _attest_fresh_start_job(fresh_grid, 1000),
            "grid-steps directory already exists",
        )
        second_fresh_grid = temporary_root / "second-fresh-grid"
        second_fresh_grid.mkdir()
        Path(str(second_fresh_grid) + "-eval").mkdir()
        _expect_protocol_error(
            lambda: _attest_fresh_start_job(second_fresh_grid, 1000),
            "evaluation directory already exists",
        )
        pristine_run = temporary_root / "run-directory"
        pristine_run.mkdir()
        for name in ("domain.pddl", "problem.pddl", "run", "static-properties"):
            (pristine_run / name).write_bytes(b"synthetic")
        _require_pristine_run_directory(pristine_run, 1)
        (pristine_run / "driver.log").write_bytes(b"stale")
        _expect_protocol_error(
            lambda: _require_pristine_run_directory(pristine_run, 1),
            "is not pristine",
        )

    unsupported = SimpleNamespace(
        domain="definitely-not-a-suite-domain",
        problem="unsupported.pddl",
    )
    _expect_protocol_error(
        lambda: _require_supported_tasks([unsupported]), "unsupported"
    )
    print(
        "selector start-preflight helper self-tests: PASS "
        "(steps; stale protocol/static; copied binary; supported tasks)"
    )


def self_test():
    C.self_test_scheduler_headers()
    C.self_test_cofactor_width_parser()
    C.self_test_pdb_selector_parser()
    C.self_test_plan_file_parser()
    tasks = read_manifest()
    C.require_revision_ancestor_of_head(PLANNER_REVISION)
    matrix = validate_config_matrix(tasks)
    validate_cache_pin(required=False)
    prospective_metadata = make_protocol_metadata(
        matrix,
        C.REPO,
        {
            "source_manifest_sha256": (
                suite_cost_manifest.EXPECTED_MANIFEST_SHA256
            ),
            "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
        },
    )
    if prospective_metadata.get("protocol_revision") != C.REV:
        raise AssertionError("prospective metadata does not bind current HEAD")
    if (
        prospective_metadata.get("planner_preprocess_sha256")
        != CACHE_PREPROCESS_SHA256
    ):
        raise AssertionError("prospective metadata omits preprocess provenance")
    self_test_start_preflight_helpers()
    original_git_output = C._git_output

    def simulated_dirty_git_output(*args):
        if args == ("status", "--porcelain", "--untracked-files=no"):
            return " M experiments/exp_arrhenius_common.py"
        return original_git_output(*args)

    C._git_output = simulated_dirty_git_output
    try:
        try:
            C.require_clean_committed_revision(
                PLANNER_REVISION,
                protocol_files=PROTOCOL_FILES,
            )
        except RuntimeError as err:
            if "clean tracked worktree" not in str(err):
                raise
        else:
            raise AssertionError("simulated dirty protocol launch was accepted")
    finally:
        C._git_output = original_git_output

    runner_relative = Path(__file__).resolve().relative_to(C.REPO).as_posix()
    manifest_relative = MANIFEST.resolve().relative_to(C.REPO).as_posix()
    for simulated_uncommitted in (runner_relative, manifest_relative):
        def simulated_uncommitted_git_output(*args):
            if args == ("status", "--porcelain", "--untracked-files=no"):
                return ""
            if args[:3] == ("ls-files", "--error-unmatch", "--"):
                relative = args[3]
                if relative == simulated_uncommitted:
                    raise subprocess.CalledProcessError(1, ["git", *args])
                return relative
            return original_git_output(*args)

        C._git_output = simulated_uncommitted_git_output
        try:
            try:
                C.require_clean_committed_revision(
                    PLANNER_REVISION,
                    protocol_files=PROTOCOL_FILES,
                )
            except RuntimeError as err:
                if (
                    "must be committed" not in str(err)
                    or simulated_uncommitted not in str(err)
                ):
                    raise
            else:
                raise AssertionError(
                    "simulated uncommitted protocol file was accepted: {}".
                    format(simulated_uncommitted)
                )
        finally:
            C._git_output = original_git_output
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
        "Arrhenius selector pilot self-test: PASS "
        "({} tasks x {} configs = {} one-run array elements)".format(
            len(tasks), len(matrix["configs"]), matrix["run_count"]
        )
    )
    print("control configs SHA-256: {}".format(matrix["control_digest"]))
    print("selector configs SHA-256: {}".format(matrix["selector_digest"]))
    print("option matrix SHA-256: {}".format(matrix["matrix_digest"]))
    print("exact generated header assertions:")
    for line in expected_headers:
        print("  " + line)


def check_protocol(tasks, matrix):
    benchmark_root = require_pinned_benchmark_worktree()
    source_attestation = attest_task_sources(benchmark_root, tasks)
    validate_cache_pin(required=False)
    cache_info = C.inspect_revision_cache(PLANNER_REVISION)
    cached_preprocessor = (
        Path(cache_info["path"])
        / "builds"
        / C.CACHE_BUILD_NAME
        / "bin"
        / "preprocess"
    )
    cached_preprocess_sha256 = (
        _sha256_file(cached_preprocessor)
        if cached_preprocessor.is_file()
        else None
    )
    launch_blockers = inspect_launch_blockers()
    _, job = C.make_in_memory_run_job(matrix["run_count"])
    expected_headers = exact_header_assertions(job, matrix["run_count"])

    print("Arrhenius selector pilot read-only check: PASS")
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
        "tasks: {}; configs: {} controls + {} selectors; runs: {}".format(
            len(tasks),
            len(CONTROL_CONFIGS),
            len(SELECTOR_CONFIGS),
            matrix["run_count"],
        )
    )
    print("option matrix SHA-256: {}".format(matrix["matrix_digest"]))
    print("revision cache: {}".format(cache_info["path"]))
    print("cached binary SHA-256: {}".format(cache_info["binary_sha256"]))
    print("cached preprocess SHA-256: {}".format(cached_preprocess_sha256))
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
    cache_info = C.require_launch_prerequisites(
        PLANNER_REVISION,
        CACHE_BINARY_SHA256,
        args=args.steps,
        protocol_files=PROTOCOL_FILES,
    )
    if cache_info is not None:
        require_selector_revision_cache()
    _, job = C.make_in_memory_run_job(matrix["run_count"])
    exact_header_assertions(job, matrix["run_count"])

    metadata = make_protocol_metadata(
        matrix, benchmark_root, source_attestation
    )
    if "start" in args.steps:
        attestation = attest_existing_start_grid(
            metadata, benchmark_root, tasks, matrix
        )
        print(
            "start grid attestation: PASS ({} runs; binary {}; preprocess {}; "
            "job {})".
            format(
                attestation["run_count"],
                attestation["binary_sha256"],
                attestation["preprocess_sha256"],
                attestation["job_sha256"],
            )
        )
    experiment = C.new_experiment(metadata)
    if Path(experiment.path).resolve() != EXPERIMENT_DATA_PATH:
        raise ProtocolError(
            "experiment data path changed: {} != {}".format(
                Path(experiment.path).resolve(), EXPERIMENT_DATA_PATH
            )
        )
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
