#!/usr/bin/env python3
"""Bound-seeded pruning experiment (guidance as an incumbent).

Each run chains lama-first (60s, incumbent cost c) with a symbolic search
under bound=c via seeded_driver.py; all configurations get the same 30-minute
total budget, with seeding time charged to the seeded configurations. A task
counts as solved iff optimality is proved: the symbolic search finds a plan
cheaper than the seed, or exhausts the bounded space (the seed is optimal), or
solves directly (unseeded baseline).

Configurations:
  blind_bd         -- sym_bd, unseeded (the baseline; a seed provably does not
                      reduce blind search's work, only pruning converts it)
  seeded_bd_blind  -- sym_bd with the seed bound (control: quantifies what the
                      bound alone does without pruning -- earlier termination
                      of solution reporting only)
  seeded_bd_ms     -- sym_bd_ms with the seed bound (pruners active from
                      layer zero in both directions; the headline config)
  seeded_pot_prune -- sym_fw_pot(m=8, prune_only) with the seed bound
                      (forward pruning evidence; positive-cost tasks only)

Dry run: WBH_LOCAL=1 python3 experiments/exp_seeded.py build start parse fetch report
Sweep:   python3 experiments/exp_seeded.py   (Tetralith)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lab.experiment import Experiment
from lab.parser import Parser

import exp_common as C
import suite_wbh

DRIVER = Path(__file__).resolve().parent / "seeded_driver.py"
TOTAL = 120 if C.LOCAL else 1800
SEED_TIME = 30 if C.LOCAL else 60

CONFIGS = {
    "blind_bd": ("sym_bd()", False),
    "seeded_bd_blind": ("sym_bd()", True),
    "seeded_bd_ms": ("sym_bd_ms(max_states=10000)", True),
    "seeded_pot_prune": ("sym_fw_pot(m=8, prune_only=true)", True),
}


def enumerate_tasks():
    from downward import suites
    descriptions = suite_wbh.SMOKE if C.LOCAL else suite_wbh.suite()
    return [(t.domain, t.problem, t.domain_file, t.problem_file)
            for t in suites.build_suite(str(C.BENCHMARKS), descriptions)]


def get_parser():
    parser = Parser()
    parser.add_pattern(
        "seed_cost", r"SEED_COST (\d+)", type=int, required=False)
    parser.add_pattern(
        "solution_cost", r"SEEDED_RESULT cost=(\d+)", type=int,
        required=False)

    def outcome(content, props):
        props["coverage"] = 1 if "SEEDED_RESULT" in content else 0
        for via in ("better", "seed-proof", "direct"):
            if f"via={via}" in content:
                props["via"] = via
    parser.add_function(outcome, file="run.log")
    return parser


def main():
    exp = Experiment(environment=C.get_environment())

    for domain, problem, df, pf in enumerate_tasks():
        for name, (search, seed) in CONFIGS.items():
            run = exp.add_run()
            cmd = [sys.executable, str(DRIVER), str(df), str(pf), search,
                   "--total", str(TOTAL), "--seed-time", str(SEED_TIME)]
            if seed:
                cmd.append("--seed")
            # Driver enforces per-phase limits; small slack for its own
            # bookkeeping.
            run.add_command(
                "plan", cmd, time_limit=TOTAL + 120, memory_limit=8192)
            run.set_property("algorithm", name)
            run.set_property("domain", domain)
            run.set_property("problem", problem)
            run.set_property("id", [name, domain, problem])

    exp.add_parser(get_parser())
    exp.add_step("build", exp.build)
    exp.add_step("start", exp.start_runs)
    exp.add_step("parse", exp.parse)
    exp.add_fetcher(name="fetch")

    from downward.reports.absolute import AbsoluteReport
    exp.add_report(
        AbsoluteReport(
            attributes=["coverage", "solution_cost", "seed_cost", "via"]),
        name="report", outfile="report.html")

    exp.run_steps()


if __name__ == "__main__":
    main()
