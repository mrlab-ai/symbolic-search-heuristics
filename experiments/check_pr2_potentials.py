#!/usr/bin/env python3
"""PR2 verification for width-capped integer potentials (the parts that do not
depend on the CUDD ADD, which is built in PR3 with the search variable order).

For 5 smoke domains and M in {0,1,2,4,8}, runs A* with wbh_int_potential and
checks:
  * plan cost equals the known optimum (consistency + admissibility);
  * M=0 gives initial heuristic 0 (h == 0);
  * the initial heuristic value is non-decreasing in M and never exceeds the
    optimum (admissibility);
  * the construction-time self-check reports max|P| <= M.

Usage: python3 experiments/check_pr2_potentials.py
"""
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import FD, resolve_domain, BENCHMARKS  # noqa: E402

TASKS = [
    ("gripper", "prob01.pddl"),
    ("miconic", "s1-2.pddl"),
    ("blocks", "probBLOCKS-4-0.pddl"),
    ("driverlog", "p01.pddl"),
    ("satellite", "p01-pfile1.pddl"),
]
MS = [0, 1, 2, 4, 8]

COST_RE = re.compile(r"Plan cost:\s*(\d+)")
INITH_RE = re.compile(r"Initial heuristic value for wbh_int_potential:\s*(-?\d+)")
MAXP_RE = re.compile(r"wbh_int_potential: m=(\d+), max\|P\|=(-?[\d.]+)")


def run(domain, problem, m):
    search = f"astar(wbh_int_potential(m={m}, objective=initial_state))"
    cmd = [sys.executable, str(FD), str(resolve_domain(domain, problem)),
           str(BENCHMARKS / domain / problem), "--search", search]
    out = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
    cost = COST_RE.search(out)
    inith = INITH_RE.search(out)
    maxp = MAXP_RE.search(out)
    return {
        "cost": int(cost.group(1)) if cost else None,
        "init_h": int(inith.group(1)) if inith else None,
        "max_p": float(maxp.group(2)) if maxp else None,
    }


def main():
    failures = []
    for domain, problem in TASKS:
        key = f"{domain}:{problem}"
        prev_h = None
        opt = None
        row = []
        for m in MS:
            r = run(domain, problem, m)
            row.append(f"m={m}:h={r['init_h']}(|P|<={r['max_p']})")
            if opt is None:
                opt = r["cost"]
            if r["cost"] != opt:
                failures.append(f"{key} m={m}: cost {r['cost']} != {opt}")
            if m == 0 and r["init_h"] != 0:
                failures.append(f"{key} m=0: init_h {r['init_h']} != 0")
            if r["init_h"] is not None and r["init_h"] > opt:
                failures.append(f"{key} m={m}: init_h {r['init_h']} > opt {opt}")
            if r["max_p"] is not None and r["max_p"] > m:
                failures.append(f"{key} m={m}: max|P| {r['max_p']} > m")
            if prev_h is not None and r["init_h"] is not None \
                    and r["init_h"] < prev_h:
                failures.append(
                    f"{key} m={m}: init_h {r['init_h']} < previous {prev_h}")
            prev_h = r["init_h"]
        print(f"{'OK' if not any(key in f for f in failures) else 'FAIL':5s} "
              f"{key:32s} opt={opt}  " + "  ".join(row))

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("PR2 potential checks passed (optimality, m=0 => h=0, admissible, "
          "monotone init-h, |P|<=m). ADD width stats: deferred to PR3.")


if __name__ == "__main__":
    main()
