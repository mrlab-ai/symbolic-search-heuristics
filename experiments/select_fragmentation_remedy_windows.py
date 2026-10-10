#!/usr/bin/env python3
"""Stage 1 of the fragmentation-remedy protocol: select batching windows.

Reads the cell records of the development screen, checks that every cell
ran and that solution costs agree, and applies the selection rule of
Section 4 of fragmentation_remedy_protocol.md: per family, the window with
the highest coverage, ties by lower PAR2 (unsolved = 600 s) summed over the
cohort, remaining ties by the smaller window.  Writes a canonical summary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SCREEN = Path("/nobackup/proj/disk/dfsplan/personal/jendrik/symk-remedy-dev")
OUTPUT = SCRIPT_DIR / "artifacts" / "fragmentation-remedy" / "stage1-v1.json"
COHORT_SHA256 = "5c43a5d0891d32285c248c14cfe81ab5fa308b8eeb3d3d34e7d22ee782fcda2e"
WINDOWS = (("1", "w1"), ("8", "w8"), ("infinity", "winf"))
ORDER = {"1": 0, "8": 1, "infinity": 2}


def load(screen):
    configs = json.loads((screen / "configs.json").read_text())
    tasks = json.loads((screen / "tasks.json").read_text())
    cohort = (SCRIPT_DIR / "fragmentation_remedy_dev_cohort.txt").read_bytes()
    if hashlib.sha256(cohort).hexdigest() != COHORT_SHA256:
        raise SystemExit("development cohort changed")
    if ["{}:{}".format(*t) for t in tasks] != cohort.decode().splitlines():
        raise SystemExit("screen tasks differ from the cohort")
    cells, missing = {}, []
    for label, _ in configs:
        for domain, problem in tasks:
            path = screen / "runs" / label / "{}__{}".format(domain, problem)
            try:
                cells[(label, domain, problem)] = json.loads(
                    (path / "cell.json").read_text())
            except (OSError, ValueError):
                missing.append("{}/{}:{}".format(label, domain, problem))
    return configs, tasks, cells, missing


def summarize(configs, tasks, cells):
    conflicts = []
    for domain, problem in tasks:
        costs = {
            cells[(label, domain, problem)]["cost"]
            for label, _ in configs
            if cells[(label, domain, problem)]["cost"] is not None
        }
        if len(costs) > 1:
            conflicts.append("{}:{}".format(domain, problem))
    stats = {}
    for label, search in configs:
        solved, par2, exits = 0, 0.0, {}
        for domain, problem in tasks:
            cell = cells[(label, domain, problem)]
            exits[str(cell["exit_code"])] = exits.get(str(cell["exit_code"]), 0) + 1
            ok = (
                cell["cost"] is not None
                and "{}:{}".format(domain, problem) not in conflicts
            )
            solved += ok
            par2 += cell["total_time"] if ok else 600.0
        stats[label] = {"search": search, "solved": solved,
                        "par2_sum": round(par2, 3), "exit_codes": exits}
    selection = {}
    for family in ("ms", "pdb", "pot"):
        ranked = sorted(
            WINDOWS,
            key=lambda w: (-stats["{}_batch_{}".format(family, w[1])]["solved"],
                           stats["{}_batch_{}".format(family, w[1])]["par2_sum"],
                           ORDER[w[0]]))
        selection[family] = ranked[0][0]
    return {
        "schema": "symbolic-search-heuristics/fragmentation-remedy-stage1/v1",
        "cohort_manifest_sha256": COHORT_SHA256,
        "tasks": len(tasks),
        "configs": len(configs),
        "cost_conflicts": conflicts,
        "stats": stats,
        "selected_windows": selection,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screen", type=Path, default=SCREEN)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    configs, tasks, cells, missing = load(args.screen)
    if missing:
        print("{} cells missing, e.g. {}".format(len(missing), missing[:3]))
        return 1
    summary = summarize(configs, tasks, cells)
    raw = (json.dumps(summary, sort_keys=True, indent=1) + "\n").encode()
    if args.write:
        if OUTPUT.exists():
            raise SystemExit("stage 1 summary already exists")
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_bytes(raw)
        print(hashlib.sha256(raw).hexdigest())
    for label, record in summary["stats"].items():
        print("{:16s} {:4d} {:10.1f} {}".format(
            label, record["solved"], record["par2_sum"], record["exit_codes"]))
    print("conflicts:", summary["cost_conflicts"])
    print("selected:", summary["selected_windows"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
