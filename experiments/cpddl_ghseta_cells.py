#!/usr/bin/env python3
"""Write the task and configuration lists of the CPDDL GHSETA* study.

  cpddl_ghseta_cells.py dev       -> symk-cpddl/dev/{tasks,configs}.json
  cpddl_ghseta_cells.py holdout   -> symk-cpddl/holdout/{tasks,configs}.json

Tasks carry their PDDL paths and SHA-256 values from the source manifest.
"""

import hashlib
import json
import sys
from pathlib import Path

import pdb_profile_harm_generality_protocol as Generality
import suite_cost_manifest

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path("/nobackup/proj/disk/dfsplan/personal/jendrik/symk-cpddl")
DEV_COHORT = SCRIPT_DIR / "fragmentation_remedy_dev_cohort.txt"
DEV_SHA256 = "5c43a5d0891d32285c248c14cfe81ab5fa308b8eeb3d3d34e7d22ee782fcda2e"
COMMON = ["--fdr-tnfm"]
POT = ["--symba-fw-pot", "--symba-fw-pot-cfg", "A+I"]
CONFIGS = [
    ["cp_blind_fw", COMMON + ["--symba", "fw"], False],
    ["cp_pot_fw", COMMON + ["--symba", "fw"] + POT, False],
    ["cp_blind_bi", COMMON + ["--symba", "bi"], False],
    ["cp_pot_bi", COMMON + ["--symba", "bi"] + POT, False],
    ["cp_blind_fw_prof", COMMON + ["--symba", "fw"], True],
    ["cp_pot_fw_prof", COMMON + ["--symba", "fw"] + POT, True],
]


def cohort(name):
    if name == "holdout":
        return [(t.domain, t.problem) for t in Generality.load_cohort()]
    raw = DEV_COHORT.read_bytes()
    if hashlib.sha256(raw).hexdigest() != DEV_SHA256:
        raise SystemExit("development cohort changed")
    return [tuple(line.split(":", 1)) for line in raw.decode().splitlines()]


def main():
    name = sys.argv[1]
    records = {(r["domain"], r["problem"]): r
               for r in suite_cost_manifest.load_manifest()["tasks"]}
    tasks = []
    for domain, problem in cohort(name):
        r = records[(domain, problem)]
        tasks.append({key: r[key] for key in (
            "domain", "problem", "domain_file", "problem_file",
            "domain_sha256", "problem_sha256")})
    out = ROOT / name
    out.mkdir(parents=True, exist_ok=True)
    for file_name, data in (("tasks.json", tasks), ("configs.json", CONFIGS)):
        path = out / file_name
        if path.exists():
            raise SystemExit("{} already exists".format(path))
        path.write_text(json.dumps(data, indent=1) + "\n")
    print(len(tasks), "tasks,", len(CONFIGS), "configs")


if __name__ == "__main__":
    main()
