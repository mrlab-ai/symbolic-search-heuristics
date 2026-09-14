#!/usr/bin/env python3
"""Retain launch/accounting evidence and enforce the user's hourly polling."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import subprocess

from pdb_within_family_source_worker import canonical, file_sha


def publish(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(canonical(value))


def capture_launch(experiment, output):
    grid = Path(str(experiment) + "-grid-steps")
    jobs = []
    for receipt_path in sorted(grid.glob("*.receipt.json")):
        receipt = json.loads(receipt_path.read_bytes())
        job_file = Path(receipt["job_file"])
        if file_sha(job_file) != receipt["job_sha256"]:
            raise ValueError("submitted job file changed")
        script = job_file.read_text()
        array = re.findall(r"^#SBATCH --array=1-([1-9][0-9]*)$", script, re.M)
        if len(array) != 1 or re.search(r"^#SBATCH --array=.*%", script, re.M):
            raise ValueError("array shape changed or throttle present")
        receipt["array_elements"] = int(array[0])
        receipt["script"] = script
        jobs.append(receipt)
    if not jobs or len({row["job_id"] for row in jobs}) != len(jobs):
        raise ValueError("missing or duplicate launch receipts")
    value = {"schema": "pdb-within-family-launch/v1", "experiment": str(experiment),
             "jobs": jobs, "poll_interval_seconds": 3600}
    publish(output, value)
    return value


def check_accounting(launch, stdout):
    rows = []
    for line in stdout.splitlines():
        fields = line.split("|")
        if len(fields) != 12:
            raise ValueError("scheduler accounting columns changed")
        rows.append(dict(zip(("id", "name", "state", "exit", "partition", "account",
                              "qos", "cpus", "memory", "time_limit", "nodes", "elapsed"), fields)))
    expected = {}
    for job in launch["jobs"]:
        for index in range(1, job["array_elements"] + 1):
            expected[f"{job['job_id']}_{index}"] = job
    normalized = {}
    for row in rows:
        identity = row["id"]
        if identity not in expected and identity + "_1" in expected:
            if expected[identity + "_1"]["array_elements"] == 1:
                identity += "_1"
        if identity not in expected or identity in normalized:
            raise ValueError("unexpected or duplicate accounting identity")
        normalized[identity] = row
    complete = len(normalized) == len(expected) and all(
        row["state"] == "COMPLETED" and row["exit"] == "0:0"
        for row in normalized.values())
    resources_ok = all(
        row["partition"] == "fat" and row["account"] == "naiss2025-5-561-cpu"
        and row["qos"] == "normal" and row["cpus"] == "9"
        and row["memory"] in {"3Gc", "3072Mc"}
        for row in normalized.values())
    for identity, row in normalized.items():
        job = expected[identity]
        time_limit = re.search(r"^#SBATCH --time=(.+)$", job["script"], re.M)
        name = re.search(r"^#SBATCH --job-name=(.+)$", job["script"], re.M)
        resources_ok = resources_ok and bool(time_limit and name) and (
            row["time_limit"] == time_limit.group(1) and row["name"] == name.group(1))
    return {"expected_elements": len(expected), "observed_elements": len(normalized),
            "all_completed_successfully": complete, "resources_match": resources_ok,
            "rows": normalized}


def poll(launch_path):
    launch = json.loads(launch_path.read_bytes())
    times = [datetime.fromisoformat(row["accepted_utc"]) for row in launch["jobs"]]
    for path in launch_path.parent.glob("poll-*.json"):
        times.append(datetime.fromisoformat(json.loads(path.read_bytes())["started_utc"]))
    now = datetime.now(timezone.utc)
    permitted = max(times) + timedelta(seconds=3600)
    if now < permitted:
        raise ValueError(f"hourly polling: next check no earlier than {permitted.isoformat()}")
    ids = ",".join(row["job_id"] for row in launch["jobs"])
    commands = {
        "queue": ["squeue", "--noheader", "--jobs", ids, "--format=%i|%T|%R"],
        "accounting": ["sacct", "--noheader", "--parsable2", "--allocations", "--jobs", ids,
                       "--format=JobID%80,JobName%128,State%40,ExitCode,Partition,Account,QOS,ReqCPUS,ReqMem,Timelimit,NodeList%200,ElapsedRaw"],
    }
    value = {"schema": "pdb-within-family-poll/v1", "started_utc": now.isoformat(),
             "launch_sha256": file_sha(launch_path), "queries": {}}
    for name, command in commands.items():
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=45)
            query = {"command": command, "returncode": result.returncode,
                     "stdout": result.stdout, "stderr": result.stderr}
        except subprocess.TimeoutExpired as error:
            query = {"command": command, "returncode": None,
                     "stdout": (error.stdout or b"").decode("utf-8", "replace"),
                     "stderr": "scheduler query timed out"}
        value["queries"][name] = query
    accounting = value["queries"]["accounting"]
    if accounting["returncode"] == 0:
        try:
            value["validation"] = check_accounting(launch, accounting["stdout"])
        except ValueError as error:
            value["validation_error"] = str(error)
    grid = Path(launch["experiment"] + "-grid-steps")
    value["pipeline_logs"] = {}
    for name in ("slurm.log", "slurm.err"):
        path = grid / name
        if path.exists():
            value["pipeline_logs"][name] = {"sha256": file_sha(path),
                                            "tail": path.read_bytes()[-12000:].decode("utf-8", "replace")}
    output = launch_path.parent / f"poll-{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    publish(output, value)
    print(json.dumps({"path": str(output), "validation": value.get("validation"),
                      "validation_error": value.get("validation_error")}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    capture = sub.add_parser("capture-launch")
    capture.add_argument("--experiment", type=Path, required=True)
    capture.add_argument("--output", type=Path, required=True)
    check = sub.add_parser("poll")
    check.add_argument("--launch", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "capture-launch":
        value = capture_launch(args.experiment.resolve(), args.output.resolve())
        print(json.dumps({"jobs": [r["job_id"] for r in value["jobs"]]}))
    else:
        poll(args.launch.resolve())


if __name__ == "__main__":
    main()
