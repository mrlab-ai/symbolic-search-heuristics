#!/usr/bin/env python3
"""Frozen protocol and source loader for terminal-incidence Confirmation A."""

from __future__ import annotations

import hashlib
import json
import re
import stat
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdb_profile_comparison_protocol as Source


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
SOURCE_AUDIT_SCHEMA = (
    "symbolic-search-heuristics/"
    "universal-unseen-confirmation-source-audit/v1"
)
PROTOCOL = "pdb-terminal-incidence-confirmation-a-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-terminal-incidence-confirmation-a-analysis-v1"
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

COHORT_TASKS = 650
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
MIN_SHARED_STRICT_PAIRS = 600
MIN_PRIMARY_CONCORDANCE_NUMERATOR = 13
MIN_PRIMARY_CONCORDANCE_DENOMINATOR = 20
MIN_ADVANTAGE_NUMERATOR = 1
MIN_ADVANTAGE_DENOMINATOR = 50
BOOTSTRAP_REPLICATES = 100000
BOOTSTRAP_SEED = 20260901

MIN_NEW_STRATUM_COMPARISON_FAMILIES = 10
MIN_NEW_STRATUM_SHARED_STRICT_PAIRS = 100
MIN_NEW_STRATUM_CONCORDANCE_NUMERATOR = 13
MIN_NEW_STRATUM_CONCORDANCE_DENOMINATOR = 20

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
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as err:
        raise ProtocolError("cannot inspect {}".format(path)) from err
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise ProtocolError("{} is not a regular file".format(path))
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as err:
        raise ProtocolError("cannot hash {}".format(path)) from err
    return digest.hexdigest()


def _load_canonical(path: Path, label: str) -> tuple[bytes, dict]:
    path = Path(path)
    try:
        info = path.lstat()
        raw = path.read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ProtocolError("cannot load {}".format(label)) from err
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or not isinstance(value, dict)
        or raw != canonical_json_line(value)
    ):
        raise ProtocolError("{} is not canonical regular JSON".format(label))
    return raw, value


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
    "experiments/pdb_fixed_pattern_parser.py",
    "experiments/pdb_profile_certificate_holdout_protocol.md",
    "experiments/pdb_profile_certificate_holdout_protocol.py",
    "experiments/pdb_profile_comparison_parser.py",
    "experiments/pdb_profile_comparison_protocol.py",
    "experiments/pdb_profile_semantic_union_protocol.md",
    "experiments/pdb_profile_semantic_union_protocol.py",
    "experiments/pdb_terminal_incidence_confirmation_a_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_a_protocol.py",
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
    attestation_path: Path
    execution_receipt_path: Path
    launch_receipt_path: Path
    attestation_sha256: str
    execution_receipt_sha256: str
    launch_receipt_sha256: str
    cohort_manifest_sha256: str
    records_sha256: str
    translator_source_sha256: str
    tasks: tuple[dict, ...]
    directories: tuple[str, ...]
    directory_to_family: dict[str, str]
    shadow_unrepresented_families: tuple[str, ...]
    all_prior_unrepresented_families: tuple[str, ...]
    execution_receipt: dict
    launch_receipt: dict


def _validate_task(task: dict) -> None:
    required_strings = (
        "directory", "family", "problem", "domain_file", "problem_file",
        "domain_sha256", "problem_sha256", "selection_role",
        "selection_rank_sha256", "source_audit_evidence_sha256",
    )
    if not isinstance(task, dict) or any(
        not isinstance(task.get(field), str) or not task[field]
        for field in required_strings
    ):
        raise ProtocolError("confirmation task record is malformed")
    if any(
        SHA256_RE.fullmatch(task[field]) is None
        for field in (
            "domain_sha256", "problem_sha256", "selection_rank_sha256",
            "source_audit_evidence_sha256",
        )
    ):
        raise ProtocolError("confirmation task hash is malformed")
    for field in ("domain_file", "problem_file"):
        path = Path(task[field])
        if path.is_absolute() or ".." in path.parts:
            raise ProtocolError("confirmation source path is unsafe")
    if task["selection_role"] != "confirmation-a":
        raise ProtocolError("confirmation task has the wrong split role")
    if any(
        type(task.get(field)) is not bool
        for field in (
            "is_shadow_unrepresented", "is_all_prior_represented",
            "is_all_prior_unrepresented", "is_shadow_family",
        )
    ):
        raise ProtocolError("confirmation task stratum flag is malformed")
    if task["is_all_prior_represented"] == task["is_all_prior_unrepresented"]:
        raise ProtocolError("all-prior stratum flags are inconsistent")


