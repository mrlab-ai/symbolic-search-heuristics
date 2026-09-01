#!/usr/bin/env python3
"""Launch, monitor, and seal independent full source-audit campaign v2."""

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

import audit_pdb_terminal_incidence_confirmation_sources_v2 as Source
import pdb_terminal_incidence_confirmation_inventory as Inventory


_BASE_NAME = "_pdb_terminal_incidence_confirmation_source_launch_v2_base"
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
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v2.slurm"
)
CODE_MANIFEST = Source.DEFAULT_CODE_MANIFEST
OUTPUT_DIR = Source.DEFAULT_SHARDS
SOURCE_INVENTORY = Source.DEFAULT_INVENTORY
CANDIDATE = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v2_candidate.json"
)
ATTESTATION = Source.DEFAULT_OUTPUT
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v2"
)
INTENT = ARTIFACT_DIR / "source-audit-launch-intent-v2.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-launch-receipt-v2.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v2.json"
LAUNCH_SCHEMA = Source.SCHEMA + "/campaign-v2/launch"
EXECUTION_SCHEMA = Source.SCHEMA + "/campaign-v2/execution"
ARRAY_TASKS = Source.SHARD_COUNT
ACCOUNT = "naiss2025-5-561-cpu"
CONTROLLED_PATH = Source.CONTROLLED_PATH
UNSET_PYTHON_ENV = Source.UNSET_PYTHON_ENV
PYTHON_COMMAND = (
    SCRIPT_DIR / "data" / "pdb-terminal-incidence-shadow-venv" /
    "bin" / "python"
)
SHA256SUM_COMMAND = Path("/usr/bin/sha256sum")
JJ_COMMAND = Path("/home/jendrik/bin/jj")
JJ_EXECUTABLE_SHA256 = (
    "d1d69a0f87df266eebf0d2592dd019eb288c300b15fd019afe26cb1ed11ba152"
)
MEMORY_PER_CPU = "256G"
TIME_LIMIT = "01:40:00"
JOB_NAME_PREFIX = "confirmation-source-audit-v2"
COMMENT_PREFIX = "confirmation-source-audit-v2"

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
        raise LaunchAuditError("source-audit v2 Slurm script is not regular")
    try:
        lines = SLURM_SCRIPT.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as err:
        raise LaunchAuditError("cannot read source-audit v2 Slurm script") from err
    required = {
        "#SBATCH --job-name=confirmation-source-audit-v2",
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
        raise LaunchAuditError("source-audit v2 Slurm header changed")
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
        raise LaunchAuditError("source-audit v2 Slurm directives conflict")
    array_line = next(line for line in lines if line.startswith("#SBATCH --array="))
    if "%" in array_line or any("--nice" in line for line in lines):
        raise LaunchAuditError("source-audit v2 submission is throttled")
    assignments = [
        Base.MANIFEST_ASSIGNMENT_RE.fullmatch(line)
        for line in lines
        if line.startswith("code_manifest_sha256=")
    ]
    if len(assignments) != 1 or assignments[0] is None:
        raise LaunchAuditError("source-audit v2 code manifest is not pinned")
    manifest_sha = assignments[0].group(1)
    code = Source.validate_code_manifest(CODE_MANIFEST, manifest_sha)
    environment = Base._execution_environment(code)
    required_environment_lines = {
        "unset {}".format(" ".join(UNSET_PYTHON_ENV)),
        'export PYTHONNOUSERSITE="1"',
        'export PYTHONDONTWRITEBYTECODE="1"',
        'export PYTHONPYCACHEPREFIX="/tmp/'
        'symk-confirmation-source-audit-v2-'
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
        raise LaunchAuditError("source-audit v2 execution environment changed")
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
        raise LaunchAuditError("cannot attest scoped v2 commit") from err
    if (
        _jj_executable_identity() != jj_identity
        or changed
        or set(tracked) != set(SCOPED_COMMIT_FILES)
        or len(tracked) != len(SCOPED_COMMIT_FILES)
        or Base.JJ_COMMIT_RE.fullmatch(commit_id) is None
    ):
        raise LaunchAuditError(
            "source-audit v2 requires every bound file committed at @-"
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


def _fixed_materials(
    source_inventory_sha256: str,
    repository_commit_id: str | None = None,
) -> dict:
    if not Source._is_sha256(source_inventory_sha256):
        raise LaunchAuditError("source inventory hash is invalid")
    slurm_sha, manifest_sha, code = _slurm_preflight()
    environment = Base._execution_environment(code)
    if repository_commit_id is None:
        repository_commit_id = _scoped_repository_commit()
    if Base.JJ_COMMIT_RE.fullmatch(repository_commit_id) is None:
        raise LaunchAuditError("source-audit v2 repository commit is invalid")
    jj_identity = _jj_executable_identity()
    return {
        "campaign": "v2",
        "whole_campaign_rerun": True,
        "reused_v1_shards": 0,
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
        raise LaunchAuditError("source-audit v2 submission token is invalid")
    return (
        "{}-{}".format(JOB_NAME_PREFIX, token),
        "{}/{}".format(COMMENT_PREFIX, token),
    )


def _submit_command(
    source_inventory_sha256: str,
    output_dir: Path,
    submission_token: str,
) -> list[str]:
    if not Source._is_sha256(source_inventory_sha256):
        raise LaunchAuditError("source inventory hash is invalid")
    job_name, comment = _submission_identity(submission_token)
    return [
        "sbatch", "--parsable", "--export=NONE",
        "--job-name={}".format(job_name),
        "--comment={}".format(comment),
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


def launch() -> None:
    if any(path.exists() for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR,
        CANDIDATE, ATTESTATION,
    )):
        raise LaunchAuditError("source-audit v2 launch artifacts already exist")
    inventory = Inventory.load_inventory()
    source_inventory_value = Source.build_inventory_manifest(inventory)
    source_inventory_raw = Source.canonical_json(source_inventory_value)
    source_inventory_sha = hashlib.sha256(source_inventory_raw).hexdigest()
    materials = _fixed_materials(source_inventory_sha)
    diagnostic = _v1_failure_diagnostic()
    token = secrets.token_hex(12)
    recorded_utc = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(timespec="seconds")
    command = _submit_command(source_inventory_sha, OUTPUT_DIR, token)
    intent = {
        "schema": LAUNCH_SCHEMA + "/intent",
        **materials,
        "v1_failure_diagnostic": diagnostic,
        "recorded_utc": recorded_utc,
        "submission_token": token,
        "submit_command": command,
    }
    Base._exclusive_json(INTENT, intent, "source-audit v2 launch intent")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    Base._exclusive_bytes(
        SOURCE_INVENTORY,
        source_inventory_raw,
        "source inventory v2",
    )
    try:
        output = subprocess.check_output(command, cwd=REPO, text=True).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("source-audit v2 sbatch failed after intent") from err
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
    raw, intent = Base._load_json(INTENT, "source-audit v2 launch intent")
    source_inventory_sha = intent.get("source_inventory_sha256")
    materials = _fixed_materials(
        source_inventory_sha, intent.get("repository_commit_id")
    )
    diagnostic = _v1_failure_diagnostic()
    token = intent.get("submission_token")
    recorded_utc = intent.get("recorded_utc")
    command = _submit_command(source_inventory_sha, OUTPUT_DIR, token)
    if (
        intent != {
            "schema": LAUNCH_SCHEMA + "/intent",
            **materials,
            "v1_failure_diagnostic": diagnostic,
            "recorded_utc": recorded_utc,
            "submission_token": token,
            "submit_command": command,
        }
        or not isinstance(recorded_utc, str)
        or Base.SUBMISSION_TOKEN_RE.fullmatch(token or "") is None
    ):
        raise LaunchAuditError("source-audit v2 launch intent changed")
    Source.load_inventory_manifest(SOURCE_INVENTORY, source_inventory_sha)
    return raw, intent, {**materials, "v1_failure_diagnostic": diagnostic}


def seal() -> None:
    import recover_pdb_terminal_incidence_confirmation_source_audit_v2 as Recovery

    if (
        EXECUTION_RECEIPT.exists()
        or CANDIDATE.exists()
        or ATTESTATION.exists()
        or Recovery.UNION_DIR.exists()
    ):
        raise LaunchAuditError("source-audit v2 execution artifacts already exist")
    launch_sha, launch_receipt, rows = Base.status()
    union = Recovery.prepare_union(launch_sha, launch_receipt, rows)
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
        CANDIDATE, "source-audit v2 candidate attestation"
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
        raise LaunchAuditError("source-audit v2 candidate identity changed")
    attestation_sha = Base._exclusive_bytes(
        ATTESTATION, candidate_raw, "frozen source-audit v2 attestation"
    )
    receipt = {
        "schema": EXECUTION_SCHEMA,
        "campaign": "v2",
        "whole_campaign_rerun": True,
        "reused_v1_shards": 0,
        "v1_failure_diagnostic": launch_receipt["v1_failure_diagnostic"],
        "launch_receipt_sha256": launch_sha,
        "job_id": launch_receipt["job_id"],
        "partition": "fat",
        "memory_per_cpu": MEMORY_PER_CPU,
        "array_throttle": 0,
        "shards": ARRAY_TASKS,
        "candidates": Source.CANDIDATE_COUNT,
        "scheduler_state_counts": dict(Counter(
            row["state"] for row in rows
        )),
        "scheduler_rows": rows,
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
        EXECUTION_RECEIPT, receipt, "source-audit v2 execution receipt"
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
