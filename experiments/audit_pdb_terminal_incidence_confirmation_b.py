#!/usr/bin/env python3
"""Seal Confirmation B raw, parsed, and fetched artifacts fail closed."""

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

import analyze_pdb_terminal_incidence_shadow as OriginalAnalyzer
import audit_pdb_terminal_incidence_shadow as Legacy
import exp_pdb_terminal_incidence_confirmation_b as Runner
import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_b_protocol as P


class ExecutionAuditError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
EXPERIMENT_PATH = Runner.EXPERIMENT_PATH
GRID_DIR = Runner.GRID_DIR
ARTIFACT_DIR = Runner.ARTIFACT_DIR
EXPECTED_CELLS = P.CELL_COUNT
EXPECTED_ARRAY_TASKS = P.EXPECTED_ARRAY_TASKS
RUNS_PER_ARRAY_TASK = P.RUNS_PER_ARRAY_TASK
PARTITION = "fat"
QOS = "normal"
SCHEDULER_TIME_LIMIT = P.SCHEDULER_TIME_LIMIT
SCHEDULER_MEMORY = P.SCHEDULER_MEMORY
EXPECTED_JOB_NAME = Runner.EXPECTED_JOB_NAME
EXECUTION_RECEIPT = ARTIFACT_DIR / "execution-receipt-v1.json"
EXECUTION_RECEIPT_PIN = ARTIFACT_DIR / "execution-receipt-v1.sha256"
EXECUTION_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-b-execution/v1"
)
PARSE_INTENT = ARTIFACT_DIR / "parse-intent-v1.json"
PARSE_RECEIPT = ARTIFACT_DIR / "parse-receipt-v1.json"
PARSE_RECEIPT_PIN = ARTIFACT_DIR / "parse-receipt-v1.sha256"
PARSE_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-b-parse/v1"
)
FETCH_INTENT = ARTIFACT_DIR / "fetch-intent-v1.json"
FETCH_RECEIPT = ARTIFACT_DIR / "fetch-receipt-v1.json"
FETCH_RECEIPT_PIN = ARTIFACT_DIR / "fetch-receipt-v1.sha256"
FETCH_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-b-fetch/v1"
)
EVAL_PROPERTIES = Path(str(EXPERIMENT_PATH) + "-eval") / "properties"
RECOVERY_ROOT = ARTIFACT_DIR / "recovery"
RECOVERY_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-b-recovery/v2"
)
INFRASTRUCTURE_STATES = frozenset({
    "BOOT_FAIL", "NODE_FAIL", "PREEMPTED", "REVOKED",
})
ACTIVE_STATES = frozenset({
    "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
    "RESIZING", "SUSPENDED",
})
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
RECOVERY_DYNAMIC_NAMES = frozenset(Runner.DYNAMIC_OUTPUT_NAMES)


def _translate_error(err: Exception) -> ExecutionAuditError:
    return ExecutionAuditError(str(err))


def _configure_legacy() -> None:
    try:
        launch_sha, _ = Runner.load_launch_receipt(verify_live=True)
    except Runner.ConfirmationLaunchError as err:
        raise _translate_error(err) from err
    Legacy.P = P
    Legacy.RECOVERY_DYNAMIC_NAMES = set(RECOVERY_DYNAMIC_NAMES)
    Legacy.EXPERIMENT_PATH = EXPERIMENT_PATH
    Legacy.GRID_DIR = GRID_DIR
    Legacy.EXPECTED_JOB_NAME = EXPECTED_JOB_NAME
    Legacy.EXPECTED_CELLS = EXPECTED_CELLS
    Legacy.RUNS_PER_ARRAY_TASK = RUNS_PER_ARRAY_TASK
    Legacy.EXPECTED_ARRAY_TASKS = EXPECTED_ARRAY_TASKS
    Legacy.SCHEDULER_TIME_LIMIT = SCHEDULER_TIME_LIMIT
    Legacy.SCHEDULER_MEMORY = SCHEDULER_MEMORY
    Legacy.PARTITION = PARTITION
    Legacy.QOS = QOS
    Legacy.LAUNCH_RECEIPT = Runner.LAUNCH_RECEIPT
    Legacy.LAUNCH_INTENT = Runner.LAUNCH_INTENT
    Legacy.BUILD_RECEIPT = Runner.BUILD_RECEIPT
    Legacy.LAUNCH_RECEIPT_PIN = Runner.LAUNCH_RECEIPT_PIN
    Legacy.LAUNCH_RECEIPT_SHA256 = launch_sha
    Legacy.LAUNCH_RECEIPT_SCHEMA = Runner.LAUNCH_SCHEMA
    Legacy.EXECUTION_RECEIPT = EXECUTION_RECEIPT
    Legacy.EXECUTION_RECEIPT_PIN = EXECUTION_RECEIPT_PIN
    Legacy.EXECUTION_RECEIPT_SCHEMA = EXECUTION_SCHEMA
    Legacy.PARSE_INTENT = PARSE_INTENT
    Legacy.PARSE_RECEIPT = PARSE_RECEIPT
    Legacy.PARSE_RECEIPT_PIN = PARSE_RECEIPT_PIN
    Legacy.PARSE_RECEIPT_SCHEMA = PARSE_SCHEMA
    Legacy.PARSE_INTENT_SCHEMA = PARSE_SCHEMA + "/intent"
    Legacy.FETCH_INTENT = FETCH_INTENT
    Legacy.FETCH_RECEIPT = FETCH_RECEIPT
    Legacy.FETCH_RECEIPT_PIN = FETCH_RECEIPT_PIN
    Legacy.FETCH_RECEIPT_SCHEMA = FETCH_SCHEMA
    Legacy.FETCH_INTENT_SCHEMA = FETCH_SCHEMA + "/intent"
    Legacy.EVAL_PROPERTIES = EVAL_PROPERTIES
    Legacy.RECOVERY_RECEIPT_SCHEMA = RECOVERY_SCHEMA + "/launch"
    Legacy.RECOVERY_INTENT_SCHEMA = RECOVERY_SCHEMA + "/launch/intent"
    Legacy.load_launch_receipt = _legacy_load_launch_receipt
    Legacy.load_execution_receipt = _legacy_load_execution_receipt
    Legacy._validate_live_sources = _legacy_validate_live_sources
    Legacy.recovery_executions = _legacy_recovery_executions
    Legacy.make_status = _legacy_make_status
    Legacy.cell_completeness = _legacy_cell_completeness


