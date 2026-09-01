#!/usr/bin/env python3
"""Scheduler-array recovery with exact whole-triad archive accounting."""

from __future__ import annotations

import argparse
import copy
import fcntl
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_transport as Transport


class RecoveryError(RuntimeError):
    pass


# Linux UAPI constants.  CPython exposes these when its build headers contain
# them, but the frozen Python 3.12.13 environment omits the fcntl names even
# though the Arrhenius kernel implements memfd sealing.
F_ADD_SEALS = getattr(fcntl, "F_ADD_SEALS", 1033)
F_GET_SEALS = getattr(fcntl, "F_GET_SEALS", 1034)
F_SEAL_SEAL = getattr(fcntl, "F_SEAL_SEAL", 0x0001)
F_SEAL_SHRINK = getattr(fcntl, "F_SEAL_SHRINK", 0x0002)
F_SEAL_GROW = getattr(fcntl, "F_SEAL_GROW", 0x0004)
F_SEAL_WRITE = getattr(fcntl, "F_SEAL_WRITE", 0x0008)


JOURNAL_SCHEMA = P.FREEZE_SCHEMA + "/scheduler-recovery-journal/v1"
SCHEDULER_SNAPSHOT_SCHEMA = P.FREEZE_SCHEMA + "/scheduler-array-snapshot/v1"
RESCAN_SCHEMA = P.FREEZE_SCHEMA + "/post-archive-rescan/v1"
SCHEDULER_SNAPSHOT_PATH = P.ARTIFACT_DIR / "scheduler-array-snapshot-v1.json"
JOURNAL_PATH = P.ARTIFACT_DIR / "recovery-journal-v1.json"
POST_ARCHIVE_RESCAN_PATH = P.ARTIFACT_DIR / "recovery-post-archive-rescan-v1.json"
PRE_SUBMIT_RESCAN_PATH = P.ARTIFACT_DIR / "recovery-pre-submit-rescan-v1.json"
ARCHIVE_ROOT = P.ARTIFACT_DIR / "recovery-archive-v1"
RECOVERY_JOB_PATH = P.ARTIFACT_DIR / "recovery-job-v1.sh"
EXPERIMENT_ROOT = P.SCRIPT_DIR / "data" / "pdb_terminal_metric_choice"
STATIC_RUN_NAMES = {"run", "static-properties", "domain.pddl", "problem.pddl"}
SBATCH_EXECUTABLE = Path("/usr/bin/sbatch")
SBATCH_EXECUTABLE_SHA256 = (
    "efbb8e172acc7ed768430740d04e19cc07a3ac4701b005d1a997c08424bde741"
)
SUBMISSION_ENVIRONMENT = {"LANG": "C", "LC_ALL": "C"}

COMPLETE = "complete"
INTERRUPTED = "infrastructure_interrupted"
ACTIVE = "active"
SEMANTIC_FAILURE = "semantic_failure"
STATES = {COMPLETE, INTERRUPTED, ACTIVE, SEMANTIC_FAILURE}
INFRASTRUCTURE_STATES = {
    "BOOT_FAIL", "NODE_FAIL", "PREEMPTED", "REVOKED",
}
ACTIVE_SCHEDULER_STATES = {
    "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
    "RESIZING", "SUSPENDED", "STAGE_OUT",
}


def _sha(value) -> str:
    return hashlib.sha256(P.canonical_json(value)).hexdigest()


def _exact_cells(value, triad, label: str) -> None:
    if not isinstance(value, list) or any(type(cell) is not int for cell in value) or (
        value != sorted(set(value)) or not set(value) <= set(triad)
    ):
        raise RecoveryError("{} cell accounting changed".format(label))


