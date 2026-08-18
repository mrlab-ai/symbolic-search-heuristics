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
        "scientific-outcome-aggregation/v2"
    ),
    "amendment": (
        "v2-adds-scope-specific-solved-count-and-solved-runtime-total-"
        "identities-so-every-reported-micro-par2-value-is-reconstructed/v1"
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
        "count_summary_total_type": (
            "exact-nonnegative-integer-when-observed-else-null/v1"
        ),
    },
    "paired_operational": {
        "candidate": "pdb_cap_grid_k8",
        "reference": "pdb_selector_k8",
        "ratio_direction": "candidate-over-reference",
        "micro_par2_seconds": (
            "candidate-reference-and-candidate-minus-reference-arithmetic-"
            "means-over-the-fixed-task-denominator-with-unsolved-equal-600-"
            "reconstructed-from-solved-counts-and-solved-runtime-totals/v2"
        ),
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
        "micro_par2_required_output": [
            "fixed_task_denominator",
            "candidate_solved",
            "reference_solved",
            "candidate_solved_planner_cpu_total_seconds",
            "reference_solved_planner_cpu_total_seconds",
            "candidate",
            "reference",
            "candidate_minus_reference",
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
    "1df86a1255cb301ffe2b6eb0db52ba81ca7f8c511e5a011cd028d8eff2dfc862"
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
