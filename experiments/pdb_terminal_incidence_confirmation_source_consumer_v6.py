#!/usr/bin/env python3
"""Fail-closed consumer for the prospective mixed V5/V6 source seal.

V6 is a selective, scheduler-defined repair of terminal V5.  This consumer
binds both producer revisions, the terminal diagnostic, the repair launch and
execution receipts, and every byte in the exact 820-shard mixed union.  It
does not accept any V1--V4 shard or a partial result from a noncompleted V5
array task.
"""

from __future__ import annotations

import hashlib
import re
import stat
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_safe_io_v6 as StreamingTree
import pdb_terminal_incidence_confirmation_source_consumer_v5 as V5
import audit_pdb_terminal_incidence_confirmation_sources_v6 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v6 as Launch


class SourceConsumerError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
SCHEMA = Launch.SCHEMA
ATTESTATION_SCHEMA = Source.Base.SCHEMA
CAMPAIGN = "v6-selective-repair"
ATTESTATION = Launch.ATTESTATION
ARTIFACT_DIR = Launch.ARTIFACT_DIR
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
V5_SOURCE_INVENTORY = Launch.V5_SOURCE_INVENTORY
ARRAY_TASKS = Launch.ARRAY_TASKS
CANDIDATES = Source.CANDIDATE_COUNT
TASKS_PER_SHARD = Source.TASKS_PER_SHARD
SHA256_RE = re.compile(r"[0-9a-f]{64}")
COMMIT_RE = re.compile(r"[0-9a-f]{40,64}")
TOKEN_RE = re.compile(r"[0-9a-f]{24}")
ELAPSED_RE = re.compile(
    r"(?:(?:0|[1-9][0-9]*)-)?([0-9]{2}):[0-5][0-9]:[0-5][0-9]"
)

CODE_MANIFEST_FILES = tuple(Source.CODE_MANIFEST_FILES)
MANIFEST_RELATIVE = CODE_MANIFEST.relative_to(REPO).as_posix()
SCOPED_FILES = tuple(Launch.SCOPED_COMMIT_FILES)

