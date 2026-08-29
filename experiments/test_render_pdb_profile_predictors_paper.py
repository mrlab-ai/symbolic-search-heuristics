#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import analyze_pdb_profile_predictors as Analysis
import pdb_profile_comparison_protocol as Protocol
import render_pdb_profile_predictors_paper as Renderer


def fraction(value):
    if not isinstance(value, Fraction):
        value = Fraction(str(value))
    return Analysis._fraction_record(value)


def distribute(total):
    quotient, remainder = divmod(total, Protocol.COHORT_DOMAINS)
    return [
        quotient + (index < remainder)
        for index in range(Protocol.COHORT_DOMAINS)
    ]


def pairwise(predictor, target, direction, concordance, comparable_per_domain=100):
    concordance = Fraction(str(concordance))
    if (concordance * comparable_per_domain).denominator != 1:
        raise AssertionError("fixture concordance is not integral")
    eligible_domains = Analysis.MIN_STRONG_CLAIM_DOMAINS
    rows = []
    concordant_total = 0
    discordant_total = 0
    domain_values = {}
    for index in range(Protocol.COHORT_DOMAINS):
        domain = "d{:02d}".format(index + 1)
        comparable = comparable_per_domain if index < eligible_domains else 0
        concordant = int(concordance * comparable) if comparable else 0
        discordant = comparable - concordant
        concordant_total += concordant
        discordant_total += discordant
        value = Fraction(concordant, comparable) if comparable else None
        domain_values[domain] = value
        rows.append({
            "domain": domain,
            "concordant": concordant,
            "discordant": discordant,
            "comparable": comparable,
            "concordance": fraction(value) if value is not None else None,
        })
    macro = sum(
        (value for value in domain_values.values() if value is not None),
        Fraction(),
    ) / eligible_domains
    loo = {}
    for omitted in domain_values:
        retained = [
            value
            for domain, value in domain_values.items()
            if domain != omitted and value is not None
        ]
        loo[omitted] = sum(retained, Fraction()) / len(retained)
    comparable = concordant_total + discordant_total
    return {
        "predictor": predictor,
        "target": target,
        "direction": direction,
        "distinct_heuristic_pairs": comparable,
        "tasks_with_comparable_pairs": Analysis.MIN_STRONG_CLAIM_TASKS,
        "concordant": concordant_total,
        "discordant": discordant_total,
        "comparable": comparable,
        "micro_concordance": fraction(Fraction(concordant_total, comparable)),
        "eligible_domains": eligible_domains,
        "equal_domain_macro": fraction(macro),
        "leave_one_domain_out": {
            "values": {domain: fraction(value) for domain, value in loo.items()},
            "minimum": fraction(min(loo.values())),
            "maximum": fraction(max(loo.values())),
        },
        "by_domain": rows,
    }


def shared(target, specifications, values):
    predictors = {
        key: pairwise(predictor, target, direction, values[key])
        for key, (predictor, direction) in specifications.items()
    }
    comparable = next(iter(predictors.values()))["comparable"]
    per_domain = 100
    return {
        "protocol": Analysis.SHARED_COMPARISON_PROTOCOL,
        "target": target,
        "support": {
            "observation_pairs": comparable,
            "target_tied": 0,
            "any_predictor_tied": 0,
            "comparable": comparable,
            "tasks_with_comparable_pairs": Analysis.MIN_STRONG_CLAIM_TASKS,
            "eligible_domains": Analysis.MIN_STRONG_CLAIM_DOMAINS,
            "predictor_tie_counts": {},
            "by_domain": [
                {
                    "domain": "d{:02d}".format(index + 1),
                    "comparable": (
                        per_domain
                        if index < Analysis.MIN_STRONG_CLAIM_DOMAINS
                        else 0
                    ),
                }
                for index in range(Protocol.COHORT_DOMAINS)
            ],
        },
        "predictors": predictors,
    }


