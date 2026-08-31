#!/usr/bin/env python3
"""Fail-closed analysis of the unseen Gamer-seed validation."""

from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_comparison as Base
import analyze_pdb_profile_joint_pilot as Joint
import analyze_pdb_profile_order_intervention as Order
import pdb_profile_joint_seed_validation_protocol as P


class SeedValidationAnalysisError(RuntimeError):
    pass


SCHEMA = "symbolic-search-heuristics/pdb-profile-joint-seed-validation/v1"


def validate_matrix(records):
    original = Order.P
    Order.P = P
    try:
        return Order.validate_matrix(records, expected_tasks=P.COHORT_TASKS)
    except Order.OrderInterventionAnalysisError as err:
        raise SeedValidationAnalysisError(str(err)) from err
    finally:
        Order.P = original


def grouped_observations(matrix, tasks):
    statuses = Counter()
    grouped = defaultdict(dict)
    rows = []
    semantic_fields = (
        "pattern",
        "solution_cost",
        "finite_values",
        "expanded_states",
        "active_identity",
    )
    for task in tasks:
        observed = {}
        for label in P.LABELS:
            try:
                status, item = Joint._joint_observation(
                    matrix[(label, task)], task, label
                )
            except Joint.JointPilotAnalysisError as err:
                raise SeedValidationAnalysisError(str(err)) from err
            statuses["{}:{}".format(label, status)] += 1
            if item is not None:
                observed[label] = item
        if len(observed) != P.CONFIG_COUNT:
            statuses["task_ineligible"] += 1
            continue

        reference = observed[P.LABELS[0]]
        for label in P.LABELS[1:]:
            candidate = observed[label]
            for field in semantic_fields:
                if candidate[field] != reference[field]:
                    raise SeedValidationAnalysisError(
                        "seed intervention changed semantic field {}"
                        .format(field)
                    )
        for left, right in itertools.combinations(P.LABELS, 2):
            status = (
                "seed_pair_identical_order"
                if observed[left]["variable_order_sha256"]
                == observed[right]["variable_order_sha256"]
                else "seed_pair_distinct_order"
            )
            statuses[status] += 1
        statuses["task_all_eligible"] += 1
        grouped[task] = observed
        rows.append((task, observed))
    return rows, grouped, dict(statuses)


def _shared(grouped, specs, target, domains):
    try:
        return Order._shared(grouped, specs, target, domains)
    except Order.OrderInterventionAnalysisError as err:
        raise SeedValidationAnalysisError(str(err)) from err


def _summary_value(summary, predictor):
    try:
        return Order._exact_fraction(
            summary["predictors"][predictor]["equal_domain_macro"],
            "{} macro".format(predictor),
        )
    except (KeyError, TypeError, Order.OrderInterventionAnalysisError) as err:
        raise SeedValidationAnalysisError(
            "comparison lacks a valid {} macro".format(predictor)
        ) from err


def _lodo(summary, predictor):
    try:
        records = summary["predictors"][predictor][
            "leave_one_domain_out"
        ]["values"]
    except (KeyError, TypeError) as err:
        raise SeedValidationAnalysisError(
            "comparison lacks {} LODO values".format(predictor)
        ) from err
    values = {}
    for domain, record in records.items():
        if record is None:
            values[domain] = None
        else:
            try:
                values[domain] = Order._exact_fraction(
                    record, "{} LODO".format(predictor)
                )
            except Order.OrderInterventionAnalysisError as err:
                raise SeedValidationAnalysisError(str(err)) from err
    return values


def _support_passes(support):
    requirements = (
        ("comparable", P.MIN_COMPARABLE_PAIRS),
        (
            "tasks_with_comparable_pairs",
            P.MIN_TASKS_WITH_COMPARABLE_PAIRS,
        ),
        ("eligible_domains", P.MIN_DOMAINS),
    )
    return all(
        type(support.get(field)) is int
        and support[field] >= minimum
        for field, minimum in requirements
    )


