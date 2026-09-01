#!/usr/bin/env python3
"""Launch, monitor, and seal independent full source-audit campaign v3."""

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


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources_v3 as Source
import pdb_terminal_incidence_confirmation_inventory as Inventory


_BASE_NAME = "_pdb_terminal_incidence_confirmation_source_launch_v3_base"
_BASE_PATH = (
    SCRIPT_DIR / "launch_pdb_terminal_incidence_confirmation_source_audit.py"
)
_spec = importlib.util.spec_from_file_location(_BASE_NAME, _BASE_PATH)
if _spec is None or _spec.loader is None:
    raise RuntimeError("cannot load frozen source-audit launcher")
Base = importlib.util.module_from_spec(_spec)
sys.modules[_BASE_NAME] = Base
_spec.loader.exec_module(Base)


SLURM_SCRIPT = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v3.slurm"
)
CODE_MANIFEST = Source.DEFAULT_CODE_MANIFEST
OUTPUT_DIR = Source.DEFAULT_SHARDS
SOURCE_INVENTORY = Source.DEFAULT_INVENTORY
CANDIDATE = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v3_candidate.json"
)
ATTESTATION = Source.DEFAULT_OUTPUT
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v3"
)
INTENT = ARTIFACT_DIR / "source-audit-launch-intent-v3.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-launch-receipt-v3.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v3.json"
RECOVERY_ARTIFACT_ROOT = ARTIFACT_DIR / "recovery"
RECOVERY_DATA_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_recovery_v3"
)
UNION_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_union_v3"
)
LAUNCH_SCHEMA = Source.SCHEMA + "/campaign-v3/launch"
EXECUTION_SCHEMA = Source.SCHEMA + "/campaign-v3/execution"
ARRAY_TASKS = Source.SHARD_COUNT
ACCOUNT = "naiss2025-5-561-cpu"
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
SUBMISSION_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
}
SHA256SUM_COMMAND = Path("/usr/bin/sha256sum")
JJ_COMMAND = Path("/home/jendrik/bin/jj")
JJ_EXECUTABLE_SHA256 = (
    "d1d69a0f87df266eebf0d2592dd019eb288c300b15fd019afe26cb1ed11ba152"
)
MEMORY_PER_CPU = "512G"
TIME_LIMIT = "04:10:00"
JOB_NAME_PREFIX = "confirmation-source-audit-v3"
COMMENT_PREFIX = "confirmation-source-audit-v3"

V1_LAUNCH_RECEIPT = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation" /
    "source-audit-launch-receipt-v1.json"
)
V1_LAUNCH_RECEIPT_SHA256 = (
    "3c7b830c181faa21a8f95c648dd15103dfdd6cf69111b07cc7eb01aa1b2817e2"
)
V1_JOB_ID = "1860905"
V1_MEMORY_PER_CPU = "26G"
V1_SOURCE_INVENTORY_SHA256 = (
    "bb9be49a4652ff7bedcadb04b4db35cad701a5b2a2a6d6347c15e0ad670e056e"
)
V1_CODE_MANIFEST_SHA256 = (
    "281aab0344095d7d81f74349916d616bb3cee730e5be095822ed37574ea258a3"
)
V1_SLURM_SCRIPT_SHA256 = (
    "82be051851dca4951ec5df0f43b8938ce9bd15a25a65bf2660cfc1eedaac5557"
)
V1_CANDIDATE = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v1_candidate.json"
)
V1_ATTESTATION = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v1.json"
)
V1_EXECUTION_RECEIPT = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation" /
    "source-audit-execution-receipt-v1.json"
)
V1_TERMINAL_STATES = frozenset({
    "BOOT_FAIL", "CANCELLED", "COMPLETED", "DEADLINE", "FAILED",
    "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "REVOKED", "TIMEOUT",
})

V2_LAUNCH_RECEIPT = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v2" /
    "source-audit-launch-receipt-v2.json"
)
V2_LAUNCH_RECEIPT_SHA256 = (
    "f69e9d4fe8448a2af5d71109d2f058335c346ab755a7970b66f4775a185b2373"
)
V2_JOB_ID = "1861842"
V2_MEMORY_PER_CPU = "256G"
V2_TASK_TIMEOUT_SECONDS = 2700
V2_TIME_LIMIT = "01:40:00"
V2_SOURCE_INVENTORY_SHA256 = (
    "bb9be49a4652ff7bedcadb04b4db35cad701a5b2a2a6d6347c15e0ad670e056e"
)
V2_CODE_MANIFEST_SHA256 = (
    "ed21cc76d7388f89b9ef9a5fc7e6855ba657a36909efd00c1aedf5df1908eb3c"
)
V2_SLURM_SCRIPT_SHA256 = (
    "9c2cd7b7dd6448f41b776921a03df5959cd81f0a0272f076a127e265edb3690a"
)
V2_SCHEDULER_STATE_COUNTS = {
    "COMPLETED": 793,
    "FAILED": 23,
    "OUT_OF_MEMORY": 4,
}
V2_SCHEDULER_ROWS_SHA256 = (
    "2b111f8cab6acd395cee1e63b159671b1cfc4682c48b40846cf7439df2ee8e13"
)
V2_FAILURE_LOGS_SHA256 = (
    "d60542cef3c0d04b860f8a5f59fd6a2bdab50f7f56e6c175d84f3ac47b53fe47"
)
V2_CANDIDATE = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v2_candidate.json"
)
V2_ATTESTATION = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v2.json"
)
V2_EXECUTION_RECEIPT = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v2" /
    "source-audit-execution-receipt-v2.json"
)
V2_OUTPUT_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v2"
)

