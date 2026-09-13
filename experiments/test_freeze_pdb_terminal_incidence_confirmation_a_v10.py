#!/usr/bin/env python3
"""Focused tests for the V10 Confirmation A freeze boundary."""

from __future__ import annotations

import copy
import dataclasses
import unittest
from unittest import mock

import freeze_pdb_terminal_incidence_confirmation_a as Freeze
import pdb_terminal_incidence_confirmation_a_protocol as P
import pdb_terminal_incidence_confirmation_v10_adapter as Adapter
import test_pdb_terminal_incidence_confirmation_v10_adapter as Fixture


FREEZE_REVISION = "4" * 40


def authorized_v10():
    source = Fixture.authorized_confirmation()
    for record in source.all_records:
        directory = record["directory"]
        record["domain_file"] = directory + "/domain.pddl"
        record["problem_file"] = directory + "/" + record["problem"]
        record["canonical_path"] = record["problem_file"]
        record["aliases"][0]["domain_file"] = record["domain_file"]
        record["aliases"][0]["problem_file"] = record["problem_file"]
    with (
        mock.patch.object(Adapter.SourceV10, "paths_for", return_value=object()),
        mock.patch.object(
            Adapter.SourceV10, "load_authorized_confirmation",
            return_value=source,
        ),
    ):
        return Adapter.load_authorized_cohorts(Fixture.FULL_REVISION)


class ConfirmationAV10FreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authorized = authorized_v10()
        with mock.patch.object(
            P.SourceV10, "load_authorized_cohorts", return_value=cls.authorized,
        ):
            cls.materials = P.load_source_materials(Fixture.FULL_REVISION)

    def test_cli_accepts_only_source_seal_and_freeze_inputs(self):
        parsed = Freeze.parse_args([
            "--source-seal-revision", Fixture.FULL_REVISION,
            "--freeze-repository-revision", FREEZE_REVISION,
        ])
        self.assertEqual(parsed.source_seal_revision, Fixture.FULL_REVISION)
        self.assertFalse(hasattr(parsed, "attestation"))
        self.assertFalse(hasattr(parsed, "execution_receipt"))
        self.assertFalse(hasattr(parsed, "launch_receipt"))

    def test_source_ancestry_is_exact_s_to_p_to_q_to_freeze(self):
        with mock.patch.object(Freeze.JJ, "require_ancestor") as require:
            Freeze._require_source_ancestry(
                self.materials.bindings, FREEZE_REVISION,
            )
        self.assertEqual(require.call_args_list, [
            mock.call(Freeze.REPO, Fixture.SOURCE_REVISION,
                      Fixture.PREFLIGHT_REVISION),
            mock.call(Freeze.REPO, Fixture.PREFLIGHT_REVISION,
                      Fixture.FULL_REVISION),
            mock.call(Freeze.REPO, Fixture.FULL_REVISION, FREEZE_REVISION),
            mock.call(Freeze.REPO, P.PLANNER_REVISION_REQUIRED,
                      FREEZE_REVISION),
        ])

    def test_frozen_loader_never_reopens_v10(self):
        with mock.patch.object(
            P.SourceV10, "load_authorized_cohorts",
            side_effect=AssertionError("must not reopen V10"),
        ):
            loaded = P._materials_from_frozen_source(
                self.materials.source_audit,
            )
        self.assertEqual(len(loaded.tasks), 650)
        self.assertEqual(
            set(loaded.tasks[0]), set(Adapter.SOURCE_PROJECTION_FIELDS),
        )

    def test_build_and_revalidation_consume_same_v10_seal_twice(self):
        planner = {
            "revision": P.PLANNER_REVISION_REQUIRED,
            "cache_name": "cache", "build_options": list(P.BUILD_OPTIONS),
            "downward_sha256": "a" * 64,
            "preprocess_sha256": "b" * 64,
            "tree_manifest_sha256": "c" * 64,
        }
        with (
            mock.patch.object(P, "validate_protocol_design"),
            mock.patch.object(P, "load_source_materials",
                              return_value=self.materials) as load,
            mock.patch.object(Freeze, "_require_source_ancestry"),
            mock.patch.object(Freeze, "_planner_freeze", return_value=planner),
            mock.patch.object(Freeze, "_source_hashes", return_value={}),
        ):
            value = Freeze.build_freeze(
                source_seal_revision=Fixture.FULL_REVISION,
                freeze_repository_revision=FREEZE_REVISION,
            )
            with mock.patch.object(
                Freeze, "_require_clean_parent", return_value=FREEZE_REVISION,
            ):
                Freeze._revalidate_before_write(
                    value, source_seal_revision=Fixture.FULL_REVISION,
                    freeze_repository_revision=FREEZE_REVISION,
                )
        self.assertEqual(load.call_args_list, [
            mock.call(Fixture.FULL_REVISION),
            mock.call(Fixture.FULL_REVISION),
        ])
        self.assertEqual(set(value["source_audit"]), {
            "schema", "source_seal_revision", "bindings", "confirmation_a",
        })

    def test_second_consumption_detects_any_source_projection_change(self):
        changed_source = copy.deepcopy(self.materials.source_audit)
        changed_source["bindings"]["attestation_sha256"] = "f" * 64
        changed = dataclasses.replace(
            self.materials, source_audit=changed_source,
        )
        value = {
            "freeze_repository_revision": FREEZE_REVISION,
            "source_audit": self.materials.source_audit,
            "experiment_source_sha256": {},
        }
        with (
            mock.patch.object(
                Freeze, "_require_clean_parent", return_value=FREEZE_REVISION,
            ),
            mock.patch.object(Freeze, "_require_source_ancestry"),
            mock.patch.object(Freeze, "_source_hashes", return_value={}),
            mock.patch.object(P, "load_source_materials", return_value=changed),
            self.assertRaisesRegex(Freeze.FreezeError, "V10 source changed"),
        ):
            Freeze._revalidate_before_write(
                value, source_seal_revision=Fixture.FULL_REVISION,
                freeze_repository_revision=FREEZE_REVISION,
            )


if __name__ == "__main__":
    unittest.main()
