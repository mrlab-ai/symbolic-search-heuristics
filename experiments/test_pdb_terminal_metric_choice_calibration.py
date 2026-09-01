#!/usr/bin/env python3

from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

import pdb_terminal_metric_choice_calibration as C
import pdb_terminal_metric_choice_protocol as P
from test_pdb_terminal_metric_choice_protocol import fake_calibration
from test_pdb_terminal_metric_choice_protocol import fake_planner


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

    def test_calibration_executes_the_attested_revision_cache_driver(self):
        manifest = fake_planner()
        cache = C.PlannerManifest.REVISION_CACHE / manifest["cache_name"]
        expected_hashes = {
            cache / manifest["driver_path"]: manifest["driver_sha256"],
            cache / manifest["downward_path"]: manifest["downward_sha256"],
            cache / manifest["preprocess_path"]: manifest["preprocess_sha256"],
        }
        with mock.patch.object(
            C.PlannerManifest, "verify_manifest", return_value=manifest
        ), mock.patch.object(
            P, "sha256_file",
            side_effect=lambda path, **kwargs: expected_hashes[path],
        ) as sha:
            self.assertEqual(C._validate_live_planner(manifest), cache / "fast-downward.py")
        self.assertEqual({call.args[0] for call in sha.call_args_list}, set(expected_hashes))
        self.assertTrue(all(
            call.kwargs["root"] == C.PlannerManifest.REVISION_CACHE
            for call in sha.call_args_list
        ))

    def test_driver_options_precede_search_configuration(self):
        driver = Path("/cache/fast-downward.py")
        domain = Path("/tmp/domain.pddl")
        problem = Path("/tmp/problem.pddl")
        mode = P.INCIDENCE_MODE
        self.assertEqual(
            C._planner_command(driver, domain, problem, mode),
            [
                str(driver), "--build", P.BUILD_OPTIONS[0],
                str(domain), str(problem), "--search", P.SEARCHES[mode],
            ],
        )

    def test_python_runtime_is_pinned(self):
        self.assertEqual(P.REQUIRED_PYTHON_VERSION, "3.12.13")


if __name__ == "__main__":
    unittest.main()
