#!/usr/bin/env python3
"""Audit or seal semantic-union execution without reading planner outcomes."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import exp_pdb_profile_semantic_union as E
import pdb_profile_semantic_union_protocol as P


class ExecutionAuditError(RuntimeError):
    pass


LAUNCH_RECEIPT_SHA256 = (
    "e21a96243cda0a4048163b243f0529ff6b4ad5dd0733008addcc4473b03fa573"
)
EXECUTION_RECEIPT = (
    E.SCRIPT_DIR
    / "artifacts"
    / "pdb-profile-semantic-union"
    / "execution-receipt-v1.json"
)
EXECUTION_RECEIPT_SCHEMA = (
    "symbolic-search-heuristics/pdb-profile-semantic-union-execution/v1"
)
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
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_launch_receipt():
    path = E.LAUNCH_RECEIPT
    try:
        raw = path.read_bytes()
        receipt = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ExecutionAuditError("cannot load the launch receipt") from err
    if hashlib.sha256(raw).hexdigest() != LAUNCH_RECEIPT_SHA256:
        raise ExecutionAuditError("launch receipt bytes changed")
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != E.LAUNCH_RECEIPT_SCHEMA
        or receipt.get("array_throttle") != 0
        or receipt.get("partition") != "fat"
        or receipt.get("cells") != P.CELL_COUNT
    ):
        raise ExecutionAuditError("launch receipt semantics changed")
    return receipt


def _run_dir(run_id: int) -> Path:
    lower = ((run_id - 1) // 100) * 100 + 1
    upper = min(lower + 99, P.CELL_COUNT)
    return (
        E.EXPERIMENT_PATH
        / "runs-{:05d}-{:05d}".format(lower, upper)
        / "{:05d}".format(run_id)
    )


def cell_completeness():
    counts = Counter()
    incomplete = []
    for run_id in range(1, P.CELL_COUNT + 1):
        path = _run_dir(run_id) / "driver.log"
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


def scheduler_rows(job_id: str):
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
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 7:
            raise ExecutionAuditError("unexpected sacct row shape")
        array_id, job_id_raw, state, exit_code, node, elapsed, partition = fields
        state = state.split("+", 1)[0].split()[0]
        prefix = job_id + "_"
        if not array_id.startswith(prefix) or not array_id[len(prefix):].isdigit():
            continue
        task = int(array_id[len(prefix):])
        if not 1 <= task <= E.EXPECTED_ARRAY_TASKS:
            raise ExecutionAuditError("Slurm array task id is out of range")
        if partition != "fat":
            raise ExecutionAuditError("Slurm accounting reports a non-fat task")
        rows.append({
            "array_task": task,
            "job_id_raw": job_id_raw,
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
    if len(by_task) != E.EXPECTED_ARRAY_TASKS:
        raise ExecutionAuditError(
            "Slurm accounting has {} of {} array tasks".format(
                len(by_task), E.EXPECTED_ARRAY_TASKS
            )
        )
    return [by_task[task] for task in sorted(by_task)]


def dynamic_tree_digest():
    digest = hashlib.sha256()
    files = 0
    excluded = {"run", "static-properties", "domain.pddl", "problem.pddl"}
    for run_id in range(1, P.CELL_COUNT + 1):
        run_dir = _run_dir(run_id)
        for path in sorted(run_dir.iterdir()):
            if path.name in excluded or path.is_symlink() or not path.is_file():
                continue
            relative = path.relative_to(E.EXPERIMENT_PATH).as_posix().encode("ascii")
            digest.update(relative + b"\0" + bytes.fromhex(_sha256_file(path)))
            files += 1
    return digest.hexdigest(), files


def make_status():
    launch = load_launch_receipt()
    tree_hash, run_files, property_files = E._run_input_tree_digest()
    if (
        tree_hash != launch["generated_run_input_tree_sha256"]
        or run_files != P.CELL_COUNT
        or property_files != P.CELL_COUNT
    ):
        raise ExecutionAuditError("immutable generated run inputs changed")
    rows = scheduler_rows(launch["job_id"])
    cell_counts, incomplete = cell_completeness()
    state_counts = dict(Counter(row["state"] for row in rows))
    terminal = all(row["state"] in TERMINAL_SCHEDULER_STATES for row in rows)
    successful = terminal and set(state_counts) == {"COMPLETED"}
    return launch, rows, {
        "scheduler_state_counts": state_counts,
        "scheduler_terminal": terminal,
        "scheduler_all_completed": successful,
        "cell_state_counts": cell_counts,
        "incomplete_cells": incomplete,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seal", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    launch, rows, status = make_status()
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
            "cannot seal: not every Slurm array task completed"
        )
    if status["incomplete_cells"]:
        raise ExecutionAuditError("cannot seal: cell files are incomplete")
    dynamic_hash, dynamic_files = dynamic_tree_digest()
    receipt = {
        "schema": EXECUTION_RECEIPT_SCHEMA,
        "launch_receipt_sha256": LAUNCH_RECEIPT_SHA256,
        "job_id": launch["job_id"],
        "array_throttle": 0,
        "partition": "fat",
        "scheduler_state_counts": status["scheduler_state_counts"],
        "cell_state_counts": status["cell_state_counts"],
        "scheduler_rows": rows,
        "dynamic_cell_tree_sha256": dynamic_hash,
        "dynamic_cell_files": dynamic_files,
    }
    raw = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii") + b"\n"
    EXECUTION_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    EXECUTION_RECEIPT.write_bytes(raw)
    print(
        "sealed {} complete cells from {} completed unthrottled fat tasks".format(
            P.CELL_COUNT, E.EXPECTED_ARRAY_TASKS
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (E.LaunchError, P.ProtocolError, ExecutionAuditError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
