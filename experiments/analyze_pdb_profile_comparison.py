#!/usr/bin/env python3
"""Fail-closed descriptive analysis for the 1,327 x 18 profile matrix."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter
from fractions import Fraction
from pathlib import Path


import pdb_profile_comparison_protocol as P
import exp_pdb_profile_comparison as E


class AnalysisError(RuntimeError):
    pass


SCHEMA = "symbolic-search-heuristics/pdb-profile-comparison/v1"
PAIR_PROTOCOL = "fixed-task-coverage-and-jointly-solved-effort/v1"
PROFILE_CERTIFICATE_PROTOCOL = (
    "cut-aligned-layer-profile-times-active-values-i-0-through-n-minus-1/v1"
)
OUTCOME_SPECS = {
    0: ("success", 1, 0, "solved"),
    1: ("search-plan-found-and-out-of-memory", 1, 0, "solved_resource"),
    2: ("search-plan-found-and-out-of-time", 1, 0, "solved_resource"),
    3: ("search-plan-found-and-out-of-memory-and-time", 1, 0, "solved_resource"),
    10: ("translate-unsolvable", 0, 1, "presearch"),
    11: ("search-unsolvable", 0, 1, "search_terminal"),
    12: ("search-unsolvable-incomplete", 0, 0, "search_terminal"),
    20: ("translate-out-of-memory", 0, 0, "presearch"),
    21: ("translate-out-of-time", 0, 0, "presearch"),
    22: ("search-out-of-memory", 0, 0, "search_resource"),
    23: ("search-out-of-time", 0, 0, "search_resource"),
    24: ("search-out-of-memory-and-time", 0, 0, "search_resource"),
}


def _fraction(numerator, denominator):
    if denominator == 0:
        return None
    value = Fraction(numerator, denominator)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }


def _finite_ratio(numerator, denominator):
    if denominator == 0:
        return None
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator,
    }


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
        raise AnalysisError("analysis is not finite canonical JSON") from err


def load_records(path: Path) -> list[dict]:
    try:
        root = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise AnalysisError("cannot load properties: {}".format(err)) from err
    if isinstance(root, dict):
        records = list(root.values())
    elif isinstance(root, list):
        records = root
    else:
        raise AnalysisError("properties must be an object or list")
    if any(not isinstance(record, dict) for record in records):
        raise AnalysisError("properties contain a non-object record")
    return records


def _outcome_class(record, label):
    errors = record.get("unexplained_errors")
    if errors not in (None, []):
        raise AnalysisError("cell carries unexplained parser/execution errors")
    code = record.get("planner_exit_code")
    if type(code) is not int or code not in OUTCOME_SPECS:
        raise AnalysisError("cell has an unrecognized planner terminal outcome")
    expected_error, coverage, unsolvable, outcome_class = OUTCOME_SPECS[code]
    if (
        record.get("error") != expected_error
        or record.get("coverage") != coverage
        or type(record.get("coverage")) is not int
        or record.get("unsolvable") != unsolvable
    ):
        raise AnalysisError("cell terminal outcome fields contradict each other")

    expansion_present = record.get("wbh_expansion_profile_present") is True
    expansion_certified = record.get("wbh_expansion_profile_certified") is True
    expansion_complete = record.get("wbh_expansion_profile_complete") is True
    profile_expected = label != "blind_fw"
    profile_present = record.get("wbh_profile_present") is True
    profile_prefix = record.get("wbh_profile_prefix_certified") is True
    profile_complete = record.get("wbh_profile_complete") is True
    selector_present = record.get("pdb_profile_selector_present") is True
    selector_prefix = (
        record.get("pdb_profile_selector_prefix_certified") is True
    )

    if outcome_class == "presearch":
        if expansion_present or profile_present or selector_present:
            raise AnalysisError("pre-search outcome unexpectedly emitted search evidence")
        if record.get("construction_completed") is not None:
            raise AnalysisError("pre-search outcome unexpectedly reached construction")
        return outcome_class

    if expansion_present and not expansion_certified:
        raise AnalysisError("present schema-v2 stream is malformed")
    if profile_present and not profile_prefix:
        raise AnalysisError("present profile stream is malformed")
    if selector_present and not selector_prefix:
        raise AnalysisError("present selector prefix is malformed")

    if outcome_class == "solved":
        if (
            not expansion_present
            or not expansion_certified
            or not expansion_complete
            or record.get("wbh_solved_summary_certified") is not True
        ):
            raise AnalysisError("solved cell lacks complete schema-v2 done evidence")
        if profile_expected and (
            not profile_present
            or not profile_prefix
            or not profile_complete
            or record.get("wbh_profile_done") is None
        ):
            raise AnalysisError("solved profiled cell lacks complete done+summary evidence")
    elif outcome_class == "search_terminal":
        if not expansion_present or not expansion_certified or not expansion_complete:
            raise AnalysisError("terminal search outcome lacks a complete schema-v2 stream")
        if profile_expected and (
            not profile_present or not profile_prefix or not profile_complete
        ):
            raise AnalysisError("terminal search outcome lacks a complete profile stream")
    elif outcome_class in ("search_resource", "solved_resource"):
        # A resource kill can occur before either logger opens.  Any bytes that
        # do exist must nevertheless form a valid flushed prefix.
        pass
    else:
        raise AnalysisError("internal outcome taxonomy error")

    if label.startswith("pdb_") and record.get("construction_completed") is True:
        if (
            record.get("pdb_profile_selector_trace_complete") is not True
            or record.get("pdb_profile_selector_trace_certified") is not True
            or not profile_present
            or not profile_prefix
            or not isinstance(record.get("wbh_profile_heuristic_profile"), dict)
        ):
            raise AnalysisError(
                "completed PDB construction lacks its selector/heuristic evidence"
            )
    return outcome_class


def validate_matrix(records, expected_tasks=P.COHORT_TASKS):
    expected_cells = expected_tasks * P.CONFIG_COUNT
    if len(records) != expected_cells:
        raise AnalysisError(
            "matrix has {} records, expected {}".format(len(records), expected_cells)
        )
    matrix = {}
    tasks = set()
    stratum_by_task = {}
    fixed = {
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "cohort_role": P.COHORT_ROLE,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "cohort_task_count": P.COHORT_TASKS,
        "config_count": P.CONFIG_COUNT,
        "declared_run_count": P.CELL_COUNT,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "matched_budget_archive_sha256": P.MATCH_ARCHIVE_SHA256,
        "matched_budget_candidates": P.MATCH_CANDIDATES,
        "add_match_role": P.ADD_MATCH_ROLE,
        "planner_revision": E.PLANNER_REVISION,
        "planner_binary_sha256": E.PLANNER_BINARY_SHA256,
        "preprocess_binary_sha256": E.PREPROCESS_BINARY_SHA256,
        "planner_preprocess_sha256": E.PREPROCESS_BINARY_SHA256,
        "required_lab_version": P.REQUIRED_LAB_VERSION,
        "planner_time_limit": P.TIME_LIMIT_SECONDS,
        "planner_memory_limit": P.MEMORY_LIMIT_MIB,
    }
    expected_driver_options = [
        "--validate",
        "--overall-time-limit",
        "{}s".format(P.TIME_LIMIT_SECONDS),
        "--overall-memory-limit",
        "{}M".format(P.MEMORY_LIMIT_MIB),
        "--build",
        "release_no_lp",
    ]
    for record in records:
        label = record.get("algorithm")
        domain = record.get("domain")
        problem = record.get("problem")
        if label not in P.LABELS or not all(
            isinstance(value, str) and value for value in (domain, problem)
        ):
            raise AnalysisError("record has an invalid cell identity")
        task = (domain, problem)
        key = (label, task)
        if key in matrix:
            raise AnalysisError("matrix contains a duplicate cell")
        for field, expected in fixed.items():
            if record.get(field) != expected or type(record.get(field)) is not type(expected):
                raise AnalysisError("cell changed fixed field {}".format(field))
        if record.get("id") != [label, domain, problem]:
            raise AnalysisError("cell id differs from its matrix identity")
        if record.get("component_options") != ["--search", P.SEARCHES[label]]:
            raise AnalysisError("cell component options differ from its label")
        if record.get("driver_options") != expected_driver_options:
            raise AnalysisError("cell driver options changed")
        if record.get("build_options") != list(P.BUILD_OPTIONS):
            raise AnalysisError("cell build options changed")
        for field in ("local_revision", "global_revision"):
            if record.get(field) != E.PLANNER_REVISION:
                raise AnalysisError("cell changed {}".format(field))
        stratum = record.get("cohort_stratum")
        if stratum not in {
            "legacy_triple_finite_cap",
            "legacy_triple_exact_endpoint",
            "primary_other",
        }:
            raise AnalysisError("cell has an invalid cohort stratum")
        if task in stratum_by_task and stratum_by_task[task] != stratum:
            raise AnalysisError("cohort stratum differs across configurations")
        stratum_by_task[task] = stratum
        outcome_class = _outcome_class(record, label)
        expected_profile = label != "blind_fw"
        if record.get("wbh_profile_expected") is not expected_profile:
            raise AnalysisError("cell has the wrong profile expectation")
        heuristic = record.get("wbh_profile_heuristic_profile")
        if (
            label.startswith("pdb_")
            and record.get("construction_completed") is True
            and not isinstance(heuristic, dict)
        ):
            raise AnalysisError("selector cell lacks its heuristic profile")
        if (
            label.startswith("pdb_")
            and outcome_class == "solved"
            and record.get("pdb_profile_selector_trace_certified") is not True
        ):
            raise AnalysisError("solved selector cell lacks a certified selector trace")
        if label == "blind_fw_profiled" and heuristic is not None:
            raise AnalysisError("profiled blind cell unexpectedly has a heuristic")
        if (
            label.startswith("pdb_")
            and record.get("wbh_profile_prefix_certified") is True
            and record.get("wbh_profile_layer_profile_attempts", 0) != 0
        ):
            raise AnalysisError("selector cell unexpectedly logged exact blind layers")
        matrix[key] = record
        tasks.add(task)
    tasks = sorted(tasks)
    if len(tasks) != expected_tasks:
        raise AnalysisError("task count changed")
    for task in tasks:
        if any((label, task) not in matrix for label in P.LABELS):
            raise AnalysisError("matrix is incomplete")
    if expected_tasks == P.COHORT_TASKS:
        manifest = "".join("{}:{}\n".format(*task) for task in tasks).encode("utf-8")
        if hashlib.sha256(manifest).hexdigest() != P.COHORT_MANIFEST_SHA256:
            raise AnalysisError("task manifest changed")
        counts = Counter(stratum_by_task.values())
        expected = {
            "legacy_triple_finite_cap": P.LEGACY_FINITE_CAP_TASKS,
            "legacy_triple_exact_endpoint": P.LEGACY_EXACT_ENDPOINT_TASKS,
            "primary_other": P.PRIMARY_OTHER_TASKS,
        }
        if dict(counts) != expected:
            raise AnalysisError("legacy stratum counts changed")
    return matrix, tasks, stratum_by_task


def _target_effort(record, label):
    if record.get("coverage") != 1:
        return None
    if label == "blind_fw_profiled":
        if (
            record.get("wbh_profile_complete") is not True
            or record.get("wbh_profile_certified") is not True
        ):
            return None
        done = record.get("wbh_profile_done")
        if not isinstance(done, dict):
            return None
        effort = done.get("layer_union_effort")
    else:
        if (
            record.get("wbh_solved_summary_certified") is not True
            or record.get("wbh_expansion_profile_complete") is not True
        ):
            return None
        effort = record.get("effort")
    if type(effort) is not int or effort < 0:
        raise AnalysisError("target effort is invalid")
    return effort


def config_summary(matrix, tasks, label, certificate_summaries=None):
    records = [matrix[(label, task)] for task in tasks]
    solved = sum(record["coverage"] for record in records)
    times = [record.get("planner_time") for record in records if record["coverage"]]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in times):
        raise AnalysisError("solved planner time is invalid")
    efforts = [
        effort
        for record in records
        for effort in [_target_effort(record, label)]
        if effort is not None
    ]
    result = {
        "tasks": len(tasks),
        "solved": solved,
        "terminal_outcomes": dict(Counter(
            _outcome_class(record, label) for record in records
        )),
        "coverage": _fraction(solved, len(tasks)),
        "solved_planner_time_total": sum(times),
        "solved_effort_count": len(efforts),
        "solved_effort_incomplete": solved - len(efforts),
        "solved_effort_total": sum(efforts),
    }
    if label == "blind_fw_profiled":
        layers = [
            layer
            for record in records
            for layer in record.get("wbh_profile_layer_profiles", [])
            if layer["completed"]
        ]
        result["complete_layer_profiles"] = len(layers)
        result["maximum_layer_cofactor_width"] = (
            max((layer["cofactor_width"] for layer in layers), default=None)
        )
        result["maximum_layer_paper_cut_width"] = (
            max((layer["paper_cut_width"] for layer in layers), default=None)
        )
        result["layer_cut_product_sum"] = sum(
            layer["paper_cut_product_sum"] for layer in layers
        )
    elif label.startswith("pdb_"):
        certificates = [
            record["wbh_profile_heuristic_paper_cuts"]
            for record in records
            if record.get("wbh_profile_heuristic_paper_cuts") is not None
        ]
        result["heuristic_profile_count"] = len(certificates)
        result["maximum_selected_cofactor_width"] = max(
            (item["cofactor_width"] for item in certificates), default=None
        )
        result["maximum_selected_paper_cut_width"] = max(
            (item["paper_cut_width"] for item in certificates), default=None
        )
        result["heuristic_cut_product_sum"] = sum(
            item["cut_product_sum"] for item in certificates
        )
        if certificate_summaries is not None:
            result["theorem_certificate"] = certificate_summaries[label]
    return result


def _profile_certificate(candidate, blind, task, label):
    """Instantiate the paper's layerwise certificate for one eligible cell."""
    if candidate.get("coverage") != 1:
        return {"status": "candidate_unsolved"}
    if blind.get("coverage") != 1:
        return {"status": "reference_unsolved"}
    if not all(
        predicate is True
        for predicate in (
            candidate.get("wbh_profile_certified"),
            candidate.get("wbh_profile_complete"),
            candidate.get("wbh_expansion_profile_certified"),
            candidate.get("wbh_expansion_profile_complete"),
            candidate.get("wbh_solved_summary_certified"),
            candidate.get("pdb_profile_selector_trace_certified"),
        )
    ) or not isinstance(candidate.get("wbh_profile_done"), dict):
        return {"status": "candidate_metrics_incomplete"}
    if not all(
        predicate is True
        for predicate in (
            blind.get("wbh_profile_certified"),
            blind.get("wbh_profile_complete"),
        )
    ) or not isinstance(blind.get("wbh_profile_done"), dict):
        return {"status": "reference_metrics_incomplete"}
    cost = candidate.get("solution_cost")
    if type(cost) is not int or cost < 0 or blind.get("solution_cost") != cost:
        raise AnalysisError("certificate pair has an invalid or unequal solution cost")
    state_bits = candidate.get("wbh_profile_state_bits")
    order_digest = candidate.get("wbh_profile_variable_order_sha256")
    if (
        type(state_bits) is not int
        or state_bits < 1
        or blind.get("wbh_profile_state_bits") != state_bits
        or not isinstance(order_digest, str)
        or len(order_digest) != 64
        or blind.get("wbh_profile_variable_order_sha256") != order_digest
    ):
        raise AnalysisError("certificate pair has different state-bit/order certificates")

    heuristic = candidate.get("wbh_profile_heuristic_profile")
    paper_cuts = candidate.get("wbh_profile_heuristic_paper_cuts")
    selected = candidate.get("pdb_profile_selector_selected")
    raw_pool_common_sha256 = candidate.get(
        "pdb_profile_selector_raw_pool_common_sha256"
    )
    raw_pool_extended_sha256 = candidate.get(
        "pdb_profile_selector_raw_pool_extended_sha256"
    )
    if not all(isinstance(value, dict) for value in (heuristic, paper_cuts, selected)):
        raise AnalysisError("eligible PDB cell lacks aligned heuristic metadata")
    if (
        not isinstance(raw_pool_common_sha256, str)
        or len(raw_pool_common_sha256) != 64
    ):
        raise AnalysisError("eligible PDB cell lacks a complete raw-pool identity")
    residuals = heuristic.get("cofactor_counts")
    if (
        not isinstance(residuals, list)
        or len(residuals) != state_bits + 1
        or any(type(value) is not int or value < 1 for value in residuals)
    ):
        raise AnalysisError("heuristic cofactor vector is invalid")
    width = max(residuals)
    paper_width = max(residuals[:-1])
    add_nodes = heuristic.get("add_nodes")
    terminals = heuristic.get("num_terminals")
    if (
        type(add_nodes) is not int
        or add_nodes < 0
        or type(terminals) is not int
        or terminals < 1
        or heuristic.get("cofactor_width") != width
        or paper_cuts != {
            "paper_cut_width": paper_width,
            "cofactor_width": width,
            "cut_product_sum": sum(residuals[:-1]),
            "terminal_residuals": residuals[-1],
        }
    ):
        raise AnalysisError("heuristic profile summary changed")
    profile_identity = {
        "add_nodes": add_nodes,
        "num_values": heuristic.get("num_values"),
        "num_terminals": terminals,
        "cofactor_width": width,
        "width_upper_bound": add_nodes + terminals,
    }
    stream_identity = {
        "add_nodes": candidate.get("add_nodes"),
        "num_values": candidate.get("num_values"),
        "num_terminals": candidate.get("num_terminals"),
        "cofactor_width": width,
        "width_upper_bound": candidate.get("width_upper_bound"),
    }
    if profile_identity != stream_identity:
        raise AnalysisError("profile and schema-v2 heuristic identities differ")
    if (
        selected.get("cofactor_width") != width
        or selected.get("width_upper_bound") != add_nodes + terminals
    ):
        raise AnalysisError("profile and selector width identities differ")
    if selected.get("protocol") in {
        "fixed_pool_cap_grid_v6",
        "fixed_pool_total_add_cap_grid_v1",
        "fixed_pool_total_add_value_cap_v1",
    } and any(
        selected.get(field) != expected
        for field, expected in (
            ("add_nodes", add_nodes),
            ("transformed_num_values", heuristic.get("num_values")),
            ("num_terminals", terminals),
        )
    ):
        raise AnalysisError("cap-grid profile and selector ADD identities differ")
    if selected.get("protocol") in {
        "fixed_pool_cap_grid_v6",
        "fixed_pool_total_add_cap_grid_v1",
    } and (
        not isinstance(raw_pool_extended_sha256, str)
        or len(raw_pool_extended_sha256) != 64
    ):
        raise AnalysisError("eligible cap-grid cell lacks its extended pool identity")

    candidate_done = candidate.get("wbh_profile_done")
    done = blind.get("wbh_profile_done")
    if (
        not isinstance(candidate_done, dict)
        or candidate_done.get("solution_cost") != cost
        or not isinstance(done, dict)
        or done.get("solution_cost") != cost
    ):
        raise AnalysisError("profile done event disagrees with C-star")
    blind_layers = {}
    for layer in blind.get("wbh_profile_layer_profiles", []):
        if not isinstance(layer, dict):
            raise AnalysisError("profiled blind layer summary is invalid")
        if not layer.get("completed") or layer.get("g", cost) >= cost:
            continue
        g = layer.get("g")
        if g in blind_layers:
            raise AnalysisError("profiled blind repeats a completed active g layer")
        counts = layer.get("cofactor_counts")
        if (
            type(g) is not int
            or g < 0
            or not isinstance(counts, list)
            or len(counts) != state_bits + 1
            or any(type(value) is not int or value < 1 for value in counts)
        ):
            raise AnalysisError("profiled blind layer vector is invalid")
        blind_layers[g] = layer

    active_by_g = {}
    for active in candidate.get("wbh_expansion_profile", []):
        if not isinstance(active, dict):
            raise AnalysisError("schema-v2 per-g expansion profile is invalid")
        g = active.get("g")
        values = active.get("active_value_count")
        buckets = active.get("buckets")
        pieces = active.get("pieces")
        if (
            type(g) is not int
            or g < 0
            or g >= cost
            or g in active_by_g
            or type(values) is not int
            or values < 1
            or type(buckets) is not int
            or buckets != values
            or type(pieces) is not int
            or pieces != buckets
        ):
            raise AnalysisError(
                "schema-v2 active V_g/bucket/piece profile is invalid"
            )
        active_by_g[g] = active
    if not set(active_by_g).issubset(blind_layers):
        raise AnalysisError("PDB active g layer is absent from profiled blind layers")

    profile_bound = 0
    width_bound = 0
    add_cudd_safe_bound = 0
    combined_bound = 0
    layer_relations = Counter()
    for g in sorted(active_by_g):
        layer = blind_layers[g]
        active = active_by_g[g]
        layer_counts = layer["cofactor_counts"]
        values = active["active_value_count"]
        # The final terminal cut (i=n) validates the complete vectors but is
        # excluded from all theorem products and cofactor-count sums.
        cut_product = sum(
            left * right
            for left, right in zip(layer_counts[:-1], residuals[:-1])
        )
        width_relaxation = width * sum(layer_counts[:-1])
        bdd_nodes = layer.get("bdd_nodes")
        if type(bdd_nodes) is not int or bdd_nodes < 0:
            raise AnalysisError("profiled blind layer has invalid BDD size")
        # The logged b is CUDD's regular-node count with complement sharing.
        # Expanding to at most 2b signed ordinary nodes gives a conservative
        # bridge to the paper's ordinary Apply argument.
        add_apply = 2 * (add_nodes + 1) * bdd_nodes + add_nodes
        if cut_product > width_relaxation:
            raise AnalysisError("exact profile product exceeds its width relaxation")
        profile_bound += values * cut_product
        width_bound += values * width_relaxation
        add_cudd_safe_bound += values * add_apply
        combined_bound += values * min(cut_product, add_apply)
        relation = "profile_lt_add" if cut_product < add_apply else (
            "profile_gt_add" if cut_product > add_apply else "profile_eq_add"
        )
        layer_relations[relation] += 1

    actual_effort = _target_effort(candidate, label)
    if actual_effort is None:
        raise AnalysisError("eligible certificate cell lacks actual effort")
    if any(
        actual_effort > bound
        for bound in (
            profile_bound,
            width_bound,
            add_cudd_safe_bound,
            combined_bound,
        )
    ):
        raise AnalysisError("measured effort exceeds a theorem certificate")
    if sum(layer["bdd_nodes"] for layer in blind_layers.values()) != done.get(
        "layer_union_effort"
    ):
        raise AnalysisError("profiled blind active layers disagree with done effort")
    domain, problem = task
    return {
        "status": "eligible",
        "domain": domain,
        "problem": problem,
        "config": label,
        "solution_cost": cost,
        "state_bits": state_bits,
        "variable_order_sha256": order_digest,
        "raw_pool_sha256": raw_pool_common_sha256,
        "raw_pool_common_sha256": raw_pool_common_sha256,
        "raw_pool_extended_sha256": raw_pool_extended_sha256,
        "active_layers": len(active_by_g),
        "actual_effort": actual_effort,
        "B_profile": profile_bound,
        "B_width": width_bound,
        "B_add_apply_cudd_safe": add_cudd_safe_bound,
        "B_combined": combined_bound,
        "actual_over_B_profile": _fraction(actual_effort, profile_bound),
        "B_profile_over_B_width": _fraction(profile_bound, width_bound),
        "B_profile_over_B_add_apply_cudd_safe": _fraction(
            profile_bound, add_cudd_safe_bound
        ),
        "actual_over_B_combined": _fraction(actual_effort, combined_bound),
        "layer_profile_vs_add": {
            "profile_smaller": layer_relations["profile_lt_add"],
            "equal": layer_relations["profile_eq_add"],
            "profile_larger": layer_relations["profile_gt_add"],
        },
    }


