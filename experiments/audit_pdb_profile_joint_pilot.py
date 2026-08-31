#!/usr/bin/env python3
"""Audit or seal the developmental joint-profile pilot."""

from __future__ import annotations

import argparse
import json

import audit_pdb_profile_certificate_holdout as Audit
import exp_pdb_profile_joint_pilot as Runner
import pdb_profile_joint_pilot_protocol as P


def configure() -> None:
    Runner.configure()
    Audit.E = Runner.Base
    Audit.P = P
    Audit.LAUNCH_RECEIPT_SHA256 = (
        "71a72268e8a2b59e32db0b63d2ce8f035452d1a450ca1ef7c6ebd742542eb575"
    )
    Audit.EXECUTION_RECEIPT = (
        Audit.E.SCRIPT_DIR
        / "artifacts"
        / "pdb-profile-joint-pilot"
        / "execution-receipt-v1.json"
    )
    Audit.EXECUTION_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/pdb-profile-joint-pilot-execution/v1"
    )
    Audit.RECOVERY_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/"
        "pdb-profile-joint-pilot-recovery-launch/v1"
    )


def _seal() -> None:
    launch, rows, recoveries, status = Audit.make_status()
    if not status["scheduler_terminal"]:
        raise Audit.ExecutionAuditError("primary array is not terminal")
    recovery_rows = [
        row
        for execution in recoveries
        for row in execution["scheduler_rows"]
    ]
    if any(row["state"] not in Audit.TERMINAL_SCHEDULER_STATES for row in recovery_rows):
        raise Audit.ExecutionAuditError("a recovery array is not terminal")
    if any(row["state"] != "COMPLETED" for row in recovery_rows):
        raise Audit.ExecutionAuditError("a recovery task did not complete")
    if status["incomplete_cells"]:
        raise Audit.ExecutionAuditError("a pilot cell lacks a terminal driver log")

    # Eleven primary tasks reached a complete planner terminal record before
    # Slurm killed the surrounding worker at its wall-time boundary. Accepting
    # those cells is safe because the frozen parsers validate their complete
    # streams and terminal outcome; the four actually interrupted cells were
    # recovered separately and retain their archived prefixes.
    dynamic_hash, dynamic_files = Audit.dynamic_tree_digest()
    receipt = {
        "schema": Audit.EXECUTION_RECEIPT_SCHEMA,
        "launch_receipt_sha256": Audit.LAUNCH_RECEIPT_SHA256,
        "job_id": launch["job_id"],
        "array_throttle": 0,
        "partition": "fat",
        "completion_policy": (
            "scheduler-terminal-and-every-cell-terminal-driver-log-v1"
        ),
        "scheduler_state_counts": status["scheduler_state_counts"],
        "cell_state_counts": status["cell_state_counts"],
        "scheduler_rows": rows,
        "recovery_executions": recoveries,
        "dynamic_cell_tree_sha256": dynamic_hash,
        "dynamic_cell_files": dynamic_files,
    }
    raw = json.dumps(
        receipt, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii") + b"\n"
    Audit.EXECUTION_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    Audit.EXECUTION_RECEIPT.write_bytes(raw)
    print(
        "sealed {} terminal cells from the unthrottled fat execution"
        .format(P.CELL_COUNT)
    )


def main(argv=None):
    configure()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seal", action="store_true")
    args = parser.parse_args(argv)
    if args.seal:
        _seal()
        return 0
    return Audit.main([])


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Audit.E.LaunchError, P.ProtocolError, Audit.ExecutionAuditError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
