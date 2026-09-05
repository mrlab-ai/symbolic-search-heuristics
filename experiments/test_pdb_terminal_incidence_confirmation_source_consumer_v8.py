#!/usr/bin/env python3
"""Adversarial tests for the strict V5/V8 two-origin consumer."""

from __future__ import annotations

import hashlib
import os
import stat
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pdb_terminal_incidence_confirmation_source_consumer_v8 as C


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _root(path: Path, inode: int) -> dict:
    return {
        "path": str(path), "canonical_path": str(path), "mode": "0700",
        "uid": 1, "device": 2, "inode": inode,
    }


def _rows():
    return [
        {"array_task": 0, "state": "COMPLETED", "exit_code": "0:0", "partition": "fat"},
        {"array_task": 1, "state": "FAILED", "exit_code": "2:0", "partition": "fat"},
        {"array_task": 2, "state": "OUT_OF_MEMORY", "exit_code": "0:125", "partition": "fat"},
    ]


def _diagnostic():
    rows = _rows()
    repair_rows = rows[1:]
    return {
        "v5_launch_receipt_sha256": _sha("v5-launch"),
        "v5_source_inventory_sha256": _sha("inventory"),
        "v5_code_manifest_sha256": _sha("v5-code"),
        "v5_launch_receipt": {
            "job_id": "111",
            "benchmark_revision": C.Source.Base.Inventory.BENCHMARK_REVISION,
            "launch_root_identities": {
                "output_dir": _root(C.V5_OUTPUT_DIR, 1),
                "tmpdir_root": _root(C.Launch.V5Launch.Source.TMP_ROOT, 2),
            },
        },
        "v5_scheduler_rows": rows,
        "v5_scheduler_rows_sha256": C._digest(rows),
        "repair_v5_scheduler_rows": repair_rows,
        "reusable_v5_shard_indices": [0],
        "repair_v5_shard_indices": [1, 2],
        "reuse_eligibility_rule": "scheduler state COMPLETED with exit 0:0 only",
        "repair_eligibility_rule": "every other recognized terminal scheduler row and exit code",
        "resource_mapping": C.Launch._resource_mapping(),
        "pre_diagnosis_freeze": {},
        "v8_design_timing_disclosure": C.Launch._design_timing_disclosure(),
    }


def _launch_pair(diagnostic_raw: bytes, diagnostic: dict):
    token = "a" * 24
    code = {
        "code_manifest_sha256": _sha("v8-code"),
        "python_version": "3.12.13", "python_executable": "/python",
        "python_executable_sha256": _sha("python"),
        "python_environment_sha256": _sha("environment"),
        "python_distributions": {},
        "python_requirements_sha256": _sha("requirements"),
    }
    materials = {key: None for key in C.MATERIAL_KEYS}
    capture_identities = {
        stream: {
            "path": str(path), "canonical_path": str(path),
            "device": 2, "inode": inode, "mode": "0400",
            "uid": os.getuid(), "gid": 1, "link_count": 1,
            "bytes_at_intent": 0,
        }
        for stream, path, inode in (
            ("stdout", C.Launch.SBATCH_STDOUT, 101),
            ("stderr", C.Launch.SBATCH_STDERR, 102),
        )
    }
    materials.update({
        "campaign": C.CAMPAIGN,
        "benchmark_revision": C.Source.Base.Inventory.BENCHMARK_REVISION,
        "v5_scheduler_diagnostic_sha256": hashlib.sha256(diagnostic_raw).hexdigest(),
        "v5_launch_receipt_sha256": diagnostic["v5_launch_receipt_sha256"],
        "logical_shards": 3, "candidates": C.CANDIDATES,
        "reusable_v5_shard_indices": [0], "repair_v5_shard_indices": [1, 2],
        "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "reused_v5_shards": 1, "reused_v6_shards": 0,
        "reused_v7_shards": 0,
        "repaired_v5_shards": 2,
        "reuse_eligibility_rule": diagnostic["reuse_eligibility_rule"],
        "repair_scope": "complete original two-candidate shards",
        "whole_campaign_rerun": False,
        "source_support_outcome_blind_selective_repair": True,
        "noncompleted_v5_shards_used": False,
        "array": "1,2", "array_throttle": 0,
        "partition": "fat", "qos": "normal", "account": C.Launch.ACCOUNT,
        "cpus_per_task": 1, "resource_mapping": C.Launch._resource_mapping(),
        "source_inventory_sha256": diagnostic["v5_source_inventory_sha256"],
        "code_manifest_sha256": _sha("v8-code"),
        "slurm_template_sha256": _sha("template"),
        "slurm_program_sha256": _sha("rendered"),
        "slurm_program_bytes": len(b"rendered"),
        "slurm_submission_mode": "stdin", "repository_commit_id": "b" * 40,
        "scoped_repository_files": list(C.SCOPED_FILES),
        "launch_root_identities": {
            "output_dir": _root(C.OUTPUT_DIR, 3),
            "tmpdir_root": _root(C.TMP_ROOT, 4),
        },
        "output_dir": str(C.OUTPUT_DIR), "tmpdir_root": str(C.TMP_ROOT),
        "source_inventory_path": str(C.SOURCE_INVENTORY),
        "candidate_attestation": str(C.CANDIDATE),
        "frozen_attestation": str(C.ATTESTATION),
        "execution_environment": C.Launch.Runtime._execution_environment(code),
        "scheduler_only_partition": True,
        "v5_failure_logs_inspected_by_v8": False,
        "v5_detailed_accounting_inspected_by_v8": False,
        "source_support_outcomes_used_for_v8_design": False,
        "accepted_translation_statuses": ["input-rejected", "success"],
        "translator_timeout_is_infrastructure_failure": True,
        "resource_ceiling_changes_accepted_outcome_classes": False,
        "source_audit_runtime_estimand_recorded": False,
        "cross_campaign_runtime_comparison_authorized": False,
        "scheduler_membership_affects_execution_origin_only": True,
        "v6_runtime_artifacts_used": False,
        "v7_runtime_artifacts_used": False,
        "v5_scheduler_rows_sha256": diagnostic["v5_scheduler_rows_sha256"],
        "v8_design_timing_disclosure": C.Launch._design_timing_disclosure(),
        "v7_launch_intent_sha256": C.Launch.V7_INTENT_SHA256,
        "v7_launch_failure_sha256": C.Launch.V7_LAUNCH_FAILURE_SHA256,
        "scheduler_profile_change_from_v7": ["memory 3000G to 2950G"],
        "v5_output_namespace_enumerated_by_v8": False,
        "v5_output_triplet_bytes_read_before_v8_all_success_gate": False,
        "v5_reusable_triplet_read_policy": (
            "only-during-seal-after-v8-all-success-gate"
        ),
        "v5_reusable_selected_tree_commitment_policy": (
            "first-separate-record-at-v8-seal"
        ),
        "v5_source_inventory_read_by_v8": False,
        "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion": (
            False
        ),
        "path_containment_trust_model": C.Launch._path_containment_trust_model(),
        "sbatch_stdout_path": str(C.Launch.SBATCH_STDOUT),
        "sbatch_stderr_path": str(C.Launch.SBATCH_STDERR),
        "sbatch_result_path": str(C.Launch.SBATCH_RESULT),
        "sbatch_capture_initial_identities": capture_identities,
    })
    intent = {
        "schema": C.Launch.LAUNCH_SCHEMA + "/intent", **materials,
        "recorded_utc": "2026-09-05T00:00:00+00:00",
        "submission_token": token,
        "submit_command": C.Launch.Runtime._submit_command(diagnostic, token),
    }
    intent_raw = C._canonical_json_line(intent)
    launch = {
        "schema": C.Launch.LAUNCH_SCHEMA,
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "sbatch_result_sha256": _sha("sbatch-result"),
        "launch_recovered_from_journal": True,
        "job_id": "222",
    }
    return code, intent_raw, intent, C._canonical_json_line(launch), launch


