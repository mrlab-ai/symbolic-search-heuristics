#!/usr/bin/env python3
"""External-baseline experiment for Q3/Q4 (PR5).

The comparison planners live in ../baselines as vendored, pre-built binaries
(no git history, so Downward Lab's cached-revision build cannot be used).
Instead this is a generic lab Experiment that invokes the built binaries
directly with per-run limits (30 min, 8 GiB), a small parser for coverage and
plan cost, and an absolute report.

Algorithms:
  a_plus_i    -- cpddl pddl-symba, bidirectional symbolic search with forward
                 and backward operator potentials (Fiser et al. AIJ 2024 A+I),
                 the Q3 (c) baseline.
  symba_star  -- cpddl pddl-symba, bidirectional symbolic search WITHOUT
                 potentials, used as the SymBA* baseline (Q3 d). We use cpddl's
                 symba (the maintained successor of Torralba's SymBA*): the
                 original IPC-2014 SymBA* in baselines/symba does not link on
                 this toolchain (old 64-bit Fast Downward preprocessor). See
                 baselines/README.md.
  scorpion    -- Scorpion (flagship optimal cost-partitioning alias), the Q4
                 context baseline.

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

TIME_LIMIT = 60 if C.LOCAL else 1800  # seconds
MEMORY_LIMIT = 4096 if C.LOCAL else 8192  # MiB


def a_plus_i_cmd(domain, problem):
    return [str(CPDDL), "--symba", "bi",
            "--symba-fw-pot", "--symba-fw-pot-cfg", "I",
            "--symba-bw-pot", "--symba-bw-pot-cfg", "I",
            str(domain), str(problem)]


def symba_star_cmd(domain, problem):
    return [str(CPDDL), "--symba", "bi", str(domain), str(problem)]


def scorpion_cmd(domain, problem):
    return [sys.executable, str(SCORPION_FD), "--alias", "scorpion",
            str(domain), str(problem)]


ALGORITHMS = {
    "a_plus_i": a_plus_i_cmd,
    "symba_star": symba_star_cmd,
    "scorpion": scorpion_cmd,
}


def enumerate_tasks():
    """Return (domain, problem, domain_file, problem_file) for the suite."""
    tasks = []
    if C.LOCAL:
        specs = [s.split(":") for s in suite_wbh.SMOKE]
    else:
        specs = []
        for domain in suite_wbh.suite():
            ddir = C.BENCHMARKS / domain
            if not ddir.is_dir():
                continue
            for pf in sorted(ddir.glob("*.pddl")):
                if "domain" in pf.name:
                    continue
                specs.append([domain, pf.name])
    for domain, problem in specs:
        pf = C.BENCHMARKS / domain / problem
        df = C.BENCHMARKS / domain / "domain.pddl"
        if not df.exists():
            df = C.BENCHMARKS / domain / (Path(problem).stem + "-domain.pddl")
        tasks.append((domain, problem, df, pf))
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
            run.add_command(
                "plan", builder(df, pf),
                time_limit=TIME_LIMIT, memory_limit=MEMORY_LIMIT)
            run.set_property("algorithm", alg)
            run.set_property("domain", domain)
            run.set_property("problem", problem)
            run.set_property("id", [alg, domain, problem])

    exp.add_parser(get_parser())
    # "build" writes the run directories/scripts (the binaries are prebuilt).
    exp.add_step("build", exp.build)
    exp.add_step("start", exp.start_runs)
    exp.add_step("parse", exp.parse)
    exp.add_fetcher(name="fetch")

    from downward.reports.absolute import AbsoluteReport
    exp.add_report(
        AbsoluteReport(attributes=["coverage", "solution_cost", "total_time"]),
        name="report", outfile="report.html")

    exp.run_steps()


if __name__ == "__main__":
    main()
