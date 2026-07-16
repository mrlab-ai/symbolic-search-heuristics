#!/usr/bin/env python3
"""Run blind symbolic forward and bidirectional search on the smoke suite and
record cost, expansions and total_time into baseline.json.

Usage: python3 experiments/run_baseline.py [--timeout SECONDS]
Requires the environment variable DOWNWARD_BENCHMARKS to point at the
downward-benchmarks checkout (default: ~/projects/benchmarks).
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FD = REPO / "fast-downward.py"
BENCHMARKS = Path(
    os.environ.get("DOWNWARD_BENCHMARKS", os.path.expanduser("~/projects/benchmarks"))
)
CONFIGS = {"sym_fw": "sym_fw()", "sym_bd": "sym_bd()"}

COST_RE = re.compile(r"Plan cost:\s*(\d+)")
TIME_RE = re.compile(r"Total time:\s*([\d.]+)s")


def read_suite():
    tasks = []
    for line in (REPO / "experiments" / "smoke_suite.txt").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        domain, problem = line.split()
        tasks.append((domain, problem))
    return tasks


def resolve_domain(domain, problem):
    """Return the domain PDDL: shared domain.pddl or per-problem <stem>-domain.pddl."""
    shared = BENCHMARKS / domain / "domain.pddl"
    if shared.exists():
        return shared
    per_problem = BENCHMARKS / domain / (Path(problem).stem + "-domain.pddl")
    return per_problem


def run(domain, problem, config, timeout):
    domain_file = resolve_domain(domain, problem)
    problem_file = BENCHMARKS / domain / problem
    cmd = [
        sys.executable, str(FD), str(domain_file), str(problem_file),
        "--search", config,
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        ).stdout
    except subprocess.TimeoutExpired:
        return {"cost": None, "total_time": None, "status": "timeout"}
    cost = COST_RE.search(out)
    time = TIME_RE.search(out)
    return {
        "cost": int(cost.group(1)) if cost else None,
        "total_time": float(time.group(1)) if time else None,
        "status": "solved" if cost else "unsolved",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    results = {}
    for domain, problem in read_suite():
        key = f"{domain}:{problem}"
        results[key] = {}
        for name, config in CONFIGS.items():
            r = run(domain, problem, config, args.timeout)
            results[key][name] = r
            print(f"{key:45s} {name:8s} cost={r['cost']} "
                  f"time={r['total_time']} {r['status']}")
    out_path = REPO / "experiments" / "baseline.json"
    out_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
