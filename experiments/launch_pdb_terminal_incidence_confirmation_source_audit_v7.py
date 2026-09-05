#!/usr/bin/env python3
"""Partition terminal V5 scheduler rows, repair their complement, and seal V7.

The V7 diagnostic uses only raw array identity, state, exit code, and partition.
It never opens a V5 shard, environment record, or log.  The mixed seal may read
only the scheduler-reusable V5 triplets, and only after every V7 repair row has
been established as COMPLETED 0:0.
"""

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


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources_v5 as V5Source
import audit_pdb_terminal_incidence_confirmation_sources_v7 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v5 as V5Launch
import pdb_terminal_incidence_confirmation_inventory as Inventory
import pdb_terminal_incidence_confirmation_safe_io_v7 as SelectedIO
import pdb_terminal_incidence_confirmation_source_consumer_v5 as V5Consumer


def _load_private_v6_runtime():
    """Load committed V6 helpers without mutating the public V6 module."""
    path = (
        SCRIPT_DIR /
        "launch_pdb_terminal_incidence_confirmation_source_audit_v6.py"
    )
    name = "_pdb_terminal_incidence_confirmation_source_audit_v7_runtime"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load committed V6 repair helpers")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


Runtime = _load_private_v6_runtime()
LaunchAuditError = Runtime.LaunchAuditError

SCHEMA = Source.Base.SCHEMA + "/campaign-v7"
DIAGNOSTIC_SCHEMA = SCHEMA + "/v5-scheduler-terminal-diagnostic/v1"
LAUNCH_SCHEMA = SCHEMA + "/repair-launch/v1"
EXECUTION_SCHEMA = SCHEMA + "/execution/v1"
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v7"
)
DIAGNOSTIC = ARTIFACT_DIR / "v5-scheduler-terminal-diagnostic-v7.json"
INTENT = ARTIFACT_DIR / "source-audit-repair-launch-intent-v7.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-repair-launch-receipt-v7.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v7.json"
SEAL_PLAN = ARTIFACT_DIR / "source-audit-seal-plan-v7.json"
UNION_ROOT_STAGE = ARTIFACT_DIR / "source-audit-union-root-stage-v7.json"
UNION_STAGE = ARTIFACT_DIR / "source-audit-union-stage-v7.json"
CANDIDATE_STAGE = ARTIFACT_DIR / "source-audit-candidate-stage-v7.json"
ATTESTATION_STAGE = ARTIFACT_DIR / "source-audit-attestation-stage-v7.json"
SEAL_STAGE_ARTIFACTS = (
    SEAL_PLAN, UNION_ROOT_STAGE, UNION_STAGE,
    CANDIDATE_STAGE, ATTESTATION_STAGE,
)
SLURM_TEMPLATE = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v7.slurm"
)
CODE_MANIFEST = Source.DEFAULT_CODE_MANIFEST
OUTPUT_DIR = Source.DEFAULT_SHARDS
SOURCE_INVENTORY = Source.DEFAULT_INVENTORY
TMP_ROOT = Source.TMP_ROOT
UNION_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v7_union"
)
CANDIDATE = Source.DEFAULT_OUTPUT
ATTESTATION = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v7.json"
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
V7_TOTAL_MEMORY = "3000G"
V7_TOTAL_MEMORY_MIB = 3000 * 1024
FAT_NODE_REAL_MEMORY_MIB = V5Launch.FAT_NODE_REAL_MEMORY_MIB
V7_TASK_TIMEOUT_SECONDS = Source.TASK_TIMEOUT_SECONDS
V5_TASK_TIMEOUT_SECONDS = V5Source.TASK_TIMEOUT_SECONDS
V7_TIME_LIMIT = "3-00:00:00"
ACCEPTED_TRANSLATION_STATUSES = ("input-rejected", "success")
CONTROLLED_PATH = V5Launch.CONTROLLED_PATH
SUBMISSION_ENVIRONMENT = dict(V5Launch.SUBMISSION_ENVIRONMENT)
SBATCH_COMMAND = V5Launch.SBATCH_COMMAND
SBATCH_COMMAND_SHA256 = V5Launch.SBATCH_COMMAND_SHA256
SACCT_COMMAND = V5Launch.SACCT_COMMAND
SACCT_COMMAND_SHA256 = V5Launch.SACCT_COMMAND_SHA256
JOB_NAME_PREFIX = "confirmation-source-audit-v7"
COMMENT_PREFIX = "confirmation-source-audit-v7"
TIMEOUT_PLACEHOLDER = b"__V7_TASK_TIMEOUT_SECONDS__"
MANIFEST_PLACEHOLDER = b"__V7_CODE_MANIFEST_SHA256__"
NORMALIZED_SLURM_SHA256 = (
    "cdbd944245e37d34dfde7371ef60fef7ea4776b2aa8ef21241f43a5ecfd3011b"
)

SEAL_PLAN_SCHEMA = EXECUTION_SCHEMA + "/seal-plan/v1"
UNION_ROOT_STAGE_SCHEMA = EXECUTION_SCHEMA + "/union-root-stage/v1"
UNION_STAGE_SCHEMA = EXECUTION_SCHEMA + "/union-stage/v1"
CANDIDATE_STAGE_SCHEMA = EXECUTION_SCHEMA + "/candidate-stage/v1"
ATTESTATION_STAGE_SCHEMA = EXECUTION_SCHEMA + "/attestation-stage/v1"

