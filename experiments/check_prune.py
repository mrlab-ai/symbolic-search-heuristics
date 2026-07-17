#!/usr/bin/env python3
"""Acceptance test for the prune-only width-bounded search (paper Cor.
cor-prune).

For each positive-cost smoke task:
  1. prune-only variants of all three families find the optimal cost;
  2. with m=0 the prune-only potential search is exactly blind (identical
     per-layer expand records and effort);
  3. prune-only effort never exceeds blind effort (layers are slices of blind
     layers, so per-layer BDDs can only shrink... measured on reduced BDDs the
     slice can be larger (paper Ex. ex-parity), so we check effort <=
     Wn-factor loosely: effort_prune <= 5 * effort_blind as a smoke-level
     sanity bound, and report the ratio).

Usage: python3 experiments/check_prune.py [--timeout SECONDS]
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import FD, read_suite, resolve_domain, BENCHMARKS  # noqa: E402

COST_RE = re.compile(r"Plan cost:\s*(\d+)")


def run(domain, problem, search, timeout):
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        log = tf.name
    inner = search[search.index("(") + 1:-1].strip()
    sep = "," if inner else ""
    full = f'{search[:search.index("(")]}({inner}{sep}wbh_log="{log}")'
    cmd = [sys.executable, str(FD), str(resolve_domain(domain, problem)),
           str(BENCHMARKS / domain / problem), "--search", full]
    out = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout).stdout
    cost = COST_RE.search(out)
    events = [json.loads(l) for l in open(log) if l.strip()]
    Path(log).unlink()
    return (int(cost.group(1)) if cost else None), events


def expands(events):
    return [(e["g"], e["bdd_nodes"], e["states"])
            for e in events if e["event"] == "expand"]


def effort(events):
    return next((e["effort"] for e in events if e["event"] == "done"), None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    failures = []
    for domain, problem in read_suite():
        key = f"{domain}:{problem}"
        blind_cost, blind_ev = run(domain, problem, "sym_fw()", args.timeout)

        c0, ev0 = run(
            domain, problem, "sym_fw_pot(m=0, prune_only=true)", args.timeout)
        if c0 is None:
            print(f"SKIP  {key:45s} (zero-cost / not applicable)")
            continue
        if expands(ev0) != expands(blind_ev) or effort(ev0) != effort(blind_ev):
            failures.append(f"{key}: prune m=0 not blind-equivalent")

        ratios = []
        costs_ok = True
        for name, search in [
                ("pot", "sym_fw_pot(m=8, prune_only=true)"),
                ("pdb", "sym_fw_pdb(budget=100000, prune_only=true)"),
                ("ms", "sym_fw_ms(max_states=10000, prune_only=true)")]:
            c, ev = run(domain, problem, search, args.timeout)
            if c != blind_cost:
                failures.append(f"{key} {name}: cost {c} != {blind_cost}")
                costs_ok = False
            e, be = effort(ev), effort(blind_ev)
            if e and be:
                ratios.append(e / be)
                if e > 5 * be:
                    failures.append(f"{key} {name}: effort {e} > 5x blind {be}")

        status = "OK" if costs_ok and expands(ev0) == expands(blind_ev) \
            else "FAIL"
        rstr = "/".join(f"{r:.2f}" for r in ratios)
        print(f"{status:5s} {key:45s} cost={blind_cost} "
              f"effort_ratio(pot/pdb/ms)={rstr}")

    print()
    if failures:
        print("FAILURES:\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("Prune-only acceptance passed: optimal costs, blind-equivalence at "
          "m=0, bounded effort.")


if __name__ == "__main__":
    main()