def _legacy_load_launch_receipt() -> dict:
    try:
        return Runner.load_launch_receipt(verify_live=True)[1]
    except Runner.ConfirmationLaunchError as err:
        raise Legacy.ExecutionAuditError(str(err)) from err


def _legacy_load_execution_receipt(
    *, verify_live: bool = True
) -> tuple[str, dict]:
    try:
        return load_execution_receipt(verify_live=verify_live)
    except ExecutionAuditError as err:
        raise Legacy.ExecutionAuditError(str(err)) from err


def _legacy_validate_live_sources(source_hashes: dict) -> None:
    try:
        expected_names = Runner._source_names()
    except (Runner.ConfirmationLaunchError, P.ProtocolError) as err:
        raise Legacy.ExecutionAuditError(str(err)) from err
    if (
        not isinstance(source_hashes, dict)
        or set(source_hashes) != set(expected_names)
    ):
        raise Legacy.ExecutionAuditError(
            "Confirmation B launch receipt source set changed"
        )
    for name, expected in source_hashes.items():
        relative = Path(name)
        if (
            relative.is_absolute()
            or ".." in relative.parts
            or SHA256_RE.fullmatch(expected or "") is None
        ):
            raise Legacy.ExecutionAuditError(
                "Confirmation B launch receipt source path changed"
            )
        path = SCRIPT_DIR / relative
        try:
            actual = P.sha256_file(path)
        except P.ProtocolError as err:
            raise Legacy.ExecutionAuditError(str(err)) from err
        if actual != expected:
            raise Legacy.ExecutionAuditError(
                "Confirmation B executed source changed: {}".format(name)
            )


