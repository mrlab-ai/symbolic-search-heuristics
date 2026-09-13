#!/usr/bin/env python3
"""Focused adversarial tests for the independent V11 source consumer."""

from __future__ import annotations

import base64
import copy
import datetime
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
from unittest import mock

import pdb_terminal_incidence_confirmation_source_consumer_v11 as C


ZERO = "0" * 64
SOURCE = "1" * 40
PREFLIGHT_SEAL = "2" * 40
FULL_SEAL = "3" * 40
JOB = "12345"
TOKEN = "a" * 24


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def put(path: Path, raw: bytes) -> None:
    path.write_bytes(raw)
    path.chmod(0o400)


def root_record(path: Path, inode: int) -> dict:
    return {
        "path": str(path), "canonical_path": str(path),
        "device": 1, "inode": inode, "mode": "0700",
        "uid": os.getuid(), "gid": os.getgid(),
    }


def capture_identity(path: Path, *, initial: bool) -> dict:
    info = path.lstat()
    value = {
        "path": str(path), "canonical_path": str(path),
        "device": info.st_dev, "inode": info.st_ino, "mode": "0400",
        "uid": info.st_uid, "gid": info.st_gid, "link_count": 1,
    }
    value["bytes_at_intent" if initial else "bytes"] = (
        0 if initial else info.st_size
    )
    return value


def capture_record(path: Path, raw: bytes, initial: dict) -> dict:
    return {
        "path": str(path), "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "initial_identity": initial,
        "final_identity": capture_identity(path, initial=False),
    }


def recorded_identity(inode: int, size: int, mode: int = 0o400) -> dict:
    return {
        "device": 1, "inode": inode, "mode": mode,
        "uid": os.getuid(), "size": size,
    }


def candidate_stream(raw: bytes, name: str) -> dict:
    tail = raw[-C.STREAM_TAIL_BYTES:]
    return {
        "total_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "retained_path": name, "retained_bytes": len(raw),
        "retained_sha256": hashlib.sha256(raw).hexdigest(),
        "retention_limit_bytes": C.STREAM_PREFIX_BYTES, "truncated": False,
        "tail_base64": base64.b64encode(tail).decode("ascii"),
        "tail_bytes": len(tail),
    }


def candidate_fixture(index: int = 0, *, origin: str = "v11-fresh"):
    domain_hash = hashlib.sha256(b"domain").hexdigest()
    problem_hash = hashlib.sha256("problem-{}".format(index).encode()).hexdigest()
    problem = "problem-{}.pddl".format(index)
    inventory = {
        "candidate_index": index, "directory": "fixture",
        "family": "fixture", "problem": problem,
        "domain_file": "fixture/domain.pddl",
        "problem_file": "fixture/" + problem,
        "domain_sha256": domain_hash, "problem_sha256": problem_hash,
        "canonical_path": "fixture/" + problem,
        "is_shadow_family": False, "is_shadow_unrepresented": True,
        "is_all_prior_represented": False,
        "is_all_prior_unrepresented": True,
        "aliases": [],
    }
    stdout = b"translated\n"
    stderr = b""
    snapshot_files = []
    for position, (role, key, hash_key, name, size) in enumerate((
        ("domain", "domain_file", "domain_sha256", "domain.pddl", 6),
        ("problem", "problem_file", "problem_sha256", "problem.pddl", 7),
    )):
        snapshot = recorded_identity(20 + position, size)
        snapshot_files.append({
            "role": role, "source_file": inventory[key],
            "source_identity": recorded_identity(10 + position, size, 0o644),
            "snapshot_name": name, "snapshot_identity_before": snapshot,
            "snapshot_identity_after": dict(snapshot), "bytes": size,
            "sha256": inventory[hash_key],
        })
    sas = {
        "sas_version": 3, "metric": 1, "num_variables": 2,
        "num_mutex_groups": 0, "num_operators": 1, "num_effects": 1,
        "num_conditional_effects": 0, "num_zero_cost_operators": 0,
        "min_operator_cost": 1, "max_operator_cost": 1,
        "num_serialized_axioms": 0,
    }
    child = {
        "schema": C.SCHEMA + "/child-limit-evidence/v1", "pid": 123,
        "process_group": 123,
        "rlimit_as": [C.ADDRESS_SPACE_BYTES, C.ADDRESS_SPACE_BYTES],
        "rlimit_cpu": [C.CPU_SOFT_SECONDS, C.CPU_HARD_SECONDS],
        "no_new_privs": 1, "seccomp_mode": 2, "seccomp_filters": 1,
        "threads": 1,
    }
    task = {
        **inventory, "schema": C.CANDIDATE_SCHEMA,
        "logical_shard_index": index // 2, "position_in_shard": index % 2,
        "candidate_origin": origin, "translation_attempted": True,
        "translator_command": [
            "PINNED_PYTHON", "-B",
            "experiments/pdb_terminal_incidence_confirmation_translate_v11.py",
            "--", inventory["domain_file"], inventory["problem_file"],
        ],
        "code_manifest_sha256": ZERO, "repository_commit_id": SOURCE,
        "resource_contract": C._candidate_resource_contract(),
        "resource_contract_sha256": C._digest(C._candidate_resource_contract()),
        "child_limit_attestation": child,
        "parent_prlimit_observation": {
            "tool_sha256": C.PRLIMIT_SHA256,
            "command": [
                "/usr/bin/prlimit", "--pid", "CHILD_PID", "--as", "--cpu",
                "--output=RESOURCE,SOFT,HARD,UNITS", "--noheadings", "--raw",
            ],
            "stdout_sha256": C.PRLIMIT_STDOUT_SHA256,
            "rlimit_as": [C.ADDRESS_SPACE_BYTES, C.ADDRESS_SPACE_BYTES],
            "rlimit_cpu": [C.CPU_SOFT_SECONDS, C.CPU_HARD_SECONDS],
        },
        "parent_isolation_observation": {
            "status_sha256": "9" * 64, "process_group": 123,
            "no_new_privs": 1, "seccomp_mode": 2, "seccomp_filters": 1,
            "threads": 1,
            "process_creation_syscalls_denied": list(C.DENIED_PROCESS_SYSCALLS),
            "libseccomp_sha256": C.LIBSECCOMP_SHA256,
        },
        "process_returncode": 0, "complete_process_group_reaped": True,
        "stdout": candidate_stream(
            stdout, "candidate-{:04d}.stdout.prefix".format(index),
        ),
        "stderr": candidate_stream(
            stderr, "candidate-{:04d}.stderr.prefix".format(index),
        ),
        "normalization": {
            "schema": C.SCHEMA + "/normalization-evidence/v1",
            "num_normalized_axioms": 0, "strategy": "axiom_based",
        },
        "sas": sas, "sas_bytes": 100, "sas_sha256": "8" * 64,
        "partial_sas_evidence": None, "status": "success",
        "resource_exclusion_kind": None, "support_determined": True,
        "supported": True, "support_exclusion_reasons": [],
        "eligible_for_cohort": True,
        "source_snapshot": {
            "schema": C.SOURCE_SNAPSHOT_SCHEMA, "files": snapshot_files,
            "candidate_private_working_directory": True,
            "source_hashes_verified_before_use": True,
            "identity_and_sha256_verified_after_use": True,
            "exact_snapshot_files_removed": True,
        },
    }
    return inventory, task, {"stdout": stdout, "stderr": stderr}


