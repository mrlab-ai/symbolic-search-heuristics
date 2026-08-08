#!/usr/bin/env python3
"""External-baseline experiment for Q3/Q4 (PR5).

The comparison planners live in ../baselines as vendored, pre-built binaries
(no git history, so Downward Lab's cached-revision build cannot be used).
Instead this is a generic lab Experiment that invokes the built binaries
directly with per-run limits (30 min, 8 GiB), a small parser for coverage and
plan cost, and an absolute report.

Algorithms:
  cpddl_i_i       -- CPDDL pddl-symba, bidirectional symbolic search with a
                     single initial-state-objective potential in each
                     direction. The command is I/I, not A+I.
  cpddl_blind_bi  -- CPDDL pddl-symba, bidirectional search without
                     potentials. This is a stand-in, not the original
                     IPC-2014 SymBA* binary; that binary in baselines/symba
                     does not link on this toolchain.
  scorpion    -- Scorpion (flagship optimal cost-partitioning alias), the Q4
                 context baseline.

The checked-in ``exp_baselines-eval`` archive predates these accurate names:
its ``a_plus_i`` and ``symba_star`` identifiers mean ``cpddl_i_i`` and
``cpddl_blind_bi``, respectively. Preserve those legacy identifiers when
reading the archive, but never expand them to the claims their names suggest.

Compare with the SymK configs from exp_q3.py / exp_q1.py by fetching this
experiment's properties alongside theirs (same attributes: coverage,
solution_cost, total_time).

Dry run:  WBH_LOCAL=1 python3 experiments/exp_baselines.py build start parse fetch report
Sweep:    python3 experiments/exp_baselines.py   (Tetralith; do not launch without sign-off)
"""
import os
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab.experiment import Experiment
from lab.parser import Parser

import exp_common as C
import suite_wbh

BASELINES = C.REPO / "baselines"
CPDDL = BASELINES / "cpddl" / "bin" / "pddl-symba"
SCORPION_FD = BASELINES / "scorpion" / "fast-downward.py"
CPDDL_REVISION = "2c7de0ec0e7d1d002a08aead4c5c5bbdcf171b89"
SCORPION_REVISION = "4fd73aea3cfbb159e3ec9e61a8d2e30fb661916c"

TIME_LIMIT = 60 if C.LOCAL else 1800  # seconds
MEMORY_LIMIT = 4096 if C.LOCAL else 8192  # MiB


def cpddl_i_i_cmd(domain, problem):
    return [str(CPDDL), "--symba", "bi",
            "--symba-fw-pot", "--symba-fw-pot-cfg", "I",
            "--symba-bw-pot", "--symba-bw-pot-cfg", "I",
            str(domain), str(problem)]


def cpddl_blind_bi_cmd(domain, problem):
    return [str(CPDDL), "--symba", "bi", str(domain), str(problem)]


def scorpion_cmd(domain, problem):
    return [sys.executable, str(SCORPION_FD), "--alias", "scorpion",
            str(domain), str(problem)]


ALGORITHMS = {
    "cpddl_i_i": cpddl_i_i_cmd,
    "cpddl_blind_bi": cpddl_blind_bi_cmd,
    "scorpion": scorpion_cmd,
}

BASELINE_UPSTREAM_VENDORED_COMMITS = {
    "cpddl_i_i": CPDDL_REVISION,
    "cpddl_blind_bi": CPDDL_REVISION,
    "scorpion": SCORPION_REVISION,
}


def enumerate_tasks():
    """Return (domain, problem, domain_file, problem_file) for the suite,
    using Downward Lab's task resolver so per-problem domain files (airport,
    openstacks, parcprinter, ...) are found correctly."""
    from downward import suites
    descriptions = suite_wbh.SMOKE if C.LOCAL else suite_wbh.suite()
    tasks = []
    for t in suites.build_suite(str(C.BENCHMARKS), descriptions):
        tasks.append((t.domain, t.problem, t.domain_file, t.problem_file))
    return tasks


def get_parser():
    parser = Parser()
    # cpddl prints "Plan Cost: N"; Fast Downward/Scorpion print "Plan cost: N".
    parser.add_pattern(
        "solution_cost", r"Plan [Cc]ost: (\d+)", type=int, required=False)
    parser.add_pattern(
        "total_time", r"Total time: (.+)s", type=float, required=False)

    def coverage(content, props):
        props["coverage"] = 1 if ("PLAN FOUND" in content
                                   or "Solution found" in content) else 0
    parser.add_function(coverage, file="run.log")
    return parser


def main():
    exp = Experiment(environment=C.get_environment())

    for domain, problem, df, pf in enumerate_tasks():
        for alg, builder in ALGORITHMS.items():
            run = exp.add_run()
            command = builder(df, pf)
            run.add_command(
                "plan", command,
                time_limit=TIME_LIMIT, memory_limit=MEMORY_LIMIT)
            run.set_property("algorithm", alg)
            run.set_property("domain", domain)
            run.set_property("problem", problem)
            run.set_property("id", [alg, domain, problem])
            # The commit is contextual upstream-vendoring metadata, not an
            # attestation of the local source tree or executable. Generic Lab
            # does not add limit properties automatically, so record those and
            # the exact command explicitly for future archives.
            run.set_property(
                "baseline_upstream_vendored_commit",
                BASELINE_UPSTREAM_VENDORED_COMMITS[alg])
            run.set_property("planner_time_limit", TIME_LIMIT)
            run.set_property("planner_memory_limit", MEMORY_LIMIT)
            run.set_property("component_options", command)
            run.set_property("repetitions", 1)

    exp.add_parser(get_parser())
    # "build" writes the run directories/scripts (the binaries are prebuilt).
    exp.add_step("build", exp.build)
    exp.add_step("start", exp.start_runs)
    exp.add_step("parse", exp.parse)
    exp.add_fetcher(name="fetch")

    from downward.reports.absolute import AbsoluteReport
    exp.add_report(
        AbsoluteReport(attributes=[
            "coverage", "solution_cost", "total_time",
            "baseline_upstream_vendored_commit",
            "planner_time_limit", "planner_memory_limit", "repetitions",
        ]),
        name="report", outfile="report.html")

    exp.run_steps()


if __name__ == "__main__":
    main()
