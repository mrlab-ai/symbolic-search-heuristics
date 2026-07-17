#!/usr/bin/env python3
"""Combined fair coverage across all width-bounded-heuristics sweeps.

Determines the positive-cost task subset (tasks the heuristic configs support,
i.e. not flagged as zero-cost-unsupported by any of them, detected from
exit-250 run.err or a clean SEARCH_UNSUPPORTED), then reports each
configuration's coverage over that common subset and writes a per-domain
coverage CSV to results/coverage_per_domain.csv.

Usage: python3 experiments/combined_coverage.py
"""
import collections
import csv
import json
import os
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent.parent / "results"
EXPS = ["exp_q1", "exp_q2", "exp_baselines", "exp_ms", "exp_blind_bd", "exp_prune", "exp_bd_prune", "exp_bd_prune2"]
HEUR = {"pot_m8", "pdb", "ms", "pot_m0", "pot_m1", "pot_m2", "pot_m4",
        "pot_m16", "pot_unbounded", "pot_m8_prune", "pdb_prune", "ms_prune"}
# Report order; dedup keeps the first experiment that has each algorithm.
ALGS = ["blind_fw", "blind_bd", "pot_m8", "pdb", "ms",
        "pot_m8_prune", "pdb_prune", "ms_prune",
        "bd_ms10k", "bd_ms100k", "bd_ms10k_b60",
        "a_plus_i", "symba_star", "scorpion"]
EXP_ORDER = ["exp_q2", "exp_q1", "exp_ms", "exp_prune", "exp_bd_prune", "exp_bd_prune2", "exp_blind_bd", "exp_baselines"]


def load(name):
    f = DATA / f"{name}-eval" / "properties"
    return json.loads(f.read_text()) if f.exists() else {}


def is_zero_cost(r, exp):
    if r.get("coverage") or r.get("algorithm") not in HEUR:
        return False
    err = str(r.get("error", ""))
    if err in ("exitcode-250", "") or "unexplained" in err:
        p = DATA / exp / r.get("run_dir", "") / "run.err"
        try:
            return "requires positive operator" in p.read_text()
        except OSError:
            return False
    return "unsupported" in err


def main():
    allp = {e: load(e) for e in EXPS}
    zero = set()
    for e, props in allp.items():
        for r in props.values():
            if is_zero_cost(r, e):
                zero.add((r.get("domain"), r.get("problem")))

    cov = collections.defaultdict(lambda: [0, 0])
    per_domain = collections.defaultdict(lambda: collections.defaultdict(int))
    dom_tasks = collections.Counter()
    seen = collections.defaultdict(set)
    for e in EXP_ORDER:
        for r in allp.get(e, {}).values():
            a = r.get("algorithm")
            task = (r.get("domain"), r.get("problem"))
            if a not in ALGS or task in zero or task in seen[a]:
                continue
            seen[a].add(task)
            c = r.get("coverage", 0) or 0
            cov[a][0] += c
            cov[a][1] += 1
            per_domain[r.get("domain")][a] += c
    for task in seen.get("blind_fw", set()):
        dom_tasks[task[0]] += 1

    total = max((v[1] for v in cov.values()), default=0)
    print(f"positive-cost subset: {total} tasks "
          f"(zero-cost excluded: {len(zero)})")
    for a in ALGS:
        if a in cov:
            print(f"  {a:14s} {cov[a][0]:5d} / {cov[a][1]}")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / "coverage_per_domain.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["domain", "tasks"] + ALGS)
        for d in sorted(per_domain):
            w.writerow([d, dom_tasks.get(d, 0)]
                       + [per_domain[d].get(a, 0) for a in ALGS])
        w.writerow(["TOTAL", sum(dom_tasks.values())]
                   + [cov[a][0] for a in ALGS])
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
