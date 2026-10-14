#!/usr/bin/env python3
"""Frozen analysis of the prospective bounded-search study.

Evaluates Section 5 of bounded_search_protocol.md exactly as written: nine
primary exact two-sided sign tests on solved-task discordance (bounded
search with each heuristic against BDDA* with the same heuristic, against
blind forward search and against bounded blind search), Holm adjustment at
family-wise alpha 0.05, and descriptive coverage, PAR2, comparisons with
blind bidirectional search, effort and time medians, and first-phase
statistics.  Bounded runs solve their task only if the planner exits with
code 0 and reports a best plan cost (Section 2); their cost is the last best
cost and their effort the nodes of all completed symbolic expansions.  The
frozen outcome, sign-test and Holm functions of
analyze_fragmentation_remedy.py are reused with this study's protocol.

  analyze    read the fetched properties and write the canonical summary
             artifact plus its .sha256 sidecar
  self-test  check the tests and the claim logic on synthetic runs
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from fractions import Fraction
from pathlib import Path

import analyze_fragmentation_remedy as Remedy
import bounded_search_protocol as P
import render_pdb_profile_semantic_union_paper as Common


Remedy.P = P
AnalysisError = Remedy.AnalysisError
SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROPERTIES = (
    SCRIPT_DIR / "data" / "exp_bounded_search-eval" / "properties"
)
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "bounded-search"
DEFAULT_ARTIFACT = ARTIFACT_DIR / "analysis-v1.json"
SCHEMA = "symbolic-search-heuristics/bounded-search-analysis/v1"
_real = Remedy._real
_median = Remedy._median


def normalize(properties):
    """Apply the solved, cost and effort definitions of Section 2 to the
    bounded runs; other runs are unchanged."""
    result = copy.deepcopy(properties)
    for run in result.values():
        if run.get("algorithm") not in P.BOUNDED_LABELS:
            continue
        if run.get("bounded_parse_error"):
            raise AnalysisError("bounded run with a parse error")
        final = run.get("bounded_final_cost")
        solved = run.get("planner_exit_code") == 0 and isinstance(final, int)
        run["coverage"] = 1 if solved else 0
        run["cost"] = final if solved else None
        nodes = run.get("bounded_expanded_nodes")
        run["effort"] = nodes if solved and isinstance(nodes, int) and nodes > 0 \
            else None
    return result


def _first_phase(cohort, runs, outcomes, label, optimal_costs):
    found = 0
    optimal, ratios = 0, []
    for t in cohort:
        run = runs[(label, t.domain, t.problem)]
        bound = run.get("bounded_bound")
        if isinstance(bound, int):
            found += 1
        if not outcomes[(label, t)][0] or not isinstance(bound, int):
            continue
        cost = optimal_costs.get(t)
        if cost is None or cost <= 0:
            continue
        optimal += bound == cost
        ratios.append(Fraction(bound, cost))
    return {
        "first_phase_plans": found,
        "solved_with_bound": len(ratios),
        "bound_optimal": optimal,
        "bound_ratio_median": _real(_median(ratios)),
    }


def analyze(properties):
    cohort, runs = Remedy._index_runs(normalize(properties))
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
    pairs = [(P.BLIND_BD, P.BLIND_FW), (P.BLIND_BOUNDED, P.BLIND_FW),
             (P.BLIND_BOUNDED, P.BLIND_BD)]
    for family in P.FAMILY_NAMES:
        pairs += [("{}_bounded".format(family), P.BLIND_BD),
                  ("{}_plain".format(family), P.BLIND_FW)]
    for label, reference in pairs:
        gains, losses = Remedy._discordance(cohort, outcomes, label, reference)
        context["{}_vs_{}".format(label, reference)] = {
            "gains": gains, "losses": losses,
            "p_unadjusted": _real(Remedy.sign_test(gains, losses), 8),
        }
    optimal_costs = {}
    for t in cohort:
        costs = {runs[(label, t.domain, t.problem)]["cost"]
                 for label in P.LABELS if outcomes[(label, t)][0]}
        if len(costs) == 1:
            optimal_costs[t] = costs.pop()
    mechanism, first_phase = {}, {}
    for family in P.FAMILY_NAMES:
        plain = "{}_plain".format(family)
        bounded = "{}_bounded".format(family)
        labels = (plain, bounded, P.BLIND_FW)
        mechanism[family] = {
            "plain": Remedy._ratios(cohort, outcomes, labels, plain),
            "bounded": Remedy._ratios(cohort, outcomes, labels, bounded),
        }
    for label in P.BOUNDED_LABELS:
        first_phase[label] = _first_phase(
            cohort, runs, outcomes, label, optimal_costs)
    return {
        "schema": SCHEMA,
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "cost_conflicts": conflicts,
        "coverage": {
            label: Remedy._coverage(cohort, outcomes, label)
            for label in P.LABELS
        },
        "primary_tests": tests,
        "claims": claims,
        "context": context,
        "mechanism": mechanism,
        "first_phase": first_phase,
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
                "total_time": time,
            }
            if label in P.BOUNDED_LABELS:
                # Lab's coverage and first-match cost must be ignored.
                run.update({
                    "coverage": 1, "cost": 12,
                    "planner_exit_code": 0 if solved else 23,
                    "bounded_bound": 12,
                    "bounded_final_cost": 10,
                    "bounded_expanded_nodes": effort,
                })
            else:
                run.update({"coverage": 1 if solved else 0,
                            "cost": 10 if solved else None,
                            "effort": effort if solved else None})
            properties[str(index)] = run
            index += 1
    return properties


def _self_test():
    def solve(label, number):
        # Blind solves even tasks; bounded heuristic search adds every third
        # odd task; bounded blind search and plain heuristics solve < 600.
        if label in (P.BLIND_FW, P.BLIND_BD):
            return number % 2 == 0, 10.0, 1000
        if label.endswith("_bounded") and label != P.BLIND_BOUNDED:
            return number % 2 == 0 or number % 6 == 1, 8.0, 800
        return number < 600, 20.0, 3000

    result = analyze(_synthetic_properties(solve))
    claims = result["claims"]
    if claims["H2:ms_bounded"] != "better":
        raise AnalysisError("self-test: bounded gain over blind missed")
    if result["cost_conflicts"]:
        raise AnalysisError("self-test: final costs were not used")
    record = result["first_phase"]["pot_bounded"]
    if record["bound_optimal"] != 0 or record["bound_ratio_median"] != 1.2:
        raise AnalysisError("self-test: first-phase statistics")
    expected = sum(1 for n in range(P.COHORT_TASKS) if n % 2 == 0 or n % 6 == 1)
    if result["coverage"]["pdb_bounded"]["solved"] != expected:
        raise AnalysisError("self-test: bounded coverage")
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
