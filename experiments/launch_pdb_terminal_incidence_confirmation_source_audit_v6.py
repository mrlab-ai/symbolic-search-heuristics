#!/usr/bin/env python3
"""Diagnose terminal V5, repair its exact complement, and seal V6."""

from __future__ import annotations

import argparse
import datetime
import hashlib
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
from types import SimpleNamespace


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources_v5 as V5Source
import audit_pdb_terminal_incidence_confirmation_sources_v6 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v5 as V5Launch
import pdb_terminal_incidence_confirmation_inventory as Inventory
import pdb_terminal_incidence_confirmation_safe_io_v5 as SafeIO
import pdb_terminal_incidence_confirmation_safe_io_v6 as SafeTreeIO


class LaunchAuditError(RuntimeError):
    pass


SCHEMA = Source.Base.SCHEMA + "/campaign-v6"
DIAGNOSTIC_SCHEMA = SCHEMA + "/v5-infrastructure-diagnostic/v1"
LAUNCH_SCHEMA = SCHEMA + "/repair-launch/v1"
EXECUTION_SCHEMA = SCHEMA + "/execution/v1"
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v6"
)
DIAGNOSTIC = ARTIFACT_DIR / "v5-infrastructure-failure-diagnostic-v6.json"
INTENT = ARTIFACT_DIR / "source-audit-repair-launch-intent-v6.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-repair-launch-receipt-v6.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v6.json"
SEAL_PLAN = ARTIFACT_DIR / "source-audit-seal-plan-v6.json"
UNION_ROOT_STAGE = ARTIFACT_DIR / "source-audit-union-root-stage-v6.json"
UNION_STAGE = ARTIFACT_DIR / "source-audit-union-stage-v6.json"
CANDIDATE_STAGE = ARTIFACT_DIR / "source-audit-candidate-stage-v6.json"
ATTESTATION_STAGE = ARTIFACT_DIR / "source-audit-attestation-stage-v6.json"
SEAL_STAGE_ARTIFACTS = (
    SEAL_PLAN, UNION_ROOT_STAGE, UNION_STAGE,
    CANDIDATE_STAGE, ATTESTATION_STAGE,
)
SLURM_TEMPLATE = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v6.slurm"
)
CODE_MANIFEST = Source.DEFAULT_CODE_MANIFEST
OUTPUT_DIR = Source.DEFAULT_SHARDS
SOURCE_INVENTORY = Source.DEFAULT_INVENTORY
TMP_ROOT = Source.TMP_ROOT
UNION_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v6_union"
)
CANDIDATE = Source.DEFAULT_OUTPUT
ATTESTATION = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v6.json"
)
V5_OUTPUT_DIR = V5Launch.OUTPUT_DIR
V5_SOURCE_INVENTORY = V5Launch.SOURCE_INVENTORY
V5_CODE_MANIFEST = V5Launch.CODE_MANIFEST
V5_INTENT = V5Launch.INTENT
V5_LAUNCH_RECEIPT = V5Launch.LAUNCH_RECEIPT
V5_EXECUTION_RECEIPT = V5Launch.EXECUTION_RECEIPT
V5_CANDIDATE = V5Launch.CANDIDATE
V5_ATTESTATION = V5Launch.ATTESTATION

ARRAY_TASKS = Source.SHARD_COUNT
ACCOUNT = V5Launch.ACCOUNT
PARTITION = "fat"
QOS = "normal"
CPUS_PER_TASK = 1
V5_MEMORY_PER_CPU = "2T"
V6_TOTAL_MEMORY = "3000G"
V6_TOTAL_MEMORY_MIB = 3000 * 1024
FAT_NODE_REAL_MEMORY_MIB = V5Launch.FAT_NODE_REAL_MEMORY_MIB
V5_TASK_TIMEOUT_SECONDS = Source.V5_TIMEOUT_SECONDS
V6_TASK_TIMEOUT_SECONDS = Source.AMENDED_TIMEOUT_SECONDS
V5_TIME_LIMIT = "16:40:00"
V6_TIME_LIMIT = "3-00:00:00"
CONTROLLED_PATH = V5Launch.CONTROLLED_PATH
SUBMISSION_ENVIRONMENT = dict(V5Launch.SUBMISSION_ENVIRONMENT)
SBATCH_COMMAND = V5Launch.SBATCH_COMMAND
SBATCH_COMMAND_SHA256 = V5Launch.SBATCH_COMMAND_SHA256
SACCT_COMMAND = V5Launch.SACCT_COMMAND
SACCT_COMMAND_SHA256 = V5Launch.SACCT_COMMAND_SHA256
JOB_NAME_PREFIX = "confirmation-source-audit-v6"
COMMENT_PREFIX = "confirmation-source-audit-v6"
TIMEOUT_PLACEHOLDER = b"__V6_TASK_TIMEOUT_SECONDS__"
MANIFEST_PLACEHOLDER = b"__V6_CODE_MANIFEST_SHA256__"
NORMALIZED_SLURM_SHA256 = (
    "3f0ab84a94e0af38c5cc9da19b4af50c91e3dcbf879acab61dfd53ce545dfedc"
)
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
SEAL_PLAN_SCHEMA = EXECUTION_SCHEMA + "/seal-plan/v1"
UNION_ROOT_STAGE_SCHEMA = EXECUTION_SCHEMA + "/union-root-stage/v1"
UNION_STAGE_SCHEMA = EXECUTION_SCHEMA + "/union-stage/v1"
CANDIDATE_STAGE_SCHEMA = EXECUTION_SCHEMA + "/candidate-stage/v1"
ATTESTATION_STAGE_SCHEMA = EXECUTION_SCHEMA + "/attestation-stage/v1"

ACTIVE_STATES = frozenset({
    "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
    "RESIZING", "SUSPENDED", "STAGE_OUT",
})
TERMINAL_ACCOUNTING_STATES = frozenset({
    "BOOT_FAIL", "CANCELLED", "COMPLETED", "DEADLINE", "FAILED",
    "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "REVOKED", "TIMEOUT",
})
ALLOWED_SCHEDULER_STATES = ACTIVE_STATES | TERMINAL_ACCOUNTING_STATES
SCHEDULER_INTERRUPTION_STATES = frozenset({
    "BOOT_FAIL", "NODE_FAIL", "PREEMPTED", "REVOKED",
})
ALLOWED_FAILURE_CLASSES = frozenset({
    "scheduler-interruption",
    "scheduler-out-of-memory",
    "translator-wallclock-timeout",
})
ROW_KEYS = {"array_task", "state", "exit_code", "elapsed", "partition"}
SUBMISSION_TOKEN_RE = re.compile(r"[0-9a-f]{24}")
JJ_COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
SHA256_RE = re.compile(r"[0-9a-f]{64}")
SCOPED_COMMIT_FILES = tuple(sorted({
    *Source.CODE_MANIFEST_FILES,
    CODE_MANIFEST.relative_to(REPO).as_posix(),
}))
DIAGNOSTIC_RELATIVE_PATH = DIAGNOSTIC.relative_to(REPO).as_posix()
PRE_DIAGNOSIS_FILES = tuple(
    relative for relative in Source.CODE_MANIFEST_FILES
    if relative != DIAGNOSTIC_RELATIVE_PATH
)
DIAGNOSTIC_FIELDS = frozenset({
    "schema",
    "v5_launch_intent_path", "v5_launch_intent_sha256",
    "v5_launch_receipt_path", "v5_launch_receipt_sha256",
    "v5_launch_receipt", "v5_code_manifest_path",
    "v5_code_manifest_sha256", "v5_source_inventory_sha256",
    "v5_scheduler_rows", "v5_scheduler_rows_sha256",
    "v5_scheduler_state_counts", "logical_shards", "candidates",
    "reuse_eligibility_rule", "reusable_v5_shard_indices",
    "reusable_v5_shard_indices_sha256", "repair_v5_shard_indices",
    "repair_v5_shard_indices_sha256", "reused_v5_shards",
    "repaired_v5_shards", "repair_scope", "failure_records",
    "failure_records_sha256", "failure_classes", "resource_mapping",
    "v5_output_manifest", "successful_v5_shard_contents_parsed",
    "successful_v5_log_contents_inspected",
    "source_support_outcomes_used_for_v6_design",
    "noncompleted_v5_shards_used", "pre_v5_campaign_shards_used",
    "whole_campaign_rerun", "outcome_blind_selective_repair",
    "v6_reuse_is_scheduler_defined",
    "pre_diagnosis_freeze",
})
ACCOUNTING_RECORD_FIELDS = frozenset({
    "job_id", "job_id_raw", "state", "exit_code", "elapsed",
    "requested_memory", "max_rss", "max_vm_size", "node_list",
})
FAILURE_RECORD_COMMON_FIELDS = frozenset({
    "array_task", "state", "exit_code", "failure_class",
    "log_inspected", "path", "accounting_rows",
})
FAILURE_RECORD_LOG_FIELDS = frozenset({
    "task_name", "bytes", "sha256",
})
EXIT_CODE_RE = re.compile(r"(?:0|[1-9][0-9]*):(?:0|[1-9][0-9]*)")
ELAPSED_RE = re.compile(
    r"(?:(?:0|[1-9][0-9]*)-)?([0-9]{2}):[0-5][0-9]:[0-5][0-9]"
)
MEMORY_VALUE_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?[KMGTPE]?[cn]?")
NODE_LIST_RE = re.compile(r"[!-~]+")
JOB_ID_RAW_RE = re.compile(
    r"([0-9]+(?:_[0-9]+)?)(\.(?:batch|extern))?"
)


def _canonical_json(value) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii") + b"\n"
    except (TypeError, ValueError) as err:
        raise LaunchAuditError("value is not canonical finite JSON") from err


def _safe_file(path: Path, label: str, *, root: Path | None = None):
    try:
        return SafeIO.read_regular_file(
            Path(path), label=label, expected_path=Path(path), root=root
        )
    except SafeIO.SafeReadError as err:
        raise LaunchAuditError(str(err)) from err


def _safe_tree(path: Path, label: str):
    try:
        return SafeTreeIO.read_streaming_tree(
            Path(path), label=label, expected_path=Path(path)
        )
    except SafeTreeIO.SafeTreeError as err:
        raise LaunchAuditError(str(err)) from err


def _safe_directory(path: Path, label: str):
    try:
        return SafeIO.inspect_directory(
            Path(path), label=label, expected_path=Path(path)
        )
    except SafeIO.SafeReadError as err:
        raise LaunchAuditError(str(err)) from err


def _load_json(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        loaded, value = SafeIO.read_canonical_json(
            Path(path), label=label, canonical_json_line=_canonical_json,
            expected_path=Path(path),
        )
    except SafeIO.SafeReadError as err:
        raise LaunchAuditError(str(err)) from err
    return loaded.raw, value


def _exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    try:
        return Source.atomic_exclusive_bytes(path, raw, label)
    except Source.SourceAuditError as err:
        raise LaunchAuditError(str(err)) from err


def _exclusive_json(path: Path, value, label: str) -> str:
    return _exclusive_bytes(path, _canonical_json(value), label)


def _sha256(path: Path, label: str | None = None) -> str:
    return _safe_file(path, label or str(path)).sha256


def _root_identity(path: Path, label: str, *, require_empty: bool = False) -> dict:
    path = Path(path)
    loaded = _safe_directory(path, label)
    info = loaded.identity
    if (
        not path.is_absolute()
        or path != Path(os.path.normpath(path))
        or not stat.S_ISDIR(info["mode"])
        or stat.S_IMODE(info["mode"]) != 0o700
        or info["uid"] != os.getuid()
        or (require_empty and loaded.entries)
    ):
        raise LaunchAuditError("{} identity changed".format(label))
    return {
        "path": str(path), "canonical_path": str(path),
        "device": info["device"], "inode": info["inode"],
        "mode": "0700", "uid": info["uid"],
    }


def _create_private_directory(path: Path, label: str) -> dict:
    path = Path(path)
    try:
        SafeIO.inspect_directory(
            path.parent, label=label + " parent", expected_path=path.parent
        )
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
        path.chmod(0o700)
    except (OSError, SafeIO.SafeReadError) as err:
        raise LaunchAuditError("cannot create {}".format(label)) from err
    return _root_identity(path, label, require_empty=True)


def _executable_identity(path: Path, expected_sha256: str, label: str) -> dict:
    loaded = _safe_file(path, label)
    if (
        not path.is_absolute()
        or not stat.S_ISREG(loaded.identity["mode"])
        or stat.S_IMODE(loaded.identity["mode"]) & 0o111 == 0
        or not os.access(path, os.X_OK)
        or loaded.sha256 != expected_sha256
    ):
        raise LaunchAuditError("pinned {} identity changed".format(label))
    return {"path": str(path), "sha256": expected_sha256}


def _pre_diagnosis_file_records() -> list[dict]:
    if (
        PRE_DIAGNOSIS_FILES != tuple(sorted(set(PRE_DIAGNOSIS_FILES)))
        or DIAGNOSTIC_RELATIVE_PATH in PRE_DIAGNOSIS_FILES
        or set(PRE_DIAGNOSIS_FILES)
        != set(Source.CODE_MANIFEST_FILES) - {DIAGNOSTIC_RELATIVE_PATH}
    ):
        raise LaunchAuditError("V6 pre-diagnosis file set changed")
    records = []
    for relative in PRE_DIAGNOSIS_FILES:
        path = REPO / relative
        loaded = _safe_file(path, "V6 pre-diagnosis source", root=REPO)
        records.append({
            "path": relative,
            "bytes": loaded.identity["size"],
            "sha256": loaded.sha256,
        })
    return records


def _pre_diagnosis_freeze() -> dict:
    """Attest the committed outcome-free V6 design before any V5 access."""
    generic = V5Launch.Generic
    jj_path = Path(generic.JJ_COMMAND)
    jj_identity = _executable_identity(
        jj_path, generic.JJ_EXECUTABLE_SHA256, "jj"
    )
    jj = str(jj_path)

    def repository_state():
        try:
            changed = subprocess.check_output(
                [jj, "--no-pager", "diff", "--summary", "-r", "@", "--",
                 *PRE_DIAGNOSIS_FILES],
                cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), text=True,
            )
            tracked = subprocess.check_output(
                [jj, "--no-pager", "file", "list", "-r", "@-", "--",
                 *PRE_DIAGNOSIS_FILES],
                cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), text=True,
            ).splitlines()
            commit_id = subprocess.check_output(
                [jj, "--no-pager", "log", "-r", "@-", "--no-graph", "-T",
                 'commit_id ++ "\\n"'],
                cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), text=True,
            ).strip()
        except (OSError, subprocess.CalledProcessError) as err:
            raise LaunchAuditError(
                "cannot freeze the V6 pre-diagnosis design"
            ) from err
        return changed, tracked, commit_id

    before = repository_state()
    records = _pre_diagnosis_file_records()
    after = repository_state()
    changed, tracked, commit_id = after
    if (
        _executable_identity(jj_path, generic.JJ_EXECUTABLE_SHA256, "jj")
        != jj_identity
        or before != after
        or changed
        or tracked != list(PRE_DIAGNOSIS_FILES)
        or JJ_COMMIT_RE.fullmatch(commit_id or "") is None
    ):
        raise LaunchAuditError(
            "V6 pre-diagnosis files must be clean and tracked at @-"
        )
    return {
        "schema": DIAGNOSTIC_SCHEMA + "/pre-diagnosis-freeze/v1",
        "repository_commit_id": commit_id,
        "working_copy_revision": "@",
        "committed_revision": "@-",
        "scoped_diff_empty": True,
        "diagnostic_excluded": True,
        "jj": jj_identity,
        "files": records,
        "files_sha256": hashlib.sha256(_canonical_json(records)).hexdigest(),
    }