ACTIVE_STATES = Runtime.ACTIVE_STATES
TERMINAL_ACCOUNTING_STATES = Runtime.TERMINAL_ACCOUNTING_STATES
EXIT_CODE_RE = Runtime.EXIT_CODE_RE
SHA256_RE = Runtime.SHA256_RE
JJ_COMMIT_RE = Runtime.JJ_COMMIT_RE
SUBMISSION_TOKEN_RE = Runtime.SUBMISSION_TOKEN_RE
DIAGNOSTIC_ROW_KEYS = frozenset({
    "array_task", "state", "exit_code", "partition",
})
DIAGNOSTIC_FIELDS = frozenset({
    "schema", "pre_diagnosis_freeze",
    "v5_launch_intent_path", "v5_launch_intent_sha256",
    "v5_launch_receipt_path", "v5_launch_receipt_sha256",
    "v5_launch_receipt", "v5_code_manifest_path",
    "v5_code_manifest_sha256", "v5_source_inventory_sha256",
    "v5_scheduler_rows", "v5_scheduler_rows_sha256",
    "v5_scheduler_state_counts", "scheduler_snapshot_fields",
    "logical_shards", "candidates", "reuse_eligibility_rule",
    "repair_eligibility_rule", "reusable_v5_shard_indices",
    "reusable_v5_shard_indices_sha256", "repair_v5_shard_indices",
    "repair_v5_shard_indices_sha256", "repair_v5_scheduler_rows",
    "repair_v5_scheduler_rows_sha256", "reused_v5_shards",
    "repaired_v5_shards", "repair_scope", "resource_mapping",
    "scheduler_only_partition", "v5_failure_logs_inspected_by_v7",
    "v5_detailed_accounting_inspected_by_v7", "v5_shards_inspected",
    "v5_environment_records_inspected",
    "source_support_outcomes_used_for_v7_design",
    "accepted_translation_statuses",
    "translator_timeout_is_infrastructure_failure",
    "resource_ceiling_changes_accepted_outcome_classes",
    "source_audit_runtime_estimand_recorded",
    "cross_campaign_runtime_comparison_authorized",
    "scheduler_membership_affects_execution_origin_only",
    "noncompleted_v5_shards_used", "pre_v5_campaign_shards_used",
    "v6_runtime_artifacts_used", "whole_campaign_rerun",
    "source_support_outcome_blind_selective_repair",
    "v7_reuse_is_scheduler_defined",
    "v7_design_timing_disclosure", "v5_output_namespace_enumerated_by_v7",
    "v5_output_triplet_bytes_read_before_v7_all_success_gate",
    "v5_reusable_triplet_read_policy",
    "v5_reusable_selected_tree_commitment_policy",
    "v5_source_inventory_read_by_v7",
    "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion",
    "path_containment_trust_model",
})

DIAGNOSTIC_RELATIVE_PATH = DIAGNOSTIC.relative_to(REPO).as_posix()
_V5_RUNTIME_INPUTS = frozenset({
    V5_CODE_MANIFEST.relative_to(REPO).as_posix(),
    V5_INTENT.relative_to(REPO).as_posix(),
    V5_LAUNCH_RECEIPT.relative_to(REPO).as_posix(),
    DIAGNOSTIC_RELATIVE_PATH,
})
PRE_DIAGNOSIS_FILES = tuple(sorted(
    set(Source.CODE_MANIFEST_FILES) - _V5_RUNTIME_INPUTS
))
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


def _pre_diagnosis_file_records() -> list[dict]:
    expected = set(Source.CODE_MANIFEST_FILES) - _V5_RUNTIME_INPUTS
    if (
        PRE_DIAGNOSIS_FILES != tuple(sorted(set(PRE_DIAGNOSIS_FILES)))
        or set(PRE_DIAGNOSIS_FILES) != expected
    ):
        raise LaunchAuditError("V7 prediagnosis design boundary changed")
    records = []
    for relative in PRE_DIAGNOSIS_FILES:
        loaded = Runtime._safe_file(
            REPO / relative, "V7 prediagnosis source", root=REPO
        )
        records.append({
            "path": relative,
            "bytes": loaded.identity["size"],
            "sha256": loaded.sha256,
        })
    return records


def _validate_recorded_pre_diagnosis_freeze(value: dict) -> None:
    """Validate the immutable freeze record without reading descendant files.

    Launch and recovery additionally call the imported live validator.  A
    downstream consumer instead authenticates these exact recorded hashes from
    the pinned prediagnosis revision, so unrelated paper and renderer files may
    evolve after a successful V7 seal.
    """
    expected_keys = {
        "schema", "repository_commit_id", "working_copy_revision",
        "committed_revision", "scoped_diff_empty", "diagnostic_excluded",
        "jj", "files", "files_sha256",
    }
    files = value.get("files") if type(value) is dict else None
    if type(files) is not list:
        raise LaunchAuditError("V7 recorded prediagnosis freeze changed")
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
        raise LaunchAuditError("V7 recorded prediagnosis freeze changed")


