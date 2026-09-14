"""Numeric projections for the two dependent selector experiments."""

from __future__ import annotations

from collections import defaultdict
from fractions import Fraction

import render_terminal_incidence_results as R
import terminal_incidence_evidence as E


B_NAMES = dict(zip(R.B_CONFIGURATIONS, (
    "blind_fw", "pdb_bdd_prefix", "pdb_goal_prefix", "pdb_goal_fill",
    "pdb_cegar_deterministic", "pdb_exact_width_k32", "pdb_cap_aware_k32",
    "pdb_terminal_incidence_guided", "pdb_terminal_incidence_matched",
)))
DIRECT_MJ = "terminal_dual_mj_guided"
DIRECT_MATCHED = "terminal_dual_matched_control"
WORK_NAMES = dict(zip(R.DIRECT_WORK_FIELDS, (
    "candidate_count", "probe_state_profile_count", "probe_state_profile_cut_entries",
    "terminal_incidence_layer_measurements", "joint_profile_layer_measurements",
    "joint_profile_cut_entries", "joint_summed_cut_entries",
)))
B_DIR = E.BASE + "/confirmation-b"
D_DIR = "experiments/artifacts/pdb-terminal-metric-choice"
PATHS = {
    "b_freeze": E.BASE + "/confirmation-b-freeze-v1.json",
    "b_result": B_DIR + "/analysis-v3.json",
    "b_repeat": B_DIR + "/analysis-v3-repeat.json",
    "b_receipt": B_DIR + "/analysis-execution-receipt-v3.json",
    "b_receipt_pin": B_DIR + "/analysis-execution-receipt-v3.sha256",
    "b_execution": B_DIR + "/execution-receipt-v1.json",
    "b_execution_pin": B_DIR + "/execution-receipt-v1.sha256",
    "b_fetch": B_DIR + "/fetch-receipt-v1.json",
    "b_fetch_pin": B_DIR + "/fetch-receipt-v1.sha256",
    "d_freeze": D_DIR + "/freeze-v1.json",
    "d_result": D_DIR + "/analysis-v4.json",
    "d_repeat": D_DIR + "/analysis-v4-repeat.json",
    "d_receipt": D_DIR + "/analysis-execution-receipt-v4.json",
    "d_receipt_pin": D_DIR + "/analysis-execution-receipt-v4.sha256",
    "d_execution": D_DIR + "/execution-receipt-v1.json",
    "d_execution_pin": D_DIR + "/execution-receipt-v1.sha256",
    "d_fetch": D_DIR + "/post-fetch-receipt-v1.json",
    "d_standalone": D_DIR + "/standalone-k32-v1.json",
    "d_calibration": D_DIR + "/calibration-receipt-v1.json",
    "d_planner": D_DIR + "/planner-manifest-v1.json",
}


def fraction(value):
    if value is None:
        return None
    return {"numerator": value.numerator, "denominator": value.denominator}


def contrast(value, *, direct=False):
    if value is None:
        return {
            "coverage_incidence": 0, "coverage_comparator": 0,
            "mean_improvement": None, "bootstrap_lower": None,
            "bootstrap_upper": None, "lofo_minimum": None,
            "outcome_decomposition": {
                "both_solved": 0, "incidence_only_solved": 0,
                "comparator_only_solved": 0, "neither_solved": 0,
                "common_solved_tasks": 0, "common_solved_families": 0,
                "equal_family_normalized_time_improvement": None,
            },
        }
    decomposition = value["outcome_decomposition"]
    pairs = decomposition["solve_pair_counts"]
    common = decomposition["common_solved"]
    if common["normalization_seconds"] != 1800:
        raise E.EvidenceError("common-solved normalization changed")
    return {
        "coverage_incidence": value["coverage"]["intervention" if direct else "guided"],
        "coverage_comparator": value["coverage"]["reference"],
        "mean_improvement": E.q(value[
            "equal_family_normalized_par2_improvement" if direct
            else "family_macro_normalized_improvement"
        ]),
        "bootstrap_lower": E.q(value["bootstrap"]["lower_95"]),
        "bootstrap_upper": E.q(value["bootstrap"]["upper_95"]),
        "lofo_minimum": E._minimum(value["lodo" if direct else "leave_one_family_out"].values()),
        "outcome_decomposition": {
            "both_solved": pairs["both_solved"],
            "incidence_only_solved": pairs["intervention_only_solved"],
            "comparator_only_solved": pairs["reference_only_solved"],
            "neither_solved": pairs["neither_solved"],
            "common_solved_tasks": common["tasks"],
            "common_solved_families": common["families"],
            "equal_family_normalized_time_improvement": E.q(common["equal_family_normalized_time_improvement"]),
        },
    }


