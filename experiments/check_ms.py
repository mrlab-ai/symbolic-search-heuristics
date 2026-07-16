#!/usr/bin/env python3
"""Acceptance test for the linear merge-and-shrink heuristic search (sym_fw_ms).

For each positive-cost smoke task: sym_fw_ms must find the optimal cost (equal
to blind sym_fw), and the in-planner M&S level-set self-check (BDD lookup ==
abstraction lookup on sampled states) must pass. Zero-cost tasks are skipped.

Usage: python3 experiments/check_ms.py [--timeout SECONDS]
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import FD, read_suite, resolve_domain, BENCHMARKS  # noqa: E402

COST_RE = re.compile(r"Plan cost:\s*(\d+)")
SELFCHECK_RE = re.compile(r"M&S level-set self-check passed \((\d+)")


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
        blind = COST_RE.search(run(domain, problem, "sym_fw()", args.timeout))
        blind_cost = int(blind.group(1)) if blind else None
        out = run(domain, problem, "sym_fw_ms(max_states=10000)", args.timeout)
        cost = COST_RE.search(out)
        cost = int(cost.group(1)) if cost else None
        selfcheck = SELFCHECK_RE.search(out)
        if cost is None:
            print(f"SKIP  {key:45s} (zero-cost / not applicable)")
            continue
        if not selfcheck:
            failures.append(f"{key}: self-check missing")
        if cost != blind_cost:
            failures.append(f"{key}: cost {cost} != optimal {blind_cost}")
        status = "OK" if cost == blind_cost and selfcheck else "FAIL"
        print(f"{status:5s} {key:45s} cost {cost}/{blind_cost} "
              f"selfcheck={selfcheck.group(1) if selfcheck else 'NO'}")

    print()
    if failures:
        print("FAILURES:\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("sym_fw_ms acceptance passed: optimal costs, BDD level sets == "
          "explicit M&S abstraction.")


if __name__ == "__main__":
    main()