def _validate_pre_diagnosis_freeze(value: dict) -> None:
    expected_keys = {
        "schema", "repository_commit_id", "working_copy_revision",
        "committed_revision", "scoped_diff_empty", "diagnostic_excluded",
        "jj", "files", "files_sha256",
    }
    files = value.get("files") if isinstance(value, dict) else None
    if not isinstance(files, list):
        raise LaunchAuditError("V6 pre-diagnosis freeze changed")
    actual = _pre_diagnosis_file_records()
    if (
        set(value) != expected_keys
        or value.get("schema")
        != DIAGNOSTIC_SCHEMA + "/pre-diagnosis-freeze/v1"
        or not _matches(JJ_COMMIT_RE, value.get("repository_commit_id"))
        or value.get("working_copy_revision") != "@"
        or value.get("committed_revision") != "@-"
        or value.get("scoped_diff_empty") is not True
        or value.get("diagnostic_excluded") is not True
        or value.get("jj") != {
            "path": str(V5Launch.Generic.JJ_COMMAND),
            "sha256": V5Launch.Generic.JJ_EXECUTABLE_SHA256,
        }
        or files != actual
        or value.get("files_sha256")
        != hashlib.sha256(_canonical_json(files)).hexdigest()
    ):
        raise LaunchAuditError("V6 pre-diagnosis freeze changed")


def _manifest_records(path: Path, expected_sha256: str) -> dict[str, str]:
    loaded = _safe_file(path, "V6 code manifest", root=REPO)
    if loaded.sha256 != expected_sha256:
        raise LaunchAuditError("V6 code manifest hash changed")
    try:
        lines = loaded.raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise LaunchAuditError("V6 code manifest is not ASCII") from err
    records = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([!-~]+)", line)
        if match is None or match.group(2) in records:
            raise LaunchAuditError("V6 code manifest is malformed")
        records[match.group(2)] = match.group(1)
    if tuple(sorted(records)) != tuple(Source.CODE_MANIFEST_FILES):
        raise LaunchAuditError("V6 code manifest file set changed")
    return records


def _validate_freeze_against_manifest(
    freeze: dict, manifest_path: Path, manifest_sha256: str
) -> None:
    _validate_pre_diagnosis_freeze(freeze)
    manifest = _manifest_records(manifest_path, manifest_sha256)
    frozen = {item["path"]: item["sha256"] for item in freeze["files"]}
    if any(manifest.get(path) != sha256 for path, sha256 in frozen.items()):
        raise LaunchAuditError("V6 manifest differs from pre-diagnosis bytes")


