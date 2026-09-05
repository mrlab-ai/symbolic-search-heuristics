#!/usr/bin/env python3
"""Run the prospective V8 repair and seal the fixed V5/V8 source union.

V8 inherits the exact scheduler-only 795/25 partition committed by V7.  It
never diagnoses V5 again and never consumes a V7 task artifact.  Relative to
V7's rejected submission, its only scheduler-relevant change is the uniform
memory request from 3000G to the independently test-accepted 2950G profile.
"""

from __future__ import annotations

import argparse
import copy
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


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources_v5 as V5Source
import audit_pdb_terminal_incidence_confirmation_sources_v8 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v5 as V5Launch
import launch_pdb_terminal_incidence_confirmation_source_audit_v7 as V7Launch
import pdb_terminal_incidence_confirmation_inventory as Inventory
import pdb_terminal_incidence_confirmation_safe_io_v8 as SelectedIO
import pdb_terminal_incidence_confirmation_source_consumer_v5 as V5Consumer


def _load_private_v6_runtime():
    """Load committed V6 helpers without mutating the public V6 module."""
    path = (
        SCRIPT_DIR /
        "launch_pdb_terminal_incidence_confirmation_source_audit_v6.py"
    )
    name = "_pdb_terminal_incidence_confirmation_source_audit_v8_runtime"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load committed V6 repair helpers")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


Runtime = _load_private_v6_runtime()
LaunchAuditError = Runtime.LaunchAuditError

SCHEMA = Source.Base.SCHEMA + "/campaign-v8"
DIAGNOSTIC_SCHEMA = V7Launch.DIAGNOSTIC_SCHEMA
LAUNCH_SCHEMA = SCHEMA + "/repair-launch/v1"
EXECUTION_SCHEMA = SCHEMA + "/execution/v1"
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v8"
)
DIAGNOSTIC = V7Launch.DIAGNOSTIC
V7_LAUNCH_INTENT = V7Launch.INTENT
V7_LAUNCH_FAILURE = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v7" /
    "source-audit-repair-launch-failure-v7.json"
)
V7_LAUNCH_FAILURE_SHA256 = (
    "2e944a6c04322b36361b0ec7c6a4785a065f7d977ca4472e66ec2a938da8c8cd"
)
V7_DIAGNOSTIC_SHA256 = (
    "9ddb5f19ccc05f4d48e037f2175feaebdb548a053430865faf540979f77c9110"
)
V7_INTENT_SHA256 = (
    "2c63e63adfed5da82224c6d66ab92e8ec6647d8bf0f667b389bae54f55521a17"
)
V7_CODE_MANIFEST_SHA256 = (
    "1c6d390ce32a16b43472ad9228b2e3d07109147e95e623f8ec5fc10126c4b34a"
)
INTENT = ARTIFACT_DIR / "source-audit-repair-launch-intent-v8.json"
SBATCH_STDOUT = ARTIFACT_DIR / "source-audit-sbatch-stdout-v8.bin"
SBATCH_STDERR = ARTIFACT_DIR / "source-audit-sbatch-stderr-v8.bin"
SBATCH_RESULT = ARTIFACT_DIR / "source-audit-sbatch-result-v8.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-repair-launch-receipt-v8.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v8.json"
SEAL_PLAN = ARTIFACT_DIR / "source-audit-seal-plan-v8.json"
UNION_ROOT_STAGE = ARTIFACT_DIR / "source-audit-union-root-stage-v8.json"
UNION_STAGE = ARTIFACT_DIR / "source-audit-union-stage-v8.json"
CANDIDATE_STAGE = ARTIFACT_DIR / "source-audit-candidate-stage-v8.json"
ATTESTATION_STAGE = ARTIFACT_DIR / "source-audit-attestation-stage-v8.json"
SEAL_STAGE_ARTIFACTS = (
    SEAL_PLAN, UNION_ROOT_STAGE, UNION_STAGE,
    CANDIDATE_STAGE, ATTESTATION_STAGE,
)
SLURM_TEMPLATE = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v8.slurm"
)
CODE_MANIFEST = Source.DEFAULT_CODE_MANIFEST
OUTPUT_DIR = Source.DEFAULT_SHARDS
SOURCE_INVENTORY = Source.DEFAULT_INVENTORY
TMP_ROOT = Source.TMP_ROOT
UNION_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v8_union"
)
CANDIDATE = Source.DEFAULT_OUTPUT
ATTESTATION = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v8.json"
)
V5_OUTPUT_DIR = V5Launch.OUTPUT_DIR
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
V8_TOTAL_MEMORY = "2950G"
V8_TOTAL_MEMORY_MIB = 2950 * 1024
FAT_NODE_REAL_MEMORY_MIB = V5Launch.FAT_NODE_REAL_MEMORY_MIB
FAT_NODE_MEM_SPEC_LIMIT_MIB = 65536
FAT_NODE_ALLOCATABLE_MEMORY_MIB = (
    FAT_NODE_REAL_MEMORY_MIB - FAT_NODE_MEM_SPEC_LIMIT_MIB
)
V8_TASK_TIMEOUT_SECONDS = Source.TASK_TIMEOUT_SECONDS
V5_TASK_TIMEOUT_SECONDS = V5Source.TASK_TIMEOUT_SECONDS
V8_TIME_LIMIT = "3-00:00:00"
ACCEPTED_TRANSLATION_STATUSES = ("input-rejected", "success")
CONTROLLED_PATH = V5Launch.CONTROLLED_PATH
SUBMISSION_ENVIRONMENT = dict(V5Launch.SUBMISSION_ENVIRONMENT)
SBATCH_COMMAND = V5Launch.SBATCH_COMMAND
SBATCH_COMMAND_SHA256 = V5Launch.SBATCH_COMMAND_SHA256
SACCT_COMMAND = V5Launch.SACCT_COMMAND
SACCT_COMMAND_SHA256 = V5Launch.SACCT_COMMAND_SHA256
JOB_NAME_PREFIX = "confirmation-source-audit-v8"
COMMENT_PREFIX = "confirmation-source-audit-v8"
TIMEOUT_PLACEHOLDER = b"__V8_TASK_TIMEOUT_SECONDS__"
MANIFEST_PLACEHOLDER = b"__V8_CODE_MANIFEST_SHA256__"
NORMALIZED_SLURM_SHA256 = (
    "ab074a889e4ab031294baf199e9d7deaa4e6aafe2288c44535791cbf33b1dea8"
)

SEAL_PLAN_SCHEMA = EXECUTION_SCHEMA + "/seal-plan/v1"
UNION_ROOT_STAGE_SCHEMA = EXECUTION_SCHEMA + "/union-root-stage/v1"
UNION_STAGE_SCHEMA = EXECUTION_SCHEMA + "/union-stage/v1"
CANDIDATE_STAGE_SCHEMA = EXECUTION_SCHEMA + "/candidate-stage/v1"
ATTESTATION_STAGE_SCHEMA = EXECUTION_SCHEMA + "/attestation-stage/v1"
SBATCH_RESULT_SCHEMA = LAUNCH_SCHEMA + "/sbatch-result/v1"
CAPTURE_IDENTITY_KEYS = frozenset({
    "path", "canonical_path", "device", "inode", "mode", "uid", "gid",
    "link_count", "bytes_at_intent",
})
FINAL_CAPTURE_IDENTITY_KEYS = (
    CAPTURE_IDENTITY_KEYS - {"bytes_at_intent"}
) | {"bytes"}

ACTIVE_STATES = Runtime.ACTIVE_STATES
TERMINAL_ACCOUNTING_STATES = Runtime.TERMINAL_ACCOUNTING_STATES
EXIT_CODE_RE = Runtime.EXIT_CODE_RE
SHA256_RE = Runtime.SHA256_RE
JJ_COMMIT_RE = Runtime.JJ_COMMIT_RE
SUBMISSION_TOKEN_RE = Runtime.SUBMISSION_TOKEN_RE
DIAGNOSTIC_ROW_KEYS = frozenset({
    "array_task", "state", "exit_code", "partition",
})
DIAGNOSTIC_FIELDS = V7Launch.DIAGNOSTIC_FIELDS

DIAGNOSTIC_RELATIVE_PATH = DIAGNOSTIC.relative_to(REPO).as_posix()
_V5_RUNTIME_INPUTS = V7Launch._V5_RUNTIME_INPUTS
PRE_DIAGNOSIS_FILES = V7Launch.PRE_DIAGNOSIS_FILES
SCOPED_COMMIT_FILES = tuple(sorted({
    *Source.CODE_MANIFEST_FILES,
    CODE_MANIFEST.relative_to(REPO).as_posix(),
}))


def _canonical_json(value) -> bytes:
    return Runtime._canonical_json(value)


def _digest(value) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    try:
        return SelectedIO.atomic_exclusive_bytes(
            Path(path), raw, label, root=REPO
        )
    except SelectedIO.PublicationError as err:
        raise LaunchAuditError(str(err)) from err


def _create_private_directory(path: Path, label: str) -> dict:
    try:
        info = SelectedIO.create_private_directory(
            Path(path), label, root=REPO
        )
    except SelectedIO.PublicationError as err:
        raise LaunchAuditError(str(err)) from err
    return {
        "path": str(path), "canonical_path": str(path),
        "device": info["device"], "inode": info["inode"],
        "mode": "0700", "uid": info["uid"],
    }