def _resource_mapping() -> dict:
    maximum_candidate_seconds = Source.TASKS_PER_SHARD * V7_TASK_TIMEOUT_SECONDS
    job_limit_seconds = 3 * 24 * 60 * 60
    if (
        V7_TOTAL_MEMORY_MIB >= FAT_NODE_REAL_MEMORY_MIB
        or maximum_candidate_seconds >= job_limit_seconds
    ):
        raise LaunchAuditError("V7 fixed resource ceiling is inconsistent")
    return {
        "profile": "fixed-fat-maximum-v7",
        "fixed_before_v7_scheduler_diagnosis": True,
        "uniform_for_every_repair_shard": True,
        "nodes": 1,
        "ntasks": 1,
        "cpus_per_task": CPUS_PER_TASK,
        "memory": {
            "option": "--mem={}".format(V7_TOTAL_MEMORY),
            "requested": V7_TOTAL_MEMORY,
            "mode": "total",
        },
        "task_timeout_seconds": V7_TASK_TIMEOUT_SECONDS,
        "time_limit": V7_TIME_LIMIT,
        "fat_node_real_memory_mib": FAT_NODE_REAL_MEMORY_MIB,
        "v7_total_memory_mib": V7_TOTAL_MEMORY_MIB,
        "fat_node_memory_headroom_mib": (
            FAT_NODE_REAL_MEMORY_MIB - V7_TOTAL_MEMORY_MIB
        ),
        "candidates_per_shard": Source.TASKS_PER_SHARD,
        "maximum_candidate_seconds_per_shard": maximum_candidate_seconds,
        "job_limit_seconds": job_limit_seconds,
        "wrapper_headroom_seconds": job_limit_seconds - maximum_candidate_seconds,
        "historical_operational_information_known_before_v7_freeze": [
            "aggregate V5 terminal scheduler states: 795 COMPLETED, "
            "15 FAILED, 10 OUT_OF_MEMORY",
            "V6 classifier rejection of array row 2 as FAILED 2:0",
        ],
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
        "historical_operational_information_known_before_v7_freeze": [
            "aggregate V5 terminal scheduler-state counts: 795 COMPLETED, "
            "15 FAILED, 10 OUT_OF_MEMORY",
            "V6 classifier rejected scheduler array row 2 as FAILED 2:0",
            "V6 revalidated frozen V5 inventory and task metadata",
            "V6 scheduler parser transiently parsed per-row Elapsed fields",
        ],
        "not_read_before_v7_freeze": [
            "V5 shard payloads", "V5 environment records",
            "V5 logs", "source-support classifications",
        ],
        "accepted_v6_diagnostic_manifest_launch_job_or_shards": False,
        "interpretation": (
            "V7 is prospectively frozen before repair and scientific outcome "
            "inspection, not preregistered before V5 scheduler telemetry"
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


def _validate_diagnostic_rows(rows: list[dict]) -> None:
    if type(rows) is not list or len(rows) != ARRAY_TASKS:
        raise LaunchAuditError("V5 scheduler row cardinality changed")
    for index, row in enumerate(rows):
        if (
            type(row) is not dict
            or set(row) != DIAGNOSTIC_ROW_KEYS
            or row.get("array_task") != index
            or row.get("partition") != PARTITION
            or row.get("state") not in TERMINAL_ACCOUNTING_STATES | ACTIVE_STATES
            or not _matches(EXIT_CODE_RE, row.get("exit_code"))
        ):
            raise LaunchAuditError("V5 scheduler row identity changed")


def _partition_terminal_rows(rows: list[dict]) -> tuple[list[int], list[int]]:
    """Reuse iff COMPLETED 0:0; repair every other recognized terminal row."""
    _validate_diagnostic_rows(rows)
    reusable = []
    repair = []
    for row in rows:
        if row["state"] in ACTIVE_STATES:
            raise LaunchAuditError("V5 source-audit array is not terminal")
        if row["state"] == "COMPLETED" and row["exit_code"] == "0:0":
            reusable.append(row["array_task"])
        else:
            repair.append(row["array_task"])
    _validate_shard_partition(reusable, repair)
    return reusable, repair


def _validate_shard_partition(reusable: list[int], repair: list[int]) -> None:
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
        raise LaunchAuditError("V7 shard partition is not an exact complement")


def _v5_scheduler_rows(job_id: str) -> list[dict]:
    """Read only the raw scheduler fields required by the V7 partition rule."""
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("V5 scheduler job identity changed")
    output = Runtime._sacct([
        str(SACCT_COMMAND), "-j", job_id, "-X", "--array", "-n", "-P",
        "--format=JobID,State,ExitCode,Partition",
    ])
    lines = output.splitlines()
    if len(lines) != ARRAY_TASKS:
        raise LaunchAuditError("V5 scheduler row cardinality changed")
    rows = []
    for index, line in enumerate(lines):
        fields = line.split("|")
        if len(fields) != 4:
            raise LaunchAuditError("V5 scheduler row changed")
        task_id, state, exit_code, partition = fields
        if (
            task_id != "{}_{}".format(job_id, index)
            or state not in TERMINAL_ACCOUNTING_STATES | ACTIVE_STATES
            or not _matches(EXIT_CODE_RE, exit_code)
            or partition != PARTITION
        ):
            raise LaunchAuditError("V5 scheduler field changed")
        rows.append({
            "array_task": index,
            "state": state,
            "exit_code": exit_code,
            "partition": partition,
        })
    _validate_diagnostic_rows(rows)
    return rows


def _load_v5_launch_without_output_access() -> tuple[str, dict]:
    """Authenticate the V5 launch without touching its output namespace."""
    try:
        intent_raw, intent = V5Consumer._read_json(
            V5_INTENT, V5_INTENT, "V5 launch intent"
        )
        launch_raw, launch_receipt = V5Consumer._read_json(
            V5_LAUNCH_RECEIPT, V5_LAUNCH_RECEIPT, "V5 launch receipt"
        )
        V5Consumer._validate_launch(intent_raw, intent, launch_receipt)
        manifest = V5Consumer._manifest(launch_receipt)
        if (
            launch_receipt.get("launcher_sha256") != manifest.get(
                "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py"
            )
            or launch_receipt.get("python_requirements_sha256") != manifest.get(
                "experiments/requirements-pdb-terminal-incidence-shadow.txt"
            )
        ):
            raise LaunchAuditError("V5 launch code/environment chain changed")
        V5Consumer._validate_diagnostic(launch_receipt, manifest)
        V5Consumer._slurm(launch_receipt)
    except V5Consumer.SourceConsumerError as err:
        raise LaunchAuditError("V5 launch provenance is invalid") from err
    return hashlib.sha256(launch_raw).hexdigest(), launch_receipt


def diagnose_v5() -> None:
    # This is deliberately first.  Tests spy on every later V5/scheduler path.
    freeze = Runtime._pre_diagnosis_freeze()
    if os.path.lexists(DIAGNOSTIC):
        raise LaunchAuditError("V7 scheduler diagnostic already exists")
    if any(os.path.lexists(path) for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR, TMP_ROOT,
        UNION_DIR, CANDIDATE, ATTESTATION, CODE_MANIFEST,
        *SEAL_STAGE_ARTIFACTS,
    )):
        raise LaunchAuditError("V7 namespace is not empty before diagnosis")
    if any(os.path.lexists(path) for path in (
        V5_EXECUTION_RECEIPT, V5_CANDIDATE, V5_ATTESTATION,
    )):
        raise LaunchAuditError("V5 is already sealed; V7 repair is forbidden")

    launch_sha, launch = _load_v5_launch_without_output_access()
    rows = _v5_scheduler_rows(launch["job_id"])
    reusable, repair = _partition_terminal_rows(rows)
    repair_rows = [rows[index] for index in repair]
    intent_raw = Runtime._safe_file(V5_INTENT, "V5 launch intent").raw
    diagnostic = {
        "schema": DIAGNOSTIC_SCHEMA,
        "pre_diagnosis_freeze": freeze,
        "v5_launch_intent_path": str(V5_INTENT),
        "v5_launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "v5_launch_receipt_path": str(V5_LAUNCH_RECEIPT),
        "v5_launch_receipt_sha256": launch_sha,
        "v5_launch_receipt": launch,
        "v5_code_manifest_path": str(V5_CODE_MANIFEST),
        "v5_code_manifest_sha256": launch["code_manifest_sha256"],
        "v5_source_inventory_sha256": launch["source_inventory_sha256"],
        "v5_scheduler_rows": rows,
        "v5_scheduler_rows_sha256": _digest(rows),
        "v5_scheduler_state_counts": dict(sorted(Counter(
            row["state"] for row in rows
        ).items())),
        "scheduler_snapshot_fields": [
            "JobID", "State", "ExitCode", "Partition",
        ],
        "logical_shards": ARRAY_TASKS,
        "candidates": Source.CANDIDATE_COUNT,
        "reuse_eligibility_rule": "scheduler state COMPLETED with exit 0:0 only",
        "repair_eligibility_rule": (
            "every other recognized terminal scheduler row and exit code"
        ),
        "reusable_v5_shard_indices": reusable,
        "reusable_v5_shard_indices_sha256": _digest(reusable),
        "repair_v5_shard_indices": repair,
        "repair_v5_shard_indices_sha256": _digest(repair),
        "repair_v5_scheduler_rows": repair_rows,
        "repair_v5_scheduler_rows_sha256": _digest(repair_rows),
        "reused_v5_shards": len(reusable),
        "repaired_v5_shards": len(repair),
        "repair_scope": "complete original two-candidate shards",
        "resource_mapping": _resource_mapping(),
        "scheduler_only_partition": True,
        "v5_failure_logs_inspected_by_v7": False,
        "v5_detailed_accounting_inspected_by_v7": False,
        "v5_shards_inspected": False,
        "v5_environment_records_inspected": False,
        "source_support_outcomes_used_for_v7_design": False,
        "accepted_translation_statuses": list(ACCEPTED_TRANSLATION_STATUSES),
        "translator_timeout_is_infrastructure_failure": True,
        "resource_ceiling_changes_accepted_outcome_classes": False,
        "source_audit_runtime_estimand_recorded": False,
        "cross_campaign_runtime_comparison_authorized": False,
        "scheduler_membership_affects_execution_origin_only": True,
        "noncompleted_v5_shards_used": False,
        "pre_v5_campaign_shards_used": [],
        "v6_runtime_artifacts_used": False,
        "whole_campaign_rerun": False,
        "source_support_outcome_blind_selective_repair": True,
        "v7_reuse_is_scheduler_defined": True,
        "v7_design_timing_disclosure": _design_timing_disclosure(),
        "v5_output_namespace_enumerated_by_v7": False,
        "v5_output_triplet_bytes_read_before_v7_all_success_gate": False,
        "v5_reusable_triplet_read_policy": (
            "only-during-seal-after-v7-all-success-gate"
        ),
        "v5_reusable_selected_tree_commitment_policy": (
            "first-separate-record-at-v7-seal"
        ),
        "v5_source_inventory_read_by_v7": False,
        "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion": (
            False
        ),
        "path_containment_trust_model": _path_containment_trust_model(),
    }
    digest = Runtime._exclusive_json(
        DIAGNOSTIC, diagnostic, "V7 scheduler diagnostic"
    )
    print(json.dumps({
        "diagnostic_sha256": digest,
        "reused_v5_shards": len(reusable),
        "repaired_v5_shards": len(repair),
        "resource_mapping": diagnostic["resource_mapping"],
    }, sort_keys=True, indent=2))


def _load_diagnostic_common(
    *, require_live_prediagnosis_files: bool,
) -> tuple[str, dict]:
    raw, value = Runtime._load_json(DIAGNOSTIC, "V7 scheduler diagnostic")
    if type(value) is not dict or set(value) != DIAGNOSTIC_FIELDS:
        raise LaunchAuditError("V7 scheduler diagnostic schema changed")
    reusable = value.get("reusable_v5_shard_indices")
    repair = value.get("repair_v5_shard_indices")
    rows = value.get("v5_scheduler_rows")
    launch = value.get("v5_launch_receipt")
    freeze = value.get("pre_diagnosis_freeze")
    _validate_recorded_pre_diagnosis_freeze(freeze)
    if require_live_prediagnosis_files:
        Runtime._validate_pre_diagnosis_freeze(freeze)
    _validate_shard_partition(reusable, repair)
    expected_repair_rows = [rows[index] for index in repair] if isinstance(
        rows, list
    ) and all(type(index) is int and 0 <= index < len(rows) for index in repair) else None
    if (
        value.get("schema") != DIAGNOSTIC_SCHEMA
        or value.get("v5_launch_intent_path") != str(V5_INTENT)
        or value.get("v5_launch_receipt_path") != str(V5_LAUNCH_RECEIPT)
        or value.get("v5_code_manifest_path") != str(V5_CODE_MANIFEST)
        or not isinstance(launch, dict)
        or _partition_terminal_rows(rows) != (reusable, repair)
        or value.get("logical_shards") != ARRAY_TASKS
        or value.get("candidates") != Source.CANDIDATE_COUNT
        or value.get("reused_v5_shards") != len(reusable)
        or value.get("repaired_v5_shards") != len(repair)
        or value.get("v5_scheduler_rows_sha256") != _digest(rows)
        or value.get("v5_scheduler_state_counts") != dict(sorted(Counter(
            row["state"] for row in rows
        ).items()))
        or value.get("scheduler_snapshot_fields") != [
            "JobID", "State", "ExitCode", "Partition",
        ]
        or value.get("reusable_v5_shard_indices_sha256") != _digest(reusable)
        or value.get("repair_v5_shard_indices_sha256") != _digest(repair)
        or value.get("repair_v5_scheduler_rows") != expected_repair_rows
        or value.get("repair_v5_scheduler_rows_sha256") != _digest(
            expected_repair_rows
        )
        or value.get("reuse_eligibility_rule")
        != "scheduler state COMPLETED with exit 0:0 only"
        or value.get("repair_eligibility_rule")
        != "every other recognized terminal scheduler row and exit code"
        or value.get("repair_scope") != "complete original two-candidate shards"
        or value.get("resource_mapping") != _resource_mapping()
        or value.get("scheduler_only_partition") is not True
        or value.get("v5_failure_logs_inspected_by_v7") is not False
        or value.get("v5_detailed_accounting_inspected_by_v7") is not False
        or value.get("v5_shards_inspected") is not False
        or value.get("v5_environment_records_inspected") is not False
        or value.get("source_support_outcomes_used_for_v7_design") is not False
        or value.get("accepted_translation_statuses")
        != list(ACCEPTED_TRANSLATION_STATUSES)
        or value.get("translator_timeout_is_infrastructure_failure") is not True
        or value.get("resource_ceiling_changes_accepted_outcome_classes")
        is not False
        or value.get("source_audit_runtime_estimand_recorded") is not False
        or value.get("cross_campaign_runtime_comparison_authorized") is not False
        or value.get("scheduler_membership_affects_execution_origin_only") is not True
        or value.get("noncompleted_v5_shards_used") is not False
        or value.get("pre_v5_campaign_shards_used") != []
        or value.get("v6_runtime_artifacts_used") is not False
        or value.get("whole_campaign_rerun") is not False
        or value.get("source_support_outcome_blind_selective_repair") is not True
        or value.get("v7_reuse_is_scheduler_defined") is not True
        or value.get("v7_design_timing_disclosure")
        != _design_timing_disclosure()
        or value.get("v5_output_namespace_enumerated_by_v7") is not False
        or value.get(
            "v5_output_triplet_bytes_read_before_v7_all_success_gate"
        ) is not False
        or value.get(
            "v5_reusable_triplet_read_policy"
        ) != "only-during-seal-after-v7-all-success-gate"
        or value.get("v5_reusable_selected_tree_commitment_policy")
        != "first-separate-record-at-v7-seal"
        or value.get("v5_source_inventory_read_by_v7") is not False
        or value.get(
            "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion"
        ) is not False
        or value.get("path_containment_trust_model")
        != _path_containment_trust_model()
    ):
        raise LaunchAuditError("V7 scheduler diagnostic changed")
    launch_raw, actual_launch = Runtime._load_json(
        V5_LAUNCH_RECEIPT, "V5 launch receipt"
    )
    if (
        hashlib.sha256(launch_raw).hexdigest()
        != value.get("v5_launch_receipt_sha256")
        or actual_launch != launch
        or Runtime._sha256(V5_INTENT) != value.get("v5_launch_intent_sha256")
        or Runtime._sha256(V5_CODE_MANIFEST)
        != value.get("v5_code_manifest_sha256")
        or launch.get("source_inventory_sha256")
        != value.get("v5_source_inventory_sha256")
    ):
        raise LaunchAuditError("V5 launch inputs changed after V7 diagnosis")
    return hashlib.sha256(raw).hexdigest(), value


def _load_diagnostic() -> tuple[str, dict]:
    """Load a diagnostic for prelaunch/recovery with live freeze equality."""
    return _load_diagnostic_common(require_live_prediagnosis_files=True)


def _load_recorded_diagnostic() -> tuple[str, dict]:
    """Load a sealed diagnostic without constraining descendant design files.

    Consumers must separately authenticate every recorded prediagnosis file
    from ``repository_commit_id``.  This path deliberately performs no live
    comparison against paper, renderer, or downstream design bytes.
    """
    return _load_diagnostic_common(require_live_prediagnosis_files=False)


def _slurm_template() -> bytes:
    loaded = Runtime._safe_file(SLURM_TEMPLATE, "V7 Slurm template", root=REPO)
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
        b'code_manifest="experiments/pdb_terminal_incidence_confirmation_source_audit_v7_code.sha256"',
        b'code_manifest_sha256="' + MANIFEST_PLACEHOLDER + b'"',
        b'source_inventory="experiments/data/pdb_terminal_incidence_confirmation_source_audit_v7_repair/source-inventory-v7.json"',
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
        b"    experiments/audit_pdb_terminal_incidence_confirmation_sources_v7.py scan \\",
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
        raise LaunchAuditError("V7 Slurm template contract changed")
    return raw


_base_launch_materials = Runtime._launch_materials


def _launch_materials(
    diagnostic_sha: str,
    diagnostic: dict,
    *,
    repository_commit_id: str | None = None,
    roots: dict | None = None,
) -> dict:
    materials = _base_launch_materials(
        diagnostic_sha, diagnostic,
        repository_commit_id=repository_commit_id, roots=roots,
    )
    if materials.get("campaign") != "v6-selective-repair":
        raise LaunchAuditError("imported V6 launch-material contract changed")
    materials["campaign"] = "v7-selective-repair"
    materials["source_support_outcome_blind_selective_repair"] = materials.pop(
        "outcome_blind_selective_repair"
    )
    materials["v5_scheduler_diagnostic_sha256"] = materials.pop(
        "v5_terminal_diagnostic_sha256"
    )
    materials.update({
        "reused_v6_shards": 0,
        "scheduler_only_partition": True,
        "v5_failure_logs_inspected_by_v7": False,
        "v5_detailed_accounting_inspected_by_v7": False,
        "source_support_outcomes_used_for_v7_design": False,
        "accepted_translation_statuses": list(ACCEPTED_TRANSLATION_STATUSES),
        "translator_timeout_is_infrastructure_failure": True,
        "resource_ceiling_changes_accepted_outcome_classes": False,
        "source_audit_runtime_estimand_recorded": False,
        "cross_campaign_runtime_comparison_authorized": False,
        "scheduler_membership_affects_execution_origin_only": True,
        "v6_runtime_artifacts_used": False,
        "v5_scheduler_rows_sha256": diagnostic["v5_scheduler_rows_sha256"],
        "v7_design_timing_disclosure": diagnostic[
            "v7_design_timing_disclosure"
        ],
        "v5_output_namespace_enumerated_by_v7": False,
        "v5_output_triplet_bytes_read_before_v7_all_success_gate": False,
        "v5_reusable_triplet_read_policy": (
            "only-during-seal-after-v7-all-success-gate"
        ),
        "v5_reusable_selected_tree_commitment_policy": (
            "first-separate-record-at-v7-seal"
        ),
        "v5_source_inventory_read_by_v7": False,
        "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion": (
            False
        ),
        "path_containment_trust_model": _path_containment_trust_model(),
    })
    return materials


def _rebuilt_inventory(diagnostic: dict) -> bytes:
    inventory = Inventory.load_inventory()
    value = Source.build_inventory_manifest(inventory)
    raw = Source.canonical_json(value)
    if hashlib.sha256(raw).hexdigest() != diagnostic["v5_source_inventory_sha256"]:
        raise LaunchAuditError("rebuilt frozen source inventory changed")
    return raw


def launch() -> None:
    if any(os.path.lexists(path) for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR, TMP_ROOT,
        UNION_DIR, CANDIDATE, ATTESTATION, *SEAL_STAGE_ARTIFACTS,
    )):
        raise LaunchAuditError("V7 launch namespace is not empty")
    diagnostic_sha, diagnostic = _load_diagnostic()
    repository_commit_id = Runtime._scoped_repository_commit()
    manifest_sha = Runtime._sha256(CODE_MANIFEST, "V7 code manifest")
    Source.configure(V7_TASK_TIMEOUT_SECONDS)
    Source.validate_code_manifest(CODE_MANIFEST, manifest_sha)
    Runtime._validate_freeze_against_manifest(
        diagnostic["pre_diagnosis_freeze"], CODE_MANIFEST, manifest_sha
    )
    Runtime._render_slurm(manifest_sha, V7_TASK_TIMEOUT_SECONDS)
    inventory_raw = _rebuilt_inventory(diagnostic)
    output_identity = Runtime._create_private_directory(
        OUTPUT_DIR, "V7 output directory"
    )
    tmp_identity = Runtime._create_private_directory(
        TMP_ROOT, "V7 TMPDIR root"
    )
    roots = {"output_dir": output_identity, "tmpdir_root": tmp_identity}
    Runtime._exclusive_bytes(SOURCE_INVENTORY, inventory_raw, "V7 source inventory")
    materials = _launch_materials(
        diagnostic_sha, diagnostic,
        repository_commit_id=repository_commit_id, roots=roots,
    )
    token = secrets.token_hex(12)
    recorded = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )
    command = Runtime._submit_command(diagnostic, token)
    intent = {
        "schema": LAUNCH_SCHEMA + "/intent",
        **materials,
        "recorded_utc": recorded,
        "submission_token": token,
        "submit_command": command,
    }
    intent_raw = _canonical_json(intent)
    Runtime._exclusive_json(INTENT, intent, "V7 launch intent")
    rendered = Runtime._render_slurm(manifest_sha, V7_TASK_TIMEOUT_SECONDS)
    if (
        hashlib.sha256(rendered).hexdigest() != materials["slurm_program_sha256"]
        or len(rendered) != materials["slurm_program_bytes"]
    ):
        raise LaunchAuditError("V7 rendered Slurm bytes changed before submission")
    Runtime._executable_identity(SBATCH_COMMAND, SBATCH_COMMAND_SHA256, "sbatch")
    try:
        completed = subprocess.run(
            command, input=rendered, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=REPO,
            env=dict(SUBMISSION_ENVIRONMENT), check=True,
        )
        output = completed.stdout.decode("ascii").strip()
    except (OSError, subprocess.CalledProcessError, UnicodeDecodeError) as err:
        raise LaunchAuditError("V7 sbatch failed after intent") from err
    job_id = output.split(";", 1)[0]
    digest = Runtime._write_launch_receipt(intent_raw, intent, job_id)
    print(json.dumps({
        "job_id": job_id,
        "launch_receipt_sha256": digest,
        "repair_v5_shard_indices": diagnostic["repair_v5_shard_indices"],
    }, sort_keys=True, indent=2))


