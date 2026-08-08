"""Shared setup for the width-bounded-heuristics Downward Lab experiments (PR5).

Environment selection:
  * default: TetralithEnvironment (the NSC cluster; we submit from the login
    node). Limits: 30 min, 8 GiB per run (matching Fiser et al.).
  * WBH_LOCAL=1 in the environment: LocalEnvironment for dry runs, with a
    short time limit.

Algorithms are added against the current git revision of this repository (the
`bounded-heuristics` branch), which Downward Lab builds and caches. Each search
config writes its JSON-lines instrumentation to wbh.jsonl in the run directory
(parsed by wbh_parser).
"""
import hashlib
import os
import platform
import subprocess
import sys
from pathlib import Path

from downward.experiment import FastDownwardExperiment
from downward.reports.absolute import AbsoluteReport
from lab.environments import (
    LocalEnvironment,
    TetralithEnvironment,
    is_run_step,
)

import wbh_parser

REPO = Path(__file__).resolve().parent.parent
BENCHMARKS = Path(
    os.environ.get("DOWNWARD_BENCHMARKS", os.path.expanduser("~/projects/benchmarks"))
)
REV = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "HEAD"],
    capture_output=True, text=True).stdout.strip()

LOCAL = os.environ.get("WBH_LOCAL") == "1"

# Per-run limits (Fiser et al.): 30 min, 8 GiB. Shortened for local dry runs.
TIME_LIMIT = "60s" if LOCAL else "1800s"
MEMORY_LIMIT = "4G" if LOCAL else "8G"

# wbh_log is written to the run directory; the parser reads it from there.
WBH_LOG = 'wbh.jsonl'


# NSC/Tetralith allocation for this project. Per-run limits (30 min, 8 GiB) are
# enforced by the Fast Downward driver (add_algorithm below); Tetralith's
# defaults (9 GiB/cpu, 24 h/job) comfortably envelope them so the driver limits
# bind first and fail gracefully.
TETRALITH_EMAIL = os.environ.get("WBH_EMAIL", "jendrik.seipp@liu.se")
TETRALITH_ACCOUNT = os.environ.get("WBH_ACCOUNT", "naiss2025-5-382")
TETRALITH_QOS = os.environ.get("WBH_QOS", "normal")
TETRALITH_TASK_TIME = os.environ.get("WBH_TASK_TIME", "24:00:00")
TETRALITH_MEMORY_PER_CPU = os.environ.get(
    "WBH_MEMORY_PER_CPU", "9G")

# Lab randomizes the task order by default using process-global entropy.  Keep
# the useful randomization, but make it reproducible for every prospective
# c280 experiment.  This does not reinterpret or reorder an already-built
# experiment (in particular, the ec839 cap pilot).
TASK_ORDER_SEED = "symbolic-search-heuristics/c280-task-order/v1"
TASK_ORDER_METHOD = "sha256(seed-nul-count-nul-task-id)-sort/v1"

# Keep the prospective arrays within the concurrency already exercised by the
# sealed cap pilot.  This must be encoded in the submitted header: Tetralith's
# devel QOS limits users to two nodes, but many 1-CPU array elements can share
# those nodes, so the QOS node limit is not an array-task throttle.
ARRAY_TASK_THROTTLE = 5
_SLURM_ARRAY_DIRECTIVE = "#SBATCH --array="
FROZEN_C280_REVISION = "c2800d7e65abb61d4b94b08a5487f701ceb41d6b"
FROZEN_C280_CACHE_NAME = FROZEN_C280_REVISION + "_e5e41175"
FROZEN_C280_SENTINEL_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
FROZEN_C280_DOWNWARD_SHA256 = (
    "774e0f80cfb06bd476b542b0539aed36a4e428f19cdc813b55813e775f392f37")


def lab_step_numbers(args):
    """Return Lab's normalized 1-based numeric step aliases."""
    return {
        int(arg) for arg in args
        if isinstance(arg, str) and arg.isdigit()
    }


