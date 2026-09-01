#!/usr/bin/env python3
"""Fail-closed analysis of the frozen terminal-incidence shadow study."""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import os
import random
import re
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import pdb_fixed_pattern_parser as PatternParser
import pdb_profile_comparison_parser as ProfileParser
import pdb_terminal_incidence_shadow_protocol as P


class TerminalIncidenceAnalysisError(RuntimeError):
    pass


SCHEMA = "symbolic-search-heuristics/pdb-terminal-incidence-shadow-analysis/v1"
COMPARISON_PROTOCOL = "grand-shared-strict-task-family-macro/v1"
BOOTSTRAP_PROTOCOL = "paired-family-percentile-lower-bound/v1"
LAB_SLURM_ERROR = "output-to-slurm.err"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OUTCOME_SPECS = {
    0: ("success", 1, 0, "solved"),
    1: ("search-plan-found-and-out-of-memory", 1, 0, "solved_resource"),
    2: ("search-plan-found-and-out-of-time", 1, 0, "solved_resource"),
    3: (
        "search-plan-found-and-out-of-memory-and-time",
        1,
        0,
        "solved_resource",
    ),
    10: ("translate-unsolvable", 0, 1, "presearch"),
    11: ("search-unsolvable", 0, 1, "search_terminal"),
    12: ("search-unsolved-incomplete", 0, 0, "search_terminal"),
    20: ("translate-out-of-memory", 0, 0, "presearch"),
    21: ("translate-out-of-time", 0, 0, "presearch"),
    22: ("search-out-of-memory", 0, 0, "search_resource"),
    23: ("search-out-of-time", 0, 0, "search_resource"),
    24: ("search-out-of-memory-and-time", 0, 0, "search_resource"),
}

PREDICTORS = ("I", "kD", "mQ", "mJ", "Cartesian", "width", "ADD")
PRIMARY_PREDICTOR = "I"
CONTROLS = PREDICTORS[1:]
REQUESTED_MODES = {
    "pdb_bdd_prefix_shadow": "bdd_prefix",
    "pdb_goal_prefix_shadow": "goal_prefix",
    "pdb_goal_fill_shadow": "goal_fill",
    "pdb_cegar_shadow": "cegar",
    "pdb_goal_fill_cap8_shadow": "goal_fill",
}
LABEL_MODES = {
    label: (
        {mode, "cegar_fallback_goal_fill"}
        if mode == "cegar" else {mode}
    )
    for label, mode in REQUESTED_MODES.items()
}
GOAL_FILL_LABEL = "pdb_goal_fill_shadow"


def _canonical(value) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise TerminalIncidenceAnalysisError(
            "analysis is not finite canonical JSON"
        ) from err


def _sha(value) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _fraction_record(value):
    if value is None:
        return None
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }


def _mean(values):
    values = list(values)
    if not values:
        return None
    return sum(values, Fraction(0, 1)) / len(values)


def _compare(left, right) -> int:
    return (left > right) - (left < right)


def _compare_ratio(left_num, left_den, right_num, right_den) -> int:
    if left_den <= 0 or right_den <= 0:
        raise TerminalIncidenceAnalysisError(
            "normalized comparison has a nonpositive denominator"
        )
    return _compare(left_num * right_den, right_num * left_den)