def _validate_archive_manifest(value: dict, cell: int) -> None:
    if not isinstance(value, dict) or set(value) != {
        "cell", "manifest",
    } or type(value.get("cell")) is not int or value.get("cell") != cell:
        raise RecoveryError("recovery archive binding changed")
    manifest = value.get("manifest")
    if not isinstance(manifest, dict) or set(manifest) != {
        "entries", "entries_sha256",
    }:
        raise RecoveryError("recovery archive manifest changed")
    entries = manifest["entries"]
    if not isinstance(entries, list) or entries != sorted(
        entries, key=lambda row: row.get("name", "") if isinstance(row, dict) else ""
    ):
        raise RecoveryError("recovery archive entry order changed")
    names = []
    for row in entries:
        if not isinstance(row, dict) or set(row) != {"name", "sha256"} or (
            not isinstance(row["name"], str)
            or Path(row["name"]).name != row["name"]
            or P.SHA256_RE.fullmatch(row["sha256"] or "") is None
        ):
            raise RecoveryError("recovery archive entry changed")
        names.append(row["name"])
    if names != sorted(set(names)) or manifest["entries_sha256"] != hashlib.sha256(
        b"".join(
            row["name"].encode("ascii") + b"\0" + bytes.fromhex(row["sha256"])
            for row in entries
        )
    ).hexdigest():
        raise RecoveryError("recovery archive manifest digest changed")


def validate_journal(journal: dict, freeze: dict, freeze_sha256: str) -> None:
    if not isinstance(journal, dict) or set(journal) != {
        "schema", "freeze_sha256", "run_cell_mapping_sha256",
        "scheduler_contract", "entries", "entries_sha256",
    } or journal.get("schema") != JOURNAL_SCHEMA or (
        journal.get("freeze_sha256") != freeze_sha256
    ) or journal.get("run_cell_mapping_sha256") != freeze["design"][
        "run_cell_mapping_sha256"
    ]:
        raise RecoveryError("recovery journal header changed")
    try:
        Transport.validate_scheduler_contract(
            journal["scheduler_contract"], freeze, P.ACCOUNT
        )
    except Transport.TransportError as err:
        raise RecoveryError(str(err)) from err
    entries = journal.get("entries")
    if not isinstance(entries, list) or len(entries) != P.EXPECTED_ARRAY_TASKS or (
        journal.get("entries_sha256") != _sha(entries)
    ):
        raise RecoveryError("recovery journal accounting changed")
    for expected_task, entry in enumerate(entries, 1):
        if not isinstance(entry, dict) or set(entry) != {
            "array_task", "attempt", "job_id", "state", "triad_cells",
            "started_cells", "completed_cells", "archived_cells",
            "archive_manifests", "archive_manifest_sha256",
        }:
            raise RecoveryError("recovery journal entry changed")
        triad = list(P.triad_cells(expected_task))
        if any((
            type(entry["array_task"]) is not int,
            entry["array_task"] != expected_task,
            type(entry["attempt"]) is not int or entry["attempt"] < 1,
            not isinstance(entry["job_id"], str) or not entry["job_id"].isdigit(),
            entry["state"] not in STATES,
            entry["triad_cells"] != triad,
        )):
            raise RecoveryError("recovery array-task identity changed")
        if any(type(cell) is not int for cell in entry["triad_cells"]):
            raise RecoveryError("recovery triad cell type changed")
        for field in ("started_cells", "completed_cells", "archived_cells"):
            _exact_cells(entry[field], triad, "recovery " + field)
        started = entry["started_cells"]
        completed = entry["completed_cells"]
        archived = entry["archived_cells"]
        if not isinstance(entry["archive_manifests"], list):
            raise RecoveryError("recovery archive manifest list changed")
        if not set(completed) <= set(started):
            raise RecoveryError("completed recovery cell was not started")
        if entry["state"] == COMPLETE:
            if started != triad or completed != triad or archived or (
                entry["archive_manifests"] or entry["archive_manifest_sha256"] is not None
            ):
                raise RecoveryError("complete triad accounting changed")
        elif entry["state"] == INTERRUPTED:
            if archived != started or len(entry["archive_manifests"]) != len(started) or (
                [row.get("cell") for row in entry["archive_manifests"]] != started
            ) or not isinstance(
                entry["archive_manifest_sha256"], str
            ) or P.SHA256_RE.fullmatch(entry["archive_manifest_sha256"]) is None:
                raise RecoveryError("interrupted triad was not archived exactly")
            for cell, manifest in zip(started, entry["archive_manifests"]):
                _validate_archive_manifest(manifest, cell)
            if entry["archive_manifest_sha256"] != _sha(entry["archive_manifests"]):
                raise RecoveryError("interrupted archive aggregate changed")
        elif archived or entry["archive_manifests"] or (
            entry["archive_manifest_sha256"] is not None
        ):
            raise RecoveryError("non-recoverable triad has archive accounting")


