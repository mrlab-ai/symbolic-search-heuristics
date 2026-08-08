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
import os
import platform
import subprocess
from pathlib import Path

from downward.experiment import FastDownwardExperiment
from downward.reports.absolute import AbsoluteReport
from lab.environments import LocalEnvironment, TetralithEnvironment

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


def get_environment():
    if LOCAL:
        return LocalEnvironment(processes=4)
    return TetralithEnvironment(
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
    exp = FastDownwardExperiment(environment=get_environment())
    # Standard Fast Downward parsers plus our JSON-lines parser. The search
    # parser must run before the planner parser (which reads "coverage").
    exp.add_parser(exp.EXITCODE_PARSER)
    exp.add_parser(exp.TRANSLATOR_PARSER)
    exp.add_parser(exp.SINGLE_SEARCH_PARSER)
    exp.add_parser(exp.PLANNER_PARSER)
    exp.add_parser(wbh_parser.get_parser())
    return exp


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
    "piece_metrics_certified",
    "expanded_buckets_single_piece",
    "partition_ratio_max", "partition_ratio_geomean", "width_upper_bound",
    "num_values", "num_terminals", "add_nodes", "construction_time",
    "heuristic_kind",
    "heuristic_size_bound", "value_cap", "construction_completed",
    "num_pruned_deadends", "pruned_deadend_states",
    "pruned_deadend_bdd_nodes", "error",
]


def hostname():
    return platform.node()
