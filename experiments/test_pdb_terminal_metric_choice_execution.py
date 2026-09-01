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
import pdb_terminal_metric_choice_execution as Coordinator
import pdb_confirmation_run_cell as RunCell
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_recovery as Recovery
import pdb_terminal_metric_choice_runner as Runner
import pdb_terminal_metric_choice_transport as Transport
from test_pdb_terminal_metric_choice_protocol import fake_freeze, fake_standalone
from test_pdb_terminal_metric_choice_parser import (
    differing_events, same_pool_events, short_probe_events, encode,
)
import pdb_terminal_metric_choice_parser as Trace


FREEZE_SHA = "f" * 64


def hardware_bytes(model="Synthetic CPU", architecture="x86_64"):
    return RunCell._canonical_json_line({
        "schema": RunCell.HARDWARE_ATTESTATION_SCHEMA,
        "processor_model": model,
        "architecture": architecture,
    })


class LabPathContractTest(unittest.TestCase):
    def test_fetched_properties_use_lab_810_filename(self):
        self.assertEqual(Runner.EVAL_PROPERTIES.name, "properties")
        self.assertEqual(
            Runner.EVAL_PROPERTIES.parent,
            Path(str(Runner.EXPERIMENT_PATH) + "-eval"),
        )


def _identity(pattern_index, incidence, mj):
    return {
        "pattern_index": pattern_index,
        "sources": ["empty"] if pattern_index == 0 else ["bdd_prefix"],
        "pattern": [] if pattern_index == 0 else [0],
        "value_cap": None,
        "terminal_incidence": incidence,
        "masked_joint": mj,
    }


def fake_records(*, differing_tasks=100, short_probe_tasks=0):
    freeze = fake_freeze()
    properties = Runner.build_manifest_properties(freeze, FREEZE_SHA)
    mapping = Runner.build_manifest(freeze, FREEZE_SHA)["cells"]
    certificates = {
        (differs, mode): Trace.certify_trace(
            encode((differing_events if differs else same_pool_events)(mode)), mode
        )
        for differs in (False, True) for mode in P.MODES
    }
    short_certificates = {
        mode: Trace.certify_trace(encode(short_probe_events()), mode)
        for mode in P.MODES
    }
    records = []
    for cell in mapping:
        task_index = int(cell["problem"][1:4])
        differs = task_index < differing_tasks
        short = task_index >= P.COHORT_TASKS - short_probe_tasks
        certificate = (
            short_certificates[cell["algorithm"]]
            if short else certificates[(differs, cell["algorithm"])]
        )
        total_time = {
            P.INCIDENCE_MODE: 100.0,
            P.MJ_MODE: 300.0,
            P.MATCHED_MODE: 400.0,
        }[cell["algorithm"]]
        result_fields = (
            (
                "structural_trace", "structural_trace_sha256",
                "probe_completed_layers",
            ) if short else (
                "structural_trace", "structural_trace_sha256", "pool_sha256",
                "normalized_pool", "normalized_pool_sha256",
                "state_profiles_sha256", "incidence_projection_sha256",
                "incidence_v3_projection_sha256", "preselection_sha256",
                "reference_identity", "incidence_winner_identity",
                "masked_joint_winner_identity", "selected_identity",
                "selected_differs_from_reference",
                "incidence_and_mj_winners_differ", "work_signature",
                "probe_completed_layers",
            )
        )
        overhead_fields = (
            "probe_cpu_seconds", "probe_wall_seconds",
            "probe_peak_memory_before_kb", "probe_peak_memory_after_kb",
            "probe_peak_memory_delta_kb",
        ) + (() if short else (
            "selection_cpu_seconds", "selection_wall_seconds",
            "selection_peak_memory_before_kb",
            "selection_peak_memory_after_kb",
            "selection_peak_memory_delta_kb",
        ))
        outcome = (
            {"coverage": 0, "planner_exit_code": 34}
            if short else {
                "coverage": 1, "planner_exit_code": 0,
                "total_time": total_time,
            }
        )
        record = {
            **cell, **properties, **outcome,
            "id": [cell["algorithm"], cell["domain"], cell["problem"]],
            "component_options": ["--search", P.SEARCHES[cell["algorithm"]]],
            "driver_options": [
                "--overall-time-limit", "1800s",
                "--overall-memory-limit", "24576M",
                "--build", "release_no_lp",
            ],
            "build_options": ["release_no_lp"],
            "local_revision": P.REQUIRED_PLANNER_REVISION,
            "global_revision": P.REQUIRED_PLANNER_REVISION,
            "dual_selector_trace_schema": P.DUAL_TRACE_SCHEMA,
            "dual_selector_trace_certified": True,
            "dual_selector_trace_validation_error": None,
            "dual_selector_trace_status": certificate["status"],
            **{
                "dual_selector_" + key: certificate[key]
                for key in (*result_fields, *overhead_fields)
            },
        }
        records.append(record)
    return records


