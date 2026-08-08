#!/usr/bin/env python3
"""Predeclared 50-task pilot for merge-and-shrink terminal value caps.

The manifest was selected from archived exp_ms outcomes before running the
new configurations. It balances blind-only resource wins, exact-M&S-only
wins, and jointly solved controls across domains. Each run gets 300 seconds
and 8 GiB. The cap sweep tests the consistent transform min(h_MS, K).

Usage:
  experiments/.venv/bin/python experiments/exp_ms_caps_pilot.py build start
  experiments/.venv/bin/python experiments/exp_ms_caps_pilot.py parse fetch report
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_common as C


MANIFEST = Path(__file__).with_name("ms_caps_pilot_suite.txt")
CAPS = [2, 4, 8, 16, 32]


def read_manifest():
    tasks = []
    for line in MANIFEST.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tasks.append(line)
    assert len(tasks) == 50, len(tasks)
    assert len({task.split(":", 1)[0] for task in tasks}) == 25
    return tasks


def main():
    # Freeze pilot limits independently of the full-suite defaults.
    C.TIME_LIMIT = "300s"
    C.MEMORY_LIMIT = "8G"

    exp = C.new_experiment()
    C.add_suite(exp, read_manifest())
    C.add_algorithm(exp, "blind_fw", "sym_fw()")
    C.add_algorithm(
        exp, "ms_exact", "sym_fw_ms(max_states=10000,value_cap=-1)")
    for cap in CAPS:
        C.add_algorithm(
            exp, f"ms_cap{cap}",
            f"sym_fw_ms(max_states=10000,value_cap={cap})")
    C.add_standard_steps(exp, C.ATTRIBUTES)
    exp.run_steps()


if __name__ == "__main__":
    main()
