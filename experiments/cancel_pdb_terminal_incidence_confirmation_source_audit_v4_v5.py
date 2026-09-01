#!/usr/bin/env python3
"""Prospectively authorize and execute one whole-array v4 cancellation.

This helper never resubmits work and never selects array elements.  A durable,
committed canonical intent is required before the single exact parent-job
``scancel`` invocation.  Recovery can only determine a receipt from scheduler
state after an existing attempt marker; it cannot invoke ``scancel``.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources_v5 as Source
import pdb_terminal_incidence_confirmation_safe_io_v5 as SafeIO


class CancellationError(RuntimeError):
    pass


JOB_ID = "1865695"
ARRAY_TASKS = 820
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v5"
)
INTENT = ARTIFACT_DIR / "v4-cancellation-intent-v5.json"
ATTEMPT = ARTIFACT_DIR / "v4-cancellation-attempt-v5.json"
RECEIPT = ARTIFACT_DIR / "v4-cancellation-receipt-v5.json"
SCANCEL = Path("/usr/bin/scancel")
SCANCEL_SHA256 = (
    "5f24c1ecee7423f39c10198b785fd44b72c4b6f08a341ebe5e2083be001cb753"
)
SCANCEL_ARGV = [str(SCANCEL), JOB_ID]
SACCT = Path("/usr/bin/sacct")
SACCT_SHA256 = (
    "58f3976b19baa2bc26772a92ab224dd0c1bf0ab3d9b675d85aa3e4636c836315"
)
JJ = Path("/home/jendrik/bin/jj")
JJ_SHA256 = (
    "d1d69a0f87df266eebf0d2592dd019eb288c300b15fd019afe26cb1ed11ba152"
)
CONTROLLED_ENV = {"LANG": "C", "LC_ALL": "C", "PATH": Source.CONTROLLED_PATH}
ACTIVE_STATES = frozenset({
    "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
    "RESIZING", "SUSPENDED", "STAGE_OUT",
})
TERMINAL_STATES = frozenset({
    "COMPLETED", "FAILED", "OUT_OF_MEMORY", "CANCELLED",
})
KNOWN_STATES = ACTIVE_STATES | TERMINAL_STATES
INTENT_SCHEMA = Source.SCHEMA + "/campaign-v5/v4-cancellation/intent/v1"
ATTEMPT_SCHEMA = Source.SCHEMA + "/campaign-v5/v4-cancellation/attempt/v1"
RECEIPT_SCHEMA = Source.SCHEMA + "/campaign-v5/v4-cancellation/receipt/v1"
REASON = (
    "v4 is seal-ineligible after the pinned translator timeouts and scheduler "
    "OOMs; cancel only the remaining parent array before a fresh zero-reuse "
    "v5 rerun"
)
V4_OUTPUT_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v4"
)
TRIGGER_SPECS = {
    147: {
        "state": "FAILED",
        "exit_code": "75:0",
        "failure_class": "translator-wallclock-timeout",
        "log_bytes": 2140,
        "log_sha256": (
            "796c47815fbd4cd3666e7d11e9205f334a1e40f6be34d807bc574a334e6c9fd1"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_147", "job_id_raw": "1865849",
                "state": "FAILED", "exit_code": "75:0",
                "elapsed": "05:10:08", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_147.batch",
                "job_id_raw": "1865849.batch", "state": "FAILED",
                "exit_code": "75:0", "elapsed": "05:10:08",
                "requested_memory": None, "max_rss": "350066053K",
                "max_vm_size": "354470312K",
            },
            {
                "job_id": "1865695_147.extern",
                "job_id_raw": "1865849.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "05:10:08",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    150: {
        "state": "FAILED",
        "exit_code": "75:0",
        "failure_class": "translator-wallclock-timeout",
        "log_bytes": 2105,
        "log_sha256": (
            "cd0907b3801b23026966251cc0e5a80162e56b6ea1241b5e03bb04288ad0bcea"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_150", "job_id_raw": "1865852",
                "state": "FAILED", "exit_code": "75:0",
                "elapsed": "04:00:13", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_150.batch",
                "job_id_raw": "1865852.batch", "state": "FAILED",
                "exit_code": "75:0", "elapsed": "04:00:13",
                "requested_memory": None, "max_rss": "349946713K",
                "max_vm_size": "354292836K",
            },
            {
                "job_id": "1865695_150.extern",
                "job_id_raw": "1865852.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "04:00:13",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    484: {
        "state": "FAILED",
        "exit_code": "75:0",
        "failure_class": "translator-wallclock-timeout",
        "log_bytes": 2167,
        "log_sha256": (
            "f4ad30cebbfd2466233db64b4b5d0e11f03e1760707d2cd51c3f99e54a2ab919"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_484", "job_id_raw": "1870270",
                "state": "FAILED", "exit_code": "75:0",
                "elapsed": "04:00:52", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_484.batch",
                "job_id_raw": "1870270.batch", "state": "FAILED",
                "exit_code": "75:0", "elapsed": "04:00:52",
                "requested_memory": None, "max_rss": "880383646K",
                "max_vm_size": "1042803456K",
            },
            {
                "job_id": "1865695_484.extern",
                "job_id_raw": "1870270.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "04:00:53",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    486: {
        "state": "FAILED",
        "exit_code": "75:0",
        "failure_class": "translator-wallclock-timeout",
        "log_bytes": 2319,
        "log_sha256": (
            "ebf24a2c7c4f07c498c56ffc65f60ffacdf577dcd6287a39f0f34e01748a56af"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_486", "job_id_raw": "1870272",
                "state": "FAILED", "exit_code": "75:0",
                "elapsed": "04:01:43", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_486.batch",
                "job_id_raw": "1870272.batch", "state": "FAILED",
                "exit_code": "75:0", "elapsed": "04:01:43",
                "requested_memory": None, "max_rss": "972214824K",
                "max_vm_size": "982929432K",
            },
            {
                "job_id": "1865695_486.extern",
                "job_id_raw": "1870272.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "04:01:43",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    487: {
        "state": "FAILED",
        "exit_code": "75:0",
        "failure_class": "translator-wallclock-timeout",
        "log_bytes": 2127,
        "log_sha256": (
            "a13303629929b99b8674a34a4aeec89e0ec41360e3fec4eeaf8771b4f51a5f2d"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_487", "job_id_raw": "1870273",
                "state": "FAILED", "exit_code": "75:0",
                "elapsed": "04:00:32", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_487.batch",
                "job_id_raw": "1870273.batch", "state": "FAILED",
                "exit_code": "75:0", "elapsed": "04:00:32",
                "requested_memory": None, "max_rss": "942747015K",
                "max_vm_size": "952638248K",
            },
            {
                "job_id": "1865695_487.extern",
                "job_id_raw": "1870273.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "04:00:32",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    488: {
        "state": "OUT_OF_MEMORY",
        "exit_code": "0:125",
        "failure_class": "scheduler-out-of-memory",
        "log_bytes": 2242,
        "log_sha256": (
            "d5a47a14b1d27b9d7341f2cec0be553130d230d59e94a36d3c2e02eed708086a"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_488", "job_id_raw": "1870274",
                "state": "OUT_OF_MEMORY", "exit_code": "0:125",
                "elapsed": "02:00:24", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_488.batch",
                "job_id_raw": "1870274.batch", "state": "OUT_OF_MEMORY",
                "exit_code": "0:125", "elapsed": "02:00:24",
                "requested_memory": None, "max_rss": "1071599733K",
                "max_vm_size": "1087451720K",
            },
            {
                "job_id": "1865695_488.extern",
                "job_id_raw": "1870274.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "02:00:24",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    489: {
        "state": "FAILED",
        "exit_code": "75:0",
        "failure_class": "translator-wallclock-timeout",
        "log_bytes": 2127,
        "log_sha256": (
            "7eb4626a832645d64b1416ddcf7ec76fe88fc558657b7ad2917b4b91d3a900dc"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_489", "job_id_raw": "1870275",
                "state": "FAILED", "exit_code": "75:0",
                "elapsed": "04:00:44", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_489.batch",
                "job_id_raw": "1870275.batch", "state": "FAILED",
                "exit_code": "75:0", "elapsed": "04:00:44",
                "requested_memory": None, "max_rss": "969771009K",
                "max_vm_size": "1072429040K",
            },
            {
                "job_id": "1865695_489.extern",
                "job_id_raw": "1870275.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "04:00:44",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    716: {
        "state": "OUT_OF_MEMORY",
        "exit_code": "0:125",
        "failure_class": "scheduler-out-of-memory",
        "log_bytes": 2224,
        "log_sha256": (
            "2d275d765948a8354e689e0a1acda532c9ba47127b52d86cb29a6629492c2f23"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_716", "job_id_raw": "1873521",
                "state": "OUT_OF_MEMORY", "exit_code": "0:125",
                "elapsed": "03:41:10", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_716.batch",
                "job_id_raw": "1873521.batch", "state": "OUT_OF_MEMORY",
                "exit_code": "0:125", "elapsed": "03:41:10",
                "requested_memory": None, "max_rss": "1054370899K",
                "max_vm_size": "1069066976K",
            },
            {
                "job_id": "1865695_716.extern",
                "job_id_raw": "1873521.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "03:41:11",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    717: {
        "state": "OUT_OF_MEMORY",
        "exit_code": "0:125",
        "failure_class": "scheduler-out-of-memory",
        "log_bytes": 2224,
        "log_sha256": (
            "8c0eaaf157f2d5fa7aeb3680bda1cf267bfb41487e33f4a56caf8101bd67f61b"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_717", "job_id_raw": "1873522",
                "state": "OUT_OF_MEMORY", "exit_code": "0:125",
                "elapsed": "03:28:26", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_717.batch",
                "job_id_raw": "1873522.batch", "state": "OUT_OF_MEMORY",
                "exit_code": "0:125", "elapsed": "03:28:26",
                "requested_memory": None, "max_rss": "1071622629K",
                "max_vm_size": "1073078444K",
            },
            {
                "job_id": "1865695_717.extern",
                "job_id_raw": "1873522.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "03:28:26",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    718: {
        "state": "OUT_OF_MEMORY",
        "exit_code": "0:125",
        "failure_class": "scheduler-out-of-memory",
        "log_bytes": 2224,
        "log_sha256": (
            "7f70f4c5327c7435041977e7b55f090a18873dfb2bb1661e36b23f00f6b2adb7"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_718", "job_id_raw": "1873523",
                "state": "OUT_OF_MEMORY", "exit_code": "0:125",
                "elapsed": "03:33:59", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_718.batch",
                "job_id_raw": "1873523.batch", "state": "OUT_OF_MEMORY",
                "exit_code": "0:125", "elapsed": "03:33:59",
                "requested_memory": None, "max_rss": "1056671983K",
                "max_vm_size": "1068164944K",
            },
            {
                "job_id": "1865695_718.extern",
                "job_id_raw": "1873523.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "03:33:59",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    719: {
        "state": "OUT_OF_MEMORY",
        "exit_code": "0:125",
        "failure_class": "scheduler-out-of-memory",
        "log_bytes": 2224,
        "log_sha256": (
            "471db3ece0c3b98b3fb8459c7d286ff152a4efddcb3dd9d958ad5220fb7650eb"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_719", "job_id_raw": "1873524",
                "state": "OUT_OF_MEMORY", "exit_code": "0:125",
                "elapsed": "03:40:14", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_719.batch",
                "job_id_raw": "1873524.batch", "state": "OUT_OF_MEMORY",
                "exit_code": "0:125", "elapsed": "03:40:14",
                "requested_memory": None, "max_rss": "1056300488K",
                "max_vm_size": "1066803356K",
            },
            {
                "job_id": "1865695_719.extern",
                "job_id_raw": "1873524.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "03:40:14",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    720: {
        "state": "OUT_OF_MEMORY",
        "exit_code": "0:125",
        "failure_class": "scheduler-out-of-memory",
        "log_bytes": 2224,
        "log_sha256": (
            "dffba4d69139089c8b3976de084c7378b1912efae7ddeda73e63f1e595ea286b"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_720", "job_id_raw": "1873525",
                "state": "OUT_OF_MEMORY", "exit_code": "0:125",
                "elapsed": "02:41:47", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_720.batch",
                "job_id_raw": "1873525.batch", "state": "OUT_OF_MEMORY",
                "exit_code": "0:125", "elapsed": "02:41:47",
                "requested_memory": None, "max_rss": "1066464869K",
                "max_vm_size": "1069162072K",
            },
            {
                "job_id": "1865695_720.extern",
                "job_id_raw": "1873525.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "02:41:47",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
    722: {
        "state": "OUT_OF_MEMORY",
        "exit_code": "0:125",
        "failure_class": "scheduler-out-of-memory",
        "log_bytes": 2224,
        "log_sha256": (
            "e65a146a654b8d1de9fd480d8d8610d0a315ad86dd1b320484e2c3e1a82caa05"
        ),
        "accounting_rows": [
            {
                "job_id": "1865695_722", "job_id_raw": "1878985",
                "state": "OUT_OF_MEMORY", "exit_code": "0:125",
                "elapsed": "02:51:48", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_722.batch",
                "job_id_raw": "1878985.batch", "state": "OUT_OF_MEMORY",
                "exit_code": "0:125", "elapsed": "02:51:48",
                "requested_memory": None, "max_rss": "1057000387K",
                "max_vm_size": "1069303288K",
            },
            {
                "job_id": "1865695_722.extern",
                "job_id_raw": "1878985.extern", "state": "COMPLETED",
                "exit_code": "0:0", "elapsed": "02:51:49",
                "requested_memory": None, "max_rss": None,
                "max_vm_size": None,
            },
        ],
    },
}
CANCELLATION_CODE_FILES = tuple(sorted({
    "experiments/audit_pdb_terminal_incidence_confirmation_sources.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v5.py",
    "experiments/cancel_pdb_terminal_incidence_confirmation_source_audit_v4_v5.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py",
    "experiments/pdb_terminal_incidence_confirmation_inventory.py",
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v5.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_cancellation_v5_protocol.md",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v4_cancellation_v5.py",
}))
SCOPED_COMMIT_FILES = tuple(sorted({
    *CANCELLATION_CODE_FILES,
    INTENT.relative_to(REPO).as_posix(),
}))


def _canonical(value) -> bytes:
    return Source.canonical_json(value)


def _digest_json(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _safe_file(path: Path, label: str, *, root: Path | None = None):
    try:
        return SafeIO.read_regular_file(
            path, label=label, expected_path=path, root=root
        )
    except SafeIO.SafeReadError as err:
        raise CancellationError(str(err)) from err


def _load_json(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        loaded, value = SafeIO.read_canonical_json(
            path,
            label=label,
            canonical_json_line=_canonical,
            expected_path=path,
        )
    except SafeIO.SafeReadError as err:
        raise CancellationError(str(err)) from err
    return loaded.raw, value


def _exclusive_json(path: Path, value, label: str) -> str:
    raw = _canonical(value)
    try:
        return Source.atomic_exclusive_bytes(path, raw, label)
    except Source.SourceAuditError as err:
        raise CancellationError(str(err)) from err


def _tool(path: Path, expected_sha256: str, label: str) -> dict:
    loaded = _safe_file(path, label)
    if (
        not path.is_absolute()
        or loaded.sha256 != expected_sha256
        or not stat.S_ISREG(loaded.identity["mode"])
        or stat.S_IMODE(loaded.identity["mode"]) & 0o111 == 0
        or not os.access(path, os.X_OK)
    ):
        raise CancellationError("pinned {} identity changed".format(label))
    return {"path": str(path), "sha256": loaded.sha256}


def _sacct(arguments: list[str]) -> str:
    _tool(SACCT, SACCT_SHA256, "sacct")
    try:
        return subprocess.check_output(
            [str(SACCT), *arguments], env=dict(CONTROLLED_ENV), text=True
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise CancellationError("cannot query v4 scheduler accounting") from err


def scheduler_rows() -> list[dict]:
    output = _sacct([
        "-j", JOB_ID, "-X", "--array", "-n", "-P",
        "--format=JobID,State,ExitCode,Elapsed,Partition",
    ])
    records = {}
    prefix = JOB_ID + "_"
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 5:
            raise CancellationError("v4 scheduler row changed")
        array_id, state, exit_code, elapsed, partition = fields
        if not array_id.startswith(prefix):
            continue
        suffix = array_id[len(prefix):]
        if not suffix.isdigit():
            raise CancellationError("v4 scheduler array is compressed")
        task = int(suffix)
        normalized_state = state.split("+", 1)[0].split()[0]
        if (
            task in records
            or not 0 <= task < ARRAY_TASKS
            or partition != "fat"
            or normalized_state not in KNOWN_STATES
        ):
            raise CancellationError("v4 scheduler identity/state changed")
        records[task] = {
            "array_task": task,
            "state": normalized_state,
            "exit_code": exit_code,
            "elapsed": elapsed,
            "partition": partition,
        }
    if set(records) != set(range(ARRAY_TASKS)):
        raise CancellationError("v4 scheduler task set is incomplete")
    return [records[index] for index in range(ARRAY_TASKS)]


def _trigger_accounting_rows(task: int) -> list[dict]:
    output = _sacct([
        "-j", "{}_{}".format(JOB_ID, task), "-n", "-P",
        "--format=JobID,JobIDRaw,State,ExitCode,Elapsed,ReqMem,MaxRSS,MaxVMSize",
    ])
    records = []
    prefix = "{}_{}".format(JOB_ID, task)
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 8:
            raise CancellationError("v4 trigger accounting row changed")
        (
            job_id, raw_id, state, exit_code, elapsed, req_mem,
            max_rss, max_vm,
        ) = fields
        if not job_id.startswith(prefix):
            continue
        records.append({
            "job_id": job_id,
            "job_id_raw": raw_id,
            "state": state.split("+", 1)[0].split()[0],
            "exit_code": exit_code,
            "elapsed": elapsed,
            "requested_memory": req_mem or None,
            "max_rss": max_rss or None,
            "max_vm_size": max_vm or None,
        })
    return records


def _validate_terminal_evidence_contract(rows: list[dict]) -> None:
    """Reject active, unknown, and unauthorized failure rows before log reads."""
    for row in rows:
        state = row["state"]
        exit_code = row["exit_code"]
        if state == "COMPLETED" and exit_code == "0:0":
            continue
        if state == "FAILED" and exit_code == "75:0":
            continue
        if state == "OUT_OF_MEMORY" and exit_code == "0:125":
            continue
        if (
            state == "CANCELLED"
            and re.fullmatch(r"[0-9]+:[0-9]+", exit_code or "") is not None
        ):
            continue
        raise CancellationError(
            "v4 terminal snapshot has an unauthorized state or failure class"
        )


def _trigger_evidence(
    rows: list[dict], *, allow_cancelled: bool = False
) -> list[dict]:
    by_task = {row["array_task"]: row for row in rows}
    if allow_cancelled:
        _validate_terminal_evidence_contract(rows)
    else:
        _validate_pre_cancel_contract(rows)
    # State/tool/job validation occurs before any failure log is opened.
    for task, expected in TRIGGER_SPECS.items():
        row = by_task.get(task)
        if (
            row is None
            or row["state"] != expected["state"]
            or row["exit_code"] != expected["exit_code"]
        ):
            raise CancellationError("authorized v4 trigger state changed")
    failure_rows = [
        row for row in rows
        if row["state"] in {"FAILED", "OUT_OF_MEMORY"}
    ]
    if not set(TRIGGER_SPECS) <= {
        row["array_task"] for row in failure_rows
    }:
        raise CancellationError("a pinned v4 trigger is absent")
    result = []
    task_line_re = re.compile(rb"^\[[12]/2\] ([^\r\n]+)\r?$", re.MULTILINE)
    empty_sha = hashlib.sha256(b"").hexdigest().encode("ascii")
    for row in failure_rows:
        task = row["array_task"]
        expected = TRIGGER_SPECS.get(task)
        accounting = _trigger_accounting_rows(task)
        prefix = "{}_{}".format(JOB_ID, task)
        parent = [item for item in accounting if item["job_id"] == prefix]
        batch = [item for item in accounting if item["job_id"] == prefix + ".batch"]
        if (
            len(parent) != 1
            or len(batch) != 1
            or parent[0]["state"] != row["state"]
            or parent[0]["exit_code"] != row["exit_code"]
            or parent[0]["elapsed"] != row["elapsed"]
            or parent[0]["requested_memory"] != "1T"
            or batch[0]["state"] != row["state"]
            or batch[0]["exit_code"] != row["exit_code"]
            or re.fullmatch(r"[1-9][0-9]*K", batch[0]["max_rss"] or "") is None
            or re.fullmatch(
                r"[1-9][0-9]*K", batch[0]["max_vm_size"] or ""
            ) is None
        ):
            raise CancellationError("authorized v4 trigger accounting changed")
        if expected is not None and accounting != expected["accounting_rows"]:
            raise CancellationError("authorized v4 trigger accounting changed")
        log_path = V4_OUTPUT_DIR / "slurm-{}_{}.out".format(JOB_ID, task)
        loaded = _safe_file(log_path, "authorized failed v4 log", root=V4_OUTPUT_DIR)
        if expected is not None and (
            len(loaded.raw) != expected["log_bytes"]
            or loaded.sha256 != expected["log_sha256"]
        ):
            raise CancellationError("authorized failed v4 log changed")
        names = task_line_re.findall(loaded.raw)
        if not names:
            raise CancellationError("authorized v4 trigger task is absent")
        try:
            task_name = names[-1].decode("ascii")
        except UnicodeDecodeError as err:
            raise CancellationError(
                "authorized v4 trigger task changed"
            ) from err
        timeout = re.findall(
            rb"infrastructure error: translator exceeded 14400s for "
            + re.escape(task_name.encode("ascii"))
            + rb"; stderr_sha256=([0-9a-f]{64}); stderr_tail='([^\r\n]*)'",
            loaded.raw,
        )
        if (
            row["state"] == "FAILED"
            and row["exit_code"] == "75:0"
            and timeout == [(empty_sha, b"")]
        ):
            failure_class = "translator-wallclock-timeout"
        elif (
            row["state"] == "OUT_OF_MEMORY"
            and row["exit_code"] == "0:125"
            and b"translator critical exit -9" in loaded.raw
            and b"oom_kill" in loaded.raw
        ):
            failure_class = "scheduler-out-of-memory"
        else:
            raise CancellationError("v4 trigger failure class changed")
        if expected is not None and failure_class != expected["failure_class"]:
            raise CancellationError("pinned v4 trigger class changed")
        result.append({
            "array_task": task,
            "state": row["state"],
            "exit_code": row["exit_code"],
            "task_name": task_name,
            "failure_class": failure_class,
            "log_path": str(log_path),
            "log_bytes": len(loaded.raw),
            "log_sha256": loaded.sha256,
            "accounting_rows": accounting,
            "accounting_rows_sha256": _digest_json(accounting),
        })
    return sorted(result, key=lambda item: item["array_task"])


def _code_materials() -> list[dict]:
    records = []
    for relative in CANCELLATION_CODE_FILES:
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise CancellationError("cancellation code path changed")
        loaded = _safe_file(
            REPO / relative, "cancellation code", root=REPO
        )
        records.append({"path": relative, "sha256": loaded.sha256})
    return records


def _snapshot(rows: list[dict]) -> dict:
    return {
        "rows": rows,
        "rows_sha256": _digest_json(rows),
        "state_counts": dict(sorted(Counter(
            row["state"] for row in rows
        ).items())),
    }


def _validate_snapshot(value: dict, *, terminal: bool = False) -> list[dict]:
    rows = value.get("rows") if isinstance(value, dict) else None
    if (
        not isinstance(value, dict)
        or set(value) != {"rows", "rows_sha256", "state_counts"}
        or not isinstance(rows, list)
        or len(rows) != ARRAY_TASKS
        or value.get("rows_sha256") != _digest_json(rows)
        or value.get("state_counts") != dict(sorted(Counter(
            row.get("state") for row in rows if isinstance(row, dict)
        ).items()))
    ):
        raise CancellationError("v4 scheduler snapshot changed")
    expected_tasks = list(range(ARRAY_TASKS))
    if [row.get("array_task") for row in rows] != expected_tasks:
        raise CancellationError("v4 scheduler snapshot task set changed")
    allowed = TERMINAL_STATES if terminal else KNOWN_STATES
    for row in rows:
        if (
            not isinstance(row, dict)
            or set(row) != {
                "array_task", "state", "exit_code", "elapsed", "partition",
            }
            or row["state"] not in allowed
            or row["partition"] != "fat"
        ):
            raise CancellationError("v4 scheduler snapshot state changed")
    return rows


def _validate_monotonic_transition(
    earlier_rows: list[dict],
    later_rows: list[dict],
    *,
    allow_cancelled: bool = False,
) -> None:
    """Allow only stage-appropriate progress; terminal rows never change."""
    _validate_snapshot(_snapshot(earlier_rows))
    _validate_snapshot(_snapshot(later_rows))
    if len(earlier_rows) != ARRAY_TASKS or len(later_rows) != ARRAY_TASKS:
        raise CancellationError("v4 scheduler transition task set changed")
    for before, after in zip(earlier_rows, later_rows):
        if (
            before.get("array_task") != after.get("array_task")
            or before.get("partition") != "fat"
            or after.get("partition") != "fat"
        ):
            raise CancellationError("v4 scheduler transition identity changed")
        before_state = before.get("state")
        after_state = after.get("state")
        if before_state in TERMINAL_STATES:
            if after != before:
                raise CancellationError(
                    "terminal v4 row changed after cancellation intent"
                )
            continue
        if before_state not in ACTIVE_STATES:
            raise CancellationError("v4 intent state is not authorized")
        if after_state in ACTIVE_STATES:
            if after.get("exit_code") != "0:0":
                raise CancellationError("active v4 row has a nonzero exit code")
            continue
        if after_state == "COMPLETED" and after.get("exit_code") == "0:0":
            continue
        if (
            allow_cancelled
            and after_state == "CANCELLED"
            and re.fullmatch(
                r"[0-9]+:[0-9]+", after.get("exit_code") or ""
            ) is not None
        ):
            continue
        raise CancellationError(
            "unauthorized v4 scheduler transition"
        )


def _validate_pre_cancel_contract(rows: list[dict]) -> None:
    for row in rows:
        state = row["state"]
        exit_code = row["exit_code"]
        if state in ACTIVE_STATES and exit_code == "0:0":
            continue
        if state == "COMPLETED" and exit_code == "0:0":
            continue
        if state == "FAILED" and exit_code == "75:0":
            continue
        if state == "OUT_OF_MEMORY" and exit_code == "0:125":
            continue
        raise CancellationError(
            "v4 pre-cancel snapshot has an unauthorized terminal class"
        )


def _validate_trigger_records(triggers: object, snapshot_rows: list[dict]) -> None:
    """Bind canonical trigger evidence to every failed row in the snapshot."""
    if not isinstance(triggers, list):
        raise CancellationError("v4 cancellation trigger records changed")
    failure_rows = [
        row for row in snapshot_rows
        if row["state"] in {"FAILED", "OUT_OF_MEMORY"}
    ]
    expected_tasks = [row["array_task"] for row in failure_rows]
    if not set(TRIGGER_SPECS) <= set(expected_tasks):
        raise CancellationError("a pinned v4 cancellation trigger is absent")
    if [item.get("array_task") for item in triggers if isinstance(item, dict)] \
            != expected_tasks:
        raise CancellationError(
            "v4 cancellation triggers do not match the snapshot failures"
        )
    trigger_keys = {
        "array_task", "state", "exit_code", "task_name", "failure_class",
        "log_path", "log_bytes", "log_sha256", "accounting_rows",
        "accounting_rows_sha256",
    }
    accounting_keys = {
        "job_id", "job_id_raw", "state", "exit_code", "elapsed",
        "requested_memory", "max_rss", "max_vm_size",
    }
    by_task = {row["array_task"]: row for row in failure_rows}
    for trigger in triggers:
        if not isinstance(trigger, dict) or set(trigger) != trigger_keys:
            raise CancellationError("v4 cancellation trigger record changed")
        task = trigger["array_task"]
        row = by_task[task]
        failure_class = {
            ("FAILED", "75:0"): "translator-wallclock-timeout",
            ("OUT_OF_MEMORY", "0:125"): "scheduler-out-of-memory",
        }[(row["state"], row["exit_code"])]
        accounting = trigger["accounting_rows"]
        try:
            trigger["task_name"].encode("ascii")
        except (AttributeError, UnicodeEncodeError) as err:
            raise CancellationError("v4 cancellation trigger task changed") from err
        if (
            trigger["state"] != row["state"]
            or trigger["exit_code"] != row["exit_code"]
            or not trigger["task_name"]
            or trigger["failure_class"] != failure_class
            or trigger["log_path"] != str(
                V4_OUTPUT_DIR / "slurm-{}_{}.out".format(JOB_ID, task)
            )
            or not isinstance(trigger["log_bytes"], int)
            or isinstance(trigger["log_bytes"], bool)
            or trigger["log_bytes"] <= 0
            or not Source._is_sha256(trigger["log_sha256"])
            or not isinstance(accounting, list)
            or not accounting
            or any(
                not isinstance(item, dict) or set(item) != accounting_keys
                for item in accounting
            )
            or trigger["accounting_rows_sha256"] != _digest_json(accounting)
        ):
            raise CancellationError("v4 cancellation trigger record changed")
        expected = TRIGGER_SPECS.get(task)
        if expected is not None and (
            trigger["state"] != expected["state"]
            or trigger["exit_code"] != expected["exit_code"]
            or trigger["failure_class"] != expected["failure_class"]
            or trigger["log_bytes"] != expected["log_bytes"]
            or trigger["log_sha256"] != expected["log_sha256"]
            or accounting != expected["accounting_rows"]
        ):
            raise CancellationError("pinned v4 cancellation trigger changed")


def _validate_intent(intent_raw: bytes, intent: dict) -> None:
    snapshot = intent.get("scheduler_snapshot")
    snapshot_rows = _validate_snapshot(snapshot)
    _validate_pre_cancel_contract(snapshot_rows)
    triggers = intent.get("authorized_triggers")
    _validate_trigger_records(triggers, snapshot_rows)
    code = intent.get("code_materials")
    if (
        set(intent) != {
            "schema", "recorded_utc", "job_id", "cancel_scope", "reason",
            "scancel", "argv", "controlled_environment",
            "authorized_triggers", "authorized_triggers_sha256",
            "scheduler_snapshot", "scheduler_snapshot_sha256",
            "code_materials", "code_materials_sha256", "full_v5_rerun",
        }
        or intent.get("schema") != INTENT_SCHEMA
        or not isinstance(intent.get("recorded_utc"), str)
        or intent.get("job_id") != JOB_ID
        or intent.get("cancel_scope") != "whole-parent-array-once"
        or intent.get("reason") != REASON
        or intent.get("scancel") != {
            "path": str(SCANCEL), "sha256": SCANCEL_SHA256,
        }
        or intent.get("argv") != SCANCEL_ARGV
        or intent.get("controlled_environment") != CONTROLLED_ENV
        or not isinstance(triggers, list)
        or intent.get("authorized_triggers_sha256") != _digest_json(triggers)
        or intent.get("scheduler_snapshot_sha256") != _digest_json(snapshot)
        or not isinstance(code, list)
        or intent.get("code_materials_sha256") != _digest_json(code)
        or intent.get("full_v5_rerun") != {
            "whole_campaign_rerun": True,
            "array_tasks": ARRAY_TASKS,
            "candidates": Source.CANDIDATE_COUNT,
            "reused_v1_shards": 0,
            "reused_v2_shards": 0,
            "reused_v3_shards": 0,
            "reused_v4_shards": 0,
        }
        or intent_raw != _canonical(intent)
    ):
        raise CancellationError("v4 cancellation intent changed")


def _load_intent(*, verify_live_triggers: bool) -> tuple[bytes, dict]:
    raw, intent = _load_json(INTENT, "v4 cancellation intent")
    _validate_intent(raw, intent)
    if intent["code_materials"] != _code_materials():
        raise CancellationError("v4 cancellation code changed")
    _tool(SCANCEL, SCANCEL_SHA256, "scancel")
    if verify_live_triggers:
        rows = scheduler_rows()
        if _trigger_evidence(rows) != intent["authorized_triggers"]:
            raise CancellationError("authorized v4 trigger evidence changed")
    return raw, intent


def _scoped_repository_commit() -> str:
    jj_identity = _tool(JJ, JJ_SHA256, "jj")
    commands = (
        [str(JJ), "--no-pager", "diff", "--summary", "-r", "@", "--",
         *SCOPED_COMMIT_FILES],
        [str(JJ), "--no-pager", "file", "list", "-r", "@-", "--",
         *SCOPED_COMMIT_FILES],
        [str(JJ), "--no-pager", "log", "-r", "@-", "--no-graph",
         "-T", 'commit_id ++ "\\n"'],
    )
    try:
        changed = subprocess.check_output(
            commands[0], cwd=REPO, env=dict(CONTROLLED_ENV), text=True
        )
        tracked = subprocess.check_output(
            commands[1], cwd=REPO, env=dict(CONTROLLED_ENV), text=True
        ).splitlines()
        commit = subprocess.check_output(
            commands[2], cwd=REPO, env=dict(CONTROLLED_ENV), text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise CancellationError("cannot attest committed cancellation intent") from err
    if (
        _tool(JJ, JJ_SHA256, "jj") != jj_identity
        or changed
        or set(tracked) != set(SCOPED_COMMIT_FILES)
        or len(tracked) != len(SCOPED_COMMIT_FILES)
        or re.fullmatch(r"[0-9a-f]{64}", commit or "") is None
    ):
        raise CancellationError(
            "cancellation code and intent must be committed together at @-"
        )
    return commit


def _validate_recorded_commit(
    commit: str, intent_raw: bytes, intent: dict
) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", commit or "") is None:
        raise CancellationError("recorded cancellation commit changed")
    identity = _tool(JJ, JJ_SHA256, "jj")
    expected = [
        *intent["code_materials"],
        {
            "path": INTENT.relative_to(REPO).as_posix(),
            "sha256": hashlib.sha256(intent_raw).hexdigest(),
        },
    ]
    try:
        for item in expected:
            raw = subprocess.check_output(
                [
                    str(JJ), "--no-pager", "file", "show", "-r", commit,
                    item["path"],
                ],
                cwd=REPO,
                env=dict(CONTROLLED_ENV),
            )
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise CancellationError(
                    "recorded cancellation commit bytes changed"
                )
    except (OSError, subprocess.CalledProcessError) as err:
        raise CancellationError(
            "cannot validate recorded cancellation commit"
        ) from err
    if _tool(JJ, JJ_SHA256, "jj") != identity:
        raise CancellationError("jj changed while validating cancellation commit")


def prepare_cancel_intent() -> None:
    if any(os.path.lexists(path) for path in (INTENT, ATTEMPT, RECEIPT)):
        raise CancellationError("v4 cancellation namespace is not empty")
    scancel = _tool(SCANCEL, SCANCEL_SHA256, "scancel")
    rows = scheduler_rows()
    if not any(row["state"] in ACTIVE_STATES for row in rows):
        raise CancellationError("v4 has no remaining array work to cancel")
    triggers = _trigger_evidence(rows)
    code = _code_materials()
    snapshot = _snapshot(rows)
    intent = {
        "schema": INTENT_SCHEMA,
        "recorded_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "job_id": JOB_ID,
        "cancel_scope": "whole-parent-array-once",
        "reason": REASON,
        "scancel": scancel,
        "argv": SCANCEL_ARGV,
        "controlled_environment": CONTROLLED_ENV,
        "authorized_triggers": triggers,
        "authorized_triggers_sha256": _digest_json(triggers),
        "scheduler_snapshot": snapshot,
        "scheduler_snapshot_sha256": _digest_json(snapshot),
        "code_materials": code,
        "code_materials_sha256": _digest_json(code),
        "full_v5_rerun": {
            "whole_campaign_rerun": True,
            "array_tasks": ARRAY_TASKS,
            "candidates": Source.CANDIDATE_COUNT,
            "reused_v1_shards": 0,
            "reused_v2_shards": 0,
            "reused_v3_shards": 0,
            "reused_v4_shards": 0,
        },
    }
    _validate_intent(_canonical(intent), intent)
    digest = _exclusive_json(INTENT, intent, "v4 cancellation intent")
    print(json.dumps({
        "intent_path": str(INTENT),
        "intent_sha256": digest,
        "next_step": "commit the exact cancellation scope before cancel-v4",
    }, sort_keys=True, indent=2))


def _validate_attempt(
    attempt_raw: bytes, attempt: dict, intent_sha256: str
) -> None:
    snapshot = attempt.get("pre_cancel_scheduler_snapshot")
    _validate_snapshot(snapshot)
    if (
        set(attempt) != {
            "schema", "recorded_utc", "job_id", "repository_commit_id",
            "intent_path", "intent_sha256", "scancel", "argv",
            "controlled_environment", "pre_cancel_scheduler_snapshot",
            "pre_cancel_scheduler_snapshot_sha256",
            "intent_scheduler_snapshot_sha256",
        }
        or attempt.get("schema") != ATTEMPT_SCHEMA
        or not isinstance(attempt.get("recorded_utc"), str)
        or attempt.get("job_id") != JOB_ID
        or re.fullmatch(
            r"[0-9a-f]{64}", attempt.get("repository_commit_id", "")
        ) is None
        or attempt.get("intent_path") != str(INTENT)
        or attempt.get("intent_sha256") != intent_sha256
        or not Source._is_sha256(
            attempt.get("intent_scheduler_snapshot_sha256")
        )
        or attempt.get("scancel") != {
            "path": str(SCANCEL), "sha256": SCANCEL_SHA256,
        }
        or attempt.get("argv") != SCANCEL_ARGV
        or attempt.get("controlled_environment") != CONTROLLED_ENV
        or attempt.get("pre_cancel_scheduler_snapshot_sha256")
        != _digest_json(snapshot)
        or attempt_raw != _canonical(attempt)
    ):
        raise CancellationError("v4 cancellation attempt changed")


def _write_receipt(
    *,
    intent_sha256: str,
    attempt_raw: bytes,
    attempt: dict,
    determination: str,
    returncode: int | None,
    stdout: bytes | None,
    stderr: bytes | None,
    post_rows: list[dict],
    recovered: bool,
) -> str:
    _validate_monotonic_transition(
        attempt["pre_cancel_scheduler_snapshot"]["rows"],
        post_rows,
        allow_cancelled=True,
    )
    snapshot = _snapshot(post_rows)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "recorded_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "job_id": JOB_ID,
        "repository_commit_id": attempt["repository_commit_id"],
        "intent_path": str(INTENT),
        "intent_sha256": intent_sha256,
        "intent_scheduler_snapshot_sha256": attempt[
            "intent_scheduler_snapshot_sha256"
        ],
        "attempt_path": str(ATTEMPT),
        "attempt_sha256": hashlib.sha256(attempt_raw).hexdigest(),
        "pre_cancel_scheduler_snapshot_sha256": attempt[
            "pre_cancel_scheduler_snapshot_sha256"
        ],
        "scancel": {"path": str(SCANCEL), "sha256": SCANCEL_SHA256},
        "argv": SCANCEL_ARGV,
        "controlled_environment": CONTROLLED_ENV,
        "determination": determination,
        "returncode": returncode,
        "stdout_sha256": hashlib.sha256(stdout or b"").hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr or b"").hexdigest(),
        "post_cancel_scheduler_snapshot": snapshot,
        "post_cancel_scheduler_snapshot_sha256": _digest_json(snapshot),
        "recovered_without_reissue": recovered,
        "resubmitted": False,
        "selective_cancel": False,
    }
    return _exclusive_json(RECEIPT, receipt, "v4 cancellation receipt")


def cancel_v4() -> None:
    if os.path.lexists(RECEIPT) or os.path.lexists(ATTEMPT):
        raise CancellationError("v4 cancellation was already attempted")
    intent_raw, _ = _load_intent(verify_live_triggers=False)
    commit = _scoped_repository_commit()
    # Revalidate job state and permitted failed logs only after code,
    # intent, argv, and tool identity have passed.
    rows = scheduler_rows()
    if not any(row["state"] in ACTIVE_STATES for row in rows):
        raise CancellationError("v4 has no remaining array work to cancel")
    second_intent_raw, intent = _load_intent(verify_live_triggers=False)
    if second_intent_raw != intent_raw:
        raise CancellationError("v4 cancellation intent changed before execution")
    _validate_monotonic_transition(
        intent["scheduler_snapshot"]["rows"], rows
    )
    if _trigger_evidence(rows) != intent["authorized_triggers"]:
        raise CancellationError("authorized v4 trigger evidence changed")
    _tool(SCANCEL, SCANCEL_SHA256, "scancel")
    snapshot = _snapshot(rows)
    attempt = {
        "schema": ATTEMPT_SCHEMA,
        "recorded_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "job_id": JOB_ID,
        "repository_commit_id": commit,
        "intent_path": str(INTENT),
        "intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "intent_scheduler_snapshot_sha256": intent[
            "scheduler_snapshot_sha256"
        ],
        "scancel": intent["scancel"],
        "argv": intent["argv"],
        "controlled_environment": intent["controlled_environment"],
        "pre_cancel_scheduler_snapshot": snapshot,
        "pre_cancel_scheduler_snapshot_sha256": _digest_json(snapshot),
    }
    attempt_raw = _canonical(attempt)
    _exclusive_json(ATTEMPT, attempt, "v4 cancellation attempt")
    try:
        completed = subprocess.run(
            SCANCEL_ARGV,
            cwd=REPO,
            env=dict(CONTROLLED_ENV),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as err:
        raise CancellationError(
            "scancel invocation is indeterminate; recovery will never reissue it"
        ) from err
    post_rows = scheduler_rows()
    determination = (
        "scancel-returned-zero" if completed.returncode == 0
        else "scancel-returned-nonzero"
    )
    digest = _write_receipt(
        intent_sha256=hashlib.sha256(intent_raw).hexdigest(),
        attempt_raw=attempt_raw,
        attempt=attempt,
        determination=determination,
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        post_rows=post_rows,
        recovered=False,
    )
    if completed.returncode != 0:
        raise CancellationError(
            "scancel returned nonzero; receipt recorded and no retry is permitted"
        )
    print(json.dumps({
        "job_id": JOB_ID,
        "receipt_sha256": digest,
        "whole_parent_array_cancel_requested_once": True,
    }, sort_keys=True, indent=2))


def _load_attempt(intent_sha256: str) -> tuple[bytes, dict]:
    raw, attempt = _load_json(ATTEMPT, "v4 cancellation attempt")
    _validate_attempt(raw, attempt, intent_sha256)
    return raw, attempt


def recover_cancel_receipt() -> None:
    if os.path.lexists(RECEIPT):
        raise CancellationError("v4 cancellation receipt already exists")
    intent_raw, intent = _load_intent(verify_live_triggers=False)
    intent_sha = hashlib.sha256(intent_raw).hexdigest()
    attempt_raw, attempt = _load_attempt(intent_sha)
    if (
        attempt.get("intent_scheduler_snapshot_sha256")
        != intent.get("scheduler_snapshot_sha256")
    ):
        raise CancellationError("attempt does not bind the intent scheduler snapshot")
    _validate_monotonic_transition(
        intent["scheduler_snapshot"]["rows"],
        attempt["pre_cancel_scheduler_snapshot"]["rows"],
    )
    rows = scheduler_rows()
    if any(row["state"] in ACTIVE_STATES for row in rows):
        raise CancellationError(
            "cancellation remains indeterminate; recovery refuses to reissue scancel"
        )
    cancelled = [row for row in rows if row["state"] == "CANCELLED"]
    determination = (
        "recovered-terminal-cancelled" if cancelled
        else "recovered-terminal-without-cancelled"
    )
    digest = _write_receipt(
        intent_sha256=intent_sha,
        attempt_raw=attempt_raw,
        attempt=attempt,
        determination=determination,
        returncode=None,
        stdout=None,
        stderr=None,
        post_rows=rows,
        recovered=True,
    )
    print(json.dumps({
        "job_id": JOB_ID,
        "receipt_recovered_without_reissue": True,
        "receipt_sha256": digest,
    }, sort_keys=True, indent=2))


def _validate_receipt(
    receipt_raw: bytes,
    receipt: dict,
    *,
    intent_sha256: str,
    attempt_raw: bytes,
    attempt: dict,
) -> None:
    snapshot = receipt.get("post_cancel_scheduler_snapshot")
    snapshot_rows = _validate_snapshot(snapshot)
    _validate_monotonic_transition(
        attempt["pre_cancel_scheduler_snapshot"]["rows"],
        snapshot_rows,
        allow_cancelled=True,
    )
    normal = (
        receipt.get("determination") == "scancel-returned-zero"
        and receipt.get("returncode") == 0
        and receipt.get("recovered_without_reissue") is False
    )
    recovered = (
        receipt.get("determination") == "recovered-terminal-cancelled"
        and receipt.get("returncode") is None
        and receipt.get("recovered_without_reissue") is True
    )
    if (
        set(receipt) != {
            "schema", "recorded_utc", "job_id", "repository_commit_id",
            "intent_path", "intent_sha256",
            "intent_scheduler_snapshot_sha256",
            "attempt_path", "attempt_sha256",
            "pre_cancel_scheduler_snapshot_sha256",
            "scancel", "argv", "controlled_environment", "determination",
            "returncode", "stdout_sha256", "stderr_sha256",
            "post_cancel_scheduler_snapshot",
            "post_cancel_scheduler_snapshot_sha256",
            "recovered_without_reissue", "resubmitted", "selective_cancel",
        }
        or receipt.get("schema") != RECEIPT_SCHEMA
        or not isinstance(receipt.get("recorded_utc"), str)
        or receipt.get("job_id") != JOB_ID
        or receipt.get("repository_commit_id") != attempt["repository_commit_id"]
        or receipt.get("intent_path") != str(INTENT)
        or receipt.get("intent_sha256") != intent_sha256
        or receipt.get("intent_scheduler_snapshot_sha256")
        != attempt["intent_scheduler_snapshot_sha256"]
        or receipt.get("attempt_path") != str(ATTEMPT)
        or receipt.get("attempt_sha256") != hashlib.sha256(attempt_raw).hexdigest()
        or receipt.get("pre_cancel_scheduler_snapshot_sha256")
        != attempt["pre_cancel_scheduler_snapshot_sha256"]
        or receipt.get("scancel") != {
            "path": str(SCANCEL), "sha256": SCANCEL_SHA256,
        }
        or receipt.get("argv") != SCANCEL_ARGV
        or receipt.get("controlled_environment") != CONTROLLED_ENV
        or not (normal or recovered)
        or not Source._is_sha256(receipt.get("stdout_sha256"))
        or not Source._is_sha256(receipt.get("stderr_sha256"))
        or receipt.get("post_cancel_scheduler_snapshot_sha256")
        != _digest_json(snapshot)
        or receipt.get("resubmitted") is not False
        or receipt.get("selective_cancel") is not False
        or receipt_raw != _canonical(receipt)
    ):
        raise CancellationError("v4 cancellation receipt changed")


def _cancelled_accounting_rows(cancelled_tasks: list[int]) -> list[dict]:
    result = []
    for task in cancelled_tasks:
        output = _sacct([
            "-j", "{}_{}".format(JOB_ID, task), "-n", "-P",
            "--format=JobID,JobIDRaw,State,ExitCode,Elapsed,ReqMem,NodeList,Reason",
        ])
        rows = []
        prefix = "{}_{}".format(JOB_ID, task)
        for line in output.splitlines():
            fields = line.split("|")
            if len(fields) != 8:
                raise CancellationError("cancelled accounting row changed")
            job_id, raw_id, state, exit_code, elapsed, req_mem, nodes, reason = fields
            if not job_id.startswith(prefix):
                continue
            rows.append({
                "job_id": job_id,
                "job_id_raw": raw_id,
                "state": state.split("+", 1)[0].split()[0],
                "exit_code": exit_code,
                "elapsed": elapsed,
                "requested_memory": req_mem or None,
                "node_list": nodes or None,
                "reason": reason or None,
            })
        parent = [row for row in rows if row["job_id"] == prefix]
        if len(parent) != 1 or parent[0]["state"] != "CANCELLED":
            raise CancellationError("cancelled parent accounting row changed")
        result.append({"array_task": task, "rows": rows})
    return result


def validate_terminal_cancellation(rows: list[dict]) -> dict:
    """Validate cancellation artifacts and pin every cancelled task row.

    The caller must supply the already validated full parent-array snapshot.
    No successful or cancelled Slurm log is opened here; only actual
    FAILED/OOM trigger logs are read after all scheduler states and artifact
    identities have been validated.
    """
    snapshot = _snapshot(rows)
    _validate_snapshot(snapshot, terminal=True)
    cancelled_tasks = [
        row["array_task"] for row in rows if row["state"] == "CANCELLED"
    ]
    if not cancelled_tasks:
        raise CancellationError("terminal v4 snapshot has no cancelled tasks")
    intent_raw, intent = _load_intent(verify_live_triggers=False)
    intent_sha = hashlib.sha256(intent_raw).hexdigest()
    attempt_raw, attempt = _load_attempt(intent_sha)
    if (
        attempt.get("intent_scheduler_snapshot_sha256")
        != intent.get("scheduler_snapshot_sha256")
    ):
        raise CancellationError("attempt does not bind the intent scheduler snapshot")
    _validate_monotonic_transition(
        intent["scheduler_snapshot"]["rows"],
        attempt["pre_cancel_scheduler_snapshot"]["rows"],
    )
    receipt_raw, receipt = _load_json(RECEIPT, "v4 cancellation receipt")
    _validate_receipt(
        receipt_raw,
        receipt,
        intent_sha256=intent_sha,
        attempt_raw=attempt_raw,
        attempt=attempt,
    )
    _validate_monotonic_transition(
        receipt["post_cancel_scheduler_snapshot"]["rows"],
        rows,
        allow_cancelled=True,
    )
    _validate_recorded_commit(
        attempt["repository_commit_id"], intent_raw, intent
    )
    if _trigger_evidence(rows, allow_cancelled=True) != intent["authorized_triggers"]:
        raise CancellationError("terminal v4 trigger evidence changed")
    accounting = _cancelled_accounting_rows(cancelled_tasks)
    return {
        "intent_path": str(INTENT),
        "intent_sha256": intent_sha,
        "attempt_path": str(ATTEMPT),
        "attempt_sha256": hashlib.sha256(attempt_raw).hexdigest(),
        "receipt_path": str(RECEIPT),
        "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "repository_commit_id": attempt["repository_commit_id"],
        "job_id": JOB_ID,
        "argv": SCANCEL_ARGV,
        "scancel": {"path": str(SCANCEL), "sha256": SCANCEL_SHA256},
        "cancelled_array_tasks": cancelled_tasks,
        "cancelled_scheduler_rows": [rows[task] for task in cancelled_tasks],
        "cancelled_scheduler_rows_sha256": _digest_json(
            [rows[task] for task in cancelled_tasks]
        ),
        "cancelled_accounting_rows": accounting,
        "cancelled_accounting_rows_sha256": _digest_json(accounting),
        "cancelled_or_completed_logs_read": False,
        "reused_v1_shards": 0,
        "reused_v2_shards": 0,
        "reused_v3_shards": 0,
        "reused_v4_shards": 0,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "prepare-cancel-intent", "cancel-v4", "recover-cancel-receipt",
    ))
    command = parser.parse_args(argv).command
    {
        "prepare-cancel-intent": prepare_cancel_intent,
        "cancel-v4": cancel_v4,
        "recover-cancel-receipt": recover_cancel_receipt,
    }[command]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CancellationError as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
