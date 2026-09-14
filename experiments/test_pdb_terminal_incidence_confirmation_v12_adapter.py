#!/usr/bin/env python3
"""Focused tests for the freeze-time V12 Confirmation A/B adapter."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import unittest
from types import MappingProxyType
from unittest import mock

import pdb_terminal_incidence_confirmation_source_consumer_v12 as SourceV12
import pdb_terminal_incidence_confirmation_v12_adapter as Adapter


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
    SourceV12.ALL_PRIOR_UNREPRESENTED_FAMILIES[:10]
)
EXTRA_NONSHADOW_FAMILIES = ["airport", "blocks"]
SHADOW_FAMILIES = list(SourceV12.SHADOW_FAMILIES[:20])


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
        "schema": SourceV12.CANDIDATE_SCHEMA,
        "candidate_origin": "v12-fresh",
        "code_manifest_sha256": CODE_MANIFEST_SHA256,
        "repository_commit_id": PREFLIGHT_REVISION,
        "candidate_index": index,
        **canonical,
        "canonical_path": canonical["problem_file"],
        "is_shadow_family": family in SourceV12.SHADOW_FAMILIES,
        "is_shadow_unrepresented": family not in SourceV12.SHADOW_FAMILIES,
        "is_all_prior_represented": family in SourceV12.ALL_PRIOR_FAMILIES,
        "is_all_prior_unrepresented": family not in SourceV12.ALL_PRIOR_FAMILIES,
        "aliases": [canonical],
        "status": "success",
        "translation_attempted": True,
        "process_returncode": 0,
        "process_cpu_time_us": 1000,
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
        "experiments/artifacts/v12-preflight/authorization.json": "a" * 64,
    }
    full = {
        **common,
        "experiments/artifacts/v12-full/attestation.json": "b" * 64,
    }
    return preflight, full


def authorized_confirmation() -> SourceV12.AuthorizedConfirmation:
    a_families = confirmation_families()
    b_families = guided_families()
    assert len(a_families) == SourceV12.CONFIRMATION_TASKS
    assert len(b_families) == SourceV12.GUIDED_TARGET_TASKS
    selected_families = a_families + b_families
    all_records = [
        candidate(
            index,
            selected_families[index]
            if index < len(selected_families)
            else SHADOW_FAMILIES[index % len(SHADOW_FAMILIES)],
        )
        for index in range(SourceV12.CANDIDATE_COUNT)
    ]
    preflight_tracked, full_tracked = tracked_closures()
    preflight = SourceV12.AuthorizedPreflight(
        campaign=SourceV12.PREFLIGHT_CAMPAIGN,
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
    return SourceV12.AuthorizedConfirmation(
        campaign=SourceV12.CAMPAIGN,
        benchmark_revision=SourceV12.BENCHMARK_REVISION,
        seal_repository_commit_id=FULL_REVISION,
        source_inventory_sha256="6" * 64,
        code_manifest_sha256=CODE_MANIFEST_SHA256,
        launch_receipt_sha256="7" * 64,
        execution_receipt_sha256="8" * 64,
        attestation_sha256="9" * 64,
        preflight=preflight,
        confirmation_a=tuple(all_records[:SourceV12.CONFIRMATION_TASKS]),
        guided_b=tuple(all_records[
            SourceV12.CONFIRMATION_TASKS:
            SourceV12.CONFIRMATION_TASKS + SourceV12.GUIDED_TARGET_TASKS
        ]),
        eligible_records=tuple(all_records),
        all_records=tuple(all_records),
        outcome_counts={
            "input-rejected": 0,
            "resource-excluded": 0,
            "success": SourceV12.CANDIDATE_COUNT,
        },
        resource_exclusions_by_family={},
        tracked_file_sha256=full_tracked,
    )


def changed_record(record: dict, **updates: object) -> dict:
    result = dict(record)
    result.update(updates)
    return result


def consumer_freeze(value: object) -> object:
    if type(value) is dict:
        return MappingProxyType({
            key: consumer_freeze(item) for key, item in value.items()
        })
    if type(value) is list:
        return tuple(consumer_freeze(item) for item in value)
    return value


def mixed_authorized_confirmation() -> SourceV12.AuthorizedConfirmation:
    source = authorized_confirmation()
    records = list(source.all_records)
    records[950] = changed_record(
        records[950], supported=False, eligible_for_cohort=False,
        support_exclusion_reasons=list(Adapter.SUPPORT_EXCLUSION_REASONS[1:]),
    )
    records[951] = changed_record(
        records[951], status="input-rejected", process_returncode=31,
        supported=False, eligible_for_cohort=False,
        support_exclusion_reasons=["translation-input-rejected"],
        normalization=None, sas=None, sas_bytes=None, sas_sha256=None,
    )
    for index, kind, returncode in ((952, "memory", 20), (953, "time", 21)):
        records[index] = changed_record(
            records[index], status="resource-excluded",
            process_returncode=returncode, support_determined=False,
            supported=None, eligible_for_cohort=False,
            support_exclusion_reasons=None, resource_exclusion_kind=kind,
            normalization=None, sas=None, sas_bytes=None, sas_sha256=None,
        )
    resource_exclusions_by_family = {}
    for record in records:
        kind = record["resource_exclusion_kind"]
        if kind is None:
            continue
        counts = resource_exclusions_by_family.setdefault(
            record["family"], {"memory": 0, "time": 0, "total": 0},
        )
        counts[kind] += 1
        counts["total"] += 1
    return dataclasses.replace(
        source,
        all_records=tuple(records),
        eligible_records=tuple(
            record for record in records if record["eligible_for_cohort"]
        ),
        outcome_counts={
            "input-rejected": 1,
            "resource-excluded": 2,
            "success": SourceV12.CANDIDATE_COUNT - 3,
        },
        resource_exclusions_by_family=resource_exclusions_by_family,
    )


def frozen_mixed_authorized_confirmation() -> SourceV12.AuthorizedConfirmation:
    source = mixed_authorized_confirmation()
    return dataclasses.replace(
        source,
        preflight=dataclasses.replace(
            source.preflight,
            tracked_file_sha256=consumer_freeze(
                source.preflight.tracked_file_sha256
            ),
        ),
        confirmation_a=tuple(
            consumer_freeze(record) for record in source.confirmation_a
        ),
        guided_b=tuple(consumer_freeze(record) for record in source.guided_b),
        eligible_records=tuple(
            consumer_freeze(record) for record in source.eligible_records
        ),
        all_records=tuple(
            consumer_freeze(record) for record in source.all_records
        ),
        outcome_counts=consumer_freeze(source.outcome_counts),
        resource_exclusions_by_family=consumer_freeze(
            source.resource_exclusions_by_family
        ),
        tracked_file_sha256=consumer_freeze(source.tracked_file_sha256),
    )


class V12AdapterTests(unittest.TestCase):
    def load(self, authorized: SourceV12.AuthorizedConfirmation):
        snapshot_reader = object()
        paths = object()
        with (
            mock.patch.object(Adapter.SourceV12, "paths_for", return_value=paths) as paths_for,
            mock.patch.object(
                Adapter.SourceV12,
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
            mock.patch.object(Adapter.SourceV12, "paths_for", return_value=object()),
            mock.patch.object(
                Adapter.SourceV12,
                "load_authorized_confirmation",
                return_value=authorized,
            ),
            mock.patch.object(Adapter, "read_committed_snapshot", object()),
            self.assertRaisesRegex(Adapter.V12AdapterError, pattern),
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
        self.assertEqual(bindings.inventory_families_count, 32)
        self.assertEqual(
            bindings.translation_attempts_count, SourceV12.CANDIDATE_COUNT,
        )
        self.assertEqual(bindings.support_status_counts, {
            "indeterminate": 0,
            "supported": SourceV12.CANDIDATE_COUNT,
            "unsupported": 0,
        })
        self.assertEqual(
            bindings.support_exclusion_counts,
            {reason: 0 for reason in Adapter.SUPPORT_EXCLUSION_REASONS},
        )
        self.assertEqual(
            bindings.resource_exclusion_counts, {"memory": 0, "time": 0},
        )
        for name in (
            "support_status_counts", "support_exclusion_counts",
            "resource_exclusion_counts",
        ):
            self.assertEqual(
                getattr(bindings, name + "_sha256"),
                digest(dict(getattr(bindings, name))),
            )
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
        with self.assertRaises(TypeError):
            bindings.support_status_counts["supported"] = 0
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

    def test_mixed_census_summary_is_dense_conserved_and_authenticated(self):
        source = mixed_authorized_confirmation()
        bindings = self.load(source).bindings
        expected_status = {
            "indeterminate": 2,
            "supported": SourceV12.CANDIDATE_COUNT - 4,
            "unsupported": 2,
        }
        expected_reasons = {
            reason: 1 for reason in Adapter.SUPPORT_EXCLUSION_REASONS
        }
        expected_resource = {"memory": 1, "time": 1}
        self.assertEqual(bindings.inventory_families_count, 32)
        self.assertEqual(
            bindings.translation_attempts_count, bindings.all_records_count,
        )
        self.assertEqual(bindings.eligible_records_count, 1636)
        self.assertEqual(dict(bindings.support_status_counts), expected_status)
        self.assertEqual(
            set(bindings.support_status_counts), set(Adapter.SUPPORT_STATUS_KEYS),
        )
        self.assertEqual(
            dict(bindings.support_exclusion_counts), expected_reasons,
        )
        self.assertEqual(
            set(bindings.support_exclusion_counts),
            set(Adapter.SUPPORT_EXCLUSION_REASONS),
        )
        self.assertEqual(
            dict(bindings.resource_exclusion_counts), expected_resource,
        )
        self.assertEqual(
            set(bindings.resource_exclusion_counts),
            set(Adapter.RESOURCE_EXCLUSION_KEYS),
        )
        self.assertEqual(
            sum(bindings.support_status_counts.values()),
            bindings.all_records_count,
        )
        self.assertEqual(
            bindings.support_status_counts["supported"],
            bindings.eligible_records_count,
        )
        self.assertEqual(
            bindings.support_status_counts["indeterminate"],
            bindings.outcome_counts["resource-excluded"],
        )
        aggregated = {
            key: sum(
                counts[key]
                for counts in bindings.resource_exclusions_by_family.values()
            )
            for key in Adapter.RESOURCE_EXCLUSION_KEYS
        }
        self.assertEqual(dict(bindings.resource_exclusion_counts), aggregated)
        for name, expected in (
            ("support_status_counts", expected_status),
            ("support_exclusion_counts", expected_reasons),
            ("resource_exclusion_counts", expected_resource),
        ):
            self.assertEqual(getattr(bindings, name + "_sha256"), digest(expected))

    def test_recursively_frozen_consumer_shape_is_accepted(self):
        source = frozen_mixed_authorized_confirmation()
        self.assertIsInstance(source.all_records[951], MappingProxyType)
        self.assertIsInstance(
            source.all_records[951]["support_exclusion_reasons"], tuple,
        )
        bindings = self.load(source).bindings
        self.assertEqual(bindings.translation_attempts_count, 1640)
        self.assertEqual(bindings.support_status_counts["unsupported"], 2)

    def test_invalid_revision_is_rejected_before_consumer_or_paths(self):
        with (
            mock.patch.object(Adapter.SourceV12, "paths_for") as paths_for,
            mock.patch.object(
                Adapter.SourceV12, "load_authorized_confirmation",
            ) as consume,
            self.assertRaisesRegex(Adapter.V12AdapterError, "exact 40-hex"),
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
            support_exclusion_reasons=[Adapter.SUPPORT_EXCLUSION_REASONS[1]],
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
                    "classification|native supported success",
                )

    def test_census_classification_is_fail_closed(self):
        cases = (
            (
                {"translation_attempted": False},
                "translation attempt",
            ),
            (
                {"supported": True, "eligible_for_cohort": False},
                "classification",
            ),
            (
                {
                    "supported": False,
                    "eligible_for_cohort": False,
                    "support_exclusion_reasons": [
                        Adapter.SUPPORT_EXCLUSION_REASONS[1],
                        Adapter.SUPPORT_EXCLUSION_REASONS[1],
                    ],
                },
                "classification",
            ),
            (
                {
                    "status": "resource-excluded",
                    "support_determined": False,
                    "supported": None,
                    "eligible_for_cohort": False,
                    "support_exclusion_reasons": None,
                    "resource_exclusion_kind": "disk",
                },
                "classification",
            ),
        )
        for updates, pattern in cases:
            source = authorized_confirmation()
            records = list(source.all_records)
            records[950] = changed_record(records[950], **updates)
            with self.subTest(updates=updates):
                self.assert_rejected(
                    dataclasses.replace(source, all_records=tuple(records)),
                    pattern,
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
                Adapter.SourceV12, name, value,
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
        for campaign in range(1, 12):
            full = dict(source.tracked_file_sha256)
            full[
                "experiments/artifacts/v{}-full/attestation.json".format(campaign)
            ] = "0" * 64
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
            "success": SourceV12.CANDIDATE_COUNT - 1,
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
        mixed = mixed_authorized_confirmation()
        self.assert_rejected(
            dataclasses.replace(
                mixed,
                resource_exclusions_by_family={
                    mixed.all_records[0]["family"]: {
                        "memory": 1, "time": 1, "total": 2,
                    },
                },
            ),
            "differs from census records",
        )


if __name__ == "__main__":
    unittest.main()
