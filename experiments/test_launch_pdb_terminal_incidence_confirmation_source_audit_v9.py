#!/usr/bin/env python3
"""Adversarial tests for the one-shot full-census V9 launcher."""

from __future__ import annotations

import ast
import hashlib
import os
import re
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import launch_pdb_terminal_incidence_confirmation_source_audit_v9 as Launch


def _minimal_rows(job_id="123", *, failed_index=None, restarts=0):
    lines = []
    for index in range(Launch.ARRAY_TASKS):
        state = "FAILED" if index == failed_index else "COMPLETED"
        exit_code = "1:0" if index == failed_index else "0:0"
        lines.append(
            "{}_{}|{}|{}|fat|{}".format(
                job_id, index, state, exit_code,
                restarts if index == 0 else 0,
            )
        )
    return "\n".join(lines) + "\n"


def _contract_rows(job_id="123", token="a" * 24, *, memory="26G"):
    name, _comment = Launch._submission_identity(token)
    return "\n".join(
        "{}_{}|naiss2025-5-561-cpu|fat|normal|1|{}|01:10:00|"
        "COMPLETED|0:0|0|{}".format(job_id, index, memory, name)
        for index in range(Launch.ARRAY_TASKS)
    ) + "\n"


def _row(index, *, state="COMPLETED", exit_code="0:0", restarts=0):
    return {
        "array_task": index, "state": state, "exit_code": exit_code,
        "partition": "fat", "restarts": restarts,
    }


