#!/usr/bin/env python3
"""Render paper macros for the CPDDL objective study.

Reads only the pinned frozen analysis of analyze_cpddl_objective_study.py and
computes no new estimand; the number of domains with harmful pairs is
counted from the analysis' per-pair points (harmful if u * frag > 1).
Rendering fails closed unless the claims are those the paper states.

  --write   write paper/generated/cpddl-objective-v1.tex
  --check   compare the generated file byte for byte
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import render_pdb_profile_semantic_union_paper as Common
import render_pot_all_decomposition_paper as Writer

RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ANALYSIS = SCRIPT_DIR / "artifacts" / "cpddl-objective" / "analysis-v1.json"
EXPECTED_ANALYSIS_SHA256 = "8334e5717572a33d877f7401e011ee1d31004a184ee1da75eeb1aed2467086ad"
EXPECTED_CLAIMS = {"H-I": "better"}
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "paper" / "generated" / "cpddl-objective-v1.tex"
MAX_TEX_BYTES = 16 * 1024


def _load(path):
    if Path(path).resolve() != DEFAULT_ANALYSIS.resolve():
        raise RenderError("unexpected analysis path")
    raw = Common._read_regular(path, 4 * 1024 * 1024)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ANALYSIS_SHA256:
        raise RenderError("analysis artifact is not the frozen pin")
    sidecar = "{}  {}\n".format(digest, Path(path).name).encode("ascii")
    if Common._read_regular(Path(str(path) + ".sha256"), 256) != sidecar:
        raise RenderError("analysis sidecar differs from the pin")
    data = json.loads(raw.decode("ascii"))
    if data.get("claims") != EXPECTED_CLAIMS:
        raise RenderError("claims differ from those the paper states")
    return data, digest


def render(data, digest):
    cov = {k: v["solved"] for k, v in data["coverage"].items()}
    test = data["primary_tests"]["H-I"]
    d = data["decomposition"]
    harmful_domains = len({p[0] for p in d["points"] if p[3] * p[4] > 1})

    def f2(x):
        return "{:.2f}".format(x)

    macros = [
        ("CpISolvedBlindFw", str(cov["cp_blind_fw"])),
        ("CpISolvedPotFw", str(cov["cp_pot_fw"])),
        ("CpIGains", str(test["gains"])),
        ("CpILosses", str(test["losses"])),
        ("CpIPairs", str(d["pairs"])),
        ("CpIHarmful", str(d["harmful"])),
        ("CpIHelpful", str(d["helpful"])),
        ("CpIHurtUnion", f2(d["harmful_u_median"])),
        ("CpIHurtFrag", f2(d["harmful_f_median"])),
        ("CpIHelpUnion", f2(d["helpful_u_median"])),
        ("CpIHelpFrag", f2(d["helpful_f_median"])),
        ("CpIRow", "Operator potentials, I (CPDDL) & \\num{{{}}} & \\num{{{}}} ({}) & {} & {}/{} & {} & {} & {} & {} \\\\".format(
            d["pairs"], d["harmful"], harmful_domains, f2(d["share"]),
            d["strong_frag_above_unsplit"], d["strong"], f2(d["harmful_u_median"]),
            f2(d["harmful_f_median"]), f2(d["helpful_u_median"]),
            f2(d["helpful_f_median"]))),
    ]
    lines = ["% Generated from the frozen CPDDL objective analysis.",
             "% Analysis SHA-256: {}".format(digest)] + [
        Common._macro(name, value) for name, value in macros]
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


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
        if Path(args.output).resolve() != DEFAULT_OUTPUT.resolve():
            raise RenderError("--write is restricted to the generated-paper path")
        Writer.DEFAULT_OUTPUT = DEFAULT_OUTPUT
        Writer._write_atomic(args.output, raw)
    elif Common._read_regular(args.output, MAX_TEX_BYTES) != raw:
        raise RenderError("generated TeX is stale")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RenderError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
