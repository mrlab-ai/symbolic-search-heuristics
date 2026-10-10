#!/usr/bin/env python3
"""Frozen analysis of the prospective harm-generality study.

Pairs every heuristic run with the profiled blind run of its task.  For an
eligible pair, r = effort(h) / effort(blind), u = unionEffort(h) /
effort(blind), and frag = effort(h) / unionEffort(h), so r = u * frag.  The
primary estimand, per family and pooled over all heuristic pairs, is the
share of the log excess carried by fragmentation over harmful pairs (r > 1),
S = sum(ln frag) / sum(ln r).  The decision rule of the frozen protocol
(Section 5 of pdb_profile_harm_generality_protocol.md) is evaluated exactly
as written there; failed rules are reported, never adjusted.

  analyze    read the fetched properties and write the canonical summary
             artifact plus its .sha256 sidecar
  self-test  check the pairing and the decision logic on synthetic runs
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

import pdb_profile_harm_generality_protocol as P
import render_pdb_profile_semantic_union_paper as Common


class AnalysisError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PROPERTIES = (
    SCRIPT_DIR / "data" / "exp_pdb_profile_harm_generality-eval" / "properties"
)
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "pdb-profile-harm-generality"
DEFAULT_ARTIFACT = ARTIFACT_DIR / "analysis-v1.json"
SCHEMA = "symbolic-search-heuristics/pdb-profile-harm-generality-analysis/v1"
POOLED = "pooled"


def _quantile(values, p):
    ordered = sorted(values)
    return ordered[int(p * (len(ordered) - 1))]


def _exact(value):
    return {"numerator": value.numerator, "denominator": value.denominator}


def _real(value):
    return {"value": round(float(value), 6)}


def _median(values):
    return _exact(_quantile(values, Fraction(1, 2))) if values else None


def _positive_int(value):
    return type(value) is int and value > 0


def _overhead_seconds(run):
    summary = run.get("wbh_profile_summary")
    if not isinstance(summary, dict):
        return None
    total = 0.0
    for field in P.OVERHEAD_FIELDS:
        value = summary.get(field, 0)
        if not isinstance(value, (int, float)) or value < 0:
            return None
        total += value
    return total


def _adjusted_time(run):
    """Process time minus the profile's reported overhead, at least 0.01 s."""
    total = run.get("total_time")
    overhead = _overhead_seconds(run)
    if not isinstance(total, (int, float)) or overhead is None:
        return None
    return Fraction(max(total - overhead, 0.01)).limit_denominator(10 ** 6)


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


def _solved(run):
    return run.get("coverage") == 1


def _profiled(run):
    done = run.get("wbh_profile_done")
    return (
        _solved(run)
        and run.get("wbh_profile_certified") is True
        and run.get("wbh_profile_complete") is True
        and run.get("wbh_expansion_profile_certified") is True
        and _positive_int(run.get("effort"))
        and isinstance(done, dict)
        and _positive_int(done.get("layer_union_effort"))
    )


def pairs_from_runs(cohort, runs):
    pairs = []
    for task in cohort:
        blind = runs[(P.BLIND_LABEL, task.domain, task.problem)]
        if not _profiled(blind):
            continue
        for label in P.LABELS[1:]:
            heur = runs[(label, task.domain, task.problem)]
            if not _profiled(heur) or heur.get("cost") != blind.get("cost"):
                continue
            effort = heur["effort"]
            union = heur["wbh_profile_done"]["layer_union_effort"]
            blind_effort = blind["effort"]
            blind_time = _adjusted_time(blind)
            heur_time = _adjusted_time(heur)
            pairs.append({
                "label": label,
                "family": P.FAMILIES[label],
                "domain": task.domain,
                "problem": task.problem,
                "r": Fraction(effort, blind_effort),
                "u": Fraction(union, blind_effort),
                "f": Fraction(effort, union),
                "blind_time": blind_time,
                "time": (
                    heur_time / blind_time
                    if blind_time is not None and heur_time is not None
                    else None
                ),
            })
    return pairs


