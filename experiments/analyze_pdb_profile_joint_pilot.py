#!/usr/bin/env python3
"""Fail-closed analysis of the co-occurring-residual development pilot."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_comparison as Base
import analyze_pdb_profile_order_intervention as Order
import pdb_profile_joint_pilot_protocol as P


class JointPilotAnalysisError(RuntimeError):
    pass


SCHEMA = "symbolic-search-heuristics/pdb-profile-joint-pilot/v1"


def validate_matrix(records):
    original = Order.P
    Order.P = P
    try:
        return Order.validate_matrix(records, expected_tasks=P.COHORT_TASKS)
    except Order.OrderInterventionAnalysisError as err:
        raise JointPilotAnalysisError(str(err)) from err
    finally:
        Order.P = original


def _joint_observation(record, task, label):
    try:
        status, item = Order._observation(record, task, label)
    except Order.OrderInterventionAnalysisError as err:
        raise JointPilotAnalysisError(str(err)) from err
    if item is None:
        return status, None
    if record.get("wbh_profile_schema_version") != 2:
        raise JointPilotAnalysisError(
            "eligible joint-profile cell does not use schema version 2"
        )

    state_bits = record["wbh_profile_state_bits"]
    heuristic_counts = record["wbh_profile_heuristic_profile"][
        "cofactor_counts"
    ]
    layers = {
        layer["g"]: layer
        for layer in record["wbh_profile_layer_profiles"]
    }
    expansions = {
        expansion["g"]: expansion
        for expansion in record["wbh_expansion_profile"]
    }
    joint_bound = 0
    for g in sorted(layers):
        layer = layers[g]
        state_counts = layer["cofactor_counts"]
        joint_counts = layer.get("joint_cofactor_counts")
        if (
            not isinstance(joint_counts, list)
            or len(joint_counts) != state_bits + 1
            or any(type(value) is not int or value < 1 for value in joint_counts)
        ):
            raise JointPilotAnalysisError(
                "eligible layer lacks a complete joint cofactor profile"
            )
        for position, values in enumerate(
            zip(state_counts, heuristic_counts, joint_counts)
        ):
            state_count, heuristic_count, joint_count = values
            if not (
                max(state_count, heuristic_count)
                <= joint_count
                <= state_count * heuristic_count
            ):
                raise JointPilotAnalysisError(
                    "joint cofactor profile violates its cut bounds at {}"
                    .format(position)
                )
        active_values = expansions[g]["active_value_count"]
        joint_cut = sum(joint_counts[:-1])
        cartesian_cut = sum(
            left * right
            for left, right in zip(
                state_counts[:-1], heuristic_counts[:-1]
            )
        )
        if joint_cut > cartesian_cut:
            raise JointPilotAnalysisError(
                "joint profile exceeds the Cartesian profile"
            )
        joint_bound += active_values * joint_cut

    if not item["actual_effort"] <= joint_bound <= item["B_profile"]:
        raise JointPilotAnalysisError(
            "joint run-level certificate violates its theorem chain"
        )
    union_effort = item["semantic_union_effort"]
    item["B_joint"] = joint_bound
    item["R_joint"] = Fraction(joint_bound, union_effort)
    item["inverse_union"] = Fraction(1, union_effort)
    return status, item


def paired_observations(matrix, tasks):
    statuses = Counter()
    grouped = defaultdict(dict)
    pairs = []
    for task in tasks:
        observed = {}
        for label in P.LABELS:
            status, item = _joint_observation(
                matrix[(label, task)], task, label
            )
            statuses["{}:{}".format(label, status)] += 1
            if item is not None:
                observed[label] = item
        if len(observed) != P.CONFIG_COUNT:
            statuses["pair_ineligible"] += 1
            continue
        gamer = observed[P.LABELS[0]]
        fd = observed[P.LABELS[1]]
        for field in (
            "pattern",
            "solution_cost",
            "finite_values",
            "expanded_states",
            "active_identity",
        ):
            if gamer[field] != fd[field]:
                raise JointPilotAnalysisError(
                    "order intervention changed semantic field {}".format(
                        field
                    )
                )
        if gamer["variable_order_sha256"] == fd["variable_order_sha256"]:
            statuses["pair_identical_order"] += 1
        else:
            statuses["pair_distinct_order"] += 1
        grouped[task] = {P.LABELS[0]: gamer, P.LABELS[1]: fd}
        pairs.append((task, gamer, fd))
    return pairs, grouped, dict(statuses)


def _shared(grouped, specs, target, domains):
    try:
        return Order._shared(grouped, specs, target, domains)
    except Order.OrderInterventionAnalysisError as err:
        raise JointPilotAnalysisError(str(err)) from err


def _public_observation(item):
    legacy = {
        key: value
        for key, value in item.items()
        if key not in {"R_joint", "inverse_union"}
    }
    result = Order._public_observation(legacy)
    result["R_joint"] = Order._fraction_record(item["R_joint"])
    result["inverse_union"] = Order._fraction_record(item["inverse_union"])
    return result


def make_analysis(records):
    P.validate_protocol_without_archive()
    matrix, tasks, outcomes = validate_matrix(records)
    pairs, grouped, statuses = paired_observations(matrix, tasks)
    domains = {domain for domain, _ in tasks}
    normalized_joint_vs_null = _shared(
        grouped,
        {
            "joint": ("R_joint", "same"),
            "inverse_union": ("inverse_union", "same"),
        },
        "_fragmentation",
        domains,
    )
    normalized_certificates = _shared(
        grouped,
        {
            "joint": ("R_joint", "same"),
            "cartesian": ("R_profile", "same"),
            "width": ("R_width", "same"),
            "add": ("R_add", "same"),
        },
        "_fragmentation",
        domains,
    )
    absolute_certificates = _shared(
        grouped,
        {
            "joint": ("B_joint", "same"),
            "cartesian": ("B_profile", "same"),
            "width": ("B_width", "same"),
            "add": ("B_add", "same"),
            "union": ("semantic_union_effort", "same"),
        },
        "actual_effort",
        domains,
    )
    return {
        "schema": SCHEMA,
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "development_only": True,
        "frozen_protocol_sha256": P.PROTOCOL_SHA256,
        "scope": {
            "tasks": len(tasks),
            "domains": len(domains),
            "configurations": P.CONFIG_COUNT,
            "cells": len(records),
        },
        "terminal_outcomes": dict(Counter(outcomes.values())),
        "observation_status": statuses,
        "paired_observations": [
            {
                "domain": task[0],
                "problem": task[1],
                "gamer": _public_observation(gamer),
                "fd": _public_observation(fd),
            }
            for task, gamer, fd in pairs
        ],
        "normalized_joint_vs_inverse_union": normalized_joint_vs_null,
        "normalized_certificates": normalized_certificates,
        "absolute_certificates": absolute_certificates,
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
    try:
        raw = json.dumps(
            analysis,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii") + b"\n"
    except (TypeError, ValueError) as err:
        raise JointPilotAnalysisError(
            "analysis is not finite canonical JSON"
        ) from err
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
        JointPilotAnalysisError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
