#!/usr/bin/env python3
"""Q2 -- the width knob (PR5).

M in {0, 1, 2, 4, 8, 16, unbounded} with the initial-state objective; report
coverage, geometric-mean effort and expansions vs blind forward. The winning M
is picked from the report and frozen in experiments/WINNING_M (do this after
the full sweep).

"unbounded" is approximated by a large finite cap (the integer MIP requires a
finite bound). The heuristic's width saturates once the cap exceeds the LP
optimum magnitude (empirically around m~100 on small tasks: width_upper_bound
stops growing), while the MIP solve time grows with the cap. We therefore use a
cap that is effectively unbounded for these benchmarks yet keeps the MIP
tractable (m=10000 solves in ~1 s where m=1e6 does not). Note this in the
README.

Dry run: WBH_LOCAL=1 python3 experiments/exp_q2.py build start parse fetch report
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_common as C
import suite_wbh

M_VALUES = [0, 1, 2, 4, 8, 16]
# Effectively unbounded for these benchmarks; keeps the integer MIP tractable
# (a 1e6 box makes CPLEX hang even on trivial tasks).
UNBOUNDED_CAP = 10000


def main():
    exp = C.new_experiment()
    C.add_suite(exp, suite_wbh.SMOKE if C.LOCAL else suite_wbh.suite())

    C.add_algorithm(exp, "blind_fw", "sym_fw()")
    for m in M_VALUES:
        C.add_algorithm(exp, f"pot_m{m}", f"sym_fw_pot(m={m})")
    C.add_algorithm(
        exp, "pot_unbounded", f"sym_fw_pot(m={UNBOUNDED_CAP})")

    C.add_standard_steps(exp, C.ATTRIBUTES + ["expansions"])
    exp.run_steps()


if __name__ == "__main__":
    main()
