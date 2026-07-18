#!/usr/bin/env python3
"""Merge-order alignment experiment (paper Prop. prop-ms alignment condition).

Head-to-head: linear M&S BDDA* with the default causal-graph level merge
order (ms) vs the same configuration merging along the search's Gamer
variable order (ms_aligned), which satisfies the alignment condition so the
a-priori dN width bound applies. Questions: does alignment change the
measured width (in the search order) and coverage?

Sweep: python3 experiments/exp_ms_aligned.py   (Tetralith)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_common as C
import suite_wbh


def main():
    exp = C.new_experiment()
    C.add_suite(exp, suite_wbh.SMOKE if C.LOCAL else suite_wbh.suite())
    C.add_algorithm(exp, "ms", "sym_fw_ms(max_states=10000)")
    C.add_algorithm(
        exp, "ms_aligned",
        "sym_fw_ms(max_states=10000, align_merge_order=true)")
    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
