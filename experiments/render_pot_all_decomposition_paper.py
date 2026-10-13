#!/usr/bin/env python3
"""Render paper macros for the pot-all decomposition study.

Reads only the pinned frozen analysis artifact of
`analyze_pot_all_decomposition.py` and computes no new estimand.  Rendering
fails closed unless the artifact's decision is the one that the paper text
states (EXPECTED_DECISIONS).  The table row has the format of the family
rows of the harm-generality study.

  --write   write paper/generated/pot-all-decomposition-v1.tex
  --check   compare the generated file byte for byte
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import pot_all_decomposition_protocol as P
import render_pdb_profile_harm_generality_paper as Generality
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR / "artifacts" / "pot-all-decomposition" / "analysis-v1.json"
)
EXPECTED_ANALYSIS_SHA256 = (
    "c85c5d9a747d3ec85cd1d33bdac7ee5572fe98f1bcc0fc35b59aefbc45229cbb"
)
EXPECTED_DECISIONS = {"diagnosis_holds": True}
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "pot-all-decomposition-v1.tex"
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
    if data.get("decisions") != EXPECTED_DECISIONS:
        raise RenderError("decisions differ from those the paper states")
    if data.get("protocol_sha256") != P.PROTOCOL_SHA256:
        raise RenderError("analysis names a different protocol")
    return data, digest


def render(data, digest):
    _fixed = Generality._fixed
    descriptive = data["descriptive"]
    macros = [("PotAll" + name, value) for name, value in
              Generality._group_values(data["group"]).items()]
    macros += [
        ("PotAllCells", str(P.CELL_COUNT)),
        ("PotAllHurtStates", _fixed(descriptive["harmful_s_median"], 2)),
        ("PotAllHelpStates", _fixed(descriptive["helpful_s_median"], 2)),
        ("PotAllHurtUnionAboveOne", str(descriptive["harmful_u_above_one"])),
        ("PotAllLowPairs", str(descriptive["low_pairs"])),
        ("PotAllLowHelpful", str(descriptive["low_helpful"])),
        ("PotAllHighPairs", str(descriptive["high_pairs"])),
        ("PotAllHighHelpful", str(descriptive["high_helpful"])),
        ("PotAllSolved", str(data["coverage"][P.POT_ALL])),
        ("PotAllBlindSolved", str(data["coverage"][P.BLIND_LABEL])),
        ("PotAllRow", Generality._row("Potentials, all states", data["group"])),
    ]
    names = [name for name, _ in macros]
    if len(set(names)) != len(names):
        raise RenderError("duplicate macro name")
    lines = [
        "% Generated from the frozen pot-all decomposition analysis.",
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
