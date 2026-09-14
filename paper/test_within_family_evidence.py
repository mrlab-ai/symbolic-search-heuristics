"""Synthetic and adversarial tests for the fresh within-family adapter."""

import copy
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import terminal_incidence_evidence as E
import test_render_terminal_incidence_results as Fixtures
import test_terminal_incidence_evidence as OldTests
import within_family_evidence as W


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def fixture():
    old = Fixtures.fixture(a_pass=False, direct_pass=None, b_pass=None)
    analysis = OldTests.native_a(old["confirmation_a"])
    primary_gate = analysis["gates"]["primary"]
    primary_gate["pass"] = False
    analysis.update({
        "schema": "pdb-terminal-incidence-within-family-a-analysis/v1",
        "scope": "fresh-instances-within-previously-studied-families",
        "gates": {"pass": False, "primary": primary_gate,
                  "decision": "FAIL", "unseen_family_gate": False},
        "matrix": {"tasks": 650, "cells": 2600, "configs": 4, "families": 27},
        "freeze_sha256": "f" * 64,
        "input": {"properties_sha256": "e" * 64, "code_commit": "c" * 40,
                   "code_sha256": {"code.py": "d" * 64}},
        "statistical_selector_gate_passed": False,
        "eligible_tasks": 320, "eligible_families": 27,
    })
    task_rows = [{"family": f"f{i % 27}", "level": i % 5} for i in range(650)]
    level_allocations = {"a": {f"f{i}": {str(level): 0 for level in range(5)} for i in range(27)}}
    for row in task_rows:
        level_allocations["a"][row["family"]][str(row["level"])] += 1
    freeze = {
        "schema": "pdb-terminal-incidence-within-family-cohort/v1/freeze",
        "scope": "fresh-instances-within-previously-studied-families",
        "targets": {"a": 650}, "families": [f"f{i}" for i in range(27)],
        "tasks": {"a": task_rows},
        "level_allocation_rule": "balanced-supported-levels-ascending/v1",
        "level_allocations": level_allocations,
        "source_status_counts": {"supported": 650, "unsupported": 0},
        "analysis": {"minimum_eligible_tasks": 300, "minimum_comparison_tasks": 300,
                      "minimum_families": 25, "minimum_target_strict_pairs": 600,
                      "minimum_concordance": [13, 20], "minimum_advantage": [1, 50],
                      "bootstrap_replicates": 100000, "bootstrap_seed": 20260901,
                      "horizon": 16, "unseen_family_gate": False},
        "code_commit": "c" * 40, "code_sha256": {"code.py": "d" * 64},
    }
    launch = {"schema": "pdb-within-family-launch/v1", "experiment": "/tmp/within-family", "jobs": []}
    poll = {"schema": "pdb-within-family-poll/v1", "launch_sha256": E._sha(canonical(launch)), "queries": {"accounting": {
        "returncode": 0, "stdout": ""}}}
    freeze["performance_observed"] = False
    freeze_raw = canonical(freeze)
    analysis["freeze_sha256"] = E._sha(freeze_raw)
    result = canonical(analysis)
    receipt = canonical({"schema": "pdb-terminal-incidence-within-family-a-analysis/v1/double-execution",
                         "byte_identical": True, "analysis_sha256": E._sha(result),
                         "repeat_sha256": E._sha(result), "freeze_sha256": E._sha(freeze_raw),
                         "properties_sha256": "e" * 64,
                         "scheduler_audit_required_before_selector_launch": True})
    artifacts = {"freeze": freeze_raw, "analysis": result, "repeat": result,
                 "receipt": receipt, "launch": canonical(launch), "poll": canonical(poll)}
    seal = {"schema": "pdb-terminal-incidence-within-family-a-seal/v1",
            "scope": freeze["scope"], "decision": "FAIL",
            "selector_experiments_authorized": False, "matrix": analysis["matrix"],
            "code_commit": freeze["code_commit"],
            "evidence": {key: {"sha256": E._sha(value)} for key, value in artifacts.items()}}
    seal["evidence"]["properties"] = {"sha256": "e" * 64}
    artifacts["seal"] = canonical(seal)
    pins = {key: E._sha(value) for key, value in artifacts.items()}
    return artifacts, pins


