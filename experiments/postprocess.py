#!/usr/bin/env python3
"""Post-process width-bounded-heuristics sweep results (PR5).

The Q1/Q2 sweeps ran on a binary that ABORTed (exit 250, "unexplained error")
on tasks the heuristic search does not support -- zero-cost-operator tasks
(positive-cost assumption) and tasks whose initial state is a heuristic
dead-end (provably unsolvable). This script reclassifies those runs from their
run.err message into clean categories and reports coverage on the fair
POSITIVE-COST subset, so no search re-run is needed. (Newer binaries exit
SEARCH_UNSUPPORTED / SEARCH_UNSOLVABLE directly; those are handled too.)

A task is "zero-cost" iff a heuristic config reported the positive-cost
condition on it; such tasks are excluded from the heuristic-vs-blind
comparison (a strict subset of the Fiser et al. suite -- see suite_wbh.py).

Usage:
  python3 experiments/postprocess.py [exp_q1 exp_q2 exp_baselines ...]
Defaults to whichever of those eval dirs exist under data/.
"""
import collections
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"

HEUR_CONFIGS = {"pot_m8", "pdb", "ms", "pot_m0", "pot_m1", "pot_m2", "pot_m4",
                "pot_m16", "pot_unbounded"}


def run_err(exp_dir, run_dir):
    f = exp_dir / run_dir / "run.err"
    try:
        return f.read_text()
    except OSError:
        return ""


def classify(r, exp_dir):
    if r.get("coverage"):
        return "solved"
    err = str(r.get("error", "") or "")
    if err in ("exitcode-250", "") or "unexplained" in err:
        t = run_err(exp_dir, r.get("run_dir", ""))
        if "requires positive operator" in t:
            return "unsupported-zerocost"
        if "infinite heuristic" in t or "no finite heuristic" in t:
            return "unsolvable"
    if "unsupported" in err:
        return "unsupported-zerocost"
    if "unsolvable" in err:
        return "unsolvable"
    if "out-of-time" in err:
        return "timeout"
    if "out-of-memory" in err:
        return "oom"
    return err or "other"


def process(name):
    eval_dir = DATA / f"{name}-eval"
    exp_dir = DATA / name
    props_file = eval_dir / "properties"
    if not props_file.exists():
        print(f"[{name}] no properties (not fetched yet)")
        return
    props = json.loads(props_file.read_text())

    by_task = collections.defaultdict(dict)
    status = {}
    for key, r in props.items():
        task = (r.get("domain"), r.get("problem"))
        alg = r.get("algorithm")
        by_task[task][alg] = r
        status[(alg, task)] = classify(r, exp_dir)

    # A task is zero-cost iff a heuristic config flagged the positive-cost
    # condition there.
    zero_cost = set()
    for task, algs in by_task.items():
        for alg in algs:
            if alg in HEUR_CONFIGS and \
                    status[(alg, task)] == "unsupported-zerocost":
                zero_cost.add(task)
                break
    positive = [t for t in by_task if t not in zero_cost]

    algs = sorted({r.get("algorithm") for r in props.values()})
    print(f"\n=== {name}: {len(by_task)} tasks "
          f"({len(positive)} positive-cost, {len(zero_cost)} zero-cost) ===")
    header = f"{'algorithm':16s} {'cov(all)':>9s} {'cov(pos-cost)':>14s}"
    print(header)
    for alg in algs:
        cov_all = sum(
            1 for t in by_task if status.get((alg, t)) == "solved")
        cov_pos = sum(
            1 for t in positive if status.get((alg, t)) == "solved")
        print(f"{alg:16s} {cov_all:9d} {cov_pos:14d}")

    # Error breakdown for the heuristic configs.
    errs = collections.Counter(
        status[(alg, t)] for alg in algs if alg in HEUR_CONFIGS
        for t in by_task)
    if errs:
        print("  heuristic-config outcomes:",
              dict(errs.most_common()))


def main():
    names = sys.argv[1:] or ["exp_q1", "exp_q2", "exp_baselines"]
    for name in names:
        if (DATA / f"{name}-eval" / "properties").exists() or \
                name in sys.argv[1:]:
            process(name)


if __name__ == "__main__":
    main()
