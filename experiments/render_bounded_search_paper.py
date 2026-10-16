#!/usr/bin/env python3
"""Render paper macros for the bounded-search study and the Q2 summary table.

Reads only pinned frozen analysis artifacts and computes no new estimand:
the bounded-search analysis for its macros, and additionally the
fragmentation-remedy and unsplit-bound analyses for the summary table, whose
entries are coverage differences to blind forward search of the same study
with the significance verdicts of that study's primary tests.  Rendering
fails closed unless the bounded-search claims are those that the paper text
states (EXPECTED_CLAIMS).

  --write   write paper/generated/bounded-search-v1.tex
  --check   compare the generated file byte for byte
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import bounded_search_protocol as P
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
ARTIFACTS = SCRIPT_DIR / "artifacts"
DEFAULT_ANALYSIS = ARTIFACTS / "bounded-search" / "analysis-v1.json"
PINS = {
    "bounded": (DEFAULT_ANALYSIS,
                "f018236c637f910e07dc7c31ab42ec23fba0377c12b61d3877a83f96c3694ff8"),
    "remedy": (ARTIFACTS / "fragmentation-remedy" / "analysis-v1.json",
               "773234a6f4757265f05899cb6eededfa7eec3d70ebc6db96e84fa1e8b9ae024b"),
    "unsplit": (ARTIFACTS / "unsplit-bound" / "analysis-v1.json",
                "26ca6de0e34e2a468e2bf62bf9cbaf33bb6216bf0099d83951c8c84bee03031f"),
}
EXPECTED_CLAIMS = {
    "H1:ms_bounded": "not_significant",
    "H1:pdb_bounded": "better",
    "H1:pot_bounded": "better",
    "H2:ms_bounded": "not_significant",
    "H2:pdb_bounded": "not_significant",
    "H2:pot_bounded": "not_significant",
    "H3:ms_bounded": "not_significant",
    "H3:pdb_bounded": "not_significant",
    "H3:pot_bounded": "not_significant",
}
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "bounded-search-v1.tex"
)
MAX_ANALYSIS_BYTES = 1024 * 1024
MAX_TEX_BYTES = 16 * 1024
FAMILIES = (("ms", "Ms"), ("pdb", "Pdb"), ("pot", "Pot"))


def _load_pinned(path, expected):
    raw = Common._read_regular(path, MAX_ANALYSIS_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected:
        raise RenderError("{} is not the frozen pin".format(path))
    sidecar = "{}  {}\n".format(digest, Path(path).name).encode("ascii")
    if Common._read_regular(Path(str(path) + ".sha256"), 256) != sidecar:
        raise RenderError("{} sidecar differs from the pin".format(path))
    data = json.loads(raw.decode("ascii"))
    if raw != Common._canonical_json(data) + b"\n":
        raise RenderError("{} is not canonical".format(path))
    return data, digest


def _load(path):
    if Path(path).resolve() != DEFAULT_ANALYSIS.resolve():
        raise RenderError("unexpected bounded-search analysis path")
    loaded = {name: _load_pinned(*pin) for name, pin in PINS.items()}
    data, digest = loaded["bounded"]
    if data.get("claims") != EXPECTED_CLAIMS:
        raise RenderError("claims differ from those the paper states")
    if data.get("protocol_sha256") != P.PROTOCOL_SHA256:
        raise RenderError("analysis names a different protocol")
    return {name: value[0] for name, value in loaded.items()}, digest


def _delta(value):
    if value > 0:
        return "+{}".format(value)
    if value < 0:
        return "$-${}".format(-value)
    return "0"


def _marked(study, label, plain_test, blind_test):
    coverage = study["coverage"]
    value = _delta(coverage[label]["solved"] - coverage["blind_fw"]["solved"])
    marks = ""
    tests = study["primary_tests"]
    if plain_test and tests[plain_test]["significant"]:
        marks += r"\dagger"
    if blind_test and tests[blind_test]["significant"]:
        marks += "*"
    return value + ("$^{{{}}}$".format(marks) if marks else "")


def render(all_data, digest):
    data = all_data["bounded"]
    coverage = data["coverage"]
    tests = data["primary_tests"]

    def fixed(value, places=2):
        return "{:.{}f}".format(float(value), places)

    macros = [("BdCells", "\\num{{{}}}".format(P.CELL_COUNT))]
    for label, name in (("blind_fw", "BlindFw"), ("blind_bd", "BlindBd"),
                        ("blind_bounded", "BlindBounded")):
        macros.append(("BdSolved" + name, str(coverage[label]["solved"])))
    for family, prefix in FAMILIES:
        plain, bounded = family + "_plain", family + "_bounded"
        mechanism = data["mechanism"][family]
        macros += [
            ("BdSolved{}Plain".format(prefix), str(coverage[plain]["solved"])),
            ("BdSolved{}Bounded".format(prefix), str(coverage[bounded]["solved"])),
        ]
        for test, name in (("H1", "VsPlain"), ("H2", "VsBlind"),
                           ("H3", "VsBlindBounded")):
            record = tests["{}:{}".format(test, bounded)]
            macros += [("Bd{}{}Gains".format(prefix, name), str(record["gains"])),
                       ("Bd{}{}Losses".format(prefix, name), str(record["losses"]))]
        macros += [
            ("Bd{}EffortPlain".format(prefix),
             fixed(mechanism["plain"]["effort_ratio_median"])),
            ("Bd{}EffortBounded".format(prefix),
             fixed(mechanism["bounded"]["effort_ratio_median"])),
        ]
    first = data["first_phase"]
    ratios = [first[label]["bound_ratio_median"] for label in P.BOUNDED_LABELS]
    optimal = [first[label]["bound_optimal"] for label in P.BOUNDED_LABELS]
    solved = [first[label]["solved_with_bound"] for label in P.BOUNDED_LABELS]
    macros += [
        ("BdBoundExcessMin", "{:.0f}".format(100 * (min(ratios) - 1))),
        ("BdBoundExcessMax", "{:.0f}".format(100 * (max(ratios) - 1))),
        ("BdBoundOptimalMin", str(min(optimal))),
        ("BdBoundOptimalMax", str(max(optimal))),
        ("BdBoundSolvedMin", str(min(solved))),
        ("BdBoundSolvedMax", str(max(solved))),
    ]
    remedy, unsplit = all_data["remedy"], all_data["unsplit"]
    # One group per study, each with its own \bddastar row, since coverage
    # near the time limit varies between launches.
    groups = (
        (remedy, (
            (r"\bddastar", "{}_plain", None, None),
            ("prune-only", "{}_prune", "H1:{}_prune", "H2:{}_prune"),
            ("batched", "{}_batch", "H1:{}_batch", "H2:{}_batch"),
        )),
        (unsplit, (
            (r"\bddastar", "{}_plain", None, None),
            ("unsplit", "{}_unsplit", "H1:{}_unsplit", "H2:{}_unsplit"),
        )),
        (data, (
            (r"\bddastar", "{}_plain", None, None),
            ("bounded", "{}_bounded", "H1:{}_bounded", "H2:{}_bounded"),
        )),
    )
    rows = []
    for index, (study, specs) in enumerate(groups):
        if index:
            rows.append(r"\midrule")
        for name, label, plain_test, blind_test in specs:
            cells = [
                _marked(study, label.format(family),
                        plain_test.format(family) if plain_test else None,
                        blind_test.format(family) if blind_test else None)
                for family, _ in FAMILIES
            ]
            rows.append("{} & {} \\\\".format(name, " & ".join(cells)))
    macros.append(("RemedySummaryRows", "\n".join(rows)))
    names = [name for name, _ in macros]
    if len(set(names)) != len(names):
        raise RenderError("duplicate macro name")
    lines = [
        "% Generated from the frozen bounded-search, fragmentation-remedy and",
        "% unsplit-bound analyses.",
        "% Analysis SHA-256: {}".format(digest),
    ] + [Common._macro(name, value) for name, value in macros]
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


def _write_atomic(path, raw):
    path = Path(path)
    if path.resolve() != DEFAULT_OUTPUT.resolve():
        raise RenderError("--write is restricted to the generated-paper path")
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


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    raw = render(*_load(args.analysis))
    if args.write:
        _write_atomic(args.output, raw)
    elif Common._read_regular(args.output, MAX_TEX_BYTES) != raw:
        raise RenderError("generated TeX is stale")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RenderError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
