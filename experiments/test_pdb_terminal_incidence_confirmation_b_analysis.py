#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from unittest import mock

import analyze_pdb_terminal_incidence_confirmation_b as A
import pdb_cap_selector_parser as CapParser
import pdb_confirmation_run_cell as RunCell
import pdb_terminal_incidence_confirmation_b_protocol as P


HARDWARE = {
    "hardware_attestation_schema": RunCell.HARDWARE_ATTESTATION_SCHEMA,
    "hardware_attestation_files": 2700,
    "hardware_records_sha256": "3" * 64,
    "processor_model_counts": {"Synthetic CPU": 2700},
    "architecture_counts": {"x86_64": 2700},
}


def _selector_record(*, status="complete", differs=False, selected=None):
    pool = [{
        "pattern_index": 0,
        "sources": ["empty"],
        "pattern": [],
        "abstract_states": 1,
        "within_state_budget": True,
    }]
    structural = [
        {"event": "schema"},
        {"event": "probe", "g_values": [0]},
    ]
    if status == "complete":
        structural.append({"event": "pool", "patterns": pool})
    reference_identity = {
        "pattern_index": 0,
        "sources": ["empty"],
        "pattern": [],
        "value_cap": None,
        "terminal_incidence": 1,
    }
    selected_identity = {
        **reference_identity,
        "value_cap": selected,
    }
    value = {
        "coverage": 0 if status == "short_probe" else 1,
        "planner_exit_code": 34 if status == "short_probe" else 0,
        "incidence_selector_trace_schema": P.SELECTOR_TRACE_SCHEMA,
        "incidence_selector_trace_status": status,
        "incidence_selector_trace_certified": True,
        "incidence_selector_trace_validation_error": None,
        "incidence_selector_structural_trace": structural,
        "incidence_selector_structural_trace_sha256": hashlib.sha256(
            P.canonical_json(structural)
        ).hexdigest(),
        "incidence_selector_pool_sha256": "2" * 64 if status == "complete" else None,
        "incidence_selector_preselection_sha256": (
            "3" * 64 if status == "complete" else None
        ),
        "incidence_selector_reference_identity": (
            reference_identity if status == "complete" else None
        ),
        "incidence_selector_selected_identity": (
            selected_identity if status == "complete" else None
        ),
        "incidence_selector_selected_differs_from_reference": differs,
        "incidence_selector_probe_completed_layers": (
            16 if status == "complete" else 3
        ),
        "incidence_selector_probe_cpu_seconds": 1.0,
        "incidence_selector_probe_wall_seconds": 1.1,
        "incidence_selector_probe_peak_memory_before_kb": 100,
        "incidence_selector_probe_peak_memory_after_kb": 120,
        "incidence_selector_probe_peak_memory_delta_kb": 20,
    }
    if status == "complete":
        value.update({
            "incidence_selector_selection_cpu_seconds": 2.0,
            "incidence_selector_selection_wall_seconds": 2.1,
            "incidence_selector_selection_peak_memory_before_kb": 120,
            "incidence_selector_selection_peak_memory_after_kb": 150,
            "incidence_selector_selection_peak_memory_delta_kb": 30,
        })
    return value


def _matrix(
    tasks, *, guided=10, plain=3600, matched=3600,
    non_gating=3600, differs=True,
):
    matrix = {}
    for task in tasks:
        matrix[(P.GUIDED_LABEL, task)] = {
            "record": _selector_record(differs=differs, selected=0),
            "par2": Fraction(guided),
        }
        matrix[(P.MATCHED_LABEL, task)] = {
            "record": _selector_record(differs=False, selected=None),
            "par2": Fraction(matched),
        }
        matrix[(P.PLAIN_REFERENCE_LABEL, task)] = {
            "record": {"coverage": int(plain < P.PAR2_SECONDS)},
            "par2": Fraction(plain),
            "plain_reference_identity": {
                "pattern_index": 0,
                "sources": ["empty"],
                "pattern": [],
                "value_cap": None,
            },
            "plain_reference_pool": [{
                "pattern_index": 0,
                "sources": ["empty"],
                "pattern": [],
                "abstract_states": 1,
                "within_state_budget": True,
            }],
            "plain_reference_pool_sha256": "4" * 64,
        }
        for label in P.NON_GATING_REFERENCE_LABELS:
            matrix[(label, task)] = {
                "record": {"coverage": int(non_gating < P.PAR2_SECONDS)},
                "par2": Fraction(non_gating),
            }
    return matrix


