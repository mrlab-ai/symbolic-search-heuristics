#!/usr/bin/env python3

from __future__ import annotations

import copy
import errno
import fcntl
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pdb_terminal_metric_choice_audit as Audit
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_recovery as Recovery
import pdb_terminal_metric_choice_runner as Runner
import pdb_terminal_metric_choice_transport as Transport
from test_pdb_terminal_metric_choice_protocol import fake_freeze, fake_standalone
from test_pdb_terminal_metric_choice_parser import (
    differing_events, same_pool_events, encode,
)
import pdb_terminal_metric_choice_parser as Trace


FREEZE_SHA = "f" * 64


def _identity(pattern_index, incidence, mj):
    return {
        "pattern_index": pattern_index,
        "sources": ["empty"] if pattern_index == 0 else ["bdd_prefix"],
        "pattern": [] if pattern_index == 0 else [0],
        "value_cap": None,
        "terminal_incidence": incidence,
        "masked_joint": mj,
    }


def fake_records(*, differing_tasks=100):
    freeze = fake_freeze()
    properties = Runner.build_manifest_properties(freeze, FREEZE_SHA)
    mapping = Runner.build_manifest(freeze, FREEZE_SHA)["cells"]
    certificates = {
        (differs, mode): Trace.certify_trace(
            encode((differing_events if differs else same_pool_events)(mode)), mode
        )
        for differs in (False, True) for mode in P.MODES
    }
    records = []
    for cell in mapping:
        task_index = int(cell["problem"][1:4])
        differs = task_index < differing_tasks
        certificate = certificates[(differs, cell["algorithm"])]
        total_time = {
            P.INCIDENCE_MODE: 100.0,
            P.MJ_MODE: 300.0,
            P.MATCHED_MODE: 400.0,
        }[cell["algorithm"]]
        record = {
            **cell, **properties, "coverage": 1, "total_time": total_time,
            "id": [cell["algorithm"], cell["domain"], cell["problem"]],
            "component_options": ["--search", P.SEARCHES[cell["algorithm"]]],
            "driver_options": [
                "--overall-time-limit", "1800s",
                "--overall-memory-limit", "24576M",
                "--build", "release_no_lp",
            ],
            "build_options": ["release_no_lp"],
            "local_revision": P.REQUIRED_SELECTOR_COMMIT,
            "global_revision": P.REQUIRED_SELECTOR_COMMIT,
            "dual_selector_trace_schema": P.DUAL_TRACE_SCHEMA,
            "dual_selector_trace_certified": True,
            "dual_selector_trace_status": "complete",
            **{
                "dual_selector_" + key: certificate[key] for key in (
                    "structural_trace", "structural_trace_sha256", "pool_sha256",
                    "normalized_pool", "normalized_pool_sha256",
                    "state_profiles_sha256", "incidence_projection_sha256",
                    "incidence_v3_projection_sha256", "preselection_sha256",
                    "reference_identity", "incidence_winner_identity",
                    "masked_joint_winner_identity", "selected_identity",
                    "incidence_and_mj_winners_differ", "work_signature",
                    "probe_completed_layers",
                )
            },
        }
        records.append(record)
    return records


