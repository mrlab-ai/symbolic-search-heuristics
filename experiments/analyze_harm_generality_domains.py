#!/usr/bin/env python3
"""Post-hoc per-domain view of the frozen harm-generality analysis.

Descriptive and post hoc; changes no frozen estimand or decision.  Uses the
frozen pairing of `analyze_pdb_profile_harm_generality.py` on the pinned
properties and reports, per domain and pooled over all heuristics, the
share S = sum(ln frag) / sum(ln r) over harmful pairs (r > 1), and per family
a domain-cluster bootstrap interval for S (2,000 resamples of domains with
replacement, fixed seed).

  analyze  write artifacts/pdb-profile-harm-generality/domains-v1.json
  render   write paper/generated/pdb-profile-harm-generality-domains-v1.tex
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path

import analyze_pdb_profile_harm_generality as Frozen
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
EXPECTED_PROPERTIES_SHA256 = (
    "451d10ee4c26e5115ca2d88fac50dc97ad8089c7c1782ffe0c014ae940eff105"
)
DEFAULT_ARTIFACT = Frozen.ARTIFACT_DIR / "domains-v1.json"
EXPECTED_ARTIFACT_SHA256 = (
    "7579f878d2cd0df6dc1b2c8ed016014dc86eca04680f4bd9cf1a20f9ba2138c0"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated"
    / "pdb-profile-harm-generality-domains-v1.tex"
)
BOOTSTRAP_RESAMPLES = 2000
BOOTSTRAP_SEED = "harm-generality-domain-bootstrap/v1"
MIN_DOMAIN_HARMFUL = 5
MAX_TEX_BYTES = 16 * 1024


def _share(pairs):
    harmful = [p for p in pairs if p["r"] > 1]
    log_r = sum(math.log(p["r"]) for p in harmful)
    log_f = sum(math.log(p["f"]) for p in harmful)
    return (log_f / log_r) if harmful else None, len(harmful)


def _bootstrap(pairs, rng):
    by_domain = {}
    for p in pairs:
        if p["r"] > 1:
            by_domain.setdefault(p["domain"], []).append(p)
    domains = sorted(by_domain)
    sums = {d: (sum(math.log(p["f"]) for p in by_domain[d]),
                sum(math.log(p["r"]) for p in by_domain[d])) for d in domains}
    shares = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sample = [domains[rng.randrange(len(domains))] for _ in domains]
        log_f = sum(sums[d][0] for d in sample)
        log_r = sum(sums[d][1] for d in sample)
        shares.append(log_f / log_r)
    shares.sort()
    return {
        "low": round(shares[int(0.025 * (len(shares) - 1))], 4),
        "high": round(shares[int(0.975 * (len(shares) - 1))], 4),
    }


def analyze(properties):
    cohort, runs = Frozen._index_runs(properties)
    pairs = Frozen.pairs_from_runs(cohort, runs)
    rng = random.Random(BOOTSTRAP_SEED)
    families = {}
    for family in ("ms", "pdb", "pot", "pooled"):
        mine = pairs if family == "pooled" else [
            p for p in pairs if p["family"] == family]
        share, harmful = _share(mine)
        families[family] = {
            "share": round(share, 4),
            "harmful": harmful,
            "bootstrap_95": _bootstrap(mine, rng),
        }
    domains = {}
    for domain in sorted({p["domain"] for p in pairs}):
        mine = [p for p in pairs if p["domain"] == domain]
        share, harmful = _share(mine)
        domains[domain] = {
            "pairs": len(mine),
            "harmful": harmful,
            "share": None if share is None else round(share, 4),
            "strong": sum(1 for p in mine if p["r"] > 2),
            "strong_frag_above_unsplit": sum(
                1 for p in mine if p["r"] > 2 and p["f"] > p["u"]),
        }
    return {
        "schema": "symbolic-search-heuristics/harm-generality-domains/v1",
        "status": "post-hoc-descriptive",
        "properties_sha256": EXPECTED_PROPERTIES_SHA256,
        "bootstrap": {"resamples": BOOTSTRAP_RESAMPLES, "seed": BOOTSTRAP_SEED},
        "families": families,
        "domains": domains,
    }


def command_analyze(args):
    raw_properties = Path(args.properties).read_bytes()
    if hashlib.sha256(raw_properties).hexdigest() != EXPECTED_PROPERTIES_SHA256:
        raise RenderError("properties differ from the pinned harm-generality run")
    artifact = analyze(json.loads(raw_properties))
    raw = Common._canonical_json(artifact) + b"\n"
    if DEFAULT_ARTIFACT.exists():
        raise RenderError("domain artifact already exists")
    Frozen._write_atomic(DEFAULT_ARTIFACT, raw)
    digest = hashlib.sha256(raw).hexdigest()
    Frozen._write_atomic(
        str(DEFAULT_ARTIFACT) + ".sha256",
        "{}  {}\n".format(digest, DEFAULT_ARTIFACT.name).encode("ascii"))
    print(digest)
    return 0


def _load(path):
    raw = Common._read_regular(path, 1024 * 1024)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ARTIFACT_SHA256:
        raise RenderError("domain artifact is not the reviewed pin")
    sidecar = "{}  {}\n".format(digest, Path(path).name).encode("ascii")
    if Common._read_regular(Path(str(path) + ".sha256"), 256) != sidecar:
        raise RenderError("domain sidecar differs from the pinned artifact")
    return json.loads(raw.decode("ascii")), digest


def _tex_domain(name):
    return r"\texttt{{{}}}".format(name.replace("_", r"\_"))


def render(data, digest):
    rows = []
    shown = [
        (name, record) for name, record in data["domains"].items()
        if record["harmful"] >= MIN_DOMAIN_HARMFUL
    ]
    for name, record in sorted(shown, key=lambda item: item[1]["share"]):
        rows.append("{} & {} & {} & {:.2f} & {}/{} \\\\".format(
            _tex_domain(name), record["pairs"], record["harmful"],
            record["share"], record["strong_frag_above_unsplit"],
            record["strong"]))
    below = [name for name, record in shown if record["share"] < 0.9]
    macros = [
        ("GenDomainRows", "\n".join(rows)),
        ("GenDomainsShown", str(len(shown))),
        ("GenDomainMinHarmful", str(MIN_DOMAIN_HARMFUL)),
        ("GenDomainsBelow", str(len(below))),
        ("GenBootstrapResamples", "\\num{{{}}}".format(BOOTSTRAP_RESAMPLES)),
    ]
    for family, prefix in (("ms", "Ms"), ("pdb", "Pdb"), ("pot", "Pot"),
                           ("pooled", "All")):
        interval = data["families"][family]["bootstrap_95"]
        macros += [
            ("Gen{}BootLow".format(prefix), "{:.2f}".format(interval["low"])),
            ("Gen{}BootHigh".format(prefix), "{:.2f}".format(interval["high"])),
        ]
    lines = [
        "% Generated post hoc from the harm-generality domain summary.",
        "% Descriptive only; changes no frozen estimand or decision.",
        "% Summary SHA-256: {}".format(digest),
    ] + [Common._macro(name, value) for name, value in macros]
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


def command_render(args):
    data, digest = _load(args.artifact)
    raw = render(data, digest)
    if args.check:
        if Common._read_regular(args.output, MAX_TEX_BYTES) != raw:
            raise RenderError("generated TeX is stale")
        return 0
    if Path(args.output).resolve() != DEFAULT_OUTPUT.resolve():
        raise RenderError("--write is restricted to the generated-paper path")
    Frozen._write_atomic(args.output, raw)
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--properties", type=Path, default=Frozen.DEFAULT_PROPERTIES)
    r = sub.add_parser("render")
    r.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    r.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    modes = r.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "analyze":
        return command_analyze(args)
    return command_render(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RenderError, Frozen.AnalysisError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
