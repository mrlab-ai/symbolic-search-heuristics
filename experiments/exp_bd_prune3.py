#!/usr/bin/env python3
"""Bidirectional width-bounded pruning, deferred construction (v3).

v2 (eager + 60s budget) reached 1041 vs blind_bd 1051: paying construction
before the first solution loses borderline tasks. v3 defers the abstraction
construction to the first solution cut (the upper-bound slice cannot prune
earlier), so the search is exactly blind bidirectional until then and the
proof phase gets the pruning. Design goal: never worse than sym_bd.

Sweep: python3 experiments/exp_bd_prune3.py   (Tetralith)
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
    C.add_algorithm(exp, "bd_ms10k_defer", "sym_bd_ms(max_states=10000)")
    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