def _matches(pattern: re.Pattern, value) -> bool:
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _validate_capture_initial_identities(value: dict) -> dict:
    expected_paths = {"stdout": SBATCH_STDOUT, "stderr": SBATCH_STDERR}
    if type(value) is not dict or set(value) != set(expected_paths):
        raise LaunchAuditError("V8 sbatch capture identities changed")
    inodes = []
    for stream, path in expected_paths.items():
        record = value.get(stream)
        if (
            type(record) is not dict
            or set(record) != CAPTURE_IDENTITY_KEYS
            or record.get("path") != str(path)
            or record.get("canonical_path") != str(path)
            or record.get("mode") != "0400"
            or record.get("uid") != os.getuid()
            or type(record.get("link_count")) is not int
            or record.get("link_count") != 1
            or type(record.get("bytes_at_intent")) is not int
            or record.get("bytes_at_intent") != 0
            or any(
                type(record.get(field)) is not int
                or record[field] < (1 if field == "inode" else 0)
                for field in ("device", "inode", "uid", "gid")
            )
        ):
            raise LaunchAuditError("V8 sbatch capture identities changed")
        inodes.append((record["device"], record["inode"]))
    if len(set(inodes)) != 2:
        raise LaunchAuditError("V8 sbatch capture identities alias")
    return value


def _validate_final_capture_records(
    intent: dict,
    records: dict[str, dict],
    payloads: dict[str, bytes],
) -> None:
    initial = _validate_capture_initial_identities(
        intent.get("sbatch_capture_initial_identities")
    )
    paths = {"stdout": SBATCH_STDOUT, "stderr": SBATCH_STDERR}
    if (
        type(records) is not dict
        or set(records) != set(paths)
        or type(payloads) is not dict
        or set(payloads) != set(paths)
    ):
        raise LaunchAuditError("V8 sbatch capture records changed")
    for stream, path in paths.items():
        raw = payloads[stream]
        record = records[stream]
        final = record.get("final_identity") if type(record) is dict else None
        expected_initial = initial[stream]
        if (
            type(raw) is not bytes
            or type(record) is not dict
            or set(record) != {
                "path", "bytes", "sha256",
                "initial_identity", "final_identity",
            }
            or record.get("path") != str(path)
            or type(record.get("bytes")) is not int
            or record.get("bytes") != len(raw)
            or record.get("sha256") != hashlib.sha256(raw).hexdigest()
            or record.get("initial_identity") != expected_initial
            or type(final) is not dict
            or set(final) != FINAL_CAPTURE_IDENTITY_KEYS
            or final.get("path") != str(path)
            or final.get("canonical_path") != str(path)
            or final.get("mode") != "0400"
            or type(final.get("bytes")) is not int
            or final.get("bytes") != len(raw)
            or any(
                final.get(field) != expected_initial[field]
                for field in (
                    "device", "inode", "uid", "gid", "link_count",
                )
            )
        ):
            raise LaunchAuditError("V8 sbatch capture records changed")


def _pre_diagnosis_file_records() -> list[dict]:
    """Reuse V7's exact immutable prediagnosis byte boundary."""
    return V7Launch._pre_diagnosis_file_records()


def _validate_recorded_pre_diagnosis_freeze(value: dict) -> None:
    """Validate the immutable freeze record without reading descendant files.

    Launch and recovery additionally call the imported live validator.  A
    downstream consumer instead authenticates these exact recorded hashes from
    the pinned prediagnosis revision, so unrelated paper and renderer files may
    evolve after a successful V8 seal.
    """
    expected_keys = {
        "schema", "repository_commit_id", "working_copy_revision",
        "committed_revision", "scoped_diff_empty", "diagnostic_excluded",
        "jj", "files", "files_sha256",
    }
    files = value.get("files") if type(value) is dict else None
    if type(files) is not list:
        raise LaunchAuditError("V8 recorded prediagnosis freeze changed")
    expected_paths = list(PRE_DIAGNOSIS_FILES)
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
        or len(files) != len(expected_paths)
        or [
            item.get("path") if type(item) is dict else None
            for item in files
        ] != expected_paths
        or any(
            set(item) != {"path", "bytes", "sha256"}
            or type(item["bytes"]) is not int
            or item["bytes"] < 0
            or not _matches(SHA256_RE, item["sha256"])
            for item in files
        )
        or value.get("files_sha256") != _digest(files)
    ):
        raise LaunchAuditError("V8 recorded prediagnosis freeze changed")


def _resource_mapping() -> dict:
    maximum_candidate_seconds = Source.TASKS_PER_SHARD * V8_TASK_TIMEOUT_SECONDS
    job_limit_seconds = 3 * 24 * 60 * 60
    if (
        V8_TOTAL_MEMORY_MIB >= FAT_NODE_ALLOCATABLE_MEMORY_MIB
        or maximum_candidate_seconds >= job_limit_seconds
    ):
        raise LaunchAuditError("V8 fixed resource ceiling is inconsistent")
    return {
        "profile": "fixed-fat-allocatable-v8",
        "fixed_before_v8_launch": True,
        "uniform_for_every_repair_shard": True,
        "nodes": 1,
        "ntasks": 1,
        "cpus_per_task": CPUS_PER_TASK,
        "memory": {
            "option": "--mem={}".format(V8_TOTAL_MEMORY),
            "requested": V8_TOTAL_MEMORY,
            "mode": "total",
        },
        "task_timeout_seconds": V8_TASK_TIMEOUT_SECONDS,
        "time_limit": V8_TIME_LIMIT,
        "fat_node_real_memory_mib": FAT_NODE_REAL_MEMORY_MIB,
        "fat_node_mem_spec_limit_mib": FAT_NODE_MEM_SPEC_LIMIT_MIB,
        "fat_node_allocatable_memory_mib": FAT_NODE_ALLOCATABLE_MEMORY_MIB,
        "v8_total_memory_mib": V8_TOTAL_MEMORY_MIB,
        "fat_node_allocatable_memory_headroom_mib": (
            FAT_NODE_ALLOCATABLE_MEMORY_MIB - V8_TOTAL_MEMORY_MIB
        ),
        "candidates_per_shard": Source.TASKS_PER_SHARD,
        "maximum_candidate_seconds_per_shard": maximum_candidate_seconds,
        "job_limit_seconds": job_limit_seconds,
        "wrapper_headroom_seconds": job_limit_seconds - maximum_candidate_seconds,
        "historical_operational_information_known_before_v8_freeze": [
            "aggregate V5 terminal scheduler states: 795 COMPLETED, "
            "15 FAILED, 10 OUT_OF_MEMORY",
            "V6 classifier rejection of array row 2 as FAILED 2:0",
            "V7 one-shot 3000G submission was rejected before a job existed",
            "post-failure non-submitting scheduler tests rejected 3000G and "
            "accepted 2950G after accounting for MemSpecLimit",
        ],
        "scheduler_profile_change_from_v7": ["memory 3000G to 2950G"],
        "post_failure_test_only_validation": {
            "submits_job": False,
            "v7_exact_profile_exit_code": 1,
            "v7_exact_profile_stderr": (
                "allocation failure: Requested node configuration is not available"
            ),
            "v8_corrected_profile_exit_code": 0,
            "v8_scheduler_estimate": (
                "request accepted for scheduling estimation on an idle fat node"
            ),
            "original_v7_submission_stderr_preserved": False,
            "interpretation": (
                "post-hoc scheduler-cause reconstruction, not original "
                "submission evidence"
            ),
        },
        "per_task_difficulty_fields_consulted_for_resource_selection": [],
        "source_support_fields_consulted_for_resource_selection": [],
        "resource_ceiling_policy": {
            "child_level_exclusion_allowed": False,
            "seal_requires_every_repair_shard_completed_0_0": True,
            "partial_repair_shards_usable": False,
            "adaptive_retry_or_escalation_allowed": False,
        },
    }


def _design_timing_disclosure() -> dict:
    return {
        "historical_operational_information_known_before_v8_freeze": [
            "aggregate V5 terminal scheduler-state counts: 795 COMPLETED, "
            "15 FAILED, 10 OUT_OF_MEMORY",
            "V6 classifier rejected scheduler array row 2 as FAILED 2:0",
            "V6 revalidated frozen V5 inventory and task metadata",
            "V6 scheduler parser transiently parsed per-row Elapsed fields",
            "V7 committed the exact scheduler-only 795/25 partition",
            "V7 created an intent and isolated roots, then its one allowed "
            "sbatch call failed before a job was accepted",
            "a later non-submitting scheduler diagnosis established that "
            "3000G exceeded RealMemory minus MemSpecLimit and that 2950G "
            "was accepted by sbatch --test-only",
        ],
        "not_read_before_v8_freeze": [
            "V5 shard payloads", "V5 environment records",
            "V5 logs", "source-support classifications",
        ],
        "v7_launch_failure_record_sha256": V7_LAUNCH_FAILURE_SHA256,
        "v7_original_submission_stderr_preserved": False,
        "scheduler_cause_reconstructed_post_hoc_with_non_submitting_tests": True,
        "v7_job_accepted": False,
        "v7_task_outputs_used": False,
        "v5_scheduler_diagnosis_repeated_by_v8": False,
        "v8_scheduler_profile_change_from_v7": ["memory 3000G to 2950G"],
        "interpretation": (
            "V8 is prospective with respect to repair and scientific outcome "
            "inspection, but its scheduler-valid memory ceiling was selected "
            "after the disclosed V7 launch rejection"
        ),
    }


def _path_containment_trust_model() -> dict:
    return {
        "controller_exclusive_file_publication": (
            "descriptor-relative-nofollow-with-final-inode-and-byte-recheck"
        ),
        "controller_private_directory_creation": (
            "descriptor-relative-nofollow-with-ancestor-chain-recheck"
        ),
        "task_side_path_operations": (
            "require-no-concurrent-same-uid-pathname-mutator"
        ),
        "active_same_uid_task_path_containment_claimed": False,
    }


def diagnose_v5() -> None:
    """V8 has no V5 diagnosis phase or V5 scheduler-query implementation."""
    raise LaunchAuditError(
        "V8 inherits V7's committed scheduler partition; V5 diagnosis is disabled"
    )


