#!/usr/bin/env python3
"""Focused tests for the semantic-union paper renderer."""

from __future__ import annotations

import copy
import unittest
from fractions import Fraction

import render_pdb_profile_semantic_union_paper as Renderer


class SemanticUnionRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.digest = Renderer._load(Renderer.DEFAULT_ANALYSIS)

    def test_production_artifact_renders_expected_gate_and_support(self):
        raw = Renderer.render(self.data, self.digest).decode("ascii")
        self.assertIn(r"\newcommand{\SemanticUnionGate}{fail}", raw)
        self.assertIn(r"\newcommand{\SemanticUnionPairTasks}{113}", raw)
        self.assertIn(r"\newcommand{\SemanticUnionWidthMacro}{0.786}", raw)
        self.assertIn(r"\newcommand{\SemanticUnionQualityMacro}{0.228}", raw)

    def test_scope_and_gate_contradictions_fail_closed(self):
        changed = copy.deepcopy(self.data)
        changed["scope"]["tasks"] += 1
        with self.assertRaisesRegex(Renderer.RenderError, "scope changed"):
            Renderer.render(changed, self.digest)
        changed = copy.deepcopy(self.data)
        changed["decision_gate"]["pass"] = True
        with self.assertRaisesRegex(Renderer.RenderError, "contradicts"):
            Renderer.render(changed, self.digest)

    def test_exact_fraction_validation(self):
        changed = copy.deepcopy(self.data)
        record = changed["shared_primary_comparison"]["predictors"][
            "cofactor_width"
        ]["equal_domain_macro"]
        record["value"] += 0.01
        with self.assertRaisesRegex(Renderer.RenderError, "disagrees"):
            Renderer.render(changed, self.digest)

    def test_rounding_is_half_up(self):
        self.assertEqual(Renderer._decimal(Fraction(1571, 2000)), "0.786")


if __name__ == "__main__":
    unittest.main()