def recovered_fixture():
    artifacts, _pins = fixture()
    steps = (("01-build", 1), ("02-start", 867), ("03-parse", 1),
             ("04-fetch", 1), ("05-report", 1), ("06-analyze", 1))
    launch = {"schema": "pdb-within-family-launch/v1",
              "experiment": str(W.RECOVERY_EXPERIMENT), "jobs": []}
    accounting = []
    grid = Path(str(W.RECOVERY_EXPERIMENT) + "-grid-steps")
    for index, (step, elements) in enumerate(steps, 1):
        job_id = str(1000 + index)
        name = W.RECOVERY_EXPERIMENT.name + "-" + step
        launch["jobs"].append({"job_id": job_id, "job_file": str(grid / name),
                               "array_elements": elements,
                               "script": "#SBATCH --time=01:45:00\n#SBATCH --job-name=" + name + "\n"})
        state, exit_code = (("FAILED", "1:0") if step == "06-analyze"
                            else ("COMPLETED", "0:0"))
        accounting.extend(
            f"{job_id}_{element}|{name}|{state}|{exit_code}|fat|naiss2025-5-561-cpu|"
            "normal|9|3Gc|01:45:00|synthetic|1"
            for element in range(1, elements + 1))
    poll = {"schema": "pdb-within-family-poll/v1",
            "launch_sha256": E._sha(canonical(launch)),
            "queries": {"accounting": {"returncode": 0, "stdout": "\n".join(accounting)}},
            "pipeline_logs": {"slurm.err": {"tail": W.SERIALIZATION_ERROR}}}
    artifacts["launch"] = canonical(launch)
    artifacts["poll"] = canonical(poll)
    artifacts["wrapper"] = b"committed recovery wrapper"
    artifacts["stdout"] = b"local recovery summary\n"
    artifacts["stderr"] = b""
    invocation = {
        "schema": "pdb-terminal-incidence-within-family-a-serialization-recovery/v1/invocation",
        "command": [str(W.RECOVERY_PYTHON), "-X", "int_max_str_digits=100000", "-B",
                    str(W.RECOVERY_ANALYSIS), "--properties", str(W.RECOVERY_PROPERTIES),
                    "--output", str(W.RECOVERY_OUTPUT)],
        "cwd": str(W.EXPERIMENTS.resolve()), "environment": W.RECOVERY_ENVIRONMENT,
        "returncode": 0, "timed_out": False, "integer_max_str_digits": 100000,
        "interpreter": {"path": str(W.RECOVERY_INTERPRETER),
                        "sha256": W.RECOVERY_PYTHON_SHA256},
        "started_utc": "2026-09-14T23:00:00+00:00",
        "ended_utc": "2026-09-14T23:03:00+00:00",
        "stdout_sha256": E._sha(artifacts["stdout"]),
        "stderr_sha256": E._sha(artifacts["stderr"]),
    }
    artifacts["invocation"] = canonical(invocation)
    output = W.RECOVERY_OUTPUT
    evidence_paths = {
        "freeze": (W.REPO / W.PATHS["freeze"]).resolve(),
        "launch": (W.REPO / W.PATHS["launch"]).resolve(),
        "poll": output / "poll-20260914T211529Z.json",
        "properties": W.RECOVERY_PROPERTIES,
        "analysis": output / "analysis.json",
        "repeat": output / "analysis-repeat.json",
        "analysis_receipt": output / "analysis-receipt.json",
        "stdout": output / "serialization-recovery-venv.stdout",
        "stderr": output / "serialization-recovery-venv.stderr",
    }
    artifact_roles = {"freeze": "freeze", "launch": "launch", "poll": "poll",
                      "analysis": "analysis", "repeat": "repeat",
                      "analysis_receipt": "receipt", "stdout": "stdout", "stderr": "stderr"}
    recovery = {
        "schema": "pdb-terminal-incidence-within-family-a-serialization-recovery/v1",
        "integer_max_str_digits": 100000, "scheduler_queries_made_by_recovery": 0,
        "scientific_runs_repeated": 0,
        "original_analysis_failure": {"step": "06-analyze", "job_id": "1006",
                                      "accounting_id": "1006_1", "state": "FAILED",
                                      "exit": "1:0", "error": W.SERIALIZATION_ERROR},
        "immutable_code": {"frozen_commit": "c" * 40,
                           "frozen_code_sha256": {"code.py": "d" * 64},
                           "recovery_wrapper": {"path": str(W.RECOVERY_WRAPPER),
                                                "sha256": E._sha(artifacts["wrapper"]),
                                                "committed_revision": "b" * 40}},
        "invocation": {"path": str(W.RECOVERY_INVOCATION),
                       "sha256": E._sha(artifacts["invocation"])},
        "evidence": {role: {"path": str(path),
                            "sha256": ("e" * 64 if role == "properties"
                                       else E._sha(artifacts[artifact_roles[role]]))}
                     for role, path in evidence_paths.items()},
    }
    artifacts["recovery"] = canonical(recovery)
    analysis = json.loads(artifacts["analysis"])
    seal_roles = {"freeze": "freeze", "launch": "launch", "poll": "poll",
                  "analysis": "analysis", "repeat": "repeat", "receipt": "receipt",
                  "recovery": "recovery"}
    seal_paths = {"freeze": evidence_paths["freeze"], "launch": evidence_paths["launch"],
                  "poll": evidence_paths["poll"], "analysis": evidence_paths["analysis"],
                  "repeat": evidence_paths["repeat"],
                  "receipt": evidence_paths["analysis_receipt"],
                  "recovery": output / "serialization-recovery.json"}
    seal = {"schema": "pdb-terminal-incidence-within-family-a-seal/v2-serialization-recovery",
            "scope": analysis["scope"], "decision": "FAIL",
            "selector_experiments_authorized": False,
            "scheduler_queries_made_by_seal": 0,
            "original_scheduler_analysis": recovery["original_analysis_failure"],
            "matrix": analysis["matrix"], "code_commit": "c" * 40,
            "evidence": {role: {"path": str(seal_paths[role]),
                                "sha256": E._sha(artifacts[artifact_role])}
                         for role, artifact_role in seal_roles.items()}}
    seal["evidence"]["properties"] = {"path": str(W.RECOVERY_PROPERTIES), "sha256": "e" * 64}
    artifacts["seal"] = canonical(seal)
    pins = {role: E._sha(artifacts[role]) for role in W.PATHS}
    pins["recovery"] = E._sha(artifacts["recovery"])
    return artifacts, pins, launch, poll, recovery, invocation