def validate_rescan(rescan: dict, journal: dict, *, label: str) -> None:
    if not isinstance(rescan, dict) or set(rescan) != {
        "schema", "journal_sha256", "rows", "rows_sha256",
    } or rescan.get("schema") != RESCAN_SCHEMA or (
        rescan.get("journal_sha256") != hashlib.sha256(
            P.canonical_json_line(journal)
        ).hexdigest()
    ):
        raise RecoveryError("{} header changed".format(label))
    interrupted = [
        entry for entry in journal["entries"] if entry["state"] == INTERRUPTED
    ]
    rows = rescan.get("rows")
    if not isinstance(rows, list) or rescan.get("rows_sha256") != _sha(rows) or (
        len(rows) != len(interrupted)
    ):
        raise RecoveryError("{} accounting changed".format(label))
    for entry, row in zip(interrupted, rows):
        expected = {
            "array_task": entry["array_task"],
            "archive_manifest_sha256": entry["archive_manifest_sha256"],
            "cell_dynamic_entries": [
                {"cell": cell, "names": []} for cell in entry["triad_cells"]
            ],
            "dynamic_entries_after_archive": [],
        }
        if P.canonical_json(row) != P.canonical_json(expected):
            raise RecoveryError("{} found an unarchived triad entry".format(label))


def recovery_plan(
    journal: dict, freeze: dict, freeze_sha256: str,
    post_archive_rescan: dict, pre_submit_rescan: dict,
) -> dict:
    validate_journal(journal, freeze, freeze_sha256)
    validate_rescan(post_archive_rescan, journal, label="post-archive rescan")
    validate_rescan(pre_submit_rescan, journal, label="pre-submit rescan")
    if post_archive_rescan != pre_submit_rescan:
        raise RecoveryError("recovery namespace changed before submission")
    if any(entry["state"] == ACTIVE for entry in journal["entries"]):
        raise RecoveryError("an array triad is still active")
    if any(entry["state"] == SEMANTIC_FAILURE for entry in journal["entries"]):
        raise RecoveryError("semantic failures are not recoverable")
    tasks = [
        entry["array_task"] for entry in journal["entries"]
        if entry["state"] == INTERRUPTED
    ]
    array_spec = ",".join(map(str, tasks)) if tasks else None
    cells = [cell for task in tasks for cell in P.triad_cells(task)]
    return {
        "submission_required": bool(tasks),
        "array_tasks": tasks, "array_spec": array_spec,
        "array_throttle": 0, "whole_triad_cells": cells,
        "runs_per_array_task": P.RUNS_PER_ARRAY_TASK,
        "run_order_protocol": P.RUN_ORDER_PROTOCOL,
        "run_cell_mapping_sha256": freeze["design"]["run_cell_mapping_sha256"],
        "scheduler_contract": journal["scheduler_contract"],
        "journal_sha256": hashlib.sha256(P.canonical_json_line(journal)).hexdigest(),
        "rescan_sha256": hashlib.sha256(
            P.canonical_json_line(pre_submit_rescan)
        ).hexdigest(),
    }