def _v7_scheduler_rows(job_id: str, expected: list[int]) -> list[dict]:
    if (
        not isinstance(job_id, str)
        or not job_id.isdigit()
        or type(expected) is not list
        or not expected
        or expected != sorted(set(expected))
        or any(type(index) is not int or not 0 <= index < ARRAY_TASKS
               for index in expected)
    ):
        raise LaunchAuditError("V7 scheduler query is invalid")
    output = Runtime._sacct([
        str(SACCT_COMMAND), "-j", job_id, "-X", "--array", "-n", "-P",
        "--format=JobID,State,ExitCode,Partition",
    ])
    lines = output.splitlines()
    if len(lines) != len(expected):
        raise LaunchAuditError("V7 accounting task cardinality changed")
    rows = []
    for index, line in zip(expected, lines):
        fields = line.split("|")
        if len(fields) != 4:
            raise LaunchAuditError("V7 accounting row changed")
        task_id, state, exit_code, partition = fields
        if (
            task_id != "{}_{}".format(job_id, index)
            or state not in TERMINAL_ACCOUNTING_STATES | ACTIVE_STATES
            or not _matches(EXIT_CODE_RE, exit_code)
            or partition != PARTITION
        ):
            raise LaunchAuditError("V7 accounting field changed")
        rows.append({
            "array_task": index, "state": state,
            "exit_code": exit_code, "partition": partition,
        })
    return rows


