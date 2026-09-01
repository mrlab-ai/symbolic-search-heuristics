#!/usr/bin/env python3
"""Acceptance checks for deterministic CEGAR and incidence-guided PDBs."""

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from fractions import Fraction
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
GRIPPER = REPO / "misc/tests/benchmarks/gripper/prob01.pddl"
SOURCE_ORDER = ["empty", "bdd_prefix", "goal_prefix", "goal_fill", "cegar"]
CAP_GRID = [0, 1, 2, 4, 8, 16, 32, 64, 128, 256, "exact"]
SCHEMA = "symbolic-search-heuristics/terminal-incidence-selector-trace/v1"
CEGAR_SUMMARY_RE = re.compile(
    r"CEGAR refinement summary: configured=(\d+), actual=(\d+), "
    r"reached=(true|false)"
)


def make_chain_sas(domain_size):
    lines = [
        "begin_version",
        "3",
        "end_version",
        "begin_metric",
        "0",
        "end_metric",
        "1",
        "begin_variable",
        "var0",
        "-1",
        str(domain_size),
    ]
    lines.extend(f"Atom value-{value}()" for value in range(domain_size))
    lines.extend(
        [
            "end_variable",
            "0",
            "begin_state",
            "0",
            "end_state",
            "begin_goal",
            "1",
            f"0 {domain_size - 1}",
            "end_goal",
            str(domain_size - 1),
        ]
    )
    for value in range(domain_size - 1):
        lines.extend(
            [
                "begin_operator",
                f"step-{value}",
                "0",
                "1",
                f"0 0 {value} {value + 1}",
                "1",
                "end_operator",
            ]
        )
    lines.append("0")
    return "\n".join(lines) + "\n"


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


def run(command, cwd, expected_returncode=0, input_text=None):
    result = subprocess.run(
        command, cwd=cwd, input=input_text, capture_output=True, text=True
    )
    output = result.stdout + result.stderr
    if result.returncode != expected_returncode:
        print(output)
        raise RuntimeError(
            f"return code {result.returncode}, expected {expected_returncode}: "
            f"{' '.join(map(str, command))}"
        )
    return output


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def pool_canonical(patterns):
    lines = []
    for spec in patterns:
        sources = ",".join(spec["sources"])
        pattern = ",".join(map(str, spec["pattern"]))
        feasible = int(spec["within_state_budget"])
        lines.append(
            f'{spec["pattern_index"]}|sources={sources}|pattern={pattern}'
            f'|abstract_states={spec["abstract_states"]}'
            f"|within_state_budget={feasible}\n"
        )
    return "".join(lines)


def cap_text(cap):
    return "exact" if cap is None else str(cap)


def preselection_canonical(candidates):
    lines = []
    for candidate in candidates:
        initial_h = (
            "null" if candidate["initial_dead_end"] else str(candidate["initial_h"])
        )
        incidence = ",".join(map(str, candidate["terminal_incidence_by_layer"]))
        lines.append(
            f'{candidate["pattern_index"]}|cap={cap_text(candidate["value_cap"])}'
            f'|initial_dead_end={int(candidate["initial_dead_end"])}'
            f"|initial_h={initial_h}"
            f'|finite_sum={candidate["finite_sum"]}'
            f'|finite_count={candidate["finite_count"]}'
            f'|dead_count={candidate["dead_count"]}'
            f'|cofactor_width={candidate["cofactor_width"]}'
            f'|width_upper_bound={candidate["width_upper_bound"]}'
            f"|incidence={incidence}"
            f'|incidence_total={candidate["terminal_incidence"]}'
            f'|reference_feasible={int(candidate["reference_feasible"])}\n'
        )
    return "".join(lines)


def quality_key(candidate):
    if candidate["finite_count"] == 0:
        mean_key = (0, Fraction(0))
    else:
        mean_key = (
            1,
            -Fraction(candidate["finite_sum"], candidate["finite_count"]),
        )
    return (
        -int(candidate["initial_dead_end"]),
        -(candidate["initial_h"] or 0),
        mean_key,
        -Fraction(candidate["dead_count"], candidate["abstract_states"]),
        candidate["cofactor_width"],
        candidate["abstract_states"],
        tuple(candidate["pattern"]),
    )


def identity(candidate):
    return (
        candidate["pattern_index"],
        tuple(candidate["sources"]),
        tuple(candidate["pattern"]),
        candidate["value_cap"],
        candidate["terminal_incidence"],
    )