def normalize_direct(result):
    mechanism = result["mechanism_diagnostics"]
    changes = mechanism["change_taxonomy"]["incidence_vs_mj"]["classes"]
    scores = mechanism["frozen_selection_score_relation"]["differing_incidence_mj_winners"]["relation"]
    geometry = mechanism["budget_geometry"]
    subset = result["differing_winner_subset_i_vs_mj"]
    normalized_mechanism = {
        "structural_identity_pass": result["audit"]["certified"],
        "work_counts_match": result["audit"]["certified"],
        **{key + "_tasks": changes[key] for key in (
            "same_candidate", "same_pattern_different_cap", "different_pattern",
        )},
        **{f"score_{key}_tasks": scores[key] for key in ("higher", "tied", "lower")},
        "incidence_own_utilization": E.q(geometry["incidence_own_utilization"]["equal_family_mean"]),
        "mj_own_utilization": E.q(geometry["mj_own_utilization"]["equal_family_mean"]),
        "incidence_binding_tasks": geometry["binding_tasks"]["incidence"],
        "mj_binding_tasks": geometry["binding_tasks"]["mj"],
        "incidence_under_mj_budget_tasks": geometry["cross_feasibility_counts"]["incidence_mj_feasible"],
        "mj_under_incidence_budget_tasks": geometry["cross_feasibility_counts"]["mj_incidence_feasible"],
        "candidate_work": {name: E.q(mechanism["candidate_work"][key]["equal_family_mean"])
                           for name, key in WORK_NAMES.items()},
    }
    for short, mode in (("mj", DIRECT_MJ), ("matched", DIRECT_MATCHED)):
        for timer in ("cpu_seconds", "wall_seconds"):
            normalized_mechanism[f"incidence_minus_{short}_{timer}"] = E.q(
                mechanism["paired_recorded_probe_selection_time"]["incidence_minus_" + mode][timer]["equal_family_mean"]
            )
    return {
        "sealed": True, "audit_certified": result["audit"]["certified"],
        "tasks": result["primary_i_vs_mj"]["tasks"],
        "families": result["primary_i_vs_mj"]["families"],
        "probe_support": dict(result["probe_support"]),
        "full": contrast(result["primary_i_vs_mj"], direct=True),
        "differing_winners": {
            "tasks": subset["tasks"], "families": subset["families"],
            **contrast(subset, direct=True),
        },
        "secondary_vs_matched": contrast(result["secondary_i_vs_matched"], direct=True),
        "mechanism": normalized_mechanism,
    }


