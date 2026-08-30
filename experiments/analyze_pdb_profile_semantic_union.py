#!/usr/bin/env python3
"""Fail-closed analysis of the corrected semantic-union measurement.

The thresholds and cohort are frozen in
``pdb_profile_semantic_union_protocol.md``.  This analyzer deliberately
reuses the predictor ordering machinery from the earlier, sealed analysis,
but validates the new 275 x 16 matrix independently because PDB runs now
contain terminal per-g semantic-union profiles.
"""

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
import exp_pdb_profile_semantic_union as E
import pdb_profile_semantic_union_protocol as P


class SemanticUnionAnalysisError(RuntimeError):
    pass


SCHEMA = "symbolic-search-heuristics/pdb-profile-semantic-union/v1"
LAB_SLURM_ERROR = "output-to-slurm.err"
PREDICTOR_SPECS = {
    "cofactor_width": ("cofactor_width", "same"),
    "total_add_nodes": ("total_add_nodes", "same"),
    "quality": ("_quality", "opposite"),
}


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
        raise SemanticUnionAnalysisError(
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
        raise SemanticUnionAnalysisError(
            "{} is not a fraction record".format(label)
        )
    numerator = record.get("numerator")
    denominator = record.get("denominator")
    if (
        type(numerator) is not int
        or type(denominator) is not int
        or denominator <= 0
    ):
        raise SemanticUnionAnalysisError(
            "{} is not an exact fraction".format(label)
        )
    value = Fraction(numerator, denominator)
    if (value.numerator, value.denominator) != (numerator, denominator):
        raise SemanticUnionAnalysisError(
            "{} is not a reduced exact fraction".format(label)
        )
    return value


def _manifest_digest(tasks) -> str:
    payload = "".join(
        "{}:{}\n".format(domain, problem)
        for domain, problem in sorted(tasks)
    ).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _terminal_class(record):
    errors = record.get("unexplained_errors")
    if errors not in (None, [], [LAB_SLURM_ERROR]):
        raise SemanticUnionAnalysisError(
            "cell carries unexplained parser or execution errors"
        )
    code = record.get("planner_exit_code")
    if type(code) is not int or code not in Base.OUTCOME_SPECS:
        raise SemanticUnionAnalysisError(
            "cell has an unrecognized planner terminal outcome"
        )
    expected_error, coverage, unsolvable, outcome_class = Base.OUTCOME_SPECS[code]
    if (
        record.get("error") != expected_error
        or type(record.get("coverage")) is not int
        or record.get("coverage") != coverage
        or record.get("unsolvable") != unsolvable
    ):
        raise SemanticUnionAnalysisError(
            "cell terminal outcome fields contradict each other"
        )
    return outcome_class


def _validate_stream_contract(record, outcome_class):
    expansion_present = record.get("wbh_expansion_profile_present") is True
    expansion_certified = record.get("wbh_expansion_profile_certified") is True
    expansion_complete = record.get("wbh_expansion_profile_complete") is True
    profile_present = record.get("wbh_profile_present") is True
    profile_prefix = record.get("wbh_profile_prefix_certified") is True
    profile_complete = record.get("wbh_profile_complete") is True
    selector_present = record.get("pdb_profile_selector_present") is True
    selector_prefix = (
        record.get("pdb_profile_selector_prefix_certified") is True
    )

    if outcome_class == "presearch":
        if expansion_present or profile_present or selector_present:
            raise SemanticUnionAnalysisError(
                "pre-search outcome unexpectedly emitted search evidence"
            )
        if record.get("construction_completed") is not None:
            raise SemanticUnionAnalysisError(
                "pre-search outcome unexpectedly reached construction"
            )
        return

    if expansion_present and not expansion_certified:
        raise SemanticUnionAnalysisError("present schema-v2 stream is malformed")
    if profile_present and not profile_prefix:
        raise SemanticUnionAnalysisError("present profile stream is malformed")
    if selector_present and not selector_prefix:
        raise SemanticUnionAnalysisError("present selector stream is malformed")

    if outcome_class == "solved":
        if not all(
            value is True
            for value in (
                expansion_present,
                expansion_certified,
                expansion_complete,
                record.get("wbh_solved_summary_certified"),
                profile_present,
                profile_prefix,
                profile_complete,
                record.get("wbh_profile_certified"),
                selector_present,
                selector_prefix,
                record.get("pdb_profile_selector_trace_complete"),
                record.get("pdb_profile_selector_trace_certified"),
                record.get("construction_completed"),
            )
        ):
            raise SemanticUnionAnalysisError(
                "solved PDB cell lacks complete certified evidence"
            )
        if not isinstance(record.get("wbh_profile_done"), dict):
            raise SemanticUnionAnalysisError("solved PDB cell lacks profile done")
    elif outcome_class == "search_terminal":
        if not all(
            value is True
            for value in (
                expansion_present,
                expansion_certified,
                expansion_complete,
                profile_present,
                profile_prefix,
                profile_complete,
            )
        ):
            raise SemanticUnionAnalysisError(
                "terminal search outcome lacks complete profile streams"
            )
    elif outcome_class not in {"search_resource", "solved_resource"}:
        raise SemanticUnionAnalysisError("internal outcome taxonomy error")

    if record.get("construction_completed") is True and not all(
        value is True
        for value in (
            record.get("pdb_profile_selector_trace_complete"),
            record.get("pdb_profile_selector_trace_certified"),
        )
    ):
        raise SemanticUnionAnalysisError(
            "completed PDB construction lacks a certified selector trace"
        )
    if (
        record.get("construction_completed") is True
        and not isinstance(record.get("wbh_profile_heuristic_profile"), dict)
    ):
        raise SemanticUnionAnalysisError(
            "completed PDB construction lacks its heuristic profile"
        )


def validate_matrix(records, expected_tasks=P.COHORT_TASKS):
    expected_cells = expected_tasks * P.CONFIG_COUNT
    if len(records) != expected_cells:
        raise SemanticUnionAnalysisError(
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
        "planner_revision": E.PLANNER_REVISION,
        "planner_binary_sha256": E.PLANNER_BINARY_SHA256,
        "preprocess_binary_sha256": E.PREPROCESS_BINARY_SHA256,
        "planner_preprocess_sha256": E.PREPROCESS_BINARY_SHA256,
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
            raise SemanticUnionAnalysisError("record has an invalid cell identity")
        task = (domain, problem)
        key = (label, task)
        if key in matrix:
            raise SemanticUnionAnalysisError("matrix contains a duplicate cell")
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
                raise SemanticUnionAnalysisError(
                    "cell changed fixed field {}".format(field)
                )
        if record.get("id") != [label, domain, problem]:
            raise SemanticUnionAnalysisError(
                "cell id differs from its matrix identity"
            )
        if record.get("component_options") != ["--search", P.SEARCHES[label]]:
            raise SemanticUnionAnalysisError(
                "cell component options differ from its label"
            )
        if record.get("driver_options") != expected_driver_options:
            raise SemanticUnionAnalysisError("cell driver options changed")
        if record.get("build_options") != list(P.BUILD_OPTIONS):
            raise SemanticUnionAnalysisError("cell build options changed")
        for field in ("local_revision", "global_revision"):
            if record.get(field) != E.PLANNER_REVISION:
                raise SemanticUnionAnalysisError(
                    "cell changed {}".format(field)
                )
        outcome_class = _terminal_class(record)
        _validate_stream_contract(record, outcome_class)
        expectation = record.get("wbh_profile_expected")
        if "wbh_profile_expected" not in record:
            if outcome_class != "presearch":
                raise SemanticUnionAnalysisError(
                    "search cell lacks its profile parser contract"
                )
        elif expectation is not True:
            raise SemanticUnionAnalysisError(
                "PDB cell has the wrong profile expectation"
            )
        matrix[key] = record
        outcome_classes[key] = outcome_class
        tasks.add(task)

    tasks = sorted(tasks)
    if len(tasks) != expected_tasks:
        raise SemanticUnionAnalysisError("task count changed")
    for task in tasks:
        if any((label, task) not in matrix for label in P.LABELS):
            raise SemanticUnionAnalysisError("matrix is incomplete")
        solved_costs = {
            matrix[(label, task)].get("solution_cost")
            for label in P.LABELS
            if matrix[(label, task)].get("coverage") == 1
        }
        if any(type(cost) is not int or cost < 0 for cost in solved_costs):
            raise SemanticUnionAnalysisError("solved cell has an invalid cost")
        if len(solved_costs) > 1:
            raise SemanticUnionAnalysisError(
                "configurations disagree on solution cost"
            )
    if expected_tasks == P.COHORT_TASKS:
        if _manifest_digest(tasks) != P.COHORT_MANIFEST_SHA256:
            raise SemanticUnionAnalysisError("task manifest changed")
        if len({domain for domain, _ in tasks}) != P.COHORT_DOMAINS:
            raise SemanticUnionAnalysisError("domain count changed")
    return matrix, tasks, outcome_classes


def _validate_solved_measurement(record):
    effort = record.get("effort")
    cost = record.get("solution_cost")
    done = record.get("wbh_profile_done")
    layers = record.get("wbh_profile_layer_profiles")
    expansion = record.get("wbh_expansion_profile")
    if (
        type(effort) is not int
        or effort < 0
        or type(cost) is not int
        or cost < 0
        or not isinstance(done, dict)
        or done.get("solution_cost") != cost
        or not isinstance(layers, list)
        or not isinstance(expansion, list)
    ):
        raise SemanticUnionAnalysisError(
            "solved cell has malformed effort, cost, or profile data"
        )
    layer_g = []
    for layer in layers:
        if not isinstance(layer, dict):
            raise SemanticUnionAnalysisError("layer profile is not an object")
        g = layer.get("g")
        if (
            layer.get("completed") is not True
            or type(g) is not int
            or not 0 <= g < cost
            or type(layer.get("bdd_nodes")) is not int
            or layer["bdd_nodes"] < 0
            or layer.get("piece_count") != 1
        ):
            raise SemanticUnionAnalysisError(
                "solved semantic-union layer is invalid"
            )
        layer_g.append(g)
    if layer_g != sorted(set(layer_g)):
        raise SemanticUnionAnalysisError(
            "solved semantic-union layers are not sorted and unique"
        )
    union_effort = done.get("layer_union_effort")
    if (
        type(union_effort) is not int
        or union_effort < 0
        or union_effort != sum(layer["bdd_nodes"] for layer in layers)
        or record.get("wbh_profile_layer_profile_attempts") != len(layers)
        or record.get("wbh_profile_completed_layer_profiles") != len(layers)
    ):
        raise SemanticUnionAnalysisError(
            "semantic-union effort fails event conservation"
        )
    expansion_g = []
    for item in expansion:
        if (
            not isinstance(item, dict)
            or type(item.get("g")) is not int
            or not 0 <= item["g"] < cost
            or type(item.get("effort")) is not int
            or item["effort"] < 0
        ):
            raise SemanticUnionAnalysisError(
                "per-g expansion profile is invalid"
            )
        expansion_g.append(item["g"])
    if expansion_g != sorted(set(expansion_g)):
        raise SemanticUnionAnalysisError(
            "per-g expansion profile is not sorted and unique"
        )
    if sum(item["effort"] for item in expansion) != effort:
        raise SemanticUnionAnalysisError(
            "bucket effort fails per-g event conservation"
        )
    if layer_g != expansion_g:
        raise SemanticUnionAnalysisError(
            "semantic-union and bucket profiles cover different g layers"
        )
    return effort, union_effort


def _observation(record, task, label):
    if record.get("coverage") != 1:
        return "unsolved", None
    if not all(
        value is True
        for value in (
            record.get("wbh_solved_summary_certified"),
            record.get("wbh_expansion_profile_complete"),
            record.get("wbh_expansion_profile_certified"),
            record.get("wbh_profile_complete"),
            record.get("wbh_profile_certified"),
            record.get("pdb_profile_selector_trace_certified"),
        )
    ):
        return "incomplete_profile", None
    effort, union_effort = _validate_solved_measurement(record)
    if union_effort == 0:
        return "zero_union_effort", None

    selected = record.get("pdb_profile_selector_selected")
    heuristic = record.get("wbh_profile_heuristic_profile")
    if not isinstance(selected, dict) or not isinstance(heuristic, dict):
        raise SemanticUnionAnalysisError(
            "eligible cell lacks selected heuristic evidence"
        )
    try:
        quality = Predictor._quality_key(selected)
    except Predictor.PredictorAnalysisError as err:
        raise SemanticUnionAnalysisError(str(err)) from err
    add_nodes = heuristic.get("add_nodes")
    terminals = heuristic.get("num_terminals")
    values = heuristic.get("num_values")
    width = heuristic.get("cofactor_width")
    if any(type(value) is not int for value in (add_nodes, terminals, values, width)):
        raise SemanticUnionAnalysisError(
            "eligible heuristic has noninteger predictors"
        )
    if add_nodes < 0 or terminals < 1 or values < 1 or width < 1:
        raise SemanticUnionAnalysisError("eligible heuristic predictors are invalid")
    total_add = add_nodes + terminals
    if (
        selected.get("cofactor_width") != width
        or selected.get("width_upper_bound") != total_add
        or record.get("add_nodes") != add_nodes
        or record.get("num_terminals") != terminals
        or record.get("num_values") != values
        or record.get("width_upper_bound") != total_add
    ):
        raise SemanticUnionAnalysisError(
            "selector, profile, and schema-v2 heuristic identities differ"
        )
    for field, expected in (
        ("add_nodes", add_nodes),
        ("num_terminals", terminals),
        ("transformed_num_values", values),
    ):
        if field in selected and selected[field] != expected:
            raise SemanticUnionAnalysisError(
                "selector {} disagrees with the heuristic profile".format(field)
            )
    try:
        semantic_id = Predictor._semantic_id(selected, heuristic, quality)
    except Predictor.PredictorAnalysisError as err:
        raise SemanticUnionAnalysisError(str(err)) from err
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
        "actual_effort": effort,
        "semantic_union_effort": union_effort,
        "_quality": quality,
        "_fragmentation": (effort, union_effort),
    }


def observations(matrix, tasks):
    statuses = Counter()
    grouped = defaultdict(dict)
    for task in tasks:
        for label in P.LABELS:
            status, observation = _observation(matrix[(label, task)], task, label)
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
                "actual_effort",
                "semantic_union_effort",
                "_quality",
                "_fragmentation",
            )
            if any(previous[field] != observation[field] for field in invariant):
                raise SemanticUnionAnalysisError(
                    "duplicate selected heuristic has different deterministic evidence"
                )
            previous["configs"].append(label)
    flat = [
        observation
        for task in tasks
        for observation in grouped.get(task, {}).values()
    ]
    return flat, grouped, dict(statuses)