def event_identity(event, prefix):
    return (
        event[f"{prefix}pattern_index"],
        tuple(event[f"{prefix}sources"]),
        tuple(event[f"{prefix}pattern"]),
        event[f"{prefix}value_cap"],
        event[f"{prefix}terminal_incidence"],
    )


def validate_trace(path, mode):
    events = [json.loads(line) for line in path.read_text().splitlines()]
    assert events[0]["event"] == "schema"
    assert events[0]["schema"] == SCHEMA
    assert events[0]["candidate_sources"] == SOURCE_ORDER
    assert events[0]["value_cap_grid"] == CAP_GRID

    pool = next(event for event in events if event["event"] == "pool")
    probe = next(event for event in events if event["event"] == "probe")
    candidates = [event for event in events if event["event"] == "candidate"]
    preselection = next(
        event for event in events if event["event"] == "preselection"
    )
    reference = next(event for event in events if event["event"] == "reference")
    selected = next(event for event in events if event["event"] == "selected")
    accounting = next(
        event for event in events if event["event"] == "selection_accounting"
    )
    assert [event["event"] for event in events] == (
        ["schema", "probe", "pool"]
        + ["candidate"] * len(candidates)
        + ["preselection", "reference", "selected", "selection_accounting"]
    )

    assert probe["complete"] is True
    assert probe["target_layers"] == probe["completed_layers"] == 16
    assert probe["g_values"] == list(range(16))
    assert len(probe["bdd_nodes"]) == 16
    for field in ("cpu_seconds", "wall_seconds"):
        assert probe[field] >= 0
        assert accounting[field] >= 0
    for field in (
        "peak_memory_before_kb",
        "peak_memory_after_kb",
        "peak_memory_delta_kb",
    ):
        assert probe[field] >= 0
        assert accounting[field] >= 0

    assert sha256(pool_canonical(pool["patterns"])) == pool["pool_sha256"]
    assert sha256(preselection_canonical(candidates)) == preselection[
        "preselection_sha256"
    ]
    assert preselection["pool_sha256"] == pool["pool_sha256"]
    assert preselection["candidate_count"] == len(candidates)
    assert reference["pool_sha256"] == selected["pool_sha256"] == pool[
        "pool_sha256"
    ]
    assert reference["preselection_sha256"] == selected[
        "preselection_sha256"
    ] == preselection["preselection_sha256"]

    by_pattern = {}
    for candidate in candidates:
        by_pattern.setdefault(candidate["pattern_index"], []).append(candidate)
        assert len(candidate["terminal_incidence_by_layer"]) == 16
        assert candidate["terminal_incidence"] == sum(
            candidate["terminal_incidence_by_layer"]
        )
    reference_reps = []
    for pattern_variants in by_pattern.values():
        feasible = [v for v in pattern_variants if v["reference_feasible"]]
        if feasible:
            reference_reps.append(feasible[-1])
    expected_reference = min(reference_reps, key=quality_key)
    assert event_identity(reference, "reference_") == identity(expected_reference)
    budget = expected_reference["terminal_incidence"]
    assert reference["incidence_budget"] == budget

    guided_reps = []
    for variants in by_pattern.values():
        feasible = [v for v in variants if v["terminal_incidence"] <= budget]
        for variant in variants:
            assert variant["incidence_feasible"] is (
                variant["terminal_incidence"] <= budget
            )
            assert variant["retained_for_pattern"] is (
                bool(feasible) and variant is feasible[-1]
            )
        if feasible:
            guided_reps.append(feasible[-1])
    expected_guided = min(guided_reps, key=quality_key)
    expected_selected = (
        expected_reference if mode == "matched_control" else expected_guided
    )
    assert selected["decision_mode"] == mode
    assert event_identity(selected, "selected_") == identity(expected_selected)
    assert selected["incidence_budget"] == budget
    return {
        "pool_sha256": pool["pool_sha256"],
        "preselection_sha256": preselection["preselection_sha256"],
        "probe_structure": (probe["g_values"], probe["bdd_nodes"]),
        "candidates": candidates,
        "reference": reference,
    }


def run_incidence(build, directory, mode, repetition):
    trace = directory / f"{mode}-{repetition}.jsonl"
    plan = directory / f"{mode}-{repetition}.plan"
    search = (
        "sym_fw_pdb(budget=100000,"
        f"pattern_selection=terminal_incidence_{mode},"
        "cegar_seed=2011,cegar_max_time=infinity,"
        "cegar_max_refinements=128,gamer_ordering=false,"
        "dynamic_reordering=false,"
        f'incidence_selector_log="{trace}")'
    )
    output = run(
        [
            str(REPO / "builds" / build / "bin" / "downward"),
            "--search",
            search,
            "--internal-plan-file",
            str(plan),
        ],
        directory,
        input_text=make_chain_sas(18),
    )
    assert "Plan cost: 17" in output
    assert CEGAR_SUMMARY_RE.findall(output) == [("128", "0", "false")]
    return validate_trace(trace, mode)


