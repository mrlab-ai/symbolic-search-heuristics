#!/usr/bin/env python3
"""Audit or seal the shadow study without reading experimental outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
from collections import Counter
from pathlib import Path

import pdb_terminal_incidence_shadow_protocol as P
import jj_cached_revision as JJ


class ExecutionAuditError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
EXPERIMENT_PATH = SCRIPT_DIR / "data" / "exp_pdb_terminal_incidence_shadow"
GRID_DIR = Path(str(EXPERIMENT_PATH) + "-grid-steps")
EXPECTED_JOB_NAME = "exp_pdb_terminal_incidence_shadow-02-start"
EXPECTED_CELLS = 2300
RUNS_PER_ARRAY_TASK = 3
EXPECTED_ARRAY_TASKS = 767
SCHEDULER_TIME_LIMIT = "00:20:00"
SCHEDULER_MEMORY = "9G"
PARTITION = "fat"
QOS = "normal"
LAUNCH_RECEIPT = (
    SCRIPT_DIR
    / "artifacts"
    / "pdb-terminal-incidence-shadow"
    / "launch-receipt-v1.json"
)
LAUNCH_RECEIPT_SCHEMA = (
    "symbolic-search-heuristics/pdb-terminal-incidence-shadow-launch/v1"
)
LAUNCH_INTENT = LAUNCH_RECEIPT.with_name("launch-intent-v1.json")
BUILD_RECEIPT = LAUNCH_RECEIPT.with_name("build-receipt-v1.json")
LAUNCH_RECEIPT_PIN = LAUNCH_RECEIPT.with_name("launch-receipt-v1.sha256")
try:
    pin_info = LAUNCH_RECEIPT_PIN.lstat()
    if LAUNCH_RECEIPT_PIN.is_symlink() or not stat.S_ISREG(pin_info.st_mode):
        raise OSError("launch receipt pin is not a regular file")
    LAUNCH_RECEIPT_SHA256 = LAUNCH_RECEIPT_PIN.read_text(
        encoding="ascii"
    ).strip()
except (OSError, UnicodeDecodeError):
    # The separate pin appears only after the one permitted launch. Keeping
    # it out of this source file lets the build-sealed audit code stay exact.
    LAUNCH_RECEIPT_SHA256 = "TO_PIN_AFTER_LAUNCH"
EXECUTION_RECEIPT = (
    SCRIPT_DIR
    / "artifacts"
    / "pdb-terminal-incidence-shadow"
    / "execution-receipt-v1.json"
)
EXECUTION_RECEIPT_SCHEMA = (
    "symbolic-search-heuristics/pdb-terminal-incidence-shadow-execution/v1"
)
EXECUTION_RECEIPT_PIN = EXECUTION_RECEIPT.with_name(
    "execution-receipt-v1.sha256"
)
PARSE_RECEIPT = EXECUTION_RECEIPT.with_name("parse-receipt-v1.json")
PARSE_RECEIPT_PIN = EXECUTION_RECEIPT.with_name("parse-receipt-v1.sha256")
PARSE_INTENT = EXECUTION_RECEIPT.with_name("parse-intent-v1.json")
PARSE_RECEIPT_SCHEMA = (
    "symbolic-search-heuristics/pdb-terminal-incidence-shadow-parse/v1"
)
PARSE_INTENT_SCHEMA = "{}/intent".format(PARSE_RECEIPT_SCHEMA)
FETCH_RECEIPT = EXECUTION_RECEIPT.with_name("fetch-receipt-v1.json")
FETCH_RECEIPT_PIN = EXECUTION_RECEIPT.with_name("fetch-receipt-v1.sha256")
FETCH_INTENT = EXECUTION_RECEIPT.with_name("fetch-intent-v1.json")
FETCH_RECEIPT_SCHEMA = (
    "symbolic-search-heuristics/pdb-terminal-incidence-shadow-fetch/v1"
)
FETCH_INTENT_SCHEMA = "{}/intent".format(FETCH_RECEIPT_SCHEMA)
EVAL_PROPERTIES = Path(str(EXPERIMENT_PATH) + "-eval") / "properties"
RECOVERY_RECEIPT_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-shadow-recovery-launch/v1"
)
RECOVERY_INTENT_SCHEMA = "{}/intent".format(RECOVERY_RECEIPT_SCHEMA)
RECOVERY_DYNAMIC_NAMES = {
    "driver.err",
    "driver.log",
    "output.sas",
    "run.err",
    "run.log",
    "sas_plan",
    "wbh-profile.jsonl",
    "wbh.jsonl",
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
DRIVER_TERMINAL_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} "
    r"INFO     planner exit code: -?\d+$"
)
TERMINAL_SCHEDULER_STATES = {
    "BOOT_FAIL",
    "CANCELLED",
    "COMPLETED",
    "DEADLINE",
    "FAILED",
    "NODE_FAIL",
    "OUT_OF_MEMORY",
    "PREEMPTED",
    "REVOKED",
    "TIMEOUT",
}


def _sha256_file(path: Path) -> str:
    _require_regular_file(Path(path), "hashed artifact")
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as err:
        raise ExecutionAuditError("cannot hash {}".format(path)) from err
    return digest.hexdigest()


def _require_regular_file(path: Path, label: str) -> None:
    try:
        info = path.lstat()
    except OSError as err:
        raise ExecutionAuditError("{} is not a regular file".format(label)) from err
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise ExecutionAuditError("{} is not a regular file".format(label))


def _read_pin(path: Path, label: str) -> str:
    _require_regular_file(path, "{} SHA-256 pin".format(label))
    try:
        raw = path.read_bytes()
    except OSError as err:
        raise ExecutionAuditError("{} SHA-256 is not pinned".format(label)) from err
    try:
        value = raw.decode("ascii").strip()
    except UnicodeDecodeError as err:
        raise ExecutionAuditError("{} SHA-256 pin is invalid".format(label)) from err
    if raw != (value + "\n").encode("ascii") or SHA256_RE.fullmatch(value) is None:
        raise ExecutionAuditError("{} SHA-256 pin is invalid".format(label))
    return value


def _load_pinned_json(path: Path, pin: Path, label: str) -> tuple[str, dict]:
    expected = _read_pin(pin, label)
    _require_regular_file(path, label)
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ExecutionAuditError("cannot load {}".format(label)) from err
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ExecutionAuditError("{} bytes changed".format(label))
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii") + b"\n"
    if raw != canonical or not isinstance(value, dict):
        raise ExecutionAuditError("{} is not canonical".format(label))
    return expected, value


def _write_exclusive_json(path: Path, value, label: str) -> str:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii") + b"\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise ExecutionAuditError("{} already exists".format(label)) from err
    return hashlib.sha256(raw).hexdigest()


def _launch_receipt_bytes() -> tuple[bytes, dict]:
    if SHA256_RE.fullmatch(LAUNCH_RECEIPT_SHA256) is None:
        raise ExecutionAuditError(
            "launch receipt SHA-256 is not pinned after submission"
        )
    _require_regular_file(LAUNCH_RECEIPT, "launch receipt")
    try:
        raw = LAUNCH_RECEIPT.read_bytes()
        receipt = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ExecutionAuditError("cannot load the launch receipt") from err
    if hashlib.sha256(raw).hexdigest() != LAUNCH_RECEIPT_SHA256:
        raise ExecutionAuditError("launch receipt bytes changed")
    return raw, receipt


def _validate_live_sources(source_hashes: dict) -> None:
    import exp_pdb_terminal_incidence_shadow as Runner

    if set(source_hashes) != set(Runner.RUNNER_SOURCE_FILES):
        raise ExecutionAuditError("launch receipt source set changed")
    for name, expected in source_hashes.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ExecutionAuditError("launch receipt has an unsafe source path")
        path = SCRIPT_DIR / relative
        try:
            info = path.lstat()
        except OSError as err:
            raise ExecutionAuditError("sealed source file is absent") from err
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise ExecutionAuditError("sealed source is not a regular file")
        if _sha256_file(path) != expected:
            raise ExecutionAuditError("sealed source bytes changed")


def _validate_static_experiment_properties(expected: str) -> None:
    path = EXPERIMENT_PATH / "static-experiment-properties"
    try:
        info = path.lstat()
    except OSError as err:
        raise ExecutionAuditError(
            "static experiment properties are absent"
        ) from err
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise ExecutionAuditError(
            "static experiment properties are not a regular file"
        )
    if _sha256_file(path) != expected:
        raise ExecutionAuditError("static experiment properties changed")


def load_launch_receipt() -> dict:
    _, receipt = _launch_receipt_bytes()
    fixed = {
        "schema": LAUNCH_RECEIPT_SCHEMA,
        "job_name": EXPECTED_JOB_NAME,
        "partition": PARTITION,
        "qos": QOS,
        "slurm_array": "1-{}".format(EXPECTED_ARRAY_TASKS),
        "array_throttle": 0,
        "array_tasks": EXPECTED_ARRAY_TASKS,
        "runs_per_array_task": RUNS_PER_ARRAY_TASK,
        "cells": EXPECTED_CELLS,
        "time_limit": SCHEDULER_TIME_LIMIT,
        "memory_per_cpu": SCHEDULER_MEMORY,
        "cpus_per_task": 1,
        "account": P.ACCOUNT,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "lab_version": P.REQUIRED_LAB_VERSION,
        "python_version": P.REQUIRED_PYTHON_VERSION,
        "planner_revision": P.PLANNER_REVISION,
        "benchmark_revision": P.BENCHMARK_REVISION,
        "planner_cache_name": P.PLANNER_CACHE_NAME,
        "translator_source_sha256": P.TRANSLATOR_SOURCE_SHA256,
        "cost_attestation_sha256": P.COST_ATTESTATION_SHA256,
        "cost_attestation_records_sha256": (
            P.COST_ATTESTATION_RECORDS_SHA256
        ),
        "source_audit_job_id": P.SOURCE_AUDIT_JOB_ID,
        "source_audit_launch_receipt_sha256": (
            P.SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256
        ),
        "source_audit_execution_receipt_sha256": (
            P.SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256
        ),
        "source_audit_slurm_sha256": P.SOURCE_AUDIT_SLURM_SHA256,
        "source_audit_intent_sha256": P.SOURCE_AUDIT_INTENT_SHA256,
        "source_audit_code_manifest_sha256": (
            P.SOURCE_AUDIT_CODE_MANIFEST_SHA256
        ),
        "source_audit_output_tree_sha256": (
            P.SOURCE_AUDIT_OUTPUT_TREE_SHA256
        ),
        "source_audit_repository_commit_id": (
            P.SOURCE_AUDIT_REPOSITORY_COMMIT_ID
        ),
        "generated_run_files": EXPECTED_CELLS,
        "generated_static_property_files": EXPECTED_CELLS,
        "materialized_pddl_inputs": True,
        "generated_pddl_input_files": 2 * EXPECTED_CELLS,
    }
    if not isinstance(receipt, dict) or any(
        receipt.get(key) != value for key, value in fixed.items()
    ):
        raise ExecutionAuditError("launch receipt semantics changed")
    for field in (
        "job_file_sha256",
        "generated_run_input_tree_sha256",
        "static_experiment_properties_sha256",
        "launch_intent_sha256",
        "build_receipt_sha256",
    ):
        if SHA256_RE.fullmatch(receipt.get(field, "")) is None:
            raise ExecutionAuditError("launch receipt has an invalid hash")
    _require_regular_file(LAUNCH_INTENT, "launch intent")
    try:
        intent_raw = LAUNCH_INTENT.read_bytes()
        intent = json.loads(intent_raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ExecutionAuditError("cannot load the launch intent") from err
    if hashlib.sha256(intent_raw).hexdigest() != receipt["launch_intent_sha256"]:
        raise ExecutionAuditError("launch intent bytes changed")
    expected_intent = {
        "schema": "{}/intent".format(LAUNCH_RECEIPT_SCHEMA),
        "prepared_receipt_without_job_id": {
            key: value for key, value in receipt.items()
            if key not in {"job_id", "launch_intent_sha256"}
        },
    }
    if intent != expected_intent or intent_raw != (
        json.dumps(
            intent, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii") + b"\n"
    ):
        raise ExecutionAuditError("launch intent semantics changed")
    _require_regular_file(BUILD_RECEIPT, "build receipt")
    if _sha256_file(BUILD_RECEIPT) != receipt["build_receipt_sha256"]:
        raise ExecutionAuditError("build receipt bytes changed")
    try:
        build = json.loads(BUILD_RECEIPT.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ExecutionAuditError("cannot load the build receipt") from err
    shared_build_fields = (
        "cells",
        "planner_revision",
        "cohort_manifest_sha256",
        "option_matrix_sha256",
        "protocol_sha256",
        "lab_version",
        "python_version",
        "python_executable",
        "python_executable_sha256",
        "python_environment_sha256",
        "python_distributions",
        "python_requirements_sha256",
        "revision_cache_attestation",
        "experiment_code_path",
        "experiment_code_attestation",
        "static_experiment_properties_sha256",
        "generated_run_input_tree_sha256",
        "generated_run_files",
        "generated_static_property_files",
        "materialized_pddl_inputs",
        "generated_pddl_input_files",
        "source_file_sha256",
    )
    if (
        not isinstance(build, dict)
        or build.get("schema") != "{}/build".format(LAUNCH_RECEIPT_SCHEMA)
        or any(build.get(field) != receipt.get(field)
               for field in shared_build_fields)
    ):
        raise ExecutionAuditError("build and launch receipts disagree")
    attestation = receipt.get("revision_cache_attestation")
    expected_attestation = {
        "revision": P.PLANNER_REVISION,
        "build_options": list(P.BUILD_OPTIONS),
        "downward_sha256": P.PLANNER_BINARY_SHA256,
        "preprocess_sha256": P.PREPROCESS_BINARY_SHA256,
        "tree_manifest_sha256": P.PLANNER_TREE_MANIFEST_SHA256,
    }
    if not isinstance(attestation, dict) or any(
        attestation.get(key) != value
        for key, value in expected_attestation.items()
    ):
        raise ExecutionAuditError("revision-cache attestation changed")
    experiment_attestation = receipt.get("experiment_code_attestation")
    if experiment_attestation != attestation:
        raise ExecutionAuditError("experiment-code attestation changed")
    cached = JJ.JjCachedFastDownwardRevision(
        SCRIPT_DIR / "data" / "revision-cache",
        SCRIPT_DIR.parent,
        P.PLANNER_REVISION,
        list(P.BUILD_OPTIONS),
    )
    if cached.name != P.PLANNER_CACHE_NAME:
        raise ExecutionAuditError("revision-cache name changed")
    if cached.attest() != attestation:
        raise ExecutionAuditError("revision cache changed after launch")
    code_path = receipt.get("experiment_code_path")
    if not isinstance(code_path, str) or not code_path:
        raise ExecutionAuditError("experiment code path is invalid")
    try:
        resolved_code = (EXPERIMENT_PATH / code_path).resolve()
        resolved_code.relative_to(EXPERIMENT_PATH.resolve())
    except (OSError, ValueError) as err:
        raise ExecutionAuditError("experiment code path escapes") from err
    if cached.attest_path(resolved_code) != experiment_attestation:
        raise ExecutionAuditError("experiment code changed after launch")
    source_hashes = receipt.get("source_file_sha256")
    if (
        not isinstance(source_hashes, dict)
        or not source_hashes
        or any(
            not isinstance(name, str)
            or not name
            or SHA256_RE.fullmatch(value or "") is None
            for name, value in source_hashes.items()
        )
    ):
        raise ExecutionAuditError("launch receipt has invalid source hashes")
    _validate_live_sources(source_hashes)
    import exp_pdb_profile_certificate_holdout as Base

    current_environment = Base._environment_attestation(
        SCRIPT_DIR / "requirements-pdb-terminal-incidence-shadow.txt"
    )
    if (
        receipt.get("python_executable")
        != str(Path(Base.sys.executable).resolve())
        or any(
            receipt.get(field) != value
            for field, value in current_environment.items()
        )
    ):
        raise ExecutionAuditError("sealed Python environment changed")
    _validate_static_experiment_properties(
        receipt["static_experiment_properties_sha256"]
    )
    if not isinstance(receipt.get("job_id"), str) or not receipt["job_id"].isdigit():
        raise ExecutionAuditError("launch receipt has an invalid job id")
    return receipt


def _run_dir(run_id: int) -> Path:
    if type(run_id) is not int or not 1 <= run_id <= EXPECTED_CELLS:
        raise ExecutionAuditError("run id is out of range")
    lower = ((run_id - 1) // 100) * 100 + 1
    # Lab uses full 100-run shard names, including the final shard.
    upper = lower + 99
    return (
        EXPERIMENT_PATH
        / "runs-{:05d}-{:05d}".format(lower, upper)
        / "{:05d}".format(run_id)
    )


def _run_input_tree_digest() -> tuple[str, int, int]:
    digest = hashlib.sha256()
    expected_directories = []
    expected_files = []
    for run_id in range(1, EXPECTED_CELLS + 1):
        directory = _run_dir(run_id).relative_to(EXPERIMENT_PATH)
        expected_directories.append(directory)
        names = ("run", "static-properties", "domain.pddl", "problem.pddl")
        run_dir = EXPERIMENT_PATH / directory
        if run_dir.is_symlink() or not run_dir.is_dir():
            raise ExecutionAuditError(
                "generated run directory is absent or invalid"
            )
        try:
            entries = list(run_dir.iterdir())
        except OSError as err:
            raise ExecutionAuditError(
                "cannot inspect generated run directory"
            ) from err
        entry_names = {entry.name for entry in entries}
        if (
            not set(names) <= entry_names
            or not entry_names
            <= set(names) | RECOVERY_DYNAMIC_NAMES | {"properties"}
        ):
            raise ExecutionAuditError(
                "generated run directory has unexpected entries"
            )
        expected_files.extend(directory / name for name in names)
    actual_directories = {
        path.relative_to(EXPERIMENT_PATH)
        for path in EXPERIMENT_PATH.glob("runs-*/[0-9]*")
    }
    if actual_directories != set(expected_directories):
        raise ExecutionAuditError("generated run matrix has wrong directories")
    for relative in expected_files:
        path = EXPERIMENT_PATH / relative
        try:
            info = path.lstat()
        except OSError as err:
            raise ExecutionAuditError("cannot inspect generated run input") from err
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise ExecutionAuditError(
                "generated run input is not a regular file"
            )
        encoded = relative.as_posix().encode("ascii")
        digest.update(encoded + b"\0" + bytes.fromhex(_sha256_file(path)))
    return digest.hexdigest(), EXPECTED_CELLS, EXPECTED_CELLS


def cell_completeness() -> tuple[dict[str, int], list[int]]:
    counts = Counter()
    incomplete = []
    for run_id in range(1, EXPECTED_CELLS + 1):
        path = _run_dir(run_id) / "driver.log"
        if path.is_symlink():
            raise ExecutionAuditError("driver completeness marker is a symlink")
        if not path.is_file():
            state = "missing"
        else:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as err:
                raise ExecutionAuditError(
                    "cannot inspect driver completeness for run {}".format(run_id)
                ) from err
            state = (
                "complete"
                if lines and DRIVER_TERMINAL_RE.fullmatch(lines[-1])
                else "interrupted"
            )
        counts[state] += 1
        if state != "complete":
            incomplete.append(run_id)
    return dict(counts), incomplete


def scheduler_rows(job_id: str, expected_array_tasks=None) -> list[dict]:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise ExecutionAuditError("Slurm job id is invalid")
    if expected_array_tasks is None:
        expected_array_tasks = set(range(1, EXPECTED_ARRAY_TASKS + 1))
    else:
        expected_array_tasks = set(expected_array_tasks)
    if (
        not expected_array_tasks
        or any(
            type(task) is not int or not 1 <= task <= EXPECTED_ARRAY_TASKS
            for task in expected_array_tasks
        )
    ):
        raise ExecutionAuditError("expected Slurm task set is invalid")
    command = [
        "sacct",
        "-j",
        job_id,
        "-X",
        "-n",
        "-P",
        "-o",
        "JobID,JobIDRaw,State,ExitCode,NodeList,ElapsedRaw,Partition",
    ]
    try:
        output = subprocess.check_output(command, text=True)
    except (OSError, subprocess.CalledProcessError) as err:
        raise ExecutionAuditError("cannot query Slurm accounting") from err
    rows = []
    prefix = job_id + "_"
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 7:
            raise ExecutionAuditError("unexpected sacct row shape")
        array_id, raw_id, state, exit_code, node, elapsed, partition = fields
        state = state.split("+", 1)[0].split()[0]
        if not array_id.startswith(prefix) or not array_id[len(prefix):].isdigit():
            continue
        task = int(array_id[len(prefix):])
        if task not in expected_array_tasks:
            raise ExecutionAuditError("Slurm array task id is out of range")
        if partition != PARTITION:
            raise ExecutionAuditError("Slurm accounting reports a non-fat task")
        rows.append({
            "array_task": task,
            "job_id_raw": raw_id,
            "state": state,
            "exit_code": exit_code,
            "node": node,
            "elapsed_raw": elapsed,
            "partition": partition,
        })
    by_task = {}
    for row in rows:
        task = row["array_task"]
        if task in by_task:
            raise ExecutionAuditError("Slurm accounting repeats an array task")
        by_task[task] = row
    if set(by_task) != expected_array_tasks:
        raise ExecutionAuditError(
            "Slurm accounting has {} of {} expected array tasks".format(
                len(by_task), len(expected_array_tasks)
            )
        )
    return [by_task[task] for task in sorted(by_task)]


def _recovery_wave(path: Path) -> int:
    match = re.fullmatch(r"wave-(\d{4})", path.name)
    if match is None:
        raise ExecutionAuditError("recovery wave path is malformed")
    return int(match.group(1))


def _load_recovery_json(path: Path, label: str) -> tuple[bytes, dict]:
    if path.is_symlink() or not path.is_file():
        raise ExecutionAuditError("{} is not a regular file".format(label))
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ExecutionAuditError("cannot load {}".format(label)) from err
    canonical = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii") + b"\n"
    if raw != canonical or not isinstance(value, dict):
        raise ExecutionAuditError("{} bytes are not canonical".format(label))
    return raw, value


def _valid_recovery_tasks(value) -> bool:
    return (
        isinstance(value, list)
        and value
        and value == sorted(set(value))
        and all(
            type(task) is int and 1 <= task <= EXPECTED_ARRAY_TASKS
            for task in value
        )
    )


def _valid_recovery_cells(value, tasks: list[int]) -> bool:
    if (
        not isinstance(value, list)
        or value != sorted(set(value))
        or any(type(cell) is not int for cell in value)
    ):
        return False
    allowed = set()
    for task in tasks:
        first = (task - 1) * RUNS_PER_ARRAY_TASK + 1
        allowed.update(
            range(first, min(first + RUNS_PER_ARRAY_TASK, EXPECTED_CELLS + 1))
        )
    return set(value) <= allowed


def _validate_recovery_archive(
    wave_dir: Path, plan, recoverable_cells: list[int]
) -> None:
    if not isinstance(plan, list):
        raise ExecutionAuditError("recovery archive plan is invalid")
    identities = set()
    for item in plan:
        if not isinstance(item, dict) or set(item) != {
            "run_id", "name", "source", "target", "size", "sha256"
        }:
            raise ExecutionAuditError("recovery archive item is invalid")
        run_id = item["run_id"]
        name = item["name"]
        if (
            type(run_id) is not int
            or run_id not in recoverable_cells
            or name not in RECOVERY_DYNAMIC_NAMES
            or type(item["size"]) is not int
            or item["size"] < 0
            or SHA256_RE.fullmatch(item["sha256"] or "") is None
        ):
            raise ExecutionAuditError("recovery archive item changed")
        expected_source = (_run_dir(run_id) / name).relative_to(
            EXPERIMENT_PATH
        ).as_posix()
        expected_target = (
            Path("interrupted-cell-files")
            / "{:05d}".format(run_id)
            / name
        ).as_posix()
        if (
            item["source"] != expected_source
            or item["target"] != expected_target
            or (run_id, name) in identities
        ):
            raise ExecutionAuditError("recovery archive paths changed")
        identities.add((run_id, name))
        target = wave_dir / expected_target
        if (
            target.is_symlink()
            or not target.is_file()
            or target.stat().st_size != item["size"]
            or _sha256_file(target) != item["sha256"]
        ):
            raise ExecutionAuditError("recovery archive bytes changed")


def recovery_executions(launch: dict) -> list[dict]:
    executions = []
    root = LAUNCH_RECEIPT.parent / "recovery"
    if not root.exists():
        return executions
    if root.is_symlink() or not root.is_dir():
        raise ExecutionAuditError("recovery root is not a regular directory")
    for wave_dir in sorted(root.iterdir()):
        if wave_dir.is_symlink() or not wave_dir.is_dir():
            raise ExecutionAuditError("recovery root contains an invalid entry")
        wave = _recovery_wave(wave_dir)
        intent_path = wave_dir / "launch-intent.json"
        receipt_path = wave_dir / "launch-receipt.json"
        if not intent_path.exists() or not receipt_path.exists():
            raise ExecutionAuditError(
                "recovery wave has an unresolved launch intent"
            )
        intent_raw, intent = _load_recovery_json(
            intent_path, "recovery launch intent"
        )
        raw, receipt = _load_recovery_json(
            receipt_path, "recovery launch receipt"
        )
        tasks = receipt.get("array_tasks")
        cells = receipt.get("recoverable_cells")
        valid_tasks = _valid_recovery_tasks(tasks)
        valid_cells = valid_tasks and _valid_recovery_cells(cells, tasks)
        common = (
            "wave",
            "source_job_id",
            "source_launch_receipt_sha256",
            "source_job_file_sha256",
            "array_tasks",
            "array_spec",
            "array_throttle",
            "partition",
            "qos",
            "runs_per_array_task",
            "cells",
            "recoverable_cells",
            "submit_command",
        )
        if (
            intent.get("schema") != RECOVERY_INTENT_SCHEMA
            or receipt.get("schema") != RECOVERY_RECEIPT_SCHEMA
            or intent.get("wave") != wave
            or receipt.get("wave") != wave
            or receipt.get("source_job_id") != launch["job_id"]
            or receipt.get("source_launch_receipt_sha256")
            != LAUNCH_RECEIPT_SHA256
            or receipt.get("source_job_file_sha256")
            != launch["job_file_sha256"]
            or receipt.get("partition") != PARTITION
            or receipt.get("qos") != QOS
            or receipt.get("array_throttle") != 0
            or receipt.get("runs_per_array_task") != RUNS_PER_ARRAY_TASK
            or receipt.get("cells") != EXPECTED_CELLS
            or not valid_tasks
            or not valid_cells
            or receipt.get("array_spec")
            != ",".join(str(task) for task in tasks)
            or not isinstance(receipt.get("job_id"), str)
            or not receipt["job_id"].isdigit()
            or SHA256_RE.fullmatch(
                receipt.get("launch_intent_sha256", "")
            ) is None
            or receipt["launch_intent_sha256"]
            != hashlib.sha256(intent_raw).hexdigest()
            or any(intent.get(field) != receipt.get(field) for field in common)
            or intent.get("archive_plan")
            != receipt.get("archived_interrupted_files")
        ):
            raise ExecutionAuditError("recovery launch receipt semantics changed")
        expected_command = [
            "sbatch",
            "--parsable",
            "--export=PATH",
            "--array={}".format(receipt["array_spec"]),
            "--job-name=pdb-terminal-incidence-shadow-recovery-{:04d}".format(
                wave
            ),
            "--output={}".format(
                (wave_dir / "slurm-%A_%a.log").resolve()
            ),
            "--error={}".format(
                (wave_dir / "slurm-%A_%a.err").resolve()
            ),
            "--partition={}".format(PARTITION),
            "--qos={}".format(QOS),
            "--time={}".format(SCHEDULER_TIME_LIMIT),
            "--mem-per-cpu={}".format(SCHEDULER_MEMORY),
            "--cpus-per-task=1",
            "--account={}".format(launch["account"]),
            "--no-requeue",
            str((GRID_DIR / EXPECTED_JOB_NAME).resolve()),
        ]
        if receipt.get("submit_command") != expected_command:
            raise ExecutionAuditError("recovery submit command changed")
        _validate_recovery_archive(
            wave_dir, intent.get("archive_plan"), cells
        )
        executions.append({
            "intent_path": intent_path.relative_to(SCRIPT_DIR.parent).as_posix(),
            "intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "receipt_path": receipt_path.relative_to(SCRIPT_DIR.parent).as_posix(),
            "receipt_sha256": hashlib.sha256(raw).hexdigest(),
            "receipt": receipt,
            "scheduler_rows": scheduler_rows(receipt["job_id"], tasks),
        })
    return executions


def dynamic_tree_digest() -> tuple[str, int]:
    digest = hashlib.sha256()
    files = 0
    excluded = {
        "run", "static-properties", "domain.pddl", "problem.pddl",
        "properties",
    }
    for run_id in range(1, EXPECTED_CELLS + 1):
        run_dir = _run_dir(run_id)
        try:
            paths = sorted(run_dir.iterdir())
        except OSError as err:
            raise ExecutionAuditError(
                "cannot inspect dynamic files for run {}".format(run_id)
            ) from err
        for path in paths:
            if path.name in excluded:
                continue
            if path.is_symlink() or not path.is_file():
                raise ExecutionAuditError(
                    "dynamic cell entry is not a regular file"
                )
            relative = path.relative_to(EXPERIMENT_PATH).as_posix().encode("ascii")
            digest.update(relative + b"\0" + bytes.fromhex(_sha256_file(path)))
            files += 1
    return digest.hexdigest(), files


def load_execution_receipt(*, verify_live: bool = True) -> tuple[str, dict]:
    launch = load_launch_receipt()
    digest, receipt = _load_pinned_json(
        EXECUTION_RECEIPT,
        EXECUTION_RECEIPT_PIN,
        "execution receipt",
    )
    if (
        set(receipt) != {
            "schema",
            "launch_receipt_sha256",
            "job_id",
            "array_throttle",
            "partition",
            "scheduler_state_counts",
            "cell_state_counts",
            "scheduler_rows",
            "recovery_executions",
            "dynamic_cell_tree_sha256",
            "dynamic_cell_files",
        }
        or receipt.get("schema") != EXECUTION_RECEIPT_SCHEMA
        or receipt.get("launch_receipt_sha256") != LAUNCH_RECEIPT_SHA256
        or receipt.get("job_id") != launch["job_id"]
        or receipt.get("array_throttle") != 0
        or receipt.get("partition") != PARTITION
        or receipt.get("cell_state_counts") != {"complete": EXPECTED_CELLS}
        or SHA256_RE.fullmatch(
            receipt.get("dynamic_cell_tree_sha256", "")
        ) is None
        or type(receipt.get("dynamic_cell_files")) is not int
        or receipt["dynamic_cell_files"] < EXPECTED_CELLS
    ):
        raise ExecutionAuditError("execution receipt semantics changed")
    if verify_live:
        input_hash, run_files, property_files = _run_input_tree_digest()
        if any((
            input_hash != launch["generated_run_input_tree_sha256"],
            run_files != launch["generated_run_files"],
            property_files != launch["generated_static_property_files"],
            launch["generated_pddl_input_files"] != 2 * run_files,
        )):
            raise ExecutionAuditError(
                "sealed immutable generated run inputs changed"
            )
        tree_hash, files = dynamic_tree_digest()
        if (
            tree_hash != receipt["dynamic_cell_tree_sha256"]
            or files != receipt["dynamic_cell_files"]
        ):
            raise ExecutionAuditError("sealed dynamic cell bytes changed")
    return digest, receipt


def _parsed_properties_tree_digest() -> tuple[str, int]:
    digest = hashlib.sha256()
    expected = [_run_dir(run_id) / "properties"
                for run_id in range(1, EXPECTED_CELLS + 1)]
    actual = list(EXPERIMENT_PATH.glob("runs-*/[0-9]*/properties"))
    if {path.relative_to(EXPERIMENT_PATH) for path in actual} != {
        path.relative_to(EXPERIMENT_PATH) for path in expected
    }:
        raise ExecutionAuditError("parsed properties matrix has wrong paths")
    for path in expected:
        try:
            info = path.lstat()
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
            raise ExecutionAuditError("cannot validate parsed properties") from err
        if (
            path.is_symlink()
            or not stat.S_ISREG(info.st_mode)
            or not isinstance(value, dict)
        ):
            raise ExecutionAuditError("parsed properties file is invalid")
        relative = path.relative_to(EXPERIMENT_PATH).as_posix().encode("ascii")
        digest.update(relative + b"\0" + bytes.fromhex(_sha256_file(path)))
    return digest.hexdigest(), len(expected)


def validate_before_parse() -> None:
    if any(path.exists() or path.is_symlink() for path in (
        PARSE_INTENT, PARSE_RECEIPT, PARSE_RECEIPT_PIN
    )):
        raise ExecutionAuditError("parse provenance already exists")
    if Path(str(EXPERIMENT_PATH) + "-eval").exists():
        raise ExecutionAuditError("evaluation directory exists before parsing")
    if any(
        (_run_dir(run_id) / "properties").exists()
        for run_id in range(1, EXPECTED_CELLS + 1)
    ):
        raise ExecutionAuditError("parsed properties already exist")
    execution_sha, _ = load_execution_receipt(verify_live=True)
    _write_exclusive_json(
        PARSE_INTENT,
        {
            "schema": PARSE_INTENT_SCHEMA,
            "execution_receipt_sha256": execution_sha,
            "experiment_path": str(EXPERIMENT_PATH.resolve()),
            "expected_property_files": EXPECTED_CELLS,
        },
        "parse intent",
    )


def _load_parse_intent(execution_sha: str) -> tuple[str, dict]:
    raw, intent = _load_recovery_json(PARSE_INTENT, "parse intent")
    expected = {
        "schema": PARSE_INTENT_SCHEMA,
        "execution_receipt_sha256": execution_sha,
        "experiment_path": str(EXPERIMENT_PATH.resolve()),
        "expected_property_files": EXPECTED_CELLS,
    }
    if intent != expected:
        raise ExecutionAuditError("parse intent semantics changed")
    return hashlib.sha256(raw).hexdigest(), intent


def seal_parse() -> None:
    if PARSE_RECEIPT_PIN.exists() or PARSE_RECEIPT_PIN.is_symlink():
        raise ExecutionAuditError("parse receipt pin already exists")
    execution_sha, _ = load_execution_receipt(verify_live=True)
    intent_sha, _ = _load_parse_intent(execution_sha)
    tree_hash, files = _parsed_properties_tree_digest()
    digest = _write_exclusive_json(
        PARSE_RECEIPT,
        {
            "schema": PARSE_RECEIPT_SCHEMA,
            "parse_intent_sha256": intent_sha,
            "execution_receipt_sha256": execution_sha,
            "properties_tree_sha256": tree_hash,
            "property_files": files,
        },
        "parse receipt",
    )
    print("parse receipt SHA-256 to pin: {}".format(digest))


def load_parse_receipt(*, verify_live: bool = True) -> tuple[str, dict]:
    execution_sha, _ = load_execution_receipt(verify_live=verify_live)
    intent_sha, _ = _load_parse_intent(execution_sha)
    digest, receipt = _load_pinned_json(
        PARSE_RECEIPT, PARSE_RECEIPT_PIN, "parse receipt"
    )
    if (
        receipt != {
            "schema": PARSE_RECEIPT_SCHEMA,
            "parse_intent_sha256": intent_sha,
            "execution_receipt_sha256": execution_sha,
            "properties_tree_sha256": receipt.get("properties_tree_sha256"),
            "property_files": EXPECTED_CELLS,
        }
        or SHA256_RE.fullmatch(
            receipt.get("properties_tree_sha256", "")
        ) is None
    ):
        raise ExecutionAuditError("parse receipt semantics changed")
    if verify_live:
        tree_hash, files = _parsed_properties_tree_digest()
        if (
            tree_hash != receipt["properties_tree_sha256"]
            or files != receipt["property_files"]
        ):
            raise ExecutionAuditError("parsed properties bytes changed")
    return digest, receipt


def validate_before_fetch() -> None:
    if any(path.exists() or path.is_symlink() for path in (
        FETCH_INTENT, FETCH_RECEIPT, FETCH_RECEIPT_PIN
    )):
        raise ExecutionAuditError("fetch provenance already exists")
    if EVAL_PROPERTIES.parent.exists():
        raise ExecutionAuditError("evaluation directory already exists")
    parse_sha, _ = load_parse_receipt(verify_live=True)
    _write_exclusive_json(
        FETCH_INTENT,
        {
            "schema": FETCH_INTENT_SCHEMA,
            "parse_receipt_sha256": parse_sha,
            "properties_path": str(EVAL_PROPERTIES.resolve()),
            "expected_records": EXPECTED_CELLS,
        },
        "fetch intent",
    )


def _load_fetch_intent(parse_sha: str) -> tuple[str, dict]:
    raw, intent = _load_recovery_json(FETCH_INTENT, "fetch intent")
    expected = {
        "schema": FETCH_INTENT_SCHEMA,
        "parse_receipt_sha256": parse_sha,
        "properties_path": str(EVAL_PROPERTIES.resolve()),
        "expected_records": EXPECTED_CELLS,
    }
    if intent != expected:
        raise ExecutionAuditError("fetch intent semantics changed")
    return hashlib.sha256(raw).hexdigest(), intent


def seal_fetch() -> None:
    if FETCH_RECEIPT_PIN.exists() or FETCH_RECEIPT_PIN.is_symlink():
        raise ExecutionAuditError("fetch receipt pin already exists")
    parse_sha, _ = load_parse_receipt(verify_live=True)
    intent_sha, _ = _load_fetch_intent(parse_sha)
    if EVAL_PROPERTIES.is_symlink() or not EVAL_PROPERTIES.is_file():
        raise ExecutionAuditError("fetched properties are not a regular file")
    try:
        records = json.loads(EVAL_PROPERTIES.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ExecutionAuditError("cannot validate fetched properties") from err
    if not isinstance(records, dict) or len(records) != EXPECTED_CELLS:
        raise ExecutionAuditError("fetched properties matrix has wrong size")
    digest = _write_exclusive_json(
        FETCH_RECEIPT,
        {
            "schema": FETCH_RECEIPT_SCHEMA,
            "fetch_intent_sha256": intent_sha,
            "parse_receipt_sha256": parse_sha,
            "properties_path": str(EVAL_PROPERTIES.resolve()),
            "properties_sha256": _sha256_file(EVAL_PROPERTIES),
            "records": len(records),
        },
        "fetch receipt",
    )
    print("fetch receipt SHA-256 to pin: {}".format(digest))


def load_fetch_receipt(*, verify_live: bool = True) -> tuple[str, dict]:
    parse_sha, _ = load_parse_receipt(verify_live=verify_live)
    intent_sha, _ = _load_fetch_intent(parse_sha)
    digest, receipt = _load_pinned_json(
        FETCH_RECEIPT, FETCH_RECEIPT_PIN, "fetch receipt"
    )
    expected = {
        "schema": FETCH_RECEIPT_SCHEMA,
        "fetch_intent_sha256": intent_sha,
        "parse_receipt_sha256": parse_sha,
        "properties_path": str(EVAL_PROPERTIES.resolve()),
        "properties_sha256": receipt.get("properties_sha256"),
        "records": EXPECTED_CELLS,
    }
    if (
        receipt != expected
        or SHA256_RE.fullmatch(receipt.get("properties_sha256", "")) is None
    ):
        raise ExecutionAuditError("fetch receipt semantics changed")
    if verify_live and (
        EVAL_PROPERTIES.is_symlink()
        or not EVAL_PROPERTIES.is_file()
        or _sha256_file(EVAL_PROPERTIES) != receipt["properties_sha256"]
    ):
        raise ExecutionAuditError("fetched properties bytes changed")
    return digest, receipt


def make_status():
    launch = load_launch_receipt()
    tree_hash, run_files, property_files = _run_input_tree_digest()
    if (
        tree_hash != launch["generated_run_input_tree_sha256"]
        or run_files != EXPECTED_CELLS
        or property_files != EXPECTED_CELLS
    ):
        raise ExecutionAuditError("immutable generated run inputs changed")
    rows = scheduler_rows(launch["job_id"])
    recoveries = recovery_executions(launch)
    cell_counts, incomplete = cell_completeness()
    latest_by_task = {row["array_task"]: row for row in rows}
    for execution in recoveries:
        for row in execution["scheduler_rows"]:
            latest_by_task[row["array_task"]] = row
    primary_terminal = all(
        row["state"] in TERMINAL_SCHEDULER_STATES for row in rows
    )
    recovery_terminal = all(
        row["state"] in TERMINAL_SCHEDULER_STATES
        for execution in recoveries
        for row in execution["scheduler_rows"]
    )
    completed = sum(
        row["state"] == "COMPLETED" for row in latest_by_task.values()
    )
    successful = (
        primary_terminal
        and recovery_terminal
        and completed == EXPECTED_ARRAY_TASKS
    )
    return launch, rows, recoveries, {
        "scheduler_state_counts": dict(Counter(row["state"] for row in rows)),
        "scheduler_terminal": primary_terminal,
        "recovery_scheduler_terminal": recovery_terminal,
        "scheduler_all_completed": successful,
        "recovery_scheduler_state_counts": dict(Counter(
            row["state"]
            for execution in recoveries
            for row in execution["scheduler_rows"]
        )),
        "effectively_completed_array_tasks": completed,
        "cell_state_counts": cell_counts,
        "incomplete_cells": incomplete,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seal", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    launch, rows, recoveries, status = make_status()
    if not args.seal:
        public = dict(status)
        public["incomplete_cells"] = {
            "count": len(status["incomplete_cells"]),
            "first": status["incomplete_cells"][:20],
        }
        print(json.dumps(public, sort_keys=True, indent=2))
        return 0
    if not status["scheduler_all_completed"]:
        raise ExecutionAuditError(
            "cannot seal: not every latest Slurm array task completed"
        )
    if status["incomplete_cells"]:
        raise ExecutionAuditError("cannot seal: cell files are incomplete")
    if EXECUTION_RECEIPT.exists():
        raise ExecutionAuditError("execution receipt already exists")
    dynamic_hash, dynamic_files = dynamic_tree_digest()
    receipt = {
        "schema": EXECUTION_RECEIPT_SCHEMA,
        "launch_receipt_sha256": LAUNCH_RECEIPT_SHA256,
        "job_id": launch["job_id"],
        "array_throttle": 0,
        "partition": PARTITION,
        "scheduler_state_counts": status["scheduler_state_counts"],
        "cell_state_counts": status["cell_state_counts"],
        "scheduler_rows": rows,
        "recovery_executions": recoveries,
        "dynamic_cell_tree_sha256": dynamic_hash,
        "dynamic_cell_files": dynamic_files,
    }
    digest = _write_exclusive_json(
        EXECUTION_RECEIPT, receipt, "execution receipt"
    )
    print(
        "sealed {} complete cells from {} unthrottled fat tasks; "
        "receipt SHA-256 to pin: {}".format(
            EXPECTED_CELLS, EXPECTED_ARRAY_TASKS, digest
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (P.ProtocolError, JJ.JjCacheError, ExecutionAuditError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