def decision_gates(primary, absolute):
    support = primary.get("support") or {}
    absolute_support = absolute.get("support") or {}
    joint = _summary_value(primary, "joint")
    null = _summary_value(primary, "inverse_union")
    absolute_joint = _summary_value(absolute, "joint")
    joint_lodo = _lodo(primary, "joint")
    null_lodo = _lodo(primary, "inverse_union")
    expected_domains = set(joint_lodo) | set(null_lodo)
    lodo_complete = (
        len(expected_domains) == P.COHORT_DOMAINS
        and set(joint_lodo) == expected_domains
        and set(null_lodo) == expected_domains
        and all(
            joint_lodo[domain] is not None
            and null_lodo[domain] is not None
            for domain in expected_domains
        )
    )
    lodo_nonworse = lodo_complete and all(
        joint_lodo[domain] >= null_lodo[domain]
        for domain in expected_domains
    )
    primary_support = _support_passes(support)
    absolute_support_ok = _support_passes(absolute_support)
    min_primary = Fraction(
        P.MIN_PRIMARY_CONCORDANCE_NUMERATOR,
        P.MIN_PRIMARY_CONCORDANCE_DENOMINATOR,
    )
    min_margin = Fraction(
        P.MIN_NULL_MARGIN_NUMERATOR,
        P.MIN_NULL_MARGIN_DENOMINATOR,
    )
    min_absolute = Fraction(
        P.MIN_ABSOLUTE_CONCORDANCE_NUMERATOR,
        P.MIN_ABSOLUTE_CONCORDANCE_DENOMINATOR,
    )
    margin = joint - null if joint is not None and null is not None else None
    return {
        "joint_beyond_denominator_null": {
            "pass": (
                primary_support
                and joint is not None
                and null is not None
                and joint >= min_primary
                and margin >= min_margin
                and lodo_nonworse
            ),
            "support_pass": primary_support,
            "minimum_concordance": Order._fraction_record(min_primary),
            "minimum_null_margin": Order._fraction_record(min_margin),
            "observed_joint": Order._fraction_record(joint),
            "observed_inverse_union": Order._fraction_record(null),
            "observed_margin": Order._fraction_record(margin),
            "lodo_complete": lodo_complete,
            "lodo_joint_never_worse": lodo_nonworse,
        },
        "absolute_joint_certificate": {
            "pass": (
                absolute_support_ok
                and absolute_joint is not None
                and absolute_joint >= min_absolute
            ),
            "support_pass": absolute_support_ok,
            "minimum_concordance": Order._fraction_record(min_absolute),
            "observed_joint": Order._fraction_record(absolute_joint),
        },
    }


def make_analysis(records):
    P.validate_protocol_without_archive()
    matrix, tasks, outcomes = validate_matrix(records)
    rows, grouped, statuses = grouped_observations(matrix, tasks)
    domains = {domain for domain, _ in tasks}
    primary = _shared(
        grouped,
        {
            "joint": ("R_joint", "same"),
            "inverse_union": ("inverse_union", "same"),
        },
        "_fragmentation",
        domains,
    )
    normalized = _shared(
        grouped,
        {
            "joint": ("R_joint", "same"),
            "cartesian": ("R_profile", "same"),
            "width": ("R_width", "same"),
            "add": ("R_add", "same"),
            "inverse_union": ("inverse_union", "same"),
        },
        "_fragmentation",
        domains,
    )
    absolute = _shared(
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
        "frozen_protocol_sha256": P.PROTOCOL_SHA256,
        "scope": {
            "tasks": len(tasks),
            "domains": len(domains),
            "configurations": P.CONFIG_COUNT,
            "cells": len(records),
            "seeds": list(P.SEEDS),
        },
        "terminal_outcomes": dict(Counter(outcomes.values())),
        "observation_status": statuses,
        "task_observations": [
            {
                "domain": task[0],
                "problem": task[1],
                "seeds": {
                    label: Joint._public_observation(observed[label])
                    for label in P.LABELS
                },
            }
            for task, observed in rows
        ],
        "primary_joint_vs_inverse_union": primary,
        "normalized_certificates": normalized,
        "absolute_certificates": absolute,
        "decision_gates": decision_gates(primary, absolute),
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
        raise SeedValidationAnalysisError(
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
        SeedValidationAnalysisError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
