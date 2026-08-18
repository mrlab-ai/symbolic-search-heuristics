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
        cls.structure, cls.structure_raw, cls.structure_digest = (
            renderer._current_structure_fixture()
        )
        cls.p5_analysis, cls.p5_digest = renderer.load_p5_analysis()
        cls.p5_raw = renderer._read_regular(
            renderer.DEFAULT_P5_ANALYSIS, renderer.MAX_ARTIFACT_BYTES
        )
        cls.tex = renderer._render_tex_with_test_pins(
            cls.analysis,
            cls.digest,
            launch_pins=cls.launch_pins,
            structure=cls.structure,
            structure_sha256=cls.structure_digest,
            p5_analysis=cls.p5_analysis,
            p5_analysis_sha256=cls.p5_digest,
        )
        cls.paper_data = renderer._paper_data_with_test_pins(
            cls.analysis,
            cls.digest,
            launch_pins=cls.launch_pins,
            structure=cls.structure,
            structure_sha256=cls.structure_digest,
            p5_analysis=cls.p5_analysis,
            p5_analysis_sha256=cls.p5_digest,
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

    def assert_p5_rejected(self, mutation, fragment):
        changed = copy.deepcopy(self.p5_analysis)
        mutation(changed)
        changed_raw = renderer.canonical_json(changed).encode("ascii") + b"\n"
        changed_digest = hashlib.sha256(changed_raw).hexdigest()
        with self.assertRaisesRegex(renderer.RenderError, re.escape(fragment)):
            renderer._validate_p5_analysis(changed, changed_digest)

    def assert_structure_rejected(self, mutation, fragment):
        changed = copy.deepcopy(self.structure)
        mutation(changed)
        changed_raw = renderer.canonical_json(changed).encode("ascii") + b"\n"
        changed_digest = hashlib.sha256(changed_raw).hexdigest()
        with self.assertRaisesRegex(renderer.RenderError, re.escape(fragment)):
            renderer._validate_structure_with_test_pins(
                changed,
                changed_digest,
                analysis=self.analysis,
                analysis_sha256=self.digest,
                launch_pins=self.launch_pins,
            )

    def test_current_analyzer_fixture_is_stable_and_deterministic(self):
        self.assertEqual(
            self.digest,
            "605c2bb61dbed30a82d490dbe38d29c750cc70fc47731cf3e9a97c143a52c9f9",
        )
        self.assertEqual(
            self.structure_digest,
            "da0029621cb9c4a20092158d2c4cd9016d3dd46a57a8ba18f22acca17312e9b3",
        )
        self.assertEqual(
            hashlib.sha256(self.tex).hexdigest(),
            "44f64ff5093bbf3907aace1b1aabca054fba0b5b410606bf9bc13013281fb6fa",
        )
        paper_json = renderer.canonical_json(self.paper_data).encode("ascii")
        self.assertEqual(
            hashlib.sha256(paper_json).hexdigest(),
            "8305e8ae7bb518040c329a3eef58aa438b37fae903c72a565b58f04886fab2e6",
        )
        self.assertEqual(
            self.tex,
            renderer._render_tex_with_test_pins(
                copy.deepcopy(self.analysis),
                self.digest,
                launch_pins=self.launch_pins,
                structure=copy.deepcopy(self.structure),
                structure_sha256=self.structure_digest,
                p5_analysis=copy.deepcopy(self.p5_analysis),
                p5_analysis_sha256=self.p5_digest,
            ),
        )
        self.assertEqual(
            renderer.canonical_json(self.paper_data),
            renderer.canonical_json(
                renderer._paper_data_with_test_pins(
                    copy.deepcopy(self.analysis),
                    self.digest,
                    launch_pins=self.launch_pins,
                    structure=copy.deepcopy(self.structure),
                    structure_sha256=self.structure_digest,
                    p5_analysis=copy.deepcopy(self.p5_analysis),
                    p5_analysis_sha256=self.p5_digest,
                )
            ),
        )

    def test_p5_pin_identity_and_label_index_are_exact(self):
        self.assertEqual(
            self.p5_digest,
            "7c598f068164224272b8ba035b987973f35d0d45e695f90c9083931790908cea",
        )
        self.assertEqual(
            self.p5_raw,
            renderer.canonical_json(self.p5_analysis).encode("ascii") + b"\n",
        )
        self.assertEqual(
            renderer.DEFAULT_P5_SIDECAR.read_bytes(),
            (
                self.p5_digest
                + "  "
                + renderer.DEFAULT_P5_ANALYSIS.name
                + "\n"
            ).encode("ascii"),
        )
        p5_data = self.paper_data["p5_heldout"]
        self.assertEqual(p5_data["schema"], renderer.P5_PAPER_INPUT_SCHEMA)
        self.assertEqual(p5_data["analysis_sha256"], self.p5_digest)
        self.assertEqual(p5_data["task_count"], 92)
        self.assertEqual(p5_data["domain_count"], 46)
        self.assertEqual(p5_data["config_count"], 7)
        self.assertEqual(p5_data["cell_count"], 644)
        self.assertEqual(
            [row["label"] for row in p5_data["configs"]],
            list(renderer.CONFIG_LABELS),
        )
        self.assertEqual(
            [row["solved"] for row in p5_data["configs"]],
            [40, 42, 42, 41, 40, 43, 41],
        )

    def test_structure_schema_identity_and_interpretation_are_fail_closed(self):
        self.assertEqual(self.structure["schema"], renderer.STRUCTURE_SCHEMA)
        self.assertIn(b"\\ArrFullStructureDirectRows", self.tex)
        self.assertIn(b"\\ArrFullStructurePartitionRows", self.tex)
        self.assertIn(b"\\ArrFullStructureCorrelationRows", self.tex)
        self.assertIn(b"\\ArrFullStructureCandidateRows", self.tex)
        self.assertIn(b"\\ArrFullStructureSourceRows", self.tex)
        for caveat in (
            renderer.STRUCTURE_TIMING_CAVEAT,
            renderer.STRUCTURE_INFERENCE_CAVEAT,
            renderer.STRUCTURE_RESOURCE_PREFIX_CAVEAT,
        ):
            self.assertIn(renderer._tex_escape(caveat).encode("ascii"), self.tex)
        self.assertIn(
            "Protocol audits had already parsed individual structural fields",
            renderer.STRUCTURE_TIMING_CAVEAT,
        )
        self.assertNotIn(
            "before any structural value", renderer.STRUCTURE_TIMING_CAVEAT
        )
        self.assertEqual(self.tex.count(b" & Complete WBH log & "), 7)
        self.assertEqual(self.tex.count(b" & Certified resource prefix & "), 7)
        self.assertEqual(
            self.tex.count(b" / maximum partition ratio & ")
            + self.tex.count(b" / geometric-mean partition ratio & "),
            28,
        )
        self.assert_structure_rejected(
            lambda value: value.__setitem__("schema", "changed"),
            "structure.schema",
        )
        self.assert_structure_rejected(
            lambda value: value.__setitem__("unexpected", 1),
            "structure keys changed",
        )
        self.assert_structure_rejected(
            lambda value: value.__setitem__("decision_label", "prospective"),
            "structure.decision_label",
        )
        self.assert_structure_rejected(
            lambda value: value["interpretation"].__setitem__(
                "theorem_validation", True
            ),
            "structure.interpretation",
        )
        self.assert_structure_rejected(
            lambda value: value["input_identity"].__setitem__(
                "properties_canonical_sha256", hashlib.sha256(b"drift").hexdigest()
            ),
            "structure.input_identity",
        )
        self.assert_structure_rejected(
            lambda value: value["input_identity"]["config_order"].reverse(),
            "structure.input_identity",
        )
        self.assert_structure_rejected(
            lambda value: value["configs"][1].__setitem__("label", "blind_fw"),
            "unexpected or duplicate label",
        )

    def test_structure_direct_tuple_and_partition_arithmetic_are_fail_closed(self):
        direct = lambda value: value["configs"][1]["direct_W_A_V_T_U"]
        self.assert_structure_rejected(
            lambda value: direct(value).__setitem__("observed_cells", 1376),
            "direct-tuple denominator arithmetic",
        )
        self.assert_structure_rejected(
            lambda value: direct(value)["tuple_census"][0].__setitem__("U", 1),
            "violates W >= T >= V",
        )
        self.assert_structure_rejected(
            lambda value: direct(value)["summaries"]["W"].__setitem__("total", 1.0),
            "summaries.W.mean arithmetic",
        )
        self.assert_structure_rejected(
            lambda value: value["configs"][5]["direct_W_A_V_T_U"][
                "unobserved_reason_counts"
            ].update(construction_fallback=37, resource_before_direct_tuple=1),
            "construction-fallback census disagrees",
        )
        self.assert_structure_rejected(
            lambda value: value["configs"][1]["partition_ratios"][
                "raw_complete_logs_not_necessarily_complete_searches"
            ].__setitem__("eligible_logs", 1376),
            "logs_without_partition_ratios exceeds",
        )
        self.assert_structure_rejected(
            lambda value: value["configs"][1]["partition_ratios"][
                "raw_complete_logs_not_necessarily_complete_searches"
            ]["terminal_outcome_counts"][0].__setitem__("count", 1376),
            "outcome counts do not conserve",
        )

        def undercount_partition_strata(value):
            raw = value["configs"][1]["partition_ratios"][
                "raw_complete_logs_not_necessarily_complete_searches"
            ]
            raw["eligible_logs"] -= 1
            raw["logs_without_partition_ratios"] -= 1
            raw["terminal_outcome_counts"][0]["count"] -= 1

        self.assert_structure_rejected(
            undercount_partition_strata,
            "partition strata do not equal completed constructions",
        )

        def impossible_resource_prefix_stratum(value):
            partition = value["configs"][1]["partition_ratios"]
            raw = partition["raw_complete_logs_not_necessarily_complete_searches"]
            prefix = partition["certified_resource_prefixes"]
            raw["eligible_logs"] -= 1
            raw["logs_without_partition_ratios"] -= 1
            raw["terminal_outcome_counts"][10]["count"] -= 1
            prefix["eligible_logs"] = 1
            prefix["logs_without_partition_ratios"] = 1
            prefix["terminal_outcome_counts"][10]["count"] = 1

        self.assert_structure_rejected(
            impossible_resource_prefix_stratum,
            "resource-prefix structural logs exceed canonical incomplete prefixes",
        )
        analysis_config = copy.deepcopy(self.analysis["primary"]["configs"][1])
        analysis_config["image"]["complete_certified"]["certified_cells"] -= 1
        outcome_counts = {
            row["planner_exit_code"]: row["cell_records"]
            for row in self.analysis["terminal_outcome_census"]["per_config"][1]["outcomes"]
        }
        with self.assertRaisesRegex(
            renderer.RenderError, "raw-complete structural logs exceed canonical complete logs"
        ):
            renderer._validate_structure_config(
                self.structure["configs"][1],
                renderer.CONFIGS[1],
                analysis_config,
                outcome_counts,
            )

        def paired_width_not_in_direct_census(value):
            raw = value["configs"][1]["partition_ratios"][
                "raw_complete_logs_not_necessarily_complete_searches"
            ]
            raw["logs_with_partition_ratios"] = 1
            raw["logs_without_partition_ratios"] -= 1
            raw["ratio_observation_terminal_outcome_counts"][0]["count"] = 1
            raw["partition_ratio_census"] = [
                {
                    "partition_ratio_max": 2.0,
                    "partition_ratio_geomean": 1.0,
                    "count": 1,
                }
            ]
            raw["summaries"]["partition_ratio_max"] = renderer._expected_structure_summary([2.0])
            raw["summaries"]["partition_ratio_geomean"] = renderer._expected_structure_summary([1.0])
            raw["paired_direct_tuple_and_ratio_cells"] = 1
            raw["paired_W_U_partition_ratio_census"] = [
                {
                    "W": 6,
                    "U": 26,
                    "partition_ratio_max": 2.0,
                    "partition_ratio_geomean": 1.0,
                    "count": 1,
                }
            ]
            for key, _display in renderer.STRUCTURE_CORRELATIONS:
                raw["cross_task_descriptive_confounded_correlations"][key] = {
                    "n": 1,
                    "coefficient": None,
                    "null_reason": "fewer-than-two-pairs",
                }

        self.assert_structure_rejected(
            paired_width_not_in_direct_census,
            "paired W/U census exceeds the direct-tuple census",
        )

        def width_only_prefix_outside_selector(value):
            direct_config = value["configs"][1]["direct_W_A_V_T_U"]
            direct_config["observed_cells"] -= 1
            direct_config["unobserved_cells"] += 1
            direct_config["observation_source_counts"]["completed_construction"] -= 1
            direct_config["unobserved_reason_counts"][
                "selector_width_only_resource_prefix"
            ] += 1
            direct_config["tuple_census"][0]["count"] -= 1
            direct_config["tuple_census"][0]["completed_construction_cells"] -= 1
            for key in (
                "W", "A", "V", "T", "U", "U_over_W", "A_over_W", "V_over_W", "T_over_W"
            ):
                summary = direct_config["summaries"][key]
                summary["observed"] -= 1
                summary["total"] -= summary["mean"]

        self.assert_structure_rejected(
            width_only_prefix_outside_selector,
            "has a selector-width-only prefix outside the selector",
        )

        def validate_selector_config(structure_config, analysis_config):
            outcome_counts = {
                row["planner_exit_code"]: row["cell_records"]
                for row in self.analysis["terminal_outcome_census"]["per_config"][6][
                    "outcomes"
                ]
            }
            return renderer._validate_structure_config(
                structure_config,
                renderer.CONFIGS[6],
                analysis_config,
                outcome_counts,
            )

        # Reclassifying completed cells as certified heuristic-only resource
        # prefixes used to pass when all local source and partition counts were
        # changed consistently.  There are no canonical incomplete prefixes in
        # this fixture, so even one such cell is impossible.
        structure_config = copy.deepcopy(self.structure["configs"][6])
        analysis_config = copy.deepcopy(self.analysis["primary"]["configs"][6])
        direct_config = structure_config["direct_W_A_V_T_U"]
        direct_config["observation_source_counts"]["completed_construction"] -= 1
        direct_config["observation_source_counts"][
            "heuristic_event_only_resource_prefix"
        ] += 1
        direct_config["tuple_census"][0]["completed_construction_cells"] -= 1
        direct_config["tuple_census"][0][
            "heuristic_event_only_resource_prefix_cells"
        ] += 1
        raw = structure_config["partition_ratios"][
            "raw_complete_logs_not_necessarily_complete_searches"
        ]
        raw["eligible_logs"] -= 1
        raw["logs_without_partition_ratios"] -= 1
        raw["terminal_outcome_counts"][0]["count"] -= 1
        analysis_config["construction"]["certification"]["certified_cells"] -= 1
        with self.assertRaisesRegex(
            renderer.RenderError,
            "certified structural resource-prefix categories exceed",
        ):
            validate_selector_config(structure_config, analysis_config)

        # The resource-outcome constraint is independent of the incomplete-log
        # constraint: allow 107 hypothetical incomplete prefixes, but retain the
        # canonical 106 resource outcomes.  The 106 raw resource outcomes plus
        # 107 heuristic-only prefixes cannot describe disjoint cells.
        structure_config = copy.deepcopy(self.structure["configs"][6])
        analysis_config = copy.deepcopy(self.analysis["primary"]["configs"][6])
        direct_config = structure_config["direct_W_A_V_T_U"]
        direct_config["observation_source_counts"]["completed_construction"] -= 107
        direct_config["observation_source_counts"][
            "heuristic_event_only_resource_prefix"
        ] += 107
        direct_config["tuple_census"][0]["completed_construction_cells"] -= 107
        direct_config["tuple_census"][0][
            "heuristic_event_only_resource_prefix_cells"
        ] += 107
        raw = structure_config["partition_ratios"][
            "raw_complete_logs_not_necessarily_complete_searches"
        ]
        raw["eligible_logs"] -= 107
        raw["logs_without_partition_ratios"] -= 107
        raw["terminal_outcome_counts"][0]["count"] -= 107
        analysis_config["construction"]["certification"]["certified_cells"] -= 107
        analysis_config["image"]["certified_prefix"]["certified_cells"] += 107
        with self.assertRaisesRegex(
            renderer.RenderError,
            "structural resource categories exceed the canonical resource-outcome census",
        ):
            validate_selector_config(structure_config, analysis_config)

        # A width-only selector prefix contributes to the canonical width total
        # but not the direct W/A/V/T/U tuple census.  Its omitted total must be
        # feasible under the canonical integer width range.
        structure_config = copy.deepcopy(self.structure["configs"][6])
        analysis_config = copy.deepcopy(self.analysis["primary"]["configs"][6])
        direct_config = structure_config["direct_W_A_V_T_U"]
        direct_config["observed_cells"] -= 1
        direct_config["unobserved_cells"] += 1
        direct_config["observation_source_counts"]["completed_construction"] -= 1
        direct_config["unobserved_reason_counts"][
            "selector_width_only_resource_prefix"
        ] += 1
        direct_config["tuple_census"][0]["count"] -= 1
        direct_config["tuple_census"][0]["completed_construction_cells"] -= 1
        for key in ("W", "A", "V", "T", "U", "U_over_W", "A_over_W", "V_over_W", "T_over_W"):
            summary = direct_config["summaries"][key]
            summary["observed"] -= 1
            summary["total"] -= summary["mean"]
        analysis_config["exact_cofactor_width"]["summary"]["total"] += 1
        with self.assertRaisesRegex(
            renderer.RenderError, "omitted selector-width total is infeasible"
        ):
            validate_selector_config(structure_config, analysis_config)
        analysis_config["exact_cofactor_width"]["summary"].update(
            minimum=0,
            total=direct_config["summaries"]["W"]["total"],
        )
        with self.assertRaisesRegex(
            renderer.RenderError, "omitted selector-width total is infeasible"
        ):
            validate_selector_config(structure_config, analysis_config)

    def test_structure_ratio_correlation_and_candidate_censuses_are_fail_closed(self):
        raw = copy.deepcopy(self.structure["configs"][1]["partition_ratios"][
            "raw_complete_logs_not_necessarily_complete_searches"
        ])
        raw["logs_with_partition_ratios"] = 2
        raw["logs_without_partition_ratios"] = raw["eligible_logs"] - 2
        raw["ratio_observation_terminal_outcome_counts"][0]["count"] = 2
        raw["partition_ratio_census"] = [
            {"partition_ratio_max": 2.0, "partition_ratio_geomean": 1.0, "count": 1},
            {"partition_ratio_max": 4.0, "partition_ratio_geomean": 2.0, "count": 1},
        ]
        for key, values in (
            ("partition_ratio_max", [2.0, 4.0]),
            ("partition_ratio_geomean", [1.0, 2.0]),
        ):
            raw["summaries"][key] = renderer._expected_structure_summary(values)
        raw["paired_direct_tuple_and_ratio_cells"] = 2
        raw["paired_W_U_partition_ratio_census"] = [
            {"W": 2, "U": 4, "partition_ratio_max": 2.0, "partition_ratio_geomean": 1.0, "count": 1},
            {"W": 4, "U": 8, "partition_ratio_max": 4.0, "partition_ratio_geomean": 2.0, "count": 1},
        ]
        for key in (
            "W_vs_partition_ratio_max", "U_vs_partition_ratio_max",
            "W_vs_partition_ratio_geomean", "U_vs_partition_ratio_geomean",
        ):
            raw["cross_task_descriptive_confounded_correlations"][key] = {
                "n": 2, "coefficient": 1.0, "null_reason": None
            }
        renderer._validate_structure_stratum(
            raw, "synthetic.raw_complete", resource_prefix=False
        )

        projection_drift = copy.deepcopy(raw)
        projection_drift["paired_W_U_partition_ratio_census"][0][
            "partition_ratio_max"
        ] = 3.0
        with self.assertRaisesRegex(renderer.RenderError, "does not project"):
            renderer._validate_structure_stratum(
                projection_drift,
                "synthetic.raw_complete",
                resource_prefix=False,
            )

        changed = copy.deepcopy(raw)
        changed["cross_task_descriptive_confounded_correlations"][
            "W_vs_partition_ratio_max"
        ]["coefficient"] = -1.0
        with self.assertRaisesRegex(renderer.RenderError, "coefficient arithmetic"):
            renderer._validate_structure_stratum(
                changed, "synthetic.raw_complete", resource_prefix=False
            )

        pool = lambda value: value["selector_candidate_pool"]
        self.assert_structure_rejected(
            lambda value: pool(value)["deduplicated_candidate_counts"].__setitem__(
                "total", 4130
            ),
            "candidate materialization arithmetic",
        )
        self.assert_structure_rejected(
            lambda value: pool(value)["materialized_W_U_census"][0].__setitem__(
                "deduplicated_candidate_count", 1376
            ),
            "materialized W/U census does not conserve",
        )
        self.assert_structure_rejected(
            lambda value: pool(value)["source_status_counts"][0].__setitem__(
                "materialized_task_pools", 1376
            ),
            "source status does not conserve",
        )

    def test_structure_identity_arrays_are_order_insensitive_and_normalized(self):
        shuffled = copy.deepcopy(self.structure)
        shuffled["configs"].reverse()
        for config in shuffled["configs"]:
            direct = config["direct_W_A_V_T_U"]
            direct["tuple_census"].reverse()
            for stratum in config["partition_ratios"].values():
                stratum["terminal_outcome_counts"].reverse()
                stratum["ratio_observation_terminal_outcome_counts"].reverse()
                stratum["partition_ratio_census"].reverse()
                if "paired_W_U_partition_ratio_census" in stratum:
                    stratum["paired_W_U_partition_ratio_census"].reverse()
        pool = shuffled["selector_candidate_pool"]
        pool["deduplicated_candidates_per_pool_histogram"].reverse()
        pool["source_status_counts"].reverse()
        pool["materialized_W_U_census"].reverse()
        raw = renderer.canonical_json(shuffled).encode("ascii") + b"\n"
        digest = hashlib.sha256(raw).hexdigest()
        shuffled_data = renderer._paper_data_with_test_pins(
            self.analysis,
            self.digest,
            launch_pins=self.launch_pins,
            structure=shuffled,
            structure_sha256=digest,
            p5_analysis=self.p5_analysis,
            p5_analysis_sha256=self.p5_digest,
        )
        shuffled_tex = renderer._render_tex_with_test_pins(
            self.analysis,
            self.digest,
            launch_pins=self.launch_pins,
            structure=shuffled,
            structure_sha256=digest,
            p5_analysis=self.p5_analysis,
            p5_analysis_sha256=self.p5_digest,
        )
        normalized_tex = shuffled_tex.replace(
            digest.encode("ascii"), self.structure_digest.encode("ascii")
        ).replace(
            renderer.sha256_json(shuffled_data).encode("ascii"),
            renderer.sha256_json(self.paper_data).encode("ascii"),
        )
        self.assertEqual(normalized_tex, self.tex)
        shuffled_data["structure_sha256"] = self.structure_digest
        self.assertEqual(
            renderer.canonical_json(shuffled_data),
            renderer.canonical_json(self.paper_data),
        )

    def test_p5_schema_identity_matrix_count_and_arithmetic_fail_closed(self):
        self.assert_p5_rejected(
            lambda value: value.__setitem__("schema", "changed"),
            "P5 analysis.schema",
        )
        self.assert_p5_rejected(
            lambda value: value["execution"].__setitem__(
                "properties_canonical_sha256", hashlib.sha256(b"drift").hexdigest()
            ),
            "P5 execution identity",
        )
        self.assert_p5_rejected(
            lambda value: value["execution"].__setitem__(
                "option_matrix_sha256", hashlib.sha256(b"matrix drift").hexdigest()
            ),
            "P5 execution identity",
        )
        for key, changed in (
            ("task_count", 91),
            ("domain_count", 45),
            ("config_count", 6),
            ("cell_count", 643),
        ):
            self.assert_p5_rejected(
                lambda value, key=key, changed=changed: value["execution"].__setitem__(
                    key, changed
                ),
                "P5 execution identity",
            )
        self.assert_p5_rejected(
            lambda value: value["secondary"]["configs"][0]["coverage"].__setitem__(
                "rate", 0.0
            ),
            "coverage.rate arithmetic",
        )
        self.assert_p5_rejected(
            lambda value: value["secondary"]["configs"][0].__setitem__(
                "micro_par2_seconds", 0.0
            ),
            "micro_par2_seconds arithmetic",
        )
        self.assert_p5_rejected(
            lambda value: value["secondary"]["configs"][-1][
                "cofactor_width"
            ].__setitem__("maximum", 2),
            "width maximum changed",
        )
        self.assert_p5_rejected(
            lambda value: value["primary"]["domain_contributions"][0][
                "difference"
            ].__setitem__("numerator", 9),
            "exact fraction",
        )

        stale = copy.deepcopy(self.p5_analysis)
        stale["execution"]["properties_canonical_sha256"] = hashlib.sha256(
            b"changed in-memory P5"
        ).hexdigest()
        with self.assertRaisesRegex(renderer.RenderError, "in-memory P5 analysis"):
            renderer._paper_data_with_test_pins(
                self.analysis,
                self.digest,
                launch_pins=self.launch_pins,
                structure=self.structure,
                structure_sha256=self.structure_digest,
                p5_analysis=stale,
                p5_analysis_sha256=self.p5_digest,
            )
        stale_raw = renderer.canonical_json(stale).encode("ascii") + b"\n"
        stale_digest = hashlib.sha256(stale_raw).hexdigest()
        with self.assertRaisesRegex(renderer.RenderError, "pinned digest"):
            renderer._paper_data_with_test_pins(
                self.analysis,
                self.digest,
                launch_pins=self.launch_pins,
                structure=self.structure,
                structure_sha256=self.structure_digest,
                p5_analysis=stale,
                p5_analysis_sha256=stale_digest,
            )
        with self.assertRaisesRegex(renderer.RenderError, "supplied together"):
            renderer._paper_data_with_test_pins(
                self.analysis,
                self.digest,
                launch_pins=self.launch_pins,
                structure=self.structure,
                structure_sha256=self.structure_digest,
                p5_analysis=self.p5_analysis,
            )

    def test_p5_rows_are_indexed_by_label_and_reject_duplicate_or_missing(self):
        shuffled = copy.deepcopy(self.p5_analysis)
        shuffled["secondary"]["configs"].reverse()
        shuffled["secondary"]["comparisons"].reverse()
        raw = renderer.canonical_json(shuffled).encode("ascii") + b"\n"
        digest = hashlib.sha256(raw).hexdigest()
        renderer._validate_p5_analysis(shuffled, digest)
        shuffled_data = renderer._p5_paper_input(shuffled, digest)
        self.assertEqual(
            [row["label"] for row in shuffled_data["configs"]],
            list(renderer.CONFIG_LABELS),
        )
        original_data = renderer._p5_paper_input(
            self.p5_analysis, self.p5_digest
        )
        for row in shuffled_data["configs"]:
            row_original = next(
                entry
                for entry in original_data["configs"]
                if entry["label"] == row["label"]
            )
            self.assertEqual(
                {key: value for key, value in row.items()},
                {key: value for key, value in row_original.items()},
            )
        p6_by_label = {row["label"]: row for row in self.paper_data["configs"]}
        shuffled_rows = [
            renderer._combined_stage_row(row, p6_by_label[row["label"]])
            for row in shuffled_data["configs"]
        ]
        original_rows = [
            renderer._combined_stage_row(row, p6_by_label[row["label"]])
            for row in original_data["configs"]
        ]
        self.assertEqual(shuffled_rows, original_rows)

        self.assert_p5_rejected(
            lambda value: value["secondary"]["configs"][-1].__setitem__(
                "label", value["secondary"]["configs"][0]["label"]
            ),
            "duplicate label",
        )
        self.assert_p5_rejected(
            lambda value: value["secondary"]["configs"].pop(),
            "must contain 7 entries",
        )
        self.assert_p5_rejected(
            lambda value: value["secondary"]["comparisons"][-1].__setitem__(
                "name", value["secondary"]["comparisons"][0]["name"]
            ),
            "duplicate name",
        )

    def test_p5_loader_rejects_hash_sidecar_canonical_and_symlink_drift(self):
        with tempfile.TemporaryDirectory(prefix="renderer-p5-loader-") as raw_dir:
            root = Path(raw_dir)
            artifact = root / "analysis-v3.json"
            sidecar = Path(str(artifact) + ".sha256")
            artifact.write_bytes(self.p5_raw)
            sidecar.write_bytes(
                "{}  {}\n".format(self.p5_digest, artifact.name).encode("ascii")
            )
            loaded, digest = renderer._load_p5_analysis_with_expected_sha(
                artifact, expected_analysis_sha256=self.p5_digest
            )
            self.assertEqual(loaded, self.p5_analysis)
            self.assertEqual(digest, self.p5_digest)

            artifact.write_bytes(self.p5_raw[:-2] + b" \n")
            with self.assertRaisesRegex(renderer.RenderError, "pinned digest"):
                renderer._load_p5_analysis_with_expected_sha(
                    artifact, expected_analysis_sha256=self.p5_digest
                )

            artifact.write_bytes(self.p5_raw)
            sidecar.write_bytes(
                "{} *{}\n".format(self.p5_digest, artifact.name).encode("ascii")
            )
            with self.assertRaisesRegex(renderer.RenderError, "sidecar"):
                renderer._load_p5_analysis_with_expected_sha(
                    artifact, expected_analysis_sha256=self.p5_digest
                )

            noncanonical = self.p5_raw[:-1] + b" \n"
            noncanonical_digest = hashlib.sha256(noncanonical).hexdigest()
            artifact.write_bytes(noncanonical)
            sidecar.write_bytes(
                "{}  {}\n".format(noncanonical_digest, artifact.name).encode(
                    "ascii"
                )
            )
            with self.assertRaisesRegex(renderer.RenderError, "canonical ASCII JSON"):
                renderer._load_p5_analysis_with_expected_sha(
                    artifact, expected_analysis_sha256=noncanonical_digest
                )

            target = root / "real-analysis-v3.json"
            target.write_bytes(self.p5_raw)
            artifact.unlink()
            artifact.symlink_to(target)
            sidecar.write_bytes(
                "{}  {}\n".format(self.p5_digest, artifact.name).encode("ascii")
            )
            with self.assertRaises(renderer.RenderError):
                renderer._load_p5_analysis_with_expected_sha(
                    artifact, expected_analysis_sha256=self.p5_digest
                )

    def test_p5_path_is_fixed_confined_and_symlink_safe(self):
        with tempfile.TemporaryDirectory(prefix="renderer-p5-path-") as raw_dir:
            root = Path(raw_dir)
            expected = root / "artifacts" / "p5" / "analysis-v3.json"
            expected.parent.mkdir(parents=True)
            expected.write_bytes(self.p5_raw)
            self.assertEqual(
                renderer._validate_p5_input_path(
                    expected, expected=expected, root=root
                ),
                expected,
            )
            with self.assertRaisesRegex(renderer.RenderError, "restricted"):
                renderer._validate_p5_input_path(
                    root / "other.json", expected=expected, root=root
                )
            outside = root.parent / "p5-outside.json"
            with self.assertRaisesRegex(renderer.RenderError, "outside"):
                renderer._validate_p5_input_path(
                    outside, expected=outside, root=root
                )

            expected.unlink()
            target = root / "target.json"
            target.write_bytes(self.p5_raw)
            expected.symlink_to(target)
            with self.assertRaisesRegex(renderer.RenderError, "symlink component"):
                renderer._validate_p5_input_path(
                    expected, expected=expected, root=root
                )

        with tempfile.TemporaryDirectory(prefix="renderer-p5-parent-") as raw_dir:
            root = Path(raw_dir)
            real = root / "real"
            real.mkdir()
            (root / "linked").symlink_to(real, target_is_directory=True)
            expected = root / "linked" / "analysis-v3.json"
            (real / "analysis-v3.json").write_bytes(self.p5_raw)
            with self.assertRaisesRegex(renderer.RenderError, "symlink component"):
                renderer._validate_p5_input_path(
                    expected, expected=expected, root=root
                )

    def test_cli_p5_input_defaults_to_fixed_path_and_self_test_rejects_override(self):
        args = renderer.parse_args(["--self-test"])
        self.assertEqual(args.p5_analysis, renderer.DEFAULT_P5_ANALYSIS)
        self.assertEqual(args.structure, renderer.DEFAULT_STRUCTURE)
        self.assertEqual(args.structure_sidecar, renderer.DEFAULT_STRUCTURE_SIDECAR)
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                renderer.parse_args(
                    [
                        "--self-test",
                        "--p5-analysis",
                        "elsewhere/analysis-v3.json",
                    ]
                )
        with mock.patch("sys.stderr"):
            with self.assertRaises(SystemExit):
                renderer.parse_args(
                    ["--self-test", "--structure", "elsewhere/structure-v1.json"]
                )
        with self.assertRaisesRegex(renderer.RenderError, "restricted"):
            renderer.load_p5_analysis(Path("elsewhere/analysis-v3.json"))
        with self.assertRaisesRegex(renderer.RenderError, "restricted"):
            renderer._validate_structure_input_path(
                Path("elsewhere/structure-v1.json")
            )
        with tempfile.TemporaryDirectory(prefix="structure-path-") as raw_dir:
            root = Path(raw_dir)
            real = root / "real"
            real.mkdir()
            (real / "structure-v1.json").write_bytes(self.structure_raw)
            (root / "linked").symlink_to(real, target_is_directory=True)
            expected = root / "linked" / "structure-v1.json"
            with self.assertRaisesRegex(renderer.RenderError, "symlink component"):
                renderer._validate_structure_input_path(
                    expected, expected=expected, root=root
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
        self.assertIn("ArrFullCombinedStageRows", macros)
        self.assertIn("ArrFullPairedMetricRows", macros)
        self.assertIn("ArrFullDomainCoverageRows", macros)
        self.assertIn("ArrFullTerminalOutcomeRows", macros)
        self.assertIn("ArrFullTerminalOutcomePerConfigRows", macros)
        for expected in renderer.CONFIGS:
            self.assertIn(expected["paper_label"], text)

    def test_combined_stage_rows_have_exact_descriptive_five_column_schema(self):
        text = self.tex.decode("utf-8")
        match = re.search(
            r"\\newcommand\{\\ArrFullCombinedStageRows\}\{%\n(.*?)\n\}",
            text,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        rows = match.group(1).splitlines()
        self.assertEqual(len(rows), len(renderer.CONFIGS))
        p5_by_label = {
            row["label"]: row for row in self.paper_data["p5_heldout"]["configs"]
        }
        p6_by_label = {row["label"]: row for row in self.paper_data["configs"]}
        expected_rows = [
            renderer._combined_stage_row(p5_by_label[label], p6_by_label[label])
            for label in renderer.CONFIG_LABELS
        ]
        self.assertEqual(rows, expected_rows)
        for row in rows:
            self.assertEqual(len(row.removesuffix(" \\\\%").split(" & ")), 5)
        self.assertEqual(
            rows[0],
            "Blind forward & $40/92$ & 348.1627 & ${}/1{{,}}377$ & {} \\\\%".format(
                renderer._tex_int(p6_by_label["blind_fw"]["coverage"]["solved"]),
                renderer._decimal(
                    p6_by_label["blind_fw"]["micro_par2_seconds"], 4
                ),
            ),
        )
        self.assertIn(
            "% Combined-stage rows are within-stage descriptive summaries only; "
            "no between-stage causal contrast.",
            text,
        )
        self.assertIn(renderer.COMBINED_STAGE_CAVEAT, text)
        self.assertNotIn("between-stage delta", match.group(0).lower())

        macros = set(re.findall(r"\\newcommand\{\\([A-Za-z]+)\}", text))
        for name in (
            "ArrFullPfiveTaskDenominator",
            "ArrFullPsixTaskDenominator",
            "ArrFullPfiveDomainDenominator",
            "ArrFullPsixDomainDenominator",
            "ArrFullPfiveCellDenominator",
            "ArrFullPsixCellDenominator",
            "ArrFullCombinedStageCaveat",
            "ArrFullPfiveAnalysisSha",
            "ArrFullPfivePropertiesSha",
            "ArrFullPfiveAnalysisSchema",
            "ArrFullPfiveProtocol",
            "ArrFullPfiveProtocolRevision",
        ):
            self.assertIn(name, macros)
        self.assertIn(
            "\\newcommand{\\ArrFullPfiveTaskDenominator}{92}", text
        )
        self.assertIn(
            "\\newcommand{\\ArrFullPsixTaskDenominator}{1{,}377}", text
        )
        for expected in renderer.CONFIGS:
            for stage in ("Pfive", "Psix"):
                self.assertIn(
                    "ArrFull{}{}Solved".format(stage, expected["suffix"]), macros
                )
                self.assertIn(
                    "ArrFull{}{}ParTwo".format(stage, expected["suffix"]), macros
                )

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
            shuffled,
            shuffled_digest,
            launch_pins=self.launch_pins,
            structure=self.structure,
            structure_sha256=self.structure_digest,
            p5_analysis=self.p5_analysis,
            p5_analysis_sha256=self.p5_digest,
        )
        shuffled_tex = renderer._render_tex_with_test_pins(
            shuffled,
            shuffled_digest,
            launch_pins=self.launch_pins,
            structure=self.structure,
            structure_sha256=self.structure_digest,
            p5_analysis=self.p5_analysis,
            p5_analysis_sha256=self.p5_digest,
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

            structure_artifact = root / "structure-v1.json"
            structure_sidecar = Path(str(structure_artifact) + ".sha256")
            structure_artifact.write_bytes(self.structure_raw)
            structure_sidecar.write_text(
                "{}  {}\n".format(self.structure_digest, structure_artifact.name),
                encoding="ascii",
            )
            loaded_structure, loaded_structure_digest = (
                renderer._load_frozen_structure_with_test_pin(
                    structure_artifact,
                    expected_structure_sha256=self.structure_digest,
                    analysis=self.analysis,
                    analysis_sha256=self.digest,
                    launch_pins=self.launch_pins,
                )
            )
            self.assertEqual(loaded_structure, self.structure)
            self.assertEqual(loaded_structure_digest, self.structure_digest)
            structure_sidecar.write_text(
                "{} *{}\n".format(self.structure_digest, structure_artifact.name),
                encoding="ascii",
            )
            with self.assertRaisesRegex(renderer.RenderError, "structure sidecar"):
                renderer._load_frozen_structure_with_test_pin(
                    structure_artifact,
                    expected_structure_sha256=self.structure_digest,
                    analysis=self.analysis,
                    analysis_sha256=self.digest,
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
        partial["analysis_sha256"] = None
        with self.assertRaisesRegex(renderer.RenderError, "partially set"):
            renderer._reviewed_production_pins_from(partial)

        overrides = {
            "EXPECTED_FULL_ANALYSIS_SHA256": self.digest,
            "EXPECTED_FULL_STRUCTURE_SHA256": self.structure_digest,
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
            for call in (
                lambda: renderer.validate_analysis(self.analysis, self.digest),
                lambda: renderer.paper_data(self.analysis, self.digest),
                lambda: renderer.render_tex(self.analysis, self.digest),
            ):
                with self.assertRaisesRegex(renderer.RenderError, "structure value"):
                    call()
            renderer.validate_analysis(
                self.analysis,
                self.digest,
                structure=self.structure,
                structure_sha256=self.structure_digest,
            )
            self.assertEqual(
                renderer.paper_data(
                    self.analysis,
                    self.digest,
                    structure=self.structure,
                    structure_sha256=self.structure_digest,
                ),
                self.paper_data,
            )
            self.assertEqual(
                renderer.render_tex(
                    self.analysis,
                    self.digest,
                    structure=self.structure,
                    structure_sha256=self.structure_digest,
                ),
                self.tex,
            )
            stale = copy.deepcopy(self.analysis)
            stale["execution"]["properties_canonical_sha256"] = hashlib.sha256(
                b"different in-memory value"
            ).hexdigest()
            for call in (
                lambda: renderer.validate_analysis(
                    stale, self.digest, structure=self.structure,
                    structure_sha256=self.structure_digest,
                ),
                lambda: renderer.paper_data(
                    stale, self.digest, structure=self.structure,
                    structure_sha256=self.structure_digest,
                ),
                lambda: renderer.render_tex(
                    stale, self.digest, structure=self.structure,
                    structure_sha256=self.structure_digest,
                ),
            ):
                with self.assertRaisesRegex(renderer.RenderError, "in-memory canonical"):
                    call()
            stale_p5 = copy.deepcopy(self.p5_analysis)
            stale_p5["execution"]["properties_canonical_sha256"] = hashlib.sha256(
                b"different in-memory P5 value"
            ).hexdigest()
            for call in (
                lambda: renderer.paper_data(
                    self.analysis,
                    self.digest,
                    structure=self.structure,
                    structure_sha256=self.structure_digest,
                    p5_analysis=stale_p5,
                    p5_analysis_sha256=self.p5_digest,
                ),
                lambda: renderer.render_tex(
                    self.analysis,
                    self.digest,
                    structure=self.structure,
                    structure_sha256=self.structure_digest,
                    p5_analysis=stale_p5,
                    p5_analysis_sha256=self.p5_digest,
                ),
            ):
                with self.assertRaisesRegex(
                    renderer.RenderError, "in-memory P5 analysis"
                ):
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
                lambda: renderer.validate_analysis(
                    canceled, canceled_digest, structure=self.structure,
                    structure_sha256=self.structure_digest,
                ),
                lambda: renderer.paper_data(
                    canceled, canceled_digest, structure=self.structure,
                    structure_sha256=self.structure_digest,
                ),
                lambda: renderer.render_tex(
                    canceled, canceled_digest, structure=self.structure,
                    structure_sha256=self.structure_digest,
                ),
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

    def test_ordinary_gate_uses_the_atomically_reviewed_production_pins(self):
        expected = {
            "analysis_sha256": (
                "39958f1984d9c33fc2717ef221881751e24dc68434932b6ea9b92e4dd3f2b1c5"
            ),
            "structure_sha256": (
                "bde07d0d2e279b5f8e06b5e59eb67aa7f513a1fae58f101fa0e87bc01030cc69"
            ),
            "protocol": "arrhenius-selector-full-population-v4",
            "protocol_revision": "0cb19e111da36fbb32d1b3bc0f07a52b733fbbe9",
            "full_runner_source_sha256": (
                "3a7cfd4307217db13a8ec42d9157cd2290b0e8fba962f9aa40815af80d06058f"
            ),
            "planner_revision": "a3486a027a0f281e762cb6d66d72311455b66b33",
            "planner_binary_sha256": (
                "2887194c74acc88273702b807dba28e4fd8f7ae3d916562bcf1b83ec79632758"
            ),
            "planner_preprocess_sha256": (
                "40e1d5580ec447cb606ead447317469bd861bd8cda398095df3fbf22922d0d23"
            ),
            "prospective_start_job_sha256": (
                "c83c880c1bfaa503cfffab69c91abb037e58b4424b7216480aa551631aed043f"
            ),
        }
        self.assertEqual(renderer._production_pin_values(), expected)
        reviewed = renderer.reviewed_production_pins()
        self.assertEqual(reviewed["analysis_sha256"], expected["analysis_sha256"])
        self.assertEqual(reviewed["structure_sha256"], expected["structure_sha256"])
        self.assertEqual(
            reviewed["launch"],
            {key: expected[key] for key in renderer.LAUNCH_PIN_KEYS},
        )

        analysis, analysis_sha256 = renderer.load_frozen_analysis(
            renderer.DEFAULT_ANALYSIS
        )
        structure_value, structure_sha256 = renderer.load_frozen_structure(
            analysis=analysis,
            analysis_sha256=analysis_sha256,
        )
        self.assertEqual(analysis_sha256, expected["analysis_sha256"])
        self.assertEqual(structure_sha256, expected["structure_sha256"])
        renderer.validate_analysis(
            analysis,
            analysis_sha256,
            structure=structure_value,
            structure_sha256=structure_sha256,
        )


if __name__ == "__main__":
    unittest.main()
