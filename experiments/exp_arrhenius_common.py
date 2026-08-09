"""Shared, fail-closed support for prospective Arrhenius experiments.

This module is deliberately separate from :mod:`exp_common`, which freezes the
Tetralith protocol used by earlier experiments.  It never compiles a planner:
prospective ``build`` and ``start`` steps require a pre-existing, hash-pinned
``release_no_lp`` Downward Lab revision cache.

Run the in-memory scheduler compatibility tests with::

    python experiments/exp_arrhenius_common.py

The tests write no experiment files and submit no jobs.
"""

from __future__ import annotations

import hashlib
import importlib.metadata
import math
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

from downward.cached_revision import CachedFastDownwardRevision
from downward.experiment import FastDownwardExperiment
from downward.reports.absolute import AbsoluteReport
from lab import tools
from lab.environments import SlurmEnvironment, is_run_step
from lab.parser import Parser

import wbh_parser


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
REQUIREMENTS = SCRIPT_DIR / "requirements.txt"
REVISION_CACHE = Path(
    os.environ.get(
        "DOWNWARD_REVISION_CACHE", str(SCRIPT_DIR / "data" / "revision-cache")
    )
).resolve()

REV = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()

# Planner and scheduler limits for the preliminary screens.
TIME_LIMIT = "300s"
TIME_LIMIT_SECONDS = 300
MEMORY_LIMIT = "8G"
BUILD_OPTIONS = ["release_no_lp"]
CACHE_BUILD_NAME = "release_no_lp"
CACHE_SENTINEL_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)

# Arrhenius CPU nodes are homogeneous AMD EPYC 9755 nodes.  MAX_TASKS follows
# Slurm's MaxArraySize=1001: Lab uses one-based array indices, hence at most
# 1000 array elements.
SCHEDULER_CLUSTER = "arrhenius"
SCHEDULER_CPU_MODEL = "AMD EPYC 9755 128-Core Processor"
SCHEDULER_PARTITION = "cpu"
SCHEDULER_QOS = "normal"
SCHEDULER_ACCOUNT = os.environ.get(
    "WBH_ACCOUNT", "naiss2025-5-382-cpu"
)
SCHEDULER_TIME_LIMIT = os.environ.get("WBH_TASK_TIME", "00:10:00")
SCHEDULER_MEMORY_PER_CPU = os.environ.get("WBH_MEMORY_PER_CPU", "9G")
SCHEDULER_CPUS_PER_TASK = 1
ARRAY_TASK_THROTTLE = 5
MAX_ARRAY_TASKS = 1000
SCHEDULER_WRAPPER_ALLOWANCE_SECONDS = 60

TASK_ORDER_SEED = "symbolic-search-heuristics/arrhenius-task-order/v1"
TASK_ORDER_METHOD = (
    "sha256(seed-nul-array-count-nul-array-id)-sort;"
    "ascending-run-id-within-array-task/v1"
)
WBH_LOG = "wbh.jsonl"
COFACTOR_WIDTH_PROPERTY = "cofactor_width"
COFACTOR_WIDTH_PARSER_PROTOCOL = (
    "run.log/unique-wbh-heuristic-cofactor-width/v1"
)

