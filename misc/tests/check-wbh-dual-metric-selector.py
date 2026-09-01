#!/usr/bin/env python3
"""Acceptance checks for the outcome-blind dual I/mJ PDB selector core."""

import argparse
import hashlib
import importlib.util
import json
import tempfile
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]
INCIDENCE_TEST_PATH = REPO / "misc/tests/check-wbh-incidence-selector.py"
SPEC = importlib.util.spec_from_file_location(
    "wbh_incidence_fixture", INCIDENCE_TEST_PATH
)
IncidenceFixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IncidenceFixture)

SCHEMA = "symbolic-search-heuristics/terminal-dual-metric-selector-trace/v1"
MODES = {
    "incidence_guided": "terminal_dual_incidence_guided",
    "masked_joint_guided": "terminal_dual_mj_guided",
    "matched_control": "terminal_dual_matched_control",
}


def make_dead_branch_chain_sas(domain_size):
    lines = [
        "begin_version",
        "3",
        "end_version",
        "begin_metric",
        "0",
        "end_metric",
        "2",
        "begin_variable",
        "var0",
        "-1",
        str(domain_size),
    ]
    lines.extend(f"Atom position-{value}()" for value in range(domain_size))
    lines.extend(
        [
            "end_variable",
            "begin_variable",
            "var1",
            "-1",
            "2",
            "Atom safe()",
            "Atom trapped()",
            "end_variable",
            "0",
            "begin_state",
            "0",
            "0",
            "end_state",
            "begin_goal",
            "2",
            f"0 {domain_size - 1}",
            "1 0",
            "end_goal",
            str(2 * domain_size - 1),
        ]
    )
    for value in range(domain_size - 1):
        lines.extend(
            [
                "begin_operator",
                f"step-{value}",
                "1",
                "1 0",
                "1",
                f"0 0 {value} {value + 1}",
                "1",
                "end_operator",
            ]
        )
    for value in range(domain_size):
        lines.extend(
            [
                "begin_operator",
                f"trap-{value}",
                "1",
                f"0 {value}",
                "1",
                "0 1 0 1",
                "1",
                "end_operator",
            ]
        )
    lines.append("0")
    return "\n".join(lines) + "\n"


def sha256(text):
    return hashlib.sha256(text.encode()).hexdigest()


def csv(values):
    return ",".join(str(value) for value in values)


def nested_csv(rows):
    return ";".join(csv(row) for row in rows)


def state_profile_canonical(probe, profiles):
    return "".join(
        (
            f"{index}|g={probe['g_values'][index]}"
            f"|bdd_nodes={probe['bdd_nodes'][index]}"
            f"|cofactor_counts={csv(profile)}\n"
        )
        for index, profile in enumerate(profiles)
    )


def incidence_projection_line(candidate, terminate=True):
    cap = IncidenceFixture.cap_text(candidate["value_cap"])
    initial_h = (
        "null" if candidate["initial_dead_end"] else candidate["initial_h"]
    )
    histogram = candidate["raw_value_histogram"]
    histogram = "null" if histogram is None else histogram
    line = (
        f"{candidate['pattern_index']}|cap={cap}"
        f"|initial_dead_end={int(candidate['initial_dead_end'])}"
        f"|initial_h={initial_h}"
        f"|finite_sum={candidate['finite_sum']}"
        f"|finite_count={candidate['finite_count']}"
        f"|dead_count={candidate['dead_count']}"
        f"|cofactor_width={candidate['cofactor_width']}"
        f"|width_upper_bound={candidate['width_upper_bound']}"
        f"|raw_max_finite_value={candidate['raw_max_finite_value']}"
        f"|raw_value_histogram={histogram}"
        f"|incidence={csv(candidate['terminal_incidence_by_layer'])}"
        f"|incidence_total={candidate['terminal_incidence']}"
        f"|reference_feasible={int(candidate['reference_feasible'])}"
    )
    return line + ("\n" if terminate else "")