def fake_journal(freeze, *, task=None, state=Recovery.INTERRUPTED):
    entries = []
    for array_task in range(1, 301):
        triad = list(P.triad_cells(array_task))
        if array_task == task:
            started = triad[:1] if state == Recovery.INTERRUPTED else []
            bindings = [
                {"cell": cell, "manifest": {
                    "entries": [],
                    "entries_sha256": hashlib.sha256(b"").hexdigest(),
                }} for cell in started
            ]
            entry = {
                "array_task": array_task, "attempt": 1, "job_id": "42",
                "state": state, "triad_cells": triad,
                "started_cells": started, "completed_cells": [],
                "archived_cells": started,
                "archive_manifest_sha256": (
                    hashlib.sha256(P.canonical_json(bindings)).hexdigest()
                    if state == Recovery.INTERRUPTED else None
                ),
                "archive_manifests": bindings,
            }
        else:
            entry = {
                "array_task": array_task, "attempt": 1, "job_id": "42",
                "state": Recovery.COMPLETE, "triad_cells": triad,
                "started_cells": triad, "completed_cells": triad,
                "archived_cells": [], "archive_manifest_sha256": None,
                "archive_manifests": [],
            }
        entries.append(entry)
    journal = {
        "schema": Recovery.JOURNAL_SCHEMA, "freeze_sha256": FREEZE_SHA,
        "run_cell_mapping_sha256": freeze["design"]["run_cell_mapping_sha256"],
        "scheduler_contract": Runner.build_manifest(
            freeze, FREEZE_SHA
        )["transport"],
        "entries": entries,
        "entries_sha256": hashlib.sha256(P.canonical_json(entries)).hexdigest(),
    }
    rows = [{
        "array_task": entry["array_task"],
        "archive_manifest_sha256": entry["archive_manifest_sha256"],
        "cell_dynamic_entries": [
            {"cell": cell, "names": []} for cell in entry["triad_cells"]
        ],
        "dynamic_entries_after_archive": [],
    } for entry in entries if entry["state"] == Recovery.INTERRUPTED]
    rescan = {
        "schema": Recovery.RESCAN_SCHEMA,
        "journal_sha256": hashlib.sha256(
            P.canonical_json_line(journal)
        ).hexdigest(),
        "rows": rows,
        "rows_sha256": hashlib.sha256(P.canonical_json(rows)).hexdigest(),
    }
    return journal, rescan


def fake_scheduler_snapshot(freeze, *, task=None, started=None, completed=None):
    entries = []
    for array_task in range(1, 301):
        triad = list(P.triad_cells(array_task))
        if array_task == task:
            entry = {
                "array_task": array_task, "attempt": 2, "job_id": "42",
                "state": Recovery.INTERRUPTED,
                "started_cells": list(started if started is not None else triad[:1]),
                "completed_cells": list(completed if completed is not None else []),
            }
        else:
            entry = {
                "array_task": array_task, "attempt": 1, "job_id": "42",
                "state": Recovery.COMPLETE, "started_cells": triad,
                "completed_cells": triad,
            }
        entries.append(entry)
    return {
        "schema": Recovery.SCHEDULER_SNAPSHOT_SCHEMA,
        "freeze_sha256": FREEZE_SHA,
        "run_cell_mapping_sha256": freeze["design"]["run_cell_mapping_sha256"],
        "scheduler_contract": Runner.build_manifest(
            freeze, FREEZE_SHA
        )["transport"],
        "entries": entries,
        "entries_sha256": hashlib.sha256(P.canonical_json(entries)).hexdigest(),
    }


def make_run(experiment_root: Path, cell: int, dynamic=()):
    directory = Recovery._run_directory(experiment_root, cell)
    directory.mkdir(parents=True)
    for name in Recovery.STATIC_RUN_NAMES:
        (directory / name).write_bytes((name + "\n").encode("ascii"))
    for name in dynamic:
        (directory / name).write_bytes((name + "\n").encode("ascii"))
    return directory


def make_recovery_job(path: Path, freeze: dict, array_spec: str):
    contract = Transport.scheduler_contract(freeze, P.ACCOUNT)
    contract.update({
        "array_spec": array_spec,
        "array_tasks": len(array_spec.split(",")),
    })
    raw = ("\n".join(
        ["#!/bin/bash", *sorted(Transport._required_directives(contract))]
    ) + "\n").encode("ascii")
    path.write_bytes(raw)
    return raw


