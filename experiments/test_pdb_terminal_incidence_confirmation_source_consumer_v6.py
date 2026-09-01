#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import unittest
from pathlib import Path
from unittest import mock

import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_source_consumer_v6 as C


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("ascii")).hexdigest()


def _root(path: Path, inode: int = 1) -> dict:
    return {
        "path": str(path), "canonical_path": str(path), "uid": 1,
        "mode": "0700", "device": 2, "inode": inode,
    }


def _diagnostic() -> dict:
    return {
        "reusable_v5_shard_indices": [0, 1],
        "repair_v5_shard_indices": [2],
        "v5_launch_receipt_sha256": _sha("v5-launch"),
        "v5_source_inventory_sha256": _sha("inventory"),
        "v5_code_manifest_sha256": _sha("v5-code"),
        "v5_launch_receipt": {
            "job_id": "111",
            "benchmark_revision": C.Source.Base.Inventory.BENCHMARK_REVISION,
        },
        "reuse_eligibility_rule": "scheduler state COMPLETED with exit 0:0 only",
        "resource_mapping": {
            "memory": {"option": "--mem=3000G", "requested": "3000G"},
            "time_limit": "3-00:00:00", "task_timeout_seconds": 115200,
        },
        "v5_output_manifest": {"files": []},
    }


def _launch_pair(diagnostic_raw: bytes, diagnostic: dict):
    token = "a" * 24
    code = {"code_manifest_sha256": _sha("v6-code")}
    materials = {key: None for key in C.MATERIAL_KEYS}
    materials.update({
        "campaign": C.CAMPAIGN,
        "benchmark_revision": C.Source.Base.Inventory.BENCHMARK_REVISION,
        "v5_terminal_diagnostic_sha256": hashlib.sha256(diagnostic_raw).hexdigest(),
        "v5_launch_receipt_sha256": diagnostic["v5_launch_receipt_sha256"],
        "logical_shards": 3, "candidates": C.CANDIDATES,
        "reusable_v5_shard_indices": [0, 1], "repair_v5_shard_indices": [2],
        "reused_v1_shards": 0, "reused_v2_shards": 0,
        "reused_v3_shards": 0, "reused_v4_shards": 0,
        "reused_v5_shards": 2, "repaired_v5_shards": 1,
        "reuse_eligibility_rule": diagnostic["reuse_eligibility_rule"],
        "repair_scope": "complete original two-candidate shards",
        "whole_campaign_rerun": False, "outcome_blind_selective_repair": True,
        "noncompleted_v5_shards_used": False, "array": "2",
        "array_throttle": 0, "partition": "fat", "qos": "normal",
        "account": C.Launch.ACCOUNT, "cpus_per_task": 1,
        "resource_mapping": diagnostic["resource_mapping"],
        "source_inventory_sha256": diagnostic["v5_source_inventory_sha256"],
        "code_manifest_sha256": _sha("v6-code"),
        "slurm_template_sha256": _sha("template"),
        "slurm_program_sha256": _sha("rendered"), "slurm_program_bytes": 8,
        "slurm_submission_mode": "stdin", "repository_commit_id": "b" * 40,
        "scoped_repository_files": list(C.SCOPED_FILES),
        "launch_root_identities": {
            "output_dir": _root(C.OUTPUT_DIR, 1),
            "tmpdir_root": _root(C.TMP_ROOT, 2),
        },
        "output_dir": str(C.OUTPUT_DIR), "tmpdir_root": str(C.TMP_ROOT),
        "source_inventory_path": str(C.SOURCE_INVENTORY),
        "candidate_attestation": str(C.CANDIDATE),
        "frozen_attestation": str(C.ATTESTATION),
        "execution_environment": C.Launch._execution_environment(code),
    })
    intent = {
        "schema": C.Launch.LAUNCH_SCHEMA + "/intent", **materials,
        "recorded_utc": "2026-09-02T00:00:00+00:00",
        "submission_token": token,
        "submit_command": C.Launch._submit_command(diagnostic, token),
    }
    raw = C._canonical_json_line(intent)
    launch = {
        "schema": C.Launch.LAUNCH_SCHEMA,
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(raw).hexdigest(),
        "job_id": "222",
    }
    return code, raw, intent, C._canonical_json_line(launch), launch


