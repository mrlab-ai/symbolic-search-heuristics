#!/usr/bin/env python3
"""Lab pipeline for the 90-instance, translation-only fresh-source pilot."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import importlib.metadata
import json
import os
from pathlib import Path
import sys

from downward.reports.absolute import AbsoluteReport
from lab.environments import ArrheniusEnvironment
from lab.experiment import Experiment
from lab.parser import Parser

import jj_cached_revision as JJ
import pdb_within_family_instances as G
import pdb_within_family_source_worker as W


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "data/pdb-within-family-generator-pilot-v2"
OUTPUT = ROOT / "data/exp_pdb_within_family_source_pilot_v1"
REVISION = "8148f798f13059ee881ad2471bd20cdd61d2ec18"
CACHE = ROOT / "data/revision-cache/8148f798f13059ee_e261f35e36be"
WORKERS = ("pdb_within_family_source_worker.py",
           "pdb_terminal_incidence_confirmation_translate_v12.py")


def load_manifest():
    value = json.loads((INPUT / "manifest.json").read_bytes())
    rows = value["records"]
    if (value["schema"] != G.SCHEMA or value["role"] != "pilot"
            or value["performance_observed"] is not False or len(rows) != 90
            or value["records_sha256"] != G.sha(G.canonical(rows))
            or value["kit"]["revision"] != G.KIT_REVISION):
        raise ValueError("generator pilot manifest changed")
    expected = {(family, index) for family in G.FAMILIES for index in range(3)}
    if {(r["family"], r["index"]) for r in rows} != expected:
        raise ValueError("incomplete or duplicate generator pilot")
    for row in rows:
        if row["status"] != "generated" or row["role"] != "pilot":
            raise ValueError("pilot generation was not complete")
        for kind in ("domain", "problem"):
            if W.file_sha(INPUT / row[f"{kind}_file"]) != row[f"{kind}_sha256"]:
                raise ValueError("generator pilot input changed")
    return value


def parse_result(content, props):
    result = json.loads(content)
    if (result["schema"] != W.SCHEMA or result["id"] != props["id"]
            or result["config_sha256"] != props["source_config_sha256"]
            or result["domain_sha256"] != props["domain_sha256"]
            or result["problem_sha256"] != props["problem_sha256"]
            or result["performance_observed"] is not False):
        raise ValueError("source result identity changed")
    props["source_result"] = result
    props["source_status"] = result["status"]
    props["coverage"] = int(result["status"] == "supported")
    props["error"] = ("none" if result["status"] in {
        "supported", "unsupported", "memory-excluded", "time-excluded", "wall-excluded"
    } else result["status"])
    props["source_cpu_seconds"] = result["cpu_seconds"]
    props["source_wall_seconds"] = result["wall_seconds"]


def summarize(manifest):
    path = Path(str(OUTPUT) + "-eval")
    properties = json.loads((path / "properties").read_bytes())
    expected = {("translator", r["family"], Path(r["problem_file"]).name)
                for r in manifest["records"]}
    actual = [tuple(p["id"]) for p in properties.values()]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError("source pilot has missing, extra, or duplicate results")
    families = defaultdict(Counter)
    records = []
    for props in properties.values():
        if props.get("error") != "none" or props.get("unexplained_errors"):
            raise ValueError(f"unreviewed source error: {props['id']}")
        result = props["source_result"]
        if result["status"] in {"supported", "unsupported"}:
            reasons = W.support_reasons(result["sas"], result["normalization"]["num_normalized_axioms"])
            if reasons != result["support_reasons"] or bool(reasons) != (result["status"] == "unsupported"):
                raise ValueError("source support predicate disagrees")
        families[props["domain"]][props["source_status"]] += 1
        records.append(result)
    result = {"schema": W.SCHEMA + "/pilot-summary", "performance_observed": False,
              "generator_manifest_sha256": W.file_sha(INPUT / "manifest.json"),
              "properties_sha256": W.file_sha(path / "properties"),
              "family_status_counts": families,
              "fully_supported_families": sorted(f for f, c in families.items()
                                                  if c == {"supported": 3}),
              "records": sorted(records, key=lambda r: r["id"])}
    destination = path / "source-summary.json"
    with destination.open("xb") as stream:
        stream.write(G.canonical(result))


class RecordedEnvironment(ArrheniusEnvironment):
    def _submit_job(self, job_file, dependency=None):
        job = super()._submit_job(job_file, dependency=dependency)
        receipt = {"job_id": job, "dependency": dependency,
                   "accepted_utc": datetime.now(timezone.utc).isoformat(),
                   "job_file": str(job_file), "job_sha256": W.file_sha(job_file),
                   "first_poll_after_seconds": 3600}
        with Path(str(job_file) + ".receipt.json").open("xb") as stream:
            stream.write(G.canonical(receipt))
        return job


def make_experiment():
    manifest = load_manifest()
    for line in (ROOT / "requirements-pdb-terminal-incidence-shadow.txt").read_text().splitlines():
        name, version = line.split("==")
        if importlib.metadata.version(name) != version:
            raise ValueError(f"Python dependency changed: {name}")
    cached = JJ.JjCachedFastDownwardRevision(CACHE.parent, ROOT.parent, REVISION, ["release_no_lp"])
    attestation = cached.attest()
    source_manifest = {
        p.relative_to(CACHE / "src/translate").as_posix(): W.file_sha(p)
        for p in sorted((CACHE / "src/translate").rglob("*.py"))}
    worker_manifest = {name: W.file_sha(ROOT / name) for name in WORKERS}
    environment = RecordedEnvironment(
        partition="fat", qos="normal", cpus_per_task=9, memory_per_cpu="3G",
        time_limit_per_task="00:35:00", randomize_task_order=False,
        extra_options="#SBATCH --account=naiss2025-5-561-cpu\n#SBATCH --no-requeue",
        export=["PATH", "PYTHONNOUSERSITE=1", "PYTHONDONTWRITEBYTECODE=1", "PYTHONHASHSEED=0"],
        setup="unset PYTHONPATH PYTHONHOME VIRTUAL_ENV\nexport LC_ALL=C LANG=C",
    )
    exp = Experiment(path=OUTPUT, environment=environment)
    exp.add_resource("translator", CACHE / "src/translate", "translator/translate")
    exp.add_resource("worker", ROOT / WORKERS[0])
    exp.add_resource("", ROOT / WORKERS[1])
    exp.add_new_file("generator_manifest", "generator-manifest.json",
                     G.canonical(manifest).decode("ascii"))
    exp.set_property("planner_attestation", attestation)
    exp.set_property("source_revision", JJ.current_commit(ROOT.parent))
    exp.set_property("script_sha256", W.file_sha(__file__))
    for row in manifest["records"]:
        run = exp.add_run()
        identity = ["translator", row["family"], Path(row["problem_file"]).name]
        config = {"id": identity, "planner_revision": REVISION,
                  "translator_sha256": source_manifest, "worker_sha256": worker_manifest,
                  "python_sha256": W.file_sha(sys.executable),
                  "domain_sha256": row["domain_sha256"], "problem_sha256": row["problem_sha256"]}
        for key, value in {"id": identity, "algorithm": "translator", "domain": row["family"],
                           "problem": identity[2], "source_config_sha256": G.sha(G.canonical(config)),
                           "domain_sha256": row["domain_sha256"],
                           "problem_sha256": row["problem_sha256"], "generator": row}.items():
            run.set_property(key, value)
        for kind in ("domain", "problem"):
            run.add_resource(kind, INPUT / row[f"{kind}_file"], f"{kind}.pddl")
        run.add_new_file("config", "source-config.json", G.canonical(config).decode("ascii"))
        run.add_command("support", [sys.executable, "-B", "{worker}", "--translator", "{translator}",
                                    "--config", "{config}"],
                        time_limit=1900, wall_time_limit=2000, memory_limit=26000)
    parser = Parser()
    parser.add_function(parse_result, file="source-result.json")
    exp.add_parser(parser)
    exp.add_step("build", exp.build)
    exp.add_step("start", exp.start_runs)
    exp.add_step("parse", exp.parse)
    exp.add_fetcher(name="fetch")
    exp.add_report(AbsoluteReport(attributes=["error", "coverage", "source_status",
                                             "source_cpu_seconds", "source_wall_seconds"]),
                   name="report", outfile="source.html")
    exp.add_step("summarize", summarize, manifest)
    return exp


if __name__ == "__main__":
    if not os.environ.get("SLURM_JOB_ID") and any(arg in {"--all", "build", "start", "1", "2"} for arg in sys.argv[1:]):
        for path in (OUTPUT, Path(str(OUTPUT) + "-eval"), Path(str(OUTPUT) + "-grid-steps")):
            if path.exists():
                raise SystemExit(f"refusing to overwrite existing campaign: {path}")
    make_experiment().run_steps()
