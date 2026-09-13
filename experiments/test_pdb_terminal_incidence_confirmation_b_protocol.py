#!/usr/bin/env python3
"""Focused tests for the Confirmation B production protocol surface."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import pdb_terminal_incidence_confirmation_b_protocol as P


class ConfirmationBProtocolTest(unittest.TestCase):
    def test_analysis_v3_consumes_confirmation_a_v4_namespace(self):
        self.assertEqual(
            P.ANALYSIS_PROTOCOL,
            "pdb-terminal-incidence-confirmation-b-analysis-v3",
        )
        self.assertEqual(
            P.CONFIRMATION_A_RECEIPT_PATH.name,
            "analysis-execution-receipt-v4.json",
        )
        self.assertEqual(
            P.CONFIRMATION_A_RECEIPT_PIN_PATH.name,
            "analysis-execution-receipt-v4.sha256",
        )
        self.assertEqual(
            P.CONFIRMATION_A_FIRST_OUTPUT_PATH.name,
            "analysis-v4.json",
        )
        self.assertEqual(
            P.CONFIRMATION_A_SECOND_OUTPUT_PATH.name,
            "analysis-v4-repeat.json",
        )

    def test_source_loader_accepts_only_one_v11_seal_revision(self):
        parameters = inspect.signature(P.load_source_materials).parameters
        self.assertEqual(tuple(parameters), ("source_seal_revision",))
        self.assertIs(
            parameters["source_seal_revision"].default,
            inspect.Parameter.empty,
        )
        with self.assertRaises(TypeError):
            P.load_source_materials(
                Path("attestation.json"),
                Path("execution.json"),
                Path("launch.json"),
            )
        with self.assertRaises(TypeError):
            P.load_source_materials("revision", Path("execution.json"))
        with self.assertRaisesRegex(P.ProtocolError, "revision is malformed"):
            P.load_source_materials(Path("not-a-literal-revision"))

    def test_legacy_source_readers_are_not_production_api(self):
        for name in (
            "LegacySourceMaterials",
            "_load_source_materials_v4_obsolete",
            "_load_source_materials_v7_legacy",
            "_load_freeze_v7_legacy",
            "_load_source_v4_byte_chain",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(P, name))

    def test_b_uses_v11_adapter_and_bound_planner(self):
        self.assertTrue({
            "experiments/pdb_terminal_incidence_confirmation_v11_adapter.py",
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v11.py",
            "experiments/pdb_terminal_incidence_v11_snapshot_reader.py",
        }.issubset(P.EXPERIMENT_SOURCE_FILES))
        self.assertFalse(any(
            "source_consumer_v7" in relative
            for relative in P.EXPERIMENT_SOURCE_FILES
        ))
        self.assertEqual(
            P.PLANNER_REVISION_REQUIRED,
            "8148f798f13059ee881ad2471bd20cdd61d2ec18",
        )

    def test_static_nine_configuration_design(self):
        P.validate_static_design()
        self.assertEqual(len(P.CONFIGS), 9)
        self.assertEqual(P.SEARCHES["blind_fw"], "sym_fw()")
        self.assertFalse(any(
            "shadow_partition=true" in search for _, search in P.CONFIGS
        ))
        self.assertIn(
            "pattern_selection=terminal_incidence_guided",
            P.SEARCHES[P.GUIDED_LABEL],
        )
        self.assertIn(
            "pattern_selection=terminal_incidence_matched_control",
            P.SEARCHES[P.MATCHED_LABEL],
        )

    def test_dynamic_cardinality_contract_requires_exactly_300(self):
        tasks = 300
        cells = len(P.CONFIGS) * tasks
        with mock.patch.multiple(
            P,
            COHORT_TASKS=tasks,
            CELL_COUNT=cells,
            EXPECTED_ARRAY_TASKS=(cells + P.RUNS_PER_ARRAY_TASK - 1)
            // P.RUNS_PER_ARRAY_TASK,
            RUN_CELL_MAPPING_SHA256="a" * 64,
        ):
            P.validate_protocol_design()

    def test_missing_freeze_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(P.ProtocolError):
                P._load_freeze(Path(tmp) / "missing.json")


if __name__ == "__main__":
    unittest.main()
