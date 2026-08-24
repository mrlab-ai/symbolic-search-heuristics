#!/usr/bin/env python3
"""Render pinned post-hoc cap-grid diagnostics as anonymous TeX macros.

The renderer reads only the canonical post-hoc JSON artifact and its sidecar.
It never opens Lab properties.  ``--check`` fails if either the artifact pin or
the generated TeX payload has drifted.
"""

from __future__ import annotations

import argparse
import copy
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


class RenderError(RuntimeError):
    """The pinned artifact cannot be safely rendered."""


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR
    / "artifacts"
    / "pdb-cap-grid-posthoc-review"
    / "analysis-v1.json"
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / "paper" / "generated" / "pdb-cap-grid-posthoc-v1.tex"

ANALYSIS_SCHEMA = "symbolic-search-heuristics/pdb-cap-grid-posthoc-review/v1"
ANALYSIS_PROTOCOL = "pdb-cap-grid-posthoc-review-analysis-v1"
ROLE = "post-hoc-theorem-guided-descriptive"
NO_INFERENCE_POLICY = "fixed-census-description-only-no-inference/v1"
CLAIM_GUIDANCE = "theorem-guided-diagnostics/v1"
OPERATIONAL_ELIGIBILITY = "same-pair-complete-certified-schema-v2-image-metrics/v1"
FINITE_CAP_DEFINITION = "cap-selected-kappa-is-nonnegative/v1"
EXACT_ENDPOINT_DEFINITION = "cap-selected-kappa-equals-minus-one/v1"
MATERIAL_TRANSFORM_DEFINITION = (
    "kappa-below-raw-max-strict-finite-sum-and-representation-reduction/v1"
)
SELECTED_COEFFICIENT_FORMULA = "c=2*V_selected*W_selected"
SELECTED_COEFFICIENT_ELIGIBILITY = "complete-certified-selector-trace-per-config/v1"
COVERAGE_LODO_ESTIMAND = "cap-minus-exact-equal-domain-macro-coverage/v1"
NODE_LODO_ESTIMAND = (
    "cap-over-exact-total-expanded-bdd-nodes-on-complete-certified-pairs/v1"
)
PARTITION_ELIGIBILITY = "finite-nonnegative-observed-partition_ratio_max/v1"
EXPECTED_ANALYSIS_SHA256 = (
    "195c209a8ba34a89c98fd0920c4f58753635cd3f375f6424ca49da017effc59d"
)
EXPECTED_PROPERTIES_CANONICAL_SHA256 = (
    "bddc69b2eedcc1442e6a42517d4d294e9a6ae0ab7dbf4aebc49714b152c0f215"
)
EXPECTED_RECORD_SCHEMA_MANIFEST_SHA256 = (
    "e944922a633c08594e48a2c667bf84cd35d6b8121d85d2b1c672aed4abea533e"
)
EXPECTED_PROSPECTIVE_ARTIFACT_SHA256 = (
    "fb8db53b4f5eea7306961351d110b0d331abc87fa2a31242321de429f32ad60a"
)
EXPECTED_PROSPECTIVE_SCHEMA = "symbolic-search-heuristics/pdb-cap-grid-focused-full/v1"
EXPECTED_PROTOCOL = "pdb-cap-grid-focused-full-evaluation-v1"
EXPECTED_SOURCE_ANALYSIS_PROTOCOL = "pdb-cap-grid-focused-full-analysis-v1"
EXPECTED_PROTOCOL_REVISION = "0fa5ecc1d93884e9cf35b433bacfe684765ba112"
EXPECTED_TASK_MANIFEST_SHA256 = (
    "295bff030c51eaf39871714335ff9cb945ce39ebc556774eeb3bfad112681345"
)
EXPECTED_PRIMARY_TASK_MANIFEST_SHA256 = (
    "1e126791b438d903cb6adcc441391b92d76a7e14cf46f6a89465a066823a986f"
)
EXPECTED_DEVELOPMENT_MANIFEST_SHA256 = (
    "3195dac7e62a34e5ac4cbeb715ab7f9b99e2ee64341082dd7d718ea2820751ca"
)
EXPECTED_OPTION_MATRIX_SHA256 = (
    "94238d64a699142ef81cc4a35489467af8b78dcdf46973536556eb7e3f6b6f78"
)

MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_TEX_BYTES = 256 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
MACRO_RE = re.compile(r"^[A-Za-z]+$")

