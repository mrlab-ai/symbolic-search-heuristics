#!/usr/bin/env python3
"""Render the sealed cofactor-profile predictor analysis as TeX macros.

The renderer reads only the canonical predictor artifact and its SHA-256
sidecar.  It never opens Lab properties.  The production digest deliberately
remains unset until the complete recovered matrix has been analyzed; normal
``--write`` and ``--check`` modes fail closed while the renderer is unsealed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_predictors as Analysis
import pdb_profile_comparison_protocol as Protocol


class RenderError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR / "artifacts" / "pdb-profile-comparison" / "predictors-v1.json"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "pdb-profile-predictors-v1.tex"
)

# Set exactly once, after outcome-blind recovery and analysis.  The committed
# artifact sidecar is not by itself a scientific pin because both files could
# otherwise drift together.
EXPECTED_ANALYSIS_SHA256 = None

MAX_ANALYSIS_BYTES = 128 * 1024 * 1024
MAX_TEX_BYTES = 256 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MACRO_RE = re.compile(r"^[A-Za-z]+$")

FRAGMENTATION_SPECS = (
    ("cofactor_width", "Cofactor width $W$", "cofactor_width", "fragmentation", "same"),
    ("total_add_nodes", "Total ADD size $U$", "total_add_nodes", "fragmentation", "same"),
    ("finite_values", "Finite values $V$", "finite_values", "fragmentation", "same"),
    ("quality", "Selector score", "quality", "fragmentation", "opposite"),
    (
        "quality_to_total_effort",
        "Selector score",
        "quality",
        "actual_effort",
        "opposite",
    ),
)
CERTIFICATE_SPECS = (
    ("B_profile", "$B_{\\mathrm{profile}}$", "B_profile"),
    ("B_width", "$B_{\\mathrm{width}}$", "B_width"),
    ("B_add", "$B_{\\mathrm{add}}$", "B_add"),
)
GATE_NAMES = (
    "cofactor_width_useful_fragmentation_predictor",
    "cut_aligned_profile_sharper_explanation",
    "width_filter_materially_lower_effort_than_matched_add",
    "cap_aware_width_materially_lower_effort_than_exact_width",
    "cap_aware_width_higher_coverage_than_profiled_blind",
)


def canonical_json(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise RenderError("analysis is not finite canonical JSON") from err


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RenderError("duplicate JSON key {!r}".format(key))
        result[key] = value
    return result


def read_regular(path, maximum):
    path = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(path, flags)
    except OSError as err:
        raise RenderError("cannot open {}: {}".format(path, err)) from err
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise RenderError("{} must be a regular non-symlink file".format(path))
        if info.st_size > maximum:
            raise RenderError("{} exceeds its size limit".format(path))
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise RenderError("{} exceeds its size limit".format(path))
        final = os.fstat(descriptor)
        if (
            final.st_dev != info.st_dev
            or final.st_ino != info.st_ino
            or final.st_size != info.st_size
            or len(raw) != info.st_size
        ):
            raise RenderError("{} changed while it was read".format(path))
        return raw
    finally:
        os.close(descriptor)


def parse_canonical(raw, source):
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as err:
        raise RenderError("{} is not ASCII JSON".format(source)) from err

    def reject_constant(token):
        raise RenderError("{} contains nonfinite {}".format(source, token))

    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=reject_constant,
        )
    except RenderError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as err:
        raise RenderError("{} is invalid JSON".format(source)) from err
    if raw != canonical_json(value) + b"\n":
        raise RenderError("{} is not canonical ASCII JSON plus one newline".format(source))
    return value


def _require_mapping(value, label, keys=None):
    if not isinstance(value, dict):
        raise RenderError("{} must be an object".format(label))
    if keys is not None and set(value) != set(keys):
        raise RenderError("{} keys changed".format(label))
    return value


def _require_sequence(value, label, length=None):
    if not isinstance(value, list):
        raise RenderError("{} must be an array".format(label))
    if length is not None and len(value) != length:
        raise RenderError("{} length changed".format(label))
    return value


def _require_int(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise RenderError("{} must be an integer >= {}".format(label, minimum))
    return value


def _fraction(record, label, allow_none=False):
    if record is None:
        if allow_none:
            return None
        raise RenderError("{} is missing".format(label))
    record = _require_mapping(
        record, label, {"numerator", "denominator", "value"}
    )
    numerator = record["numerator"]
    denominator = record["denominator"]
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise RenderError("{} is not an exact fraction".format(label))
    result = Fraction(numerator, denominator)
    if result.numerator != numerator or result.denominator != denominator:
        raise RenderError("{} is not reduced".format(label))
    decimal = record["value"]
    if type(decimal) not in (int, float) or not math.isfinite(float(decimal)):
        raise RenderError("{} has a nonfinite decimal projection".format(label))
    if float(decimal) != float(result):
        raise RenderError("{} decimal projection changed".format(label))
    return result


def _ratio_matches(record, numerator, denominator, label):
    expected = None if denominator == 0 else Fraction(numerator, denominator)
    actual = _fraction(record, label, allow_none=True)
    if actual != expected:
        raise RenderError("{} arithmetic changed".format(label))
    return actual


def _validate_pairwise(summary, key, predictor, target, direction):
    label = "predictor {}".format(key)
    summary = _require_mapping(summary, label)
    if (
        summary.get("predictor") != predictor
        or summary.get("target") != target
        or summary.get("direction") != direction
    ):
        raise RenderError("{} semantic contract changed".format(label))
    outcome_keys = (
        "both_tied",
        "predictor_tied",
        "target_tied",
        "concordant",
        "discordant",
    )
    counts = {
        outcome: _require_int(summary.get(outcome, 0), "{} {}".format(label, outcome))
        for outcome in outcome_keys
    }
    pairs = _require_int(summary.get("distinct_heuristic_pairs"), label + " pairs")
    if pairs != sum(counts.values()):
        raise RenderError("{} pair outcomes do not conserve".format(label))
    comparable = _require_int(summary.get("comparable"), label + " comparable")
    if comparable != counts["concordant"] + counts["discordant"]:
        raise RenderError("{} comparable count changed".format(label))
    _ratio_matches(
        summary.get("micro_concordance"),
        counts["concordant"],
        comparable,
        label + " micro concordance",
    )
    tasks = _require_int(
        summary.get("tasks_with_comparable_pairs"), label + " task support"
    )
    domains = _require_int(summary.get("eligible_domains"), label + " domains")
    if tasks > Protocol.COHORT_TASKS or domains > Protocol.COHORT_DOMAINS:
        raise RenderError("{} support exceeds the frozen cohort".format(label))
    domain_rows = _require_sequence(
        summary.get("by_domain"), label + " by domain", Protocol.COHORT_DOMAINS
    )
    aggregate = {outcome: 0 for outcome in outcome_keys}
    domain_values = {}
    domain_comparable = {}
    for row in domain_rows:
        row = _require_mapping(row, label + " domain row")
        domain = row.get("domain")
        if type(domain) is not str or domain in domain_values:
            raise RenderError("{} has duplicate or invalid domains".format(label))
        row_counts = {
            outcome: _require_int(
                row.get(outcome, 0), "{} {} {}".format(label, domain, outcome)
            )
            for outcome in outcome_keys
        }
        row_comparable = row_counts["concordant"] + row_counts["discordant"]
        if row.get("comparable") != row_comparable:
            raise RenderError("{} {} comparable count changed".format(label, domain))
        domain_comparable[domain] = row_comparable
        concordance = _ratio_matches(
            row.get("concordance"),
            row_counts["concordant"],
            row_comparable,
            "{} {} concordance".format(label, domain),
        )
        domain_values[domain] = concordance
        for outcome in outcome_keys:
            aggregate[outcome] += row_counts[outcome]
    if aggregate != counts:
        raise RenderError("{} domain outcomes do not conserve".format(label))
    if len([value for value in domain_values.values() if value is not None]) != domains:
        raise RenderError("{} eligible-domain count changed".format(label))
    eligible_values = {
        domain: value for domain, value in domain_values.items() if value is not None
    }
    expected_macro = (
        sum(eligible_values.values(), Fraction()) / len(eligible_values)
        if eligible_values
        else None
    )
    macro = _fraction(summary.get("equal_domain_macro"), label + " macro", True)
    if macro != expected_macro:
        raise RenderError("{} macro arithmetic changed".format(label))
    loo = _require_mapping(summary.get("leave_one_domain_out"), label + " LOO")
    values = _require_mapping(loo.get("values"), label + " LOO values")
    if len(values) != Protocol.COHORT_DOMAINS:
        raise RenderError("{} LOO domain count changed".format(label))
    if set(values) != set(domain_values):
        raise RenderError("{} LOO domains changed".format(label))
    loo_values = []
    for omitted, record in sorted(values.items()):
        actual = _fraction(record, "{} LOO {}".format(label, omitted), True)
        retained = [
            value for domain, value in eligible_values.items() if domain != omitted
        ]
        expected = sum(retained, Fraction()) / len(retained) if retained else None
        if actual != expected:
            raise RenderError("{} LOO {} arithmetic changed".format(label, omitted))
        loo_values.append(actual)
    finite_loo = [value for value in loo_values if value is not None]
    minimum = _fraction(loo.get("minimum"), label + " LOO minimum", True)
    maximum = _fraction(loo.get("maximum"), label + " LOO maximum", True)
    if minimum != (min(finite_loo) if finite_loo else None):
        raise RenderError("{} LOO minimum changed".format(label))
    if maximum != (max(finite_loo) if finite_loo else None):
        raise RenderError("{} LOO maximum changed".format(label))
    return {
        "summary": summary,
        "macro": macro,
        "minimum": minimum,
        "maximum": maximum,
        "pairs": comparable,
        "tasks": tasks,
        "domains": domains,
        "domain_comparable": domain_comparable,
    }


def _validate_shared_comparison(value, label, specs, target):
    value = _require_mapping(
        value, label, {"protocol", "target", "support", "predictors"}
    )
    if value["protocol"] != Analysis.SHARED_COMPARISON_PROTOCOL:
        raise RenderError("{} protocol changed".format(label))
    if value["target"] != target:
        raise RenderError("{} target changed".format(label))
    support = _require_mapping(
        value["support"],
        label + " support",
        {
            "observation_pairs",
            "target_tied",
            "any_predictor_tied",
            "comparable",
            "tasks_with_comparable_pairs",
            "eligible_domains",
            "predictor_tie_counts",
            "by_domain",
        },
    )
    pairs = _require_int(support["observation_pairs"], label + " observation pairs")
    target_tied = _require_int(support["target_tied"], label + " target ties")
    predictor_tied = _require_int(
        support["any_predictor_tied"], label + " predictor ties"
    )
    comparable = _require_int(support["comparable"], label + " comparable")
    if pairs != target_tied + predictor_tied + comparable:
        raise RenderError("{} support does not partition pairs".format(label))
    tasks = _require_int(
        support["tasks_with_comparable_pairs"], label + " supported tasks"
    )
    domains = _require_int(support["eligible_domains"], label + " supported domains")
    if tasks > Protocol.COHORT_TASKS or domains > Protocol.COHORT_DOMAINS:
        raise RenderError("{} support exceeds the cohort".format(label))
    domain_rows = _require_sequence(
        support["by_domain"], label + " support by domain", Protocol.COHORT_DOMAINS
    )
    support_by_domain = {}
    domain_comparable = 0
    contributing_domains = 0
    for row in domain_rows:
        row = _require_mapping(row, label + " support domain row", {"domain", "comparable"})
        domain = row["domain"]
        if type(domain) is not str or domain in support_by_domain:
            raise RenderError("{} support domains changed".format(label))
        count = _require_int(row["comparable"], label + " domain comparable")
        support_by_domain[domain] = count
        domain_comparable += count
        contributing_domains += count > 0
    if domain_comparable != comparable or contributing_domains != domains:
        raise RenderError("{} domain support does not conserve".format(label))
    tie_counts = _require_mapping(
        support["predictor_tie_counts"], label + " predictor tie counts"
    )
    if not set(tie_counts).issubset(specs) or any(
        type(count) is not int or count < 0 for count in tie_counts.values()
    ):
        raise RenderError("{} predictor tie detail changed".format(label))
    predictors = _require_mapping(
        value["predictors"], label + " predictors", set(specs)
    )
    validated = {}
    for key, (predictor, direction) in specs.items():
        row = _validate_pairwise(
            predictors[key], key, predictor, target, direction
        )
        if row["pairs"] != comparable or row["tasks"] != tasks or row["domains"] != domains:
            raise RenderError("{} predictor support is not shared".format(label))
        if row["domain_comparable"] != support_by_domain:
            raise RenderError("{} predictor domain support is not shared".format(label))
        validated[key] = row
    return validated


def _validate_contrast(item, candidate, reference, label):
    item = _require_mapping(
        item,
        label,
        {
            "candidate",
            "reference",
            "fixed_task_denominator",
            "coverage",
            "conditional_effort",
            "leave_one_domain_out",
            "by_domain",
        },
    )
    if item.get("candidate") != candidate or item.get("reference") != reference:
        raise RenderError("{} labels changed".format(label))
    if item.get("fixed_task_denominator") != Protocol.COHORT_TASKS:
        raise RenderError("{} denominator changed".format(label))
    coverage = _require_mapping(item.get("coverage"), label + " coverage")
    outcome_keys = (
        "both_solved", "candidate_only", "reference_only", "both_unsolved"
    )
    required_coverage_keys = {
        "candidate_minus_reference", "equal_domain_macro_difference"
    }
    allowed_coverage_keys = set(outcome_keys) | required_coverage_keys | {
        "incomplete_effort", "pool_ineligible"
    }
    if (
        not required_coverage_keys.issubset(coverage)
        or not set(coverage).issubset(allowed_coverage_keys)
    ):
        raise RenderError("{} coverage keys changed".format(label))
    outcomes = {
        key: _require_int(coverage.get(key, 0), "{} coverage {}".format(label, key))
        for key in outcome_keys
    }
    if sum(outcomes.values()) != Protocol.COHORT_TASKS:
        raise RenderError("{} coverage outcomes do not conserve".format(label))
    difference = outcomes["candidate_only"] - outcomes["reference_only"]
    if coverage.get("candidate_minus_reference") != difference:
        raise RenderError("{} coverage difference changed".format(label))
    conditional = _require_mapping(
        item.get("conditional_effort"), label + " conditional effort"
    )
    eligible = _require_int(conditional.get("eligible_pairs"), label + " eligible pairs")
    candidate_total = _require_int(
        conditional.get("candidate_total"), label + " candidate effort"
    )
    reference_total = _require_int(
        conditional.get("reference_total"), label + " reference effort"
    )
    if eligible > outcomes["both_solved"]:
        raise RenderError("{} effort support exceeds joint coverage".format(label))
    incomplete = _require_int(
        coverage.get("incomplete_effort", 0), label + " incomplete effort"
    )
    pool_ineligible = _require_int(
        coverage.get("pool_ineligible", 0), label + " pool ineligible"
    )
    if eligible + incomplete + pool_ineligible != outcomes["both_solved"]:
        raise RenderError("{} jointly solved effort statuses do not conserve".format(label))
    if not reference.startswith("pdb_") and pool_ineligible:
        raise RenderError("{} has an inapplicable pool exclusion".format(label))
    ratio = _ratio_matches(
        conditional.get("candidate_over_reference"),
        candidate_total,
        reference_total,
        label + " effort ratio",
    )
    rows = _require_sequence(item.get("by_domain"), label + " domain rows")
    if len(rows) != Protocol.COHORT_DOMAINS:
        raise RenderError("{} domain count changed".format(label))
    explicit_row_keys = {
        "domain",
        "tasks",
        "coverage_difference",
        "effort_eligible_pairs",
        "candidate_effort",
        "reference_effort",
        "effort_ratio",
    }
    allowed_row_keys = explicit_row_keys | set(outcome_keys)
    domain_data = {}
    aggregate_outcomes = {key: 0 for key in outcome_keys}
    aggregate_tasks = 0
    aggregate_eligible = 0
    aggregate_candidate = 0
    aggregate_reference = 0
    for raw_row in rows:
        row = _require_mapping(raw_row, label + " domain row")
        if not explicit_row_keys.issubset(row) or not set(row).issubset(allowed_row_keys):
            raise RenderError("{} domain-row keys changed".format(label))
        domain = row["domain"]
        if type(domain) is not str or domain in domain_data:
            raise RenderError("{} domain universe changed".format(label))
        tasks = _require_int(row["tasks"], "{} {} tasks".format(label, domain), 1)
        row_outcomes = {
            key: _require_int(
                row.get(key, 0), "{} {} {}".format(label, domain, key)
            )
            for key in outcome_keys
        }
        if sum(row_outcomes.values()) != tasks:
            raise RenderError("{} {} coverage does not conserve".format(label, domain))
        coverage_difference = _ratio_matches(
            row["coverage_difference"],
            row_outcomes["candidate_only"] - row_outcomes["reference_only"],
            tasks,
            "{} {} coverage difference".format(label, domain),
        )
        row_eligible = _require_int(
            row["effort_eligible_pairs"], "{} {} eligible pairs".format(label, domain)
        )
        if row_eligible > row_outcomes["both_solved"]:
            raise RenderError("{} {} effort support exceeds coverage".format(label, domain))
        row_candidate = _require_int(
            row["candidate_effort"], "{} {} candidate effort".format(label, domain)
        )
        row_reference = _require_int(
            row["reference_effort"], "{} {} reference effort".format(label, domain)
        )
        _ratio_matches(
            row["effort_ratio"],
            row_candidate,
            row_reference,
            "{} {} effort ratio".format(label, domain),
        )
        domain_data[domain] = {
            "coverage_difference": coverage_difference,
            "candidate_effort": row_candidate,
            "reference_effort": row_reference,
        }
        aggregate_tasks += tasks
        aggregate_eligible += row_eligible
        aggregate_candidate += row_candidate
        aggregate_reference += row_reference
        for key in outcome_keys:
            aggregate_outcomes[key] += row_outcomes[key]
    if aggregate_tasks != Protocol.COHORT_TASKS or aggregate_outcomes != outcomes:
        raise RenderError("{} domain coverage totals do not conserve".format(label))
    if (
        aggregate_eligible != eligible
        or aggregate_candidate != candidate_total
        or aggregate_reference != reference_total
    ):
        raise RenderError("{} domain effort totals do not conserve".format(label))
    expected_macro = sum(
        (row["coverage_difference"] for row in domain_data.values()), Fraction()
    ) / Protocol.COHORT_DOMAINS
    actual_macro = _fraction(
        coverage["equal_domain_macro_difference"], label + " coverage macro"
    )
    if actual_macro != expected_macro:
        raise RenderError("{} coverage macro arithmetic changed".format(label))
    loo = _require_mapping(item.get("leave_one_domain_out"), label + " LOO")
    effort_loo = _require_mapping(loo.get("effort_ratio"), label + " effort LOO")
    coverage_loo = _require_mapping(
        loo.get("coverage_macro_difference"), label + " coverage LOO"
    )
    if set(effort_loo) != set(domain_data) or set(coverage_loo) != set(domain_data):
        raise RenderError("{} effort LOO domains changed".format(label))
    for omitted, row in domain_data.items():
        _ratio_matches(
            effort_loo[omitted],
            candidate_total - row["candidate_effort"],
            reference_total - row["reference_effort"],
            "{} effort LOO {}".format(label, omitted),
        )
        expected_coverage = sum(
            (
                retained["coverage_difference"]
                for domain, retained in domain_data.items()
                if domain != omitted
            ),
            Fraction(),
        ) / (Protocol.COHORT_DOMAINS - 1)
        actual_coverage = _fraction(
            coverage_loo[omitted], "{} coverage LOO {}".format(label, omitted)
        )
        if actual_coverage != expected_coverage:
            raise RenderError("{} coverage LOO {} arithmetic changed".format(label, omitted))
    return {
        "item": item,
        "coverage_difference": difference,
        "eligible": eligible,
        "ratio": ratio,
        "domain_names": frozenset(domain_data),
    }


def validate_analysis(value):
    try:
        Analysis.require_frozen_protocol()
    except Analysis.PredictorAnalysisError as err:
        raise RenderError("frozen predictor protocol bytes changed") from err
    top_keys = {
        "schema",
        "raw_analysis_protocol",
        "frozen_predictor_protocol_sha256",
        "scope",
        "fragmentation_observation_status",
        "fragmentation_observations",
        "fragmentation_predictors",
        "fragmentation_gate_comparison",
        "certificate_predictors",
        "certificate_gate_comparison",
        "selector_contrasts",
        "decision_gates",
    }
    value = _require_mapping(value, "analysis", top_keys)
    if value["schema"] != Analysis.SCHEMA:
        raise RenderError("analysis schema changed")
    if value["raw_analysis_protocol"] != Protocol.ANALYSIS_PROTOCOL:
        raise RenderError("raw analysis protocol changed")
    if value["frozen_predictor_protocol_sha256"] != Analysis.PROTOCOL_SHA256:
        raise RenderError("frozen predictor protocol digest changed")
    scope = _require_mapping(
        value["scope"],
        "scope",
        {
            "tasks",
            "domains",
            "configurations",
            "inference",
            "strong_claim_support",
        },
    )
    if scope != {
        "tasks": Protocol.COHORT_TASKS,
        "domains": Protocol.COHORT_DOMAINS,
        "configurations": Protocol.CONFIG_COUNT,
        "inference": Protocol.INFERENCE_POLICY,
        "strong_claim_support": {
            "minimum_domains": Analysis.MIN_STRONG_CLAIM_DOMAINS,
            "minimum_tasks_or_pairs": Analysis.MIN_STRONG_CLAIM_TASKS,
        },
    }:
        raise RenderError("analysis scope changed")

    statuses = _require_mapping(
        value["fragmentation_observation_status"], "fragmentation statuses"
    )
    allowed_statuses = {"eligible", "unsolved", "incomplete_profile", "zero_union_effort"}
    if not set(statuses).issubset(allowed_statuses):
        raise RenderError("fragmentation status vocabulary changed")
    if sum(
        _require_int(count, "fragmentation status {}".format(status))
        for status, count in statuses.items()
    ) != Protocol.COHORT_TASKS * (Protocol.CONFIG_COUNT - 2):
        raise RenderError("fragmentation statuses do not conserve cells")
    observations = _require_sequence(
        value["fragmentation_observations"], "fragmentation observations"
    )
    if len(observations) > statuses.get("eligible", 0):
        raise RenderError("deduplicated observations exceed eligible cells")

    fragmentation = _require_mapping(
        value["fragmentation_predictors"],
        "fragmentation predictors",
        {spec[0] for spec in FRAGMENTATION_SPECS},
    )
    validated_fragmentation = {
        key: _validate_pairwise(fragmentation[key], key, predictor, target, direction)
        for key, _, predictor, target, direction in FRAGMENTATION_SPECS
    }
    validated_fragmentation_gate = _validate_shared_comparison(
        value["fragmentation_gate_comparison"],
        "fragmentation gate comparison",
        {
            "cofactor_width": ("cofactor_width", "same"),
            "total_add_nodes": ("total_add_nodes", "same"),
            "quality": ("quality", "opposite"),
        },
        "fragmentation",
    )
    certificates = _require_mapping(
        value["certificate_predictors"],
        "certificate predictors",
        {spec[0] for spec in CERTIFICATE_SPECS},
    )
    validated_certificates = {
        key: _validate_pairwise(
            certificates[key], key, predictor, "actual_effort", "same"
        )
        for key, _, predictor in CERTIFICATE_SPECS
    }
    validated_certificate_gate = _validate_shared_comparison(
        value["certificate_gate_comparison"],
        "certificate gate comparison",
        {
            "B_profile": ("B_profile", "same"),
            "B_width": ("B_width", "same"),
            "B_add": ("B_add", "same"),
        },
        "actual_effort",
    )

    contrasts = _require_mapping(
        value["selector_contrasts"],
        "selector contrasts",
        {
            "matched_width_vs_add",
            "cap_width_vs_exact_width",
            "constrained_vs_unconstrained",
            "selector_vs_profiled_blind",
        },
    )
    width_add_items = _require_sequence(
        contrasts["matched_width_vs_add"], "matched width/ADD contrasts", 5
    )
    cap_exact_items = _require_sequence(
        contrasts["cap_width_vs_exact_width"], "cap/exact contrasts", 5
    )
    width_add = []
    cap_exact = []
    for index, (k, u) in enumerate(Protocol.MATCHED_BUDGETS):
        width = "pdb_cap_width_k{}".format(k)
        width_add.append(_validate_contrast(
            width_add_items[index],
            width,
            "pdb_cap_add_u{}".format(u),
            "matched width/ADD K={}".format(k),
        ))
        cap_exact.append(_validate_contrast(
            cap_exact_items[index],
            width,
            "pdb_exact_k{}".format(k),
            "cap/exact K={}".format(k),
        ))

    constrained_items = _require_sequence(
        contrasts["constrained_vs_unconstrained"],
        "constrained/unconstrained contrasts",
        15,
    )
    constrained = []
    constrained_index = 0
    for k, u in Protocol.MATCHED_BUDGETS:
        for selector in (
            "pdb_exact_k{}".format(k),
            "pdb_cap_width_k{}".format(k),
            "pdb_cap_add_u{}".format(u),
        ):
            constrained.append(_validate_contrast(
                constrained_items[constrained_index],
                selector,
                "pdb_exact_unconstrained",
                "constrained/unconstrained {}".format(selector),
            ))
            constrained_index += 1
    blind_items = _require_sequence(
        contrasts["selector_vs_profiled_blind"], "selector/blind contrasts", 16
    )
    blind_by_label = {}
    for index, selector in enumerate(Protocol.LABELS[2:]):
        validated = _validate_contrast(
            blind_items[index],
            selector,
            "blind_fw_profiled",
            "selector/blind {}".format(selector),
        )
        blind_by_label[selector] = validated

    domain_sets = [
        frozenset(row["domain_comparable"])
        for row in (
            list(validated_fragmentation.values())
            + list(validated_fragmentation_gate.values())
            + list(validated_certificates.values())
            + list(validated_certificate_gate.values())
        )
    ] + [
        row["domain_names"]
        for row in width_add + cap_exact + constrained + list(blind_by_label.values())
    ]
    if not domain_sets or any(domains != domain_sets[0] for domains in domain_sets[1:]):
        raise RenderError("analysis domain universes disagree")

    gates = _require_mapping(value["decision_gates"], "decision gates", GATE_NAMES)
    recomputed = Analysis.decision_gates(
        value["fragmentation_gate_comparison"]["predictors"],
        value["certificate_gate_comparison"]["predictors"],
        contrasts,
    )
    if gates != recomputed:
        raise RenderError("decision gates disagree with the frozen exact computation")
    if any(type(item.get("pass")) is not bool for item in gates.values()):
        raise RenderError("decision-gate verdict is not Boolean")
    return {
        "analysis": value,
        "fragmentation": validated_fragmentation,
        "fragmentation_gate": validated_fragmentation_gate,
        "certificates": validated_certificates,
        "certificate_gate": validated_certificate_gate,
        "width_add": width_add,
        "cap_exact": cap_exact,
        "blind_by_label": blind_by_label,
        "gates": gates,
    }


def load_analysis(path, expected_digest=EXPECTED_ANALYSIS_SHA256):
    if expected_digest is None:
        raise RenderError("predictor renderer is unsealed; expected digest is unset")
    if type(expected_digest) is not str or SHA256_RE.fullmatch(expected_digest) is None:
        raise RenderError("expected analysis digest is invalid")
    path = Path(path)
    raw = read_regular(path, MAX_ANALYSIS_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_digest:
        raise RenderError("analysis artifact digest changed")
    sidecar = read_regular(path.with_name(path.name + ".sha256"), 1024)
    expected_sidecar = "{}  {}\n".format(digest, path.name).encode("ascii")
    if sidecar != expected_sidecar:
        raise RenderError("analysis sidecar changed")
    value = parse_canonical(raw, "predictor analysis artifact")
    return value, digest


def _decimal(value, places=3):
    if value is None:
        return "--"
    if isinstance(value, Fraction):
        number = Decimal(value.numerator) / Decimal(value.denominator)
    elif type(value) in (int, float) and math.isfinite(float(value)):
        number = Decimal(str(value))
    else:
        raise RenderError("rendered value is not finite")
    quantum = Decimal(1).scaleb(-places)
    rendered = format(number.quantize(quantum, rounding=ROUND_HALF_UP), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered == "-0" else rendered


def _signed(value):
    value = _require_int(abs(value), "signed result") * (-1 if value < 0 else 1)
    return "+{}".format(value) if value > 0 else str(value)


def _macro(name, content):
    if MACRO_RE.fullmatch(name) is None:
        raise RenderError("invalid macro name {}".format(name))
    if type(content) is not str or "\x00" in content:
        raise RenderError("invalid macro content")
    return "\\newcommand{{\\{}}}{{{}}}".format(name, content)


def _rows_macro(name, rows, columns):
    if not rows:
        raise RenderError("{} has no rows".format(name))
    rendered = []
    for row in rows:
        if not isinstance(row, (tuple, list)) or len(row) != columns:
            raise RenderError("{} row shape changed".format(name))
        if any(type(cell) is not str or "\n" in cell or "\r" in cell for cell in row):
            raise RenderError("{} contains an invalid cell".format(name))
        rendered.append(" & ".join(row) + " " + "\\" * 2)
    return _macro(name, "%\n" + "\n".join(rendered))


def _support(row):
    return "{}/{}".format(row["pairs"], row["domains"])


def _range(row):
    if row["minimum"] is None or row["maximum"] is None:
        return "--"
    return "{}--{}".format(_decimal(row["minimum"]), _decimal(row["maximum"]))


def render_tex(value, digest):
    if type(digest) is not str or SHA256_RE.fullmatch(digest) is None:
        raise RenderError("analysis digest is invalid")
    data = validate_analysis(value)
    fragment_rows = []
    for key, paper_label, _, target, _ in FRAGMENTATION_SPECS:
        row = (
            data["fragmentation_gate"][key]
            if key in data["fragmentation_gate"]
            else data["fragmentation"][key]
        )
        target_label = "Fragmentation" if target == "fragmentation" else "Effort"
        fragment_rows.append((
            paper_label,
            target_label,
            _decimal(row["macro"]),
            _range(row),
            _support(row),
        ))
    certificate_rows = []
    for key, paper_label, _ in CERTIFICATE_SPECS:
        row = data["certificate_gate"][key]
        certificate_rows.append((
            paper_label,
            _decimal(row["macro"]),
            _range(row),
            _support(row),
        ))
    width_add_rows = []
    cap_exact_rows = []
    cap_blind_rows = []
    for (k, u), width_add, cap_exact in zip(
        Protocol.MATCHED_BUDGETS, data["width_add"], data["cap_exact"]
    ):
        blind = data["blind_by_label"]["pdb_cap_width_k{}".format(k)]
        width_add_rows.append((
            str(k),
            str(u),
            _signed(width_add["coverage_difference"]),
            _decimal(width_add["ratio"]),
            str(width_add["eligible"]),
        ))
        cap_exact_rows.append((
            str(k),
            _signed(cap_exact["coverage_difference"]),
            _decimal(cap_exact["ratio"]),
            str(cap_exact["eligible"]),
        ))
        cap_blind_rows.append((
            str(k),
            _signed(blind["coverage_difference"]),
            _decimal(blind["ratio"]),
            str(blind["eligible"]),
        ))

    width = data["fragmentation_gate"]["cofactor_width"]
    add = data["fragmentation_gate"]["total_add_nodes"]
    quality = data["fragmentation_gate"]["quality"]
    profile = data["certificate_gate"]["B_profile"]
    width_certificate = data["certificate_gate"]["B_width"]
    add_certificate = data["certificate_gate"]["B_add"]
    lines = [
        "% Generated from the sealed cofactor-profile predictor analysis.",
        "% Fixed-census descriptive results; support is comparable pairs/domains.",
        "% Analysis SHA-256: {}".format(digest),
        _macro("ProfileTasks", str(Protocol.COHORT_TASKS)),
        _macro("ProfileDomains", str(Protocol.COHORT_DOMAINS)),
        _macro("ProfileConfigurations", str(Protocol.CONFIG_COUNT)),
        _macro("ProfileWidthMacro", _decimal(width["macro"])),
        _macro("ProfileAddMacro", _decimal(add["macro"])),
        _macro("ProfileQualityMacro", _decimal(quality["macro"])),
        _macro("ProfileCertificateMacro", _decimal(profile["macro"])),
        _macro("ProfileWidthCertificateMacro", _decimal(width_certificate["macro"])),
        _macro("ProfileAddCertificateMacro", _decimal(add_certificate["macro"])),
        _macro(
            "ProfileWidthPredictorGate",
            "pass" if data["gates"][GATE_NAMES[0]]["pass"] else "fail",
        ),
        _macro(
            "ProfileSharperCertificateGate",
            "pass" if data["gates"][GATE_NAMES[1]]["pass"] else "fail",
        ),
        _macro(
            "ProfileMatchedAddGate",
            "pass" if data["gates"][GATE_NAMES[2]]["pass"] else "fail",
        ),
        _macro(
            "ProfileConstructionGate",
            "pass" if data["gates"][GATE_NAMES[3]]["pass"] else "fail",
        ),
        _macro(
            "ProfileBlindCoverageGate",
            "pass" if data["gates"][GATE_NAMES[4]]["pass"] else "fail",
        ),
        _rows_macro("ProfilePredictorRows", fragment_rows, 5),
        _rows_macro("ProfileCertificateRows", certificate_rows, 4),
        _rows_macro("ProfileWidthAddRows", width_add_rows, 5),
        _rows_macro("ProfileCapExactRows", cap_exact_rows, 4),
        _rows_macro("ProfileCapBlindRows", cap_blind_rows, 4),
    ]
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


def write_atomic(path, raw):
    path = Path(path)
    if path.resolve() != DEFAULT_OUTPUT.resolve():
        raise RenderError("--write is restricted to the generated-paper path")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def self_test():
    for value, expected in (
        (Fraction(1, 3), "0.333"),
        (Fraction(2, 3), "0.667"),
        (Fraction(1, 2000), "0.001"),
    ):
        if _decimal(value) != expected:
            raise RenderError("decimal self-test failed")
    if _signed(2) != "+2" or _signed(-2) != "-2" or _signed(0) != "0":
        raise RenderError("signed-integer self-test failed")
    try:
        _fraction({"numerator": 2, "denominator": 4, "value": 0.5}, "fixture")
    except RenderError:
        pass
    else:
        raise RenderError("unreduced fraction self-test failed")
    try:
        load_analysis(DEFAULT_ANALYSIS, expected_digest=None)
    except RenderError as err:
        if "unsealed" not in str(err):
            raise
    else:
        raise RenderError("unsealed renderer self-test failed")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    analysis, digest = load_analysis(args.analysis)
    expected = render_tex(analysis, digest)
    if args.write:
        write_atomic(args.output, expected)
        return 0
    actual = read_regular(args.output, MAX_TEX_BYTES)
    if actual != expected:
        raise RenderError("generated predictor TeX changed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RenderError as err:
        print("error: {}".format(err), file=__import__("sys").stderr)
        raise SystemExit(2)
