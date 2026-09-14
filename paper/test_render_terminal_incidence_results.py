#!/usr/bin/env python3
"""Unit tests for the terminal-incidence result renderer."""

from __future__ import annotations

import copy
import contextlib
import io
import math
import re
import sys
import tempfile
import unittest
from unittest import mock
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_terminal_incidence_results as renderer


EXPECTED_BASELINES = (
    "masked_add_size",
    "value_count",
    "kD",
    "mQ",
    "mJ",
    "cartesian",
    "width",
    "apply",
    "layerwise_min_certificate",
)


def _q(numerator: int, denominator: int = 1) -> dict:
    value = Fraction(numerator, denominator)
    return {"numerator": value.numerator, "denominator": value.denominator}


def _baselines(
    *, pass_gate: bool = True, incidence: Fraction = Fraction(7, 10)
) -> dict:
    margin_value = Fraction(3, 100) if pass_gate else Fraction(19, 1000)
    return {
        name: {
            "concordance": _q(
                (incidence - margin_value).numerator,
                (incidence - margin_value).denominator,
            ),
            "margin": _q(margin_value.numerator, margin_value.denominator),
            "bootstrap_lower": _q(1, 100),
            "bootstrap_upper": _q(1, 20),
            "lofo_minimum": _q(1, 200),
        }
        for name in renderer.BASELINES
    }


def _contrast(
    *,
    pass_gate: bool = True,
    maximum_tasks: int = 300,
    families: int = 32,
    comparator_coverage: int | None = None,
) -> dict:
    incidence_coverage = min(210, maximum_tasks)
    comparator_coverage = (
        min(205, maximum_tasks)
        if comparator_coverage is None
        else comparator_coverage
    )
    both = min(incidence_coverage, comparator_coverage)
    return {
        "coverage_incidence": incidence_coverage,
        "coverage_comparator": comparator_coverage,
        "mean_improvement": _q(3, 100) if pass_gate else _q(19, 1000),
        "bootstrap_lower": _q(1, 100),
        "bootstrap_upper": _q(1, 20),
        "lofo_minimum": _q(1, 200),
        "outcome_decomposition": {
            "both_solved": both,
            "incidence_only_solved": incidence_coverage - both,
            "comparator_only_solved": comparator_coverage - both,
            "neither_solved": (
                maximum_tasks
                - incidence_coverage
                - comparator_coverage
                + both
            ),
            "common_solved_tasks": both,
            "common_solved_families": min(families, both),
            "equal_family_normalized_time_improvement": (
                _q(1, 100) if both else None
            ),
        },
    }


def _predictor_values(value: Fraction = Fraction(7, 10)) -> dict:
    return {
        name: _q(value.numerator, value.denominator)
        for name in renderer.ORDERING_PREDICTORS
    }


def _oracle_regret() -> dict:
    return {
        "tasks": 300,
        "families": 25,
        "predictors": {
            name: {
                "equal_family_regret": _q(1, 10),
                "tie_rate": _q(1, 20),
            }
            for name in renderer.ORDERING_PREDICTORS
        },
    }


def _tightness() -> dict:
    return {
        "tasks": 310,
        "families": 25,
        "predictors": {
            name: {
                "equal_family": _q(3, 4),
                "q25": _q(1, 2),
                "q50": _q(3, 4),
                "q75": _q(9, 10),
            }
            for name in renderer.CERTIFICATE_PREDICTORS
        },
    }


def _direct_mechanism() -> dict:
    return {
        "structural_identity_pass": True,
        "work_counts_match": True,
        "same_candidate_tasks": 240,
        "same_pattern_different_cap_tasks": 35,
        "different_pattern_tasks": 15,
        "score_higher_tasks": 25,
        "score_tied_tasks": 15,
        "score_lower_tasks": 10,
        "incidence_own_utilization": _q(4, 5),
        "mj_own_utilization": _q(3, 4),
        "incidence_binding_tasks": 100,
        "mj_binding_tasks": 90,
        "incidence_under_mj_budget_tasks": 250,
        "mj_under_incidence_budget_tasks": 240,
        "candidate_work": {
            name: _q(10) for name in renderer.DIRECT_WORK_FIELDS
        },
        "incidence_minus_mj_cpu_seconds": _q(-1, 10),
        "incidence_minus_mj_wall_seconds": _q(-1, 20),
        "incidence_minus_matched_cpu_seconds": _q(1, 10),
        "incidence_minus_matched_wall_seconds": _q(1, 20),
    }


def _b_configurations() -> dict:
    return {
        name: {
            "coverage": 210 if name == "incidence_guided" else (
                205 if name in {"cap_aware_k32", "matched_work"} else 200
            ),
            "par2_sum_seconds": _q(600000),
            "par2_mean_seconds": _q(2000),
            "equal_family_mean_par2_seconds": _q(2100),
        }
        for name in renderer.B_CONFIGURATIONS
    }


def _b_overhead() -> dict:
    return {name: _q(1, 10) for name in renderer.B_OVERHEAD_FIELDS}


def _as_fraction(record: dict) -> Fraction:
    return Fraction(record["numerator"], record["denominator"])


def _set_baseline_margin(target: dict, name: str, margin: Fraction) -> None:
    incidence = _as_fraction(target["i_concordance"])
    target["baselines"][name]["margin"] = _q(
        margin.numerator, margin.denominator
    )
    concordance = incidence - margin
    target["baselines"][name]["concordance"] = _q(
        concordance.numerator, concordance.denominator
    )


