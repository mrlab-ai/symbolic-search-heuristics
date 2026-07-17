#!/usr/bin/env python3
"""Symbolic bidirectional blind baseline (sym_bd) sweep -- the strong SymK
baseline for the Q3 comparison. Same suite/parser/limits as exp_q1.

Sweep: python3 experiments/exp_blind_bd.py   (Tetralith)
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
    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
