#!/usr/bin/env python3
"""Render the sealed semantic-union analysis as paper-facing TeX macros."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_semantic_union as Analysis
import pdb_profile_semantic_union_protocol as Protocol


class RenderError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR / "artifacts" / "pdb-profile-semantic-union" / "analysis-v1.json"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "paper"
    / "generated"
    / "pdb-profile-semantic-union-v1.tex"
)
EXPECTED_ANALYSIS_SHA256 = (
    "3029d547912a65552bf7cb1eae87e57ba7a159f0b7433366ab7f60322c96ddfe"
)
MAX_ANALYSIS_BYTES = 4 * 1024 * 1024
MAX_TEX_BYTES = 64 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(value):
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


def _read_regular(path, maximum):
    path = Path(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as err:
        raise RenderError("cannot open {}: {}".format(path, err)) from err
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise RenderError("{} must be a single-link regular file".format(path))
        if before.st_size > maximum:
            raise RenderError("{} exceeds its size limit".format(path))
        raw = b""
        while len(raw) <= maximum:
            block = os.read(descriptor, min(1024 * 1024, maximum + 1 - len(raw)))
            if not block:
                break
            raw += block
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or len(raw) != before.st_size:
            raise RenderError("{} changed while read".format(path))
        return raw
    finally:
        os.close(descriptor)


def _load(path):
    raw = _read_regular(path, MAX_ANALYSIS_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ANALYSIS_SHA256:
        raise RenderError("analysis digest is not the reviewed production pin")
    sidecar = Path(str(path) + ".sha256")
    sidecar_raw = _read_regular(sidecar, 256)
    expected_sidecar = "{}  {}\n".format(digest, Path(path).name).encode("ascii")
    if sidecar_raw != expected_sidecar:
        raise RenderError("analysis sidecar differs from the pinned artifact")
    try:
        data = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RenderError("analysis is not ASCII JSON") from err
    if raw != _canonical_json(data) + b"\n":
        raise RenderError("analysis is not canonical ASCII JSON plus one newline")
    return data, digest


def _mapping(value, label):
    if not isinstance(value, dict):
        raise RenderError("{} must be an object".format(label))
    return value


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise RenderError("{} must be an integer >= {}".format(label, minimum))
    return value


def _fraction(record, label):
    record = _mapping(record, label)
    numerator = record.get("numerator")
    denominator = record.get("denominator")
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise RenderError("{} is not an exact fraction".format(label))
    result = Fraction(numerator, denominator)
    if (result.numerator, result.denominator) != (numerator, denominator):
        raise RenderError("{} is not reduced".format(label))
    value = record.get("value")
    if type(value) not in (int, float) or float(result) != value:
        raise RenderError("{} decimal disagrees with its exact fraction".format(label))
    return result


def _decimal(value):
    rounded = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        Decimal("0.001"), rounding=ROUND_HALF_UP
    )
    return format(rounded, ".3f")


def _macro(name, value):
    if re.fullmatch(r"[A-Za-z]+", name) is None:
        raise RenderError("invalid macro name")
    return "\\newcommand{{\\{}}}{{{}}}".format(name, value)


def _predictor(data, key):
    predictors = _mapping(
        _mapping(data.get("shared_primary_comparison"), "shared comparison").get(
            "predictors"
        ),
        "shared predictors",
    )
    row = _mapping(predictors.get(key), "predictor {}".format(key))
    macro = _fraction(row.get("equal_domain_macro"), key + " macro")
    loo = _mapping(row.get("leave_one_domain_out"), key + " LODO")
    minimum = _fraction(loo.get("minimum"), key + " LODO minimum")
    maximum = _fraction(loo.get("maximum"), key + " LODO maximum")
    return macro, minimum, maximum


def validate(data):
    if data.get("schema") != Analysis.SCHEMA:
        raise RenderError("analysis schema changed")
    if data.get("protocol") != Protocol.PROTOCOL:
        raise RenderError("measurement protocol changed")
    if data.get("analysis_protocol") != Protocol.ANALYSIS_PROTOCOL:
        raise RenderError("analysis protocol changed")
    if data.get("frozen_protocol_sha256") != Protocol.PROTOCOL_SHA256:
        raise RenderError("frozen protocol digest changed")
    scope = _mapping(data.get("scope"), "scope")
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
    if scope != expected_scope:
        raise RenderError("analysis scope changed")
    statuses = _mapping(data.get("observation_status"), "observation status")
    if set(statuses) != {"eligible", "incomplete_profile", "unsolved"}:
        raise RenderError("observation status taxonomy changed")
    if sum(_integer(value, "observation status") for value in statuses.values()) != (
        Protocol.CELL_COUNT
    ):
        raise RenderError("observation statuses do not conserve cells")
    shared = _mapping(data.get("shared_primary_comparison"), "shared comparison")
    support = _mapping(shared.get("support"), "shared support")
    for key in ("comparable", "tasks_with_comparable_pairs", "eligible_domains"):
        _integer(support.get(key), "shared support {}".format(key))
    for key in ("cofactor_width", "total_add_nodes", "quality"):
        _predictor(data, key)
    gate = _mapping(data.get("decision_gate"), "decision gate")
    criteria = _mapping(gate.get("criteria"), "decision criteria")
    expected_criteria = {
        "at_least_31_domains",
        "at_least_184_tasks",
        "width_macro_at_least_0_65",
        "every_width_lodo_at_least_0_60",
        "width_beats_quality",
        "width_within_0_02_of_total_add",
    }
    if set(criteria) != expected_criteria or any(
        type(value) is not bool for value in criteria.values()
    ):
        raise RenderError("decision criteria changed")
    if type(gate.get("pass")) is not bool or gate["pass"] != all(criteria.values()):
        raise RenderError("decision gate contradicts its criteria")
    overhead = _mapping(data.get("instrumentation_overhead"), "overhead")
    ratio = overhead.get("pooled_new_over_old_planner_time")
    if type(ratio) not in (int, float) or not 0 <= ratio < 100:
        raise RenderError("instrumentation overhead ratio is invalid")


def render(data, digest):
    validate(data)
    support = data["shared_primary_comparison"]["support"]
    statuses = data["observation_status"]
    width = _predictor(data, "cofactor_width")
    add = _predictor(data, "total_add_nodes")
    quality = _predictor(data, "quality")
    rows = [
        ("Cofactor width $W$",) + tuple(_decimal(value) for value in width),
        ("Total ADD size $U$",) + tuple(_decimal(value) for value in add),
        ("Information-quality score",) + tuple(
            _decimal(value) for value in quality
        ),
    ]
    row_text = "%\n" + "\n".join(
        "  {} & {} & [{}, {}] \\\\".format(*row) for row in rows
    )
    gate = data["decision_gate"]
    overhead = data["instrumentation_overhead"]["pooled_new_over_old_planner_time"]
    lines = [
        "% Generated from the sealed corrected semantic-union analysis.",
        "% Analysis SHA-256: {}".format(digest),
        _macro("SemanticUnionTasks", str(Protocol.COHORT_TASKS)),
        _macro("SemanticUnionDomains", str(Protocol.COHORT_DOMAINS)),
        _macro("SemanticUnionCells", str(Protocol.CELL_COUNT)),
        _macro("SemanticUnionEligible", str(statuses["eligible"])),
        _macro("SemanticUnionIncomplete", str(statuses["incomplete_profile"])),
        _macro("SemanticUnionPairs", str(support["comparable"])),
        _macro("SemanticUnionPairTasks", str(support["tasks_with_comparable_pairs"])),
        _macro("SemanticUnionPairDomains", str(support["eligible_domains"])),
        _macro(
            "SemanticUnionTaskFloor",
            str(Protocol.MIN_TASKS_WITH_COMPARABLE_PAIRS),
        ),
        _macro("SemanticUnionWidthMacro", _decimal(width[0])),
        _macro("SemanticUnionWidthLodoMin", _decimal(width[1])),
        _macro("SemanticUnionWidthLodoMax", _decimal(width[2])),
        _macro("SemanticUnionAddMacro", _decimal(add[0])),
        _macro("SemanticUnionQualityMacro", _decimal(quality[0])),
        _macro("SemanticUnionGate", "pass" if gate["pass"] else "fail"),
        _macro("SemanticUnionInstrumentationRatio", "{:.3f}".format(overhead)),
        _macro("SemanticUnionPredictorRows", row_text),
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


def self_test():
    if _decimal(Fraction(157, 200)) != "0.785":
        raise RenderError("decimal rounding self-test failed")
    if not SHA256_RE.fullmatch(EXPECTED_ANALYSIS_SHA256):
        raise RenderError("production digest pin is invalid")


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
        self_test()
        return 0
    data, digest = _load(args.analysis)
    raw = render(data, digest)
    if args.write:
        _write_atomic(args.output, raw)
    elif args.check:
        if _read_regular(args.output, MAX_TEX_BYTES) != raw:
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
