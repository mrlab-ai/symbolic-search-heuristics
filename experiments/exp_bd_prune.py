#!/usr/bin/env python3
"""Bidirectional width-bounded pruning sweep (sym_bd_ms vs sym_bd).

The headline comparison: blind bidirectional search (the practically
strongest symbolic configuration) against the same search with
merge-and-shrink pruning in both directions. sym_bd_ms supports zero-cost
tasks (pruning soundness needs only admissibility), so this runs on the FULL
suite, like sym_bd.

Dry run: WBH_LOCAL=1 python3 experiments/exp_bd_prune.py build start parse fetch report
Sweep:   python3 experiments/exp_bd_prune.py   (Tetralith)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_common as C
import suite_wbh


def main():
    exp = C.new_experiment()
    C.add_suite(exp, suite_wbh.SMOKE if C.LOCAL else suite_wbh.suite())
    C.add_algorithm(exp, "blind_bd", "sym_bd()")
    C.add_algorithm(exp, "bd_ms10k", "sym_bd_ms(max_states=10000)")
    C.add_algorithm(exp, "bd_ms100k", "sym_bd_ms(max_states=100000)")
    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