class V9LauncherTest(unittest.TestCase):
    def test_schema_paths_and_zero_reuse_contract_are_fresh(self):
        self.assertEqual(Launch.SCHEMA, Launch.Source.SCHEMA)
        self.assertEqual(
            Launch.LAUNCH_SCHEMA,
            "symbolic-search-heuristics/universal-unseen-confirmation-"
            "source-audit/v1/campaign-v9/launch/v1",
        )
        self.assertEqual(Launch.ARTIFACT_DIR, Launch.Source.ARTIFACT_DIR)
        self.assertEqual(Launch.OUTPUT_DIR, Launch.Source.DEFAULT_OUTPUT)
        self.assertEqual(Launch.SOURCE_INVENTORY, Launch.Source.DEFAULT_INVENTORY)
        self.assertEqual(Launch.TMP_ROOT, Launch.Source.TMP_ROOT)
        self.assertEqual(Launch.LOG_ROOT, Launch.Source.LOG_ROOT)
        self.assertEqual(Launch.ZERO_PRIOR_PAYLOAD, {
            "prior_runtime_payloads_read": 0,
            "prior_runtime_payload_bytes_read": 0,
            "prior_runtime_payloads_reused": 0,
            "selective_recovery_authorized": False,
            "whole_campaign_fresh": True,
        })

    def test_exact_resource_profile_and_unthrottled_submit_command(self):
        self.assertEqual(Launch._resource_profile(), {
            "account": "naiss2025-5-561-cpu", "partition": "fat",
            "qos": "normal", "nodes": 1, "ntasks": 1,
            "cpus_per_task": 1, "mem": "26G", "time": "01:10:00",
            "array": "0-819", "array_throttle": None, "nice": 0,
            "requeue": False, "export": "NONE",
        })
        command = Launch._submit_command("a" * 24)
        expected_options = {
            "--parsable", "--export=NONE",
            "--job-name=pdb-source-v9-" + "a" * 24,
            "--comment=pdb-source-v9-" + "a" * 24,
            "--account=naiss2025-5-561-cpu", "--partition=fat",
            "--qos=normal", "--nodes=1", "--ntasks=1",
            "--cpus-per-task=1", "--mem=26G", "--time=01:10:00",
            "--array=0-819", "--nice=0", "--no-requeue",
            "--chdir=" + str(Launch.REPO),
            "--output={}/slurm-%A_%a.out".format(Launch.LOG_ROOT),
            "--error={}/slurm-%A_%a.err".format(Launch.LOG_ROOT),
        }
        self.assertEqual(command[0], "/usr/bin/sbatch")
        self.assertEqual(set(command[1:]), expected_options)
        self.assertEqual(len(command[1:]), len(expected_options))
        self.assertFalse(any(option.startswith("--array=0-819%") for option in command))
        for invalid in ("", "a" * 23, "g" * 24, True):
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._submit_command(invalid)

    def test_array_mapping_is_exact_full_census_bijection(self):
        mapping = Launch._array_mapping()
        pairs = [[2 * shard, 2 * shard + 1] for shard in range(820)]
        self.assertEqual(mapping["logical_shards"], 820)
        self.assertEqual(mapping["candidate_count"], 1640)
        self.assertEqual(mapping["candidate_index_first"], 0)
        self.assertEqual(mapping["candidate_index_last"], 1639)
        self.assertTrue(mapping["independent_of_prior_scheduler_rows"])
        self.assertEqual(mapping["candidate_pairs_sha256"], Launch._digest(pairs))
        self.assertEqual([item for pair in pairs for item in pair], list(range(1640)))

    def test_slurm_template_and_rendering_fix_every_resource(self):
        raw = Launch._slurm_template()
        text = raw.decode("ascii")
        directives = [
            line for line in text.splitlines() if line.startswith("#SBATCH")
        ]
        self.assertEqual(directives, [
            "#SBATCH --account=naiss2025-5-561-cpu",
            "#SBATCH --partition=fat", "#SBATCH --qos=normal",
            "#SBATCH --nodes=1", "#SBATCH --ntasks=1",
            "#SBATCH --cpus-per-task=1", "#SBATCH --mem=26G",
            "#SBATCH --time=01:10:00", "#SBATCH --array=0-819",
            "#SBATCH --output={}/slurm-%A_%a.out".format(Launch.LOG_ROOT),
            "#SBATCH --error={}/slurm-%A_%a.err".format(Launch.LOG_ROOT),
            "#SBATCH --export=NONE", "#SBATCH --nice=0",
            "#SBATCH --no-requeue",
        ])
        self.assertNotIn("#SBATCH --array=0-819%", text)
        self.assertIn('if test "${status}" -eq 0; then', text)
        self.assertIn('--tmp-root "${tmp_root}"', text)
        rendered = Launch._render_slurm("a" * 64, "b" * 64, "c" * 40)
        self.assertEqual(rendered.count(b"a" * 64), 1)
        self.assertEqual(rendered.count(b"b" * 64), 1)
        self.assertEqual(rendered.count(b"c" * 40), 1)
        for marker in (
            Launch.MANIFEST_PLACEHOLDER, Launch.INVENTORY_PLACEHOLDER,
            Launch.COMMIT_PLACEHOLDER,
        ):
            self.assertNotIn(marker, rendered)
        for bad in ("a" * 63, "A" * 64, True):
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._render_slurm(bad, "b" * 64, "c" * 40)

    def test_runtime_files_do_not_import_or_name_old_campaign_runtime(self):
        launcher = Path(Launch.__file__).read_text("utf-8")
        module = ast.parse(launcher)
        imports = []
        for statement in ast.walk(module):
            if isinstance(statement, ast.Import):
                imports.extend(alias.name for alias in statement.names)
            elif isinstance(statement, ast.ImportFrom) and statement.module:
                imports.append(statement.module)
        self.assertFalse(any(re.search(r"_v[1-8](?:\.|$)", name) for name in imports))
        self.assertFalse(re.search(
            r"source_(?:audit|scan|consumer)[^\n\"']*_v[1-8]", launcher
        ))
        slurm = Launch.SLURM_TEMPLATE.read_text("utf-8")
        self.assertFalse(re.search(
            r"source_(?:audit|scan|consumer)[^\n\"']*_v[1-8]", slurm
        ))

    def test_prepare_manifest_is_exact_and_exclusive(self):
        with tempfile.TemporaryDirectory(prefix="v9-manifest-") as tmp:
            repo = Path(tmp) / "repo"
            experiments = repo / "experiments"
            experiments.mkdir(parents=True)
            launcher = experiments / "launcher.py"
            slurm = experiments / "scan.slurm"
            audit = experiments / "audit_pdb_terminal_incidence_confirmation_sources_v9.py"
            launcher.write_bytes(b"launcher\n")
            slurm.write_bytes(b"slurm\n")
            audit.write_bytes(b"audit\n")
            paths = tuple(sorted({
                "experiments/launcher.py", "experiments/scan.slurm",
                "experiments/audit_pdb_terminal_incidence_confirmation_sources_v9.py",
            }))
            manifest = experiments / "manifest.sha256"
            artifact = experiments / "artifacts-v9"
            output = experiments / "output-v9"
            tmp_root = experiments / "tmp-v9"
            log_root = experiments / "logs-v9"
            with (
                mock.patch.object(Launch, "REPO", repo),
                mock.patch.object(Launch, "__file__", str(launcher)),
                mock.patch.object(Launch, "SLURM_TEMPLATE", slurm),
                mock.patch.object(Launch, "CODE_MANIFEST", manifest),
                mock.patch.object(Launch, "ARTIFACT_DIR", artifact),
                mock.patch.object(Launch, "OUTPUT_DIR", output),
                mock.patch.object(Launch, "TMP_ROOT", tmp_root),
                mock.patch.object(Launch, "LOG_ROOT", log_root),
                mock.patch.object(Launch.Source, "CODE_MANIFEST_FILES", paths),
            ):
                Launch.prepare_manifest()
                expected = b"".join(
                    hashlib.sha256((repo / relative).read_bytes()).hexdigest().encode("ascii")
                    + b"  " + relative.encode("ascii") + b"\n"
                    for relative in paths
                )
                self.assertEqual(manifest.read_bytes(), expected)
                self.assertEqual(stat.S_IMODE(manifest.stat().st_mode), 0o400)
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch.prepare_manifest()

    def test_exclusive_publication_rejects_collision_and_symlink_parent(self):
        with tempfile.TemporaryDirectory(prefix="v9-publish-") as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            real = repo / "real"
            real.mkdir()
            target = real / "record.json"
            with mock.patch.object(Launch, "REPO", repo):
                digest = Launch._exclusive_bytes(target, b"record\n", "fixture")
                self.assertEqual(digest, hashlib.sha256(b"record\n").hexdigest())
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o400)
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._exclusive_bytes(target, b"changed\n", "fixture")
                alias = repo / "alias"
                alias.symlink_to(real, target_is_directory=True)
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._exclusive_bytes(alias / "x", b"x", "symlink fixture")

    def test_capture_pair_retains_exact_descriptors_and_bytes(self):
        with tempfile.TemporaryDirectory(prefix="v9-capture-") as tmp:
            repo = Path(tmp) / "repo"
            artifact = repo / "artifacts"
            artifact.mkdir(parents=True)
            os.chmod(artifact, 0o700)
            stdout = artifact / "stdout.bin"
            stderr = artifact / "stderr.bin"
            with (
                mock.patch.object(Launch, "REPO", repo),
                mock.patch.object(Launch, "SBATCH_STDOUT", stdout),
                mock.patch.object(Launch, "SBATCH_STDERR", stderr),
            ):
                with Launch._CapturePair() as captures:
                    os.write(captures.stdout_fd, b"123;cluster\n")
                    os.write(captures.stderr_fd, b"warning\n")
                    records, payloads = captures.finalize()
                    self.assertEqual(payloads, {
                        "stdout": b"123;cluster\n", "stderr": b"warning\n",
                    })
                    self.assertEqual(records["stdout"]["bytes"], 12)
                    self.assertEqual(
                        records["stdout"]["initial_identity"]["inode"],
                        records["stdout"]["final_identity"]["inode"],
                    )
                self.assertEqual(stat.S_IMODE(stdout.stat().st_mode), 0o400)
                with self.assertRaises(Launch.LaunchAuditError):
                    with Launch._CapturePair():
                        pass

    def test_sbatch_result_binds_raw_captures_and_detects_mutation(self):
        with tempfile.TemporaryDirectory(prefix="v9-result-") as tmp:
            repo = Path(tmp) / "repo"
            artifact = repo / "artifacts"
            artifact.mkdir(parents=True)
            os.chmod(artifact, 0o700)
            stdout = artifact / "stdout.bin"
            stderr = artifact / "stderr.bin"
            result_path = artifact / "result.json"
            rendered = b"program"
            intent = {
                "slurm_program": {
                    "rendered_sha256": hashlib.sha256(rendered).hexdigest(),
                },
                "submit_command": ["/usr/bin/sbatch", "--parsable"],
            }
            intent_raw = Launch._canonical_json(intent)
            with (
                mock.patch.object(Launch, "REPO", repo),
                mock.patch.object(Launch, "SBATCH_STDOUT", stdout),
                mock.patch.object(Launch, "SBATCH_STDERR", stderr),
                mock.patch.object(Launch, "SBATCH_RESULT", result_path),
            ):
                with Launch._CapturePair() as captures:
                    intent["sbatch_capture_initial_identities"] = (
                        captures.initial_identities
                    )
                    intent_raw = Launch._canonical_json(intent)
                    os.write(captures.stdout_fd, b"456\n")
                    os.write(captures.stderr_fd, b"")
                    records, payloads = captures.finalize()
                    digest, result = Launch._publish_sbatch_result(
                        intent_raw, intent, rendered, records, payloads,
                        completed=subprocess.CompletedProcess([], 0),
                        error=None, recovered=False,
                    )
                self.assertEqual(result["parsed_job_id"], "456")
                self.assertTrue(result["accepted_by_launcher"])
                self.assertEqual(digest, hashlib.sha256(result_path.read_bytes()).hexdigest())
                loaded_sha, loaded = Launch._load_sbatch_result(intent_raw, intent)
                self.assertEqual(loaded_sha, digest)
                self.assertEqual(loaded, result)
                os.chmod(stdout, 0o600)
                with stdout.open("ab") as stream:
                    stream.write(b"tamper")
                os.chmod(stdout, 0o400)
                with self.assertRaises(Launch.LaunchAuditError):
                    Launch._load_sbatch_result(intent_raw, intent)

    def test_scheduler_rows_query_is_minimal_exact_and_restart_free(self):
        commands = []

        def fake_sacct(command):
            commands.append(command)
            return _minimal_rows()

        with mock.patch.object(Launch, "_sacct", side_effect=fake_sacct):
            rows = Launch._scheduler_rows("123")
        self.assertEqual(len(rows), 820)
        self.assertEqual(rows[0], _row(0))
        self.assertEqual(rows[-1], _row(819))
        self.assertEqual(commands[0][-1], (
            "--format=JobID,State,ExitCode,Partition,Restarts"
        ))
        self.assertNotIn("MaxRSS", " ".join(commands[0]))
        self.assertNotIn("NodeList", " ".join(commands[0]))
        for output in (
            _minimal_rows().replace("123_1|", "123_0|", 1),
            _minimal_rows().split("\n", 1)[1],
            _minimal_rows(restarts=1),
            _minimal_rows().replace("|fat|", "|cpu|", 1),
        ):
            with (
                self.subTest(output=output[:80]),
                mock.patch.object(Launch, "_sacct", return_value=output),
                self.assertRaises(Launch.LaunchAuditError),
            ):
                Launch._scheduler_rows("123")

    def test_resource_query_cannot_run_before_all_success(self):
        failed = [_row(index) for index in range(820)]
        failed[17] = _row(17, state="OUT_OF_MEMORY", exit_code="0:125")
        receipt = {"submission_token": "a" * 24}
        with (
            mock.patch.object(
                Launch, "_sacct",
                side_effect=AssertionError("detailed accounting was queried"),
            ),
            self.assertRaisesRegex(Launch.LaunchAuditError, "payload reads forbidden"),
        ):
            Launch._scheduler_contract_rows("123", receipt, failed)

        success = [_row(index) for index in range(820)]
        with mock.patch.object(
            Launch, "_sacct", return_value=_contract_rows(),
        ) as accounting:
            contracts = Launch._scheduler_contract_rows("123", receipt, success)
        self.assertEqual(len(contracts), 820)
        self.assertEqual(contracts[0]["req_mem"], "26G")
        self.assertEqual(accounting.call_args.args[0][-1], (
            "--format=JobID,Account,Partition,QOS,ReqCPUS,ReqMem,Timelimit,"
            "State,ExitCode,Restarts,JobName"
        ))
        with (
            mock.patch.object(
                Launch, "_sacct", return_value=_contract_rows(memory="25G"),
            ),
            self.assertRaises(Launch.LaunchAuditError),
        ):
            Launch._scheduler_contract_rows("123", receipt, success)

    def test_seal_calls_no_payload_reader_until_both_scheduler_gates_pass(self):
        receipt = {"job_id": "123", "submission_token": "a" * 24}
        success = [_row(index) for index in range(820)]
        failed = list(success)
        failed[9] = _row(9, state="TIMEOUT", exit_code="0:0")
        with (
            mock.patch.object(Launch, "_load_launch", return_value=("d" * 64, receipt)),
            mock.patch.object(Launch, "_scheduler_rows", return_value=failed),
            mock.patch.object(Launch, "_scheduler_contract_rows") as details,
            mock.patch.object(Launch.Source, "seal_campaign", create=True) as payload,
            self.assertRaises(Launch.LaunchAuditError),
        ):
            Launch.seal()
        details.assert_not_called()
        payload.assert_not_called()

        contracts = [{"array_task": index} for index in range(820)]
        events = []
        with (
            mock.patch.object(Launch, "_load_launch", return_value=("d" * 64, receipt)),
            mock.patch.object(
                Launch, "_scheduler_rows",
                side_effect=lambda _job: events.append("minimal") or success,
            ),
            mock.patch.object(
                Launch, "_scheduler_contract_rows",
                side_effect=lambda *_args: events.append("detailed") or contracts,
            ),
            mock.patch.object(
                Launch.Source, "seal_campaign", create=True,
                side_effect=lambda **_kwargs: events.append("payload"),
            ) as payload,
        ):
            Launch.seal()
        self.assertEqual(events, ["minimal", "detailed", "payload"])
        payload.assert_called_once_with(
            launch_sha="d" * 64, launch_receipt=receipt,
            scheduler_rows=success, scheduler_contract_rows=contracts,
        )

    def test_recovery_never_resubmits_and_prefers_retained_stdout(self):
        intent = {
            "code_manifest_sha256": "a" * 64,
            "source_inventory_sha256": "b" * 64,
            "repository_commit_id": "c" * 40,
        }
        result = {
            "parsed_job_id": "789",
            "stdout": {"sha256": "d" * 64},
            "accepted_by_launcher": True,
            "process_observation": {
                "kind": "completed-process", "returncode": 0,
            },
        }
        with tempfile.TemporaryDirectory(prefix="v9-recover-") as tmp:
            receipt_path = Path(tmp) / "receipt.json"
            with (
                mock.patch.object(Launch, "LAUNCH_RECEIPT", receipt_path),
                mock.patch.object(Launch, "SBATCH_RESULT", Path(tmp) / "result.json"),
                mock.patch.object(os.path, "lexists", side_effect=lambda path: path != receipt_path),
                mock.patch.object(Launch, "_load_intent_only", return_value=(b"intent", intent)),
                mock.patch.object(Launch, "_render_slurm", return_value=b"program"),
                mock.patch.object(Launch, "_load_sbatch_result", return_value=("e" * 64, result)),
                mock.patch.object(Launch, "_submission_journal") as journal,
                mock.patch.object(Launch, "_write_launch_receipt", return_value="f" * 64) as write,
                mock.patch.object(
                    Launch.subprocess, "run",
                    side_effect=AssertionError("recovery resubmitted"),
                ),
            ):
                Launch.recover_launch()
        journal.assert_not_called()
        evidence = write.call_args.kwargs["recovery_evidence"]
        self.assertEqual(evidence["source"], "retained-sbatch-stdout")
        self.assertEqual(evidence["job_id"], "789")
        self.assertTrue(evidence["accepted_returncode_zero"])
        self.assertTrue(evidence["no_resubmission"])

    def test_uncertain_recovery_requires_matching_submission_journal(self):
        intent = {"submission_token": "a" * 24}
        journal = {
            "source": "scheduler-submission-journal", "job_id": "789",
            "rows": [{"job_id": "789"}], "rows_sha256": "e" * 64,
            "no_resubmission": True,
        }
        observations = (
            {
                "kind": "controller-crash-returncode-unavailable",
                "returncode": None,
            },
            {"kind": "completed-process", "returncode": 1},
            {"kind": "os-error", "returncode": None},
        )
        for process in observations:
            result = {
                "parsed_job_id": "789", "accepted_by_launcher": False,
                "stdout": {"sha256": "d" * 64},
                "process_observation": process,
            }
            with (
                self.subTest(process=process),
                mock.patch.object(
                    Launch, "_submission_journal", return_value=journal,
                ) as queried,
            ):
                evidence = Launch._recovery_evidence(intent, result)
            queried.assert_called_once_with(intent)
            self.assertEqual(evidence["source"], "scheduler-submission-journal")
            self.assertEqual(evidence["uncertain_stdout_job_id"], "789")
            self.assertEqual(evidence["uncertain_stdout_sha256"], "d" * 64)
        result = {
            "parsed_job_id": "789", "accepted_by_launcher": False,
            "stdout": {"sha256": "d" * 64},
            "process_observation": observations[0],
        }
        with (
            mock.patch.object(
                Launch, "_submission_journal",
                return_value={**journal, "job_id": "790"},
            ),
            self.assertRaisesRegex(Launch.LaunchAuditError, "disagree"),
        ):
            Launch._recovery_evidence(intent, result)

    def test_missing_result_recovery_uses_journal_and_never_submits(self):
        intent = {
            "code_manifest_sha256": "a" * 64,
            "source_inventory_sha256": "b" * 64,
            "repository_commit_id": "c" * 40,
            "submission_token": "d" * 24,
        }
        unavailable = {
            "parsed_job_id": None, "accepted_by_launcher": False,
            "stdout": {"sha256": "e" * 64},
            "process_observation": {
                "kind": "controller-crash-returncode-unavailable",
                "returncode": None,
            },
        }
        journal = {
            "source": "scheduler-submission-journal", "job_id": "987",
            "rows": [{"job_id": "987"}], "rows_sha256": "f" * 64,
            "no_resubmission": True,
        }
        with tempfile.TemporaryDirectory(prefix="v9-recover-missing-") as tmp:
            receipt_path = Path(tmp) / "receipt.json"
            result_path = Path(tmp) / "result.json"
            with (
                mock.patch.object(Launch, "LAUNCH_RECEIPT", receipt_path),
                mock.patch.object(Launch, "SBATCH_RESULT", result_path),
                mock.patch.object(
                    Launch, "_load_intent_only", return_value=(b"intent", intent),
                ),
                mock.patch.object(Launch, "_render_slurm", return_value=b"program"),
                mock.patch.object(
                    Launch, "_capture_records_from_disk",
                    return_value=({"stdout": {}, "stderr": {}},
                                  {"stdout": b"", "stderr": b""}),
                ),
                mock.patch.object(
                    Launch, "_publish_sbatch_result",
                    return_value=("1" * 64, unavailable),
                ) as publish,
                mock.patch.object(
                    Launch, "_submission_journal", return_value=journal,
                ) as queried,
                mock.patch.object(
                    Launch, "_write_launch_receipt", return_value="2" * 64,
                ) as write,
                mock.patch.object(
                    Launch.subprocess, "run",
                    side_effect=AssertionError("recovery resubmitted"),
                ),
            ):
                Launch.recover_launch()
        publish.assert_called_once()
        queried.assert_called_once_with(intent)
        self.assertEqual(write.call_args.args[2], "987")
        self.assertEqual(
            write.call_args.kwargs["recovery_evidence"], journal,
        )

    def test_launch_submits_once_after_intent_and_retains_raw_result(self):
        events = []

        class Captures:
            stdout_fd = 101
            stderr_fd = 102
            initial_identities = {
                "stdout": {"inode": 1}, "stderr": {"inode": 2},
            }

            def __enter__(self):
                events.append("captures-open")
                return self

            def __exit__(self, *_args):
                events.append("captures-close")

            def verify_initial(self):
                events.append("captures-verified")

            def finalize(self):
                events.append("captures-finalized")
                return (
                    {"stdout": {"bytes": 4}, "stderr": {"bytes": 0}},
                    {"stdout": b"123\n", "stderr": b""},
                )

        def publish_intent(path, _value, _label):
            self.assertEqual(path, Launch.INTENT)
            events.append("intent")
            return "0" * 64

        def submit(command, **kwargs):
            events.append("sbatch")
            self.assertEqual(command, Launch._submit_command("a" * 24))
            self.assertEqual(kwargs["input"], b"rendered")
            self.assertEqual(kwargs["stdout"], 101)
            self.assertEqual(kwargs["stderr"], 102)
            self.assertFalse(kwargs["check"])
            return subprocess.CompletedProcess(command, 0)

        def publish_result(*_args, **_kwargs):
            events.append("result")
            return "1" * 64, {
                "accepted_by_launcher": True, "parsed_job_id": "123",
            }

        def write_receipt(*_args, **kwargs):
            events.append("receipt")
            self.assertFalse(kwargs["recovered"])
            self.assertIsNone(kwargs["recovery_evidence"])
            return "2" * 64

        root_identity = {
            "path": "/fixture", "canonical_path": "/fixture",
            "device": 1, "inode": 2, "mode": "0700", "uid": 1, "gid": 1,
        }
        with (
            mock.patch.object(Launch, "_assert_source_contract"),
            mock.patch.object(Launch, "_assert_namespace_empty"),
            mock.patch.object(
                Launch, "_load_code_manifest", return_value=("b" * 64, []),
            ),
            mock.patch.object(Launch, "_repository_commit", return_value="c" * 40),
            mock.patch.object(
                Launch, "_build_inventory", return_value=(b"inventory", "d" * 64),
            ),
            mock.patch.object(Launch, "_render_slurm", return_value=b"rendered"),
            mock.patch.object(
                Launch, "_create_private_directory", return_value=root_identity,
            ),
            mock.patch.object(
                Launch, "_exclusive_bytes",
                side_effect=lambda *_args: events.append("inventory") or "e" * 64,
            ),
            mock.patch.object(Launch, "_CapturePair", return_value=Captures()),
            mock.patch.object(Launch, "_exclusive_json", side_effect=publish_intent),
            mock.patch.object(Launch.secrets, "token_hex", return_value="a" * 24),
            mock.patch.object(Launch, "_executable_identity", return_value={}),
            mock.patch.object(Launch.subprocess, "run", side_effect=submit) as run,
            mock.patch.object(
                Launch, "_publish_sbatch_result", side_effect=publish_result,
            ),
            mock.patch.object(
                Launch, "_write_launch_receipt", side_effect=write_receipt,
            ) as receipt,
        ):
            Launch.launch()
        run.assert_called_once()
        receipt.assert_called_once()
        self.assertEqual(events, [
            "inventory", "captures-open", "intent", "captures-verified",
            "sbatch", "captures-finalized", "result", "captures-close",
            "receipt",
        ])

    def test_submission_journal_rejects_collision(self):
        token = "a" * 24
        name, comment = Launch._submission_identity(token)
        intent = {
            "submission_token": token,
            "recorded_utc": "2026-09-13T12:00:00+00:00",
            "submit_command": Launch._submit_command(token),
        }
        submit_line = " ".join(intent["submit_command"])
        valid = "321|{}|{}|{}\n".format(name, comment, submit_line)
        with mock.patch.object(Launch, "_sacct", return_value=valid):
            evidence = Launch._submission_journal(intent)
        self.assertEqual(evidence["job_id"], "321")
        self.assertTrue(evidence["no_resubmission"])
        collided = valid + "322|{}|{}|{}\n".format(name, comment, submit_line)
        with (
            mock.patch.object(Launch, "_sacct", return_value=collided),
            self.assertRaisesRegex(Launch.LaunchAuditError, "exactly one"),
        ):
            Launch._submission_journal(intent)

    def test_launch_receipt_exposes_consumer_contract(self):
        intent = {
            "submission_token": "a" * 24,
            "repository_commit_id": "b" * 40,
            "source_inventory_sha256": "c" * 64,
            "code_manifest_sha256": "d" * 64,
            "root_identities": {"root": "identity"},
            "slurm_program": {"rendered_sha256": "e" * 64},
        }
        receipt = Launch._receipt_value(
            b"intent\n", intent, "f" * 64, "123",
            recovered=False, recovery_evidence=None,
        )
        for key, value in Launch.ZERO_PRIOR_PAYLOAD.items():
            self.assertEqual(receipt[key], value)
        self.assertEqual(receipt["resource_profile"], Launch._resource_profile())
        self.assertEqual(receipt["campaign"], "v9-full-census")
        self.assertEqual(receipt["job_id"], "123")
        self.assertEqual(
            receipt["launch_intent_sha256"],
            hashlib.sha256(b"intent\n").hexdigest(),
        )

    def test_source_contract_and_inventory_cardinality_fail_closed(self):
        Launch._assert_source_contract()
        with (
            mock.patch.object(Launch.Source, "CANDIDATE_COUNT", 1639),
            self.assertRaises(Launch.LaunchAuditError),
        ):
            Launch._assert_source_contract()
        with (
            mock.patch.object(Launch.Source, "build_inventory_manifest", return_value={"x": 1}),
            mock.patch.object(Launch.Source, "validate_inventory_manifest", return_value=[{}]),
            self.assertRaises(Launch.LaunchAuditError),
        ):
            Launch._build_inventory()


if __name__ == "__main__":
    unittest.main()
