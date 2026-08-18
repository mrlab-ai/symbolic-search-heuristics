#!/usr/bin/env python3
"""Frozen identities and promotion rule for the focused cap-grid census.

This module contains no scheduler entry point.  In particular, the promotion
gate refuses to open the outcome-bearing development properties until their
canonical digest has been reviewed and pinned in a descendant commit.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import math
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_pdb_cap_grid_pilot as screen_analyzer
import exp_arrhenius_selector_full as full_base
import exp_pdb_cap_grid_pilot as screen_runner


class ProtocolError(RuntimeError):
    pass


PROTOCOL = "pdb-cap-grid-focused-full-evaluation-v1"
ANALYSIS_PROTOCOL = "pdb-cap-grid-focused-full-analysis-v1"
# Set in a descendant pin commit to the hash of this outcome-independent
# implementation commit.  The launch revision itself is the clean descendant
# HEAD containing reviewed screen/job pins, and is recorded dynamically.
PROTOCOL_IMPLEMENTATION_REVISION = "13026ed5e85f32fbdc5879a8348130a661e3b5a7"
PLANNER_REVISION = "e04d56cc61d00c954f2369e9fb74bd469277d52e"
CACHE_BINARY_SHA256 = (
    "77cf4950563be2d2a60aded13783a3ffe26c0c8391ac9d626f3bd618231941fa"
)
CACHE_PREPROCESS_SHA256 = (
    "fc3233bfd260210cf4d0cce11146fe6f3198820d6e19a8b56740c1240039378b"
)
CACHE_NAME_SUFFIX = "_61a748e5"

SCREEN_PROTOCOL_REVISION = "6fb512eb6b0359b38f23e4f72053d0027b697e00"
SCREEN_PROTOCOL = "pdb-cap-grid-development-screen-v3"
SCREEN_PLANNER_REVISION = PLANNER_REVISION
SCREEN_CACHE_BINARY_SHA256 = CACHE_BINARY_SHA256
SCREEN_CACHE_PREPROCESS_SHA256 = CACHE_PREPROCESS_SHA256
EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256 = None

CONFIGS = (
    ("blind_fw", "sym_fw()"),
    (
        "ms_exact",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false)",
    ),
    (
        "pdb_cegar_b100k",
        "sym_fw_pdb(budget=100000,pattern_selection=cegar,"
        "cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_selector_k8",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=8,cegar_max_time=10,cegar_seed=2011)",
    ),
    (
        "pdb_cap_grid_k8",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=8,cegar_max_time=10,cegar_seed=2011,"
        "select_value_cap=true)",
    ),
)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
BLIND = "blind_fw"
MS_EXACT = "ms_exact"
CEGAR = "pdb_cegar_b100k"
EXACT = "pdb_selector_k8"
CAP = "pdb_cap_grid_k8"
OPTION_MATRIX_SHA256 = (
    "94238d64a699142ef81cc4a35489467af8b78dcdf46973536556eb7e3f6b6f78"
)

EXPECTED_TASKS = 1377
EXPECTED_DOMAINS = 46
EXPECTED_CONFIGS = 5
EXPECTED_CELLS = 6885
EXPECTED_TASK_MANIFEST_SHA256 = full_base.EXPECTED_TASK_MANIFEST_SHA256
EXPECTED_DOMAIN_SEQUENCE_SHA256 = full_base.EXPECTED_DOMAIN_SEQUENCE_SHA256
EXPECTED_DOMAIN_TASK_COUNTS_SHA256 = full_base.EXPECTED_DOMAIN_TASK_COUNTS_SHA256
EXPECTED_TASK_SOURCES_SHA256 = full_base.EXPECTED_TASK_SOURCES_SHA256
EXPECTED_SOURCE_MANIFEST_SHA256 = full_base.EXPECTED_SOURCE_MANIFEST_SHA256
EXPECTED_PRIMARY_TASKS = 1327
EXPECTED_PRIMARY_DOMAINS = 46
EXPECTED_PRIMARY_TASK_MANIFEST_SHA256 = (
    full_base.EXPECTED_SCREEN_EXCLUDED_TASK_MANIFEST_SHA256
)
EXPECTED_PRIMARY_TASK_SOURCES_SHA256 = (
    full_base.EXPECTED_SCREEN_EXCLUDED_TASK_SOURCES_SHA256
)
SCREEN_MANIFEST_SHA256 = screen_runner.MANIFEST_DIGEST

EXPECTED_PDDL_BYTES_PER_CONFIG = full_base.EXPECTED_PDDL_BYTES_PER_CONFIG
EXPECTED_UNIQUE_PDDL_SOURCE_FILES = full_base.EXPECTED_UNIQUE_PDDL_SOURCE_FILES
EXPECTED_UNIQUE_PDDL_SOURCE_BYTES = full_base.EXPECTED_UNIQUE_PDDL_SOURCE_BYTES
EXPECTED_MATERIALIZED_PDDL_FILES = 13770
EXPECTED_MATERIALIZED_PDDL_BYTES = 764795335
MATERIALIZED_PDDL_PROTOCOL = full_base.MATERIALIZED_PDDL_PROTOCOL

EXPECTED_ARRAY_TASKS = 984
EXPECTED_RUNS_PER_ARRAY_TASK = 7
SCHEDULER_TIME_LIMIT = "00:45:00"
SCHEDULER_TIME_LIMIT_SECONDS = 45 * 60
EXPECTED_ARRAY_ASSIGNMENT_SHA256 = (
    "977a1cac30b027990c8ed5f23803032a351c9497b26a837b303ba9604fc4f775"
)
EXPECTED_FINAL_LOGICAL_GROUP_SLURM_ID = 472
EXPECTED_PROSPECTIVE_JOB_SHA256 = None
WRAPPER_ALLOWANCE_SECONDS_PER_RUN = 60
PLANNER_SOFT_STDOUT_LIMIT_KIB = screen_runner.PLANNER_SOFT_STDOUT_LIMIT_KIB
PLANNER_HARD_STDOUT_LIMIT_KIB = screen_runner.PLANNER_HARD_STDOUT_LIMIT_KIB

PROMOTION_RULE = {
    "protocol": "complete-cap-grid-screen-k8-promotion-v1",
    "screen_cells": 300,
    "screen_tasks": 50,
    "screen_configs": 6,
    "complete_matrix_required": True,
    "all_exact_cap_k8_raw_pools_must_match": True,
    "all_solved_costs_must_agree": True,
    "cap_k8_semantic_nontrivial_must_strictly_exceed_exact_k8": True,
    "cap_k8_coverage_wins_minus_losses_minimum": 0,
    "k32_may_substitute": False,
}
PROMOTION_RULE_SHA256 = (
    "2c19a90e46eeda33ca5b0d2325efc95b7ff3a51e3d055996a92143d935539a8c"
)
PROMOTION_IMPLEMENTATION_SHA256 = (
    "3af338448139607e8e69bceb7a3d6e6584edf453d04f53e799bbae6fd37a90b4"
)

ANALYSIS_PREDECLARATION = {
    "status": "prospective-before-development-screen-aggregate-inspection",
    "primary_population": "frozen-full-population-minus-50-development-tasks",
    "primary_task_count": EXPECTED_PRIMARY_TASKS,
    "primary_domain_count": EXPECTED_PRIMARY_DOMAINS,
    "primary_contrast": (
        "cap-k8-minus-exact-k8-equal-domain-macro-coverage/v1"
    ),
    "primary_task_micro_summary": (
        "paired-wins-losses-both-solved-both-unsolved-discordance/v1"
    ),
    "context_configs": [BLIND, MS_EXACT, CEGAR],
    "context_role": "descriptive-only",
    "mechanism": {
        "raw_pool_identity": "same-k-exact-vs-cap-grid-required/v1",
        "semantic_nontrivial": "finite-sum-positive-or-dead-count-positive/v1",
        "selection_difference_required_for_mechanism_claim": True,
    },
    "prespecified_sensitivity": {
        "population": "all-1377-frozen-supported-tasks-including-development",
        "scope_role": "census-sensitivity-not-primary",
    },
    "confidence_intervals": None,
    "p_values": None,
    "population_inference": "none-fixed-populations",
    "reranking": False,
}

COMPLETION_POLICY = copy.deepcopy(full_base.FULL_COMPLETION_POLICY)
COMPLETION_POLICY["recovery"] = (
    "Reuse the P6 atomic completion-marker and requeue archive protocol. "
    "After terminal collection, any missing, duplicate, starved, or "
    "unrecognized infrastructure cell invalidates this census; no post-hoc "
    "cell fill is permitted."
)


def canonical_json(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as err:
        raise ProtocolError("value is not canonical finite JSON: {}".format(err))


def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def require_sha256(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ProtocolError("{} must be 64 lowercase hexadecimal digits".format(label))
    if len(set(value)) == 1:
        raise ProtocolError("{} still looks synthetic".format(label))


def require_revision(value, label):
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{40}", value) is None:
        raise ProtocolError("{} must be 40 lowercase hexadecimal digits".format(label))


def option_matrix_digest(configs=CONFIGS):
    return sha256_json(
        [{"label": label, "search": search} for label, search in configs]
    )


def validate_layout(num_runs=EXPECTED_CELLS):
    if num_runs != EXPECTED_CELLS:
        raise ProtocolError("focused full run count must be exactly 6,885")
    array_tasks, runs_per_array_task = full_base.C.run_layout(num_runs)
    if (array_tasks, runs_per_array_task) != (
        EXPECTED_ARRAY_TASKS,
        EXPECTED_RUNS_PER_ARRAY_TASK,
    ):
        raise ProtocolError("focused full array layout changed")
    required = runs_per_array_task * (
        screen_analyzer.TIME_LIMIT_SECONDS + WRAPPER_ALLOWANCE_SECONDS_PER_RUN
    )
    if SCHEDULER_TIME_LIMIT_SECONDS < required:
        raise ProtocolError("focused full scheduler envelope is too short")
    full_groups, partial_runs = divmod(num_runs, runs_per_array_task)
    partial_groups = int(partial_runs != 0)
    if full_groups + partial_groups != array_tasks:
        raise ProtocolError("focused full group distribution changed")
    return {
        "raw_runs": num_runs,
        "array_tasks": array_tasks,
        "runs_per_array_task": runs_per_array_task,
        "array_task_run_distribution": {
            "full_array_tasks": full_groups,
            "full_runs_per_array_task": runs_per_array_task,
            "partial_array_tasks": partial_groups,
            "partial_runs": partial_runs,
        },
        "scheduler_time_limit_seconds": SCHEDULER_TIME_LIMIT_SECONDS,
        "wrapper_allowance_seconds_per_run": WRAPPER_ALLOWANCE_SECONDS_PER_RUN,
    }


def array_assignment():
    layout = validate_layout()
    groups = list(range(1, layout["array_tasks"] + 1))

    def key(group_id):
        payload = "{}\0{}\0{}".format(
            full_base.C.TASK_ORDER_SEED, layout["array_tasks"], group_id
        )
        return hashlib.sha256(payload.encode("utf-8")).digest(), group_id

    groups.sort(key=key)
    digest = sha256_json(groups)
    final_id = groups.index(layout["array_tasks"]) + 1
    if digest != EXPECTED_ARRAY_ASSIGNMENT_SHA256:
        raise ProtocolError("focused full array-assignment digest changed")
    if final_id != EXPECTED_FINAL_LOGICAL_GROUP_SLURM_ID:
        raise ProtocolError("focused full final-group array ID changed")
    return {
        "protocol": full_base.C.TASK_ORDER_METHOD,
        "slurm_id_to_logical_group_sha256": digest,
        "final_logical_group": layout["array_tasks"],
        "final_logical_group_slurm_id": final_id,
        "final_logical_group_runs": (
            layout["array_task_run_distribution"]["partial_runs"]
            or layout["runs_per_array_task"]
        ),
    }


def validate_matrix(tasks):
    if len(tasks) != EXPECTED_TASKS or len(set(tasks)) != EXPECTED_TASKS:
        raise ProtocolError("focused full task census changed")
    if len(CONFIGS) != EXPECTED_CONFIGS:
        raise ProtocolError("focused full matrix must contain exactly five configs")
    labels = [label for label, _ in CONFIGS]
    searches = [search for _, search in CONFIGS]
    if len(set(labels)) != len(labels) or len(set(searches)) != len(searches):
        raise ProtocolError("focused full labels/searches must be unique")
    for label, search in CONFIGS:
        if re.fullmatch(r"[a-z][a-z0-9_]*", label) is None:
            raise ProtocolError("invalid configuration label {!r}".format(label))
        full_base.C.search_config(search)
    digest = option_matrix_digest()
    if digest != OPTION_MATRIX_SHA256:
        raise ProtocolError("focused full option matrix changed")
    if len(tasks) * len(CONFIGS) != EXPECTED_CELLS:
        raise ProtocolError("focused full cell product changed")
    return {
        "configs": list(CONFIGS),
        "matrix_digest": digest,
        "run_count": EXPECTED_CELLS,
        "layout": validate_layout(),
    }


def load_full_tasks():
    tasks, attestation = full_base.read_full_tasks()
    expected = {
        "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
        "domain_sequence_sha256": EXPECTED_DOMAIN_SEQUENCE_SHA256,
        "domain_task_counts_sha256": EXPECTED_DOMAIN_TASK_COUNTS_SHA256,
        "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
        "screen_excluded_task_manifest_sha256": (
            EXPECTED_PRIMARY_TASK_MANIFEST_SHA256
        ),
        "screen_excluded_task_sources_sha256": (
            EXPECTED_PRIMARY_TASK_SOURCES_SHA256
        ),
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
    }
    if attestation != expected:
        raise ProtocolError("focused full task/source attestation changed")
    validate_matrix(tasks)
    return tasks, attestation


def primary_tasks(full_tasks):
    screen = screen_analyzer.load_tasks()
    screen_set = set(screen)
    result = [tuple(task.split(":", 1)) for task in full_tasks]
    result = [task for task in result if task not in screen_set]
    digest = hashlib.sha256(
        "".join("{}:{}\n".format(*task) for task in result).encode("utf-8")
    ).hexdigest()
    if (
        len(screen_set) != 50
        or len(result) != EXPECTED_PRIMARY_TASKS
        or len({domain for domain, _ in result}) != EXPECTED_PRIMARY_DOMAINS
        or digest != EXPECTED_PRIMARY_TASK_MANIFEST_SHA256
    ):
        raise ProtocolError("focused primary complement changed")
    return result


def _require_screen_properties_pin():
    if EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256 is None:
        raise ProtocolError(
            "screen properties SHA-256 is unset; refusing to read screen outcomes"
        )
    require_sha256(
        EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256,
        "screen properties canonical SHA-256",
    )


def _screen_properties_digest(records):
    return screen_analyzer.legacy.logical_properties_sha256(records)


def promotion_checks(primary, *, record_count, matrix_count):
    """Apply the frozen Boolean promotion boundary to a validated K=8 result."""
    if primary.get("candidate") != CAP or primary.get("reference") != EXACT:
        raise ProtocolError("screen primary comparison is not cap-K8 vs exact-K8")
    coverage = primary.get("coverage", {})
    raw = primary.get("raw_pool_isolation", {})
    semantic = primary.get("semantic_nontrivial_selection", {})
    return {
        "complete_300_cell_screen": record_count == 300 and matrix_count == 300,
        "all_k8_raw_pools_match": (
            raw.get("status") == "certified"
            and raw.get("matching_complete_cross_protocol_fingerprints") == 50
            and raw.get("required") == 50
        ),
        # validate_records reaches this function only after checking every
        # solved cost and every solved/proved-unsolvable cross-configuration
        # pair.  This field records that validated precondition.
        "solved_costs_agree": True,
        "cap_k8_has_strictly_more_semantic_nontrivial_selections": (
            semantic.get("status") == "estimable"
            and semantic.get("paired_certified_traces") == 50
            and type(semantic.get("candidate_nontrivial")) is int
            and type(semantic.get("reference_nontrivial")) is int
            and semantic["candidate_nontrivial"] > semantic["reference_nontrivial"]
        ),
        "cap_k8_coverage_wins_minus_losses_nonnegative": (
            type(coverage.get("wins")) is int
            and type(coverage.get("losses")) is int
            and coverage["wins"] - coverage["losses"]
            >= PROMOTION_RULE[
                "cap_k8_coverage_wins_minus_losses_minimum"
            ]
        ),
        "k32_not_substituted": True,
    }


def evaluate_promotion(records, properties_sha256):
    """Revalidate all 300 records, then apply only the frozen K=8 rule."""
    if properties_sha256 != EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256:
        raise ProtocolError("screen properties canonical SHA-256 changed")
    try:
        screen_analyzer.validate_runner_contract(check_reviewed_pins=False)
    except screen_analyzer.AnalysisError as err:
        raise ProtocolError(str(err)) from err
    tasks = screen_analyzer.load_tasks()
    matrix, errors = screen_analyzer.validate_records(
        records,
        tasks,
        SCREEN_PLANNER_REVISION,
        SCREEN_PROTOCOL_REVISION,
        SCREEN_CACHE_BINARY_SHA256,
        SCREEN_CACHE_PREPROCESS_SHA256,
    )
    if errors:
        shown = "; ".join(errors[:12])
        raise ProtocolError(
            "complete 300-cell screen validation failed ({} errors): {}".format(
                len(errors), shown
            )
        )
    if len(records) != 300 or len(matrix) != 300:
        raise ProtocolError("promotion requires the complete 300-cell screen")
    primary = screen_analyzer._comparison(matrix, tasks, 8)
    coverage = primary.get("coverage", {})
    raw = primary.get("raw_pool_isolation", {})
    semantic = primary.get("semantic_nontrivial_selection", {})
    checks = promotion_checks(
        primary, record_count=len(records), matrix_count=len(matrix)
    )
    promoted = all(checks.values())
    certificate = {
        "protocol": PROMOTION_RULE["protocol"],
        "rule": copy.deepcopy(PROMOTION_RULE),
        "screen_protocol": SCREEN_PROTOCOL,
        "screen_protocol_revision": SCREEN_PROTOCOL_REVISION,
        "screen_planner_revision": SCREEN_PLANNER_REVISION,
        "screen_properties_canonical_sha256": properties_sha256,
        "checks": checks,
        "k8": {
            "coverage_wins": coverage.get("wins"),
            "coverage_losses": coverage.get("losses"),
            "coverage_net": coverage.get("wins") - coverage.get("losses"),
            "cap_semantic_nontrivial": semantic.get("candidate_nontrivial"),
            "exact_semantic_nontrivial": semantic.get("reference_nontrivial"),
            "matching_raw_pool_pairs": raw.get(
                "matching_complete_cross_protocol_fingerprints"
            ),
        },
        "k32_consulted_for_promotion": False,
        "promoted": promoted,
    }
    return json.loads(canonical_json(certificate))


def load_and_evaluate_promotion(path):
    # This pin gate must remain before any path inspection or properties load.
    _require_screen_properties_pin()
    try:
        records = screen_analyzer.safe_loader.load_properties(str(path))
    except screen_analyzer.safe_loader.AnalysisError as err:
        raise ProtocolError(str(err)) from err
    digest = _screen_properties_digest(records)
    certificate = evaluate_promotion(records, digest)
    if not certificate["promoted"]:
        failed = [name for name, passed in certificate["checks"].items() if not passed]
        raise ProtocolError(
            "cap-grid K8 did not pass the frozen promotion rule: {}".format(
                ", ".join(failed)
            )
        )
    return certificate


def validate_prospective_contract():
    require_revision(PLANNER_REVISION, "planner revision")
    require_revision(SCREEN_PROTOCOL_REVISION, "screen protocol revision")
    require_sha256(CACHE_BINARY_SHA256, "planner binary SHA-256")
    require_sha256(CACHE_PREPROCESS_SHA256, "preprocess SHA-256")
    if SCREEN_PLANNER_REVISION != PLANNER_REVISION:
        raise ProtocolError("screen/full planner revisions differ")
    if SCREEN_CACHE_BINARY_SHA256 != CACHE_BINARY_SHA256:
        raise ProtocolError("screen/full planner binaries differ")
    if SCREEN_CACHE_PREPROCESS_SHA256 != CACHE_PREPROCESS_SHA256:
        raise ProtocolError("screen/full preprocess binaries differ")
    if screen_runner.PROTOCOL != SCREEN_PROTOCOL:
        raise ProtocolError("screen protocol identity changed")
    if screen_runner.PLANNER_REVISION != SCREEN_PLANNER_REVISION:
        raise ProtocolError("screen planner pin changed")
    if screen_runner.CACHE_BINARY_SHA256 != SCREEN_CACHE_BINARY_SHA256:
        raise ProtocolError("screen binary pin changed")
    if screen_runner.CACHE_PREPROCESS_SHA256 != SCREEN_CACHE_PREPROCESS_SHA256:
        raise ProtocolError("screen preprocess pin changed")
    try:
        screen_analyzer.validate_runner_contract(check_reviewed_pins=False)
    except screen_analyzer.AnalysisError as err:
        raise ProtocolError(str(err)) from err
    if option_matrix_digest() != OPTION_MATRIX_SHA256:
        raise ProtocolError("focused option matrix digest changed")
    if sha256_json(PROMOTION_RULE) != PROMOTION_RULE_SHA256:
        raise ProtocolError("promotion rule changed")
    promotion_source = "".join(
        inspect.getsource(function)
        for function in (
            promotion_checks,
            evaluate_promotion,
            load_and_evaluate_promotion,
        )
    )
    if hashlib.sha256(promotion_source.encode("utf-8")).hexdigest() != (
        PROMOTION_IMPLEMENTATION_SHA256
    ):
        raise ProtocolError("promotion implementation changed")
    if sha256_json(ANALYSIS_PREDECLARATION) != (
        "54ee45b88a6a1ca1507971919ad8f3d168abfcbb690857f5900618d407182c5b"
    ):
        raise ProtocolError("analysis predeclaration changed")
    validate_layout()
    array_assignment()
    return True
