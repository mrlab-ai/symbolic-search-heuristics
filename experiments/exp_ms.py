#!/usr/bin/env python3
"""Linear merge-and-shrink family sweep (third width-bounded family).

Runs sym_fw_ms on the full suite (blind_fw included as the reference on the
same tasks). Its coverage/fragmentation results combine with exp_q1's
potential and PDB families for the Q1 comparison across all three families.
Uses the same suite, parser and limits as exp_q1.

Dry run: WBH_LOCAL=1 python3 experiments/exp_ms.py build start parse fetch report
Sweep:   python3 experiments/exp_ms.py   (Tetralith)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_common as C
import suite_wbh


def main():
    exp = C.new_experiment()
    C.add_suite(exp, suite_wbh.SMOKE if C.LOCAL else suite_wbh.suite())
    C.add_algorithm(exp, "blind_fw", "sym_fw()")
    C.add_algorithm(exp, "ms", "sym_fw_ms(max_states=10000)")
    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