class OutcomeTest(unittest.TestCase):
    def test_analysis_v3_schema_and_paths(self):
        self.assertEqual(
            A.SCHEMA,
            "symbolic-search-heuristics/"
            "pdb-terminal-incidence-confirmation-b-analysis/v3",
        )
        self.assertEqual(A.DEFAULT_OUTPUT.name, "analysis-v3.json")
        self.assertEqual(A.DEFAULT_REPEAT_OUTPUT.name, "analysis-v3-repeat.json")
        self.assertEqual(
            A.DEFAULT_RECEIPT.name,
            "analysis-execution-receipt-v3.json",
        )

    def test_every_failure_is_fixed_par2(self):
        for code in (10, 22, 23, 24, 34, 99):
            value, outcome = A._par2({
                "coverage": 0, "planner_exit_code": code,
            })
            self.assertEqual(value, P.PAR2_SECONDS)
            self.assertIn(outcome, {"short_probe", "unsolved_or_failure"})

    def test_solved_runtime_is_not_replaced_by_search_only_time(self):
        value, outcome = A._par2({
            "coverage": 1,
            "planner_exit_code": 0,
            "total_time": 123.5,
            "search_time": 2.0,
        })
        self.assertEqual(value, Fraction("123.5"))
        self.assertEqual(outcome, "solved")

    def test_coverage_exit_and_time_limit_contradictions_fail_closed(self):
        cases = (
            {"coverage": 1, "planner_exit_code": 34, "total_time": 1},
            {"coverage": 1, "planner_exit_code": 23, "total_time": 1},
            {"coverage": 0, "planner_exit_code": 0},
            {
                "coverage": 1,
                "planner_exit_code": 0,
                "total_time": P.TIME_LIMIT_SECONDS + 0.001,
            },
        )
        for record in cases:
            with self.subTest(record=record):
                with self.assertRaises(A.ConfirmationBAnalysisError):
                    A._par2(record)


