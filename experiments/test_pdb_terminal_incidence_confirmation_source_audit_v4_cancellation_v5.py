#!/usr/bin/env python3
"""Adversarial tests for v5 safe reads and prospective v4 cancellation."""

from __future__ import annotations

import hashlib
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock


SCRIPT_DIR = Path(__file__).absolute().parent
import sys
sys.path.insert(0, str(SCRIPT_DIR))

import cancel_pdb_terminal_incidence_confirmation_source_audit_v4_v5 as Cancel
import audit_pdb_terminal_incidence_confirmation_sources_v5 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v5 as Launch
import pdb_terminal_incidence_confirmation_safe_io_v5 as SafeIO


def scheduler_rows(*, active=False, cancelled=False, unknown=False):
    rows = [
        {
            "array_task": task,
            "state": "COMPLETED",
            "exit_code": "0:0",
            "elapsed": "00:01:00",
            "partition": "fat",
        }
        for task in range(Cancel.ARRAY_TASKS)
    ]
    for task in (147, 150, 484, 486, 487, 489):
        rows[task].update(
            state="FAILED",
            exit_code="75:0",
            elapsed=Cancel.TRIGGER_SPECS[task]["accounting_rows"][0]["elapsed"],
        )
    for task in (488, 716, 717, 718, 719, 720, 722):
        rows[task].update(
            state="OUT_OF_MEMORY",
            exit_code="0:125",
            elapsed=Cancel.TRIGGER_SPECS[task]["accounting_rows"][0]["elapsed"],
        )
    if active:
        rows[0].update(state="RUNNING", exit_code="0:0")
    if cancelled:
        rows[1].update(state="CANCELLED", exit_code="0:15")
    if unknown:
        rows[2].update(state="MYSTERY", exit_code="0:0")
    return rows


def trigger_records(rows):
    by_task = {row["array_task"]: row for row in rows}
    records = []
    for task in sorted(Cancel.TRIGGER_SPECS):
        expected = Cancel.TRIGGER_SPECS[task]
        accounting = expected["accounting_rows"]
        records.append({
            "array_task": task,
            "state": by_task[task]["state"],
            "exit_code": by_task[task]["exit_code"],
            "task_name": "fixture-task-{}".format(task),
            "failure_class": expected["failure_class"],
            "log_path": str(
                Cancel.V4_OUTPUT_DIR
                / "slurm-{}_{}.out".format(Cancel.JOB_ID, task)
            ),
            "log_bytes": expected["log_bytes"],
            "log_sha256": expected["log_sha256"],
            "accounting_rows": accounting,
            "accounting_rows_sha256": Cancel._digest_json(accounting),
        })
    return records


