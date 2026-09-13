#!/usr/bin/env python3
"""Adversarial synthetic tests for the independent V9 consumer."""

from __future__ import annotations

import ast
import base64
import copy
import hashlib
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import pdb_terminal_incidence_confirmation_source_consumer_v9 as C


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _source(index: int, family: str = "family") -> dict:
    candidate = {
        "directory": "dir-{}".format(family),
        "family": family,
        "problem": "p{:04d}.pddl".format(index),
        "domain_file": "dir-{}/domain.pddl".format(family),
        "problem_file": "dir-{}/p{:04d}.pddl".format(family, index),
        "domain_sha256": _sha("domain-{}".format(family)),
        "problem_sha256": _sha("problem-{}".format(index)),
    }
    return {
        "candidate_index": index,
        **candidate,
        "canonical_path": candidate["problem_file"],
        "is_shadow_family": False,
        "is_shadow_unrepresented": True,
        "is_all_prior_represented": False,
        "is_all_prior_unrepresented": True,
        "aliases": [candidate],
    }


def _stream(label: str, retained_path: str) -> dict:
    payload = label.encode("ascii")
    return {
        "total_bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "retained_path": retained_path,
        "retained_bytes": len(payload),
        "retained_sha256": hashlib.sha256(payload).hexdigest(),
        "retention_limit_bytes": C.STREAM_PREFIX_BYTES,
        "truncated": False,
        "tail_base64": base64.b64encode(payload).decode("ascii"),
        "tail_bytes": len(payload),
    }


def _sas() -> dict:
    return {
        "sas_version": 3,
        "metric": 1,
        "num_variables": 2,
        "num_mutex_groups": 0,
        "num_operators": 1,
        "num_effects": 1,
        "num_conditional_effects": 0,
        "num_zero_cost_operators": 0,
        "min_operator_cost": 1,
        "max_operator_cost": 1,
        "num_serialized_axioms": 0,
    }


def _task(source: dict, outcome: str = "success", kind: str = "memory") -> dict:
    index = source["candidate_index"]
    returncode = 0
    sas = _sas()
    sas_bytes = 123
    sas_sha256 = _sha("sas-{}".format(index))
    normalization = {
        "schema": C.NORMALIZATION_SCHEMA,
        "strategy": "axiom_based",
        "num_normalized_axioms": 0,
    }
    exclusion = None
    supported = True
    support_determined = True
    reasons = []
    eligible = True
    if outcome == "input-rejected":
        returncode = 31
        sas = sas_bytes = sas_sha256 = None
        normalization = None
        supported = False
        reasons = ["translation-input-rejected"]
        eligible = False
    elif outcome == "resource-excluded":
        returncode = 20 if kind == "memory" else 21
        sas = sas_bytes = sas_sha256 = None
        normalization = None
        exclusion = kind
        supported = None
        support_determined = False
        reasons = None
        eligible = False
    identity = {
        "device": 1, "inode": 10000 + index, "mode": 0o400,
        "uid": os.getuid(), "size": 10,
    }
    snapshot_files = []
    for role, file_key, sha_key, name in (
        ("domain", "domain_file", "domain_sha256", "domain.pddl"),
        ("problem", "problem_file", "problem_sha256", "problem.pddl"),
    ):
        item_identity = dict(identity)
        item_identity["inode"] += 1 if role == "domain" else 2
        snapshot_files.append({
            "role": role,
            "source_file": source[file_key],
            "source_identity": dict(item_identity),
            "snapshot_name": name,
            "snapshot_identity_before": dict(item_identity),
            "bytes": 10,
            "sha256": source[sha_key],
            "snapshot_identity_after": dict(item_identity),
        })
    prlimit_stdout = (
        "AS {} {} bytes\nCPU {} {} seconds\n".format(
            C.ADDRESS_SPACE_BYTES, C.ADDRESS_SPACE_BYTES,
            C.CPU_LIMIT_SECONDS, C.CPU_HARD_LIMIT_SECONDS,
        ).encode("ascii")
    )
    return {
        "schema": C.CANDIDATE_SCHEMA,
        **source,
        "logical_shard_index": index // C.TASKS_PER_SHARD,
        "position_in_shard": index % C.TASKS_PER_SHARD,
        "candidate_origin": C.FRESH_ORIGIN,
        "translation_attempted": True,
        "translator_command": [
            "PINNED_PYTHON", "-B",
            "experiments/pdb_terminal_incidence_confirmation_translate_v9.py",
            "--", source["domain_file"], source["problem_file"],
        ],
        "code_manifest_sha256": _sha("code"),
        "repository_commit_id": "b" * 40,
        "resource_contract": C._resource_contract(),
        "resource_contract_sha256": C._digest(C._resource_contract()),
        "child_limit_attestation": {
            "schema": C.CHILD_LIMIT_SCHEMA,
            "pid": 1000 + index,
            "process_group": 1000 + index,
            "rlimit_as": [C.ADDRESS_SPACE_BYTES, C.ADDRESS_SPACE_BYTES],
            "rlimit_cpu": [C.CPU_LIMIT_SECONDS, C.CPU_HARD_LIMIT_SECONDS],
            "no_new_privs": 1,
            "seccomp_mode": 2,
            "seccomp_filters": 1,
            "threads": 1,
        },
        "parent_prlimit_observation": {
            "tool_sha256": C.PRLIMIT_SHA256,
            "command": [
                "/usr/bin/prlimit", "--pid", "CHILD_PID", "--as", "--cpu",
                "--output=RESOURCE,SOFT,HARD,UNITS", "--noheadings", "--raw",
            ],
            "stdout_sha256": hashlib.sha256(prlimit_stdout).hexdigest(),
            "rlimit_as": [C.ADDRESS_SPACE_BYTES, C.ADDRESS_SPACE_BYTES],
            "rlimit_cpu": [C.CPU_LIMIT_SECONDS, C.CPU_HARD_LIMIT_SECONDS],
        },
        "parent_isolation_observation": {
            "status_sha256": _sha("status-{}".format(index)),
            "process_group": 1000 + index,
            "no_new_privs": 1,
            "seccomp_mode": 2,
            "seccomp_filters": 1,
            "threads": 1,
            "process_creation_syscalls_denied": list(
                C.DENIED_PROCESS_SYSCALLS
            ),
            "libseccomp_sha256": C.LIBSECCOMP_SHA256,
        },
        "process_returncode": returncode,
        "complete_process_group_reaped": True,
        "stdout": _stream(
            "stdout", "candidate-{:04d}.stdout.prefix".format(index),
        ),
        "stderr": _stream(
            "stderr", "candidate-{:04d}.stderr.prefix".format(index),
        ),
        "normalization": normalization,
        "sas": sas,
        "sas_bytes": sas_bytes,
        "sas_sha256": sas_sha256,
        "partial_sas_evidence": None,
        "status": outcome,
        "resource_exclusion_kind": exclusion,
        "support_determined": support_determined,
        "supported": supported,
        "support_exclusion_reasons": reasons,
        "eligible_for_cohort": eligible,
        "source_snapshot": {
            "schema": C.SOURCE_SNAPSHOT_SCHEMA,
            "files": snapshot_files,
            "candidate_private_working_directory": True,
            "source_hashes_verified_before_use": True,
            "identity_and_sha256_verified_after_use": True,
            "exact_snapshot_files_removed": True,
        },
    }


