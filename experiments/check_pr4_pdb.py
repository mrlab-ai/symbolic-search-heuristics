#!/usr/bin/env python3
"""Acceptance test for budget-bounded pattern database heuristic search.

For each positive-cost smoke task, runs both BDD-order and goal-directed
sym_fw_pdb variants and checks that sampled BDD lookups equal explicit PDB
lookups, the requested selection mode was used, and solution costs are optimal.
Zero-cost tasks are skipped.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import FD, read_suite, resolve_domain, BENCHMARKS  # noqa: E402

COST_RE = re.compile(r"Plan cost:\s*(\d+)")
SELFCHECK_RE = re.compile(r"PDB level-set self-check passed \((\d+)")
PATTERN_RE = re.compile(r"(BDD-order|Goal-directed) PDB pattern \((\d+) vars")
MODES = [(False, "BDD-order"), (True, "Goal-directed")]


def run(domain, problem, search, timeout):
    cmd = [sys.executable, str(FD), str(resolve_domain(domain, problem)),
           str(BENCHMARKS / domain / problem), "--search", search]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout).stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    failures = []
    for domain, problem in read_suite():
        key = f"{domain}:{problem}"
        blind = run(domain, problem, "sym_fw()", args.timeout)
        blind_cost = COST_RE.search(blind)
        blind_cost = int(blind_cost.group(1)) if blind_cost else None

        results = []
        for goal_directed, mode_name in MODES:
            option = "true" if goal_directed else "false"
            out = run(
                domain, problem,
                f"sym_fw_pdb(budget=100000,goal_directed={option})",
                args.timeout)
            cost_match = COST_RE.search(out)
            results.append({
                "mode": mode_name,
                "cost": int(cost_match.group(1)) if cost_match else None,
                "unsupported":
                    "requires positive operator costs" in out,
                "selfcheck": SELFCHECK_RE.search(out),
                "pattern": PATTERN_RE.search(out),
            })

        if all(result["unsupported"] for result in results):
            print(f"SKIP  {key:45s} (zero-cost / not applicable)")
            continue
        if all(result["cost"] is None for result in results):
            failures.append(f"{key}: both PDB configurations failed")
            print(f"FAIL  {key:45s} both PDB configurations failed")
            continue

        row_ok = True
        columns = []
        for result in results:
            mode_name = result["mode"]
            cost = result["cost"]
            selfcheck = result["selfcheck"]
            pattern = result["pattern"]
            if not selfcheck:
                failures.append(
                    f"{key} {mode_name}: PDB self-check did not run/pass")
                row_ok = False
            if not pattern or pattern.group(1) != mode_name:
                failures.append(
                    f"{key} {mode_name}: pattern selection line missing/wrong")
                row_ok = False
            if cost != blind_cost:
                failures.append(
                    f"{key} {mode_name}: cost {cost} != optimal {blind_cost}")
                row_ok = False
            columns.append(
                f"{mode_name}:cost={cost},"
                f"pattern={pattern.group(2) if pattern else '?'}vars,"
                f"check={selfcheck.group(1) if selfcheck else 'NO'}")

        print(f"{'OK' if row_ok else 'FAIL':5s} {key:45s} "
              f"optimal={blind_cost}  " + "  ".join(columns))

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("PDB acceptance passed: BDD-order and goal-directed patterns have "
          "optimal costs and BDD lookup equals explicit PDB lookup.")


if __name__ == "__main__":
    main()