def _sacct(command: list[str]) -> str:
    _executable_identity(SACCT_COMMAND, SACCT_COMMAND_SHA256, "sacct")
    try:
        return subprocess.check_output(
            command, env=dict(SUBMISSION_ENVIRONMENT), text=True
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot query V6 source-audit accounting") from err


def _validate_rows(rows: list[dict]) -> None:
    _validate_sparse_rows(rows, list(range(ARRAY_TASKS)), "V5")


def _validate_sparse_rows(rows, expected: list[int], campaign: str) -> None:
    if type(rows) is not list or len(rows) != len(expected):
        raise LaunchAuditError("{} scheduler row cardinality changed".format(
            campaign
        ))
    for index, row in zip(expected, rows):
        if (
            type(row) is not dict
            or set(row) != ROW_KEYS
            or row.get("array_task") != index
            or row.get("partition") != PARTITION
            or row.get("state") not in ALLOWED_SCHEDULER_STATES
            or not _matches(EXIT_CODE_RE, row.get("exit_code"))
            or not _valid_elapsed(row.get("elapsed"))
        ):
            raise LaunchAuditError("{} scheduler row identity changed".format(
                campaign
            ))


def _valid_elapsed(value) -> bool:
    match = ELAPSED_RE.fullmatch(value) if isinstance(value, str) else None
    return match is not None and int(match.group(1)) < 24


def _matches(pattern: re.Pattern, value) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _valid_optional(pattern: re.Pattern, value) -> bool:
    return value is None or (
        isinstance(value, str) and pattern.fullmatch(value) is not None
    )


def _job_id_raw_root(
    job_id: str, raw: str, parent_id: str
) -> str | None:
    if not all(isinstance(value, str) for value in (job_id, raw, parent_id)):
        return None
    if job_id == parent_id:
        suffix = ""
    elif job_id == parent_id + ".batch":
        suffix = ".batch"
    elif job_id == parent_id + ".extern":
        suffix = ".extern"
    else:
        return None
    match = JOB_ID_RAW_RE.fullmatch(raw)
    if match is None or (match.group(2) or "") != suffix:
        return None
    return match.group(1)


def _partition_terminal_rows(rows: list[dict]) -> tuple[list[int], list[int]]:
    """Select reuse solely from terminal scheduler state and exit code."""
    _validate_rows(rows)
    reusable = []
    repair = []
    for row in rows:
        state = row["state"]
        exit_code = row["exit_code"]
        if state == "COMPLETED" and exit_code == "0:0":
            reusable.append(row["array_task"])
        elif state in ACTIVE_STATES:
            raise LaunchAuditError("V5 source-audit array is not terminal")
        elif (
            (state == "FAILED" and exit_code == "75:0")
            or (state == "OUT_OF_MEMORY" and exit_code == "0:125")
            or state in SCHEDULER_INTERRUPTION_STATES
        ):
            repair.append(row["array_task"])
        else:
            raise LaunchAuditError(
                "V5 task {} has a non-infrastructure terminal result {} {}"
                .format(row["array_task"], state, exit_code)
            )
    if (
        sorted(reusable + repair) != list(range(ARRAY_TASKS))
        or set(reusable) & set(repair)
    ):
        raise LaunchAuditError("V5 reuse/repair partition changed")
    return reusable, repair


def _validate_shard_partition(
    reusable: list[int], repair: list[int]
) -> None:
    if (
        type(reusable) is not list
        or type(repair) is not list
        or not repair
        or reusable != sorted(set(reusable))
        or repair != sorted(set(repair))
        or any(type(index) is not int for index in reusable + repair)
        or set(reusable) & set(repair)
        or sorted(reusable + repair) != list(range(ARRAY_TASKS))
    ):
        raise LaunchAuditError("V6 shard partition is not an exact complement")


def _failure_log_record(
    job_id: str, row: dict, expected_records: list[dict] | None = None
) -> dict:
    task = row["array_task"]
    state = row["state"]
    path = V5_OUTPUT_DIR / "slurm-{}_{}.out".format(job_id, task)
    if state in SCHEDULER_INTERRUPTION_STATES:
        return {
            "array_task": task,
            "state": state,
            "exit_code": row["exit_code"],
            "failure_class": "scheduler-interruption",
            "log_inspected": False,
            "path": str(path),
        }
    payload = _safe_file(
        path, "V5 failed-task log", root=V5_OUTPUT_DIR
    ).raw
    task_matches = re.findall(
        rb"^\[[12]/2\] ([^\r\n]+)\r?$", payload, re.MULTILINE
    )
    try:
        task_name = task_matches[-1].decode("ascii")
    except (IndexError, UnicodeDecodeError) as err:
        raise LaunchAuditError("V5 failed-task identity is absent") from err
    if expected_records is not None:
        expected_names = {
            "{}:{}".format(record["directory"], record["problem"])
            for record in expected_records
        }
        if task_name not in expected_names:
            raise LaunchAuditError("V5 failed-task identity changed")
    if state == "FAILED":
        timeout_matches = re.findall(
            rb"infrastructure error: translator exceeded 28800s for "
            + re.escape(task_name.encode("ascii"))
            + rb"; stderr_sha256=([0-9a-f]{64}); "
            rb"stderr_tail=''",
            payload,
        )
        if timeout_matches != [EMPTY_SHA256.encode("ascii")]:
            raise LaunchAuditError(
                "V5 FAILED task {} is not the frozen translator timeout"
                .format(task)
            )
        failure_class = "translator-wallclock-timeout"
    elif (
        state == "OUT_OF_MEMORY"
        and b"translator critical exit -9" in payload
        and b"oom_kill" in payload
    ):
        failure_class = "scheduler-out-of-memory"
    else:
        raise LaunchAuditError(
            "V5 task {} has unclassified failure evidence".format(task)
        )
    return {
        "array_task": task,
        "state": state,
        "exit_code": row["exit_code"],
        "failure_class": failure_class,
        "task_name": task_name,
        "log_inspected": True,
        "path": str(path),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _failure_accounting_rows(job_id: str, row: dict) -> list[dict]:
    task = row["array_task"]
    output = _sacct([
        str(SACCT_COMMAND), "-j", "{}_{}".format(job_id, task),
        "-n", "-P", "--format=JobID,JobIDRaw,State,ExitCode,Elapsed,"
        "ReqMem,MaxRSS,MaxVMSize,NodeList",
    ])
    return _parse_failure_accounting(output, job_id, row)


def _parse_failure_accounting(
    output: str, job_id: str, row: dict
) -> list[dict]:
    if (
        not isinstance(output, str)
        or not isinstance(job_id, str)
        or not job_id.isdigit()
        or type(row) is not dict
        or set(row) != ROW_KEYS
    ):
        raise LaunchAuditError("V5 failed-task accounting input changed")
    task = row["array_task"]
    prefix = "{}_{}".format(job_id, task)
    allowed_ids = (prefix, prefix + ".batch", prefix + ".extern")
    records = []
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 9:
            raise LaunchAuditError("V5 failed-task accounting row changed")
        job_name, raw, state, exit_code, elapsed, req_mem, rss, vm, nodes = fields
        if (
            job_name not in allowed_ids
            or any(record["job_id"] == job_name for record in records)
            or state not in TERMINAL_ACCOUNTING_STATES
            or EXIT_CODE_RE.fullmatch(exit_code) is None
            or not _valid_elapsed(elapsed)
            or _job_id_raw_root(job_name, raw, prefix) is None
            or (req_mem and MEMORY_VALUE_RE.fullmatch(req_mem) is None)
            or (rss and MEMORY_VALUE_RE.fullmatch(rss) is None)
            or (vm and MEMORY_VALUE_RE.fullmatch(vm) is None)
            or (nodes and NODE_LIST_RE.fullmatch(nodes) is None)
        ):
            raise LaunchAuditError("V5 failed-task accounting field changed")
        records.append({
            "job_id": job_name,
            "job_id_raw": raw,
            "state": state,
            "exit_code": exit_code,
            "elapsed": elapsed,
            "requested_memory": req_mem or None,
            "max_rss": rss or None,
            "max_vm_size": vm or None,
            "node_list": nodes or None,
        })
    if [allowed_ids.index(record["job_id"]) for record in records] != sorted(
        allowed_ids.index(record["job_id"]) for record in records
    ):
        raise LaunchAuditError("V5 failed-task accounting order changed")
    parent = [record for record in records if record["job_id"] == prefix]
    parent_raw_root = (
        _job_id_raw_root(
            parent[0]["job_id"], parent[0]["job_id_raw"], prefix
        )
        if len(parent) == 1 else None
    )
    if (
        len(parent) != 1
        or parent_raw_root is None
        or any(
            _job_id_raw_root(
                record["job_id"], record["job_id_raw"], prefix
            ) != parent_raw_root
            for record in records
        )
        or parent[0]["state"] != row["state"]
        or parent[0]["exit_code"] != row["exit_code"]
        or parent[0]["elapsed"] != row["elapsed"]
        or parent[0]["requested_memory"] != V5_MEMORY_PER_CPU
    ):
        raise LaunchAuditError("V5 failed-task resource accounting changed")
    return records


def _validate_failure_records(
    failures: list[dict], rows: list[dict], repair: list[int], job_id: str
) -> list[str]:
    if (
        not isinstance(failures, list)
        or len(failures) != len(repair)
        or [item.get("array_task") if isinstance(item, dict) else None
            for item in failures] != repair
    ):
        raise LaunchAuditError("V5 failure-record set changed")
    classes = []
    for item, index in zip(failures, repair):
        row = rows[index]
        expected_class = {
            "FAILED": "translator-wallclock-timeout",
            "OUT_OF_MEMORY": "scheduler-out-of-memory",
        }.get(row["state"], "scheduler-interruption")
        accounting = item.get("accounting_rows")
        expected_item_fields = FAILURE_RECORD_COMMON_FIELDS
        if expected_class != "scheduler-interruption":
            expected_item_fields |= FAILURE_RECORD_LOG_FIELDS
        if not isinstance(accounting, list):
            raise LaunchAuditError("V5 classified failure record changed")
        accounting_ids = []
        allowed_ids = (
            "{}_{}".format(job_id, index),
            "{}_{}.batch".format(job_id, index),
            "{}_{}.extern".format(job_id, index),
        )
        for record in accounting:
            if (
                type(record) is not dict
                or set(record) != ACCOUNTING_RECORD_FIELDS
                or record.get("job_id") not in allowed_ids
                or record.get("state") not in TERMINAL_ACCOUNTING_STATES
                or not _matches(EXIT_CODE_RE, record.get("exit_code"))
                or not _valid_elapsed(record.get("elapsed"))
                or _job_id_raw_root(
                    record.get("job_id", ""),
                    record.get("job_id_raw", ""),
                    "{}_{}".format(job_id, index),
                ) is None
                or not _valid_optional(
                    MEMORY_VALUE_RE, record.get("requested_memory")
                )
                or not _valid_optional(MEMORY_VALUE_RE, record.get("max_rss"))
                or not _valid_optional(
                    MEMORY_VALUE_RE, record.get("max_vm_size")
                )
                or not _valid_optional(NODE_LIST_RE, record.get("node_list"))
            ):
                raise LaunchAuditError("V5 failure accounting record changed")
            accounting_ids.append(record["job_id"])
        if (
            len(accounting_ids) != len(set(accounting_ids))
            or [allowed_ids.index(item) for item in accounting_ids]
            != sorted(allowed_ids.index(item) for item in accounting_ids)
        ):
            raise LaunchAuditError("V5 failure accounting record changed")
        parents = [
            record for record in accounting or []
            if isinstance(record, dict)
            and record.get("job_id") == "{}_{}".format(job_id, index)
        ]
        parent_id = "{}_{}".format(job_id, index)
        parent_raw_root = (
            _job_id_raw_root(
                parents[0].get("job_id"),
                parents[0].get("job_id_raw"),
                parent_id,
            )
            if len(parents) == 1 else None
        )
        if (
            set(item) != expected_item_fields
            or item.get("state") != row["state"]
            or item.get("exit_code") != row["exit_code"]
            or item.get("failure_class") != expected_class
            or len(parents) != 1
            or parent_raw_root is None
            or any(
                _job_id_raw_root(
                    record.get("job_id"),
                    record.get("job_id_raw"),
                    parent_id,
                ) != parent_raw_root
                for record in accounting
            )
            or parents[0].get("state") != row["state"]
            or parents[0].get("exit_code") != row["exit_code"]
            or parents[0].get("elapsed") != row["elapsed"]
            or parents[0].get("requested_memory") != V5_MEMORY_PER_CPU
            or item.get("path") != str(
                V5_OUTPUT_DIR / "slurm-{}_{}.out".format(job_id, index)
            )
            or (
                expected_class == "scheduler-interruption"
                and item.get("log_inspected") is not False
            )
            or (
                expected_class != "scheduler-interruption"
                and (
                    item.get("log_inspected") is not True
                    or not isinstance(item.get("task_name"), str)
                    or not item["task_name"]
                    or not _matches(SHA256_RE, item.get("sha256"))
                    or type(item.get("bytes")) is not int
                    or item["bytes"] < 0
                )
            )
        ):
            raise LaunchAuditError("V5 classified failure record changed")
        classes.append(expected_class)
    return sorted(set(classes))


def _resource_mapping(failure_classes) -> dict:
    """Map infrastructure classes to one uniform, outcome-free V6 request."""
    classes = frozenset(failure_classes)
    if not classes or not classes <= ALLOWED_FAILURE_CLASSES:
        raise LaunchAuditError("V6 failure-class set is not authorized")
    memory_amended = "scheduler-out-of-memory" in classes
    time_amended = "translator-wallclock-timeout" in classes
    if memory_amended and V6_TOTAL_MEMORY_MIB >= FAT_NODE_REAL_MEMORY_MIB:
        raise LaunchAuditError("V6 memory request does not fit a frozen fat node")
    return {
        "classified_failure_classes": sorted(classes),
        "uniform_for_every_repair_shard": True,
        "cpus_per_task": CPUS_PER_TASK,
        "memory": {
            "option": "--mem={}".format(V6_TOTAL_MEMORY)
            if memory_amended else
            "--mem-per-cpu={}".format(V5_MEMORY_PER_CPU),
            "requested": V6_TOTAL_MEMORY if memory_amended else V5_MEMORY_PER_CPU,
            "mode": "total" if memory_amended else "per-cpu",
            "amended": memory_amended,
            "decision_rule": (
                "request 3000G total iff a scheduler OOM is classified; "
                "otherwise retain V5's 2T per CPU"
            ),
        },
        "task_timeout_seconds": (
            V6_TASK_TIMEOUT_SECONDS if time_amended
            else V5_TASK_TIMEOUT_SECONDS
        ),
        "time_limit": V6_TIME_LIMIT if time_amended else V5_TIME_LIMIT,
        "time_amended": time_amended,
        "time_decision_rule": (
            "use the fixed 115200-second per-candidate and three-day fat-"
            "partition ceiling iff an exact producer timeout is classified; "
            "otherwise retain V5 limits"
        ),
        "fat_node_real_memory_mib": FAT_NODE_REAL_MEMORY_MIB,
        "v6_total_memory_mib": V6_TOTAL_MEMORY_MIB if memory_amended else None,
        "outcome_fields_consulted": [],
        "resource_ceiling_policy": {
            "child_level_exclusion_allowed": False,
            "seal_requires_every_repair_shard_completed_0_0": True,
            "on_ceiling_failure": (
                "V6 fails closed; define a prospective V7 on larger hardware "
                "or revise the population before inspecting source outcomes"
            ),
            "partial_repair_shards_usable": False,
        },
    }


def _allowed_v5_output_names(job_id: str) -> set[str]:
    names = {V5_SOURCE_INVENTORY.name}
    for index in range(ARRAY_TASKS):
        names.add(V5Source.shard_path(V5_OUTPUT_DIR, index).name)
        names.add(V5Source.task_environment_path(V5_OUTPUT_DIR, index).name)
        names.add("slurm-{}_{}.out".format(job_id, index))
    return names


def _opaque_v5_output_manifest(
    launch: dict, reusable: list[int], repair: list[int]
) -> dict:
    """Hash V5 outputs without decoding any source/support record."""
    tree = _safe_tree(V5_OUTPUT_DIR, "terminal V5 output tree")
    if tree.directories:
        raise LaunchAuditError("terminal V5 output tree contains directories")
    by_name = {item.path: item for item in tree.files}
    if set(by_name) - _allowed_v5_output_names(launch["job_id"]):
        raise LaunchAuditError("terminal V5 output tree has unexpected files")
    inventory = by_name.get(V5_SOURCE_INVENTORY.name)
    if (
        inventory is None
        or inventory.sha256 != launch.get("source_inventory_sha256")
    ):
        raise LaunchAuditError("terminal V5 source inventory changed")
    for index in reusable:
        required = {
            V5Source.shard_path(V5_OUTPUT_DIR, index).name,
            V5Source.task_environment_path(V5_OUTPUT_DIR, index).name,
            "slurm-{}_{}.out".format(launch["job_id"], index),
        }
        if not required <= set(by_name):
            raise LaunchAuditError(
                "scheduler-completed V5 task {} lacks a reusable triplet"
                .format(index)
            )
    root = tree.root_identity
    root_identity = {
        "path": str(V5_OUTPUT_DIR), "canonical_path": str(V5_OUTPUT_DIR),
        "device": root["device"], "inode": root["inode"],
        "mode": "0700", "uid": root["uid"],
    }
    if (
        not stat.S_ISDIR(root["mode"])
        or stat.S_IMODE(root["mode"]) != 0o700
        or root_identity != launch.get("launch_root_identities", {}).get(
            "output_dir"
        )
    ):
        raise LaunchAuditError("terminal V5 output root identity changed")
    records = [
        {"path": item.path, "bytes": item.identity["size"], "sha256": item.sha256}
        for item in tree.files
    ]
    digest = hashlib.sha256()
    digest.update(b"root-identity\0" + _canonical_json(root_identity))
    for item in records:
        digest.update(
            item["path"].encode("ascii") + b"\0"
            + bytes.fromhex(item["sha256"])
        )
    repair_set = set(repair)
    quarantined = [
        item for item in records
        if any(
            item["path"] == V5Source.shard_path(V5_OUTPUT_DIR, index).name
            or item["path"] == V5Source.task_environment_path(
                V5_OUTPUT_DIR, index
            ).name
            for index in repair_set
        )
    ]
    return {
        "sha256": digest.hexdigest(),
        "root_identity": root_identity,
        "files_count": len(records),
        "files": records,
        "successful_files_parsed": False,
        "successful_files_opaque_hashed": True,
        "noncompleted_partial_files_quarantined": quarantined,
        "noncompleted_partial_files_used": False,
    }


def _validate_opaque_v5_manifest(
    value: dict, launch: dict, reusable: list[int], repair: list[int]
) -> None:
    files = value.get("files") if isinstance(value, dict) else None
    if not isinstance(files, list):
        raise LaunchAuditError("opaque V5 output manifest changed")
    by_path = {}
    for item in files:
        if (
            not isinstance(item, dict)
            or set(item) != {"path", "bytes", "sha256"}
            or not isinstance(item["path"], str)
            or item["path"] in by_path
            or item["path"] not in _allowed_v5_output_names(launch["job_id"])
            or type(item["bytes"]) is not int
            or item["bytes"] < 0
            or not _matches(SHA256_RE, item["sha256"])
        ):
            raise LaunchAuditError("opaque V5 output file record changed")
        by_path[item["path"]] = item
    if [item["path"] for item in files] != sorted(by_path):
        raise LaunchAuditError("opaque V5 output file order changed")
    for index in reusable:
        required = {
            V5Source.shard_path(V5_OUTPUT_DIR, index).name,
            V5Source.task_environment_path(V5_OUTPUT_DIR, index).name,
            "slurm-{}_{}.out".format(launch["job_id"], index),
        }
        if not required <= set(by_path):
            raise LaunchAuditError("opaque V5 reusable triplet changed")
    inventory = by_path.get(V5_SOURCE_INVENTORY.name)
    if (
        inventory is None
        or inventory["sha256"] != launch.get("source_inventory_sha256")
    ):
        raise LaunchAuditError("opaque V5 inventory record changed")
    expected_quarantine = [
        item for item in files
        if any(
            item["path"] == V5Source.shard_path(V5_OUTPUT_DIR, index).name
            or item["path"] == V5Source.task_environment_path(
                V5_OUTPUT_DIR, index
            ).name
            for index in repair
        )
    ]
    root = value.get("root_identity")
    digest = hashlib.sha256()
    if isinstance(root, dict):
        digest.update(b"root-identity\0" + _canonical_json(root))
    for item in files:
        digest.update(
            item["path"].encode("ascii") + b"\0"
            + bytes.fromhex(item["sha256"])
        )
    if (
        value.get("files_count") != len(files)
        or value.get("sha256") != digest.hexdigest()
        or root != launch.get("launch_root_identities", {}).get("output_dir")
        or value.get("successful_files_parsed") is not False
        or value.get("successful_files_opaque_hashed") is not True
        or value.get("noncompleted_partial_files_quarantined")
        != expected_quarantine
        or value.get("noncompleted_partial_files_used") is not False
    ):
        raise LaunchAuditError("opaque V5 output manifest changed")


def _validate_failure_logs_against_tree(
    failures: list[dict], output_manifest: dict
) -> None:
    files = {
        item["path"]: item for item in output_manifest.get("files", [])
    }
    for failure in failures:
        if failure.get("log_inspected") is not True:
            continue
        path = Path(failure.get("path", ""))
        if path.parent != V5_OUTPUT_DIR:
            raise LaunchAuditError("V5 failure log escaped its output tree")
        frozen = files.get(path.name)
        if (
            frozen is None
            or frozen.get("bytes") != failure.get("bytes")
            or frozen.get("sha256") != failure.get("sha256")
        ):
            raise LaunchAuditError(
                "V5 classified failure log differs from opaque tree"
            )


def diagnose_v5() -> None:
    pre_diagnosis_freeze = _pre_diagnosis_freeze()
    if DIAGNOSTIC.exists():
        raise LaunchAuditError("V5 terminal diagnostic already exists")
    if any(os.path.lexists(path) for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR, TMP_ROOT,
        UNION_DIR, CANDIDATE, ATTESTATION, CODE_MANIFEST,
        *SEAL_STAGE_ARTIFACTS,
    )):
        raise LaunchAuditError("V6 namespace is not empty before diagnosis")
    if any(os.path.lexists(path) for path in (
        V5_EXECUTION_RECEIPT, V5_CANDIDATE, V5_ATTESTATION,
    )):
        raise LaunchAuditError("V5 is already sealed; V6 repair is forbidden")
    launch_sha, launch = V5Launch._load_launch()
    rows = _scheduler_rows(launch["job_id"], list(range(ARRAY_TASKS)))
    reusable, repair = _partition_terminal_rows(rows)
    _validate_shard_partition(reusable, repair)
    if not repair:
        raise LaunchAuditError("V5 has no repair complement; use the V5 seal")
    try:
        _inventory_sha, inventory_records = V5Source.load_inventory_manifest(
            V5_SOURCE_INVENTORY, launch["source_inventory_sha256"]
        )
    except V5Source.SourceAuditError as err:
        raise LaunchAuditError("V5 source inventory changed") from err
    failures = []
    for index in repair:
        row = rows[index]
        start = index * Source.TASKS_PER_SHARD
        log = _failure_log_record(
            launch["job_id"], row,
            inventory_records[start:start + Source.TASKS_PER_SHARD],
        )
        accounting = _failure_accounting_rows(launch["job_id"], row)
        failures.append({**log, "accounting_rows": accounting})
    classes = set(_validate_failure_records(
        failures, rows, repair, launch["job_id"]
    ))
    resources = _resource_mapping(classes)
    output_manifest = _opaque_v5_output_manifest(launch, reusable, repair)
    _validate_opaque_v5_manifest(output_manifest, launch, reusable, repair)
    _validate_failure_logs_against_tree(failures, output_manifest)
    intent_raw = _safe_file(V5_INTENT, "V5 launch intent").raw
    diagnostic = {
        "schema": DIAGNOSTIC_SCHEMA,
        "pre_diagnosis_freeze": pre_diagnosis_freeze,
        "v5_launch_intent_path": str(V5_INTENT),
        "v5_launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "v5_launch_receipt_path": str(V5_LAUNCH_RECEIPT),
        "v5_launch_receipt_sha256": launch_sha,
        "v5_launch_receipt": launch,
        "v5_code_manifest_path": str(V5_CODE_MANIFEST),
        "v5_code_manifest_sha256": launch["code_manifest_sha256"],
        "v5_source_inventory_sha256": launch["source_inventory_sha256"],
        "v5_scheduler_rows": rows,
        "v5_scheduler_rows_sha256": hashlib.sha256(
            _canonical_json(rows)
        ).hexdigest(),
        "v5_scheduler_state_counts": dict(sorted(Counter(
            row["state"] for row in rows
        ).items())),
        "logical_shards": ARRAY_TASKS,
        "candidates": Source.CANDIDATE_COUNT,
        "reuse_eligibility_rule": "scheduler state COMPLETED with exit 0:0 only",
        "reusable_v5_shard_indices": reusable,
        "reusable_v5_shard_indices_sha256": hashlib.sha256(
            _canonical_json(reusable)
        ).hexdigest(),
        "repair_v5_shard_indices": repair,
        "repair_v5_shard_indices_sha256": hashlib.sha256(
            _canonical_json(repair)
        ).hexdigest(),
        "reused_v5_shards": len(reusable),
        "repaired_v5_shards": len(repair),
        "repair_scope": "complete original two-candidate shards",
        "failure_records": failures,
        "failure_records_sha256": hashlib.sha256(
            _canonical_json(failures)
        ).hexdigest(),
        "failure_classes": sorted(classes),
        "resource_mapping": resources,
        "v5_output_manifest": output_manifest,
        "successful_v5_shard_contents_parsed": False,
        "successful_v5_log_contents_inspected": False,
        "source_support_outcomes_used_for_v6_design": False,
        "noncompleted_v5_shards_used": False,
        "pre_v5_campaign_shards_used": [],
        "whole_campaign_rerun": False,
        "outcome_blind_selective_repair": True,
        "v6_reuse_is_scheduler_defined": True,
    }
    digest = _exclusive_json(DIAGNOSTIC, diagnostic, "V5 terminal diagnostic")
    print(json.dumps({
        "diagnostic_sha256": digest,
        "reused_v5_shards": len(reusable),
        "repaired_v5_shards": len(repair),
        "resource_mapping": resources,
    }, sort_keys=True, indent=2))


def _load_diagnostic() -> tuple[str, dict]:
    raw, value = _load_json(DIAGNOSTIC, "V5 terminal diagnostic")
    if type(value) is not dict or set(value) != DIAGNOSTIC_FIELDS:
        raise LaunchAuditError("V5 terminal diagnostic schema changed")
    reusable = value.get("reusable_v5_shard_indices")
    repair = value.get("repair_v5_shard_indices")
    rows = value.get("v5_scheduler_rows")
    failures = value.get("failure_records")
    classes = value.get("failure_classes")
    launch = value.get("v5_launch_receipt")
    _validate_pre_diagnosis_freeze(value.get("pre_diagnosis_freeze"))
    _validate_shard_partition(reusable, repair)
    if (
        value.get("schema") != DIAGNOSTIC_SCHEMA
        or value.get("v5_launch_intent_path") != str(V5_INTENT)
        or value.get("v5_launch_receipt_path") != str(V5_LAUNCH_RECEIPT)
        or value.get("v5_code_manifest_path") != str(V5_CODE_MANIFEST)
        or not isinstance(launch, dict)
        or not isinstance(failures, list)
        or not isinstance(classes, list)
        or _partition_terminal_rows(rows) != (reusable, repair)
        or value.get("logical_shards") != ARRAY_TASKS
        or value.get("candidates") != Source.CANDIDATE_COUNT
        or value.get("reused_v5_shards") != len(reusable)
        or value.get("repaired_v5_shards") != len(repair)
        or value.get("reusable_v5_shard_indices_sha256")
        != hashlib.sha256(_canonical_json(reusable)).hexdigest()
        or value.get("repair_v5_shard_indices_sha256")
        != hashlib.sha256(_canonical_json(repair)).hexdigest()
        or value.get("v5_scheduler_rows_sha256")
        != hashlib.sha256(_canonical_json(rows)).hexdigest()
        or value.get("v5_scheduler_state_counts")
        != dict(sorted(Counter(row["state"] for row in rows).items()))
        or value.get("failure_records_sha256")
        != hashlib.sha256(_canonical_json(failures)).hexdigest()
        or _validate_failure_records(
            failures, rows, repair, launch.get("job_id", "")
        ) != classes
        or value.get("resource_mapping") != _resource_mapping(classes)
        or value.get("reuse_eligibility_rule")
        != "scheduler state COMPLETED with exit 0:0 only"
        or value.get("repair_scope") != "complete original two-candidate shards"
        or value.get("successful_v5_shard_contents_parsed") is not False
        or value.get("successful_v5_log_contents_inspected") is not False
        or value.get("source_support_outcomes_used_for_v6_design") is not False
        or value.get("noncompleted_v5_shards_used") is not False
        or value.get("pre_v5_campaign_shards_used") != []
        or value.get("whole_campaign_rerun") is not False
        or value.get("outcome_blind_selective_repair") is not True
        or value.get("v6_reuse_is_scheduler_defined") is not True
    ):
        raise LaunchAuditError("V5 terminal diagnostic changed")
    _validate_opaque_v5_manifest(
        value.get("v5_output_manifest"), launch, reusable, repair
    )
    _validate_failure_logs_against_tree(
        failures, value["v5_output_manifest"]
    )
    launch_raw, actual_launch = _load_json(
        V5_LAUNCH_RECEIPT, "V5 launch receipt"
    )
    if (
        hashlib.sha256(launch_raw).hexdigest()
        != value.get("v5_launch_receipt_sha256")
        or actual_launch != launch
        or _sha256(V5_INTENT) != value.get("v5_launch_intent_sha256")
        or _sha256(V5_CODE_MANIFEST) != value.get("v5_code_manifest_sha256")
        or launch.get("source_inventory_sha256")
        != value.get("v5_source_inventory_sha256")
    ):
        raise LaunchAuditError("V5 launch inputs changed after diagnosis")
    return hashlib.sha256(raw).hexdigest(), value


def _slurm_template() -> bytes:
    loaded = _safe_file(SLURM_TEMPLATE, "V6 Slurm template", root=REPO)
    raw = loaded.raw
    lines = raw.splitlines()
    required = {
        b"#!/bin/bash",
        b"set -euo pipefail",
        b'test "$#" -eq 0',
        b'source_inventory_sha256="bb9be49a4652ff7bedcadb04b4db35cad701a5b2a2a6d6347c15e0ad670e056e"',
        b'source_audit_output_dir="' + str(OUTPUT_DIR).encode("ascii") + b'"',
        b'task_timeout_seconds="' + TIMEOUT_PLACEHOLDER + b'"',
        b'[[ "${task_timeout_seconds}" =~ ^(28800|115200)$ ]]',
        b'[[ "${SLURM_ARRAY_JOB_ID}" =~ ^[0-9]+$ ]]',
        b'[[ "${SLURM_ARRAY_TASK_ID}" =~ ^[0-9]+$ ]]',
        b'test "${SLURM_ARRAY_TASK_ID}" -ge 0',
        b'test "${SLURM_ARRAY_TASK_ID}" -lt 820',
        b"unset PYTHONPATH PYTHONHOME VIRTUAL_ENV",
        b'export PYTHONNOUSERSITE="1"',
        b'export PYTHONDONTWRITEBYTECODE="1"',
        b'export PATH="/usr/bin:/bin"',
        b"cd " + str(REPO).encode("ascii"),
        b'code_manifest="experiments/pdb_terminal_incidence_confirmation_source_audit_v6_code.sha256"',
        b'code_manifest_sha256="' + MANIFEST_PLACEHOLDER + b'"',
        b'source_inventory="experiments/data/pdb_terminal_incidence_confirmation_source_audit_v6_repair/source-inventory-v6.json"',
        b'tmpdir_root="' + str(TMP_ROOT).encode("ascii") + b'"',
        b'python_executable="'
        + str(V5Launch.PYTHON_COMMAND).encode("ascii") + b'"',
        b'python_executable_sha256="'
        + Source.Base.PINNED_PYTHON_EXECUTABLE_SHA256.encode("ascii") + b'"',
        b'sha256sum_executable="/usr/bin/sha256sum"',
        b'sha256sum_executable_sha256="'
        + Source.V5.SHA256SUM_SHA256.encode("ascii") + b'"',
        b'mkdir_executable="/usr/bin/mkdir"',
        b'mkdir_executable_sha256="'
        + Source.V5.MKDIR_SHA256.encode("ascii") + b'"',
        b'rmdir_executable="/usr/bin/rmdir"',
        b'rmdir_executable_sha256="'
        + Source.V5.RMDIR_SHA256.encode("ascii") + b'"',
        b'actual_sha256sum="$("${sha256sum_executable}" "${sha256sum_executable}")"',
        b'test "${actual_sha256sum%% *}" = "${sha256sum_executable_sha256}"',
        b'actual_python="$("${sha256sum_executable}" "${python_executable}")"',
        b'test "${actual_python%% *}" = "${python_executable_sha256}"',
        b'actual_mkdir="$("${sha256sum_executable}" "${mkdir_executable}")"',
        b'test "${actual_mkdir%% *}" = "${mkdir_executable_sha256}"',
        b'actual_rmdir="$("${sha256sum_executable}" "${rmdir_executable}")"',
        b'test "${actual_rmdir%% *}" = "${rmdir_executable_sha256}"',
        b'actual_manifest="$("${sha256sum_executable}" "${code_manifest}")"',
        b'test "${actual_manifest%% *}" = "${code_manifest_sha256}"',
        b'actual_inventory="$("${sha256sum_executable}" "${source_inventory}")"',
        b'test "${actual_inventory%% *}" = "${source_inventory_sha256}"',
        b'"${sha256sum_executable}" --strict --check "${code_manifest}"',
        b'test -d "${tmpdir_root}"',
        b'test ! -L "${tmpdir_root}"',
        b'export TMPDIR="${tmpdir_root}/task-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"',
        b'export PYTHONPYCACHEPREFIX="${TMPDIR}/pycache"',
        b'test ! -e "${TMPDIR}"',
        b"umask 077",
        b'"${mkdir_executable}" --mode=0700 -- "${TMPDIR}"',
        b'    if ! "${rmdir_executable}" -- "${TMPDIR}"; then',
        b"trap cleanup_tmpdir EXIT",
        b'"${python_executable}" -B \\',
        b"    experiments/audit_pdb_terminal_incidence_confirmation_sources_v6.py scan \\",
        b'    --output-dir "${source_audit_output_dir}" \\',
        b'    --inventory-manifest "${source_inventory}" \\',
        b'    --inventory-sha256 "${source_inventory_sha256}" \\',
        b'    --num-shards 820 \\',
        b'    --shard-index "${SLURM_ARRAY_TASK_ID}" \\',
        b'    --task-timeout "${task_timeout_seconds}" \\',
        b'    --code-manifest "${code_manifest}" \\',
        b'    --code-manifest-sha256 "${code_manifest_sha256}"',
    }
    if (
        loaded.sha256 != NORMALIZED_SLURM_SHA256
        or not raw.endswith(b"\n")
        or not required <= set(lines)
        or any(lines.count(line) != 1 for line in required)
        or raw.count(TIMEOUT_PLACEHOLDER) != 1
        or raw.count(MANIFEST_PLACEHOLDER) != 1
        or any(line.startswith(b"#SBATCH") for line in lines)
        or b"rm -" in raw
        or b'="$1"' in raw
        or b'="$2"' in raw
        or raw.count(b"trap cleanup_tmpdir EXIT") != 1
    ):
        raise LaunchAuditError("V6 Slurm template contract changed")
    return raw


def _code_manifest_bytes() -> bytes:
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
            raise LaunchAuditError("V6 code manifest path set is invalid")
        seen.add(relative)
        path = REPO / relative
        records.append("{}  {}\n".format(
            _sha256(path, "V6 code manifest input"), relative
        ))
    return "".join(records).encode("ascii")


def prepare_manifest() -> None:
    if CODE_MANIFEST.exists():
        raise LaunchAuditError("V6 code manifest already exists")
    if any(os.path.lexists(path) for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR, TMP_ROOT,
        UNION_DIR, CANDIDATE, ATTESTATION, *SEAL_STAGE_ARTIFACTS,
    )):
        raise LaunchAuditError("V6 launch namespace is not empty")
    _diagnostic_sha, diagnostic = _load_diagnostic()
    _slurm_template()
    raw = _code_manifest_bytes()
    digest = _exclusive_bytes(CODE_MANIFEST, raw, "V6 code manifest")
    _validate_freeze_against_manifest(
        diagnostic["pre_diagnosis_freeze"], CODE_MANIFEST, digest
    )
    print(json.dumps({
        "code_manifest_path": str(CODE_MANIFEST),
        "code_manifest_sha256": digest,
        "files": len(Source.CODE_MANIFEST_FILES),
    }, sort_keys=True, indent=2))


