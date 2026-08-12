#!/usr/bin/env python3
"""Stdlib tests for the frozen full-census paper renderer."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import sys
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_arrhenius_selector_full_paper as renderer


class FullPaperRendererTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.launch_pins = renderer.CURRENT_ANALYZER_FIXTURE_LAUNCH_PINS
        cls.analysis, cls.raw, cls.digest = renderer._current_analyzer_fixture()
        cls.tex = renderer._render_tex_with_test_pins(
            cls.analysis, cls.digest, launch_pins=cls.launch_pins
        )
        cls.paper_data = renderer._paper_data_with_test_pins(
            cls.analysis, cls.digest, launch_pins=cls.launch_pins
        )

    def assert_rejected(self, mutation, fragment):
        changed = copy.deepcopy(self.analysis)
        mutation(changed)
        changed_raw = renderer.canonical_json(changed).encode("ascii") + b"\n"
        changed_digest = hashlib.sha256(changed_raw).hexdigest()
        with self.assertRaisesRegex(renderer.RenderError, re.escape(fragment)):
            renderer._validate_analysis_with_test_pins(
                changed, changed_digest, launch_pins=self.launch_pins
            )

    def test_current_analyzer_fixture_is_stable_and_deterministic(self):
        self.assertEqual(
            self.digest,
            "605c2bb61dbed30a82d490dbe38d29c750cc70fc47731cf3e9a97c143a52c9f9",
        )
        self.assertEqual(
            hashlib.sha256(self.tex).hexdigest(),
            "e9c2634f7ff1027654ea1d0655d50246a9cc9def2cf3596a9ae5ab2e273213b2",
        )
        paper_json = renderer.canonical_json(self.paper_data).encode("ascii")
        self.assertEqual(
            hashlib.sha256(paper_json).hexdigest(),
            "94f61d1879265731151eb2a67bd9a1557446f195ed17b0913cffb95cbcb0b2b5",
        )
        self.assertEqual(
            self.tex,
            renderer._render_tex_with_test_pins(
                copy.deepcopy(self.analysis),
                self.digest,
                launch_pins=self.launch_pins,
            ),
        )
        self.assertEqual(
            renderer.canonical_json(self.paper_data),
            renderer.canonical_json(
                renderer._paper_data_with_test_pins(
                    copy.deepcopy(self.analysis),
                    self.digest,
                    launch_pins=self.launch_pins,
                )
            ),
        )

    def test_output_uses_exact_label_index_and_unique_tex_macros(self):
        labels = [entry["label"] for entry in self.paper_data["configs"]]
        self.assertEqual(labels, list(renderer.CONFIG_LABELS))
        comparison_names = [entry["name"] for entry in self.paper_data["comparisons"]]
        self.assertEqual(comparison_names, [entry[0] for entry in renderer.COMPARISONS])
        text = self.tex.decode("utf-8")
        macros = re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", text)
        self.assertEqual(len(macros), len(set(macros)))
        self.assertIn("ArrFullConfigRows", macros)
        self.assertIn("ArrFullPairedMetricRows", macros)
        self.assertIn("ArrFullDomainCoverageRows", macros)
        self.assertIn("ArrFullTerminalOutcomeRows", macros)
        self.assertIn("ArrFullTerminalOutcomePerConfigRows", macros)
        for expected in renderer.CONFIGS:
            self.assertIn(expected["paper_label"], text)

    def test_identity_layout_and_order_mutations_fail_closed(self):
        self.assert_rejected(
            lambda value: value["execution"].__setitem__(
                "full_runner_source_sha256", hashlib.sha256(b"changed").hexdigest()
            ),
            "full_runner_source_sha256",
        )
        self.assert_rejected(
            lambda value: value["execution"]["array_layout"][
                "array_task_run_distribution"
            ].__setitem__("partial_runs", 8),
            "partial_runs",
        )
        self.assert_rejected(
            lambda value: value["execution"].__setitem__(
                "p5_to_p6_git_lineage_protocol", "changed"
            ),
            "p5_to_p6_git_lineage_protocol",
        )
        self.assert_rejected(
            lambda value: value["execution"].__setitem__(
                "presearch_sigxcpu_effective_exit_code", 232
            ),
            "presearch_sigxcpu_effective_exit_code",
        )
        self.assert_rejected(
            lambda value: value["primary"]["configs"][-1].__setitem__(
                "label", "blind_fw"
            ),
            "duplicate label",
        )
        self.assert_rejected(
            lambda value: value["primary"]["carried_comparisons"][-1].__setitem__(
                "name", renderer.PRIMARY_COMPARISON
            ),
            "duplicate name",
        )

    def test_terminal_outcome_census_is_exact_and_fail_closed(self):
        census = self.analysis["terminal_outcome_census"]
        self.assertEqual(
            census["protocol"], renderer.TERMINAL_OUTCOME_CENSUS_PROTOCOL
        )
        self.assertEqual(census["unit"], renderer.TERMINAL_OUTCOME_CENSUS_UNIT)
        self.assertEqual(census, self.paper_data["terminal_outcome_census"])
        self.assertEqual(
            [row["planner_exit_code"] for row in census["global"]["outcomes"]],
            list(renderer.TERMINAL_OUTCOME_CODES),
        )
        self.assertEqual(
            [entry["label"] for entry in census["per_config"]],
            list(renderer.CONFIG_LABELS),
        )
        self.assertEqual(
            sum(row["cell_records"] for row in census["global"]["outcomes"]),
            renderer.CELLS,
        )
        for row, spec in zip(
            census["global"]["outcomes"], renderer.TERMINAL_OUTCOME_SPECS
        ):
            code, error, presearch, raw_exit, effective_exit = spec
            self.assertEqual(
                (
                    row["planner_exit_code"],
                    row["error"],
                    row["presearch"],
                    row["search_raw_exit_code"],
                    row["search_effective_exit_code"],
                ),
                (code, error, presearch, raw_exit, effective_exit),
            )
        self.assertTrue(
            any(row["cell_records"] == 0 for row in census["global"]["outcomes"])
        )

        self.assert_rejected(
            lambda value: value["terminal_outcome_census"].__setitem__(
                "unit", "attempt-generations"
            ),
            "terminal_outcome_census.unit",
        )
        self.assert_rejected(
            lambda value: value["terminal_outcome_census"].__setitem__(
                "unexpected", 0
            ),
            "terminal_outcome_census keys changed",
        )
        self.assert_rejected(
            lambda value: value["terminal_outcome_census"]["global"][
                "outcomes"
            ][-1].__setitem__("planner_exit_code", 232),
            "planner_exit_code",
        )
        self.assert_rejected(
            lambda value: value["terminal_outcome_census"]["global"][
                "outcomes"
            ][1].__setitem__("search_raw_exit_code", 1),
            "search_raw_exit_code",
        )
        self.assert_rejected(
            lambda value: value["terminal_outcome_census"]["global"][
                "outcomes"
            ][2].__setitem__("search_effective_exit_code", 23),
            "search_effective_exit_code",
        )
        self.assert_rejected(
            lambda value: value["terminal_outcome_census"]["global"][
                "outcomes"
            ][2].__setitem__("error", "search-out-of-time"),
            ".error",
        )
        self.assert_rejected(
            lambda value: value["terminal_outcome_census"]["global"][
                "outcomes"
            ][4].__setitem__("presearch", 1),
            "presearch",
        )
        self.assert_rejected(
            lambda value: value["terminal_outcome_census"]["global"][
                "outcomes"
            ][0].__setitem__("unexpected", 0),
            "keys changed",
        )
        self.assert_rejected(
            lambda value: value["terminal_outcome_census"]["global"][
                "outcomes"
            ][4].__setitem__("cell_records", 0.5),
            "must be an exact integer",
        )
        self.assert_rejected(
            lambda value: value["terminal_outcome_census"]["global"][
                "outcomes"
            ].pop(3),
            "must contain 12 entries",
        )
        self.assert_rejected(
            lambda value: value["terminal_outcome_census"]["per_config"].reverse(),
            "label",
        )

        def shift_counts(value, source, target):
            for outcome_slice in (
                value["terminal_outcome_census"]["global"],
                value["terminal_outcome_census"]["per_config"][0],
            ):
                by_code = {
                    row["planner_exit_code"]: row
                    for row in outcome_slice["outcomes"]
                }
                by_code[source]["cell_records"] -= 1
                by_code[target]["cell_records"] += 1

        self.assert_rejected(
            lambda value: shift_counts(value, 0, 23),
            "terminal solved counts disagree with coverage",
        )
        self.assert_rejected(
            lambda value: shift_counts(value, 23, 20),
            "pre-search outcome counts disagree with image summary",
        )

        def change_global_marginal(value):
            by_code = {
                row["planner_exit_code"]: row
                for row in value["terminal_outcome_census"]["global"][
                    "outcomes"
                ]
            }
            by_code[23]["cell_records"] -= 1
            by_code[22]["cell_records"] += 1

        self.assert_rejected(
            change_global_marginal,
            "global/per-configuration counts disagree",
        )

    def test_label_indexed_array_permutations_render_identically(self):
        shuffled = copy.deepcopy(self.analysis)
        shuffled["primary"]["configs"].reverse()
        shuffled["primary"]["carried_comparisons"].reverse()
        shuffled["completion_and_recovery"]["per_config"].reverse()
        shuffled["primary"][
            "selector_vs_cegar_equally_weighted_domain_coverage"
        ]["per_domain"].reverse()
        shuffled["sole_predeclared_sensitivity"]["per_domain"].reverse()
        for config in shuffled["primary"]["configs"]:
            config["per_domain_coverage"].reverse()
        shuffled_raw = renderer.canonical_json(shuffled).encode("ascii") + b"\n"
        shuffled_digest = hashlib.sha256(shuffled_raw).hexdigest()
        shuffled_data = renderer._paper_data_with_test_pins(
            shuffled, shuffled_digest, launch_pins=self.launch_pins
        )
        shuffled_tex = renderer._render_tex_with_test_pins(
            shuffled, shuffled_digest, launch_pins=self.launch_pins
        )
        normalized_tex = shuffled_tex.replace(
            shuffled_digest.encode("ascii"), self.digest.encode("ascii")
        ).replace(
            renderer.sha256_json(shuffled_data).encode("ascii"),
            renderer.sha256_json(self.paper_data).encode("ascii"),
        )
        self.assertEqual(
            normalized_tex, self.tex
        )
        shuffled_data["analysis_sha256"] = self.digest
        self.assertEqual(
            renderer.canonical_json(shuffled_data),
            renderer.canonical_json(self.paper_data),
        )

    def test_summary_certification_and_pair_arithmetic_fail_closed(self):
        self.assert_rejected(
            lambda value: value["primary"]["configs"][6]["coverage"].__setitem__(
                "rate", 0.0
            ),
            "coverage.rate arithmetic",
        )
        self.assert_rejected(
            lambda value: value["primary"]["configs"][1]["construction"][
                "certification"
            ].__setitem__("uncertified_or_unobserved_cells", 1),
            "certification arithmetic",
        )
        self.assert_rejected(
            lambda value: value["primary"]["configs"][1]["construction"][
                "time_seconds"
            ].__setitem__("mean", 9.0),
            "mean lies outside",
        )
        self.assert_rejected(
            lambda value: value["primary"]["carried_comparisons"][0][
                "paired_solved_effort"
            ].__setitem__("candidate_minus_reference", 9.0),
            "candidate_minus_reference arithmetic",
        )

        def make_pair_candidate_total_fractional(value, metric_name):
            metric = value["primary"]["carried_comparisons"][0][metric_name]
            metric["candidate_total"] += 0.5
            metric["candidate_minus_reference"] = (
                metric["candidate_total"] - metric["reference_total"]
            )
            metric["candidate_over_reference"] = (
                metric["candidate_total"] / metric["reference_total"]
            )

        self.assert_rejected(
            lambda value: make_pair_candidate_total_fractional(
                value, "paired_observed_cofactor_width"
            ),
            "candidate_total must be integral",
        )
        self.assert_rejected(
            lambda value: make_pair_candidate_total_fractional(
                value, "paired_solved_effort"
            ),
            "candidate_total must be integral",
        )
        self.assert_rejected(
            lambda value: value["primary"]["carried_comparisons"][0][
                "paired_solved_effort"
            ].__setitem__(
                "pairs",
                value["primary"]["carried_comparisons"][0]["coverage"][
                    "both_solved"
                ]
                - 1,
            ),
            "solved-effort intersection is incomplete",
        )
        self.assert_rejected(
            lambda value: value["primary"]["configs"][6][
                "exact_cofactor_width"
            ]["summary"].__setitem__("maximum", 2),
            "width above one",
        )

        def change_selector_feasible_total(value):
            summary = value["primary"]["configs"][6]["selector_effort"][
                "feasible_candidate_records"
            ]
            summary["total"] += 1
            summary["mean"] = summary["total"] / summary["observed"]
            summary["maximum"] += 1

        self.assert_rejected(
            change_selector_feasible_total,
            "selector candidate feasibility total arithmetic",
        )

        def make_selector_counts_fractional(value):
            selector = value["primary"]["configs"][6]["selector_effort"]
            for name in ("candidate_records", "feasible_candidate_records"):
                summary = selector[name]
                summary["total"] += 0.5
                summary["mean"] = summary["total"] / summary["observed"]
                summary["maximum"] += 1

        self.assert_rejected(
            make_selector_counts_fractional,
            "total must be integral",
        )

    def test_macro_sensitivity_and_recovery_arithmetic_fail_closed(self):
        self.assert_rejected(
            lambda value: value["primary"][
                "selector_vs_cegar_equally_weighted_domain_coverage"
            ]["per_domain"][0]["candidate_minus_reference_rate"].__setitem__(
                "numerator", 0
            ),
            "reduced fraction",
        )

        def change_config_domain_without_macro(value):
            entries = value["primary"]["configs"][6]["per_domain_coverage"]
            pair = None
            for first in entries:
                for second in entries:
                    if (
                        first is not second
                        and first["tasks"] == second["tasks"]
                        and first["solved"] < first["tasks"]
                        and second["solved"] > 0
                    ):
                        pair = first, second
                        break
                if pair is not None:
                    break
            first, second = pair
            first["solved"] += 1
            second["solved"] -= 1
            first["rate"] = first["solved"] / first["tasks"]
            second["rate"] = second["solved"] / second["tasks"]

        self.assert_rejected(
            change_config_domain_without_macro,
            "primary macro per-domain coverage disagrees",
        )

        def change_screen_domain_distribution(value):
            full = {
                entry["domain"]: entry["tasks"]
                for entry in value["primary"][
                    "selector_vs_cegar_equally_weighted_domain_coverage"
                ]["per_domain"]
            }
            entries = value["sole_predeclared_sensitivity"]["per_domain"]
            removed_two = next(
                entry for entry in entries if full[entry["domain"]] - entry["tasks"] == 2
            )
            removed_zero = next(
                entry
                for entry in entries
                if full[entry["domain"]] == entry["tasks"]
                and entry["candidate_solved"] <= entry["tasks"] - 1
                and entry["reference_solved"] <= entry["tasks"] - 1
            )
            removed_two["tasks"] += 1
            removed_zero["tasks"] -= 1
            deltas = []
            for entry in entries:
                delta = Fraction(
                    entry["candidate_solved"] - entry["reference_solved"],
                    entry["tasks"],
                )
                entry["candidate_minus_reference_rate"] = {
                    "numerator": delta.numerator,
                    "denominator": delta.denominator,
                    "value": float(delta),
                }
                deltas.append(delta)
            estimate = sum(deltas, Fraction(0, 1)) / len(deltas)
            value["sole_predeclared_sensitivity"]["estimate"] = {
                "numerator": estimate.numerator,
                "denominator": estimate.denominator,
                "value": float(estimate),
            }

        self.assert_rejected(
            change_screen_domain_distribution,
            "removes neither zero nor two tasks",
        )
        self.assert_rejected(
            lambda value: value["sole_predeclared_sensitivity"]["identity"].__setitem__(
                "task_count", 1326
            ),
            "task_count",
        )
        self.assert_rejected(
            lambda value: value["completion_and_recovery"]["global"].__setitem__(
                "total_partial_archives", 0
            ),
            "archive total arithmetic",
        )

    def test_canonical_loader_sidecar_and_atomic_output(self):
        with tempfile.TemporaryDirectory(prefix="renderer-unittest-") as raw_dir:
            root = Path(raw_dir)
            artifact = root / "analysis-v4.json"
            sidecar = Path(str(artifact) + ".sha256")
            artifact.write_bytes(self.raw)
            sidecar.write_text(
                "{}  {}\n".format(self.digest, artifact.name), encoding="ascii"
            )
            loaded, digest = renderer._load_frozen_analysis_with_test_pins(
                artifact,
                expected_analysis_sha256=self.digest,
                launch_pins=self.launch_pins,
            )
            self.assertEqual(loaded, self.analysis)
            self.assertEqual(digest, self.digest)

            output = root / "paper" / "generated.tex"
            renderer._write_atomic(output, self.tex)
            renderer.check_output(output, self.tex)
            renderer._write_atomic(output, self.tex)
            self.assertEqual(output.read_bytes(), self.tex)

            sidecar.write_text(
                "{} *{}\n".format(self.digest, artifact.name), encoding="ascii"
            )
            with self.assertRaisesRegex(renderer.RenderError, "sidecar"):
                renderer._load_frozen_analysis_with_test_pins(
                    artifact,
                    expected_analysis_sha256=self.digest,
                    launch_pins=self.launch_pins,
                )

    def test_noncanonical_and_duplicate_json_are_rejected(self):
        value = {"a": 1}
        with self.assertRaisesRegex(renderer.RenderError, "one newline"):
            renderer.parse_canonical_analysis(
                renderer.canonical_json(value).encode("ascii"), "synthetic"
            )
        with self.assertRaisesRegex(renderer.RenderError, "duplicate JSON key"):
            renderer.parse_canonical_analysis(b'{"a":1,"a":2}\n', "synthetic")
        with self.assertRaisesRegex(renderer.RenderError, "non-finite JSON"):
            renderer.parse_canonical_analysis(b'{"a":NaN}\n', "synthetic")

    def test_exact_fraction_percentage_rounding(self):
        self.assertEqual(
            renderer._tex_stat(9_007_199_254_740_993),
            "9{,}007{,}199{,}254{,}740{,}993",
        )
        self.assertEqual(
            renderer._fraction_percent(
                {"numerator": 1, "denominator": 8, "value": 0.125}, 2
            ),
            "12.50",
        )
        self.assertEqual(
            renderer._fraction_percent(
                {"numerator": 1, "denominator": 32, "value": 0.03125}, 2
            ),
            "3.13",
        )
        self.assertEqual(
            renderer._fraction_percent(
                {"numerator": -1, "denominator": 32, "value": -0.03125}, 2
            ),
            "-3.13",
        )

    def test_tex_reporting_inventory_and_row_arities(self):
        text = self.tex.decode("utf-8")
        macros = set(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", text))
        for expected in renderer.CONFIGS:
            suffix = expected["suffix"]
            for tail in (
                "RuntimeObserved",
                "RuntimeMinimum",
                "RuntimeMedian",
                "RuntimeMaximum",
                "RuntimeMean",
                "RuntimeTotal",
                "EffortObserved",
                "EffortMinimum",
                "EffortMedian",
                "EffortMaximum",
                "EffortMean",
                "EffortTotal",
                "ConstructionObserved",
                "ConstructionEligible",
                "WidthObserved",
                "WidthEligible",
                "WidthMinimum",
                "ImagePrefixObserved",
                "ImagePrefixEligible",
                "ImagePrefixSeconds",
                "ImageCompleteObserved",
                "ImageCompleteEligible",
                "ImageCompleteSeconds",
                "ImageAttemptedCalls",
                "ImageCompletedCalls",
                "ImageSecondsPerCall",
            ):
                self.assertIn("ArrFull{}{}".format(suffix, tail), macros)
        for name in (
            "ArrFullConfigRows",
            "ArrFullImageRows",
            "ArrFullRuntimeEffortRows",
            "ArrFullSelectorEffortRows",
            "ArrFullComparisonRows",
            "ArrFullPairedMetricRows",
            "ArrFullCompletionRows",
            "ArrFullTerminalOutcomeRows",
            "ArrFullTerminalOutcomePerConfigRows",
            "ArrFullDomainCoverageRows",
        ):
            self.assertIn(name, macros)
        for name in (
            "ArrFullAnalysisSha",
            "ArrFullPropertiesSha",
            "ArrFullPaperDataSha",
            "ArrFullSelectionSha",
            "ArrFullAnalysisSchema",
            "ArrFullProtocol",
            "ArrFullProtocolRevision",
            "ArrFullRunnerSha",
            "ArrFullPlannerRevision",
            "ArrFullPlannerBinarySha",
            "ArrFullPlannerPreprocessSha",
            "ArrFullJobSha",
            "ArrFullTerminalOutcomeProtocol",
            "ArrFullTerminalOutcomeUnit",
            "ArrFullTerminalOutcomeUnitNote",
            "ArrFullTerminalOutcomeTwentyOneCaveat",
            "ArrFullSensitivityCandidateSolved",
            "ArrFullSensitivityReferenceSolved",
        ):
            self.assertIn(name, macros)
        paper_data_digest = renderer.sha256_json(self.paper_data)
        self.assertIn(
            "% Source analysis SHA-256: {}".format(self.digest), text
        )
        self.assertIn(
            "% Source properties SHA-256: {}".format(
                self.paper_data["properties_canonical_sha256"]
            ),
            text,
        )
        self.assertIn(
            "% Extraction schema: {}".format(renderer.PAPER_DATA_SCHEMA), text
        )
        self.assertIn(
            "% Canonical PaperData SHA-256: {}".format(paper_data_digest), text
        )
        config_row = renderer._config_row(self.paper_data["configs"][1])
        self.assertEqual(len(config_row.removesuffix(" \\\\%").split(" & ")), 6)
        self.assertIn("344.250", config_row)
        image_row = renderer._image_row(self.paper_data["configs"][1])
        self.assertEqual(len(image_row.removesuffix(" \\\\%").split(" & ")), 8)
        runtime_row = renderer._runtime_effort_row(self.paper_data["configs"][1])
        self.assertEqual(len(runtime_row.removesuffix(" \\\\%").split(" & ")), 13)
        selector_row = renderer._selector_summary_row(
            "Candidate records",
            self.paper_data["configs"][6]["selector_effort"]["candidate_records"],
        )
        self.assertEqual(len(selector_row.removesuffix(" \\\\%").split(" & ")), 7)
        terminal_row = renderer._terminal_outcome_row(
            self.paper_data["terminal_outcome_census"]["global"]["outcomes"][4]
        )
        self.assertEqual(len(terminal_row.removesuffix(" \\\\%").split(" & ")), 6)
        self.assertIn("-- & --", terminal_row)
        terminal_config_row = renderer._terminal_outcome_per_config_row(
            "Blind forward",
            self.paper_data["terminal_outcome_census"]["per_config"][0],
        )
        self.assertEqual(
            len(terminal_config_row.removesuffix(" \\\\%").split(" & ")),
            13,
        )
        self.assertIn(renderer.TERMINAL_OUTCOME_UNIT_NOTE, text)
        self.assertIn(renderer.TERMINAL_OUTCOME_CODE_21_CAVEAT, text)
        for _, suffix in renderer.TERMINAL_OUTCOME_CODE_SUFFIXES:
            self.assertIn("ArrFullTerminalOutcomeCode{}".format(suffix), macros)
            for config in renderer.CONFIGS:
                self.assertIn(
                    "ArrFull{}TerminalOutcomeCode{}".format(
                        config["suffix"], suffix
                    ),
                    macros,
                )

    def test_write_target_is_confined_and_symlink_safe(self):
        with tempfile.TemporaryDirectory(prefix="renderer-write-target-") as raw_dir:
            root = Path(raw_dir)
            expected = root / "paper" / "generated" / "result.tex"
            self.assertEqual(
                renderer._validate_write_target(
                    expected, expected=expected, root=root
                ),
                expected,
            )
            with self.assertRaisesRegex(renderer.RenderError, "restricted"):
                renderer._validate_write_target(
                    root / "elsewhere.tex", expected=expected, root=root
                )
            outside = root / "outside"
            outside.mkdir()
            (root / "paper").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(renderer.RenderError, "symlink component"):
                renderer._validate_write_target(
                    expected, expected=expected, root=root
                )

    def test_production_pin_state_is_atomic_and_public_contract_is_v4(self):
        partial = renderer._production_pin_values()
        partial["analysis_sha256"] = self.digest
        with self.assertRaisesRegex(renderer.RenderError, "partially set"):
            renderer._reviewed_production_pins_from(partial)

        overrides = {
            "EXPECTED_FULL_ANALYSIS_SHA256": self.digest,
            "EXPECTED_PROTOCOL_REVISION": self.launch_pins["protocol_revision"],
            "EXPECTED_FULL_RUNNER_SHA256": self.launch_pins[
                "full_runner_source_sha256"
            ],
            "EXPECTED_PLANNER_BINARY_SHA256": self.launch_pins[
                "planner_binary_sha256"
            ],
            "EXPECTED_PLANNER_PREPROCESS_SHA256": self.launch_pins[
                "planner_preprocess_sha256"
            ],
            "EXPECTED_PROSPECTIVE_JOB_SHA256": self.launch_pins[
                "prospective_start_job_sha256"
            ],
        }
        with mock.patch.multiple(renderer, **overrides):
            renderer.validate_analysis(self.analysis, self.digest)
            self.assertEqual(renderer.paper_data(self.analysis, self.digest), self.paper_data)
            self.assertEqual(renderer.render_tex(self.analysis, self.digest), self.tex)
            stale = copy.deepcopy(self.analysis)
            stale["execution"]["properties_canonical_sha256"] = hashlib.sha256(
                b"different in-memory value"
            ).hexdigest()
            for call in (
                lambda: renderer.validate_analysis(stale, self.digest),
                lambda: renderer.paper_data(stale, self.digest),
                lambda: renderer.render_tex(stale, self.digest),
            ):
                with self.assertRaisesRegex(renderer.RenderError, "in-memory canonical"):
                    call()
            with tempfile.TemporaryDirectory(prefix="renderer-public-v4-") as raw_dir:
                artifact = Path(raw_dir) / "analysis-v4.json"
                artifact.write_bytes(self.raw)
                Path(str(artifact) + ".sha256").write_text(
                    "{}  {}\n".format(self.digest, artifact.name), encoding="ascii"
                )
                loaded, loaded_digest = renderer.load_frozen_analysis(artifact)
                self.assertEqual(loaded, self.analysis)
                self.assertEqual(loaded_digest, self.digest)

        canceled = copy.deepcopy(self.analysis)
        canceled_pins = {
            "protocol": "arrhenius-selector-full-population-v3",
            "protocol_revision": "a52488637a1c054b26dac93fe2eb1a556110a2dd",
            "full_runner_source_sha256": (
                "84d6408781724203ba3420d6a559d1c56aac196f560f8b76c14f8cde730ab642"
            ),
            "planner_revision": "165b6d2ee29d5d7b6e1bf4c52540c393ba19b54f",
            "planner_binary_sha256": (
                "af2a19d236ecad9b747d2a1b9c49da73d98248c38d21cc60ad0ac7613d74bdbe"
            ),
            "planner_preprocess_sha256": (
                "1b351a4a5f9380bf41fe9fd61b98c816505ebd8cf88b20afa0d81a9bfb2474bd"
            ),
            "prospective_start_job_sha256": (
                "c83c880c1bfaa503cfffab69c91abb037e58b4424b7216480aa551631aed043f"
            ),
        }
        for key, value in canceled_pins.items():
            canceled["execution"][key] = value
        canceled_raw = renderer.canonical_json(canceled).encode("ascii") + b"\n"
        canceled_digest = hashlib.sha256(canceled_raw).hexdigest()
        with self.assertRaisesRegex(renderer.RenderError, "protocol v4"):
            renderer._validate_analysis_with_test_pins(
                canceled, canceled_digest, launch_pins=canceled_pins
            )
        canceled_overrides = dict(overrides)
        canceled_overrides["EXPECTED_FULL_ANALYSIS_SHA256"] = canceled_digest
        with mock.patch.multiple(renderer, **canceled_overrides):
            for call in (
                lambda: renderer.validate_analysis(canceled, canceled_digest),
                lambda: renderer.paper_data(canceled, canceled_digest),
                lambda: renderer.render_tex(canceled, canceled_digest),
            ):
                with self.assertRaisesRegex(renderer.RenderError, "execution.protocol"):
                    call()
            with tempfile.TemporaryDirectory(prefix="renderer-public-v3-") as raw_dir:
                artifact = Path(raw_dir) / "analysis-v4.json"
                artifact.write_bytes(canceled_raw)
                Path(str(artifact) + ".sha256").write_text(
                    "{}  {}\n".format(canceled_digest, artifact.name),
                    encoding="ascii",
                )
                with self.assertRaisesRegex(renderer.RenderError, "execution.protocol"):
                    renderer.load_frozen_analysis(artifact)

    def test_ordinary_gate_remains_unset(self):
        self.assertIsNone(renderer.EXPECTED_FULL_ANALYSIS_SHA256)
        self.assertEqual(
            renderer.FULL_PROTOCOL,
            "arrhenius-selector-full-population-v4",
        )
        for value in (
            renderer.EXPECTED_PROTOCOL_REVISION,
            renderer.EXPECTED_FULL_RUNNER_SHA256,
            renderer.EXPECTED_PLANNER_BINARY_SHA256,
            renderer.EXPECTED_PLANNER_PREPROCESS_SHA256,
            renderer.EXPECTED_PROSPECTIVE_JOB_SHA256,
        ):
            self.assertIsNone(value)
        self.assertEqual(
            renderer.EXPECTED_PLANNER_REVISION,
            "a3486a027a0f281e762cb6d66d72311455b66b33",
        )
        with self.assertRaisesRegex(renderer.RenderError, "all unset"):
            renderer.reviewed_production_pins()
        public_calls = (
            lambda: renderer.load_frozen_analysis(Path("does-not-need-to-exist.json")),
            lambda: renderer.validate_analysis(self.analysis, self.digest),
            lambda: renderer.paper_data(self.analysis, self.digest),
            lambda: renderer.render_tex(self.analysis, self.digest),
        )
        for call in public_calls:
            with self.assertRaisesRegex(renderer.RenderError, "all unset"):
                call()


if __name__ == "__main__":
    unittest.main()