def status() -> tuple[str, dict, dict, list[dict]]:
    launch_sha, launch_receipt, diagnostic = Runtime._load_launch()
    rows = _v7_scheduler_rows(
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
    """Read detailed V7 resources only after the all-success row gate."""
    repair = diagnostic["repair_v5_shard_indices"]
    if (
        len(rows) != len(repair)
        or any(row.get("state") != "COMPLETED" or row.get("exit_code") != "0:0"
               for row in rows)
    ):
        raise LaunchAuditError("V7 success gate must precede resource accounting")
    output = Runtime._sacct([
        str(SACCT_COMMAND), "-j", launch_receipt["job_id"], "-X", "--array",
        "-n", "-P", "--format=JobID,Account,Partition,QOS,ReqCPUS,ReqMem,"
        "Timelimit,Elapsed,State,ExitCode,JobName",
    ])
    lines = output.splitlines()
    if len(lines) != len(repair):
        raise LaunchAuditError("V7 resource accounting cardinality changed")
    expected_name, _ = Runtime._submission_identity(
        launch_receipt["submission_token"]
    )
    result = []
    for index, row, line in zip(repair, rows, lines):
        fields = line.split("|")
        if len(fields) != 11:
            raise LaunchAuditError("V7 resource accounting row changed")
        (task_id, account, partition, qos, cpus, memory, time_limit,
         elapsed, state, exit_code, job_name) = fields
        if (
            task_id != "{}_{}".format(launch_receipt["job_id"], index)
            or account != ACCOUNT or partition != PARTITION or qos != QOS
            or cpus != "1" or memory != V7_TOTAL_MEMORY
            or time_limit != V7_TIME_LIMIT
            or not Runtime._valid_elapsed(elapsed)
            or state != row["state"] or exit_code != row["exit_code"]
            or state != "COMPLETED" or exit_code != "0:0"
            or job_name != expected_name
        ):
            raise LaunchAuditError("V7 actual resource contract changed")
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
            "V7 attestation contains a nonaccepted translation outcome"
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
    diagnostic: dict, v5_tree: dict, v7_tree: dict, plan_sha256: str,
    *, recovery: bool,
) -> tuple[str, dict]:
    root_stage_sha, root_stage = Runtime._ensure_union_root(
        plan_sha256, recovery=recovery
    )
    partial = Runtime._union_tree(root_stage["root_identity"], complete=False)
    partial_names = {item["path"] for item in partial["files"]}
    expected_names = set(Runtime._expected_union_names())
    if not partial_names <= expected_names:
        raise LaunchAuditError("V7 union contains an unexpected partial shard")
    v5_files = _manifest_file_map(v5_tree)
    v7_files = _manifest_file_map(v7_tree)
    reusable = set(diagnostic["reusable_v5_shard_indices"])
    sources = []
    for index in range(ARRAY_TASKS):
        if index in reusable:
            source = V5Source.shard_path(V5_OUTPUT_DIR, index)
            origin = "v5-completed"
            frozen = v5_files.get(source.name)
        else:
            source = Source.shard_path(OUTPUT_DIR, index)
            origin = "v7-repair"
            frozen = v7_files.get(source.name)
        if frozen is None:
            raise LaunchAuditError("V7 union source is absent from frozen tree")
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
        UNION_STAGE, stage, "V7 union stage"
    ), stage


