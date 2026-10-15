#!/usr/bin/env python3
"""Frozen analysis of the CPDDL GHSETA* study (cpddl_ghseta_protocol.md).

Reads the cell records in symk-cpddl/{dev,holdout}/runs and evaluates
Section 5 of the protocol: two primary exact two-sided sign tests (forward
GHSETA* with operator potentials against blind forward search, and
bidirectional search with forward potentials against blind bidirectional
search) with Holm adjustment at family-wise alpha 0.05, descriptive coverage
and PAR2, and the decomposition of the forward effort into the unsplit ratio
u and the fragmentation factor relative to blind search.  On the
development cohort it writes the pilot summary of Section 4 instead.

  analyze --cohort dev|holdout   write artifacts/cpddl-ghseta/{pilot,analysis}-v1.json
  self-test                      check the statistics on synthetic cells
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path

import analyze_fragmentation_remedy as Remedy
import render_pdb_profile_semantic_union_paper as Common


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = Path("/nobackup/proj/disk/dfsplan/personal/jendrik/symk-cpddl")
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "cpddl-ghseta"
PROTOCOL_PATH = SCRIPT_DIR / "cpddl_ghseta_protocol.md"
PROTOCOL_SHA256 = "TO_PIN"
LABELS = ("cp_blind_fw", "cp_pot_fw", "cp_blind_bi", "cp_pot_bi",
          "cp_blind_fw_prof", "cp_pot_fw_prof")
PRIMARY = (("H-A", "cp_pot_fw", "cp_blind_fw"),
           ("H-B", "cp_pot_bi", "cp_blind_bi"))
CONTEXT = (("cp_pot_bi", "cp_pot_fw"), ("cp_blind_bi", "cp_blind_fw"))
ALPHA = Fraction(5, 100)
PAR2_UNSOLVED_SECONDS = 600
STRONG_RATIO = 2
LOW_STATE_RATIO = Fraction(1, 10)
HIGH_STATE_RATIO = Fraction(4, 5)


class AnalysisError(RuntimeError):
    pass


def load_cells(cohort_dir):
    tasks = json.load(open(cohort_dir / "tasks.json"))
    configs = json.load(open(cohort_dir / "configs.json"))
    if [c[0] for c in configs] != list(LABELS):
        raise AnalysisError("configurations differ from the protocol")
    cells = {}
    for label in LABELS:
        for task in tasks:
            path = cohort_dir / "runs" / label / "{}__{}".format(
                task["domain"], task["problem"]) / "cell.json"
            try:
                cells[(label, task["domain"], task["problem"])] = json.load(
                    open(path))
            except (OSError, ValueError) as err:
                raise AnalysisError("missing cell {}".format(path)) from err
    return [(t["domain"], t["problem"]) for t in tasks], cells


def _median(values):
    return Remedy._median(sorted(values)) if values else None


def _real(value, places=6):
    return None if value is None else round(float(value), places)


def outcomes(tasks, cells):
    """Per (label, task): solved after the cost-conflict rule."""
    conflicts = []
    solved = {}
    for task in tasks:
        costs = {cells[(l,) + task]["cost"] for l in LABELS
                 if cells[(l,) + task]["solved"]}
        conflict = len(costs) > 1
        if conflict:
            conflicts.append("{}:{}".format(*task))
        for label in LABELS:
            solved[(label, task)] = cells[(label,) + task]["solved"] and not conflict
    return solved, conflicts


def discordance(tasks, solved, label, reference):
    gains = sum(solved[(label, t)] and not solved[(reference, t)] for t in tasks)
    losses = sum(solved[(reference, t)] and not solved[(label, t)] for t in tasks)
    return gains, losses


def coverage(tasks, cells, solved, label):
    par2 = sum(cells[(label,) + t]["wall_seconds"] if solved[(label, t)]
               else PAR2_UNSOLVED_SECONDS for t in tasks)
    return {"solved": sum(solved[(label, t)] for t in tasks),
            "par2_sum": _real(par2, 3)}


def decomposition(tasks, cells, solved):
    pairs = []
    blind_frag = []
    for task in tasks:
        b = cells[("cp_blind_fw_prof",) + task]
        h = cells[("cp_pot_fw_prof",) + task]
        if not (solved[("cp_blind_fw_prof", task)]
                and solved[("cp_pot_fw_prof", task)]):
            continue
        values = [b.get(k) for k in ("wbh_expand_nodes", "wbh_layer_nodes",
                                     "wbh_expand_states")]
        values += [h.get(k) for k in ("wbh_expand_nodes", "wbh_layer_nodes",
                                      "wbh_expand_states")]
        if not all(isinstance(x, (int, float)) and x > 0 for x in values):
            continue
        be, bu, bs, he, hu, hs = values
        r = Fraction(he, be)
        u = Fraction(hu, bu)
        pairs.append({"task": task, "r": r, "u": u, "f": r / u,
                      "s": Fraction(hs) / Fraction(bs)})
        blind_frag.append(Fraction(be, bu))
    harmful = [p for p in pairs if p["r"] > 1]
    helpful = [p for p in pairs if p["r"] < 1]
    strong = [p for p in pairs if p["r"] > STRONG_RATIO]
    log_r = sum(math.log(p["r"]) for p in harmful)
    log_f = sum(math.log(p["f"]) for p in harmful)
    low = [p for p in pairs if p["s"] < LOW_STATE_RATIO]
    high = [p for p in pairs if p["s"] >= HIGH_STATE_RATIO]

    def med(group, key):
        return _real(_median([p[key] for p in group]))

    return {
        "pairs": len(pairs),
        "pair_domains": len({p["task"][0] for p in pairs}),
        "harmful": len(harmful),
        "helpful": len(helpful),
        "share": _real(log_f / log_r) if harmful and log_r > 0 else None,
        "strong": len(strong),
        "strong_frag_above_unsplit": sum(p["f"] > p["u"] for p in strong),
        "harmful_u_median": med(harmful, "u"),
        "harmful_f_median": med(harmful, "f"),
        "harmful_s_median": med(harmful, "s"),
        "helpful_u_median": med(helpful, "u"),
        "helpful_f_median": med(helpful, "f"),
        "helpful_s_median": med(helpful, "s"),
        "all_u_median": med(pairs, "u"),
        "all_f_median": med(pairs, "f"),
        "all_r_median": med(pairs, "r"),
        "low_pairs": len(low),
        "low_helpful": sum(p["r"] < 1 for p in low),
        "high_pairs": len(high),
        "high_helpful": sum(p["r"] < 1 for p in high),
        "blind_frag_median": _real(_median(blind_frag)),
        "points": sorted([p["task"][0], p["task"][1], _real(p["s"]),
                          _real(p["u"]), _real(p["f"])] for p in pairs),
    }


def analyze(tasks, cells, pilot):
    solved, conflicts = outcomes(tasks, cells)
    result = {
        "schema": "symbolic-search-heuristics/cpddl-ghseta-{}/v1".format(
            "pilot" if pilot else "analysis"),
        "protocol_sha256": PROTOCOL_SHA256,
        "tasks": len(tasks),
        "cost_conflicts": conflicts,
        "coverage": {l: coverage(tasks, cells, solved, l) for l in LABELS},
        "exit_codes": {
            l: dict(sorted(
                __import__("collections").Counter(
                    str(cells[(l,) + t]["exit_code"]) for t in tasks).items()))
            for l in LABELS},
    }
    if pilot:
        profiled = [cells[(l,) + t] for l in ("cp_blind_fw_prof", "cp_pot_fw_prof")
                    for t in tasks if solved[(l, t)]]
        result["profiled_solved_with_layers"] = sum(
            1 for c in profiled
            if c.get("wbh_layers", 0) > 0 and isinstance(c.get("wbh_done"), dict))
        result["profiled_solved"] = len(profiled)
        return result
    tests, raw = {}, {}
    for name, label, reference in PRIMARY:
        g, l = discordance(tasks, solved, label, reference)
        raw[name] = Remedy.sign_test(g, l)
        tests[name] = {"config": label, "reference": reference, "gains": g,
                       "losses": l, "p": _real(raw[name], 8)}
    adjusted = Remedy.holm(raw)
    claims = {}
    for name, record in tests.items():
        significant = adjusted[name] <= ALPHA
        record["p_holm"] = _real(adjusted[name], 8)
        record["significant"] = significant
        claims[name] = ("better" if significant and record["gains"] > record["losses"]
                        else "worse" if significant else "not_significant")
    context = {}
    for label, reference in CONTEXT:
        g, l = discordance(tasks, solved, label, reference)
        context["{}_vs_{}".format(label, reference)] = {
            "gains": g, "losses": l,
            "p_unadjusted": _real(Remedy.sign_test(g, l), 8)}
    result.update({"primary_tests": tests, "claims": claims,
                   "context": context,
                   "decomposition": decomposition(tasks, cells, solved)})
    return result


def command_analyze(args):
    pilot = args.cohort == "dev"
    if not pilot:
        raw = PROTOCOL_PATH.read_bytes()
        if PROTOCOL_SHA256 == "TO_PIN" or hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
            raise AnalysisError("protocol is not frozen")
    tasks, cells = load_cells(ROOT / args.cohort)
    if pilot and len(tasks) != 275 or not pilot and len(tasks) != 1052:
        raise AnalysisError("unexpected cohort size")
    artifact = analyze(tasks, cells, pilot)
    raw = Common._canonical_json(artifact) + b"\n"
    out = ARTIFACT_DIR / ("pilot-v1.json" if pilot else "analysis-v1.json")
    if out.exists():
        raise AnalysisError("{} already exists".format(out))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    Path(str(out) + ".sha256").write_text("{}  {}\n".format(digest, out.name))
    print(digest)
    print(json.dumps(artifact.get("claims", artifact["coverage"]), sort_keys=True))
    return 0


def _self_test():
    tasks = [("d{}".format(i % 30), "p{}.pddl".format(i)) for i in range(200)]
    cells = {}
    for i, task in enumerate(tasks):
        for label in LABELS:
            heuristic = "pot" in label
            solved = i % 2 == 0 or (heuristic and i % 6 == 1)
            cell = {"solved": solved, "cost": 10 if solved else None,
                    "wall_seconds": 5.0, "exit_code": 0 if solved else -24}
            if label.endswith("_prof"):
                # Blind: E = U = 1000, 100 states.  Heuristic on even tasks:
                # helpful (E 500, U 250, 5 states); else harmful (E 3000,
                # U 1000, 90 states).
                if heuristic:
                    e, u, s = (500, 250, 5) if i % 4 == 0 else (3000, 1000, 90)
                else:
                    e, u, s = 1000, 1000, 100
                cell.update({"wbh_expand_nodes": e, "wbh_layer_nodes": u,
                             "wbh_expand_states": s, "wbh_layers": 3,
                             "wbh_done": {}})
            cells[(label,) + task] = cell
    result = analyze(tasks, cells, pilot=False)
    if result["claims"]["H-A"] != "better" or result["primary_tests"]["H-A"]["gains"] != sum(1 for i in range(200) if i % 6 == 1):
        raise AnalysisError("self-test: primary test")
    d = result["decomposition"]
    if not (d["pairs"] == 100 and d["harmful"] == 50 and d["helpful"] == 50
            and d["harmful_u_median"] == 1.0 and d["harmful_f_median"] == 3.0
            and d["helpful_u_median"] == 0.25 and d["helpful_f_median"] == 2.0
            and d["low_helpful"] == 50 and d["high_helpful"] == 0
            and d["share"] == 1.0 and d["blind_frag_median"] == 1.0):
        raise AnalysisError("self-test: decomposition {}".format(
            {k: v for k, v in d.items() if k != "points"}))
    cells[("cp_blind_bi",) + tasks[0]]["cost"] = 11
    if analyze(tasks, cells, pilot=False)["cost_conflicts"] != ["d0:p0.pddl"]:
        raise AnalysisError("self-test: cost conflict")
    print("self-test passed")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--cohort", choices=("dev", "holdout"), required=True)
    sub.add_parser("self-test")
    args = parser.parse_args(argv)
    if args.command == "self-test":
        return _self_test()
    return command_analyze(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, AnalysisError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