def _render_slurm(code_manifest_sha256: str, timeout_seconds: int) -> bytes:
    if (
        not _matches(SHA256_RE, code_manifest_sha256)
        or timeout_seconds not in Source.ALLOWED_TIMEOUT_SECONDS
    ):
        raise LaunchAuditError("V6 rendered Slurm inputs are invalid")
    raw = _slurm_template()
    rendered = raw.replace(
        TIMEOUT_PLACEHOLDER, str(timeout_seconds).encode("ascii")
    ).replace(MANIFEST_PLACEHOLDER, code_manifest_sha256.encode("ascii"))
    if TIMEOUT_PLACEHOLDER in rendered or MANIFEST_PLACEHOLDER in rendered:
        raise LaunchAuditError("V6 Slurm placeholders remain")
    return rendered


def _array_spec(indices: list[int]) -> str:
    if (
        not indices
        or indices != sorted(set(indices))
        or any(type(index) is not int or not 0 <= index < ARRAY_TASKS
               for index in indices)
    ):
        raise LaunchAuditError("V6 repair task set is invalid")
    value = ",".join(map(str, indices))
    if "%" in value:
        raise LaunchAuditError("V6 repair array is throttled")
    return value


def _submission_identity(token: str) -> tuple[str, str]:
    if not isinstance(token, str) or SUBMISSION_TOKEN_RE.fullmatch(token) is None:
        raise LaunchAuditError("V6 submission token is invalid")
    return (
        "{}-{}".format(JOB_NAME_PREFIX, token),
        "{}/{}".format(COMMENT_PREFIX, token),
    )