MATERIAL_KEYS = frozenset({
    "campaign", "benchmark_revision", "v5_terminal_diagnostic_sha256",
    "v5_launch_receipt_sha256", "logical_shards", "candidates",
    "reusable_v5_shard_indices", "repair_v5_shard_indices",
    "reused_v1_shards", "reused_v2_shards", "reused_v3_shards",
    "reused_v4_shards", "reused_v5_shards", "repaired_v5_shards",
    "reuse_eligibility_rule", "repair_scope", "whole_campaign_rerun",
    "outcome_blind_selective_repair", "noncompleted_v5_shards_used",
    "array", "array_throttle", "partition", "qos", "account",
    "cpus_per_task", "resource_mapping", "source_inventory_sha256",
    "code_manifest_sha256", "slurm_template_sha256",
    "slurm_program_sha256", "slurm_program_bytes",
    "slurm_submission_mode", "repository_commit_id",
    "scoped_repository_files", "launch_root_identities", "output_dir",
    "tmpdir_root", "source_inventory_path", "candidate_attestation",
    "frozen_attestation", "execution_environment",
})
INTENT_KEYS = MATERIAL_KEYS | frozenset({
    "schema", "recorded_utc", "submission_token", "submit_command",
})
LAUNCH_KEYS = (INTENT_KEYS - {"schema"}) | frozenset({
    "schema", "launch_intent_sha256", "job_id",
})
EXECUTION_KEYS = frozenset({
    "schema", "campaign", "benchmark_revision", "logical_shards", "candidates",
    "whole_campaign_rerun", "outcome_blind_selective_repair",
    "noncompleted_v5_shards_used", "reuse_eligibility_rule",
    "pre_diagnosis_freeze", "seal_recovery_protocol", "seal_plan_sha256",
    "union_root_stage_sha256", "union_stage_sha256",
    "candidate_stage_sha256", "attestation_stage_sha256",
    "launch_receipt_sha256", "v5_terminal_diagnostic_sha256",
    "v5_launch_receipt_sha256", "v5_job_id", "v6_job_id",
    "reused_v1_shards", "reused_v2_shards", "reused_v3_shards",
    "reused_v4_shards", "reused_v5_shards",
    "reusable_v5_shard_indices", "repaired_v5_shards",
    "repair_v5_shard_indices", "repair_scope", "array_throttle",
    "resource_mapping", "scheduler_state_counts", "scheduler_rows",
    "scheduler_contract_rows", "v5_output_manifest", "v6_output_tree",
    "v5_reusable_environment_manifest",
    "v6_repair_environment_manifest", "union_sources",
    "union_sources_sha256", "union_tree", "source_inventory_sha256",
    "v5_code_manifest_sha256", "v6_code_manifest_sha256",
    "execution_environment", "source_audit_complete",
    "confirmation_prelaunch_authorized", "prelaunch_gate",
    "attestation_sha256", "attestation_records_sha256",
    "cohort_manifest_sha256", "counts", "translation_status_counts",
    "support_exclusion_counts",
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


def _valid_elapsed(value) -> bool:
    """Validate raw Slurm elapsed text without trusting producer code."""
    match = ELAPSED_RE.fullmatch(value) if isinstance(value, str) else None
    return match is not None and int(match.group(1)) < 24


def _canonical_json_line(value) -> bytes:
    try:
        import json
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii") + b"\n"
    except (TypeError, ValueError) as err:
        raise SourceConsumerError("value is not canonical finite JSON") from err


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
            path, label=label, expected_path=expected, root=REPO,
        )
    except SafeIO.SafeReadError as err:
        raise SourceConsumerError(str(err)) from err


def _digest(value) -> str:
    return hashlib.sha256(_canonical_json_line(value)).hexdigest()


def _root_identity(value, expected: Path) -> bool:
    return (
        type(value) is dict
        and set(value) == {
            "path", "canonical_path", "uid", "mode", "device", "inode",
        }
        and value.get("path") == str(expected)
        and value.get("canonical_path") == str(expected)
        and value.get("mode") == "0700"
        and all(type(value.get(key)) is int and value[key] >= 0
                for key in ("uid", "device", "inode"))
    )


def _validate_snapshot(
    revision: str, files: tuple[str, ...], tracked: dict[str, str],
    snapshot_reader: SnapshotReader, label: str,
) -> None:
    snapshot = snapshot_reader(revision, list(files))
    if (
        type(snapshot) is not dict
        or set(snapshot) != set(files)
        or any(type(raw) is not bytes for raw in snapshot.values())
        or any(hashlib.sha256(snapshot[path]).hexdigest() != tracked[path]
               for path in files)
    ):
        raise SourceConsumerError("{} producer revision byte chain changed".format(label))


def _validate_v5_producer(
    diagnostic: dict, snapshot_reader: SnapshotReader,
) -> dict[str, str]:
    """Validate terminal V5's launch closure without accepting a V5 seal."""
    try:
        intent_raw, intent = V5._read_json(V5.INTENT, V5.INTENT, "V5 launch intent")
        launch_raw, launch = V5._read_json(
            V5.LAUNCH_RECEIPT, V5.LAUNCH_RECEIPT, "V5 launch receipt"
        )
        V5._validate_launch(intent_raw, intent, launch)
        manifest = V5._manifest(launch)
        if (
            launch.get("launcher_sha256") != manifest.get(
                "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py"
            )
            or launch.get("python_requirements_sha256") != manifest.get(
                "experiments/requirements-pdb-terminal-incidence-shadow.txt"
            )
        ):
            raise SourceConsumerError("V5 launcher/environment byte chain changed")
        V5._validate_diagnostic(launch, manifest)
        slurm_sha = V5._slurm(launch)
    except V5.SourceConsumerError as err:
        raise SourceConsumerError("invalid terminal V5 producer: {}".format(err)) from err
    if (
        diagnostic.get("v5_launch_receipt") != launch
        or diagnostic.get("v5_launch_receipt_sha256")
        != hashlib.sha256(launch_raw).hexdigest()
        or diagnostic.get("v5_launch_intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or diagnostic.get("v5_code_manifest_sha256")
        != launch.get("code_manifest_sha256")
        or diagnostic.get("v5_source_inventory_sha256")
        != launch.get("source_inventory_sha256")
    ):
        raise SourceConsumerError("terminal V5 diagnostic ancestry changed")
    tracked = {
        **manifest,
        V5.SLURM_RELATIVE: slurm_sha,
        V5.MANIFEST_RELATIVE: launch["code_manifest_sha256"],
    }
    _validate_snapshot(
        launch["repository_commit_id"], V5.SCOPED_FILES, tracked,
        snapshot_reader, "V5",
    )
    return tracked


def _manifest(launch: dict, diagnostic: dict) -> tuple[dict[str, str], dict]:
    loaded = _read_file(CODE_MANIFEST, CODE_MANIFEST, "V6 code manifest")
    if (
        SHA256_RE.fullmatch(launch.get("code_manifest_sha256", "")) is None
        or loaded.sha256 != launch.get("code_manifest_sha256")
    ):
        raise SourceConsumerError("V6 code-manifest hash chain changed")
    try:
        lines = loaded.raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise SourceConsumerError("V6 code manifest is not ASCII") from err
    records = {}
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([!-~]+)", line)
        if match is None or match.group(2) in records:
            raise SourceConsumerError("V6 code manifest is malformed")
        records[match.group(2)] = match.group(1)
    if (
        not loaded.raw.endswith(b"\n")
        or tuple(sorted(records)) != CODE_MANIFEST_FILES
    ):
        raise SourceConsumerError("V6 code-manifest file set changed")
    for relative, expected in records.items():
        path = REPO / relative
        if _read_file(path, path, "V6 manifest dependency").sha256 != expected:
            raise SourceConsumerError("V6 manifest dependency changed")
    # V6 deliberately reuses V5's pinned Python environment.  Reconstruct the
    # attestation from the already validated V5 launch rather than consulting
    # the consumer process's ambient Python installation.
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
    raw, diagnostic = _read_json(DIAGNOSTIC, DIAGNOSTIC, "V6 terminal diagnostic")
    try:
        digest, validated = Launch._load_diagnostic()
    except (Launch.LaunchAuditError, Source.SourceAuditError) as err:
        raise SourceConsumerError("invalid V6 terminal diagnostic: {}".format(err)) from err
    if (
        diagnostic != validated
        or hashlib.sha256(raw).hexdigest() != digest
        or set(diagnostic) != set(Launch.DIAGNOSTIC_FIELDS)
    ):
        raise SourceConsumerError("V6 terminal diagnostic byte chain changed")
    return raw, diagnostic


def _validate_launch(
    diagnostic_raw: bytes, diagnostic: dict, intent_raw: bytes,
    intent: dict, launch_raw: bytes, launch: dict,
) -> tuple[dict[str, str], dict]:
    if (
        type(intent) is not dict or set(intent) != INTENT_KEYS
        or type(launch) is not dict or set(launch) != LAUNCH_KEYS
        or intent.get("schema") != Launch.LAUNCH_SCHEMA + "/intent"
        or launch.get("schema") != Launch.LAUNCH_SCHEMA
        or launch != {
            "schema": Launch.LAUNCH_SCHEMA,
            **{key: value for key, value in intent.items() if key != "schema"},
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": launch.get("job_id"),
        }
        or TOKEN_RE.fullmatch(intent.get("submission_token", "")) is None
        or not isinstance(intent.get("recorded_utc"), str)
        or not isinstance(launch.get("job_id"), str)
        or not launch["job_id"].isdigit()
        or COMMIT_RE.fullmatch(launch.get("repository_commit_id", "")) is None
    ):
        raise SourceConsumerError("V6 launch/intent chain changed")
    reusable = diagnostic["reusable_v5_shard_indices"]
    repair = diagnostic["repair_v5_shard_indices"]
    fixed = {
        "campaign": CAMPAIGN,
        "benchmark_revision": Source.Base.Inventory.BENCHMARK_REVISION,
        "v5_terminal_diagnostic_sha256": hashlib.sha256(diagnostic_raw).hexdigest(),
        "v5_launch_receipt_sha256": diagnostic["v5_launch_receipt_sha256"],
        "logical_shards": ARRAY_TASKS, "candidates": CANDIDATES,
        "reusable_v5_shard_indices": reusable,
        "repair_v5_shard_indices": repair,
        "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "reused_v5_shards": len(reusable), "repaired_v5_shards": len(repair),
        "reuse_eligibility_rule": "scheduler state COMPLETED with exit 0:0 only",
        "repair_scope": "complete original two-candidate shards",
        "whole_campaign_rerun": False, "outcome_blind_selective_repair": True,
        "noncompleted_v5_shards_used": False,
        "array": Launch._array_spec(repair), "array_throttle": 0,
        "partition": "fat", "qos": "normal", "account": Launch.ACCOUNT,
        "cpus_per_task": 1, "resource_mapping": diagnostic["resource_mapping"],
        "source_inventory_sha256": diagnostic["v5_source_inventory_sha256"],
        "scoped_repository_files": list(SCOPED_FILES),
        "output_dir": str(OUTPUT_DIR), "tmpdir_root": str(TMP_ROOT),
        "source_inventory_path": str(SOURCE_INVENTORY),
        "candidate_attestation": str(CANDIDATE),
        "frozen_attestation": str(ATTESTATION),
        "slurm_submission_mode": "stdin",
    }
    if (
        any(type(launch.get(key)) is not type(value) or launch.get(key) != value
            for key, value in fixed.items())
        or launch.get("submit_command")
        != Launch._submit_command(diagnostic, launch["submission_token"])
        or not _root_identity(
            launch.get("launch_root_identities", {}).get("output_dir"), OUTPUT_DIR
        )
        or not _root_identity(
            launch.get("launch_root_identities", {}).get("tmpdir_root"), TMP_ROOT
        )
    ):
        raise SourceConsumerError("V6 launch material changed")
    records, code = _manifest(launch, diagnostic)
    try:
        rendered = Launch._render_slurm(
            launch["code_manifest_sha256"],
            diagnostic["resource_mapping"]["task_timeout_seconds"],
        )
    except Launch.LaunchAuditError as err:
        raise SourceConsumerError("V6 Slurm template changed") from err
    template = _read_file(SLURM_TEMPLATE, SLURM_TEMPLATE, "V6 Slurm template")
    if (
        launch.get("slurm_template_sha256") != template.sha256
        or launch.get("slurm_program_sha256")
        != hashlib.sha256(rendered).hexdigest()
        or launch.get("slurm_program_bytes") != len(rendered)
        or launch.get("execution_environment") != Launch._execution_environment(code)
    ):
        raise SourceConsumerError("V6 Slurm/environment chain changed")
    return records, code


def _file_map(tree: dict, label: str) -> dict[str, dict]:
    files = tree.get("files") if isinstance(tree, dict) else None
    if (
        type(tree) is not dict
        or set(tree) != {"sha256", "root_identity", "files_count", "files"}
        or type(files) is not list
        or tree.get("files_count") != len(files)
        or SHA256_RE.fullmatch(tree.get("sha256", "")) is None
    ):
        raise SourceConsumerError("{} tree receipt changed".format(label))
    result = {}
    digest = hashlib.sha256()
    digest.update(b"root-identity\0" + _canonical_json_line(tree["root_identity"]))
    # Producer tree digests use canonical JSON with its trailing newline.
    for record in files:
        if (
            type(record) is not dict
            or set(record) != {"path", "bytes", "sha256"}
            or not isinstance(record.get("path"), str)
            or record["path"] in result
            or type(record.get("bytes")) is not int or record["bytes"] < 0
            or SHA256_RE.fullmatch(record.get("sha256", "")) is None
        ):
            raise SourceConsumerError("{} tree record changed".format(label))
        result[record["path"]] = record
        digest.update(
            record["path"].encode("ascii") + b"\0"
            + bytes.fromhex(record["sha256"])
        )
    if (
        [record["path"] for record in files] != sorted(result)
        or digest.hexdigest() != tree["sha256"]
    ):
        raise SourceConsumerError("{} tree digest changed".format(label))
    return result


def _validate_live_tree(
    receipt: dict, root: Path, expected_paths: list[str], expected_root: dict,
    label: str,
) -> dict[str, dict]:
    records = _file_map(receipt, label)
    if set(records) != set(expected_paths) or receipt["root_identity"] != expected_root:
        raise SourceConsumerError("{} file set changed".format(label))
    try:
        tree = StreamingTree.read_streaming_tree(
            root, label=label, expected_path=root,
        )
    except StreamingTree.SafeTreeError as err:
        raise SourceConsumerError(str(err)) from err
    actual = tree.root_identity
    if (
        tree.directories
        or [item.path for item in tree.files] != sorted(expected_paths)
        or actual.get("device") != expected_root["device"]
        or actual.get("inode") != expected_root["inode"]
        or actual.get("uid") != expected_root["uid"]
        or not stat.S_ISDIR(actual.get("mode", 0))
        or stat.S_IMODE(actual["mode"]) != 0o700
    ):
        raise SourceConsumerError("live {} changed".format(label))
    for item in tree.files:
        record = records[item.path]
        if item.sha256 != record["sha256"] or item.identity["size"] != record["bytes"]:
            raise SourceConsumerError("live {} file changed".format(label))
    return records


def _validate_scheduler(execution: dict, launch: dict, repair: list[int]) -> None:
    rows = execution.get("scheduler_rows")
    contracts = execution.get("scheduler_contract_rows")
    expected_memory = launch["resource_mapping"]["memory"]["requested"]
    expected_name = "{}-{}".format(
        Launch.JOB_NAME_PREFIX, launch["submission_token"]
    )
    if (
        type(rows) is not list or type(contracts) is not list
        or len(rows) != len(repair) or len(contracts) != len(repair)
        or execution.get("scheduler_state_counts") != {"COMPLETED": len(repair)}
    ):
        raise SourceConsumerError("V6 scheduler receipt changed")
    for index, row, contract in zip(repair, rows, contracts):
        if (
            type(row) is not dict
            or set(row) != {"array_task", "state", "exit_code", "elapsed", "partition"}
            or row.get("array_task") != index or row.get("state") != "COMPLETED"
            or row.get("exit_code") != "0:0" or row.get("partition") != "fat"
            or not _valid_elapsed(row.get("elapsed"))
            or type(contract) is not dict
            or set(contract) != {
                "array_task", "account", "partition", "qos", "req_cpus",
                "req_mem", "time_limit", "elapsed", "state", "exit_code",
                "job_name",
            }
            or not _valid_elapsed(contract.get("elapsed"))
            or contract != {
                "array_task": index, "account": Launch.ACCOUNT,
                "partition": "fat", "qos": "normal", "req_cpus": 1,
                "req_mem": expected_memory,
                "time_limit": launch["resource_mapping"]["time_limit"],
                "elapsed": row["elapsed"],
                "state": "COMPLETED", "exit_code": "0:0",
                "job_name": expected_name,
            }
        ):
            raise SourceConsumerError("V6 scheduler/resource row changed")


def _validate_environment_manifests(
    execution: dict, launch: dict, diagnostic: dict,
    v5_files: dict[str, dict], v6_files: dict[str, dict],
) -> None:
    reusable = diagnostic["reusable_v5_shard_indices"]
    repair = diagnostic["repair_v5_shard_indices"]
    v5_manifest = execution.get("v5_reusable_environment_manifest")
    v6_manifest = execution.get("v6_repair_environment_manifest")
    specs = (
        (v5_manifest, reusable, v5_files, V5_OUTPUT_DIR, diagnostic["v5_launch_receipt"], True),
        (v6_manifest, repair, v6_files, OUTPUT_DIR, launch, False),
    )
    for manifest, indices, files, root, owner, is_v5 in specs:
        flag = (
            "strict_completed_triplet_validation" if is_v5
            else "all_repair_tmpdirs_removed_by_rmdir"
        )
        records = manifest.get("records") if isinstance(manifest, dict) else None
        if (
            type(manifest) is not dict or set(manifest) != {"records", "records_sha256", flag}
            or manifest.get(flag) is not True or type(records) is not list
            or len(records) != len(indices) or manifest.get("records_sha256") != _digest(records)
        ):
            raise SourceConsumerError("V6 mixed environment manifest changed")
        for index, record in zip(indices, records):
            shard = "shard-{:04d}-of-0820.json".format(index)
            environment = "environment-{:04d}-of-0820.json".format(index)
            expected_keys = {
                "array_task", "environment_path", "environment_sha256",
                "shard_path", "shard_sha256", "tmpdir", "output_dir_identity",
                "slurm_log_path", "slurm_log_sha256",
            }
            tmpdir = str(
                (V5.TMP_ROOT if is_v5 else TMP_ROOT)
                / "task-{}-{}".format(owner["job_id"], index)
            )
            if (
                type(record) is not dict or set(record) != expected_keys
                or record.get("array_task") != index
                or record.get("environment_path") != environment
                or record.get("environment_sha256") != files[environment]["sha256"]
                or record.get("shard_path") != shard
                or record.get("shard_sha256") != files[shard]["sha256"]
                or record.get("tmpdir") != tmpdir
                or record.get("output_dir_identity")
                != owner["launch_root_identities"]["output_dir"]
            ):
                raise SourceConsumerError("V6 mixed environment record changed")
            log = "slurm-{}_{}.out".format(owner["job_id"], index)
            if (
                record.get("slurm_log_path") != log
                or record.get("slurm_log_sha256") != files[log]["sha256"]
            ):
                raise SourceConsumerError("V6 mixed log ancestry changed")


def _validate_union(
    execution: dict, diagnostic: dict,
    v5_files: dict[str, dict], v6_files: dict[str, dict],
) -> None:
    sources = execution.get("union_sources")
    reusable = set(diagnostic["reusable_v5_shard_indices"])
    if (
        type(sources) is not list or len(sources) != ARRAY_TASKS
        or execution.get("union_sources_sha256") != _digest(sources)
    ):
        raise SourceConsumerError("V6 union source ledger changed")
    expected_union_paths = [
        "shard-{:04d}-of-0820.json".format(index)
        for index in range(ARRAY_TASKS)
    ]
    union_tree = execution.get("union_tree")
    union_root = union_tree.get("root_identity") if isinstance(union_tree, dict) else None
    if not _root_identity(union_root, UNION_DIR):
        raise SourceConsumerError("V6 union root identity changed")
    union_files = _validate_live_tree(
        union_tree, UNION_DIR, expected_union_paths, union_root, "V6 union tree",
    )
    for index, item in enumerate(sources):
        shard = expected_union_paths[index]
        is_v5 = index in reusable
        source_root = V5_OUTPUT_DIR if is_v5 else OUTPUT_DIR
        source_files = v5_files if is_v5 else v6_files
        expected = {
            "shard_index": index,
            "origin": "v5-completed" if is_v5 else "v6-repair",
            "source": str(source_root / shard),
            "source_sha256": source_files[shard]["sha256"],
            "union": shard,
            "union_sha256": union_files[shard]["sha256"],
        }
        if item != expected or item["source_sha256"] != item["union_sha256"]:
            raise SourceConsumerError("V6 union origin/hash invariant changed")


def _validate_seal_stages(
    attestation_raw: bytes, attestation: dict, diagnostic: dict,
    launch_raw: bytes, execution: dict,
) -> None:
    paths = (
        (SEAL_PLAN, "seal_plan_sha256", "V6 seal plan"),
        (UNION_ROOT_STAGE, "union_root_stage_sha256", "V6 union-root stage"),
        (UNION_STAGE, "union_stage_sha256", "V6 union stage"),
        (CANDIDATE_STAGE, "candidate_stage_sha256", "V6 candidate stage"),
        (ATTESTATION_STAGE, "attestation_stage_sha256", "V6 attestation stage"),
    )
    values = {}
    for path, field, label in paths:
        raw, value = _read_json(path, path, label)
        if hashlib.sha256(raw).hexdigest() != execution.get(field):
            raise SourceConsumerError("{} hash chain changed".format(label))
        values[field] = value
    plan = values["seal_plan_sha256"]
    expected_plan = {
        "schema": Launch.SEAL_PLAN_SCHEMA,
        "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
        "v5_terminal_diagnostic_sha256": execution[
            "v5_terminal_diagnostic_sha256"
        ],
        "pre_diagnosis_files_sha256": diagnostic[
            "pre_diagnosis_freeze"
        ]["files_sha256"],
        "scheduler_rows": execution["scheduler_rows"],
        "scheduler_contract_rows": execution["scheduler_contract_rows"],
        "v5_output_tree_sha256": diagnostic["v5_output_manifest"]["sha256"],
        "v6_output_tree": execution["v6_output_tree"],
        "v5_reusable_environment_manifest": execution[
            "v5_reusable_environment_manifest"
        ],
        "v6_repair_environment_manifest": execution[
            "v6_repair_environment_manifest"
        ],
        "source_record_count": CANDIDATES,
        "source_record_sequence_sha256": attestation["records_sha256"],
    }
    if plan != expected_plan:
        raise SourceConsumerError("V6 seal plan changed")
    root_stage = values["union_root_stage_sha256"]
    if root_stage != {
        "schema": Launch.UNION_ROOT_STAGE_SCHEMA,
        "seal_plan_sha256": execution["seal_plan_sha256"],
        "root_identity": execution["union_tree"]["root_identity"],
    }:
        raise SourceConsumerError("V6 union-root stage changed")
    union_stage = values["union_stage_sha256"]
    if union_stage != {
        "schema": Launch.UNION_STAGE_SCHEMA,
        "seal_plan_sha256": execution["seal_plan_sha256"],
        "union_root_stage_sha256": execution["union_root_stage_sha256"],
        "sources": execution["union_sources"],
        "sources_sha256": execution["union_sources_sha256"],
        "tree": execution["union_tree"],
    }:
        raise SourceConsumerError("V6 union stage changed")
    candidate = _read_file(CANDIDATE, CANDIDATE, "V6 candidate attestation")
    candidate_stage = values["candidate_stage_sha256"]
    if (
        candidate.raw != attestation_raw
        or candidate_stage != {
            "schema": Launch.CANDIDATE_STAGE_SCHEMA,
            "union_stage_sha256": execution["union_stage_sha256"],
            "candidate_path": str(CANDIDATE),
            "candidate_bytes": len(candidate.raw),
            "candidate_sha256": candidate.sha256,
            "records_sha256": attestation["records_sha256"],
        }
    ):
        raise SourceConsumerError("V6 candidate stage changed")
    attestation_stage = values["attestation_stage_sha256"]
    if attestation_stage != {
        "schema": Launch.ATTESTATION_STAGE_SCHEMA,
        "candidate_stage_sha256": execution["candidate_stage_sha256"],
        "attestation_path": str(ATTESTATION),
        "attestation_bytes": len(attestation_raw),
        "attestation_sha256": hashlib.sha256(attestation_raw).hexdigest(),
    }:
        raise SourceConsumerError("V6 attestation stage changed")


def _validate_execution(
    attestation_raw: bytes, attestation: dict, diagnostic_raw: bytes,
    diagnostic: dict, launch_raw: bytes, launch: dict, execution: dict,
) -> None:
    reusable = diagnostic["reusable_v5_shard_indices"]
    repair = diagnostic["repair_v5_shard_indices"]
    fixed = {
        "schema": Launch.EXECUTION_SCHEMA, "campaign": CAMPAIGN,
        "benchmark_revision": Source.Base.Inventory.BENCHMARK_REVISION,
        "logical_shards": ARRAY_TASKS, "candidates": CANDIDATES,
        "whole_campaign_rerun": False, "outcome_blind_selective_repair": True,
        "noncompleted_v5_shards_used": False,
        "reuse_eligibility_rule": "scheduler state COMPLETED with exit 0:0 only",
        "pre_diagnosis_freeze": diagnostic["pre_diagnosis_freeze"],
        "seal_recovery_protocol": "deterministic-exclusive-hash-chain-v1",
        "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
        "v5_terminal_diagnostic_sha256": hashlib.sha256(diagnostic_raw).hexdigest(),
        "v5_launch_receipt_sha256": diagnostic["v5_launch_receipt_sha256"],
        "v5_job_id": diagnostic["v5_launch_receipt"]["job_id"],
        "v6_job_id": launch["job_id"],
        "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "reused_v5_shards": len(reusable),
        "reusable_v5_shard_indices": reusable,
        "repaired_v5_shards": len(repair), "repair_v5_shard_indices": repair,
        "repair_scope": "complete original two-candidate shards",
        "array_throttle": 0, "resource_mapping": diagnostic["resource_mapping"],
        "v5_output_manifest": diagnostic["v5_output_manifest"],
        "source_inventory_sha256": launch["source_inventory_sha256"],
        "v5_code_manifest_sha256": diagnostic["v5_code_manifest_sha256"],
        "v6_code_manifest_sha256": launch["code_manifest_sha256"],
        "execution_environment": launch["execution_environment"],
        "source_audit_complete": True,
    }
    if (
        type(execution) is not dict or set(execution) != EXECUTION_KEYS
        or any(type(execution.get(key)) is not type(value) or execution.get(key) != value
               for key, value in fixed.items())
    ):
        raise SourceConsumerError("V6 execution-receipt chain changed")
    if (
        attestation.get("schema") != ATTESTATION_SCHEMA
        or execution.get("attestation_sha256")
        != hashlib.sha256(attestation_raw).hexdigest()
        or attestation.get("source_inventory_sha256") != launch["source_inventory_sha256"]
        or attestation.get("code_manifest_sha256") != launch["code_manifest_sha256"]
        or execution.get("confirmation_prelaunch_authorized") is not True
        or attestation.get("confirmation_prelaunch_authorized") is not True
        or execution.get("prelaunch_gate") != attestation.get("prelaunch_gate")
        or execution.get("prelaunch_gate", {}).get("passed") is not True
        or execution.get("attestation_records_sha256") != attestation.get("records_sha256")
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
        or execution.get("support_exclusion_counts")
        != attestation.get("support_exclusion_counts")
    ):
        raise SourceConsumerError("V6 attestation/cohort provenance changed")
    for field in (
        "seal_plan_sha256", "union_root_stage_sha256", "union_stage_sha256",
        "candidate_stage_sha256", "attestation_stage_sha256",
    ):
        if SHA256_RE.fullmatch(execution.get(field, "")) is None:
            raise SourceConsumerError("V6 seal-stage hash changed")
    _validate_seal_stages(
        attestation_raw, attestation, diagnostic, launch_raw, execution
    )
    _validate_scheduler(execution, launch, repair)

    try:
        current_v5 = Launch._opaque_v5_output_manifest(
            diagnostic["v5_launch_receipt"], reusable, repair
        )
    except Launch.LaunchAuditError as err:
        raise SourceConsumerError("terminal V5 output ancestry changed") from err
    if current_v5 != diagnostic["v5_output_manifest"]:
        raise SourceConsumerError("terminal V5 output bytes changed")
    v5_files = {
        record["path"]: record
        for record in diagnostic["v5_output_manifest"]["files"]
    }
    expected_v6 = [SOURCE_INVENTORY.name]
    for index in repair:
        expected_v6.extend([
            "shard-{:04d}-of-0820.json".format(index),
            "environment-{:04d}-of-0820.json".format(index),
            "slurm-{}_{}.out".format(launch["job_id"], index),
        ])
    v6_files = _validate_live_tree(
        execution.get("v6_output_tree"), OUTPUT_DIR, sorted(expected_v6),
        launch["launch_root_identities"]["output_dir"], "V6 repair output tree",
    )
    if v6_files[SOURCE_INVENTORY.name]["sha256"] != launch["source_inventory_sha256"]:
        raise SourceConsumerError("V6 repair inventory hash changed")
    _validate_environment_manifests(
        execution, launch, diagnostic, v5_files, v6_files
    )
    _validate_union(execution, diagnostic, v5_files, v6_files)


def load_v6_source(
    attestation_path: Path,
    execution_receipt_path: Path,
    launch_receipt_path: Path,
    *,
    snapshot_reader: SnapshotReader,
) -> ValidatedSource:
    attestation_raw, attestation = _read_json(
        attestation_path, ATTESTATION, "V6 source attestation"
    )
    execution_raw, execution = _read_json(
        execution_receipt_path, EXECUTION_RECEIPT, "V6 execution receipt"
    )
    launch_raw, launch = _read_json(
        launch_receipt_path, LAUNCH_RECEIPT, "V6 launch receipt"
    )
    intent_raw, intent = _read_json(INTENT, INTENT, "V6 launch intent")
    diagnostic_raw, diagnostic = _load_diagnostic()
    pre = diagnostic["pre_diagnosis_freeze"]
    pre_tracked = {record["path"]: record["sha256"] for record in pre["files"]}
    if set(pre_tracked) != set(Launch.PRE_DIAGNOSIS_FILES):
        raise SourceConsumerError("V6 pre-diagnosis committed closure changed")
    _validate_snapshot(
        pre["repository_commit_id"], tuple(Launch.PRE_DIAGNOSIS_FILES),
        pre_tracked, snapshot_reader, "V6 pre-diagnosis",
    )
    _validate_v5_producer(diagnostic, snapshot_reader)
    manifest, _code = _validate_launch(
        diagnostic_raw, diagnostic, intent_raw, intent, launch_raw, launch
    )
    inventory_raw, inventory = _read_json(
        SOURCE_INVENTORY, SOURCE_INVENTORY, "V6 source inventory"
    )
    v5_inventory = _read_file(
        V5_SOURCE_INVENTORY, V5_SOURCE_INVENTORY, "terminal V5 source inventory"
    )
    inventory_sha = hashlib.sha256(inventory_raw).hexdigest()
    if (
        inventory_sha != launch.get("source_inventory_sha256")
        or v5_inventory.sha256 != inventory_sha
        or v5_inventory.raw != inventory_raw
        or attestation.get("source_inventory_sha256") != inventory_sha
    ):
        raise SourceConsumerError("V5/V6 inventory ancestry changed")
    _validate_execution(
        attestation_raw, attestation, diagnostic_raw, diagnostic,
        launch_raw, launch, execution,
    )
    tracked = {**manifest, MANIFEST_RELATIVE: launch["code_manifest_sha256"]}
    if set(tracked) != set(SCOPED_FILES):
        raise SourceConsumerError("V6 scoped producer closure changed")
    _validate_snapshot(
        launch["repository_commit_id"], SCOPED_FILES, tracked,
        snapshot_reader, "V6",
    )
    return ValidatedSource(
        attestation_path=ATTESTATION,
        diagnostic_path=DIAGNOSTIC,
        intent_path=INTENT,
        execution_receipt_path=EXECUTION_RECEIPT,
        launch_receipt_path=LAUNCH_RECEIPT,
        attestation_raw=attestation_raw,
        diagnostic_raw=diagnostic_raw,
        intent_raw=intent_raw,
        execution_raw=execution_raw,
        launch_raw=launch_raw,
        inventory_raw=inventory_raw,
        attestation=attestation,
        diagnostic=diagnostic,
        intent=intent,
        execution=execution,
        launch=launch,
        inventory=inventory,
        tracked_file_sha256=dict(sorted(tracked.items())),
    )