class WithinFamilyEvidenceTests(unittest.TestCase):
    def test_defaults_refuse_unset_production(self):
        with self.assertRaises(W.EvidenceError):
            W.load_evidence()

    def test_projects_a_without_all_prior_or_selector_fields(self):
        artifacts, pins = fixture()
        with mock.patch.object(W, "_read", return_value=artifacts), \
                mock.patch.object(W, "_validate_pipeline"), \
                mock.patch.object(W, "_code_closure", return_value="c" * 40):
            result = W.load_evidence(results_revision="a" * 40, artifact_pins=pins)
        self.assertEqual(result["design"], "within-family-v1")
        self.assertFalse(result["a_pass"])
        self.assertEqual(result["source"]["tasks"], 650)
        self.assertEqual(result["source"]["families"], [f"f{i}" for i in range(27)])
        self.assertEqual(result["source"]["candidate_status_counts"], {"supported": 650, "unsupported": 0})
        self.assertNotIn("all_prior", result["confirmation_a"])
        self.assertNotIn("selector", result)

    def test_rejects_nonidentical_analysis(self):
        artifacts, pins = fixture()
        artifacts = copy.copy(artifacts)
        artifacts["repeat"] = artifacts["repeat"] + b" "
        pins = {key: E._sha(value) for key, value in artifacts.items()}
        with mock.patch.object(W, "_read", return_value=artifacts):
            with self.assertRaisesRegex(W.EvidenceError, "byte-identical"):
                W.load_evidence(results_revision="a" * 40, artifact_pins=pins)

    def test_pipeline_validation_rejects_incomplete_and_failed_accounting(self):
        launch = {"schema": "pdb-within-family-launch/v1", "experiment": "/tmp/within-family", "jobs": []}
        accounting = []
        for index, (step, elements) in enumerate((
                ("01-build", 1), ("02-start", 867), ("03-parse", 1),
                ("04-fetch", 1), ("05-report", 1), ("06-analyze", 1)), 1):
            name = f"synthetic-{index:02d}-{step}"
            launch["jobs"].append({"job_id": str(index), "job_file": name,
                                   "array_elements": elements,
                                   "script": "#SBATCH --time=01:45:00\n#SBATCH --job-name=" + name + "\n"})
            accounting.extend(
                f"{index}_{element}|{name}|COMPLETED|0:0|fat|naiss2025-5-561-cpu|normal|9|3Gc|01:45:00|synthetic|1"
                for element in range(1, elements + 1))
        poll = {"schema": "pdb-within-family-poll/v1", "launch_sha256": E._sha(canonical(launch)),
                "queries": {"accounting": {"returncode": 0, "stdout": "\n".join(accounting)}}}
        W._validate_pipeline(launch, poll)
        failed = copy.deepcopy(poll)
        failed["queries"]["accounting"]["stdout"] = "\n".join(accounting).replace("COMPLETED", "FAILED", 1)
        with self.assertRaisesRegex(W.EvidenceError, "successfully"):
            W._validate_pipeline(launch, failed)
        incomplete = copy.deepcopy(launch)
        incomplete["jobs"] = incomplete["jobs"][:-1]
        with self.assertRaisesRegex(W.EvidenceError, "pipeline shape"):
            W._validate_pipeline(incomplete, poll)

    def test_code_closure_digest_is_checked_against_committed_snapshot(self):
        freeze = {"code_commit": "c" * 40, "code_sha256": {"code.py": "d" * 64}}
        with mock.patch.object(W, "_snapshot_reader", return_value=lambda _revision, paths: {paths[0]: b"wrong"}):
            with self.assertRaisesRegex(W.EvidenceError, "scientific code differs"):
                W._code_closure(freeze, "a" * 40)

    def test_level_allocation_must_match_selected_tasks(self):
        artifacts, _pins = fixture()
        freeze = json.loads(artifacts["freeze"])
        freeze["level_allocations"]["a"]["f0"]["0"] += 1
        with self.assertRaisesRegex(W.EvidenceError, "allocations disagree"):
            W._validate_level_allocations(freeze)

    def test_full_recovered_load_with_872_accounting_rows(self):
        artifacts, pins, _launch, poll, _receipt, _invocation = recovered_fixture()
        self.assertEqual(len(poll["queries"]["accounting"]["stdout"].splitlines()), 872)
        mapping = {path: artifacts[role] for role, path in W.PATHS.items() if path is not None}
        for role, path in (("poll", W.RECOVERY_OUTPUT / "poll-20260914T211529Z.json"),
                           ("recovery", W.RECOVERY_OUTPUT / "serialization-recovery.json"),
                           ("invocation", W.RECOVERY_INVOCATION),
                           ("stdout", W.RECOVERY_OUTPUT / "serialization-recovery-venv.stdout"),
                           ("stderr", W.RECOVERY_OUTPUT / "serialization-recovery-venv.stderr"),
                           ("wrapper", W.RECOVERY_WRAPPER)):
            mapping[path.resolve().relative_to(W.REPO).as_posix()] = artifacts[role]

        def reader(_revision, paths):
            return {path: mapping[path] for path in paths}

        with mock.patch.object(W, "_snapshot_reader", return_value=reader), \
                mock.patch.object(W, "_code_closure", return_value="c" * 40):
            loaded = W.load_evidence(results_revision="a" * 40, artifact_pins=pins)
        self.assertEqual(loaded["design"], "within-family-v1")
        self.assertFalse(loaded["a_pass"])

    def test_recovery_rejects_rehashed_invocation_semantics(self):
        artifacts, _pins, launch, poll, receipt, invocation = recovered_fixture()
        freeze = json.loads(artifacts["freeze"])
        analysis = json.loads(artifacts["analysis"])
        for field in ("returncode", "command"):
            with self.subTest(field=field):
                changed_invocation = copy.deepcopy(invocation)
                if field == "returncode":
                    changed_invocation[field] = 1
                else:
                    changed_invocation[field][4] = str(W.EXPERIMENTS / "other_analysis.py")
                changed_artifacts = dict(artifacts, invocation=canonical(changed_invocation))
                changed_receipt = copy.deepcopy(receipt)
                changed_receipt["invocation"]["sha256"] = E._sha(changed_artifacts["invocation"])
                with self.assertRaisesRegex(W.EvidenceError, "invocation changed"):
                    W._validate_recovery(changed_receipt, changed_artifacts, freeze,
                                         analysis, launch, poll)

    def test_recovered_pipeline_rejects_poll_failure_state_mutation(self):
        _artifacts, _pins, launch, poll, _receipt, _invocation = recovered_fixture()
        completed_analysis = copy.deepcopy(poll)
        completed_analysis["queries"]["accounting"]["stdout"] = (
            completed_analysis["queries"]["accounting"]["stdout"].replace(
                "FAILED|1:0", "COMPLETED|0:0", 1))
        with self.assertRaisesRegex(W.EvidenceError, "analysis failure changed"):
            W._validate_pipeline(launch, completed_analysis, recovered=True)
        failed_scientific = copy.deepcopy(poll)
        failed_scientific["queries"]["accounting"]["stdout"] = (
            failed_scientific["queries"]["accounting"]["stdout"].replace(
                "COMPLETED|0:0", "FAILED|1:0", 1))
        with self.assertRaisesRegex(W.EvidenceError, "pre-analysis pipeline failed"):
            W._validate_pipeline(launch, failed_scientific, recovered=True)

    def test_paper_decoder_uses_finite_large_integer_limit(self):
        self.assertEqual(sys.get_int_max_str_digits(), 100000)
        raw = canonical({"large": int("7" * 5000)})
        self.assertEqual(json.loads(raw)["large"], int("7" * 5000))


if __name__ == "__main__":
    unittest.main()
