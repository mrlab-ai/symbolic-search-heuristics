#!/usr/bin/env python3
"""Recover A's completed analysis from the finite integer serialization limit."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import exp_pdb_within_family_a_v1 as Runner
import jj_cached_revision as JJ
import pdb_within_family_a_analysis as A
import pdb_within_family_cohort as C


SCHEMA = "pdb-terminal-incidence-within-family-a-serialization-recovery/v1"
INVOCATION_SCHEMA = SCHEMA + "/invocation"
SEAL_SCHEMA = "pdb-terminal-incidence-within-family-a-seal/v2-serialization-recovery"
INT_MAX_STR_DIGITS = 100000
TIMEOUT_SECONDS = 900

LAUNCH = A.OUTPUT / "launch.json"
POLL = A.OUTPUT / "poll-20260914T211529Z.json"
PROPERTIES = Path(str(Runner.OUTPUT) + "-eval/properties")
PYTHON = C.G.ROOT / "data/pdb-terminal-incidence-shadow-venv/bin/python"
ANALYSIS = C.G.ROOT / "pdb_within_family_a_analysis.py"
WRAPPER = Path(__file__).resolve()

RECOVERY = A.OUTPUT / "serialization-recovery.json"
INVOCATION = A.OUTPUT / "serialization-recovery-invocation.json"
STDOUT = A.OUTPUT / "serialization-recovery.stdout"
STDERR = A.OUTPUT / "serialization-recovery.stderr"
SEAL = A.OUTPUT / "completion-seal.json"

EXPECTED_LAUNCH_SHA256 = "47922017ce4ca0b86233005723da29e433826a2360879b300e3194a7876ac881"
EXPECTED_POLL_SHA256 = "c48ed72a2b6cf93ffce93e324e965f67b5cc74c9a6010b5b3001f662ff96532e"
EXPECTED_FREEZE_SHA256 = "0c95dd5afe61ea0f77c7441a824bcecbe255641994874d28734274a64e3a0c67"
EXPECTED_PROPERTIES_SHA256 = "664b2aabb78fd299646dfbe006e595c1baf3ebec6fbc338220f678639389ec99"
EXPECTED_PYTHON_SHA256 = "021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
EXPECTED_JOB_IDS = {
    "01-build": "2418263",
    "02-start": "2418264",
    "03-parse": "2418265",
    "04-fetch": "2418266",
    "05-report": "2418267",
    "06-analyze": "2418268",
}
SERIALIZATION_ERROR = (
    "ValueError: Exceeds the limit (4300 digits) for integer string conversion; "
    "use sys.set_int_max_str_digits() to increase the limit"
)

ENVIRONMENT = {
    "unset": ["PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"],
    "set": {
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
    },
}


def _sha_record(path):
    path = Path(path).resolve()
    return {"path": str(path), "sha256": C.W.file_sha(path)}


def _write_exclusive(path, raw):
    with Path(path).open("xb") as stream:
        stream.write(raw)


def configure_integer_serialization():
    sys.set_int_max_str_digits(INT_MAX_STR_DIGITS)
    if sys.get_int_max_str_digits() != INT_MAX_STR_DIGITS:
        raise ValueError("finite integer string conversion limit was not installed")


def _step_jobs(launch):
    expected_elements = {
        "01-build": 1,
        "02-start": (4 * C.TARGETS["a"] + 2) // 3,
        "03-parse": 1,
        "04-fetch": 1,
        "05-report": 1,
        "06-analyze": 1,
    }
    steps = {}
    for job in launch.get("jobs", []):
        matches = [step for step in expected_elements
                   if Path(job.get("job_file", "")).name.endswith("-" + step)]
        if len(matches) != 1 or matches[0] in steps:
            raise ValueError("A pipeline has an unknown or duplicate step")
        step = matches[0]
        expected_file = Path(str(Runner.OUTPUT) + "-grid-steps") / (
            Runner.OUTPUT.name + "-" + step)
        if (job.get("job_id") != EXPECTED_JOB_IDS[step]
                or job.get("array_elements") != expected_elements[step]
                or Path(job["job_file"]).resolve() != expected_file.resolve()
                or C.W.file_sha(expected_file) != job.get("job_sha256")
                or expected_file.read_text() != job.get("script")):
            raise ValueError("A launch job identity changed")
        steps[step] = job
    if set(steps) != set(expected_elements):
        raise ValueError("A pipeline does not have the exact six-step shape")
    return steps


def _expected_query_commands(steps):
    ids = ",".join(steps[step]["job_id"] for step in EXPECTED_JOB_IDS)
    return {
        "queue": ["squeue", "--noheader", "--jobs", ids, "--format=%i|%T|%R"],
        "accounting": [
            "sacct", "--noheader", "--parsable2", "--allocations", "--jobs", ids,
            "--format=JobID%80,JobName%128,State%40,ExitCode,Partition,Account,QOS,"
            "ReqCPUS,ReqMem,Timelimit,NodeList%200,ElapsedRaw",
        ],
    }


def validate_original_failure(launch_path=LAUNCH, poll_path=POLL):
    launch_path = Path(launch_path).resolve()
    poll_path = Path(poll_path).resolve()
    if (C.W.file_sha(launch_path) != EXPECTED_LAUNCH_SHA256
            or C.W.file_sha(poll_path) != EXPECTED_POLL_SHA256):
        raise ValueError("original A launch/poll identity changed")
    launch = json.loads(launch_path.read_bytes())
    poll = json.loads(poll_path.read_bytes())
    if (launch.get("schema") != "pdb-within-family-launch/v1"
            or Path(launch.get("experiment", "")).resolve() != Runner.OUTPUT.resolve()
            or poll.get("schema") != "pdb-within-family-poll/v1"
            or poll.get("launch_sha256") != EXPECTED_LAUNCH_SHA256):
        raise ValueError("original A launch/poll identity changed")
    steps = _step_jobs(launch)
    queries = poll.get("queries")
    commands = _expected_query_commands(steps)
    if not isinstance(queries, dict) or set(queries) != set(commands):
        raise ValueError("original A scheduler query record changed")
    for name, command in commands.items():
        query = queries[name]
        if (query.get("command") != command or query.get("returncode") != 0
                or query.get("stderr") != ""):
            raise ValueError("original A scheduler query record changed")
    if queries["queue"].get("stdout") != "":
        raise ValueError("original A pipeline was not terminal")
    validation = C.Monitor.check_accounting(launch, queries["accounting"].get("stdout", ""))
    if poll.get("validation") != validation:
        raise ValueError("retained A scheduler validation changed")
    expected_total = sum(job["array_elements"] for job in steps.values())
    if (expected_total != 872 or validation["expected_elements"] != expected_total
            or validation["observed_elements"] != expected_total
            or not validation["resources_match"]):
        raise ValueError("A scheduler identities or resources changed")
    analysis_identity = steps["06-analyze"]["job_id"] + "_1"
    for identity, row in validation["rows"].items():
        if identity == analysis_identity:
            if row["state"] != "FAILED" or row["exit"] != "1:0":
                raise ValueError("original A analysis failure changed")
        elif row["state"] != "COMPLETED" or row["exit"] != "0:0":
            raise ValueError("a scientific or preprocessing A job did not succeed")
    logs = poll.get("pipeline_logs")
    grid = Path(str(Runner.OUTPUT) + "-grid-steps")
    if not isinstance(logs, dict) or set(logs) != {"slurm.log", "slurm.err"}:
        raise ValueError("original A pipeline logs changed")
    for name, record in logs.items():
        path = grid / name
        raw = path.read_bytes()
        if (C.G.sha(raw) != record.get("sha256")
                or raw[-12000:].decode("utf-8", "replace") != record.get("tail")):
            raise ValueError("original A pipeline logs changed")
    error_tail = logs["slurm.err"]["tail"]
    if (error_tail.count(SERIALIZATION_ERROR) != 1
            or "versions.append(C.G.canonical(result))" not in error_tail
            or not error_tail.endswith("aborting\n")):
        raise ValueError("original A analysis failed for a different reason")
    return {
        "step": "06-analyze",
        "job_id": steps["06-analyze"]["job_id"],
        "accounting_id": analysis_identity,
        "state": "FAILED",
        "exit": "1:0",
        "error": SERIALIZATION_ERROR,
    }


def _validate_freeze_and_properties(properties=PROPERTIES):
    freeze = C.load_freeze()
    if C.W.file_sha(C.FREEZE) != EXPECTED_FREEZE_SHA256:
        raise ValueError("frozen A cohort identity changed")
    properties = Path(properties).resolve()
    if C.W.file_sha(properties) != EXPECTED_PROPERTIES_SHA256:
        raise ValueError("A properties changed")
    analysis_sha = C.W.file_sha(ANALYSIS)
    if freeze["code_sha256"].get(ANALYSIS.name) != analysis_sha:
        raise ValueError("unchanged A analysis code identity changed")
    return freeze


def _validate_analysis(analysis_directory, properties, freeze):
    directory = Path(analysis_directory).resolve()
    properties = Path(properties).resolve()
    freeze_sha = C.W.file_sha(C.FREEZE)
    analysis_path = directory / "analysis.json"
    repeat_path = directory / "analysis-repeat.json"
    receipt_path = directory / "analysis-receipt.json"
    raw = analysis_path.read_bytes()
    if raw != repeat_path.read_bytes():
        raise ValueError("recovered repeated A analyses differ")
    result = json.loads(raw)
    receipt = json.loads(receipt_path.read_bytes())
    expected_receipt = {
        "schema": A.SCHEMA + "/double-execution",
        "byte_identical": True,
        "analysis_sha256": C.G.sha(raw),
        "repeat_sha256": C.G.sha(raw),
        "properties_sha256": EXPECTED_PROPERTIES_SHA256,
        "freeze_sha256": freeze_sha,
        "scheduler_audit_required_before_selector_launch": True,
    }
    if receipt != expected_receipt:
        raise ValueError("recovered A double-execution receipt changed")
    expected_input = {
        "properties_path": str(properties),
        "properties_sha256": EXPECTED_PROPERTIES_SHA256,
        "code_commit": freeze["code_commit"],
        "code_sha256": freeze["code_sha256"],
    }
    matrix = result.get("matrix", {})
    if (result.get("schema") != A.SCHEMA
            or result.get("freeze_sha256") != freeze_sha
            or result.get("scope") != freeze["scope"]
            or result.get("input") != expected_input
            or matrix.get("tasks") != C.TARGETS["a"]
            or matrix.get("cells") != 4 * C.TARGETS["a"]
            or matrix.get("configs") != 4
            or matrix.get("families") != len(freeze["families"])):
        raise ValueError("recovered A analysis identity or complete matrix changed")
    records = list(json.loads(properties.read_bytes()).values())
    A.verify_run_evidence(records, freeze, Runner.OUTPUT)
    with A.configured(freeze):
        A.validate_matrix(records, freeze, freeze_sha)
    passed = result.get("gates", {}).get("pass")
    if (type(passed) is not bool
            or passed != result["gates"].get("primary", {}).get("pass")
            or passed != result.get("statistical_selector_gate_passed")
            or result["gates"].get("decision") != ("PASS" if passed else "FAIL")
            or result["gates"].get("unseen_family_gate") is not False):
        raise ValueError("recovered A decision fields disagree")
    return result


def _committed_wrapper_identity(wrapper=WRAPPER):
    wrapper = Path(wrapper).resolve()
    repository = C.G.ROOT.parent.resolve()
    relative = wrapper.relative_to(repository).as_posix()
    revision = JJ.parent_commit(repository)
    sha256 = C.W.file_sha(wrapper)
    if JJ.tracked_file_sha256(repository, revision, relative) != sha256:
        raise ValueError("recovery wrapper is not identical to its committed revision")
    return {"path": str(wrapper), "sha256": sha256, "committed_revision": revision}


def _validate_committed_wrapper(record):
    if (not isinstance(record, dict) or Path(record.get("path", "")).resolve() != WRAPPER
            or C.W.file_sha(WRAPPER) != record.get("sha256")
            or re.fullmatch(r"[0-9a-f]{40}", record.get("committed_revision", "")) is None):
        raise ValueError("recovery wrapper identity changed")
    repository = C.G.ROOT.parent.resolve()
    relative = WRAPPER.relative_to(repository).as_posix()
    revision = record["committed_revision"]
    JJ.resolve_pinned_commit(repository, revision)
    if JJ.tracked_file_sha256(repository, revision, relative) != record["sha256"]:
        raise ValueError("committed recovery wrapper identity changed")


def _paths(output):
    output = Path(output).resolve()
    return {
        "recovery": output / RECOVERY.name,
        "invocation": output / INVOCATION.name,
        "stdout": output / STDOUT.name,
        "stderr": output / STDERR.name,
        "seal": output / SEAL.name,
        "analysis": output / "analysis.json",
        "repeat": output / "analysis-repeat.json",
        "analysis_receipt": output / "analysis-receipt.json",
    }


def _command(python, properties, output):
    return [
        str(Path(python).resolve()), "-X", "int_max_str_digits=100000", "-B",
        str(ANALYSIS.resolve()), "--properties", str(Path(properties).resolve()),
        "--output", str(Path(output).resolve()),
    ]


def _invocation(command, started, ended, returncode, timed_out, stdout, stderr, python):
    return {
        "schema": INVOCATION_SCHEMA,
        "command": command,
        "cwd": str(C.G.ROOT.resolve()),
        "environment": ENVIRONMENT,
        "interpreter": _sha_record(python),
        "integer_max_str_digits": INT_MAX_STR_DIGITS,
        "started_utc": started,
        "ended_utc": ended,
        "returncode": returncode,
        "timed_out": timed_out,
        "stdout_sha256": C.G.sha(stdout),
        "stderr_sha256": C.G.sha(stderr),
    }


def _receipt(failure, freeze, wrapper, invocation_path, paths, launch, poll, properties):
    evidence_paths = {
        "freeze": C.FREEZE,
        "launch": launch,
        "poll": poll,
        "properties": properties,
        "analysis": paths["analysis"],
        "repeat": paths["repeat"],
        "analysis_receipt": paths["analysis_receipt"],
        "stdout": paths["stdout"],
        "stderr": paths["stderr"],
    }
    return {
        "schema": SCHEMA,
        "integer_max_str_digits": INT_MAX_STR_DIGITS,
        "scientific_runs_repeated": 0,
        "scheduler_queries_made_by_recovery": 0,
        "original_analysis_failure": failure,
        "immutable_code": {
            "frozen_commit": freeze["code_commit"],
            "frozen_code_sha256": freeze["code_sha256"],
            "recovery_wrapper": wrapper,
        },
        "invocation": _sha_record(invocation_path),
        "evidence": {role: _sha_record(path) for role, path in evidence_paths.items()},
    }


def validate_recovery_receipt(receipt_path=RECOVERY, launch=LAUNCH, poll=POLL,
                              properties=PROPERTIES, output=A.OUTPUT):
    configure_integer_serialization()
    paths = _paths(output)
    if Path(receipt_path).resolve() != paths["recovery"]:
        raise ValueError("unexpected A serialization recovery receipt path")
    failure = validate_original_failure(launch, poll)
    freeze = _validate_freeze_and_properties(properties)
    result = _validate_analysis(output, properties, freeze)
    retained = json.loads(paths["recovery"].read_bytes())
    wrapper = retained.get("immutable_code", {}).get("recovery_wrapper")
    _validate_committed_wrapper(wrapper)
    invocation_record = retained.get("invocation", {})
    if invocation_record != _sha_record(paths["invocation"]):
        raise ValueError("recovery invocation identity changed")
    invocation = json.loads(paths["invocation"].read_bytes())
    expected_command = _command(PYTHON, properties, output)
    if (invocation.get("schema") != INVOCATION_SCHEMA
            or invocation.get("command") != expected_command
            or invocation.get("cwd") != str(C.G.ROOT.resolve())
            or invocation.get("environment") != ENVIRONMENT
            or invocation.get("interpreter") != _sha_record(PYTHON)
            or invocation.get("integer_max_str_digits") != INT_MAX_STR_DIGITS
            or invocation.get("returncode") != 0
            or invocation.get("timed_out") is not False
            or invocation.get("stdout_sha256") != C.W.file_sha(paths["stdout"])
            or invocation.get("stderr_sha256") != C.W.file_sha(paths["stderr"])):
        raise ValueError("recovery invocation changed")
    try:
        started = datetime.fromisoformat(invocation["started_utc"])
        ended = datetime.fromisoformat(invocation["ended_utc"])
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("recovery invocation times changed") from error
    if (started.tzinfo is None or ended.tzinfo is None or ended < started):
        raise ValueError("recovery invocation times changed")
    expected = _receipt(failure, freeze, wrapper, paths["invocation"], paths,
                        Path(launch).resolve(), Path(poll).resolve(), Path(properties).resolve())
    if retained != expected:
        raise ValueError("A serialization recovery receipt changed")
    return retained, result


def build_seal(receipt_path=RECOVERY, launch=LAUNCH, poll=POLL,
               properties=PROPERTIES, output=A.OUTPUT):
    recovery, result = validate_recovery_receipt(receipt_path, launch, poll, properties, output)
    paths = _paths(output)
    freeze = C.load_freeze()
    evidence_paths = {
        "freeze": C.FREEZE,
        "launch": Path(launch).resolve(),
        "poll": Path(poll).resolve(),
        "analysis": paths["analysis"],
        "repeat": paths["repeat"],
        "receipt": paths["analysis_receipt"],
        "properties": Path(properties).resolve(),
        "recovery": paths["recovery"],
    }
    seal = {
        "schema": SEAL_SCHEMA,
        "scope": freeze["scope"],
        "decision": result["gates"]["decision"],
        "selector_experiments_authorized": result["gates"]["pass"],
        "scheduler_queries_made_by_seal": 0,
        "original_scheduler_analysis": recovery["original_analysis_failure"],
        "matrix": result["matrix"],
        "code_commit": freeze["code_commit"],
        "evidence": {role: _sha_record(path) for role, path in evidence_paths.items()},
    }
    return seal, result


def load_seal(path=SEAL):
    configure_integer_serialization()
    retained = json.loads(Path(path).read_bytes())
    if retained.get("schema") != SEAL_SCHEMA or set(retained.get("evidence", {})) != {
            "freeze", "launch", "poll", "analysis", "repeat", "receipt", "properties", "recovery"}:
        raise ValueError("recovered A seal shape changed")
    for record in retained["evidence"].values():
        if _sha_record(record["path"]) != record:
            raise ValueError("recovered A evidence changed")
    evidence = retained["evidence"]
    fresh, result = build_seal(
        evidence["recovery"]["path"], evidence["launch"]["path"],
        evidence["poll"]["path"], evidence["properties"]["path"],
        Path(evidence["analysis"]["path"]).parent)
    if retained != fresh:
        raise ValueError("recovered A seal cannot be reproduced")
    return retained, result


def recover(launch=LAUNCH, poll=POLL, properties=PROPERTIES, output=A.OUTPUT,
            python=PYTHON, runner=None):
    configure_integer_serialization()
    output = Path(output).resolve()
    if output != A.OUTPUT.resolve():
        raise ValueError("recovery must use the original canonical A analysis directory")
    paths = _paths(output)
    if any(path.exists() for path in paths.values()):
        raise ValueError("refusing existing analysis outputs, recovery records, or diagnostic logs")
    failure = validate_original_failure(launch, poll)
    freeze = _validate_freeze_and_properties(properties)
    if C.W.file_sha(python) != EXPECTED_PYTHON_SHA256:
        raise ValueError("pinned recovery interpreter changed")
    wrapper = _committed_wrapper_identity()
    command = _command(python, properties, output)
    environment = os.environ.copy()
    for name in ENVIRONMENT["unset"]:
        environment.pop(name, None)
    environment.update(ENVIRONMENT["set"])
    started = datetime.now(timezone.utc).isoformat()
    run = subprocess.run if runner is None else runner
    try:
        completed = run(command, cwd=C.G.ROOT, env=environment, capture_output=True,
                        timeout=TIMEOUT_SECONDS, check=False)
    except subprocess.TimeoutExpired as error:
        ended = datetime.now(timezone.utc).isoformat()
        stdout = error.stdout or b""
        stderr = error.stderr or b""
        if isinstance(stdout, str):
            stdout = stdout.encode("utf-8")
        if isinstance(stderr, str):
            stderr = stderr.encode("utf-8")
        _write_exclusive(paths["stdout"], stdout)
        _write_exclusive(paths["stderr"], stderr)
        invocation = _invocation(command, started, ended, None, True, stdout, stderr, python)
        C.Monitor.publish(paths["invocation"], invocation)
        raise ValueError("bounded local analysis recovery timed out") from error
    ended = datetime.now(timezone.utc).isoformat()
    _write_exclusive(paths["stdout"], completed.stdout)
    _write_exclusive(paths["stderr"], completed.stderr)
    invocation = _invocation(command, started, ended, completed.returncode, False,
                             completed.stdout, completed.stderr, python)
    C.Monitor.publish(paths["invocation"], invocation)
    if completed.returncode != 0:
        raise ValueError("local analysis recovery returned nonzero")
    freeze_after = _validate_freeze_and_properties(properties)
    if freeze_after != freeze:
        raise ValueError("frozen A identity changed during recovery")
    _validate_analysis(output, properties, freeze_after)
    receipt = _receipt(failure, freeze_after, wrapper, paths["invocation"], paths,
                       Path(launch).resolve(), Path(poll).resolve(), Path(properties).resolve())
    C.Monitor.publish(paths["recovery"], receipt)
    seal, _ = build_seal(paths["recovery"], launch, poll, properties, output)
    C.Monitor.publish(paths["seal"], seal)
    return receipt, seal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--launch", type=Path, default=LAUNCH)
    parser.add_argument("--poll", type=Path, default=POLL)
    args = parser.parse_args()
    receipt, seal = recover(args.launch.resolve(), args.poll.resolve())
    print(json.dumps({
        "recovery_sha256": C.G.sha(C.G.canonical(receipt)),
        "seal_sha256": C.G.sha(C.G.canonical(seal)),
    }, sort_keys=True))


if __name__ == "__main__":
    main()
