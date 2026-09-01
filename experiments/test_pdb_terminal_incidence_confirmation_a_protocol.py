#!/usr/bin/env python3

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import audit_pdb_terminal_incidence_confirmation_sources as SourceAudit
import pdb_terminal_incidence_confirmation_a_protocol as P
import freeze_pdb_terminal_incidence_confirmation_a as Freeze


def _write(path: Path, value: dict) -> bytes:
    raw = P.canonical_json_line(value)
    path.write_bytes(raw)
    return raw


def _root_identity(path: Path, inode: int = 1) -> dict:
    value = str(path)
    return {
        "path": value,
        "canonical_path": value,
        "uid": 1,
        "mode": "0700",
        "device": 1,
        "inode": inode,
    }


def _tree(records: list[dict], root_identity: dict) -> dict:
    records = sorted(records, key=lambda record: record["path"])
    digest = hashlib.sha256()
    digest.update(b"root-identity\0" + P.canonical_json(root_identity))
    for record in records:
        digest.update(
            record["path"].encode("ascii") + b"\0"
            + bytes.fromhex(record["sha256"])
        )
    return {
        "sha256": digest.hexdigest(),
        "root_identity": root_identity,
        "files_count": len(records),
        "files": records,
    }


def _source_execution_environment(repo: Path):
    tmp_root = (
        repo / "experiments" / "data" /
        "pdb_terminal_incidence_confirmation_source_audit_v4_tmp"
    )
    tmpdir = str(tmp_root / "task-{array_job_id}-{array_task_id}")
    cache = tmpdir + "/pycache"
    controlled_path = "/usr/bin:/bin"
    return {
        "submission_export": "NONE",
        "slurm_export": "NONE",
        "unset_variables": ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"],
        "python_no_user_site": "1",
        "python_no_user_site_flag": 1,
        "python_dont_write_bytecode": "1",
        "python_dont_write_bytecode_flag": True,
        "tmpdir_root": str(tmp_root),
        "tmpdir_template": tmpdir,
        "python_tempfile_directory_template": tmpdir,
        "python_pycache_prefix_template": cache,
        "tmpdir_mode": "0700",
        "tmpdir_cleanup": "EXIT trap with pinned /usr/bin/rmdir; no recursion",
        "root_identity_policy": (
            "canonical absolute path; no direct/ancestor symlinks; mode 0700; "
            "launch uid/device/inode retained"
        ),
        "source_snapshot_policy": {
            "scope": "one domain/problem snapshot tree per candidate",
            "location": "inside the exact per-array-task TMPDIR",
            "directory_mode": "0700",
            "file_mode": "0400",
            "consumers": ["translator", "axiom_based normalization"],
            "verify_before_each_consumer": True,
            "verify_identity_and_sha256_after_use": True,
            "cleanup": (
                "unlink exact files, then rmdir exact directories; no recursion"
            ),
        },
        "outer_python_flag": "-B",
        "path": controlled_path,
        "translator_child_environment": {
            "PATH": controlled_path,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": tmpdir,
            "PYTHONPYCACHEPREFIX": cache,
            "PYTHONPATH": str(repo / "src"),
        },
        "python_command": str(
            repo / "experiments" / "data" /
            "pdb-terminal-incidence-shadow-venv" /
            "bin" / "python"
        ),
        "python_executable": "/pinned/python3.12",
        "python_executable_sha256": "a" * 64,
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


def _task(index: int) -> dict:
    family = "family-{:02d}".format(index % 30)
    directory = "directory-{:02d}".format(index % 60)
    digest = hashlib.sha256("problem-{}".format(index).encode()).hexdigest()
    domain_digest = hashlib.sha256(directory.encode()).hexdigest()
    value = {
        "candidate_index": index,
        "directory": directory,
        "family": family,
        "problem": "p{:04d}.pddl".format(index),
        "domain_file": "{}/domain.pddl".format(directory),
        "problem_file": "{}/p{:04d}.pddl".format(directory, index),
        "domain_sha256": domain_digest,
        "problem_sha256": digest,
        "canonical_path": "{}/p{:04d}.pddl".format(directory, index),
        "is_shadow_family": index % 2 == 0,
        "is_shadow_unrepresented": index % 2 == 1,
        "is_all_prior_represented": index % 3 != 0,
        "is_all_prior_unrepresented": index % 3 == 0,
        "aliases": [],
        "selection_role": "confirmation-a",
        "selection_rank_sha256": "",
        "source_audit_evidence_sha256": hashlib.sha256(
            "evidence-{}".format(index).encode()
        ).hexdigest(),
    }
    alias_keys = (
        "directory", "family", "problem", "domain_file", "problem_file",
        "domain_sha256", "problem_sha256",
    )
    value["aliases"] = [{key: value[key] for key in alias_keys}]
    value["selection_rank_sha256"] = hashlib.sha256(b"\0".join(
        item.encode("utf-8") for item in (
            P.COHORT_SEED, value["selection_role"], family, digest,
            value["canonical_path"],
        )
    )).hexdigest()
    return value


def _guided_task(index: int) -> dict:
    value = _task(650 + index)
    value["selection_role"] = "guided-b"
    value["selection_stage"] = "base"
    value["selection_rank_sha256"] = hashlib.sha256(b"\0".join(
        item.encode("utf-8") for item in (
            P.COHORT_SEED, value["selection_role"], value["family"],
            value["problem_sha256"], value["canonical_path"],
        )
    )).hexdigest()
    return value


def _inventory_record(task: dict) -> dict:
    return {key: task[key] for key in P._INVENTORY_TASK_KEYS}


def _prelaunch_gate(a_tasks, b_tasks, shadow, all_prior):
    def support(tasks):
        families = {task["family"] for task in tasks}
        shadow_families = families & set(shadow)
        prior_tasks = [
            task for task in tasks if task["family"] in set(all_prior)
        ]
        return families, shadow_families, prior_tasks, {
            task["family"] for task in prior_tasks
        }

    af, ashadow, aprior, apriorf = support(a_tasks)
    bf, bshadow, bprior, bpriorf = support(b_tasks)
    clauses = {
        "confirmation_tasks": {
            "actual": len(a_tasks), "required": 650,
            "passed": len(a_tasks) == 650,
        },
        "confirmation_families": {
            "actual": len(af), "required_minimum": 28,
            "passed": len(af) >= 28,
        },
        "confirmation_shadow_unrepresented_families": {
            "actual": len(ashadow), "required_minimum": 12,
            "passed": len(ashadow) >= 12,
        },
        "confirmation_all_prior_unrepresented_tasks": {
            "actual": len(aprior), "required_minimum": 100,
            "passed": len(aprior) >= 100,
        },
        "confirmation_all_prior_unrepresented_families": {
            "actual": len(apriorf), "required_minimum": 10,
            "passed": len(apriorf) >= 10,
        },
        "guided_tasks": {
            "actual": len(b_tasks), "required_minimum": 200,
            "passed": len(b_tasks) >= 200,
        },
        "guided_families": {
            "actual": len(bf), "required_minimum": 30,
            "passed": len(bf) >= 30,
        },
        "guided_shadow_unrepresented_families": {
            "actual": len(bshadow), "required_minimum": 12,
            "passed": len(bshadow) >= 12,
        },
        "guided_all_prior_unrepresented_tasks": {
            "actual": len(bprior), "required_minimum": 50,
            "passed": len(bprior) >= 50,
        },
        "guided_all_prior_unrepresented_families": {
            "actual": len(bpriorf), "required_minimum": 10,
            "passed": len(bpriorf) >= 10,
        },
    }
    a_ids = {(task["directory"], task["problem"]) for task in a_tasks}
    b_ids = {(task["directory"], task["problem"]) for task in b_tasks}
    a_hashes = {task["problem_sha256"] for task in a_tasks}
    b_hashes = {task["problem_sha256"] for task in b_tasks}
    return {
        "outcome_blind": True,
        "availability": {
            "supported_tasks": len(a_tasks) + len(b_tasks),
            "supported_families": len(af | bf),
            "supported_tasks_sha256": "1" * 64,
            "shadow_unrepresented": {
                "tasks": 1, "families": 1,
                "tasks_sha256": "2" * 64, "families_sha256": "3" * 64,
            },
            "all_prior_unrepresented": {
                "tasks": 1, "families": 1,
                "tasks_sha256": "4" * 64, "families_sha256": "5" * 64,
            },
            "post_confirmation_remaining_tasks": len(b_tasks),
            "guided_b_maximum_under_family_cap": len(b_tasks),
            "guided_b_target_tasks": 300,
            "guided_b_max_tasks_per_family": 12,
        },
        "passed": all(clause["passed"] for clause in clauses.values()),
        "clauses": clauses,
        "cohort_disjointness": {
            "source_identity_overlap": len(a_ids & b_ids),
            "problem_sha256_overlap": len(a_hashes & b_hashes),
            "passed": not (a_ids & b_ids or a_hashes & b_hashes),
        },
    }


class SourceFixture:
    def __init__(self, root: Path, **overrides):
        self.repo = root.resolve()
        script_dir = self.repo / "experiments"
        self.artifact_dir = (
            script_dir / "artifacts" /
            "pdb-terminal-incidence-confirmation-v4"
        )
        self.intent = self.artifact_dir / "source-audit-launch-intent-v4.json"
        self.launch = self.artifact_dir / "source-audit-launch-receipt-v4.json"
        self.execution = (
            self.artifact_dir / "source-audit-execution-receipt-v4.json"
        )
        self.attestation = (
            script_dir / "pdb_terminal_incidence_confirmation_source_audit_v4.json"
        )
        self.slurm = (
            script_dir / "pdb_terminal_incidence_confirmation_source_scan_v4.slurm"
        )
        self.manifest = (
            script_dir /
            "pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256"
        )
        self.amendment = (
            script_dir /
            "pdb_terminal_incidence_confirmation_source_audit_v4_protocol.md"
        )
        self.output_dir = (
            script_dir / "data" /
            "pdb_terminal_incidence_confirmation_source_audit_v4"
        )
        self.inventory = self.output_dir / "source-inventory-v4.json"
        self.tmpdir_root = (
            script_dir / "data" /
            "pdb_terminal_incidence_confirmation_source_audit_v4_tmp"
        )
        self.candidate = (
            script_dir / "data" /
            "pdb_terminal_incidence_confirmation_source_audit_v4_candidate.json"
        )
        for path in (
            self.intent, self.launch, self.execution, self.attestation,
            self.slurm, self.manifest, self.amendment, self.inventory,
        ):
            path.parent.mkdir(parents=True, exist_ok=True)

        schema = P.SOURCE_AUDIT_SCHEMA
        diagnostic_relative = P.SOURCE_V4_V3_DIAGNOSTIC_RELATIVE
        diagnostic = {
            "schema": schema + "/campaign-v4/v3-infrastructure-diagnostic",
            "successful_v3_shard_contents_inspected": False,
            "successful_v3_log_contents_inspected": False,
            "source_support_outcomes_used_for_v4_design": False,
            "full_rerun_decision": {
                "reused_v1_shards": 0,
                "reused_v2_shards": 0,
                "reused_v3_shards": 0,
                "scope": "all-820-original-shards-and-1640-candidates",
                "whole_campaign_rerun": True,
            },
        }
        manifest_hashes = {}
        producer_relative = (
            "experiments/audit_pdb_terminal_incidence_confirmation_sources.py"
        )
        inventory_producer_relative = (
            "experiments/pdb_terminal_incidence_confirmation_inventory.py"
        )
        for relative in P.SOURCE_V4_MANIFEST_FILES:
            path = self.repo / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative in P.SOURCE_V4_MANIFEST_FILES[:2]:
                raw = P.canonical_json_line({})
            elif relative == diagnostic_relative:
                raw = P.canonical_json_line(diagnostic)
            elif relative == producer_relative:
                raw = Path(SourceAudit.__file__).read_bytes()
            elif relative == inventory_producer_relative:
                raw = Path(SourceAudit.Inventory.__file__).read_bytes()
            else:
                raw = ("fixture:{}\n".format(relative)).encode("ascii")
            path.write_bytes(raw)
            manifest_hashes[relative] = hashlib.sha256(raw).hexdigest()
        self.amendment_sha = manifest_hashes[
            "experiments/"
            "pdb_terminal_incidence_confirmation_source_audit_v4_protocol.md"
        ]
        self.diagnostic_sha = manifest_hashes[diagnostic_relative]
        manifest_raw = "".join(
            "{}  {}\n".format(manifest_hashes[relative], relative)
            for relative in P.SOURCE_V4_MANIFEST_FILES
        ).encode("ascii")
        self.manifest.write_bytes(manifest_raw)
        self.manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
        slurm_raw = b"#!/bin/bash\n# synthetic source-audit v4 producer\n"
        self.slurm.write_bytes(slurm_raw)
        self.slurm_sha = hashlib.sha256(slurm_raw).hexdigest()
        inventory_tasks = [_task(index) for index in range(1640)]
        inventory_value = {
            "schema": P.SOURCE_AUDIT_SCHEMA + "/inventory",
            "benchmark_revision": P.BENCHMARK_REVISION,
            "records": [_inventory_record(task) for task in inventory_tasks],
        }
        inventory_raw = _write(self.inventory, inventory_value)
        self.inventory_sha = hashlib.sha256(inventory_raw).hexdigest()
        empty_stream = {
            "bytes": 0,
            "sha256": hashlib.sha256(b"").hexdigest(),
            "tail": "",
            "tail_bytes": 0,
        }
        sas = {
            "sas_version": 3,
            "metric": 1,
            "num_variables": 1,
            "num_mutex_groups": 0,
            "num_operators": 1,
            "num_effects": 1,
            "num_conditional_effects": 0,
            "num_zero_cost_operators": 0,
            "num_serialized_axioms": 0,
            "min_operator_cost": 1,
            "max_operator_cost": 1,
        }
        source_records = [{
            **_inventory_record(task),
            "translation_attempted": True,
            "translator_command": [
                "PINNED_PYTHON", "-B", "-m", "translate",
                task["domain_file"], task["problem_file"],
            ],
            "translation": {
                "status": "success",
                "timeout_seconds": 14400,
                "returncode": 0,
                "stdout": empty_stream,
                "stderr": empty_stream,
                "sas": sas,
                "sas_sha256": "6" * 64,
                "error": None,
            },
            "normalization": {
                "status": "success",
                "strategy": "axiom_based",
                "num_normalized_axioms": 0,
                "error": None,
            },
            "supported": True,
            "support_exclusion_reasons": [],
        } for task in inventory_tasks]
        inventory_records_sha = hashlib.sha256(
            P.canonical_json_line(inventory_value["records"])
        ).hexdigest()
        records_sha = hashlib.sha256(
            P.canonical_json_line(source_records)
        ).hexdigest()

        shadow = sorted({
            task["family"] for task in inventory_tasks
            if task["is_shadow_unrepresented"]
        })
        all_prior = sorted({
            task["family"] for task in inventory_tasks
            if task["is_all_prior_unrepresented"]
        })
        self.shadow_represented = {
            task["family"] for task in inventory_tasks
            if task["is_shadow_family"]
        }
        self.all_prior_unrepresented = set(all_prior)
        with mock.patch.object(
            SourceAudit.Inventory, "SHADOW_FAMILIES",
            self.shadow_represented,
        ), mock.patch.object(
            SourceAudit, "ALL_PRIOR_UNREPRESENTED_FAMILIES",
            self.all_prior_unrepresented,
        ), mock.patch.object(
            SourceAudit, "__file__",
            str(
                self.repo /
                "experiments/"
                "audit_pdb_terminal_incidence_confirmation_sources.py"
            ),
        ), mock.patch.object(
            SourceAudit.Inventory, "__file__",
            str(
                self.repo / "experiments" /
                "pdb_terminal_incidence_confirmation_inventory.py"
            ),
        ):
            gate, cohorts = SourceAudit.split_supported(source_records)
        tasks = cohorts["confirmation_a"]["tasks"]
        guided_tasks = cohorts["guided_b"]["tasks"]
        cohort_sha = hashlib.sha256(P.canonical_json_line(tasks)).hexdigest()
        guided_sha = hashlib.sha256(
            P.canonical_json_line(guided_tasks)
        ).hexdigest()
        self.fixed_hashes = {
            **P.SOURCE_V4_FIXED_HASHES,
            "shadow_unrepresented_family_sequence_sha256": hashlib.sha256(
                P.canonical_json(shadow)
            ).hexdigest(),
            "all_prior_unrepresented_family_sequence_sha256": hashlib.sha256(
                P.canonical_json(all_prior)
            ).hexdigest(),
        }
        attestation = {
            "schema": schema,
            "benchmark_revision": P.BENCHMARK_REVISION,
            "translator_source_sha256": P.SOURCE_V4_FIXED_HASHES[
                "translator_source_sha256"
            ],
            "source_inventory_sha256": self.inventory_sha,
            "source_inventory_records_sha256": inventory_records_sha,
            "code_manifest_sha256": self.manifest_sha,
            "split_seed": P.COHORT_SEED,
            "split_rank_encoding": P._SPLIT_RANK_ENCODING,
            "split_role_labels": P._SPLIT_ROLE_LABELS,
            "records_sha256": records_sha,
            "confirmation_prelaunch_authorized": True,
            "prelaunch_gate": gate,
            "counts": {
                "candidates": 1640,
                "translation_attempts": 1640,
                "translated_successfully": 1640,
                "supported": 1640,
                "unsupported": 0,
                "families": 30,
            },
            "translation_status_counts": {"success": 1640},
            "support_exclusion_counts": {},
            "split_strata": {
                "shadow_unrepresented": {
                    "definition": (
                        "families absent from the frozen shadow suites"
                    ),
                    "families": shadow,
                    "families_sha256": hashlib.sha256(
                        P.canonical_json_line(shadow)
                    ).hexdigest(),
                    "inventory_family_sequence_sha256": self.fixed_hashes[
                        "shadow_unrepresented_family_sequence_sha256"
                    ],
                },
                "all_prior_unrepresented": {
                    "definition": (
                        "families absent from both frozen prior experiment "
                        "artifacts"
                    ),
                    "families": all_prior,
                    "families_sha256": hashlib.sha256(
                        P.canonical_json_line(all_prior)
                    ).hexdigest(),
                    "inventory_family_sequence_sha256": self.fixed_hashes[
                        "all_prior_unrepresented_family_sequence_sha256"
                    ],
                    "prior_directory_family_map_sha256": self.fixed_hashes[
                        "prior_directory_family_map_sha256"
                    ],
                    "prior_family_ledger_sha256": self.fixed_hashes[
                        "prior_family_ledger_sha256"
                    ],
                },
            },
            "cohorts": cohorts,
            "records": source_records,
        }
        attestation_raw = _write(self.attestation, attestation)
        output_root_identity = _root_identity(self.output_dir, 1)
        tmp_root_identity = _root_identity(self.tmpdir_root, 2)
        launch_roots = {
            "output_dir": output_root_identity,
            "tmpdir_root": tmp_root_identity,
        }
        fixed = {
            "campaign": "v4",
            "whole_campaign_rerun": True,
            "reused_v1_shards": 0,
            "reused_v2_shards": 0,
            "reused_v3_shards": 0,
            "partition": "fat",
            "qos": "normal",
            "account": P.ACCOUNT,
            "array": "0-819",
            "array_throttle": 0,
            "array_tasks": 820,
            "tasks_per_array_task": 2,
            "candidates": 1640,
            "cpus_per_task": 1,
            "time_limit": "08:20:00",
            "memory_per_cpu": "1024G",
            "task_timeout_seconds": 14400,
            "benchmark_revision": P.BENCHMARK_REVISION,
            **self.fixed_hashes,
            "source_inventory_sha256": self.inventory_sha,
            "source_inventory_path": str(self.inventory),
            "slurm_script_sha256": self.slurm_sha,
            "slurm_submission_mode": "stdin",
            "slurm_stdin_sha256": self.slurm_sha,
            "slurm_stdin_bytes": len(slurm_raw),
            "slurm_path_argument": False,
            "submission_journal_contract": (
                "exact sbatch options-only SubmitLine"
            ),
            "code_manifest_sha256": self.manifest_sha,
            "launcher_sha256": manifest_hashes[
                "experiments/"
                "launch_pdb_terminal_incidence_confirmation_source_audit_v4.py"
            ],
            "repository_commit_id": "4" * 40,
            "scoped_repository_files": sorted({
                *P.SOURCE_V4_MANIFEST_FILES,
                P.SOURCE_V4_SLURM_RELATIVE,
                P.SOURCE_V4_MANIFEST_RELATIVE,
            }),
            "jj_executable": "/home/jendrik/bin/jj",
            "jj_executable_sha256": (
                "d1d69a0f87df266eebf0d2592dd019eb288c300b15fd019afe26cb1ed11ba152"
            ),
            "sbatch_executable": "/usr/bin/sbatch",
            "sbatch_executable_sha256": (
                "efbb8e172acc7ed768430740d04e19cc07a3ac4701b005d1a997c08424bde741"
            ),
            "sacct_executable": "/usr/bin/sacct",
            "sacct_executable_sha256": (
                "58f3976b19baa2bc26772a92ab224dd0c1bf0ab3d9b675d85aa3e4636c836315"
            ),
            "submission_environment": {
                "LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin",
            },
            "output_dir": str(self.output_dir),
            "tmpdir_root": str(self.tmpdir_root),
            "launch_root_identities": launch_roots,
            "candidate_attestation": str(self.candidate),
            "frozen_attestation": str(self.attestation),
            "execution_environment": _source_execution_environment(self.repo),
            "v3_infrastructure_diagnostic_path": str(
                self.repo / diagnostic_relative
            ),
            "v3_infrastructure_diagnostic_sha256": self.diagnostic_sha,
            "v3_infrastructure_diagnostic": diagnostic,
            "python_version": P.REQUIRED_PYTHON_VERSION,
            "python_executable": "/pinned/python3.12",
            "python_executable_sha256": "a" * 64,
            "python_environment_sha256": "c" * 64,
            "python_distributions": {},
            "python_requirements_sha256": "d" * 64,
        }
        launch_overrides = dict(overrides.get("launch", {}))
        launch_special = {
            key: launch_overrides.pop(key)
            for key in tuple(launch_overrides)
            if key in {"schema", "launch_intent_sha256", "job_id"}
        }
        fixed.update(launch_overrides)
        token = "a" * 24
        submit_command = [
            "/usr/bin/sbatch", "--parsable", "--export=NONE",
            "--job-name=confirmation-source-audit-v4-{}".format(token),
            "--comment=confirmation-source-audit-v4/{}".format(token),
            "--account={}".format(P.ACCOUNT), "--partition=fat",
            "--qos=normal", "--array=0-819", "--nodes=1", "--ntasks=1",
            "--cpus-per-task=1", "--mem-per-cpu=1024G", "--time=08:20:00",
            "--nice=0", "--no-requeue", "--chdir={}".format(self.repo),
            "--output={}".format(
                (self.output_dir / "slurm-%A_%a.out").resolve()
            ),
        ]
        intent_value = {
            "schema": schema + "/campaign-v4/launch/intent",
            **fixed,
            "recorded_utc": "2026-09-01T12:00:00+00:00",
            "submission_token": token,
            "submit_command": submit_command,
        }
        intent_raw = _write(self.intent, intent_value)
        self.intent_sha = hashlib.sha256(intent_raw).hexdigest()
        launch = {
            "schema": schema + "/campaign-v4/launch",
            **{key: value for key, value in intent_value.items() if key != "schema"},
            "launch_intent_sha256": self.intent_sha,
            "job_id": "123456",
        }
        launch.update(launch_special)
        launch_raw = _write(self.launch, launch)
        self.launch_sha = hashlib.sha256(launch_raw).hexdigest()
        shard_names = [
            "shard-{:04d}-of-0820.json".format(index)
            for index in range(820)
        ]
        shard_hashes = {
            name: hashlib.sha256(name.encode("ascii")).hexdigest()
            for name in shard_names
        }
        environment_names = [
            "environment-{:04d}-of-0820.json".format(index)
            for index in range(820)
        ]
        environment_hashes = {
            name: hashlib.sha256(name.encode("ascii")).hexdigest()
            for name in environment_names
        }
        original_records = [{
            "path": "source-inventory-v4.json", "bytes": 1,
            "sha256": self.inventory_sha,
        }]
        original_records.extend({
            "path": name, "bytes": 1, "sha256": shard_hashes[name],
        } for name in shard_names)
        original_records.extend({
            "path": name, "bytes": 1, "sha256": environment_hashes[name],
        } for name in environment_names)
        original_records.extend({
            "path": "slurm-123456_{}.out".format(index),
            "bytes": 1,
            "sha256": hashlib.sha256(
                "log-{}".format(index).encode("ascii")
            ).hexdigest(),
        } for index in range(820))
        environment_records = [{
            "array_task": index,
            "path": environment_names[index],
            "sha256": environment_hashes[environment_names[index]],
            "tmpdir": str(self.tmpdir_root / "task-123456-{}".format(index)),
            "tmpdir_identity": _root_identity(
                self.tmpdir_root / "task-123456-{}".format(index),
                10 + index,
            ),
            "output_dir_identity": output_root_identity,
            "shard_sha256": shard_hashes[shard_names[index]],
        } for index in range(820)]
        environment_manifest = {
            "schema": (
                schema + "/campaign-v4/task-environment/v1/manifest/v1"
            ),
            "records": environment_records,
            "records_sha256": hashlib.sha256(
                P.canonical_json(environment_records)
            ).hexdigest(),
            "tmpdir_root_identity": tmp_root_identity,
            "output_dir_identity": output_root_identity,
            "all_task_tmpdirs_removed_by_rmdir": True,
        }
        scheduler_rows = [{
            "array_task": index,
            "state": "COMPLETED",
            "exit_code": "0:0",
            "elapsed": "00:01:00",
            "partition": "fat",
        } for index in range(820)]
        scheduler_contract_rows = [{
            "array_task": index,
            "account": P.ACCOUNT,
            "partition": "fat",
            "qos": "normal",
            "req_cpus": 1,
            "req_mem": "1024G",
            "time_limit": "08:20:00",
            "state": "COMPLETED",
            "exit_code": "0:0",
            "job_name": "confirmation-source-audit-v4-{}".format(token),
        } for index in range(820)]
        execution = {
            "schema": schema + "/campaign-v4/execution",
            "campaign": "v4",
            "whole_campaign_rerun": True,
            "original_only": True,
            "recovery": None,
            "reused_v1_shards": 0,
            "reused_v2_shards": 0,
            "reused_v3_shards": 0,
            "launch_receipt_sha256": hashlib.sha256(launch_raw).hexdigest(),
            "job_id": "123456",
            "partition": "fat",
            "qos": "normal",
            "account": P.ACCOUNT,
            "array": "0-819",
            "array_tasks": 820,
            "tasks_per_array_task": 2,
            "cpus_per_task": 1,
            "memory_per_cpu": "1024G",
            "time_limit": "08:20:00",
            "task_timeout_seconds": 14400,
            "array_throttle": 0,
            "shards": 820,
            "candidates": 1640,
            "scheduler_rows": scheduler_rows,
            "scheduler_state_counts": {"COMPLETED": 820},
            "scheduler_contract_rows": scheduler_contract_rows,
            "launch_root_identities": launch_roots,
            "sealing_root_identities_before": launch_roots,
            "sealing_root_identities_after": launch_roots,
            "original_output_tree": _tree(
                original_records, output_root_identity
            ),
            "task_environment_manifest": environment_manifest,
            "code_manifest_sha256": self.manifest_sha,
            "source_inventory_sha256": self.inventory_sha,
            "v3_infrastructure_diagnostic_sha256": self.diagnostic_sha,
            "v3_infrastructure_diagnostic": diagnostic,
            "execution_environment": launch["execution_environment"],
            "source_audit_complete": True,
            "confirmation_prelaunch_authorized": True,
            "prelaunch_gate": gate,
            "attestation_sha256": hashlib.sha256(attestation_raw).hexdigest(),
            "attestation_records_sha256": records_sha,
            "cohort_manifest_sha256": {
                "confirmation_a": cohort_sha,
                "guided_b": guided_sha,
            },
            "counts": attestation["counts"],
            "translation_status_counts": attestation[
                "translation_status_counts"
            ],
            "support_exclusion_counts": {},
        }
        execution.update(overrides.get("execution", {}))
        _write(self.execution, execution)

    def load(self):
        with self.patch():
            return P.load_source_materials(
                self.attestation, self.execution, self.launch
            )

    def v6_chain(self):
        # Retain the legacy fixture's exhaustive synthetic mutations while the
        # dedicated V6-consumer tests cover the new sealed provenance layer.
        P._load_source_materials_v4_obsolete(
            self.attestation, self.execution, self.launch
        )
        tracked = {}
        for relative in P.SourceV6.SCOPED_FILES:
            path = self.repo / relative
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(("v6-fixture:{}\n".format(relative)).encode())
            tracked[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        execution = json.loads(self.execution.read_text())
        execution.update({
            "schema": P.SourceV6.Launch.EXECUTION_SCHEMA,
            "campaign": "v6-selective-repair",
            "benchmark_revision": P.BENCHMARK_REVISION,
            "v6_code_manifest_sha256": execution["code_manifest_sha256"],
            "union_tree": execution["original_output_tree"],
            "union_sources_sha256": "a" * 64,
            "v6_output_tree": execution["original_output_tree"],
            "v5_launch_receipt_sha256": "b" * 64,
            "v5_code_manifest_sha256": "c" * 64,
            "pre_diagnosis_freeze": {
                "repository_commit_id": "d" * 40,
                "files_sha256": "d" * 64,
            },
            "seal_recovery_protocol": (
                "deterministic-exclusive-hash-chain-v1"
            ),
            "seal_plan_sha256": "e" * 64,
            "union_root_stage_sha256": "f" * 64,
            "union_stage_sha256": "1" * 64,
            "candidate_stage_sha256": "2" * 64,
            "attestation_stage_sha256": "3" * 64,
        })
        launch = json.loads(self.launch.read_text())
        launch.update({
            "schema": P.SourceV6.Launch.LAUNCH_SCHEMA,
            "campaign": "v6-selective-repair",
            "benchmark_revision": P.BENCHMARK_REVISION,
        })
        launch["slurm_template_sha256"] = launch["slurm_script_sha256"]
        return SimpleNamespace(
            attestation_path=self.attestation,
            diagnostic_path=self.amendment,
            intent_path=self.intent,
            execution_receipt_path=self.execution,
            launch_receipt_path=self.launch,
            attestation_raw=self.attestation.read_bytes(),
            diagnostic_raw=self.amendment.read_bytes(),
            intent_raw=self.intent.read_bytes(),
            execution_raw=self.execution.read_bytes(),
            launch_raw=self.launch.read_bytes(),
            inventory_raw=self.inventory.read_bytes(),
            attestation=json.loads(self.attestation.read_text()),
            intent=json.loads(self.intent.read_text()),
            execution=execution,
            launch=launch,
            inventory=json.loads(self.inventory.read_text()),
            tracked_file_sha256=dict(sorted(tracked.items())),
        )

    @contextlib.contextmanager
    def patch(self):
        with mock.patch.multiple(
                P,
                SOURCE_V4_REPO=self.repo,
                SOURCE_V4_ATTESTATION_PATH=self.attestation,
                SOURCE_V4_ARTIFACT_DIR=self.artifact_dir,
                SOURCE_V4_INTENT_PATH=self.intent,
                SOURCE_V4_LAUNCH_RECEIPT_PATH=self.launch,
                SOURCE_V4_LAUNCH_RECEIPT_SHA256=self.launch_sha,
                SOURCE_V4_LAUNCH_INTENT_SHA256=self.intent_sha,
                SOURCE_V4_EXECUTION_RECEIPT_PATH=self.execution,
                SOURCE_V4_SLURM_PATH=self.slurm,
                SOURCE_V4_CODE_MANIFEST_PATH=self.manifest,
                SOURCE_V4_AMENDMENT_PATH=self.amendment,
                SOURCE_V4_INVENTORY_PATH=self.inventory,
                SOURCE_V4_OUTPUT_DIR=self.output_dir,
                SOURCE_V4_CANDIDATE_PATH=self.candidate,
                SOURCE_V4_SLURM_SHA256=self.slurm_sha,
                SOURCE_V4_CODE_MANIFEST_SHA256=self.manifest_sha,
                SOURCE_V4_AMENDMENT_SHA256=self.amendment_sha,
                SOURCE_V4_INVENTORY_SHA256=self.inventory_sha,
                SOURCE_V4_FIXED_HASHES=self.fixed_hashes,
                SOURCE_V4_V3_DIAGNOSTIC_SHA256=self.diagnostic_sha,
                SOURCE_V4_PRODUCER_COMMIT_ID="4" * 40,
                SOURCE_V4_JOB_ID="123456",
                _repository_snapshot_files=lambda commit, relatives: {
                    relative: (self.repo / relative).read_bytes()
                    for relative in relatives
                },
                SOURCE_AUDIT_TASK_TIMEOUT_SECONDS=14400,
        ), mock.patch.object(
            P, "_load_v6_source_chain", side_effect=lambda *args: self.v6_chain()
        ), mock.patch.object(
            SourceAudit.Inventory, "SHADOW_FAMILIES",
            self.shadow_represented,
        ), mock.patch.object(
            SourceAudit, "ALL_PRIOR_UNREPRESENTED_FAMILIES",
            self.all_prior_unrepresented,
        ), mock.patch.object(
            SourceAudit, "__file__",
            str(
                self.repo / "experiments" /
                "audit_pdb_terminal_incidence_confirmation_sources.py"
            ),
        ), mock.patch.object(
            SourceAudit.Inventory, "__file__",
            str(
                self.repo / "experiments" /
                "pdb_terminal_incidence_confirmation_inventory.py"
            ),
        ):
            yield

    def mutate_intent(self, mutate) -> None:
        intent = json.loads(self.intent.read_text())
        mutate(intent)
        intent_raw = _write(self.intent, intent)
        launch = json.loads(self.launch.read_text())
        job_id = launch["job_id"]
        launch = {
            "schema": P.SOURCE_AUDIT_SCHEMA + "/campaign-v4/launch",
            **{key: value for key, value in intent.items() if key != "schema"},
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": job_id,
        }
        launch_raw = _write(self.launch, launch)
        self.launch_sha = hashlib.sha256(launch_raw).hexdigest()
        execution = json.loads(self.execution.read_text())
        execution["launch_receipt_sha256"] = hashlib.sha256(
            launch_raw
        ).hexdigest()
        execution["v3_infrastructure_diagnostic"] = launch[
            "v3_infrastructure_diagnostic"
        ]
        _write(self.execution, execution)

    def freeze(self, path: Path) -> dict:
        materials = self.load()
        value = {
            "schema": P.FREEZE_SCHEMA,
            "freeze_repository_revision": "e" * 40,
            "source_audit": {
                "campaign": materials.execution_receipt["campaign"],
                "attestation_path": self.attestation.relative_to(
                    P.REPO
                ).as_posix(),
                "terminal_diagnostic_path": self.amendment.relative_to(
                    P.REPO
                ).as_posix(),
                "execution_receipt_path": self.execution.relative_to(
                    P.REPO
                ).as_posix(),
                "launch_receipt_path": self.launch.relative_to(
                    P.REPO
                ).as_posix(),
                "launch_intent_path": self.intent.relative_to(P.REPO).as_posix(),
                "attestation_sha256": materials.attestation_sha256,
                "terminal_diagnostic_sha256": materials.diagnostic_sha256,
                "execution_receipt_sha256": (
                    materials.execution_receipt_sha256
                ),
                "launch_receipt_sha256": materials.launch_receipt_sha256,
                "launch_intent_sha256": materials.intent_sha256,
                "cohort_manifest_sha256": materials.cohort_manifest_sha256,
                "attestation_records_sha256": materials.records_sha256,
                "translator_source_sha256": (
                    materials.translator_source_sha256
                ),
                "job_id": materials.launch_receipt["job_id"],
                "code_manifest_sha256": materials.execution_receipt[
                    "v6_code_manifest_sha256"
                ],
                "repository_commit_id": materials.launch_receipt[
                    "repository_commit_id"
                ],
                "union_tree_sha256": materials.execution_receipt[
                    "union_tree"
                ]["sha256"],
                "union_sources_sha256": materials.execution_receipt[
                    "union_sources_sha256"
                ],
                "v6_output_tree_sha256": materials.execution_receipt[
                    "v6_output_tree"
                ]["sha256"],
                "v5_launch_receipt_sha256": materials.execution_receipt[
                    "v5_launch_receipt_sha256"
                ],
                "v5_code_manifest_sha256": materials.execution_receipt[
                    "v5_code_manifest_sha256"
                ],
                "slurm_template_sha256": materials.launch_receipt[
                    "slurm_template_sha256"
                ],
                **P.v6_recovery_provenance(
                    materials.execution_receipt
                ),
                "tracked_file_sha256": materials.tracked_file_sha256,
            },
            "planner": {
                "revision": P.PLANNER_REVISION_REQUIRED,
                "cache_name": "synthetic-confirmation-a-cache",
                "build_options": list(P.BUILD_OPTIONS),
                "downward_sha256": "b" * 64,
                "preprocess_sha256": "c" * 64,
                "tree_manifest_sha256": "d" * 64,
            },
            "design": {
                "protocol_sha256": P.sha256_file(P.PROTOCOL_PATH),
                "option_matrix_sha256": P.option_matrix_digest(),
                "cohort_tasks": P.COHORT_TASKS,
                "configs": P.CONFIG_COUNT,
                "cells": P.CELL_COUNT,
                "horizon": P.HORIZON,
                "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
                "bootstrap_seed": P.BOOTSTRAP_SEED,
            },
            "experiment_source_sha256": {
                relative: P.sha256_file(P.REPO / relative)
                for relative in P.EXPERIMENT_SOURCE_FILES
            },
        }
        _write(path, value)
        return value


class ConfirmationAProtocolTest(unittest.TestCase):
    def test_analysis_v4_preregisters_noncertificate_baselines(self):
        self.assertEqual(
            P.ANALYSIS_PROTOCOL,
            "pdb-terminal-incidence-confirmation-a-analysis-v4",
        )
        self.assertEqual(
            P.PREDICTORS[0:3], ("I", "D", "value_count")
        )
        self.assertEqual(P.PREDICTOR_BASELINES[0:2], ("D", "value_count"))
        self.assertNotIn("D", P.CERTIFICATE_BASELINES)
        self.assertNotIn("value_count", P.CERTIFICATE_BASELINES)
        self.assertEqual(P.ACTIVE_VALUE_COUNT_DIAGNOSTIC, "value_count")
        self.assertEqual(P.MEET_CERTIFICATE, "meet")
        self.assertEqual(P.CERTIFICATE_BASELINES[-1], "meet")
        self.assertEqual(len(P.CERTIFICATE_BASELINES), 7)
        self.assertEqual(len(P.PREDICTORS), 10)

    def test_v6_manifest_contract_has_exact_order_and_cardinality(self):
        self.assertGreater(len(P.SourceV6.CODE_MANIFEST_FILES), 38)
        self.assertEqual(
            len(P.SourceV6.SCOPED_FILES),
            len(P.SourceV6.CODE_MANIFEST_FILES) + 1,
        )
        self.assertEqual(
            tuple(sorted(P.SourceV6.CODE_MANIFEST_FILES)),
            P.SourceV6.CODE_MANIFEST_FILES,
        )

    def test_v6_source_consumer_and_8148_planner_are_bound(self):
        self.assertIn(
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v6.py",
            P.EXPERIMENT_SOURCE_FILES,
        )
        self.assertEqual(
            P.PLANNER_REVISION_REQUIRED,
            "8148f798f13059ee881ad2471bd20cdd61d2ec18",
        )

    def test_design_and_cegar_bound(self):
        P.validate_protocol_design()
        cegar = P.SEARCHES["pdb_cegar_shadow"]
        self.assertIn("cegar_max_time=infinity", cegar)
        self.assertIn("cegar_max_refinements=128", cegar)
        prose = " ".join(P.PROTOCOL_PATH.read_text().split())
        self.assertIn("at most 128 refinement calls", prose)

    def test_exact_v4_campaign_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            materials = SourceFixture(Path(tmp)).load()
        self.assertEqual(len(materials.tasks), 650)
        self.assertEqual(materials.launch_receipt["memory_per_cpu"], "1024G")

    def test_v4_attestation_and_execution_receipt_are_both_required(self):
        for missing in ("attestation", "execution"):
            with self.subTest(missing=missing), tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                getattr(fixture, missing).unlink()
                with self.assertRaisesRegex(P.ProtocolError, "cannot load"):
                    fixture.load()

    def test_attestation_envelope_and_split_replay_are_exact(self):
        mutations = (
            lambda value: value.update(unexpected=True),
            lambda value: value.update(split_seed="wrong"),
            lambda value: value.update(
                source_inventory_records_sha256="9" * 64
            ),
            lambda value: value["records"][0].update(
                supported=False,
                support_exclusion_reasons=["translation-input-rejected"],
            ),
            lambda value: value["cohorts"]["confirmation_a"]["tasks"][0].update(
                source_audit_evidence_sha256="8" * 64
            ),
        )
        for mutate in mutations:
            with self.subTest(mutate=mutate), tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                attestation = json.loads(fixture.attestation.read_text())
                mutate(attestation)
                attestation["records_sha256"] = hashlib.sha256(
                    P.canonical_json_line(attestation["records"])
                ).hexdigest()
                cohort = attestation["cohorts"]["confirmation_a"]
                cohort["tasks_sha256"] = hashlib.sha256(
                    P.canonical_json_line(cohort["tasks"])
                ).hexdigest()
                attestation_raw = _write(fixture.attestation, attestation)
                execution = json.loads(fixture.execution.read_text())
                execution["attestation_sha256"] = hashlib.sha256(
                    attestation_raw
                ).hexdigest()
                execution["attestation_records_sha256"] = attestation[
                    "records_sha256"
                ]
                execution["cohort_manifest_sha256"]["confirmation_a"] = (
                    cohort["tasks_sha256"]
                )
                _write(fixture.execution, execution)
                with self.assertRaises(P.ProtocolError):
                    fixture.load()

    def test_global_prelaunch_gate_requires_feasible_disjoint_b(self):
        def missing_guided(value):
            value["cohorts"].pop("guided_b")

        def under_floor_guided(value):
            guided = value["cohorts"]["guided_b"]
            guided["tasks"] = guided["tasks"][:199]
            guided["tasks_sha256"] = hashlib.sha256(
                P.canonical_json_line(guided["tasks"])
            ).hexdigest()

        def overlapping_guided(value):
            guided = value["cohorts"]["guided_b"]
            guided["tasks"][0] = json.loads(json.dumps(
                value["cohorts"]["confirmation_a"]["tasks"][0]
            ))
            guided["tasks_sha256"] = hashlib.sha256(
                P.canonical_json_line(guided["tasks"])
            ).hexdigest()

        for mutate in (missing_guided, under_floor_guided, overlapping_guided):
            with self.subTest(mutate=mutate.__name__), \
                    tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                attestation = json.loads(fixture.attestation.read_text())
                mutate(attestation)
                attestation_raw = _write(fixture.attestation, attestation)
                execution = json.loads(fixture.execution.read_text())
                execution["attestation_sha256"] = hashlib.sha256(
                    attestation_raw
                ).hexdigest()
                execution["cohort_manifest_sha256"] = {
                    name: cohort["tasks_sha256"]
                    for name, cohort in attestation["cohorts"].items()
                }
                _write(fixture.execution, execution)
                with self.assertRaises(P.ProtocolError):
                    fixture.load()

    def test_unverified_split_producer_is_not_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            producer = (
                fixture.repo / "experiments" /
                "audit_pdb_terminal_incidence_confirmation_sources.py"
            )
            producer.write_bytes(producer.read_bytes() + b"# tamper\n")
            with fixture.patch(), mock.patch.object(
                    P.importlib, "import_module",
                    side_effect=AssertionError("unverified producer executed"),
            ) as imported:
                with self.assertRaises(P.ProtocolError):
                    P.load_source_materials(
                        fixture.attestation, fixture.execution, fixture.launch
                    )
                imported.assert_not_called()

    def test_unverified_inventory_dependency_is_not_imported(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            dependency = (
                fixture.repo / "experiments" /
                "pdb_terminal_incidence_confirmation_inventory.py"
            )
            dependency.write_bytes(
                dependency.read_bytes()
                + b"\nraise RuntimeError('unverified dependency executed')\n"
            )
            manifest_hashes = {
                line.split("  ", 1)[1]: line.split("  ", 1)[0]
                for line in fixture.manifest.read_text().splitlines()
            }
            attestation = json.loads(fixture.attestation.read_text())
            names = (
                "audit_pdb_terminal_incidence_confirmation_sources",
                "pdb_terminal_incidence_confirmation_inventory",
            )
            saved = {name: sys.modules.pop(name, None) for name in names}
            try:
                with fixture.patch(), mock.patch.object(
                        P.importlib, "import_module",
                        side_effect=AssertionError(
                            "unverified dependency imported"
                        ),
                ) as imported, self.assertRaises(P.ProtocolError):
                    P._validate_attestation_split(
                        attestation, manifest_hashes
                    )
                imported.assert_not_called()
            finally:
                for name, module in saved.items():
                    if module is not None:
                        sys.modules[name] = module

    def test_nested_source_evidence_schema_is_replayed_exactly(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            attestation = json.loads(fixture.attestation.read_text())
            attestation["records"][0]["translation"][
                "arbitrary_unexpected_nested_field"
            ] = True
            with fixture.patch():
                gate, cohorts = SourceAudit.split_supported(
                    attestation["records"]
                )
            attestation["records_sha256"] = hashlib.sha256(
                P.canonical_json_line(attestation["records"])
            ).hexdigest()
            attestation["prelaunch_gate"] = gate
            attestation["cohorts"] = cohorts
            attestation["confirmation_prelaunch_authorized"] = gate["passed"]
            attestation_raw = _write(fixture.attestation, attestation)
            execution = json.loads(fixture.execution.read_text())
            execution["attestation_sha256"] = hashlib.sha256(
                attestation_raw
            ).hexdigest()
            execution["attestation_records_sha256"] = attestation[
                "records_sha256"
            ]
            execution["prelaunch_gate"] = gate
            execution["confirmation_prelaunch_authorized"] = gate["passed"]
            execution["cohort_manifest_sha256"] = {
                name: cohort["tasks_sha256"]
                for name, cohort in cohorts.items()
            }
            _write(fixture.execution, execution)
            with self.assertRaises(P.ProtocolError):
                fixture.load()

    def test_v4_local_byte_chain_tampering_is_rejected(self):
        def corrupt(path):
            path.write_bytes(path.read_bytes() + b"tamper\n")

        targets = (
            lambda fixture: fixture.intent,
            lambda fixture: fixture.slurm,
            lambda fixture: fixture.manifest,
            lambda fixture: fixture.amendment,
            lambda fixture: fixture.inventory,
            lambda fixture: fixture.repo / P.SOURCE_V4_MANIFEST_FILES[3],
        )
        for target in targets:
            with self.subTest(target=target), tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                corrupt(target(fixture))
                with self.assertRaises(P.ProtocolError):
                    fixture.load()

    def test_symlinked_sealed_source_artifacts_are_rejected(self):
        for attribute in ("attestation", "execution", "launch"):
            with self.subTest(attribute=attribute), \
                    tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                path = getattr(fixture, attribute)
                target = path.with_name(path.name + ".target")
                path.rename(target)
                path.symlink_to(target.name)
                with self.assertRaisesRegex(
                    P.ProtocolError, "canonical regular JSON"
                ):
                    fixture.load()

    def test_v4_intent_fixed_materials_and_repository_snapshot_are_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            fixture.mutate_intent(lambda intent: intent.update(
                candidate_records_sha256="9" * 64
            ))
            with self.assertRaises(P.ProtocolError):
                fixture.load()
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            with fixture.patch():
                snapshot = {
                    relative: (fixture.repo / relative).read_bytes()
                    for relative in sorted({
                        *P.SOURCE_V4_MANIFEST_FILES,
                        P.SOURCE_V4_SLURM_RELATIVE,
                        P.SOURCE_V4_MANIFEST_RELATIVE,
                    })
                }
                snapshot[P.SOURCE_V4_SLURM_RELATIVE] += b"tamper\n"
                with mock.patch.object(
                    P, "_repository_snapshot_files", return_value=snapshot
                ), self.assertRaisesRegex(P.ProtocolError, "snapshot"):
                    P.load_source_materials(
                        fixture.attestation, fixture.execution, fixture.launch
                    )

    def test_freeze_revision_tracks_all_v4_bound_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            materials = fixture.load()
            with mock.patch.object(Freeze, "REPO", fixture.repo), \
                    mock.patch.object(
                        Freeze.JJ,
                        "tracked_file_sha256",
                        side_effect=lambda repo, revision, relative: (
                            materials.tracked_file_sha256[relative]
                        ),
                    ):
                self.assertEqual(
                    Freeze._tracked_source_v6_hashes(materials, "4" * 40),
                    materials.tracked_file_sha256,
                )
            first = next(iter(materials.tracked_file_sha256))
            with mock.patch.object(Freeze, "REPO", fixture.repo), \
                    mock.patch.object(
                        Freeze.JJ,
                        "tracked_file_sha256",
                        side_effect=lambda repo, revision, relative: (
                            "9" * 64 if relative == first
                            else materials.tracked_file_sha256[relative]
                        ),
                    ), self.assertRaisesRegex(Freeze.FreezeError, "freeze revision"):
                Freeze._tracked_source_v6_hashes(materials, "4" * 40)

    def test_freeze_requires_source_revision_ancestor(self):
        with tempfile.TemporaryDirectory() as tmp:
            materials = SourceFixture(Path(tmp)).load()
        with mock.patch.object(
                Freeze.JJ, "require_ancestor",
                side_effect=Freeze.JJ.JjCacheError("divergent"),
        ), self.assertRaisesRegex(Freeze.FreezeError, "not an ancestor"):
            Freeze._require_source_ancestor(materials, "4" * 40)

    def test_freeze_clean_parent_uses_live_working_copy_snapshot(self):
        revision = "4" * 40
        with mock.patch.object(
            Freeze.JJ, "live_working_copy_diff_summary", return_value="",
        ) as live, mock.patch.object(
            Freeze.JJ, "parent_commit", return_value=revision,
        ) as parent:
            self.assertEqual(Freeze._require_clean_parent(None), revision)
        live.assert_called_once_with(Freeze.REPO)
        parent.assert_called_once_with(Freeze.REPO)
        with mock.patch.object(
            Freeze.JJ, "live_working_copy_diff_summary", return_value="M source",
        ), mock.patch.object(
            Freeze.JJ, "parent_commit",
        ) as parent, self.assertRaisesRegex(Freeze.FreezeError, "clean empty"):
            Freeze._require_clean_parent(None)
        parent.assert_not_called()

    def test_jj_queries_reject_wrong_identity_and_ignore_path_shadow(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "jj"
            fake.write_bytes(b"#!/bin/sh\nexit 0\n")
            with mock.patch.object(Freeze.JJ, "JJ_EXECUTABLE", fake), \
                    self.assertRaises(Freeze.JJ.JjCacheError):
                Freeze.JJ._verify_jj_identity()
        completed = mock.Mock(stdout=b"ok\n")
        with mock.patch.dict(os.environ, {"PATH": "/hostile/path"}), \
                mock.patch.object(
                    Freeze.JJ, "_verify_jj_identity", return_value=None
                ), mock.patch.object(
                    Freeze.JJ.subprocess, "run", return_value=completed
                ) as run:
            self.assertEqual(
                Freeze.JJ._run_jj(P.REPO, ["version"]), b"ok\n"
            )
        command = run.call_args.args[0]
        self.assertEqual(command[0], str(Freeze.JJ.JJ_EXECUTABLE))
        self.assertIn("--ignore-working-copy", command)

    def test_source_snapshot_rechecks_jj_after_each_subprocess(self):
        with mock.patch.object(
                P, "sha256_file",
                side_effect=[P.SOURCE_V4_JJ_EXECUTABLE_SHA256, "9" * 64],
        ), mock.patch.object(
                P.subprocess, "check_output", return_value="file\n"
        ) as query, self.assertRaisesRegex(
                P.ProtocolError, "Jujutsu executable identity"
        ):
            P._repository_snapshot_files("4" * 40, ["file"])
        query.assert_called_once()

    def test_freeze_rechecks_live_bytes_around_revision_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            materials = fixture.load()
            first = next(iter(materials.tracked_file_sha256))
            target = fixture.repo / first
            changed = []

            def mutate_during_lookup(repo, revision, relative):
                if relative == first and not changed:
                    target.write_bytes(target.read_bytes() + b"swap\n")
                    changed.append(True)
                return materials.tracked_file_sha256[relative]

            with mock.patch.object(Freeze, "REPO", fixture.repo), \
                    mock.patch.object(
                        Freeze.JJ, "tracked_file_sha256",
                        side_effect=mutate_during_lookup,
                    ), self.assertRaisesRegex(
                        Freeze.FreezeError, "changed during revision check"
                    ):
                Freeze._tracked_source_v6_hashes(materials, "4" * 40)

    def test_freeze_reloads_source_after_mocked_planner_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))

            def mocked_cache():
                fixture.attestation.write_bytes(
                    fixture.attestation.read_bytes() + b"changed-in-cache\n"
                )

            with fixture.patch(), mock.patch.object(
                    Freeze, "REPO", fixture.repo
            ), mock.patch.object(
                    Freeze, "_require_clean_parent", return_value="4" * 40
            ), mock.patch.object(
                    Freeze, "_require_source_ancestor", return_value=None
            ):
                mocked_cache()
                with self.assertRaises(P.ProtocolError):
                    Freeze._revalidate_before_write(
                        {},
                        attestation=fixture.attestation,
                        execution_receipt=fixture.execution,
                        launch_receipt=fixture.launch,
                        freeze_repository_revision="4" * 40,
                    )

    def test_freeze_rejects_live_tamper_and_symlink_for_sealed_artifact(self):
        for mutation in ("tamper", "symlink"):
            with self.subTest(mutation=mutation), \
                    tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                materials = fixture.load()
                path = materials.attestation_path
                if mutation == "tamper":
                    path.write_bytes(path.read_bytes() + b"tamper\n")
                else:
                    target = path.with_name(path.name + ".target")
                    path.rename(target)
                    path.symlink_to(target.name)
                with mock.patch.object(Freeze, "REPO", fixture.repo), \
                        self.assertRaises(Freeze.FreezeError):
                    Freeze._attest_tracked_file(
                        path, materials.attestation_sha256, "4" * 40,
                        "sealed source artifact",
                    )

    def test_v3_diagnostic_rejects_self_rehashed_substitution(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            fixture.mutate_intent(lambda intent: intent[
                "v3_infrastructure_diagnostic"
            ].update(successful_v3_log_contents_inspected=True))
            with self.assertRaises(P.ProtocolError):
                fixture.load()

    def test_cohort_hash_matches_source_audit_canonical_line_convention(self):
        tasks = [_task(index) for index in range(P.COHORT_TASKS)]
        source_audit_canonical_json = P.canonical_json(tasks) + b"\n"
        self.assertEqual(
            P.canonical_json_line(tasks), source_audit_canonical_json
        )
        self.assertEqual(
            hashlib.sha256(P.canonical_json_line(tasks)).hexdigest(),
            hashlib.sha256(source_audit_canonical_json).hexdigest(),
        )

    def test_v1_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture = SourceFixture(root)
            launch = json.loads(fixture.launch.read_text())
            launch["schema"] = launch["schema"].replace(
                "/campaign-v4/launch", "/launch"
            )
            launch_raw = _write(fixture.launch, launch)
            execution = json.loads(fixture.execution.read_text())
            execution["schema"] = execution["schema"].replace(
                "/campaign-v4/execution", "/execution"
            )
            execution["launch_receipt_sha256"] = hashlib.sha256(
                launch_raw
            ).hexdigest()
            _write(fixture.execution, execution)
            with self.assertRaisesRegex(P.ProtocolError, "schema chain"):
                fixture.load()

    def test_nonexact_attestation_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            data = json.loads(fixture.attestation.read_text())
            data["schema"] = P.SOURCE_AUDIT_SCHEMA + "-lookalike"
            att_raw = _write(fixture.attestation, data)
            execution = json.loads(fixture.execution.read_text())
            execution["attestation_sha256"] = hashlib.sha256(att_raw).hexdigest()
            _write(fixture.execution, execution)
            with self.assertRaisesRegex(P.ProtocolError, "schema chain"):
                fixture.load()

    def test_mismatched_v3_failure_diagnostic_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            execution = json.loads(fixture.execution.read_text())
            execution["v3_infrastructure_diagnostic"] = {
                **execution["v3_infrastructure_diagnostic"],
                "successful_v3_log_contents_inspected": True,
            }
            _write(fixture.execution, execution)
            with self.assertRaisesRegex(P.ProtocolError, "diagnostic chain"):
                fixture.load()

    def test_non_full_v4_rerun_diagnostic_is_rejected_even_when_matched(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            fixture.mutate_intent(lambda intent: intent[
                "v3_infrastructure_diagnostic"
            ]["full_rerun_decision"].update(scope="selected-shards"))
            with self.assertRaises(P.ProtocolError):
                fixture.load()

    def test_prior_reuse_and_wrong_v3_resources_are_rejected(self):
        cases = (
            {"launch": {"campaign": "v3"}},
            {"execution": {"campaign": "v3"}},
            {"launch": {"reused_v1_shards": 1}},
            {"execution": {"reused_v1_shards": 1}},
            {"launch": {"reused_v2_shards": 1}},
            {"execution": {"reused_v2_shards": 1}},
            {"launch": {"reused_v2_shards": False}},
            {"execution": {"reused_v2_shards": False}},
            {"launch": {"reused_v3_shards": 1}},
            {"execution": {"reused_v3_shards": 1}},
            {"launch": {"whole_campaign_rerun": False}},
            {"execution": {"whole_campaign_rerun": False}},
            {"launch": {"memory_per_cpu": "256G"}},
            {"execution": {"memory_per_cpu": "256G"}},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp), **overrides)
                    with self.assertRaisesRegex(
                        P.ProtocolError, "did not authorize"
                    ):
                        fixture.load()

    def test_v3_diagnostic_must_attest_a_full_outcome_blind_rerun(self):
        cases = (
            ("schema", P.SOURCE_AUDIT_SCHEMA + "/wrong-diagnostic"),
            ("successful_v3_shard_contents_inspected", True),
            ("successful_v3_log_contents_inspected", True),
            ("source_support_outcomes_used_for_v4_design", True),
        )
        for field, value in cases:
            with self.subTest(field=field, value=value):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp))
                    fixture.mutate_intent(
                        lambda intent: intent[
                            "v3_infrastructure_diagnostic"
                        ].update(
                            {field: value}
                        )
                    )
                    with self.assertRaises(P.ProtocolError):
                        fixture.load()

    def test_source_provenance_chain_must_match(self):
        cases = (
            {"launch": {"source_inventory_sha256": "9" * 64}},
            {"execution": {"source_inventory_sha256": "9" * 64}},
            {"launch": {"code_manifest_sha256": "9" * 64}},
            {"execution": {"code_manifest_sha256": "9" * 64}},
            {"execution": {"job_id": "654321"}},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp), **overrides)
                    with self.assertRaises(P.ProtocolError):
                        fixture.load()

    def test_source_v4_scheduler_contract_is_exact(self):
        cases = (
            {"launch": {"partition": "thin"}},
            {"launch": {"qos": "low"}},
            {"launch": {"array": "0-818"}},
            {"launch": {"array_throttle": 10}},
            {"launch": {"array_throttle": False}},
            {"launch": {"array_tasks": 819}},
            {"launch": {"tasks_per_array_task": 1}},
            {"launch": {"candidates": 1639}},
            {"launch": {"cpus_per_task": 2}},
            {"launch": {"cpus_per_task": True}},
            {"launch": {"time_limit": "01:40:00"}},
            {"launch": {"task_timeout_seconds": 2700}},
            {"execution": {"partition": "thin"}},
            {"execution": {"array_throttle": 10}},
            {"execution": {"array_throttle": False}},
            {"execution": {"shards": 819}},
            {"execution": {"candidates": 1639}},
        )
        for overrides in cases:
            with self.subTest(overrides=overrides):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp), **overrides)
                    with self.assertRaisesRegex(
                        P.ProtocolError, "scheduler contract"
                    ):
                        fixture.load()

    def test_source_v4_scheduler_row_identity_is_exact(self):
        completed_rows = [{
            "array_task": index,
            "state": "COMPLETED",
            "exit_code": "0:0",
            "elapsed": "00:01:00",
            "partition": "fat",
        } for index in range(820)]
        cases = (
            {"scheduler_rows": []},
            {"scheduler_rows": [{
                "array_task": index,
                "state": "COMPLETED",
                "exit_code": "0:0",
                "elapsed": "00:01:00",
                "partition": "thin" if index == 17 else "fat",
            } for index in range(820)]},
            {"scheduler_rows": [{
                "array_task": 18 if index == 17 else index,
                "state": "COMPLETED",
                "exit_code": "0:0",
                "elapsed": "00:01:00",
                "partition": "fat",
            } for index in range(820)]},
            {"scheduler_rows": [{
                "array_task": False if index == 0 else index,
                "state": "COMPLETED",
                "exit_code": "0:0",
                "elapsed": "00:01:00",
                "partition": "fat",
            } for index in range(820)]},
            {
                "scheduler_rows": [
                    {
                        **row,
                        "state": "FAILED" if index == 17 else "COMPLETED",
                        "exit_code": "1:0" if index == 17 else "0:0",
                    }
                    for index, row in enumerate(completed_rows)
                ],
                "scheduler_state_counts": {"COMPLETED": 819, "FAILED": 1},
            },
        )
        for execution in cases:
            with self.subTest(first=str(execution)[:80]):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(
                        Path(tmp), execution=execution
                    )
                    with self.assertRaisesRegex(
                        P.ProtocolError, "scheduler rows"
                    ):
                        fixture.load()

    def test_source_v4_scheduler_resource_rows_are_exact(self):
        mutations = (
            ("array_task", False),
            ("account", "other"),
            ("partition", "thin"),
            ("qos", "short"),
            ("req_cpus", True),
            ("req_mem", "511G"),
            ("time_limit", "04:09:59"),
            ("state", "FAILED"),
            ("exit_code", "1:0"),
            ("job_name", "wrong"),
        )
        for field, value in mutations:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                execution = json.loads(fixture.execution.read_text())
                execution["scheduler_contract_rows"][0][field] = value
                _write(fixture.execution, execution)
                with self.assertRaisesRegex(P.ProtocolError, "resource accounting"):
                    fixture.load()

    def test_source_execution_environment_is_bound(self):
        for case in (
            "missing", "export", "boolean", "python-hash", "execution",
        ):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp).resolve()
                    changed_export = _source_execution_environment(root)
                    changed_export["submission_export"] = "ALL"
                    boolean_flag = _source_execution_environment(root)
                    boolean_flag["python_no_user_site_flag"] = True
                    overrides = {
                        "missing": {"launch": {"execution_environment": None}},
                        "export": {
                            "launch": {"execution_environment": changed_export}
                        },
                        "boolean": {
                            "launch": {"execution_environment": boolean_flag}
                        },
                        "python-hash": {
                            "launch": {"python_environment_sha256": "invalid"}
                        },
                        "execution": {
                            "execution": {
                                "execution_environment": {"unexpected": True}
                            }
                        },
                    }[case]
                    fixture = SourceFixture(Path(tmp), **overrides)
                    with self.assertRaisesRegex(
                        P.ProtocolError, "execution environment"
                    ):
                        fixture.load()

    def test_confirmation_task_schema_rank_aliases_and_candidate_ids_are_exact(self):
        def missing_fields(tasks):
            for field in ("candidate_index", "canonical_path", "aliases"):
                tasks[0].pop(field)

        def boolean_index(tasks):
            tasks[0]["candidate_index"] = False

        def duplicate_index(tasks):
            tasks[1]["candidate_index"] = tasks[0]["candidate_index"]

        def out_of_range_index(tasks):
            tasks[0]["candidate_index"] = 1640

        def inconsistent_shadow_flags(tasks):
            tasks[0]["is_shadow_family"] = tasks[0][
                "is_shadow_unrepresented"
            ]

        def wrong_rank(tasks):
            tasks[0]["selection_rank_sha256"] = "9" * 64

        def empty_aliases(tasks):
            tasks[0]["aliases"] = []

        for mutation in (
            missing_fields, boolean_index, duplicate_index,
            out_of_range_index, inconsistent_shadow_flags, wrong_rank,
            empty_aliases,
        ):
            with self.subTest(mutation=mutation.__name__), \
                    tempfile.TemporaryDirectory() as tmp:
                fixture = SourceFixture(Path(tmp))
                attestation = json.loads(fixture.attestation.read_text())
                cohort = attestation["cohorts"]["confirmation_a"]
                mutation(cohort["tasks"])
                cohort_sha = hashlib.sha256(
                    P.canonical_json_line(cohort["tasks"])
                ).hexdigest()
                cohort["tasks_sha256"] = cohort_sha
                attestation_raw = _write(fixture.attestation, attestation)
                execution = json.loads(fixture.execution.read_text())
                execution["attestation_sha256"] = hashlib.sha256(
                    attestation_raw
                ).hexdigest()
                execution["cohort_manifest_sha256"]["confirmation_a"] = (
                    cohort_sha
                )
                _write(fixture.execution, execution)
                with self.assertRaises(P.ProtocolError):
                    fixture.load()

    def test_v4_original_output_and_environment_tree_are_exact(self):
        def recovery(execution):
            execution["recovery"] = {"unexpected": True}

        def wrong_environment_hash(execution):
            execution["task_environment_manifest"]["records"][17][
                "sha256"
            ] = "9" * 64

        def wrong_tree_digest(execution):
            execution["original_output_tree"]["sha256"] = "9" * 64

        def boolean_task_index(execution):
            execution["task_environment_manifest"]["records"][0][
                "array_task"
            ] = False

        def wrong_root(execution):
            execution["original_output_tree"]["root_identity"][
                "inode"
            ] = 99

        for mutation in (
            recovery, wrong_environment_hash, boolean_task_index,
            wrong_tree_digest, wrong_root,
        ):
            with self.subTest(mutation=mutation.__name__):
                with tempfile.TemporaryDirectory() as tmp:
                    fixture = SourceFixture(Path(tmp))
                    execution = json.loads(fixture.execution.read_text())
                    mutation(execution)
                    _write(fixture.execution, execution)
                    with self.assertRaises(P.ProtocolError):
                        fixture.load()

    def test_executed_source_manifest_covers_reused_runtime_modules(self):
        self.assertIn(
            "experiments/audit_pdb_terminal_incidence_shadow.py",
            P.EXPERIMENT_SOURCE_FILES,
        )
        self.assertIn(
            "experiments/pdb_terminal_incidence_shadow_protocol.py",
            P.EXPERIMENT_SOURCE_FILES,
        )

    def test_missing_freeze_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(P.ProtocolError):
                P._load_freeze(Path(tmp) / "missing.json")

    def test_synthetic_complete_freeze_is_accepted_and_source_tamper_rejected(self):
        with tempfile.TemporaryDirectory(
            prefix=".confirmation-a-fixture-", dir=P.SCRIPT_DIR
        ) as tmp:
            root = Path(tmp)
            fixture = SourceFixture(root)
            freeze_path = root / "freeze.json"
            value = fixture.freeze(freeze_path)
            with fixture.patch():
                freeze, materials = P._load_freeze(freeze_path)
            self.assertEqual(freeze, value)
            self.assertEqual(len(materials.tasks), P.COHORT_TASKS)
            with fixture.patch(), mock.patch.object(
                P, "FREEZE_PATH", freeze_path
            ):
                installed = P._installed_values()
            self.assertEqual(
                installed["DIRECTORY_FAMILY_JSON_SHA256"],
                hashlib.sha256(P.canonical_json(
                    materials.directory_to_family
                )).hexdigest(),
            )
            value["source_audit"]["unexpected"] = True
            _write(freeze_path, value)
            with fixture.patch(), self.assertRaisesRegex(
                P.ProtocolError, "source hashes changed"
            ):
                P._load_freeze(freeze_path)
            del value["source_audit"]["unexpected"]
            relative = P.EXPERIMENT_SOURCE_FILES[0]
            value["experiment_source_sha256"][relative] = "9" * 64
            _write(freeze_path, value)
            with fixture.patch(), self.assertRaisesRegex(
                P.ProtocolError, "source changed"
            ):
                P._load_freeze(freeze_path)

    def test_stratum_flag_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = SourceFixture(Path(tmp))
            data = json.loads(fixture.attestation.read_text())
            task = data["cohorts"]["confirmation_a"]["tasks"][0]
            task["is_all_prior_unrepresented"] = not task[
                "is_all_prior_unrepresented"
            ]
            tasks = data["cohorts"]["confirmation_a"]["tasks"]
            data["cohorts"]["confirmation_a"]["tasks_sha256"] = hashlib.sha256(
                P.canonical_json_line(tasks)
            ).hexdigest()
            att_raw = _write(fixture.attestation, data)
            execution = json.loads(fixture.execution.read_text())
            execution["attestation_sha256"] = hashlib.sha256(att_raw).hexdigest()
            execution["cohort_manifest_sha256"]["confirmation_a"] = data[
                "cohorts"
            ]["confirmation_a"]["tasks_sha256"]
            _write(fixture.execution, execution)
            with self.assertRaises(P.ProtocolError):
                fixture.load()


if __name__ == "__main__":
    unittest.main()
