#!/usr/bin/env python3
"""Frozen protocol and source loader for terminal-incidence Confirmation B."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pdb_profile_comparison_protocol as Source
import pdb_terminal_incidence_confirmation_a_protocol as SourceValidation


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
PROTOCOL_PATH = SCRIPT_DIR / "pdb_terminal_incidence_confirmation_b_protocol.md"
FREEZE_PATH = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation" /
    "confirmation-b-freeze-v1.json"
)
FREEZE_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-b-freeze/v1"
)
CONFIRMATION_A_ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation" /
    "confirmation-a"
)
CONFIRMATION_A_RECEIPT_PATH = (
    CONFIRMATION_A_ARTIFACT_DIR / "analysis-execution-receipt-v4.json"
)
CONFIRMATION_A_RECEIPT_PIN_PATH = (
    CONFIRMATION_A_ARTIFACT_DIR / "analysis-execution-receipt-v4.sha256"
)
CONFIRMATION_A_FIRST_OUTPUT_PATH = (
    CONFIRMATION_A_ARTIFACT_DIR / "analysis-v4.json"
)
CONFIRMATION_A_SECOND_OUTPUT_PATH = (
    CONFIRMATION_A_ARTIFACT_DIR / "analysis-v4-repeat.json"
)
SOURCE_AUDIT_SCHEMA = (
    "symbolic-search-heuristics/"
    "universal-unseen-confirmation-source-audit/v1"
)
PROTOCOL = "pdb-terminal-incidence-confirmation-b-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-terminal-incidence-confirmation-b-analysis-v3"
COHORT_ROLE = "source-disjoint-universal-confirmation-b"
COHORT_SEED = (
    "symbolic-search-heuristics/universal-unseen-confirmation-guided-split/v1"
)
BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
BENCHMARK_REPOSITORY = "https://github.com/aibasel/downward-benchmarks.git"
ACCOUNT = "naiss2025-5-561-cpu"
REQUIRED_LAB_VERSION = "8.10"
REQUIRED_PYTHON_VERSION = "3.12.13"
BUILD_OPTIONS = ("release_no_lp",)
PLANNER_REVISION_REQUIRED = SourceValidation.PLANNER_REVISION_REQUIRED

MIN_COHORT_TASKS = 300
TARGET_COHORT_TASKS = 300
MAX_COHORT_TASKS = 300
MIN_COHORT_FAMILIES = 30
MIN_SHADOW_UNREPRESENTED_FAMILIES = 12
MIN_ALL_PRIOR_UNREPRESENTED_TASKS = 50
MIN_ALL_PRIOR_UNREPRESENTED_FAMILIES = 10

# Installed from the one immutable freeze.  Before freezing, cardinalities are
# deliberately unusable so a campaign cannot accidentally launch a guessed
# cohort size.
COHORT_TASKS = 0
CONFIG_COUNT = 9
CELL_COUNT = 0
PROBE_LAYERS = 16
TIME_LIMIT_SECONDS = 1800
MEMORY_LIMIT_MIB = 24576
RUNS_PER_ARRAY_TASK = 3
EXPECTED_ARRAY_TASKS = 0
SCHEDULER_TIME_LIMIT = "01:40:00"
SCHEDULER_MEMORY = "26G"

PRIMARY_LABELS = (
    "blind_fw",
    "pdb_bdd_prefix",
    "pdb_goal_prefix",
    "pdb_goal_fill",
    "pdb_cegar_deterministic",
    "pdb_exact_width_k32",
    "pdb_cap_aware_k32",
    "pdb_terminal_incidence_guided",
    "pdb_terminal_incidence_matched",
)
INTERVENTION_LABEL = "__no_confirmation_b_intervention__"
PLAIN_REFERENCE_LABEL = "pdb_cap_aware_k32"
GUIDED_LABEL = "pdb_terminal_incidence_guided"
MATCHED_LABEL = "pdb_terminal_incidence_matched"
NON_GATING_REFERENCE_LABELS = (
    "blind_fw",
    "pdb_bdd_prefix",
    "pdb_goal_prefix",
    "pdb_goal_fill",
    "pdb_cegar_deterministic",
    "pdb_exact_width_k32",
)
SELECTOR_TRACE = "incidence-selector.jsonl"
SELECTOR_TRACE_SCHEMA = (
    "symbolic-search-heuristics/terminal-incidence-selector-trace/v3"
)
PAR2_SECONDS = 3600
MIN_NORMALIZED_PAR2_IMPROVEMENT_NUMERATOR = 1
MIN_NORMALIZED_PAR2_IMPROVEMENT_DENOMINATOR = 50
BOOTSTRAP_REPLICATES = 100000
BOOTSTRAP_SEED = 20260902
MIN_MECHANISM_TASKS = 50
MIN_MECHANISM_FAMILIES = 10
RUN_ORDER_PROTOCOL = "task-major-family-balanced-triads/v1"

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
        return SourceValidation.sha256_file(Path(path))
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err


def _same_exact(actual, expected) -> bool:
    """Compare JSON scalar values without accepting bool as an integer."""
    return type(actual) is type(expected) and actual == expected


def _load_canonical(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        return SourceValidation._load_canonical(Path(path), label)
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err


# Confirmation A and B consume the same immutable source-audit campaign.  Keep
# one fail-closed implementation of the v4 byte, output-tree, environment, and
# accounting contracts instead of allowing the two consumers to drift again.
def _validate_shared_v4_constants() -> None:
    names = (
        "SOURCE_V4_REPO", "SOURCE_V4_ATTESTATION_PATH",
        "SOURCE_V4_ARTIFACT_DIR",
        "SOURCE_V4_INTENT_PATH", "SOURCE_V4_LAUNCH_RECEIPT_PATH",
        "SOURCE_V4_LAUNCH_RECEIPT_SHA256", "SOURCE_V4_LAUNCH_INTENT_SHA256",
        "SOURCE_V4_EXECUTION_RECEIPT_PATH", "SOURCE_V4_SLURM_PATH",
        "SOURCE_V4_CODE_MANIFEST_PATH", "SOURCE_V4_AMENDMENT_PATH",
        "SOURCE_V4_INVENTORY_PATH", "SOURCE_V4_OUTPUT_DIR",
        "SOURCE_V4_CANDIDATE_PATH", "SOURCE_V4_MANIFEST_FILES",
        "SOURCE_V4_SLURM_RELATIVE", "SOURCE_V4_MANIFEST_RELATIVE",
        "SOURCE_V4_SLURM_SHA256", "SOURCE_V4_CODE_MANIFEST_SHA256",
        "SOURCE_V4_AMENDMENT_SHA256", "SOURCE_V4_INVENTORY_SHA256",
        "SOURCE_V4_FIXED_HASHES", "SOURCE_V4_V3_DIAGNOSTIC_RELATIVE",
        "SOURCE_V4_V3_DIAGNOSTIC_SHA256", "SOURCE_V4_PRODUCER_COMMIT_ID",
        "SOURCE_V4_JOB_ID", "SOURCE_V4_SBATCH_EXECUTABLE",
        "SOURCE_V4_SBATCH_EXECUTABLE_SHA256", "SOURCE_V4_SACCT_EXECUTABLE",
        "SOURCE_V4_SACCT_EXECUTABLE_SHA256", "SOURCE_V4_JJ_EXECUTABLE",
        "SOURCE_V4_JJ_EXECUTABLE_SHA256",
    )
    if any(globals()[name] != getattr(SourceValidation, name) for name in names):
        raise ProtocolError("Confirmation A/B source-audit v4 bindings diverged")


def _load_source_v4_byte_chain(launch: dict) -> tuple[bytes, dict, dict]:
    _validate_shared_v4_constants()
    try:
        return SourceValidation._load_source_v4_byte_chain(launch)
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err


def _source_v4_tracked_file_sha256(
    launch: dict, manifest_hashes: dict
) -> dict[str, str]:
    _validate_shared_v4_constants()
    try:
        return SourceValidation._source_v4_tracked_file_sha256(
            launch, manifest_hashes
        )
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err


def _validate_source_execution_environment(launch: dict, execution: dict) -> None:
    _validate_shared_v4_constants()
    try:
        SourceValidation._validate_source_execution_environment(launch, execution)
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err


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


def _pdb(mode: str, *, select_value_cap: bool = False) -> str:
    options = [
        "budget=100000",
        "pattern_selection={}".format(mode),
    ]
    if mode in (
        "cegar", "exact_width_filter", "terminal_incidence_guided",
        "terminal_incidence_matched_control",
    ):
        options.extend((
            "cegar_max_time=infinity",
            "cegar_max_refinements=128",
            "cegar_seed=2011",
        ))
    options.extend((
        "cofactor_width_budget={}".format(
            32 if mode == "exact_width_filter" else "infinity"
        ),
        "total_add_node_budget=infinity",
        "value_cap=-1",
        "select_value_cap={}".format(
            "true" if select_value_cap else "false"
        ),
        "gamer_ordering=false",
        "dynamic_reordering=false",
        "shadow_partition=false",
        "prune_only=false",
        "batch_f_window=0",
    ))
    if mode in (
        "terminal_incidence_guided",
        "terminal_incidence_matched_control",
    ):
        options.append('incidence_selector_log="{}"'.format(SELECTOR_TRACE))
    return "sym_fw_pdb({})".format(",".join(options))


CONFIGS = (
    ("blind_fw", "sym_fw()"),
    ("pdb_bdd_prefix", _pdb("bdd_prefix")),
    ("pdb_goal_prefix", _pdb("goal_prefix")),
    ("pdb_goal_fill", _pdb("goal_fill")),
    ("pdb_cegar_deterministic", _pdb("cegar")),
    ("pdb_exact_width_k32", _pdb("exact_width_filter")),
    ("pdb_cap_aware_k32", _pdb("exact_width_filter", select_value_cap=True)),
    ("pdb_terminal_incidence_guided", _pdb("terminal_incidence_guided")),
    (
        "pdb_terminal_incidence_matched",
        _pdb("terminal_incidence_matched_control"),
    ),
)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)


def _task_identity(task) -> tuple[str, str, str]:
    if isinstance(task, dict):
        domain = task.get("directory", task.get("domain"))
        problem = task.get("problem")
        family = task.get("family")
    else:
        domain = getattr(task, "domain", None)
        problem = getattr(task, "problem", None)
        family = getattr(task, "family", None)
    if family is None and isinstance(domain, str):
        family = DIRECTORY_TO_FAMILY.get(domain)
    if not all(isinstance(value, str) and value for value in (
        domain, problem, family,
    )):
        raise ProtocolError("run-order task identity is incomplete")
    return domain, problem, family


def task_major_cell_mapping(tasks) -> list[dict]:
    """Return the deterministic task-major run order used by Lab and Slurm."""
    identities = sorted(_task_identity(task) for task in tasks)
    if len(identities) != len(set(
        (domain, problem) for domain, problem, _ in identities
    )):
        raise ProtocolError("run-order task identity is duplicated")
    fixed = PRIMARY_LABELS[:-3]
    triad = PRIMARY_LABELS[-3:]
    if triad != (PLAIN_REFERENCE_LABEL, GUIDED_LABEL, MATCHED_LABEL):
        raise ProtocolError("primary blocked triad changed")
    family_positions = Counter()
    rows = []
    for domain, problem, family in identities:
        position = family_positions[family]
        family_positions[family] += 1
        rotation = position % len(triad)
        rotated = triad[rotation:] + triad[:rotation]
        for label in (*fixed, *rotated):
            rows.append({
                "run_id": len(rows) + 1,
                "algorithm": label,
                "domain": domain,
                "problem": problem,
                "family": family,
                "family_sequence_index": position,
                "triad_position": (
                    rotated.index(label) if label in triad else None
                ),
            })
    return rows


def run_cell_mapping_digest(tasks) -> str:
    return hashlib.sha256(
        canonical_json(task_major_cell_mapping(tasks))
    ).hexdigest()


def task_major_blocked_run_order(algorithms, tasks):
    """Translate the frozen mapping into Fast Downward run objects."""
    if tuple(algorithms) != LABELS:
        raise ProtocolError("Lab algorithm insertion order changed")
    task_by_identity = {}
    for task in tasks:
        domain, problem, _ = _task_identity(task)
        identity = (domain, problem)
        if identity in task_by_identity:
            raise ProtocolError("Lab task identity is duplicated")
        task_by_identity[identity] = task
    rows = task_major_cell_mapping(tasks)
    if len(rows) != len(tasks) * CONFIG_COUNT:
        raise ProtocolError("Lab run mapping cardinality changed")
    return [
        (algorithms[row["algorithm"]], task_by_identity[
            (row["domain"], row["problem"])
        ])
        for row in rows
    ]


def option_matrix_digest(configs=CONFIGS) -> str:
    return hashlib.sha256(canonical_json([
        {"label": label, "search": search} for label, search in configs
    ])).hexdigest()


EXPERIMENT_SOURCE_FILES = (
    "experiments/analyze_pdb_terminal_incidence_confirmation_a.py",
    "experiments/analyze_pdb_terminal_incidence_confirmation_b.py",
    "experiments/analyze_pdb_terminal_incidence_shadow.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v5.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v6.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v7.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_a.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_b.py",
    "experiments/audit_pdb_terminal_incidence_shadow.py",
    "experiments/exp_arrhenius_common.py",
    "experiments/exp_pdb_profile_certificate_holdout.py",
    "experiments/exp_pdb_terminal_incidence_confirmation_a.py",
    "experiments/exp_pdb_terminal_incidence_confirmation_b.py",
    "experiments/freeze_pdb_terminal_incidence_confirmation_b.py",
    "experiments/jj_cached_revision.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v6.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v7.py",
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
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v5.py",
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v6.py",
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v7.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v5.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v6.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v7.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v7_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v7.slurm",
    "experiments/pdb_terminal_incidence_selector_parser.py",
    "experiments/pdb_terminal_incidence_shadow_protocol.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_b.py",
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
    confirmation_a_cohort_manifest_sha256: str
    records_sha256: str
    translator_source_sha256: str
    tracked_file_sha256: dict[str, str]
    tasks: tuple[dict, ...]
    directories: tuple[str, ...]
    directory_to_family: dict[str, str]
    shadow_unrepresented_families: tuple[str, ...]
    all_prior_unrepresented_families: tuple[str, ...]
    execution_receipt: dict
    launch_receipt: dict


def load_confirmation_a_authorization(
    receipt_path: Path,
    receipt_pin_path: Path,
    first_output_path: Path,
    second_output_path: Path,
) -> dict:
    """Load the sealed complete A gate through A's canonical verifier."""
    paths = tuple(Path(path) for path in (
        receipt_path, receipt_pin_path, first_output_path, second_output_path,
    ))
    expected_paths = tuple(Path(path) for path in (
        CONFIRMATION_A_RECEIPT_PATH,
        CONFIRMATION_A_RECEIPT_PIN_PATH,
        CONFIRMATION_A_FIRST_OUTPUT_PATH,
        CONFIRMATION_A_SECOND_OUTPUT_PATH,
    ))
    if tuple(map(os.fspath, paths)) != tuple(map(os.fspath, expected_paths)):
        raise ProtocolError(
            "Confirmation A authorization artifact paths changed"
        )
    receipt_path, receipt_pin_path, first_output_path, second_output_path = paths
    try:
        import analyze_pdb_terminal_incidence_confirmation_a as ConfirmationA

        receipt_sha, receipt, output = ConfirmationA.load_analysis_receipt(
            receipt_path=Path(receipt_path),
            receipt_pin=Path(receipt_pin_path),
            output=Path(first_output_path),
            repeat_output=Path(second_output_path),
            verify_live=True,
        )
        (
            records,
            properties_sha,
            fetch_sha,
            execution_sha,
            hardware,
        ) = ConfirmationA._load_sealed_input(
            ConfirmationA.Audit.EVAL_PROPERTIES
        )
        recomputed = ConfirmationA.analyze_records(records)
        recomputed["input"] = {
            "path": str(ConfirmationA.Audit.EVAL_PROPERTIES.resolve()),
            "sha256": properties_sha,
            "fetch_receipt_sha256": fetch_sha,
            "execution_receipt_sha256": execution_sha,
            "hardware": hardware,
        }
        if ConfirmationA.P.canonical_json_line(recomputed) != (
            ConfirmationA.P.canonical_json_line(output)
        ):
            raise ProtocolError(
                "Confirmation A authorization output does not recompute"
            )
    except Exception as err:
        # The concrete A exceptions are deliberately translated at this
        # protocol boundary.  B never authorizes itself from a partial A
        # result or from a lookalike receipt.
        raise ProtocolError(
            "sealed Confirmation A complete gate does not authorize B"
        ) from err
    return {
        "receipt_path": receipt_path,
        "receipt_pin_path": receipt_pin_path,
        "first_output_path": first_output_path,
        "second_output_path": second_output_path,
        "receipt_sha256": receipt_sha,
        "first_output_sha256": receipt["first_output_sha256"],
        "second_output_sha256": receipt["second_output_sha256"],
        "input_properties_sha256": receipt["input_properties_sha256"],
        "fetch_receipt_sha256": receipt["fetch_receipt_sha256"],
        "execution_receipt_sha256": receipt["execution_receipt_sha256"],
        "hardware": receipt["hardware"],
        "receipt_schema": receipt["schema"],
        "analysis_protocol": receipt["analysis_protocol"],
        "guided_study_authorized": output["guided_study_authorized"],
        "benchmark_revision": ConfirmationA.P.BENCHMARK_REVISION,
        "cost_attestation_sha256": ConfirmationA.P.COST_ATTESTATION_SHA256,
        "source_audit_launch_receipt_sha256": (
            ConfirmationA.P.SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256
        ),
        "source_audit_execution_receipt_sha256": (
            ConfirmationA.P.SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256
        ),
        "confirmation_a_cohort_manifest_sha256": (
            ConfirmationA.P.COHORT_MANIFEST_SHA256
        ),
        "planner_identity": receipt["planner_identity"],
    }


