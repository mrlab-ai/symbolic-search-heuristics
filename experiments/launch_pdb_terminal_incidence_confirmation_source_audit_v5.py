#!/usr/bin/env python3
"""Diagnose v4, then launch, monitor, and seal full source audit v5."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import secrets
import shlex
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources_v5 as Source
import pdb_terminal_incidence_confirmation_inventory as Inventory
import pdb_terminal_incidence_confirmation_safe_io_v5 as SafeIO


_LEGACY_PATH = (
    SCRIPT_DIR / "launch_pdb_terminal_incidence_confirmation_source_audit_v4.py"
)
_LEGACY_SPEC = importlib.util.spec_from_file_location(
    "_pdb_terminal_incidence_confirmation_source_launch_v5_shared",
    _LEGACY_PATH,
)
if _LEGACY_SPEC is None or _LEGACY_SPEC.loader is None:
    raise RuntimeError("cannot load frozen campaign-v4 launch helpers")
Legacy = importlib.util.module_from_spec(_LEGACY_SPEC)
sys.modules[_LEGACY_SPEC.name] = Legacy
_LEGACY_SPEC.loader.exec_module(Legacy)
Generic = Legacy.Legacy
Base = Generic.Base
_SHARED_LOAD_INTENT = Base._load_intent_only
_SHARED_LOAD_LAUNCH = Base._load_launch
_SHARED_STATUS = Base.status


class LaunchAuditError(RuntimeError):
    pass


SLURM_SCRIPT = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v5.slurm"
)
CODE_MANIFEST = Source.DEFAULT_CODE_MANIFEST
OUTPUT_DIR = Source.DEFAULT_SHARDS
SOURCE_INVENTORY = Source.DEFAULT_INVENTORY
CANDIDATE = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v5_candidate.json"
)
ATTESTATION = Source.DEFAULT_OUTPUT
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v5"
)
V4_DIAGNOSTIC = Source.V4_DIAGNOSTIC
INTENT = ARTIFACT_DIR / "source-audit-launch-intent-v5.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-launch-receipt-v5.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v5.json"
LAUNCH_SCHEMA = Source.SCHEMA + "/campaign-v5/launch"
EXECUTION_SCHEMA = Source.SCHEMA + "/campaign-v5/execution"
V4_DIAGNOSTIC_SCHEMA = Source.SCHEMA + "/campaign-v5/v4-infrastructure-diagnostic"
ARRAY_TASKS = Source.SHARD_COUNT
ACCOUNT = "naiss2025-5-561-cpu"
# v4 task 723 reached 1,071,622,750 KiB MaxRSS and was killed under a
# 1-TiB request.  Doubling to 2 TiB gives nearly 100% observed-peak
# headroom.  A fat node exposes 3,095,813 MiB to Slurm, so at most one v5 task
# fits per node even though the 0--819 array remains unthrottled.
MEMORY_PER_CPU = "2T"
TIME_LIMIT = "16:40:00"
V4_TIME_LIMIT = "08:20:00"
V4_TASK_TIMEOUT_SECONDS = 14400
V4_SACCT_REQUESTED_MEMORY = "1T"
FAT_NODE_REAL_MEMORY_MIB = 3095813
V5_REQUEST_MEMORY_MIB = 2048 * 1024
V4_ACTIVE_STATES = frozenset({
    "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
    "RESIZING", "SUSPENDED", "STAGE_OUT",
})
V4_TERMINAL_STATES = frozenset({
    "COMPLETED", "FAILED", "OUT_OF_MEMORY", "CANCELLED",
})
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
JOB_NAME_PREFIX = "confirmation-source-audit-v5"
COMMENT_PREFIX = "confirmation-source-audit-v5"
MANIFEST_ASSIGNMENT_RE = re.compile(
    r'^code_manifest_sha256="([0-9a-f]{64})"$'
)

V4_JOB_ID = "1865695"
V4_OUTPUT_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v4"
)
V4_LAUNCH_INTENT = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v4" /
    "source-audit-launch-intent-v4.json"
)
V4_LAUNCH_INTENT_SHA256 = (
    "d4c106b9aa6975f63a14ef3e59cc9186c2f28add9e31a1090f9d0b8d7ff82e27"
)
V4_LAUNCH_RECEIPT = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v4" /
    "source-audit-launch-receipt-v4.json"
)
V4_LAUNCH_RECEIPT_SHA256 = (
    "90ec55eb1d603cb7434885eeb99ceb2a0123ac02f4f9c02c885cab2635442921"
)
V4_CODE_MANIFEST = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256"
)
V4_CODE_MANIFEST_SHA256 = (
    "d3b571aaffce9f58f09d15f118df57997773c522e3da74bcdcbfbc00299f0518"
)
V4_SLURM_SCRIPT = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v4.slurm"
)
V4_SLURM_SCRIPT_SHA256 = (
    "8504f5b778d74a5120605947e710713532018e2007d276df8c580167b9ce1a8f"
)
SOURCE_INVENTORY_SHA256 = (
    "bb9be49a4652ff7bedcadb04b4db35cad701a5b2a2a6d6347c15e0ad670e056e"
)

# SHA256 of the complete Slurm file after replacing only the embedded code
# manifest digest with 64 zeroes.  This avoids a manifest/Slurm hash cycle.
NORMALIZED_SLURM_SHA256 = (
    "bc53eed1683e364e078a2075c827c70bf3b48162af4795fa3a29bd98a31437ee"
)

SCOPED_COMMIT_FILES = tuple(sorted({
    *Source.CODE_MANIFEST_FILES,
    SLURM_SCRIPT.relative_to(REPO).as_posix(),
    CODE_MANIFEST.relative_to(REPO).as_posix(),
}))

# Campaign v4 already hardened the generic Slurm accounting, submission
# journal, exact-resource, and scoped-jj checks.  Load those frozen helpers in
# a private module and change only their campaign constants; v4 itself remains
# byte-for-byte untouched and unaffected in other Python processes.
_SHARED_CAMPAIGN_VALUES = {
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
    "MEMORY_PER_CPU": MEMORY_PER_CPU,
    "TIME_LIMIT": TIME_LIMIT,
    "JOB_NAME_PREFIX": JOB_NAME_PREFIX,
    "COMMENT_PREFIX": COMMENT_PREFIX,
    "SCOPED_COMMIT_FILES": SCOPED_COMMIT_FILES,
}
for _module in (Legacy, Generic, Base):
    for _name, _value in _SHARED_CAMPAIGN_VALUES.items():
        setattr(_module, _name, _value)


def _sha256(path: Path) -> str:
    return _safe_file(path, str(path)).sha256


def _safe_file(
    path: Path,
    label: str,
    *,
    expected_path: Path | None = None,
    root: Path | None = None,
    read_callback=None,
) -> SafeIO.RegularFile:
    try:
        return SafeIO.read_regular_file(
            Path(path),
            label=label,
            expected_path=expected_path,
            root=root,
            read_callback=read_callback,
        )
    except SafeIO.SafeReadError as err:
        raise LaunchAuditError(str(err)) from err


def _safe_directory(
    path: Path,
    label: str,
    *,
    expected_path: Path | None = None,
    root: Path | None = None,
) -> SafeIO.Directory:
    try:
        return SafeIO.inspect_directory(
            Path(path),
            label=label,
            expected_path=expected_path,
            root=root,
        )
    except SafeIO.SafeReadError as err:
        raise LaunchAuditError(str(err)) from err


def _safe_tree(
    path: Path,
    label: str,
    *,
    expected_path: Path | None = None,
    root: Path | None = None,
    read_callback=None,
) -> SafeIO.RegularTree:
    try:
        return SafeIO.read_regular_tree(
            Path(path),
            label=label,
            expected_path=expected_path,
            root=root,
            read_callback=read_callback,
        )
    except SafeIO.SafeReadError as err:
        raise LaunchAuditError(str(err)) from err


def _exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    try:
        return Source.atomic_exclusive_bytes(path, raw, label)
    except Source.SourceAuditError as err:
        raise LaunchAuditError(str(err)) from err


def _exclusive_json(path: Path, value, label: str) -> str:
    return _exclusive_bytes(path, Source.canonical_json(value), label)


def _load_json(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        loaded, value = SafeIO.read_canonical_json(
            path,
            label=label,
            canonical_json_line=Source.canonical_json,
            expected_path=path,
        )
    except SafeIO.SafeReadError as err:
        raise LaunchAuditError(str(err)) from err
    return loaded.raw, value


def _directory_identity(
    path: Path, label: str, *, require_empty: bool = False
) -> dict:
    path = Path(path)
    loaded = _safe_directory(path, label, expected_path=path)
    info = loaded.identity
    if (
        not path.is_absolute()
        or path != Path(os.path.normpath(path))
        or not stat.S_ISDIR(info["mode"])
        or stat.S_IMODE(info["mode"]) != 0o700
        or info["uid"] != os.getuid()
    ):
        raise LaunchAuditError("{} identity changed".format(label))
    if require_empty and loaded.entries:
        raise LaunchAuditError("{} is not empty".format(label))
    return {
        "path": str(path),
        "canonical_path": str(path),
        "device": info["device"],
        "inode": info["inode"],
        "mode": "0700",
        "uid": info["uid"],
    }


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
        # The path was just created with exist_ok=False after checking all
        # ancestors, so a plain chmod is both portable and race-bounded by the
        # subsequent inode/identity check.
        path.chmod(0o700)
    except Source.SourceAuditError as err:
        raise LaunchAuditError(str(err)) from err
    except OSError as err:
        raise LaunchAuditError("cannot create {}".format(label)) from err
    return _directory_identity(path, label)


def _live_launch_root_identities(*, require_empty_tmp: bool = False) -> dict:
    return {
        "output_dir": _directory_identity(
            OUTPUT_DIR, "v5 output directory"
        ),
        "tmpdir_root": _directory_identity(
            Source.TMP_ROOT,
            "v5 TMPDIR root",
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
        raise LaunchAuditError("v5 launch root identities are invalid")
    actual = _live_launch_root_identities(
        require_empty_tmp=require_empty_tmp
    )
    if actual != expected:
        raise LaunchAuditError("v5 launch root was replaced")
    return actual


def _executable_identity(
    path: Path, expected_sha256: str, label: str
) -> dict:
    loaded = _safe_file(path, label, expected_path=path)
    if (
        not path.is_absolute()
        or not stat.S_ISREG(loaded.identity["mode"])
        or stat.S_IMODE(loaded.identity["mode"]) & 0o111 == 0
        or not os.access(path, os.X_OK)
        or loaded.sha256 != expected_sha256
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
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("source-audit scheduler query is invalid")
    output = _sacct([
        str(SACCT_COMMAND), "-j", job_id, "-X", "--array", "-n", "-P",
        "--format=JobID,State,ExitCode,Elapsed,Partition",
    ])
    rows = {}
    prefix = job_id + "_"
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 5:
            raise LaunchAuditError("source-audit accounting row changed")
        array_id, state, exit_code, elapsed, partition = fields
        if not array_id.startswith(prefix):
            continue
        suffix = array_id[len(prefix):]
        if not suffix.isdigit():
            raise LaunchAuditError("source-audit accounting array is compressed")
        task = int(suffix)
        if task in rows or not 0 <= task < ARRAY_TASKS or partition != "fat":
            raise LaunchAuditError("source-audit accounting identity changed")
        rows[task] = {
            "array_task": task,
            "state": state.split("+", 1)[0].split()[0],
            "exit_code": exit_code,
            "elapsed": elapsed,
            "partition": partition,
        }
    if set(rows) != set(range(ARRAY_TASKS)):
        raise LaunchAuditError("source-audit accounting task set is incomplete")
    return [rows[index] for index in range(ARRAY_TASKS)]


def _v4_fixed_launch_provenance() -> dict:
    intent_raw, _ = _load_json(V4_LAUNCH_INTENT, "v4 launch intent")
    receipt_raw, receipt = _load_json(V4_LAUNCH_RECEIPT, "v4 launch receipt")
    fixed_files = {
        "launch_intent": (V4_LAUNCH_INTENT, V4_LAUNCH_INTENT_SHA256),
        "launch_receipt": (V4_LAUNCH_RECEIPT, V4_LAUNCH_RECEIPT_SHA256),
        "code_manifest": (V4_CODE_MANIFEST, V4_CODE_MANIFEST_SHA256),
        "slurm_script": (V4_SLURM_SCRIPT, V4_SLURM_SCRIPT_SHA256),
    }
    if any(_sha256(path) != expected for path, expected in fixed_files.values()):
        raise LaunchAuditError("v4 launch/source bytes changed")
    if (
        hashlib.sha256(intent_raw).hexdigest() != V4_LAUNCH_INTENT_SHA256
        or hashlib.sha256(receipt_raw).hexdigest() != V4_LAUNCH_RECEIPT_SHA256
        or receipt.get("job_id") != V4_JOB_ID
        or receipt.get("campaign") != "v4"
        or receipt.get("whole_campaign_rerun") is not True
        or receipt.get("array") != "0-819"
        or receipt.get("array_tasks") != ARRAY_TASKS
        or receipt.get("candidates") != Source.CANDIDATE_COUNT
        or receipt.get("partition") != "fat"
        or receipt.get("qos") != "normal"
        or receipt.get("account") != ACCOUNT
        or receipt.get("cpus_per_task") != 1
        or receipt.get("memory_per_cpu") != "1024G"
        or receipt.get("time_limit") != V4_TIME_LIMIT
        or receipt.get("task_timeout_seconds") != V4_TASK_TIMEOUT_SECONDS
        or receipt.get("array_throttle") != 0
        or receipt.get("reused_v1_shards") != 0
        or receipt.get("reused_v2_shards") != 0
        or receipt.get("reused_v3_shards") != 0
        or receipt.get("source_inventory_sha256") != SOURCE_INVENTORY_SHA256
        or receipt.get("code_manifest_sha256") != V4_CODE_MANIFEST_SHA256
        or receipt.get("slurm_script_sha256") != V4_SLURM_SCRIPT_SHA256
    ):
        raise LaunchAuditError("v4 launch receipt identity changed")
    return {
        "v4_job_id": V4_JOB_ID,
        "v4_launch_intent_path": str(V4_LAUNCH_INTENT),
        "v4_launch_intent_sha256": V4_LAUNCH_INTENT_SHA256,
        "v4_launch_receipt_path": str(V4_LAUNCH_RECEIPT),
        "v4_launch_receipt_sha256": V4_LAUNCH_RECEIPT_SHA256,
        "v4_code_manifest_path": str(V4_CODE_MANIFEST),
        "v4_code_manifest_sha256": V4_CODE_MANIFEST_SHA256,
        "v4_slurm_script_path": str(V4_SLURM_SCRIPT),
        "v4_slurm_script_sha256": V4_SLURM_SCRIPT_SHA256,
        "v4_source_inventory_sha256": SOURCE_INVENTORY_SHA256,
    }


def _v4_oom_resource_rows(tasks: list[int]) -> list[dict]:
    records = []
    for task in tasks:
        output = _sacct([
            str(SACCT_COMMAND), "-j", "{}_{}".format(V4_JOB_ID, task),
            "-n", "-P",
            "--format=JobID,JobIDRaw,State,ExitCode,ReqMem,MaxRSS,MaxVMSize",
        ])
        task_rows = []
        for line in output.splitlines():
            fields = line.split("|")
            if len(fields) != 7:
                raise LaunchAuditError("v4 OOM accounting row changed")
            job_id, raw_id, state, exit_code, req_mem, max_rss, max_vm = fields
            if not job_id.startswith("{}_{}".format(V4_JOB_ID, task)):
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
            V4_JOB_ID, task
        )]
        batch = [row for row in task_rows if row["job_id"].endswith(".batch")]
        if (
            len(parent) != 1
            or len(batch) != 1
            or parent[0]["state"] != "OUT_OF_MEMORY"
            or parent[0]["exit_code"] != "0:125"
            or parent[0]["requested_memory"] != V4_SACCT_REQUESTED_MEMORY
            or batch[0]["state"] != "OUT_OF_MEMORY"
            or batch[0]["exit_code"] != "0:125"
            or re.fullmatch(r"[1-9][0-9]*K", batch[0]["max_rss"] or "") is None
            or re.fullmatch(r"[1-9][0-9]*K", batch[0]["max_vm_size"] or "") is None
        ):
            raise LaunchAuditError("v4 OOM resource evidence changed")
        records.append({"array_task": task, "rows": task_rows})
    return records


def _v4_timeout_resource_rows(tasks: list[int]) -> list[dict]:
    records = []
    for task in tasks:
        output = _sacct([
            str(SACCT_COMMAND), "-j", "{}_{}".format(V4_JOB_ID, task),
            "-n", "-P",
            "--format=JobID,JobIDRaw,State,ExitCode,Elapsed,ReqMem,"
            "MaxRSS,MaxVMSize",
        ])
        task_rows = []
        for line in output.splitlines():
            fields = line.split("|")
            if len(fields) != 8:
                raise LaunchAuditError("v4 timeout accounting row changed")
            (
                job_id, raw_id, state, exit_code, elapsed, req_mem,
                max_rss, max_vm,
            ) = fields
            if not job_id.startswith("{}_{}".format(V4_JOB_ID, task)):
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
            V4_JOB_ID, task
        )]
        batch = [row for row in task_rows if row["job_id"].endswith(".batch")]
        if (
            len(parent) != 1
            or len(batch) != 1
            or parent[0]["state"] != "FAILED"
            or parent[0]["exit_code"] != "75:0"
            or parent[0]["requested_memory"] != V4_SACCT_REQUESTED_MEMORY
            or re.fullmatch(r"[0-9]+:[0-9]{2}:[0-9]{2}", parent[0]["elapsed"])
            is None
            or batch[0]["state"] != "FAILED"
            or batch[0]["exit_code"] != "75:0"
            or re.fullmatch(r"[1-9][0-9]*K", batch[0]["max_rss"] or "") is None
            or re.fullmatch(r"[1-9][0-9]*K", batch[0]["max_vm_size"] or "")
            is None
        ):
            raise LaunchAuditError("v4 translator-timeout evidence changed")
        records.append({"array_task": task, "rows": task_rows})
    return records


def _expected_v4_diagnostic() -> dict:
    provenance = _v4_fixed_launch_provenance()
    rows = _scheduler_rows(V4_JOB_ID)
    states_present = {row["state"] for row in rows}
    if states_present - (V4_ACTIVE_STATES | V4_TERMINAL_STATES):
        raise LaunchAuditError(
            "v4 has an unclassified terminal failure or unknown state"
        )
    if states_present & V4_ACTIVE_STATES:
        raise LaunchAuditError("v4 source-audit array is not fully terminal")
    if not states_present <= V4_TERMINAL_STATES:
        raise LaunchAuditError("v4 source-audit terminal state changed")
    cancelled_tasks = [
        row["array_task"] for row in rows if row["state"] == "CANCELLED"
    ]
    cancellation = None
    if cancelled_tasks:
        # Load cancellation artifacts only after the complete scheduler state
        # allowlist has passed, and validate all identities before any v4 log.
        import cancel_pdb_terminal_incidence_confirmation_source_audit_v4_v5 \
            as Cancellation
        try:
            cancellation = Cancellation.validate_terminal_cancellation(rows)
        except Cancellation.CancellationError as err:
            raise LaunchAuditError(str(err)) from err
    failure_logs = []
    oom_tasks = []
    timeout_tasks = []
    task_line_re = re.compile(rb"^\[[12]/2\] ([^\r\n]+)\r?$", re.MULTILINE)
    for row in rows:
        state = row["state"]
        if state == "COMPLETED" and row["exit_code"] == "0:0":
            continue
        if state == "CANCELLED":
            # CANCELLED logs are outside the permitted diagnostic scope.
            continue
        if state not in {"FAILED", "OUT_OF_MEMORY"}:
            raise LaunchAuditError(
                "v4 has an unclassified terminal failure exit/state pair"
            )
        if (
            (state == "FAILED" and row["exit_code"] != "75:0")
            or (
                state == "OUT_OF_MEMORY"
                and row["exit_code"] != "0:125"
            )
        ):
            raise LaunchAuditError(
                "v4 has an unclassified terminal failure exit/state pair"
            )
        path = V4_OUTPUT_DIR / "slurm-{}_{}.out".format(
            V4_JOB_ID, row["array_task"]
        )
        payload = _safe_file(
            path, "v4 failure log", expected_path=path, root=V4_OUTPUT_DIR
        ).raw
        task_matches = task_line_re.findall(payload)
        if not task_matches:
            raise LaunchAuditError("v4 failure task identity is absent")
        try:
            task_name = task_matches[-1].decode("ascii")
        except UnicodeDecodeError as err:
            raise LaunchAuditError("v4 failure task identity changed") from err
        timeout_wrappers = re.findall(
            rb"infrastructure error: translator exceeded 14400s for "
            + re.escape(task_name.encode("ascii"))
            + rb"; stderr_sha256=([0-9a-f]{64}); stderr_tail='([^\r\n]*)'",
            payload,
        )
        if (
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
        else:
            raise LaunchAuditError(
                "v4 has an unclassified terminal failure at task {}".format(
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
    if not oom_tasks:
        raise LaunchAuditError("v4 diagnoses do not support the v5 memory amendment")
    if not timeout_tasks:
        raise LaunchAuditError("v4 diagnoses do not support the v5 time amendment")
    states = dict(sorted(Counter(row["state"] for row in rows).items()))
    oom_resources = _v4_oom_resource_rows(oom_tasks)
    timeout_resources = _v4_timeout_resource_rows(timeout_tasks)
    return {
        "schema": V4_DIAGNOSTIC_SCHEMA,
        **provenance,
        "v4_scheduler_rows": rows,
        "v4_scheduler_rows_sha256": hashlib.sha256(
            Source.canonical_json(rows)
        ).hexdigest(),
        "v4_scheduler_state_counts": states,
        "v4_cancelled_array_tasks": cancelled_tasks,
        "v4_cancellation": cancellation,
        "v4_failure_logs": failure_logs,
        "v4_failure_logs_sha256": hashlib.sha256(
            Source.canonical_json(failure_logs)
        ).hexdigest(),
        "v4_out_of_memory_array_tasks": oom_tasks,
        "v4_translator_timeout_array_tasks": timeout_tasks,
        "v4_oom_scheduler_resource_rows": oom_resources,
        "v4_oom_scheduler_resource_rows_sha256": hashlib.sha256(
            Source.canonical_json(oom_resources)
        ).hexdigest(),
        "v4_timeout_scheduler_resource_rows": timeout_resources,
        "v4_timeout_scheduler_resource_rows_sha256": hashlib.sha256(
            Source.canonical_json(timeout_resources)
        ).hexdigest(),
        "failure_classes": [
            "scheduler-out-of-memory",
            "translator-wallclock-timeout",
        ],
        "inspection_scope": (
            "all v4 scheduler rows, failed/OOM scheduler resource rows, "
            "cancellation intent/receipt/accounting, and only actual FAILED75 "
            "or OUT_OF_MEMORY v4 Slurm logs"
        ),
        "successful_v4_shard_contents_inspected": False,
        "successful_v4_log_contents_inspected": False,
        "cancelled_v4_log_contents_inspected": False,
        "source_support_outcomes_used_for_v5_design": False,
        "resource_amendment": {
            "temporary_storage": {
                "from": (
                    "project-backed per-candidate snapshots and per-task "
                    "temporary directories"
                ),
                "to": Source.TMPDIR_TEMPLATE,
                "reason": (
                    "retain v4's project-backed isolation unchanged; the "
                    "classified v4 failure is memory exhaustion, not ENOSPC"
                ),
                "cleanup": "per-task EXIT trap using pinned rmdir only",
            },
            "memory_per_cpu": {
                "from": "1024G",
                "to": MEMORY_PER_CPU,
                "factor": 2,
                "reason": (
                    "v4 scheduler OOM at 1 TiB; batch MaxRSS and MaxVMSize "
                    "are pinned above"
                ),
            },
            "task_timeout_seconds": {
                "from": V4_TASK_TIMEOUT_SECONDS,
                "to": Source.TASK_TIMEOUT_SECONDS,
                "factor": 2,
                "reason": (
                    "v4 translator exceeded its 14,400-second source limit; "
                    "task/log/accounting evidence is pinned above"
                ),
            },
            "time_limit": {
                "from": V4_TIME_LIMIT,
                "to": TIME_LIMIT,
                "factor": 2,
                "reason": "preserve scheduler headroom for doubled source limit",
            },
        },
        "scheduler_memory_geometry": {
            "fat_node_real_memory_mib": FAT_NODE_REAL_MEMORY_MIB,
            "v5_request_memory_mib": V5_REQUEST_MEMORY_MIB,
            "maximum_v5_tasks_per_node_by_memory": (
                FAT_NODE_REAL_MEMORY_MIB // V5_REQUEST_MEMORY_MIB
            ),
            "array_throttle": 0,
            "interpretation": (
                "the unthrottled array leaves concurrency to Slurm; the "
                "memory request permits at most one v5 task per fat node"
            ),
        },
        "full_rerun_decision": {
            "scope": "all-820-original-shards-and-1640-candidates",
            "whole_campaign_rerun": True,
            "reused_v1_shards": 0,
            "reused_v2_shards": 0,
            "reused_v3_shards": 0,
            "reused_v4_shards": 0,
        },
    }


def diagnose_v4() -> None:
    if V4_DIAGNOSTIC.exists():
        raise LaunchAuditError("v4 infrastructure diagnostic already exists")
    if any(path.exists() for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR,
        Source.TMP_ROOT, CANDIDATE, ATTESTATION,
    )):
        raise LaunchAuditError("v5 namespace is not empty before diagnosis")
    diagnostic = _expected_v4_diagnostic()
    digest = _exclusive_json(
        V4_DIAGNOSTIC, diagnostic, "v4 infrastructure diagnostic"
    )
    print(json.dumps({
        "v4_diagnostic_sha256": digest,
        "v4_out_of_memory_array_tasks": (
            diagnostic["v4_out_of_memory_array_tasks"]
        ),
        "v4_translator_timeout_array_tasks": (
            diagnostic["v4_translator_timeout_array_tasks"]
        ),
    }, sort_keys=True, indent=2))


def _load_v4_diagnostic() -> tuple[str, dict]:
    raw, diagnostic = _load_json(V4_DIAGNOSTIC, "v4 infrastructure diagnostic")
    if diagnostic != _expected_v4_diagnostic():
        raise LaunchAuditError("v4 infrastructure diagnostic changed")
    return hashlib.sha256(raw).hexdigest(), diagnostic


def _code_manifest_bytes() -> bytes:
    """Hash the exact regular producer files named by the v5 source module."""
    records = []
    seen = set()
    for relative in Source.CODE_MANIFEST_FILES:
        if (
            not isinstance(relative, str)
            or not relative
            or relative in seen
            or Path(relative).is_absolute()
            or ".." in Path(relative).parts
            or re.fullmatch(r"[!-~]+", relative) is None
        ):
            raise LaunchAuditError("v5 code manifest path set is invalid")
        seen.add(relative)
        path = REPO / relative
        loaded = _safe_file(
            path, "v5 code manifest input", expected_path=path, root=REPO
        )
        records.append("{}  {}\n".format(loaded.sha256, relative))
    if len(seen) != len(Source.CODE_MANIFEST_FILES):
        raise LaunchAuditError("v5 code manifest path order changed")
    return "".join(records).encode("ascii")


def prepare_manifest() -> None:
    """Create the v5 code manifest after the terminal v4 diagnostic."""
    if CODE_MANIFEST.exists():
        raise LaunchAuditError("v5 code manifest already exists")
    _assert_launch_namespace_empty()
    _load_v4_diagnostic()
    loaded_slurm = _safe_file(
        SLURM_SCRIPT,
        "v5 Slurm template",
        expected_path=SLURM_SCRIPT,
        root=SLURM_SCRIPT.parent,
    )
    raw_slurm = loaded_slurm.raw
    if (
        loaded_slurm.sha256 != NORMALIZED_SLURM_SHA256
        or raw_slurm.count(b"0" * 64) != 1
        or b'code_manifest_sha256="' + b"0" * 64 + b'"' not in raw_slurm
    ):
        raise LaunchAuditError("v5 Slurm template is not normalized")
    manifest_raw = _code_manifest_bytes()
    digest = _exclusive_bytes(
        CODE_MANIFEST, manifest_raw, "v5 code manifest"
    )
    print(json.dumps({
        "code_manifest_path": str(CODE_MANIFEST),
        "code_manifest_sha256": digest,
        "files": len(Source.CODE_MANIFEST_FILES),
        "next_step": (
            "replace the single 64-zero code_manifest_sha256 value in the "
            "v5 Slurm script with this digest, then rerun the full tests"
        ),
    }, sort_keys=True, indent=2))


def _execution_environment(code: dict) -> dict:
    python_identity = _executable_identity(
        Path(code.get("python_executable", "")),
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
        loaded = _safe_file(
            SLURM_SCRIPT,
            "v5 Slurm script",
            expected_path=SLURM_SCRIPT,
            root=SLURM_SCRIPT.parent,
        )
        raw = loaded.raw
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise LaunchAuditError("cannot read v5 Slurm script") from err
    assignments = [
        MANIFEST_ASSIGNMENT_RE.fullmatch(line)
        for line in lines if line.startswith("code_manifest_sha256=")
    ]
    if len(assignments) != 1 or assignments[0] is None:
        raise LaunchAuditError("v5 code manifest is not pinned in Slurm")
    manifest_sha = assignments[0].group(1)
    normalized = raw.replace(manifest_sha.encode("ascii"), b"0" * 64, 1)
    if (
        hashlib.sha256(normalized).hexdigest() != NORMALIZED_SLURM_SHA256
        or raw.count(manifest_sha.encode("ascii")) != 1
    ):
        raise LaunchAuditError("v5 Slurm executable bytes changed")
    ordered_header = [
        "#!/bin/bash",
        "#SBATCH --job-name=confirmation-source-audit-v5",
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
        raise LaunchAuditError("v5 Slurm resource/tempfile contract changed")
    code = Source.validate_code_manifest(CODE_MANIFEST, manifest_sha)
    environment = _execution_environment(code)
    required = {
        'test "$#" -eq 0',
        'source_inventory_sha256="{}"'.format(SOURCE_INVENTORY_SHA256),
        'source_audit_output_dir="{}"'.format(OUTPUT_DIR),
        'export TMPDIR="${tmpdir_root}/task-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"',
        'export PYTHONPYCACHEPREFIX="${TMPDIR}/pycache"',
        '"${mkdir_executable}" --mode=0700 -- "${TMPDIR}"',
        '    experiments/audit_pdb_terminal_incidence_confirmation_sources_v5.py scan \\',
        '    --task-timeout 28800 \\',
        '    --code-manifest-sha256 "${code_manifest_sha256}"',
    }
    if not required <= set(lines) or any(lines.count(line) != 1 for line in required):
        raise LaunchAuditError("v5 Slurm execution contract changed")
    if any(line in {'source_inventory_sha256="$1"', 'source_audit_output_dir="$2"'}
           for line in lines):
        raise LaunchAuditError("v5 Slurm script accepts runtime path arguments")
    return raw, loaded.sha256, manifest_sha, code


def _jj_identity() -> dict:
    return _executable_identity(
        Path(Generic.JJ_COMMAND), Generic.JJ_EXECUTABLE_SHA256, "jj"
    )


def _scoped_repository_commit() -> str:
    jj_identity = _jj_identity()
    jj = jj_identity["path"]
    diff_command = [
        jj, "--no-pager", "diff", "--summary", "-r", "@", "--",
        *SCOPED_COMMIT_FILES,
    ]
    list_command = [
        jj, "--no-pager", "file", "list", "-r", "@-", "--",
        *SCOPED_COMMIT_FILES,
    ]
    commit_command = [
        jj, "--no-pager", "log", "-r", "@-", "--no-graph",
        "-T", 'commit_id ++ "\\n"',
    ]
    try:
        changed = subprocess.check_output(
            diff_command,
            cwd=REPO,
            env=dict(SUBMISSION_ENVIRONMENT),
            text=True,
        )
        tracked = subprocess.check_output(
            list_command,
            cwd=REPO,
            env=dict(SUBMISSION_ENVIRONMENT),
            text=True,
        ).splitlines()
        commit_id = subprocess.check_output(
            commit_command,
            cwd=REPO,
            env=dict(SUBMISSION_ENVIRONMENT),
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot attest scoped v5 commit") from err
    if (
        _jj_identity() != jj_identity
        or changed
        or set(tracked) != set(SCOPED_COMMIT_FILES)
        or len(tracked) != len(SCOPED_COMMIT_FILES)
        or Base.JJ_COMMIT_RE.fullmatch(commit_id) is None
    ):
        raise LaunchAuditError(
            "source-audit v5 requires every bound file committed at @-"
        )
    return commit_id


def _fixed_materials(
    source_inventory_sha256: str,
    repository_commit_id: str | None = None,
    launch_root_identities: dict | None = None,
) -> dict:
    if source_inventory_sha256 != SOURCE_INVENTORY_SHA256:
        raise LaunchAuditError("frozen source inventory hash changed")
    diagnostic_sha, diagnostic = _load_v4_diagnostic()
    slurm_raw, slurm_sha, manifest_sha, code = _slurm_preflight()
    environment = _execution_environment(code)
    if repository_commit_id is None:
        repository_commit_id = _scoped_repository_commit()
    if Base.JJ_COMMIT_RE.fullmatch(repository_commit_id or "") is None:
        raise LaunchAuditError("source-audit v5 repository commit is invalid")
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
        "campaign": "v5",
        "whole_campaign_rerun": True,
        "reused_v1_shards": 0,
        "reused_v2_shards": 0,
        "reused_v3_shards": 0,
        "reused_v4_shards": 0,
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
        "v4_infrastructure_diagnostic_path": str(V4_DIAGNOSTIC),
        "v4_infrastructure_diagnostic_sha256": diagnostic_sha,
        "v4_infrastructure_diagnostic": diagnostic,
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
        raise LaunchAuditError("v5 output directory changed")
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
        raise LaunchAuditError("v5 Slurm stdin changed before submission")
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
        raise LaunchAuditError("v5 sbatch failed after intent") from err
    return output


def _assert_launch_namespace_empty() -> None:
    if any(os.path.lexists(path) for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR,
        Source.TMP_ROOT, CANDIDATE, ATTESTATION,
    )):
        raise LaunchAuditError("v5 launch namespace is not empty")


def _write_launch_receipt(intent_raw: bytes, intent: dict, job_id: str) -> str:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("Slurm returned an invalid v5 job id")
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
    return _exclusive_json(LAUNCH_RECEIPT, receipt, "v5 launch receipt")


def launch() -> None:
    _assert_launch_namespace_empty()
    inventory = Inventory.load_inventory()
    inventory_value = Source.build_inventory_manifest(inventory)
    inventory_raw = Source.canonical_json(inventory_value)
    inventory_sha = hashlib.sha256(inventory_raw).hexdigest()
    if inventory_sha != SOURCE_INVENTORY_SHA256:
        raise LaunchAuditError("frozen source inventory hash changed")
    output_identity = _create_private_directory(
        OUTPUT_DIR, "v5 output directory"
    )
    tmp_identity = _create_private_directory(
        Source.TMP_ROOT, "v5 TMPDIR root"
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
    _exclusive_json(INTENT, intent, "v5 launch intent")
    _exclusive_bytes(SOURCE_INVENTORY, inventory_raw, "v5 source inventory")
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
    raw, intent = _load_json(INTENT, "v5 launch intent")
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
        or Base.SUBMISSION_TOKEN_RE.fullmatch(token or "") is None
    ):
        raise LaunchAuditError("source-audit v5 launch intent changed")
    Source.load_inventory_manifest(SOURCE_INVENTORY, source_inventory_sha)
    return raw, intent, materials


def _load_launch() -> tuple[str, dict]:
    intent_raw, intent, materials = _load_intent_only()
    launch_raw, receipt = _load_json(LAUNCH_RECEIPT, "v5 launch receipt")
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
        raise LaunchAuditError("source-audit v5 launch provenance changed")
    if _journal_job_ids(intent) != [receipt["job_id"]]:
        raise LaunchAuditError("v5 launch receipt is not journal-bound")
    return hashlib.sha256(launch_raw).hexdigest(), receipt


def _journal_job_ids(intent: dict) -> list[str]:
    token = intent.get("submission_token")
    job_name, comment = _submission_identity(token)
    try:
        recorded = datetime.datetime.fromisoformat(intent.get("recorded_utc"))
    except (TypeError, ValueError) as err:
        raise LaunchAuditError(
            "source-audit submission timestamp is invalid"
        ) from err
    if recorded.tzinfo is None:
        raise LaunchAuditError(
            "source-audit submission timestamp has no timezone"
        )
    output = _sacct([
        str(SACCT_COMMAND), "-X", "--array", "-S",
        recorded.date().isoformat(), "--name=" + job_name, "-n", "-P",
        "--format=JobID%64,JobName%128,Comment%128,SubmitLine%4096",
    ])
    parents = set()
    indices_by_parent = {}
    expected_indices = set(range(ARRAY_TASKS))
    expected_command = intent.get("submit_command")
    if not isinstance(expected_command, list) or not expected_command:
        raise LaunchAuditError("source-audit submit command is invalid")
    for line in output.splitlines():
        fields = line.split("|", 3)
        if len(fields) != 4:
            raise LaunchAuditError("source-audit submission journal row changed")
        job_id, actual_name, actual_comment, submit_line = fields
        if (
            actual_name != job_name
            and actual_comment != comment
            and token not in submit_line
        ):
            continue
        try:
            actual_command = shlex.split(submit_line)
        except ValueError as err:
            raise LaunchAuditError(
                "source-audit submission command cannot be parsed"
            ) from err
        if (
            actual_command
            and actual_command[0] == SBATCH_COMMAND.name
            and expected_command[0] == str(SBATCH_COMMAND)
        ):
            actual_command[0] = str(SBATCH_COMMAND)
        command_matches = actual_command == expected_command
        parent_match = re.fullmatch(r"([0-9]+)", job_id)
        array_match = re.fullmatch(r"([0-9]+)_([0-9]+)", job_id)
        if (
            actual_name == job_name
            or actual_comment == comment
            or command_matches
            or token in submit_line
        ):
            if (
                actual_name != job_name
                or actual_comment not in ("", comment)
                or not command_matches
                or (parent_match is None and array_match is None)
            ):
                raise LaunchAuditError(
                    "source-audit submission identity collided"
                )
            parent = (parent_match or array_match).group(1)
            parents.add(parent)
            if array_match is not None:
                task = int(array_match.group(2))
                indices_by_parent.setdefault(parent, set()).add(task)
    if len(parents) > 1:
        raise LaunchAuditError(
            "submission journal identifies multiple source-audit jobs"
        )
    if len(parents) == 1:
        parent = next(iter(parents))
        if indices_by_parent.get(parent, set()) != expected_indices:
            raise LaunchAuditError(
                "source-audit submission journal has an incomplete array"
            )
    return sorted(parents, key=int)


def recover_launch() -> None:
    if LAUNCH_RECEIPT.exists():
        raise LaunchAuditError("v5 launch receipt already exists")
    raw, intent, _ = _load_intent_only()
    jobs = _journal_job_ids(intent)
    if len(jobs) != 1:
        raise LaunchAuditError(
            "journal identifies {} v5 jobs; refusing resubmission".format(
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
    if (
        not isinstance(job_id, str)
        or not job_id.isdigit()
        or not isinstance(launch_receipt, dict)
        or type(scheduler_rows) is not list
        or len(scheduler_rows) != ARRAY_TASKS
    ):
        raise LaunchAuditError("source-audit v5 resource query is invalid")
    output = _sacct([
        str(SACCT_COMMAND), "-j", job_id, "-X", "--array", "-n", "-P",
        "--format=JobID,Account,Partition,QOS,ReqCPUS,ReqMem,"
        "Timelimit,State,ExitCode,JobName",
    ])
    token = launch_receipt.get("submission_token")
    expected_name, _ = _submission_identity(token)
    prefix = job_id + "_"
    rows = {}
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 10:
            raise LaunchAuditError("source-audit v5 resource row changed")
        (
            array_id, account, partition, qos, req_cpus, req_mem,
            time_limit, state, exit_code, job_name,
        ) = fields
        if not array_id.startswith(prefix):
            continue
        suffix = array_id[len(prefix):]
        if not suffix.isdigit():
            raise LaunchAuditError("source-audit resource array is compressed")
        task = int(suffix)
        state = state.split("+", 1)[0].split()[0]
        if (
            task in rows
            or not 0 <= task < ARRAY_TASKS
            or req_cpus != "1"
            or account != ACCOUNT
            or partition != "fat"
            or qos != "normal"
            or req_mem != MEMORY_PER_CPU
            or time_limit != TIME_LIMIT
            or state != "COMPLETED"
            or exit_code != "0:0"
            or job_name != expected_name
            or scheduler_rows[task].get("array_task") != task
            or scheduler_rows[task].get("state") != state
            or scheduler_rows[task].get("exit_code") != exit_code
        ):
            raise LaunchAuditError(
                "source-audit v5 actual resource contract changed"
            )
        rows[task] = {
            "array_task": task,
            "account": account,
            "partition": partition,
            "qos": qos,
            "req_cpus": 1,
            "req_mem": req_mem,
            "time_limit": time_limit,
            "state": state,
            "exit_code": exit_code,
            "job_name": job_name,
        }
    if set(rows) != set(range(ARRAY_TASKS)):
        raise LaunchAuditError(
            "source-audit v5 resource accounting task set is incomplete"
        )
    return [rows[index] for index in range(ARRAY_TASKS)]


def _tree_digest(
    root: Path,
    tree: SafeIO.RegularTree,
    expected_root_identity: dict,
) -> dict:
    root = Path(root)
    traversal_identity = tree.root_identity
    if (
        not root.is_absolute()
        or root != Path(os.path.normpath(root))
        or not stat.S_ISDIR(traversal_identity["mode"])
        or stat.S_IMODE(traversal_identity["mode"]) != 0o700
        or traversal_identity["uid"] != os.getuid()
    ):
        raise LaunchAuditError("v5 output directory identity changed")
    root_identity = {
        "path": str(root),
        "canonical_path": str(root),
        "device": traversal_identity["device"],
        "inode": traversal_identity["inode"],
        "mode": "0700",
        "uid": traversal_identity["uid"],
    }
    if root_identity != expected_root_identity:
        raise LaunchAuditError("v5 output directory identity changed")
    digest = hashlib.sha256()
    digest.update(b"root-identity\0" + Source.canonical_json(root_identity))
    records = []
    for item in tree.files:
        relative = item.path
        digest.update(
            relative.encode("ascii") + b"\0" + bytes.fromhex(item.sha256)
        )
        records.append({
            "path": relative,
            "bytes": item.identity["size"],
            "sha256": item.sha256,
        })
    return {
        "sha256": digest.hexdigest(),
        "root_identity": root_identity,
        "files_count": len(records),
        "files": records,
    }


def _output_tree(
    job_id: str, expected_root_identity: dict, *, tree_callback=None
) -> dict:
    expected = {SOURCE_INVENTORY}
    for index in range(ARRAY_TASKS):
        expected.add(Source.shard_path(OUTPUT_DIR, index))
        expected.add(Source.task_environment_path(OUTPUT_DIR, index))
        expected.add(OUTPUT_DIR / "slurm-{}_{}.out".format(job_id, index))
    tree = _safe_tree(
        OUTPUT_DIR,
        "v5 output tree",
        expected_path=OUTPUT_DIR,
        read_callback=tree_callback,
    )
    actual = {OUTPUT_DIR / item.path for item in tree.files}
    if tree.directories or actual != expected:
        raise LaunchAuditError("v5 output tree is incomplete or has extra paths")
    return _tree_digest(OUTPUT_DIR, tree, expected_root_identity)


def _tmp_root_identity(*, require_empty: bool) -> dict:
    return _directory_identity(
        Source.TMP_ROOT, "v5 TMPDIR root", require_empty=require_empty
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
            raise LaunchAuditError("v5 tasks used different TMPDIR roots")
        if common_output is None:
            common_output = output_identity
        elif output_identity != common_output:
            raise LaunchAuditError("v5 tasks used different output roots")
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
    live_output = _directory_identity(OUTPUT_DIR, "v5 output directory")
    launch_roots = launch_receipt.get("launch_root_identities")
    if (
        not isinstance(launch_roots, dict)
        or common_root != live_root
        or common_root != launch_roots.get("tmpdir_root")
        or common_output != live_output
        or common_output != launch_roots.get("output_dir")
    ):
        raise LaunchAuditError("live v5 roots differ from launch/task evidence")
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
        raise LaunchAuditError("v5 execution artifacts already exist")
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
        raise LaunchAuditError("v5 original output changed while sealing")
    if _task_environment_manifest(
        launch_receipt["job_id"], launch_receipt, code
    ) != environments:
        raise LaunchAuditError("v5 environment evidence changed while sealing")
    candidate_raw, candidate = _load_json(CANDIDATE, "v5 candidate attestation")
    if (
        candidate.get("schema") != Source.SCHEMA
        or candidate.get("counts", {}).get("candidates") != Source.CANDIDATE_COUNT
        or candidate.get("counts", {}).get("translation_attempts")
        != Source.CANDIDATE_COUNT
        or candidate.get("confirmation_prelaunch_authorized")
        is not candidate.get("prelaunch_gate", {}).get("passed")
    ):
        raise LaunchAuditError("v5 candidate identity changed")
    attestation_sha = _exclusive_bytes(
        ATTESTATION, candidate_raw, "frozen v5 source attestation"
    )
    roots_after = _require_launch_root_identities(
        launch_roots, require_empty_tmp=True
    )
    if roots_after != roots_before or _output_tree(
        launch_receipt["job_id"], launch_roots["output_dir"]
    ) != tree_before:
        raise LaunchAuditError("v5 roots or output changed during sealing")
    receipt = {
        "schema": EXECUTION_SCHEMA,
        "campaign": "v5",
        "whole_campaign_rerun": True,
        "original_only": True,
        "recovery": None,
        "reused_v1_shards": 0,
        "reused_v2_shards": 0,
        "reused_v3_shards": 0,
        "reused_v4_shards": 0,
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
        "v4_infrastructure_diagnostic_sha256": launch_receipt[
            "v4_infrastructure_diagnostic_sha256"
        ],
        "v4_infrastructure_diagnostic": launch_receipt[
            "v4_infrastructure_diagnostic"
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
        EXECUTION_RECEIPT, receipt, "v5 execution receipt"
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
        "diagnose-v4", "prepare-manifest", "launch", "recover-launch",
        "status", "seal",
    ))
    args = parser.parse_args(argv)
    {
        "diagnose-v4": diagnose_v4,
        "prepare-manifest": prepare_manifest,
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