def _set_incidence_concordance(target: dict, value: Fraction) -> None:
    target["i_concordance"] = _q(value.numerator, value.denominator)
    for result in target["baselines"].values():
        margin = _as_fraction(result["margin"])
        concordance = value - margin
        result["concordance"] = _q(
            concordance.numerator, concordance.denominator
        )


def _set_contrast_coverage(
    contrast: dict, incidence: int, comparator: int
) -> None:
    decomposition = contrast["outcome_decomposition"]
    tasks = sum(
        decomposition[field]
        for field in (
            "both_solved",
            "incidence_only_solved",
            "comparator_only_solved",
            "neither_solved",
        )
    )
    both = min(incidence, comparator)
    contrast["coverage_incidence"] = incidence
    contrast["coverage_comparator"] = comparator
    decomposition.update({
        "both_solved": both,
        "incidence_only_solved": incidence - both,
        "comparator_only_solved": comparator - both,
        "neither_solved": tasks - incidence - comparator + both,
        "common_solved_tasks": both,
        "common_solved_families": min(
            decomposition["common_solved_families"], both
        ),
        "equal_family_normalized_time_improvement": (
            _q(1, 100) if both else None
        ),
    })


def fixture(*, a_pass: bool, direct_pass: bool | None, b_pass: bool | None) -> dict:
    if not a_pass and (direct_pass is not None or b_pass is not None):
        raise ValueError("a failed fixture cannot contain downstream outcomes")
    if a_pass and (direct_pass is None or b_pass is None):
        raise ValueError("a passing fixture requires both downstream outcomes")
    a_incidence = Fraction(7, 10) if a_pass else Fraction(16, 25)
    prior_incidence = Fraction(17, 25)
    evidence = {
        "source_audit": {
            "sealed": True,
            "campaign_number": 12,
            "inventory_candidates": 1640,
            "candidates": 1640,
            "inventory_families": 40,
            "translation_attempts": 1640,
            "translated_successfully": 1500,
            "translation_status_counts": {
                "success": 1500, "input_rejected": 120, "resource_excluded": 20,
            },
            "supported_tasks": 1400,
            "unsupported_tasks": 220,
            "indeterminate_tasks": 20,
            "unassigned_supported_tasks": 450,
            "reason_incidence_counts": {
                "translation_input_rejected": 120,
                "no_serialized_operators": 40,
                "nonpositive_serialized_operator_cost": 30,
                "serialized_axioms": 20,
                "serialized_conditional_effects": 10,
                "normalized_axioms": 20,
            },
            "resource_exclusion_counts": {"memory": 10, "time": 10},
            "resource_exclusions_by_family": {
                "freecell": {"memory": 10, "time": 10},
            },
            "logical_shards": 820,
            "whole_campaign_rerun": True,
            "prior_campaign_shards_reused": 0,
            "time_limit_seconds": 1800,
            "memory_limit_mib": 24576,
            "source_chain_verified": True,
            "environment_verified": True,
            "scheduler_verified": True,
            "cohort_disjoint": True,
            "a_tasks": 650,
            "a_families": 30,
            "a_shadow_tasks": 200,
            "a_shadow_families": 14,
            "a_prior_tasks": 120,
            "a_prior_families": 12,
            "b_tasks": 300,
            "b_families": 32,
            "b_shadow_tasks": 100,
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
            "i_concordance": _q(a_incidence.numerator, a_incidence.denominator),
            "baselines": _baselines(incidence=a_incidence),
            "orientation": {
                "orders_identical": True,
                "inverse_u_tied": True,
            },
            "all_prior": {
                "comparison_tasks": 60,
                "comparison_families": 10,
                "target_strict_pairs": 120,
                "i_concordance": _q(
                    prior_incidence.numerator, prior_incidence.denominator
                ),
                "baselines": _baselines(incidence=prior_incidence),
                "orientation": {
                    "orders_identical": True,
                    "inverse_u_tied": True,
                },
            },
            "all_strict": {
                "comparison_tasks": 300,
                "comparison_families": 25,
                "pairs": 500,
                "predictors": _predictor_values(),
            },
            "oracle_regret": _oracle_regret(),
            "certificate_tightness": _tightness(),
            "timing": {
                "cells": 1200,
                "tasks": 310,
                "tasks_with_positive_partition_time": 300,
                "families_with_positive_partition_time": 25,
                "pooled_masked_seconds": _q(1000),
                "pooled_partition_audit_seconds": _q(2000),
                "pooled_masked_over_partition_ratio": _q(1, 2),
                "equal_family_mean_of_task_ratios": _q(3, 5),
            },
            "frontier_statuses": {
                name: (320 if name == "eligible" else 330 if name ==
                       "insufficient_completed_layers" else 0)
                for name in renderer.A_FRONTIER_STATUSES
            },
            "construction_by_configuration": {
                name: {"completed": 600, "failed": 40, "absent": 10}
                for name in renderer.A_CONSTRUCTION_CONFIGURATIONS
            },
            "cegar_fallback_tasks": 25,
        },
        "hardware": {
            "a": {
                "receipt_sealed": True,
                "cells": 2600,
                "processor_models": 1,
                "architectures": 1,
            },
            "direct": None,
            "b": None,
        },
    }
    if a_pass:
        evidence["direct_metric_choice"] = {
            "sealed": True,
            "audit_certified": True,
            "tasks": 300,
            "families": 32,
            "probe_support": {
                "complete_tasks": 290,
                "short_probe_tasks": 10,
                "complete_families": 32,
                "short_probe_families": 8,
            },
            "full": _contrast(pass_gate=bool(direct_pass)),
            "differing_winners": {
                "tasks": 50,
                "families": 12,
                **_contrast(
                    pass_gate=bool(direct_pass),
                    maximum_tasks=50,
                    families=12,
                ),
            },
            "secondary_vs_matched": _contrast(),
            "mechanism": _direct_mechanism(),
        }
        evidence["confirmation_b"] = {
            "sealed": True,
            "selector_provenance_pass": True,
            "tasks": 300,
            "families": 32,
            "complete_pairs": 290,
            "short_probe_pairs": 10,
            "failed_pairs": 0,
            "selected_difference_tasks": 60,
            "reference_identity_pass": True,
            "versus_reference": _contrast(pass_gate=bool(b_pass)),
            "versus_matched": _contrast(pass_gate=bool(b_pass)),
            "alternatives": {
                name: _contrast(
                    comparator_coverage=(
                        205 if name in {"cap_aware_k32", "matched_work"} else 200
                    )
                )
                for name in renderer.B_ALTERNATIVES
            },
            "configurations": _b_configurations(),
            "mechanism": {
                "tasks": 60,
                "families": 12,
                "claim_authorized": True,
                "versus_matched": _contrast(
                    pass_gate=True, maximum_tasks=60, families=12
                ),
            },
            "overhead": _b_overhead(),
        }
        evidence["hardware"]["direct"] = {
            "receipt_sealed": True,
            "cells": 900,
            "processor_models": 1,
            "architectures": 1,
        }
        evidence["hardware"]["b"] = {
            "receipt_sealed": True,
            "cells": 2700,
            "processor_models": 1,
            "architectures": 1,
        }
    return evidence