def _submit_command(diagnostic: dict, token: str) -> list[str]:
    resources = diagnostic["resource_mapping"]
    repair = diagnostic["repair_v5_shard_indices"]
    job_name, comment = _submission_identity(token)
    return [
        str(SBATCH_COMMAND), "--parsable", "--export=NONE",
        "--job-name={}".format(job_name), "--comment={}".format(comment),
        "--account={}".format(ACCOUNT), "--partition={}".format(PARTITION),
        "--qos={}".format(QOS), "--array={}".format(_array_spec(repair)),
        "--nodes=1", "--ntasks=1", "--cpus-per-task=1",
        resources["memory"]["option"],
        "--time={}".format(resources["time_limit"]),
        "--nice=0", "--no-requeue", "--chdir={}".format(REPO),
        "--output={}".format(OUTPUT_DIR / "slurm-%A_%a.out"),
    ]


def _scoped_repository_commit() -> str:
    generic = V5Launch.Generic
    jj = str(generic.JJ_COMMAND)
    _executable_identity(
        Path(jj), generic.JJ_EXECUTABLE_SHA256, "jj"
    )
    try:
        changed = subprocess.check_output(
            [jj, "--no-pager", "diff", "--summary", "-r", "@", "--",
             *SCOPED_COMMIT_FILES],
            cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), text=True,
        )
        tracked = subprocess.check_output(
            [jj, "--no-pager", "file", "list", "-r", "@-", "--",
             *SCOPED_COMMIT_FILES],
            cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), text=True,
        ).splitlines()
        commit_id = subprocess.check_output(
            [jj, "--no-pager", "log", "-r", "@-", "--no-graph", "-T",
             'commit_id ++ "\\n"'],
            cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot attest scoped V6 commit") from err
    if (
        changed
        or set(tracked) != set(SCOPED_COMMIT_FILES)
        or len(tracked) != len(SCOPED_COMMIT_FILES)
        or JJ_COMMIT_RE.fullmatch(commit_id or "") is None
    ):
        raise LaunchAuditError("V6 requires every bound file committed at @-")
    return commit_id


def _execution_environment(code: dict) -> dict:
    return {
        "submission_export": "NONE",
        "slurm_export": "NONE",
        "path": CONTROLLED_PATH,
        "python_no_user_site": "1",
        "python_dont_write_bytecode": "1",
        "unset_variables": list(Source.UNSET_PYTHON_ENV),
        "tmpdir_root": str(TMP_ROOT),
        "tmpdir_template": Source.TMPDIR_TEMPLATE,
        "python_pycache_prefix_template": Source.PYTHON_CACHE_PREFIX_TEMPLATE,
        "source_snapshot_policy": Source.SOURCE_SNAPSHOT_POLICY,
        "python_environment": code,
    }


def _launch_materials(
    diagnostic_sha: str,
    diagnostic: dict,
    *,
    repository_commit_id: str | None = None,
    roots: dict | None = None,
) -> dict:
    manifest_sha = _sha256(CODE_MANIFEST, "V6 code manifest")
    timeout = diagnostic["resource_mapping"]["task_timeout_seconds"]
    Source.configure(timeout)
    code = Source.validate_code_manifest(CODE_MANIFEST, manifest_sha)
    _validate_freeze_against_manifest(
        diagnostic["pre_diagnosis_freeze"], CODE_MANIFEST, manifest_sha
    )
    rendered = _render_slurm(manifest_sha, timeout)
    if repository_commit_id is None:
        repository_commit_id = _scoped_repository_commit()
    if not _matches(JJ_COMMIT_RE, repository_commit_id):
        raise LaunchAuditError("V6 repository commit identity is invalid")
    if roots is None:
        roots = {
            "output_dir": _root_identity(OUTPUT_DIR, "V6 output directory"),
            "tmpdir_root": _root_identity(TMP_ROOT, "V6 TMPDIR root"),
        }
    elif roots != {
        "output_dir": _root_identity(OUTPUT_DIR, "V6 output directory"),
        "tmpdir_root": _root_identity(TMP_ROOT, "V6 TMPDIR root"),
    }:
        raise LaunchAuditError("V6 launch roots changed")
    benchmark_revision = diagnostic["v5_launch_receipt"].get(
        "benchmark_revision"
    )
    if benchmark_revision != Source.Base.Inventory.BENCHMARK_REVISION:
        raise LaunchAuditError("V6 benchmark revision changed")
    return {
        "campaign": "v6-selective-repair",
        "benchmark_revision": benchmark_revision,
        "v5_terminal_diagnostic_sha256": diagnostic_sha,
        "v5_launch_receipt_sha256": diagnostic["v5_launch_receipt_sha256"],
        "logical_shards": ARRAY_TASKS,
        "candidates": Source.CANDIDATE_COUNT,
        "reusable_v5_shard_indices": diagnostic[
            "reusable_v5_shard_indices"
        ],
        "repair_v5_shard_indices": diagnostic["repair_v5_shard_indices"],
        "reused_v1_shards": 0,
        "reused_v2_shards": 0,
        "reused_v3_shards": 0,
        "reused_v4_shards": 0,
        "reused_v5_shards": len(diagnostic["reusable_v5_shard_indices"]),
        "repaired_v5_shards": len(diagnostic["repair_v5_shard_indices"]),
        "reuse_eligibility_rule": diagnostic["reuse_eligibility_rule"],
        "repair_scope": "complete original two-candidate shards",
        "whole_campaign_rerun": False,
        "outcome_blind_selective_repair": True,
        "noncompleted_v5_shards_used": False,
        "array": _array_spec(diagnostic["repair_v5_shard_indices"]),
        "array_throttle": 0,
        "partition": PARTITION,
        "qos": QOS,
        "account": ACCOUNT,
        "cpus_per_task": CPUS_PER_TASK,
        "resource_mapping": diagnostic["resource_mapping"],
        "source_inventory_sha256": diagnostic["v5_source_inventory_sha256"],
        "code_manifest_sha256": manifest_sha,
        "slurm_template_sha256": _sha256(SLURM_TEMPLATE),
        "slurm_program_sha256": hashlib.sha256(rendered).hexdigest(),
        "slurm_program_bytes": len(rendered),
        "slurm_submission_mode": "stdin",
        "repository_commit_id": repository_commit_id,
        "scoped_repository_files": list(SCOPED_COMMIT_FILES),
        "launch_root_identities": roots,
        "output_dir": str(OUTPUT_DIR),
        "tmpdir_root": str(TMP_ROOT),
        "source_inventory_path": str(SOURCE_INVENTORY),
        "candidate_attestation": str(CANDIDATE),
        "frozen_attestation": str(ATTESTATION),
        "execution_environment": _execution_environment(code),
    }


def _write_launch_receipt(intent_raw: bytes, intent: dict, job_id: str) -> str:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("Slurm returned an invalid V6 job id")
    receipt = {
        "schema": LAUNCH_SCHEMA,
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": job_id,
    }
    return _exclusive_json(LAUNCH_RECEIPT, receipt, "V6 launch receipt")


def launch() -> None:
    if any(os.path.lexists(path) for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR, TMP_ROOT,
        UNION_DIR, CANDIDATE, ATTESTATION, *SEAL_STAGE_ARTIFACTS,
    )):
        raise LaunchAuditError("V6 launch namespace is not empty")
    diagnostic_sha, diagnostic = _load_diagnostic()
    repository_commit_id = _scoped_repository_commit()
    manifest_sha = _sha256(CODE_MANIFEST, "V6 code manifest")
    timeout = diagnostic["resource_mapping"]["task_timeout_seconds"]
    Source.configure(timeout)
    Source.validate_code_manifest(CODE_MANIFEST, manifest_sha)
    _validate_freeze_against_manifest(
        diagnostic["pre_diagnosis_freeze"], CODE_MANIFEST, manifest_sha
    )
    _render_slurm(manifest_sha, timeout)
    inventory = _safe_file(
        V5_SOURCE_INVENTORY, "V5 source inventory", root=V5_OUTPUT_DIR
    )
    if inventory.sha256 != diagnostic["v5_source_inventory_sha256"]:
        raise LaunchAuditError("V5 source inventory changed before V6 launch")
    if _opaque_v5_output_manifest(
        diagnostic["v5_launch_receipt"],
        diagnostic["reusable_v5_shard_indices"],
        diagnostic["repair_v5_shard_indices"],
    ) != diagnostic["v5_output_manifest"]:
        raise LaunchAuditError("V5 output bytes changed before V6 launch")
    output_identity = _create_private_directory(OUTPUT_DIR, "V6 output directory")
    tmp_identity = _create_private_directory(TMP_ROOT, "V6 TMPDIR root")
    roots = {"output_dir": output_identity, "tmpdir_root": tmp_identity}
    _exclusive_bytes(SOURCE_INVENTORY, inventory.raw, "V6 source inventory")
    materials = _launch_materials(
        diagnostic_sha, diagnostic,
        repository_commit_id=repository_commit_id, roots=roots,
    )
    token = secrets.token_hex(12)
    recorded = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )
    command = _submit_command(diagnostic, token)
    intent = {
        "schema": LAUNCH_SCHEMA + "/intent",
        **materials,
        "recorded_utc": recorded,
        "submission_token": token,
        "submit_command": command,
    }
    intent_raw = _canonical_json(intent)
    _exclusive_json(INTENT, intent, "V6 launch intent")
    rendered = _render_slurm(
        materials["code_manifest_sha256"],
        diagnostic["resource_mapping"]["task_timeout_seconds"],
    )
    if (
        hashlib.sha256(rendered).hexdigest()
        != materials["slurm_program_sha256"]
        or len(rendered) != materials["slurm_program_bytes"]
    ):
        raise LaunchAuditError("V6 rendered Slurm bytes changed before submission")
    _executable_identity(SBATCH_COMMAND, SBATCH_COMMAND_SHA256, "sbatch")
    try:
        completed = subprocess.run(
            command, input=rendered, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=REPO,
            env=dict(SUBMISSION_ENVIRONMENT), check=True,
        )
        output = completed.stdout.decode("ascii").strip()
    except (
        OSError, subprocess.CalledProcessError, UnicodeDecodeError,
    ) as err:
        raise LaunchAuditError("V6 sbatch failed after intent") from err
    job_id = output.split(";", 1)[0]
    digest = _write_launch_receipt(intent_raw, intent, job_id)
    print(json.dumps({
        "job_id": job_id,
        "launch_receipt_sha256": digest,
        "repair_v5_shard_indices": diagnostic["repair_v5_shard_indices"],
    }, sort_keys=True, indent=2))


