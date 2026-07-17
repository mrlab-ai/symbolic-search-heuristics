#!/usr/bin/env python3
"""Bidirectional width-bounded pruning, budgeted (v2).

The first bd_prune sweep showed the M&S construction cost (p90 97s at
max_states=10000, up to the whole 30-min budget) eats more coverage than
pruning gains: bd_ms10k lost 22 tasks to blind_bd and won 3. v2 adds the
60s construction budget with fallback to blind bidirectional search, making
pruning safe including its setup cost.

Sweep: python3 experiments/exp_bd_prune2.py   (Tetralith)
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
    C.add_algorithm(exp, "bd_ms10k_b60", "sym_bd_ms(max_states=10000)")
    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
