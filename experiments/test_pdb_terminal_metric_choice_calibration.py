#!/usr/bin/env python3

from __future__ import annotations

import unittest

import pdb_terminal_metric_choice_calibration as C
import pdb_terminal_metric_choice_protocol as P
from test_pdb_terminal_metric_choice_protocol import fake_calibration


class CalibrationTest(unittest.TestCase):
    def test_development_tasks_are_fixed_generated_and_reserved(self):
        manifest = C.development_manifest()
        self.assertEqual(len(manifest["tasks"]), 3)
        self.assertEqual(C.development_manifest_sha256(), C.development_manifest_sha256())
        self.assertTrue(all(
            row["task_id"].startswith("__metric_choice_calibration__/")
            and row["eligibility"] == "synthetic-generated-never-benchmark-eligible"
            for row in manifest["tasks"]
        ))

    def test_receipt_exposes_only_registered_overheads(self):
        receipt = fake_calibration()
        P.validate_calibration_receipt(receipt)
        allowed = {"task_id", "mode", *C.EXPOSED_FIELDS}
        self.assertTrue(all(set(row) == allowed for row in receipt["observations"]))
        serialized = P.canonical_json(receipt).decode("ascii")
        for forbidden in (
            "selected_identity", "winner_identity", "reference_identity",
            '"coverage"', '"search_time"', '"plan_cost"', '"exit_code"',
        ):
            self.assertNotIn(forbidden, serialized)


if __name__ == "__main__":
    unittest.main()