SCOPED_COMMIT_FILES = tuple(sorted({
    *Source.CODE_MANIFEST_FILES,
    SLURM_SCRIPT.relative_to(REPO).as_posix(),
    CODE_MANIFEST.relative_to(REPO).as_posix(),
}))


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
    setattr(Base, _name, _value)


class LaunchAuditError(Base.LaunchAuditError):
    pass


def _slurm_preflight() -> tuple[str, str, dict]:
    if SLURM_SCRIPT.is_symlink() or not SLURM_SCRIPT.is_file():
        raise LaunchAuditError("source-audit v3 Slurm script is not regular")
    try:
        lines = SLURM_SCRIPT.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as err:
        raise LaunchAuditError("cannot read source-audit v3 Slurm script") from err
    ordered_header = [
        "#!/bin/bash",
        "#SBATCH --job-name=confirmation-source-audit-v3",
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
    ):
        raise LaunchAuditError("source-audit v3 Slurm header order changed")
    required = {
        "#SBATCH --job-name=confirmation-source-audit-v3",
        "#SBATCH --account={}".format(ACCOUNT),
        "#SBATCH --partition=fat",
        "#SBATCH --qos=normal",
        "#SBATCH --array=0-819",
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --mem-per-cpu={}".format(MEMORY_PER_CPU),
        "#SBATCH --time={}".format(TIME_LIMIT),
        "#SBATCH --output={}/slurm-%A_%a.out".format(OUTPUT_DIR),
        "#SBATCH --export=NONE",
    }
    if not required <= set(lines):
        raise LaunchAuditError("source-audit v3 Slurm header changed")
    prefixes = (
        "#SBATCH --job-name=", "#SBATCH --account=",
        "#SBATCH --partition=", "#SBATCH --qos=", "#SBATCH --array=",
        "#SBATCH --cpus-per-task=", "#SBATCH --mem-per-cpu=",
        "#SBATCH --time=", "#SBATCH --output=", "#SBATCH --export=",
    )
    if any(
        sum(line.startswith(prefix) for line in lines) != 1
        for prefix in prefixes
    ):
        raise LaunchAuditError("source-audit v3 Slurm directives conflict")
    array_line = next(line for line in lines if line.startswith("#SBATCH --array="))
    if "%" in array_line or any("--nice" in line for line in lines):
        raise LaunchAuditError("source-audit v3 submission is throttled")
    assignments = [
        Base.MANIFEST_ASSIGNMENT_RE.fullmatch(line)
        for line in lines
        if line.startswith("code_manifest_sha256=")
    ]
    if len(assignments) != 1 or assignments[0] is None:
        raise LaunchAuditError("source-audit v3 code manifest is not pinned")
    manifest_sha = assignments[0].group(1)
    code = Source.validate_code_manifest(CODE_MANIFEST, manifest_sha)
    environment = Base._execution_environment(code)
    expected_lines = ordered_header + [
        "",
        'test "$#" -eq 2',
        'source_inventory_sha256="$1"',
        'source_audit_output_dir="$2"',
        '[[ "${source_inventory_sha256}" =~ ^[0-9a-f]{64}$ ]]',
        '[[ "${source_audit_output_dir}" = /* ]]',
        "",
        "unset {}".format(" ".join(UNSET_PYTHON_ENV)),
        'export PYTHONNOUSERSITE="1"',
        'export PYTHONDONTWRITEBYTECODE="1"',
        'export PYTHONPYCACHEPREFIX="/tmp/'
        'symk-confirmation-source-audit-v3-'
        '${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"',
        'export PATH="{}"'.format(CONTROLLED_PATH),
        "",
        "cd {}".format(REPO),
        'code_manifest="experiments/'
        'pdb_terminal_incidence_confirmation_source_audit_v3_code.sha256"',
        'code_manifest_sha256="{}"'.format(manifest_sha),
        'source_inventory="experiments/data/'
        'pdb_terminal_incidence_confirmation_source_audit_v3/'
        'source-inventory-v3.json"',
        'python_executable="{}"'.format(PYTHON_COMMAND),
        'python_executable_sha256="{}"'.format(
            environment["python_executable_sha256"]
        ),
        'sha256sum_executable="{}"'.format(SHA256SUM_COMMAND),
        'sha256sum_executable_sha256="{}"'.format(
            environment["sha256sum_executable_sha256"]
        ),
        "",
        'actual_sha256sum="$("${sha256sum_executable}" '
        '"${sha256sum_executable}")"',
        'test "${actual_sha256sum%% *}" = '
        '"${sha256sum_executable_sha256}"',
        'actual_python="$("${sha256sum_executable}" '
        '"${python_executable}")"',
        'test "${actual_python%% *}" = "${python_executable_sha256}"',
        'actual_manifest="$("${sha256sum_executable}" '
        '"${code_manifest}")"',
        'test "${actual_manifest%% *}" = "${code_manifest_sha256}"',
        'actual_inventory="$("${sha256sum_executable}" '
        '"${source_inventory}")"',
        'test "${actual_inventory%% *}" = "${source_inventory_sha256}"',
        '"${sha256sum_executable}" --strict --check "${code_manifest}"',
        "",
        'exec "${python_executable}" -B \\',
        '    experiments/'
        'audit_pdb_terminal_incidence_confirmation_sources_v3.py scan \\',
        '    --output-dir "${source_audit_output_dir}" \\',
        '    --inventory-manifest "${source_inventory}" \\',
        '    --inventory-sha256 "${source_inventory_sha256}" \\',
        '    --num-shards 820 \\',
        '    --shard-index "${SLURM_ARRAY_TASK_ID}" \\',
        '    --task-timeout 7200 \\',
        '    --code-manifest "${code_manifest}" \\',
        '    --code-manifest-sha256 "${code_manifest_sha256}"',
    ]
    if lines != expected_lines:
        raise LaunchAuditError("source-audit v3 executable body changed")
    required_environment_lines = {
        "unset {}".format(" ".join(UNSET_PYTHON_ENV)),
        'export PYTHONNOUSERSITE="1"',
        'export PYTHONDONTWRITEBYTECODE="1"',
        'export PYTHONPYCACHEPREFIX="/tmp/'
        'symk-confirmation-source-audit-v3-'
        '${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"',
        'export PATH="{}"'.format(CONTROLLED_PATH),
        'python_executable="{}"'.format(PYTHON_COMMAND),
        'python_executable_sha256="{}"'.format(
            environment["python_executable_sha256"]
        ),
        'sha256sum_executable="{}"'.format(SHA256SUM_COMMAND),
        'sha256sum_executable_sha256="{}"'.format(
            environment["sha256sum_executable_sha256"]
        ),
        'exec "${python_executable}" -B \\',
    }
    if (
        not required_environment_lines <= set(lines)
        or any(lines.count(line) != 1 for line in required_environment_lines)
    ):
        raise LaunchAuditError("source-audit v3 execution environment changed")
    return Base._sha256(SLURM_SCRIPT), manifest_sha, code