def _configurations(result):
    rows = result["matrix"]["accounting_rows"]
    if {row["algorithm"] for row in rows} != set(B_NAMES.values()):
        raise E.EvidenceError("Confirmation B accounting matrix labels changed")
    if len({(row["algorithm"], row["domain"], row["problem"]) for row in rows}) != len(rows):
        raise E.EvidenceError("Confirmation B accounting matrix has duplicate cells")
    summaries = {}
    for name, label in B_NAMES.items():
        selected = [row for row in rows if row["algorithm"] == label]
        if len(selected) != 300:
            raise E.EvidenceError("Confirmation B accounting matrix is incomplete")
        by_family = defaultdict(list)
        coverage = 0
        for row in selected:
            if type(row["coverage"]) is not int or row["coverage"] not in (0, 1):
                raise E.EvidenceError("Confirmation B accounting coverage is not binary")
            value = E.q(row["par2"])
            if value is None:
                raise E.EvidenceError("Confirmation B cell has no PAR2 value")
            exact = Fraction(value["numerator"], value["denominator"])
            if (row["coverage"] == 0 and exact != 3600) or not 0 <= exact <= 3600:
                raise E.EvidenceError("Confirmation B PAR2 is inconsistent with coverage")
            by_family[row["family"]].append(exact)
            coverage += row["coverage"]
        total = sum((sum(values, Fraction()) for values in by_family.values()), Fraction())
        family_mean = sum((sum(values, Fraction()) / len(values)
                           for values in by_family.values()), Fraction()) / len(by_family)
        summaries[name] = {
            "coverage": coverage, "par2_sum_seconds": fraction(total),
            "par2_mean_seconds": fraction(total / len(selected)),
            "equal_family_mean_par2_seconds": fraction(family_mean),
        }
    return summaries


def normalize_b(result):
    provenance = result["selector_provenance"]
    mechanism = result["mechanism"]
    reference = result["contrasts"][B_NAMES["cap_aware_k32"]]
    overhead = {}
    for short, label in (("guided", B_NAMES["incidence_guided"]),
                         ("matched", B_NAMES["matched_work"])):
        phases = result["selector_overhead"]["by_arm"][label]["phases"]
        for phase in ("probe", "selection"):
            overhead[f"{short}_{phase}_wall_seconds"] = E.q(phases[phase]["wall_seconds"]["mean"])
            overhead[f"{short}_{phase}_peak_delta_kb"] = E.q(phases[phase]["peak_memory_delta_kb"]["mean"])
    return {
        "sealed": True, "selector_provenance_pass": provenance["pass"],
        "tasks": result["matrix"]["tasks"], "families": reference["families"],
        "complete_pairs": provenance["full_preselection_pairs"],
        "short_probe_pairs": provenance["certified_short_probe_pairs"],
        "failed_pairs": len(provenance["failed_pairs"]),
        "selected_difference_tasks": provenance["selected_difference_tasks"],
        "reference_identity_pass": provenance["pass"],
        "versus_reference": contrast(reference),
        "versus_matched": contrast(result["contrasts"][B_NAMES["matched_work"]]),
        "alternatives": {name: contrast(result["non_gating_contrasts"]["references"][B_NAMES[name]])
                         for name in R.B_ALTERNATIVES},
        "configurations": _configurations(result),
        "mechanism": {
            "tasks": mechanism["eligible_tasks"], "families": mechanism["eligible_families"],
            "claim_authorized": mechanism["claim_authorized"],
            "versus_matched": contrast(mechanism["contrast"]),
        },
        "overhead": overhead,
    }


