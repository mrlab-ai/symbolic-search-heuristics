#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pdb_terminal_metric_choice_analyzer as Analyzer
import pdb_terminal_metric_choice_protocol as P
from test_pdb_terminal_metric_choice_execution import FREEZE_SHA, fake_records
from test_pdb_terminal_metric_choice_protocol import fake_freeze, fake_standalone


class AnalyzerTest(unittest.TestCase):
    def analyze(self, records):
        freeze = fake_freeze()
        return Analyzer.analyze(
            records, freeze, FREEZE_SHA,
            fake_standalone(freeze["base_confirmation_b"]),
            bootstrap_replicates=500,
        )

    def test_primary_and_differing_subset_gate_pass(self):
        result = self.analyze(fake_records(differing_tasks=100))
        self.assertTrue(result["pass"])
        self.assertTrue(result["primary_i_vs_mj"]["pass"])
        subset = result["differing_winner_subset_i_vs_mj"]
        self.assertEqual(subset["tasks"], 100)
        self.assertEqual(subset["families"], 10)
        self.assertTrue(all(subset["support_clauses"].values()))
        self.assertTrue(all(subset["clauses"].values()))

    def test_macro_threshold_is_exactly_gating(self):
        records = fake_records()
        for row in records:
            if row["algorithm"] == P.INCIDENCE_MODE:
                row["total_time"] = 290.0
        result = self.analyze(records)
        self.assertFalse(result["pass"])
        self.assertFalse(result["primary_i_vs_mj"]["clauses"][
            "equal_family_normalized_par2_at_least_0_02"
        ])

    def test_differing_subset_support_is_gating(self):
        result = self.analyze(fake_records(differing_tasks=40))
        self.assertFalse(result["pass"])
        subset = result["differing_winner_subset_i_vs_mj"]
        self.assertFalse(subset["support_clauses"]["tasks_at_least_50"])
        self.assertFalse(subset["support_clauses"]["families_at_least_10"])

    def test_incidence_coverage_must_be_nonlower(self):
        records = fake_records()
        first = next(
            row for row in records if row["algorithm"] == P.INCIDENCE_MODE
        )
        first["coverage"] = 0
        result = self.analyze(records)
        self.assertFalse(result["primary_i_vs_mj"]["clauses"][
            "coverage_nonlower"
        ])
        self.assertFalse(result["pass"])

    def test_matched_contrast_is_secondary_only(self):
        records = fake_records()
        for row in records:
            if row["algorithm"] == P.MATCHED_MODE:
                row["total_time"] = 50.0
        result = self.analyze(records)
        self.assertTrue(result["pass"])
        self.assertFalse(result["secondary_i_vs_matched"]["pass"])
        self.assertFalse(result["secondary_i_vs_matched"][
            "affects_primary_gate"
        ])

    def test_downstream_provenance_is_v5_only_and_closed(self):
        freeze = fake_freeze()
        properties = Analyzer.Runner.build_manifest_properties(
            freeze, FREEZE_SHA
        )
        keys = set(properties)
        self.assertFalse(any("v4" in key.lower() for key in keys))
        self.assertFalse(any(
            "v4" in key.lower() for key in Analyzer.ANALYSIS_PROVENANCE_FIELDS
        ))
        required = {
            "campaign_freeze_repository_revision",
            "base_b_freeze_repository_revision",
            "base_b_experiment_source_manifest_sha256",
            "planner_manifest_sha256",
            "standalone_k32_evidence_sha256",
            "standalone_k32_records_sha256",
            "standalone_b_parse_receipt_sha256",
            "standalone_b_fetch_receipt_sha256",
            "standalone_b_properties_sha256",
            "source_audit_v5_attestation_sha256",
            "source_audit_v5_launch_intent_sha256",
            "source_audit_v5_launch_receipt_sha256",
            "source_audit_v5_execution_receipt_sha256",
            "source_audit_v5_code_manifest_sha256",
            "source_audit_v5_repository_commit_id",
            "source_audit_v5_output_tree_sha256",
            "source_audit_v5_slurm_script_sha256",
            "source_audit_v5_translator_source_sha256",
            "source_audit_v5_tracked_manifest_sha256",
            "source_audit_v5_attestation_path",
            "source_audit_v5_launch_intent_path",
            "source_audit_v5_launch_receipt_path",
            "source_audit_v5_execution_receipt_path",
            "source_audit_v5_cohort_manifest_sha256",
            "source_audit_v5_confirmation_a_cohort_manifest_sha256",
            "source_audit_v5_attestation_records_sha256",
            "source_audit_v5_job_id",
            "source_audit_v5_provenance_sha256",
        }
        self.assertTrue(required.issubset(keys))
        provenance = Analyzer._analysis_provenance(freeze, FREEZE_SHA)
        self.assertEqual(
            set(provenance), set(Analyzer.ANALYSIS_PROVENANCE_FIELDS)
        )
        self.assertEqual(
            provenance,
            {key: properties[key] for key in Analyzer.ANALYSIS_PROVENANCE_FIELDS},
        )
        self.assertTrue(required.issubset(provenance))

    def test_double_execution_publishes_identical_outputs_and_pin(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        inputs = (
            fake_records(), freeze, FREEZE_SHA, standalone, "a" * 64,
            "b" * 64, "experiments/artifacts/execution-receipt-v1.json",
            "c" * 64,
        )
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output, repeat, receipt, pin = (
                root / "analysis.json", root / "analysis-repeat.json",
                root / "receipt.json", root / "receipt.sha256",
            )
            with mock.patch.object(
                Analyzer, "_load_inputs",
                side_effect=[copy.deepcopy(inputs), copy.deepcopy(inputs)],
            ):
                published = Analyzer.run_twice(
                    output, repeat, receipt, pin, bootstrap_replicates=500
                )
            self.assertEqual(output.read_bytes(), repeat.read_bytes())
            receipt_sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
            self.assertEqual(pin.read_text(), receipt_sha + "\n")
            self.assertEqual(published["analysis_receipt_sha256"], receipt_sha)
            self.assertTrue(published["outputs_byte_identical"])
            self.assertEqual(published["execution_receipt_sha256"], "c" * 64)
            self.assertEqual(
                published["execution_receipt_path"],
                "experiments/artifacts/execution-receipt-v1.json",
            )
            analysis_value = json.loads(output.read_text())
            receipt_value = json.loads(receipt.read_text())
            analysis_provenance = analysis_value["input"]["frozen_provenance"]
            receipt_provenance = receipt_value["frozen_provenance"]
            self.assertEqual(analysis_provenance, receipt_provenance)
            self.assertTrue(set(
                Analyzer.Runner.V5_PROVENANCE_PROPERTY_FIELDS
            ).issubset(analysis_provenance))

    def test_second_pass_input_drift_publishes_nothing(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        base = [
            [], freeze, FREEZE_SHA, standalone, "a" * 64, "b" * 64,
            "experiments/artifacts/execution-receipt-v1.json", "c" * 64,
        ]
        mutations = {
            "freeze": lambda value: value[1].update({"nonce": 1}),
            "standalone": lambda value: value[3].update({"nonce": 1}),
            "properties": lambda value: value.__setitem__(4, "0" * 64),
            "fetch": lambda value: value.__setitem__(5, "0" * 64),
            "execution_path": lambda value: value.__setitem__(6, "elsewhere"),
            "execution_sha": lambda value: value.__setitem__(7, "0" * 64),
        }
        for label, mutate in mutations.items():
            first = copy.deepcopy(base)
            second = copy.deepcopy(base)
            mutate(second)
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                paths = (
                    root / "analysis.json", root / "analysis-repeat.json",
                    root / "receipt.json", root / "receipt.sha256",
                )
                with mock.patch.object(
                    Analyzer, "_load_inputs", side_effect=[first, second],
                ), mock.patch.object(
                    Analyzer, "analyze",
                    return_value={"schema": Analyzer.ANALYSIS_SCHEMA, "pass": True},
                ), self.assertRaisesRegex(Analyzer.AnalysisError, "input changed"):
                    Analyzer.run_twice(*paths, bootstrap_replicates=500)
                self.assertFalse(any(path.exists() for path in paths))

    def test_nondeterministic_analysis_publishes_nothing(self):
        freeze = fake_freeze()
        standalone = fake_standalone(freeze["base_confirmation_b"])
        inputs = (
            [], freeze, FREEZE_SHA, standalone, "a" * 64, "b" * 64,
            "experiments/artifacts/execution-receipt-v1.json", "c" * 64,
        )
        first = {"schema": Analyzer.ANALYSIS_SCHEMA, "pass": True, "nonce": 1}
        second = {**first, "nonce": 2}
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = (
                root / "analysis.json", root / "analysis-repeat.json",
                root / "receipt.json", root / "receipt.sha256",
            )
            with mock.patch.object(
                Analyzer, "_load_inputs",
                side_effect=[copy.deepcopy(inputs), copy.deepcopy(inputs)],
            ), mock.patch.object(
                Analyzer, "analyze", side_effect=[first, second]
            ), self.assertRaisesRegex(Analyzer.AnalysisError, "byte-identical"):
                Analyzer.run_twice(*paths)
            self.assertFalse(any(path.exists() for path in paths))


if __name__ == "__main__":
    unittest.main()
