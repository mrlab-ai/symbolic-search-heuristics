#!/usr/bin/env python3
"""Bound-seeded symbolic search driver (one lab run = seed + prove).

Runs lama-first for at most SEED_TIME seconds to obtain an incumbent plan of
cost c, then runs the given symbolic search with bound=c (SymK's bound is
exclusive: it searches for plans cheaper than c and, if it exhausts the space,
has proved c optimal) and the remaining time budget. Without --seed the
symbolic search runs unseeded with the full budget (baseline mode).

Outcome markers (parsed by exp_seeded.py):
  SEED_COST <c>                 -- incumbent found by lama-first
  SEEDED_RESULT cost=<x> via=<better|seed-proof|direct>
      better:     symbolic search found a plan cheaper than the seed
      seed-proof: symbolic search proved no cheaper plan exists (exit 12),
                  so the seed cost is optimal
      direct:     unseeded run found (and proved) an optimal plan
No SEEDED_RESULT marker means the task is unsolved (or proved unsolvable).

Usage:
  seeded_driver.py DOMAIN PROBLEM SEARCH [--seed] [--total T] [--seed-time S]
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FD = REPO / "fast-downward.py"
COST_RE = re.compile(r"Plan cost:\s*(\d+)")


def run_fd(args, time_limit, memory_limit="8G"):
    cmd = [sys.executable, str(FD),
           "--overall-time-limit", f"{max(1, int(time_limit))}s",
           "--overall-memory-limit", memory_limit] + args
    proc = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)
    return proc.returncode, proc.stdout


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("domain")
    parser.add_argument("problem")
    parser.add_argument("search")
    parser.add_argument("--seed", action="store_true")
    parser.add_argument("--total", type=int, default=1800)
    parser.add_argument("--seed-time", type=int, default=60)
    args = parser.parse_args()

    start = time.monotonic()
    seed_cost = None

    if args.seed:
        print(f"=== seeded_driver: lama-first ({args.seed_time}s) ===",
              flush=True)
        _, out = run_fd(
            ["--alias", "lama-first", args.domain, args.problem],
            args.seed_time)
        costs = COST_RE.findall(out)
        if costs:
            seed_cost = int(costs[-1])
            print(f"SEED_COST {seed_cost}", flush=True)
        else:
            print("=== seeded_driver: no incumbent found ===", flush=True)

    search = args.search
    if seed_cost is not None:
        inner = search[search.index("(") + 1:-1].strip()
        sep = ", " if inner else ""
        search = f"{search[:search.index('(')]}({inner}{sep}bound={seed_cost})"

    remaining = args.total - (time.monotonic() - start)
    if remaining <= 5:
        print("=== seeded_driver: no time left for symbolic search ===",
              flush=True)
        return
    print(f"=== seeded_driver: symbolic search ({int(remaining)}s): "
          f"{search} ===", flush=True)
    code, out = run_fd(
        [args.domain, args.problem, "--search", search], remaining)

    m = COST_RE.findall(out)
    if m:
        cost = int(m[-1])
        via = "better" if seed_cost is not None else "direct"
        print(f"SEEDED_RESULT cost={cost} via={via}", flush=True)
    elif code == 12 and seed_cost is not None:
        # Exit 12 (search unsolved, complete): no plan cheaper than the bound
        # exists, hence the incumbent is optimal.
        print(f"SEEDED_RESULT cost={seed_cost} via=seed-proof", flush=True)


if __name__ == "__main__":
    main()