def _certificate_summary(statuses, rows):
    totals = {
        field: sum(row[field] for row in rows)
        for field in (
            "actual_effort",
            "B_profile",
            "B_width",
            "B_add_apply_cudd_safe",
            "B_combined",
        )
    }
    return {
        "fixed_task_denominator": sum(statuses.values()),
        "status": dict(statuses),
        "eligible_cells": len(rows),
        "totals": totals,
        "actual_over_B_profile": _fraction(
            totals["actual_effort"], totals["B_profile"]
        ),
        "B_profile_over_B_width": _fraction(
            totals["B_profile"], totals["B_width"]
        ),
        "B_profile_over_B_add_apply_cudd_safe": _fraction(
            totals["B_profile"], totals["B_add_apply_cudd_safe"]
        ),
        "actual_over_B_combined": _fraction(
            totals["actual_effort"], totals["B_combined"]
        ),
        "cell_profile_vs_width": dict(Counter(
            "profile_smaller" if row["B_profile"] < row["B_width"] else "equal"
            for row in rows
        )),
        "cell_profile_vs_add_apply": dict(Counter(
            "profile_smaller"
            if row["B_profile"] < row["B_add_apply_cudd_safe"]
            else (
                "profile_larger"
                if row["B_profile"] > row["B_add_apply_cudd_safe"]
                else "equal"
            )
            for row in rows
        )),
    }


