#!/usr/bin/env python3
"""Unit tests for the terminal-incidence result renderer."""

from __future__ import annotations

import copy
import contextlib
import io
import re
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_terminal_incidence_results as renderer


def _q(numerator: int, denominator: int = 1) -> dict:
    value = Fraction(numerator, denominator)
    return {"numerator": value.numerator, "denominator": value.denominator}


def _baselines(*, pass_gate: bool = True) -> dict:
    margin = _q(3, 100) if pass_gate else _q(19, 1000)
    return {
        name: {
            "margin": dict(margin),
            "bootstrap_lower": _q(1, 100),
            "lofo_minimum": _q(1, 200),
        }
        for name in renderer.BASELINES
    }


def _contrast(*, pass_gate: bool = True, maximum_tasks: int = 300) -> dict:
    return {
        "coverage_incidence": min(210, maximum_tasks),
        "coverage_comparator": min(205, maximum_tasks),
        "mean_improvement": _q(3, 100) if pass_gate else _q(19, 1000),
        "bootstrap_lower": _q(1, 100),
        "lofo_minimum": _q(1, 200),
    }


def fixture(*, a_pass: bool, direct_pass: bool | None, b_pass: bool | None) -> dict:
    if not a_pass and (direct_pass is not None or b_pass is not None):
        raise ValueError("a failed fixture cannot contain downstream outcomes")
    if a_pass and (direct_pass is None or b_pass is None):
        raise ValueError("a passing fixture requires both downstream outcomes")
    evidence = {
        "source_audit": {
            "sealed": True,
            "a_tasks": 650,
            "a_families": 30,
            "a_shadow_families": 14,
            "a_prior_tasks": 120,
            "a_prior_families": 12,
            "b_tasks": 300,
            "b_families": 32,
            "b_shadow_families": 15,
            "b_prior_tasks": 60,
            "b_prior_families": 11,
        },
        "confirmation_a": {
            "sealed": True,
            "eligible_tasks": 320,
            "comparison_tasks": 310,
            "eligible_families": 27,
            "comparison_families": 25,
            "target_strict_pairs": 700,
            "i_concordance": _q(7, 10) if a_pass else _q(16, 25),
            "baselines": _baselines(),
            "orientation": {
                "orders_identical": True,
                "inverse_u_tied": True,
            },
            "all_prior": {
                "comparison_tasks": 60,
                "comparison_families": 10,
                "target_strict_pairs": 120,
                "i_concordance": _q(17, 25),
                "baselines": _baselines(),
                "orientation": {
                    "orders_identical": True,
                    "inverse_u_tied": True,
                },
            },
        },
        "hardware": {
            "a_receipt_sealed": True,
            "downstream_receipts_sealed": a_pass,
        },
    }
    if a_pass:
        evidence["direct_metric_choice"] = {
            "sealed": True,
            "audit_certified": True,
            "tasks": 300,
            "families": 32,
            "full": _contrast(pass_gate=bool(direct_pass)),
            "differing_winners": {
                "tasks": 60,
                "families": 12,
                **_contrast(pass_gate=bool(direct_pass), maximum_tasks=60),
            },
        }
        evidence["confirmation_b"] = {
            "sealed": True,
            "selector_provenance_pass": True,
            "tasks": 300,
            "families": 32,
            "versus_reference": _contrast(pass_gate=bool(b_pass)),
            "versus_matched": _contrast(pass_gate=bool(b_pass)),
        }
    return evidence


def _drop_downstream(evidence: dict) -> None:
    del evidence["direct_metric_choice"]
    del evidence["confirmation_b"]
    evidence["hardware"]["downstream_receipts_sealed"] = False


