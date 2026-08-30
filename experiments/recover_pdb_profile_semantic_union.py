#!/usr/bin/env python3
"""Rerun only scheduler-failed, file-incomplete semantic-union cells."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import audit_pdb_profile_semantic_union as Audit
import exp_pdb_profile_semantic_union as E
import pdb_profile_semantic_union_protocol as P


class RecoveryError(RuntimeError):
    pass


RECOVERY_SCHEMA = (
    "symbolic-search-heuristics/pdb-profile-semantic-union-recovery-launch/v1"
)
DYNAMIC_NAMES = {
    "driver.err",
    "driver.log",
    "output.sas",
    "run.err",
    "run.log",
    "sas_plan",
    "wbh-profile.jsonl",
    "wbh.jsonl",
}


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _task_cells(array_task: int):
    first = (array_task - 1) * E.RUNS_PER_ARRAY_TASK + 1
    return range(first, min(first + E.RUNS_PER_ARRAY_TASK, P.CELL_COUNT + 1))


def _next_wave(root: Path):
    for index in range(1, 1000):
        path = root / "wave-{:04d}".format(index)
        if not path.exists():
            return index, path
    raise RecoveryError("recovery wave namespace is exhausted")


def _archive_interrupted(cells, wave_dir):
    archived = []
    archive_root = wave_dir / "interrupted-cell-files"
    for run_id in cells:
        run_dir = Audit._run_dir(run_id)
        driver = run_dir / "driver.log"
        if not driver.exists():
            continue
        try:
            lines = driver.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as err:
            raise RecoveryError(
                "cannot inspect interrupted run {}".format(run_id)
            ) from err
        if lines and Audit.DRIVER_TERMINAL_RE.fullmatch(lines[-1]):
            continue
        target_dir = archive_root / "{:05d}".format(run_id)
        target_dir.mkdir(parents=True, exist_ok=False)
        for name in sorted(DYNAMIC_NAMES):
            source = run_dir / name
            if source.exists():
                if source.is_symlink() or not source.is_file():
                    raise RecoveryError("dynamic recovery target is not a file")
                digest = _sha256_file(source)
                size = source.stat().st_size
                target = target_dir / name
                shutil.move(str(source), str(target))
                archived.append({
                    "run_id": run_id,
                    "name": name,
                    "size": size,
                    "sha256": digest,
                })
    return archived


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    launch, scheduler, status = Audit.make_status()
    scheduler_by_task = {row["array_task"]: row for row in scheduler}
    incomplete = set(status["incomplete_cells"])
    recover_tasks = []
    recover_cells = []
    for task in range(1, E.EXPECTED_ARRAY_TASKS + 1):
        row = scheduler_by_task[task]
        task_incomplete = [run for run in _task_cells(task) if run in incomplete]
        if not task_incomplete:
            continue
        if row["state"] not in Audit.TERMINAL_SCHEDULER_STATES:
            continue
        if row["state"] == "COMPLETED":
            raise RecoveryError(
                "completed Slurm task {} has incomplete cells".format(task)
            )
        recover_tasks.append(task)
        recover_cells.extend(task_incomplete)
    if not recover_tasks:
        message = {
            "recoverable_array_tasks": [],
            "recoverable_cells": [],
            "note": "no terminal scheduler failure currently needs recovery",
        }
        print(json.dumps(message, sort_keys=True, indent=2))
        return 0
    preview = {
        "recoverable_array_tasks": recover_tasks,
        "recoverable_cells": recover_cells,
        "array_throttle": 0,
        "partition": "fat",
    }
    if args.dry_run:
        print(json.dumps(preview, sort_keys=True, indent=2))
        return 0

    recovery_root = E.LAUNCH_RECEIPT.parent / "recovery"
    wave, wave_dir = _next_wave(recovery_root)
    wave_dir.mkdir(parents=True, exist_ok=False)
    archived = _archive_interrupted(recover_cells, wave_dir)
    grid_dir = Path(str(E.EXPERIMENT_PATH) + "-grid-steps")
    source_job = grid_dir / "exp_pdb_profile_semantic_union-02-start"
    if _sha256_file(source_job) != launch["job_file_sha256"]:
        raise RecoveryError("submitted Slurm job file changed")
    array_spec = ",".join(str(task) for task in recover_tasks)
    stdout = wave_dir / "slurm-%A_%a.log"
    stderr = wave_dir / "slurm-%A_%a.err"
    command = [
        "sbatch",
        "--parsable",
        "--export=PATH",
        "--array={}".format(array_spec),
        "--job-name=pdb-semantic-union-recovery-{:04d}".format(wave),
        "--output={}".format(stdout.resolve()),
        "--error={}".format(stderr.resolve()),
        "--partition=fat",
        "--qos=normal",
        "--time={}".format(E.SCHEDULER_TIME_LIMIT),
        "--mem-per-cpu={}".format(E.SCHEDULER_MEMORY),
        "--cpus-per-task=1",
        "--account={}".format(E.ACCOUNT),
        "--no-requeue",
        str(source_job.resolve()),
    ]
    try:
        output = subprocess.check_output(command, cwd=grid_dir, text=True).strip()
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
        "source_job_file_sha256": launch["job_file_sha256"],
        "job_id": job_id,
        "array_tasks": recover_tasks,
        "array_spec": array_spec,
        "array_throttle": 0,
        "partition": "fat",
        "recoverable_cells": recover_cells,
        "archived_interrupted_files": archived,
        "submit_command": command,
    }
    receipt_path = wave_dir / "launch-receipt.json"
    receipt_path.write_bytes(
        json.dumps(
            receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii") + b"\n"
    )
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        Audit.ExecutionAuditError,
        E.LaunchError,
        P.ProtocolError,
        RecoveryError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