def _validate_confirmation_a_source_link(
    authorization: dict, materials: SourceMaterials
) -> None:
    expected = {
        "benchmark_revision": BENCHMARK_REVISION,
        "cost_attestation_sha256": materials.attestation_sha256,
        "source_audit_launch_receipt_sha256": materials.launch_receipt_sha256,
        "source_audit_execution_receipt_sha256": (
            materials.execution_receipt_sha256
        ),
        "confirmation_a_cohort_manifest_sha256": (
            materials.confirmation_a_cohort_manifest_sha256
        ),
    }
    if any(authorization.get(key) != value for key, value in expected.items()):
        raise ProtocolError(
            "Confirmation A authorization is not linked to B source audit"
        )


def _planner_identity(planner: dict) -> dict:
    return {
        "revision": planner.get("revision"),
        "cache_name": planner.get("cache_name"),
        "build_options": planner.get("build_options"),
        "downward_sha256": planner.get("downward_sha256"),
        "preprocess_sha256": planner.get("preprocess_sha256"),
        "tree_manifest_sha256": planner.get("tree_manifest_sha256"),
    }


def _validate_task(task: dict) -> None:
    expected_keys = {
        "candidate_index", "directory", "family", "problem",
        "domain_file", "problem_file", "domain_sha256", "problem_sha256",
        "canonical_path", "is_shadow_family", "is_shadow_unrepresented",
        "is_all_prior_represented", "is_all_prior_unrepresented", "aliases",
        "selection_role", "selection_rank_sha256",
        "source_audit_evidence_sha256", "selection_stage",
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
    stage = task.get("selection_stage")
    expected_roles = {"base": "guided-b", "top-up": "guided-b-topup"}
    if stage not in expected_roles or task["selection_role"] != expected_roles[stage]:
        raise ProtocolError("guided task has the wrong split role or stage")
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
    _validate_shared_v4_constants()
    try:
        return SourceValidation._validate_v4_original_output(
            execution, launch, source_inventory_sha256
        )
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err


def _validate_v4_scheduler_contract_rows(
    execution: dict, launch: dict, scheduler_rows: list[dict]
) -> None:
    _validate_shared_v4_constants()
    try:
        SourceValidation._validate_v4_scheduler_contract_rows(
            execution, launch, scheduler_rows
        )
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err


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
        raise ProtocolError("source audit did not authorize Confirmation B")
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
    try:
        SourceValidation._validate_attestation_envelope(attestation, inventory)
        SourceValidation._validate_attestation_split(
            attestation, manifest_hashes
        )
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err
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
    cohort = attestation.get("cohorts", {}).get("guided_b")
    tasks = cohort.get("tasks") if isinstance(cohort, dict) else None
    if (
        not isinstance(tasks, list)
        or len(tasks) != TARGET_COHORT_TASKS
        or cohort.get("role") != "guided-b"
        or cohort.get("top_up_role") != "guided-b-topup"
        or cohort.get("target_tasks") != TARGET_COHORT_TASKS
        or cohort.get("max_tasks_per_family") != 12
    ):
        raise ProtocolError("source audit has the wrong Confirmation B cohort")
    for task in tasks:
        _validate_task(task)
        try:
            SourceValidation._validate_task_inventory_binding(task, inventory)
        except SourceValidation.ProtocolError as err:
            raise ProtocolError(str(err)) from err
    candidate_indexes = [task["candidate_index"] for task in tasks]
    if len(set(candidate_indexes)) != len(candidate_indexes):
        raise ProtocolError("Confirmation B contains duplicate candidate indices")
    if max(Counter(task["family"] for task in tasks).values()) > 12:
        raise ProtocolError("source audit has the wrong Confirmation B cohort")
    cohort_sha = hashlib.sha256(canonical_json_line(tasks)).hexdigest()
    if any((
        cohort.get("tasks_sha256") != cohort_sha,
        execution.get("cohort_manifest_sha256", {}).get("guided_b")
        != cohort_sha,
        execution.get("attestation_records_sha256")
        != attestation.get("records_sha256"),
    )):
        raise ProtocolError("source-audit cohort hash chain changed")
    identities = [(task["directory"], task["problem"]) for task in tasks]
    problem_hashes = [task["problem_sha256"] for task in tasks]
    if len(set(identities)) != len(tasks) or len(set(problem_hashes)) != len(tasks):
        raise ProtocolError("Confirmation B contains duplicate sources")
    confirmation = attestation.get("cohorts", {}).get("confirmation_a", {})
    confirmation_tasks = confirmation.get("tasks")
    if not isinstance(confirmation_tasks, list):
        raise ProtocolError("source audit lacks the disjoint A cohort")
    try:
        for other in confirmation_tasks:
            SourceValidation._validate_task(other)
            SourceValidation._validate_task_inventory_binding(other, inventory)
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err
    confirmation_candidate_indexes = [
        other["candidate_index"] for other in confirmation_tasks
    ]
    if (
        len(set(confirmation_candidate_indexes)) != len(confirmation_tasks)
        or set(confirmation_candidate_indexes) & set(candidate_indexes)
    ):
        raise ProtocolError("source audit A/B candidate identities changed")
    confirmation_sha = hashlib.sha256(
        canonical_json_line(confirmation_tasks)
    ).hexdigest()
    if any((
        confirmation.get("role") != "confirmation-a",
        confirmation.get("tasks_sha256") != confirmation_sha,
        execution.get("cohort_manifest_sha256", {}).get("confirmation_a")
        != confirmation_sha,
    )):
        raise ProtocolError("source-audit Confirmation A cohort hash changed")
    confirmation_identities = {
        (other.get("directory"), other.get("problem"))
        for other in confirmation_tasks if isinstance(other, dict)
    }
    confirmation_hashes = {
        other.get("problem_sha256")
        for other in confirmation_tasks if isinstance(other, dict)
    }
    if any(
        (task["directory"], task["problem"]) in confirmation_identities
        or task["problem_sha256"] in confirmation_hashes
        for task in tasks
    ):
        raise ProtocolError("Confirmation B is not source-disjoint from A")
    directory_to_family = {}
    for task in tasks:
        previous = directory_to_family.setdefault(task["directory"], task["family"])
        if previous != task["family"]:
            raise ProtocolError("source audit maps one directory to two families")
    try:
        shadow, all_prior = SourceValidation._validate_split_strata(
            attestation, SOURCE_V4_FIXED_HASHES
        )
        SourceValidation._validate_prelaunch_gate(
            attestation, shadow, all_prior
        )
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err
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
        len(families) < MIN_COHORT_FAMILIES,
        len(shadow_families) < MIN_SHADOW_UNREPRESENTED_FAMILIES,
        len(all_prior_tasks) < MIN_ALL_PRIOR_UNREPRESENTED_TASKS,
        len(all_prior_families) < MIN_ALL_PRIOR_UNREPRESENTED_FAMILIES,
    )):
        raise ProtocolError("Confirmation B source-support floor changed")
    expected_cohort_hashes = {
        "confirmation_a": confirmation_sha,
        "guided_b": cohort_sha,
    }
    if execution.get("cohort_manifest_sha256") != expected_cohort_hashes:
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
        confirmation_a_cohort_manifest_sha256=confirmation_sha,
        records_sha256=records_sha,
        translator_source_sha256=translator_sha,
        tracked_file_sha256=tracked_file_sha256,
        tasks=tuple(tasks),
        directories=tuple(sorted(directory_to_family)),
        directory_to_family=dict(sorted(directory_to_family.items())),
        shadow_unrepresented_families=tuple(shadow),
        all_prior_unrepresented_families=tuple(all_prior),
        execution_receipt=execution,
        launch_receipt=launch,
    )


