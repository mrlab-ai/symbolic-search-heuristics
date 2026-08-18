#!/usr/bin/env python3
"""Frozen secondary descriptive contract for the cap-grid full census.

This contract was committed while the 1,377-task run was active, before its
properties were fetched and before any scientific outcome or aggregate was
read.  Completion-marker and error-file health monitoring had begun.  The
contract cannot change the primary estimand in ``pdb_cap_grid_full_protocol``.
"""

from __future__ import annotations

import hashlib
import json


CONTRACT = {
    "status": (
        "frozen-during-active-full-execution-before-properties-fetch-or-"
        "scientific-outcome-aggregation/v1"
    ),
    "role": "secondary-descriptive-only-no-primary-or-promotion-effect/v1",
    "task_scopes": [
        "primary-1327-task-development-complement",
        "all-1377-task-census-sensitivity",
    ],
    "selector_summary": {
        "eligibility": "complete-certified-selector-traces-only/v1",
        "configs": ["pdb_selector_k8", "pdb_cap_grid_k8"],
        "counts": [
            "eligible_cells",
            "complete_certified_traces",
            "semantic_nontrivial",
        ],
        "semantic_nontrivial": "finite-sum-positive-or-dead-count-positive/v1",
        "histograms": [
            "effective_cap-with-minus-one-denoting-exact",
            "selected_first_provenance_source",
        ],
        "numeric_summaries": [
            "pattern_size",
            "cofactor_width_W",
            "add_inner_nodes_A",
            "terminal_count_T",
            "total_add_nodes_U_equals_A_plus_T",
            "finite_value_count_V",
        ],
        "summary_fields": [
            "observed",
            "minimum",
            "median",
            "maximum",
            "mean",
            "total",
        ],
    },
    "paired_operational": {
        "candidate": "pdb_cap_grid_k8",
        "reference": "pdb_selector_k8",
        "ratio_direction": "candidate-over-reference",
        "jointly_solved_planner_cpu": (
            "geometric-mean-of-paired-positive-candidate-over-reference-ratios/v1"
        ),
        "image_time": (
            "ratio-of-candidate-and-reference-totals-on-pairs-with-complete-"
            "certified-image-counters/v1"
        ),
        "expanded_bdd_nodes": (
            "ratio-of-candidate-and-reference-totals-on-the-same-complete-"
            "certified-image-pairs/v1"
        ),
        "construction_time": (
            "ratio-of-candidate-and-reference-totals-on-pairs-with-observed-"
            "completed-construction-times/v1"
        ),
        "required_output": [
            "eligible_pair_count",
            "candidate_total-when-additive",
            "reference_total-when-additive",
            "candidate_over_reference",
        ],
    },
    "config_context": {
        "scope": "all-1377-task-census-only",
        "fields": [
            "cells",
            "solved",
            "micro_par2_seconds",
            "solved_planner_cpu_summary",
            "completed_construction_time_summary",
        ],
        "role": "descriptive-context-not-primary-contrast/v1",
    },
    "missingness": (
        "report-fixed-task-denominators-and-each-eligible-pair-or-trace-"
        "denominator-no-imputation/v1"
    ),
    "inference": {
        "confidence_intervals": None,
        "p_values": None,
        "causal_claim": False,
        "population_generalization": False,
    },
}


EXPECTED_CONTRACT_SHA256 = (
    "3a067e1a0767bdf9e9f842806f292596fe80c11347c145afb63bec69d2f3df90"
)


def canonical_json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def contract_sha256():
    return hashlib.sha256(canonical_json(CONTRACT).encode("ascii")).hexdigest()


def validate_contract():
    digest = contract_sha256()
    if EXPECTED_CONTRACT_SHA256 is None:
        raise RuntimeError("secondary descriptive contract hash is unset")
    if digest != EXPECTED_CONTRACT_SHA256:
        raise RuntimeError("secondary descriptive contract changed")
    return digest


if __name__ == "__main__":
    print(validate_contract())
