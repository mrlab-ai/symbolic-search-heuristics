#!/usr/bin/env python3
"""Write the task and configuration lists of the CPDDL objective study.

  cpddl_objective_cells.py   -> symk-cpddl/holdout-objective-I/{tasks,configs}.json
"""

import json

import cpddl_ghseta_cells as Cells

COMMON = ["--fdr-tnfm"]
POT_I = ["--symba-fw-pot", "--symba-fw-pot-cfg", "I"]
CONFIGS = [
    ["cp_blind_fw", COMMON + ["--symba", "fw"], False],
    ["cp_pot_fw", COMMON + ["--symba", "fw"] + POT_I, False],
    ["cp_blind_fw_prof", COMMON + ["--symba", "fw"], True],
    ["cp_pot_fw_prof", COMMON + ["--symba", "fw"] + POT_I, True],
]


def main():
    records = {(r["domain"], r["problem"]): r
               for r in Cells.suite_cost_manifest.load_manifest()["tasks"]}
    tasks = []
    for domain, problem in Cells.cohort("holdout"):
        r = records[(domain, problem)]
        tasks.append({key: r[key] for key in (
            "domain", "problem", "domain_file", "problem_file",
            "domain_sha256", "problem_sha256")})
    out = Cells.ROOT / "holdout-objective-I"
    out.mkdir(parents=True, exist_ok=True)
    for name, data in (("tasks.json", tasks), ("configs.json", CONFIGS)):
        path = out / name
        if path.exists():
            raise SystemExit("{} already exists".format(path))
        path.write_text(json.dumps(data, indent=1) + "\n")
    print(len(tasks), "tasks,", len(CONFIGS), "configs")


if __name__ == "__main__":
    main()
