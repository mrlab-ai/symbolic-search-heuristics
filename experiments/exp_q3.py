#!/usr/bin/env python3
"""Q3 -- main comparison (PR5).

Winning-M forward search vs
  (a) SymK blind forward       -- sym_fw()
  (b) SymK blind bidirectional -- sym_bd()   (default strong config)
  (c) Fiser et al. A+I operator potentials   -- EXTERNAL BASELINE (TODO)
  (d) SymBA*                                  -- see note

Success criterion (paper plan): among the domains where A+I loses coverage to
blind bidirectional (~14 expected; recompute from runs (c) vs (b)), the capped
configuration recovers at least half while retaining >= 80% of A+I's aggregate
coverage gains elsewhere.

The winning M is read from experiments/WINNING_M (frozen after Q2). The A+I
baseline (c) requires obtaining and building the Fiser et al. (2024) planner
(linked from the paper); wire it in as a separate add_algorithm against that
repo/binary. SymBA* (d): if a SymBA* configuration is available in this SymK
build, add it here; otherwise document its absence.

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
    # TODO(Q3): add the Fiser et al. A+I operator-potential baseline as a
    # separate add_algorithm against their planner (report their numbers from
    # our runs on our suite -- never from their paper's tables). If it does not
    # build within reasonable effort, report back before using the weaker
    # fallback (our own unconstrained-M integration).
    # TODO(Q3): add SymBA* if available in this build.

    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
