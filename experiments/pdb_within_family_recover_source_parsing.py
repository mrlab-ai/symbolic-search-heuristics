#!/usr/bin/env python3
"""Recover static-context parsing without rerunning or altering translations."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from downward.reports.absolute import AbsoluteReport
from lab.parser import Parser
from lab.tools import Properties

import exp_pdb_within_family_source_pilot_v1 as Original
import pdb_within_family_cohort as C
from pdb_within_family_parse_context import initialize_static


def recover(launch_path, poll_path, output):
    launch = json.loads(launch_path.read_bytes())
    poll = json.loads(poll_path.read_bytes())
    if poll["launch_sha256"] != C.W.file_sha(launch_path):
        raise ValueError("source poll/launch identity changed")
    validation = C.require_translation_jobs_complete(launch, poll)
    if "KeyError: 'id'" not in poll["pipeline_logs"]["slurm.err"]["tail"]:
        raise ValueError("source failure is not the diagnosed static-context error")
    if Path(launch["experiment"]) != Original.OUTPUT:
        raise ValueError("unexpected source pilot to recover")
    manifest = Original.load_manifest()
    expected = {("translator", row["family"], Path(row["problem_file"]).name)
                for row in manifest["records"]}
    parser = Parser()
    parser.add_function(initialize_static, file="run.log")
    parser.add_function(Original.parse_result, file="source-result.json")
    properties = {}
    raw_hashes = {}
    for directory in sorted(Original.OUTPUT.glob("runs-*/*")):
        if not directory.is_dir():
            continue
        raw_path = directory / "source-result.json"
        raw_hashes[str(raw_path)] = C.W.file_sha(raw_path)
        props = Properties()
        parser.parse(directory, props)
        identity = tuple(props["id"])
        if identity not in expected or "-".join(identity) in properties or props.get("error") != "none":
            raise ValueError("recovered source matrix has an unknown, duplicated or failed cell")
        properties["-".join(identity)] = dict(props)
    if {tuple(props["id"]) for props in properties.values()} != expected:
        raise ValueError("recovered source matrix is incomplete")
    output.mkdir(parents=True, exist_ok=False)
    C.Monitor.publish(output / "properties", properties)
    AbsoluteReport(attributes=["error", "coverage", "source_status", "source_cpu_seconds",
                               "source_wall_seconds"])(str(output), str(output / "source.html"))
    counts = defaultdict(Counter)
    records = []
    for props in properties.values():
        counts[props["domain"]][props["source_status"]] += 1
        records.append(props["source_result"])
    for name, expected_sha in raw_hashes.items():
        if C.W.file_sha(name) != expected_sha:
            raise ValueError("raw translation payload changed during recovery")
    recovery = {"schema": C.W.SCHEMA + "/static-context-recovery/v1",
                "source_launch_sha256": C.W.file_sha(launch_path),
                "source_poll_sha256": C.W.file_sha(poll_path),
                "raw_translation_payloads_unchanged": True,
                "original_pipeline_completed_successfully": validation["all_completed_successfully"],
                "code_sha256": {name: C.W.file_sha(C.G.ROOT / name) for name in (
                    "pdb_within_family_recover_source_parsing.py", "pdb_within_family_parse_context.py",
                    "exp_pdb_within_family_source_pilot_v1.py")}}
    summary = {"schema": C.W.SCHEMA + "/pilot-summary", "performance_observed": False,
               "generator_manifest_sha256": C.W.file_sha(Original.INPUT / "manifest.json"),
               "properties_sha256": C.W.file_sha(output / "properties"),
               "family_status_counts": counts,
               "fully_supported_families": sorted(f for f, c in counts.items() if c == {"supported": 3}),
               "records": sorted(records, key=lambda record: record["id"]), "parsing_recovery": recovery}
    summary_path = output / "source-summary.json"
    C.Monitor.publish(summary_path, summary)
    C.load_completed_source(summary_path, launch_path, poll_path, Original.INPUT / "manifest.json")
    print(json.dumps({"supported_families": summary["fully_supported_families"],
                      "family_status_counts": counts, "summary": str(summary_path)}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", type=Path, required=True)
    parser.add_argument("--poll", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    recover(args.launch.resolve(), args.poll.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
