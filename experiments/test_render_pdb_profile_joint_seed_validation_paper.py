#!/usr/bin/env python3
"""Adversarial tests for the unseen-seed paper renderer."""

from __future__ import annotations

import copy
import unittest

import render_pdb_profile_joint_seed_validation_paper as Renderer


class JointSeedValidationRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.digest = Renderer._load(Renderer.DEFAULT_ANALYSIS)

    def test_production_output_is_exact_and_current(self):
        raw = Renderer.render(self.data, self.digest)
        self.assertEqual(
            raw,
            Renderer.Common._read_regular(
                Renderer.DEFAULT_OUTPUT, Renderer.MAX_TEX_BYTES
            ),
        )
        text = raw.decode("ascii")
        self.assertIn(r"\newcommand{\SeedPrimaryPairs}{1832}", text)
        self.assertIn(r"\newcommand{\SeedJointMacro}{0.631}", text)
        self.assertIn(r"\newcommand{\SeedNullMacro}{0.641}", text)
        self.assertIn(r"\newcommand{\SeedCartesianMacro}{0.494}", text)
        self.assertIn(r"\newcommand{\SeedPrimaryGate}{fail}", text)
        self.assertIn(r"\newcommand{\SeedAbsoluteGate}{pass}", text)
        self.assertIn(
            r"\newcommand{\SeedJointCartesianMedianRatio}{0.205}", text
        )
        self.assertIn(self.digest, text)

    def test_scope_gate_and_certificate_mutations_fail_closed(self):
        changed = copy.deepcopy(self.data)
        changed["scope"]["tasks"] += 1
        with self.assertRaisesRegex(Renderer.RenderError, "scope changed"):
            Renderer.render(changed, self.digest)

        changed = copy.deepcopy(self.data)
        gate = changed["decision_gates"]["joint_beyond_denominator_null"]
        gate["pass"] = not gate["pass"]
        with self.assertRaisesRegex(Renderer.RenderError, "decision gates"):
            Renderer.render(changed, self.digest)

        changed = copy.deepcopy(self.data)
        seed = next(iter(changed["task_observations"][0]["seeds"].values()))
        seed["B_joint"] = seed["B_profile"] + 1
        with self.assertRaisesRegex(
            Renderer.RenderError, "exceeds Cartesian relaxation"
        ):
            Renderer.render(changed, self.digest)


if __name__ == "__main__":
    unittest.main()
