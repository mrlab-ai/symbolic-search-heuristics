"""Regression tests for the outcome-independent fresh-instance generator."""

from pathlib import Path
import unittest

import pdb_within_family_instances as G


class GeneratorTests(unittest.TestCase):
    def test_all_families_are_previously_studied(self):
        self.assertEqual(len(G.FAMILIES), 30)
        self.assertEqual(len(set(G.FAMILIES)), 30)
        self.assertTrue(set(G.FAMILIES) <= set(G.ALL_PRIOR_FAMILIES))

    def test_reproducible_role_disjoint_seeds(self):
        seen = set()
        for role in ("pilot", "a", "b"):
            for family in G.FAMILIES:
                for index in range(30):
                    value = G.seed_for(role, family, index)
                    self.assertEqual(value, G.seed_for(role, family, index))
                    self.assertGreater(value, 0)
                    self.assertLess(value, 2**31 - 1)
                    self.assertNotIn(value, seen)
                    seen.add(value)

    def test_every_size_setting_has_explicit_seed(self):
        destination = Path("/project/owned-generator-temp")
        for family in G.FAMILIES:
            for level in range(5):
                with self.subTest(family=family, level=level):
                    spec = G.specification(family, level, 918273, destination)
                    self.assertIn("918273", spec["command"])
                    self.assertEqual(
                        spec, G.specification(family, level, 918273, destination)
                    )
                    for name in ("domain_output", "problem_output"):
                        if spec[name] is not None:
                            self.assertEqual(spec[name].parent, destination)

    def test_no_randomization_only_in_name_or_comments(self):
        first = b"(define (problem first) (:domain d) (:init (p a)) (:goal (q a)))"
        renamed = b"; seed 999\n( DEFINE (PROBLEM second) (:domain d) (:init (p a)) (:goal (q a)))"
        changed = first.replace(b"(p a)", b"(p b)")
        self.assertEqual(G.instance_fingerprint(first), G.instance_fingerprint(renamed))
        self.assertNotEqual(G.instance_fingerprint(first), G.instance_fingerprint(changed))

    def test_invalid_pddl_is_rejected(self):
        for raw in (b"", b"usage: generator", b"(define (problem p)",
                    b"(define (domain p))", b"(define (problem p)))"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                G.instance_fingerprint(raw)

    def test_no_input_parameters_outside_fixed_grid(self):
        for family, level, seed in (("unseen", 0, 1), ("blocks", 5, 1),
                                    ("blocks", 0, 0)):
            with self.assertRaises(ValueError):
                G.specification(family, level, seed, Path("/project/owned-temp"))


if __name__ == "__main__":
    unittest.main()
