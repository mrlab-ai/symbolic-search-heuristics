#!/usr/bin/env python3
"""Focused tests for the freeze-time V11 Confirmation A/B adapter."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import unittest
from types import MappingProxyType
from unittest import mock

import pdb_terminal_incidence_confirmation_source_consumer_v11 as SourceV11
import pdb_terminal_incidence_confirmation_v11_adapter as Adapter


SOURCE_REVISION = "1" * 40
PREFLIGHT_REVISION = "2" * 40
FULL_REVISION = "3" * 40
CODE_MANIFEST_SHA256 = "c" * 64


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")).hexdigest()


UNREPRESENTED_FAMILIES = list(
    SourceV11.ALL_PRIOR_UNREPRESENTED_FAMILIES[:10]
)
EXTRA_NONSHADOW_FAMILIES = ["airport", "blocks"]
SHADOW_FAMILIES = list(SourceV11.SHADOW_FAMILIES[:20])


def confirmation_families() -> list[str]:
    return (
        [family for family in UNREPRESENTED_FAMILIES for _ in range(10)]
        + [family for family in EXTRA_NONSHADOW_FAMILIES for _ in range(5)]
        + [family for family in SHADOW_FAMILIES for _ in range(27)]
    )


def guided_families() -> list[str]:
    shadow_counts = [12] * 14 + [11] * 6
    return (
        [family for family in UNREPRESENTED_FAMILIES for _ in range(5)]
        + [family for family in EXTRA_NONSHADOW_FAMILIES for _ in range(8)]
        + [
            family
            for family, count in zip(SHADOW_FAMILIES, shadow_counts)
            for _ in range(count)
        ]
    )


def candidate(index: int, family: str) -> dict:
    problem_sha256 = digest("problem-{}".format(index))
    domain_sha256 = digest("domain-{}".format(index))
    canonical = {
        "directory": "directory-{:04d}".format(index),
        "family": family,
        "problem": "problem-{:04d}.pddl".format(index),
        "domain_file": "/benchmarks/domain-{:04d}.pddl".format(index),
        "problem_file": "/benchmarks/problem-{:04d}.pddl".format(index),
        "domain_sha256": domain_sha256,
        "problem_sha256": problem_sha256,
    }
    return {
        "schema": SourceV11.CANDIDATE_SCHEMA,
        "candidate_origin": "v11-fresh",
        "code_manifest_sha256": CODE_MANIFEST_SHA256,
        "repository_commit_id": PREFLIGHT_REVISION,
        "candidate_index": index,
        **canonical,
        "canonical_path": canonical["problem_file"],
        "is_shadow_family": family in SourceV11.SHADOW_FAMILIES,
        "is_shadow_unrepresented": family not in SourceV11.SHADOW_FAMILIES,
        "is_all_prior_represented": family in SourceV11.ALL_PRIOR_FAMILIES,
        "is_all_prior_unrepresented": family not in SourceV11.ALL_PRIOR_FAMILIES,
        "aliases": [canonical],
        "status": "success",
        "process_returncode": 0,
        "complete_process_group_reaped": True,
        "support_determined": True,
        "supported": True,
        "support_exclusion_reasons": [],
        "eligible_for_cohort": True,
        "normalization": {},
        "sas": {},
        "sas_bytes": 1,
        "sas_sha256": digest("sas-{}".format(index)),
        "partial_sas_evidence": None,
        "resource_exclusion_kind": None,
    }


def tracked_closures() -> tuple[dict[str, str], dict[str, str]]:
    common = {
        Adapter.CODE_MANIFEST_RELATIVE: CODE_MANIFEST_SHA256,
        **{
            "src/translate/translator-{:02d}.py".format(index): digest(
                "translator-{}".format(index)
            )
            for index in range(Adapter.TRANSLATOR_FILE_COUNT)
        },
    }
    preflight = {
        **common,
        "experiments/artifacts/v11-preflight/authorization.json": "a" * 64,
    }
    full = {
        **common,
        "experiments/artifacts/v11-full/attestation.json": "b" * 64,
    }
    return preflight, full


def authorized_confirmation() -> SourceV11.AuthorizedConfirmation:
    a_families = confirmation_families()
    b_families = guided_families()
    assert len(a_families) == SourceV11.CONFIRMATION_TASKS
    assert len(b_families) == SourceV11.GUIDED_TARGET_TASKS
    selected_families = a_families + b_families
    all_records = [
        candidate(
            index,
            selected_families[index]
            if index < len(selected_families)
            else SHADOW_FAMILIES[index % len(SHADOW_FAMILIES)],
        )
        for index in range(SourceV11.CANDIDATE_COUNT)
    ]
    preflight_tracked, full_tracked = tracked_closures()
    preflight = SourceV11.AuthorizedPreflight(
        campaign=SourceV11.PREFLIGHT_CAMPAIGN,
        seal_repository_commit_id=PREFLIGHT_REVISION,
        source_repository_commit_id=SOURCE_REVISION,
        authorization_sha256="0" * 64,
        controller_publisher_canary_receipt_sha256="1" * 64,
        compute_canary_launch_receipt_sha256="2" * 64,
        compute_canary_terminal_poll_receipt_sha256="3" * 64,
        compute_canary_seal_plan_sha256="4" * 64,
        compute_canary_attestation_sha256="5" * 64,
        code_manifest_sha256=CODE_MANIFEST_SHA256,
        full_launch_authorized=True,
        tracked_file_sha256=preflight_tracked,
    )
    return SourceV11.AuthorizedConfirmation(
        campaign=SourceV11.CAMPAIGN,
        benchmark_revision=SourceV11.BENCHMARK_REVISION,
        seal_repository_commit_id=FULL_REVISION,
        source_inventory_sha256="6" * 64,
        code_manifest_sha256=CODE_MANIFEST_SHA256,
        launch_receipt_sha256="7" * 64,
        execution_receipt_sha256="8" * 64,
        attestation_sha256="9" * 64,
        preflight=preflight,
        confirmation_a=tuple(all_records[:SourceV11.CONFIRMATION_TASKS]),
        guided_b=tuple(all_records[
            SourceV11.CONFIRMATION_TASKS:
            SourceV11.CONFIRMATION_TASKS + SourceV11.GUIDED_TARGET_TASKS
        ]),
        eligible_records=tuple(all_records),
        all_records=tuple(all_records),
        outcome_counts={
            "input-rejected": 0,
            "resource-excluded": 0,
            "success": SourceV11.CANDIDATE_COUNT,
        },
        resource_exclusions_by_family={},
        tracked_file_sha256=full_tracked,
    )


def changed_record(record: dict, **updates: object) -> dict:
    result = dict(record)
    result.update(updates)
    return result


class V11AdapterTests(unittest.TestCase):
    def load(self, authorized: SourceV11.AuthorizedConfirmation):
        snapshot_reader = object()
        paths = object()
        with (
            mock.patch.object(Adapter.SourceV11, "paths_for", return_value=paths) as paths_for,
            mock.patch.object(
                Adapter.SourceV11,
                "load_authorized_confirmation",
                return_value=authorized,
            ) as consume,
            mock.patch.object(Adapter, "read_committed_snapshot", snapshot_reader),
        ):
            result = Adapter.load_authorized_cohorts(FULL_REVISION)
        paths_for.assert_called_once_with()
        consume.assert_called_once_with(
            paths,
            snapshot_reader=snapshot_reader,
            seal_revision=FULL_REVISION,
        )
        return result

    def assert_rejected(self, authorized, pattern: str):
        with (
            mock.patch.object(Adapter.SourceV11, "paths_for", return_value=object()),
            mock.patch.object(
                Adapter.SourceV11,
                "load_authorized_confirmation",
                return_value=authorized,
            ),
            mock.patch.object(Adapter, "read_committed_snapshot", object()),
            self.assertRaisesRegex(Adapter.V11AdapterError, pattern),
        ):
            Adapter.load_authorized_cohorts(FULL_REVISION)

    def test_exact_consumer_call_and_comprehensive_immutable_result(self):
        source = authorized_confirmation()
        result = self.load(source)
        bindings = result.bindings
        self.assertEqual(len(result.confirmation_a.records), 650)
        self.assertEqual(len(result.guided_b.records), 300)
        self.assertEqual(
            set(result.confirmation_a.records[0]),
            set(Adapter.SOURCE_PROJECTION_FIELDS),
        )
        self.assertNotIn("candidate_origin", result.confirmation_a.records[0])
        self.assertEqual(bindings.seal_repository_commit_id, FULL_REVISION)
        self.assertEqual(
            bindings.preflight_source_repository_commit_id, SOURCE_REVISION,
        )
        self.assertEqual(
            bindings.preflight_seal_repository_commit_id, PREFLIGHT_REVISION,
        )
        self.assertIs(bindings.preflight_full_launch_authorized, True)
        self.assertEqual(
            bindings.preflight_code_manifest_sha256, CODE_MANIFEST_SHA256,
        )
        self.assertEqual(bindings.confirmation_a_count, 650)
        self.assertEqual(bindings.guided_b_count, 300)
        translator_records = [
            {"path": path, "sha256": source.tracked_file_sha256[path]}
            for path in sorted(source.tracked_file_sha256)
            if path.startswith("src/translate/") and path.endswith(".py")
        ]
        self.assertEqual(
            bindings.translator_source_sha256, digest(translator_records),
        )
        self.assertEqual(
            bindings.confirmation_a_source_projection_sha256,
            result.confirmation_a.source_projection_sha256,
        )
        self.assertEqual(
            bindings.guided_b_candidate_indices_sha256,
            result.guided_b.candidate_indices_sha256,
        )
        self.assertEqual(
            bindings.combined_tracked_file_sha256[
                Adapter.CODE_MANIFEST_RELATIVE
            ],
            CODE_MANIFEST_SHA256,
        )
        with self.assertRaises(TypeError):
            result.confirmation_a.records[0]["family"] = "changed"
        with self.assertRaises(TypeError):
            result.confirmation_a.records[0]["aliases"][0]["family"] = "changed"
        with self.assertRaises(TypeError):
            bindings.full_tracked_file_sha256["new"] = "0" * 64
        with self.assertRaises(dataclasses.FrozenInstanceError):
            bindings.campaign = "changed"
        source.confirmation_a[0]["family"] = "mutated-after-load"
        source.tracked_file_sha256[Adapter.CODE_MANIFEST_RELATIVE] = "f" * 64
        self.assertNotEqual(
            result.confirmation_a.records[0]["family"], "mutated-after-load",
        )
        self.assertEqual(
            bindings.full_tracked_file_sha256[Adapter.CODE_MANIFEST_RELATIVE],
            CODE_MANIFEST_SHA256,
        )

    def test_invalid_revision_is_rejected_before_consumer_or_paths(self):
        with (
            mock.patch.object(Adapter.SourceV11, "paths_for") as paths_for,
            mock.patch.object(
                Adapter.SourceV11, "load_authorized_confirmation",
            ) as consume,
            self.assertRaisesRegex(Adapter.V11AdapterError, "exact 40-hex"),
        ):
            Adapter.load_authorized_cohorts("3" * 39)
        paths_for.assert_not_called()
        consume.assert_not_called()

    def test_campaign_commit_and_hash_bindings_are_fail_closed(self):
        source = authorized_confirmation()
        cases = (
            dataclasses.replace(source, campaign="v9"),
            dataclasses.replace(source, seal_repository_commit_id="4" * 40),
            dataclasses.replace(source, attestation_sha256="not-a-sha"),
            dataclasses.replace(
                source,
                preflight=dataclasses.replace(
                    source.preflight, full_launch_authorized=False,
                ),
            ),
            dataclasses.replace(
                source,
                preflight=dataclasses.replace(
                    source.preflight, code_manifest_sha256="d" * 64,
                ),
            ),
        )
        for changed in cases:
            with self.subTest(changed=changed):
                self.assert_rejected(changed, "authorization binding")

    def test_exact_a_and_b_cardinalities_are_required(self):
        source = authorized_confirmation()
        for changed in (
            dataclasses.replace(source, confirmation_a=source.confirmation_a[:-1]),
            dataclasses.replace(
                source,
                confirmation_a=source.confirmation_a + (source.all_records[950],),
            ),
            dataclasses.replace(source, guided_b=source.guided_b[:-1]),
            dataclasses.replace(
                source,
                guided_b=source.guided_b + (source.all_records[950],),
            ),
        ):
            with self.subTest(size=(len(changed.confirmation_a), len(changed.guided_b))):
                self.assert_rejected(changed, "family coverage")

    def test_within_cohort_duplicates_and_cross_cohort_overlap_are_rejected(self):
        source = authorized_confirmation()
        duplicate_a = list(source.confirmation_a)
        duplicate_a[1] = duplicate_a[0]
        self.assert_rejected(
            dataclasses.replace(source, confirmation_a=tuple(duplicate_a)),
            "duplicate identities",
        )
        overlapping_b = list(source.guided_b)
        overlapping_b[0] = source.confirmation_a[0]
        self.assert_rejected(
            dataclasses.replace(source, guided_b=tuple(overlapping_b)),
            "cohorts overlap",
        )

    def test_selected_record_must_be_exactly_eligible(self):
        source = authorized_confirmation()
        changed = changed_record(
            source.confirmation_a[0], eligible_for_cohort=False,
            supported=False,
        )
        all_records = list(source.all_records)
        all_records[0] = changed
        confirmation = list(source.confirmation_a)
        confirmation[0] = changed
        self.assert_rejected(
            dataclasses.replace(
                source,
                all_records=tuple(all_records),
                eligible_records=tuple(all_records[1:]),
                confirmation_a=tuple(confirmation),
            ),
            "native supported success",
        )

    def test_selected_record_must_retain_native_success_disposition(self):
        source = authorized_confirmation()
        cases = {
            "process_returncode": 1,
            "complete_process_group_reaped": False,
            "support_exclusion_reasons": ["unsupported-feature"],
            "normalization": None,
            "sas": None,
            "sas_bytes": 0,
            "sas_sha256": None,
            "partial_sas_evidence": {"discarded": True},
            "resource_exclusion_kind": "time",
        }
        for key, value in cases.items():
            changed = changed_record(source.confirmation_a[0], **{key: value})
            all_records = list(source.all_records)
            eligible = list(source.eligible_records)
            confirmation = list(source.confirmation_a)
            all_records[0] = changed
            eligible[0] = changed
            confirmation[0] = changed
            with self.subTest(field=key):
                self.assert_rejected(
                    dataclasses.replace(
                        source,
                        all_records=tuple(all_records),
                        eligible_records=tuple(eligible),
                        confirmation_a=tuple(confirmation),
                    ),
                    "native supported success",
                )

    def test_full_census_order_identity_and_eligible_projection_are_bound(self):
        source = authorized_confirmation()
        reordered = list(source.all_records)
        reordered[0], reordered[1] = reordered[1], reordered[0]
        self.assert_rejected(
            dataclasses.replace(source, all_records=tuple(reordered)),
            "full-census order",
        )
        self.assert_rejected(
            dataclasses.replace(source, eligible_records=source.eligible_records[:-1]),
            "eligible-record projection",
        )

    def test_every_family_floor_and_guided_cap_is_rechecked(self):
        source = authorized_confirmation()
        limits = {
            "MIN_CONFIRMATION_FAMILIES": 33,
            "MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES": 13,
            "MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS": 101,
            "MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES": 11,
            "MIN_GUIDED_FAMILIES": 33,
            "MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES": 13,
            "MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS": 51,
            "MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES": 11,
            "MAX_GUIDED_TASKS_PER_FAMILY": 11,
        }
        for name, value in limits.items():
            with self.subTest(limit=name), mock.patch.object(
                Adapter.SourceV11, name, value,
            ):
                self.assert_rejected(source, "family coverage")
        bad = changed_record(
            source.confirmation_a[0], is_shadow_unrepresented=False,
        )
        all_records = list(source.all_records)
        eligible = list(source.eligible_records)
        confirmation = list(source.confirmation_a)
        all_records[0] = bad
        eligible[0] = bad
        confirmation[0] = bad
        self.assert_rejected(
            dataclasses.replace(
                source, all_records=tuple(all_records),
                eligible_records=tuple(eligible),
                confirmation_a=tuple(confirmation),
            ),
            "family classification",
        )

    def test_tracked_closures_and_translator_set_are_fail_closed(self):
        source = authorized_confirmation()
        full = dict(source.tracked_file_sha256)
        full["../escape"] = "0" * 64
        self.assert_rejected(
            dataclasses.replace(source, tracked_file_sha256=full),
            "tracked",
        )
        full = dict(source.tracked_file_sha256)
        del full["src/translate/translator-00.py"]
        self.assert_rejected(
            dataclasses.replace(source, tracked_file_sha256=full),
            "translator source closure",
        )
        preflight = dict(source.preflight.tracked_file_sha256)
        preflight["src/translate/translator-00.py"] = "f" * 64
        self.assert_rejected(
            dataclasses.replace(
                source,
                preflight=dataclasses.replace(
                    source.preflight, tracked_file_sha256=preflight,
                ),
            ),
            "tracked closures disagree",
        )
        full = dict(source.tracked_file_sha256)
        full["experiments/artifacts/v10-full/attestation.json"] = "0" * 64
        self.assert_rejected(
            dataclasses.replace(source, tracked_file_sha256=full),
            "tracked closure changed",
        )
        full = dict(source.tracked_file_sha256)
        preflight = dict(source.preflight.tracked_file_sha256)
        full["src/translate/extra.py"] = "e" * 64
        preflight["src/translate/extra.py"] = "e" * 64
        self.assert_rejected(
            dataclasses.replace(
                source,
                tracked_file_sha256=full,
                preflight=dataclasses.replace(
                    source.preflight, tracked_file_sha256=preflight,
                ),
            ),
            "translator source closure",
        )

    def test_outcome_and_resource_summaries_are_cross_validated(self):
        source = authorized_confirmation()
        bad_outcomes = {
            "input-rejected": 0,
            "resource-excluded": 1,
            "success": SourceV11.CANDIDATE_COUNT - 1,
        }
        self.assert_rejected(
            dataclasses.replace(source, outcome_counts=bad_outcomes),
            "differs from census records",
        )
        self.assert_rejected(
            dataclasses.replace(
                source,
                resource_exclusions_by_family={
                    "not-in-census": {"memory": 0, "time": 1, "total": 1},
                },
            ),
            "resource-exclusion summary",
        )
        self.assert_rejected(
            dataclasses.replace(
                source,
                resource_exclusions_by_family={
                    source.all_records[0]["family"]: {
                        "memory": 0, "time": 1, "total": 1,
                    },
                },
            ),
            "resource-exclusion total",
        )


if __name__ == "__main__":
    unittest.main()