def profile_certificates(matrix, tasks):
    rows = []
    summaries = {}
    by_label_task = {}
    for label in P.LABELS[2:]:
        statuses = Counter()
        label_rows = []
        for task in tasks:
            result = _profile_certificate(
                matrix[(label, task)], matrix[("blind_fw_profiled", task)], task, label
            )
            statuses[result["status"]] += 1
            if result["status"] == "eligible":
                rows.append(result)
                label_rows.append(result)
                by_label_task[(label, task)] = result
        summaries[label] = _certificate_summary(statuses, label_rows)
    return rows, summaries, by_label_task


def paired_certificate_summary(by_label_task, tasks, candidate, reference):
    jointly_certified = [
        (by_label_task[(candidate, task)], by_label_task[(reference, task)])
        for task in tasks
        if (candidate, task) in by_label_task and (reference, task) in by_label_task
    ]
    pairs = []
    extended_pool_pairs = 0
    for left, right in jointly_certified:
        left_extended = left.get("raw_pool_extended_sha256")
        right_extended = right.get("raw_pool_extended_sha256")
        if isinstance(left_extended, str) and isinstance(right_extended, str):
            equal_pool = left_extended == right_extended
            extended_pool_pairs += int(equal_pool)
        else:
            equal_pool = (
                isinstance(left.get("raw_pool_common_sha256"), str)
                and left["raw_pool_common_sha256"]
                == right.get("raw_pool_common_sha256")
            )
        if equal_pool:
            pairs.append((left, right))
    candidate_profile = sum(left["B_profile"] for left, _ in pairs)
    reference_profile = sum(right["B_profile"] for _, right in pairs)
    candidate_actual = sum(left["actual_effort"] for left, _ in pairs)
    reference_actual = sum(right["actual_effort"] for _, right in pairs)
    return {
        "candidate": candidate,
        "reference": reference,
        "jointly_certified_cells": len(jointly_certified),
        "jointly_certified_pairs": len(pairs),
        "extended_identity_pairs": extended_pool_pairs,
        "different_or_missing_raw_pool": len(jointly_certified) - len(pairs),
        "B_profile_candidate_total": candidate_profile,
        "B_profile_reference_total": reference_profile,
        "B_profile_candidate_over_reference": _fraction(
            candidate_profile, reference_profile
        ),
        "actual_candidate_total": candidate_actual,
        "actual_reference_total": reference_actual,
        "actual_candidate_over_reference": _fraction(
            candidate_actual, reference_actual
        ),
    }


