#!/usr/bin/env python3
"""Preview or recover failed terminal-incidence shadow array tasks."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

import audit_pdb_terminal_incidence_shadow as Audit
import pdb_terminal_incidence_shadow_protocol as P


class RecoveryError(RuntimeError):
    pass


RECOVERY_SCHEMA = Audit.RECOVERY_RECEIPT_SCHEMA
RECOVERY_JOB_PREFIX = "pdb-terminal-incidence-shadow-recovery"
DYNAMIC_NAMES = Audit.RECOVERY_DYNAMIC_NAMES
IMMUTABLE_NAMES = {"run", "static-properties", "domain.pddl", "problem.pddl"}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as err:
        raise RecoveryError("cannot hash {}".format(path)) from err
    return digest.hexdigest()


def _task_cells(array_task: int) -> range:
    if (
        type(array_task) is not int
        or not 1 <= array_task <= Audit.EXPECTED_ARRAY_TASKS
    ):
        raise RecoveryError("array task is out of range")
    first = (array_task - 1) * Audit.RUNS_PER_ARRAY_TASK + 1
    return range(
        first,
        min(first + Audit.RUNS_PER_ARRAY_TASK, Audit.EXPECTED_CELLS + 1),
    )


def _next_wave(root: Path) -> tuple[int, Path]:
    for index in range(1, 1000):
        path = root / "wave-{:04d}".format(index)
        if not path.exists():
            return index, path
    raise RecoveryError("recovery wave namespace is exhausted")


def _verify_source_job(launch: dict) -> Path:
    """Verify the immutable submitted job before any recovery mutation."""
    source_job = Audit.GRID_DIR / Audit.EXPECTED_JOB_NAME
    if source_job.is_symlink() or not source_job.is_file():
        raise RecoveryError("submitted Slurm job file is not a regular file")
    expected = launch.get("job_file_sha256")
    if Audit.SHA256_RE.fullmatch(expected or "") is None:
        raise RecoveryError("launch receipt has an invalid job-file hash")
    if _sha256_file(source_job) != expected:
        raise RecoveryError("submitted Slurm job file changed")
    return source_job


def _archive_plan(cells) -> list[dict]:
    """Describe partial dynamic files without mutating them."""
    plan = []
    for run_id in cells:
        run_dir = Audit._run_dir(run_id)
        try:
            entries = list(run_dir.iterdir())
        except OSError as err:
            raise RecoveryError(
                "cannot inspect interrupted run {}".format(run_id)
            ) from err
        unexpected = {
            entry.name for entry in entries
            if entry.name not in IMMUTABLE_NAMES | DYNAMIC_NAMES
        }
        if unexpected:
            raise RecoveryError(
                "interrupted run has unexpected mutable entries"
            )
        driver = run_dir / "driver.log"
        if driver.exists():
            try:
                lines = driver.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as err:
                raise RecoveryError(
                    "cannot inspect interrupted run {}".format(run_id)
                ) from err
            if lines and Audit.DRIVER_TERMINAL_RE.fullmatch(lines[-1]):
                raise RecoveryError(
                    "run {} completed while recovery was prepared".format(run_id)
                )
        for name in sorted(DYNAMIC_NAMES):
            source = run_dir / name
            if not source.exists():
                continue
            if source.is_symlink() or not source.is_file():
                raise RecoveryError("dynamic recovery target is not a file")
            plan.append({
                "run_id": run_id,
                "name": name,
                "source": source.relative_to(
                    Audit.EXPERIMENT_PATH
                ).as_posix(),
                "target": (
                    Path("interrupted-cell-files")
                    / "{:05d}".format(run_id)
                    / name
                ).as_posix(),
                "size": source.stat().st_size,
                "sha256": _sha256_file(source),
            })
    return plan


def _archive_interrupted(plan, wave_dir: Path) -> list[dict]:
    """Move an exclusively recorded archive plan after revalidation."""
    archived = []
    for item in plan:
        source = Audit.EXPERIMENT_PATH / item["source"]
        target = wave_dir / item["target"]
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise RecoveryError("recovery archive target already exists")
        if (
            source.is_symlink()
            or not source.is_file()
            or source.stat().st_size != item["size"]
            or _sha256_file(source) != item["sha256"]
        ):
            raise RecoveryError("recovery source changed after intent")
        shutil.move(str(source), str(target))
        if source.exists() or _sha256_file(target) != item["sha256"]:
            raise RecoveryError("recovery archive move failed attestation")
        archived.append(dict(item))
    return archived


def _exclusive_json(path: Path, value, label: str) -> bytes:
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii") + b"\n"
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise RecoveryError("{} already exists".format(label)) from err
    return raw


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--submit",
        action="store_true",
        help="submit the displayed recovery only after reviewing the preview",
    )
    return parser.parse_args(argv)


def _recovery_plan():
    launch, scheduler, recoveries, status = Audit.make_status()
    if not status["scheduler_terminal"]:
        raise RecoveryError("primary array is not yet terminal")
    latest_by_task = {row["array_task"]: row for row in scheduler}
    for execution in recoveries:
        for row in execution["scheduler_rows"]:
            latest_by_task[row["array_task"]] = row
    incomplete = set(status["incomplete_cells"])
    recover_tasks = []
    recover_cells = []
    for task in range(1, Audit.EXPECTED_ARRAY_TASKS + 1):
        row = latest_by_task[task]
        task_incomplete = [run for run in _task_cells(task) if run in incomplete]
        if row["state"] not in Audit.TERMINAL_SCHEDULER_STATES:
            raise RecoveryError(
                "latest execution of task {} is not terminal".format(task)
            )
        if row["state"] == "COMPLETED":
            if task_incomplete:
                raise RecoveryError(
                    "completed Slurm task {} has incomplete cells".format(task)
                )
            continue
        recover_tasks.append(task)
        recover_cells.extend(task_incomplete)
    return launch, recover_tasks, recover_cells


def main(argv=None) -> int:
    args = parse_args(argv)
    launch, recover_tasks, recover_cells = _recovery_plan()
    if not recover_tasks:
        message = {
            "recoverable_array_tasks": [],
            "recoverable_cells": [],
            "note": "no terminal scheduler failure currently needs recovery",
        }
        print(json.dumps(message, sort_keys=True, indent=2))
        return 0

    # This read-only verification deliberately precedes preview output, wave
    # creation, file archival, and submission.
    source_job = _verify_source_job(launch)
    preview = {
        "mode": "submit" if args.submit else "preview",
        "recoverable_array_tasks": recover_tasks,
        "recoverable_cells": recover_cells,
        "array_spec": ",".join(str(task) for task in recover_tasks),
        "array_throttle": 0,
        "partition": Audit.PARTITION,
        "qos": Audit.QOS,
        "runs_per_array_task": Audit.RUNS_PER_ARRAY_TASK,
        "cells": Audit.EXPECTED_CELLS,
        "source_job_file_sha256": launch["job_file_sha256"],
    }
    if not args.submit:
        print(json.dumps(preview, sort_keys=True, indent=2))
        return 0

    recovery_root = Audit.LAUNCH_RECEIPT.parent / "recovery"
    wave, wave_dir = _next_wave(recovery_root)
    wave_dir.mkdir(parents=True, exist_ok=False)
    array_spec = preview["array_spec"]
    stdout = wave_dir / "slurm-%A_%a.log"
    stderr = wave_dir / "slurm-%A_%a.err"
    command = [
        "sbatch",
        "--parsable",
        "--export=PATH",
        "--array={}".format(array_spec),
        "--job-name={}-{:04d}".format(RECOVERY_JOB_PREFIX, wave),
        "--output={}".format(stdout.resolve()),
        "--error={}".format(stderr.resolve()),
        "--partition={}".format(Audit.PARTITION),
        "--qos={}".format(Audit.QOS),
        "--time={}".format(Audit.SCHEDULER_TIME_LIMIT),
        "--mem-per-cpu={}".format(Audit.SCHEDULER_MEMORY),
        "--cpus-per-task=1",
        "--account={}".format(launch["account"]),
        "--no-requeue",
        str(source_job.resolve()),
    ]
    archive_plan = _archive_plan(recover_cells)
    intent = {
        "schema": "{}/intent".format(RECOVERY_SCHEMA),
        "recorded_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "wave": wave,
        "source_job_id": launch["job_id"],
        "source_launch_receipt_sha256": Audit.LAUNCH_RECEIPT_SHA256,
        "source_job_file_sha256": launch["job_file_sha256"],
        "array_tasks": recover_tasks,
        "array_spec": array_spec,
        "array_throttle": 0,
        "partition": Audit.PARTITION,
        "qos": Audit.QOS,
        "runs_per_array_task": Audit.RUNS_PER_ARRAY_TASK,
        "cells": Audit.EXPECTED_CELLS,
        "recoverable_cells": recover_cells,
        "archive_plan": archive_plan,
        "submit_command": command,
    }
    intent_path = wave_dir / "launch-intent.json"
    intent_raw = _exclusive_json(intent_path, intent, "recovery intent")
    archived = _archive_interrupted(archive_plan, wave_dir)
    try:
        output = subprocess.check_output(
            command, cwd=Audit.GRID_DIR, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("recovery submission failed") from err
    job_id = output.split(";", 1)[0]
    if not job_id.isdigit():
        raise RecoveryError("Slurm returned an invalid recovery job id")
    receipt = {
        "schema": RECOVERY_SCHEMA,
        "recorded_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "wave": wave,
        "source_job_id": launch["job_id"],
        "source_launch_receipt_sha256": Audit.LAUNCH_RECEIPT_SHA256,
        "source_job_file_sha256": launch["job_file_sha256"],
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": job_id,
        "array_tasks": recover_tasks,
        "array_spec": array_spec,
        "array_throttle": 0,
        "partition": Audit.PARTITION,
        "qos": Audit.QOS,
        "runs_per_array_task": Audit.RUNS_PER_ARRAY_TASK,
        "cells": Audit.EXPECTED_CELLS,
        "recoverable_cells": recover_cells,
        "archived_interrupted_files": archived,
        "submit_command": command,
    }
    receipt_path = wave_dir / "launch-receipt.json"
    _exclusive_json(receipt_path, receipt, "recovery receipt")
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Audit.ExecutionAuditError, P.ProtocolError, RecoveryError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