def slurm_record(path: Path) -> dict:
    return {
        "template_path": str(path), "template_sha256": "4" * 64,
        "rendered_sha256": "5" * 64, "rendered_bytes": 1234,
        "submission_mode": "stdin", "path_argument": False,
    }


def compute_launch_bundle(root: Path):
    artifact = root / "preflight"
    artifact.mkdir(mode=0o700)
    paths = C.preflight_paths_for(
        artifact, code_manifest=root / "code.sha256",
        controller_output_root=root / "publisher",
        compute_output_root=root / "compute",
    )
    stdout = (JOB + "\n").encode("ascii")
    stderr = b""
    put(paths.compute_sbatch_stdout, stdout)
    put(paths.compute_sbatch_stderr, stderr)
    stdout_initial = capture_identity(paths.compute_sbatch_stdout, initial=True)
    stderr_initial = capture_identity(paths.compute_sbatch_stderr, initial=True)
    roots = {
        "artifact_dir": root_record(paths.artifact_dir, 1),
        "output_dir": root_record(paths.compute_output_root, 2),
        "tmpdir_root": root_record(C.COMPUTE_CANARY_TMP_ROOT, 3),
        "log_root": root_record(C.COMPUTE_CANARY_LOG_ROOT, 4),
    }
    command = C._submit_command(TOKEN, canary=True)
    intent = {
        "schema": C.COMPUTE_LAUNCH_INTENT_SCHEMA,
        "campaign": "v11-compute-canary",
        "recorded_utc": "2026-01-01T00:00:00+00:00",
        "submission_token": TOKEN, "repository_commit_id": SOURCE,
        "code_manifest_sha256": ZERO,
        "controller_publisher_canary_receipt_sha256": "6" * 64,
        "resource_profile": C._resource_profile("0-0"),
        "root_identities": roots,
        "slurm_program": slurm_record(C.COMPUTE_CANARY_SLURM_PROGRAM),
        "capture_protocol": C.CAPTURE_PROTOCOL,
        "sbatch_capture_initial_identities": {
            "stdout": stdout_initial, "stderr": stderr_initial,
        },
        "submit_command": command,
        "prior_runtime_payloads_read": 0,
        "prior_runtime_payload_bytes_read": 0,
        "prior_runtime_payloads_reused": 0,
    }
    intent_raw = canonical(intent)
    result = {
        "schema": C.COMPUTE_SBATCH_RESULT_SCHEMA,
        "campaign": "v11-compute-canary",
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "submit_command_sha256": C._digest(command),
        "slurm_program_sha256": intent["slurm_program"]["rendered_sha256"],
        "process_returncode": 0,
        "stdout": capture_record(
            paths.compute_sbatch_stdout, stdout, stdout_initial,
        ),
        "stderr": capture_record(
            paths.compute_sbatch_stderr, stderr, stderr_initial,
        ),
        "parsed_job_id": JOB, "accepted_by_launcher": True,
        "raw_streams_preserved": True,
    }
    result_raw = canonical(result)
    receipt = {
        "schema": C.COMPUTE_LAUNCH_SCHEMA,
        "campaign": "v11-compute-canary", "job_id": JOB,
        "accepted_utc": "2026-01-01T00:00:01+00:00",
        "submission_token": TOKEN, "repository_commit_id": SOURCE,
        "code_manifest_sha256": ZERO,
        "controller_publisher_canary_receipt_sha256": "6" * 64,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "sbatch_result_sha256": hashlib.sha256(result_raw).hexdigest(),
        "resource_profile": intent["resource_profile"],
        "root_identities": roots, "slurm_program": intent["slurm_program"],
        "launch_recovered": False, "recovery_evidence": None,
    }
    raws = {
        "compute-canary-launch-intent-v11.json": intent_raw,
        "compute-canary-sbatch-result-v11.json": result_raw,
        "compute-canary-launch-receipt-v11.json": canonical(receipt),
        "compute-canary-sbatch-stdout-v11.bin": stdout,
        "compute-canary-sbatch-stderr-v11.bin": stderr,
    }
    return paths, raws


