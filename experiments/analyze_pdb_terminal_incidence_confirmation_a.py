#!/usr/bin/env python3
"""Analyze Confirmation A twice and require byte-identical canonical results."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import stat
import tempfile
from collections import Counter
from fractions import Fraction
from pathlib import Path

import analyze_pdb_terminal_incidence_shadow as Original
import audit_pdb_terminal_incidence_confirmation_a as Audit
import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_a_protocol as P


class ConfirmationAnalysisError(RuntimeError):
    pass


SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-a-analysis/v2"
)
RECEIPT_SCHEMA = SCHEMA + "/double-execution"
ARTIFACT_DIR = Audit.ARTIFACT_DIR
DEFAULT_OUTPUT = ARTIFACT_DIR / "analysis-v2.json"
DEFAULT_REPEAT_OUTPUT = ARTIFACT_DIR / "analysis-v2-repeat.json"
DEFAULT_RECEIPT = ARTIFACT_DIR / "analysis-execution-receipt-v2.json"
DEFAULT_RECEIPT_PIN = ARTIFACT_DIR / "analysis-execution-receipt-v2.sha256"


def _configure_original() -> None:
    Original.P = P
    Original.SCHEMA = SCHEMA
    Original.REQUESTED_MODES = {
        "pdb_bdd_prefix_shadow": "bdd_prefix",
        "pdb_goal_prefix_shadow": "goal_prefix",
        "pdb_goal_fill_shadow": "goal_fill",
        "pdb_cegar_shadow": "cegar",
    }
    Original.LABEL_MODES = {
        label: ({mode, "cegar_fallback_goal_fill"} if mode == "cegar" else {mode})
        for label, mode in Original.REQUESTED_MODES.items()
    }
    Original.GOAL_FILL_LABEL = "pdb_goal_fill_shadow"


def _projected_attestation() -> bytes:
    _, materials = P._load_freeze(P.FREEZE_PATH)
    tasks = [{
        "domain": task["directory"],
        "problem": task["problem"],
        "domain_sha256": task["domain_sha256"],
        "problem_sha256": task["problem_sha256"],
        "domain_source_sha256": task["domain_sha256"],
        "problem_source_sha256": task["problem_sha256"],
    } for task in materials.tasks]
    return P.canonical_json_line({"tasks": tasks})


@contextlib.contextmanager
def _attestation_view():
    payload = _projected_attestation()
    original = P.COST_ATTESTATION_PATH
    descriptor, name = tempfile.mkstemp(
        prefix="confirmation-a-source-view-", suffix=".json"
    )
    path = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        P.COST_ATTESTATION_PATH = path
        yield
    finally:
        P.COST_ATTESTATION_PATH = original
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def _public_comparison(comparison: dict) -> dict:
    return {
        **comparison,
        "predictors": {
            key: {
                field: value for field, value in summary.items()
                if not field.startswith("_")
            }
            for key, summary in comparison["predictors"].items()
        },
    }


def _fraction(record, label: str) -> Fraction | None:
    if record is None:
        return None
    try:
        return Original._internal_fraction(record, label)
    except Original.TerminalIncidenceAnalysisError as err:
        raise ConfirmationAnalysisError(str(err)) from err


def _stratum_gate(comparison: dict) -> dict:
    bootstrap = Original._bootstrap_differences(comparison)
    support = comparison["support"]
    i_record = comparison["predictors"]["I"]["equal_family"]["macro"]
    i_macro = _fraction(i_record, "stratum I family macro")
    minimum = Fraction(
        P.MIN_NEW_STRATUM_CONCORDANCE_NUMERATOR,
        P.MIN_NEW_STRATUM_CONCORDANCE_DENOMINATOR,
    )
    minimum_advantage = Fraction(
        P.MIN_NEW_STRATUM_ADVANTAGE_NUMERATOR,
        P.MIN_NEW_STRATUM_ADVANTAGE_DENOMINATOR,
    )
    controls = {}
    for control in Original.CONTROLS:
        control_record = comparison["predictors"][control][
            "equal_family"
        ]["macro"]
        control_macro = _fraction(
            control_record, "stratum {} family macro".format(control)
        )
        advantage = (
            i_macro - control_macro
            if i_macro is not None and control_macro is not None else None
        )
        lower_record = bootstrap[control]["lower_95"]
        lower = _fraction(
            lower_record, "stratum {} bootstrap lower".format(control)
        )
        i_lodo = comparison["predictors"]["I"]["_family_lodo"]
        control_lodo = comparison["predictors"][control]["_family_lodo"]
        if set(i_lodo) != set(control_lodo):
            raise ConfirmationAnalysisError(
                "stratum comparison produced different family supports"
            )
        lodo_differences = {
            family: (
                None
                if i_lodo[family] is None or control_lodo[family] is None
                else i_lodo[family] - control_lodo[family]
            )
            for family in sorted(i_lodo)
        }
        lodo_pass = bool(lodo_differences) and all(
            value is not None and value > 0
            for value in lodo_differences.values()
        )
        advantage_pass = (
            advantage is not None and advantage >= minimum_advantage
        )
        bootstrap_pass = lower is not None and lower > 0
        controls[control] = {
            "advantage": Original._fraction_record(advantage),
            "minimum_advantage": Original._fraction_record(
                minimum_advantage
            ),
            "advantage_pass": advantage_pass,
            "bootstrap": bootstrap[control],
            "bootstrap_lower_strictly_positive": bootstrap_pass,
            "leave_one_family_out_differences": {
                family: Original._fraction_record(value)
                for family, value in lodo_differences.items()
            },
            "every_leave_one_family_out_positive": lodo_pass,
            "pass": advantage_pass and bootstrap_pass and lodo_pass,
        }
    support_pass = all((
        support.get("tasks_with_shared_pairs", 0)
        >= P.MIN_NEW_STRATUM_COMPARISON_TASKS,
        support.get("families_with_shared_pairs", 0)
        >= P.MIN_NEW_STRATUM_COMPARISON_FAMILIES,
        support.get("target_strict", 0)
        >= P.MIN_NEW_STRATUM_TARGET_STRICT_PAIRS,
    ))
    macro_pass = i_macro is not None and i_macro >= minimum
    orientation_pass = (
        comparison["target_orientations"].get("orders_identical") is True
        and comparison["target_orientations"].get("inverse_U_null")
        == "tied_within_task"
    )
    pass_value = (
        support_pass
        and macro_pass
        and orientation_pass
        and all(row["pass"] for row in controls.values())
    )
    return {
        "pass": pass_value,
        "support": {
            "comparison_tasks": support.get("tasks_with_shared_pairs", 0),
            "minimum_comparison_tasks": (
                P.MIN_NEW_STRATUM_COMPARISON_TASKS
            ),
            "comparison_families": support.get("families_with_shared_pairs", 0),
            "minimum_comparison_families": (
                P.MIN_NEW_STRATUM_COMPARISON_FAMILIES
            ),
            "target_strict_pairs": support.get("target_strict", 0),
            "minimum_target_strict_pairs": (
                P.MIN_NEW_STRATUM_TARGET_STRICT_PAIRS
            ),
            "pass": support_pass,
        },
        "primary_macro": {
            "value": i_record,
            "minimum": Original._fraction_record(minimum),
            "pass": macro_pass,
        },
        "controls": controls,
        "orientation": {
            "absolute_and_normalized_agree": comparison[
                "target_orientations"
            ].get("orders_identical") is True,
            "inverse_U_tied": comparison["target_orientations"].get(
                "inverse_U_null"
            ) == "tied_within_task",
            "pass": orientation_pass,
        },
        "bootstrap_protocol": Original.BOOTSTRAP_PROTOCOL,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
    }


def _stratum(
    grouped: dict, frontiers: dict, families: tuple[str, ...], *, gating: bool
) -> dict:
    family_set = set(families)
    selected_grouped = {
        task: observations for task, observations in grouped.items()
        if P.DIRECTORY_TO_FAMILY[task[0]] in family_set
    }
    selected_frontiers = {
        task: frontier for task, frontier in frontiers.items()
        if P.DIRECTORY_TO_FAMILY[task[0]] in family_set
    }
    comparison = Original.target_strict_tie_aware_comparison(selected_grouped)
    return {
        "gating": gating,
        "frozen_families": list(families),
        "eligible_tasks": len(selected_frontiers),
        "eligible_families": len({
            P.DIRECTORY_TO_FAMILY[task[0]] for task in selected_frontiers
        }),
        "comparison": _public_comparison(comparison),
        "gate": _stratum_gate(comparison),
    }


def _top_choice_regret(grouped: dict) -> dict:
    """Report bounded regret when each predictor chooses its minimum."""
    task_values = {key: {} for key in Original.PREDICTORS}
    tie_counts = Counter()
    rows = []
    exclusions = Counter()
    for task in sorted(grouped):
        observations = sorted(
            grouped[task].values(), key=lambda item: item["semantic_id"]
        )
        if len(observations) < 2:
            exclusions["fewer_than_two_semantic_observations"] += 1
            continue
        target_min = min(item["E"] for item in observations)
        target_max = max(item["E"] for item in observations)
        if target_min == target_max:
            exclusions["target_tied_tasks"] += 1
            continue
        predictor_rows = {}
        for key in Original.PREDICTORS:
            best_value = min(item[key] for item in observations)
            selected = [
                item for item in observations if item[key] == best_value
            ]
            if len(selected) > 1:
                tie_counts[key] += 1
            selected_target = Fraction(
                sum(item["E"] for item in selected), len(selected)
            )
            regret = Fraction(
                selected_target - target_min, target_max - target_min
            )
            task_values[key][task] = regret
            predictor_rows[key] = {
                "minimum_predictor_value": best_value,
                "selected_semantic_ids": [
                    item["semantic_id"] for item in selected
                ],
                "selected_target_mean": Original._fraction_record(
                    selected_target
                ),
                "normalized_regret": Original._fraction_record(regret),
            }
        rows.append({
            "domain": task[0],
            "family": P.DIRECTORY_TO_FAMILY[task[0]],
            "problem": task[1],
            "oracle_target_minimum": target_min,
            "target_maximum": target_max,
            "predictors": predictor_rows,
        })

    summaries = {}
    for key in Original.PREDICTORS:
        by_family = {}
        for task, value in task_values[key].items():
            by_family.setdefault(P.DIRECTORY_TO_FAMILY[task[0]], []).append(
                value
            )
        family_values = {
            name: Original._mean(values)
            for name, values in sorted(by_family.items())
        }
        task_count = len(task_values[key])
        summaries[key] = {
            "tasks": task_count,
            "families": len(family_values),
            "top_choice_tied_tasks": tie_counts[key],
            "top_choice_tie_rate": Original._fraction_record(
                Fraction(tie_counts[key], task_count) if task_count else None
            ),
            "task_macro_normalized_regret": Original._fraction_record(
                Original._mean(task_values[key].values())
            ),
            "equal_family_normalized_regret": Original._fraction_record(
                Original._mean(family_values.values())
            ),
            "family_normalized_regret": {
                name: Original._fraction_record(value)
                for name, value in family_values.items()
            },
        }
    return {
        "gating": False,
        "definition": (
            "within each target-nontied task, choose every predictor-minimal "
            "semantic heuristic; average E across a tied top set; report "
            "(selected_mean_E-min_E)/(max_E-min_E)"
        ),
        "lower_is_better": True,
        "tie_policy": "average-target-over-all-predictor-minimal-choices",
        "support": {
            **dict(exclusions),
            "eligible_tasks": len(rows),
            "eligible_families": len({row["family"] for row in rows}),
        },
        "predictors": summaries,
        "rows": rows,
    }


def analyze_records(records: list[dict]) -> dict:
    _configure_original()
    P.validate_protocol_without_sources()
    with _attestation_view():
        matrix, tasks, outcomes = Original.validate_matrix(
            records, P.COHORT_TASKS
        )
    primary = Original.primary_observations(matrix, tasks)
    comparison = Original.target_strict_tie_aware_comparison(
        primary["grouped"]
    )
    strict_comparison = Original.grand_shared_comparison(primary["grouped"])
    eligible_tasks = len(primary["frontiers"])
    eligible_families = len({
        P.DIRECTORY_TO_FAMILY[task[0]] for task in primary["frontiers"]
    })
    primary_gate = Original.primary_gates(
        comparison, eligible_tasks, eligible_families
    )
    new_stratum = _stratum(
        primary["grouped"], primary["frontiers"],
        P.ALL_PRIOR_UNREPRESENTED_FAMILIES, gating=True,
    )
    shadow_stratum = _stratum(
        primary["grouped"], primary["frontiers"],
        P.SHADOW_UNREPRESENTED_FAMILIES, gating=False,
    )
    complete_pass = primary_gate["pass"] and new_stratum["gate"]["pass"]
    support_pass = (
        primary_gate["support"]["pass"]
        and new_stratum["gate"]["support"]["pass"]
    )
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
        "comparison": _public_comparison(comparison),
        "gates": {
            "pass": complete_pass,
            "decision": "PASS" if complete_pass else "FAIL",
            "support_pass": support_pass,
            "support_failure_is_failure": True,
            "primary": primary_gate,
            "all_prior_unrepresented": new_stratum["gate"],
            "absolute_and_normalized_gate_decisions_identical": True,
        },
        "strata": {
            "all_prior_unrepresented": new_stratum,
            "shadow_unrepresented": shadow_stratum,
        },
        "sensitivity": {
            "gating": False,
            "all_predictor_strict": _public_comparison(strict_comparison),
            "top_choice_regret": _top_choice_regret(primary["grouped"]),
            "equal_directory_results": {
                key: summary["equal_directory"]
                for key, summary in _public_comparison(comparison)[
                    "predictors"
                ].items()
            },
            "shadow_unrepresented": shadow_stratum,
        },
        "secondary_diagnostics": Original.secondary_diagnostics(
            primary["observations"]
        ),
        "guided_study_authorized": complete_pass,
    }


def _load_sealed_input(path: Path) -> tuple[list[dict], str, str]:
    try:
        path = SafeIO.validate_lexical_path(
            Path(path), label="sealed Confirmation A properties",
            expected_path=Audit.EVAL_PROPERTIES,
        )
    except SafeIO.SafeReadError as err:
        raise ConfirmationAnalysisError("analysis input is not the sealed matrix") from err
    P.validate_protocol_without_sources()
    try:
        fetch_sha, fetch = Audit.load_fetch_receipt(verify_live=True)
    except Audit.ExecutionAuditError as err:
        raise ConfirmationAnalysisError(
            "fetched properties provenance is invalid"
        ) from err
    try:
        loaded = SafeIO.read_regular_file(
            path, label="sealed Confirmation A properties",
            expected_path=Audit.EVAL_PROPERTIES,
        )
        raw = loaded.raw
    except SafeIO.SafeReadError as err:
        raise ConfirmationAnalysisError("cannot read sealed properties") from err
    properties_sha = loaded.sha256
    if (
        properties_sha != fetch["properties_sha256"]
    ):
        raise ConfirmationAnalysisError("analysis input is not the sealed matrix")
    try:
        root = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as err:
        raise ConfirmationAnalysisError("cannot parse sealed properties") from err
    records = list(root.values()) if isinstance(root, dict) else root
    if not isinstance(records, list) or any(
        not isinstance(record, dict) for record in records
    ):
        raise ConfirmationAnalysisError(
            "sealed properties must contain a matrix of objects"
        )
    return records, properties_sha, fetch_sha


def _exclusive(path: Path, raw: bytes, label: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise ConfirmationAnalysisError("{} already exists".format(label)) from err
    return hashlib.sha256(raw).hexdigest()


def run_twice(
    properties: Path,
    output: Path,
    repeat_output: Path,
    receipt_path: Path,
    receipt_pin: Path,
) -> dict:
    paths = (output, repeat_output, receipt_path, receipt_pin)
    if len({path.resolve() for path in paths}) != len(paths) or any(
        path.exists() or path.is_symlink() for path in paths
    ):
        raise ConfirmationAnalysisError("analysis output namespace is not fresh")
    records_one, properties_sha, fetch_sha = _load_sealed_input(properties)
    result_one = analyze_records(records_one)
    result_one["input"] = {
        "path": str(properties.resolve()),
        "sha256": properties_sha,
        "fetch_receipt_sha256": fetch_sha,
    }
    raw_one = P.canonical_json_line(result_one)
    records_two, properties_sha_two, fetch_sha_two = _load_sealed_input(properties)
    if (properties_sha_two, fetch_sha_two) != (properties_sha, fetch_sha):
        raise ConfirmationAnalysisError("analysis input changed between executions")
    result_two = analyze_records(records_two)
    result_two["input"] = dict(result_one["input"])
    raw_two = P.canonical_json_line(result_two)
    if raw_one != raw_two:
        raise ConfirmationAnalysisError("two analyses are not byte-identical")
    first_sha = _exclusive(output, raw_one, "primary analysis output")
    second_sha = _exclusive(
        repeat_output, raw_two, "repeat analysis output"
    )
    try:
        first_readback = SafeIO.read_regular_file(
            output, label="primary analysis output"
        ).raw
        second_readback = SafeIO.read_regular_file(
            repeat_output, label="repeat analysis output"
        ).raw
    except SafeIO.SafeReadError as err:
        raise ConfirmationAnalysisError("cannot verify published analyses") from err
    if first_sha != second_sha or first_readback != second_readback:
        raise ConfirmationAnalysisError("published analyses differ")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "input_properties_sha256": properties_sha,
        "fetch_receipt_sha256": fetch_sha,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
        "first_output": str(output.resolve()),
        "second_output": str(repeat_output.resolve()),
        "first_output_sha256": first_sha,
        "second_output_sha256": second_sha,
        "outputs_byte_identical": True,
        "confirmation_a_complete_gate_passed": result_one["gates"]["pass"],
        "guided_study_authorized": result_one["guided_study_authorized"],
    }
    receipt_raw = P.canonical_json_line(receipt)
    receipt_sha = _exclusive(receipt_path, receipt_raw, "analysis receipt")
    _exclusive(
        receipt_pin,
        (receipt_sha + "\n").encode("ascii"),
        "analysis receipt pin",
    )
    return {**receipt, "analysis_receipt_sha256": receipt_sha}


def load_analysis_receipt(
    *,
    receipt_path: Path = DEFAULT_RECEIPT,
    receipt_pin: Path = DEFAULT_RECEIPT_PIN,
    output: Path = DEFAULT_OUTPUT,
    repeat_output: Path = DEFAULT_REPEAT_OUTPUT,
    verify_live: bool = True,
) -> tuple[str, dict, dict]:
    """Load the complete A gate for a dependent experiment, fail closed."""
    receipt_path = Path(receipt_path)
    receipt_pin = Path(receipt_pin)
    output = Path(output)
    repeat_output = Path(repeat_output)
    if verify_live:
        P.validate_protocol_without_sources()
    try:
        receipt_raw, receipt = P._load_canonical(
            receipt_path, "Confirmation A analysis receipt"
        )
        pin_raw = SafeIO.read_regular_file(
            receipt_pin, label="Confirmation A analysis receipt pin"
        ).raw
    except (P.ProtocolError, SafeIO.SafeReadError) as err:
        raise ConfirmationAnalysisError(
            "Confirmation A analysis receipt is not sealed"
        ) from err
    receipt_sha = hashlib.sha256(receipt_raw).hexdigest()
    if (
        pin_raw != (receipt_sha + "\n").encode("ascii")
    ):
        raise ConfirmationAnalysisError(
            "Confirmation A analysis receipt pin changed"
        )

    output_records = []
    for path, label in (
        (output, "primary Confirmation A analysis"),
        (repeat_output, "repeat Confirmation A analysis"),
    ):
        try:
            raw, value = P._load_canonical(path, label)
        except P.ProtocolError as err:
            raise ConfirmationAnalysisError(
                "{} is not canonical".format(label)
            ) from err
        output_records.append((raw, value, hashlib.sha256(raw).hexdigest()))
    first_raw, first, first_sha = output_records[0]
    second_raw, second, second_sha = output_records[1]

    expected_fields = {
        "schema", "input_properties_sha256", "fetch_receipt_sha256",
        "analysis_protocol", "bootstrap_replicates", "bootstrap_seed",
        "first_output", "second_output", "first_output_sha256",
        "second_output_sha256", "outputs_byte_identical",
        "confirmation_a_complete_gate_passed", "guided_study_authorized",
    }
    analysis_input = first.get("input")
    gates = first.get("gates")
    if any((
        set(receipt) != expected_fields,
        receipt.get("schema") != RECEIPT_SCHEMA,
        receipt.get("analysis_protocol") != P.ANALYSIS_PROTOCOL,
        receipt.get("bootstrap_replicates") != P.BOOTSTRAP_REPLICATES,
        receipt.get("bootstrap_seed") != P.BOOTSTRAP_SEED,
        receipt.get("first_output") != str(output.resolve()),
        receipt.get("second_output") != str(repeat_output.resolve()),
        receipt.get("first_output_sha256") != first_sha,
        receipt.get("second_output_sha256") != second_sha,
        receipt.get("outputs_byte_identical") is not True,
        receipt.get("confirmation_a_complete_gate_passed") is not True,
        receipt.get("guided_study_authorized") is not True,
        first_raw != second_raw,
        first != second,
        first_sha != second_sha,
        first.get("schema") != SCHEMA,
        first.get("analysis_protocol") != P.ANALYSIS_PROTOCOL,
        not isinstance(gates, dict),
        gates.get("pass") is not True if isinstance(gates, dict) else True,
        first.get("guided_study_authorized") is not True,
        not isinstance(analysis_input, dict),
        analysis_input.get("sha256")
        != receipt.get("input_properties_sha256")
        if isinstance(analysis_input, dict) else True,
        analysis_input.get("fetch_receipt_sha256")
        != receipt.get("fetch_receipt_sha256")
        if isinstance(analysis_input, dict) else True,
        P.SHA256_RE.fullmatch(receipt.get("input_properties_sha256", ""))
        is None,
        P.SHA256_RE.fullmatch(receipt.get("fetch_receipt_sha256", "")) is None,
    )):
        raise ConfirmationAnalysisError(
            "Confirmation A complete-gate receipt changed or did not pass"
        )
    if verify_live:
        try:
            fetch_sha, fetch = Audit.load_fetch_receipt(verify_live=True)
        except Audit.ExecutionAuditError as err:
            raise ConfirmationAnalysisError(
                "Confirmation A fetched-input seal changed"
            ) from err
        if any((
            fetch_sha != receipt["fetch_receipt_sha256"],
            fetch.get("properties_sha256")
            != receipt["input_properties_sha256"],
            analysis_input.get("path") != str(Audit.EVAL_PROPERTIES.resolve()),
        )):
            raise ConfirmationAnalysisError(
                "Confirmation A analysis input provenance changed"
            )
    return receipt_sha, receipt, first


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("properties", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--repeat-output", type=Path, default=DEFAULT_REPEAT_OUTPUT
    )
    parser.add_argument("--receipt", type=Path, default=DEFAULT_RECEIPT)
    parser.add_argument("--receipt-pin", type=Path, default=DEFAULT_RECEIPT_PIN)
    args = parser.parse_args(argv)
    result = run_twice(
        args.properties, args.output, args.repeat_output,
        args.receipt, args.receipt_pin,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ConfirmationAnalysisError,
        Audit.ExecutionAuditError,
        Original.TerminalIncidenceAnalysisError,
        P.ProtocolError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