def reject_unsafe_combined_steps(args=None):
    """Reject Lab invocations that could start after a failed build.

    Downward Lab links grid steps with ``afterany``.  The prospective
    protocols therefore require ``build`` and ``start`` in separate
    invocations, after the revision-cache sentinel and built run matrix have
    each been checked.  Enforce that contract for both step names and Lab's
    numeric aliases; ``--all`` necessarily combines them.  Explicit help is
    always read-only and remains available.
    """
    requested = list(sys.argv[1:] if args is None else args)
    if any(arg in {"-h", "--help"} for arg in requested):
        return
    all_aliases = {
        arg for arg in requested
        if isinstance(arg, str) and len(arg) > 2 and "--all".startswith(arg)
    }
    if all_aliases:
        raise RuntimeError(
            "prospective protocols forbid --all (including argparse "
            "abbreviations); run build and start separately")
    tokens = set(requested)
    step_numbers = lab_step_numbers(requested)
    wants_build = "build" in tokens or 1 in step_numbers
    wants_start = "start" in tokens or 2 in step_numbers
    if wants_build and wants_start:
        raise RuntimeError(
            "prospective protocols require build and start in separate "
            "invocations")


def _sha256_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_frozen_revision_cache(revision, args=None):
    """Fail before prospective build/start unless c280 is already cached.

    Fast Downward's Lab integration can create a missing revision cache while
    reconstructing a grid experiment.  On a login node that would compile the
    planner before the run array is submitted.  The frozen protocol instead
    prebuilds c280 in a compute allocation and attests both the cache sentinel
    and executable.  Read-only help and non-execution steps do not need the
    cache.
    """
    requested = list(sys.argv[1:] if args is None else args)
    if any(arg in {"-h", "--help"} for arg in requested):
        return
    tokens = set(requested)
    step_numbers = lab_step_numbers(requested)
    if not (tokens & {"build", "start"} or step_numbers & {1, 2}):
        return
    if revision != FROZEN_C280_REVISION:
        raise RuntimeError(
            "prospective cache gate only permits frozen revision {}".format(
                FROZEN_C280_REVISION))
    cache = REPO / "experiments" / "data" / "revision-cache" / \
        FROZEN_C280_CACHE_NAME
    expected = {
        cache / "build_successful": FROZEN_C280_SENTINEL_SHA256,
        cache / "builds" / "release" / "bin" / "downward":
            FROZEN_C280_DOWNWARD_SHA256,
    }
    for path, wanted in expected.items():
        if not path.is_file():
            raise RuntimeError(
                "frozen c280 revision cache is incomplete: {}".format(path))
        actual = _sha256_file(path)
        if actual != wanted:
            raise RuntimeError(
                "frozen c280 cache hash mismatch for {}: expected {}, got {}".
                format(path, wanted, actual))


class _SeededTaskOrderMixin:
    def __init__(self, *args, task_order_seed=TASK_ORDER_SEED, **kwargs):
        self.task_order_seed = task_order_seed
        # Our override performs the shuffle, so disable Lab's unseeded one.
        kwargs["randomize_task_order"] = False
        super().__init__(*args, **kwargs)

    def _get_task_order(self, num_tasks):
        task_order = list(range(1, num_tasks + 1))
        # Hash-sort is a seeded shuffle with a byte-stable definition; it does
        # not depend on Python's PRNG implementation or prior calls.
        def key(task_id):
            payload = "{}\0{}\0{}".format(
                self.task_order_seed, num_tasks, task_id)
            return hashlib.sha256(payload.encode("utf-8")).digest(), task_id

        task_order.sort(key=key)
        return task_order


class SeededLocalEnvironment(_SeededTaskOrderMixin, LocalEnvironment):
    pass


class SeededTetralithEnvironment(_SeededTaskOrderMixin, TetralithEnvironment):
    @staticmethod
    def _assert_throttled_run_header(header, num_tasks):
        expected = "{}1-{}%{}".format(
            _SLURM_ARRAY_DIRECTIVE, num_tasks, ARRAY_TASK_THROTTLE)
        directives = [
            line for line in header.splitlines()
            if line.startswith(_SLURM_ARRAY_DIRECTIVE)]
        if directives != [expected]:
            raise RuntimeError(
                "prospective start job must contain exactly {!r}; got {!r}".format(
                    expected, directives))

    def _get_job_header(self, step, is_last):
        header = super()._get_job_header(step, is_last)
        if not is_run_step(step):
            return header

        num_tasks = self._get_num_tasks(step)
        unthrottled = "{}1-{}".format(_SLURM_ARRAY_DIRECTIVE, num_tasks)
        throttled = "{}%{}".format(unthrottled, ARRAY_TASK_THROTTLE)
        lines = header.splitlines()
        array_directives = [
            line for line in lines if line.startswith(_SLURM_ARRAY_DIRECTIVE)]
        if array_directives != [unthrottled]:
            raise RuntimeError(
                "Lab start header changed; expected one exact {!r}, got {!r}".format(
                    unthrottled, array_directives))
        lines[lines.index(unthrottled)] = throttled
        patched = "\n".join(lines) + ("\n" if header.endswith("\n") else "")
        self._assert_throttled_run_header(patched, num_tasks)
        return patched

    def _get_job(self, step, is_last):
        job = super()._get_job(step, is_last)
        if is_run_step(step):
            # Assert the complete generated start script, not only the header
            # fragment, so a later Lab template change cannot add a second,
            # unthrottled array directive elsewhere in the job.
            self._assert_throttled_run_header(
                job, self._get_num_tasks(step))
        return job