def _canonical_load(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        loaded, value = SafeIO.read_canonical_json(
            Path(path), label=label, canonical_json_line=P.canonical_json_line
        )
    except SafeIO.SafeReadError as err:
        raise ExecutionAuditError(str(err)) from err
    return loaded.raw, value


def _write_pin(path: Path, digest: str, label: str) -> None:
    if SHA256_RE.fullmatch(digest or "") is None:
        raise ExecutionAuditError("{} digest is invalid".format(label))
    try:
        with path.open("xb") as stream:
            stream.write((digest + "\n").encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise ExecutionAuditError("{} pin already exists".format(label)) from err


def _task_cells(array_task: int) -> range:
    if type(array_task) is not int or not 1 <= array_task <= EXPECTED_ARRAY_TASKS:
        raise ExecutionAuditError("array task is out of range")
    first = (array_task - 1) * RUNS_PER_ARRAY_TASK + 1
    return range(first, min(first + RUNS_PER_ARRAY_TASK, EXPECTED_CELLS + 1))


def scheduler_rows(job_id: str, expected_tasks=None) -> list[dict]:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise ExecutionAuditError("Slurm job id is invalid")
    if expected_tasks is None:
        expected_tasks = set(range(1, EXPECTED_ARRAY_TASKS + 1))
    else:
        expected_tasks = set(expected_tasks)
    if not expected_tasks or any(
        type(task) is not int or not 1 <= task <= EXPECTED_ARRAY_TASKS
        for task in expected_tasks
    ):
        raise ExecutionAuditError("expected Slurm task set is invalid")
    try:
        Runner._executable_identity(
            Runner.SACCT_COMMAND, Runner.SACCT_COMMAND_SHA256, "sacct"
        )
        output = subprocess.check_output(
            [str(Runner.SACCT_COMMAND), "-j", job_id, "-X", "-n", "-P",
             "-o", "JobID,JobIDRaw,State,ExitCode,NodeList,ElapsedRaw,Partition"],
            env=dict(Runner.SUBMISSION_ENVIRONMENT), text=True,
        )
    except (OSError, subprocess.CalledProcessError, Runner.ConfirmationLaunchError) as err:
        raise ExecutionAuditError("cannot query pinned Slurm accounting") from err
    rows = {}
    prefix = job_id + "_"
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 7:
            raise ExecutionAuditError("unexpected sacct row shape")
        array_id, raw_id, state, exit_code, node, elapsed, partition = fields
        if not array_id.startswith(prefix) or not array_id[len(prefix):].isdigit():
            continue
        task = int(array_id[len(prefix):])
        state = state.split("+", 1)[0].split()[0]
        if task in rows or task not in expected_tasks or partition != PARTITION:
            raise ExecutionAuditError("Slurm accounting task identity changed")
        rows[task] = {
            "array_task": task, "job_id_raw": raw_id, "state": state,
            "exit_code": exit_code, "node": node, "elapsed_raw": elapsed,
            "partition": partition,
        }
    if set(rows) != expected_tasks:
        raise ExecutionAuditError("Slurm accounting task set is incomplete")
    return [rows[task] for task in sorted(rows)]


def scheduler_contract_rows(
    job_id: str, job_name: str, scheduler: list[dict], expected_tasks=None
) -> list[dict]:
    expected_tasks = (
        set(range(1, EXPECTED_ARRAY_TASKS + 1))
        if expected_tasks is None else set(expected_tasks)
    )
    try:
        Runner._executable_identity(
            Runner.SACCT_COMMAND, Runner.SACCT_COMMAND_SHA256, "sacct"
        )
        output = subprocess.check_output(
            [str(Runner.SACCT_COMMAND), "-j", job_id, "-X", "-n", "-P",
             "--format=JobID,Account,Partition,QOS,ReqCPUS,ReqMem,"
             "Timelimit,State,ExitCode,JobName"],
            env=dict(Runner.SUBMISSION_ENVIRONMENT), text=True,
        )
    except (OSError, subprocess.CalledProcessError, Runner.ConfirmationLaunchError) as err:
        raise ExecutionAuditError("cannot query actual resource accounting") from err
    scheduler_by_task = {row["array_task"]: row for row in scheduler}
    rows = {}
    prefix = job_id + "_"
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 10:
            raise ExecutionAuditError("actual resource row shape changed")
        (array_id, account, partition, qos, req_cpus, req_mem,
         time_limit, state, exit_code, actual_name) = fields
        if not array_id.startswith(prefix) or not array_id[len(prefix):].isdigit():
            continue
        task = int(array_id[len(prefix):])
        state = state.split("+", 1)[0].split()[0]
        if (
            task in rows or task not in expected_tasks
            or account != P.ACCOUNT or partition != PARTITION or qos != QOS
            or req_cpus != "1" or req_mem != SCHEDULER_MEMORY
            or time_limit != SCHEDULER_TIME_LIMIT or actual_name != job_name
            or scheduler_by_task.get(task, {}).get("state") != state
            or scheduler_by_task.get(task, {}).get("exit_code") != exit_code
        ):
            raise ExecutionAuditError("actual resource contract changed")
        rows[task] = {
            "array_task": task, "account": account, "partition": partition,
            "qos": qos, "req_cpus": 1, "req_mem": req_mem,
            "time_limit": time_limit, "state": state,
            "exit_code": exit_code, "job_name": actual_name,
        }
    if set(rows) != expected_tasks:
        raise ExecutionAuditError("actual resource accounting is incomplete")
    return [rows[task] for task in sorted(rows)]


def _row_class(row: dict) -> str:
    state = row.get("state")
    exit_code = row.get("exit_code")
    if state == "COMPLETED" and exit_code == "0:0":
        return "successful"
    if state in INFRASTRUCTURE_STATES:
        return "recoverable"
    if state in ACTIVE_STATES:
        return "active"
    raise ExecutionAuditError(
        "array task {} has nonrecoverable scheduler outcome {} {}".format(
            row.get("array_task"), state, exit_code
        )
    )


def _wave_number(path: Path) -> int:
    match = re.fullmatch(r"wave-(\d{4})", path.name)
    if match is None or int(match.group(1)) < 1:
        raise ExecutionAuditError("recovery wave directory is malformed")
    return int(match.group(1))


def _validate_archive(wave_dir: Path, plan: list[dict], cells: list[int]) -> None:
    if (
        not isinstance(plan, list)
        or not isinstance(cells, list)
        or cells != sorted(set(cells))
        or any(type(cell) is not int or not 1 <= cell <= EXPECTED_CELLS
               for cell in cells)
    ):
        raise ExecutionAuditError("recovery archive plan is malformed")
    seen = set()
    expected_targets = set()
    for item in plan:
        if not isinstance(item, dict):
            raise ExecutionAuditError("recovery archive item is malformed")
        run_id = item.get("run_id")
        name = item.get("name")
        if (
            set(item) != {
                "run_id", "name", "source", "target", "size", "sha256",
                "identity",
            }
            or type(run_id) is not int
            or not isinstance(name, str)
        ):
            raise ExecutionAuditError("recovery archive item changed")
        lower = ((run_id - 1) // 100) * 100 + 1
        expected_source = (
            Path("runs-{:05d}-{:05d}".format(lower, lower + 99))
            / "{:05d}".format(run_id) / name
        )
        expected_target = (
            Path("interrupted-cell-files") / "{:05d}".format(run_id) / str(name)
        )
        if any((
            run_id not in cells,
            name not in RECOVERY_DYNAMIC_NAMES,
            item.get("source") != expected_source.as_posix(),
            item.get("target") != expected_target.as_posix(),
            not isinstance(item.get("size"), int),
            item.get("size", -1) < 0,
            SHA256_RE.fullmatch(item.get("sha256", "")) is None,
            not isinstance(item.get("identity"), dict),
            set(item.get("identity", {})) != {
                "device", "inode", "mode", "size", "mtime_ns",
            },
            any(
                type(item.get("identity", {}).get(field)) is not int
                or item["identity"][field] < 0
                for field in ("device", "inode", "mode", "size", "mtime_ns")
            ) if isinstance(item.get("identity"), dict) else True,
            not stat.S_ISREG(item.get("identity", {}).get("mode", 0)),
            item.get("identity", {}).get("size") != item.get("size"),
            (run_id, name) in seen,
        )):
            raise ExecutionAuditError("recovery archive item changed")
        seen.add((run_id, name))
        expected_targets.add(expected_target.as_posix())
        target = wave_dir / expected_target
        try:
            loaded = SafeIO.read_regular_file(
                target, label="recovery archive target", root=wave_dir
            )
        except SafeIO.SafeReadError as err:
            raise ExecutionAuditError("recovery archive bytes changed") from err
        if loaded.sha256 != item["sha256"] or loaded.identity != item["identity"]:
            raise ExecutionAuditError("recovery archive bytes changed")
    archive_root = wave_dir / "interrupted-cell-files"
    try:
        root_info = archive_root.lstat()
    except FileNotFoundError:
        if expected_targets:
            raise ExecutionAuditError("recovery archive tree is incomplete")
        return
    except OSError as err:
        raise ExecutionAuditError("cannot inspect recovery archive tree") from err
    if not stat.S_ISDIR(root_info.st_mode):
        raise ExecutionAuditError("recovery archive root is invalid")
    actual_targets = set()
    for directory, dirnames, filenames in os.walk(archive_root, followlinks=False):
        parent = Path(directory)
        for name in dirnames:
            try:
                info = (parent / name).lstat()
            except OSError as err:
                raise ExecutionAuditError("recovery archive tree changed") from err
            if not stat.S_ISDIR(info.st_mode):
                raise ExecutionAuditError("recovery archive directory is invalid")
        for name in filenames:
            path = parent / name
            try:
                info = path.lstat()
            except OSError as err:
                raise ExecutionAuditError("recovery archive tree changed") from err
            if not stat.S_ISREG(info.st_mode):
                raise ExecutionAuditError("recovery archive target is not regular")
            actual_targets.add(path.relative_to(wave_dir).as_posix())
    if actual_targets != expected_targets:
        raise ExecutionAuditError("recovery archive tree changed")


def _output_tree(wave_dir: Path, job_id: str, tasks: list[int]) -> dict:
    paths = []
    for task in tasks:
        paths.extend((
            wave_dir / "slurm-{}_{}.out".format(job_id, task),
            wave_dir / "slurm-{}_{}.err".format(job_id, task),
        ))
    if any(not path.exists() for path in paths):
        return {"complete": False, "files": None, "sha256": None}
    digest = hashlib.sha256()
    records = []
    for path in sorted(paths):
        if path.is_symlink() or not path.is_file():
            raise ExecutionAuditError("recovery output is not regular")
        relative = path.relative_to(wave_dir).as_posix()
        sha = P.sha256_file(path)
        digest.update(relative.encode("ascii") + b"\0" + bytes.fromhex(sha))
        records.append({
            "path": relative,
            "size": path.stat().st_size,
            "sha256": sha,
        })
    return {"complete": True, "files": records, "sha256": digest.hexdigest()}


def _expected_recovery_command(
    wave_dir: Path, wave: int, tasks: list[int], token: str
) -> tuple[list[str], str]:
    if re.fullmatch(r"[0-9a-f]{24}", token or "") is None:
        raise ExecutionAuditError("recovery submission token is invalid")
    array_spec = ",".join(map(str, tasks))
    name = "pdb-incidence-confirm-b-recovery-{:04d}".format(wave)
    comment = "pdb-incidence-confirm-b-recovery/{}/{}".format(wave, token)
    return ([
        str(Runner.SBATCH_COMMAND), "--parsable", "--export=NONE", "--no-requeue",
        "--array={}".format(array_spec),
        "--job-name={}".format(name),
        "--comment={}".format(comment),
        "--output={}".format(
            (wave_dir / "slurm-%A_%a.out").resolve()
        ),
        "--error={}".format(
            (wave_dir / "slurm-%A_%a.err").resolve()
        ),
        "--partition=fat", "--qos=normal",
        "--time={}".format(P.SCHEDULER_TIME_LIMIT),
        "--mem-per-cpu={}".format(P.SCHEDULER_MEMORY),
        "--cpus-per-task=1", "--nodes=1", "--ntasks=1",
        "--account={}".format(P.ACCOUNT),
        "--chdir={}".format(Runner.GRID_DIR.resolve()),
        "--open-mode=append", "--mail-type=NONE", "--mail-user=",
    ], comment)


def recovery_executions(
    launch: dict, original_rows: list[dict] | None = None
) -> list[dict]:
    if original_rows is None:
        original_rows = scheduler_rows(launch["job_id"])
    latest = {row["array_task"]: row for row in original_rows}
    try:
        recovery_info = RECOVERY_ROOT.lstat()
    except FileNotFoundError:
        return []
    except OSError as err:
        raise ExecutionAuditError("cannot inspect recovery root") from err
    if not stat.S_ISDIR(recovery_info.st_mode):
        raise ExecutionAuditError("recovery root is invalid")
    executions = []
    expected_wave = 1
    for wave_dir in sorted(RECOVERY_ROOT.iterdir()):
        wave = _wave_number(wave_dir)
        try:
            wave_info = wave_dir.lstat()
        except OSError as err:
            raise ExecutionAuditError("cannot inspect recovery wave") from err
        if wave != expected_wave or not stat.S_ISDIR(wave_info.st_mode):
            raise ExecutionAuditError("recovery wave sequence changed")
        expected_wave += 1
        intent_path = wave_dir / "launch-intent.json"
        receipt_path = wave_dir / "launch-receipt.json"
        intent_raw, intent = _canonical_load(intent_path, "recovery launch intent")
        receipt_raw, receipt = _canonical_load(receipt_path, "recovery launch receipt")
        try:
            Runner._validate_recorded_utc(intent.get("recorded_utc"))
        except Runner.ConfirmationLaunchError as err:
            raise ExecutionAuditError(
                "recovery submission timestamp changed"
            ) from err
        tasks = receipt.get("array_tasks")
        cells = receipt.get("recoverable_cells")
        if (
            not isinstance(tasks, list)
            or not tasks
            or tasks != sorted(set(tasks))
            or any(type(task) is not int or not 1 <= task <= EXPECTED_ARRAY_TASKS
                   for task in tasks)
            or not isinstance(cells, list)
            or cells != sorted(set(cells))
            or any(type(cell) is not int or not 1 <= cell <= EXPECTED_CELLS
                   for cell in cells)
        ):
            raise ExecutionAuditError("recovery task or cell set is invalid")
        source_rows = [latest[task] for task in tasks]
        if any(_row_class(row) != "recoverable" for row in source_rows):
            raise ExecutionAuditError("recovery includes a non-interrupted task")
        all_recoverable = sorted(
            task for task, row in latest.items()
            if _row_class(row) == "recoverable"
        )
        if tasks != all_recoverable:
            raise ExecutionAuditError("recovery selectively omitted interrupted tasks")
        expected_cells = sorted(
            cell for task in tasks for cell in _task_cells(task)
        )
        if cells != expected_cells:
            raise ExecutionAuditError("recovery cell mapping changed")
        expected_command, expected_comment = _expected_recovery_command(
            wave_dir, wave, tasks, receipt.get("submission_token")
        )
        common = {
            "wave": wave,
            "source_job_id": launch["job_id"],
            "source_launch_receipt_sha256": Runner.load_launch_receipt()[0],
            "source_job_file_sha256": launch["job_file_sha256"],
            "source_latest_scheduler_rows": source_rows,
            "array_tasks": tasks,
            "array_spec": ",".join(map(str, tasks)),
            "array_throttle": 0,
            "partition": PARTITION,
            "qos": QOS,
            "account": P.ACCOUNT,
            "cpus_per_task": 1,
            "memory_per_cpu": SCHEDULER_MEMORY,
            "time_limit": SCHEDULER_TIME_LIMIT,
            "runs_per_array_task": RUNS_PER_ARRAY_TASK,
            "run_order_protocol": P.RUN_ORDER_PROTOCOL,
            "run_cell_mapping_sha256": P.RUN_CELL_MAPPING_SHA256,
            "cells": EXPECTED_CELLS,
            "recoverable_cells": cells,
            "submission_export": "NONE",
            "slurm_submission_mode": "stdin",
            "slurm_stdin_sha256": launch["slurm_stdin_sha256"],
            "slurm_stdin_bytes": launch["slurm_stdin_bytes"],
            "slurm_path_argument": False,
            "submission_journal_contract": "exact sbatch options-only SubmitLine",
            "sbatch_executable": str(Runner.SBATCH_COMMAND),
            "sbatch_executable_sha256": Runner.SBATCH_COMMAND_SHA256,
            "sacct_executable": str(Runner.SACCT_COMMAND),
            "sacct_executable_sha256": Runner.SACCT_COMMAND_SHA256,
            "submission_environment": dict(Runner.SUBMISSION_ENVIRONMENT),
            "nice_adjustment": None,
            "requeue": False,
            "submission_token": receipt.get("submission_token"),
            "submission_comment": expected_comment,
            "submit_command": expected_command,
        }
        expected_intent = {
            "schema": RECOVERY_SCHEMA + "/launch/intent",
            "recorded_utc": intent.get("recorded_utc"),
            **common,
            "archive_plan": intent.get("archive_plan"),
        }
        expected_receipt = {
            "schema": RECOVERY_SCHEMA + "/launch",
            "recorded_utc": intent.get("recorded_utc"),
            **common,
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": receipt.get("job_id"),
            "archived_interrupted_files": intent.get("archive_plan"),
        }
        if (
            intent != expected_intent
            or receipt != expected_receipt
            or not isinstance(receipt.get("job_id"), str)
            or not receipt["job_id"].isdigit()
            or re.fullmatch(r"[0-9a-f]{24}", receipt.get("submission_token", ""))
            is None
        ):
            raise ExecutionAuditError("recovery launch provenance changed")
        _validate_archive(wave_dir, intent["archive_plan"], cells)
        rows = scheduler_rows(receipt["job_id"], set(tasks))
        contract_rows = scheduler_contract_rows(
            receipt["job_id"],
            "pdb-incidence-confirm-b-recovery-{:04d}".format(wave),
            rows, set(tasks),
        )
        output_tree = _output_tree(wave_dir, receipt["job_id"], tasks)
        if all(_row_class(row) != "active" for row in rows) and not output_tree["complete"]:
            raise ExecutionAuditError("terminal recovery lacks complete Slurm logs")
        executions.append({
            "wave": wave,
            "intent_path": intent_path.relative_to(SCRIPT_DIR).as_posix(),
            "intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "receipt_path": receipt_path.relative_to(SCRIPT_DIR).as_posix(),
            "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
            "receipt": receipt,
            "scheduler_rows": rows,
            "scheduler_contract_rows": contract_rows,
            "output_tree": output_tree,
        })
        for row in rows:
            latest[row["array_task"]] = row
    return executions


def _legacy_recovery_executions(launch: dict) -> list[dict]:
    try:
        return recovery_executions(launch)
    except ExecutionAuditError as err:
        raise Legacy.ExecutionAuditError(str(err)) from err


def _run_directory(run_id: int) -> Path:
    lower = ((run_id - 1) // 100) * 100 + 1
    return (
        EXPERIMENT_PATH /
        "runs-{:05d}-{:05d}".format(lower, lower + 99) /
        "{:05d}".format(run_id)
    )


def cell_completeness() -> tuple[dict[str, int], list[int]]:
    counts = Counter()
    incomplete = []
    for run_id in range(1, EXPECTED_CELLS + 1):
        path = _run_directory(run_id) / "driver.log"
        try:
            path.lstat()
        except FileNotFoundError:
            state = "missing"
        except OSError as err:
            raise ExecutionAuditError("cannot inspect driver completeness") from err
        else:
            try:
                loaded = SafeIO.read_regular_file(
                    path, label="driver completeness marker",
                    root=EXPERIMENT_PATH,
                )
                lines = loaded.raw.decode("utf-8").splitlines()
            except (SafeIO.SafeReadError, UnicodeDecodeError) as err:
                raise ExecutionAuditError(
                    "driver completeness marker is not a stable regular file"
                ) from err
            state = (
                "complete"
                if lines and Legacy.DRIVER_TERMINAL_RE.fullmatch(lines[-1])
                else "interrupted"
            )
        counts[state] += 1
        if state != "complete":
            incomplete.append(run_id)
    return dict(counts), incomplete


def _legacy_cell_completeness():
    try:
        return cell_completeness()
    except ExecutionAuditError as err:
        raise Legacy.ExecutionAuditError(str(err)) from err


def make_status() -> tuple[dict, list[dict], list[dict], dict]:
    try:
        launch_sha, launch = Runner.load_launch_receipt(verify_live=True)
        del launch_sha
        tree_hash, run_files, property_files = Legacy._run_input_tree_digest()
    except (Runner.ConfirmationLaunchError, Legacy.ExecutionAuditError) as err:
        raise _translate_error(err) from err
    if any((
        tree_hash != launch["generated_run_input_tree_sha256"],
        run_files != EXPECTED_CELLS,
        property_files != EXPECTED_CELLS,
    )):
        raise ExecutionAuditError("immutable generated inputs changed")
    rows = scheduler_rows(launch["job_id"])
    recoveries = recovery_executions(launch, rows)
    latest = {row["array_task"]: row for row in rows}
    for execution in recoveries:
        for row in execution["scheduler_rows"]:
            latest[row["array_task"]] = row
    classes = {task: _row_class(row) for task, row in latest.items()}
    try:
        cell_counts, incomplete = cell_completeness()
    except ExecutionAuditError as err:
        raise _translate_error(err) from err
    incomplete_set = set(incomplete)
    for task, row_class in classes.items():
        task_incomplete = incomplete_set.intersection(_task_cells(task))
        if row_class == "successful" and task_incomplete:
            raise ExecutionAuditError(
                "successful array task has incomplete cells; recovery is forbidden"
            )
    terminal = all(value != "active" for value in classes.values())
    successful = all(value == "successful" for value in classes.values())
    return launch, rows, recoveries, {
        "scheduler_state_counts": dict(Counter(row["state"] for row in rows)),
        "scheduler_terminal": terminal,
        "scheduler_all_completed": successful,
        "effectively_completed_array_tasks": sum(
            value == "successful" for value in classes.values()
        ),
        "recoverable_array_tasks": sorted(
            task for task, value in classes.items() if value == "recoverable"
        ),
        "active_array_tasks": sorted(
            task for task, value in classes.items() if value == "active"
        ),
        "cell_state_counts": cell_counts,
        "incomplete_cells": incomplete,
    }


def _legacy_make_status():
    try:
        return make_status()
    except ExecutionAuditError as err:
        raise Legacy.ExecutionAuditError(str(err)) from err


def _live_execution_value() -> dict:
    launch_sha, launch = Runner.load_launch_receipt(verify_live=True)
    launch_live, rows, recoveries, status = make_status()
    if launch_live != launch:
        raise ExecutionAuditError("launch changed while pinning execution")
    contract_rows = scheduler_contract_rows(
        launch["job_id"], launch["job_name"], rows
    )
    dynamic_hash, dynamic_files = Legacy.dynamic_tree_digest()
    value = {
        "schema": EXECUTION_SCHEMA,
        "launch_receipt_sha256": launch_sha,
        "job_id": launch["job_id"],
        "array_throttle": 0,
        "partition": PARTITION,
        "scheduler_state_counts": status["scheduler_state_counts"],
        "cell_state_counts": status["cell_state_counts"],
        "scheduler_rows": rows,
        "scheduler_contract_rows": contract_rows,
        "recovery_executions": recoveries,
        "dynamic_cell_tree_sha256": dynamic_hash,
        "dynamic_cell_files": dynamic_files,
    }
    if not status["scheduler_all_completed"] or status["incomplete_cells"]:
        raise ExecutionAuditError("execution receipt does not seal a complete matrix")
    return value


def _pin_execution() -> str:
    if EXECUTION_RECEIPT_PIN.exists() or EXECUTION_RECEIPT_PIN.is_symlink():
        raise ExecutionAuditError("execution receipt pin already exists")
    raw, receipt = _canonical_load(EXECUTION_RECEIPT, "execution receipt")
    if receipt != _live_execution_value():
        raise ExecutionAuditError("execution receipt does not seal a complete matrix")
    digest = hashlib.sha256(raw).hexdigest()
    _write_pin(EXECUTION_RECEIPT_PIN, digest, "execution receipt")
    return digest


def seal_execution() -> str:
    _configure_legacy()
    if not EXECUTION_RECEIPT.exists():
        Runner._exclusive_json(
            EXECUTION_RECEIPT, _live_execution_value(), "execution receipt"
        )
    return _pin_execution()


def load_execution_receipt(*, verify_live: bool = True) -> tuple[str, dict]:
    _configure_legacy()
    try:
        raw, receipt = _canonical_load(EXECUTION_RECEIPT, "execution receipt")
        pin = SafeIO.read_regular_file(
            EXECUTION_RECEIPT_PIN, label="execution receipt pin"
        ).raw
    except (OSError, SafeIO.SafeReadError) as err:
        raise ExecutionAuditError("execution receipt is not pinned") from err
    digest = hashlib.sha256(raw).hexdigest()
    launch_sha, launch = Runner.load_launch_receipt(verify_live=verify_live)
    expected_keys = {
        "schema", "launch_receipt_sha256", "job_id", "array_throttle",
        "partition", "scheduler_state_counts", "cell_state_counts",
        "scheduler_rows", "scheduler_contract_rows", "recovery_executions",
        "dynamic_cell_tree_sha256", "dynamic_cell_files",
    }
    if (
        pin != (digest + "\n").encode("ascii")
        or set(receipt) != expected_keys
        or receipt.get("schema") != EXECUTION_SCHEMA
        or receipt.get("launch_receipt_sha256") != launch_sha
        or receipt.get("job_id") != launch["job_id"]
        or not P._same_exact(receipt.get("array_throttle"), 0)
        or receipt.get("partition") != PARTITION
        or receipt.get("cell_state_counts") != {"complete": EXPECTED_CELLS}
        or SHA256_RE.fullmatch(receipt.get("dynamic_cell_tree_sha256", "")) is None
        or type(receipt.get("dynamic_cell_files")) is not int
        or receipt["dynamic_cell_files"] < EXPECTED_CELLS
    ):
        raise ExecutionAuditError("execution receipt semantics changed")
    if verify_live and receipt != _live_execution_value():
        raise ExecutionAuditError("sealed scheduler/recovery state changed")
    return digest, receipt


def validate_before_parse() -> None:
    _configure_legacy()
    load_execution_receipt(verify_live=True)
    try:
        Legacy.validate_before_parse()
    except Legacy.ExecutionAuditError as err:
        raise _translate_error(err) from err


def _pin_parse() -> str:
    if PARSE_RECEIPT_PIN.exists() or PARSE_RECEIPT_PIN.is_symlink():
        raise ExecutionAuditError("parse receipt pin already exists")
    execution_sha, _ = load_execution_receipt(verify_live=True)
    try:
        intent_sha, _ = Legacy._load_parse_intent(execution_sha)
        tree_hash, files = Legacy._parsed_properties_tree_digest()
    except Legacy.ExecutionAuditError as err:
        raise _translate_error(err) from err
    raw, receipt = _canonical_load(PARSE_RECEIPT, "parse receipt")
    expected = {
        "schema": PARSE_SCHEMA,
        "parse_intent_sha256": intent_sha,
        "execution_receipt_sha256": execution_sha,
        "properties_tree_sha256": tree_hash,
        "property_files": files,
    }
    if receipt != expected or files != EXPECTED_CELLS:
        raise ExecutionAuditError("parse receipt does not seal the full matrix")
    digest = hashlib.sha256(raw).hexdigest()
    _write_pin(PARSE_RECEIPT_PIN, digest, "parse receipt")
    return digest


def seal_parse() -> None:
    _configure_legacy()
    if not PARSE_RECEIPT.exists():
        try:
            Legacy.seal_parse()
        except Legacy.ExecutionAuditError as err:
            raise _translate_error(err) from err
    _pin_parse()


def load_parse_receipt(*, verify_live: bool = True) -> tuple[str, dict]:
    _configure_legacy()
    try:
        return Legacy.load_parse_receipt(verify_live=verify_live)
    except Legacy.ExecutionAuditError as err:
        raise _translate_error(err) from err


def validate_before_fetch() -> None:
    _configure_legacy()
    load_parse_receipt(verify_live=True)
    try:
        Legacy.validate_before_fetch()
    except Legacy.ExecutionAuditError as err:
        raise _translate_error(err) from err


def _sealed_properties_sha256() -> str:
    try:
        loaded = SafeIO.read_regular_file(
            EVAL_PROPERTIES,
            label="sealed Confirmation B properties",
            expected_path=EVAL_PROPERTIES,
        )
    except SafeIO.SafeReadError as err:
        raise ExecutionAuditError(
            "cannot read sealed Confirmation B properties"
        ) from err
    return loaded.sha256


def _pin_fetch() -> str:
    if FETCH_RECEIPT_PIN.exists() or FETCH_RECEIPT_PIN.is_symlink():
        raise ExecutionAuditError("fetch receipt pin already exists")
    parse_sha, _ = load_parse_receipt(verify_live=True)
    try:
        intent_sha, _ = Legacy._load_fetch_intent(parse_sha)
    except Legacy.ExecutionAuditError as err:
        raise _translate_error(err) from err
    raw, receipt = _canonical_load(FETCH_RECEIPT, "fetch receipt")
    expected = {
        "schema": FETCH_SCHEMA,
        "fetch_intent_sha256": intent_sha,
        "parse_receipt_sha256": parse_sha,
        "properties_path": str(EVAL_PROPERTIES.resolve()),
        "properties_sha256": _sealed_properties_sha256(),
        "records": EXPECTED_CELLS,
    }
    if receipt != expected:
        raise ExecutionAuditError("fetch receipt does not seal the full matrix")
    digest = hashlib.sha256(raw).hexdigest()
    _write_pin(FETCH_RECEIPT_PIN, digest, "fetch receipt")
    return digest


def seal_fetch() -> None:
    _configure_legacy()
    _sealed_properties_sha256()
    if not FETCH_RECEIPT.exists():
        try:
            Legacy.seal_fetch()
        except Legacy.ExecutionAuditError as err:
            raise _translate_error(err) from err
    _pin_fetch()


def load_fetch_receipt(*, verify_live: bool = True) -> tuple[str, dict]:
    _configure_legacy()
    try:
        loaded = Legacy.load_fetch_receipt(verify_live=verify_live)
    except Legacy.ExecutionAuditError as err:
        raise _translate_error(err) from err
    if verify_live:
        digest = _sealed_properties_sha256()
        receipt = loaded[1]
        if (
            receipt.get("properties_path") != str(EVAL_PROPERTIES.resolve())
            or receipt.get("properties_sha256") != digest
        ):
            raise ExecutionAuditError(
                "fetch receipt does not bind the sealed Confirmation B input"
            )
    return loaded


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "status", "seal", "recover-seal", "recover-parse-seal",
            "recover-fetch-seal",
        ),
    )
    args = parser.parse_args(argv)
    _configure_legacy()
    if args.command == "status":
        _, _, _, status = make_status()
        public = dict(status)
        public["incomplete_cells"] = {
            "count": len(status["incomplete_cells"]),
            "first": status["incomplete_cells"][:20],
        }
        print(json.dumps(public, sort_keys=True, indent=2))
    elif args.command in ("seal", "recover-seal"):
        print(json.dumps({
            "execution_receipt_sha256": seal_execution()
        }, sort_keys=True, indent=2))
    elif args.command == "recover-parse-seal":
        print(json.dumps({"parse_receipt_sha256": _pin_parse()}, indent=2))
    else:
        print(json.dumps({"fetch_receipt_sha256": _pin_fetch()}, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ExecutionAuditError,
        Runner.ConfirmationLaunchError,
        P.ProtocolError,
        Legacy.ExecutionAuditError,
        OriginalAnalyzer.TerminalIncidenceAnalysisError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