def paired_summary(matrix, tasks, candidate, reference):
    counts = Counter()
    candidate_total = 0
    reference_total = 0
    effort_pairs = 0
    same_pool = 0
    different_pool = 0
    incomplete_pool = 0
    pool_pairs = 0
    incomplete_metrics = 0
    pool_ineligible_solved = 0
    selector_pair = candidate.startswith("pdb_") and reference.startswith("pdb_")
    for task in tasks:
        left = matrix[(candidate, task)]
        right = matrix[(reference, task)]
        lc = left["coverage"]
        rc = right["coverage"]
        counts[
            "both_solved" if lc and rc else
            "candidate_only" if lc else
            "reference_only" if rc else
            "both_unsolved"
        ] += 1
        left_common_pool = left.get(
            "pdb_profile_selector_raw_pool_common_sha256"
        )
        right_common_pool = right.get(
            "pdb_profile_selector_raw_pool_common_sha256"
        )
        left_extended_pool = left.get(
            "pdb_profile_selector_raw_pool_extended_sha256"
        )
        right_extended_pool = right.get(
            "pdb_profile_selector_raw_pool_extended_sha256"
        )
        both_extended = isinstance(left_extended_pool, str) and isinstance(
            right_extended_pool, str
        )
        left_pool = left_extended_pool if both_extended else left_common_pool
        right_pool = right_extended_pool if both_extended else right_common_pool
        complete_pools = (
            left.get("pdb_profile_selector_trace_certified") is True
            and right.get("pdb_profile_selector_trace_certified") is True
            and isinstance(left_pool, str)
            and isinstance(right_pool, str)
        )
        equal_pool = complete_pools and left_pool == right_pool
        if complete_pools:
            pool_pairs += 1
            if equal_pool:
                same_pool += 1
            else:
                different_pool += 1
        elif selector_pair:
            incomplete_pool += 1
        if lc and rc:
            left_effort = _target_effort(left, candidate)
            right_effort = _target_effort(right, reference)
            if left_effort is None or right_effort is None:
                incomplete_metrics += 1
                continue
            left_cost = left.get("solution_cost")
            right_cost = right.get("solution_cost")
            if (
                type(left_cost) is not int
                or type(right_cost) is not int
                or left_cost != right_cost
            ):
                raise AnalysisError("jointly solved pair has different costs")
            if not selector_pair or equal_pool:
                candidate_total += left_effort
                reference_total += right_effort
                effort_pairs += 1
            else:
                pool_ineligible_solved += 1
    return {
        "protocol": PAIR_PROTOCOL,
        "candidate": candidate,
        "reference": reference,
        "fixed_task_denominator": len(tasks),
        "coverage": {
            **counts,
            "candidate_minus_reference": counts["candidate_only"] - counts["reference_only"],
        },
        "jointly_solved_effort": {
            "eligibility": (
                "jointly-solved-complete-identical-raw-pool"
                if selector_pair else "jointly-solved"
            ),
            "eligible_pairs": effort_pairs,
            "incomplete_metrics_pairs": incomplete_metrics,
            "complete_but_pool_ineligible_pairs": pool_ineligible_solved,
            "candidate_total": candidate_total,
            "reference_total": reference_total,
            "candidate_over_reference": _fraction(candidate_total, reference_total),
        },
        "same_raw_pool": {
            "applicable": selector_pair,
            "eligible_pairs": pool_pairs,
            "identical_pairs": same_pool,
            "different_pairs": different_pool,
            "incomplete_pairs": incomplete_pool,
        },
    }


