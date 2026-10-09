#!/usr/bin/env python3
"""Render post-hoc certificate slack on the sealed holdout as paper-facing TeX.

This is a descriptive, post-hoc summary of the sealed prospective-holdout
analysis.  It changes no frozen estimand or gate.  For every eligible
heuristic observation, the slack of a normalized certificate R is R / frag,
the factor by which the certificate overestimates the observed bucket
fragmentation (Theorem: frag <= R_profile <= R_width).  Quantiles use the
lower nearest rank, sorted[floor(p * (N - 1))], on exact fractions.
"""

from __future__ import annotations

import argparse
import os
import tempfile
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

import render_pdb_profile_certificate_holdout_paper as Holdout
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = Holdout.DEFAULT_ANALYSIS
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "pdb-profile-certificate-slack-v1.tex"
)
EXPECTED_OBSERVATIONS = 2891
CERTIFICATES = (("Profile", "R_profile"), ("Width", "R_width"), ("Add", "R_add"))
QUANTILES = (("Ten", Fraction(1, 10)), ("Median", Fraction(1, 2)),
             ("Ninety", Fraction(9, 10)))
MAX_TEX_BYTES = 16 * 1024


def _fraction(record, label):
    record = Common._mapping(record, label)
    numerator = record.get("numerator")
    denominator = record.get("denominator")
    if type(numerator) is not int or type(denominator) is not int:
        raise RenderError("{} is not an exact fraction".format(label))
    if numerator <= 0 or denominator <= 0:
        raise RenderError("{} must be positive".format(label))
    return Fraction(numerator, denominator)


def _quantile(values, p):
    ordered = sorted(values)
    return ordered[int(p * (len(ordered) - 1))]


def _fixed(value, places):
    quantum = Decimal(1).scaleb(-places)
    rounded = (Decimal(value.numerator) / Decimal(value.denominator)).quantize(
        quantum, rounding=ROUND_HALF_UP
    )
    return format(rounded, ".{}f".format(places))


def summarize(data):
    observations = data.get("observations")
    if not isinstance(observations, list):
        raise RenderError("analysis lacks its observation list")
    if len(observations) != EXPECTED_OBSERVATIONS:
        raise RenderError("observation count differs from the sealed holdout")
    fragmentation = []
    slack = {key: [] for _, key in CERTIFICATES}
    for index, item in enumerate(observations):
        item = Common._mapping(item, "observation {}".format(index))
        frag = _fraction(item.get("fragmentation"), "fragmentation")
        fragmentation.append(frag)
        for _, key in CERTIFICATES:
            value = _fraction(item.get(key), key)
            if value < frag:
                raise RenderError("certificate {} is below fragmentation".format(key))
            slack[key].append(value / frag)
        if slack["R_width"][-1] < slack["R_profile"][-1]:
            raise RenderError("width relaxation is tighter than the profile")
    return fragmentation, slack


def render(data, digest):
    fragmentation, slack = summarize(data)
    above_one = sum(1 for value in fragmentation if value > 1)
    lines = [
        "% Generated post hoc from the sealed prospective-holdout analysis.",
        "% Descriptive only; changes no frozen estimand or gate.",
        "% Holdout analysis SHA-256: {}".format(digest),
        Common._macro("SlackObservations", str(len(fragmentation))),
        Common._macro(
            "SlackFragAboveOnePercent",
            _fixed(Fraction(100 * above_one, len(fragmentation)), 0),
        ),
        Common._macro("SlackFragMax", _fixed(max(fragmentation), 1)),
    ]
    for name, p in QUANTILES:
        lines.append(Common._macro(
            "SlackFrag" + name, _fixed(_quantile(fragmentation, p), 2)
        ))
    for label, key in CERTIFICATES:
        for name, p in QUANTILES:
            lines.append(Common._macro(
                "Slack" + label + name, _fixed(_quantile(slack[key], p), 1)
            ))
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


def _self_test():
    def record(numerator, denominator=1):
        return {"numerator": numerator, "denominator": denominator}

    data = {"observations": [
        {"fragmentation": record(1), "R_profile": record(2),
         "R_width": record(3), "R_add": record(4)},
        {"fragmentation": record(2), "R_profile": record(2),
         "R_width": record(8), "R_add": record(8)},
    ]}
    saved = globals()["EXPECTED_OBSERVATIONS"]
    globals()["EXPECTED_OBSERVATIONS"] = 2
    try:
        fragmentation, slack = summarize(data)
        if slack["R_profile"] != [2, 1] or max(fragmentation) != 2:
            raise RenderError("self-test summary is wrong")
        broken = {"observations": [dict(data["observations"][0],
                                        R_profile=record(1, 2))]}
        globals()["EXPECTED_OBSERVATIONS"] = 1
        try:
            summarize(broken)
        except RenderError:
            pass
        else:
            raise RenderError("self-test accepted a certificate below frag")
    finally:
        globals()["EXPECTED_OBSERVATIONS"] = saved
    return 0


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
        os.chmod(temporary, 0o644)
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
        return _self_test()
    data, digest = Holdout._load(
        args.analysis,
        Holdout.EXPECTED_ANALYSIS_SHA256,
        Holdout.MAX_ANALYSIS_BYTES,
        "holdout analysis",
    )
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
