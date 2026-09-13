#!/usr/bin/env python3
"""Focused fail-closed tests for the V11 control plane."""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import launch_pdb_terminal_incidence_confirmation_source_audit_v11 as Launch


class V11LauncherTest(unittest.TestCase):
    def _private_root(self):
        return tempfile.TemporaryDirectory(prefix="v11-control-", dir=Launch.REPO)

    @staticmethod
    def _completed_row(
        job_id: str, name: str, index: int = 0, *, bare: bool = False,
    ) -> bytes:
        raw_id = job_id if bare else f"{job_id}_{index}"
        return (
            f"{raw_id}|{Launch.ACCOUNT}|fat|normal|1|26G|"
            f"01:10:00|COMPLETED|0:0|0|{name}\n"
        ).encode("ascii")

    @staticmethod
    def _receipt(job_id="123", accepted="2026-09-13T10:00:00+00:00"):
        return {
            "job_id": job_id,
            "accepted_utc": accepted,
            "submission_token": "a" * 24,
        }

    @staticmethod
    def _rewrite_json(path: Path, mutate) -> None:
        value = json.loads(path.read_text("ascii"))
        mutate(value)
        path.chmod(0o600)
        path.write_bytes(Launch._canonical_json(value))
        path.chmod(0o400)

    def _run_state_poll(
        self, *, poll_dir: Path, terminal: Path, receipt: dict,
        when: str, state: str,
    ) -> None:
        name = "pdb-source-v11-" + "a" * 24
        raw = self._completed_row("123", name).replace(
            b"|COMPLETED|", ("|{}|".format(state)).encode("ascii")
        )

        def run(command, **kwargs):
            os.write(kwargs["stdout"], raw)
            return subprocess.CompletedProcess(command, 0)

        with (
            mock.patch.object(Launch, "_executable_identity", return_value={}),
            mock.patch("subprocess.run", side_effect=run),
        ):
            Launch._poll_scheduler(
                campaign="v11-full-census", launch_sha="b" * 64,
                launch_receipt=receipt,
                launch_recorded_utc=receipt["accepted_utc"],
                poll_dir=poll_dir, terminal_path=terminal, task_count=1,
                job_name=name,
                terminal_schema=Launch.EXECUTION_SCHEMA + "/terminal/v1",
                poll_schema=Launch.POLL_SCHEMA,
                now=datetime.datetime.fromisoformat(when),
            )

    def test_profiles_are_exact_unthrottled_fat_contracts(self):
        self.assertEqual(Launch._resource_profile(), {
            "account": "naiss2025-5-561-cpu", "partition": "fat",
            "qos": "normal", "nodes": 1, "ntasks": 1,
            "cpus_per_task": 1, "mem": "26G", "time": "01:10:00",
            "array": "0-819", "array_throttle": None, "nice": 0,
            "requeue": False, "export": "NONE",
        })
        self.assertEqual(Launch._canary_resource_profile()["array"], "0-0")
        full = Launch._slurm_template()
        canary = Launch._compute_canary_template()
        self.assertNotIn(b"%", full.split(b"#SBATCH --array=", 1)[1].splitlines()[0])
        self.assertIn(b"#SBATCH --array=0-0", canary)
        for raw in (full, canary):
            self.assertIn(b"export LANG=\"C\"", raw)
            self.assertIn(b"export LC_ALL=\"C\"", raw)
            self.assertIn(b"#SBATCH --export=NONE", raw)
            self.assertIn(b"#SBATCH --no-requeue", raw)

    def test_controller_filesystem_probe_proves_lustre_name_and_magic(self):
        probe = Launch._lustre_filesystem_probe(Launch.REPO)
        self.assertEqual(probe["filesystem_type"], "lustre")
        self.assertEqual(probe["filesystem_magic"], "bd00bd0")
        self.assertEqual(probe["target_device"], Launch.REPO.stat().st_dev)
        self.assertEqual(probe["program"]["sha256"], Launch.STAT_COMMAND_SHA256)

        wrong = subprocess.CompletedProcess(
            probe["command"], 0, stdout=b"xfs|58465342\n", stderr=b"",
        )
        with (
            mock.patch.object(Launch, "_executable_identity", return_value={}),
            mock.patch("subprocess.run", return_value=wrong),
            self.assertRaisesRegex(Launch.LaunchAuditError, "not the expected"),
        ):
            Launch._lustre_filesystem_probe(Launch.REPO)

    def test_combined_query_produces_both_exact_row_projections(self):
        raw = self._completed_row("123", "pdb-source-v11-" + "a" * 24)
        rows, contracts = Launch._parse_combined_scheduler_rows(
            raw, job_id="123", task_count=1,
            job_name="pdb-source-v11-" + "a" * 24,
        )
        self.assertEqual(rows[0], {
            "array_task": 0, "state": "COMPLETED", "exit_code": "0:0",
            "partition": "fat", "restarts": 0,
        })
        self.assertEqual(contracts[0]["req_mem"], "26G")
        self.assertEqual(contracts[0]["req_cpus"], 1)
        with self.assertRaises(Launch.LaunchAuditError):
            Launch._parse_combined_scheduler_rows(
                raw.replace(b"|26G|", b"|25G|"), job_id="123", task_count=1,
                job_name="pdb-source-v11-" + "a" * 24,
            )

    def test_bare_job_id_is_only_single_element_array_task_zero(self):
        name = "pdb-source-v11-canary-" + "a" * 24
        raw = self._completed_row("123", name, bare=True)
        rows, contracts = Launch._parse_combined_scheduler_rows(
            raw, job_id="123", task_count=1, job_name=name,
        )
        self.assertEqual([row["array_task"] for row in rows], [0])
        self.assertEqual([row["array_task"] for row in contracts], [0])
        with self.assertRaisesRegex(
            Launch.LaunchAuditError, "resource contract",
        ):
            Launch._parse_combined_scheduler_rows(
                raw, job_id="123", task_count=2, job_name=name,
            )
        with self.assertRaisesRegex(
            Launch.LaunchAuditError, "resource contract",
        ):
            Launch._parse_combined_scheduler_rows(
                raw, job_id="124", task_count=1, job_name=name,
            )

    def test_first_poll_is_anchored_after_acceptance_and_makes_no_early_query(self):
        with self._private_root() as tmp:
            root = Path(tmp)
            poll_dir = root / "polls"
            poll_dir.mkdir(mode=0o700)
            poll_dir.chmod(0o700)
            receipt = self._receipt()
            with mock.patch("subprocess.run") as run:
                with self.assertRaisesRegex(Launch.LaunchAuditError, "once per hour"):
                    Launch._poll_scheduler(
                        campaign="v11-full-census", launch_sha="b" * 64,
                        launch_receipt=receipt,
                        launch_recorded_utc=receipt["accepted_utc"],
                        poll_dir=poll_dir, terminal_path=root / "terminal.json",
                        task_count=1,
                        job_name="pdb-source-v11-" + "a" * 24,
                        terminal_schema=Launch.EXECUTION_SCHEMA + "/terminal/v1",
                        poll_schema=Launch.POLL_SCHEMA,
                        now=datetime.datetime.fromisoformat(
                            "2026-09-13T10:59:59+00:00"
                        ),
                    )
            run.assert_not_called()
            self.assertEqual(list(poll_dir.iterdir()), [])

    def _run_terminal_poll(self, root: Path, *, bare: bool = False):
        poll_dir = root / "polls"
        poll_dir.mkdir(mode=0o700)
        poll_dir.chmod(0o700)
        terminal = root / "terminal.json"
        receipt = self._receipt()
        name = "pdb-source-v11-" + "a" * 24

        def run(command, **kwargs):
            self.assertTrue((poll_dir / "poll-0000-intent.json").exists())
            os.write(
                kwargs["stdout"],
                self._completed_row("123", name, bare=bare),
            )
            return subprocess.CompletedProcess(command, 0)

        with (
            mock.patch.object(Launch, "_executable_identity", return_value={}),
            mock.patch("subprocess.run", side_effect=run) as called,
        ):
            summary = Launch._poll_scheduler(
                campaign="v11-full-census", launch_sha="b" * 64,
                launch_receipt=receipt,
                launch_recorded_utc=receipt["accepted_utc"],
                poll_dir=poll_dir, terminal_path=terminal, task_count=1,
                job_name=name,
                terminal_schema=Launch.EXECUTION_SCHEMA + "/terminal/v1",
                poll_schema=Launch.POLL_SCHEMA,
                now=datetime.datetime.fromisoformat(
                    "2026-09-13T11:00:00+00:00"
                ),
            )
        self.assertEqual(called.call_count, 1)
        self.assertEqual(summary["scheduler_queries_this_poll"], 1)
        self.assertTrue(summary["all_success"])
        terminal_value = json.loads(terminal.read_text("ascii"))
        self.assertEqual(set(terminal_value), {
            "schema", "campaign", "job_id", "all_success",
            "state_counts", "terminal_poll_receipt_sha256",
        })
        return poll_dir, terminal, receipt

    def test_one_combined_query_creates_retained_terminal_gate(self):
        with self._private_root() as tmp:
            poll_dir, terminal, _receipt = self._run_terminal_poll(Path(tmp))
            self.assertTrue(terminal.exists())
            self.assertEqual(
                sorted(path.suffix for path in poll_dir.iterdir()),
                [".bin", ".bin", ".json", ".json", ".json"],
            )

    def test_bare_single_element_poll_survives_terminal_revalidation(self):
        with self._private_root() as tmp:
            root = Path(tmp)
            poll_dir, terminal, receipt = self._run_terminal_poll(
                root, bare=True,
            )
            terminal_sha, poll_sha, poll = Launch._retained_terminal_gate(
                terminal_path=terminal, poll_dir=poll_dir,
                expected_schema=Launch.EXECUTION_SCHEMA + "/terminal/v1",
                campaign="v11-full-census", job_id="123", task_count=1,
                job_name="pdb-source-v11-" + "a" * 24,
                poll_schema=Launch.POLL_SCHEMA, launch_sha="b" * 64,
                launch_accepted_utc=receipt["accepted_utc"],
            )
            self.assertRegex(terminal_sha, r"^[0-9a-f]{64}$")
            self.assertRegex(poll_sha, r"^[0-9a-f]{64}$")
            self.assertTrue(poll["all_success"])

    def test_next_poll_before_hour_is_zero_query(self):
        with self._private_root() as tmp:
            root = Path(tmp)
            poll_dir = root / "polls"
            poll_dir.mkdir(mode=0o700)
            poll_dir.chmod(0o700)
            receipt = self._receipt()
            name = "pdb-source-v11-" + "a" * 24
            pending = self._completed_row("123", name).replace(
                b"|COMPLETED|", b"|RUNNING|"
            )

            def run(command, **kwargs):
                os.write(kwargs["stdout"], pending)
                return subprocess.CompletedProcess(command, 0)

            with (
                mock.patch.object(Launch, "_executable_identity", return_value={}),
                mock.patch("subprocess.run", side_effect=run) as called,
            ):
                Launch._poll_scheduler(
                    campaign="v11-full-census", launch_sha="b" * 64,
                    launch_receipt=receipt,
                    launch_recorded_utc=receipt["accepted_utc"],
                    poll_dir=poll_dir, terminal_path=root / "terminal.json",
                    task_count=1, job_name=name,
                    terminal_schema=Launch.EXECUTION_SCHEMA + "/terminal/v1",
                    poll_schema=Launch.POLL_SCHEMA,
                    now=datetime.datetime.fromisoformat(
                        "2026-09-13T11:00:00+00:00"
                    ),
                )
                with self.assertRaisesRegex(
                    Launch.LaunchAuditError, "once per hour"
                ):
                    Launch._poll_scheduler(
                        campaign="v11-full-census", launch_sha="b" * 64,
                        launch_receipt=receipt,
                        launch_recorded_utc=receipt["accepted_utc"],
                        poll_dir=poll_dir,
                        terminal_path=root / "terminal.json", task_count=1,
                        job_name=name,
                        terminal_schema=(
                            Launch.EXECUTION_SCHEMA + "/terminal/v1"
                        ),
                        poll_schema=Launch.POLL_SCHEMA,
                        now=datetime.datetime.fromisoformat(
                            "2026-09-13T11:59:59+00:00"
                        ),
                    )
            self.assertEqual(called.call_count, 1)

    def test_canary_poll_wrapper_anchors_to_post_sbatch_acceptance(self):
        with self._private_root() as tmp:
            root = Path(tmp)
            poll_dir = root / "polls"
            poll_dir.mkdir(mode=0o700)
            poll_dir.chmod(0o700)
            receipt = self._receipt(accepted="2026-09-13T10:05:00+00:00")
            with (
                mock.patch.object(
                    Launch, "_load_compute_launch",
                    return_value=("b" * 64, receipt, receipt["accepted_utc"]),
                ),
                mock.patch.object(Launch, "COMPUTE_CANARY_POLL_DIR", poll_dir),
                mock.patch.object(
                    Launch, "COMPUTE_CANARY_TERMINAL_RECEIPT",
                    root / "terminal.json",
                ),
                mock.patch("subprocess.run") as called,
                self.assertRaisesRegex(Launch.LaunchAuditError, "once per hour"),
            ):
                Launch.poll_compute_canary(datetime.datetime.fromisoformat(
                    "2026-09-13T11:04:59+00:00"
                ))
            called.assert_not_called()

    def test_full_seal_reuses_terminal_poll_and_makes_zero_scheduler_queries(self):
        with self._private_root() as tmp:
            root = Path(tmp)
            poll_dir, terminal, receipt = self._run_terminal_poll(root)
            source_seal = mock.Mock()
            with (
                mock.patch.object(Launch, "FULL_POLL_DIR", poll_dir),
                mock.patch.object(Launch, "FULL_TERMINAL_RECEIPT", terminal),
                mock.patch.object(Launch, "ARRAY_TASKS", 1),
                mock.patch.object(
                    Launch, "_load_launch", return_value=("b" * 64, receipt)
                ),
                mock.patch.object(Launch.Source, "seal_campaign", source_seal),
                mock.patch("subprocess.run") as scheduler,
            ):
                Launch.seal()
            scheduler.assert_not_called()
            source_seal.assert_called_once()
            kwargs = source_seal.call_args.kwargs
            self.assertEqual(kwargs["scheduler_rows"][0]["state"], "COMPLETED")
            self.assertRegex(kwargs["terminal_poll_receipt_sha256"], r"^[0-9a-f]{64}$")

    def test_forged_prior_receipt_cannot_advance_next_query_cadence(self):
        with self._private_root() as tmp:
            root = Path(tmp)
            poll_dir = root / "polls"
            poll_dir.mkdir(mode=0o700)
            poll_dir.chmod(0o700)
            terminal = root / "terminal.json"
            receipt = self._receipt()
            self._run_state_poll(
                poll_dir=poll_dir, terminal=terminal, receipt=receipt,
                when="2026-09-13T11:00:00+00:00", state="RUNNING",
            )
            prior = poll_dir / "poll-0000-receipt.json"
            self._rewrite_json(
                prior,
                lambda value: value.__setitem__(
                    "recorded_utc", "2026-09-13T10:00:00+00:00"
                ),
            )
            with (
                mock.patch("subprocess.run") as query,
                self.assertRaisesRegex(Launch.LaunchAuditError, "retained poll"),
            ):
                Launch._poll_scheduler(
                    campaign="v11-full-census", launch_sha="b" * 64,
                    launch_receipt=receipt,
                    launch_recorded_utc=receipt["accepted_utc"],
                    poll_dir=poll_dir, terminal_path=terminal, task_count=1,
                    job_name="pdb-source-v11-" + "a" * 24,
                    terminal_schema=Launch.EXECUTION_SCHEMA + "/terminal/v1",
                    poll_schema=Launch.POLL_SCHEMA,
                    now=datetime.datetime.fromisoformat(
                        "2026-09-13T11:01:00+00:00"
                    ),
                )
            query.assert_not_called()

    def test_every_prior_attempt_is_revalidated_before_terminal_gate(self):
        with self._private_root() as tmp:
            root = Path(tmp)
            poll_dir = root / "polls"
            poll_dir.mkdir(mode=0o700)
            poll_dir.chmod(0o700)
            terminal = root / "terminal.json"
            receipt = self._receipt()
            self._run_state_poll(
                poll_dir=poll_dir, terminal=terminal, receipt=receipt,
                when="2026-09-13T11:00:00+00:00", state="RUNNING",
            )
            self._run_state_poll(
                poll_dir=poll_dir, terminal=terminal, receipt=receipt,
                when="2026-09-13T12:00:00+00:00", state="COMPLETED",
            )
            self._rewrite_json(
                poll_dir / "poll-0000-receipt.json",
                lambda value: value["state_counts"].__setitem__("RUNNING", 2),
            )
            with self.assertRaisesRegex(
                Launch.LaunchAuditError, "retained poll receipt"
            ):
                Launch._retained_terminal_gate(
                    terminal_path=terminal, poll_dir=poll_dir,
                    expected_schema=Launch.EXECUTION_SCHEMA + "/terminal/v1",
                    campaign="v11-full-census", job_id="123", task_count=1,
                    job_name="pdb-source-v11-" + "a" * 24,
                    poll_schema=Launch.POLL_SCHEMA, launch_sha="b" * 64,
                    launch_accepted_utc=receipt["accepted_utc"],
                )

    def test_corrupt_raw_result_or_receipt_cannot_recover_terminal(self):
        mutations = ("stdout", "result", "receipt", "mode")
        for target in mutations:
            with self.subTest(target=target), self._private_root() as tmp:
                root = Path(tmp)
                poll_dir, terminal, receipt = self._run_terminal_poll(root)
                terminal.unlink()
                if target == "stdout":
                    path = poll_dir / "poll-0000-stdout.bin"
                    path.chmod(0o600)
                    path.write_bytes(path.read_bytes() + b"x")
                    path.chmod(0o400)
                elif target == "result":
                    self._rewrite_json(
                        poll_dir / "poll-0000-result.json",
                        lambda value: value.__setitem__(
                            "command_sha256", "0" * 64
                        ),
                    )
                elif target == "receipt":
                    self._rewrite_json(
                        poll_dir / "poll-0000-receipt.json",
                        lambda value: value.__setitem__(
                            "stdout_sha256", "0" * 64
                        ),
                    )
                else:
                    (poll_dir / "poll-0000-receipt.json").chmod(0o600)
                with (
                    mock.patch("subprocess.run") as query,
                    self.assertRaises(Launch.LaunchAuditError),
                ):
                    Launch._poll_scheduler(
                        campaign="v11-full-census", launch_sha="b" * 64,
                        launch_receipt=receipt,
                        launch_recorded_utc=receipt["accepted_utc"],
                        poll_dir=poll_dir, terminal_path=terminal, task_count=1,
                        job_name="pdb-source-v11-" + "a" * 24,
                        terminal_schema=(
                            Launch.EXECUTION_SCHEMA + "/terminal/v1"
                        ),
                        poll_schema=Launch.POLL_SCHEMA,
                        now=datetime.datetime.fromisoformat(
                            "2026-09-13T12:00:00+00:00"
                        ),
                    )
                query.assert_not_called()
                self.assertFalse(terminal.exists())

    def test_stranded_post_intent_waits_hour_then_gets_zero_query_abandonment(self):
        with self._private_root() as tmp:
            root = Path(tmp)
            poll_dir = root / "polls"
            poll_dir.mkdir(mode=0o700)
            poll_dir.chmod(0o700)
            receipt = self._receipt()
            paths = Launch._poll_paths(poll_dir, 0)
            for name in ("stdout", "stderr"):
                paths[name].write_bytes(b"")
                paths[name].chmod(0o400)
            capture_identities = {}
            for name in ("stdout", "stderr"):
                info = paths[name].lstat()
                capture_identities[name] = {
                    "path": str(paths[name]),
                    "canonical_path": str(paths[name]),
                    "device": info.st_dev,
                    "inode": info.st_ino,
                    "mode": "0400",
                    "uid": info.st_uid,
                    "gid": info.st_gid,
                    "link_count": 1,
                    "bytes_at_intent": 0,
                }
            intent = {
                "schema": Launch.POLL_SCHEMA + "/intent",
                "campaign": "v11-full-census", "poll_index": 0,
                "job_id": "123", "recorded_utc": "2026-09-13T11:00:00+00:00",
                "not_before_utc": "2026-09-13T11:00:00+00:00",
                "previous_poll_receipt_sha256": None,
                "launch_receipt_sha256": "b" * 64,
                "command": Launch._poll_command("123"),
                "capture_initial_identities": capture_identities,
            }
            paths["intent"].write_bytes(Launch._canonical_json(intent))
            paths["intent"].chmod(0o400)
            name = "pdb-source-v11-" + "a" * 24

            def run(command, **kwargs):
                os.write(kwargs["stdout"], self._completed_row("123", name, 0))
                return subprocess.CompletedProcess(command, 0)

            with (
                mock.patch.object(Launch, "_executable_identity", return_value={}),
                mock.patch("subprocess.run", side_effect=run) as called,
            ):
                summary = Launch._poll_scheduler(
                    campaign="v11-full-census", launch_sha="b" * 64,
                    launch_receipt=receipt,
                    launch_recorded_utc=receipt["accepted_utc"],
                    poll_dir=poll_dir, terminal_path=root / "terminal.json",
                    task_count=1, job_name=name,
                    terminal_schema=Launch.EXECUTION_SCHEMA + "/terminal/v1",
                    poll_schema=Launch.POLL_SCHEMA,
                    now=datetime.datetime.fromisoformat(
                        "2026-09-13T12:00:00+00:00"
                    ),
                )
            self.assertEqual(called.call_count, 1)
            self.assertEqual(summary["poll_index"], 1)
            abandoned_raw = paths["abandoned"].read_bytes()
            successor = json.loads(
                (poll_dir / "poll-0001-receipt.json").read_text("ascii")
            )
            self.assertEqual(
                successor["previous_poll_receipt_sha256"],
                hashlib.sha256(abandoned_raw).hexdigest(),
            )
            abandoned = json.loads(abandoned_raw)
            self.assertFalse(abandoned["authorizing"])
            self.assertEqual(abandoned["scheduler_queries_during_recovery"], 0)
            self._rewrite_json(
                paths["abandoned"],
                lambda value: value["durable_files"].__setitem__(
                    paths["stdout"].name, "0" * 64
                ),
            )
            with self.assertRaisesRegex(
                Launch.LaunchAuditError, "abandoned poll"
            ):
                Launch._retained_terminal_gate(
                    terminal_path=root / "terminal.json", poll_dir=poll_dir,
                    expected_schema=Launch.EXECUTION_SCHEMA + "/terminal/v1",
                    campaign="v11-full-census", job_id="123", task_count=1,
                    job_name=name, poll_schema=Launch.POLL_SCHEMA,
                    launch_sha="b" * 64,
                    launch_accepted_utc=receipt["accepted_utc"],
                )

    def test_pre_intent_stranding_burns_campaign_without_query(self):
        with self._private_root() as tmp:
            poll_dir = Path(tmp) / "polls"
            poll_dir.mkdir(mode=0o700)
            poll_dir.chmod(0o700)
            path = Launch._poll_paths(poll_dir, 0)["stdout"]
            path.write_bytes(b"")
            path.chmod(0o400)
            with self.assertRaisesRegex(Launch.LaunchAuditError, "burns"):
                Launch._poll_sequence(poll_dir)

    def test_successful_consumer_object_is_explicit_full_authorization(self):
        authorized = SimpleNamespace(
            seal_repository_commit_id="a" * 40,
            authorization_sha256="b" * 64,
            compute_canary_attestation_sha256="c" * 64,
            controller_publisher_canary_receipt_sha256="d" * 64,
            code_manifest_sha256="e" * 64,
        )
        with (
            mock.patch.dict("sys.modules", {
                "pdb_terminal_incidence_confirmation_source_consumer_v11":
                    SimpleNamespace(
                        preflight_paths_for=lambda **_kwargs: object(),
                        load_authorized_preflight=lambda *_args, **_kwargs: authorized,
                    ),
            }),
            mock.patch(
                "pdb_terminal_incidence_v11_snapshot_reader.read_committed_snapshot"
            ),
        ):
            binding = Launch._load_preflight_binding("a" * 40, "e" * 64)
        self.assertTrue(binding["full_launch_authorized"])
        self.assertTrue(binding["snapshot_consumed"])

    def test_launch_recovery_never_queries_scheduler(self):
        ambiguous = {
            "accepted_by_launcher": False,
            "process_observation": {
                "kind": "os-error", "returncode": None,
            },
            "parsed_job_id": None,
            "stdout": {"sha256": "a" * 64},
        }
        with (
            mock.patch("subprocess.check_output") as scheduler_query,
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "extra scheduler query"
            ),
        ):
            Launch._recovery_evidence({}, ambiguous)
        scheduler_query.assert_not_called()

        retained_acceptance = {
            "accepted_by_launcher": True,
            "process_observation": {
                "kind": "completed-process", "returncode": 0,
            },
            "parsed_job_id": "123",
            "stdout": {"sha256": "b" * 64},
        }
        evidence = Launch._recovery_evidence({}, retained_acceptance)
        self.assertEqual(evidence["source"], "retained-sbatch-stdout")
        self.assertEqual(evidence["scheduler_queries_during_recovery"], 0)

    def test_runtime_source_has_no_old_multi_query_seal_path(self):
        source = Path(Launch.__file__).read_text(encoding="utf-8")
        self.assertNotIn("def _scheduler_rows(", source)
        self.assertNotIn("def _scheduler_contract_rows(", source)
        self.assertNotIn("def scheduler_gate(", source)
        self.assertNotIn("def _submission_journal(", source)
        self.assertIn("single_scheduler_query", source)
        self.assertIn("MIN_POLL_INTERVAL_SECONDS = 3600", source)


if __name__ == "__main__":
    unittest.main()