_SLURM_ARRAY_DIRECTIVE = "#SBATCH --array="
_RANDOM_RUN_LOOP = (
    "for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID | shuf); do"
)
_DETERMINISTIC_RUN_LOOP = (
    "for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID); do"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WBH_HEURISTIC_LINE_RE = re.compile(
    r"^\[t=\d+\.\d{6}s, \d+ KB\] "
    r"wbh [^:\r\n]+ heuristic:[^\r\n]*$",
    re.MULTILINE,
)
_ANY_WBH_HEURISTIC_LINE_RE = re.compile(
    r"^[^\r\n]*\bwbh [^:\r\n]+ heuristic:[^\r\n]*$", re.MULTILINE
)
_COFACTOR_WIDTH_FIELD_RE = re.compile(
    r"(?:^|, )cofactor_width=(\d+)(?=, |$)"
)


def parse_cofactor_width(content, props) -> None:
    """Parse the one exact heuristic width printed to ``run.log``.

    Blind runs intentionally have no ``wbh ... heuristic:`` line.  Any
    heuristic run has exactly one such line and exactly one integer
    ``cofactor_width`` field.  Treat repetitions and malformed fields as
    unexplained errors instead of silently selecting one value.
    """
    candidates = _ANY_WBH_HEURISTIC_LINE_RE.findall(content)
    if not candidates:
        return
    if len(candidates) != 1:
        tools.add_unexplained_error(
            props,
            "cofactor-width parser expected one wbh heuristic line; got {}".
            format(len(candidates)),
        )
        return
    lines = _WBH_HEURISTIC_LINE_RE.findall(content)
    if lines != candidates:
        tools.add_unexplained_error(
            props,
            "cofactor-width parser rejected a nonstandard run.log prefix",
        )
        return

    fields = _COFACTOR_WIDTH_FIELD_RE.findall(lines[0])
    if len(fields) != 1:
        tools.add_unexplained_error(
            props,
            "cofactor-width parser expected one integer field; got {}".
            format(len(fields)),
        )
        return
    props[COFACTOR_WIDTH_PROPERTY] = int(fields[0])


def get_cofactor_width_parser() -> Parser:
    parser = Parser()
    parser.add_function(parse_cofactor_width, file="run.log")
    return parser


def _required_lab_version() -> str:
    matches = []
    for raw_line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("lab=="):
            matches.append(line.partition("==")[2])
    if len(matches) != 1 or not matches[0]:
        raise RuntimeError(
            "requirements.txt must contain exactly one exact lab==VERSION pin"
        )
    return matches[0]


REQUIRED_LAB_VERSION = _required_lab_version()
INSTALLED_LAB_VERSION = importlib.metadata.version("lab")


def lab_step_numbers(args):
    """Return Lab's normalized one-based numeric step aliases."""
    return {
        int(arg)
        for arg in args
        if isinstance(arg, str) and arg.isdigit()
    }


def requested_build_or_start(args=None):
    requested = list(sys.argv[1:] if args is None else args)
    tokens = set(requested)
    numbers = lab_step_numbers(requested)
    return bool(tokens & {"build", "start"} or numbers & {1, 2})


def reject_unsafe_combined_steps(args=None):
    """Forbid Lab invocations that could start after a failed build."""
    requested = list(sys.argv[1:] if args is None else args)
    if any(arg in {"-h", "--help"} for arg in requested):
        return
    if any(
        isinstance(arg, str)
        and len(arg) > 2
        and "--all".startswith(arg)
        for arg in requested
    ):
        raise RuntimeError(
            "Arrhenius protocols forbid --all and its argparse abbreviations"
        )
    tokens = set(requested)
    numbers = lab_step_numbers(requested)
    wants_build = "build" in tokens or 1 in numbers
    wants_start = "start" in tokens or 2 in numbers
    if wants_build and wants_start:
        raise RuntimeError(
            "Arrhenius protocols require build and start in separate invocations"
        )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_output(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def require_revision_ancestor_of_head(revision: str) -> str:
    """Return protocol HEAD after attesting a full, existing ancestor commit."""
    if not isinstance(revision, str) or not re.fullmatch(
        r"[0-9a-f]{40}", revision
    ):
        raise RuntimeError("planner revision must be a full 40-digit commit")
    head = _git_output("rev-parse", "HEAD")
    try:
        _git_output("cat-file", "-e", revision + "^{commit}")
    except subprocess.CalledProcessError as err:
        raise RuntimeError(
            "pinned planner revision does not name an existing commit: {}".
            format(revision)
        ) from err
    try:
        _git_output("merge-base", "--is-ancestor", revision, head)
    except subprocess.CalledProcessError as err:
        raise RuntimeError(
            "pinned planner revision {} is not an ancestor of protocol HEAD {}".
            format(revision, head)
        ) from err
    return head


def require_clean_committed_revision(
    revision: str, protocol_files=()
) -> None:
    """Require a clean protocol HEAD descending from the pinned planner."""
    require_revision_ancestor_of_head(revision)
    dirty = _git_output("status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise RuntimeError(
            "prospective build/start requires a clean tracked worktree; got:\n{}".
            format(dirty)
        )
    required_files = [Path(__file__).resolve()]
    required_files.extend(Path(path).resolve() for path in protocol_files)
    for path in required_files:
        try:
            relative = path.relative_to(REPO).as_posix()
        except ValueError as err:
            raise RuntimeError(
                "protocol file is outside the planner repository: {}".format(
                    path
                )
            ) from err
        try:
            tracked = _git_output(
                "ls-files", "--error-unmatch", "--", relative
            )
        except subprocess.CalledProcessError as err:
            raise RuntimeError(
                "protocol file must be committed before build/start: {}".
                format(relative)
            ) from err
        if tracked != relative:
            raise RuntimeError(
                "could not attest committed protocol file: {}".format(relative)
            )


def require_pinned_lab_version() -> None:
    if INSTALLED_LAB_VERSION != REQUIRED_LAB_VERSION:
        raise RuntimeError(
            "build/start requires Lab {} from requirements.txt; installed is {}".
            format(REQUIRED_LAB_VERSION, INSTALLED_LAB_VERSION)
        )


def cached_revision(revision: str) -> CachedFastDownwardRevision:
    """Describe, but do not build, the exact prospective Lab cache."""
    return CachedFastDownwardRevision(
        str(REVISION_CACHE), str(REPO), revision, list(BUILD_OPTIONS)
    )


def revision_cache_paths(revision: str):
    cache = cached_revision(revision)
    return (
        cache,
        cache.path / "build_successful",
        cache.path / "builds" / CACHE_BUILD_NAME / "bin" / "downward",
    )


def inspect_revision_cache(revision: str):
    """Return cache identity and hashes without modifying the cache."""
    cache, sentinel, binary = revision_cache_paths(revision)
    return {
        "name": cache.name,
        "path": str(cache.path),
        "sentinel": str(sentinel),
        "binary": str(binary),
        "sentinel_sha256": _sha256_file(sentinel) if sentinel.is_file() else None,
        "binary_sha256": _sha256_file(binary) if binary.is_file() else None,
        "binary_executable": binary.is_file() and os.access(binary, os.X_OK),
    }


def require_revision_cache(
    revision: str, expected_binary_sha256: str | None
) -> dict:
    """Require the prebuilt, stripped ``release_no_lp`` cache and exact hash."""
    if not isinstance(expected_binary_sha256, str) or not _SHA256_RE.fullmatch(
        expected_binary_sha256
    ):
        raise RuntimeError(
            "set CACHE_BINARY_SHA256 to the reviewed cached-binary SHA-256 "
            "before build/start"
        )
    info = inspect_revision_cache(revision)
    if info["sentinel_sha256"] != CACHE_SENTINEL_SHA256:
        raise RuntimeError(
            "missing or changed revision-cache sentinel: {}".format(
                info["sentinel"]
            )
        )
    if not info["binary_executable"]:
        raise RuntimeError(
            "missing or non-executable cached planner: {}".format(info["binary"])
        )
    if info["binary_sha256"] != expected_binary_sha256:
        raise RuntimeError(
            "cached planner SHA-256 mismatch: expected {}, got {}".format(
                expected_binary_sha256, info["binary_sha256"]
            )
        )
    return info


def require_launch_prerequisites(
    revision: str,
    expected_binary_sha256: str | None,
    args=None,
    protocol_files=(),
) -> dict | None:
    """Apply all launch-only gates without affecting read-only steps."""
    if not requested_build_or_start(args):
        return None
    require_clean_committed_revision(revision, protocol_files)
    require_pinned_lab_version()
    return require_revision_cache(revision, expected_binary_sha256)


def _parse_slurm_time(value: str) -> int:
    match = re.fullmatch(r"(?:(\d+)-)?(\d+):(\d{2}):(\d{2})", value)
    if not match:
        raise RuntimeError("invalid Slurm wall time {!r}".format(value))
    days, hours, minutes, seconds = (
        int(field or 0) for field in match.groups()
    )
    if minutes >= 60 or seconds >= 60:
        raise RuntimeError("invalid Slurm wall time {!r}".format(value))
    return (((days * 24) + hours) * 60 + minutes) * 60 + seconds


def run_layout(num_runs: int):
    if type(num_runs) is not int or num_runs <= 0:
        raise RuntimeError("num_runs must be a positive integer")
    runs_per_array_task = math.ceil(num_runs / MAX_ARRAY_TASKS)
    array_tasks = math.ceil(num_runs / runs_per_array_task)
    return array_tasks, runs_per_array_task


def validate_run_layout(
    num_runs: int,
    *,
    planner_time_limit_seconds: int = TIME_LIMIT_SECONDS,
    scheduler_time_limit: str = SCHEDULER_TIME_LIMIT,
    require_one_run_per_array_task: bool = False,
) -> dict:
    array_tasks, runs_per_array_task = run_layout(num_runs)
    if array_tasks > MAX_ARRAY_TASKS:
        raise RuntimeError("Arrhenius array exceeds MAX_TASKS=1000")
    if require_one_run_per_array_task and runs_per_array_task != 1:
        raise RuntimeError(
            "pilot must contain at most 1000 runs so every array element "
            "executes exactly one run"
        )
    scheduler_seconds = _parse_slurm_time(scheduler_time_limit)
    required_seconds = runs_per_array_task * (
        planner_time_limit_seconds + SCHEDULER_WRAPPER_ALLOWANCE_SECONDS
    )
    if scheduler_seconds < required_seconds:
        raise RuntimeError(
            "scheduler envelope {} is too short for {} run(s) per array task; "
            "need at least {} seconds".format(
                scheduler_time_limit, runs_per_array_task, required_seconds
            )
        )
    return {
        "raw_runs": num_runs,
        "array_tasks": array_tasks,
        "runs_per_array_task": runs_per_array_task,
        "scheduler_time_limit_seconds": scheduler_seconds,
    }


class _SeededTaskOrderMixin:
    def __init__(self, *args, task_order_seed=TASK_ORDER_SEED, **kwargs):
        self.task_order_seed = task_order_seed
        kwargs["randomize_task_order"] = False
        super().__init__(*args, **kwargs)

    def _get_task_order(self, num_tasks):
        task_order = list(range(1, num_tasks + 1))

        def key(task_id):
            payload = "{}\0{}\0{}".format(
                self.task_order_seed, num_tasks, task_id
            )
            return hashlib.sha256(payload.encode("utf-8")).digest(), task_id

        task_order.sort(key=key)
        return task_order


class SeededArrheniusEnvironment(_SeededTaskOrderMixin, SlurmEnvironment):
    """Arrhenius environment with deterministic grouping and sealed headers."""

    DEFAULT_PARTITION = SCHEDULER_PARTITION
    DEFAULT_QOS = SCHEDULER_QOS
    DEFAULT_TIME_LIMIT_PER_TASK = SCHEDULER_TIME_LIMIT
    DEFAULT_MEMORY_PER_CPU = SCHEDULER_MEMORY_PER_CPU
    MAX_TASKS = MAX_ARRAY_TASKS

    @classmethod
    def is_present(cls):
        node = platform.node()
        return bool(
            re.fullmatch(
                r"arrhenius\d+\.hpc\.arrhenius\.naiss\.se|n\d+", node
            )
        )

    def _get_job_header(self, step, is_last):
        header = super()._get_job_header(step, is_last)
        if not header.startswith("#! /bin/bash -l\n"):
            raise RuntimeError("Lab Slurm shebang changed; review Arrhenius header")
        header = header.replace("#! /bin/bash -l", "#! /bin/bash", 1)
        if not is_run_step(step):
            return header

        num_tasks = self._get_num_tasks(step)
        unthrottled = "{}1-{}".format(_SLURM_ARRAY_DIRECTIVE, num_tasks)
        throttled = "{}%{}".format(unthrottled, ARRAY_TASK_THROTTLE)
        lines = header.splitlines()
        directives = [
            line for line in lines if line.startswith(_SLURM_ARRAY_DIRECTIVE)
        ]
        if directives != [unthrottled]:
            raise RuntimeError(
                "Lab array header changed: expected {!r}, got {!r}".format(
                    unthrottled, directives
                )
            )
        lines[lines.index(unthrottled)] = throttled
        return "\n".join(lines) + ("\n" if header.endswith("\n") else "")

    def _get_run_job_body(self, run_step):
        body = super()._get_run_job_body(run_step)
        if body.count(_RANDOM_RUN_LOOP) != 1:
            raise RuntimeError(
                "Lab run-body shuffle changed; review deterministic grouping"
            )
        return body.replace(_RANDOM_RUN_LOOP, _DETERMINISTIC_RUN_LOOP, 1)

    def _get_job(self, step, is_last):
        job = super()._get_job(step, is_last)
        if is_run_step(step):
            assert_exact_run_header(self, job, len(self.exp.runs))
            if _RANDOM_RUN_LOOP in job or job.count(_DETERMINISTIC_RUN_LOOP) != 1:
                raise RuntimeError("run job does not use deterministic inner order")
        return job


def get_environment() -> SeededArrheniusEnvironment:
    if SCHEDULER_PARTITION != "cpu" or SCHEDULER_QOS != "normal":
        raise RuntimeError("Arrhenius protocol requires cpu/normal")
    if not re.fullmatch(r"[a-z0-9-]+-cpu", SCHEDULER_ACCOUNT):
        raise RuntimeError(
            "Arrhenius account must include its -cpu suffix: {}".format(
                SCHEDULER_ACCOUNT
            )
        )
    environment = SeededArrheniusEnvironment(
        email=None,
        partition=SCHEDULER_PARTITION,
        qos=SCHEDULER_QOS,
        time_limit_per_task=SCHEDULER_TIME_LIMIT,
        memory_per_cpu=SCHEDULER_MEMORY_PER_CPU,
        cpus_per_task=SCHEDULER_CPUS_PER_TASK,
        extra_options="#SBATCH --account={}".format(SCHEDULER_ACCOUNT),
    )
    environment.protocol_account = SCHEDULER_ACCOUNT
    return environment


def _require_exact_directive(lines, expected):
    prefix = expected.partition("=")[0] + "="
    matches = [line for line in lines if line.startswith(prefix)]
    if matches != [expected]:
        raise RuntimeError(
            "expected exactly one scheduler directive {!r}; got {!r}".format(
                expected, matches
            )
        )


def assert_exact_run_header(environment, job: str, num_runs: int) -> dict:
    """Assert every research-relevant Arrhenius header field exactly."""
    layout = validate_run_layout(
        num_runs,
        scheduler_time_limit=environment.time_limit_per_task,
    )
    lines = job.splitlines()
    if not lines or lines[0] != "#! /bin/bash":
        raise RuntimeError("Arrhenius jobs must use non-login bash")
    if any(line == "#! /bin/bash -l" for line in lines):
        raise RuntimeError("Arrhenius job retained a login-shell shebang")

    expected = [
        "#SBATCH --partition={}".format(SCHEDULER_PARTITION),
        "#SBATCH --qos={}".format(SCHEDULER_QOS),
        "#SBATCH --time={}".format(environment.time_limit_per_task),
        "#SBATCH --mem-per-cpu={}".format(environment.memory_per_cpu),
        "#SBATCH --cpus-per-task={}".format(environment.cpus_per_task),
        "#SBATCH --array=1-{}%{}".format(
            layout["array_tasks"], ARRAY_TASK_THROTTLE
        ),
        "#SBATCH --account={}".format(environment.protocol_account),
    ]
    for directive in expected:
        _require_exact_directive(lines, directive)
    array_directives = [
        line for line in lines if line.startswith(_SLURM_ARRAY_DIRECTIVE)
    ]
    if array_directives != [expected[5]]:
        raise RuntimeError(
            "expected one exact throttled array directive; got {!r}".format(
                array_directives
            )
        )
    return layout


def make_in_memory_run_job(
    num_runs: int, scheduler_time_limit=SCHEDULER_TIME_LIMIT
):
    class FakeStep:
        name = "start"
        _funcname = "start_runs"

    class FakeExperiment:
        name = "arrhenius-header-self-test"
        path = "/tmp/arrhenius-header-self-test"

        def __init__(self):
            self.runs = [None] * num_runs
            self.steps = [FakeStep()]

    environment = SeededArrheniusEnvironment(
        email=None,
        partition=SCHEDULER_PARTITION,
        qos=SCHEDULER_QOS,
        time_limit_per_task=scheduler_time_limit,
        memory_per_cpu=SCHEDULER_MEMORY_PER_CPU,
        cpus_per_task=SCHEDULER_CPUS_PER_TASK,
        extra_options="#SBATCH --account={}".format(SCHEDULER_ACCOUNT),
    )
    environment.protocol_account = SCHEDULER_ACCOUNT
    environment.exp = FakeExperiment()
    # Lab >=8.0 resolves shared log paths through this attribute even for
    # in-memory headers.  No directory is created.
    environment.job_dir = Path("/tmp/arrhenius-header-self-test-grid-steps")
    step = environment.exp.steps[0]
    return environment, environment._get_job(step, True)


class ProtocolFastDownwardExperiment(FastDownwardExperiment):
    """Fast Downward experiment that copies protocol metadata into every run."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.protocol_run_properties = {}

    def _add_runs(self):
        first_new_run = len(self.runs)
        super()._add_runs()
        for run in self.runs[first_new_run:]:
            for name, value in self.protocol_run_properties.items():
                run.set_property(name, value)


def common_protocol_metadata(
    revision: str,
    cache_binary_sha256: str | None,
    num_runs: int,
) -> dict:
    layout = validate_run_layout(num_runs)
    protocol_revision = require_revision_ancestor_of_head(revision)
    cache = cached_revision(revision)
    return {
        "planner_revision": revision,
        "protocol_revision": protocol_revision,
        "planner_revision_is_protocol_ancestor": True,
        "planner_build_options": list(BUILD_OPTIONS),
        "planner_build_config": CACHE_BUILD_NAME,
        "planner_binary_sha256": cache_binary_sha256,
        "planner_revision_cache_name": cache.name,
        "cofactor_width_property": COFACTOR_WIDTH_PROPERTY,
        "cofactor_width_parser_protocol": COFACTOR_WIDTH_PARSER_PROTOCOL,
        "python_version": platform.python_version(),
        "lab_version": INSTALLED_LAB_VERSION,
        "required_lab_version": REQUIRED_LAB_VERSION,
        "task_order_seed": TASK_ORDER_SEED,
        "task_order_method": TASK_ORDER_METHOD,
        "driver_time_limit": TIME_LIMIT,
        "driver_memory_limit": MEMORY_LIMIT,
        "scheduler_environment": "arrhenius-slurm",
        "scheduler_cluster": SCHEDULER_CLUSTER,
        "scheduler_cpu_model": SCHEDULER_CPU_MODEL,
        "scheduler_partition": SCHEDULER_PARTITION,
        "scheduler_qos": SCHEDULER_QOS,
        "scheduler_account": SCHEDULER_ACCOUNT,
        "scheduler_time_limit_per_task": SCHEDULER_TIME_LIMIT,
        "scheduler_memory_per_cpu": SCHEDULER_MEMORY_PER_CPU,
        "scheduler_cpus_per_task": SCHEDULER_CPUS_PER_TASK,
        "scheduler_array_task_throttle": ARRAY_TASK_THROTTLE,
        "scheduler_max_array_tasks": MAX_ARRAY_TASKS,
        "scheduler_array_tasks": layout["array_tasks"],
        "scheduler_runs_per_array_task": layout["runs_per_array_task"],
        "declared_run_count": num_runs,
        "repetitions": 1,
    }


def validate_common_protocol_metadata(metadata: dict) -> None:
    """Require a complete, internally consistent common protocol record."""
    if not isinstance(metadata, dict):
        raise TypeError("protocol metadata must be a dictionary")
    required_identity = (
        "planner_revision",
        "planner_binary_sha256",
        "declared_run_count",
    )
    missing_identity = [
        name for name in required_identity if name not in metadata
    ]
    if missing_identity:
        raise RuntimeError(
            "protocol metadata is missing: {}".format(
                ", ".join(missing_identity)
            )
        )
    expected = common_protocol_metadata(
        metadata["planner_revision"],
        metadata["planner_binary_sha256"],
        metadata["declared_run_count"],
    )
    mismatches = {
        name: (metadata.get(name), value)
        for name, value in expected.items()
        if metadata.get(name) != value
    }
    if mismatches:
        details = "; ".join(
            "{}={!r}, expected {!r}".format(name, actual, wanted)
            for name, (actual, wanted) in sorted(mismatches.items())
        )
        raise RuntimeError("common protocol metadata mismatch: " + details)


def new_experiment(protocol_metadata: dict) -> ProtocolFastDownwardExperiment:
    validate_common_protocol_metadata(protocol_metadata)
    environment = get_environment()
    experiment = ProtocolFastDownwardExperiment(
        environment=environment, revision_cache=str(REVISION_CACHE)
    )
    experiment.protocol_run_properties.update(protocol_metadata)
    experiment.add_parser(experiment.EXITCODE_PARSER)
    experiment.add_parser(experiment.TRANSLATOR_PARSER)
    experiment.add_parser(experiment.SINGLE_SEARCH_PARSER)
    experiment.add_parser(experiment.PLANNER_PARSER)
    experiment.add_parser(wbh_parser.get_parser())
    experiment.add_parser(get_cofactor_width_parser())
    return experiment


def set_protocol_run_properties(experiment, properties):
    if not isinstance(experiment, ProtocolFastDownwardExperiment):
        raise TypeError("expected ProtocolFastDownwardExperiment")
    overlap = set(experiment.protocol_run_properties) & set(properties)
    if overlap:
        raise RuntimeError(
            "protocol properties already set: {}".format(
                ", ".join(sorted(overlap))
            )
        )
    experiment.protocol_run_properties.update(properties)


def search_config(search_expr: str) -> str:
    if not search_expr.endswith(")") or "(" not in search_expr:
        raise ValueError("expected a plugin expression ending in ')'")
    open_paren = search_expr.index("(")
    inner = search_expr[open_paren + 1 : -1].strip()
    separator = "," if inner else ""
    return '{}{}{}wbh_log="{}")'.format(
        search_expr[: open_paren + 1], inner, separator, WBH_LOG
    )


def add_algorithm(
    experiment, name: str, search_expr: str, *, revision: str
) -> None:
    require_revision_ancestor_of_head(revision)
    experiment.add_algorithm(
        name,
        str(REPO),
        revision,
        ["--search", search_config(search_expr)],
        build_options=list(BUILD_OPTIONS),
        driver_options=[
            "--build",
            CACHE_BUILD_NAME,
            "--overall-time-limit",
            TIME_LIMIT,
            "--overall-memory-limit",
            MEMORY_LIMIT,
        ],
    )


def add_suite(experiment, benchmarks: Path, suite) -> None:
    experiment.add_suite(str(benchmarks), suite)


ATTRIBUTES = [
    "coverage", "solution_cost", "planner_time", "total_time", "effort",
    "cofactor_width",
    "peak_bdd_nodes", "expanded_bdd_nodes", "expanded_states",
    "expanded_bdd_pieces", "attempted_bdd_nodes", "attempted_states",
    "attempted_bdd_pieces", "bucket_expansions", "bucket_expansion_attempts",
    "image_events", "bucket_images", "image_source_buckets",
    "image_source_pieces", "image_calls_attempted", "image_calls_completed",
    "batched_images", "image_time", "raw_metrics_complete",
    "wbh_schema_version", "node_count_convention", "image_count_convention",
    "expansion_count_convention", "piece_metrics_certified",
    "metrics_validation_protocol", "metrics_validation_error",
    "expanded_buckets_single_piece", "partition_ratio_max",
    "partition_ratio_geomean", "width_upper_bound", "num_values",
    "num_terminals", "add_nodes", "construction_time", "heuristic_kind",
    "heuristic_size_bound", "value_cap", "construction_completed",
    "num_pruned_deadends", "pruned_deadend_states",
    "pruned_deadend_bdd_nodes", "error",
]


def add_standard_steps(experiment, extra_attributes=()):
    experiment.add_step("build", experiment.build)
    experiment.add_step("start", experiment.start_runs)
    experiment.add_step("parse", experiment.parse)
    experiment.add_fetcher(name="fetch")
    attributes = list(dict.fromkeys(
        ATTRIBUTES
        + list(experiment.protocol_run_properties)
        + list(extra_attributes)
    ))
    experiment.add_report(
        AbsoluteReport(attributes=attributes),
        name="report",
        outfile="report.html",
    )


def self_test_scheduler_headers():
    expected_layouts = {
        1: (1, 1),
        700: (700, 1),
        1000: (1000, 1),
        1001: (501, 2),
        1050: (525, 2),
        1404: (702, 2),
    }
    for num_runs, expected in expected_layouts.items():
        wall = "00:20:00" if expected[1] == 2 else "00:10:00"
        environment, job = make_in_memory_run_job(
            num_runs, scheduler_time_limit=wall
        )
        layout = assert_exact_run_header(environment, job, num_runs)
        actual = (layout["array_tasks"], layout["runs_per_array_task"])
        if actual != expected:
            raise AssertionError(
                "{} runs produced layout {}, expected {}".format(
                    num_runs, actual, expected
                )
            )
        if _RANDOM_RUN_LOOP in job or job.count(_DETERMINISTIC_RUN_LOOP) != 1:
            raise AssertionError("inner run order is not deterministic")
        first_order = environment._get_task_order(layout["array_tasks"])
        second_order = environment._get_task_order(layout["array_tasks"])
        if first_order != second_order or sorted(first_order) != list(
            range(1, layout["array_tasks"] + 1)
        ):
            raise AssertionError("seeded array-task order is not reproducible")

    conflicting_header = job.replace(
        "#SBATCH --partition=cpu",
        "#SBATCH --partition=cpu\n#SBATCH --partition=gpu",
        1,
    )
    try:
        assert_exact_run_header(environment, conflicting_header, num_runs)
    except RuntimeError:
        pass
    else:
        raise AssertionError("conflicting scheduler directive was accepted")

    try:
        validate_run_layout(
            1001,
            scheduler_time_limit="00:10:00",
            require_one_run_per_array_task=True,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("one-run-per-array pilot gate accepted 1001 runs")

    for unsafe in (
        ["build", "start"], ["1", "2"], ["build", "2"], ["--a"],
        ["--al"], ["--all"],
    ):
        try:
            reject_unsafe_combined_steps(unsafe)
        except RuntimeError:
            pass
        else:
            raise AssertionError("unsafe Lab steps were accepted: {!r}".format(unsafe))

    cache = cached_revision(REV)
    if not cache.name.endswith("_61a748e5"):
        raise AssertionError(
            "release_no_lp cache identity changed: {}".format(cache.name)
        )
    if REQUIRED_LAB_VERSION != "8.0":
        raise AssertionError(
            "review requirements-version test for lab=={}".format(
                REQUIRED_LAB_VERSION
            )
        )
    if not INSTALLED_LAB_VERSION:
        raise AssertionError("installed Lab version is unavailable")
    try:
        require_pinned_lab_version()
    except RuntimeError:
        if INSTALLED_LAB_VERSION == REQUIRED_LAB_VERSION:
            raise AssertionError("matching Lab version was rejected")
    else:
        if INSTALLED_LAB_VERSION != REQUIRED_LAB_VERSION:
            raise AssertionError("mismatched Lab version was accepted")
    try:
        require_revision_cache(REV, None)
    except RuntimeError:
        pass
    else:
        raise AssertionError("missing cache-binary hash pin was accepted")
    if require_launch_prerequisites(REV, None, args=["parse"]) is not None:
        raise AssertionError("read-only parse unexpectedly required the cache")

    class FakeExperiment:
        def add_algorithm(self, *args, **kwargs):
            self.call = (args, kwargs)

    fake_experiment = FakeExperiment()
    add_algorithm(
        fake_experiment, "blind", "sym_fw()", revision=REV
    )
    args, kwargs = fake_experiment.call
    if args[2] != REV or kwargs.get("build_options") != BUILD_OPTIONS:
        raise AssertionError("explicit algorithm revision/build was not retained")
    if kwargs.get("driver_options", [])[:2] != [
        "--build", CACHE_BUILD_NAME
    ]:
        raise AssertionError("cached build was not selected in driver options")

    print(
        "Arrhenius scheduler self-tests: PASS "
        "(layouts 1/700/1000/1001/1050/1404; throttle=5)"
    )
    print(
        "exact run headers: cpu, normal, one CPU, 9G, non-login bash, "
        "account {}, deterministic grouping".format(SCHEDULER_ACCOUNT)
    )
    print(
        "Lab compatibility: installed {}; requirements pin {} "
        "(build/start require an exact match)".format(
            INSTALLED_LAB_VERSION, REQUIRED_LAB_VERSION
        )
    )


def self_test_cofactor_width_parser():
    examples = {
        (
            "[t=1.234567s, 45678 KB] wbh linear M&S heuristic: "
            "max_states=10000, value_cap=-1, "
            "abstract_states=482, values=19, cofactor_width=7, "
            "width_upper_bound=21\n"
        ): 7,
        (
            "[t=0.071340s, 534048 KB] wbh PDB heuristic: "
            "pattern_size=6, values=12, "
            "cofactor_width=11, width_upper_bound=17\n"
        ): 11,
        (
            "[t=12.000001s, 987654 KB] wbh potential heuristic: m=8, "
            "values=9, cofactor_width=3, width_upper_bound=10\n"
        ): 3,
    }
    for content, expected in examples.items():
        props = {}
        parse_cofactor_width(content, props)
        if props != {COFACTOR_WIDTH_PROPERTY: expected}:
            raise AssertionError(
                "wrong cofactor-width parse: {!r}".format(props)
            )

    blind_props = {}
    parse_cofactor_width("Solution found.\n", blind_props)
    if blind_props:
        raise AssertionError("blind output unexpectedly gained a width")

    bad_prefix_props = {}
    parse_cofactor_width(
        "[t=0.071340, 534048 KB] wbh PDB heuristic: pattern_size=6, "
        "values=12, cofactor_width=11, width_upper_bound=17\n",
        bad_prefix_props,
    )
    expected_bad_prefix = [
        "cofactor-width parser rejected a nonstandard run.log prefix"
    ]
    if bad_prefix_props != {"unexplained_errors": expected_bad_prefix}:
        raise AssertionError(
            "nonstandard log prefix did not fail closed: {!r}".format(
                bad_prefix_props
            )
        )

    malformed_props = {}
    parse_cofactor_width(
        "[t=0.071340s, 534048 KB] wbh PDB heuristic: "
        "pattern_size=6, values=12, "
        "cofactor_width=oops, width_upper_bound=17\n",
        malformed_props,
    )
    expected_malformed = [
        "cofactor-width parser expected one integer field; got 0"
    ]
    if malformed_props != {"unexplained_errors": expected_malformed}:
        raise AssertionError(
            "malformed cofactor width did not fail closed: {!r}".format(
                malformed_props
            )
        )

    duplicate_props = {}
    duplicate_line = next(iter(examples))
    parse_cofactor_width(duplicate_line + duplicate_line, duplicate_props)
    expected_duplicate = [
        "cofactor-width parser expected one wbh heuristic line; got 2"
    ]
    if duplicate_props != {"unexplained_errors": expected_duplicate}:
        raise AssertionError(
            "duplicate heuristic lines did not fail closed: {!r}".format(
                duplicate_props
            )
        )

    duplicate_field_props = {}
    parse_cofactor_width(
        "[t=0.071340s, 534048 KB] wbh PDB heuristic: "
        "pattern_size=6, cofactor_width=4, "
        "cofactor_width=5, width_upper_bound=17\n",
        duplicate_field_props,
    )
    expected_duplicate_field = [
        "cofactor-width parser expected one integer field; got 2"
    ]
    if duplicate_field_props != {
        "unexplained_errors": expected_duplicate_field
    }:
        raise AssertionError(
            "duplicate cofactor fields did not fail closed: {!r}".format(
                duplicate_field_props
            )
        )

    parser = get_cofactor_width_parser()
    if len(parser.functions) != 1 or parser.functions[0].filename != "run.log":
        raise AssertionError("cofactor-width parser is not bound to run.log")
    if COFACTOR_WIDTH_PROPERTY not in ATTRIBUTES:
        raise AssertionError("cofactor_width is missing from ATTRIBUTES")
    metadata = common_protocol_metadata(REV, "0" * 64, 700)
    if metadata.get("cofactor_width_parser_protocol") != (
        COFACTOR_WIDTH_PARSER_PROTOCOL
    ):
        raise AssertionError("cofactor-width protocol metadata changed")
    tampered = dict(metadata)
    tampered["cofactor_width_parser_protocol"] = "changed"
    try:
        validate_common_protocol_metadata(tampered)
    except RuntimeError:
        pass
    else:
        raise AssertionError("changed cofactor-width protocol was accepted")
    print(
        "cofactor-width parser self-tests: PASS "
        "(M&S/PDB/potential; missing/duplicate/malformed gates)"
    )


if __name__ == "__main__":
    self_test_scheduler_headers()
    self_test_cofactor_width_parser()