def _seal_context() -> dict:
    launch_sha, launch_receipt, diagnostic, rows = status()
    # The gate must precede every V5/V7 shard, environment, or log access.
    if any(
        row["state"] != "COMPLETED" or row["exit_code"] != "0:0"
        for row in rows
    ):
        raise LaunchAuditError("V7 repair array is not entirely successful")
    contract = _scheduler_contract_rows(launch_receipt, diagnostic, rows)
    v5_tree, v5_tasks, v5_environments = _read_v5_reusable_triplets(
        diagnostic
    )
    _validate_accepted_translation_records(
        v5_tasks, diagnostic["reusable_v5_shard_indices"],
        V5_TASK_TIMEOUT_SECONDS, "V5 reusable records",
    )
    v7_tree = Runtime._v6_output_tree(launch_receipt, diagnostic)
    v7_tasks, v7_environments = Runtime._validate_v6_repair_shards(
        launch_receipt, diagnostic, v7_tree
    )
    _validate_accepted_translation_records(
        v7_tasks, diagnostic["repair_v5_shard_indices"],
        V7_TASK_TIMEOUT_SECONDS, "V7 repair records",
    )
    record_sha = Runtime._source_record_sequence_sha256(
        diagnostic, v5_tasks, v7_tasks
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
        "v7_output_tree": v7_tree,
        "v5_reusable_environment_manifest": v5_environments,
        "v7_repair_environment_manifest": v7_environments,
        "source_record_count": Source.CANDIDATE_COUNT,
        "source_record_sequence_sha256": record_sha,
    }
    return {
        "launch_sha": launch_sha, "launch": launch_receipt,
        "diagnostic": diagnostic, "rows": rows, "contract": contract,
        "v5_tree": v5_tree, "v7_tree": v7_tree,
        "v5_environments": v5_environments,
        "v7_environments": v7_environments, "plan": plan,
    }


