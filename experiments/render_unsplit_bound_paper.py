#!/usr/bin/env python3
"""Render paper macros for the unsplit-bound study.

Reads only the pinned frozen analysis artifact of `analyze_unsplit_bound.py`
and computes no new estimand.  Rendering fails closed unless the artifact's
claims are those that the paper text states (EXPECTED_CLAIMS).

  --write   write paper/generated/unsplit-bound-v1.tex
  --check   compare the generated file byte for byte
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import unsplit_bound_protocol as P
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR / "artifacts" / "unsplit-bound" / "analysis-v1.json"
)
EXPECTED_ANALYSIS_SHA256 = (
    "26ca6de0e34e2a468e2bf62bf9cbaf33bb6216bf0099d83951c8c84bee03031f"
)
EXPECTED_CLAIMS = {
    "H1:ms_unsplit": "not_significant",
    "H1:pdb_unsplit": "not_significant",
    "H1:pot_unsplit": "not_significant",
    "H2:ms_unsplit": "not_significant",
    "H2:pdb_unsplit": "not_significant",
    "H2:pot_unsplit": "worse",
}
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "unsplit-bound-v1.tex"
)
MAX_ANALYSIS_BYTES = 1024 * 1024
MAX_TEX_BYTES = 16 * 1024


def _load(path):
    raw = Common._read_regular(path, MAX_ANALYSIS_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ANALYSIS_SHA256:
        raise RenderError("analysis artifact is not the frozen pin")
    sidecar = "{}  {}\n".format(digest, Path(path).name).encode("ascii")
    if Common._read_regular(Path(str(path) + ".sha256"), 256) != sidecar:
        raise RenderError("analysis sidecar differs from the pinned artifact")
    data = json.loads(raw.decode("ascii"))
    if raw != Common._canonical_json(data) + b"\n":
        raise RenderError("analysis artifact is not canonical")
    if data.get("claims") != EXPECTED_CLAIMS:
        raise RenderError("claims differ from those the paper states")
    if data.get("protocol_sha256") != P.PROTOCOL_SHA256:
        raise RenderError("analysis names a different protocol")
    return data, digest


def render(data, digest):
    def fixed(value, places=2):
        return "{:.{}f}".format(float(value), places)

    coverage = data["coverage"]
    tests = data["primary_tests"]
    macros = [("UbCells", "\\num{{{}}}".format(P.CELL_COUNT))]
    for label, name in (("blind_fw", "BlindFw"), ("blind_bd", "BlindBd")):
        macros.append(("UbSolved" + name, str(coverage[label]["solved"])))
    shares, plains, unsplits = [], [], []
    for family, prefix in (("ms", "Ms"), ("pdb", "Pdb"), ("pot", "Pot")):
        plain, unsplit = family + "_plain", family + "_unsplit"
        mechanism = data["mechanism"][family]
        iterations = data["iterations"][family]
        h1, h2 = tests["H1:" + unsplit], tests["H2:" + unsplit]
        macros += [
            ("UbSolved{}Plain".format(prefix), str(coverage[plain]["solved"])),
            ("UbSolved{}Unsplit".format(prefix), str(coverage[unsplit]["solved"])),
            ("Ub{}VsPlainGains".format(prefix), str(h1["gains"])),
            ("Ub{}VsPlainLosses".format(prefix), str(h1["losses"])),
            ("Ub{}VsBlindGains".format(prefix), str(h2["gains"])),
            ("Ub{}VsBlindLosses".format(prefix), str(h2["losses"])),
            ("Ub{}EffortPlain".format(prefix),
             fixed(mechanism["plain"]["effort_ratio_median"])),
            ("Ub{}EffortUnsplit".format(prefix),
             fixed(mechanism["unsplit"]["effort_ratio_median"])),
            ("Ub{}TimePlain".format(prefix),
             fixed(mechanism["plain"]["time_ratio_median"])),
            ("Ub{}TimeUnsplit".format(prefix),
             fixed(mechanism["unsplit"]["time_ratio_median"])),
            ("Ub{}Iterations".format(prefix),
             "{:.0f}".format(iterations["iterations_median"])),
            ("Ub{}LastShare".format(prefix),
             "{:.0f}".format(100 * iterations["last_iteration_share_median"])),
        ]
        shares.append(100 * iterations["last_iteration_share_median"])
    macros += [
        ("UbMinLastShare", "{:.0f}".format(min(shares))),
        ("UbMaxLastShare", "{:.0f}".format(max(shares))),
        ("UbIterationsMin", "{:.0f}".format(min(
            data["iterations"][f]["iterations_median"] for f in P.FAMILY_NAMES))),
        ("UbIterationsMax", "{:.0f}".format(max(
            data["iterations"][f]["iterations_median"] for f in P.FAMILY_NAMES))),
    ]
    names = [name for name, _ in macros]
    if len(set(names)) != len(names):
        raise RenderError("duplicate macro name")
    lines = [
        "% Generated from the frozen unsplit-bound analysis.",
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