def evaluate_group(pairs):
    harmful = [p for p in pairs if p["r"] > 1]
    helpful = [p for p in pairs if p["r"] < 1]
    strong = [p for p in pairs if p["r"] > P.STRONG_RATIO]
    log_r = sum(math.log(p["r"]) for p in harmful)
    log_f = sum(math.log(p["f"]) for p in harmful)
    share = log_f / log_r if harmful else None
    strong_frag = sum(p["f"] > p["u"] for p in strong)
    harmful_domains = len({p["domain"] for p in harmful})
    supported = (
        len(harmful) >= P.MIN_HARMFUL_PAIRS
        and harmful_domains >= P.MIN_HARMFUL_DOMAINS
    )
    strong_evaluated = len(strong) >= P.MIN_STRONG_PAIRS
    strong_ok = (
        not strong_evaluated
        or Fraction(strong_frag, len(strong)) >= P.MIN_STRONG_SHARE
    )
    share_ok = share is not None and share >= float(P.MIN_SHARE)
    hard = [
        p for p in pairs
        if p["blind_time"] is not None and p["time"] is not None
        and p["blind_time"] >= P.HARD_BLIND_SECONDS
    ]
    time_harm = [p for p in hard if p["time"] > P.TIME_HARM_RATIO]
    time_help = [p for p in hard if p["time"] < P.TIME_HELP_RATIO]
    return {
        "pairs": len(pairs),
        "pair_domains": len({p["domain"] for p in pairs}),
        "harmful": len(harmful),
        "harmful_domains": harmful_domains,
        "helpful": len(helpful),
        "log_effort_ratio": _real(log_r),
        "log_fragmentation": _real(log_f),
        "share": None if share is None else _real(share),
        "strong": len(strong),
        "strong_frag_above_unsplit": strong_frag,
        "supported": supported,
        "strong_evaluated": strong_evaluated,
        "rule_2_holds": bool(supported and share_ok and strong_ok),
        "harmful_u_median": _median([p["u"] for p in harmful]),
        "harmful_f_median": _median([p["f"] for p in harmful]),
        "helpful_u_median": _median([p["u"] for p in helpful]),
        "helpful_f_median": _median([p["f"] for p in helpful]),
        "hard": len(hard),
        "time_harm": len(time_harm),
        "time_harm_u_median": _median([p["u"] for p in time_harm]),
        "time_harm_f_median": _median([p["f"] for p in time_harm]),
        "time_help": len(time_help),
        "time_help_u_median": _median([p["u"] for p in time_help]),
        "time_help_f_median": _median([p["f"] for p in time_help]),
    }


def coverage_and_headroom(cohort, runs):
    blind_solved = {
        task for task in cohort
        if _solved(runs[(P.BLIND_LABEL, task.domain, task.problem)])
    }
    coverage = {}
    headroom = {}
    for label in P.LABELS:
        solved = {
            task for task in cohort
            if _solved(runs[(label, task.domain, task.problem)])
        }
        coverage[label] = len(solved)
        if label != P.BLIND_LABEL:
            headroom[label] = len(solved - blind_solved)
    families = {}
    for family in sorted(set(P.FAMILIES.values())):
        best = max(
            headroom[label] for label in headroom
            if P.FAMILIES[label] == family
        )
        families[family] = {
            "headroom_tasks": best,
            "at_least_guard_fraction": (
                Fraction(best, len(cohort)) >= P.GUARD_HEADROOM_FRACTION
            ),
        }
    return coverage, headroom, families


