#!/usr/bin/env python3
"""Bind completed fresh-instance A evidence without making scheduler queries."""

import argparse
import json
from pathlib import Path

import pdb_within_family_a_analysis as A
import pdb_within_family_cohort as C


SCHEMA = "pdb-terminal-incidence-within-family-a-seal/v1"
OUTPUT = A.OUTPUT / "completion-seal.json"


def validate_completed(launch_path, poll_path, analysis_directory=A.OUTPUT):
    freeze = C.load_freeze()
    freeze_sha = C.W.file_sha(C.FREEZE)
    launch = json.loads(launch_path.read_bytes())
    poll = json.loads(poll_path.read_bytes())
    if (Path(launch["experiment"]).resolve() != A.Runner.OUTPUT.resolve()
            or poll["launch_sha256"] != C.W.file_sha(launch_path)):
        raise ValueError("A launch/poll identity changed")
    expected_steps = {"01-build": 1, "02-start": (4 * C.TARGETS["a"] + 2) // 3,
                      "03-parse": 1, "04-fetch": 1, "05-report": 1, "06-analyze": 1}
    steps = {}
    for job in launch["jobs"]:
        matches = [step for step in expected_steps if Path(job["job_file"]).name.endswith("-" + step)]
        if len(matches) != 1 or matches[0] in steps:
            raise ValueError("A pipeline has an unknown or duplicate step")
        steps[matches[0]] = job["array_elements"]
    if steps != expected_steps:
        raise ValueError("A pipeline shape differs from the frozen task matrix")
    accounting = poll["queries"]["accounting"]
    if accounting["returncode"] != 0:
        raise ValueError("A accounting query did not succeed")
    validation = C.Monitor.check_accounting(launch, accounting["stdout"])
    if not validation["all_completed_successfully"] or not validation["resources_match"]:
        raise ValueError("A pipeline is not successfully complete")
    analysis_path = analysis_directory / "analysis.json"
    repeat_path = analysis_directory / "analysis-repeat.json"
    receipt_path = analysis_directory / "analysis-receipt.json"
    raw = analysis_path.read_bytes()
    if raw != repeat_path.read_bytes():
        raise ValueError("repeated A analyses differ")
    result = json.loads(raw)
    receipt = json.loads(receipt_path.read_bytes())
    expected_receipt = {"schema": A.SCHEMA + "/double-execution", "byte_identical": True,
                        "analysis_sha256": C.G.sha(raw), "repeat_sha256": C.G.sha(raw),
                        "properties_sha256": result["input"]["properties_sha256"],
                        "freeze_sha256": freeze_sha,
                        "scheduler_audit_required_before_selector_launch": True}
    if receipt != expected_receipt:
        raise ValueError("A double-execution receipt changed")
    properties = Path(str(A.Runner.OUTPUT) + "-eval/properties")
    expected_input = {"properties_path": str(properties), "properties_sha256": C.W.file_sha(properties),
                      "code_commit": freeze["code_commit"], "code_sha256": freeze["code_sha256"]}
    if (result["schema"] != A.SCHEMA or result["freeze_sha256"] != freeze_sha
            or result["scope"] != freeze["scope"] or result["input"] != expected_input
            or result["matrix"]["tasks"] != C.TARGETS["a"]
            or result["matrix"]["cells"] != 4 * C.TARGETS["a"]
            or result["matrix"]["configs"] != 4
            or result["matrix"]["families"] != len(freeze["families"])):
        raise ValueError("A analysis identity or complete matrix changed")
    records = list(json.loads(properties.read_bytes()).values())
    A.verify_run_evidence(records, freeze, A.Runner.OUTPUT)
    with A.configured(freeze):
        A.validate_matrix(records, freeze, freeze_sha)
    passed = result["gates"]["pass"]
    if (type(passed) is not bool or passed != result["gates"]["primary"]["pass"]
            or passed != result["statistical_selector_gate_passed"]
            or result["gates"]["decision"] != ("PASS" if passed else "FAIL")
            or result["gates"]["unseen_family_gate"] is not False):
        raise ValueError("A decision fields disagree")
    paths = {"freeze": C.FREEZE, "launch": launch_path, "poll": poll_path,
             "analysis": analysis_path, "repeat": repeat_path, "receipt": receipt_path,
             "properties": properties}
    seal = {"schema": SCHEMA, "scope": freeze["scope"], "decision": result["gates"]["decision"],
            "selector_experiments_authorized": passed, "scheduler_queries_made_by_seal": 0,
            "matrix": result["matrix"], "code_commit": freeze["code_commit"],
            "evidence": {key: {"path": str(path), "sha256": C.W.file_sha(path)}
                         for key, path in paths.items()}}
    return seal, result


def load_seal(path=OUTPUT):
    retained = json.loads(path.read_bytes())
    for record in retained["evidence"].values():
        if C.W.file_sha(record["path"]) != record["sha256"]:
            raise ValueError("completed A evidence changed")
    evidence = retained["evidence"]
    fresh, result = validate_completed(Path(evidence["launch"]["path"]), Path(evidence["poll"]["path"]),
                                       Path(evidence["analysis"]["path"]).parent)
    if retained != fresh:
        raise ValueError("completed A seal cannot be reproduced")
    return retained, result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", type=Path, required=True)
    parser.add_argument("--poll", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    value, _ = validate_completed(args.launch.resolve(), args.poll.resolve())
    C.Monitor.publish(args.output.resolve(), value)
    print(json.dumps({"decision": value["decision"], "matrix": value["matrix"],
                      "selector_experiments_authorized": value["selector_experiments_authorized"]}, sort_keys=True))


if __name__ == "__main__":
    main()
