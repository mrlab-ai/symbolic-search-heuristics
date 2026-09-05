#!/usr/bin/env python3
"""Strict downstream consumer for the two-origin V5/V8 source seal."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_safe_io_v6 as CompleteTreeIO
import pdb_terminal_incidence_confirmation_safe_io_v8 as SelectedTreeIO
import pdb_terminal_incidence_confirmation_source_consumer_v6 as V6Utilities
import audit_pdb_terminal_incidence_confirmation_sources_v8 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v8 as Launch


class SourceConsumerError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
CAMPAIGN = "v8-selective-repair"
ATTESTATION_SCHEMA = Source.Base.SCHEMA
ATTESTATION = Launch.ATTESTATION
DIAGNOSTIC = Launch.DIAGNOSTIC
INTENT = Launch.INTENT
LAUNCH_RECEIPT = Launch.LAUNCH_RECEIPT
EXECUTION_RECEIPT = Launch.EXECUTION_RECEIPT
CODE_MANIFEST = Launch.CODE_MANIFEST
SLURM_TEMPLATE = Launch.SLURM_TEMPLATE
OUTPUT_DIR = Launch.OUTPUT_DIR
SOURCE_INVENTORY = Launch.SOURCE_INVENTORY
TMP_ROOT = Launch.TMP_ROOT
UNION_DIR = Launch.UNION_DIR
CANDIDATE = Launch.CANDIDATE
SEAL_PLAN = Launch.SEAL_PLAN
UNION_ROOT_STAGE = Launch.UNION_ROOT_STAGE
UNION_STAGE = Launch.UNION_STAGE
CANDIDATE_STAGE = Launch.CANDIDATE_STAGE
ATTESTATION_STAGE = Launch.ATTESTATION_STAGE
V5_OUTPUT_DIR = Launch.V5_OUTPUT_DIR
ARRAY_TASKS = Launch.ARRAY_TASKS
CANDIDATES = Source.CANDIDATE_COUNT
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
TOKEN_RE = re.compile(r"[0-9a-f]{24}")
CODE_MANIFEST_FILES = tuple(Source.CODE_MANIFEST_FILES)
LIVE_SEMANTIC_REPLAY_FILES = (
    "experiments/audit_pdb_terminal_incidence_confirmation_sources.py",
    "experiments/pdb_terminal_incidence_confirmation_inventory.py",
)
MANIFEST_RELATIVE = CODE_MANIFEST.relative_to(REPO).as_posix()
SCOPED_FILES = tuple(Launch.SCOPED_COMMIT_FILES)
SHARD_CODE_FIELDS = (
    "code_manifest_sha256", "python_version", "python_executable",
    "python_executable_sha256", "python_environment_sha256",
    "python_distributions", "python_requirements_sha256",
)

MATERIAL_KEYS = frozenset({
    "campaign", "benchmark_revision", "v5_scheduler_diagnostic_sha256",
    "v5_launch_receipt_sha256", "logical_shards", "candidates",
    "reusable_v5_shard_indices", "repair_v5_shard_indices",
    "reused_v1_shards", "reused_v2_shards", "reused_v3_shards",
    "reused_v4_shards", "reused_v5_shards", "reused_v6_shards",
    "reused_v7_shards",
    "repaired_v5_shards", "reuse_eligibility_rule", "repair_scope",
    "whole_campaign_rerun", "source_support_outcome_blind_selective_repair",
    "noncompleted_v5_shards_used", "array", "array_throttle",
    "partition", "qos", "account", "cpus_per_task", "resource_mapping",
    "source_inventory_sha256", "code_manifest_sha256",
    "slurm_template_sha256", "slurm_program_sha256",
    "slurm_program_bytes", "slurm_submission_mode",
    "repository_commit_id", "scoped_repository_files",
    "launch_root_identities", "output_dir", "tmpdir_root",
    "source_inventory_path", "candidate_attestation",
    "frozen_attestation", "execution_environment",
    "scheduler_only_partition", "v5_failure_logs_inspected_by_v8",
    "v5_detailed_accounting_inspected_by_v8",
    "source_support_outcomes_used_for_v8_design",
    "accepted_translation_statuses",
    "translator_timeout_is_infrastructure_failure",
    "resource_ceiling_changes_accepted_outcome_classes",
    "source_audit_runtime_estimand_recorded",
    "cross_campaign_runtime_comparison_authorized",
    "scheduler_membership_affects_execution_origin_only",
    "v6_runtime_artifacts_used", "v7_runtime_artifacts_used",
    "v5_scheduler_rows_sha256", "v7_launch_intent_sha256",
    "v7_launch_failure_sha256", "scheduler_profile_change_from_v7",
    "v8_design_timing_disclosure", "v5_output_namespace_enumerated_by_v8",
    "v5_output_triplet_bytes_read_before_v8_all_success_gate",
    "v5_reusable_triplet_read_policy",
    "v5_reusable_selected_tree_commitment_policy",
    "v5_source_inventory_read_by_v8",
    "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion",
    "path_containment_trust_model",
    "sbatch_stdout_path", "sbatch_stderr_path", "sbatch_result_path",
    "sbatch_capture_initial_identities",
})
INTENT_KEYS = MATERIAL_KEYS | frozenset({
    "schema", "recorded_utc", "submission_token", "submit_command",
})
LAUNCH_KEYS = (INTENT_KEYS - {"schema"}) | frozenset({
    "schema", "launch_intent_sha256", "sbatch_result_sha256",
    "launch_recovered_from_journal", "job_id",
})
EXECUTION_KEYS = frozenset({
    "schema", "campaign", "benchmark_revision", "logical_shards",
    "candidates", "whole_campaign_rerun",
    "source_support_outcome_blind_selective_repair",
    "noncompleted_v5_shards_used", "noncompleted_v5_files_opened",
    "v5_noncompleted_failure_logs_inspected",
    "v5_failure_detailed_accounting_inspected",
    "v8_success_resource_accounting_recorded",
    "source_support_outcomes_used_for_v8_design",
    "accepted_translation_statuses",
    "translator_timeout_is_infrastructure_failure",
    "resource_ceiling_changes_accepted_outcome_classes",
    "source_audit_runtime_estimand_recorded",
    "cross_campaign_runtime_comparison_authorized",
    "scheduler_membership_affects_execution_origin_only",
    "v6_runtime_artifacts_used", "v7_runtime_artifacts_used",
    "v8_design_timing_disclosure", "v7_launch_intent_sha256",
    "v7_launch_failure_sha256", "sbatch_result_sha256",
    "v5_output_namespace_enumerated_by_v8",
    "v5_output_triplet_bytes_read_before_v8_all_success_gate",
    "v5_reusable_triplet_bytes_read_during_seal_after_v8_all_success_gate",
    "v5_source_inventory_read_by_v8",
    "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion",
    "v5_reusable_selected_tree_first_separately_recorded_at_v8_seal",
    "path_containment_trust_model",
    "reuse_eligibility_rule",
    "repair_eligibility_rule", "pre_diagnosis_freeze",
    "seal_recovery_protocol", "seal_plan_sha256",
    "union_root_stage_sha256", "union_stage_sha256",
    "candidate_stage_sha256", "attestation_stage_sha256",
    "launch_receipt_sha256", "v5_scheduler_diagnostic_sha256",
    "v5_launch_receipt_sha256", "v5_job_id", "v8_job_id",
    "reused_v1_shards", "reused_v2_shards", "reused_v3_shards",
    "reused_v4_shards", "reused_v5_shards", "reused_v6_shards",
    "reused_v7_shards",
    "reusable_v5_shard_indices", "repaired_v5_shards",
    "repair_v5_shard_indices", "repair_scope", "array_throttle",
    "resource_mapping", "scheduler_state_counts", "scheduler_rows",
    "scheduler_contract_rows", "v5_reusable_tree", "v8_output_tree",
    "v5_reusable_environment_manifest", "v8_repair_environment_manifest",
    "union_sources", "union_sources_sha256", "union_tree",
    "source_inventory_sha256", "v5_code_manifest_sha256",
    "v8_code_manifest_sha256", "execution_environment",
    "source_audit_complete", "confirmation_prelaunch_authorized",
    "prelaunch_gate", "attestation_sha256",
    "attestation_records_sha256", "cohort_manifest_sha256", "counts",
    "translation_status_counts", "support_exclusion_counts",
})


@dataclass(frozen=True)
class ValidatedSource:
    attestation_path: Path
    diagnostic_path: Path
    intent_path: Path
    execution_receipt_path: Path
    launch_receipt_path: Path
    attestation_raw: bytes
    diagnostic_raw: bytes
    intent_raw: bytes
    execution_raw: bytes
    launch_raw: bytes
    inventory_raw: bytes
    attestation: dict
    diagnostic: dict
    intent: dict
    execution: dict
    launch: dict
    inventory: dict
    tracked_file_sha256: dict[str, str]


SnapshotReader = Callable[[str, list[str]], dict[str, bytes]]


def _canonical_json_line(value) -> bytes:
    return Launch._canonical_json(value)


def _digest(value) -> str:
    return hashlib.sha256(_canonical_json_line(value)).hexdigest()


def _read_json(path: Path, expected: Path, label: str) -> tuple[bytes, dict]:
    try:
        loaded, value = SafeIO.read_canonical_json(
            path, label=label, expected_path=expected, root=REPO,
            canonical_json_line=_canonical_json_line,
        )
    except SafeIO.SafeReadError as err:
        raise SourceConsumerError(str(err)) from err
    return loaded.raw, value


def _read_file(path: Path, expected: Path, label: str):
    try:
        return SafeIO.read_regular_file(
            path, label=label, expected_path=expected, root=REPO
        )
    except SafeIO.SafeReadError as err:
        raise SourceConsumerError(str(err)) from err


def _root_identity(value, expected: Path) -> bool:
    return V6Utilities._root_identity(value, expected)


def _validate_snapshot(
    revision: str, files: tuple[str, ...], tracked: dict[str, str],
    snapshot_reader: SnapshotReader, label: str,
) -> None:
    try:
        V6Utilities._validate_snapshot(
            revision, files, tracked, snapshot_reader, label
        )
    except V6Utilities.SourceConsumerError as err:
        raise SourceConsumerError(str(err)) from err


def _manifest(launch_receipt: dict, diagnostic: dict):
    loaded = _read_file(CODE_MANIFEST, CODE_MANIFEST, "V8 code manifest")
    if (
        not isinstance(launch_receipt.get("code_manifest_sha256"), str)
        or SHA256_RE.fullmatch(launch_receipt["code_manifest_sha256"]) is None
        or loaded.sha256 != launch_receipt["code_manifest_sha256"]
    ):
        raise SourceConsumerError("V8 code-manifest hash chain changed")
    try:
        lines = loaded.raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise SourceConsumerError("V8 code manifest is not ASCII") from err
    records = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([!-~]+)", line)
        if match is None or match.group(2) in records:
            raise SourceConsumerError("V8 code manifest is malformed")
        records[match.group(2)] = match.group(1)
    if (
        not loaded.raw.endswith(b"\n")
        or tuple(sorted(records)) != CODE_MANIFEST_FILES
    ):
        raise SourceConsumerError("V8 code-manifest file set changed")
    # The complete design closure is authenticated below from the pinned
    # launch revision.  Only modules executed for live semantic replay must
    # still match in the descendant working copy; paper/result renderers may
    # evolve after seal without invalidating the producer revision.
    for relative in LIVE_SEMANTIC_REPLAY_FILES:
        expected = records.get(relative)
        path = REPO / relative
        if (
            expected is None
            or _read_file(
                path, path, "V8 live semantic replay dependency"
            ).sha256 != expected
        ):
            raise SourceConsumerError("V8 live semantic replay code changed")
    v5_launch = diagnostic["v5_launch_receipt"]
    code = {
        "code_manifest_sha256": loaded.sha256,
        "python_version": v5_launch["python_version"],
        "python_executable": v5_launch["python_executable"],
        "python_executable_sha256": v5_launch["python_executable_sha256"],
        "python_environment_sha256": v5_launch["python_environment_sha256"],
        "python_distributions": v5_launch["python_distributions"],
        "python_requirements_sha256": v5_launch["python_requirements_sha256"],
    }
    return records, code


def _load_diagnostic() -> tuple[bytes, dict]:
    raw, diagnostic = _read_json(
        DIAGNOSTIC, DIAGNOSTIC, "V8 scheduler diagnostic"
    )
    try:
        # The producer revision, not the descendant working copy, owns the
        # complete prediagnosis design closure.  load_v8_source authenticates
        # its recorded hashes through snapshot_reader immediately below.
        digest, validated = Launch._load_recorded_diagnostic()
    except (Launch.LaunchAuditError, Source.SourceAuditError) as err:
        raise SourceConsumerError("invalid V8 scheduler diagnostic") from err
    if (
        diagnostic != validated
        or hashlib.sha256(raw).hexdigest() != digest
        or set(diagnostic) != set(Launch.DIAGNOSTIC_FIELDS)
        or any(key in diagnostic for key in (
            "failure_records", "failure_classes", "v5_output_manifest",
        ))
    ):
        raise SourceConsumerError("V8 scheduler diagnostic byte chain changed")
    return raw, diagnostic


def _validate_launch(
    diagnostic_raw: bytes, diagnostic: dict, intent_raw: bytes,
    intent: dict, launch_raw: bytes, launch_receipt: dict,
):
    try:
        capture_identities = Launch._validate_capture_initial_identities(
            intent.get("sbatch_capture_initial_identities")
            if type(intent) is dict else None
        )
        result_sha, result = Launch._load_sbatch_result(intent_raw, intent)
    except Launch.LaunchAuditError as err:
        raise SourceConsumerError("V8 sbatch evidence changed") from err
    if (
        type(intent) is not dict or set(intent) != INTENT_KEYS
        or type(launch_receipt) is not dict or set(launch_receipt) != LAUNCH_KEYS
        or intent.get("schema") != Launch.LAUNCH_SCHEMA + "/intent"
        or launch_receipt.get("schema") != Launch.LAUNCH_SCHEMA
        or launch_receipt != {
            "schema": Launch.LAUNCH_SCHEMA,
            **{key: value for key, value in intent.items() if key != "schema"},
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "sbatch_result_sha256": result_sha,
            "launch_recovered_from_journal": launch_receipt.get(
                "launch_recovered_from_journal"
            ),
            "job_id": launch_receipt.get("job_id"),
        }
        or TOKEN_RE.fullmatch(intent.get("submission_token", "")) is None
        or not isinstance(intent.get("recorded_utc"), str)
        or not isinstance(launch_receipt.get("job_id"), str)
        or not launch_receipt["job_id"].isdigit()
        or type(launch_receipt.get("launch_recovered_from_journal")) is not bool
        or (
            launch_receipt.get("launch_recovered_from_journal") is False
            and (
                result is None
                or result.get("accepted_by_launcher") is not True
                or result.get("parsed_job_id") != launch_receipt["job_id"]
            )
        )
        or (
            launch_receipt.get("launch_recovered_from_journal") is True
            and result.get("parsed_job_id") is not None
            and result.get("parsed_job_id") != launch_receipt["job_id"]
        )
        or COMMIT_RE.fullmatch(
            launch_receipt.get("repository_commit_id", "")
        ) is None
    ):
        raise SourceConsumerError("V8 launch/intent chain changed")
    reusable = diagnostic["reusable_v5_shard_indices"]
    repair = diagnostic["repair_v5_shard_indices"]
    fixed = {
        "campaign": CAMPAIGN,
        "benchmark_revision": Source.Base.Inventory.BENCHMARK_REVISION,
        "v5_scheduler_diagnostic_sha256": hashlib.sha256(
            diagnostic_raw
        ).hexdigest(),
        "v5_launch_receipt_sha256": diagnostic["v5_launch_receipt_sha256"],
        "logical_shards": ARRAY_TASKS, "candidates": CANDIDATES,
        "reusable_v5_shard_indices": reusable,
        "repair_v5_shard_indices": repair,
        "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "reused_v5_shards": len(reusable), "reused_v6_shards": 0,
        "reused_v7_shards": 0,
        "repaired_v5_shards": len(repair),
        "reuse_eligibility_rule": "scheduler state COMPLETED with exit 0:0 only",
        "repair_scope": "complete original two-candidate shards",
        "whole_campaign_rerun": False,
        "source_support_outcome_blind_selective_repair": True,
        "noncompleted_v5_shards_used": False,
        "array": Launch.Runtime._array_spec(repair), "array_throttle": 0,
        "partition": "fat", "qos": "normal", "account": Launch.ACCOUNT,
        "cpus_per_task": 1, "resource_mapping": Launch._resource_mapping(),
        "source_inventory_sha256": diagnostic["v5_source_inventory_sha256"],
        "scoped_repository_files": list(SCOPED_FILES),
        "output_dir": str(OUTPUT_DIR), "tmpdir_root": str(TMP_ROOT),
        "source_inventory_path": str(SOURCE_INVENTORY),
        "candidate_attestation": str(CANDIDATE),
        "frozen_attestation": str(ATTESTATION),
        "slurm_submission_mode": "stdin",
        "scheduler_only_partition": True,
        "v5_failure_logs_inspected_by_v8": False,
        "v5_detailed_accounting_inspected_by_v8": False,
        "source_support_outcomes_used_for_v8_design": False,
        "accepted_translation_statuses": list(
            Launch.ACCEPTED_TRANSLATION_STATUSES
        ),
        "translator_timeout_is_infrastructure_failure": True,
        "resource_ceiling_changes_accepted_outcome_classes": False,
        "source_audit_runtime_estimand_recorded": False,
        "cross_campaign_runtime_comparison_authorized": False,
        "scheduler_membership_affects_execution_origin_only": True,
        "v6_runtime_artifacts_used": False,
        "v5_scheduler_rows_sha256": diagnostic["v5_scheduler_rows_sha256"],
        "v8_design_timing_disclosure": Launch._design_timing_disclosure(),
        "v7_launch_intent_sha256": Launch.V7_INTENT_SHA256,
        "v7_launch_failure_sha256": Launch.V7_LAUNCH_FAILURE_SHA256,
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
        "path_containment_trust_model": Launch._path_containment_trust_model(),
        "sbatch_stdout_path": str(Launch.SBATCH_STDOUT),
        "sbatch_stderr_path": str(Launch.SBATCH_STDERR),
        "sbatch_result_path": str(Launch.SBATCH_RESULT),
        "sbatch_capture_initial_identities": capture_identities,
    }
    if (
        any(type(launch_receipt.get(key)) is not type(value)
            or launch_receipt.get(key) != value for key, value in fixed.items())
        or launch_receipt.get("submit_command")
        != Launch.Runtime._submit_command(
            diagnostic, launch_receipt["submission_token"]
        )
        or not _root_identity(
            launch_receipt.get("launch_root_identities", {}).get("output_dir"),
            OUTPUT_DIR,
        )
        or not _root_identity(
            launch_receipt.get("launch_root_identities", {}).get("tmpdir_root"),
            TMP_ROOT,
        )
    ):
        raise SourceConsumerError("V8 launch material changed")
    records, code = _manifest(launch_receipt, diagnostic)
    try:
        rendered = Launch.Runtime._render_slurm(
            launch_receipt["code_manifest_sha256"],
            Source.TASK_TIMEOUT_SECONDS,
        )
    except Launch.LaunchAuditError as err:
        raise SourceConsumerError("V8 Slurm template changed") from err
    template = _read_file(SLURM_TEMPLATE, SLURM_TEMPLATE, "V8 Slurm template")
    if (
        launch_receipt.get("slurm_template_sha256") != template.sha256
        or launch_receipt.get("slurm_program_sha256")
        != hashlib.sha256(rendered).hexdigest()
        or launch_receipt.get("slurm_program_bytes") != len(rendered)
        or launch_receipt.get("execution_environment")
        != Launch.Runtime._execution_environment(code)
    ):
        raise SourceConsumerError("V8 Slurm/environment chain changed")
    return records


def _generic_file_map(tree: dict, label: str) -> dict[str, dict]:
    try:
        return V6Utilities._file_map(tree, label)
    except V6Utilities.SourceConsumerError as err:
        raise SourceConsumerError(str(err)) from err


def _validate_complete_tree(
    receipt: dict, root: Path, paths: list[str], expected_root: dict, label: str,
    *, read_callback=None,
) -> dict[str, dict]:
    records = _generic_file_map(receipt, label)
    if set(records) != set(paths) or receipt["root_identity"] != expected_root:
        raise SourceConsumerError("{} file set changed".format(label))
    try:
        options = {"label": label, "expected_path": root}
        if read_callback is not None:
            options["read_callback"] = read_callback
        tree = CompleteTreeIO.read_streaming_tree(root, **options)
    except CompleteTreeIO.SafeTreeError as err:
        raise SourceConsumerError(str(err)) from err
    actual = tree.root_identity
    if (
        tree.directories
        or [item.path for item in tree.files] != sorted(paths)
        or actual["device"] != expected_root["device"]
        or actual["inode"] != expected_root["inode"]
        or actual["uid"] != expected_root["uid"]
        or not stat.S_ISDIR(actual["mode"])
        or stat.S_IMODE(actual["mode"]) != 0o700
    ):
        raise SourceConsumerError("live {} changed".format(label))
    for item in tree.files:
        if (
            item.sha256 != records[item.path]["sha256"]
            or item.identity["size"] != records[item.path]["bytes"]
        ):
            raise SourceConsumerError("live {} file changed".format(label))
    return records


def _selected_file_map(tree: dict) -> dict[str, dict]:
    files = tree.get("files") if isinstance(tree, dict) else None
    if (
        type(tree) is not dict
        or set(tree) != {
            "sha256", "root_identity", "files_count", "files",
            "selection_rule", "noncompleted_v5_files_opened",
        }
        or type(files) is not list
        or tree.get("files_count") != len(files)
        or tree.get("selection_rule")
        != "V5 scheduler COMPLETED 0:0 triplets only"
        or tree.get("noncompleted_v5_files_opened") is not False
    ):
        raise SourceConsumerError("V5 selected-tree receipt changed")
    records = {}
    digest = hashlib.sha256()
    digest.update(b"root-identity\0" + _canonical_json_line(
        tree["root_identity"]
    ))
    for record in files:
        if (
            type(record) is not dict
            or set(record) != {"path", "bytes", "sha256"}
            or not isinstance(record.get("path"), str)
            or record["path"] in records
            or type(record.get("bytes")) is not int or record["bytes"] < 0
            or SHA256_RE.fullmatch(record.get("sha256", "")) is None
        ):
            raise SourceConsumerError("V5 selected-tree record changed")
        records[record["path"]] = record
        digest.update(record["path"].encode("ascii") + b"\0"
                      + bytes.fromhex(record["sha256"]))
    if (
        [item["path"] for item in files] != sorted(records)
        or tree.get("sha256") != digest.hexdigest()
    ):
        raise SourceConsumerError("V5 selected-tree digest changed")
    return records


def _validate_selected_v5_tree(tree: dict, diagnostic: dict):
    records = _selected_file_map(tree)
    names = Launch._v5_reusable_names(diagnostic)
    expected_root = diagnostic["v5_launch_receipt"][
        "launch_root_identities"
    ]["output_dir"]
    if (
        set(records) != set(names)
        or tree.get("root_identity") != expected_root
        or not _root_identity(expected_root, V5_OUTPUT_DIR)
    ):
        raise SourceConsumerError("V5 reusable selected path set changed")
    try:
        live = SelectedTreeIO.read_selected_flat_tree(
            V5_OUTPUT_DIR, names, label="V5 reusable triplets",
            expected_path=V5_OUTPUT_DIR,
        )
    except SelectedTreeIO.SelectedTreeError as err:
        raise SourceConsumerError(str(err)) from err
    actual = live.root_identity
    if (
        actual["device"] != expected_root["device"]
        or actual["inode"] != expected_root["inode"]
        or actual["uid"] != expected_root["uid"]
        or not stat.S_ISDIR(actual["mode"])
        or stat.S_IMODE(actual["mode"]) != 0o700
    ):
        raise SourceConsumerError("live V5 reusable root changed")
    for item in live.files:
        if (
            item.sha256 != records[item.path]["sha256"]
            or item.identity["size"] != records[item.path]["bytes"]
        ):
            raise SourceConsumerError("live V5 reusable file changed")
    return records


def _validate_scheduler(execution: dict, launch_receipt: dict, repair: list[int]):
    rows = execution.get("scheduler_rows")
    contracts = execution.get("scheduler_contract_rows")
    expected_name = "{}-{}".format(
        Launch.JOB_NAME_PREFIX, launch_receipt["submission_token"]
    )
    if (
        type(rows) is not list or type(contracts) is not list
        or len(rows) != len(repair) or len(contracts) != len(repair)
        or execution.get("scheduler_state_counts") != {"COMPLETED": len(repair)}
    ):
        raise SourceConsumerError("V8 scheduler receipt changed")
    for index, row, contract in zip(repair, rows, contracts):
        if (
            row != {"array_task": index, "state": "COMPLETED",
                    "exit_code": "0:0", "partition": "fat"}
            or type(contract) is not dict
            or set(contract) != {
                "array_task", "account", "partition", "qos", "req_cpus",
                "req_mem", "time_limit", "elapsed", "state", "exit_code",
                "job_name",
            }
            or contract.get("array_task") != index
            or contract.get("account") != Launch.ACCOUNT
            or contract.get("partition") != "fat"
            or contract.get("qos") != "normal"
            or contract.get("req_cpus") != 1
            or contract.get("req_mem") != "2950G"
            or contract.get("time_limit") != "3-00:00:00"
            or not Launch.Runtime._valid_elapsed(contract.get("elapsed"))
            or contract.get("state") != "COMPLETED"
            or contract.get("exit_code") != "0:0"
            or contract.get("job_name") != expected_name
        ):
            raise SourceConsumerError("V8 scheduler/resource row changed")


def _validate_environment_manifests(
    execution: dict, launch_receipt: dict, diagnostic: dict,
    v5_files: dict[str, dict], v8_files: dict[str, dict],
):
    specs = (
        (execution.get("v5_reusable_environment_manifest"),
         diagnostic["reusable_v5_shard_indices"], v5_files, V5_OUTPUT_DIR,
         diagnostic["v5_launch_receipt"],
         {"strict_completed_triplet_validation": True,
          "noncompleted_v5_files_opened": False}),
        (execution.get("v8_repair_environment_manifest"),
         diagnostic["repair_v5_shard_indices"], v8_files, OUTPUT_DIR,
         launch_receipt, {"all_repair_tmpdirs_removed_by_rmdir": True}),
    )
    for manifest, indices, files, root, owner, flags in specs:
        records = manifest.get("records") if isinstance(manifest, dict) else None
        if (
            type(manifest) is not dict
            or set(manifest) != {"records", "records_sha256", *flags}
            or any(manifest.get(key) is not value for key, value in flags.items())
            or type(records) is not list or len(records) != len(indices)
            or manifest.get("records_sha256") != _digest(records)
        ):
            raise SourceConsumerError("V5/V8 environment manifest changed")
        for index, record in zip(indices, records):
            shard = "shard-{:04d}-of-0820.json".format(index)
            environment = "environment-{:04d}-of-0820.json".format(index)
            log = "slurm-{}_{}.out".format(owner["job_id"], index)
            expected = {
                "array_task": index,
                "environment_path": environment,
                "environment_sha256": files[environment]["sha256"],
                "shard_path": shard, "shard_sha256": files[shard]["sha256"],
                "slurm_log_path": log,
                "slurm_log_sha256": files[log]["sha256"],
                "tmpdir": str(
                    (Launch.V5Launch.Source.TMP_ROOT if root == V5_OUTPUT_DIR
                     else TMP_ROOT) / "task-{}-{}".format(owner["job_id"], index)
                ),
                "output_dir_identity": owner["launch_root_identities"]["output_dir"],
            }
            if record != expected:
                raise SourceConsumerError("V5/V8 environment record changed")


def _read_bound_union_leaf(
    root_fd: int, name: str, frozen: dict,
) -> bytes:
    """Read one receipt-bound union leaf through the stable tree descriptor."""
    descriptor = None
    try:
        before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise SourceConsumerError("V8 union shard is not regular")
        descriptor = os.open(
            name, CompleteTreeIO._file_flags(), dir_fd=root_fd
        )
        opened = os.fstat(descriptor)
        fingerprint = CompleteTreeIO._fingerprint(opened)
        if fingerprint != CompleteTreeIO._fingerprint(before):
            raise SourceConsumerError("V8 union shard changed before parsing")
        chunks = []
        digest = hashlib.sha256()
        count = 0
        while True:
            block = os.read(descriptor, CompleteTreeIO.CHUNK_BYTES)
            if not block:
                break
            chunks.append(block)
            count += len(block)
            digest.update(block)
        after_fd = os.fstat(descriptor)
        after_path = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if (
            count != frozen.get("bytes")
            or digest.hexdigest() != frozen.get("sha256")
            or CompleteTreeIO._fingerprint(after_fd) != fingerprint
            or CompleteTreeIO._fingerprint(after_path) != fingerprint
        ):
            raise SourceConsumerError("V8 union shard changed while parsing")
        return b"".join(chunks)
    except SourceConsumerError:
        raise
    except OSError as err:
        raise SourceConsumerError("cannot parse V8 union shard safely") from err
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _validate_union(
    execution: dict, diagnostic: dict,
    v5_files: dict[str, dict], v8_files: dict[str, dict],
    attestation: dict, launch_receipt: dict,
):
    sources = execution.get("union_sources")
    reusable = set(diagnostic["reusable_v5_shard_indices"])
    if (
        type(sources) is not list or len(sources) != ARRAY_TASKS
        or execution.get("union_sources_sha256") != _digest(sources)
    ):
        raise SourceConsumerError("V8 union source ledger changed")
    paths = [
        "shard-{:04d}-of-0820.json".format(index)
        for index in range(ARRAY_TASKS)
    ]
    union_tree = execution.get("union_tree")
    root = union_tree.get("root_identity") if isinstance(union_tree, dict) else None
    if not _root_identity(root, UNION_DIR):
        raise SourceConsumerError("V8 union root identity changed")
    frozen_union_files = _generic_file_map(union_tree, "V8 union tree")
    records_from_union = []
    v5_launch = diagnostic["v5_launch_receipt"]
    v5_code = {key: v5_launch.get(key) for key in SHARD_CODE_FIELDS}
    environment = launch_receipt.get("execution_environment")
    v8_code = environment.get("python_environment") \
        if isinstance(environment, dict) else None
    if (
        type(v8_code) is not dict
        or set(v8_code) != set(SHARD_CODE_FIELDS)
        or any(v5_code[key] is None for key in SHARD_CODE_FIELDS)
    ):
        raise SourceConsumerError("V5/V8 shard code provenance changed")

    def parse_union(_root: Path, root_fd: int) -> None:
        for index, name in enumerate(paths):
            raw = _read_bound_union_leaf(
                root_fd, name, frozen_union_files[name]
            )
            try:
                value = json.loads(raw.decode("ascii"))
            except (UnicodeDecodeError, json.JSONDecodeError) as err:
                raise SourceConsumerError("V8 union shard is malformed") from err
            tasks = value.get("tasks") if type(value) is dict else None
            code = v5_code if index in reusable else v8_code
            expected_keys = {
                "schema", "shard_index", "num_shards", "tasks_per_shard",
                "benchmark_revision", "translator_source_sha256",
                "source_inventory_sha256", "tasks", *SHARD_CODE_FIELDS,
            }
            if (
                type(value) is not dict
                or _canonical_json_line(value) != raw
                or set(value) != expected_keys
                or value.get("schema") != Source.Base.SHARD_SCHEMA
                or value.get("shard_index") != index
                or value.get("num_shards") != ARRAY_TASKS
                or value.get("tasks_per_shard") != Source.TASKS_PER_SHARD
                or value.get("benchmark_revision")
                != Source.Base.Inventory.BENCHMARK_REVISION
                or value.get("translator_source_sha256")
                != Source.Base.TRANSLATOR_SOURCE_SHA256
                or value.get("source_inventory_sha256")
                != launch_receipt["source_inventory_sha256"]
                or any(value.get(key) != code[key] for key in SHARD_CODE_FIELDS)
                or type(tasks) is not list
                or len(tasks) != Source.TASKS_PER_SHARD
            ):
                raise SourceConsumerError("V8 union shard contract changed")
            records_from_union.extend(tasks)

    union_files = _validate_complete_tree(
        union_tree, UNION_DIR, paths, root, "V8 union tree",
        read_callback=parse_union,
    )
    for index, item in enumerate(sources):
        is_v5 = index in reusable
        origin = "v5-completed" if is_v5 else "v8-repair"
        root_path = V5_OUTPUT_DIR if is_v5 else OUTPUT_DIR
        file_map = v5_files if is_v5 else v8_files
        expected = {
            "shard_index": index, "origin": origin,
            "source": str(root_path / paths[index]),
            "source_sha256": file_map[paths[index]]["sha256"],
            "union": paths[index],
            "union_sha256": union_files[paths[index]]["sha256"],
        }
        if item != expected or item["source_sha256"] != item["union_sha256"]:
            raise SourceConsumerError("V8 union origin/hash invariant changed")
    attestation_records = attestation.get("records") \
        if isinstance(attestation, dict) else None
    if (
        type(attestation_records) is not list
        or len(records_from_union) != CANDIDATES
        or [record.get("candidate_index") if isinstance(record, dict) else None
            for record in records_from_union] != list(range(CANDIDATES))
        or records_from_union != attestation_records
        or attestation.get("records_sha256") != _digest(attestation_records)
        or execution.get("attestation_records_sha256")
        != attestation["records_sha256"]
    ):
        raise SourceConsumerError("V8 union/attestation record chain changed")


def _validate_timeout_aware_translation_records(
    attestation: dict, execution: dict,
) -> None:
    """Replay each record under the ceiling fixed by its union origin."""
    records = attestation.get("records") if isinstance(attestation, dict) else None
    sources = execution.get("union_sources") \
        if isinstance(execution, dict) else None
    if (
        type(records) is not list
        or len(records) != CANDIDATES
        or type(sources) is not list
        or len(sources) != ARRAY_TASKS
        or Source.TASKS_PER_SHARD * ARRAY_TASKS != CANDIDATES
    ):
        raise SourceConsumerError("V8 timeout-aware record population changed")
    timeout_by_origin = {
        "v5-completed": Launch.V5_TASK_TIMEOUT_SECONDS,
        "v8-repair": Launch.V8_TASK_TIMEOUT_SECONDS,
    }
    previous_timeout = Source.Base.TASK_TIMEOUT_SECONDS
    try:
        for candidate_index, record in enumerate(records):
            shard_index = candidate_index // Source.TASKS_PER_SHARD
            source = sources[shard_index]
            translation = record.get("translation") \
                if isinstance(record, dict) else None
            origin = source.get("origin") if isinstance(source, dict) else None
            expected_timeout = timeout_by_origin.get(origin)
            if (
                not isinstance(source, dict)
                or source.get("shard_index") != shard_index
                or type(record) is not dict
                or record.get("candidate_index") != candidate_index
                or type(translation) is not dict
                or translation.get("status")
                not in Launch.ACCEPTED_TRANSLATION_STATUSES
                or translation.get("timeout_seconds") != expected_timeout
            ):
                raise SourceConsumerError(
                    "V8 origin-aware translation record changed"
                )
            Source.Base.TASK_TIMEOUT_SECONDS = expected_timeout
            try:
                Source.Base._validate_scan_evidence(record)
            except Source.SourceAuditError as err:
                raise SourceConsumerError(
                    "V8 origin-aware translation evidence is invalid"
                ) from err
    finally:
        Source.Base.TASK_TIMEOUT_SECONDS = previous_timeout


def _validate_seal_stages(
    attestation_raw: bytes, attestation: dict, diagnostic: dict,
    launch_raw: bytes, execution: dict,
):
    paths = (
        (SEAL_PLAN, "seal_plan_sha256"),
        (UNION_ROOT_STAGE, "union_root_stage_sha256"),
        (UNION_STAGE, "union_stage_sha256"),
        (CANDIDATE_STAGE, "candidate_stage_sha256"),
        (ATTESTATION_STAGE, "attestation_stage_sha256"),
    )
    values = {}
    for path, field in paths:
        raw, value = _read_json(path, path, "V8 seal stage")
        if hashlib.sha256(raw).hexdigest() != execution.get(field):
            raise SourceConsumerError("V8 seal-stage hash chain changed")
        values[field] = value
    expected_plan = {
        "schema": Launch.SEAL_PLAN_SCHEMA,
        "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
        "v5_scheduler_diagnostic_sha256": execution[
            "v5_scheduler_diagnostic_sha256"
        ],
        "pre_diagnosis_files_sha256": diagnostic[
            "pre_diagnosis_freeze"
        ]["files_sha256"],
        "scheduler_rows": execution["scheduler_rows"],
        "scheduler_contract_rows": execution["scheduler_contract_rows"],
        "v5_reusable_tree": execution["v5_reusable_tree"],
        "v8_output_tree": execution["v8_output_tree"],
        "v5_reusable_environment_manifest": execution[
            "v5_reusable_environment_manifest"
        ],
        "v8_repair_environment_manifest": execution[
            "v8_repair_environment_manifest"
        ],
        "source_record_count": CANDIDATES,
        "source_record_sequence_sha256": attestation["records_sha256"],
    }
    if values["seal_plan_sha256"] != expected_plan:
        raise SourceConsumerError("V8 seal plan changed")
    if values["union_root_stage_sha256"] != {
        "schema": Launch.UNION_ROOT_STAGE_SCHEMA,
        "seal_plan_sha256": execution["seal_plan_sha256"],
        "root_identity": execution["union_tree"]["root_identity"],
    }:
        raise SourceConsumerError("V8 union-root stage changed")
    if values["union_stage_sha256"] != {
        "schema": Launch.UNION_STAGE_SCHEMA,
        "seal_plan_sha256": execution["seal_plan_sha256"],
        "union_root_stage_sha256": execution["union_root_stage_sha256"],
        "sources": execution["union_sources"],
        "sources_sha256": execution["union_sources_sha256"],
        "tree": execution["union_tree"],
    }:
        raise SourceConsumerError("V8 union stage changed")
    candidate = _read_file(CANDIDATE, CANDIDATE, "V8 candidate")
    if (
        candidate.raw != attestation_raw
        or values["candidate_stage_sha256"] != {
            "schema": Launch.CANDIDATE_STAGE_SCHEMA,
            "union_stage_sha256": execution["union_stage_sha256"],
            "candidate_path": str(CANDIDATE),
            "candidate_bytes": len(candidate.raw),
            "candidate_sha256": candidate.sha256,
            "records_sha256": attestation["records_sha256"],
        }
        or values["attestation_stage_sha256"] != {
            "schema": Launch.ATTESTATION_STAGE_SCHEMA,
            "candidate_stage_sha256": execution["candidate_stage_sha256"],
            "attestation_path": str(ATTESTATION),
            "attestation_bytes": len(attestation_raw),
            "attestation_sha256": hashlib.sha256(attestation_raw).hexdigest(),
        }
    ):
        raise SourceConsumerError("V8 candidate/attestation stage changed")


def _validate_execution(
    attestation_raw: bytes, attestation: dict, diagnostic_raw: bytes,
    diagnostic: dict, launch_raw: bytes, launch_receipt: dict, execution: dict,
):
    reusable = diagnostic["reusable_v5_shard_indices"]
    repair = diagnostic["repair_v5_shard_indices"]
    fixed = {
        "schema": Launch.EXECUTION_SCHEMA, "campaign": CAMPAIGN,
        "benchmark_revision": Source.Base.Inventory.BENCHMARK_REVISION,
        "logical_shards": ARRAY_TASKS, "candidates": CANDIDATES,
        "whole_campaign_rerun": False,
        "source_support_outcome_blind_selective_repair": True,
        "noncompleted_v5_shards_used": False,
        "noncompleted_v5_files_opened": False,
        "v5_noncompleted_failure_logs_inspected": False,
        "v5_failure_detailed_accounting_inspected": False,
        "v8_success_resource_accounting_recorded": True,
        "source_support_outcomes_used_for_v8_design": False,
        "accepted_translation_statuses": list(
            Launch.ACCEPTED_TRANSLATION_STATUSES
        ),
        "translator_timeout_is_infrastructure_failure": True,
        "resource_ceiling_changes_accepted_outcome_classes": False,
        "source_audit_runtime_estimand_recorded": False,
        "cross_campaign_runtime_comparison_authorized": False,
        "scheduler_membership_affects_execution_origin_only": True,
        "v6_runtime_artifacts_used": False,
        "v7_runtime_artifacts_used": False,
        "v8_design_timing_disclosure": Launch._design_timing_disclosure(),
        "v7_launch_intent_sha256": Launch.V7_INTENT_SHA256,
        "v7_launch_failure_sha256": Launch.V7_LAUNCH_FAILURE_SHA256,
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
        "path_containment_trust_model": Launch._path_containment_trust_model(),
        "reuse_eligibility_rule": diagnostic["reuse_eligibility_rule"],
        "repair_eligibility_rule": diagnostic["repair_eligibility_rule"],
        "pre_diagnosis_freeze": diagnostic["pre_diagnosis_freeze"],
        "seal_recovery_protocol": "deterministic-exclusive-hash-chain-v1",
        "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
        "v5_scheduler_diagnostic_sha256": hashlib.sha256(
            diagnostic_raw
        ).hexdigest(),
        "v5_launch_receipt_sha256": diagnostic["v5_launch_receipt_sha256"],
        "v5_job_id": diagnostic["v5_launch_receipt"]["job_id"],
        "v8_job_id": launch_receipt["job_id"],
        "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "reused_v5_shards": len(reusable), "reused_v6_shards": 0,
        "reused_v7_shards": 0,
        "reusable_v5_shard_indices": reusable,
        "repaired_v5_shards": len(repair), "repair_v5_shard_indices": repair,
        "repair_scope": "complete original two-candidate shards",
        "array_throttle": 0, "resource_mapping": Launch._resource_mapping(),
        "v5_reusable_tree": execution.get("v5_reusable_tree"),
        "source_inventory_sha256": launch_receipt["source_inventory_sha256"],
        "v5_code_manifest_sha256": diagnostic["v5_code_manifest_sha256"],
        "v8_code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "execution_environment": launch_receipt["execution_environment"],
        "source_audit_complete": True,
    }
    if (
        type(execution) is not dict or set(execution) != EXECUTION_KEYS
        or any(type(execution.get(key)) is not type(value)
               or execution.get(key) != value for key, value in fixed.items())
    ):
        raise SourceConsumerError("V8 execution-receipt chain changed")
    if (
        attestation.get("schema") != ATTESTATION_SCHEMA
        or execution.get("attestation_sha256")
        != hashlib.sha256(attestation_raw).hexdigest()
        or attestation.get("source_inventory_sha256")
        != launch_receipt["source_inventory_sha256"]
        or attestation.get("code_manifest_sha256")
        != launch_receipt["code_manifest_sha256"]
        or execution.get("confirmation_prelaunch_authorized") is not True
        or attestation.get("confirmation_prelaunch_authorized") is not True
        or execution.get("prelaunch_gate") != attestation.get("prelaunch_gate")
        or execution.get("prelaunch_gate", {}).get("passed") is not True
        or execution.get("attestation_records_sha256")
        != attestation.get("records_sha256")
        or execution.get("cohort_manifest_sha256") != {
            name: cohort.get("tasks_sha256")
            for name, cohort in attestation.get("cohorts", {}).items()
        }
        or execution.get("counts") != attestation.get("counts")
        or execution.get("counts", {}).get("candidates") != CANDIDATES
        or type(attestation.get("records")) is not list
        or len(attestation["records"]) != CANDIDATES
        or execution.get("translation_status_counts")
        != attestation.get("translation_status_counts")
        or type(execution.get("translation_status_counts")) is not dict
        or not set(execution["translation_status_counts"]) <= set(
            Launch.ACCEPTED_TRANSLATION_STATUSES
        )
        or any(
            type(count) is not int or count < 0
            for count in execution["translation_status_counts"].values()
        )
        or sum(execution["translation_status_counts"].values()) != CANDIDATES
        or execution.get("support_exclusion_counts")
        != attestation.get("support_exclusion_counts")
    ):
        raise SourceConsumerError("V8 attestation/cohort provenance changed")
    for field in (
        "seal_plan_sha256", "union_root_stage_sha256", "union_stage_sha256",
        "candidate_stage_sha256", "attestation_stage_sha256",
    ):
        if SHA256_RE.fullmatch(execution.get(field, "")) is None:
            raise SourceConsumerError("V8 seal-stage hash changed")
    _validate_seal_stages(
        attestation_raw, attestation, diagnostic, launch_raw, execution
    )
    _validate_scheduler(execution, launch_receipt, repair)
    v5_files = _validate_selected_v5_tree(
        execution["v5_reusable_tree"], diagnostic
    )
    expected_v8 = [SOURCE_INVENTORY.name]
    for index in repair:
        expected_v8.extend((
            "shard-{:04d}-of-0820.json".format(index),
            "environment-{:04d}-of-0820.json".format(index),
            "slurm-{}_{}.out".format(launch_receipt["job_id"], index),
        ))
    v8_files = _validate_complete_tree(
        execution["v8_output_tree"], OUTPUT_DIR, sorted(expected_v8),
        launch_receipt["launch_root_identities"]["output_dir"],
        "V8 repair output tree",
    )
    if v8_files[SOURCE_INVENTORY.name]["sha256"] != launch_receipt[
        "source_inventory_sha256"
    ]:
        raise SourceConsumerError("V8 repair inventory changed")
    _validate_environment_manifests(
        execution, launch_receipt, diagnostic, v5_files, v8_files
    )
    _validate_union(
        execution, diagnostic, v5_files, v8_files,
        attestation, launch_receipt,
    )
    _validate_timeout_aware_translation_records(attestation, execution)


def _validate_inventory_manifest(inventory: dict) -> None:
    try:
        inventory_records = Source.Base.validate_inventory_manifest(inventory)
    except (
        Source.SourceAuditError,
        Source.Base.Inventory.InventoryError,
    ) as err:
        raise SourceConsumerError("V8 rebuilt inventory is invalid") from err
    if inventory_records != inventory.get("records"):
        raise SourceConsumerError("V8 rebuilt inventory records changed")


def _validate_v5_producer_ancestry(
    diagnostic: dict, snapshot_reader: SnapshotReader,
) -> dict[str, str]:
    """Apply the unchanged V6 ancestry validator under V5's LF encoding."""
    try:
        return Source.validate_with_historical_v5_diagnostic_encoding(
            V6Utilities.V5, V6Utilities._validate_v5_producer,
            diagnostic, snapshot_reader,
        )
    except V6Utilities.SourceConsumerError as err:
        raise SourceConsumerError("invalid V5 producer ancestry") from err


