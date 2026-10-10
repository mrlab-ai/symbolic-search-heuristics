#!/usr/bin/env python3
"""Render paper macros and table rows for the fragmentation-remedy study.

Reads only the pinned frozen analysis artifact of
`analyze_fragmentation_remedy.py` and computes no new estimand.  Rendering
fails closed unless the artifact's claims are those that the paper text
states (EXPECTED_CLAIMS).

  --write   write paper/generated/fragmentation-remedy-v1.tex
  --check   compare the generated file byte for byte
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
import os
from pathlib import Path

import fragmentation_remedy_protocol as P
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR / "artifacts" / "fragmentation-remedy" / "analysis-v1.json"
)
EXPECTED_ANALYSIS_SHA256 = "TO_PIN"
EXPECTED_CLAIMS = "TO_PIN"
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "fragmentation-remedy-v1.tex"
)
MAX_ANALYSIS_BYTES = 1024 * 1024
MAX_TEX_BYTES = 16 * 1024

MACRO_NAMES = {
    "blind_fw": "BlindFw",
    "blind_bd": "BlindBd",
    "bd_ms_prune": "BdMsPrune",
    "ms_plain": "MsPlain",
    "ms_prune": "MsPrune",
    "ms_batch": "MsBatch",
    "pdb_plain": "PdbPlain",
    "pdb_prune": "PdbPrune",
    "pdb_batch": "PdbBatch",
    "pot_plain": "PotPlain",
    "pot_prune": "PotPrune",
    "pot_batch": "PotBatch",
    "pot_all_plain": "PotAllPlain",
}
ROW_NAMES = (
    ("blind_fw", "Blind forward"),
    ("blind_bd", "Blind bidirectional"),
    ("bd_ms_prune", r"Bidir.\ + M\&S pruning"),
    ("ms_plain", r"M\&S"),
    ("ms_prune", r"\quad prune-only"),
    ("ms_batch", r"\quad batched"),
    ("pdb_plain", "CEGAR PDB"),
    ("pdb_prune", r"\quad prune-only"),
    ("pdb_batch", r"\quad batched"),
    ("pot_plain", "Potentials"),
    ("pot_prune", r"\quad prune-only"),
    ("pot_batch", r"\quad batched"),
    ("pot_all_plain", r"Potentials, all states"),
)


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
    if [label for label, _ in ROW_NAMES] != list(P.LABELS):
        raise RenderError("row names do not match the protocol")
    return data, digest


def _fixed(value, places):
    return "--" if value is None else "{:.{}f}".format(float(value), places)


def _delta(test):
    mark = r"$^{*}$" if test["significant"] else ""
    return r"+{}/$-${}{}".format(test["gains"], test["losses"], mark)


def render(data, digest):
    macros = []
    coverage = data["coverage"]
    tests = data["primary_tests"]
    for label, name in MACRO_NAMES.items():
        macros.append(("RemSolved" + name, str(coverage[label]["solved"])))
    for family, prefix in (("ms", "Ms"), ("pdb", "Pdb"), ("pot", "Pot")):
        window = data["batch_windows"][family]
        macros.append(("RemWindow" + prefix,
                       r"\infty" if window == "infinity" else window))
        for remedy, rname in (("prune", "Prune"), ("batch", "Batch")):
            label = "{}_{}".format(family, remedy)
            for test, tname in (("H1", "VsPlain"), ("H2", "VsBlind")):
                record = tests["{}:{}".format(test, label)]
                key = "Rem{}{}{}".format(prefix, rname, tname)
                macros += [(key + "Gains", str(record["gains"])),
                           (key + "Losses", str(record["losses"]))]
            mechanism = data["mechanism"][label]
            key = "Rem{}{}".format(prefix, rname)
            macros += [
                (key + "MechTasks", str(mechanism["remedy"]["tasks"])),
                (key + "EffortPlain",
                 _fixed(mechanism["plain"]["effort_ratio_median"], 2)),
                (key + "EffortRemedy",
                 _fixed(mechanism["remedy"]["effort_ratio_median"], 2)),
                (key + "TimePlain",
                 _fixed(mechanism["plain"]["time_ratio_median"], 2)),
                (key + "TimeRemedy",
                 _fixed(mechanism["remedy"]["time_ratio_median"], 2)),
            ]
    context = data["bidirectional_context"]
    for key, name in (
        ("blind_bd_vs_blind_fw", "BdVsFw"),
        ("bd_ms_prune_vs_blind_fw", "BdMsVsFw"),
        ("bd_ms_prune_vs_blind_bd", "BdMsVsBd"),
        ("pot_all_plain_vs_blind_fw", "PotAllVsFw"),
        ("pot_all_plain_vs_pot_plain", "PotAllVsPot"),
    ):
        macros += [("Rem{}Gains".format(name), str(context[key]["gains"])),
                   ("Rem{}Losses".format(name), str(context[key]["losses"]))]
    pot_all = context["pot_all_plain_effort"]
    macros += [
        ("RemPotAllEffort", _fixed(pot_all["effort_ratio_median"], 2)),
        ("RemPotAllTime", _fixed(pot_all["time_ratio_median"], 2)),
        ("RemMaxHeadroomOverBd",
         str(max(data["headroom_over_blind_bd"].values()))),
    ]
    for family, prefix in (("ms", "Ms"), ("pdb", "Pdb"), ("pot", "Pot"),
                           ("pooled", "All")):
        record = data["effort_time"][family]
        macros += [
            ("RemEffTime{}Pairs".format(prefix), str(record["pairs"])),
            ("RemEffTime{}Rho".format(prefix), _fixed(record["spearman"], 2)),
            ("RemEffTime{}Same".format(prefix),
             _fixed(100 * record["same_side_fraction"], 0)),
        ]
    rows = []
    for label, name in ROW_NAMES:
        family = label.split("_")[0]
        remedy = label.split("_")[1] if label.count("_") == 1 else None
        if family in ("ms", "pdb", "pot") and remedy in ("prune", "batch"):
            vs_plain = _delta(tests["H1:" + label])
            vs_blind = _delta(tests["H2:" + label])
        else:
            vs_plain = "--"
            vs_blind = "--"
        rows.append("{} & {} & {} & {} \\\\".format(
            name, coverage[label]["solved"], vs_plain, vs_blind))
    macros.append(("RemCoverageRows", "\n".join(rows)))
    names = [name for name, _ in macros]
    if len(set(names)) != len(names):
        raise RenderError("duplicate macro name")
    lines = [
        "% Generated from the frozen fragmentation-remedy analysis.",
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
