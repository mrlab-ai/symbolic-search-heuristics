#!/usr/bin/env python3
"""Frozen analysis of the prospective pot-all decomposition study.

Pairs every run of potentials optimized for all states with the profiled
blind run of its task and evaluates the decision rule of Section 5 of
pot_all_decomposition_protocol.md with the frozen pairing and group
functions of analyze_pdb_profile_harm_generality.py, whose protocol module
is replaced by this study's.  It adds the state ratio s = expanded
states(h) / expanded states(blind) of every pair for the descriptive
quantities.  Failed rules are reported, never adjusted.

  analyze    read the fetched properties and write the canonical summary
             artifact plus its .sha256 sidecar
  self-test  check the pairing and the decision logic on synthetic runs
"""

from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_harm_generality as Frozen
import pot_all_decomposition_protocol as P
import render_pdb_profile_semantic_union_paper as Common


Frozen.P = P
AnalysisError = Frozen.AnalysisError
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROPERTIES = (
    SCRIPT_DIR / "data" / "exp_pot_all_decomposition-eval" / "properties"
)
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "pot-all-decomposition"
DEFAULT_ARTIFACT = ARTIFACT_DIR / "analysis-v1.json"
SCHEMA = "symbolic-search-heuristics/pot-all-decomposition-analysis/v1"
LOW_STATE_RATIO = Fraction(1, 10)
HIGH_STATE_RATIO = Fraction(4, 5)


def _states(run):
    # Large state counts come from BDD model counting as doubles.
    value = run.get("expanded_states")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise AnalysisError("solved run without positive expanded states")
    return Fraction(value)


def analyze(properties):
    cohort, runs = Frozen._index_runs(properties)
    pairs = Frozen.pairs_from_runs(cohort, runs)
    for p in pairs:
        blind = runs[(P.BLIND_LABEL, p["domain"], p["problem"])]
        heur = runs[(p["label"], p["domain"], p["problem"])]
        p["s"] = _states(heur) / _states(blind)
    group = Frozen.evaluate_group(pairs)
    harmful = [p for p in pairs if p["r"] > 1]
    helpful = [p for p in pairs if p["r"] < 1]
    low = [p for p in pairs if p["s"] < LOW_STATE_RATIO]
    high = [p for p in pairs if p["s"] >= HIGH_STATE_RATIO]
    coverage = {
        label: sum(
            Frozen._solved(runs[(label, task.domain, task.problem)])
            for task in cohort)
        for label in P.LABELS
    }
    return {
        "schema": SCHEMA,
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "group": group,
        "descriptive": {
            "harmful_s_median": Frozen._median([p["s"] for p in harmful]),
            "helpful_s_median": Frozen._median([p["s"] for p in helpful]),
            "harmful_u_above_one": sum(p["u"] > 1 for p in harmful),
            "u_above_s": sum(p["u"] > p["s"] for p in pairs),
            "low_state_ratio": str(LOW_STATE_RATIO),
            "low_pairs": len(low),
            "low_helpful": sum(p["r"] < 1 for p in low),
            "high_state_ratio": str(HIGH_STATE_RATIO),
            "high_pairs": len(high),
            "high_helpful": sum(p["r"] < 1 for p in high),
        },
        "coverage": coverage,
        "decisions": {"diagnosis_holds": group["rule_2_holds"]},
        "points": sorted(
            [p["domain"], p["problem"], round(float(p["s"]), 6),
             round(float(p["u"]), 6), round(float(p["f"]), 6)]
            for p in pairs
        ),
    }


def command_analyze(args):
    P.validate_protocol_without_archive()
    raw_properties = Path(args.properties).read_bytes()
    artifact = analyze(json.loads(raw_properties))
    artifact["properties_sha256"] = hashlib.sha256(raw_properties).hexdigest()
    raw = Common._canonical_json(artifact) + b"\n"
    if Path(args.artifact).resolve() != DEFAULT_ARTIFACT.resolve():
        raise AnalysisError("refusing to write outside the artifact path")
    if DEFAULT_ARTIFACT.exists():
        raise AnalysisError("analysis artifact already exists")
    Frozen._write_atomic(DEFAULT_ARTIFACT, raw)
    digest = hashlib.sha256(raw).hexdigest()
    Frozen._write_atomic(
        str(DEFAULT_ARTIFACT) + ".sha256",
        "{}  {}\n".format(digest, DEFAULT_ARTIFACT.name).encode("ascii"),
    )
    print(digest)
    print(json.dumps(artifact["decisions"], sort_keys=True))
    return 0


def _synthetic(label, task, effort, union, states):
    run = Frozen._synthetic_run(label, task, effort, union)
    run["expanded_states"] = states
    return run


def _self_test():
    cohort = P.load_cohort()

    def build(harmful_union):
        properties = {}
        for number, task in enumerate(cohort):
            blind = _synthetic(P.BLIND_LABEL, task, 1000, 1000, 100)
            if number % 2 == 0:
                # Harmful: few states removed, r = 3.
                heur = _synthetic(P.POT_ALL, task, 3000, harmful_union, 90)
            else:
                # Helpful: most states removed, u = 1/2, frag = 1.
                heur = _synthetic(P.POT_ALL, task, 500, 500, 5)
            properties[str(2 * number)] = blind
            properties[str(2 * number + 1)] = heur
        return properties

    result = analyze(build(1000))
    descriptive = result["descriptive"]
    if not (
        result["decisions"]["diagnosis_holds"]
        and result["group"]["harmful"] == 526
        and result["group"]["share"]["value"] == 1.0
        and descriptive["low_pairs"] == 526
        and descriptive["low_helpful"] == 526
        and descriptive["high_pairs"] == 526
        and descriptive["high_helpful"] == 0
        and descriptive["harmful_u_above_one"] == 0
        and result["coverage"] == {P.BLIND_LABEL: 1052, P.POT_ALL: 1052}
    ):
        raise AnalysisError("self-test: fragmentation harm was not detected")
    # Harm carried by unsplit growth (u = 3, frag = 1) must fail the rule.
    result = analyze(build(3000))
    if (
        result["decisions"]["diagnosis_holds"]
        or result["descriptive"]["harmful_u_above_one"] != 526
    ):
        raise AnalysisError("self-test: unsplit harm was not rejected")
    properties = build(1000)
    del properties["1"]
    try:
        analyze(properties)
    except AnalysisError:
        pass
    else:
        raise AnalysisError("self-test accepted a missing cell")
    print("self-test passed")
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    analyze_parser = sub.add_parser("analyze")
    analyze_parser.add_argument("--properties", type=Path, default=DEFAULT_PROPERTIES)
    analyze_parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    sub.add_parser("self-test")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "analyze":
        return command_analyze(args)
    return _self_test()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, AnalysisError, P.ProtocolError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