def load_source_materials(
    attestation_path: Path,
    execution_receipt_path: Path,
    launch_receipt_path: Path,
) -> SourceMaterials:
    attestation_path = Path(attestation_path).resolve()
    execution_receipt_path = Path(execution_receipt_path).resolve()
    launch_receipt_path = Path(launch_receipt_path).resolve()
    attestation_raw, attestation = _load_canonical(
        attestation_path, "source attestation"
    )
    execution_raw, execution = _load_canonical(
        execution_receipt_path, "source execution receipt"
    )
    launch_raw, launch = _load_canonical(
        launch_receipt_path, "source launch receipt"
    )
    attestation_sha = hashlib.sha256(attestation_raw).hexdigest()
    execution_sha = hashlib.sha256(execution_raw).hexdigest()
    launch_sha = hashlib.sha256(launch_raw).hexdigest()
    schema = attestation.get("schema")
    if (
        schema != SOURCE_AUDIT_SCHEMA
        or execution.get("schema") != schema + "/campaign-v2/execution"
        or launch.get("schema") != schema + "/campaign-v2/launch"
    ):
        raise ProtocolError("source-audit schema chain changed")
    if any((
        attestation.get("benchmark_revision") != BENCHMARK_REVISION,
        launch.get("benchmark_revision") != BENCHMARK_REVISION,
        launch.get("campaign") != "v2",
        execution.get("campaign") != "v2",
        launch.get("whole_campaign_rerun") is not True,
        execution.get("whole_campaign_rerun") is not True,
        launch.get("reused_v1_shards") != 0,
        execution.get("reused_v1_shards") != 0,
        launch.get("memory_per_cpu") != "256G",
        execution.get("memory_per_cpu") != "256G",
        execution.get("launch_receipt_sha256") != launch_sha,
        execution.get("attestation_sha256") != attestation_sha,
        execution.get("source_audit_complete") is not True,
        execution.get("confirmation_prelaunch_authorized") is not True,
        attestation.get("confirmation_prelaunch_authorized") is not True,
        execution.get("prelaunch_gate", {}).get("passed") is not True,
        attestation.get("prelaunch_gate", {}).get("passed") is not True,
        execution.get("prelaunch_gate") != attestation.get("prelaunch_gate"),
    )):
        raise ProtocolError("source audit did not authorize Confirmation A")
    expected_launch_scheduler = {
        "partition": "fat",
        "qos": "normal",
        "account": ACCOUNT,
        "array": "0-819",
        "array_throttle": 0,
        "array_tasks": 820,
        "tasks_per_array_task": 2,
        "candidates": 1640,
        "cpus_per_task": 1,
        "time_limit": "01:40:00",
        "memory_per_cpu": "256G",
        "task_timeout_seconds": 2700,
    }
    expected_execution_scheduler = {
        "partition": "fat",
        "memory_per_cpu": "256G",
        "array_throttle": 0,
        "shards": 820,
        "candidates": 1640,
    }
    if any(
        launch.get(field) != expected
        for field, expected in expected_launch_scheduler.items()
    ) or any(
        execution.get(field) != expected
        for field, expected in expected_execution_scheduler.items()
    ):
        raise ProtocolError("source-audit v2 scheduler contract changed")
    scheduler_rows = execution.get("scheduler_rows")
    if (
        not isinstance(scheduler_rows, list)
        or len(scheduler_rows) != 820
        or any(
            not isinstance(row, dict)
            or set(row) != {
                "array_task", "state", "exit_code", "elapsed", "partition",
            }
            or row.get("array_task") != index
            or row.get("partition") != "fat"
            or any(
                not isinstance(row.get(field), str) or not row[field]
                for field in ("state", "exit_code", "elapsed")
            )
            for index, row in enumerate(scheduler_rows)
        )
        or execution.get("scheduler_state_counts")
        != dict(Counter(row["state"] for row in scheduler_rows))
    ):
        raise ProtocolError("source-audit v2 scheduler rows changed")

    source_inventory_sha = attestation.get("source_inventory_sha256")
    code_manifest_sha = attestation.get("code_manifest_sha256")
    records_sha = attestation.get("records_sha256")
    union_tree = execution.get("union_tree")
    if any((
        SHA256_RE.fullmatch(source_inventory_sha or "") is None,
        SHA256_RE.fullmatch(code_manifest_sha or "") is None,
        SHA256_RE.fullmatch(records_sha or "") is None,
        launch.get("source_inventory_sha256") != source_inventory_sha,
        execution.get("source_inventory_sha256") != source_inventory_sha,
        launch.get("code_manifest_sha256") != code_manifest_sha,
        execution.get("code_manifest_sha256") != code_manifest_sha,
        launch.get("translator_source_sha256")
        != attestation.get("translator_source_sha256"),
        execution.get("job_id") != launch.get("job_id"),
        COMMIT_RE.fullmatch(launch.get("repository_commit_id", "")) is None,
        SHA256_RE.fullmatch(launch.get("slurm_script_sha256", "")) is None,
        SHA256_RE.fullmatch(launch.get("launch_intent_sha256", "")) is None,
        not isinstance(union_tree, dict),
        SHA256_RE.fullmatch(
            union_tree.get("sha256", "") if isinstance(union_tree, dict) else ""
        ) is None,
    )):
        raise ProtocolError("source-audit provenance chain changed")
    diagnostic = launch.get("v1_failure_diagnostic")
    if (
        not isinstance(diagnostic, dict)
        or execution.get("v1_failure_diagnostic") != diagnostic
        or diagnostic.get("schema")
        != schema + "/campaign-v2/v1-infrastructure-diagnostic"
        or diagnostic.get("rerun_scope") != "all-820-shards"
        or diagnostic.get("reused_v1_shards") != 0
        or diagnostic.get("successful_shard_contents_used_for_v2_design")
        is not False
        or diagnostic.get("source_support_outcomes_used_for_v2_design")
        is not False
    ):
        raise ProtocolError("source-audit v1 failure diagnostic chain changed")
    cohort = attestation.get("cohorts", {}).get("confirmation_a")
    tasks = cohort.get("tasks") if isinstance(cohort, dict) else None
    if (
        not isinstance(tasks, list)
        or len(tasks) != COHORT_TASKS
        or cohort.get("role") != "confirmation-a"
    ):
        raise ProtocolError("source audit has the wrong Confirmation A cohort")
    for task in tasks:
        _validate_task(task)
    cohort_sha = hashlib.sha256(canonical_json_line(tasks)).hexdigest()
    if any((
        cohort.get("tasks_sha256") != cohort_sha,
        execution.get("cohort_manifest_sha256", {}).get("confirmation_a")
        != cohort_sha,
        execution.get("attestation_records_sha256")
        != attestation.get("records_sha256"),
    )):
        raise ProtocolError("source-audit cohort hash chain changed")
    identities = [(task["directory"], task["problem"]) for task in tasks]
    problem_hashes = [task["problem_sha256"] for task in tasks]
    if len(set(identities)) != COHORT_TASKS or len(set(problem_hashes)) != COHORT_TASKS:
        raise ProtocolError("Confirmation A contains duplicate sources")
    directory_to_family = {}
    for task in tasks:
        previous = directory_to_family.setdefault(task["directory"], task["family"])
        if previous != task["family"]:
            raise ProtocolError("source audit maps one directory to two families")
    split_strata = attestation.get("split_strata")
    if not isinstance(split_strata, dict):
        raise ProtocolError("source audit lacks frozen strata")
    shadow = split_strata.get("shadow_unrepresented", {}).get("families")
    all_prior = split_strata.get("all_prior_unrepresented", {}).get("families")
    if any(
        not isinstance(values, list)
        or values != sorted(set(values))
        or any(not isinstance(value, str) or not value for value in values)
        for values in (shadow, all_prior)
    ):
        raise ProtocolError("source-audit stratum family set changed")
    shadow_set = set(shadow)
    all_prior_set = set(all_prior)
    for task in tasks:
        if (
            task["is_shadow_unrepresented"]
            != (task["family"] in shadow_set)
            or task["is_all_prior_unrepresented"]
            != (task["family"] in all_prior_set)
        ):
            raise ProtocolError("source-audit task stratum flag changed")
    translator_sha = attestation.get("translator_source_sha256")
    if SHA256_RE.fullmatch(translator_sha or "") is None:
        raise ProtocolError("translator source hash is invalid")
    if not isinstance(launch.get("job_id"), str) or not launch["job_id"].isdigit():
        raise ProtocolError("source launch job ID is invalid")
    return SourceMaterials(
        attestation_path=attestation_path,
        execution_receipt_path=execution_receipt_path,
        launch_receipt_path=launch_receipt_path,
        attestation_sha256=attestation_sha,
        execution_receipt_sha256=execution_sha,
        launch_receipt_sha256=launch_sha,
        cohort_manifest_sha256=cohort_sha,
        records_sha256=records_sha,
        translator_source_sha256=translator_sha,
        tasks=tuple(tasks),
        directories=tuple(sorted(directory_to_family)),
        directory_to_family=dict(sorted(directory_to_family.items())),
        shadow_unrepresented_families=tuple(shadow),
        all_prior_unrepresented_families=tuple(all_prior),
        execution_receipt=execution,
        launch_receipt=launch,
    )