def blind_profile_overhead_summary(matrix, tasks):
    counts = Counter()
    profiled_time = 0.0
    control_time = 0.0
    profiled_schema_effort = 0
    control_schema_effort = 0
    union_target_effort = 0
    effort_equal = 0
    expansion_equal = 0
    components = Counter()
    jointly_solved = 0
    incomplete_evidence = 0
    for task in tasks:
        profiled = matrix[("blind_fw_profiled", task)]
        control = matrix[("blind_fw", task)]
        pc = profiled["coverage"]
        cc = control["coverage"]
        counts[
            "both_solved" if pc and cc else
            "profiled_only" if pc else
            "control_only" if cc else
            "both_unsolved"
        ] += 1
        if not (pc and cc):
            continue
        if (
            profiled.get("wbh_solved_summary_certified") is not True
            or control.get("wbh_solved_summary_certified") is not True
            or profiled.get("wbh_expansion_profile_complete") is not True
            or control.get("wbh_expansion_profile_complete") is not True
            or profiled.get("wbh_profile_complete") is not True
            or profiled.get("wbh_profile_certified") is not True
        ):
            incomplete_evidence += 1
            continue
        if profiled.get("solution_cost") != control.get("solution_cost"):
            raise AnalysisError("blind profiling control changes solution cost")
        for record in (profiled, control):
            if record.get("wbh_solved_summary_certified") is not True:
                raise AnalysisError("jointly solved blind control lacks schema-v2 done")
        times = (profiled.get("planner_time"), control.get("planner_time"))
        if any(
            type(value) not in (int, float)
            or not math.isfinite(value)
            or value < 0
            for value in times
        ):
            raise AnalysisError("blind profiling control has invalid planner time")
        p_effort = profiled.get("effort")
        c_effort = control.get("effort")
        if any(type(value) is not int or value < 0 for value in (p_effort, c_effort)):
            raise AnalysisError("blind profiling control has invalid schema-v2 effort")
        summary = profiled.get("wbh_profile_summary")
        done = profiled.get("wbh_profile_done")
        if not isinstance(summary, dict) or not isinstance(done, dict):
            raise AnalysisError("jointly solved profiled blind lacks profile summary")
        for field in (
            "union_seconds",
            "cofactor_seconds",
            "heuristic_cofactor_seconds",
            "serialization_seconds",
            "output_seconds",
        ):
            value = summary.get(field)
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise AnalysisError("blind profile overhead component is invalid")
            components[field] += value
        profiled_time += times[0]
        control_time += times[1]
        profiled_schema_effort += p_effort
        control_schema_effort += c_effort
        union_target_effort += done["layer_union_effort"]
        effort_equal += p_effort == c_effort
        expansion_equal += (
            profiled.get("wbh_expansion_profile")
            == control.get("wbh_expansion_profile")
        )
        jointly_solved += 1
    return {
        "fixed_task_denominator": len(tasks),
        "coverage_discordance": {
            **counts,
            "profiled_minus_control": counts["profiled_only"] - counts["control_only"],
        },
        "jointly_solved_same_cost_pairs": jointly_solved,
        "jointly_solved_incomplete_evidence_pairs": incomplete_evidence,
        "planner_time": {
            "profiled_total": profiled_time,
            "control_total": control_time,
            "profiled_over_control": _finite_ratio(profiled_time, control_time),
        },
        "schema_v2_effort": {
            "profiled_total": profiled_schema_effort,
            "control_total": control_schema_effort,
            "equal_pairs": effort_equal,
            "different_pairs": jointly_solved - effort_equal,
        },
        "per_g_expansion_profile": {
            "equal_pairs": expansion_equal,
            "different_pairs": jointly_solved - expansion_equal,
        },
        "profile_instrumentation_seconds": dict(components),
        "semantic_union_target_effort_total": union_target_effort,
    }


