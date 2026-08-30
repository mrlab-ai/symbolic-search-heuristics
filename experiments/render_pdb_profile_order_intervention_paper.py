#!/usr/bin/env python3
"""Render the sealed variable-order intervention as paper-facing TeX."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import analyze_pdb_profile_order_intervention as Analysis
import pdb_profile_order_intervention_protocol as Protocol
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR / "artifacts" / "pdb-profile-order-intervention" / "analysis-v1.json"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "paper"
    / "generated"
    / "pdb-profile-order-intervention-v1.tex"
)
EXPECTED_ANALYSIS_SHA256 = (
    "1683e6d743267d444b6d1ce1dfdb24450a24f06150c658ccf49814685210d959"
)
MAX_ANALYSIS_BYTES = 2 * 1024 * 1024
MAX_TEX_BYTES = 64 * 1024


def _load(path):
    path = Path(path)
    raw = Common._read_regular(path, MAX_ANALYSIS_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ANALYSIS_SHA256:
        raise RenderError("analysis digest is not the reviewed production pin")
    sidecar = Path(str(path) + ".sha256")
    expected = "{}  {}\n".format(digest, path.name).encode("ascii")
    if Common._read_regular(sidecar, 256) != expected:
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


def _predictor(comparison, key):
    predictors = _mapping(comparison.get("predictors"), "predictors")
    row = _mapping(predictors.get(key), "predictor {}".format(key))
    macro = Common._fraction(row.get("equal_domain_macro"), key + " macro")
    micro = Common._fraction(row.get("micro_concordance"), key + " micro")
    lodo = _mapping(row.get("leave_one_domain_out"), key + " LODO")
    minimum = Common._fraction(lodo.get("minimum"), key + " LODO minimum")
    maximum = Common._fraction(lodo.get("maximum"), key + " LODO maximum")
    return macro, micro, minimum, maximum


def validate(data):
    if data.get("schema") != Analysis.SCHEMA:
        raise RenderError("analysis schema changed")
    if data.get("protocol") != Protocol.PROTOCOL:
        raise RenderError("measurement protocol changed")
    if data.get("analysis_protocol") != Protocol.ANALYSIS_PROTOCOL:
        raise RenderError("analysis protocol changed")
    if data.get("frozen_protocol_sha256") != Protocol.PROTOCOL_SHA256:
        raise RenderError("frozen protocol digest changed")
    expected_scope = {
        "tasks": Protocol.COHORT_TASKS,
        "domains": Protocol.COHORT_DOMAINS,
        "configurations": Protocol.CONFIG_COUNT,
        "cells": Protocol.CELL_COUNT,
        "minimum_domains": Protocol.MIN_DOMAINS,
        "minimum_tasks_with_comparable_pairs": (
            Protocol.MIN_TASKS_WITH_COMPARABLE_PAIRS
        ),
    }
    if data.get("scope") != expected_scope:
        raise RenderError("analysis scope changed")
    outcomes = _mapping(data.get("terminal_outcomes"), "terminal outcomes")
    if sum(_integer(value, "terminal outcome") for value in outcomes.values()) != (
        Protocol.CELL_COUNT
    ):
        raise RenderError("terminal outcomes do not conserve cells")
    statuses = _mapping(data.get("observation_status"), "observation status")
    expected_statuses = {
        "pair_distinct_order",
        "pair_identical_order",
        "pair_ineligible",
        "pdb_goal_fill_fd:eligible",
        "pdb_goal_fill_fd:unsolved",
        "pdb_goal_fill_gamer:eligible",
        "pdb_goal_fill_gamer:incomplete_profile",
        "pdb_goal_fill_gamer:unsolved",
    }
    if set(statuses) != expected_statuses:
        raise RenderError("observation status taxonomy changed")
    primary = _mapping(data.get("primary_shared"), "primary comparison")
    absolute = _mapping(data.get("absolute_shared"), "absolute comparison")
    for comparison in (primary, absolute):
        support = _mapping(comparison.get("support"), "comparison support")
        for key in (
            "comparable",
            "observation_pairs",
            "tasks_with_comparable_pairs",
            "eligible_domains",
        ):
            _integer(support.get(key), "support {}".format(key))
        for predictor in ("profile", "width", "add"):
            _predictor(comparison, predictor)
    expected_gates = Analysis.decision_gates(primary)
    if data.get("decision_gates") != expected_gates:
        raise RenderError("decision gates contradict the frozen analysis")


def _row(label, values):
    return "  {} & {} & [{}, {}] \\\\".format(
        label,
        Common._decimal(values[0]),
        Common._decimal(values[2]),
        Common._decimal(values[3]),
    )


def render(data, digest):
    validate(data)
    primary = data["primary_shared"]
    absolute = data["absolute_shared"]
    profile = _predictor(primary, "profile")
    width = _predictor(primary, "width")
    add = _predictor(primary, "add")
    absolute_profile = _predictor(absolute, "profile")
    absolute_width = _predictor(absolute, "width")
    absolute_add = _predictor(absolute, "add")
    statuses = data["observation_status"]
    support = primary["support"]
    rows = "%\n" + "\n".join((
        _row("Cut-aligned profile $\\mathcal{R}_{\\pi}$", profile),
        _row("Maximum width relaxation", width),
        _row("Total-ADD Apply relaxation", add),
    ))
    absolute_rows = "%\n" + "\n".join((
        _row("Cut-aligned profile $\\mathcal{P}_{\\pi}$", absolute_profile),
        _row("Maximum width relaxation", absolute_width),
        _row("Total-ADD Apply relaxation", absolute_add),
    ))
    gate = data["decision_gates"]
    lines = [
        "% Generated from the sealed fixed-heuristic variable-order intervention.",
        "% Analysis SHA-256: {}".format(digest),
        Common._macro("OrderTasks", str(Protocol.COHORT_TASKS)),
        Common._macro("OrderDomains", str(Protocol.COHORT_DOMAINS)),
        Common._macro("OrderCells", str(Protocol.CELL_COUNT)),
        Common._macro("OrderPairs", str(support["observation_pairs"])),
        Common._macro("OrderStrictPairs", str(support["comparable"])),
        Common._macro(
            "OrderPairTasks", str(support["tasks_with_comparable_pairs"])
        ),
        Common._macro("OrderPairDomains", str(support["eligible_domains"])),
        Common._macro(
            "OrderDistinctPairs", str(statuses["pair_distinct_order"])
        ),
        Common._macro(
            "OrderIdenticalPairs", str(statuses["pair_identical_order"])
        ),
        Common._macro("OrderProfileMacro", Common._decimal(profile[0])),
        Common._macro("OrderProfileMicro", Common._decimal(profile[1])),
        Common._macro("OrderProfileLodoMin", Common._decimal(profile[2])),
        Common._macro("OrderProfileLodoMax", Common._decimal(profile[3])),
        Common._macro("OrderWidthMacro", Common._decimal(width[0])),
        Common._macro("OrderAddMacro", Common._decimal(add[0])),
        Common._macro(
            "OrderAbsoluteProfileMacro", Common._decimal(absolute_profile[0])
        ),
        Common._macro(
            "OrderAbsoluteWidthMacro", Common._decimal(absolute_width[0])
        ),
        Common._macro(
            "OrderAbsoluteAddMacro", Common._decimal(absolute_add[0])
        ),
        Common._macro(
            "OrderUsefulGate",
            "pass" if gate["predicts_order_sensitivity"]["pass"] else "fail",
        ),
        Common._macro(
            "OrderSharperGate",
            "pass" if gate["sharper_order_predictor"]["pass"] else "fail",
        ),
        Common._macro("OrderPredictorRows", rows),
        Common._macro("OrderAbsoluteRows", absolute_rows),
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
            raise RenderError("production digest pin is invalid")
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
