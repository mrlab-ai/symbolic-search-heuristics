#!/usr/bin/env python3
"""Frozen predictor analysis layered on the complete profile experiment.

This script implements ``pdb_profile_predictor_protocol.md``.  It must only be
run on the complete, recovered 23,886-cell matrix after the base analyzer's
identity and parser gates pass.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_comparison as Base
import pdb_profile_comparison_protocol as P


class PredictorAnalysisError(RuntimeError):
    pass


SCHEMA = "symbolic-search-heuristics/pdb-profile-predictors/v2"
SHARED_COMPARISON_PROTOCOL = "strictly-ordered-shared-pair-comparison/v1"
PROTOCOL_PATH = Path(__file__).with_name("pdb_profile_predictor_protocol.md")
PROTOCOL_SHA256 = (
    "b51c93ae31e3911c3b345de2e9f3c17567cb9c85e34f5fc077b692af2a5d8dab"
)
MIN_STRONG_CLAIM_DOMAINS = (2 * P.COHORT_DOMAINS + 2) // 3
MIN_STRONG_CLAIM_TASKS = (P.COHORT_TASKS + 4) // 5


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
        raise PredictorAnalysisError("analysis is not finite canonical JSON") from err


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as err:
        raise PredictorAnalysisError("cannot read frozen protocol") from err
    return digest.hexdigest()


def require_frozen_protocol() -> None:
    if _sha256(PROTOCOL_PATH) != PROTOCOL_SHA256:
        raise PredictorAnalysisError("predictor protocol bytes changed")


def _ratio(numerator: int, denominator: int):
    if denominator == 0:
        return None
    value = Fraction(numerator, denominator)
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


def _fraction_record(value):
    if value is None:
        return None
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }


def _compare(left, right) -> int:
    return (left > right) - (left < right)


def _compare_fraction(left, right) -> int:
    left_num, left_den = left
    right_num, right_den = right
    return _compare(left_num * right_den, right_num * left_den)


def _quality_key(selected: dict):
    required = (
        "initial_dead_end",
        "initial_h",
        "finite_sum",
        "finite_count",
        "dead_count",
        "abstract_states",
    )
    if any(field not in selected for field in required):
        raise PredictorAnalysisError("selected heuristic lacks quality fields")
    dead = selected["initial_dead_end"]
    initial_h = selected["initial_h"]
    finite_sum = selected["finite_sum"]
    finite_count = selected["finite_count"]
    dead_count = selected["dead_count"]
    abstract_states = selected["abstract_states"]
    if (
        type(dead) is not bool
        or type(finite_sum) is not int
        or finite_sum < 0
        or type(finite_count) is not int
        or finite_count < 1
        or type(dead_count) is not int
        or dead_count < 0
        or type(abstract_states) is not int
        or abstract_states != finite_count + dead_count
        or (dead and initial_h is not None)
        or (not dead and (type(initial_h) is not int or initial_h < 0))
    ):
        raise PredictorAnalysisError("selected heuristic has invalid quality fields")
    # Initial dead-end recognition is the first score component.  Its value
    # dominates the remaining placeholders in the tuple.
    return (
        int(dead),
        0 if dead else initial_h,
        Fraction(finite_sum, finite_count),
        Fraction(dead_count, abstract_states),
    )


def _semantic_id(selected: dict, heuristic: dict, quality) -> str:
    pattern = selected.get("pattern")
    cap = selected.get("value_cap", -1)
    counts = heuristic.get("cofactor_counts")
    if (
        not isinstance(pattern, list)
        or any(type(value) is not int or value < 0 for value in pattern)
        or type(cap) is not int
        or not isinstance(counts, list)
        or any(type(value) is not int or value < 1 for value in counts)
    ):
        raise PredictorAnalysisError("selected heuristic identity is malformed")
    payload = {
        "pattern": pattern,
        "value_cap": cap,
        "add_nodes": heuristic.get("add_nodes"),
        "num_values": heuristic.get("num_values"),
        "num_terminals": heuristic.get("num_terminals"),
        "cofactor_counts": counts,
        "quality": [
            quality[0],
            quality[1],
            [quality[2].numerator, quality[2].denominator],
            [quality[3].numerator, quality[3].denominator],
        ],
    }
    return hashlib.sha256(_canonical(payload)).hexdigest()


def _fragmentation_observation(record: dict, task, label: str):
    if record.get("coverage") != 1:
        return "unsolved", None
    effort = Base._target_effort(record, label)
    done = record.get("wbh_profile_done")
    if (
        effort is None
        or record.get("wbh_profile_certified") is not True
        or record.get("wbh_profile_complete") is not True
        or not isinstance(done, dict)
    ):
        return "incomplete_profile", None
    union_effort = done.get("layer_union_effort")
    if type(union_effort) is not int or union_effort < 0:
        raise PredictorAnalysisError("semantic union effort is invalid")
    if union_effort == 0:
        return "zero_union_effort", None
    selected = record.get("pdb_profile_selector_selected")
    heuristic = record.get("wbh_profile_heuristic_profile")
    if not isinstance(selected, dict) or not isinstance(heuristic, dict):
        raise PredictorAnalysisError("eligible cell lacks selected heuristic profile")
    quality = _quality_key(selected)
    add_nodes = heuristic.get("add_nodes")
    terminals = heuristic.get("num_terminals")
    values = heuristic.get("num_values")
    width = heuristic.get("cofactor_width")
    if any(type(value) is not int for value in (add_nodes, terminals, values, width)):
        raise PredictorAnalysisError("eligible heuristic has noninteger predictors")
    if add_nodes < 0 or terminals < 1 or values < 1 or width < 1:
        raise PredictorAnalysisError("eligible heuristic has invalid predictors")
    if selected.get("cofactor_width") != width:
        raise PredictorAnalysisError("selector/profile width mismatch")
    total_add = add_nodes + terminals
    if selected.get("width_upper_bound") != total_add:
        raise PredictorAnalysisError("selector/profile total-ADD mismatch")
    domain, problem = task
    return "eligible", {
        "domain": domain,
        "problem": problem,
        "task": task,
        "config": label,
        "semantic_id": _semantic_id(selected, heuristic, quality),
        "cofactor_width": width,
        "total_add_nodes": total_add,
        "finite_values": values,
        "_quality": quality,
        "actual_effort": effort,
        "semantic_union_effort": union_effort,
        "_fragmentation": (effort, union_effort),
    }


def fragmentation_observations(matrix, tasks):
    statuses = Counter()
    grouped = defaultdict(dict)
    by_cell = {}
    for task in tasks:
        for label in P.LABELS[2:]:
            status, observation = _fragmentation_observation(
                matrix[(label, task)], task, label
            )
            statuses[status] += 1
            if observation is None:
                continue
            semantic_id = observation["semantic_id"]
            previous = grouped[task].get(semantic_id)
            if previous is None:
                observation["configs"] = [label]
                grouped[task][semantic_id] = observation
            else:
                invariant = (
                    "cofactor_width",
                    "total_add_nodes",
                    "finite_values",
                    "_quality",
                    "actual_effort",
                    "semantic_union_effort",
                    "_fragmentation",
                )
                if any(previous[field] != observation[field] for field in invariant):
                    raise PredictorAnalysisError(
                        "duplicate selected heuristic has different deterministic evidence"
                    )
                previous["configs"].append(label)
            by_cell[(label, task)] = grouped[task][semantic_id]
    observations = [
        observation
        for task in tasks
        for observation in grouped.get(task, {}).values()
    ]
    return observations, grouped, by_cell, dict(statuses)


def _pairwise_summary(
    grouped, predictor: str, target: str, direction: str, all_domains=None
):
    if direction not in {"same", "opposite"}:
        raise PredictorAnalysisError("invalid predictor direction")
    totals = Counter()
    domains = defaultdict(Counter)
    tasks_with_pairs = set()
    for task, observations_by_id in grouped.items():
        observations = list(observations_by_id.values())
        for left, right in itertools.combinations(observations, 2):
            predictor_order = _compare(left[predictor], right[predictor])
            if target == "_fragmentation":
                target_order = _compare_fraction(left[target], right[target])
            else:
                target_order = _compare(left[target], right[target])
            if predictor_order == 0 and target_order == 0:
                outcome = "both_tied"
            elif predictor_order == 0:
                outcome = "predictor_tied"
            elif target_order == 0:
                outcome = "target_tied"
            else:
                expected = predictor_order if direction == "same" else -predictor_order
                outcome = "concordant" if expected == target_order else "discordant"
                tasks_with_pairs.add(task)
            totals[outcome] += 1
            domains[task[0]][outcome] += 1

    if all_domains is None:
        all_domains = {task[0] for task in grouped}
    else:
        all_domains = set(all_domains)
    if not all_domains or any(type(domain) is not str for domain in all_domains):
        raise PredictorAnalysisError("pairwise domain universe is invalid")

    domain_rows = []
    domain_values = {}
    for domain in sorted(all_domains):
        counts = domains[domain]
        comparable = counts["concordant"] + counts["discordant"]
        value = (
            Fraction(counts["concordant"], comparable)
            if comparable
            else None
        )
        domain_values[domain] = value
        domain_rows.append({
            "domain": domain,
            **dict(counts),
            "comparable": comparable,
            "concordance": _fraction_record(value),
        })
    eligible_domain_values = {
        domain: value for domain, value in domain_values.items() if value is not None
    }
    macro = _mean(eligible_domain_values.values())
    loo = {}
    for omitted in sorted(all_domains):
        retained = [
            value
            for domain, value in eligible_domain_values.items()
            if domain != omitted
        ]
        loo[omitted] = _mean(retained)
    loo_values = [value for value in loo.values() if value is not None]
    comparable = totals["concordant"] + totals["discordant"]
    return {
        "predictor": predictor.removeprefix("_"),
        "target": target.removeprefix("_"),
        "direction": direction,
        "distinct_heuristic_pairs": sum(totals.values()),
        "tasks_with_comparable_pairs": len(tasks_with_pairs),
        **dict(totals),
        "comparable": comparable,
        "micro_concordance": _ratio(totals["concordant"], comparable),
        "eligible_domains": len(eligible_domain_values),
        "equal_domain_macro": _fraction_record(macro),
        "leave_one_domain_out": {
            "values": {
                domain: _fraction_record(value) for domain, value in loo.items()
            },
            "minimum": _fraction_record(min(loo_values)) if loo_values else None,
            "maximum": _fraction_record(max(loo_values)) if loo_values else None,
        },
        "by_domain": domain_rows,
    }


def _shared_pairwise_comparison(grouped, predictor_specs, target, all_domains):
    """Compare predictors on one identical, strictly ordered task-pair set."""
    all_domains = set(all_domains)
    if not all_domains or not predictor_specs:
        raise PredictorAnalysisError("shared comparison universe is empty")
    for key, (predictor, direction) in predictor_specs.items():
        if type(key) is not str or direction not in {"same", "opposite"}:
            raise PredictorAnalysisError("shared predictor specification is invalid")

    exclusions = Counter()
    tied_by_predictor = Counter()
    common_by_domain = Counter()
    tasks_with_pairs = set()
    predictor_totals = {key: Counter() for key in predictor_specs}
    predictor_domains = {
        key: defaultdict(Counter) for key in predictor_specs
    }
    for task, observations_by_id in grouped.items():
        observations = list(observations_by_id.values())
        for left, right in itertools.combinations(observations, 2):
            if target == "_fragmentation":
                target_order = _compare_fraction(left[target], right[target])
            else:
                target_order = _compare(left[target], right[target])
            if target_order == 0:
                exclusions["target_tied"] += 1
                continue
            orders = {
                key: _compare(left[predictor], right[predictor])
                for key, (predictor, _) in predictor_specs.items()
            }
            tied = [key for key, order in orders.items() if order == 0]
            if tied:
                exclusions["any_predictor_tied"] += 1
                for key in tied:
                    tied_by_predictor[key] += 1
                continue
            exclusions["comparable"] += 1
            common_by_domain[task[0]] += 1
            tasks_with_pairs.add(task)
            for key, (_, direction) in predictor_specs.items():
                expected = orders[key] if direction == "same" else -orders[key]
                outcome = "concordant" if expected == target_order else "discordant"
                predictor_totals[key][outcome] += 1
                predictor_domains[key][task[0]][outcome] += 1

    summaries = {}
    for key, (predictor, direction) in predictor_specs.items():
        totals = predictor_totals[key]
        domain_values = {}
        domain_rows = []
        for domain in sorted(all_domains):
            counts = predictor_domains[key][domain]
            comparable = counts["concordant"] + counts["discordant"]
            value = (
                Fraction(counts["concordant"], comparable)
                if comparable
                else None
            )
            domain_values[domain] = value
            domain_rows.append({
                "domain": domain,
                "concordant": counts["concordant"],
                "discordant": counts["discordant"],
                "comparable": comparable,
                "concordance": _fraction_record(value),
            })
        eligible = {
            domain: value for domain, value in domain_values.items()
            if value is not None
        }
        macro = _mean(eligible.values())
        loo = {
            omitted: _mean(
                value for domain, value in eligible.items() if domain != omitted
            )
            for omitted in sorted(all_domains)
        }
        finite_loo = [value for value in loo.values() if value is not None]
        comparable = totals["concordant"] + totals["discordant"]
        summaries[key] = {
            "predictor": predictor.removeprefix("_"),
            "target": target.removeprefix("_"),
            "direction": direction,
            "distinct_heuristic_pairs": comparable,
            "concordant": totals["concordant"],
            "discordant": totals["discordant"],
            "comparable": comparable,
            "micro_concordance": _ratio(totals["concordant"], comparable),
            "tasks_with_comparable_pairs": len(tasks_with_pairs),
            "eligible_domains": len(eligible),
            "equal_domain_macro": _fraction_record(macro),
            "leave_one_domain_out": {
                "values": {
                    domain: _fraction_record(value) for domain, value in loo.items()
                },
                "minimum": _fraction_record(min(finite_loo)) if finite_loo else None,
                "maximum": _fraction_record(max(finite_loo)) if finite_loo else None,
            },
            "by_domain": domain_rows,
        }
    return {
        "protocol": SHARED_COMPARISON_PROTOCOL,
        "target": target.removeprefix("_"),
        "support": {
            "observation_pairs": sum(exclusions.values()),
            "target_tied": exclusions["target_tied"],
            "any_predictor_tied": exclusions["any_predictor_tied"],
            "comparable": exclusions["comparable"],
            "tasks_with_comparable_pairs": len(tasks_with_pairs),
            "eligible_domains": sum(value > 0 for value in common_by_domain.values()),
            "predictor_tie_counts": dict(tied_by_predictor),
            "by_domain": [
                {"domain": domain, "comparable": common_by_domain[domain]}
                for domain in sorted(all_domains)
            ],
        },
        "predictors": summaries,
    }


def fragmentation_predictors(grouped, domains=None):
    return {
        "cofactor_width": _pairwise_summary(
            grouped, "cofactor_width", "_fragmentation", "same", domains
        ),
        "total_add_nodes": _pairwise_summary(
            grouped, "total_add_nodes", "_fragmentation", "same", domains
        ),
        "finite_values": _pairwise_summary(
            grouped, "finite_values", "_fragmentation", "same", domains
        ),
        "quality": _pairwise_summary(
            grouped, "_quality", "_fragmentation", "opposite", domains
        ),
        "quality_to_total_effort": _pairwise_summary(
            grouped, "_quality", "actual_effort", "opposite", domains
        ),
    }


def fragmentation_gate_comparison(grouped, domains):
    return _shared_pairwise_comparison(
        grouped,
        {
            "cofactor_width": ("cofactor_width", "same"),
            "total_add_nodes": ("total_add_nodes", "same"),
            "quality": ("_quality", "opposite"),
        },
        "_fragmentation",
        domains,
    )


def _certificate_observation_groups(certificate_rows, matrix):
    grouped = defaultdict(dict)
    for row in certificate_rows:
        task = (row["domain"], row["problem"])
        record = matrix[(row["config"], task)]
        selected = record.get("pdb_profile_selector_selected")
        heuristic = record.get("wbh_profile_heuristic_profile")
        if not isinstance(selected, dict) or not isinstance(heuristic, dict):
            raise PredictorAnalysisError(
                "certificate-eligible cell lacks selected heuristic identity"
            )
        semantic_id = _semantic_id(
            selected, heuristic, _quality_key(selected)
        )
        item = {
            "domain": row["domain"],
            "problem": row["problem"],
            "task": task,
            "semantic_id": semantic_id,
            "B_profile": row["B_profile"],
            "B_width": row["B_width"],
            "B_add": row["B_add_apply_cudd_safe"],
            "actual_effort": row["actual_effort"],
        }
        previous = grouped[task].get(semantic_id)
        if previous is None:
            grouped[task][semantic_id] = item
        elif any(
            previous[field] != item[field]
            for field in ("B_profile", "B_width", "B_add", "actual_effort")
        ):
            raise PredictorAnalysisError(
                "duplicate heuristic has different certificate evidence"
            )
    return grouped


def certificate_predictors(certificate_rows, matrix, domains=None):
    grouped = _certificate_observation_groups(certificate_rows, matrix)
    return {
        "B_profile": _pairwise_summary(
            grouped, "B_profile", "actual_effort", "same", domains
        ),
        "B_width": _pairwise_summary(
            grouped, "B_width", "actual_effort", "same", domains
        ),
        "B_add": _pairwise_summary(
            grouped, "B_add", "actual_effort", "same", domains
        ),
    }


def certificate_gate_comparison(certificate_rows, matrix, domains):
    grouped = _certificate_observation_groups(certificate_rows, matrix)
    return _shared_pairwise_comparison(
        grouped,
        {
            "B_profile": ("B_profile", "same"),
            "B_width": ("B_width", "same"),
            "B_add": ("B_add", "same"),
        },
        "actual_effort",
        domains,
    )


def _pool_equal(left: dict, right: dict) -> bool:
    left_extended = left.get("pdb_profile_selector_raw_pool_extended_sha256")
    right_extended = right.get("pdb_profile_selector_raw_pool_extended_sha256")
    if isinstance(left_extended, str) and isinstance(right_extended, str):
        return left_extended == right_extended
    left_common = left.get("pdb_profile_selector_raw_pool_common_sha256")
    right_common = right.get("pdb_profile_selector_raw_pool_common_sha256")
    return isinstance(left_common, str) and left_common == right_common


def selector_contrast(matrix, tasks, candidate: str, reference: str):
    counts = Counter()
    domain_counts = defaultdict(Counter)
    domain_effort = defaultdict(lambda: [0, 0, 0])
    candidate_total = 0
    reference_total = 0
    eligible_pairs = 0
    selector_pair = candidate.startswith("pdb_") and reference.startswith("pdb_")
    for task in tasks:
        left = matrix[(candidate, task)]
        right = matrix[(reference, task)]
        lc = left["coverage"]
        rc = right["coverage"]
        outcome = (
            "both_solved" if lc and rc else
            "candidate_only" if lc else
            "reference_only" if rc else
            "both_unsolved"
        )
        counts[outcome] += 1
        domain_counts[task[0]][outcome] += 1
        if not (lc and rc):
            continue
        left_effort = Base._target_effort(left, candidate)
        right_effort = Base._target_effort(right, reference)
        if left_effort is None or right_effort is None:
            counts["incomplete_effort"] += 1
            continue
        if left.get("solution_cost") != right.get("solution_cost"):
            raise PredictorAnalysisError("jointly solved contrast has unequal costs")
        if selector_pair and not _pool_equal(left, right):
            counts["pool_ineligible"] += 1
            continue
        candidate_total += left_effort
        reference_total += right_effort
        eligible_pairs += 1
        domain_effort[task[0]][0] += left_effort
        domain_effort[task[0]][1] += right_effort
        domain_effort[task[0]][2] += 1

    domain_rows = []
    domain_differences = []
    for domain in sorted(domain_counts):
        dc = domain_counts[domain]
        task_count = sum(dc[key] for key in (
            "both_solved", "candidate_only", "reference_only", "both_unsolved"
        ))
        difference = Fraction(
            dc["candidate_only"] - dc["reference_only"], task_count
        )
        domain_differences.append(difference)
        ce, re, pairs = domain_effort[domain]
        domain_rows.append({
            "domain": domain,
            "tasks": task_count,
            **dict(dc),
            "coverage_difference": _fraction_record(difference),
            "effort_eligible_pairs": pairs,
            "candidate_effort": ce,
            "reference_effort": re,
            "effort_ratio": _ratio(ce, re),
        })

    loo_effort = {}
    loo_coverage = {}
    for row in domain_rows:
        domain = row["domain"]
        loo_effort[domain] = _ratio(
            candidate_total - row["candidate_effort"],
            reference_total - row["reference_effort"],
        )
        remaining = [
            item["coverage_difference"]
            for item in domain_rows
            if item["domain"] != domain
        ]
        loo_coverage[domain] = _fraction_record(_mean(
            Fraction(item["numerator"], item["denominator"])
            for item in remaining
        ))
    return {
        "candidate": candidate,
        "reference": reference,
        "fixed_task_denominator": len(tasks),
        "coverage": {
            **dict(counts),
            "candidate_minus_reference": (
                counts["candidate_only"] - counts["reference_only"]
            ),
            "equal_domain_macro_difference": _fraction_record(
                _mean(domain_differences)
            ),
        },
        "conditional_effort": {
            "eligible_pairs": eligible_pairs,
            "candidate_total": candidate_total,
            "reference_total": reference_total,
            "candidate_over_reference": _ratio(candidate_total, reference_total),
        },
        "leave_one_domain_out": {
            "effort_ratio": loo_effort,
            "coverage_macro_difference": loo_coverage,
        },
        "by_domain": domain_rows,
    }


def selector_contrasts(matrix, tasks):
    matched_width_add = []
    cap_exact = []
    constrained_unconstrained = []
    selector_blind = []
    for k, u in P.MATCHED_BUDGETS:
        width = "pdb_cap_width_k{}".format(k)
        add = "pdb_cap_add_u{}".format(u)
        exact = "pdb_exact_k{}".format(k)
        matched_width_add.append(selector_contrast(matrix, tasks, width, add))
        cap_exact.append(selector_contrast(matrix, tasks, width, exact))
        for label in (exact, width, add):
            constrained_unconstrained.append(selector_contrast(
                matrix, tasks, label, "pdb_exact_unconstrained"
            ))
    for label in P.LABELS[2:]:
        selector_blind.append(selector_contrast(
            matrix, tasks, label, "blind_fw_profiled"
        ))
    return {
        "matched_width_vs_add": matched_width_add,
        "cap_width_vs_exact_width": cap_exact,
        "constrained_vs_unconstrained": constrained_unconstrained,
        "selector_vs_profiled_blind": selector_blind,
    }


def _all_budget_summary(contrasts):
    if not contrasts:
        raise PredictorAnalysisError("all-budget contrast set is empty")
    domain_sets = []
    for contrast in contrasts:
        rows = contrast.get("by_domain")
        if not isinstance(rows, list) or len(rows) != P.COHORT_DOMAINS:
            raise PredictorAnalysisError("contrast domain universe is incomplete")
        names = [row.get("domain") for row in rows if isinstance(row, dict)]
        if (
            len(names) != P.COHORT_DOMAINS
            or any(type(name) is not str for name in names)
            or len(set(names)) != P.COHORT_DOMAINS
        ):
            raise PredictorAnalysisError("contrast domain universe is invalid")
        domain_sets.append(set(names))
    if any(domains != domain_sets[0] for domains in domain_sets[1:]):
        raise PredictorAnalysisError("contrast domain universes disagree")

    candidate_total = sum(
        item["conditional_effort"]["candidate_total"] for item in contrasts
    )
    reference_total = sum(
        item["conditional_effort"]["reference_total"] for item in contrasts
    )
    coverage = sum(
        item["coverage"]["candidate_minus_reference"] for item in contrasts
    )
    domains = sorted(domain_sets[0])
    loo = {}
    loo_coverage = {}
    for domain in domains:
        removed_candidate = 0
        removed_reference = 0
        removed_coverage = 0
        for item in contrasts:
            row = next(row for row in item["by_domain"] if row["domain"] == domain)
            removed_candidate += row["candidate_effort"]
            removed_reference += row["reference_effort"]
            removed_coverage += row.get("candidate_only", 0) - row.get(
                "reference_only", 0
            )
        loo[domain] = _ratio(
            candidate_total - removed_candidate,
            reference_total - removed_reference,
        )
        loo_coverage[domain] = coverage - removed_coverage
    return {
        "conditional_effort": {
            "candidate_total": candidate_total,
            "reference_total": reference_total,
            "candidate_over_reference": _ratio(candidate_total, reference_total),
        },
        "coverage_candidate_minus_reference": coverage,
        "leave_one_domain_out_effort_ratio": loo,
        "leave_one_domain_out_coverage_difference": loo_coverage,
    }


def _value(summary, *path):
    current = summary
    for key in path:
        if current is None:
            return None
        current = current.get(key)
    return current


def _exact_fraction(record, label):
    """Recover an exact rational from an internally generated fraction record."""
    if record is None:
        return None
    if not isinstance(record, dict):
        raise PredictorAnalysisError("{} is not a fraction record".format(label))
    numerator = record.get("numerator")
    denominator = record.get("denominator")
    if (
        type(numerator) is not int
        or type(denominator) is not int
        or denominator <= 0
    ):
        raise PredictorAnalysisError("{} is not an exact fraction".format(label))
    value = Fraction(numerator, denominator)
    if value.numerator != numerator or value.denominator != denominator:
        raise PredictorAnalysisError("{} is not reduced".format(label))
    return value


def _pairwise_support(summary):
    return (
        type(summary.get("eligible_domains")) is int
        and summary["eligible_domains"] >= MIN_STRONG_CLAIM_DOMAINS
        and type(summary.get("tasks_with_comparable_pairs")) is int
        and summary["tasks_with_comparable_pairs"] >= MIN_STRONG_CLAIM_TASKS
    )


def _contrast_support(contrast):
    effort = contrast.get("conditional_effort")
    rows = contrast.get("by_domain")
    if not isinstance(effort, dict) or not isinstance(rows, list):
        return False
    eligible = effort.get("eligible_pairs")
    if type(eligible) is not int or eligible < MIN_STRONG_CLAIM_TASKS:
        return False
    if len(rows) != P.COHORT_DOMAINS:
        return False
    domain_names = [row.get("domain") for row in rows if isinstance(row, dict)]
    if (
        len(domain_names) != P.COHORT_DOMAINS
        or len(set(domain_names)) != P.COHORT_DOMAINS
        or any(type(domain) is not str for domain in domain_names)
    ):
        return False
    contributing_domains = sum(
        isinstance(row, dict)
        and type(row.get("effort_eligible_pairs")) is int
        and row["effort_eligible_pairs"] > 0
        for row in rows
    )
    return contributing_domains >= MIN_STRONG_CLAIM_DOMAINS


def decision_gates(fragmentation, certificates, contrasts):
    width = fragmentation["cofactor_width"]
    quality = fragmentation["quality"]
    add = fragmentation["total_add_nodes"]
    width_macro = _exact_fraction(
        _value(width, "equal_domain_macro"), "width macro"
    )
    width_loo_min = _exact_fraction(
        _value(width, "leave_one_domain_out", "minimum"), "width LOO minimum"
    )
    quality_macro = _exact_fraction(
        _value(quality, "equal_domain_macro"), "quality macro"
    )
    add_macro = _exact_fraction(
        _value(add, "equal_domain_macro"), "ADD macro"
    )
    width_loo_records = _value(
        width, "leave_one_domain_out", "values"
    ) or {}
    width_loo_values = [
        _exact_fraction(record, "width LOO {}".format(domain))
        for domain, record in width_loo_records.items()
    ]
    complete_width_loo = (
        len(width_loo_records) == P.COHORT_DOMAINS
        and all(value is not None for value in width_loo_values)
    )
    fragmentation_criteria = {
        "broad_support": all(
            _pairwise_support(summary) for summary in (width, quality, add)
        ),
        "macro_at_least_0_65": (
            width_macro is not None and width_macro >= Fraction(13, 20)
        ),
        "loo_min_at_least_0_60": (
            complete_width_loo
            and width_loo_min is not None
            and width_loo_min >= Fraction(3, 5)
        ),
        "beats_quality": (
            width_macro is not None
            and quality_macro is not None
            and width_macro > quality_macro
        ),
        "within_0_02_of_add": (
            width_macro is not None
            and add_macro is not None
            and width_macro >= add_macro - Fraction(1, 50)
        ),
    }

    profile_macro = _exact_fraction(
        _value(certificates["B_profile"], "equal_domain_macro"),
        "profile-certificate macro",
    )
    width_bound_macro = _exact_fraction(
        _value(certificates["B_width"], "equal_domain_macro"),
        "width-certificate macro",
    )
    add_bound_macro = _exact_fraction(
        _value(certificates["B_add"], "equal_domain_macro"),
        "ADD-certificate macro",
    )
    profile_loo = _value(
        certificates["B_profile"], "leave_one_domain_out", "values"
    ) or {}
    width_bound_loo = _value(
        certificates["B_width"], "leave_one_domain_out", "values"
    ) or {}
    add_bound_loo = _value(
        certificates["B_add"], "leave_one_domain_out", "values"
    ) or {}
    profile_domains = set(profile_loo)
    width_bound_domains = set(width_bound_loo)
    add_bound_domains = set(add_bound_loo)
    complete_profile_loo = (
        len(profile_domains) == P.COHORT_DOMAINS
        and profile_domains == width_bound_domains == add_bound_domains
    )
    loo_advantages = []
    for domain in sorted(profile_domains | width_bound_domains | add_bound_domains):
        pv = _exact_fraction(profile_loo.get(domain), "profile LOO {}".format(domain))
        wv = _exact_fraction(
            width_bound_loo.get(domain), "width LOO {}".format(domain)
        )
        av = _exact_fraction(add_bound_loo.get(domain), "ADD LOO {}".format(domain))
        if None not in (pv, wv, av):
            loo_advantages.append(pv > wv and pv > av)
        else:
            loo_advantages.append(False)
    profile_criteria = {
        "broad_support": all(
            _pairwise_support(summary) for summary in certificates.values()
        ),
        "beats_both_macro": (
            None not in (profile_macro, width_bound_macro, add_bound_macro)
            and profile_macro > width_bound_macro
            and profile_macro > add_bound_macro
        ),
        "margin_at_least_0_02": (
            None not in (profile_macro, width_bound_macro, add_bound_macro)
            and profile_macro >= width_bound_macro + Fraction(1, 50)
            and profile_macro >= add_bound_macro + Fraction(1, 50)
        ),
        "positive_every_loo": (
            complete_profile_loo
            and len(loo_advantages) == P.COHORT_DOMAINS
            and all(loo_advantages)
        ),
    }

    width_add = contrasts["matched_width_vs_add"]
    width_add_all = _all_budget_summary(width_add)
    width_add_ratios = [
        _exact_fraction(
            _value(item, "conditional_effort", "candidate_over_reference"),
            "matched width/ADD effort ratio",
        )
        for item in width_add
    ]
    effort_wins = sum(
        value is not None and value < 1 for value in width_add_ratios
    )
    width_add_all_ratio = _exact_fraction(
        _value(
            width_add_all,
            "conditional_effort",
            "candidate_over_reference",
        ),
        "all-budget width/ADD effort ratio",
    )
    width_add_loo = width_add_all["leave_one_domain_out_effort_ratio"]
    width_add_criteria = {
        "broad_support_every_budget": all(
            _contrast_support(item) for item in width_add
        ),
        "effort_wins_at_least_4_of_5": effort_wins >= 4,
        "all_budget_effort_below_1": (
            width_add_all_ratio is not None and width_add_all_ratio < 1
        ),
        "all_budget_effort_reduction_at_least_0_02": (
            width_add_all_ratio is not None
            and width_add_all_ratio <= Fraction(49, 50)
        ),
        "no_budget_coverage_loss_below_minus_2": all(
            item["coverage"]["candidate_minus_reference"] >= -2
            for item in width_add
        ),
        "every_loo_effort_below_1": (
            len(width_add_loo) == P.COHORT_DOMAINS
            and all(
                _exact_fraction(row, "width/ADD LOO effort ratio") is not None
                and _exact_fraction(row, "width/ADD LOO effort ratio") < 1
                for row in width_add_loo.values()
            )
        ),
    }

    cap_exact = contrasts["cap_width_vs_exact_width"]
    cap_exact_all = _all_budget_summary(cap_exact)
    cap_exact_ratios = [
        _exact_fraction(
            _value(item, "conditional_effort", "candidate_over_reference"),
            "cap/exact effort ratio",
        )
        for item in cap_exact
    ]
    cap_effort_wins = sum(
        value is not None and value < 1 for value in cap_exact_ratios
    )
    cap_exact_all_ratio = _exact_fraction(
        _value(
            cap_exact_all,
            "conditional_effort",
            "candidate_over_reference",
        ),
        "all-budget cap/exact effort ratio",
    )
    cap_loo_effort = cap_exact_all["leave_one_domain_out_effort_ratio"]
    cap_loo_coverage = cap_exact_all["leave_one_domain_out_coverage_difference"]
    complete_cap_loo = (
        len(cap_loo_effort) == P.COHORT_DOMAINS
        and set(cap_loo_effort) == set(cap_loo_coverage)
    )
    cap_criteria = {
        "broad_support_every_budget": all(
            _contrast_support(item) for item in cap_exact
        ),
        "effort_wins_at_least_3_of_5": cap_effort_wins >= 3,
        "all_budget_effort_reduction_at_least_0_02": (
            cap_exact_all_ratio is not None
            and cap_exact_all_ratio <= Fraction(49, 50)
        ),
        "no_budget_coverage_loss_below_minus_2": all(
            item["coverage"]["candidate_minus_reference"] >= -2
            for item in cap_exact
        ),
        "aggregate_coverage_nonnegative": (
            cap_exact_all["coverage_candidate_minus_reference"] >= 0
        ),
        "no_loo_reversal": (
            complete_cap_loo
            and all(
                _exact_fraction(row, "cap/exact LOO effort ratio") is not None
                and _exact_fraction(row, "cap/exact LOO effort ratio") < 1
                for row in cap_loo_effort.values()
            )
            and all(value >= 0 for value in cap_loo_coverage.values())
        ),
    }
    cap_blind_by_label = {
        item["candidate"]: item
        for item in contrasts["selector_vs_profiled_blind"]
    }
    cap_blind = [
        cap_blind_by_label["pdb_cap_width_k{}".format(k)]
        for k in P.WIDTH_BUDGETS
    ]
    cap_blind_coverage_wins = sum(
        item["coverage"]["candidate_minus_reference"] > 0
        for item in cap_blind
    )
    cap_blind_coverage_differences = [
        item["coverage"]["candidate_minus_reference"] for item in cap_blind
    ]
    blind_coverage_criteria = {
        "material_effort_gate_passes": all(cap_criteria.values()),
        "coverage_wins_at_least_3_of_5": cap_blind_coverage_wins >= 3,
        "aggregate_coverage_nonnegative": (
            sum(cap_blind_coverage_differences) >= 0
        ),
        "no_budget_coverage_loss_below_minus_2": all(
            difference >= -2 for difference in cap_blind_coverage_differences
        ),
    }
    return {
        "cofactor_width_useful_fragmentation_predictor": {
            "pass": all(fragmentation_criteria.values()),
            "criteria": fragmentation_criteria,
        },
        "cut_aligned_profile_sharper_explanation": {
            "pass": all(profile_criteria.values()),
            "criteria": profile_criteria,
        },
        "width_filter_materially_lower_effort_than_matched_add": {
            "pass": all(width_add_criteria.values()),
            "criteria": width_add_criteria,
            "all_budget": width_add_all,
        },
        "cap_aware_width_materially_lower_effort_than_exact_width": {
            "pass": all(cap_criteria.values()),
            "criteria": cap_criteria,
            "all_budget": cap_exact_all,
        },
        "cap_aware_width_higher_coverage_than_profiled_blind": {
            "pass": all(blind_coverage_criteria.values()),
            "criteria": blind_coverage_criteria,
            "fixed_budget_contrasts": cap_blind,
        },
    }


def make_analysis(records):
    require_frozen_protocol()
    matrix, tasks, _ = Base.validate_matrix(records)
    certificate_rows, _, _ = Base.profile_certificates(matrix, tasks)
    observations, grouped, _, statuses = fragmentation_observations(
        matrix, tasks
    )
    domains = {task[0] for task in tasks}
    fragmentation = fragmentation_predictors(grouped, domains)
    fragmentation_comparison = fragmentation_gate_comparison(grouped, domains)
    certificates = certificate_predictors(certificate_rows, matrix, domains)
    certificate_comparison = certificate_gate_comparison(
        certificate_rows, matrix, domains
    )
    contrasts = selector_contrasts(matrix, tasks)
    public_observations = []
    for observation in observations:
        public_observations.append({
            key: value
            for key, value in observation.items()
            if not key.startswith("_") and key != "task"
        } | {
            "quality": [
                observation["_quality"][0],
                observation["_quality"][1],
                _fraction_record(observation["_quality"][2]),
                _fraction_record(observation["_quality"][3]),
            ],
            "fragmentation": _ratio(*observation["_fragmentation"]),
        })
    result = {
        "schema": SCHEMA,
        "raw_analysis_protocol": P.ANALYSIS_PROTOCOL,
        "frozen_predictor_protocol_sha256": PROTOCOL_SHA256,
        "scope": {
            "tasks": len(tasks),
            "domains": len({task[0] for task in tasks}),
            "configurations": P.CONFIG_COUNT,
            "inference": P.INFERENCE_POLICY,
            "strong_claim_support": {
                "minimum_domains": MIN_STRONG_CLAIM_DOMAINS,
                "minimum_tasks_or_pairs": MIN_STRONG_CLAIM_TASKS,
            },
        },
        "fragmentation_observation_status": statuses,
        "fragmentation_observations": public_observations,
        "fragmentation_predictors": fragmentation,
        "fragmentation_gate_comparison": fragmentation_comparison,
        "certificate_predictors": certificates,
        "certificate_gate_comparison": certificate_comparison,
        "selector_contrasts": contrasts,
    }
    result["decision_gates"] = decision_gates(
        fragmentation_comparison["predictors"],
        certificate_comparison["predictors"],
        contrasts,
    )
    return result


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("properties", type=Path)
    parser.add_argument("--output", type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    analysis = make_analysis(Base.load_records(args.properties))
    raw = _canonical(analysis) + b"\n"
    if args.output:
        args.output.write_bytes(raw)
    else:
        print(raw.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Base.AnalysisError, PredictorAnalysisError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
