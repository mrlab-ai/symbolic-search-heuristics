#!/usr/bin/env python3
"""Q4 -- context (PR5, optional, run last).

Coverage-only comparison against Scorpion for the paper's context paragraph.
Scorpion is an external explicit-search planner (EXTERNAL BASELINE, TODO): wire
it in as a separate add_algorithm against its repo/binary, or run it separately
and merge coverage tables. Only the coverage attribute is needed here.

Do NOT launch without sign-off.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_common as C
import suite_wbh


def read_winning_m(default=8):
    path = Path(__file__).resolve().parent / "WINNING_M"
    return int(path.read_text().strip()) if path.exists() else default


def main():
    exp = C.new_experiment()
    C.add_suite(exp, suite_wbh.SMOKE if C.LOCAL else suite_wbh.suite())

    m = read_winning_m()
    C.add_algorithm(exp, f"pot_m{m}", f"sym_fw_pot(m={m})")
    C.add_algorithm(exp, "blind_bd", "sym_bd()")
    # Scorpion (external, coverage-only context) runs via
    # experiments/exp_baselines.py (the "scorpion" algorithm). Fetch its
    # properties alongside this experiment's for the combined coverage table.

    C.add_standard_steps(exp, ["coverage", "solution_cost", "total_time"])
    exp.run_steps()


if __name__ == "__main__":
    main()
