#!/usr/bin/env python3
"""Combined fair coverage across all width-bounded-heuristics sweeps.

Loads the checked-in, translator-attested cost/support manifest, then reports
each configuration's coverage over its 1377-task positive-cost, normalized-
axiom-free subset and writes a per-domain coverage CSV to
results/coverage_per_domain.csv.  The manifest is hash- and schema-validated,
so archived evaluation tarballs are sufficient; legacy exit-250 logs are not
used to infer task properties.

Usage: python3 experiments/combined_coverage.py
"""
import collections
import csv
import json
import sys
import tarfile
from pathlib import Path

import suite_cost_manifest

DATA = Path(__file__).resolve().parent / "data"
RESULTS = Path(__file__).resolve().parent.parent / "results"
EXPS = [
    "exp_q1", "exp_q2", "exp_baselines", "exp_ms", "exp_blind_bd",
    "exp_prune", "exp_bd_prune", "exp_bd_prune2",
]
# Report order; dedup keeps the first experiment that has each algorithm.
ALGS = ["blind_fw", "blind_bd", "pot_m8", "pot_m16", "pdb", "ms",
        "pot_m8_prune", "pdb_prune", "ms_prune",
        "bd_ms10k", "bd_ms100k", "bd_ms10k_b60",
        "cpddl_i_i", "cpddl_blind_bi", "scorpion"]
LEGACY_ALGORITHM_NAMES = {
    # Preserve archived identifiers in the source data, but use labels that
    # describe the commands actually executed.
    "a_plus_i": "cpddl_i_i",
    "symba_star": "cpddl_blind_bi",
}
# exp_blind_bd first so blind_bd comes from its dedicated sweep (repeated
# sym_bd runs differ by a task or two through timing-based direction selection).
EXP_ORDER = [
    "exp_q2", "exp_q1", "exp_ms", "exp_prune", "exp_blind_bd",
    "exp_bd_prune", "exp_bd_prune2", "exp_baselines",
]


def load(name):
    f = DATA / f"{name}-eval" / "properties"
    if f.exists():
        return json.loads(f.read_text())
    archive_path = DATA / f"{name}-eval.tar.gz"
    if not archive_path.exists():
        return {}
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


def validate_complete_algorithms(seen, supported):
    missing_algorithms = [
        algorithm for algorithm in ALGS if not seen.get(algorithm)]
    if missing_algorithms:
        raise RuntimeError(
            "expected algorithms are entirely absent: {}".format(
                ", ".join(missing_algorithms)))
    for algorithm in ALGS:
        observed = seen[algorithm]
        if observed != supported:
            missing = len(supported - observed)
            extra = len(observed - supported)
            raise RuntimeError(
                f"{algorithm} does not cover the complete manifest subset: "
                f"{missing} missing, {extra} extra tasks")


def self_test():
    positive = {("d", "p1"), ("d", "p2")}
    complete = {algorithm: set(positive) for algorithm in ALGS}
    validate_complete_algorithms(complete, positive)

    absent = dict(complete)
    del absent[ALGS[-1]]
    try:
        validate_complete_algorithms(absent, positive)
    except RuntimeError as err:
        assert "entirely absent" in str(err)
    else:
        raise AssertionError("entirely absent algorithm was accepted")

    partial = {algorithm: set(tasks) for algorithm, tasks in complete.items()}
    partial[ALGS[0]].pop()
    try:
        validate_complete_algorithms(partial, positive)
    except RuntimeError as err:
        assert "1 missing" in str(err)
    else:
        raise AssertionError("partial algorithm matrix was accepted")
    print("combined-coverage synthetic completeness tests: PASS")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv == ["--self-test"]:
        self_test()
        return
    if argv:
        raise RuntimeError("usage: combined_coverage.py [--self-test]")
    allp = {e: load(e) for e in EXPS}
    positive, zero = suite_cost_manifest.task_classes()
    supported = suite_cost_manifest.supported_tasks()
    positive_with_axioms = positive - supported
    universe = positive | zero
    for e, props in allp.items():
        for r in props.values():
            task = (r.get("domain"), r.get("problem"))
            if task not in universe:
                raise RuntimeError(
                    f"{e} contains task {task!r} outside suite_wbh manifest")

    cov = collections.defaultdict(lambda: [0, 0])
    per_domain = collections.defaultdict(lambda: collections.defaultdict(int))
    dom_tasks = collections.Counter()
    seen = collections.defaultdict(set)
    for e in EXP_ORDER:
        for r in allp.get(e, {}).values():
            a = LEGACY_ALGORITHM_NAMES.get(
                r.get("algorithm"), r.get("algorithm"))
            task = (r.get("domain"), r.get("problem"))
            if a not in ALGS or task not in supported or task in seen[a]:
                continue
            seen[a].add(task)
            c = r.get("coverage", 0) or 0
            cov[a][0] += c
            cov[a][1] += 1
            per_domain[r.get("domain")][a] += c
    validate_complete_algorithms(seen, supported)
    for task in supported:
        dom_tasks[task[0]] += 1

    total = len(supported)
    print(f"supported positive-cost, normalized-axiom-free subset: "
          f"{total} tasks (zero-cost excluded: {len(zero)}; "
          f"positive-cost with normalized axioms excluded: "
          f"{len(positive_with_axioms)})")
    for a in ALGS:
        print(f"  {a:14s} {cov[a][0]:5d} / {cov[a][1]}")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / "coverage_per_domain.csv"
    with open(out, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["domain", "tasks"] + ALGS)
        for d in sorted(dom_tasks):
            w.writerow([d, dom_tasks.get(d, 0)]
                       + [per_domain[d].get(a, 0) for a in ALGS])
        w.writerow(["TOTAL", total]
                   + [cov[a][0] for a in ALGS])
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