def dual_canonical_line(candidate):
    return (
        incidence_projection_line(candidate, terminate=False)
        + f"|heuristic_cofactor_counts={csv(candidate['heuristic_cofactor_counts'])}"
        + f"|masked_add_nodes={csv(candidate['masked_add_nodes_by_layer'])}"
        + "|active_finite_values="
        + nested_csv(candidate["active_finite_values_by_layer"])
        + "|dead_end_active="
        + csv(int(value) for value in candidate["dead_end_active_by_layer"])
        + "|active_terminal_count="
        + csv(candidate["active_terminal_count_by_layer"])
        + "|joint_cofactor_counts="
        + nested_csv(candidate["joint_cofactor_counts_by_layer"])
        + "|joint_cofactor_sum="
        + csv(candidate["joint_cofactor_sum_by_layer"])
        + "|masked_joint="
        + csv(candidate["masked_joint_by_layer"])
        + f"|masked_joint_total={candidate['masked_joint']}\n"
    )


def identity(candidate):
    return (
        candidate["pattern_index"],
        tuple(candidate["sources"]),
        tuple(candidate["pattern"]),
        candidate["value_cap"],
        candidate["terminal_incidence"],
        candidate["masked_joint"],
    )


def event_identity(event, prefix):
    return (
        event[f"{prefix}pattern_index"],
        tuple(event[f"{prefix}sources"]),
        tuple(event[f"{prefix}pattern"]),
        event[f"{prefix}value_cap"],
        event[f"{prefix}terminal_incidence"],
        event[f"{prefix}masked_joint"],
    )