def _load_freeze(path: Path = FREEZE_PATH) -> tuple[dict, SourceMaterials]:
    raw, freeze = _load_canonical(path, "Confirmation A freeze")
    if freeze.get("schema") != FREEZE_SCHEMA:
        raise ProtocolError("Confirmation A freeze schema changed")
    sources = freeze.get("source_audit")
    planner = freeze.get("planner")
    design = freeze.get("design")
    source_hashes = freeze.get("experiment_source_sha256")
    if not all(isinstance(value, dict) for value in (
        sources, planner, design, source_hashes
    )):
        raise ProtocolError("Confirmation A freeze is incomplete")
    attestation_path = _safe_repo_path(sources.get("attestation_path"), "attestation")
    execution_path = _safe_repo_path(
        sources.get("execution_receipt_path"), "source execution receipt"
    )
    launch_path = _safe_repo_path(
        sources.get("launch_receipt_path"), "source launch receipt"
    )
    materials = load_source_materials(attestation_path, execution_path, launch_path)
    expected_sources = {
        "attestation_sha256": materials.attestation_sha256,
        "execution_receipt_sha256": materials.execution_receipt_sha256,
        "launch_receipt_sha256": materials.launch_receipt_sha256,
        "cohort_manifest_sha256": materials.cohort_manifest_sha256,
        "attestation_records_sha256": materials.records_sha256,
        "translator_source_sha256": materials.translator_source_sha256,
    }
    if any(sources.get(key) != value for key, value in expected_sources.items()):
        raise ProtocolError("Confirmation A freeze source hashes changed")
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
    if design != expected_design:
        raise ProtocolError("Confirmation A frozen design changed")
    required_planner = (
        "revision", "cache_name", "downward_sha256", "preprocess_sha256",
        "tree_manifest_sha256",
    )
    if (
        COMMIT_RE.fullmatch(planner.get("revision", "")) is None
        or any(SHA256_RE.fullmatch(planner.get(field, "")) is None
               for field in required_planner[2:])
        or not isinstance(planner.get("cache_name"), str)
        or not planner["cache_name"]
        or planner.get("build_options") != list(BUILD_OPTIONS)
    ):
        raise ProtocolError("Confirmation A planner pins are invalid")
    if set(source_hashes) != set(EXPERIMENT_SOURCE_FILES):
        raise ProtocolError("Confirmation A executed-source set changed")
    for relative, expected in source_hashes.items():
        if SHA256_RE.fullmatch(expected or "") is None:
            raise ProtocolError("Confirmation A source hash is invalid")
        path = _safe_repo_path(relative, "experiment source")
        if sha256_file(path) != expected:
            raise ProtocolError("Confirmation A experiment source changed")
    return freeze, materials


