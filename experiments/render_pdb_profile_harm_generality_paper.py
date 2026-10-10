#!/usr/bin/env python3
"""Render the paper-facing TeX and figure of the harm-generality study.

Reads only the pinned frozen analysis artifact of
`analyze_pdb_profile_harm_generality.py`; it computes no new estimand.
Rendering fails closed unless the artifact's pre-registered decisions are
the ones that the paper text states: the claim beyond PDBs holds for every
family and pooled, and the online guard is not pursued.

  tex     macros and table rows for paper.tex and supplement.tex
  figure  per-family scatter of unsplit ratio u against fragmentation; the
          PDF carries no timestamps, so --check compares it byte for byte
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import tempfile
from fractions import Fraction
from pathlib import Path

import pdb_profile_harm_generality_protocol as P
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR / "artifacts" / "pdb-profile-harm-generality" / "analysis-v1.json"
)
EXPECTED_ANALYSIS_SHA256 = (
    "445f8774906b2aa84ee60e00db612d22685756213bd550ef30aa3f38f474bd38"
)
GENERATED = REPOSITORY_ROOT / "paper" / "generated"
DEFAULT_TEX = GENERATED / "pdb-profile-harm-generality-v1.tex"
DEFAULT_FIGURE = GENERATED / "pdb-profile-harm-generality-v1.pdf"
EXPECTED_DECISIONS = {
    "claim_beyond_pdbs": True,
    "family_claims": {"ms": True, "pdb": True, "pot": True},
    "pooled_claim": True,
    "pursue_online_guard": False,
}
MAX_ANALYSIS_BYTES = 1024 * 1024
MAX_TEX_BYTES = 16 * 1024
MAX_PDF_BYTES = 4 * 1024 * 1024

# Macro prefix, table name and figure title of each analysis group.
GROUPS = (
    ("ms", "Ms", r"M\&S", "M&S"),
    ("pdb", "Pdb", "CEGAR PDB", "CEGAR PDB"),
    ("pot", "Pot", "Potentials", "Potentials"),
    ("pooled", "All", "Pooled", None),
)
CONFIG_NAMES = (
    ("blind_fw_profiled", r"Blind"),
    ("ms_unaligned_10k", r"M\&S unaligned, \num{10000}"),
    ("ms_aligned_10k", r"M\&S aligned, \num{10000}"),
    ("ms_unaligned_50k", r"M\&S unaligned, \num{50000}"),
    ("pdb_cegar_1m", r"CEGAR PDB, \num{1000000}"),
    ("pot_m4", r"Potentials, $m=4$"),
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
    _validate(data)
    return data, digest


def _validate(data):
    if data.get("decisions") != EXPECTED_DECISIONS:
        raise RenderError("decisions differ from those the paper states")
    if data.get("protocol_sha256") != P.PROTOCOL_SHA256:
        raise RenderError("analysis names a different protocol")
    if [label for label, _ in CONFIG_NAMES] != list(P.LABELS):
        raise RenderError("configuration names do not match the protocol")


def _fraction(record):
    return Fraction(record["numerator"], record["denominator"])


def _fixed(value, places):
    if isinstance(value, dict):
        value = _fraction(value) if "numerator" in value else value["value"]
    return "{:.{}f}".format(float(value), places)


def _group_values(group):
    return {
        "Pairs": str(group["pairs"]),
        "PairDomains": str(group["pair_domains"]),
        "Harmful": str(group["harmful"]),
        "HarmfulDomains": str(group["harmful_domains"]),
        "Helpful": str(group["helpful"]),
        "Share": _fixed(group["share"], 2),
        "Strong": str(group["strong"]),
        "StrongFrag": str(group["strong_frag_above_unsplit"]),
        "HurtUnion": _fixed(group["harmful_u_median"], 2),
        "HurtFrag": _fixed(group["harmful_f_median"], 2),
        "HelpUnion": _fixed(group["helpful_u_median"], 2),
        "HelpFrag": _fixed(group["helpful_f_median"], 2),
        "Hard": str(group["hard"]),
        "TimeHarm": str(group["time_harm"]),
        "TimeHarmUnion": _fixed(group["time_harm_u_median"], 2),
        "TimeHarmFrag": _fixed(group["time_harm_f_median"], 2),
        "TimeHelp": str(group["time_help"]),
        "TimeHelpUnion": _fixed(group["time_help_u_median"], 2),
        "TimeHelpFrag": _fixed(group["time_help_f_median"], 2),
    }


def _row(name, group):
    v = _group_values(group)
    return (
        "{} & \\num{{{}}} & \\num{{{}}} ({}) & {} & {}/{} & {} & {} & {} & {} "
        "\\\\".format(
            name, v["Pairs"], v["Harmful"], v["HarmfulDomains"], v["Share"],
            v["StrongFrag"], v["Strong"], v["HurtUnion"], v["HurtFrag"],
            v["HelpUnion"], v["HelpFrag"],
        )
    )


def render_tex(data, digest):
    macros = []
    for key, prefix, _, _ in GROUPS:
        for name, value in _group_values(data["groups"][key]).items():
            macros.append(("Gen" + prefix + name, value))
    for key, prefix, _, _ in GROUPS[:3]:
        macros.append(("Gen" + prefix + "Headroom",
                       str(data["family_headroom"][key]["headroom_tasks"])))
    # Ranges over the three families, for prose that names no family.
    families = [_group_values(data["groups"][key]) for key, _, _, _ in GROUPS[:3]]
    for name in ("HarmfulDomains", "HurtUnion", "HurtFrag", "Share"):
        values = sorted((family[name] for family in families), key=float)
        macros += [("GenMin" + name, values[0]), ("GenMax" + name, values[-1])]
    headroom = max(r["headroom_tasks"] for r in data["family_headroom"].values())
    guard_tasks = -(-P.GUARD_HEADROOM_FRACTION.numerator * P.COHORT_TASKS
                    // P.GUARD_HEADROOM_FRACTION.denominator)
    coverage = data["coverage"]
    blind = coverage[P.BLIND_LABEL]
    macros += [
        ("GenTasks", str(P.COHORT_TASKS)),
        ("GenCells", str(P.CELL_COUNT)),
        ("GenBlindSolved", str(blind)),
        ("GenMaxHeuristicSolved",
         str(max(v for k, v in coverage.items() if k != P.BLIND_LABEL))),
        ("GenMinHeuristicSolved",
         str(min(v for k, v in coverage.items() if k != P.BLIND_LABEL))),
        ("GenMaxHeadroom", str(headroom)),
        ("GenGuardTasks", str(guard_tasks)),
        ("GenGuardPercent",
         _fixed(P.GUARD_HEADROOM_FRACTION * 100, 0)),
        ("GenShareThreshold", _fixed(P.MIN_SHARE, 1)),
        ("GenStrongThresholdPercent", _fixed(P.MIN_STRONG_SHARE * 100, 0)),
        ("GenSupportPairs", str(P.MIN_HARMFUL_PAIRS)),
        ("GenSupportDomains", str(P.MIN_HARMFUL_DOMAINS)),
        ("GenStrongSupportPairs", str(P.MIN_STRONG_PAIRS)),
    ]
    family_rows = [_row(name, data["groups"][key]) for key, _, name, _ in GROUPS]
    config_rows = [
        _row(name, data["per_config_descriptive"][label])
        for label, name in CONFIG_NAMES[1:]
    ]
    coverage_rows = []
    for label, name in CONFIG_NAMES:
        extra = (
            "--" if label == P.BLIND_LABEL
            else str(data["headroom_tasks"][label])
        )
        coverage_rows.append("{} & {} & {} \\\\".format(
            name, coverage[label], extra))
    macros += [
        ("GenFamilyRows", "\n".join(family_rows)),
        ("GenConfigRows", "\n".join(config_rows)),
        ("GenCoverageRows", "\n".join(coverage_rows)),
    ]
    if headroom >= guard_tasks or blind < max(coverage.values()):
        raise RenderError("coverage contradicts the paper's guard statement")
    names = [name for name, _ in macros]
    if len(set(names)) != len(names):
        raise RenderError("duplicate macro name")
    lines = [
        "% Generated from the frozen harm-generality analysis.",
        "% Analysis SHA-256: {}".format(digest),
    ] + [Common._macro(name, value) for name, value in macros]
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


def render_figure(data):
    import matplotlib

    matplotlib.use("pdf")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator

    points = data["points"]
    if not points:
        raise RenderError("no points")
    plt.rcParams.update({
        "pdf.fonttype": 42,
        "font.family": "serif",
        "font.size": 7,
        "axes.linewidth": 0.5,
    })
    lo_u = min(p[1] for p in points) / 1.2
    hi_u = max(p[1] for p in points) * 1.2
    lo_f = min(p[2] for p in points) / 1.1
    hi_f = max(p[2] for p in points) * 1.1
    figure, panels = plt.subplots(1, 3, figsize=(3.3, 1.45), sharey=True)
    for axes, (key, _, _, title) in zip(panels, GROUPS):
        mine = [(u, f) for label, u, f in points if P.FAMILIES[label] == key]
        helped = [(u, f) for u, f in mine if u * f <= 1]
        hurt = [(u, f) for u, f in mine if u * f > 1]
        for group, color, label in ((helped, "0.7", "effort at most blind"),
                                    (hurt, "0.1", "effort above blind")):
            if group:
                xs, ys = zip(*group)
                axes.scatter(xs, ys, s=1.2, c=color, linewidths=0, label=label)
        for ratio, style in ((1.0, "-"), (2.0, "--")):
            xs = [lo_u, hi_u]
            axes.plot(xs, [ratio / x for x in xs], style, color="0.4",
                      linewidth=0.6)
        axes.set_xscale("log")
        axes.set_yscale("log")
        axes.set_xlim(lo_u, hi_u)
        axes.set_ylim(lo_f, hi_f)
        axes.set_title("{} ({})".format(title, len(mine)), fontsize=7, pad=2)
        axes.xaxis.set_major_locator(FixedLocator([0.01, 0.1, 1.0]))
        axes.yaxis.set_major_locator(FixedLocator([1.0, 2.0, 4.0, 8.0]))
        for axis in (axes.xaxis, axes.yaxis):
            axis.set_minor_locator(NullLocator())
            axis.set_major_formatter(
                FuncFormatter(lambda value, _: "{:g}".format(value)))
    panels[0].set_ylabel("fragmentation")
    panels[1].set_xlabel("unsplit effort / blind effort")
    figure.tight_layout(pad=0.2, w_pad=0.3)
    stream = io.BytesIO()
    figure.savefig(stream, format="pdf",
                   metadata={"CreationDate": None, "ModDate": None,
                             "Creator": None, "Producer": None})
    plt.close(figure)
    raw = stream.getvalue()
    if len(raw) > MAX_PDF_BYTES:
        raise RenderError("figure exceeds its size limit")
    return raw


def _write_atomic(path, raw, allowed):
    path = Path(path)
    if path.resolve() != allowed.resolve():
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


def _self_test():
    data, _ = _load(DEFAULT_ANALYSIS)
    tampered = json.loads(json.dumps(data))
    tampered["decisions"]["family_claims"]["pot"] = False
    try:
        _validate(tampered)
    except RenderError:
        pass
    else:
        raise RenderError("self-test: a failed family claim was rendered")
    tampered = json.loads(json.dumps(data))
    tampered["family_headroom"]["ms"]["headroom_tasks"] = 40
    try:
        render_tex(tampered, "0" * 64)
    except RenderError:
        pass
    else:
        raise RenderError("self-test: guard headroom contradiction was rendered")
    if _fixed({"numerator": 1, "denominator": 3}, 2) != "0.33":
        raise RenderError("self-test: fraction formatting")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("target", choices=("tex", "figure", "self-test"))
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument("--output", type=Path)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.target == "self-test":
        return _self_test()
    data, digest = _load(args.analysis)
    if args.target == "tex":
        raw, default, limit = render_tex(data, digest), DEFAULT_TEX, MAX_TEX_BYTES
    else:
        raw, default, limit = render_figure(data), DEFAULT_FIGURE, MAX_PDF_BYTES
    output = args.output or default
    if args.write:
        _write_atomic(output, raw, default)
    elif args.check:
        if Common._read_regular(output, limit) != raw:
            raise RenderError("generated {} is stale".format(args.target))
    elif args.target == "tex":
        print(raw.decode("ascii"), end="")
    else:
        raise RenderError("figure needs --write or --check")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RenderError, P.ProtocolError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
