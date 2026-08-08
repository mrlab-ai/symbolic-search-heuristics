#!/usr/bin/env python3
"""Predeclared 50-task pilot for merge-and-shrink terminal value caps.

The manifest was selected from archived exp_ms outcomes before running the
new configurations. It balances archived blind-only and exact-M&S-only
coverage cases with jointly solved controls across domains; the evaluation
archive does not identify the resource cause of an unsolved run. Each run gets
300 seconds and 8 GiB. The cap sweep tests the consistent transform min(h_MS,K).

Usage:
  experiments/.venv/bin/python experiments/exp_ms_caps_pilot.py build start
  experiments/.venv/bin/python experiments/exp_ms_caps_pilot.py parse fetch report
"""
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_common as C


MANIFEST = Path(__file__).with_name("ms_caps_pilot_suite.txt")
FROZEN_REVISION = "ec8399257de93e0739046a187af4bed0b85e19ce"
MANIFEST_DIGEST = "c63a59ee2096b40c24f80db895ee2c0d22aabc2630c823b882e7f50f529a481b"
CAPS = [2, 4, 8, 16, 32]


def read_manifest():
    tasks = []
    for line in MANIFEST.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            tasks.append(line)
    assert len(tasks) == 50, len(tasks)
    assert len(set(tasks)) == 50
    assert len({task.split(":", 1)[0] for task in tasks}) == 25
    payload = "".join("{}\n".format(task) for task in tasks)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if digest != MANIFEST_DIGEST:
        raise RuntimeError(
            "pilot manifest digest changed: {} != {}".format(
                digest, MANIFEST_DIGEST))
    return tasks


def main():
    # Freeze the implementation and limits independently of later commits and
    # the full-suite defaults. This is the revision used by job 54287205.
    C.REV = FROZEN_REVISION
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