def _task_name_digest(tasks) -> str:
    payload = "".join(
        "{}:{}\n".format(domain, problem)
        for domain, problem in sorted(tasks)
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def load_records(path: Path) -> list[dict]:
    try:
        root = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as err:
        raise TerminalIncidenceAnalysisError(
            "cannot load properties: {}".format(err)
        ) from err
    records = list(root.values()) if isinstance(root, dict) else root
    if not isinstance(records, list) or any(
        not isinstance(record, dict) for record in records
    ):
        raise TerminalIncidenceAnalysisError(
            "properties must be an object or list of objects"
        )
    return records


def _terminal_class(record):
    code = record.get("planner_exit_code")
    if type(code) is not int or code not in OUTCOME_SPECS:
        raise TerminalIncidenceAnalysisError(
            "cell has an unrecognized planner terminal outcome"
        )
    expected_error, coverage, unsolvable, outcome_class = OUTCOME_SPECS[code]
    if any((
        record.get("error") != expected_error,
        type(record.get("coverage")) is not int,
        record.get("coverage") != coverage,
        record.get("unsolvable") != unsolvable,
    )):
        raise TerminalIncidenceAnalysisError(
            "cell terminal outcome fields contradict each other"
        )
    if coverage == 1 and (
        type(record.get("solution_cost")) is not int
        or record["solution_cost"] < 0
    ):
        raise TerminalIncidenceAnalysisError(
            "solved cell has an invalid solution cost"
        )
    return outcome_class


def _recognized_outcome_invalidation(record) -> bool:
    """Recognize the parser's narrow fail-closed cost/coverage invalidation."""
    code = record.get("planner_exit_code")
    if type(code) is not int or code not in OUTCOME_SPECS:
        return False
    expected_error, _coverage, unsolvable, _outcome_class = OUTCOME_SPECS[code]
    errors = record.get("unexplained_errors")
    prefixes = (
        "WBH outcome validation failed: ",
        "run-log coverage validation failed: ",
    )
    return all((
        record.get("error") == expected_error,
        record.get("coverage") is None,
        record.get("unsolvable") == unsolvable,
        isinstance(errors, list),
        bool(errors),
        all(isinstance(message, str) for message in errors),
        any(
            isinstance(message, str) and message.startswith(prefixes)
            for message in errors
        ),
    ))


def _fixed_properties():
    return {
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "cohort_role": P.COHORT_ROLE,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "cohort_task_count": P.COHORT_TASKS,
        "cohort_domain_count": P.COHORT_DOMAINS,
        "config_count": P.CONFIG_COUNT,
        "declared_run_count": P.CELL_COUNT,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "source_protocol": P.PROTOCOL,
        "planner_revision": P.PLANNER_REVISION,
        "planner_binary_sha256": P.PLANNER_BINARY_SHA256,
        "preprocess_binary_sha256": P.PREPROCESS_BINARY_SHA256,
        "planner_preprocess_sha256": P.PREPROCESS_BINARY_SHA256,
        "required_lab_version": P.REQUIRED_LAB_VERSION,
        "planner_time_limit": P.TIME_LIMIT_SECONDS,
        "planner_memory_limit": P.MEMORY_LIMIT_MIB,
        "external_validation_requested": False,
        "slurm_partition": "fat",
        "array_throttle": 0,
        "benchmark_revision": P.BENCHMARK_REVISION,
        "planner_cache_name": P.PLANNER_CACHE_NAME,
        "translator_source_sha256": P.TRANSLATOR_SOURCE_SHA256,
        "cost_attestation_sha256": P.COST_ATTESTATION_SHA256,
        "source_audit_launch_receipt_sha256": (
            P.SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256
        ),
        "source_audit_execution_receipt_sha256": (
            P.SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256
        ),
        "source_audit_code_manifest_sha256": (
            P.SOURCE_AUDIT_CODE_MANIFEST_SHA256
        ),
        "source_audit_repository_commit_id": (
            P.SOURCE_AUDIT_REPOSITORY_COMMIT_ID
        ),
        "cohort_seed": P.COHORT_SEED,
        "cohort_family_count": P.COHORT_FAMILIES,
        "cohort_directory_family_sha256": P.DIRECTORY_FAMILY_JSON_SHA256,
        "analysis_horizon": P.HORIZON,
        "primary_labels": list(P.PRIMARY_LABELS),
        "intervention_label": P.INTERVENTION_LABEL,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
    }


def _validate_parser_contract(record, outcome_class):
    expected_protocols = {
        "wbh_profile_parser_protocol": ProfileParser.PROFILE_PARSER_PROTOCOL,
        "wbh_expansion_parser_protocol": ProfileParser.EXPANSION_PARSER_PROTOCOL,
        "pdb_profile_selector_parser_protocol": (
            ProfileParser.SELECTOR_PARSER_PROTOCOL
        ),
        "pdb_fixed_pattern_parser_protocol": PatternParser.PARSER_PROTOCOL,
    }
    for field, expected in expected_protocols.items():
        if record.get(field) != expected:
            raise TerminalIncidenceAnalysisError(
                "cell changed parser contract {}".format(field)
            )
    if record.get("pdb_profile_selector_present") is True:
        raise TerminalIncidenceAnalysisError(
            "direct-PDB cell unexpectedly emitted selector evidence"
        )

    profile_present = record.get("wbh_profile_present") is True
    expansion_present = record.get("wbh_expansion_profile_present") is True
    if outcome_class == "presearch":
        if profile_present or expansion_present:
            raise TerminalIncidenceAnalysisError(
                "pre-search outcome unexpectedly emitted search evidence"
            )
        if record.get("construction_completed") is not None:
            raise TerminalIncidenceAnalysisError(
                "pre-search outcome unexpectedly reached construction"
            )


def _measurement_surface_valid(record) -> bool:
    errors = record.get("unexplained_errors")
    if errors not in (None, [], [LAB_SLURM_ERROR]):
        return False
    profile_present = record.get("wbh_profile_present") is True
    expansion_present = record.get("wbh_expansion_profile_present") is True
    if profile_present and any((
        record.get("wbh_profile_prefix_certified") is not True,
        record.get("wbh_profile_schema_version") != 3,
    )):
        return False
    if expansion_present and any((
        record.get("wbh_expansion_profile_certified") is not True,
        record.get("wbh_schema_version") != 2,
    )):
        return False
    discarded = (
        record.get("wbh_profile_trailing_fragment_discarded"),
        record.get("wbh_expansion_trailing_fragment_discarded"),
    )
    if any(type(value) is not bool for value in discarded):
        return False
    if sum(value is True for value in discarded) > 1:
        return False
    return True


def validate_matrix(records, expected_tasks=P.COHORT_TASKS):
    expected_cells = expected_tasks * P.CONFIG_COUNT
    if len(records) != expected_cells:
        raise TerminalIncidenceAnalysisError(
            "matrix has {} records, expected {}".format(
                len(records), expected_cells
            )
        )
    driver_options = [
        "--overall-time-limit",
        "{}s".format(P.TIME_LIMIT_SECONDS),
        "--overall-memory-limit",
        "{}M".format(P.MEMORY_LIMIT_MIB),
        "--build",
        "release_no_lp",
    ]
    fixed = _fixed_properties()
    matrix = {}
    tasks = set()
    outcomes = {}
    source_attestation = None
    if expected_tasks == P.COHORT_TASKS:
        try:
            source_data = json.loads(
                P.COST_ATTESTATION_PATH.read_text(encoding="ascii")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
            raise TerminalIncidenceAnalysisError(
                "cannot load the pinned source attestation"
            ) from err
        source_attestation = {
            (item["domain"], item["problem"]): item
            for item in source_data.get("tasks", [])
            if isinstance(item, dict)
        }
        if len(source_attestation) != P.COHORT_TASKS:
            raise TerminalIncidenceAnalysisError(
                "source attestation task count changed"
            )
    for record in records:
        label = record.get("algorithm")
        domain = record.get("domain")
        problem = record.get("problem")
        if label not in P.LABELS or not all(
            isinstance(item, str) and item for item in (domain, problem)
        ):
            raise TerminalIncidenceAnalysisError(
                "record has an invalid cell identity"
            )
        task = (domain, problem)
        key = (label, task)
        if key in matrix:
            raise TerminalIncidenceAnalysisError(
                "matrix contains a duplicate cell"
            )
        for field, expected in fixed.items():
            actual = record.get(field)
            normalized_time = (
                field == "planner_time_limit"
                and type(actual) is float
                and actual.is_integer()
                and int(actual) == expected
            )
            if not normalized_time and (
                actual != expected or type(actual) is not type(expected)
            ):
                raise TerminalIncidenceAnalysisError(
                    "cell changed fixed field {}".format(field)
                )
        if record.get("id") != [label, domain, problem]:
            raise TerminalIncidenceAnalysisError(
                "cell id differs from its matrix identity"
            )
        if record.get("component_options") != ["--search", P.SEARCHES[label]]:
            raise TerminalIncidenceAnalysisError(
                "cell component options differ from its label"
            )
        if record.get("driver_options") != driver_options:
            raise TerminalIncidenceAnalysisError("cell driver options changed")
        if record.get("build_options") != list(P.BUILD_OPTIONS):
            raise TerminalIncidenceAnalysisError("cell build options changed")
        source_fields = {
            "domain_source_path": record.get("domain_source_path"),
            "problem_source_path": record.get("problem_source_path"),
            "domain_source_sha256": record.get("domain_source_sha256"),
            "problem_source_sha256": record.get("problem_source_sha256"),
        }
        if (
            not all(
                isinstance(source_fields[field], str)
                and source_fields[field]
                for field in ("domain_source_path", "problem_source_path")
            )
            or any(
                SHA256_RE.fullmatch(source_fields[field] or "") is None
                for field in (
                    "domain_source_sha256",
                    "problem_source_sha256",
                )
            )
        ):
            raise TerminalIncidenceAnalysisError(
                "cell lacks frozen benchmark-source identity"
            )
        if source_attestation is not None:
            expected_source = source_attestation.get(task)
            if expected_source is None or any(
                source_fields[field] != expected_source[field]
                for field in (
                    "domain_source_sha256",
                    "problem_source_sha256",
                )
            ):
                raise TerminalIncidenceAnalysisError(
                    "cell benchmark-source hash changed"
                )
        for field in ("local_revision", "global_revision"):
            if record.get(field) != P.PLANNER_REVISION:
                raise TerminalIncidenceAnalysisError(
                    "cell changed {}".format(field)
                )
        if label == P.INTERVENTION_LABEL:
            outcome = "deferred_until_primary_gate"
        else:
            if _recognized_outcome_invalidation(record):
                outcome = "invalid_outcome"
                expected = OUTCOME_SPECS[record["planner_exit_code"]][3]
                _validate_parser_contract(record, expected)
            else:
                outcome = _terminal_class(record)
                _validate_parser_contract(record, outcome)
        matrix[key] = record
        outcomes[key] = outcome
        tasks.add(task)

    tasks = sorted(tasks)
    if len(tasks) != expected_tasks:
        raise TerminalIncidenceAnalysisError("task count changed")
    for task in tasks:
        if any((label, task) not in matrix for label in P.LABELS):
            raise TerminalIncidenceAnalysisError("matrix is incomplete")
        for field in (
            "domain_source_path",
            "problem_source_path",
            "domain_source_sha256",
            "problem_source_sha256",
        ):
            if len({matrix[(label, task)][field] for label in P.LABELS}) != 1:
                raise TerminalIncidenceAnalysisError(
                    "task source identity differs across configurations"
                )
    if expected_tasks == P.COHORT_TASKS:
        if _task_name_digest(tasks) != P.TASK_NAME_SHA256:
            raise TerminalIncidenceAnalysisError("task-name manifest changed")
        directories = {domain for domain, _ in tasks}
        if directories != set(P.DIRECTORIES):
            raise TerminalIncidenceAnalysisError(
                "benchmark directory universe changed"
            )
        if {
            P.DIRECTORY_TO_FAMILY[domain] for domain in directories
        } != set(P.DIRECTORY_TO_FAMILY.values()):
            raise TerminalIncidenceAnalysisError("family universe changed")
    return matrix, tasks, outcomes


def _complete_measurement(record) -> bool:
    return _measurement_surface_valid(record) and all(
        record.get(field) is True for field in (
        "wbh_profile_present",
        "wbh_profile_prefix_certified",
        "wbh_profile_complete",
        "wbh_profile_certified",
        "wbh_expansion_profile_present",
        "wbh_expansion_profile_certified",
        "wbh_expansion_profile_complete",
        "raw_metrics_complete",
        "piece_metrics_certified",
        )
    )


def _prefix_measurement(record) -> bool:
    return _measurement_surface_valid(record) and all(
        record.get(field) is True for field in (
        "wbh_profile_present",
        "wbh_profile_prefix_certified",
        "wbh_expansion_profile_present",
        "wbh_expansion_profile_certified",
        )
    )


def _unique_by_g(items, label):
    if not isinstance(items, list):
        raise TerminalIncidenceAnalysisError("{} is not a list".format(label))
    result = {}
    for item in items:
        if not isinstance(item, dict) or type(item.get("g")) is not int:
            raise TerminalIncidenceAnalysisError(
                "{} contains an invalid layer".format(label)
            )
        if item["g"] in result:
            raise TerminalIncidenceAnalysisError(
                "{} repeats g={}".format(label, item["g"])
            )
        result[item["g"]] = item
    return result


def _completed_profile_by_g(record):
    items = record.get("wbh_profile_layer_profiles")
    if not isinstance(items, list):
        raise TerminalIncidenceAnalysisError("profile stream is not a list")
    return _unique_by_g(
        [item for item in items if isinstance(item, dict)
         and item.get("completed") is True],
        "completed profile stream",
    )


def _record_frontier(record, retained_g):
    layers = _completed_profile_by_g(record)
    expansions = _unique_by_g(
        record.get("wbh_expansion_profile"), "expansion stream"
    )
    identity = []
    for g in retained_g:
        layer = layers.get(g)
        expansion = expansions.get(g)
        if layer is None or expansion is None:
            return None
        counts = layer.get("cofactor_counts")
        counts_sha = layer.get("cofactor_counts_sha256")
        bdd_nodes = layer.get("bdd_nodes")
        if any((
            layer.get("completed") is not True,
            type(bdd_nodes) is not int,
            bdd_nodes < 0,
            not isinstance(counts, list),
            any(type(value) is not int or value < 1 for value in counts),
            counts_sha != _sha(counts),
            expansion.get("active_h_values") != [0],
            expansion.get("active_value_count") != 1,
            expansion.get("buckets") != 1,
            expansion.get("pieces") != layer.get("piece_count"),
            expansion.get("effort") != bdd_nodes,
        )):
            raise TerminalIncidenceAnalysisError(
                "retained blind layer g={} is invalid".format(g)
            )
        identity.append({
            "g": g,
            "bdd_nodes": bdd_nodes,
            "cofactor_counts_sha256": counts_sha,
            "cofactor_counts": counts,
            "blind_effort": expansion["effort"],
        })
    return identity


def _frontier_for_task(matrix, task):
    records = [matrix[(label, task)] for label in P.PRIMARY_LABELS]
    if any(_recognized_outcome_invalidation(record) for record in records):
        return "invalid_primary_terminal_outcome", None
    if any(record.get("construction_completed") is False
           for record in records):
        return "primary_construction_failure", None
    if any(record.get("construction_completed") is None
           for record in records):
        return "primary_construction_absent", None
    if not all(_prefix_measurement(record) for record in records):
        return "invalid_or_missing_primary_prefix", None
    if any(record.get("wbh_profile_schema_version") != 3 for record in records):
        raise TerminalIncidenceAnalysisError(
            "complete primary profile is not schema v3"
        )
    solved = [record.get("coverage") == 1 for record in records]
    costs = [record.get("solution_cost") for record in records]
    solved_costs = {
        cost for cost, is_solved in zip(costs, solved) if is_solved
    }
    if len(solved_costs) > 1:
        return "inconsistent_primary_solution_cost", None
    completed_sequences = []
    for record, is_solved, cost in zip(records, solved, costs):
        sequence = sorted(_completed_profile_by_g(record))
        if is_solved:
            sequence = [g for g in sequence if g < cost]
        completed_sequences.append(tuple(sequence))

    through_horizon = all(
        len(sequence) >= P.HORIZON for sequence in completed_sequences
    )
    if through_horizon:
        horizon_sequences = [
            sequence[:P.HORIZON] for sequence in completed_sequences
        ]
        if any(sequence != horizon_sequences[0]
               for sequence in horizon_sequences[1:]):
            raise TerminalIncidenceAnalysisError(
                "primary cells have different retained g sequences"
            )
        retained_g = horizon_sequences[0]
        earlier = False
        retained_solution_cost = None
    else:
        all_solve_same = (
            all(solved)
            and len(set(costs)) == 1
            and type(costs[0]) is int
            and costs[0] >= 0
            and all(_complete_measurement(record) for record in records)
            and all(isinstance(record.get("wbh_profile_done"), dict)
                    for record in records)
            and all(record.get("wbh_solved_summary_certified") is True
                    for record in records)
        )
        if not all_solve_same:
            return "insufficient_completed_layers", None
        if any(sequence != completed_sequences[0]
               for sequence in completed_sequences[1:]):
            raise TerminalIncidenceAnalysisError(
                "early-solved primary cells have different pre-goal layers"
            )
        if len(completed_sequences[0]) >= P.HORIZON:
            raise TerminalIncidenceAnalysisError(
                "internal horizon classification is inconsistent"
            )
        retained_g = completed_sequences[0]
        earlier = True
        retained_solution_cost = costs[0]
    identities = []
    for record in records:
        identity = _record_frontier(record, retained_g)
        if identity is None:
            return "missing_retained_layer", None
        identities.append(identity)
    order_hashes = {
        record.get("wbh_profile_variable_order_sha256") for record in records
    }
    if (
        len(order_hashes) != 1
        or not isinstance(next(iter(order_hashes)), str)
        or len(next(iter(order_hashes))) != 64
    ):
        raise TerminalIncidenceAnalysisError(
            "primary cells have different variable orders"
        )
    if any(identity != identities[0] for identity in identities[1:]):
        raise TerminalIncidenceAnalysisError(
            "primary cells have different fixed-frontier identities"
        )
    return "eligible", {
        "task": task,
        "retained_g": retained_g,
        "early_solution": earlier,
        "solution_cost": retained_solution_cost,
        "variable_order_sha256": next(iter(order_hashes)),
        "layers": identities[0],
        "union_effort": sum(item["bdd_nodes"] for item in identities[0]),
        "identity_sha256": _sha({
            "order": next(iter(order_hashes)),
            "layers": identities[0],
        }),
    }


def _expected_modes(label):
    try:
        return LABEL_MODES[label]
    except KeyError as err:
        raise TerminalIncidenceAnalysisError(
            "configuration lacks a frozen direct-PDB mode"
        ) from err


def _semantic_identity(record, label, heuristic):
    if not all(record.get(field) is True for field in (
        "construction_completed",
        "pdb_fixed_pattern_present",
        "pdb_fixed_pattern_certified",
    )):
        return None
    pattern = record.get("pdb_fixed_pattern")
    final = record.get("pdb_fixed_pattern_final")
    mode = record.get("pdb_fixed_pattern_mode")
    requested_mode = REQUESTED_MODES.get(label)
    pattern_sha = _sha(pattern) if isinstance(pattern, list) else None
    fallback = mode == "cegar_fallback_goal_fill"
    if (
        not isinstance(pattern, list)
        or not isinstance(final, dict)
        or mode not in _expected_modes(label)
        or requested_mode is None
        or record.get("pdb_fixed_pattern_requested_mode") != requested_mode
        or record.get("pdb_fixed_pattern_observed_mode") != mode
        or record.get("pdb_fixed_pattern_fallback") is not fallback
        or record.get("pdb_fixed_pattern_validation_error") is not None
        or record.get("pdb_fixed_pattern_size") != len(pattern)
        or record.get("pdb_fixed_pattern_sha256") != pattern_sha
        or final.get("mode") != mode
        or final.get("state_budget") != 100000
        or final.get("pattern") != pattern
        or final.get("pattern_sha256") != pattern_sha
    ):
        raise TerminalIncidenceAnalysisError(
            "completed PDB has an invalid direct identity"
        )
    expected_cap = 8 if label == P.INTERVENTION_LABEL else None
    if final.get("value_cap") != expected_cap:
        raise TerminalIncidenceAnalysisError(
            "direct PDB identity has the wrong value cap"
        )
    add_nodes = heuristic.get("add_nodes")
    terminals = heuristic.get("num_terminals")
    values = heuristic.get("num_values")
    width = heuristic.get("cofactor_width")
    counts = heuristic.get("cofactor_counts")
    if any(type(value) is not int for value in (
        add_nodes, terminals, values, width
    )) or any((
        add_nodes < 0,
        terminals < 1,
        values < 1,
        width < 1,
        not isinstance(counts, list),
        any(type(value) is not int or value < 1 for value in counts),
        max(counts, default=0) != width,
        counts[-1] != terminals,
        final.get("pattern_size") != len(pattern),
        final.get("num_values") != values,
        final.get("cofactor_width") != width,
        final.get("width_upper_bound") != add_nodes + terminals,
        record.get("add_nodes") != add_nodes,
        record.get("num_terminals") != terminals,
        record.get("num_values") != values,
        record.get("width_upper_bound") != add_nodes + terminals,
    )):
        raise TerminalIncidenceAnalysisError(
            "direct, schema-v2, and profile PDB identities disagree"
        )
    core = {
        "pattern": pattern,
        "value_cap": expected_cap,
        "heuristic_cofactor_counts": counts,
        "add_nodes": add_nodes,
        "num_terminals": terminals,
        "num_values": values,
    }
    return {
        "id": _sha(core),
        "core": core,
        "mode": mode,
        "pattern": pattern,
        "value_cap": expected_cap,
    }


def _assert_frontier_match(record, frontier):
    required = (
        _complete_measurement(record)
        if frontier["early_solution"] else _prefix_measurement(record)
    )
    if not required:
        return False
    if record.get("wbh_profile_schema_version") != 3:
        raise TerminalIncidenceAnalysisError(
            "complete comparison profile is not schema v3"
        )
    if record.get("wbh_profile_variable_order_sha256") != (
        frontier["variable_order_sha256"]
    ):
        raise TerminalIncidenceAnalysisError(
            "comparison cell changed the fixed variable order"
        )
    identity = _record_frontier(record, frontier["retained_g"])
    if identity is None:
        return False
    if identity != frontier["layers"]:
        raise TerminalIncidenceAnalysisError(
            "comparison cell changed the fixed frontier"
        )
    return True


def _observation(record, task, label, frontier):
    if not _assert_frontier_match(record, frontier):
        return "incomplete_measurement", None
    heuristic = record.get("wbh_profile_heuristic_profile")
    if not isinstance(heuristic, dict):
        if record.get("construction_completed") is True:
            raise TerminalIncidenceAnalysisError(
                "completed PDB lacks its heuristic profile"
            )
        return "construction_incomplete", None
    semantic = _semantic_identity(record, label, heuristic)
    if semantic is None:
        return "construction_incomplete", None
    state_bits = record.get("wbh_profile_state_bits")
    heuristic_counts = heuristic["cofactor_counts"]
    if (
        type(state_bits) is not int
        or state_bits < 1
        or len(heuristic_counts) != state_bits + 1
    ):
        raise TerminalIncidenceAnalysisError(
            "heuristic cofactor profile has the wrong dimension"
        )
    layers = _unique_by_g(
        record.get("wbh_profile_layer_profiles"), "profile stream"
    )
    totals = {key: 0 for key in PREDICTORS}
    active_terminal_sum = 0
    masked_add_sum = 0
    masked_seconds = 0.0
    partition_audit_seconds = 0.0
    layer_rows = []
    for frontier_layer in frontier["layers"]:
        g = frontier_layer["g"]
        layer = layers[g]
        state_counts = layer.get("cofactor_counts")
        joint = layer.get("joint_cofactor_counts")
        masked = layer.get("masked_cofactor_counts")
        active_values = layer.get("active_values")
        values = (
            layer.get("active_value_count"),
            layer.get("masked_add_nodes"),
            layer.get("masked_cofactor_sum"),
            layer.get("terminal_incidence"),
            layer.get("partition_audit_effort"),
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise TerminalIncidenceAnalysisError(
                "layer g={} has noninteger masked statistics".format(g)
            )
        k, masked_nodes, masked_sum, incidence, effort = values
        layer_masked_seconds = layer.get("masked_seconds")
        layer_partition_seconds = layer.get("partition_audit_seconds")
        if any(
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value < 0
            for value in (layer_masked_seconds, layer_partition_seconds)
        ):
            raise TerminalIncidenceAnalysisError(
                "layer g={} has invalid certificate timings".format(g)
            )
        if any((
            state_counts != frontier_layer["cofactor_counts"],
            not isinstance(joint, list),
            not isinstance(masked, list),
            len(joint) != state_bits + 1,
            len(masked) != state_bits + 1,
            any(type(value) is not int or value < 1 for value in joint),
            any(type(value) is not int or value < 1 for value in masked),
            not isinstance(active_values, list),
            active_values != sorted(set(active_values)),
            any(type(value) is not int or value < 0 for value in active_values),
            k != len(active_values),
            not 1 <= k <= heuristic["num_terminals"],
            masked_sum != sum(masked[:-1]),
            masked[-1] != k + int(layer.get("bottom_reachable") is True),
            any(m > j for m, j in zip(masked, joint)),
        )):
            raise TerminalIncidenceAnalysisError(
                "layer g={} has an invalid masked profile".format(g)
            )
        for index, (state, h_count, joint_count) in enumerate(zip(
            state_counts, heuristic_counts, joint
        )):
            if not max(state, h_count) <= joint_count <= state * h_count:
                raise TerminalIncidenceAnalysisError(
                    "layer g={} violates joint bounds at cut {}".format(
                        g, index
                    )
                )
        k_d = k * masked_nodes
        masked_q = k * masked_sum
        masked_j = k * sum(joint[:-1])
        cartesian = k * sum(
            state * h_count
            for state, h_count in zip(state_counts[:-1], heuristic_counts[:-1])
        )
        width = (
            k * heuristic["cofactor_width"] * sum(state_counts[:-1])
        )
        add = k * (
            2 * (heuristic["add_nodes"] + 1) * layer["bdd_nodes"]
            + heuristic["add_nodes"]
        )
        if not (
            effort <= incidence <= k_d <= masked_q <= masked_j
            <= cartesian <= width
        ):
            raise TerminalIncidenceAnalysisError(
                "layer g={} violates the certificate chain".format(g)
            )
        if incidence > add:
            raise TerminalIncidenceAnalysisError(
                "layer g={} terminal incidence exceeds the ADD apply "
                "certificate".format(g)
            )
        if effort > add:
            raise TerminalIncidenceAnalysisError(
                "layer g={} exceeds the ADD apply certificate".format(g)
            )
        row = {
            "g": g,
            "E": effort,
            "I": incidence,
            "kD": k_d,
            "mQ": masked_q,
            "mJ": masked_j,
            "Cartesian": cartesian,
            "width": width,
            "ADD": add,
            "active_terminals": k,
            "active_values": active_values,
            "masked_add_nodes": masked_nodes,
            "bottom_reachable": layer.get("bottom_reachable"),
            "masked_cofactor_counts": masked,
            "joint_cofactor_counts": joint,
        }
        layer_rows.append(row)
        for predictor in PREDICTORS:
            totals[predictor] += row[predictor]
        active_terminal_sum += k
        masked_add_sum += masked_nodes
        masked_seconds += layer_masked_seconds
        partition_audit_seconds += layer_partition_seconds

    totals["E"] = sum(row["E"] for row in layer_rows)
    if any(totals["E"] > totals[key] for key in PREDICTORS):
        raise TerminalIncidenceAnalysisError(
            "run target exceeds a preregistered certificate"
        )
    if frontier["early_solution"]:
        done = record.get("wbh_profile_done")
        if not isinstance(done, dict) or any((
            done.get("solution_cost") != frontier["solution_cost"],
            done.get("layer_union_effort") != frontier["union_effort"],
            done.get("masked_add_effort") != masked_add_sum,
            done.get("terminal_incidence_effort") != totals["I"],
            done.get("partition_audit_effort") != totals["E"],
        )):
            raise TerminalIncidenceAnalysisError(
                "early-solved done event disagrees with retained totals"
            )
    domain, problem = task
    return "eligible", {
        "domain": domain,
        "family": P.DIRECTORY_TO_FAMILY.get(domain, domain),
        "problem": problem,
        "task": task,
        "config": label,
        "configs": [label],
        "semantic_id": semantic["id"],
        "semantic_identity": semantic["core"],
        "generator_mode": semantic["mode"],
        "pattern": semantic["pattern"],
        "value_cap": semantic["value_cap"],
        "E": totals["E"],
        **{key: totals[key] for key in PREDICTORS},
        "U": frontier["union_effort"],
        "active_terminal_sum": active_terminal_sum,
        "masked_add_node_sum": masked_add_sum,
        "timing_measurements": [{
            "config": label,
            "masked_seconds": masked_seconds,
            "partition_audit_seconds": partition_audit_seconds,
        }],
        "layers": layer_rows,
    }


def primary_observations(matrix, tasks):
    frontier_statuses = Counter()
    cell_statuses = Counter()
    construction_by_label = {
        label: Counter() for label in P.PRIMARY_LABELS
    }
    cegar_fallbacks = 0
    frontiers = {}
    grouped = defaultdict(dict)
    by_cell = {}
    for task in tasks:
        for label in P.PRIMARY_LABELS:
            record = matrix[(label, task)]
            completed = record.get("construction_completed")
            status = (
                "completed" if completed is True
                else "failed" if completed is False
                else "absent"
            )
            construction_by_label[label][status] += 1
        if matrix[("pdb_cegar_shadow", task)].get(
            "pdb_fixed_pattern_fallback"
        ) is True:
            cegar_fallbacks += 1
        status, frontier = _frontier_for_task(matrix, task)
        frontier_statuses[status] += 1
        if frontier is None:
            continue
        frontiers[task] = frontier
        for label in P.PRIMARY_LABELS:
            status, observation = _observation(
                matrix[(label, task)], task, label, frontier
            )
            cell_statuses[status] += 1
            if observation is None:
                continue
            by_cell[(label, task)] = observation
            semantic_id = observation["semantic_id"]
            previous = grouped[task].get(semantic_id)
            if previous is None:
                grouped[task][semantic_id] = observation
                continue
            invariant = (
                "semantic_identity", "E", *PREDICTORS, "U",
                "active_terminal_sum", "masked_add_node_sum", "layers",
            )
            if any(previous[field] != observation[field] for field in invariant):
                raise TerminalIncidenceAnalysisError(
                    "duplicate PDB semantics have different measurements"
                )
            previous["configs"].append(label)
            previous["timing_measurements"].extend(
                observation["timing_measurements"]
            )
            by_cell[(label, task)] = previous
    observations = [
        item for task in tasks for item in grouped.get(task, {}).values()
    ]
    return {
        "observations": observations,
        "grouped": grouped,
        "by_cell": by_cell,
        "frontiers": frontiers,
        "frontier_statuses": dict(frontier_statuses),
        "cell_statuses": dict(cell_statuses),
        "construction_by_label": {
            label: dict(counts)
            for label, counts in construction_by_label.items()
        },
        "cegar_fallback_tasks": cegar_fallbacks,
    }


def _aggregate_task_first(task_counts, universe, level):
    by_group = defaultdict(list)
    task_values = {}
    for task, counts in task_counts.items():
        comparable = counts["concordant"] + counts["discordant"]
        if not comparable:
            continue
        value = Fraction(counts["concordant"], comparable)
        task_values[task] = value
        directory = task[0]
        group = (
            P.DIRECTORY_TO_FAMILY.get(directory, directory)
            if level == "family" else directory
        )
        by_group[group].append(value)
    group_values = {
        group: _mean(values) for group, values in sorted(by_group.items())
    }
    if not set(group_values).issubset(universe):
        raise TerminalIncidenceAnalysisError(
            "comparison contains an unregistered aggregation group"
        )
    macro = _mean(group_values.values())
    lodo = {
        omitted: _mean(
            value for group, value in group_values.items() if group != omitted
        )
        for omitted in group_values
    }
    return {
        "task_values": {
            "{}:{}".format(*task): _fraction_record(value)
            for task, value in sorted(task_values.items())
        },
        "group_values": {
            group: _fraction_record(value)
            for group, value in group_values.items()
        },
        "eligible_groups": len(group_values),
        "macro": _fraction_record(macro),
        "leave_one_group_out": {
            group: _fraction_record(value) for group, value in lodo.items()
        },
        "_group_values": group_values,
        "_lodo": lodo,
    }


def grand_shared_comparison(grouped):
    exclusions = Counter()
    predictor_ties = Counter()
    counts = {key: defaultdict(Counter) for key in PREDICTORS}
    pair_ids = []
    inverse_u_ties = 0
    for task in sorted(grouped):
        observations = sorted(
            grouped[task].values(), key=lambda item: item["semantic_id"]
        )
        for left, right in itertools.combinations(observations, 2):
            exclusions["semantic_pairs"] += 1
            if left["U"] != right["U"]:
                raise TerminalIncidenceAnalysisError(
                    "fixed-task observations have different blind denominators"
                )
            target_order = _compare(left["E"], right["E"])
            if left["U"] == 0:
                if target_order != 0:
                    raise TerminalIncidenceAnalysisError(
                        "zero blind denominator accompanies a strict target"
                    )
                normalized_order = 0
            else:
                normalized_order = _compare_ratio(
                    left["E"], left["U"], right["E"], right["U"]
                )
                inverse_u_order = _compare_ratio(
                    1, left["U"], 1, right["U"]
                )
                if inverse_u_order != 0:
                    raise TerminalIncidenceAnalysisError(
                        "inverse-U null is not tied within a fixed task"
                    )
                inverse_u_ties += 1
            if normalized_order != target_order:
                raise TerminalIncidenceAnalysisError(
                    "absolute and E/U target orientations disagree"
                )
            if target_order == 0:
                exclusions["target_tied"] += 1
                continue
            exclusions["target_strict"] += 1
            orders = {
                key: _compare(left[key], right[key]) for key in PREDICTORS
            }
            tied = [key for key, order in orders.items() if order == 0]
            if tied:
                exclusions["any_predictor_tied"] += 1
                for key in tied:
                    predictor_ties[key] += 1
                continue
            exclusions["grand_shared_strict"] += 1
            pair_ids.append({
                "task": list(task),
                "left": left["semantic_id"],
                "right": right["semantic_id"],
            })
            for key, order in orders.items():
                outcome = (
                    "concordant" if order == target_order else "discordant"
                )
                counts[key][task][outcome] += 1

    family_universe = tuple(sorted(set(P.DIRECTORY_TO_FAMILY.values())))
    directory_universe = tuple(P.DIRECTORIES)
    summaries = {}
    for key in PREDICTORS:
        family = _aggregate_task_first(
            counts[key], family_universe, "family"
        )
        directory = _aggregate_task_first(
            counts[key], directory_universe, "directory"
        )
        total = sum(
            task_counts["concordant"] + task_counts["discordant"]
            for task_counts in counts[key].values()
        )
        concordant = sum(
            task_counts["concordant"] for task_counts in counts[key].values()
        )
        summaries[key] = {
            "concordant": concordant,
            "discordant": total - concordant,
            "comparable": total,
            "tasks_with_pairs": len(counts[key]),
            "micro_concordance": _fraction_record(
                Fraction(concordant, total) if total else None
            ),
            "equal_family": {
                field: value for field, value in family.items()
                if not field.startswith("_")
            },
            "equal_directory": {
                field: value for field, value in directory.items()
                if not field.startswith("_")
            },
            "_family_values": family["_group_values"],
            "_family_lodo": family["_lodo"],
        }
    return {
        "protocol": COMPARISON_PROTOCOL,
        "support": {
            **dict(exclusions),
            "predictor_ties_on_target_strict": dict(predictor_ties),
            "tasks_with_shared_pairs": len({
                task for task, task_counts
                in counts[PRIMARY_PREDICTOR].items()
                if sum(task_counts.values())
            }),
            "families_with_shared_pairs": len({
                P.DIRECTORY_TO_FAMILY.get(task[0], task[0])
                for task, task_counts
                in counts[PRIMARY_PREDICTOR].items()
                if sum(task_counts.values())
            }),
            "directories_with_shared_pairs": len({
                task[0] for task, task_counts
                in counts[PRIMARY_PREDICTOR].items()
                if sum(task_counts.values())
            }),
            "shared_pair_sha256": _sha(pair_ids),
        },
        "target_orientations": {
            "absolute": "E",
            "normalized": "E/U",
            "orders_identical": True,
            "inverse_U_tied_pairs": inverse_u_ties,
            "inverse_U_null": "tied_within_task",
        },
        "predictors": summaries,
    }


def _bootstrap_differences(comparison):
    family_values = {
        key: comparison["predictors"][key]["_family_values"]
        for key in PREDICTORS
    }
    families = sorted(family_values[PRIMARY_PREDICTOR])
    if any(set(family_values[key]) != set(families) for key in PREDICTORS):
        raise TerminalIncidenceAnalysisError(
            "grand-shared comparison produced different family supports"
        )
    if not families:
        return {
            control: {
                "families": 0,
                "observed_difference": None,
                "lower_95": None,
                "upper_95": None,
            }
            for control in CONTROLS
        }
    rng = random.Random(P.BOOTSTRAP_SEED)
    samples = {control: [] for control in CONTROLS}
    for _ in range(P.BOOTSTRAP_REPLICATES):
        selected = [
            families[rng.randrange(len(families))]
            for _ in range(len(families))
        ]
        for control in CONTROLS:
            samples[control].append(_mean(
                family_values[PRIMARY_PREDICTOR][family]
                - family_values[control][family]
                for family in selected
            ))
    lower_index = math.ceil(0.025 * P.BOOTSTRAP_REPLICATES) - 1
    upper_index = math.ceil(0.975 * P.BOOTSTRAP_REPLICATES) - 1
    result = {}
    for control in CONTROLS:
        ordered = sorted(samples[control])
        result[control] = {
            "families": len(families),
            "observed_difference": _fraction_record(_mean(
                family_values[PRIMARY_PREDICTOR][family]
                - family_values[control][family]
                for family in families
            )),
            "lower_95": _fraction_record(ordered[lower_index]),
            "upper_95": _fraction_record(ordered[upper_index]),
        }
    return result


def _internal_fraction(record, label):
    if not isinstance(record, dict):
        raise TerminalIncidenceAnalysisError(
            "{} is not an exact fraction".format(label)
        )
    numerator = record.get("numerator")
    denominator = record.get("denominator")
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise TerminalIncidenceAnalysisError(
            "{} is not an exact fraction".format(label)
        )
    return Fraction(numerator, denominator)


def primary_gates(comparison, eligible_tasks, eligible_families):
    bootstrap = _bootstrap_differences(comparison)
    i_summary = comparison["predictors"][PRIMARY_PREDICTOR]
    i_macro_record = i_summary["equal_family"]["macro"]
    i_macro = (
        _internal_fraction(i_macro_record, "I family macro")
        if i_macro_record is not None else None
    )
    support = comparison["support"]
    support_pass = all((
        eligible_tasks >= P.MIN_ELIGIBLE_TASKS,
        eligible_families >= P.MIN_ELIGIBLE_FAMILIES,
        support.get("tasks_with_shared_pairs", 0)
        >= P.MIN_COMPARISON_TASKS,
        support.get("grand_shared_strict", 0) >= P.MIN_SHARED_STRICT_PAIRS,
        support.get("families_with_shared_pairs", 0)
        >= P.MIN_COMPARISON_FAMILIES,
    ))
    minimum_macro = Fraction(
        P.MIN_PRIMARY_CONCORDANCE_NUMERATOR,
        P.MIN_PRIMARY_CONCORDANCE_DENOMINATOR,
    )
    minimum_advantage = Fraction(
        P.MIN_ADVANTAGE_NUMERATOR,
        P.MIN_ADVANTAGE_DENOMINATOR,
    )
    control_rows = {}
    for control in CONTROLS:
        control_macro_record = comparison["predictors"][control][
            "equal_family"
        ]["macro"]
        control_macro = (
            _internal_fraction(
                control_macro_record, "{} family macro".format(control)
            ) if control_macro_record is not None else None
        )
        advantage = (
            i_macro - control_macro
            if i_macro is not None and control_macro is not None else None
        )
        lower_record = bootstrap[control]["lower_95"]
        lower = (
            _internal_fraction(lower_record, "{} bootstrap lower".format(control))
            if lower_record is not None else None
        )
        i_lodo = i_summary["_family_lodo"]
        control_lodo = comparison["predictors"][control]["_family_lodo"]
        lodo_differences = {
            family: (
                None if i_lodo[family] is None or control_lodo[family] is None
                else i_lodo[family] - control_lodo[family]
            )
            for family in sorted(i_lodo)
        }
        lodo_pass = all(
            value is not None and value > 0
            for value in lodo_differences.values()
        )
        row_pass = all((
            advantage is not None and advantage >= minimum_advantage,
            lower is not None and lower > 0,
            lodo_pass,
        ))
        control_rows[control] = {
            "advantage": _fraction_record(advantage),
            "minimum_advantage": _fraction_record(minimum_advantage),
            "bootstrap": bootstrap[control],
            "leave_one_family_out_differences": {
                family: _fraction_record(value)
                for family, value in lodo_differences.items()
            },
            "all_leave_one_family_out_positive": lodo_pass,
            "pass": row_pass,
        }
    macro_pass = i_macro is not None and i_macro >= minimum_macro
    orientation_pass = (
        comparison["target_orientations"].get("orders_identical") is True
        and comparison["target_orientations"].get("inverse_U_null")
        == "tied_within_task"
    )
    overall = (
        support_pass
        and macro_pass
        and orientation_pass
        and all(row["pass"] for row in control_rows.values())
    )
    return {
        "pass": overall,
        "support": {
            "eligible_tasks": eligible_tasks,
            "minimum_eligible_tasks": P.MIN_ELIGIBLE_TASKS,
            "eligible_families": eligible_families,
            "minimum_eligible_families": P.MIN_ELIGIBLE_FAMILIES,
            "shared_strict_pairs": support.get("grand_shared_strict", 0),
            "minimum_shared_strict_pairs": P.MIN_SHARED_STRICT_PAIRS,
            "comparison_tasks": support.get("tasks_with_shared_pairs", 0),
            "minimum_comparison_tasks": P.MIN_COMPARISON_TASKS,
            "comparison_families": support.get("families_with_shared_pairs", 0),
            "minimum_comparison_families": P.MIN_COMPARISON_FAMILIES,
            "pass": support_pass,
        },
        "primary_macro": {
            "value": i_macro_record,
            "minimum": _fraction_record(minimum_macro),
            "pass": macro_pass,
        },
        "controls": control_rows,
        "orientation": {
            "absolute_and_normalized_agree": comparison[
                "target_orientations"
            ].get("orders_identical") is True,
            "inverse_U_tied": comparison["target_orientations"].get(
                "inverse_U_null"
            ) == "tied_within_task",
            "pass": orientation_pass,
        },
        "bootstrap_protocol": BOOTSTRAP_PROTOCOL,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
    }


def _validate_intervention_cells(matrix, tasks):
    outcomes = {}
    for task in tasks:
        record = matrix[(P.INTERVENTION_LABEL, task)]
        if _recognized_outcome_invalidation(record):
            outcome = "invalid_outcome"
            expected = OUTCOME_SPECS[record["planner_exit_code"]][3]
            _validate_parser_contract(record, expected)
        else:
            outcome = _terminal_class(record)
            _validate_parser_contract(record, outcome)
        outcomes[task] = outcome
    return outcomes


def cap8_intervention(matrix, tasks, primary):
    intervention_outcomes = _validate_intervention_cells(matrix, tasks)
    statuses = Counter()
    rows = []
    for task in tasks:
        if intervention_outcomes[task] == "invalid_outcome":
            statuses["invalid_outcome"] += 1
            continue
        frontier = primary["frontiers"].get(task)
        uncapped = primary["by_cell"].get((GOAL_FILL_LABEL, task))
        if frontier is None or uncapped is None:
            statuses["primary_ineligible"] += 1
            continue
        status, capped = _observation(
            matrix[(P.INTERVENTION_LABEL, task)],
            task,
            P.INTERVENTION_LABEL,
            frontier,
        )
        statuses[status] += 1
        if capped is None:
            continue
        if (
            uncapped["pattern"] != capped["pattern"]
            or uncapped["value_cap"] is not None
            or capped["value_cap"] != 8
        ):
            raise TerminalIncidenceAnalysisError(
                "cap-8 intervention changed the goal-fill pattern"
            )
        raw_identity = uncapped["semantic_identity"]
        capped_identity = capped["semantic_identity"]
        if any((
            capped_identity["add_nodes"] > raw_identity["add_nodes"],
            capped_identity["num_terminals"]
            > raw_identity["num_terminals"],
            capped_identity["num_values"] > raw_identity["num_values"],
            len(capped_identity["heuristic_cofactor_counts"])
            != len(raw_identity["heuristic_cofactor_counts"]),
            any(
                cap_count > raw_count
                for cap_count, raw_count in zip(
                    capped_identity["heuristic_cofactor_counts"],
                    raw_identity["heuristic_cofactor_counts"],
                )
            ),
        )):
            raise TerminalIncidenceAnalysisError(
                "cap-8 heuristic violates terminal-map consequences"
            )
        if len(uncapped["layers"]) != len(capped["layers"]):
            raise TerminalIncidenceAnalysisError(
                "cap-8 intervention changed the retained layer count"
            )
        layer_rows = []
        for raw, cap in zip(uncapped["layers"], capped["layers"]):
            if raw["g"] != cap["g"]:
                raise TerminalIncidenceAnalysisError(
                    "cap-8 intervention changed the retained layers"
                )
            if any((
                cap["bottom_reachable"] != raw["bottom_reachable"],
                cap["masked_add_nodes"] > raw["masked_add_nodes"],
                cap["active_terminals"] > raw["active_terminals"],
                cap["I"] > raw["I"],
                any(
                    cap_count > raw_count
                    for cap_count, raw_count in zip(
                        cap["masked_cofactor_counts"],
                        raw["masked_cofactor_counts"],
                    )
                ),
                any(
                    cap_count > raw_count
                    for cap_count, raw_count in zip(
                        cap["joint_cofactor_counts"],
                        raw["joint_cofactor_counts"],
                    )
                ),
                any(value > 9 for value in cap["active_values"]),
            )):
                raise TerminalIncidenceAnalysisError(
                    "cap-8 intervention violates terminal-map consequences "
                    "at g={}".format(raw["g"])
                )
            layer_rows.append({
                "g": raw["g"],
                "active_terminals_delta": (
                    cap["active_terminals"] - raw["active_terminals"]
                ),
                "terminal_incidence_delta": cap["I"] - raw["I"],
                "partition_effort_delta": cap["E"] - raw["E"],
            })
        row = {
            "domain": task[0],
            "family": P.DIRECTORY_TO_FAMILY.get(task[0], task[0]),
            "problem": task[1],
            "active_terminal_delta": (
                capped["active_terminal_sum"] - uncapped["active_terminal_sum"]
            ),
            "terminal_incidence_delta": capped["I"] - uncapped["I"],
            "partition_effort_delta": capped["E"] - uncapped["E"],
            "layers": layer_rows,
        }
        if any(row[key] > 0 for key in (
            "active_terminal_delta",
            "terminal_incidence_delta",
        )):
            raise TerminalIncidenceAnalysisError(
                "cap-8 intervention violates run-level terminal-map "
                "monotonicity"
            )
        rows.append(row)
    return {
        "status": "analyzed",
        "outcome_classes": dict(Counter(intervention_outcomes.values())),
        "cell_statuses": dict(statuses),
        "eligible_pairs": len(rows),
        "observed_terminal_map_consequences_hold": True,
        "strict_decreases": {
            key: sum(row[key] < 0 for row in rows)
            for key in (
                "active_terminal_delta",
                "terminal_incidence_delta",
                "partition_effort_delta",
            )
        },
        "sum_deltas": {
            key: sum(row[key] for row in rows)
            for key in (
                "active_terminal_delta",
                "terminal_incidence_delta",
                "partition_effort_delta",
            )
        },
        "rows": rows,
    }


def _nearest_rank(values, numerator, denominator):
    ordered = sorted(values)
    if not ordered:
        return None
    index = math.ceil(numerator * len(ordered) / denominator) - 1
    return ordered[index]


def secondary_diagnostics(observations):
    by_task = defaultdict(list)
    for observation in observations:
        by_task[observation["task"]].append(observation)

    tightness = {}
    for predictor in PREDICTORS:
        task_values = {}
        for task, rows in by_task.items():
            ratios = []
            for row in rows:
                target = row["E"]
                certificate = row[predictor]
                if certificate == 0:
                    if target != 0:
                        raise TerminalIncidenceAnalysisError(
                            "zero certificate has positive partition effort"
                        )
                    ratios.append(Fraction(1, 1))
                else:
                    ratios.append(Fraction(target, certificate))
            task_values[task] = _mean(ratios)
        family_values = {}
        for family in sorted(set(P.DIRECTORY_TO_FAMILY.values())):
            values = [
                value for task, value in task_values.items()
                if P.DIRECTORY_TO_FAMILY.get(task[0], task[0]) == family
            ]
            if values:
                family_values[family] = _mean(values)
        tightness[predictor] = {
            "definition": "task-first equal-family mean of E/predictor",
            "tasks": len(task_values),
            "families": len(family_values),
            "equal_family_macro": _fraction_record(
                _mean(family_values.values())
            ),
            "family_quantiles_nearest_rank": {
                "q25": _fraction_record(
                    _nearest_rank(family_values.values(), 1, 4)
                ),
                "q50": _fraction_record(
                    _nearest_rank(family_values.values(), 1, 2)
                ),
                "q75": _fraction_record(
                    _nearest_rank(family_values.values(), 3, 4)
                ),
            },
            "family_values": {
                family: _fraction_record(value)
                for family, value in family_values.items()
            },
        }

    timing_by_task = defaultdict(lambda: [0.0, 0.0, 0])
    for observation in observations:
        task = observation["task"]
        for timing in observation["timing_measurements"]:
            timing_by_task[task][0] += timing["masked_seconds"]
            timing_by_task[task][1] += timing["partition_audit_seconds"]
            timing_by_task[task][2] += 1
    task_ratios = {
        task: masked / partition
        for task, (masked, partition, _cells) in timing_by_task.items()
        if partition > 0
    }
    family_ratios = {}
    for family in sorted(set(P.DIRECTORY_TO_FAMILY.values())):
        values = [
            value for task, value in task_ratios.items()
            if P.DIRECTORY_TO_FAMILY.get(task[0], task[0]) == family
        ]
        if values:
            family_ratios[family] = sum(values) / len(values)
    total_masked = sum(value[0] for value in timing_by_task.values())
    total_partition = sum(value[1] for value in timing_by_task.values())
    return {
        "tightness": tightness,
        "computation_time": {
            "masked_scope": (
                "masked ADD construction, masked cofactor profile, and "
                "terminal-incidence traversal"
            ),
            "partition_scope": "exact per-active-value bucket construction",
            "cells": sum(value[2] for value in timing_by_task.values()),
            "tasks": len(timing_by_task),
            "tasks_with_positive_partition_time": len(task_ratios),
            "families_with_positive_partition_time": len(family_ratios),
            "pooled_masked_seconds": total_masked,
            "pooled_partition_audit_seconds": total_partition,
            "pooled_masked_over_partition_ratio": (
                total_masked / total_partition
                if total_partition > 0 else None
            ),
            "equal_family_mean_of_task_ratios": (
                sum(family_ratios.values()) / len(family_ratios)
                if family_ratios else None
            ),
            "family_mean_task_ratios": family_ratios,
        },
    }


def analyze_records(records, expected_tasks=P.COHORT_TASKS):
    matrix, tasks, outcomes = validate_matrix(records, expected_tasks)
    primary = primary_observations(matrix, tasks)
    comparison = grand_shared_comparison(primary["grouped"])
    eligible_tasks = len(primary["frontiers"])
    eligible_families = len({
        P.DIRECTORY_TO_FAMILY.get(task[0], task[0])
        for task in primary["frontiers"]
    })
    gates = primary_gates(comparison, eligible_tasks, eligible_families)
    intervention = (
        cap8_intervention(matrix, tasks, primary)
        if gates["pass"] else {
            "status": "not_analyzed_primary_gate_failed",
            "eligible_pairs": None,
            "rows": None,
        }
    )
    public_comparison = {
        **comparison,
        "predictors": {
            key: {
                field: value for field, value in summary.items()
                if not field.startswith("_")
            }
            for key, summary in comparison["predictors"].items()
        },
    }
    return {
        "schema": SCHEMA,
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "matrix": {
            "tasks": len(tasks),
            "configs": P.CONFIG_COUNT,
            "cells": len(records),
            "outcome_classes": dict(Counter(outcomes.values())),
        },
        "primary": {
            "frontier_statuses": primary["frontier_statuses"],
            "cell_statuses": primary["cell_statuses"],
            "construction_by_label": primary["construction_by_label"],
            "cegar_fallback_tasks": primary["cegar_fallback_tasks"],
            "eligible_tasks": eligible_tasks,
            "eligible_families": eligible_families,
            "semantic_observations": len(primary["observations"]),
            "duplicate_config_observations": (
                sum(len(item["configs"]) for item in primary["observations"])
                - len(primary["observations"])
            ),
            "rows": primary["observations"],
        },
        "comparison": public_comparison,
        "gates": gates,
        "secondary_diagnostics": secondary_diagnostics(
            primary["observations"]
        ),
        "intervention": intervention,
        "guided_study_authorized": gates["pass"],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("properties", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    P.validate_protocol_without_sources()
    import audit_pdb_terminal_incidence_shadow as Audit

    try:
        fetch_sha, fetch_receipt = Audit.load_fetch_receipt(verify_live=True)
    except Audit.ExecutionAuditError as err:
        raise TerminalIncidenceAnalysisError(
            "fetched properties provenance is invalid"
        ) from err
    if (
        args.properties.resolve() != Audit.EVAL_PROPERTIES.resolve()
        or hashlib.sha256(args.properties.read_bytes()).hexdigest()
        != fetch_receipt["properties_sha256"]
    ):
        raise TerminalIncidenceAnalysisError(
            "analysis input is not the sealed fetched properties file"
        )
    records = load_records(args.properties)
    result = analyze_records(records)
    result["input"] = {
        "path": str(args.properties.resolve()),
        "sha256": hashlib.sha256(args.properties.read_bytes()).hexdigest(),
        "fetch_receipt_sha256": fetch_sha,
    }
    payload = _canonical(result) + b"\n"
    if args.output:
        try:
            with args.output.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError as err:
            raise TerminalIncidenceAnalysisError(
                "refusing to overwrite analysis output"
            ) from err
    else:
        print(payload.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TerminalIncidenceAnalysisError, P.ProtocolError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