def sbatch_options(plan: dict, job_name: str) -> list[str]:
    tasks = plan.get("array_tasks")
    if plan.get("submission_required") is not True or not tasks:
        raise RecoveryError("there are no triads to recover")
    if plan.get("whole_triad_cells") != [
        cell for task in tasks for cell in P.triad_cells(task)
    ]:
        raise RecoveryError("partial-triad recovery is forbidden")
    array_spec = ",".join(map(str, tasks))
    if array_spec != plan.get("array_spec") or "%" in array_spec:
        raise RecoveryError("recovery array specification changed")
    if not isinstance(job_name, str) or not job_name:
        raise RecoveryError("recovery job name is invalid")
    contract = plan["scheduler_contract"]
    return [
        "--array={}".format(array_spec), "--job-name={}".format(job_name),
        "--partition={}".format(contract["partition"]),
        "--qos={}".format(contract["qos"]),
        "--time={}".format(contract["time_limit"]),
        "--mem-per-cpu={}".format(contract["memory_per_cpu"]),
        "--cpus-per-task=1", "--nodes=1", "--ntasks=1",
        "--account={}".format(contract["account"]), "--no-requeue",
        "--export=NONE",
    ]


def validate_scheduler_snapshot(
    snapshot: dict, freeze: dict, freeze_sha256: str,
) -> None:
    if not isinstance(snapshot, dict) or set(snapshot) != {
        "schema", "freeze_sha256", "primary_launch_receipt_sha256",
        "run_cell_mapping_sha256", "scheduler_contract", "scheduler_rows",
        "scheduler_contract_rows", "entries", "entries_sha256",
    } or snapshot.get("schema") != SCHEDULER_SNAPSHOT_SCHEMA or (
        snapshot.get("freeze_sha256") != freeze_sha256
    ) or snapshot.get("run_cell_mapping_sha256") != freeze["design"][
        "run_cell_mapping_sha256"
    ] or P.SHA256_RE.fullmatch(
        snapshot.get("primary_launch_receipt_sha256", "")
    ) is None:
        raise RecoveryError("scheduler snapshot header changed")
    try:
        Transport.validate_scheduler_contract(
            snapshot["scheduler_contract"], freeze, P.ACCOUNT
        )
    except Transport.TransportError as err:
        raise RecoveryError(str(err)) from err
    entries = snapshot.get("entries")
    scheduler_rows = snapshot.get("scheduler_rows")
    contract_rows = snapshot.get("scheduler_contract_rows")
    if any(
        not isinstance(value, list) or len(value) != P.EXPECTED_ARRAY_TASKS
        for value in (entries, scheduler_rows, contract_rows)
    ) or snapshot.get("entries_sha256") != _sha(entries):
        raise RecoveryError("scheduler snapshot accounting changed")
    for task, (entry, scheduler, contract) in enumerate(zip(
        entries, scheduler_rows, contract_rows
    ), 1):
        if not isinstance(entry, dict) or set(entry) != {
            "array_task", "attempt", "job_id", "state", "started_cells",
            "completed_cells",
        }:
            raise RecoveryError("scheduler snapshot entry changed")
        triad = list(P.triad_cells(task))
        if any((
            type(entry["array_task"]) is not int,
            entry["array_task"] != task,
            type(entry["attempt"]) is not int or entry["attempt"] < 1,
            not isinstance(entry["job_id"], str) or not entry["job_id"].isdigit(),
            entry["state"] not in STATES,
        )):
            raise RecoveryError("scheduler array-task identity changed")
        if (
            not isinstance(scheduler, dict)
            or set(scheduler) != {
                "array_task", "job_id_raw", "state", "exit_code", "node",
                "elapsed_raw", "partition",
            }
            or type(scheduler.get("array_task")) is not int
            or scheduler["array_task"] != task
            or re.fullmatch(
                re.escape(entry["job_id"]) + r"_[0-9]+",
                scheduler.get("job_id_raw", ""),
            ) is None
            or not isinstance(scheduler.get("state"), str)
            or not scheduler["state"]
            or not isinstance(scheduler.get("exit_code"), str)
            or not scheduler["exit_code"]
            or not isinstance(scheduler.get("node"), str)
            or type(scheduler.get("elapsed_raw")) is not int
            or scheduler["elapsed_raw"] < 0
            or scheduler.get("partition") != "fat"
            or not isinstance(contract, dict)
            or set(contract) != {
                "array_task", "account", "partition", "qos", "req_cpus",
                "req_mem", "time_limit", "state", "exit_code", "job_name",
            }
            or type(contract.get("array_task")) is not int
            or contract["array_task"] != task
            or contract.get("account") != P.ACCOUNT
            or contract.get("partition") != "fat"
            or contract.get("qos") != "normal"
            or type(contract.get("req_cpus")) is not int
            or contract["req_cpus"] != 1
            or contract.get("req_mem") != freeze["design"]["scheduler_memory"]
            or contract.get("time_limit")
            != freeze["design"]["scheduler_time_limit"]
            or contract.get("state") != scheduler["state"]
            or contract.get("exit_code") != scheduler["exit_code"]
            or not isinstance(contract.get("job_name"), str)
            or not contract["job_name"]
        ):
            raise RecoveryError("scheduler snapshot resource row changed")
        _exact_cells(entry["started_cells"], triad, "scheduler started")
        _exact_cells(entry["completed_cells"], triad, "scheduler completed")
        if not set(entry["completed_cells"]) <= set(entry["started_cells"]):
            raise RecoveryError("scheduler completed cell was not started")
        if entry["state"] == COMPLETE and (
            entry["started_cells"] != triad or entry["completed_cells"] != triad
        ):
            raise RecoveryError("scheduler complete triad accounting changed")
        if scheduler["state"] == "COMPLETED" and scheduler["exit_code"] == "0:0":
            expected_state = (
                COMPLETE if entry["completed_cells"] == triad
                else SEMANTIC_FAILURE
            )
        elif scheduler["state"] in INFRASTRUCTURE_STATES:
            expected_state = INTERRUPTED
        elif scheduler["state"] in ACTIVE_SCHEDULER_STATES:
            expected_state = ACTIVE
        else:
            expected_state = SEMANTIC_FAILURE
        if entry["state"] != expected_state:
            raise RecoveryError("scheduler snapshot classification changed")


