#!/usr/bin/env python3
"""Adversarial tests for the terminal-incidence shadow protocol."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audit_pdb_terminal_incidence_sources as SourceAudit
import exp_pdb_terminal_incidence_shadow as Experiment
import pdb_fixed_pattern_parser as Pattern
import pdb_terminal_incidence_shadow_protocol as P


BENCHMARKS = Path(
    "/nobackup/proj/disk/dfsplan/personal/jendrik/downward-benchmarks-wbh"
)


class TerminalIncidenceShadowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cohort = P.load_cohort(BENCHMARKS, validate_costs=False)

    def test_protocol_cohort_and_translator_are_exact(self):
        P.validate_protocol_without_sources()
        self.assertEqual(len(self.cohort), 460)
        self.assertEqual(len({task.domain for task in self.cohort}), 46)
        self.assertEqual(len({task.family for task in self.cohort}), 26)
        self.assertEqual(
            SourceAudit.translator_source_digest(),
            P.TRANSLATOR_SOURCE_SHA256,
        )

    def test_cost_attestation_covers_every_task(self):
        data = P.validate_cost_attestation(self.cohort)
        self.assertEqual(data["counts"]["sas_v3_scan"], 190)
        self.assertEqual(
            data["counts"]["pddl_no_metric_unit_cost_proof"], 270
        )
        self.assertEqual(data["counts"]["positive_cost"], 460)
        self.assertEqual(data["counts"]["with_normalized_axioms"], 0)

    def test_matrix_is_fixed_frontier_and_cap_is_separate(self):
        self.assertEqual(P.LABELS[:-1], P.PRIMARY_LABELS)
        self.assertEqual(P.LABELS[-1], P.INTERVENTION_LABEL)
        for label, search in P.CONFIGS:
            self.assertIn("shadow_partition=true", search)
            self.assertIn("gamer_ordering=false", search)
            self.assertIn("dynamic_reordering=false", search)
            self.assertEqual("value_cap=8" in search, label == P.INTERVENTION_LABEL)

    def test_direct_pattern_parser_binds_mode_pattern_and_final_stats(self):
        content = "\n".join((
            "PDB pattern selection=bdd_prefix "
            "(3 vars, <= 100000 abstract states): [0, 2, 5]",
            "wbh PDB heuristic: pattern_size=3, values=7, "
            "cofactor_width=11, width_upper_bound=19",
        ))
        identity = Pattern.parse_identity(content)
        self.assertEqual(identity["mode"], "bdd_prefix")
        self.assertEqual(identity["pattern"], [0, 2, 5])
        self.assertEqual(identity["num_values"], 7)
        props = {}
        Pattern.parse_goal_fill_pattern(content, props)
        self.assertTrue(props["pdb_fixed_pattern_certified"])
        self.assertEqual(props["pdb_fixed_pattern_final"], identity)

    def test_direct_pattern_parser_rejects_crossed_final_identity(self):
        content = "\n".join((
            "PDB pattern selection=goal_fill "
            "(2 vars, <= 100000 abstract states): [0, 2]",
            "wbh PDB heuristic: pattern_size=3, values=7, value_cap=8, "
            "cofactor_width=11, width_upper_bound=19",
        ))
        with self.assertRaisesRegex(Pattern.PatternParseError, "invalid"):
            Pattern.parse_identity(content)

    def test_direct_pattern_parser_rejects_algorithm_mode_mismatch(self):
        content = "\n".join((
            "PDB pattern selection=goal_prefix "
            "(1 vars, <= 100000 abstract states): [0]",
            "wbh PDB heuristic: pattern_size=1, values=2, "
            "cofactor_width=2, width_upper_bound=3",
        ))
        props = {"algorithm": "pdb_bdd_prefix_shadow"}
        Pattern.parse_goal_fill_pattern(content, props)
        self.assertFalse(props["pdb_fixed_pattern_certified"])
        self.assertIn("disagrees", props["pdb_fixed_pattern_validation_error"])

    def test_runner_is_unthrottled_fat_and_uses_pinned_sources(self):
        Experiment.configure()
        self.assertEqual(Experiment.Base.PARTITION, "fat")
        self.assertEqual(Experiment.Base.RUNS_PER_ARRAY_TASK, 3)
        self.assertEqual(Experiment.Base.EXPECTED_ARRAY_TASKS, 767)
        self.assertFalse(
            Experiment.Base.VALIDATE_MATCHED_BUDGET_PROVENANCE
        )
        self.assertEqual(Experiment.Base.BENCHMARKS, BENCHMARKS)
        Experiment.Base.self_test()

    def test_launch_inputs_are_frozen_before_submission(self):
        Experiment.configure()
        base = Experiment.Base

        class Cache:
            @staticmethod
            def attest():
                return {
                    "revision": base.PLANNER_REVISION,
                    "build_options": list(P.BUILD_OPTIONS),
                    "downward_sha256": base.PLANNER_BINARY_SHA256,
                    "preprocess_sha256": base.PREPROCESS_BINARY_SHA256,
                    "tree_manifest_sha256": P.PLANNER_TREE_MANIFEST_SHA256,
                }

            @staticmethod
            def get_relative_exp_path(relpath=""):
                return str(Path("code-pinned") / relpath)

            @classmethod
            def attest_path(cls, _path):
                return cls.attest()

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            experiment = root / "data"
            run_dir = experiment / "runs-00001-00100" / "00001"
            run_dir.mkdir(parents=True)
            (run_dir / "run").write_text("run-v1\n", encoding="ascii")
            (run_dir / "static-properties").write_text(
                "properties-v1\n", encoding="ascii"
            )
            (experiment / "static-experiment-properties").write_text(
                "experiment-v1\n", encoding="ascii"
            )
            source = root / "runner.py"
            source.write_text("# frozen\n", encoding="ascii")
            job = root / base.EXPECTED_JOB_NAME
            job.write_text("#!/bin/bash\n", encoding="ascii")
            receipt = root / "artifacts" / "launch-receipt-v1.json"
            with (
                mock.patch.object(base, "SCRIPT_DIR", root),
                mock.patch.object(base, "EXPERIMENT_PATH", experiment),
                mock.patch.object(base, "LAUNCH_RECEIPT", receipt),
                mock.patch.object(base, "RUNNER_SOURCE_FILES", ("runner.py",)),
                mock.patch.object(base, "EXTRA_RECEIPT_PROPERTIES", {}),
                mock.patch.object(base, "MATERIALIZE_PDDL_INPUTS", False),
                mock.patch.object(
                    base, "ENVIRONMENT_REQUIREMENTS_FILE", root / "req.txt"
                ),
                mock.patch.object(
                    base,
                    "_environment_attestation",
                    return_value={
                        "python_executable_sha256": "a" * 64,
                        "python_environment_sha256": "b" * 64,
                        "python_distributions": {"lab": "8.10"},
                        "python_requirements_sha256": "c" * 64,
                    },
                ),
                mock.patch.object(P, "CELL_COUNT", 1),
            ):
                base._write_build_receipt(Cache())
                materials = base._prepare_launch_materials(job, Cache())
                intent = base._launch_intent_path()
                self.assertTrue(intent.is_file())
                self.assertFalse(receipt.exists())
                (run_dir / "run").write_text("changed\n", encoding="ascii")
                base._write_launch_receipt("12345", materials)
                recorded = json.loads(receipt.read_text(encoding="ascii"))
                self.assertEqual(recorded["job_id"], "12345")
                self.assertEqual(
                    recorded["launch_intent_sha256"],
                    hashlib.sha256(intent.read_bytes()).hexdigest(),
                )

    def test_launch_preflight_rejects_an_incomplete_run_tree(self):
        Experiment.configure()
        base = Experiment.Base
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            experiment = root / "data"
            experiment.mkdir()
            (experiment / "static-experiment-properties").write_text(
                "experiment-v1\n", encoding="ascii"
            )
            source = root / "runner.py"
            source.write_text("# frozen\n", encoding="ascii")
            job = root / base.EXPECTED_JOB_NAME
            job.write_text("#!/bin/bash\n", encoding="ascii")
            receipt = root / "artifacts" / "launch-receipt-v1.json"
            with (
                mock.patch.object(base, "SCRIPT_DIR", root),
                mock.patch.object(base, "EXPERIMENT_PATH", experiment),
                mock.patch.object(base, "LAUNCH_RECEIPT", receipt),
                mock.patch.object(base, "RUNNER_SOURCE_FILES", ("runner.py",)),
                mock.patch.object(base, "MATERIALIZE_PDDL_INPUTS", False),
                mock.patch.object(P, "CELL_COUNT", 1),
            ):
                with self.assertRaisesRegex(
                    base.LaunchError, "run directory is absent or invalid"
                ):
                    base._run_input_tree_digest()
                self.assertFalse(base._launch_intent_path().exists())

    def test_config_mutation_is_rejected(self):
        original = P.CONFIGS
        try:
            changed = list(original)
            changed[0] = (
                changed[0][0],
                changed[0][1].replace(
                    "dynamic_reordering=false",
                    "dynamic_reordering=true",
                ),
            )
            self.assertNotEqual(P.option_matrix_digest(tuple(changed)), P.OPTION_MATRIX_SHA256)
        finally:
            P.CONFIGS = original


if __name__ == "__main__":
    unittest.main()