def _load_intent_only() -> tuple[bytes, dict, dict, dict]:
    raw, intent = _load_json(INTENT, "V6 launch intent")
    diagnostic_sha, diagnostic = _load_diagnostic()
    materials = _launch_materials(
        diagnostic_sha, diagnostic,
        repository_commit_id=intent.get("repository_commit_id"),
        roots=intent.get("launch_root_identities"),
    )
    token = intent.get("submission_token")
    recorded = intent.get("recorded_utc")
    expected = {
        "schema": LAUNCH_SCHEMA + "/intent",
        **materials,
        "recorded_utc": recorded,
        "submission_token": token,
        "submit_command": _submit_command(diagnostic, token),
    }
    if (
        intent != expected
        or not isinstance(recorded, str)
        or not _matches(SUBMISSION_TOKEN_RE, token)
    ):
        raise LaunchAuditError("V6 launch intent changed")
    return raw, intent, diagnostic_sha, diagnostic


def _journal_job_ids(intent: dict, repair: list[int]) -> list[str]:
    name, comment = _submission_identity(intent["submission_token"])
    try:
        recorded = datetime.datetime.fromisoformat(intent["recorded_utc"])
    except (TypeError, ValueError) as err:
        raise LaunchAuditError("V6 submission timestamp is invalid") from err
    if recorded.tzinfo is None:
        raise LaunchAuditError("V6 submission timestamp has no timezone")
    output = _sacct([
        str(SACCT_COMMAND), "-X", "--array", "-S",
        recorded.date().isoformat(), "--name=" + name, "-n", "-P",
        "--format=JobID%64,JobName%128,Comment%128,SubmitLine%4096",
    ])
    parents = set()
    indices = {}
    expected_command = intent["submit_command"]
    for line in output.splitlines():
        fields = line.split("|", 3)
        if len(fields) != 4:
            raise LaunchAuditError("V6 submission journal row changed")
        job_id, actual_name, actual_comment, submit_line = fields
        if actual_name != name and actual_comment != comment:
            continue
        try:
            command = shlex.split(submit_line)
        except ValueError as err:
            raise LaunchAuditError("V6 SubmitLine cannot be parsed") from err
        if command and command[0] == SBATCH_COMMAND.name:
            command[0] = str(SBATCH_COMMAND)
        parent = re.fullmatch(r"([0-9]+)", job_id)
        child = re.fullmatch(r"([0-9]+)_([0-9]+)", job_id)
        if (
            actual_name != name
            or actual_comment not in ("", comment)
            or command != expected_command
            or (parent is None and child is None)
        ):
            raise LaunchAuditError("V6 submission identity collided")
        parent_id = (parent or child).group(1)
        parents.add(parent_id)
        if child is not None:
            indices.setdefault(parent_id, set()).add(int(child.group(2)))
    if len(parents) > 1:
        raise LaunchAuditError("journal identifies multiple V6 jobs")
    if len(parents) == 1:
        parent_id = next(iter(parents))
        if indices.get(parent_id, set()) != set(repair):
            raise LaunchAuditError("V6 submission journal array is incomplete")
    return sorted(parents, key=int)


def _load_launch() -> tuple[str, dict, dict]:
    intent_raw, intent, _diagnostic_sha, diagnostic = _load_intent_only()
    raw, receipt = _load_json(LAUNCH_RECEIPT, "V6 launch receipt")
    expected = {
        "schema": LAUNCH_SCHEMA,
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": receipt.get("job_id"),
    }
    if (
        receipt != expected
        or not isinstance(receipt.get("job_id"), str)
        or not receipt["job_id"].isdigit()
        or _journal_job_ids(intent, diagnostic["repair_v5_shard_indices"])
        != [receipt["job_id"]]
    ):
        raise LaunchAuditError("V6 launch receipt changed")
    return hashlib.sha256(raw).hexdigest(), receipt, diagnostic


def recover_launch() -> None:
    if LAUNCH_RECEIPT.exists():
        raise LaunchAuditError("V6 launch receipt already exists")
    raw, intent, _sha, diagnostic = _load_intent_only()
    jobs = _journal_job_ids(intent, diagnostic["repair_v5_shard_indices"])
    if len(jobs) != 1:
        raise LaunchAuditError(
            "journal identifies {} V6 jobs; refusing resubmission".format(
                len(jobs)
            )
        )
    digest = _write_launch_receipt(raw, intent, jobs[0])
    print(json.dumps({
        "job_id": jobs[0],
        "launch_receipt_reconstructed": True,
        "launch_receipt_sha256": digest,
    }, sort_keys=True, indent=2))


def _scheduler_rows(job_id: str, expected: list[int]) -> list[dict]:
    if (
        not isinstance(job_id, str)
        or not job_id.isdigit()
        or type(expected) is not list
        or not expected
        or expected != sorted(set(expected))
        or any(type(index) is not int or not 0 <= index < ARRAY_TASKS
               for index in expected)
    ):
        raise LaunchAuditError("V6 scheduler query is invalid")
    output = _sacct([
        str(SACCT_COMMAND), "-j", job_id, "-X", "--array", "-n", "-P",
        "--format=JobID,State,ExitCode,Elapsed,Partition",
    ])
    rows = []
    prefix = job_id + "_"
    lines = output.splitlines()
    if len(lines) != len(expected):
        raise LaunchAuditError("V6 accounting task cardinality changed")
    for expected_index, line in zip(expected, lines):
        fields = line.split("|")
        if len(fields) != 5:
            raise LaunchAuditError("V6 accounting row changed")
        task_id, state, exit_code, elapsed, partition = fields
        if task_id != "{}{}".format(prefix, expected_index):
            raise LaunchAuditError("V6 accounting identity changed")
        if (
            state not in ALLOWED_SCHEDULER_STATES
            or EXIT_CODE_RE.fullmatch(exit_code) is None
            or not _valid_elapsed(elapsed)
            or partition != PARTITION
        ):
            raise LaunchAuditError("V6 accounting field changed")
        rows.append({
            "array_task": expected_index,
            "state": state,
            "exit_code": exit_code,
            "elapsed": elapsed,
            "partition": partition,
        })
    _validate_sparse_rows(rows, expected, "V6")
    return rows


def status() -> tuple[str, dict, dict, list[dict]]:
    launch_sha, launch_receipt, diagnostic = _load_launch()
    rows = _scheduler_rows(
        launch_receipt["job_id"], diagnostic["repair_v5_shard_indices"]
    )
    print(json.dumps({
        "job_id": launch_receipt["job_id"],
        "state_counts": dict(Counter(row["state"] for row in rows)),
    }, sort_keys=True, indent=2))
    return launch_sha, launch_receipt, diagnostic, rows


def _scheduler_contract_rows(
    launch: dict, diagnostic: dict, rows: list[dict]
) -> list[dict]:
    output = _sacct([
        str(SACCT_COMMAND), "-j", launch["job_id"], "-X", "--array", "-n", "-P",
        "--format=JobID,Account,Partition,QOS,ReqCPUS,ReqMem,"
        "Timelimit,Elapsed,State,ExitCode,JobName",
    ])
    expected_indices = diagnostic["repair_v5_shard_indices"]
    expected_memory = diagnostic["resource_mapping"]["memory"]["requested"]
    expected_name, _ = _submission_identity(launch["submission_token"])
    prefix = launch["job_id"] + "_"
    _validate_sparse_rows(rows, expected_indices, "V6")
    by_index = {row["array_task"]: row for row in rows}
    lines = output.splitlines()
    if len(lines) != len(expected_indices):
        raise LaunchAuditError("V6 resource accounting cardinality changed")
    result = []
    for index, line in zip(expected_indices, lines):
        fields = line.split("|")
        if len(fields) != 11:
            raise LaunchAuditError("V6 resource accounting row changed")
        (task_id, account, partition, qos, cpus, memory, time_limit,
         elapsed, state, exit_code, job_name) = fields
        if (
            task_id != "{}{}".format(prefix, index)
            or account != ACCOUNT
            or partition != PARTITION
            or qos != QOS
            or cpus != "1"
            or memory != expected_memory
            or time_limit != diagnostic["resource_mapping"]["time_limit"]
            or not _valid_elapsed(elapsed)
            or state != "COMPLETED"
            or exit_code != "0:0"
            or job_name != expected_name
            or by_index.get(index, {}).get("state") != state
            or by_index.get(index, {}).get("exit_code") != exit_code
            or by_index.get(index, {}).get("elapsed") != elapsed
        ):
            raise LaunchAuditError("V6 actual resource contract changed")
        result.append({
            "array_task": index, "account": account, "partition": partition,
            "qos": qos, "req_cpus": 1, "req_mem": memory,
            "time_limit": time_limit, "elapsed": elapsed, "state": state,
            "exit_code": exit_code, "job_name": job_name,
        })
    return result


def _tree_digest(root: Path, tree, expected_root: dict) -> dict:
    info = tree.root_identity
    actual_root = {
        "path": str(root), "canonical_path": str(root),
        "device": info["device"], "inode": info["inode"],
        "mode": "0700", "uid": info["uid"],
    }
    if (
        not stat.S_ISDIR(info["mode"])
        or stat.S_IMODE(info["mode"]) != 0o700
        or actual_root != expected_root
    ):
        raise LaunchAuditError("V6 output root identity changed")
    records = [
        {"path": item.path, "bytes": item.identity["size"], "sha256": item.sha256}
        for item in tree.files
    ]
    digest = hashlib.sha256()
    digest.update(b"root-identity\0" + _canonical_json(actual_root))
    for item in records:
        digest.update(
            item["path"].encode("ascii") + b"\0"
            + bytes.fromhex(item["sha256"])
        )
    return {
        "sha256": digest.hexdigest(), "root_identity": actual_root,
        "files_count": len(records), "files": records,
    }


def _v6_output_tree(launch: dict, diagnostic: dict) -> dict:
    expected = {SOURCE_INVENTORY.name}
    for index in diagnostic["repair_v5_shard_indices"]:
        expected.update({
            Source.shard_path(OUTPUT_DIR, index).name,
            Source.task_environment_path(OUTPUT_DIR, index).name,
            "slurm-{}_{}.out".format(launch["job_id"], index),
        })
    tree = _safe_tree(OUTPUT_DIR, "V6 repair output tree")
    if tree.directories or {item.path for item in tree.files} != expected:
        raise LaunchAuditError("V6 repair output tree is incomplete or changed")
    return _tree_digest(
        OUTPUT_DIR, tree, launch["launch_root_identities"]["output_dir"]
    )


def _manifest_file_map(manifest: dict) -> dict[str, dict]:
    return {item["path"]: item for item in manifest["files"]}