def _final_tree_rehash(context: dict, union_root_stage: dict, union_stage: dict):
    if _v5_reusable_tree(context["diagnostic"]) != context["v5_tree"]:
        raise LaunchAuditError("V5 reusable bytes changed before V7 receipt")
    if Runtime._v6_output_tree(
        context["launch"], context["diagnostic"]
    ) != context["v7_tree"]:
        raise LaunchAuditError("V7 repair output changed before receipt")
    if Runtime._union_tree(
        union_root_stage["root_identity"], complete=True
    ) != union_stage["tree"]:
        raise LaunchAuditError("V7 union changed before receipt")


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
        "campaign": "v7-selective-repair",
        "benchmark_revision": launch_receipt["benchmark_revision"],
        "logical_shards": ARRAY_TASKS,
        "candidates": Source.CANDIDATE_COUNT,
        "whole_campaign_rerun": False,
        "source_support_outcome_blind_selective_repair": True,
        "noncompleted_v5_shards_used": False,
        "noncompleted_v5_files_opened": False,
        "v5_noncompleted_failure_logs_inspected": False,
        "v5_failure_detailed_accounting_inspected": False,
        "v7_success_resource_accounting_recorded": True,
        "source_support_outcomes_used_for_v7_design": False,
        "accepted_translation_statuses": list(ACCEPTED_TRANSLATION_STATUSES),
        "translator_timeout_is_infrastructure_failure": True,
        "resource_ceiling_changes_accepted_outcome_classes": False,
        "source_audit_runtime_estimand_recorded": False,
        "cross_campaign_runtime_comparison_authorized": False,
        "scheduler_membership_affects_execution_origin_only": True,
        "v6_runtime_artifacts_used": False,
        "v7_design_timing_disclosure": diagnostic[
            "v7_design_timing_disclosure"
        ],
        "v5_output_namespace_enumerated_by_v7": False,
        "v5_output_triplet_bytes_read_before_v7_all_success_gate": False,
        "v5_reusable_triplet_bytes_read_during_seal_after_v7_all_success_gate": (
            True
        ),
        "v5_source_inventory_read_by_v7": False,
        "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion": (
            False
        ),
        "v5_reusable_selected_tree_first_separately_recorded_at_v7_seal": True,
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
        "v7_job_id": launch_receipt["job_id"],
        "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "reused_v6_shards": 0,
        "reused_v5_shards": len(diagnostic["reusable_v5_shard_indices"]),
        "reusable_v5_shard_indices": diagnostic["reusable_v5_shard_indices"],
        "repaired_v5_shards": len(diagnostic["repair_v5_shard_indices"]),
        "repair_v5_shard_indices": diagnostic["repair_v5_shard_indices"],
        "repair_scope": "complete original two-candidate shards",
        "array_throttle": 0,
        "resource_mapping": diagnostic["resource_mapping"],
        "scheduler_state_counts": {"COMPLETED": len(rows)},
        "scheduler_rows": rows,
        "scheduler_contract_rows": context["contract"],
        "v5_reusable_tree": context["v5_tree"],
        "v7_output_tree": context["v7_tree"],
        "v5_reusable_environment_manifest": context["v5_environments"],
        "v7_repair_environment_manifest": context["v7_environments"],
        "union_sources": union_stage["sources"],
        "union_sources_sha256": union_stage["sources_sha256"],
        "union_tree": union_stage["tree"],
        "source_inventory_sha256": launch_receipt["source_inventory_sha256"],
        "v5_code_manifest_sha256": diagnostic["v5_code_manifest_sha256"],
        "v7_code_manifest_sha256": launch_receipt["code_manifest_sha256"],
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
        SEAL_PLAN, context["plan"], "V7 seal plan"
    )
    union_stage_sha, union_stage = _prepare_union(
        context["diagnostic"], context["v5_tree"], context["v7_tree"],
        plan_sha, recovery=recovery,
    )
    union_root_raw, union_root_stage = Runtime._load_json(
        UNION_ROOT_STAGE, "V7 union-root stage"
    )
    union_root_sha = hashlib.sha256(union_root_raw).hexdigest()
    if union_root_sha != union_stage["union_root_stage_sha256"]:
        raise LaunchAuditError("V7 union stage chain changed")
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
        CANDIDATE, candidate_raw, "V7 candidate before receipt"
    ) != candidate_stage["candidate_sha256"]:
        raise LaunchAuditError("V7 candidate changed before receipt")
    if Runtime._publish_or_validate_bytes(
        ATTESTATION, candidate_raw, "V7 attestation before receipt"
    ) != attestation_sha:
        raise LaunchAuditError("V7 attestation changed before receipt")
    checks = (
        (SEAL_PLAN, context["plan"], plan_sha, "V7 seal plan"),
        (UNION_ROOT_STAGE, union_root_stage, union_root_sha, "V7 union-root stage"),
        (UNION_STAGE, union_stage, union_stage_sha, "V7 union stage"),
        (CANDIDATE_STAGE, candidate_stage, candidate_stage_sha, "V7 candidate stage"),
        (ATTESTATION_STAGE, att_stage, att_stage_sha, "V7 attestation stage"),
    )
    if any(
        Runtime._publish_or_validate_json(path, value_, label) != expected
        for path, value_, expected, label in checks
    ):
        raise LaunchAuditError("V7 seal-stage hash chain changed")
    _final_tree_rehash(context, union_root_stage, union_stage)
    digest = Runtime._publish_or_validate_json(
        EXECUTION_RECEIPT, receipt, "V7 execution receipt"
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
            "V7 seal state exists; use recover-seal after an interruption"
        )
    _run_seal(recovery=False)