def _drop_downstream(evidence: dict) -> None:
    del evidence["direct_metric_choice"]
    del evidence["confirmation_b"]
    evidence["hardware"]["direct"] = None
    evidence["hardware"]["b"] = None


class RendererTests(unittest.TestCase):
    def test_baseline_schema_is_the_registered_nine(self) -> None:
        self.assertEqual(renderer.BASELINES, EXPECTED_BASELINES)
        self.assertEqual(len(renderer.BASELINE_TEX_LABELS), len(EXPECTED_BASELINES))

    def test_original_five_terminal_branches_are_preserved(self) -> None:
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
        self.assertEqual(len(set(renderer.OutcomeBranch) - {
            renderer.OutcomeBranch.A_PASS_SELECTORS_UNTESTED}), 5)
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

    def test_exact_fixed_macro_interface(self) -> None:
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
                "TIOutcomeAPredictorRows",
                "TIOutcomeADiagnosticRows",
                "TIOutcomeAConstructionRows",
                "TIOutcomeAFrontierRows",
                "TIOutcomeATimingRows",
                "TIOutcomeMetricChoice",
                "TIOutcomeMetricMechanismRows",
                "TIOutcomeMetricOutcomeRows",
                "TIOutcomeB",
                "TIOutcomeBConfigurationRows",
                "TIOutcomeBAlternativeRows",
                "TIOutcomeBOutcomeRows",
                "TIOutcomeBOverheadRows",
                "TIOutcomeConclusion",
                "TIOutcomeSourceAudit",
                "TIOutcomeSourceExclusionRows",
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

    def test_source_reason_schemas_are_exact_and_conservative(self) -> None:
        self.assertEqual(
            renderer.SOURCE_EXCLUSION_CATEGORIES,
            (
                "translation_input_rejected",
                "no_serialized_operators",
                "nonpositive_serialized_operator_cost",
                "serialized_axioms",
                "serialized_conditional_effects",
                "normalized_axioms",
            ),
        )
        renderer.classify(fixture(a_pass=True, direct_pass=True, b_pass=True))
        for field in ("reason_incidence_counts",):
            for mutation in ("missing", "extra"):
                evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
                counts = evidence["source_audit"][field]
                if mutation == "missing":
                    del counts["normalized_axioms"]
                else:
                    counts["unknown_reason"] = 0
                with self.subTest(field=field, mutation=mutation):
                    with self.assertRaisesRegex(renderer.RenderError, "schema mismatch"):
                        renderer.classify(evidence)

    def test_source_translation_support_and_resource_conservation(self) -> None:
        mutations = (
            ("translation_status_counts", "success", 1499),
            ("translation_status_counts", "input_rejected", 119),
            ("translation_status_counts", "resource_excluded", 19),
            ("reason_incidence_counts", "translation_input_rejected", 119),
            ("resource_exclusion_counts", "time", 9),
        )
        for section, field, value in mutations:
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            evidence["source_audit"][section][field] = value
            with self.subTest(section=section, field=field):
                with self.assertRaises(renderer.RenderError):
                    renderer.classify(evidence)
        for field in (
            "supported_tasks", "unsupported_tasks", "indeterminate_tasks",
            "unassigned_supported_tasks",
        ):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            evidence["source_audit"][field] -= 1
            with self.subTest(field=field):
                with self.assertRaisesRegex(renderer.RenderError, "does not authorize"):
                    renderer.classify(evidence)

    def test_source_reason_category_bounds_fail_closed(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["source_audit"]["reason_incidence_counts"]["normalized_axioms"] = 221
        with self.assertRaisesRegex(renderer.RenderError, "outside its allowed range"):
            renderer.classify(evidence)

    def test_source_resource_family_census_is_conserved(self) -> None:
        for changed in (
            {},
            {"freecell": {"memory": 9, "time": 10}},
            {"freecell": {"memory": 10, "time": 10}, "blocks": {"memory": 0, "time": 0}},
            {"freecell": {"memory": 10, "time": True}},
            {"freecell": {"memory": 10, "time": 10, "extra": 0}},
        ):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            evidence["source_audit"]["resource_exclusions_by_family"] = changed
            with self.subTest(changed=changed):
                with self.assertRaises(renderer.RenderError):
                    renderer.classify(evidence)

    def test_source_v12_contract_is_required(self) -> None:
        for field, invalid in (
            ("campaign_number", 11), ("logical_shards", 819),
            ("whole_campaign_rerun", False), ("prior_campaign_shards_reused", 1),
            ("time_limit_seconds", 1801), ("memory_limit_mib", 24575),
            ("source_chain_verified", False), ("environment_verified", False),
            ("scheduler_verified", False), ("cohort_disjoint", False),
        ):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            evidence["source_audit"][field] = invalid
            with self.subTest(field=field):
                with self.assertRaisesRegex(renderer.RenderError, "does not authorize"):
                    renderer.classify(evidence)
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["source_audit"]["reusable_v5_shard_indices"] = []
        with self.assertRaisesRegex(renderer.RenderError, "schema mismatch"):
            renderer.classify(evidence)

    def test_a_gate_boundary_is_recomputed(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        _set_baseline_margin(
            evidence["confirmation_a"], "mJ", Fraction(19, 1000)
        )
        _drop_downstream(evidence)
        self.assertEqual(
            renderer.classify(evidence).branch,
            renderer.OutcomeBranch.A_FAIL,
        )

    def test_layerwise_min_certificate_controls_both_a_gates(self) -> None:
        for section in ("primary", "all_prior"):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            target = evidence["confirmation_a"]
            if section == "all_prior":
                target = target["all_prior"]
            _set_baseline_margin(
                target, "layerwise_min_certificate", Fraction(19, 1000)
            )
            _drop_downstream(evidence)
            with self.subTest(section=section):
                self.assertEqual(
                    renderer.classify(evidence).branch,
                    renderer.OutcomeBranch.A_FAIL,
                )

    def test_layerwise_min_certificate_is_required_by_both_a_schemas(self) -> None:
        for section in ("primary", "all_prior"):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            target = evidence["confirmation_a"]
            if section == "all_prior":
                target = target["all_prior"]
            del target["baselines"]["layerwise_min_certificate"]
            with self.subTest(section=section):
                    with self.assertRaisesRegex(renderer.RenderError, "schema mismatch"):
                        renderer.classify(evidence)

    def test_value_count_is_registered_gating_and_not_a_certificate(self) -> None:
        self.assertEqual(
            renderer.BASELINES[:2], ("masked_add_size", "value_count")
        )
        self.assertNotIn("value_count", renderer.CERTIFICATE_PREDICTORS)
        for section in ("primary", "all_prior"):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            target = evidence["confirmation_a"]
            if section == "all_prior":
                target = target["all_prior"]
            _set_baseline_margin(target, "value_count", Fraction(19, 1000))
            _drop_downstream(evidence)
            with self.subTest(section=section):
                self.assertEqual(
                    renderer.classify(evidence).branch,
                    renderer.OutcomeBranch.A_FAIL,
                )

    def test_value_count_is_required_and_rendered_in_registered_order(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["confirmation_a"]["all_strict"]["predictors"][
            "value_count"
        ] = _q(11, 20)
        evidence["confirmation_a"]["oracle_regret"]["predictors"][
            "value_count"
        ]["equal_family_regret"] = _q(7, 100)
        output = renderer.render(evidence)
        self.assertIn(r"$\sum_g k_g$ & 0.5500 & 0.0700", output)
        self.assertNotIn("value_count", evidence["confirmation_a"][
            "certificate_tightness"
        ]["predictors"])
        for section in ("primary", "all_prior"):
            changed = fixture(a_pass=True, direct_pass=True, b_pass=True)
            target = changed["confirmation_a"]
            if section == "all_prior":
                target = target["all_prior"]
            del target["baselines"]["value_count"]
            with self.subTest(section=section):
                with self.assertRaisesRegex(renderer.RenderError, "schema mismatch"):
                    renderer.classify(changed)
        changed = fixture(a_pass=True, direct_pass=True, b_pass=True)
        changed["confirmation_a"]["certificate_tightness"]["predictors"][
            "value_count"
        ] = {
            "equal_family": _q(1), "q25": _q(1),
            "q50": _q(1), "q75": _q(1),
        }
        with self.assertRaisesRegex(renderer.RenderError, "schema mismatch"):
            renderer.classify(changed)

    def test_a_render_reports_each_registered_baseline_in_order(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        output = renderer.render(evidence)
        labels = ", ".join(renderer.BASELINE_TEX_LABELS)
        self.assertIn(labels, output)
        self.assertIn("$B_\\wedge$", output)
        self.assertEqual(output.count("margin/bootstrap-interval/"), 1)
        self.assertEqual(
            output.count("(0.0300/[0.0100,0.0500]/0.0050)"), 18
        )

    def test_a_attrition_and_full_timing_panel_are_rendered_and_conserved(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        output = renderer.render(evidence)
        self.assertIn("BDD-prefix & 600 & 40 & 10", output)
        self.assertIn("insufficient completed layers & 330", output)
        for fragment in (
            "measured cells & 1200",
            "measured tasks & 310",
            "tasks with positive exact-partition time & 300",
            "families with positive exact-partition time & 25",
            "pooled masked seconds & 1000.0000",
            "pooled exact-partition seconds & 2000.0000",
            "pooled masked/exact-partition ratio & 0.5000",
            "equal-family mean task ratio & 0.6000",
        ):
            self.assertIn(fragment, output)

        changed = fixture(a_pass=True, direct_pass=True, b_pass=True)
        changed["confirmation_a"]["construction_by_configuration"][
            "cegar"
        ]["absent"] = 9
        with self.assertRaisesRegex(renderer.RenderError, "every A construction"):
            renderer.classify(changed)

        changed = fixture(a_pass=True, direct_pass=True, b_pass=True)
        changed["confirmation_a"]["timing"][
            "pooled_masked_over_partition_ratio"
        ] = _q(2, 3)
        with self.assertRaisesRegex(renderer.RenderError, "ratio is inconsistent"):
            renderer.classify(changed)

    def test_a_fraction_panels_have_exact_support_dependent_null_patterns(self) -> None:
        for section in ("primary", "all_prior"):
            for field in ("bootstrap_lower", "bootstrap_upper", "lofo_minimum"):
                evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
                target = evidence["confirmation_a"]
                if section == "all_prior":
                    target = target["all_prior"]
                target["baselines"]["value_count"][field] = None
                with self.subTest(section=section, field=field):
                    with self.assertRaisesRegex(renderer.RenderError, "incomplete"):
                        renderer.classify(evidence)

        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        tightness = evidence["confirmation_a"]["certificate_tightness"][
            "predictors"
        ]["incidence"]
        tightness["q50"] = None
        with self.assertRaisesRegex(renderer.RenderError, "incomplete"):
            renderer.classify(evidence)

        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        tightness = evidence["confirmation_a"]["certificate_tightness"][
            "predictors"
        ]["incidence"]
        tightness["q25"] = _q(4, 5)
        with self.assertRaisesRegex(renderer.RenderError, "quantiles are unordered"):
            renderer.classify(evidence)

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
            if keys == ("baselines", "mJ", "margin"):
                _set_baseline_margin(
                    evidence["confirmation_a"],
                    "mJ",
                    _as_fraction(value),
                )
                _drop_downstream(evidence)
                with self.subTest(keys=keys):
                    self.assertEqual(
                        renderer.classify(evidence).branch,
                        renderer.OutcomeBranch.A_FAIL,
                    )
                continue
            if keys == ("i_concordance",):
                _set_incidence_concordance(
                    evidence["confirmation_a"], _as_fraction(value)
                )
                _drop_downstream(evidence)
                with self.subTest(keys=keys):
                    self.assertEqual(
                        renderer.classify(evidence).branch,
                        renderer.OutcomeBranch.A_FAIL,
                    )
                continue
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
        _set_incidence_concordance(
            evidence["confirmation_a"], Fraction(13, 20)
        )
        _set_incidence_concordance(
            evidence["confirmation_a"]["all_prior"], Fraction(13, 20)
        )
        _set_baseline_margin(evidence["confirmation_a"], "mJ", Fraction(1, 50))
        _set_baseline_margin(
            evidence["confirmation_a"]["all_prior"], "mJ", Fraction(1, 50)
        )
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
        confirmation["all_strict"] = {
            "comparison_tasks": 0,
            "comparison_families": 0,
            "pairs": 0,
            "predictors": {
                name: None for name in renderer.ORDERING_PREDICTORS
            },
        }
        prior = confirmation["all_prior"]
        prior["comparison_tasks"] = 0
        prior["comparison_families"] = 0
        prior["target_strict_pairs"] = 0
        prior["i_concordance"] = None
        for stratum in (confirmation, prior):
            for baseline in stratum["baselines"].values():
                for field in (
                    "concordance",
                    "margin",
                    "bootstrap_lower",
                    "bootstrap_upper",
                    "lofo_minimum",
                ):
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
        for field in (
            "mean_improvement",
            "bootstrap_lower",
            "bootstrap_upper",
            "lofo_minimum",
        ):
            differing[field] = None
        differing["outcome_decomposition"] = {
            "both_solved": 0,
            "incidence_only_solved": 0,
            "comparator_only_solved": 0,
            "neither_solved": 0,
            "common_solved_tasks": 0,
            "common_solved_families": 0,
            "equal_family_normalized_time_improvement": None,
        }
        mechanism = evidence["direct_metric_choice"]["mechanism"]
        mechanism["same_candidate_tasks"] = 290
        mechanism["same_pattern_different_cap_tasks"] = 0
        mechanism["different_pattern_tasks"] = 0
        mechanism["score_higher_tasks"] = 0
        mechanism["score_tied_tasks"] = 0
        mechanism["score_lower_tasks"] = 0
        outcome = renderer.classify(evidence)
        self.assertFalse(outcome.direct_pass)
        self.assertEqual(
            outcome.branch,
            renderer.OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS,
        )
        self.assertIn("not estimable", renderer.render(evidence))

    def test_positive_support_rejects_missing_registered_statistics(self) -> None:
        selectors = (
            lambda evidence: evidence["direct_metric_choice"]["full"],
            lambda evidence: evidence["direct_metric_choice"][
                "differing_winners"
            ],
            lambda evidence: evidence["direct_metric_choice"][
                "secondary_vs_matched"
            ],
            lambda evidence: evidence["confirmation_b"]["versus_reference"],
            lambda evidence: evidence["confirmation_b"]["versus_matched"],
            lambda evidence: evidence["confirmation_b"]["mechanism"][
                "versus_matched"
            ],
            lambda evidence: evidence["confirmation_b"]["alternatives"][
                "blind"
            ],
        )
        for index, select in enumerate(selectors):
            for field in (
                "mean_improvement",
                "bootstrap_lower",
                "bootstrap_upper",
                "lofo_minimum",
            ):
                evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
                select(evidence)[field] = None
                with self.subTest(panel=index, field=field):
                    with self.assertRaisesRegex(renderer.RenderError, "incomplete"):
                        renderer.classify(evidence)

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
        evidence["confirmation_b"]["complete_pairs"] = 289
        evidence["confirmation_b"]["failed_pairs"] = 1
        evidence["confirmation_b"]["mechanism"]["claim_authorized"] = False
        outcome = renderer.classify(evidence)
        self.assertFalse(outcome.b_pass)
        self.assertEqual(
            outcome.branch,
            renderer.OutcomeBranch.A_PASS_DIRECT_PASS_B_FAIL,
        )
        evidence["confirmation_b"]["selector_provenance_pass"] = True
        with self.assertRaisesRegex(renderer.RenderError, "provenance is inconsistent"):
            renderer.classify(evidence)

    def test_b_mechanism_authorization_is_recomputed_independently(self) -> None:
        for provenance in (False, True):
            for support_pass in (False, True):
                for contrast_pass in (False, True):
                    for overall_identity_pass in (False, True):
                        evidence = fixture(
                            a_pass=True, direct_pass=True, b_pass=True
                        )
                        confirmation = evidence["confirmation_b"]
                        confirmation["selector_provenance_pass"] = provenance
                        if not provenance:
                            confirmation["complete_pairs"] = 289
                            confirmation["failed_pairs"] = 1
                        confirmation["reference_identity_pass"] = overall_identity_pass
                        mechanism = confirmation["mechanism"]
                        mechanism_tasks = 60 if support_pass else 40
                        mechanism_families = 12 if support_pass else 9
                        confirmation["selected_difference_tasks"] = mechanism_tasks
                        mechanism.update({
                            "tasks": mechanism_tasks,
                            "families": mechanism_families,
                            "versus_matched": _contrast(
                                pass_gate=contrast_pass,
                                maximum_tasks=mechanism_tasks,
                                families=mechanism_families,
                            ),
                        })
                        expected_claim = (
                            provenance and support_pass and contrast_pass
                        )
                        mechanism["claim_authorized"] = expected_claim
                        with self.subTest(
                            provenance=provenance,
                            support=support_pass,
                            contrast=contrast_pass,
                            overall_identity=overall_identity_pass,
                        ):
                            outcome = renderer.classify(evidence)
                            self.assertEqual(
                                outcome.b_pass,
                                provenance and overall_identity_pass,
                            )
                            mechanism["claim_authorized"] = not expected_claim
                            with self.assertRaisesRegex(
                                renderer.RenderError,
                                "mechanism authorization is inconsistent",
                            ):
                                renderer.classify(evidence)

    def test_b_mechanism_can_be_authorized_when_overall_gate_fails(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=False)
        outcome = renderer.classify(evidence)
        self.assertFalse(outcome.b_pass)
        self.assertTrue(evidence["confirmation_b"]["mechanism"][
            "claim_authorized"
        ])
        self.assertIn("conditional claim was authorized", renderer.render(evidence))

    def test_b_all_six_alternatives_are_validated_rendered_and_non_gating(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        self.assertEqual(set(evidence["confirmation_b"]["alternatives"]), set(
            renderer.B_ALTERNATIVES
        ))
        evidence["confirmation_b"]["alternatives"]["blind"][
            "mean_improvement"
        ] = _q(-1, 10)
        outcome = renderer.classify(evidence)
        self.assertTrue(outcome.b_pass)
        output = renderer.render(evidence)
        for label in renderer.B_CONFIGURATION_TEX_LABELS[:6]:
            self.assertIn(f"{label} & 210/200", output)

        del evidence["confirmation_b"]["alternatives"]["blind"]
        with self.assertRaisesRegex(renderer.RenderError, "schema mismatch"):
            renderer.classify(evidence)

    def test_b_configuration_schema_is_exactly_all_nine_arms(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        self.assertEqual(
            tuple(evidence["confirmation_b"]["configurations"]),
            renderer.B_CONFIGURATIONS,
        )
        self.assertEqual(len(renderer.B_CONFIGURATIONS), 9)
        del evidence["confirmation_b"]["configurations"]["goal_fill"]
        with self.assertRaisesRegex(renderer.RenderError, "schema mismatch"):
            renderer.classify(evidence)

    def test_b_par2_means_are_exact_bounded_and_clearly_labelled(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        output = renderer.render(evidence)
        self.assertIn("exact task-mean PAR2 (sealed PAR2 sum divided by 300)", output)
        self.assertIn("blind & 200 & 2000.0000 & 2100.0000", output)
        for field, value, message in (
            ("par2_mean_seconds", _q(1999), "sum/tasks"),
            ("equal_family_mean_par2_seconds", _q(3601), "allowed range"),
        ):
            changed = fixture(a_pass=True, direct_pass=True, b_pass=True)
            changed["confirmation_b"]["configurations"]["blind"][field] = value
            with self.subTest(field=field):
                with self.assertRaisesRegex(renderer.RenderError, message):
                    renderer.classify(changed)
        changed = fixture(a_pass=True, direct_pass=True, b_pass=True)
        configuration = changed["confirmation_b"]["configurations"]["blind"]
        configuration["par2_sum_seconds"] = _q(1)
        configuration["par2_mean_seconds"] = _q(1, 300)
        with self.assertRaisesRegex(renderer.RenderError, "incompatible with coverage"):
            renderer.classify(changed)

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

    def test_differing_winner_support_equals_mechanism_taxonomy(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["direct_metric_choice"]["mechanism"][
            "same_pattern_different_cap_tasks"
        ] -= 1
        evidence["direct_metric_choice"]["mechanism"][
            "same_candidate_tasks"
        ] += 1
        with self.assertRaisesRegex(renderer.RenderError, "disagrees with change taxonomy"):
            renderer.classify(evidence)

    def test_differing_winner_families_are_bounded_by_complete_families(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        evidence["direct_metric_choice"]["probe_support"][
            "complete_families"
        ] = 11
        with self.assertRaisesRegex(renderer.RenderError, "outside its allowed range"):
            renderer.classify(evidence)

    def test_direct_render_includes_differing_and_matched_full_panels(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        secondary = evidence["direct_metric_choice"]["secondary_vs_matched"]
        secondary["mean_improvement"] = _q(7, 100)
        secondary["bootstrap_lower"] = _q(1, 50)
        secondary["bootstrap_upper"] = _q(9, 100)
        secondary["lofo_minimum"] = _q(1, 100)
        output = renderer.render(evidence)
        self.assertIn("incidence/developmental coverages were 50/50", output)
        self.assertIn(
            "incidence/matched coverages, improvement, bootstrap interval", output
        )
        self.assertIn("210/205, 0.0700, [0.0200, 0.0900] and 0.0100", output)
        self.assertIn("full: incidence vs. matched", output)

    def test_single_family_contrast_uses_exact_lofo_null_pattern(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        differing = evidence["direct_metric_choice"]["differing_winners"]
        differing.clear()
        differing.update({
            "tasks": 1,
            "families": 1,
            **_contrast(maximum_tasks=1, families=1),
        })
        differing["lofo_minimum"] = None
        mechanism = evidence["direct_metric_choice"]["mechanism"]
        mechanism.update({
            "same_candidate_tasks": 289,
            "same_pattern_different_cap_tasks": 1,
            "different_pattern_tasks": 0,
            "score_higher_tasks": 1,
            "score_tied_tasks": 0,
            "score_lower_tasks": 0,
        })
        outcome = renderer.classify(evidence)
        self.assertFalse(outcome.direct_pass)

        differing["lofo_minimum"] = _q(0)
        with self.assertRaisesRegex(renderer.RenderError, "must be null"):
            renderer.classify(evidence)

    def test_differing_winner_coverage_cannot_exceed_full_coverage(self) -> None:
        for field in ("coverage_incidence", "coverage_comparator"):
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            full = evidence["direct_metric_choice"]["full"]
            differing = evidence["direct_metric_choice"]["differing_winners"]
            if field == "coverage_incidence":
                _set_contrast_coverage(full, 1, full["coverage_comparator"])
                _set_contrast_coverage(
                    differing, 2, differing["coverage_comparator"]
                )
            else:
                _set_contrast_coverage(full, full["coverage_incidence"], 1)
                _set_contrast_coverage(
                    differing, differing["coverage_incidence"], 2
                )
            with self.subTest(field=field):
                with self.assertRaisesRegex(
                    renderer.RenderError, "exceeds full-cohort coverage"
                ):
                    renderer.classify(evidence)

    def test_b_guided_coverage_must_agree_across_contrasts(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        matched = evidence["confirmation_b"]["versus_matched"]
        _set_contrast_coverage(matched, 100, 90)
        with self.assertRaisesRegex(renderer.RenderError, "guided coverage differs"):
            renderer.classify(evidence)

    def test_outcome_decompositions_are_exact_for_direct_and_b(self) -> None:
        paths = (
            ("direct", "full"),
            ("direct", "differing_winners"),
            ("direct", "secondary_vs_matched"),
            ("b", "versus_reference"),
            ("b", "versus_matched"),
            ("b", "mechanism"),
            ("b", "alternative"),
        )
        for owner, name in paths:
            evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
            if owner == "direct":
                contrast = evidence["direct_metric_choice"][name]
            elif name == "mechanism":
                contrast = evidence["confirmation_b"]["mechanism"][
                    "versus_matched"
                ]
            elif name == "alternative":
                contrast = evidence["confirmation_b"]["alternatives"]["blind"]
            else:
                contrast = evidence["confirmation_b"][name]
            contrast["outcome_decomposition"]["neither_solved"] += 1
            with self.subTest(owner=owner, name=name):
                with self.assertRaisesRegex(renderer.RenderError, "2x2 counts"):
                    renderer.classify(evidence)

        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        decomposition = evidence["confirmation_b"]["versus_reference"][
            "outcome_decomposition"
        ]
        decomposition["common_solved_tasks"] -= 1
        with self.assertRaisesRegex(renderer.RenderError, "common-solved support"):
            renderer.classify(evidence)

        evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
        decomposition = evidence["confirmation_b"]["versus_reference"][
            "outcome_decomposition"
        ]
        decomposition["equal_family_normalized_time_improvement"] = None
        with self.assertRaisesRegex(renderer.RenderError, "incomplete"):
            renderer.classify(evidence)

    def test_all_common_solved_equal_family_values_are_bounded(self) -> None:
        selectors = (
            lambda evidence: evidence["direct_metric_choice"]["full"],
            lambda evidence: evidence["direct_metric_choice"][
                "differing_winners"
            ],
            lambda evidence: evidence["direct_metric_choice"][
                "secondary_vs_matched"
            ],
            lambda evidence: evidence["confirmation_b"]["versus_reference"],
            lambda evidence: evidence["confirmation_b"]["versus_matched"],
            lambda evidence: evidence["confirmation_b"]["mechanism"][
                "versus_matched"
            ],
            lambda evidence: evidence["confirmation_b"]["alternatives"][
                "blind"
            ],
        )
        for index, select in enumerate(selectors):
            for value in (Fraction(-1001, 1000), Fraction(1001, 1000)):
                evidence = fixture(a_pass=True, direct_pass=True, b_pass=True)
                select(evidence)["outcome_decomposition"][
                    "equal_family_normalized_time_improvement"
                ] = _q(value.numerator, value.denominator)
                with self.subTest(panel=index, value=value):
                    with self.assertRaisesRegex(
                        renderer.RenderError, "outside its allowed range"
                    ):
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
        import within_family_evidence as Within

        self.assertIsNone(renderer.PRODUCTION_EXPECTED_A_PASS)
        self.assertEqual(
            renderer.PRODUCTION_DIGEST_PINS,
            {
                "source_audit": renderer.ZERO_SHA256,
                "confirmation_a": renderer.ZERO_SHA256,
                "direct_metric_choice": None,
                "confirmation_b": None,
            },
        )
        with mock.patch.object(Within, "PRODUCTION_RESULTS_REVISION", None), \
                mock.patch.object(Within, "PRODUCTION_ARTIFACT_PINS", {}):
            with self.assertRaisesRegex(renderer.RenderError, "outcome branch is unset"):
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

    def test_production_pin_contract_is_branch_exact(self) -> None:
        digest = "1" * 64
        common = {
            "source_audit": digest,
            "confirmation_a": digest,
            "direct_metric_choice": None,
            "confirmation_b": None,
        }
        renderer._validate_production_pin_contract(common, False)
        with self.assertRaisesRegex(renderer.RenderError, "exact downstream absence"):
            renderer._validate_production_pin_contract(
                {**common, "direct_metric_choice": digest}, False
            )
        passing = {
            **common,
            "direct_metric_choice": digest,
            "confirmation_b": digest,
        }
        renderer._validate_production_pin_contract(passing, True)
        with self.assertRaisesRegex(renderer.RenderError, "passing A requires"):
            renderer._validate_production_pin_contract(common, True)

    def test_a_failure_requires_exact_downstream_hardware_absence(self) -> None:
        evidence = fixture(a_pass=False, direct_pass=None, b_pass=None)
        evidence["hardware"]["direct"] = {
            "receipt_sealed": True,
            "cells": 900,
            "processor_models": 1,
            "architectures": 1,
        }
        with self.assertRaisesRegex(renderer.RenderError, "exact downstream"):
            renderer.classify(evidence)

    def test_threshold_formatting_never_rounds_across_a_gate(self) -> None:
        below = Fraction(19999999999999999, 10**18)
        rendered = renderer._fmt(below, threshold=Fraction(1, 50))
        self.assertGreaterEqual(len(rendered.split(".")[-1]), 4)
        self.assertLess(Fraction(rendered), Fraction(1, 50))
        self.assertEqual(
            renderer._fmt(Fraction(1, 50), threshold=Fraction(1, 50)),
            "0.0200",
        )
        equality_fallback = renderer._fmt(
            Fraction(1, 3), threshold=Fraction(1, 3)
        )
        self.assertRegex(equality_fallback, r"^0\.\d{18}\\;\(=1/3\)$")

    def test_fraction_normalization_accepts_analyzer_variants(self) -> None:
        expected = {"numerator": 1, "denominator": 3}
        self.assertEqual(
            renderer.normalize_fraction_record(
                {"numerator": 1, "denominator": 3, "value": 1 / 3}, "a"
            ),
            expected,
        )
        self.assertEqual(
            renderer.normalize_fraction_record(
                {"numerator": 1, "denominator": 3, "decimal": 1 / 3}, "direct"
            ),
            expected,
        )
        with self.assertRaisesRegex(renderer.RenderError, "disagrees"):
            renderer.normalize_fraction_record(
                {"numerator": 1, "denominator": 3, "value": 0.5}, "bad"
            )
        with self.assertRaisesRegex(renderer.RenderError, "canonical"):
            renderer.normalize_fraction_record(
                {"numerator": 2, "denominator": 6}, "bad"
            )
        with self.assertRaisesRegex(renderer.RenderError, "disagrees"):
            renderer.normalize_fraction_record(
                {
                    "numerator": 1,
                    "denominator": 3,
                    "decimal": math.nextafter(1 / 3, math.inf),
                },
                "rounded-but-different",
            )
        with self.assertRaisesRegex(renderer.RenderError, "cannot represent"):
            renderer.normalize_fraction_record(
                {
                    "numerator": 10**10000,
                    "denominator": 1,
                    "decimal": 1.0,
                },
                "overflow",
            )
        huge = 10**10000
        self.assertEqual(
            renderer.normalize_fraction_record(
                {"numerator": huge, "denominator": 1, "value": huge},
                "exact-huge-integer",
            )["numerator"],
            huge,
        )

    def test_render_is_deterministic_and_does_not_mutate_input(self) -> None:
        evidence = fixture(a_pass=True, direct_pass=True, b_pass=False)
        before = copy.deepcopy(evidence)
        self.assertEqual(renderer.render(evidence), renderer.render(evidence))
        self.assertEqual(evidence, before)


if __name__ == "__main__":
    unittest.main()
