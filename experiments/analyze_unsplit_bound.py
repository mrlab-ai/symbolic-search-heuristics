#!/usr/bin/env python3
"""Frozen analysis of the prospective unsplit-bound study.

Evaluates Section 5 of unsplit_bound_protocol.md exactly as written: six
primary exact two-sided sign tests on solved-task discordance (unsplit
f-bounded search against BDDA* with the same heuristic and against blind
forward search), Holm adjustment at family-wise alpha 0.05, and descriptive
coverage, PAR2, comparisons with blind bidirectional search, effort and time
medians, and iteration statistics.  It reuses the frozen outcome, sign-test
and Holm functions of analyze_fragmentation_remedy.py with this study's
protocol module.

  analyze    read the fetched properties and write the canonical summary
             artifact plus its .sha256 sidecar
  self-test  check the tests and the claim logic on synthetic runs
"""

from __future__ import annotations

import argparse
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import analyze_fragmentation_remedy as Remedy
import render_pdb_profile_semantic_union_paper as Common
import unsplit_bound_protocol as P


Remedy.P = P
AnalysisError = Remedy.AnalysisError
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROPERTIES = (
    SCRIPT_DIR / "data" / "exp_unsplit_bound-eval" / "properties"
)
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "unsplit-bound"
DEFAULT_ARTIFACT = ARTIFACT_DIR / "analysis-v1.json"
SCHEMA = "symbolic-search-heuristics/unsplit-bound-analysis/v1"
_real = Remedy._real
_median = Remedy._median


def _iterations(cohort, runs, outcomes, label):
    """Iteration statistics over the solved runs of an unsplit config."""
    counts, shares, overshoots = [], [], []
    for t in cohort:
        if not outcomes[(label, t)][0]:
            continue
        run = runs[(label, t.domain, t.problem)]
        iterations = run.get("unsplit_iterations")
        final = run.get("unsplit_final_nodes")
        bound = run.get("unsplit_final_bound")
        effort = outcomes[(label, t)][2]
        if not (isinstance(iterations, int) and iterations > 0
                and run.get("unsplit_final_solved") is True
                and isinstance(final, int) and isinstance(bound, int)):
            raise AnalysisError("solved unsplit run without iteration log")
        counts.append(iterations)
        if effort:
            shares.append(Fraction(final, effort))
        overshoots.append(bound - run["cost"])
    return {
        "solved": len(counts),
        "iterations_median": _real(_median(counts)),
        "last_iteration_share_median": _real(_median(shares)),
        "bound_overshoot_median": _real(_median(overshoots)),
    }