def contrast(candidate, reference, ratio=Fraction(4, 5), coverage=1):
    ratio = Fraction(ratio)
    candidate_total = ratio.numerator * 1000
    reference_total = ratio.denominator * 1000
    candidate_effort = distribute(candidate_total)
    reference_effort = distribute(reference_total)
    eligible = distribute(Analysis.MIN_STRONG_CLAIM_TASKS)
    tasks = distribute(Protocol.COHORT_TASKS)
    rows = []
    row_differences = {}
    for index in range(Protocol.COHORT_DOMAINS):
        domain = "d{:02d}".format(index + 1)
        row_difference = Fraction(coverage, tasks[index])
        row_differences[domain] = row_difference
        rows.append({
            "domain": domain,
            "tasks": tasks[index],
            "both_solved": tasks[index] - max(coverage, 0),
            "candidate_only": max(coverage, 0),
            "reference_only": max(-coverage, 0),
            "both_unsolved": 0,
            "coverage_difference": fraction(row_difference),
            "effort_eligible_pairs": eligible[index],
            "candidate_effort": candidate_effort[index],
            "reference_effort": reference_effort[index],
            "effort_ratio": fraction(
                Fraction(candidate_effort[index], reference_effort[index])
            ),
        })
    candidate_only = Protocol.COHORT_DOMAINS * max(coverage, 0)
    reference_only = Protocol.COHORT_DOMAINS * max(-coverage, 0)
    both_solved = Protocol.COHORT_TASKS - candidate_only - reference_only
    effort_loo = {}
    coverage_loo = {}
    for row in rows:
        effort_loo[row["domain"]] = fraction(Fraction(
            candidate_total - row["candidate_effort"],
            reference_total - row["reference_effort"],
        ))
        retained = [
            difference
            for domain, difference in row_differences.items()
            if domain != row["domain"]
        ]
        coverage_loo[row["domain"]] = fraction(
            sum(retained, Fraction()) / len(retained)
        )
    coverage_macro = sum(row_differences.values(), Fraction()) / len(row_differences)
    return {
        "candidate": candidate,
        "reference": reference,
        "fixed_task_denominator": Protocol.COHORT_TASKS,
        "coverage": {
            "both_solved": both_solved,
            "candidate_only": candidate_only,
            "reference_only": reference_only,
            "both_unsolved": 0,
            "incomplete_effort": both_solved - Analysis.MIN_STRONG_CLAIM_TASKS,
            "candidate_minus_reference": candidate_only - reference_only,
            "equal_domain_macro_difference": fraction(coverage_macro),
        },
        "conditional_effort": {
            "eligible_pairs": Analysis.MIN_STRONG_CLAIM_TASKS,
            "candidate_total": candidate_total,
            "reference_total": reference_total,
            "candidate_over_reference": fraction(ratio),
        },
        "leave_one_domain_out": {
            "effort_ratio": effort_loo,
            "coverage_macro_difference": coverage_loo,
        },
        "by_domain": rows,
    }


def fixture():
    fragmentation_specs = {
        "cofactor_width": ("cofactor_width", "same"),
        "total_add_nodes": ("total_add_nodes", "same"),
        "quality": ("quality", "opposite"),
    }
    certificate_specs = {
        "B_profile": ("B_profile", "same"),
        "B_width": ("B_width", "same"),
        "B_add": ("B_add", "same"),
    }
    fragmentation_gate = shared(
        "fragmentation",
        fragmentation_specs,
        {"cofactor_width": 0.70, "total_add_nodes": 0.71, "quality": 0.55},
    )
    certificate_gate = shared(
        "actual_effort",
        certificate_specs,
        {"B_profile": 0.80, "B_width": 0.75, "B_add": 0.76},
    )
    fragmentation = {
        **fragmentation_gate["predictors"],
        "finite_values": pairwise(
            "finite_values", "fragmentation", "same", 0.65
        ),
        "quality_to_total_effort": pairwise(
            "quality", "actual_effort", "opposite", 0.60
        ),
    }
    certificates = certificate_gate["predictors"]

    width_add = []
    cap_exact = []
    constrained = []
    blind = []
    for k, u in Protocol.MATCHED_BUDGETS:
        width = "pdb_cap_width_k{}".format(k)
        add = "pdb_cap_add_u{}".format(u)
        exact = "pdb_exact_k{}".format(k)
        width_add.append(contrast(width, add, coverage=0))
        cap_exact.append(contrast(width, exact, coverage=1))
        constrained.extend([
            contrast(exact, "pdb_exact_unconstrained", coverage=0),
            contrast(width, "pdb_exact_unconstrained", coverage=0),
            contrast(add, "pdb_exact_unconstrained", coverage=0),
        ])
    for label in Protocol.LABELS[2:]:
        blind.append(contrast(label, "blind_fw_profiled", coverage=1))
    contrasts = {
        "matched_width_vs_add": width_add,
        "cap_width_vs_exact_width": cap_exact,
        "constrained_vs_unconstrained": constrained,
        "selector_vs_profiled_blind": blind,
    }
    gates = Analysis.decision_gates(
        fragmentation_gate["predictors"], certificate_gate["predictors"], contrasts
    )
    return {
        "schema": Analysis.SCHEMA,
        "raw_analysis_protocol": Protocol.ANALYSIS_PROTOCOL,
        "frozen_predictor_protocol_sha256": Analysis.PROTOCOL_SHA256,
        "scope": {
            "tasks": Protocol.COHORT_TASKS,
            "domains": Protocol.COHORT_DOMAINS,
            "configurations": Protocol.CONFIG_COUNT,
            "inference": Protocol.INFERENCE_POLICY,
            "strong_claim_support": {
                "minimum_domains": Analysis.MIN_STRONG_CLAIM_DOMAINS,
                "minimum_tasks_or_pairs": Analysis.MIN_STRONG_CLAIM_TASKS,
            },
        },
        "fragmentation_observation_status": {
            "unsolved": Protocol.COHORT_TASKS * (Protocol.CONFIG_COUNT - 2)
        },
        "fragmentation_observations": [],
        "fragmentation_predictors": fragmentation,
        "fragmentation_gate_comparison": fragmentation_gate,
        "certificate_predictors": certificates,
        "certificate_gate_comparison": certificate_gate,
        "selector_contrasts": contrasts,
        "decision_gates": gates,
    }


