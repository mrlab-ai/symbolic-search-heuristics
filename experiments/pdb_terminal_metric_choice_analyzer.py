#!/usr/bin/env python3
"""Pre-registered I-versus-mJ analysis for the dual-metric campaign."""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

import pdb_terminal_metric_choice_audit as Audit
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_runner as Runner


class AnalysisError(RuntimeError):
    pass


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
    if coverage == 0:
        return Fraction(P.PAR2_SECONDS)
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
    for task in sorted(tasks):
        left = matrix[(intervention, task)]
        right = matrix[(reference, task)]
        intervention_coverage += left["coverage"]
        reference_coverage += right["coverage"]
        value = (_par2(right) - _par2(left)) / P.PAR2_SECONDS
        task_values[task] = value
        by_family[left["family"]].append(value)
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
        "clauses": clauses,
        "pass": all(clauses.values()),
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
        for row in freeze["base_confirmation_b"]["cohort"]["tasks"]
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
    different = [
        task for task in tasks
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
    passed = audit["certified"] and primary["pass"] and subset["pass"]
    return {
        "schema": P.FREEZE_SCHEMA + "/analysis",
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "audit": audit,
        "primary_i_vs_mj": primary,
        "differing_winner_subset_i_vs_mj": subset,
        "secondary_i_vs_matched": secondary,
        "pass": passed,
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    args = parser.parse_args(argv)
    del args
    freeze_path = P.FREEZE_PATH
    freeze = P.load_authorized_freeze(freeze_path)
    standalone = P.load_bound_standalone(freeze)
    freeze_sha = P.sha256_file(freeze_path, expected_path=P.FREEZE_PATH)
    try:
        payload = Runner.load_fetched_properties(freeze_sha)
    except Runner.RunnerError as err:
        raise AnalysisError("cannot load exact campaign properties") from err
    records = Audit.records_from_payload(payload)
    result = analyze(records, freeze, freeze_sha, standalone)
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
