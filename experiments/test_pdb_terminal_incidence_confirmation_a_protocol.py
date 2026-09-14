#!/usr/bin/env python3
"""Focused tests for the Confirmation A production protocol surface."""

from __future__ import annotations

import inspect
import tempfile
import unittest
from pathlib import Path

import pdb_terminal_incidence_confirmation_a_protocol as P


class ConfirmationAProtocolTest(unittest.TestCase):
    def test_analysis_v4_preregisters_noncertificate_baselines(self):
        self.assertEqual(
            P.ANALYSIS_PROTOCOL,
            "pdb-terminal-incidence-confirmation-a-analysis-v4",
        )
        self.assertEqual(P.PREDICTORS[:3], ("I", "D", "value_count"))
        self.assertEqual(P.PREDICTOR_BASELINES[:2], ("D", "value_count"))
        self.assertNotIn("D", P.CERTIFICATE_BASELINES)
        self.assertNotIn("value_count", P.CERTIFICATE_BASELINES)
        self.assertEqual(P.CERTIFICATE_BASELINES[-1], P.MEET_CERTIFICATE)

    def test_source_loader_accepts_only_one_v12_seal_revision(self):
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
            "SourceV7",
            "LegacySourceMaterials",
            "_load_source_materials_v4_obsolete",
            "_load_source_materials_v7_legacy",
            "_load_freeze_v7_legacy",
            "_load_source_v4_byte_chain",
            "_repository_snapshot_files",
        ):
            with self.subTest(name=name):
                self.assertFalse(hasattr(P, name))

    def test_v12_adapter_and_planner_revision_are_bound(self):
        self.assertTrue({
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v12.py",
            "experiments/pdb_terminal_incidence_confirmation_v12_adapter.py",
            "experiments/pdb_terminal_incidence_v12_snapshot_reader.py",
        }.issubset(P.EXPERIMENT_SOURCE_FILES))
        self.assertFalse(any(
            "source_consumer_v7" in relative
            for relative in P.EXPERIMENT_SOURCE_FILES
        ))
        self.assertEqual(
            P.PLANNER_REVISION_REQUIRED,
            "8148f798f13059ee881ad2471bd20cdd61d2ec18",
        )

    def test_design_and_cegar_are_bound(self):
        P.validate_protocol_design()
        cegar = P.SEARCHES["pdb_cegar_shadow"]
        self.assertIn("cegar_max_time=infinity", cegar)
        self.assertIn("cegar_max_refinements=128", cegar)

    def test_missing_freeze_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(P.ProtocolError):
                P._load_freeze(Path(tmp) / "missing.json")


if __name__ == "__main__":
    unittest.main()
