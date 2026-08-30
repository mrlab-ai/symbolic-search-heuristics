#!/usr/bin/env python3
"""Fail-closed analysis of the prospective certificate holdout."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_comparison as Base
import analyze_pdb_profile_predictors as Predictor
import analyze_pdb_profile_semantic_union as Semantic
import pdb_profile_certificate_holdout_protocol as P


class CertificateHoldoutAnalysisError(RuntimeError):
    pass


SCHEMA = "symbolic-search-heuristics/pdb-profile-certificate-holdout/v1"
LAB_SLURM_ERROR = "output-to-slurm.err"


def _canonical(value) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise CertificateHoldoutAnalysisError(
            "analysis is not finite canonical JSON"
        ) from err


def _fraction_record(value):
    if value is None:
        return None
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }


def _ratio(numerator: int, denominator: int):
    if denominator == 0:
        return None
    return _fraction_record(Fraction(numerator, denominator))


def _exact_fraction(record, label):
    if record is None:
        return None
    if not isinstance(record, dict):
        raise CertificateHoldoutAnalysisError(
            "{} is not a fraction record".format(label)
        )
    numerator = record.get("numerator")
    denominator = record.get("denominator")
    if (
        type(numerator) is not int
        or type(denominator) is not int
        or denominator <= 0
    ):
        raise CertificateHoldoutAnalysisError(
            "{} is not an exact fraction".format(label)
        )
    value = Fraction(numerator, denominator)
    if (value.numerator, value.denominator) != (numerator, denominator):
        raise CertificateHoldoutAnalysisError(
            "{} is not reduced".format(label)
        )
    return value


def _manifest_digest(tasks) -> str:
    raw = "".join(
        "{}:{}\n".format(domain, problem)
        for domain, problem in sorted(tasks)
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _terminal_class(record):
    errors = record.get("unexplained_errors")
    if errors not in (None, [], [LAB_SLURM_ERROR]):
        raise CertificateHoldoutAnalysisError(
            "cell carries unexplained parser or execution errors"
        )
    try:
        return Semantic._terminal_class(record)
    except Semantic.SemanticUnionAnalysisError as err:
        raise CertificateHoldoutAnalysisError(str(err)) from err


def _validate_stream_contract(record, outcome_class, label):
    expansion_present = record.get("wbh_expansion_profile_present") is True
    expansion_certified = (
        record.get("wbh_expansion_profile_certified") is True
    )
    expansion_complete = record.get("wbh_expansion_profile_complete") is True
    profile_present = record.get("wbh_profile_present") is True
    profile_prefix = record.get("wbh_profile_prefix_certified") is True
    profile_complete = record.get("wbh_profile_complete") is True
    selector_present = record.get("pdb_profile_selector_present") is True
    selector_prefix = (
        record.get("pdb_profile_selector_prefix_certified") is True
    )
    is_pdb = label in P.PDB_LABELS

    if outcome_class == "presearch":
        if expansion_present or profile_present or selector_present:
            raise CertificateHoldoutAnalysisError(
                "pre-search outcome unexpectedly emitted search evidence"
            )
        if record.get("construction_completed") is not None:
            raise CertificateHoldoutAnalysisError(
                "pre-search outcome unexpectedly reached construction"
            )
        return

    if expansion_present and not expansion_certified:
        raise CertificateHoldoutAnalysisError(
            "present schema-v2 stream is malformed"
        )
    if profile_present and not profile_prefix:
        raise CertificateHoldoutAnalysisError(
            "present profile stream is malformed"
        )
    if is_pdb and selector_present and not selector_prefix:
        raise CertificateHoldoutAnalysisError(
            "present selector stream is malformed"
        )
    if not is_pdb and selector_present:
        raise CertificateHoldoutAnalysisError(
            "profiled blind cell emitted a PDB selector stream"
        )

    if outcome_class == "solved":
        common = (
            expansion_present,
            expansion_certified,
            expansion_complete,
            record.get("wbh_solved_summary_certified") is True,
            profile_present,
            profile_prefix,
            profile_complete,
            record.get("wbh_profile_certified") is True,
        )
        if not all(common) or not isinstance(
            record.get("wbh_profile_done"), dict
        ):
            raise CertificateHoldoutAnalysisError(
                "solved cell lacks complete certified search evidence"
            )
        if is_pdb and not all((
            selector_present,
            selector_prefix,
            record.get("pdb_profile_selector_trace_complete") is True,
            record.get("pdb_profile_selector_trace_certified") is True,
            record.get("construction_completed") is True,
        )):
            raise CertificateHoldoutAnalysisError(
                "solved PDB cell lacks complete selector evidence"
            )
    elif outcome_class == "search_terminal":
        if not all((
            expansion_present,
            expansion_certified,
            expansion_complete,
            profile_present,
            profile_prefix,
            profile_complete,
        )):
            raise CertificateHoldoutAnalysisError(
                "terminal search outcome lacks complete profile streams"
            )
    elif outcome_class not in {"search_resource", "solved_resource"}:
        raise CertificateHoldoutAnalysisError(
            "internal outcome taxonomy error"
        )

    if is_pdb and record.get("construction_completed") is True:
        if not all((
            record.get("pdb_profile_selector_trace_complete") is True,
            record.get("pdb_profile_selector_trace_certified") is True,
            isinstance(record.get("wbh_profile_heuristic_profile"), dict),
        )):
            raise CertificateHoldoutAnalysisError(
                "completed PDB construction lacks certified metadata"
            )


def validate_matrix(records, expected_tasks=P.COHORT_TASKS):
    expected_cells = expected_tasks * P.CONFIG_COUNT
    if len(records) != expected_cells:
        raise CertificateHoldoutAnalysisError(
            "matrix has {} records, expected {}".format(
                len(records), expected_cells
            )
        )
    fixed = {
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "cohort_role": P.COHORT_ROLE,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "cohort_task_count": P.COHORT_TASKS,
        "cohort_domain_count": P.COHORT_DOMAINS,
        "config_count": P.CONFIG_COUNT,
        "declared_run_count": P.CELL_COUNT,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "source_protocol": P.Source.PROTOCOL,
        "planner_revision": P.PLANNER_REVISION,
        "planner_binary_sha256": P.PLANNER_BINARY_SHA256,
        "preprocess_binary_sha256": P.PREPROCESS_BINARY_SHA256,
        "planner_preprocess_sha256": P.PREPROCESS_BINARY_SHA256,
        "required_lab_version": P.REQUIRED_LAB_VERSION,
        "planner_time_limit": P.TIME_LIMIT_SECONDS,
        "planner_memory_limit": P.MEMORY_LIMIT_MIB,
        "external_validation_requested": False,
        "slurm_partition": "fat",
        "array_throttle": 0,
    }
    expected_driver_options = [
        "--overall-time-limit",
        "{}s".format(P.TIME_LIMIT_SECONDS),
        "--overall-memory-limit",
        "{}M".format(P.MEMORY_LIMIT_MIB),
        "--build",
        "release_no_lp",
    ]
    matrix = {}
    tasks = set()
    outcome_classes = {}
    for record in records:
        label = record.get("algorithm")
        domain = record.get("domain")
        problem = record.get("problem")
        if label not in P.LABELS or not all(
            isinstance(value, str) and value
            for value in (domain, problem)
        ):
            raise CertificateHoldoutAnalysisError(
                "record has an invalid cell identity"
            )
        task = (domain, problem)
        key = (label, task)
        if key in matrix:
            raise CertificateHoldoutAnalysisError(
                "matrix contains a duplicate cell"
            )
        for field, expected in fixed.items():
            actual = record.get(field)
            normalized_time = (
                field == "planner_time_limit"
                and type(actual) is float
                and actual.is_integer()
                and int(actual) == expected
            )
            if not normalized_time and (
                actual != expected or type(actual) is not type(expected)
            ):
                raise CertificateHoldoutAnalysisError(
                    "cell changed fixed field {}".format(field)
                )
        if record.get("id") != [label, domain, problem]:
            raise CertificateHoldoutAnalysisError(
                "cell id differs from its matrix identity"
            )
        if record.get("component_options") != ["--search", P.SEARCHES[label]]:
            raise CertificateHoldoutAnalysisError(
                "cell component options differ from its label"
            )
        if record.get("driver_options") != expected_driver_options:
            raise CertificateHoldoutAnalysisError(
                "cell driver options changed"
            )
        if record.get("build_options") != list(P.BUILD_OPTIONS):
            raise CertificateHoldoutAnalysisError(
                "cell build options changed"
            )
        for field in ("local_revision", "global_revision"):
            if record.get(field) != P.PLANNER_REVISION:
                raise CertificateHoldoutAnalysisError(
                    "cell changed {}".format(field)
                )
        outcome_class = _terminal_class(record)
        _validate_stream_contract(record, outcome_class, label)
        if "wbh_profile_expected" not in record:
            if outcome_class != "presearch":
                raise CertificateHoldoutAnalysisError(
                    "search cell lacks its profile parser contract"
                )
        elif record.get("wbh_profile_expected") is not True:
            raise CertificateHoldoutAnalysisError(
                "cell has the wrong profile expectation"
            )
        matrix[key] = record
        outcome_classes[key] = outcome_class
        tasks.add(task)

    tasks = sorted(tasks)
    if len(tasks) != expected_tasks:
        raise CertificateHoldoutAnalysisError("task count changed")
    for task in tasks:
        if any((label, task) not in matrix for label in P.LABELS):
            raise CertificateHoldoutAnalysisError("matrix is incomplete")
        solved_costs = {
            matrix[(label, task)].get("solution_cost")
            for label in P.LABELS
            if matrix[(label, task)].get("coverage") == 1
        }
        if any(type(cost) is not int or cost < 0 for cost in solved_costs):
            raise CertificateHoldoutAnalysisError(
                "solved cell has an invalid cost"
            )
        if len(solved_costs) > 1:
            raise CertificateHoldoutAnalysisError(
                "configurations disagree on solution cost"
            )
    if expected_tasks == P.COHORT_TASKS:
        if _manifest_digest(tasks) != P.COHORT_MANIFEST_SHA256:
            raise CertificateHoldoutAnalysisError("task manifest changed")
        if len({domain for domain, _ in tasks}) != P.COHORT_DOMAINS:
            raise CertificateHoldoutAnalysisError("domain count changed")
    return matrix, tasks, outcome_classes


def _certificate_observation(record, task, label):
    if record.get("coverage") != 1:
        return "unsolved", None
    required = (
        "wbh_solved_summary_certified",
        "wbh_expansion_profile_complete",
        "wbh_expansion_profile_certified",
        "wbh_profile_complete",
        "wbh_profile_certified",
        "pdb_profile_selector_trace_certified",
    )
    if any(record.get(field) is not True for field in required):
        return "incomplete_profile", None
    try:
        effort, union_effort = Semantic._validate_solved_measurement(record)
    except Semantic.SemanticUnionAnalysisError as err:
        raise CertificateHoldoutAnalysisError(str(err)) from err
    if union_effort == 0:
        return "zero_union_effort", None

    selected = record.get("pdb_profile_selector_selected")
    heuristic = record.get("wbh_profile_heuristic_profile")
    state_bits = record.get("wbh_profile_state_bits")
    if (
        not isinstance(selected, dict)
        or not isinstance(heuristic, dict)
        or type(state_bits) is not int
        or state_bits < 1
    ):
        raise CertificateHoldoutAnalysisError(
            "eligible cell lacks selected heuristic evidence"
        )
    try:
        quality = Predictor._quality_key(selected)
    except Predictor.PredictorAnalysisError as err:
        raise CertificateHoldoutAnalysisError(str(err)) from err

    add_nodes = heuristic.get("add_nodes")
    terminals = heuristic.get("num_terminals")
    values = heuristic.get("num_values")
    width = heuristic.get("cofactor_width")
    residuals = heuristic.get("cofactor_counts")
    if (
        any(type(value) is not int for value in (
            add_nodes, terminals, values, width
        ))
        or add_nodes < 0
        or terminals < 1
        or values < 1
        or width < 1
        or not isinstance(residuals, list)
        or len(residuals) != state_bits + 1
        or any(type(value) is not int or value < 1 for value in residuals)
        or max(residuals) != width
    ):
        raise CertificateHoldoutAnalysisError(
            "eligible heuristic profile is invalid"
        )
    total_add = add_nodes + terminals
    if (
        selected.get("cofactor_width") != width
        or selected.get("width_upper_bound") != total_add
        or record.get("add_nodes") != add_nodes
        or record.get("num_terminals") != terminals
        or record.get("num_values") != values
        or record.get("width_upper_bound") != total_add
    ):
        raise CertificateHoldoutAnalysisError(
            "selector, profile and schema-v2 heuristic identities differ"
        )
    for field, expected in (
        ("add_nodes", add_nodes),
        ("num_terminals", terminals),
        ("transformed_num_values", values),
    ):
        if field in selected and selected[field] != expected:
            raise CertificateHoldoutAnalysisError(
                "selector {} disagrees with the profile".format(field)
            )

    layers = {
        layer["g"]: layer
        for layer in record["wbh_profile_layer_profiles"]
    }
    expansions = {
        item["g"]: item for item in record["wbh_expansion_profile"]
    }
    if set(layers) != set(expansions):
        raise CertificateHoldoutAnalysisError(
            "layer and expansion profiles cover different g values"
        )
    profile_bound = 0
    width_bound = 0
    add_bound = 0
    for g in sorted(layers):
        layer = layers[g]
        active = expansions[g]
        counts = layer.get("cofactor_counts")
        active_values = active.get("active_value_count")
        if (
            not isinstance(counts, list)
            or len(counts) != state_bits + 1
            or any(type(value) is not int or value < 1 for value in counts)
            or max(counts) != layer.get("cofactor_width")
            or type(active_values) is not int
            or active_values < 1
            or active.get("buckets") != active_values
            or active.get("pieces") != active_values
        ):
            raise CertificateHoldoutAnalysisError(
                "eligible layer profile is invalid"
            )
        cut_product = sum(
            left * right
            for left, right in zip(counts[:-1], residuals[:-1])
        )
        width_relaxation = width * sum(counts[:-1])
        bdd_nodes = layer["bdd_nodes"]
        add_apply = 2 * (add_nodes + 1) * bdd_nodes + add_nodes
        if cut_product > width_relaxation:
            raise CertificateHoldoutAnalysisError(
                "profile product exceeds its width relaxation"
            )
        profile_bound += active_values * cut_product
        width_bound += active_values * width_relaxation
        add_bound += active_values * add_apply
    if any(
        effort > bound for bound in (profile_bound, width_bound, add_bound)
    ):
        raise CertificateHoldoutAnalysisError(
            "measured effort exceeds a theorem certificate"
        )
    expanded_states = record.get("expanded_states")
    if (
        type(expanded_states) not in (int, float)
        or isinstance(expanded_states, bool)
        or not math.isfinite(expanded_states)
        or expanded_states < 0
    ):
        raise CertificateHoldoutAnalysisError(
            "eligible cell has invalid expanded-state count"
        )
    try:
        semantic_id = Predictor._semantic_id(selected, heuristic, quality)
    except Predictor.PredictorAnalysisError as err:
        raise CertificateHoldoutAnalysisError(str(err)) from err
    return "eligible", {
        "domain": task[0],
        "problem": task[1],
        "task": task,
        "config": label,
        "configs": [label],
        "semantic_id": semantic_id,
        "cofactor_width": width,
        "total_add_nodes": total_add,
        "finite_values": values,
        "expanded_states": expanded_states,
        "actual_effort": effort,
        "semantic_union_effort": union_effort,
        "B_profile": profile_bound,
        "B_width": width_bound,
        "B_add": add_bound,
        "R_profile": Fraction(profile_bound, union_effort),
        "R_width": Fraction(width_bound, union_effort),
        "R_add": Fraction(add_bound, union_effort),
        "_quality": quality,
        "_fragmentation": (effort, union_effort),
    }


def observations(matrix, tasks, labels=P.PDB_LABELS):
    statuses = Counter()
    grouped = defaultdict(dict)
    for task in tasks:
        for label in labels:
            status, observation = _certificate_observation(
                matrix[(label, task)], task, label
            )
            statuses[status] += 1
            if observation is None:
                continue
            semantic_id = observation["semantic_id"]
            previous = grouped[task].get(semantic_id)
            if previous is None:
                grouped[task][semantic_id] = observation
                continue
            invariant = (
                "cofactor_width",
                "total_add_nodes",
                "finite_values",
                "expanded_states",
                "actual_effort",
                "semantic_union_effort",
                "B_profile",
                "B_width",
                "B_add",
                "R_profile",
                "R_width",
                "R_add",
                "_quality",
                "_fragmentation",
            )
            if any(previous[field] != observation[field] for field in invariant):
                raise CertificateHoldoutAnalysisError(
                    "duplicate heuristic has different deterministic evidence"
                )
            previous["configs"].append(label)
    flat = [
        observation
        for task in tasks
        for observation in grouped.get(task, {}).values()
    ]
    return flat, grouped, dict(statuses)


def _shared(grouped, specs, target, domains):
    try:
        return Predictor._shared_pairwise_comparison(
            grouped, specs, target, domains
        )
    except Predictor.PredictorAnalysisError as err:
        raise CertificateHoldoutAnalysisError(str(err)) from err


def _summary_value(summary, predictor, field="equal_domain_macro"):
    try:
        record = summary["predictors"][predictor][field]
    except (KeyError, TypeError) as err:
        raise CertificateHoldoutAnalysisError(
            "comparison lacks {} {}".format(predictor, field)
        ) from err
    return _exact_fraction(record, "{} {}".format(predictor, field))


def _lodo(summary, predictor):
    try:
        records = summary["predictors"][predictor][
            "leave_one_domain_out"
        ]["values"]
    except (KeyError, TypeError) as err:
        raise CertificateHoldoutAnalysisError(
            "comparison lacks {} LODO values".format(predictor)
        ) from err
    if not isinstance(records, dict):
        raise CertificateHoldoutAnalysisError("LODO map is invalid")
    return {
        domain: _exact_fraction(record, "{} LODO {}".format(predictor, domain))
        for domain, record in records.items()
    }


def _support_ok(summary):
    support = summary.get("support") or {}
    return (
        type(support.get("eligible_domains")) is int
        and support["eligible_domains"] >= P.MIN_DOMAINS
        and type(support.get("tasks_with_comparable_pairs")) is int
        and support["tasks_with_comparable_pairs"]
        >= P.MIN_TASKS_WITH_COMPARABLE_PAIRS
    )


def _all_lodo_at_least(values, threshold):
    return (
        len(values) == P.COHORT_DOMAINS
        and all(value is not None and value >= threshold for value in values.values())
    )


def _all_lodo_advantage(left, right):
    return (
        set(left) == set(right)
        and len(left) == P.COHORT_DOMAINS
        and all(
            left[domain] is not None
            and right[domain] is not None
            and left[domain] > right[domain]
            for domain in left
        )
    )


def mechanism_gates(representation, profile_quality, guidance_states,
                    guidance_union):
    rp = _summary_value(representation, "profile")
    rw = _summary_value(representation, "width")
    ra = _summary_value(representation, "add")
    pq_profile = _summary_value(profile_quality, "profile")
    pq_quality = _summary_value(profile_quality, "quality")
    rp_lodo = _lodo(representation, "profile")
    rw_lodo = _lodo(representation, "width")
    ra_lodo = _lodo(representation, "add")
    pq_profile_lodo = _lodo(profile_quality, "profile")
    pq_quality_lodo = _lodo(profile_quality, "quality")

    useful_criteria = {
        "representation_support": _support_ok(representation),
        "profile_quality_support": _support_ok(profile_quality),
        "profile_macro_at_least_0_70": rp is not None and rp >= Fraction(7, 10),
        "profile_lodo_at_least_0_65": _all_lodo_at_least(
            rp_lodo, Fraction(13, 20)
        ),
        "profile_beats_quality_by_0_20": (
            pq_profile is not None
            and pq_quality is not None
            and pq_profile >= pq_quality + Fraction(1, 5)
        ),
        "profile_beats_quality_in_every_lodo": _all_lodo_advantage(
            pq_profile_lodo, pq_quality_lodo
        ),
        "profile_within_0_02_of_width": (
            rp is not None and rw is not None and rp >= rw - Fraction(1, 50)
        ),
        "profile_within_0_02_of_add": (
            rp is not None and ra is not None and rp >= ra - Fraction(1, 50)
        ),
    }
    sharper_criteria = {
        "representation_support": _support_ok(representation),
        "profile_macro_beats_width": (
            rp is not None and rw is not None and rp > rw
        ),
        "profile_macro_beats_add": (
            rp is not None and ra is not None and rp > ra
        ),
        "profile_beats_width_in_every_lodo": _all_lodo_advantage(
            rp_lodo, rw_lodo
        ),
        "profile_beats_add_in_every_lodo": _all_lodo_advantage(
            rp_lodo, ra_lodo
        ),
    }

    guidance_criteria = {}
    for name, summary in (
        ("states", guidance_states),
        ("union", guidance_union),
    ):
        quality = _summary_value(summary, "quality")
        profile = _summary_value(summary, "profile")
        quality_lodo = _lodo(summary, "quality")
        profile_lodo = _lodo(summary, "profile")
        guidance_criteria.update({
            "{}_support".format(name): _support_ok(summary),
            "{}_quality_macro_at_least_0_80".format(name): (
                quality is not None and quality >= Fraction(4, 5)
            ),
            "{}_quality_lodo_at_least_0_75".format(name): (
                _all_lodo_at_least(quality_lodo, Fraction(3, 4))
            ),
            "{}_quality_beats_profile_by_0_20".format(name): (
                quality is not None
                and profile is not None
                and quality >= profile + Fraction(1, 5)
            ),
            "{}_quality_beats_profile_in_every_lodo".format(name): (
                _all_lodo_advantage(quality_lodo, profile_lodo)
            ),
        })
    guidance_criteria.update({
        "fragmentation_profile_beats_quality_by_0_20": (
            pq_profile is not None
            and pq_quality is not None
            and pq_profile >= pq_quality + Fraction(1, 5)
        ),
        "fragmentation_profile_beats_quality_in_every_lodo": (
            _all_lodo_advantage(pq_profile_lodo, pq_quality_lodo)
        ),
    })
    return {
        "useful_fragmentation_certificate": {
            "pass": all(useful_criteria.values()),
            "criteria": useful_criteria,
        },
        "sharper_representation_predictor": {
            "pass": all(sharper_criteria.values()),
            "criteria": sharper_criteria,
            "material_macro_advantage_over_width": (
                rp is not None and rw is not None and rp >= rw + Fraction(1, 50)
            ),
            "material_macro_advantage_over_add": (
                rp is not None and ra is not None and rp >= ra + Fraction(1, 50)
            ),
        },
        "two_effect_separation": {
            "pass": all(guidance_criteria.values()),
            "criteria": guidance_criteria,
        },
    }


def _contrast_support(contrast):
    effort = contrast.get("conditional_effort") or {}
    rows = contrast.get("by_domain") or []
    return (
        type(effort.get("eligible_pairs")) is int
        and effort["eligible_pairs"] >= P.MIN_TASKS_WITH_COMPARABLE_PAIRS
        and sum(
            type(row) is dict and row.get("effort_eligible_pairs", 0) > 0
            for row in rows
        ) >= P.MIN_DOMAINS
    )


def _contrast_ratio(contrast):
    return _exact_fraction(
        (contrast.get("conditional_effort") or {}).get(
            "candidate_over_reference"
        ),
        "selector effort ratio",
    )


def selector_gates(contrasts):
    matched = contrasts["matched_width_vs_add"]
    cap_exact = contrasts["cap_width_vs_exact_width"]

    def pooled(items):
        candidate = sum(
            item["conditional_effort"]["candidate_total"] for item in items
        )
        reference = sum(
            item["conditional_effort"]["reference_total"] for item in items
        )
        return Fraction(candidate, reference) if reference else None

    matched_pooled = pooled(matched)
    cap_exact_pooled = pooled(cap_exact)
    matched_criteria = {
        "all_budgets_have_support": all(_contrast_support(item) for item in matched),
        "lower_effort_at_four_of_five_budgets": sum(
            _contrast_ratio(item) is not None and _contrast_ratio(item) < 1
            for item in matched
        ) >= 4,
        "pooled_ratio_at_most_0_98": (
            matched_pooled is not None
            and matched_pooled <= Fraction(49, 50)
        ),
        "no_budget_loses_more_than_two_coverage_tasks": all(
            item["coverage"]["candidate_minus_reference"] >= -2
            for item in matched
        ),
    }
    cap_exact_criteria = {
        "all_budgets_have_support": all(
            _contrast_support(item) for item in cap_exact
        ),
        "lower_effort_at_three_of_five_budgets": sum(
            _contrast_ratio(item) is not None and _contrast_ratio(item) < 1
            for item in cap_exact
        ) >= 3,
        "pooled_ratio_at_most_0_98": (
            cap_exact_pooled is not None
            and cap_exact_pooled <= Fraction(49, 50)
        ),
        "nonnegative_aggregate_coverage": sum(
            item["coverage"]["candidate_minus_reference"]
            for item in cap_exact
        ) >= 0,
        "no_budget_loses_more_than_two_coverage_tasks": all(
            item["coverage"]["candidate_minus_reference"] >= -2
            for item in cap_exact
        ),
    }
    return {
        "width_vs_matched_add": {
            "pass": all(matched_criteria.values()),
            "criteria": matched_criteria,
            "pooled_effort_ratio": _fraction_record(matched_pooled),
        },
        "cap_width_vs_exact_width": {
            "pass": all(cap_exact_criteria.values()),
            "criteria": cap_exact_criteria,
            "pooled_effort_ratio": _fraction_record(cap_exact_pooled),
        },
    }


def coverage_summary(matrix, tasks):
    rows = []
    for label in P.LABELS:
        solved = sum(matrix[(label, task)]["coverage"] for task in tasks)
        rows.append({
            "config": label,
            "tasks": len(tasks),
            "solved": solved,
            "coverage": _ratio(solved, len(tasks)),
        })
    return rows


def make_analysis(records):
    P.validate_protocol_without_archive()
    matrix, tasks, outcomes = validate_matrix(records)
    flat, grouped, statuses = observations(matrix, tasks)
    domains = {domain for domain, _ in tasks}
    representation = _shared(
        grouped,
        {
            "profile": ("R_profile", "same"),
            "width": ("R_width", "same"),
            "add": ("R_add", "same"),
        },
        "_fragmentation",
        domains,
    )
    profile_quality = _shared(
        grouped,
        {
            "profile": ("R_profile", "same"),
            "quality": ("_quality", "opposite"),
        },
        "_fragmentation",
        domains,
    )
    guidance_states = _shared(
        grouped,
        {
            "profile": ("R_profile", "same"),
            "quality": ("_quality", "opposite"),
        },
        "expanded_states",
        domains,
    )
    guidance_union = _shared(
        grouped,
        {
            "profile": ("R_profile", "same"),
            "quality": ("_quality", "opposite"),
        },
        "semantic_union_effort",
        domains,
    )
    absolute = _shared(
        grouped,
        {
            "profile": ("B_profile", "same"),
            "width": ("B_width", "same"),
            "add": ("B_add", "same"),
        },
        "actual_effort",
        domains,
    )
    try:
        contrasts = Predictor.selector_contrasts(matrix, tasks)
    except Predictor.PredictorAnalysisError as err:
        raise CertificateHoldoutAnalysisError(str(err)) from err

    public = []
    for item in flat:
        public.append({
            key: value
            for key, value in item.items()
            if not key.startswith("_")
            and key not in {"task", "R_profile", "R_width", "R_add"}
        } | {
            "R_profile": _fraction_record(item["R_profile"]),
            "R_width": _fraction_record(item["R_width"]),
            "R_add": _fraction_record(item["R_add"]),
            "quality": [
                item["_quality"][0],
                item["_quality"][1],
                _fraction_record(item["_quality"][2]),
                _fraction_record(item["_quality"][3]),
            ],
            "fragmentation": _ratio(*item["_fragmentation"]),
        })
    mechanism = {
        "representation_shared": representation,
        "profile_quality_shared": profile_quality,
        "guidance_expanded_states_shared": guidance_states,
        "guidance_union_effort_shared": guidance_union,
        "absolute_certificate_shared": absolute,
    }
    return {
        "schema": SCHEMA,
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "frozen_protocol_sha256": P.PROTOCOL_SHA256,
        "scope": {
            "tasks": len(tasks),
            "domains": len(domains),
            "configurations": P.CONFIG_COUNT,
            "cells": len(records),
            "minimum_domains": P.MIN_DOMAINS,
            "minimum_tasks_with_comparable_pairs": (
                P.MIN_TASKS_WITH_COMPARABLE_PAIRS
            ),
        },
        "terminal_outcomes": dict(Counter(outcomes.values())),
        "coverage": coverage_summary(matrix, tasks),
        "observation_status": statuses,
        "observations": public,
        "mechanism": mechanism,
        "mechanism_gates": mechanism_gates(
            representation, profile_quality, guidance_states, guidance_union
        ),
        "selector_contrasts": contrasts,
        "selector_gates": selector_gates(contrasts),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("properties", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    records = Base.load_records(args.properties)
    analysis = make_analysis(records)
    raw = _canonical(analysis) + b"\n"
    if args.output:
        args.output.write_bytes(raw)
    else:
        print(raw.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        Base.AnalysisError,
        P.ProtocolError,
        CertificateHoldoutAnalysisError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