def _write_json(path: Path, value: dict) -> bytes:
    raw = C._canonical_json(value)
    path.write_bytes(raw)
    path.chmod(0o400)
    return raw


def _tracked_manifest() -> dict[str, str]:
    return {
        C.CODE_MANIFEST_RELATIVE: _sha("manifest"),
        **{path: _sha(path) for path in C.CODE_MANIFEST_FILES},
    }


def _slurm_template(log_root: str) -> bytes:
    lines = [
        "#!/bin/bash",
        "#SBATCH --account=" + C.RESOURCE_PROFILE["account"],
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
        "    --num-shards 820 \\",
        '    --shard-index "${SLURM_ARRAY_TASK_ID}" \\',
        '    --tmp-root "${tmp_root}"',
        C.MANIFEST_PLACEHOLDER.decode("ascii"),
        C.INVENTORY_PLACEHOLDER.decode("ascii"),
        C.COMMIT_PLACEHOLDER.decode("ascii"),
    ]
    return ("\n".join(lines) + "\n").encode("ascii")


def _replace_json(path: Path, value: dict) -> bytes:
    path.chmod(0o600)
    return _write_json(path, value)


def _launch_journal_fixture(
    root: Path, *, recovered: bool = False, returncode: int = 0,
    stdout: bytes = b"123\n",
) -> tuple[C.V9Paths, dict, dict[str, str]]:
    artifacts = root / "artifacts"
    data = root / "data"
    temporary = root / "tmp"
    logs = root / "logs"
    for directory in (artifacts, data, temporary, logs):
        directory.mkdir(mode=0o700)
        directory.chmod(0o700)
    paths = C.paths_for(
        artifacts, data, tmpdir_root=temporary, log_root=logs,
        slurm_program=root / "source-scan-v9.slurm",
    )
    roots = {
        "artifact_dir": C._expected_root_identity(artifacts, "artifacts"),
        "log_root": C._expected_root_identity(logs, "logs"),
        "output_dir": C._expected_root_identity(data, "data"),
        "tmpdir_root": C._expected_root_identity(temporary, "tmp"),
    }
    paths.sbatch_stdout.write_bytes(stdout)
    paths.sbatch_stderr.write_bytes(b"diagnostic")
    paths.sbatch_stdout.chmod(0o400)
    paths.sbatch_stderr.chmod(0o400)

    def initial(path):
        info = path.lstat()
        return {
            "path": str(path), "canonical_path": str(path),
            "device": info.st_dev, "inode": info.st_ino,
            "mode": "0400", "uid": info.st_uid, "gid": info.st_gid,
            "link_count": 1, "bytes_at_intent": 0,
        }

    initial_identities = {
        "stdout": initial(paths.sbatch_stdout),
        "stderr": initial(paths.sbatch_stderr),
    }
    tracked = _tracked_manifest()
    code_records = [
        {"path": path, "sha256": tracked[path]}
        for path in C.CODE_MANIFEST_FILES
    ]
    token = "a" * 24
    slurm = {
        "template_path": str(paths.slurm_program),
        "template_sha256": _sha("template"),
        "rendered_sha256": _sha("rendered"),
        "rendered_bytes": 123,
        "submission_mode": "stdin",
        "path_argument": False,
    }
    zero_prior = {
        "prior_runtime_payloads_read": 0,
        "prior_runtime_payload_bytes_read": 0,
        "prior_runtime_payloads_reused": 0,
        "selective_recovery_authorized": False,
        "whole_campaign_fresh": True,
    }
    intent = {
        "schema": C.LAUNCH_INTENT_SCHEMA,
        "campaign": C.CAMPAIGN,
        "recorded_utc": "2026-09-13T12:34:56+00:00",
        "submission_token": token,
        "repository_commit_id": "b" * 40,
        "resource_profile": C.RESOURCE_PROFILE,
        "array_mapping": C._array_mapping(),
        "source_inventory": {
            "path": str(paths.inventory),
            "sha256": _sha("inventory"),
            "candidate_count": C.CANDIDATE_COUNT,
        },
        "source_inventory_sha256": _sha("inventory"),
        "code_manifest": {
            "path": str(paths.code_manifest),
            "sha256": tracked[C.CODE_MANIFEST_RELATIVE],
            "files": code_records,
            "files_sha256": C._digest(code_records),
        },
        "code_manifest_sha256": tracked[C.CODE_MANIFEST_RELATIVE],
        "slurm_program": slurm,
        "root_identities": roots,
        "execution_environment": C._execution_environment(paths),
        "capture_protocol": C.CAPTURE_PROTOCOL,
        "sbatch_capture_initial_identities": initial_identities,
        "submit_command": C._expected_submit_command(paths, token),
        **zero_prior,
    }
    intent_raw = _write_json(paths.launch_intent, intent)
    process = {
        "kind": "completed-process", "returncode": returncode,
        "os_error_type": None, "os_error_errno": None,
    }
    parsed = C._parse_job_id(stdout)
    accepted = returncode == 0 and parsed is not None
    records = {
        "stdout": C._capture_record(
            paths.sbatch_stdout, stdout, paths.sbatch_stdout.lstat(),
            initial_identities["stdout"], "stdout",
        ),
        "stderr": C._capture_record(
            paths.sbatch_stderr, b"diagnostic", paths.sbatch_stderr.lstat(),
            initial_identities["stderr"], "stderr",
        ),
    }
    result = {
        "schema": C.SBATCH_RESULT_SCHEMA,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "submit_command_sha256": C._digest(intent["submit_command"]),
        "slurm_program_sha256": slurm["rendered_sha256"],
        "capture_protocol": C.CAPTURE_PROTOCOL,
        "process_observation": process,
        "stdout": records["stdout"], "stderr": records["stderr"],
        "parsed_job_id": parsed,
        "accepted_by_launcher": accepted,
        "raw_streams_preserved": True,
    }
    result_raw = _write_json(paths.sbatch_result, result)
    recovery = None
    if recovered and accepted:
        recovery = {
            "source": "retained-sbatch-stdout", "job_id": "123",
            "stdout_sha256": records["stdout"]["sha256"],
            "accepted_returncode_zero": True, "no_resubmission": True,
        }
    elif recovered:
        row = {
            "job_id": "123_0", "job_name": "pdb-source-v9-" + token,
            "comment": "pdb-source-v9-" + token,
            "submit_command": C._expected_submit_command(paths, token),
        }
        recovery = {
            "source": "scheduler-submission-journal", "job_id": "123",
            "rows": [row], "rows_sha256": C._digest([row]),
            "no_resubmission": True,
        }
        if parsed is not None:
            recovery.update({
                "uncertain_stdout_job_id": parsed,
                "uncertain_stdout_sha256": records["stdout"]["sha256"],
            })
    launch = {
        "schema": C.LAUNCH_SCHEMA, "campaign": C.CAMPAIGN,
        "job_id": "123", "submission_token": token,
        "repository_commit_id": "b" * 40,
        "source_inventory_sha256": _sha("inventory"),
        "code_manifest_sha256": tracked[C.CODE_MANIFEST_RELATIVE],
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "sbatch_result_sha256": hashlib.sha256(result_raw).hexdigest(),
        "resource_profile": C.RESOURCE_PROFILE,
        "root_identities": roots, "slurm_program": slurm,
        "launch_recovered": recovered, "recovery_evidence": recovery,
        **zero_prior,
    }
    return paths, launch, tracked


