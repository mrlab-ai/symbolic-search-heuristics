#!/usr/bin/env python3
"""Fail-closed analysis of the fixed-heuristic variable-order intervention."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_comparison as Base
import analyze_pdb_profile_certificate_holdout as Certificate
import analyze_pdb_profile_predictors as Predictor
import analyze_pdb_profile_semantic_union as Semantic
import pdb_fixed_pattern_parser as Pattern
import pdb_profile_order_intervention_protocol as P


class OrderInterventionAnalysisError(RuntimeError):
    pass


SCHEMA = "symbolic-search-heuristics/pdb-profile-order-intervention/v1"


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
        raise OrderInterventionAnalysisError(
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


def _exact_fraction(record, label):
    if record is None:
        return None
    if not isinstance(record, dict):
        raise OrderInterventionAnalysisError(
            "{} is not a fraction record".format(label)
        )
    numerator = record.get("numerator")
    denominator = record.get("denominator")
    if (
        type(numerator) is not int
        or type(denominator) is not int
        or denominator <= 0
    ):
        raise OrderInterventionAnalysisError(
            "{} is not an exact fraction".format(label)
        )
    value = Fraction(numerator, denominator)
    if (value.numerator, value.denominator) != (numerator, denominator):
        raise OrderInterventionAnalysisError(
            "{} is not reduced".format(label)
        )
    return value


def _manifest_digest(tasks) -> str:
    raw = "".join(
        "{}:{}\n".format(domain, problem)
        for domain, problem in sorted(tasks)
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def validate_matrix(records, expected_tasks=P.COHORT_TASKS):
    expected_cells = expected_tasks * P.CONFIG_COUNT
    if len(records) != expected_cells:
        raise OrderInterventionAnalysisError(
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
        "source_protocol": P.Holdout.PROTOCOL,
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
    outcomes = {}
    for record in records:
        label = record.get("algorithm")
        domain = record.get("domain")
        problem = record.get("problem")
        if label not in P.LABELS or not all(
            isinstance(value, str) and value
            for value in (domain, problem)
        ):
            raise OrderInterventionAnalysisError(
                "record has an invalid cell identity"
            )
        task = (domain, problem)
        key = (label, task)
        if key in matrix:
            raise OrderInterventionAnalysisError(
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
                raise OrderInterventionAnalysisError(
                    "cell changed fixed field {}".format(field)
                )
        if record.get("id") != [label, domain, problem]:
            raise OrderInterventionAnalysisError(
                "cell id differs from its matrix identity"
            )
        if record.get("component_options") != [
            "--search", P.SEARCHES[label]
        ]:
            raise OrderInterventionAnalysisError(
                "cell component options differ from its label"
            )
        if record.get("driver_options") != expected_driver_options:
            raise OrderInterventionAnalysisError(
                "cell driver options changed"
            )
        if record.get("build_options") != list(P.BUILD_OPTIONS):
            raise OrderInterventionAnalysisError(
                "cell build options changed"
            )
        for field in ("local_revision", "global_revision"):
            if record.get(field) != P.PLANNER_REVISION:
                raise OrderInterventionAnalysisError(
                    "cell changed {}".format(field)
                )
        try:
            outcome = Certificate._terminal_class(record)
            Certificate._validate_stream_contract(record, outcome, label)
        except Certificate.CertificateHoldoutAnalysisError as err:
            raise OrderInterventionAnalysisError(str(err)) from err
        if "wbh_profile_expected" not in record:
            if outcome != "presearch":
                raise OrderInterventionAnalysisError(
                    "search cell lacks its profile parser contract"
                )
        elif record.get("wbh_profile_expected") is not True:
            raise OrderInterventionAnalysisError(
                "PDB cell has the wrong profile expectation"
            )
        if record.get("construction_completed") is True and not all((
            record.get("pdb_fixed_pattern_parser_protocol")
            == Pattern.PARSER_PROTOCOL,
            record.get("pdb_fixed_pattern_present") is True,
            record.get("pdb_fixed_pattern_certified") is True,
            isinstance(record.get("pdb_fixed_pattern"), list),
        )):
            raise OrderInterventionAnalysisError(
                "completed construction lacks its fixed-pattern identity"
            )
        matrix[key] = record
        outcomes[key] = outcome
        tasks.add(task)

    tasks = sorted(tasks)
    if len(tasks) != expected_tasks:
        raise OrderInterventionAnalysisError("task count changed")
    for task in tasks:
        if any((label, task) not in matrix for label in P.LABELS):
            raise OrderInterventionAnalysisError("matrix is incomplete")
        solved_costs = {
            matrix[(label, task)].get("solution_cost")
            for label in P.LABELS
            if matrix[(label, task)].get("coverage") == 1
        }
        if any(type(cost) is not int or cost < 0 for cost in solved_costs):
            raise OrderInterventionAnalysisError(
                "solved cell has an invalid cost"
            )
        if len(solved_costs) > 1:
            raise OrderInterventionAnalysisError(
                "the two orders disagree on solution cost"
            )
    if expected_tasks == P.COHORT_TASKS:
        if _manifest_digest(tasks) != P.COHORT_MANIFEST_SHA256:
            raise OrderInterventionAnalysisError("task manifest changed")
        if len({domain for domain, _ in tasks}) != P.COHORT_DOMAINS:
            raise OrderInterventionAnalysisError("domain count changed")
    return matrix, tasks, outcomes


def _observation(record, task, label):
    if record.get("coverage") != 1:
        return "unsolved", None
    required = (
        "wbh_solved_summary_certified",
        "wbh_expansion_profile_complete",
        "wbh_expansion_profile_certified",
        "wbh_profile_complete",
        "wbh_profile_certified",
        "pdb_fixed_pattern_certified",
    )
    if any(record.get(field) is not True for field in required):
        return "incomplete_profile", None
    try:
        effort, union_effort = Semantic._validate_solved_measurement(record)
    except Semantic.SemanticUnionAnalysisError as err:
        raise OrderInterventionAnalysisError(str(err)) from err
    if union_effort == 0:
        return "zero_union_effort", None

    heuristic = record.get("wbh_profile_heuristic_profile")
    state_bits = record.get("wbh_profile_state_bits")
    pattern = record.get("pdb_fixed_pattern")
    order_sha = record.get("wbh_profile_variable_order_sha256")
    if (
        not isinstance(heuristic, dict)
        or type(state_bits) is not int
        or state_bits < 1
        or not isinstance(pattern, list)
        or not isinstance(order_sha, str)
        or len(order_sha) != 64
        or any(char not in "0123456789abcdef" for char in order_sha)
    ):
        raise OrderInterventionAnalysisError(
            "eligible cell lacks profile, pattern or order identity"
        )
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
        raise OrderInterventionAnalysisError(
            "eligible heuristic profile is invalid"
        )
    total_add = add_nodes + terminals
    if any((
        record.get("add_nodes") != add_nodes,
        record.get("num_terminals") != terminals,
        record.get("num_values") != values,
        record.get("width_upper_bound") != total_add,
        record.get("pdb_fixed_pattern_size") != len(pattern),
    )):
        raise OrderInterventionAnalysisError(
            "schema-v2 and profile heuristic identities differ"
        )

    layers = {
        layer["g"]: layer
        for layer in record["wbh_profile_layer_profiles"]
    }
    expansions = {
        item["g"]: item for item in record["wbh_expansion_profile"]
    }
    if set(layers) != set(expansions):
        raise OrderInterventionAnalysisError(
            "layer and expansion profiles cover different g values"
        )
    profile_bound = 0
    width_bound = 0
    add_bound = 0
    active_identity = []
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
            raise OrderInterventionAnalysisError(
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
            raise OrderInterventionAnalysisError(
                "profile product exceeds its width relaxation"
            )
        profile_bound += active_values * cut_product
        width_bound += active_values * width_relaxation
        add_bound += active_values * add_apply
        active_identity.append((g, active_values))
    if any(effort > bound for bound in (
        profile_bound, width_bound, add_bound
    )):
        raise OrderInterventionAnalysisError(
            "measured effort exceeds a theorem certificate"
        )
    expanded_states = record.get("expanded_states")
    if (
        type(expanded_states) not in (int, float)
        or isinstance(expanded_states, bool)
        or not math.isfinite(expanded_states)
        or expanded_states < 0
    ):
        raise OrderInterventionAnalysisError(
            "eligible cell has invalid expanded-state count"
        )
    return "eligible", {
        "domain": task[0],
        "problem": task[1],
        "task": task,
        "config": label,
        "pattern": pattern,
        "solution_cost": record["solution_cost"],
        "finite_values": values,
        "expanded_states": expanded_states,
        "active_identity": tuple(active_identity),
        "variable_order_sha256": order_sha,
        "cofactor_width": width,
        "total_add_nodes": total_add,
        "actual_effort": effort,
        "semantic_union_effort": union_effort,
        "B_profile": profile_bound,
        "B_width": width_bound,
        "B_add": add_bound,
        "R_profile": Fraction(profile_bound, union_effort),
        "R_width": Fraction(width_bound, union_effort),
        "R_add": Fraction(add_bound, union_effort),
        "_fragmentation": (effort, union_effort),
    }


def paired_observations(matrix, tasks):
    statuses = Counter()
    grouped = defaultdict(dict)
    pairs = []
    for task in tasks:
        observed = {}
        for label in P.LABELS:
            status, item = _observation(matrix[(label, task)], task, label)
            statuses["{}:{}".format(label, status)] += 1
            if item is not None:
                observed[label] = item
        if len(observed) != 2:
            statuses["pair_ineligible"] += 1
            continue
        gamer = observed["pdb_goal_fill_gamer"]
        fd = observed["pdb_goal_fill_fd"]
        for field in (
            "pattern",
            "solution_cost",
            "finite_values",
            "expanded_states",
            "active_identity",
        ):
            if gamer[field] != fd[field]:
                raise OrderInterventionAnalysisError(
                    "order intervention changed semantic field {}".format(
                        field
                    )
                )
        if gamer["variable_order_sha256"] == fd["variable_order_sha256"]:
            statuses["pair_identical_order"] += 1
        else:
            statuses["pair_distinct_order"] += 1
        grouped[task] = {"gamer": gamer, "fd": fd}
        pairs.append({"task": task, "gamer": gamer, "fd": fd})
    return pairs, grouped, dict(statuses)


def _shared(grouped, specs, target, domains):
    try:
        return Predictor._shared_pairwise_comparison(
            grouped, specs, target, domains
        )
    except Predictor.PredictorAnalysisError as err:
        raise OrderInterventionAnalysisError(str(err)) from err


def _summary_value(summary, predictor):
    try:
        record = summary["predictors"][predictor]["equal_domain_macro"]
    except (KeyError, TypeError) as err:
        raise OrderInterventionAnalysisError(
            "comparison lacks {} macro".format(predictor)
        ) from err
    return _exact_fraction(record, "{} macro".format(predictor))


def _lodo(summary, predictor):
    try:
        records = summary["predictors"][predictor][
            "leave_one_domain_out"
        ]["values"]
    except (KeyError, TypeError) as err:
        raise OrderInterventionAnalysisError(
            "comparison lacks {} LODO values".format(predictor)
        ) from err
    return {
        domain: _exact_fraction(record, "{} LODO".format(predictor))
        for domain, record in records.items()
    }


def decision_gates(primary):
    support = primary.get("support") or {}
    profile = _summary_value(primary, "profile")
    width = _summary_value(primary, "width")
    add = _summary_value(primary, "add")
    profile_lodo = _lodo(primary, "profile")
    width_lodo = _lodo(primary, "width")
    add_lodo = _lodo(primary, "add")
    support_ok = (
        type(support.get("eligible_domains")) is int
        and support["eligible_domains"] >= P.MIN_DOMAINS
        and type(support.get("tasks_with_comparable_pairs")) is int
        and support["tasks_with_comparable_pairs"]
        >= P.MIN_TASKS_WITH_COMPARABLE_PAIRS
    )
    complete_profile_lodo = (
        len(profile_lodo) == P.COHORT_DOMAINS
        and all(
            value is not None and value >= Fraction(3, 5)
            for value in profile_lodo.values()
        )
    )
    useful = {
        "support": support_ok,
        "profile_macro_at_least_0_65": (
            profile is not None and profile >= Fraction(13, 20)
        ),
        "profile_lodo_at_least_0_60": complete_profile_lodo,
        "profile_within_0_02_of_width": (
            profile is not None
            and width is not None
            and profile >= width - Fraction(1, 50)
        ),
        "profile_within_0_02_of_add": (
            profile is not None
            and add is not None
            and profile >= add - Fraction(1, 50)
        ),
    }
    def every_advantage(left, right):
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

    sharper = {
        "support": support_ok,
        "profile_macro_beats_width": (
            profile is not None and width is not None and profile > width
        ),
        "profile_macro_beats_add": (
            profile is not None and add is not None and profile > add
        ),
        "profile_beats_width_in_every_lodo": every_advantage(
            profile_lodo, width_lodo
        ),
        "profile_beats_add_in_every_lodo": every_advantage(
            profile_lodo, add_lodo
        ),
    }
    return {
        "predicts_order_sensitivity": {
            "pass": all(useful.values()),
            "criteria": useful,
        },
        "sharper_order_predictor": {
            "pass": all(sharper.values()),
            "criteria": sharper,
            "material_macro_advantage_over_width": (
                profile is not None
                and width is not None
                and profile >= width + Fraction(1, 50)
            ),
            "material_macro_advantage_over_add": (
                profile is not None
                and add is not None
                and profile >= add + Fraction(1, 50)
            ),
        },
    }


def _public_observation(item):
    return {
        key: value
        for key, value in item.items()
        if key not in {
            "task", "active_identity", "R_profile", "R_width", "R_add",
            "_fragmentation",
        }
    } | {
        "active_identity": [list(value) for value in item["active_identity"]],
        "R_profile": _fraction_record(item["R_profile"]),
        "R_width": _fraction_record(item["R_width"]),
        "R_add": _fraction_record(item["R_add"]),
        "fragmentation": _fraction_record(Fraction(*item["_fragmentation"])),
    }


def make_analysis(records):
    P.validate_protocol_without_archive()
    matrix, tasks, outcomes = validate_matrix(records)
    pairs, grouped, statuses = paired_observations(matrix, tasks)
    domains = {domain for domain, _ in tasks}
    primary = _shared(
        grouped,
        {
            "profile": ("R_profile", "same"),
            "width": ("R_width", "same"),
            "add": ("R_add", "same"),
        },
        "_fragmentation",
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
        "observation_status": statuses,
        "paired_observations": [
            {
                "domain": pair["task"][0],
                "problem": pair["task"][1],
                "gamer": _public_observation(pair["gamer"]),
                "fd": _public_observation(pair["fd"]),
            }
            for pair in pairs
        ],
        "primary_shared": primary,
        "absolute_shared": absolute,
        "decision_gates": decision_gates(primary),
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
        OrderInterventionAnalysisError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
