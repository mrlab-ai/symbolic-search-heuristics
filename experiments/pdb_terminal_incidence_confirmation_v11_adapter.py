#!/usr/bin/env python3
"""Freeze-time adapter for independently authorized V11 source cohorts.

The V11 consumer authenticates the live scientific payload and its committed
control evidence.  This module deliberately exposes only immutable source
projections plus the hashes needed to bind later Confirmation A/B freezes to
that authorization.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import PurePosixPath
from types import MappingProxyType
from typing import Any

import pdb_terminal_incidence_confirmation_source_consumer_v11 as SourceV11
from pdb_terminal_incidence_v11_snapshot_reader import read_committed_snapshot


class V11AdapterError(RuntimeError):
    """The authorized V11 result cannot safely seed Confirmation A/B."""


SCHEMA = (
    "symbolic-search-heuristics/"
    "universal-unseen-confirmation-source-adapter/v1/campaign-v11"
)
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
PRINTABLE_PATH_RE = re.compile(r"[!-~]+\Z")
OLD_CAMPAIGN_RE = re.compile(r"(?:^|[-_./])v(?:[1-9]|10)(?:[-_./]|$)")
TRANSLATOR_FILE_COUNT = 38
CODE_MANIFEST_RELATIVE = (
    "experiments/"
    "pdb_terminal_incidence_confirmation_source_audit_v11_code.sha256"
)

SOURCE_PROJECTION_FIELDS = (
    "candidate_index",
    "directory",
    "family",
    "problem",
    "domain_file",
    "problem_file",
    "domain_sha256",
    "problem_sha256",
    "canonical_path",
    "is_shadow_family",
    "is_shadow_unrepresented",
    "is_all_prior_represented",
    "is_all_prior_unrepresented",
    "aliases",
)
ALIAS_FIELDS = (
    "directory",
    "family",
    "problem",
    "domain_file",
    "problem_file",
    "domain_sha256",
    "problem_sha256",
)
SUPPORT_STATUS_KEYS = ("indeterminate", "supported", "unsupported")
SUPPORT_EXCLUSION_REASONS = (
    "translation-input-rejected",
    "no-serialized-operators",
    "nonpositive-serialized-operator-cost",
    "serialized-axioms",
    "serialized-conditional-effects",
    "normalized-axioms",
)
RESOURCE_EXCLUSION_KEYS = ("memory", "time")


@dataclass(frozen=True)
class V11CohortProjection:
    role: str
    records: tuple[Mapping[str, Any], ...]
    candidate_indices_sha256: str
    source_projection_sha256: str


@dataclass(frozen=True)
class V11SourceBindings:
    schema: str
    campaign: str
    benchmark_revision: str
    seal_repository_commit_id: str
    preflight_campaign: str
    preflight_source_repository_commit_id: str
    preflight_seal_repository_commit_id: str
    preflight_full_launch_authorized: bool
    source_inventory_sha256: str
    code_manifest_sha256: str
    preflight_code_manifest_sha256: str
    launch_receipt_sha256: str
    execution_receipt_sha256: str
    attestation_sha256: str
    preflight_authorization_sha256: str
    controller_publisher_canary_receipt_sha256: str
    compute_canary_launch_receipt_sha256: str
    compute_canary_terminal_poll_receipt_sha256: str
    compute_canary_seal_plan_sha256: str
    compute_canary_attestation_sha256: str
    translator_source_sha256: str
    inventory_families_count: int
    translation_attempts_count: int
    all_records_count: int
    all_records_sha256: str
    all_source_projection_sha256: str
    eligible_records_count: int
    eligible_records_sha256: str
    eligible_candidate_indices_sha256: str
    eligible_source_projection_sha256: str
    confirmation_a_count: int
    confirmation_a_candidate_indices_sha256: str
    confirmation_a_source_projection_sha256: str
    guided_b_count: int
    guided_b_candidate_indices_sha256: str
    guided_b_source_projection_sha256: str
    outcome_counts: Mapping[str, int]
    outcome_counts_sha256: str
    support_status_counts: Mapping[str, int]
    support_status_counts_sha256: str
    support_exclusion_counts: Mapping[str, int]
    support_exclusion_counts_sha256: str
    resource_exclusion_counts: Mapping[str, int]
    resource_exclusion_counts_sha256: str
    resource_exclusions_by_family: Mapping[str, Any]
    resource_exclusions_by_family_sha256: str
    full_tracked_file_sha256: Mapping[str, str]
    full_tracked_file_sha256_digest: str
    preflight_tracked_file_sha256: Mapping[str, str]
    preflight_tracked_file_sha256_digest: str
    combined_tracked_file_sha256: Mapping[str, str]
    combined_tracked_file_sha256_digest: str


@dataclass(frozen=True)
class AuthorizedV11Cohorts:
    bindings: V11SourceBindings
    confirmation_a: V11CohortProjection
    guided_b: V11CohortProjection


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            if type(key) is not str:
                raise V11AdapterError("V11 mapping key is not text")
            result[key] = _plain(item)
        return result
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    if value is None or type(value) in (bool, int, float, str):
        return value
    raise V11AdapterError("V11 value is not finite canonical JSON")


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            _plain(value), sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise V11AdapterError("V11 value is not finite canonical JSON") from err


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(item) for item in value)
    return value


def _is_sha256(value: Any) -> bool:
    return type(value) is str and SHA256_RE.fullmatch(value) is not None


def _is_commit(value: Any) -> bool:
    return type(value) is str and COMMIT_RE.fullmatch(value) is not None


def _source_identity(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        record["directory"], record["problem"], record["problem_file"],
        record["domain_file"],
    )


def _alias_identity(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        record["directory"], record["problem"], record["problem_file"],
        record["domain_file"],
    )


def _project_record(record: Any) -> dict[str, Any]:
    if not isinstance(record, Mapping):
        raise V11AdapterError("V11 candidate record is not a mapping")
    missing = set(SOURCE_PROJECTION_FIELDS) - set(record)
    if missing:
        raise V11AdapterError("V11 candidate lacks stable source fields")
    index = record["candidate_index"]
    if type(index) is not int or not 0 <= index < SourceV11.CANDIDATE_COUNT:
        raise V11AdapterError("V11 candidate index is invalid")
    text_fields = (
        "directory", "family", "problem", "domain_file", "problem_file",
        "canonical_path",
    )
    if any(type(record[key]) is not str or not record[key] for key in text_fields):
        raise V11AdapterError("V11 source identity is invalid")
    if (
        record["canonical_path"] != record["problem_file"]
        or not _is_sha256(record["domain_sha256"])
        or not _is_sha256(record["problem_sha256"])
    ):
        raise V11AdapterError("V11 source hash or canonical path is invalid")
    family = record["family"]
    expected_flags = {
        "is_shadow_family": family in SourceV11.SHADOW_FAMILIES,
        "is_shadow_unrepresented": family not in SourceV11.SHADOW_FAMILIES,
        "is_all_prior_represented": family in SourceV11.ALL_PRIOR_FAMILIES,
        "is_all_prior_unrepresented": family not in SourceV11.ALL_PRIOR_FAMILIES,
    }
    if any(record[key] is not value for key, value in expected_flags.items()):
        raise V11AdapterError("V11 source family classification changed")
    aliases = record["aliases"]
    if (
        not isinstance(aliases, Sequence)
        or isinstance(aliases, (str, bytes, bytearray))
        or not aliases
    ):
        raise V11AdapterError("V11 source aliases are invalid")
    plain_aliases = []
    for alias in aliases:
        if not isinstance(alias, Mapping) or set(alias) != set(ALIAS_FIELDS):
            raise V11AdapterError("V11 source alias shape changed")
        plain = _plain(alias)
        if (
            any(type(plain[key]) is not str or not plain[key] for key in ALIAS_FIELDS)
            or not _is_sha256(plain["domain_sha256"])
            or not _is_sha256(plain["problem_sha256"])
            or plain["family"] != family
            or plain["problem_sha256"] != record["problem_sha256"]
        ):
            raise V11AdapterError("V11 source alias changed")
        plain_aliases.append(plain)
    canonical_alias = {key: record[key] for key in ALIAS_FIELDS}
    identities = [_alias_identity(alias) for alias in plain_aliases]
    if (
        plain_aliases[0] != canonical_alias
        or identities != sorted(identities)
        or len(identities) != len(set(identities))
    ):
        raise V11AdapterError("V11 source alias order or identity changed")
    projection = {
        key: (_plain(aliases) if key == "aliases" else record[key])
        for key in SOURCE_PROJECTION_FIELDS
    }
    return projection


def _validate_candidate_result(
    record: Any, *, code_manifest_sha256: str, repository_commit_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    projection = _project_record(record)
    if (
        record.get("schema") != SourceV11.CANDIDATE_SCHEMA
        or record.get("candidate_origin") != "v11-fresh"
        or record.get("code_manifest_sha256") != code_manifest_sha256
        or record.get("repository_commit_id") != repository_commit_id
        or type(record.get("eligible_for_cohort")) is not bool
        or type(record.get("support_determined")) is not bool
        or (
            record.get("supported") is not None
            and type(record.get("supported")) is not bool
        )
        or (
            record.get("eligible_for_cohort") is True
            and (
                record.get("status") != "success"
                or record.get("support_determined") is not True
                or record.get("supported") is not True
            )
        )
    ):
        raise V11AdapterError("V11 candidate authorization fields changed")
    status = record.get("status")
    supported = record.get("supported")
    reasons = record.get("support_exclusion_reasons")
    eligible = record.get("eligible_for_cohort")
    resource_kind = record.get("resource_exclusion_kind")
    if record.get("translation_attempted") is not True:
        raise V11AdapterError("V11 candidate translation attempt changed")
    if status == "success":
        structural_reasons = SUPPORT_EXCLUSION_REASONS[1:]
        valid_reasons = (
            isinstance(reasons, (tuple, list))
            and list(reasons) == [
                reason for reason in structural_reasons if reason in reasons
            ]
        )
        valid = (
            record.get("support_determined") is True
            and type(supported) is bool
            and eligible is supported
            and resource_kind is None
            and valid_reasons
            and ((supported is True and len(reasons) == 0)
                 or (supported is False and len(reasons) > 0))
        )
    elif status == "input-rejected":
        valid = (
            record.get("support_determined") is True
            and supported is False
            and eligible is False
            and isinstance(reasons, (tuple, list))
            and list(reasons) == ["translation-input-rejected"]
            and resource_kind is None
        )
    elif status == "resource-excluded":
        valid = (
            record.get("support_determined") is False
            and supported is None
            and eligible is False
            and reasons is None
            and resource_kind in RESOURCE_EXCLUSION_KEYS
        )
    else:
        valid = False
    if not valid:
        raise V11AdapterError("V11 candidate classification changed")
    return _plain(record), projection


def _classification_summaries(records: list[dict[str, Any]]) -> dict[str, Any]:
    outcomes = Counter(record["status"] for record in records)
    outcome_counts = {
        key: outcomes[key]
        for key in ("input-rejected", "resource-excluded", "success")
    }
    support_labels = [
        "supported" if record["supported"] is True else (
            "unsupported" if record["supported"] is False else "indeterminate"
        )
        for record in records
    ]
    support_statuses = Counter(support_labels)
    support_status_counts = {
        key: support_statuses[key] for key in SUPPORT_STATUS_KEYS
    }
    support_reasons = Counter(
        reason for record in records
        for reason in (record["support_exclusion_reasons"] or [])
    )
    support_exclusion_counts = {
        reason: support_reasons[reason] for reason in SUPPORT_EXCLUSION_REASONS
    }
    resource_records = [
        record for record in records if record["status"] == "resource-excluded"
    ]
    resource_kinds = Counter(
        record["resource_exclusion_kind"] for record in resource_records
    )
    resource_exclusion_counts = {
        key: resource_kinds[key] for key in RESOURCE_EXCLUSION_KEYS
    }
    resource_exclusions_by_family = {}
    for family in sorted({record["family"] for record in resource_records}):
        selected = [
            record for record in resource_records if record["family"] == family
        ]
        resource_exclusions_by_family[family] = {
            "memory": sum(
                record["resource_exclusion_kind"] == "memory"
                for record in selected
            ),
            "time": sum(
                record["resource_exclusion_kind"] == "time"
                for record in selected
            ),
            "total": len(selected),
        }
    return {
        "inventory_families_count": len({record["family"] for record in records}),
        "translation_attempts_count": sum(
            record["translation_attempted"] for record in records
        ),
        "outcome_counts": outcome_counts,
        "support_status_counts": support_status_counts,
        "support_exclusion_counts": support_exclusion_counts,
        "resource_exclusion_counts": resource_exclusion_counts,
        "resource_exclusions_by_family": resource_exclusions_by_family,
    }


def _validated_tracked(value: Any, label: str) -> dict[str, str]:
    if not isinstance(value, Mapping) or not value:
        raise V11AdapterError(label + " tracked closure is empty")
    result: dict[str, str] = {}
    for path, digest in value.items():
        if type(path) is not str or PRINTABLE_PATH_RE.fullmatch(path) is None:
            raise V11AdapterError(label + " tracked path is unsafe")
        pure = PurePosixPath(path)
        if (
            pure.is_absolute()
            or pure.as_posix() != path
            or any(part in ("", ".", "..") for part in pure.parts)
            or pure.parts[0] in (".git", ".jj")
            or OLD_CAMPAIGN_RE.search(path) is not None
            or not _is_sha256(digest)
        ):
            raise V11AdapterError(label + " tracked closure changed")
        result[path] = digest
    return dict(sorted(result.items()))


def _validate_outcome_counts(value: Any) -> dict[str, int]:
    expected = {"input-rejected", "resource-excluded", "success"}
    if (
        not isinstance(value, Mapping)
        or set(value) != expected
        or any(type(value[key]) is not int or value[key] < 0 for key in expected)
        or sum(value.values()) != SourceV11.CANDIDATE_COUNT
    ):
        raise V11AdapterError("V11 outcome counts changed")
    return {key: value[key] for key in sorted(expected)}


def _validate_resource_exclusions(
    value: Any, *, census_families: set[str], expected_total: int,
    expected_by_family: Mapping[str, Mapping[str, int]],
) -> dict[str, dict[str, int]]:
    if not isinstance(value, Mapping):
        raise V11AdapterError("V11 resource-exclusion summary changed")
    result = {}
    for family, counts in value.items():
        if (
            type(family) is not str
            or not family
            or family not in census_families
            or not isinstance(counts, Mapping)
            or set(counts) != {"memory", "time", "total"}
            or any(type(counts[key]) is not int or counts[key] < 0 for key in counts)
            or counts["total"] != counts["memory"] + counts["time"]
            or counts["total"] == 0
        ):
            raise V11AdapterError("V11 resource-exclusion summary changed")
        result[family] = {key: counts[key] for key in ("memory", "time", "total")}
    if sum(counts["total"] for counts in result.values()) != expected_total:
        raise V11AdapterError("V11 resource-exclusion total changed")
    result = dict(sorted(result.items()))
    if result != expected_by_family:
        raise V11AdapterError(
            "V11 resource-exclusion summary differs from census records"
        )
    return result


def _validate_family_contract(
    records: list[dict[str, Any]], *, role: str,
) -> None:
    families = {record["family"] for record in records}
    shadow_unrepresented = {
        record["family"] for record in records
        if record["is_shadow_unrepresented"] is True
    }
    all_prior_unrepresented = [
        record for record in records
        if record["is_all_prior_unrepresented"] is True
    ]
    all_prior_unrepresented_families = {
        record["family"] for record in all_prior_unrepresented
    }
    if role == SourceV11.CONFIRMATION_ROLE:
        passed = (
            len(records) == SourceV11.CONFIRMATION_TASKS
            and len(families) >= SourceV11.MIN_CONFIRMATION_FAMILIES
            and len(shadow_unrepresented)
            >= SourceV11.MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES
            and len(all_prior_unrepresented)
            >= SourceV11.MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS
            and len(all_prior_unrepresented_families)
            >= SourceV11.MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES
        )
    elif role == SourceV11.GUIDED_ROLE:
        per_family = Counter(record["family"] for record in records)
        passed = (
            len(records) == SourceV11.GUIDED_TARGET_TASKS
            and len(families) >= SourceV11.MIN_GUIDED_FAMILIES
            and len(shadow_unrepresented)
            >= SourceV11.MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES
            and len(all_prior_unrepresented)
            >= SourceV11.MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS
            and len(all_prior_unrepresented_families)
            >= SourceV11.MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES
            and max(per_family.values(), default=0)
            <= SourceV11.MAX_GUIDED_TASKS_PER_FAMILY
        )
    else:
        raise V11AdapterError("unknown V11 cohort role")
    if not passed:
        raise V11AdapterError(role + " family coverage contract failed")


def _cohort(
    records: Any, *, role: str, all_by_index: Mapping[int, dict[str, Any]],
    eligible_indices: set[int], code_manifest_sha256: str,
    repository_commit_id: str,
) -> tuple[V11CohortProjection, list[dict[str, Any]]]:
    if not isinstance(records, (tuple, list)):
        raise V11AdapterError(role + " cohort is not a sequence")
    plain_records = []
    projections = []
    for record in records:
        plain, projection = _validate_candidate_result(
            record, code_manifest_sha256=code_manifest_sha256,
            repository_commit_id=repository_commit_id,
        )
        reasons = record.get("support_exclusion_reasons")
        if (
            record.get("status") != "success"
            or record.get("process_returncode") != 0
            or record.get("complete_process_group_reaped") is not True
            or record.get("support_determined") is not True
            or record.get("supported") is not True
            or record.get("eligible_for_cohort") is not True
            or not isinstance(reasons, (tuple, list))
            or len(reasons) != 0
            or not isinstance(record.get("normalization"), Mapping)
            or not isinstance(record.get("sas"), Mapping)
            or type(record.get("sas_bytes")) is not int
            or record["sas_bytes"] <= 0
            or not _is_sha256(record.get("sas_sha256"))
            or record.get("partial_sas_evidence") is not None
            or record.get("resource_exclusion_kind") is not None
        ):
            raise V11AdapterError(role + " record is not native supported success")
        index = projection["candidate_index"]
        if all_by_index.get(index) != plain or index not in eligible_indices:
            raise V11AdapterError(role + " record is not an eligible census record")
        plain_records.append(plain)
        projections.append(projection)
    indices = [record["candidate_index"] for record in projections]
    problem_hashes = [record["problem_sha256"] for record in projections]
    sources = [_source_identity(record) for record in projections]
    if (
        len(indices) != len(set(indices))
        or len(problem_hashes) != len(set(problem_hashes))
        or len(sources) != len(set(sources))
    ):
        raise V11AdapterError(role + " cohort contains duplicate identities")
    _validate_family_contract(projections, role=role)
    projection = V11CohortProjection(
        role=role,
        records=tuple(_freeze(record) for record in projections),
        candidate_indices_sha256=_digest(indices),
        source_projection_sha256=_digest(projections),
    )
    return projection, plain_records


def _load_and_validate(seal_revision: str) -> AuthorizedV11Cohorts:
    if not _is_commit(seal_revision):
        raise V11AdapterError("V11 full-seal revision must be exact 40-hex")
    if frozenset(SOURCE_PROJECTION_FIELDS) != SourceV11.INVENTORY_RECORD_KEYS:
        raise V11AdapterError("V11 native source projection shape changed")
    paths = SourceV11.paths_for()
    authorized = SourceV11.load_authorized_confirmation(
        paths,
        snapshot_reader=read_committed_snapshot,
        seal_revision=seal_revision,
    )
    if type(authorized) is not SourceV11.AuthorizedConfirmation:
        raise V11AdapterError("V11 consumer returned an unexpected result")
    preflight = authorized.preflight
    if type(preflight) is not SourceV11.AuthorizedPreflight:
        raise V11AdapterError("V11 preflight result changed")
    commits = (
        authorized.seal_repository_commit_id,
        preflight.source_repository_commit_id,
        preflight.seal_repository_commit_id,
    )
    full_hashes = (
        authorized.source_inventory_sha256,
        authorized.code_manifest_sha256,
        authorized.launch_receipt_sha256,
        authorized.execution_receipt_sha256,
        authorized.attestation_sha256,
    )
    preflight_hashes = (
        preflight.authorization_sha256,
        preflight.controller_publisher_canary_receipt_sha256,
        preflight.compute_canary_launch_receipt_sha256,
        preflight.compute_canary_terminal_poll_receipt_sha256,
        preflight.compute_canary_seal_plan_sha256,
        preflight.compute_canary_attestation_sha256,
        preflight.code_manifest_sha256,
    )
    if (
        authorized.campaign != SourceV11.CAMPAIGN
        or authorized.benchmark_revision != SourceV11.BENCHMARK_REVISION
        or authorized.seal_repository_commit_id != seal_revision
        or preflight.campaign != SourceV11.PREFLIGHT_CAMPAIGN
        or preflight.full_launch_authorized is not True
        or any(not _is_commit(value) for value in commits)
        or len(set(commits)) != len(commits)
        or any(not _is_sha256(value) for value in full_hashes + preflight_hashes)
        or authorized.code_manifest_sha256 != preflight.code_manifest_sha256
    ):
        raise V11AdapterError("V11 authorization binding changed")

    all_records = authorized.all_records
    if not isinstance(all_records, (tuple, list)) or len(all_records) != SourceV11.CANDIDATE_COUNT:
        raise V11AdapterError("V11 full-census cardinality changed")
    all_plain = []
    all_projections = []
    for expected_index, record in enumerate(all_records):
        plain, projection = _validate_candidate_result(
            record, code_manifest_sha256=authorized.code_manifest_sha256,
            repository_commit_id=preflight.seal_repository_commit_id,
        )
        if projection["candidate_index"] != expected_index:
            raise V11AdapterError("V11 full-census order changed")
        all_plain.append(plain)
        all_projections.append(projection)
    problem_hashes = [record["problem_sha256"] for record in all_projections]
    sources = [_source_identity(record) for record in all_projections]
    if len(problem_hashes) != len(set(problem_hashes)) or len(sources) != len(set(sources)):
        raise V11AdapterError("V11 census contains duplicate source identities")

    classification = _classification_summaries(all_plain)

    expected_eligible = [
        record for record in all_plain if record["eligible_for_cohort"] is True
    ]
    eligible_plain = _plain(authorized.eligible_records)
    if eligible_plain != expected_eligible:
        raise V11AdapterError("V11 eligible-record projection changed")
    eligible_indices = {record["candidate_index"] for record in expected_eligible}

    all_by_index = {record["candidate_index"]: record for record in all_plain}
    confirmation_a, confirmation_plain = _cohort(
        authorized.confirmation_a,
        role=SourceV11.CONFIRMATION_ROLE,
        all_by_index=all_by_index,
        eligible_indices=eligible_indices,
        code_manifest_sha256=authorized.code_manifest_sha256,
        repository_commit_id=preflight.seal_repository_commit_id,
    )
    guided_b, guided_plain = _cohort(
        authorized.guided_b,
        role=SourceV11.GUIDED_ROLE,
        all_by_index=all_by_index,
        eligible_indices=eligible_indices,
        code_manifest_sha256=authorized.code_manifest_sha256,
        repository_commit_id=preflight.seal_repository_commit_id,
    )
    confirmation_projections = [_project_record(record) for record in confirmation_plain]
    guided_projections = [_project_record(record) for record in guided_plain]
    if (
        {record["candidate_index"] for record in confirmation_projections}
        & {record["candidate_index"] for record in guided_projections}
        or {record["problem_sha256"] for record in confirmation_projections}
        & {record["problem_sha256"] for record in guided_projections}
        or {_source_identity(record) for record in confirmation_projections}
        & {_source_identity(record) for record in guided_projections}
    ):
        raise V11AdapterError("V11 Confirmation A and guided B cohorts overlap")

    full_tracked = _validated_tracked(
        authorized.tracked_file_sha256, "V11 full",
    )
    preflight_tracked = _validated_tracked(
        preflight.tracked_file_sha256, "V11 preflight",
    )
    if (
        full_tracked.get(CODE_MANIFEST_RELATIVE) != authorized.code_manifest_sha256
        or preflight_tracked.get(CODE_MANIFEST_RELATIVE)
        != authorized.code_manifest_sha256
        or any(
            full_tracked[path] != preflight_tracked[path]
            for path in set(full_tracked) & set(preflight_tracked)
        )
    ):
        raise V11AdapterError("V11 full/preflight tracked closures disagree")
    full_translator = {
        path: digest for path, digest in full_tracked.items()
        if path.startswith("src/translate/") and path.endswith(".py")
    }
    preflight_translator = {
        path: digest for path, digest in preflight_tracked.items()
        if path.startswith("src/translate/") and path.endswith(".py")
    }
    if (
        len(full_translator) != TRANSLATOR_FILE_COUNT
        or full_translator != preflight_translator
    ):
        raise V11AdapterError("V11 translator source closure changed")
    translator_records = [
        {"path": path, "sha256": full_translator[path]}
        for path in sorted(full_translator)
    ]
    combined_tracked = dict(preflight_tracked)
    combined_tracked.update(full_tracked)
    outcome_counts = _validate_outcome_counts(authorized.outcome_counts)
    if outcome_counts != classification["outcome_counts"]:
        raise V11AdapterError("V11 outcome summary differs from census records")
    resource_exclusions = _validate_resource_exclusions(
        authorized.resource_exclusions_by_family,
        census_families={record["family"] for record in all_projections},
        expected_total=outcome_counts["resource-excluded"],
        expected_by_family=classification["resource_exclusions_by_family"],
    )
    support_status_counts = classification["support_status_counts"]
    support_exclusion_counts = classification["support_exclusion_counts"]
    resource_exclusion_counts = classification["resource_exclusion_counts"]
    aggregated_resource_counts = {
        key: sum(counts[key] for counts in resource_exclusions.values())
        for key in RESOURCE_EXCLUSION_KEYS
    }
    if (
        classification["translation_attempts_count"] != len(all_plain)
        or sum(support_status_counts.values()) != len(all_plain)
        or support_status_counts["supported"] != len(expected_eligible)
        or support_status_counts["indeterminate"]
        != outcome_counts["resource-excluded"]
        or support_exclusion_counts["translation-input-rejected"]
        != outcome_counts["input-rejected"]
        or sum(resource_exclusion_counts.values())
        != outcome_counts["resource-excluded"]
        or resource_exclusion_counts != aggregated_resource_counts
    ):
        raise V11AdapterError("V11 classification summary is incoherent")
    eligible_projections = [
        all_projections[record["candidate_index"]] for record in expected_eligible
    ]
    bindings = V11SourceBindings(
        schema=SCHEMA,
        campaign=authorized.campaign,
        benchmark_revision=authorized.benchmark_revision,
        seal_repository_commit_id=authorized.seal_repository_commit_id,
        preflight_campaign=preflight.campaign,
        preflight_source_repository_commit_id=preflight.source_repository_commit_id,
        preflight_seal_repository_commit_id=preflight.seal_repository_commit_id,
        preflight_full_launch_authorized=preflight.full_launch_authorized,
        source_inventory_sha256=authorized.source_inventory_sha256,
        code_manifest_sha256=authorized.code_manifest_sha256,
        preflight_code_manifest_sha256=preflight.code_manifest_sha256,
        launch_receipt_sha256=authorized.launch_receipt_sha256,
        execution_receipt_sha256=authorized.execution_receipt_sha256,
        attestation_sha256=authorized.attestation_sha256,
        preflight_authorization_sha256=preflight.authorization_sha256,
        controller_publisher_canary_receipt_sha256=(
            preflight.controller_publisher_canary_receipt_sha256
        ),
        compute_canary_launch_receipt_sha256=(
            preflight.compute_canary_launch_receipt_sha256
        ),
        compute_canary_terminal_poll_receipt_sha256=(
            preflight.compute_canary_terminal_poll_receipt_sha256
        ),
        compute_canary_seal_plan_sha256=preflight.compute_canary_seal_plan_sha256,
        compute_canary_attestation_sha256=preflight.compute_canary_attestation_sha256,
        translator_source_sha256=_digest(translator_records),
        inventory_families_count=classification["inventory_families_count"],
        translation_attempts_count=classification["translation_attempts_count"],
        all_records_count=len(all_plain),
        all_records_sha256=_digest(all_plain),
        all_source_projection_sha256=_digest(all_projections),
        eligible_records_count=len(expected_eligible),
        eligible_records_sha256=_digest(expected_eligible),
        eligible_candidate_indices_sha256=_digest([
            record["candidate_index"] for record in expected_eligible
        ]),
        eligible_source_projection_sha256=_digest(eligible_projections),
        confirmation_a_count=len(confirmation_a.records),
        confirmation_a_candidate_indices_sha256=(
            confirmation_a.candidate_indices_sha256
        ),
        confirmation_a_source_projection_sha256=(
            confirmation_a.source_projection_sha256
        ),
        guided_b_count=len(guided_b.records),
        guided_b_candidate_indices_sha256=guided_b.candidate_indices_sha256,
        guided_b_source_projection_sha256=guided_b.source_projection_sha256,
        outcome_counts=_freeze(outcome_counts),
        outcome_counts_sha256=_digest(outcome_counts),
        support_status_counts=_freeze(support_status_counts),
        support_status_counts_sha256=_digest(support_status_counts),
        support_exclusion_counts=_freeze(support_exclusion_counts),
        support_exclusion_counts_sha256=_digest(support_exclusion_counts),
        resource_exclusion_counts=_freeze(resource_exclusion_counts),
        resource_exclusion_counts_sha256=_digest(resource_exclusion_counts),
        resource_exclusions_by_family=_freeze(resource_exclusions),
        resource_exclusions_by_family_sha256=_digest(resource_exclusions),
        full_tracked_file_sha256=_freeze(full_tracked),
        full_tracked_file_sha256_digest=_digest(full_tracked),
        preflight_tracked_file_sha256=_freeze(preflight_tracked),
        preflight_tracked_file_sha256_digest=_digest(preflight_tracked),
        combined_tracked_file_sha256=_freeze(combined_tracked),
        combined_tracked_file_sha256_digest=_digest(combined_tracked),
    )
    return AuthorizedV11Cohorts(
        bindings=bindings, confirmation_a=confirmation_a, guided_b=guided_b,
    )


def load_authorized_cohorts(seal_revision: str) -> AuthorizedV11Cohorts:
    """Consume one exact full-seal revision and return immutable A/B inputs."""
    return _load_and_validate(seal_revision)


__all__ = [
    "AuthorizedV11Cohorts", "RESOURCE_EXCLUSION_KEYS", "SOURCE_PROJECTION_FIELDS",
    "SUPPORT_EXCLUSION_REASONS", "SUPPORT_STATUS_KEYS", "V11AdapterError",
    "V11CohortProjection", "V11SourceBindings", "load_authorized_cohorts",
]