class RendererTests(unittest.TestCase):
    def test_complete_fixture_validates_and_renders(self):
        value = fixture()
        Renderer.validate_analysis(value)
        raw = Renderer.canonical_json(value) + b"\n"
        digest = hashlib.sha256(raw).hexdigest()
        tex = Renderer.render_tex(value, digest)
        self.assertIn(b"\\newcommand{\\ProfileWidthPredictorGate}{pass}", tex)
        self.assertIn(b"\\newcommand{\\ProfileWidthAddRows}", tex)

        with self.assertRaisesRegex(Renderer.RenderError, "digest is invalid"):
            Renderer.render_tex(value, "0" * 64 + "\\n\\input{paper}")

    def test_shared_support_and_gate_mutations_fail_closed(self):
        value = fixture()
        value["fragmentation_gate_comparison"]["support"]["by_domain"].pop()
        with self.assertRaisesRegex(Renderer.RenderError, "length changed"):
            Renderer.validate_analysis(value)

        value = fixture()
        old = value["decision_gates"].pop(
            "cap_aware_width_higher_coverage_than_profiled_blind"
        )
        value["decision_gates"][
            "cap_aware_width_generally_better_than_blind"
        ] = old
        with self.assertRaisesRegex(Renderer.RenderError, "keys changed"):
            Renderer.validate_analysis(value)

        value = fixture()
        rows = value["selector_contrasts"]["matched_width_vs_add"][0]["by_domain"]
        rows[-1]["domain"] = rows[-2]["domain"]
        with self.assertRaisesRegex(Renderer.RenderError, "domain universe changed"):
            Renderer.validate_analysis(value)

        value = fixture()
        support = value["fragmentation_gate_comparison"]["support"]["by_domain"]
        support[0]["comparable"] += 1
        support[1]["comparable"] -= 1
        with self.assertRaisesRegex(Renderer.RenderError, "domain support is not shared"):
            Renderer.validate_analysis(value)

        value = fixture()
        row = value["selector_contrasts"]["matched_width_vs_add"][0]["by_domain"][0]
        row["candidate_effort"] += 123456789
        with self.assertRaisesRegex(Renderer.RenderError, "effort ratio arithmetic changed"):
            Renderer.validate_analysis(value)

    def test_frozen_protocol_mismatch_fails_closed(self):
        with mock.patch.object(Renderer.Analysis, "_sha256", return_value="0" * 64):
            with self.assertRaisesRegex(Renderer.RenderError, "protocol bytes changed"):
                Renderer.validate_analysis(fixture())

    def test_sealed_load_requires_exact_artifact_and_sidecar(self):
        value = fixture()
        raw = Renderer.canonical_json(value) + b"\n"
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "predictors-v1.json"
            path.write_bytes(raw)
            path.with_name(path.name + ".sha256").write_text(
                "{}  {}\n".format(digest, path.name), encoding="ascii"
            )
            loaded, actual = Renderer.load_analysis(path, digest)
            self.assertEqual(loaded, value)
            self.assertEqual(actual, digest)
            with self.assertRaisesRegex(Renderer.RenderError, "digest changed"):
                Renderer.load_analysis(path, "0" * 64)


if __name__ == "__main__":
    unittest.main()
