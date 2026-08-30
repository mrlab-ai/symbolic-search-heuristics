#!/usr/bin/env python3
"""Focused tests for the variable-order intervention paper renderer."""

from __future__ import annotations

import copy
import unittest

import render_pdb_profile_order_intervention_paper as Renderer


class OrderInterventionRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.digest = Renderer._load(Renderer.DEFAULT_ANALYSIS)

    def test_production_artifact_renders_frozen_result(self):
        raw = Renderer.render(self.data, self.digest).decode("ascii")
        self.assertIn(r"\newcommand{\OrderStrictPairs}{305}", raw)
        self.assertIn(r"\newcommand{\OrderProfileMacro}{0.714}", raw)
        self.assertIn(r"\newcommand{\OrderWidthMacro}{0.420}", raw)
        self.assertIn(r"\newcommand{\OrderAddMacro}{0.356}", raw)
        self.assertIn(r"\newcommand{\OrderSharperGate}{pass}", raw)

    def test_scope_and_gate_contradictions_fail_closed(self):
        changed = copy.deepcopy(self.data)
        changed["scope"]["tasks"] += 1
        with self.assertRaisesRegex(Renderer.RenderError, "scope changed"):
            Renderer.render(changed, self.digest)
        changed = copy.deepcopy(self.data)
        changed["decision_gates"]["sharper_order_predictor"]["pass"] = False
        with self.assertRaisesRegex(Renderer.RenderError, "decision gates"):
            Renderer.render(changed, self.digest)

    def test_exact_fraction_validation(self):
        changed = copy.deepcopy(self.data)
        record = changed["primary_shared"]["predictors"]["profile"][
            "equal_domain_macro"
        ]
        record["value"] += 0.01
        with self.assertRaisesRegex(Renderer.RenderError, "disagrees"):
            Renderer.render(changed, self.digest)


if __name__ == "__main__":
    unittest.main()