SCOPES = (
    ("primary", "Primary", 1327),
    ("all_tasks", "All tasks", 1377),
)
STRATA = (
    ("finite_cap", "Finite cap"),
    ("exact_endpoint", "Exact endpoint"),
)
SELECTORS = (
    ("pdb_selector_k8", "Exact"),
    ("pdb_cap_grid_k8", "Cap-aware"),
)
SCOPE_ROLES = {
    "primary": "primary-development-complement-post-hoc-description",
    "all_tasks": "all-task-census-post-hoc-description",
}
EXPECTED_SELECTOR_TRACE_COUNTS = {
    "primary": {"pdb_selector_k8": 1308, "pdb_cap_grid_k8": 1306},
    "all_tasks": {"pdb_selector_k8": 1358, "pdb_cap_grid_k8": 1356},
}
CONFIG_LABELS = (
    ("blind_fw", "Blind"),
    ("ms_exact", "M\\&S"),
    ("pdb_cegar_b100k", "CEGAR"),
    ("pdb_selector_k8", "Exact"),
    ("pdb_cap_grid_k8", "Cap-aware"),
)


def canonical_json(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as err:
        raise RenderError("value is not canonical finite JSON: {}".format(err)) from err


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RenderError("duplicate JSON key {!r}".format(key))
        result[key] = value
    return result


def read_regular(path, maximum):
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as err:
        raise RenderError("cannot inspect {}: {}".format(path, err)) from err
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RenderError("{} must be a regular non-symlink file".format(path))
    if info.st_size > maximum:
        raise RenderError("{} exceeds the {}-byte limit".format(path, maximum))
    try:
        return path.read_bytes()
    except OSError as err:
        raise RenderError("cannot read {}: {}".format(path, err)) from err


def parse_canonical(raw, source):
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as err:
        raise RenderError("{} is not ASCII JSON".format(source)) from err

    def reject_constant(token):
        raise RenderError("{} contains nonfinite constant {}".format(source, token))

    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=reject_constant,
        )
    except RenderError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as err:
        raise RenderError("{} is invalid JSON: {}".format(source, err)) from err
    if raw != canonical_json(value).encode("ascii") + b"\n":
        raise RenderError("{} is not canonical ASCII JSON plus one newline".format(source))
    return value


def _same(actual, expected):
    return type(actual) is type(expected) and actual == expected


def _require_dict(value, label):
    if not isinstance(value, dict):
        raise RenderError("{} must be an object".format(label))
    return value


