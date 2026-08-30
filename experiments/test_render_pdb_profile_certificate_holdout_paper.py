#!/usr/bin/env python3
"""Adversarial tests for the prospective-holdout paper renderer."""

from __future__ import annotations

import copy
import unittest

import render_pdb_profile_certificate_holdout_paper as Renderer


class CertificateHoldoutRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.primary, cls.primary_digest = Renderer._load(
            Renderer.DEFAULT_ANALYSIS,
            Renderer.EXPECTED_ANALYSIS_SHA256,
            Renderer.MAX_ANALYSIS_BYTES,
            "primary analysis",
        )
        cls.audit, cls.audit_digest = Renderer._load(
            Renderer.DEFAULT_DENOMINATOR_AUDIT,
            Renderer.EXPECTED_DENOMINATOR_AUDIT_SHA256,
            Renderer.MAX_AUDIT_BYTES,
            "denominator audit",
        )

    def test_production_output_is_exact_and_current(self):
        raw = Renderer.render(
            self.primary,
            self.audit,
            self.primary_digest,
            self.audit_digest,
        )
        self.assertEqual(
            raw,
            Renderer.Common._read_regular(
                Renderer.DEFAULT_OUTPUT, Renderer.MAX_TEX_BYTES
            ),
        )
        text = raw.decode("ascii")
        self.assertIn("\\newcommand{\\HoldoutTwoEffectRows}", text)
        self.assertIn("\\newcommand{\\HoldoutWidthAddRows}", text)
        self.assertIn(self.primary_digest, text)
        self.assertIn(self.audit_digest, text)

    def test_scope_and_gate_mutations_fail_closed(self):
        changed = copy.deepcopy(self.primary)
        changed["scope"]["tasks"] -= 1
        with self.assertRaisesRegex(Renderer.RenderError, "scope changed"):
            Renderer.render(
                changed,
                self.audit,
                self.primary_digest,
                self.audit_digest,
            )

        changed = copy.deepcopy(self.audit)
        gate = changed["decision_gates"]["denominator_artifact_robustness"]
        gate["pass"] = not gate["pass"]
        with self.assertRaisesRegex(Renderer.RenderError, "gates contradict"):
            Renderer.render(
                self.primary,
                changed,
                self.primary_digest,
                self.audit_digest,
            )


if __name__ == "__main__":
    unittest.main()
