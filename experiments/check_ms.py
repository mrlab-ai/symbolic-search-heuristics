#!/usr/bin/env python3
"""Acceptance test for the linear merge-and-shrink heuristic search (sym_fw_ms).

For each positive-cost smoke task and K in {4, 16, exact}, the search must
match blind optimal cost and its BDD levels must match capped explicit
abstraction lookups. Finite caps must also bound every expanded h value.
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
SELFCHECK_RE = re.compile(r"M&S level-set self-check passed \((\d+)")
VALUE_CAPS = [4, 16, -1]


def run(domain, problem, search, timeout):
    cmd = [sys.executable, str(FD), str(resolve_domain(domain, problem)),
           str(BENCHMARKS / domain / problem), "--search", search]
    return subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout).stdout


def run_logged(domain, problem, search, timeout):
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
        log = Path(tf.name)
    assert search.endswith(")")
    inner = search[search.index("(") + 1:-1].strip()
    sep = "," if inner else ""
    full = f'{search[:search.index("(")]}({inner}{sep}wbh_log="{log}")'
    try:
        out = run(domain, problem, full, timeout)
        events = [
            json.loads(line) for line in log.read_text().splitlines()
            if line.strip()]
    finally:
        log.unlink(missing_ok=True)
    return out, events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()

    failures = []
    for domain, problem in read_suite():
        key = f"{domain}:{problem}"
        blind = COST_RE.search(run(domain, problem, "sym_fw()", args.timeout))
        blind_cost = int(blind.group(1)) if blind else None

        results = []
        for cap in VALUE_CAPS:
            out, events = run_logged(
                domain, problem,
                f"sym_fw_ms(max_states=10000,value_cap={cap})",
                args.timeout)
            cost_match = COST_RE.search(out)
            results.append({
                "cap": cap,
                "cost": int(cost_match.group(1)) if cost_match else None,
                "unsupported":
                    "requires positive operator costs" in out,
                "selfcheck": SELFCHECK_RE.search(out),
                "construction": next(
                    (event for event in events
                     if event.get("event") == "construction"), None),
                "expanded_h": [
                    event["h"] for event in events
                    if event.get("event") == "expand"],
            })

        if all(result["unsupported"] for result in results):
            print(f"SKIP  {key:45s} (zero-cost / not applicable)")
            continue
        if all(result["cost"] is None for result in results):
            failures.append(f"{key}: every M&S configuration failed")
            print(f"FAIL  {key:45s} all M&S configurations failed")
            continue

        row_ok = True
        columns = []
        for result in results:
            cap = result["cap"]
            cost = result["cost"]
            selfcheck = result["selfcheck"]
            construction = result["construction"]
            expanded_h = result["expanded_h"]
            if not selfcheck:
                failures.append(f"{key} cap={cap}: self-check missing")
                row_ok = False
            if cost != blind_cost:
                failures.append(
                    f"{key} cap={cap}: cost {cost} != optimal {blind_cost}")
                row_ok = False
            if (construction is None
                    or construction.get("heuristic") != "merge_and_shrink"
                    or construction.get("value_cap") != cap
                    or construction.get("completed") is not True):
                failures.append(
                    f"{key} cap={cap}: construction metadata missing/wrong")
                row_ok = False
            over_cap = [
                value for value in expanded_h if cap >= 0 and value > cap]
            if over_cap:
                failures.append(
                    f"{key} cap={cap}: expanded h exceeds cap: {over_cap[:3]}")
                row_ok = False
            label = "exact" if cap == -1 else f"K={cap}"
            max_h = max(expanded_h) if expanded_h else "-"
            columns.append(
                f"{label}:cost={cost},maxh={max_h},"
                f"check={selfcheck.group(1) if selfcheck else 'NO'}")

        print(f"{'OK' if row_ok else 'FAIL':5s} {key:45s} "
              f"optimal={blind_cost}  " + "  ".join(columns))

    print()
    if failures:
        print("FAILURES:\n  " + "\n  ".join(failures))
        sys.exit(1)
    print("sym_fw_ms acceptance passed: exact and capped variants are optimal, "
          "BDD levels equal explicit abstraction lookups, and h respects K.")


if __name__ == "__main__":
    main()
