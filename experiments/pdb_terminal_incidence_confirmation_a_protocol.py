#!/usr/bin/env python3
"""Frozen protocol and source loader for terminal-incidence Confirmation A."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import stat
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdb_profile_comparison_protocol as Source
import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_source_consumer_v7 as SourceV7


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
# Retained only for the obsolete V4 fixture/reader below.
SOURCE_AUDIT_TASK_TIMEOUT_SECONDS = 14400
SOURCE_AUDIT_V5_TASK_TIMEOUT_SECONDS = 28800
SOURCE_AUDIT_V7_TASK_TIMEOUT_SECONDS = 115200

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
COMMIT_RE = re.compile(r"^[0-9a-f]{40,64}$")
SOURCE_V4_REPO = REPO
SOURCE_V4_ATTESTATION_PATH = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v4.json"
)
SOURCE_V4_ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v4"
)
SOURCE_V4_INTENT_PATH = (
    SOURCE_V4_ARTIFACT_DIR / "source-audit-launch-intent-v4.json"
)
SOURCE_V4_LAUNCH_RECEIPT_PATH = (
    SOURCE_V4_ARTIFACT_DIR / "source-audit-launch-receipt-v4.json"
)
SOURCE_V4_LAUNCH_RECEIPT_SHA256 = (
    "90ec55eb1d603cb7434885eeb99ceb2a0123ac02f4f9c02c885cab2635442921"
)
SOURCE_V4_LAUNCH_INTENT_SHA256 = (
    "d4c106b9aa6975f63a14ef3e59cc9186c2f28add9e31a1090f9d0b8d7ff82e27"
)
SOURCE_V4_EXECUTION_RECEIPT_PATH = (
    SOURCE_V4_ARTIFACT_DIR / "source-audit-execution-receipt-v4.json"
)
SOURCE_V4_SLURM_PATH = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v4.slurm"
)
SOURCE_V4_CODE_MANIFEST_PATH = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256"
)
SOURCE_V4_AMENDMENT_PATH = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v4_protocol.md"
)
SOURCE_V4_INVENTORY_PATH = (
    SCRIPT_DIR / "data" / "pdb_terminal_incidence_confirmation_source_audit_v4" /
    "source-inventory-v4.json"
)
SOURCE_V4_OUTPUT_DIR = SOURCE_V4_INVENTORY_PATH.parent
SOURCE_V4_CANDIDATE_PATH = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v4_candidate.json"
)
SOURCE_V4_MANIFEST_FILES = (
    "experiments/artifacts/pdb-terminal-incidence-confirmation/"
    "source-audit-launch-receipt-v1.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v2/"
    "source-audit-launch-receipt-v2.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v3/"
    "source-audit-launch-intent-v3.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v3/"
    "source-audit-launch-receipt-v3.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
    "v3-infrastructure-failure-diagnostic.json",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v3.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v4.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v4.py",
    "experiments/pdb_terminal_incidence_confirmation_inventory.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v3_code.sha256",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v3_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v3.slurm",
    "experiments/pdb_terminal_incidence_shadow_cost_attestation.json",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit_v4.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/suite_wbh_operator_costs.json",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v4.py",
)
SOURCE_V4_SLURM_RELATIVE = (
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v4.slurm"
)
SOURCE_V4_MANIFEST_RELATIVE = (
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256"
)
SOURCE_V4_SLURM_SHA256 = (
    "8504f5b778d74a5120605947e710713532018e2007d276df8c580167b9ce1a8f"
)
SOURCE_V4_CODE_MANIFEST_SHA256 = (
    "d3b571aaffce9f58f09d15f118df57997773c522e3da74bcdcbfbc00299f0518"
)
SOURCE_V4_AMENDMENT_SHA256 = (
    "f146aa22c517ecb266d6d323455beffa961ff4e04fcad3155df61c29c02ca9a4"
)
SOURCE_V4_INVENTORY_SHA256 = (
    "bb9be49a4652ff7bedcadb04b4db35cad701a5b2a2a6d6347c15e0ad670e056e"
)
SOURCE_V4_FIXED_HASHES = {
    "candidate_records_sha256": (
        "5add608b876d236a3fc6b3ab0eaeb67a4b7629c9328039ba2752c4c380e3035c"
    ),
    "alias_groups_sha256": (
        "d9843d73b854eeb58b37dcdfad9265daf7552d909ab0df865b0ff9b13d6dc425"
    ),
    "prior_identity_ledger_sha256": (
        "d4b6aaae00581781dfb4dc7947f7fbec592e19a60167bb5c4a35bd6d2abb3f86"
    ),
    "prior_family_ledger_sha256": (
        "9de66fb087855ede93eabf3193e462bbacdde1bcdc7b2ddc48ab3168b1f31101"
    ),
    "prior_directory_family_map_sha256": (
        "790426b33b085c70ae2a3b63a337616e14a0446db91ff40d854634996d345a52"
    ),
    "shadow_unrepresented_family_sequence_sha256": (
        "9b831aa026deeda951f8aefd3ce8632ec0b82fb7f5231d3fbb5acf9dbd97f746"
    ),
    "all_prior_family_sequence_sha256": (
        "fe05c88ed11512cf25cb68bfe0c2522558bfe23daa1090df7182fc6df4206a59"
    ),
    "all_prior_unrepresented_family_sequence_sha256": (
        "2b461a68f2bcad8bdeb18304ec1cfad68dd287994cce0770b7392fcc285f9ec1"
    ),
    "translator_source_sha256": (
        "c93a014324c4866cc9f83c456d75fc2ad9d4b397bae48411bdc0c757e2f88cbc"
    ),
}
SOURCE_V4_V3_DIAGNOSTIC_RELATIVE = (
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
    "v3-infrastructure-failure-diagnostic.json"
)
SOURCE_V4_V3_DIAGNOSTIC_SHA256 = (
    "a340d2de01304702f6c101d2bb1592536ebc6dfedc1638c5ce1c0559e5ddcf57"
)
SOURCE_V4_PRODUCER_COMMIT_ID = "9fa1387455f947772b8b37e3b103f1ca84efb27b"
SOURCE_V4_JOB_ID = "1865695"
SOURCE_V4_SBATCH_EXECUTABLE = "/usr/bin/sbatch"
SOURCE_V4_SBATCH_EXECUTABLE_SHA256 = (
    "efbb8e172acc7ed768430740d04e19cc07a3ac4701b005d1a997c08424bde741"
)
SOURCE_V4_SACCT_EXECUTABLE = "/usr/bin/sacct"
SOURCE_V4_SACCT_EXECUTABLE_SHA256 = (
    "58f3976b19baa2bc26772a92ab224dd0c1bf0ab3d9b675d85aa3e4636c836315"
)
SOURCE_V4_JJ_EXECUTABLE = Path("/home/jendrik/bin/jj")
SOURCE_V4_JJ_EXECUTABLE_SHA256 = (
    "d1d69a0f87df266eebf0d2592dd019eb288c300b15fd019afe26cb1ed11ba152"
)


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


def _same_exact(actual, expected) -> bool:
    """Compare JSON scalar values without accepting bool as an integer."""
    return type(actual) is type(expected) and actual == expected


def _valid_source_root_identity(value, expected_path: str) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {
            "path", "canonical_path", "uid", "mode", "device", "inode",
        }
        and value.get("path") == expected_path
        and value.get("canonical_path") == expected_path
        and value.get("mode") == "0700"
        and all(
            type(value.get(field)) is int and value[field] >= 0
            for field in ("uid", "device", "inode")
        )
    )


def _validate_split_strata(
    attestation: dict, fixed_hashes: dict | None = None
) -> tuple[list[str], list[str]]:
    if fixed_hashes is None:
        fixed_hashes = SOURCE_V4_FIXED_HASHES
    split = attestation.get("split_strata")
    if not isinstance(split, dict) or set(split) != {
        "shadow_unrepresented", "all_prior_unrepresented",
    }:
        raise ProtocolError("source audit lacks frozen strata")
    shadow_record = split.get("shadow_unrepresented")
    prior_record = split.get("all_prior_unrepresented")
    if (
        not isinstance(shadow_record, dict)
        or set(shadow_record) != {
            "definition", "families", "families_sha256",
            "inventory_family_sequence_sha256",
        }
        or not isinstance(prior_record, dict)
        or set(prior_record) != {
            "definition", "families", "families_sha256",
            "inventory_family_sequence_sha256",
            "prior_directory_family_map_sha256",
            "prior_family_ledger_sha256",
        }
    ):
        raise ProtocolError("source-audit stratum schema changed")
    shadow = shadow_record.get("families")
    all_prior = prior_record.get("families")
    for values in (shadow, all_prior):
        if (
            not isinstance(values, list)
            or values != sorted(set(values))
            or any(not isinstance(value, str) or not value for value in values)
        ):
            raise ProtocolError("source-audit stratum family set changed")
    shadow_sha = hashlib.sha256(canonical_json_line(shadow)).hexdigest()
    shadow_sequence_sha = hashlib.sha256(canonical_json(shadow)).hexdigest()
    prior_sha = hashlib.sha256(canonical_json_line(all_prior)).hexdigest()
    prior_sequence_sha = hashlib.sha256(canonical_json(all_prior)).hexdigest()
    if any((
        shadow_record.get("definition")
        != "families absent from the frozen shadow suites",
        shadow_record.get("families_sha256") != shadow_sha,
        shadow_sequence_sha != fixed_hashes[
            "shadow_unrepresented_family_sequence_sha256"
        ],
        shadow_record.get("inventory_family_sequence_sha256")
        != shadow_sequence_sha,
        prior_record.get("definition")
        != "families absent from both frozen prior experiment artifacts",
        prior_record.get("families_sha256") != prior_sha,
        prior_sequence_sha != fixed_hashes[
            "all_prior_unrepresented_family_sequence_sha256"
        ],
        prior_record.get("inventory_family_sequence_sha256")
        != prior_sequence_sha,
        prior_record.get("prior_directory_family_map_sha256")
        != fixed_hashes["prior_directory_family_map_sha256"],
        prior_record.get("prior_family_ledger_sha256")
        != fixed_hashes["prior_family_ledger_sha256"],
    )):
        raise ProtocolError("source-audit stratum digest chain changed")
    return shadow, all_prior


def _validate_prelaunch_gate(
    attestation: dict, shadow: list[str], all_prior: list[str]
) -> None:
    cohorts = attestation.get("cohorts")
    if not isinstance(cohorts, dict):
        raise ProtocolError("source audit lacks frozen cohorts")
    confirmation = cohorts.get("confirmation_a")
    guided = cohorts.get("guided_b")
    a_tasks = confirmation.get("tasks") if isinstance(confirmation, dict) else None
    b_tasks = guided.get("tasks") if isinstance(guided, dict) else None
    if any(
        not isinstance(tasks, list)
        or any(
            not isinstance(task, dict)
            or not isinstance(task.get("family"), str)
            or not task["family"]
            for task in tasks
        )
        for tasks in (a_tasks, b_tasks)
    ):
        raise ProtocolError("source audit global prelaunch cohorts changed")
    a_sha = hashlib.sha256(canonical_json_line(a_tasks)).hexdigest()
    b_sha = hashlib.sha256(canonical_json_line(b_tasks)).hexdigest()
    if any((
        confirmation.get("role") != "confirmation-a",
        confirmation.get("tasks_sha256") != a_sha,
        guided.get("role") != "guided-b",
        guided.get("top_up_role") != "guided-b-topup",
        not _same_exact(guided.get("target_tasks"), 300),
        not _same_exact(guided.get("max_tasks_per_family"), 12),
        guided.get("tasks_sha256") != b_sha,
        not 200 <= len(b_tasks) <= 300,
        bool(b_tasks) and max(Counter(
            task["family"] for task in b_tasks
        ).values()) > 12,
    )):
        raise ProtocolError("source audit global prelaunch cohorts changed")
    shadow_set = set(shadow)
    prior_set = set(all_prior)

    def support(tasks):
        families = {task["family"] for task in tasks}
        shadow_families = families & shadow_set
        prior_tasks = [task for task in tasks if task["family"] in prior_set]
        prior_families = {task["family"] for task in prior_tasks}
        return families, shadow_families, prior_tasks, prior_families

    a_families, a_shadow, a_prior_tasks, a_prior_families = support(a_tasks)
    b_families, b_shadow, b_prior_tasks, b_prior_families = support(b_tasks)
    clauses = {
        "confirmation_tasks": {
            "actual": len(a_tasks), "required": 650,
            "passed": len(a_tasks) == 650,
        },
        "confirmation_families": {
            "actual": len(a_families), "required_minimum": 28,
            "passed": len(a_families) >= 28,
        },
        "confirmation_shadow_unrepresented_families": {
            "actual": len(a_shadow), "required_minimum": 12,
            "passed": len(a_shadow) >= 12,
        },
        "confirmation_all_prior_unrepresented_tasks": {
            "actual": len(a_prior_tasks), "required_minimum": 100,
            "passed": len(a_prior_tasks) >= 100,
        },
        "confirmation_all_prior_unrepresented_families": {
            "actual": len(a_prior_families), "required_minimum": 10,
            "passed": len(a_prior_families) >= 10,
        },
        "guided_tasks": {
            "actual": len(b_tasks), "required_minimum": 200,
            "passed": len(b_tasks) >= 200,
        },
        "guided_families": {
            "actual": len(b_families), "required_minimum": 30,
            "passed": len(b_families) >= 30,
        },
        "guided_shadow_unrepresented_families": {
            "actual": len(b_shadow), "required_minimum": 12,
            "passed": len(b_shadow) >= 12,
        },
        "guided_all_prior_unrepresented_tasks": {
            "actual": len(b_prior_tasks), "required_minimum": 50,
            "passed": len(b_prior_tasks) >= 50,
        },
        "guided_all_prior_unrepresented_families": {
            "actual": len(b_prior_families), "required_minimum": 10,
            "passed": len(b_prior_families) >= 10,
        },
    }
    a_ids = {(task.get("directory"), task.get("problem")) for task in a_tasks}
    b_ids = {(task.get("directory"), task.get("problem")) for task in b_tasks}
    a_hashes = {task.get("problem_sha256") for task in a_tasks}
    b_hashes = {task.get("problem_sha256") for task in b_tasks}
    disjointness = {
        "source_identity_overlap": len(a_ids & b_ids),
        "problem_sha256_overlap": len(a_hashes & b_hashes),
        "passed": not (a_ids & b_ids or a_hashes & b_hashes),
    }
    gate = attestation.get("prelaunch_gate")
    if not isinstance(gate, dict) or set(gate) != {
        "outcome_blind", "availability", "passed", "clauses",
        "cohort_disjointness",
    }:
        raise ProtocolError("source audit global prelaunch gate changed")
    availability = gate.get("availability")
    availability_keys = {
        "supported_tasks", "supported_families", "supported_tasks_sha256",
        "shadow_unrepresented", "all_prior_unrepresented",
        "post_confirmation_remaining_tasks",
        "guided_b_maximum_under_family_cap", "guided_b_target_tasks",
        "guided_b_max_tasks_per_family",
    }
    if (
        not isinstance(availability, dict)
        or set(availability) != availability_keys
        or any(
            type(availability.get(field)) is not int
            or availability[field] < 0
            for field in (
                "supported_tasks", "supported_families",
                "post_confirmation_remaining_tasks",
                "guided_b_maximum_under_family_cap",
            )
        )
        or availability["supported_tasks"] < len(a_tasks) + len(b_tasks)
        or availability["supported_families"] < len(a_families | b_families)
        or availability["guided_b_maximum_under_family_cap"] < len(b_tasks)
        or not _same_exact(availability.get("guided_b_target_tasks"), 300)
        or not _same_exact(availability.get("guided_b_max_tasks_per_family"), 12)
        or SHA256_RE.fullmatch(availability.get("supported_tasks_sha256", ""))
        is None
    ):
        raise ProtocolError("source audit prelaunch availability changed")
    for name in ("shadow_unrepresented", "all_prior_unrepresented"):
        summary = availability.get(name)
        if (
            not isinstance(summary, dict)
            or set(summary) != {
                "tasks", "families", "tasks_sha256", "families_sha256",
            }
            or any(type(summary.get(field)) is not int or summary[field] < 0
                   for field in ("tasks", "families"))
            or any(SHA256_RE.fullmatch(summary.get(field, "")) is None
                   for field in ("tasks_sha256", "families_sha256"))
        ):
            raise ProtocolError("source audit prelaunch availability changed")
    if any((
        gate.get("outcome_blind") is not True,
        canonical_json(gate.get("clauses")) != canonical_json(clauses),
        canonical_json(gate.get("cohort_disjointness"))
        != canonical_json(disjointness),
        not all(clause["passed"] for clause in clauses.values()),
        disjointness["passed"] is not True,
        gate.get("passed") is not True,
    )):
        raise ProtocolError("source audit global prelaunch gate changed")


_INVENTORY_TASK_KEYS = {
    "aliases", "candidate_index", "canonical_path", "directory",
    "domain_file", "domain_sha256", "family", "is_all_prior_represented",
    "is_all_prior_unrepresented", "is_shadow_family",
    "is_shadow_unrepresented", "problem", "problem_file", "problem_sha256",
}


def _validate_task_inventory_binding(task: dict, inventory: dict) -> None:
    records = inventory.get("records") if isinstance(inventory, dict) else None
    index = task.get("candidate_index")
    if (
        not isinstance(records, list)
        or len(records) != 1640
        or type(index) is not int
        or not 0 <= index < len(records)
        or not isinstance(records[index], dict)
        or set(records[index]) != _INVENTORY_TASK_KEYS
        or canonical_json(records[index])
        != canonical_json({key: task.get(key) for key in _INVENTORY_TASK_KEYS})
    ):
        raise ProtocolError("confirmation task is not bound to source inventory")


_ATTESTATION_KEYS = {
    "schema", "benchmark_revision", "translator_source_sha256",
    "source_inventory_sha256", "source_inventory_records_sha256",
    "code_manifest_sha256", "split_seed", "split_rank_encoding",
    "split_role_labels", "split_strata", "counts",
    "translation_status_counts", "support_exclusion_counts",
    "records_sha256", "prelaunch_gate",
    "confirmation_prelaunch_authorized", "cohorts", "records",
}
_SPLIT_RANK_ENCODING = (
    "SHA256(seed || NUL || role || NUL || family || NUL || "
    "problem_sha256 || NUL || canonical_path)"
)
_SPLIT_ROLE_LABELS = {
    "confirmation_a": "confirmation-a",
    "guided_b_base": "guided-b",
    "guided_b_top_up": "guided-b-topup",
}


def _validate_attestation_envelope(attestation: dict, inventory: dict) -> None:
    inventory_records = inventory.get("records") \
        if isinstance(inventory, dict) else None
    records = attestation.get("records") if isinstance(attestation, dict) else None
    record_keys = _INVENTORY_TASK_KEYS | {
        "translation_attempted", "translator_command", "translation",
        "normalization", "supported", "support_exclusion_reasons",
    }
    if (
        not isinstance(attestation, dict)
        or set(attestation) != _ATTESTATION_KEYS
        or not isinstance(inventory_records, list)
        or len(inventory_records) != 1640
        or not isinstance(records, list)
        or len(records) != 1640
        or attestation.get("split_seed") != COHORT_SEED
        or attestation.get("split_rank_encoding") != _SPLIT_RANK_ENCODING
        or attestation.get("split_role_labels") != _SPLIT_ROLE_LABELS
        or attestation.get("source_inventory_records_sha256")
        != hashlib.sha256(canonical_json_line(inventory_records)).hexdigest()
        or attestation.get("records_sha256")
        != hashlib.sha256(canonical_json_line(records)).hexdigest()
    ):
        raise ProtocolError("source attestation envelope changed")
    for index, (record, inventory_record) in enumerate(zip(
            records, inventory_records
    )):
        reasons = record.get("support_exclusion_reasons") \
            if isinstance(record, dict) else None
        translation = record.get("translation") \
            if isinstance(record, dict) else None
        if (
            not isinstance(record, dict)
            or set(record) != record_keys
            or type(record.get("candidate_index")) is not int
            or record["candidate_index"] != index
            or canonical_json({
                key: record.get(key) for key in _INVENTORY_TASK_KEYS
            }) != canonical_json(inventory_record)
            or record.get("translation_attempted") is not True
            or type(record.get("supported")) is not bool
            or not isinstance(reasons, list)
            or any(not isinstance(reason, str) or not reason for reason in reasons)
            or record["supported"] is not (len(reasons) == 0)
            or not isinstance(translation, dict)
            or not isinstance(translation.get("status"), str)
            or not translation["status"]
            or not isinstance(record.get("normalization"), dict)
            or not isinstance(record.get("translator_command"), list)
        ):
            raise ProtocolError("source attestation record chain changed")
    translation_statuses = dict(sorted(Counter(
        record["translation"]["status"] for record in records
    ).items()))
    exclusions = dict(sorted(Counter(
        reason for record in records
        for reason in record["support_exclusion_reasons"]
    ).items()))
    counts = {
        "candidates": len(records),
        "translation_attempts": sum(
            record["translation_attempted"] for record in records
        ),
        "translated_successfully": translation_statuses.get("success", 0),
        "supported": sum(record["supported"] for record in records),
        "unsupported": sum(not record["supported"] for record in records),
        "families": len({record["family"] for record in records}),
    }
    if (
        attestation.get("counts") != counts
        or attestation.get("translation_status_counts") != translation_statuses
        or attestation.get("support_exclusion_counts") != exclusions
    ):
        raise ProtocolError("source attestation aggregate accounting changed")


def _validate_attestation_split(
    attestation: dict, manifest_hashes: dict[str, str],
    execution: dict | None = None,
) -> None:
    producer_relative = (
        "experiments/audit_pdb_terminal_incidence_confirmation_sources.py"
    )
    inventory_relative = (
        "experiments/pdb_terminal_incidence_confirmation_inventory.py"
    )
    expected_path = Path(os.path.abspath(SOURCE_V4_REPO / producer_relative))
    expected_inventory_path = Path(os.path.abspath(
        SOURCE_V4_REPO / inventory_relative
    ))
    expected_sha = manifest_hashes.get(producer_relative)
    # Hash the producer and every local module it imports before importing:
    # unverified producer bytes must never execute in the consumer process.
    if (
        sha256_file(expected_path) != expected_sha
        or sha256_file(expected_inventory_path)
        != manifest_hashes.get(inventory_relative)
    ):
        raise ProtocolError("source-split producer identity changed")
    try:
        producer = importlib.import_module(
            "audit_pdb_terminal_incidence_confirmation_sources"
        )
        producer_path = Path(os.path.abspath(producer.__file__))
        inventory_path = Path(os.path.abspath(producer.Inventory.__file__))
        if (
            producer_path != expected_path
            or inventory_path != expected_inventory_path
            or sha256_file(inventory_path)
            != manifest_hashes.get(inventory_relative)
        ):
            raise ProtocolError("source-split producer identity changed")
        if execution is None:
            timeout_by_shard = None
        else:
            union_sources = execution.get("union_sources")
            if (
                type(union_sources) is not list
                or len(union_sources) != SourceV7.ARRAY_TASKS
                or SourceV7.CANDIDATES % SourceV7.ARRAY_TASKS != 0
            ):
                raise ProtocolError("V7 source origin ledger changed")
            timeout_by_shard = {}
            for item in union_sources:
                if (
                    not isinstance(item, dict)
                    or type(item.get("shard_index")) is not int
                    or item["shard_index"] in timeout_by_shard
                    or item.get("origin") not in {
                        "v5-completed", "v7-repair",
                    }
                ):
                    raise ProtocolError("V7 source origin ledger changed")
                timeout_by_shard[item["shard_index"]] = {
                    "v5-completed": SOURCE_AUDIT_V5_TASK_TIMEOUT_SECONDS,
                    "v7-repair": SOURCE_AUDIT_V7_TASK_TIMEOUT_SECONDS,
                }[item["origin"]]
            if set(timeout_by_shard) != set(range(SourceV7.ARRAY_TASKS)):
                raise ProtocolError("V7 source origin ledger changed")
        previous_timeout = producer.TASK_TIMEOUT_SECONDS
        try:
            for record in attestation["records"]:
                if timeout_by_shard is None:
                    # Obsolete V4 fixture compatibility only.
                    timeout = SOURCE_AUDIT_TASK_TIMEOUT_SECONDS
                else:
                    candidates_per_shard = (
                        SourceV7.CANDIDATES // SourceV7.ARRAY_TASKS
                    )
                    timeout = timeout_by_shard.get(
                        record["candidate_index"] // candidates_per_shard
                    )
                    if timeout is None:
                        raise ProtocolError("V7 source origin ledger changed")
                producer.TASK_TIMEOUT_SECONDS = timeout
                producer._validate_scan_evidence(record)
                if record["support_exclusion_reasons"] != producer._support_reasons(
                        record["translation"], record["normalization"]
                ):
                    raise ProtocolError(
                        "source attestation support classification changed"
                    )
        finally:
            producer.TASK_TIMEOUT_SECONDS = previous_timeout
        gate, cohorts = producer.split_supported(attestation["records"])
    except ProtocolError:
        raise
    except (Exception, SystemExit) as err:
        raise ProtocolError("source attestation split cannot be replayed") from err
    if (
        sha256_file(expected_path) != expected_sha
        or sha256_file(expected_inventory_path)
        != manifest_hashes.get(inventory_relative)
    ):
        raise ProtocolError("source-split producer changed during replay")
    if (
        canonical_json(gate) != canonical_json(attestation.get("prelaunch_gate"))
        or canonical_json(cohorts) != canonical_json(attestation.get("cohorts"))
        or gate.get("passed") is not True
    ):
        raise ProtocolError("source attestation split replay changed")


def _validate_source_execution_environment(launch: dict, execution: dict) -> None:
    environment = launch.get("execution_environment")
    source_script_dir = SOURCE_V4_REPO / "experiments"
    tmp_root = (
        source_script_dir / "data" /
        "pdb_terminal_incidence_confirmation_source_audit_v4_tmp"
    )
    tmp_template = str(
        tmp_root / "task-{array_job_id}-{array_task_id}"
    )
    cache_template = tmp_template + "/pycache"
    controlled_path = "/usr/bin:/bin"
    python_command = str(
        source_script_dir / "data" / "pdb-terminal-incidence-shadow-venv" /
        "bin" / "python"
    )
    snapshot_policy = {
        "scope": "one domain/problem snapshot tree per candidate",
        "location": "inside the exact per-array-task TMPDIR",
        "directory_mode": "0700",
        "file_mode": "0400",
        "consumers": ["translator", "axiom_based normalization"],
        "verify_before_each_consumer": True,
        "verify_identity_and_sha256_after_use": True,
        "cleanup": (
            "unlink exact files, then rmdir exact directories; no recursion"
        ),
    }
    expected_scalars = {
        "submission_export": "NONE",
        "slurm_export": "NONE",
        "unset_variables": ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"],
        "python_no_user_site": "1",
        "python_no_user_site_flag": 1,
        "python_dont_write_bytecode": "1",
        "python_dont_write_bytecode_flag": True,
        "tmpdir_root": str(tmp_root),
        "tmpdir_template": tmp_template,
        "python_tempfile_directory_template": tmp_template,
        "python_pycache_prefix_template": cache_template,
        "tmpdir_mode": "0700",
        "tmpdir_cleanup": (
            "EXIT trap with pinned /usr/bin/rmdir; no recursion"
        ),
        "root_identity_policy": (
            "canonical absolute path; no direct/ancestor symlinks; mode 0700; "
            "launch uid/device/inode retained"
        ),
        "source_snapshot_policy": snapshot_policy,
        "outer_python_flag": "-B",
        "path": controlled_path,
        "python_command": python_command,
        "sha256sum_command": "/usr/bin/sha256sum",
        "sha256sum_executable": "/usr/bin/sha256sum",
        "sha256sum_executable_sha256": (
            "1950eda10a1bb0c6c2a086ba009b847edec6f30d25eb311b9154ae08819041a9"
        ),
        "mkdir_executable": "/usr/bin/mkdir",
        "mkdir_executable_sha256": (
            "9a71255933f2013dda3fe7e8ad928dc50b7e4c2ae6a7cac58fc1225106c10814"
        ),
        "rmdir_executable": "/usr/bin/rmdir",
        "rmdir_executable_sha256": (
            "b87fd3112c40dd30dca11fa5bc1b3dacc9ed2e309868344dd696824abafc5ded"
        ),
    }
    if (
        not isinstance(environment, dict)
        or execution.get("execution_environment") != environment
        or set(environment) != set(expected_scalars) | {
            "translator_child_environment", "python_executable",
            "python_executable_sha256",
        }
        or any(
            not _same_exact(environment.get(field), expected)
            for field, expected in expected_scalars.items()
        )
        or environment.get("translator_child_environment") != {
            "PATH": controlled_path,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "TMPDIR": tmp_template,
            "PYTHONPYCACHEPREFIX": cache_template,
            "PYTHONPATH": str(SOURCE_V4_REPO / "src"),
        }
        or not isinstance(environment.get("python_executable"), str)
        or not Path(environment["python_executable"]).is_absolute()
        or SHA256_RE.fullmatch(
            environment.get("python_executable_sha256", "")
        ) is None
        or launch.get("submission_environment") != {
            "LANG": "C", "LC_ALL": "C", "PATH": controlled_path,
        }
        or launch.get("sbatch_executable") != SOURCE_V4_SBATCH_EXECUTABLE
        or launch.get("sbatch_executable_sha256")
        != SOURCE_V4_SBATCH_EXECUTABLE_SHA256
        or launch.get("sacct_executable") != SOURCE_V4_SACCT_EXECUTABLE
        or launch.get("sacct_executable_sha256")
        != SOURCE_V4_SACCT_EXECUTABLE_SHA256
        or launch.get("python_version") != REQUIRED_PYTHON_VERSION
        or launch.get("python_executable") != environment["python_executable"]
        or launch.get("python_executable_sha256")
        != environment["python_executable_sha256"]
        or SHA256_RE.fullmatch(
            launch.get("python_environment_sha256", "")
        ) is None
        or SHA256_RE.fullmatch(
            launch.get("python_requirements_sha256", "")
        ) is None
        or not isinstance(launch.get("python_distributions"), dict)
    ):
        raise ProtocolError("source-audit execution environment changed")


def _safe_read_root(path: Path) -> Path:
    path = Path(path)
    try:
        path.relative_to(SOURCE_V4_REPO)
    except ValueError:
        # Explicit non-repository inputs (principally sealed-analysis test
        # fixtures) own their immediate directory as the read trust boundary.
        return path.parent
    return SOURCE_V4_REPO


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


def _read_regular_bytes(path: Path, label: str) -> bytes:
    path = Path(path)
    try:
        return SafeIO.read_regular_file(
            path, label=label, root=_safe_read_root(path)
        ).raw
    except SafeIO.SafeReadError as err:
        raise ProtocolError(str(err)) from err


def _repository_snapshot_files(
    commit_id: str, relative_paths: list[str]
) -> dict[str, bytes]:
    def checked(command, *, text=False):
        if sha256_file(
            SOURCE_V4_JJ_EXECUTABLE
        ) != SOURCE_V4_JJ_EXECUTABLE_SHA256:
            raise ProtocolError("source-audit Jujutsu executable identity changed")
        result = subprocess.check_output(
            command, cwd=SOURCE_V4_REPO, text=text
        )
        if sha256_file(
            SOURCE_V4_JJ_EXECUTABLE
        ) != SOURCE_V4_JJ_EXECUTABLE_SHA256:
            raise ProtocolError("source-audit Jujutsu executable identity changed")
        return result

    base = [
        str(SOURCE_V4_JJ_EXECUTABLE), "--ignore-working-copy", "--no-pager"
    ]
    try:
        listed = checked(
            [*base, "file", "list", "-r", commit_id, "--", *relative_paths],
            text=True,
        ).splitlines()
        values = {
            relative: checked(
                [*base, "file", "show", "-r", commit_id, "--", relative]
            )
            for relative in relative_paths
        }
    except (OSError, subprocess.CalledProcessError) as err:
        raise ProtocolError("cannot verify source-audit v4 repository snapshot") from err
    if len(listed) != len(relative_paths) or set(listed) != set(relative_paths):
        raise ProtocolError("source-audit v4 repository snapshot changed")
    return values


def _load_source_v4_byte_chain(launch: dict) -> tuple[bytes, dict, dict]:
    intent_raw, intent = _load_canonical(
        SOURCE_V4_INTENT_PATH, "source-audit v4 launch intent"
    )
    manifest_raw = _read_regular_bytes(
        SOURCE_V4_CODE_MANIFEST_PATH, "source-audit v4 code manifest"
    )
    slurm_raw = _read_regular_bytes(
        SOURCE_V4_SLURM_PATH, "source-audit v4 Slurm script"
    )
    if (
        hashlib.sha256(intent_raw).hexdigest()
        != SOURCE_V4_LAUNCH_INTENT_SHA256
        or launch.get("launch_intent_sha256")
        != SOURCE_V4_LAUNCH_INTENT_SHA256
        or launch.get("job_id") != SOURCE_V4_JOB_ID
        or hashlib.sha256(manifest_raw).hexdigest()
        != SOURCE_V4_CODE_MANIFEST_SHA256
        or hashlib.sha256(slurm_raw).hexdigest() != SOURCE_V4_SLURM_SHA256
    ):
        raise ProtocolError("source-audit v4 producer roots changed")
    try:
        manifest_lines = manifest_raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise ProtocolError("source-audit v4 code manifest is not ASCII") from err
    matches = [
        re.fullmatch(r"([0-9a-f]{64})  (experiments/[A-Za-z0-9_./-]+)", line)
        for line in manifest_lines
    ]
    if (
        not manifest_raw.endswith(b"\n")
        or any(match is None for match in matches)
        or tuple(match.group(2) for match in matches) != SOURCE_V4_MANIFEST_FILES
        or len(set(SOURCE_V4_MANIFEST_FILES)) != len(SOURCE_V4_MANIFEST_FILES)
    ):
        raise ProtocolError("source-audit v4 code manifest schema changed")
    manifest_hashes = {
        match.group(2): match.group(1) for match in matches
    }
    for relative, expected_sha in manifest_hashes.items():
        raw = _read_regular_bytes(
            SOURCE_V4_REPO / relative,
            "source-audit v4 manifest file {}".format(relative),
        )
        if hashlib.sha256(raw).hexdigest() != expected_sha:
            raise ProtocolError("source-audit v4 manifest-listed bytes changed")
    amendment_relative = SOURCE_V4_AMENDMENT_PATH.relative_to(
        SOURCE_V4_REPO
    ).as_posix()
    diagnostic_relative = SOURCE_V4_V3_DIAGNOSTIC_RELATIVE
    if (
        amendment_relative not in manifest_hashes
        or manifest_hashes[amendment_relative] != SOURCE_V4_AMENDMENT_SHA256
        or diagnostic_relative not in manifest_hashes
        or manifest_hashes[diagnostic_relative]
        != SOURCE_V4_V3_DIAGNOSTIC_SHA256
    ):
        raise ProtocolError("source-audit v4 amendment or diagnostic changed")
    expected_scoped = sorted({
        *SOURCE_V4_MANIFEST_FILES,
        SOURCE_V4_SLURM_RELATIVE,
        SOURCE_V4_MANIFEST_RELATIVE,
    })
    launcher_relative = (
        "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v4.py"
    )
    inventory_raw, inventory = _load_canonical(
        SOURCE_V4_INVENTORY_PATH, "source-audit v4 inventory"
    )
    diagnostic_raw, diagnostic = _load_canonical(
        SOURCE_V4_REPO / diagnostic_relative,
        "source-audit v3 infrastructure diagnostic",
    )
    inventory_sha = hashlib.sha256(inventory_raw).hexdigest()
    token = intent.get("submission_token") if isinstance(intent, dict) else None
    expected_submit = [
        "/usr/bin/sbatch", "--parsable", "--export=NONE",
        "--job-name=confirmation-source-audit-v4-{}".format(token),
        "--comment=confirmation-source-audit-v4/{}".format(token),
        "--account={}".format(ACCOUNT),
        "--partition=fat", "--qos=normal", "--array=0-819",
        "--nodes=1", "--ntasks=1", "--cpus-per-task=1",
        "--mem-per-cpu=1024G", "--time=08:20:00", "--nice=0",
        "--no-requeue", "--chdir={}".format(SOURCE_V4_REPO),
        "--output={}".format(
            (SOURCE_V4_OUTPUT_DIR / "slurm-%A_%a.out").resolve()
        ),
    ]
    intent_keys = {
        "schema", "campaign", "whole_campaign_rerun", "reused_v1_shards",
        "reused_v2_shards", "reused_v3_shards", "partition", "qos",
        "account", "array",
        "array_throttle", "array_tasks", "tasks_per_array_task", "candidates",
        "cpus_per_task", "time_limit", "memory_per_cpu",
        "task_timeout_seconds", "benchmark_revision", "candidate_records_sha256",
        "alias_groups_sha256", "prior_identity_ledger_sha256",
        "prior_family_ledger_sha256", "prior_directory_family_map_sha256",
        "shadow_unrepresented_family_sequence_sha256",
        "all_prior_family_sequence_sha256",
        "all_prior_unrepresented_family_sequence_sha256",
        "translator_source_sha256", "source_inventory_sha256",
        "source_inventory_path", "slurm_script_sha256", "code_manifest_sha256",
        "slurm_submission_mode", "slurm_stdin_sha256", "slurm_stdin_bytes",
        "slurm_path_argument", "submission_journal_contract",
        "launcher_sha256", "repository_commit_id", "scoped_repository_files",
        "jj_executable", "jj_executable_sha256", "sbatch_executable",
        "sbatch_executable_sha256", "sacct_executable",
        "sacct_executable_sha256", "submission_environment", "output_dir",
        "tmpdir_root", "launch_root_identities",
        "candidate_attestation", "frozen_attestation", "execution_environment",
        "python_version", "python_executable", "python_executable_sha256",
        "python_environment_sha256", "python_distributions",
        "python_requirements_sha256", "v3_infrastructure_diagnostic_path",
        "v3_infrastructure_diagnostic_sha256",
        "v3_infrastructure_diagnostic", "recorded_utc", "submission_token",
        "submit_command",
    }
    job_id = launch.get("job_id") if isinstance(launch, dict) else None
    expected_launch = {
        "schema": SOURCE_AUDIT_SCHEMA + "/campaign-v4/launch",
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": job_id,
    }
    hash_fields = (
        "candidate_records_sha256", "alias_groups_sha256",
        "prior_identity_ledger_sha256", "prior_family_ledger_sha256",
        "prior_directory_family_map_sha256",
        "shadow_unrepresented_family_sequence_sha256",
        "all_prior_family_sequence_sha256",
        "all_prior_unrepresented_family_sequence_sha256",
        "translator_source_sha256", "jj_executable_sha256",
        "sbatch_executable_sha256", "sacct_executable_sha256",
    )
    if (
        set(intent) != intent_keys
        or intent.get("schema")
        != SOURCE_AUDIT_SCHEMA + "/campaign-v4/launch/intent"
        or launch != expected_launch
        or job_id != SOURCE_V4_JOB_ID
        or not isinstance(token, str) or re.fullmatch(r"[0-9a-f]{24}", token) is None
        or not isinstance(intent.get("recorded_utc"), str)
        or intent.get("submit_command") != expected_submit
        or intent.get("jj_executable") != "/home/jendrik/bin/jj"
        or intent.get("jj_executable_sha256")
        != "d1d69a0f87df266eebf0d2592dd019eb288c300b15fd019afe26cb1ed11ba152"
        or intent.get("sbatch_executable") != "/usr/bin/sbatch"
        or intent.get("sbatch_executable_sha256")
        != "efbb8e172acc7ed768430740d04e19cc07a3ac4701b005d1a997c08424bde741"
        or intent.get("sacct_executable") != "/usr/bin/sacct"
        or intent.get("sacct_executable_sha256")
        != "58f3976b19baa2bc26772a92ab224dd0c1bf0ab3d9b675d85aa3e4636c836315"
        or intent.get("submission_environment") != {
            "LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin",
        }
        or intent.get("slurm_submission_mode") != "stdin"
        or intent.get("slurm_stdin_sha256") != SOURCE_V4_SLURM_SHA256
        or not _same_exact(intent.get("slurm_stdin_bytes"), len(slurm_raw))
        or intent.get("slurm_path_argument") is not False
        or intent.get("submission_journal_contract")
        != "exact sbatch options-only SubmitLine"
        or inventory_sha != SOURCE_V4_INVENTORY_SHA256
        or intent.get("source_inventory_sha256") != inventory_sha
        or intent.get("source_inventory_path") != str(SOURCE_V4_INVENTORY_PATH)
        or intent.get("output_dir") != str(SOURCE_V4_OUTPUT_DIR)
        or intent.get("candidate_attestation") != str(SOURCE_V4_CANDIDATE_PATH)
        or intent.get("frozen_attestation") != str(SOURCE_V4_ATTESTATION_PATH)
        or intent.get("tmpdir_root") != str(
            SOURCE_V4_REPO / "experiments" / "data" /
            "pdb_terminal_incidence_confirmation_source_audit_v4_tmp"
        )
        or intent.get("slurm_script_sha256") != SOURCE_V4_SLURM_SHA256
        or intent.get("code_manifest_sha256")
        != SOURCE_V4_CODE_MANIFEST_SHA256
        or intent.get("launcher_sha256") != manifest_hashes[launcher_relative]
        or intent.get("scoped_repository_files") != expected_scoped
        or intent.get("repository_commit_id") != SOURCE_V4_PRODUCER_COMMIT_ID
        or not isinstance(intent.get("launch_root_identities"), dict)
        or set(intent["launch_root_identities"]) != {
            "output_dir", "tmpdir_root",
        }
        or any(
            not _valid_source_root_identity(
                intent["launch_root_identities"].get(name), expected_path
            )
            for name, expected_path in (
                ("output_dir", str(SOURCE_V4_OUTPUT_DIR)),
                (
                    "tmpdir_root",
                    str(
                        SOURCE_V4_REPO / "experiments" / "data" /
                        "pdb_terminal_incidence_confirmation_source_audit_v4_tmp"
                    ),
                ),
            )
        )
        or intent.get("v3_infrastructure_diagnostic_path")
        != str(SOURCE_V4_REPO / diagnostic_relative)
        or intent.get("v3_infrastructure_diagnostic_sha256")
        != SOURCE_V4_V3_DIAGNOSTIC_SHA256
        or hashlib.sha256(diagnostic_raw).hexdigest()
        != SOURCE_V4_V3_DIAGNOSTIC_SHA256
        or intent.get("v3_infrastructure_diagnostic") != diagnostic
        or diagnostic.get("schema")
        != SOURCE_AUDIT_SCHEMA + "/campaign-v4/v3-infrastructure-diagnostic"
        or diagnostic.get("successful_v3_shard_contents_inspected") is not False
        or diagnostic.get("successful_v3_log_contents_inspected") is not False
        or diagnostic.get("source_support_outcomes_used_for_v4_design") is not False
        or diagnostic.get("full_rerun_decision") != {
            "reused_v1_shards": 0,
            "reused_v2_shards": 0,
            "reused_v3_shards": 0,
            "scope": "all-820-original-shards-and-1640-candidates",
            "whole_campaign_rerun": True,
        }
        or any(
            SHA256_RE.fullmatch(intent.get(field, "")) is None
            for field in hash_fields
        )
        or any(
            intent.get(field) != expected
            for field, expected in SOURCE_V4_FIXED_HASHES.items()
        )
    ):
        raise ProtocolError("source-audit v4 local byte chain changed")
    snapshot = _repository_snapshot_files(
        intent["repository_commit_id"], expected_scoped
    )
    expected_snapshot_hashes = {
        **manifest_hashes,
        SOURCE_V4_SLURM_RELATIVE: SOURCE_V4_SLURM_SHA256,
        SOURCE_V4_MANIFEST_RELATIVE: SOURCE_V4_CODE_MANIFEST_SHA256,
    }
    if (
        set(snapshot) != set(expected_scoped)
        or any(
            hashlib.sha256(snapshot[relative]).hexdigest() != expected_sha
            for relative, expected_sha in expected_snapshot_hashes.items()
        )
    ):
        raise ProtocolError("source-audit v4 repository snapshot changed")
    return inventory_raw, inventory, manifest_hashes


def _source_v4_tracked_file_sha256(
    launch: dict, manifest_hashes: dict
) -> dict[str, str]:
    def relative(path: Path) -> str:
        try:
            lexical = Path(os.path.abspath(path))
            root = Path(os.path.abspath(SOURCE_V4_REPO))
            return lexical.relative_to(root).as_posix()
        except ValueError as err:
            raise ProtocolError("source-audit v4 bound path escaped repository") from err

    values = {
        **manifest_hashes,
        SOURCE_V4_SLURM_RELATIVE: SOURCE_V4_SLURM_SHA256,
        SOURCE_V4_MANIFEST_RELATIVE: SOURCE_V4_CODE_MANIFEST_SHA256,
    }
    if len(values) != 26 or any(
        SHA256_RE.fullmatch(value) is None for value in values.values()
    ):
        raise ProtocolError("source-audit v4 tracked file set changed")
    return dict(sorted(values.items()))


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
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v5.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v6.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v7.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_a.py",
    "experiments/audit_pdb_terminal_incidence_shadow.py",
    "experiments/exp_pdb_profile_certificate_holdout.py",
    "experiments/exp_pdb_terminal_incidence_confirmation_a.py",
    "experiments/freeze_pdb_terminal_incidence_confirmation_a.py",
    "experiments/jj_cached_revision.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v6.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v7.py",
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
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v5.py",
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v6.py",
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v7.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v5.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v6.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v7.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v7_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v7.slurm",
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
    diagnostic_path: Path
    intent_path: Path
    execution_receipt_path: Path
    launch_receipt_path: Path
    attestation_sha256: str
    diagnostic_sha256: str
    intent_sha256: str
    execution_receipt_sha256: str
    launch_receipt_sha256: str
    cohort_manifest_sha256: str
    records_sha256: str
    translator_source_sha256: str
    tracked_file_sha256: dict[str, str]
    tasks: tuple[dict, ...]
    directories: tuple[str, ...]
    directory_to_family: dict[str, str]
    shadow_unrepresented_families: tuple[str, ...]
    all_prior_unrepresented_families: tuple[str, ...]
    attestation: dict
    inventory: dict
    execution_receipt: dict
    launch_receipt: dict


V7_RECOVERY_STAGE_ARTIFACTS = (
    ("seal_plan", SourceV7.SEAL_PLAN, "seal_plan_sha256"),
    ("union_root_stage", SourceV7.UNION_ROOT_STAGE,
     "union_root_stage_sha256"),
    ("union_stage", SourceV7.UNION_STAGE, "union_stage_sha256"),
    ("candidate_stage", SourceV7.CANDIDATE_STAGE,
     "candidate_stage_sha256"),
    ("attestation_stage", SourceV7.ATTESTATION_STAGE,
     "attestation_stage_sha256"),
)


def v7_recovery_artifacts(execution: dict) -> tuple[tuple[Path, str], ...]:
    return tuple(
        (path, execution[hash_field])
        for _label, path, hash_field in V7_RECOVERY_STAGE_ARTIFACTS
    )


def v7_recovery_provenance(execution: dict) -> dict:
    pre = execution["pre_diagnosis_freeze"]
    provenance = {
        "seal_recovery_protocol": execution["seal_recovery_protocol"],
        "pre_diagnosis_repository_commit_id": pre["repository_commit_id"],
        "pre_diagnosis_files_sha256": pre["files_sha256"],
    }
    for label, path, hash_field in V7_RECOVERY_STAGE_ARTIFACTS:
        provenance[label + "_path"] = path.relative_to(REPO).as_posix()
        provenance[hash_field] = execution[hash_field]
    return provenance


def _validate_task(task: dict) -> None:
    expected_keys = {
        "candidate_index", "directory", "family", "problem",
        "domain_file", "problem_file", "domain_sha256", "problem_sha256",
        "canonical_path", "is_shadow_family", "is_shadow_unrepresented",
        "is_all_prior_represented", "is_all_prior_unrepresented", "aliases",
        "selection_role", "selection_rank_sha256",
        "source_audit_evidence_sha256",
    }
    required_strings = (
        "directory", "family", "problem", "domain_file", "problem_file",
        "canonical_path", "domain_sha256", "problem_sha256", "selection_role",
        "selection_rank_sha256", "source_audit_evidence_sha256",
    )
    if (
        not isinstance(task, dict)
        or set(task) != expected_keys
        or type(task.get("candidate_index")) is not int
        or not 0 <= task["candidate_index"] < 1640
        or any(
        not isinstance(task.get(field), str) or not task[field]
        for field in required_strings
        )
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
    if (
        task["canonical_path"] != task["problem_file"]
        or Path(task["problem_file"]) != Path(task["directory"]) / task["problem"]
        or Path(task["domain_file"]).parent != Path(task["directory"])
    ):
        raise ProtocolError("confirmation task canonical path is inconsistent")
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
    if task["is_shadow_family"] == task["is_shadow_unrepresented"]:
        raise ProtocolError("shadow stratum flags are inconsistent")
    alias_keys = {
        "directory", "family", "problem", "domain_file", "problem_file",
        "domain_sha256", "problem_sha256",
    }
    aliases = task["aliases"]
    canonical_alias = {key: task[key] for key in alias_keys}
    if (
        not isinstance(aliases, list)
        or not aliases
        or any(not isinstance(alias, dict) or set(alias) != alias_keys
               for alias in aliases)
        or aliases[0] != canonical_alias
        or aliases != sorted(aliases, key=lambda alias: (
            alias["directory"], alias["problem"], alias["problem_file"],
            alias["domain_file"],
        ))
        or any(
            alias["family"] != task["family"]
            or alias["problem_sha256"] != task["problem_sha256"]
            or SHA256_RE.fullmatch(alias["domain_sha256"]) is None
            for alias in aliases
        )
    ):
        raise ProtocolError("confirmation task alias provenance is malformed")
    expected_rank = hashlib.sha256(b"\0".join(
        value.encode("utf-8") for value in (
            COHORT_SEED, task["selection_role"], task["family"],
            task["problem_sha256"], task["canonical_path"],
        )
    )).hexdigest()
    if task["selection_rank_sha256"] != expected_rank:
        raise ProtocolError("confirmation task split rank changed")


def _validate_v4_original_output(
    execution: dict, launch: dict, source_inventory_sha256: str
) -> dict[str, str]:
    tree = execution.get("original_output_tree")
    launch_roots = launch.get("launch_root_identities")
    if not isinstance(launch_roots, dict):
        raise ProtocolError("source-audit v4 launch roots changed")
    expected_root = launch_roots.get("output_dir")
    shard_names = [
        "shard-{:04d}-of-0820.json".format(index) for index in range(820)
    ]
    environment_names = [
        "environment-{:04d}-of-0820.json".format(index)
        for index in range(820)
    ]
    expected_paths = sorted([
        "source-inventory-v4.json",
        *shard_names,
        *environment_names,
        *(
            "slurm-{}_{}.out".format(launch["job_id"], index)
            for index in range(820)
        ),
    ])
    if (
        not isinstance(tree, dict)
        or set(tree) != {"sha256", "root_identity", "files_count", "files"}
        or tree.get("root_identity") != expected_root
        or not _valid_source_root_identity(
            tree.get("root_identity"), str(SOURCE_V4_OUTPUT_DIR)
        )
        or not _same_exact(tree.get("files_count"), 2461)
        or not isinstance(tree.get("files"), list)
        or len(tree["files"]) != 2461
        or SHA256_RE.fullmatch(tree.get("sha256", "")) is None
    ):
        raise ProtocolError("source-audit v4 original output schema changed")
    digest = hashlib.sha256()
    digest.update(b"root-identity\0" + canonical_json(expected_root))
    hashes = {}
    for record, expected_path in zip(tree["files"], expected_paths):
        if (
            not isinstance(record, dict)
            or set(record) != {"path", "bytes", "sha256"}
            or record.get("path") != expected_path
            or type(record.get("bytes")) is not int
            or record["bytes"] < 0
            or SHA256_RE.fullmatch(record.get("sha256", "")) is None
        ):
            raise ProtocolError("source-audit v4 original output file changed")
        hashes[expected_path] = record["sha256"]
        digest.update(
            expected_path.encode("ascii") + b"\0"
            + bytes.fromhex(record["sha256"])
        )
    if (
        digest.hexdigest() != tree["sha256"]
        or hashes["source-inventory-v4.json"] != source_inventory_sha256
    ):
        raise ProtocolError("source-audit v4 original output digest changed")

    environments = execution.get("task_environment_manifest")
    expected_environment_schema = (
        SOURCE_AUDIT_SCHEMA + "/campaign-v4/task-environment/v1/manifest/v1"
    )
    if (
        not isinstance(environments, dict)
        or set(environments) != {
            "schema", "records", "records_sha256", "tmpdir_root_identity",
            "output_dir_identity", "all_task_tmpdirs_removed_by_rmdir",
        }
        or environments.get("schema") != expected_environment_schema
        or environments.get("tmpdir_root_identity")
        != launch_roots.get("tmpdir_root")
        or environments.get("output_dir_identity") != expected_root
        or environments.get("all_task_tmpdirs_removed_by_rmdir") is not True
        or not isinstance(environments.get("records"), list)
        or len(environments["records"]) != 820
    ):
        raise ProtocolError("source-audit v4 task environment manifest changed")
    tmp_root = Path(launch["tmpdir_root"])
    for index, record in enumerate(environments["records"]):
        environment_name = environment_names[index]
        shard_name = shard_names[index]
        tmpdir = str(tmp_root / "task-{}-{}".format(launch["job_id"], index))
        if (
            not isinstance(record, dict)
            or set(record) != {
                "array_task", "path", "sha256", "tmpdir",
                "tmpdir_identity", "output_dir_identity", "shard_sha256",
            }
            or not _same_exact(record.get("array_task"), index)
            or record.get("path") != environment_name
            or record.get("sha256") != hashes[environment_name]
            or record.get("tmpdir") != tmpdir
            or not _valid_source_root_identity(
                record.get("tmpdir_identity"), tmpdir
            )
            or record.get("output_dir_identity") != expected_root
            or record.get("shard_sha256") != hashes[shard_name]
        ):
            raise ProtocolError("source-audit v4 task environment record changed")
    if environments.get("records_sha256") != hashlib.sha256(
        canonical_json(environments["records"])
    ).hexdigest():
        raise ProtocolError("source-audit v4 task environment digest changed")
    for field in (
        "launch_root_identities", "sealing_root_identities_before",
        "sealing_root_identities_after",
    ):
        if execution.get(field) != launch_roots:
            raise ProtocolError("source-audit v4 root identity chain changed")
    return hashes


def _validate_v4_scheduler_contract_rows(
    execution: dict, launch: dict, scheduler_rows: list[dict]
) -> None:
    rows = execution.get("scheduler_contract_rows")
    token = launch.get("submission_token")
    expected_name = "confirmation-source-audit-v4-{}".format(token)
    expected_keys = {
        "array_task", "account", "partition", "qos", "req_cpus",
        "req_mem", "time_limit", "state", "exit_code", "job_name",
    }
    if not isinstance(rows, list) or len(rows) != 820:
        raise ProtocolError("source-audit v4 resource accounting changed")
    for index, (row, scheduler_row) in enumerate(zip(rows, scheduler_rows)):
        if (
            not isinstance(row, dict)
            or set(row) != expected_keys
            or type(row.get("array_task")) is not int
            or row["array_task"] != index
            or row.get("account") != ACCOUNT
            or row.get("partition") != "fat"
            or row.get("qos") != "normal"
            or not _same_exact(row.get("req_cpus"), 1)
            or row.get("req_mem") != "1024G"
            or row.get("time_limit") != "08:20:00"
            or row.get("state") != "COMPLETED"
            or row.get("exit_code") != "0:0"
            or row.get("job_name") != expected_name
            or row["state"] != scheduler_row["state"]
            or row["exit_code"] != scheduler_row["exit_code"]
        ):
            raise ProtocolError("source-audit v4 resource accounting changed")


def _load_source_materials_v4_obsolete(
    attestation_path: Path,
    execution_receipt_path: Path,
    launch_receipt_path: Path,
) -> SourceMaterials:
    # Normalize dot components without following symlinks.  The fixed lexical
    # location must match first; _load_canonical then lstat-checks that exact
    # directory entry rather than a resolved target.
    attestation_path = Path(os.path.abspath(attestation_path))
    execution_receipt_path = Path(os.path.abspath(execution_receipt_path))
    launch_receipt_path = Path(os.path.abspath(launch_receipt_path))
    if (
        attestation_path != Path(os.path.abspath(SOURCE_V4_ATTESTATION_PATH))
        or execution_receipt_path
        != Path(os.path.abspath(SOURCE_V4_EXECUTION_RECEIPT_PATH))
        or launch_receipt_path
        != Path(os.path.abspath(SOURCE_V4_LAUNCH_RECEIPT_PATH))
    ):
        raise ProtocolError("source-audit v4 fixed artifact paths changed")
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
    execution_keys = {
        "schema", "campaign", "whole_campaign_rerun", "original_only",
        "recovery", "reused_v1_shards", "reused_v2_shards",
        "reused_v3_shards",
        "launch_receipt_sha256", "job_id", "partition", "qos", "account",
        "array", "array_tasks", "tasks_per_array_task", "cpus_per_task",
        "memory_per_cpu", "time_limit", "task_timeout_seconds",
        "array_throttle", "shards", "candidates", "scheduler_state_counts",
        "scheduler_rows", "scheduler_contract_rows", "launch_root_identities",
        "sealing_root_identities_before", "sealing_root_identities_after",
        "original_output_tree", "task_environment_manifest",
        "code_manifest_sha256", "source_inventory_sha256",
        "v3_infrastructure_diagnostic_sha256",
        "v3_infrastructure_diagnostic", "execution_environment",
        "source_audit_complete", "confirmation_prelaunch_authorized",
        "prelaunch_gate", "attestation_sha256",
        "attestation_records_sha256", "cohort_manifest_sha256", "counts",
        "translation_status_counts", "support_exclusion_counts",
    }
    if (
        schema != SOURCE_AUDIT_SCHEMA
        or set(execution) != execution_keys
        or execution.get("schema") != schema + "/campaign-v4/execution"
        or launch.get("schema") != schema + "/campaign-v4/launch"
    ):
        raise ProtocolError("source-audit schema chain changed")
    if any((
        attestation.get("benchmark_revision") != BENCHMARK_REVISION,
        launch.get("benchmark_revision") != BENCHMARK_REVISION,
        launch.get("campaign") != "v4",
        execution.get("campaign") != "v4",
        launch.get("whole_campaign_rerun") is not True,
        execution.get("whole_campaign_rerun") is not True,
        execution.get("original_only") is not True,
        execution.get("recovery") is not None,
        not _same_exact(launch.get("reused_v1_shards"), 0),
        not _same_exact(execution.get("reused_v1_shards"), 0),
        not _same_exact(launch.get("reused_v2_shards"), 0),
        not _same_exact(execution.get("reused_v2_shards"), 0),
        not _same_exact(launch.get("reused_v3_shards"), 0),
        not _same_exact(execution.get("reused_v3_shards"), 0),
        launch.get("memory_per_cpu") != "1024G",
        execution.get("memory_per_cpu") != "1024G",
        launch_sha != SOURCE_V4_LAUNCH_RECEIPT_SHA256,
        execution.get("launch_receipt_sha256") != launch_sha,
        execution.get("attestation_sha256") != attestation_sha,
        execution.get("source_audit_complete") is not True,
        execution.get("confirmation_prelaunch_authorized") is not True,
        attestation.get("confirmation_prelaunch_authorized") is not True,
        execution.get("prelaunch_gate", {}).get("passed") is not True,
        attestation.get("prelaunch_gate", {}).get("passed") is not True,
        execution.get("prelaunch_gate") != attestation.get("prelaunch_gate"),
        execution.get("counts") != attestation.get("counts"),
        execution.get("translation_status_counts")
        != attestation.get("translation_status_counts"),
        execution.get("support_exclusion_counts")
        != attestation.get("support_exclusion_counts"),
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
        "time_limit": "08:20:00",
        "memory_per_cpu": "1024G",
        "task_timeout_seconds": 14400,
    }
    expected_execution_scheduler = {
        "partition": "fat",
        "qos": "normal",
        "account": ACCOUNT,
        "array": "0-819",
        "array_tasks": 820,
        "tasks_per_array_task": 2,
        "cpus_per_task": 1,
        "memory_per_cpu": "1024G",
        "time_limit": "08:20:00",
        "task_timeout_seconds": 14400,
        "array_throttle": 0,
        "shards": 820,
        "candidates": 1640,
    }
    if any(
        not _same_exact(launch.get(field), expected)
        for field, expected in expected_launch_scheduler.items()
    ) or any(
        not _same_exact(execution.get(field), expected)
        for field, expected in expected_execution_scheduler.items()
    ):
        raise ProtocolError("source-audit v4 scheduler contract changed")
    scheduler_rows = execution.get("scheduler_rows")
    if (
        not isinstance(scheduler_rows, list)
        or len(scheduler_rows) != 820
        or any(
            not isinstance(row, dict)
            or set(row) != {
                "array_task", "state", "exit_code", "elapsed", "partition",
            }
            or type(row.get("array_task")) is not int
            or row.get("array_task") != index
            or row.get("partition") != "fat"
            or row.get("state") != "COMPLETED"
            or row.get("exit_code") != "0:0"
            or any(
                not isinstance(row.get(field), str) or not row[field]
                for field in ("state", "exit_code", "elapsed")
            )
            for index, row in enumerate(scheduler_rows)
        )
        or execution.get("scheduler_state_counts") != {"COMPLETED": 820}
        or dict(Counter(row["state"] for row in scheduler_rows))
        != {"COMPLETED": 820}
    ):
        raise ProtocolError("source-audit v4 scheduler rows changed")
    _validate_v4_scheduler_contract_rows(execution, launch, scheduler_rows)
    _validate_source_execution_environment(launch, execution)

    inventory_raw, inventory, manifest_hashes = _load_source_v4_byte_chain(launch)
    _validate_attestation_envelope(attestation, inventory)
    _validate_attestation_split(attestation, manifest_hashes)
    tracked_file_sha256 = _source_v4_tracked_file_sha256(
        launch, manifest_hashes
    )

    source_inventory_sha = attestation.get("source_inventory_sha256")
    code_manifest_sha = attestation.get("code_manifest_sha256")
    records_sha = attestation.get("records_sha256")
    original_tree = execution.get("original_output_tree")
    if any((
        SHA256_RE.fullmatch(source_inventory_sha or "") is None,
        SHA256_RE.fullmatch(code_manifest_sha or "") is None,
        SHA256_RE.fullmatch(records_sha or "") is None,
        launch.get("source_inventory_sha256") != source_inventory_sha,
        execution.get("source_inventory_sha256") != source_inventory_sha,
        source_inventory_sha != hashlib.sha256(inventory_raw).hexdigest(),
        launch.get("code_manifest_sha256") != code_manifest_sha,
        execution.get("code_manifest_sha256") != code_manifest_sha,
        code_manifest_sha != SOURCE_V4_CODE_MANIFEST_SHA256,
        launch.get("translator_source_sha256")
        != attestation.get("translator_source_sha256"),
        execution.get("job_id") != launch.get("job_id"),
        launch.get("repository_commit_id") != SOURCE_V4_PRODUCER_COMMIT_ID,
        launch.get("slurm_script_sha256") != SOURCE_V4_SLURM_SHA256,
        launch.get("launch_intent_sha256") != SOURCE_V4_LAUNCH_INTENT_SHA256,
        not isinstance(original_tree, dict),
        SHA256_RE.fullmatch(
            original_tree.get("sha256", "")
            if isinstance(original_tree, dict) else ""
        ) is None,
    )):
        raise ProtocolError("source-audit provenance chain changed")
    _validate_v4_original_output(
        execution, launch, source_inventory_sha
    )
    diagnostic = launch.get("v3_infrastructure_diagnostic")
    if (
        not isinstance(diagnostic, dict)
        or execution.get("v3_infrastructure_diagnostic") != diagnostic
        or execution.get("v3_infrastructure_diagnostic_sha256")
        != SOURCE_V4_V3_DIAGNOSTIC_SHA256
        or diagnostic.get("schema")
        != schema + "/campaign-v4/v3-infrastructure-diagnostic"
        or diagnostic.get("successful_v3_shard_contents_inspected") is not False
        or diagnostic.get("successful_v3_log_contents_inspected") is not False
        or diagnostic.get("source_support_outcomes_used_for_v4_design") is not False
    ):
        raise ProtocolError("source-audit v3 infrastructure diagnostic chain changed")
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
        _validate_task_inventory_binding(task, inventory)
    candidate_indexes = [task["candidate_index"] for task in tasks]
    if len(set(candidate_indexes)) != len(candidate_indexes):
        raise ProtocolError("Confirmation A contains duplicate candidate indices")
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
    shadow, all_prior = _validate_split_strata(attestation)
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
    families = {task["family"] for task in tasks}
    shadow_families = {task["family"] for task in tasks
                       if task["is_shadow_unrepresented"]}
    all_prior_tasks = [task for task in tasks
                       if task["is_all_prior_unrepresented"]]
    all_prior_families = {task["family"] for task in all_prior_tasks}
    if any((
        len(families) < MIN_SOURCE_COHORT_FAMILIES,
        len(shadow_families) < MIN_SOURCE_SHADOW_UNREPRESENTED_FAMILIES,
        len(all_prior_tasks) < MIN_SOURCE_ALL_PRIOR_UNREPRESENTED_TASKS,
        len(all_prior_families) < MIN_SOURCE_ALL_PRIOR_UNREPRESENTED_FAMILIES,
    )):
        raise ProtocolError("Confirmation A source-support floor changed")
    _validate_prelaunch_gate(attestation, shadow, all_prior)
    guided = attestation["cohorts"]["guided_b"]
    guided_indexes = []
    for guided_task in guided["tasks"]:
        _validate_task_inventory_binding(guided_task, inventory)
        guided_indexes.append(guided_task["candidate_index"])
    if (
        len(set(guided_indexes)) != len(guided_indexes)
        or set(guided_indexes) & set(candidate_indexes)
    ):
        raise ProtocolError("source-audit global cohorts reuse candidates")
    guided_sha = hashlib.sha256(
        canonical_json_line(guided["tasks"])
    ).hexdigest()
    if execution.get("cohort_manifest_sha256") != {
        "confirmation_a": cohort_sha,
        "guided_b": guided_sha,
    }:
        raise ProtocolError("source-audit global cohort hash chain changed")
    translator_sha = attestation.get("translator_source_sha256")
    if SHA256_RE.fullmatch(translator_sha or "") is None:
        raise ProtocolError("translator source hash is invalid")
    if not isinstance(launch.get("job_id"), str) or not launch["job_id"].isdigit():
        raise ProtocolError("source launch job ID is invalid")
    return SourceMaterials(
        attestation_path=attestation_path,
        diagnostic_path=SOURCE_V4_AMENDMENT_PATH,
        intent_path=SOURCE_V4_INTENT_PATH,
        execution_receipt_path=execution_receipt_path,
        launch_receipt_path=launch_receipt_path,
        attestation_sha256=attestation_sha,
        diagnostic_sha256=SOURCE_V4_AMENDMENT_SHA256,
        intent_sha256=SOURCE_V4_LAUNCH_INTENT_SHA256,
        execution_receipt_sha256=execution_sha,
        launch_receipt_sha256=launch_sha,
        cohort_manifest_sha256=cohort_sha,
        records_sha256=records_sha,
        translator_source_sha256=translator_sha,
        tracked_file_sha256=tracked_file_sha256,
        tasks=tuple(tasks),
        directories=tuple(sorted(directory_to_family)),
        directory_to_family=dict(sorted(directory_to_family.items())),
        shadow_unrepresented_families=tuple(shadow),
        all_prior_unrepresented_families=tuple(all_prior),
        attestation=attestation,
        inventory=inventory,
        execution_receipt=execution,
        launch_receipt=launch,
    )


def _load_v7_source_chain(
    attestation_path: Path,
    execution_receipt_path: Path,
    launch_receipt_path: Path,
):
    try:
        return SourceV7.load_v7_source(
            attestation_path,
            execution_receipt_path,
            launch_receipt_path,
            snapshot_reader=_repository_snapshot_files,
        )
    except SourceV7.SourceConsumerError as err:
        raise ProtocolError(str(err)) from err


def _validate_v7_source_envelope(
    attestation: dict, inventory: dict, execution: dict, launch: dict,
) -> None:
    if (
        attestation.get("schema") != SOURCE_AUDIT_SCHEMA
        or attestation.get("benchmark_revision") != BENCHMARK_REVISION
        or launch.get("schema") != SourceV7.Launch.LAUNCH_SCHEMA
        or launch.get("campaign") != SourceV7.CAMPAIGN
        or launch.get("benchmark_revision") != BENCHMARK_REVISION
        or execution.get("schema") != SourceV7.Launch.EXECUTION_SCHEMA
        or execution.get("campaign") != SourceV7.CAMPAIGN
        or execution.get("benchmark_revision") != BENCHMARK_REVISION
        or SourceV7.Launch.V5Source.TASK_TIMEOUT_SECONDS
        != SOURCE_AUDIT_V5_TASK_TIMEOUT_SECONDS
        or SourceV7.Source.TASK_TIMEOUT_SECONDS
        != SOURCE_AUDIT_V7_TASK_TIMEOUT_SECONDS
        or not isinstance(inventory, dict)
        or inventory.get("schema") != SOURCE_AUDIT_SCHEMA + "/inventory"
        or inventory.get("benchmark_revision") != BENCHMARK_REVISION
        or not isinstance(inventory.get("records"), list)
    ):
        raise ProtocolError("V7 source schema/benchmark provenance changed")


def load_source_materials(
    attestation_path: Path,
    execution_receipt_path: Path,
    launch_receipt_path: Path,
) -> SourceMaterials:
    """Load the sole prospective V7 two-origin seal used by A and B."""
    chain = _load_v7_source_chain(
        attestation_path, execution_receipt_path, launch_receipt_path
    )
    attestation = chain.attestation
    execution = chain.execution
    launch = chain.launch
    inventory = chain.inventory
    _validate_v7_source_envelope(attestation, inventory, execution, launch)
    _validate_attestation_envelope(attestation, inventory)
    manifest_hashes = {
        relative: chain.tracked_file_sha256[relative]
        for relative in SourceV7.CODE_MANIFEST_FILES
    }
    _validate_attestation_split(attestation, manifest_hashes, execution)

    cohort = attestation.get("cohorts", {}).get("confirmation_a")
    tasks = cohort.get("tasks") if isinstance(cohort, dict) else None
    if (
        not isinstance(tasks, list)
        or len(tasks) != COHORT_TASKS
        or cohort.get("role") != "confirmation-a"
    ):
        raise ProtocolError("V7 source audit has the wrong Confirmation A cohort")
    for task in tasks:
        _validate_task(task)
        _validate_task_inventory_binding(task, inventory)
    candidate_indexes = [task["candidate_index"] for task in tasks]
    identities = [(task["directory"], task["problem"]) for task in tasks]
    problem_hashes = [task["problem_sha256"] for task in tasks]
    if (
        len(set(candidate_indexes)) != COHORT_TASKS
        or len(set(identities)) != COHORT_TASKS
        or len(set(problem_hashes)) != COHORT_TASKS
    ):
        raise ProtocolError("Confirmation A contains duplicate V7 sources")
    cohort_sha = hashlib.sha256(canonical_json_line(tasks)).hexdigest()
    records_sha = attestation.get("records_sha256")
    guided = attestation.get("cohorts", {}).get("guided_b")
    guided_tasks = guided.get("tasks") if isinstance(guided, dict) else None
    if not isinstance(guided_tasks, list):
        raise ProtocolError("V7 source audit lacks the guided B cohort")
    for task in guided_tasks:
        _validate_task_inventory_binding(task, inventory)
    guided_indexes = [task["candidate_index"] for task in guided_tasks]
    guided_sha = hashlib.sha256(canonical_json_line(guided_tasks)).hexdigest()
    if (
        cohort.get("tasks_sha256") != cohort_sha
        or guided.get("tasks_sha256") != guided_sha
        or len(set(guided_indexes)) != len(guided_indexes)
        or set(guided_indexes) & set(candidate_indexes)
        or execution.get("cohort_manifest_sha256") != {
            "confirmation_a": cohort_sha,
            "guided_b": guided_sha,
        }
        or execution.get("attestation_records_sha256") != records_sha
    ):
        raise ProtocolError("V7 cohort hash chain changed")
    directory_to_family = {}
    for task in tasks:
        previous = directory_to_family.setdefault(task["directory"], task["family"])
        if previous != task["family"]:
            raise ProtocolError("V7 source audit maps one directory twice")
    shadow, all_prior = _validate_split_strata(attestation)
    shadow_set = set(shadow)
    all_prior_set = set(all_prior)
    for task in tasks:
        if (
            task["is_shadow_unrepresented"] != (task["family"] in shadow_set)
            or task["is_all_prior_unrepresented"]
            != (task["family"] in all_prior_set)
        ):
            raise ProtocolError("V7 task stratum flag changed")
    families = {task["family"] for task in tasks}
    shadow_families = {
        task["family"] for task in tasks if task["is_shadow_unrepresented"]
    }
    all_prior_tasks = [task for task in tasks if task["is_all_prior_unrepresented"]]
    if (
        len(families) < MIN_SOURCE_COHORT_FAMILIES
        or len(shadow_families) < MIN_SOURCE_SHADOW_UNREPRESENTED_FAMILIES
        or len(all_prior_tasks) < MIN_SOURCE_ALL_PRIOR_UNREPRESENTED_TASKS
        or len({task["family"] for task in all_prior_tasks})
        < MIN_SOURCE_ALL_PRIOR_UNREPRESENTED_FAMILIES
    ):
        raise ProtocolError("Confirmation A V7 source-support floor changed")
    _validate_prelaunch_gate(attestation, shadow, all_prior)
    translator_sha = attestation.get("translator_source_sha256")
    if (
        SHA256_RE.fullmatch(records_sha or "") is None
        or SHA256_RE.fullmatch(translator_sha or "") is None
    ):
        raise ProtocolError("V7 attestation digest changed")
    origins = Counter(
        item.get("origin") for item in execution.get("union_sources", [])
        if isinstance(item, dict)
    )
    if (
        execution.get("reused_v6_shards") != 0
        or execution.get("v6_runtime_artifacts_used") is not False
        or execution.get("source_support_outcome_blind_selective_repair") is not True
        or execution.get(
            "v5_reusable_triplet_bytes_read_during_seal_after_v7_all_success_gate"
        ) is not True
        or execution.get(
            "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion"
        ) is not False
        or execution.get(
            "v5_reusable_selected_tree_first_separately_recorded_at_v7_seal"
        ) is not True
        or execution.get(
            "scheduler_membership_affects_execution_origin_only"
        ) is not True
        or execution.get("accepted_translation_statuses")
        != ["input-rejected", "success"]
        or execution.get("translator_timeout_is_infrastructure_failure") is not True
        or execution.get(
            "resource_ceiling_changes_accepted_outcome_classes"
        ) is not False
        or execution.get("reused_v5_shards")
        + execution.get("repaired_v5_shards") != SourceV7.ARRAY_TASKS
        or origins != Counter({
            "v5-completed": execution.get("reused_v5_shards"),
            "v7-repair": execution.get("repaired_v5_shards"),
        })
    ):
        raise ProtocolError("V7 source audit origin ledger changed")
    return SourceMaterials(
        attestation_path=chain.attestation_path,
        diagnostic_path=chain.diagnostic_path,
        intent_path=chain.intent_path,
        execution_receipt_path=chain.execution_receipt_path,
        launch_receipt_path=chain.launch_receipt_path,
        attestation_sha256=hashlib.sha256(chain.attestation_raw).hexdigest(),
        diagnostic_sha256=hashlib.sha256(chain.diagnostic_raw).hexdigest(),
        intent_sha256=hashlib.sha256(chain.intent_raw).hexdigest(),
        execution_receipt_sha256=hashlib.sha256(chain.execution_raw).hexdigest(),
        launch_receipt_sha256=hashlib.sha256(chain.launch_raw).hexdigest(),
        cohort_manifest_sha256=cohort_sha,
        records_sha256=records_sha,
        translator_source_sha256=translator_sha,
        tracked_file_sha256=chain.tracked_file_sha256,
        tasks=tuple(tasks),
        directories=tuple(sorted(directory_to_family)),
        directory_to_family=dict(sorted(directory_to_family.items())),
        shadow_unrepresented_families=tuple(shadow),
        all_prior_unrepresented_families=tuple(all_prior),
        attestation=attestation,
        inventory=inventory,
        execution_receipt=execution,
        launch_receipt=launch,
    )


def _load_freeze(path: Path = FREEZE_PATH) -> tuple[dict, SourceMaterials]:
    raw, freeze = _load_canonical(path, "Confirmation A freeze")
    if (
        set(freeze) != {
            "schema", "freeze_repository_revision", "source_audit", "planner", "design",
            "experiment_source_sha256",
        }
        or freeze.get("schema") != FREEZE_SCHEMA
    ):
        raise ProtocolError("Confirmation A freeze schema changed")
    sources = freeze.get("source_audit")
    freeze_repository_revision = freeze.get("freeze_repository_revision")
    planner = freeze.get("planner")
    design = freeze.get("design")
    source_hashes = freeze.get("experiment_source_sha256")
    if (
        COMMIT_RE.fullmatch(freeze_repository_revision or "") is None
        or not all(isinstance(value, dict) for value in (
        sources, planner, design, source_hashes
        ))
    ):
        raise ProtocolError("Confirmation A freeze is incomplete")
    attestation_path = _safe_repo_path(sources.get("attestation_path"), "attestation")
    execution_path = _safe_repo_path(
        sources.get("execution_receipt_path"), "source execution receipt"
    )
    launch_path = _safe_repo_path(
        sources.get("launch_receipt_path"), "source launch receipt"
    )
    intent_path = _safe_repo_path(
        sources.get("launch_intent_path"), "source launch intent"
    )
    materials = load_source_materials(attestation_path, execution_path, launch_path)
    expected_sources = {
        "campaign": materials.execution_receipt["campaign"],
        "attestation_path": materials.attestation_path.relative_to(
            REPO
        ).as_posix(),
        "terminal_diagnostic_path": materials.diagnostic_path.relative_to(
            REPO
        ).as_posix(),
        "execution_receipt_path": materials.execution_receipt_path.relative_to(
            REPO
        ).as_posix(),
        "launch_receipt_path": materials.launch_receipt_path.relative_to(
            REPO
        ).as_posix(),
        "launch_intent_path": materials.intent_path.relative_to(REPO).as_posix(),
        "attestation_sha256": materials.attestation_sha256,
        "terminal_diagnostic_sha256": materials.diagnostic_sha256,
        "execution_receipt_sha256": materials.execution_receipt_sha256,
        "launch_receipt_sha256": materials.launch_receipt_sha256,
        "launch_intent_sha256": materials.intent_sha256,
        "cohort_manifest_sha256": materials.cohort_manifest_sha256,
        "attestation_records_sha256": materials.records_sha256,
        "translator_source_sha256": materials.translator_source_sha256,
        "job_id": materials.launch_receipt["job_id"],
        "code_manifest_sha256": materials.execution_receipt[
            "v7_code_manifest_sha256"
        ],
        "repository_commit_id": materials.launch_receipt[
            "repository_commit_id"
        ],
        "union_tree_sha256": materials.execution_receipt["union_tree"]["sha256"],
        "union_sources_sha256": materials.execution_receipt[
            "union_sources_sha256"
        ],
        "v5_reusable_tree_sha256": materials.execution_receipt[
            "v5_reusable_tree"
        ]["sha256"],
        "v7_output_tree_sha256": materials.execution_receipt[
            "v7_output_tree"
        ]["sha256"],
        "v5_launch_receipt_sha256": materials.execution_receipt[
            "v5_launch_receipt_sha256"
        ],
        "v5_code_manifest_sha256": materials.execution_receipt[
            "v5_code_manifest_sha256"
        ],
        "reused_v5_shards": materials.execution_receipt["reused_v5_shards"],
        "repaired_v5_shards": materials.execution_receipt["repaired_v5_shards"],
        "reused_v6_shards": materials.execution_receipt["reused_v6_shards"],
        "source_support_outcome_blind_selective_repair": (
            materials.execution_receipt[
                "source_support_outcome_blind_selective_repair"
            ]
        ),
        "v5_reusable_triplet_bytes_read_during_seal_after_v7_all_success_gate": (
            materials.execution_receipt[
                "v5_reusable_triplet_bytes_read_during_seal_after_v7_all_success_gate"
            ]
        ),
        "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion": (
            materials.execution_receipt[
                "v5_reusable_selected_tree_contemporaneously_externally_committed_at_v5_completion"
            ]
        ),
        "v5_reusable_selected_tree_first_separately_recorded_at_v7_seal": (
            materials.execution_receipt[
                "v5_reusable_selected_tree_first_separately_recorded_at_v7_seal"
            ]
        ),
        "scheduler_membership_affects_execution_origin_only": (
            materials.execution_receipt[
                "scheduler_membership_affects_execution_origin_only"
            ]
        ),
        "v6_runtime_artifacts_used": materials.execution_receipt[
            "v6_runtime_artifacts_used"
        ],
        "accepted_translation_statuses": materials.execution_receipt[
            "accepted_translation_statuses"
        ],
        "translator_timeout_is_infrastructure_failure": (
            materials.execution_receipt[
                "translator_timeout_is_infrastructure_failure"
            ]
        ),
        "resource_ceiling_changes_accepted_outcome_classes": (
            materials.execution_receipt[
                "resource_ceiling_changes_accepted_outcome_classes"
            ]
        ),
        "slurm_template_sha256": materials.launch_receipt[
            "slurm_template_sha256"
        ],
        **v7_recovery_provenance(materials.execution_receipt),
        "tracked_file_sha256": materials.tracked_file_sha256,
    }
    if intent_path != materials.intent_path or sources != expected_sources:
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
        set(planner) != set(required_planner) | {"build_options"}
        or
        COMMIT_RE.fullmatch(planner.get("revision", "")) is None
        or planner.get("revision") != PLANNER_REVISION_REQUIRED
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
        "FREEZE_REPOSITORY_REVISION": "TO_FREEZE",
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
        "SOURCE_AUDIT_TERMINAL_DIAGNOSTIC_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_V5_LAUNCH_RECEIPT_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_V5_CODE_MANIFEST_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_UNION_SOURCES_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_V5_REUSABLE_TREE_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_V7_OUTPUT_TREE_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_PRE_DIAGNOSIS_REPOSITORY_COMMIT_ID": "TO_FREEZE",
        "SOURCE_AUDIT_PRE_DIAGNOSIS_FILES_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_SEAL_PLAN_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_UNION_ROOT_STAGE_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_UNION_STAGE_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_CANDIDATE_STAGE_SHA256": "TO_FREEZE",
        "SOURCE_AUDIT_ATTESTATION_STAGE_SHA256": "TO_FREEZE",
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
        "FREEZE_REPOSITORY_REVISION": freeze["freeze_repository_revision"],
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
        "SOURCE_AUDIT_CODE_MANIFEST_SHA256": execution[
            "v7_code_manifest_sha256"
        ],
        "SOURCE_AUDIT_TERMINAL_DIAGNOSTIC_SHA256": (
            materials.diagnostic_sha256
        ),
        "SOURCE_AUDIT_V5_LAUNCH_RECEIPT_SHA256": execution[
            "v5_launch_receipt_sha256"
        ],
        "SOURCE_AUDIT_V5_CODE_MANIFEST_SHA256": execution[
            "v5_code_manifest_sha256"
        ],
        "SOURCE_AUDIT_UNION_SOURCES_SHA256": execution[
            "union_sources_sha256"
        ],
        "SOURCE_AUDIT_V5_REUSABLE_TREE_SHA256": execution[
            "v5_reusable_tree"
        ]["sha256"],
        "SOURCE_AUDIT_V7_OUTPUT_TREE_SHA256": execution[
            "v7_output_tree"
        ]["sha256"],
        "SOURCE_AUDIT_PRE_DIAGNOSIS_REPOSITORY_COMMIT_ID": execution[
            "pre_diagnosis_freeze"
        ]["repository_commit_id"],
        "SOURCE_AUDIT_PRE_DIAGNOSIS_FILES_SHA256": execution[
            "pre_diagnosis_freeze"
        ]["files_sha256"],
        "SOURCE_AUDIT_SEAL_PLAN_SHA256": execution["seal_plan_sha256"],
        "SOURCE_AUDIT_UNION_ROOT_STAGE_SHA256": execution[
            "union_root_stage_sha256"
        ],
        "SOURCE_AUDIT_UNION_STAGE_SHA256": execution["union_stage_sha256"],
        "SOURCE_AUDIT_CANDIDATE_STAGE_SHA256": execution[
            "candidate_stage_sha256"
        ],
        "SOURCE_AUDIT_ATTESTATION_STAGE_SHA256": execution[
            "attestation_stage_sha256"
        ],
        "SOURCE_AUDIT_REPOSITORY_COMMIT_ID": launch["repository_commit_id"],
        "SOURCE_AUDIT_OUTPUT_TREE_SHA256": execution["union_tree"]["sha256"],
        "SOURCE_AUDIT_SLURM_SHA256": launch["slurm_template_sha256"],
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