class ProtocolFastDownwardExperiment(FastDownwardExperiment):
    """Fast Downward experiment that freezes common per-run metadata."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.protocol_run_properties = {}

    def _add_runs(self):
        first_new_run = len(self.runs)
        super()._add_runs()
        for run in self.runs[first_new_run:]:
            for name, value in self.protocol_run_properties.items():
                run.set_property(name, value)


def get_environment():
    if LOCAL:
        return SeededLocalEnvironment(processes=4)
    return SeededTetralithEnvironment(
        email=TETRALITH_EMAIL,
        qos=TETRALITH_QOS,
        time_limit_per_task=TETRALITH_TASK_TIME,
        memory_per_cpu=TETRALITH_MEMORY_PER_CPU,
        extra_options=f"#SBATCH --account={TETRALITH_ACCOUNT}",
    )


def search_config(search_expr):
    """Insert the wbh_log option into a sym_* search expression."""
    assert search_expr.endswith(")")
    inner = search_expr[search_expr.index("(") + 1:-1].strip()
    sep = "," if inner else ""
    head = search_expr[:search_expr.index("(")]
    return f'{head}({inner}{sep}wbh_log="{WBH_LOG}")'


def new_experiment():
    environment = get_environment()
    exp = ProtocolFastDownwardExperiment(environment=environment)
    exp.protocol_run_properties.update({
        "task_order_seed": TASK_ORDER_SEED,
        "task_order_method": TASK_ORDER_METHOD,
        "driver_time_limit": TIME_LIMIT,
        "driver_memory_limit": MEMORY_LIMIT,
        "scheduler_environment": (
            "local" if LOCAL else "tetralith-slurm"),
        "scheduler_qos": "local" if LOCAL else TETRALITH_QOS,
        "scheduler_time_limit_per_task": (
            None if LOCAL else TETRALITH_TASK_TIME),
        "scheduler_memory_per_cpu": (
            None if LOCAL else TETRALITH_MEMORY_PER_CPU),
        "scheduler_cpus_per_task": (
            None if LOCAL else environment.cpus_per_task),
        "scheduler_array_task_throttle": (
            None if LOCAL else ARRAY_TASK_THROTTLE),
        "scheduler_account": None if LOCAL else TETRALITH_ACCOUNT,
        "repetitions": 1,
    })
    # Standard Fast Downward parsers plus our JSON-lines parser. The search
    # parser must run before the planner parser (which reads "coverage").
    exp.add_parser(exp.EXITCODE_PARSER)
    exp.add_parser(exp.TRANSLATOR_PARSER)
    exp.add_parser(exp.SINGLE_SEARCH_PARSER)
    exp.add_parser(exp.PLANNER_PARSER)
    exp.add_parser(wbh_parser.get_parser())
    return exp


def set_protocol_run_properties(exp, properties):
    """Attach immutable protocol metadata to all runs created at build time."""
    if not isinstance(exp, ProtocolFastDownwardExperiment):
        raise TypeError("expected ProtocolFastDownwardExperiment")
    overlap = set(exp.protocol_run_properties) & set(properties)
    if overlap:
        raise ValueError(
            "protocol properties already set: {}".format(
                ", ".join(sorted(overlap))))
    exp.protocol_run_properties.update(properties)


def add_algorithm(exp, name, search_expr):
    exp.add_algorithm(
        name, str(REPO), REV,
        ["--search", search_config(search_expr)],
        driver_options=[
            "--overall-time-limit", TIME_LIMIT,
            "--overall-memory-limit", MEMORY_LIMIT,
        ],
    )


def add_suite(exp, suite):
    exp.add_suite(str(BENCHMARKS), suite)


def add_standard_steps(exp, attributes):
    exp.add_step("build", exp.build)
    exp.add_step("start", exp.start_runs)
    exp.add_step("parse", exp.parse)
    exp.add_fetcher(name="fetch")
    exp.add_report(
        AbsoluteReport(attributes=attributes), name="report",
        outfile="report.html")


ATTRIBUTES = [
    "coverage", "solution_cost", "total_time", "effort", "peak_bdd_nodes",
    "expanded_bdd_nodes", "expanded_states", "expanded_bdd_pieces",
    "attempted_bdd_nodes", "attempted_states", "attempted_bdd_pieces",
    "bucket_expansions", "bucket_expansion_attempts",
    "image_events", "bucket_images",
    "image_source_buckets", "image_source_pieces", "image_calls_attempted",
    "image_calls_completed", "batched_images", "image_time",
    "raw_metrics_complete", "wbh_schema_version", "node_count_convention",
    "image_count_convention", "expansion_count_convention",
    "piece_metrics_certified", "metrics_validation_protocol",
    "metrics_validation_error",
    "expanded_buckets_single_piece",
    "partition_ratio_max", "partition_ratio_geomean", "width_upper_bound",
    "num_values", "num_terminals", "add_nodes", "construction_time",
    "heuristic_kind",
    "heuristic_size_bound", "value_cap", "construction_completed",
    "num_pruned_deadends", "pruned_deadend_states",
    "pruned_deadend_bdd_nodes", "error",
    "task_order_seed", "task_order_method",
    "driver_time_limit", "driver_memory_limit",
    "scheduler_environment", "scheduler_qos",
    "scheduler_time_limit_per_task", "scheduler_memory_per_cpu",
    "scheduler_cpus_per_task", "scheduler_array_task_throttle",
    "scheduler_account", "repetitions",
]


def hostname():
    return platform.node()


def self_test_scheduler_headers():
    """Generate prospective job texts in memory and verify array throttling."""
    class FakeStep:
        def __init__(self, name, funcname):
            self.name = name
            self._funcname = funcname

    class FakeExperiment:
        name = "prospective-header-test"

        def __init__(self, num_runs, steps):
            self.runs = [None] * num_runs
            self.steps = steps

    for num_runs in (460, 552, 644, 1050, 1404):
        environment = SeededTetralithEnvironment(
            email=None,
            qos="devel",
            time_limit_per_task="00:10:00",
            memory_per_cpu="9G",
            extra_options="#SBATCH --account={}".format(TETRALITH_ACCOUNT),
        )
        build = FakeStep("build", "build")
        start = FakeStep("start", "start_runs")
        environment.exp = FakeExperiment(num_runs, [build, start])
        start_job = environment._get_job(start, True)
        environment._assert_throttled_run_header(start_job, num_runs)

        build_header = environment._get_job_header(build, False)
        directives = [
            line for line in build_header.splitlines()
            if line.startswith(_SLURM_ARRAY_DIRECTIVE)]
        if directives != ["{}1-1".format(_SLURM_ARRAY_DIRECTIVE)]:
            raise AssertionError(
                "non-run job was throttled or changed: {!r}".format(directives))
    print(
        "prospective Slurm header tests: PASS "
        "(460, 552, 644, 1050, and 1404 runs; throttle={})".format(
            ARRAY_TASK_THROTTLE))

    for unsafe in (
            ["build", "start"], ["1", "2"], ["build", "2"],
            ["1", "start"], ["01", "002"], ["build", "0002"],
            ["0001", "start"], ["--a"], ["--al"], ["--all"]):
        try:
            reject_unsafe_combined_steps(unsafe)
        except RuntimeError:
            pass
        else:
            raise AssertionError(
                "unsafe combined prospective steps were accepted: {!r}".format(
                    unsafe))
    for safe in ([], ["build"], ["start"], ["parse", "fetch"],
                 ["--help", "--all"]):
        reject_unsafe_combined_steps(safe)
    print("prospective build/start separation tests: PASS")

    require_frozen_revision_cache("not-c280", ["parse"])
    try:
        require_frozen_revision_cache("not-c280", ["0001"])
    except RuntimeError:
        pass
    else:
        raise AssertionError("wrong revision passed the c280 cache gate")
    print("prospective revision-cache gate tests: PASS")


if __name__ == "__main__":
    self_test_scheduler_headers()