def _require_int(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise RenderError("{} must be an integer >= {}".format(label, minimum))
    return value


def _require_number(value, label, minimum=None):
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise RenderError("{} must be a finite number".format(label))
    if minimum is not None and value < minimum:
        raise RenderError("{} must be >= {}".format(label, minimum))
    return value


def _require_sha256(value, label, expected):
    if type(value) is not str or SHA256_RE.fullmatch(value) is None or value != expected:
        raise RenderError("{} changed".format(label))


def load_analysis(path):
    raw = read_regular(path, MAX_ARTIFACT_BYTES)
    digest = sha256_bytes(raw)
    _require_sha256(digest, "analysis artifact digest", EXPECTED_ANALYSIS_SHA256)
    sidecar_path = Path(path).with_name(Path(path).name + ".sha256")
    expected_sidecar = "{}  {}\n".format(digest, Path(path).name).encode("ascii")
    if read_regular(sidecar_path, 1024) != expected_sidecar:
        raise RenderError("analysis sidecar changed")
    analysis = parse_canonical(raw, "post-hoc analysis artifact")
    validate_analysis(analysis)
    return analysis


def _validate_summary(summary, label, allow_empty=False, expected_count=None):
    summary = _require_dict(summary, label)
    count = _require_int(summary.get("count"), "{} count".format(label))
    if expected_count is not None and count != expected_count:
        raise RenderError("{} count changed".format(label))
    fields = ("minimum", "median", "nearest_rank_p95", "maximum")
    if count == 0:
        if not allow_empty or any(summary.get(field) is not None for field in fields):
            raise RenderError("{} has an invalid empty summary".format(label))
        return count
    values = [_require_number(summary.get(field), "{} {}".format(label, field), 0) for field in fields]
    if values != sorted(values):
        raise RenderError("{} quantiles are not ordered".format(label))
    return count


def _validate_coverage(coverage, pairs, label):
    coverage = _require_dict(coverage, label)
    if coverage.get("task_pairs") != pairs:
        raise RenderError("{} pair count changed".format(label))
    counts = [
        _require_int(coverage.get(field), "{} {}".format(label, field))
        for field in ("cap_wins", "cap_losses", "both_solved", "both_unsolved")
    ]
    if sum(counts) != pairs or coverage.get("wins_minus_losses") != counts[0] - counts[1]:
        raise RenderError("{} does not partition its pairs".format(label))


def _validate_operational(operational, label, maximum_pairs):
    operational = _require_dict(operational, label)
    if operational.get("eligibility") != OPERATIONAL_ELIGIBILITY:
        raise RenderError("{} eligibility changed".format(label))
    eligible_counts = set()
    for metric in ("expanded_bdd_nodes", "image_time_seconds"):
        item = _require_dict(operational.get(metric), "{} {}".format(label, metric))
        count = _require_int(item.get("eligible_pair_count"), "{} {} count".format(label, metric), 1)
        if count > maximum_pairs:
            raise RenderError("{} {} count exceeds its trace denominator".format(label, metric))
        eligible_counts.add(count)
        comparisons = [
            _require_int(item.get(field), "{} {} {}".format(label, metric, field))
            for field in ("cap_lower", "equal", "cap_higher")
        ]
        if sum(comparisons) != count:
            raise RenderError("{} {} comparisons do not partition pairs".format(label, metric))
        cap_total = _require_number(item.get("cap_total"), "{} {} cap total".format(label, metric), 0)
        exact_total = _require_number(item.get("exact_total"), "{} {} exact total".format(label, metric), 0)
        ratio = _require_number(item.get("cap_over_exact"), "{} {} ratio".format(label, metric), 0)
        if exact_total <= 0 or not math.isclose(ratio, cap_total / exact_total, rel_tol=1e-14, abs_tol=0):
            raise RenderError("{} {} ratio is inconsistent".format(label, metric))
    if len(eligible_counts) != 1:
        raise RenderError("{} metric denominators disagree".format(label))
    return eligible_counts.pop()


def _validate_fraction(item, label):
    item = _require_dict(item, label)
    numerator = _require_int(abs(item.get("numerator")), "{} |numerator|".format(label)) if type(item.get("numerator")) is int else None
    if numerator is None:
        raise RenderError("{} numerator must be an integer".format(label))
    denominator = _require_int(item.get("denominator"), "{} denominator".format(label), 1)
    value = _require_number(item.get("value"), "{} value".format(label))
    if not math.isclose(value, item["numerator"] / denominator, rel_tol=1e-14, abs_tol=1e-18):
        raise RenderError("{} decimal value is inconsistent".format(label))
    return Fraction(item["numerator"], denominator)


def _validate_operational_conservation(overall, strata, label):
    for metric in ("expanded_bdd_nodes", "image_time_seconds"):
        whole = overall[metric]
        parts = [stratum[metric] for stratum in strata]
        for field in ("eligible_pair_count", "cap_lower", "equal", "cap_higher"):
            if whole[field] != sum(part[field] for part in parts):
                raise RenderError(
                    "{} {} {} does not conserve across strata".format(label, metric, field)
                )
        for field in ("cap_total", "exact_total"):
            if not math.isclose(
                whole[field],
                math.fsum(part[field] for part in parts),
                rel_tol=1e-14,
                abs_tol=1e-12,
            ):
                raise RenderError(
                    "{} {} {} does not conserve across strata".format(label, metric, field)
                )


def _validate_scope(scope, key, task_count):
    scope = _require_dict(scope, key)
    if scope.get("role") != SCOPE_ROLES[key]:
        raise RenderError("{} role changed".format(key))
    population = _require_dict(scope.get("population"), "{} population".format(key))
    if population != {"domains": 46, "tasks": task_count}:
        raise RenderError("{} population changed".format(key))
    paired = _require_dict(scope.get("paired_trace_summary"), "{} paired traces".format(key))
    pair_count = _require_int(paired.get("complete_certified_pairs"), "{} trace pairs".format(key), 1)
    if paired.get("identical_raw_pool_pairs") != pair_count:
        raise RenderError("{} raw-pool identity invariant failed".format(key))
    _validate_coverage(paired.get("coverage"), pair_count, "{} paired coverage".format(key))
    paired_operational = _require_dict(
        paired.get("operational"),
        "{} paired operational".format(key),
    )
    _validate_operational(
        paired_operational,
        "{} paired operational".format(key),
        pair_count,
    )

    strata = _require_dict(scope.get("trace_strata"), "{} strata".format(key))
    if set(strata) != {"finite_cap", "exact_endpoint"}:
        raise RenderError("{} trace strata changed".format(key))
    finite = _require_dict(strata.get("finite_cap"), "{} finite stratum".format(key))
    exact = _require_dict(strata.get("exact_endpoint"), "{} exact stratum".format(key))
    if finite.get("definition") != FINITE_CAP_DEFINITION:
        raise RenderError("{} finite stratum definition changed".format(key))
    if exact.get("definition") != EXACT_ENDPOINT_DEFINITION:
        raise RenderError("{} exact stratum definition changed".format(key))
    finite_count = _require_int(finite.get("trace_pairs"), "{} finite pairs".format(key), 1)
    exact_count = _require_int(exact.get("trace_pairs"), "{} exact pairs".format(key), 1)
    if finite_count + exact_count != pair_count:
        raise RenderError("{} trace strata do not partition paired traces".format(key))
    stratum_operationals = []
    for name, stratum, count in (("finite", finite, finite_count), ("exact", exact, exact_count)):
        _validate_coverage(stratum.get("coverage"), count, "{} {} coverage".format(key, name))
        operational = _require_dict(
            stratum.get("operational"),
            "{} {} operational".format(key, name),
        )
        _validate_operational(
            operational,
            "{} {} operational".format(key, name),
            count,
        )
        stratum_operationals.append(operational)
    _validate_operational_conservation(
        paired_operational,
        stratum_operationals,
        key,
    )

    transform = _require_dict(finite.get("selected_transform"), "{} finite transform".format(key))
    _validate_summary(
        transform.get("selected_raw_W"),
        "{} raw W".format(key),
        expected_count=finite_count,
    )
    if transform.get("selected_count") != finite_count:
        raise RenderError("{} finite selected count changed".format(key))
    material = _require_dict(transform.get("material_transform"), "{} material transform".format(key))
    if not (
        material.get("definition") == MATERIAL_TRANSFORM_DEFINITION
        and material.get("checked") == finite_count
        and material.get("material") == finite_count
        and material.get("violations") == 0
        and material.get("invariant") is True
    ):
        raise RenderError("{} material transform invariant failed".format(key))
    universal = _require_dict(
        transform.get("cap_specific_universal_coefficient"),
        "{} universal coefficient".format(key),
    )
    if universal.get("formula") != "2*K*min(K,kappa+1)" or universal.get("K") != 8:
        raise RenderError("{} universal coefficient definition changed".format(key))
    universal_total = 0
    for entry in universal.get("counts", []):
        entry = _require_dict(entry, "{} universal coefficient entry".format(key))
        coefficient = _require_int(entry.get("coefficient"), "{} coefficient".format(key), 1)
        selected_count = _require_int(entry.get("selected_count"), "{} coefficient count".format(key), 1)
        caps = _require_dict(entry.get("selected_cap_counts"), "{} coefficient caps".format(key))
        if sum(_require_int(count, "{} cap count".format(key), 1) for count in caps.values()) != selected_count:
            raise RenderError("{} coefficient cap counts disagree".format(key))
        if any(2 * 8 * min(8, int(cap) + 1) != coefficient for cap in caps):
            raise RenderError("{} coefficient formula disagrees with selected caps".format(key))
        universal_total += selected_count
    if universal_total != finite_count:
        raise RenderError("{} coefficient counts do not cover finite selections".format(key))

    identity = _require_dict(exact.get("selected_identity"), "{} endpoint identity".format(key))
    if not (
        identity.get("checked") == exact_count
        and identity.get("selected_heuristic_identity_mismatches") == 0
        and identity.get("selected_heuristic_identity_invariant") is True
        and identity.get("transformed_vs_raw_identity_mismatches") == 0
        and identity.get("transformed_vs_raw_identity_invariant") is True
    ):
        raise RenderError("{} exact-endpoint identity invariant failed".format(key))

    initial_h = _require_dict(scope.get("selected_initial_h_on_non_dead_pairs"), "{} initial h".format(key))
    non_dead = _require_int(initial_h.get("non_dead_pairs"), "{} non-dead pairs".format(key), 1)
    relations = [
        _require_int(initial_h.get(field), "{} initial-h {}".format(key, field))
        for field in ("cap_strict_higher", "equal", "cap_lower")
    ]
    if sum(relations) != non_dead or relations[2] != 0 or initial_h.get("no_cap_lower_invariant") is not True:
        raise RenderError("{} initial-h invariant failed".format(key))

    coefficients = _require_dict(scope.get("selected_certificate_coefficient"), "{} coefficients".format(key))
    if not (
        coefficients.get("formula") == SELECTED_COEFFICIENT_FORMULA
        and coefficients.get("eligibility") == SELECTED_COEFFICIENT_ELIGIBILITY
    ):
        raise RenderError("{} certificate coefficient definition changed".format(key))
    by_selector = _require_dict(coefficients.get("by_selector"), "{} selector coefficients".format(key))
    if set(by_selector) != {selector for selector, _ in SELECTORS}:
        raise RenderError("{} coefficient selectors changed".format(key))
    for selector, _ in SELECTORS:
        _validate_summary(
            by_selector.get(selector),
            "{} {} coefficient".format(key, selector),
            expected_count=EXPECTED_SELECTOR_TRACE_COUNTS[key][selector],
        )

    lodo = _require_dict(scope.get("leave_one_domain_out"), "{} LODO".format(key))
    expected_estimands = {
        "coverage": COVERAGE_LODO_ESTIMAND,
        "expanded_bdd_nodes": NODE_LODO_ESTIMAND,
    }
    for metric in ("coverage", "expanded_bdd_nodes"):
        item = _require_dict(lodo.get(metric), "{} LODO {}".format(key, metric))
        if item.get("estimand") != expected_estimands[metric]:
            raise RenderError("{} LODO {} estimand changed".format(key, metric))
        if item.get("omitted_domain_replicates") != 46:
            raise RenderError("{} LODO {} replicate count changed".format(key, metric))
        _validate_fraction(item.get("base"), "{} LODO {} base".format(key, metric))
        minimum = _validate_fraction(
            item.get("minimum", {}).get("ratio"),
            "{} LODO {} min".format(key, metric),
        )
        maximum = _validate_fraction(
            item.get("maximum", {}).get("ratio"),
            "{} LODO {} max".format(key, metric),
        )
        width = _validate_fraction(
            item.get("range_width"),
            "{} LODO {} width".format(key, metric),
        )
        if minimum > maximum or width != maximum - minimum:
            raise RenderError("{} LODO {} range is inconsistent".format(key, metric))

    partitions = _require_dict(scope.get("partition_ratio_max"), "{} partitions".format(key))
    if partitions.get("eligibility") != PARTITION_ELIGIBILITY:
        raise RenderError("{} partition eligibility changed".format(key))
    by_config = _require_dict(partitions.get("by_config"), "{} partition configs".format(key))
    if set(by_config) != {config for config, _ in CONFIG_LABELS}:
        raise RenderError("{} partition configurations changed".format(key))
    for config, _ in CONFIG_LABELS:
        _validate_summary(
            by_config.get(config),
            "{} {} partition ratio".format(key, config),
            allow_empty=(config == "blind_fw"),
        )


def validate_analysis(analysis):
    analysis = _require_dict(analysis, "analysis")
    expected_top = {
        "schema",
        "analysis_protocol",
        "role",
        "claim_policy",
        "input_binding",
        "diagnostics",
        "inference",
    }
    if set(analysis) != expected_top:
        raise RenderError("analysis top-level schema changed")
    if analysis.get("schema") != ANALYSIS_SCHEMA or analysis.get("analysis_protocol") != ANALYSIS_PROTOCOL:
        raise RenderError("analysis schema/protocol changed")
    if analysis.get("role") != ROLE:
        raise RenderError("analysis role changed")
    claims = _require_dict(analysis.get("claim_policy"), "claim policy")
    if not (
        claims.get("status") == "post-hoc"
        and claims.get("guidance") == CLAIM_GUIDANCE
        and claims.get("inference") == NO_INFERENCE_POLICY
        and claims.get("confirmatory_or_prospective") is False
    ):
        raise RenderError("post-hoc claim policy changed")
    inference = _require_dict(analysis.get("inference"), "inference")
    if not (
        inference.get("confidence_intervals") is None
        and inference.get("hypothesis_tests") is None
        and inference.get("p_values") is None
        and inference.get("population_generalization") is False
        and inference.get("policy") == NO_INFERENCE_POLICY
    ):
        raise RenderError("no-inference policy changed")

    binding = _require_dict(analysis.get("input_binding"), "input binding")
    _require_sha256(
        binding.get("properties_canonical_sha256"),
        "properties digest",
        EXPECTED_PROPERTIES_CANONICAL_SHA256,
    )
    _require_sha256(
        binding.get("record_schema_manifest_sha256"),
        "record schema digest",
        EXPECTED_RECORD_SCHEMA_MANIFEST_SHA256,
    )
    prospective = _require_dict(binding.get("prospective_analysis_artifact"), "prospective binding")
    if prospective.get("schema") != EXPECTED_PROSPECTIVE_SCHEMA:
        raise RenderError("prospective schema binding changed")
    _require_sha256(
        prospective.get("sha256"),
        "prospective artifact digest",
        EXPECTED_PROSPECTIVE_ARTIFACT_SHA256,
    )
    execution = _require_dict(binding.get("execution"), "execution binding")
    expected_execution = {
        "protocol": EXPECTED_PROTOCOL,
        "analysis_protocol": EXPECTED_SOURCE_ANALYSIS_PROTOCOL,
        "protocol_revision": EXPECTED_PROTOCOL_REVISION,
        "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
        "primary_task_manifest_sha256": EXPECTED_PRIMARY_TASK_MANIFEST_SHA256,
        "development_task_manifest_sha256": EXPECTED_DEVELOPMENT_MANIFEST_SHA256,
        "option_matrix_sha256": EXPECTED_OPTION_MATRIX_SHA256,
        "cells": 6885,
    }
    for field, expected in expected_execution.items():
        if not _same(execution.get(field), expected):
            raise RenderError("execution binding {} changed".format(field))

    diagnostics = _require_dict(analysis.get("diagnostics"), "diagnostics")
    if set(diagnostics) != {item[0] for item in SCOPES}:
        raise RenderError("diagnostic scopes changed")
    for key, _, task_count in SCOPES:
        _validate_scope(diagnostics.get(key), key, task_count)


def _decimal(value, places=3):
    quantum = Decimal(1).scaleb(-places)
    rounded = Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP)
    result = format(rounded, "f")
    if "." in result:
        result = result.rstrip("0").rstrip(".")
    return result