class RendererTests(unittest.TestCase):
    def test_exact_five_terminal_branches(self) -> None:
        cases = (
            (False, None, None, renderer.OutcomeBranch.A_FAIL),
            (
                True,
                False,
                False,
                renderer.OutcomeBranch.A_PASS_DIRECT_FAIL_B_FAIL,
            ),
            (
                True,
                False,
                True,
                renderer.OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS,
            ),
            (
                True,
                True,
                False,
                renderer.OutcomeBranch.A_PASS_DIRECT_PASS_B_FAIL,
            ),
            (
                True,
                True,
                True,
                renderer.OutcomeBranch.A_PASS_DIRECT_PASS_B_PASS,
            ),
        )
        self.assertEqual(len(renderer.OutcomeBranch), 5)
        for a_pass, direct_pass, b_pass, expected in cases:
            with self.subTest(expected=expected.value):
                actual = renderer.classify(
                    fixture(
                        a_pass=a_pass,
                        direct_pass=direct_pass,
                        b_pass=b_pass,
                    )
                )
                self.assertEqual(actual.branch, expected)

    def test_b_never_changes_title(self) -> None:
        for direct_pass, expected in (
            (False, renderer.TITLE_PREDICTOR),
            (True, renderer.TITLE_SELECTION),
        ):
            titles = set()
            for b_pass in (False, True):
                output = renderer.render(
                    fixture(a_pass=True, direct_pass=direct_pass, b_pass=b_pass)
                )
                match = re.search(r"\\newcommand\{\\TIOutcomeTitle\}\{([^\n]*)\}", output)
                self.assertIsNotNone(match)
                titles.add(match.group(1))
            self.assertEqual(titles, {expected})

    def test_a_failure_uses_certificate_title(self) -> None:
        output = renderer.render(
            fixture(a_pass=False, direct_pass=None, b_pass=None)
        )
        self.assertIn(
            rf"\newcommand{{\TIOutcomeTitle}}{{{renderer.TITLE_CERTIFICATES}}}",
            output,
        )

    def test_exact_eight_macros(self) -> None:
        output = renderer.render(
            fixture(a_pass=True, direct_pass=True, b_pass=True)
        )
        names = re.findall(r"^\\newcommand\{\\([^}]+)\}", output, re.MULTILINE)
        self.assertEqual(
            names,
            [
                "TIOutcomeTitle",
                "TIOutcomeAbstract",
                "TIOutcomeA",
                "TIOutcomeMetricChoice",
                "TIOutcomeB",
                "TIOutcomeConclusion",
                "TIOutcomeSourceAudit",
                "TIOutcomeHardware",
            ],
        )

    def test_a_failure_rejects_downstream_results(self) -> None:
        evidence = fixture(a_pass=False, direct_pass=None, b_pass=None)
        passing = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["direct_metric_choice"] = passing["direct_metric_choice"]
        evidence["confirmation_b"] = passing["confirmation_b"]
        with self.assertRaisesRegex(renderer.RenderError, "schema mismatch"):
            renderer.classify(evidence)

    def test_a_pass_requires_b_and_direct_inputs(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        del evidence["confirmation_b"]
        with self.assertRaisesRegex(renderer.RenderError, "schema mismatch"):
            renderer.classify(evidence)

    def test_a_pass_requires_sealed_downstream_inputs(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["direct_metric_choice"]["sealed"] = False
        with self.assertRaisesRegex(renderer.RenderError, "not sealed"):
            renderer.classify(evidence)

    def test_decisions_are_recomputed_from_evidence(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["direct_metric_choice"]["full"]["mean_improvement"] = _q(
            19, 1000
        )
        outcome = renderer.classify(evidence)
        self.assertFalse(outcome.direct_pass)
        self.assertEqual(
            outcome.branch,
            renderer.OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS,
        )

    def test_decision_labels_are_not_in_the_schema(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=False, b_pass=False)
        evidence["direct_metric_choice"]["decision"] = "PASS"
        with self.assertRaisesRegex(renderer.RenderError, "artifact-provided text"):
            renderer.classify(evidence)

    def test_extra_numeric_field_is_not_in_the_schema(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=False, b_pass=False)
        evidence["confirmation_b"]["unreviewed_statistic"] = 1
        with self.assertRaisesRegex(renderer.RenderError, "schema mismatch"):
            renderer.classify(evidence)

    def test_exact_types_reject_bool_as_int_and_scalar_as_rational(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["source_audit"]["a_tasks"] = True
        with self.assertRaisesRegex(renderer.RenderError, "must be an int"):
            renderer.classify(evidence)
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["confirmation_a"]["i_concordance"] = 1
        with self.assertRaisesRegex(renderer.RenderError, "must be a dict"):
            renderer.classify(evidence)

    def test_malformed_or_noncanonical_rational_is_rejected(self) -> None:
        for value, message in (
            ({"numerator": 1, "denominator": 0}, "positive int"),
            ({"numerator": 1, "denominator": -1}, "positive int"),
            ({"numerator": 2, "denominator": 4}, "canonical rational"),
            ({"numerator": 0, "denominator": 2}, "canonical rational"),
            ({"numerator": True, "denominator": 1}, "numerator must be an int"),
            ({"numerator": 1, "denominator": True}, "positive int"),
            ({"numerator": 2, "denominator": 1}, "allowed range"),
            ({"numerator": 1}, "schema mismatch"),
            (
                {"numerator": 1, "denominator": 2, "value": 0.5},
                "schema mismatch",
            ),
            (float("nan"), "must be a dict"),
            (float("inf"), "must be a dict"),
        ):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            evidence["confirmation_b"]["versus_reference"][
                "bootstrap_lower"
            ] = value
            with self.subTest(value=value):
                with self.assertRaisesRegex(renderer.RenderError, message):
                    renderer.classify(evidence)

    def test_tex_and_private_identity_injection_are_rejected(self) -> None:
        for injected in (r"\input{/tmp/attack}", "/home/private/user/result"):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            evidence["confirmation_a"]["i_concordance"] = injected
            with self.subTest(injected=injected):
                with self.assertRaisesRegex(
                    renderer.RenderError, "artifact-provided text"
                ):
                    renderer.render(evidence)

    def test_a_gate_boundary_is_recomputed(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["confirmation_a"]["baselines"]["mJ"]["margin"] = _q(
            19, 1000
        )
        _drop_downstream(evidence)
        self.assertEqual(
            renderer.classify(evidence).branch,
            renderer.OutcomeBranch.A_FAIL,
        )

    def test_exact_rationals_do_not_round_up_across_gate_boundaries(self) -> None:
        cases = (
            (
                ("baselines", "mJ", "margin"),
                _q(19999999999999999, 10**18),
            ),
            (("i_concordance",), _q(64999999999999999, 10**17)),
        )
        for keys, value in cases:
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            target = evidence["confirmation_a"]
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value
            _drop_downstream(evidence)
            with self.subTest(keys=keys):
                self.assertEqual(
                    renderer.classify(evidence).branch,
                    renderer.OutcomeBranch.A_FAIL,
                )

    def test_exact_gate_boundaries_pass_but_strict_zero_boundaries_fail(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["confirmation_a"]["i_concordance"] = _q(13, 20)
        evidence["confirmation_a"]["all_prior"]["i_concordance"] = _q(13, 20)
        evidence["confirmation_a"]["baselines"]["mJ"]["margin"] = _q(1, 50)
        evidence["confirmation_a"]["all_prior"]["baselines"]["mJ"][
            "margin"
        ] = _q(1, 50)
        evidence["direct_metric_choice"]["full"]["mean_improvement"] = _q(1, 50)
        evidence["direct_metric_choice"]["differing_winners"][
            "mean_improvement"
        ] = _q(1, 50)
        for contrast in ("versus_reference", "versus_matched"):
            evidence["confirmation_b"][contrast]["mean_improvement"] = _q(1, 50)
        self.assertTrue(renderer.classify(evidence).a_pass)
        self.assertTrue(renderer.classify(evidence).direct_pass)
        self.assertTrue(renderer.classify(evidence).b_pass)

        for field in ("bootstrap_lower", "lofo_minimum"):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            evidence["direct_metric_choice"]["full"][field] = _q(0)
            with self.subTest(field=field):
                self.assertFalse(renderer.classify(evidence).direct_pass)

    def test_each_downstream_contrast_controls_its_gate(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["direct_metric_choice"]["differing_winners"][
            "mean_improvement"
        ] = _q(19, 1000)
        self.assertFalse(renderer.classify(evidence).direct_pass)

        for contrast in ("versus_reference", "versus_matched"):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            evidence["confirmation_b"][contrast]["mean_improvement"] = _q(
                19, 1000
            )
            with self.subTest(contrast=contrast):
                self.assertFalse(renderer.classify(evidence).b_pass)

    def test_zero_support_null_statistics_render_a_failure(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        confirmation = evidence["confirmation_a"]
        confirmation["comparison_tasks"] = 0
        confirmation["comparison_families"] = 0
        confirmation["target_strict_pairs"] = 0
        confirmation["i_concordance"] = None
        prior = confirmation["all_prior"]
        prior["comparison_tasks"] = 0
        prior["comparison_families"] = 0
        prior["target_strict_pairs"] = 0
        prior["i_concordance"] = None
        for stratum in (confirmation, prior):
            for baseline in stratum["baselines"].values():
                for field in ("margin", "bootstrap_lower", "lofo_minimum"):
                    baseline[field] = None
        _drop_downstream(evidence)
        self.assertEqual(
            renderer.classify(evidence).branch,
            renderer.OutcomeBranch.A_FAIL,
        )
        self.assertIn("not estimable", renderer.render(evidence))

    def test_zero_support_null_statistics_render_direct_failure(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        differing = evidence["direct_metric_choice"]["differing_winners"]
        differing["tasks"] = 0
        differing["families"] = 0
        differing["coverage_incidence"] = 0
        differing["coverage_comparator"] = 0
        for field in ("mean_improvement", "bootstrap_lower", "lofo_minimum"):
            differing[field] = None
        outcome = renderer.classify(evidence)
        self.assertFalse(outcome.direct_pass)
        self.assertEqual(
            outcome.branch,
            renderer.OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS,
        )
        self.assertIn("not estimable", renderer.render(evidence))

    def test_none_never_passes_an_estimable_gate_clause(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["direct_metric_choice"]["full"]["mean_improvement"] = None
        self.assertFalse(renderer.classify(evidence).direct_pass)

        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["confirmation_b"]["versus_matched"]["bootstrap_lower"] = None
        self.assertFalse(renderer.classify(evidence).b_pass)

    def test_both_a_orientation_gates_are_required(self) -> None:
        for stratum in (None, "all_prior"):
            for field in ("orders_identical", "inverse_u_tied"):
                evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
                target = evidence["confirmation_a"]
                if stratum is not None:
                    target = target[stratum]
                target["orientation"][field] = False
                _drop_downstream(evidence)
                with self.subTest(stratum=stratum or "primary", field=field):
                    self.assertEqual(
                        renderer.classify(evidence).branch,
                        renderer.OutcomeBranch.A_FAIL,
                    )

    def test_direct_audit_certification_is_part_of_the_gate(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["direct_metric_choice"]["audit_certified"] = False
        outcome = renderer.classify(evidence)
        self.assertFalse(outcome.direct_pass)
        self.assertEqual(
            outcome.branch,
            renderer.OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS,
        )

    def test_b_selector_provenance_is_part_of_the_gate(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["confirmation_b"]["selector_provenance_pass"] = False
        outcome = renderer.classify(evidence)
        self.assertFalse(outcome.b_pass)
        self.assertEqual(
            outcome.branch,
            renderer.OutcomeBranch.A_PASS_DIRECT_PASS_B_FAIL,
        )

    def test_all_prior_families_cannot_exceed_tasks(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        prior = evidence["confirmation_a"]["all_prior"]
        prior["comparison_tasks"] = 10
        prior["comparison_families"] = 11
        with self.assertRaisesRegex(renderer.RenderError, "outside its allowed range"):
            renderer.classify(evidence)

    def test_differing_winner_families_cannot_exceed_tasks(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        differing = evidence["direct_metric_choice"]["differing_winners"]
        differing["tasks"] = 10
        differing["families"] = 11
        differing["coverage_incidence"] = 10
        differing["coverage_comparator"] = 9
        with self.assertRaisesRegex(renderer.RenderError, "outside its allowed range"):
            renderer.classify(evidence)

    def test_differing_winner_coverage_cannot_exceed_full_coverage(self) -> None:
        for field in ("coverage_incidence", "coverage_comparator"):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            full = evidence["direct_metric_choice"]["full"]
            differing = evidence["direct_metric_choice"]["differing_winners"]
            full[field] = 1
            differing[field] = 2
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    renderer.RenderError, "exceeds full-cohort coverage"
                ):
                    renderer.classify(evidence)

    def test_b_guided_coverage_must_agree_across_contrasts(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        matched = evidence["confirmation_b"]["versus_matched"]
        matched["coverage_incidence"] = 100
        matched["coverage_comparator"] = 90
        with self.assertRaisesRegex(renderer.RenderError, "guided coverage differs"):
            renderer.classify(evidence)

    def test_atomic_output_helpers_accept_only_safe_canonical_target(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            generated = root / "generated"
            generated.mkdir()
            output = generated / "terminal-incidence-results.tex"
            renderer._write_output_atomic(
                output,
                "first\n",
                expected=output,
                trusted_root=root,
            )
            renderer._check_output(
                output,
                "first\n",
                expected=output,
                trusted_root=root,
            )
            renderer._write_output_atomic(
                output,
                "second\n",
                expected=output,
                trusted_root=root,
            )
            renderer._check_output(
                output,
                "second\n",
                expected=output,
                trusted_root=root,
            )

            alias = generated / ".." / "generated" / output.name
            with self.assertRaisesRegex(renderer.RenderError, "exact canonical"):
                renderer._write_output_atomic(
                    alias,
                    "attack\n",
                    expected=output,
                    trusted_root=root,
                )

    def test_output_helpers_reject_symlink_leaf_and_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            generated = root / "generated"
            generated.mkdir()
            victim = root / "victim.tex"
            victim.write_text("untouched\n", encoding="utf-8")
            output = generated / "terminal-incidence-results.tex"
            output.symlink_to(victim)
            for operation in (
                lambda: renderer._write_output_atomic(
                    output,
                    "attack\n",
                    expected=output,
                    trusted_root=root,
                ),
                lambda: renderer._check_output(
                    output,
                    "untouched\n",
                    expected=output,
                    trusted_root=root,
                ),
            ):
                with self.assertRaisesRegex(renderer.RenderError, "symlink"):
                    operation()
            self.assertEqual(victim.read_text(encoding="utf-8"), "untouched\n")

            output.unlink()
            real_parent = root / "real-parent"
            real_parent.mkdir()
            linked_parent = root / "linked-parent"
            linked_parent.symlink_to(real_parent, target_is_directory=True)
            linked_output = linked_parent / output.name
            with self.assertRaisesRegex(renderer.RenderError, "symlink"):
                renderer._write_output_atomic(
                    linked_output,
                    "attack\n",
                    expected=linked_output,
                    trusted_root=root,
                )

    def test_production_modes_are_disabled_and_do_not_write(self) -> None:
        self.assertTrue(
            all(
                digest == renderer.ZERO_SHA256
                and len(digest) == 64
                and set(digest) == {"0"}
                for digest in renderer.PRODUCTION_DIGEST_PINS.values()
            )
        )
        with self.assertRaisesRegex(renderer.RenderError, "unset digest pins"):
            renderer._load_production_evidence()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "results.tex"
            with contextlib.redirect_stderr(io.StringIO()):
                check_status = renderer.main(
                    ["--check", "--output", str(output)]
                )
            self.assertEqual(check_status, 2)
            self.assertFalse(output.exists())
            with contextlib.redirect_stderr(io.StringIO()):
                write_status = renderer.main(
                    ["--write", "--output", str(output)]
                )
            self.assertEqual(write_status, 2)
            self.assertFalse(output.exists())

    def test_render_is_deterministic_and_does_not_mutate_input(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=False)
        before = copy.deepcopy(evidence)
        self.assertEqual(renderer.render(evidence), renderer.render(evidence))
        self.assertEqual(evidence, before)


if __name__ == "__main__":
    unittest.main()
