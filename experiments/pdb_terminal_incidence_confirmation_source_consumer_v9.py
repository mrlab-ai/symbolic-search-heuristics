#!/usr/bin/env python3
"""Independent fail-closed consumer for the full-census V9 source seal.

This module deliberately imports no source-audit producer, launcher, or older
consumer.  The constants below are the downstream contract.  Confirmation A,
guided B, and the direct selector should call ``load_authorized_confirmation``
and use only the immutable records returned by it.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import base64
import datetime
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping


class SourceConsumerError(RuntimeError):
    """The V9 seal is incomplete, inconsistent, or unauthorized."""


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
ARTIFACT_DIR = SCRIPT_DIR / "artifacts/pdb-terminal-incidence-confirmation-v9"
DATA_ROOT = SCRIPT_DIR / "data/pdb-terminal-incidence-confirmation-source-audit-v9"
TMP_ROOT = SCRIPT_DIR / "data/pdb-terminal-incidence-confirmation-source-audit-v9-tmp"
LOG_ROOT = SCRIPT_DIR / "data/pdb-terminal-incidence-confirmation-source-audit-v9-logs"
SLURM_PROGRAM = SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v9.slurm"

BASE_SCHEMA = (
    "symbolic-search-heuristics/universal-unseen-confirmation-source-audit/v1"
)
SCHEMA = BASE_SCHEMA + "/campaign-v9"
LAUNCH_SCHEMA = SCHEMA + "/launch/v1"
LAUNCH_INTENT_SCHEMA = LAUNCH_SCHEMA + "/intent"
SBATCH_RESULT_SCHEMA = LAUNCH_SCHEMA + "/sbatch-result/v1"
EXECUTION_SCHEMA = SCHEMA + "/execution/v1"
SHARD_SCHEMA = SCHEMA + "/shard/v1"
CANDIDATE_SCHEMA = SCHEMA + "/candidate-result/v1"
TASK_ENVIRONMENT_SCHEMA = SCHEMA + "/task-environment/v1"
SOURCE_SNAPSHOT_SCHEMA = SCHEMA + "/source-snapshot/v1"
RESOURCE_CONTRACT_SCHEMA = SCHEMA + "/resource-contract/v1"
ATTESTATION_SCHEMA = SCHEMA + "/attestation/v1"
TREE_SCHEMA = SCHEMA + "/output-tree/v1"
SEAL_PLAN_SCHEMA = SCHEMA + "/seal-plan/v1"
TREE_STAGE_SCHEMA = SCHEMA + "/tree-stage/v1"
CENSUS_STAGE_SCHEMA = SCHEMA + "/census-stage/v1"
SPLIT_STAGE_SCHEMA = SCHEMA + "/split-stage/v1"
ATTESTATION_STAGE_SCHEMA = SCHEMA + "/attestation-stage/v1"
INVENTORY_SCHEMA = SCHEMA + "/inventory/v1"
NORMALIZATION_SCHEMA = SCHEMA + "/normalization-evidence/v1"
CHILD_LIMIT_SCHEMA = SCHEMA + "/child-limit-evidence/v1"

CAMPAIGN = "v9-full-census"
BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
CANDIDATE_COUNT = 1640
SHARD_COUNT = 820
TASKS_PER_SHARD = 2
SPLIT_SEED = (
    "symbolic-search-heuristics/universal-unseen-confirmation-guided-split/v1"
)
CONFIRMATION_ROLE = "confirmation-a"
GUIDED_ROLE = "guided-b"
GUIDED_TOP_UP_ROLE = "guided-b-topup"
CONFIRMATION_TASKS = 650
MIN_CONFIRMATION_FAMILIES = 28
MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES = 12
MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS = 100
MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES = 10
GUIDED_TARGET_TASKS = 300
MAX_GUIDED_TASKS_PER_FAMILY = 12
MIN_GUIDED_TASKS = 200
MIN_GUIDED_FAMILIES = 30
MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES = 12
MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS = 50
MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES = 10

ADDRESS_SPACE_BYTES = 25769803776
CPU_LIMIT_SECONDS = 1800
CPU_HARD_LIMIT_SECONDS = 1801
WALL_WATCHDOG_SECONDS = 1950
STREAM_TAIL_BYTES = 8192
STREAM_PREFIX_BYTES = 1024 * 1024
FRESH_ORIGIN = "v9-fresh"
OUTCOMES = ("input-rejected", "resource-excluded", "success")
SUPPORT_STATUSES = ("indeterminate", "supported", "unsupported")
RESOURCE_KINDS = ("memory", "time")
PINNED_PYTHON_SHA256 = (
    "021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
)
PRLIMIT_SHA256 = (
    "fc3d011a1d832dabd768343b26d38223cb2bbd13d59ed97998a2d6a747ce8676"
)
LIBSECCOMP_SHA256 = (
    "54068c4d4cf1e5692ba8051ce0744cd175d0c0e2c9812b668d738d2cbe3915d9"
)
DENIED_PROCESS_SYSCALLS = (
    "clone", "clone3", "fork", "setpgid", "setsid", "vfork",
)

SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
TOKEN_RE = re.compile(r"[0-9a-f]{24}")
MAX_JSON_BYTES = 256 * 1024 * 1024
READ_CHUNK_BYTES = 1024 * 1024
CAPTURE_PROTOCOL = "pre-intent-o-excl-nofollow-sealed-0400-retained-fd-v1"
CONTROLLED_PATH = "/usr/bin:/bin"

# Immutable inventory commitments copied into this independent trust boundary.
COST_MANIFEST_SHA256 = (
    "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168"
)
SHADOW_ATTESTATION_SHA256 = (
    "bf2c42860fad91c56620c90a41657ab472f4d58acd184a7580c7b5994aa72d04"
)
CANDIDATE_RECORDS_SHA256 = (
    "5add608b876d236a3fc6b3ab0eaeb67a4b7629c9328039ba2752c4c380e3035c"
)
ALIAS_GROUPS_SHA256 = (
    "d9843d73b854eeb58b37dcdfad9265daf7552d909ab0df865b0ff9b13d6dc425"
)
FAMILY_MAP_SHA256 = (
    "7e05588a27ccae96fa50c58417b6bd0417532121b668b1205850adee03591dc1"
)
SHADOW_FAMILY_SEQUENCE_SHA256 = (
    "f1f6877788c0565179660ac1892268fc85235ab73729053c285dd6cfeb01fa28"
)
SHADOW_UNREPRESENTED_FAMILY_SEQUENCE_SHA256 = (
    "9b831aa026deeda951f8aefd3ce8632ec0b82fb7f5231d3fbb5acf9dbd97f746"
)
ALL_PRIOR_FAMILY_SEQUENCE_SHA256 = (
    "fe05c88ed11512cf25cb68bfe0c2522558bfe23daa1090df7182fc6df4206a59"
)
ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256 = (
    "2b461a68f2bcad8bdeb18304ec1cfad68dd287994cce0770b7392fcc285f9ec1"
)
PRIOR_DIRECTORY_FAMILY_MAP_SHA256 = (
    "790426b33b085c70ae2a3b63a337616e14a0446db91ff40d854634996d345a52"
)
PRIOR_FAMILY_LEDGER_SHA256 = (
    "9de66fb087855ede93eabf3193e462bbacdde1bcdc7b2ddc48ab3168b1f31101"
)
INVENTORY_DIGESTS_SHA256 = (
    "470ce26164fd4966d20fbf026f18882a541014cff66214136decde8b80b4401d"
)
EXPECTED_FAMILIES = 43
EXPECTED_REPRESENTED_SHADOW_FAMILIES = 23
EXPECTED_SHADOW_UNREPRESENTED_FAMILIES = 20
EXPECTED_REPRESENTED_ALL_PRIOR_FAMILIES = 30
EXPECTED_ALL_PRIOR_UNREPRESENTED_FAMILIES = 13
EXPECTED_PRIOR_FAMILY_LEDGER_RECORDS = 2157
EXPECTED_DISCARDED_ALIASES = 93

RESOURCE_PROFILE = {
    "account": "naiss2025-5-561-cpu",
    "partition": "fat",
    "qos": "normal",
    "nodes": 1,
    "ntasks": 1,
    "cpus_per_task": 1,
    "mem": "26G",
    "time": "01:10:00",
    "array": "0-819",
    "array_throttle": None,
    "nice": 0,
    "requeue": False,
    "export": "NONE",
}
PRIOR_CAMPAIGNS = ["v{}".format(index) for index in range(1, 9)]
PRIOR_RUNTIME_PAYLOAD = {
    "campaigns": PRIOR_CAMPAIGNS,
    "paths_read": [],
    "bytes_read": 0,
    "records_read": 0,
    "payloads_reused": 0,
    "scientific_bytes_reused": 0,
    "reuse_authorized": False,
}
CODE_MANIFEST_RELATIVE = (
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v9_code.sha256"
)
SLURM_PROGRAM_RELATIVE = (
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v9.slurm"
)
MANIFEST_PLACEHOLDER = b"__V9_CODE_MANIFEST_SHA256__"
INVENTORY_PLACEHOLDER = b"__V9_SOURCE_INVENTORY_SHA256__"
COMMIT_PLACEHOLDER = b"__V9_REPOSITORY_COMMIT_ID__"
PINNED_PYTHON = (
    SCRIPT_DIR / "data/pdb-terminal-incidence-shadow-venv/bin/python"
)
TRANSLATOR_FILES = (
    "src/translate/__init__.py",
    "src/translate/__main__.py",
    "src/translate/axiom_rules.py",
    "src/translate/build_model.py",
    "src/translate/constraints.py",
    "src/translate/fact_groups.py",
    "src/translate/graph.py",
    "src/translate/greedy_join.py",
    "src/translate/instantiate.py",
    "src/translate/invariant_finder.py",
    "src/translate/invariants.py",
    "src/translate/main.py",
    "src/translate/normalize.py",
    "src/translate/options.py",
    "src/translate/pddl/__init__.py",
    "src/translate/pddl/actions.py",
    "src/translate/pddl/axioms.py",
    "src/translate/pddl/conditions.py",
    "src/translate/pddl/effects.py",
    "src/translate/pddl/f_expression.py",
    "src/translate/pddl/functions.py",
    "src/translate/pddl/pddl_types.py",
    "src/translate/pddl/predicates.py",
    "src/translate/pddl/tasks.py",
    "src/translate/pddl_parser/__init__.py",
    "src/translate/pddl_parser/lisp_parser.py",
    "src/translate/pddl_parser/parse_error.py",
    "src/translate/pddl_parser/parsing_functions.py",
    "src/translate/pddl_parser/pddl_file.py",
    "src/translate/pddl_parser/warning.py",
    "src/translate/pddl_to_prolog.py",
    "src/translate/sas_tasks.py",
    "src/translate/sccs.py",
    "src/translate/simplify.py",
    "src/translate/split_rules.py",
    "src/translate/timers.py",
    "src/translate/tools.py",
    "src/translate/variable_order.py",
)
CODE_MANIFEST_FILES = tuple(sorted({
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v9.py",
    "experiments/jj_cached_revision.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v9.py",
    "experiments/pdb_terminal_incidence_confirmation_inventory.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v9_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v9.py",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v9.slurm",
    "experiments/pdb_terminal_incidence_confirmation_translate_v9.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/suite_wbh_operator_costs.json",
    "experiments/pdb_terminal_incidence_shadow_cost_attestation.json",
    "experiments/test_launch_pdb_terminal_incidence_confirmation_source_audit_v9.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v9.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_seal_v9.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_consumer_v9.py",
    "experiments/test_pdb_terminal_incidence_confirmation_translate_v9.py",
    *TRANSLATOR_FILES,
}))
REQUIRED_MANIFEST_FILES = frozenset(CODE_MANIFEST_FILES)

LAUNCH_INTENT_FILENAME = "source-audit-launch-intent-v9.json"
SBATCH_STDOUT_FILENAME = "source-audit-sbatch-stdout-v9.bin"
SBATCH_STDERR_FILENAME = "source-audit-sbatch-stderr-v9.bin"
SBATCH_RESULT_FILENAME = "source-audit-sbatch-result-v9.json"
LAUNCH_RECEIPT_FILENAME = "source-audit-launch-receipt-v9.json"
SEAL_PLAN_FILENAME = "source-audit-seal-plan-v9.json"
TREE_STAGE_FILENAME = "source-audit-tree-stage-v9.json"
CENSUS_STAGE_FILENAME = "source-audit-census-stage-v9.json"
SPLIT_STAGE_FILENAME = "source-audit-split-stage-v9.json"
ATTESTATION_STAGE_FILENAME = "source-audit-attestation-stage-v9.json"
ATTESTATION_FILENAME = "source-audit-attestation-v9.json"
EXECUTION_RECEIPT_FILENAME = "source-audit-execution-receipt-v9.json"
REQUIRED_ARTIFACT_FILENAMES = (
    LAUNCH_INTENT_FILENAME,
    SBATCH_STDOUT_FILENAME,
    SBATCH_STDERR_FILENAME,
    SBATCH_RESULT_FILENAME,
    LAUNCH_RECEIPT_FILENAME,
    SEAL_PLAN_FILENAME,
    TREE_STAGE_FILENAME,
    CENSUS_STAGE_FILENAME,
    SPLIT_STAGE_FILENAME,
    ATTESTATION_STAGE_FILENAME,
    ATTESTATION_FILENAME,
    EXECUTION_RECEIPT_FILENAME,
)

INVENTORY_RECORD_KEYS = frozenset({
    "candidate_index", "directory", "family", "problem", "domain_file",
    "problem_file", "domain_sha256", "problem_sha256", "canonical_path",
    "is_shadow_family", "is_shadow_unrepresented",
    "is_all_prior_represented", "is_all_prior_unrepresented", "aliases",
})
SOURCE_KEYS = (
    "directory", "family", "problem", "domain_file", "problem_file",
    "domain_sha256", "problem_sha256",
)
TASK_KEYS = INVENTORY_RECORD_KEYS | frozenset({
    "schema", "logical_shard_index", "position_in_shard",
    "candidate_origin", "translation_attempted", "translator_command",
    "code_manifest_sha256", "repository_commit_id", "resource_contract",
    "resource_contract_sha256", "child_limit_attestation",
    "parent_prlimit_observation", "parent_isolation_observation",
    "process_returncode",
    "complete_process_group_reaped", "stdout", "stderr", "normalization",
    "sas", "sas_bytes", "sas_sha256", "partial_sas_evidence", "status",
    "resource_exclusion_kind", "support_determined", "supported",
    "support_exclusion_reasons", "eligible_for_cohort", "source_snapshot",
})
SAS_KEYS = frozenset({
    "sas_version", "metric", "num_variables", "num_mutex_groups",
    "num_operators", "num_effects", "num_conditional_effects",
    "num_zero_cost_operators", "min_operator_cost", "max_operator_cost",
    "num_serialized_axioms",
})

LAUNCH_RECEIPT_KEYS = frozenset({
    "schema", "campaign", "job_id", "submission_token",
    "repository_commit_id", "source_inventory_sha256",
    "code_manifest_sha256", "launch_intent_sha256",
    "sbatch_result_sha256", "resource_profile", "root_identities",
    "slurm_program", "launch_recovered", "recovery_evidence",
    "prior_runtime_payloads_read", "prior_runtime_payload_bytes_read",
    "prior_runtime_payloads_reused", "selective_recovery_authorized",
    "whole_campaign_fresh",
})
LAUNCH_INTENT_KEYS = frozenset({
    "schema", "campaign", "recorded_utc", "submission_token",
    "repository_commit_id", "resource_profile", "array_mapping",
    "source_inventory", "source_inventory_sha256", "code_manifest",
    "code_manifest_sha256", "slurm_program", "root_identities",
    "execution_environment", "capture_protocol",
    "sbatch_capture_initial_identities", "submit_command",
    "prior_runtime_payloads_read", "prior_runtime_payload_bytes_read",
    "prior_runtime_payloads_reused", "selective_recovery_authorized",
    "whole_campaign_fresh",
})
SBATCH_RESULT_KEYS = frozenset({
    "schema", "launch_intent_sha256", "submit_command_sha256",
    "slurm_program_sha256", "capture_protocol", "process_observation",
    "stdout", "stderr", "parsed_job_id", "accepted_by_launcher",
    "raw_streams_preserved",
})
EXECUTION_KEYS = frozenset({
    "schema", "campaign", "benchmark_revision", "logical_shards",
    "candidates", "tasks_per_shard", "fresh_full_census",
    "candidate_indices_sha256", "launch_receipt_sha256",
    "source_inventory_sha256", "code_manifest_sha256", "resource_profile",
    "scheduler_state_counts", "scheduler_rows", "scheduler_rows_sha256",
    "scheduler_contract_rows", "scheduler_contract_rows_sha256",
    "scheduler_gate_passed", "scheduler_gate_passed_before_payload_read",
    "output_tree", "output_tree_sha256", "environment_records_sha256",
    "prior_runtime_payload", "partial_v9_reuse_authorized",
    "seal_recovery_protocol", "seal_plan_sha256", "tree_stage_sha256",
    "census_stage_sha256", "split_stage_sha256",
    "attestation_stage_sha256", "attestation_sha256",
    "attestation_records_sha256", "cohorts_sha256", "outcome_counts",
    "support_status_counts", "support_exclusion_counts",
    "resource_exclusion_counts", "resource_exclusions_by_family",
    "prelaunch_gate", "source_audit_complete",
    "confirmation_prelaunch_authorized",
})

ATTESTATION_KEYS = frozenset({
    "schema", "campaign", "benchmark_revision", "translator_source_sha256",
    "source_inventory_sha256",
    "source_inventory_records_sha256",
    "code_manifest_sha256", "split_seed", "split_rank_encoding",
    "split_role_labels", "limits", "full_census_fresh",
    "candidate_indices_sha256", "counts", "outcome_counts",
    "support_status_counts", "support_exclusion_counts",
    "resource_exclusion_counts", "resource_exclusions_by_family",
    "records_sha256", "cohorts", "cohorts_sha256", "prelaunch_gate",
    "confirmation_prelaunch_authorized", "records",
})
SEAL_PLAN_KEYS = frozenset({
    "schema", "campaign", "launch_receipt_sha256",
    "source_inventory_sha256", "code_manifest_sha256", "job_id",
    "scheduler_rows", "scheduler_rows_sha256", "scheduler_contract_rows",
    "scheduler_contract_rows_sha256", "scheduler_gate_passed",
    "scheduler_gate_passed_before_payload_read", "scheduler_restarts",
    "logical_shards", "candidates", "root_identities",
    "expected_output_root_entries", "expected_output_root_entries_sha256",
    "log_payloads_read", "prior_runtime_payloads_read",
})
TREE_STAGE_KEYS = frozenset({
    "schema", "seal_plan_sha256", "output_tree", "output_tree_sha256",
    "environment_records_sha256",
})
CENSUS_STAGE_KEYS = frozenset({
    "schema", "tree_stage_sha256", "candidate_count",
    "candidate_indices_sha256", "candidate_origin_counts",
    "whole_campaign_rerun", "prior_campaign_payloads_read",
    "prior_campaign_shards_used", "records_sha256", "counts",
    "outcome_counts", "support_status_counts", "support_exclusion_counts",
    "resource_exclusion_counts", "resource_exclusions_by_family",
})
SPLIT_STAGE_KEYS = frozenset({
    "schema", "census_stage_sha256", "split_seed", "split_rank_encoding",
    "cohorts", "cohorts_sha256", "prelaunch_gate",
    "confirmation_prelaunch_authorized",
})
ATTESTATION_STAGE_KEYS = frozenset({
    "schema", "split_stage_sha256", "attestation_path",
    "attestation_bytes", "attestation_sha256", "attestation_records_sha256",
    "cohorts_sha256", "confirmation_prelaunch_authorized",
})


@dataclass(frozen=True)
class V9Paths:
    artifact_dir: Path
    data_root: Path
    launch_intent: Path
    sbatch_stdout: Path
    sbatch_stderr: Path
    sbatch_result: Path
    launch_receipt: Path
    execution_receipt: Path
    attestation: Path
    inventory: Path
    seal_plan: Path
    tree_stage: Path
    census_stage: Path
    split_stage: Path
    attestation_stage: Path
    code_manifest: Path
    tmpdir_root: Path
    log_root: Path
    slurm_program: Path


def paths_for(
    artifact_dir: Path = ARTIFACT_DIR, data_root: Path = DATA_ROOT, *,
    tmpdir_root: Path | None = None, log_root: Path | None = None,
    slurm_program: Path = SLURM_PROGRAM,
) -> V9Paths:
    """Return the exact V9 artifact layout under the two supplied roots."""
    artifact_dir = Path(os.path.abspath(artifact_dir))
    data_root = Path(os.path.abspath(data_root))
    tmpdir_root = Path(os.path.abspath(
        tmpdir_root if tmpdir_root is not None
        else data_root.parent / TMP_ROOT.name
    ))
    log_root = Path(os.path.abspath(
        log_root if log_root is not None else data_root.parent / LOG_ROOT.name
    ))
    slurm_program = Path(os.path.abspath(slurm_program))
    return V9Paths(
        artifact_dir=artifact_dir,
        data_root=data_root,
        launch_intent=artifact_dir / LAUNCH_INTENT_FILENAME,
        sbatch_stdout=artifact_dir / SBATCH_STDOUT_FILENAME,
        sbatch_stderr=artifact_dir / SBATCH_STDERR_FILENAME,
        sbatch_result=artifact_dir / SBATCH_RESULT_FILENAME,
        launch_receipt=artifact_dir / LAUNCH_RECEIPT_FILENAME,
        execution_receipt=artifact_dir / EXECUTION_RECEIPT_FILENAME,
        attestation=artifact_dir / ATTESTATION_FILENAME,
        inventory=data_root / "source-inventory-v9.json",
        seal_plan=artifact_dir / SEAL_PLAN_FILENAME,
        tree_stage=artifact_dir / TREE_STAGE_FILENAME,
        census_stage=artifact_dir / CENSUS_STAGE_FILENAME,
        split_stage=artifact_dir / SPLIT_STAGE_FILENAME,
        attestation_stage=artifact_dir / ATTESTATION_STAGE_FILENAME,
        code_manifest=SCRIPT_DIR / Path(CODE_MANIFEST_RELATIVE).name,
        tmpdir_root=tmpdir_root,
        log_root=log_root,
        slurm_program=slurm_program,
    )


@dataclass(frozen=True)
class AuthorizedConfirmation:
    campaign: str
    benchmark_revision: str
    seal_repository_commit_id: str
    source_inventory_sha256: str
    code_manifest_sha256: str
    launch_receipt_sha256: str
    execution_receipt_sha256: str
    attestation_sha256: str
    confirmation_a: tuple[Mapping[str, Any], ...]
    guided_b: tuple[Mapping[str, Any], ...]
    eligible_records: tuple[Mapping[str, Any], ...]
    all_records: tuple[Mapping[str, Any], ...]
    outcome_counts: Mapping[str, int]
    resource_exclusions_by_family: Mapping[str, Any]
    tracked_file_sha256: Mapping[str, str]


SnapshotReader = Callable[[str, list[str]], dict[str, bytes]]


def _canonical_json(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise SourceConsumerError("value is not canonical finite JSON") from err


def _canonical_json_line(value: Any) -> bytes:
    return _canonical_json(value) + b"\n"


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _fingerprint(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns,
    )


def _read_regular_with_stat(
    path: Path, label: str, *, expected_mode: int | None = None,
    expected_uid: int | None = None,
) -> tuple[bytes, os.stat_result]:
    descriptor = None
    try:
        before = path.lstat()
        if (
            path.is_symlink() or not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (
                expected_mode is not None
                and stat.S_IMODE(before.st_mode) != expected_mode
            )
            or (expected_uid is not None and before.st_uid != expected_uid)
        ):
            raise SourceConsumerError(
                "{} has the wrong regular-file identity".format(label)
            )
        if before.st_size > MAX_JSON_BYTES:
            raise SourceConsumerError("{} is unexpectedly large".format(label))
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        descriptor = os.open(path, flags)
        opened = os.fstat(descriptor)
        if _fingerprint(opened) != _fingerprint(before):
            raise SourceConsumerError("{} changed before reading".format(label))
        chunks = []
        size = 0
        while True:
            chunk = os.read(descriptor, READ_CHUNK_BYTES)
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if size > MAX_JSON_BYTES:
                raise SourceConsumerError("{} is unexpectedly large".format(label))
        after_fd = os.fstat(descriptor)
        after_path = path.lstat()
        if (
            _fingerprint(after_fd) != _fingerprint(opened)
            or _fingerprint(after_path) != _fingerprint(opened)
            or path.is_symlink()
        ):
            raise SourceConsumerError("{} changed while reading".format(label))
        return b"".join(chunks), after_fd
    except SourceConsumerError:
        raise
    except OSError as err:
        raise SourceConsumerError("cannot read {}".format(label)) from err
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_regular(
    path: Path, label: str, *, expected_mode: int | None = None,
    expected_uid: int | None = None,
) -> bytes:
    raw, _info = _read_regular_with_stat(
        path, label, expected_mode=expected_mode, expected_uid=expected_uid,
    )
    return raw


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise SourceConsumerError("canonical JSON contains a duplicate key")
        value[key] = item
    return value


def _read_json(
    path: Path, label: str, *, trailing_newline: bool = False,
    expected_mode: int | None = None, expected_uid: int | None = None,
) -> tuple[bytes, dict]:
    raw = _read_regular(
        path, label, expected_mode=expected_mode, expected_uid=expected_uid,
    )
    try:
        value = json.loads(
            raw.decode("ascii"), object_pairs_hook=_reject_duplicate_keys,
        )
    except SourceConsumerError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SourceConsumerError("{} is not canonical JSON".format(label)) from err
    expected = _canonical_json_line(value) if trailing_newline else _canonical_json(value)
    if type(value) is not dict or expected != raw:
        raise SourceConsumerError("{} is not canonical JSON".format(label))
    return raw, value


def _freeze(value: Any) -> Any:
    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def shard_name(index: int) -> str:
    return "shard-{:04d}-of-{:04d}".format(index, SHARD_COUNT)


def environment_name(index: int) -> str:
    return "{}/environment.json".format(shard_name(index))


def result_name(index: int) -> str:
    return "{}/result.json".format(shard_name(index))


def prefix_name(candidate_index: int, stream: str) -> str:
    if stream not in ("stdout", "stderr"):
        raise SourceConsumerError("invalid V9 stream name")
    return "{}/candidate-{:04d}.{}.prefix".format(
        shard_name(candidate_index // TASKS_PER_SHARD), candidate_index, stream,
    )


def _candidate_indices_sha256() -> str:
    return _digest(list(range(CANDIDATE_COUNT)))


def _expected_root_identity(path: Path, label: str) -> dict:
    try:
        info = path.lstat()
    except OSError as err:
        raise SourceConsumerError("cannot inspect {}".format(label)) from err
    if (
        path.is_symlink() or not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.getuid()
    ):
        raise SourceConsumerError("{} is not a private owned directory".format(label))
    return {
        "path": str(path), "canonical_path": str(path),
        "device": info.st_dev, "inode": info.st_ino, "mode": "0700",
        "uid": info.st_uid, "gid": info.st_gid,
    }


def _expected_submit_command(paths: V9Paths, token: str) -> list[str]:
    identity = "pdb-source-v9-{}".format(token)
    return [
        "/usr/bin/sbatch", "--parsable", "--export=NONE",
        "--job-name=" + identity, "--comment=" + identity,
        "--account=" + RESOURCE_PROFILE["account"], "--partition=fat",
        "--qos=normal", "--nodes=1", "--ntasks=1", "--cpus-per-task=1",
        "--mem=26G", "--time=01:10:00", "--array=0-819", "--nice=0",
        "--no-requeue", "--chdir=" + str(REPO),
        "--output={}/slurm-%A_%a.out".format(paths.log_root),
        "--error={}/slurm-%A_%a.err".format(paths.log_root),
    ]


def _array_mapping() -> dict:
    pairs = [
        [shard * TASKS_PER_SHARD + offset
         for offset in range(TASKS_PER_SHARD)]
        for shard in range(SHARD_COUNT)
    ]
    return {
        "logical_shards": SHARD_COUNT,
        "candidate_count": CANDIDATE_COUNT,
        "rule": "array element s owns candidates 2s and 2s+1",
        "candidate_index_first": 0,
        "candidate_index_last": CANDIDATE_COUNT - 1,
        "candidate_pairs_sha256": _digest(pairs),
        "independent_of_prior_scheduler_rows": True,
    }


def _execution_environment(paths: V9Paths) -> dict:
    return {
        "submission_export": "NONE",
        "slurm_export": "NONE",
        "path": CONTROLLED_PATH,
        "unset_variables": ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"],
        "python_no_user_site": "1",
        "python_dont_write_bytecode": "1",
        "python_command": str(PINNED_PYTHON),
        "python_executable_sha256": PINNED_PYTHON_SHA256,
        "tmpdir_root": str(paths.tmpdir_root),
        "scheduler_log_root": str(paths.log_root),
        "tmpdir_template": str(
            paths.tmpdir_root
            / "task-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"
        ),
        "task_tmpdir_mode": "0700",
        "task_tmpdir_cleanup": (
            "exact empty unpublished directory on success only"
        ),
        "candidate_address_space_limit_mib": 24576,
        "candidate_cpu_limit_seconds": CPU_LIMIT_SECONDS,
        "candidate_wall_watchdog_seconds": WALL_WATCHDOG_SECONDS,
    }


def _parse_job_id(raw: bytes) -> str | None:
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    match = re.fullmatch(
        r"([0-9]+)(?:;[A-Za-z0-9_.-]+)?\n?", value,
    )
    return match.group(1) if match else None


def _capture_record(
    path: Path, raw: bytes, info: os.stat_result, initial: Any, label: str,
) -> dict:
    expected_initial = {
        "path": str(path),
        "canonical_path": str(path),
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": "0400",
        "uid": info.st_uid,
        "gid": info.st_gid,
        "link_count": 1,
        "bytes_at_intent": 0,
    }
    if initial != expected_initial:
        raise SourceConsumerError("{} initial identity changed".format(label))
    final = {
        **{
            key: value for key, value in expected_initial.items()
            if key != "bytes_at_intent"
        },
        "bytes": len(raw),
    }
    return {
        "path": str(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "initial_identity": expected_initial,
        "final_identity": final,
    }


def _validate_recovery(value: Any, launch: dict, paths: V9Paths) -> None:
    if launch["launch_recovered"] is False:
        if value is not None:
            raise SourceConsumerError("V9 non-recovered launch has recovery evidence")
        return
    if type(value) is not dict or value.get("job_id") != launch["job_id"]:
        raise SourceConsumerError("V9 recovery evidence changed")
    source = value.get("source")
    if source == "retained-sbatch-stdout":
        if (
            set(value) != {
                "source", "job_id", "stdout_sha256",
                "accepted_returncode_zero", "no_resubmission",
            }
            or not _is_sha256(value.get("stdout_sha256"))
            or value.get("accepted_returncode_zero") is not True
            or value.get("no_resubmission") is not True
        ):
            raise SourceConsumerError("V9 retained-stdout recovery changed")
        return
    if source != "scheduler-submission-journal":
        raise SourceConsumerError("V9 recovery source changed")
    optional = {"uncertain_stdout_job_id", "uncertain_stdout_sha256"}
    base = {"source", "job_id", "rows", "rows_sha256", "no_resubmission"}
    if set(value) not in (base, base | optional):
        raise SourceConsumerError("V9 scheduler-journal recovery shape changed")
    rows = value.get("rows")
    expected_identity = "pdb-source-v9-{}".format(launch["submission_token"])
    expected_command = _expected_submit_command(paths, launch["submission_token"])
    if (
        type(rows) is not list or not rows
        or value.get("rows_sha256") != _digest(rows)
        or value.get("no_resubmission") is not True
        or (
            optional <= set(value)
            and (
                value["uncertain_stdout_job_id"] != launch["job_id"]
                or not _is_sha256(value["uncertain_stdout_sha256"])
            )
        )
    ):
        raise SourceConsumerError("V9 scheduler-journal recovery changed")
    for row in rows:
        job_id = row.get("job_id") if type(row) is dict else None
        match = re.fullmatch(
            re.escape(launch["job_id"]) + r"(?:_[0-9]+|_\[[^]]+\])?",
            job_id or "",
        )
        if (
            type(row) is not dict
            or set(row) != {
                "job_id", "job_name", "comment", "submit_command",
            }
            or match is None
            or row.get("job_name") != expected_identity
            or row.get("comment") not in ("", expected_identity)
            or row.get("submit_command") != expected_command
        ):
            raise SourceConsumerError("V9 scheduler-journal row changed")


def _validate_launch(launch: dict, paths: V9Paths) -> None:
    required = {
        "schema": LAUNCH_SCHEMA,
        "campaign": CAMPAIGN,
        "resource_profile": RESOURCE_PROFILE,
        "whole_campaign_fresh": True,
        "prior_runtime_payloads_read": 0,
        "prior_runtime_payload_bytes_read": 0,
        "prior_runtime_payloads_reused": 0,
        "selective_recovery_authorized": False,
    }
    if (
        type(launch) is not dict
        or set(launch) != LAUNCH_RECEIPT_KEYS
        or any(type(launch.get(key)) is not type(value) or launch.get(key) != value
               for key, value in required.items())
        or not isinstance(launch.get("job_id"), str)
        or not launch["job_id"].isdigit()
        or TOKEN_RE.fullmatch(launch.get("submission_token", "")) is None
        or COMMIT_RE.fullmatch(launch.get("repository_commit_id", "")) is None
        or not _is_sha256(launch.get("source_inventory_sha256"))
        or not _is_sha256(launch.get("code_manifest_sha256"))
        or not _is_sha256(launch.get("launch_intent_sha256"))
        or not _is_sha256(launch.get("sbatch_result_sha256"))
        or type(launch.get("launch_recovered")) is not bool
    ):
        raise SourceConsumerError("V9 launch receipt changed")
    expected_roots = {
        "artifact_dir": paths.artifact_dir,
        "log_root": paths.log_root,
        "output_dir": paths.data_root,
        "tmpdir_root": paths.tmpdir_root,
    }
    roots = launch.get("root_identities")
    slurm = launch.get("slurm_program")
    if (
        type(roots) is not dict or set(roots) != set(expected_roots)
        or any(
            roots.get(name) != _expected_root_identity(path, "V9 " + name)
            for name, path in expected_roots.items()
        )
        or type(slurm) is not dict
        or set(slurm) != {
            "template_path", "template_sha256", "rendered_sha256",
            "rendered_bytes", "submission_mode", "path_argument",
        }
        or slurm.get("template_path") != str(paths.slurm_program)
        or not _is_sha256(slurm.get("template_sha256"))
        or not _is_sha256(slurm.get("rendered_sha256"))
        or type(slurm.get("rendered_bytes")) is not int
        or slurm["rendered_bytes"] <= 0
        or slurm.get("submission_mode") != "stdin"
        or slurm.get("path_argument") is not False
    ):
        raise SourceConsumerError("V9 launch roots or Slurm program changed")
    _validate_recovery(launch.get("recovery_evidence"), launch, paths)


def _snapshot_read(
    reader: SnapshotReader, revision: str, paths: list[str], label: str,
) -> dict[str, bytes]:
    try:
        value = reader(revision, paths)
    except Exception as err:
        raise SourceConsumerError("cannot read {} snapshot".format(label)) from err
    if (
        type(value) is not dict or set(value) != set(paths)
        or any(type(raw) is not bytes for raw in value.values())
    ):
        raise SourceConsumerError("{} snapshot file set changed".format(label))
    return value


def _validate_slurm_template(template: bytes, launch: dict) -> None:
    try:
        lines = template.decode("ascii").splitlines()
        log_root = launch["root_identities"]["log_root"]["path"]
    except (UnicodeDecodeError, KeyError, TypeError) as err:
        raise SourceConsumerError("V9 Slurm template evidence changed") from err
    header = [
        "#!/bin/bash",
        "#SBATCH --account=" + RESOURCE_PROFILE["account"],
        "#SBATCH --partition=fat",
        "#SBATCH --qos=normal",
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --mem=26G",
        "#SBATCH --time=01:10:00",
        "#SBATCH --array=0-819",
        "#SBATCH --output={}/slurm-%A_%a.out".format(log_root),
        "#SBATCH --error={}/slurm-%A_%a.err".format(log_root),
        "#SBATCH --export=NONE",
        "#SBATCH --nice=0",
        "#SBATCH --no-requeue",
    ]
    if (
        lines[:len(header)] != header
        or any(line.startswith("#SBATCH") for line in lines[len(header):])
        or "%" in header[9]
        or template.count(MANIFEST_PLACEHOLDER) != 1
        or template.count(INVENTORY_PLACEHOLDER) != 1
        or template.count(COMMIT_PLACEHOLDER) != 1
        or sum(line.startswith("    --num-shards 820 ") for line in lines) != 1
        or sum(
            line.startswith('    --shard-index "${SLURM_ARRAY_TASK_ID}" ')
            for line in lines
        ) != 1
        or lines.count('    --tmp-root "${tmp_root}"') != 1
    ):
        raise SourceConsumerError("V9 Slurm resource or execution contract changed")


def _validate_producer_snapshot(
    launch: dict, snapshot_reader: SnapshotReader,
) -> dict[str, str]:
    revision = launch["repository_commit_id"]
    manifest_snapshot = _snapshot_read(
        snapshot_reader, revision, [CODE_MANIFEST_RELATIVE], "V9 manifest",
    )
    manifest_raw = manifest_snapshot[CODE_MANIFEST_RELATIVE]
    if (
        hashlib.sha256(manifest_raw).hexdigest()
        != launch["code_manifest_sha256"]
        or not manifest_raw.endswith(b"\n")
    ):
        raise SourceConsumerError("V9 committed code manifest changed")
    records = {}
    try:
        lines = manifest_raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise SourceConsumerError("V9 code manifest is not ASCII") from err
    old_campaign = re.compile(r"(?:^|[_-])v[1-8](?:[_.-]|$)")
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([!-~]+)", line)
        if match is None:
            raise SourceConsumerError("V9 code-manifest record changed")
        digest, relative = match.groups()
        candidate = Path(relative)
        if (
            relative in records or candidate.is_absolute()
            or ".." in candidate.parts or old_campaign.search(relative)
        ):
            raise SourceConsumerError("V9 code-manifest path changed")
        records[relative] = digest
    if (
        tuple(records) != CODE_MANIFEST_FILES
        or CODE_MANIFEST_RELATIVE in records
    ):
        raise SourceConsumerError("V9 code-manifest closure changed")
    requested = [CODE_MANIFEST_RELATIVE, *records]
    snapshot = _snapshot_read(snapshot_reader, revision, requested, "V9 producer")
    if snapshot[CODE_MANIFEST_RELATIVE] != manifest_raw:
        raise SourceConsumerError("V9 manifest changed between snapshot reads")
    for relative, digest in records.items():
        if hashlib.sha256(snapshot[relative]).hexdigest() != digest:
            raise SourceConsumerError("V9 committed producer byte changed")
    template = snapshot[SLURM_PROGRAM_RELATIVE]
    slurm = launch["slurm_program"]
    markers = (
        MANIFEST_PLACEHOLDER, INVENTORY_PLACEHOLDER, COMMIT_PLACEHOLDER,
    )
    if (
        hashlib.sha256(template).hexdigest() != slurm["template_sha256"]
        or any(template.count(marker) != 1 for marker in markers)
    ):
        raise SourceConsumerError("V9 committed Slurm template changed")
    _validate_slurm_template(template, launch)
    rendered = template.replace(
        MANIFEST_PLACEHOLDER, launch["code_manifest_sha256"].encode("ascii"),
    ).replace(
        INVENTORY_PLACEHOLDER,
        launch["source_inventory_sha256"].encode("ascii"),
    ).replace(
        COMMIT_PLACEHOLDER, launch["repository_commit_id"].encode("ascii"),
    )
    if (
        any(marker in rendered for marker in markers)
        or hashlib.sha256(rendered).hexdigest() != slurm["rendered_sha256"]
        or len(rendered) != slurm["rendered_bytes"]
    ):
        raise SourceConsumerError("V9 rendered Slurm program changed")
    return {
        CODE_MANIFEST_RELATIVE: launch["code_manifest_sha256"],
        **records,
    }


def _valid_process_observation(value: Any) -> bool:
    if (
        type(value) is not dict
        or set(value) != {
            "kind", "returncode", "os_error_type", "os_error_errno",
        }
    ):
        return False
    return (
        (
            value["kind"] == "completed-process"
            and type(value["returncode"]) is int
            and value["os_error_type"] is None
            and value["os_error_errno"] is None
        )
        or (
            value["kind"] == "os-error"
            and value["returncode"] is None
            and isinstance(value["os_error_type"], str)
            and (
                value["os_error_errno"] is None
                or type(value["os_error_errno"]) is int
            )
        )
        or (
            value["kind"] == "controller-crash-returncode-unavailable"
            and value["returncode"] is None
            and value["os_error_type"] is None
            and value["os_error_errno"] is None
        )
    )


def _validate_launch_artifacts(
    paths: V9Paths, launch: dict, tracked: Mapping[str, str],
) -> dict[str, bytes]:
    """Bind the launch receipt to the independently replayed launch journal."""
    intent_raw, intent = _read_json(
        paths.launch_intent, "V9 launch intent",
        expected_mode=0o400, expected_uid=os.getuid(),
    )
    if (
        hashlib.sha256(intent_raw).hexdigest()
        != launch["launch_intent_sha256"]
        or set(intent) != LAUNCH_INTENT_KEYS
    ):
        raise SourceConsumerError("V9 launch-intent hash or shape changed")
    recorded = intent.get("recorded_utc")
    try:
        timestamp = datetime.datetime.fromisoformat(recorded)
    except (TypeError, ValueError) as err:
        raise SourceConsumerError("V9 launch timestamp changed") from err
    if (
        timestamp.tzinfo is None
        or timestamp.utcoffset() != datetime.timedelta(0)
        or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:"
            r"[0-9]{2}:[0-9]{2}\+00:00",
            recorded,
        ) is None
    ):
        raise SourceConsumerError("V9 launch timestamp changed")

    initial = intent.get("sbatch_capture_initial_identities")
    if type(initial) is not dict or set(initial) != {"stdout", "stderr"}:
        raise SourceConsumerError("V9 initial capture identities changed")
    stdout_raw, stdout_info = _read_regular_with_stat(
        paths.sbatch_stdout, "V9 sbatch stdout",
        expected_mode=0o400, expected_uid=os.getuid(),
    )
    stderr_raw, stderr_info = _read_regular_with_stat(
        paths.sbatch_stderr, "V9 sbatch stderr",
        expected_mode=0o400, expected_uid=os.getuid(),
    )
    capture_records = {
        "stdout": _capture_record(
            paths.sbatch_stdout, stdout_raw, stdout_info, initial["stdout"],
            "V9 sbatch stdout",
        ),
        "stderr": _capture_record(
            paths.sbatch_stderr, stderr_raw, stderr_info, initial["stderr"],
            "V9 sbatch stderr",
        ),
    }
    identities = {
        (
            record["initial_identity"]["device"],
            record["initial_identity"]["inode"],
        )
        for record in capture_records.values()
    }
    if len(identities) != 2:
        raise SourceConsumerError("V9 sbatch captures alias")

    try:
        code_records = [
            {"path": relative, "sha256": tracked[relative]}
            for relative in CODE_MANIFEST_FILES
        ]
    except KeyError as err:
        raise SourceConsumerError("V9 launch manifest is incomplete") from err
    zero_prior = {
        "prior_runtime_payloads_read": 0,
        "prior_runtime_payload_bytes_read": 0,
        "prior_runtime_payloads_reused": 0,
        "selective_recovery_authorized": False,
        "whole_campaign_fresh": True,
    }
    expected_intent = {
        "schema": LAUNCH_INTENT_SCHEMA,
        "campaign": CAMPAIGN,
        "recorded_utc": recorded,
        "submission_token": launch["submission_token"],
        "repository_commit_id": launch["repository_commit_id"],
        "resource_profile": RESOURCE_PROFILE,
        "array_mapping": _array_mapping(),
        "source_inventory": {
            "path": str(paths.inventory),
            "sha256": launch["source_inventory_sha256"],
            "candidate_count": CANDIDATE_COUNT,
        },
        "source_inventory_sha256": launch["source_inventory_sha256"],
        "code_manifest": {
            "path": str(paths.code_manifest),
            "sha256": launch["code_manifest_sha256"],
            "files": code_records,
            "files_sha256": _digest(code_records),
        },
        "code_manifest_sha256": launch["code_manifest_sha256"],
        "slurm_program": launch["slurm_program"],
        "root_identities": launch["root_identities"],
        "execution_environment": _execution_environment(paths),
        "capture_protocol": CAPTURE_PROTOCOL,
        "sbatch_capture_initial_identities": initial,
        "submit_command": _expected_submit_command(
            paths, launch["submission_token"],
        ),
        **zero_prior,
    }
    if intent != expected_intent:
        raise SourceConsumerError("V9 launch intent changed")

    result_raw, result = _read_json(
        paths.sbatch_result, "V9 sbatch result",
        expected_mode=0o400, expected_uid=os.getuid(),
    )
    process = result.get("process_observation")
    parsed_job_id = _parse_job_id(stdout_raw)
    accepted = (
        _valid_process_observation(process)
        and process["kind"] == "completed-process"
        and process["returncode"] == 0
        and parsed_job_id is not None
    )
    expected_result = {
        "schema": SBATCH_RESULT_SCHEMA,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "submit_command_sha256": _digest(intent["submit_command"]),
        "slurm_program_sha256": launch["slurm_program"]["rendered_sha256"],
        "capture_protocol": CAPTURE_PROTOCOL,
        "process_observation": process,
        "stdout": capture_records["stdout"],
        "stderr": capture_records["stderr"],
        "parsed_job_id": parsed_job_id,
        "accepted_by_launcher": accepted,
        "raw_streams_preserved": True,
    }
    if (
        hashlib.sha256(result_raw).hexdigest()
        != launch["sbatch_result_sha256"]
        or set(result) != SBATCH_RESULT_KEYS
        or not _valid_process_observation(process)
        or result != expected_result
    ):
        raise SourceConsumerError("V9 sbatch result or capture changed")

    validated_raws = {
        LAUNCH_INTENT_FILENAME: intent_raw,
        SBATCH_STDOUT_FILENAME: stdout_raw,
        SBATCH_STDERR_FILENAME: stderr_raw,
        SBATCH_RESULT_FILENAME: result_raw,
    }
    evidence = launch["recovery_evidence"]
    if launch["launch_recovered"] is False:
        if not accepted or parsed_job_id != launch["job_id"] or evidence is not None:
            raise SourceConsumerError("V9 non-recovered launch is unauthorized")
        return validated_raws
    if parsed_job_id is not None and parsed_job_id != launch["job_id"]:
        raise SourceConsumerError("V9 recovered stdout disagrees with the job")
    if accepted:
        if evidence != {
            "source": "retained-sbatch-stdout",
            "job_id": launch["job_id"],
            "stdout_sha256": capture_records["stdout"]["sha256"],
            "accepted_returncode_zero": True,
            "no_resubmission": True,
        }:
            raise SourceConsumerError("V9 retained-stdout recovery changed")
        return validated_raws
    if evidence.get("source") != "scheduler-submission-journal":
        raise SourceConsumerError("V9 recovery journal changed")
    optional = {"uncertain_stdout_job_id", "uncertain_stdout_sha256"}
    if parsed_job_id is None:
        if optional & set(evidence):
            raise SourceConsumerError("V9 spurious uncertain stdout changed")
    elif (
        not optional <= set(evidence)
        or evidence["uncertain_stdout_job_id"] != parsed_job_id
        or evidence["uncertain_stdout_sha256"]
        != capture_records["stdout"]["sha256"]
    ):
        raise SourceConsumerError("V9 uncertain stdout recovery changed")
    return validated_raws


def _validate_artifact_namespace(paths: V9Paths, launch: dict) -> None:
    expected_root = launch["root_identities"]["artifact_dir"]
    if (
        _expected_root_identity(paths.artifact_dir, "V9 artifact directory")
        != expected_root
    ):
        raise SourceConsumerError("V9 artifact root changed")
    try:
        entries = list(os.scandir(paths.artifact_dir))
    except OSError as err:
        raise SourceConsumerError("cannot enumerate V9 artifact directory") from err
    if sorted(entry.name for entry in entries) != sorted(
        REQUIRED_ARTIFACT_FILENAMES
    ):
        raise SourceConsumerError("V9 artifact namespace changed")
    for entry in entries:
        path = paths.artifact_dir / entry.name
        try:
            info = path.lstat()
        except OSError as err:
            raise SourceConsumerError("V9 artifact entry vanished") from err
        if (
            entry.is_symlink()
            or not entry.is_file(follow_symlinks=False)
            or not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o400
            or info.st_uid != os.getuid()
        ):
            raise SourceConsumerError("V9 artifact entry identity changed")


def _validate_seal_revision(seal_revision: Any, launch: dict) -> None:
    if (
        type(seal_revision) is not str
        or COMMIT_RE.fullmatch(seal_revision) is None
        or seal_revision == launch["repository_commit_id"]
    ):
        raise SourceConsumerError(
            "V9 seal revision must be a distinct exact 40-hex commit"
        )


def _repo_relative(path: Path, label: str) -> str:
    absolute = Path(os.path.abspath(path))
    repository = Path(os.path.abspath(REPO))
    try:
        relative = absolute.relative_to(repository)
    except ValueError as err:
        raise SourceConsumerError("{} is outside the repository".format(label)) from err
    if not relative.parts or ".." in relative.parts:
        raise SourceConsumerError("{} has an unsafe repository path".format(label))
    return relative.as_posix()


def _validate_committed_seal(
    paths: V9Paths, launch: dict, seal_revision: str,
    snapshot_reader: SnapshotReader, tracked: Mapping[str, str],
    consumed_artifacts: Mapping[str, bytes],
) -> None:
    _validate_seal_revision(seal_revision, launch)
    _validate_artifact_namespace(paths, launch)
    if (
        type(consumed_artifacts) is not dict
        or set(consumed_artifacts) != set(REQUIRED_ARTIFACT_FILENAMES)
        or any(type(raw) is not bytes for raw in consumed_artifacts.values())
    ):
        raise SourceConsumerError("V9 consumed artifact closure changed")
    validated_artifacts = {}
    artifact_paths = []
    for filename in REQUIRED_ARTIFACT_FILENAMES:
        path = paths.artifact_dir / filename
        relative = _repo_relative(path, "V9 sealed artifact")
        artifact_paths.append(relative)
        validated_artifacts[relative] = consumed_artifacts[filename]
    source_paths = [CODE_MANIFEST_RELATIVE, *CODE_MANIFEST_FILES]
    requested = [*artifact_paths, *source_paths]
    if len(set(requested)) != len(requested):
        raise SourceConsumerError("V9 committed-seal path closure changed")
    sealed = _snapshot_read(
        snapshot_reader, seal_revision, requested, "V9 committed seal",
    )
    prelaunch = _snapshot_read(
        snapshot_reader, launch["repository_commit_id"], source_paths,
        "V9 prelaunch source closure",
    )
    for relative in artifact_paths:
        if sealed[relative] != validated_artifacts[relative]:
            raise SourceConsumerError("V9 committed artifact byte changed")
    for relative in source_paths:
        expected_sha256 = tracked.get(relative)
        if (
            not _is_sha256(expected_sha256)
            or sealed[relative] != prelaunch[relative]
            or hashlib.sha256(prelaunch[relative]).hexdigest() != expected_sha256
            or hashlib.sha256(sealed[relative]).hexdigest() != expected_sha256
        ):
            raise SourceConsumerError(
                "V9 source closure changed at the seal revision"
            )
    _validate_artifact_namespace(paths, launch)
    for relative, before in validated_artifacts.items():
        filename = Path(relative).name
        after = _read_regular(
            paths.artifact_dir / filename,
            "V9 stable sealed artifact " + filename,
            expected_mode=0o400, expected_uid=os.getuid(),
        )
        if after != before:
            raise SourceConsumerError("V9 live artifact changed during snapshot")


def _translator_source_sha256(tracked: Mapping[str, str]) -> str:
    if tuple(path for path in CODE_MANIFEST_FILES if path in TRANSLATOR_FILES) != (
        TRANSLATOR_FILES
    ):
        raise SourceConsumerError("V9 translator manifest ordering changed")
    try:
        records = [
            {"path": path, "sha256": tracked[path]}
            for path in TRANSLATOR_FILES
        ]
    except KeyError as err:
        raise SourceConsumerError("V9 translator manifest is incomplete") from err
    return _digest(records)


def _validate_scheduler(execution: dict, launch: dict) -> None:
    rows = execution.get("scheduler_rows")
    contracts = execution.get("scheduler_contract_rows")
    expected_job_name = "pdb-source-v9-{}".format(launch["submission_token"])
    if (
        type(rows) is not list
        or type(contracts) is not list
        or len(rows) != SHARD_COUNT
        or len(contracts) != SHARD_COUNT
        or execution.get("scheduler_state_counts") != {"COMPLETED": SHARD_COUNT}
        or execution.get("scheduler_rows_sha256") != _digest(rows)
        or execution.get("scheduler_contract_rows_sha256") != _digest(contracts)
        or execution.get("scheduler_gate_passed") is not True
        or execution.get("scheduler_gate_passed_before_payload_read") is not True
    ):
        raise SourceConsumerError("V9 scheduler gate changed")
    for index, (row, contract) in enumerate(zip(rows, contracts)):
        if row != {
            "array_task": index,
            "state": "COMPLETED",
            "exit_code": "0:0",
            "partition": "fat",
            "restarts": 0,
        }:
            raise SourceConsumerError("V9 scheduler row changed")
        if (
            type(contract) is not dict
            or set(contract) != {
                "array_task", "account", "partition", "qos", "req_cpus",
                "req_mem", "time_limit", "state", "exit_code", "restarts",
                "job_name",
            }
            or contract != {
                "array_task": index,
                "account": RESOURCE_PROFILE["account"],
                "partition": "fat",
                "qos": "normal",
                "req_cpus": 1,
                "req_mem": "26G",
                "time_limit": "01:10:00",
                "state": "COMPLETED",
                "exit_code": "0:0",
                "restarts": 0,
                "job_name": expected_job_name,
            }
        ):
            raise SourceConsumerError("V9 scheduler resource contract changed")


def _validate_execution_header(
    execution: dict, execution_raw: bytes, launch: dict, launch_raw: bytes,
) -> None:
    fixed = {
        "schema": EXECUTION_SCHEMA,
        "campaign": CAMPAIGN,
        "benchmark_revision": BENCHMARK_REVISION,
        "logical_shards": SHARD_COUNT,
        "candidates": CANDIDATE_COUNT,
        "tasks_per_shard": TASKS_PER_SHARD,
        "fresh_full_census": True,
        "candidate_indices_sha256": _candidate_indices_sha256(),
        "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
        "source_inventory_sha256": launch["source_inventory_sha256"],
        "code_manifest_sha256": launch["code_manifest_sha256"],
        "resource_profile": RESOURCE_PROFILE,
        "prior_runtime_payload": PRIOR_RUNTIME_PAYLOAD,
        "partial_v9_reuse_authorized": False,
        "seal_recovery_protocol": "exclusive-five-stage-hash-chain-v1",
        "source_audit_complete": True,
        "confirmation_prelaunch_authorized": True,
    }
    if (
        type(execution) is not dict
        or set(execution) != EXECUTION_KEYS
        or any(type(execution.get(key)) is not type(value) or execution.get(key) != value
               for key, value in fixed.items())
        or len(execution_raw) > MAX_JSON_BYTES
    ):
        raise SourceConsumerError("V9 execution receipt changed")
    for key in (
        "output_tree_sha256", "environment_records_sha256",
        "seal_plan_sha256", "tree_stage_sha256", "census_stage_sha256",
        "split_stage_sha256", "attestation_stage_sha256",
        "attestation_sha256", "attestation_records_sha256", "cohorts_sha256",
    ):
        if not _is_sha256(execution.get(key)):
            raise SourceConsumerError("V9 execution hash chain changed")
    _validate_scheduler(execution, launch)


def _source_key(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        record["directory"], record["problem"], record["problem_file"],
        record["domain_file"],
    )


def _validate_inventory(inventory: dict) -> list[dict]:
    inventory_keys = {
        "schema", "benchmark_revision", "cost_manifest_sha256",
        "shadow_attestation_sha256", "candidate_records_sha256",
        "alias_groups_sha256", "inventory_digests", "counts",
        "shadow_families", "all_prior_families",
        "all_prior_unrepresented_families", "records_sha256", "records",
    }
    fixed = {
        "schema": INVENTORY_SCHEMA,
        "benchmark_revision": BENCHMARK_REVISION,
        "cost_manifest_sha256": COST_MANIFEST_SHA256,
        "shadow_attestation_sha256": SHADOW_ATTESTATION_SHA256,
        "candidate_records_sha256": CANDIDATE_RECORDS_SHA256,
        "alias_groups_sha256": ALIAS_GROUPS_SHA256,
    }
    records = inventory.get("records")
    counts = inventory.get("counts")
    digests = inventory.get("inventory_digests")
    if (
        type(inventory) is not dict
        or set(inventory) != inventory_keys
        or any(inventory.get(key) != value for key, value in fixed.items())
        or type(records) is not list
        or len(records) != CANDIDATE_COUNT
        or inventory.get("records_sha256") != _digest(records)
        or type(counts) is not dict
        or set(counts) != {
            "candidates", "families", "source_aliases", "discarded_aliases",
            "prior_identity_overlap", "prior_problem_hash_overlap",
        }
        or counts.get("candidates") != CANDIDATE_COUNT
        or counts.get("families") != EXPECTED_FAMILIES
        or counts.get("discarded_aliases") != EXPECTED_DISCARDED_ALIASES
        or counts.get("prior_identity_overlap") != 0
        or counts.get("prior_problem_hash_overlap") != 0
        or type(digests) is not dict
        or _digest(digests) != INVENTORY_DIGESTS_SHA256
        or digests.get("family_map") != FAMILY_MAP_SHA256
        or digests.get("candidate_records") != CANDIDATE_RECORDS_SHA256
        or digests.get("alias_groups") != ALIAS_GROUPS_SHA256
    ):
        raise SourceConsumerError("V9 source inventory changed")
    shadow = inventory.get("shadow_families")
    prior = inventory.get("all_prior_families")
    prior_unrepresented = inventory.get("all_prior_unrepresented_families")
    if (
        type(shadow) is not list or shadow != sorted(set(shadow))
        or _digest(shadow) != SHADOW_FAMILY_SEQUENCE_SHA256
        or type(prior) is not list or prior != sorted(set(prior))
        or _digest(prior) != ALL_PRIOR_FAMILY_SEQUENCE_SHA256
        or type(prior_unrepresented) is not list
        or prior_unrepresented != sorted(set(prior_unrepresented))
        or _digest(prior_unrepresented)
        != ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
    ):
        raise SourceConsumerError("V9 inventory family strata changed")
    shadow_set = set(shadow)
    prior_set = set(prior)
    seen_hashes = set()
    candidates = []
    alias_groups = []
    for index, record in enumerate(records):
        if (
            type(record) is not dict
            or set(record) != INVENTORY_RECORD_KEYS
            or record.get("candidate_index") != index
            or record.get("canonical_path") != record.get("problem_file")
            or not _is_sha256(record.get("domain_sha256"))
            or not _is_sha256(record.get("problem_sha256"))
            or record["problem_sha256"] in seen_hashes
            or record.get("is_shadow_family")
            is not (record.get("family") in shadow_set)
            or record.get("is_shadow_unrepresented")
            is not (record.get("family") not in shadow_set)
            or record.get("is_all_prior_represented")
            is not (record.get("family") in prior_set)
            or record.get("is_all_prior_unrepresented")
            is not (record.get("family") not in prior_set)
        ):
            raise SourceConsumerError("V9 inventory record changed")
        seen_hashes.add(record["problem_sha256"])
        candidate = {key: record[key] for key in SOURCE_KEYS}
        aliases = record.get("aliases")
        if (
            type(aliases) is not list or not aliases
            or any(type(alias) is not dict or set(alias) != set(SOURCE_KEYS)
                   for alias in aliases)
            or aliases != sorted(aliases, key=_source_key)
            or aliases[0] != candidate
            or any(alias["family"] != record["family"]
                   or alias["problem_sha256"] != record["problem_sha256"]
                   for alias in aliases)
        ):
            raise SourceConsumerError("V9 inventory aliases changed")
        candidates.append(candidate)
        alias_groups.append({
            "problem_sha256": record["problem_sha256"],
            "canonical": candidate,
            "aliases": aliases,
        })
    if (
        _digest(candidates) != CANDIDATE_RECORDS_SHA256
        or _digest(sorted(alias_groups, key=lambda item: item["problem_sha256"]))
        != ALIAS_GROUPS_SHA256
        or counts.get("source_aliases") != sum(len(record["aliases"]) for record in records)
        or counts.get("families")
        != len({record["family"] for record in records})
        or prior_unrepresented
        != sorted({record["family"] for record in records} - prior_set)
        or len({record["family"] for record in records} & shadow_set)
        != EXPECTED_REPRESENTED_SHADOW_FAMILIES
        or len({record["family"] for record in records} - shadow_set)
        != EXPECTED_SHADOW_UNREPRESENTED_FAMILIES
        or len({record["family"] for record in records} & prior_set)
        != EXPECTED_REPRESENTED_ALL_PRIOR_FAMILIES
        or len(prior_unrepresented) != EXPECTED_ALL_PRIOR_UNREPRESENTED_FAMILIES
    ):
        raise SourceConsumerError("V9 inventory identity commitment changed")
    return records


def _valid_identity(
    value: Any, *, expected_mode: int | None = None,
    expected_uid: int | None = None,
) -> bool:
    return (
        type(value) is dict
        and set(value) == {"device", "inode", "mode", "uid", "size"}
        and all(type(value[key]) is int and value[key] >= 0 for key in value)
        and value["inode"] > 0
        and (expected_mode is None or value["mode"] == expected_mode)
        and (expected_uid is None or value["uid"] == expected_uid)
    )


def _resource_contract() -> dict:
    return {
        "schema": RESOURCE_CONTRACT_SCHEMA,
        "address_space_bytes": ADDRESS_SPACE_BYTES,
        "cpu_soft_seconds": CPU_LIMIT_SECONDS,
        "cpu_hard_seconds": CPU_HARD_LIMIT_SECONDS,
        "child_wall_watchdog_seconds": WALL_WATCHDOG_SECONDS,
        "wall_watchdog_is_scientific_exclusion": False,
        "memory_exit_code": 20,
        "cpu_time_exit_code": 21,
        "input_error_exit_code": 31,
        "handshake_failure_exit_code": 70,
        "release_byte_base64": "Rw==",
        "candidate_process_group_isolated": True,
        "candidate_process_creation_denied": True,
        "denied_process_syscalls": list(DENIED_PROCESS_SYSCALLS),
        "pinned_python_sha256": PINNED_PYTHON_SHA256,
        "prlimit_sha256": PRLIMIT_SHA256,
        "libseccomp_sha256": LIBSECCOMP_SHA256,
    }


def _valid_stream(value: Any, expected_path: str) -> bool:
    if (
        type(value) is not dict
        or set(value) != {
            "total_bytes", "sha256", "retained_path", "retained_bytes",
            "retained_sha256", "retention_limit_bytes", "truncated",
            "tail_base64", "tail_bytes",
        }
        or type(value["total_bytes"]) is not int or value["total_bytes"] < 0
        or not _is_sha256(value["sha256"])
        or value["retained_path"] != expected_path
        or type(value["retained_bytes"]) is not int
        or value["retained_bytes"] != min(value["total_bytes"], STREAM_PREFIX_BYTES)
        or not _is_sha256(value["retained_sha256"])
        or value["retention_limit_bytes"] != STREAM_PREFIX_BYTES
        or value["truncated"] is not (
            value["total_bytes"] > value["retained_bytes"]
        )
        or type(value["tail_bytes"]) is not int
        or value["tail_bytes"] != min(value["total_bytes"], STREAM_TAIL_BYTES)
        or not isinstance(value["tail_base64"], str)
    ):
        return False
    try:
        tail = base64.b64decode(value["tail_base64"], validate=True)
    except (ValueError, TypeError):
        return False
    return len(tail) == value["tail_bytes"]


def _validate_sas(value: Any) -> None:
    integer_fields = (
        "sas_version", "metric", "num_variables", "num_mutex_groups",
        "num_operators", "num_effects", "num_conditional_effects",
        "num_zero_cost_operators", "num_serialized_axioms",
    )
    optional_fields = ("min_operator_cost", "max_operator_cost")
    if (
        type(value) is not dict or set(value) != SAS_KEYS
        or any(type(value[field]) is not int or value[field] < 0
               for field in integer_fields)
        or any(value[field] is not None and (
            type(value[field]) is not int or value[field] < 0
        ) for field in optional_fields)
        or value["sas_version"] != 3
        or value["metric"] not in (0, 1)
        or (value["num_operators"] == 0) is not (
            value["min_operator_cost"] is None
            and value["max_operator_cost"] is None
        )
        or (
            value["num_operators"] > 0
            and value["min_operator_cost"] > value["max_operator_cost"]
        )
    ):
        raise SourceConsumerError("V9 SAS evidence changed")


def _support_reasons(task: dict) -> tuple[bool | None, list[str] | None, bool]:
    outcome = task["status"]
    if outcome == "resource-excluded":
        return None, None, False
    if outcome == "input-rejected":
        return False, ["translation-input-rejected"], False
    sas = task["sas"]
    normalization = task["normalization"]
    reasons = []
    if sas["num_operators"] < 1:
        reasons.append("no-serialized-operators")
    if (
        sas["num_zero_cost_operators"] != 0
        or sas["min_operator_cost"] is None
        or sas["min_operator_cost"] < 1
    ):
        reasons.append("nonpositive-serialized-operator-cost")
    if sas["num_serialized_axioms"] != 0:
        reasons.append("serialized-axioms")
    if sas["num_conditional_effects"] != 0:
        reasons.append("serialized-conditional-effects")
    if normalization["num_normalized_axioms"] != 0:
        reasons.append("normalized-axioms")
    return not reasons, reasons, not reasons


def _validate_task(
    task: dict, inventory_record: dict, index: int, *,
    code_manifest_sha256: str | None = None,
    repository_commit_id: str | None = None,
) -> None:
    stdout_name = "candidate-{:04d}.stdout.prefix".format(index)
    stderr_name = "candidate-{:04d}.stderr.prefix".format(index)
    if (
        type(task) is not dict or set(task) != TASK_KEYS
        or any(task.get(key) != inventory_record[key] for key in INVENTORY_RECORD_KEYS)
        or task.get("schema") != CANDIDATE_SCHEMA
        or task.get("logical_shard_index") != index // TASKS_PER_SHARD
        or task.get("position_in_shard") != index % TASKS_PER_SHARD
        or task.get("candidate_origin") != FRESH_ORIGIN
        or task.get("translation_attempted") is not True
        or task.get("translator_command") != [
            "PINNED_PYTHON", "-B",
            "experiments/pdb_terminal_incidence_confirmation_translate_v9.py",
            "--", task.get("domain_file"), task.get("problem_file"),
        ]
        or not _is_sha256(task.get("code_manifest_sha256"))
        or (
            code_manifest_sha256 is not None
            and task.get("code_manifest_sha256") != code_manifest_sha256
        )
        or COMMIT_RE.fullmatch(task.get("repository_commit_id", "")) is None
        or (
            repository_commit_id is not None
            and task.get("repository_commit_id") != repository_commit_id
        )
        or task.get("resource_contract") != _resource_contract()
        or task.get("resource_contract_sha256") != _digest(_resource_contract())
        or task.get("status") not in OUTCOMES
        or task.get("complete_process_group_reaped") is not True
        or not _valid_stream(task.get("stdout"), stdout_name)
        or not _valid_stream(task.get("stderr"), stderr_name)
    ):
        raise SourceConsumerError("V9 candidate record changed")
    limits = task["child_limit_attestation"]
    if (
        type(limits) is not dict
        or set(limits) != {
            "schema", "pid", "process_group", "rlimit_as", "rlimit_cpu",
            "no_new_privs", "seccomp_mode", "seccomp_filters", "threads",
        }
        or limits.get("schema") != CHILD_LIMIT_SCHEMA
        or type(limits.get("pid")) is not int or limits["pid"] <= 0
        or limits.get("process_group") != limits["pid"]
        or limits.get("rlimit_as") != [ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES]
        or limits.get("rlimit_cpu") != [CPU_LIMIT_SECONDS, CPU_HARD_LIMIT_SECONDS]
        or limits.get("no_new_privs") != 1
        or limits.get("seccomp_mode") != 2
        or type(limits.get("seccomp_filters")) is not int
        or limits["seccomp_filters"] < 1
        or limits.get("threads") != 1
    ):
        raise SourceConsumerError("V9 child-limit evidence changed")
    parent = task.get("parent_prlimit_observation")
    expected_prlimit_stdout = (
        "AS {} {} bytes\nCPU {} {} seconds\n".format(
            ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES,
            CPU_LIMIT_SECONDS, CPU_HARD_LIMIT_SECONDS,
        ).encode("ascii")
    )
    if parent != {
        "tool_sha256": PRLIMIT_SHA256,
        "command": [
            "/usr/bin/prlimit", "--pid", "CHILD_PID", "--as", "--cpu",
            "--output=RESOURCE,SOFT,HARD,UNITS", "--noheadings", "--raw",
        ],
        "stdout_sha256": hashlib.sha256(expected_prlimit_stdout).hexdigest(),
        "rlimit_as": [ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES],
        "rlimit_cpu": [CPU_LIMIT_SECONDS, CPU_HARD_LIMIT_SECONDS],
    }:
        raise SourceConsumerError("V9 parent limit observation changed")
    isolation = task.get("parent_isolation_observation")
    if (
        type(isolation) is not dict
        or set(isolation) != {
            "status_sha256", "process_group", "no_new_privs",
            "seccomp_mode", "seccomp_filters", "threads",
            "process_creation_syscalls_denied", "libseccomp_sha256",
        }
        or not _is_sha256(isolation.get("status_sha256"))
        or isolation.get("process_group") != limits["pid"]
        or isolation.get("no_new_privs") != 1
        or isolation.get("seccomp_mode") != 2
        or isolation.get("seccomp_filters") != limits["seccomp_filters"]
        or isolation.get("threads") != 1
        or isolation.get("process_creation_syscalls_denied")
        != list(DENIED_PROCESS_SYSCALLS)
        or isolation.get("libseccomp_sha256") != LIBSECCOMP_SHA256
    ):
        raise SourceConsumerError("V9 parent isolation observation changed")
    _validate_source_snapshot(task.get("source_snapshot"), inventory_record)
    outcome = task["status"]
    normalization = task.get("normalization")
    if outcome == "success":
        if (
            task.get("process_returncode") != 0
            or not _is_sha256(task.get("sas_sha256"))
            or type(task.get("sas_bytes")) is not int
            or task["sas_bytes"] <= 0
            or task.get("partial_sas_evidence") is not None
            or task.get("resource_exclusion_kind") is not None
            or type(normalization) is not dict
            or set(normalization) != {
                "schema", "strategy", "num_normalized_axioms",
            }
            or normalization.get("schema") != NORMALIZATION_SCHEMA
            or normalization.get("strategy") != "axiom_based"
            or type(normalization.get("num_normalized_axioms")) is not int
            or normalization["num_normalized_axioms"] < 0
        ):
            raise SourceConsumerError("V9 successful translation evidence changed")
        _validate_sas(task.get("sas"))
    elif outcome == "input-rejected":
        if (
            task.get("process_returncode") != 31
            or task.get("sas") is not None
            or task.get("sas_bytes") is not None
            or task.get("sas_sha256") is not None
            or task.get("partial_sas_evidence") is not None
            or normalization is not None
            or task.get("resource_exclusion_kind") is not None
        ):
            raise SourceConsumerError("V9 input rejection evidence changed")
    else:
        exclusion = task.get("resource_exclusion_kind")
        partial = task.get("partial_sas_evidence")
        if (
            exclusion not in RESOURCE_KINDS
            or task.get("process_returncode") != (
                20 if exclusion == "memory" else 21
            )
            or task.get("sas") is not None
            or task.get("sas_bytes") is not None
            or task.get("sas_sha256") is not None
            or normalization is not None and (
                type(normalization) is not dict
                or set(normalization) != {
                    "schema", "strategy", "num_normalized_axioms",
                }
                or normalization.get("schema") != NORMALIZATION_SCHEMA
                or normalization.get("strategy") != "axiom_based"
                or type(normalization.get("num_normalized_axioms")) is not int
                or normalization["num_normalized_axioms"] < 0
            )
            or partial is not None and (
                type(partial) is not dict
                or set(partial) != {"bytes", "sha256", "discarded"}
                or type(partial.get("bytes")) is not int or partial["bytes"] < 0
                or not _is_sha256(partial.get("sha256"))
                or partial.get("discarded") is not True
            )
        ):
            raise SourceConsumerError("V9 resource exclusion evidence changed")
    supported, reasons, eligible = _support_reasons(task)
    if (
        task.get("support_determined") is not (supported is not None)
        or task.get("supported") is not supported
        or task.get("support_exclusion_reasons") != reasons
        or task.get("eligible_for_cohort") is not eligible
    ):
        raise SourceConsumerError("V9 support/eligibility classification changed")


def _validate_source_snapshot(value: Any, inventory_record: dict) -> None:
    files = value.get("files") if type(value) is dict else None
    if (
        type(value) is not dict
        or set(value) != {
            "schema", "files", "candidate_private_working_directory",
            "source_hashes_verified_before_use",
            "identity_and_sha256_verified_after_use",
            "exact_snapshot_files_removed",
        }
        or value.get("schema") != SOURCE_SNAPSHOT_SCHEMA
        or type(files) is not list or len(files) != 2
        or value.get("candidate_private_working_directory") is not True
        or value.get("source_hashes_verified_before_use") is not True
        or value.get("identity_and_sha256_verified_after_use") is not True
        or value.get("exact_snapshot_files_removed") is not True
    ):
        raise SourceConsumerError("V9 source snapshot changed")
    for item, role, file_key, sha_key, snapshot_name in zip(
        files,
        ("domain", "problem"),
        ("domain_file", "problem_file"),
        ("domain_sha256", "problem_sha256"),
        ("domain.pddl", "problem.pddl"),
    ):
        if (
            type(item) is not dict
            or set(item) != {
                "role", "source_file", "source_identity", "snapshot_name",
                "snapshot_identity_before", "bytes", "sha256",
                "snapshot_identity_after",
            }
            or item.get("role") != role
            or item.get("source_file") != inventory_record[file_key]
            or item.get("snapshot_name") != snapshot_name
            or type(item.get("bytes")) is not int or item["bytes"] <= 0
            or item.get("sha256") != inventory_record[sha_key]
            or not _valid_identity(item.get("source_identity"))
            or not _valid_identity(
                item.get("snapshot_identity_before"), expected_mode=0o400,
                expected_uid=os.getuid(),
            )
            or item.get("snapshot_identity_after")
            != item.get("snapshot_identity_before")
            or item["snapshot_identity_before"]["size"] != item["bytes"]
            or item["source_identity"]["size"] != item["bytes"]
        ):
            raise SourceConsumerError("V9 source-snapshot file changed")


def _rank(record: Mapping[str, Any], role: str) -> str:
    fields = (
        SPLIT_SEED, role, record["family"], record["problem_sha256"],
        record["canonical_path"],
    )
    return hashlib.sha256(b"\0".join(
        field.encode("utf-8") for field in fields
    )).hexdigest()


def _stratum_summary(records: list[dict], key: str) -> dict:
    selected = [record["candidate_index"] for record in records if record[key]]
    families = sorted({record["family"] for record in records if record[key]})
    return {
        "tasks": len(selected),
        "families": len(families),
        "candidate_indices_sha256": _digest(selected),
        "families_sha256": _digest(families),
    }


def _expected_split(records: list[dict]) -> tuple[dict, dict, list[dict], list[dict]]:
    supported = [record for record in records if record["eligible_for_cohort"]]
    by_family = defaultdict(list)
    for record in supported:
        by_family[record["family"]].append(record)
    guided_base = []
    guided_hashes = set()
    for family in sorted(by_family):
        ordered = sorted(by_family[family], key=lambda record: (
            _rank(record, GUIDED_ROLE), record["canonical_path"],
        ))
        for record in ordered[:min(3, len(ordered) // 2)]:
            guided_base.append(record)
            guided_hashes.add(record["problem_sha256"])
    queues = {}
    for family in sorted(by_family):
        queues[family] = deque(sorted(
            (record for record in by_family[family]
             if record["problem_sha256"] not in guided_hashes),
            key=lambda record: (
                _rank(record, CONFIRMATION_ROLE), record["canonical_path"],
            ),
        ))
    confirmation = []
    while len(confirmation) < CONFIRMATION_TASKS:
        progressed = False
        for family in sorted(queues):
            if queues[family] and len(confirmation) < CONFIRMATION_TASKS:
                confirmation.append(queues[family].popleft())
                progressed = True
        if not progressed:
            break
    selected_hashes = guided_hashes | {
        record["problem_sha256"] for record in confirmation
    }
    guided_counts = Counter(record["family"] for record in guided_base)
    top_up_queues = {
        family: deque(sorted(
            (record for record in by_family[family]
             if record["problem_sha256"] not in selected_hashes),
            key=lambda record: (
                _rank(record, GUIDED_TOP_UP_ROLE), record["canonical_path"],
            ),
        ))
        for family in sorted(by_family)
    }
    remaining = sum(len(queue) for queue in top_up_queues.values())
    capacity = len(guided_base) + sum(min(
        len(top_up_queues[family]),
        MAX_GUIDED_TASKS_PER_FAMILY - guided_counts[family],
    ) for family in top_up_queues)
    guided_top_up = []
    while len(guided_base) + len(guided_top_up) < GUIDED_TARGET_TASKS:
        progressed = False
        for family in sorted(top_up_queues):
            if (
                top_up_queues[family]
                and guided_counts[family] < MAX_GUIDED_TASKS_PER_FAMILY
                and len(guided_base) + len(guided_top_up) < GUIDED_TARGET_TASKS
            ):
                record = top_up_queues[family].popleft()
                guided_top_up.append(record)
                guided_counts[family] += 1
                progressed = True
        if not progressed:
            break
    guided_base.sort(key=lambda record: (
        record["family"], _rank(record, GUIDED_ROLE), record["canonical_path"],
    ))
    guided = guided_base + guided_top_up
    confirmation_families = {record["family"] for record in confirmation}
    guided_families = {record["family"] for record in guided}
    confirmation_all_prior = [
        record for record in confirmation
        if record["is_all_prior_unrepresented"]
    ]
    guided_all_prior = [
        record for record in guided if record["is_all_prior_unrepresented"]
    ]
    clauses = {
        "confirmation_tasks": {
            "actual": len(confirmation), "required": CONFIRMATION_TASKS,
            "passed": len(confirmation) == CONFIRMATION_TASKS,
        },
        "confirmation_families": {
            "actual": len(confirmation_families),
            "required_minimum": MIN_CONFIRMATION_FAMILIES,
            "passed": len(confirmation_families) >= MIN_CONFIRMATION_FAMILIES,
        },
        "confirmation_shadow_unrepresented_families": {
            "actual": len({
                record["family"] for record in confirmation
                if record["is_shadow_unrepresented"]
            }),
            "required_minimum": MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES,
            "passed": len({
                record["family"] for record in confirmation
                if record["is_shadow_unrepresented"]
            }) >= MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES,
        },
        "confirmation_all_prior_unrepresented_tasks": {
            "actual": len(confirmation_all_prior),
            "required_minimum": MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS,
            "passed": len(confirmation_all_prior)
            >= MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS,
        },
        "confirmation_all_prior_unrepresented_families": {
            "actual": len({record["family"] for record in confirmation_all_prior}),
            "required_minimum": MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES,
            "passed": len({record["family"] for record in confirmation_all_prior})
            >= MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES,
        },
        "guided_tasks": {
            "actual": len(guided), "required_minimum": MIN_GUIDED_TASKS,
            "passed": len(guided) >= MIN_GUIDED_TASKS,
        },
        "guided_families": {
            "actual": len(guided_families),
            "required_minimum": MIN_GUIDED_FAMILIES,
            "passed": len(guided_families) >= MIN_GUIDED_FAMILIES,
        },
        "guided_shadow_unrepresented_families": {
            "actual": len({
                record["family"] for record in guided
                if record["is_shadow_unrepresented"]
            }),
            "required_minimum": MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES,
            "passed": len({
                record["family"] for record in guided
                if record["is_shadow_unrepresented"]
            }) >= MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES,
        },
        "guided_all_prior_unrepresented_tasks": {
            "actual": len(guided_all_prior),
            "required_minimum": MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS,
            "passed": len(guided_all_prior)
            >= MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS,
        },
        "guided_all_prior_unrepresented_families": {
            "actual": len({record["family"] for record in guided_all_prior}),
            "required_minimum": MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES,
            "passed": len({record["family"] for record in guided_all_prior})
            >= MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES,
        },
    }
    confirmation_ids = {record["candidate_index"] for record in confirmation}
    guided_ids = {record["candidate_index"] for record in guided}
    confirmation_hashes = {record["problem_sha256"] for record in confirmation}
    guided_hashes_final = {record["problem_sha256"] for record in guided}
    confirmation_sources = {_source_key(record) for record in confirmation}
    guided_sources = {_source_key(record) for record in guided}
    disjointness = {
        "candidate_index_overlap": len(confirmation_ids & guided_ids),
        "problem_sha256_overlap": len(confirmation_hashes & guided_hashes_final),
        "source_identity_overlap": len(confirmation_sources & guided_sources),
    }
    disjointness["passed"] = all(value == 0 for value in disjointness.values())
    gate = {
        "outcome_blind": True,
        "resource_exclusions_ineligible": True,
        "availability": {
            "supported_tasks": len(supported),
            "supported_families": len(by_family),
            "supported_candidate_indices_sha256": _digest([
                record["candidate_index"] for record in supported
            ]),
            "shadow_unrepresented": _stratum_summary(
                supported, "is_shadow_unrepresented",
            ),
            "all_prior_unrepresented": _stratum_summary(
                supported, "is_all_prior_unrepresented",
            ),
            "post_confirmation_remaining_tasks": remaining,
            "guided_b_maximum_under_family_cap": capacity,
            "guided_b_target_tasks": GUIDED_TARGET_TASKS,
            "guided_b_max_tasks_per_family": MAX_GUIDED_TASKS_PER_FAMILY,
        },
        "clauses": clauses,
        "cohort_disjointness": disjointness,
    }
    gate["passed"] = (
        all(clause["passed"] for clause in clauses.values())
        and gate["cohort_disjointness"]["passed"]
    )
    cohorts = {
        "confirmation_a": {
            "role": CONFIRMATION_ROLE,
            "candidate_indices": [
                record["candidate_index"] for record in confirmation
            ],
            "candidate_indices_sha256": _digest([
                record["candidate_index"] for record in confirmation
            ]),
        },
        "guided_b": {
            "role": GUIDED_ROLE,
            "top_up_role": GUIDED_TOP_UP_ROLE,
            "base_candidate_indices": [
                record["candidate_index"] for record in guided_base
            ],
            "top_up_candidate_indices": [
                record["candidate_index"] for record in guided_top_up
            ],
            "candidate_indices": [record["candidate_index"] for record in guided],
            "candidate_indices_sha256": _digest([
                record["candidate_index"] for record in guided
            ]),
        },
    }
    return gate, cohorts, confirmation, guided


def _summaries(records: list[dict]) -> dict:
    outcomes = Counter(record["status"] for record in records)
    statuses = Counter(
        "indeterminate" if record["supported"] is None
        else "supported" if record["supported"] else "unsupported"
        for record in records
    )
    exclusions = Counter(
        reason for record in records
        for reason in (record["support_exclusion_reasons"] or [])
    )
    resource = Counter(
        record["resource_exclusion_kind"] for record in records
        if record["resource_exclusion_kind"] is not None
    )
    by_family = defaultdict(Counter)
    for record in records:
        if record["resource_exclusion_kind"] is not None:
            by_family[record["family"]][record["resource_exclusion_kind"]] += 1
    return {
        "counts": {
            "candidates": len(records),
            "translation_attempts": sum(record["translation_attempted"] for record in records),
            "support_determinate": sum(record["support_determined"] for record in records),
            "supported": statuses["supported"],
            "unsupported": statuses["unsupported"],
            "indeterminate": statuses["indeterminate"],
            "cohort_eligible": sum(record["eligible_for_cohort"] for record in records),
            "families": len({record["family"] for record in records}),
        },
        "outcome_counts": {key: outcomes[key] for key in OUTCOMES},
        "support_status_counts": {key: statuses[key] for key in SUPPORT_STATUSES},
        "support_exclusion_counts": dict(sorted(exclusions.items())),
        "resource_exclusion_counts": {key: resource[key] for key in RESOURCE_KINDS},
        "resource_exclusions_by_family": {
            family: {
                "memory": counts["memory"], "time": counts["time"],
                "total": counts["memory"] + counts["time"],
            }
            for family, counts in sorted(by_family.items())
        },
    }


def _file_record(path: str, raw: bytes) -> dict:
    return {
        "path": path,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _validate_output_tree(
    paths: V9Paths, execution: dict, launch: dict,
) -> dict[str, dict]:
    tree = execution.get("output_tree")
    files = tree.get("files") if type(tree) is dict else None
    directories = tree.get("directories") if type(tree) is dict else None
    expected_directories = [
        {"path": shard_name(index), "mode": "0500"}
        for index in range(SHARD_COUNT)
    ]
    expected_names = [paths.inventory.name]
    for index in range(SHARD_COUNT):
        expected_names.extend((result_name(index), environment_name(index)))
        for candidate_index in (
            index * TASKS_PER_SHARD, index * TASKS_PER_SHARD + 1,
        ):
            expected_names.extend((
                prefix_name(candidate_index, "stdout"),
                prefix_name(candidate_index, "stderr"),
            ))
    expected_names = sorted(expected_names)
    expected_root = launch.get("root_identities", {}).get("output_dir")
    if (
        type(tree) is not dict
        or set(tree) != {
            "schema", "root", "root_identity", "directories_count",
            "directories", "files_count", "files", "sha256",
        }
        or tree.get("schema") != TREE_SCHEMA
        or tree.get("root") != str(paths.data_root)
        or tree.get("root_identity") != expected_root
        or tree.get("directories_count") != SHARD_COUNT
        or directories != expected_directories
        or type(files) is not list
        or tree.get("files_count") != len(expected_names)
        or execution.get("output_tree_sha256") != _digest(tree)
    ):
        raise SourceConsumerError("V9 output-tree commitment changed")
    records = {}
    for item in files:
        if (
            type(item) is not dict or set(item) != {"path", "bytes", "sha256"}
            or not isinstance(item.get("path"), str) or item["path"] in records
            or type(item.get("bytes")) is not int or item["bytes"] < 0
            or not _is_sha256(item.get("sha256"))
        ):
            raise SourceConsumerError("V9 output-tree file record changed")
        records[item["path"]] = item
    if (
        [item["path"] for item in files] != expected_names
        or sorted(records) != expected_names
        or tree.get("sha256") != _digest({
            "root_identity": expected_root,
            "directories": expected_directories,
            "files": files,
        })
    ):
        raise SourceConsumerError("V9 output-tree file set changed")
    try:
        root_info = paths.data_root.lstat()
        entries = list(os.scandir(paths.data_root))
    except OSError as err:
        raise SourceConsumerError("cannot inspect V9 output tree") from err
    if (
        paths.data_root.is_symlink() or not stat.S_ISDIR(root_info.st_mode)
        or type(expected_root) is not dict
        or set(expected_root) != {
            "path", "canonical_path", "device", "inode", "mode", "uid", "gid",
        }
        or expected_root.get("path") != str(paths.data_root)
        or expected_root.get("canonical_path") != str(paths.data_root)
        or expected_root.get("device") != root_info.st_dev
        or expected_root.get("inode") != root_info.st_ino
        or expected_root.get("mode") != "0700"
        or expected_root.get("uid") != root_info.st_uid
        or expected_root.get("gid") != root_info.st_gid
        or stat.S_IMODE(root_info.st_mode) != 0o700
    ):
        raise SourceConsumerError("V9 output root is not a directory")
    expected_root_entries = [paths.inventory.name] + [
        shard_name(index) for index in range(SHARD_COUNT)
    ]
    if sorted(entry.name for entry in entries) != sorted(expected_root_entries):
        raise SourceConsumerError("live V9 output file set changed")
    for index in range(SHARD_COUNT):
        directory = paths.data_root / shard_name(index)
        try:
            info = directory.lstat()
            children = list(os.scandir(directory))
        except OSError as err:
            raise SourceConsumerError("cannot inspect V9 shard directory") from err
        expected_children = {
            "result.json", "environment.json",
            *("candidate-{:04d}.{}.prefix".format(candidate_index, stream)
              for candidate_index in (
                  index * TASKS_PER_SHARD, index * TASKS_PER_SHARD + 1,
              ) for stream in ("stdout", "stderr")),
        }
        if (
            directory.is_symlink() or not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o500
            or info.st_uid != os.getuid()
            or {entry.name for entry in children} != expected_children
            or any(entry.is_symlink() or not entry.is_file(follow_symlinks=False)
                   for entry in children)
        ):
            raise SourceConsumerError("live V9 shard directory changed")
    for name in expected_names:
        raw = _read_regular(
            paths.data_root / name, "V9 output {}".format(name),
            expected_mode=0o400, expected_uid=os.getuid(),
        )
        if _file_record(name, raw) != records[name]:
            raise SourceConsumerError("live V9 output file changed")
    return records


def _read_bound_json(
    path: Path, relative: str, record: dict, label: str,
) -> tuple[bytes, dict]:
    raw, value = _read_json(
        path, label, expected_mode=0o400, expected_uid=os.getuid(),
    )
    if _file_record(relative, raw) != record:
        raise SourceConsumerError("{} differs from the sealed tree".format(label))
    return raw, value


def _validate_shards_and_environments(
    paths: V9Paths, execution: dict, file_map: dict[str, dict],
    inventory_records: list[dict], launch: dict,
    translator_source_sha256: str,
) -> tuple[list[dict], list[dict]]:
    tasks = []
    environments = []
    for index in range(SHARD_COUNT):
        result_relative = result_name(index)
        result_raw, shard = _read_bound_json(
            paths.data_root / result_relative, result_relative,
            file_map[result_relative],
            "V9 shard {}".format(index),
        )
        expected_indices = [index * TASKS_PER_SHARD + offset
                            for offset in range(TASKS_PER_SHARD)]
        shard_tasks = shard.get("candidates") if type(shard) is dict else None
        if (
            type(shard) is not dict
            or set(shard) != {
                "schema", "campaign", "whole_campaign_rerun",
                "logical_shard_index", "array_task_count", "candidate_indices",
                "candidate_count", "candidates", "candidate_origin_counts",
                "prior_campaign_payloads_read", "prior_campaign_shards_used",
                "source_inventory_sha256", "code_manifest_sha256",
                "repository_commit_id", "resource_contract_sha256",
            }
            or shard.get("schema") != SHARD_SCHEMA
            or shard.get("campaign") != CAMPAIGN
            or shard.get("whole_campaign_rerun") is not True
            or shard.get("logical_shard_index") != index
            or shard.get("array_task_count") != SHARD_COUNT
            or shard.get("candidate_indices") != expected_indices
            or shard.get("candidate_count") != TASKS_PER_SHARD
            or shard.get("candidate_origin_counts") != {FRESH_ORIGIN: TASKS_PER_SHARD}
            or shard.get("prior_campaign_payloads_read") != []
            or shard.get("prior_campaign_shards_used") != 0
            or shard.get("source_inventory_sha256") != launch["source_inventory_sha256"]
            or shard.get("code_manifest_sha256") != launch["code_manifest_sha256"]
            or shard.get("repository_commit_id") != launch["repository_commit_id"]
            or shard.get("resource_contract_sha256") != _digest(_resource_contract())
            or type(shard_tasks) is not list or len(shard_tasks) != TASKS_PER_SHARD
        ):
            raise SourceConsumerError("V9 shard contract changed")
        for candidate_index, task in zip(expected_indices, shard_tasks):
            _validate_task(
                task, inventory_records[candidate_index], candidate_index,
                code_manifest_sha256=launch["code_manifest_sha256"],
                repository_commit_id=launch["repository_commit_id"],
            )
            for stream in ("stdout", "stderr"):
                relative = prefix_name(candidate_index, stream)
                raw = _read_regular(
                    paths.data_root / relative,
                    "V9 candidate {} {} prefix".format(candidate_index, stream),
                    expected_mode=0o400, expected_uid=os.getuid(),
                )
                frozen = file_map[relative]
                evidence = task[stream]
                if (
                    _file_record(relative, raw) != frozen
                    or len(raw) != evidence["retained_bytes"]
                    or hashlib.sha256(raw).hexdigest()
                    != evidence["retained_sha256"]
                    or (
                        evidence["truncated"] is False
                        and evidence["retained_sha256"] != evidence["sha256"]
                    )
                    or (
                        evidence["truncated"] is False
                        and base64.b64decode(
                            evidence["tail_base64"], validate=True,
                        ) != raw[-STREAM_TAIL_BYTES:]
                    )
                ):
                    raise SourceConsumerError("V9 retained stream prefix changed")
            tasks.append(task)
        environment_relative = environment_name(index)
        _raw, environment = _read_bound_json(
            paths.data_root / environment_relative, environment_relative,
            file_map[environment_relative],
            "V9 environment {}".format(index),
        )
        if not _validate_environment(
            environment, index, expected_indices, launch, shard,
            result_raw, paths, translator_source_sha256,
        ):
            raise SourceConsumerError("V9 environment record changed")
        environments.append(environment)
    if (
        [task["candidate_index"] for task in tasks] != list(range(CANDIDATE_COUNT))
        or execution.get("environment_records_sha256") != _digest(environments)
        or any(
            environment["manifest_evidence"]
            != environments[0]["manifest_evidence"]
            for environment in environments
        )
    ):
        raise SourceConsumerError("V9 full-census sequence changed")
    return tasks, environments


def _validate_environment(
    value: Any, index: int, expected_indices: list[int], launch: dict,
    shard: dict, result_raw: bytes, paths: V9Paths,
    translator_source_sha256: str,
) -> bool:
    if type(value) is not dict or set(value) != {
        "schema", "array_job_id", "array_task_id", "slurm_restart_count",
        "candidate_indices", "task_tmp_identity", "code_manifest_sha256",
        "source_inventory_sha256", "repository_commit_id",
        "pinned_python_identity", "pinned_python_sha256",
        "prior_campaign_payloads_read", "prior_campaign_payloads_reused",
        "manifest_evidence", "output_root_identity",
        "stage_directory_identity", "result_sha256",
    }:
        return False
    manifest = value.get("manifest_evidence")
    output_root = launch.get("root_identities", {}).get("output_dir")
    stage = value.get("stage_directory_identity")
    try:
        live_stage = (paths.data_root / shard_name(index)).lstat()
    except OSError:
        return False
    return (
        value.get("schema") == TASK_ENVIRONMENT_SCHEMA
        and value.get("array_job_id") == launch.get("job_id")
        and value.get("array_task_id") == index
        and value.get("slurm_restart_count") == 0
        and value.get("candidate_indices") == expected_indices
        and _valid_identity(
            value.get("task_tmp_identity"), expected_mode=0o700,
            expected_uid=os.getuid(),
        )
        and value.get("code_manifest_sha256") == launch.get("code_manifest_sha256")
        and value.get("source_inventory_sha256") == launch.get("source_inventory_sha256")
        and value.get("repository_commit_id") == launch.get("repository_commit_id")
        and _valid_identity(value.get("pinned_python_identity"))
        and value.get("pinned_python_sha256") == PINNED_PYTHON_SHA256
        and value["pinned_python_identity"]["size"] > 0
        and value.get("prior_campaign_payloads_read") == []
        and value.get("prior_campaign_payloads_reused") == []
        and type(manifest) is dict
        and set(manifest) == {
            "code_manifest_sha256", "code_manifest_records",
            "pinned_python_sha256", "prlimit_sha256", "libseccomp_sha256",
            "translator_file_count", "translator_files_sha256",
        }
        and manifest.get("code_manifest_sha256") == launch.get("code_manifest_sha256")
        and manifest.get("code_manifest_records") == len(CODE_MANIFEST_FILES)
        and manifest.get("pinned_python_sha256") == PINNED_PYTHON_SHA256
        and manifest.get("prlimit_sha256") == PRLIMIT_SHA256
        and manifest.get("libseccomp_sha256") == LIBSECCOMP_SHA256
        and manifest.get("translator_file_count") == len(TRANSLATOR_FILES)
        and manifest.get("translator_files_sha256") == translator_source_sha256
        and _valid_identity(
            value.get("output_root_identity"), expected_mode=0o700,
            expected_uid=os.getuid(),
        )
        and type(output_root) is dict
        and value["output_root_identity"]["device"] == output_root.get("device")
        and value["output_root_identity"]["inode"] == output_root.get("inode")
        and value["output_root_identity"]["uid"] == output_root.get("uid")
        and value["output_root_identity"]["mode"] == 0o700
        and _valid_identity(
            stage, expected_mode=0o700, expected_uid=os.getuid(),
        )
        and stage["device"] == live_stage.st_dev
        and stage["inode"] == live_stage.st_ino
        and stage["uid"] == live_stage.st_uid
        and stage["mode"] == 0o700
        and stat.S_IMODE(live_stage.st_mode) == 0o500
        and value.get("result_sha256") == hashlib.sha256(result_raw).hexdigest()
        and value["result_sha256"] == _digest(shard)
    )


def _validate_attestation(
    attestation: dict, attestation_raw: bytes, records: list[dict],
    inventory: dict, execution: dict, launch: dict,
    translator_source_sha256: str,
) -> tuple[list[dict], list[dict]]:
    summaries = _summaries(records)
    gate, cohorts, confirmation, guided = _expected_split(records)
    fixed = {
        "schema": ATTESTATION_SCHEMA,
        "campaign": CAMPAIGN,
        "benchmark_revision": BENCHMARK_REVISION,
        "translator_source_sha256": translator_source_sha256,
        "source_inventory_sha256": launch["source_inventory_sha256"],
        "source_inventory_records_sha256": inventory["records_sha256"],
        "code_manifest_sha256": launch["code_manifest_sha256"],
        "split_seed": SPLIT_SEED,
        "split_rank_encoding": (
            "SHA256(seed || NUL || role || NUL || family || NUL || "
            "problem_sha256 || NUL || canonical_path)"
        ),
        "split_role_labels": {
            "confirmation_a": CONFIRMATION_ROLE,
            "guided_b_base": GUIDED_ROLE,
            "guided_b_top_up": GUIDED_TOP_UP_ROLE,
        },
        "limits": _resource_contract(),
        "full_census_fresh": True,
        "candidate_indices_sha256": _candidate_indices_sha256(),
        "records_sha256": _digest(records),
        "cohorts": cohorts,
        "cohorts_sha256": _digest(cohorts),
        "prelaunch_gate": gate,
        "confirmation_prelaunch_authorized": True,
        "records": records,
        **summaries,
    }
    if (
        type(attestation) is not dict
        or set(attestation) != ATTESTATION_KEYS
        or any(attestation.get(key) != value for key, value in fixed.items())
        or gate["passed"] is not True
        or gate["cohort_disjointness"]["passed"] is not True
        or execution.get("attestation_sha256")
        != hashlib.sha256(attestation_raw).hexdigest()
    ):
        raise SourceConsumerError("V9 attestation or source split changed")
    mirrored = (
        "attestation_records_sha256", "cohorts_sha256", "outcome_counts",
        "support_status_counts", "support_exclusion_counts",
        "resource_exclusion_counts", "resource_exclusions_by_family",
        "prelaunch_gate",
    )
    attestation_keys = {
        "attestation_records_sha256": "records_sha256",
        **{key: key for key in mirrored if key != "attestation_records_sha256"},
    }
    if any(execution.get(key) != attestation.get(source)
           for key, source in attestation_keys.items()):
        raise SourceConsumerError("V9 execution/attestation summary changed")
    return confirmation, guided


def _load_stage(path: Path, digest: str, label: str) -> tuple[bytes, dict]:
    raw, value = _read_json(
        path, label, expected_mode=0o400, expected_uid=os.getuid(),
    )
    if hashlib.sha256(raw).hexdigest() != digest:
        raise SourceConsumerError("{} hash changed".format(label))
    return raw, value


def _validate_stages(
    paths: V9Paths, execution: dict, launch_raw: bytes, attestation_raw: bytes,
    launch: dict, attestation: dict,
) -> dict[str, bytes]:
    plan_raw, plan = _load_stage(
        paths.seal_plan, execution["seal_plan_sha256"], "V9 seal plan",
    )
    tree_raw, tree = _load_stage(
        paths.tree_stage, execution["tree_stage_sha256"], "V9 tree stage",
    )
    census_raw, census = _load_stage(
        paths.census_stage, execution["census_stage_sha256"], "V9 census stage",
    )
    split_raw, split = _load_stage(
        paths.split_stage, execution["split_stage_sha256"], "V9 split stage",
    )
    final_raw, final = _load_stage(
        paths.attestation_stage, execution["attestation_stage_sha256"],
        "V9 attestation stage",
    )
    root_kinds = {paths.inventory.name: "file"}
    root_kinds.update({shard_name(index): "directory" for index in range(SHARD_COUNT)})
    expected_root_entries = [
        {"name": name, "kind": root_kinds[name]}
        for name in sorted(root_kinds)
    ]
    if plan != {
        "schema": SEAL_PLAN_SCHEMA,
        "campaign": CAMPAIGN,
        "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
        "source_inventory_sha256": execution["source_inventory_sha256"],
        "code_manifest_sha256": execution["code_manifest_sha256"],
        "job_id": launch["job_id"],
        "scheduler_rows": execution["scheduler_rows"],
        "scheduler_rows_sha256": execution["scheduler_rows_sha256"],
        "scheduler_contract_rows": execution["scheduler_contract_rows"],
        "scheduler_contract_rows_sha256": execution["scheduler_contract_rows_sha256"],
        "scheduler_gate_passed": True,
        "scheduler_gate_passed_before_payload_read": True,
        "scheduler_restarts": 0,
        "logical_shards": SHARD_COUNT,
        "candidates": CANDIDATE_COUNT,
        "root_identities": launch["root_identities"],
        "expected_output_root_entries": expected_root_entries,
        "expected_output_root_entries_sha256": _digest(expected_root_entries),
        "log_payloads_read": 0,
        "prior_runtime_payloads_read": 0,
    }:
        raise SourceConsumerError("V9 seal plan changed")
    if tree != {
        "schema": TREE_STAGE_SCHEMA,
        "seal_plan_sha256": execution["seal_plan_sha256"],
        "output_tree": execution["output_tree"],
        "output_tree_sha256": execution["output_tree_sha256"],
        "environment_records_sha256": execution["environment_records_sha256"],
    }:
        raise SourceConsumerError("V9 tree stage changed")
    if census != {
        "schema": CENSUS_STAGE_SCHEMA,
        "tree_stage_sha256": execution["tree_stage_sha256"],
        "candidate_count": CANDIDATE_COUNT,
        "candidate_indices_sha256": _candidate_indices_sha256(),
        "candidate_origin_counts": {FRESH_ORIGIN: CANDIDATE_COUNT},
        "whole_campaign_rerun": True,
        "prior_campaign_payloads_read": [],
        "prior_campaign_shards_used": 0,
        "records_sha256": execution["attestation_records_sha256"],
        "counts": attestation["counts"],
        "outcome_counts": execution["outcome_counts"],
        "support_status_counts": execution["support_status_counts"],
        "support_exclusion_counts": execution["support_exclusion_counts"],
        "resource_exclusion_counts": execution["resource_exclusion_counts"],
        "resource_exclusions_by_family": execution["resource_exclusions_by_family"],
    }:
        raise SourceConsumerError("V9 census stage changed")
    if split != {
        "schema": SPLIT_STAGE_SCHEMA,
        "census_stage_sha256": execution["census_stage_sha256"],
        "split_seed": SPLIT_SEED,
        "split_rank_encoding": attestation["split_rank_encoding"],
        "cohorts": attestation["cohorts"],
        "cohorts_sha256": execution["cohorts_sha256"],
        "prelaunch_gate": execution["prelaunch_gate"],
        "confirmation_prelaunch_authorized": True,
    }:
        raise SourceConsumerError("V9 split stage changed")
    if final != {
        "schema": ATTESTATION_STAGE_SCHEMA,
        "split_stage_sha256": execution["split_stage_sha256"],
        "attestation_path": str(paths.attestation),
        "attestation_bytes": len(attestation_raw),
        "attestation_sha256": hashlib.sha256(attestation_raw).hexdigest(),
        "attestation_records_sha256": execution["attestation_records_sha256"],
        "cohorts_sha256": execution["cohorts_sha256"],
        "confirmation_prelaunch_authorized": True,
    }:
        raise SourceConsumerError("V9 attestation stage changed")
    return {
        SEAL_PLAN_FILENAME: plan_raw,
        TREE_STAGE_FILENAME: tree_raw,
        CENSUS_STAGE_FILENAME: census_raw,
        SPLIT_STAGE_FILENAME: split_raw,
        ATTESTATION_STAGE_FILENAME: final_raw,
    }


def load_authorized_confirmation(
    paths: V9Paths | None = None, *, snapshot_reader: SnapshotReader,
    seal_revision: str,
) -> AuthorizedConfirmation:
    """Validate the complete V9 seal and return immutable authorized cohorts.

    The scheduler gate is authenticated before this function opens any V9
    worker payload, stage, inventory, shard, environment, or attestation.
    Any discrepancy raises :class:`SourceConsumerError` and returns no cohort.
    """
    paths = paths or paths_for()
    launch_raw, launch = _read_json(
        paths.launch_receipt, "V9 launch receipt",
        expected_mode=0o400, expected_uid=os.getuid(),
    )
    _validate_launch(launch, paths)
    _validate_seal_revision(seal_revision, launch)
    tracked = _validate_producer_snapshot(launch, snapshot_reader)
    _validate_launch_artifacts(paths, launch, tracked)
    translator_source_sha256 = _translator_source_sha256(tracked)
    execution_raw, execution = _read_json(
        paths.execution_receipt, "V9 execution receipt",
        expected_mode=0o400, expected_uid=os.getuid(),
    )
    _validate_execution_header(execution, execution_raw, launch, launch_raw)
    _validate_artifact_namespace(paths, launch)
    try:
        if any(paths.tmpdir_root.iterdir()):
            raise SourceConsumerError("V9 task TMP root is not empty")
    except SourceConsumerError:
        raise
    except OSError as err:
        raise SourceConsumerError("cannot enumerate V9 task TMP root") from err

    # Only after the exact 820-row all-success gate has passed may payloads be
    # opened.  Preserve this ordering when modifying the function.
    file_map = _validate_output_tree(paths, execution, launch)
    inventory_raw, inventory = _read_bound_json(
        paths.inventory, paths.inventory.name, file_map[paths.inventory.name],
        "V9 source inventory",
    )
    if hashlib.sha256(inventory_raw).hexdigest() != launch["source_inventory_sha256"]:
        raise SourceConsumerError("V9 source-inventory file hash changed")
    inventory_records = _validate_inventory(inventory)
    records, _environments = _validate_shards_and_environments(
        paths, execution, file_map, inventory_records, launch,
        translator_source_sha256,
    )
    attestation_raw, attestation = _read_json(
        paths.attestation, "V9 attestation",
        expected_mode=0o400, expected_uid=os.getuid(),
    )
    confirmation, guided = _validate_attestation(
        attestation, attestation_raw, records, inventory, execution, launch,
        translator_source_sha256,
    )
    stage_raws = _validate_stages(
        paths, execution, launch_raw, attestation_raw, launch, attestation,
    )
    launch_artifact_raws = _validate_launch_artifacts(paths, launch, tracked)
    _validate_artifact_namespace(paths, launch)
    if _validate_output_tree(paths, execution, launch) != file_map:
        raise SourceConsumerError("V9 output tree changed during validation")
    if (
        execution["confirmation_prelaunch_authorized"] is not True
        or execution["source_audit_complete"] is not True
        or attestation["confirmation_prelaunch_authorized"] is not True
    ):
        raise SourceConsumerError("V9 confirmation is not authorized")
    consumed_artifacts = {
        LAUNCH_RECEIPT_FILENAME: launch_raw,
        EXECUTION_RECEIPT_FILENAME: execution_raw,
        ATTESTATION_FILENAME: attestation_raw,
        **launch_artifact_raws,
        **stage_raws,
    }
    _validate_committed_seal(
        paths, launch, seal_revision, snapshot_reader, tracked,
        consumed_artifacts,
    )
    if _validate_output_tree(paths, execution, launch) != file_map:
        raise SourceConsumerError("V9 output tree changed during seal snapshot")
    eligible = [record for record in records if record["eligible_for_cohort"]]
    return AuthorizedConfirmation(
        campaign=CAMPAIGN,
        benchmark_revision=BENCHMARK_REVISION,
        seal_repository_commit_id=seal_revision,
        source_inventory_sha256=launch["source_inventory_sha256"],
        code_manifest_sha256=launch["code_manifest_sha256"],
        launch_receipt_sha256=hashlib.sha256(launch_raw).hexdigest(),
        execution_receipt_sha256=hashlib.sha256(execution_raw).hexdigest(),
        attestation_sha256=hashlib.sha256(attestation_raw).hexdigest(),
        confirmation_a=tuple(_freeze(record) for record in confirmation),
        guided_b=tuple(_freeze(record) for record in guided),
        eligible_records=tuple(_freeze(record) for record in eligible),
        all_records=tuple(_freeze(record) for record in records),
        outcome_counts=_freeze(attestation["outcome_counts"]),
        resource_exclusions_by_family=_freeze(
            attestation["resource_exclusions_by_family"]
        ),
        tracked_file_sha256=_freeze(dict(sorted(tracked.items()))),
    )


__all__ = [
    "AuthorizedConfirmation", "SourceConsumerError", "V9Paths",
    "load_authorized_confirmation", "paths_for",
]