def _stat(value):
    return "--" if value is None else _decimal(value)


def _tex_escape(value):
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
    }
    return "".join(replacements.get(character, character) for character in str(value))


def _macro(name, body):
    if MACRO_RE.fullmatch(name) is None:
        raise RenderError("invalid TeX macro name {}".format(name))
    return "\\newcommand{{\\{}}}{{{}}}".format(name, body)


def _rows_macro(name, rows):
    if not rows:
        raise RenderError("{} has no rows".format(name))
    row_break = " " + "\\" * 2 + "\n"
    return _macro(name, "%\n" + row_break.join(rows) + " " + "\\" * 2)


def render_tex(analysis):
    diagnostics = analysis["diagnostics"]
    lines = [
        "% Generated from the pinned post-hoc cap-grid review artifact.",
        "% Descriptive diagnostics only: no tests, intervals, or generalization.",
        _macro("CapPosthocAnalysisRole", "post-hoc theorem-guided descriptive"),
        _macro("CapPosthocInferencePolicy", "none"),
    ]

    trace_rows = []
    operational_rows = []
    primary_operational_strata_rows = []
    initial_h_rows = []
    coefficient_rows = []
    raw_width_rows = []
    universal_rows = []
    lodo_rows = []
    partition_rows = []
    for scope_key, scope_label, _ in SCOPES:
        scope = diagnostics[scope_key]
        for stratum_key, stratum_label in STRATA:
            stratum = scope["trace_strata"][stratum_key]
            coverage = stratum["coverage"]
            trace_rows.append(
                "{} & {} & {} & {} & {} & {} & {}".format(
                    scope_label,
                    stratum_label,
                    stratum["trace_pairs"],
                    coverage["cap_wins"],
                    coverage["cap_losses"],
                    coverage["both_solved"],
                    coverage["both_unsolved"],
                )
            )
            for metric_key, metric_label in (
                ("expanded_bdd_nodes", "BDD nodes"),
                ("image_time_seconds", "Image time (s)"),
            ):
                metric = stratum["operational"][metric_key]
                operational_rows.append(
                    "{} & {} & {} & {} & {} & {} & {} & {} & {} & {}".format(
                        scope_label,
                        stratum_label,
                        metric_label,
                        metric["eligible_pair_count"],
                        _decimal(metric["cap_total"]),
                        _decimal(metric["exact_total"]),
                        _decimal(metric["cap_over_exact"]),
                        metric["cap_lower"],
                        metric["equal"],
                        metric["cap_higher"],
                    )
                )
            if scope_key == "primary":
                nodes = stratum["operational"]["expanded_bdd_nodes"]
                image_time = stratum["operational"]["image_time_seconds"]
                primary_operational_strata_rows.append(
                    "{} & {} & {} & {}/{}/{} & {}".format(
                        stratum_label,
                        nodes["eligible_pair_count"],
                        _decimal(nodes["cap_over_exact"]),
                        nodes["cap_lower"],
                        nodes["equal"],
                        nodes["cap_higher"],
                        _decimal(image_time["cap_over_exact"]),
                    )
                )

        initial = scope["selected_initial_h_on_non_dead_pairs"]
        initial_h_rows.append(
            "{} & {} & {} & {} & {}".format(
                scope_label,
                initial["non_dead_pairs"],
                initial["cap_strict_higher"],
                initial["equal"],
                initial["cap_lower"],
            )
        )
        coefficients = scope["selected_certificate_coefficient"]["by_selector"]
        for selector_key, selector_label in SELECTORS:
            item = coefficients[selector_key]
            coefficient_rows.append(
                "{} & {} & {} & {} & {} & {} & {}".format(
                    scope_label,
                    selector_label,
                    item["count"],
                    _stat(item["minimum"]),
                    _stat(item["median"]),
                    _stat(item["nearest_rank_p95"]),
                    _stat(item["maximum"]),
                )
            )
        transform = scope["trace_strata"]["finite_cap"]["selected_transform"]
        raw_width = transform["selected_raw_W"]
        raw_width_rows.append(
            "{} & {} & {} & {} & {} & {}".format(
                scope_label,
                raw_width["count"],
                _stat(raw_width["minimum"]),
                _stat(raw_width["median"]),
                _stat(raw_width["nearest_rank_p95"]),
                _stat(raw_width["maximum"]),
            )
        )
        for entry in transform["cap_specific_universal_coefficient"]["counts"]:
            caps = ",".join(str(cap) for cap in sorted(map(int, entry["selected_cap_counts"])))
            universal_rows.append(
                "{} & {} & {} & {}".format(
                    scope_label,
                    entry["coefficient"],
                    entry["selected_count"],
                    caps,
                )
            )
        for metric_key, metric_label, multiplier in (
            ("coverage", "Coverage delta (pp)", 100),
            ("expanded_bdd_nodes", "Node ratio", 1),
        ):
            item = scope["leave_one_domain_out"][metric_key]
            minimum = item["minimum"]
            maximum = item["maximum"]
            lodo_rows.append(
                "{} & {} & {} & {} ({}) & {} ({})".format(
                    scope_label,
                    metric_label,
                    _decimal(multiplier * item["base"]["value"]),
                    _decimal(multiplier * minimum["ratio"]["value"]),
                    _tex_escape(", ".join(minimum["omitted_domains"])),
                    _decimal(multiplier * maximum["ratio"]["value"]),
                    _tex_escape(", ".join(maximum["omitted_domains"])),
                )
            )
        partitions = scope["partition_ratio_max"]["by_config"]
        for config_key, config_label in CONFIG_LABELS:
            item = partitions[config_key]
            partition_rows.append(
                "{} & {} & {} & {} & {} & {}".format(
                    scope_label,
                    config_label,
                    item["count"],
                    _stat(item["median"]),
                    _stat(item["nearest_rank_p95"]),
                    _stat(item["maximum"]),
                )
            )

    primary = diagnostics["primary"]
    all_tasks = diagnostics["all_tasks"]
    primary_initial = primary["selected_initial_h_on_non_dead_pairs"]
    primary_raw_width = primary["trace_strata"]["finite_cap"][
        "selected_transform"
    ]["selected_raw_W"]
    primary_lodo = primary["leave_one_domain_out"]
    primary_partitions = primary["partition_ratio_max"]["by_config"]
    lines.extend(
        [
            _macro("CapPosthocPrimaryFinitePairs", str(primary["trace_strata"]["finite_cap"]["trace_pairs"])),
            _macro("CapPosthocPrimaryExactEndpointPairs", str(primary["trace_strata"]["exact_endpoint"]["trace_pairs"])),
            _macro("CapPosthocAllFinitePairs", str(all_tasks["trace_strata"]["finite_cap"]["trace_pairs"])),
            _macro("CapPosthocAllExactEndpointPairs", str(all_tasks["trace_strata"]["exact_endpoint"]["trace_pairs"])),
            _macro("CapPosthocPrimaryExactIdentityMismatches", "0"),
            _macro("CapPosthocAllExactIdentityMismatches", "0"),
            _macro("CapPosthocPrimaryMaterialTransformViolations", "0"),
            _macro("CapPosthocAllMaterialTransformViolations", "0"),
            _macro(
                "CapPosthocPrimaryInitialNondeadPairs",
                str(primary_initial["non_dead_pairs"]),
            ),
            _macro(
                "CapPosthocPrimaryInitialHigher",
                str(primary_initial["cap_strict_higher"]),
            ),
            _macro(
                "CapPosthocPrimaryInitialEqual", str(primary_initial["equal"])
            ),
            _macro(
                "CapPosthocPrimaryInitialLower", str(primary_initial["cap_lower"])
            ),
            _macro(
                "CapPosthocPrimaryRawWidthMinimum",
                _stat(primary_raw_width["minimum"]),
            ),
            _macro(
                "CapPosthocPrimaryRawWidthMedian",
                _stat(primary_raw_width["median"]),
            ),
            _macro(
                "CapPosthocPrimaryRawWidthMaximum",
                _stat(primary_raw_width["maximum"]),
            ),
            _macro(
                "CapPosthocPrimaryCoverageLodoMinimumPoints",
                _decimal(100 * primary_lodo["coverage"]["minimum"]["ratio"]["value"]),
            ),
            _macro(
                "CapPosthocPrimaryCoverageLodoMaximumPoints",
                _decimal(100 * primary_lodo["coverage"]["maximum"]["ratio"]["value"]),
            ),
            _macro(
                "CapPosthocPrimaryNodeLodoMinimumRatio",
                _decimal(primary_lodo["expanded_bdd_nodes"]["minimum"]["ratio"]["value"]),
            ),
            _macro(
                "CapPosthocPrimaryNodeLodoMaximumRatio",
                _decimal(primary_lodo["expanded_bdd_nodes"]["maximum"]["ratio"]["value"]),
            ),
            _macro(
                "CapPosthocPrimaryExactPartitionPninetyfive",
                _stat(primary_partitions["pdb_selector_k8"]["nearest_rank_p95"]),
            ),
            _macro(
                "CapPosthocPrimaryCapPartitionPninetyfive",
                _stat(primary_partitions["pdb_cap_grid_k8"]["nearest_rank_p95"]),
            ),
            _rows_macro("CapPosthocTraceStrataRows", trace_rows),
            _rows_macro("CapPosthocOperationalRows", operational_rows),
            _rows_macro(
                "CapPosthocPrimaryOperationalStrataRows",
                primary_operational_strata_rows,
            ),
            _rows_macro("CapPosthocInitialHRows", initial_h_rows),
            _rows_macro("CapPosthocCertificateCoefficientRows", coefficient_rows),
            _rows_macro("CapPosthocRawWidthRows", raw_width_rows),
            _rows_macro("CapPosthocUniversalCoefficientRows", universal_rows),
            _rows_macro("CapPosthocLeaveOneDomainOutRows", lodo_rows),
            _rows_macro("CapPosthocPartitionRatioRows", partition_rows),
        ]
    )
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX is unexpectedly large")
    return raw