def _unfrozen_defaults() -> dict:
    return {
        "PROTOCOL_SHA256": "TO_FREEZE",
        "OPTION_MATRIX_SHA256": "TO_FREEZE",
        "PLANNER_REVISION": "TO_FREEZE",
        "PLANNER_CACHE_NAME": "TO_FREEZE",
        "PLANNER_BINARY_SHA256": "TO_FREEZE",
        "PREPROCESS_BINARY_SHA256": "TO_FREEZE",
        "PLANNER_TREE_MANIFEST_SHA256": "TO_FREEZE",
        "COHORT_MANIFEST_SHA256": "TO_FREEZE",
        "TASK_NAME_SHA256": "TO_FREEZE",
        "DIRECTORY_FAMILY_JSON_SHA256": "TO_FREEZE",
        "COST_ATTESTATION_SHA256": "TO_FREEZE",
        "COST_ATTESTATION_RECORDS_SHA256": "TO_FREEZE",
        "TRANSLATOR_SOURCE_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_JOB_ID": "TO_FREEZE",
        "SOURCE_AUDIT_CODE_MANIFEST_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_REPOSITORY_COMMIT_ID": "TO_FREEZE",
        "SOURCE_AUDIT_OUTPUT_TREE_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_SLURM_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_INTENT_SHA256": "TO_FREEZE",
        "COST_ATTESTATION_PATH": FREEZE_PATH.with_name("missing-attestation"),
        "DIRECTORIES": (),
        "DIRECTORY_TO_FAMILY": {},
        "COHORT_DIRECTORIES": 0,
        "COHORT_DOMAINS": 0,
        "COHORT_FAMILIES": 0,
        "SHADOW_UNREPRESENTED_FAMILIES": (),
        "ALL_PRIOR_UNREPRESENTED_FAMILIES": (),
    }


