#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_safe_io_v5 as TreeIO
import pdb_terminal_incidence_confirmation_source_consumer_v5 as C


def _root(path: Path, inode: int) -> dict:
    return {
        "path": str(path), "canonical_path": str(path), "uid": 1,
        "mode": "0700", "device": 2, "inode": inode,
    }


def _launch_pair() -> tuple[bytes, dict, dict]:
    token = "a" * 24
    intent = {key: None for key in C.INTENT_KEYS}
    intent.update({
        "schema": C.SCHEMA + "/campaign-v5/launch/intent",
        "campaign": "v5", "whole_campaign_rerun": True,
        "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "partition": "fat", "qos": "normal", "account": C.PLANNER_ACCOUNT,
        "array": "0-819", "array_throttle": 0,
        "array_tasks": C.ARRAY_TASKS, "tasks_per_array_task": 2,
        "candidates": C.CANDIDATES, "cpus_per_task": 1,
        "time_limit": C.TIME_LIMIT, "memory_per_cpu": C.MEMORY_PER_CPU,
        "task_timeout_seconds": C.TASK_TIMEOUT_SECONDS,
        "source_inventory_path": str(C.SOURCE_INVENTORY),
        "output_dir": str(C.OUTPUT_DIR), "tmpdir_root": str(C.TMP_ROOT),
        "candidate_attestation": str(C.CANDIDATE),
        "frozen_attestation": str(C.ATTESTATION),
        "scoped_repository_files": list(C.SCOPED_FILES),
        "slurm_submission_mode": "stdin", "slurm_path_argument": False,
        "submission_journal_contract": "exact sbatch options-only SubmitLine",
        "repository_commit_id": "b" * 40,
        "jj_executable": "/home/jendrik/bin/jj",
        "sbatch_executable": "/usr/bin/sbatch",
        "sacct_executable": "/usr/bin/sacct",
        "submission_environment": {
            "LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin",
        },
        "launch_root_identities": {
            "output_dir": _root(C.OUTPUT_DIR, 1),
            "tmpdir_root": _root(C.TMP_ROOT, 2),
        },
        "recorded_utc": "2026-09-01T00:00:00+00:00",
        "submission_token": token, "submit_command": C._expected_submit(token),
        "python_distributions": {}, "execution_environment": {},
    })
    for field in (
        "candidate_records_sha256", "alias_groups_sha256",
        "prior_identity_ledger_sha256", "prior_family_ledger_sha256",
        "prior_directory_family_map_sha256",
        "shadow_unrepresented_family_sequence_sha256",
        "all_prior_family_sequence_sha256",
        "all_prior_unrepresented_family_sequence_sha256",
        "source_inventory_sha256", "slurm_script_sha256",
        "slurm_stdin_sha256", "code_manifest_sha256", "launcher_sha256",
        "jj_executable_sha256", "sbatch_executable_sha256",
        "sacct_executable_sha256", "translator_source_sha256",
        "v4_infrastructure_diagnostic_sha256", "python_executable_sha256",
        "python_environment_sha256", "python_requirements_sha256",
    ):
        intent[field] = "c" * 64
    intent.update({
        "slurm_stdin_bytes": 10, "benchmark_revision": "d" * 40,
        "v4_infrastructure_diagnostic_path": str(
            C.ARTIFACT_DIR / "v4-infrastructure-failure-diagnostic.json"
        ),
        "v4_infrastructure_diagnostic": {}, "python_version": "3.12.13",
        "python_executable": "/pinned/python3.12",
    })
    raw = C._canonical_json_line(intent)
    launch = {
        "schema": C.SCHEMA + "/campaign-v5/launch",
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(raw).hexdigest(),
        "job_id": "12345",
    }
    return raw, intent, launch