def _atomic_write(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise RenderError("refusing to replace symlink {}".format(path))
    descriptor, temporary = tempfile.mkstemp(prefix=".{}-".format(path.name), dir=str(path.parent))
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
    assert _decimal(0.8843855) == "0.884"
    assert _decimal(48.0) == "48"
    assert _tex_escape("transport_opt") == r"transport\_opt"
    assert _macro("ValidName", "x") == r"\newcommand{\ValidName}{x}"

    analysis = load_analysis(DEFAULT_ANALYSIS)

    def expect_rejected(candidate, label):
        try:
            validate_analysis(candidate)
        except RenderError:
            return
        raise AssertionError("validator accepted {}".format(label))

    semantic_mutations = (
        (("diagnostics", "primary", "role"), "changed-role"),
        (
            ("diagnostics", "primary", "trace_strata", "finite_cap", "definition"),
            "changed-definition",
        ),
        (
            ("diagnostics", "primary", "paired_trace_summary", "operational", "eligibility"),
            "changed-eligibility",
        ),
        (
            ("diagnostics", "primary", "leave_one_domain_out", "coverage", "estimand"),
            "changed-estimand",
        ),
        (
            ("diagnostics", "primary", "partition_ratio_max", "eligibility"),
            "changed-eligibility",
        ),
    )
    for path, value in semantic_mutations:
        candidate = copy.deepcopy(analysis)
        target = candidate
        for field in path[:-1]:
            target = target[field]
        target[path[-1]] = value
        expect_rejected(candidate, ".".join(path))

    candidate = copy.deepcopy(analysis)
    candidate["diagnostics"]["primary"]["leave_one_domain_out"]["coverage"][
        "range_width"
    ] = {"numerator": 0, "denominator": 1, "value": 0.0}
    expect_rejected(candidate, "inconsistent LODO range width")

    candidate = copy.deepcopy(analysis)
    candidate["diagnostics"]["primary"]["selected_certificate_coefficient"][
        "by_selector"
    ]["pdb_selector_k8"]["count"] -= 1
    expect_rejected(candidate, "coefficient/trace denominator mismatch")

    candidate = copy.deepcopy(analysis)
    item = candidate["diagnostics"]["primary"]["trace_strata"]["finite_cap"][
        "operational"
    ]["expanded_bdd_nodes"]
    item["cap_total"] += 1
    item["cap_over_exact"] = item["cap_total"] / item["exact_total"]
    expect_rejected(candidate, "nonconserving operational stratum")

    candidate = copy.deepcopy(analysis)
    item = candidate["diagnostics"]["primary"]["trace_strata"]["finite_cap"][
        "operational"
    ]["image_time_seconds"]
    item["eligible_pair_count"] += 1
    item["equal"] += 1
    expect_rejected(candidate, "node/image denominator mismatch")
    print("self-test passed")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write the generated TeX")
    mode.add_argument("--check", action="store_true", help="verify generated TeX byte-for-byte")
    mode.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    analysis = load_analysis(args.analysis)
    raw = render_tex(analysis)
    if args.check:
        if read_regular(args.output, MAX_TEX_BYTES) != raw:
            raise RenderError("generated TeX is stale")
        print("verified {}".format(args.output))
    else:
        _atomic_write(args.output, raw)
        print("wrote {}".format(args.output))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RenderError as err:
        print("error: {}".format(err), file=os.sys.stderr)
        raise SystemExit(2)
