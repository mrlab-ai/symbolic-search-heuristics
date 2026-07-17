#!/usr/bin/env python3
"""Pruning-only width-bounded search sweep (paper Cor. cor-prune).

Runs the prune_only=true variants of all three families plus blind forward
as the reference. Same suite, parser and limits as exp_q1.

Dry run: WBH_LOCAL=1 python3 experiments/exp_prune.py build start parse fetch report
Sweep:   python3 experiments/exp_prune.py   (Tetralith)
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
    C.add_algorithm(exp, "pot_m8_prune", "sym_fw_pot(m=8, prune_only=true)")
    C.add_algorithm(
        exp, "pdb_prune", "sym_fw_pdb(budget=100000, prune_only=true)")
    C.add_algorithm(
        exp, "ms_prune", "sym_fw_ms(max_states=10000, prune_only=true)")
    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