def check_cegar_limit_zero(build, directory):
    output = run(
        [
            str(REPO / "fast-downward.py"),
            "--build",
            build,
            "--plan-file",
            str(directory / "gripper.plan"),
            str(GRIPPER),
            "--search",
            "astar(pdb(pattern=cegar_pattern(max_pdb_size=1000,"
            "max_time=infinity,max_refinements=0,random_seed=2011)))",
        ],
        directory,
    )
    assert CEGAR_SUMMARY_RE.findall(output) == [("0", "0", "true")]

    output = run(
        [
            str(REPO / "builds" / build / "bin" / "downward"),
            "--search",
            "sym_fw_pdb(budget=100,pattern_selection=cegar,"
            "cegar_max_time=infinity,cegar_max_refinements=0,"
            "cegar_seed=2011,gamer_ordering=false)",
            "--internal-plan-file",
            str(directory / "unsolvable.plan"),
        ],
        directory,
        expected_returncode=11,
        input_text=UNSOLVABLE_SAS,
    )
    assert CEGAR_SUMMARY_RE.findall(output) == [("0", "0", "false")]
    assert "task proved unsolvable during computation of abstraction" in output


def check_exact_pool_selected_add(build, directory):
    profile = directory / "exact-pool-profile.jsonl"
    output = run(
        [
            str(REPO / "builds" / build / "bin" / "downward"),
            "--search",
            "sym_fw_pdb(budget=100,pattern_selection=exact_width_filter,"
            "cofactor_width_budget=100,cegar_max_time=infinity,"
            "cegar_max_refinements=0,cegar_seed=2011,gamer_ordering=false,"
            f'wbh_profile_log="{profile}")',
            "--internal-plan-file",
            str(directory / "exact-unsolvable.plan"),
        ],
        directory,
        expected_returncode=11,
        input_text=UNSOLVABLE_SAS,
    )
    assert "Initial state has infinite heuristic value" in output
    events = [json.loads(line) for line in profile.read_text().splitlines()]
    heuristic_profiles = [
        event for event in events if event["event"] == "heuristic_profile"
    ]
    assert len(heuristic_profiles) == 1
    assert heuristic_profiles[0]["num_terminals"] >= 1


def check_fail_closed(build, directory):
    trace = directory / "short.jsonl"
    search = (
        "sym_fw_pdb(budget=100000,"
        "pattern_selection=terminal_incidence_guided,"
        "cegar_seed=2011,cegar_max_time=infinity,cegar_max_refinements=128,"
        "gamer_ordering=false,dynamic_reordering=false,"
        f'incidence_selector_log="{trace}")'
    )
    output = run(
        [str(REPO / "builds" / build / "bin" / "downward"), "--search", search],
        directory,
        expected_returncode=34,
        input_text=make_chain_sas(3),
    )
    assert "no fallback is permitted" in output
    probe = [json.loads(line) for line in trace.read_text().splitlines()][1]
    assert probe["event"] == "probe"
    assert probe["complete"] is False
    assert probe["completed_layers"] == 3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", default="release_no_lp")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="wbh-incidence-selector-") as tmp:
        directory = Path(tmp)
        matched = run_incidence(args.build, directory, "matched_control", 1)
        guided_a = run_incidence(args.build, directory, "guided", 1)
        guided_b = run_incidence(args.build, directory, "guided", 2)
        for field in ("pool_sha256", "preselection_sha256", "probe_structure"):
            assert matched[field] == guided_a[field] == guided_b[field]
        assert matched["candidates"] == guided_a["candidates"] == guided_b[
            "candidates"
        ]
        assert matched["reference"] == guided_a["reference"] == guided_b[
            "reference"
        ]
        check_cegar_limit_zero(args.build, directory)
        check_exact_pool_selected_add(args.build, directory)
        check_fail_closed(args.build, directory)
    print(
        "Terminal-incidence selector acceptance passed: deterministic pool and "
        "preselection hashes, identical matched work, independent K=32/B/winner "
        "reconstruction, 16-layer detachment, fail-closed short probes, and "
        "CEGAR refinement-limit/decisive-unsolvability semantics all match."
    )


if __name__ == "__main__":
    main()
