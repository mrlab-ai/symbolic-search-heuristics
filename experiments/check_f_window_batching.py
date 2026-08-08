#!/usr/bin/env python3
"""Acceptance test for opt-in same-g f-window image batching.

The test compares the legacy product-at-evaluation search (the default
batch_f_window=0) with positive windows. It checks:

  * every variant returns the blind optimal cost;
  * batching preserves the logical expansion trace (g, h, represented set);
  * JSON summaries distinguish logical bucket expansions from physical image
    calls and agree with the corresponding events; and
  * at least one tested run performs a real multi-bucket image.

Zero-cost tasks are skipped because HeuristicFwSearch deliberately supports
only positive operator costs.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import (  # noqa: E402
    BENCHMARKS,
    FD,
    read_suite,
    resolve_domain,
)
from validate_wbh_log import validate_line  # noqa: E402


COST_RE = re.compile(r"Plan cost:\s*(\d+)")
FAMILIES = {
    "ms": "sym_fw_ms(max_states=10000,value_cap=16{batch})",
    "pdb": (
        "sym_fw_pdb(budget=100000,goal_directed=true{batch})"
    ),
    "pot": "sym_fw_pot(m=8{batch})",
}


def run(domain, problem, search, timeout, logged=False):
    log_path = None
    if logged:
        with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as tf:
            log_path = Path(tf.name)
        assert search.endswith(")")
        inner = search[search.index("(") + 1:-1].strip()
        separator = "," if inner else ""
        search = search[:-1] + (
            f'{separator}wbh_log="{log_path}")')
    cmd = [
        sys.executable,
        str(FD),
        str(resolve_domain(domain, problem)),
        str(BENCHMARKS / domain / problem),
        "--search",
        search,
    ]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout)
        output = result.stdout + result.stderr
        events = []
        if log_path is not None and log_path.exists():
            events = [
                json.loads(line)
                for line in log_path.read_text().splitlines()
                if line.strip()
            ]
        cost_match = COST_RE.search(output)
        return {
            "cost": int(cost_match.group(1)) if cost_match else None,
            "events": events,
            "unsupported":
                "requires positive operator costs" in output,
            "output": output,
        }
    finally:
        if log_path is not None:
            log_path.unlink(missing_ok=True)


def expansion_trace(events):
    # This deterministic observable signature catches changes in logical
    # selection order, represented-state cardinality, and BDD representation.
    return [
        (event["g"], event["h"], event["bdd_nodes"], event["states"])
        for event in events
        if event.get("event") == "expand" and event["completed"]
    ]


def validate_stats(label, events, failures):
    for lineno, event in enumerate(events, 1):
        try:
            validate_line(label, lineno, json.dumps(event))
        except ValueError as err:
            failures.append(str(err))

    schemas = [e for e in events if e.get("event") == "schema"]
    expands = [e for e in events if e.get("event") == "expand"]
    images = [e for e in events if e.get("event") == "image"]
    summaries = [e for e in events if e.get("event") == "summary"]
    if (len(schemas) != 1
            or schemas[0].get("version") != 2
            or schemas[0].get("node_count_convention")
            != "inner_nodes_per_piece"
            or schemas[0].get("image_count_convention")
            != "per_piece_attempted_completed"
            or schemas[0].get("expansion_count_convention")
            != "completed_with_attempts"):
        failures.append(f"{label}: missing or invalid schema-v2 event")
    if not summaries:
        failures.append(f"{label}: missing summary event")
        return images
    summary = summaries[-1]
    expected = {
        "bucket_expansions": sum(e["completed"] for e in expands),
        "bucket_expansion_attempts": len(expands),
        "expanded_bdd_nodes": sum(
            e["bdd_nodes"] for e in expands if e["completed"]),
        "expanded_states": sum(
            e["states"] for e in expands if e["completed"]),
        "expanded_bdd_pieces": sum(
            e["piece_count"] for e in expands if e["completed"]),
        "attempted_bdd_nodes": sum(e["bdd_nodes"] for e in expands),
        "attempted_states": sum(e["states"] for e in expands),
        "attempted_bdd_pieces": sum(
            e["piece_count"] for e in expands),
        "image_events": len(images),
        "bucket_images":
            sum(e["calls_completed"] for e in images),
        "image_source_buckets":
            sum(e["source_buckets"] for e in images),
        "image_source_pieces":
            sum(e["source_pieces"] for e in images),
        "image_calls_attempted":
            sum(e["calls_attempted"] for e in images),
        "image_calls_completed":
            sum(e["calls_completed"] for e in images),
        "batched_images":
            sum(e["source_buckets"] > 1 for e in images),
    }
    for key, value in expected.items():
        if summary.get(key) != value:
            failures.append(
                f"{label}: summary {key}={summary.get(key)} != {value}")
    if any(e["source_buckets"] < 1 or e["source_pieces"] < 1
           for e in images):
        failures.append(f"{label}: image with no source bucket")
    return images


def validate_blind_piece_calls(label, events, failures):
    expands = [e for e in events if e.get("event") == "expand"]
    images = [e for e in events if e.get("event") == "image"]
    if len(expands) != len(images):
        failures.append(
            f"{label}: {len(expands)} expansion attempts but "
            f"{len(images)} image events")
        return
    for index, (expand, image) in enumerate(zip(expands, images)):
        pieces = expand["piece_count"]
        if (not expand["completed"]
                or image["source_buckets"] != 1
                or image["source_pieces"] != pieces
                or image["calls_attempted"] != pieces
                or image["calls_completed"] != pieces):
            failures.append(
                f"{label}: image {index} piece/call counts disagree: "
                f"expand={expand}, image={image}")
        if expand["bdd_nodes"] < 0 or image["bdd_nodes"] < 0:
            failures.append(f"{label}: negative inner-node count")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument(
        "--limit", type=int, default=8,
        help="number of leading smoke-suite tasks to test")
    parser.add_argument(
        "--families", nargs="+", choices=sorted(FAMILIES), default=["ms"],
        help="heuristic families to test")
    parser.add_argument(
        "--windows", nargs="+", type=int, default=[4, 16])
    args = parser.parse_args()
    if args.limit < 1 or any(window <= 0 for window in args.windows):
        parser.error("--limit and every --windows value must be positive")

    failures = []
    total_batched_images = 0
    tasks_tested = 0
    for domain, problem in read_suite()[:args.limit]:
        task = f"{domain}:{problem}"
        blind = run(
            domain, problem, "sym_fw()", args.timeout, logged=True)
        if blind["cost"] is None:
            failures.append(f"{task}: blind reference did not solve")
            continue
        validate_stats(f"{task}/blind", blind["events"], failures)
        validate_blind_piece_calls(
            f"{task}/blind", blind["events"], failures)

        task_supported = False
        for family in args.families:
            template = FAMILIES[family]
            legacy_search = template.format(batch="")
            legacy = run(
                domain, problem, legacy_search, args.timeout, logged=True)
            if legacy["unsupported"]:
                continue
            task_supported = True
            label = f"{task}/{family}/legacy"
            validate_stats(label, legacy["events"], failures)
            if legacy["cost"] != blind["cost"]:
                failures.append(
                    f"{label}: cost {legacy['cost']} != blind "
                    f"{blind['cost']}")
            legacy_trace = expansion_trace(legacy["events"])

            columns = [
                f"legacy:exp={len(legacy_trace)},"
                f"img={sum(e.get('event') == 'image' for e in legacy['events'])}"
            ]
            for window in args.windows:
                search = template.format(
                    batch=f",batch_f_window={window}")
                result = run(
                    domain, problem, search, args.timeout, logged=True)
                run_label = f"{task}/{family}/window={window}"
                images = validate_stats(
                    run_label, result["events"], failures)
                batched = sum(e["source_buckets"] > 1 for e in images)
                total_batched_images += batched
                trace = expansion_trace(result["events"])
                if result["cost"] != blind["cost"]:
                    failures.append(
                        f"{run_label}: cost {result['cost']} != blind "
                        f"{blind['cost']}")
                if trace != legacy_trace:
                    failures.append(
                        f"{run_label}: logical expansion trace differs from "
                        "legacy")
                if len(images) > len([
                        e for e in legacy["events"]
                        if e.get("event") == "image"]):
                    failures.append(
                        f"{run_label}: batching increased physical image "
                        "count")
                columns.append(
                    f"w{window}:exp={len(trace)},img={len(images)},"
                    f"batched={batched}")
            print(f"OK?   {task:45s} {family:3s}  " + "  ".join(columns))
        if task_supported:
            tasks_tested += 1
        else:
            print(f"SKIP  {task:45s} (zero-cost / unsupported)")

    if tasks_tested == 0:
        failures.append("no supported positive-cost task was tested")
    if total_batched_images == 0:
        failures.append(
            "no multi-bucket image occurred; choose a wider window or more "
            "tasks")

    print()
    if failures:
        print("FAILURES:")
        for failure in failures:
            print("  " + failure)
        return 1
    print(
        "f-window batching acceptance passed: optimal costs and logical "
        "expansion traces match legacy; physical image accounting is exact; "
        f"{total_batched_images} multi-bucket images observed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
