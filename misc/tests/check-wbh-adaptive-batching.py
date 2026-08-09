#!/usr/bin/env python3
"""Focused acceptance check for node-adaptive same-g contour batching.

The check uses the bundled Gripper task and verifies that disabled, accepting,
absolute-limit, and ratio-limit policies preserve the legacy logical expansion
trace and optimal cost. It also guards the exact schema-v2 image-event shape and
the single aggregate stdout diagnostic.
"""

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
SUMMARY_MARKER = "WBH adaptive batch summary:"
PLAN_COST_RE = re.compile(r"Plan cost:\s*(\d+)")

SCHEMA_V2 = {
    "event": "schema",
    "version": 2,
    "node_count_convention": "inner_nodes_per_piece",
    "image_count_convention": "per_piece_attempted_completed",
    "expansion_count_convention": "completed_with_attempts",
}
IMAGE_KEYS = {
    "event",
    "g",
    "min_h",
    "max_h",
    "source_buckets",
    "source_pieces",
    "calls_attempted",
    "calls_completed",
    "zero_cost",
    "bdd_nodes",
    "states",
    "image_time",
}


def run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"command failed with exit code {result.returncode}")
    return result.stdout


def parse_gate_summary(output):
    lines = [line for line in output.splitlines() if SUMMARY_MARKER in line]
    assert len(lines) == 1, lines
    fields = lines[0].split(SUMMARY_MARKER, 1)[1].strip()
    return {
        key.strip(): float(value.strip())
        for key, value in (field.split("=", 1) for field in fields.split(","))
    }


def run_case(build, sas_file, directory, label, extra_options):
    log = directory / f"{label}.jsonl"
    search = (
        "sym_fw_ms(max_states=1000,value_cap=16,batch_f_window=16"
        f"{extra_options},wbh_log=\"{log}\")"
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
            search,
        ],
        directory,
    )
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert events[0] == SCHEMA_V2
    images = [event for event in events if event.get("event") == "image"]
    assert images and all(set(event) == IMAGE_KEYS for event in images)
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
        for event in images
    ]
    return int(cost_match.group(1)), trace, image_signature, output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", default="release_no_lp")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="wbh-adaptive-batching-") as tmp:
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

        cases = {
            "legacy": "",
            "accept": (
                ",batch_max_union_nodes=1000000,"
                "batch_max_union_ratio=10.0"
            ),
            "node_limit": ",batch_max_union_nodes=1",
            "node_ratio": ",batch_max_union_ratio=0.1",
        }
        results = {
            label: run_case(args.build, sas_file, directory, label, options)
            for label, options in cases.items()
        }

        costs = {result[0] for result in results.values()}
        traces = {tuple(result[1]) for result in results.values()}
        assert costs == {11}, costs
        assert len(traces) == 1, "adaptive gates changed the logical A* trace"

        legacy = results["legacy"]
        accepting = results["accept"]
        assert SUMMARY_MARKER not in legacy[3]
        assert accepting[2] == legacy[2], (
            "nonbinding gates changed fixed-window image sources"
        )

        accept_summary = parse_gate_summary(accepting[3])
        node_summary = parse_gate_summary(results["node_limit"][3])
        ratio_summary = parse_gate_summary(results["node_ratio"][3])
        assert accept_summary["accepted_extras"] > 0
        assert accept_summary["rejected_node_limit"] == 0
        assert accept_summary["rejected_node_ratio"] == 0
        assert node_summary["rejected_node_limit"] > 0
        assert ratio_summary["rejected_node_ratio"] > 0
        for summary in (accept_summary, node_summary, ratio_summary):
            assert summary["eligible_extras"] == (
                summary["accepted_extras"]
                + summary["rejected_node_limit"]
                + summary["rejected_node_ratio"]
            )
            assert summary["max_candidate_union_inner_nodes"] > 0
            assert summary["max_final_union_inner_nodes"] > 0
            assert summary["max_candidate_union_ratio"] > 0
            assert summary["max_final_union_ratio"] > 0

    print(
        "adaptive batching acceptance passed: cost/trace preserved, both gates "
        "exercised, nonbinding policy matches legacy images, and schema-v2 is "
        "unchanged"
    )


if __name__ == "__main__":
    main()
