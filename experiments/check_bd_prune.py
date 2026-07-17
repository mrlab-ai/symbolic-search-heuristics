#!/usr/bin/env python3
"""Acceptance test for bidirectional width-bounded pruning (sym_bd_ms).

For every smoke task (including zero-cost ones -- pruning soundness needs only
admissibility, so sym_bd_ms supports all tasks like sym_bd):
  1. sym_bd_ms(max_states=10000) finds the same optimal cost as sym_bd;
  2. sym_bd_ms(max_states=1) (constant-zero heuristics, no pruning possible)
     also matches -- the blind-coincidence case of the paper's Cor. cor-prune.
Direction selection in bidirectional SymK is timing-based and varies
run-to-run even for sym_bd itself, so only costs are compared.

Usage: python3 experiments/check_bd_prune.py [--timeout SECONDS]
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import FD, read_suite, resolve_domain, BENCHMARKS  # noqa: E402

COST_RE = re.compile(r"Plan cost:\s*(\d+)")


def run(domain, problem, search, timeout):
    cmd = [sys.executable, str(FD), str(resolve_domain(domain, problem)),
           str(BENCHMARKS / domain / problem), "--search", search]
    out = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout).stdout
    m = COST_RE.search(out)
    return int(m.group(1)) if m else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    failures = []
    for domain, problem in read_suite():
        key = f"{domain}:{problem}"
        ref = run(domain, problem, "sym_bd()", args.timeout)
        c_prune = run(
            domain, problem, "sym_bd_ms(max_states=10000)", args.timeout)
        c_blind1 = run(domain, problem, "sym_bd_ms(max_states=1)", args.timeout)
        ok = c_prune == ref and c_blind1 == ref
        if not ok:
            failures.append(f"{key}: sym_bd={ref} prune={c_prune} n1={c_blind1}")
        print(f"{'OK' if ok else 'FAIL':5s} {key:45s} "
              f"cost bd/prune/n1 = {ref}/{c_prune}/{c_blind1}")

    print()
    if failures:
        print("FAILURES:\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("sym_bd_ms acceptance passed: optimal costs on all smoke tasks "
          "(incl. zero-cost), blind coincidence at max_states=1.")


if __name__ == "__main__":
    main()