def analyze(properties):
    cohort, runs = Remedy._index_runs(properties)
    outcomes, conflicts = Remedy._outcomes(cohort, runs)
    tests, raw = {}, {}
    for name, label, reference in P.primary_tests():
        gains, losses = Remedy._discordance(cohort, outcomes, label, reference)
        raw[name] = Remedy.sign_test(gains, losses)
        tests[name] = {"config": label, "reference": reference,
                       "gains": gains, "losses": losses,
                       "p": _real(raw[name], 8)}
    adjusted = Remedy.holm(raw)
    claims = {}
    for name, record in tests.items():
        significant = adjusted[name] <= P.ALPHA
        record["p_holm"] = _real(adjusted[name], 8)
        record["significant"] = significant
        if significant and record["gains"] > record["losses"]:
            verdict = "better"
        elif significant and record["losses"] > record["gains"]:
            verdict = "worse"
        else:
            verdict = "not_significant"
        claims[name] = verdict
    context = {}
    pairs = [(P.BLIND_BD, P.BLIND_FW)]
    for family in P.FAMILY_NAMES:
        pairs += [("{}_unsplit".format(family), P.BLIND_BD),
                  ("{}_plain".format(family), P.BLIND_FW)]
    for label, reference in pairs:
        gains, losses = Remedy._discordance(cohort, outcomes, label, reference)
        context["{}_vs_{}".format(label, reference)] = {
            "gains": gains, "losses": losses,
            "p_unadjusted": _real(Remedy.sign_test(gains, losses), 8),
        }
    mechanism, iterations = {}, {}
    for family in P.FAMILY_NAMES:
        plain = "{}_plain".format(family)
        unsplit = "{}_unsplit".format(family)
        labels = (plain, unsplit, P.BLIND_FW)
        mechanism[family] = {
            "plain": Remedy._ratios(cohort, outcomes, labels, plain),
            "unsplit": Remedy._ratios(cohort, outcomes, labels, unsplit),
        }
        iterations[family] = _iterations(cohort, runs, outcomes, unsplit)
    return {
        "schema": SCHEMA,
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "schedules": dict(P.SCHEDULES),
        "cost_conflicts": conflicts,
        "coverage": {
            label: Remedy._coverage(cohort, outcomes, label)
            for label in P.LABELS
        },
        "primary_tests": tests,
        "claims": claims,
        "context": context,
        "mechanism": mechanism,
        "iterations": iterations,
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
    Remedy._write_atomic(DEFAULT_ARTIFACT, raw)
    digest = hashlib.sha256(raw).hexdigest()
    Remedy._write_atomic(
        str(DEFAULT_ARTIFACT) + ".sha256",
        "{}  {}\n".format(digest, DEFAULT_ARTIFACT.name).encode("ascii"),
    )
    print(digest)
    print(json.dumps(artifact["claims"], sort_keys=True))
    return 0


def _synthetic_properties(solve):
    """solve(label, number) -> (solved, time, effort)."""
    properties, index = {}, 0
    for number, task in enumerate(P.load_cohort()):
        for label in P.LABELS:
            solved, time, effort = solve(label, number)
            run = {
                "algorithm": label,
                "domain": task.domain,
                "problem": task.problem,
                "protocol": P.PROTOCOL,
                "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
                "protocol_sha256": P.PROTOCOL_SHA256,
                "planner_binary_sha256": P.PLANNER_BINARY_SHA256,
                "coverage": 1 if solved else 0,
                "cost": 10 if solved else None,
                "total_time": time,
                "effort": effort if solved else None,
            }
            if label.endswith("_unsplit") and solved:
                run.update({"unsplit_iterations": 3,
                            "unsplit_final_bound": 12,
                            "unsplit_final_nodes": effort // 2,
                            "unsplit_final_solved": True})
            properties[str(index)] = run
            index += 1
    return properties


def _self_test():
    def solve(label, number):
        # Blind solves even tasks; unsplit search adds every third odd task;
        # the plain heuristic solves tasks below 600.
        if label in (P.BLIND_FW, P.BLIND_BD):
            return number % 2 == 0, 10.0, 1000
        if label.endswith("_unsplit"):
            return number % 2 == 0 or number % 6 == 1, 8.0, 800
        return number < 600, 20.0, 3000

    result = analyze(_synthetic_properties(solve))
    claims = result["claims"]
    if claims["H2:ms_unsplit"] != "better":
        raise AnalysisError("self-test: unsplit gain over blind missed")
    if result["coverage"][P.BLIND_FW]["solved"] != 526:
        raise AnalysisError("self-test: coverage count")
    record = result["iterations"]["pdb"]
    if (record["iterations_median"] != 3
            or record["last_iteration_share_median"] != 0.5
            or record["bound_overshoot_median"] != 2):
        raise AnalysisError("self-test: iteration statistics")
    properties = _synthetic_properties(solve)
    for run in properties.values():
        if run["algorithm"] == "pot_unsplit" and run["coverage"] == 1:
            del run["unsplit_iterations"]
            break
    try:
        analyze(properties)
    except AnalysisError:
        pass
    else:
        raise AnalysisError("self-test accepted a run without iterations")
    properties = _synthetic_properties(solve)
    del properties[next(iter(properties))]
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
    if args.command == "self-test":
        return _self_test()
    return command_analyze(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, AnalysisError, P.ProtocolError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