def _run_directory(experiment_root: Path, cell: int) -> Path:
    lower = ((cell - 1) // 100) * 100 + 1
    return experiment_root / "runs-{:05d}-{:05d}".format(
        lower, lower + 99
    ) / "{:05d}".format(cell)


def _scan_cell(experiment_root: Path, cell: int) -> list[str]:
    directory = _run_directory(experiment_root, cell)
    try:
        return Transport.scan_regular_namespace(
            directory, expected_directory=directory, root=experiment_root,
            excluded_names=STATIC_RUN_NAMES,
            label="recovery cell {:05d}".format(cell),
        )
    except Transport.TransportError as err:
        raise RecoveryError(str(err)) from err


def _make_rescan(journal: dict, experiment_root: Path) -> dict:
    rows = []
    for entry in journal["entries"]:
        if entry["state"] != INTERRUPTED:
            continue
        cells = [
            {"cell": cell, "names": _scan_cell(experiment_root, cell)}
            for cell in entry["triad_cells"]
        ]
        rows.append({
            "array_task": entry["array_task"],
            "archive_manifest_sha256": entry["archive_manifest_sha256"],
            "cell_dynamic_entries": cells,
            "dynamic_entries_after_archive": sorted({
                name for row in cells for name in row["names"]
            }),
        })
    value = {
        "schema": RESCAN_SCHEMA,
        "journal_sha256": hashlib.sha256(
            P.canonical_json_line(journal)
        ).hexdigest(),
        "rows": rows, "rows_sha256": _sha(rows),
    }
    validate_rescan(value, journal, label="live recovery rescan")
    return value


def _verify_archives(journal: dict, archive_root: Path) -> None:
    for entry in journal["entries"]:
        for binding in entry["archive_manifests"]:
            cell = binding["cell"]
            directory = archive_root / "array-{:03d}".format(
                entry["array_task"]
            ) / "attempt-{:03d}".format(entry["attempt"]) / "cell-{:05d}".format(cell)
            names = [row["name"] for row in binding["manifest"]["entries"]]
            try:
                found = Transport.scan_regular_namespace(
                    directory, expected_directory=directory, root=archive_root,
                    excluded_names=set(), label="recovery archive",
                )
                if found != names:
                    raise RecoveryError("recovery archive namespace changed")
                manifest = Transport.immutable_tree_manifest(
                    directory, names, label="recovery archive"
                )
            except Transport.TransportError as err:
                raise RecoveryError(str(err)) from err
            if [
                {"name": row["path"], "sha256": row["sha256"]}
                for row in manifest["files"]
            ] != binding["manifest"]["entries"]:
                raise RecoveryError("recovery archive changed before submission")
            try:
                after = Transport.scan_regular_namespace(
                    directory, expected_directory=directory, root=archive_root,
                    excluded_names=set(), label="recovery archive",
                )
            except Transport.TransportError as err:
                raise RecoveryError(str(err)) from err
            if after != names:
                raise RecoveryError("recovery archive changed during rescan")


def _write_receipt(root: Path, name: str, value: dict) -> None:
    path = root / name
    try:
        CampaignIO.write_canonical_exclusive(
            path, value, expected=path, root=root,
            label="recovery receipt", canonical_json_line=P.canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise RecoveryError(str(err)) from err


def _submit_pinned(options: list[str], raw: bytes) -> str:
    required_constants = (
        "MFD_ALLOW_SEALING", "MFD_CLOEXEC",
    )
    if (
        not isinstance(raw, bytes)
        or not isinstance(options, list)
        or any(not isinstance(option, str) for option in options)
        or options.count("--export=NONE") != 1
        or any(
            option.startswith("--export") and option != "--export=NONE"
            for option in options
        )
        or not hasattr(os, "memfd_create")
        or any(not hasattr(os, name) for name in required_constants)
        or (F_ADD_SEALS, F_GET_SEALS) != (1033, 1034)
        or (F_SEAL_SEAL, F_SEAL_SHRINK, F_SEAL_GROW, F_SEAL_WRITE)
        != (0x0001, 0x0002, 0x0004, 0x0008)
    ):
        raise RecoveryError("sealed Slurm submission contract is unavailable")
    required_seals = (
        F_SEAL_WRITE | F_SEAL_GROW | F_SEAL_SHRINK | F_SEAL_SEAL
    )
    descriptor = os.memfd_create(
        "metric-choice-recovery", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING
    )
    executable_fd = None
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise RecoveryError("cannot pin recovery job bytes")
            view = view[written:]
        fcntl.fcntl(descriptor, F_ADD_SEALS, required_seals)
        if fcntl.fcntl(descriptor, F_GET_SEALS) != required_seals:
            raise RecoveryError("recovery job memfd seal set changed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        blocks = []
        digest = hashlib.sha256()
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            blocks.append(block)
            digest.update(block)
        if b"".join(blocks) != raw or digest.hexdigest() != hashlib.sha256(
            raw
        ).hexdigest():
            raise RecoveryError("sealed recovery job bytes changed")
        os.lseek(descriptor, 0, os.SEEK_SET)
        try:
            executable_fd = Transport.open_verified_executable(
                SBATCH_EXECUTABLE, expected_path=SBATCH_EXECUTABLE,
                expected_sha256=SBATCH_EXECUTABLE_SHA256,
                label="frozen sbatch executable",
            )
        except Transport.TransportError as err:
            raise RecoveryError(str(err)) from err
        result = subprocess.run(
            [
                str(SBATCH_EXECUTABLE), "--parsable", *options,
                "/proc/self/fd/{}".format(descriptor),
            ],
            check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            pass_fds=(executable_fd, descriptor),
            executable="/proc/self/fd/{}".format(executable_fd),
            env=dict(SUBMISSION_ENVIRONMENT),
        )
    except (OSError, subprocess.SubprocessError) as err:
        raise RecoveryError("recovery submission failed") from err
    finally:
        if executable_fd is not None:
            os.close(executable_fd)
        os.close(descriptor)
    job_id = result.stdout.strip().split(";", 1)[0]
    if not job_id.isdigit():
        raise RecoveryError("scheduler returned an invalid recovery job id")
    return job_id


def coordinate_recovery(
    scheduler_snapshot: dict, freeze: dict, freeze_sha256: str, *,
    experiment_root: Path, archive_root: Path, receipt_root: Path,
    job_file: Path | None = None, expected_job_file: Path | None = None,
    job_name: str = "pdb-terminal-metric-choice-recovery",
    submitter=None,
) -> dict:
    """Archive, rescan, and submit interrupted whole triads in one checked flow."""
    validate_scheduler_snapshot(scheduler_snapshot, freeze, freeze_sha256)
    if any(row["state"] == ACTIVE for row in scheduler_snapshot["entries"]):
        raise RecoveryError("an array triad is still active")
    if any(row["state"] == SEMANTIC_FAILURE for row in scheduler_snapshot["entries"]):
        raise RecoveryError("semantic failures are not recoverable")
    tasks = [
        row["array_task"] for row in scheduler_snapshot["entries"]
        if row["state"] == INTERRUPTED
    ]
    loaded_job = None
    if tasks:
        if job_file is None or expected_job_file is None or submitter is None:
            raise RecoveryError("recovery submission inputs are absent")
        early_contract = copy.deepcopy(scheduler_snapshot["scheduler_contract"])
        early_contract.update({
            "array_spec": ",".join(map(str, tasks)), "array_tasks": len(tasks),
        })
        try:
            loaded_job = CampaignIO.read_regular_exact(
                job_file, expected=expected_job_file, label="recovery Slurm job"
            )
            Transport.validate_job_bytes(loaded_job.raw, early_contract)
        except (CampaignIO.CampaignIOError, Transport.TransportError) as err:
            raise RecoveryError(str(err)) from err
    try:
        Transport.validate_stable_directory(
            experiment_root, expected_directory=experiment_root,
            root=experiment_root.parent, label="recovery experiment root",
        )
    except Transport.TransportError as err:
        raise RecoveryError(str(err)) from err
    for path, root, label in (
        (receipt_root, receipt_root.parent, "recovery receipt root"),
        (archive_root, archive_root.parent, "recovery archive root"),
    ):
        try:
            CampaignIO.ensure_directory(path, root=root, label=label)
        except CampaignIO.CampaignIOError as err:
            raise RecoveryError(str(err)) from err

    journal_entries = []
    for snapshot_entry in scheduler_snapshot["entries"]:
        task = snapshot_entry["array_task"]
        triad = list(P.triad_cells(task))
        archive_bindings = []
        if snapshot_entry["state"] == INTERRUPTED:
            initial = {cell: _scan_cell(experiment_root, cell) for cell in triad}
            for cell in triad:
                if cell not in snapshot_entry["started_cells"] and initial[cell]:
                    raise RecoveryError("scheduler omitted a started recovery cell")
            for cell in snapshot_entry["started_cells"]:
                destination = archive_root / "array-{:03d}".format(task) / (
                    "attempt-{:03d}".format(snapshot_entry["attempt"])
                ) / "cell-{:05d}".format(cell)
                source = _run_directory(experiment_root, cell)
                try:
                    manifest = Transport.archive_regular_entries(
                        source, destination, initial[cell],
                        expected_source_directory=source,
                        expected_archive_directory=destination,
                        source_root=experiment_root, archive_root=archive_root,
                        label="recovery archive",
                    )
                except Transport.TransportError as err:
                    raise RecoveryError(str(err)) from err
                archive_bindings.append({"cell": cell, "manifest": manifest})
        journal_entries.append({
            "array_task": task, "attempt": snapshot_entry["attempt"],
            "job_id": snapshot_entry["job_id"], "state": snapshot_entry["state"],
            "triad_cells": triad,
            "started_cells": snapshot_entry["started_cells"],
            "completed_cells": snapshot_entry["completed_cells"],
            "archived_cells": (
                list(snapshot_entry["started_cells"])
                if snapshot_entry["state"] == INTERRUPTED else []
            ),
            "archive_manifests": archive_bindings,
            "archive_manifest_sha256": (
                _sha(archive_bindings)
                if snapshot_entry["state"] == INTERRUPTED else None
            ),
        })
    journal = {
        "schema": JOURNAL_SCHEMA, "freeze_sha256": freeze_sha256,
        "run_cell_mapping_sha256": freeze["design"]["run_cell_mapping_sha256"],
        "scheduler_contract": copy.deepcopy(scheduler_snapshot["scheduler_contract"]),
        "entries": journal_entries, "entries_sha256": _sha(journal_entries),
    }
    validate_journal(journal, freeze, freeze_sha256)
    post = _make_rescan(journal, experiment_root)
    _verify_archives(journal, archive_root)
    _write_receipt(receipt_root, JOURNAL_PATH.name, journal)
    _write_receipt(receipt_root, POST_ARCHIVE_RESCAN_PATH.name, post)
    plan = recovery_plan(journal, freeze, freeze_sha256, post, copy.deepcopy(post))
    if not plan["submission_required"]:
        return {"plan": plan, "journal": journal, "post_archive_rescan": post,
                "pre_submit_rescan": None, "submission": None}
    if not isinstance(job_name, str) or re.fullmatch(r"[A-Za-z0-9_.-]+", job_name) is None:
        raise RecoveryError("recovery job name is invalid")
    recovery_contract = copy.deepcopy(journal["scheduler_contract"])
    recovery_contract.update({
        "array_spec": plan["array_spec"], "array_tasks": len(plan["array_tasks"]),
    })
    if loaded_job is None:
        raise RecoveryError("recovery job was not pinned")
    Transport.validate_job_bytes(loaded_job.raw, recovery_contract)
    _verify_archives(journal, archive_root)
    pre = _make_rescan(journal, experiment_root)
    if pre != post:
        raise RecoveryError("recovery namespace changed before submission")
    _write_receipt(receipt_root, PRE_SUBMIT_RESCAN_PATH.name, pre)
    options = sbatch_options(plan, job_name)
    job_id = submitter(options, loaded_job.raw)
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise RecoveryError("recovery submitter returned an invalid job id")
    return {
        "plan": plan, "journal": journal, "post_archive_rescan": post,
        "pre_submit_rescan": pre,
        "submission": {
            "job_id": job_id, "options": options,
            "job_sha256": hashlib.sha256(loaded_job.raw).hexdigest(),
        },
    }


def _load_exact(path: Path, label: str) -> dict:
    try:
        _, value = CampaignIO.read_canonical_exact(
            path, expected=path, label=label,
            canonical_json_line=P.canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise RecoveryError(str(err)) from err
    return value


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--submit", action="store_true",
        help="execute the checked archive/rescan/pinned-sbatch flow",
    )
    args = parser.parse_args(argv)
    if not args.submit:
        parser.error("recovery requires explicit --submit")
    # The execution coordinator is the only production entry point because it
    # writes the tokenized intent before submission and can reconcile a crash.
    import pdb_terminal_metric_choice_execution as Execution
    base = __import__("pdb_terminal_metric_choice_runner").configure_lab_transport(
        P.FREEZE_PATH
    )
    result = Execution.launch_recovery(base)
    print(json.dumps(
        result,
        sort_keys=True, separators=(",", ":"),
    ))


if __name__ == "__main__":
    main()
