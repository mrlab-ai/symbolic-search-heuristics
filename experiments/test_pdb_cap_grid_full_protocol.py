#!/usr/bin/env python3

import copy
import sys
import unittest
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_pdb_cap_grid_full as runner
import pdb_cap_grid_full_protocol as P


class FocusedFullProtocolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tasks = P.screen_analyzer.load_tasks()
        pins = (
            P.SCREEN_PROTOCOL_REVISION,
            P.SCREEN_PLANNER_REVISION,
            P.SCREEN_CACHE_BINARY_SHA256,
            P.SCREEN_CACHE_PREPROCESS_SHA256,
        )
        cls.synthetic_screen = P.screen_analyzer.synthetic_records(tasks, pins)
        cls.synthetic_digest = P._screen_properties_digest(cls.synthetic_screen)

    def primary(self):
        return {
            "candidate": P.CAP,
            "reference": P.EXACT,
            "coverage": {"wins": 3, "losses": 3},
            "raw_pool_isolation": {
                "status": "certified",
                "matching_complete_cross_protocol_fingerprints": 50,
                "required": 50,
            },
            "semantic_nontrivial_selection": {
                "status": "estimable",
                "paired_certified_traces": 50,
                "candidate_nontrivial": 4,
                "reference_nontrivial": 3,
            },
        }

    def test_exact_matrix_and_layout(self):
        self.assertEqual(P.option_matrix_digest(), P.OPTION_MATRIX_SHA256)
        self.assertEqual(P.validate_layout()["raw_runs"], 6885)
        self.assertEqual(P.validate_layout()["array_tasks"], 984)
        self.assertEqual(P.validate_layout()["runs_per_array_task"], 7)
        self.assertEqual(
            P.array_assignment()["slurm_id_to_logical_group_sha256"],
            P.EXPECTED_ARRAY_ASSIGNMENT_SHA256,
        )

    def test_promotion_boundary_is_inclusive_at_zero_net(self):
        checks = P.promotion_checks(
            self.primary(), record_count=300, matrix_count=300
        )
        self.assertTrue(all(checks.values()))

    def test_k8_loss_or_non_strict_mechanism_blocks(self):
        primary = self.primary()
        primary["coverage"] = {"wins": 2, "losses": 3}
        checks = P.promotion_checks(
            primary, record_count=300, matrix_count=300
        )
        self.assertFalse(
            checks["cap_k8_coverage_wins_minus_losses_nonnegative"]
        )
        primary = self.primary()
        primary["semantic_nontrivial_selection"]["candidate_nontrivial"] = 3
        checks = P.promotion_checks(
            primary, record_count=300, matrix_count=300
        )
        self.assertFalse(
            checks[
                "cap_k8_has_strictly_more_semantic_nontrivial_selections"
            ]
        )

    def test_k32_cannot_substitute(self):
        primary = self.primary()
        primary["candidate"] = "pdb_cap_grid_k32"
        primary["reference"] = "pdb_selector_k32"
        with self.assertRaisesRegex(P.ProtocolError, "cap-K8"):
            P.promotion_checks(primary, record_count=300, matrix_count=300)

    def test_properties_pin_precedes_loader(self):
        old = P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256
        P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256 = None
        try:
            with mock.patch.object(
                P.screen_analyzer.safe_loader,
                "load_properties",
                side_effect=AssertionError("loader must not be reached"),
            ) as loader:
                with self.assertRaisesRegex(P.ProtocolError, "refusing to read"):
                    P.load_and_evaluate_promotion("/outcome/path")
                loader.assert_not_called()
        finally:
            P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256 = old

    def test_complete_synthetic_screen_is_revalidated_and_promotes(self):
        old = P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256
        P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256 = self.synthetic_digest
        try:
            certificate = P.evaluate_promotion(
                copy.deepcopy(self.synthetic_screen), self.synthetic_digest
            )
            self.assertTrue(certificate["promoted"])
            self.assertEqual(certificate["k8"]["matching_raw_pool_pairs"], 50)
            self.assertGreater(
                certificate["k8"]["cap_semantic_nontrivial"],
                certificate["k8"]["exact_semantic_nontrivial"],
            )
            self.assertGreaterEqual(certificate["k8"]["coverage_net"], 0)
        finally:
            P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256 = old

    def test_screen_solved_cost_disagreement_fails_before_promotion(self):
        records = copy.deepcopy(self.synthetic_screen)
        target = next(
            record
            for record in records
            if record["algorithm"] == P.BLIND and record["coverage"] == 1
        )
        target["solution_cost"] += 1
        digest = P._screen_properties_digest(records)
        old = P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256
        P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256 = digest
        try:
            with self.assertRaisesRegex(P.ProtocolError, "validation failed"):
                P.evaluate_promotion(records, digest)
        finally:
            P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256 = old

    def test_job_is_deterministic_and_unpinned(self):
        runner.configure_completion_base()
        first, first_digest = runner.prospective_job()
        second, second_digest = runner.prospective_job()
        self.assertEqual(first, second)
        self.assertEqual(first_digest, second_digest)
        self.assertRegex(first_digest, r"^[0-9a-f]{64}$")
        self.assertIsNone(P.EXPECTED_PROSPECTIVE_JOB_SHA256)
        self.assertIsNone(P.PROTOCOL_IMPLEMENTATION_REVISION)


if __name__ == "__main__":
    unittest.main()
