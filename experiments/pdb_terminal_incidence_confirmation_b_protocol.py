#!/usr/bin/env python3
"""Frozen protocol and source loader for terminal-incidence Confirmation B."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass
from pathlib import Path

import pdb_terminal_incidence_confirmation_a_protocol as SourceValidation
import pdb_terminal_incidence_confirmation_v12_adapter as SourceV12


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
FROZEN_SOURCE_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-b-source/v1/campaign-v12"
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
PROTOCOL = "pdb-terminal-incidence-confirmation-b-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-terminal-incidence-confirmation-b-analysis-v3"
CONFIRMATION_A_RECEIPT_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-a-analysis/v4/double-execution"
)
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
        return SourceValidation.sha256_file(Path(path))
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err


def _load_canonical(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        return SourceValidation._load_canonical(Path(path), label)
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
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v12.py",
    "experiments/pdb_terminal_incidence_confirmation_v12_adapter.py",
    "experiments/pdb_terminal_incidence_selector_parser.py",
    "experiments/pdb_terminal_incidence_v12_snapshot_reader.py",
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
    source_audit: dict
    bindings: dict
    tasks: tuple[dict, ...]
    cohort_role: str
    candidate_indices_sha256: str
    source_projection_sha256: str
    confirmation_a_candidate_indices_sha256: str
    confirmation_a_source_projection_sha256: str
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

    @property
    def confirmation_a_cohort_manifest_sha256(self) -> str:
        return self.confirmation_a_source_projection_sha256


def _plain_v12(value):
    if is_dataclass(value):
        return {
            field.name: _plain_v12(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, Mapping):
        if any(type(key) is not str for key in value):
            raise ProtocolError("V12 source mapping key is not text")
        return {key: _plain_v12(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain_v12(item) for item in value]
    if value is None or type(value) in (bool, int, float, str):
        return value
    raise ProtocolError("V12 source value is not canonical JSON")


def _source_payload(authorized) -> dict:
    if type(authorized) is not SourceV12.AuthorizedV12Cohorts:
        raise ProtocolError("V12 adapter returned an unexpected result")
    return {
        "schema": FROZEN_SOURCE_SCHEMA,
        "source_seal_revision": authorized.bindings.seal_repository_commit_id,
        "bindings": _plain_v12(authorized.bindings),
        "guided_b": _plain_v12(authorized.guided_b),
    }


def _validate_native_task(task: dict) -> None:
    try:
        SourceValidation._validate_native_task(task)
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err).replace("Confirmation A", "Confirmation B")) \
            from err


def _validate_v12_bindings(bindings: dict, source_seal_revision: str) -> None:
    try:
        SourceValidation._validate_v12_bindings(
            bindings, source_seal_revision,
        )
    except SourceValidation.ProtocolError as err:
        raise ProtocolError(str(err)) from err


def _materials_from_frozen_source(source: dict) -> SourceMaterials:
    if not isinstance(source, dict) or set(source) != {
        "schema", "source_seal_revision", "bindings", "guided_b",
    } or source.get("schema") != FROZEN_SOURCE_SCHEMA:
        raise ProtocolError("Confirmation B frozen source shape changed")
    revision = source.get("source_seal_revision")
    _validate_v12_bindings(source.get("bindings"), revision)
    bindings = source["bindings"]
    cohort = source.get("guided_b")
    if not isinstance(cohort, dict) or set(cohort) != {
        "role", "records", "candidate_indices_sha256",
        "source_projection_sha256",
    } or cohort.get("role") != "guided-b":
        raise ProtocolError("Confirmation B frozen cohort shape changed")
    tasks = cohort.get("records")
    if not isinstance(tasks, list) or len(tasks) != TARGET_COHORT_TASKS:
        raise ProtocolError("Confirmation B frozen cohort cardinality changed")
    for task in tasks:
        _validate_native_task(task)
    indices = [task["candidate_index"] for task in tasks]
    identities = [(task["directory"], task["problem"]) for task in tasks]
    problem_hashes = [task["problem_sha256"] for task in tasks]
    if (
        len(set(indices)) != TARGET_COHORT_TASKS
        or len(set(identities)) != TARGET_COHORT_TASKS
        or len(set(problem_hashes)) != TARGET_COHORT_TASKS
        or hashlib.sha256(canonical_json(indices)).hexdigest()
        != cohort["candidate_indices_sha256"]
        or hashlib.sha256(canonical_json(tasks)).hexdigest()
        != cohort["source_projection_sha256"]
        or cohort["candidate_indices_sha256"]
        != bindings["guided_b_candidate_indices_sha256"]
        or cohort["source_projection_sha256"]
        != bindings["guided_b_source_projection_sha256"]
    ):
        raise ProtocolError("Confirmation B frozen cohort hash changed")
    directory_to_family = {}
    for task in tasks:
        previous = directory_to_family.setdefault(task["directory"], task["family"])
        if previous != task["family"]:
            raise ProtocolError("Confirmation B directory maps to two families")
    families = set(directory_to_family.values())
    per_family = Counter(task["family"] for task in tasks)
    shadow = sorted({
        task["family"] for task in tasks
        if task["is_shadow_unrepresented"]
    })
    all_prior_tasks = [
        task for task in tasks if task["is_all_prior_unrepresented"]
    ]
    all_prior = sorted({task["family"] for task in all_prior_tasks})
    if (
        len(families) < MIN_COHORT_FAMILIES
        or bindings["inventory_families_count"] < len(families)
        or max(per_family.values(), default=0) > 12
        or len(shadow) < MIN_SHADOW_UNREPRESENTED_FAMILIES
        or len(all_prior_tasks) < MIN_ALL_PRIOR_UNREPRESENTED_TASKS
        or len(all_prior) < MIN_ALL_PRIOR_UNREPRESENTED_FAMILIES
    ):
        raise ProtocolError("Confirmation B frozen family floor changed")
    return SourceMaterials(
        source_audit=source,
        bindings=bindings,
        tasks=tuple(tasks),
        cohort_role=cohort["role"],
        candidate_indices_sha256=cohort["candidate_indices_sha256"],
        source_projection_sha256=cohort["source_projection_sha256"],
        confirmation_a_candidate_indices_sha256=(
            bindings["confirmation_a_candidate_indices_sha256"]
        ),
        confirmation_a_source_projection_sha256=(
            bindings["confirmation_a_source_projection_sha256"]
        ),
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


def _v12_source_provenance(materials: SourceMaterials) -> dict:
    bindings = materials.bindings
    return {
        "source_audit_campaign": "v12-full-census",
        "source_audit_launch_receipt_sha256": bindings["launch_receipt_sha256"],
        "source_audit_execution_receipt_sha256": (
            bindings["execution_receipt_sha256"]
        ),
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
        "source_audit_guided_b_indices_sha256": (
            materials.candidate_indices_sha256
        ),
        "source_audit_guided_b_projection_sha256": (
            materials.source_projection_sha256
        ),
    }


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
        "source_audit_provenance": ConfirmationA.P.v12_run_provenance(),
        "confirmation_a_freeze_path": ConfirmationA.P.FREEZE_PATH,
        "confirmation_a_freeze_repository_revision": (
            ConfirmationA.P.FREEZE_REPOSITORY_REVISION
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
    source_provenance = authorization.get("source_audit_provenance")
    expected_provenance = _v12_source_provenance(materials)
    if (
        authorization.get("guided_study_authorized") is not True
        or any(authorization.get(key) != value for key, value in expected.items())
        or not isinstance(source_provenance, dict)
        or set(source_provenance) != (
            set(expected_provenance) | {"confirmation_a_freeze_sha256"}
        )
        or any(source_provenance.get(key) != value
               for key, value in expected_provenance.items())
        or SHA256_RE.fullmatch(
            source_provenance.get("confirmation_a_freeze_sha256", "")
        ) is None
    ):
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


def load_source_materials(source_seal_revision: str) -> SourceMaterials:
    """Load the authorized source projection from one immutable V12 seal."""
    if not isinstance(source_seal_revision, str):
        raise ProtocolError("V12 source seal revision is malformed")
    try:
        authorized = SourceV12.load_authorized_cohorts(source_seal_revision)
    except (
        SourceV12.V12AdapterError,
        SourceV12.SourceV12.SourceConsumerError,
    ) as err:
        raise ProtocolError(str(err)) from err
    source = _source_payload(authorized)
    if source["source_seal_revision"] != source_seal_revision:
        raise ProtocolError("V12 adapter returned the wrong seal revision")
    return _materials_from_frozen_source(source)


_CONFIRMATION_A_AUTHORIZATION_KEYS = frozenset({
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
})


def _validate_frozen_confirmation_a_authorization(
    authorization: dict, materials: SourceMaterials, planner: dict,
) -> None:
    expected_paths = {
        "receipt_path": CONFIRMATION_A_RECEIPT_PATH.relative_to(REPO).as_posix(),
        "receipt_pin_path": (
            CONFIRMATION_A_RECEIPT_PIN_PATH.relative_to(REPO).as_posix()
        ),
        "first_output_path": (
            CONFIRMATION_A_FIRST_OUTPUT_PATH.relative_to(REPO).as_posix()
        ),
        "second_output_path": (
            CONFIRMATION_A_SECOND_OUTPUT_PATH.relative_to(REPO).as_posix()
        ),
        "confirmation_a_freeze_path": (
            SourceValidation.FREEZE_PATH.relative_to(REPO).as_posix()
        ),
    }
    hash_fields = (
        "receipt_sha256", "first_output_sha256", "second_output_sha256",
        "input_properties_sha256", "fetch_receipt_sha256",
        "execution_receipt_sha256", "cost_attestation_sha256",
        "source_audit_launch_receipt_sha256",
        "source_audit_execution_receipt_sha256",
        "confirmation_a_cohort_manifest_sha256",
    )
    if (
        not isinstance(authorization, dict)
        or set(authorization) != _CONFIRMATION_A_AUTHORIZATION_KEYS
        or any(authorization.get(key) != value
               for key, value in expected_paths.items())
        or any(SHA256_RE.fullmatch(authorization.get(key, "")) is None
               for key in hash_fields)
        or authorization.get("first_output_sha256")
        != authorization.get("second_output_sha256")
        or authorization.get("guided_study_authorized") is not True
        or authorization.get("benchmark_revision") != BENCHMARK_REVISION
        or authorization.get("analysis_protocol")
        != SourceValidation.ANALYSIS_PROTOCOL
        or COMMIT_RE.fullmatch(authorization.get(
            "confirmation_a_freeze_repository_revision", ""
        )) is None
        or authorization.get("receipt_schema") != CONFIRMATION_A_RECEIPT_SCHEMA
        or not isinstance(authorization.get("hardware"), dict)
        or authorization.get("planner_identity") != _planner_identity(planner)
    ):
        raise ProtocolError("Confirmation A authorization freeze changed")
    _validate_confirmation_a_source_link(authorization, materials)


def _load_freeze(path: Path = FREEZE_PATH) -> tuple[dict, SourceMaterials]:
    _raw, freeze = _load_canonical(path, "Confirmation B freeze")
    if (
        set(freeze) != {
            "schema", "freeze_repository_revision", "source_audit",
            "confirmation_a_authorization", "planner", "design",
            "experiment_source_sha256",
        }
        or freeze.get("schema") != FREEZE_SCHEMA
        or COMMIT_RE.fullmatch(freeze.get("freeze_repository_revision", ""))
        is None
    ):
        raise ProtocolError("Confirmation B freeze schema changed")
    materials = _materials_from_frozen_source(freeze.get("source_audit"))
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
        raise ProtocolError("Confirmation B planner pins are invalid")
    _validate_frozen_confirmation_a_authorization(
        freeze.get("confirmation_a_authorization"), materials, planner,
    )
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
    if freeze.get("design") != expected_design:
        raise ProtocolError("Confirmation B frozen design changed")
    source_hashes = freeze.get("experiment_source_sha256")
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(
        EXPERIMENT_SOURCE_FILES
    ):
        raise ProtocolError("Confirmation B executed-source set changed")
    for relative, expected in source_hashes.items():
        if SHA256_RE.fullmatch(expected or "") is None:
            raise ProtocolError("Confirmation B source hash is invalid")
        if sha256_file(_safe_repo_path(relative, "experiment source")) != expected:
            raise ProtocolError("Confirmation B experiment source changed")
    return freeze, materials


def _unfrozen_defaults() -> dict:
    names = (
        "PROTOCOL_SHA256", "OPTION_MATRIX_SHA256", "PLANNER_REVISION",
        "FREEZE_REPOSITORY_REVISION", "PLANNER_CACHE_NAME",
        "PLANNER_BINARY_SHA256", "PREPROCESS_BINARY_SHA256",
        "PLANNER_TREE_MANIFEST_SHA256", "COHORT_MANIFEST_SHA256",
        "TASK_NAME_SHA256", "RUN_CELL_MAPPING_SHA256",
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
        "CONFIRMATION_A_AUTHORIZATION_RECEIPT_SHA256",
        "CONFIRMATION_A_COHORT_MANIFEST_SHA256",
        "CONFIRMATION_A_FREEZE_SHA256",
    )
    return {
        **{name: "TO_FREEZE" for name in names},
        "COHORT_TASKS": 0, "CELL_COUNT": 0, "EXPECTED_ARRAY_TASKS": 0,
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
    authorization = freeze["confirmation_a_authorization"]
    cohort_tasks = len(materials.tasks)
    cell_count = cohort_tasks * CONFIG_COUNT
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
        "RUN_CELL_MAPPING_SHA256": run_cell_mapping_digest(materials.tasks),
        "COST_ATTESTATION_SHA256": bindings["attestation_sha256"],
        "COST_ATTESTATION_RECORDS_SHA256": bindings["all_records_sha256"],
        "TRANSLATOR_SOURCE_SHA256": bindings["translator_source_sha256"],
        "SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256": bindings[
            "launch_receipt_sha256"
        ],
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
        "SOURCE_AUDIT_CONFIRMATION_A_INDICES_SHA256": bindings[
            "confirmation_a_candidate_indices_sha256"
        ],
        "SOURCE_AUDIT_CONFIRMATION_A_PROJECTION_SHA256": bindings[
            "confirmation_a_source_projection_sha256"
        ],
        "SOURCE_AUDIT_GUIDED_B_INDICES_SHA256": (
            materials.candidate_indices_sha256
        ),
        "SOURCE_AUDIT_GUIDED_B_PROJECTION_SHA256": (
            materials.source_projection_sha256
        ),
        "CONFIRMATION_A_AUTHORIZATION_RECEIPT_SHA256": authorization[
            "receipt_sha256"
        ],
        "CONFIRMATION_A_COHORT_MANIFEST_SHA256": (
            materials.confirmation_a_source_projection_sha256
        ),
        "CONFIRMATION_A_FREEZE_SHA256": authorization[
            "source_audit_provenance"
        ]["confirmation_a_freeze_sha256"],
        "COHORT_TASKS": cohort_tasks,
        "CELL_COUNT": cell_count,
        "EXPECTED_ARRAY_TASKS": (
            cell_count + RUNS_PER_ARRAY_TASK - 1
        ) // RUNS_PER_ARRAY_TASK,
        "DIRECTORIES": materials.directories,
        "DIRECTORY_TO_FAMILY": materials.directory_to_family,
        "COHORT_DIRECTORIES": len(materials.directories),
        "COHORT_DOMAINS": len(materials.directories),
        "COHORT_FAMILIES": len(set(materials.directory_to_family.values())),
        "SHADOW_UNREPRESENTED_FAMILIES": (
            materials.shadow_unrepresented_families
        ),
        "ALL_PRIOR_UNREPRESENTED_FAMILIES": (
            materials.all_prior_unrepresented_families
        ),
    })
    return values


globals().update(_installed_values())


def v12_run_provenance() -> dict:
    """Return the canonical V12 source projection for every B cell."""
    if not FREEZE_PATH.exists():
        raise ProtocolError("Confirmation B freeze is not installed")
    _freeze, materials = _load_freeze(FREEZE_PATH)
    return {
        **_v12_source_provenance(materials),
        "confirmation_b_freeze_sha256": sha256_file(FREEZE_PATH),
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
