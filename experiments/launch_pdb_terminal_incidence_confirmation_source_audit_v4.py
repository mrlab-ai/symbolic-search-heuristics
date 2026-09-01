#!/usr/bin/env python3
"""Diagnose v3, then launch, monitor, and seal full source audit v4."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources_v4 as Source
import pdb_terminal_incidence_confirmation_inventory as Inventory


_LEGACY_PATH = (
    SCRIPT_DIR / "launch_pdb_terminal_incidence_confirmation_source_audit_v3.py"
)
_LEGACY_SPEC = importlib.util.spec_from_file_location(
    "_pdb_terminal_incidence_confirmation_source_launch_v4_shared",
    _LEGACY_PATH,
)
if _LEGACY_SPEC is None or _LEGACY_SPEC.loader is None:
    raise RuntimeError("cannot load frozen campaign-v3 launch helpers")
Legacy = importlib.util.module_from_spec(_LEGACY_SPEC)
sys.modules[_LEGACY_SPEC.name] = Legacy
_LEGACY_SPEC.loader.exec_module(Legacy)
_SHARED_LOAD_INTENT = Legacy.Base._load_intent_only
_SHARED_LOAD_LAUNCH = Legacy.Base._load_launch
_SHARED_STATUS = Legacy.Base.status


class LaunchAuditError(RuntimeError):
    pass


SLURM_SCRIPT = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v4.slurm"
)
CODE_MANIFEST = Source.DEFAULT_CODE_MANIFEST
OUTPUT_DIR = Source.DEFAULT_SHARDS
SOURCE_INVENTORY = Source.DEFAULT_INVENTORY
CANDIDATE = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v4_candidate.json"
)
ATTESTATION = Source.DEFAULT_OUTPUT
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v4"
)
V3_DIAGNOSTIC = Source.V3_DIAGNOSTIC
INTENT = ARTIFACT_DIR / "source-audit-launch-intent-v4.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-launch-receipt-v4.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v4.json"
LAUNCH_SCHEMA = Source.SCHEMA + "/campaign-v4/launch"
EXECUTION_SCHEMA = Source.SCHEMA + "/campaign-v4/execution"
V3_DIAGNOSTIC_SCHEMA = Source.SCHEMA + "/campaign-v4/v3-infrastructure-diagnostic"
ARRAY_TASKS = Source.SHARD_COUNT
ACCOUNT = "naiss2025-5-561-cpu"
MEMORY_PER_CPU = "1024G"
TIME_LIMIT = "08:20:00"
V3_TIME_LIMIT = "04:10:00"
V3_TASK_TIMEOUT_SECONDS = 7200
CONTROLLED_PATH = Source.CONTROLLED_PATH
UNSET_PYTHON_ENV = Source.UNSET_PYTHON_ENV
PYTHON_COMMAND = (
    SCRIPT_DIR / "data" / "pdb-terminal-incidence-shadow-venv" /
    "bin" / "python"
)
SBATCH_COMMAND = Path("/usr/bin/sbatch")
SBATCH_COMMAND_SHA256 = (
    "efbb8e172acc7ed768430740d04e19cc07a3ac4701b005d1a997c08424bde741"
)
SACCT_COMMAND = Path("/usr/bin/sacct")
SACCT_COMMAND_SHA256 = (
    "58f3976b19baa2bc26772a92ab224dd0c1bf0ab3d9b675d85aa3e4636c836315"
)
SHA256SUM_COMMAND = Source.SHA256SUM_COMMAND
SUBMISSION_ENVIRONMENT = {"LANG": "C", "LC_ALL": "C", "PATH": CONTROLLED_PATH}
JOB_NAME_PREFIX = "confirmation-source-audit-v4"
COMMENT_PREFIX = "confirmation-source-audit-v4"
MANIFEST_ASSIGNMENT_RE = re.compile(
    r'^code_manifest_sha256="([0-9a-f]{64})"$'
)

V3_JOB_ID = "1863146"
V3_OUTPUT_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v3"
)
V3_LAUNCH_INTENT = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v3" /
    "source-audit-launch-intent-v3.json"
)
V3_LAUNCH_INTENT_SHA256 = (
    "a56c06abb85a8d7f1498505bb7564495ed286599cf99fea5fa93863f4a029cc7"
)
V3_LAUNCH_RECEIPT = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v3" /
    "source-audit-launch-receipt-v3.json"
)
V3_LAUNCH_RECEIPT_SHA256 = (
    "c331b7a42acd911f9b4a17b8a4999037874b105f2a9c8e6df7f11667d830e76e"
)
V3_CODE_MANIFEST = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v3_code.sha256"
)
V3_CODE_MANIFEST_SHA256 = (
    "7577f375bcba062417bef2c651016e5e69d27e145f24ff5770ff53199690f21f"
)
V3_SLURM_SCRIPT = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v3.slurm"
)
V3_SLURM_SCRIPT_SHA256 = (
    "5eb4b8ff62eb40797cfa39d9b49e1bbf425ad242bcc24052a7834a92a2804de9"
)
SOURCE_INVENTORY_SHA256 = (
    "bb9be49a4652ff7bedcadb04b4db35cad701a5b2a2a6d6347c15e0ad670e056e"
)

# SHA256 of the complete Slurm file after replacing only the embedded code
# manifest digest with 64 zeroes.  This avoids a manifest/Slurm hash cycle.
NORMALIZED_SLURM_SHA256 = (
    "bc1c6786120aae4848a906af0a71d9b2ecdfa14393208821cfd83a40bc070a36"
)

SCOPED_COMMIT_FILES = tuple(sorted({
    *Source.CODE_MANIFEST_FILES,
    SLURM_SCRIPT.relative_to(REPO).as_posix(),
    CODE_MANIFEST.relative_to(REPO).as_posix(),
}))

# Campaign v3 already hardened the generic Slurm accounting, submission
# journal, exact-resource, and scoped-jj checks.  Load those frozen helpers in
# a private module and change only their campaign constants; v3 itself remains
# byte-for-byte untouched and unaffected in other Python processes.
for _name, _value in {
    "SLURM_SCRIPT": SLURM_SCRIPT,
    "CODE_MANIFEST": CODE_MANIFEST,
    "OUTPUT_DIR": OUTPUT_DIR,
    "SOURCE_INVENTORY": SOURCE_INVENTORY,
    "CANDIDATE": CANDIDATE,
    "ATTESTATION": ATTESTATION,
    "ARTIFACT_DIR": ARTIFACT_DIR,
    "INTENT": INTENT,
    "LAUNCH_RECEIPT": LAUNCH_RECEIPT,
    "EXECUTION_RECEIPT": EXECUTION_RECEIPT,
    "LAUNCH_SCHEMA": LAUNCH_SCHEMA,
    "EXECUTION_SCHEMA": EXECUTION_SCHEMA,
    "MEMORY_PER_CPU": MEMORY_PER_CPU,
    "TIME_LIMIT": TIME_LIMIT,
    "JOB_NAME_PREFIX": JOB_NAME_PREFIX,
    "COMMENT_PREFIX": COMMENT_PREFIX,
    "SCOPED_COMMIT_FILES": SCOPED_COMMIT_FILES,
}.items():
    setattr(Legacy, _name, _value)

for _name, _value in {
    "Source": Source,
    "Inventory": Inventory,
    "SLURM_SCRIPT": SLURM_SCRIPT,
    "CODE_MANIFEST": CODE_MANIFEST,
    "OUTPUT_DIR": OUTPUT_DIR,
    "SOURCE_INVENTORY": SOURCE_INVENTORY,
    "CANDIDATE": CANDIDATE,
    "ATTESTATION": ATTESTATION,
    "ARTIFACT_DIR": ARTIFACT_DIR,
    "INTENT": INTENT,
    "LAUNCH_RECEIPT": LAUNCH_RECEIPT,
    "EXECUTION_RECEIPT": EXECUTION_RECEIPT,
    "LAUNCH_SCHEMA": LAUNCH_SCHEMA,
    "EXECUTION_SCHEMA": EXECUTION_SCHEMA,
    "ARRAY_TASKS": ARRAY_TASKS,
    "ACCOUNT": ACCOUNT,
    "CONTROLLED_PATH": CONTROLLED_PATH,
    "UNSET_PYTHON_ENV": UNSET_PYTHON_ENV,
    "PYTHON_COMMAND": PYTHON_COMMAND,
    "SHA256SUM_COMMAND": SHA256SUM_COMMAND,
}.items():
    setattr(Legacy.Base, _name, _value)


def _sha256(path: Path) -> str:
    return Source.sha256_file(path)


def _exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    try:
        return Source.atomic_exclusive_bytes(path, raw, label)
    except Source.SourceAuditError as err:
        raise LaunchAuditError(str(err)) from err


def _exclusive_json(path: Path, value, label: str) -> str:
    return _exclusive_bytes(path, Source.canonical_json(value), label)


def _load_json(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        info = path.lstat()
        raw = path.read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise LaunchAuditError("cannot load {}".format(label)) from err
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or not isinstance(value, dict)
        or raw != Source.canonical_json(value)
    ):
        raise LaunchAuditError("{} is not canonical and regular".format(label))
    return raw, value


def _directory_identity(
    path: Path, label: str, *, require_empty: bool = False
) -> dict:
    try:
        identity = Source._directory_identity(Path(path), label)
        children = list(Path(path).iterdir()) if require_empty else None
    except Source.SourceAuditError as err:
        raise LaunchAuditError(str(err)) from err
    except OSError as err:
        raise LaunchAuditError("cannot inspect {}".format(label)) from err
    if require_empty and children:
        raise LaunchAuditError("{} is not empty".format(label))
    return identity


def _require_directory_identity(
    path: Path, expected: dict, label: str, *, require_empty: bool = False
) -> dict:
    actual = _directory_identity(path, label, require_empty=require_empty)
    if actual != expected:
        raise LaunchAuditError("{} was replaced".format(label))
    return actual


def _create_private_directory(path: Path, label: str) -> dict:
    path = Path(path)
    try:
        Source._assert_no_symlink_components(path.parent, "{} parent".format(label))
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
        # The project data directory is setgid.  Linux propagates that bit to
        # newly created subdirectories even when mkdir requests mode 0700, so
        # clear inherited special bits before recording the exact identity.
        path.chmod(0o700, follow_symlinks=False)
    except Source.SourceAuditError as err:
        raise LaunchAuditError(str(err)) from err
    except OSError as err:
        raise LaunchAuditError("cannot create {}".format(label)) from err
    return _directory_identity(path, label)


def _live_launch_root_identities(*, require_empty_tmp: bool = False) -> dict:
    return {
        "output_dir": _directory_identity(
            OUTPUT_DIR, "v4 output directory"
        ),
        "tmpdir_root": _directory_identity(
            Source.TMP_ROOT,
            "v4 TMPDIR root",
            require_empty=require_empty_tmp,
        ),
    }


def _require_launch_root_identities(
    expected: dict, *, require_empty_tmp: bool = False
) -> dict:
    if (
        not isinstance(expected, dict)
        or set(expected) != {"output_dir", "tmpdir_root"}
    ):
        raise LaunchAuditError("v4 launch root identities are invalid")
    actual = _live_launch_root_identities(
        require_empty_tmp=require_empty_tmp
    )
    if actual != expected:
        raise LaunchAuditError("v4 launch root was replaced")
    return actual


def _executable_identity(
    path: Path, expected_sha256: str, label: str
) -> dict:
    try:
        info = path.lstat()
    except OSError as err:
        raise LaunchAuditError("cannot inspect {}".format(label)) from err
    if (
        not path.is_absolute()
        or path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or not os.access(path, os.X_OK)
        or _sha256(path) != expected_sha256
    ):
        raise LaunchAuditError("pinned {} identity changed".format(label))
    return {"path": str(path), "sha256": expected_sha256}


def _sacct(command: list[str]) -> str:
    _executable_identity(SACCT_COMMAND, SACCT_COMMAND_SHA256, "sacct")
    try:
        return subprocess.check_output(
            command, env=dict(SUBMISSION_ENVIRONMENT), text=True
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot query source-audit accounting") from err


def _scheduler_rows(job_id: str) -> list[dict]:
    try:
        return Legacy._scheduler_rows(job_id)
    except Legacy.LaunchAuditError as err:
        raise LaunchAuditError(str(err)) from err


def _v3_fixed_launch_provenance() -> dict:
    intent_raw, _ = _load_json(V3_LAUNCH_INTENT, "v3 launch intent")
    receipt_raw, receipt = _load_json(V3_LAUNCH_RECEIPT, "v3 launch receipt")
    fixed_files = {
        "launch_intent": (V3_LAUNCH_INTENT, V3_LAUNCH_INTENT_SHA256),
        "launch_receipt": (V3_LAUNCH_RECEIPT, V3_LAUNCH_RECEIPT_SHA256),
        "code_manifest": (V3_CODE_MANIFEST, V3_CODE_MANIFEST_SHA256),
        "slurm_script": (V3_SLURM_SCRIPT, V3_SLURM_SCRIPT_SHA256),
    }
    if any(_sha256(path) != expected for path, expected in fixed_files.values()):
        raise LaunchAuditError("v3 launch/source bytes changed")
    if (
        hashlib.sha256(intent_raw).hexdigest() != V3_LAUNCH_INTENT_SHA256
        or hashlib.sha256(receipt_raw).hexdigest() != V3_LAUNCH_RECEIPT_SHA256
        or receipt.get("job_id") != V3_JOB_ID
        or receipt.get("campaign") != "v3"
        or receipt.get("whole_campaign_rerun") is not True
        or receipt.get("array") != "0-819"
        or receipt.get("array_tasks") != ARRAY_TASKS
        or receipt.get("candidates") != Source.CANDIDATE_COUNT
        or receipt.get("partition") != "fat"
        or receipt.get("qos") != "normal"
        or receipt.get("account") != ACCOUNT
        or receipt.get("cpus_per_task") != 1
        or receipt.get("memory_per_cpu") != "512G"
        or receipt.get("time_limit") != V3_TIME_LIMIT
        or receipt.get("task_timeout_seconds") != V3_TASK_TIMEOUT_SECONDS
        or receipt.get("array_throttle") != 0
        or receipt.get("reused_v1_shards") != 0
        or receipt.get("reused_v2_shards") != 0
        or receipt.get("source_inventory_sha256") != SOURCE_INVENTORY_SHA256
        or receipt.get("code_manifest_sha256") != V3_CODE_MANIFEST_SHA256
        or receipt.get("slurm_script_sha256") != V3_SLURM_SCRIPT_SHA256
    ):
        raise LaunchAuditError("v3 launch receipt identity changed")
    return {
        "v3_job_id": V3_JOB_ID,
        "v3_launch_intent_path": str(V3_LAUNCH_INTENT),
        "v3_launch_intent_sha256": V3_LAUNCH_INTENT_SHA256,
        "v3_launch_receipt_path": str(V3_LAUNCH_RECEIPT),
        "v3_launch_receipt_sha256": V3_LAUNCH_RECEIPT_SHA256,
        "v3_code_manifest_path": str(V3_CODE_MANIFEST),
        "v3_code_manifest_sha256": V3_CODE_MANIFEST_SHA256,
        "v3_slurm_script_path": str(V3_SLURM_SCRIPT),
        "v3_slurm_script_sha256": V3_SLURM_SCRIPT_SHA256,
        "v3_source_inventory_sha256": SOURCE_INVENTORY_SHA256,
    }


def _v3_oom_resource_rows(tasks: list[int]) -> list[dict]:
    records = []
    for task in tasks:
        output = _sacct([
            str(SACCT_COMMAND), "-j", "{}_{}".format(V3_JOB_ID, task),
            "-n", "-P",
            "--format=JobID,JobIDRaw,State,ExitCode,ReqMem,MaxRSS,MaxVMSize",
        ])
        task_rows = []
        for line in output.splitlines():
            fields = line.split("|")
            if len(fields) != 7:
                raise LaunchAuditError("v3 OOM accounting row changed")
            job_id, raw_id, state, exit_code, req_mem, max_rss, max_vm = fields
            if not job_id.startswith("{}_{}".format(V3_JOB_ID, task)):
                continue
            task_rows.append({
                "job_id": job_id,
                "job_id_raw": raw_id,
                "state": state.split("+", 1)[0].split()[0],
                "exit_code": exit_code,
                "requested_memory": req_mem or None,
                "max_rss": max_rss or None,
                "max_vm_size": max_vm or None,
            })
        parent = [row for row in task_rows if row["job_id"] == "{}_{}".format(
            V3_JOB_ID, task
        )]
        batch = [row for row in task_rows if row["job_id"].endswith(".batch")]
        if (
            len(parent) != 1
            or len(batch) != 1
            or parent[0]["state"] != "OUT_OF_MEMORY"
            or parent[0]["exit_code"] != "0:125"
            or parent[0]["requested_memory"] != "512G"
            or batch[0]["state"] != "OUT_OF_MEMORY"
            or batch[0]["exit_code"] != "0:125"
            or re.fullmatch(r"[1-9][0-9]*K", batch[0]["max_rss"] or "") is None
            or re.fullmatch(r"[1-9][0-9]*K", batch[0]["max_vm_size"] or "") is None
        ):
            raise LaunchAuditError("v3 OOM resource evidence changed")
        records.append({"array_task": task, "rows": task_rows})
    return records


def _v3_timeout_resource_rows(tasks: list[int]) -> list[dict]:
    records = []
    for task in tasks:
        output = _sacct([
            str(SACCT_COMMAND), "-j", "{}_{}".format(V3_JOB_ID, task),
            "-n", "-P",
            "--format=JobID,JobIDRaw,State,ExitCode,Elapsed,ReqMem,"
            "MaxRSS,MaxVMSize",
        ])
        task_rows = []
        for line in output.splitlines():
            fields = line.split("|")
            if len(fields) != 8:
                raise LaunchAuditError("v3 timeout accounting row changed")
            (
                job_id, raw_id, state, exit_code, elapsed, req_mem,
                max_rss, max_vm,
            ) = fields
            if not job_id.startswith("{}_{}".format(V3_JOB_ID, task)):
                continue
            task_rows.append({
                "job_id": job_id,
                "job_id_raw": raw_id,
                "state": state.split("+", 1)[0].split()[0],
                "exit_code": exit_code,
                "elapsed": elapsed,
                "requested_memory": req_mem or None,
                "max_rss": max_rss or None,
                "max_vm_size": max_vm or None,
            })
        parent = [row for row in task_rows if row["job_id"] == "{}_{}".format(
            V3_JOB_ID, task
        )]
        batch = [row for row in task_rows if row["job_id"].endswith(".batch")]
        if (
            len(parent) != 1
            or len(batch) != 1
            or parent[0]["state"] != "FAILED"
            or parent[0]["exit_code"] != "75:0"
            or parent[0]["requested_memory"] != "512G"
            or re.fullmatch(r"[0-9]+:[0-9]{2}:[0-9]{2}", parent[0]["elapsed"])
            is None
            or batch[0]["state"] != "FAILED"
            or batch[0]["exit_code"] != "75:0"
            or re.fullmatch(r"[1-9][0-9]*K", batch[0]["max_rss"] or "") is None
            or re.fullmatch(r"[1-9][0-9]*K", batch[0]["max_vm_size"] or "")
            is None
        ):
            raise LaunchAuditError("v3 translator-timeout evidence changed")
        records.append({"array_task": task, "rows": task_rows})
    return records


def _expected_v3_diagnostic() -> dict:
    provenance = _v3_fixed_launch_provenance()
    rows = _scheduler_rows(V3_JOB_ID)
    active = {
        "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
        "RESIZING", "SUSPENDED",
    }
    if any(row["state"] in active for row in rows):
        raise LaunchAuditError("v3 source-audit array is not fully terminal")
    failure_logs = []
    enospc_tasks = []
    oom_tasks = []
    timeout_tasks = []
    timeout_enospc_tasks = []
    task_line_re = re.compile(rb"^\[[12]/2\] ([^\r\n]+)\r?$", re.MULTILINE)
    for row in rows:
        state = row["state"]
        if state == "COMPLETED" and row["exit_code"] == "0:0":
            continue
        path = V3_OUTPUT_DIR / "slurm-{}_{}.out".format(
            V3_JOB_ID, row["array_task"]
        )
        try:
            info = path.lstat()
            payload = path.read_bytes()
        except OSError as err:
            raise LaunchAuditError("cannot read v3 failure log") from err
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise LaunchAuditError("v3 failure log is not regular")
        task_matches = task_line_re.findall(payload)
        if not task_matches:
            raise LaunchAuditError("v3 failure task identity is absent")
        try:
            task_name = task_matches[-1].decode("ascii")
        except UnicodeDecodeError as err:
            raise LaunchAuditError("v3 failure task identity changed") from err
        timeout_wrappers = re.findall(
            rb"infrastructure error: translator exceeded 7200s for "
            + re.escape(task_name.encode("ascii"))
            + rb"; stderr_sha256=([0-9a-f]{64}); stderr_tail='([^\r\n]*)'",
            payload,
        )
        if (
            state == "FAILED"
            and row["exit_code"] == "2:0"
            and b"OSError: [Errno 28] No space left on device" in payload
            and b"sas_task.output(output_file)" in payload
        ):
            failure_class = "compute-node-tmp-enospc-writing-output-sas"
            enospc_tasks.append(row["array_task"])
        elif (
            state == "OUT_OF_MEMORY"
            and row["exit_code"] == "0:125"
            and b"translator critical exit -9" in payload
            and b"oom_kill" in payload
        ):
            failure_class = "scheduler-out-of-memory"
            oom_tasks.append(row["array_task"])
        elif (
            state == "FAILED"
            and row["exit_code"] == "75:0"
            and timeout_wrappers == [(
                hashlib.sha256(b"").hexdigest().encode("ascii"), b"",
            )]
        ):
            failure_class = "translator-wallclock-timeout"
            timeout_tasks.append(row["array_task"])
        elif (
            state == "FAILED"
            and row["exit_code"] == "75:0"
            and len(timeout_wrappers) == 1
            and timeout_wrappers[0][0]
            != hashlib.sha256(b"").hexdigest().encode("ascii")
            and b"OSError: [Errno 28] No space left on device"
            in timeout_wrappers[0][1]
            and b"sas_task.output(output_file)" in timeout_wrappers[0][1]
        ):
            failure_class = "translator-timeout-with-compute-node-tmp-enospc"
            timeout_enospc_tasks.append(row["array_task"])
        else:
            raise LaunchAuditError(
                "v3 has an unclassified terminal failure at task {}".format(
                    row["array_task"]
                )
            )
        failure_logs.append({
            "array_task": row["array_task"],
            "state": state,
            "exit_code": row["exit_code"],
            "task_name": task_name,
            "failure_class": failure_class,
            "path": str(path),
            "bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    if (
        not enospc_tasks
        or not oom_tasks
        or not timeout_tasks
        or not timeout_enospc_tasks
    ):
        raise LaunchAuditError("v3 diagnoses do not support all v4 amendments")
    states = dict(sorted(Counter(row["state"] for row in rows).items()))
    oom_resources = _v3_oom_resource_rows(oom_tasks)
    all_timeout_tasks = sorted(timeout_tasks + timeout_enospc_tasks)
    timeout_resources = _v3_timeout_resource_rows(all_timeout_tasks)
    return {
        "schema": V3_DIAGNOSTIC_SCHEMA,
        **provenance,
        "v3_scheduler_rows": rows,
        "v3_scheduler_rows_sha256": hashlib.sha256(
            Source.canonical_json(rows)
        ).hexdigest(),
        "v3_scheduler_state_counts": states,
        "v3_failure_logs": failure_logs,
        "v3_failure_logs_sha256": hashlib.sha256(
            Source.canonical_json(failure_logs)
        ).hexdigest(),
        "v3_enospc_array_tasks": enospc_tasks,
        "v3_out_of_memory_array_tasks": oom_tasks,
        "v3_translator_timeout_array_tasks": all_timeout_tasks,
        "v3_pure_translator_timeout_array_tasks": timeout_tasks,
        "v3_translator_timeout_with_enospc_array_tasks": timeout_enospc_tasks,
        "v3_oom_scheduler_resource_rows": oom_resources,
        "v3_oom_scheduler_resource_rows_sha256": hashlib.sha256(
            Source.canonical_json(oom_resources)
        ).hexdigest(),
        "v3_timeout_scheduler_resource_rows": timeout_resources,
        "v3_timeout_scheduler_resource_rows_sha256": hashlib.sha256(
            Source.canonical_json(timeout_resources)
        ).hexdigest(),
        "failure_classes": [
            "compute-node-tmp-enospc-writing-output-sas",
            "scheduler-out-of-memory",
            "translator-wallclock-timeout",
            "translator-timeout-with-compute-node-tmp-enospc",
        ],
        "inspection_scope": (
            "all v3 scheduler rows, OOM scheduler resource rows, and only "
            "non-success v3 Slurm logs"
        ),
        "successful_v3_shard_contents_inspected": False,
        "successful_v3_log_contents_inspected": False,
        "source_support_outcomes_used_for_v4_design": False,
        "resource_amendment": {
            "temporary_storage": {
                "from": "/tmp via Python tempfile",
                "to": Source.TMPDIR_TEMPLATE,
                "reason": (
                    "v3 ENOSPC while the translator serialized output.sas"
                ),
                "cleanup": "per-task EXIT trap using pinned rmdir only",
            },
            "memory_per_cpu": {
                "from": "512G",
                "to": MEMORY_PER_CPU,
                "factor": 2,
                "reason": (
                    "v3 scheduler OOM at 512G; batch MaxRSS and MaxVMSize "
                    "are pinned above"
                ),
            },
            "task_timeout_seconds": {
                "from": V3_TASK_TIMEOUT_SECONDS,
                "to": Source.TASK_TIMEOUT_SECONDS,
                "factor": 2,
                "reason": (
                    "v3 translator exceeded its 7200-second source limit; "
                    "task/log/accounting evidence is pinned above"
                ),
            },
            "time_limit": {
                "from": V3_TIME_LIMIT,
                "to": TIME_LIMIT,
                "factor": 2,
                "reason": "preserve scheduler headroom for doubled source limit",
            },
        },
        "full_rerun_decision": {
            "scope": "all-820-original-shards-and-1640-candidates",
            "whole_campaign_rerun": True,
            "reused_v1_shards": 0,
            "reused_v2_shards": 0,
            "reused_v3_shards": 0,
        },
    }


def diagnose_v3() -> None:
    if V3_DIAGNOSTIC.exists():
        raise LaunchAuditError("v3 infrastructure diagnostic already exists")
    if any(path.exists() for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR,
        Source.TMP_ROOT, CANDIDATE, ATTESTATION,
    )):
        raise LaunchAuditError("v4 namespace is not empty before diagnosis")
    diagnostic = _expected_v3_diagnostic()
    digest = _exclusive_json(
        V3_DIAGNOSTIC, diagnostic, "v3 infrastructure diagnostic"
    )
    print(json.dumps({
        "v3_diagnostic_sha256": digest,
        "v3_enospc_array_tasks": diagnostic["v3_enospc_array_tasks"],
        "v3_out_of_memory_array_tasks": (
            diagnostic["v3_out_of_memory_array_tasks"]
        ),
        "v3_translator_timeout_array_tasks": (
            diagnostic["v3_translator_timeout_array_tasks"]
        ),
    }, sort_keys=True, indent=2))


def _load_v3_diagnostic() -> tuple[str, dict]:
    raw, diagnostic = _load_json(V3_DIAGNOSTIC, "v3 infrastructure diagnostic")
    if diagnostic != _expected_v3_diagnostic():
        raise LaunchAuditError("v3 infrastructure diagnostic changed")
    return hashlib.sha256(raw).hexdigest(), diagnostic


def _execution_environment(code: dict) -> dict:
    python_identity = _executable_identity(
        PYTHON_COMMAND.resolve(strict=True),
        code.get("python_executable_sha256"),
        "Python",
    )
    if python_identity["path"] != code.get("python_executable"):
        raise LaunchAuditError("source-audit Python executable changed")
    sha_identity = _executable_identity(
        SHA256SUM_COMMAND, Source.SHA256SUM_SHA256, "sha256sum"
    )
    mkdir_identity = _executable_identity(
        Source.MKDIR_COMMAND, Source.MKDIR_SHA256, "mkdir"
    )
    rmdir_identity = _executable_identity(
        Source.RMDIR_COMMAND, Source.RMDIR_SHA256, "rmdir"
    )
    return {
        "submission_export": "NONE",
        "slurm_export": "NONE",
        "unset_variables": list(UNSET_PYTHON_ENV),
        "python_no_user_site": "1",
        "python_no_user_site_flag": 1,
        "python_dont_write_bytecode": "1",
        "python_dont_write_bytecode_flag": True,
        "tmpdir_root": str(Source.TMP_ROOT),
        "tmpdir_template": Source.TMPDIR_TEMPLATE,
        "python_tempfile_directory_template": Source.TMPDIR_TEMPLATE,
        "python_pycache_prefix_template": Source.PYTHON_CACHE_PREFIX_TEMPLATE,
        "tmpdir_mode": "0700",
        "tmpdir_cleanup": "EXIT trap with pinned /usr/bin/rmdir; no recursion",
        "root_identity_policy": (
            "canonical absolute path; no direct/ancestor symlinks; mode 0700; "
            "launch uid/device/inode retained"
        ),
        "source_snapshot_policy": Source.SOURCE_SNAPSHOT_POLICY,
        "outer_python_flag": "-B",
        "path": CONTROLLED_PATH,
        "translator_child_environment": {
            "PATH": CONTROLLED_PATH,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": Source.TMPDIR_TEMPLATE,
            "PYTHONPYCACHEPREFIX": Source.PYTHON_CACHE_PREFIX_TEMPLATE,
            "PYTHONPATH": str(REPO / "src"),
        },
        "python_command": str(PYTHON_COMMAND),
        "python_executable": python_identity["path"],
        "python_executable_sha256": python_identity["sha256"],
        "sha256sum_command": str(SHA256SUM_COMMAND),
        "sha256sum_executable": sha_identity["path"],
        "sha256sum_executable_sha256": sha_identity["sha256"],
        "mkdir_executable": mkdir_identity["path"],
        "mkdir_executable_sha256": mkdir_identity["sha256"],
        "rmdir_executable": rmdir_identity["path"],
        "rmdir_executable_sha256": rmdir_identity["sha256"],
    }


def _slurm_preflight() -> tuple[bytes, str, str, dict]:
    try:
        info = SLURM_SCRIPT.lstat()
        raw = SLURM_SCRIPT.read_bytes()
        lines = raw.decode("ascii").splitlines()
    except (OSError, UnicodeDecodeError) as err:
        raise LaunchAuditError("cannot read v4 Slurm script") from err
    if SLURM_SCRIPT.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise LaunchAuditError("v4 Slurm script is not regular")
    assignments = [
        MANIFEST_ASSIGNMENT_RE.fullmatch(line)
        for line in lines if line.startswith("code_manifest_sha256=")
    ]
    if len(assignments) != 1 or assignments[0] is None:
        raise LaunchAuditError("v4 code manifest is not pinned in Slurm")
    manifest_sha = assignments[0].group(1)
    normalized = raw.replace(manifest_sha.encode("ascii"), b"0" * 64, 1)
    if (
        hashlib.sha256(normalized).hexdigest() != NORMALIZED_SLURM_SHA256
        or raw.count(manifest_sha.encode("ascii")) != 1
    ):
        raise LaunchAuditError("v4 Slurm executable bytes changed")
    ordered_header = [
        "#!/bin/bash",
        "#SBATCH --job-name=confirmation-source-audit-v4",
        "#SBATCH --account={}".format(ACCOUNT),
        "#SBATCH --partition=fat",
        "#SBATCH --qos=normal",
        "#SBATCH --array=0-819",
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --mem-per-cpu={}".format(MEMORY_PER_CPU),
        "#SBATCH --time={}".format(TIME_LIMIT),
        "#SBATCH --output={}/slurm-%A_%a.out".format(OUTPUT_DIR),
        "#SBATCH --export=NONE",
        "",
        "set -euo pipefail",
    ]
    if (
        lines[:len(ordered_header)] != ordered_header
        or any(line.startswith("#SBATCH") for line in lines[len(ordered_header):])
        or "%" in lines[5]
        or any("rm -" in line or "/tmp/" in line for line in lines)
        or lines.count('trap cleanup_tmpdir EXIT') != 1
        or lines.count('    if ! "${rmdir_executable}" -- "${TMPDIR}"; then') != 1
    ):
        raise LaunchAuditError("v4 Slurm resource/tempfile contract changed")
    code = Source.validate_code_manifest(CODE_MANIFEST, manifest_sha)
    environment = _execution_environment(code)
    required = {
        'test "$#" -eq 0',
        'source_inventory_sha256="{}"'.format(SOURCE_INVENTORY_SHA256),
        'source_audit_output_dir="{}"'.format(OUTPUT_DIR),
        'export TMPDIR="${tmpdir_root}/task-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"',
        'export PYTHONPYCACHEPREFIX="${TMPDIR}/pycache"',
        '"${mkdir_executable}" --mode=0700 -- "${TMPDIR}"',
        '    experiments/audit_pdb_terminal_incidence_confirmation_sources_v4.py scan \\',
        '    --task-timeout 14400 \\',
        '    --code-manifest-sha256 "${code_manifest_sha256}"',
    }
    if not required <= set(lines) or any(lines.count(line) != 1 for line in required):
        raise LaunchAuditError("v4 Slurm execution contract changed")
    if any(line in {'source_inventory_sha256="$1"', 'source_audit_output_dir="$2"'}
           for line in lines):
        raise LaunchAuditError("v4 Slurm script accepts runtime path arguments")
    return raw, hashlib.sha256(raw).hexdigest(), manifest_sha, code


def _jj_identity() -> dict:
    try:
        return Legacy._jj_executable_identity()
    except Legacy.LaunchAuditError as err:
        raise LaunchAuditError(str(err)) from err


def _scoped_repository_commit() -> str:
    try:
        return Legacy._scoped_repository_commit()
    except Legacy.LaunchAuditError as err:
        raise LaunchAuditError(str(err)) from err


def _fixed_materials(
    source_inventory_sha256: str,
    repository_commit_id: str | None = None,
    launch_root_identities: dict | None = None,
) -> dict:
    if source_inventory_sha256 != SOURCE_INVENTORY_SHA256:
        raise LaunchAuditError("frozen source inventory hash changed")
    diagnostic_sha, diagnostic = _load_v3_diagnostic()
    slurm_raw, slurm_sha, manifest_sha, code = _slurm_preflight()
    environment = _execution_environment(code)
    if repository_commit_id is None:
        repository_commit_id = _scoped_repository_commit()
    if Legacy.Base.JJ_COMMIT_RE.fullmatch(repository_commit_id or "") is None:
        raise LaunchAuditError("source-audit v4 repository commit is invalid")
    if launch_root_identities is None:
        launch_root_identities = _live_launch_root_identities()
    else:
        _require_launch_root_identities(launch_root_identities)
    jj_identity = _jj_identity()
    sbatch_identity = _executable_identity(
        SBATCH_COMMAND, SBATCH_COMMAND_SHA256, "sbatch"
    )
    sacct_identity = _executable_identity(
        SACCT_COMMAND, SACCT_COMMAND_SHA256, "sacct"
    )
    return {
        "campaign": "v4",
        "whole_campaign_rerun": True,
        "reused_v1_shards": 0,
        "reused_v2_shards": 0,
        "reused_v3_shards": 0,
        "partition": "fat",
        "qos": "normal",
        "account": ACCOUNT,
        "array": "0-819",
        "array_throttle": 0,
        "array_tasks": ARRAY_TASKS,
        "tasks_per_array_task": Source.TASKS_PER_SHARD,
        "candidates": Source.CANDIDATE_COUNT,
        "cpus_per_task": 1,
        "time_limit": TIME_LIMIT,
        "memory_per_cpu": MEMORY_PER_CPU,
        "task_timeout_seconds": Source.TASK_TIMEOUT_SECONDS,
        "benchmark_revision": Inventory.BENCHMARK_REVISION,
        "candidate_records_sha256": Inventory.CANDIDATE_RECORDS_SHA256,
        "alias_groups_sha256": Inventory.ALIAS_GROUPS_SHA256,
        "prior_identity_ledger_sha256": Inventory.PRIOR_IDENTITY_LEDGER_SHA256,
        "prior_family_ledger_sha256": Inventory.PRIOR_FAMILY_LEDGER_SHA256,
        "prior_directory_family_map_sha256": (
            Inventory.PRIOR_DIRECTORY_FAMILY_MAP_SHA256
        ),
        "shadow_unrepresented_family_sequence_sha256": (
            Inventory.SHADOW_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
        ),
        "all_prior_family_sequence_sha256": (
            Inventory.ALL_PRIOR_FAMILY_SEQUENCE_SHA256
        ),
        "all_prior_unrepresented_family_sequence_sha256": (
            Inventory.ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
        ),
        "translator_source_sha256": Source.TRANSLATOR_SOURCE_SHA256,
        "source_inventory_sha256": source_inventory_sha256,
        "source_inventory_path": str(SOURCE_INVENTORY),
        "slurm_script_sha256": slurm_sha,
        "slurm_submission_mode": "stdin",
        "slurm_stdin_sha256": slurm_sha,
        "slurm_stdin_bytes": len(slurm_raw),
        "slurm_path_argument": False,
        "submission_journal_contract": "exact sbatch options-only SubmitLine",
        "code_manifest_sha256": manifest_sha,
        "launcher_sha256": _sha256(Path(__file__)),
        "repository_commit_id": repository_commit_id,
        "scoped_repository_files": list(SCOPED_COMMIT_FILES),
        "jj_executable": jj_identity["path"],
        "jj_executable_sha256": jj_identity["sha256"],
        "sbatch_executable": sbatch_identity["path"],
        "sbatch_executable_sha256": sbatch_identity["sha256"],
        "sacct_executable": sacct_identity["path"],
        "sacct_executable_sha256": sacct_identity["sha256"],
        "submission_environment": dict(SUBMISSION_ENVIRONMENT),
        "output_dir": str(OUTPUT_DIR),
        "tmpdir_root": str(Source.TMP_ROOT),
        "launch_root_identities": launch_root_identities,
        "candidate_attestation": str(CANDIDATE),
        "frozen_attestation": str(ATTESTATION),
        "execution_environment": environment,
        "v3_infrastructure_diagnostic_path": str(V3_DIAGNOSTIC),
        "v3_infrastructure_diagnostic_sha256": diagnostic_sha,
        "v3_infrastructure_diagnostic": diagnostic,
        **{
            key: code[key]
            for key in (
                "python_version", "python_executable",
                "python_executable_sha256", "python_environment_sha256",
                "python_distributions", "python_requirements_sha256",
            )
        },
    }


def _submission_identity(token: str) -> tuple[str, str]:
    try:
        return Legacy._submission_identity(token)
    except Legacy.LaunchAuditError as err:
        raise LaunchAuditError(str(err)) from err


def _submit_command(
    source_inventory_sha256: str, output_dir: Path, token: str
) -> list[str]:
    if source_inventory_sha256 != SOURCE_INVENTORY_SHA256:
        raise LaunchAuditError("frozen source inventory hash changed")
    if Path(output_dir) != OUTPUT_DIR:
        raise LaunchAuditError("v4 output directory changed")
    job_name, comment = _submission_identity(token)
    return [
        str(SBATCH_COMMAND), "--parsable", "--export=NONE",
        "--job-name={}".format(job_name),
        "--comment={}".format(comment),
        "--account={}".format(ACCOUNT),
        "--partition=fat", "--qos=normal", "--array=0-819",
        "--nodes=1", "--ntasks=1", "--cpus-per-task=1",
        "--mem-per-cpu={}".format(MEMORY_PER_CPU),
        "--time={}".format(TIME_LIMIT), "--nice=0", "--no-requeue",
        "--chdir={}".format(REPO),
        "--output={}".format(OUTPUT_DIR / "slurm-%A_%a.out"),
    ]


def _submit_sbatch(command: list[str], materials: dict) -> str:
    raw, slurm_sha, manifest_sha, _ = _slurm_preflight()
    if (
        slurm_sha != materials.get("slurm_stdin_sha256")
        or slurm_sha != materials.get("slurm_script_sha256")
        or len(raw) != materials.get("slurm_stdin_bytes")
        or manifest_sha != materials.get("code_manifest_sha256")
        or materials.get("slurm_submission_mode") != "stdin"
        or materials.get("slurm_path_argument") is not False
        or not isinstance(command, list)
        or not command
        or command[0] != str(SBATCH_COMMAND)
        or any(not option.startswith("--") for option in command[1:])
    ):
        raise LaunchAuditError("v4 Slurm stdin changed before submission")
    _executable_identity(SBATCH_COMMAND, SBATCH_COMMAND_SHA256, "sbatch")
    try:
        completed = subprocess.run(
            command,
            input=raw,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=REPO,
            env=dict(SUBMISSION_ENVIRONMENT),
            check=True,
        )
        output = completed.stdout.decode("ascii").strip()
    except (
        OSError, subprocess.CalledProcessError, UnicodeDecodeError,
    ) as err:
        raise LaunchAuditError("v4 sbatch failed after intent") from err
    return output


def _assert_launch_namespace_empty() -> None:
    if any(os.path.lexists(path) for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR,
        Source.TMP_ROOT, CANDIDATE, ATTESTATION,
    )):
        raise LaunchAuditError("v4 launch namespace is not empty")


def _write_launch_receipt(intent_raw: bytes, intent: dict, job_id: str) -> str:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("Slurm returned an invalid v4 job id")
    excluded = {
        "schema", "recorded_utc", "submission_token", "submit_command",
    }
    materials = {key: value for key, value in intent.items() if key not in excluded}
    receipt = {
        "schema": LAUNCH_SCHEMA,
        **materials,
        "recorded_utc": intent["recorded_utc"],
        "submission_token": intent["submission_token"],
        "submit_command": intent["submit_command"],
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": job_id,
    }
    return _exclusive_json(LAUNCH_RECEIPT, receipt, "v4 launch receipt")


def launch() -> None:
    _assert_launch_namespace_empty()
    inventory = Inventory.load_inventory()
    inventory_value = Source.build_inventory_manifest(inventory)
    inventory_raw = Source.canonical_json(inventory_value)
    inventory_sha = hashlib.sha256(inventory_raw).hexdigest()
    if inventory_sha != SOURCE_INVENTORY_SHA256:
        raise LaunchAuditError("frozen source inventory hash changed")
    output_identity = _create_private_directory(
        OUTPUT_DIR, "v4 output directory"
    )
    tmp_identity = _create_private_directory(
        Source.TMP_ROOT, "v4 TMPDIR root"
    )
    launch_roots = {
        "output_dir": output_identity,
        "tmpdir_root": tmp_identity,
    }
    materials = _fixed_materials(
        inventory_sha, launch_root_identities=launch_roots
    )
    token = secrets.token_hex(12)
    recorded_utc = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(timespec="seconds")
    command = _submit_command(inventory_sha, OUTPUT_DIR, token)
    intent = {
        "schema": LAUNCH_SCHEMA + "/intent",
        **materials,
        "recorded_utc": recorded_utc,
        "submission_token": token,
        "submit_command": command,
    }
    intent_raw = Source.canonical_json(intent)
    _exclusive_json(INTENT, intent, "v4 launch intent")
    _exclusive_bytes(SOURCE_INVENTORY, inventory_raw, "v4 source inventory")
    _require_launch_root_identities(launch_roots, require_empty_tmp=True)
    output = _submit_sbatch(command, materials)
    _require_launch_root_identities(launch_roots)
    job_id = output.split(";", 1)[0]
    digest = _write_launch_receipt(intent_raw, intent, job_id)
    print(json.dumps({
        "job_id": job_id,
        "launch_receipt_sha256": digest,
        "source_inventory_sha256": inventory_sha,
    }, sort_keys=True, indent=2))


def _load_intent_only() -> tuple[bytes, dict, dict]:
    raw, intent = _load_json(INTENT, "v4 launch intent")
    source_inventory_sha = intent.get("source_inventory_sha256")
    materials = _fixed_materials(
        source_inventory_sha,
        intent.get("repository_commit_id"),
    )
    token = intent.get("submission_token")
    recorded_utc = intent.get("recorded_utc")
    command = _submit_command(source_inventory_sha, OUTPUT_DIR, token)
    if (
        intent != {
            "schema": LAUNCH_SCHEMA + "/intent",
            **materials,
            "recorded_utc": recorded_utc,
            "submission_token": token,
            "submit_command": command,
        }
        or not isinstance(recorded_utc, str)
        or Legacy.Base.SUBMISSION_TOKEN_RE.fullmatch(token or "") is None
    ):
        raise LaunchAuditError("source-audit v4 launch intent changed")
    Source.load_inventory_manifest(SOURCE_INVENTORY, source_inventory_sha)
    return raw, intent, materials


def _load_launch() -> tuple[str, dict]:
    intent_raw, intent, materials = _load_intent_only()
    launch_raw, receipt = _load_json(LAUNCH_RECEIPT, "v4 launch receipt")
    if (
        receipt != {
            "schema": LAUNCH_SCHEMA,
            **materials,
            "recorded_utc": intent["recorded_utc"],
            "submission_token": intent["submission_token"],
            "submit_command": intent["submit_command"],
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": receipt.get("job_id"),
        }
        or not isinstance(receipt.get("job_id"), str)
        or not receipt["job_id"].isdigit()
    ):
        raise LaunchAuditError("source-audit v4 launch provenance changed")
    if _journal_job_ids(intent) != [receipt["job_id"]]:
        raise LaunchAuditError("v4 launch receipt is not journal-bound")
    return hashlib.sha256(launch_raw).hexdigest(), receipt


def _journal_job_ids(intent: dict) -> list[str]:
    try:
        return Legacy._journal_job_ids(intent)
    except Legacy.LaunchAuditError as err:
        raise LaunchAuditError(str(err)) from err


def recover_launch() -> None:
    if LAUNCH_RECEIPT.exists():
        raise LaunchAuditError("v4 launch receipt already exists")
    raw, intent, _ = _load_intent_only()
    jobs = _journal_job_ids(intent)
    if len(jobs) != 1:
        raise LaunchAuditError(
            "journal identifies {} v4 jobs; refusing resubmission".format(
                len(jobs)
            )
        )
    digest = _write_launch_receipt(raw, intent, jobs[0])
    print(json.dumps({
        "job_id": jobs[0],
        "launch_receipt_reconstructed": True,
        "launch_receipt_sha256": digest,
    }, sort_keys=True, indent=2))


def status() -> tuple[str, dict, list[dict]]:
    launch_sha, receipt = _load_launch()
    rows = _scheduler_rows(receipt["job_id"])
    print(json.dumps({
        "job_id": receipt["job_id"],
        "state_counts": dict(Counter(row["state"] for row in rows)),
    }, sort_keys=True, indent=2))
    return launch_sha, receipt, rows


def _validate_original_success_rows(rows: list[dict]) -> None:
    try:
        Legacy._validate_original_success_rows(rows)
    except Legacy.LaunchAuditError as err:
        raise LaunchAuditError(str(err)) from err


def _scheduler_contract_rows(
    job_id: str, launch_receipt: dict, scheduler_rows: list[dict]
) -> list[dict]:
    try:
        return Legacy._scheduler_contract_rows(
            job_id, launch_receipt, scheduler_rows
        )
    except Legacy.LaunchAuditError as err:
        raise LaunchAuditError(str(err)) from err


def _tree_digest(
    root: Path, paths: set[Path], expected_root_identity: dict
) -> dict:
    root_identity = _require_directory_identity(
        root, expected_root_identity, "v4 output directory"
    )
    digest = hashlib.sha256()
    digest.update(b"root-identity\0" + Source.canonical_json(root_identity))
    records = []
    for path in sorted(paths):
        try:
            info = path.lstat()
        except OSError as err:
            raise LaunchAuditError("cannot inspect v4 output") from err
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise LaunchAuditError("v4 output is not regular")
        relative = path.relative_to(root).as_posix()
        sha256 = _sha256(path)
        try:
            after = path.lstat()
        except OSError as err:
            raise LaunchAuditError("cannot recheck v4 output") from err
        if (
            not stat.S_ISREG(after.st_mode)
            or (info.st_dev, info.st_ino, info.st_size)
            != (after.st_dev, after.st_ino, after.st_size)
        ):
            raise LaunchAuditError("v4 output changed while hashing")
        digest.update(relative.encode("ascii") + b"\0" + bytes.fromhex(sha256))
        records.append({"path": relative, "bytes": after.st_size, "sha256": sha256})
    _require_directory_identity(
        root, root_identity, "v4 output directory"
    )
    return {
        "sha256": digest.hexdigest(),
        "root_identity": root_identity,
        "files_count": len(records),
        "files": records,
    }


def _output_tree(job_id: str, expected_root_identity: dict) -> dict:
    expected = {SOURCE_INVENTORY}
    for index in range(ARRAY_TASKS):
        expected.add(Source.shard_path(OUTPUT_DIR, index))
        expected.add(Source.task_environment_path(OUTPUT_DIR, index))
        expected.add(OUTPUT_DIR / "slurm-{}_{}.out".format(job_id, index))
    try:
        actual = set(OUTPUT_DIR.iterdir())
    except OSError as err:
        raise LaunchAuditError("cannot inspect v4 output tree") from err
    if actual != expected:
        raise LaunchAuditError("v4 output tree is incomplete or has extra paths")
    return _tree_digest(OUTPUT_DIR, actual, expected_root_identity)


def _tmp_root_identity(*, require_empty: bool) -> dict:
    return _directory_identity(
        Source.TMP_ROOT, "v4 TMPDIR root", require_empty=require_empty
    )


def _task_environment_manifest(
    job_id: str, launch_receipt: dict, code: dict
) -> dict:
    records = []
    common_root = None
    common_output = None
    for index in range(ARRAY_TASKS):
        shard = Source.shard_path(OUTPUT_DIR, index)
        path = Source.task_environment_path(OUTPUT_DIR, index)
        value = Source.load_task_environment_attestation(
            path,
            index=index,
            array_job_id=job_id,
            inventory_sha256=launch_receipt["source_inventory_sha256"],
            code_manifest_sha256=launch_receipt["code_manifest_sha256"],
            code=code,
            shard_sha256=_sha256(shard),
        )
        root_identity = value["tmpdir_root_identity_after"]
        output_identity = value["output_dir_identity_after"]
        if common_root is None:
            common_root = root_identity
        elif root_identity != common_root:
            raise LaunchAuditError("v4 tasks used different TMPDIR roots")
        if common_output is None:
            common_output = output_identity
        elif output_identity != common_output:
            raise LaunchAuditError("v4 tasks used different output roots")
        records.append({
            "array_task": index,
            "path": path.relative_to(OUTPUT_DIR).as_posix(),
            "sha256": _sha256(path),
            "tmpdir": value["tmpdir"],
            "tmpdir_identity": value["tmpdir_identity_after"],
            "output_dir_identity": output_identity,
            "shard_sha256": value["shard_sha256"],
        })
    live_root = _tmp_root_identity(require_empty=True)
    live_output = _directory_identity(OUTPUT_DIR, "v4 output directory")
    launch_roots = launch_receipt.get("launch_root_identities")
    if (
        not isinstance(launch_roots, dict)
        or common_root != live_root
        or common_root != launch_roots.get("tmpdir_root")
        or common_output != live_output
        or common_output != launch_roots.get("output_dir")
    ):
        raise LaunchAuditError("live v4 roots differ from launch/task evidence")
    return {
        "schema": Source.TASK_ENVIRONMENT_SCHEMA + "/manifest/v1",
        "records": records,
        "records_sha256": hashlib.sha256(
            Source.canonical_json(records)
        ).hexdigest(),
        "tmpdir_root_identity": live_root,
        "output_dir_identity": live_output,
        "all_task_tmpdirs_removed_by_rmdir": True,
    }


def seal() -> None:
    if EXECUTION_RECEIPT.exists() or CANDIDATE.exists() or ATTESTATION.exists():
        raise LaunchAuditError("v4 execution artifacts already exist")
    launch_sha, launch_receipt, rows = status()
    _validate_original_success_rows(rows)
    contract = _scheduler_contract_rows(
        launch_receipt["job_id"], launch_receipt, rows
    )
    code = Source.validate_code_manifest(
        CODE_MANIFEST, launch_receipt["code_manifest_sha256"]
    )
    launch_roots = launch_receipt.get("launch_root_identities")
    roots_before = _require_launch_root_identities(
        launch_roots, require_empty_tmp=True
    )
    tree_before = _output_tree(
        launch_receipt["job_id"], launch_roots["output_dir"]
    )
    environments = _task_environment_manifest(
        launch_receipt["job_id"], launch_receipt, code
    )
    Source.main([
        "assemble",
        "--shard-dir", str(OUTPUT_DIR),
        "--inventory-manifest", str(SOURCE_INVENTORY),
        "--inventory-sha256", launch_receipt["source_inventory_sha256"],
        "--num-shards", str(ARRAY_TASKS),
        "--output", str(CANDIDATE),
        "--code-manifest", str(CODE_MANIFEST),
        "--code-manifest-sha256", launch_receipt["code_manifest_sha256"],
    ])
    if _output_tree(
        launch_receipt["job_id"], launch_roots["output_dir"]
    ) != tree_before:
        raise LaunchAuditError("v4 original output changed while sealing")
    if _task_environment_manifest(
        launch_receipt["job_id"], launch_receipt, code
    ) != environments:
        raise LaunchAuditError("v4 environment evidence changed while sealing")
    candidate_raw, candidate = _load_json(CANDIDATE, "v4 candidate attestation")
    if (
        candidate.get("schema") != Source.SCHEMA
        or candidate.get("counts", {}).get("candidates") != Source.CANDIDATE_COUNT
        or candidate.get("counts", {}).get("translation_attempts")
        != Source.CANDIDATE_COUNT
        or candidate.get("confirmation_prelaunch_authorized")
        is not candidate.get("prelaunch_gate", {}).get("passed")
    ):
        raise LaunchAuditError("v4 candidate identity changed")
    attestation_sha = _exclusive_bytes(
        ATTESTATION, candidate_raw, "frozen v4 source attestation"
    )
    roots_after = _require_launch_root_identities(
        launch_roots, require_empty_tmp=True
    )
    if roots_after != roots_before or _output_tree(
        launch_receipt["job_id"], launch_roots["output_dir"]
    ) != tree_before:
        raise LaunchAuditError("v4 roots or output changed during sealing")
    receipt = {
        "schema": EXECUTION_SCHEMA,
        "campaign": "v4",
        "whole_campaign_rerun": True,
        "original_only": True,
        "recovery": None,
        "reused_v1_shards": 0,
        "reused_v2_shards": 0,
        "reused_v3_shards": 0,
        "launch_receipt_sha256": launch_sha,
        "job_id": launch_receipt["job_id"],
        "partition": "fat",
        "qos": "normal",
        "account": ACCOUNT,
        "array": "0-819",
        "array_tasks": ARRAY_TASKS,
        "tasks_per_array_task": Source.TASKS_PER_SHARD,
        "cpus_per_task": 1,
        "memory_per_cpu": MEMORY_PER_CPU,
        "time_limit": TIME_LIMIT,
        "task_timeout_seconds": Source.TASK_TIMEOUT_SECONDS,
        "array_throttle": 0,
        "shards": ARRAY_TASKS,
        "candidates": Source.CANDIDATE_COUNT,
        "scheduler_state_counts": {"COMPLETED": ARRAY_TASKS},
        "scheduler_rows": rows,
        "scheduler_contract_rows": contract,
        "launch_root_identities": launch_roots,
        "sealing_root_identities_before": roots_before,
        "sealing_root_identities_after": roots_after,
        "original_output_tree": tree_before,
        "task_environment_manifest": environments,
        "code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "source_inventory_sha256": launch_receipt["source_inventory_sha256"],
        "v3_infrastructure_diagnostic_sha256": launch_receipt[
            "v3_infrastructure_diagnostic_sha256"
        ],
        "v3_infrastructure_diagnostic": launch_receipt[
            "v3_infrastructure_diagnostic"
        ],
        "execution_environment": launch_receipt["execution_environment"],
        "source_audit_complete": True,
        "confirmation_prelaunch_authorized": candidate[
            "confirmation_prelaunch_authorized"
        ],
        "prelaunch_gate": candidate["prelaunch_gate"],
        "attestation_sha256": attestation_sha,
        "attestation_records_sha256": candidate["records_sha256"],
        "cohort_manifest_sha256": {
            name: cohort["tasks_sha256"]
            for name, cohort in candidate["cohorts"].items()
        },
        "counts": candidate["counts"],
        "translation_status_counts": candidate["translation_status_counts"],
        "support_exclusion_counts": candidate["support_exclusion_counts"],
    }
    digest = _exclusive_json(
        EXECUTION_RECEIPT, receipt, "v4 execution receipt"
    )
    print(json.dumps({
        "attestation_sha256": attestation_sha,
        "confirmation_prelaunch_authorized": candidate[
            "confirmation_prelaunch_authorized"
        ],
        "execution_receipt_sha256": digest,
        "original_output_tree_sha256": tree_before["sha256"],
        "task_environment_records_sha256": environments["records_sha256"],
    }, sort_keys=True, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "diagnose-v3", "launch", "recover-launch", "status", "seal",
    ))
    args = parser.parse_args(argv)
    {
        "diagnose-v3": diagnose_v3,
        "launch": launch,
        "recover-launch": recover_launch,
        "status": status,
        "seal": seal,
    }[args.command]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        LaunchAuditError,
        Source.SourceAuditError,
        Inventory.InventoryError,
    ) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