def decision_gate(shared):
    support = shared.get("support") or {}
    predictors = shared.get("predictors") or {}
    try:
        width = predictors["cofactor_width"]
        add = predictors["total_add_nodes"]
        quality = predictors["quality"]
    except KeyError as err:
        raise SemanticUnionAnalysisError("shared comparison lacks a predictor") from err
    width_macro = _exact_fraction(
        width.get("equal_domain_macro"), "width macro"
    )
    add_macro = _exact_fraction(add.get("equal_domain_macro"), "ADD macro")
    quality_macro = _exact_fraction(
        quality.get("equal_domain_macro"), "quality macro"
    )
    loo_records = (width.get("leave_one_domain_out") or {}).get("values") or {}
    loo_values = {
        domain: _exact_fraction(record, "width LODO {}".format(domain))
        for domain, record in loo_records.items()
    }
    criteria = {
        "at_least_31_domains": (
            type(support.get("eligible_domains")) is int
            and support["eligible_domains"] >= P.MIN_DOMAINS
        ),
        "at_least_184_tasks": (
            type(support.get("tasks_with_comparable_pairs")) is int
            and support["tasks_with_comparable_pairs"]
            >= P.MIN_TASKS_WITH_COMPARABLE_PAIRS
        ),
        "width_macro_at_least_0_65": (
            width_macro is not None and width_macro >= Fraction(13, 20)
        ),
        "every_width_lodo_at_least_0_60": (
            len(loo_values) == P.COHORT_DOMAINS
            and all(value is not None and value >= Fraction(3, 5)
                    for value in loo_values.values())
        ),
        "width_beats_quality": (
            width_macro is not None
            and quality_macro is not None
            and width_macro > quality_macro
        ),
        "width_within_0_02_of_total_add": (
            width_macro is not None
            and add_macro is not None
            and width_macro >= add_macro - Fraction(1, 50)
        ),
    }
    return {
        "pass": all(criteria.values()),
        "criteria": criteria,
        "consequence": (
            "freeze_one_fragmentation_aware_selector_before_evaluation"
            if all(criteria.values())
            else "do_not_tune_a_rescue_selector"
        ),
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


def instrumentation_overhead(matrix, tasks, baseline_records):
    """Describe wall-time change against the sealed earlier experiment.

    This is a diagnostic, not a gate.  The older outcomes are already known,
    so the function reports only fixed-pair coverage and jointly solved timing.
    """
    baseline_matrix, _, _ = Base.validate_matrix(baseline_records)
    rows = []
    pooled_new = 0.0
    pooled_old = 0.0
    for label in P.LABELS:
        coverage_delta = 0
        pairs = 0
        new_total = 0.0
        old_total = 0.0
        for task in tasks:
            new = matrix[(label, task)]
            old = baseline_matrix[(label, task)]
            coverage_delta += new["coverage"] - old["coverage"]
            if (
                new["coverage"] == 1
                and old["coverage"] == 1
                and new.get("solution_cost") == old.get("solution_cost")
            ):
                new_time = new.get("planner_time")
                old_time = old.get("planner_time")
                if not all(
                    type(value) in (int, float)
                    and not isinstance(value, bool)
                    and math.isfinite(value)
                    and value >= 0
                    for value in (new_time, old_time)
                ):
                    raise SemanticUnionAnalysisError(
                        "jointly solved overhead pair has invalid planner time"
                    )
                pairs += 1
                new_total += new_time
                old_total += old_time
        pooled_new += new_total
        pooled_old += old_total
        rows.append({
            "config": label,
            "coverage_new_minus_old": coverage_delta,
            "jointly_solved_same_cost_pairs": pairs,
            "new_planner_time_total": new_total,
            "old_planner_time_total": old_total,
            "new_over_old_planner_time": (
                new_total / old_total if old_total else None
            ),
        })
    return {
        "role": "diagnostic_only_not_a_decision_gate",
        "baseline_protocol": P.Source.PROTOCOL,
        "by_config": rows,
        "pooled_new_planner_time_total": pooled_new,
        "pooled_old_planner_time_total": pooled_old,
        "pooled_new_over_old_planner_time": (
            pooled_new / pooled_old if pooled_old else None
        ),
    }


def make_analysis(records, baseline_records=None):
    P.validate_protocol_without_archive()
    matrix, tasks, outcome_classes = validate_matrix(records)
    flat, grouped, statuses = observations(matrix, tasks)
    domains = {domain for domain, _ in tasks}
    try:
        individual = Predictor.fragmentation_predictors(grouped, domains)
        shared = Predictor._shared_pairwise_comparison(
            grouped, PREDICTOR_SPECS, "_fragmentation", domains
        )
    except Predictor.PredictorAnalysisError as err:
        raise SemanticUnionAnalysisError(str(err)) from err
    public = []
    for observation in flat:
        public.append({
            key: value
            for key, value in observation.items()
            if not key.startswith("_") and key != "task"
        } | {
            "quality": [
                observation["_quality"][0],
                observation["_quality"][1],
                _fraction_record(observation["_quality"][2]),
                _fraction_record(observation["_quality"][3]),
            ],
            "fragmentation": _ratio(*observation["_fragmentation"]),
        })
    result = {
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
        "terminal_outcomes": dict(Counter(outcome_classes.values())),
        "coverage": coverage_summary(matrix, tasks),
        "observation_status": statuses,
        "observations": public,
        "individual_pairwise_predictors": individual,
        "shared_primary_comparison": shared,
    }
    result["decision_gate"] = decision_gate(shared)
    if baseline_records is not None:
        result["instrumentation_overhead"] = instrumentation_overhead(
            matrix, tasks, baseline_records
        )
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("properties", type=Path)
    parser.add_argument("--baseline-properties", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    records = Base.load_records(args.properties)
    baseline = (
        Base.load_records(args.baseline_properties)
        if args.baseline_properties
        else None
    )
    analysis = make_analysis(records, baseline)
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
        SemanticUnionAnalysisError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
