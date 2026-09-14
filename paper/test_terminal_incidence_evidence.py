"""Synthetic regression tests for the committed-evidence paper projector."""

from __future__ import annotations

import copy
import json
import unittest
from fractions import Fraction
from unittest import mock

import render_terminal_incidence_results as R
import terminal_incidence_evidence as E
import test_render_terminal_incidence_results as Fixtures


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def native_a(normalized):
    """Reverse the documented analyzer field mapping on a synthetic fixture."""
    def comparison(value):
        return {
            "support": {
                "tasks_with_shared_pairs": value["comparison_tasks"],
                "families_with_shared_pairs": value["comparison_families"],
                "target_strict": value["target_strict_pairs"],
            },
            "target_orientations": {
                "orders_identical": value["orientation"]["orders_identical"],
                "inverse_U_null": "tied_within_task",
            },
            "predictors": {
                E.PREDICTOR_NAMES[name]: {"equal_family": {"macro": (
                    value["i_concordance"] if name == "incidence"
                    else value["baselines"][name]["concordance"]
                )}} for name in E.PREDICTOR_NAMES
            },
        }

    def gate(value):
        return {"controls": {
            E.PREDICTOR_NAMES[name]: {
                "advantage": item["margin"],
                "bootstrap": {"lower_95": item["bootstrap_lower"], "upper_95": item["bootstrap_upper"]},
                "leave_one_family_out_differences": {"family": item["lofo_minimum"]},
            } for name, item in value["baselines"].items()
        }}

    strict = normalized["all_strict"]
    regret = normalized["oracle_regret"]
    tightness = normalized["certificate_tightness"]
    timing = {
        key: (float(Fraction(value["numerator"], value["denominator"]))
              if type(value) is dict else value)
        for key, value in normalized["timing"].items()
    }
    return {
        "primary": {
            **{key: normalized[key] for key in (
                "eligible_tasks", "eligible_families", "frontier_statuses", "cegar_fallback_tasks",
            )},
            "construction_by_label": {f"pdb_{name}_shadow": counts
                                      for name, counts in normalized["construction_by_configuration"].items()},
        },
        "comparison": comparison(normalized),
        "gates": {"primary": gate(normalized)},
        "strata": {"all_prior_unrepresented": {
            "comparison": comparison(normalized["all_prior"]),
            "gate": gate(normalized["all_prior"]),
        }},
        "sensitivity": {
            "all_predictor_strict": {
                "support": {
                    "tasks_with_shared_pairs": strict["comparison_tasks"],
                    "families_with_shared_pairs": strict["comparison_families"],
                    "grand_shared_strict": strict["pairs"],
                },
                "predictors": {E.PREDICTOR_NAMES[name]: {"equal_family": {"macro": value}}
                               for name, value in strict["predictors"].items()},
            },
            "top_choice_regret": {
                "support": {"eligible_tasks": regret["tasks"], "eligible_families": regret["families"]},
                "predictors": {E.PREDICTOR_NAMES[name]: {
                    "equal_family_normalized_regret": value["equal_family_regret"],
                    "top_choice_tie_rate": value["tie_rate"],
                } for name, value in regret["predictors"].items()},
            },
        },
        "secondary_diagnostics": {
            "tightness": {E.PREDICTOR_NAMES[name]: {
                "tasks": tightness["tasks"], "families": tightness["families"],
                "equal_family_macro": value["equal_family"],
                "family_quantiles_nearest_rank": {key: value[key] for key in ("q25", "q50", "q75")},
            } for name, value in tightness["predictors"].items()},
            "computation_time": timing,
        },
    }