def load_source_materials(
    attestation_path: Path,
    execution_receipt_path: Path,
    launch_receipt_path: Path,
) -> SourceMaterials:
    """Use A's shared V7 validator, then project the sealed guided-B cohort."""
    try:
        source = SourceValidation.load_source_materials(
            attestation_path, execution_receipt_path, launch_receipt_path
        )
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err
    attestation = source.attestation
    inventory = source.inventory
    execution = source.execution_receipt
    cohort = attestation.get("cohorts", {}).get("guided_b")
    tasks = cohort.get("tasks") if isinstance(cohort, dict) else None
    if (
        not isinstance(tasks, list)
        or len(tasks) != TARGET_COHORT_TASKS
        or cohort.get("role") != "guided-b"
        or cohort.get("top_up_role") != "guided-b-topup"
        or not _same_exact(cohort.get("target_tasks"), TARGET_COHORT_TASKS)
        or not _same_exact(cohort.get("max_tasks_per_family"), 12)
    ):
        raise ProtocolError("V7 source audit has the wrong Confirmation B cohort")
    try:
        for task in tasks:
            _validate_task(task)
            SourceValidation._validate_task_inventory_binding(task, inventory)
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err
    candidate_indexes = [task["candidate_index"] for task in tasks]
    identities = [(task["directory"], task["problem"]) for task in tasks]
    problem_hashes = [task["problem_sha256"] for task in tasks]
    if (
        len(set(candidate_indexes)) != len(tasks)
        or len(set(identities)) != len(tasks)
        or len(set(problem_hashes)) != len(tasks)
        or max(Counter(task["family"] for task in tasks).values()) > 12
    ):
        raise ProtocolError("Confirmation B V7 source identities changed")
    cohort_sha = hashlib.sha256(canonical_json_line(tasks)).hexdigest()
    confirmation = attestation.get("cohorts", {}).get("confirmation_a")
    confirmation_tasks = (
        confirmation.get("tasks") if isinstance(confirmation, dict) else None
    )
    if not isinstance(confirmation_tasks, list):
        raise ProtocolError("V7 source audit lacks the disjoint A cohort")
    confirmation_sha = hashlib.sha256(
        canonical_json_line(confirmation_tasks)
    ).hexdigest()
    confirmation_indexes = {
        task["candidate_index"] for task in confirmation_tasks
    }
    confirmation_identities = {
        (task["directory"], task["problem"]) for task in confirmation_tasks
    }
    confirmation_hashes = {
        task["problem_sha256"] for task in confirmation_tasks
    }
    if (
        confirmation_sha != source.cohort_manifest_sha256
        or cohort.get("tasks_sha256") != cohort_sha
        or execution.get("cohort_manifest_sha256") != {
            "confirmation_a": confirmation_sha, "guided_b": cohort_sha,
        }
        or set(candidate_indexes) & confirmation_indexes
        or set(identities) & confirmation_identities
        or set(problem_hashes) & confirmation_hashes
    ):
        raise ProtocolError("V7 source audit A/B disjointness changed")
    directory_to_family = {}
    for task in tasks:
        previous = directory_to_family.setdefault(task["directory"], task["family"])
        if previous != task["family"]:
            raise ProtocolError("V7 source audit maps one directory twice")
    shadow = source.shadow_unrepresented_families
    all_prior = source.all_prior_unrepresented_families
    shadow_set = set(shadow)
    all_prior_set = set(all_prior)
    for task in tasks:
        if (
            task["is_shadow_unrepresented"] != (task["family"] in shadow_set)
            or task["is_all_prior_unrepresented"]
            != (task["family"] in all_prior_set)
        ):
            raise ProtocolError("V7 guided task stratum flag changed")
    families = {task["family"] for task in tasks}
    shadow_families = {
        task["family"] for task in tasks if task["is_shadow_unrepresented"]
    }
    all_prior_tasks = [task for task in tasks if task["is_all_prior_unrepresented"]]
    if (
        len(families) < MIN_COHORT_FAMILIES
        or len(shadow_families) < MIN_SHADOW_UNREPRESENTED_FAMILIES
        or len(all_prior_tasks) < MIN_ALL_PRIOR_UNREPRESENTED_TASKS
        or len({task["family"] for task in all_prior_tasks})
        < MIN_ALL_PRIOR_UNREPRESENTED_FAMILIES
    ):
        raise ProtocolError("Confirmation B V7 source-support floor changed")
    return SourceMaterials(
        attestation_path=source.attestation_path,
        diagnostic_path=source.diagnostic_path,
        intent_path=source.intent_path,
        execution_receipt_path=source.execution_receipt_path,
        launch_receipt_path=source.launch_receipt_path,
        attestation_sha256=source.attestation_sha256,
        diagnostic_sha256=source.diagnostic_sha256,
        intent_sha256=source.intent_sha256,
        execution_receipt_sha256=source.execution_receipt_sha256,
        launch_receipt_sha256=source.launch_receipt_sha256,
        cohort_manifest_sha256=cohort_sha,
        confirmation_a_cohort_manifest_sha256=confirmation_sha,
        records_sha256=source.records_sha256,
        translator_source_sha256=source.translator_source_sha256,
        tracked_file_sha256=source.tracked_file_sha256,
        tasks=tuple(tasks),
        directories=tuple(sorted(directory_to_family)),
        directory_to_family=dict(sorted(directory_to_family.items())),
        shadow_unrepresented_families=tuple(shadow),
        all_prior_unrepresented_families=tuple(all_prior),
        execution_receipt=source.execution_receipt,
        launch_receipt=source.launch_receipt,
    )