def full_launch_bundle(root: Path):
    artifact = root / "artifacts"
    artifact.mkdir(mode=0o700)
    data = root / "data"
    paths = C.paths_for(
        artifact, data, code_manifest=root / "code.sha256",
    )
    stdout = (JOB + "\n").encode("ascii")
    stderr = b""
    put(paths.sbatch_stdout, stdout)
    put(paths.sbatch_stderr, stderr)
    stdout_initial = capture_identity(paths.sbatch_stdout, initial=True)
    stderr_initial = capture_identity(paths.sbatch_stderr, initial=True)
    roots = {
        "artifact_dir": root_record(paths.artifact_dir, 1),
        "log_root": root_record(C.FULL_LOG_ROOT, 2),
        "output_dir": root_record(paths.data_root, 3),
        "tmpdir_root": root_record(C.FULL_TMP_ROOT, 4),
    }
    command = C._submit_command(TOKEN, canary=False)
    files = [{"path": "experiments/example.py", "sha256": "7" * 64}]
    preflight = {"opaque": "validated separately"}
    intent = {
        "schema": C.LAUNCH_SCHEMA + "/intent", "campaign": C.CAMPAIGN,
        "recorded_utc": "2026-01-01T00:00:00+00:00",
        "submission_token": TOKEN, "repository_commit_id": PREFLIGHT_SEAL,
        "resource_profile": C._resource_profile("0-819"),
        "array_mapping": {
            "logical_shards": C.SHARD_COUNT,
            "candidate_count": C.CANDIDATE_COUNT,
            "rule": "array element s owns candidates 2s and 2s+1",
            "candidate_index_first": 0,
            "candidate_index_last": C.CANDIDATE_COUNT - 1,
            "candidate_pairs_sha256": C._digest([
                [2 * shard, 2 * shard + 1]
                for shard in range(C.SHARD_COUNT)
            ]),
            "independent_of_prior_scheduler_rows": True,
        },
        "source_inventory": {
            "path": str(data / "source-inventory-v11.json"),
            "sha256": ZERO, "candidate_count": C.CANDIDATE_COUNT,
        },
        "source_inventory_sha256": ZERO,
        "code_manifest": {
            "path": str(paths.code_manifest), "sha256": "8" * 64,
            "files": files, "files_sha256": C._digest(files),
        },
        "code_manifest_sha256": "8" * 64,
        "slurm_program": slurm_record(C.FULL_SLURM_PROGRAM),
        "root_identities": roots,
        "execution_environment": C._execution_environment(),
        "capture_protocol": C.CAPTURE_PROTOCOL,
        "sbatch_capture_initial_identities": {
            "stdout": stdout_initial, "stderr": stderr_initial,
        },
        "submit_command": command, "preflight_binding": preflight,
        "prior_runtime_payloads_read": 0,
        "prior_runtime_payload_bytes_read": 0,
        "prior_runtime_payloads_reused": 0,
        "selective_recovery_authorized": False,
        "whole_campaign_fresh": True,
    }
    intent_raw = canonical(intent)
    result = {
        "schema": C.SBATCH_RESULT_SCHEMA,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "submit_command_sha256": C._digest(command),
        "slurm_program_sha256": intent["slurm_program"]["rendered_sha256"],
        "capture_protocol": C.CAPTURE_PROTOCOL,
        "process_observation": {
            "kind": "completed-process", "returncode": 0,
            "os_error_type": None, "os_error_errno": None,
        },
        "stdout": capture_record(paths.sbatch_stdout, stdout, stdout_initial),
        "stderr": capture_record(paths.sbatch_stderr, stderr, stderr_initial),
        "parsed_job_id": JOB, "accepted_by_launcher": True,
        "raw_streams_preserved": True,
    }
    result_raw = canonical(result)
    receipt = {
        "schema": C.LAUNCH_SCHEMA, "campaign": C.CAMPAIGN,
        "job_id": JOB, "submission_token": TOKEN,
        "accepted_utc": "2026-01-01T00:00:01+00:00",
        "repository_commit_id": PREFLIGHT_SEAL,
        "source_inventory_sha256": ZERO,
        "code_manifest_sha256": "8" * 64,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "sbatch_result_sha256": hashlib.sha256(result_raw).hexdigest(),
        "resource_profile": intent["resource_profile"],
        "root_identities": roots, "slurm_program": intent["slurm_program"],
        "preflight_authorization": preflight,
        "launch_recovered": False, "recovery_evidence": None,
        "prior_runtime_payloads_read": 0,
        "prior_runtime_payload_bytes_read": 0,
        "prior_runtime_payloads_reused": 0,
        "selective_recovery_authorized": False,
        "whole_campaign_fresh": True,
    }
    raws = {
        "source-audit-launch-intent-v11.json": intent_raw,
        "source-audit-sbatch-result-v11.json": result_raw,
        "source-audit-launch-receipt-v11.json": canonical(receipt),
        "source-audit-sbatch-stdout-v11.bin": stdout,
        "source-audit-sbatch-stderr-v11.bin": stderr,
    }
    return paths, raws


def scheduler_rows(
    state: str = "COMPLETED", *, bare: bool = False,
) -> tuple[list[dict], list[dict], bytes]:
    exit_code = "0:0"
    name = "pdb-source-v11-" + TOKEN
    raw_id = JOB if bare else JOB + "_0"
    raw = (
        "{}|naiss2025-5-561-cpu|fat|normal|1|26G|01:10:00|{}|{}|0|{}\n"
        .format(raw_id, state, exit_code, name)
    ).encode("ascii")
    rows = [{
        "array_task": 0, "state": state, "exit_code": exit_code,
        "partition": "fat", "restarts": 0,
    }]
    contracts = [{
        "array_task": 0, "account": "naiss2025-5-561-cpu",
        "partition": "fat", "qos": "normal", "req_cpus": 1,
        "req_mem": "26G", "time_limit": "01:10:00", "state": state,
        "exit_code": exit_code, "restarts": 0, "job_name": name,
    }]
    return rows, contracts, raw


def normal_poll(
    directory: Path, index: int, *, previous: str | None,
    anchor: datetime.datetime, state: str = "COMPLETED",
    bare: bool = False,
) -> str:
    recorded = anchor + datetime.timedelta(hours=1)
    command = [
        "/usr/bin/sacct", "-j", JOB, "-X", "--array", "-n", "-P",
        "--format=JobIDRaw,Account,Partition,QOS,ReqCPUS,ReqMem,Timelimit,State,ExitCode,Restarts,JobName",
    ]
    stem = "poll-{:04d}-".format(index)
    rows, contracts, stdout = scheduler_rows(state, bare=bare)
    stderr = b""
    stdout_path = directory / (stem + "stdout.bin")
    stderr_path = directory / (stem + "stderr.bin")
    put(stdout_path, stdout)
    put(stderr_path, stderr)
    stdout_initial = capture_identity(stdout_path, initial=True)
    stderr_initial = capture_identity(stderr_path, initial=True)
    intent = {
        "schema": C.FULL_POLL_SCHEMA + "/intent", "campaign": C.CAMPAIGN,
        "poll_index": index, "job_id": JOB,
        "recorded_utc": recorded.isoformat(timespec="seconds"),
        "not_before_utc": recorded.isoformat(timespec="seconds"),
        "previous_poll_receipt_sha256": previous,
        "launch_receipt_sha256": ZERO, "command": command,
        "capture_initial_identities": {
            "stdout": stdout_initial, "stderr": stderr_initial,
        },
    }
    intent_raw = canonical(intent)
    result = {
        "schema": C.FULL_POLL_SCHEMA + "/result", "campaign": C.CAMPAIGN,
        "poll_index": index, "intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "command_sha256": C._digest(command), "process_returncode": 0,
        "stdout": capture_record(stdout_path, stdout, stdout_initial),
        "stderr": capture_record(stderr_path, stderr, stderr_initial),
        "single_scheduler_query": True,
    }
    result_raw = canonical(result)
    receipt = {
        "schema": C.FULL_POLL_SCHEMA + "/receipt", "campaign": C.CAMPAIGN,
        "poll_index": index, "job_id": JOB,
        "recorded_utc": intent["recorded_utc"],
        "not_before_utc": intent["not_before_utc"],
        "previous_poll_receipt_sha256": previous,
        "intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "result_sha256": hashlib.sha256(result_raw).hexdigest(),
        "scheduler_rows": rows, "scheduler_contract_rows": contracts,
        "state_counts": {state: 1},
        "all_terminal": state in C.TERMINAL_STATES,
        "all_success": state == "COMPLETED",
    }
    for suffix, raw in (
        ("intent.json", intent_raw), ("result.json", result_raw),
        ("receipt.json", canonical(receipt)),
    ):
        put(directory / (stem + suffix), raw)
    return hashlib.sha256(canonical(receipt)).hexdigest()