def _validate_b_chain(raw, authorized, a_raw, a_freeze, results_revision):
    jj, _safe, _adapter, _snapshot = E._imports()
    import pdb_terminal_incidence_confirmation_b_protocol as B
    freeze, materials = B._load_freeze(B.FREEZE_PATH)
    if freeze != E._canonical(raw["b_freeze"], "Confirmation B freeze"):
        raise E.EvidenceError("Confirmation B freeze changed during validation")
    if materials.source_audit != B._source_payload(authorized):
        raise E.EvidenceError("Confirmation B freeze differs from the V12 adapter")
    authorization = freeze["confirmation_a_authorization"]
    if any((
        authorization["receipt_sha256"] != E._sha(a_raw["a_receipt"]),
        authorization["first_output_sha256"] != E._sha(a_raw["a_result"]),
        authorization["second_output_sha256"] != E._sha(a_raw["a_repeat"]),
        authorization["confirmation_a_freeze_repository_revision"] != a_freeze["freeze_repository_revision"],
        freeze["planner"] != a_freeze["planner"],
    )):
        raise E.EvidenceError("Confirmation B authorization differs from sealed A")
    jj.require_ancestor(E.REPO, authorized.bindings.seal_repository_commit_id,
                        freeze["freeze_repository_revision"])
    jj.require_ancestor(E.REPO, freeze["freeze_repository_revision"], results_revision)
    result, receipt = E._check_double_analysis(raw, "b", None)
    schema = "symbolic-search-heuristics/pdb-terminal-incidence-confirmation-b-analysis/v3"
    if any((
        result["schema"] != schema, receipt["schema"] != schema + "/double-execution",
        result["protocol"] != B.PROTOCOL,
        result["analysis_protocol"] != B.ANALYSIS_PROTOCOL,
        receipt["analysis_protocol"] != B.ANALYSIS_PROTOCOL,
        receipt["bootstrap_replicates"] != B.BOOTSTRAP_REPLICATES,
        receipt["bootstrap_seed"] != B.BOOTSTRAP_SEED,
        receipt["first_output"] != str(E.REPO / PATHS["b_result"]),
        receipt["second_output"] != str(E.REPO / PATHS["b_repeat"]),
        result["input"]["path"] != str(E.EXPERIMENTS / "data" / "exp_pdb_terminal_incidence_confirmation_b-eval" / "properties"),
        result["matrix"]["cells"] != 2700,
        result["matrix"]["tasks"] != 300, result["matrix"]["configs"] != 9,
        result["matrix"]["all_cells_assigned_par2"] is not True,
        result["matrix"]["algorithm_failures_are_par2"] is not True,
        result["matrix"]["no_task_dropping"] is not True,
        result["matrix"]["par2_seconds"] != 3600,
        result["gates"]["pass"] is not receipt["confirmation_b_complete_gate_passed"],
        result["mechanism"]["claim_authorized"] is not receipt["mechanism_claim_authorized"],
    )):
        raise E.EvidenceError("Confirmation B production identity changed")
    expected_tasks = {(task["directory"], task["problem"]): task["family"]
                      for task in authorized.guided_b.records}
    for label in B_NAMES.values():
        actual = {(row["domain"], row["problem"]): row["family"]
                  for row in result["matrix"]["accounting_rows"] if row["algorithm"] == label}
        if actual != expected_tasks:
            raise E.EvidenceError("Confirmation B accounting differs from the source cohort")
    return result, receipt, freeze