def _load_freeze(path: Path = FREEZE_PATH) -> tuple[dict, SourceMaterials]:
    raw, freeze = _load_canonical(path, "Confirmation B freeze")
    if (
        set(freeze) != {
            "schema", "freeze_repository_revision", "source_audit",
            "confirmation_a_authorization",
            "planner", "design", "experiment_source_sha256",
        }
        or freeze.get("schema") != FREEZE_SCHEMA
    ):
        raise ProtocolError("Confirmation B freeze schema changed")
    sources = freeze.get("source_audit")
    freeze_repository_revision = freeze.get("freeze_repository_revision")
    authorization = freeze.get("confirmation_a_authorization")
    planner = freeze.get("planner")
    design = freeze.get("design")
    source_hashes = freeze.get("experiment_source_sha256")
    if (
        COMMIT_RE.fullmatch(freeze_repository_revision or "") is None
        or not all(isinstance(value, dict) for value in (
        sources, authorization, planner, design, source_hashes
        ))
    ):
        raise ProtocolError("Confirmation B freeze is incomplete")
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
        "confirmation_a_cohort_manifest_sha256": (
            materials.confirmation_a_cohort_manifest_sha256
        ),
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
        **SourceValidation.v7_recovery_provenance(
            materials.execution_receipt
        ),
        "tracked_file_sha256": materials.tracked_file_sha256,
    }
    if intent_path != materials.intent_path or sources != expected_sources:
        raise ProtocolError("Confirmation B freeze source hashes changed")
    authorization_paths = {
        key: _safe_repo_path(authorization.get(key), key)
        for key in (
            "receipt_path", "receipt_pin_path", "first_output_path",
            "second_output_path",
        )
    }
    live_authorization = load_confirmation_a_authorization(
        authorization_paths["receipt_path"],
        authorization_paths["receipt_pin_path"],
        authorization_paths["first_output_path"],
        authorization_paths["second_output_path"],
    )
    _validate_confirmation_a_source_link(live_authorization, materials)
    expected_authorization = {
        **{key: path.relative_to(REPO).as_posix()
           for key, path in authorization_paths.items()},
        **{key: value for key, value in live_authorization.items()
           if not key.endswith("_path")},
    }
    if authorization != expected_authorization:
        raise ProtocolError("Confirmation A authorization freeze changed")
    cohort_tasks = len(materials.tasks)
    cells = cohort_tasks * CONFIG_COUNT
    array_tasks = (cells + RUNS_PER_ARRAY_TASK - 1) // RUNS_PER_ARRAY_TASK
    expected_design = {
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "option_matrix_sha256": option_matrix_digest(),
        "cohort_tasks": cohort_tasks,
        "target_cohort_tasks": TARGET_COHORT_TASKS,
        "minimum_cohort_tasks": MIN_COHORT_TASKS,
        "maximum_cohort_tasks": MAX_COHORT_TASKS,
        "configs": CONFIG_COUNT,
        "cells": cells,
        "expected_array_tasks": array_tasks,
        "runs_per_array_task": RUNS_PER_ARRAY_TASK,
        "run_order_protocol": RUN_ORDER_PROTOCOL,
        "run_cell_mapping_sha256": run_cell_mapping_digest(materials.tasks),
        "probe_layers": PROBE_LAYERS,
        "par2_seconds": PAR2_SECONDS,
        "bootstrap_replicates": BOOTSTRAP_REPLICATES,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "minimum_mechanism_tasks": MIN_MECHANISM_TASKS,
        "minimum_mechanism_families": MIN_MECHANISM_FAMILIES,
        "non_gating_reference_labels": list(NON_GATING_REFERENCE_LABELS),
    }
    if design != expected_design:
        raise ProtocolError("Confirmation B frozen design changed")
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
        raise ProtocolError("Confirmation B planner pins are invalid")
    if live_authorization.get("planner_identity") != _planner_identity(planner):
        raise ProtocolError("Confirmation A/B planner identity differs")
    if set(source_hashes) != set(EXPERIMENT_SOURCE_FILES):
        raise ProtocolError("Confirmation B executed-source set changed")
    for relative, expected in source_hashes.items():
        if SHA256_RE.fullmatch(expected or "") is None:
            raise ProtocolError("Confirmation B source hash is invalid")
        path = _safe_repo_path(relative, "experiment source")
        if sha256_file(path) != expected:
            raise ProtocolError("Confirmation B experiment source changed")
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
        "RUN_CELL_MAPPING_SHA256": "TO_FREEZE",
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
        "CONFIRMATION_A_AUTHORIZATION_RECEIPT_SHA256": "TO_FREEZE",
        "CONFIRMATION_A_COHORT_MANIFEST_SHA256": "TO_FREEZE",
        "COHORT_TASKS": 0,
        "CELL_COUNT": 0,
        "EXPECTED_ARRAY_TASKS": 0,
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
    cohort_tasks = len(materials.tasks)
    cell_count = cohort_tasks * CONFIG_COUNT
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
        "RUN_CELL_MAPPING_SHA256": run_cell_mapping_digest(materials.tasks),
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
        "CONFIRMATION_A_AUTHORIZATION_RECEIPT_SHA256": freeze[
            "confirmation_a_authorization"
        ]["receipt_sha256"],
        "CONFIRMATION_A_COHORT_MANIFEST_SHA256": (
            materials.confirmation_a_cohort_manifest_sha256
        ),
        "COHORT_TASKS": cohort_tasks,
        "CELL_COUNT": cell_count,
        "EXPECTED_ARRAY_TASKS": (
            cell_count + RUNS_PER_ARRAY_TASK - 1
        ) // RUNS_PER_ARRAY_TASK,
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


