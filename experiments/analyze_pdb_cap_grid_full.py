#!/usr/bin/env python3
"""Fail-closed analysis of the focused 1,377-by-5 cap-grid census.

The primary population is the frozen 1,327-task complement of the development
screen.  The primary estimand is cap-K8 minus exact-K8 equal-domain macro
coverage.  Task-micro discordance and the all-1,377 census are descriptive,
prespecified summaries; no confidence intervals or p-values are computed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from fractions import Fraction
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_arrhenius_selector_full as full_analysis
import analyze_pdb_cap_grid_pilot as cap_analysis
import exp_pdb_cap_grid_full as runner
import pdb_cap_grid_full_protocol as P
import pdb_cap_grid_full_secondary_contract as secondary
import pdb_cap_selector_parser as cap_parser


class AnalysisError(RuntimeError):
    pass


ANALYSIS_SCHEMA = "symbolic-search-heuristics/pdb-cap-grid-focused-full/v1"
EXPECTED_PROTOCOL_REVISION = None
EXPECTED_PROPERTIES_CANONICAL_SHA256 = None
EXPECTED_PROSPECTIVE_JOB_SHA256 = None
PAR2_UNSOLVED_SECONDS = cap_analysis.PAR2_UNSOLVED_SECONDS


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
        raise AnalysisError("value is not canonical finite JSON: {}".format(err))


def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def _same(actual, expected):
    return type(actual) is type(expected) and actual == expected


def _number(value):
    if type(value) not in (int, float):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _append(errors, prefix, message):
    errors.append("{}: {}".format(prefix, message))


def _cell(label, task):
    return "{} {}:{}".format(label, *task)


def validate_runner_contract(check_analysis_pins=True):
    P.validate_prospective_contract()
    secondary.validate_contract()
    exact = (
        (runner.P.PROTOCOL, P.PROTOCOL, "protocol"),
        (runner.P.PLANNER_REVISION, P.PLANNER_REVISION, "planner revision"),
        (tuple(runner.P.CONFIGS), P.CONFIGS, "configuration matrix"),
        (runner.P.OPTION_MATRIX_SHA256, P.OPTION_MATRIX_SHA256, "matrix digest"),
        (runner.P.EXPECTED_TASKS, 1377, "task count"),
        (runner.P.EXPECTED_PRIMARY_TASKS, 1327, "primary task count"),
        (runner.P.EXPECTED_CELLS, 6885, "cell count"),
        (
            runner.P.ANALYSIS_PREDECLARATION,
            P.ANALYSIS_PREDECLARATION,
            "analysis predeclaration",
        ),
        (runner.P.PROMOTION_RULE, P.PROMOTION_RULE, "promotion rule"),
        (
            runner.P.PLANNER_SOFT_STDOUT_LIMIT_KIB,
            7168,
            "soft stdout limit",
        ),
        (
            runner.P.PLANNER_HARD_STDOUT_LIMIT_KIB,
            16384,
            "hard stdout limit",
        ),
        (PAR2_UNSOLVED_SECONDS, 600.0, "PAR2 unsolved penalty"),
    )
    errors = [
        label + " changed"
        for actual, expected, label in exact
        if not _same(actual, expected)
    ]
    if check_analysis_pins:
        try:
            P.require_revision(
                P.PROTOCOL_IMPLEMENTATION_REVISION,
                "protocol implementation revision",
            )
            P.require_revision(EXPECTED_PROTOCOL_REVISION, "launch revision")
            runner.C._git_output(
                "merge-base",
                "--is-ancestor",
                P.PROTOCOL_IMPLEMENTATION_REVISION,
                EXPECTED_PROTOCOL_REVISION,
            )
        except Exception:
            errors.append(
                "implementation/launch protocol revision lineage is invalid"
            )
        if EXPECTED_PROSPECTIVE_JOB_SHA256 != P.EXPECTED_PROSPECTIVE_JOB_SHA256:
            errors.append("runner/analyzer job pins differ")
    if errors:
        raise AnalysisError("runner/analyzer contract mismatch: " + "; ".join(errors))


def require_reviewed_pins(properties_sha256=None):
    pins = (
        EXPECTED_PROTOCOL_REVISION,
        EXPECTED_PROPERTIES_CANONICAL_SHA256,
        EXPECTED_PROSPECTIVE_JOB_SHA256,
        P.PROTOCOL_IMPLEMENTATION_REVISION,
        P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256,
    )
    if any(value is None for value in pins):
        if not all(value is None for value in pins):
            raise AnalysisError("focused full analysis pins are only partially set")
        raise AnalysisError(
            "focused full analysis pins are unset; refusing to read outcomes"
        )
    try:
        P.require_revision(EXPECTED_PROTOCOL_REVISION, "protocol revision")
        P.require_sha256(
            EXPECTED_PROPERTIES_CANONICAL_SHA256,
            "properties canonical SHA-256",
        )
        P.require_sha256(
            EXPECTED_PROSPECTIVE_JOB_SHA256,
            "prospective job SHA-256",
        )
        P.require_sha256(
            P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256,
            "screen properties canonical SHA-256",
        )
    except P.ProtocolError as err:
        raise AnalysisError(str(err)) from err
    if properties_sha256 is not None and properties_sha256 != (
        EXPECTED_PROPERTIES_CANONICAL_SHA256
    ):
        raise AnalysisError("focused properties canonical SHA-256 changed")
    validate_runner_contract(check_analysis_pins=True)


def load_tasks():
    try:
        descriptions, _ = P.load_full_tasks()
        tasks = [tuple(item.split(":", 1)) for item in descriptions]
        primary = P.primary_tasks(descriptions)
    except (P.ProtocolError, RuntimeError) as err:
        raise AnalysisError(str(err)) from err
    if len(tasks) != 1377 or len(primary) != 1327:
        raise AnalysisError("focused task populations changed")
    return tasks, primary


def _expected_static(benchmark_worktree):
    source = {
        "source_manifest_sha256": P.EXPECTED_SOURCE_MANIFEST_SHA256,
        "task_sources_sha256": P.EXPECTED_TASK_SOURCES_SHA256,
    }
    promotion = {
        "screen_properties_canonical_sha256": (
            P.EXPECTED_SCREEN_PROPERTIES_CANONICAL_SHA256
        )
    }
    return runner.make_protocol_metadata(
        benchmark_worktree,
        source,
        promotion,
        protocol_revision=EXPECTED_PROTOCOL_REVISION,
        prospective_job_sha256=EXPECTED_PROSPECTIVE_JOB_SHA256,
    )


def _expected_component_options(search):
    return full_analysis.expected_component_options(search)


def _validate_static_record(
    record, label, task, run_id, expected_static, errors
):
    prefix = _cell(label, task)
    exact = {
        "id": [label, task[0], task[1]],
        "algorithm": label,
        "domain": task[0],
        "problem": task[1],
        "component_options": _expected_component_options(P.SEARCHES[label]),
        "driver_options": [
            "--overall-time-limit",
            "30m",
            "--overall-memory-limit",
            "3584M",
            "--build",
            "release_no_lp",
            "--overall-time-limit",
            "300s",
            "--overall-memory-limit",
            "8G",
        ],
        "build_options": ["release_no_lp"],
        "local_revision": P.PLANNER_REVISION,
        "global_revision": P.PLANNER_REVISION,
        "repo": str(runner.C.REPO),
        "experiment_name": "exp_pdb_cap_grid_full",
        "run_dir": full_analysis._run_relative_path(run_id),
    }
    for field, expected in exact.items():
        if field not in record or not _same(record.get(field), expected):
            _append(
                errors,
                prefix,
                "{}={!r}, expected {!r}".format(
                    field, record.get(field), expected
                ),
            )
    for field, expected in expected_static.items():
        if field not in record or not _same(record.get(field), expected):
            _append(
                errors,
                prefix,
                "{}={!r}, expected {!r}".format(
                    field, record.get(field), expected
                ),
            )
    for field, expected in (
        ("planner_time_limit", 300.0),
        ("planner_memory_limit", 8192.0),
    ):
        if _number(record.get(field)) != expected:
            _append(errors, prefix, "{} changed".format(field))


def _trace_complete(record):
    return (
        record.get("pdb_selector_trace_complete") is True
        and record.get("pdb_selector_trace_certified") is True
        and record.get("pdb_selector_validation_error") is None
        and isinstance(record.get("pdb_selector_selected"), dict)
        and isinstance(record.get("pdb_selector_candidates"), list)
    )


def _semantic_nontrivial(record):
    selected = record["pdb_selector_selected"]
    return selected["finite_sum"] > 0 or selected["dead_count"] > 0


def validate_records(records, tasks):
    task_set = set(tasks)
    matrix = {}
    errors = []
    if len(records) != P.EXPECTED_CELLS:
        errors.append(
            "properties contain {} records; expected exactly 6885".format(
                len(records)
            )
        )
    worktrees = {
        record.get("benchmark_worktree")
        for record in records
        if isinstance(record.get("benchmark_worktree"), str)
    }
    if len(worktrees) != 1 or not Path(next(iter(worktrees), "")).is_absolute():
        errors.append("records require one consistent absolute benchmark_worktree")
        benchmark_worktree = "/invalid"
    else:
        benchmark_worktree = next(iter(worktrees))
    expected_static = _expected_static(benchmark_worktree)

    for record in records:
        try:
            label, task = full_analysis.heldout.analyzer_utils.identity(record)
        except full_analysis.heldout.analyzer_utils.AnalysisError as err:
            errors.append(str(err))
            continue
        if label not in P.LABELS:
            errors.append("unexpected algorithm {}".format(label))
            continue
        if task not in task_set:
            errors.append("record outside focused census {}:{}".format(*task))
            continue
        key = (label, task)
        if key in matrix:
            errors.append("duplicate cell {}".format(_cell(label, task)))
        else:
            matrix[key] = record
    missing = [
        (label, task)
        for label in P.LABELS
        for task in tasks
        if (label, task) not in matrix
    ]
    if missing:
        errors.append(
            "missing {} expected cells; first: {}".format(
                len(missing), ", ".join(_cell(*item) for item in missing[:8])
            )
        )
    if len(matrix) != P.EXPECTED_CELLS:
        errors.append(
            "matrix contains {} cells; expected 6885".format(len(matrix))
        )

    costs = defaultdict(list)
    proofs = defaultdict(list)
    for config_index, label in enumerate(P.LABELS):
        for task_index, task in enumerate(tasks):
            record = matrix.get((label, task))
            if record is None:
                continue
            run_id = config_index * len(tasks) + task_index + 1
            prefix = _cell(label, task)
            _validate_static_record(
                record, label, task, run_id, expected_static, errors
            )
            full_analysis._validate_completion(record, run_id, prefix, errors)
            full_analysis.heldout.pilot_analyzer._validate_outcome(
                record, prefix, errors
            )
            full_analysis.heldout._validate_metric_certification(
                record, prefix, errors
            )
            if label == P.CAP:
                cap_analysis._validate_heuristic_stats(
                    record, label, prefix, errors
                )
                cap_analysis._validate_cap_trace(record, label, prefix, errors)
            else:
                full_analysis.heldout._validate_heuristic(
                    record, label, P.SEARCHES[label], prefix, errors
                )
            if record.get("coverage") == 1 and type(
                record.get("solution_cost")
            ) is int:
                costs[task].append((label, record["solution_cost"]))
            if record.get("coverage") == 0 and record.get("unsolvable") == 1:
                proofs[task].append(label)

    for task in tasks:
        distinct = {cost for _, cost in costs.get(task, [])}
        if len(distinct) > 1:
            errors.append("solved-cost disagreement on {}:{}".format(*task))
        if distinct and proofs.get(task):
            errors.append(
                "solved/proved-unsolvable disagreement on {}:{}".format(*task)
            )
        exact = matrix.get((P.EXACT, task))
        cap = matrix.get((P.CAP, task))
        if exact is None or cap is None:
            continue
        if _trace_complete(exact) and _trace_complete(cap):
            exact_identity = cap_analysis._raw_pool_identity(exact, False)
            cap_identity = cap_analysis._raw_pool_identity(cap, True)
            if exact_identity != cap_identity:
                errors.append(
                    "same-K raw selector pool disagreement on {}:{}".format(*task)
                )

    if errors:
        shown = errors[:60]
        suffix = "" if len(errors) <= 60 else "\n... {} more".format(len(errors) - 60)
        raise AnalysisError(
            "focused full validation failed ({} errors):\n{}{}".format(
                len(errors), "\n".join("- " + item for item in shown), suffix
            )
        )
    return matrix


def _summary(values):
    values = list(values)
    if not values:
        return {
            "observed": 0,
            "minimum": None,
            "median": None,
            "maximum": None,
            "mean": None,
            "total": None,
        }
    return {
        "observed": len(values),
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
        "mean": statistics.fmean(values),
        "total": math.fsum(values),
    }


def _count_summary(values):
    values = list(values)
    if any(type(value) is not int or value < 0 for value in values):
        raise AnalysisError("count summary requires exact nonnegative integers")
    if not values:
        return {
            "observed": 0,
            "minimum": None,
            "median": None,
            "maximum": None,
            "mean": None,
            "total": None,
        }
    return {
        "observed": len(values),
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
        "mean": statistics.fmean(values),
        "total": sum(values),
    }


def summarize_config(matrix, tasks, label):
    records = [matrix[(label, task)] for task in tasks]
    solved = [record for record in records if record.get("coverage") == 1]
    constructed = [
        record
        for record in records
        if record.get("construction_completed") is True
        and _number(record.get("construction_time")) is not None
    ]
    solved_cpu = _summary(record["planner_time"] for record in solved)
    solved_cpu_total = 0.0 if solved_cpu["total"] is None else solved_cpu["total"]
    micro_par2 = (
        solved_cpu_total
        + PAR2_UNSOLVED_SECONDS * (len(records) - len(solved))
    ) / len(records)
    return {
        "label": label,
        "role": (
            "primary-contrast" if label in (P.EXACT, P.CAP) else "descriptive-context"
        ),
        "cells": len(records),
        "solved": len(solved),
        "coverage_rate": len(solved) / len(records),
        "micro_par2_seconds": micro_par2,
        "solved_planner_cpu_seconds": solved_cpu,
        "completed_construction_seconds": _summary(
            record["construction_time"] for record in constructed
        ),
    }


def _certified_complete_trace(record):
    return (
        record.get("pdb_selector_trace_complete") is True
        and record.get("pdb_selector_trace_certified") is True
        and record.get("pdb_selector_validation_error") is None
        and isinstance(record.get("pdb_selector_selected"), dict)
    )


def _cap_histogram(selected):
    counts = defaultdict(int)
    for item in selected:
        cap = item.get("value_cap", -1)
        key = "exact" if cap == -1 else str(cap)
        counts[key] += 1
    return {
        key: counts[key]
        for key in sorted(
            counts,
            key=lambda value: (
                value == "exact",
                int(value) if value != "exact" else 0,
            ),
        )
    }


def selector_summary(matrix, tasks, label):
    records = [matrix[(label, task)] for task in tasks]
    selected_pairs = [
        (record, record["pdb_selector_selected"])
        for record in records
        if _certified_complete_trace(record)
    ]
    selected = [item for _, item in selected_pairs]
    return {
        "eligible_cells": len(records),
        "complete_certified_traces": len(selected),
        "semantic_nontrivial": sum(
            item["finite_sum"] > 0 or item["dead_count"] > 0
            for item in selected
        ),
        "effective_cap_histogram": _cap_histogram(selected),
        "selected_first_provenance_source": {
            source: sum(item["sources"][0] == source for item in selected)
            for source in cap_analysis.common.PDB_SELECTOR_SOURCES
        },
        "pattern_size": _count_summary(len(item["pattern"]) for item in selected),
        "W": _count_summary(item["cofactor_width"] for item in selected),
        "A": _count_summary(
            item.get("add_nodes", record.get("add_nodes"))
            for record, item in selected_pairs
            if type(item.get("add_nodes", record.get("add_nodes"))) is int
        ),
        "T": _count_summary(
            item.get("num_terminals", record.get("num_terminals"))
            for record, item in selected_pairs
            if type(item.get("num_terminals", record.get("num_terminals")))
            is int
        ),
        "U": _count_summary(item["width_upper_bound"] for item in selected),
        "V": _count_summary(
            item.get("transformed_num_values", record.get("num_values"))
            for record, item in selected_pairs
            if type(
                item.get("transformed_num_values", record.get("num_values"))
            )
            is int
        ),
    }


def _ratio(candidate_total, reference_total):
    return None if reference_total == 0 else candidate_total / reference_total


def _paired_total_ratio(matrix, tasks, field, predicate):
    pairs = [
        (matrix[(P.CAP, task)], matrix[(P.EXACT, task)])
        for task in tasks
        if predicate(matrix[(P.CAP, task)])
        and predicate(matrix[(P.EXACT, task)])
    ]
    candidate_total = sum(candidate[field] for candidate, _ in pairs)
    reference_total = sum(reference[field] for _, reference in pairs)
    return {
        "eligible_pair_count": len(pairs),
        "candidate_total": candidate_total,
        "reference_total": reference_total,
        "candidate_over_reference": _ratio(candidate_total, reference_total),
    }


def _jointly_solved_cpu_ratio(matrix, tasks):
    jointly_solved = [
        (matrix[(P.CAP, task)], matrix[(P.EXACT, task)])
        for task in tasks
        if matrix[(P.CAP, task)].get("coverage") == 1
        and matrix[(P.EXACT, task)].get("coverage") == 1
    ]
    positive_pairs = [
        (candidate, reference)
        for candidate, reference in jointly_solved
        if (
            _number(candidate.get("planner_time")) is not None
            and _number(reference.get("planner_time")) is not None
            and candidate["planner_time"] > 0
            and reference["planner_time"] > 0
        )
    ]
    ratio = None
    if positive_pairs:
        ratio = math.exp(
            statistics.fmean(
                math.log(candidate["planner_time"])
                - math.log(reference["planner_time"])
                for candidate, reference in positive_pairs
            )
        )
    return {
        "jointly_solved_pair_count": len(jointly_solved),
        "eligible_pair_count": len(positive_pairs),
        "excluded_nonpositive_pair_count": (
            len(jointly_solved) - len(positive_pairs)
        ),
        "candidate_over_reference": ratio,
    }


def secondary_descriptive_scope(matrix, tasks):
    complete_image = cap_analysis.legacy.certified_image_cell
    constructed = lambda record: (
        record.get("construction_completed") is True
        and _number(record.get("construction_time")) is not None
    )
    candidate_records = [matrix[(P.CAP, task)] for task in tasks]
    reference_records = [matrix[(P.EXACT, task)] for task in tasks]
    candidate_solved = [
        record for record in candidate_records if record.get("coverage") == 1
    ]
    reference_solved = [
        record for record in reference_records if record.get("coverage") == 1
    ]
    candidate_runtime_total = math.fsum(
        record["planner_time"] for record in candidate_solved
    )
    reference_runtime_total = math.fsum(
        record["planner_time"] for record in reference_solved
    )
    candidate_par2 = (
        candidate_runtime_total
        + PAR2_UNSOLVED_SECONDS * (len(tasks) - len(candidate_solved))
    ) / len(tasks)
    reference_par2 = (
        reference_runtime_total
        + PAR2_UNSOLVED_SECONDS * (len(tasks) - len(reference_solved))
    ) / len(tasks)
    return {
        "tasks": len(tasks),
        "selector_summary": {
            P.EXACT: selector_summary(matrix, tasks, P.EXACT),
            P.CAP: selector_summary(matrix, tasks, P.CAP),
        },
        "paired_operational": {
            "micro_par2_seconds": {
                "fixed_task_denominator": len(tasks),
                "candidate_solved": len(candidate_solved),
                "reference_solved": len(reference_solved),
                "candidate_solved_planner_cpu_total_seconds": (
                    candidate_runtime_total
                ),
                "reference_solved_planner_cpu_total_seconds": (
                    reference_runtime_total
                ),
                "candidate": candidate_par2,
                "reference": reference_par2,
                "candidate_minus_reference": candidate_par2 - reference_par2,
            },
            "jointly_solved_planner_cpu": _jointly_solved_cpu_ratio(
                matrix, tasks
            ),
            "complete_certified_image_time": _paired_total_ratio(
                matrix, tasks, "image_time", complete_image
            ),
            "complete_certified_expanded_bdd_nodes": _paired_total_ratio(
                matrix, tasks, "expanded_bdd_nodes", complete_image
            ),
            "observed_completed_construction_time": _paired_total_ratio(
                matrix, tasks, "construction_time", constructed
            ),
        },
    }


def _fraction_record(value, fixed_denominator=None):
    if not isinstance(value, Fraction):
        value = Fraction(value)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "fixed_estimand_denominator": fixed_denominator,
        "value": float(value),
    }


def contrast(matrix, tasks, role):
    domains = list(dict.fromkeys(domain for domain, _ in tasks))
    per_domain = []
    cap_macro = Fraction(0, 1)
    exact_macro = Fraction(0, 1)
    pairs = []
    for domain in domains:
        domain_tasks = [task for task in tasks if task[0] == domain]
        cap_solved = sum(
            matrix[(P.CAP, task)]["coverage"] == 1 for task in domain_tasks
        )
        exact_solved = sum(
            matrix[(P.EXACT, task)]["coverage"] == 1 for task in domain_tasks
        )
        cap_rate = Fraction(cap_solved, len(domain_tasks))
        exact_rate = Fraction(exact_solved, len(domain_tasks))
        cap_macro += cap_rate
        exact_macro += exact_rate
        per_domain.append(
            {
                "domain": domain,
                "tasks": len(domain_tasks),
                "cap_solved": cap_solved,
                "exact_solved": exact_solved,
                "cap_minus_exact_rate": _fraction_record(cap_rate - exact_rate),
            }
        )
    cap_macro /= len(domains)
    exact_macro /= len(domains)
    for task in tasks:
        pairs.append((matrix[(P.CAP, task)], matrix[(P.EXACT, task)]))
    wins = sum(cap["coverage"] == 1 and exact["coverage"] == 0 for cap, exact in pairs)
    losses = sum(cap["coverage"] == 0 and exact["coverage"] == 1 for cap, exact in pairs)
    both_solved = sum(cap["coverage"] == exact["coverage"] == 1 for cap, exact in pairs)
    both_unsolved = len(pairs) - wins - losses - both_solved

    complete = [
        (cap, exact)
        for cap, exact in pairs
        if _trace_complete(cap) and _trace_complete(exact)
    ]
    raw_matching = [
        (cap, exact)
        for cap, exact in complete
        if cap_analysis._raw_pool_identity(cap, True)
        == cap_analysis._raw_pool_identity(exact, False)
    ]
    cap_nontrivial = sum(_semantic_nontrivial(cap) for cap, _ in complete)
    exact_nontrivial = sum(_semantic_nontrivial(exact) for _, exact in complete)
    semantic_wins = sum(
        _semantic_nontrivial(cap) and not _semantic_nontrivial(exact)
        for cap, exact in complete
    )
    semantic_losses = sum(
        not _semantic_nontrivial(cap) and _semantic_nontrivial(exact)
        for cap, exact in complete
    )
    mechanism_certified = (
        len(complete) == len(tasks)
        and len(raw_matching) == len(tasks)
        and semantic_wins + semantic_losses > 0
    )
    return {
        "role": role,
        "population": {
            "tasks": len(tasks),
            "domains": len(domains),
        },
        "equal_domain_macro_coverage": {
            "cap": _fraction_record(cap_macro, len(domains)),
            "exact": _fraction_record(exact_macro, len(domains)),
            "cap_minus_exact": _fraction_record(
                cap_macro - exact_macro, len(domains)
            ),
            "domain_weighting": "each-domain-equal/v1",
        },
        "task_micro_discordance": {
            "cap_wins": wins,
            "cap_losses": losses,
            "wins_minus_losses": wins - losses,
            "discordant": wins + losses,
            "both_solved": both_solved,
            "both_unsolved": both_unsolved,
            "task_pairs": len(pairs),
        },
        "mechanism": {
            "status": "certified" if mechanism_certified else "not-certified",
            "required_pairs": len(tasks),
            "paired_complete_certified_traces": len(complete),
            "same_k_raw_pool_identity_pairs": len(raw_matching),
            "cap_semantic_nontrivial": cap_nontrivial,
            "exact_semantic_nontrivial": exact_nontrivial,
            "semantic_pair_wins": semantic_wins,
            "semantic_pair_losses": semantic_losses,
            "semantic_selection_difference_observed": (
                semantic_wins + semantic_losses > 0
            ),
            "claim_policy": (
                "requires-all-pairs-complete-all-raw-pools-identical-and-at-"
                "least-one-paired-semantic-nontrivial-difference/v1"
            ),
        },
        "per_domain": per_domain,
    }


def make_analysis(records, matrix, tasks, primary, properties_sha256):
    primary_set = set(primary)
    if not primary_set.issubset(set(tasks)):
        raise AnalysisError("primary complement is outside full census")
    result = {
        "schema": ANALYSIS_SCHEMA,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "predeclaration": copy.deepcopy(P.ANALYSIS_PREDECLARATION),
        "execution": {
            "protocol": P.PROTOCOL,
            "protocol_revision": EXPECTED_PROTOCOL_REVISION,
            "planner_revision": P.PLANNER_REVISION,
            "planner_binary_sha256": P.CACHE_BINARY_SHA256,
            "planner_preprocess_sha256": P.CACHE_PREPROCESS_SHA256,
            "prospective_start_job_sha256": EXPECTED_PROSPECTIVE_JOB_SHA256,
            "properties_canonical_sha256": properties_sha256,
            "task_manifest_sha256": P.EXPECTED_TASK_MANIFEST_SHA256,
            "primary_task_manifest_sha256": P.EXPECTED_PRIMARY_TASK_MANIFEST_SHA256,
            "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
            "cell_count": len(records),
            "all_cells_validated": len(records) == P.EXPECTED_CELLS,
            "solved_cost_agreement_validated_across_all_configs": True,
            "completion_recovery_protocol": (
                runner.Full.FULL_COMPLETION_MARKER_PROTOCOL
            ),
        },
        "secondary_descriptive_contract": {
            "sha256": secondary.validate_contract(),
            "contract": copy.deepcopy(secondary.CONTRACT),
        },
        "primary": contrast(matrix, primary, "primary-development-complement"),
        "full_census_sensitivity": contrast(
            matrix, tasks, "prespecified-scope-sensitivity"
        ),
        "secondary_descriptive": {
            "primary_development_complement": secondary_descriptive_scope(
                matrix, primary
            ),
            "full_census_sensitivity": secondary_descriptive_scope(
                matrix, tasks
            ),
        },
        "descriptive_full_census_configs": [
            summarize_config(matrix, tasks, label) for label in P.LABELS
        ],
        "inference": {
            "confidence_intervals": None,
            "p_values": None,
            "fixed_population_census": True,
        },
    }
    return json.loads(canonical_json(result))


def _synthetic_pool_records(nontrivial_exact, nontrivial_cap):
    exact = {
        "pdb_selector_trace_complete": True,
        "pdb_selector_trace_certified": True,
        "pdb_selector_validation_error": None,
        "pdb_selector_selected": {
            "finite_sum": int(nontrivial_exact),
            "dead_count": 0,
        },
        "pdb_selector_candidates": [
            {
                "sources": ["empty"],
                "pattern": [],
                "abstract_states": 1,
                "initial_dead_end": False,
                "initial_h": 0,
                "finite_sum": 0,
                "finite_count": 1,
                "dead_count": 0,
                "cofactor_width": 1,
                "width_upper_bound": 1,
            }
        ],
    }
    cap = {
        "pdb_selector_trace_complete": True,
        "pdb_selector_trace_certified": True,
        "pdb_selector_validation_error": None,
        "pdb_selector_selected": {
            "finite_sum": int(nontrivial_cap),
            "dead_count": 0,
        },
        "pdb_selector_candidates": [
            {
                "sources": ["empty"],
                "pattern": [],
                "abstract_states": 1,
                "raw_num_values": 1,
                "value_cap": -1,
                "initial_dead_end": False,
                "initial_h": 0,
                "finite_sum": 0,
                "finite_count": 1,
                "dead_count": 0,
                "raw_cofactor_width": 1,
                "raw_width_upper_bound": 1,
            }
        ],
    }
    return exact, cap


def self_test():
    validate_runner_contract(check_analysis_pins=False)
    tasks = [("d1", "p1"), ("d1", "p2"), ("d1", "p3"), ("d2", "p1")]
    matrix = {}
    coverages = {
        P.EXACT: [1, 0, 0, 1],
        P.CAP: [1, 1, 0, 0],
    }
    for index, task in enumerate(tasks):
        exact, cap = _synthetic_pool_records(False, index == 1)
        exact.update({"coverage": coverages[P.EXACT][index], "planner_time": 1.0})
        cap.update({"coverage": coverages[P.CAP][index], "planner_time": 1.0})
        matrix[(P.EXACT, task)] = exact
        matrix[(P.CAP, task)] = cap
    result = contrast(matrix, tasks, "synthetic")
    # d1 is +1/3 and d2 is -1, so the equal-domain macro delta is -1/3.
    macro = result["equal_domain_macro_coverage"]["cap_minus_exact"]
    if (macro["numerator"], macro["denominator"]) != (-1, 3):
        raise AssertionError("equal-domain macro weighting changed")
    micro = result["task_micro_discordance"]
    if (micro["cap_wins"], micro["cap_losses"], micro["discordant"]) != (1, 1, 2):
        raise AssertionError("task-micro discordance changed")
    mechanism = result["mechanism"]
    if mechanism["status"] != "certified" or mechanism["semantic_pair_wins"] != 1:
        raise AssertionError("mechanism certification changed")
    if canonical_json(result) != canonical_json(
        contrast(copy.deepcopy(matrix), list(tasks), "synthetic")
    ):
        raise AssertionError("focused analysis is nondeterministic")
    print("Focused cap-grid full analyzer self-test: PASS")
    print("synthetic contrast SHA-256: {}".format(sha256_json(result)))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--properties", help="exact Lab properties JSON/file/directory")
    parser.add_argument("--emit-json", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    # This identity gate intentionally precedes task loading, path inspection,
    # and all outcome-bearing properties reads.
    require_reviewed_pins()
    if not args.properties:
        raise AnalysisError("--properties is required")
    tasks, primary = load_tasks()
    try:
        records = full_analysis.load_properties(args.properties)
    except full_analysis.AnalysisError as err:
        raise AnalysisError(str(err)) from err
    digest = full_analysis.logical_properties_sha256(records)
    require_reviewed_pins(digest)
    matrix = validate_records(records, tasks)
    result = make_analysis(records, matrix, tasks, primary, digest)
    if args.emit_json:
        print(canonical_json(result))
    else:
        print("Focused cap-grid full analysis: PASS")
        print("canonical analysis SHA-256: {}".format(sha256_json(result)))
        print(canonical_json(result))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AnalysisError, P.ProtocolError, RuntimeError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