class ExecutionTest(unittest.TestCase):
    MAPPING_SHA = "e" * 64

    def test_runner_is_exact_unthrottled_triads(self):
        freeze = fake_freeze()
        manifest = Runner.build_manifest(freeze, FREEZE_SHA)
        self.assertEqual(manifest["transport"]["array_spec"], "1-300")
        self.assertEqual(manifest["transport"]["array_throttle"], 0)
        self.assertNotIn("%", manifest["transport"]["array_spec"])
        Runner.validate_manifest(manifest, freeze, FREEZE_SHA)

    def test_cross_arm_audit_and_adversarial_mismatch(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        records = fake_records()
        result = Audit.audit_records(records, freeze, FREEZE_SHA, standalone)
        self.assertEqual(result["triads"], 300)
        self.assertEqual(result["differing_winner_tasks"], 100)
        broken = copy.deepcopy(records)
        broken[1]["dual_selector_work_signature"]["candidate_count"] = 99
        with self.assertRaises(Audit.AuditError):
            Audit.audit_records(broken, freeze, FREEZE_SHA, standalone)
        broken = copy.deepcopy(records)
        broken[0]["dual_selector_selected_identity"] = broken[0][
            "dual_selector_reference_identity"
        ]
        with self.assertRaises(Audit.AuditError):
            Audit.audit_records(broken, freeze, FREEZE_SHA, standalone)
        broken = copy.deepcopy(records)
        del broken[0]["array_task"]
        with self.assertRaisesRegex(Audit.AuditError, "mapping"):
            Audit.audit_records(broken, freeze, FREEZE_SHA, standalone)
        broken = copy.deepcopy(records)
        broken[0]["dual_selector_structural_trace"][5][
            "incidence_node_kinds_by_layer"
        ][0] = [2]
        with self.assertRaisesRegex(Audit.AuditError, "structural replay"):
            Audit.audit_records(broken, freeze, FREEZE_SHA, standalone)

    def test_recovery_expands_partial_cell_to_whole_triad(self):
        freeze = fake_freeze()
        journal, rescan = fake_journal(freeze, task=2)
        plan = Recovery.recovery_plan(
            journal, freeze, FREEZE_SHA, rescan, copy.deepcopy(rescan)
        )
        self.assertEqual(plan["array_tasks"], [2])
        self.assertEqual(plan["whole_triad_cells"], [4, 5, 6])
        options = Recovery.sbatch_options(plan, "metric-choice-recovery")
        self.assertIn("--array=2", options)
        self.assertFalse(any("%" in option for option in options))

    def test_recovery_receipts_reject_boolean_integer_aliases(self):
        freeze = fake_freeze()
        journal, rescan = fake_journal(freeze, task=1)
        mutated = copy.deepcopy(rescan)
        mutated["rows"][0]["array_task"] = True
        mutated["rows_sha256"] = hashlib.sha256(
            P.canonical_json(mutated["rows"])
        ).hexdigest()
        with self.assertRaises(Recovery.RecoveryError):
            Recovery.recovery_plan(
                journal, freeze, FREEZE_SHA, mutated, copy.deepcopy(mutated)
            )

    def test_active_and_semantic_failure_block_recovery(self):
        for state in (Recovery.ACTIVE, Recovery.SEMANTIC_FAILURE):
            freeze = fake_freeze()
            journal, rescan = fake_journal(freeze, task=1, state=state)
            with self.assertRaises(Recovery.RecoveryError):
                Recovery.recovery_plan(
                    journal, freeze, FREEZE_SHA, rescan, copy.deepcopy(rescan)
                )

    def test_zero_interrupted_triads_is_explicit_no_submit(self):
        freeze = fake_freeze()
        journal, rescan = fake_journal(freeze)
        plan = Recovery.recovery_plan(
            journal, freeze, FREEZE_SHA, rescan, copy.deepcopy(rescan)
        )
        self.assertFalse(plan["submission_required"])
        self.assertIsNone(plan["array_spec"])
        with self.assertRaises(Recovery.RecoveryError):
            Recovery.sbatch_options(plan, "unused")

    def test_coordinator_archives_actual_entries_and_submits_whole_complete_triad(self):
        freeze = fake_freeze()
        triad = list(P.triad_cells(2))
        snapshot = fake_scheduler_snapshot(
            freeze, task=2, started=triad, completed=triad
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            experiment = root / "experiment"
            experiment.mkdir()
            for cell in triad:
                make_run(experiment, cell, ("driver.log", "properties"))
            job = root / "recovery.sh"
            raw = make_recovery_job(job, freeze, "2")
            submitter = mock.Mock(return_value="77")
            with mock.patch.object(
                Transport, "archive_regular_entries",
                wraps=Transport.archive_regular_entries,
            ) as archive:
                result = Recovery.coordinate_recovery(
                    snapshot, freeze, FREEZE_SHA,
                    experiment_root=experiment,
                    archive_root=root / "archive",
                    receipt_root=root / "receipts",
                    job_file=job, expected_job_file=job,
                    submitter=submitter,
                )
            self.assertEqual(archive.call_count, 3)
            self.assertEqual(result["plan"]["array_tasks"], [2])
            self.assertEqual(result["plan"]["whole_triad_cells"], triad)
            self.assertEqual(result["submission"]["job_id"], "77")
            options, pinned = submitter.call_args.args
            self.assertEqual(pinned, raw)
            self.assertIn("--array=2", options)
            self.assertIn("--no-requeue", options)
            for cell in triad:
                source = Recovery._run_directory(experiment, cell)
                self.assertFalse((source / "driver.log").exists())
                archived = root / "archive" / "array-002" / "attempt-002" / (
                    "cell-{:05d}".format(cell)
                )
                self.assertEqual(
                    sorted(path.name for path in archived.iterdir()),
                    ["driver.log", "properties"],
                )
            bindings = result["journal"]["entries"][1]["archive_manifests"]
            self.assertEqual([row["cell"] for row in bindings], triad)

    def test_coordinator_empty_recovery_never_opens_job_or_submits(self):
        freeze = fake_freeze()
        snapshot = fake_scheduler_snapshot(freeze)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            experiment = root / "experiment"
            experiment.mkdir()
            submitter = mock.Mock()
            with mock.patch.object(
                Recovery.CampaignIO, "read_regular_exact",
                side_effect=AssertionError("job file was opened"),
            ):
                result = Recovery.coordinate_recovery(
                    snapshot, freeze, FREEZE_SHA,
                    experiment_root=experiment,
                    archive_root=root / "receipts" / "archive",
                    receipt_root=root / "receipts",
                    submitter=submitter,
                )
            self.assertFalse(result["plan"]["submission_required"])
            self.assertIsNone(result["submission"])
            submitter.assert_not_called()

    def test_coordinator_rejects_fabricated_scheduler_accounting(self):
        freeze = fake_freeze()
        snapshot = fake_scheduler_snapshot(
            freeze, task=1, started=[], completed=[]
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            experiment = root / "experiment"
            experiment.mkdir()
            triad = list(P.triad_cells(1))
            make_run(experiment, triad[0], ("driver.log",))
            for cell in triad[1:]:
                make_run(experiment, cell)
            job = root / "recovery.sh"
            make_recovery_job(job, freeze, "1")
            submitter = mock.Mock()
            with self.assertRaisesRegex(Recovery.RecoveryError, "omitted"):
                Recovery.coordinate_recovery(
                    snapshot, freeze, FREEZE_SHA,
                    experiment_root=experiment,
                    archive_root=root / "archive",
                    receipt_root=root / "receipts",
                    job_file=job, expected_job_file=job,
                    submitter=submitter,
                )
            submitter.assert_not_called()

    def test_coordinator_rejects_leftover_symlink_fifo_race_and_collision(self):
        freeze = fake_freeze()
        snapshot = fake_scheduler_snapshot(freeze, task=1)
        triad = list(P.triad_cells(1))
        for attack in ("leftover", "symlink", "fifo", "ancestor-race", "collision"):
            with self.subTest(attack=attack), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                experiment = root / "experiment"
                experiment.mkdir()
                started = make_run(experiment, triad[0], ("driver.log",))
                for cell in triad[1:]:
                    make_run(experiment, cell)
                job = root / "recovery.sh"
                make_recovery_job(job, freeze, "1")
                archive_root = root / "archive"
                receipt_root = root / "receipts"
                submitter = mock.Mock(return_value="77")
                stack = []
                if attack == "symlink":
                    (started / "driver.log").unlink()
                    (started / "driver.log").symlink_to(started / "run")
                elif attack == "fifo":
                    (started / "driver.log").unlink()
                    os.mkfifo(started / "driver.log")
                elif attack == "collision":
                    collision = archive_root / "array-001/attempt-002/cell-00001"
                    collision.mkdir(parents=True)
                elif attack == "leftover":
                    real_archive = Transport.archive_regular_entries

                    def inject(*args, **kwargs):
                        manifest = real_archive(*args, **kwargs)
                        (started / "reappeared").write_bytes(b"race")
                        return manifest

                    stack.append(mock.patch.object(
                        Transport, "archive_regular_entries", side_effect=inject
                    ))
                elif attack == "ancestor-race":
                    real_listdir = Transport.os.listdir
                    raced = False

                    def replace_ancestor(descriptor):
                        nonlocal raced
                        names = real_listdir(descriptor)
                        if not raced:
                            raced = True
                            bucket = started.parent
                            bucket.rename(experiment / "old-bucket")
                        return names

                    stack.append(mock.patch.object(
                        Transport.os, "listdir", side_effect=replace_ancestor
                    ))
                for context in stack:
                    context.start()
                try:
                    with self.assertRaises(Recovery.RecoveryError):
                        Recovery.coordinate_recovery(
                            snapshot, freeze, FREEZE_SHA,
                            experiment_root=experiment,
                            archive_root=archive_root,
                            receipt_root=receipt_root,
                            job_file=job, expected_job_file=job,
                            submitter=submitter,
                        )
                finally:
                    for context in reversed(stack):
                        context.stop()
                submitter.assert_not_called()

    def test_pinned_submit_seals_bytes_and_sanitizes_exact_executable_handoff(self):
        raw = b"#!/bin/bash\ntrue\n"
        with tempfile.TemporaryDirectory() as temporary:
            executable = Path(temporary) / "sbatch"
            executable_bytes = b"synthetic pinned sbatch executable\n"
            executable.write_bytes(executable_bytes)
            executable.chmod(0o755)
            executable_sha = hashlib.sha256(executable_bytes).hexdigest()

            def inspect_handoff(command, **kwargs):
                self.assertEqual(command[0], str(executable))
                self.assertEqual(command[1], "--parsable")
                self.assertIn("--export=NONE", command)
                job_fd = int(command[-1].rsplit("/", 1)[1])
                executable_fd = int(kwargs["executable"].rsplit("/", 1)[1])
                self.assertEqual(kwargs["pass_fds"], (executable_fd, job_fd))
                self.assertEqual(kwargs["env"], {"LANG": "C", "LC_ALL": "C"})
                self.assertFalse(any(
                    name.startswith("SBATCH_") or name.startswith("PYTHON")
                    or name in {"PATH", "VIRTUAL_ENV", "LD_PRELOAD", "LD_LIBRARY_PATH"}
                    for name in kwargs["env"]
                ))
                self.assertEqual(os.pread(job_fd, len(raw) + 1, 0), raw)
                self.assertEqual(
                    os.pread(executable_fd, len(executable_bytes) + 1, 0),
                    executable_bytes,
                )
                seals = fcntl.fcntl(job_fd, fcntl.F_GET_SEALS)
                required = (
                    fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW
                    | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
                )
                self.assertEqual(seals, required)
                with self.assertRaises(OSError) as error:
                    os.pwrite(job_fd, b"X", 0)
                self.assertEqual(error.exception.errno, errno.EPERM)
                return mock.Mock(stdout="789\n")

            with mock.patch.object(
                Recovery, "SBATCH_EXECUTABLE", executable
            ), mock.patch.object(
                Recovery, "SBATCH_EXECUTABLE_SHA256", executable_sha
            ), mock.patch.object(
                Recovery.subprocess, "run", side_effect=inspect_handoff
            ) as child:
                job_id = Recovery._submit_pinned(["--export=NONE"], raw)
            self.assertEqual(job_id, "789")
            child.assert_called_once()
            with self.assertRaisesRegex(Recovery.RecoveryError, "contract"):
                Recovery._submit_pinned(
                    ["--export=NONE", "--export=ALL"], raw
                )


if __name__ == "__main__":
    unittest.main()
