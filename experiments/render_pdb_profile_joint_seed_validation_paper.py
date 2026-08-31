#!/usr/bin/env python3
"""Render the sealed unseen-seed validation as paper-facing TeX."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_joint_seed_validation as Analysis
import pdb_profile_joint_seed_validation_protocol as Protocol
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR
    / "artifacts"
    / "pdb-profile-joint-seed-validation"
    / "analysis-v1.json"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "paper"
    / "generated"
    / "pdb-profile-joint-seed-validation-v1.tex"
)
EXPECTED_ANALYSIS_SHA256 = (
    "2b854d13fc92d9f394a2248271e1173d66bd43f1360fee1ce44564c9627cb3b7"
)
MAX_ANALYSIS_BYTES = 64 * 1024 * 1024
MAX_TEX_BYTES = 64 * 1024


def _load(path):
    path = Path(path)
    raw = Common._read_regular(path, MAX_ANALYSIS_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ANALYSIS_SHA256:
        raise RenderError("analysis digest is not the reviewed production pin")
    expected_sidecar = "{}  {}\n".format(digest, path.name).encode("ascii")
    if Common._read_regular(Path(str(path) + ".sha256"), 256) != expected_sidecar:
        raise RenderError("analysis sidecar differs from the pinned artifact")
    try:
        data = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RenderError("analysis is not ASCII JSON") from err
    if raw != Common._canonical_json(data) + b"\n":
        raise RenderError("analysis is not canonical ASCII JSON plus one newline")
    return data, digest


def _mapping(value, label):
    return Common._mapping(value, label)


def _integer(value, label, minimum=0):
    return Common._integer(value, label, minimum)


def _optional_fraction(value, label):
    if value is None:
        return None
    return Common._fraction(value, label)


def _decimal(value):
    return "--" if value is None else Common._decimal(value)


def _predictor(comparison, key):
    predictors = _mapping(comparison.get("predictors"), "predictors")
    row = _mapping(predictors.get(key), "predictor {}".format(key))
    macro = _optional_fraction(row.get("equal_domain_macro"), key + " macro")
    micro = _optional_fraction(row.get("micro_concordance"), key + " micro")
    lodo = _mapping(row.get("leave_one_domain_out"), key + " LODO")
    minimum = _optional_fraction(lodo.get("minimum"), key + " LODO minimum")
    maximum = _optional_fraction(lodo.get("maximum"), key + " LODO maximum")
    values = _mapping(lodo.get("values"), key + " LODO values")
    if len(values) != Protocol.COHORT_DOMAINS:
        raise RenderError("{} LODO domain universe changed".format(key))
    for domain, value in values.items():
        if not isinstance(domain, str) or not domain:
            raise RenderError("{} LODO domain identity changed".format(key))
        _optional_fraction(value, "{} LODO {}".format(key, domain))
    return macro, micro, minimum, maximum


def _comparison(data, field, predictor_keys):
    comparison = _mapping(data.get(field), field)
    support = _mapping(comparison.get("support"), field + " support")
    for key in (
        "observation_pairs",
        "target_tied",
        "any_predictor_tied",
        "comparable",
        "tasks_with_comparable_pairs",
        "eligible_domains",
    ):
        _integer(support.get(key), "{} {}".format(field, key))
    by_domain = support.get("by_domain")
    if not isinstance(by_domain, list) or len(by_domain) != Protocol.COHORT_DOMAINS:
        raise RenderError("{} support domain universe changed".format(field))
    predictors = _mapping(comparison.get("predictors"), field + " predictors")
    if set(predictors) != set(predictor_keys):
        raise RenderError("{} predictor set changed".format(field))
    for key in predictor_keys:
        _predictor(comparison, key)
    return comparison


def _joint_cartesian_ratios(observations):
    ratios = []
    for task in observations:
        task = _mapping(task, "task observation")
        seeds = _mapping(task.get("seeds"), "task seed observations")
        if set(seeds) != set(Protocol.LABELS):
            raise RenderError("task seed observation set changed")
        for label in Protocol.LABELS:
            item = _mapping(seeds[label], "seed observation")
            joint = _integer(item.get("B_joint"), "joint certificate", 1)
            cartesian = _integer(
                item.get("B_profile"), "Cartesian certificate", 1
            )
            if joint > cartesian:
                raise RenderError("joint certificate exceeds Cartesian relaxation")
            ratios.append(Fraction(joint, cartesian))
    if not ratios:
        return None, None, 0
    ratios.sort()
    middle = len(ratios) // 2
    median = (
        ratios[middle]
        if len(ratios) % 2
        else (ratios[middle - 1] + ratios[middle]) / 2
    )
    mean = sum(ratios, Fraction()) / len(ratios)
    return median, mean, len(ratios)


def validate(data):
    if data.get("schema") != Analysis.SCHEMA:
        raise RenderError("analysis schema changed")
    if data.get("protocol") != Protocol.PROTOCOL:
        raise RenderError("measurement protocol changed")
    if data.get("analysis_protocol") != Protocol.ANALYSIS_PROTOCOL:
        raise RenderError("analysis protocol changed")
    if data.get("frozen_protocol_sha256") != Protocol.PROTOCOL_SHA256:
        raise RenderError("frozen protocol digest changed")
    if data.get("scope") != {
        "tasks": Protocol.COHORT_TASKS,
        "domains": Protocol.COHORT_DOMAINS,
        "configurations": Protocol.CONFIG_COUNT,
        "cells": Protocol.CELL_COUNT,
        "seeds": list(Protocol.SEEDS),
    }:
        raise RenderError("analysis scope changed")
    outcomes = _mapping(data.get("terminal_outcomes"), "terminal outcomes")
    if sum(_integer(value, "terminal outcome") for value in outcomes.values()) != (
        Protocol.CELL_COUNT
    ):
        raise RenderError("terminal outcomes do not conserve cells")
    statuses = _mapping(data.get("observation_status"), "observation status")
    statuses = {
        key: _integer(value, "observation status")
        for key, value in statuses.items()
    }
    for label in Protocol.LABELS:
        if sum(
            value for key, value in statuses.items()
            if key.startswith(label + ":")
        ) != Protocol.COHORT_TASKS:
            raise RenderError("per-seed observation statuses do not conserve tasks")
    eligible = statuses.get("task_all_eligible", 0)
    if eligible + statuses.get("task_ineligible", 0) != Protocol.COHORT_TASKS:
        raise RenderError("task eligibility statuses do not conserve tasks")
    if (
        statuses.get("seed_pair_distinct_order", 0)
        + statuses.get("seed_pair_identical_order", 0)
        != eligible * 6
    ):
        raise RenderError("seed-pair order statuses do not conserve pairs")
    observations = data.get("task_observations")
    if not isinstance(observations, list) or len(observations) != eligible:
        raise RenderError("task observations do not match eligible tasks")
    primary = _comparison(
        data,
        "primary_joint_vs_inverse_union",
        ("joint", "inverse_union"),
    )
    normalized = _comparison(
        data,
        "normalized_certificates",
        ("joint", "cartesian", "width", "add", "inverse_union"),
    )
    absolute = _comparison(
        data,
        "absolute_certificates",
        ("joint", "cartesian", "width", "add", "union"),
    )
    if data.get("decision_gates") != Analysis.decision_gates(primary, absolute):
        raise RenderError("decision gates contradict the frozen analysis")
    _joint_cartesian_ratios(observations)
    return primary, normalized, absolute, statuses, observations


def _row(label, values):
    return "  {} & {} & [{}, {}] \\\\".format(
        label,
        _decimal(values[0]),
        _decimal(values[2]),
        _decimal(values[3]),
    )


def _gate_word(value):
    if type(value) is not bool:
        raise RenderError("gate result is not Boolean")
    return "pass" if value else "fail"


def render(data, digest):
    primary, normalized, absolute, statuses, observations = validate(data)
    primary_joint = _predictor(primary, "joint")
    primary_null = _predictor(primary, "inverse_union")
    normalized_values = {
        key: _predictor(normalized, key)
        for key in ("joint", "cartesian", "width", "add", "inverse_union")
    }
    absolute_values = {
        key: _predictor(absolute, key)
        for key in ("joint", "cartesian", "width", "add", "union")
    }
    normalized_rows = "%\n" + "\n".join((
        _row("Co-occurring profile $\\mathcal{R}^{\\mathcal J}_{\\pi}$", normalized_values["joint"]),
        _row("Cartesian profile $\\mathcal{R}_{\\pi}$", normalized_values["cartesian"]),
        _row("Maximum-width relaxation", normalized_values["width"]),
        _row("Total-ADD relaxation", normalized_values["add"]),
        _row("Denominator-only null", normalized_values["inverse_union"]),
    ))
    absolute_rows = "%\n" + "\n".join((
        _row("Co-occurring profile $\\mathcal{P}^{\\mathcal J}_{\\pi}$", absolute_values["joint"]),
        _row("Cartesian profile $\\mathcal{P}_{\\pi}$", absolute_values["cartesian"]),
        _row("Maximum-width relaxation", absolute_values["width"]),
        _row("Total-ADD relaxation", absolute_values["add"]),
        _row("Unsplit effort", absolute_values["union"]),
    ))
    primary_support = primary["support"]
    normalized_support = normalized["support"]
    absolute_support = absolute["support"]
    median_ratio, mean_ratio, ratio_count = _joint_cartesian_ratios(observations)
    gates = data["decision_gates"]
    margin = (
        primary_joint[0] - primary_null[0]
        if primary_joint[0] is not None and primary_null[0] is not None
        else None
    )
    lines = [
        "% Generated from the sealed unseen Gamer-seed validation.",
        "% Analysis SHA-256: {}".format(digest),
        Common._macro("SeedValidationTasks", str(Protocol.COHORT_TASKS)),
        Common._macro("SeedValidationDomains", str(Protocol.COHORT_DOMAINS)),
        Common._macro("SeedValidationCells", str(Protocol.CELL_COUNT)),
        Common._macro("SeedValidationEligibleTasks", str(len(observations))),
        Common._macro(
            "SeedValidationDistinctOrderPairs",
            str(statuses.get("seed_pair_distinct_order", 0)),
        ),
        Common._macro(
            "SeedValidationIdenticalOrderPairs",
            str(statuses.get("seed_pair_identical_order", 0)),
        ),
        Common._macro("SeedPrimaryPairs", str(primary_support["comparable"])),
        Common._macro(
            "SeedPrimaryPairTasks",
            str(primary_support["tasks_with_comparable_pairs"]),
        ),
        Common._macro(
            "SeedPrimaryPairDomains", str(primary_support["eligible_domains"])
        ),
        Common._macro("SeedJointMacro", _decimal(primary_joint[0])),
        Common._macro("SeedJointMicro", _decimal(primary_joint[1])),
        Common._macro("SeedJointLodoMin", _decimal(primary_joint[2])),
        Common._macro("SeedJointLodoMax", _decimal(primary_joint[3])),
        Common._macro("SeedNullMacro", _decimal(primary_null[0])),
        Common._macro("SeedNullLodoMin", _decimal(primary_null[2])),
        Common._macro("SeedNullLodoMax", _decimal(primary_null[3])),
        Common._macro("SeedJointNullMargin", _decimal(margin)),
        Common._macro(
            "SeedCartesianMacro", _decimal(normalized_values["cartesian"][0])
        ),
        Common._macro("SeedWidthMacro", _decimal(normalized_values["width"][0])),
        Common._macro("SeedAddMacro", _decimal(normalized_values["add"][0])),
        Common._macro(
            "SeedPrimaryGate",
            _gate_word(gates["joint_beyond_denominator_null"]["pass"]),
        ),
        Common._macro(
            "SeedAbsoluteGate",
            _gate_word(gates["absolute_joint_certificate"]["pass"]),
        ),
        Common._macro(
            "SeedNormalizedPairs", str(normalized_support["comparable"])
        ),
        Common._macro(
            "SeedNormalizedPairTasks",
            str(normalized_support["tasks_with_comparable_pairs"]),
        ),
        Common._macro(
            "SeedNormalizedPairDomains",
            str(normalized_support["eligible_domains"]),
        ),
        Common._macro("SeedAbsolutePairs", str(absolute_support["comparable"])),
        Common._macro(
            "SeedAbsolutePairTasks",
            str(absolute_support["tasks_with_comparable_pairs"]),
        ),
        Common._macro(
            "SeedAbsolutePairDomains", str(absolute_support["eligible_domains"])
        ),
        Common._macro(
            "SeedAbsoluteJointMacro", _decimal(absolute_values["joint"][0])
        ),
        Common._macro(
            "SeedAbsoluteCartesianMacro",
            _decimal(absolute_values["cartesian"][0]),
        ),
        Common._macro(
            "SeedAbsoluteWidthMacro", _decimal(absolute_values["width"][0])
        ),
        Common._macro(
            "SeedAbsoluteAddMacro", _decimal(absolute_values["add"][0])
        ),
        Common._macro(
            "SeedAbsoluteUnionMacro", _decimal(absolute_values["union"][0])
        ),
        Common._macro("SeedJointCartesianRatioCount", str(ratio_count)),
        Common._macro("SeedJointCartesianMedianRatio", _decimal(median_ratio)),
        Common._macro("SeedJointCartesianMeanRatio", _decimal(mean_ratio)),
        Common._macro("SeedNormalizedRows", normalized_rows),
        Common._macro("SeedAbsoluteRows", absolute_rows),
    ]
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


def _write_atomic(path, raw):
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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        if len(EXPECTED_ANALYSIS_SHA256) != 64:
            raise RenderError("production digest pin is not finalized")
        return 0
    data, digest = _load(args.analysis)
    raw = render(data, digest)
    if args.write:
        _write_atomic(args.output, raw)
    elif args.check:
        if Common._read_regular(args.output, MAX_TEX_BYTES) != raw:
            raise RenderError("generated TeX is stale")
    else:
        print(raw.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RenderError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