def _validate_direct_chain(raw, b_freeze, a_raw, results_revision):
    jj, _safe, _adapter, _snapshot = E._imports()
    import pdb_terminal_metric_choice_protocol as D
    import pdb_terminal_metric_choice_analyzer as Analysis
    freeze = D.load_freeze(D.FREEZE_PATH)
    if freeze != E._canonical(raw["d_freeze"], "direct freeze"):
        raise E.EvidenceError("direct freeze changed during validation")
    base = freeze["base_confirmation_b"]
    if any((
        base["base_b_freeze_sha256"] != E._sha(raw["b_freeze"]),
        base["base_b_freeze_repository_revision"] != b_freeze["freeze_repository_revision"],
        base["source_audit_v12"] != b_freeze["source_audit"],
        base["confirmation_a_authorization"] != b_freeze["confirmation_a_authorization"],
        base["confirmation_a_freeze"]["sha256"] != E._sha(a_raw["a_freeze"]),
    )):
        raise E.EvidenceError("direct freeze differs from the sealed A/B source chain")
    jj.require_ancestor(E.REPO, b_freeze["freeze_repository_revision"], freeze["freeze_repository_revision"])
    jj.require_ancestor(E.REPO, freeze["freeze_repository_revision"], results_revision)
    if D.load_bound_standalone(freeze) != E._canonical(raw["d_standalone"], "standalone evidence"):
        raise E.EvidenceError("direct standalone evidence changed")
    if D.load_bound_calibration(freeze) != E._canonical(raw["d_calibration"], "calibration evidence"):
        raise E.EvidenceError("direct calibration evidence changed")
    planner = E._canonical(raw["d_planner"], "direct planner manifest")
    D.validate_planner_manifest(planner)
    if planner != freeze["planner"]:
        raise E.EvidenceError("direct planner manifest differs from the freeze")
    result = E._canonical(raw["d_result"], "direct result")
    receipt = E._canonical(raw["d_receipt"], "direct analysis receipt")
    execution = E._canonical(raw["d_execution"], "direct execution receipt")
    fetch = E._canonical(raw["d_fetch"], "direct fetch receipt")
    freeze_sha = E._sha(raw["d_freeze"])
    provenance = Analysis._analysis_provenance(freeze, freeze_sha)
    if any((
        raw["d_result"] != raw["d_repeat"],
        raw["d_receipt_pin"] != (E._sha(raw["d_receipt"]) + "\n").encode("ascii"),
        raw["d_execution_pin"] != (E._sha(raw["d_execution"]) + "\n").encode("ascii"),
        result["schema"] != Analysis.ANALYSIS_SCHEMA,
        receipt["schema"] != Analysis.RECEIPT_SCHEMA,
        result["analysis_protocol"] != D.ANALYSIS_PROTOCOL,
        receipt["analysis_protocol"] != D.ANALYSIS_PROTOCOL,
        receipt["bootstrap_replicates"] != D.BOOTSTRAP_REPLICATES,
        receipt["bootstrap_seed"] != D.BOOTSTRAP_SEED,
        receipt["first_output_sha256"] != E._sha(raw["d_result"]),
        receipt["second_output_sha256"] != E._sha(raw["d_repeat"]),
        receipt["first_output"] != str(E.REPO / PATHS["d_result"]),
        receipt["second_output"] != str(E.REPO / PATHS["d_repeat"]),
        receipt["outputs_byte_identical"] is not True,
        receipt["freeze_sha256"] != freeze_sha,
        receipt["frozen_provenance"] != provenance,
        receipt["fetched_properties_sha256"] != fetch["fetched_properties_sha256"],
        receipt["post_fetch_receipt_sha256"] != E._sha(raw["d_fetch"]),
        receipt["execution_receipt_sha256"] != E._sha(raw["d_execution"]),
        receipt["execution_receipt_path"] != PATHS["d_execution"],
        fetch["execution_receipt_sha256"] != E._sha(raw["d_execution"]),
        fetch["freeze_sha256"] != freeze_sha,
        receipt["hardware"] != execution["hardware"],
        receipt["primary_gate_passed"] is not result["pass"],
    )):
        raise E.EvidenceError("direct double-analysis chain changed")
    for key in ("freeze_sha256", "frozen_provenance", "fetched_properties_sha256",
                "post_fetch_receipt_sha256", "execution_receipt_path",
                "execution_receipt_sha256", "hardware"):
        if result["input"][key] != receipt[key]:
            raise E.EvidenceError("direct result and receipt provenance differ")
    return result, receipt


def load_selection_evidence(results_revision, artifact_pins, result_pins,
                            authorized, a_raw, a_freeze):
    raw = E._read_artifacts(results_revision, PATHS,
                            {key: artifact_pins[key] for key in PATHS})
    if (E._sha(raw["b_result"]) != result_pins["confirmation_b"]
            or E._sha(raw["d_result"]) != result_pins["direct_metric_choice"]):
        raise E.EvidenceError("selector results differ from production pins")
    b, b_receipt, b_freeze = _validate_b_chain(raw, authorized, a_raw, a_freeze, results_revision)
    direct, d_receipt = _validate_direct_chain(raw, b_freeze, a_raw, results_revision)
    b_normalized, d_normalized = normalize_b(b), normalize_direct(direct)
    source = E.source_summary(authorized)
    R._validate_b(b_normalized, source)
    R._validate_direct(d_normalized, source)
    if R._b_gate(b_normalized) is not b["gates"]["pass"] or R._direct_gate(d_normalized) is not direct["pass"]:
        raise E.EvidenceError("recomputed selector gate differs from the sealed result")
    return {
        "confirmation_b": b_normalized, "direct_metric_choice": d_normalized,
    }, {
        "b": E._hardware(b_receipt["hardware"], 2700),
        "direct": E._hardware(d_receipt["hardware"], 900),
    }
