#!/usr/bin/env python3
"""Focused acceptance check for complete state-cut cofactor profiles.

The two-bit task has an XOR exact layer at g=1. Its two residuals at the
second cut are represented by complementary CUDD pointers, so the expected
[1, 2, 2] profile guards against accidentally regularizing complement edges.
The opt-in exact self-test also exercises the extracted joint profiler on seven
golden masked-function cases. The check verifies semantic-union blind effort, a
selected heuristic ADD profile, and that adding the independent profile stream
does not change the frozen wbh.jsonl schema-v2 trace.
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DRIVER = REPO / "fast-downward.py"

TWO_BIT_SAS = """begin_version
3
end_version
begin_metric
0
end_metric
2
begin_variable
var0
-1
2
Atom v0()
NegatedAtom v0()
end_variable
begin_variable
var1
-1
2
Atom v1()
NegatedAtom v1()
end_variable
0
begin_state
0
0
end_state
begin_goal
2
0 1
1 1
end_goal
2
begin_operator
set-v0
0
1
0 0 0 1
1
end_operator
begin_operator
set-v1
0
1
0 1 0 1
1
end_operator
0
"""

SCHEMA_V2 = {
    "event": "schema",
    "version": 2,
    "node_count_convention": "inner_nodes_per_piece",
    "image_count_convention": "per_piece_attempted_completed",
    "expansion_count_convention": "completed_with_attempts",
}
PROFILE_SCHEMA_V3 = {
    "event": "schema",
    "version": 3,
    "cut_convention": (
        "unprimed_state_bits_in_cudd_level_order_including_terminal"
    ),
    "node_count_convention": "regular_cudd_inner_nodes_of_semantic_union",
    "residual_identity": (
        "canonical_signed_cudd_pointer_with_complement_polarity"
    ),
    "joint_residual_identity": (
        "cooccurring_signed_bdd_and_regular_add_pointer_pair"
    ),
    "masked_function": "heuristic_on_layer_fresh_bottom_elsewhere",
    "terminal_incidence": (
        "sum_of_reachable_nonbottom_terminals_over_regular_inner_masked_add_nodes"
    ),
    "partition_audit_effort": (
        "sum_of_regular_cudd_inner_nodes_of_nonempty_layer_value_buckets_audit_only"
    ),
}


def run(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    if result.returncode:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"command failed with exit code {result.returncode}")
    return result.stdout


def read_events(path):
    return [json.loads(line) for line in path.read_text().splitlines()]


def run_search(build, sas_file, directory, label, search):
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
    assert "Plan cost: 2" in output, output


def stable_legacy_event(event):
    # Wall-clock image time is expected to differ across separate executions.
    return {key: value for key, value in event.items() if key != "image_time"}


def validate_order_and_lengths(events):
    order = [event for event in events if event["event"] == "variable_order"]
    assert len(order) == 1, order
    order = order[0]
    assert order["state_bits"] == 2
    assert len(order["cudd_indices"]) == 2
    assert len(order["cudd_levels"]) == 2
    assert len(order["fd_variables"]) == 2
    assert len(order["fd_bit_positions"]) == 2
    assert order["cudd_levels"] == sorted(order["cudd_levels"])
    assert all(index % 2 == 0 for index in order["cudd_indices"])

    for event in events:
        if event["event"] in {"layer_profile", "heuristic_profile"}:
            assert len(event["cofactor_counts"]) == order["state_bits"] + 1
            assert event["cofactor_width"] == max(event["cofactor_counts"])
        if event["event"] == "layer_profile" and event["joint_cofactor_counts"]:
            assert (
                len(event["joint_cofactor_counts"])
                == order["state_bits"] + 1
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", default="release_no_lp")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="wbh-complete-profile-") as tmp:
        directory = Path(tmp)
        sas_file = directory / "two-bit.sas"
        sas_file.write_text(TWO_BIT_SAS)

        legacy_only = directory / "legacy-only.jsonl"
        run_search(
            args.build,
            sas_file,
            directory,
            "legacy-only",
            f'sym_fw(wbh_log="{legacy_only}")',
        )

        legacy_combined = directory / "legacy-combined.jsonl"
        blind_profile = directory / "blind-profile.jsonl"
        run_search(
            args.build,
            sas_file,
            directory,
            "combined",
            (
                f'sym_fw(wbh_log="{legacy_combined}",'
                f'wbh_profile_log="{blind_profile}",'
                "wbh_profile_self_test=true)"
            ),
        )

        legacy_only_events = read_events(legacy_only)
        legacy_combined_events = read_events(legacy_combined)
        assert legacy_only_events[0] == SCHEMA_V2
        assert legacy_combined_events[0] == SCHEMA_V2
        assert all("profile" not in event["event"] for event in legacy_combined_events)
        assert [stable_legacy_event(event) for event in legacy_only_events] == [
            stable_legacy_event(event) for event in legacy_combined_events
        ]

        blind_events = read_events(blind_profile)
        assert blind_events[0] == PROFILE_SCHEMA_V3
        validate_order_and_lengths(blind_events)
        layers = [event for event in blind_events if event["event"] == "layer_profile"]
        assert [event["g"] for event in layers] == [0, 1], layers
        assert all(event["completed"] is True for event in layers)
        assert all(event["piece_count"] >= 1 for event in layers)
        assert all(event["cofactor_counts"] == [1, 2, 2] for event in layers)
        # In particular, g=1 is XOR: its last two residuals are complements.
        assert layers[1]["cofactor_width"] == 2
        done = [event for event in blind_events if event["event"] == "done"]
        assert done == [
            {
                "event": "done",
                "layer_union_effort": sum(event["bdd_nodes"] for event in layers),
                "masked_add_effort": 0,
                "terminal_incidence_effort": 0,
                "partition_audit_effort": 0,
                "solution_cost": 2,
            }
        ]
        summary = [event for event in blind_events if event["event"] == "summary"]
        assert len(summary) == 1 and summary[0]["solved"] is True
        assert summary[0]["profiled_layer_attempts"] == 2
        assert summary[0]["profiled_layers"] == 2
        assert summary[0]["heuristic_profiled"] is False
        for key in (
            "union_seconds",
            "cofactor_seconds",
            "serialization_seconds",
            "output_seconds",
        ):
            assert summary[0][key] >= 0

        heuristic_profile = directory / "heuristic-profile.jsonl"
        run_search(
            args.build,
            sas_file,
            directory,
            "heuristic",
            (
                "sym_fw_ms(max_states=100,value_cap=4,"
                f'align_merge_order=true,wbh_profile_log="{heuristic_profile}")'
            ),
        )
        heuristic_events = read_events(heuristic_profile)
        assert heuristic_events[0] == PROFILE_SCHEMA_V3
        validate_order_and_lengths(heuristic_events)
        heuristics = [
            event for event in heuristic_events
            if event["event"] == "heuristic_profile"
        ]
        assert len(heuristics) == 1
        heuristic = heuristics[0]
        assert heuristic["cofactor_counts"][-1] == heuristic["num_terminals"]
        assert heuristic["cofactor_seconds"] >= 0
        assert not any(
            event["event"] == "layer_profile" for event in heuristic_events
        )
        summary = [
            event for event in heuristic_events if event["event"] == "summary"
        ]
        assert len(summary) == 1 and summary[0]["heuristic_profiled"] is True
        assert summary[0]["profiled_layer_attempts"] == 0
        assert summary[0]["profiled_layers"] == 0

        pdb_profile = directory / "pdb-profile.jsonl"
        run_search(
            args.build,
            sas_file,
            directory,
            "pdb-profile",
            (
                "sym_fw_pdb(budget=100,"
                "pattern_selection=exact_width_filter,"
                "cegar_max_time=1,cegar_seed=2011,"
                "cofactor_width_budget=infinity,"
                f'wbh_profile_log="{pdb_profile}")'
            ),
        )
        pdb_events = read_events(pdb_profile)
        assert pdb_events[0] == PROFILE_SCHEMA_V3
        validate_order_and_lengths(pdb_events)
        assert sum(
            event["event"] == "heuristic_profile" for event in pdb_events
        ) == 1
        layers = [
            event for event in pdb_events
            if event["event"] == "layer_profile"
        ]
        assert layers
        assert [event["g"] for event in layers] == sorted(
            {event["g"] for event in layers}
        )
        assert all(event["completed"] is True for event in layers)
        assert all(event["piece_count"] == 1 for event in layers)
        done = [event for event in pdb_events if event["event"] == "done"]
        assert len(done) == 1
        assert done[0]["layer_union_effort"] == sum(
            event["bdd_nodes"]
            for event in layers
            if event["g"] < done[0]["solution_cost"]
        )
        assert done[0]["layer_union_effort"] > 0
        summary = [
            event for event in pdb_events if event["event"] == "summary"
        ]
        assert len(summary) == 1
        assert summary[0]["heuristic_profiled"] is True
        assert summary[0]["profiled_layers"] == len(layers)

    print(
        "complete cofactor profiles passed: complement polarity, unprimed "
        "projection, blind and heuristic exact layer unions, heuristic "
        "profile, cost/effort, timings, and frozen schema-v2 invariance"
    )


if __name__ == "__main__":
    main()
