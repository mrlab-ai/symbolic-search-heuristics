#!/usr/bin/env python3
"""Post-process width-bounded-heuristics sweep results (PR5).

The Q1/Q2 sweeps ran on a binary that ABORTed (exit 250, "unexplained error")
on tasks the heuristic search does not support -- zero-cost-operator tasks,
tasks whose translation uses axioms, and tasks whose initial state is a
heuristic dead-end (provably unsolvable). This script reclassifies those runs
from their run.err message into clean categories and reports coverage on the
fair positive-cost, normalized-axiom-free subset, so no search re-run is
needed. (Newer binaries exit SEARCH_UNSUPPORTED / SEARCH_UNSOLVABLE directly;
those are handled too.)

A task's cost class comes from the checked-in manifest: 1684 direct serialized
SAS scans plus 13 pinned-translator no-metric/unit-cost proofs for
resource-heavy task translations. Both establish the same SAS zero-cost
predicate. Exact PDDL
parsing followed by pinned default normalization separately attests axiom
support.  This avoids inferring task properties from a censored planner outcome. Legacy
run.err files are still used, when present, to describe *why* a run failed,
but they are not needed to define the 1377-task comparison subset.

Usage:
  python3 experiments/postprocess.py [exp_q1 exp_q2 exp_baselines ...]
Defaults to whichever of those evaluation directories or archives exist under
data/.
"""
import collections
import json
import sys
import tarfile
from pathlib import Path

import suite_cost_manifest

DATA = Path(__file__).resolve().parent / "data"

HEUR_CONFIGS = {"pot_m8", "pdb", "ms", "pot_m0", "pot_m1", "pot_m2", "pot_m4",
                "pot_m16", "pot_unbounded"}
DISPLAY_ALGORITHM = {
    "a_plus_i": "cpddl_i_i",
    "symba_star": "cpddl_blind_bi",
}


def load_properties(name):
    props_file = DATA / f"{name}-eval" / "properties"
    if props_file.exists():
        return json.loads(props_file.read_text())
    archive_path = DATA / f"{name}-eval.tar.gz"
    if not archive_path.exists():
        return None
    with tarfile.open(archive_path, "r:*") as archive:
        members = [
            member for member in archive.getmembers()
            if member.isfile() and Path(member.name).name == "properties"
        ]
        if len(members) != 1:
            raise RuntimeError(
                f"{archive_path} contains {len(members)} properties members")
        stream = archive.extractfile(members[0])
        if stream is None:
            raise RuntimeError(f"cannot read {members[0].name}")
        return json.load(stream)


def run_err(exp_dir, run_dir):
    f = exp_dir / run_dir / "run.err"
    try:
        return f.read_text()
    except OSError:
        return None


def classify(r, exp_dir):
    if r.get("coverage"):
        return "solved"
    err = str(r.get("error", "") or "")
    if err in ("exitcode-250", "") or "unexplained" in err:
        t = run_err(exp_dir, r.get("run_dir", ""))
        if t is None:
            return "censored-exit250-missing-log"
        if "requires positive operator" in t:
            return "search-unsupported"
        if "infinite heuristic" in t or "no finite heuristic" in t:
            return "unsolvable"
    if "unsupported" in err:
        return "search-unsupported"
    if "unsolvable" in err:
        return "unsolvable"
    if "out-of-time" in err:
        return "timeout"
    if "out-of-memory" in err:
        return "oom"
    return err or "other"


def process(name):
    exp_dir = DATA / name
    props = load_properties(name)
    if props is None:
        print(f"[{name}] no properties (not fetched yet)")
        return

    by_task = collections.defaultdict(dict)
    status = {}
    for key, r in props.items():
        task = (r.get("domain"), r.get("problem"))
        alg = r.get("algorithm")
        by_task[task][alg] = r
        status[(alg, task)] = classify(r, exp_dir)

    manifest_positive, manifest_zero = suite_cost_manifest.task_classes()
    manifest_supported = suite_cost_manifest.supported_tasks()
    universe = manifest_positive | manifest_zero
    unknown = set(by_task) - universe
    if unknown:
        raise RuntimeError(
            f"{name} contains {len(unknown)} tasks outside suite_wbh manifest: "
            f"{sorted(unknown)[:3]}")
    zero_cost = set(by_task) & manifest_zero
    positive_with_axioms = set(by_task) & (
        manifest_positive - manifest_supported)
    supported = sorted(set(by_task) & manifest_supported)

    algs = sorted({r.get("algorithm") for r in props.values()})
    subset_text = (
        f"{len(supported)} supported positive-cost/axiom-free, "
        f"{len(zero_cost)} zero-cost, "
        f"{len(positive_with_axioms)} positive-cost with normalized axioms")
    print(f"\n=== {name}: {len(by_task)} tasks ({subset_text}) ===")
    header = f"{'algorithm':16s} {'cov(all)':>9s} {'cov(supported)':>14s}"
    print(header)
    for alg in algs:
        cov_all = sum(
            1 for t in by_task if status.get((alg, t)) == "solved")
        cov_pos = sum(
            1 for t in supported if status.get((alg, t)) == "solved")
        display_alg = DISPLAY_ALGORITHM.get(alg, alg)
        print(f"{display_alg:16s} {cov_all:9d} {cov_pos:14d}")

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
                (DATA / f"{name}-eval.tar.gz").exists() or \
                name in sys.argv[1:]:
            process(name)


if __name__ == "__main__":
    main()