def _installed_values() -> dict:
    defaults = _unfrozen_defaults()
    if not FREEZE_PATH.exists():
        return defaults
    freeze, materials = _load_freeze(FREEZE_PATH)
    planner = freeze["planner"]
    source = freeze["source_audit"]
    launch = materials.launch_receipt
    execution = materials.execution_receipt
    task_payload = "".join(
        "{}:{}\n".format(task["directory"], task["problem"])
        for task in sorted(
            materials.tasks, key=lambda task: (task["directory"], task["problem"])
        )
    ).encode("utf-8")
    values = {
        "PROTOCOL_SHA256": freeze["design"]["protocol_sha256"],
        "OPTION_MATRIX_SHA256": freeze["design"]["option_matrix_sha256"],
        "PLANNER_REVISION": planner["revision"],
        "PLANNER_CACHE_NAME": planner["cache_name"],
        "PLANNER_BINARY_SHA256": planner["downward_sha256"],
        "PREPROCESS_BINARY_SHA256": planner["preprocess_sha256"],
        "PLANNER_TREE_MANIFEST_SHA256": planner["tree_manifest_sha256"],
        "COHORT_MANIFEST_SHA256": materials.cohort_manifest_sha256,
        "TASK_NAME_SHA256": hashlib.sha256(task_payload).hexdigest(),
        "DIRECTORY_FAMILY_JSON_SHA256": hashlib.sha256(
            canonical_json(materials.directory_to_family)
        ).hexdigest(),
        "COST_ATTESTATION_SHA256": materials.attestation_sha256,
        "COST_ATTESTATION_RECORDS_SHA256": materials.records_sha256,
        "TRANSLATOR_SOURCE_SHA256": materials.translator_source_sha256,
        "SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256": materials.launch_receipt_sha256,
        "SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256": materials.execution_receipt_sha256,
        "SOURCE_AUDIT_JOB_ID": launch["job_id"],
        "SOURCE_AUDIT_CODE_MANIFEST_SHA256": execution["code_manifest_sha256"],
        "SOURCE_AUDIT_REPOSITORY_COMMIT_ID": launch["repository_commit_id"],
        "SOURCE_AUDIT_OUTPUT_TREE_SHA256": execution["union_tree"]["sha256"],
        "SOURCE_AUDIT_SLURM_SHA256": launch["slurm_script_sha256"],
        "SOURCE_AUDIT_INTENT_SHA256": launch["launch_intent_sha256"],
        "COST_ATTESTATION_PATH": materials.attestation_path,
        "DIRECTORIES": materials.directories,
        "DIRECTORY_TO_FAMILY": materials.directory_to_family,
        "COHORT_DIRECTORIES": len(materials.directories),
        "COHORT_DOMAINS": len(materials.directories),
        "COHORT_FAMILIES": len(set(materials.directory_to_family.values())),
        "SHADOW_UNREPRESENTED_FAMILIES": materials.shadow_unrepresented_families,
        "ALL_PRIOR_UNREPRESENTED_FAMILIES": materials.all_prior_unrepresented_families,
    }
    return values


globals().update(_installed_values())


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
        BOOTSTRAP_REPLICATES != 100000,
        BOOTSTRAP_SEED != 20260901,
        ACCOUNT != "naiss2025-5-561-cpu",
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