class ProjectionTests(unittest.TestCase):
    def test_v12_adapter_projection_conserves_all_source_classes(self):
        E._imports()
        import test_freeze_pdb_terminal_incidence_confirmation_a_v12 as F
        result = E.source_summary(F.authorized_v12())
        self.assertEqual(result["campaign_number"], 12)
        self.assertEqual(result["translated_successfully"], 1637)
        self.assertEqual(result["supported_tasks"], 1636)
        self.assertEqual(result["unsupported_tasks"], 2)
        self.assertEqual(result["indeterminate_tasks"], 2)
        self.assertEqual(result["resource_exclusion_counts"], {"time": 1, "memory": 1})
        self.assertEqual(result["a_tasks"] + result["b_tasks"] + result["unassigned_supported_tasks"], 1636)
        self.assertNotIn("primary_exclusion_counts", result)

    def test_native_a_mapping_preserves_every_numeric_field_and_branch(self):
        for passed in (False, True):
            fixture = Fixtures.fixture(a_pass=passed, direct_pass=True if passed else None,
                                       b_pass=True if passed else None)
            native = native_a(fixture["confirmation_a"])
            expected = copy.deepcopy(fixture["confirmation_a"])
            # The analyzer records this non-gating timing mean as a float.
            expected["timing"]["equal_family_mean_of_task_ratios"] = E._numeric_fraction(
                native["secondary_diagnostics"]["computation_time"]["equal_family_mean_of_task_ratios"]
            )
            self.assertEqual(E.normalize_a(native), expected)
            fixture["confirmation_a"] = E.normalize_a(native)
            self.assertIs(R.classify(fixture).a_pass, passed)

    def test_unknown_attrition_is_not_silently_dropped(self):
        fixture = Fixtures.fixture(a_pass=False, direct_pass=None, b_pass=None)
        for field in ("frontier_statuses", "construction_by_label"):
            native = native_a(fixture["confirmation_a"])
            target = native["primary"][field]
            if field == "construction_by_label":
                target = target["pdb_cegar_shadow"]
            target["new-unhandled-outcome"] = 1
            with self.subTest(field=field), self.assertRaises(E.EvidenceError):
                E.normalize_a(native)

    def test_timing_float_roundoff_does_not_create_a_false_exact_ratio(self):
        fixture = Fixtures.fixture(a_pass=False, direct_pass=None, b_pass=None)
        native = native_a(fixture["confirmation_a"])
        timing = native["secondary_diagnostics"]["computation_time"]
        timing.update(pooled_masked_seconds=0.1, pooled_partition_audit_seconds=0.3,
                      pooled_masked_over_partition_ratio=0.1 / 0.3)
        output = E.normalize_a(native)["timing"]
        ratio = output["pooled_masked_over_partition_ratio"]
        self.assertEqual(Fraction(ratio["numerator"], ratio["denominator"]), Fraction(0.1) / Fraction(0.3))
        R._validate_a_timing(output, "timing")
        timing["pooled_masked_over_partition_ratio"] = 0.5
        with self.assertRaisesRegex(E.EvidenceError, "timing ratio"):
            E.normalize_a(native)

    def test_invalid_revision_and_missing_pins_fail_before_artifact_io(self):
        pins = {"source_audit": "1" * 64, "confirmation_a": "2" * 64,
                "confirmation_b": None, "direct_metric_choice": None}
        for revision in (None, "@-", "a" * 39, "a" * 41):
            with mock.patch.object(E, "_read_artifacts") as reader:
                with self.assertRaisesRegex(E.EvidenceError, "explicit 40-hex"):
                    E.load_evidence(source_revision=revision, results_revision="b" * 40,
                                    artifact_pins={}, result_pins=pins, expected_a_pass=False)
                reader.assert_not_called()
        with mock.patch.object(E, "_imports") as imports:
            with self.assertRaisesRegex(E.EvidenceError, "artifact-pin roles"):
                E._read_artifacts("a" * 40, E.A_PATHS, {})
            imports.assert_not_called()

    def test_noncanonical_and_duplicate_json_keys_fail(self):
        for raw in (b'{"x":1}', b'{"x":1,"x":1}\n', b'{"x":NaN}\n', b'[]\n'):
            with self.subTest(raw=raw), self.assertRaises(E.EvidenceError):
                E._canonical(raw, "test")

    def test_hardware_projection_has_exact_numeric_interface(self):
        E._imports()
        import pdb_confirmation_run_cell as Cell
        hardware = {
            "hardware_attestation_schema": Cell.HARDWARE_ATTESTATION_SCHEMA,
            "hardware_attestation_files": 2600,
            "hardware_records_sha256": "a" * 64,
            "processor_model_counts": {"Synthetic CPU": 2600},
            "architecture_counts": {"x86_64": 2600},
        }
        result = E._hardware(hardware, 2600)
        R._validate_campaign_hardware(result, "hardware", 2600)
        self.assertEqual(result, {"receipt_sealed": True, "cells": 2600,
                                  "processor_models": 1, "architectures": 1})

    def test_double_analysis_rejects_changed_bytes_links_and_gate(self):
        hardware = {"synthetic": True}
        execution_raw = canonical({"hardware": hardware})
        fetch_raw = canonical({"properties_sha256": "a" * 64})
        result = {
            "input": {
                "sha256": "a" * 64, "fetch_receipt_sha256": E._sha(fetch_raw),
                "execution_receipt_sha256": E._sha(execution_raw), "hardware": hardware,
            },
            "gates": {"pass": False}, "guided_study_authorized": False,
        }
        result_raw = canonical(result)
        receipt = {
            "first_output_sha256": E._sha(result_raw), "second_output_sha256": E._sha(result_raw),
            "outputs_byte_identical": True, "input_properties_sha256": "a" * 64,
            "execution_receipt_sha256": E._sha(execution_raw),
            "fetch_receipt_sha256": E._sha(fetch_raw), "hardware": hardware,
            "confirmation_a_complete_gate_passed": False, "guided_study_authorized": False,
        }
        raw = {
            "a_result": result_raw, "a_repeat": result_raw,
            "a_receipt": canonical(receipt), "a_execution": execution_raw, "a_fetch": fetch_raw,
        }
        for name in ("receipt", "execution", "fetch"):
            raw[f"a_{name}_pin"] = (E._sha(raw[f"a_{name}"]) + "\n").encode("ascii")
        self.assertEqual(E._check_double_analysis(raw, "a", False), (result, receipt))
        for field in ("a_repeat", "a_receipt_pin", "a_execution", "a_fetch"):
            changed = dict(raw)
            changed[field] += b" "
            with self.subTest(field=field), self.assertRaises(E.EvidenceError):
                E._check_double_analysis(changed, "a", False)
        with self.assertRaisesRegex(E.EvidenceError, "outcome branch"):
            E._check_double_analysis(raw, "a", True)
        changed = dict(raw)
        bad_receipt = {**receipt, "fetch_receipt_sha256": "b" * 64}
        changed["a_receipt"] = canonical(bad_receipt)
        changed["a_receipt_pin"] = (E._sha(changed["a_receipt"]) + "\n").encode("ascii")
        with self.assertRaisesRegex(E.EvidenceError, "double-analysis chain"):
            E._check_double_analysis(changed, "a", False)

    def test_failed_a_checks_downstream_absence_without_payload_reads(self):
        with mock.patch.object(E.os.path, "lexists", return_value=False) as exists:
            E._require_downstream_absence()
            self.assertEqual(exists.call_count, len(E.DOWNSTREAM_PATHS))
        with mock.patch.object(E.os.path, "lexists", return_value=True):
            with self.assertRaisesRegex(E.EvidenceError, "absent downstream"):
                E._require_downstream_absence()


if __name__ == "__main__":
    unittest.main()