def validate_trace(path, mode):
    content = path.read_text()
    events = [json.loads(line) for line in content.splitlines()]
    schema = events[0]
    assert schema["event"] == "schema"
    assert schema["schema"] == SCHEMA
    assert schema["version"] == 1
    assert schema["probe_layers"] == 16
    assert schema["reference_cofactor_width_budget"] == 32
    assert "excluding_terminal_from_sums" in schema["cut_convention"]
    assert (
        schema["joint_residual_identity"]
        == "cooccurring_signed_bdd_and_regular_add_pointer_pair"
    )
    assert schema["active_terminal_semantics"].startswith(
        "finite_values_plus_semantic_dead_end"
    )

    variable_order = events[1]
    probe = events[2]
    state_event = events[3]
    pool = events[4]
    candidates = [event for event in events if event["event"] == "candidate"]
    preselection = next(
        event for event in events if event["event"] == "preselection"
    )
    reference = next(event for event in events if event["event"] == "reference")
    winners = next(
        event for event in events if event["event"] == "metric_winners"
    )
    selected = next(event for event in events if event["event"] == "selected")
    accounting = next(
        event for event in events if event["event"] == "selection_accounting"
    )
    assert [event["event"] for event in events] == (
        ["schema", "variable_order", "probe", "probe_state_profiles", "pool"]
        + ["candidate"] * len(candidates)
        + [
            "preselection",
            "reference",
            "metric_winners",
            "selected",
            "selection_accounting",
        ]
    )

    state_bits = variable_order["state_bits"]
    assert state_bits == len(variable_order["cudd_indices"])
    assert state_bits == len(variable_order["cudd_levels"])
    assert state_bits == len(variable_order["fd_variables"])
    assert state_bits == len(variable_order["fd_bit_positions"])
    assert variable_order["cudd_levels"] == sorted(
        variable_order["cudd_levels"]
    )
    assert probe["complete"] is True
    assert probe["completed_layers"] == probe["target_layers"] == 16
    profiles = state_event["cofactor_counts_by_layer"]
    assert len(profiles) == 16
    assert all(len(profile) == state_bits + 1 for profile in profiles)
    assert sha256(state_profile_canonical(probe, profiles)) == state_event[
        "state_profiles_sha256"
    ]

    assert sha256(IncidenceFixture.pool_canonical(pool["patterns"])) == pool[
        "pool_sha256"
    ]
    assert preselection["candidate_count"] == len(candidates)
    incidence_projection = "".join(
        incidence_projection_line(candidate) for candidate in candidates
    )
    dual_canonical = "".join(
        dual_canonical_line(candidate) for candidate in candidates
    )
    assert sha256(incidence_projection) == preselection[
        "incidence_projection_sha256"
    ]
    assert sha256(dual_canonical) == preselection["preselection_sha256"]
    hashes = (
        "pool_sha256",
        "state_profiles_sha256",
        "incidence_projection_sha256",
        "preselection_sha256",
    )
    for field in hashes:
        assert preselection[field] == reference[field]
        assert preselection[field] == winners[field]
        assert preselection[field] == selected[field]

    by_pattern = {}
    total_joint_entries = 0
    for candidate in candidates:
        by_pattern.setdefault(candidate["pattern_index"], []).append(candidate)
        layer_fields = (
            candidate["terminal_incidence_by_layer"],
            candidate["masked_add_nodes_by_layer"],
            candidate["active_finite_values_by_layer"],
            candidate["dead_end_active_by_layer"],
            candidate["active_terminal_count_by_layer"],
            candidate["joint_cofactor_counts_by_layer"],
            candidate["joint_cofactor_sum_by_layer"],
            candidate["masked_joint_by_layer"],
        )
        assert all(len(field) == 16 for field in layer_fields)
        assert len(candidate["heuristic_cofactor_counts"]) == state_bits + 1
        assert candidate["terminal_incidence"] == sum(layer_fields[0])
        assert candidate["masked_joint"] == sum(layer_fields[7])
        total_joint_entries += 16 * (state_bits + 1)
        for layer in range(16):
            finite = layer_fields[2][layer]
            dead = layer_fields[3][layer]
            k = layer_fields[4][layer]
            joint = layer_fields[5][layer]
            joint_sum = layer_fields[6][layer]
            masked_joint = layer_fields[7][layer]
            incidence = layer_fields[0][layer]
            masked_nodes = layer_fields[1][layer]
            assert finite == sorted(set(finite))
            assert all(type(value) is int and value >= 0 for value in finite)
            assert type(dead) is bool
            assert k == len(finite) + int(dead)
            assert k >= 1
            assert len(joint) == state_bits + 1
            assert joint_sum == sum(joint[:-1])
            assert masked_joint == k * joint_sum
            assert masked_nodes <= incidence <= k * masked_nodes
            assert incidence <= masked_joint
            for state_count, heuristic_count, joint_count in zip(
                profiles[layer],
                candidate["heuristic_cofactor_counts"],
                joint,
            ):
                assert max(state_count, heuristic_count) <= joint_count
                assert joint_count <= state_count * heuristic_count
    assert any(
        any(candidate["dead_end_active_by_layer"])
        for candidate in candidates
    )

    for variants in by_pattern.values():
        raw_max = variants[-1]["raw_max_finite_value"]
        expected_caps = [
            str(cap)
            for cap in IncidenceFixture.CAP_GRID[:-1]
            if cap < raw_max
        ] + ["exact"]
        assert [
            IncidenceFixture.cap_text(variant["value_cap"])
            for variant in variants
        ] == expected_caps
        for weaker, stronger in zip(variants, variants[1:]):
            assert weaker["reference_feasible"] or not stronger[
                "reference_feasible"
            ]
            for scalar in ("terminal_incidence", "masked_joint"):
                assert weaker[scalar] <= stronger[scalar]
            for field in (
                "heuristic_cofactor_counts",
                "terminal_incidence_by_layer",
                "masked_add_nodes_by_layer",
                "active_terminal_count_by_layer",
                "joint_cofactor_sum_by_layer",
                "masked_joint_by_layer",
            ):
                assert all(
                    left <= right
                    for left, right in zip(weaker[field], stronger[field])
                )
            for old_joint, new_joint in zip(
                weaker["joint_cofactor_counts_by_layer"],
                stronger["joint_cofactor_counts_by_layer"],
            ):
                assert all(
                    left <= right
                    for left, right in zip(old_joint, new_joint)
                )

    reference_reps = []
    for variants in by_pattern.values():
        feasible = [item for item in variants if item["reference_feasible"]]
        if feasible:
            reference_reps.append(feasible[-1])
    expected_reference = min(
        reference_reps, key=IncidenceFixture.quality_key
    )
    assert event_identity(reference, "reference_") == identity(
        expected_reference
    )
    incidence_budget = expected_reference["terminal_incidence"]
    masked_joint_budget = expected_reference["masked_joint"]
    assert reference["incidence_budget"] == incidence_budget
    assert reference["masked_joint_budget"] == masked_joint_budget

    expected_winners = {}
    for metric, candidate_field, budget, feasible_field, retained_field in (
        (
            "incidence",
            "terminal_incidence",
            incidence_budget,
            "incidence_feasible",
            "incidence_retained_for_pattern",
        ),
        (
            "masked_joint",
            "masked_joint",
            masked_joint_budget,
            "masked_joint_feasible",
            "masked_joint_retained_for_pattern",
        ),
    ):
        representatives = []
        for variants in by_pattern.values():
            feasible = [
                item for item in variants if item[candidate_field] <= budget
            ]
            for item in variants:
                assert item[feasible_field] is (
                    item[candidate_field] <= budget
                )
                assert item[retained_field] is (
                    bool(feasible) and item is feasible[-1]
                )
            if feasible:
                representatives.append(feasible[-1])
        expected_winners[metric] = min(
            representatives, key=IncidenceFixture.quality_key
        )
    assert event_identity(
        winners, "incidence_winner_"
    ) == identity(expected_winners["incidence"])
    assert event_identity(
        winners, "masked_joint_winner_"
    ) == identity(expected_winners["masked_joint"])

    expected_selected = {
        "incidence_guided": expected_winners["incidence"],
        "masked_joint_guided": expected_winners["masked_joint"],
        "matched_control": expected_reference,
    }[mode]
    assert selected["decision_mode"] == mode
    assert event_identity(selected, "selected_") == identity(expected_selected)
    assert selected["incidence_budget"] == incidence_budget
    assert selected["masked_joint_budget"] == masked_joint_budget

    assert accounting["candidate_count"] == len(candidates)
    assert accounting["probe_state_profile_count"] == 16
    assert accounting["probe_state_profile_cut_entries"] == 16 * (
        state_bits + 1
    )
    assert accounting["terminal_incidence_layer_measurements"] == (
        16 * len(candidates)
    )
    assert accounting["joint_profile_layer_measurements"] == (
        16 * len(candidates)
    )
    assert accounting["joint_profile_cut_entries"] == total_joint_entries
    assert accounting["joint_summed_cut_entries"] == (
        16 * len(candidates) * state_bits
    )
    for field in ("cpu_seconds", "wall_seconds"):
        assert accounting[field] >= 0
    for field in (
        "peak_memory_before_kb",
        "peak_memory_after_kb",
        "peak_memory_delta_kb",
    ):
        assert accounting[field] >= 0

    return {
        "pool_sha256": pool["pool_sha256"],
        "state_profiles_sha256": state_event["state_profiles_sha256"],
        "incidence_projection_sha256": preselection[
            "incidence_projection_sha256"
        ],
        "preselection_sha256": preselection["preselection_sha256"],
        "candidates": candidates,
        "reference": reference,
        "winners": winners,
        "probe_structure": (probe["g_values"], probe["bdd_nodes"]),
        "state_event": state_event,
    }


