#!/usr/bin/env python3
"""Post-hoc decomposition of heuristic harm on the sealed holdout.

Descriptive and post hoc; changes no frozen estimand or gate.  Each eligible
heuristic observation of the sealed holdout analysis (one per task and
heuristic semantics) is paired with the profiled blind run of its task.  For
jointly solved pairs, the effort ratio r = effort(h) / effort(blind) factors
exactly as r = u * frag with u = unionEffort(h) / effort(blind), because blind
search has fragmentation one.  The analysis reports how often r exceeds one,
which factor carries the excess, how time harm on harder tasks relates to the
two factors, why heuristic runs lose tasks that blind search solves, and how
well fragmentation on the first layers tracks final fragmentation and search
time.  Quantiles use the lower nearest rank on exact fractions where the
inputs are integers.

Subcommands:
  analyze  read the pinned raw properties and the sealed holdout analysis,
           and write the summary artifact (canonical JSON plus .sha256)
  render   render paper-facing TeX from the pinned summary artifact
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from fractions import Fraction
from pathlib import Path

import render_pdb_profile_certificate_holdout_paper as Holdout
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_PROPERTIES = Path(
    "/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe/"
    "experiments/data/exp_pdb_profile_certificate_holdout-eval/properties"
)
EXPECTED_PROPERTIES_SHA256 = (
    "8519abd2891cc74f6ee927a7aeb2170772c2db2a1af2eadb7d47b6789b706928"
)
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "pdb-profile-harm-decomposition"
DEFAULT_ARTIFACT = ARTIFACT_DIR / "analysis-v1.json"
EXPECTED_ARTIFACT_SHA256 = (
    "0814ae2554b139ed71f9aaf30440f5c1855ddf34731bcc70dd17bdb8575b3512"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "pdb-profile-harm-decomposition-v1.tex"
)
BLIND = "blind_fw_profiled"
HARD_BLIND_SECONDS = 10.0
TIME_HARM = 1.5
TIME_HELP = Fraction(2, 3)
PREFIX_LAYERS = 5
MAX_ARTIFACT_BYTES = 1024 * 1024
MAX_TEX_BYTES = 16 * 1024


def _quantile(values, p):
    ordered = sorted(values)
    return ordered[int(p * (len(ordered) - 1))]


def _ratio(value):
    if isinstance(value, Fraction):
        return {"numerator": value.numerator, "denominator": value.denominator}
    return {"value": round(float(value), 6)}


def _value(record):
    if "numerator" in record:
        return Fraction(record["numerator"], record["denominator"])
    return record["value"]


def _concordance(xs, ys):
    concordant = discordant = 0
    n = len(xs)
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[i] - xs[j]
            dy = ys[i] - ys[j]
            if dx == 0 or dy == 0:
                continue
            if (dx > 0) == (dy > 0):
                concordant += 1
            else:
                discordant += 1
    total = concordant + discordant
    return Fraction(concordant, total) if total else None


def _prefix_fragmentation(run, k):
    layers = {e["g"]: e["effort"] for e in run.get("wbh_expansion_profile") or []}
    unions = {
        lp["g"]: lp["bdd_nodes"]
        for lp in run.get("wbh_profile_layer_profiles") or []
        if lp.get("g") is not None and lp.get("bdd_nodes") is not None
    }
    gs = sorted(g for g in layers if g in unions)[:k]
    if len(gs) < k:
        return None
    union = sum(unions[g] for g in gs)
    if union <= 0:
        return None
    return Fraction(sum(layers[g] for g in gs), union)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1 << 24), b""):
            digest.update(block)
    return digest.hexdigest()


def analyze(properties, holdout):
    """Return the summary dictionary from loaded inputs."""
    runs = {}
    for run in properties.values():
        runs[(run["algorithm"], run["domain"], run["problem"])] = run
    pairs = []
    for obs in holdout["observations"]:
        blind = runs.get((BLIND, obs["domain"], obs["problem"]))
        if blind is None:
            raise RenderError("observation lacks its blind run")
        if blind.get("coverage") != 1 or not blind.get("wbh_profile_certified"):
            continue
        blind_effort = blind.get("effort")
        if type(blind_effort) is not int or blind_effort <= 0:
            continue
        config = sorted(obs["configs"])[0]
        heur = runs[(config, obs["domain"], obs["problem"])]
        if heur.get("effort") != obs["actual_effort"]:
            raise RenderError("heuristic run disagrees with the sealed observation")
        effort = obs["actual_effort"]
        union = obs["semantic_union_effort"]
        pairs.append({
            "domain": obs["domain"],
            "problem": obs["problem"],
            "r": Fraction(effort, blind_effort),
            "u": Fraction(union, blind_effort),
            "f": Fraction(effort, union),
            "blind_time": blind["search_time"],
            "time": heur["search_time"] / max(blind["search_time"], 0.01),
            "images": Fraction(heur["image_calls_completed"],
                               max(blind["image_calls_completed"], 1)),
            "prefix": _prefix_fragmentation(heur, PREFIX_LAYERS),
        })
    if not pairs:
        raise RenderError("no eligible pairs")
    hurt = [p for p in pairs if p["r"] > 1]
    helped = [p for p in pairs if p["r"] < 1]
    doubled = [p for p in pairs if p["r"] > 2]
    summary = {
        "pairs": len(pairs),
        "pair_tasks": len({(p["domain"], p["problem"]) for p in pairs}),
        "pair_domains": len({p["domain"] for p in pairs}),
        "hurt": len(hurt),
        "helped": len(helped),
        "hurt_union_above_one": sum(p["u"] > 1 for p in hurt),
        "hurt_frag_above_one": sum(p["f"] > 1 for p in hurt),
        "hurt_union_median": _ratio(_quantile([p["u"] for p in hurt], Fraction(1, 2))),
        "hurt_frag_median": _ratio(_quantile([p["f"] for p in hurt], Fraction(1, 2))),
        "hurt_log_union": _ratio(sum(math.log(p["u"]) for p in hurt)),
        "hurt_log_frag": _ratio(sum(math.log(p["f"]) for p in hurt)),
        "doubled": len(doubled),
        "doubled_frag_above_two": sum(p["f"] > 2 for p in doubled),
        "doubled_union_above_two": sum(p["u"] > 2 for p in doubled),
    }
    hard = [p for p in pairs if p["blind_time"] >= HARD_BLIND_SECONDS]
    time_harm = [p for p in hard if p["time"] > TIME_HARM]
    time_help = [p for p in hard if p["time"] < TIME_HELP]
    for name, group in (("time_harm", time_harm), ("time_help", time_help)):
        summary[name] = len(group)
        for key in ("u", "f", "images", "time"):
            summary["{}_{}_median".format(name, key)] = _ratio(
                _quantile([p[key] for p in group], Fraction(1, 2))
            )
    summary["hard"] = len(hard)
    summary["time_harm_effort_above_one"] = sum(p["r"] > 1 for p in time_harm)
    with_prefix = [p for p in pairs if p["prefix"] is not None]
    hard_prefix = [p for p in hard if p["prefix"] is not None]
    summary["prefix_layers"] = PREFIX_LAYERS
    summary["prefix_pairs"] = len(with_prefix)
    summary["prefix_frag_concordance"] = _ratio(_concordance(
        [p["prefix"] for p in with_prefix], [p["f"] for p in with_prefix]))
    summary["hard_prefix_pairs"] = len(hard_prefix)
    summary["hard_prefix_time_concordance"] = _ratio(_concordance(
        [p["prefix"] for p in hard_prefix], [p["time"] for p in hard_prefix]))
    losses = []
    for (algorithm, domain, problem), run in runs.items():
        if algorithm == BLIND:
            continue
        blind = runs[(BLIND, domain, problem)]
        if blind.get("coverage") == 1 and run.get("coverage") != 1:
            losses.append(run)
    summary["losses"] = len(losses)
    summary["losses_search_timeout"] = sum(
        run.get("error") == "search-out-of-time" for run in losses
    )
    construction = [run.get("construction_time") for run in losses]
    if any(not isinstance(value, (int, float)) for value in construction):
        raise RenderError("a lost run lacks its construction time")
    summary["losses_max_construction_seconds"] = _ratio(max(construction))
    return summary


def _canonical(value):
    return Common._canonical_json(value) + b"\n"


def _write_atomic(path, raw, allowed):
    path = Path(path)
    if path.resolve() != Path(allowed).resolve():
        raise RenderError("refusing to write outside the pinned output path")
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


def command_analyze(args):
    if _sha256_file(args.properties) != EXPECTED_PROPERTIES_SHA256:
        raise RenderError("raw properties differ from the pinned holdout properties")
    holdout, holdout_digest = Holdout._load(
        args.analysis,
        Holdout.EXPECTED_ANALYSIS_SHA256,
        Holdout.MAX_ANALYSIS_BYTES,
        "holdout analysis",
    )
    with open(args.properties) as stream:
        properties = json.load(stream)
    summary = analyze(properties, holdout)
    artifact = {
        "analysis_role": "post-hoc-descriptive-harm-decomposition",
        "holdout_analysis_sha256": holdout_digest,
        "properties_sha256": EXPECTED_PROPERTIES_SHA256,
        "parameters": {
            "hard_blind_search_seconds": HARD_BLIND_SECONDS,
            "time_harm_ratio": TIME_HARM,
            "time_help_ratio": _ratio(TIME_HELP),
            "prefix_layers": PREFIX_LAYERS,
        },
        "summary": summary,
    }
    raw = _canonical(artifact)
    _write_atomic(args.artifact, raw, DEFAULT_ARTIFACT)
    digest = hashlib.sha256(raw).hexdigest()
    sidecar = "{}  {}\n".format(digest, Path(args.artifact).name).encode("ascii")
    _write_atomic(str(args.artifact) + ".sha256", sidecar,
                  str(DEFAULT_ARTIFACT) + ".sha256")
    print(digest)
    return 0


def _load_artifact(path):
    raw = Common._read_regular(path, MAX_ARTIFACT_BYTES)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ARTIFACT_SHA256:
        raise RenderError("summary artifact is not the reviewed pin")
    expected = "{}  {}\n".format(digest, Path(path).name).encode("ascii")
    if Common._read_regular(Path(str(path) + ".sha256"), 256) != expected:
        raise RenderError("summary sidecar differs from the pinned artifact")
    data = json.loads(raw.decode("ascii"))
    if raw != _canonical(data):
        raise RenderError("summary artifact is not canonical")
    return data, digest


def _fixed(value, places):
    value = _value(value) if isinstance(value, dict) else value
    return "{:.{}f}".format(float(value), places)


def render(data, digest):
    s = data["summary"]
    macros = [
        ("HarmPairs", str(s["pairs"])),
        ("HarmPairTasks", str(s["pair_tasks"])),
        ("HarmPairDomains", str(s["pair_domains"])),
        ("HarmHurt", str(s["hurt"])),
        ("HarmHelped", str(s["helped"])),
        ("HarmHurtUnionMedian", _fixed(s["hurt_union_median"], 2)),
        ("HarmHurtFragMedian", _fixed(s["hurt_frag_median"], 2)),
        ("HarmHurtUnionAboveOne", str(s["hurt_union_above_one"])),
        ("HarmHurtLogUnion", _fixed(s["hurt_log_union"], 0)),
        ("HarmHurtLogFrag", _fixed(s["hurt_log_frag"], 0)),
        ("HarmDoubled", str(s["doubled"])),
        ("HarmDoubledFragAboveTwo", str(s["doubled_frag_above_two"])),
        ("HarmDoubledUnionAboveTwo", str(s["doubled_union_above_two"])),
        ("HarmHard", str(s["hard"])),
        ("HarmTimeHarm", str(s["time_harm"])),
        ("HarmTimeHarmUnion", _fixed(s["time_harm_u_median"], 2)),
        ("HarmTimeHarmFrag", _fixed(s["time_harm_f_median"], 2)),
        ("HarmTimeHarmImages", _fixed(s["time_harm_images_median"], 1)),
        ("HarmTimeHarmEffortAboveOne", str(s["time_harm_effort_above_one"])),
        ("HarmTimeHelp", str(s["time_help"])),
        ("HarmTimeHelpUnion", _fixed(s["time_help_u_median"], 2)),
        ("HarmTimeHelpFrag", _fixed(s["time_help_f_median"], 2)),
        ("HarmPrefixLayers", str(s["prefix_layers"])),
        ("HarmPrefixFragConcordance", _fixed(s["prefix_frag_concordance"], 2)),
        ("HarmHardPrefixTimeConcordance",
         _fixed(s["hard_prefix_time_concordance"], 2)),
        ("HarmLosses", str(s["losses"])),
        ("HarmLossesTimeout", str(s["losses_search_timeout"])),
        ("HarmLossesMaxConstruction",
         _fixed(s["losses_max_construction_seconds"], 1)),
    ]
    lines = [
        "% Generated post hoc from the pinned harm-decomposition summary.",
        "% Descriptive only; changes no frozen estimand or gate.",
        "% Summary SHA-256: {}".format(digest),
    ] + [Common._macro(name, value) for name, value in macros]
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


def command_render(args):
    if args.self_test:
        return _self_test()
    data, digest = _load_artifact(args.artifact)
    raw = render(data, digest)
    if args.write:
        _write_atomic(args.output, raw, DEFAULT_OUTPUT)
    elif args.check:
        if Common._read_regular(args.output, MAX_TEX_BYTES) != raw:
            raise RenderError("generated TeX is stale")
    else:
        print(raw.decode("ascii"), end="")
    return 0


def _self_test():
    if _concordance([1, 2, 3], [1, 2, 3]) != 1:
        raise RenderError("self-test: concordance of identical orders")
    if _concordance([1, 2, 3], [3, 2, 1]) != 0:
        raise RenderError("self-test: concordance of reversed orders")
    if _quantile([Fraction(3), Fraction(1), Fraction(2)], Fraction(1, 2)) != 2:
        raise RenderError("self-test: median")
    run = {
        "wbh_expansion_profile": [{"g": 0, "effort": 4}, {"g": 1, "effort": 6}],
        "wbh_profile_layer_profiles": [{"g": 0, "bdd_nodes": 4},
                                       {"g": 1, "bdd_nodes": 3}],
    }
    if _prefix_fragmentation(run, 2) != Fraction(10, 7):
        raise RenderError("self-test: prefix fragmentation")
    if _prefix_fragmentation(run, 3) is not None:
        raise RenderError("self-test: short prefix")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("--properties", type=Path, default=DEFAULT_PROPERTIES)
    analyze_parser.add_argument("--analysis", type=Path,
                                default=Holdout.DEFAULT_ANALYSIS)
    analyze_parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    render_parser = sub.add_parser("render")
    render_parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    render_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    modes = render_parser.add_mutually_exclusive_group()
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "analyze":
        return command_analyze(args)
    return command_render(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RenderError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