def _scoped_repository_commit() -> str:
    jj_identity = _jj_executable_identity()
    diff_command = [
        str(JJ_COMMAND), "--no-pager", "diff", "--summary", "-r", "@", "--",
        *SCOPED_COMMIT_FILES,
    ]
    list_command = [
        str(JJ_COMMAND), "--no-pager", "file", "list", "-r", "@-", "--",
        *SCOPED_COMMIT_FILES,
    ]
    commit_command = [
        str(JJ_COMMAND), "--no-pager", "log", "-r", "@-", "--no-graph",
        "-T", 'commit_id ++ "\\n"',
    ]
    try:
        changed = subprocess.check_output(
            diff_command, cwd=REPO, text=True
        )
        tracked = subprocess.check_output(
            list_command, cwd=REPO, text=True
        ).splitlines()
        commit_id = subprocess.check_output(
            commit_command, cwd=REPO, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot attest scoped v3 commit") from err
    if (
        _jj_executable_identity() != jj_identity
        or changed
        or set(tracked) != set(SCOPED_COMMIT_FILES)
        or len(tracked) != len(SCOPED_COMMIT_FILES)
        or Base.JJ_COMMIT_RE.fullmatch(commit_id) is None
    ):
        raise LaunchAuditError(
            "source-audit v3 requires every bound file committed at @-"
        )
    return commit_id


def _jj_executable_identity() -> dict:
    try:
        info = JJ_COMMAND.lstat()
    except OSError as err:
        raise LaunchAuditError("cannot inspect pinned jj executable") from err
    if (
        not JJ_COMMAND.is_absolute()
        or not stat.S_ISREG(info.st_mode)
        or not os.access(JJ_COMMAND, os.X_OK)
    ):
        raise LaunchAuditError(
            "pinned jj executable is not regular and executable"
        )
    try:
        actual_sha256 = Base._sha256(JJ_COMMAND)
    except Source.SourceAuditError as err:
        raise LaunchAuditError("cannot hash pinned jj executable") from err
    if actual_sha256 != JJ_EXECUTABLE_SHA256:
        raise LaunchAuditError("pinned jj executable bytes changed")
    return {
        "path": str(JJ_COMMAND),
        "sha256": actual_sha256,
    }


def _sbatch_executable_identity() -> dict:
    try:
        info = SBATCH_COMMAND.lstat()
    except OSError as err:
        raise LaunchAuditError("cannot inspect pinned sbatch executable") from err
    if (
        not SBATCH_COMMAND.is_absolute()
        or not stat.S_ISREG(info.st_mode)
        or not os.access(SBATCH_COMMAND, os.X_OK)
    ):
        raise LaunchAuditError(
            "pinned sbatch executable is not regular and executable"
        )
    actual_sha256 = Base._sha256(SBATCH_COMMAND)
    if actual_sha256 != SBATCH_COMMAND_SHA256:
        raise LaunchAuditError("pinned sbatch executable bytes changed")
    return {"path": str(SBATCH_COMMAND), "sha256": actual_sha256}


def _sacct_executable_identity() -> dict:
    try:
        info = SACCT_COMMAND.lstat()
    except OSError as err:
        raise LaunchAuditError("cannot inspect pinned sacct executable") from err
    if (
        not SACCT_COMMAND.is_absolute()
        or not stat.S_ISREG(info.st_mode)
        or not os.access(SACCT_COMMAND, os.X_OK)
    ):
        raise LaunchAuditError(
            "pinned sacct executable is not regular and executable"
        )
    actual_sha256 = Base._sha256(SACCT_COMMAND)
    if actual_sha256 != SACCT_COMMAND_SHA256:
        raise LaunchAuditError("pinned sacct executable bytes changed")
    return {"path": str(SACCT_COMMAND), "sha256": actual_sha256}


def _scheduler_rows(
    job_id: str, expected_tasks: set[int] | None = None
) -> list[dict]:
    _sacct_executable_identity()
    if expected_tasks is None:
        expected_tasks = set(range(ARRAY_TASKS))
    if (
        not isinstance(job_id, str)
        or not job_id.isdigit()
        or type(expected_tasks) is not set
        or not expected_tasks
        or any(
            type(task) is not int or not 0 <= task < ARRAY_TASKS
            for task in expected_tasks
        )
    ):
        raise LaunchAuditError("source-audit scheduler query is invalid")
    command = [
        str(SACCT_COMMAND), "-j", job_id, "-X", "-n", "-P",
        "--format=JobID,State,ExitCode,Elapsed,Partition",
    ]
    try:
        output = subprocess.check_output(
            command,
            env=dict(SUBMISSION_ENVIRONMENT),
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot query source-audit accounting") from err
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
            continue
        task = int(suffix)
        if task in rows or task not in expected_tasks or partition != "fat":
            raise LaunchAuditError("source-audit accounting identity changed")
        rows[task] = {
            "array_task": task,
            "state": state.split("+", 1)[0].split()[0],
            "exit_code": exit_code,
            "elapsed": elapsed,
            "partition": partition,
        }
    if set(rows) != expected_tasks:
        raise LaunchAuditError("source-audit accounting task set is incomplete")
    return [rows[index] for index in sorted(expected_tasks)]


def _journal_job_ids(intent: dict) -> list[str]:
    _sacct_executable_identity()
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
    command = [
        str(SACCT_COMMAND), "-X", "-S", recorded.date().isoformat(),
        "--name=" + job_name, "-n", "-P",
        "--format=JobID%64,JobName%128,Comment%128,SubmitLine%4096",
    ]
    try:
        output = subprocess.check_output(
            command,
            env=dict(SUBMISSION_ENVIRONMENT),
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError(
            "cannot query source-audit submission journal"
        ) from err
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
        if (
            actual_name == job_name
            or actual_comment == comment
            or command_matches
            or token in submit_line
        ):
            parent_match = re.fullmatch(r"([0-9]+)", job_id)
            array_match = re.fullmatch(r"([0-9]+)_([0-9]+)", job_id)
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


def _fixed_materials(
    source_inventory_sha256: str,
    repository_commit_id: str | None = None,
) -> dict:
    if source_inventory_sha256 != V2_SOURCE_INVENTORY_SHA256:
        raise LaunchAuditError("frozen source inventory hash changed")
    slurm_sha, manifest_sha, code = _slurm_preflight()
    environment = Base._execution_environment(code)
    if repository_commit_id is None:
        repository_commit_id = _scoped_repository_commit()
    if Base.JJ_COMMIT_RE.fullmatch(repository_commit_id) is None:
        raise LaunchAuditError("source-audit v3 repository commit is invalid")
    jj_identity = _jj_executable_identity()
    sbatch_identity = _sbatch_executable_identity()
    sacct_identity = _sacct_executable_identity()
    return {
        "campaign": "v3",
        "whole_campaign_rerun": True,
        "reused_v1_shards": 0,
        "reused_v2_shards": 0,
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
        "prior_identity_ledger_sha256": (
            Inventory.PRIOR_IDENTITY_LEDGER_SHA256
        ),
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
        "code_manifest_sha256": manifest_sha,
        "launcher_sha256": Base._sha256(Path(__file__)),
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
        "candidate_attestation": str(CANDIDATE),
        "frozen_attestation": str(ATTESTATION),
        "execution_environment": environment,
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
    if (
        not isinstance(token, str)
        or Base.SUBMISSION_TOKEN_RE.fullmatch(token) is None
    ):
        raise LaunchAuditError("source-audit v3 submission token is invalid")
    return (
        "{}-{}".format(JOB_NAME_PREFIX, token),
        "{}/{}".format(COMMENT_PREFIX, token),
    )


def _submit_command(
    source_inventory_sha256: str,
    output_dir: Path,
    submission_token: str,
) -> list[str]:
    if source_inventory_sha256 != V2_SOURCE_INVENTORY_SHA256:
        raise LaunchAuditError("frozen source inventory hash changed")
    job_name, comment = _submission_identity(submission_token)
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
        "--output={}".format(
            (OUTPUT_DIR / "slurm-%A_%a.out").resolve()
        ),
        str(SLURM_SCRIPT), source_inventory_sha256,
        str(Path(output_dir).resolve()),
    ]


def _v1_failure_diagnostic() -> dict:
    raw, receipt = Base._load_json(
        V1_LAUNCH_RECEIPT, "v1 source-audit launch receipt"
    )
    if (
        hashlib.sha256(raw).hexdigest() != V1_LAUNCH_RECEIPT_SHA256
        or receipt.get("job_id") != V1_JOB_ID
        or receipt.get("memory_per_cpu") != V1_MEMORY_PER_CPU
        or receipt.get("array_tasks") != ARRAY_TASKS
        or receipt.get("candidates") != Source.CANDIDATE_COUNT
        or receipt.get("source_inventory_sha256")
        != V1_SOURCE_INVENTORY_SHA256
        or receipt.get("code_manifest_sha256")
        != V1_CODE_MANIFEST_SHA256
        or receipt.get("slurm_script_sha256") != V1_SLURM_SCRIPT_SHA256
    ):
        raise LaunchAuditError("v1 launch diagnostic provenance changed")
    if any(path.exists() for path in (
        V1_CANDIDATE, V1_ATTESTATION, V1_EXECUTION_RECEIPT,
    )):
        raise LaunchAuditError(
            "v1 source outcome or execution attestation unexpectedly exists"
        )
    rows = Base._scheduler_rows(V1_JOB_ID)
    states = Counter(row["state"] for row in rows)
    if (
        len(rows) != ARRAY_TASKS
        or any(row["state"] not in V1_TERMINAL_STATES for row in rows)
        or states["OUT_OF_MEMORY"] < 1
    ):
        raise LaunchAuditError(
            "v1 accounting is not fully terminal with an OOM diagnosis"
        )
    return {
        "schema": Source.SCHEMA + "/campaign-v2/v1-infrastructure-diagnostic",
        "v1_launch_receipt_path": str(V1_LAUNCH_RECEIPT),
        "v1_launch_receipt_sha256": V1_LAUNCH_RECEIPT_SHA256,
        "v1_job_id": V1_JOB_ID,
        "v1_memory_per_cpu": V1_MEMORY_PER_CPU,
        "v1_scheduler_rows": rows,
        "v1_scheduler_rows_sha256": hashlib.sha256(
            Source.canonical_json(rows)
        ).hexdigest(),
        "v1_scheduler_state_counts": dict(sorted(states.items())),
        "v1_source_attestation_absent": True,
        "successful_shard_contents_used_for_v2_design": False,
        "source_support_outcomes_used_for_v2_design": False,
        "inspection_scope": (
            "scheduler states plus OOM log/task diagnostics only"
        ),
        "failure_class": "scheduler-out-of-memory",
        "rerun_scope": "all-820-shards",
        "reused_v1_shards": 0,
    }


def _v2_failure_diagnostic() -> dict:
    raw, receipt = Base._load_json(
        V2_LAUNCH_RECEIPT, "v2 source-audit launch receipt"
    )
    v1_diagnostic = _v1_failure_diagnostic()
    integer_fields = {
        "array_tasks": ARRAY_TASKS,
        "candidates": Source.CANDIDATE_COUNT,
        "cpus_per_task": 1,
        "array_throttle": 0,
        "reused_v1_shards": 0,
        "task_timeout_seconds": V2_TASK_TIMEOUT_SECONDS,
    }
    if (
        hashlib.sha256(raw).hexdigest() != V2_LAUNCH_RECEIPT_SHA256
        or receipt.get("schema") != Source.SCHEMA + "/campaign-v2/launch"
        or receipt.get("campaign") != "v2"
        or receipt.get("whole_campaign_rerun") is not True
        or receipt.get("job_id") != V2_JOB_ID
        or receipt.get("partition") != "fat"
        or receipt.get("memory_per_cpu") != V2_MEMORY_PER_CPU
        or receipt.get("time_limit") != V2_TIME_LIMIT
        or receipt.get("array") != "0-819"
        or any(
            type(receipt.get(key)) is not int or receipt.get(key) != value
            for key, value in integer_fields.items()
        )
        or receipt.get("source_inventory_sha256")
        != V2_SOURCE_INVENTORY_SHA256
        or receipt.get("code_manifest_sha256")
        != V2_CODE_MANIFEST_SHA256
        or receipt.get("slurm_script_sha256") != V2_SLURM_SCRIPT_SHA256
        or receipt.get("v1_failure_diagnostic") != v1_diagnostic
    ):
        raise LaunchAuditError("v2 launch diagnostic provenance changed")
    if any(path.exists() for path in (
        V2_CANDIDATE, V2_ATTESTATION, V2_EXECUTION_RECEIPT,
    )):
        raise LaunchAuditError(
            "v2 source outcome or execution attestation unexpectedly exists"
        )
    rows = Base._scheduler_rows(V2_JOB_ID)
    states = Counter(row["state"] for row in rows)
    rows_sha256 = hashlib.sha256(Source.canonical_json(rows)).hexdigest()
    if (
        len(rows) != ARRAY_TASKS
        or dict(sorted(states.items())) != V2_SCHEDULER_STATE_COUNTS
        or rows_sha256 != V2_SCHEDULER_ROWS_SHA256
        or any(
            row["exit_code"] != {
                "COMPLETED": "0:0",
                "FAILED": "75:0",
                "OUT_OF_MEMORY": "0:125",
            }[row["state"]]
            for row in rows
        )
    ):
        raise LaunchAuditError(
            "v2 accounting is not fully terminal with timeout/OOM diagnoses"
        )
    failure_logs = []
    for row in rows:
        if row["state"] == "COMPLETED":
            continue
        path = V2_OUTPUT_DIR / "slurm-{}_{}.out".format(
            V2_JOB_ID, row["array_task"]
        )
        try:
            info = path.lstat()
            payload = path.read_bytes()
        except OSError as err:
            raise LaunchAuditError("cannot read v2 failure diagnostic") from err
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise LaunchAuditError("v2 failure diagnostic is not regular")
        if row["state"] == "FAILED":
            marker = b"infrastructure error: translator exceeded 2700s"
        else:
            marker = b"oom_kill"
        if marker not in payload:
            raise LaunchAuditError("v2 failure diagnostic class changed")
        failure_logs.append({
            "array_task": row["array_task"],
            "state": row["state"],
            "sha256": hashlib.sha256(payload).hexdigest(),
        })
    failure_logs_sha256 = hashlib.sha256(
        Source.canonical_json(failure_logs)
    ).hexdigest()
    if failure_logs_sha256 != V2_FAILURE_LOGS_SHA256:
        raise LaunchAuditError("v2 failure-log manifest changed")
    return {
        "schema": Source.SCHEMA + "/campaign-v3/v2-infrastructure-diagnostic",
        "v2_launch_receipt_path": str(V2_LAUNCH_RECEIPT),
        "v2_launch_receipt_sha256": V2_LAUNCH_RECEIPT_SHA256,
        "v2_job_id": V2_JOB_ID,
        "v2_memory_per_cpu": V2_MEMORY_PER_CPU,
        "v2_task_timeout_seconds": V2_TASK_TIMEOUT_SECONDS,
        "v2_time_limit": V2_TIME_LIMIT,
        "v2_scheduler_rows": rows,
        "v2_scheduler_rows_sha256": rows_sha256,
        "v2_scheduler_state_counts": dict(sorted(states.items())),
        "v2_failure_logs": failure_logs,
        "v2_failure_logs_sha256": failure_logs_sha256,
        "v2_source_attestation_absent": True,
        "successful_v1_v2_shard_contents_used_for_v3_design": False,
        "source_support_outcomes_used_for_v3_design": False,
        "inspection_scope": (
            "scheduler rows plus timeout/OOM logs and task names only"
        ),
        "failure_class": "translator-timeout-and-out-of-memory",
        "resource_amendment": {
            "memory_per_cpu": MEMORY_PER_CPU,
            "task_timeout_seconds": Source.TASK_TIMEOUT_SECONDS,
            "time_limit": TIME_LIMIT,
        },
        "rerun_scope": "all-820-shards",
        "reused_v1_shards": 0,
        "reused_v2_shards": 0,
        "v1_failure_diagnostic": v1_diagnostic,
    }


def _assert_launch_namespace_empty() -> None:
    paths = (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR,
        CANDIDATE, ATTESTATION, RECOVERY_ARTIFACT_ROOT,
        RECOVERY_DATA_ROOT, UNION_DIR,
    )
    if any(path.exists() for path in paths):
        raise LaunchAuditError(
            "source-audit v3 launch namespace is not empty"
        )


def launch() -> None:
    _assert_launch_namespace_empty()
    inventory = Inventory.load_inventory()
    source_inventory_value = Source.build_inventory_manifest(inventory)
    source_inventory_raw = Source.canonical_json(source_inventory_value)
    source_inventory_sha = hashlib.sha256(source_inventory_raw).hexdigest()
    materials = _fixed_materials(source_inventory_sha)
    diagnostic = _v2_failure_diagnostic()
    token = secrets.token_hex(12)
    recorded_utc = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(timespec="seconds")
    command = _submit_command(source_inventory_sha, OUTPUT_DIR, token)
    intent = {
        "schema": LAUNCH_SCHEMA + "/intent",
        **materials,
        "v2_failure_diagnostic": diagnostic,
        "recorded_utc": recorded_utc,
        "submission_token": token,
        "submit_command": command,
    }
    Base._exclusive_json(INTENT, intent, "source-audit v3 launch intent")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    Base._exclusive_bytes(
        SOURCE_INVENTORY,
        source_inventory_raw,
        "source inventory v3",
    )
    try:
        output = subprocess.check_output(
            command,
            cwd=REPO,
            env=dict(SUBMISSION_ENVIRONMENT),
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("source-audit v3 sbatch failed after intent") from err
    job_id = output.split(";", 1)[0]
    digest = Base._write_launch_receipt(
        Source.canonical_json(intent), intent, job_id
    )
    print(json.dumps({
        "job_id": job_id,
        "launch_receipt_sha256": digest,
        "source_inventory_sha256": source_inventory_sha,
    }, sort_keys=True, indent=2))


def _load_intent_only() -> tuple[bytes, dict, dict]:
    raw, intent = Base._load_json(INTENT, "source-audit v3 launch intent")
    source_inventory_sha = intent.get("source_inventory_sha256")
    materials = _fixed_materials(
        source_inventory_sha, intent.get("repository_commit_id")
    )
    diagnostic = _v2_failure_diagnostic()
    token = intent.get("submission_token")
    recorded_utc = intent.get("recorded_utc")
    command = _submit_command(source_inventory_sha, OUTPUT_DIR, token)
    if (
        intent != {
            "schema": LAUNCH_SCHEMA + "/intent",
            **materials,
            "v2_failure_diagnostic": diagnostic,
            "recorded_utc": recorded_utc,
            "submission_token": token,
            "submit_command": command,
        }
        or not isinstance(recorded_utc, str)
        or Base.SUBMISSION_TOKEN_RE.fullmatch(token or "") is None
    ):
        raise LaunchAuditError("source-audit v3 launch intent changed")
    Source.load_inventory_manifest(SOURCE_INVENTORY, source_inventory_sha)
    return raw, intent, {**materials, "v2_failure_diagnostic": diagnostic}


def _validate_original_success_rows(rows: list[dict]) -> None:
    expected_keys = {
        "array_task", "state", "exit_code", "elapsed", "partition",
    }
    if type(rows) is not list or len(rows) != ARRAY_TASKS:
        raise LaunchAuditError("source-audit v3 scheduler cardinality changed")
    for index, row in enumerate(rows):
        if (
            type(row) is not dict
            or set(row) != expected_keys
            or type(row.get("array_task")) is not int
            or row["array_task"] != index
            or row.get("state") != "COMPLETED"
            or row.get("exit_code") != "0:0"
            or row.get("partition") != "fat"
            or not isinstance(row.get("elapsed"), str)
            or not row["elapsed"]
        ):
            raise LaunchAuditError(
                "campaign v3 requires every original shard to complete"
            )


def _scheduler_contract_rows(
    job_id: str, launch_receipt: dict, scheduler_rows: list[dict]
) -> list[dict]:
    _sacct_executable_identity()
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("source-audit v3 job id is invalid")
    command = [
        str(SACCT_COMMAND), "-j", job_id, "-X", "-n", "-P",
        "--format=JobID,Account,Partition,QOS,ReqCPUS,ReqMem,"
        "Timelimit,State,ExitCode,JobName",
    ]
    try:
        output = subprocess.check_output(
            command,
            env=dict(SUBMISSION_ENVIRONMENT),
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError(
            "cannot query source-audit v3 resource accounting"
        ) from err
    token = launch_receipt.get("submission_token")
    expected_name, _ = _submission_identity(token)
    prefix = job_id + "_"
    rows = {}
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 10:
            raise LaunchAuditError("source-audit v3 resource row changed")
        (
            array_id, account, partition, qos, req_cpus, req_mem,
            time_limit, state, exit_code, job_name,
        ) = fields
        if not array_id.startswith(prefix):
            continue
        suffix = array_id[len(prefix):]
        if not suffix.isdigit():
            continue
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
            or scheduler_rows[task]["state"] != state
            or scheduler_rows[task]["exit_code"] != exit_code
        ):
            raise LaunchAuditError(
                "source-audit v3 actual resource contract changed"
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
            "source-audit v3 resource accounting task set is incomplete"
        )
    return [rows[index] for index in range(ARRAY_TASKS)]


def seal() -> None:
    import recover_pdb_terminal_incidence_confirmation_source_audit_v3 as Recovery

    if (
        EXECUTION_RECEIPT.exists()
        or CANDIDATE.exists()
        or ATTESTATION.exists()
        or Recovery.UNION_DIR.exists()
    ):
        raise LaunchAuditError("source-audit v3 execution artifacts already exist")
    launch_sha, launch_receipt, rows = Base.status()
    _validate_original_success_rows(rows)
    contract_rows = _scheduler_contract_rows(
        launch_receipt["job_id"], launch_receipt, rows
    )
    union = Recovery.prepare_union(launch_sha, launch_receipt, rows)
    if (
        union.get("recovery") is not None
        or any(
            item.get("shard_index") != index
            or item.get("origin") != "original"
            for index, item in enumerate(union.get("sources", []))
        )
        or len(union.get("sources", [])) != ARRAY_TASKS
    ):
        raise LaunchAuditError("campaign v3 cannot use recovered shards")
    Source.main([
        "assemble",
        "--shard-dir", str(Recovery.UNION_DIR),
        "--inventory-manifest", str(SOURCE_INVENTORY),
        "--inventory-sha256", launch_receipt["source_inventory_sha256"],
        "--num-shards", str(ARRAY_TASKS),
        "--output", str(CANDIDATE),
        "--code-manifest", str(CODE_MANIFEST),
        "--code-manifest-sha256", launch_receipt["code_manifest_sha256"],
    ])
    Recovery.verify_union(union, launch_receipt)
    candidate_raw, candidate = Base._load_json(
        CANDIDATE, "source-audit v3 candidate attestation"
    )
    if (
        candidate.get("schema") != Source.SCHEMA
        or candidate.get("counts", {}).get("candidates")
        != Source.CANDIDATE_COUNT
        or candidate.get("counts", {}).get("translation_attempts")
        != Source.CANDIDATE_COUNT
        or candidate.get("confirmation_prelaunch_authorized")
        is not candidate.get("prelaunch_gate", {}).get("passed")
    ):
        raise LaunchAuditError("source-audit v3 candidate identity changed")
    attestation_sha = Base._exclusive_bytes(
        ATTESTATION, candidate_raw, "frozen source-audit v3 attestation"
    )
    receipt = {
        "schema": EXECUTION_SCHEMA,
        "campaign": "v3",
        "whole_campaign_rerun": True,
        "reused_v1_shards": 0,
        "reused_v2_shards": 0,
        "v2_failure_diagnostic": launch_receipt["v2_failure_diagnostic"],
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
        "scheduler_state_counts": dict(Counter(
            row["state"] for row in rows
        )),
        "scheduler_rows": rows,
        "scheduler_contract_rows": contract_rows,
        "sacct_executable": launch_receipt["sacct_executable"],
        "sacct_executable_sha256": launch_receipt[
            "sacct_executable_sha256"
        ],
        "original_output_tree": union["original_output_tree"],
        "recovery": union["recovery"],
        "union_sources": union["sources"],
        "union_tree": union["union_tree"],
        "code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "source_inventory_sha256": launch_receipt[
            "source_inventory_sha256"
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
    digest = Base._exclusive_json(
        EXECUTION_RECEIPT, receipt, "source-audit v3 execution receipt"
    )
    print(json.dumps({
        "attestation_sha256": attestation_sha,
        "confirmation_prelaunch_authorized": candidate[
            "confirmation_prelaunch_authorized"
        ],
        "execution_receipt_sha256": digest,
        "union_tree_sha256": union["union_tree"]["sha256"],
    }, sort_keys=True, indent=2))


for _name, _value in {
    "LaunchAuditError": LaunchAuditError,
    "_slurm_preflight": _slurm_preflight,
    "_fixed_materials": _fixed_materials,
    "_submission_identity": _submission_identity,
    "_submit_command": _submit_command,
    "_scheduler_rows": _scheduler_rows,
    "_journal_job_ids": _journal_job_ids,
    "launch": launch,
    "_load_intent_only": _load_intent_only,
    "seal": seal,
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
        LaunchAuditError,
        Source.SourceAuditError,
        Inventory.InventoryError,
    ) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
