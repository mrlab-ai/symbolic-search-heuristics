#!/usr/bin/env python3
"""Frozen analysis of the prospective fragmentation-remedy study.

Evaluates Section 5 of fragmentation_remedy_protocol.md exactly as written:
twelve primary exact two-sided sign tests on solved-task discordance (each
remedy against its plain heuristic and against blind forward search), Holm
adjustment at family-wise alpha 0.05, and descriptive coverage, PAR2,
bidirectional context, mechanism medians, and the effort-time relation.

  analyze    read the fetched properties and write the canonical summary
             artifact plus its .sha256 sidecar
  self-test  check the tests and the claim logic on synthetic runs
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

import fragmentation_remedy_protocol as P
import render_pdb_profile_semantic_union_paper as Common


class AnalysisError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROPERTIES = (
    SCRIPT_DIR / "data" / "exp_fragmentation_remedy-eval" / "properties"
)
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "fragmentation-remedy"
DEFAULT_ARTIFACT = ARTIFACT_DIR / "analysis-v1.json"
SCHEMA = "symbolic-search-heuristics/fragmentation-remedy-analysis/v1"
MIN_TIME = 0.01


def _real(value, places=6):
    return None if value is None else round(float(value), places)


def _median(values):
    ordered = sorted(values)
    if not ordered:
        return None
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def sign_test(gains, losses):
    """Exact two-sided binomial test of gains out of gains + losses."""
    n = gains + losses
    if n == 0:
        return Fraction(1)
    tail = sum(math.comb(n, k) for k in range(min(gains, losses) + 1))
    return min(Fraction(1), Fraction(2 * tail, 2 ** n))


def holm(pvalues):
    """Holm-adjusted p-values for a mapping name -> p."""
    order = sorted(pvalues, key=lambda name: (pvalues[name], name))
    adjusted, running = {}, Fraction(0)
    m = len(order)
    for rank, name in enumerate(order):
        running = max(running, min(Fraction(1), (m - rank) * pvalues[name]))
        adjusted[name] = running
    return adjusted


def _ranks(values):
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs, ys):
    if len(xs) < 3:
        return None
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx = sum((a - mx) ** 2 for a in rx)
    syy = sum((b - my) ** 2 for b in ry)
    if sxx == 0 or syy == 0:
        return None
    return sxy / math.sqrt(sxx * syy)


def _index_runs(properties):
    cohort = P.load_cohort()
    expected = {
        (label, task.domain, task.problem)
        for label in P.LABELS
        for task in cohort
    }
    runs = {}
    for run in properties.values():
        key = (run.get("algorithm"), run.get("domain"), run.get("problem"))
        if key not in expected:
            raise AnalysisError("unexpected run {}".format(key))
        if key in runs:
            raise AnalysisError("duplicate run {}".format(key))
        if (
            run.get("protocol") != P.PROTOCOL
            or run.get("option_matrix_sha256") != P.OPTION_MATRIX_SHA256
            or run.get("protocol_sha256") != P.PROTOCOL_SHA256
            or run.get("planner_binary_sha256") != P.PLANNER_BINARY_SHA256
        ):
            raise AnalysisError("run {} has foreign provenance".format(key))
        runs[key] = run
    if set(runs) != expected:
        raise AnalysisError(
            "{} of {} cells are missing".format(
                len(expected) - len(runs), len(expected)
            )
        )
    return cohort, runs


def _outcomes(cohort, runs):
    """Per task and label: (solved, time, effort); cost conflicts unsolve."""
    outcomes, conflicts = {}, []
    for task in cohort:
        costs = {
            runs[(label, task.domain, task.problem)].get("cost")
            for label in P.LABELS
            if runs[(label, task.domain, task.problem)].get("coverage") == 1
        }
        conflict = len(costs) > 1
        if conflict:
            conflicts.append("{}:{}".format(task.domain, task.problem))
        for label in P.LABELS:
            run = runs[(label, task.domain, task.problem)]
            solved = run.get("coverage") == 1 and not conflict
            total = run.get("total_time")
            time = (
                max(float(total), MIN_TIME)
                if solved and isinstance(total, (int, float)) else None
            )
            if solved and time is None:
                raise AnalysisError("solved run lacks total_time")
            effort = run.get("effort")
            outcomes[(label, task)] = (
                solved,
                time,
                effort if solved and type(effort) is int and effort > 0
                else None,
            )
    return outcomes, conflicts


def _discordance(cohort, outcomes, label, reference):
    gains = sum(
        outcomes[(label, t)][0] and not outcomes[(reference, t)][0]
        for t in cohort
    )
    losses = sum(
        outcomes[(reference, t)][0] and not outcomes[(label, t)][0]
        for t in cohort
    )
    return gains, losses


def _coverage(cohort, outcomes, label):
    solved = [t for t in cohort if outcomes[(label, t)][0]]
    domains = sorted({t.domain for t in cohort})
    per_domain = [
        Fraction(
            sum(1 for t in solved if t.domain == d),
            sum(1 for t in cohort if t.domain == d),
        )
        for d in domains
    ]
    par2 = sum(
        outcomes[(label, t)][1] if outcomes[(label, t)][0]
        else P.PAR2_UNSOLVED_SECONDS
        for t in cohort
    )
    return {
        "solved": len(solved),
        "domain_average_percent": _real(100 * sum(per_domain) / len(domains), 4),
        "par2_sum": _real(par2, 3),
    }


def _ratios(cohort, outcomes, labels, numerator):
    """Medians of effort and time of `numerator` over blind forward search,
    on the tasks that every label in `labels` solves."""
    tasks = [t for t in cohort if all(outcomes[(l, t)][0] for l in labels)]
    effort = [
        outcomes[(numerator, t)][2] / outcomes[(P.BLIND_FW, t)][2]
        for t in tasks
        if outcomes[(numerator, t)][2] and outcomes[(P.BLIND_FW, t)][2]
    ]
    time = [outcomes[(numerator, t)][1] / outcomes[(P.BLIND_FW, t)][1]
            for t in tasks]
    return {
        "tasks": len(tasks),
        "effort_ratio_median": _real(_median(effort)),
        "time_ratio_median": _real(_median(time)),
    }


def _effort_time(cohort, outcomes, labels):
    xs, ys = [], []
    for label in labels:
        for t in cohort:
            heur, blind = outcomes[(label, t)], outcomes[(P.BLIND_FW, t)]
            if not (heur[0] and blind[0] and heur[2] and blind[2]):
                continue
            if blind[1] < P.EFFORT_TIME_MIN_BLIND_SECONDS:
                continue
            xs.append(math.log(heur[2] / blind[2]))
            ys.append(math.log(heur[1] / blind[1]))
    same = sum((x > 0) == (y > 0) for x, y in zip(xs, ys))
    return {
        "pairs": len(xs),
        "spearman": _real(spearman(xs, ys)),
        "same_side_fraction": _real(Fraction(same, len(xs)) if xs else None),
    }


def analyze(properties):
    cohort, runs = _index_runs(properties)
    outcomes, conflicts = _outcomes(cohort, runs)
    tests = {}
    raw = {}
    for name, label, reference in P.primary_tests():
        gains, losses = _discordance(cohort, outcomes, label, reference)
        raw[name] = sign_test(gains, losses)
        tests[name] = {"config": label, "reference": reference,
                       "gains": gains, "losses": losses,
                       "p": _real(raw[name], 8)}
    adjusted = holm(raw)
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
    for label, reference in (
        (P.BLIND_BD, P.BLIND_FW),
        (P.BD_MS_PRUNE, P.BLIND_FW),
        (P.BD_MS_PRUNE, P.BLIND_BD),
    ):
        gains, losses = _discordance(cohort, outcomes, label, reference)
        context["{}_vs_{}".format(label, reference)] = {
            "gains": gains, "losses": losses,
            "p_unadjusted": _real(sign_test(gains, losses), 8),
        }
    for reference in (P.BLIND_FW, "pot_plain"):
        gains, losses = _discordance(cohort, outcomes, P.POT_ALL, reference)
        context["{}_vs_{}".format(P.POT_ALL, reference)] = {
            "gains": gains, "losses": losses,
            "p_unadjusted": _real(sign_test(gains, losses), 8),
        }
    context["{}_effort".format(P.POT_ALL)] = _ratios(
        cohort, outcomes, (P.POT_ALL, P.BLIND_FW), P.POT_ALL)
    bd_headroom = {
        label: _discordance(cohort, outcomes, label, P.BLIND_BD)[0]
        for label in P.LABELS if label != P.BLIND_BD
    }
    mechanism = {}
    for family in P.FAMILY_NAMES:
        plain = "{}_plain".format(family)
        for remedy in P.REMEDIES:
            label = "{}_{}".format(family, remedy)
            labels = (plain, label, P.BLIND_FW)
            mechanism[label] = {
                "plain": _ratios(cohort, outcomes, labels, plain),
                "remedy": _ratios(cohort, outcomes, labels, label),
            }
    plains = ["{}_plain".format(f) for f in P.FAMILY_NAMES]
    effort_time = {
        family: _effort_time(cohort, outcomes, ["{}_plain".format(family)])
        for family in P.FAMILY_NAMES
    }
    effort_time["pooled"] = _effort_time(cohort, outcomes, plains)
    return {
        "schema": SCHEMA,
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "batch_windows": dict(P.BATCH_WINDOWS),
        "cost_conflicts": conflicts,
        "coverage": {
            label: _coverage(cohort, outcomes, label) for label in P.LABELS
        },
        "primary_tests": tests,
        "claims": claims,
        "bidirectional_context": context,
        "headroom_over_blind_bd": bd_headroom,
        "mechanism": mechanism,
        "effort_time": effort_time,
    }


def _write_atomic(path, raw):
    path = Path(path)
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


def command_analyze(args):
    P.validate_protocol_without_archive()
    raw_properties = Path(args.properties).read_bytes()
    properties = json.loads(raw_properties)
    artifact = analyze(properties)
    artifact["properties_sha256"] = hashlib.sha256(raw_properties).hexdigest()
    raw = Common._canonical_json(artifact) + b"\n"
    if Path(args.artifact).resolve() != DEFAULT_ARTIFACT.resolve():
        raise AnalysisError("refusing to write outside the artifact path")
    if DEFAULT_ARTIFACT.exists():
        raise AnalysisError("analysis artifact already exists")
    _write_atomic(DEFAULT_ARTIFACT, raw)
    digest = hashlib.sha256(raw).hexdigest()
    _write_atomic(
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
            properties[str(index)] = {
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
            index += 1
    return properties


def _self_test():
    if sign_test(0, 0) != 1 or sign_test(5, 5) != 1:
        raise AnalysisError("self-test: sign test of balanced discordance")
    if sign_test(10, 0) != Fraction(2, 1024):
        raise AnalysisError("self-test: sign test tail")
    adjusted = holm({"a": Fraction(1, 100), "b": Fraction(4, 100),
                     "c": Fraction(3, 100)})
    if adjusted != {"a": Fraction(3, 100), "c": Fraction(6, 100),
                    "b": Fraction(6, 100)}:
        raise AnalysisError("self-test: Holm adjustment")
    if spearman([1, 2, 3, 4], [10, 20, 30, 40]) != 1.0:
        raise AnalysisError("self-test: Spearman")

    def solve(label, number):
        # Blind solves even tasks; prune-only adds every third odd task;
        # batching matches the plain heuristic, which solves tasks < 600.
        if label == P.BLIND_FW:
            return number % 2 == 0, 10.0, 1000
        if label.endswith("_prune"):
            return number % 2 == 0 or number % 6 == 1, 8.0, 900
        if label.endswith("_plain") or label.endswith("_batch"):
            return number < 600, 20.0, 3000
        return number % 2 == 0, 5.0, 500

    result = analyze(_synthetic_properties(solve))
    claims = result["claims"]
    if claims["H2:ms_prune"] != "better":
        raise AnalysisError("self-test: prune-only gain over blind missed")
    if claims["H1:ms_batch"] != "not_significant":
        raise AnalysisError("self-test: identical configurations differ")
    if result["coverage"][P.BLIND_FW]["solved"] != 526:
        raise AnalysisError("self-test: coverage count")
    pooled = result["effort_time"]["pooled"]
    if pooled["same_side_fraction"] != 1.0:
        raise AnalysisError("self-test: effort and time sides")
    # A cost conflict unsolves the whole task.
    properties = _synthetic_properties(solve)
    first = next(iter(properties.values()))
    for run in properties.values():
        if (run["domain"], run["problem"]) == (first["domain"], first["problem"]) \
                and run["algorithm"] == P.BLIND_BD:
            run["cost"] = 11
    result = analyze(properties)
    if len(result["cost_conflicts"]) != 1:
        raise AnalysisError("self-test: cost conflict not reported")
    if result["coverage"][P.BLIND_FW]["solved"] != 525:
        raise AnalysisError("self-test: conflicting task still counted")
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
