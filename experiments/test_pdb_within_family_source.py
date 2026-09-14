"""Structural support and resource-exit classifications for the fresh design."""

import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest

import pdb_within_family_source_worker as W


class SupportTests(unittest.TestCase):
    def test_positive_strips_is_supported(self):
        self.assertEqual(W.support_reasons(self.sas(), 0), [])

    @staticmethod
    def sas(**changes):
        result = {"num_operators": 4, "num_zero_cost_operators": 0,
                  "min_operator_cost": 1, "num_serialized_axioms": 0,
                  "num_conditional_effects": 0}
        return dict(result, **changes)

    def test_each_structural_violation_is_rejected(self):
        for field in ("num_zero_cost_operators", "num_serialized_axioms", "num_conditional_effects"):
            with self.subTest(field=field):
                self.assertEqual(len(W.support_reasons(self.sas(**{field: 1}), 0)), 1)
        self.assertEqual(W.support_reasons(self.sas(), 1), ["normalized-axioms"])
        self.assertIn("no-serialized-operators", W.support_reasons(self.sas(num_operators=0), 0))
        for cost in (0, None):
            self.assertIn("nonpositive-serialized-operator-cost",
                          W.support_reasons(self.sas(min_operator_cost=cost), 0))

    def test_signal_is_not_silently_a_resource_exclusion(self):
        self.assertEqual(W.classify_exit(-signal.SIGKILL, 1), "infrastructure-error")
        self.assertEqual(W.classify_exit(-signal.SIGKILL, 1801), "time-excluded")
        self.assertEqual(W.classify_exit(-signal.SIGSEGV, 1801), "infrastructure-error")
        self.assertEqual(W.classify_exit(-signal.SIGKILL, 2, True), "wall-excluded")

    def test_translator_outcomes_remain_distinct(self):
        for code, outcome in ((0, "translated"), (20, "memory-excluded"),
                              (21, "time-excluded"), (31, "input-error"),
                              (1, "infrastructure-error")):
            self.assertEqual(W.classify_exit(code, 0), outcome)

    def test_real_pinned_translator_and_input_integrity(self):
        root = Path(__file__).resolve().parent
        translator = root / "data/revision-cache/8148f798f13059ee_e261f35e36be/src/translate"
        with tempfile.TemporaryDirectory(prefix="source-worker-test-", dir=root / "data") as temporary:
            directory = Path(temporary)
            (directory / "domain.pddl").write_text(
                "(define (domain d) (:requirements :strips) (:predicates (p) (q)) "
                "(:action move :parameters () :precondition (p) :effect (and (not (p)) (q))))")
            (directory / "problem.pddl").write_text(
                "(define (problem p) (:domain d) (:init (p)) (:goal (q)))")
            config = {
                "id": ["translator", "synthetic", "p.pddl"],
                "planner_revision": "8148f798f13059ee881ad2471bd20cdd61d2ec18",
                "translator_sha256": {p.relative_to(translator).as_posix(): W.file_sha(p)
                                      for p in translator.rglob("*.py")},
                "worker_sha256": {name: W.file_sha(root / name) for name in (
                    "pdb_within_family_source_worker.py", "pdb_terminal_incidence_confirmation_translate_v12.py")},
                "python_sha256": W.file_sha(sys.executable),
                "domain_sha256": W.file_sha(directory / "domain.pddl"),
                "problem_sha256": W.file_sha(directory / "problem.pddl"),
            }
            config_path = directory / "source-config.json"
            config_path.write_bytes(W.canonical(config))
            previous = Path.cwd()
            try:
                os.chdir(directory)
                self.assertEqual(W.run(config_path, translator), 0)
                result = json.loads((directory / "source-result.json").read_bytes())
                self.assertEqual(result["status"], "supported")
                self.assertFalse(result["performance_observed"])
                self.assertEqual(result["normalization"]["num_normalized_axioms"], 0)
                with self.assertRaisesRegex(ValueError, "already used"):
                    W.run(config_path, translator)
                (directory / "problem.pddl").write_text("changed")
                with self.assertRaisesRegex(ValueError, "problem input changed"):
                    W.verify_inputs(config, translator)
            finally:
                os.chdir(previous)


if __name__ == "__main__":
    unittest.main()