def analyze(properties):
    cohort, runs = _index_runs(properties)
    pairs = pairs_from_runs(cohort, runs)
    groups = {POOLED: evaluate_group(pairs)}
    for family in sorted(set(P.FAMILIES.values())):
        groups[family] = evaluate_group(
            [p for p in pairs if p["family"] == family]
        )
    per_config = {
        label: evaluate_group([p for p in pairs if p["label"] == label])
        for label in P.LABELS[1:]
    }
    coverage, headroom, family_headroom = coverage_and_headroom(cohort, runs)
    general = groups[POOLED]["rule_2_holds"] and all(
        groups[family]["rule_2_holds"] for family in P.NON_PDB_FAMILIES
    )
    return {
        "schema": SCHEMA,
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "groups": groups,
        "per_config_descriptive": per_config,
        "coverage": coverage,
        "headroom_tasks": headroom,
        "family_headroom": family_headroom,
        "decisions": {
            "family_claims": {
                family: groups[family]["rule_2_holds"]
                for family in sorted(set(P.FAMILIES.values()))
            },
            "pooled_claim": groups[POOLED]["rule_2_holds"],
            "claim_beyond_pdbs": general,
            "pursue_online_guard": any(
                record["at_least_guard_fraction"]
                for record in family_headroom.values()
            ),
        },
        "points": sorted(
            [p["label"], round(float(p["u"]), 6), round(float(p["f"]), 6)]
            for p in pairs
        ),
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
    print(json.dumps(artifact["decisions"], sort_keys=True))
    return 0


def _synthetic_run(label, task, effort, union, cost=10, solved=True, time=20.0):
    return {
        "algorithm": label,
        "domain": task.domain,
        "problem": task.problem,
        "protocol": P.PROTOCOL,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "planner_binary_sha256": P.PLANNER_BINARY_SHA256,
        "coverage": 1 if solved else 0,
        "cost": cost,
        "effort": effort,
        "total_time": time,
        "wbh_profile_certified": True,
        "wbh_profile_complete": True,
        "wbh_expansion_profile_certified": True,
        "wbh_profile_done": {"layer_union_effort": union},
        "wbh_profile_summary": {field: 0 for field in P.OVERHEAD_FIELDS},
    }


def _self_test():
    cohort = P.load_cohort()
    properties = {}
    index = 0
    for number, task in enumerate(cohort):
        for label in P.LABELS:
            if label == P.BLIND_LABEL:
                run = _synthetic_run(label, task, 1000, 1000)
            elif number % 2 == 0:
                # Harmful by fragmentation: u = 1, frag = 3 (r = 3).
                run = _synthetic_run(label, task, 3000, 1000, time=40.0)
            else:
                # Helpful: u = 1/2, frag = 1.
                run = _synthetic_run(label, task, 500, 500, time=10.0)
            properties[str(index)] = run
            index += 1
    result = analyze(properties)
    if not (
        result["decisions"]["claim_beyond_pdbs"]
        and result["groups"]["ms"]["share"]["value"] == 1.0
        and result["groups"]["ms"]["strong"] == 3 * 526
        and result["groups"]["ms"]["strong_frag_above_unsplit"] == 3 * 526
        and not result["decisions"]["pursue_online_guard"]
    ):
        raise AnalysisError("self-test: fragmentation harm was not detected")
    # Harm carried by unsplit growth: u = 3, frag = 1 must fail rule 2.
    for run in properties.values():
        if run["algorithm"] == "pot_m4" and run["effort"] == 3000:
            run["wbh_profile_done"] = {"layer_union_effort": 3000}
    result = analyze(properties)
    if (
        result["groups"]["pot"]["rule_2_holds"]
        or result["decisions"]["claim_beyond_pdbs"]
        or not result["groups"]["ms"]["rule_2_holds"]
    ):
        raise AnalysisError("self-test: unsplit harm was not rejected")
    # Cost disagreement and missing cells.
    first = next(iter(properties.values()))
    first_key = next(iter(properties))
    properties[first_key] = dict(first, cost=11)
    analyze(properties)
    del properties[first_key]
    try:
        analyze(properties)
    except AnalysisError:
        pass
    else:
        raise AnalysisError("self-test accepted a missing cell")
    # Guard headroom: heuristic solves 40 tasks blind does not (3.8%).
    properties = {}
    index = 0
    for number, task in enumerate(cohort):
        for label in P.LABELS:
            solved = label != P.BLIND_LABEL or number >= 40
            properties[str(index)] = _synthetic_run(
                label, task, 1000, 1000, solved=solved
            )
            index += 1
    result = analyze(properties)
    if not result["decisions"]["pursue_online_guard"]:
        raise AnalysisError("self-test: guard headroom was not detected")
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
