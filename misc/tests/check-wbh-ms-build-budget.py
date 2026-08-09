#!/usr/bin/env python3
"""Focused acceptance check for forward M&S construction budgets."""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DRIVER = REPO / "fast-downward.py"
TASK = REPO / "misc/tests/benchmarks/gripper/prob01.pddl"
FALLBACK_MARKER = "wbh forward M&S construction budget"
PLAN_COST_RE = re.compile(r"Plan cost:\s*(\d+)")

SCHEMA_V2 = {
    "event": "schema",
    "version": 2,
    "node_count_convention": "inner_nodes_per_piece",
    "image_count_convention": "per_piece_attempted_completed",
    "expansion_count_convention": "completed_with_attempts",
}
CONSTRUCTION_KEYS = {
    "event",
    "heuristic",
    "seconds",
    "size_bound",
    "value_cap",
    "completed",
}
SUMMARY_KEYS = {
    "event",
    "expanded_bdd_nodes",
    "expanded_states",
    "expanded_bdd_pieces",
    "attempted_bdd_nodes",
    "attempted_states",
    "attempted_bdd_pieces",
    "bucket_expansions",
    "bucket_expansion_attempts",
    "image_events",
    "bucket_images",
    "image_source_buckets",
    "image_source_pieces",
    "image_calls_attempted",
    "image_calls_completed",
    "batched_images",
    "image_time",
    "solved",
}


def run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"command failed with exit code {result.returncode}")
    return result.stdout


def run_case(build, sas_file, directory, label, search):
    log = directory / f"{label}.jsonl"
    assert search.endswith(")")
    inner = search[search.index("(") + 1 : -1].strip()
    separator = "," if inner else ""
    logged_search = (
        f"{search[:search.index('(')]}({inner}{separator}wbh_log=\"{log}\")"
    )
    output = run(
        [
            sys.executable,
            str(DRIVER),
            "--build",
            build,
            "--plan-file",
            str(directory / f"{label}.plan"),
            str(sas_file),
            "--search",
            logged_search,
        ],
        directory,
    )
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert events[0] == SCHEMA_V2
    summaries = [event for event in events if event.get("event") == "summary"]
    assert len(summaries) == 1 and set(summaries[0]) == SUMMARY_KEYS
    assert summaries[0]["solved"] is True
    assert summaries[0]["image_events"] > 0
    cost_match = PLAN_COST_RE.search(output)
    assert cost_match, output
    trace = [
        (
            event["g"],
            event["h"],
            event["completed"],
            event["piece_count"],
            event["bdd_nodes"],
            event["states"],
        )
        for event in events
        if event.get("event") == "expand"
    ]
    image_signature = [
        (
            event["g"],
            event["min_h"],
            event["max_h"],
            event["source_buckets"],
            event["source_pieces"],
            event["calls_attempted"],
            event["calls_completed"],
            event["bdd_nodes"],
            event["states"],
        )
        for event in events
        if event.get("event") == "image"
    ]
    return int(cost_match.group(1)), trace, image_signature, events, output


def get_construction(result):
    constructions = [
        event for event in result[3] if event.get("event") == "construction"
    ]
    assert len(constructions) == 1
    construction = constructions[0]
    assert set(construction) == CONSTRUCTION_KEYS
    assert construction["heuristic"] == "merge_and_shrink"
    assert construction["size_bound"] == 1000
    assert construction["value_cap"] == 16
    assert construction["seconds"] >= 0
    return construction


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", default="release_no_lp")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="wbh-ms-build-budget-") as tmp:
        directory = Path(tmp)
        sas_file = directory / "output.sas"
        run(
            [
                sys.executable,
                str(DRIVER),
                "--build",
                args.build,
                "--sas-file",
                str(sas_file),
                "--translate",
                str(TASK),
            ],
            directory,
        )

        results = {
            "blind": run_case(
                args.build, sas_file, directory, "blind", "sym_fw()"
            ),
            "fallback": run_case(
                args.build,
                sas_file,
                directory,
                "fallback",
                "sym_fw_ms(max_states=1000,value_cap=16,build_time_limit=0)",
            ),
            "legacy_ms": run_case(
                args.build,
                sas_file,
                directory,
                "legacy_ms",
                "sym_fw_ms(max_states=1000,value_cap=16)",
            ),
            "budgeted_ms": run_case(
                args.build,
                sas_file,
                directory,
                "budgeted_ms",
                "sym_fw_ms(max_states=1000,value_cap=16,build_time_limit=60)",
            ),
        }

        assert {result[0] for result in results.values()} == {11}
        assert results["fallback"][1] == results["blind"][1]
        assert results["fallback"][2] == results["blind"][2]
        assert results["budgeted_ms"][1] == results["legacy_ms"][1]
        assert results["budgeted_ms"][2] == results["legacy_ms"][2]

        fallback_events = results["fallback"][3]
        assert not any(
            event.get("event") == "heuristic" for event in fallback_events
        )
        assert get_construction(results["fallback"])["completed"] is False
        assert FALLBACK_MARKER in results["fallback"][4]

        for label in ("legacy_ms", "budgeted_ms"):
            assert get_construction(results[label])["completed"] is True
            assert sum(
                event.get("event") == "heuristic"
                for event in results[label][3]
            ) == 1
            assert FALLBACK_MARKER not in results[label][4]

    print(
        "forward M&S build-budget acceptance passed: zero-time fallback is "
        "blind-equivalent, nonbinding budget matches legacy M&S, and schema-v2 "
        "construction/summary events are valid"
    )


if __name__ == "__main__":
    main()