def _validate_v5_reusable_triplets(
    diagnostic: dict,
) -> tuple[dict[int, list[dict]], dict]:
    """Parse reusable shards only after the repair campaign is terminal."""
    launch = diagnostic["v5_launch_receipt"]
    current = _opaque_v5_output_manifest(
        launch,
        diagnostic["reusable_v5_shard_indices"],
        diagnostic["repair_v5_shard_indices"],
    )
    if current != diagnostic["v5_output_manifest"]:
        raise LaunchAuditError("V5 output bytes changed after terminal diagnosis")
    try:
        code = V5Source.validate_code_manifest(
            V5_CODE_MANIFEST, launch["code_manifest_sha256"]
        )
        _inventory_sha, inventory = V5Source.load_inventory_manifest(
            V5_SOURCE_INVENTORY, launch["source_inventory_sha256"]
        )
    except V5Source.SourceAuditError as err:
        raise LaunchAuditError("V5 reusable provenance is invalid") from err
    tasks_by_shard = {}
    environment_records = []
    file_map = _manifest_file_map(current)
    for index in diagnostic["reusable_v5_shard_indices"]:
        start = index * Source.TASKS_PER_SHARD
        shard = V5Source.shard_path(V5_OUTPUT_DIR, index)
        environment = V5Source.task_environment_path(V5_OUTPUT_DIR, index)
        try:
            tasks = V5Source._load_shard(
                shard, index,
                inventory[start:start + Source.TASKS_PER_SHARD],
                launch["source_inventory_sha256"], code,
            )
            value = V5Source.load_task_environment_attestation(
                environment,
                index=index,
                array_job_id=launch["job_id"],
                inventory_sha256=launch["source_inventory_sha256"],
                code_manifest_sha256=launch["code_manifest_sha256"],
                code=code,
                shard_sha256=file_map[shard.name]["sha256"],
            )
            if (
                value["output_dir_identity_after"]
                != launch["launch_root_identities"]["output_dir"]
                or value["tmpdir_root_identity_after"]
                != launch["launch_root_identities"]["tmpdir_root"]
            ):
                raise V5Source.SourceAuditError(
                    "V5 reusable task roots differ from launch"
                )
        except (V5Source.SourceAuditError, KeyError) as err:
            raise LaunchAuditError(
                "scheduler-completed V5 task {} has an invalid reusable triplet"
                .format(index)
            ) from err
        tasks_by_shard[index] = tasks
        environment_records.append({
            "array_task": index,
            "environment_path": environment.name,
            "environment_sha256": file_map[environment.name]["sha256"],
            "shard_path": shard.name,
            "shard_sha256": file_map[shard.name]["sha256"],
            "slurm_log_path": "slurm-{}_{}.out".format(launch["job_id"], index),
            "slurm_log_sha256": file_map[
                "slurm-{}_{}.out".format(launch["job_id"], index)
            ]["sha256"],
            "tmpdir": value["tmpdir"],
            "output_dir_identity": value["output_dir_identity_after"],
        })
    return tasks_by_shard, {
        "records": environment_records,
        "records_sha256": hashlib.sha256(
            _canonical_json(environment_records)
        ).hexdigest(),
        "strict_completed_triplet_validation": True,
    }


def _validate_v6_repair_shards(
    launch: dict, diagnostic: dict, output_tree: dict,
) -> tuple[dict[int, list[dict]], dict]:
    timeout = diagnostic["resource_mapping"]["task_timeout_seconds"]
    Source.configure(timeout)
    try:
        code = Source.validate_code_manifest(
            CODE_MANIFEST, launch["code_manifest_sha256"]
        )
        _inventory_sha, inventory = Source.load_inventory_manifest(
            SOURCE_INVENTORY, launch["source_inventory_sha256"]
        )
    except Source.SourceAuditError as err:
        raise LaunchAuditError("V6 repair provenance is invalid") from err
    files = _manifest_file_map(output_tree)
    tasks_by_shard = {}
    environments = []
    for index in diagnostic["repair_v5_shard_indices"]:
        start = index * Source.TASKS_PER_SHARD
        shard = Source.shard_path(OUTPUT_DIR, index)
        environment = Source.task_environment_path(OUTPUT_DIR, index)
        try:
            tasks = Source._load_shard(
                shard, index,
                inventory[start:start + Source.TASKS_PER_SHARD],
                launch["source_inventory_sha256"], code,
            )
            value = Source.load_task_environment_attestation(
                environment,
                index=index,
                array_job_id=launch["job_id"],
                inventory_sha256=launch["source_inventory_sha256"],
                code_manifest_sha256=launch["code_manifest_sha256"],
                code=code,
                shard_sha256=files[shard.name]["sha256"],
            )
            if (
                value["output_dir_identity_after"]
                != launch["launch_root_identities"]["output_dir"]
                or value["tmpdir_root_identity_after"]
                != launch["launch_root_identities"]["tmpdir_root"]
            ):
                raise Source.SourceAuditError(
                    "V6 repair task roots differ from launch"
                )
        except (Source.SourceAuditError, KeyError) as err:
            raise LaunchAuditError(
                "V6 repair task {} is invalid".format(index)
            ) from err
        tasks_by_shard[index] = tasks
        log_name = "slurm-{}_{}.out".format(launch["job_id"], index)
        environments.append({
            "array_task": index,
            "environment_path": environment.name,
            "environment_sha256": files[environment.name]["sha256"],
            "shard_path": shard.name,
            "shard_sha256": files[shard.name]["sha256"],
            "slurm_log_path": log_name,
            "slurm_log_sha256": files[log_name]["sha256"],
            "tmpdir": value["tmpdir"],
            "output_dir_identity": value["output_dir_identity_after"],
        })
    if _root_identity(TMP_ROOT, "V6 TMPDIR root", require_empty=True) != (
        launch["launch_root_identities"]["tmpdir_root"]
    ):
        raise LaunchAuditError("V6 TMPDIR root changed")
    return tasks_by_shard, {
        "records": environments,
        "records_sha256": hashlib.sha256(
            _canonical_json(environments)
        ).hexdigest(),
        "all_repair_tmpdirs_removed_by_rmdir": True,
    }


def _publish_or_validate_json(path: Path, expected: dict, label: str) -> str:
    if os.path.lexists(path):
        raw, value = _load_json(path, label)
        if value != expected:
            raise LaunchAuditError("{} changed".format(label))
        return hashlib.sha256(raw).hexdigest()
    return _exclusive_json(path, expected, label)


def _publish_or_validate_bytes(path: Path, raw: bytes, label: str) -> str:
    expected_sha = hashlib.sha256(raw).hexdigest()
    if os.path.lexists(path):
        loaded = _safe_file(path, label)
        if loaded.sha256 != expected_sha or loaded.raw != raw:
            raise LaunchAuditError("{} changed".format(label))
        return loaded.sha256
    return _exclusive_bytes(path, raw, label)


def _expected_union_names() -> list[str]:
    return [
        Source.shard_path(UNION_DIR, index).name
        for index in range(ARRAY_TASKS)
    ]


def _union_tree(expected_root: dict, *, complete: bool) -> dict:
    tree = _safe_tree(UNION_DIR, "V6 union tree")
    actual = [item.path for item in tree.files]
    expected = _expected_union_names()
    if (
        tree.directories
        or actual != sorted(actual)
        or (actual != expected if complete else not set(actual) <= set(expected))
    ):
        raise LaunchAuditError("V6 union topology changed")
    return _tree_digest(UNION_DIR, tree, expected_root)


def _ensure_union_root(plan_sha256: str, *, recovery: bool) -> tuple[str, dict]:
    if os.path.lexists(UNION_ROOT_STAGE):
        raw, stage = _load_json(UNION_ROOT_STAGE, "V6 union-root stage")
        if (
            set(stage) != {"schema", "seal_plan_sha256", "root_identity"}
            or stage.get("schema") != UNION_ROOT_STAGE_SCHEMA
            or stage.get("seal_plan_sha256") != plan_sha256
            or _root_identity(UNION_DIR, "V6 union directory")
            != stage.get("root_identity")
        ):
            raise LaunchAuditError("V6 union-root stage changed")
        _union_tree(stage["root_identity"], complete=False)
        return hashlib.sha256(raw).hexdigest(), stage
    if os.path.lexists(UNION_DIR):
        if not recovery:
            raise LaunchAuditError("V6 union directory predates its stage")
        identity = _root_identity(
            UNION_DIR, "V6 interrupted union directory", require_empty=True
        )
    else:
        identity = _create_private_directory(UNION_DIR, "V6 union directory")
    stage = {
        "schema": UNION_ROOT_STAGE_SCHEMA,
        "seal_plan_sha256": plan_sha256,
        "root_identity": identity,
    }
    return (
        _publish_or_validate_json(
            UNION_ROOT_STAGE, stage, "V6 union-root stage"
        ),
        stage,
    )


def _copy_or_validate_union_shard(
    source: Path, target: Path, frozen: dict
) -> str:
    loaded = _safe_file(source, "V6 union source shard")
    if (
        loaded.sha256 != frozen.get("sha256")
        or loaded.identity["size"] != frozen.get("bytes")
    ):
        raise LaunchAuditError("V6 union origin differs from frozen tree")
    if os.path.lexists(target):
        target_loaded = _safe_file(target, "V6 interrupted union shard")
        if (
            target_loaded.sha256 != loaded.sha256
            or target_loaded.identity["size"] != loaded.identity["size"]
        ):
            raise LaunchAuditError("V6 interrupted union shard changed")
        return target_loaded.sha256
    digest = _exclusive_bytes(target, loaded.raw, "V6 union shard")
    target_loaded = _safe_file(target, "V6 published union shard")
    if (
        digest != loaded.sha256
        or target_loaded.sha256 != loaded.sha256
        or target_loaded.identity["size"] != loaded.identity["size"]
    ):
        raise LaunchAuditError("V6 union copy changed")
    return digest


def _prepare_union(
    diagnostic: dict,
    v6_output_tree: dict,
    plan_sha256: str,
    *,
    recovery: bool,
) -> tuple[str, dict]:
    root_stage_sha, root_stage = _ensure_union_root(
        plan_sha256, recovery=recovery
    )
    partial = _union_tree(root_stage["root_identity"], complete=False)
    partial_names = {item["path"] for item in partial["files"]}
    expected_names = set(_expected_union_names())
    if not partial_names <= expected_names:
        raise LaunchAuditError("V6 union contains an unexpected partial shard")
    v5_files = _manifest_file_map(diagnostic["v5_output_manifest"])
    v6_files = _manifest_file_map(v6_output_tree)
    reusable = set(diagnostic["reusable_v5_shard_indices"])
    sources = []
    for index in range(ARRAY_TASKS):
        if index in reusable:
            source = V5Source.shard_path(V5_OUTPUT_DIR, index)
            origin = "v5-completed"
            frozen = v5_files.get(source.name)
        else:
            source = Source.shard_path(OUTPUT_DIR, index)
            origin = "v6-repair"
            frozen = v6_files.get(source.name)
        if frozen is None:
            raise LaunchAuditError("V6 union source is absent from frozen tree")
        target = Source.shard_path(UNION_DIR, index)
        target_sha = _copy_or_validate_union_shard(source, target, frozen)
        sources.append({
            "shard_index": index,
            "origin": origin,
            "source": str(source),
            "source_sha256": frozen["sha256"],
            "union": target.name,
            "union_sha256": target_sha,
        })
    union_tree = _union_tree(root_stage["root_identity"], complete=True)
    stage = {
        "schema": UNION_STAGE_SCHEMA,
        "seal_plan_sha256": plan_sha256,
        "union_root_stage_sha256": root_stage_sha,
        "sources": sources,
        "sources_sha256": hashlib.sha256(
            _canonical_json(sources)
        ).hexdigest(),
        "tree": union_tree,
    }
    stage_sha = _publish_or_validate_json(
        UNION_STAGE, stage, "V6 union stage"
    )
    return stage_sha, stage


def _expected_candidate_from_union(diagnostic: dict) -> tuple[bytes, dict]:
    """Parse the verified union and capture deterministic assembly in memory."""
    reusable = set(diagnostic["reusable_v5_shard_indices"])
    v5_launch = diagnostic["v5_launch_receipt"]
    Source.configure(diagnostic["resource_mapping"]["task_timeout_seconds"])
    v5_code = V5Source.validate_code_manifest(
        V5_CODE_MANIFEST, v5_launch["code_manifest_sha256"]
    )
    v6_manifest_sha = _sha256(CODE_MANIFEST)
    v6_code = Source.validate_code_manifest(CODE_MANIFEST, v6_manifest_sha)
    original_loader = Source.Base._load_shard
    original_atomic_json = Source.Base._atomic_json
    captured = []

    def dispatch(path, index, expected, inventory_sha, _code):
        if index in reusable:
            return V5Source._load_shard(
                path, index, expected, inventory_sha, v5_code
            )
        return Source._load_shard(
            path, index, expected, inventory_sha, v6_code
        )

    def capture(path, value):
        if Path(path) != CANDIDATE or captured:
            raise LaunchAuditError("V6 candidate capture contract changed")
        raw = _canonical_json(value)
        captured.append((raw, value))
        return hashlib.sha256(raw).hexdigest()

    Source.Base._load_shard = dispatch
    Source.Base._atomic_json = capture
    try:
        Source.Base.assemble(SimpleNamespace(
            shard_dir=UNION_DIR,
            inventory_manifest=Source._LexicallyValidatedPath(SOURCE_INVENTORY),
            inventory_sha256=v5_launch["source_inventory_sha256"],
            num_shards=ARRAY_TASKS,
            code_manifest=Source._LexicallyValidatedPath(CODE_MANIFEST),
            code_manifest_sha256=v6_manifest_sha,
            output=CANDIDATE,
        ))
    finally:
        Source.Base._load_shard = original_loader
        Source.Base._atomic_json = original_atomic_json
    if len(captured) != 1:
        raise LaunchAuditError("V6 candidate assembly did not publish once")
    raw, candidate = captured[0]
    if (
        candidate.get("schema") != Source.Base.SCHEMA
        or candidate.get("source_inventory_sha256")
        != v5_launch["source_inventory_sha256"]
        or candidate.get("code_manifest_sha256") != v6_manifest_sha
        or candidate.get("counts", {}).get("candidates")
        != Source.CANDIDATE_COUNT
        or candidate.get("counts", {}).get("translation_attempts")
        != Source.CANDIDATE_COUNT
        or candidate.get("confirmation_prelaunch_authorized")
        is not candidate.get("prelaunch_gate", {}).get("passed")
    ):
        raise LaunchAuditError("V6 candidate attestation changed")
    return raw, candidate