def load_v8_source(
    attestation_path: Path, execution_receipt_path: Path,
    launch_receipt_path: Path, *, snapshot_reader: SnapshotReader,
) -> ValidatedSource:
    attestation_raw, attestation = _read_json(
        attestation_path, ATTESTATION, "V8 source attestation"
    )
    execution_raw, execution = _read_json(
        execution_receipt_path, EXECUTION_RECEIPT, "V8 execution receipt"
    )
    launch_raw, launch_receipt = _read_json(
        launch_receipt_path, LAUNCH_RECEIPT, "V8 launch receipt"
    )
    intent_raw, intent = _read_json(INTENT, INTENT, "V8 launch intent")
    diagnostic_raw, diagnostic = _load_diagnostic()
    pre = diagnostic["pre_diagnosis_freeze"]
    pre_tracked = {item["path"]: item["sha256"] for item in pre["files"]}
    if set(pre_tracked) != set(Launch.PRE_DIAGNOSIS_FILES):
        raise SourceConsumerError("V8 prediagnosis closure changed")
    _validate_snapshot(
        pre["repository_commit_id"], Launch.PRE_DIAGNOSIS_FILES,
        pre_tracked, snapshot_reader, "V8 prediagnosis",
    )
    _validate_v5_producer_ancestry(diagnostic, snapshot_reader)
    manifest = _validate_launch(
        diagnostic_raw, diagnostic, intent_raw, intent,
        launch_raw, launch_receipt,
    )
    if any(
        manifest.get(path) != pre_tracked[path]
        for path in Launch.PRE_DIAGNOSIS_FILES
    ):
        raise SourceConsumerError(
            "V8 prediagnosis freeze differs from launch manifest"
        )
    runtime_inputs = {
        Launch.DIAGNOSTIC_RELATIVE_PATH: hashlib.sha256(
            diagnostic_raw
        ).hexdigest(),
        Launch.V5_CODE_MANIFEST.relative_to(REPO).as_posix(): diagnostic[
            "v5_code_manifest_sha256"
        ],
        Launch.V5_INTENT.relative_to(REPO).as_posix(): diagnostic[
            "v5_launch_intent_sha256"
        ],
        Launch.V5_LAUNCH_RECEIPT.relative_to(REPO).as_posix(): diagnostic[
            "v5_launch_receipt_sha256"
        ],
    }
    if (
        set(runtime_inputs) != set(Launch._V5_RUNTIME_INPUTS)
        or set(pre_tracked) & set(runtime_inputs)
        or not (
            set(pre_tracked) | set(runtime_inputs)
        ) <= set(CODE_MANIFEST_FILES)
        or any(manifest.get(path) != digest
               for path, digest in runtime_inputs.items())
    ):
        raise SourceConsumerError(
            "V8 launch-input manifest ancestry changed"
        )
    v8_additions = set(CODE_MANIFEST_FILES) - set(pre_tracked) - set(runtime_inputs)
    required_additions = {
        Launch.V7_LAUNCH_INTENT.relative_to(REPO).as_posix(),
        Launch.V7_LAUNCH_FAILURE.relative_to(REPO).as_posix(),
        Launch.V7Launch.CODE_MANIFEST.relative_to(REPO).as_posix(),
        "experiments/audit_pdb_terminal_incidence_confirmation_sources_v8.py",
        "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v8.py",
        "experiments/pdb_terminal_incidence_confirmation_source_consumer_v8.py",
        "experiments/pdb_terminal_incidence_confirmation_source_scan_v8.slurm",
        "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v8.py",
        "experiments/test_pdb_terminal_incidence_confirmation_source_consumer_v8.py",
    }
    if (
        v8_additions and not required_additions <= v8_additions
        or any(path not in manifest for path in v8_additions)
    ):
        raise SourceConsumerError("V8 infrastructure closure changed")
    inventory_raw, inventory = _read_json(
        SOURCE_INVENTORY, SOURCE_INVENTORY, "V8 source inventory"
    )
    if (
        hashlib.sha256(inventory_raw).hexdigest()
        != launch_receipt["source_inventory_sha256"]
        or attestation.get("source_inventory_sha256")
        != launch_receipt["source_inventory_sha256"]
    ):
        raise SourceConsumerError("V8 rebuilt inventory ancestry changed")
    _validate_inventory_manifest(inventory)
    _validate_execution(
        attestation_raw, attestation, diagnostic_raw, diagnostic,
        launch_raw, launch_receipt, execution,
    )
    tracked = {**manifest, MANIFEST_RELATIVE: launch_receipt["code_manifest_sha256"]}
    if set(tracked) != set(SCOPED_FILES):
        raise SourceConsumerError("V8 scoped producer closure changed")
    _validate_snapshot(
        launch_receipt["repository_commit_id"], SCOPED_FILES,
        tracked, snapshot_reader, "V8",
    )
    return ValidatedSource(
        attestation_path=ATTESTATION, diagnostic_path=DIAGNOSTIC,
        intent_path=INTENT, execution_receipt_path=EXECUTION_RECEIPT,
        launch_receipt_path=LAUNCH_RECEIPT,
        attestation_raw=attestation_raw, diagnostic_raw=diagnostic_raw,
        intent_raw=intent_raw, execution_raw=execution_raw,
        launch_raw=launch_raw, inventory_raw=inventory_raw,
        attestation=attestation, diagnostic=diagnostic, intent=intent,
        execution=execution, launch=launch_receipt, inventory=inventory,
        tracked_file_sha256=dict(sorted(tracked.items())),
    )