class SafeIOV5Tests(unittest.TestCase):
    def test_regular_file_and_read_callback(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence"
            path.write_bytes(b"fixed")
            calls = []
            loaded = SafeIO.read_regular_file(
                path,
                label="evidence",
                expected_path=path,
                read_callback=lambda candidate, descriptor: calls.append(
                    (candidate, descriptor)
                ),
            )
            self.assertEqual(loaded.raw, b"fixed")
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][0], path)

    def test_final_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target"
            link = root / "link"
            target.write_bytes(b"fixed")
            link.symlink_to(target)
            with self.assertRaises(SafeIO.SafeReadError):
                SafeIO.read_regular_file(link, label="symlink", root=root)

    def test_ancestor_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            (real / "leaf").write_bytes(b"fixed")
            alias = root / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaises(SafeIO.SafeReadError):
                SafeIO.read_regular_file(
                    alias / "leaf", label="ancestor symlink", root=root
                )

    def test_relative_candidate_is_relative_to_absolute_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nested").mkdir()
            (root / "nested" / "leaf").write_bytes(b"fixed")
            loaded = SafeIO.read_regular_file(
                Path("nested/leaf"),
                label="root-relative leaf",
                expected_path=Path("nested/leaf"),
                root=root,
            )
            self.assertEqual(loaded.raw, b"fixed")

    def test_noncanonical_absolute_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "leaf").write_bytes(b"fixed")
            with self.assertRaisesRegex(SafeIO.SafeReadError, "canonical"):
                SafeIO.read_regular_file(
                    Path("leaf"),
                    label="noncanonical root",
                    root=root / "child" / "..",
                )

    def test_symlink_above_declared_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            real = base / "real"
            root = real / "root"
            root.mkdir(parents=True)
            (root / "leaf").write_bytes(b"fixed")
            alias = base / "alias"
            alias.symlink_to(real, target_is_directory=True)
            with self.assertRaises(SafeIO.SafeReadError):
                SafeIO.read_regular_file(
                    Path("leaf"),
                    label="symlink above root",
                    root=alias / "root",
                )

    def test_replacement_above_declared_root_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            upper = base / "upper"
            root = upper / "root"
            root.mkdir(parents=True)
            (root / "leaf").write_bytes(b"fixed")

            def replace(_candidate, _descriptor):
                upper.rename(base / "old-upper")
                replacement = upper / "root"
                replacement.mkdir(parents=True)
                (replacement / "leaf").write_bytes(b"fixed")

            with self.assertRaisesRegex(SafeIO.SafeReadError, "changed"):
                SafeIO.read_regular_file(
                    Path("leaf"),
                    label="replacement above root",
                    expected_path=Path("leaf"),
                    root=root,
                    read_callback=replace,
                )

    def test_exact_relative_slurm_code_manifest_path_is_root_relative(self):
        slurm = SafeIO.read_regular_file(
            Launch.SLURM_SCRIPT,
            label="v5 Slurm fixture",
            expected_path=Launch.SLURM_SCRIPT,
        ).raw
        marker = b'code_manifest="'
        lines = [line for line in slurm.splitlines() if line.startswith(marker)]
        self.assertEqual(len(lines), 1)
        relative = lines[0][len(marker):-1].decode("ascii")
        self.assertEqual(
            relative,
            "experiments/pdb_terminal_incidence_confirmation_source_audit_v5_code.sha256",
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / relative
            target.parent.mkdir(parents=True)
            target.write_bytes(b"manifest")
            loaded = SafeIO.read_regular_file(
                Path(relative),
                label="relative Slurm code manifest",
                expected_path=Path(relative),
                root=root,
            )
            self.assertEqual(loaded.raw, b"manifest")

    def test_fifo_is_rejected_without_opening_for_blocking_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fifo"
            os.mkfifo(path)
            with self.assertRaises(SafeIO.SafeReadError):
                SafeIO.read_regular_file(path, label="fifo")

    def test_callback_inode_swap_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence"
            old = Path(tmp) / "old"
            path.write_bytes(b"before")

            def swap(candidate, _descriptor):
                candidate.rename(old)
                candidate.write_bytes(b"after")

            with self.assertRaisesRegex(SafeIO.SafeReadError, "changed"):
                SafeIO.read_regular_file(
                    path, label="inode swap", read_callback=swap
                )

    def test_callback_same_inode_content_swap_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence"
            path.write_bytes(b"before")

            def swap(candidate, _descriptor):
                with candidate.open("r+b") as stream:
                    stream.seek(0)
                    stream.write(b"replacement")
                    stream.truncate()
                    stream.flush()
                    os.fsync(stream.fileno())

            with self.assertRaisesRegex(SafeIO.SafeReadError, "changed"):
                SafeIO.read_regular_file(
                    path, label="content swap", read_callback=swap
                )

    def test_recursive_translator_tree_rejects_directory_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            tree = repo / "src" / "translate"
            (tree / "nested").mkdir(parents=True)
            (tree / "nested" / "module.py").write_bytes(b"fixed")

            def mutate(candidate, _descriptor):
                (candidate / "nested" / "injected.py").write_bytes(b"new")

            with (
                mock.patch.object(Source, "REPO", repo),
                self.assertRaisesRegex(Source.SourceAuditError, "changed"),
            ):
                Source.translator_source_digest(tree_callback=mutate)

    def test_output_tree_rejects_injected_extra_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = root / "source-inventory-v5.json"
            inventory.write_bytes(b"fixed")
            identity = SafeIO.inspect_directory(
                root, label="output fixture", expected_path=root
            ).identity

            def mutate(candidate, _descriptor):
                (candidate / "injected").write_bytes(b"new")

            with (
                mock.patch.object(Launch, "OUTPUT_DIR", root),
                mock.patch.object(Launch, "SOURCE_INVENTORY", inventory),
                mock.patch.object(Launch, "ARRAY_TASKS", 0),
                self.assertRaisesRegex(Launch.LaunchAuditError, "changed"),
            ):
                Launch._output_tree("1", identity, tree_callback=mutate)

    def test_clean_output_tree_matches_launch_identity_on_two_reads(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            output.mkdir(mode=0o700)
            output.chmod(0o700)
            inventory = output / "source-inventory-v5.json"
            shard = Source.shard_path(output, 0)
            environment = Source.task_environment_path(output, 0)
            log = output / "slurm-42_0.out"
            payloads = {
                inventory: b"inventory\n",
                shard: b"shard\n",
                environment: b"environment\n",
                log: b"log\n",
            }
            for path, raw in payloads.items():
                path.write_bytes(raw)
            identity = Launch._directory_identity(output, "output fixture")
            digest = hashlib.sha256()
            digest.update(
                b"root-identity\0" + Source.canonical_json(identity)
            )
            records = []
            for path in sorted(payloads):
                relative = path.relative_to(output).as_posix()
                sha256 = hashlib.sha256(payloads[path]).hexdigest()
                digest.update(
                    relative.encode("ascii") + b"\0" + bytes.fromhex(sha256)
                )
                records.append({
                    "path": relative,
                    "bytes": len(payloads[path]),
                    "sha256": sha256,
                })
            expected = {
                "sha256": digest.hexdigest(),
                "root_identity": identity,
                "files_count": 4,
                "files": records,
            }
            with (
                mock.patch.object(Launch, "OUTPUT_DIR", output),
                mock.patch.object(Launch, "SOURCE_INVENTORY", inventory),
                mock.patch.object(Launch, "ARRAY_TASKS", 1),
            ):
                first = Launch._output_tree("42", identity)
                second = Launch._output_tree("42", identity)
            self.assertEqual(first, expected)
            self.assertEqual(second, expected)
            self.assertEqual(first, second)


class CancellationV5Tests(unittest.TestCase):
    def _valid_intent(self):
        rows = scheduler_rows(active=True)
        snapshot = Cancel._snapshot(rows)
        triggers = trigger_records(rows)
        code = [{"path": "experiments/example", "sha256": "a" * 64}]
        return {
            "schema": Cancel.INTENT_SCHEMA,
            "recorded_utc": "2026-09-01T00:00:00+00:00",
            "job_id": Cancel.JOB_ID,
            "cancel_scope": "whole-parent-array-once",
            "reason": Cancel.REASON,
            "scancel": {
                "path": str(Cancel.SCANCEL),
                "sha256": Cancel.SCANCEL_SHA256,
            },
            "argv": Cancel.SCANCEL_ARGV,
            "controlled_environment": Cancel.CONTROLLED_ENV,
            "authorized_triggers": triggers,
            "authorized_triggers_sha256": Cancel._digest_json(triggers),
            "scheduler_snapshot": snapshot,
            "scheduler_snapshot_sha256": Cancel._digest_json(snapshot),
            "code_materials": code,
            "code_materials_sha256": Cancel._digest_json(code),
            "full_v5_rerun": {
                "whole_campaign_rerun": True,
                "array_tasks": 820,
                "candidates": 1640,
                "reused_v1_shards": 0,
                "reused_v2_shards": 0,
                "reused_v3_shards": 0,
                "reused_v4_shards": 0,
            },
        }

    def test_exact_parent_only_argv(self):
        self.assertEqual(Cancel.SCANCEL_ARGV, ["/usr/bin/scancel", "1865695"])
        self.assertNotIn("_", Cancel.SCANCEL_ARGV[1])

    def test_all_known_pre_intent_failures_are_exactly_pinned(self):
        self.assertEqual(
            set(Cancel.TRIGGER_SPECS),
            {147, 150, 484, 486, 487, 488, 489, 716, 717, 718, 719, 720, 722},
        )
        self.assertEqual(
            Cancel.TRIGGER_SPECS[147]["log_sha256"],
            "796c47815fbd4cd3666e7d11e9205f334a1e40f6be34d807bc574a334e6c9fd1",
        )
        self.assertEqual(Cancel.TRIGGER_SPECS[147]["log_bytes"], 2140)
        self.assertEqual(
            Cancel.TRIGGER_SPECS[487]["log_sha256"],
            "a13303629929b99b8674a34a4aeec89e0ec41360e3fec4eeaf8771b4f51a5f2d",
        )
        self.assertEqual(Cancel.TRIGGER_SPECS[487]["log_bytes"], 2127)
        self.assertEqual(
            {
                task: (
                    Cancel.TRIGGER_SPECS[task]["log_bytes"],
                    Cancel.TRIGGER_SPECS[task]["log_sha256"],
                )
                for task in (484, 486, 489)
            },
            {
                484: (
                    2167,
                    "f4ad30cebbfd2466233db64b4b5d0e11f03e1760707d2cd51c3f99e54a2ab919",
                ),
                486: (
                    2319,
                    "ebf24a2c7c4f07c498c56ffc65f60ffacdf577dcd6287a39f0f34e01748a56af",
                ),
                489: (
                    2127,
                    "7eb4626a832645d64b1416ddcf7ec76fe88fc558657b7ad2917b4b91d3a900dc",
                ),
            },
        )
        self.assertEqual(
            Cancel.TRIGGER_SPECS[720]["log_sha256"],
            "dffba4d69139089c8b3976de084c7378b1912efae7ddeda73e63f1e595ea286b",
        )
        self.assertEqual(Cancel.TRIGGER_SPECS[720]["log_bytes"], 2224)
        self.assertEqual(
            Cancel.TRIGGER_SPECS[147]["accounting_rows"][1]["max_rss"],
            "350066053K",
        )
        self.assertEqual(
            Cancel.TRIGGER_SPECS[720]["accounting_rows"][1]["max_rss"],
            "1066464869K",
        )
        self.assertEqual(
            Cancel.TRIGGER_SPECS[487]["accounting_rows"][1]["max_rss"],
            "942747015K",
        )
        self.assertEqual(
            {
                task: (
                    Cancel.TRIGGER_SPECS[task]["log_sha256"],
                    Cancel.TRIGGER_SPECS[task]["accounting_rows"][1]["max_rss"],
                    Cancel.TRIGGER_SPECS[task]["accounting_rows"][1]["max_vm_size"],
                )
                for task in (716, 717, 718, 719, 722)
            },
            {
                716: (
                    "2d275d765948a8354e689e0a1acda532c9ba47127b52d86cb29a6629492c2f23",
                    "1054370899K", "1069066976K",
                ),
                717: (
                    "8c0eaaf157f2d5fa7aeb3680bda1cf267bfb41487e33f4a56caf8101bd67f61b",
                    "1071622629K", "1073078444K",
                ),
                718: (
                    "7f70f4c5327c7435041977e7b55f090a18873dfb2bb1661e36b23f00f6b2adb7",
                    "1056671983K", "1068164944K",
                ),
                719: (
                    "471db3ece0c3b98b3fb8459c7d286ff152a4efddcb3dd9d958ad5220fb7650eb",
                    "1056300488K", "1066803356K",
                ),
                722: (
                    "e65a146a654b8d1de9fd480d8d8610d0a315ad86dd1b320484e2c3e1a82caa05",
                    "1057000387K", "1069303288K",
                ),
            },
        )

    def test_intent_trigger_set_must_equal_snapshot_failure_set(self):
        intent = self._valid_intent()
        intent["authorized_triggers"] = intent["authorized_triggers"][:-1]
        intent["authorized_triggers_sha256"] = Cancel._digest_json(
            intent["authorized_triggers"]
        )
        with self.assertRaisesRegex(
            Cancel.CancellationError, "snapshot failures"
        ):
            Cancel._validate_intent(Cancel._canonical(intent), intent)

    def test_wrong_argv_pin_is_rejected(self):
        intent = self._valid_intent()
        Cancel._validate_intent(Cancel._canonical(intent), intent)
        intent["argv"] = ["/usr/bin/scancel", "1865695_0"]
        with self.assertRaisesRegex(Cancel.CancellationError, "intent changed"):
            Cancel._validate_intent(Cancel._canonical(intent), intent)

    def test_mixed_terminal_states_are_allowed_but_active_is_not_terminal(self):
        rows = scheduler_rows(cancelled=True)
        Cancel._validate_snapshot(Cancel._snapshot(rows), terminal=True)
        with self.assertRaisesRegex(Cancel.CancellationError, "state changed"):
            Cancel._validate_snapshot(
                Cancel._snapshot(scheduler_rows(active=True, cancelled=True)),
                terminal=True,
            )

    def test_transition_rejects_new_failure_class(self):
        before = scheduler_rows(active=True)
        after = [dict(row) for row in before]
        after[0].update(state="FAILED", exit_code="1:0")
        with self.assertRaisesRegex(
            Cancel.CancellationError, "unauthorized"
        ):
            Cancel._validate_monotonic_transition(before, after)

    def test_preinvoke_transition_rejects_cancellation(self):
        before = scheduler_rows(active=True)
        after = [dict(row) for row in before]
        after[0].update(state="CANCELLED", exit_code="0:15")
        with self.assertRaisesRegex(
            Cancel.CancellationError, "unauthorized"
        ):
            Cancel._validate_monotonic_transition(before, after)

    def test_postinvoke_and_delayed_cancellation_transitions_are_allowed(self):
        before = scheduler_rows(active=True)
        before[1].update(state="PENDING", exit_code="0:0")
        before[2].update(state="RUNNING", exit_code="0:0")
        receipt = [dict(row) for row in before]
        receipt[0].update(
            state="COMPLETED", exit_code="0:0", elapsed="00:02:00"
        )
        receipt[1].update(
            state="CANCELLED", exit_code="0:15", elapsed="00:00:30"
        )
        receipt[2].update(elapsed="00:00:45")
        Cancel._validate_monotonic_transition(
            before, receipt, allow_cancelled=True
        )
        final = [dict(row) for row in receipt]
        final[2].update(
            state="CANCELLED", exit_code="0:15", elapsed="00:01:00"
        )
        Cancel._validate_monotonic_transition(
            receipt, final, allow_cancelled=True
        )

    def test_completed_to_cancelled_and_terminal_mutation_are_rejected(self):
        before = scheduler_rows()
        completed_to_cancelled = [dict(row) for row in before]
        completed_to_cancelled[0].update(
            state="CANCELLED", exit_code="0:15"
        )
        with self.assertRaisesRegex(Cancel.CancellationError, "terminal"):
            Cancel._validate_monotonic_transition(
                before, completed_to_cancelled, allow_cancelled=True
            )
        mutated_failure = [dict(row) for row in before]
        mutated_failure[147]["elapsed"] = "05:10:09"
        with self.assertRaisesRegex(Cancel.CancellationError, "terminal"):
            Cancel._validate_monotonic_transition(
                before, mutated_failure, allow_cancelled=True
            )

    def test_trigger_reader_never_opens_completed_or_cancelled_logs(self):
        rows = [
            {
                "array_task": task,
                "state": "COMPLETED",
                "exit_code": "0:0",
                "elapsed": "00:01:00",
                "partition": "fat",
            }
            for task in range(Cancel.ARRAY_TASKS)
        ]
        rows[0].update(state="CANCELLED", exit_code="0:15")
        rows[1].update(state="FAILED", exit_code="75:0", elapsed="04:00:01")
        accounting = [
            {
                "job_id": "1865695_1", "job_id_raw": "1",
                "state": "FAILED", "exit_code": "75:0",
                "elapsed": "04:00:01", "requested_memory": "1T",
                "max_rss": None, "max_vm_size": None,
            },
            {
                "job_id": "1865695_1.batch", "job_id_raw": "1.batch",
                "state": "FAILED", "exit_code": "75:0",
                "elapsed": "04:00:01", "requested_memory": None,
                "max_rss": "1K", "max_vm_size": "1K",
            },
        ]
        task_name = b"fixture-task"
        payload = (
            b"[2/2] " + task_name + b"\n"
            b"infrastructure error: translator exceeded 14400s for "
            + task_name
            + b"; stderr_sha256="
            + hashlib.sha256(b"").hexdigest().encode("ascii")
            + b"; stderr_tail=''\n"
        )
        with (
            mock.patch.object(Cancel, "TRIGGER_SPECS", {}),
            mock.patch.object(
                Cancel, "_trigger_accounting_rows", return_value=accounting
            ),
            mock.patch.object(
                Cancel,
                "_safe_file",
                return_value=types.SimpleNamespace(
                    raw=payload, sha256=hashlib.sha256(payload).hexdigest()
                ),
            ) as read_log,
        ):
            evidence = Cancel._trigger_evidence(rows, allow_cancelled=True)
        self.assertEqual([item["array_task"] for item in evidence], [1])
        self.assertEqual(read_log.call_count, 1)
        self.assertTrue(str(read_log.call_args.args[0]).endswith("_1.out"))

    def test_final_transition_rejects_before_failed_log_read(self):
        intent_rows = scheduler_rows(active=True)
        receipt_rows = [dict(row) for row in intent_rows]
        receipt_rows[0].update(state="CANCELLED", exit_code="0:15")
        final_rows = [dict(row) for row in receipt_rows]
        final_rows[1].update(state="CANCELLED", exit_code="0:15")
        snapshot_sha = "c" * 64
        intent_raw = b"intent\n"
        attempt_raw = b"attempt\n"
        intent = {
            "scheduler_snapshot": Cancel._snapshot(intent_rows),
            "scheduler_snapshot_sha256": snapshot_sha,
        }
        attempt = {
            "intent_scheduler_snapshot_sha256": snapshot_sha,
            "pre_cancel_scheduler_snapshot": Cancel._snapshot(intent_rows),
            "repository_commit_id": "a" * 64,
        }
        receipt = {
            "post_cancel_scheduler_snapshot": Cancel._snapshot(receipt_rows),
        }
        with (
            mock.patch.object(
                Cancel, "_load_intent", return_value=(intent_raw, intent)
            ),
            mock.patch.object(
                Cancel, "_load_attempt", return_value=(attempt_raw, attempt)
            ),
            mock.patch.object(
                Cancel, "_load_json", return_value=(b"receipt\n", receipt)
            ),
            mock.patch.object(Cancel, "_validate_receipt"),
            mock.patch.object(Cancel, "_validate_recorded_commit"),
            mock.patch.object(Cancel, "_trigger_evidence") as read_log,
        ):
            with self.assertRaisesRegex(Cancel.CancellationError, "terminal"):
                Cancel.validate_terminal_cancellation(final_rows)
            read_log.assert_not_called()

    def test_unknown_or_active_state_rejected_before_launcher_log_read(self):
        for rows in (scheduler_rows(active=True), scheduler_rows(unknown=True)):
            with self.subTest(state=rows[0]["state"]):
                with (
                    mock.patch.object(
                        Launch, "_v4_fixed_launch_provenance", return_value={}
                    ),
                    mock.patch.object(Launch, "_scheduler_rows", return_value=rows),
                    mock.patch.object(Launch, "_safe_file") as read_log,
                ):
                    with self.assertRaises(Launch.LaunchAuditError):
                        Launch._expected_v4_diagnostic()
                    read_log.assert_not_called()

    def test_bad_cancellation_evidence_rejected_before_launcher_log_read(self):
        rows = scheduler_rows(cancelled=True)
        with (
            mock.patch.object(
                Launch, "_v4_fixed_launch_provenance", return_value={}
            ),
            mock.patch.object(Launch, "_scheduler_rows", return_value=rows),
            mock.patch.object(
                Cancel,
                "validate_terminal_cancellation",
                side_effect=Cancel.CancellationError("missing receipt"),
            ),
            mock.patch.object(Launch, "_safe_file") as read_log,
        ):
            with self.assertRaisesRegex(Launch.LaunchAuditError, "missing receipt"):
                Launch._expected_v4_diagnostic()
            read_log.assert_not_called()

    def test_natural_terminal_v4_needs_no_cancellation_artifact(self):
        rows = scheduler_rows()
        empty_sha = hashlib.sha256(b"").hexdigest()

        def failed_log(path, *_args, **_kwargs):
            task = int(path.stem.rsplit("_", 1)[1])
            task_name = "fixture-task-{}".format(task)
            if rows[task]["state"] == "FAILED":
                raw = (
                    "[2/2] {task}\n"
                    "infrastructure error: translator exceeded 14400s for "
                    "{task}; stderr_sha256={sha}; stderr_tail=''\n"
                ).format(task=task_name, sha=empty_sha).encode("ascii")
            else:
                raw = (
                    "[2/2] {task}\ntranslator critical exit -9\n"
                    "scheduler: oom_kill\n"
                ).format(task=task_name).encode("ascii")
            return types.SimpleNamespace(raw=raw)

        with (
            mock.patch.object(
                Launch, "_v4_fixed_launch_provenance", return_value={}
            ),
            mock.patch.object(Launch, "_scheduler_rows", return_value=rows),
            mock.patch.object(Launch, "_safe_file", side_effect=failed_log),
            mock.patch.object(
                Launch, "_v4_oom_resource_rows", return_value=[]
            ),
            mock.patch.object(
                Launch, "_v4_timeout_resource_rows", return_value=[]
            ),
        ):
            diagnostic = Launch._expected_v4_diagnostic()
        self.assertIsNone(diagnostic["v4_cancellation"])
        self.assertEqual(diagnostic["v4_cancelled_array_tasks"], [])
        self.assertEqual(
            diagnostic["v4_translator_timeout_array_tasks"],
            [147, 150, 484, 486, 487, 489],
        )
        self.assertEqual(
            diagnostic["v4_out_of_memory_array_tasks"],
            [488, 716, 717, 718, 719, 720, 722],
        )

    def test_prepare_intent_records_zero_reuse_and_full_snapshot(self):
        captured = {}
        rows = scheduler_rows(active=True)
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / name for name in ("intent", "attempt", "receipt")]

            def publish(_path, value, _label):
                captured.update(value)
                return hashlib.sha256(Cancel._canonical(value)).hexdigest()

            with (
                mock.patch.multiple(
                    Cancel, INTENT=paths[0], ATTEMPT=paths[1], RECEIPT=paths[2]
                ),
                mock.patch.object(
                    Cancel, "_tool", return_value={
                        "path": str(Cancel.SCANCEL),
                        "sha256": Cancel.SCANCEL_SHA256,
                    }
                ),
                mock.patch.object(Cancel, "scheduler_rows", return_value=rows),
                mock.patch.object(
                    Cancel, "_trigger_evidence", return_value=trigger_records(rows)
                ),
                mock.patch.object(
                    Cancel, "_code_materials", return_value=[{
                        "path": "experiments/fixed", "sha256": "a" * 64,
                    }]
                ),
                mock.patch.object(Cancel, "_exclusive_json", side_effect=publish),
            ):
                Cancel.prepare_cancel_intent()
        rerun = captured["full_v5_rerun"]
        self.assertEqual(rerun["array_tasks"], 820)
        self.assertEqual(rerun["candidates"], 1640)
        self.assertEqual(
            [rerun["reused_v{}_shards".format(version)] for version in range(1, 5)],
            [0, 0, 0, 0],
        )
        self.assertEqual(
            captured["scheduler_snapshot"]["rows_sha256"],
            Cancel._digest_json(rows),
        )

    def test_crash_after_attempt_can_never_issue_second_cancel(self):
        rows = scheduler_rows(active=True)
        intent = {
            "scancel": {"path": str(Cancel.SCANCEL), "sha256": Cancel.SCANCEL_SHA256},
            "argv": Cancel.SCANCEL_ARGV,
            "controlled_environment": Cancel.CONTROLLED_ENV,
            "authorized_triggers": [],
            "scheduler_snapshot": Cancel._snapshot(rows),
            "scheduler_snapshot_sha256": Cancel._digest_json(
                Cancel._snapshot(rows)
            ),
        }
        intent_raw = b"fixed-intent\n"
        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / name for name in ("intent", "attempt", "receipt")]

            def publish(path, value, _label):
                raw = Cancel._canonical(value)
                path.write_bytes(raw)
                return hashlib.sha256(raw).hexdigest()

            with (
                mock.patch.multiple(
                    Cancel, INTENT=paths[0], ATTEMPT=paths[1], RECEIPT=paths[2]
                ),
                mock.patch.object(
                    Cancel, "_load_intent", return_value=(intent_raw, intent)
                ),
                mock.patch.object(Cancel, "_scoped_repository_commit", return_value="a" * 64),
                mock.patch.object(Cancel, "scheduler_rows", return_value=rows),
                mock.patch.object(Cancel, "_trigger_evidence", return_value=[]),
                mock.patch.object(Cancel, "_tool", return_value=intent["scancel"]),
                mock.patch.object(Cancel, "_exclusive_json", side_effect=publish),
                mock.patch.object(
                    Cancel.subprocess, "run", side_effect=OSError("crash")
                ) as run,
            ):
                with self.assertRaisesRegex(Cancel.CancellationError, "indeterminate"):
                    Cancel.cancel_v4()
                self.assertTrue(paths[1].exists())
                with self.assertRaisesRegex(Cancel.CancellationError, "already attempted"):
                    Cancel.cancel_v4()
                self.assertEqual(run.call_count, 1)
                self.assertEqual(run.call_args.args[0], Cancel.SCANCEL_ARGV)

    def test_recovery_never_calls_scancel_or_resubmits(self):
        rows = scheduler_rows(cancelled=True)
        pre_rows = scheduler_rows()
        pre_rows[1].update(state="RUNNING", exit_code="0:0")
        intent_raw = b"fixed-intent\n"
        attempt_raw = b"fixed-attempt\n"
        snapshot_sha = "c" * 64
        attempt = {
            "repository_commit_id": "a" * 64,
            "intent_scheduler_snapshot_sha256": snapshot_sha,
            "pre_cancel_scheduler_snapshot": Cancel._snapshot(pre_rows),
        }
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt"
            with (
                mock.patch.object(Cancel, "RECEIPT", receipt),
                mock.patch.object(
                    Cancel,
                    "_load_intent",
                    return_value=(intent_raw, {
                        "scheduler_snapshot_sha256": snapshot_sha,
                        "scheduler_snapshot": Cancel._snapshot(pre_rows),
                    }),
                ),
                mock.patch.object(
                    Cancel, "_load_attempt", return_value=(attempt_raw, attempt)
                ),
                mock.patch.object(Cancel, "scheduler_rows", return_value=rows),
                mock.patch.object(Cancel, "_write_receipt", return_value="b" * 64),
                mock.patch.object(Cancel.subprocess, "run") as run,
            ):
                Cancel.recover_cancel_receipt()
                run.assert_not_called()

    def test_recovery_rejects_terminal_mutation_before_receipt_write(self):
        pre_rows = scheduler_rows()
        final_rows = [dict(row) for row in pre_rows]
        final_rows[0].update(state="CANCELLED", exit_code="0:15")
        snapshot_sha = "c" * 64
        intent = {
            "scheduler_snapshot_sha256": snapshot_sha,
            "scheduler_snapshot": Cancel._snapshot(pre_rows),
        }
        attempt = {
            "repository_commit_id": "a" * 64,
            "intent_scheduler_snapshot_sha256": snapshot_sha,
            "pre_cancel_scheduler_snapshot": Cancel._snapshot(pre_rows),
            "pre_cancel_scheduler_snapshot_sha256": Cancel._digest_json(
                Cancel._snapshot(pre_rows)
            ),
        }
        with tempfile.TemporaryDirectory() as tmp:
            with (
                mock.patch.object(Cancel, "RECEIPT", Path(tmp) / "receipt"),
                mock.patch.object(
                    Cancel, "_load_intent", return_value=(b"intent\n", intent)
                ),
                mock.patch.object(
                    Cancel, "_load_attempt", return_value=(b"attempt\n", attempt)
                ),
                mock.patch.object(
                    Cancel, "scheduler_rows", return_value=final_rows
                ),
                mock.patch.object(Cancel, "_exclusive_json") as publish,
            ):
                with self.assertRaisesRegex(Cancel.CancellationError, "terminal"):
                    Cancel.recover_cancel_receipt()
                publish.assert_not_called()

    def test_transition_during_commit_allows_progress_and_binds_both_snapshots(self):
        intent_rows = scheduler_rows(active=True)
        intent_rows[3].update(state="PENDING", exit_code="0:0")
        live_rows = [dict(row) for row in intent_rows]
        live_rows[0].update(
            state="COMPLETED", exit_code="0:0", elapsed="00:02:00"
        )
        live_rows[3].update(state="RUNNING", elapsed="00:00:30")
        post_rows = [dict(row) for row in live_rows]
        intent_snapshot = Cancel._snapshot(intent_rows)
        intent = {
            "scancel": {
                "path": str(Cancel.SCANCEL), "sha256": Cancel.SCANCEL_SHA256,
            },
            "argv": Cancel.SCANCEL_ARGV,
            "controlled_environment": Cancel.CONTROLLED_ENV,
            "authorized_triggers": [],
            "scheduler_snapshot": intent_snapshot,
            "scheduler_snapshot_sha256": Cancel._digest_json(intent_snapshot),
        }
        intent_raw = b"fixed-intent\n"
        captured = {}

        def receipt(**kwargs):
            captured.update(kwargs)
            return "d" * 64

        with tempfile.TemporaryDirectory() as tmp:
            paths = [Path(tmp) / name for name in ("intent", "attempt", "receipt")]
            with (
                mock.patch.multiple(
                    Cancel, INTENT=paths[0], ATTEMPT=paths[1], RECEIPT=paths[2]
                ),
                mock.patch.object(
                    Cancel, "_load_intent", return_value=(intent_raw, intent)
                ),
                mock.patch.object(
                    Cancel, "_scoped_repository_commit", return_value="a" * 64
                ),
                mock.patch.object(
                    Cancel, "scheduler_rows", side_effect=[live_rows, post_rows]
                ),
                mock.patch.object(Cancel, "_trigger_evidence", return_value=[]),
                mock.patch.object(Cancel, "_tool", return_value=intent["scancel"]),
                mock.patch.object(Cancel, "_exclusive_json", return_value="b" * 64),
                mock.patch.object(Cancel, "_write_receipt", side_effect=receipt),
                mock.patch.object(
                    Cancel.subprocess,
                    "run",
                    return_value=types.SimpleNamespace(
                        returncode=0, stdout=b"", stderr=b""
                    ),
                ) as run,
            ):
                Cancel.cancel_v4()
        run.assert_called_once()
        self.assertEqual(
            captured["attempt"]["intent_scheduler_snapshot_sha256"],
            intent["scheduler_snapshot_sha256"],
        )
        self.assertEqual(
            captured["attempt"]["pre_cancel_scheduler_snapshot_sha256"],
            Cancel._digest_json(Cancel._snapshot(live_rows)),
        )
        self.assertNotEqual(
            captured["attempt"]["intent_scheduler_snapshot_sha256"],
            captured["attempt"]["pre_cancel_scheduler_snapshot_sha256"],
        )

    def test_wrong_cancelled_accounting_pin_is_rejected(self):
        output = "1865695_1|1|COMPLETED|0:0|00:00:00|1T|node|None\n"
        with mock.patch.object(Cancel, "_sacct", return_value=output):
            with self.assertRaisesRegex(
                Cancel.CancellationError, "cancelled parent accounting"
            ):
                Cancel._cancelled_accounting_rows([1])


if __name__ == "__main__":
    unittest.main()
