#!/usr/bin/env python3
"""Acceptance test for budget-bounded pattern database heuristic search.

For each positive-cost smoke task, runs the two legacy prefixes plus the new
budget-filling and CEGAR strategies. It checks that sampled BDD lookups equal
explicit PDB lookups, the requested selection mode was used, the exact
cofactor width respects its ADD-derived upper bound, and solution costs are
optimal. Zero-cost tasks are skipped.
"""
import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import FD, read_suite, resolve_domain, BENCHMARKS  # noqa: E402

COST_RE = re.compile(r"Plan cost:\s*(\d+)")
SELFCHECK_RE = re.compile(r"PDB level-set self-check passed \((\d+)")
PATTERN_RE = re.compile(
    r"PDB pattern selection=([a-z_]+) \((\d+) vars")
WIDTH_RE = re.compile(
    r"wbh PDB heuristic:.*cofactor_width=(\d+), "
    r"width_upper_bound=(\d+)")
MODES = [
    ("legacy-bdd", "sym_fw_pdb(budget=100000,goal_directed=false)",
     "bdd_order"),
    ("legacy-goal", "sym_fw_pdb(budget=100000,goal_directed=true)",
     "goal_directed"),
    ("goal-fill", "sym_fw_pdb(budget=100000,pattern_selection=goal_fill)",
     "goal_fill"),
    ("cegar", "sym_fw_pdb(budget=100000,pattern_selection=cegar,"
     "cegar_max_time=2,cegar_seed=2011)", "cegar"),
]


def run(domain, problem, search, timeout):
    build = os.environ.get("DOWNWARD_BUILD", "release")
    cmd = [sys.executable, str(FD), "--build", build,
           str(resolve_domain(domain, problem)),
           str(BENCHMARKS / domain / problem), "--search", search]
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout)
    return result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--limit", type=int, default=None,
        help="test only the first N smoke tasks")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")

    failures = []
    suite = read_suite()
    if args.limit is not None:
        suite = suite[:args.limit]
    for domain, problem in suite:
        key = f"{domain}:{problem}"
        blind = run(domain, problem, "sym_fw()", args.timeout)
        blind_cost = COST_RE.search(blind)
        blind_cost = int(blind_cost.group(1)) if blind_cost else None

        results = []
        for mode_name, search, expected_selection in MODES:
            out = run(domain, problem, search, args.timeout)
            cost_match = COST_RE.search(out)
            results.append({
                "mode": mode_name,
                "selection": expected_selection,
                "cost": int(cost_match.group(1)) if cost_match else None,
                "unsupported":
                    "requires positive operator costs" in out,
                "selfcheck": SELFCHECK_RE.search(out),
                "pattern": PATTERN_RE.search(out),
                "width": WIDTH_RE.search(out),
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
            width = result["width"]
            if not selfcheck:
                failures.append(
                    f"{key} {mode_name}: PDB self-check did not run/pass")
                row_ok = False
            if not pattern or pattern.group(1) != result["selection"]:
                failures.append(
                    f"{key} {mode_name}: pattern selection line missing/wrong")
                row_ok = False
            if not width:
                failures.append(
                    f"{key} {mode_name}: exact cofactor width line missing")
                row_ok = False
            elif int(width.group(1)) > int(width.group(2)):
                failures.append(
                    f"{key} {mode_name}: exact width {width.group(1)} exceeds "
                    f"upper bound {width.group(2)}")
                row_ok = False
            if cost != blind_cost:
                failures.append(
                    f"{key} {mode_name}: cost {cost} != optimal {blind_cost}")
                row_ok = False
            columns.append(
                f"{mode_name}:cost={cost},"
                f"pattern={pattern.group(2) if pattern else '?'}vars,"
                f"width={width.group(1) if width else '?'}/"
                f"{width.group(2) if width else '?'},"
                f"check={selfcheck.group(1) if selfcheck else 'NO'}")

        print(f"{'OK' if row_ok else 'FAIL':5s} {key:45s} "
              f"optimal={blind_cost}  " + "  ".join(columns))

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("PDB acceptance passed: legacy, budget-filling, and CEGAR patterns "
          "have optimal costs, exact widths, and BDD lookup equals explicit "
          "PDB lookup.")


if __name__ == "__main__":
    main()