class V6ConsumerAdversarialTest(unittest.TestCase):
    def test_manifest_closure_contains_consumer_and_adversarial_test(self):
        self.assertEqual(tuple(sorted(C.CODE_MANIFEST_FILES)), C.CODE_MANIFEST_FILES)
        self.assertIn(
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v6.py",
            C.CODE_MANIFEST_FILES,
        )
        self.assertIn(
            "experiments/test_pdb_terminal_incidence_confirmation_source_consumer_v6.py",
            C.CODE_MANIFEST_FILES,
        )
        self.assertEqual(
            set(C.SCOPED_FILES), set(C.CODE_MANIFEST_FILES) | {C.MANIFEST_RELATIVE}
        )

    def test_manifest_requires_exact_file_set_and_live_bytes(self):
        payloads = {
            relative: ("fixture:" + relative + "\n").encode("ascii")
            for relative in C.CODE_MANIFEST_FILES
        }
        manifest_raw = b"".join(
            hashlib.sha256(payloads[path]).hexdigest().encode("ascii")
            + b"  " + path.encode("ascii") + b"\n"
            for path in C.CODE_MANIFEST_FILES
        )
        manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        diagnostic = {
            "v5_launch_receipt": {
                "python_version": "3.12.13", "python_executable": "/python",
                "python_executable_sha256": _sha("python"),
                "python_environment_sha256": _sha("env"),
                "python_distributions": {},
                "python_requirements_sha256": _sha("requirements"),
            }
        }

        def loaded(path, expected, label):
            del expected, label
            raw = manifest_raw if path == C.CODE_MANIFEST else payloads[
                path.relative_to(C.REPO).as_posix()
            ]
            return SafeIO.RegularFile(raw, hashlib.sha256(raw).hexdigest(), {})

        with mock.patch.object(C, "_read_file", side_effect=loaded):
            records, code = C._manifest({"code_manifest_sha256": manifest_sha}, diagnostic)
        self.assertEqual(set(records), set(C.CODE_MANIFEST_FILES))
        self.assertEqual(code["code_manifest_sha256"], manifest_sha)
        bad = manifest_raw.rsplit(b"\n", 2)[0] + b"\n"
        with mock.patch.object(
            C, "_read_file",
            return_value=SafeIO.RegularFile(bad, hashlib.sha256(bad).hexdigest(), {}),
        ), self.assertRaisesRegex(C.SourceConsumerError, "file set"):
            C._manifest({"code_manifest_sha256": hashlib.sha256(bad).hexdigest()}, diagnostic)

    def test_launch_is_strict_v6_and_rejects_prior_or_partial_reuse(self):
        diagnostic = _diagnostic()
        diagnostic_raw = C._canonical_json_line(diagnostic)
        code, intent_raw, intent, launch_raw, launch = _launch_pair(
            diagnostic_raw, diagnostic
        )
        rendered = b"rendered"
        with mock.patch.object(C, "ARRAY_TASKS", 3), mock.patch.object(
            C, "_manifest", return_value=({}, code)
        ), mock.patch.object(
            C.Launch, "_render_slurm", return_value=rendered
        ), mock.patch.object(
            C, "_read_file", return_value=SafeIO.RegularFile(
                b"template", _sha("template"), {}
            )
        ):
            C._validate_launch(
                diagnostic_raw, diagnostic, intent_raw, intent, launch_raw, launch
            )
            changed = dict(launch)
            changed["noncompleted_v5_shards_used"] = True
            with self.assertRaises(C.SourceConsumerError):
                C._validate_launch(
                    diagnostic_raw, diagnostic, intent_raw, intent, launch_raw, changed
                )
            changed = dict(launch)
            changed["reused_v3_shards"] = 1
            with self.assertRaises(C.SourceConsumerError):
                C._validate_launch(
                    diagnostic_raw, diagnostic, intent_raw, intent, launch_raw, changed
                )

    def test_exact_union_rejects_wrong_origin_and_hash(self):
        diagnostic = _diagnostic()
        root = _root(C.UNION_DIR, 9)
        v5_files = {}
        v6_files = {}
        union_files = {}
        sources = []
        for index in range(3):
            name = "shard-{:04d}-of-0820.json".format(index)
            record = {"path": name, "bytes": 1, "sha256": _sha(name)}
            (v5_files if index < 2 else v6_files)[name] = record
            union_files[name] = record
            sources.append({
                "shard_index": index,
                "origin": "v5-completed" if index < 2 else "v6-repair",
                "source": str((C.V5_OUTPUT_DIR if index < 2 else C.OUTPUT_DIR) / name),
                "source_sha256": record["sha256"],
                "union": name, "union_sha256": record["sha256"],
            })
        execution = {
            "union_sources": sources, "union_sources_sha256": C._digest(sources),
            "union_tree": {"root_identity": root},
        }
        with mock.patch.object(C, "ARRAY_TASKS", 3), mock.patch.object(
            C, "_validate_live_tree", return_value=union_files
        ):
            C._validate_union(execution, diagnostic, v5_files, v6_files)
            sources[1]["origin"] = "v6-repair"
            execution["union_sources_sha256"] = C._digest(sources)
            with self.assertRaisesRegex(C.SourceConsumerError, "origin/hash"):
                C._validate_union(execution, diagnostic, v5_files, v6_files)

    def test_snapshot_reader_must_return_exact_committed_closure(self):
        files = ("a", "b")
        payload = {"a": b"A", "b": b"B"}
        tracked = {key: hashlib.sha256(value).hexdigest() for key, value in payload.items()}
        C._validate_snapshot("a" * 40, files, tracked, lambda revision, paths: payload, "V6")
        with self.assertRaisesRegex(C.SourceConsumerError, "revision byte chain"):
            C._validate_snapshot(
                "a" * 40, files, tracked,
                lambda revision, paths: {**payload, "extra": b"x"}, "V6",
            )

    def test_recovery_stage_chain_is_exact_and_tamper_evident(self):
        records_sha = _sha("records")
        attestation = {"records_sha256": records_sha}
        attestation_raw = C._canonical_json_line(attestation)
        launch_raw = b"launch\n"
        diagnostic = {
            "pre_diagnosis_freeze": {"files_sha256": _sha("pre-files")},
            "v5_output_manifest": {"sha256": _sha("v5-tree")},
        }
        execution = {
            "v5_terminal_diagnostic_sha256": _sha("diagnostic"),
            "scheduler_rows": [], "scheduler_contract_rows": [],
            "v6_output_tree": {"tree": "repair"},
            "v5_reusable_environment_manifest": {"records": []},
            "v6_repair_environment_manifest": {"records": []},
            "union_sources": [], "union_sources_sha256": _sha("sources"),
            "union_tree": {"root_identity": _root(C.UNION_DIR, 17)},
        }
        plan = {
            "schema": C.Launch.SEAL_PLAN_SCHEMA,
            "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
            "v5_terminal_diagnostic_sha256": execution[
                "v5_terminal_diagnostic_sha256"
            ],
            "pre_diagnosis_files_sha256": diagnostic[
                "pre_diagnosis_freeze"
            ]["files_sha256"],
            "scheduler_rows": [], "scheduler_contract_rows": [],
            "v5_output_tree_sha256": diagnostic["v5_output_manifest"][
                "sha256"
            ],
            "v6_output_tree": execution["v6_output_tree"],
            "v5_reusable_environment_manifest": execution[
                "v5_reusable_environment_manifest"
            ],
            "v6_repair_environment_manifest": execution[
                "v6_repair_environment_manifest"
            ],
            "source_record_count": C.CANDIDATES,
            "source_record_sequence_sha256": records_sha,
        }
        values = {C.SEAL_PLAN: plan}
        execution["seal_plan_sha256"] = hashlib.sha256(
            C._canonical_json_line(plan)
        ).hexdigest()
        root_stage = {
            "schema": C.Launch.UNION_ROOT_STAGE_SCHEMA,
            "seal_plan_sha256": execution["seal_plan_sha256"],
            "root_identity": execution["union_tree"]["root_identity"],
        }
        values[C.UNION_ROOT_STAGE] = root_stage
        execution["union_root_stage_sha256"] = hashlib.sha256(
            C._canonical_json_line(root_stage)
        ).hexdigest()
        union_stage = {
            "schema": C.Launch.UNION_STAGE_SCHEMA,
            "seal_plan_sha256": execution["seal_plan_sha256"],
            "union_root_stage_sha256": execution[
                "union_root_stage_sha256"
            ],
            "sources": [], "sources_sha256": execution["union_sources_sha256"],
            "tree": execution["union_tree"],
        }
        values[C.UNION_STAGE] = union_stage
        execution["union_stage_sha256"] = hashlib.sha256(
            C._canonical_json_line(union_stage)
        ).hexdigest()
        candidate_stage = {
            "schema": C.Launch.CANDIDATE_STAGE_SCHEMA,
            "union_stage_sha256": execution["union_stage_sha256"],
            "candidate_path": str(C.CANDIDATE),
            "candidate_bytes": len(attestation_raw),
            "candidate_sha256": hashlib.sha256(attestation_raw).hexdigest(),
            "records_sha256": records_sha,
        }
        values[C.CANDIDATE_STAGE] = candidate_stage
        execution["candidate_stage_sha256"] = hashlib.sha256(
            C._canonical_json_line(candidate_stage)
        ).hexdigest()
        attestation_stage = {
            "schema": C.Launch.ATTESTATION_STAGE_SCHEMA,
            "candidate_stage_sha256": execution["candidate_stage_sha256"],
            "attestation_path": str(C.ATTESTATION),
            "attestation_bytes": len(attestation_raw),
            "attestation_sha256": hashlib.sha256(attestation_raw).hexdigest(),
        }
        values[C.ATTESTATION_STAGE] = attestation_stage
        execution["attestation_stage_sha256"] = hashlib.sha256(
            C._canonical_json_line(attestation_stage)
        ).hexdigest()

        def read_json(path, expected, label):
            del expected, label
            raw = C._canonical_json_line(values[path])
            return raw, values[path]

        candidate = SafeIO.RegularFile(
            attestation_raw, hashlib.sha256(attestation_raw).hexdigest(), {}
        )
        with mock.patch.object(C, "_read_json", side_effect=read_json), \
                mock.patch.object(C, "_read_file", return_value=candidate):
            C._validate_seal_stages(
                attestation_raw, attestation, diagnostic, launch_raw, execution
            )
            values[C.UNION_STAGE] = {**union_stage, "sources": [{}]}
            with self.assertRaisesRegex(C.SourceConsumerError, "hash chain"):
                C._validate_seal_stages(
                    attestation_raw, attestation, diagnostic,
                    launch_raw, execution,
                )

    def test_direct_contract_matches_v6_producer_closure(self):
        import pdb_terminal_metric_choice_protocol as Direct

        self.assertEqual(Direct.V6_CODE_MANIFEST_FILES, C.CODE_MANIFEST_FILES)
        self.assertEqual(Direct.V6_SCOPED_FILES, C.SCOPED_FILES)
        self.assertEqual(Direct.V6_ATTESTATION_PATH, C.ATTESTATION)
        self.assertEqual(Direct.V6_DIAGNOSTIC_PATH, C.DIAGNOSTIC)
        self.assertEqual(Direct.V6_INTENT_PATH, C.INTENT)
        self.assertEqual(Direct.V6_LAUNCH_RECEIPT_PATH, C.LAUNCH_RECEIPT)
        self.assertEqual(
            Direct.V6_EXECUTION_RECEIPT_PATH, C.EXECUTION_RECEIPT
        )
        self.assertEqual(Direct.V6_CODE_MANIFEST_PATH, C.CODE_MANIFEST)
        self.assertEqual(Direct.V6_SLURM_PATH, C.SLURM_TEMPLATE)
        self.assertEqual(Direct.V6_SEAL_PLAN_PATH, C.SEAL_PLAN)
        self.assertEqual(Direct.V6_UNION_ROOT_STAGE_PATH, C.UNION_ROOT_STAGE)
        self.assertEqual(Direct.V6_UNION_STAGE_PATH, C.UNION_STAGE)
        self.assertEqual(Direct.V6_CANDIDATE_STAGE_PATH, C.CANDIDATE_STAGE)
        self.assertEqual(
            Direct.V6_ATTESTATION_STAGE_PATH, C.ATTESTATION_STAGE
        )
        self.assertTrue({
            "pre_diagnosis_freeze", "seal_recovery_protocol",
            "seal_plan_sha256", "union_root_stage_sha256",
            "union_stage_sha256", "candidate_stage_sha256",
            "attestation_stage_sha256",
        } <= C.EXECUTION_KEYS)

    def test_scheduler_elapsed_and_state_are_raw_exact_slurm_values(self):
        token = "a" * 24
        launch = {
            "submission_token": token,
            "resource_mapping": {
                "memory": {"requested": "3000G"},
                "time_limit": "3-00:00:00",
            },
        }

        def execution(elapsed="00:01:00", *, contract_elapsed=None,
                      state="COMPLETED", contract_state="COMPLETED"):
            if contract_elapsed is None:
                contract_elapsed = elapsed
            return {
                "scheduler_state_counts": {"COMPLETED": 1},
                "scheduler_rows": [{
                    "array_task": 2, "state": state, "exit_code": "0:0",
                    "elapsed": elapsed, "partition": "fat",
                }],
                "scheduler_contract_rows": [{
                    "array_task": 2, "account": C.Launch.ACCOUNT,
                    "partition": "fat", "qos": "normal", "req_cpus": 1,
                    "req_mem": "3000G", "time_limit": "3-00:00:00",
                    "elapsed": contract_elapsed, "state": contract_state,
                    "exit_code": "0:0",
                    "job_name": C.Launch.JOB_NAME_PREFIX + "-" + token,
                }],
            }

        for elapsed in ("00:00:00", "23:59:59", "0-00:01:00",
                        "12-23:59:59"):
            self.assertTrue(C._valid_elapsed(elapsed))
            C._validate_scheduler(execution(elapsed), launch, [2])
        for elapsed in (
            "", "0:01:00", "24:00:00", "00:60:00", "00:00:60",
            "01-00:00:00", "1-24:00:00", "00:01:00+", 60,
        ):
            self.assertFalse(C._valid_elapsed(elapsed))
            with self.assertRaisesRegex(
                C.SourceConsumerError, "scheduler/resource row"
            ):
                C._validate_scheduler(execution(elapsed), launch, [2])
            with self.assertRaisesRegex(
                C.SourceConsumerError, "scheduler/resource row"
            ):
                C._validate_scheduler(
                    execution(contract_elapsed=elapsed), launch, [2]
                )
        with self.assertRaisesRegex(
            C.SourceConsumerError, "scheduler/resource row"
        ):
            C._validate_scheduler(
                execution(state="COMPLETED+"), launch, [2]
            )
        with self.assertRaisesRegex(
            C.SourceConsumerError, "scheduler/resource row"
        ):
            C._validate_scheduler(
                execution(contract_state="COMPLETED+"), launch, [2]
            )

    def test_native_v6_envelope_is_consumable_by_confirmation_a(self):
        import pdb_terminal_incidence_confirmation_a_protocol as A

        diagnostic = _diagnostic()
        diagnostic_raw = C._canonical_json_line(diagnostic)
        _code, _intent_raw, _intent, _launch_raw, launch = _launch_pair(
            diagnostic_raw, diagnostic
        )
        revision = C.Source.Base.Inventory.BENCHMARK_REVISION
        attestation = {
            "schema": C.ATTESTATION_SCHEMA,
            "benchmark_revision": revision,
        }
        inventory = {
            "schema": C.ATTESTATION_SCHEMA + "/inventory",
            "benchmark_revision": revision,
            "records": [],
        }
        execution = {
            "schema": C.Launch.EXECUTION_SCHEMA,
            "campaign": C.CAMPAIGN,
            "benchmark_revision": revision,
        }
        A._validate_v6_source_envelope(
            attestation, inventory, execution, launch
        )
        for target in (launch, execution):
            changed = dict(target)
            changed.pop("benchmark_revision")
            args = (attestation, inventory, execution, changed)
            if target is execution:
                args = (attestation, inventory, changed, launch)
            with self.assertRaisesRegex(A.ProtocolError, "schema/benchmark"):
                A._validate_v6_source_envelope(*args)

    def test_downstream_contracts_are_v6_only(self):
        paths = (
            C.SCRIPT_DIR / "pdb_terminal_incidence_confirmation_a_protocol.py",
            C.SCRIPT_DIR / "freeze_pdb_terminal_incidence_confirmation_a.py",
            C.SCRIPT_DIR / "pdb_terminal_incidence_confirmation_b_protocol.py",
            C.SCRIPT_DIR / "freeze_pdb_terminal_incidence_confirmation_b.py",
            C.SCRIPT_DIR / "pdb_terminal_metric_choice_protocol.py",
            C.SCRIPT_DIR / "pdb_terminal_metric_choice_runner.py",
            C.SCRIPT_DIR / "pdb_terminal_metric_choice_execution.py",
        )
        joined = "\n".join(path.read_text() for path in paths)
        self.assertIn("source_audit_v6", joined)
        self.assertIn("v6_code_manifest_sha256", joined)
        self.assertNotIn("load_v5_source(", joined)
        self.assertNotIn('source_audit_v5"]', joined)


if __name__ == "__main__":
    unittest.main()
