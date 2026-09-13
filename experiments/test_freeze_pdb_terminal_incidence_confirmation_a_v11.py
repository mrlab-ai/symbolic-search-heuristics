#!/usr/bin/env python3
"""Focused tests for the V11 Confirmation A freeze boundary."""

from __future__ import annotations

import copy
import dataclasses
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import freeze_pdb_terminal_incidence_confirmation_a as Freeze
import pdb_terminal_incidence_confirmation_a_protocol as P
import pdb_terminal_incidence_confirmation_v11_adapter as Adapter
import test_pdb_terminal_incidence_confirmation_v11_adapter as Fixture


FREEZE_REVISION = "4" * 40


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


class ConfirmationAV11FreezeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.authorized = authorized_v11()
        with mock.patch.object(
            P.SourceV11, "load_authorized_cohorts", return_value=cls.authorized,
        ):
            cls.materials = P.load_source_materials(Fixture.FULL_REVISION)

    def test_exact_v11_seal_revision_path_is_green(self):
        with mock.patch.object(
            P.SourceV11,
            "load_authorized_cohorts",
            return_value=self.authorized,
        ):
            materials = P.load_source_materials(Fixture.FULL_REVISION)
        self.assertEqual(len(materials.tasks), P.COHORT_TASKS)
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

    def test_frozen_loader_never_reopens_v11(self):
        with mock.patch.object(
            P.SourceV11, "load_authorized_cohorts",
            side_effect=AssertionError("must not reopen V11"),
        ):
            loaded = P._materials_from_frozen_source(
                self.materials.source_audit,
            )
        self.assertEqual(len(loaded.tasks), 650)
        self.assertEqual(
            set(loaded.tasks[0]), set(Adapter.SOURCE_PROJECTION_FIELDS),
        )
        self.assertEqual(
            loaded.bindings["support_status_counts"],
            self.materials.bindings["support_status_counts"],
        )
        self.assertEqual(
            loaded.bindings["support_exclusion_counts_sha256"],
            self.materials.bindings["support_exclusion_counts_sha256"],
        )
        self.assertEqual(
            loaded.bindings["resource_exclusion_counts"],
            self.materials.bindings["resource_exclusion_counts"],
        )

    def test_build_and_revalidation_consume_same_v11_seal_twice(self):
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
            self.assertRaisesRegex(Freeze.FreezeError, "V11 source changed"),
        ):
            Freeze._revalidate_before_write(
                value, source_seal_revision=Fixture.FULL_REVISION,
                freeze_repository_revision=FREEZE_REVISION,
            )

    def test_v11_experiment_sources_are_bound_at_freeze_revision(self):
        digests = {
            relative: "{:064x}".format(index + 1)
            for index, relative in enumerate(P.EXPERIMENT_SOURCE_FILES)
        }
        with (
            mock.patch.object(
                P, "sha256_file",
                side_effect=lambda path: digests[
                    Path(path).relative_to(Freeze.REPO).as_posix()
                ],
            ),
            mock.patch.object(Freeze, "_attest_tracked_file") as attest,
        ):
            self.assertEqual(Freeze._source_hashes(FREEZE_REVISION), digests)
        self.assertEqual(attest.call_count, len(P.EXPERIMENT_SOURCE_FILES))
        self.assertTrue(all(
            call.args[2] == FREEZE_REVISION for call in attest.call_args_list
        ))

    def test_v11_freeze_round_trip_rejects_embedded_and_source_tamper(self):
        value = {
            "schema": P.FREEZE_SCHEMA,
            "freeze_repository_revision": FREEZE_REVISION,
            "source_audit": copy.deepcopy(self.materials.source_audit),
            "planner": {
                "revision": P.PLANNER_REVISION_REQUIRED,
                "cache_name": "synthetic-cache",
                "build_options": list(P.BUILD_OPTIONS),
                "downward_sha256": "a" * 64,
                "preprocess_sha256": "b" * 64,
                "tree_manifest_sha256": "c" * 64,
            },
            "design": {
                "protocol_sha256": P.sha256_file(P.PROTOCOL_PATH),
                "option_matrix_sha256": P.option_matrix_digest(),
                "cohort_tasks": P.COHORT_TASKS,
                "configs": P.CONFIG_COUNT,
                "cells": P.CELL_COUNT,
                "horizon": P.HORIZON,
                "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
                "bootstrap_seed": P.BOOTSTRAP_SEED,
            },
            "experiment_source_sha256": {
                relative: P.sha256_file(P.REPO / relative)
                for relative in P.EXPERIMENT_SOURCE_FILES
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "freeze.json"
            path.write_bytes(P.canonical_json_line(value))
            loaded, materials = P._load_freeze(path)
            self.assertEqual(loaded, value)
            self.assertEqual(len(materials.tasks), P.COHORT_TASKS)
            self.assertEqual(
                materials.bindings["support_status_counts"],
                {"indeterminate": 2, "supported": 1636, "unsupported": 2},
            )

            semantic_tampers = []
            changed = copy.deepcopy(value)
            changed["source_audit"]["bindings"]["inventory_families_count"] = 0
            semantic_tampers.append(changed)
            changed = copy.deepcopy(value)
            changed["source_audit"]["bindings"]["translation_attempts_count"] = 1639
            semantic_tampers.append(changed)
            changed = copy.deepcopy(value)
            status = changed["source_audit"]["bindings"]["support_status_counts"]
            status["supported"] -= 1
            status["unsupported"] += 1
            changed["source_audit"]["bindings"][
                "support_status_counts_sha256"
            ] = hashlib.sha256(P.canonical_json(status)).hexdigest()
            semantic_tampers.append(changed)
            changed = copy.deepcopy(value)
            status = changed["source_audit"]["bindings"]["support_status_counts"]
            del status["indeterminate"]
            changed["source_audit"]["bindings"][
                "support_status_counts_sha256"
            ] = hashlib.sha256(P.canonical_json(status)).hexdigest()
            semantic_tampers.append(changed)
            changed = copy.deepcopy(value)
            exclusions = changed["source_audit"]["bindings"][
                "support_exclusion_counts"
            ]
            exclusions["unknown"] = 0
            changed["source_audit"]["bindings"][
                "support_exclusion_counts_sha256"
            ] = hashlib.sha256(P.canonical_json(exclusions)).hexdigest()
            semantic_tampers.append(changed)
            changed = copy.deepcopy(value)
            exclusions = changed["source_audit"]["bindings"][
                "support_exclusion_counts"
            ]
            exclusions["translation-input-rejected"] = 0
            changed["source_audit"]["bindings"][
                "support_exclusion_counts_sha256"
            ] = hashlib.sha256(P.canonical_json(exclusions)).hexdigest()
            semantic_tampers.append(changed)
            changed = copy.deepcopy(value)
            resources = changed["source_audit"]["bindings"][
                "resource_exclusion_counts"
            ]
            resources.update(memory=2, time=0)
            changed["source_audit"]["bindings"][
                "resource_exclusion_counts_sha256"
            ] = hashlib.sha256(P.canonical_json(resources)).hexdigest()
            semantic_tampers.append(changed)
            for changed in semantic_tampers:
                path.write_bytes(P.canonical_json_line(changed))
                with self.assertRaisesRegex(
                    P.ProtocolError, "authorization|summary",
                ):
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