def abandoned_poll(
    directory: Path, index: int, *, previous: str | None,
    anchor: datetime.datetime, with_result: bool,
) -> str:
    recorded = anchor + datetime.timedelta(hours=1)
    stem = "poll-{:04d}-".format(index)
    stdout_path = directory / (stem + "stdout.bin")
    stderr_path = directory / (stem + "stderr.bin")
    put(stdout_path, b"")
    put(stderr_path, b"")
    stdout_initial = capture_identity(stdout_path, initial=True)
    stderr_initial = capture_identity(stderr_path, initial=True)
    command = [
        "/usr/bin/sacct", "-j", JOB, "-X", "--array", "-n", "-P",
        "--format=JobIDRaw,Account,Partition,QOS,ReqCPUS,ReqMem,Timelimit,State,ExitCode,Restarts,JobName",
    ]
    intent = {
        "schema": C.FULL_POLL_SCHEMA + "/intent", "campaign": C.CAMPAIGN,
        "poll_index": index, "job_id": JOB,
        "recorded_utc": recorded.isoformat(timespec="seconds"),
        "not_before_utc": recorded.isoformat(timespec="seconds"),
        "previous_poll_receipt_sha256": previous,
        "launch_receipt_sha256": ZERO, "command": command,
        "capture_initial_identities": {
            "stdout": stdout_initial, "stderr": stderr_initial,
        },
    }
    intent_raw = canonical(intent)
    put(directory / (stem + "intent.json"), intent_raw)
    durable = {
        stem + "intent.json": hashlib.sha256(intent_raw).hexdigest(),
        stem + "stdout.bin": hashlib.sha256(b"").hexdigest(),
        stem + "stderr.bin": hashlib.sha256(b"").hexdigest(),
    }
    if with_result:
        result = {
            "schema": C.FULL_POLL_SCHEMA + "/result", "campaign": C.CAMPAIGN,
            "poll_index": index,
            "intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "command_sha256": C._digest(command), "process_returncode": 1,
            "stdout": capture_record(stdout_path, b"", stdout_initial),
            "stderr": capture_record(stderr_path, b"", stderr_initial),
            "single_scheduler_query": True,
        }
        result_raw = canonical(result)
        put(directory / (stem + "result.json"), result_raw)
        durable[stem + "result.json"] = hashlib.sha256(result_raw).hexdigest()
    abandoned = {
        "schema": C.FULL_POLL_SCHEMA + "/abandoned", "campaign": C.CAMPAIGN,
        "poll_index": index, "job_id": JOB,
        "recorded_utc": (recorded + datetime.timedelta(hours=1)).isoformat(
            timespec="seconds",
        ),
        "successor_not_before_utc": (
            recorded + datetime.timedelta(hours=1)
        ).isoformat(timespec="seconds"),
        "intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "durable_files": durable, "outcome": "abandoned-unknown",
        "authorizing": False, "scheduler_queries_during_recovery": 0,
    }
    raw = canonical(abandoned)
    put(directory / (stem + "abandoned.json"), raw)
    return hashlib.sha256(raw).hexdigest()