def run_dual(build, directory, mode):
    trace = directory / f"dual-{mode}.jsonl"
    search = (
        "sym_fw_pdb(budget=100000,"
        f"pattern_selection={MODES[mode]},"
        "cegar_seed=2011,cegar_max_time=infinity,"
        "cegar_max_refinements=128,gamer_ordering=false,"
        "dynamic_reordering=false,"
        f'incidence_selector_log="{trace}")'
    )
    output = IncidenceFixture.run(
        [
            str(REPO / "builds" / build / "bin" / "downward"),
            "--search",
            search,
            "--internal-plan-file",
            str(directory / f"dual-{mode}.plan"),
        ],
        directory,
        input_text=make_dead_branch_chain_sas(18),
    )
    assert "Plan cost: 17" in output
    return validate_trace(trace, mode)


def check_short_probe(build, directory):
    trace = directory / "dual-short.jsonl"
    search = (
        "sym_fw_pdb(budget=100000,"
        "pattern_selection=terminal_dual_mj_guided,"
        "cegar_seed=2011,cegar_max_time=infinity,"
        "cegar_max_refinements=128,gamer_ordering=false,"
        "dynamic_reordering=false,"
        f'incidence_selector_log="{trace}")'
    )
    output = IncidenceFixture.run(
        [str(REPO / "builds" / build / "bin" / "downward"), "--search", search],
        directory,
        expected_returncode=34,
        input_text=IncidenceFixture.make_chain_sas(3),
    )
    assert "no fallback is permitted" in output
    events = [json.loads(line) for line in trace.read_text().splitlines()]
    assert [event["event"] for event in events] == [
        "schema",
        "variable_order",
        "probe",
    ]
    assert events[-1]["complete"] is False
    assert events[-1]["completed_layers"] == 3


