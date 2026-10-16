#!/usr/bin/env python3
"""Render paper macros for the strong-heuristics study.

Reads the pinned frozen analysis of analyze_strong_heuristics.py and
computes no new estimand; table rows use the format of the family rows of
the harm-generality study.  Post hoc and descriptive, it also counts from
the pinned properties how many runs that fail on tasks that blind search
solves did not complete the construction of the heuristic.  Rendering fails
closed unless the decisions are those that the paper states.

  --write   write paper/generated/strong-heuristics-v1.tex
  --check   compare the generated file byte for byte
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import render_pdb_profile_harm_generality_paper as Generality
import render_pdb_profile_semantic_union_paper as Common
import render_pot_all_decomposition_paper as Writer
import strong_heuristics_protocol as P

RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_ANALYSIS = SCRIPT_DIR / "artifacts" / "strong-heuristics" / "analysis-v1.json"
EXPECTED_ANALYSIS_SHA256 = "f9e81416777a4618ef0f1341ba3cb7bec90bfa3820e2f07eb98d3affa4debfa9"
PROPERTIES = SCRIPT_DIR / "data" / "exp_strong_heuristics-eval" / "properties"
EXPECTED_PROPERTIES_SHA256 = "3a400cde7aead94cc0cf0726c7ce299ee88fed7dfa794cf12b75082f92990f68"
EXPECTED_DECISIONS = {"ms_unaligned_200k": True, "pot_all_m1000": True}
DEFAULT_OUTPUT = SCRIPT_DIR.parent / "paper" / "generated" / "strong-heuristics-v1.tex"
MAX_TEX_BYTES = 16 * 1024
NAMES = {"pot_all_m1000": ("StPot", r"Potentials, all states, $|P|\leq1000$"),
         "ms_unaligned_200k": ("StMs", r"M\&S, \num{200000} states")}


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
    if data.get("decisions") != EXPECTED_DECISIONS:
        raise RenderError("decisions differ from those the paper states")
    raw_properties = PROPERTIES.read_bytes()
    if hashlib.sha256(raw_properties).hexdigest() != EXPECTED_PROPERTIES_SHA256:
        raise RenderError("properties differ from the pinned run")
    runs = {(v["algorithm"], v["domain"], v["problem"]): v
            for v in json.loads(raw_properties).values()}
    lost = {}
    for label in EXPECTED_DECISIONS:
        failing = [v for (a, d, p), v in runs.items() if a == label
                   and runs[(P.BLIND_LABEL, d, p)].get("coverage") == 1
                   and v.get("coverage") != 1]
        lost[label] = (len(failing),
                       sum(v.get("construction_completed") is not True
                           for v in failing))
    return (data, lost), digest


def render(loaded, digest):
    data, lost = loaded
    macros = [("StBlindSolved", str(data["coverage"][P.BLIND_LABEL]))]
    for label, (prefix, name) in NAMES.items():
        group, desc = data["groups"][label], data["descriptive"][label]
        values = Generality._group_values(group)
        macros += [
            (prefix + "Solved", str(data["coverage"][label])),
            (prefix + "Harmful", values["Harmful"]),
            (prefix + "Helpful", values["Helpful"]),
            (prefix + "Pairs", values["Pairs"]),
            (prefix + "HurtUnion", values["HurtUnion"]),
            (prefix + "HurtFrag", values["HurtFrag"]),
            (prefix + "HelpUnion", values["HelpUnion"]),
            (prefix + "HelpFrag", values["HelpFrag"]),
            (prefix + "HurtStates", Generality._fixed(desc["harmful_s_median"], 2)),
            (prefix + "HelpStates", Generality._fixed(desc["helpful_s_median"], 2)),
            (prefix + "LowPairs", str(desc["low_pairs"])),
            (prefix + "LowHelpful", str(desc["low_helpful"])),
            (prefix + "HighPairs", str(desc["high_pairs"])),
            (prefix + "HighHelpful", str(desc["high_helpful"])),
            (prefix + "Lost", str(lost[label][0])),
            (prefix + "Unconstructed", str(lost[label][1])),
            (prefix + "Row", Generality._row(name, group)),
        ]
    lines = ["% Generated from the frozen strong-heuristics analysis.",
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