class ContractTests(unittest.TestCase):
    def test_compute_launch_chain_binds_intent_result_streams_and_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths, raws = compute_launch_bundle(Path(temporary))
            _intent, result, receipt = C._validate_compute_launch_evidence(
                paths, raws,
            )
            self.assertTrue(result["accepted_by_launcher"])
            self.assertEqual(receipt["job_id"], JOB)

            mutations = (
                ("compute-canary-launch-intent-v11.json", "schema", "wrong"),
                ("compute-canary-sbatch-result-v11.json", "process_returncode", 1),
                ("compute-canary-launch-receipt-v11.json", "sbatch_result_sha256", ZERO),
                ("compute-canary-launch-receipt-v11.json", "extra", True),
            )
            for filename, key, replacement in mutations:
                with self.subTest(filename=filename, key=key):
                    changed = dict(raws)
                    value = json.loads(changed[filename])
                    value[key] = replacement
                    changed[filename] = canonical(value)
                    with self.assertRaises(C.SourceConsumerError):
                        C._validate_compute_launch_evidence(paths, changed)

            changed = dict(raws)
            changed["compute-canary-sbatch-stdout-v11.bin"] = b"999\n"
            with self.assertRaises(C.SourceConsumerError):
                C._validate_compute_launch_evidence(paths, changed)

    def test_compute_launch_rejects_byte_identical_capture_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths, raws = compute_launch_bundle(Path(temporary))
            original = paths.compute_sbatch_stdout.read_bytes()
            paths.compute_sbatch_stdout.chmod(0o600)
            paths.compute_sbatch_stdout.unlink()
            put(paths.compute_sbatch_stdout, original)
            with self.assertRaisesRegex(
                C.SourceConsumerError, "capture identity",
            ):
                C._validate_compute_launch_evidence(paths, raws)

    def test_full_launch_chain_binds_intent_result_streams_and_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths, raws = full_launch_bundle(Path(temporary))
            intent, result, receipt = C._validate_full_launch_evidence(
                paths, raws,
            )
            self.assertEqual(intent["resource_profile"]["array_throttle"], None)
            self.assertTrue(result["accepted_by_launcher"])
            self.assertEqual(receipt["job_id"], JOB)

            mutations = (
                ("source-audit-launch-intent-v11.json", "schema", "wrong"),
                ("source-audit-sbatch-result-v11.json", "accepted_by_launcher", False),
                ("source-audit-launch-receipt-v11.json", "launch_intent_sha256", ZERO),
                ("source-audit-launch-receipt-v11.json", "sbatch_result_sha256", ZERO),
                ("source-audit-launch-receipt-v11.json", "extra", True),
            )
            for filename, key, replacement in mutations:
                with self.subTest(filename=filename, key=key):
                    changed = dict(raws)
                    value = json.loads(changed[filename])
                    value[key] = replacement
                    changed[filename] = canonical(value)
                    with self.assertRaises(C.SourceConsumerError):
                        C._validate_full_launch_evidence(paths, changed)

            changed = dict(raws)
            changed["source-audit-sbatch-result-v11.json"] = b"not JSON"
            with self.assertRaises(C.SourceConsumerError):
                C._validate_full_launch_evidence(paths, changed)

    def test_full_launch_rejects_throttle_and_false_recovery_story(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths, raws = full_launch_bundle(Path(temporary))
            intent = json.loads(raws["source-audit-launch-intent-v11.json"])
            intent["resource_profile"]["array_throttle"] = 10
            changed = dict(raws)
            changed["source-audit-launch-intent-v11.json"] = canonical(intent)
            with self.assertRaises(C.SourceConsumerError):
                C._validate_full_launch_evidence(paths, changed)

            receipt = json.loads(raws["source-audit-launch-receipt-v11.json"])
            receipt["launch_recovered"] = True
            changed = dict(raws)
            changed["source-audit-launch-receipt-v11.json"] = canonical(receipt)
            with self.assertRaises(C.SourceConsumerError):
                C._validate_full_launch_evidence(paths, changed)

    def test_rendered_slurm_hash_is_reconstructed_from_sealed_template(self):
        raw = C.COMPUTE_CANARY_SLURM_PROGRAM.read_bytes()
        rendered = raw.replace(
            b"__V11_CODE_MANIFEST_SHA256__", ZERO.encode("ascii"),
        ).replace(
            b"__V11_REPOSITORY_COMMIT_ID__", SOURCE.encode("ascii"),
        )
        intent = {
            "code_manifest_sha256": ZERO,
            "repository_commit_id": SOURCE,
            "slurm_program": {
                "template_sha256": hashlib.sha256(raw).hexdigest(),
                "rendered_sha256": hashlib.sha256(rendered).hexdigest(),
                "rendered_bytes": len(rendered),
            },
        }
        sealed = {C._relative(C.COMPUTE_CANARY_SLURM_PROGRAM): raw}
        C._validate_rendered_slurm(
            intent, sealed, template=C.COMPUTE_CANARY_SLURM_PROGRAM,
            inventory_sha256=None,
        )
        intent["slurm_program"]["rendered_sha256"] = ZERO
        with self.assertRaises(C.SourceConsumerError):
            C._validate_rendered_slurm(
                intent, sealed, template=C.COMPUTE_CANARY_SLURM_PROGRAM,
                inventory_sha256=None,
            )

    def test_paths_and_exact_full_tree_cardinality(self):
        paths = C.paths_for(Path("/a"), Path("/d"))
        self.assertEqual(paths.poll_dir.name, "source-audit-scheduler-polls-v11")
        self.assertEqual(
            paths.terminal_receipt.name,
            "source-audit-scheduler-terminal-receipt-v11.json",
        )
        names = ["source-inventory-v11.json"]
        for index in range(C.SHARD_COUNT):
            self.assertEqual(len(C._expected_shard_names(index)), 8)
            names.extend(
                C.shard_name(index) + "/" + name
                for name in C._expected_shard_names(index)
            )
        self.assertEqual(len(names), 6561)
        self.assertEqual(C.FULL_TREE_FILE_COUNT, 6561)
        self.assertEqual(C.PRIOR_CAMPAIGNS, ["v{}".format(i) for i in range(1, 11)])
        self.assertEqual(
            C.COMPUTE_TERMINAL_RECEIPT_SCHEMA,
            C.SCHEMA + "/preflight/v1/compute-canary-terminal/v1",
        )
        self.assertEqual(
            C.FULL_TERMINAL_RECEIPT_SCHEMA,
            C.SCHEMA + "/execution/v1/terminal/v1",
        )
        self.assertEqual(
            C.PREFLIGHT_AUTHORIZATION_SCHEMA,
            C.SCHEMA + "/preflight/v1/authorization/v1",
        )

    def test_terminal_gate_is_exact_and_fail_closed(self):
        value = {
            "schema": C.FULL_TERMINAL_RECEIPT_SCHEMA,
            "campaign": C.CAMPAIGN, "job_id": JOB, "all_success": True,
            "state_counts": {"COMPLETED": 820},
            "terminal_poll_receipt_sha256": ZERO,
        }
        C._terminal_gate(
            value, schema=C.FULL_TERMINAL_RECEIPT_SCHEMA,
            campaign=C.CAMPAIGN, completed=820, last_poll_sha=ZERO,
            expected_job_id=JOB,
        )
        for mutation in (
            {**value, "all_success": False},
            {**value, "extra": True},
            {**value, "state_counts": {"FAILED": 820}},
            {**value, "job_id": "999"},
        ):
            with self.assertRaises(C.SourceConsumerError):
                C._terminal_gate(
                    mutation, schema=C.FULL_TERMINAL_RECEIPT_SCHEMA,
                    campaign=C.CAMPAIGN, completed=820, last_poll_sha=ZERO,
                    expected_job_id=JOB,
                )

    def test_poll_is_derived_from_retained_one_call_stdout(self):
        launch = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            expected = normal_poll(directory, 0, previous=None, anchor=launch)
            _raws, digest, final = C._poll_bundle(
                directory, campaign=C.CAMPAIGN,
                poll_schema=C.FULL_POLL_SCHEMA, expected_tasks=1,
                launch_receipt_sha256=ZERO,
                launch_recorded_utc=launch.isoformat(), expected_job_id=JOB,
                expected_job_name="pdb-source-v11-" + TOKEN,
            )
            self.assertEqual(digest, expected)
            self.assertTrue(final["all_success"])
            receipt_path = directory / "poll-0000-receipt.json"
            receipt = json.loads(receipt_path.read_text())
            receipt["scheduler_rows"][0]["state"] = "FAILED"
            receipt_path.chmod(0o600)
            put(receipt_path, canonical(receipt))
            with self.assertRaises(C.SourceConsumerError):
                C._poll_bundle(
                    directory, campaign=C.CAMPAIGN,
                    poll_schema=C.FULL_POLL_SCHEMA, expected_tasks=1,
                    launch_receipt_sha256=ZERO,
                    launch_recorded_utc=launch.isoformat(), expected_job_id=JOB,
                    expected_job_name="pdb-source-v11-" + TOKEN,
                )

    def test_bare_job_id_is_only_valid_for_single_element_array(self):
        launch = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            expected = normal_poll(
                directory, 0, previous=None, anchor=launch, bare=True,
            )
            _raws, digest, final = C._poll_bundle(
                directory, campaign=C.CAMPAIGN,
                poll_schema=C.FULL_POLL_SCHEMA, expected_tasks=1,
                launch_receipt_sha256=ZERO,
                launch_recorded_utc=launch.isoformat(),
                expected_job_id=JOB,
                expected_job_name="pdb-source-v11-" + TOKEN,
            )
            self.assertEqual(digest, expected)
            self.assertEqual(final["scheduler_rows"][0]["array_task"], 0)
            with self.assertRaisesRegex(
                C.SourceConsumerError, "scheduler stdout identity",
            ):
                C._poll_bundle(
                    directory, campaign=C.CAMPAIGN,
                    poll_schema=C.FULL_POLL_SCHEMA, expected_tasks=2,
                    launch_receipt_sha256=ZERO,
                    launch_recorded_utc=launch.isoformat(),
                    expected_job_id=JOB,
                    expected_job_name="pdb-source-v11-" + TOKEN,
                )

    def test_active_poll_then_terminal_success_is_a_valid_hourly_chain(self):
        launch = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            first = normal_poll(
                directory, 0, previous=None, anchor=launch, state="RUNNING"
            )
            second = normal_poll(
                directory, 1, previous=first,
                anchor=launch + datetime.timedelta(hours=1),
            )
            _raws, digest, final = C._poll_bundle(
                directory, campaign=C.CAMPAIGN,
                poll_schema=C.FULL_POLL_SCHEMA, expected_tasks=1,
                launch_receipt_sha256=ZERO,
                launch_recorded_utc=launch.isoformat(), expected_job_id=JOB,
                expected_job_name="pdb-source-v11-" + TOKEN,
            )
            self.assertEqual(digest, second)
            self.assertTrue(final["all_success"])

    def test_poll_tampering_in_command_time_job_stdout_or_result_is_rejected(self):
        launch = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        cases = ("command", "timestamp", "job", "stdout", "result")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                normal_poll(directory, 0, previous=None, anchor=launch)
                if case in ("command", "timestamp"):
                    path = directory / "poll-0000-intent.json"
                    value = json.loads(path.read_text())
                    if case == "command":
                        value["command"][-1] = "JobIDRaw"
                    else:
                        value["recorded_utc"] = "2026-01-01T01:00:00"
                    path.chmod(0o600)
                    put(path, canonical(value))
                elif case == "job":
                    path = directory / "poll-0000-receipt.json"
                    value = json.loads(path.read_text())
                    value["job_id"] = "999"
                    path.chmod(0o600)
                    put(path, canonical(value))
                elif case == "stdout":
                    path = directory / "poll-0000-stdout.bin"
                    path.chmod(0o600)
                    put(path, path.read_bytes() + b"forged\n")
                else:
                    path = directory / "poll-0000-result.json"
                    value = json.loads(path.read_text())
                    value["single_scheduler_query"] = False
                    path.chmod(0o600)
                    put(path, canonical(value))
                with self.assertRaises(C.SourceConsumerError):
                    C._poll_bundle(
                        directory, campaign=C.CAMPAIGN,
                        poll_schema=C.FULL_POLL_SCHEMA, expected_tasks=1,
                        launch_receipt_sha256=ZERO,
                        launch_recorded_utc=launch.isoformat(),
                        expected_job_id=JOB,
                        expected_job_name="pdb-source-v11-" + TOKEN,
                    )

    def test_abandoned_attempt_is_non_authorizing_but_successor_can_pass(self):
        launch = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        query_time = launch + datetime.timedelta(hours=1)
        command = [
            "/usr/bin/sacct", "-j", JOB, "-X", "--array", "-n", "-P",
            "--format=JobIDRaw,Account,Partition,QOS,ReqCPUS,ReqMem,Timelimit,State,ExitCode,Restarts,JobName",
        ]
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            stdout_path = directory / "poll-0000-stdout.bin"
            stderr_path = directory / "poll-0000-stderr.bin"
            put(stdout_path, b"")
            put(stderr_path, b"")
            intent = {
                "schema": C.FULL_POLL_SCHEMA + "/intent",
                "campaign": C.CAMPAIGN, "poll_index": 0, "job_id": JOB,
                "recorded_utc": query_time.isoformat(timespec="seconds"),
                "not_before_utc": query_time.isoformat(timespec="seconds"),
                "previous_poll_receipt_sha256": None,
                "launch_receipt_sha256": ZERO, "command": command,
                "capture_initial_identities": {
                    "stdout": capture_identity(stdout_path, initial=True),
                    "stderr": capture_identity(stderr_path, initial=True),
                },
            }
            intent_raw = canonical(intent)
            put(directory / "poll-0000-intent.json", intent_raw)
            abandoned_time = query_time + datetime.timedelta(hours=1)
            durable = {
                "poll-0000-intent.json": hashlib.sha256(intent_raw).hexdigest(),
                "poll-0000-stdout.bin": hashlib.sha256(b"").hexdigest(),
                "poll-0000-stderr.bin": hashlib.sha256(b"").hexdigest(),
            }
            abandoned = {
                "schema": C.FULL_POLL_SCHEMA + "/abandoned",
                "campaign": C.CAMPAIGN, "poll_index": 0, "job_id": JOB,
                "recorded_utc": abandoned_time.isoformat(timespec="seconds"),
                "successor_not_before_utc": abandoned_time.isoformat(timespec="seconds"),
                "intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
                "durable_files": durable, "outcome": "abandoned-unknown",
                "authorizing": False, "scheduler_queries_during_recovery": 0,
            }
            abandoned_raw = canonical(abandoned)
            put(directory / "poll-0000-abandoned.json", abandoned_raw)
            abandoned_sha = hashlib.sha256(abandoned_raw).hexdigest()
            final_sha = normal_poll(
                directory, 1, previous=abandoned_sha, anchor=query_time,
            )
            _raws, observed, final = C._poll_bundle(
                directory, campaign=C.CAMPAIGN,
                poll_schema=C.FULL_POLL_SCHEMA, expected_tasks=1,
                launch_receipt_sha256=ZERO,
                launch_recorded_utc=launch.isoformat(), expected_job_id=JOB,
                expected_job_name="pdb-source-v11-" + TOKEN,
            )
            self.assertEqual(observed, final_sha)
            self.assertTrue(final["all_success"])

    def test_poll_rejects_byte_identical_capture_replacement(self):
        launch = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        for abandoned in (False, True):
            with self.subTest(abandoned=abandoned), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                if abandoned:
                    first = abandoned_poll(
                        directory, 0, previous=None, anchor=launch,
                        with_result=True,
                    )
                    normal_poll(
                        directory, 1, previous=first,
                        anchor=launch + datetime.timedelta(hours=1),
                    )
                else:
                    normal_poll(directory, 0, previous=None, anchor=launch)
                path = directory / "poll-0000-stdout.bin"
                raw = path.read_bytes()
                path.chmod(0o600)
                path.unlink()
                put(path, raw)
                with self.assertRaisesRegex(C.SourceConsumerError, "capture identity"):
                    C._poll_bundle(
                        directory, campaign=C.CAMPAIGN,
                        poll_schema=C.FULL_POLL_SCHEMA, expected_tasks=1,
                        launch_receipt_sha256=ZERO,
                        launch_recorded_utc=launch.isoformat(),
                        expected_job_id=JOB,
                        expected_job_name="pdb-source-v11-" + TOKEN,
                    )

    def test_abandoned_poll_requires_streams_and_exact_result(self):
        launch = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        for case in ("missing-stream", "bad-result"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temporary:
                directory = Path(temporary)
                previous = abandoned_poll(
                    directory, 0, previous=None, anchor=launch,
                    with_result=True,
                )
                normal_poll(
                    directory, 1, previous=previous,
                    anchor=launch + datetime.timedelta(hours=1),
                )
                if case == "missing-stream":
                    path = directory / "poll-0000-stderr.bin"
                    path.chmod(0o600)
                    path.unlink()
                else:
                    result_path = directory / "poll-0000-result.json"
                    result = json.loads(result_path.read_text("ascii"))
                    result["process_returncode"] = True
                    result_raw = canonical(result)
                    result_path.chmod(0o600)
                    put(result_path, result_raw)
                    abandoned_path = directory / "poll-0000-abandoned.json"
                    abandoned = json.loads(abandoned_path.read_text("ascii"))
                    abandoned["durable_files"][result_path.name] = hashlib.sha256(
                        result_raw,
                    ).hexdigest()
                    abandoned_path.chmod(0o600)
                    put(abandoned_path, canonical(abandoned))
                with self.assertRaises(C.SourceConsumerError):
                    C._poll_bundle(
                        directory, campaign=C.CAMPAIGN,
                        poll_schema=C.FULL_POLL_SCHEMA, expected_tasks=1,
                        launch_receipt_sha256=ZERO,
                        launch_recorded_utc=launch.isoformat(),
                        expected_job_id=JOB,
                        expected_job_name="pdb-source-v11-" + TOKEN,
                    )

    def test_poll_after_terminal_is_rejected(self):
        launch = datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            previous = normal_poll(
                directory, 0, previous=None, anchor=launch,
            )
            abandoned_poll(
                directory, 1, previous=previous,
                anchor=launch + datetime.timedelta(hours=1), with_result=False,
            )
            with self.assertRaisesRegex(
                C.SourceConsumerError, "follows a terminal poll",
            ):
                C._poll_bundle(
                    directory, campaign=C.CAMPAIGN,
                    poll_schema=C.FULL_POLL_SCHEMA, expected_tasks=1,
                    launch_receipt_sha256=ZERO,
                    launch_recorded_utc=launch.isoformat(),
                    expected_job_id=JOB,
                    expected_job_name="pdb-source-v11-" + TOKEN,
                )

    def test_candidate_semantics_reject_self_consistent_forgery(self):
        inventory, task, streams = candidate_fixture()
        C._validate_candidate_record(
            task, inventory, shard_index=0, position=0,
            candidate_origin="v11-fresh", stream_raws=streams,
            code_manifest_sha256=ZERO, repository_commit_id=SOURCE,
        )
        cases = (
            "resource", "child", "prlimit", "isolation", "snapshot",
            "stream", "disposition", "extra-key",
        )
        for case in cases:
            with self.subTest(case=case):
                changed = copy.deepcopy(task)
                if case == "resource":
                    changed["resource_contract"]["address_space_bytes"] += 1
                    changed["resource_contract_sha256"] = C._digest(
                        changed["resource_contract"],
                    )
                elif case == "child":
                    changed["child_limit_attestation"]["no_new_privs"] = 0
                elif case == "prlimit":
                    changed["parent_prlimit_observation"]["command"][-1] = "--json"
                elif case == "isolation":
                    changed["parent_isolation_observation"][
                        "process_creation_syscalls_denied"
                    ] = []
                elif case == "snapshot":
                    changed["source_snapshot"]["files"].reverse()
                elif case == "stream":
                    changed["stdout"]["tail_base64"] = ""
                elif case == "disposition":
                    changed["eligible_for_cohort"] = False
                else:
                    changed["extra"] = True
                with self.assertRaises(C.SourceConsumerError):
                    C._validate_candidate_record(
                        changed, inventory, shard_index=0, position=0,
                        candidate_origin="v11-fresh", stream_raws=streams,
                        code_manifest_sha256=ZERO,
                        repository_commit_id=SOURCE,
                    )

    def test_candidate_exact_input_and_resource_dispositions(self):
        inventory, success, streams = candidate_fixture()
        rejected = copy.deepcopy(success)
        rejected.update({
            "process_returncode": 31, "normalization": None, "sas": None,
            "sas_bytes": None, "sas_sha256": None,
            "partial_sas_evidence": None, "status": "input-rejected",
            "resource_exclusion_kind": None, "support_determined": True,
            "supported": False,
            "support_exclusion_reasons": ["translation-input-rejected"],
            "eligible_for_cohort": False,
        })
        excluded = copy.deepcopy(success)
        excluded.update({
            "process_returncode": 20, "normalization": None, "sas": None,
            "sas_bytes": None, "sas_sha256": None,
            "partial_sas_evidence": {
                "bytes": 0, "sha256": hashlib.sha256(b"").hexdigest(),
                "discarded": True,
            },
            "status": "resource-excluded", "resource_exclusion_kind": "memory",
            "support_determined": False, "supported": None,
            "support_exclusion_reasons": None, "eligible_for_cohort": False,
        })
        for task in (rejected, excluded):
            C._validate_candidate_record(
                task, inventory, shard_index=0, position=0,
                candidate_origin="v11-fresh", stream_raws=streams,
                code_manifest_sha256=ZERO, repository_commit_id=SOURCE,
            )
        excluded["supported"] = False
        with self.assertRaisesRegex(C.SourceConsumerError, "disposition"):
            C._validate_candidate_record(
                excluded, inventory, shard_index=0, position=0,
                candidate_origin="v11-fresh", stream_raws=streams,
                code_manifest_sha256=ZERO, repository_commit_id=SOURCE,
            )

    def test_task_environment_is_exact_and_manifest_bound(self):
        tracked = {"experiments/code.sha256": ZERO}
        tracked.update({name: "7" * 64 for name in C.REQUIRED_SOURCE_FILES})
        tracked.update({
            "src/translate/module-{:02d}.py".format(index):
            hashlib.sha256(str(index).encode()).hexdigest()
            for index in range(38)
        })
        translator_records = [
            {"path": name, "sha256": tracked[name]}
            for name in sorted(tracked) if name.startswith("src/translate/")
        ]
        result_raw = b"{}"
        environment = {
            "schema": C.TASK_ENVIRONMENT_SCHEMA, "array_job_id": JOB,
            "array_task_id": 0, "slurm_restart_count": 0,
            "candidate_indices": [0, 1],
            "task_tmp_identity": recorded_identity(100, 0, 0o700),
            "code_manifest_sha256": ZERO,
            "source_inventory_sha256": "1" * 64,
            "repository_commit_id": SOURCE,
            "pinned_python_identity": recorded_identity(101, 100, 0o755),
            "pinned_python_sha256": C.PYTHON_EXECUTABLE_SHA256,
            "prior_campaign_payloads_read": [],
            "prior_campaign_payloads_reused": [],
            "manifest_evidence": {
                "code_manifest_sha256": ZERO,
                "code_manifest_records": 62,
                "pinned_python_sha256": C.PYTHON_EXECUTABLE_SHA256,
                "prlimit_sha256": C.PRLIMIT_SHA256,
                "libseccomp_sha256": C.LIBSECCOMP_SHA256,
                "translator_file_count": 38,
                "translator_files_sha256": C._digest(translator_records),
            },
            "output_root_identity": recorded_identity(200, 0, 0o700),
            "stage_directory_identity": recorded_identity(301, 0, 0o700),
            "result_sha256": hashlib.sha256(result_raw).hexdigest(),
        }
        kwargs = {
            "shard_index": 0, "candidate_indices": [0, 1], "job_id": JOB,
            "inventory_sha256": "1" * 64, "code_manifest_sha256": ZERO,
            "repository_commit_id": SOURCE, "tracked": tracked,
            "output_root_identity": {
                "device": 1, "inode": 200, "uid": os.getuid(),
            },
            "shard_info": SimpleNamespace(
                st_dev=1, st_ino=300, st_uid=os.getuid(),
            ),
            "result_raw": result_raw,
        }
        C._validate_task_environment(environment, **kwargs)
        for case in ("extra", "manifest", "stage"):
            with self.subTest(case=case):
                changed = copy.deepcopy(environment)
                if case == "extra":
                    changed["extra"] = True
                elif case == "manifest":
                    changed["manifest_evidence"]["code_manifest_records"] += 1
                else:
                    changed["stage_directory_identity"]["device"] += 1
                with self.assertRaises(C.SourceConsumerError):
                    C._validate_task_environment(changed, **kwargs)

    def test_split_is_independently_ranked_and_exact(self):
        families = [
            *C.ALL_PRIOR_UNREPRESENTED_FAMILIES,
            *("new-family-{:02d}".format(index) for index in range(20)),
        ]
        records = []
        for index in range(C.CANDIDATE_COUNT):
            family = families[index % len(families)]
            problem = "problem-{:04d}.pddl".format(index)
            records.append({
                "candidate_index": index, "family": family,
                "problem_sha256": hashlib.sha256(problem.encode()).hexdigest(),
                "canonical_path": family + "/" + problem,
                "directory": family, "problem": problem,
                "problem_file": family + "/" + problem,
                "domain_file": family + "/domain.pddl", "supported": True,
            })
        gate, cohorts = C._recompute_split(records)
        self.assertTrue(gate["passed"])
        self.assertEqual(
            len(cohorts["confirmation_a"]["candidate_indices"]), 650,
        )
        self.assertEqual(len(cohorts["guided_b"]["candidate_indices"]), 300)
        self.assertEqual(
            cohorts["guided_b"]["candidate_indices"],
            cohorts["guided_b"]["base_candidate_indices"]
            + cohorts["guided_b"]["top_up_candidate_indices"],
        )
        forged = copy.deepcopy(cohorts)
        forged["confirmation_a"]["candidate_indices"][:2] = reversed(
            forged["confirmation_a"]["candidate_indices"][:2]
        )
        forged["confirmation_a"]["candidate_indices_sha256"] = C._digest(
            forged["confirmation_a"]["candidate_indices"],
        )
        self.assertNotEqual(forged, C._recompute_split(records)[1])

    def test_output_namespace_second_pass_rejects_directory_replacement(self):
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(
            C, "SHARD_COUNT", 1,
        ):
            root = Path(temporary) / "output"
            root.mkdir(mode=0o700)
            put(root / "source-inventory-v11.json", b"{}")
            shard = root / C.shard_name(0)
            shard.mkdir(mode=0o700)
            for name in C._expected_shard_names(0):
                put(shard / name, b"{}")
            shard.chmod(0o500)
            root_info = root.lstat()
            shard_info = shard.lstat()
            execution = {"output_tree": {
                "root_identity": {
                    "path": str(root), "canonical_path": str(root),
                    "device": root_info.st_dev, "inode": root_info.st_ino,
                    "mode": "0700", "uid": root_info.st_uid,
                    "gid": root_info.st_gid,
                },
                "directories": [{
                    "path": shard.name, "device": shard_info.st_dev,
                    "inode": shard_info.st_ino, "uid": shard_info.st_uid,
                    "gid": shard_info.st_gid, "mode": "0500",
                }],
            }}
            paths = SimpleNamespace(data_root=root)
            C._validate_output_namespace_stable(paths, execution)
            old = root / "old"
            shard.rename(old)
            replacement = root / C.shard_name(0)
            replacement.mkdir(mode=0o700)
            for name in C._expected_shard_names(0):
                put(replacement / name, b"{}")
            replacement.chmod(0o500)
            with self.assertRaisesRegex(
                C.SourceConsumerError, "changed after snapshot",
            ):
                C._validate_output_namespace_stable(paths, execution)

    def test_preflight_binding_uses_seal_commit_not_source_commit(self):
        preflight = C.AuthorizedPreflight(
            C.PREFLIGHT_CAMPAIGN, PREFLIGHT_SEAL, SOURCE, ZERO, ZERO, ZERO,
            ZERO, ZERO, ZERO, ZERO, True, MappingProxyType({}),
        )
        binding = C._preflight_binding(preflight)
        self.assertEqual(binding["seal_repository_commit_id"], PREFLIGHT_SEAL)
        self.assertNotIn(SOURCE, binding.values())

    def test_scheduler_rejection_precedes_any_worker_payload_read(self):
        preflight = C.AuthorizedPreflight(
            C.PREFLIGHT_CAMPAIGN, PREFLIGHT_SEAL, SOURCE, ZERO, ZERO, ZERO,
            ZERO, ZERO, ZERO, ZERO, True, MappingProxyType({}),
        )
        binding = C._preflight_binding(preflight)
        launch = {
            "schema": C.LAUNCH_SCHEMA, "campaign": C.CAMPAIGN,
            "repository_commit_id": PREFLIGHT_SEAL, "job_id": JOB,
            "submission_token": TOKEN, "source_inventory_sha256": ZERO,
            "code_manifest_sha256": ZERO, "whole_campaign_fresh": True,
            "prior_runtime_payloads_read": 0,
            "prior_runtime_payload_bytes_read": 0,
            "prior_runtime_payloads_reused": 0,
            "selective_recovery_authorized": False,
            "preflight_authorization": binding,
            "accepted_utc": "2026-01-01T00:00:01+00:00",
        }
        intent = {"recorded_utc": "2026-01-01T00:00:00+00:00"}
        terminal = {
            "schema": C.FULL_TERMINAL_RECEIPT_SCHEMA,
            "campaign": C.CAMPAIGN, "job_id": JOB, "all_success": False,
            "state_counts": {"FAILED": 820},
            "terminal_poll_receipt_sha256": ZERO,
        }
        values = {
            "source-audit-launch-receipt-v11.json": launch,
            "source-audit-launch-intent-v11.json": intent,
            "source-audit-scheduler-terminal-receipt-v11.json": terminal,
        }
        def fake_read(path: Path, _label: str, mode: int = 0o400) -> bytes:
            return canonical(values.get(Path(path).name, {}))
        paths = C.paths_for(Path("/repo/artifacts"), Path("/worker-payload"))
        with (
            mock.patch.object(C, "_artifact_namespace"),
            mock.patch.object(C, "_read_regular", side_effect=fake_read),
            mock.patch.object(C, "_poll_bundle", return_value=({}, ZERO, {})),
            mock.patch.object(C, "_validate_output_tree") as payload_read,
            self.assertRaises(C.SourceConsumerError),
        ):
            C.load_authorized_confirmation(
                paths, snapshot_reader=lambda _r, _p: {},
                seal_revision=FULL_SEAL, preflight=preflight,
            )
        payload_read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
