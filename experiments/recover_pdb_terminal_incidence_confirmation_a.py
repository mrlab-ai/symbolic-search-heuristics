#!/usr/bin/env python3
"""Recover only scheduler-interrupted Confirmation A array elements."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
from pathlib import Path

import audit_pdb_terminal_incidence_confirmation_a as Audit
import exp_pdb_terminal_incidence_confirmation_a as Runner
import pdb_terminal_incidence_confirmation_a_protocol as P


class RecoveryError(RuntimeError):
    pass


IMMUTABLE_NAMES = {"run", "static-properties", "domain.pddl", "problem.pddl"}
SUBMISSION_TOKEN_RE = re.compile(r"^[0-9a-f]{24}$")
JOURNAL_FIELDS = "JobID%64,JobName%128,Comment%128"


def _next_wave() -> tuple[int, Path]:
    for wave in range(1, 1000):
        path = Audit.RECOVERY_ROOT / "wave-{:04d}".format(wave)
        if not path.exists():
            return wave, path
    raise RecoveryError("recovery wave namespace is exhausted")


def _run_dir(run_id: int) -> Path:
    lower = ((run_id - 1) // 100) * 100 + 1
    return (
        Audit.EXPERIMENT_PATH /
        "runs-{:05d}-{:05d}".format(lower, lower + 99) /
        "{:05d}".format(run_id)
    )


def _archive_plan(cells: list[int]) -> list[dict]:
    plan = []
    for run_id in cells:
        run_dir = _run_dir(run_id)
        try:
            entries = list(run_dir.iterdir())
        except OSError as err:
            raise RecoveryError("cannot inspect interrupted cell") from err
        unexpected = {
            entry.name for entry in entries
            if entry.name not in IMMUTABLE_NAMES | LegacyDynamic.names()
        }
        if unexpected:
            raise RecoveryError("interrupted cell has unexpected files")
        driver = run_dir / "driver.log"
        if driver.exists():
            try:
                lines = driver.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as err:
                raise RecoveryError("cannot inspect interrupted driver log") from err
            if lines and Audit.Legacy.DRIVER_TERMINAL_RE.fullmatch(lines[-1]):
                raise RecoveryError("recovery plan includes a completed cell")
        for name in sorted(LegacyDynamic.names()):
            source = run_dir / name
            if not source.exists():
                continue
            if source.is_symlink() or not source.is_file():
                raise RecoveryError("partial dynamic artifact is not regular")
            target = (
                Path("interrupted-cell-files") /
                "{:05d}".format(run_id) / name
            )
            plan.append({
                "run_id": run_id,
                "name": name,
                "source": source.relative_to(Audit.EXPERIMENT_PATH).as_posix(),
                "target": target.as_posix(),
                "size": source.stat().st_size,
                "sha256": P.sha256_file(source),
            })
    return plan


class LegacyDynamic:
    @staticmethod
    def names() -> set[str]:
        return set(Audit.Legacy.RECOVERY_DYNAMIC_NAMES)


def _archive(plan: list[dict], wave_dir: Path) -> None:
    for item in plan:
        source = Audit.EXPERIMENT_PATH / item["source"]
        target = wave_dir / item["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if any((
            target.exists(),
            source.is_symlink(),
            not source.is_file(),
            source.stat().st_size != item["size"],
            P.sha256_file(source) != item["sha256"],
        )):
            raise RecoveryError("partial artifact changed after recovery intent")
        shutil.move(str(source), str(target))
        if source.exists() or P.sha256_file(target) != item["sha256"]:
            raise RecoveryError("partial artifact archive failed")


def _submission_identity(wave: int, token: str) -> tuple[str, str]:
    if SUBMISSION_TOKEN_RE.fullmatch(token or "") is None:
        raise RecoveryError("recovery submission token is invalid")
    return (
        "pdb-incidence-confirm-a-recovery-{:04d}".format(wave),
        "pdb-incidence-confirm-a-recovery/{}/{}".format(wave, token),
    )


def submit_command(
    wave: int, wave_dir: Path, tasks: list[int], token: str
) -> list[str]:
    if (
        not tasks
        or tasks != sorted(set(tasks))
        or any(type(task) is not int or not 1 <= task <= P.EXPECTED_ARRAY_TASKS
               for task in tasks)
    ):
        raise RecoveryError("recovery array task set is invalid")
    array_spec = ",".join(map(str, tasks))
    if "%" in array_spec:
        raise RecoveryError("recovery array is throttled")
    name, comment = _submission_identity(wave, token)
    return [
        "sbatch", "--parsable", "--export=NONE", "--no-requeue",
        "--array={}".format(array_spec),
        "--job-name={}".format(name),
        "--comment={}".format(comment),
        "--output={}".format(
            (wave_dir / "slurm-%A_%a.out").resolve()
        ),
        "--error={}".format(
            (wave_dir / "slurm-%A_%a.err").resolve()
        ),
        "--partition=fat", "--qos=normal", "--time=01:40:00",
        "--mem-per-cpu=26G", "--cpus-per-task=1",
        "--account={}".format(P.ACCOUNT),
        str(Runner.JOB_FILE.resolve()),
    ]


def _latest_rows(rows: list[dict], recoveries: list[dict]) -> dict[int, dict]:
    latest = {row["array_task"]: row for row in rows}
    for execution in recoveries:
        for row in execution["scheduler_rows"]:
            latest[row["array_task"]] = row
    return latest


def recovery_plan() -> dict:
    launch, rows, recoveries, status = Audit.make_status()
    if status["active_array_tasks"]:
        raise RecoveryError("latest array execution is not terminal")
    tasks = status["recoverable_array_tasks"]
    if not tasks:
        return {
            "launch": launch,
            "rows": rows,
            "recoveries": recoveries,
            "tasks": [],
            "cells": [],
            "source_rows": [],
        }
    incomplete = set(status["incomplete_cells"])
    cells = sorted(
        cell for task in tasks for cell in Audit._task_cells(task)
        if cell in incomplete
    )
    latest = _latest_rows(rows, recoveries)
    source_rows = [latest[task] for task in tasks]
    if any(Audit._row_class(row) != "recoverable" for row in source_rows):
        raise RecoveryError("recovery plan contains a non-infrastructure failure")
    return {
        "launch": launch,
        "rows": rows,
        "recoveries": recoveries,
        "tasks": tasks,
        "cells": cells,
        "source_rows": source_rows,
    }


def _common(
    plan: dict, wave: int, wave_dir: Path, token: str
) -> dict:
    launch_sha, launch = Runner.load_launch_receipt(verify_live=True)
    if launch != plan["launch"]:
        raise RecoveryError("launch changed during recovery preparation")
    command = submit_command(wave, wave_dir, plan["tasks"], token)
    return {
        "wave": wave,
        "source_job_id": launch["job_id"],
        "source_launch_receipt_sha256": launch_sha,
        "source_job_file_sha256": launch["job_file_sha256"],
        "source_latest_scheduler_rows": plan["source_rows"],
        "array_tasks": plan["tasks"],
        "array_spec": ",".join(map(str, plan["tasks"])),
        "array_throttle": 0,
        "partition": "fat",
        "qos": "normal",
        "account": P.ACCOUNT,
        "cpus_per_task": 1,
        "memory_per_cpu": "26G",
        "time_limit": "01:40:00",
        "runs_per_array_task": 3,
        "cells": 2600,
        "recoverable_cells": plan["cells"],
        "submission_export": "NONE",
        "nice_adjustment": None,
        "requeue": False,
        "submission_token": token,
        "submission_comment": _submission_identity(wave, token)[1],
        "submit_command": command,
    }


def preview() -> None:
    plan = recovery_plan()
    print(json.dumps({
        "recoverable_array_tasks": plan["tasks"],
        "recoverable_cells": plan["cells"],
        "array_throttle": 0,
        "partition": "fat",
        "qos": "normal",
    }, sort_keys=True, indent=2))


def launch() -> None:
    plan = recovery_plan()
    if not plan["tasks"]:
        print(json.dumps({
            "recoverable_array_tasks": [],
            "note": "no scheduler-interrupted task needs recovery",
        }, sort_keys=True, indent=2))
        return
    wave, wave_dir = _next_wave()
    token = secrets.token_hex(12)
    recorded = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )
    common = _common(plan, wave, wave_dir, token)
    archive_plan = _archive_plan(plan["cells"])
    intent = {
        "schema": Audit.RECOVERY_SCHEMA + "/launch/intent",
        "recorded_utc": recorded,
        **common,
        "archive_plan": archive_plan,
    }
    wave_dir.mkdir(parents=True, exist_ok=False)
    intent_raw = P.canonical_json_line(intent)
    Runner._exclusive_bytes(
        wave_dir / "launch-intent.json", intent_raw, "recovery launch intent"
    )
    _archive(archive_plan, wave_dir)
    try:
        output = subprocess.check_output(
            common["submit_command"], cwd=Runner.GRID_DIR, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("recovery sbatch failed after intent") from err
    job_id = output.split(";", 1)[0]
    _write_receipt(wave_dir, intent_raw, intent, job_id)
    print(json.dumps({
        "wave": wave,
        "job_id": job_id,
        "array_tasks": plan["tasks"],
    }, sort_keys=True, indent=2))


def _load_intent(wave_dir: Path) -> tuple[bytes, dict]:
    raw, intent = Audit._canonical_load(
        wave_dir / "launch-intent.json", "recovery launch intent"
    )
    wave = Audit._wave_number(wave_dir)
    tasks = intent.get("array_tasks")
    token = intent.get("submission_token")
    if not isinstance(tasks, list):
        raise RecoveryError("recovery intent lacks an array task set")
    try:
        Runner._validate_recorded_utc(intent.get("recorded_utc"))
    except Runner.ConfirmationLaunchError as err:
        raise RecoveryError("recovery submission timestamp changed") from err
    command = submit_command(wave, wave_dir, tasks, token)
    if any((
        intent.get("schema") != Audit.RECOVERY_SCHEMA + "/launch/intent",
        intent.get("wave") != wave,
        intent.get("submit_command") != command,
        intent.get("submission_comment") != _submission_identity(wave, token)[1],
    )):
        raise RecoveryError("recovery launch intent changed")
    Audit._validate_archive(wave_dir, intent.get("archive_plan"), intent.get("recoverable_cells"))
    return raw, intent


def _write_receipt(
    wave_dir: Path, intent_raw: bytes, intent: dict, job_id: str
) -> None:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise RecoveryError("Slurm returned an invalid recovery job ID")
    excluded = {"schema", "archive_plan"}
    receipt = {
        "schema": Audit.RECOVERY_SCHEMA + "/launch",
        **{key: value for key, value in intent.items() if key not in excluded},
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": job_id,
        "archived_interrupted_files": intent["archive_plan"],
    }
    Runner._exclusive_json(
        wave_dir / "launch-receipt.json", receipt, "recovery launch receipt"
    )


def _journal_ids(intent: dict) -> list[str]:
    try:
        recorded = datetime.datetime.fromisoformat(intent["recorded_utc"])
    except (KeyError, TypeError, ValueError) as err:
        raise RecoveryError("recovery submission timestamp is invalid") from err
    if recorded.tzinfo is None:
        raise RecoveryError("recovery timestamp lacks a timezone")
    command = [
        "sacct", "-X", "-S", recorded.date().isoformat(), "-n", "-P",
        "-o", JOURNAL_FIELDS,
    ]
    try:
        output = subprocess.check_output(command, text=True)
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("cannot query recovery submission journal") from err
    name, comment = _submission_identity(
        intent["wave"], intent["submission_token"]
    )
    parents = set()
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 3:
            raise RecoveryError("recovery submission journal row changed")
        job_id, actual_name, actual_comment = fields
        if actual_name != name and actual_comment != comment:
            continue
        match = re.fullmatch(r"([0-9]+)(?:_[0-9]+)?", job_id)
        if match is None or actual_name != name or actual_comment != comment:
            raise RecoveryError("recovery submission identity collided")
        parents.add(match.group(1))
    if len(parents) > 1:
        raise RecoveryError("recovery submission identity is not unique")
    return sorted(parents, key=int)


def recover_launch() -> None:
    if not Audit.RECOVERY_ROOT.exists():
        raise RecoveryError("no recovery launch intent exists")
    wave_dirs = sorted(Audit.RECOVERY_ROOT.iterdir())
    unresolved = [
        path for path in wave_dirs
        if (path / "launch-intent.json").exists()
        and not (path / "launch-receipt.json").exists()
    ]
    if len(unresolved) != 1 or unresolved[0] != wave_dirs[-1]:
        raise RecoveryError("recovery has no unique latest unresolved intent")
    wave_dir = unresolved[0]
    intent_raw, intent = _load_intent(wave_dir)
    jobs = _journal_ids(intent)
    if len(jobs) != 1:
        raise RecoveryError(
            "submission journal identifies {} recovery jobs".format(len(jobs))
        )
    _write_receipt(wave_dir, intent_raw, intent, jobs[0])
    print(json.dumps({
        "wave": intent["wave"],
        "job_id": jobs[0],
        "launch_receipt_reconstructed": True,
    }, sort_keys=True, indent=2))


def status() -> None:
    _, _, recoveries, state = Audit.make_status()
    print(json.dumps({
        "recovery_waves": len(recoveries),
        "recoverable_array_tasks": state["recoverable_array_tasks"],
        "active_array_tasks": state["active_array_tasks"],
        "effectively_completed_array_tasks": state[
            "effectively_completed_array_tasks"
        ],
    }, sort_keys=True, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("preview", "launch", "recover-launch", "status")
    )
    args = parser.parse_args(argv)
    {
        "preview": preview,
        "launch": launch,
        "recover-launch": recover_launch,
        "status": status,
    }[args.command]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        RecoveryError,
        Audit.ExecutionAuditError,
        Runner.ConfirmationLaunchError,
        P.ProtocolError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
