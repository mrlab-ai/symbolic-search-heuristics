#!/usr/bin/env python3
"""Frozen, outcome-blind protocol for the dual terminal-metric campaign.

Importing this module is side-effect free.  In particular, it does not inspect
the sealed Confirmation A/B artifacts.  The Confirmation B verifier is
imported only by :func:`snapshot_sealed_b` while constructing the direct
freeze; production cohort loading uses only the embedded guided-B projection.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import math
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdb_confirmation_safe_io as SafeIO
import pdb_confirmation_run_cell as RunCell
import pdb_terminal_metric_choice_io as CampaignIO


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).parent
REPO = SCRIPT_DIR.parent
PROTOCOL_PATH = SCRIPT_DIR / "pdb_terminal_metric_choice_protocol.md"
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "pdb-terminal-metric-choice"
FREEZE_PATH = ARTIFACT_DIR / "freeze-v1.json"
CALIBRATION_RECEIPT_PATH = ARTIFACT_DIR / "calibration-receipt-v1.json"
PLANNER_MANIFEST_PATH = ARTIFACT_DIR / "planner-manifest-v1.json"
STANDALONE_K32_PATH = ARTIFACT_DIR / "standalone-k32-v1.json"
BASE_CONFIRMATION_ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation"
)
BASE_A_ARTIFACT_DIR = BASE_CONFIRMATION_ARTIFACT_DIR / "confirmation-a"
BASE_A_RECEIPT_PATH = BASE_A_ARTIFACT_DIR / "analysis-execution-receipt-v4.json"
BASE_A_RECEIPT_PIN_PATH = BASE_A_ARTIFACT_DIR / "analysis-execution-receipt-v4.sha256"
BASE_A_FIRST_OUTPUT_PATH = BASE_A_ARTIFACT_DIR / "analysis-v4.json"
BASE_A_SECOND_OUTPUT_PATH = BASE_A_ARTIFACT_DIR / "analysis-v4-repeat.json"
BASE_A_FREEZE_PATH = (
    BASE_CONFIRMATION_ARTIFACT_DIR / "confirmation-a-freeze-v1.json"
)
BASE_A_RECEIPT_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-a-analysis/v4/double-execution"
)
BASE_A_ANALYSIS_PROTOCOL = "pdb-terminal-incidence-confirmation-a-analysis-v4"
BASE_A_CELL_COUNT = 2600
BASE_B_FREEZE_PATH = BASE_CONFIRMATION_ARTIFACT_DIR / "confirmation-b-freeze-v1.json"
BASE_B_ARTIFACT_DIR = BASE_CONFIRMATION_ARTIFACT_DIR / "confirmation-b"
BASE_B_PARSE_RECEIPT_PATH = BASE_B_ARTIFACT_DIR / "parse-receipt-v1.json"
BASE_B_FETCH_RECEIPT_PATH = BASE_B_ARTIFACT_DIR / "fetch-receipt-v1.json"
BASE_B_PROPERTIES_PATH = (
    SCRIPT_DIR / "data" / "exp_pdb_terminal_incidence_confirmation_b-eval" /
    "properties"
)
CALIBRATION_DRIVER_PATH = REPO / "fast-downward.py"
FREEZE_SCHEMA = (
    "symbolic-search-heuristics/pdb-terminal-metric-choice-freeze/v1"
)
BASE_SNAPSHOT_SCHEMA = FREEZE_SCHEMA + "/sealed-confirmation-b-snapshot"
V11_SOURCE_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-b-source/v1/campaign-v11"
)
V11_ADAPTER_SCHEMA = (
    "symbolic-search-heuristics/"
    "universal-unseen-confirmation-source-adapter/v1/campaign-v11"
)
CALIBRATION_SCHEMA = (
    "symbolic-search-heuristics/pdb-terminal-metric-choice-calibration/v1"
)
STANDALONE_SCHEMA = (
    "symbolic-search-heuristics/pdb-terminal-metric-choice-standalone-k32/v1"
)
PLANNER_MANIFEST_SCHEMA = FREEZE_SCHEMA + "/planner-manifest"
PROTOCOL = "pdb-terminal-metric-choice-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-terminal-metric-choice-analysis-v4"
REQUIRED_PLANNER_REVISION = "8148f798f13059ee881ad2471bd20cdd61d2ec18"
REQUIRED_SELECTOR_COMMIT = "ccc93bed78d4aa864c2e27d68d80461c1c20807c"
DUAL_TRACE_SCHEMA = (
    "symbolic-search-heuristics/terminal-dual-metric-selector-trace/v2"
)
DUAL_TRACE_PROTOCOL = "terminal_dual_metric_fixed_pool_v1"
SELECTOR_TRACE = "dual-selector.jsonl"
CANDIDATE_SOURCES = (
    "empty", "bdd_prefix", "goal_prefix", "goal_fill", "cegar",
)
VALUE_CAP_GRID = (0, 1, 2, 4, 8, 16, 32, 64, 128, 256, None)

MODES = (
    "terminal_dual_incidence_guided",
    "terminal_dual_mj_guided",
    "terminal_dual_matched_control",
)
INCIDENCE_MODE, MJ_MODE, MATCHED_MODE = MODES
CONFIG_COUNT = 3
COHORT_TASKS = 300
CELL_COUNT = 900
RUNS_PER_ARRAY_TASK = 3
EXPECTED_ARRAY_TASKS = 300
RUN_ORDER_PROTOCOL = "task-major-family-cyclic-dual-triads/v1"

PROBE_LAYERS = 16
REFERENCE_COFACTOR_WIDTH_BUDGET = 32
TIME_LIMIT_SECONDS = 1800
MEMORY_LIMIT_MIB = 24576
ACCOUNT = "naiss2025-5-561-cpu"
BUILD_OPTIONS = ("release_no_lp",)
REQUIRED_LAB_VERSION = "8.10"
REQUIRED_PYTHON_VERSION = "3.12.13"
PAR2_SECONDS = 3600
MIN_NORMALIZED_PAR2_IMPROVEMENT_NUMERATOR = 1
MIN_NORMALIZED_PAR2_IMPROVEMENT_DENOMINATOR = 50
BOOTSTRAP_REPLICATES = 100000
BOOTSTRAP_SEED = 20260903
MIN_DIFFERING_WINNER_TASKS = 50
MIN_DIFFERING_WINNER_FAMILIES = 10
CALIBRATION_TASK_SPECS = (
    ("__metric_choice_calibration__/chain-19", 19),
    ("__metric_choice_calibration__/chain-23", 23),
    ("__metric_choice_calibration__/chain-29", 29),
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
V11_TRANSLATOR_FILE_COUNT = 38
V11_CODE_MANIFEST_RELATIVE = (
    "experiments/"
    "pdb_terminal_incidence_confirmation_source_audit_v11_code.sha256"
)
V11_SHADOW_FAMILIES = frozenset({
    "agricola", "barman", "caldera", "cavediving", "childsnack",
    "floortile", "hiking", "maintenance", "miconic", "nomystery",
    "nurikabe", "openstacks", "organic-synthesis", "parking",
    "quantum-layout", "rubiks-cube", "schedule", "slitherlink", "snake",
    "termes", "tetris", "thoughtful", "tidybot", "transport", "visitall",
    "woodworking",
})
V11_ALL_PRIOR_FAMILIES = frozenset({
    "agricola", "airport", "barman", "blocks", "caldera", "cavediving",
    "childsnack", "depot", "driverlog", "elevators", "floortile",
    "freecell", "ged", "grid", "gripper", "hiking", "logistics",
    "maintenance", "miconic", "movie", "mprime", "mystery", "nomystery",
    "nurikabe", "openstacks", "organic-synthesis", "parcprinter", "parking",
    "pathways", "pegsol", "pipesworld", "psr", "quantum-layout", "rovers",
    "rubiks-cube", "satellite", "scanalyzer", "schedule", "slitherlink",
    "snake", "sokoban", "storage", "termes", "tetris", "thoughtful",
    "tidybot", "tpp", "transport", "trucks", "visitall", "woodworking",
    "zenotravel",
})
V11_A_MIN_FAMILIES = 28
V11_A_MIN_SHADOW_UNREPRESENTED_FAMILIES = 12
V11_A_MIN_ALL_PRIOR_UNREPRESENTED_TASKS = 100
V11_A_MIN_ALL_PRIOR_UNREPRESENTED_FAMILIES = 10
V11_B_MIN_FAMILIES = 30
V11_B_MIN_SHADOW_UNREPRESENTED_FAMILIES = 12
V11_B_MIN_ALL_PRIOR_UNREPRESENTED_TASKS = 50
V11_B_MIN_ALL_PRIOR_UNREPRESENTED_FAMILIES = 10
V11_B_MAX_TASKS_PER_FAMILY = 12
V11_SUPPORT_STATUS_KEYS = (
    "indeterminate", "supported", "unsupported",
)
V11_SUPPORT_EXCLUSION_REASONS = (
    "translation-input-rejected", "no-serialized-operators",
    "nonpositive-serialized-operator-cost", "serialized-axioms",
    "serialized-conditional-effects", "normalized-axioms",
)
V11_RESOURCE_EXCLUSION_KEYS = ("memory", "time")

V11_BINDING_FIELDS = (
    "schema", "campaign", "benchmark_revision", "seal_repository_commit_id",
    "preflight_campaign", "preflight_source_repository_commit_id",
    "preflight_seal_repository_commit_id", "preflight_full_launch_authorized",
    "source_inventory_sha256", "code_manifest_sha256",
    "preflight_code_manifest_sha256", "launch_receipt_sha256",
    "execution_receipt_sha256", "attestation_sha256",
    "preflight_authorization_sha256",
    "controller_publisher_canary_receipt_sha256",
    "compute_canary_launch_receipt_sha256",
    "compute_canary_terminal_poll_receipt_sha256",
    "compute_canary_seal_plan_sha256", "compute_canary_attestation_sha256",
    "translator_source_sha256", "inventory_families_count",
    "translation_attempts_count", "all_records_count", "all_records_sha256",
    "all_source_projection_sha256", "eligible_records_count",
    "eligible_records_sha256", "eligible_candidate_indices_sha256",
    "eligible_source_projection_sha256", "confirmation_a_count",
    "confirmation_a_candidate_indices_sha256",
    "confirmation_a_source_projection_sha256", "guided_b_count",
    "guided_b_candidate_indices_sha256", "guided_b_source_projection_sha256",
    "outcome_counts", "outcome_counts_sha256", "support_status_counts",
    "support_status_counts_sha256", "support_exclusion_counts",
    "support_exclusion_counts_sha256", "resource_exclusion_counts",
    "resource_exclusion_counts_sha256", "resource_exclusions_by_family",
    "resource_exclusions_by_family_sha256", "full_tracked_file_sha256",
    "full_tracked_file_sha256_digest", "preflight_tracked_file_sha256",
    "preflight_tracked_file_sha256_digest", "combined_tracked_file_sha256",
    "combined_tracked_file_sha256_digest",
)
V11_TRACKED_BINDING_FIELDS = (
    "full_tracked_file_sha256", "preflight_tracked_file_sha256",
    "combined_tracked_file_sha256",
)
V11_COMMIT_BINDING_FIELDS = (
    "preflight_source_repository_commit_id",
    "preflight_seal_repository_commit_id", "seal_repository_commit_id",
)
V11_RUN_PROVENANCE_FIELDS = (
    "source_audit_campaign", "source_audit_launch_receipt_sha256",
    "source_audit_execution_receipt_sha256",
    "source_audit_code_manifest_sha256", "source_audit_repository_commit_id",
    "source_audit_source_repository_commit_id",
    "source_audit_preflight_seal_repository_commit_id",
    "source_audit_seal_repository_commit_id", "source_audit_inventory_sha256",
    "source_audit_preflight_authorization_sha256",
    "source_audit_controller_canary_sha256",
    "source_audit_compute_canary_launch_sha256",
    "source_audit_compute_canary_terminal_poll_receipt_sha256",
    "source_audit_compute_canary_seal_sha256",
    "source_audit_compute_canary_attestation_sha256",
    "source_audit_full_tracked_closure_sha256",
    "source_audit_preflight_tracked_closure_sha256",
    "source_audit_combined_tracked_closure_sha256",
    "source_audit_all_records_sha256",
    "source_audit_confirmation_a_indices_sha256",
    "source_audit_confirmation_a_projection_sha256",
    "source_audit_guided_b_indices_sha256",
    "source_audit_guided_b_projection_sha256", "confirmation_a_freeze_sha256",
)
V11_SOURCE_PROJECTION_FIELDS = (
    "candidate_index", "directory", "family", "problem", "domain_file",
    "problem_file", "domain_sha256", "problem_sha256", "canonical_path",
    "is_shadow_family", "is_shadow_unrepresented", "is_all_prior_represented",
    "is_all_prior_unrepresented", "aliases",
)
V11_ALIAS_FIELDS = (
    "directory", "family", "problem", "domain_file", "problem_file",
    "domain_sha256", "problem_sha256",
)

BASE_B_EXPERIMENT_SOURCE_FILES = (
    "experiments/analyze_pdb_terminal_incidence_confirmation_a.py",
    "experiments/analyze_pdb_terminal_incidence_confirmation_b.py",
    "experiments/analyze_pdb_terminal_incidence_shadow.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_a.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_b.py",
    "experiments/audit_pdb_terminal_incidence_shadow.py",
    "experiments/exp_arrhenius_common.py",
    "experiments/exp_pdb_profile_certificate_holdout.py",
    "experiments/exp_pdb_terminal_incidence_confirmation_a.py",
    "experiments/exp_pdb_terminal_incidence_confirmation_b.py",
    "experiments/freeze_pdb_terminal_incidence_confirmation_b.py",
    "experiments/jj_cached_revision.py",
    "experiments/pdb_cap_selector_parser.py",
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
    "experiments/pdb_terminal_incidence_confirmation_b_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_b_protocol.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v11.py",
    "experiments/pdb_terminal_incidence_confirmation_v11_adapter.py",
    "experiments/pdb_terminal_incidence_selector_parser.py",
    "experiments/pdb_terminal_incidence_v11_snapshot_reader.py",
    "experiments/pdb_terminal_incidence_shadow_protocol.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_b.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/validate_wbh_log.py",
    "experiments/wbh_parser.py",
)

SOURCE_FILES = (
    "experiments/pdb_confirmation_safe_io.py",
    "experiments/pdb_terminal_metric_choice_io.py",
    "experiments/pdb_terminal_metric_choice_transport.py",
    "experiments/pdb_confirmation_run_cell.py",
    "experiments/exp_pdb_profile_certificate_holdout.py",
    "experiments/jj_cached_revision.py",
    "experiments/pdb_profile_comparison_parser.py",
    "experiments/wbh_parser.py",
    "experiments/pdb_terminal_metric_choice_protocol.py",
    "experiments/pdb_terminal_metric_choice_planner_manifest.py",
    "experiments/pdb_terminal_metric_choice_freeze.py",
    "experiments/pdb_terminal_metric_choice_runner.py",
    "experiments/pdb_terminal_metric_choice_execution.py",
    "experiments/pdb_terminal_metric_choice_audit.py",
    "experiments/pdb_terminal_metric_choice_recovery.py",
    "experiments/pdb_terminal_metric_choice_standalone.py",
    "experiments/pdb_terminal_metric_choice_analyzer.py",
    "experiments/pdb_terminal_metric_choice_parser.py",
    "experiments/pdb_terminal_metric_choice_calibration.py",
    "experiments/pdb_terminal_metric_choice_protocol.md",
    "experiments/pdb_terminal_metric_choice_requirements.txt",
    "experiments/pdb_terminal_incidence_confirmation_a_protocol.py",
    "experiments/pdb_terminal_incidence_confirmation_b_protocol.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v11.py",
    "experiments/pdb_terminal_incidence_confirmation_v11_adapter.py",
    "experiments/pdb_terminal_incidence_v11_snapshot_reader.py",
    "experiments/test_pdb_terminal_metric_choice_protocol.py",
    "experiments/test_pdb_terminal_metric_choice_planner_manifest.py",
    "experiments/test_pdb_terminal_metric_choice_parser.py",
    "experiments/test_pdb_terminal_metric_choice_analyzer.py",
    "experiments/test_pdb_terminal_metric_choice_execution.py",
    "experiments/test_pdb_terminal_metric_choice_standalone.py",
    "experiments/test_pdb_terminal_metric_choice_calibration.py",
    "experiments/test_pdb_terminal_metric_choice_hardening.py",
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


def sha256_file(
    path: Path, *, expected_path: Path | None = None,
    root: Path | None = None, label: str = "campaign file",
) -> str:
    try:
        loaded = SafeIO.read_regular_file(
            Path(path), label=label,
            expected_path=(Path(path) if expected_path is None else expected_path),
            root=root,
        )
    except SafeIO.SafeReadError as err:
        raise ProtocolError(str(err)) from err
    return loaded.sha256


def load_canonical(
    path: Path, label: str, *, expected_path: Path,
) -> tuple[bytes, dict]:
    try:
        loaded, value = CampaignIO.read_canonical_exact(
            Path(path), expected=Path(expected_path), label=label,
            canonical_json_line=canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise ProtocolError(str(err)) from err
    return loaded.raw, value


def _safe_repo_path(value: str, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ProtocolError("{} path is invalid".format(label))
    relative = Path(value)
    if (
        relative.is_absolute() or ".." in relative.parts
        or relative.as_posix() != value or value.startswith("./")
    ):
        raise ProtocolError("{} path escapes the repository".format(label))
    path = REPO / relative
    try:
        SafeIO.validate_lexical_path(path, label=label, root=REPO)
    except SafeIO.SafeReadError as err:
        raise ProtocolError("{} path escapes the repository".format(label)) from err
    return path


def _safe_experiment_path(value: str, label: str) -> Path:
    path = _safe_repo_path(value, label)
    if Path(value).parts[:1] != ("experiments",):
        raise ProtocolError("{} is outside experiments".format(label))
    return path


def _task_identity(task) -> tuple[str, str, str]:
    if isinstance(task, dict):
        domain = task.get("directory", task.get("domain"))
        problem = task.get("problem")
        family = task.get("family")
    else:
        domain = getattr(task, "domain", None)
        problem = getattr(task, "problem", None)
        family = getattr(task, "family", None)
    if not all(isinstance(value, str) and value for value in (
        domain,
        problem,
        family,
    )):
        raise ProtocolError("task identity is incomplete")
    return domain, problem, family


def cohort_digest(tasks) -> str:
    return hashlib.sha256(canonical_json_line(list(tasks))).hexdigest()


def task_name_digest(tasks) -> str:
    payload = "".join(
        "{}:{}\n".format(domain, problem)
        for domain, problem, _ in sorted(_task_identity(task) for task in tasks)
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _dual_search(mode: str) -> str:
    if mode not in MODES:
        raise ProtocolError("unknown dual selector mode")
    options = (
        "budget=100000",
        "pattern_selection={}".format(mode),
        "cegar_max_time=infinity",
        "cegar_max_refinements=128",
        "cegar_seed=2011",
        "cofactor_width_budget=infinity",
        "total_add_node_budget=infinity",
        "value_cap=-1",
        "select_value_cap=false",
        "gamer_ordering=false",
        "dynamic_reordering=false",
        "shadow_partition=false",
        "prune_only=false",
        "batch_f_window=0",
        'incidence_selector_log="{}"'.format(SELECTOR_TRACE),
    )
    return "sym_fw_pdb({})".format(",".join(options))


CONFIGS = tuple((mode, _dual_search(mode)) for mode in MODES)
LABELS = MODES
SEARCHES = dict(CONFIGS)


def option_matrix_digest(configs=CONFIGS) -> str:
    return hashlib.sha256(canonical_json([
        {"label": label, "search": search} for label, search in configs
    ])).hexdigest()


def task_major_cell_mapping(tasks) -> list[dict]:
    identities = sorted(_task_identity(task) for task in tasks)
    if len(identities) != len(set(
        (domain, problem) for domain, problem, _ in identities
    )):
        raise ProtocolError("cohort task identity is duplicated")
    family_positions = Counter()
    rows = []
    for array_task, (domain, problem, family) in enumerate(identities, 1):
        family_index = family_positions[family]
        family_positions[family] += 1
        rotation = family_index % CONFIG_COUNT
        order = MODES[rotation:] + MODES[:rotation]
        for triad_position, mode in enumerate(order):
            rows.append({
                "run_id": len(rows) + 1,
                "array_task": array_task,
                "algorithm": mode,
                "domain": domain,
                "problem": problem,
                "family": family,
                "family_sequence_index": family_index,
                "triad_position": triad_position,
            })
    return rows


def run_cell_mapping_digest(tasks) -> str:
    return hashlib.sha256(canonical_json(task_major_cell_mapping(tasks))).hexdigest()


def task_major_blocked_run_order(algorithms, tasks):
    if tuple(algorithms) != LABELS:
        raise ProtocolError("algorithm insertion order changed")
    task_by_identity = {}
    for task in tasks:
        domain, problem, _ = _task_identity(task)
        identity = (domain, problem)
        if identity in task_by_identity:
            raise ProtocolError("cohort task identity is duplicated")
        task_by_identity[identity] = task
    return [
        (
            algorithms[row["algorithm"]],
            task_by_identity[(row["domain"], row["problem"])],
        )
        for row in task_major_cell_mapping(tasks)
    ]


def triad_cells(array_task: int) -> tuple[int, int, int]:
    if type(array_task) is not int or not 1 <= array_task <= EXPECTED_ARRAY_TASKS:
        raise ProtocolError("array task is out of range")
    first = (array_task - 1) * RUNS_PER_ARRAY_TASK + 1
    return first, first + 1, first + 2


def validate_static_design() -> None:
    if any((
        LABELS != MODES,
        CONFIG_COUNT != 3,
        COHORT_TASKS != 300,
        CELL_COUNT != 900,
        EXPECTED_ARRAY_TASKS != 300,
        RUNS_PER_ARRAY_TASK != 3,
        len(set(SEARCHES.values())) != 3,
        option_matrix_digest() == "",
        PROBE_LAYERS != 16,
        REFERENCE_COFACTOR_WIDTH_BUDGET != 32,
        PAR2_SECONDS != 3600,
        MIN_DIFFERING_WINNER_TASKS != 50,
        MIN_DIFFERING_WINNER_FAMILIES != 10,
        BASE_A_CELL_COUNT != 2600,
    )):
        raise ProtocolError("dual metric static design changed")
    for mode, search in CONFIGS:
        required = (
            "pattern_selection={}".format(mode),
            "budget=100000",
            "cegar_seed=2011",
            "cegar_max_time=infinity",
            "cegar_max_refinements=128",
            "dynamic_reordering=false",
            "value_cap=-1",
            "select_value_cap=false",
            "cofactor_width_budget=infinity",
            "total_add_node_budget=infinity",
            "shadow_partition=false",
            "prune_only=false",
            "batch_f_window=0",
            'incidence_selector_log="{}"'.format(SELECTOR_TRACE),
        )
        if any(search.count(item) != 1 for item in required):
            raise ProtocolError("dual selector option contract changed")


def _require_sha(value, label: str) -> None:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise ProtocolError("{} SHA-256 is invalid".format(label))


def calibration_resource_recommendation(observations: list[dict]) -> dict:
    """Derive the only allowed scheduler recommendation from redacted data."""
    if not isinstance(observations, list) or not observations:
        raise ProtocolError("calibration observations are absent")
    try:
        selector_wall = max(row["selection_wall_seconds"] for row in observations)
        selector_memory = max(
            row["selection_peak_memory_delta_kb"] for row in observations
        )
    except (KeyError, TypeError, ValueError) as err:
        raise ProtocolError("calibration resource observations are invalid") from err
    if any(
        type(value) not in (int, float) or not math.isfinite(value) or value < 0
        for value in (selector_wall, selector_memory)
    ):
        raise ProtocolError("calibration resource observations are invalid")
    return {
        "minimum_selector_wall_seconds": math.ceil(selector_wall * 2),
        "minimum_selector_peak_delta_kb": math.ceil(selector_memory * 2),
    }


def scheduler_resource_floor(recommendation: dict) -> tuple[int, int]:
    if not isinstance(recommendation, dict) or set(recommendation) != {
        "minimum_selector_wall_seconds", "minimum_selector_peak_delta_kb",
    } or any(type(value) is not int or value < 0
             for value in recommendation.values()):
        raise ProtocolError("calibration resource recommendation is invalid")
    time_seconds = CONFIG_COUNT * max(
        TIME_LIMIT_SECONDS, recommendation["minimum_selector_wall_seconds"]
    )
    memory_mib = max(
        MEMORY_LIMIT_MIB,
        math.ceil(recommendation["minimum_selector_peak_delta_kb"] / 1024),
    )
    return time_seconds, memory_mib


def validate_frozen_resources(
    time_limit: str, memory: str, recommendation: dict,
) -> None:
    if not isinstance(time_limit, str) or not isinstance(memory, str):
        raise ProtocolError("frozen scheduler resource syntax changed")
    time_match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2})", time_limit)
    memory_match = re.fullmatch(r"([1-9]\d*)([MG])", memory)
    if time_match is None or memory_match is None:
        raise ProtocolError("frozen scheduler resource syntax changed")
    hours, minutes, seconds = map(int, time_match.groups())
    total_seconds = hours * 3600 + minutes * 60 + seconds
    memory_value = int(memory_match.group(1))
    memory_mib = memory_value * (1024 if memory_match.group(2) == "G" else 1)
    minimum_time, minimum_memory = scheduler_resource_floor(recommendation)
    if any((
        minutes >= 60, seconds >= 60,
        total_seconds < minimum_time,
        memory_mib < minimum_memory,
    )):
        raise ProtocolError("frozen scheduler resources cannot cover one triad")


PLANNER_IDENTITY_FIELDS = (
    "revision", "cache_name", "build_options", "downward_sha256",
    "preprocess_sha256", "tree_manifest_sha256",
)


def planner_identity(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ProtocolError("planner identity source is invalid")
    return {field: value.get(field) for field in PLANNER_IDENTITY_FIELDS}


def validate_planner_identity(value: dict) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != set(PLANNER_IDENTITY_FIELDS)
        or value.get("revision") != REQUIRED_PLANNER_REVISION
        or not isinstance(value.get("cache_name"), str)
        or not value["cache_name"]
        or value.get("build_options") != list(BUILD_OPTIONS)
    ):
        raise ProtocolError("sealed planner identity changed")
    for field in (
        "downward_sha256", "preprocess_sha256", "tree_manifest_sha256",
    ):
        _require_sha(value.get(field), "sealed planner {}".format(field))


def _require_commit40(value, label: str) -> None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ProtocolError("{} commit is invalid".format(label))


def _validate_v11_tracked(value, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value:
        raise ProtocolError("{} tracked closure is absent".format(label))
    for relative, digest in value.items():
        _safe_repo_path(relative, label + " tracked source")
        _require_sha(digest, label + " tracked source")
    return dict(sorted(value.items()))


def _validate_v11_bindings(bindings: dict) -> None:
    if not isinstance(bindings, dict) or set(bindings) != set(V11_BINDING_FIELDS):
        raise ProtocolError("V11 source binding shape changed")
    for field in V11_COMMIT_BINDING_FIELDS:
        _require_commit40(bindings.get(field), "V11 " + field)
    commits = tuple(bindings[field] for field in V11_COMMIT_BINDING_FIELDS)
    hash_fields = {
        field for field in V11_BINDING_FIELDS
        if field.endswith("_sha256") or field.endswith("_sha256_digest")
    } - set(V11_TRACKED_BINDING_FIELDS)
    for field in hash_fields:
        _require_sha(bindings.get(field), "V11 " + field)
    if any((
        bindings.get("schema") != V11_ADAPTER_SCHEMA,
        bindings.get("campaign") != "v11-full-census",
        bindings.get("preflight_campaign") != "v11-preflight",
        bindings.get("benchmark_revision")
        != "48d6a00d482de2384a9e751f9343df58bf5582be",
        bindings.get("preflight_full_launch_authorized") is not True,
        len(set(commits)) != len(commits),
        bindings.get("code_manifest_sha256")
        != bindings.get("preflight_code_manifest_sha256"),
        type(bindings.get("all_records_count")) is not int,
        bindings.get("all_records_count") != 1640,
        type(bindings.get("inventory_families_count")) is not int,
        not 1 <= bindings.get("inventory_families_count", 0) <= 1640,
        type(bindings.get("translation_attempts_count")) is not int,
        bindings.get("translation_attempts_count") != 1640,
        type(bindings.get("eligible_records_count")) is not int,
        not 950 <= bindings.get("eligible_records_count", -1) <= 1640,
        bindings.get("confirmation_a_count") != 650,
        bindings.get("guided_b_count") != COHORT_TASKS,
    )):
        raise ProtocolError("V11 source authorization changed")
    outcome_counts = bindings.get("outcome_counts")
    if (
        not isinstance(outcome_counts, dict)
        or set(outcome_counts) != {"input-rejected", "resource-excluded", "success"}
        or any(type(value) is not int or value < 0
               for value in outcome_counts.values())
        or sum(outcome_counts.values()) != 1640
        or hashlib.sha256(canonical_json(outcome_counts)).hexdigest()
        != bindings["outcome_counts_sha256"]
    ):
        raise ProtocolError("V11 source outcome summary changed")
    summary_keys = {
        "support_status_counts": set(V11_SUPPORT_STATUS_KEYS),
        "support_exclusion_counts": set(V11_SUPPORT_EXCLUSION_REASONS),
        "resource_exclusion_counts": set(V11_RESOURCE_EXCLUSION_KEYS),
    }
    for name, keys in summary_keys.items():
        value = bindings.get(name)
        if (
            not isinstance(value, dict) or set(value) != keys
            or any(type(value[key]) is not int or value[key] < 0 for key in keys)
            or hashlib.sha256(canonical_json(value)).hexdigest()
            != bindings[name + "_sha256"]
        ):
            raise ProtocolError("V11 source classification summary changed")
    exclusions = bindings.get("resource_exclusions_by_family")
    if (
        not isinstance(exclusions, dict)
        or len(exclusions) > bindings["inventory_families_count"]
    ):
        raise ProtocolError("V11 resource-exclusion summary changed")
    excluded = 0
    for family, counts in exclusions.items():
        if (
            not isinstance(family, str) or not family
            or not isinstance(counts, dict)
            or set(counts) != {"memory", "time", "total"}
            or any(type(value) is not int or value < 0
                   for value in counts.values())
            or counts["total"] != counts["memory"] + counts["time"]
            or counts["total"] == 0
        ):
            raise ProtocolError("V11 resource-exclusion summary changed")
        excluded += counts["total"]
    if (
        excluded != outcome_counts["resource-excluded"]
        or hashlib.sha256(canonical_json(exclusions)).hexdigest()
        != bindings["resource_exclusions_by_family_sha256"]
    ):
        raise ProtocolError("V11 resource-exclusion summary changed")
    support_status = bindings["support_status_counts"]
    support_exclusions = bindings["support_exclusion_counts"]
    resource_counts = bindings["resource_exclusion_counts"]
    unsupported_success = (
        support_status["unsupported"] - outcome_counts["input-rejected"]
    )
    structural_counts = [
        support_exclusions[reason]
        for reason in V11_SUPPORT_EXCLUSION_REASONS[1:]
    ]
    aggregated_resource_counts = {
        key: sum(counts[key] for counts in exclusions.values())
        for key in V11_RESOURCE_EXCLUSION_KEYS
    }
    if any((
        sum(support_status.values()) != bindings["all_records_count"],
        support_status["supported"] != bindings["eligible_records_count"],
        support_status["indeterminate"]
        != outcome_counts["resource-excluded"],
        support_exclusions["translation-input-rejected"]
        != outcome_counts["input-rejected"],
        unsupported_success < 0,
        any(count > unsupported_success for count in structural_counts),
        sum(structural_counts) < unsupported_success,
        sum(resource_counts.values()) != outcome_counts["resource-excluded"],
        resource_counts != aggregated_resource_counts,
    )):
        raise ProtocolError("V11 source classification summary is incoherent")
    tracked = {
        field: _validate_v11_tracked(bindings[field], "V11 " + field)
        for field in V11_TRACKED_BINDING_FIELDS
    }
    if any(
        tracked[field].get(V11_CODE_MANIFEST_RELATIVE)
        != bindings["code_manifest_sha256"]
        for field in (
            "full_tracked_file_sha256", "preflight_tracked_file_sha256",
        )
    ):
        raise ProtocolError("V11 code-manifest closure changed")
    for field in V11_TRACKED_BINDING_FIELDS:
        if hashlib.sha256(canonical_json(tracked[field])).hexdigest() != bindings[
            field + "_digest"
        ]:
            raise ProtocolError("V11 tracked-closure digest changed")
    combined = dict(tracked["preflight_tracked_file_sha256"])
    for relative, digest in tracked["full_tracked_file_sha256"].items():
        if relative in combined and combined[relative] != digest:
            raise ProtocolError("V11 tracked closures disagree")
        combined[relative] = digest
    if dict(sorted(combined.items())) != tracked["combined_tracked_file_sha256"]:
        raise ProtocolError("V11 combined tracked closure changed")
    full_translator = {
        relative: digest
        for relative, digest in tracked["full_tracked_file_sha256"].items()
        if relative.startswith("src/translate/") and relative.endswith(".py")
    }
    preflight_translator = {
        relative: digest
        for relative, digest in tracked["preflight_tracked_file_sha256"].items()
        if relative.startswith("src/translate/") and relative.endswith(".py")
    }
    translator = [
        {"path": relative, "sha256": digest}
        for relative, digest in sorted(full_translator.items())
    ]
    if (
        len(full_translator) != V11_TRANSLATOR_FILE_COUNT
        or full_translator != preflight_translator
        or hashlib.sha256(canonical_json(translator)).hexdigest()
        != bindings["translator_source_sha256"]
    ):
        raise ProtocolError("V11 translator source digest changed")


def _validate_v11_source_task(task: dict) -> None:
    if not isinstance(task, dict) or set(task) != set(V11_SOURCE_PROJECTION_FIELDS):
        raise ProtocolError("V11 source task shape changed")
    text_fields = (
        "directory", "family", "problem", "domain_file", "problem_file",
        "canonical_path",
    )
    if (
        type(task.get("candidate_index")) is not int
        or not 0 <= task["candidate_index"] < 1640
        or any(type(task.get(field)) is not str or not task[field]
               for field in text_fields)
        or any(SHA256_RE.fullmatch(task.get(field, "")) is None
               for field in ("domain_sha256", "problem_sha256"))
        or task.get("canonical_path") != task.get("problem_file")
        or any(type(task.get(field)) is not bool for field in (
            "is_shadow_family", "is_shadow_unrepresented",
            "is_all_prior_represented", "is_all_prior_unrepresented",
        ))
        or task["is_shadow_family"] == task["is_shadow_unrepresented"]
        or task["is_all_prior_represented"] == task["is_all_prior_unrepresented"]
        or task["is_shadow_family"] is not (
            task["family"] in V11_SHADOW_FAMILIES
        )
        or task["is_all_prior_represented"] is not (
            task["family"] in V11_ALL_PRIOR_FAMILIES
        )
    ):
        raise ProtocolError("V11 source task changed")
    for field in ("directory", "domain_file", "problem_file"):
        path = Path(task[field])
        if (
            path.is_absolute() or path == Path(".") or ".." in path.parts
            or path.as_posix() != task[field] or task[field].startswith("./")
        ):
            raise ProtocolError("V11 source task path is unsafe")
    if (
        Path(task["problem_file"]) != Path(task["directory"]) / task["problem"]
        or Path(task["domain_file"]).parent != Path(task["directory"])
    ):
        raise ProtocolError("V11 source task identity changed")
    aliases = task.get("aliases")
    alias_fields = set(V11_ALIAS_FIELDS)
    if not isinstance(aliases, list) or not aliases:
        raise ProtocolError("V11 source aliases changed")
    identities = []
    for alias in aliases:
        if (
            not isinstance(alias, dict) or set(alias) != alias_fields
            or any(type(alias.get(field)) is not str or not alias[field]
                   for field in V11_ALIAS_FIELDS)
            or any(SHA256_RE.fullmatch(alias.get(field, "")) is None
                   for field in ("domain_sha256", "problem_sha256"))
            or alias["family"] != task["family"]
            or alias["problem_sha256"] != task["problem_sha256"]
        ):
            raise ProtocolError("V11 source aliases changed")
        for field in ("directory", "domain_file", "problem_file"):
            path = Path(alias[field])
            if (
                path.is_absolute() or path == Path(".") or ".." in path.parts
                or path.as_posix() != alias[field]
                or alias[field].startswith("./")
            ):
                raise ProtocolError("V11 source alias path is unsafe")
        if (
            Path(alias["problem_file"])
            != Path(alias["directory"]) / alias["problem"]
            or Path(alias["domain_file"]).parent != Path(alias["directory"])
        ):
            raise ProtocolError("V11 source alias identity changed")
        identities.append((
            alias["directory"], alias["problem"], alias["problem_file"],
            alias["domain_file"],
        ))
    canonical_alias = {field: task[field] for field in V11_ALIAS_FIELDS}
    if (
        aliases[0] != canonical_alias
        or identities != sorted(identities)
        or len(identities) != len(set(identities))
    ):
        raise ProtocolError("V11 source alias order changed")


def _validate_v11_cohort(
    cohort: dict, role: str, count: int,
) -> tuple[list[dict], dict[str, str]]:
    if not isinstance(cohort, dict) or set(cohort) != {
        "role", "records", "candidate_indices_sha256", "source_projection_sha256",
    } or cohort.get("role") != role:
        raise ProtocolError("{} cohort shape changed".format(role))
    tasks = cohort.get("records")
    if not isinstance(tasks, list) or len(tasks) != count:
        raise ProtocolError("{} cohort cardinality changed".format(role))
    for task in tasks:
        _validate_v11_source_task(task)
    indices = [task["candidate_index"] for task in tasks]
    identities = [(task["directory"], task["problem"]) for task in tasks]
    problem_hashes = [task["problem_sha256"] for task in tasks]
    if (
        len(indices) != len(set(indices))
        or len(identities) != len(set(identities))
        or len(problem_hashes) != len(set(problem_hashes))
        or cohort.get("candidate_indices_sha256")
        != hashlib.sha256(canonical_json(indices)).hexdigest()
        or cohort.get("source_projection_sha256")
        != hashlib.sha256(canonical_json(tasks)).hexdigest()
    ):
        raise ProtocolError("{} cohort digest changed".format(role))
    directory_to_family = {}
    for task in tasks:
        for source in (task, *task["aliases"]):
            previous = directory_to_family.setdefault(
                source["directory"], source["family"]
            )
            if previous != source["family"]:
                raise ProtocolError(
                    "{} directory-to-family ledger changed".format(role)
                )
    families = {task["family"] for task in tasks}
    per_family = Counter(task["family"] for task in tasks)
    shadow_unrepresented = {
        task["family"] for task in tasks
        if task["is_shadow_unrepresented"]
    }
    all_prior_unrepresented = [
        task for task in tasks if task["is_all_prior_unrepresented"]
    ]
    all_prior_unrepresented_families = {
        task["family"] for task in all_prior_unrepresented
    }
    if role == "confirmation-a":
        passed = all((
            len(families) >= V11_A_MIN_FAMILIES,
            len(shadow_unrepresented)
            >= V11_A_MIN_SHADOW_UNREPRESENTED_FAMILIES,
            len(all_prior_unrepresented)
            >= V11_A_MIN_ALL_PRIOR_UNREPRESENTED_TASKS,
            len(all_prior_unrepresented_families)
            >= V11_A_MIN_ALL_PRIOR_UNREPRESENTED_FAMILIES,
        ))
    elif role == "guided-b":
        passed = all((
            len(families) >= V11_B_MIN_FAMILIES,
            max(per_family.values(), default=0)
            <= V11_B_MAX_TASKS_PER_FAMILY,
            len(shadow_unrepresented)
            >= V11_B_MIN_SHADOW_UNREPRESENTED_FAMILIES,
            len(all_prior_unrepresented)
            >= V11_B_MIN_ALL_PRIOR_UNREPRESENTED_TASKS,
            len(all_prior_unrepresented_families)
            >= V11_B_MIN_ALL_PRIOR_UNREPRESENTED_FAMILIES,
        ))
    else:
        raise ProtocolError("unknown V11 cohort role")
    if not passed:
        raise ProtocolError("{} family/novelty floor changed".format(role))
    return tasks, dict(sorted(directory_to_family.items()))


def _expected_v11_run_provenance(
    bindings: dict, confirmation_a_freeze_sha256: str,
) -> dict:
    return {
        "source_audit_campaign": bindings["campaign"],
        "source_audit_launch_receipt_sha256": bindings["launch_receipt_sha256"],
        "source_audit_execution_receipt_sha256": bindings[
            "execution_receipt_sha256"
        ],
        "source_audit_code_manifest_sha256": bindings["code_manifest_sha256"],
        "source_audit_repository_commit_id": bindings[
            "seal_repository_commit_id"
        ],
        "source_audit_source_repository_commit_id": bindings[
            "preflight_source_repository_commit_id"
        ],
        "source_audit_preflight_seal_repository_commit_id": bindings[
            "preflight_seal_repository_commit_id"
        ],
        "source_audit_seal_repository_commit_id": bindings[
            "seal_repository_commit_id"
        ],
        "source_audit_inventory_sha256": bindings["source_inventory_sha256"],
        "source_audit_preflight_authorization_sha256": bindings[
            "preflight_authorization_sha256"
        ],
        "source_audit_controller_canary_sha256": bindings[
            "controller_publisher_canary_receipt_sha256"
        ],
        "source_audit_compute_canary_launch_sha256": bindings[
            "compute_canary_launch_receipt_sha256"
        ],
        "source_audit_compute_canary_terminal_poll_receipt_sha256": bindings[
            "compute_canary_terminal_poll_receipt_sha256"
        ],
        "source_audit_compute_canary_seal_sha256": bindings[
            "compute_canary_seal_plan_sha256"
        ],
        "source_audit_compute_canary_attestation_sha256": bindings[
            "compute_canary_attestation_sha256"
        ],
        "source_audit_full_tracked_closure_sha256": bindings[
            "full_tracked_file_sha256_digest"
        ],
        "source_audit_preflight_tracked_closure_sha256": bindings[
            "preflight_tracked_file_sha256_digest"
        ],
        "source_audit_combined_tracked_closure_sha256": bindings[
            "combined_tracked_file_sha256_digest"
        ],
        "source_audit_all_records_sha256": bindings["all_records_sha256"],
        "source_audit_confirmation_a_indices_sha256": bindings[
            "confirmation_a_candidate_indices_sha256"
        ],
        "source_audit_confirmation_a_projection_sha256": bindings[
            "confirmation_a_source_projection_sha256"
        ],
        "source_audit_guided_b_indices_sha256": bindings[
            "guided_b_candidate_indices_sha256"
        ],
        "source_audit_guided_b_projection_sha256": bindings[
            "guided_b_source_projection_sha256"
        ],
        "confirmation_a_freeze_sha256": confirmation_a_freeze_sha256,
    }


def guided_b_tasks(snapshot: dict) -> list[dict]:
    return snapshot["source_audit_v11"]["guided_b"]["records"]


def guided_b_projection_sha256(snapshot: dict) -> str:
    return snapshot["source_audit_v11"]["guided_b"][
        "source_projection_sha256"
    ]


def validate_base_snapshot(snapshot: dict) -> None:
    keys = {
        "schema", "base_b_freeze_path", "base_b_freeze_sha256",
        "base_b_freeze_repository_revision", "base_b_experiment_source_sha256",
        "base_b_planner", "benchmark_revision", "confirmation_a_authorization",
        "confirmation_a_freeze", "source_audit_v11", "confirmation_a_cohort",
    }
    if not isinstance(snapshot, dict) or set(snapshot) != keys or (
        snapshot.get("schema") != BASE_SNAPSHOT_SCHEMA
    ):
        raise ProtocolError("sealed B snapshot schema changed")
    _require_sha(snapshot.get("base_b_freeze_sha256"), "base B freeze")
    expected_base_freeze = BASE_B_FREEZE_PATH.relative_to(REPO).as_posix()
    if snapshot.get("base_b_freeze_path") != expected_base_freeze:
        raise ProtocolError("base B freeze path changed")
    _safe_experiment_path(expected_base_freeze, "base B freeze")
    _require_commit40(
        snapshot.get("base_b_freeze_repository_revision"), "base B freeze",
    )
    base_source_hashes = snapshot.get("base_b_experiment_source_sha256")
    if not isinstance(base_source_hashes, dict) or set(
        base_source_hashes
    ) != set(BASE_B_EXPERIMENT_SOURCE_FILES):
        raise ProtocolError("base B experiment source closure changed")
    for relative, digest in base_source_hashes.items():
        _safe_repo_path(relative, "base B experiment source")
        _require_sha(digest, "base B experiment source")
    validate_planner_identity(snapshot.get("base_b_planner"))
    _require_commit40(snapshot.get("benchmark_revision"), "benchmark revision")

    source = snapshot.get("source_audit_v11")
    if not isinstance(source, dict) or set(source) != {
        "schema", "source_seal_revision", "bindings", "guided_b",
    } or source.get("schema") != V11_SOURCE_SCHEMA:
        raise ProtocolError("sealed V11 source shape changed")
    bindings = source.get("bindings")
    _validate_v11_bindings(bindings)
    if (
        source.get("source_seal_revision")
        != bindings["seal_repository_commit_id"]
        or snapshot["benchmark_revision"] != bindings["benchmark_revision"]
    ):
        raise ProtocolError("sealed V11 revision binding changed")
    tasks_b, directory_families_b = _validate_v11_cohort(
        source.get("guided_b"), "guided-b", COHORT_TASKS
    )
    if (
        source["guided_b"]["candidate_indices_sha256"]
        != bindings["guided_b_candidate_indices_sha256"]
        or source["guided_b"]["source_projection_sha256"]
        != bindings["guided_b_source_projection_sha256"]
    ):
        raise ProtocolError("guided-B projection binding changed")

    confirmation_freeze = snapshot.get("confirmation_a_freeze")
    expected_a_freeze = BASE_A_FREEZE_PATH.relative_to(REPO).as_posix()
    if not isinstance(confirmation_freeze, dict) or set(confirmation_freeze) != {
        "path", "sha256", "repository_revision",
    } or confirmation_freeze.get("path") != expected_a_freeze:
        raise ProtocolError("Confirmation A freeze binding changed")
    _safe_experiment_path(expected_a_freeze, "Confirmation A freeze")
    _require_sha(confirmation_freeze.get("sha256"), "Confirmation A freeze")
    _require_commit40(
        confirmation_freeze.get("repository_revision"), "Confirmation A freeze",
    )
    confirmation = snapshot.get("confirmation_a_cohort")
    tasks_a, directory_families_a = _validate_v11_cohort(
        confirmation, "confirmation-a", 650
    )
    if (
        confirmation["candidate_indices_sha256"]
        != bindings["confirmation_a_candidate_indices_sha256"]
        or confirmation["source_projection_sha256"]
        != bindings["confirmation_a_source_projection_sha256"]
    ):
        raise ProtocolError("Confirmation A projection binding changed")
    if bindings["inventory_families_count"] < len({
        task["family"] for task in (*tasks_a, *tasks_b)
    }):
        raise ProtocolError("V11 inventory family count is too small")
    if (
        any(
            directory_families_a[directory] != directory_families_b[directory]
            for directory in set(directory_families_a) & set(directory_families_b)
        )
    ):
        raise ProtocolError("sealed A/B directory-to-family ledgers disagree")
    if (
        {task["candidate_index"] for task in tasks_a}
        & {task["candidate_index"] for task in tasks_b}
        or {(task["directory"], task["problem"]) for task in tasks_a}
        & {(task["directory"], task["problem"]) for task in tasks_b}
        or {task["problem_sha256"] for task in tasks_a}
        & {task["problem_sha256"] for task in tasks_b}
    ):
        raise ProtocolError("sealed A and guided-B projections overlap")

    authorization = snapshot.get("confirmation_a_authorization")
    authorization_keys = {
        "receipt_path", "receipt_pin_path", "first_output_path",
        "second_output_path", "receipt_sha256", "first_output_sha256",
        "second_output_sha256", "input_properties_sha256",
        "fetch_receipt_sha256", "execution_receipt_sha256", "hardware",
        "receipt_schema", "analysis_protocol", "guided_study_authorized",
        "benchmark_revision", "cost_attestation_sha256",
        "source_audit_launch_receipt_sha256",
        "source_audit_execution_receipt_sha256",
        "confirmation_a_cohort_manifest_sha256", "source_audit_provenance",
        "confirmation_a_freeze_path",
        "confirmation_a_freeze_repository_revision", "planner_identity",
    }
    if (
        not isinstance(authorization, dict)
        or set(authorization) != authorization_keys
        or authorization.get("guided_study_authorized") is not True
    ):
        raise ProtocolError("Confirmation A does not authorize the campaign")
    for field in (
        "receipt_sha256", "first_output_sha256", "second_output_sha256",
        "input_properties_sha256", "fetch_receipt_sha256",
        "execution_receipt_sha256", "cost_attestation_sha256",
        "source_audit_launch_receipt_sha256",
        "source_audit_execution_receipt_sha256",
        "confirmation_a_cohort_manifest_sha256",
    ):
        _require_sha(authorization.get(field), "A authorization " + field)
    try:
        RunCell.validate_hardware_summary(
            authorization.get("hardware"), BASE_A_CELL_COUNT
        )
    except RunCell.RunCellError as err:
        raise ProtocolError("A authorization hardware changed") from err
    expected_authorization_paths = {
        "receipt_path": BASE_A_RECEIPT_PATH,
        "receipt_pin_path": BASE_A_RECEIPT_PIN_PATH,
        "first_output_path": BASE_A_FIRST_OUTPUT_PATH,
        "second_output_path": BASE_A_SECOND_OUTPUT_PATH,
        "confirmation_a_freeze_path": BASE_A_FREEZE_PATH,
    }
    for field, path in expected_authorization_paths.items():
        expected = path.relative_to(REPO).as_posix()
        if authorization.get(field) != expected:
            raise ProtocolError("A authorization artifact path changed")
        _safe_experiment_path(expected, "A authorization")
    if any((
        authorization.get("benchmark_revision") != snapshot["benchmark_revision"],
        authorization.get("receipt_schema") != BASE_A_RECEIPT_SCHEMA,
        authorization.get("analysis_protocol") != BASE_A_ANALYSIS_PROTOCOL,
        authorization.get("first_output_sha256")
        != authorization.get("second_output_sha256"),
        authorization.get("cost_attestation_sha256")
        != bindings["attestation_sha256"],
        authorization.get("source_audit_launch_receipt_sha256")
        != bindings["launch_receipt_sha256"],
        authorization.get("source_audit_execution_receipt_sha256")
        != bindings["execution_receipt_sha256"],
        authorization.get("confirmation_a_cohort_manifest_sha256")
        != confirmation["source_projection_sha256"],
        authorization.get("confirmation_a_freeze_repository_revision")
        != confirmation_freeze["repository_revision"],
        authorization.get("source_audit_provenance")
        != _expected_v11_run_provenance(
            bindings, confirmation_freeze["sha256"]
        ),
    )):
        raise ProtocolError("Confirmation A authorization metadata changed")
    validate_planner_identity(authorization.get("planner_identity"))
    if authorization["planner_identity"] != snapshot["base_b_planner"]:
        raise ProtocolError("Confirmation A/B planner identity differs")


def _lazy_base_protocol():
    return importlib.import_module("pdb_terminal_incidence_confirmation_b_protocol")


def snapshot_sealed_b(calibration_receipt: dict) -> dict:
    """Validate A authorization and snapshot the canonical V11 A/B sources."""
    validate_calibration_receipt(calibration_receipt)
    base = _lazy_base_protocol()
    if tuple(base.EXPERIMENT_SOURCE_FILES) != BASE_B_EXPERIMENT_SOURCE_FILES:
        raise ProtocolError("Confirmation B source-file contract drifted")
    try:
        base.validate_protocol_without_sources()
        freeze, materials = base._load_freeze(base.FREEZE_PATH)
        live_authorization = base.load_confirmation_a_authorization(
            BASE_A_RECEIPT_PATH, BASE_A_RECEIPT_PIN_PATH,
            BASE_A_FIRST_OUTPUT_PATH, BASE_A_SECOND_OUTPUT_PATH,
        )
        base._validate_confirmation_a_source_link(live_authorization, materials)
        a_freeze, a_materials = base.SourceValidation._load_freeze(
            BASE_A_FREEZE_PATH
        )
    except Exception as err:
        raise ProtocolError("sealed V11 A/B protocol is unavailable") from err

    authorization = {}
    for field, value in live_authorization.items():
        if field.endswith("_path"):
            if not isinstance(value, Path):
                raise ProtocolError("A authorization path is not canonical")
            try:
                value = Path(os.path.abspath(value)).relative_to(
                    Path(os.path.abspath(REPO))
                ).as_posix()
            except ValueError as err:
                raise ProtocolError(
                    "A authorization path escaped repository"
                ) from err
        authorization[field] = value
    authorization = json.loads(canonical_json(authorization).decode("ascii"))
    if authorization != freeze["confirmation_a_authorization"]:
        raise ProtocolError("live and frozen Confirmation A authorizations differ")
    if materials.source_audit != freeze["source_audit"]:
        raise ProtocolError("Confirmation B source material changed")
    a_freeze_sha256 = base.sha256_file(BASE_A_FREEZE_PATH)
    if any((
        a_materials.bindings != materials.bindings,
        a_materials.candidate_indices_sha256
        != materials.confirmation_a_candidate_indices_sha256,
        a_materials.source_projection_sha256
        != materials.confirmation_a_source_projection_sha256,
        a_freeze["freeze_repository_revision"]
        != authorization["confirmation_a_freeze_repository_revision"],
        a_freeze_sha256
        != authorization["source_audit_provenance"][
            "confirmation_a_freeze_sha256"
        ],
        planner_identity(a_freeze["planner"])
        != planner_identity(freeze["planner"]),
    )):
        raise ProtocolError("sealed V11 A/B source bindings differ")
    try:
        confirmation_cohort = a_freeze["source_audit"]["confirmation_a"]
    except (KeyError, TypeError) as err:
        raise ProtocolError("sealed V11 A projection is unavailable") from err
    snapshot = {
        "schema": BASE_SNAPSHOT_SCHEMA,
        "base_b_freeze_path": base.FREEZE_PATH.relative_to(REPO).as_posix(),
        "base_b_freeze_sha256": base.sha256_file(base.FREEZE_PATH),
        "base_b_freeze_repository_revision": freeze[
            "freeze_repository_revision"
        ],
        "base_b_experiment_source_sha256": dict(sorted(
            freeze["experiment_source_sha256"].items()
        )),
        "base_b_planner": dict(freeze["planner"]),
        "benchmark_revision": base.BENCHMARK_REVISION,
        "confirmation_a_authorization": authorization,
        "confirmation_a_freeze": {
            "path": BASE_A_FREEZE_PATH.relative_to(REPO).as_posix(),
            "sha256": a_freeze_sha256,
            "repository_revision": a_freeze["freeze_repository_revision"],
        },
        "source_audit_v11": json.loads(
            canonical_json(materials.source_audit).decode("ascii")
        ),
        "confirmation_a_cohort": json.loads(
            canonical_json(confirmation_cohort).decode("ascii")
        ),
    }
    validate_base_snapshot(snapshot)
    if planner_identity(calibration_receipt["planner"]) != snapshot[
        "base_b_planner"
    ]:
        raise ProtocolError("calibration and Confirmation A/B planner differ")
    validate_calibration_exclusion(calibration_receipt, snapshot)
    return snapshot

def validate_planner_manifest(manifest: dict) -> None:
    keys = {
        "schema", "revision", "selector_base_revision", "cache_name", "downward_sha256",
        "preprocess_sha256", "tree_manifest_sha256", "build_options",
        "driver_path", "driver_sha256", "downward_path", "preprocess_path",
        "option_matrix_sha256", "searches", "dual_trace_schema",
    }
    if (
        not isinstance(manifest, dict)
        or set(manifest) != keys
        or manifest.get("schema") != PLANNER_MANIFEST_SCHEMA
        or manifest.get("revision") != REQUIRED_PLANNER_REVISION
        or manifest.get("selector_base_revision") != REQUIRED_SELECTOR_COMMIT
        or not isinstance(manifest.get("cache_name"), str)
        or not manifest["cache_name"]
        or manifest.get("build_options") != list(BUILD_OPTIONS)
        or manifest.get("driver_path") != "fast-downward.py"
        or manifest.get("downward_path")
        != "builds/release_no_lp/bin/downward"
        or manifest.get("preprocess_path")
        != "builds/release_no_lp/bin/preprocess"
        or manifest.get("option_matrix_sha256") != option_matrix_digest()
        or manifest.get("searches") != [
            {"mode": mode, "search": SEARCHES[mode]} for mode in MODES
        ]
        or manifest.get("dual_trace_schema") != DUAL_TRACE_SCHEMA
    ):
        raise ProtocolError("planner manifest changed")
    for field in (
        "driver_sha256", "downward_sha256", "preprocess_sha256",
        "tree_manifest_sha256",
    ):
        _require_sha(manifest.get(field), "planner {}".format(field))


def _identity_without_metrics(value: dict) -> dict:
    keys = {"pattern_index", "sources", "pattern", "value_cap"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ProtocolError("standalone K32 identity changed")
    sources = value["sources"]
    if (
        not isinstance(sources, list)
        or not sources
        or any(
            not isinstance(item, str) or item not in CANDIDATE_SOURCES
            for item in sources
        )
    ):
        raise ProtocolError("standalone K32 identity is invalid")
    if any((
        type(value["pattern_index"]) is not int,
        value["pattern_index"] < 0,
        sources != sorted(set(sources), key=CANDIDATE_SOURCES.index),
        not isinstance(value["pattern"], list),
        any(type(item) is not int or item < 0 for item in value["pattern"]),
        value["pattern"] != sorted(set(value["pattern"])),
        value["value_cap"] is not None and (
            type(value["value_cap"]) is not int
            or value["value_cap"] not in VALUE_CAP_GRID
        ),
    )):
        raise ProtocolError("standalone K32 identity is invalid")
    return value


def _reference_score_better(candidate: dict, incumbent: dict) -> bool:
    if candidate["initial_dead_end"] != incumbent["initial_dead_end"]:
        return candidate["initial_dead_end"]
    if not candidate["initial_dead_end"] and candidate["initial_h"] != (
        incumbent["initial_h"]
    ):
        return candidate["initial_h"] > incumbent["initial_h"]
    if candidate["finite_count"] == 0 or incumbent["finite_count"] == 0:
        if candidate["finite_count"] != incumbent["finite_count"]:
            return candidate["finite_count"] == 0
    else:
        left = candidate["finite_sum"] * incumbent["finite_count"]
        right = incumbent["finite_sum"] * candidate["finite_count"]
        if left != right:
            return left > right
    left = candidate["dead_count"] * incumbent["abstract_states"]
    right = incumbent["dead_count"] * candidate["abstract_states"]
    if left != right:
        return left > right
    for field in ("cofactor_width", "abstract_states"):
        if candidate[field] != incumbent[field]:
            return candidate[field] < incumbent[field]
    return candidate["pattern"] < incumbent["pattern"]


def _standalone_reference_candidate(value: dict, pool: list[dict]) -> dict:
    keys = {
        "pattern_index", "sources", "pattern", "value_cap",
        "initial_dead_end", "initial_h", "finite_sum", "finite_count",
        "dead_count", "abstract_states", "cofactor_width",
        "reference_feasible",
    }
    if not isinstance(value, dict) or set(value) != keys:
        raise ProtocolError("standalone K32 reference candidate changed")
    _identity_without_metrics({key: value[key] for key in (
        "pattern_index", "sources", "pattern", "value_cap",
    )})
    index = value["pattern_index"]
    if type(index) is not int or not 0 <= index < len(pool):
        raise ProtocolError("standalone K32 reference candidate is outside pool")
    row = pool[index]
    if any((
        value["sources"] != row["sources"],
        value["pattern"] != row["pattern"],
        value["abstract_states"] != row["abstract_states"],
        not row["within_state_budget"],
        type(value["initial_dead_end"]) is not bool,
        value["initial_dead_end"] != (value["initial_h"] is None),
        value["initial_h"] is not None and (
            type(value["initial_h"]) is not int or value["initial_h"] < 0
        ),
        any(type(value[field]) is not int or value[field] < 0 for field in (
            "finite_sum", "finite_count", "dead_count", "cofactor_width",
        )),
        value["finite_count"] + value["dead_count"]
        != value["abstract_states"],
        type(value["reference_feasible"]) is not bool,
        value["reference_feasible"] != (value["cofactor_width"] <= 32),
        not value["reference_feasible"],
    )):
        raise ProtocolError("standalone K32 reference candidate is invalid")
    return value


def validate_standalone_source_binding(binding: dict) -> None:
    expected_paths = {
        "parse_receipt_path": BASE_B_PARSE_RECEIPT_PATH,
        "fetch_receipt_path": BASE_B_FETCH_RECEIPT_PATH,
        "properties_path": BASE_B_PROPERTIES_PATH,
    }
    if not isinstance(binding, dict) or set(binding) != {
        *expected_paths, "parse_receipt_sha256", "fetch_receipt_sha256",
        "properties_sha256",
    }:
        raise ProtocolError("standalone K32 sealed-B input binding changed")
    for field, path in expected_paths.items():
        expected = path.relative_to(REPO).as_posix()
        if binding.get(field) != expected:
            raise ProtocolError("standalone K32 sealed-B input path changed")
        _safe_experiment_path(expected, "standalone K32 sealed-B input")
    for field in (
        "parse_receipt_sha256", "fetch_receipt_sha256", "properties_sha256",
    ):
        _require_sha(binding.get(field), "standalone K32 sealed-B input")


def validate_standalone_evidence(
    evidence: dict, snapshot: dict, planner_manifest: dict | None = None,
) -> None:
    validate_base_snapshot(snapshot)
    keys = {
        "schema", "base_b_freeze_sha256", "cohort_manifest_sha256",
        "producer", "sealed_b_input", "records", "records_sha256",
    }
    if (
        not isinstance(evidence, dict)
        or set(evidence) != keys
        or evidence.get("schema") != STANDALONE_SCHEMA
        or evidence.get("base_b_freeze_sha256")
        != snapshot["base_b_freeze_sha256"]
        or evidence.get("cohort_manifest_sha256")
        != guided_b_projection_sha256(snapshot)
    ):
        raise ProtocolError("standalone K32 evidence header changed")
    producer = evidence.get("producer")
    if not isinstance(producer, dict) or set(producer) != {
        "planner_manifest", "planner_manifest_sha256",
        "option_matrix_sha256", "reference_rule",
    } or producer.get("option_matrix_sha256") != option_matrix_digest() or (
        producer.get("reference_rule")
        != "strongest-K32-feasible-cap-per-pattern-then-score-v1"
    ):
        raise ProtocolError("standalone K32 producer binding changed")
    validate_planner_manifest(producer.get("planner_manifest"))
    if producer.get("planner_manifest_sha256") != hashlib.sha256(
        canonical_json_line(producer["planner_manifest"])
    ).hexdigest() or (
        planner_identity(producer["planner_manifest"])
        != snapshot["base_b_planner"]
    ) or (
        planner_manifest is not None
        and canonical_json(planner_manifest)
        != canonical_json(producer["planner_manifest"])
    ):
        raise ProtocolError("standalone K32 planner binding changed")
    validate_standalone_source_binding(evidence.get("sealed_b_input"))
    records = evidence.get("records")
    if not isinstance(records, list) or len(records) != COHORT_TASKS:
        raise ProtocolError("standalone K32 evidence cardinality changed")
    expected_tasks = {
        (domain, problem): family
        for domain, problem, family in map(
            _task_identity, guided_b_tasks(snapshot)
        )
    }
    seen = set()
    for record in records:
        if not isinstance(record, dict) or set(record) != {
            "domain", "problem", "family", "reference_identity",
            "reference_representatives", "reference_representatives_sha256",
            "normalized_pool", "normalized_pool_sha256",
        }:
            raise ProtocolError("standalone K32 evidence record changed")
        task = (record["domain"], record["problem"])
        if task in seen or expected_tasks.get(task) != record["family"]:
            raise ProtocolError("standalone K32 evidence task changed")
        seen.add(task)
        _identity_without_metrics(record["reference_identity"])
        pool = record["normalized_pool"]
        if not isinstance(pool, list) or not pool:
            raise ProtocolError("standalone K32 pool is invalid")
        vectors = set()
        sources_seen = []
        for index, pattern in enumerate(pool):
            if not isinstance(pattern, dict) or set(pattern) != {
                "pattern_index", "sources", "pattern", "abstract_states",
                "within_state_budget",
            }:
                raise ProtocolError("standalone K32 pool row changed")
            sources = pattern["sources"]
            variables = pattern["pattern"]
            states = pattern["abstract_states"]
            if (
                not isinstance(sources, list) or not sources or any(
                    not isinstance(source, str)
                    or source not in CANDIDATE_SOURCES
                    for source in sources
                )
            ):
                raise ProtocolError("standalone K32 pool source is invalid")
            if any((
                pattern["pattern_index"] != index,
                sources != sorted(set(sources), key=CANDIDATE_SOURCES.index),
                not isinstance(variables, list),
                any(type(var) is not int or var < 0 for var in variables),
                variables != sorted(set(variables)),
                tuple(variables) in vectors,
                type(states) is not int or not 1 <= states <= 2**31 - 1,
                type(pattern["within_state_budget"]) is not bool,
                pattern["within_state_budget"] != (states <= 100000),
            )):
                raise ProtocolError("standalone K32 pool row is invalid")
            vectors.add(tuple(variables))
            sources_seen.extend(sources)
        if pool[0] != {
            "pattern_index": 0, "sources": ["empty"], "pattern": [],
            "abstract_states": 1, "within_state_budget": True,
        }:
            raise ProtocolError("standalone K32 empty pattern changed")
        if sources_seen != list(CANDIDATE_SOURCES):
            raise ProtocolError("standalone K32 pool generator coverage changed")
        identity = record["reference_identity"]
        representatives = record["reference_representatives"]
        if not isinstance(representatives, list) or not representatives:
            raise ProtocolError("standalone K32 representatives are absent")
        representatives = [
            _standalone_reference_candidate(row, pool) for row in representatives
        ]
        indexes = [row["pattern_index"] for row in representatives]
        expected_indexes = [
            row["pattern_index"] for row in pool if row["within_state_budget"]
        ]
        if indexes != expected_indexes or (
            record["reference_representatives_sha256"] != hashlib.sha256(
                canonical_json(representatives)
            ).hexdigest()
        ):
            raise ProtocolError("standalone K32 representative set changed")
        expected_reference = representatives[0]
        for candidate in representatives[1:]:
            if _reference_score_better(candidate, expected_reference):
                expected_reference = candidate
        reconstructed = {key: expected_reference[key] for key in (
            "pattern_index", "sources", "pattern", "value_cap",
        )}
        if identity != reconstructed:
            raise ProtocolError("standalone K32 reference reconstruction changed")
        if hashlib.sha256(canonical_json(pool)).hexdigest() != record.get(
            "normalized_pool_sha256"
        ):
            raise ProtocolError("standalone K32 pool digest changed")
    if seen != set(expected_tasks) or evidence.get("records_sha256") != (
        hashlib.sha256(canonical_json(records)).hexdigest()
    ):
        raise ProtocolError("standalone K32 evidence digest changed")


def _contains_forbidden_calibration_key(value) -> bool:
    forbidden = (
        "selected", "winner", "reference_identity", "coverage", "outcome",
        "plan_cost", "search_time", "total_time", "exit_code",
    )
    if isinstance(value, dict):
        return any(
            any(token in str(key).lower() for token in forbidden)
            or _contains_forbidden_calibration_key(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_calibration_key(item) for item in value)
    return False


def validate_calibration_receipt(receipt: dict) -> None:
    keys = {
        "schema", "development_task_manifest_sha256", "dual_trace_schema",
        "modes", "exposed_fields", "observations", "observations_sha256",
        "all_traces_complete", "resource_recommendation",
        "planner_manifest_sha256", "planner", "option_matrix_sha256",
    }
    allowed_fields = [
        "trace_status", "probe_completed_layers", "probe_cpu_seconds",
        "probe_wall_seconds", "probe_peak_memory_before_kb",
        "probe_peak_memory_after_kb", "probe_peak_memory_delta_kb",
        "selection_cpu_seconds", "selection_wall_seconds",
        "selection_peak_memory_before_kb",
        "selection_peak_memory_after_kb", "selection_peak_memory_delta_kb",
    ]
    if (
        not isinstance(receipt, dict)
        or set(receipt) != keys
        or receipt.get("schema") != CALIBRATION_SCHEMA
        or receipt.get("dual_trace_schema") != DUAL_TRACE_SCHEMA
        or receipt.get("modes") != list(MODES)
        or receipt.get("option_matrix_sha256") != option_matrix_digest()
        or receipt.get("exposed_fields") != allowed_fields
        or receipt.get("all_traces_complete") is not True
        or _contains_forbidden_calibration_key(receipt)
    ):
        raise ProtocolError("calibration receipt exposes forbidden information")
    _require_sha(
        receipt.get("development_task_manifest_sha256"), "calibration task manifest"
    )
    _require_sha(receipt.get("planner_manifest_sha256"), "calibration planner")
    validate_planner_manifest(receipt.get("planner"))
    if receipt["planner_manifest_sha256"] != hashlib.sha256(
        canonical_json_line(receipt["planner"])
    ).hexdigest():
        raise ProtocolError("calibration planner manifest digest changed")
    calibration_module = importlib.import_module(
        "pdb_terminal_metric_choice_calibration"
    )
    if receipt["development_task_manifest_sha256"] != (
        calibration_module.development_manifest_sha256()
    ):
        raise ProtocolError("calibration development task manifest changed")
    observations = receipt.get("observations")
    if not isinstance(observations, list) or len(observations) != 9:
        raise ProtocolError("calibration observations are absent")
    if receipt.get("observations_sha256") != hashlib.sha256(
        canonical_json(observations)
    ).hexdigest():
        raise ProtocolError("calibration observation digest changed")
    observed_cells = set()
    for observation in observations:
        if not isinstance(observation, dict) or set(observation) != {
            "task_id", "mode", *allowed_fields,
        } or observation.get("mode") not in MODES or (
            observation.get("trace_status") != "complete"
        ) or observation.get("probe_completed_layers") != PROBE_LAYERS:
            raise ProtocolError("calibration observation changed")
        task_id = observation.get("task_id")
        cell = (task_id, observation["mode"])
        if (
            not isinstance(task_id, str)
            or not task_id.startswith("__metric_choice_calibration__/")
            or cell in observed_cells
        ):
            raise ProtocolError("calibration development task changed")
        for prefix in ("probe", "selection"):
            for suffix in ("cpu_seconds", "wall_seconds"):
                value = observation["{}_{}".format(prefix, suffix)]
                if type(value) not in (int, float) or not math.isfinite(
                    value
                ) or value < 0:
                    raise ProtocolError("calibration timing is invalid")
            before = observation["{}_peak_memory_before_kb".format(prefix)]
            after = observation["{}_peak_memory_after_kb".format(prefix)]
            delta = observation["{}_peak_memory_delta_kb".format(prefix)]
            if any(type(value) is not int or value < 0 for value in (
                before, after, delta,
            )) or delta != max(0, after - before):
                raise ProtocolError("calibration memory is invalid")
        observed_cells.add(cell)
    task_ids = {task_id for task_id, _ in observed_cells}
    expected_task_ids = {task_id for task_id, _ in CALIBRATION_TASK_SPECS}
    if task_ids != expected_task_ids or observed_cells != {
        (task_id, mode) for task_id in expected_task_ids for mode in MODES
    }:
        raise ProtocolError("calibration matrix changed")
    recommendation = receipt.get("resource_recommendation")
    if recommendation != calibration_resource_recommendation(observations):
        raise ProtocolError("calibration resource recommendation changed")


def validate_calibration_exclusion(receipt: dict, snapshot: dict) -> None:
    """Prove generated development bytes/IDs are outside both sealed cohorts."""
    validate_calibration_receipt(receipt)
    validate_base_snapshot(snapshot)
    calibration_module = importlib.import_module(
        "pdb_terminal_metric_choice_calibration"
    )
    development = calibration_module.development_manifest()["tasks"]
    dev_ids = {row["task_id"] for row in development}
    dev_domains = {row["domain_sha256"] for row in development}
    dev_problems = {row["problem_sha256"] for row in development}
    cohort_rows = [
        *snapshot["confirmation_a_cohort"]["records"],
        *guided_b_tasks(snapshot),
    ]
    for row in cohort_rows:
        identity = "{}/{}".format(
            row.get("directory", row.get("domain")), row["problem"]
        )
        if any((
            identity in dev_ids,
            row.get("domain_sha256") in dev_domains,
            row.get("problem_sha256") in dev_problems,
        )):
            raise ProtocolError(
                "calibration development task overlaps a sealed A/B cohort"
            )


def live_source_hashes() -> dict[str, str]:
    hashes = {}
    for relative in SOURCE_FILES:
        hashes[relative] = sha256_file(_safe_repo_path(relative, "campaign source"))
    return hashes


def build_freeze(
    *,
    freeze_repository_revision: str,
    base_snapshot: dict,
    calibration_receipt: dict,
    calibration_receipt_path: str,
    calibration_receipt_sha256: str,
    planner_manifest: dict,
    standalone_evidence: dict,
    standalone_evidence_path: str,
    standalone_evidence_sha256: str,
    source_hashes: dict[str, str],
    scheduler_time_limit: str,
    scheduler_memory: str,
) -> dict:
    validate_static_design()
    validate_base_snapshot(base_snapshot)
    validate_calibration_receipt(calibration_receipt)
    validate_planner_manifest(planner_manifest)
    if planner_identity(planner_manifest) != base_snapshot["base_b_planner"]:
        raise ProtocolError("campaign freeze repository/planner binding changed")
    _require_commit40(freeze_repository_revision, "campaign freeze repository")
    validate_calibration_exclusion(calibration_receipt, base_snapshot)
    validate_standalone_evidence(
        standalone_evidence, base_snapshot, planner_manifest
    )
    validate_frozen_resources(
        scheduler_time_limit, scheduler_memory,
        calibration_receipt["resource_recommendation"],
    )
    _require_sha(calibration_receipt_sha256, "calibration receipt")
    _require_sha(standalone_evidence_sha256, "standalone evidence")
    expected_calibration = CALIBRATION_RECEIPT_PATH.relative_to(REPO).as_posix()
    expected_standalone = STANDALONE_K32_PATH.relative_to(REPO).as_posix()
    if calibration_receipt_path != expected_calibration or (
        standalone_evidence_path != expected_standalone
    ):
        raise ProtocolError("bound campaign evidence path changed")
    _safe_experiment_path(calibration_receipt_path, "calibration receipt")
    _safe_experiment_path(standalone_evidence_path, "standalone evidence")
    if calibration_receipt_sha256 != hashlib.sha256(
        canonical_json_line(calibration_receipt)
    ).hexdigest() or standalone_evidence_sha256 != hashlib.sha256(
        canonical_json_line(standalone_evidence)
    ).hexdigest():
        raise ProtocolError("bound receipt digest does not match its content")
    if canonical_json(calibration_receipt["planner"]) != canonical_json(
        planner_manifest
    ):
        raise ProtocolError("calibration used a different planner manifest")
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(SOURCE_FILES):
        raise ProtocolError("campaign source manifest changed")
    for relative, digest in source_hashes.items():
        _safe_repo_path(relative, "campaign source")
        _require_sha(digest, "campaign source")
    tasks = guided_b_tasks(base_snapshot)
    mapping_sha = run_cell_mapping_digest(tasks)
    return {
        "schema": FREEZE_SCHEMA,
        "freeze_repository_revision": freeze_repository_revision,
        "base_confirmation_b": base_snapshot,
        "calibration": {
            "receipt_path": calibration_receipt_path,
            "receipt_sha256": calibration_receipt_sha256,
            "development_task_manifest_sha256": calibration_receipt[
                "development_task_manifest_sha256"
            ],
            "observations_sha256": calibration_receipt["observations_sha256"],
            "resource_recommendation": calibration_receipt[
                "resource_recommendation"
            ],
        },
        "planner": planner_manifest,
        "standalone_k32": {
            "evidence_path": standalone_evidence_path,
            "evidence_sha256": standalone_evidence_sha256,
            "records_sha256": standalone_evidence["records_sha256"],
            "sealed_b_input": standalone_evidence["sealed_b_input"],
        },
        "design": {
            "protocol": PROTOCOL,
            "analysis_protocol": ANALYSIS_PROTOCOL,
            "protocol_sha256": sha256_file(PROTOCOL_PATH),
            "option_matrix_sha256": option_matrix_digest(),
            "run_order_protocol": RUN_ORDER_PROTOCOL,
            "run_cell_mapping_sha256": mapping_sha,
            "cohort_tasks": COHORT_TASKS,
            "config_count": CONFIG_COUNT,
            "cell_count": CELL_COUNT,
            "array_tasks": EXPECTED_ARRAY_TASKS,
            "runs_per_array_task": RUNS_PER_ARRAY_TASK,
            "array_throttle": 0,
            "modes": list(MODES),
            "dual_trace_schema": DUAL_TRACE_SCHEMA,
            "dual_trace_protocol": DUAL_TRACE_PROTOCOL,
            "probe_layers": PROBE_LAYERS,
            "reference_cofactor_width_budget": REFERENCE_COFACTOR_WIDTH_BUDGET,
            "time_limit_seconds": TIME_LIMIT_SECONDS,
            "memory_limit_mib": MEMORY_LIMIT_MIB,
            "scheduler_time_limit": scheduler_time_limit,
            "scheduler_memory": scheduler_memory,
            "par2_seconds": PAR2_SECONDS,
            "bootstrap_replicates": BOOTSTRAP_REPLICATES,
            "bootstrap_seed": BOOTSTRAP_SEED,
            "minimum_differing_winner_tasks": MIN_DIFFERING_WINNER_TASKS,
            "minimum_differing_winner_families": MIN_DIFFERING_WINNER_FAMILIES,
        },
        "experiment_source_sha256": dict(sorted(source_hashes.items())),
    }


def _load_bound_file(
    relative: str, digest: str, label: str, *, expected_path: Path,
) -> dict:
    path = _safe_repo_path(relative, label)
    raw, value = load_canonical(path, label, expected_path=expected_path)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ProtocolError("{} digest changed".format(label))
    return value


def validate_freeze(freeze: dict, *, verify_live_sources: bool = True) -> None:
    if not isinstance(freeze, dict) or set(freeze) != {
        "schema", "freeze_repository_revision", "base_confirmation_b",
        "calibration", "planner", "standalone_k32", "design",
        "experiment_source_sha256",
    } or freeze.get("schema") != FREEZE_SCHEMA:
        raise ProtocolError("dual metric freeze schema changed")
    _require_commit40(
        freeze.get("freeze_repository_revision"), "dual metric freeze repository"
    )
    validate_base_snapshot(freeze["base_confirmation_b"])
    validate_planner_manifest(freeze["planner"])
    if planner_identity(freeze["planner"]) != freeze["base_confirmation_b"][
        "base_b_planner"
    ]:
        raise ProtocolError("dual metric planner differs from Confirmation A/B")
    design = freeze.get("design")
    tasks = guided_b_tasks(freeze["base_confirmation_b"])
    expected_design = {
        "protocol": PROTOCOL,
        "analysis_protocol": ANALYSIS_PROTOCOL,
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "option_matrix_sha256": option_matrix_digest(),
        "run_order_protocol": RUN_ORDER_PROTOCOL,
        "run_cell_mapping_sha256": run_cell_mapping_digest(tasks),
        "cohort_tasks": COHORT_TASKS,
        "config_count": CONFIG_COUNT,
        "cell_count": CELL_COUNT,
        "array_tasks": EXPECTED_ARRAY_TASKS,
        "runs_per_array_task": RUNS_PER_ARRAY_TASK,
        "array_throttle": 0,
        "modes": list(MODES),
        "dual_trace_schema": DUAL_TRACE_SCHEMA,
        "dual_trace_protocol": DUAL_TRACE_PROTOCOL,
        "probe_layers": PROBE_LAYERS,
        "reference_cofactor_width_budget": REFERENCE_COFACTOR_WIDTH_BUDGET,
        "time_limit_seconds": TIME_LIMIT_SECONDS,
        "memory_limit_mib": MEMORY_LIMIT_MIB,
        "par2_seconds": PAR2_SECONDS,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "minimum_differing_winner_tasks": MIN_DIFFERING_WINNER_TASKS,
        "minimum_differing_winner_families": MIN_DIFFERING_WINNER_FAMILIES,
    }
    if not isinstance(design, dict):
        raise ProtocolError("dual metric frozen design changed")
    comparison_design = dict(design)
    comparison_design.pop("scheduler_time_limit", None)
    comparison_design.pop("scheduler_memory", None)
    if comparison_design != expected_design:
        raise ProtocolError("dual metric frozen design changed")
    source_hashes = freeze.get("experiment_source_sha256")
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(SOURCE_FILES):
        raise ProtocolError("dual metric source manifest changed")
    for relative, digest in source_hashes.items():
        _require_sha(digest, "campaign source")
        if verify_live_sources and sha256_file(
            _safe_repo_path(relative, "campaign source")
        ) != digest:
            raise ProtocolError("campaign source changed: {}".format(relative))
    calibration = freeze.get("calibration")
    standalone = freeze.get("standalone_k32")
    if not isinstance(calibration, dict) or set(calibration) != {
        "receipt_path", "receipt_sha256", "development_task_manifest_sha256",
        "observations_sha256", "resource_recommendation",
    } or not isinstance(standalone, dict) or set(standalone) != {
        "evidence_path", "evidence_sha256", "records_sha256",
        "sealed_b_input",
    }:
        raise ProtocolError("frozen calibration or K32 binding changed")
    validate_standalone_source_binding(standalone.get("sealed_b_input"))
    for value, label in (
        (calibration["receipt_sha256"], "calibration receipt"),
        (calibration["development_task_manifest_sha256"], "development tasks"),
        (calibration["observations_sha256"], "calibration observations"),
        (standalone["evidence_sha256"], "standalone K32 evidence"),
        (standalone["records_sha256"], "standalone K32 records"),
    ):
        _require_sha(value, label)
    if calibration["receipt_path"] != CALIBRATION_RECEIPT_PATH.relative_to(
        REPO
    ).as_posix() or standalone["evidence_path"] != STANDALONE_K32_PATH.relative_to(
        REPO
    ).as_posix():
        raise ProtocolError("frozen evidence path changed")
    _safe_experiment_path(calibration["receipt_path"], "calibration receipt")
    _safe_experiment_path(standalone["evidence_path"], "standalone evidence")
    recommendation = calibration["resource_recommendation"]
    if not isinstance(recommendation, dict) or set(recommendation) != {
        "minimum_selector_wall_seconds", "minimum_selector_peak_delta_kb",
    } or any(type(value) is not int or value < 0
             for value in recommendation.values()):
        raise ProtocolError("frozen calibration resources changed")
    validate_frozen_resources(
        design.get("scheduler_time_limit"), design.get("scheduler_memory"),
        recommendation,
    )


def load_freeze(path: Path = FREEZE_PATH, *, verify_live_sources=True) -> dict:
    _, freeze = load_canonical(
        path, "dual metric freeze", expected_path=FREEZE_PATH
    )
    validate_freeze(freeze, verify_live_sources=verify_live_sources)
    return freeze


def load_bound_calibration(freeze: dict) -> dict:
    binding = freeze["calibration"]
    value = _load_bound_file(
        binding["receipt_path"], binding["receipt_sha256"], "calibration receipt",
        expected_path=CALIBRATION_RECEIPT_PATH,
    )
    validate_calibration_receipt(value)
    if any((
        value["observations_sha256"] != binding["observations_sha256"],
        value["development_task_manifest_sha256"]
        != binding["development_task_manifest_sha256"],
        value["resource_recommendation"] != binding["resource_recommendation"],
    )):
        raise ProtocolError("calibration binding changed")
    return value


def load_bound_standalone(freeze: dict) -> dict:
    binding = freeze["standalone_k32"]
    value = _load_bound_file(
        binding["evidence_path"], binding["evidence_sha256"],
        "standalone K32 evidence",
        expected_path=STANDALONE_K32_PATH,
    )
    validate_standalone_evidence(
        value, freeze["base_confirmation_b"], freeze["planner"]
    )
    if (
        value["records_sha256"] != binding["records_sha256"]
        or value["sealed_b_input"] != binding["sealed_b_input"]
    ):
        raise ProtocolError("standalone K32 binding changed")
    return value


@dataclass(frozen=True, order=True)
class CohortTask:
    domain: str
    problem: str
    family: str
    domain_file: str
    problem_file: str
    domain_sha256: str
    problem_sha256: str


def load_cohort(benchmarks, *, freeze_path: Path = FREEZE_PATH):
    freeze = load_freeze(freeze_path)
    root = Path(benchmarks).resolve()
    tasks = []
    for record in guided_b_tasks(freeze["base_confirmation_b"]):
        for field, hash_field in (
            ("domain_file", "domain_sha256"),
            ("problem_file", "problem_sha256"),
        ):
            path = root / record[field]
            if sha256_file(
                path, expected_path=path, root=root, label="benchmark source",
            ) != record[hash_field]:
                raise ProtocolError("embedded guided-B source bytes changed")
        tasks.append(CohortTask(
            domain=record["directory"], problem=record["problem"],
            family=record["family"], domain_file=record["domain_file"],
            problem_file=record["problem_file"],
            domain_sha256=record["domain_sha256"],
            problem_sha256=record["problem_sha256"],
        ))
    return tuple(tasks)


validate_static_design()
