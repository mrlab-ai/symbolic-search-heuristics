"""Synthetic and adversarial tests for the fresh within-family adapter."""

import copy
import json
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
    freeze = {
        "schema": "pdb-terminal-incidence-within-family-cohort/v1/freeze",
        "scope": "fresh-instances-within-previously-studied-families",
        "targets": {"a": 650}, "families": [f"f{i}" for i in range(27)],
        "tasks": {"a": [{"family": f"f{i % 27}"} for i in range(650)]},
        "source_status_counts": {"supported": 650, "unsupported": 0},
        "analysis": {"minimum_eligible_tasks": 300, "minimum_comparison_tasks": 300,
                      "minimum_families": 25, "minimum_target_strict_pairs": 600,
                      "minimum_concordance": [13, 20], "minimum_advantage": [1, 50],
                      "bootstrap_replicates": 100000, "bootstrap_seed": 20260901,
                      "horizon": 16, "unseen_family_gate": False},
        "code_commit": "c" * 40, "code_sha256": {"code.py": "d" * 64},
    }
    launch = {"experiment": "/tmp/within-family", "jobs": []}
    poll = {"launch_sha256": E._sha(canonical(launch)), "queries": {"accounting": {
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
        launch = {"experiment": "/tmp/within-family", "jobs": []}
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
        poll = {"launch_sha256": E._sha(canonical(launch)),
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


if __name__ == "__main__":
    unittest.main()