def run_incumbent_projection(build, directory):
    trace = directory / "incumbent-guided.jsonl"
    search = (
        "sym_fw_pdb(budget=100000,"
        "pattern_selection=terminal_incidence_guided,"
        "cegar_seed=2011,cegar_max_time=infinity,"
        "cegar_max_refinements=128,gamer_ordering=false,"
        "dynamic_reordering=false,"
        f'incidence_selector_log="{trace}")'
    )
    output = IncidenceFixture.run(
        [
            str(REPO / "builds" / build / "bin" / "downward"),
            "--search",
            search,
            "--internal-plan-file",
            str(directory / "incumbent-guided.plan"),
        ],
        directory,
        input_text=make_dead_branch_chain_sas(18),
    )
    assert "Plan cost: 17" in output
    events = [
        json.loads(line) for line in trace.read_text().splitlines()
    ]
    pool = next(event for event in events if event["event"] == "pool")
    candidates = [
        event for event in events if event["event"] == "candidate"
    ]
    preselection = next(
        event for event in events if event["event"] == "preselection"
    )
    reference = next(
        event for event in events if event["event"] == "reference"
    )
    assert sha256(
        IncidenceFixture.preselection_canonical(candidates)
    ) == preselection["preselection_sha256"]
    return {
        "pool_sha256": pool["pool_sha256"],
        "preselection_sha256": preselection["preselection_sha256"],
        "reference": reference,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", default="release_no_lp")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="wbh-dual-selector-") as tmp:
        directory = Path(tmp)
        traces = {
            mode: run_dual(args.build, directory, mode) for mode in MODES
        }
        for field in (
            "pool_sha256",
            "state_profiles_sha256",
            "incidence_projection_sha256",
            "preselection_sha256",
            "candidates",
            "reference",
            "winners",
            "probe_structure",
            "state_event",
        ):
            values = [trace[field] for trace in traces.values()]
            assert values[1:] == values[:-1]

        incumbent = run_incumbent_projection(args.build, directory)
        dual = traces["incidence_guided"]
        assert dual["pool_sha256"] == incumbent["pool_sha256"]
        assert (
            dual["incidence_projection_sha256"]
            == incumbent["preselection_sha256"]
        )
        assert (
            dual["reference"]["reference_pattern_index"],
            dual["reference"]["reference_sources"],
            dual["reference"]["reference_pattern"],
            dual["reference"]["reference_value_cap"],
            dual["reference"]["reference_terminal_incidence"],
        ) == (
            incumbent["reference"]["reference_pattern_index"],
            incumbent["reference"]["reference_sources"],
            incumbent["reference"]["reference_pattern"],
            incumbent["reference"]["reference_value_cap"],
            incumbent["reference"]["reference_terminal_incidence"],
        )
        check_short_probe(args.build, directory)
    print(
        "Dual I/mJ selector acceptance passed: exact A-compatible joint "
        "profiles and terminal exclusion, semantic dead ends, independent "
        "B_I/B_M winners, common K=32 reference, incumbent incidence "
        "projection, identical three-mode work, hashes, and fail-closed short "
        "probes all match."
    )


if __name__ == "__main__":
    main()
