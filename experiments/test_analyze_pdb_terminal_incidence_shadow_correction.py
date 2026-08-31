#!/usr/bin/env python3
"""Focused tests for the frozen terminal-incidence analysis correction."""

from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import analyze_pdb_terminal_incidence_shadow as Original
import analyze_pdb_terminal_incidence_shadow_correction as Correction
import pdb_fixed_pattern_parser as PatternParser
import pdb_profile_comparison_parser as ProfileParser
import pdb_terminal_incidence_shadow_protocol as P


class TerminalIncidenceCorrectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.attestation_raw = P.COST_ATTESTATION_PATH.read_bytes()
        cls.attestation = json.loads(cls.attestation_raw.decode("ascii"))
        cls.records = cls._synthetic_presearch_matrix(cls.attestation["tasks"])

    @staticmethod
    def _synthetic_presearch_matrix(tasks):
        records = []
        for task in tasks:
            domain = task["domain"]
            problem = task["problem"]
            for label in P.LABELS:
                record = {
                    "algorithm": label,
                    "domain": domain,
                    "problem": problem,
                    "id": [label, domain, problem],
                    "component_options": ["--search", P.SEARCHES[label]],
                    "driver_options": [
                        "--overall-time-limit",
                        "{}s".format(P.TIME_LIMIT_SECONDS),
                        "--overall-memory-limit",
                        "{}M".format(P.MEMORY_LIMIT_MIB),
                        "--build",
                        "release_no_lp",
                    ],
                    "build_options": list(P.BUILD_OPTIONS),
                    "local_revision": P.PLANNER_REVISION,
                    "global_revision": P.PLANNER_REVISION,
                    "wbh_profile_parser_protocol": (
                        ProfileParser.PROFILE_PARSER_PROTOCOL
                    ),
                    "wbh_expansion_parser_protocol": (
                        ProfileParser.EXPANSION_PARSER_PROTOCOL
                    ),
                    "pdb_profile_selector_parser_protocol": (
                        ProfileParser.SELECTOR_PARSER_PROTOCOL
                    ),
                    "pdb_profile_selector_present": False,
                    "pdb_fixed_pattern_parser_protocol": (
                        PatternParser.PARSER_PROTOCOL
                    ),
                    "domain_source_path": "{}/domain.pddl".format(domain),
                    "problem_source_path": "{}/{}".format(domain, problem),
                    "domain_source_sha256": task["domain_sha256"],
                    "problem_source_sha256": task["problem_sha256"],
                    "planner_exit_code": 10,
                    "error": "translate-unsolvable",
                    "coverage": 0,
                    "unsolvable": 1,
                    "unexplained_errors": [],
                    "wbh_profile_present": False,
                    "wbh_expansion_profile_present": False,
                    "construction_completed": None,
                }
                record.update(Original._fixed_properties())
                records.append(record)
        return records

    def test_alias_view_changes_only_the_two_attestation_keys(self):
        payload = Correction._corrected_attestation_payload(self.attestation_raw)
        corrected = json.loads(payload.decode("ascii"))
        self.assertEqual(payload, P.canonical_json(corrected) + b"\n")
        self.assertEqual(set(corrected), set(self.attestation))
        for before, after in zip(self.attestation["tasks"], corrected["tasks"]):
            self.assertEqual(
                set(after),
                set(before) | {alias for alias, _ in Correction.ATTESTATION_ALIASES},
            )
            for key, value in before.items():
                self.assertEqual(after[key], value)
            for alias, source in Correction.ATTESTATION_ALIASES:
                self.assertEqual(after[alias], before[source])

    def test_alias_collision_and_attestation_drift_fail_closed(self):
        with self.assertRaisesRegex(
            Correction.CorrectionError,
            "source attestation bytes changed",
        ):
            Correction._corrected_attestation_payload(
                self.attestation_raw + b" "
            )
        changed = copy.deepcopy(self.attestation)
        changed["tasks"][0]["domain_source_sha256"] = (
            changed["tasks"][0]["domain_sha256"]
        )
        raw = P.canonical_json(changed) + b"\n"
        with mock.patch.object(
            P, "COST_ATTESTATION_SHA256", hashlib.sha256(raw).hexdigest()
        ):
            with self.assertRaisesRegex(
                Correction.CorrectionError,
                "already contains alias keys",
            ):
                Correction._corrected_attestation_payload(raw)

    def test_full_analysis_matches_frozen_analyzer_except_provenance(self):
        with Correction._aliased_attestation_view():
            expected = Correction._FROZEN_ANALYZE_RECORDS(
                copy.deepcopy(self.records)
            )
        corrected = Correction.analyze_records(copy.deepcopy(self.records))
        self.assertEqual(
            corrected.pop("frozen_protocol_sha256"), P.PROTOCOL_SHA256
        )
        provenance = corrected.pop("analysis_correction")
        self.assertEqual(provenance["schema"], Correction.CORRECTION_SCHEMA)
        self.assertEqual(provenance["correction_id"], Correction.CORRECTION_ID)
        self.assertEqual(
            provenance["attestation_key_aliases"],
            dict(Correction.ATTESTATION_ALIASES),
        )
        self.assertEqual(
            provenance["excluded_terminal_outcomes"],
            Correction._excluded_outcome_provenance(),
        )
        self.assertEqual(
            provenance["requested_mode_derivation"],
            Correction._requested_mode_provenance(),
        )
        self.assertEqual(
            provenance["original_analyzer_sha256"],
            Correction.ORIGINAL_ANALYZER_SHA256,
        )
        self.assertEqual(
            provenance["original_attestation_sha256"],
            P.COST_ATTESTATION_SHA256,
        )
        self.assertEqual(
            provenance["attestation_alias_view_sha256"],
            hashlib.sha256(
                Correction._corrected_attestation_payload(
                    self.attestation_raw
                )
            ).hexdigest(),
        )
        self.assertEqual(
            provenance["correction_wrapper_sha256"],
            Correction._sha256_file(Correction.CORRECTION_WRAPPER_PATH),
        )
        self.assertEqual(corrected, expected)

    def test_source_hash_mutation_fails_closed(self):
        changed = copy.deepcopy(self.records)
        changed[0]["domain_source_sha256"] = "0" * 64
        with self.assertRaisesRegex(
            Original.TerminalIncidenceAnalysisError,
            "benchmark-source hash changed",
        ):
            Correction.validate_matrix(changed)

    def test_frozen_task_and_directory_checks_still_run(self):
        with mock.patch.object(P, "TASK_NAME_SHA256", "0" * 64):
            with self.assertRaisesRegex(
                Original.TerminalIncidenceAnalysisError,
                "task-name manifest changed",
            ):
                Correction.validate_matrix(self.records)
        with mock.patch.object(P, "DIRECTORIES", P.DIRECTORIES[:-1]):
            with self.assertRaisesRegex(
                Original.TerminalIncidenceAnalysisError,
                "directory universe changed",
            ):
                Correction.validate_matrix(self.records)
        changed_families = dict(P.DIRECTORY_TO_FAMILY)
        changed_families["extra-directory"] = "extra-family"
        with mock.patch.object(P, "DIRECTORY_TO_FAMILY", changed_families):
            with self.assertRaisesRegex(
                Original.TerminalIncidenceAnalysisError,
                "family universe changed",
            ):
                Correction.validate_matrix(self.records)

    def test_reduced_cohort_override_is_rejected(self):
        with self.assertRaisesRegex(
            Correction.CorrectionError,
            "requires the frozen full cohort",
        ):
            Correction.validate_matrix([], expected_tasks=0)

    def test_original_analyzer_drift_fails_closed(self):
        with mock.patch.object(Correction, "_sha256_file", return_value="0" * 64):
            with self.assertRaisesRegex(
                Correction.CorrectionError,
                "frozen original analyzer bytes changed",
            ):
                Correction._assert_original_analyzer()

    def test_original_analyzer_protocol_module_drift_fails_closed(self):
        with mock.patch.object(Original, "P", object()):
            with self.assertRaisesRegex(
                Correction.CorrectionError,
                "protocol module changed",
            ):
                Correction._assert_original_analyzer()

    def test_original_outcome_table_drift_fails_closed(self):
        with mock.patch.object(Original, "OUTCOME_SPECS", {}):
            with self.assertRaisesRegex(
                Correction.CorrectionError,
                "outcome table changed",
            ):
                Correction._assert_original_analyzer()

    def test_exact_excluded_terminal_outcomes_are_accepted_and_restored(self):
        phase = {
            30: (None, False, False),
            34: (None, True, True),
            247: (None, False, False),
            250: (True, True, True),
        }
        records = copy.deepcopy(self.records)
        original_table = Original.OUTCOME_SPECS
        for index, code in enumerate(sorted(Correction.EXCLUDED_TERMINAL_OUTCOMES)):
            expected = Correction.EXCLUDED_TERMINAL_OUTCOMES[code]
            record = records[index]
            construction, profile, expansion = phase[code]
            record.update({
                "planner_exit_code": code,
                "error": expected["error"],
                "coverage": expected["coverage"],
                "unsolvable": expected["unsolvable"],
                "unexplained_errors": [
                    expected["error"],
                    Original.LAB_SLURM_ERROR,
                ],
                "construction_completed": construction,
                "wbh_profile_present": profile,
                "wbh_expansion_profile_present": expansion,
            })
        matrix, _tasks, outcomes = Correction.validate_matrix(records)
        self.assertEqual(len(matrix), P.CELL_COUNT)
        for index, code in enumerate(sorted(Correction.EXCLUDED_TERMINAL_OUTCOMES)):
            record = records[index]
            key = (record["algorithm"], (record["domain"], record["problem"]))
            self.assertEqual(
                outcomes[key], Correction.EXCLUDED_OUTCOME_CLASS
            )
        self.assertIs(Original.OUTCOME_SPECS, original_table)

    def test_excluded_terminal_near_matches_fail_closed(self):
        expected = Correction.EXCLUDED_TERMINAL_OUTCOMES[250]
        base = copy.deepcopy(self.records[0])
        base.update({
            "planner_exit_code": 250,
            "error": expected["error"],
            "coverage": expected["coverage"],
            "unsolvable": expected["unsolvable"],
            "unexplained_errors": [
                expected["error"],
                Original.LAB_SLURM_ERROR,
            ],
            "construction_completed": True,
            "wbh_profile_present": True,
            "wbh_expansion_profile_present": True,
        })
        mutations = (
            ("error", "changed"),
            ("coverage", 1),
            ("unsolvable", 1),
            ("construction_completed", None),
            ("wbh_profile_present", False),
            ("wbh_expansion_profile_present", False),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(base)
                changed[field] = value
                with self.assertRaisesRegex(
                    Correction.CorrectionError,
                    "fields changed",
                ):
                    Correction._validate_excluded_terminal_contract(
                        [changed], set(P.PRIMARY_LABELS)
                    )
        for errors in ([], [expected["error"]], [Original.LAB_SLURM_ERROR]):
            with self.subTest(errors=errors):
                changed = copy.deepcopy(base)
                changed["unexplained_errors"] = errors
                with self.assertRaisesRegex(
                    Correction.CorrectionError,
                    "invalidating evidence",
                ):
                    Correction._validate_excluded_terminal_contract(
                        [changed], set(P.PRIMARY_LABELS)
                    )

    def test_unknown_primary_terminal_fails_closed(self):
        unknown = copy.deepcopy(self.records[0])
        unknown["planner_exit_code"] = 251
        with self.assertRaisesRegex(
            Correction.CorrectionError,
            "unrecognized terminal outcome",
        ):
            Correction._validate_excluded_terminal_contract(
                [unknown], set(P.PRIMARY_LABELS)
            )

    def test_failed_gate_does_not_read_intervention_terminal_outcome(self):
        records = copy.deepcopy(self.records)
        intervention = next(
            record for record in records
            if record["algorithm"] == P.INTERVENTION_LABEL
        )
        intervention["planner_exit_code"] = "outcome remains blinded"
        intervention["wbh_profile_parser_protocol"] = "unread-after-failed-gate"
        result = Correction.analyze_records(records)
        self.assertFalse(result["gates"]["pass"])
        self.assertEqual(
            result["intervention"]["status"],
            "not_analyzed_primary_gate_failed",
        )

    def test_passing_gate_validates_intervention_terminal_outcome(self):
        records = copy.deepcopy(self.records)
        intervention = next(
            record for record in records
            if record["algorithm"] == P.INTERVENTION_LABEL
        )
        intervention["planner_exit_code"] = "malformed-after-passing-gate"
        with mock.patch.object(
            Original, "primary_gates", return_value={"pass": True}
        ):
            with self.assertRaisesRegex(
                Correction.CorrectionError,
                "unrecognized terminal outcome",
            ):
                Correction.analyze_records(records)

    def test_outcome_table_is_restored_after_analysis_failure(self):
        original_table = Original.OUTCOME_SPECS
        with mock.patch.object(
            Correction,
            "_FROZEN_ANALYZE_RECORDS",
            side_effect=RuntimeError("analysis failure"),
        ):
            with self.assertRaisesRegex(RuntimeError, "analysis failure"):
                Correction.analyze_records(copy.deepcopy(self.records))
        self.assertIs(Original.OUTCOME_SPECS, original_table)

    @staticmethod
    def _direct_identity(label, mode=None, requested=None):
        mode = Original.REQUESTED_MODES[label] if mode is None else mode
        pattern = [1, 2]
        pattern_sha = Original._sha(pattern)
        value_cap = 8 if label == P.INTERVENTION_LABEL else None
        record = {
            "algorithm": label,
            "construction_completed": True,
            "pdb_fixed_pattern_present": True,
            "pdb_fixed_pattern_certified": True,
            "pdb_fixed_pattern": pattern,
            "pdb_fixed_pattern_final": {
                "mode": mode,
                "state_budget": 100000,
                "pattern": pattern,
                "pattern_sha256": pattern_sha,
                "value_cap": value_cap,
                "pattern_size": 2,
                "num_values": 3,
                "cofactor_width": 3,
                "width_upper_bound": 7,
            },
            "pdb_fixed_pattern_mode": mode,
            "pdb_fixed_pattern_requested_mode": requested,
            "pdb_fixed_pattern_observed_mode": mode,
            "pdb_fixed_pattern_fallback": (
                mode == "cegar_fallback_goal_fill"
            ),
            "pdb_fixed_pattern_validation_error": None,
            "pdb_fixed_pattern_size": 2,
            "pdb_fixed_pattern_sha256": pattern_sha,
            "add_nodes": 4,
            "num_terminals": 3,
            "num_values": 3,
            "width_upper_bound": 7,
        }
        heuristic = {
            "add_nodes": 4,
            "num_terminals": 3,
            "num_values": 3,
            "cofactor_width": 3,
            "cofactor_counts": [1, 2, 3],
        }
        return record, heuristic

    def test_requested_mode_reconstruction_matches_manual_correction(self):
        cases = [(label, None) for label in P.LABELS]
        cases.append(("pdb_cegar_shadow", "cegar_fallback_goal_fill"))
        for label, mode in cases:
            with self.subTest(label=label, mode=mode):
                record, heuristic = self._direct_identity(label, mode=mode)
                before = copy.deepcopy(record)
                manual = dict(record)
                manual["pdb_fixed_pattern_requested_mode"] = (
                    Original.REQUESTED_MODES[label]
                )
                expected = Correction._FROZEN_SEMANTIC_IDENTITY(
                    manual, label, heuristic
                )
                actual = Correction._semantic_identity_with_requested_mode(
                    record, label, heuristic
                )
                self.assertEqual(actual, expected)
                self.assertEqual(record, before)

    def test_requested_mode_correction_fails_closed(self):
        label = "pdb_goal_fill_shadow"
        record, heuristic = self._direct_identity(label)
        missing = dict(record)
        del missing["pdb_fixed_pattern_requested_mode"]
        with self.assertRaisesRegex(
            Correction.CorrectionError, "lacks requested-mode"
        ):
            Correction._semantic_identity_with_requested_mode(
                missing, label, heuristic
            )
        with self.assertRaisesRegex(
            Correction.CorrectionError, "algorithm and label disagree"
        ):
            Correction._semantic_identity_with_requested_mode(
                record, "pdb_goal_prefix_shadow", heuristic
            )
        unknown = dict(record)
        unknown["algorithm"] = "unknown"
        with self.assertRaisesRegex(
            Correction.CorrectionError, "unknown label"
        ):
            Correction._semantic_identity_with_requested_mode(
                unknown, "unknown", heuristic
            )
        wrong = dict(record)
        wrong["pdb_fixed_pattern_requested_mode"] = "bdd_prefix"
        with self.assertRaisesRegex(
            Original.TerminalIncidenceAnalysisError,
            "invalid direct identity",
        ):
            Correction._semantic_identity_with_requested_mode(
                wrong, label, heuristic
            )
        correct = dict(record)
        correct["pdb_fixed_pattern_requested_mode"] = (
            Original.REQUESTED_MODES[label]
        )
        before = copy.deepcopy(correct)
        self.assertEqual(
            Correction._semantic_identity_with_requested_mode(
                correct, label, heuristic
            ),
            Correction._FROZEN_SEMANTIC_IDENTITY(
                correct, label, heuristic
            ),
        )
        self.assertEqual(correct, before)
        other_conjunct = dict(record)
        other_conjunct["pdb_fixed_pattern_final"] = dict(
            record["pdb_fixed_pattern_final"], state_budget=99999
        )
        with self.assertRaisesRegex(
            Original.TerminalIncidenceAnalysisError,
            "invalid direct identity",
        ):
            Correction._semantic_identity_with_requested_mode(
                other_conjunct, label, heuristic
            )

    def test_semantic_identity_entry_point_restores_after_failure(self):
        original = Original._semantic_identity

        def fail(_records):
            self.assertIs(
                Original._semantic_identity,
                Correction._semantic_identity_with_requested_mode,
            )
            raise RuntimeError("semantic analysis failure")

        with mock.patch.object(
            Correction, "_FROZEN_ANALYZE_RECORDS", side_effect=fail
        ):
            with self.assertRaisesRegex(
                RuntimeError, "semantic analysis failure"
            ):
                Correction.analyze_records(copy.deepcopy(self.records))
        self.assertIs(Original._semantic_identity, original)

    def test_nonregular_original_analyzer_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "target.py"
            target.write_bytes(b"pass\n")
            link = Path(directory) / "analyzer.py"
            link.symlink_to(target)
            with mock.patch.object(Correction, "ORIGINAL_ANALYZER_PATH", link):
                with self.assertRaisesRegex(
                    Correction.CorrectionError,
                    "not a regular file",
                ):
                    Correction._assert_original_analyzer()

    def test_attestation_path_is_restored_and_view_deleted_on_failure(self):
        original_path = P.COST_ATTESTATION_PATH
        delegated_paths = []

        def fail(_records, _expected_tasks):
            delegated_paths.append(P.COST_ATTESTATION_PATH)
            self.assertTrue(P.COST_ATTESTATION_PATH.is_file())
            raise RuntimeError("delegated failure")

        with mock.patch.object(
            Correction, "_FROZEN_VALIDATE_MATRIX", side_effect=fail
        ):
            with self.assertRaisesRegex(RuntimeError, "delegated failure"):
                Correction.validate_matrix(self.records)
        self.assertEqual(P.COST_ATTESTATION_PATH, original_path)
        self.assertEqual(len(delegated_paths), 1)
        self.assertFalse(delegated_paths[0].exists())

    def test_live_checks_precede_record_loading(self):
        events = []
        original_attestation_path = P.COST_ATTESTATION_PATH

        def record_event(name):
            events.append((name, P.COST_ATTESTATION_PATH))

        with tempfile.TemporaryDirectory() as directory:
            properties = Path(directory) / "properties"
            properties.write_bytes(b"{}\n")
            digest = hashlib.sha256(properties.read_bytes()).hexdigest()
            with (
                mock.patch.object(
                    P,
                    "validate_protocol_without_sources",
                    side_effect=lambda: record_event("protocol"),
                ),
                mock.patch.object(
                    Correction.Audit,
                    "load_fetch_receipt",
                    side_effect=lambda **_kwargs: (
                        record_event("fetch") or (
                            "f" * 64,
                            {"properties_sha256": digest},
                        )
                    ),
                ),
                mock.patch.object(Correction.Audit, "EVAL_PROPERTIES", properties),
                mock.patch.object(
                    Original,
                    "load_records",
                    side_effect=lambda _path: record_event("load") or [],
                ),
            ):
                records, fetch_sha, properties_sha = Correction._load_live_input(
                    properties
                )
        self.assertEqual(
            events,
            [
                ("protocol", original_attestation_path),
                ("fetch", original_attestation_path),
                ("load", original_attestation_path),
            ],
        )
        self.assertEqual(records, [])
        self.assertEqual(fetch_sha, "f" * 64)
        self.assertEqual(properties_sha, digest)

    def test_output_is_exclusive_and_fsynced(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "analysis.json"
            with mock.patch.object(
                Correction.os, "fsync", wraps=Correction.os.fsync
            ) as fsync:
                Correction._write_exclusive(output, b"{}\n")
            self.assertEqual(output.read_bytes(), b"{}\n")
            fsync.assert_called_once()
            with self.assertRaisesRegex(
                Correction.CorrectionError,
                "refusing to overwrite",
            ):
                Correction._write_exclusive(output, b"changed\n")


if __name__ == "__main__":
    unittest.main()