def _prepare_candidate(
    diagnostic: dict,
    union_stage_sha256: str,
    expected_records_sha256: str,
) -> tuple[str, dict, bytes, dict]:
    raw, candidate = _expected_candidate_from_union(diagnostic)
    if candidate.get("records_sha256") != expected_records_sha256:
        raise LaunchAuditError(
            "V6 union parse differs from the frozen source sequence"
        )
    candidate_sha = _publish_or_validate_bytes(
        CANDIDATE, raw, "V6 candidate attestation"
    )
    stage = {
        "schema": CANDIDATE_STAGE_SCHEMA,
        "union_stage_sha256": union_stage_sha256,
        "candidate_path": str(CANDIDATE),
        "candidate_bytes": len(raw),
        "candidate_sha256": candidate_sha,
        "records_sha256": candidate["records_sha256"],
    }
    stage_sha = _publish_or_validate_json(
        CANDIDATE_STAGE, stage, "V6 candidate stage"
    )
    return stage_sha, stage, raw, candidate


def _source_record_sequence_sha256(
    diagnostic: dict, v5_tasks: dict, v6_tasks: dict
) -> str:
    reusable = set(diagnostic["reusable_v5_shard_indices"])
    records = []
    for index in range(ARRAY_TASKS):
        records.extend((v5_tasks if index in reusable else v6_tasks)[index])
    if (
        len(records) != Source.CANDIDATE_COUNT
        or [record.get("candidate_index") for record in records]
        != list(range(Source.CANDIDATE_COUNT))
    ):
        raise LaunchAuditError("V6 assembled source population changed")
    return hashlib.sha256(_canonical_json(records)).hexdigest()


def _seal_context() -> dict:
    launch_sha, launch_receipt, diagnostic, rows = status()
    if any(
        row["state"] != "COMPLETED" or row["exit_code"] != "0:0"
        for row in rows
    ):
        raise LaunchAuditError("V6 repair array is not entirely successful")
    contract = _scheduler_contract_rows(
        launch_receipt, diagnostic, rows
    )
    output_before = _v6_output_tree(launch_receipt, diagnostic)
    v5_tasks, v5_environments = _validate_v5_reusable_triplets(diagnostic)
    v6_tasks, v6_environments = _validate_v6_repair_shards(
        launch_receipt, diagnostic, output_before
    )
    record_sequence_sha = _source_record_sequence_sha256(
        diagnostic, v5_tasks, v6_tasks
    )
    plan = {
        "schema": SEAL_PLAN_SCHEMA,
        "launch_receipt_sha256": launch_sha,
        "v5_terminal_diagnostic_sha256": launch_receipt[
            "v5_terminal_diagnostic_sha256"
        ],
        "pre_diagnosis_files_sha256": diagnostic[
            "pre_diagnosis_freeze"
        ]["files_sha256"],
        "scheduler_rows": rows,
        "scheduler_contract_rows": contract,
        "v5_output_tree_sha256": diagnostic["v5_output_manifest"]["sha256"],
        "v6_output_tree": output_before,
        "v5_reusable_environment_manifest": v5_environments,
        "v6_repair_environment_manifest": v6_environments,
        "source_record_count": Source.CANDIDATE_COUNT,
        "source_record_sequence_sha256": record_sequence_sha,
    }
    return {
        "launch_sha": launch_sha,
        "launch": launch_receipt,
        "diagnostic": diagnostic,
        "rows": rows,
        "contract": contract,
        "v6_output_tree": output_before,
        "v5_environments": v5_environments,
        "v6_environments": v6_environments,
        "plan": plan,
    }


def _attestation_stage(
    candidate_stage_sha256: str, candidate_raw: bytes
) -> tuple[str, dict, str]:
    attestation_sha = _publish_or_validate_bytes(
        ATTESTATION, candidate_raw, "frozen V6 source attestation"
    )
    stage = {
        "schema": ATTESTATION_STAGE_SCHEMA,
        "candidate_stage_sha256": candidate_stage_sha256,
        "attestation_path": str(ATTESTATION),
        "attestation_bytes": len(candidate_raw),
        "attestation_sha256": attestation_sha,
    }
    stage_sha = _publish_or_validate_json(
        ATTESTATION_STAGE, stage, "V6 attestation stage"
    )
    return stage_sha, stage, attestation_sha


def _final_tree_rehash(
    context: dict, union_root_stage: dict, union_stage: dict
) -> None:
    diagnostic = context["diagnostic"]
    current_v5 = _opaque_v5_output_manifest(
        diagnostic["v5_launch_receipt"],
        diagnostic["reusable_v5_shard_indices"],
        diagnostic["repair_v5_shard_indices"],
    )
    if current_v5 != diagnostic["v5_output_manifest"]:
        raise LaunchAuditError("V5 output changed before V6 receipt")
    _validate_failure_logs_against_tree(
        diagnostic["failure_records"], current_v5
    )
    if _v6_output_tree(context["launch"], diagnostic) != context[
        "v6_output_tree"
    ]:
        raise LaunchAuditError("V6 repair output changed before receipt")
    if _union_tree(
        union_root_stage["root_identity"], complete=True
    ) != union_stage["tree"]:
        raise LaunchAuditError("V6 union changed before receipt")


def _execution_receipt(
    context: dict,
    *,
    plan_sha256: str,
    union_root_stage_sha256: str,
    union_stage_sha256: str,
    union_stage: dict,
    candidate_stage_sha256: str,
    attestation_stage_sha256: str,
    attestation_sha256: str,
    value: dict,
) -> dict:
    launch_receipt = context["launch"]
    diagnostic = context["diagnostic"]
    rows = context["rows"]
    receipt = {
        "schema": EXECUTION_SCHEMA,
        "campaign": "v6-selective-repair",
        "benchmark_revision": launch_receipt["benchmark_revision"],
        "logical_shards": ARRAY_TASKS,
        "candidates": Source.CANDIDATE_COUNT,
        "whole_campaign_rerun": False,
        "outcome_blind_selective_repair": True,
        "noncompleted_v5_shards_used": False,
        "reuse_eligibility_rule": diagnostic["reuse_eligibility_rule"],
        "pre_diagnosis_freeze": diagnostic["pre_diagnosis_freeze"],
        "seal_recovery_protocol": "deterministic-exclusive-hash-chain-v1",
        "seal_plan_sha256": plan_sha256,
        "union_root_stage_sha256": union_root_stage_sha256,
        "union_stage_sha256": union_stage_sha256,
        "candidate_stage_sha256": candidate_stage_sha256,
        "attestation_stage_sha256": attestation_stage_sha256,
        "launch_receipt_sha256": context["launch_sha"],
        "v5_terminal_diagnostic_sha256": launch_receipt[
            "v5_terminal_diagnostic_sha256"
        ],
        "v5_launch_receipt_sha256": diagnostic["v5_launch_receipt_sha256"],
        "v5_job_id": diagnostic["v5_launch_receipt"]["job_id"],
        "v6_job_id": launch_receipt["job_id"],
        "reused_v1_shards": 0,
        "reused_v2_shards": 0,
        "reused_v3_shards": 0,
        "reused_v4_shards": 0,
        "reused_v5_shards": len(diagnostic["reusable_v5_shard_indices"]),
        "reusable_v5_shard_indices": diagnostic[
            "reusable_v5_shard_indices"
        ],
        "repaired_v5_shards": len(diagnostic["repair_v5_shard_indices"]),
        "repair_v5_shard_indices": diagnostic["repair_v5_shard_indices"],
        "repair_scope": "complete original two-candidate shards",
        "array_throttle": 0,
        "resource_mapping": diagnostic["resource_mapping"],
        "scheduler_state_counts": {"COMPLETED": len(rows)},
        "scheduler_rows": rows,
        "scheduler_contract_rows": context["contract"],
        "v5_output_manifest": diagnostic["v5_output_manifest"],
        "v6_output_tree": context["v6_output_tree"],
        "v5_reusable_environment_manifest": context["v5_environments"],
        "v6_repair_environment_manifest": context["v6_environments"],
        "union_sources": union_stage["sources"],
        "union_sources_sha256": union_stage["sources_sha256"],
        "union_tree": union_stage["tree"],
        "source_inventory_sha256": launch_receipt["source_inventory_sha256"],
        "v5_code_manifest_sha256": diagnostic["v5_code_manifest_sha256"],
        "v6_code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "execution_environment": launch_receipt["execution_environment"],
        "source_audit_complete": True,
        "confirmation_prelaunch_authorized": value[
            "confirmation_prelaunch_authorized"
        ],
        "prelaunch_gate": value["prelaunch_gate"],
        "attestation_sha256": attestation_sha,
        "attestation_records_sha256": value["records_sha256"],
        "cohort_manifest_sha256": {
            name: cohort["tasks_sha256"]
            for name, cohort in value["cohorts"].items()
        },
        "counts": value["counts"],
        "translation_status_counts": value["translation_status_counts"],
        "support_exclusion_counts": value["support_exclusion_counts"],
    }
    return receipt


def _run_seal(*, recovery: bool) -> None:
    context = _seal_context()
    plan_sha = _publish_or_validate_json(
        SEAL_PLAN, context["plan"], "V6 seal plan"
    )
    union_stage_sha, union_stage = _prepare_union(
        context["diagnostic"], context["v6_output_tree"], plan_sha,
        recovery=recovery,
    )
    union_root_raw, union_root_stage = _load_json(
        UNION_ROOT_STAGE, "V6 union-root stage"
    )
    union_root_sha = hashlib.sha256(union_root_raw).hexdigest()
    if union_root_sha != union_stage["union_root_stage_sha256"]:
        raise LaunchAuditError("V6 union stage chain changed")
    candidate_stage_sha, candidate_stage, candidate_raw, value = (
        _prepare_candidate(
            context["diagnostic"], union_stage_sha,
            context["plan"]["source_record_sequence_sha256"],
        )
    )
    attestation_stage_sha, attestation_stage_value, attestation_sha = (
        _attestation_stage(candidate_stage_sha, candidate_raw)
    )
    receipt = _execution_receipt(
        context,
        plan_sha256=plan_sha,
        union_root_stage_sha256=union_root_sha,
        union_stage_sha256=union_stage_sha,
        union_stage=union_stage,
        candidate_stage_sha256=candidate_stage_sha,
        attestation_stage_sha256=attestation_stage_sha,
        attestation_sha256=attestation_sha,
        value=value,
    )
    if _publish_or_validate_bytes(
        CANDIDATE, candidate_raw, "V6 candidate before receipt"
    ) != candidate_stage["candidate_sha256"]:
        raise LaunchAuditError("V6 candidate changed before receipt")
    if _publish_or_validate_bytes(
        ATTESTATION, candidate_raw, "V6 attestation before receipt"
    ) != attestation_sha:
        raise LaunchAuditError("V6 attestation changed before receipt")
    if (
        _publish_or_validate_json(
            SEAL_PLAN, context["plan"], "V6 seal plan before receipt"
        ) != plan_sha
        or _publish_or_validate_json(
            UNION_ROOT_STAGE, union_root_stage,
            "V6 union-root stage before receipt",
        ) != union_root_sha
        or _publish_or_validate_json(
            UNION_STAGE, union_stage, "V6 union stage before receipt"
        ) != union_stage_sha
        or _publish_or_validate_json(
            CANDIDATE_STAGE, candidate_stage,
            "V6 candidate stage before receipt",
        ) != candidate_stage_sha
        or _publish_or_validate_json(
            ATTESTATION_STAGE, attestation_stage_value,
            "V6 attestation stage before receipt",
        ) != attestation_stage_sha
    ):
        raise LaunchAuditError("V6 seal-stage hash chain changed")
    _final_tree_rehash(context, union_root_stage, union_stage)
    digest = _publish_or_validate_json(
        EXECUTION_RECEIPT, receipt, "V6 execution receipt"
    )
    print(json.dumps({
        "attestation_sha256": attestation_sha,
        "confirmation_prelaunch_authorized": value[
            "confirmation_prelaunch_authorized"
        ],
        "execution_receipt_sha256": digest,
        "union_tree_sha256": union_stage["tree"]["sha256"],
    }, sort_keys=True, indent=2))


def seal() -> None:
    partials = (
        EXECUTION_RECEIPT, UNION_DIR, CANDIDATE, ATTESTATION,
        *SEAL_STAGE_ARTIFACTS,
    )
    if any(os.path.lexists(path) for path in partials):
        raise LaunchAuditError(
            "V6 seal state exists; use recover-seal after an interruption"
        )
    _run_seal(recovery=False)


def recover_seal() -> None:
    partials = (
        EXECUTION_RECEIPT, UNION_DIR, CANDIDATE, ATTESTATION,
        *SEAL_STAGE_ARTIFACTS,
    )
    if not any(os.path.lexists(path) for path in partials):
        raise LaunchAuditError("V6 has no interrupted seal state")
    _run_seal(recovery=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "diagnose-v5", "prepare-manifest", "launch", "recover-launch",
        "status", "seal", "recover-seal",
    ))
    args = parser.parse_args(argv)
    {
        "diagnose-v5": diagnose_v5,
        "prepare-manifest": prepare_manifest,
        "launch": launch,
        "recover-launch": recover_launch,
        "status": status,
        "seal": seal,
        "recover-seal": recover_seal,
    }[args.command]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        LaunchAuditError, Source.SourceAuditError,
        V5Source.SourceAuditError, Inventory.InventoryError,
    ) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