def validate_static_design() -> None:
    if any((
        LABELS != PRIMARY_LABELS,
        len(set(LABELS)) != CONFIG_COUNT,
        CONFIG_COUNT != 9,
        MIN_COHORT_TASKS != 300,
        TARGET_COHORT_TASKS != 300,
        MAX_COHORT_TASKS != 300,
        MIN_COHORT_FAMILIES != 30,
        MIN_SHADOW_UNREPRESENTED_FAMILIES != 12,
        MIN_ALL_PRIOR_UNREPRESENTED_TASKS != 50,
        MIN_ALL_PRIOR_UNREPRESENTED_FAMILIES != 10,
        RUNS_PER_ARRAY_TASK != 3,
        TIME_LIMIT_SECONDS != 1800,
        MEMORY_LIMIT_MIB != 24576,
        SCHEDULER_TIME_LIMIT != "01:40:00",
        SCHEDULER_MEMORY != "26G",
        PROBE_LAYERS != 16,
        PAR2_SECONDS != 3600,
        BOOTSTRAP_REPLICATES != 100000,
        BOOTSTRAP_SEED != 20260902,
        MIN_MECHANISM_TASKS != 50,
        MIN_MECHANISM_FAMILIES != 10,
        RUN_ORDER_PROTOCOL != "task-major-family-balanced-triads/v1",
        ACCOUNT != "naiss2025-5-561-cpu",
        PLANNER_REVISION_REQUIRED
        != "8148f798f13059ee881ad2471bd20cdd61d2ec18",
        PLAIN_REFERENCE_LABEL != "pdb_cap_aware_k32",
        GUIDED_LABEL != "pdb_terminal_incidence_guided",
        MATCHED_LABEL != "pdb_terminal_incidence_matched",
        SELECTOR_TRACE_SCHEMA
        != "symbolic-search-heuristics/terminal-incidence-selector-trace/v3",
        NON_GATING_REFERENCE_LABELS != (
            "blind_fw", "pdb_bdd_prefix", "pdb_goal_prefix",
            "pdb_goal_fill", "pdb_cegar_deterministic",
            "pdb_exact_width_k32",
        ),
        set(NON_GATING_REFERENCE_LABELS)
        != set(PRIMARY_LABELS) - {
            PLAIN_REFERENCE_LABEL, GUIDED_LABEL, MATCHED_LABEL,
        },
        SEARCHES.get("blind_fw") != "sym_fw()",
    )):
        raise ProtocolError("Confirmation B static design constants changed")
    modes = {
        "pdb_bdd_prefix": "bdd_prefix",
        "pdb_goal_prefix": "goal_prefix",
        "pdb_goal_fill": "goal_fill",
        "pdb_cegar_deterministic": "cegar",
        "pdb_exact_width_k32": "exact_width_filter",
        "pdb_cap_aware_k32": "exact_width_filter",
        "pdb_terminal_incidence_guided": "terminal_incidence_guided",
        "pdb_terminal_incidence_matched": (
            "terminal_incidence_matched_control"
        ),
    }
    for label, search in CONFIGS:
        if "shadow_partition=true" in search:
            raise ProtocolError("B configuration accidentally enables shadow mode")
        if label == "blind_fw":
            continue
        required = (
            "budget=100000",
            "pattern_selection={}".format(modes[label]),
            "value_cap=-1",
            "total_add_node_budget=infinity",
            "gamer_ordering=false",
            "dynamic_reordering=false",
            "shadow_partition=false",
            "prune_only=false",
            "batch_f_window=0",
        )
        if any(search.count(item) != 1 for item in required):
            raise ProtocolError("configuration contract changed for {}".format(label))
        pool_options = (
            "cegar_max_time=infinity",
            "cegar_max_refinements=128",
            "cegar_seed=2011",
        )
        pool_labels = {
            "pdb_cegar_deterministic", "pdb_exact_width_k32",
            "pdb_cap_aware_k32", GUIDED_LABEL, MATCHED_LABEL,
        }
        if label in pool_labels and any(search.count(item) != 1
                                        for item in pool_options):
            raise ProtocolError("deterministic pool contract changed")
        if label not in pool_labels and any(item in search for item in pool_options):
            raise ProtocolError("direct prefix gained pool-generation options")
        exact_k32 = label in {"pdb_exact_width_k32", "pdb_cap_aware_k32"}
        expected_width = (
            "cofactor_width_budget=32" if exact_k32
            else "cofactor_width_budget=infinity"
        )
        if search.count(expected_width) != 1:
            raise ProtocolError("cofactor-width contract changed")
        expected_cap_selection = (
            label == "pdb_cap_aware_k32"
        )
        if search.count("select_value_cap={}".format(
            "true" if expected_cap_selection else "false"
        )) != 1:
            raise ProtocolError("cap-selection contract changed")
        selector = label in {GUIDED_LABEL, MATCHED_LABEL}
        if selector != (search.count(
            'incidence_selector_log="{}"'.format(SELECTOR_TRACE)
        ) == 1):
            raise ProtocolError("selector trace contract changed")


def validate_protocol_design() -> None:
    validate_static_design()
    if any((
        COHORT_TASKS != TARGET_COHORT_TASKS,
        CELL_COUNT != CONFIG_COUNT * COHORT_TASKS,
        EXPECTED_ARRAY_TASKS
        != (CELL_COUNT + RUNS_PER_ARRAY_TASK - 1) // RUNS_PER_ARRAY_TASK,
        (EXPECTED_ARRAY_TASKS - 1) * RUNS_PER_ARRAY_TASK >= CELL_COUNT,
        EXPECTED_ARRAY_TASKS * RUNS_PER_ARRAY_TASK < CELL_COUNT,
        RUN_CELL_MAPPING_SHA256 == "TO_FREEZE",
    )):
        raise ProtocolError("Confirmation B frozen cardinalities changed")


def validate_protocol_without_sources() -> None:
    _load_freeze(FREEZE_PATH)
    validate_protocol_design()


validate_protocol_without_archive = validate_protocol_without_sources


if __name__ == "__main__":
    validate_protocol_without_sources()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            COHORT_TASKS, CONFIG_COUNT, CELL_COUNT
        )
    )