def make_analysis(records):
    matrix, tasks, strata = validate_matrix(records)
    certificate_rows, certificate_summaries, certificate_by_cell = (
        profile_certificates(matrix, tasks)
    )
    comparisons = []
    certificate_comparisons = []
    for k, u in P.MATCHED_BUDGETS:
        comparisons.extend(
            (
                paired_summary(
                    matrix, tasks,
                    "pdb_cap_width_k{}".format(k),
                    "pdb_exact_k{}".format(k),
                ),
                paired_summary(
                    matrix, tasks,
                    "pdb_cap_add_u{}".format(u),
                    "pdb_cap_width_k{}".format(k),
                ),
                paired_summary(
                    matrix, tasks,
                    "pdb_exact_k{}".format(k),
                    "pdb_exact_unconstrained",
                ),
                paired_summary(
                    matrix, tasks,
                    "pdb_cap_width_k{}".format(k),
                    "pdb_exact_unconstrained",
                ),
                paired_summary(
                    matrix, tasks,
                    "pdb_cap_add_u{}".format(u),
                    "pdb_exact_unconstrained",
                ),
            )
        )
        certificate_comparisons.extend(
            (
                paired_certificate_summary(
                    certificate_by_cell,
                    tasks,
                    "pdb_cap_width_k{}".format(k),
                    "pdb_exact_k{}".format(k),
                ),
                paired_certificate_summary(
                    certificate_by_cell,
                    tasks,
                    "pdb_cap_add_u{}".format(u),
                    "pdb_cap_width_k{}".format(k),
                ),
                paired_certificate_summary(
                    certificate_by_cell,
                    tasks,
                    "pdb_exact_k{}".format(k),
                    "pdb_exact_unconstrained",
                ),
                paired_certificate_summary(
                    certificate_by_cell,
                    tasks,
                    "pdb_cap_width_k{}".format(k),
                    "pdb_exact_unconstrained",
                ),
                paired_certificate_summary(
                    certificate_by_cell,
                    tasks,
                    "pdb_cap_add_u{}".format(u),
                    "pdb_exact_unconstrained",
                ),
            )
        )
    for label in P.LABELS[2:]:
        comparisons.append(
            paired_summary(matrix, tasks, label, "blind_fw_profiled")
        )
    return {
        "schema": SCHEMA,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "scope": {
            "role": P.COHORT_ROLE,
            "tasks": len(tasks),
            "domains": len({task[0] for task in tasks}),
            "strata": dict(Counter(strata.values())),
            "inference": P.INFERENCE_POLICY,
            "add_match_interpretation": P.ADD_MATCH_ROLE,
            "matched_budget_provenance": {
                "archive_sha256": P.MATCH_ARCHIVE_SHA256,
                "candidate_records": P.MATCH_CANDIDATES,
                "policy": "nearest acceptance-matched transformed candidates",
                "matches": [
                    {
                        "K": k,
                        "U": u,
                        "width_accepted": width_count,
                        "add_accepted": add_count,
                        "acceptance_delta": delta,
                    }
                    for k, u, width_count, add_count, delta in zip(
                        P.WIDTH_BUDGETS,
                        P.TOTAL_ADD_NODE_BUDGETS,
                        P.MATCH_WIDTH_ACCEPTED,
                        P.MATCH_ADD_ACCEPTED,
                        P.MATCH_ACCEPTANCE_DELTAS,
                    )
                ],
            },
        },
        "configs": [
            {
                "label": label,
                **config_summary(
                    matrix, tasks, label, certificate_summaries
                ),
            }
            for label in P.LABELS
        ],
        "comparisons": comparisons,
        "blind_profile_overhead": blind_profile_overhead_summary(matrix, tasks),
        "theorem_certificate": {
            "protocol": PROFILE_CERTIFICATE_PROTOCOL,
            "cut_range": "i=0,...,n-1; terminal cut i=n validation only",
            "eligible_cells": certificate_rows,
            "matched_config_comparisons": certificate_comparisons,
        },
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("properties", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    analysis = make_analysis(load_records(args.properties))
    raw = _canonical(analysis) + b"\n"
    if args.output:
        args.output.write_bytes(raw)
    else:
        print(raw.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AnalysisError as err:
        print("error: {}".format(err), file=__import__("sys").stderr)
        raise SystemExit(2)
