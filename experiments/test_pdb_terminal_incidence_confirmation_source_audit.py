#!/usr/bin/env python3
"""Focused adversarial tests for the universal confirmation source audit."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))

import audit_pdb_terminal_incidence_confirmation_sources as Source
import launch_pdb_terminal_incidence_confirmation_source_audit as Launch
import recover_pdb_terminal_incidence_confirmation_source_audit as Recovery


def _sas(operator_effect: str = "0 0 -1 1", cost: int = 1) -> str:
    return "\n".join((
        "begin_version", "3", "end_version",
        "begin_metric", "1", "end_metric",
        "1",
        "begin_variable", "var0", "-1", "2", "Atom a()", "<none of those>",
        "end_variable",
        "0",
        "begin_state", "0", "end_state",
        "begin_goal", "1", "0 1", "end_goal",
        "1",
        "begin_operator", "move", "0", "1", operator_effect, str(cost),
        "end_operator",
        "0",
    )) + "\n"


def _record(index: int, family: str, supported: bool = True) -> dict:
    digest = hashlib.sha256("problem-{}".format(index).encode()).hexdigest()
    domain_digest = hashlib.sha256(family.encode()).hexdigest()
    candidate = {
        "candidate_index": index,
        "directory": family + "-directory",
        "family": family,
        "problem": "p{:04d}.pddl".format(index),
        "domain_file": family + "/domain.pddl",
        "problem_file": family + "/p{:04d}.pddl".format(index),
        "domain_sha256": domain_digest,
        "problem_sha256": digest,
        "canonical_path": family + "/p{:04d}.pddl".format(index),
        "is_shadow_family": family in Source.Inventory.SHADOW_FAMILIES,
        "is_shadow_unrepresented": (
            family not in Source.Inventory.SHADOW_FAMILIES
        ),
        "is_all_prior_represented": (
            family in Source.Inventory.ALL_PRIOR_FAMILIES
        ),
        "is_all_prior_unrepresented": (
            family not in Source.Inventory.ALL_PRIOR_FAMILIES
        ),
        "aliases": [{
            "directory": family + "-directory",
            "family": family,
            "problem": "p{:04d}.pddl".format(index),
            "domain_file": family + "/domain.pddl",
            "problem_file": family + "/p{:04d}.pddl".format(index),
            "domain_sha256": domain_digest,
            "problem_sha256": digest,
        }],
    }
    translation = {
        "status": "success",
        "sas": {
            "num_operators": 1,
            "num_zero_cost_operators": 0,
            "min_operator_cost": 1,
            "num_serialized_axioms": 0,
            "num_conditional_effects": 0,
        },
    }
    normalization = {
        "status": "success",
        "num_normalized_axioms": 0,
    }
    reasons = [] if supported else ["normalized-axioms"]
    if not supported:
        normalization["num_normalized_axioms"] = 1
    return {
        **candidate,
        "translation_attempted": True,
        "translation": translation,
        "normalization": normalization,
        "supported": supported,
        "support_exclusion_reasons": reasons,
    }


def _supported_inventory_records() -> list[dict]:
    manifest = Source.build_inventory_manifest(Source.Inventory.load_inventory())
    records = []
    for candidate in manifest["records"]:
        evidence = _record(
            candidate["candidate_index"], candidate["family"]
        )
        records.append({
            **candidate,
            **{
                key: evidence[key]
                for key in (
                    "translation_attempted", "translation", "normalization",
                    "supported", "support_exclusion_reasons",
                )
            },
        })
    return records


class ConfirmationSourceAuditTest(unittest.TestCase):
    def test_sas_parser_counts_serialized_conditional_effects_and_costs(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "output.sas"
            path.write_text(_sas("1 0 0 0 -1 1", 7), encoding="utf-8")
            parsed = Source.parse_sas(path)
        self.assertEqual(parsed["sas_version"], 3)
        self.assertEqual(parsed["num_operators"], 1)
        self.assertEqual(parsed["num_effects"], 1)
        self.assertEqual(parsed["num_conditional_effects"], 1)
        self.assertEqual(parsed["min_operator_cost"], 7)
        self.assertEqual(parsed["num_serialized_axioms"], 0)

    def test_support_requires_all_three_source_properties(self):
        translation = {
            "status": "success",
            "sas": {
                "num_operators": 2,
                "num_zero_cost_operators": 1,
                "min_operator_cost": 0,
                "num_serialized_axioms": 1,
                "num_conditional_effects": 3,
            },
        }
        normalization = {
            "status": "success", "num_normalized_axioms": 2,
        }
        self.assertEqual(Source._support_reasons(translation, normalization), [
            "nonpositive-serialized-operator-cost",
            "serialized-axioms",
            "serialized-conditional-effects",
            "normalized-axioms",
        ])

    def test_source_inventory_binds_all_prior_family_provenance(self):
        inventory = Source.Inventory.load_inventory()
        manifest = Source.build_inventory_manifest(inventory)
        self.assertEqual(
            len(Source.validate_inventory_manifest(manifest)),
            Source.CANDIDATE_COUNT,
        )
        tampered = json.loads(Source.canonical_json(manifest))
        tampered["prior_family_provenance"]["ledger"][0]["family"] += "-x"
        with self.assertRaisesRegex(
            Source.SourceAuditError, "source inventory identity changed"
        ):
            Source.validate_inventory_manifest(tampered)

    def test_only_exit_31_is_retained_as_unsupported_source_evidence(self):
        candidate = _record(0, "airport")
        completed = subprocess.CompletedProcess(
            args=[], returncode=31, stdout=b"translator output", stderr=b"bad task"
        )
        with (
            mock.patch.object(Source, "_regular_source", return_value=Path("/x")),
            mock.patch.object(
                Source.subprocess, "run", return_value=completed
            ) as run,
            mock.patch.object(
                Source, "_count_normalized_axioms", return_value=0
            ) as normalize,
            mock.patch.dict(
                os.environ, {"PYTHONPYCACHEPREFIX": "/tmp/unique-cache"}
            ),
        ):
            result = Source._scan_task(candidate, Path("/bench"), 2700)
        normalize.assert_not_called()
        self.assertEqual(
            run.call_args.args[0][1:4], ["-B", "-m", "translate"]
        )
        self.assertEqual(run.call_args.kwargs["env"], {
            "PATH": Source.CONTROLLED_PATH,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": "/tmp/unique-cache",
            "PYTHONPATH": str(Source.REPO / "src"),
        })
        self.assertTrue(result["translation_attempted"])
        self.assertFalse(result["supported"])
        self.assertEqual(result["translation"]["status"], "input-rejected")
        self.assertEqual(result["normalization"]["status"], "not-applicable")
        self.assertEqual(
            result["support_exclusion_reasons"], ["translation-input-rejected"]
        )
        self.assertEqual(
            result["translation"]["stderr"]["sha256"],
            hashlib.sha256(b"bad task").hexdigest(),
        )

    def test_timeout_and_critical_exit_fail_the_shard(self):
        candidate = _record(0, "airport")
        environment = {"PYTHONPYCACHEPREFIX": "/tmp/unique-cache"}
        with (
            mock.patch.object(Source, "_regular_source", return_value=Path("/x")),
            mock.patch.object(
                Source.subprocess,
                "run",
                side_effect=subprocess.TimeoutExpired([], 2700, stderr=b"slow"),
            ),
            mock.patch.dict(os.environ, environment),
            self.assertRaises(Source.InfrastructureAuditError),
        ):
            Source._scan_task(candidate, Path("/bench"), 2700)
        completed = subprocess.CompletedProcess(
            args=[], returncode=20, stdout=b"", stderr=b"memory"
        )
        with (
            mock.patch.object(Source, "_regular_source", return_value=Path("/x")),
            mock.patch.object(Source.subprocess, "run", return_value=completed),
            mock.patch.dict(os.environ, environment),
            self.assertRaisesRegex(Source.SourceAuditError, "critical exit 20"),
        ):
            Source._scan_task(candidate, Path("/bench"), 2700)

    def test_source_split_is_deterministic_disjoint_and_passes_all_floors(self):
        shadow = list(Source.Inventory.SHADOW_FAMILIES[:23])
        new = [
            *Source.ALL_PRIOR_UNREPRESENTED_FAMILIES,
            *["shadow-unrepresented-{:02d}".format(index) for index in range(7)],
        ]
        families = shadow + new
        records = []
        index = 0
        for family in families:
            for _ in range(20):
                records.append(_record(index, family))
                index += 1
        gate1, cohorts1 = Source.split_supported(records)
        gate2, cohorts2 = Source.split_supported(records)
        self.assertEqual((gate1, cohorts1), (gate2, cohorts2))
        self.assertTrue(gate1["passed"])
        self.assertEqual(
            gate1["availability"]["guided_b_target_tasks"], 300
        )
        self.assertEqual(
            gate1["availability"]["guided_b_max_tasks_per_family"], 12
        )
        self.assertEqual(
            gate1["availability"]["guided_b_maximum_under_family_cap"],
            210,
        )
        self.assertEqual(cohorts1["confirmation_a"]["counts"]["tasks"], 650)
        self.assertEqual(cohorts1["guided_b"]["counts"]["tasks"], 210)
        confirmation = {
            task["problem_sha256"]
            for task in cohorts1["confirmation_a"]["tasks"]
        }
        guided = {
            task["problem_sha256"]
            for task in cohorts1["guided_b"]["tasks"]
        }
        self.assertFalse(confirmation & guided)
        guided_by_family = {
            family: [
                task for task in cohorts1["guided_b"]["tasks"]
                if task["family"] == family
            ]
            for family in families
        }
        self.assertTrue(all(3 < len(tasks) <= Source.MAX_GUIDED_TASKS_PER_FAMILY
                            for tasks in guided_by_family.values()))
        for family in families:
            expected_base = sorted(
                (record for record in records if record["family"] == family),
                key=lambda record: (
                    Source._rank(record, Source.GUIDED_ROLE),
                    record["canonical_path"],
                ),
            )[:3]
            self.assertTrue({
                record["problem_sha256"] for record in expected_base
            } <= {
                task["problem_sha256"] for task in guided_by_family[family]
            })
        base = cohorts1["guided_b"]["selection_stages"]["base"]
        top_up = cohorts1["guided_b"]["selection_stages"]["top_up"]
        self.assertEqual(base["tasks"], 3 * len(families))
        self.assertEqual(top_up["tasks"], 81)

    def test_all_supported_inventory_has_frozen_stratum_counts(self):
        records = _supported_inventory_records()
        gate1, cohorts1 = Source.split_supported(records)
        gate2, cohorts2 = Source.split_supported(records)
        self.assertEqual((gate1, cohorts1), (gate2, cohorts2))
        self.assertTrue(gate1["passed"])
        self.assertGreaterEqual(
            gate1["availability"]["guided_b_maximum_under_family_cap"],
            300,
        )
        confirmation = cohorts1["confirmation_a"]
        guided = cohorts1["guided_b"]
        self.assertEqual(
            (
                confirmation["counts"]["tasks"],
                confirmation["counts"]["families"],
                confirmation["counts"]["shadow_unrepresented_tasks"],
                confirmation["counts"]["shadow_unrepresented_families"],
                confirmation["counts"]["all_prior_unrepresented_tasks"],
                confirmation["counts"]["all_prior_unrepresented_families"],
            ),
            (650, 43, 347, 20, 237, 13),
        )
        self.assertEqual(
            (
                guided["counts"]["tasks"],
                guided["counts"]["families"],
                guided["counts"]["shadow_unrepresented_tasks"],
                guided["counts"]["shadow_unrepresented_families"],
                guided["counts"]["all_prior_unrepresented_tasks"],
                guided["counts"]["all_prior_unrepresented_families"],
            ),
            (300, 42, 183, 19, 128, 12),
        )
        confirmation_ids = {
            (task["directory"], task["problem"])
            for task in confirmation["tasks"]
        }
        guided_ids = {
            (task["directory"], task["problem"])
            for task in guided["tasks"]
        }
        confirmation_hashes = {
            task["problem_sha256"] for task in confirmation["tasks"]
        }
        guided_hashes = {
            task["problem_sha256"] for task in guided["tasks"]
        }
        self.assertFalse(confirmation_ids & guided_ids)
        self.assertFalse(confirmation_hashes & guided_hashes)
        self.assertLessEqual(max(
            sum(task["family"] == family for task in guided["tasks"])
            for family in {task["family"] for task in guided["tasks"]}
        ), Source.MAX_GUIDED_TASKS_PER_FAMILY)

    def test_all_prior_source_floor_fails_closed(self):
        records = _supported_inventory_records()
        for record in records:
            if record["family"] in Source.ALL_PRIOR_UNREPRESENTED_FAMILIES:
                record["normalization"] = {
                    "status": "success",
                    "num_normalized_axioms": 1,
                }
                record["supported"] = False
                record["support_exclusion_reasons"] = ["normalized-axioms"]
        gate, _ = Source.split_supported(records)
        self.assertFalse(gate["passed"])
        self.assertFalse(gate["clauses"][
            "confirmation_all_prior_unrepresented_tasks"
        ]["passed"])
        self.assertFalse(gate["clauses"][
            "guided_all_prior_unrepresented_families"
        ]["passed"])

    def test_source_split_fails_closed_without_support(self):
        records = [_record(index, "airport", supported=index < 10)
                   for index in range(100)]
        gate, cohorts = Source.split_supported(records)
        self.assertFalse(gate["passed"])
        self.assertLess(
            cohorts["confirmation_a"]["counts"]["tasks"],
            Source.CONFIRMATION_TASKS,
        )

    def test_rank_uses_the_exact_frozen_nul_encoding(self):
        record = _record(7, "airport")
        expected = hashlib.sha256(b"\0".join((
            Source.SPLIT_SEED.encode(),
            Source.GUIDED_ROLE.encode(),
            b"airport",
            record["problem_sha256"].encode(),
            record["canonical_path"].encode(),
        ))).hexdigest()
        self.assertEqual(Source._rank(record, Source.GUIDED_ROLE), expected)
        expected_top_up = hashlib.sha256(b"\0".join((
            Source.SPLIT_SEED.encode(),
            Source.GUIDED_TOP_UP_ROLE.encode(),
            b"airport",
            record["problem_sha256"].encode(),
            record["canonical_path"].encode(),
        ))).hexdigest()
        self.assertEqual(
            Source._rank(record, Source.GUIDED_TOP_UP_ROLE), expected_top_up
        )

    def test_execution_environment_rejects_inherited_pythonpath(self):
        with mock.patch.dict(os.environ, {"PYTHONPATH": "/uncontrolled"}):
            with self.assertRaisesRegex(
                Source.SourceAuditError, "environment is not clean"
            ):
                Source.validate_execution_environment()

    def test_execution_environment_requires_unique_array_pycache(self):
        environment = {
            "SLURM_ARRAY_JOB_ID": "123",
            "SLURM_ARRAY_TASK_ID": "7",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": (
                "/tmp/symk-confirmation-source-audit-123-7"
            ),
            "PATH": Source.CONTROLLED_PATH,
        }
        with (
            mock.patch.dict(os.environ, environment, clear=True),
            mock.patch.object(
                Source.sys, "flags", mock.Mock(no_user_site=1)
            ),
            mock.patch.object(Source.sys, "dont_write_bytecode", True),
        ):
            Source.validate_execution_environment()
            os.environ["PYTHONPYCACHEPREFIX"] = "/tmp/shared-cache"
            with self.assertRaisesRegex(
                Source.SourceAuditError, "execution environment changed"
            ):
                Source.validate_execution_environment()

    def test_slurm_contract_is_unthrottled_fat_and_uses_two_candidates(self):
        lines = Launch.SLURM_SCRIPT.read_text(encoding="ascii").splitlines()
        for line in (
            "#SBATCH --partition=fat",
            "#SBATCH --qos=normal",
            "#SBATCH --array=0-819",
            "#SBATCH --cpus-per-task=1",
            "#SBATCH --mem-per-cpu=26G",
            "#SBATCH --time=01:40:00",
            "#SBATCH --export=NONE",
            'export PYTHONDONTWRITEBYTECODE="1"',
            'export PYTHONPYCACHEPREFIX="/tmp/symk-confirmation-source-audit-'
            '${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"',
            'exec "${python_executable}" -B \\',
            "    --num-shards 820 \\",
            "    --task-timeout 2700 \\",
        ):
            self.assertEqual(lines.count(line), 1)
        self.assertNotIn("%", next(
            line for line in lines if line.startswith("#SBATCH --array=")
        ))
        self.assertEqual(Source.TASKS_PER_SHARD, 2)
        command = Launch._submit_command(
            "a" * 64, Launch.OUTPUT_DIR, "b" * 24
        )
        self.assertEqual(command[:3], ["sbatch", "--parsable", "--export=NONE"])
        self.assertEqual(command[-2], "a" * 64)
        self.assertEqual(command[-1], str(Launch.OUTPUT_DIR.resolve()))
        self.assertFalse(any("--nice" in item for item in command))

    def test_launch_requires_clean_committed_jj_tree(self):
        with mock.patch.object(
            Launch.subprocess,
            "check_output",
            side_effect=("M experiments/x.py\n", "a" * 40 + "\n"),
        ):
            with self.assertRaisesRegex(
                Launch.LaunchAuditError, "clean committed working copy"
            ):
                Launch._clean_repository_commit()
        with mock.patch.object(
            Launch.subprocess,
            "check_output",
            side_effect=("", "a" * 40 + "\n"),
        ):
            self.assertEqual(Launch._clean_repository_commit(), "a" * 40)

    def test_atomic_publication_is_no_clobber_and_cleans_failed_temp(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "output" / "shard.json"
            Source.atomic_exclusive_bytes(output, b"first\n", "test shard")
            with self.assertRaisesRegex(Source.SourceAuditError, "overwrite"):
                Source.atomic_exclusive_bytes(output, b"second\n", "test shard")
            self.assertEqual(output.read_bytes(), b"first\n")
            failed = root / "other" / "shard.json"
            with (
                mock.patch.object(Source.os, "link", side_effect=OSError("kill")),
                self.assertRaisesRegex(Source.SourceAuditError, "publish"),
            ):
                Source.atomic_exclusive_bytes(failed, b"partial\n", "failed shard")
            self.assertFalse(failed.exists())
            temp_root = root / ".other.publication-tmp"
            self.assertEqual(list(temp_root.iterdir()), [])

    def test_submission_journal_canonicalizes_realistic_array_rows(self):
        token = "b" * 24
        name, comment = Launch._submission_identity(token)
        output = "\n".join((
            "123|{}|{}".format(name, comment),
            "123_0|{}|{}".format(name, comment),
            "123_1|{}|{}".format(name, comment),
            "123_2|{}|{}".format(name, comment),
        )) + "\n"
        intent = {
            "submission_token": token,
            "recorded_utc": "2026-09-01T10:00:00+00:00",
        }
        with (
            mock.patch.object(Launch, "ARRAY_TASKS", 3),
            mock.patch.object(
                Launch.subprocess, "check_output", return_value=output
            ) as query,
        ):
            self.assertEqual(Launch._journal_job_ids(intent), ["123"])
        self.assertEqual(query.call_args.args[0][-1], Launch.JOURNAL_FIELDS)
        self.assertIn("JobName%128", Launch.JOURNAL_FIELDS)
        self.assertIn("Comment%128", Launch.JOURNAL_FIELDS)
        with (
            mock.patch.object(Launch, "ARRAY_TASKS", 3),
            mock.patch.object(
                Launch.subprocess,
                "check_output",
                return_value=output.replace(
                    "123_2|{}|{}\n".format(name, comment), ""
                ),
            ),
            self.assertRaisesRegex(Launch.LaunchAuditError, "incomplete array"),
        ):
            Launch._journal_job_ids(intent)

    def test_scheduler_rows_support_sparse_recovery_indices(self):
        output = (
            "77_7|NODE_FAIL|0:9|00:01:00|fat\n"
            "77_2|COMPLETED|0:0|00:02:00|fat\n"
        )
        with mock.patch.object(
            Launch.subprocess, "check_output", return_value=output
        ):
            rows = Launch._scheduler_rows("77", {2, 7})
        self.assertEqual([row["array_task"] for row in rows], [2, 7])

    def test_recovery_selects_only_frozen_infrastructure_failures(self):
        rows = [
            {"array_task": 0, "state": "COMPLETED", "exit_code": "0:0"},
            {"array_task": 1, "state": "NODE_FAIL", "exit_code": "0:9"},
        ]
        with mock.patch.object(Source, "SHARD_COUNT", 2):
            self.assertEqual(Recovery._classify_rows(rows), ([0], [1]))
            rows[1] = {
                "array_task": 1, "state": "FAILED", "exit_code": "75:0"
            }
            with self.assertRaisesRegex(Recovery.RecoveryError, "forbidden"):
                Recovery._classify_rows(rows)

    def test_recovery_command_matches_resources_without_throttle_or_nice(self):
        plan = {
            "recoverable_shards": [2, 7],
            "source_inventory_sha256": "a" * 64,
        }
        command = Recovery._submit_command(plan, "b" * 24)
        name, comment = Recovery._submission_identity("b" * 24)
        self.assertEqual(command, [
            "sbatch", "--parsable", "--export=NONE", "--array=2,7",
            "--job-name={}".format(name), "--comment={}".format(comment),
            "--account={}".format(Launch.ACCOUNT), "--partition=fat",
            "--qos=normal", "--cpus-per-task=1", "--mem-per-cpu=26G",
            "--time=01:40:00",
            "--output={}".format(
                (Recovery.OUTPUT_DIR / "slurm-%A_%a.out").resolve()
            ),
            str(Launch.SLURM_SCRIPT), "a" * 64,
            str(Recovery.OUTPUT_DIR.resolve()),
        ])
        self.assertFalse(any("%" in item for item in command if "--array=" in item))
        self.assertFalse(any("nice" in item for item in command))

    def test_recovery_launch_noop_creates_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {
                "RECOVERY_ROOT": root / "recovery",
                "DATA_ROOT": root / "data",
                "UNION_DIR": root / "union",
            }
            with (
                mock.patch.multiple(Recovery, **paths),
                mock.patch.object(
                    Launch, "EXECUTION_RECEIPT", root / "main-execution.json"
                ),
                mock.patch.object(
                    Recovery, "_plan", return_value={"recoverable_shards": []}
                ),
                mock.patch.object(
                    Recovery.subprocess, "check_output"
                ) as submit,
            ):
                Recovery.launch()
            submit.assert_not_called()
            self.assertFalse(any(path.exists() for path in paths.values()))

    def test_recovery_journal_canonicalizes_sparse_array_rows(self):
        token = "c" * 24
        name, comment = Recovery._submission_identity(token)
        output = "\n".join((
            "456|{}|{}".format(name, comment),
            "456_2|{}|{}".format(name, comment),
            "456_7|{}|{}".format(name, comment),
        )) + "\n"
        intent = {
            "submission_token": token,
            "recorded_utc": "2026-09-01T10:00:00+00:00",
            "recoverable_shards": [2, 7],
        }
        with mock.patch.object(
            Recovery.subprocess, "check_output", return_value=output
        ) as query:
            self.assertEqual(Recovery._journal_job_ids(intent), ["456"])
        self.assertEqual(query.call_args.args[0][-1], Launch.JOURNAL_FIELDS)
        with (
            mock.patch.object(
                Recovery.subprocess,
                "check_output",
                return_value=output.replace(
                    "456_7|{}|{}\n".format(name, comment), ""
                ),
            ),
            self.assertRaisesRegex(Recovery.RecoveryError, "incomplete array"),
        ):
            Recovery._journal_job_ids(intent)

    def test_recover_launch_reconstructs_without_resubmission(self):
        intent = {"submission_token": "d" * 24}
        raw = Source.canonical_json(intent)
        with tempfile.TemporaryDirectory() as tmp:
            receipt = Path(tmp) / "receipt.json"
            with (
                mock.patch.object(Recovery, "LAUNCH_RECEIPT", receipt),
                mock.patch.object(
                    Recovery, "_load_intent_only",
                    return_value=(raw, intent, {}),
                ),
                mock.patch.object(
                    Recovery, "_journal_job_ids", return_value=["789"]
                ),
                mock.patch.object(
                    Recovery, "_write_launch_receipt", return_value="e" * 64
                ) as write,
                mock.patch.object(
                    Recovery.subprocess, "check_output"
                ) as submit,
            ):
                Recovery.recover_launch()
            write.assert_called_once_with(raw, intent, "789")
            submit.assert_not_called()

    def test_union_prefers_recovery_for_noncompleted_valid_original_shard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = root / "original"
            recovered = root / "recovered"
            union_dir = root / "union"
            original.mkdir()
            recovered.mkdir()
            inventory = original / "source-inventory-v1.json"
            inventory.write_bytes(b"inventory\n")
            (original / "slurm-111_0.out").write_bytes(b"ok\n")
            (original / "slurm-111_1.out").write_bytes(b"node failed\n")
            Source.shard_path(original, 0).write_bytes(b"original-zero\n")
            # A valid-looking shard from a noncompleted task is bound but never
            # selected; the sealed recovery is authoritative for this index.
            Source.shard_path(original, 1).write_bytes(b"stale-one\n")
            Source.shard_path(recovered, 1).write_bytes(b"recovered-one\n")
            rows = [
                {"array_task": 0, "state": "COMPLETED", "exit_code": "0:0"},
                {"array_task": 1, "state": "NODE_FAIL", "exit_code": "0:9"},
            ]
            launch = {"job_id": "111"}
            with (
                mock.patch.object(Source, "SHARD_COUNT", 2),
                mock.patch.object(Launch, "OUTPUT_DIR", original),
                mock.patch.object(Launch, "SOURCE_INVENTORY", inventory),
                mock.patch.object(Recovery, "OUTPUT_DIR", recovered),
                mock.patch.object(Recovery, "UNION_DIR", union_dir),
            ):
                successful, interrupted = Recovery._classify_rows(rows)
                tree, missing, existing = Recovery._original_output_tree(
                    launch, rows, successful, interrupted
                )
                plan = {
                    "source_launch_receipt_sha256": "a" * 64,
                    "recoverable_shards": [1],
                    "missing_shard_indices": missing,
                    "existing_interrupted_shard_indices": existing,
                    "original_scheduler_rows": rows,
                    "original_output_tree": tree,
                }
                with mock.patch.object(
                    Recovery,
                    "load_execution",
                    return_value=("e" * 64, {"sealed": True}, plan),
                ):
                    context = Recovery.prepare_union("a" * 64, launch, rows)
                    self.assertEqual(existing, [1])
                    self.assertEqual(
                        Source.shard_path(union_dir, 1).read_bytes(),
                        b"recovered-one\n",
                    )
                    self.assertEqual(context["sources"][1]["origin"], "recovery")
                    Source.shard_path(recovered, 1).write_bytes(b"tampered\n")
                    with self.assertRaisesRegex(
                        Recovery.RecoveryError, "union source bytes changed"
                    ):
                        Recovery.verify_union(context, launch)
                    Source.shard_path(recovered, 1).write_bytes(
                        b"recovered-one\n"
                    )
                    Source.shard_path(union_dir, 1).write_bytes(b"tampered\n")
                    with self.assertRaisesRegex(
                        Recovery.RecoveryError, "union tree changed"
                    ):
                        Recovery.verify_union(context, launch)
                    Source.shard_path(union_dir, 1).write_bytes(
                        b"recovered-one\n"
                    )
                    Source.shard_path(original, 0).write_bytes(b"tampered\n")
                    with self.assertRaisesRegex(
                        Recovery.RecoveryError, "original output tree changed"
                    ):
                        Recovery.verify_union(context, launch)

    def test_seal_rejects_union_change_before_freezing_attestation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            candidate = root / "candidate.json"
            attestation = root / "attestation.json"
            execution = root / "execution.json"
            value = {
                "schema": Source.SCHEMA,
                "counts": {
                    "candidates": Source.CANDIDATE_COUNT,
                    "translation_attempts": Source.CANDIDATE_COUNT,
                },
                "prelaunch_gate": {"passed": True},
                "confirmation_prelaunch_authorized": True,
                "cohorts": {},
                "records_sha256": "e" * 64,
            }

            def assemble(argv):
                output = Path(argv[argv.index("--output") + 1])
                output.write_bytes(Source.canonical_json(value))

            launch_receipt = {
                "job_id": "123",
                "source_inventory_sha256": "a" * 64,
                "code_manifest_sha256": "b" * 64,
                "execution_environment": {"submission_export": "NONE"},
            }
            rows = [
                {"array_task": index, "state": "COMPLETED", "exit_code": "0:0"}
                for index in range(Launch.ARRAY_TASKS)
            ]
            union = {
                "original_output_tree": {"sha256": "d" * 64},
                "recovery": None,
                "sources": [],
                "union_tree": {"sha256": "f" * 64},
            }
            with (
                mock.patch.object(Launch, "CANDIDATE", candidate),
                mock.patch.object(Launch, "ATTESTATION", attestation),
                mock.patch.object(Launch, "EXECUTION_RECEIPT", execution),
                mock.patch.object(
                    Launch, "status", return_value=("c" * 64, launch_receipt, rows)
                ),
                mock.patch.object(
                    Recovery, "prepare_union", return_value=union
                ),
                mock.patch.object(
                    Recovery, "verify_union",
                    side_effect=Recovery.RecoveryError("union tree changed"),
                ),
                mock.patch.object(Launch.Source, "main", side_effect=assemble),
            ):
                with self.assertRaisesRegex(Recovery.RecoveryError, "union tree"):
                    Launch.seal()
            self.assertFalse(attestation.exists())
            self.assertFalse(execution.exists())


if __name__ == "__main__":
    unittest.main()
