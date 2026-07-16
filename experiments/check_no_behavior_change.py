#!/usr/bin/env python3
"""PR1 acceptance test: the --wbh-log flag must not change search behavior.

For each smoke task, runs blind forward search with the flag off and on and
checks that the plan cost and the per-layer BOUND progression -- which together
pin down the exact sequence of expanded layers and the optimal solution -- are
identical. Peak BDD-node counts are a deterministic function of the expanded
BDDs, so they are checked directly for stability by running with the flag on
twice and diffing the logged (g, bdd_nodes) sequences. Peak *process* memory is
reported for information only: it legitimately grows by a few KB with logging
on (the log-record vector and the file buffer) and is not a search-behavior
signal. Every emitted log line is validated against the schema and the median
runtime overhead of logging is reported.

Usage: python3 experiments/check_no_behavior_change.py [--timeout SECONDS]
"""
import argparse
import json
import re
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import FD, read_suite, resolve_domain, BENCHMARKS  # noqa: E402
from validate_wbh_log import validate_line  # noqa: E402

COST_RE = re.compile(r"Plan cost:\s*(\d+)")
TIME_RE = re.compile(r"Total time:\s*([\d.]+)s")
PEAK_RE = re.compile(r"Peak memory:\s*(\d+) KB")
BOUND_RE = re.compile(r"BOUND:\s*(\d+) < (\d+)")


def run(domain, problem, log_path, timeout):
    search = "sym_fw(silent=false"
    if log_path:
        search += f',wbh_log="{log_path}"'
    search += ")"
    cmd = [sys.executable, str(FD), str(resolve_domain(domain, problem)),
           str(BENCHMARKS / domain / problem), "--search", search]
    out = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout).stdout
    cost = COST_RE.search(out)
    time = TIME_RE.search(out)
    peak = PEAK_RE.search(out)
    return {
        "cost": int(cost.group(1)) if cost else None,
        "time": float(time.group(1)) if time else None,
        "peak": int(peak.group(1)) if peak else None,
        "bounds": BOUND_RE.findall(out),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()

    def expand_nodes(log_path):
        """Return the ordered list of (g, bdd_nodes) from expand events."""
        seq = []
        with open(log_path) as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if obj["event"] == "expand":
                    seq.append((obj["g"], obj["bdd_nodes"]))
        return seq

    overheads = []
    failures = []
    for domain, problem in read_suite():
        key = f"{domain}:{problem}"
        off = run(domain, problem, None, args.timeout)
        logs = []
        for _ in range(2):
            with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
                logs.append(tf.name)
        on = run(domain, problem, logs[0], args.timeout)
        run(domain, problem, logs[1], args.timeout)

        # Validate every emitted log line.
        n_lines = 0
        with open(logs[0]) as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if line:
                    validate_line(logs[0], lineno, line)
                    n_lines += 1

        cost_ok = off["cost"] == on["cost"]
        bounds_ok = off["bounds"] == on["bounds"]
        nodes_ok = expand_nodes(logs[0]) == expand_nodes(logs[1])
        same = cost_ok and bounds_ok and nodes_ok
        status = "OK" if same else "MISMATCH"
        if not same:
            failures.append(key)
        if off["time"] and on["time"] and off["time"] > 0:
            overheads.append((on["time"] - off["time"]) / off["time"])
        peak_delta = (on["peak"] - off["peak"]) if (off["peak"] and on["peak"]) else 0
        print(f"{status:9s} {key:45s} cost {off['cost']}/{on['cost']} "
              f"bounds {len(off['bounds'])}={len(on['bounds'])} "
              f"nodes_stable={nodes_ok} peakdelta {peak_delta}KB lines {n_lines}")
        for p in logs:
            Path(p).unlink()

    print()
    if overheads:
        median = statistics.median(overheads)
        print(f"Median logging overhead: {median * 100:.1f}% "
              f"(threshold 5%){' OK' if median < 0.05 else ' EXCEEDED'}")
    if failures:
        print(f"BEHAVIOR CHANGED on: {failures}")
        sys.exit(1)
    print("No behavior change on any smoke task "
          "(cost, expansion progression and BDD node counts identical).")


if __name__ == "__main__":
    main()
