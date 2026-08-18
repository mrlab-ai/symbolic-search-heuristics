#!/usr/bin/env python3
"""Adversarial stdlib tests for the focused cap-grid paper renderer."""

from __future__ import annotations

import copy
import hashlib
import math
import re
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_pdb_cap_grid_full_paper as renderer
import analyze_pdb_cap_grid_full as analyzer


class FocusedCapGridPaperRendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.analysis, cls.raw, cls.digest, cls.pins = renderer._synthetic_analysis()
        cls.tex = renderer._render_tex_with_pins(
            cls.analysis, cls.digest, cls.pins
        )

    def assert_rejected(self, mutation, fragment):
        changed = copy.deepcopy(self.analysis)
        mutation(changed)
        changed_raw = renderer.canonical_json(changed).encode("ascii") + b"\n"
        changed_digest = hashlib.sha256(changed_raw).hexdigest()
        pins = dict(self.pins, analysis_sha256=changed_digest)
        with self.assertRaisesRegex(renderer.RenderError, re.escape(fragment)):
            renderer._validate_analysis_with_pins(changed, changed_digest, pins)

    def validated_mutation(self, mutation):
        changed = copy.deepcopy(self.analysis)
        mutation(changed)
        changed_raw = renderer.canonical_json(changed).encode("ascii") + b"\n"
        changed_digest = hashlib.sha256(changed_raw).hexdigest()
        pins = dict(self.pins, analysis_sha256=changed_digest)
        data = renderer._validate_analysis_with_pins(changed, changed_digest, pins)
        return changed, changed_digest, pins, data

    def test_synthetic_fixture_and_tex_are_byte_deterministic(self):
        self.assertEqual(
            self.digest,
            "8e3b9b582eceb793394ea3f18ca2bd86ba7fa664f0a3b0c71eedb4b01fb9a1e9",
        )
        self.assertEqual(
            hashlib.sha256(self.tex).hexdigest(),
            "20ad1d959c8e9a959c4ae3a015d157117a6b8d00c39e698e6b5bdcdcfc3c48fa",
        )
        self.assertEqual(
            self.tex,
            renderer._render_tex_with_pins(
                copy.deepcopy(self.analysis), self.digest, self.pins
            ),
        )
        report = renderer.self_test()
        self.assertEqual(report["self_test"], "PASS")
        self.assertEqual(report["synthetic_analysis_sha256"], self.digest)
        self.assertEqual(report["synthetic_tex_sha256"], hashlib.sha256(self.tex).hexdigest())

    def test_production_gate_precedes_any_artifact_read(self):
        self.assertIsNone(renderer.EXPECTED_FULL_ANALYSIS_SHA256)
        self.assertIsNone(renderer.EXPECTED_PROTOCOL_REVISION)
        self.assertIsNone(renderer.EXPECTED_PROPERTIES_CANONICAL_SHA256)
        self.assertIsNone(renderer.EXPECTED_PROSPECTIVE_JOB_SHA256)
        with mock.patch.object(
            renderer,
            "_read_regular",
            side_effect=AssertionError("artifact must not be inspected"),
        ) as reader:
            with self.assertRaisesRegex(renderer.RenderError, "pins are unset"):
                renderer.load_frozen_analysis(Path("/outcome-bearing/path"))
            reader.assert_not_called()

    def test_schema_provenance_counts_and_config_order_fail_closed(self):
        self.assert_rejected(
            lambda value: value.__setitem__("schema", "changed"),
            "analysis.schema changed",
        )
        self.assert_rejected(
            lambda value: value.__setitem__("unexpected", 0),
            "analysis keys changed",
        )
        self.assert_rejected(
            lambda value: value["predeclaration"].__setitem__("reranking", True),
            "analysis predeclaration changed",
        )
        self.assert_rejected(
            lambda value: value["execution"].__setitem__(
                "planner_revision", hashlib.sha1(b"changed planner").hexdigest()
            ),
            "execution.planner_revision changed",
        )
        self.assert_rejected(
            lambda value: value["execution"].__setitem__(
                "properties_canonical_sha256", hashlib.sha256(b"changed").hexdigest()
            ),
            "execution.properties_canonical_sha256 changed",
        )
        self.assert_rejected(
            lambda value: value["execution"].__setitem__("cell_count", 6884),
            "execution.cell_count is outside",
        )
        self.assert_rejected(
            lambda value: value["execution"].__setitem__("all_cells_validated", False),
            "execution.all_cells_validated must be true",
        )
        self.assert_rejected(
            lambda value: value["execution"].__setitem__(
                "solved_cost_agreement_validated_across_all_configs", False
            ),
            "solved-cost consistency is not certified",
        )
        self.assert_rejected(
            lambda value: value["descriptive_full_census_configs"].reverse(),
            "descriptive_full_census_configs[0].label changed",
        )
        self.assert_rejected(
            lambda value: value["descriptive_full_census_configs"][3].__setitem__(
                "role", "descriptive-context"
            ),
            "descriptive_full_census_configs[3].role changed",
        )

    def test_integer_schema_counts_reject_equal_floats(self):
        mutations = (
            lambda value: value["execution"].__setitem__("cell_count", 6885.0),
            lambda value: value["primary"]["population"].__setitem__(
                "tasks", 1327.0
            ),
            lambda value: value["primary"]["mechanism"].__setitem__(
                "required_pairs", 1327.0
            ),
            lambda value: value["primary"]["task_micro_discordance"].__setitem__(
                "task_pairs", 1327.0
            ),
            lambda value: value["secondary_descriptive"][
                "primary_development_complement"
            ].__setitem__("tasks", 1327.0),
            lambda value: value["secondary_descriptive"][
                "primary_development_complement"
            ]["selector_summary"][renderer.CAP].__setitem__(
                "eligible_cells", 1327.0
            ),
            lambda value: value["secondary_descriptive"][
                "primary_development_complement"
            ]["paired_operational"]["micro_par2_seconds"].__setitem__(
                "fixed_task_denominator", 1327.0
            ),
            lambda value: value["descriptive_full_census_configs"][0].__setitem__(
                "cells", 1377.0
            ),
            lambda value: value["primary"]["equal_domain_macro_coverage"][
                "cap"
            ].__setitem__("fixed_estimand_denominator", 46.0),
            lambda value: value["primary"]["task_micro_discordance"].__setitem__(
                "wins_minus_losses",
                float(
                    value["primary"]["task_micro_discordance"][
                        "wins_minus_losses"
                    ]
                ),
            ),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.assert_rejected(mutate, "must be an exact integer")

        self.assert_rejected(
            lambda value: value["inference"].__setitem__(
                "fixed_population_census", 1
            ),
            "inference policy changed",
        )

    def test_fraction_domain_and_task_conservation_fail_closed(self):
        def make_fraction_unreduced(value):
            record = value["primary"]["equal_domain_macro_coverage"]["cap"]
            record["numerator"] *= 2
            record["denominator"] *= 2

        self.assert_rejected(
            make_fraction_unreduced,
            "primary.macro.cap fraction is not reduced",
        )
        self.assert_rejected(
            lambda value: value["primary"]["equal_domain_macro_coverage"][
                "cap_minus_exact"
            ].__setitem__("value", 0.5),
            "primary.macro.cap_minus_exact.value arithmetic changed",
        )
        self.assert_rejected(
            lambda value: value["primary"]["per_domain"][0].__setitem__(
                "cap_solved", value["primary"]["per_domain"][0]["cap_solved"] + 1
            ),
            "primary.per_domain[0] cap-minus-exact rate changed",
        )
        self.assert_rejected(
            lambda value: value["primary"]["per_domain"][1].__setitem__(
                "domain", value["primary"]["per_domain"][0]["domain"]
            ),
            "contains duplicate domain",
        )
        self.assert_rejected(
            lambda value: value["primary"]["task_micro_discordance"].__setitem__(
                "both_unsolved",
                value["primary"]["task_micro_discordance"]["both_unsolved"] - 1,
            ),
            "task discordance does not conserve",
        )
        self.assert_rejected(
            lambda value: value["primary"]["task_micro_discordance"].__setitem__(
                "wins_minus_losses", 0
            ),
            "micro.wins_minus_losses changed",
        )

    def test_mechanism_status_denominators_and_semantics_fail_closed(self):
        self.assert_rejected(
            lambda value: value["primary"]["mechanism"].__setitem__(
                "required_pairs", renderer.PRIMARY_TASKS - 1
            ),
            "primary.mechanism.required_pairs is outside",
        )
        self.assert_rejected(
            lambda value: value["primary"]["mechanism"].__setitem__(
                "same_k_raw_pool_identity_pairs", renderer.PRIMARY_TASKS - 1
            ),
            "status disagrees with certification denominators",
        )
        self.assert_rejected(
            lambda value: value["primary"]["mechanism"].__setitem__(
                "cap_semantic_nontrivial",
                value["primary"]["mechanism"]["cap_semantic_nontrivial"] + 1,
            ),
            "semantic counts do not conserve paired discordance",
        )
        self.assert_rejected(
            lambda value: value["primary"]["mechanism"].__setitem__(
                "semantic_selection_difference_observed", False
            ),
            "semantic_selection_difference_observed changed",
        )
        self.assert_rejected(
            lambda value: value["primary"]["mechanism"].__setitem__(
                "claim_policy", "changed"
            ),
            "claim_policy changed",
        )

        def impossible_contingency(value):
            mechanism = value["primary"]["mechanism"]
            mechanism["cap_semantic_nontrivial"] = 0
            mechanism["exact_semantic_nontrivial"] = 1
            mechanism["semantic_pair_wins"] = 1
            mechanism["semantic_pair_losses"] = 2
            selectors = value["secondary_descriptive"][
                "primary_development_complement"
            ]["selector_summary"]
            selectors[renderer.CAP]["semantic_nontrivial"] = 0
            selectors[renderer.EXACT]["semantic_nontrivial"] = 1

        self.assert_rejected(
            impossible_contingency,
            "primary.mechanism semantic contingency table is impossible",
        )

        def make_not_certified(value):
            value["primary"]["mechanism"]["same_k_raw_pool_identity_pairs"] -= 1
            value["primary"]["mechanism"]["status"] = "not-certified"

        changed, digest, pins, _ = self.validated_mutation(make_not_certified)
        tex = renderer._render_tex_with_pins(changed, digest, pins).decode("utf-8")
        self.assertIn("Mechanism attribution was not certified", tex)

    def test_secondary_fieldwise_denominators_and_histograms_fail_closed(self):
        cap = self.analysis["secondary_descriptive"]["primary_development_complement"][
            "selector_summary"
        ][renderer.CAP]
        self.assertEqual(cap["complete_certified_traces"], renderer.PRIMARY_TASKS)
        self.assertEqual(cap["W"]["observed"], renderer.PRIMARY_TASKS)
        self.assertEqual(cap["U"]["observed"], renderer.PRIMARY_TASKS)
        self.assertEqual(cap["A"]["observed"], renderer.PRIMARY_TASKS - 1)
        self.assertEqual(cap["T"]["observed"], renderer.PRIMARY_TASKS - 2)
        self.assertEqual(cap["V"]["observed"], renderer.PRIMARY_TASKS - 3)
        producer_summary = analyzer._count_summary([1, 2, 3])
        self.assertIs(type(producer_summary["total"]), int)
        validated = renderer._validate_count_summary(
            producer_summary, "producer-count-summary", 3, 3
        )
        self.assertEqual(validated["total"], 6)
        large = analyzer._count_summary([2**53 + 2])
        self.assertEqual(
            renderer._validate_count_summary(
                large, "large-producer-count-summary", 1, 1
            )["total"],
            2**53 + 2,
        )

        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "selector_summary"
            ][renderer.CAP]["A"].__setitem__("observed", renderer.PRIMARY_TASKS + 1),
            "secondary.primary_development_complement.selector.cap.A.observed is outside",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "selector_summary"
            ][renderer.CAP]["W"].__setitem__("maximum", 9),
            "selected width exceeds the frozen K=8 budget",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "selector_summary"
            ][renderer.CAP]["effective_cap_histogram"].__setitem__("8", 899),
            "effective-cap histogram does not conserve",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "selector_summary"
            ][renderer.EXACT]["effective_cap_histogram"].__setitem__("8", 1),
            "exact selector contains a finite cap",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "selector_summary"
            ][renderer.CAP]["selected_first_provenance_source"].__setitem__("empty", 99),
            "source histogram does not conserve",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "selector_summary"
            ][renderer.CAP].__setitem__("semantic_nontrivial", 999),
            "cap nontrivial count disagrees with mechanism",
        )

    def test_zero_complete_trace_selector_summary_is_valid(self):
        summary = copy.deepcopy(
            self.analysis["secondary_descriptive"][
                "primary_development_complement"
            ]["selector_summary"][renderer.CAP]
        )
        summary["complete_certified_traces"] = 0
        summary["semantic_nontrivial"] = 0
        summary["effective_cap_histogram"] = {}
        summary["selected_first_provenance_source"] = {
            source: 0 for source in renderer.SELECTOR_SOURCES
        }
        for field in ("pattern_size", "W", "A", "T", "U", "V"):
            summary[field] = renderer._summary(0, 0)
        validated = renderer._validate_selector_summary(
            summary,
            "zero-trace-selector",
            renderer.PRIMARY_TASKS,
            renderer.CAP,
        )
        self.assertEqual(validated["traces"], 0)
        self.assertEqual(validated["summaries"]["U"]["observed"], 0)

    def test_secondary_ratio_directions_pair_sets_and_censoring_fail_closed(self):
        base = self.analysis["secondary_descriptive"]["primary_development_complement"][
            "paired_operational"
        ]
        self.assertEqual(
            base["complete_certified_image_time"]["eligible_pair_count"],
            base["complete_certified_expanded_bdd_nodes"]["eligible_pair_count"],
        )
        self.assertEqual(
            base["jointly_solved_planner_cpu"]["eligible_pair_count"]
            + base["jointly_solved_planner_cpu"]["excluded_nonpositive_pair_count"],
            base["jointly_solved_planner_cpu"]["jointly_solved_pair_count"],
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "paired_operational"
            ]["micro_par2_seconds"].__setitem__("candidate_minus_reference", 5.0),
            "par2.candidate_minus_reference arithmetic changed",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "paired_operational"
            ]["jointly_solved_planner_cpu"].__setitem__("excluded_nonpositive_pair_count", 0),
            "CPU eligible/excluded counts do not conserve",
        )
        self.assert_rejected(
            lambda value: (
                value["secondary_descriptive"]["primary_development_complement"][
                    "paired_operational"
                ]["jointly_solved_planner_cpu"].__setitem__("jointly_solved_pair_count", 457),
                value["secondary_descriptive"]["primary_development_complement"][
                    "paired_operational"
                ]["jointly_solved_planner_cpu"].__setitem__("eligible_pair_count", 456),
            ),
            "jointly solved CPU count disagrees with coverage",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "paired_operational"
            ]["complete_certified_image_time"].__setitem__("candidate_over_reference", 1.1),
            "image_time.candidate_over_reference arithmetic changed",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "paired_operational"
            ]["complete_certified_expanded_bdd_nodes"].__setitem__(
                "eligible_pair_count", 499
            ),
            "image and effort certified pair sets differ",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"]["primary_development_complement"][
                "paired_operational"
            ]["observed_completed_construction_time"].__setitem__(
                "candidate_over_reference", 0.5
            ),
            "construction_time.candidate_over_reference arithmetic changed",
        )

    def test_par2_is_reconstructed_from_solved_counts_and_runtime_totals(self):
        primary_par2 = lambda value: value["secondary_descriptive"][
            "primary_development_complement"
        ]["paired_operational"]["micro_par2_seconds"]
        self.assert_rejected(
            lambda value: primary_par2(value).__setitem__(
                "candidate_solved", primary_par2(value)["candidate_solved"] - 1
            ),
            "candidate PAR2 solved count disagrees with coverage",
        )
        self.assert_rejected(
            lambda value: primary_par2(value).__setitem__(
                "reference_solved", primary_par2(value)["reference_solved"] - 1
            ),
            "reference PAR2 solved count disagrees with coverage",
        )
        self.assert_rejected(
            lambda value: primary_par2(value).__setitem__(
                "candidate_solved_planner_cpu_total_seconds",
                primary_par2(value)[
                    "candidate_solved_planner_cpu_total_seconds"
                ]
                + 1.0,
            ),
            "par2.candidate arithmetic changed",
        )
        self.assert_rejected(
            lambda value: primary_par2(value).__setitem__(
                "reference_solved_planner_cpu_total_seconds",
                primary_par2(value)[
                    "reference_solved_planner_cpu_total_seconds"
                ]
                + 1.0,
            ),
            "par2.reference arithmetic changed",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive"][
                "primary_development_complement"
            ]["paired_operational"]["micro_par2_seconds"].__setitem__(
                "candidate",
                math.nextafter(
                    value["secondary_descriptive"][
                        "primary_development_complement"
                    ]["paired_operational"]["micro_par2_seconds"]["candidate"],
                    math.inf,
                ),
            ),
            "secondary.primary_development_complement.par2.candidate arithmetic changed",
        )
        self.assert_rejected(
            lambda value: value["descriptive_full_census_configs"][0].__setitem__(
                "micro_par2_seconds", 0.0
            ),
            "descriptive_full_census_configs[0].micro_par2_seconds arithmetic changed",
        )

    def test_primary_subset_relations_fail_closed(self):
        def histogram_exceeds_census(value):
            histogram = value["secondary_descriptive"][
                "primary_development_complement"
            ]["selector_summary"][renderer.CAP]["effective_cap_histogram"]
            histogram["8"] += 1
            histogram["exact"] -= 1

        self.assert_rejected(
            histogram_exceeds_census,
            "primary-subset.selector.cap.cap_histogram.8 primary count exceeds full census",
        )

        def paired_image_exceeds_census(value):
            paired = value["secondary_descriptive"][
                "primary_development_complement"
            ]["paired_operational"]
            paired["complete_certified_image_time"]["eligible_pair_count"] = 521
            paired["complete_certified_expanded_bdd_nodes"][
                "eligible_pair_count"
            ] = 521

        self.assert_rejected(
            paired_image_exceeds_census,
            "primary-subset.image.pairs primary count exceeds full census",
        )

        def coverage_exceeds_census(value):
            contrast = value["full_census_sensitivity"]
            for index in (2, 3):
                row = contrast["per_domain"][index]
                row["cap_solved"] -= 1
                row["cap_minus_exact_rate"] = renderer._fraction(
                    Fraction(row["cap_solved"] - row["exact_solved"], row["tasks"])
                )
            cap_macro = sum(
                Fraction(row["cap_solved"], row["tasks"])
                for row in contrast["per_domain"]
            ) / renderer.DOMAINS
            exact_macro = sum(
                Fraction(row["exact_solved"], row["tasks"])
                for row in contrast["per_domain"]
            ) / renderer.DOMAINS
            contrast["equal_domain_macro_coverage"]["cap"] = renderer._fraction(
                cap_macro, renderer.DOMAINS
            )
            contrast["equal_domain_macro_coverage"]["exact"] = renderer._fraction(
                exact_macro, renderer.DOMAINS
            )
            contrast["equal_domain_macro_coverage"][
                "cap_minus_exact"
            ] = renderer._fraction(cap_macro - exact_macro, renderer.DOMAINS)
            micro = contrast["task_micro_discordance"]
            micro["cap_wins"] = 2
            micro["wins_minus_losses"] = 0
            micro["discordant"] = 4
            micro["both_unsolved"] = (
                renderer.TASKS
                - micro["cap_wins"]
                - micro["cap_losses"]
                - micro["both_solved"]
            )
            cap_solved = micro["cap_wins"] + micro["both_solved"]
            cap_runtime_total = cap_solved * 9.0
            cap_par2 = (
                cap_runtime_total
                + renderer.PAR2_PENALTY * (renderer.TASKS - cap_solved)
            ) / renderer.TASKS
            cap_config = value["descriptive_full_census_configs"][4]
            cap_config["solved"] = cap_solved
            cap_config["coverage_rate"] = cap_solved / renderer.TASKS
            cap_config["solved_planner_cpu_seconds"] = renderer._summary(
                cap_solved, 9.0
            )
            cap_config["micro_par2_seconds"] = cap_par2
            secondary_par2 = value["secondary_descriptive"][
                "full_census_sensitivity"
            ]["paired_operational"]["micro_par2_seconds"]
            secondary_par2["candidate_solved"] = cap_solved
            secondary_par2[
                "candidate_solved_planner_cpu_total_seconds"
            ] = cap_runtime_total
            secondary_par2["candidate"] = cap_par2
            secondary_par2["candidate_minus_reference"] = (
                cap_par2 - secondary_par2["reference"]
            )

        self.assert_rejected(
            coverage_exceeds_census,
            "primary-subset.per_domain[2].cap_solved primary count exceeds full census",
        )

    def test_contract_and_canonical_finite_json_fail_closed(self):
        self.assert_rejected(
            lambda value: value["secondary_descriptive_contract"].__setitem__(
                "sha256", hashlib.sha256(b"changed contract").hexdigest()
            ),
            "secondary_descriptive_contract.sha256 changed",
        )
        self.assert_rejected(
            lambda value: value["secondary_descriptive_contract"]["contract"].__setitem__(
                "role", "changed"
            ),
            "secondary descriptive contract payload changed",
        )
        with self.assertRaisesRegex(renderer.RenderError, "duplicate JSON key"):
            renderer.parse_canonical_analysis(b'{"a":1,"a":2}\n')
        with self.assertRaisesRegex(renderer.RenderError, "one newline"):
            renderer.parse_canonical_analysis(b'{ "a": 1 }\n')
        with self.assertRaisesRegex(renderer.RenderError, "nonfinite JSON constant"):
            renderer.parse_canonical_analysis(b'{"a":NaN}\n')
        with self.assertRaisesRegex(renderer.RenderError, "canonical finite JSON"):
            renderer.canonical_json({"value": math.inf})

        with tempfile.TemporaryDirectory(prefix="cap-render-canonical-") as directory:
            root = Path(directory)
            artifact = root / "analysis-v1.json"
            sidecar = Path(str(artifact) + ".sha256")
            artifact.write_bytes(self.raw)
            sidecar.write_text(
                "{}  {}\n".format(self.digest, artifact.name), encoding="ascii"
            )
            loaded, digest = renderer._load_frozen_analysis_with_pins(
                artifact, sidecar, self.pins
            )
            self.assertEqual(loaded, self.analysis)
            self.assertEqual(digest, self.digest)
            sidecar.write_text(
                "{} *{}\n".format(self.digest, artifact.name), encoding="ascii"
            )
            with self.assertRaisesRegex(renderer.RenderError, "sidecar"):
                renderer._load_frozen_analysis_with_pins(artifact, sidecar, self.pins)

    def test_tex_is_anonymous_bounded_and_contains_planned_fragments(self):
        text = self.tex.decode("utf-8")
        macro_names = re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", text)
        self.assertEqual(len(macro_names), len(set(macro_names)))
        for name in (
            "CapFullContextRows",
            "CapPrimaryContrastRows",
            "CapPrimaryMechanismRows",
            "CapPrimarySecondaryRows",
            "CapCensusSecondaryRows",
            "CapPrimaryText",
            "CapMechanismText",
            "CapSensitivityText",
            "CapScopeCaveat",
            "CapRatioCaveat",
            "CapCensoringCaveat",
        ):
            self.assertIn(name, macro_names)
        for _, _, paper_label, _ in renderer.CONFIGS:
            self.assertIn(paper_label, text)
        self.assertLessEqual(len(self.tex), renderer.MAX_TEX_BYTES)
        self.assertNotIn("Arrhenius", text)
        self.assertNotIn("/nobackup", text)
        execution = self.analysis["execution"]
        for key in (
            "protocol_revision",
            "planner_revision",
            "planner_binary_sha256",
            "planner_preprocess_sha256",
            "prospective_start_job_sha256",
            "properties_canonical_sha256",
            "task_manifest_sha256",
            "primary_task_manifest_sha256",
            "option_matrix_sha256",
        ):
            self.assertNotIn(execution[key], text)

    def test_atomic_output_and_stale_check(self):
        with tempfile.TemporaryDirectory(prefix="cap-render-atomic-") as directory:
            output = Path(directory) / "generated.tex"
            renderer._write_atomic(output, self.tex)
            renderer.check_output(output, self.tex)
            first = output.read_bytes()
            renderer._write_atomic(output, self.tex)
            self.assertEqual(output.read_bytes(), first)
            output.write_bytes(self.tex + b"% stale\n")
            with self.assertRaisesRegex(renderer.RenderError, "stale"):
                renderer.check_output(output, self.tex)


if __name__ == "__main__":
    unittest.main()