class GateTest(unittest.TestCase):
    def setUp(self):
        self.tasks = [("d{}".format(index), "p") for index in range(3)]
        self.sources = {
            task: {"family": "f{}".format(index)}
            for index, task in enumerate(self.tasks)
        }

    def test_primary_contrast_passes_all_frozen_clauses(self):
        matrix = _matrix(self.tasks)
        with mock.patch.object(P, "BOOTSTRAP_REPLICATES", 1000):
            result = A._contrast(
                matrix, self.tasks, self.sources, P.PLAIN_REFERENCE_LABEL
            )
        self.assertTrue(result["pass"])
        self.assertTrue(all(result["clauses"].values()))
        self.assertGreater(
            result["bootstrap"]["lower_95"]["numerator"], 0
        )

    def test_macro_threshold_and_lodo_are_binding(self):
        matrix = _matrix(self.tasks, guided=3600, plain=3600)
        with mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100):
            result = A._contrast(
                matrix, self.tasks, self.sources, P.PLAIN_REFERENCE_LABEL
            )
        self.assertFalse(result["pass"])
        self.assertFalse(result["clauses"]["family_macro_at_least_0_02"])
        self.assertFalse(
            result["clauses"]["every_leave_one_family_out_positive"]
        )

    def test_contrast_reports_paired_coverage_and_common_solved_time(self):
        tasks = [("d{}".format(index), "p") for index in range(4)]
        sources = {
            task: {"family": "family"} for task in tasks
        }
        matrix = _matrix(tasks, guided=100, plain=200)
        matrix[(P.PLAIN_REFERENCE_LABEL, tasks[1])]["record"]["coverage"] = 0
        matrix[(P.PLAIN_REFERENCE_LABEL, tasks[1])]["par2"] = Fraction(3600)
        matrix[(P.GUIDED_LABEL, tasks[2])]["record"]["coverage"] = 0
        matrix[(P.GUIDED_LABEL, tasks[2])]["par2"] = Fraction(3600)
        matrix[(P.GUIDED_LABEL, tasks[3])]["record"]["coverage"] = 0
        matrix[(P.GUIDED_LABEL, tasks[3])]["par2"] = Fraction(3600)
        matrix[(P.PLAIN_REFERENCE_LABEL, tasks[3])]["record"]["coverage"] = 0
        matrix[(P.PLAIN_REFERENCE_LABEL, tasks[3])]["par2"] = Fraction(3600)
        with mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100):
            result = A._contrast(
                matrix, tasks, sources, P.PLAIN_REFERENCE_LABEL
            )
        decomposition = result["outcome_decomposition"]
        self.assertFalse(decomposition["gating"])
        self.assertEqual(decomposition["solve_pair_counts"], {
            "both_solved": 1,
            "intervention_only_solved": 1,
            "reference_only_solved": 1,
            "neither_solved": 1,
        })
        common = decomposition["common_solved"]
        self.assertEqual(common["tasks"], 1)
        self.assertEqual(common["families"], 1)
        self.assertEqual(
            common["equal_family_normalized_time_improvement"],
            A._fraction_record(Fraction(1, 18)),
        )

    def test_common_solved_time_uses_equal_family_weight(self):
        tasks = [("d{}".format(index), "p") for index in range(3)]
        sources = {
            task: {"family": "large" if index < 2 else "small"}
            for index, task in enumerate(tasks)
        }
        matrix = _matrix(tasks, guided=100, plain=200)
        matrix[(P.GUIDED_LABEL, tasks[2])]["par2"] = Fraction(200)
        matrix[(P.PLAIN_REFERENCE_LABEL, tasks[2])]["par2"] = Fraction(100)
        with mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100):
            result = A._contrast(
                matrix, tasks, sources, P.PLAIN_REFERENCE_LABEL
            )
        common = result["outcome_decomposition"]["common_solved"]
        self.assertEqual(
            common["equal_family_normalized_time_improvement"],
            A._fraction_record(Fraction(0)),
        )

    def test_selector_pair_requires_exact_preselection_evidence(self):
        matrix = _matrix(self.tasks)
        passed, different = A._selector_pair_gate(matrix, self.tasks)
        self.assertTrue(passed["pass"])
        self.assertEqual(different, set(self.tasks))
        matrix[(P.MATCHED_LABEL, self.tasks[0])]["record"][
            "incidence_selector_preselection_sha256"
        ] = "9" * 64
        failed, _ = A._selector_pair_gate(matrix, self.tasks)
        self.assertFalse(failed["pass"])
        self.assertEqual(failed["status_counts"]["failed"], 1)

        matrix = _matrix(self.tasks)
        matrix[(P.PLAIN_REFERENCE_LABEL, self.tasks[0])][
            "plain_reference_pool"
        ][0]["abstract_states"] = 2
        failed, _ = A._selector_pair_gate(matrix, self.tasks)
        self.assertFalse(failed["pass"])
        self.assertEqual(
            failed["failed_pairs"][0]["reason"],
            "standalone_reference_pool_mismatch",
        )

    def test_selector_identity_roles_and_difference_flag_are_derived(self):
        guided = _selector_record(differs=True, selected=None)
        with self.assertRaisesRegex(
            A.ConfirmationBAnalysisError, "difference flag"
        ):
            A._validate_trace_record(guided, P.GUIDED_LABEL)
        matched = _selector_record(differs=True, selected=0)
        with self.assertRaisesRegex(
            A.ConfirmationBAnalysisError, "matched control"
        ):
            A._validate_trace_record(matched, P.MATCHED_LABEL)

        matrix = _matrix(self.tasks)
        matrix[(P.GUIDED_LABEL, self.tasks[0])]["record"].update({
            "incidence_selector_selected_identity": matrix[
                (P.GUIDED_LABEL, self.tasks[0])
            ]["record"]["incidence_selector_reference_identity"],
            "incidence_selector_selected_differs_from_reference": True,
        })
        matrix[(P.MATCHED_LABEL, self.tasks[1])]["record"].update({
            "incidence_selector_selected_identity": {"value_cap": 0},
            "incidence_selector_selected_differs_from_reference": True,
        })
        gate, different = A._selector_pair_gate(matrix, self.tasks)
        self.assertFalse(gate["pass"])
        self.assertEqual(gate["status_counts"]["failed"], 2)
        self.assertNotIn(self.tasks[0], different)

    def test_standalone_k32_identity_requires_certified_cap_trace(self):
        record = {
            "pdb_cap_selector_parser_protocol": CapParser.PARSER_PROTOCOL,
            "pdb_selector_trace_complete": True,
            "pdb_selector_trace_certified": True,
            "pdb_selector_validation_error": None,
            "pdb_selector_candidates": [{
                "pattern": [], "sources": ["empty"], "abstract_states": 1,
            }],
            "pdb_selector_selected": {
                "pattern": [],
                "sources": ["empty"],
                "value_cap": -1,
                "cofactor_width_budget": 32,
            },
            "pdb_selector_final": {"value_cap": -1},
        }
        self.assertEqual(A._plain_reference_identity(record), {
            "pattern_index": 0,
            "sources": ["empty"],
            "pattern": [],
            "value_cap": None,
        })
        record["pdb_selector_trace_certified"] = False
        with self.assertRaisesRegex(
            A.ConfirmationBAnalysisError, "certified cap-selector"
        ):
            A._plain_reference_identity(record)

    def test_short_probe_pair_is_accounted_but_not_mechanism_eligible(self):
        matrix = _matrix(self.tasks)
        task = self.tasks[0]
        for label in (P.GUIDED_LABEL, P.MATCHED_LABEL):
            matrix[(label, task)]["record"] = _selector_record(
                status="short_probe", differs=False, selected=None
            )
        gate, different = A._selector_pair_gate(matrix, self.tasks)
        self.assertTrue(gate["pass"])
        self.assertEqual(gate["certified_short_probe_pairs"], 1)
        self.assertNotIn(task, different)

    def test_certified_overhead_fields_are_required_and_revalidated(self):
        complete = _selector_record()
        A._validate_trace_record(complete, P.GUIDED_LABEL)
        for mutation in ("missing", "negative", "wrong_delta"):
            with self.subTest(mutation=mutation):
                changed = dict(complete)
                if mutation == "missing":
                    del changed["incidence_selector_probe_cpu_seconds"]
                elif mutation == "negative":
                    changed["incidence_selector_selection_wall_seconds"] = -1
                else:
                    changed[
                        "incidence_selector_probe_peak_memory_delta_kb"
                    ] = 19
                with self.assertRaises(A.ConfirmationBAnalysisError):
                    A._validate_trace_record(changed, P.GUIDED_LABEL)
        short = _selector_record(status="short_probe")
        A._validate_trace_record(short, P.GUIDED_LABEL)
        short["incidence_selector_selection_cpu_seconds"] = 1.0
        with self.assertRaises(A.ConfirmationBAnalysisError):
            A._validate_trace_record(short, P.GUIDED_LABEL)

    def test_certified_selector_metadata_is_fail_closed(self):
        cases = (
            {"incidence_selector_trace_schema": "wrong"},
            {"incidence_selector_trace_validation_error": "ignored"},
            {"incidence_selector_probe_completed_layers": 15},
        )
        for mutation in cases:
            with self.subTest(mutation=mutation):
                record = _selector_record()
                record.update(mutation)
                with self.assertRaises(A.ConfirmationBAnalysisError):
                    A._validate_trace_record(record, P.GUIDED_LABEL)
        record = _selector_record()
        structural = record["incidence_selector_structural_trace"][:2]
        record["incidence_selector_structural_trace"] = structural
        record["incidence_selector_structural_trace_sha256"] = hashlib.sha256(
            P.canonical_json(structural)
        ).hexdigest()
        with self.assertRaisesRegex(
            A.ConfirmationBAnalysisError, "lacks its pattern pool"
        ):
            A._validate_trace_record(record, P.GUIDED_LABEL)
        complete_with_short_probe_exit = _selector_record()
        complete_with_short_probe_exit.update({
            "coverage": 0,
            "planner_exit_code": 34,
        })
        with self.assertRaisesRegex(
            A.ConfirmationBAnalysisError, "short-probe exit code 34"
        ):
            A._validate_trace_record(
                complete_with_short_probe_exit, P.GUIDED_LABEL
            )
        for mutation in (
            {"incidence_selector_selected_identity": {"value_cap": 0}},
            {"incidence_selector_probe_completed_layers": 16},
            {"coverage": 1, "planner_exit_code": 0, "total_time": 1},
            {"coverage": 0, "planner_exit_code": 99},
        ):
            with self.subTest(short_mutation=mutation):
                record = _selector_record(status="short_probe")
                record.update(mutation)
                with self.assertRaisesRegex(
                    A.ConfirmationBAnalysisError, "short-probe"
                ):
                    A._validate_trace_record(record, P.GUIDED_LABEL)

    def test_mechanism_claim_requires_frozen_support_floors(self):
        matrix = _matrix(self.tasks, guided=10, matched=3600, differs=True)
        outcomes = {("blind_fw", "solved"): 3}
        accounting = [{"cell": index} for index in range(27)]
        with mock.patch.object(
            A, "validate_matrix",
            return_value=(matrix, self.tasks, self.sources, outcomes, accounting),
        ), mock.patch.object(P, "BOOTSTRAP_REPLICATES", 1000), mock.patch.object(
            P, "CELL_COUNT", 27
        ):
            result = A.analyze_records([])
        self.assertEqual(result["mechanism"]["eligible_tasks"], 3)
        self.assertFalse(result["mechanism"]["support"]["pass"])
        self.assertFalse(result["mechanism"]["claim_authorized"])

        tasks = [("d{:02d}".format(index), "p") for index in range(50)]
        sources = {
            task: {"family": "f{:02d}".format(index % 10)}
            for index, task in enumerate(tasks)
        }
        matrix = _matrix(tasks, guided=10, matched=3600, differs=True)
        accounting = [{"cell": index} for index in range(9 * len(tasks))]
        with mock.patch.object(
            A, "validate_matrix",
            return_value=(matrix, tasks, sources, outcomes, accounting),
        ), mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100), mock.patch.object(
            P, "CELL_COUNT", 9 * len(tasks)
        ):
            result = A.analyze_records([])
        self.assertTrue(result["mechanism"]["support"]["pass"])
        self.assertTrue(result["mechanism"]["claim_authorized"])

    def test_all_existing_arms_are_reported_without_changing_primary_gate(self):
        matrix = _matrix(
            self.tasks, guided=10, plain=3600, matched=3600, non_gating=10
        )
        outcomes = {("blind_fw", "solved"): 3}
        accounting = [{"cell": index} for index in range(27)]
        with mock.patch.object(
            A, "validate_matrix",
            return_value=(matrix, self.tasks, self.sources, outcomes, accounting),
        ), mock.patch.object(P, "BOOTSTRAP_REPLICATES", 1000), mock.patch.object(
            P, "CELL_COUNT", 27
        ):
            result = A.analyze_records([])
        reporting = result["non_gating_contrasts"]
        self.assertFalse(reporting["affects_complete_gate"])
        self.assertEqual(
            tuple(reporting["references"]), P.NON_GATING_REFERENCE_LABELS
        )
        self.assertTrue(result["gates"]["pass"])
        self.assertTrue(all(
            not contrast["pass"]
            for contrast in reporting["references"].values()
        ))
        overhead = result["selector_overhead"]
        self.assertFalse(overhead["affects_complete_gate"])
        self.assertEqual(len(overhead["rows"]), 2 * len(self.tasks))
        self.assertEqual(
            overhead["by_arm"][P.GUIDED_LABEL]["phases"]["probe"][
                "cpu_seconds"
            ]["count"],
            len(self.tasks),
        )


