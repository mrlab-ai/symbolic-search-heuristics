#!/usr/bin/env python3
"""Q1 -- fragmentation validation (PR5).

Forward search with capped potentials (m=8) and prefix PDBs on the suite;
the report exposes frag_ratio_geomean against width_upper_bound (scatter them
from report.html / the parsed properties). Blind forward is included as the
width-1 anchor. The Speck et al. (2020) Pi_n family is added as a sanity anchor
when generated (see misc/gen_pin.py) and WBH_PIN_DIR points at it.

Protocol note: these search strings do not override ``mutex_type``. The
archived Q1 revision therefore used SymK's default ``MUTEX_EDELETION``, not
``MUTEX_NOT``; it must not be described as a pruning-disabled replication.

Dry run (acceptance): WBH_LOCAL=1 python3 experiments/exp_q1.py
  -- runs on Gripper + Miconic locally, parses, and writes report.html.

Full sweep (Tetralith): python3 experiments/exp_q1.py
  -- do not launch without sign-off.

Run individual steps by name, e.g.:  python3 experiments/exp_q1.py build
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_common as C
import suite_wbh


def main():
    exp = C.new_experiment()

    if C.LOCAL:
        C.add_suite(exp, suite_wbh.SMOKE)
    else:
        C.add_suite(exp, suite_wbh.suite())
        pin_dir = os.environ.get("WBH_PIN_DIR")
        if pin_dir and Path(pin_dir).exists():
            # Pi_n tasks share pin-nNN-domain.pddl per problem.
            exp.add_suite(pin_dir, [
                p.stem for p in sorted(Path(pin_dir).glob("pin-n*.pddl"))
                if "domain" not in p.stem
            ])

    # Intentionally records the actual archived protocol: no mutex_type
    # override on any config, hence MUTEX_EDELETION at the archived revision.
    C.add_algorithm(exp, "blind_fw", "sym_fw()")
    C.add_algorithm(exp, "pot_m8", "sym_fw_pot(m=8)")
    C.add_algorithm(exp, "pdb", "sym_fw_pdb(budget=100000)")
    C.add_algorithm(exp, "ms", "sym_fw_ms(max_states=10000)")

    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
