#!/usr/bin/env python3
"""Focused tests for the V11 Confirmation B freeze boundary."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import freeze_pdb_terminal_incidence_confirmation_b as Freeze
import pdb_terminal_incidence_confirmation_b_protocol as P
import pdb_terminal_incidence_confirmation_v11_adapter as Adapter
import test_pdb_terminal_incidence_confirmation_v11_adapter as Fixture


A_FREEZE_REVISION = "4" * 40
B_FREEZE_REVISION = "5" * 40


def authorized_v11():
    source = Fixture.mixed_authorized_confirmation()
    for record in source.all_records:
        directory = record["directory"]
        record["domain_file"] = directory + "/domain.pddl"
        record["problem_file"] = directory + "/" + record["problem"]
        record["canonical_path"] = record["problem_file"]
        record["aliases"][0]["domain_file"] = record["domain_file"]
        record["aliases"][0]["problem_file"] = record["problem_file"]
    with (
        mock.patch.object(Adapter.SourceV11, "paths_for", return_value=object()),
        mock.patch.object(
            Adapter.SourceV11, "load_authorized_confirmation",
            return_value=source,
        ),
    ):
        return Adapter.load_authorized_cohorts(Fixture.FULL_REVISION)


def planner_identity() -> dict:
    return {
        "revision": P.PLANNER_REVISION_REQUIRED,
        "cache_name": "synthetic-cache",
        "build_options": list(P.BUILD_OPTIONS),
        "downward_sha256": "a" * 64,
        "preprocess_sha256": "b" * 64,
        "tree_manifest_sha256": "c" * 64,
    }


def live_authorization(materials: P.SourceMaterials, planner: dict) -> dict:
    return {
        "receipt_path": P.CONFIRMATION_A_RECEIPT_PATH,
        "receipt_pin_path": P.CONFIRMATION_A_RECEIPT_PIN_PATH,
        "first_output_path": P.CONFIRMATION_A_FIRST_OUTPUT_PATH,
        "second_output_path": P.CONFIRMATION_A_SECOND_OUTPUT_PATH,
        "confirmation_a_freeze_path": P.SourceValidation.FREEZE_PATH,
        "receipt_sha256": "1" * 64,
        "first_output_sha256": "2" * 64,
        "second_output_sha256": "2" * 64,
        "input_properties_sha256": "3" * 64,
        "fetch_receipt_sha256": "4" * 64,
        "execution_receipt_sha256": "5" * 64,
        "hardware": {"processor_model_counts": {"Synthetic CPU": 650}},
        "receipt_schema": P.CONFIRMATION_A_RECEIPT_SCHEMA,
        "analysis_protocol": P.SourceValidation.ANALYSIS_PROTOCOL,
        "guided_study_authorized": True,
        "benchmark_revision": P.BENCHMARK_REVISION,
        "cost_attestation_sha256": materials.attestation_sha256,
        "source_audit_launch_receipt_sha256": materials.launch_receipt_sha256,
        "source_audit_execution_receipt_sha256": (
            materials.execution_receipt_sha256
        ),
        "confirmation_a_cohort_manifest_sha256": (
            materials.confirmation_a_source_projection_sha256
        ),
        "source_audit_provenance": {
            **P._v11_source_provenance(materials),
            "confirmation_a_freeze_sha256": "6" * 64,
        },
        "confirmation_a_freeze_repository_revision": A_FREEZE_REVISION,
        "planner_identity": planner,
    }


class ConfirmationBV11FreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authorized = authorized_v11()
        with mock.patch.object(
            P.SourceV11, "load_authorized_cohorts", return_value=cls.authorized,
        ):
            cls.materials = P.load_source_materials(Fixture.FULL_REVISION)
        cls.planner = planner_identity()
        cls.authorization = live_authorization(cls.materials, cls.planner)

    def test_exact_v11_seal_revision_path_is_green(self):
        with mock.patch.object(
            P.SourceV11,
            "load_authorized_cohorts",
            return_value=self.authorized,
        ):
            materials = P.load_source_materials(Fixture.FULL_REVISION)
        self.assertEqual(len(materials.tasks), P.TARGET_COHORT_TASKS)
        self.assertEqual(
            materials.bindings["seal_repository_commit_id"],
            Fixture.FULL_REVISION,
        )
        self.assertEqual(materials.bindings["inventory_families_count"], 32)
        self.assertEqual(materials.bindings["translation_attempts_count"], 1640)
        self.assertEqual(materials.bindings["support_status_counts"], {
            "indeterminate": 2, "supported": 1636, "unsupported": 2,
        })
        self.assertEqual(
            materials.bindings["support_exclusion_counts"],
            {reason: 1 for reason in Adapter.SUPPORT_EXCLUSION_REASONS},
        )
        self.assertEqual(
            materials.bindings["resource_exclusion_counts"],
            {"memory": 1, "time": 1},
        )

    def frozen_authorization(self) -> dict:
        return Freeze._authorization_provenance(self.authorization)

    def freeze_value(self) -> dict:
        return {
            "schema": P.FREEZE_SCHEMA,
            "freeze_repository_revision": B_FREEZE_REVISION,
            "source_audit": copy.deepcopy(self.materials.source_audit),
            "confirmation_a_authorization": self.frozen_authorization(),
            "planner": copy.deepcopy(self.planner),
            "design": Freeze._design(self.materials),
            "experiment_source_sha256": {
                relative: P.sha256_file(P.REPO / relative)
                for relative in P.EXPERIMENT_SOURCE_FILES
            },
        }

    def test_cli_accepts_v11_seal_and_fixed_a_authorization_inputs(self):
        parsed = Freeze.parse_args([
            "--source-seal-revision", Fixture.FULL_REVISION,
            "--freeze-repository-revision", B_FREEZE_REVISION,
        ])
        self.assertEqual(parsed.source_seal_revision, Fixture.FULL_REVISION)
        self.assertEqual(parsed.confirmation_a_receipt, P.CONFIRMATION_A_RECEIPT_PATH)
        self.assertFalse(hasattr(parsed, "attestation"))
        self.assertFalse(hasattr(parsed, "execution_receipt"))
        self.assertFalse(hasattr(parsed, "launch_receipt"))

    def test_source_ancestry_is_exact_s_to_p_to_q_to_a_to_b(self):
        with mock.patch.object(Freeze.JJ, "require_ancestor") as require:
            Freeze._require_source_ancestry(
                self.materials.bindings,
                self.authorization,
                B_FREEZE_REVISION,
            )
        self.assertEqual(require.call_args_list, [
            mock.call(Freeze.REPO, Fixture.SOURCE_REVISION,
                      Fixture.PREFLIGHT_REVISION),
            mock.call(Freeze.REPO, Fixture.PREFLIGHT_REVISION,
                      Fixture.FULL_REVISION),
            mock.call(Freeze.REPO, Fixture.FULL_REVISION, A_FREEZE_REVISION),
            mock.call(Freeze.REPO, A_FREEZE_REVISION, B_FREEZE_REVISION),
            mock.call(Freeze.REPO, P.PLANNER_REVISION_REQUIRED,
                      B_FREEZE_REVISION),
        ])

    def test_frozen_loader_never_reopens_v11_or_a(self):
        value = self.freeze_value()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "freeze.json"
            path.write_bytes(P.canonical_json_line(value))
            with (
                mock.patch.object(
                    P.SourceV11, "load_authorized_cohorts",
                    side_effect=AssertionError("must not reopen V11"),
                ),
                mock.patch.object(
                    P, "load_confirmation_a_authorization",
                    side_effect=AssertionError("must not reopen A"),
                ),
            ):
                _freeze, loaded = P._load_freeze(path)
        self.assertEqual(len(loaded.tasks), 300)
        self.assertEqual(
            set(loaded.tasks[0]), set(Adapter.SOURCE_PROJECTION_FIELDS),
        )
        self.assertEqual(
            loaded.bindings["support_status_counts_sha256"],
            self.materials.bindings["support_status_counts_sha256"],
        )
        self.assertEqual(
            loaded.bindings["resource_exclusion_counts"],
            self.materials.bindings["resource_exclusion_counts"],
        )

    def test_build_and_revalidation_consume_same_v11_seal_twice(self):
        with (
            mock.patch.object(P, "validate_static_design"),
            mock.patch.object(
                P, "load_source_materials", return_value=self.materials,
            ) as load,
            mock.patch.object(
                Freeze, "_load_authorization", return_value=self.authorization,
            ),
            mock.patch.object(Freeze, "_attest_authorization"),
            mock.patch.object(Freeze, "_require_source_ancestry"),
            mock.patch.object(Freeze, "_planner_freeze", return_value=self.planner),
            mock.patch.object(Freeze, "_source_hashes", return_value={}),
        ):
            value = Freeze.build_freeze(
                source_seal_revision=Fixture.FULL_REVISION,
                confirmation_a_receipt=P.CONFIRMATION_A_RECEIPT_PATH,
                confirmation_a_receipt_pin=P.CONFIRMATION_A_RECEIPT_PIN_PATH,
                confirmation_a_first_output=P.CONFIRMATION_A_FIRST_OUTPUT_PATH,
                confirmation_a_second_output=P.CONFIRMATION_A_SECOND_OUTPUT_PATH,
                freeze_repository_revision=B_FREEZE_REVISION,
            )
            with mock.patch.object(
                Freeze, "_require_clean_parent", return_value=B_FREEZE_REVISION,
            ):
                Freeze._revalidate_before_write(
                    value,
                    source_seal_revision=Fixture.FULL_REVISION,
                    confirmation_a_receipt=P.CONFIRMATION_A_RECEIPT_PATH,
                    confirmation_a_receipt_pin=P.CONFIRMATION_A_RECEIPT_PIN_PATH,
                    confirmation_a_first_output=P.CONFIRMATION_A_FIRST_OUTPUT_PATH,
                    confirmation_a_second_output=P.CONFIRMATION_A_SECOND_OUTPUT_PATH,
                    freeze_repository_revision=B_FREEZE_REVISION,
                )
        self.assertEqual(load.call_args_list, [
            mock.call(Fixture.FULL_REVISION),
            mock.call(Fixture.FULL_REVISION),
        ])
        self.assertEqual(set(value["source_audit"]), {
            "schema", "source_seal_revision", "bindings", "guided_b",
        })

    def test_second_consumption_detects_any_source_projection_change(self):
        changed_source = copy.deepcopy(self.materials.source_audit)
        changed_source["guided_b"]["records"][0]["problem"] = "changed.pddl"
        changed = dataclasses.replace(
            self.materials, source_audit=changed_source,
        )
        value = {
            "freeze_repository_revision": B_FREEZE_REVISION,
            "source_audit": self.materials.source_audit,
            "confirmation_a_authorization": self.frozen_authorization(),
            "planner": self.planner,
            "experiment_source_sha256": {},
        }
        with (
            mock.patch.object(
                Freeze, "_require_clean_parent", return_value=B_FREEZE_REVISION,
            ),
            mock.patch.object(
                Freeze, "_load_authorization", return_value=self.authorization,
            ),
            mock.patch.object(Freeze, "_attest_authorization"),
            mock.patch.object(Freeze, "_require_source_ancestry"),
            mock.patch.object(Freeze, "_source_hashes", return_value={}),
            mock.patch.object(P, "load_source_materials", return_value=changed),
            self.assertRaisesRegex(Freeze.FreezeError, "V11 source changed"),
        ):
            Freeze._revalidate_before_write(
                value,
                source_seal_revision=Fixture.FULL_REVISION,
                confirmation_a_receipt=P.CONFIRMATION_A_RECEIPT_PATH,
                confirmation_a_receipt_pin=P.CONFIRMATION_A_RECEIPT_PIN_PATH,
                confirmation_a_first_output=P.CONFIRMATION_A_FIRST_OUTPUT_PATH,
                confirmation_a_second_output=P.CONFIRMATION_A_SECOND_OUTPUT_PATH,
                freeze_repository_revision=B_FREEZE_REVISION,
            )

    def test_a_authorization_binds_same_q_and_both_source_projections(self):
        P._validate_confirmation_a_source_link(
            self.authorization, self.materials,
        )
        mutations = (
            ("source_audit_seal_repository_commit_id", "7" * 40),
            ("source_audit_confirmation_a_projection_sha256", "8" * 64),
            ("source_audit_guided_b_projection_sha256", "9" * 64),
            ("confirmation_a_freeze_sha256", "invalid"),
        )
        for field, value in mutations:
            with self.subTest(field=field):
                changed = copy.deepcopy(self.authorization)
                changed["source_audit_provenance"][field] = value
                with self.assertRaisesRegex(P.ProtocolError, "not linked"):
                    P._validate_confirmation_a_source_link(
                        changed, self.materials,
                    )

    def test_a_authorization_artifacts_are_all_attested_at_b_revision(self):
        with mock.patch.object(Freeze, "_attest_tracked_file") as attest:
            Freeze._attest_authorization(
                self.authorization, B_FREEZE_REVISION,
            )
        self.assertEqual(attest.call_count, 5)
        calls = {(call.args[0], call.args[1]) for call in attest.call_args_list}
        self.assertIn(
            (P.CONFIRMATION_A_RECEIPT_PATH,
             self.authorization["receipt_sha256"]), calls,
        )
        self.assertIn(
            (
                P.CONFIRMATION_A_RECEIPT_PIN_PATH,
                hashlib.sha256(
                    (self.authorization["receipt_sha256"] + "\n").encode("ascii")
                ).hexdigest(),
            ),
            calls,
        )
        self.assertIn(
            (P.SourceValidation.FREEZE_PATH, "6" * 64), calls,
        )
        self.assertTrue(all(
            call.args[2] == B_FREEZE_REVISION
            for call in attest.call_args_list
        ))

    def test_v11_experiment_sources_replace_v7_consumers(self):
        self.assertIn(
            "experiments/pdb_terminal_incidence_confirmation_v11_adapter.py",
            P.EXPERIMENT_SOURCE_FILES,
        )
        self.assertIn(
            "experiments/pdb_terminal_incidence_confirmation_source_consumer_v11.py",
            P.EXPERIMENT_SOURCE_FILES,
        )
        self.assertFalse(any(
            "source_consumer_v7" in relative
            for relative in P.EXPERIMENT_SOURCE_FILES
        ))

    def test_v11_freeze_round_trip_rejects_embedded_and_source_tamper(self):
        value = self.freeze_value()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "freeze.json"
            path.write_bytes(P.canonical_json_line(value))
            loaded, materials = P._load_freeze(path)
            self.assertEqual(loaded, value)
            self.assertEqual(len(materials.tasks), P.TARGET_COHORT_TASKS)
            self.assertEqual(
                materials.bindings["support_exclusion_counts"],
                {reason: 1 for reason in Adapter.SUPPORT_EXCLUSION_REASONS},
            )

            changed = copy.deepcopy(value)
            resources = changed["source_audit"]["bindings"][
                "resource_exclusion_counts"
            ]
            resources.update(memory=2, time=0)
            changed["source_audit"]["bindings"][
                "resource_exclusion_counts_sha256"
            ] = hashlib.sha256(P.canonical_json(resources)).hexdigest()
            path.write_bytes(P.canonical_json_line(changed))
            with self.assertRaisesRegex(P.ProtocolError, "summary"):
                P._load_freeze(path)

            changed = copy.deepcopy(value)
            changed["source_audit"]["unexpected"] = True
            path.write_bytes(P.canonical_json_line(changed))
            with self.assertRaisesRegex(P.ProtocolError, "source shape"):
                P._load_freeze(path)

            changed = copy.deepcopy(value)
            relative = P.EXPERIMENT_SOURCE_FILES[0]
            changed["experiment_source_sha256"][relative] = "f" * 64
            path.write_bytes(P.canonical_json_line(changed))
            with self.assertRaisesRegex(P.ProtocolError, "source changed"):
                P._load_freeze(path)


if __name__ == "__main__":
    unittest.main()
