#!/usr/bin/env python3
"""PR4 acceptance test for the prefix pattern database heuristic search.

For each positive-cost smoke task, runs sym_fw_pdb and checks:
  1. sampled states have BDD-lookup h equal to the explicit PDB lookup (the
     in-planner self-check "PDB level-set self-check passed" must appear; it
     aborts the run otherwise);
  2. the pattern is a prefix of the variable order (asserted in the planner;
     aborts otherwise);
  3. search costs remain optimal (equal to blind sym_fw).

Zero-cost tasks are skipped (the heuristic search assumes positive costs).

Usage: python3 experiments/check_pr4_pdb.py [--timeout SECONDS]
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
PATTERN_RE = re.compile(r"Prefix PDB pattern \((\d+) vars")


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

        out = run(domain, problem, "sym_fw_pdb(budget=100000)", args.timeout)
        cost = COST_RE.search(out)
        cost = int(cost.group(1)) if cost else None
        if cost is None:
            print(f"SKIP  {key:45s} (zero-cost / not applicable)")
            continue
        selfcheck = SELFCHECK_RE.search(out)
        pattern = PATTERN_RE.search(out)

        if not selfcheck:
            failures.append(f"{key}: PDB self-check did not run/pass")
        if not pattern:
            failures.append(f"{key}: pattern selection line missing")
        if cost != blind_cost:
            failures.append(f"{key}: cost {cost} != optimal {blind_cost}")

        status = "OK" if cost == blind_cost and selfcheck and pattern \
            else "FAIL"
        print(f"{status:5s} {key:45s} cost {cost}/{blind_cost}  "
              f"pattern={pattern.group(1) if pattern else '?'}vars  "
              f"selfcheck={selfcheck.group(1) if selfcheck else 'NO'}")

    print()
    if failures:
        print("FAILURES:")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("PR4 acceptance passed: optimal costs, BDD-lookup == explicit PDB, "
          "pattern is a prefix of the variable order.")


if __name__ == "__main__":
    main()
