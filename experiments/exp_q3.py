#!/usr/bin/env python3
"""Q3 -- main comparison (PR5).

Winning-M forward search vs
  (a) SymK blind forward       -- sym_fw()
  (b) SymK blind bidirectional -- sym_bd()   (default strong config)
  (c) CPDDL I/I operator potentials           -- external diagnostic
  (d) CPDDL blind bidirectional               -- SymBA* stand-in only

Success criterion (historical paper plan): among the domains where the
external potential baseline loses coverage to
blind bidirectional (~14 expected; recompute from runs (c) vs (b)), the capped
configuration recovers at least half while retaining >= 80% of its aggregate
coverage gains elsewhere. The executed CPDDL command used ``I/I``, however,
not the planned A+I configuration, so do not present this criterion as an A+I
comparison.

The winning M is read from experiments/WINNING_M (frozen after Q2). The
external configurations run through CPDDL in ``exp_baselines.py``. Its blind
configuration is a stand-in, not an execution of the original IPC-2014 SymBA*
binary.

Do NOT launch the full sweep without sign-off (Oct 25 gate).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_common as C
import suite_wbh


def read_winning_m(default=8):
    path = Path(__file__).resolve().parent / "WINNING_M"
    if path.exists():
        return int(path.read_text().strip())
    return default


def main():
    exp = C.new_experiment()
    C.add_suite(exp, suite_wbh.SMOKE if C.LOCAL else suite_wbh.suite())

    m = read_winning_m()
    C.add_algorithm(exp, f"pot_m{m}", f"sym_fw_pot(m={m})")
    C.add_algorithm(exp, "blind_fw", "sym_fw()")
    C.add_algorithm(exp, "blind_bd", "sym_bd()")
    # The external diagnostics (c) CPDDL I/I and (d) CPDDL blind run via
    # experiments/exp_baselines.py (cpddl_i_i, cpddl_blind_bi), which invokes
    # the pre-built CPDDL planner in ../baselines. Fetch its properties alongside
    # this experiment's and build a combined per-domain coverage table. They
    # are separate experiments because the baselines are not Fast Downward
    # repositories and were vendored without git history.

    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