class V9ConsumerTest(unittest.TestCase):
    def test_consumer_has_no_campaign_imports(self):
        tree = ast.parse(Path(C.__file__).read_text(encoding="utf-8"))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.append(node.module or "")
        self.assertFalse(any("pdb_terminal" in name or "audit_pdb" in name
                             or "launch_pdb" in name for name in imported))

    def test_production_population_and_mapping_are_exact(self):
        self.assertEqual(C.CANDIDATE_COUNT, 1640)
        self.assertEqual(C.SHARD_COUNT, 820)
        self.assertEqual(C.TASKS_PER_SHARD, 2)
        self.assertEqual(
            [2 * shard + offset for shard in range(C.SHARD_COUNT)
             for offset in range(C.TASKS_PER_SHARD)],
            list(range(C.CANDIDATE_COUNT)),
        )
        self.assertEqual(C.RESOURCE_PROFILE["partition"], "fat")
        self.assertIsNone(C.RESOURCE_PROFILE["array_throttle"])

    def test_committed_manifest_snapshot_is_complete_and_rejects_old_campaigns(self):
        payloads = {
            path: ("payload:" + path).encode("ascii")
            for path in C.CODE_MANIFEST_FILES
        }
        log_root = "/synthetic/v9-logs"
        template = _slurm_template(log_root)
        payloads[C.SLURM_PROGRAM_RELATIVE] = template
        lines = [
            "{}  {}\n".format(hashlib.sha256(raw).hexdigest(), path)
            for path, raw in payloads.items()
        ]
        manifest = "".join(lines).encode("ascii")
        inventory_sha256 = _sha("inventory")
        rendered = template.replace(
            C.MANIFEST_PLACEHOLDER, hashlib.sha256(manifest).hexdigest().encode("ascii"),
        ).replace(
            C.INVENTORY_PLACEHOLDER, inventory_sha256.encode("ascii"),
        ).replace(C.COMMIT_PLACEHOLDER, b"b" * 40)
        launch = {
            "repository_commit_id": "b" * 40,
            "code_manifest_sha256": hashlib.sha256(manifest).hexdigest(),
            "source_inventory_sha256": inventory_sha256,
            "root_identities": {"log_root": {"path": log_root}},
            "slurm_program": {
                "template_sha256": hashlib.sha256(template).hexdigest(),
                "rendered_sha256": hashlib.sha256(rendered).hexdigest(),
                "rendered_bytes": len(rendered),
            },
        }

        def snapshot(revision, paths):
            self.assertEqual(revision, "b" * 40)
            available = {C.CODE_MANIFEST_RELATIVE: manifest, **payloads}
            return {path: available[path] for path in paths}

        tracked = C._validate_producer_snapshot(launch, snapshot)
        self.assertEqual(set(tracked), {C.CODE_MANIFEST_RELATIVE, *payloads})

        def changed_snapshot(_revision, paths):
            available = {C.CODE_MANIFEST_RELATIVE: manifest, **payloads}
            result = {path: available[path] for path in paths}
            if C.TRANSLATOR_FILES[0] in result:
                result[C.TRANSLATOR_FILES[0]] = b"changed"
            return result

        with self.assertRaisesRegex(C.SourceConsumerError, "producer byte"):
            C._validate_producer_snapshot(launch, changed_snapshot)

        missing_path = C.CODE_MANIFEST_FILES[-1]
        missing_manifest = b"".join(
            line for line in manifest.splitlines(keepends=True)
            if not line.endswith(("  " + missing_path + "\n").encode("ascii"))
        )
        with self.assertRaisesRegex(C.SourceConsumerError, "closure"):
            C._validate_producer_snapshot(
                {**launch, "code_manifest_sha256": hashlib.sha256(missing_manifest).hexdigest()},
                lambda _revision, paths: {path: missing_manifest for path in paths},
            )

        old_path = "experiments/audit_source_v8.py"
        old_raw = b"old"
        old_manifest = manifest + (
            "{}  {}\n".format(hashlib.sha256(old_raw).hexdigest(), old_path)
        ).encode("ascii")
        old_launch = {
            **launch,
            "code_manifest_sha256": hashlib.sha256(old_manifest).hexdigest(),
        }
        with self.assertRaisesRegex(C.SourceConsumerError, "path"):
            C._validate_producer_snapshot(
                old_launch,
                lambda _revision, paths: {
                    path: old_manifest for path in paths
                },
            )

    def test_launch_journal_is_fully_bound_and_rejects_each_artifact_tamper(self):
        with tempfile.TemporaryDirectory(prefix="v9-launch-valid-") as directory:
            paths, launch, tracked = _launch_journal_fixture(Path(directory))
            C._validate_launch(launch, paths)
            C._validate_launch_artifacts(paths, launch, tracked)
            receipt_raw = _write_json(paths.launch_receipt, launch)
            self.assertFalse(receipt_raw.endswith(b"\n"))
            C._read_json(
                paths.launch_receipt, "launch receipt",
                expected_mode=0o400, expected_uid=os.getuid(),
            )
            paths.launch_receipt.chmod(0o600)
            paths.launch_receipt.write_bytes(receipt_raw + b"\n")
            paths.launch_receipt.chmod(0o400)
            with self.assertRaisesRegex(C.SourceConsumerError, "canonical"):
                C._read_json(
                    paths.launch_receipt, "launch receipt",
                    expected_mode=0o400, expected_uid=os.getuid(),
                )

        with tempfile.TemporaryDirectory(prefix="v9-launch-intent-") as directory:
            paths, launch, tracked = _launch_journal_fixture(Path(directory))
            intent = C._read_json(paths.launch_intent, "intent")[1]
            intent["array_mapping"]["rule"] = "candidate reuse is permitted"
            _replace_json(paths.launch_intent, intent)
            with self.assertRaisesRegex(C.SourceConsumerError, "launch-intent"):
                C._validate_launch_artifacts(paths, launch, tracked)

        with tempfile.TemporaryDirectory(prefix="v9-launch-capture-") as directory:
            paths, launch, tracked = _launch_journal_fixture(Path(directory))
            paths.sbatch_stdout.chmod(0o600)
            paths.sbatch_stdout.write_bytes(b"999\n")
            paths.sbatch_stdout.chmod(0o400)
            with self.assertRaisesRegex(C.SourceConsumerError, "capture"):
                C._validate_launch_artifacts(paths, launch, tracked)

        with tempfile.TemporaryDirectory(prefix="v9-launch-result-") as directory:
            paths, launch, tracked = _launch_journal_fixture(Path(directory))
            result = C._read_json(paths.sbatch_result, "result")[1]
            result["raw_streams_preserved"] = False
            result_raw = _replace_json(paths.sbatch_result, result)
            launch["sbatch_result_sha256"] = hashlib.sha256(result_raw).hexdigest()
            with self.assertRaisesRegex(C.SourceConsumerError, "sbatch result"):
                C._validate_launch_artifacts(paths, launch, tracked)

    def test_launch_journal_replays_acceptance_and_recovery_correlation(self):
        with tempfile.TemporaryDirectory(prefix="v9-launch-nonzero-") as directory:
            paths, launch, tracked = _launch_journal_fixture(
                Path(directory), returncode=1,
            )
            C._validate_launch(launch, paths)
            with self.assertRaisesRegex(C.SourceConsumerError, "unauthorized"):
                C._validate_launch_artifacts(paths, launch, tracked)

        with tempfile.TemporaryDirectory(prefix="v9-launch-recovered-") as directory:
            paths, launch, tracked = _launch_journal_fixture(
                Path(directory), recovered=True, returncode=1,
            )
            C._validate_launch(launch, paths)
            C._validate_launch_artifacts(paths, launch, tracked)
            changed = copy.deepcopy(launch)
            changed["recovery_evidence"]["uncertain_stdout_sha256"] = "0" * 64
            C._validate_launch(changed, paths)
            with self.assertRaisesRegex(C.SourceConsumerError, "uncertain stdout"):
                C._validate_launch_artifacts(paths, changed, tracked)
            changed = copy.deepcopy(launch)
            changed["recovery_evidence"]["no_resubmission"] = False
            with self.assertRaisesRegex(C.SourceConsumerError, "recovery"):
                C._validate_launch(changed, paths)

        with tempfile.TemporaryDirectory(prefix="v9-launch-retained-") as directory:
            paths, launch, tracked = _launch_journal_fixture(
                Path(directory), recovered=True,
            )
            C._validate_launch(launch, paths)
            C._validate_launch_artifacts(paths, launch, tracked)

    def test_completed_artifact_namespace_is_exact_private_and_stable(self):
        with tempfile.TemporaryDirectory(prefix="v9-artifact-tree-") as directory:
            paths, launch, _tracked = _launch_journal_fixture(Path(directory))
            for name in C.REQUIRED_ARTIFACT_FILENAMES:
                path = paths.artifact_dir / name
                if not path.exists():
                    path.write_bytes(b"fixture")
                    path.chmod(0o400)
            C._validate_artifact_namespace(paths, launch)

            extra = paths.artifact_dir / "source-audit-reused-v8.json"
            extra.write_bytes(b"old")
            extra.chmod(0o400)
            with self.assertRaisesRegex(C.SourceConsumerError, "namespace"):
                C._validate_artifact_namespace(paths, launch)
            extra.unlink()

            victim = paths.attestation_stage
            victim.unlink()
            os.symlink(paths.launch_intent, victim)
            with self.assertRaisesRegex(C.SourceConsumerError, "identity"):
                C._validate_artifact_namespace(paths, launch)

    def test_api_requires_a_distinct_exact_seal_revision(self):
        with self.assertRaises(TypeError):
            C.load_authorized_confirmation(snapshot_reader=lambda *_: {})
        launch = {"repository_commit_id": "b" * 40}
        reader = mock.Mock()
        with (
            mock.patch.object(C, "_read_json", return_value=(b"{}", launch)),
            mock.patch.object(C, "_validate_launch"),
            self.assertRaisesRegex(C.SourceConsumerError, "distinct exact 40-hex"),
        ):
            C.load_authorized_confirmation(
                snapshot_reader=reader, seal_revision="b" * 40,
            )
        reader.assert_not_called()

    def test_committed_seal_binds_artifacts_and_unchanged_source_closure(self):
        scenarios = (
            "accepted", "missing-artifact", "mutated-artifact",
            "changed-source", "live-artifact-race",
            "post-semantic-matching-seal",
        )
        for scenario in scenarios:
            with (
                self.subTest(scenario=scenario),
                tempfile.TemporaryDirectory(
                    prefix="v9-committed-seal-",
                ) as directory,
            ):
                root = Path(directory)
                paths, launch, tracked = _launch_journal_fixture(root)
                for name in C.REQUIRED_ARTIFACT_FILENAMES:
                    path = paths.artifact_dir / name
                    if not path.exists():
                        path.write_bytes(("artifact:" + name).encode("ascii"))
                        path.chmod(0o400)
                with mock.patch.object(C, "REPO", root):
                    artifact_paths = [
                        C._repo_relative(
                            paths.artifact_dir / name, "fixture artifact",
                        )
                        for name in C.REQUIRED_ARTIFACT_FILENAMES
                    ]
                    source_paths = [
                        C.CODE_MANIFEST_RELATIVE, *C.CODE_MANIFEST_FILES,
                    ]
                    prelaunch = {
                        C.CODE_MANIFEST_RELATIVE: b"manifest",
                        **{
                            relative: relative.encode("ascii")
                            for relative in C.CODE_MANIFEST_FILES
                        },
                    }
                    sealed = {
                        relative: (paths.artifact_dir / Path(relative).name).read_bytes()
                        for relative in artifact_paths
                    }
                    consumed_artifacts = {
                        name: (paths.artifact_dir / name).read_bytes()
                        for name in C.REQUIRED_ARTIFACT_FILENAMES
                    }
                    if scenario == "post-semantic-matching-seal":
                        target = paths.artifact_dir / Path(artifact_paths[0]).name
                        target.chmod(0o600)
                        target.write_bytes(b"post-semantic committed mutation")
                        target.chmod(0o400)
                        sealed[artifact_paths[0]] = target.read_bytes()
                    sealed.update(prelaunch)

                    def snapshot(revision, requested):
                        available = (
                            sealed if revision == "c" * 40 else prelaunch
                        )
                        result = {path: available[path] for path in requested}
                        if revision == "c" * 40:
                            if scenario == "missing-artifact":
                                result.pop(artifact_paths[0])
                            elif scenario == "mutated-artifact":
                                result[artifact_paths[0]] = b"committed mutation"
                            elif scenario == "changed-source":
                                result[C.CODE_MANIFEST_FILES[0]] = b"source mutation"
                            elif scenario == "live-artifact-race":
                                target = paths.artifact_dir / Path(artifact_paths[0]).name
                                target.chmod(0o600)
                                target.write_bytes(b"live mutation")
                                target.chmod(0o400)
                        return result

                    if scenario == "accepted":
                        C._validate_committed_seal(
                            paths, launch, "c" * 40, snapshot, tracked,
                            consumed_artifacts,
                        )
                    else:
                        with self.assertRaises(C.SourceConsumerError):
                            C._validate_committed_seal(
                                paths, launch, "c" * 40, snapshot, tracked,
                                consumed_artifacts,
                            )

    def test_inventory_source_identity_is_independently_recomputed(self):
        records = [_source(0, "f0"), _source(1, "f1")]
        records[0].update({
            "is_shadow_family": True, "is_shadow_unrepresented": False,
            "is_all_prior_represented": True,
            "is_all_prior_unrepresented": False,
        })
        candidates = [{key: record[key] for key in C.SOURCE_KEYS}
                      for record in records]
        aliases = [{
            "problem_sha256": record["problem_sha256"],
            "canonical": candidates[index], "aliases": record["aliases"],
        } for index, record in enumerate(records)]
        digests = {
            "candidate_records": C._digest(candidates),
            "alias_groups": C._digest(sorted(
                aliases, key=lambda item: item["problem_sha256"],
            )),
            "family_map": _sha("family-map"),
        }
        inventory = {
            "schema": C.INVENTORY_SCHEMA,
            "benchmark_revision": C.BENCHMARK_REVISION,
            "cost_manifest_sha256": C.COST_MANIFEST_SHA256,
            "shadow_attestation_sha256": C.SHADOW_ATTESTATION_SHA256,
            "candidate_records_sha256": digests["candidate_records"],
            "alias_groups_sha256": digests["alias_groups"],
            "inventory_digests": digests,
            "counts": {
                "candidates": 2, "families": 2, "source_aliases": 2,
                "discarded_aliases": 0, "prior_identity_overlap": 0,
                "prior_problem_hash_overlap": 0,
            },
            "shadow_families": ["f0"],
            "all_prior_families": ["f0"],
            "all_prior_unrepresented_families": ["f1"],
            "records_sha256": C._digest(records),
            "records": records,
        }
        patches = {
            "CANDIDATE_COUNT": 2,
            "CANDIDATE_RECORDS_SHA256": digests["candidate_records"],
            "ALIAS_GROUPS_SHA256": digests["alias_groups"],
            "FAMILY_MAP_SHA256": digests["family_map"],
            "INVENTORY_DIGESTS_SHA256": C._digest(digests),
            "SHADOW_FAMILY_SEQUENCE_SHA256": C._digest(["f0"]),
            "ALL_PRIOR_FAMILY_SEQUENCE_SHA256": C._digest(["f0"]),
            "ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256": C._digest(["f1"]),
            "EXPECTED_FAMILIES": 2,
            "EXPECTED_REPRESENTED_SHADOW_FAMILIES": 1,
            "EXPECTED_SHADOW_UNREPRESENTED_FAMILIES": 1,
            "EXPECTED_REPRESENTED_ALL_PRIOR_FAMILIES": 1,
            "EXPECTED_ALL_PRIOR_UNREPRESENTED_FAMILIES": 1,
            "EXPECTED_DISCARDED_ALIASES": 0,
        }
        with ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(C, name, value))
            self.assertEqual(C._validate_inventory(inventory), records)
            changed = copy.deepcopy(inventory)
            changed["records"][0]["problem_sha256"] = _sha("forged")
            changed["records_sha256"] = C._digest(changed["records"])
            with self.assertRaises(C.SourceConsumerError):
                C._validate_inventory(changed)

    def test_canonical_reader_rejects_noncanonical_duplicate_and_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            valid = root / "valid.json"
            value = {"a": 1, "b": 2}
            _write_json(valid, value)
            self.assertEqual(C._read_json(valid, "fixture")[1], value)

            noncanonical = root / "noncanonical.json"
            noncanonical.write_bytes(b'{"b": 2, "a": 1}\n')
            with self.assertRaises(C.SourceConsumerError):
                C._read_json(noncanonical, "fixture")

            duplicate = root / "duplicate.json"
            duplicate.write_bytes(b'{"a":1,"a":1}\n')
            with self.assertRaisesRegex(C.SourceConsumerError, "duplicate"):
                C._read_json(duplicate, "fixture")

            link = root / "link.json"
            os.symlink(valid, link)
            with self.assertRaisesRegex(C.SourceConsumerError, "regular"):
                C._read_json(link, "fixture")

    def test_outcome_taxonomy_and_resource_indeterminacy_are_fail_closed(self):
        source = _source(0)
        for outcome, kind in (
            ("success", "memory"),
            ("input-rejected", "memory"),
            ("resource-excluded", "memory"),
            ("resource-excluded", "time"),
        ):
            task = _task(source, outcome, kind)
            C._validate_task(task, source, 0)
        resource = _task(source, "resource-excluded", "memory")
        resource["supported"] = False
        with self.assertRaisesRegex(C.SourceConsumerError, "classification"):
            C._validate_task(resource, source, 0)
        resource = _task(source, "resource-excluded", "time")
        resource["eligible_for_cohort"] = True
        with self.assertRaisesRegex(C.SourceConsumerError, "classification"):
            C._validate_task(resource, source, 0)
        resource = _task(source, "resource-excluded", "time")
        resource["process_returncode"] = 20
        with self.assertRaisesRegex(C.SourceConsumerError, "resource exclusion"):
            C._validate_task(resource, source, 0)

    def test_candidate_resource_isolation_snapshot_stream_and_sas_are_exact(self):
        source = _source(0)
        C._validate_task(_task(source), source, 0)
        mutations = []

        changed = _task(source)
        changed["resource_contract"]["libseccomp_sha256"] = "0" * 64
        changed["resource_contract_sha256"] = C._digest(
            changed["resource_contract"]
        )
        mutations.append(changed)

        changed = _task(source)
        changed["child_limit_attestation"]["seccomp_filters"] = 0
        changed["parent_isolation_observation"]["seccomp_filters"] = 0
        mutations.append(changed)

        changed = _task(source)
        changed["parent_isolation_observation"][
            "process_creation_syscalls_denied"
        ] = list(C.DENIED_PROCESS_SYSCALLS[:-1])
        mutations.append(changed)

        changed = _task(source)
        changed["source_snapshot"]["files"][0]["bytes"] = 0
        changed["source_snapshot"]["files"][0]["source_identity"]["size"] = 0
        changed["source_snapshot"]["files"][0][
            "snapshot_identity_before"
        ]["size"] = 0
        changed["source_snapshot"]["files"][0][
            "snapshot_identity_after"
        ]["size"] = 0
        mutations.append(changed)

        changed = _task(source)
        changed["stdout"]["tail_bytes"] += 1
        mutations.append(changed)

        changed = _task(source)
        changed["sas_bytes"] = 0
        mutations.append(changed)

        changed = _task(source)
        changed["sas"]["min_operator_cost"] = 2
        changed["sas"]["max_operator_cost"] = 1
        mutations.append(changed)

        for changed in mutations:
            with self.subTest(changed=changed):
                with self.assertRaises(C.SourceConsumerError):
                    C._validate_task(changed, source, 0)

    def test_old_or_reused_origin_is_rejected(self):
        source = _source(0)
        for origin in ("v5-completed", "v8-repair", "v9-reused"):
            task = _task(source)
            task["candidate_origin"] = origin
            with self.assertRaisesRegex(C.SourceConsumerError, "candidate record"):
                C._validate_task(task, source, 0)

    def test_success_support_is_recomputed_not_trusted(self):
        source = _source(0)
        task = _task(source)
        task["sas"]["num_conditional_effects"] = 1
        with self.assertRaisesRegex(C.SourceConsumerError, "classification"):
            C._validate_task(task, source, 0)
        task["supported"] = False
        task["support_determined"] = True
        task["support_exclusion_reasons"] = ["serialized-conditional-effects"]
        task["eligible_for_cohort"] = False
        C._validate_task(task, source, 0)

    def test_split_is_replayed_with_floors_and_disjointness(self):
        records = []
        for index in range(16):
            family_index = index // 4
            source = _source(index, "f{}".format(family_index))
            source["is_shadow_family"] = family_index < 2
            source["is_shadow_unrepresented"] = family_index >= 2
            source["is_all_prior_represented"] = family_index < 3
            source["is_all_prior_unrepresented"] = family_index >= 3
            records.append(_task(source))
        patches = {
            "CONFIRMATION_TASKS": 4,
            "MIN_CONFIRMATION_FAMILIES": 4,
            "MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES": 2,
            "MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS": 1,
            "MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES": 1,
            "GUIDED_TARGET_TASKS": 8,
            "MAX_GUIDED_TASKS_PER_FAMILY": 3,
            "MIN_GUIDED_TASKS": 8,
            "MIN_GUIDED_FAMILIES": 4,
            "MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES": 2,
            "MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS": 1,
            "MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES": 1,
        }
        with ExitStack() as stack:
            for name, value in patches.items():
                stack.enter_context(mock.patch.object(C, name, value))
            gate, cohorts, confirmation, guided = C._expected_split(records)
            repeated = C._expected_split(records)
        self.assertTrue(gate["passed"])
        self.assertEqual((gate, cohorts), repeated[:2])
        self.assertEqual(len(confirmation), 4)
        self.assertEqual(len(guided), 8)
        self.assertFalse(
            {record["candidate_index"] for record in confirmation}
            & {record["candidate_index"] for record in guided}
        )
        self.assertTrue(gate["cohort_disjointness"]["passed"])

    def test_scheduler_requires_every_row_success_and_exact_resources(self):
        launch = {"submission_token": "a" * 24}
        rows = [{
            "array_task": index, "state": "COMPLETED", "exit_code": "0:0",
            "partition": "fat", "restarts": 0,
        } for index in range(2)]
        contracts = [{
            "array_task": index,
            "account": C.RESOURCE_PROFILE["account"],
            "partition": "fat", "qos": "normal", "req_cpus": 1,
            "req_mem": "26G", "time_limit": "01:10:00",
            "state": "COMPLETED", "exit_code": "0:0", "restarts": 0,
            "job_name": "pdb-source-v9-{}".format(launch["submission_token"]),
        } for index in range(2)]
        execution = {
            "scheduler_rows": rows,
            "scheduler_contract_rows": contracts,
            "scheduler_state_counts": {"COMPLETED": 2},
            "scheduler_rows_sha256": C._digest(rows),
            "scheduler_contract_rows_sha256": C._digest(contracts),
            "scheduler_gate_passed": True,
            "scheduler_gate_passed_before_payload_read": True,
        }
        with mock.patch.object(C, "SHARD_COUNT", 2):
            C._validate_scheduler(execution, launch)
            changed = copy.deepcopy(execution)
            changed["scheduler_rows"][1]["restarts"] = 1
            changed["scheduler_rows_sha256"] = C._digest(changed["scheduler_rows"])
            with self.assertRaisesRegex(C.SourceConsumerError, "scheduler row"):
                C._validate_scheduler(changed, launch)
            changed = copy.deepcopy(execution)
            changed["scheduler_contract_rows"][1]["req_mem"] = "2950G"
            changed["scheduler_contract_rows_sha256"] = C._digest(
                changed["scheduler_contract_rows"]
            )
            with self.assertRaisesRegex(C.SourceConsumerError, "resource contract"):
                C._validate_scheduler(changed, launch)

    def test_output_tree_rejects_extra_reordered_and_symlinked_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            data = root / "data"
            artifacts.mkdir()
            data.mkdir(mode=0o700)
            with (
                mock.patch.object(C, "SHARD_COUNT", 2),
                mock.patch.object(C, "CANDIDATE_COUNT", 4),
            ):
                paths = C.paths_for(artifacts, data)
                names = [paths.inventory.name]
                for index in range(2):
                    shard_dir = data / C.shard_name(index)
                    shard_dir.mkdir(mode=0o700)
                    names.extend((C.result_name(index), C.environment_name(index)))
                    for candidate_index in (2 * index, 2 * index + 1):
                        names.extend((
                            C.prefix_name(candidate_index, "stdout"),
                            C.prefix_name(candidate_index, "stderr"),
                        ))
                names.sort()
                file_records = []
                for name in names:
                    raw = _write_json(data / name, {"fixture": name})
                    file_records.append(C._file_record(name, raw))
                for index in range(2):
                    (data / C.shard_name(index)).chmod(0o500)
                info = data.lstat()
                root_identity = {
                    "path": str(data.resolve()), "canonical_path": str(data.resolve()),
                    "device": info.st_dev, "inode": info.st_ino,
                    "mode": "0700", "uid": info.st_uid, "gid": info.st_gid,
                }
                directories = [
                    {"path": C.shard_name(index), "mode": "0500"}
                    for index in range(2)
                ]
                tree = {
                    "schema": C.TREE_SCHEMA,
                    "root": str(data.resolve()),
                    "root_identity": root_identity,
                    "directories_count": 2,
                    "directories": directories,
                    "files_count": len(file_records),
                    "files": file_records,
                }
                tree["sha256"] = C._digest({
                    "root_identity": root_identity,
                    "directories": directories,
                    "files": file_records,
                })
                execution = {
                    "output_tree": tree, "output_tree_sha256": C._digest(tree),
                }
                launch = {"root_identities": {"output_dir": root_identity}}
                self.assertEqual(
                    sorted(C._validate_output_tree(paths, execution, launch)), names,
                )
                reordered = copy.deepcopy(execution)
                reordered["output_tree"]["files"].reverse()
                reordered["output_tree_sha256"] = C._digest(reordered["output_tree"])
                with self.assertRaisesRegex(C.SourceConsumerError, "file set"):
                    C._validate_output_tree(paths, reordered, launch)
                extra = data / "v8-repair.json"
                _write_json(extra, {"old": True})
                with self.assertRaisesRegex(C.SourceConsumerError, "live V9 output"):
                    C._validate_output_tree(paths, execution, launch)
                extra.unlink()
                target = paths.inventory
                saved = target.read_bytes()
                target.unlink()
                elsewhere = root / "elsewhere.json"
                elsewhere.write_bytes(saved)
                os.symlink(elsewhere, target)
                with self.assertRaises(C.SourceConsumerError):
                    C._validate_output_tree(paths, execution, launch)

    def test_stage_chain_is_exact_and_hash_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = root / "artifacts"
            data = root / "data"
            artifacts.mkdir()
            data.mkdir()
            paths = C.paths_for(artifacts, data)
            launch = {
                "job_id": "12345",
                "root_identities": {"roots": True},
            }
            launch_raw = C._canonical_json(launch)
            attestation_raw = C._canonical_json({"attestation": True})
            counts = {
                "candidates": 4, "translation_attempts": 4,
                "support_determinate": 4, "supported": 4,
                "unsupported": 0, "indeterminate": 0,
                "cohort_eligible": 4, "families": 2,
            }
            cohorts = {"confirmation_a": {}, "guided_b": {}}
            attestation = {
                "counts": counts,
                "split_rank_encoding": "rank-v1",
                "cohorts": cohorts,
            }
            rows = [{"array_task": index} for index in range(2)]
            contracts = [{"array_task": index} for index in range(2)]
            outcome_counts = {
                "input-rejected": 0, "resource-excluded": 0, "success": 4,
            }
            support_status_counts = {
                "indeterminate": 0, "supported": 4, "unsupported": 0,
            }
            execution = {
                "source_inventory_sha256": _sha("inventory"),
                "code_manifest_sha256": _sha("code"),
                "scheduler_rows": rows,
                "scheduler_rows_sha256": C._digest(rows),
                "scheduler_contract_rows": contracts,
                "scheduler_contract_rows_sha256": C._digest(contracts),
                "output_tree_sha256": _sha("tree"),
                "output_tree": {"tree": True},
                "environment_records_sha256": _sha("environments"),
                "attestation_records_sha256": _sha("records"),
                "outcome_counts": outcome_counts,
                "support_status_counts": support_status_counts,
                "support_exclusion_counts": {},
                "resource_exclusion_counts": {"memory": 0, "time": 0},
                "resource_exclusions_by_family": {},
                "cohorts_sha256": _sha("cohorts"),
                "prelaunch_gate": {"passed": True},
            }
            with (
                mock.patch.object(C, "SHARD_COUNT", 2),
                mock.patch.object(C, "CANDIDATE_COUNT", 4),
            ):
                root_kinds = {
                    "source-inventory-v9.json": "file",
                    C.shard_name(0): "directory", C.shard_name(1): "directory",
                }
                root_entries = [
                    {"name": name, "kind": root_kinds[name]}
                    for name in sorted(root_kinds)
                ]
                plan = {
                    "schema": C.SEAL_PLAN_SCHEMA,
                    "campaign": C.CAMPAIGN,
                    "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
                    "source_inventory_sha256": execution["source_inventory_sha256"],
                    "code_manifest_sha256": execution["code_manifest_sha256"],
                    "job_id": launch["job_id"],
                    "scheduler_rows": rows,
                    "scheduler_rows_sha256": execution["scheduler_rows_sha256"],
                    "scheduler_contract_rows": contracts,
                    "scheduler_contract_rows_sha256": execution["scheduler_contract_rows_sha256"],
                    "scheduler_gate_passed": True,
                    "scheduler_gate_passed_before_payload_read": True,
                    "scheduler_restarts": 0,
                    "logical_shards": 2, "candidates": 4,
                    "root_identities": launch["root_identities"],
                    "expected_output_root_entries": root_entries,
                    "expected_output_root_entries_sha256": C._digest(root_entries),
                    "log_payloads_read": 0,
                    "prior_runtime_payloads_read": 0,
                }
                seal_raw = _write_json(paths.seal_plan, plan)
                execution["seal_plan_sha256"] = hashlib.sha256(seal_raw).hexdigest()
                tree_stage = {
                    "schema": C.TREE_STAGE_SCHEMA,
                    "seal_plan_sha256": execution["seal_plan_sha256"],
                    "output_tree": execution["output_tree"],
                    "output_tree_sha256": execution["output_tree_sha256"],
                    "environment_records_sha256": execution["environment_records_sha256"],
                }
                tree_raw = _write_json(paths.tree_stage, tree_stage)
                execution["tree_stage_sha256"] = hashlib.sha256(tree_raw).hexdigest()
                census_stage = {
                    "schema": C.CENSUS_STAGE_SCHEMA,
                    "tree_stage_sha256": execution["tree_stage_sha256"],
                    "candidate_count": 4,
                    "candidate_indices_sha256": C._digest(list(range(4))),
                    "candidate_origin_counts": {C.FRESH_ORIGIN: 4},
                    "whole_campaign_rerun": True,
                    "prior_campaign_payloads_read": [],
                    "prior_campaign_shards_used": 0,
                    "records_sha256": execution["attestation_records_sha256"],
                    "counts": counts,
                    "outcome_counts": outcome_counts,
                    "support_status_counts": support_status_counts,
                    "support_exclusion_counts": {},
                    "resource_exclusion_counts": {"memory": 0, "time": 0},
                    "resource_exclusions_by_family": {},
                }
                census_raw = _write_json(paths.census_stage, census_stage)
                execution["census_stage_sha256"] = hashlib.sha256(census_raw).hexdigest()
                split_stage = {
                    "schema": C.SPLIT_STAGE_SCHEMA,
                    "census_stage_sha256": execution["census_stage_sha256"],
                    "split_seed": C.SPLIT_SEED,
                    "split_rank_encoding": attestation["split_rank_encoding"],
                    "cohorts": cohorts,
                    "cohorts_sha256": execution["cohorts_sha256"],
                    "prelaunch_gate": execution["prelaunch_gate"],
                    "confirmation_prelaunch_authorized": True,
                }
                split_raw = _write_json(paths.split_stage, split_stage)
                execution["split_stage_sha256"] = hashlib.sha256(split_raw).hexdigest()
                final_stage = {
                    "schema": C.ATTESTATION_STAGE_SCHEMA,
                    "split_stage_sha256": execution["split_stage_sha256"],
                    "attestation_path": str(paths.attestation),
                    "attestation_bytes": len(attestation_raw),
                    "attestation_sha256": hashlib.sha256(attestation_raw).hexdigest(),
                    "attestation_records_sha256": execution["attestation_records_sha256"],
                    "cohorts_sha256": execution["cohorts_sha256"],
                    "confirmation_prelaunch_authorized": True,
                }
                final_raw = _write_json(paths.attestation_stage, final_stage)
                execution["attestation_stage_sha256"] = hashlib.sha256(final_raw).hexdigest()
                C._validate_stages(
                    paths, execution, launch_raw, attestation_raw,
                    launch, attestation,
                )
                paths.census_stage.chmod(0o600)
                paths.census_stage.write_bytes(census_raw + b" ")
                with self.assertRaises(C.SourceConsumerError):
                    C._validate_stages(
                        paths, execution, launch_raw, attestation_raw,
                        launch, attestation,
                    )

    def test_scheduler_failure_stops_before_any_payload_read(self):
        paths = C.paths_for(Path("/tmp/v9-artifacts"), Path("/tmp/v9-data"))
        launch = {"fixture": "launch", "repository_commit_id": "b" * 40}
        execution = {"fixture": "execution"}
        with (
            mock.patch.object(C, "_read_json", side_effect=[
                (b"launch\n", launch), (b"execution\n", execution),
            ]),
            mock.patch.object(C, "_validate_launch"),
            mock.patch.object(
                C, "_validate_producer_snapshot", return_value=_tracked_manifest(),
            ),
            mock.patch.object(C, "_validate_launch_artifacts"),
            mock.patch.object(
                C, "_validate_execution_header",
                side_effect=C.SourceConsumerError("scheduler gate changed"),
            ),
            mock.patch.object(C, "_validate_output_tree") as tree_reader,
            self.assertRaisesRegex(C.SourceConsumerError, "scheduler gate"),
        ):
            C.load_authorized_confirmation(
                paths, snapshot_reader=lambda *_: {}, seal_revision="c" * 40,
            )
        tree_reader.assert_not_called()

    def test_public_api_returns_immutable_materialized_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = C.paths_for(root / "artifacts", root / "data")
            paths.tmpdir_root.mkdir()
            launch = {
                "source_inventory_sha256": hashlib.sha256(b"inventory\n").hexdigest(),
                "code_manifest_sha256": _sha("code"),
                "repository_commit_id": "b" * 40,
            }
            execution = {
                "confirmation_prelaunch_authorized": True,
                "source_audit_complete": True,
                "outcome_counts": {"success": 1},
            }
            source = _source(0)
            task = _task(source)
            attestation = {
                "confirmation_prelaunch_authorized": True,
                "outcome_counts": {"success": 1},
                "resource_exclusions_by_family": {},
            }
            file_map = {paths.inventory.name: {"fixture": True}}
            with (
                mock.patch.object(C, "_read_json", side_effect=[
                    (b"launch", launch), (b"execution", execution),
                    (b"attestation", attestation),
                ]),
                mock.patch.object(C, "_validate_launch"),
                mock.patch.object(
                    C, "_validate_producer_snapshot",
                    return_value=_tracked_manifest(),
                ),
                mock.patch.object(C, "_validate_launch_artifacts", return_value={
                    C.LAUNCH_INTENT_FILENAME: b"intent",
                    C.SBATCH_STDOUT_FILENAME: b"stdout",
                    C.SBATCH_STDERR_FILENAME: b"stderr",
                    C.SBATCH_RESULT_FILENAME: b"result",
                }),
                mock.patch.object(C, "_validate_execution_header"),
                mock.patch.object(C, "_validate_artifact_namespace"),
                mock.patch.object(
                    C, "_validate_output_tree", return_value=file_map,
                ),
                mock.patch.object(C, "_read_bound_json", return_value=(
                    b"inventory\n", {"records_sha256": _sha("records")},
                )),
                mock.patch.object(C, "_validate_inventory", return_value=[source]),
                mock.patch.object(
                    C, "_validate_shards_and_environments",
                    return_value=([task], []),
                ),
                mock.patch.object(
                    C, "_validate_attestation", return_value=([task], [task]),
                ),
                mock.patch.object(C, "_validate_stages", return_value={
                    C.SEAL_PLAN_FILENAME: b"plan",
                    C.TREE_STAGE_FILENAME: b"tree",
                    C.CENSUS_STAGE_FILENAME: b"census",
                    C.SPLIT_STAGE_FILENAME: b"split",
                    C.ATTESTATION_STAGE_FILENAME: b"final",
                }),
                mock.patch.object(C, "_validate_committed_seal"),
            ):
                authorized = C.load_authorized_confirmation(
                    paths, snapshot_reader=lambda *_: {},
                    seal_revision="c" * 40,
                )
        self.assertEqual(authorized.confirmation_a[0]["candidate_index"], 0)
        self.assertEqual(authorized.seal_repository_commit_id, "c" * 40)
        self.assertEqual(authorized.guided_b[0]["candidate_index"], 0)
        with self.assertRaises(TypeError):
            authorized.confirmation_a[0]["candidate_index"] = 1
        with self.assertRaises(TypeError):
            authorized.confirmation_a[0]["process_returncode"] = 7

    def test_resource_summary_reports_candidates_by_family(self):
        records = [
            _task(_source(0, "f0"), "resource-excluded", "memory"),
            _task(_source(1, "f0"), "resource-excluded", "time"),
            _task(_source(2, "f1"), "resource-excluded", "memory"),
            _task(_source(3, "f1"), "input-rejected"),
        ]
        summary = C._summaries(records)
        self.assertEqual(summary["outcome_counts"], {
            "input-rejected": 1, "resource-excluded": 3, "success": 0,
        })
        self.assertEqual(summary["support_status_counts"], {
            "indeterminate": 3, "supported": 0, "unsupported": 1,
        })
        self.assertEqual(summary["resource_exclusions_by_family"], {
            "f0": {"memory": 1, "time": 1, "total": 2},
            "f1": {"memory": 1, "time": 0, "total": 1},
        })


if __name__ == "__main__":
    unittest.main()
