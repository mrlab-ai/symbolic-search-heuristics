#!/usr/bin/env python3
"""Acceptance checks for safe value-capped PDB width selection.

The capped selector is deliberately separate from the accepted P4--P6
``fixed_pool_v1`` protocol.  On a small positive-cost smoke suite this check
certifies that:

* the uncapped selector retains its exact v1 record shape;
* a fixed finite cap uses the v2 protocol and never increases width or ADD
  node/terminal count;
* the cap-grid selector uses its isolated v6 schema, exposes one invariant raw
  identity across each pattern's transforms, considers the exact producer cap
  sequence in increasing strength, and selects the strongest feasible cap per
  pattern before independently recomputed frozen cross-pattern scoring; and
* all selected transformed PDBs pass the independent lookup check and return
  the same optimal plan cost as blind symbolic search.

Usage: ``python3 experiments/check_pdb_value_caps.py [--limit N]``.
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_baseline import BENCHMARKS, FD, read_suite, resolve_domain  # noqa: E402
import exp_arrhenius_common as Common  # noqa: E402
import pdb_cap_selector_parser as CapParser  # noqa: E402


COST_RE = re.compile(r"Plan cost:\s*(\d+)")
SELFCHECK_RE = re.compile(r"PDB level-set self-check passed \((\d+)")
STATS_RE = re.compile(
    r"wbh PDB heuristic:.*cofactor_width=(\d+), "
    r"width_upper_bound=(\d+)")
SELECTOR_RE = re.compile(
    r"PDB width-selector v1 (candidate|selected): (\{.*\})")

V1_PROTOCOL = "fixed_pool_v1"
V2_PROTOCOL = "fixed_pool_value_cap_v2"
GRID_PROTOCOL = "fixed_pool_cap_grid_v6"
GRID = (0, 1, 2, 4, 8, 16, 32, 64, 128, 256)

CONFIGS = (
    (
        "exact-k8",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=8,cegar_max_time=2,cegar_seed=2011)",
        V1_PROTOCOL,
        8,
    ),
    (
        "fixed-cap1-k8",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=8,cegar_max_time=2,cegar_seed=2011,"
        "value_cap=1)",
        V2_PROTOCOL,
        8,
    ),
    (
        "cap-grid-k8",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=8,cegar_max_time=2,cegar_seed=2011,"
        "select_value_cap=true)",
        GRID_PROTOCOL,
        8,
    ),
    (
        "exact-k32",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=32,cegar_max_time=2,cegar_seed=2011)",
        V1_PROTOCOL,
        32,
    ),
    (
        "cap-grid-k32",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=32,cegar_max_time=2,cegar_seed=2011,"
        "select_value_cap=true)",
        GRID_PROTOCOL,
        32,
    ),
)


def run(domain, problem, search, timeout):
    build = os.environ.get("DOWNWARD_BUILD", "release_no_lp")
    with tempfile.TemporaryDirectory(prefix="wbh-pdb-cap-check-") as tmp:
        cmd = [
            sys.executable,
            str(FD),
            "--build",
            build,
            "--plan-file",
            str(Path(tmp) / "sas_plan"),
            str(resolve_domain(domain, problem)),
            str(BENCHMARKS / domain / problem),
            "--search",
            search,
        ]
        result = subprocess.run(
            cmd, cwd=tmp, capture_output=True, text=True, timeout=timeout)
    return result.returncode, result.stdout + result.stderr


def parse_records(output):
    return [(kind, json.loads(payload))
            for kind, payload in SELECTOR_RE.findall(output)]


def canonical_sha(value):
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def exact_raw_pool_sha(records):
    candidates = [record for kind, record in records if kind == "candidate"]
    normalized = [
        {
            key: value
            for key, value in record.items()
            if key not in {
                "cofactor_width_budget", "feasible", "rejection_reason"
            }
        }
        for record in candidates
    ]
    return canonical_sha(normalized)


def check_transformed_record(record, errors, prefix):
    cap = record["value_cap"]
    if cap < -1 or (cap > 0 and cap not in GRID):
        errors.append(f"{prefix}: unexpected cap {cap}")
    if record["cofactor_width"] > record["raw_cofactor_width"]:
        errors.append(f"{prefix}: capping increased exact width")
    if record["width_upper_bound"] > record["raw_width_upper_bound"]:
        errors.append(f"{prefix}: capping increased ADD size")
    if record["add_nodes"] > record["raw_add_nodes"]:
        errors.append(f"{prefix}: capping increased ADD inner nodes")
    if record["num_terminals"] > record["raw_num_terminals"]:
        errors.append(f"{prefix}: capping increased ADD terminals")
    if record["transformed_num_values"] > record["raw_num_values"]:
        errors.append(f"{prefix}: capping increased finite values")
    if cap >= 0 and record["transformed_num_values"] > cap + 1:
        errors.append(f"{prefix}: cap {cap} has too many finite values")
    if cap == -1 and (
            record["cofactor_width"] != record["raw_cofactor_width"] or
            record["width_upper_bound"] != record["raw_width_upper_bound"] or
            record["transformed_num_values"] != record["raw_num_values"]):
        errors.append(f"{prefix}: exact transform disagrees with raw PDB")


def score_key(record):
    mean_key = (
        (0, Fraction(0))
        if record["finite_count"] == 0
        else (1, -Fraction(record["finite_sum"], record["finite_count"]))
    )
    return (
        -int(record["initial_dead_end"]),
        -(record["initial_h"] if record["initial_h"] is not None else 0),
        mean_key,
        -Fraction(record["dead_count"], record["abstract_states"]),
        record["cofactor_width"],
        record["abstract_states"],
        tuple(record["pattern"]),
    )


def check_grid(records, width_budget, errors, prefix):
    candidates = [record for kind, record in records if kind == "candidate"]
    selected = [record for kind, record in records if kind == "selected"]
    if len(selected) != 1:
        errors.append(f"{prefix}: expected one selected record")
        return
    if any(
        record.get("cofactor_width_budget") != width_budget
        for _, record in records
    ):
        errors.append(f"{prefix}: trace width budget differs from requested K")
    by_pattern = defaultdict(list)
    for record in candidates:
        if record["abstract_states"] <= 100000:
            check_transformed_record(record, errors, prefix)
            by_pattern[tuple(record["pattern"])].append(record)
    representatives = []
    for pattern, variants in by_pattern.items():
        caps = [record["value_cap"] for record in variants]
        finite_caps = [cap for cap in caps if cap >= 0]
        expected_caps = [
            cap for cap in GRID
            if cap < variants[0]["raw_max_finite_value"]
        ]
        if caps != expected_caps + [-1]:
            errors.append(
                f"{prefix}: pattern {pattern} cap order/uniqueness changed")
        raw_fields = (
            "raw_add_nodes", "raw_num_terminals", "raw_cofactor_width",
            "raw_width_upper_bound", "raw_num_values",
            "raw_max_finite_value", "raw_finite_sum", "raw_finite_count",
            "raw_dead_count", "raw_initial_dead_end", "raw_initial_h",
            "raw_initial_value_count", "raw_value_histogram",
        )
        raw_identities = {
            tuple(record[field] for field in raw_fields)
            for record in variants
        }
        if len(raw_identities) != 1:
            errors.append(f"{prefix}: pattern {pattern} raw identity changed")
        for record in variants:
            expected_feasible = record["cofactor_width"] <= width_budget
            expected_reason = (
                None if expected_feasible else "cofactor_width_budget"
            )
            if (
                record["feasible"] is not expected_feasible
                or record["rejection_reason"] != expected_reason
            ):
                errors.append(
                    f"{prefix}: pattern {pattern} feasibility/reason changed"
                )
        feasible = [
            record for record in variants
            if record["cofactor_width"] <= width_budget
        ]
        if not feasible:
            # Infinity is deliberately preserved by every cap. A pattern's
            # abstract dead-end classifier can therefore exceed the width
            # budget even at cap zero; such a pattern has no representative.
            continue
        representatives.append(feasible[-1])
        # Width under successively finer terminal maps must not decrease.
        widths = [record["cofactor_width"] for record in variants]
        if widths != sorted(widths):
            errors.append(f"{prefix}: pattern {pattern} width is nonmonotone")
    chosen = selected[0]
    check_transformed_record(chosen, errors, prefix)
    if chosen["cofactor_width"] > width_budget:
        errors.append(f"{prefix}: selected width exceeds {width_budget}")
    key = (tuple(chosen["pattern"]), chosen["value_cap"])
    representative_keys = {
        (tuple(record["pattern"]), record["value_cap"])
        for record in representatives
    }
    if key not in representative_keys:
        errors.append(
            f"{prefix}: selected transform is not its pattern's strongest "
            "feasible cap")
    if representatives and chosen != min(representatives, key=score_key):
        errors.append(
            f"{prefix}: selected transform violates frozen cross-pattern score")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be positive")

    failures = []
    for domain, problem in read_suite()[:args.limit]:
        key = f"{domain}:{problem}"
        _, blind_output = run(domain, problem, "sym_fw()", args.timeout)
        blind_cost_match = COST_RE.search(blind_output)
        blind_cost = int(blind_cost_match.group(1)) if blind_cost_match else None
        row = []
        raw_pool_hashes = {}
        for label, search, protocol, width_budget in CONFIGS:
            returncode, output = run(domain, problem, search, args.timeout)
            prefix = f"{key} {label}"
            cost_match = COST_RE.search(output)
            cost = int(cost_match.group(1)) if cost_match else None
            records = parse_records(output)
            selected = [record for kind, record in records if kind == "selected"]
            if returncode != 0:
                failures.append(f"{prefix}: driver exit {returncode}")
            if cost != blind_cost:
                failures.append(
                    f"{prefix}: plan cost {cost} != blind {blind_cost}")
            if not SELFCHECK_RE.search(output):
                failures.append(f"{prefix}: independent PDB check missing")
            stats = STATS_RE.search(output)
            if not stats:
                failures.append(f"{prefix}: capped heuristic stats missing")
            if len(selected) != 1 or selected[0].get("protocol") != protocol:
                failures.append(f"{prefix}: wrong/missing selected protocol")
            if any(
                record.get("cofactor_width_budget") != width_budget
                for _, record in records
                if "cofactor_width_budget" in record
            ):
                failures.append(
                    f"{prefix}: trace width budget differs from requested K"
                )
            if protocol == V1_PROTOCOL and records:
                props = {}
                Common.parse_pdb_selector_log(output, props)
                if props.get(Common.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY) is not True:
                    failures.append(f"{prefix}: legacy trace parser did not certify")
                raw_pool_hashes[label] = exact_raw_pool_sha(records)
                forbidden = {
                    "value_cap", "raw_cofactor_width",
                    "raw_width_upper_bound", "raw_num_values", "add_nodes",
                    "num_terminals", "raw_add_nodes", "raw_num_terminals",
                    "raw_max_finite_value", "raw_finite_sum",
                    "raw_finite_count", "raw_dead_count",
                    "raw_initial_dead_end", "raw_initial_h",
                    "raw_initial_value_count", "raw_value_histogram",
                    "transformed_num_values",
                }
                if any(forbidden & record.keys() for _, record in records):
                    failures.append(f"{prefix}: legacy v1 record shape changed")
            elif protocol == V2_PROTOCOL and selected:
                check_transformed_record(selected[0], failures, prefix)
            elif protocol == GRID_PROTOCOL:
                props = {}
                CapParser.parse_cap_selector_log(output, props)
                if props.get(Common.PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY) is not True:
                    failures.append(f"{prefix}: cap-grid trace parser did not certify")
                else:
                    normalized_records = [
                        ("candidate", item)
                        for item in props[Common.PDB_SELECTOR_CANDIDATES_PROPERTY]
                    ] + [
                        ("selected", props[Common.PDB_SELECTOR_SELECTED_PROPERTY])
                    ]
                    check_grid(
                        normalized_records, width_budget, failures, prefix
                    )
                raw_pool_hashes[label] = props.get(
                    CapParser.RAW_POOL_SHA256_PROPERTY
                )
            row.append(
                f"{label}:cost={cost},"
                f"cap={selected[0].get('value_cap', -1) if selected else '?'},"
                f"W={selected[0].get('cofactor_width', '?') if selected else '?'}")
        for exact_label, grid_label in (
            ("exact-k8", "cap-grid-k8"),
            ("exact-k32", "cap-grid-k32"),
        ):
            if raw_pool_hashes.get(grid_label) != raw_pool_hashes.get(exact_label):
                failures.append(
                    f"{key} {grid_label}: raw pool differs from {exact_label}"
                )
        print(f"{'OK' if not any(x.startswith(key) for x in failures) else 'FAIL':5s} "
              f"{key:45s} " + "  ".join(row))

    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print("  " + failure)
        sys.exit(1)
    print("\nPDB value-cap acceptance passed: legacy isolation, safe width "
          "transforms, strongest-feasible grid selection, and optimal costs.")


if __name__ == "__main__":
    main()