def as_short_record(record, *, completed_layers=8):
    row = copy.deepcopy(record)
    certificate = Trace.certify_trace(
        encode(short_probe_events(completed_layers)), row["algorithm"]
    )
    for field in Audit.COMPLETE_ONLY_RESULT_FIELDS:
        row.pop(field, None)
    for field in list(row):
        if field.startswith("dual_selector_selection_"):
            row.pop(field)
    row.update({
        "coverage": 0,
        "planner_exit_code": 34,
        "dual_selector_trace_status": "short_probe",
        "dual_selector_structural_trace": certificate["structural_trace"],
        "dual_selector_structural_trace_sha256": certificate[
            "structural_trace_sha256"
        ],
        "dual_selector_probe_completed_layers": certificate[
            "probe_completed_layers"
        ],
    })
    return row


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
    scheduler_rows = []
    scheduler_contract_rows = []
    for array_task in range(1, 301):
        triad = list(P.triad_cells(array_task))
        if array_task == task:
            scheduler_state = "NODE_FAIL"
            exit_code = "0:0"
            entry = {
                "array_task": array_task, "attempt": 2, "job_id": "42",
                "state": Recovery.INTERRUPTED,
                "started_cells": list(started if started is not None else triad[:1]),
                "completed_cells": list(completed if completed is not None else []),
            }
        else:
            scheduler_state = "COMPLETED"
            exit_code = "0:0"
            entry = {
                "array_task": array_task, "attempt": 1, "job_id": "42",
                "state": Recovery.COMPLETE, "started_cells": triad,
                "completed_cells": triad,
            }
        entries.append(entry)
        scheduler_rows.append({
            "array_task": array_task,
            "job_id_raw": "42_{}".format(array_task),
            "state": scheduler_state,
            "exit_code": exit_code,
            "node": "synthetic-node",
            "elapsed_raw": 1,
            "partition": "fat",
        })
        scheduler_contract_rows.append({
            "array_task": array_task,
            "account": P.ACCOUNT,
            "partition": "fat",
            "qos": "normal",
            "req_cpus": 1,
            "req_mem": freeze["design"]["scheduler_memory"],
            "time_limit": freeze["design"]["scheduler_time_limit"],
            "state": scheduler_state,
            "exit_code": exit_code,
            "job_name": Runner.EXPECTED_JOB_NAME,
        })
    return {
        "schema": Recovery.SCHEDULER_SNAPSHOT_SCHEMA,
        "freeze_sha256": FREEZE_SHA,
        "primary_launch_receipt_sha256": "a" * 64,
        "run_cell_mapping_sha256": freeze["design"]["run_cell_mapping_sha256"],
        "scheduler_contract": Runner.build_manifest(
            freeze, FREEZE_SHA
        )["transport"],
        "scheduler_rows": scheduler_rows,
        "scheduler_contract_rows": scheduler_contract_rows,
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


def fake_tree_manifest(paths):
    rows = [
        {"path": path, "sha256": "d" * 64, "size": 1}
        for path in sorted(paths)
    ]
    payload = b"".join(
        row["path"].encode("ascii") + b"\0"
        + bytes.fromhex(row["sha256"])
        for row in rows
    )
    return {
        "files": rows, "file_count": len(rows),
        "tree_sha256": hashlib.sha256(payload).hexdigest(),
    }


def fake_execution_receipt(freeze):
    rows = []
    contracts = []
    entries = []
    for task in range(1, P.EXPECTED_ARRAY_TASKS + 1):
        triad = list(P.triad_cells(task))
        rows.append({
            "array_task": task, "job_id_raw": "42_{}".format(task),
            "state": "COMPLETED", "exit_code": "0:0",
            "node": "synthetic-node", "elapsed_raw": 1,
            "partition": "fat",
        })
        contracts.append({
            "array_task": task, "account": P.ACCOUNT, "partition": "fat",
            "qos": "normal", "req_cpus": 1,
            "req_mem": freeze["design"]["scheduler_memory"],
            "time_limit": freeze["design"]["scheduler_time_limit"],
            "state": "COMPLETED", "exit_code": "0:0",
            "job_name": Runner.EXPECTED_JOB_NAME,
        })
        entries.append({
            "array_task": task, "attempt": 1, "job_id": "42",
            "state": Recovery.COMPLETE, "started_cells": triad,
            "completed_cells": triad,
        })
    dynamic = []
    for cell in range(1, P.CELL_COUNT + 1):
        relative = Coordinator._run_directory(cell).relative_to(
            Runner.EXPERIMENT_PATH
        )
        dynamic.extend(
            (relative / name).as_posix()
            for name in (
                "driver.err", "driver.log", P.SELECTOR_TRACE,
                RunCell.HARDWARE_ATTESTATION_NAME,
            )
        )
    return {
        "schema": Coordinator.EXECUTION_SCHEMA,
        "freeze_sha256": FREEZE_SHA,
        "primary_launch_receipt_sha256": "a" * 64,
        "primary_job_id": "42",
        "primary_scheduler_rows": rows,
        "primary_scheduler_contract_rows": contracts,
        "recovery_launch_receipt_sha256": None,
        "recovery_job_id": None,
        "recovery_source_snapshot_sha256": None,
        "recovery_scheduler_rows": [],
        "recovery_scheduler_contract_rows": [],
        "effective_entries": entries,
        "effective_entries_sha256": hashlib.sha256(
            P.canonical_json(entries)
        ).hexdigest(),
        "state_counts": {Recovery.COMPLETE: P.EXPECTED_ARRAY_TASKS},
        "complete_cells": P.CELL_COUNT,
        "started_cells": P.CELL_COUNT,
        "scheduler_contract": Transport.scheduler_contract(freeze, P.ACCOUNT),
        "dynamic_cell_manifest": fake_tree_manifest(dynamic),
        "hardware": {
            "hardware_attestation_schema": RunCell.HARDWARE_ATTESTATION_SCHEMA,
            "hardware_attestation_files": P.CELL_COUNT,
            "hardware_records_sha256": "c" * 64,
            "processor_model_counts": {"Synthetic CPU": P.CELL_COUNT},
            "architecture_counts": {"x86_64": P.CELL_COUNT},
        },
        "primary_log_manifest": fake_tree_manifest(["slurm.err", "slurm.log"]),
        "recovery_log_manifest": None,
    }


class ExecutionTest(unittest.TestCase):
    MAPPING_SHA = "e" * 64

    def test_launch_requires_all_ancestors_and_full_committed_closure(self):
        freeze = fake_freeze()
        commit = "9" * 40
        bindings = {"experiments/synthetic": FREEZE_SHA}
        with mock.patch.object(
            Coordinator.JJ, "require_ancestor"
        ) as ancestor, mock.patch.object(
            Coordinator.Freeze, "_launch_closure_bindings",
            return_value=bindings,
        ) as build_closure, mock.patch.object(
            Coordinator.Freeze, "_attest_repository_closure",
        ) as attest:
            Coordinator._validate_repository_commit(
                freeze, commit, FREEZE_SHA
            )
        self.assertEqual(
            [call.args[1] for call in ancestor.call_args_list],
            list(Coordinator._required_launch_ancestors(freeze)),
        )
        build_closure.assert_called_once_with(freeze, FREEZE_SHA)
        attest.assert_called_once_with(commit, bindings)
        with mock.patch.object(
            Coordinator.JJ, "require_ancestor"
        ), mock.patch.object(
            Coordinator.Freeze, "_launch_closure_bindings",
            return_value=bindings,
        ), mock.patch.object(
            Coordinator.Freeze, "_attest_repository_closure",
            side_effect=Coordinator.Freeze.FreezeError("mismatch"),
        ), self.assertRaisesRegex(Coordinator.ExecutionError, "closure changed"):
            Coordinator._validate_repository_commit(freeze, commit, FREEZE_SHA)

    def test_launch_uses_live_snapshot_and_rejects_dirty_working_copy(self):
        freeze = fake_freeze()
        commit = "9" * 40
        with mock.patch.object(
            Coordinator.JJ, "working_copy_diff_summary", return_value=""
        ) as stale_summary, mock.patch.object(
            Coordinator.JJ, "live_working_copy_diff_summary", return_value=""
        ) as live_summary, mock.patch.object(
            Coordinator.JJ, "parent_commit", return_value=commit,
        ), mock.patch.object(
            Coordinator, "_validate_repository_commit"
        ) as validate:
            self.assertEqual(
                Coordinator._clean_repository_commit(freeze, FREEZE_SHA), commit
            )
        stale_summary.assert_not_called()
        live_summary.assert_called_once_with(P.REPO)
        validate.assert_called_once_with(freeze, commit, FREEZE_SHA)
        with mock.patch.object(
            Coordinator.JJ, "working_copy_diff_summary", return_value=""
        ) as stale_summary, mock.patch.object(
            Coordinator.JJ, "live_working_copy_diff_summary", return_value="M source"
        ), mock.patch.object(
            Coordinator.JJ, "parent_commit"
        ) as parent, self.assertRaisesRegex(
            Coordinator.ExecutionError, "clean working copy"
        ):
            Coordinator._clean_repository_commit(freeze, FREEZE_SHA)
        stale_summary.assert_not_called()
        parent.assert_not_called()

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
        broken = copy.deepcopy(records)
        broken[0]["dual_selector_selected_differs_from_reference"] = not broken[
            0
        ]["dual_selector_selected_differs_from_reference"]
        with self.assertRaisesRegex(Audit.AuditError, "parsed fields"):
            Audit.audit_records(broken, freeze, FREEZE_SHA, standalone)
        broken = copy.deepcopy(records)
        broken[0]["dual_selector_trace_validation_error"] = "contradiction"
        with self.assertRaisesRegex(Audit.AuditError, "certified campaign outcome"):
            Audit.audit_records(broken, freeze, FREEZE_SHA, standalone)

    def test_audit_accepts_only_symmetric_certified_short_triads(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        records = fake_records(short_probe_tasks=1)
        result = Audit.audit_records(records, freeze, FREEZE_SHA, standalone)
        self.assertEqual(result["status_counts"], {
            "complete": 299, "short_probe": 1,
        })
        self.assertEqual(result["status_family_counts"], {
            "complete": 30, "short_probe": 1,
        })
        self.assertEqual(result["full_preselection_triads"], 299)
        self.assertEqual(result["certified_short_probe_triads"], 1)
        self.assertEqual(result["differing_winner_tasks"], 100)

        mixed = fake_records()
        mixed[-3] = as_short_record(mixed[-3])
        with self.assertRaisesRegex(Audit.AuditError, "status differs"):
            Audit.audit_records(mixed, freeze, FREEZE_SHA, standalone)

        mismatched = fake_records(short_probe_tasks=1)
        mismatched[-1] = as_short_record(
            mismatched[-1], completed_layers=7
        )
        with self.assertRaisesRegex(Audit.AuditError, "structure differs"):
            Audit.audit_records(mismatched, freeze, FREEZE_SHA, standalone)

    def test_short_audit_rejects_outcome_and_selection_field_drift(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        mutations = {
            "exit": lambda row: row.__setitem__("planner_exit_code", 0),
            "coverage": lambda row: row.__setitem__("coverage", 1),
            "complete field": lambda row: row.__setitem__(
                "dual_selector_reference_identity", {}
            ),
            "selection field": lambda row: row.__setitem__(
                "dual_selector_selection_wall_seconds", 0.0
            ),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                records = fake_records(short_probe_tasks=1)
                mutate(records[-1])
                with self.assertRaisesRegex(
                    Audit.AuditError, "short probe outcome contract"
                ):
                    Audit.audit_records(
                        records, freeze, FREEZE_SHA, standalone
                    )

    def test_complete_audit_rejects_outcome_metadata_drift(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        mutations = {
            "unsupported exit": lambda row: row.__setitem__(
                "planner_exit_code", 34
            ),
            "boolean exit": lambda row: row.__setitem__(
                "planner_exit_code", True
            ),
            "nonbinary coverage": lambda row: row.__setitem__("coverage", 2),
            "boolean coverage": lambda row: row.__setitem__("coverage", True),
            "solved failure": lambda row: row.__setitem__(
                "planner_exit_code", 23
            ),
            "unsolved success": lambda row: row.update({
                "coverage": 0, "planner_exit_code": 0,
            }),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label):
                records = fake_records()
                mutate(records[0])
                with self.assertRaisesRegex(
                    Audit.AuditError, "complete trace outcome contract"
                ):
                    Audit.audit_records(
                        records, freeze, FREEZE_SHA, standalone
                    )

    def test_audit_rechecks_probe_and_selection_overhead(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        broken_probe = fake_records()
        broken_probe[0].pop("dual_selector_probe_wall_seconds")
        with self.assertRaisesRegex(Audit.AuditError, "probe.*overhead"):
            Audit.audit_records(
                broken_probe, freeze, FREEZE_SHA, standalone
            )

        broken_selection = fake_records()
        broken_selection[0][
            "dual_selector_selection_peak_memory_delta_kb"
        ] += 1
        with self.assertRaisesRegex(Audit.AuditError, "selection.*overhead"):
            Audit.audit_records(
                broken_selection, freeze, FREEZE_SHA, standalone
            )

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
                seals = fcntl.fcntl(job_fd, Recovery.F_GET_SEALS)
                required = (
                    Recovery.F_SEAL_WRITE | Recovery.F_SEAL_GROW
                    | Recovery.F_SEAL_SHRINK | Recovery.F_SEAL_SEAL
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

    def test_options_only_stdin_submission_uses_verified_executable_bytes(self):
        raw = b"#!/bin/bash\ntrue\n"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "sbatch"
            executable_raw = b"synthetic exact sbatch\n"
            executable.write_bytes(executable_raw)
            executable.chmod(0o755)
            executable_sha = hashlib.sha256(executable_raw).hexdigest()
            options = ["--parsable", "--export=NONE", "--no-requeue"]

            def inspect(command, **kwargs):
                self.assertEqual(command, [str(executable), *options])
                self.assertEqual(kwargs["input"], raw)
                self.assertEqual(kwargs["cwd"], root)
                self.assertEqual(kwargs["env"], Coordinator.SUBMISSION_ENVIRONMENT)
                self.assertEqual(len(kwargs["pass_fds"]), 1)
                descriptor = kwargs["pass_fds"][0]
                self.assertEqual(
                    kwargs["executable"], "/proc/self/fd/{}".format(descriptor)
                )
                self.assertEqual(
                    os.pread(descriptor, len(executable_raw) + 1, 0),
                    executable_raw,
                )
                self.assertNotIn("/proc/self/fd", " ".join(command))
                return mock.Mock(stdout=b"789;synthetic\n", stderr=b"")

            with mock.patch.object(
                Transport.subprocess, "run", side_effect=inspect
            ) as child:
                job_id = Transport.submit_pinned_stdin(
                    executable, executable_sha, options, raw,
                    environment=Coordinator.SUBMISSION_ENVIRONMENT,
                    cwd=root, label="synthetic sbatch",
                )
            self.assertEqual(job_id, "789")
            child.assert_called_once()
            with self.assertRaisesRegex(Transport.TransportError, "options-only"):
                Transport.submit_pinned_stdin(
                    executable, executable_sha,
                    [*options, str(root / "mutable-job")], raw,
                    environment=Coordinator.SUBMISSION_ENVIRONMENT,
                    cwd=root, label="synthetic sbatch",
                )

    def test_exact_submission_journal_reconciliation(self):
        materials = {
            "recorded_utc": "2026-09-01T12:00:00+00:00",
            "job_name": "synthetic-primary",
            "submission_comment": "metric/synthetic-token",
            "submission_token": "synthetic-token",
            "submit_command": [
                str(Coordinator.SBATCH_EXECUTABLE), "--parsable",
                "--export=NONE", "--no-requeue",
            ],
        }
        command = " ".join(materials["submit_command"])
        journal = "\n".join((
            "42|synthetic-primary|metric/synthetic-token|{}".format(command),
            "42_1|synthetic-primary||",
            "42_2|synthetic-primary||",
        ))
        with mock.patch.object(Coordinator, "_pinned_sacct", return_value=journal):
            self.assertEqual(
                Coordinator._journal_job_ids(materials, {1, 2}), ["42"]
            )
        with mock.patch.object(Coordinator, "_pinned_sacct", return_value=""):
            self.assertEqual(Coordinator._journal_job_ids(materials, {1, 2}), [])
        ambiguous = journal + "\n43_1|synthetic-primary||"
        with mock.patch.object(
            Coordinator, "_pinned_sacct", return_value=ambiguous
        ), self.assertRaises(Coordinator.ExecutionError):
            Coordinator._journal_job_ids(materials, {1, 2})

    def test_scheduler_classification_is_fail_closed(self):
        triad = list(P.triad_cells(1))
        complete = {"array_task": 1, "state": "COMPLETED", "exit_code": "0:0"}
        self.assertEqual(
            Coordinator._classify(complete, triad, triad), Recovery.COMPLETE
        )
        self.assertEqual(
            Coordinator._classify(complete, triad, triad[:2]),
            Recovery.SEMANTIC_FAILURE,
        )
        for state, expected in (
            ("NODE_FAIL", Recovery.INTERRUPTED),
            ("RUNNING", Recovery.ACTIVE),
            ("TIMEOUT", Recovery.SEMANTIC_FAILURE),
            ("FAILED", Recovery.SEMANTIC_FAILURE),
        ):
            row = {"array_task": 1, "state": state, "exit_code": "1:0"}
            self.assertEqual(Coordinator._classify(row, triad, triad), expected)

    def test_execution_receipt_requires_complete_structural_matrix(self):
        freeze = fake_freeze()
        receipt = fake_execution_receipt(freeze)
        Coordinator._validate_execution_value(
            receipt, freeze, FREEZE_SHA, "a" * 64
        )
        broken = copy.deepcopy(receipt)
        broken["effective_entries"][0]["completed_cells"].pop()
        broken["effective_entries_sha256"] = hashlib.sha256(
            P.canonical_json(broken["effective_entries"])
        ).hexdigest()
        with self.assertRaisesRegex(
            Coordinator.ExecutionError, "effective execution entry"
        ):
            Coordinator._validate_execution_value(
                broken, freeze, FREEZE_SHA, "a" * 64
            )
        broken = copy.deepcopy(receipt)
        dynamic_paths = [
            row["path"] for row in broken["dynamic_cell_manifest"]["files"]
            if row["path"] != (
                Coordinator._run_directory(1).relative_to(
                    Runner.EXPERIMENT_PATH
                ) / RunCell.HARDWARE_ATTESTATION_NAME
            ).as_posix()
        ]
        broken["dynamic_cell_manifest"] = fake_tree_manifest(dynamic_paths)
        with self.assertRaisesRegex(
            Coordinator.ExecutionError, "dynamic cell manifest is incomplete"
        ):
            Coordinator._validate_execution_value(
                broken, freeze, FREEZE_SHA, "a" * 64
            )
        broken = copy.deepcopy(receipt)
        broken["hardware"]["processor_model_counts"] = {"Synthetic CPU": 899}
        with self.assertRaisesRegex(
            Coordinator.ExecutionError, "hardware summary"
        ):
            Coordinator._validate_execution_value(
                broken, freeze, FREEZE_SHA, "a" * 64
            )
        broken = copy.deepcopy(receipt)
        broken["primary_scheduler_rows"][0]["state"] = "TIMEOUT"
        broken["primary_scheduler_contract_rows"][0]["state"] = "TIMEOUT"
        with self.assertRaisesRegex(
            Coordinator.ExecutionError, "terminal-complete"
        ):
            Coordinator._validate_execution_value(
                broken, freeze, FREEZE_SHA, "a" * 64
            )

    def test_live_hardware_summary_requires_one_consistent_triad(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            Runner, "EXPERIMENT_PATH", Path(tmp) / "experiment"
        ), mock.patch.multiple(
            P, CELL_COUNT=3, EXPECTED_ARRAY_TASKS=1
        ):
            for cell in range(1, 4):
                directory = Coordinator._run_directory(cell)
                directory.mkdir(parents=True)
                (directory / RunCell.HARDWARE_ATTESTATION_NAME).write_bytes(
                    hardware_bytes()
                )
            summary = Coordinator._hardware_summary()
            self.assertEqual(summary["hardware_attestation_files"], 3)
            second = (
                Coordinator._run_directory(2) /
                RunCell.HARDWARE_ATTESTATION_NAME
            )
            second.write_bytes(hardware_bytes("Other CPU"))
            with self.assertRaisesRegex(
                Coordinator.ExecutionError, "within an array element"
            ):
                Coordinator._hardware_summary()


if __name__ == "__main__":
    unittest.main()
