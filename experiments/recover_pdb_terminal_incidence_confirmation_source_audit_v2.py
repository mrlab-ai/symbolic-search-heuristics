#!/usr/bin/env python3
"""Recover scheduler-interrupted source-audit v2 shards without v1 reuse."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources_v2 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v2 as Launch


_BASE_NAME = "_pdb_terminal_incidence_confirmation_source_recovery_v2_base"
_BASE_PATH = (
    SCRIPT_DIR / "recover_pdb_terminal_incidence_confirmation_source_audit.py"
)
_spec = importlib.util.spec_from_file_location(_BASE_NAME, _BASE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("cannot load frozen source-audit recovery implementation")
Base = importlib.util.module_from_spec(_spec)
sys.modules[_BASE_NAME] = Base
_spec.loader.exec_module(Base)


SCHEMA = Source.SCHEMA + "/campaign-v2/recovery/v1"
WAVE = 1
RECOVERY_ROOT = Launch.ARTIFACT_DIR / "recovery"
WAVE_DIR = RECOVERY_ROOT / "wave-0001"
INTENT = WAVE_DIR / "launch-intent.json"
LAUNCH_RECEIPT = WAVE_DIR / "launch-receipt.json"
EXECUTION_RECEIPT = WAVE_DIR / "execution-receipt.json"
DATA_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_recovery_v2"
)
OUTPUT_DIR = DATA_ROOT / "wave-0001"
UNION_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_union_v2"
)


for _name, _value in {
    "Source": Source,
    "Launch": Launch,
    "SCHEMA": SCHEMA,
    "WAVE": WAVE,
    "RECOVERY_ROOT": RECOVERY_ROOT,
    "WAVE_DIR": WAVE_DIR,
    "INTENT": INTENT,
    "LAUNCH_RECEIPT": LAUNCH_RECEIPT,
    "EXECUTION_RECEIPT": EXECUTION_RECEIPT,
    "DATA_ROOT": DATA_ROOT,
    "OUTPUT_DIR": OUTPUT_DIR,
    "UNION_DIR": UNION_DIR,
}.items():
    setattr(Base, _name, _value)


RecoveryError = Base.RecoveryError


def _submission_identity(token: str) -> tuple[str, str]:
    if (
        not isinstance(token, str)
        or Launch.SUBMISSION_TOKEN_RE.fullmatch(token) is None
    ):
        raise RecoveryError("source-audit v2 recovery token is invalid")
    return (
        "confirmation-source-recovery-v2-{}".format(token),
        "confirmation-source-recovery-v2/{}".format(token),
    )


def _submit_command(plan: dict, token: str) -> list[str]:
    tasks = plan["recoverable_shards"]
    array_spec = Base._array_spec(tasks)
    job_name, comment = _submission_identity(token)
    return [
        "sbatch", "--parsable", "--export=NONE",
        "--array={}".format(array_spec),
        "--job-name={}".format(job_name),
        "--comment={}".format(comment),
        "--account={}".format(Launch.ACCOUNT),
        "--partition=fat", "--qos=normal", "--cpus-per-task=1",
        "--mem-per-cpu={}".format(Launch.MEMORY_PER_CPU),
        "--time={}".format(Launch.TIME_LIMIT),
        "--output={}".format((OUTPUT_DIR / "slurm-%A_%a.out").resolve()),
        str(Launch.SLURM_SCRIPT),
        plan["source_inventory_sha256"], str(OUTPUT_DIR.resolve()),
    ]


def _intent_value(plan: dict, token: str, recorded_utc: str) -> dict:
    return {
        "schema": SCHEMA + "/launch/intent",
        "wave": WAVE,
        **plan,
        "recorded_utc": recorded_utc,
        "submission_token": token,
        "array_spec": Base._array_spec(plan["recoverable_shards"]),
        "array_throttle": 0,
        "partition": "fat",
        "qos": "normal",
        "account": Launch.ACCOUNT,
        "cpus_per_task": 1,
        "memory_per_cpu": Launch.MEMORY_PER_CPU,
        "time_limit": Launch.TIME_LIMIT,
        "task_timeout_seconds": Source.TASK_TIMEOUT_SECONDS,
        "output_dir": str(OUTPUT_DIR),
        "whole_campaign": "v2",
        "v1_shards_reused": 0,
        "submit_command": _submit_command(plan, token),
    }


for _name, _value in {
    "_submission_identity": _submission_identity,
    "_submit_command": _submit_command,
    "_intent_value": _intent_value,
}.items():
    setattr(Base, _name, _value)


def __getattr__(name):
    return getattr(Base, name)


def main(argv=None) -> int:
    return Base.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        RecoveryError,
        Launch.LaunchAuditError,
        Source.SourceAuditError,
    ) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
