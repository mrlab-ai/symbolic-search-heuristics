#!/usr/bin/env python3
"""Frozen protocol and source loader for terminal-incidence Confirmation A."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path

import pdb_profile_comparison_protocol as Source
import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_v11_adapter as SourceV11


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
PROTOCOL_PATH = SCRIPT_DIR / "pdb_terminal_incidence_confirmation_a_protocol.md"
FREEZE_PATH = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation" /
    "confirmation-a-freeze-v1.json"
)
FREEZE_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-a-freeze/v1"
)
FROZEN_SOURCE_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-a-source/v1/campaign-v11"
)
PROTOCOL = "pdb-terminal-incidence-confirmation-a-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-terminal-incidence-confirmation-a-analysis-v4"
COHORT_ROLE = "source-disjoint-universal-confirmation-a"
COHORT_SEED = (
    "symbolic-search-heuristics/universal-unseen-confirmation-guided-split/v1"
)
BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
BENCHMARK_REPOSITORY = "https://github.com/aibasel/downward-benchmarks.git"
ACCOUNT = "naiss2025-5-561-cpu"
REQUIRED_LAB_VERSION = "8.10"
REQUIRED_PYTHON_VERSION = "3.12.13"
BUILD_OPTIONS = ("release_no_lp",)
PLANNER_REVISION_REQUIRED = "8148f798f13059ee881ad2471bd20cdd61d2ec18"
COHORT_TASKS = 650
MIN_SOURCE_COHORT_FAMILIES = 28
MIN_SOURCE_SHADOW_UNREPRESENTED_FAMILIES = 12
MIN_SOURCE_ALL_PRIOR_UNREPRESENTED_TASKS = 100
MIN_SOURCE_ALL_PRIOR_UNREPRESENTED_FAMILIES = 10
CONFIG_COUNT = 4
CELL_COUNT = 2600
HORIZON = 16
TIME_LIMIT_SECONDS = 1800
MEMORY_LIMIT_MIB = 24576
RUNS_PER_ARRAY_TASK = 3
EXPECTED_ARRAY_TASKS = 867
SCHEDULER_TIME_LIMIT = "01:40:00"
SCHEDULER_MEMORY = "26G"

PRIMARY_LABELS = (
    "pdb_bdd_prefix_shadow",
    "pdb_goal_prefix_shadow",
    "pdb_goal_fill_shadow",
    "pdb_cegar_shadow",
)
# The legacy analyzer checks this name while validating labels.  Confirmation A
# has no intervention cell, so this value is deliberately outside LABELS.
INTERVENTION_LABEL = "__no_confirmation_a_intervention__"

MIN_ELIGIBLE_TASKS = 300
MIN_ELIGIBLE_FAMILIES = 25
MIN_COMPARISON_TASKS = 300
MIN_COMPARISON_FAMILIES = 25
MIN_TARGET_STRICT_PAIRS = 600
# Retained for the frozen all-predictor-strict sensitivity and for the legacy
# shadow analyzer, which shares the generic gate implementation.
MIN_SHARED_STRICT_PAIRS = 600
MIN_PRIMARY_CONCORDANCE_NUMERATOR = 13
MIN_PRIMARY_CONCORDANCE_DENOMINATOR = 20
MIN_ADVANTAGE_NUMERATOR = 1
MIN_ADVANTAGE_DENOMINATOR = 50
BOOTSTRAP_REPLICATES = 100000
BOOTSTRAP_SEED = 20260901

PRIMARY_PREDICTOR = "I"
MASKED_ADD_SIZE_DIAGNOSTIC = "D"
ACTIVE_VALUE_COUNT_DIAGNOSTIC = "value_count"
MEET_CERTIFICATE = "meet"
CERTIFICATE_BASELINES = (
    "kD", "mQ", "mJ", "Cartesian", "width", "ADD", MEET_CERTIFICATE,
)
PREDICTORS = (
    PRIMARY_PREDICTOR,
    MASKED_ADD_SIZE_DIAGNOSTIC,
    ACTIVE_VALUE_COUNT_DIAGNOSTIC,
    *CERTIFICATE_BASELINES,
)
PREDICTOR_BASELINES = PREDICTORS[1:]

MIN_NEW_STRATUM_COMPARISON_TASKS = 50
MIN_NEW_STRATUM_COMPARISON_FAMILIES = 10
MIN_NEW_STRATUM_TARGET_STRICT_PAIRS = 100
MIN_NEW_STRATUM_CONCORDANCE_NUMERATOR = 13
MIN_NEW_STRATUM_CONCORDANCE_DENOMINATOR = 20
MIN_NEW_STRATUM_ADVANTAGE_NUMERATOR = 1
MIN_NEW_STRATUM_ADVANTAGE_DENOMINATOR = 50

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
def canonical_json(value) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise ProtocolError("value is not canonical finite JSON") from err


def canonical_json_line(value) -> bytes:
    return canonical_json(value) + b"\n"


def sha256_file(path: Path) -> str:
    try:
        return SafeIO.read_regular_file(
            Path(path), label="hashed file"
        ).sha256
    except SafeIO.SafeReadError as err:
        raise ProtocolError(str(err)) from err


def _safe_read_root(path: Path) -> Path:
    path = Path(path)
    try:
        path.relative_to(REPO)
    except ValueError:
        # Explicit non-repository inputs own their immediate directory as the
        # read trust boundary.
        return path.parent
    return REPO


def _load_canonical(path: Path, label: str) -> tuple[bytes, dict]:
    path = Path(path)
    try:
        loaded, value = SafeIO.read_canonical_json(
            path, label=label, canonical_json_line=canonical_json_line,
            root=_safe_read_root(path),
        )
    except SafeIO.SafeReadError as err:
        if "not a regular file" in str(err) or "identity changed" in str(err):
            raise ProtocolError(
                "{} is not canonical regular JSON".format(label)
            ) from err
        raise ProtocolError("cannot load {}".format(label)) from err
    return loaded.raw, value


def _safe_repo_path(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ProtocolError("{} path is invalid".format(label))
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ProtocolError("{} path escapes the repository".format(label))
    path = REPO / relative
    try:
        path.resolve().relative_to(REPO.resolve())
    except (OSError, ValueError) as err:
        raise ProtocolError("{} path escapes the repository".format(label)) from err
    return path


def _pdb(mode: str) -> str:
    options = [
        "budget=100000",
        "pattern_selection={}".format(mode),
    ]
    if mode == "cegar":
        options.extend((
            "cegar_max_time=infinity",
            "cegar_max_refinements=128",
            "cegar_seed=2011",
        ))
    options.extend((
        "value_cap=-1",
        "gamer_ordering=false",
        "dynamic_reordering=false",
        "shadow_partition=true",
        'wbh_log="{}"'.format(Source.LEGACY_LOG),
        'wbh_profile_log="{}"'.format(Source.PROFILE_LOG),
    ))
    return "sym_fw_pdb({})".format(",".join(options))


CONFIGS = (
    ("pdb_bdd_prefix_shadow", _pdb("bdd_prefix")),
    ("pdb_goal_prefix_shadow", _pdb("goal_prefix")),
    ("pdb_goal_fill_shadow", _pdb("goal_fill")),
    ("pdb_cegar_shadow", _pdb("cegar")),
)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)


def option_matrix_digest(configs=CONFIGS) -> str:
    return hashlib.sha256(canonical_json([
        {"label": label, "search": search} for label, search in configs
    ])).hexdigest()


EXPERIMENT_SOURCE_FILES = (
    "experiments/analyze_pdb_terminal_incidence_confirmation_a.py",
    "experiments/analyze_pdb_terminal_incidence_shadow.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_a.py",
    "experiments/audit_pdb_terminal_incidence_shadow.py",
    "experiments/exp_pdb_profile_certificate_holdout.py",
    "experiments/exp_pdb_terminal_incidence_confirmation_a.py",
    "experiments/freeze_pdb_terminal_incidence_confirmation_a.py",
    "experiments/jj_cached_revision.py",
    "experiments/pdb_confirmation_safe_io.py",
    "experiments/pdb_confirmation_run_cell.py",
    "experiments/pdb_fixed_pattern_parser.py",
    "experiments/pdb_profile_certificate_holdout_protocol.md",
    "experiments/pdb_profile_certificate_holdout_protocol.py",
    "experiments/pdb_profile_comparison_parser.py",
    "experiments/pdb_profile_comparison_protocol.py",
    "experiments/pdb_profile_semantic_union_protocol.md",
    "experiments/pdb_profile_semantic_union_protocol.py",
    "experiments/pdb_terminal_incidence_confirmation_a_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_a_protocol.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v11.py",
    "experiments/pdb_terminal_incidence_confirmation_v11_adapter.py",
    "experiments/pdb_terminal_incidence_v11_snapshot_reader.py",
    "experiments/pdb_terminal_incidence_shadow_protocol.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_a.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/validate_wbh_log.py",
    "experiments/wbh_parser.py",
)


@dataclass(frozen=True, order=True)
class CohortTask:
    domain: str
    problem: str
    family: str
    domain_file: str
    problem_file: str
    domain_sha256: str
    problem_sha256: str
    is_shadow_unrepresented: bool
    is_all_prior_unrepresented: bool


@dataclass(frozen=True)
class SourceMaterials:
    source_audit: dict
    bindings: dict
    tasks: tuple[dict, ...]
    cohort_role: str
    candidate_indices_sha256: str
    source_projection_sha256: str
    directories: tuple[str, ...]
    directory_to_family: dict[str, str]
    shadow_unrepresented_families: tuple[str, ...]
    all_prior_unrepresented_families: tuple[str, ...]
    attestation_sha256: str
    execution_receipt_sha256: str
    launch_receipt_sha256: str
    records_sha256: str
    translator_source_sha256: str
    tracked_file_sha256: dict[str, str]

    @property
    def cohort_manifest_sha256(self) -> str:
        return self.source_projection_sha256


def _plain_v11(value):
    if is_dataclass(value):
        return {
            field.name: _plain_v11(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ProtocolError("V11 source mapping key is not text")
        return {key: _plain_v11(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_v11(item) for item in value]
    if value is None or type(value) in (bool, int, float, str):
        return value
    raise ProtocolError("V11 source value is not canonical JSON")


def _source_payload(authorized) -> dict:
    if type(authorized) is not SourceV11.AuthorizedV11Cohorts:
        raise ProtocolError("V11 adapter returned an unexpected result")
    return {
        "schema": FROZEN_SOURCE_SCHEMA,
        "source_seal_revision": authorized.bindings.seal_repository_commit_id,
        "bindings": _plain_v11(authorized.bindings),
        "confirmation_a": _plain_v11(authorized.confirmation_a),
    }


def _validate_native_task(task: dict) -> None:
    expected = set(SourceV11.SOURCE_PROJECTION_FIELDS)
    aliases = task.get("aliases") if isinstance(task, dict) else None
    text_fields = (
        "directory", "family", "problem", "domain_file", "problem_file",
        "canonical_path",
    )
    if (
        not isinstance(task, dict)
        or set(task) != expected
        or type(task.get("candidate_index")) is not int
        or not 0 <= task["candidate_index"] < 1640
        or any(type(task.get(key)) is not str or not task[key]
               for key in text_fields)
        or any(SHA256_RE.fullmatch(task.get(key, "")) is None
               for key in ("domain_sha256", "problem_sha256"))
        or any(type(task.get(key)) is not bool for key in (
            "is_shadow_family", "is_shadow_unrepresented",
            "is_all_prior_represented", "is_all_prior_unrepresented",
        ))
        or task.get("canonical_path") != task.get("problem_file")
    ):
        raise ProtocolError("frozen V11 source task changed")
    for key in ("domain_file", "problem_file"):
        path = Path(task[key])
        if path.is_absolute() or ".." in path.parts:
            raise ProtocolError("frozen V11 source path is unsafe")
    if (
        Path(task["problem_file"]) != Path(task["directory"]) / task["problem"]
        or Path(task["domain_file"]).parent != Path(task["directory"])
        or task["is_shadow_family"] == task["is_shadow_unrepresented"]
        or task["is_all_prior_represented"]
        == task["is_all_prior_unrepresented"]
        or task["is_shadow_family"]
        is not (task["family"] in SourceV11.SourceV11.SHADOW_FAMILIES)
        or task["is_all_prior_represented"]
        is not (task["family"] in SourceV11.SourceV11.ALL_PRIOR_FAMILIES)
    ):
        raise ProtocolError("frozen V11 source identity changed")
    alias_fields = set(SourceV11.ALIAS_FIELDS)
    canonical_alias = {key: task[key] for key in alias_fields}
    if (
        not isinstance(aliases, list)
        or not aliases
        or any(not isinstance(alias, dict) or set(alias) != alias_fields
               for alias in aliases)
        or aliases[0] != canonical_alias
    ):
        raise ProtocolError("frozen V11 source aliases changed")


def _validate_v11_bindings(bindings: dict, source_seal_revision: str) -> None:
    expected = {field.name for field in fields(SourceV11.V11SourceBindings)}
    if not isinstance(bindings, dict) or set(bindings) != expected:
        raise ProtocolError("frozen V11 binding shape changed")
    commits = (
        bindings.get("preflight_source_repository_commit_id"),
        bindings.get("preflight_seal_repository_commit_id"),
        bindings.get("seal_repository_commit_id"),
    )
    hash_fields = {
        key for key in expected
        if key.endswith("_sha256") or key.endswith("_sha256_digest")
    } - {
        "full_tracked_file_sha256", "preflight_tracked_file_sha256",
        "combined_tracked_file_sha256",
    }
    if (
        bindings.get("schema") != SourceV11.SCHEMA
        or bindings.get("campaign") != "v11-full-census"
        or bindings.get("benchmark_revision") != BENCHMARK_REVISION
        or bindings.get("preflight_campaign") != "v11-preflight"
        or bindings.get("preflight_full_launch_authorized") is not True
        or bindings.get("seal_repository_commit_id") != source_seal_revision
        or any(COMMIT_RE.fullmatch(value or "") is None for value in commits)
        or len(set(commits)) != 3
        or any(SHA256_RE.fullmatch(bindings.get(key, "")) is None
               for key in hash_fields)
        or bindings.get("code_manifest_sha256")
        != bindings.get("preflight_code_manifest_sha256")
        or bindings.get("all_records_count") != 1640
        or type(bindings.get("inventory_families_count")) is not int
        or not 1 <= bindings["inventory_families_count"] <= 1640
        or bindings.get("translation_attempts_count") != 1640
        or type(bindings.get("translation_attempts_count")) is not int
        or type(bindings.get("eligible_records_count")) is not int
        or not 0 <= bindings["eligible_records_count"] <= 1640
        or bindings.get("confirmation_a_count") != COHORT_TASKS
        or bindings.get("guided_b_count") != 300
    ):
        raise ProtocolError("frozen V11 authorization changed")
    for prefix in ("full", "preflight", "combined"):
        tracked = bindings.get(prefix + "_tracked_file_sha256")
        if (
            not isinstance(tracked, dict)
            or not tracked
            or any(type(path) is not str or not path
                   or SHA256_RE.fullmatch(digest or "") is None
                   for path, digest in tracked.items())
            or hashlib.sha256(canonical_json(tracked)).hexdigest()
            != bindings[prefix + "_tracked_file_sha256_digest"]
        ):
            raise ProtocolError("frozen V11 tracked closure changed")
    combined = dict(bindings["preflight_tracked_file_sha256"])
    for path, digest in bindings["full_tracked_file_sha256"].items():
        if path in combined and combined[path] != digest:
            raise ProtocolError("frozen V11 tracked closures disagree")
        combined[path] = digest
    if combined != bindings["combined_tracked_file_sha256"]:
        raise ProtocolError("frozen V11 combined tracked closure changed")
    summary_keys = {
        "outcome_counts": {"input-rejected", "resource-excluded", "success"},
        "support_status_counts": set(SourceV11.SUPPORT_STATUS_KEYS),
        "support_exclusion_counts": set(SourceV11.SUPPORT_EXCLUSION_REASONS),
        "resource_exclusion_counts": set(SourceV11.RESOURCE_EXCLUSION_KEYS),
    }
    for name, keys in summary_keys.items():
        value = bindings.get(name)
        if (
            not isinstance(value, dict)
            or set(value) != keys
            or any(type(value[key]) is not int or value[key] < 0 for key in keys)
            or hashlib.sha256(canonical_json(value)).hexdigest()
            != bindings[name + "_sha256"]
        ):
            raise ProtocolError("frozen V11 summary changed")
    resource_by_family = bindings.get("resource_exclusions_by_family")
    if (
        not isinstance(resource_by_family, dict)
        or len(resource_by_family) > bindings["inventory_families_count"]
        or any(
            type(family) is not str
            or not family
            or not isinstance(counts, dict)
            or set(counts) != {"memory", "time", "total"}
            or any(
                type(counts[key]) is not int or counts[key] < 0
                for key in ("memory", "time", "total")
            )
            or counts["total"] != counts["memory"] + counts["time"]
            or counts["total"] == 0
            for family, counts in resource_by_family.items()
        )
        or hashlib.sha256(canonical_json(resource_by_family)).hexdigest()
        != bindings["resource_exclusions_by_family_sha256"]
    ):
        raise ProtocolError("frozen V11 summary changed")
    outcome_counts = bindings["outcome_counts"]
    support_status_counts = bindings["support_status_counts"]
    support_exclusion_counts = bindings["support_exclusion_counts"]
    resource_exclusion_counts = bindings["resource_exclusion_counts"]
    unsupported_success = (
        support_status_counts["unsupported"]
        - outcome_counts["input-rejected"]
    )
    structural_counts = [
        support_exclusion_counts[reason]
        for reason in SourceV11.SUPPORT_EXCLUSION_REASONS[1:]
    ]
    aggregated_resource_counts = {
        key: sum(counts[key] for counts in resource_by_family.values())
        for key in SourceV11.RESOURCE_EXCLUSION_KEYS
    }
    if (
        sum(outcome_counts.values()) != bindings["all_records_count"]
        or sum(support_status_counts.values()) != bindings["all_records_count"]
        or support_status_counts["supported"]
        != bindings["eligible_records_count"]
        or support_status_counts["indeterminate"]
        != outcome_counts["resource-excluded"]
        or support_exclusion_counts["translation-input-rejected"]
        != outcome_counts["input-rejected"]
        or unsupported_success < 0
        or any(count > unsupported_success for count in structural_counts)
        or sum(structural_counts) < unsupported_success
        or sum(resource_exclusion_counts.values())
        != outcome_counts["resource-excluded"]
        or resource_exclusion_counts != aggregated_resource_counts
    ):
        raise ProtocolError("frozen V11 summary is incoherent")
    translator = [
        {"path": path, "sha256": digest}
        for path, digest in sorted(bindings["full_tracked_file_sha256"].items())
        if path.startswith("src/translate/") and path.endswith(".py")
    ]
    if (
        len(translator) != SourceV11.TRANSLATOR_FILE_COUNT
        or hashlib.sha256(canonical_json(translator)).hexdigest()
        != bindings["translator_source_sha256"]
    ):
        raise ProtocolError("frozen V11 translator closure changed")


def _materials_from_frozen_source(source: dict) -> SourceMaterials:
    if not isinstance(source, dict) or set(source) != {
        "schema", "source_seal_revision", "bindings", "confirmation_a",
    } or source.get("schema") != FROZEN_SOURCE_SCHEMA:
        raise ProtocolError("Confirmation A frozen source shape changed")
    revision = source.get("source_seal_revision")
    _validate_v11_bindings(source.get("bindings"), revision)
    bindings = source["bindings"]
    cohort = source.get("confirmation_a")
    if not isinstance(cohort, dict) or set(cohort) != {
        "role", "records", "candidate_indices_sha256",
        "source_projection_sha256",
    } or cohort.get("role") != "confirmation-a":
        raise ProtocolError("Confirmation A frozen cohort shape changed")
    tasks = cohort.get("records")
    if not isinstance(tasks, list) or len(tasks) != COHORT_TASKS:
        raise ProtocolError("Confirmation A frozen cohort cardinality changed")
    for task in tasks:
        _validate_native_task(task)
    indices = [task["candidate_index"] for task in tasks]
    identities = [(task["directory"], task["problem"]) for task in tasks]
    problem_hashes = [task["problem_sha256"] for task in tasks]
    if (
        len(set(indices)) != COHORT_TASKS
        or len(set(identities)) != COHORT_TASKS
        or len(set(problem_hashes)) != COHORT_TASKS
        or hashlib.sha256(canonical_json(indices)).hexdigest()
        != cohort["candidate_indices_sha256"]
        or hashlib.sha256(canonical_json(tasks)).hexdigest()
        != cohort["source_projection_sha256"]
        or cohort["candidate_indices_sha256"]
        != bindings["confirmation_a_candidate_indices_sha256"]
        or cohort["source_projection_sha256"]
        != bindings["confirmation_a_source_projection_sha256"]
    ):
        raise ProtocolError("Confirmation A frozen cohort hash changed")
    directory_to_family = {}
    for task in tasks:
        previous = directory_to_family.setdefault(task["directory"], task["family"])
        if previous != task["family"]:
            raise ProtocolError("Confirmation A directory maps to two families")
    shadow = sorted({task["family"] for task in tasks
                     if task["is_shadow_unrepresented"]})
    all_prior_tasks = [task for task in tasks
                       if task["is_all_prior_unrepresented"]]
    all_prior = sorted({task["family"] for task in all_prior_tasks})
    if (
        len(set(directory_to_family.values())) < MIN_SOURCE_COHORT_FAMILIES
        or len(shadow) < MIN_SOURCE_SHADOW_UNREPRESENTED_FAMILIES
        or len(all_prior_tasks) < MIN_SOURCE_ALL_PRIOR_UNREPRESENTED_TASKS
        or len(all_prior) < MIN_SOURCE_ALL_PRIOR_UNREPRESENTED_FAMILIES
    ):
        raise ProtocolError("Confirmation A frozen family floor changed")
    return SourceMaterials(
        source_audit=source, bindings=bindings, tasks=tuple(tasks),
        cohort_role=cohort["role"],
        candidate_indices_sha256=cohort["candidate_indices_sha256"],
        source_projection_sha256=cohort["source_projection_sha256"],
        directories=tuple(sorted(directory_to_family)),
        directory_to_family=dict(sorted(directory_to_family.items())),
        shadow_unrepresented_families=tuple(shadow),
        all_prior_unrepresented_families=tuple(all_prior),
        attestation_sha256=bindings["attestation_sha256"],
        execution_receipt_sha256=bindings["execution_receipt_sha256"],
        launch_receipt_sha256=bindings["launch_receipt_sha256"],
        records_sha256=bindings["all_records_sha256"],
        translator_source_sha256=bindings["translator_source_sha256"],
        tracked_file_sha256=bindings["combined_tracked_file_sha256"],
    )


def load_source_materials(source_seal_revision: str) -> SourceMaterials:
    """Load the authorized source projection from one immutable V11 seal."""
    if not isinstance(source_seal_revision, str):
        raise ProtocolError("V11 source seal revision is malformed")
    try:
        authorized = SourceV11.load_authorized_cohorts(source_seal_revision)
    except (
        SourceV11.V11AdapterError,
        SourceV11.SourceV11.SourceConsumerError,
    ) as err:
        raise ProtocolError(str(err)) from err
    source = _source_payload(authorized)
    if source["source_seal_revision"] != source_seal_revision:
        raise ProtocolError("V11 adapter returned the wrong seal revision")
    return _materials_from_frozen_source(source)


def _load_freeze(path: Path = FREEZE_PATH) -> tuple[dict, SourceMaterials]:
    _raw, freeze = _load_canonical(path, "Confirmation A freeze")
    if (
        set(freeze) != {
            "schema", "freeze_repository_revision", "source_audit",
            "planner", "design", "experiment_source_sha256",
        }
        or freeze.get("schema") != FREEZE_SCHEMA
        or COMMIT_RE.fullmatch(freeze.get("freeze_repository_revision", ""))
        is None
    ):
        raise ProtocolError("Confirmation A freeze schema changed")
    materials = _materials_from_frozen_source(freeze.get("source_audit"))
    expected_design = {
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "option_matrix_sha256": option_matrix_digest(),
        "cohort_tasks": COHORT_TASKS,
        "configs": CONFIG_COUNT,
        "cells": CELL_COUNT,
        "horizon": HORIZON,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
    }
    if freeze.get("design") != expected_design:
        raise ProtocolError("Confirmation A frozen design changed")
    planner = freeze.get("planner")
    required_planner = (
        "revision", "cache_name", "downward_sha256", "preprocess_sha256",
        "tree_manifest_sha256",
    )
    if (
        not isinstance(planner, dict)
        or set(planner) != set(required_planner) | {"build_options"}
        or planner.get("revision") != PLANNER_REVISION_REQUIRED
        or any(SHA256_RE.fullmatch(planner.get(field, "")) is None
               for field in required_planner[2:])
        or type(planner.get("cache_name")) is not str
        or not planner["cache_name"]
        or planner.get("build_options") != list(BUILD_OPTIONS)
    ):
        raise ProtocolError("Confirmation A planner pins are invalid")
    source_hashes = freeze.get("experiment_source_sha256")
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(
        EXPERIMENT_SOURCE_FILES
    ):
        raise ProtocolError("Confirmation A executed-source set changed")
    for relative, expected in source_hashes.items():
        if SHA256_RE.fullmatch(expected or "") is None:
            raise ProtocolError("Confirmation A source hash is invalid")
        if sha256_file(_safe_repo_path(relative, "experiment source")) != expected:
            raise ProtocolError("Confirmation A experiment source changed")
    return freeze, materials


def _unfrozen_defaults() -> dict:
    names = (
        "PROTOCOL_SHA256", "OPTION_MATRIX_SHA256", "PLANNER_REVISION",
        "FREEZE_REPOSITORY_REVISION", "PLANNER_CACHE_NAME",
        "PLANNER_BINARY_SHA256", "PREPROCESS_BINARY_SHA256",
        "PLANNER_TREE_MANIFEST_SHA256", "COHORT_MANIFEST_SHA256",
        "TASK_NAME_SHA256", "DIRECTORY_FAMILY_JSON_SHA256",
        "COST_ATTESTATION_SHA256", "COST_ATTESTATION_RECORDS_SHA256",
        "TRANSLATOR_SOURCE_SHA256", "SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256",
        "SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256",
        "SOURCE_AUDIT_CODE_MANIFEST_SHA256",
        "SOURCE_AUDIT_REPOSITORY_COMMIT_ID",
        "SOURCE_AUDIT_SOURCE_REPOSITORY_COMMIT_ID",
        "SOURCE_AUDIT_PREFLIGHT_SEAL_REPOSITORY_COMMIT_ID",
        "SOURCE_AUDIT_SEAL_REPOSITORY_COMMIT_ID",
        "SOURCE_AUDIT_INVENTORY_SHA256",
        "SOURCE_AUDIT_PREFLIGHT_AUTHORIZATION_SHA256",
        "SOURCE_AUDIT_CONTROLLER_CANARY_SHA256",
        "SOURCE_AUDIT_COMPUTE_CANARY_LAUNCH_SHA256",
        "SOURCE_AUDIT_COMPUTE_CANARY_TERMINAL_SHA256",
        "SOURCE_AUDIT_COMPUTE_CANARY_SEAL_SHA256",
        "SOURCE_AUDIT_COMPUTE_CANARY_ATTESTATION_SHA256",
        "SOURCE_AUDIT_FULL_TRACKED_CLOSURE_SHA256",
        "SOURCE_AUDIT_PREFLIGHT_TRACKED_CLOSURE_SHA256",
        "SOURCE_AUDIT_COMBINED_TRACKED_CLOSURE_SHA256",
        "SOURCE_AUDIT_ALL_RECORDS_SHA256",
        "SOURCE_AUDIT_CONFIRMATION_A_INDICES_SHA256",
        "SOURCE_AUDIT_CONFIRMATION_A_PROJECTION_SHA256",
        "SOURCE_AUDIT_GUIDED_B_INDICES_SHA256",
        "SOURCE_AUDIT_GUIDED_B_PROJECTION_SHA256",
    )
    return {
        **{name: "TO_FREEZE" for name in names},
        "COST_ATTESTATION_PATH": FREEZE_PATH.with_name("missing-attestation"),
        "DIRECTORIES": (), "DIRECTORY_TO_FAMILY": {},
        "COHORT_DIRECTORIES": 0, "COHORT_DOMAINS": 0, "COHORT_FAMILIES": 0,
        "SHADOW_UNREPRESENTED_FAMILIES": (),
        "ALL_PRIOR_UNREPRESENTED_FAMILIES": (),
    }


def _installed_values() -> dict:
    values = _unfrozen_defaults()
    if not FREEZE_PATH.exists():
        return values
    freeze, materials = _load_freeze(FREEZE_PATH)
    planner = freeze["planner"]
    bindings = materials.bindings
    task_payload = "".join(
        "{}:{}\n".format(task["directory"], task["problem"])
        for task in sorted(
            materials.tasks, key=lambda task: (task["directory"], task["problem"])
        )
    ).encode("utf-8")
    values.update({
        "PROTOCOL_SHA256": freeze["design"]["protocol_sha256"],
        "OPTION_MATRIX_SHA256": freeze["design"]["option_matrix_sha256"],
        "PLANNER_REVISION": planner["revision"],
        "FREEZE_REPOSITORY_REVISION": freeze["freeze_repository_revision"],
        "PLANNER_CACHE_NAME": planner["cache_name"],
        "PLANNER_BINARY_SHA256": planner["downward_sha256"],
        "PREPROCESS_BINARY_SHA256": planner["preprocess_sha256"],
        "PLANNER_TREE_MANIFEST_SHA256": planner["tree_manifest_sha256"],
        "COHORT_MANIFEST_SHA256": materials.source_projection_sha256,
        "TASK_NAME_SHA256": hashlib.sha256(task_payload).hexdigest(),
        "DIRECTORY_FAMILY_JSON_SHA256": hashlib.sha256(
            canonical_json(materials.directory_to_family)
        ).hexdigest(),
        "COST_ATTESTATION_SHA256": bindings["attestation_sha256"],
        "COST_ATTESTATION_RECORDS_SHA256": bindings["all_records_sha256"],
        "TRANSLATOR_SOURCE_SHA256": bindings["translator_source_sha256"],
        "SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256": bindings["launch_receipt_sha256"],
        "SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256": bindings[
            "execution_receipt_sha256"
        ],
        "SOURCE_AUDIT_CODE_MANIFEST_SHA256": bindings["code_manifest_sha256"],
        "SOURCE_AUDIT_REPOSITORY_COMMIT_ID": bindings[
            "seal_repository_commit_id"
        ],
        "SOURCE_AUDIT_SOURCE_REPOSITORY_COMMIT_ID": bindings[
            "preflight_source_repository_commit_id"
        ],
        "SOURCE_AUDIT_PREFLIGHT_SEAL_REPOSITORY_COMMIT_ID": bindings[
            "preflight_seal_repository_commit_id"
        ],
        "SOURCE_AUDIT_SEAL_REPOSITORY_COMMIT_ID": bindings[
            "seal_repository_commit_id"
        ],
        "SOURCE_AUDIT_INVENTORY_SHA256": bindings["source_inventory_sha256"],
        "SOURCE_AUDIT_PREFLIGHT_AUTHORIZATION_SHA256": bindings[
            "preflight_authorization_sha256"
        ],
        "SOURCE_AUDIT_CONTROLLER_CANARY_SHA256": bindings[
            "controller_publisher_canary_receipt_sha256"
        ],
        "SOURCE_AUDIT_COMPUTE_CANARY_LAUNCH_SHA256": bindings[
            "compute_canary_launch_receipt_sha256"
        ],
        "SOURCE_AUDIT_COMPUTE_CANARY_TERMINAL_SHA256": bindings[
            "compute_canary_terminal_poll_receipt_sha256"
        ],
        "SOURCE_AUDIT_COMPUTE_CANARY_SEAL_SHA256": bindings[
            "compute_canary_seal_plan_sha256"
        ],
        "SOURCE_AUDIT_COMPUTE_CANARY_ATTESTATION_SHA256": bindings[
            "compute_canary_attestation_sha256"
        ],
        "SOURCE_AUDIT_FULL_TRACKED_CLOSURE_SHA256": bindings[
            "full_tracked_file_sha256_digest"
        ],
        "SOURCE_AUDIT_PREFLIGHT_TRACKED_CLOSURE_SHA256": bindings[
            "preflight_tracked_file_sha256_digest"
        ],
        "SOURCE_AUDIT_COMBINED_TRACKED_CLOSURE_SHA256": bindings[
            "combined_tracked_file_sha256_digest"
        ],
        "SOURCE_AUDIT_ALL_RECORDS_SHA256": bindings["all_records_sha256"],
        "SOURCE_AUDIT_CONFIRMATION_A_INDICES_SHA256": materials.candidate_indices_sha256,
        "SOURCE_AUDIT_CONFIRMATION_A_PROJECTION_SHA256": materials.source_projection_sha256,
        "SOURCE_AUDIT_GUIDED_B_INDICES_SHA256": bindings[
            "guided_b_candidate_indices_sha256"
        ],
        "SOURCE_AUDIT_GUIDED_B_PROJECTION_SHA256": bindings[
            "guided_b_source_projection_sha256"
        ],
        "DIRECTORIES": materials.directories,
        "DIRECTORY_TO_FAMILY": materials.directory_to_family,
        "COHORT_DIRECTORIES": len(materials.directories),
        "COHORT_DOMAINS": len(materials.directories),
        "COHORT_FAMILIES": len(set(materials.directory_to_family.values())),
        "SHADOW_UNREPRESENTED_FAMILIES": materials.shadow_unrepresented_families,
        "ALL_PRIOR_UNREPRESENTED_FAMILIES": (
            materials.all_prior_unrepresented_families
        ),
    })
    return values


globals().update(_installed_values())


def v11_run_provenance() -> dict:
    """Return the one canonical V11 provenance projection for every A cell."""
    if not FREEZE_PATH.exists():
        raise ProtocolError("Confirmation A freeze is not installed")
    return {
        "source_audit_campaign": "v11-full-census",
        "source_audit_launch_receipt_sha256": (
            SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256
        ),
        "source_audit_execution_receipt_sha256": (
            SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256
        ),
        "source_audit_code_manifest_sha256": (
            SOURCE_AUDIT_CODE_MANIFEST_SHA256
        ),
        "source_audit_repository_commit_id": (
            SOURCE_AUDIT_REPOSITORY_COMMIT_ID
        ),
        "source_audit_source_repository_commit_id": (
            SOURCE_AUDIT_SOURCE_REPOSITORY_COMMIT_ID
        ),
        "source_audit_preflight_seal_repository_commit_id": (
            SOURCE_AUDIT_PREFLIGHT_SEAL_REPOSITORY_COMMIT_ID
        ),
        "source_audit_seal_repository_commit_id": (
            SOURCE_AUDIT_SEAL_REPOSITORY_COMMIT_ID
        ),
        "source_audit_inventory_sha256": SOURCE_AUDIT_INVENTORY_SHA256,
        "source_audit_preflight_authorization_sha256": (
            SOURCE_AUDIT_PREFLIGHT_AUTHORIZATION_SHA256
        ),
        "source_audit_controller_canary_sha256": (
            SOURCE_AUDIT_CONTROLLER_CANARY_SHA256
        ),
        "source_audit_compute_canary_launch_sha256": (
            SOURCE_AUDIT_COMPUTE_CANARY_LAUNCH_SHA256
        ),
        "source_audit_compute_canary_terminal_poll_receipt_sha256": (
            SOURCE_AUDIT_COMPUTE_CANARY_TERMINAL_SHA256
        ),
        "source_audit_compute_canary_seal_sha256": (
            SOURCE_AUDIT_COMPUTE_CANARY_SEAL_SHA256
        ),
        "source_audit_compute_canary_attestation_sha256": (
            SOURCE_AUDIT_COMPUTE_CANARY_ATTESTATION_SHA256
        ),
        "source_audit_full_tracked_closure_sha256": (
            SOURCE_AUDIT_FULL_TRACKED_CLOSURE_SHA256
        ),
        "source_audit_preflight_tracked_closure_sha256": (
            SOURCE_AUDIT_PREFLIGHT_TRACKED_CLOSURE_SHA256
        ),
        "source_audit_combined_tracked_closure_sha256": (
            SOURCE_AUDIT_COMBINED_TRACKED_CLOSURE_SHA256
        ),
        "source_audit_all_records_sha256": SOURCE_AUDIT_ALL_RECORDS_SHA256,
        "source_audit_confirmation_a_indices_sha256": (
            SOURCE_AUDIT_CONFIRMATION_A_INDICES_SHA256
        ),
        "source_audit_confirmation_a_projection_sha256": (
            SOURCE_AUDIT_CONFIRMATION_A_PROJECTION_SHA256
        ),
        "source_audit_guided_b_indices_sha256": (
            SOURCE_AUDIT_GUIDED_B_INDICES_SHA256
        ),
        "source_audit_guided_b_projection_sha256": (
            SOURCE_AUDIT_GUIDED_B_PROJECTION_SHA256
        ),
        "confirmation_a_freeze_sha256": sha256_file(FREEZE_PATH),
    }


def load_cohort(benchmarks, *, validate_costs=True):
    del validate_costs
    _, materials = _load_freeze(FREEZE_PATH)
    root = Path(benchmarks).resolve()
    if _repository_revision(root) != BENCHMARK_REVISION:
        raise ProtocolError("benchmark root is not the frozen revision")
    tasks = tuple(CohortTask(
        domain=record["directory"],
        problem=record["problem"],
        family=record["family"],
        domain_file=record["domain_file"],
        problem_file=record["problem_file"],
        domain_sha256=record["domain_sha256"],
        problem_sha256=record["problem_sha256"],
        is_shadow_unrepresented=record["is_shadow_unrepresented"],
        is_all_prior_unrepresented=record["is_all_prior_unrepresented"],
    ) for record in materials.tasks)
    validate_benchmark_sources(tasks, root)
    return tasks


def _repository_revision(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise ProtocolError("cannot resolve benchmark repository revision") from err
    return result.stdout.strip()


def validate_benchmark_sources(cohort, benchmarks) -> None:
    root = Path(benchmarks).resolve()
    seen = set()
    for task in cohort:
        identity = (task.domain, task.problem)
        if identity in seen:
            raise ProtocolError("cohort task identity is duplicated")
        seen.add(identity)
        for relative, expected in (
            (task.domain_file, task.domain_sha256),
            (task.problem_file, task.problem_sha256),
        ):
            path = root / relative
            try:
                path.resolve().relative_to(root)
            except (OSError, ValueError) as err:
                raise ProtocolError("benchmark source escapes the root") from err
            if sha256_file(path) != expected:
                raise ProtocolError("benchmark source bytes changed")
    if len(seen) != COHORT_TASKS:
        raise ProtocolError("cohort cardinality changed")


def validate_protocol_design() -> None:
    if any((
        LABELS != PRIMARY_LABELS,
        len(set(LABELS)) != CONFIG_COUNT,
        COHORT_TASKS != 650,
        CELL_COUNT != 2600,
        RUNS_PER_ARRAY_TASK != 3,
        EXPECTED_ARRAY_TASKS != 867,
        (EXPECTED_ARRAY_TASKS - 1) * RUNS_PER_ARRAY_TASK >= CELL_COUNT,
        EXPECTED_ARRAY_TASKS * RUNS_PER_ARRAY_TASK < CELL_COUNT,
        TIME_LIMIT_SECONDS != 1800,
        MEMORY_LIMIT_MIB != 24576,
        SCHEDULER_TIME_LIMIT != "01:40:00",
        SCHEDULER_MEMORY != "26G",
        HORIZON != 16,
        MIN_ELIGIBLE_TASKS != 300,
        MIN_ELIGIBLE_FAMILIES != 25,
        MIN_COMPARISON_TASKS != 300,
        MIN_COMPARISON_FAMILIES != 25,
        MIN_TARGET_STRICT_PAIRS != 600,
        MIN_PRIMARY_CONCORDANCE_NUMERATOR != 13,
        MIN_PRIMARY_CONCORDANCE_DENOMINATOR != 20,
        MIN_ADVANTAGE_NUMERATOR != 1,
        MIN_ADVANTAGE_DENOMINATOR != 50,
        BOOTSTRAP_REPLICATES != 100000,
        BOOTSTRAP_SEED != 20260901,
        ACTIVE_VALUE_COUNT_DIAGNOSTIC != "value_count",
        MEET_CERTIFICATE != "meet",
        CERTIFICATE_BASELINES
        != ("kD", "mQ", "mJ", "Cartesian", "width", "ADD", "meet"),
        PREDICTORS
        != ("I", "D", "value_count", "kD", "mQ", "mJ", "Cartesian",
            "width", "ADD", "meet"),
        MIN_NEW_STRATUM_COMPARISON_TASKS != 50,
        MIN_NEW_STRATUM_COMPARISON_FAMILIES != 10,
        MIN_NEW_STRATUM_TARGET_STRICT_PAIRS != 100,
        MIN_NEW_STRATUM_CONCORDANCE_NUMERATOR != 13,
        MIN_NEW_STRATUM_CONCORDANCE_DENOMINATOR != 20,
        MIN_NEW_STRATUM_ADVANTAGE_NUMERATOR != 1,
        MIN_NEW_STRATUM_ADVANTAGE_DENOMINATOR != 50,
        ACCOUNT != "naiss2025-5-561-cpu",
        PLANNER_REVISION_REQUIRED
        != "8148f798f13059ee881ad2471bd20cdd61d2ec18",
    )):
        raise ProtocolError("Confirmation A design constants changed")
    modes = dict(zip(LABELS, ("bdd_prefix", "goal_prefix", "goal_fill", "cegar")))
    for label, search in CONFIGS:
        required = (
            "budget=100000",
            "pattern_selection={}".format(modes[label]),
            "value_cap=-1",
            "gamer_ordering=false",
            "dynamic_reordering=false",
            "shadow_partition=true",
        )
        if any(search.count(item) != 1 for item in required):
            raise ProtocolError("configuration contract changed for {}".format(label))
        cegar_only = (
            "cegar_max_time=infinity",
            "cegar_max_refinements=128",
            "cegar_seed=2011",
        )
        if label == "pdb_cegar_shadow":
            if any(search.count(item) != 1 for item in cegar_only):
                raise ProtocolError("CEGAR stopping contract changed")
        elif any(item in search for item in cegar_only):
            raise ProtocolError("non-CEGAR configuration gained CEGAR options")


def validate_protocol_without_sources() -> None:
    validate_protocol_design()
    _load_freeze(FREEZE_PATH)


validate_protocol_without_archive = validate_protocol_without_sources


if __name__ == "__main__":
    validate_protocol_without_sources()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            COHORT_TASKS, CONFIG_COUNT, CELL_COUNT
        )
    )