class SharedV5ConsumerTest(unittest.TestCase):
    def test_launch_key_set_and_options_only_journal_are_exact(self):
        raw, intent, launch = _launch_pair()
        with mock.patch.object(C, "_validate_execution_environment"):
            C._validate_launch(raw, intent, launch)
            changed = dict(intent)
            changed["unsealed_extra"] = True
            changed_raw = C._canonical_json_line(changed)
            changed_launch = {
                "schema": C.SCHEMA + "/campaign-v5/launch",
                **{key: value for key, value in changed.items() if key != "schema"},
                "launch_intent_sha256": hashlib.sha256(changed_raw).hexdigest(),
                "job_id": "12345",
            }
            with self.assertRaisesRegex(C.SourceConsumerError, "launch/intent"):
                C._validate_launch(changed_raw, changed, changed_launch)
            changed = dict(intent)
            changed["submit_command"] = [*changed["submit_command"], "job.slurm"]
            with self.assertRaises(C.SourceConsumerError):
                C._validate_launch(raw, changed, launch)

    def test_code_manifest_requires_exact_closure_and_live_bytes(self):
        payloads = {
            relative: ("fixture:" + relative + "\n").encode("ascii")
            for relative in C.CODE_MANIFEST_FILES
        }
        manifest_raw = b"".join(
            hashlib.sha256(payloads[relative]).hexdigest().encode("ascii")
            + b"  " + relative.encode("ascii") + b"\n"
            for relative in C.CODE_MANIFEST_FILES
        )
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()

        def loaded(path, expected, label):
            del expected, label
            if path == C.CODE_MANIFEST:
                raw = manifest_raw
            else:
                raw = payloads[path.relative_to(C.REPO).as_posix()]
            return SafeIO.RegularFile(raw, hashlib.sha256(raw).hexdigest(), {})

        with mock.patch.object(C, "_read_file", side_effect=loaded):
            records = C._manifest({"code_manifest_sha256": manifest_sha})
        self.assertEqual(set(records), set(C.CODE_MANIFEST_FILES))
        bad = manifest_raw.rsplit(b"\n", 2)[0] + b"\n"
        with mock.patch.object(
            C, "_read_file",
            return_value=SafeIO.RegularFile(
                bad, hashlib.sha256(bad).hexdigest(), {}
            ),
        ), self.assertRaisesRegex(C.SourceConsumerError, "file set"):
            C._manifest({"code_manifest_sha256": hashlib.sha256(bad).hexdigest()})

    def test_current_slurm_source_has_the_frozen_normalized_contract(self):
        raw = C.SLURM_SCRIPT.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        assignment = next(
            line for line in raw.splitlines()
            if line.startswith(b"code_manifest_sha256=")
        )
        manifest_sha = assignment.split(b'"')[1].decode("ascii")
        self.assertEqual(
            C._slurm({
                "slurm_script_sha256": digest,
                "slurm_stdin_sha256": digest,
                "slurm_stdin_bytes": len(raw),
                "slurm_submission_mode": "stdin",
                "slurm_path_argument": False,
                "code_manifest_sha256": manifest_sha,
            }),
            digest,
        )

    def test_diagnostic_binds_bytes_schema_and_no_outcome_flags(self):
        path = C.ARTIFACT_DIR / "v4-infrastructure-failure-diagnostic.json"
        diagnostic = {key: None for key in C.DIAGNOSTIC_KEYS}
        diagnostic.update({
            "schema": C.SCHEMA + "/campaign-v5/v4-infrastructure-diagnostic",
            "successful_v4_shard_contents_inspected": False,
            "successful_v4_log_contents_inspected": False,
            "cancelled_v4_log_contents_inspected": False,
            "source_support_outcomes_used_for_v5_design": False,
            "full_rerun_decision": {
                "scope": "all-820-original-shards-and-1640-candidates",
                "whole_campaign_rerun": True, "reused_v1_shards": 0,
                "reused_v2_shards": 0, "reused_v3_shards": 0,
                "reused_v4_shards": 0,
            },
            "failure_classes": [
                "scheduler-out-of-memory", "translator-wallclock-timeout",
            ],
            "inspection_scope": "synthetic infrastructure-only evidence",
            "v4_scheduler_state_counts": {},
            "v4_source_inventory_sha256": "e" * 64,
        })
        manifest = {}
        for prefix, relative in (
            ("v4_launch_intent", "experiments/artifacts/"
             "pdb-terminal-incidence-confirmation-v4/"
             "source-audit-launch-intent-v4.json"),
            ("v4_launch_receipt", "experiments/artifacts/"
             "pdb-terminal-incidence-confirmation-v4/"
             "source-audit-launch-receipt-v4.json"),
            ("v4_code_manifest", "experiments/"
             "pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256"),
            ("v4_slurm_script", "experiments/"
             "pdb_terminal_incidence_confirmation_source_scan_v4.slurm"),
        ):
            diagnostic[prefix + "_path"] = str(C.REPO / relative)
            diagnostic[prefix + "_sha256"] = "d" * 64
            manifest[relative] = "d" * 64
        for field, digest_field in (
            ("v4_scheduler_rows", "v4_scheduler_rows_sha256"),
            ("v4_failure_logs", "v4_failure_logs_sha256"),
            ("v4_oom_scheduler_resource_rows",
             "v4_oom_scheduler_resource_rows_sha256"),
            ("v4_timeout_scheduler_resource_rows",
             "v4_timeout_scheduler_resource_rows_sha256"),
        ):
            diagnostic[field] = []
            diagnostic[digest_field] = hashlib.sha256(C._canonical_json([])).hexdigest()
        diagnostic["v4_job_id"] = "123"
        diagnostic["v4_cancelled_array_tasks"] = []
        diagnostic["v4_cancellation"] = None
        diagnostic["v4_out_of_memory_array_tasks"] = []
        diagnostic["v4_translator_timeout_array_tasks"] = []
        diagnostic["resource_amendment"] = {
            "temporary_storage": {
                "from": (
                    "project-backed per-candidate snapshots and per-task "
                    "temporary directories"
                ),
                "to": str(C.TMP_ROOT / "task-{array_job_id}-{array_task_id}"),
                "reason": (
                    "retain v4's project-backed isolation unchanged; the "
                    "classified v4 failure is memory exhaustion, not ENOSPC"
                ),
                "cleanup": "per-task EXIT trap using pinned rmdir only",
            },
            "memory_per_cpu": {
                "from": "1024G", "to": "2T", "factor": 2,
                "reason": (
                    "v4 scheduler OOM at 1 TiB; batch MaxRSS and MaxVMSize "
                    "are pinned above"
                ),
            },
            "task_timeout_seconds": {
                "from": 14400, "to": 28800, "factor": 2,
                "reason": (
                    "v4 translator exceeded its 14,400-second source limit; "
                    "task/log/accounting evidence is pinned above"
                ),
            },
            "time_limit": {
                "from": "08:20:00", "to": "16:40:00", "factor": 2,
                "reason": "preserve scheduler headroom for doubled source limit",
            },
        }
        diagnostic["scheduler_memory_geometry"] = {
            "fat_node_real_memory_mib": 3095813,
            "v5_request_memory_mib": 2048 * 1024,
            "maximum_v5_tasks_per_node_by_memory": 1,
            "array_throttle": 0,
            "interpretation": (
                "the unthrottled array leaves concurrency to Slurm; the "
                "memory request permits at most one v5 task per fat node"
            ),
        }
        raw = C._canonical_json_line(diagnostic)
        digest = hashlib.sha256(raw).hexdigest()
        launch = {
            "v4_infrastructure_diagnostic_path": str(path),
            "v4_infrastructure_diagnostic_sha256": digest,
            "v4_infrastructure_diagnostic": diagnostic,
            "source_inventory_sha256": diagnostic["v4_source_inventory_sha256"],
        }
        with mock.patch.object(C, "_read_json", return_value=(raw, diagnostic)):
            C._validate_diagnostic(launch, {
                **manifest, path.relative_to(C.REPO).as_posix(): digest
            })
            changed = dict(diagnostic)
            changed["source_support_outcomes_used_for_v5_design"] = True
            with self.assertRaisesRegex(C.SourceConsumerError, "no-outcome"):
                C._validate_diagnostic(
                    {**launch, "v4_infrastructure_diagnostic": changed},
                    {**manifest, path.relative_to(C.REPO).as_posix(): digest},
                )

    def test_execution_environment_checks_exact_schema_and_executables(self):
        _, _, launch = _launch_pair()
        tmp_template = str(C.TMP_ROOT / "task-{array_job_id}-{array_task_id}")
        environment = {
            "submission_export": "NONE", "slurm_export": "NONE",
            "unset_variables": ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"],
            "python_no_user_site": "1", "python_no_user_site_flag": 1,
            "python_dont_write_bytecode": "1",
            "python_dont_write_bytecode_flag": True,
            "tmpdir_root": str(C.TMP_ROOT), "tmpdir_template": tmp_template,
            "python_tempfile_directory_template": tmp_template,
            "python_pycache_prefix_template": tmp_template + "/pycache",
            "tmpdir_mode": "0700",
            "tmpdir_cleanup": "EXIT trap with pinned /usr/bin/rmdir; no recursion",
            "root_identity_policy": (
                "canonical absolute path; no direct/ancestor symlinks; mode 0700; "
                "launch uid/device/inode retained"
            ),
            "source_snapshot_policy": {
                "scope": "one domain/problem snapshot tree per candidate",
                "location": "inside the exact per-array-task TMPDIR",
                "directory_mode": "0700", "file_mode": "0400",
                "consumers": ["translator", "axiom_based normalization"],
                "verify_before_each_consumer": True,
                "verify_identity_and_sha256_after_use": True,
                "cleanup": "unlink exact files, then rmdir exact directories; no recursion",
            },
            "outer_python_flag": "-B", "path": "/usr/bin:/bin",
            "translator_child_environment": {
                "PATH": "/usr/bin:/bin", "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": tmp_template,
                "PYTHONPYCACHEPREFIX": tmp_template + "/pycache",
                "PYTHONPATH": str(C.REPO / "src"),
            },
            "python_command": str(
                C.SCRIPT_DIR / "data" / "pdb-terminal-incidence-shadow-venv"
                / "bin" / "python"
            ),
            "python_executable": "/pinned/python3.12",
            "python_executable_sha256": "c" * 64,
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
        launch["execution_environment"] = environment
        launch["python_executable"] = environment["python_executable"]
        launch["python_executable_sha256"] = environment[
            "python_executable_sha256"
        ]
        with mock.patch.object(C, "_executable_identity") as identity:
            C._validate_execution_environment(launch)
            self.assertEqual(identity.call_count, 7)
            launch["execution_environment"] = {**environment, "extra": True}
            with self.assertRaisesRegex(C.SourceConsumerError, "environment"):
                C._validate_execution_environment(launch)

    def test_output_tree_and_task_environment_manifest_are_replayed(self):
        _, _, launch = _launch_pair()
        launch["source_inventory_sha256"] = hashlib.sha256(
            b"source-inventory-v5.json"
        ).hexdigest()
        paths = sorted([
            "source-inventory-v5.json",
            *("shard-{:04d}-of-0820.json".format(i)
              for i in range(C.ARRAY_TASKS)),
            *("environment-{:04d}-of-0820.json".format(i)
              for i in range(C.ARRAY_TASKS)),
            *("slurm-{}_{}.out".format(launch["job_id"], i)
              for i in range(C.ARRAY_TASKS)),
        ])
        file_records = [{
            "path": path, "bytes": 0,
            "sha256": hashlib.sha256(path.encode("ascii")).hexdigest(),
        } for path in paths]
        inventory = next(
            record for record in file_records
            if record["path"] == "source-inventory-v5.json"
        )
        inventory["sha256"] = launch["source_inventory_sha256"]
        digest = hashlib.sha256()
        root = launch["launch_root_identities"]["output_dir"]
        digest.update(b"root-identity\0" + C._canonical_json(root))
        for record in file_records:
            digest.update(
                record["path"].encode("ascii") + b"\0"
                + bytes.fromhex(record["sha256"])
            )
        environment_records = []
        by_path = {record["path"]: record for record in file_records}
        for index in range(C.ARRAY_TASKS):
            environment_name = "environment-{:04d}-of-0820.json".format(index)
            shard_name = "shard-{:04d}-of-0820.json".format(index)
            tmpdir = C.TMP_ROOT / "task-{}-{}".format(launch["job_id"], index)
            environment_records.append({
                "array_task": index, "path": environment_name,
                "sha256": by_path[environment_name]["sha256"],
                "tmpdir": str(tmpdir),
                "tmpdir_identity": _root(tmpdir, 100 + index),
                "output_dir_identity": root,
                "shard_sha256": by_path[shard_name]["sha256"],
            })
        execution = {
            "original_output_tree": {
                "sha256": digest.hexdigest(), "root_identity": root,
                "files_count": len(file_records), "files": file_records,
            },
            "task_environment_manifest": {
                "schema": C.SCHEMA
                + "/campaign-v5/task-environment/v1/manifest/v1",
                "records": environment_records,
                "records_sha256": hashlib.sha256(
                    C._canonical_json(environment_records)
                ).hexdigest(),
                "tmpdir_root_identity": launch["launch_root_identities"][
                    "tmpdir_root"
                ],
                "output_dir_identity": root,
                "all_task_tmpdirs_removed_by_rmdir": True,
            },
        }
        tree = TreeIO.RegularTree(
            files=tuple(
                TreeIO.TreeFile(
                    record["path"], b"", record["sha256"], {"size": 0}
                )
                for record in file_records
            ),
            directories=(),
            root_identity={
                "device": root["device"], "inode": root["inode"],
                "uid": root["uid"], "mode": stat.S_IFDIR | 0o700,
            },
        )
        with mock.patch.object(C.TreeIO, "read_regular_tree", return_value=tree):
            C._validate_output_tree(execution, launch)
            execution["task_environment_manifest"]["records"][17][
                "shard_sha256"
            ] = "f" * 64
            execution["task_environment_manifest"]["records_sha256"] = (
                hashlib.sha256(C._canonical_json(
                    execution["task_environment_manifest"]["records"]
                )).hexdigest()
            )
            with self.assertRaisesRegex(C.SourceConsumerError, "record"):
                C._validate_output_tree(execution, launch)

    def test_two_revision_and_planner_authorization_contract_is_present(self):
        a_freeze = (C.SCRIPT_DIR / "freeze_pdb_terminal_incidence_confirmation_a.py").read_text()
        b_freeze = (C.SCRIPT_DIR / "freeze_pdb_terminal_incidence_confirmation_b.py").read_text()
        a_runner = (C.SCRIPT_DIR / "exp_pdb_terminal_incidence_confirmation_a.py").read_text()
        b_runner = (C.SCRIPT_DIR / "exp_pdb_terminal_incidence_confirmation_b.py").read_text()
        b_protocol = (C.SCRIPT_DIR / "pdb_terminal_incidence_confirmation_b_protocol.py").read_text()
        analyzer = (C.SCRIPT_DIR / "analyze_pdb_terminal_incidence_confirmation_a.py").read_text()
        for text in (a_freeze, b_freeze):
            self.assertIn("P.PLANNER_REVISION_REQUIRED", text)
            self.assertIn("freeze_repository_revision", text)
            self.assertGreaterEqual(text.count("JJ.require_ancestor"), 2)
        for text in (a_runner, b_runner):
            self.assertIn(
                "JJ.require_ancestor(REPO, P.FREEZE_REPOSITORY_REVISION, commit)",
                text,
            )
        self.assertIn('"planner_identity"', analyzer)
        self.assertIn("authorization.get(\"planner_identity\") != planner_identity", b_freeze)
        self.assertIn("live_authorization.get(\"planner_identity\")", b_protocol)


if __name__ == "__main__":
    unittest.main()
