#!/usr/bin/env python3
"""Focused acceptance check for exact-width-filtered PDB selection.

The bundled Gripper task gives five distinct candidates at a PDB state budget
of 1000.  Their independently enumerated PDB scores exercise the empty-pattern
boundary, an intermediate exact-width cutoff, and the exact-mean tie breaker
when every candidate is feasible.
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
DRIVER = REPO / "fast-downward.py"
TASK = REPO / "misc/tests/benchmarks/gripper/prob01.pddl"

# Direct SAS avoids translator/preprocessor unsolvability shortcuts. The only
# variable starts at value 1, the goal requires value 0, and there are no
# operators, so the singleton CEGAR PDB is a decisive initial dead end.
UNSOLVABLE_SAS = """begin_version
3
end_version
begin_metric
0
end_metric
1
begin_variable
var0
-1
2
Atom goal()
NegatedAtom goal()
end_variable
0
begin_state
1
end_state
begin_goal
1
0 0
end_goal
0
0
"""

PDB_STATE_BUDGET = 1000
CEGAR_MAX_TIME = 10
CEGAR_SEED = 2011
PERMISSIVE_WIDTH_BUDGET = 1_000_000
DYNAMIC_REORDERING_ERROR = (
    "pattern_selection=exact_width_filter requires dynamic_reordering=false"
)

PLAN_COST_RE = re.compile(r"Plan cost:\s*(\d+)")
CANDIDATE_PREFIX = "PDB width-selector v1 candidate: "
SELECTED_PREFIX = "PDB width-selector v1 selected: "
FINAL_HEURISTIC_RE = re.compile(
    r"wbh PDB heuristic: pattern_size=(\d+), "
    r"selected_source=([a-z_]+), abstract_states=(\d+), "
    r"cofactor_width_budget=(\d+), values=(\d+), "
    r"cofactor_width=(\d+), width_upper_bound=(\d+)$"
)

SCHEMA_V2 = {
    "event": "schema",
    "version": 2,
    "node_count_convention": "inner_nodes_per_piece",
    "image_count_convention": "per_piece_attempted_completed",
    "expansion_count_convention": "completed_with_attempts",
}
CANDIDATE_KEYS = (
    "protocol",
    "score_version",
    "sources",
    "pattern",
    "abstract_states",
    "initial_dead_end",
    "initial_h",
    "finite_sum",
    "finite_count",
    "dead_count",
    "cofactor_width",
    "width_upper_bound",
    "cofactor_width_budget",
    "feasible",
    "rejection_reason",
)
PROTOCOL = "fixed_pool_v1"
SCORE_VERSION = (
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
)
SOURCE_ORDER = (
    "empty",
    "bdd_prefix",
    "goal_prefix",
    "goal_fill",
    "cegar",
)

# Exact score records for the bundled Gripper task at PDB_STATE_BUDGET=1000.
# finite_sum/finite_count is the exact mean over finite abstract states, and
# dead_count/abstract_states is the exact abstract dead-end fraction.
EXPECTED_CANDIDATES = {
    "empty": {
        "pattern": [],
        "abstract_states": 1,
        "initial_dead_end": False,
        "initial_h": 0,
        "finite_sum": 0,
        "finite_count": 1,
        "dead_count": 0,
        "cofactor_width": 1,
        "width_upper_bound": 1,
    },
    "bdd_prefix": {
        "pattern": [0, 1, 2, 4, 6],
        "abstract_states": 450,
        "initial_dead_end": False,
        "initial_h": 5,
        "finite_sum": 805,
        "finite_count": 276,
        "dead_count": 174,
        "cofactor_width": 39,
        "width_upper_bound": 159,
    },
    "goal_prefix": {
        "pattern": [2, 3, 4, 5, 6],
        "abstract_states": 405,
        "initial_dead_end": False,
        "initial_h": 4,
        "finite_sum": 1080,
        "finite_count": 405,
        "dead_count": 0,
        "cofactor_width": 8,
        "width_upper_bound": 33,
    },
    "goal_fill": {
        "pattern": [0, 2, 3, 4, 5, 6],
        "abstract_states": 810,
        "initial_dead_end": False,
        "initial_h": 5,
        "finite_sum": 2560,
        "finite_count": 810,
        "dead_count": 0,
        "cofactor_width": 11,
        "width_upper_bound": 50,
    },
    "cegar": {
        "pattern": [0, 1, 2, 6],
        "abstract_states": 150,
        "initial_dead_end": False,
        "initial_h": 3,
        "finite_sum": 184,
        "finite_count": 118,
        "dead_count": 32,
        "cofactor_width": 16,
        "width_upper_bound": 52,
    },
}

EXPECTED_WINNERS = {
    1: ("empty", 1),
    8: ("goal_prefix", 5),
    PERMISSIVE_WIDTH_BUDGET: ("goal_fill", 6),
}

HEURISTIC_KEYS = {
    "event",
    "add_nodes",
    "num_values",
    "num_terminals",
    "add_level_nodes",
    "width_upper_bound",
}
CONSTRUCTION_KEYS = {
    "event",
    "heuristic",
    "seconds",
    "size_bound",
    "value_cap",
    "completed",
}


def run(command, cwd, expected_returncode=0):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    output = result.stdout + result.stderr
    if result.returncode != expected_returncode:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(
            f"command returned {result.returncode}, expected "
            f"{expected_returncode}: {' '.join(map(str, command))}"
        )
    return output


def extract_json_records(output, prefix):
    payloads = []
    records = []
    for line in output.splitlines():
        marker = line.find(prefix)
        if marker == -1:
            continue
        payload = line[marker + len(prefix) :]
        record = json.loads(payload)
        assert tuple(record) == CANDIDATE_KEYS, tuple(record)
        payloads.append(payload)
        records.append(record)
    return payloads, records


def selector_key(record):
    """Independent exact implementation of the mandated lexicographic score."""
    if record["finite_count"] == 0:
        # An all-dead PDB has mean +infinity and sorts before finite means.
        mean_key = (0, Fraction(0))
    else:
        mean_key = (
            1,
            -Fraction(record["finite_sum"], record["finite_count"]),
        )
    initial_h = record["initial_h"]
    return (
        -int(record["initial_dead_end"]),
        -(initial_h if initial_h is not None else 0),
        mean_key,
        -Fraction(record["dead_count"], record["abstract_states"]),
        record["cofactor_width"],
        record["abstract_states"],
        tuple(record["pattern"]),
    )


def validate_candidate(record, source, width_budget):
    assert record["protocol"] == PROTOCOL
    assert record["score_version"] == SCORE_VERSION
    assert record["sources"] == [source]
    expected = EXPECTED_CANDIDATES[source]
    for key, value in expected.items():
        assert record[key] == value, (source, key, record[key], value)

    assert record["cofactor_width_budget"] == width_budget
    feasible = record["cofactor_width"] <= width_budget
    assert record["feasible"] is feasible
    if feasible:
        assert record["rejection_reason"] is None
    else:
        assert isinstance(record["rejection_reason"], str)
        assert record["rejection_reason"]

    assert record["finite_count"] + record["dead_count"] == record[
        "abstract_states"
    ]
    assert record["cofactor_width"] <= record["width_upper_bound"]
    if record["initial_dead_end"]:
        assert record["initial_h"] is None
    else:
        assert isinstance(record["initial_h"], int)
        assert not isinstance(record["initial_h"], bool)
        assert record["initial_h"] >= 0


def validate_wbh_events(events, selected, state_budget=PDB_STATE_BUDGET):
    assert events and events[0] == SCHEMA_V2
    assert sum(event.get("event") == "schema" for event in events) == 1

    heuristics = [event for event in events if event.get("event") == "heuristic"]
    constructions = [
        event for event in events if event.get("event") == "construction"
    ]
    assert len(heuristics) == 1, heuristics
    assert len(constructions) == 1, constructions

    heuristic = heuristics[0]
    assert set(heuristic) == HEURISTIC_KEYS
    assert heuristic["width_upper_bound"] == selected["width_upper_bound"]
    assert heuristic["add_nodes"] + heuristic["num_terminals"] == heuristic[
        "width_upper_bound"
    ]

    construction = constructions[0]
    assert set(construction) == CONSTRUCTION_KEYS
    assert construction["heuristic"] == "pdb_exact_width_filter"
    assert construction["size_bound"] == state_budget
    assert construction["value_cap"] == -1
    assert construction["completed"] is True
    assert isinstance(construction["seconds"], (int, float))
    assert not isinstance(construction["seconds"], bool)
    assert construction["seconds"] >= 0


def run_selector(build, sas_file, directory, label, width_budget):
    log = directory / f"{label}.jsonl"
    search = (
        f"sym_fw_pdb(budget={PDB_STATE_BUDGET},"
        "pattern_selection=exact_width_filter,"
        f"cofactor_width_budget={width_budget},"
        f"cegar_max_time={CEGAR_MAX_TIME},cegar_seed={CEGAR_SEED},"
        f'wbh_log="{log}")'
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

    candidate_payloads, candidates = extract_json_records(
        output, CANDIDATE_PREFIX
    )
    selected_payloads, selected_records = extract_json_records(
        output, SELECTED_PREFIX
    )
    assert len(candidates) == len(SOURCE_ORDER)
    assert [record["sources"] for record in candidates] == [
        [source] for source in SOURCE_ORDER
    ]
    assert len({tuple(record["pattern"]) for record in candidates}) == len(
        candidates
    )
    for record, source in zip(candidates, SOURCE_ORDER):
        validate_candidate(record, source, width_budget)

    assert len(selected_records) == 1
    selected = selected_records[0]
    assert selected_payloads[0] in candidate_payloads
    feasible = [record for record in candidates if record["feasible"]]
    assert feasible
    assert selected == min(feasible, key=selector_key)

    expected_source, expected_num_values = EXPECTED_WINNERS[width_budget]
    assert selected["sources"] == [expected_source]
    assert selected == candidates[SOURCE_ORDER.index(expected_source)]

    final_lines = [
        match
        for line in output.splitlines()
        if (match := FINAL_HEURISTIC_RE.search(line))
    ]
    assert len(final_lines) == 1
    final = final_lines[0]
    assert int(final.group(1)) == len(selected["pattern"])
    assert final.group(2) == expected_source
    assert int(final.group(3)) == selected["abstract_states"]
    assert int(final.group(4)) == width_budget
    assert int(final.group(5)) == expected_num_values
    assert int(final.group(6)) == selected["cofactor_width"]
    assert int(final.group(7)) == selected["width_upper_bound"]

    events = [json.loads(line) for line in log.read_text().splitlines()]
    validate_wbh_events(events, selected)
    expansions = [event for event in events if event.get("event") == "expand"]
    assert expansions
    assert expansions[0]["g"] == 0
    assert expansions[0]["h"] == selected["initial_h"]

    cost_match = PLAN_COST_RE.search(output)
    assert cost_match, output
    return {
        "cost": int(cost_match.group(1)),
        "candidate_payloads": candidate_payloads,
        "selected_payload": selected_payloads[0],
    }


def check_dynamic_reordering_rejection(build, sas_file, directory):
    search = (
        f"sym_fw_pdb(budget={PDB_STATE_BUDGET},"
        "pattern_selection=exact_width_filter,cofactor_width_budget=8,"
        "dynamic_reordering=true,"
        f"cegar_max_time={CEGAR_MAX_TIME},cegar_seed={CEGAR_SEED})"
    )
    output = run(
        [
            sys.executable,
            str(DRIVER),
            "--build",
            build,
            str(sas_file),
            "--search",
            search,
        ],
        directory,
        expected_returncode=33,
    )
    assert DYNAMIC_REORDERING_ERROR in output
    assert CANDIDATE_PREFIX not in output
    assert SELECTED_PREFIX not in output


def check_unsolvable_cegar_return(build, directory):
    log = directory / "unsolvable.jsonl"
    search = (
        "sym_fw_pdb(budget=100,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=100,cegar_max_time=10,cegar_seed=2011,"
        f'wbh_log="{log}")'
    )
    command = [
        str(REPO / "builds" / build / "bin" / "downward"),
        "--search",
        search,
        "--internal-plan-file",
        str(directory / "unsolvable.plan"),
    ]
    result = subprocess.run(
        command,
        cwd=directory,
        input=UNSOLVABLE_SAS,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    if result.returncode != 11:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(
            f"unsolvable selector returned {result.returncode}, expected 11"
        )
    _, candidates = extract_json_records(output, CANDIDATE_PREFIX)
    _, selected_records = extract_json_records(output, SELECTED_PREFIX)
    assert len(candidates) == 2, candidates
    assert len(selected_records) == 1
    selected = selected_records[0]
    decisive_sources = ["bdd_prefix", "goal_prefix", "goal_fill", "cegar"]
    assert selected["sources"] == decisive_sources, selected
    assert selected["pattern"] == [0]
    assert selected["initial_dead_end"] is True
    assert selected["initial_h"] is None
    assert selected == next(
        candidate
        for candidate in candidates
        if candidate["sources"] == decisive_sources
    )
    assert "task proved unsolvable during computation of abstraction" in output
    assert "Initial state has infinite heuristic value" in output

    events = [json.loads(line) for line in log.read_text().splitlines()]
    validate_wbh_events(events, selected, state_budget=100)
    assert sum(event.get("event") == "summary" for event in events) == 1
    summary = next(event for event in events if event.get("event") == "summary")
    assert summary["solved"] is False
    assert not any(event.get("event") == "done" for event in events)


def check_legacy_cegar_immediate_exit(build, directory):
    search = (
        "sym_fw_pdb(budget=100,pattern_selection=cegar,"
        "cegar_max_time=10,cegar_seed=2011)"
    )
    result = subprocess.run(
        [
            str(REPO / "builds" / build / "bin" / "downward"),
            "--search",
            search,
        ],
        cwd=directory,
        input=UNSOLVABLE_SAS,
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 11, result.returncode
    assert "task is unsolvable." in output
    assert (
        "task proved unsolvable during computation of abstraction" not in output
    )
    assert CANDIDATE_PREFIX not in output
    assert SELECTED_PREFIX not in output
    assert "wbh PDB heuristic:" not in output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", default="release_no_lp")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="wbh-pdb-width-selector-") as tmp:
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

        blind_output = run(
            [
                sys.executable,
                str(DRIVER),
                "--build",
                args.build,
                "--plan-file",
                str(directory / "blind.plan"),
                str(sas_file),
                "--search",
                "sym_fw()",
            ],
            directory,
        )
        blind_cost_match = PLAN_COST_RE.search(blind_output)
        assert blind_cost_match, blind_output
        blind_cost = int(blind_cost_match.group(1))
        assert blind_cost == 11

        results = {
            "k1": run_selector(args.build, sas_file, directory, "k1", 1),
            "k8_a": run_selector(args.build, sas_file, directory, "k8-a", 8),
            "k8_b": run_selector(args.build, sas_file, directory, "k8-b", 8),
            "permissive": run_selector(
                args.build,
                sas_file,
                directory,
                "permissive",
                PERMISSIVE_WIDTH_BUDGET,
            ),
        }

        assert {result["cost"] for result in results.values()} == {blind_cost}
        assert results["k8_a"]["candidate_payloads"] == results["k8_b"][
            "candidate_payloads"
        ]
        assert results["k8_a"]["selected_payload"] == results["k8_b"][
            "selected_payload"
        ]

        check_dynamic_reordering_rejection(args.build, sas_file, directory)
        check_unsolvable_cegar_return(args.build, directory)
        check_legacy_cegar_immediate_exit(args.build, directory)

    print(
        "PDB exact-width selector acceptance passed: K=1, intermediate, and "
        "permissive oracles match; output is deterministic; schema-v2 records "
        "one heuristic/construction; dynamic reordering is rejected; all "
        "selected searches preserve the blind optimal cost; a decisive "
        "CEGAR dead-end PDB is returned, selected, and logged before the "
        "normal unsolvable exit, while legacy CEGAR retains its immediate "
        "exit behavior"
    )


if __name__ == "__main__":
    main()
