#!/usr/bin/env python3
"""Run the frozen shared-denominator audit on the primary holdout analysis."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_certificate_holdout as Primary
import analyze_pdb_profile_predictors as Predictor
import pdb_profile_certificate_holdout_protocol as Holdout
import pdb_profile_denominator_audit_protocol as P


class DenominatorAuditError(RuntimeError):
    pass


SCHEMA = "symbolic-search-heuristics/pdb-profile-denominator-audit/v1"


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
        raise DenominatorAuditError(
            "audit is not finite canonical JSON"
        ) from err


def _load_primary(path: Path):
    try:
        raw = path.read_bytes()
        data = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise DenominatorAuditError("cannot load primary analysis") from err
    if raw != _canonical(data) + b"\n":
        raise DenominatorAuditError("primary analysis is not canonical JSON")
    return data


def _fraction(record, label):
    if not isinstance(record, dict):
        raise DenominatorAuditError("{} is not a fraction record".format(label))
    numerator = record.get("numerator")
    denominator = record.get("denominator")
    value = record.get("value")
    if (
        type(numerator) is not int
        or type(denominator) is not int
        or denominator <= 0
        or type(value) not in (int, float)
    ):
        raise DenominatorAuditError("{} is not an exact fraction".format(label))
    result = Fraction(numerator, denominator)
    if (
        (result.numerator, result.denominator) != (numerator, denominator)
        or float(result) != value
    ):
        raise DenominatorAuditError("{} fraction record disagrees".format(label))
    return result


def _primary_identity(data):
    if (
        not isinstance(data, dict)
        or data.get("schema") != Primary.SCHEMA
        or data.get("protocol") != Holdout.PROTOCOL
        or data.get("analysis_protocol") != Holdout.ANALYSIS_PROTOCOL
        or data.get("frozen_protocol_sha256") != Holdout.PROTOCOL_SHA256
    ):
        raise DenominatorAuditError("primary analysis identity changed")
    expected_scope = {
        "tasks": Holdout.COHORT_TASKS,
        "domains": Holdout.COHORT_DOMAINS,
        "configurations": Holdout.CONFIG_COUNT,
        "cells": Holdout.CELL_COUNT,
        "minimum_domains": Holdout.MIN_DOMAINS,
        "minimum_tasks_with_comparable_pairs": (
            Holdout.MIN_TASKS_WITH_COMPARABLE_PAIRS
        ),
    }
    if data.get("scope") != expected_scope:
        raise DenominatorAuditError("primary analysis scope changed")


def _domain_universe(data):
    try:
        rows = data["mechanism"]["representation_shared"]["support"][
            "by_domain"
        ]
    except (KeyError, TypeError) as err:
        raise DenominatorAuditError("primary domain universe is missing") from err
    if not isinstance(rows, list):
        raise DenominatorAuditError("primary domain universe is invalid")
    domains = [row.get("domain") for row in rows if isinstance(row, dict)]
    if (
        len(domains) != Holdout.COHORT_DOMAINS
        or len(set(domains)) != Holdout.COHORT_DOMAINS
        or any(type(domain) is not str or not domain for domain in domains)
    ):
        raise DenominatorAuditError("primary domain universe changed")
    return set(domains)


def _group_observations(data):
    observations = data.get("observations")
    if not isinstance(observations, list):
        raise DenominatorAuditError("primary observations are missing")
    grouped = defaultdict(dict)
    for index, row in enumerate(observations):
        if not isinstance(row, dict):
            raise DenominatorAuditError("primary observation is not an object")
        domain = row.get("domain")
        problem = row.get("problem")
        semantic_id = row.get("semantic_id")
        if not all(isinstance(value, str) and value for value in (domain, problem)):
            raise DenominatorAuditError("primary observation identity is invalid")
        try:
            semantic_key = _canonical(semantic_id)
        except DenominatorAuditError as err:
            raise DenominatorAuditError(
                "primary semantic identity is invalid"
            ) from err
        task = (domain, problem)
        if semantic_key in grouped[task]:
            raise DenominatorAuditError("primary semantic observation is duplicated")
        integers = {}
        for field in (
            "semantic_union_effort",
            "actual_effort",
            "B_profile",
            "B_width",
            "B_add",
        ):
            value = row.get(field)
            if type(value) is not int or value < 0:
                raise DenominatorAuditError(
                    "primary observation has invalid {}".format(field)
                )
            integers[field] = value
        union = integers["semantic_union_effort"]
        if union <= 0:
            raise DenominatorAuditError("eligible observation has zero union effort")
        fragmentation = _fraction(row.get("fragmentation"), "fragmentation")
        r_profile = _fraction(row.get("R_profile"), "R_profile")
        if fragmentation != Fraction(integers["actual_effort"], union):
            raise DenominatorAuditError("fragmentation arithmetic changed")
        if r_profile != Fraction(integers["B_profile"], union):
            raise DenominatorAuditError("R_profile arithmetic changed")
        grouped[task][semantic_key] = {
            "domain": domain,
            "problem": problem,
            "task": task,
            "semantic_id": semantic_id,
            **integers,
            "R_profile": r_profile,
            "_inverse_union": Fraction(1, union),
            "_fragmentation": (
                fragmentation.numerator,
                fragmentation.denominator,
            ),
        }
    return grouped


def _summary_value(summary, predictor, field="equal_domain_macro"):
    try:
        record = summary["predictors"][predictor][field]
    except (KeyError, TypeError) as err:
        raise DenominatorAuditError(
            "comparison lacks {} {}".format(predictor, field)
        ) from err
    return _fraction(record, "{} {}".format(predictor, field))


def _lodo(summary, predictor):
    try:
        records = summary["predictors"][predictor][
            "leave_one_domain_out"
        ]["values"]
    except (KeyError, TypeError) as err:
        raise DenominatorAuditError(
            "comparison lacks {} LODO".format(predictor)
        ) from err
    if not isinstance(records, dict) or len(records) != Holdout.COHORT_DOMAINS:
        raise DenominatorAuditError("LODO universe changed")
    return {
        domain: _fraction(record, "{} LODO {}".format(predictor, domain))
        for domain, record in records.items()
    }


def _support(summary):
    support = summary.get("support") or {}
    return (
        type(support.get("eligible_domains")) is int
        and support["eligible_domains"] >= P.MIN_DOMAINS
        and type(support.get("tasks_with_comparable_pairs")) is int
        and support["tasks_with_comparable_pairs"]
        >= P.MIN_TASKS_WITH_COMPARABLE_PAIRS
    )


def decision_gates(denominator, absolute):
    rp = _summary_value(denominator, "profile")
    null = _summary_value(denominator, "inverse_union")
    rp_lodo = _lodo(denominator, "profile")
    null_lodo = _lodo(denominator, "inverse_union")
    bp = _summary_value(absolute, "profile")
    bw = _summary_value(absolute, "width")
    ba = _summary_value(absolute, "add")
    bp_lodo = _lodo(absolute, "profile")
    denominator_criteria = {
        "support": _support(denominator),
        "profile_macro_at_least_0_70": rp >= Fraction(7, 10),
        "profile_lodo_at_least_0_65": all(
            value >= Fraction(13, 20) for value in rp_lodo.values()
        ),
        "profile_beats_inverse_union_by_0_20": (
            rp >= null + Fraction(1, 5)
        ),
        "profile_beats_inverse_union_in_every_lodo": all(
            rp_lodo[domain] > null_lodo[domain] for domain in rp_lodo
        ),
    }
    absolute_criteria = {
        "support": _support(absolute),
        "profile_macro_at_least_0_70": bp >= Fraction(7, 10),
        "profile_lodo_at_least_0_65": all(
            value >= Fraction(13, 20) for value in bp_lodo.values()
        ),
        "profile_within_0_02_of_width": bp >= bw - Fraction(1, 50),
        "profile_within_0_02_of_add": bp >= ba - Fraction(1, 50),
    }
    return {
        "denominator_artifact_robustness": {
            "pass": all(denominator_criteria.values()),
            "criteria": denominator_criteria,
        },
        "absolute_certificate_robustness": {
            "pass": all(absolute_criteria.values()),
            "criteria": absolute_criteria,
        },
    }


def make_analysis(primary):
    P.validate_protocol()
    _primary_identity(primary)
    domains = _domain_universe(primary)
    grouped = _group_observations(primary)
    try:
        denominator = Predictor._shared_pairwise_comparison(
            grouped,
            {
                "profile": ("R_profile", "same"),
                "inverse_union": ("_inverse_union", "same"),
            },
            "_fragmentation",
            domains,
        )
        absolute = Predictor._shared_pairwise_comparison(
            grouped,
            {
                "profile": ("B_profile", "same"),
                "width": ("B_width", "same"),
                "add": ("B_add", "same"),
            },
            "actual_effort",
            domains,
        )
    except Predictor.PredictorAnalysisError as err:
        raise DenominatorAuditError(str(err)) from err
    primary_absolute = primary.get("mechanism", {}).get(
        "absolute_certificate_shared"
    )
    if absolute != primary_absolute:
        raise DenominatorAuditError(
            "recomputed absolute comparison differs from primary analysis"
        )
    return {
        "schema": SCHEMA,
        "protocol": P.PROTOCOL,
        "frozen_protocol_sha256": P.PROTOCOL_SHA256,
        "source_schema": Primary.SCHEMA,
        "source_analysis_protocol": Holdout.ANALYSIS_PROTOCOL,
        "scope": {
            "eligible_observations": sum(
                len(items) for items in grouped.values()
            ),
            "tasks_with_eligible_observations": len(grouped),
            "domain_universe": len(domains),
            "minimum_domains": P.MIN_DOMAINS,
            "minimum_tasks_with_comparable_pairs": (
                P.MIN_TASKS_WITH_COMPARABLE_PAIRS
            ),
        },
        "denominator_null_shared": denominator,
        "absolute_certificate_shared": absolute,
        "decision_gates": decision_gates(denominator, absolute),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("primary_analysis", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    result = make_analysis(_load_primary(args.primary_analysis))
    raw = _canonical(result) + b"\n"
    if args.output:
        args.output.write_bytes(raw)
    else:
        print(raw.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        P.ProtocolError,
        DenominatorAuditError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
