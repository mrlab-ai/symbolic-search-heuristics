#!/usr/bin/env python3
"""Translation-only Lab census of the finite fresh A/B candidate pool."""

from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import sys

import exp_pdb_within_family_source_pilot_v1 as Base
import pdb_within_family_cohort as C


INPUT = Base.ROOT / "data/pdb-within-family-candidate-pool-v1"
OUTPUT = Base.ROOT / "data/exp_pdb_within_family_source_full_v1"


def load_manifest():
    value = json.loads((INPUT / "manifest.json").read_bytes())
    rows = value["records"]
    if (value["schema"] != C.SCHEMA or value["role"] != "candidate-pool"
            or value["performance_observed"] is not False
            or value["records_sha256"] != C.G.sha(C.G.canonical(rows))
            or value["allocations"] != C.allocations(value["families"])):
        raise ValueError("fresh candidate pool changed")
    actual = [{key: row[key] for key in ("role", "family", "level", "index", "reserve")}
              for row in rows]
    if actual != C.candidate_specs(value["families"]):
        raise ValueError("candidate pool is incomplete or reordered")
    for field in ("problem_sha256", "instance_fingerprint", "seed"):
        if len({row[field] for row in rows}) != len(rows):
            raise ValueError(f"candidate pool contains duplicate {field}")
    for row in rows:
        if row["status"] != "generated":
            raise ValueError("candidate generation was incomplete")
        for kind in ("domain", "problem"):
            if C.W.file_sha(INPUT / row[f"{kind}_file"]) != row[f"{kind}_sha256"]:
                raise ValueError("candidate input changed")
    return value


def summarize(manifest):
    path = Path(str(OUTPUT) + "-eval")
    properties = json.loads((path / "properties").read_bytes())
    expected = {("translator", row["family"], Path(row["problem_file"]).name)
                for row in manifest["records"]}
    actual = [tuple(props["id"]) for props in properties.values()]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("source census has missing, extra or duplicate cells")
    counts = defaultdict(Counter)
    records = []
    for props in properties.values():
        if props.get("error") != "none" or props.get("unexplained_errors"):
            raise ValueError(f"unresolved source error: {props['id']}")
        result = props["source_result"]
        Base.parse_result(C.G.canonical(result).decode("ascii"), dict(props))
        counts[props["domain"]][result["status"]] += 1
        records.append(result)
    C.Monitor.publish(path / "source-summary.json", {
        "schema": C.W.SCHEMA + "/candidate-source-summary", "performance_observed": False,
        "generator_manifest_sha256": C.W.file_sha(INPUT / "manifest.json"),
        "properties_sha256": C.W.file_sha(path / "properties"),
        "family_status_counts": counts,
        "records": sorted(records, key=lambda row: row["id"]),
    })


def make_experiment():
    # Reuse the immutable pilot's worker and Lab construction, with a distinct
    # source census and explicitly different manifest/report functions.
    Base.INPUT = INPUT
    Base.OUTPUT = OUTPUT
    Base.load_manifest = load_manifest
    Base.summarize = summarize
    exp = Base.make_experiment()
    # Above 1,000 runs Lab executes two runs sequentially per array element.
    exp.environment.time_limit_per_task = "01:10:00"
    exp.set_property("full_census_runner_sha256", C.W.file_sha(__file__))
    return exp


if __name__ == "__main__":
    if "--help" in sys.argv[1:] or "-h" in sys.argv[1:]:
        print(__doc__ + "\nSteps: build start parse fetch report summarize; --all runs the pipeline.")
        raise SystemExit(0)
    if not os.environ.get("SLURM_JOB_ID") and any(arg in {"--all", "build", "start", "1", "2"} for arg in sys.argv[1:]):
        for path in (OUTPUT, Path(str(OUTPUT) + "-eval"), Path(str(OUTPUT) + "-grid-steps")):
            if path.exists():
                raise SystemExit(f"refusing to overwrite existing campaign: {path}")
    make_experiment().run_steps()