def _load_v7_lineage(*, require_live_manifest: bool) -> tuple[str, dict]:
    """Load V7's immutable scheduler partition without querying V5 again."""
    try:
        digest, value = V7Launch._load_recorded_diagnostic()
    except V7Launch.LaunchAuditError as err:
        raise LaunchAuditError("committed V7 scheduler diagnostic is invalid") from err
    v7_manifest_sha = Runtime._sha256(
        V7Launch.CODE_MANIFEST, "V7 code manifest"
    )
    if require_live_manifest:
        V7Launch.Source.validate_code_manifest(
            V7Launch.CODE_MANIFEST, v7_manifest_sha
        )
    failure_loaded = Runtime._safe_file(
        V7_LAUNCH_FAILURE, "V7 launch failure record", root=REPO
    )
    failure_raw = failure_loaded.raw
    try:
        failure = json.loads(failure_raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise LaunchAuditError("V7 launch failure record is not JSON") from err
    if (
        digest != V7_DIAGNOSTIC_SHA256
        or v7_manifest_sha != V7_CODE_MANIFEST_SHA256
        or set(value) != DIAGNOSTIC_FIELDS
        or value.get("reusable_v5_shard_indices_sha256")
        != "65ce860b4caafc5d2fc714ce7ec1ac8a3a9938be93b87d46e8b46f1f5c96a21d"
        or value.get("repair_v5_shard_indices_sha256")
        != "6f5ec55c78935e47f6414c6edac036d24c93851d4c2bd34dde6a0277ca4c518c"
        or len(value.get("reusable_v5_shard_indices", [])) != 795
        or value.get("repair_v5_shard_indices") != [
            2, 64, 129, 132, 147, 150, 199, 459, 484, 485, 486, 487,
            488, 489, 715, 716, 717, 718, 719, 720, 721, 722, 723, 724,
            725,
        ]
        or hashlib.sha256(failure_raw).hexdigest()
        != V7_LAUNCH_FAILURE_SHA256
        or failure.get("launch_intent_sha256") != V7_INTENT_SHA256
        or failure.get("launch_intent_path") != str(V7_LAUNCH_INTENT)
        or failure.get("original_submission", {}).get("attempts") != 1
        or failure.get("original_submission", {}).get("accepted") is not False
        or failure.get("original_submission", {}).get("stderr_preserved") is not False
        or failure.get("launch_recovery", {}).get("matching_jobs") != 0
        or failure.get("launch_recovery", {}).get("resubmission_performed") is not False
        or failure.get("v7_runtime_namespace", {}).get("task_outputs_created") != 0
        or failure.get("v7_runtime_namespace", {}).get("slurm_logs_created") != 0
        or failure.get("post_failure_scheduler_diagnosis", {}).get(
            "fat_node_allocatable_memory_mib"
        ) != FAT_NODE_ALLOCATABLE_MEMORY_MIB
        or failure.get("post_failure_scheduler_diagnosis", {}).get(
            "corrected_resource_profile_test_only", {}
        ).get("memory") != V8_TOTAL_MEMORY
        or failure.get("scientific_outcomes_consulted_for_diagnosis") is not False
        or failure.get("v5_output_namespace_accessed") is not False
        or failure.get("v5_shards_environment_logs_or_support_read") is not False
        or failure.get("v7_scientific_task_started") is not False
        or Runtime._sha256(V7_LAUNCH_INTENT, "V7 launch intent")
        != V7_INTENT_SHA256
    ):
        raise LaunchAuditError("V7 scheduler-partition lineage changed")
    return digest, value


def _load_diagnostic() -> tuple[str, dict]:
    return _load_v7_lineage(require_live_manifest=True)


def _load_recorded_diagnostic() -> tuple[str, dict]:
    """Load the same immutable V7 scheduler partition for descendants."""
    return _load_v7_lineage(require_live_manifest=False)


def _slurm_template() -> bytes:
    loaded = Runtime._safe_file(SLURM_TEMPLATE, "V8 Slurm template", root=REPO)
    raw = loaded.raw
    lines = raw.splitlines()
    required = {
        b"#!/bin/bash",
        b"set -euo pipefail",
        b'test "$#" -eq 0',
        b'source_inventory_sha256="bb9be49a4652ff7bedcadb04b4db35cad701a5b2a2a6d6347c15e0ad670e056e"',
        b'source_audit_output_dir="' + str(OUTPUT_DIR).encode("ascii") + b'"',
        b'task_timeout_seconds="' + TIMEOUT_PLACEHOLDER + b'"',
        b'test "${task_timeout_seconds}" = "115200"',
        b'[[ "${SLURM_ARRAY_JOB_ID}" =~ ^[0-9]+$ ]]',
        b'[[ "${SLURM_ARRAY_TASK_ID}" =~ ^[0-9]+$ ]]',
        b'test "${SLURM_ARRAY_TASK_ID}" -ge 0',
        b'test "${SLURM_ARRAY_TASK_ID}" -lt 820',
        b"unset PYTHONPATH PYTHONHOME VIRTUAL_ENV",
        b'export PYTHONNOUSERSITE="1"',
        b'export PYTHONDONTWRITEBYTECODE="1"',
        b'export PATH="/usr/bin:/bin"',
        b"cd " + str(REPO).encode("ascii"),
        b'code_manifest="experiments/pdb_terminal_incidence_confirmation_source_audit_v8_code.sha256"',
        b'code_manifest_sha256="' + MANIFEST_PLACEHOLDER + b'"',
        b'source_inventory="experiments/data/pdb_terminal_incidence_confirmation_source_audit_v8_repair/source-inventory-v8.json"',
        b'tmpdir_root="' + str(TMP_ROOT).encode("ascii") + b'"',
        b'python_executable="' + str(V5Launch.PYTHON_COMMAND).encode("ascii") + b'"',
        b'python_executable_sha256="' + Source.Base.PINNED_PYTHON_EXECUTABLE_SHA256.encode("ascii") + b'"',
        b'sha256sum_executable="/usr/bin/sha256sum"',
        b'sha256sum_executable_sha256="' + Source.V5.SHA256SUM_SHA256.encode("ascii") + b'"',
        b'mkdir_executable="/usr/bin/mkdir"',
        b'mkdir_executable_sha256="' + Source.V5.MKDIR_SHA256.encode("ascii") + b'"',
        b'rmdir_executable="/usr/bin/rmdir"',
        b'rmdir_executable_sha256="' + Source.V5.RMDIR_SHA256.encode("ascii") + b'"',
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
        b"trap cleanup_tmpdir EXIT",
        b'"${python_executable}" -B \\',
        b"    experiments/audit_pdb_terminal_incidence_confirmation_sources_v8.py scan \\",
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
        raise LaunchAuditError("V8 Slurm template contract changed")
    return raw


_base_launch_materials = Runtime._launch_materials
_base_submit_command = Runtime._submit_command
_base_prepare_manifest = Runtime.prepare_manifest


def _effective_diagnostic(diagnostic: dict) -> dict:
    """Change only V7's scheduler-invalid memory request for V8 execution."""
    value = copy.deepcopy(diagnostic)
    value["resource_mapping"] = _resource_mapping()
    return value


def _submit_command(diagnostic: dict, token: str) -> list[str]:
    return _base_submit_command(_effective_diagnostic(diagnostic), token)


def _launch_materials(
    diagnostic_sha: str,
    diagnostic: dict,
    *,
    repository_commit_id: str | None = None,
    roots: dict | None = None,
    capture_initial_identities: dict,
) -> dict:
    materials = _base_launch_materials(
        diagnostic_sha, _effective_diagnostic(diagnostic),
        repository_commit_id=repository_commit_id, roots=roots,
    )
    if materials.get("campaign") != "v6-selective-repair":
        raise LaunchAuditError("imported V6 launch-material contract changed")
    materials["campaign"] = "v8-selective-repair"
    materials["source_support_outcome_blind_selective_repair"] = materials.pop(
        "outcome_blind_selective_repair"
    )
    materials["v5_scheduler_diagnostic_sha256"] = materials.pop(
        "v5_terminal_diagnostic_sha256"
    )
    materials.update({
        "reused_v6_shards": 0,
        "reused_v7_shards": 0,
        "scheduler_only_partition": True,
        "v5_failure_logs_inspected_by_v8": False,
        "v5_detailed_accounting_inspected_by_v8": False,
        "source_support_outcomes_used_for_v8_design": False,
        "accepted_translation_statuses": list(ACCEPTED_TRANSLATION_STATUSES),
        "translator_timeout_is_infrastructure_failure": True,
        "resource_ceiling_changes_accepted_outcome_classes": False,
        "source_audit_runtime_estimand_recorded": False,
        "cross_campaign_runtime_comparison_authorized": False,
        "scheduler_membership_affects_execution_origin_only": True,
        "v6_runtime_artifacts_used": False,
        "v5_scheduler_rows_sha256": diagnostic["v5_scheduler_rows_sha256"],
        "v8_design_timing_disclosure": _design_timing_disclosure(),
        "v7_launch_intent_sha256": V7_INTENT_SHA256,
        "v7_launch_failure_sha256": V7_LAUNCH_FAILURE_SHA256,
        "v7_runtime_artifacts_used": False,
        "scheduler_profile_change_from_v7": ["memory 3000G to 2950G"],
        "v5_output_namespace_enumerated_by_v8": False,
        "v5_output_triplet_bytes_read_before_v8_all_success_gate": False,
        "v5_reusable_triplet_read_policy": (
            "only-during-seal-after-v8-all-success-gate"
        ),
        "v5_reusable_selected_tree_commitment_policy": (
            "first-separate-record-at-v8-seal"
        ),
        "v5_source_inventory_read_by_v8": False,
        "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion": (
            False
        ),
        "path_containment_trust_model": _path_containment_trust_model(),
        "sbatch_stdout_path": str(SBATCH_STDOUT),
        "sbatch_stderr_path": str(SBATCH_STDERR),
        "sbatch_result_path": str(SBATCH_RESULT),
        "sbatch_capture_initial_identities": copy.deepcopy(
            _validate_capture_initial_identities(capture_initial_identities)
        ),
    })
    return materials


def _rebuilt_inventory(diagnostic: dict) -> bytes:
    inventory = Inventory.load_inventory()
    value = Source.build_inventory_manifest(inventory)
    raw = Source.canonical_json(value)
    if hashlib.sha256(raw).hexdigest() != diagnostic["v5_source_inventory_sha256"]:
        raise LaunchAuditError("rebuilt frozen source inventory changed")
    return raw


def _parse_sbatch_job_id(raw: bytes) -> str | None:
    try:
        value = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        return None
    match = re.fullmatch(r"([0-9]+)(?:;[A-Za-z0-9_.-]+)?", value)
    return match.group(1) if match is not None else None


def _open_intent_capture_pair(intent: dict, label: str):
    identities = _validate_capture_initial_identities(
        intent.get("sbatch_capture_initial_identities")
    )
    try:
        return SelectedIO.open_existing_capture_pair(
            SBATCH_STDOUT, SBATCH_STDERR, identities,
            root=REPO, label=label,
        )
    except SelectedIO.PublicationError as err:
        raise LaunchAuditError(str(err)) from err


def _load_intent_only() -> tuple[bytes, dict, str, dict]:
    """Authenticate the intent and its exact crash-left capture inodes."""
    raw, intent = Runtime._load_json(INTENT, "V8 launch intent")
    identities = _validate_capture_initial_identities(
        intent.get("sbatch_capture_initial_identities")
        if type(intent) is dict else None
    )
    diagnostic_sha, diagnostic = _load_diagnostic()
    materials = _launch_materials(
        diagnostic_sha, diagnostic,
        repository_commit_id=intent.get("repository_commit_id"),
        roots=intent.get("launch_root_identities"),
        capture_initial_identities=identities,
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
        raise LaunchAuditError("V8 launch intent changed")
    with _open_intent_capture_pair(intent, "V8 sbatch capture"):
        pass
    return raw, intent, diagnostic_sha, diagnostic


def _publish_sbatch_result(
    intent_raw: bytes,
    intent: dict,
    rendered: bytes,
    capture_records: dict[str, dict],
    capture_payloads: dict[str, bytes],
    *,
    completed: subprocess.CompletedProcess | None,
    error: OSError | None,
    recovered: bool,
) -> tuple[str, dict]:
    _validate_final_capture_records(intent, capture_records, capture_payloads)
    if (
        hashlib.sha256(rendered).hexdigest()
        != intent.get("slurm_program_sha256")
    ):
        raise LaunchAuditError("V8 sbatch capture publication input changed")
    if recovered:
        if completed is not None or error is not None:
            raise LaunchAuditError("V8 recovered process observation changed")
        kind = "controller-crash-returncode-unavailable"
        returncode = None
        error_type = None
        error_errno = None
    elif completed is not None and error is None:
        kind = "completed-process"
        returncode = completed.returncode
        if type(returncode) is not int:
            raise LaunchAuditError("V8 sbatch return code changed")
        error_type = None
        error_errno = None
    elif completed is None and isinstance(error, OSError):
        kind = "os-error"
        returncode = None
        error_type = type(error).__name__
        error_errno = error.errno
    else:
        raise LaunchAuditError("V8 sbatch process observation changed")
    stdout = capture_payloads["stdout"]
    parsed = _parse_sbatch_job_id(stdout) if (
        recovered or returncode == 0
    ) else None
    accepted = (
        kind == "completed-process"
        and returncode == 0
        and parsed is not None
    )
    result = {
        "schema": SBATCH_RESULT_SCHEMA,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "submit_command_sha256": _digest(intent["submit_command"]),
        "slurm_program_sha256": hashlib.sha256(rendered).hexdigest(),
        "capture_protocol": (
            "pre-intent-o-excl-nofollow-sealed-0400-retained-fd-flock-v1"
        ),
        "process_observation": {
            "kind": kind,
            "returncode": returncode,
            "os_error_type": error_type,
            "os_error_errno": error_errno,
        },
        "stdout": capture_records["stdout"],
        "stderr": capture_records["stderr"],
        "parsed_job_id": parsed,
        "accepted_by_launcher": accepted,
        "raw_streams_preserved": True,
    }
    digest = Runtime._exclusive_json(SBATCH_RESULT, result, "V8 sbatch result")
    return digest, result


def _read_capture_pair(intent: dict) -> tuple[dict[str, dict], dict[str, bytes]]:
    with _open_intent_capture_pair(intent, "V8 sbatch capture") as captures:
        try:
            return captures.finalize()
        except SelectedIO.PublicationError as err:
            raise LaunchAuditError(str(err)) from err


def _load_sbatch_result(intent_raw: bytes, intent: dict) -> tuple[str, dict]:
    raw, result = Runtime._load_json(SBATCH_RESULT, "V8 sbatch result")
    records, payloads = _read_capture_pair(intent)
    process = result.get("process_observation") if type(result) is dict else None
    kind = process.get("kind") if type(process) is dict else None
    returncode = process.get("returncode") if type(process) is dict else None
    if kind == "controller-crash-returncode-unavailable":
        parsed_expected = _parse_sbatch_job_id(payloads["stdout"])
    elif kind == "completed-process" and returncode == 0:
        parsed_expected = _parse_sbatch_job_id(payloads["stdout"])
    else:
        parsed_expected = None
    if (
        type(result) is not dict
        or set(result) != {
            "schema", "launch_intent_sha256", "submit_command_sha256",
            "slurm_program_sha256", "capture_protocol",
            "process_observation", "stdout", "stderr", "parsed_job_id",
            "accepted_by_launcher", "raw_streams_preserved",
        }
        or result.get("schema") != SBATCH_RESULT_SCHEMA
        or result.get("launch_intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or result.get("submit_command_sha256") != _digest(intent["submit_command"])
        or result.get("slurm_program_sha256") != intent["slurm_program_sha256"]
        or result.get("capture_protocol")
        != "pre-intent-o-excl-nofollow-sealed-0400-retained-fd-flock-v1"
        or result.get("stdout") != records["stdout"]
        or result.get("stderr") != records["stderr"]
        or type(process) is not dict
        or set(process) != {
            "kind", "returncode", "os_error_type", "os_error_errno",
        }
        or not (
            (
                kind == "completed-process"
                and type(returncode) is int
                and process.get("os_error_type") is None
                and process.get("os_error_errno") is None
            )
            or (
                kind == "os-error"
                and returncode is None
                and isinstance(process.get("os_error_type"), str)
                and bool(process.get("os_error_type"))
                and (
                    process.get("os_error_errno") is None
                    or type(process.get("os_error_errno")) is int
                )
            )
            or (
                kind == "controller-crash-returncode-unavailable"
                and returncode is None
                and process.get("os_error_type") is None
                and process.get("os_error_errno") is None
            )
        )
        or result.get("parsed_job_id") != parsed_expected
        or result.get("accepted_by_launcher") != (
            kind == "completed-process"
            and returncode == 0
            and parsed_expected is not None
        )
        or result.get("raw_streams_preserved") is not True
    ):
        raise LaunchAuditError("V8 sbatch result changed")
    return hashlib.sha256(raw).hexdigest(), result


def _ensure_recovery_sbatch_result(
    intent_raw: bytes, intent: dict, rendered: bytes,
) -> tuple[str, dict]:
    if os.path.lexists(SBATCH_RESULT):
        return _load_sbatch_result(intent_raw, intent)
    with _open_intent_capture_pair(
        intent, "V8 crash-left sbatch capture"
    ) as captures:
        try:
            records, payloads = captures.finalize()
        except SelectedIO.PublicationError as err:
            raise LaunchAuditError(str(err)) from err
        return _publish_sbatch_result(
            intent_raw, intent, rendered, records, payloads,
            completed=None, error=None, recovered=True,
        )


def _write_launch_receipt(
    intent_raw: bytes, intent: dict, job_id: str, *, recovered: bool,
) -> str:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("Slurm returned an invalid V8 job id")
    if not os.path.lexists(SBATCH_RESULT):
        raise LaunchAuditError("V8 launch lacks sbatch result")
    result_sha, result = _load_sbatch_result(intent_raw, intent)
    if (
        not recovered
        and (
            result.get("accepted_by_launcher") is not True
            or result.get("parsed_job_id") != job_id
        )
    ) or (
        recovered
        and result.get("parsed_job_id") is not None
        and result.get("parsed_job_id") != job_id
    ):
        raise LaunchAuditError("V8 sbatch result and job identity disagree")
    receipt = {
        "schema": LAUNCH_SCHEMA,
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "sbatch_result_sha256": result_sha,
        "launch_recovered_from_journal": recovered,
        "job_id": job_id,
    }
    return Runtime._exclusive_json(LAUNCH_RECEIPT, receipt, "V8 launch receipt")


def _load_launch() -> tuple[str, dict, dict]:
    intent_raw, intent, _diagnostic_sha, diagnostic = _load_intent_only()
    raw, receipt = Runtime._load_json(LAUNCH_RECEIPT, "V8 launch receipt")
    if not os.path.lexists(SBATCH_RESULT):
        raise LaunchAuditError("V8 launch receipt lacks sbatch result")
    result_sha, result = _load_sbatch_result(intent_raw, intent)
    expected = {
        "schema": LAUNCH_SCHEMA,
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "sbatch_result_sha256": result_sha,
        "launch_recovered_from_journal": receipt.get(
            "launch_recovered_from_journal"
        ),
        "job_id": receipt.get("job_id"),
    }
    recovered = receipt.get("launch_recovered_from_journal")
    job_id = receipt.get("job_id")
    if (
        receipt != expected
        or type(recovered) is not bool
        or not isinstance(job_id, str)
        or not job_id.isdigit()
        or (
            not recovered
            and (
                result.get("accepted_by_launcher") is not True
                or result.get("parsed_job_id") != job_id
            )
        )
        or (
            recovered
            and result.get("parsed_job_id") is not None
            and result.get("parsed_job_id") != job_id
        )
        or Runtime._journal_job_ids(
            intent, diagnostic["repair_v5_shard_indices"]
        ) != [job_id]
    ):
        raise LaunchAuditError("V8 launch receipt changed")
    return hashlib.sha256(raw).hexdigest(), receipt, diagnostic


def _recover_launch() -> None:
    if os.path.lexists(LAUNCH_RECEIPT):
        raise LaunchAuditError("V8 launch receipt already exists")
    raw, intent, _sha, diagnostic = _load_intent_only()
    rendered = Runtime._render_slurm(
        intent["code_manifest_sha256"],
        diagnostic["resource_mapping"]["task_timeout_seconds"],
    )
    result_sha, _result = _ensure_recovery_sbatch_result(
        raw, intent, rendered
    )
    jobs = Runtime._journal_job_ids(
        intent, diagnostic["repair_v5_shard_indices"]
    )
    if len(jobs) != 1:
        raise LaunchAuditError(
            "journal identifies {} V8 jobs; refusing resubmission; "
            "raw streams are bound by {}".format(len(jobs), result_sha)
        )
    digest = _write_launch_receipt(raw, intent, jobs[0], recovered=True)
    print(json.dumps({
        "job_id": jobs[0],
        "launch_receipt_reconstructed": True,
        "launch_receipt_sha256": digest,
        "sbatch_result_sha256": result_sha,
    }, sort_keys=True, indent=2))


def launch() -> None:
    if any(os.path.lexists(path) for path in (
        INTENT, SBATCH_STDOUT, SBATCH_STDERR, SBATCH_RESULT,
        LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR, TMP_ROOT,
        UNION_DIR, CANDIDATE, ATTESTATION, *SEAL_STAGE_ARTIFACTS,
    )):
        raise LaunchAuditError("V8 launch namespace is not empty")
    diagnostic_sha, diagnostic = _load_diagnostic()
    repository_commit_id = Runtime._scoped_repository_commit()
    manifest_sha = Runtime._sha256(CODE_MANIFEST, "V8 code manifest")
    Source.configure(V8_TASK_TIMEOUT_SECONDS)
    Source.validate_code_manifest(CODE_MANIFEST, manifest_sha)
    Runtime._validate_freeze_against_manifest(
        diagnostic["pre_diagnosis_freeze"], CODE_MANIFEST, manifest_sha
    )
    Runtime._render_slurm(manifest_sha, V8_TASK_TIMEOUT_SECONDS)
    inventory_raw = _rebuilt_inventory(diagnostic)
    output_identity = Runtime._create_private_directory(
        OUTPUT_DIR, "V8 output directory"
    )
    tmp_identity = Runtime._create_private_directory(
        TMP_ROOT, "V8 TMPDIR root"
    )
    roots = {"output_dir": output_identity, "tmpdir_root": tmp_identity}
    Runtime._exclusive_bytes(SOURCE_INVENTORY, inventory_raw, "V8 source inventory")
    try:
        capture_context = SelectedIO.open_exclusive_capture_pair(
            SBATCH_STDOUT, SBATCH_STDERR, root=REPO,
            label="V8 sbatch capture",
        )
    except SelectedIO.PublicationError as err:
        raise LaunchAuditError(str(err)) from err
    with capture_context as captures:
        materials = _launch_materials(
            diagnostic_sha, diagnostic,
            repository_commit_id=repository_commit_id, roots=roots,
            capture_initial_identities=captures.initial_identities,
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
        Runtime._exclusive_json(INTENT, intent, "V8 launch intent")
        rendered = Runtime._render_slurm(
            manifest_sha, V8_TASK_TIMEOUT_SECONDS
        )
        if (
            hashlib.sha256(rendered).hexdigest()
            != materials["slurm_program_sha256"]
            or len(rendered) != materials["slurm_program_bytes"]
        ):
            raise LaunchAuditError(
                "V8 rendered Slurm bytes changed before submission"
            )
        Runtime._executable_identity(
            SBATCH_COMMAND, SBATCH_COMMAND_SHA256, "sbatch"
        )
        try:
            captures.verify_initial()
        except SelectedIO.PublicationError as err:
            raise LaunchAuditError(str(err)) from err
        completed = None
        error = None
        try:
            completed = subprocess.run(
                command, input=rendered,
                stdout=captures.stdout_fd, stderr=captures.stderr_fd,
                cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), check=False,
            )
        except OSError as err:
            error = err
        try:
            records, payloads = captures.finalize()
        except SelectedIO.PublicationError as err:
            raise LaunchAuditError(str(err)) from err
        result_sha, result = _publish_sbatch_result(
            intent_raw, intent, rendered, records, payloads,
            completed=completed, error=error, recovered=False,
        )
        if result["accepted_by_launcher"] is not True:
            raise LaunchAuditError(
                "V8 sbatch was not accepted; raw streams are bound by "
                + result_sha
            )
        job_id = result["parsed_job_id"]
    digest = _write_launch_receipt(
        intent_raw, intent, job_id, recovered=False
    )
    print(json.dumps({
        "job_id": job_id,
        "launch_receipt_sha256": digest,
        "repair_v5_shard_indices": diagnostic["repair_v5_shard_indices"],
    }, sort_keys=True, indent=2))


def _v8_scheduler_rows(job_id: str, expected: list[int]) -> list[dict]:
    if (
        not isinstance(job_id, str)
        or not job_id.isdigit()
        or type(expected) is not list
        or not expected
        or expected != sorted(set(expected))
        or any(type(index) is not int or not 0 <= index < ARRAY_TASKS
               for index in expected)
    ):
        raise LaunchAuditError("V8 scheduler query is invalid")
    output = Runtime._sacct([
        str(SACCT_COMMAND), "-j", job_id, "-X", "--array", "-n", "-P",
        "--format=JobID,State,ExitCode,Partition",
    ])
    lines = output.splitlines()
    if len(lines) != len(expected):
        raise LaunchAuditError("V8 accounting task cardinality changed")
    rows = []
    for index, line in zip(expected, lines):
        fields = line.split("|")
        if len(fields) != 4:
            raise LaunchAuditError("V8 accounting row changed")
        task_id, state, exit_code, partition = fields
        if (
            task_id != "{}_{}".format(job_id, index)
            or state not in TERMINAL_ACCOUNTING_STATES | ACTIVE_STATES
            or not _matches(EXIT_CODE_RE, exit_code)
            or partition != PARTITION
        ):
            raise LaunchAuditError("V8 accounting field changed")
        rows.append({
            "array_task": index, "state": state,
            "exit_code": exit_code, "partition": partition,
        })
    return rows


def status() -> tuple[str, dict, dict, list[dict]]:
    launch_sha, launch_receipt, diagnostic = Runtime._load_launch()
    rows = _v8_scheduler_rows(
        launch_receipt["job_id"], diagnostic["repair_v5_shard_indices"]
    )
    print(json.dumps({
        "job_id": launch_receipt["job_id"],
        "state_counts": dict(Counter(row["state"] for row in rows)),
    }, sort_keys=True, indent=2))
    return launch_sha, launch_receipt, diagnostic, rows


def _scheduler_contract_rows(
    launch_receipt: dict, diagnostic: dict, rows: list[dict]
) -> list[dict]:
    """Read detailed V8 resources only after the all-success row gate."""
    repair = diagnostic["repair_v5_shard_indices"]
    if (
        len(rows) != len(repair)
        or any(row.get("state") != "COMPLETED" or row.get("exit_code") != "0:0"
               for row in rows)
    ):
        raise LaunchAuditError("V8 success gate must precede resource accounting")
    output = Runtime._sacct([
        str(SACCT_COMMAND), "-j", launch_receipt["job_id"], "-X", "--array",
        "-n", "-P", "--format=JobID,Account,Partition,QOS,ReqCPUS,ReqMem,"
        "Timelimit,Elapsed,State,ExitCode,JobName",
    ])
    lines = output.splitlines()
    if len(lines) != len(repair):
        raise LaunchAuditError("V8 resource accounting cardinality changed")
    expected_name, _ = Runtime._submission_identity(
        launch_receipt["submission_token"]
    )
    result = []
    for index, row, line in zip(repair, rows, lines):
        fields = line.split("|")
        if len(fields) != 11:
            raise LaunchAuditError("V8 resource accounting row changed")
        (task_id, account, partition, qos, cpus, memory, time_limit,
         elapsed, state, exit_code, job_name) = fields
        if (
            task_id != "{}_{}".format(launch_receipt["job_id"], index)
            or account != ACCOUNT or partition != PARTITION or qos != QOS
            or cpus != "1" or memory != V8_TOTAL_MEMORY
            or time_limit != V8_TIME_LIMIT
            or not Runtime._valid_elapsed(elapsed)
            or state != row["state"] or exit_code != row["exit_code"]
            or state != "COMPLETED" or exit_code != "0:0"
            or job_name != expected_name
        ):
            raise LaunchAuditError("V8 actual resource contract changed")
        result.append({
            "array_task": index, "account": account,
            "partition": partition, "qos": qos, "req_cpus": 1,
            "req_mem": memory, "time_limit": time_limit,
            "elapsed": elapsed, "state": state, "exit_code": exit_code,
            "job_name": job_name,
        })
    return result


def _root_identity_from_selected(root: Path, tree, expected: dict) -> dict:
    info = tree.root_identity
    actual = {
        "path": str(root), "canonical_path": str(root),
        "device": info["device"], "inode": info["inode"],
        "mode": "0700", "uid": info["uid"],
    }
    if (
        not stat.S_ISDIR(info["mode"])
        or stat.S_IMODE(info["mode"]) != 0o700
        or actual != expected
    ):
        raise LaunchAuditError("V5 reusable output root identity changed")
    return actual


def _v5_reusable_names(diagnostic: dict) -> tuple[str, ...]:
    job_id = diagnostic["v5_launch_receipt"]["job_id"]
    names = []
    for index in diagnostic["reusable_v5_shard_indices"]:
        names.extend((
            V5Source.shard_path(V5_OUTPUT_DIR, index).name,
            V5Source.task_environment_path(V5_OUTPUT_DIR, index).name,
            "slurm-{}_{}.out".format(job_id, index),
        ))
    return tuple(sorted(names))


def _v5_reusable_tree(diagnostic: dict, *, read_callback=None) -> dict:
    names = _v5_reusable_names(diagnostic)
    try:
        tree = SelectedIO.read_selected_flat_tree(
            V5_OUTPUT_DIR, names, label="V5 reusable triplets",
            expected_path=V5_OUTPUT_DIR, read_callback=read_callback,
        )
    except SelectedIO.SelectedTreeError as err:
        raise LaunchAuditError(str(err)) from err
    root = _root_identity_from_selected(
        V5_OUTPUT_DIR, tree,
        diagnostic["v5_launch_receipt"]["launch_root_identities"]["output_dir"],
    )
    records = [
        {"path": item.path, "bytes": item.identity["size"],
         "sha256": item.sha256}
        for item in tree.files
    ]
    digest = hashlib.sha256()
    digest.update(b"root-identity\0" + _canonical_json(root))
    for item in records:
        digest.update(item["path"].encode("ascii") + b"\0"
                      + bytes.fromhex(item["sha256"]))
    return {
        "sha256": digest.hexdigest(), "root_identity": root,
        "files_count": len(records), "files": records,
        "selection_rule": "V5 scheduler COMPLETED 0:0 triplets only",
        "noncompleted_v5_files_opened": False,
    }


def _manifest_file_map(manifest: dict) -> dict[str, dict]:
    return {item["path"]: item for item in manifest["files"]}


def _validate_accepted_translation_records(
    tasks_by_shard: dict[int, list[dict]], indices: list[int],
    expected_timeout_seconds: int, label: str,
) -> None:
    """Keep infrastructure ceilings outside the accepted record classes."""
    if set(tasks_by_shard) != set(indices):
        raise LaunchAuditError("{} shard set changed".format(label))
    for index in indices:
        tasks = tasks_by_shard[index]
        if type(tasks) is not list or len(tasks) != Source.TASKS_PER_SHARD:
            raise LaunchAuditError("{} shard cardinality changed".format(label))
        for task in tasks:
            translation = task.get("translation") if isinstance(task, dict) else None
            if (
                type(translation) is not dict
                or translation.get("status") not in ACCEPTED_TRANSLATION_STATUSES
                or translation.get("timeout_seconds")
                != expected_timeout_seconds
            ):
                raise LaunchAuditError(
                    "{} contains a nonaccepted translation outcome".format(label)
                )


def _validate_attestation_translation_statuses(value: dict) -> None:
    counts = value.get("translation_status_counts")
    if (
        type(counts) is not dict
        or not set(counts) <= set(ACCEPTED_TRANSLATION_STATUSES)
        or any(type(count) is not int or count < 0 for count in counts.values())
        or sum(counts.values()) != Source.CANDIDATE_COUNT
    ):
        raise LaunchAuditError(
            "V8 attestation contains a nonaccepted translation outcome"
        )


def _expected_success_log(
    inventory: list[dict], index: int, output_dir: Path,
    manifest_paths: tuple[str, ...],
) -> bytes:
    start = index * Source.TASKS_PER_SHARD
    records = inventory[start:start + Source.TASKS_PER_SHARD]
    if len(records) != Source.TASKS_PER_SHARD:
        raise LaunchAuditError("success-log inventory slice changed")
    lines = ["{}: OK".format(path) for path in manifest_paths]
    lines.extend(
        "[{}/{}] {}:{}".format(
            position, Source.TASKS_PER_SHARD,
            record["directory"], record["problem"],
        )
        for position, record in enumerate(records, 1)
    )
    lines.append("wrote {}".format(V5Source.shard_path(output_dir, index)))
    try:
        return ("\n".join(lines) + "\n").encode("ascii")
    except (KeyError, UnicodeEncodeError) as err:
        raise LaunchAuditError("success-log inventory record changed") from err


def _read_v5_reusable_triplets(
    diagnostic: dict,
) -> tuple[dict, dict[int, list[dict]], dict]:
    """Parse selected bytes inside the descriptor-stable streaming window."""
    launch_receipt = diagnostic["v5_launch_receipt"]
    try:
        code = V5Source.validate_code_manifest(
            V5_CODE_MANIFEST, launch_receipt["code_manifest_sha256"]
        )
        manifest_raw = V5Source._safe_file(
            V5_CODE_MANIFEST, "V5 code manifest",
            expected_path=V5_CODE_MANIFEST, root=REPO,
        ).raw
        manifest_paths = tuple(
            line.split("  ", 1)[1]
            for line in manifest_raw.decode("ascii").splitlines()
        )
        if (
            len(manifest_paths) != len(V5Source.CODE_MANIFEST_FILES)
            or set(manifest_paths) != set(V5Source.CODE_MANIFEST_FILES)
        ):
            raise V5Source.SourceAuditError("V5 manifest log paths changed")
        _inventory_sha, inventory = V5Source.load_inventory_manifest(
            SOURCE_INVENTORY, launch_receipt["source_inventory_sha256"]
        )
    except (V5Source.SourceAuditError, UnicodeDecodeError, IndexError) as err:
        raise LaunchAuditError("V5 reusable provenance is invalid") from err
    tasks_by_shard = {}
    environment_values = {}
    raw_sha256 = {}

    def validate_selected(read_selected):
        cached = {}
        for index in diagnostic["reusable_v5_shard_indices"]:
            for path in (
                V5Source.shard_path(V5_OUTPUT_DIR, index),
                V5Source.task_environment_path(V5_OUTPUT_DIR, index),
            ):
                raw = read_selected(path.name)
                try:
                    value = json.loads(raw.decode("ascii"))
                except (UnicodeDecodeError, json.JSONDecodeError) as err:
                    raise LaunchAuditError(
                        "V5 reusable JSON is malformed"
                    ) from err
                if V5Source.Base.canonical_json(value) != raw:
                    raise LaunchAuditError("V5 reusable JSON is not canonical")
                cached[path.name] = (raw, value)
                raw_sha256[path.name] = hashlib.sha256(raw).hexdigest()
            log_name = "slurm-{}_{}.out".format(
                launch_receipt["job_id"], index
            )
            log_raw = read_selected(log_name)
            if log_raw != _expected_success_log(
                inventory, index, V5_OUTPUT_DIR, manifest_paths
            ):
                raise LaunchAuditError(
                    "V5 reusable success log is inconsistent with its shard"
                )
            raw_sha256[log_name] = hashlib.sha256(log_raw).hexdigest()

        original_loader = V5Source.Base._load_canonical_json

        def load_selected(path: Path, _label: str):
            item = cached.get(Path(path).name)
            if item is None:
                raise V5Source.SourceAuditError(
                    "V5 validator requested an unselected file"
                )
            return item

        V5Source.Base._load_canonical_json = load_selected
        try:
            for index in diagnostic["reusable_v5_shard_indices"]:
                start = index * Source.TASKS_PER_SHARD
                shard = V5Source.shard_path(V5_OUTPUT_DIR, index)
                environment = V5Source.task_environment_path(
                    V5_OUTPUT_DIR, index
                )
                try:
                    tasks = V5Source._load_shard(
                        shard, index,
                        inventory[start:start + Source.TASKS_PER_SHARD],
                        launch_receipt["source_inventory_sha256"], code,
                    )
                    value = V5Source.load_task_environment_attestation(
                        environment, index=index,
                        array_job_id=launch_receipt["job_id"],
                        inventory_sha256=launch_receipt[
                            "source_inventory_sha256"
                        ],
                        code_manifest_sha256=launch_receipt[
                            "code_manifest_sha256"
                        ],
                        code=code,
                        shard_sha256=raw_sha256[shard.name],
                    )
                    if (
                        value["output_dir_identity_after"]
                        != launch_receipt[
                            "launch_root_identities"
                        ]["output_dir"]
                        or value["tmpdir_root_identity_after"]
                        != launch_receipt[
                            "launch_root_identities"
                        ]["tmpdir_root"]
                    ):
                        raise V5Source.SourceAuditError(
                            "V5 reusable roots changed"
                        )
                except (V5Source.SourceAuditError, KeyError) as err:
                    raise LaunchAuditError(
                        "scheduler-reusable V5 task {} has an invalid triplet"
                        .format(index)
                    ) from err
                tasks_by_shard[index] = tasks
                environment_values[index] = value
        finally:
            V5Source.Base._load_canonical_json = original_loader

    selected_tree = _v5_reusable_tree(
        diagnostic, read_callback=validate_selected
    )
    files = _manifest_file_map(selected_tree)
    environments = []
    for index in diagnostic["reusable_v5_shard_indices"]:
        shard = V5Source.shard_path(V5_OUTPUT_DIR, index)
        environment = V5Source.task_environment_path(V5_OUTPUT_DIR, index)
        log_name = "slurm-{}_{}.out".format(launch_receipt["job_id"], index)
        value = environment_values[index]
        if (
            files.get(shard.name, {}).get("sha256") != raw_sha256[shard.name]
            or files.get(environment.name, {}).get("sha256")
            != raw_sha256[environment.name]
            or files.get(log_name, {}).get("sha256") != raw_sha256[log_name]
        ):
            raise LaunchAuditError("V5 reusable streamed triplet changed")
        environments.append({
            "array_task": index, "environment_path": environment.name,
            "environment_sha256": files[environment.name]["sha256"],
            "shard_path": shard.name,
            "shard_sha256": files[shard.name]["sha256"],
            "slurm_log_path": log_name,
            "slurm_log_sha256": files[log_name]["sha256"],
            "tmpdir": value["tmpdir"],
            "output_dir_identity": value["output_dir_identity_after"],
        })
    return selected_tree, tasks_by_shard, {
        "records": environments,
        "records_sha256": _digest(environments),
        "strict_completed_triplet_validation": True,
        "noncompleted_v5_files_opened": False,
    }


def _prepare_union(
    diagnostic: dict, v5_tree: dict, v8_tree: dict, plan_sha256: str,
    *, recovery: bool,
) -> tuple[str, dict]:
    root_stage_sha, root_stage = Runtime._ensure_union_root(
        plan_sha256, recovery=recovery
    )
    partial = Runtime._union_tree(root_stage["root_identity"], complete=False)
    partial_names = {item["path"] for item in partial["files"]}
    expected_names = set(Runtime._expected_union_names())
    if not partial_names <= expected_names:
        raise LaunchAuditError("V8 union contains an unexpected partial shard")
    v5_files = _manifest_file_map(v5_tree)
    v8_files = _manifest_file_map(v8_tree)
    reusable = set(diagnostic["reusable_v5_shard_indices"])
    sources = []
    for index in range(ARRAY_TASKS):
        if index in reusable:
            source = V5Source.shard_path(V5_OUTPUT_DIR, index)
            origin = "v5-completed"
            frozen = v5_files.get(source.name)
        else:
            source = Source.shard_path(OUTPUT_DIR, index)
            origin = "v8-repair"
            frozen = v8_files.get(source.name)
        if frozen is None:
            raise LaunchAuditError("V8 union source is absent from frozen tree")
        target = Source.shard_path(UNION_DIR, index)
        target_sha = Runtime._copy_or_validate_union_shard(
            source, target, frozen
        )
        sources.append({
            "shard_index": index, "origin": origin,
            "source": str(source), "source_sha256": frozen["sha256"],
            "union": target.name, "union_sha256": target_sha,
        })
    union_tree = Runtime._union_tree(root_stage["root_identity"], complete=True)
    stage = {
        "schema": UNION_STAGE_SCHEMA,
        "seal_plan_sha256": plan_sha256,
        "union_root_stage_sha256": root_stage_sha,
        "sources": sources, "sources_sha256": _digest(sources),
        "tree": union_tree,
    }
    return Runtime._publish_or_validate_json(
        UNION_STAGE, stage, "V8 union stage"
    ), stage


def _seal_context() -> dict:
    launch_sha, launch_receipt, diagnostic, rows = status()
    # The gate must precede every V5/V8 shard, environment, or log access.
    if any(
        row["state"] != "COMPLETED" or row["exit_code"] != "0:0"
        for row in rows
    ):
        raise LaunchAuditError("V8 repair array is not entirely successful")
    contract = _scheduler_contract_rows(launch_receipt, diagnostic, rows)
    v5_tree, v5_tasks, v5_environments = _read_v5_reusable_triplets(
        diagnostic
    )
    _validate_accepted_translation_records(
        v5_tasks, diagnostic["reusable_v5_shard_indices"],
        V5_TASK_TIMEOUT_SECONDS, "V5 reusable records",
    )
    v8_tree = Runtime._v6_output_tree(launch_receipt, diagnostic)
    v8_tasks, v8_environments = Runtime._validate_v6_repair_shards(
        launch_receipt, diagnostic, v8_tree
    )
    _validate_accepted_translation_records(
        v8_tasks, diagnostic["repair_v5_shard_indices"],
        V8_TASK_TIMEOUT_SECONDS, "V8 repair records",
    )
    record_sha = Runtime._source_record_sequence_sha256(
        diagnostic, v5_tasks, v8_tasks
    )
    plan = {
        "schema": SEAL_PLAN_SCHEMA,
        "launch_receipt_sha256": launch_sha,
        "v5_scheduler_diagnostic_sha256": launch_receipt[
            "v5_scheduler_diagnostic_sha256"
        ],
        "pre_diagnosis_files_sha256": diagnostic[
            "pre_diagnosis_freeze"
        ]["files_sha256"],
        "scheduler_rows": rows,
        "scheduler_contract_rows": contract,
        "v5_reusable_tree": v5_tree,
        "v8_output_tree": v8_tree,
        "v5_reusable_environment_manifest": v5_environments,
        "v8_repair_environment_manifest": v8_environments,
        "source_record_count": Source.CANDIDATE_COUNT,
        "source_record_sequence_sha256": record_sha,
    }
    return {
        "launch_sha": launch_sha, "launch": launch_receipt,
        "diagnostic": diagnostic, "rows": rows, "contract": contract,
        "v5_tree": v5_tree, "v8_tree": v8_tree,
        "v5_environments": v5_environments,
        "v8_environments": v8_environments, "plan": plan,
    }


def _final_tree_rehash(context: dict, union_root_stage: dict, union_stage: dict):
    if _v5_reusable_tree(context["diagnostic"]) != context["v5_tree"]:
        raise LaunchAuditError("V5 reusable bytes changed before V8 receipt")
    if Runtime._v6_output_tree(
        context["launch"], context["diagnostic"]
    ) != context["v8_tree"]:
        raise LaunchAuditError("V8 repair output changed before receipt")
    if Runtime._union_tree(
        union_root_stage["root_identity"], complete=True
    ) != union_stage["tree"]:
        raise LaunchAuditError("V8 union changed before receipt")


def _execution_receipt(
    context: dict, *, plan_sha256: str, union_root_stage_sha256: str,
    union_stage_sha256: str, union_stage: dict,
    candidate_stage_sha256: str, attestation_stage_sha256: str,
    attestation_sha256: str, value: dict,
) -> dict:
    launch_receipt = context["launch"]
    diagnostic = context["diagnostic"]
    rows = context["rows"]
    _validate_attestation_translation_statuses(value)
    return {
        "schema": EXECUTION_SCHEMA,
        "campaign": "v8-selective-repair",
        "benchmark_revision": launch_receipt["benchmark_revision"],
        "logical_shards": ARRAY_TASKS,
        "candidates": Source.CANDIDATE_COUNT,
        "whole_campaign_rerun": False,
        "source_support_outcome_blind_selective_repair": True,
        "noncompleted_v5_shards_used": False,
        "noncompleted_v5_files_opened": False,
        "v5_noncompleted_failure_logs_inspected": False,
        "v5_failure_detailed_accounting_inspected": False,
        "v8_success_resource_accounting_recorded": True,
        "source_support_outcomes_used_for_v8_design": False,
        "accepted_translation_statuses": list(ACCEPTED_TRANSLATION_STATUSES),
        "translator_timeout_is_infrastructure_failure": True,
        "resource_ceiling_changes_accepted_outcome_classes": False,
        "source_audit_runtime_estimand_recorded": False,
        "cross_campaign_runtime_comparison_authorized": False,
        "scheduler_membership_affects_execution_origin_only": True,
        "v6_runtime_artifacts_used": False,
        "v7_runtime_artifacts_used": False,
        "v8_design_timing_disclosure": _design_timing_disclosure(),
        "v7_launch_intent_sha256": V7_INTENT_SHA256,
        "v7_launch_failure_sha256": V7_LAUNCH_FAILURE_SHA256,
        "sbatch_result_sha256": launch_receipt["sbatch_result_sha256"],
        "v5_output_namespace_enumerated_by_v8": False,
        "v5_output_triplet_bytes_read_before_v8_all_success_gate": False,
        "v5_reusable_triplet_bytes_read_during_seal_after_v8_all_success_gate": (
            True
        ),
        "v5_source_inventory_read_by_v8": False,
        "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion": (
            False
        ),
        "v5_reusable_selected_tree_first_separately_recorded_at_v8_seal": True,
        "path_containment_trust_model": _path_containment_trust_model(),
        "reuse_eligibility_rule": diagnostic["reuse_eligibility_rule"],
        "repair_eligibility_rule": diagnostic["repair_eligibility_rule"],
        "pre_diagnosis_freeze": diagnostic["pre_diagnosis_freeze"],
        "seal_recovery_protocol": "deterministic-exclusive-hash-chain-v1",
        "seal_plan_sha256": plan_sha256,
        "union_root_stage_sha256": union_root_stage_sha256,
        "union_stage_sha256": union_stage_sha256,
        "candidate_stage_sha256": candidate_stage_sha256,
        "attestation_stage_sha256": attestation_stage_sha256,
        "launch_receipt_sha256": context["launch_sha"],
        "v5_scheduler_diagnostic_sha256": launch_receipt[
            "v5_scheduler_diagnostic_sha256"
        ],
        "v5_launch_receipt_sha256": diagnostic["v5_launch_receipt_sha256"],
        "v5_job_id": diagnostic["v5_launch_receipt"]["job_id"],
        "v8_job_id": launch_receipt["job_id"],
        "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "reused_v6_shards": 0, "reused_v7_shards": 0,
        "reused_v5_shards": len(diagnostic["reusable_v5_shard_indices"]),
        "reusable_v5_shard_indices": diagnostic["reusable_v5_shard_indices"],
        "repaired_v5_shards": len(diagnostic["repair_v5_shard_indices"]),
        "repair_v5_shard_indices": diagnostic["repair_v5_shard_indices"],
        "repair_scope": "complete original two-candidate shards",
        "array_throttle": 0,
        "resource_mapping": launch_receipt["resource_mapping"],
        "scheduler_state_counts": {"COMPLETED": len(rows)},
        "scheduler_rows": rows,
        "scheduler_contract_rows": context["contract"],
        "v5_reusable_tree": context["v5_tree"],
        "v8_output_tree": context["v8_tree"],
        "v5_reusable_environment_manifest": context["v5_environments"],
        "v8_repair_environment_manifest": context["v8_environments"],
        "union_sources": union_stage["sources"],
        "union_sources_sha256": union_stage["sources_sha256"],
        "union_tree": union_stage["tree"],
        "source_inventory_sha256": launch_receipt["source_inventory_sha256"],
        "v5_code_manifest_sha256": diagnostic["v5_code_manifest_sha256"],
        "v8_code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "execution_environment": launch_receipt["execution_environment"],
        "source_audit_complete": True,
        "confirmation_prelaunch_authorized": value[
            "confirmation_prelaunch_authorized"
        ],
        "prelaunch_gate": value["prelaunch_gate"],
        "attestation_sha256": attestation_sha256,
        "attestation_records_sha256": value["records_sha256"],
        "cohort_manifest_sha256": {
            name: cohort["tasks_sha256"]
            for name, cohort in value["cohorts"].items()
        },
        "counts": value["counts"],
        "translation_status_counts": value["translation_status_counts"],
        "support_exclusion_counts": value["support_exclusion_counts"],
    }


def _run_seal(*, recovery: bool) -> None:
    context = _seal_context()
    plan_sha = Runtime._publish_or_validate_json(
        SEAL_PLAN, context["plan"], "V8 seal plan"
    )
    union_stage_sha, union_stage = _prepare_union(
        context["diagnostic"], context["v5_tree"], context["v8_tree"],
        plan_sha, recovery=recovery,
    )
    union_root_raw, union_root_stage = Runtime._load_json(
        UNION_ROOT_STAGE, "V8 union-root stage"
    )
    union_root_sha = hashlib.sha256(union_root_raw).hexdigest()
    if union_root_sha != union_stage["union_root_stage_sha256"]:
        raise LaunchAuditError("V8 union stage chain changed")
    candidate_stage_sha, candidate_stage, candidate_raw, value = (
        Runtime._prepare_candidate(
            context["diagnostic"], union_stage_sha,
            context["plan"]["source_record_sequence_sha256"],
        )
    )
    att_stage_sha, att_stage, attestation_sha = Runtime._attestation_stage(
        candidate_stage_sha, candidate_raw
    )
    receipt = _execution_receipt(
        context, plan_sha256=plan_sha,
        union_root_stage_sha256=union_root_sha,
        union_stage_sha256=union_stage_sha, union_stage=union_stage,
        candidate_stage_sha256=candidate_stage_sha,
        attestation_stage_sha256=att_stage_sha,
        attestation_sha256=attestation_sha, value=value,
    )
    if Runtime._publish_or_validate_bytes(
        CANDIDATE, candidate_raw, "V8 candidate before receipt"
    ) != candidate_stage["candidate_sha256"]:
        raise LaunchAuditError("V8 candidate changed before receipt")
    if Runtime._publish_or_validate_bytes(
        ATTESTATION, candidate_raw, "V8 attestation before receipt"
    ) != attestation_sha:
        raise LaunchAuditError("V8 attestation changed before receipt")
    checks = (
        (SEAL_PLAN, context["plan"], plan_sha, "V8 seal plan"),
        (UNION_ROOT_STAGE, union_root_stage, union_root_sha, "V8 union-root stage"),
        (UNION_STAGE, union_stage, union_stage_sha, "V8 union stage"),
        (CANDIDATE_STAGE, candidate_stage, candidate_stage_sha, "V8 candidate stage"),
        (ATTESTATION_STAGE, att_stage, att_stage_sha, "V8 attestation stage"),
    )
    if any(
        Runtime._publish_or_validate_json(path, value_, label) != expected
        for path, value_, expected, label in checks
    ):
        raise LaunchAuditError("V8 seal-stage hash chain changed")
    _final_tree_rehash(context, union_root_stage, union_stage)
    digest = Runtime._publish_or_validate_json(
        EXECUTION_RECEIPT, receipt, "V8 execution receipt"
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
            "V8 seal state exists; use recover-seal after an interruption"
        )
    _run_seal(recovery=False)


def recover_seal() -> None:
    partials = (
        EXECUTION_RECEIPT, UNION_DIR, CANDIDATE, ATTESTATION,
        *SEAL_STAGE_ARTIFACTS,
    )
    if not any(os.path.lexists(path) for path in partials):
        raise LaunchAuditError("V8 has no interrupted seal state")
    _run_seal(recovery=True)


def _configure_private_runtime() -> None:
    values = {
        "Source": Source,
        "SCHEMA": SCHEMA, "DIAGNOSTIC_SCHEMA": DIAGNOSTIC_SCHEMA,
        "LAUNCH_SCHEMA": LAUNCH_SCHEMA, "EXECUTION_SCHEMA": EXECUTION_SCHEMA,
        "ARTIFACT_DIR": ARTIFACT_DIR, "DIAGNOSTIC": DIAGNOSTIC,
        "INTENT": INTENT, "LAUNCH_RECEIPT": LAUNCH_RECEIPT,
        "EXECUTION_RECEIPT": EXECUTION_RECEIPT,
        "SEAL_PLAN": SEAL_PLAN, "UNION_ROOT_STAGE": UNION_ROOT_STAGE,
        "UNION_STAGE": UNION_STAGE, "CANDIDATE_STAGE": CANDIDATE_STAGE,
        "ATTESTATION_STAGE": ATTESTATION_STAGE,
        "SEAL_STAGE_ARTIFACTS": SEAL_STAGE_ARTIFACTS,
        "SLURM_TEMPLATE": SLURM_TEMPLATE, "CODE_MANIFEST": CODE_MANIFEST,
        "OUTPUT_DIR": OUTPUT_DIR, "SOURCE_INVENTORY": SOURCE_INVENTORY,
        # Any inherited union parser must use V8's independently rebuilt
        # inventory and must never open the copy inside the V5 output root.
        "V5_SOURCE_INVENTORY": SOURCE_INVENTORY,
        "TMP_ROOT": TMP_ROOT, "UNION_DIR": UNION_DIR,
        "CANDIDATE": CANDIDATE, "ATTESTATION": ATTESTATION,
        "ARRAY_TASKS": ARRAY_TASKS, "ACCOUNT": ACCOUNT,
        "PARTITION": PARTITION, "QOS": QOS,
        "CPUS_PER_TASK": CPUS_PER_TASK,
        "V6_TOTAL_MEMORY": V8_TOTAL_MEMORY,
        "V6_TOTAL_MEMORY_MIB": V8_TOTAL_MEMORY_MIB,
        "V6_TASK_TIMEOUT_SECONDS": V8_TASK_TIMEOUT_SECONDS,
        "V6_TIME_LIMIT": V8_TIME_LIMIT,
        "JOB_NAME_PREFIX": JOB_NAME_PREFIX, "COMMENT_PREFIX": COMMENT_PREFIX,
        "TIMEOUT_PLACEHOLDER": TIMEOUT_PLACEHOLDER,
        "MANIFEST_PLACEHOLDER": MANIFEST_PLACEHOLDER,
        "NORMALIZED_SLURM_SHA256": NORMALIZED_SLURM_SHA256,
        "SEAL_PLAN_SCHEMA": SEAL_PLAN_SCHEMA,
        "UNION_ROOT_STAGE_SCHEMA": UNION_ROOT_STAGE_SCHEMA,
        "UNION_STAGE_SCHEMA": UNION_STAGE_SCHEMA,
        "CANDIDATE_STAGE_SCHEMA": CANDIDATE_STAGE_SCHEMA,
        "ATTESTATION_STAGE_SCHEMA": ATTESTATION_STAGE_SCHEMA,
        "DIAGNOSTIC_FIELDS": DIAGNOSTIC_FIELDS,
        "DIAGNOSTIC_RELATIVE_PATH": DIAGNOSTIC_RELATIVE_PATH,
        "PRE_DIAGNOSIS_FILES": PRE_DIAGNOSIS_FILES,
        "SCOPED_COMMIT_FILES": SCOPED_COMMIT_FILES,
        "diagnose_v5": diagnose_v5,
        "_pre_diagnosis_file_records": _pre_diagnosis_file_records,
        "_resource_mapping": lambda _classes=None: _resource_mapping(),
        "_load_diagnostic": _load_diagnostic,
        "_slurm_template": _slurm_template,
        "_launch_materials": _launch_materials,
        "_submit_command": _submit_command,
        "_load_intent_only": _load_intent_only,
        "_write_launch_receipt": _write_launch_receipt,
        "_load_launch": _load_launch,
        "_exclusive_bytes": _exclusive_bytes,
        "_create_private_directory": _create_private_directory,
    }
    for name, value in values.items():
        setattr(Runtime, name, value)
    for name in (
        "_v5_scheduler_rows", "_load_v5_launch_without_output_access",
    ):
        if hasattr(Runtime, name):
            delattr(Runtime, name)


_configure_private_runtime()


def prepare_manifest() -> None:
    if any(os.path.lexists(path) for path in (
        SBATCH_STDOUT, SBATCH_STDERR, SBATCH_RESULT,
    )):
        raise LaunchAuditError("V8 submission-capture namespace is not empty")
    _base_prepare_manifest()


def recover_launch() -> None:
    _recover_launch()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "prepare-manifest", "launch", "recover-launch",
        "status", "seal", "recover-seal",
    ))
    command = parser.parse_args(argv).command
    {
        "prepare-manifest": prepare_manifest,
        "launch": launch,
        "recover-launch": recover_launch,
        "status": status,
        "seal": seal,
        "recover-seal": recover_seal,
    }[command]()
    return 0


# The imported V6 module is a private helper namespace, but leaving its old
# command entry points callable would create an unsupported alternate path
# around V8's launch-evidence ordering.  Rebind every command surface to the
# audited V8 implementation; the saved manifest helper above is the only V6
# command body deliberately reused.
for _command_name, _command in {
    "prepare_manifest": prepare_manifest,
    "launch": launch,
    "recover_launch": recover_launch,
    "status": status,
    "seal": seal,
    "recover_seal": recover_seal,
    "main": main,
}.items():
    setattr(Runtime, _command_name, _command)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        LaunchAuditError, Source.SourceAuditError,
        V5Source.SourceAuditError, Inventory.InventoryError,
    ) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
