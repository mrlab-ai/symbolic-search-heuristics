#!/usr/bin/env python3
"""Render terminal-incidence outcomes from sealed, normalized evidence.

Production modes require explicit committed source/results revisions and
non-sentinel digest pins. Synthetic fixtures never authorize a paper build.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import stat
import sys
import tempfile
import unittest
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path


ZERO_SHA256 = "0" * 64
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
PRODUCTION_EXPECTED_A_PASS = None
PRODUCTION_SOURCE_SEAL_REVISION = None
PRODUCTION_RESULTS_REVISION = None
PRODUCTION_ARTIFACT_PINS = {}
PRODUCTION_DIGEST_PINS = {
    "source_audit": ZERO_SHA256,
    "confirmation_a": ZERO_SHA256,
    # None means that the artifact is required to be absent.  Once the sealed
    # A result exists, a passing branch replaces both values with real digests;
    # a failing branch retains both None values.
    "direct_metric_choice": None,
    "confirmation_b": None,
}
PAPER_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PAPER_ROOT / "generated" / "terminal-incidence-results.tex"
MAX_OUTPUT_BYTES = 128 * 1024

BASELINES = (
    "masked_add_size",
    "value_count",
    "kD",
    "mQ",
    "mJ",
    "cartesian",
    "width",
    "apply",
    "layerwise_min_certificate",
)
BASELINE_TEX_LABELS = (
    "$D$",
    "$\\sum_g k_g$",
    "$kD$",
    "$mQ$",
    "$mJ$",
    "Cartesian",
    "width",
    "Apply",
    "$B_\\wedge$",
)
ORDERING_PREDICTORS = ("incidence", *BASELINES)
ORDERING_PREDICTOR_TEX_LABELS = ("$I$", *BASELINE_TEX_LABELS)
CERTIFICATE_PREDICTORS = (
    "incidence",
    "kD",
    "mQ",
    "mJ",
    "cartesian",
    "width",
    "apply",
    "layerwise_min_certificate",
)
B_CONFIGURATIONS = (
    "blind",
    "bdd_prefix",
    "goal_prefix",
    "goal_fill",
    "cegar",
    "exact_width_k32",
    "cap_aware_k32",
    "incidence_guided",
    "matched_work",
)
B_CONFIGURATION_TEX_LABELS = (
    "blind",
    "BDD-prefix",
    "goal-prefix",
    "goal-fill",
    "CEGAR",
    "exact-width $K=32$",
    "cap-aware $K=32$",
    "$I$-guided",
    "matched-work",
)
SOURCE_EXCLUSION_CATEGORIES = (
    "translation_input_rejected",
    "no_serialized_operators",
    "nonpositive_serialized_operator_cost",
    "serialized_axioms",
    "serialized_conditional_effects",
    "normalized_axioms",
)
A_CONSTRUCTION_CONFIGURATIONS = (
    "bdd_prefix",
    "goal_prefix",
    "goal_fill",
    "cegar",
)
A_CONSTRUCTION_STATUSES = ("completed", "failed", "absent")
B_ALTERNATIVES = B_CONFIGURATIONS[:6]
A_FRONTIER_STATUSES = (
    "eligible",
    "invalid_primary_terminal_outcome",
    "primary_construction_failure",
    "primary_construction_absent",
    "invalid_or_missing_primary_prefix",
    "inconsistent_primary_solution_cost",
    "insufficient_completed_layers",
    "missing_retained_layer",
)
DIRECT_WORK_FIELDS = (
    "candidate_count",
    "probe_state_profiles",
    "probe_cut_entries",
    "incidence_layer_measurements",
    "joint_layer_measurements",
    "joint_cut_entries",
    "joint_summed_cut_entries",
)
B_OVERHEAD_FIELDS = (
    "guided_probe_wall_seconds",
    "guided_selection_wall_seconds",
    "matched_probe_wall_seconds",
    "matched_selection_wall_seconds",
    "guided_probe_peak_delta_kb",
    "guided_selection_peak_delta_kb",
    "matched_probe_peak_delta_kb",
    "matched_selection_peak_delta_kb",
)
CONTRAST_FIELDS = (
    "coverage_incidence",
    "coverage_comparator",
    "mean_improvement",
    "bootstrap_lower",
    "bootstrap_upper",
    "lofo_minimum",
    "outcome_decomposition",
)

TITLE_SELECTION = (
    "Terminal Incidence Predicts Fixed-Frontier Partition Effort and "
    "Guides PDB Selection"
)
TITLE_PREDICTOR = (
    "Terminal Incidence Predicts Fixed-Frontier Partition Effort in Symbolic Search"
)
TITLE_CERTIFICATES = (
    "Fixed-Frontier Partition Effort in Symbolic Search: "
    "Terminal-Incidence Certificates and Their Limits"
)


class RenderError(ValueError):
    """The evidence cannot authorize a deterministic result rendering."""


def _validate_production_pin_contract(
    pins: object, expected_a_pass: bool | None,
) -> None:
    """Validate the final branch before any production artifact is opened."""
    expected_keys = {
        "source_audit",
        "confirmation_a",
        "direct_metric_choice",
        "confirmation_b",
    }
    if type(pins) is not dict or set(pins) != expected_keys:
        raise RenderError("production digest-pin schema changed")
    if type(expected_a_pass) is not bool:
        raise RenderError("the production A outcome branch is unset")
    for name in ("source_audit", "confirmation_a"):
        digest = pins[name]
        if (
            type(digest) is not str
            or SHA256_RE.fullmatch(digest) is None
            or digest == ZERO_SHA256
        ):
            raise RenderError(f"production digest pin is unset: {name}")
    for name in ("direct_metric_choice", "confirmation_b"):
        digest = pins[name]
        if expected_a_pass:
            if (
                type(digest) is not str
                or SHA256_RE.fullmatch(digest) is None
                or digest == ZERO_SHA256
            ):
                raise RenderError(
                    f"passing A requires a production digest pin: {name}"
                )
        elif digest is not None:
            raise RenderError(
                f"failing A requires exact downstream absence: {name}"
            )


def normalize_fraction_record(value: object, path: str) -> dict | None:
    """Project an analyzer fraction record to canonical string-free evidence."""
    if value is None:
        return None
    if type(value) is not dict:
        raise RenderError(f"{path} must be a fraction record or null")
    keys = set(value)
    display_keys = keys - {"numerator", "denominator"}
    if display_keys not in (set(), {"value"}, {"decimal"}):
        raise RenderError(f"{path} fraction schema changed")
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise RenderError(f"{path} is not an exact fraction")
    exact = Fraction(numerator, denominator)
    if (exact.numerator, exact.denominator) != (numerator, denominator):
        raise RenderError(f"{path} is not a canonical fraction")
    if display_keys:
        display_key = next(iter(display_keys))
        display = value[display_key]
        if type(display) not in (int, float):
            raise RenderError(f"{path}.{display_key} disagrees with its fraction")
        if type(display) is int:
            agrees = Fraction(display) == exact
        else:
            if not math.isfinite(display):
                raise RenderError(
                    f"{path}.{display_key} disagrees with its fraction"
                )
            try:
                expected_display = float(exact)
            except OverflowError as error:
                raise RenderError(
                    f"{path}.{display_key} cannot represent its fraction"
                ) from error
            agrees = display == expected_display
        if not agrees:
            raise RenderError(f"{path}.{display_key} disagrees with its fraction")
    return {"numerator": exact.numerator, "denominator": exact.denominator}


class OutcomeBranch(Enum):
    A_FAIL = "a-fail"
    A_PASS_SELECTORS_UNTESTED = "a-pass-selectors-untested"
    A_PASS_DIRECT_FAIL_B_FAIL = "a-pass-direct-fail-b-fail"
    A_PASS_DIRECT_FAIL_B_PASS = "a-pass-direct-fail-b-pass"
    A_PASS_DIRECT_PASS_B_FAIL = "a-pass-direct-pass-b-fail"
    A_PASS_DIRECT_PASS_B_PASS = "a-pass-direct-pass-b-pass"


@dataclass(frozen=True)
class Outcome:
    branch: OutcomeBranch
    a_pass: bool
    direct_pass: bool | None
    b_pass: bool | None


def _keys(record: object, expected: set[str], path: str) -> dict:
    if type(record) is not dict:
        raise RenderError(f"{path} must be a dict")
    actual = set(record)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected, key=repr)
        raise RenderError(f"{path} schema mismatch; missing={missing}, extra={extra}")
    return record


def _boolean(record: dict, key: str, path: str) -> bool:
    value = record[key]
    if type(value) is not bool:
        raise RenderError(f"{path}.{key} must be a bool")
    return value


def _integer(
    record: dict,
    key: str,
    path: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    value = record[key]
    if type(value) is not int:
        raise RenderError(f"{path}.{key} must be an int")
    if value < minimum or (maximum is not None and value > maximum):
        raise RenderError(f"{path}.{key} is outside its allowed range")
    return value


def _rational(
    record: dict,
    key: str,
    path: str,
    *,
    minimum: Fraction = Fraction(-1),
    maximum: Fraction | None = Fraction(1),
) -> Fraction | None:
    value = record[key]
    if value is None:
        return None
    fraction_path = f"{path}.{key}"
    fraction = _keys(value, {"numerator", "denominator"}, fraction_path)
    numerator = fraction["numerator"]
    denominator = fraction["denominator"]
    if type(numerator) is not int:
        raise RenderError(f"{fraction_path}.numerator must be an int")
    if type(denominator) is not int or denominator <= 0:
        raise RenderError(f"{fraction_path}.denominator must be a positive int")
    exact = Fraction(numerator, denominator)
    if exact.numerator != numerator or exact.denominator != denominator:
        raise RenderError(f"{fraction_path} must be a canonical rational record")
    if exact < minimum or (maximum is not None and exact > maximum):
        raise RenderError(f"{path}.{key} is outside its allowed range")
    return exact


def _fraction(record: dict, key: str) -> Fraction | None:
    value = record[key]
    if value is None:
        return None
    return Fraction(value["numerator"], value["denominator"])


def _validate_orientation(value: object, path: str) -> dict:
    record = _keys(value, {"orders_identical", "inverse_u_tied"}, path)
    _boolean(record, "orders_identical", path)
    _boolean(record, "inverse_u_tied", path)
    return record


def _orientation_gate(record: dict) -> bool:
    return record["orders_identical"] and record["inverse_u_tied"]


def _reject_artifact_text(value: object, path: str = "evidence") -> None:
    """Reject every artifact-provided string value before template rendering."""
    if type(value) is str:
        raise RenderError(f"{path} contains forbidden artifact-provided text")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise RenderError(f"{path} contains a non-string schema key")
            _reject_artifact_text(child, f"{path}.{key}")
    elif type(value) in (list, tuple, set):
        for index, child in enumerate(value):
            _reject_artifact_text(child, f"{path}[{index}]")


def _validate_sorted_indices(
    value: object, path: str, *, upper_bound: int
) -> list[int]:
    if type(value) is not list:
        raise RenderError(f"{path} must be a list")
    if any(type(index) is not int for index in value):
        raise RenderError(f"{path} must contain only integer indices")
    if value != sorted(value) or len(value) != len(set(value)):
        raise RenderError(f"{path} must be sorted and unique")
    if any(index < 0 or index >= upper_bound for index in value):
        raise RenderError(f"{path} contains an out-of-range index")
    return value


def _validate_source_audit(value: object) -> dict:
    """Validate the fresh V12 census, not the superseded selective repair."""
    path = "evidence.source_audit"
    record = _keys(
        value,
        {
            "sealed", "campaign_number", "inventory_candidates", "candidates",
            "inventory_families", "translation_attempts",
            "translated_successfully", "translation_status_counts",
            "supported_tasks", "unsupported_tasks", "indeterminate_tasks",
            "unassigned_supported_tasks", "reason_incidence_counts",
            "resource_exclusion_counts", "resource_exclusions_by_family",
            "logical_shards", "whole_campaign_rerun", "prior_campaign_shards_reused",
            "time_limit_seconds", "memory_limit_mib",
            "source_chain_verified", "environment_verified",
            "scheduler_verified", "cohort_disjoint",
            "a_tasks", "a_families", "a_shadow_tasks", "a_shadow_families",
            "a_prior_tasks", "a_prior_families",
            "b_tasks", "b_families", "b_shadow_tasks", "b_shadow_families",
            "b_prior_tasks", "b_prior_families",
        },
        path,
    )
    if not _boolean(record, "sealed", path):
        raise RenderError("the source audit is not sealed")
    candidates = _integer(record, "inventory_candidates", path)
    execution_candidates = _integer(record, "candidates", path)
    families = _integer(record, "inventory_families", path, maximum=candidates)
    attempts = _integer(record, "translation_attempts", path, maximum=candidates)
    translated = _integer(record, "translated_successfully", path, maximum=attempts)
    statuses = _keys(
        record["translation_status_counts"],
        {"success", "input_rejected", "resource_excluded"},
        f"{path}.translation_status_counts",
    )
    for key in statuses:
        _integer(statuses, key, f"{path}.translation_status_counts", maximum=attempts)
    supported = _integer(record, "supported_tasks", path, maximum=candidates)
    unsupported = _integer(record, "unsupported_tasks", path, maximum=candidates)
    indeterminate = _integer(record, "indeterminate_tasks", path, maximum=candidates)
    unassigned = _integer(record, "unassigned_supported_tasks", path, maximum=supported)
    reasons = _keys(
        record["reason_incidence_counts"], set(SOURCE_EXCLUSION_CATEGORIES),
        f"{path}.reason_incidence_counts",
    )
    for key in reasons:
        _integer(reasons, key, f"{path}.reason_incidence_counts", maximum=unsupported)
    resources = _keys(
        record["resource_exclusion_counts"], {"memory", "time"},
        f"{path}.resource_exclusion_counts",
    )
    for key in resources:
        _integer(resources, key, f"{path}.resource_exclusion_counts", maximum=indeterminate)
    by_family = record["resource_exclusions_by_family"]
    if type(by_family) is not dict or len(by_family) > families:
        raise RenderError("source resource-exclusion family census changed")
    totals = {"memory": 0, "time": 0}
    for family, counts in by_family.items():
        if type(family) is not str or not re.fullmatch(r"[a-z0-9-]+", family):
            raise RenderError("source resource-exclusion family is invalid")
        _keys(counts, set(totals), f"{path}.resource_exclusions_by_family.{family}")
        for key in totals:
            totals[key] += _integer(
                counts, key, f"{path}.resource_exclusions_by_family.{family}",
                maximum=indeterminate,
            )
        if sum(counts.values()) == 0:
            raise RenderError("source resource-exclusion family is empty")
    logical_shards = _integer(record, "logical_shards", path)
    prior_reused = _integer(record, "prior_campaign_shards_reused", path)
    time_limit = _integer(record, "time_limit_seconds", path)
    memory_limit = _integer(record, "memory_limit_mib", path)
    whole_rerun = _boolean(record, "whole_campaign_rerun", path)
    verification = all(
        _boolean(record, key, path)
        for key in (
            "source_chain_verified", "environment_verified",
            "scheduler_verified", "cohort_disjoint",
        )
    )
    for role in ("a", "b"):
        tasks = _integer(record, f"{role}_tasks", path, maximum=supported)
        cohort_families = _integer(
            record, f"{role}_families", path, maximum=min(tasks, families),
        )
        for stratum in ("shadow", "prior"):
            count = _integer(record, f"{role}_{stratum}_tasks", path, maximum=tasks)
            _integer(
                record, f"{role}_{stratum}_families", path,
                maximum=min(count, cohort_families),
            )
    authorized = (
        _integer(record, "campaign_number", path) == 12
        and candidates == execution_candidates == attempts == 1640
        and logical_shards == 820
        and families > 0
        and translated == statuses["success"]
        and sum(statuses.values()) == attempts
        and supported + unsupported + indeterminate == candidates
        and supported <= translated
        and indeterminate == statuses["resource_excluded"]
        and sum(resources.values()) == indeterminate
        and totals == resources
        and reasons["translation_input_rejected"] == statuses["input_rejected"]
        and all(
            reasons[key] <= translated for key in SOURCE_EXCLUSION_CATEGORIES
            if key != "translation_input_rejected"
        )
        and sum(reasons.values()) >= unsupported
        and whole_rerun and prior_reused == 0
        and time_limit == 1800 and memory_limit == 24576
        and verification
        and record["a_tasks"] == 650 and record["a_families"] >= 28
        and record["a_shadow_families"] >= 12
        and record["a_prior_tasks"] >= 100 and record["a_prior_families"] >= 10
        and record["b_tasks"] == 300 and record["b_families"] >= 30
        and record["b_shadow_families"] >= 12
        and record["b_prior_tasks"] >= 50 and record["b_prior_families"] >= 10
        and record["a_tasks"] + record["b_tasks"] + unassigned == supported
    )
    if not authorized:
        raise RenderError("the sealed source audit does not authorize both cohorts")
    return record


def _require_rational_presence(
    values: list[Fraction | None], *, required: bool, path: str
) -> None:
    if required and any(value is None for value in values):
        raise RenderError(f"{path} is incomplete for its positive support")
    if not required and any(value is not None for value in values):
        raise RenderError(f"{path} must be null at insufficient support")


def _validate_baselines(
    value: object,
    path: str,
    *,
    comparison_tasks: int,
    comparison_families: int,
) -> dict:
    record = _keys(value, set(BASELINES), path)
    for baseline in BASELINES:
        result_path = f"{path}.{baseline}"
        result = _keys(
            record[baseline],
            {
                "concordance",
                "margin",
                "bootstrap_lower",
                "bootstrap_upper",
                "lofo_minimum",
            },
            result_path,
        )
        concordance = _rational(
            result, "concordance", result_path, minimum=Fraction(0)
        )
        margin = _rational(result, "margin", result_path)
        lower = _rational(result, "bootstrap_lower", result_path)
        upper = _rational(result, "bootstrap_upper", result_path)
        lofo = _rational(result, "lofo_minimum", result_path)
        _require_rational_presence(
            [concordance, margin, lower, upper],
            required=comparison_tasks > 0 and comparison_families > 0,
            path=f"{result_path} comparison statistics",
        )
        _require_rational_presence(
            [lofo],
            required=comparison_tasks > 0 and comparison_families >= 2,
            path=f"{result_path} leave-one-family-out statistic",
        )
        if lower is not None and upper is not None and lower > upper:
            raise RenderError(f"{result_path} bootstrap endpoints are reversed")
    return record


def _validate_a_stratum(value: object, path: str) -> dict:
    record = _keys(
        value,
        {
            "comparison_tasks",
            "comparison_families",
            "target_strict_pairs",
            "i_concordance",
            "baselines",
            "orientation",
        },
        path,
    )
    comparison_tasks = _integer(record, "comparison_tasks", path, maximum=650)
    comparison_families = _integer(
        record,
        "comparison_families",
        path,
        maximum=comparison_tasks,
    )
    _integer(record, "target_strict_pairs", path)
    incidence = _rational(record, "i_concordance", path, minimum=Fraction(0))
    if comparison_tasks > 0 and comparison_families == 0:
        raise RenderError(f"{path} has tasks but no families")
    _require_rational_presence(
        [incidence],
        required=comparison_tasks > 0 and comparison_families > 0,
        path=f"{path}.i_concordance",
    )
    _validate_baselines(
        record["baselines"],
        f"{path}.baselines",
        comparison_tasks=comparison_tasks,
        comparison_families=comparison_families,
    )
    _validate_orientation(record["orientation"], f"{path}.orientation")
    _validate_a_baseline_consistency(record, path)
    return record


def _validate_a_baseline_consistency(record: dict, path: str) -> None:
    incidence = _fraction(record, "i_concordance")
    for baseline in BASELINES:
        result = record["baselines"][baseline]
        concordance = _fraction(result, "concordance")
        margin = _fraction(result, "margin")
        if incidence is None or concordance is None or margin is None:
            if any(value is not None for value in (incidence, concordance, margin)):
                raise RenderError(
                    f"{path}.{baseline} has a partial concordance comparison"
                )
        elif incidence - concordance != margin:
            raise RenderError(f"{path}.{baseline} margin is inconsistent")


def _validate_predictor_values(
    value: object, path: str, *, positive_support: bool
) -> dict:
    record = _keys(value, set(ORDERING_PREDICTORS), path)
    values = []
    for predictor in ORDERING_PREDICTORS:
        values.append(_rational(record, predictor, path, minimum=Fraction(0)))
    _require_rational_presence(
        values, required=positive_support, path=f"{path} predictor values"
    )
    return record


def _validate_all_strict(value: object, path: str) -> dict:
    record = _keys(
        value,
        {"comparison_tasks", "comparison_families", "pairs", "predictors"},
        path,
    )
    tasks = _integer(record, "comparison_tasks", path, maximum=650)
    families = _integer(record, "comparison_families", path, maximum=tasks)
    pairs = _integer(record, "pairs", path)
    if (tasks == 0) != (families == 0) or (pairs > 0 and not tasks):
        raise RenderError(f"{path} has inconsistent support")
    _validate_predictor_values(
        record["predictors"],
        f"{path}.predictors",
        positive_support=tasks > 0,
    )
    return record


def _validate_oracle_regret(value: object, path: str) -> dict:
    record = _keys(value, {"tasks", "families", "predictors"}, path)
    tasks = _integer(record, "tasks", path, maximum=650)
    families = _integer(record, "families", path, maximum=tasks)
    if (tasks == 0) != (families == 0):
        raise RenderError(f"{path} has inconsistent support")
    predictors = _keys(
        record["predictors"], set(ORDERING_PREDICTORS), f"{path}.predictors"
    )
    for predictor in ORDERING_PREDICTORS:
        predictor_path = f"{path}.predictors.{predictor}"
        summary = _keys(
            predictors[predictor],
            {"equal_family_regret", "tie_rate"},
            predictor_path,
        )
        regret = _rational(
            summary, "equal_family_regret", predictor_path, minimum=Fraction(0)
        )
        tie_rate = _rational(
            summary, "tie_rate", predictor_path, minimum=Fraction(0)
        )
        _require_rational_presence(
            [regret, tie_rate],
            required=tasks > 0,
            path=predictor_path,
        )
    return record


def _validate_tightness(value: object, path: str) -> dict:
    record = _keys(value, {"tasks", "families", "predictors"}, path)
    tasks = _integer(record, "tasks", path, maximum=650)
    families = _integer(record, "families", path, maximum=tasks)
    if (tasks == 0) != (families == 0):
        raise RenderError(f"{path} has inconsistent support")
    predictors = _keys(
        record["predictors"], set(CERTIFICATE_PREDICTORS), f"{path}.predictors"
    )
    for predictor in CERTIFICATE_PREDICTORS:
        predictor_path = f"{path}.predictors.{predictor}"
        summary = _keys(
            predictors[predictor],
            {"equal_family", "q25", "q50", "q75"},
            predictor_path,
        )
        values = [
            _rational(summary, field, predictor_path, minimum=Fraction(0))
            for field in ("equal_family", "q25", "q50", "q75")
        ]
        _require_rational_presence(
            values,
            required=tasks > 0,
            path=f"{predictor_path} tightness panel",
        )
        quantiles = values[1:]
        if all(item is not None for item in quantiles) and not (
            quantiles[0] <= quantiles[1] <= quantiles[2]
        ):
            raise RenderError(f"{predictor_path} tightness quantiles are unordered")
    return record


def _validate_a_timing(value: object, path: str) -> dict:
    record = _keys(
        value,
        {
            "cells",
            "tasks",
            "tasks_with_positive_partition_time",
            "families_with_positive_partition_time",
            "pooled_masked_seconds",
            "pooled_partition_audit_seconds",
            "pooled_masked_over_partition_ratio",
            "equal_family_mean_of_task_ratios",
        },
        path,
    )
    cells = _integer(record, "cells", path, maximum=2600)
    tasks = _integer(record, "tasks", path, maximum=650)
    positive_tasks = _integer(
        record, "tasks_with_positive_partition_time", path, maximum=tasks
    )
    positive_families = _integer(
        record,
        "families_with_positive_partition_time",
        path,
        maximum=positive_tasks,
    )
    if cells < tasks:
        raise RenderError(f"{path}.cells is smaller than its task support")
    if (positive_tasks == 0) != (positive_families == 0):
        raise RenderError(f"{path} has inconsistent positive-time support")
    masked = _rational(
        record,
        "pooled_masked_seconds",
        path,
        minimum=Fraction(0),
        maximum=None,
    )
    partition = _rational(
        record,
        "pooled_partition_audit_seconds",
        path,
        minimum=Fraction(0),
        maximum=None,
    )
    pooled_ratio = _rational(
        record,
        "pooled_masked_over_partition_ratio",
        path,
        minimum=Fraction(0),
        maximum=None,
    )
    equal_family_ratio = _rational(
        record,
        "equal_family_mean_of_task_ratios",
        path,
        minimum=Fraction(0),
        maximum=None,
    )
    _require_rational_presence(
        [masked, partition], required=True, path=f"{path} pooled totals"
    )
    expected_positive = partition is not None and partition > 0
    if expected_positive != (positive_tasks > 0):
        raise RenderError(f"{path} positive-time support disagrees with its total")
    _require_rational_presence(
        [pooled_ratio], required=expected_positive, path=f"{path} pooled ratio"
    )
    _require_rational_presence(
        [equal_family_ratio],
        required=positive_families > 0,
        path=f"{path} equal-family ratio",
    )
    if pooled_ratio is not None and pooled_ratio != masked / partition:
        raise RenderError(f"{path} pooled timing ratio is inconsistent")
    return record


def _validate_a_attrition(value: object, path: str, source_tasks: int) -> dict:
    record = _keys(value, set(A_FRONTIER_STATUSES), path)
    for status in A_FRONTIER_STATUSES:
        _integer(record, status, path, maximum=source_tasks)
    if sum(record.values()) != source_tasks:
        raise RenderError(f"{path} does not account for every A task")
    return record


def _validate_a_construction(value: object, path: str, source_tasks: int) -> dict:
    record = _keys(value, set(A_CONSTRUCTION_CONFIGURATIONS), path)
    for configuration in A_CONSTRUCTION_CONFIGURATIONS:
        counts_path = f"{path}.{configuration}"
        counts = _keys(
            record[configuration], set(A_CONSTRUCTION_STATUSES), counts_path
        )
        for status in A_CONSTRUCTION_STATUSES:
            _integer(counts, status, counts_path, maximum=source_tasks)
        if sum(counts.values()) != source_tasks:
            raise RenderError(
                f"{counts_path} does not account for every A construction"
            )
    return record


def _validate_a(value: object, source: dict, *, include_prior: bool = True) -> dict:
    path = "evidence.confirmation_a"
    record = _keys(
        value,
        {
            "sealed",
            "eligible_tasks",
            "comparison_tasks",
            "eligible_families",
            "comparison_families",
            "target_strict_pairs",
            "i_concordance",
            "baselines",
            "orientation",
            "all_strict",
            "oracle_regret",
            "certificate_tightness",
            "timing",
            "frontier_statuses",
            "construction_by_configuration",
            "cegar_fallback_tasks",
        } | ({"all_prior"} if include_prior else set()),
        path,
    )
    if not _boolean(record, "sealed", path):
        raise RenderError("Confirmation A is not sealed")
    eligible_tasks = _integer(record, "eligible_tasks", path, maximum=source["a_tasks"])
    comparison_tasks = _integer(
        record, "comparison_tasks", path, maximum=eligible_tasks
    )
    eligible_families = _integer(
        record,
        "eligible_families",
        path,
        maximum=min(source["a_families"], eligible_tasks),
    )
    comparison_families = _integer(
        record,
        "comparison_families",
        path,
        maximum=min(eligible_families, comparison_tasks),
    )
    _integer(record, "target_strict_pairs", path)
    incidence = _rational(record, "i_concordance", path, minimum=Fraction(0))
    if comparison_tasks > 0 and comparison_families == 0:
        raise RenderError(f"{path} has tasks but no families")
    _require_rational_presence(
        [incidence],
        required=comparison_tasks > 0 and comparison_families > 0,
        path=f"{path}.i_concordance",
    )
    _validate_baselines(
        record["baselines"],
        f"{path}.baselines",
        comparison_tasks=comparison_tasks,
        comparison_families=comparison_families,
    )
    _validate_orientation(record["orientation"], f"{path}.orientation")
    _validate_a_baseline_consistency(record, path)
    if include_prior:
        prior = _validate_a_stratum(record["all_prior"], f"{path}.all_prior")
        if prior["comparison_tasks"] > source["a_prior_tasks"]:
            raise RenderError("Confirmation A all-prior task support exceeds its cohort")
        if prior["comparison_tasks"] > comparison_tasks:
            raise RenderError("Confirmation A all-prior task support exceeds full support")
        if prior["comparison_families"] > source["a_prior_families"]:
            raise RenderError("Confirmation A all-prior family support exceeds its cohort")
        if prior["comparison_families"] > comparison_families:
            raise RenderError("Confirmation A all-prior family support exceeds full support")
        if prior["target_strict_pairs"] > record["target_strict_pairs"]:
            raise RenderError("Confirmation A all-prior pair support exceeds full support")
    all_strict = _validate_all_strict(record["all_strict"], f"{path}.all_strict")
    if all_strict["comparison_tasks"] > comparison_tasks:
        raise RenderError("Confirmation A all-strict support exceeds full support")
    if all_strict["comparison_families"] > comparison_families:
        raise RenderError("Confirmation A all-strict family support exceeds full support")
    oracle = _validate_oracle_regret(
        record["oracle_regret"], f"{path}.oracle_regret"
    )
    if oracle["tasks"] > eligible_tasks:
        raise RenderError("Confirmation A oracle support exceeds eligible support")
    tightness = _validate_tightness(
        record["certificate_tightness"], f"{path}.certificate_tightness"
    )
    if tightness["tasks"] > eligible_tasks:
        raise RenderError("Confirmation A tightness support exceeds eligible support")
    timing = _validate_a_timing(record["timing"], f"{path}.timing")
    if timing["tasks"] > eligible_tasks:
        raise RenderError("Confirmation A timing support exceeds eligible support")
    attrition = _validate_a_attrition(
        record["frontier_statuses"], f"{path}.frontier_statuses", source["a_tasks"]
    )
    if attrition["eligible"] != eligible_tasks:
        raise RenderError("Confirmation A eligible-task counts disagree")
    _validate_a_construction(
        record["construction_by_configuration"],
        f"{path}.construction_by_configuration",
        source["a_tasks"],
    )
    _integer(
        record, "cegar_fallback_tasks", path, maximum=source["a_tasks"]
    )
    return record


def _baseline_gate(baselines: dict) -> bool:
    for name in BASELINES:
        margin = _fraction(baselines[name], "margin")
        bootstrap = _fraction(baselines[name], "bootstrap_lower")
        lofo = _fraction(baselines[name], "lofo_minimum")
        if (
            margin is None
            or bootstrap is None
            or lofo is None
            or margin < Fraction(1, 50)
            or bootstrap <= 0
            or lofo <= 0
        ):
            return False
    return True


def _a_gate(record: dict, *, include_prior: bool = True) -> bool:
    primary_concordance = _fraction(record, "i_concordance")
    primary = (
        record["eligible_tasks"] >= 300
        and record["comparison_tasks"] >= 300
        and record["eligible_families"] >= 25
        and record["comparison_families"] >= 25
        and record["target_strict_pairs"] >= 600
        and primary_concordance is not None
        and primary_concordance >= Fraction(13, 20)
        and _baseline_gate(record["baselines"])
        and _orientation_gate(record["orientation"])
    )
    if not include_prior:
        return primary
    prior = record["all_prior"]
    prior_concordance = _fraction(prior, "i_concordance")
    return (
        primary
        and prior["comparison_tasks"] >= 50
        and prior["comparison_families"] >= 10
        and prior["target_strict_pairs"] >= 100
        and prior_concordance is not None
        and prior_concordance >= Fraction(13, 20)
        and _baseline_gate(prior["baselines"])
        and _orientation_gate(prior["orientation"])
    )


def _validate_outcome_decomposition(
    value: object,
    path: str,
    *,
    tasks: int,
    families: int,
    incidence_coverage: int,
    comparator_coverage: int,
) -> dict:
    record = _keys(
        value,
        {
            "both_solved",
            "incidence_only_solved",
            "comparator_only_solved",
            "neither_solved",
            "common_solved_tasks",
            "common_solved_families",
            "equal_family_normalized_time_improvement",
        },
        path,
    )
    both = _integer(record, "both_solved", path, maximum=tasks)
    incidence_only = _integer(
        record, "incidence_only_solved", path, maximum=tasks
    )
    comparator_only = _integer(
        record, "comparator_only_solved", path, maximum=tasks
    )
    neither = _integer(record, "neither_solved", path, maximum=tasks)
    common_tasks = _integer(record, "common_solved_tasks", path, maximum=tasks)
    common_families = _integer(
        record,
        "common_solved_families",
        path,
        maximum=min(families, common_tasks),
    )
    common_mean = _rational(
        record,
        "equal_family_normalized_time_improvement",
        path,
        minimum=Fraction(-1),
        maximum=Fraction(1),
    )
    if sum((both, incidence_only, comparator_only, neither)) != tasks:
        raise RenderError(f"{path} 2x2 counts do not cover the contrast")
    if incidence_coverage != both + incidence_only:
        raise RenderError(f"{path} incidence coverage disagrees with its 2x2 table")
    if comparator_coverage != both + comparator_only:
        raise RenderError(f"{path} comparator coverage disagrees with its 2x2 table")
    if common_tasks != both:
        raise RenderError(f"{path} common-solved support disagrees with both-solved")
    if (common_tasks == 0) != (common_families == 0):
        raise RenderError(f"{path} common-solved support is inconsistent")
    _require_rational_presence(
        [common_mean],
        required=common_tasks > 0,
        path=f"{path} common-solved equal-family statistic",
    )
    return record


def _validate_contrast(
    value: object, path: str, *, tasks: int, families: int
) -> dict:
    record = _keys(value, set(CONTRAST_FIELDS), path)
    incidence_coverage = _integer(
        record, "coverage_incidence", path, maximum=tasks
    )
    comparator_coverage = _integer(
        record, "coverage_comparator", path, maximum=tasks
    )
    mean = _rational(record, "mean_improvement", path)
    lower = _rational(record, "bootstrap_lower", path)
    upper = _rational(record, "bootstrap_upper", path)
    lofo = _rational(record, "lofo_minimum", path)
    if (tasks == 0) != (families == 0):
        raise RenderError(f"{path} has inconsistent task/family support")
    _require_rational_presence(
        [mean, lower, upper],
        required=tasks > 0,
        path=f"{path} contrast statistics",
    )
    _require_rational_presence(
        [lofo],
        required=tasks > 0 and families >= 2,
        path=f"{path} leave-one-family-out statistic",
    )
    if lower is not None and upper is not None and lower > upper:
        raise RenderError(f"{path} bootstrap endpoints are reversed")
    _validate_outcome_decomposition(
        record["outcome_decomposition"],
        f"{path}.outcome_decomposition",
        tasks=tasks,
        families=families,
        incidence_coverage=incidence_coverage,
        comparator_coverage=comparator_coverage,
    )
    return record


def _contrast_gate(record: dict) -> bool:
    improvement = _fraction(record, "mean_improvement")
    bootstrap = _fraction(record, "bootstrap_lower")
    lofo = _fraction(record, "lofo_minimum")
    return (
        record["coverage_incidence"] >= record["coverage_comparator"]
        and improvement is not None
        and improvement >= Fraction(1, 50)
        and bootstrap is not None
        and bootstrap > 0
        and lofo is not None
        and lofo > 0
    )


def _validate_probe_support(
    value: object, path: str, tasks: int, families: int
) -> dict:
    record = _keys(
        value,
        {
            "complete_tasks",
            "short_probe_tasks",
            "complete_families",
            "short_probe_families",
        },
        path,
    )
    complete = _integer(record, "complete_tasks", path, maximum=tasks)
    short = _integer(record, "short_probe_tasks", path, maximum=tasks)
    complete_families = _integer(
        record, "complete_families", path, maximum=min(complete, families)
    )
    short_families = _integer(
        record, "short_probe_families", path, maximum=min(short, families)
    )
    if complete + short != tasks:
        raise RenderError(f"{path} does not account for every task")
    if (complete == 0) != (complete_families == 0):
        raise RenderError(f"{path} complete support is inconsistent")
    if (short == 0) != (short_families == 0):
        raise RenderError(f"{path} short-probe support is inconsistent")
    return record


def _validate_direct_mechanism(
    value: object, path: str, *, complete_tasks: int, differing_tasks: int
) -> dict:
    record = _keys(
        value,
        {
            "structural_identity_pass",
            "work_counts_match",
            "same_candidate_tasks",
            "same_pattern_different_cap_tasks",
            "different_pattern_tasks",
            "score_higher_tasks",
            "score_tied_tasks",
            "score_lower_tasks",
            "incidence_own_utilization",
            "mj_own_utilization",
            "incidence_binding_tasks",
            "mj_binding_tasks",
            "incidence_under_mj_budget_tasks",
            "mj_under_incidence_budget_tasks",
            "candidate_work",
            "incidence_minus_mj_cpu_seconds",
            "incidence_minus_mj_wall_seconds",
            "incidence_minus_matched_cpu_seconds",
            "incidence_minus_matched_wall_seconds",
        },
        path,
    )
    if not _boolean(record, "structural_identity_pass", path):
        raise RenderError("direct structural identity was not certified")
    if not _boolean(record, "work_counts_match", path):
        raise RenderError("direct registered work counts did not match")
    change_counts = [
        _integer(record, field, path, maximum=complete_tasks)
        for field in (
            "same_candidate_tasks",
            "same_pattern_different_cap_tasks",
            "different_pattern_tasks",
        )
    ]
    if sum(change_counts) != complete_tasks:
        raise RenderError("direct change taxonomy does not cover complete probes")
    score_counts = [
        _integer(record, field, path, maximum=differing_tasks)
        for field in ("score_higher_tasks", "score_tied_tasks", "score_lower_tasks")
    ]
    if sum(score_counts) != differing_tasks:
        raise RenderError("direct score taxonomy does not cover differing winners")
    for field in ("incidence_own_utilization", "mj_own_utilization"):
        _rational(record, field, path, minimum=Fraction(0))
    for field in (
        "incidence_binding_tasks",
        "mj_binding_tasks",
        "incidence_under_mj_budget_tasks",
        "mj_under_incidence_budget_tasks",
    ):
        _integer(record, field, path, maximum=complete_tasks)
    work = _keys(
        record["candidate_work"], set(DIRECT_WORK_FIELDS), f"{path}.candidate_work"
    )
    work_values = [
        _rational(
            work,
            field,
            f"{path}.candidate_work",
            minimum=Fraction(0),
            maximum=None,
        )
        for field in DIRECT_WORK_FIELDS
    ]
    _require_rational_presence(
        work_values,
        required=complete_tasks > 0,
        path=f"{path}.candidate_work",
    )
    paired_values = []
    for field in (
        "incidence_minus_mj_cpu_seconds",
        "incidence_minus_mj_wall_seconds",
        "incidence_minus_matched_cpu_seconds",
        "incidence_minus_matched_wall_seconds",
    ):
        paired_values.append(_rational(
            record,
            field,
            path,
            minimum=Fraction(-3600),
            maximum=Fraction(3600),
        ))
    _require_rational_presence(
        paired_values,
        required=complete_tasks > 0,
        path=f"{path} paired recorded-time summaries",
    )
    return record


def _validate_direct(value: object, source: dict) -> dict:
    path = "evidence.direct_metric_choice"
    record = _keys(
        value,
        {
            "sealed",
            "audit_certified",
            "tasks",
            "families",
            "probe_support",
            "full",
            "differing_winners",
            "secondary_vs_matched",
            "mechanism",
        },
        path,
    )
    if not _boolean(record, "sealed", path):
        raise RenderError("the direct metric-choice input is not sealed")
    _boolean(record, "audit_certified", path)
    tasks = _integer(record, "tasks", path)
    families = _integer(record, "families", path)
    if tasks != source["b_tasks"] or families != source["b_families"]:
        raise RenderError("the direct metric-choice cohort does not match cohort B")
    support = _validate_probe_support(
        record["probe_support"], f"{path}.probe_support", tasks, families
    )
    full = _validate_contrast(
        record["full"], f"{path}.full", tasks=tasks, families=families
    )
    differing_path = f"{path}.differing_winners"
    differing = _keys(
        record["differing_winners"],
        {"tasks", "families", *CONTRAST_FIELDS},
        differing_path,
    )
    differing_tasks = _integer(differing, "tasks", differing_path, maximum=tasks)
    differing_families = _integer(
        differing,
        "families",
        differing_path,
        maximum=min(
            families, support["complete_families"], differing_tasks
        ),
    )
    if differing_tasks > support["complete_tasks"]:
        raise RenderError("direct differing-winner tasks exceed complete probes")
    _validate_contrast(
        {field: differing[field] for field in CONTRAST_FIELDS},
        differing_path,
        tasks=differing_tasks,
        families=differing_families,
    )
    differing_incidence_coverage = differing["coverage_incidence"]
    differing_comparator_coverage = differing["coverage_comparator"]
    if differing_incidence_coverage > full["coverage_incidence"]:
        raise RenderError(
            "direct differing-winner incidence coverage exceeds full-cohort coverage"
        )
    if differing_comparator_coverage > full["coverage_comparator"]:
        raise RenderError(
            "direct differing-winner comparator coverage exceeds full-cohort coverage"
        )
    _validate_contrast(
        record["secondary_vs_matched"],
        f"{path}.secondary_vs_matched",
        tasks=tasks,
        families=families,
    )
    if record["secondary_vs_matched"]["coverage_incidence"] != full[
        "coverage_incidence"
    ]:
        raise RenderError("direct incidence coverage differs across full contrasts")
    mechanism = _validate_direct_mechanism(
        record["mechanism"],
        f"{path}.mechanism",
        complete_tasks=support["complete_tasks"],
        differing_tasks=differing_tasks,
    )
    if (
        mechanism["same_pattern_different_cap_tasks"]
        + mechanism["different_pattern_tasks"]
        != differing_tasks
    ):
        raise RenderError(
            "direct differing-winner support disagrees with change taxonomy"
        )
    return record


def _direct_gate(record: dict) -> bool:
    differing = record["differing_winners"]
    return (
        record["audit_certified"]
        and _contrast_gate(record["full"])
        and differing["tasks"] >= 50
        and differing["families"] >= 10
        and _contrast_gate(differing)
    )


def _validate_b_configurations(
    value: object, path: str, tasks: int, families: int
) -> dict:
    record = _keys(value, set(B_CONFIGURATIONS), path)
    for configuration in B_CONFIGURATIONS:
        result_path = f"{path}.{configuration}"
        result = _keys(
            record[configuration],
            {
                "coverage",
                "par2_sum_seconds",
                "par2_mean_seconds",
                "equal_family_mean_par2_seconds",
            },
            result_path,
        )
        coverage = _integer(result, "coverage", result_path, maximum=tasks)
        total = _rational(
            result,
            "par2_sum_seconds",
            result_path,
            minimum=Fraction(0),
            maximum=Fraction(tasks * 3600),
        )
        mean = _rational(
            result,
            "par2_mean_seconds",
            result_path,
            minimum=Fraction(0),
            maximum=Fraction(3600),
        )
        family_mean = _rational(
            result,
            "equal_family_mean_par2_seconds",
            result_path,
            minimum=Fraction(0),
            maximum=Fraction(3600),
        )
        _require_rational_presence(
            [total, mean, family_mean],
            required=tasks > 0 and families > 0,
            path=f"{result_path} PAR2 summaries",
        )
        if total is not None:
            lower = Fraction((tasks - coverage) * 3600)
            upper = lower + Fraction(coverage * 1800)
            if not lower <= total <= upper:
                raise RenderError(
                    f"{result_path} PAR2 sum is incompatible with coverage"
                )
        if total is not None and mean != total / tasks:
            raise RenderError(f"{result_path} mean PAR2 is not sum/tasks")
    return record


def _validate_b_mechanism(
    value: object, path: str, tasks: int, families: int
) -> dict:
    record = _keys(
        value,
        {"tasks", "families", "claim_authorized", "versus_matched"},
        path,
    )
    mechanism_tasks = _integer(record, "tasks", path, maximum=tasks)
    mechanism_families = _integer(
        record, "families", path, maximum=min(families, mechanism_tasks)
    )
    _boolean(record, "claim_authorized", path)
    _validate_contrast(
        record["versus_matched"],
        f"{path}.versus_matched",
        tasks=mechanism_tasks,
        families=mechanism_families,
    )
    return record


def _validate_b_alternatives(
    value: object, path: str, *, tasks: int, families: int
) -> dict:
    record = _keys(value, set(B_ALTERNATIVES), path)
    for configuration in B_ALTERNATIVES:
        _validate_contrast(
            record[configuration],
            f"{path}.{configuration}",
            tasks=tasks,
            families=families,
        )
    return record


def _validate_b_overhead(
    value: object, path: str, *, tasks: int, complete_pairs: int
) -> dict:
    record = _keys(value, set(B_OVERHEAD_FIELDS), path)
    probe_values = []
    selection_values = []
    for field in B_OVERHEAD_FIELDS:
        normalized = _rational(
            record, field, path, minimum=Fraction(0), maximum=None
        )
        (selection_values if "selection" in field else probe_values).append(
            normalized
        )
    _require_rational_presence(
        probe_values, required=tasks > 0, path=f"{path} probe summaries"
    )
    _require_rational_presence(
        selection_values,
        required=complete_pairs > 0,
        path=f"{path} selection summaries",
    )
    return record


def _validate_b(value: object, source: dict) -> dict:
    path = "evidence.confirmation_b"
    record = _keys(
        value,
        {
            "sealed",
            "selector_provenance_pass",
            "tasks",
            "families",
            "complete_pairs",
            "short_probe_pairs",
            "failed_pairs",
            "selected_difference_tasks",
            "reference_identity_pass",
            "versus_reference",
            "versus_matched",
            "alternatives",
            "configurations",
            "mechanism",
            "overhead",
        },
        path,
    )
    if not _boolean(record, "sealed", path):
        raise RenderError("Confirmation B is not sealed")
    provenance_pass = _boolean(record, "selector_provenance_pass", path)
    tasks = _integer(record, "tasks", path)
    families = _integer(record, "families", path)
    if tasks != source["b_tasks"] or families != source["b_families"]:
        raise RenderError("the Confirmation B cohort does not match its source audit")
    complete_pairs = _integer(record, "complete_pairs", path, maximum=tasks)
    short_pairs = _integer(record, "short_probe_pairs", path, maximum=tasks)
    failed_pairs = _integer(record, "failed_pairs", path, maximum=tasks)
    if complete_pairs + short_pairs + failed_pairs != tasks:
        raise RenderError("Confirmation B selector pairs do not cover the cohort")
    if provenance_pass is not (failed_pairs == 0):
        raise RenderError("Confirmation B selector provenance is inconsistent")
    selected_difference_tasks = _integer(
        record, "selected_difference_tasks", path, maximum=complete_pairs
    )
    _boolean(record, "reference_identity_pass", path)
    reference = _validate_contrast(
        record["versus_reference"],
        f"{path}.versus_reference",
        tasks=tasks,
        families=families,
    )
    matched = _validate_contrast(
        record["versus_matched"],
        f"{path}.versus_matched",
        tasks=tasks,
        families=families,
    )
    if reference["coverage_incidence"] != matched["coverage_incidence"]:
        raise RenderError(
            "Confirmation B guided coverage differs across same-cohort contrasts"
        )
    configurations = _validate_b_configurations(
        record["configurations"], f"{path}.configurations", tasks, families
    )
    alternatives = _validate_b_alternatives(
        record["alternatives"],
        f"{path}.alternatives",
        tasks=tasks,
        families=families,
    )
    expected_coverages = {
        "incidence_guided": reference["coverage_incidence"],
        "cap_aware_k32": reference["coverage_comparator"],
        "matched_work": matched["coverage_comparator"],
    }
    if any(
        configurations[name]["coverage"] != coverage
        for name, coverage in expected_coverages.items()
    ):
        raise RenderError("Confirmation B configuration coverage is inconsistent")
    for configuration in B_ALTERNATIVES:
        alternative = alternatives[configuration]
        if (
            alternative["coverage_incidence"]
            != reference["coverage_incidence"]
            or alternative["coverage_comparator"]
            != configurations[configuration]["coverage"]
        ):
            raise RenderError(
                "Confirmation B alternative coverage is inconsistent"
            )
    mechanism = _validate_b_mechanism(
        record["mechanism"], f"{path}.mechanism", tasks, families
    )
    if mechanism["tasks"] != selected_difference_tasks:
        raise RenderError("Confirmation B mechanism support is inconsistent")
    mechanism_authorized = (
        provenance_pass
        and mechanism["tasks"] >= 50
        and mechanism["families"] >= 10
        and _contrast_gate(mechanism["versus_matched"])
    )
    if mechanism["claim_authorized"] is not mechanism_authorized:
        raise RenderError(
            "Confirmation B mechanism authorization is inconsistent"
        )
    _validate_b_overhead(
        record["overhead"],
        f"{path}.overhead",
        tasks=tasks,
        complete_pairs=complete_pairs,
    )
    return record


def _b_gate(record: dict) -> bool:
    return record["selector_provenance_pass"] and record[
        "reference_identity_pass"
    ] and _contrast_gate(
        record["versus_reference"]
    ) and _contrast_gate(
        record["versus_matched"]
    )


def _validate_campaign_hardware(
    value: object, path: str, expected_cells: int
) -> dict:
    record = _keys(
        value,
        {"receipt_sealed", "cells", "processor_models", "architectures"},
        path,
    )
    if not _boolean(record, "receipt_sealed", path):
        raise RenderError(f"{path} receipt is not sealed")
    cells = _integer(record, "cells", path)
    models = _integer(record, "processor_models", path, maximum=cells)
    architectures = _integer(record, "architectures", path, maximum=cells)
    if cells != expected_cells or models < 1 or architectures < 1:
        raise RenderError(f"{path} hardware support changed")
    return record


def _validate_hardware(value: object, *, downstream_required: bool) -> dict:
    path = "evidence.hardware"
    record = _keys(value, {"a", "direct", "b"}, path)
    _validate_campaign_hardware(record["a"], f"{path}.a", 2600)
    if downstream_required:
        _validate_campaign_hardware(record["direct"], f"{path}.direct", 900)
        _validate_campaign_hardware(record["b"], f"{path}.b", 2700)
    elif record["direct"] is not None or record["b"] is not None:
        raise RenderError("failing A requires exact downstream hardware absence")
    return record


def classify(evidence: object) -> Outcome:
    """Validate normalized evidence and recompute its unique terminal branch."""
    if type(evidence) is dict and evidence.get("design") == "within-family-v1":
        import render_within_family_results as Within
        return Within.classify(evidence)
    _reject_artifact_text(evidence)
    if type(evidence) is not dict:
        raise RenderError("evidence must be a dict")
    common = {"source_audit", "confirmation_a", "hardware"}
    downstream = {"direct_metric_choice", "confirmation_b"}
    unknown = set(evidence) - common - downstream
    missing = common - set(evidence)
    if missing or unknown:
        raise RenderError(
            f"evidence schema mismatch; missing={sorted(missing)}, "
            f"extra={sorted(unknown, key=repr)}"
        )

    source = _validate_source_audit(evidence["source_audit"])
    confirmation_a = _validate_a(evidence["confirmation_a"], source)
    a_pass = _a_gate(confirmation_a)
    expected = common | downstream if a_pass else common
    _keys(evidence, expected, "evidence")
    _validate_hardware(evidence["hardware"], downstream_required=a_pass)

    if not a_pass:
        return Outcome(OutcomeBranch.A_FAIL, False, None, None)

    direct = _validate_direct(evidence["direct_metric_choice"], source)
    confirmation_b = _validate_b(evidence["confirmation_b"], source)
    direct_pass = _direct_gate(direct)
    b_pass = _b_gate(confirmation_b)
    branch = {
        (False, False): OutcomeBranch.A_PASS_DIRECT_FAIL_B_FAIL,
        (False, True): OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS,
        (True, False): OutcomeBranch.A_PASS_DIRECT_PASS_B_FAIL,
        (True, True): OutcomeBranch.A_PASS_DIRECT_PASS_B_PASS,
    }[(direct_pass, b_pass)]
    return Outcome(branch, True, direct_pass, b_pass)


ABSTRACT_TEXT = {
    OutcomeBranch.A_FAIL: (
        "Confirmation A did not pass its prespecified fixed-frontier gate; "
        "the downstream selector experiments were therefore not authorized."
    ),
    OutcomeBranch.A_PASS_DIRECT_FAIL_B_FAIL: (
        "Confirmation A passed its prespecified fixed-frontier gate, but neither "
        "the direct metric-choice gate nor the broader selector gate passed."
    ),
    OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS: (
        "Confirmation A and the broader selector comparison passed their "
        "prespecified gates, while the direct metric-choice comparison did not."
    ),
    OutcomeBranch.A_PASS_DIRECT_PASS_B_FAIL: (
        "Confirmation A and the direct metric-choice comparison passed their "
        "prespecified gates, while the broader selector comparison did not."
    ),
    OutcomeBranch.A_PASS_DIRECT_PASS_B_PASS: (
        "Confirmation A, the direct metric-choice comparison and the broader "
        "selector comparison passed their prespecified gates."
    ),
}

CONCLUSION_TEXT = {
    OutcomeBranch.A_FAIL: (
        "The confirmatory evidence does not support the ordinal predictor claim; "
        "the selector claims remain untested."
    ),
    OutcomeBranch.A_PASS_DIRECT_FAIL_B_FAIL: (
        "The evidence supports terminal incidence as an ordinal fixed-frontier "
        "predictor, but not either downstream selector claim."
    ),
    OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS: (
        "The evidence supports the ordinal predictor and the broader frozen "
        "selector design, but not a benefit from substituting incidence for the "
        "developmental metric within the common candidate pool."
    ),
    OutcomeBranch.A_PASS_DIRECT_PASS_B_FAIL: (
        "The evidence supports the ordinal predictor and the direct metric "
        "substitution, but not the broader frozen selector design."
    ),
    OutcomeBranch.A_PASS_DIRECT_PASS_B_PASS: (
        "The evidence supports the ordinal predictor, the direct metric "
        "substitution and the broader frozen selector design within their stated scope."
    ),
}


def _fixed_decimal(value: Fraction, digits: int) -> str:
    sign = "-" if value < 0 else ""
    numerator = abs(value.numerator) * (10 ** digits)
    quotient, remainder = divmod(numerator, value.denominator)
    if 2 * remainder >= value.denominator:
        quotient += 1
    scale = 10 ** digits
    whole, fractional = divmod(quotient, scale)
    return f"{sign}{whole}.{fractional:0{digits}d}"


def _fmt(
    value: Fraction | None,
    *,
    threshold: Fraction | None = None,
    minimum_digits: int = 4,
) -> str:
    if value is None:
        return "not estimable"
    actual_side = None
    if threshold is not None:
        actual_side = (value > threshold) - (value < threshold)
    for digits in range(minimum_digits, 19):
        rendered = _fixed_decimal(value, digits)
        if threshold is None:
            return rendered
        displayed = Fraction(rendered)
        displayed_side = (displayed > threshold) - (displayed < threshold)
        if actual_side == displayed_side:
            return rendered
    relation = {-1: "<", 0: "=", 1: ">"}[actual_side]
    exact_boundary = f"{threshold.numerator}/{threshold.denominator}"
    return f"{_fixed_decimal(value, 18)}\\;({relation}{exact_boundary})"


def _table_fmt(
    value: Fraction | None, *, threshold: Fraction | None = None
) -> str:
    return "--" if value is None else _fmt(value, threshold=threshold)


def _baseline_triplets(baselines: dict) -> str:
    values = []
    for name in BASELINES:
        result = baselines[name]
        values.append(
            "({}/[{},{}]/{})".format(
                _fmt(_fraction(result, "margin"), threshold=Fraction(1, 50)),
                _fmt(_fraction(result, "bootstrap_lower"), threshold=Fraction(0)),
                _fmt(_fraction(result, "bootstrap_upper")),
                _fmt(_fraction(result, "lofo_minimum"), threshold=Fraction(0)),
            )
        )
    return ", ".join(values)


def _title(outcome: Outcome) -> str:
    if not outcome.a_pass:
        return TITLE_CERTIFICATES
    if outcome.direct_pass:
        return TITLE_SELECTION
    return TITLE_PREDICTOR


def _a_predictor_rows(evidence: dict) -> str:
    a = evidence["confirmation_a"]
    oracle = a["oracle_regret"]["predictors"]
    tightness = a["certificate_tightness"]["predictors"]
    rows = []
    for predictor, label in zip(
        ORDERING_PREDICTORS, ORDERING_PREDICTOR_TEX_LABELS
    ):
        if predictor == "incidence":
            concordance = _fraction(a, "i_concordance")
            margin = lower = upper = lofo = None
        else:
            result = a["baselines"][predictor]
            concordance = _fraction(result, "concordance")
            margin = _fraction(result, "margin")
            lower = _fraction(result, "bootstrap_lower")
            upper = _fraction(result, "bootstrap_upper")
            lofo = _fraction(result, "lofo_minimum")
        predictor_tightness = tightness.get(predictor)
        rows.append(
            "{} & {} & {} & {} & {} & {} & {} & {} \\\\".format(
                label,
                _table_fmt(concordance, threshold=Fraction(13, 20)),
                _table_fmt(margin, threshold=Fraction(1, 50)),
                _table_fmt(lower, threshold=Fraction(0)),
                _table_fmt(upper),
                _table_fmt(lofo, threshold=Fraction(0)),
                _table_fmt(
                    _fraction(oracle[predictor], "equal_family_regret")
                ),
                _table_fmt(
                    None
                    if predictor_tightness is None
                    else _fraction(predictor_tightness, "equal_family")
                ),
            )
        )
    return " ".join(rows)


def _a_diagnostic_rows(evidence: dict) -> str:
    a = evidence["confirmation_a"]
    strict = a["all_strict"]["predictors"]
    oracle = a["oracle_regret"]["predictors"]
    tightness = a["certificate_tightness"]["predictors"]
    rows = []
    for predictor, label in zip(
        ORDERING_PREDICTORS, ORDERING_PREDICTOR_TEX_LABELS
    ):
        certificate = tightness.get(predictor)
        tightness_values = (
            (None, None, None, None)
            if certificate is None
            else tuple(
                _fraction(certificate, field)
                for field in ("equal_family", "q25", "q50", "q75")
            )
        )
        rows.append(
            "{} & {} & {} & {} & {} & {} & {} & {} \\\\".format(
                label,
                _table_fmt(_fraction(strict, predictor)),
                _table_fmt(_fraction(oracle[predictor], "equal_family_regret")),
                _table_fmt(_fraction(oracle[predictor], "tie_rate")),
                *(_table_fmt(value) for value in tightness_values),
            )
        )
    return " ".join(rows)


def _a_construction_rows(evidence: dict) -> str:
    construction = evidence["confirmation_a"]["construction_by_configuration"]
    return " ".join(
        "{} & {} & {} & {} \\\\".format(
            label,
            construction[name]["completed"],
            construction[name]["failed"],
            construction[name]["absent"],
        )
        for name, label in zip(
            A_CONSTRUCTION_CONFIGURATIONS,
            ("BDD-prefix", "goal-prefix", "goal-fill", "CEGAR"),
        )
    )


def _a_frontier_rows(evidence: dict) -> str:
    statuses = evidence["confirmation_a"]["frontier_statuses"]
    return " ".join(
        f"{status.replace('_', ' ')} & {statuses[status]} \\\\"
        for status in A_FRONTIER_STATUSES
    )


def _a_timing_rows(evidence: dict) -> str:
    timing = evidence["confirmation_a"]["timing"]
    rows = (
        ("measured cells", str(timing["cells"])),
        ("measured tasks", str(timing["tasks"])),
        (
            "tasks with positive exact-partition time",
            str(timing["tasks_with_positive_partition_time"]),
        ),
        (
            "families with positive exact-partition time",
            str(timing["families_with_positive_partition_time"]),
        ),
        (
            "pooled masked seconds",
            _table_fmt(_fraction(timing, "pooled_masked_seconds")),
        ),
        (
            "pooled exact-partition seconds",
            _table_fmt(_fraction(timing, "pooled_partition_audit_seconds")),
        ),
        (
            "pooled masked/exact-partition ratio",
            _table_fmt(_fraction(timing, "pooled_masked_over_partition_ratio")),
        ),
        (
            "equal-family mean task ratio",
            _table_fmt(_fraction(timing, "equal_family_mean_of_task_ratios")),
        ),
    )
    return " ".join(f"{label} & {value} \\\\" for label, value in rows)


def _a_text(evidence: dict, outcome: Outcome) -> str:
    a = evidence["confirmation_a"]
    prior = a["all_prior"]
    decision = "passed" if outcome.a_pass else "failed"
    return (
        f"Confirmation A used {a['comparison_tasks']} comparison tasks from "
        f"{a['comparison_families']} families and {a['target_strict_pairs']} "
        f"target-strict pairs. Terminal incidence had macro concordance "
        f"{_fmt(_fraction(a, 'i_concordance'), threshold=Fraction(13, 20))}. For "
        f"{', '.join(BASELINE_TEX_LABELS)}, respectively, the "
        f"margin/bootstrap-interval/leave-one-family-out-minimum triples were "
        f"{_baseline_triplets(a['baselines'])}. The all-prior-"
        f"unrepresented stratum used {prior['comparison_tasks']} comparison tasks "
        f"from {prior['comparison_families']} families and "
        f"{prior['target_strict_pairs']} target-strict pairs, with incidence "
        f"concordance {_fmt(_fraction(prior, 'i_concordance'), threshold=Fraction(13, 20))}; "
        f"its corresponding "
        f"triples were {_baseline_triplets(prior['baselines'])}. The complete gate "
        f"{decision}. The all-strict sensitivity retained "
        f"{a['all_strict']['pairs']} pairs from "
        f"{a['all_strict']['comparison_tasks']} tasks. Choosing by incidence had "
        f"equal-family exact-E regret "
        f"{_fmt(_fraction(a['oracle_regret']['predictors']['incidence'], 'equal_family_regret'))}. "
        f"CEGAR used its registered goal-fill fallback on "
        f"{a['cegar_fallback_tasks']} tasks. "
        f"The timing panel covered {a['timing']['cells']} cells from "
        f"{a['timing']['tasks']} tasks; its pooled and equal-family "
        f"masked-to-exact-partition ratios were "
        f"{_fmt(_fraction(a['timing'], 'pooled_masked_over_partition_ratio'))} "
        f"and {_fmt(_fraction(a['timing'], 'equal_family_mean_of_task_ratios'))}."
    )


def _direct_text(evidence: dict, outcome: Outcome) -> str:
    if not outcome.a_pass:
        return "The direct metric-choice campaign was not authorized."
    direct = evidence["direct_metric_choice"]
    full = direct["full"]
    differing = direct["differing_winners"]
    secondary = direct["secondary_vs_matched"]
    support = direct["probe_support"]
    mechanism = direct["mechanism"]
    decision = "passed" if outcome.direct_pass else "failed"
    return (
        f"The sealed direct campaign had {support['complete_tasks']} complete and "
        f"{support['short_probe_tasks']} certified short probes. Its full comparison "
        f"covered {full['coverage_incidence']} tasks "
        f"with incidence and {full['coverage_comparator']} with the developmental "
        f"metric. Its equal-family normalized improvement, bootstrap interval "
        f"and leave-one-family-out minimum were "
        f"{_fmt(_fraction(full, 'mean_improvement'), threshold=Fraction(1, 50))}, "
        f"[{_fmt(_fraction(full, 'bootstrap_lower'), threshold=Fraction(0))}, "
        f"{_fmt(_fraction(full, 'bootstrap_upper'))}] and "
        f"{_fmt(_fraction(full, 'lofo_minimum'), threshold=Fraction(0))}. "
        f"The differing-winner subset contained "
        f"{differing['tasks']} tasks from {differing['families']} families; its "
        f"incidence/developmental coverages were "
        f"{differing['coverage_incidence']}/{differing['coverage_comparator']}, and its "
        f"improvement, bootstrap interval and leave-one-family-out minimum were "
        f"{_fmt(_fraction(differing, 'mean_improvement'), threshold=Fraction(1, 50))}, "
        f"[{_fmt(_fraction(differing, 'bootstrap_lower'), threshold=Fraction(0))}, "
        f"{_fmt(_fraction(differing, 'bootstrap_upper'))}] and "
        f"{_fmt(_fraction(differing, 'lofo_minimum'), threshold=Fraction(0))}. "
        f"Against matched $K=32$, the full-cohort incidence/matched coverages, "
        f"improvement, bootstrap interval and leave-one-family-out minimum were "
        f"{secondary['coverage_incidence']}/{secondary['coverage_comparator']}, "
        f"{_fmt(_fraction(secondary, 'mean_improvement'))}, "
        f"[{_fmt(_fraction(secondary, 'bootstrap_lower'))}, "
        f"{_fmt(_fraction(secondary, 'bootstrap_upper'))}] and "
        f"{_fmt(_fraction(secondary, 'lofo_minimum'))}. Incidence and $mJ$ "
        f"selected the same candidate on {mechanism['same_candidate_tasks']} "
        f"complete probes, different caps of one pattern on "
        f"{mechanism['same_pattern_different_cap_tasks']}, and different patterns on "
        f"{mechanism['different_pattern_tasks']}; the equal-family recorded wall-time "
        f"difference was "
        f"{_fmt(_fraction(mechanism, 'incidence_minus_mj_wall_seconds'))} seconds. "
        f"The direct gate {decision}."
    )


def _b_configuration_rows(evidence: dict, outcome: Outcome) -> str:
    if not outcome.a_pass:
        return "-- & -- & -- & -- \\\\"
    configurations = evidence["confirmation_b"]["configurations"]
    return " ".join(
        "{} & {} & {} & {} \\\\".format(
            label,
            configurations[name]["coverage"],
            _table_fmt(_fraction(configurations[name], "par2_mean_seconds")),
            _table_fmt(
                _fraction(configurations[name], "equal_family_mean_par2_seconds")
            ),
        )
        for name, label in zip(B_CONFIGURATIONS, B_CONFIGURATION_TEX_LABELS)
    )


def _outcome_decomposition_row(label: str, contrast: dict) -> str:
    decomposition = contrast["outcome_decomposition"]
    return "{} & {} & {} & {} & {} & {} & {} & {} \\\\".format(
        label,
        decomposition["both_solved"],
        decomposition["incidence_only_solved"],
        decomposition["comparator_only_solved"],
        decomposition["neither_solved"],
        decomposition["common_solved_tasks"],
        decomposition["common_solved_families"],
        _table_fmt(
            _fraction(decomposition, "equal_family_normalized_time_improvement")
        ),
    )


def _direct_outcome_rows(evidence: dict, outcome: Outcome) -> str:
    if not outcome.a_pass:
        return "not authorized & -- & -- & -- & -- & -- & -- & -- \\\\"
    direct = evidence["direct_metric_choice"]
    return " ".join((
        _outcome_decomposition_row("full: incidence vs. $mJ$", direct["full"]),
        _outcome_decomposition_row(
            "differing winners: incidence vs. $mJ$",
            direct["differing_winners"],
        ),
        _outcome_decomposition_row(
            "full: incidence vs. matched", direct["secondary_vs_matched"]
        ),
    ))


def _direct_mechanism_rows(evidence: dict, outcome: Outcome) -> str:
    if not outcome.a_pass:
        return "not authorized & -- \\\\"
    mechanism = evidence["direct_metric_choice"]["mechanism"]
    rows = [
        ("same candidate", str(mechanism["same_candidate_tasks"])),
        (
            "same pattern, different cap",
            str(mechanism["same_pattern_different_cap_tasks"]),
        ),
        ("different pattern", str(mechanism["different_pattern_tasks"])),
        ("score higher/tied/lower", "{}/{}/{}".format(
            mechanism["score_higher_tasks"],
            mechanism["score_tied_tasks"],
            mechanism["score_lower_tasks"],
        )),
        ("incidence own-budget utilization", _table_fmt(
            _fraction(mechanism, "incidence_own_utilization")
        )),
        ("$mJ$ own-budget utilization", _table_fmt(
            _fraction(mechanism, "mj_own_utilization")
        )),
        ("incidence/$mJ$ binding tasks", "{}/{}".format(
            mechanism["incidence_binding_tasks"], mechanism["mj_binding_tasks"]
        )),
        ("incidence/$mJ$ cross-feasible tasks", "{}/{}".format(
            mechanism["incidence_under_mj_budget_tasks"],
            mechanism["mj_under_incidence_budget_tasks"],
        )),
        ("incidence minus $mJ$ CPU/wall seconds", "{}/{}".format(
            _table_fmt(_fraction(mechanism, "incidence_minus_mj_cpu_seconds")),
            _table_fmt(_fraction(mechanism, "incidence_minus_mj_wall_seconds")),
        )),
        ("incidence minus matched CPU/wall seconds", "{}/{}".format(
            _table_fmt(
                _fraction(mechanism, "incidence_minus_matched_cpu_seconds")
            ),
            _table_fmt(
                _fraction(mechanism, "incidence_minus_matched_wall_seconds")
            ),
        )),
    ]
    rows.extend(
        (
            field.replace("_", " "),
            _table_fmt(_fraction(mechanism["candidate_work"], field)),
        )
        for field in DIRECT_WORK_FIELDS
    )
    return " ".join(f"{label} & {value} \\\\" for label, value in rows)


def _b_overhead_rows(evidence: dict, outcome: Outcome) -> str:
    if not outcome.a_pass:
        return "not authorized & -- \\\\"
    overhead = evidence["confirmation_b"]["overhead"]
    return " ".join(
        "{} & {} \\\\".format(
            field.replace("_", " "), _table_fmt(_fraction(overhead, field))
        )
        for field in B_OVERHEAD_FIELDS
    )


def _b_alternative_rows(evidence: dict, outcome: Outcome) -> str:
    if not outcome.a_pass:
        return "not authorized & -- & -- & -- & -- & -- & -- \\\\"
    alternatives = evidence["confirmation_b"]["alternatives"]
    return " ".join(
        "{} & {}/{} & {} & [{},{}] & {} & {} \\\\".format(
            label,
            alternatives[name]["coverage_incidence"],
            alternatives[name]["coverage_comparator"],
            _table_fmt(_fraction(alternatives[name], "mean_improvement")),
            _table_fmt(_fraction(alternatives[name], "bootstrap_lower")),
            _table_fmt(_fraction(alternatives[name], "bootstrap_upper")),
            _table_fmt(_fraction(alternatives[name], "lofo_minimum")),
            _table_fmt(_fraction(
                alternatives[name]["outcome_decomposition"],
                "equal_family_normalized_time_improvement",
            )),
        )
        for name, label in zip(B_ALTERNATIVES, B_CONFIGURATION_TEX_LABELS[:6])
    )


def _b_outcome_rows(evidence: dict, outcome: Outcome) -> str:
    if not outcome.a_pass:
        return "not authorized & -- & -- & -- & -- & -- & -- & -- \\\\"
    confirmation_b = evidence["confirmation_b"]
    rows = [
        _outcome_decomposition_row(
            "guided vs. cap-aware", confirmation_b["versus_reference"]
        ),
        _outcome_decomposition_row(
            "guided vs. matched", confirmation_b["versus_matched"]
        ),
        _outcome_decomposition_row(
            "different selections vs. matched",
            confirmation_b["mechanism"]["versus_matched"],
        ),
    ]
    rows.extend(
        _outcome_decomposition_row(
            f"guided vs. {label}", confirmation_b["alternatives"][name]
        )
        for name, label in zip(B_ALTERNATIVES, B_CONFIGURATION_TEX_LABELS[:6])
    )
    return " ".join(rows)


def _source_exclusion_rows(source: dict) -> str:
    return " ".join(
        "{} & {} \\\\".format(
            category.replace("_", " "),
            source["reason_incidence_counts"][category],
        )
        for category in SOURCE_EXCLUSION_CATEGORIES
    )


def _b_text(evidence: dict, outcome: Outcome) -> str:
    if not outcome.a_pass:
        return "Confirmation B was not authorized."
    confirmation_b = evidence["confirmation_b"]
    reference = confirmation_b["versus_reference"]
    matched = confirmation_b["versus_matched"]
    mechanism = confirmation_b["mechanism"]
    mechanism_contrast = mechanism["versus_matched"]
    decision = "passed" if outcome.b_pass else "failed"
    mechanism_decision = "authorized" if mechanism["claim_authorized"] else "not authorized"
    return (
        f"Confirmation B used {confirmation_b['tasks']} tasks from "
        f"{confirmation_b['families']} families, with "
        f"{confirmation_b['complete_pairs']} complete and "
        f"{confirmation_b['short_probe_pairs']} certified short selector pairs; "
        f"{confirmation_b['failed_pairs']} pairs failed provenance certification. "
        f"Incidence-guided coverage was {reference['coverage_incidence']}, versus "
        f"{reference['coverage_comparator']} for the cap-aware reference and "
        f"{matched['coverage_comparator']} for matched work. Equal-family normalized "
        f"improvements were "
        f"{_fmt(_fraction(reference, 'mean_improvement'), threshold=Fraction(1, 50))} "
        f"(bootstrap [{_fmt(_fraction(reference, 'bootstrap_lower'), threshold=Fraction(0))}, "
        f"{_fmt(_fraction(reference, 'bootstrap_upper'))}]) and "
        f"{_fmt(_fraction(matched, 'mean_improvement'), threshold=Fraction(1, 50))} "
        f"(bootstrap [{_fmt(_fraction(matched, 'bootstrap_lower'), threshold=Fraction(0))}, "
        f"{_fmt(_fraction(matched, 'bootstrap_upper'))}]), respectively; their "
        f"leave-one-family-out minima were "
        f"{_fmt(_fraction(reference, 'lofo_minimum'), threshold=Fraction(0))} and "
        f"{_fmt(_fraction(matched, 'lofo_minimum'), threshold=Fraction(0))}. "
        f"The conditional mechanism subset contained {mechanism['tasks']} tasks from "
        f"{mechanism['families']} families. Its guided/matched coverages, equal-family "
        f"normalized improvement, bootstrap interval and leave-one-family-out minimum "
        f"were {mechanism_contrast['coverage_incidence']}/"
        f"{mechanism_contrast['coverage_comparator']}, "
        f"{_fmt(_fraction(mechanism_contrast, 'mean_improvement'), threshold=Fraction(1, 50))}, "
        f"[{_fmt(_fraction(mechanism_contrast, 'bootstrap_lower'), threshold=Fraction(0))}, "
        f"{_fmt(_fraction(mechanism_contrast, 'bootstrap_upper'))}] and "
        f"{_fmt(_fraction(mechanism_contrast, 'lofo_minimum'), threshold=Fraction(0))}; the conditional "
        f"claim was {mechanism_decision}. The configuration table reports exact "
        f"task-mean PAR2 (sealed PAR2 sum divided by {confirmation_b['tasks']}) and "
        f"equal-family mean PAR2. The complete "
        f"gate {decision}."
    )


def _source_text(source: dict) -> str:
    return (
        f"The fresh source audit attempted all {source['inventory_candidates']} "
        f"candidates from {source['inventory_families']} normalized families: "
        f"{source['translated_successfully']} translated successfully, "
        f"{source['translation_status_counts']['input_rejected']} were rejected "
        f"at translation and {source['indeterminate_tasks']} reached a resource "
        f"limit ({source['resource_exclusion_counts']['time']} time and "
        f"{source['resource_exclusion_counts']['memory']} memory exclusions). "
        f"These resource exclusions have indeterminate source support. Of the "
        f"classified tasks, {source['supported_tasks']} were supported and "
        f"{source['unsupported_tasks']} unsupported. Exclusion rows count reason "
        f"incidences; a task can have several reasons. All "
        f"{source['logical_shards']} shards were computed afresh under the same "
        f"1,800-second CPU and 24,576-MiB limits; no prior campaign shard was reused. "
        f"The audit authorized {source['a_tasks']} Confirmation A tasks from "
        f"{source['a_families']} families and {source['b_tasks']} Confirmation B "
        f"tasks from {source['b_families']} families; "
        f"{source['unassigned_supported_tasks']} supported tasks were unassigned. "
        f"The all-prior-unrepresented strata contained {source['a_prior_tasks']} "
        f"and {source['b_prior_tasks']} tasks, respectively. The cohorts were "
        f"source-disjoint. Resource-excluded tasks are outside both cohorts, so "
        f"the results do not cover tasks whose translation exceeds these limits."
    )


def _hardware_text(evidence: dict, outcome: Outcome) -> str:
    hardware = evidence["hardware"]
    a = hardware["a"]
    if outcome.a_pass:
        direct = hardware["direct"]
        b = hardware["b"]
        return (
            f"Sealed hardware receipts cover {a['cells']} A cells, "
            f"{direct['cells']} direct metric-choice cells and {b['cells']} B cells; "
            f"they contain {a['processor_models']}, {direct['processor_models']} and "
            f"{b['processor_models']} processor-model identities and "
            f"{a['architectures']}, {direct['architectures']} and "
            f"{b['architectures']} architecture identities, respectively."
        )
    return (
        f"The sealed Confirmation A hardware receipt covers {a['cells']} cells "
        f"with {a['processor_models']} processor-model and {a['architectures']} "
        f"architecture identities; exact absence of "
        f"downstream hardware receipts was verified."
    )


def render(evidence: object) -> str:
    """Return the fixed prose and table-row TeX interface."""
    if type(evidence) is dict and evidence.get("design") == "within-family-v1":
        import render_within_family_results as Within
        return Within.render(evidence)
    outcome = classify(evidence)
    macros = (
        ("TIOutcomeTitle", _title(outcome)),
        ("TIOutcomeAbstract", ABSTRACT_TEXT[outcome.branch]),
        ("TIOutcomeA", _a_text(evidence, outcome)),
        ("TIOutcomeAPredictorRows", _a_predictor_rows(evidence)),
        ("TIOutcomeADiagnosticRows", _a_diagnostic_rows(evidence)),
        ("TIOutcomeAConstructionRows", _a_construction_rows(evidence)),
        ("TIOutcomeAFrontierRows", _a_frontier_rows(evidence)),
        ("TIOutcomeATimingRows", _a_timing_rows(evidence)),
        ("TIOutcomeMetricChoice", _direct_text(evidence, outcome)),
        (
            "TIOutcomeMetricMechanismRows",
            _direct_mechanism_rows(evidence, outcome),
        ),
        ("TIOutcomeMetricOutcomeRows", _direct_outcome_rows(evidence, outcome)),
        ("TIOutcomeB", _b_text(evidence, outcome)),
        ("TIOutcomeBConfigurationRows", _b_configuration_rows(evidence, outcome)),
        ("TIOutcomeBAlternativeRows", _b_alternative_rows(evidence, outcome)),
        ("TIOutcomeBOutcomeRows", _b_outcome_rows(evidence, outcome)),
        ("TIOutcomeBOverheadRows", _b_overhead_rows(evidence, outcome)),
        ("TIOutcomeConclusion", CONCLUSION_TEXT[outcome.branch]),
        ("TIOutcomeSourceAudit", _source_text(evidence["source_audit"])),
        (
            "TIOutcomeSourceExclusionRows",
            _source_exclusion_rows(evidence["source_audit"]),
        ),
        ("TIOutcomeHardware", _hardware_text(evidence, outcome)),
    )
    lines = ["% Generated by render_terminal_incidence_results.py; do not edit."]
    lines.extend(f"\\newcommand{{\\{name}}}{{{body}}}" for name, body in macros)
    return "\n".join(lines) + "\n"


def _load_production_evidence() -> dict:
    """Read only explicitly pinned, committed confirmation evidence."""
    import within_family_evidence as Within
    if Within.PRODUCTION_RESULTS_REVISION is not None:
        try:
            return Within.load_evidence(results_revision=Within.PRODUCTION_RESULTS_REVISION,
                                        artifact_pins=Within.PRODUCTION_ARTIFACT_PINS)
        except (ValueError, OSError) as error:
            raise RenderError(str(error)) from error
    _validate_production_pin_contract(
        PRODUCTION_DIGEST_PINS, PRODUCTION_EXPECTED_A_PASS
    )
    import terminal_incidence_evidence as Evidence
    try:
        return Evidence.load_evidence(
            source_revision=PRODUCTION_SOURCE_SEAL_REVISION,
            results_revision=PRODUCTION_RESULTS_REVISION,
            artifact_pins=PRODUCTION_ARTIFACT_PINS,
            result_pins=PRODUCTION_DIGEST_PINS,
            expected_a_pass=PRODUCTION_EXPECTED_A_PASS,
        )
    except (Evidence.EvidenceError, ValueError) as error:
        raise RenderError(str(error)) from error


def _validate_output_target(
    path: Path,
    *,
    expected: Path = DEFAULT_OUTPUT,
    trusted_root: Path = PAPER_ROOT,
) -> Path:
    """Require the one canonical output and reject every symlink component."""
    path = Path(path)
    expected = Path(expected)
    trusted_root = Path(trusted_root)
    if not path.is_absolute() or path != expected:
        raise RenderError("output must be the exact canonical generated-paper path")
    if not expected.is_absolute() or not trusted_root.is_absolute():
        raise RenderError("the configured output boundary is not absolute")
    try:
        relative = path.relative_to(trusted_root)
    except ValueError as error:
        raise RenderError("output is outside its trusted root") from error
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise RenderError("output has a noncanonical lexical path")

    components = [trusted_root]
    current = trusted_root
    for part in relative.parts:
        current = current / part
        components.append(current)
    for index, current in enumerate(components):
        is_leaf = index == len(components) - 1
        try:
            info = current.lstat()
        except FileNotFoundError:
            if is_leaf:
                continue
            raise RenderError(f"output parent is missing: {current}")
        except OSError as error:
            raise RenderError(f"cannot inspect output path component: {current}") from error
        if stat.S_ISLNK(info.st_mode):
            raise RenderError("output path contains a symlink component")
        if is_leaf:
            if not stat.S_ISREG(info.st_mode):
                raise RenderError("existing output is not a regular file")
        elif not stat.S_ISDIR(info.st_mode):
            raise RenderError("output parent is not a directory")

    try:
        if path.parent.resolve(strict=True) != path.parent:
            raise RenderError("output parent does not resolve to its lexical path")
        if path.exists() and path.resolve(strict=True) != path:
            raise RenderError("output does not resolve to its lexical path")
    except OSError as error:
        raise RenderError("cannot resolve the canonical output boundary") from error
    return path


def _read_output(
    path: Path,
    *,
    expected: Path = DEFAULT_OUTPUT,
    trusted_root: Path = PAPER_ROOT,
) -> bytes:
    target = _validate_output_target(
        path, expected=expected, trusted_root=trusted_root
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(target, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_OUTPUT_BYTES:
            raise RenderError("generated output is not a bounded regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(MAX_OUTPUT_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_OUTPUT_BYTES:
            raise RenderError("generated output exceeds its byte limit")
        stable = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        leaf = target.lstat()
        if (
            not stable
            or stat.S_ISLNK(leaf.st_mode)
            or not stat.S_ISREG(leaf.st_mode)
            or (leaf.st_dev, leaf.st_ino) != (after.st_dev, after.st_ino)
        ):
            raise RenderError("generated output changed while it was read")
        return raw
    except FileNotFoundError as error:
        raise RenderError(f"generated output is missing: {target}") from error
    except OSError as error:
        raise RenderError("cannot safely read generated output") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _check_output(
    path: Path,
    rendered: str,
    *,
    expected: Path = DEFAULT_OUTPUT,
    trusted_root: Path = PAPER_ROOT,
) -> None:
    raw = rendered.encode("utf-8")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise RenderError("rendered output exceeds its byte limit")
    if _read_output(path, expected=expected, trusted_root=trusted_root) != raw:
        raise RenderError(f"generated output is stale: {path}")


def _write_output_atomic(
    path: Path,
    rendered: str,
    *,
    expected: Path = DEFAULT_OUTPUT,
    trusted_root: Path = PAPER_ROOT,
) -> None:
    target = _validate_output_target(
        path, expected=expected, trusted_root=trusted_root
    )
    raw = rendered.encode("utf-8")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise RenderError("rendered output exceeds its byte limit")

    temporary = None
    parent_descriptor = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=str(target.parent)
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())

        _validate_output_target(
            target, expected=expected, trusted_root=trusted_root
        )
        parent_flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        parent_descriptor = os.open(target.parent, parent_flags)
        try:
            existing = os.stat(
                target.name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise RenderError("existing output is not a regular non-symlink file")
        os.replace(
            Path(temporary).name,
            target.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary = None
        os.fsync(parent_descriptor)
        _check_output(
            target,
            rendered,
            expected=expected,
            trusted_root=trusted_root,
        )
    except OSError as error:
        raise RenderError("cannot atomically write generated output") from error
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _run_self_test() -> bool:
    suite = unittest.TestSuite(
        unittest.defaultTestLoader.discover(str(PAPER_ROOT), pattern=pattern)
        for pattern in (
            "test_render_terminal_incidence_results.py",
            "test_terminal_incidence_evidence.py",
            "test_terminal_incidence_selection_evidence.py",
            "test_within_family_evidence.py",
            "test_render_within_family_results.py",
        )
    )
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return result.wasSuccessful()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.self_test:
        return 0 if _run_self_test() else 1
    try:
        output = _validate_output_target(args.output)
        rendered = render(_load_production_evidence())
        if args.check:
            _check_output(output, rendered)
        else:
            _write_output_atomic(output, rendered)
    except (OSError, RenderError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