class V8ConsumerTest(unittest.TestCase):
    def test_manifest_closure_contains_consumer_and_tests(self):
        self.assertEqual(tuple(sorted(C.CODE_MANIFEST_FILES)), C.CODE_MANIFEST_FILES)
        for path in (
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v8.py",
            "experiments/test_pdb_terminal_incidence_confirmation_source_consumer_v8.py",
            "experiments/pdb_terminal_incidence_confirmation_safe_io_v7.py",
            "experiments/pdb_terminal_incidence_confirmation_safe_io_v8.py",
            "experiments/test_pdb_terminal_incidence_confirmation_safe_io_v8.py",
        ):
            self.assertIn(path, C.CODE_MANIFEST_FILES)
        self.assertEqual(set(C.SCOPED_FILES), set(C.CODE_MANIFEST_FILES) | {
            C.MANIFEST_RELATIVE,
        })

    def test_v5_ancestry_compatibility_restores_encoder_on_success_and_failure(self):
        original_encoder = C.V6Utilities.V5._canonical_json
        observed = []

        def succeeds(*_args):
            observed.append(C.V6Utilities.V5._canonical_json)
            return {"validated": "v5"}

        with mock.patch.object(
            C.V6Utilities, "_validate_v5_producer", side_effect=succeeds
        ) as validator:
            result = C._validate_v5_producer_ancestry({}, lambda *_: {})
        self.assertEqual(result, {"validated": "v5"})
        validator.assert_called_once()
        self.assertEqual(observed, [C.V6Utilities.V5._canonical_json_line])
        self.assertIs(C.V6Utilities.V5._canonical_json, original_encoder)

        def fails(*_args):
            observed.append(C.V6Utilities.V5._canonical_json)
            raise C.V6Utilities.SourceConsumerError("invalid provenance")

        with (
            mock.patch.object(
                C.V6Utilities, "_validate_v5_producer", side_effect=fails
            ),
            self.assertRaisesRegex(
                C.SourceConsumerError, "invalid V5 producer ancestry"
            ),
        ):
            C._validate_v5_producer_ancestry({}, lambda *_: {})
        self.assertEqual(observed[-1], C.V6Utilities.V5._canonical_json_line)
        self.assertIs(C.V6Utilities.V5._canonical_json, original_encoder)

    def test_diagnostic_consumer_rejects_outcome_or_output_fields(self):
        value = {"schema": "fixture"}
        raw = C._canonical_json_line(value)
        with (
            mock.patch.object(C, "_read_json", return_value=(raw, value)),
            mock.patch.object(C.Launch, "_load_recorded_diagnostic", return_value=(
                hashlib.sha256(raw).hexdigest(), value
            )) as recorded_loader,
            mock.patch.object(
                C.Launch, "_load_diagnostic",
                side_effect=AssertionError("live freeze validator called"),
            ),
            mock.patch.object(C.Launch, "DIAGNOSTIC_FIELDS", frozenset({"schema"})),
        ):
            C._load_diagnostic()
        recorded_loader.assert_called_once_with()
        for forbidden in ("failure_records", "failure_classes", "v5_output_manifest"):
            changed = {"schema": "fixture", forbidden: []}
            changed_raw = C._canonical_json_line(changed)
            with (
                mock.patch.object(C, "_read_json", return_value=(changed_raw, changed)),
                mock.patch.object(C.Launch, "_load_recorded_diagnostic", return_value=(
                    hashlib.sha256(changed_raw).hexdigest(), changed
                )),
                mock.patch.object(
                    C.Launch, "DIAGNOSTIC_FIELDS", frozenset(changed)
                ),
                self.assertRaises(C.SourceConsumerError),
            ):
                C._load_diagnostic()

    def test_launch_contract_is_exact_v8_fixed_profile_and_no_v6_reuse(self):
        diagnostic = _diagnostic()
        raw = C._canonical_json_line(diagnostic)
        code, intent_raw, intent, launch_raw, launch = _launch_pair(raw, diagnostic)
        with (
            mock.patch.object(C, "ARRAY_TASKS", 3),
            mock.patch.object(C, "_manifest", return_value=({}, code)),
            mock.patch.object(
                C.Launch, "_load_sbatch_result",
                return_value=(
                    _sha("sbatch-result"),
                    {"accepted_by_launcher": False, "parsed_job_id": "222"},
                ),
            ),
            mock.patch.object(
                C.Launch.Runtime, "_render_slurm", return_value=b"rendered"
            ),
            mock.patch.object(C, "_read_file", return_value=SimpleNamespace(
                sha256=_sha("template"), raw=b"template"
            )),
        ):
            C._validate_launch(raw, diagnostic, intent_raw, intent, launch_raw, launch)
            for field in ("reused_v6_shards", "v5_failure_logs_inspected_by_v8"):
                changed = dict(launch)
                changed[field] = 1 if field == "reused_v6_shards" else True
                with self.assertRaises(C.SourceConsumerError):
                    C._validate_launch(
                        raw, diagnostic, intent_raw, intent,
                        C._canonical_json_line(changed), changed,
                    )

    def test_recovered_launch_requires_bound_result_and_matching_job(self):
        diagnostic = _diagnostic()
        raw = C._canonical_json_line(diagnostic)
        _code, intent_raw, intent, launch_raw, launch = _launch_pair(
            raw, diagnostic
        )
        with (
            mock.patch.object(
                C.Launch, "_load_sbatch_result",
                side_effect=C.Launch.LaunchAuditError("missing result"),
            ),
            self.assertRaisesRegex(C.SourceConsumerError, "sbatch evidence"),
        ):
            C._validate_launch(
                raw, diagnostic, intent_raw, intent, launch_raw, launch
            )

        with (
            mock.patch.object(
                C.Launch, "_load_sbatch_result",
                return_value=(
                    _sha("sbatch-result"),
                    {"accepted_by_launcher": False, "parsed_job_id": "999"},
                ),
            ),
            self.assertRaisesRegex(C.SourceConsumerError, "launch/intent"),
        ):
            C._validate_launch(
                raw, diagnostic, intent_raw, intent, launch_raw, launch
            )

    def test_selected_tree_schema_excludes_noncompleted_paths(self):
        diagnostic = _diagnostic()
        name_set = C.Launch._v5_reusable_names(diagnostic)
        files = [
            {"path": name, "bytes": 1, "sha256": _sha(name)}
            for name in name_set
        ]
        tree = {
            "root_identity": _root(C.V5_OUTPUT_DIR, 1),
            "files": files, "files_count": len(files),
            "selection_rule": "V5 scheduler COMPLETED 0:0 triplets only",
            "noncompleted_v5_files_opened": False,
        }
        digest = hashlib.sha256()
        digest.update(b"root-identity\0" + C._canonical_json_line(tree["root_identity"]))
        for item in files:
            digest.update(item["path"].encode("ascii") + b"\0"
                          + bytes.fromhex(item["sha256"]))
        tree["sha256"] = digest.hexdigest()
        self.assertEqual(set(C._selected_file_map(tree)), set(name_set))
        extra = dict(tree)
        extra["files"] = files + [{
            "path": "shard-0001-of-0820.json", "bytes": 1,
            "sha256": _sha("extra"),
        }]
        extra["files_count"] += 1
        with self.assertRaises(C.SourceConsumerError):
            C._validate_selected_v5_tree(extra, diagnostic)

        forged = {**tree, "root_identity": _root(C.V5_OUTPUT_DIR, 999)}
        forged_digest = hashlib.sha256()
        forged_digest.update(
            b"root-identity\0"
            + C._canonical_json_line(forged["root_identity"])
        )
        for item in files:
            forged_digest.update(
                item["path"].encode("ascii") + b"\0"
                + bytes.fromhex(item["sha256"])
            )
        forged["sha256"] = forged_digest.hexdigest()
        with (
            mock.patch.object(
                C.SelectedTreeIO, "read_selected_flat_tree"
            ) as live_reader,
            self.assertRaises(C.SourceConsumerError),
        ):
            C._validate_selected_v5_tree(forged, diagnostic)
        live_reader.assert_not_called()

    def test_complete_tree_reader_is_invoked_once_with_exact_contract(self):
        root = _root(C.OUTPUT_DIR, 7)
        receipt = {"root_identity": root}
        files = {"one": {"path": "one", "bytes": 3, "sha256": _sha("one")}}
        live = SimpleNamespace(
            directories=(),
            files=(SimpleNamespace(
                path="one", sha256=_sha("one"), identity={"size": 3},
            ),),
            root_identity={
                "device": root["device"], "inode": root["inode"],
                "uid": root["uid"], "mode": stat.S_IFDIR | 0o700,
            },
        )
        with (
            mock.patch.object(C, "_generic_file_map", return_value=files),
            mock.patch.object(
                C.CompleteTreeIO, "read_streaming_tree", return_value=live
            ) as reader,
        ):
            self.assertEqual(
                C._validate_complete_tree(
                    receipt, C.OUTPUT_DIR, ["one"], root, "fixture"
                ),
                files,
            )
        reader.assert_called_once_with(
            C.OUTPUT_DIR, label="fixture", expected_path=C.OUTPUT_DIR
        )

    def test_seal_stage_chain_uses_the_single_v5_diagnostic_key(self):
        launch_raw = b"launch\n"
        attestation_raw = b"attestation\n"
        attestation = {"records_sha256": _sha("records")}
        diagnostic = {"pre_diagnosis_freeze": {"files_sha256": _sha("pre")}}
        execution = {
            "v5_scheduler_diagnostic_sha256": _sha("diagnostic"),
            "scheduler_rows": [], "scheduler_contract_rows": [],
            "v5_reusable_tree": {"v5": True},
            "v8_output_tree": {"v8": True},
            "v5_reusable_environment_manifest": {"v5-env": True},
            "v8_repair_environment_manifest": {"v8-env": True},
            "union_tree": {"root_identity": {"root": True}},
            "union_sources": [], "union_sources_sha256": _sha("sources"),
        }
        stages = {
            C.SEAL_PLAN: {
                "schema": C.Launch.SEAL_PLAN_SCHEMA,
                "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
                "v5_scheduler_diagnostic_sha256": execution[
                    "v5_scheduler_diagnostic_sha256"
                ],
                "pre_diagnosis_files_sha256": _sha("pre"),
                "scheduler_rows": [], "scheduler_contract_rows": [],
                "v5_reusable_tree": {"v5": True},
                "v8_output_tree": {"v8": True},
                "v5_reusable_environment_manifest": {"v5-env": True},
                "v8_repair_environment_manifest": {"v8-env": True},
                "source_record_count": C.CANDIDATES,
                "source_record_sequence_sha256": _sha("records"),
            },
        }
        raw_by_path = {C.SEAL_PLAN: C._canonical_json_line(stages[C.SEAL_PLAN])}
        execution["seal_plan_sha256"] = hashlib.sha256(
            raw_by_path[C.SEAL_PLAN]
        ).hexdigest()
        stages[C.UNION_ROOT_STAGE] = {
            "schema": C.Launch.UNION_ROOT_STAGE_SCHEMA,
            "seal_plan_sha256": execution["seal_plan_sha256"],
            "root_identity": {"root": True},
        }
        raw_by_path[C.UNION_ROOT_STAGE] = C._canonical_json_line(
            stages[C.UNION_ROOT_STAGE]
        )
        execution["union_root_stage_sha256"] = hashlib.sha256(
            raw_by_path[C.UNION_ROOT_STAGE]
        ).hexdigest()
        stages[C.UNION_STAGE] = {
            "schema": C.Launch.UNION_STAGE_SCHEMA,
            "seal_plan_sha256": execution["seal_plan_sha256"],
            "union_root_stage_sha256": execution["union_root_stage_sha256"],
            "sources": [], "sources_sha256": _sha("sources"),
            "tree": execution["union_tree"],
        }
        raw_by_path[C.UNION_STAGE] = C._canonical_json_line(stages[C.UNION_STAGE])
        execution["union_stage_sha256"] = hashlib.sha256(
            raw_by_path[C.UNION_STAGE]
        ).hexdigest()
        stages[C.CANDIDATE_STAGE] = {
            "schema": C.Launch.CANDIDATE_STAGE_SCHEMA,
            "union_stage_sha256": execution["union_stage_sha256"],
            "candidate_path": str(C.CANDIDATE),
            "candidate_bytes": len(attestation_raw),
            "candidate_sha256": hashlib.sha256(attestation_raw).hexdigest(),
            "records_sha256": _sha("records"),
        }
        raw_by_path[C.CANDIDATE_STAGE] = C._canonical_json_line(
            stages[C.CANDIDATE_STAGE]
        )
        execution["candidate_stage_sha256"] = hashlib.sha256(
            raw_by_path[C.CANDIDATE_STAGE]
        ).hexdigest()
        stages[C.ATTESTATION_STAGE] = {
            "schema": C.Launch.ATTESTATION_STAGE_SCHEMA,
            "candidate_stage_sha256": execution["candidate_stage_sha256"],
            "attestation_path": str(C.ATTESTATION),
            "attestation_bytes": len(attestation_raw),
            "attestation_sha256": hashlib.sha256(attestation_raw).hexdigest(),
        }
        raw_by_path[C.ATTESTATION_STAGE] = C._canonical_json_line(
            stages[C.ATTESTATION_STAGE]
        )
        execution["attestation_stage_sha256"] = hashlib.sha256(
            raw_by_path[C.ATTESTATION_STAGE]
        ).hexdigest()

        with (
            mock.patch.object(
                C, "_read_json",
                side_effect=lambda path, *_: (raw_by_path[path], stages[path]),
            ),
            mock.patch.object(
                C, "_read_file",
                return_value=SimpleNamespace(
                    raw=attestation_raw,
                    sha256=hashlib.sha256(attestation_raw).hexdigest(),
                ),
            ),
        ):
            C._validate_seal_stages(
                attestation_raw, attestation, diagnostic,
                launch_raw, execution,
            )

    def test_scheduler_consumer_rejects_elapsed_in_minimal_rows(self):
        repair = [1]
        token = "a" * 24
        launch = {"submission_token": token}
        row = {"array_task": 1, "state": "COMPLETED", "exit_code": "0:0", "partition": "fat"}
        contract = {
            "array_task": 1, "account": C.Launch.ACCOUNT,
            "partition": "fat", "qos": "normal", "req_cpus": 1,
            "req_mem": "2950G", "time_limit": "3-00:00:00",
            "elapsed": "01:00:00", "state": "COMPLETED",
            "exit_code": "0:0",
            "job_name": C.Launch.JOB_NAME_PREFIX + "-" + token,
        }
        execution = {
            "scheduler_rows": [row], "scheduler_contract_rows": [contract],
            "scheduler_state_counts": {"COMPLETED": 1},
        }
        C._validate_scheduler(execution, launch, repair)
        execution["scheduler_rows"] = [{**row, "elapsed": "01:00:00"}]
        with self.assertRaises(C.SourceConsumerError):
            C._validate_scheduler(execution, launch, repair)

    def test_union_accepts_only_v5_completed_and_v8_repair(self):
        diagnostic = _diagnostic()
        v5_code = {
            key: ({} if key == "python_distributions" else _sha("v5-" + key))
            for key in C.SHARD_CODE_FIELDS
        }
        v8_code = {
            key: ({} if key == "python_distributions" else _sha("v8-" + key))
            for key in C.SHARD_CODE_FIELDS
        }
        diagnostic["v5_launch_receipt"].update(v5_code)
        inventory_sha = _sha("inventory")
        launch = {
            "source_inventory_sha256": inventory_sha,
            "execution_environment": {"python_environment": v8_code},
        }
        v5 = {"shard-0000-of-0820.json": {"sha256": _sha("0")}}
        v8 = {
            "shard-0001-of-0820.json": {"sha256": _sha("1")},
            "shard-0002-of-0820.json": {"sha256": _sha("2")},
        }
        union = {**v5, **v8}
        records = [
            {"candidate_index": index, "marker": "source"}
            for index in range(6)
        ]
        shard_raw = {}
        for index in range(3):
            name = "shard-{:04d}-of-0820.json".format(index)
            code = v5_code if index == 0 else v8_code
            shard_raw[name] = C._canonical_json_line({
                "schema": C.Source.Base.SHARD_SCHEMA,
                "shard_index": index,
                "num_shards": 3,
                "tasks_per_shard": 2,
                "benchmark_revision": (
                    C.Source.Base.Inventory.BENCHMARK_REVISION
                ),
                "translator_source_sha256": (
                    C.Source.Base.TRANSLATOR_SOURCE_SHA256
                ),
                "source_inventory_sha256": inventory_sha,
                **code,
                "tasks": records[2 * index:2 * index + 2],
            })
        sources = []
        for index in range(3):
            name = "shard-{:04d}-of-0820.json".format(index)
            is_v5 = index == 0
            files = v5 if is_v5 else v8
            root = C.V5_OUTPUT_DIR if is_v5 else C.OUTPUT_DIR
            sources.append({
                "shard_index": index,
                "origin": "v5-completed" if is_v5 else "v8-repair",
                "source": str(root / name), "source_sha256": files[name]["sha256"],
                "union": name, "union_sha256": files[name]["sha256"],
            })
        execution = {
            "union_sources": sources, "union_sources_sha256": C._digest(sources),
            "union_tree": {"root_identity": _root(C.UNION_DIR, 9)},
            "attestation_records_sha256": C._digest(records),
        }
        attestation = {"records": records, "records_sha256": C._digest(records)}

        def validate_tree(*_args, **kwargs):
            kwargs["read_callback"](C.UNION_DIR, 123)
            return union

        with (
            mock.patch.object(C, "ARRAY_TASKS", 3),
            mock.patch.object(C, "CANDIDATES", 6),
            mock.patch.object(C, "_generic_file_map", return_value=union),
            mock.patch.object(
                C, "_read_bound_union_leaf",
                side_effect=lambda _fd, name, _frozen: shard_raw[name],
            ),
            mock.patch.object(
                C, "_validate_complete_tree", side_effect=validate_tree
            ),
        ):
            C._validate_union(
                execution, diagnostic, v5, v8, attestation, launch
            )
            sources[1]["origin"] = "v6-repair"
            execution["union_sources_sha256"] = C._digest(sources)
            with self.assertRaises(C.SourceConsumerError):
                C._validate_union(
                    execution, diagnostic, v5, v8, attestation, launch
                )

            sources[1]["origin"] = "v8-repair"
            execution["union_sources_sha256"] = C._digest(sources)
            changed_records = [dict(record) for record in records]
            changed_records[0]["marker"] = "coherently-rewritten-attestation"
            changed_attestation = {
                "records": changed_records,
                "records_sha256": C._digest(changed_records),
            }
            execution["attestation_records_sha256"] = C._digest(
                changed_records
            )
            with self.assertRaisesRegex(
                C.SourceConsumerError, "union/attestation record chain changed"
            ):
                C._validate_union(
                    execution, diagnostic, v5, v8,
                    changed_attestation, launch,
                )

            malformed_name = "shard-0000-of-0820.json"
            original_shard = shard_raw[malformed_name]
            shard_raw[malformed_name] = b"[]\n"
            execution["attestation_records_sha256"] = C._digest(records)
            with self.assertRaisesRegex(
                C.SourceConsumerError, "union shard contract changed"
            ):
                C._validate_union(
                    execution, diagnostic, v5, v8, attestation, launch
                )
            shard_raw[malformed_name] = original_shard

    def test_timeout_aware_record_replay_uses_exact_origin_ceiling(self):
        records = [
            {
                "candidate_index": index,
                "translation": {
                    "status": "success" if index % 2 == 0 else "input-rejected",
                    "timeout_seconds": 28800 if index < 2 else 115200,
                },
            }
            for index in range(4)
        ]
        sources = [
            {"shard_index": 0, "origin": "v5-completed"},
            {"shard_index": 1, "origin": "v8-repair"},
        ]
        observed = []

        def replay(_record):
            observed.append(C.Source.Base.TASK_TIMEOUT_SECONDS)

        original_timeout = C.Source.Base.TASK_TIMEOUT_SECONDS
        with (
            mock.patch.object(C, "ARRAY_TASKS", 2),
            mock.patch.object(C, "CANDIDATES", 4),
            mock.patch.object(C.Source, "TASKS_PER_SHARD", 2),
            mock.patch.object(
                C.Source.Base, "_validate_scan_evidence", side_effect=replay
            ),
        ):
            C._validate_timeout_aware_translation_records(
                {"records": records}, {"union_sources": sources}
            )
        self.assertEqual(observed, [28800, 28800, 115200, 115200])
        self.assertEqual(C.Source.Base.TASK_TIMEOUT_SECONDS, original_timeout)

        for field, invalid in (
            ("status", "timeout"),
            ("timeout_seconds", 28800),
        ):
            changed = [dict(record) for record in records]
            changed[2] = {
                **changed[2],
                "translation": {**changed[2]["translation"], field: invalid},
            }
            with (
                self.subTest(field=field),
                mock.patch.object(C, "ARRAY_TASKS", 2),
                mock.patch.object(C, "CANDIDATES", 4),
                mock.patch.object(C.Source, "TASKS_PER_SHARD", 2),
                self.assertRaises(C.SourceConsumerError),
            ):
                C._validate_timeout_aware_translation_records(
                    {"records": changed}, {"union_sources": sources}
                )

        changed = [dict(record) for record in records]
        changed[0] = {
            **changed[0],
            "translation": {
                **changed[0]["translation"], "timeout_seconds": 115200,
            },
        }
        with (
            mock.patch.object(C, "ARRAY_TASKS", 2),
            mock.patch.object(C, "CANDIDATES", 4),
            mock.patch.object(C.Source, "TASKS_PER_SHARD", 2),
            self.assertRaises(C.SourceConsumerError),
        ):
            C._validate_timeout_aware_translation_records(
                {"records": changed}, {"union_sources": sources}
            )

        mismatched_sources = [dict(source) for source in sources]
        mismatched_sources[1]["shard_index"] = 0
        with (
            mock.patch.object(C, "ARRAY_TASKS", 2),
            mock.patch.object(C, "CANDIDATES", 4),
            mock.patch.object(C.Source, "TASKS_PER_SHARD", 2),
            self.assertRaises(C.SourceConsumerError),
        ):
            C._validate_timeout_aware_translation_records(
                {"records": records}, {"union_sources": mismatched_sources}
            )

    def test_execution_schema_has_two_origins_and_explicit_no_read_flags(self):
        for field in (
            "v8_job_id", "v8_code_manifest_sha256", "v8_output_tree",
            "v8_repair_environment_manifest", "v5_reusable_tree",
            "v5_noncompleted_failure_logs_inspected",
            "v5_failure_detailed_accounting_inspected",
            "noncompleted_v5_files_opened", "reused_v6_shards",
            "accepted_translation_statuses",
            "translator_timeout_is_infrastructure_failure",
            "resource_ceiling_changes_accepted_outcome_classes",
            "v5_output_triplet_bytes_read_before_v8_all_success_gate",
            "v5_reusable_triplet_bytes_read_during_seal_after_v8_all_success_gate",
            "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion",
            "v5_reusable_selected_tree_first_separately_recorded_at_v8_seal",
            "path_containment_trust_model",
        ):
            self.assertIn(field, C.EXECUTION_KEYS)
        for stale in ("v6_job_id", "v6_output_tree", "v6_repair_environment_manifest"):
            self.assertNotIn(stale, C.EXECUTION_KEYS)

    def test_execution_receipt_exact_schema_round_trip(self):
        diagnostic = _diagnostic()
        diagnostic_raw = C._canonical_json_line(diagnostic)
        _code, _intent_raw, _intent, launch_raw, launch = _launch_pair(
            diagnostic_raw, diagnostic
        )
        attestation = {
            "schema": C.ATTESTATION_SCHEMA,
            "source_inventory_sha256": launch["source_inventory_sha256"],
            "code_manifest_sha256": launch["code_manifest_sha256"],
            "confirmation_prelaunch_authorized": True,
            "prelaunch_gate": {"passed": True},
            "records": [{}] * C.CANDIDATES,
            "records_sha256": _sha("records"),
            "cohorts": {"confirmation-a": {"tasks_sha256": _sha("a")}},
            "counts": {"candidates": C.CANDIDATES},
            "translation_status_counts": {"success": C.CANDIDATES},
            "support_exclusion_counts": {},
        }
        attestation_raw = C._canonical_json_line(attestation)
        execution = {key: None for key in C.EXECUTION_KEYS}
        execution.update({
            "schema": C.Launch.EXECUTION_SCHEMA,
            "campaign": C.CAMPAIGN,
            "benchmark_revision": C.Source.Base.Inventory.BENCHMARK_REVISION,
            "logical_shards": 3,
            "candidates": C.CANDIDATES,
            "whole_campaign_rerun": False,
            "source_support_outcome_blind_selective_repair": True,
            "noncompleted_v5_shards_used": False,
            "noncompleted_v5_files_opened": False,
            "v5_noncompleted_failure_logs_inspected": False,
            "v5_failure_detailed_accounting_inspected": False,
            "v8_success_resource_accounting_recorded": True,
            "source_support_outcomes_used_for_v8_design": False,
            "accepted_translation_statuses": ["input-rejected", "success"],
            "translator_timeout_is_infrastructure_failure": True,
            "resource_ceiling_changes_accepted_outcome_classes": False,
            "source_audit_runtime_estimand_recorded": False,
            "cross_campaign_runtime_comparison_authorized": False,
            "scheduler_membership_affects_execution_origin_only": True,
            "v6_runtime_artifacts_used": False,
            "v7_runtime_artifacts_used": False,
            "v8_design_timing_disclosure": C.Launch._design_timing_disclosure(),
            "v7_launch_intent_sha256": C.Launch.V7_INTENT_SHA256,
            "v7_launch_failure_sha256": C.Launch.V7_LAUNCH_FAILURE_SHA256,
            "sbatch_result_sha256": launch["sbatch_result_sha256"],
            "v5_output_namespace_enumerated_by_v8": False,
            "v5_output_triplet_bytes_read_before_v8_all_success_gate": False,
            "v5_reusable_triplet_bytes_read_during_seal_after_v8_all_success_gate": True,
            "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion": False,
            "v5_reusable_selected_tree_first_separately_recorded_at_v8_seal": True,
            "path_containment_trust_model": C.Launch._path_containment_trust_model(),
            "v5_source_inventory_read_by_v8": False,
            "reuse_eligibility_rule": diagnostic["reuse_eligibility_rule"],
            "repair_eligibility_rule": diagnostic["repair_eligibility_rule"],
            "pre_diagnosis_freeze": diagnostic["pre_diagnosis_freeze"],
            "seal_recovery_protocol": "deterministic-exclusive-hash-chain-v1",
            "seal_plan_sha256": _sha("seal-plan"),
            "union_root_stage_sha256": _sha("union-root"),
            "union_stage_sha256": _sha("union"),
            "candidate_stage_sha256": _sha("candidate"),
            "attestation_stage_sha256": _sha("attestation-stage"),
            "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
            "v5_scheduler_diagnostic_sha256": hashlib.sha256(
                diagnostic_raw
            ).hexdigest(),
            "v5_launch_receipt_sha256": diagnostic[
                "v5_launch_receipt_sha256"
            ],
            "v5_job_id": "111", "v8_job_id": "222",
            "reused_v1_shards": 0, "reused_v2_shards": 0,
            "reused_v3_shards": 0, "reused_v4_shards": 0,
            "reused_v5_shards": 1, "reused_v6_shards": 0,
            "reused_v7_shards": 0,
            "reusable_v5_shard_indices": [0],
            "repaired_v5_shards": 2,
            "repair_v5_shard_indices": [1, 2],
            "repair_scope": "complete original two-candidate shards",
            "array_throttle": 0,
            "resource_mapping": C.Launch._resource_mapping(),
            "scheduler_state_counts": {"COMPLETED": 2},
            "scheduler_rows": [], "scheduler_contract_rows": [],
            "v5_reusable_tree": {"selected": True},
            "v8_output_tree": {},
            "v5_reusable_environment_manifest": {},
            "v8_repair_environment_manifest": {},
            "union_sources": [], "union_sources_sha256": _sha("sources"),
            "union_tree": {},
            "source_inventory_sha256": launch["source_inventory_sha256"],
            "v5_code_manifest_sha256": diagnostic[
                "v5_code_manifest_sha256"
            ],
            "v8_code_manifest_sha256": launch["code_manifest_sha256"],
            "execution_environment": launch["execution_environment"],
            "source_audit_complete": True,
            "confirmation_prelaunch_authorized": True,
            "prelaunch_gate": attestation["prelaunch_gate"],
            "attestation_sha256": hashlib.sha256(attestation_raw).hexdigest(),
            "attestation_records_sha256": attestation["records_sha256"],
            "cohort_manifest_sha256": {
                "confirmation-a": _sha("a")
            },
            "counts": attestation["counts"],
            "translation_status_counts": {"success": C.CANDIDATES},
            "support_exclusion_counts": {},
        })
        with (
            mock.patch.object(C, "ARRAY_TASKS", 3),
            mock.patch.object(C, "_validate_seal_stages"),
            mock.patch.object(C, "_validate_scheduler"),
            mock.patch.object(C, "_validate_selected_v5_tree", return_value={}),
            mock.patch.object(
                C, "_validate_complete_tree",
                return_value={
                    C.SOURCE_INVENTORY.name: {
                        "sha256": launch["source_inventory_sha256"]
                    }
                },
            ),
            mock.patch.object(C, "_validate_environment_manifests"),
            mock.patch.object(C, "_validate_union"),
            mock.patch.object(
                C, "_validate_timeout_aware_translation_records"
            ) as timeout_replay,
        ):
            C._validate_execution(
                attestation_raw, attestation, diagnostic_raw, diagnostic,
                launch_raw, launch, execution,
            )
            changed = dict(execution)
            changed[
                "v5_reusable_selected_tree_first_separately_recorded_at_v8_seal"
            ] = False
            with self.assertRaises(C.SourceConsumerError):
                C._validate_execution(
                    attestation_raw, attestation, diagnostic_raw, diagnostic,
                    launch_raw, launch, changed,
                )
        timeout_replay.assert_called_once_with(attestation, execution)

    def test_snapshot_validation_requires_exact_committed_closure(self):
        files = ("a", "b")
        payload = {"a": b"A", "b": b"B"}
        tracked = {key: hashlib.sha256(value).hexdigest() for key, value in payload.items()}
        C._validate_snapshot("a" * 40, files, tracked, lambda _r, _p: payload, "V8")
        with self.assertRaises(C.SourceConsumerError):
            C._validate_snapshot(
                "a" * 40, files, tracked,
                lambda _r, _p: {"a": b"changed", "b": b"B"}, "V8",
            )

    def test_manifest_allows_descendant_paper_edit_but_checks_live_semantics(self):
        records = {
            relative: _sha(relative) for relative in C.CODE_MANIFEST_FILES
        }
        manifest_raw = b"".join(
            "{}  {}\n".format(records[path], path).encode("ascii")
            for path in C.CODE_MANIFEST_FILES
        )
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        v5_launch = {
            "python_version": "3.12.13",
            "python_executable": "/python",
            "python_executable_sha256": _sha("python"),
            "python_environment_sha256": _sha("environment"),
            "python_distributions": {},
            "python_requirements_sha256": _sha("requirements"),
        }
        launch = {"code_manifest_sha256": manifest_sha}
        diagnostic = {"v5_launch_receipt": v5_launch}
        read_paths = []

        def read(path, _expected, _label):
            read_paths.append(path)
            if path == C.CODE_MANIFEST:
                return SimpleNamespace(raw=manifest_raw, sha256=manifest_sha)
            relative = path.relative_to(C.REPO).as_posix()
            if relative == "paper/paper.tex":
                raise AssertionError("descendant paper bytes must not be read")
            return SimpleNamespace(raw=b"semantic", sha256=records[relative])

        with mock.patch.object(C, "_read_file", side_effect=read):
            loaded, _environment = C._manifest(launch, diagnostic)
        self.assertEqual(loaded, records)
        self.assertEqual(
            set(read_paths[1:]),
            {C.REPO / relative for relative in C.LIVE_SEMANTIC_REPLAY_FILES},
        )

        def changed_semantic(path, _expected, _label):
            if path == C.CODE_MANIFEST:
                return SimpleNamespace(raw=manifest_raw, sha256=manifest_sha)
            return SimpleNamespace(raw=b"changed", sha256="0" * 64)

        with (
            mock.patch.object(C, "_read_file", side_effect=changed_semantic),
            self.assertRaisesRegex(
                C.SourceConsumerError, "live semantic replay code changed"
            ),
        ):
            C._manifest(launch, diagnostic)

    def test_full_loader_uses_pinned_design_but_live_semantic_replay(self):
        semantic_files = tuple(C.LIVE_SEMANTIC_REPLAY_FILES)
        prediagnosis_files = tuple(sorted((*semantic_files, "paper/paper.tex")))
        design_bytes = {
            semantic_files[0]: b"frozen semantic producer\n",
            semantic_files[1]: b"frozen inventory semantics\n",
            "paper/paper.tex": b"frozen prediagnosis paper\n",
        }
        prediagnosis_revision = "a" * 40
        producer_revision = "b" * 40
        freeze_files = [
            {
                "path": path,
                "bytes": len(design_bytes[path]),
                "sha256": hashlib.sha256(design_bytes[path]).hexdigest(),
            }
            for path in prediagnosis_files
        ]
        v5_code_raw = b"frozen V5 code manifest\n"
        v5_intent_raw = b"frozen V5 launch intent\n"
        v5_launch_raw = b"frozen V5 launch receipt\n"
        diagnostic = {
            "pre_diagnosis_freeze": {
                "repository_commit_id": prediagnosis_revision,
                "files": freeze_files,
            },
            "v5_code_manifest_sha256": hashlib.sha256(
                v5_code_raw
            ).hexdigest(),
            "v5_launch_intent_sha256": hashlib.sha256(
                v5_intent_raw
            ).hexdigest(),
            "v5_launch_receipt_sha256": hashlib.sha256(
                v5_launch_raw
            ).hexdigest(),
            "v5_launch_receipt": {
                "python_version": "3.12.13",
                "python_executable": "/python",
                "python_executable_sha256": _sha("python"),
                "python_environment_sha256": _sha("environment"),
                "python_distributions": {},
                "python_requirements_sha256": _sha("requirements"),
            },
        }
        diagnostic_raw = C._canonical_json_line(diagnostic)
        runtime_bytes = {
            C.Launch.DIAGNOSTIC_RELATIVE_PATH: diagnostic_raw,
            C.Launch.V5_CODE_MANIFEST.relative_to(C.REPO).as_posix(): (
                v5_code_raw
            ),
            C.Launch.V5_INTENT.relative_to(C.REPO).as_posix(): v5_intent_raw,
            C.Launch.V5_LAUNCH_RECEIPT.relative_to(C.REPO).as_posix(): (
                v5_launch_raw
            ),
        }
        producer_bytes = {**design_bytes, **runtime_bytes}
        records = {
            path: hashlib.sha256(raw).hexdigest()
            for path, raw in producer_bytes.items()
        }
        code_files = tuple(sorted(records))
        manifest_raw = b"".join(
            "{}  {}\n".format(records[path], path).encode("ascii")
            for path in code_files
        )
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        inventory_raw = b"{}\n"
        inventory_sha = hashlib.sha256(inventory_raw).hexdigest()
        attestation = {"source_inventory_sha256": inventory_sha}
        execution = {}
        launch = {
            "code_manifest_sha256": manifest_sha,
            "repository_commit_id": producer_revision,
            "source_inventory_sha256": inventory_sha,
        }
        intent = {}
        artifacts = {
            C.ATTESTATION: (C._canonical_json_line(attestation), attestation),
            C.EXECUTION_RECEIPT: (
                C._canonical_json_line(execution), execution,
            ),
            C.LAUNCH_RECEIPT: (C._canonical_json_line(launch), launch),
            C.INTENT: (C._canonical_json_line(intent), intent),
            C.SOURCE_INVENTORY: (inventory_raw, {}),
        }
        producer_snapshot = {
            **producer_bytes,
            C.MANIFEST_RELATIVE: manifest_raw,
        }
        prediagnosis_bytes = dict(design_bytes)
        manifest_state = {"raw": manifest_raw, "sha256": manifest_sha}
        snapshot_calls = []

        def snapshot_reader(actual_revision, paths):
            snapshot_calls.append((actual_revision, tuple(paths)))
            if actual_revision == prediagnosis_revision:
                source = prediagnosis_bytes
            elif actual_revision == producer_revision:
                source = producer_snapshot
            else:
                self.fail("unexpected snapshot revision")
            return {path: source[path] for path in paths}

        semantic_changed = {"value": False}

        def read_file(path, _expected, _label):
            if path == C.CODE_MANIFEST:
                return SimpleNamespace(
                    raw=manifest_state["raw"],
                    sha256=manifest_state["sha256"],
                )
            relative = path.relative_to(C.REPO).as_posix()
            if relative == "paper/paper.tex":
                raise AssertionError("descendant paper bytes were live-read")
            if semantic_changed["value"] and relative == semantic_files[0]:
                return SimpleNamespace(raw=b"changed\n", sha256=_sha("changed"))
            return SimpleNamespace(
                raw=design_bytes[relative], sha256=records[relative]
            )

        def validate_launch(_diagnostic_raw, actual_diagnostic, *_args):
            manifest, _environment = C._manifest(launch, actual_diagnostic)
            return manifest

        scoped_files = tuple(sorted((*code_files, C.MANIFEST_RELATIVE)))
        with (
            mock.patch.object(C, "CODE_MANIFEST_FILES", code_files),
            mock.patch.object(C, "SCOPED_FILES", scoped_files),
            mock.patch.object(
                C.Launch, "PRE_DIAGNOSIS_FILES", prediagnosis_files
            ),
            mock.patch.object(
                C, "_read_json", side_effect=lambda path, *_: artifacts[path]
            ),
            mock.patch.object(
                C, "_load_diagnostic", return_value=(diagnostic_raw, diagnostic)
            ) as diagnostic_loader,
            mock.patch.object(
                C.V6Utilities, "_validate_v5_producer", return_value={}
            ),
            mock.patch.object(C, "_validate_launch", side_effect=validate_launch),
            mock.patch.object(C, "_validate_inventory_manifest"),
            mock.patch.object(C, "_validate_execution"),
            mock.patch.object(C, "_read_file", side_effect=read_file),
        ):
            source = C.load_v8_source(
                C.ATTESTATION, C.EXECUTION_RECEIPT, C.LAUNCH_RECEIPT,
                snapshot_reader=snapshot_reader,
            )
            self.assertEqual(
                source.tracked_file_sha256,
                {**records, C.MANIFEST_RELATIVE: manifest_sha},
            )
            self.assertEqual(
                snapshot_calls,
                [
                    (prediagnosis_revision, prediagnosis_files),
                    (producer_revision, scoped_files),
                ],
            )

            older_paper = b"older prediagnosis paper\n"
            changed_freeze_files = [
                ({
                    **item,
                    "bytes": len(older_paper),
                    "sha256": hashlib.sha256(older_paper).hexdigest(),
                } if item["path"] == "paper/paper.tex" else dict(item))
                for item in freeze_files
            ]
            changed_diagnostic = {
                **diagnostic,
                "pre_diagnosis_freeze": {
                    **diagnostic["pre_diagnosis_freeze"],
                    "files": changed_freeze_files,
                },
            }
            changed_diagnostic_raw = C._canonical_json_line(changed_diagnostic)
            changed_records = {
                **records,
                C.Launch.DIAGNOSTIC_RELATIVE_PATH: hashlib.sha256(
                    changed_diagnostic_raw
                ).hexdigest(),
            }
            changed_manifest_raw = b"".join(
                "{}  {}\n".format(changed_records[path], path).encode("ascii")
                for path in code_files
            )
            changed_manifest_sha = hashlib.sha256(
                changed_manifest_raw
            ).hexdigest()
            diagnostic_loader.return_value = (
                changed_diagnostic_raw, changed_diagnostic
            )
            prediagnosis_bytes["paper/paper.tex"] = older_paper
            manifest_state.update({
                "raw": changed_manifest_raw,
                "sha256": changed_manifest_sha,
            })
            launch["code_manifest_sha256"] = changed_manifest_sha
            with self.assertRaisesRegex(
                C.SourceConsumerError,
                "prediagnosis freeze differs from launch manifest",
            ):
                C.load_v8_source(
                    C.ATTESTATION, C.EXECUTION_RECEIPT, C.LAUNCH_RECEIPT,
                    snapshot_reader=snapshot_reader,
                )

            diagnostic_loader.return_value = (diagnostic_raw, diagnostic)
            prediagnosis_bytes["paper/paper.tex"] = design_bytes[
                "paper/paper.tex"
            ]
            manifest_state.update({"raw": manifest_raw, "sha256": manifest_sha})
            launch["code_manifest_sha256"] = manifest_sha

            changed_diagnostic = {
                **diagnostic,
                "v5_launch_intent_sha256": "0" * 64,
            }
            changed_diagnostic_raw = C._canonical_json_line(changed_diagnostic)
            changed_records = {
                **records,
                C.Launch.DIAGNOSTIC_RELATIVE_PATH: hashlib.sha256(
                    changed_diagnostic_raw
                ).hexdigest(),
            }
            changed_manifest_raw = b"".join(
                "{}  {}\n".format(changed_records[path], path).encode("ascii")
                for path in code_files
            )
            changed_manifest_sha = hashlib.sha256(
                changed_manifest_raw
            ).hexdigest()
            diagnostic_loader.return_value = (
                changed_diagnostic_raw, changed_diagnostic
            )
            manifest_state.update({
                "raw": changed_manifest_raw,
                "sha256": changed_manifest_sha,
            })
            launch["code_manifest_sha256"] = changed_manifest_sha
            with self.assertRaisesRegex(
                C.SourceConsumerError, "launch-input manifest ancestry changed"
            ):
                C.load_v8_source(
                    C.ATTESTATION, C.EXECUTION_RECEIPT, C.LAUNCH_RECEIPT,
                    snapshot_reader=snapshot_reader,
                )

            diagnostic_loader.return_value = (diagnostic_raw, diagnostic)
            manifest_state.update({"raw": manifest_raw, "sha256": manifest_sha})
            launch["code_manifest_sha256"] = manifest_sha
            semantic_changed["value"] = True
            with self.assertRaisesRegex(
                C.SourceConsumerError, "live semantic replay code changed"
            ):
                C.load_v8_source(
                    C.ATTESTATION, C.EXECUTION_RECEIPT, C.LAUNCH_RECEIPT,
                    snapshot_reader=snapshot_reader,
                )

    def test_rebuilt_inventory_uses_the_full_frozen_schema_validator(self):
        inventory = {
            "schema": "full", "records": [{"candidate_index": 0}],
            "additional_frozen_provenance": {"bound": True},
        }
        with mock.patch.object(
            C.Source.Base, "validate_inventory_manifest",
            return_value=inventory["records"],
        ) as validate:
            C._validate_inventory_manifest(inventory)
        validate.assert_called_once_with(inventory)
        with (
            mock.patch.object(
                C.Source.Base, "validate_inventory_manifest", return_value=[]
            ),
            self.assertRaisesRegex(C.SourceConsumerError, "records changed"),
        ):
            C._validate_inventory_manifest(inventory)


if __name__ == "__main__":
    unittest.main()
