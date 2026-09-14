"""Project committed confirmation artifacts to the paper's numeric interface.

The source census is consumed only through the V12 adapter. Planner properties
and worker logs are never opened here: their authenticated analysis receipts
and byte-identical repeated analyses are the reporting boundary.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import re
import sys
from collections.abc import Mapping
from fractions import Fraction
from pathlib import Path

import render_terminal_incidence_results as R


REPO = Path(__file__).resolve().parent.parent
EXPERIMENTS = REPO / "experiments"
BASE = "experiments/artifacts/pdb-terminal-incidence-confirmation"
A_DIR = BASE + "/confirmation-a"
A_PATHS = {
    "a_freeze": BASE + "/confirmation-a-freeze-v1.json",
    "a_result": A_DIR + "/analysis-v4.json",
    "a_repeat": A_DIR + "/analysis-v4-repeat.json",
    "a_receipt": A_DIR + "/analysis-execution-receipt-v4.json",
    "a_receipt_pin": A_DIR + "/analysis-execution-receipt-v4.sha256",
    "a_execution": A_DIR + "/execution-receipt-v1.json",
    "a_execution_pin": A_DIR + "/execution-receipt-v1.sha256",
    "a_fetch": A_DIR + "/fetch-receipt-v1.json",
    "a_fetch_pin": A_DIR + "/fetch-receipt-v1.sha256",
}
DOWNSTREAM_PATHS = (
    BASE + "/confirmation-b-freeze-v1.json",
    BASE + "/confirmation-b/launch-receipt-v1.json",
    BASE + "/confirmation-b/analysis-v3.json",
    BASE + "/confirmation-b/analysis-execution-receipt-v3.json",
    "experiments/artifacts/pdb-terminal-metric-choice/freeze-v1.json",
    "experiments/artifacts/pdb-terminal-metric-choice/launch-receipt-v1.json",
    "experiments/artifacts/pdb-terminal-metric-choice/analysis-v4.json",
    "experiments/artifacts/pdb-terminal-metric-choice/analysis-execution-receipt-v4.json",
)
PREDICTOR_NAMES = {
    "incidence": "I", "masked_add_size": "D", "value_count": "value_count",
    "kD": "kD", "mQ": "mQ", "mJ": "mJ", "cartesian": "Cartesian",
    "width": "width", "apply": "ADD", "layerwise_min_certificate": "meet",
}


class EvidenceError(ValueError):
    """A report input is absent, inconsistent, or not independently sealed."""


def _imports():
    if str(EXPERIMENTS) not in sys.path:
        sys.path.insert(0, str(EXPERIMENTS))
    import jj_cached_revision as JJ
    import pdb_confirmation_safe_io as SafeIO
    import pdb_terminal_incidence_confirmation_v12_adapter as Adapter
    from pdb_terminal_incidence_v12_snapshot_reader import read_committed_snapshot
    return JJ, SafeIO, Adapter, read_committed_snapshot


def plain(value):
    if dataclasses.is_dataclass(value):
        return {field.name: plain(getattr(value, field.name))
                for field in dataclasses.fields(value)}
    if isinstance(value, Mapping):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(raw, label):
    try:
        value = json.loads(raw.decode("ascii"))
        expected = (json.dumps(value, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")
    except (UnicodeError, ValueError, TypeError) as error:
        raise EvidenceError(f"{label} is not canonical JSON") from error
    if type(value) is not dict or raw != expected:
        raise EvidenceError(f"{label} is not canonical JSON")
    return value


def _check_revision(value, label):
    if type(value) is not str or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise EvidenceError(f"{label} must be an explicit 40-hex commit")


def _read_artifacts(revision, paths, pins):
    if type(pins) is not dict or set(pins) != set(paths):
        raise EvidenceError("production artifact-pin roles changed")
    for role, digest in pins.items():
        if (type(digest) is not str or R.SHA256_RE.fullmatch(digest) is None
                or digest == R.ZERO_SHA256):
            raise EvidenceError(f"production artifact pin is unset: {role}")
    _jj, safe, _adapter, snapshot = _imports()
    committed = snapshot(revision, list(paths.values()))
    records = {}
    for role, relative in paths.items():
        raw = committed[relative]
        if _sha(raw) != pins[role]:
            raise EvidenceError(f"committed artifact differs from its pin: {role}")
        live = safe.read_regular_file(REPO / relative, label=role, root=REPO)
        if live.raw != raw:
            raise EvidenceError(f"live artifact differs from committed evidence: {role}")
        records[role] = raw
    return records


def _require_downstream_absence():
    for relative in DOWNSTREAM_PATHS:
        if os.path.lexists(REPO / relative):
            raise EvidenceError("failing A requires absent downstream experiments")


def source_summary(authorized):
    bindings = plain(authorized.bindings)
    if bindings["campaign"] != "v12-full-census":
        raise EvidenceError("source adapter returned the wrong campaign")
    outcomes = bindings["outcome_counts"]
    support = bindings["support_status_counts"]
    result = {
        "sealed": True, "campaign_number": 12,
        "inventory_candidates": bindings["all_records_count"],
        "candidates": bindings["all_records_count"],
        "inventory_families": bindings["inventory_families_count"],
        "translation_attempts": bindings["translation_attempts_count"],
        "translated_successfully": outcomes["success"],
        "translation_status_counts": {
            key.replace("-", "_"): value for key, value in outcomes.items()
        },
        "supported_tasks": support["supported"],
        "unsupported_tasks": support["unsupported"],
        "indeterminate_tasks": support["indeterminate"],
        "unassigned_supported_tasks": (
            bindings["eligible_records_count"] - bindings["confirmation_a_count"]
            - bindings["guided_b_count"]
        ),
        "reason_incidence_counts": {
            key.replace("-", "_"): value
            for key, value in bindings["support_exclusion_counts"].items()
        },
        "resource_exclusion_counts": bindings["resource_exclusion_counts"],
        "resource_exclusions_by_family": {
            family: {key: counts[key] for key in ("memory", "time")}
            for family, counts in bindings["resource_exclusions_by_family"].items()
        },
        "logical_shards": 820, "whole_campaign_rerun": True,
        "prior_campaign_shards_reused": 0,
        "time_limit_seconds": 1800, "memory_limit_mib": 24576,
        "source_chain_verified": True, "environment_verified": True,
        "scheduler_verified": True, "cohort_disjoint": True,
    }
    for role, cohort in (("a", authorized.confirmation_a), ("b", authorized.guided_b)):
        records = cohort.records
        result[role + "_tasks"] = len(records)
        result[role + "_families"] = len({task["family"] for task in records})
        for name, flag in (("shadow", "is_shadow_unrepresented"),
                           ("prior", "is_all_prior_unrepresented")):
            selected = [task for task in records if task[flag]]
            result[f"{role}_{name}_tasks"] = len(selected)
            result[f"{role}_{name}_families"] = len({task["family"] for task in selected})
    return R._validate_source_audit(result)


def q(value):
    return R.normalize_fraction_record(value, "analysis fraction")


def _minimum(values):
    normalized = [q(value) for value in values]
    if not normalized or any(value is None for value in normalized):
        return None
    return min(normalized, key=lambda value: Fraction(value["numerator"], value["denominator"]))


def _numeric_fraction(value):
    if value is None:
        return None
    if type(value) not in (int, float) or not math.isfinite(value):
        raise EvidenceError("timing is not a finite number")
    exact = Fraction(value)
    return {"numerator": exact.numerator, "denominator": exact.denominator}


def _comparison(comparison, gate):
    support = comparison["support"]
    predictors = comparison["predictors"]
    return {
        "comparison_tasks": support.get("tasks_with_shared_pairs", 0),
        "comparison_families": support.get("families_with_shared_pairs", 0),
        "target_strict_pairs": support.get("target_strict", 0),
        "i_concordance": q(predictors["I"]["equal_family"]["macro"]),
        "orientation": {
            "orders_identical": comparison["target_orientations"]["orders_identical"],
            "inverse_u_tied": comparison["target_orientations"]["inverse_U_null"] == "tied_within_task",
        },
        "baselines": {
            name: {
                "concordance": q(predictors[key]["equal_family"]["macro"]),
                "margin": q(gate["controls"][key]["advantage"]),
                "bootstrap_lower": q(gate["controls"][key]["bootstrap"]["lower_95"]),
                "bootstrap_upper": q(gate["controls"][key]["bootstrap"]["upper_95"]),
                "lofo_minimum": _minimum(gate["controls"][key]["leave_one_family_out_differences"].values()),
            }
            for name, key in PREDICTOR_NAMES.items() if name != "incidence"
        },
    }


def normalize_a(analysis):
    primary = analysis["primary"]
    if set(primary["frontier_statuses"]) - set(R.A_FRONTIER_STATUSES):
        raise EvidenceError("unknown Confirmation A frontier status")
    expected_labels = {f"pdb_{name}_shadow" for name in R.A_CONSTRUCTION_CONFIGURATIONS}
    if set(primary["construction_by_label"]) != expected_labels or any(
        set(counts) - set(R.A_CONSTRUCTION_STATUSES)
        for counts in primary["construction_by_label"].values()
    ):
        raise EvidenceError("unknown Confirmation A construction outcome")
    strict = analysis["sensitivity"]["all_predictor_strict"]
    regret = analysis["sensitivity"]["top_choice_regret"]
    tightness = analysis["secondary_diagnostics"]["tightness"]
    if set(tightness) != {PREDICTOR_NAMES[name] for name in R.CERTIFICATE_PREDICTORS}:
        raise EvidenceError("certificate-tightness predictor set changed")
    if any((item["tasks"], item["families"]) != (tightness["I"]["tasks"], tightness["I"]["families"])
           for item in tightness.values()):
        raise EvidenceError("certificate-tightness support differs by predictor")
    timing = analysis["secondary_diagnostics"]["computation_time"]
    times = {key: timing[key] for key in (
        "cells", "tasks", "tasks_with_positive_partition_time",
        "families_with_positive_partition_time",
    )}
    times.update({key: _numeric_fraction(timing[key]) for key in (
        "pooled_masked_seconds", "pooled_partition_audit_seconds",
        "equal_family_mean_of_task_ratios",
    )})
    masked, partition = timing["pooled_masked_seconds"], timing["pooled_partition_audit_seconds"]
    expected_ratio = masked / partition if partition > 0 else None
    if timing["pooled_masked_over_partition_ratio"] != expected_ratio:
        raise EvidenceError("analyzed timing ratio is inconsistent")
    exact_ratio = Fraction(masked) / Fraction(partition) if partition > 0 else None
    times["pooled_masked_over_partition_ratio"] = (
        {"numerator": exact_ratio.numerator, "denominator": exact_ratio.denominator}
        if exact_ratio is not None else None
    )
    prior = analysis["strata"]["all_prior_unrepresented"]
    return {
        "sealed": True,
        "eligible_tasks": primary["eligible_tasks"],
        "eligible_families": primary["eligible_families"],
        **_comparison(analysis["comparison"], analysis["gates"]["primary"]),
        "all_prior": _comparison(prior["comparison"], prior["gate"]),
        "all_strict": {
            "comparison_tasks": strict["support"].get("tasks_with_shared_pairs", 0),
            "comparison_families": strict["support"].get("families_with_shared_pairs", 0),
            "pairs": strict["support"].get("grand_shared_strict", 0),
            "predictors": {name: q(strict["predictors"][key]["equal_family"]["macro"])
                           for name, key in PREDICTOR_NAMES.items()},
        },
        "oracle_regret": {
            "tasks": regret["support"]["eligible_tasks"],
            "families": regret["support"]["eligible_families"],
            "predictors": {name: {
                "equal_family_regret": q(regret["predictors"][key]["equal_family_normalized_regret"]),
                "tie_rate": q(regret["predictors"][key]["top_choice_tie_rate"]),
            } for name, key in PREDICTOR_NAMES.items()},
        },
        "certificate_tightness": {
            "tasks": tightness["I"]["tasks"], "families": tightness["I"]["families"],
            "predictors": {name: {
                "equal_family": q(tightness[PREDICTOR_NAMES[name]]["equal_family_macro"]),
                **{key: q(value) for key, value in tightness[PREDICTOR_NAMES[name]]["family_quantiles_nearest_rank"].items()},
            } for name in R.CERTIFICATE_PREDICTORS},
        },
        "timing": times,
        "frontier_statuses": {key: primary["frontier_statuses"].get(key, 0) for key in R.A_FRONTIER_STATUSES},
        "construction_by_configuration": {
            name: {key: primary["construction_by_label"][f"pdb_{name}_shadow"].get(key, 0)
                   for key in R.A_CONSTRUCTION_STATUSES}
            for name in R.A_CONSTRUCTION_CONFIGURATIONS
        },
        "cegar_fallback_tasks": primary["cegar_fallback_tasks"],
    }


def _hardware(summary, cells):
    _imports()
    import pdb_confirmation_run_cell as RunCell
    RunCell.validate_hardware_summary(summary, cells)
    return {
        "receipt_sealed": True, "cells": cells,
        "processor_models": len(summary["processor_model_counts"]),
        "architectures": len(summary["architecture_counts"]),
    }


def _check_double_analysis(raw, prefix, expected_pass):
    result_raw, repeat_raw = raw[prefix + "_result"], raw[prefix + "_repeat"]
    result = _canonical(result_raw, prefix + " result")
    receipt = _canonical(raw[prefix + "_receipt"], prefix + " receipt")
    execution = _canonical(raw[prefix + "_execution"], prefix + " execution")
    fetch = _canonical(raw[prefix + "_fetch"], prefix + " fetch")
    for name in ("receipt", "execution", "fetch"):
        if raw[f"{prefix}_{name}_pin"] != (_sha(raw[f"{prefix}_{name}"]) + "\n").encode("ascii"):
            raise EvidenceError(f"{prefix} {name} sidecar differs")
    if result_raw != repeat_raw or any((
        receipt["first_output_sha256"] != _sha(result_raw),
        receipt["second_output_sha256"] != _sha(repeat_raw),
        receipt["outputs_byte_identical"] is not True,
        receipt["execution_receipt_sha256"] != _sha(raw[prefix + "_execution"]),
        receipt["fetch_receipt_sha256"] != _sha(raw[prefix + "_fetch"]),
        receipt["input_properties_sha256"] != fetch["properties_sha256"],
        result["input"]["sha256"] != receipt["input_properties_sha256"],
        result["input"]["fetch_receipt_sha256"] != receipt["fetch_receipt_sha256"],
        result["input"]["execution_receipt_sha256"] != receipt["execution_receipt_sha256"],
        result["input"]["hardware"] != receipt["hardware"],
        receipt["hardware"] != execution["hardware"],
    )):
        raise EvidenceError(f"{prefix} double-analysis chain differs")
    if prefix == "a" and any((
        result["gates"]["pass"] is not expected_pass,
        result["guided_study_authorized"] is not expected_pass,
        receipt["confirmation_a_complete_gate_passed"] is not expected_pass,
        receipt["guided_study_authorized"] is not expected_pass,
    )):
        raise EvidenceError("Confirmation A receipt disagrees with its outcome branch")
    return result, receipt


def load_evidence(*, source_revision, results_revision, artifact_pins,
                  result_pins, expected_a_pass):
    R._validate_production_pin_contract(result_pins, expected_a_pass)
    _check_revision(source_revision, "source seal revision")
    _check_revision(results_revision, "results revision")
    # The downstream projector will be installed before a passing branch is
    # enabled. No downstream evidence is read while this boundary is closed.
    if expected_a_pass:
        raise EvidenceError("passing-branch production projection is not yet enabled")
    _require_downstream_absence()
    raw = _read_artifacts(results_revision, A_PATHS, artifact_pins)
    jj, _safe, adapter, _snapshot = _imports()
    jj.require_ancestor(REPO, source_revision, results_revision)
    authorized = adapter.load_authorized_cohorts(source_revision)
    if authorized.bindings.attestation_sha256 != result_pins["source_audit"]:
        raise EvidenceError("source attestation differs from its production pin")
    import pdb_terminal_incidence_confirmation_a_protocol as A
    freeze, materials = A._load_freeze(A.FREEZE_PATH)
    if freeze != _canonical(raw["a_freeze"], "Confirmation A freeze"):
        raise EvidenceError("Confirmation A freeze changed during validation")
    if materials.source_audit != A._source_payload(authorized):
        raise EvidenceError("Confirmation A freeze differs from the V12 adapter")
    jj.require_ancestor(REPO, source_revision, freeze["freeze_repository_revision"])
    jj.require_ancestor(REPO, freeze["freeze_repository_revision"], results_revision)
    result, receipt = _check_double_analysis(raw, "a", expected_a_pass)
    if _sha(raw["a_result"]) != result_pins["confirmation_a"]:
        raise EvidenceError("Confirmation A result differs from its production pin")
    schema = "symbolic-search-heuristics/pdb-terminal-incidence-confirmation-a-analysis/v4"
    if any((
        result["schema"] != schema,
        receipt["schema"] != schema + "/double-execution",
        result["protocol"] != A.PROTOCOL,
        result["analysis_protocol"] != A.ANALYSIS_PROTOCOL,
        receipt["analysis_protocol"] != A.ANALYSIS_PROTOCOL,
        receipt["bootstrap_replicates"] != A.BOOTSTRAP_REPLICATES,
        receipt["bootstrap_seed"] != A.BOOTSTRAP_SEED,
        receipt["planner_identity"] != freeze["planner"],
        receipt["first_output"] != str(REPO / A_PATHS["a_result"]),
        receipt["second_output"] != str(REPO / A_PATHS["a_repeat"]),
        result["input"]["path"] != str(EXPERIMENTS / "data" / "exp_pdb_terminal_incidence_confirmation_a-eval" / "properties"),
        result["matrix"]["cells"] != 2600,
        result["matrix"]["tasks"] != 650,
        result["matrix"]["configs"] != 4,
    )):
        raise EvidenceError("Confirmation A production identity changed")
    evidence = {
        "source_audit": source_summary(authorized),
        "confirmation_a": normalize_a(result),
        "hardware": {
            "a": _hardware(receipt["hardware"], 2600), "direct": None, "b": None,
        },
    }
    if R.classify(evidence).a_pass is not expected_a_pass:
        raise EvidenceError("recomputed paper gate disagrees with the sealed result")
    return evidence
