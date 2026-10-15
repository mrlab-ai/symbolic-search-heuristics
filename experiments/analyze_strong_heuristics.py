#!/usr/bin/env python3
"""Frozen analysis of the prospective strong-heuristics study.

Pairs every run of the two strong heuristics (potentials optimized for all
states with weights in [-1000, 1000], and M&S with 200,000 abstract states)
with the profiled blind run of its task and evaluates the decision rule of
Section 5 of strong_heuristics_protocol.md per heuristic with the frozen
pairing and group functions of analyze_pdb_profile_harm_generality.py, whose
protocol module is replaced by this study's.  It adds the state ratio
s = expanded states(h) / expanded states(blind) of every pair for the
descriptive quantities.  Failed rules are reported, never adjusted.

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
import strong_heuristics_protocol as P
import render_pdb_profile_semantic_union_paper as Common


Frozen.P = P
AnalysisError = Frozen.AnalysisError
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROPERTIES = (
    SCRIPT_DIR / "data" / "exp_strong_heuristics-eval" / "properties"
)
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "strong-heuristics"
DEFAULT_ARTIFACT = ARTIFACT_DIR / "analysis-v1.json"
SCHEMA = "symbolic-search-heuristics/strong-heuristics-analysis/v1"
LOW_STATE_RATIO = Fraction(1, 10)
HIGH_STATE_RATIO = Fraction(4, 5)


def _states(run):
    # Large state counts come from BDD model counting as doubles.
    value = run.get("expanded_states")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not value > 0:
        raise AnalysisError("solved run without positive expanded states")
    return Fraction(value)


def _descriptive(pairs):
    harmful = [p for p in pairs if p["r"] > 1]
    helpful = [p for p in pairs if p["r"] < 1]
    low = [p for p in pairs if p["s"] < LOW_STATE_RATIO]
    high = [p for p in pairs if p["s"] >= HIGH_STATE_RATIO]
    return {
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
    }


def analyze(properties):
    cohort, runs = Frozen._index_runs(properties)
    pairs = Frozen.pairs_from_runs(cohort, runs)
    for p in pairs:
        blind = runs[(P.BLIND_LABEL, p["domain"], p["problem"])]
        heur = runs[(p["label"], p["domain"], p["problem"])]
        p["s"] = _states(heur) / _states(blind)
    groups, descriptive, decisions = {}, {}, {}
    for label in P.LABELS[1:]:
        mine = [p for p in pairs if p["label"] == label]
        groups[label] = Frozen.evaluate_group(mine)
        descriptive[label] = _descriptive(mine)
        decisions[label] = groups[label]["rule_2_holds"]
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
        "groups": groups,
        "descriptive": descriptive,
        "coverage": coverage,
        "decisions": decisions,
        "points": sorted(
            [p["label"], p["domain"], p["problem"], round(float(p["s"]), 6),
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
        properties, index = {}, 0
        for number, task in enumerate(cohort):
            properties[str(index)] = _synthetic(P.BLIND_LABEL, task, 1000, 1000, 100)
            index += 1
            for label in P.LABELS[1:]:
                if number % 2 == 0:
                    run = _synthetic(label, task, 3000, harmful_union, 90)
                else:
                    run = _synthetic(label, task, 500, 500, 5)
                properties[str(index)] = run
                index += 1
        return properties

    result = analyze(build(1000))
    for label in P.LABELS[1:]:
        d = result["descriptive"][label]
        if not (result["decisions"][label]
                and result["groups"][label]["harmful"] == 526
                and d["low_helpful"] == 526 and d["high_helpful"] == 0):
            raise AnalysisError("self-test: fragmentation harm was not detected")
    result = analyze(build(3000))
    if any(result["decisions"].values()):
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
