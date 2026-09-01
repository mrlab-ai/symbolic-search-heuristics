#!/usr/bin/env python3
"""Fail-closed shared consumer for the prospective source-audit V5 seal.

The consumer deliberately contains no outcome-dependent constants.  It derives
the launch, execution, and output hashes from the sealed V5 byte chain, then
checks those bytes against the exact producer revision through the caller's
snapshot reader.  Confirmation A and B both use this module.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_safe_io_v5 as TreeIO


class SourceConsumerError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
SCHEMA = (
    "symbolic-search-heuristics/"
    "universal-unseen-confirmation-source-audit/v1"
)
CAMPAIGN = "v5"
ATTESTATION = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v5.json"
)
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v5"
)
INTENT = ARTIFACT_DIR / "source-audit-launch-intent-v5.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-launch-receipt-v5.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v5.json"
CODE_MANIFEST = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v5_code.sha256"
)
SLURM_SCRIPT = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v5.slurm"
)
OUTPUT_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v5"
)
SOURCE_INVENTORY = OUTPUT_DIR / "source-inventory-v5.json"
CANDIDATE = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v5_candidate.json"
)
TMP_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v5_tmp"
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
TOKEN_RE = re.compile(r"^[0-9a-f]{24}$")
NORMALIZED_SLURM_SHA256 = (
    "bc53eed1683e364e078a2075c827c70bf3b48162af4795fa3a29bd98a31437ee"
)
PLANNER_ACCOUNT = "naiss2025-5-561-cpu"
ARRAY_TASKS = 820
CANDIDATES = 1640
MEMORY_PER_CPU = "2T"
TIME_LIMIT = "16:40:00"
TASK_TIMEOUT_SECONDS = 28800

# This is the exact, source-level V5 producer closure.  In particular, it
# expands the immutable V4 manifest rather than trusting that manifest as an
# opaque dependency.
CODE_MANIFEST_FILES = tuple(sorted({
    "experiments/artifacts/pdb-terminal-incidence-confirmation/"
    "source-audit-launch-receipt-v1.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v2/"
    "source-audit-launch-receipt-v2.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v3/"
    "source-audit-launch-intent-v3.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v3/"
    "source-audit-launch-receipt-v3.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
    "source-audit-launch-intent-v4.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
    "source-audit-launch-receipt-v4.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
    "v3-infrastructure-failure-diagnostic.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v5/"
    "v4-infrastructure-failure-diagnostic.json",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v3.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v4.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v5.py",
    "experiments/cancel_pdb_terminal_incidence_confirmation_source_audit_v4_v5.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v4.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py",
    "experiments/pdb_terminal_incidence_confirmation_inventory.py",
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v5.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v3_code.sha256",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v3_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_cancellation_v5_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v5_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v3.slurm",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v4.slurm",
    "experiments/pdb_terminal_incidence_shadow_cost_attestation.json",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit_v4.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit_v5.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/suite_wbh_operator_costs.json",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v4.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v4_cancellation_v5.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v5.py",
}))
SLURM_RELATIVE = SLURM_SCRIPT.relative_to(REPO).as_posix()
MANIFEST_RELATIVE = CODE_MANIFEST.relative_to(REPO).as_posix()
SCOPED_FILES = tuple(sorted({
    *CODE_MANIFEST_FILES, SLURM_RELATIVE, MANIFEST_RELATIVE,
}))
INTENT_KEYS = {
    "schema", "campaign", "whole_campaign_rerun", "reused_v1_shards",
    "reused_v2_shards", "reused_v3_shards", "reused_v4_shards",
    "partition", "qos", "account", "array", "array_throttle",
    "array_tasks", "tasks_per_array_task", "candidates", "cpus_per_task",
    "time_limit", "memory_per_cpu", "task_timeout_seconds",
    "benchmark_revision", "candidate_records_sha256", "alias_groups_sha256",
    "prior_identity_ledger_sha256", "prior_family_ledger_sha256",
    "prior_directory_family_map_sha256",
    "shadow_unrepresented_family_sequence_sha256",
    "all_prior_family_sequence_sha256",
    "all_prior_unrepresented_family_sequence_sha256",
    "translator_source_sha256", "source_inventory_sha256",
    "source_inventory_path", "slurm_script_sha256", "slurm_submission_mode",
    "slurm_stdin_sha256", "slurm_stdin_bytes", "slurm_path_argument",
    "submission_journal_contract", "code_manifest_sha256", "launcher_sha256",
    "repository_commit_id", "scoped_repository_files", "jj_executable",
    "jj_executable_sha256", "sbatch_executable", "sbatch_executable_sha256",
    "sacct_executable", "sacct_executable_sha256", "submission_environment",
    "output_dir", "tmpdir_root", "launch_root_identities",
    "candidate_attestation", "frozen_attestation", "execution_environment",
    "v4_infrastructure_diagnostic_path",
    "v4_infrastructure_diagnostic_sha256", "v4_infrastructure_diagnostic",
    "python_version", "python_executable", "python_executable_sha256",
    "python_environment_sha256", "python_distributions",
    "python_requirements_sha256", "recorded_utc", "submission_token",
    "submit_command",
}
EXECUTION_KEYS = {
    "schema", "campaign", "whole_campaign_rerun", "original_only",
    "recovery", "reused_v1_shards", "reused_v2_shards", "reused_v3_shards",
    "reused_v4_shards", "launch_receipt_sha256", "job_id", "partition",
    "qos", "account", "array", "array_tasks", "tasks_per_array_task",
    "cpus_per_task", "memory_per_cpu", "time_limit", "task_timeout_seconds",
    "array_throttle", "shards", "candidates", "scheduler_state_counts",
    "scheduler_rows", "scheduler_contract_rows", "launch_root_identities",
    "sealing_root_identities_before", "sealing_root_identities_after",
    "original_output_tree", "task_environment_manifest",
    "code_manifest_sha256", "source_inventory_sha256",
    "v4_infrastructure_diagnostic_sha256", "v4_infrastructure_diagnostic",
    "execution_environment", "source_audit_complete",
    "confirmation_prelaunch_authorized", "prelaunch_gate",
    "attestation_sha256", "attestation_records_sha256",
    "cohort_manifest_sha256", "counts", "translation_status_counts",
    "support_exclusion_counts",
}
DIAGNOSTIC_KEYS = {
    "schema", "v4_job_id", "v4_launch_intent_path",
    "v4_launch_intent_sha256", "v4_launch_receipt_path",
    "v4_launch_receipt_sha256", "v4_code_manifest_path",
    "v4_code_manifest_sha256", "v4_slurm_script_path",
    "v4_slurm_script_sha256", "v4_source_inventory_sha256",
    "v4_scheduler_rows", "v4_scheduler_rows_sha256",
    "v4_scheduler_state_counts", "v4_cancelled_array_tasks",
    "v4_cancellation", "v4_failure_logs", "v4_failure_logs_sha256",
    "v4_out_of_memory_array_tasks", "v4_translator_timeout_array_tasks",
    "v4_oom_scheduler_resource_rows",
    "v4_oom_scheduler_resource_rows_sha256",
    "v4_timeout_scheduler_resource_rows",
    "v4_timeout_scheduler_resource_rows_sha256", "failure_classes",
    "inspection_scope", "successful_v4_shard_contents_inspected",
    "successful_v4_log_contents_inspected",
    "cancelled_v4_log_contents_inspected",
    "source_support_outcomes_used_for_v5_design", "resource_amendment",
    "scheduler_memory_geometry", "full_rerun_decision",
}


@dataclass(frozen=True)
class ValidatedSource:
    attestation_path: Path
    intent_path: Path
    execution_receipt_path: Path
    launch_receipt_path: Path
    attestation_raw: bytes
    intent_raw: bytes
    execution_raw: bytes
    launch_raw: bytes
    inventory_raw: bytes
    attestation: dict
    intent: dict
    execution: dict
    launch: dict
    inventory: dict
    tracked_file_sha256: dict[str, str]


SnapshotReader = Callable[[str, list[str]], dict[str, bytes]]


def _canonical_json_line(value) -> bytes:
    import json
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii") + b"\n"
    except (TypeError, ValueError) as err:
        raise SourceConsumerError("value is not canonical finite JSON") from err


def _canonical_json(value) -> bytes:
    return _canonical_json_line(value)[:-1]


def _same(actual, expected) -> bool:
    return type(actual) is type(expected) and actual == expected


def _read_json(path: Path, expected: Path, label: str) -> tuple[bytes, dict]:
    try:
        loaded, value = SafeIO.read_canonical_json(
            path, label=label, expected_path=expected, root=REPO,
            canonical_json_line=_canonical_json_line,
        )
    except SafeIO.SafeReadError as err:
        raise SourceConsumerError(str(err)) from err
    return loaded.raw, value


def _read_file(path: Path, expected: Path, label: str) -> SafeIO.RegularFile:
    try:
        return SafeIO.read_regular_file(
            path, label=label, expected_path=expected, root=REPO
        )
    except SafeIO.SafeReadError as err:
        raise SourceConsumerError(str(err)) from err


def _root_identity(value, expected_path: Path) -> bool:
    return (
        type(value) is dict
        and set(value) == {
            "path", "canonical_path", "uid", "mode", "device", "inode",
        }
        and value.get("path") == str(expected_path)
        and value.get("canonical_path") == str(expected_path)
        and value.get("mode") == "0700"
        and all(
            type(value.get(key)) is int and value[key] >= 0
            for key in ("uid", "device", "inode")
        )
    )


def _executable_identity(path_value, digest, label: str) -> None:
    if (
        not isinstance(path_value, str)
        or not Path(path_value).is_absolute()
        or SHA256_RE.fullmatch(digest or "") is None
    ):
        raise SourceConsumerError("{} executable identity changed".format(label))
    try:
        loaded = SafeIO.read_regular_file(
            Path(path_value), label="{} executable".format(label),
            expected_path=Path(path_value),
        )
    except SafeIO.SafeReadError as err:
        raise SourceConsumerError(str(err)) from err
    if loaded.sha256 != digest:
        raise SourceConsumerError("{} executable identity changed".format(label))


def _validate_execution_environment(launch: dict) -> None:
    environment = launch.get("execution_environment")
    tmp_template = str(TMP_ROOT / "task-{array_job_id}-{array_task_id}")
    cache_template = tmp_template + "/pycache"
    snapshot_policy = {
        "scope": "one domain/problem snapshot tree per candidate",
        "location": "inside the exact per-array-task TMPDIR",
        "directory_mode": "0700", "file_mode": "0400",
        "consumers": ["translator", "axiom_based normalization"],
        "verify_before_each_consumer": True,
        "verify_identity_and_sha256_after_use": True,
        "cleanup": "unlink exact files, then rmdir exact directories; no recursion",
    }
    fixed = {
        "submission_export": "NONE", "slurm_export": "NONE",
        "unset_variables": ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"],
        "python_no_user_site": "1", "python_no_user_site_flag": 1,
        "python_dont_write_bytecode": "1",
        "python_dont_write_bytecode_flag": True,
        "tmpdir_root": str(TMP_ROOT), "tmpdir_template": tmp_template,
        "python_tempfile_directory_template": tmp_template,
        "python_pycache_prefix_template": cache_template,
        "tmpdir_mode": "0700",
        "tmpdir_cleanup": "EXIT trap with pinned /usr/bin/rmdir; no recursion",
        "root_identity_policy": (
            "canonical absolute path; no direct/ancestor symlinks; mode 0700; "
            "launch uid/device/inode retained"
        ),
        "source_snapshot_policy": snapshot_policy, "outer_python_flag": "-B",
        "path": "/usr/bin:/bin",
        "translator_child_environment": {
            "PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": tmp_template,
            "PYTHONPYCACHEPREFIX": cache_template,
            "PYTHONPATH": str(REPO / "src"),
        },
        "python_command": str(
            SCRIPT_DIR / "data" / "pdb-terminal-incidence-shadow-venv"
            / "bin" / "python"
        ),
        "sha256sum_command": "/usr/bin/sha256sum",
        "sha256sum_executable": "/usr/bin/sha256sum",
        "sha256sum_executable_sha256": (
            "1950eda10a1bb0c6c2a086ba009b847edec6f30d25eb311b9154ae08819041a9"
        ),
        "mkdir_executable": "/usr/bin/mkdir",
        "mkdir_executable_sha256": (
            "9a71255933f2013dda3fe7e8ad928dc50b7e4c2ae6a7cac58fc1225106c10814"
        ),
        "rmdir_executable": "/usr/bin/rmdir",
        "rmdir_executable_sha256": (
            "b87fd3112c40dd30dca11fa5bc1b3dacc9ed2e309868344dd696824abafc5ded"
        ),
    }
    if (
        type(environment) is not dict
        or set(environment) != set(fixed) | {
            "python_executable", "python_executable_sha256",
        }
        or any(not _same(environment.get(key), value)
               for key, value in fixed.items())
        or launch.get("python_version") != "3.12.13"
        or launch.get("python_executable") != environment.get("python_executable")
        or launch.get("python_executable_sha256")
        != environment.get("python_executable_sha256")
        or SHA256_RE.fullmatch(launch.get("python_environment_sha256", "")) is None
        or SHA256_RE.fullmatch(launch.get("python_requirements_sha256", "")) is None
        or type(launch.get("python_distributions")) is not dict
    ):
        raise SourceConsumerError("V5 execution environment changed")
    for path_field, hash_field, label in (
        ("python_executable", "python_executable_sha256", "Python"),
        ("sha256sum_executable", "sha256sum_executable_sha256", "sha256sum"),
        ("mkdir_executable", "mkdir_executable_sha256", "mkdir"),
        ("rmdir_executable", "rmdir_executable_sha256", "rmdir"),
    ):
        _executable_identity(environment[path_field], environment[hash_field], label)
    for path_field, hash_field, label in (
        ("jj_executable", "jj_executable_sha256", "Jujutsu"),
        ("sbatch_executable", "sbatch_executable_sha256", "sbatch"),
        ("sacct_executable", "sacct_executable_sha256", "sacct"),
    ):
        _executable_identity(launch.get(path_field), launch.get(hash_field), label)


def _validate_diagnostic(launch: dict, manifest: dict[str, str]) -> None:
    relative = (
        "experiments/artifacts/pdb-terminal-incidence-confirmation-v5/"
        "v4-infrastructure-failure-diagnostic.json"
    )
    path = REPO / relative
    raw, diagnostic = _read_json(path, path, "V5 V4-failure diagnostic")
    digest = hashlib.sha256(raw).hexdigest()
    full = diagnostic.get("full_rerun_decision")
    v4_paths = {
        "v4_launch_intent": (
            REPO / "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
            "source-audit-launch-intent-v4.json"
        ),
        "v4_launch_receipt": (
            REPO / "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
            "source-audit-launch-receipt-v4.json"
        ),
        "v4_code_manifest": (
            REPO / "experiments/"
            "pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256"
        ),
        "v4_slurm_script": (
            REPO / "experiments/"
            "pdb_terminal_incidence_confirmation_source_scan_v4.slurm"
        ),
    }
    lists_with_digests = (
        ("v4_scheduler_rows", "v4_scheduler_rows_sha256"),
        ("v4_failure_logs", "v4_failure_logs_sha256"),
        ("v4_oom_scheduler_resource_rows",
         "v4_oom_scheduler_resource_rows_sha256"),
        ("v4_timeout_scheduler_resource_rows",
         "v4_timeout_scheduler_resource_rows_sha256"),
    )
    expected_amendment = {
        "temporary_storage": {
            "from": (
                "project-backed per-candidate snapshots and per-task "
                "temporary directories"
            ),
            "to": str(TMP_ROOT / "task-{array_job_id}-{array_task_id}"),
            "reason": (
                "retain v4's project-backed isolation unchanged; the "
                "classified v4 failure is memory exhaustion, not ENOSPC"
            ),
            "cleanup": "per-task EXIT trap using pinned rmdir only",
        },
        "memory_per_cpu": {
            "from": "1024G", "to": MEMORY_PER_CPU, "factor": 2,
            "reason": (
                "v4 scheduler OOM at 1 TiB; batch MaxRSS and MaxVMSize "
                "are pinned above"
            ),
        },
        "task_timeout_seconds": {
            "from": 14400, "to": TASK_TIMEOUT_SECONDS, "factor": 2,
            "reason": (
                "v4 translator exceeded its 14,400-second source limit; "
                "task/log/accounting evidence is pinned above"
            ),
        },
        "time_limit": {
            "from": "08:20:00", "to": TIME_LIMIT, "factor": 2,
            "reason": "preserve scheduler headroom for doubled source limit",
        },
    }
    expected_geometry = {
        "fat_node_real_memory_mib": 3095813,
        "v5_request_memory_mib": 2048 * 1024,
        "maximum_v5_tasks_per_node_by_memory": 1,
        "array_throttle": 0,
        "interpretation": (
            "the unthrottled array leaves concurrency to Slurm; the "
            "memory request permits at most one v5 task per fat node"
        ),
    }
    if (
        set(diagnostic) != DIAGNOSTIC_KEYS
        or
        launch.get("v4_infrastructure_diagnostic_path") != str(path)
        or launch.get("v4_infrastructure_diagnostic_sha256") != digest
        or manifest.get(relative) != digest
        or launch.get("v4_infrastructure_diagnostic") != diagnostic
        or diagnostic.get("schema")
        != SCHEMA + "/campaign-v5/v4-infrastructure-diagnostic"
        or diagnostic.get("successful_v4_shard_contents_inspected") is not False
        or diagnostic.get("successful_v4_log_contents_inspected") is not False
        or diagnostic.get("cancelled_v4_log_contents_inspected") is not False
        or diagnostic.get("source_support_outcomes_used_for_v5_design") is not False
        or any(
            type(diagnostic.get(field)) is not list
            or diagnostic.get(digest_field)
            != hashlib.sha256(_canonical_json(diagnostic[field])).hexdigest()
            for field, digest_field in lists_with_digests
        )
        or type(diagnostic.get("v4_scheduler_state_counts")) is not dict
        or diagnostic.get("failure_classes") != [
            "scheduler-out-of-memory", "translator-wallclock-timeout",
        ]
        or not isinstance(diagnostic.get("inspection_scope"), str)
        or not diagnostic["inspection_scope"]
        or any(
            diagnostic.get(prefix + "_path") != str(expected_path)
            or diagnostic.get(prefix + "_sha256")
            != manifest.get(expected_path.relative_to(REPO).as_posix())
            for prefix, expected_path in v4_paths.items()
        )
        or diagnostic.get("v4_source_inventory_sha256")
        != launch.get("source_inventory_sha256")
        or diagnostic.get("resource_amendment") != expected_amendment
        or diagnostic.get("scheduler_memory_geometry") != expected_geometry
        or full != {
            "scope": "all-820-original-shards-and-1640-candidates",
            "whole_campaign_rerun": True, "reused_v1_shards": 0,
            "reused_v2_shards": 0, "reused_v3_shards": 0,
            "reused_v4_shards": 0,
        }
    ):
        raise SourceConsumerError("V5 failure diagnostic/no-outcome chain changed")


def _manifest(launch: dict) -> dict[str, str]:
    loaded = _read_file(CODE_MANIFEST, CODE_MANIFEST, "V5 code manifest")
    expected_sha = launch.get("code_manifest_sha256")
    if SHA256_RE.fullmatch(expected_sha or "") is None or loaded.sha256 != expected_sha:
        raise SourceConsumerError("V5 code-manifest hash chain changed")
    try:
        lines = loaded.raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise SourceConsumerError("V5 code manifest is not ASCII") from err
    records: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([!-~]+)", line)
        if match is None or match.group(2) in records:
            raise SourceConsumerError("V5 code manifest is malformed")
        records[match.group(2)] = match.group(1)
    if (
        not loaded.raw.endswith(b"\n")
        or tuple(sorted(records)) != CODE_MANIFEST_FILES
    ):
        raise SourceConsumerError("V5 code-manifest file set changed")
    for relative, expected in records.items():
        path = REPO / relative
        if _read_file(path, path, "V5 manifest dependency").sha256 != expected:
            raise SourceConsumerError("V5 manifest dependency changed")
    return records


def _slurm(launch: dict) -> str:
    loaded = _read_file(SLURM_SCRIPT, SLURM_SCRIPT, "V5 Slurm script")
    expected = launch.get("slurm_script_sha256")
    if (
        SHA256_RE.fullmatch(expected or "") is None
        or loaded.sha256 != expected
        or launch.get("slurm_stdin_sha256") != expected
        or not _same(launch.get("slurm_stdin_bytes"), len(loaded.raw))
        or launch.get("slurm_submission_mode") != "stdin"
        or launch.get("slurm_path_argument") is not False
    ):
        raise SourceConsumerError("V5 Slurm byte chain changed")
    assignments = [
        re.fullmatch(rb'code_manifest_sha256="([0-9a-f]{64})"', line)
        for line in loaded.raw.splitlines()
        if line.startswith(b"code_manifest_sha256=")
    ]
    if len(assignments) != 1 or assignments[0] is None:
        raise SourceConsumerError("V5 Slurm manifest assignment changed")
    manifest_sha = assignments[0].group(1).decode("ascii")
    normalized = loaded.raw.replace(assignments[0].group(1), b"0" * 64, 1)
    if (
        manifest_sha != launch.get("code_manifest_sha256")
        or loaded.raw.count(assignments[0].group(1)) != 1
        or hashlib.sha256(normalized).hexdigest() != NORMALIZED_SLURM_SHA256
    ):
        raise SourceConsumerError("V5 normalized Slurm contract changed")
    return loaded.sha256


def _expected_submit(token: str) -> list[str]:
    return [
        "/usr/bin/sbatch", "--parsable", "--export=NONE",
        "--job-name=confirmation-source-audit-v5-{}".format(token),
        "--comment=confirmation-source-audit-v5/{}".format(token),
        "--account={}".format(PLANNER_ACCOUNT),
        "--partition=fat", "--qos=normal", "--array=0-819",
        "--nodes=1", "--ntasks=1", "--cpus-per-task=1",
        "--mem-per-cpu=2T", "--time=16:40:00", "--nice=0",
        "--no-requeue", "--chdir={}".format(REPO),
        "--output={}".format(OUTPUT_DIR / "slurm-%A_%a.out"),
    ]


def _validate_launch(intent_raw: bytes, intent: dict, launch: dict) -> None:
    token = intent.get("submission_token")
    job_id = launch.get("job_id")
    expected_launch = {
        "schema": SCHEMA + "/campaign-v5/launch",
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": job_id,
    }
    fixed = {
        "campaign": "v5", "whole_campaign_rerun": True,
        "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "partition": "fat", "qos": "normal", "account": PLANNER_ACCOUNT,
        "array": "0-819", "array_throttle": 0,
        "array_tasks": ARRAY_TASKS, "tasks_per_array_task": 2,
        "candidates": CANDIDATES, "cpus_per_task": 1,
        "time_limit": TIME_LIMIT, "memory_per_cpu": MEMORY_PER_CPU,
        "task_timeout_seconds": TASK_TIMEOUT_SECONDS,
        "source_inventory_path": str(SOURCE_INVENTORY),
        "output_dir": str(OUTPUT_DIR), "tmpdir_root": str(TMP_ROOT),
        "candidate_attestation": str(CANDIDATE),
        "frozen_attestation": str(ATTESTATION),
        "scoped_repository_files": list(SCOPED_FILES),
        "slurm_submission_mode": "stdin", "slurm_path_argument": False,
        "submission_journal_contract": "exact sbatch options-only SubmitLine",
    }
    if (
        set(intent) != INTENT_KEYS
        or set(launch) != (INTENT_KEYS - {"schema"}) | {
            "schema", "launch_intent_sha256", "job_id",
        }
        or intent.get("schema") != SCHEMA + "/campaign-v5/launch/intent"
        or launch != expected_launch
        or TOKEN_RE.fullmatch(token or "") is None
        or not isinstance(intent.get("recorded_utc"), str)
        or not isinstance(job_id, str) or not job_id.isdigit()
        or intent.get("submit_command") != _expected_submit(token)
        or any(not _same(intent.get(key), value) for key, value in fixed.items())
        or COMMIT_RE.fullmatch(intent.get("repository_commit_id", "")) is None
        or intent.get("jj_executable") != "/home/jendrik/bin/jj"
        or intent.get("sbatch_executable") != "/usr/bin/sbatch"
        or intent.get("sacct_executable") != "/usr/bin/sacct"
        or intent.get("submission_environment")
        != {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"}
        or not _root_identity(
            intent.get("launch_root_identities", {}).get("output_dir"),
            OUTPUT_DIR,
        )
        or not _root_identity(
            intent.get("launch_root_identities", {}).get("tmpdir_root"),
            TMP_ROOT,
        )
    ):
        raise SourceConsumerError("V5 launch/intent chain changed")
    for field in (
        "source_inventory_sha256", "slurm_script_sha256",
        "slurm_stdin_sha256", "code_manifest_sha256", "launcher_sha256",
        "jj_executable_sha256", "sbatch_executable_sha256",
        "sacct_executable_sha256", "translator_source_sha256",
        "v4_infrastructure_diagnostic_sha256",
    ):
        if SHA256_RE.fullmatch(intent.get(field, "")) is None:
            raise SourceConsumerError("V5 launch hash field changed")
    _validate_execution_environment(launch)


def _validate_scheduler(execution: dict, launch: dict) -> None:
    rows = execution.get("scheduler_rows")
    resources = execution.get("scheduler_contract_rows")
    expected_name = "confirmation-source-audit-v5-{}".format(
        launch["submission_token"]
    )
    if (
        type(rows) is not list or len(rows) != ARRAY_TASKS
        or type(resources) is not list or len(resources) != ARRAY_TASKS
        or execution.get("scheduler_state_counts") != {"COMPLETED": ARRAY_TASKS}
    ):
        raise SourceConsumerError("V5 scheduler journal changed")
    for index, (row, resource) in enumerate(zip(rows, resources)):
        if (
            type(row) is not dict
            or set(row) != {
                "array_task", "state", "exit_code", "elapsed", "partition",
            }
            or not _same(row.get("array_task"), index)
            or row.get("state") != "COMPLETED"
            or row.get("exit_code") != "0:0"
            or row.get("partition") != "fat"
            or not isinstance(row.get("elapsed"), str) or not row["elapsed"]
            or type(resource) is not dict
            or set(resource) != {
                "array_task", "account", "partition", "qos", "req_cpus",
                "req_mem", "time_limit", "state", "exit_code", "job_name",
            }
            or not _same(resource.get("array_task"), index)
            or resource.get("account") != PLANNER_ACCOUNT
            or resource.get("partition") != "fat"
            or resource.get("qos") != "normal"
            or not _same(resource.get("req_cpus"), 1)
            or resource.get("req_mem") != MEMORY_PER_CPU
            or resource.get("time_limit") != TIME_LIMIT
            or resource.get("state") != row["state"]
            or resource.get("exit_code") != row["exit_code"]
            or resource.get("job_name") != expected_name
        ):
            raise SourceConsumerError("V5 scheduler journal changed")


def _validate_output_tree(execution: dict, launch: dict) -> None:
    receipt = execution.get("original_output_tree")
    root = launch["launch_root_identities"]["output_dir"]
    expected_paths = sorted([
        "source-inventory-v5.json",
        *("shard-{:04d}-of-0820.json".format(i) for i in range(ARRAY_TASKS)),
        *("environment-{:04d}-of-0820.json".format(i) for i in range(ARRAY_TASKS)),
        *("slurm-{}_{}.out".format(launch["job_id"], i)
          for i in range(ARRAY_TASKS)),
    ])
    if (
        type(receipt) is not dict
        or set(receipt) != {"sha256", "root_identity", "files_count", "files"}
        or receipt.get("root_identity") != root
        or not _same(receipt.get("files_count"), len(expected_paths))
        or type(receipt.get("files")) is not list
        or len(receipt["files"]) != len(expected_paths)
        or SHA256_RE.fullmatch(receipt.get("sha256", "")) is None
    ):
        raise SourceConsumerError("V5 output-tree receipt changed")
    digest = hashlib.sha256()
    digest.update(b"root-identity\0" + _canonical_json(root))
    records = {}
    for record, expected_path in zip(receipt["files"], expected_paths):
        if (
            type(record) is not dict
            or set(record) != {"path", "bytes", "sha256"}
            or record.get("path") != expected_path
            or type(record.get("bytes")) is not int or record["bytes"] < 0
            or SHA256_RE.fullmatch(record.get("sha256", "")) is None
        ):
            raise SourceConsumerError("V5 output-tree record changed")
        records[expected_path] = record
        digest.update(
            expected_path.encode("ascii") + b"\0"
            + bytes.fromhex(record["sha256"])
        )
    if (
        digest.hexdigest() != receipt["sha256"]
        or records["source-inventory-v5.json"]["sha256"]
        != launch["source_inventory_sha256"]
    ):
        raise SourceConsumerError("V5 output-tree digest changed")
    try:
        tree = TreeIO.read_regular_tree(
            OUTPUT_DIR, label="sealed V5 output tree",
            expected_path=OUTPUT_DIR, root=REPO,
        )
    except TreeIO.SafeReadError as err:
        raise SourceConsumerError(str(err)) from err
    actual_identity = tree.root_identity
    if (
        tree.directories
        or [item.path for item in tree.files] != expected_paths
        or actual_identity.get("device") != root["device"]
        or actual_identity.get("inode") != root["inode"]
        or actual_identity.get("uid") != root["uid"]
        or not stat.S_ISDIR(actual_identity.get("mode", 0))
        or stat.S_IMODE(actual_identity["mode"]) != 0o700
    ):
        raise SourceConsumerError("live V5 output tree changed")
    for item in tree.files:
        record = records[item.path]
        if item.sha256 != record["sha256"] or item.identity["size"] != record["bytes"]:
            raise SourceConsumerError("live V5 output file changed")

    environments = execution.get("task_environment_manifest")
    environment_records = (
        environments.get("records") if isinstance(environments, dict) else None
    )
    if (
        type(environments) is not dict
        or set(environments) != {
            "schema", "records", "records_sha256", "tmpdir_root_identity",
            "output_dir_identity", "all_task_tmpdirs_removed_by_rmdir",
        }
        or environments.get("schema")
        != SCHEMA + "/campaign-v5/task-environment/v1/manifest/v1"
        or environments.get("tmpdir_root_identity")
        != launch["launch_root_identities"]["tmpdir_root"]
        or environments.get("output_dir_identity") != root
        or environments.get("all_task_tmpdirs_removed_by_rmdir") is not True
        or type(environment_records) is not list
        or len(environment_records) != ARRAY_TASKS
        or environments.get("records_sha256")
        != hashlib.sha256(_canonical_json(environment_records)).hexdigest()
    ):
        raise SourceConsumerError("V5 task-environment manifest changed")
    for index, record in enumerate(environment_records):
        environment_name = "environment-{:04d}-of-0820.json".format(index)
        shard_name = "shard-{:04d}-of-0820.json".format(index)
        tmpdir = str(TMP_ROOT / "task-{}-{}".format(launch["job_id"], index))
        if (
            type(record) is not dict
            or set(record) != {
                "array_task", "path", "sha256", "tmpdir", "tmpdir_identity",
                "output_dir_identity", "shard_sha256",
            }
            or not _same(record.get("array_task"), index)
            or record.get("path") != environment_name
            or record.get("sha256") != records[environment_name]["sha256"]
            or record.get("tmpdir") != tmpdir
            or not _root_identity(record.get("tmpdir_identity"), Path(tmpdir))
            or record.get("output_dir_identity") != root
            or record.get("shard_sha256") != records[shard_name]["sha256"]
        ):
            raise SourceConsumerError("V5 task-environment record changed")


def _validate_execution(
    attestation_raw: bytes, attestation: dict, execution: dict, launch_raw: bytes,
    launch: dict,
) -> None:
    expected_fixed = {
        "schema": SCHEMA + "/campaign-v5/execution", "campaign": "v5",
        "whole_campaign_rerun": True, "original_only": True,
        "recovery": None, "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "job_id": launch["job_id"], "partition": "fat", "qos": "normal",
        "account": PLANNER_ACCOUNT, "array": "0-819",
        "array_tasks": ARRAY_TASKS, "tasks_per_array_task": 2,
        "cpus_per_task": 1, "memory_per_cpu": MEMORY_PER_CPU,
        "time_limit": TIME_LIMIT, "task_timeout_seconds": TASK_TIMEOUT_SECONDS,
        "array_throttle": 0, "shards": ARRAY_TASKS,
        "candidates": CANDIDATES,
    }
    if (
        set(execution) != EXECUTION_KEYS
        or any(not _same(execution.get(key), value)
            for key, value in expected_fixed.items())
        or execution.get("launch_receipt_sha256")
        != hashlib.sha256(launch_raw).hexdigest()
        or execution.get("attestation_sha256")
        != hashlib.sha256(attestation_raw).hexdigest()
        or execution.get("code_manifest_sha256")
        != launch.get("code_manifest_sha256")
        or execution.get("source_inventory_sha256")
        != launch.get("source_inventory_sha256")
        or execution.get("source_audit_complete") is not True
        or execution.get("confirmation_prelaunch_authorized") is not True
        or attestation.get("confirmation_prelaunch_authorized") is not True
        or execution.get("prelaunch_gate") != attestation.get("prelaunch_gate")
        or execution.get("prelaunch_gate", {}).get("passed") is not True
        or execution.get("counts") != attestation.get("counts")
        or execution.get("translation_status_counts")
        != attestation.get("translation_status_counts")
        or execution.get("support_exclusion_counts")
        != attestation.get("support_exclusion_counts")
        or execution.get("attestation_records_sha256")
        != attestation.get("records_sha256")
        or execution.get("v4_infrastructure_diagnostic_sha256")
        != launch.get("v4_infrastructure_diagnostic_sha256")
        or execution.get("v4_infrastructure_diagnostic")
        != launch.get("v4_infrastructure_diagnostic")
        or execution.get("execution_environment")
        != launch.get("execution_environment")
        or execution.get("launch_root_identities")
        != launch.get("launch_root_identities")
        or execution.get("sealing_root_identities_before")
        != launch.get("launch_root_identities")
        or execution.get("sealing_root_identities_after")
        != launch.get("launch_root_identities")
    ):
        raise SourceConsumerError("V5 execution-receipt chain changed")
    _validate_scheduler(execution, launch)
    _validate_output_tree(execution, launch)


def load_v5_source(
    attestation_path: Path,
    execution_receipt_path: Path,
    launch_receipt_path: Path,
    *,
    snapshot_reader: SnapshotReader,
) -> ValidatedSource:
    attestation_raw, attestation = _read_json(
        attestation_path, ATTESTATION, "V5 source attestation"
    )
    execution_raw, execution = _read_json(
        execution_receipt_path, EXECUTION_RECEIPT, "V5 execution receipt"
    )
    launch_raw, launch = _read_json(
        launch_receipt_path, LAUNCH_RECEIPT, "V5 launch receipt"
    )
    intent_raw, intent = _read_json(INTENT, INTENT, "V5 launch intent")
    if attestation.get("schema") != SCHEMA:
        raise SourceConsumerError("V5 attestation schema changed")
    _validate_launch(intent_raw, intent, launch)
    manifest = _manifest(launch)
    launcher_relative = (
        "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py"
    )
    requirements_relative = (
        "experiments/requirements-pdb-terminal-incidence-shadow.txt"
    )
    if (
        launch.get("launcher_sha256") != manifest.get(launcher_relative)
        or launch.get("python_requirements_sha256")
        != manifest.get(requirements_relative)
    ):
        raise SourceConsumerError("V5 launcher/environment byte chain changed")
    _validate_diagnostic(launch, manifest)
    slurm_sha = _slurm(launch)
    inventory_raw, inventory = _read_json(
        SOURCE_INVENTORY, SOURCE_INVENTORY, "V5 source inventory"
    )
    if (
        hashlib.sha256(inventory_raw).hexdigest()
        != launch.get("source_inventory_sha256")
        or attestation.get("source_inventory_sha256")
        != launch.get("source_inventory_sha256")
        or attestation.get("code_manifest_sha256")
        != launch.get("code_manifest_sha256")
    ):
        raise SourceConsumerError("V5 inventory/manifest chain changed")
    _validate_execution(
        attestation_raw, attestation, execution, launch_raw, launch
    )
    tracked = {
        **manifest, SLURM_RELATIVE: slurm_sha,
        MANIFEST_RELATIVE: launch["code_manifest_sha256"],
    }
    snapshot = snapshot_reader(launch["repository_commit_id"], list(SCOPED_FILES))
    if (
        type(snapshot) is not dict
        or set(snapshot) != set(SCOPED_FILES)
        or any(type(raw) is not bytes for raw in snapshot.values())
        or any(
            hashlib.sha256(snapshot[relative]).hexdigest() != tracked[relative]
            for relative in SCOPED_FILES
        )
    ):
        raise SourceConsumerError("V5 producer revision byte chain changed")
    return ValidatedSource(
        attestation_path=ATTESTATION,
        intent_path=INTENT,
        execution_receipt_path=EXECUTION_RECEIPT,
        launch_receipt_path=LAUNCH_RECEIPT,
        attestation_raw=attestation_raw,
        intent_raw=intent_raw,
        execution_raw=execution_raw,
        launch_raw=launch_raw,
        inventory_raw=inventory_raw,
        attestation=attestation,
        intent=intent,
        execution=execution,
        launch=launch,
        inventory=inventory,
        tracked_file_sha256=dict(sorted(tracked.items())),
    )