def recover_seal() -> None:
    partials = (
        EXECUTION_RECEIPT, UNION_DIR, CANDIDATE, ATTESTATION,
        *SEAL_STAGE_ARTIFACTS,
    )
    if not any(os.path.lexists(path) for path in partials):
        raise LaunchAuditError("V7 has no interrupted seal state")
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
        # Any inherited union parser must use V7's independently rebuilt
        # inventory and must never open the copy inside the V5 output root.
        "V5_SOURCE_INVENTORY": SOURCE_INVENTORY,
        "TMP_ROOT": TMP_ROOT, "UNION_DIR": UNION_DIR,
        "CANDIDATE": CANDIDATE, "ATTESTATION": ATTESTATION,
        "ARRAY_TASKS": ARRAY_TASKS, "ACCOUNT": ACCOUNT,
        "PARTITION": PARTITION, "QOS": QOS,
        "CPUS_PER_TASK": CPUS_PER_TASK,
        "V6_TOTAL_MEMORY": V7_TOTAL_MEMORY,
        "V6_TOTAL_MEMORY_MIB": V7_TOTAL_MEMORY_MIB,
        "V6_TASK_TIMEOUT_SECONDS": V7_TASK_TIMEOUT_SECONDS,
        "V6_TIME_LIMIT": V7_TIME_LIMIT,
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
        "_pre_diagnosis_file_records": _pre_diagnosis_file_records,
        "_partition_terminal_rows": _partition_terminal_rows,
        "_resource_mapping": lambda _classes=None: _resource_mapping(),
        "_load_diagnostic": _load_diagnostic,
        "_slurm_template": _slurm_template,
        "_launch_materials": _launch_materials,
        "_exclusive_bytes": _exclusive_bytes,
        "_create_private_directory": _create_private_directory,
    }
    for name, value in values.items():
        setattr(Runtime, name, value)


_configure_private_runtime()


def prepare_manifest() -> None:
    Runtime.prepare_manifest()


def recover_launch() -> None:
    Runtime.recover_launch()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "diagnose-v5", "prepare-manifest", "launch", "recover-launch",
        "status", "seal", "recover-seal",
    ))
    command = parser.parse_args(argv).command
    {
        "diagnose-v5": diagnose_v5,
        "prepare-manifest": prepare_manifest,
        "launch": launch,
        "recover-launch": recover_launch,
        "status": status,
        "seal": seal,
        "recover-seal": recover_seal,
    }[command]()
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