class DoubleExecutionTest(unittest.TestCase):
    def test_sealed_input_rejects_lexical_symlink_alias_before_provenance_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sealed = root / "properties"
            sealed.write_bytes(b"[]")
            alias = root / "alias"
            alias.symlink_to(sealed)
            with mock.patch.object(
                A.Audit, "EVAL_PROPERTIES", sealed
            ), mock.patch.object(
                A.Audit, "load_fetch_receipt"
            ) as fetch, mock.patch.object(
                A.P, "validate_protocol_without_sources"
            ) as protocol, mock.patch.object(
                A.SafeIO.os, "lstat"
            ) as inspected:
                with self.assertRaisesRegex(
                    A.ConfirmationBAnalysisError,
                    "analysis input is not the sealed matrix",
                ):
                    A._load_sealed_input(alias)
                protocol.assert_not_called()
                fetch.assert_not_called()
                inspected.assert_not_called()

    def test_sealed_input_is_parsed_from_the_bytes_that_were_hashed(self):
        raw_a = b'[{"marker":"A"}]'
        raw_b = b'[{"marker":"B"}]'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "properties.json"
            path.write_bytes(raw_a)
            receipt = {"properties_sha256": hashlib.sha256(raw_a).hexdigest()}
            with mock.patch.object(
                P, "validate_protocol_without_sources"
            ), mock.patch.object(
                A.Audit, "EVAL_PROPERTIES", path
            ), mock.patch.object(
                A.Audit, "load_fetch_receipt",
                return_value=("f" * 64, receipt),
            ), mock.patch.object(
                A.Audit, "load_execution_receipt",
                return_value=("e" * 64, {"hardware": HARDWARE}),
            ), mock.patch.object(
                Path, "read_bytes", side_effect=[raw_a, raw_a]
            ), mock.patch.object(Path, "read_text", return_value=raw_b.decode()):
                records, properties_sha, _, execution_sha, hardware = (
                    A._load_sealed_input(path)
                )
        self.assertEqual(records, [{"marker": "A"}])
        self.assertEqual(properties_sha, receipt["properties_sha256"])
        self.assertEqual(execution_sha, "e" * 64)
        self.assertEqual(hardware, HARDWARE)

    def test_double_execution_publishes_only_identical_bytes(self):
        result = {
            "schema": A.SCHEMA,
            "gates": {"pass": True},
            "mechanism": {"claim_authorized": True},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            properties = root / "properties"
            properties.write_text("{}")
            outputs = tuple(root / name for name in (
                "analysis.json", "repeat.json", "receipt.json", "receipt.sha256"
            ))
            with mock.patch.object(
                A, "_load_sealed_input",
                side_effect=[
                    ([], "1" * 64, "2" * 64, "4" * 64, HARDWARE),
                    ([], "1" * 64, "2" * 64, "4" * 64, HARDWARE),
                ],
            ), mock.patch.object(
                A, "analyze_records", side_effect=[dict(result), dict(result)]
            ):
                receipt = A.run_twice(properties, *outputs)
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            self.assertTrue(receipt["outputs_byte_identical"])
            self.assertEqual(
                outputs[3].read_text().strip(),
                receipt["analysis_receipt_sha256"],
            )

    def test_nondeterministic_analysis_publishes_nothing(self):
        first = {
            "schema": A.SCHEMA,
            "gates": {"pass": True},
            "mechanism": {"claim_authorized": False},
            "nonce": 1,
        }
        second = {**first, "nonce": 2}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            properties = root / "properties"
            properties.write_text("{}")
            outputs = tuple(root / name for name in (
                "analysis.json", "repeat.json", "receipt.json", "receipt.sha256"
            ))
            with mock.patch.object(
                A, "_load_sealed_input",
                side_effect=[
                    ([], "1" * 64, "2" * 64, "4" * 64, HARDWARE),
                    ([], "1" * 64, "2" * 64, "4" * 64, HARDWARE),
                ],
            ), mock.patch.object(
                A, "analyze_records", side_effect=[first, second]
            ):
                with self.assertRaisesRegex(
                    A.ConfirmationBAnalysisError, "byte-identical"
                ):
                    A.run_twice(properties, *outputs)
            self.assertFalse(any(path.exists() for path in outputs))

    def test_identical_post_write_tampering_cannot_produce_receipt(self):
        result = {
            "schema": A.SCHEMA,
            "gates": {"pass": True},
            "mechanism": {"claim_authorized": False},
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            properties = root / "properties"
            properties.write_text("{}")
            outputs = tuple(root / name for name in (
                "analysis.json", "repeat.json", "receipt.json",
                "receipt.sha256",
            ))
            actual_exclusive = A._exclusive
            calls = []

            def exclusive_then_tamper(path, raw, label):
                digest = actual_exclusive(path, raw, label)
                calls.append(Path(path))
                if len(calls) == 2:
                    outputs[0].write_bytes(b"identical tampering\n")
                    outputs[1].write_bytes(b"identical tampering\n")
                return digest

            with mock.patch.object(
                A, "_load_sealed_input",
                side_effect=[
                    ([], "1" * 64, "2" * 64, "4" * 64, HARDWARE),
                    ([], "1" * 64, "2" * 64, "4" * 64, HARDWARE),
                ],
            ), mock.patch.object(
                A, "analyze_records", side_effect=[dict(result), dict(result)]
            ), mock.patch.object(
                A, "_exclusive", side_effect=exclusive_then_tamper
            ):
                with self.assertRaisesRegex(
                    A.ConfirmationBAnalysisError, "published analyses differ"
                ):
                    A.run_twice(properties, *outputs)
            self.assertFalse(outputs[2].exists())
            self.assertFalse(outputs[3].exists())


if __name__ == "__main__":
    unittest.main()
