#!/usr/bin/env python3
"""Pre-registered I-versus-mJ analysis for the dual-metric campaign."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import pdb_terminal_metric_choice_audit as Audit
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_parser as Trace
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_runner as Runner


class AnalysisError(RuntimeError):
    pass


ANALYSIS_SCHEMA = P.FREEZE_SCHEMA + "/analysis/v4"
RECEIPT_SCHEMA = ANALYSIS_SCHEMA + "/double-execution"
DEFAULT_OUTPUT = P.ARTIFACT_DIR / "analysis-v4.json"
DEFAULT_REPEAT_OUTPUT = P.ARTIFACT_DIR / "analysis-v4-repeat.json"
DEFAULT_RECEIPT = P.ARTIFACT_DIR / "analysis-execution-receipt-v4.json"
DEFAULT_RECEIPT_PIN = P.ARTIFACT_DIR / "analysis-execution-receipt-v4.sha256"


def _fraction(value: Fraction | None):
    if value is None:
        return None
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "decimal": float(value),
    }


def _mean(values):
    values = list(values)
    return None if not values else sum(values, Fraction()) / len(values)


def _par2(record: dict) -> Fraction:
    coverage = record.get("coverage")
    if type(coverage) is not int or coverage not in (0, 1):
        raise AnalysisError("coverage is not binary")
    code = record.get("planner_exit_code")
    if type(code) is not int:
        raise AnalysisError("planner exit code is not an integer")
    if coverage == 0:
        if code == 0:
            raise AnalysisError("unsolved cell has the success planner exit code")
        return Fraction(P.PAR2_SECONDS)
    if code != 0:
        raise AnalysisError("solved cell has a non-success planner exit code")
    value = record.get("total_time")
    if type(value) not in (int, float) or not math.isfinite(value) or not (
        0 <= value <= P.TIME_LIMIT_SECONDS
    ):
        raise AnalysisError("covered task has invalid total time")
    return Fraction(str(value))


def _bootstrap(
    family_values: dict[str, Fraction], *, replicates: int, seed: int,
) -> dict:
    if type(replicates) is not int or replicates < 100:
        raise AnalysisError("bootstrap replicate count is invalid")
    families = sorted(family_values)
    if not families:
        return {"families": 0, "replicates": replicates, "lower_95": None,
                "upper_95": None}
    rng = random.Random(seed)
    samples = []
    for _ in range(replicates):
        samples.append(_mean(
            family_values[families[rng.randrange(len(families))]]
            for _ in families
        ))
    samples.sort()
    lower_index = math.ceil(0.025 * replicates) - 1
    upper_index = math.ceil(0.975 * replicates) - 1
    return {
        "families": len(families), "replicates": replicates, "seed": seed,
        "lower_95": _fraction(samples[lower_index]),
        "upper_95": _fraction(samples[upper_index]),
    }


def contrast(
    matrix: dict, tasks: list[tuple[str, str]], intervention: str,
    reference: str, *, replicates: int, seed: int,
) -> dict:
    by_family = defaultdict(list)
    intervention_coverage = 0
    reference_coverage = 0
    task_values = {}
    solve_pairs = Counter()
    common_solved_by_family = defaultdict(list)
    common_solved_task_values = {}
    for task in sorted(tasks):
        left = matrix[(intervention, task)]
        right = matrix[(reference, task)]
        intervention_coverage += left["coverage"]
        reference_coverage += right["coverage"]
        left_par2 = _par2(left)
        right_par2 = _par2(right)
        value = (right_par2 - left_par2) / P.PAR2_SECONDS
        task_values[task] = value
        by_family[left["family"]].append(value)
        if left["coverage"] and right["coverage"]:
            category = "both_solved"
            common_value = (
                right_par2 - left_par2
            ) / P.TIME_LIMIT_SECONDS
            common_solved_task_values[task] = common_value
            common_solved_by_family[left["family"]].append(common_value)
        elif left["coverage"]:
            category = "intervention_only_solved"
        elif right["coverage"]:
            category = "reference_only_solved"
        else:
            category = "neither_solved"
        solve_pairs[category] += 1
    family_values = {
        family: _mean(values) for family, values in sorted(by_family.items())
    }
    macro = _mean(family_values.values())
    lodo = {
        family: _mean(
            value for other, value in family_values.items() if other != family
        )
        for family in family_values
    }
    bootstrap = _bootstrap(family_values, replicates=replicates, seed=seed)
    common_solved_family_values = {
        family: _mean(values)
        for family, values in sorted(common_solved_by_family.items())
    }
    lower_record = bootstrap["lower_95"]
    lower = None if lower_record is None else Fraction(
        lower_record["numerator"], lower_record["denominator"]
    )
    minimum = Fraction(
        P.MIN_NORMALIZED_PAR2_IMPROVEMENT_NUMERATOR,
        P.MIN_NORMALIZED_PAR2_IMPROVEMENT_DENOMINATOR,
    )
    clauses = {
        "coverage_nonlower": intervention_coverage >= reference_coverage,
        "equal_family_normalized_par2_at_least_0_02": (
            macro is not None and macro >= minimum
        ),
        "bootstrap_lower_95_positive": lower is not None and lower > 0,
        "every_lodo_positive": bool(lodo) and all(
            value is not None and value > 0 for value in lodo.values()
        ),
    }
    return {
        "intervention": intervention,
        "reference": reference,
        "tasks": len(tasks),
        "families": len(family_values),
        "coverage": {
            "intervention": intervention_coverage,
            "reference": reference_coverage,
            "difference": intervention_coverage - reference_coverage,
        },
        "task_normalized_improvements": {
            "{}:{}".format(*task): _fraction(value)
            for task, value in sorted(task_values.items())
        },
        "family_normalized_improvements": {
            family: _fraction(value) for family, value in family_values.items()
        },
        "equal_family_normalized_par2_improvement": _fraction(macro),
        "bootstrap": bootstrap,
        "lodo": {family: _fraction(value) for family, value in lodo.items()},
        "outcome_decomposition": {
            "gating": False,
            "solve_pair_counts": {
                category: solve_pairs[category]
                for category in (
                    "both_solved", "intervention_only_solved",
                    "reference_only_solved", "neither_solved",
                )
            },
            "common_solved": {
                "definition": (
                    "(reference total time - intervention total time) / "
                    "planner time limit; positive favors intervention"
                ),
                "normalization_seconds": P.TIME_LIMIT_SECONDS,
                "tasks": len(common_solved_task_values),
                "families": len(common_solved_family_values),
                "task_normalized_time_improvements": {
                    "{}:{}".format(*task): _fraction(value)
                    for task, value in sorted(
                        common_solved_task_values.items()
                    )
                },
                "family_normalized_time_improvements": {
                    family: _fraction(value)
                    for family, value in common_solved_family_values.items()
                },
                "equal_family_normalized_time_improvement": _fraction(
                    _mean(common_solved_family_values.values())
                ),
            },
        },
        "clauses": clauses,
        "pass": all(clauses.values()),
    }


def _ratio(numerator: int, denominator: int):
    if denominator == 0:
        return None
    return Fraction(numerator, denominator)


def _descriptive_summary(
    rows: list[tuple[str, Fraction]], *, include_sum: bool = True,
) -> dict:
    if not rows:
        summary = {
            "tasks": 0, "families": 0, "task_mean": None,
            "equal_family_mean": None, "median_nearest_rank": None,
            "minimum": None, "maximum": None,
        }
        if include_sum:
            summary["sum"] = None
        return summary
    by_family = defaultdict(list)
    values = []
    for family, value in rows:
        if not isinstance(family, str) or not isinstance(value, Fraction):
            raise AnalysisError("mechanism summary input is malformed")
        by_family[family].append(value)
        values.append(value)
    ordered = sorted(values)
    family_values = {
        family: _mean(items) for family, items in sorted(by_family.items())
    }
    summary = {
        "tasks": len(values),
        "families": len(family_values),
        "task_mean": _fraction(_mean(values)),
        "equal_family_mean": _fraction(_mean(family_values.values())),
        "median_nearest_rank": _fraction(ordered[math.ceil(len(ordered) / 2) - 1]),
        "minimum": _fraction(ordered[0]),
        "maximum": _fraction(ordered[-1]),
    }
    if include_sum:
        summary["sum"] = _fraction(sum(values, Fraction()))
    return summary


def _identity_key(identity: dict) -> tuple:
    return (
        identity["pattern_index"], tuple(identity["sources"]),
        tuple(identity["pattern"]), identity["value_cap"],
    )


def _pattern_key(identity: dict) -> tuple:
    return _identity_key(identity)[:-1]


def _change_class(left: dict, right: dict) -> str:
    if _identity_key(left) == _identity_key(right):
        return "same_candidate"
    if _pattern_key(left) == _pattern_key(right):
        return "same_pattern_different_cap"
    return "different_pattern"


def _cap_direction(left: dict, right: dict) -> str | None:
    if _pattern_key(left) != _pattern_key(right):
        return None
    ranks = {value: rank for rank, value in enumerate(P.VALUE_CAP_GRID)}
    left_rank = ranks[left["value_cap"]]
    right_rank = ranks[right["value_cap"]]
    return "lower" if left_rank < right_rank else (
        "higher" if left_rank > right_rank else "equal"
    )


def _candidate(record: dict, identity: dict) -> dict:
    matches = [
        event for event in record["dual_selector_structural_trace"]
        if event.get("event") == "candidate"
        and Trace._candidate_identity(event) == identity
    ]
    if len(matches) != 1:
        raise AnalysisError("certified identity does not name one candidate")
    return matches[0]


def _score_relation(left: dict, right: dict) -> tuple[str, str]:
    left_better = Trace._better(left, right)
    right_better = Trace._better(right, left)
    if left_better and right_better:
        raise AnalysisError("frozen score comparator is inconsistent")
    relation = "higher" if left_better else "lower" if right_better else "tied"
    if left["initial_dead_end"] != right["initial_dead_end"]:
        criterion = "initial_dead_end"
    elif not left["initial_dead_end"] and left["initial_h"] != right["initial_h"]:
        criterion = "initial_h"
    elif Trace._compare_ratio(
        left["finite_sum"], left["finite_count"],
        right["finite_sum"], right["finite_count"], zero_infinity=True,
    ):
        criterion = "mean_finite"
    elif Trace._compare_ratio(
        left["dead_count"], left["abstract_states"],
        right["dead_count"], right["abstract_states"], zero_infinity=False,
    ):
        criterion = "dead_fraction"
    elif left["cofactor_width"] != right["cofactor_width"]:
        criterion = "cofactor_width"
    elif left["abstract_states"] != right["abstract_states"]:
        criterion = "abstract_states"
    elif left["pattern"] != right["pattern"]:
        criterion = "pattern_tiebreak"
    else:
        criterion = "tied"
    if (relation == "tied") != (criterion == "tied"):
        raise AnalysisError("frozen score decomposition is inconsistent")
    return relation, criterion


def _identity_summary(identities: list[dict]) -> dict:
    cap_counts = Counter()
    pattern_sizes = Counter()
    source_sets = Counter()
    source_membership = Counter()
    for identity in identities:
        cap = identity["value_cap"]
        cap_counts["exact" if cap is None else str(cap)] += 1
        pattern_sizes[str(len(identity["pattern"]))] += 1
        source_sets["+".join(identity["sources"])] += 1
        source_membership.update(identity["sources"])
    return {
        "tasks": len(identities),
        "cap_histogram": dict(sorted(cap_counts.items())),
        "pattern_cardinality_histogram": dict(sorted(
            pattern_sizes.items(), key=lambda item: int(item[0])
        )),
        "source_set_histogram": dict(sorted(source_sets.items())),
        "source_membership_counts": dict(sorted(source_membership.items())),
    }


def _count_fraction(count: int, denominator: int):
    return _fraction(Fraction(count, denominator)) if denominator else None


CHANGE_CLASSES = (
    "same_candidate", "same_pattern_different_cap", "different_pattern",
)
CAP_DIRECTIONS = ("lower", "higher")
SCORE_RELATIONS = ("higher", "tied", "lower")
SCORE_CRITERIA = (
    "initial_dead_end", "initial_h", "mean_finite", "dead_fraction",
    "cofactor_width", "abstract_states", "pattern_tiebreak", "tied",
)
BUDGET_MODES = ("incidence", "mj")
CROSS_GEOMETRY_OUTCOMES = (
    "incidence_mj_feasible", "incidence_mj_infeasible",
    "mj_incidence_feasible", "mj_incidence_infeasible",
    "incidence_mj_retained", "incidence_mj_not_retained",
    "mj_incidence_retained", "mj_incidence_not_retained",
)
WORK_FIELDS = (
    "candidate_count", "probe_state_profile_count",
    "probe_state_profile_cut_entries",
    "terminal_incidence_layer_measurements",
    "joint_profile_layer_measurements", "joint_profile_cut_entries",
    "joint_summed_cut_entries",
)


def _dense_counts(counter: Counter, categories: tuple[str, ...]) -> dict:
    unexpected = set(counter) - set(categories)
    if unexpected:
        raise AnalysisError("mechanism counter contains an unknown category")
    return {category: counter[category] for category in categories}


def _mechanism_diagnostics(
    matrix: dict, tasks: list[tuple[str, str]], task_families: dict,
) -> dict:
    complete_rows = []
    short_rows = []
    uptake = Counter()
    uptake_families = defaultdict(set)
    taxonomies = {
        name: Counter() for name in ("incidence_vs_mj", "incidence_vs_reference",
                                     "mj_vs_reference")
    }
    cap_directions = {name: Counter() for name in taxonomies}
    score_relations = {name: Counter() for name in taxonomies}
    score_criteria = {name: Counter() for name in taxonomies}
    score_differing = Counter()
    score_differing_criteria = Counter()
    identities = {"incidence": [], "mj": [], "reference": []}
    budget_values = {
        "incidence_slack": [], "incidence_utilization": [],
        "mj_slack": [], "mj_utilization": [],
    }
    zero_budgets = Counter()
    binding = Counter()
    cross_feasibility = Counter()
    work_rows = {field: [] for field in WORK_FIELDS}

    for task in tasks:
        family = task_families[task]
        record = matrix[(P.INCIDENCE_MODE, task)]
        status = record["dual_selector_trace_status"]
        if status == "short_probe":
            short_rows.append({
                "task": list(task), "family": family,
                "status": status,
                "completed_layers": record[
                    "dual_selector_probe_completed_layers"
                ],
                "probe_overhead_by_mode": {
                    mode: {
                        field: matrix[(mode, task)][
                            "dual_selector_probe_" + field
                        ]
                        for field in (
                            "cpu_seconds", "wall_seconds",
                            "peak_memory_after_kb", "peak_memory_delta_kb",
                        )
                    }
                    for mode in P.MODES
                },
            })
            continue
        if status != "complete":
            raise AnalysisError("audited trace status is unrecognized")
        reference = record["dual_selector_reference_identity"]
        incidence = record["dual_selector_incidence_winner_identity"]
        mj = record["dual_selector_masked_joint_winner_identity"]
        identities["reference"].append(reference)
        identities["incidence"].append(incidence)
        identities["mj"].append(mj)
        candidates = {
            "reference": _candidate(record, reference),
            "incidence": _candidate(record, incidence),
            "mj": _candidate(record, mj),
        }
        flags = {
            "incidence_differs_from_mj": _identity_key(incidence) != _identity_key(mj),
            "incidence_differs_from_reference": (
                _identity_key(incidence) != _identity_key(reference)
            ),
            "mj_differs_from_reference": _identity_key(mj) != _identity_key(reference),
        }
        flags["both_differ_from_reference"] = (
            flags["incidence_differs_from_reference"]
            and flags["mj_differs_from_reference"]
        )
        flags["all_same"] = not any(flags.values())
        for name, value in flags.items():
            if value:
                uptake[name] += 1
                uptake_families[name].add(family)

        pair_values = {
            "incidence_vs_mj": (incidence, mj, candidates["incidence"],
                                candidates["mj"]),
            "incidence_vs_reference": (
                incidence, reference, candidates["incidence"],
                candidates["reference"],
            ),
            "mj_vs_reference": (
                mj, reference, candidates["mj"], candidates["reference"],
            ),
        }
        task_taxonomy = {}
        task_scores = {}
        for name, (left, right, left_candidate, right_candidate) in pair_values.items():
            change = _change_class(left, right)
            direction = (
                _cap_direction(left, right)
                if change == "same_pattern_different_cap" else None
            )
            relation, criterion = _score_relation(left_candidate, right_candidate)
            taxonomies[name][change] += 1
            if direction is not None:
                cap_directions[name][direction] += 1
            score_relations[name][relation] += 1
            score_criteria[name][criterion] += 1
            task_taxonomy[name] = change
            task_scores[name] = {
                "relation": relation, "decisive_criterion": criterion,
            }
        if flags["incidence_differs_from_mj"]:
            differing_score = task_scores["incidence_vs_mj"]
            score_differing[differing_score["relation"]] += 1
            score_differing_criteria[
                differing_score["decisive_criterion"]
            ] += 1

        incidence_budget = reference["terminal_incidence"]
        mj_budget = reference["masked_joint"]
        incidence_slack = incidence_budget - incidence["terminal_incidence"]
        mj_slack = mj_budget - mj["masked_joint"]
        if incidence_slack < 0 or mj_slack < 0:
            raise AnalysisError("certified winner exceeds its own budget")
        incidence_utilization = _ratio(
            incidence["terminal_incidence"], incidence_budget
        )
        mj_utilization = _ratio(mj["masked_joint"], mj_budget)
        budget_values["incidence_slack"].append((family, Fraction(incidence_slack)))
        budget_values["mj_slack"].append((family, Fraction(mj_slack)))
        if incidence_utilization is None:
            zero_budgets["incidence"] += 1
        else:
            budget_values["incidence_utilization"].append(
                (family, incidence_utilization)
            )
        if mj_utilization is None:
            zero_budgets["mj"] += 1
        else:
            budget_values["mj_utilization"].append((family, mj_utilization))
        binding["incidence"] += incidence_slack == 0
        binding["mj"] += mj_slack == 0
        i_cross = incidence["masked_joint"] <= mj_budget
        m_cross = mj["terminal_incidence"] <= incidence_budget
        i_cross_retained = candidates["incidence"][
            "masked_joint_retained_for_pattern"
        ]
        m_cross_retained = candidates["mj"][
            "incidence_retained_for_pattern"
        ]
        if candidates["incidence"]["masked_joint_feasible"] != i_cross or (
            candidates["mj"]["incidence_feasible"] != m_cross
        ):
            raise AnalysisError("cross-feasibility identity changed")
        cross_feasibility[
            "incidence_mj_feasible" if i_cross else "incidence_mj_infeasible"
        ] += 1
        cross_feasibility[
            "mj_incidence_feasible" if m_cross else "mj_incidence_infeasible"
        ] += 1
        cross_feasibility[
            "incidence_mj_retained" if i_cross_retained
            else "incidence_mj_not_retained"
        ] += 1
        cross_feasibility[
            "mj_incidence_retained" if m_cross_retained
            else "mj_incidence_not_retained"
        ] += 1
        work = record["dual_selector_work_signature"]
        if set(work) != set(WORK_FIELDS):
            raise AnalysisError("certified work signature changed")
        for field in WORK_FIELDS:
            work_rows[field].append((family, Fraction(work[field])))
        complete_rows.append({
            "task": list(task), "family": family, "status": status,
            "reference": reference, "incidence_winner": incidence,
            "mj_winner": mj, "uptake": flags, "change_taxonomy": task_taxonomy,
            "score_relations": task_scores,
            "budgets": {"incidence": incidence_budget, "mj": mj_budget},
            "slack": {"incidence": incidence_slack, "mj": mj_slack},
            "own_utilization": {
                "incidence": _fraction(incidence_utilization),
                "mj": _fraction(mj_utilization),
            },
            "cross_feasible": {
                "incidence_under_mj_budget": i_cross,
                "mj_under_incidence_budget": m_cross,
            },
            "cross_retained_for_pattern": {
                "incidence_by_mj": i_cross_retained,
                "mj_by_incidence": m_cross_retained,
            },
        })

    complete_count = len(complete_rows)
    all_count = len(tasks)
    uptake_summary = {
        name: {
            "tasks": count,
            "families_with_at_least_one_task": len(uptake_families[name]),
            "fraction_of_complete_tasks": _count_fraction(count, complete_count),
        }
        for name, count in sorted(uptake.items())
    }
    for name in (
        "incidence_differs_from_mj", "incidence_differs_from_reference",
        "mj_differs_from_reference", "both_differ_from_reference", "all_same",
    ):
        uptake_summary.setdefault(name, {
            "tasks": 0, "families_with_at_least_one_task": 0,
            "fraction_of_complete_tasks": _count_fraction(0, complete_count),
        })

    overhead = {}
    for mode in P.MODES:
        probe = {field: [] for field in (
            "cpu_seconds", "wall_seconds", "peak_memory_after_kb",
            "peak_memory_delta_kb",
        )}
        selection = {field: [] for field in (
            "cpu_seconds", "wall_seconds", "peak_memory_after_kb",
            "peak_memory_delta_kb",
        )}
        total = {field: [] for field in ("cpu_seconds", "wall_seconds",
                                         "peak_memory_after_kb")}
        short_probe = {field: [] for field in probe}
        for task in tasks:
            row = matrix[(mode, task)]
            family = task_families[task]
            for field in probe:
                value = Fraction(str(row["dual_selector_probe_" + field]))
                probe[field].append((family, value))
                if row["dual_selector_trace_status"] == "short_probe":
                    short_probe[field].append((family, value))
            if row["dual_selector_trace_status"] != "complete":
                continue
            for field in selection:
                selection[field].append((
                    family,
                    Fraction(str(row["dual_selector_selection_" + field])),
                ))
            for field in ("cpu_seconds", "wall_seconds"):
                total[field].append((
                    family,
                    Fraction(str(row["dual_selector_probe_" + field]))
                    + Fraction(str(row["dual_selector_selection_" + field])),
                ))
            total["peak_memory_after_kb"].append((
                family,
                Fraction(max(
                    row["dual_selector_probe_peak_memory_after_kb"],
                    row["dual_selector_selection_peak_memory_after_kb"],
                )),
            ))
        overhead[mode] = {
            "probe": {
                field: _descriptive_summary(
                    values, include_sum="memory" not in field
                )
                for field, values in probe.items()
            },
            "selection_complete_tasks": {
                field: _descriptive_summary(
                    values, include_sum="memory" not in field
                )
                for field, values in selection.items()
            },
            "total_complete_tasks": {
                field: _descriptive_summary(
                    values, include_sum="memory" not in field
                )
                for field, values in total.items()
            },
            "short_probe_only": {
                field: _descriptive_summary(
                    values, include_sum="memory" not in field
                )
                for field, values in short_probe.items()
            },
        }

    paired_overhead = {}
    for reference_mode in (P.MJ_MODE, P.MATCHED_MODE):
        mode_rows = {field: [] for field in ("cpu_seconds", "wall_seconds")}
        for task in tasks:
            left = matrix[(P.INCIDENCE_MODE, task)]
            right = matrix[(reference_mode, task)]
            if left["dual_selector_trace_status"] != "complete":
                continue
            family = task_families[task]
            for field in mode_rows:
                left_total = Fraction(str(left["dual_selector_probe_" + field])) + (
                    Fraction(str(left["dual_selector_selection_" + field]))
                )
                right_total = Fraction(str(right["dual_selector_probe_" + field])) + (
                    Fraction(str(right["dual_selector_selection_" + field]))
                )
                mode_rows[field].append((family, left_total - right_total))
        paired_overhead["incidence_minus_" + reference_mode] = {
            field: _descriptive_summary(values)
            for field, values in mode_rows.items()
        }

    return {
        "gating": False,
        "definitions": {
            "unit": "one certified task triad",
            "frozen_selection_score_relation": (
                "higher/tied/lower under the complete parser comparator, with "
                "the first decisive registered criterion reported separately"
            ),
            "own_budget_utilization": (
                "winner metric divided by same-unit reference budget; zero "
                "budget is null"
            ),
            "short_probe_policy": (
                "support and probe overhead only; no imputed winner, budget, "
                "or selection overhead"
            ),
            "mediation_boundary": (
                "the trace contains no exact partition effort E or "
                "final-search bucket trajectory"
            ),
            "paired_recorded_probe_selection_time": (
                "incidence arm minus comparator arm for the sum of the two "
                "recorded phase timers; excludes uninstrumented gaps and "
                "trace writes"
            ),
        },
        "support": {
            "all_tasks": all_count,
            "complete_tasks": complete_count,
            "short_probe_tasks": len(short_rows),
            "complete_families": len({row["family"] for row in complete_rows}),
            "short_probe_families": len({row["family"] for row in short_rows}),
        },
        "treatment_uptake": uptake_summary,
        "change_taxonomy": {
            name: {
                "classes": _dense_counts(taxonomies[name], CHANGE_CLASSES),
                "cap_direction_within_same_pattern": _dense_counts(
                    cap_directions[name], CAP_DIRECTIONS
                ),
            }
            for name in taxonomies
        },
        "selected_candidate_distributions": {
            name: _identity_summary(values) for name, values in identities.items()
        },
        "budget_geometry": {
            "incidence_slack": _descriptive_summary(
                budget_values["incidence_slack"]
            ),
            "incidence_own_utilization": _descriptive_summary(
                budget_values["incidence_utilization"]
            ),
            "mj_slack": _descriptive_summary(budget_values["mj_slack"]),
            "mj_own_utilization": _descriptive_summary(
                budget_values["mj_utilization"]
            ),
            "zero_budget_tasks": _dense_counts(zero_budgets, BUDGET_MODES),
            "binding_tasks": _dense_counts(binding, BUDGET_MODES),
            "cross_feasibility_counts": _dense_counts(
                cross_feasibility, CROSS_GEOMETRY_OUTCOMES
            ),
        },
        "frozen_selection_score_relation": {
            "all_complete_tasks": {
                name: {
                    "relation": _dense_counts(
                        score_relations[name], SCORE_RELATIONS
                    ),
                    "decisive_criterion": _dense_counts(
                        score_criteria[name], SCORE_CRITERIA
                    ),
                }
                for name in score_relations
            },
            "differing_incidence_mj_winners": {
                "relation": _dense_counts(score_differing, SCORE_RELATIONS),
                "decisive_criterion": _dense_counts(
                    score_differing_criteria, SCORE_CRITERIA
                ),
            },
        },
        "candidate_work": {
            field: _descriptive_summary(work_rows[field])
            for field in WORK_FIELDS
        },
        "overhead_by_mode": overhead,
        "paired_recorded_probe_selection_time": paired_overhead,
        "complete_task_rows": complete_rows,
        "short_probe_rows": short_rows,
    }


def analyze(
    records: list[dict], freeze: dict, freeze_sha256: str,
    standalone: dict, *, bootstrap_replicates: int | None = None,
) -> dict:
    audit = Audit.audit_records(records, freeze, freeze_sha256, standalone)
    matrix = {}
    tasks = set()
    task_families = {
        (row["directory"], row["problem"]): row["family"]
        for row in P.guided_b_tasks(freeze["base_confirmation_b"])
    }
    for record in records:
        task = (record["domain"], record["problem"])
        key = (record["algorithm"], task)
        if key in matrix:
            raise AnalysisError("analysis matrix contains a duplicate cell")
        normalized = dict(record)
        normalized["family"] = task_families[task]
        matrix[key] = normalized
        tasks.add(task)
    tasks = sorted(tasks)
    replicates = (
        P.BOOTSTRAP_REPLICATES
        if bootstrap_replicates is None else bootstrap_replicates
    )
    primary = contrast(
        matrix, tasks, P.INCIDENCE_MODE, P.MJ_MODE,
        replicates=replicates, seed=P.BOOTSTRAP_SEED,
    )
    complete_tasks = [
        task for task in tasks
        if matrix[(P.INCIDENCE_MODE, task)][
            "dual_selector_trace_status"
        ] == "complete"
    ]
    different = [
        task for task in complete_tasks
        if matrix[(P.INCIDENCE_MODE, task)][
            "dual_selector_incidence_winner_identity"
        ] != matrix[(P.INCIDENCE_MODE, task)][
            "dual_selector_masked_joint_winner_identity"
        ]
    ]
    differing_families = {
        task_families[task] for task in different
    }
    subset = contrast(
        matrix, different, P.INCIDENCE_MODE, P.MJ_MODE,
        replicates=replicates, seed=P.BOOTSTRAP_SEED + 1,
    )
    subset_support = {
        "tasks_at_least_50": len(different) >= P.MIN_DIFFERING_WINNER_TASKS,
        "families_at_least_10": (
            len(differing_families) >= P.MIN_DIFFERING_WINNER_FAMILIES
        ),
    }
    subset["support_clauses"] = subset_support
    subset["pass"] = subset["pass"] and all(subset_support.values())
    secondary = contrast(
        matrix, tasks, P.INCIDENCE_MODE, P.MATCHED_MODE,
        replicates=replicates, seed=P.BOOTSTRAP_SEED + 2,
    )
    secondary["affects_primary_gate"] = False
    mechanism = _mechanism_diagnostics(matrix, tasks, task_families)
    passed = audit["certified"] and primary["pass"] and subset["pass"]
    probe_support = {
        "complete_tasks": audit["status_counts"]["complete"],
        "short_probe_tasks": audit["status_counts"]["short_probe"],
        "complete_families": audit["status_family_counts"]["complete"],
        "short_probe_families": audit["status_family_counts"]["short_probe"],
    }
    return {
        "schema": ANALYSIS_SCHEMA,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "audit": audit,
        "probe_support": probe_support,
        "primary_i_vs_mj": primary,
        "differing_winner_subset_i_vs_mj": subset,
        "secondary_i_vs_matched": secondary,
        "mechanism_diagnostics": mechanism,
        "pass": passed,
    }


def _exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise AnalysisError("{} already exists".format(label)) from err
    return hashlib.sha256(raw).hexdigest()


def _load_inputs() -> tuple[
    list[dict], dict, str, dict, str, str, str, str, dict,
]:
    import pdb_terminal_metric_choice_execution as Execution

    freeze_path = P.FREEZE_PATH
    freeze = P.load_freeze(freeze_path)
    standalone = P.load_bound_standalone(freeze)
    freeze_sha = P.sha256_file(
        freeze_path, expected_path=P.FREEZE_PATH, label="campaign freeze"
    )
    try:
        execution_sha, execution = Execution.load_execution_receipt(
            verify_live=False
        )
    except Execution.ExecutionError as err:
        raise AnalysisError("cannot load sealed campaign execution") from err
    try:
        payload = Runner.load_fetched_properties(freeze_sha, execution_sha)
    except Runner.RunnerError as err:
        raise AnalysisError("cannot load exact campaign properties") from err
    records = Audit.records_from_payload(payload)
    properties_sha = P.sha256_file(
        Runner.EVAL_PROPERTIES, expected_path=Runner.EVAL_PROPERTIES,
        label="fetched campaign properties",
    )
    fetch_sha = P.sha256_file(
        Runner.POST_FETCH_RECEIPT, expected_path=Runner.POST_FETCH_RECEIPT,
        label="post-fetch receipt",
    )
    execution_path = Execution.EXECUTION_RECEIPT.relative_to(P.REPO).as_posix()
    return (
        records, freeze, freeze_sha, standalone, properties_sha, fetch_sha,
        execution_path, execution_sha, execution["hardware"],
    )


ANALYSIS_PROVENANCE_FIELDS = (
    "campaign_freeze_sha256", "campaign_freeze_repository_revision",
    "base_b_freeze_sha256", "base_b_freeze_repository_revision",
    "base_b_experiment_source_manifest_sha256",
    "planner_revision", "planner_manifest_sha256",
    "standalone_k32_evidence_sha256", "standalone_k32_records_sha256",
    "standalone_b_parse_receipt_sha256",
    "standalone_b_fetch_receipt_sha256", "standalone_b_properties_sha256",
) + Runner.V12_PROVENANCE_PROPERTY_FIELDS


def _analysis_provenance(freeze: dict, freeze_sha256: str) -> dict:
    properties = Runner.build_manifest_properties(freeze, freeze_sha256)
    return {field: properties[field] for field in ANALYSIS_PROVENANCE_FIELDS}


def run_twice(
    output: Path = DEFAULT_OUTPUT,
    repeat_output: Path = DEFAULT_REPEAT_OUTPUT,
    receipt_path: Path = DEFAULT_RECEIPT,
    receipt_pin: Path = DEFAULT_RECEIPT_PIN,
    *, bootstrap_replicates: int | None = None,
) -> dict:
    paths = tuple(map(Path, (output, repeat_output, receipt_path, receipt_pin)))
    if len({str(path.absolute()) for path in paths}) != len(paths) or any(
        path.exists() or path.is_symlink() for path in paths
    ):
        raise AnalysisError("analysis output namespace is not fresh")
    first_inputs = _load_inputs()
    (
        records, freeze, freeze_sha, standalone, properties_sha, fetch_sha,
        execution_path, execution_sha, hardware,
    ) = first_inputs
    first = analyze(
        records, freeze, freeze_sha, standalone,
        bootstrap_replicates=bootstrap_replicates,
    )
    first["input"] = {
        "freeze_sha256": freeze_sha,
        "frozen_provenance": _analysis_provenance(freeze, freeze_sha),
        "fetched_properties_sha256": properties_sha,
        "post_fetch_receipt_sha256": fetch_sha,
        "execution_receipt_path": execution_path,
        "execution_receipt_sha256": execution_sha,
        "hardware": hardware,
    }
    first_raw = P.canonical_json_line(first)

    second_inputs = _load_inputs()
    (
        records_two, freeze_two, freeze_sha_two, standalone_two,
        properties_sha_two, fetch_sha_two, execution_path_two,
        execution_sha_two, hardware_two,
    ) = second_inputs
    if (
        P.canonical_json(freeze_two) != P.canonical_json(freeze)
        or P.canonical_json(standalone_two) != P.canonical_json(standalone)
        or (
            freeze_sha_two, properties_sha_two, fetch_sha_two,
            execution_path_two, execution_sha_two,
        ) != (
            freeze_sha, properties_sha, fetch_sha, execution_path,
            execution_sha,
        )
        or hardware_two != hardware
    ):
        raise AnalysisError("analysis input changed between executions")
    second = analyze(
        records_two, freeze_two, freeze_sha_two, standalone_two,
        bootstrap_replicates=bootstrap_replicates,
    )
    second["input"] = dict(first["input"])
    second_raw = P.canonical_json_line(second)
    if first_raw != second_raw:
        raise AnalysisError("two analyses are not byte-identical")

    first_sha = _exclusive_bytes(output, first_raw, "primary analysis output")
    second_sha = _exclusive_bytes(
        repeat_output, second_raw, "repeat analysis output"
    )
    try:
        first_readback = CampaignIO.read_regular_exact(
            output, expected=output, label="primary analysis output"
        )
        second_readback = CampaignIO.read_regular_exact(
            repeat_output, expected=repeat_output,
            label="repeat analysis output",
        )
    except CampaignIO.CampaignIOError as err:
        raise AnalysisError("cannot verify published analyses") from err
    if (
        first_sha != second_sha
        or first_readback.sha256 != first_sha
        or second_readback.sha256 != second_sha
        or first_readback.raw != second_readback.raw
    ):
        raise AnalysisError("published analyses differ")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "freeze_sha256": freeze_sha,
        "frozen_provenance": _analysis_provenance(freeze, freeze_sha),
        "fetched_properties_sha256": properties_sha,
        "post_fetch_receipt_sha256": fetch_sha,
        "execution_receipt_path": execution_path,
        "execution_receipt_sha256": execution_sha,
        "hardware": hardware,
        "bootstrap_replicates": (
            P.BOOTSTRAP_REPLICATES
            if bootstrap_replicates is None else bootstrap_replicates
        ),
        "bootstrap_seed": P.BOOTSTRAP_SEED,
        "first_output": str(Path(output).absolute()),
        "second_output": str(Path(repeat_output).absolute()),
        "first_output_sha256": first_sha,
        "second_output_sha256": second_sha,
        "outputs_byte_identical": True,
        "primary_gate_passed": first["pass"],
    }
    receipt_raw = P.canonical_json_line(receipt)
    receipt_sha = _exclusive_bytes(
        receipt_path, receipt_raw, "analysis execution receipt"
    )
    _exclusive_bytes(
        receipt_pin, (receipt_sha + "\n").encode("ascii"),
        "analysis execution receipt pin",
    )
    try:
        receipt_readback = CampaignIO.read_regular_exact(
            receipt_path, expected=receipt_path,
            label="analysis execution receipt",
        )
        pin_readback = CampaignIO.read_regular_exact(
            receipt_pin, expected=receipt_pin,
            label="analysis execution receipt pin",
        )
    except CampaignIO.CampaignIOError as err:
        raise AnalysisError("cannot verify published analysis receipt") from err
    if (
        receipt_readback.sha256 != receipt_sha
        or receipt_readback.raw != receipt_raw
        or pin_readback.raw != (receipt_sha + "\n").encode("ascii")
    ):
        raise AnalysisError("published analysis receipt changed")
    return {**receipt, "analysis_receipt_sha256": receipt_sha}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    args = parser.parse_args(argv)
    del args
    result = run_twice()
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
