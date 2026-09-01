#!/usr/bin/env python3
"""Analyze guided Confirmation B twice from the sealed complete matrix."""

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

import audit_pdb_terminal_incidence_confirmation_b as Audit
import pdb_cap_selector_parser as CapParser
import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_b_protocol as P


class ConfirmationBAnalysisError(RuntimeError):
    pass


SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-b-analysis/v2"
)
RECEIPT_SCHEMA = SCHEMA + "/double-execution"
ARTIFACT_DIR = Audit.ARTIFACT_DIR
DEFAULT_OUTPUT = ARTIFACT_DIR / "analysis-v2.json"
DEFAULT_REPEAT_OUTPUT = ARTIFACT_DIR / "analysis-v2-repeat.json"
DEFAULT_RECEIPT = ARTIFACT_DIR / "analysis-execution-receipt-v2.json"
DEFAULT_RECEIPT_PIN = ARTIFACT_DIR / "analysis-execution-receipt-v2.sha256"


def _fraction_record(value: Fraction | None):
    if value is None:
        return None
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }


def _mean(values) -> Fraction | None:
    values = list(values)
    if not values:
        return None
    return sum(values, Fraction()) / len(values)


def _decode_records(raw: bytes) -> list[dict]:
    try:
        root = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as err:
        raise ConfirmationBAnalysisError("cannot load fetched properties") from err
    records = list(root.values()) if isinstance(root, dict) else root
    if not isinstance(records, list) or any(
        not isinstance(record, dict) for record in records
    ):
        raise ConfirmationBAnalysisError("properties are not a record matrix")
    return records


def _load_records(path: Path) -> list[dict]:
    try:
        raw = SafeIO.read_regular_file(
            Path(path), label="fetched properties"
        ).raw
    except SafeIO.SafeReadError as err:
        raise ConfirmationBAnalysisError("cannot load fetched properties") from err
    return _decode_records(raw)


def _fixed_properties() -> dict:
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
        "planner_revision": P.PLANNER_REVISION,
        "planner_binary_sha256": P.PLANNER_BINARY_SHA256,
        "preprocess_binary_sha256": P.PREPROCESS_BINARY_SHA256,
        "planner_preprocess_sha256": P.PREPROCESS_BINARY_SHA256,
        "required_lab_version": P.REQUIRED_LAB_VERSION,
        "planner_time_limit": P.TIME_LIMIT_SECONDS,
        "planner_memory_limit": P.MEMORY_LIMIT_MIB,
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
        "incidence_probe_layers": P.PROBE_LAYERS,
        "par2_seconds": P.PAR2_SECONDS,
        "primary_labels": list(P.PRIMARY_LABELS),
        "non_gating_reference_labels": list(P.NON_GATING_REFERENCE_LABELS),
        "intervention_label": P.INTERVENTION_LABEL,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
        "run_order_protocol": P.RUN_ORDER_PROTOCOL,
        "run_cell_mapping_sha256": P.RUN_CELL_MAPPING_SHA256,
        "confirmation_b_freeze_sha256": P.sha256_file(P.FREEZE_PATH),
        "confirmation_a_authorization_receipt_sha256": (
            P.CONFIRMATION_A_AUTHORIZATION_RECEIPT_SHA256
        ),
        "confirmation_a_cohort_manifest_sha256": (
            P.CONFIRMATION_A_COHORT_MANIFEST_SHA256
        ),
    }


def _same_typed(actual, expected) -> bool:
    if type(actual) is type(expected) and actual == expected:
        return True
    return (
        type(expected) is int
        and type(actual) is float
        and actual.is_integer()
        and int(actual) == expected
    )


def _par2(record: dict) -> tuple[Fraction, str]:
    coverage = record.get("coverage")
    if type(coverage) is not int or coverage not in (0, 1):
        raise ConfirmationBAnalysisError("cell coverage is not binary")
    code = record.get("planner_exit_code")
    if type(code) is not int:
        raise ConfirmationBAnalysisError("cell lacks an integer planner exit code")
    if coverage == 0:
        if code == 0:
            raise ConfirmationBAnalysisError(
                "unsolved cell has the success planner exit code"
            )
        return Fraction(P.PAR2_SECONDS), (
            "short_probe" if code == 34 else "unsolved_or_failure"
        )
    if code != 0:
        raise ConfirmationBAnalysisError(
            "solved cell has a non-success planner exit code"
        )
    total_time = record.get("total_time")
    if type(total_time) not in (int, float) or not math.isfinite(total_time):
        raise ConfirmationBAnalysisError("solved cell lacks finite total time")
    if total_time < 0 or total_time > P.TIME_LIMIT_SECONDS:
        raise ConfirmationBAnalysisError("solved cell total time is out of range")
    return Fraction(str(total_time)), "solved"


OVERHEAD_FIELDS = (
    "cpu_seconds", "wall_seconds", "peak_memory_before_kb",
    "peak_memory_after_kb", "peak_memory_delta_kb",
)


def _phase_overhead(record: dict, phase: str, *, required: bool):
    keys = ["incidence_selector_{}_{}".format(phase, field)
            for field in OVERHEAD_FIELDS]
    present = [key in record for key in keys]
    if not required:
        if any(present):
            raise ConfirmationBAnalysisError(
                "{} overhead exists for a phase that did not run".format(phase)
            )
        return None
    if not all(present):
        raise ConfirmationBAnalysisError(
            "certified selector trace lacks {} overhead".format(phase)
        )
    values = {field: record[key] for field, key in zip(OVERHEAD_FIELDS, keys)}
    for field in ("cpu_seconds", "wall_seconds"):
        value = values[field]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ConfirmationBAnalysisError(
                "selector {} {} is invalid".format(phase, field)
            )
    for field in (
        "peak_memory_before_kb", "peak_memory_after_kb",
        "peak_memory_delta_kb",
    ):
        if type(values[field]) is not int or values[field] < 0:
            raise ConfirmationBAnalysisError(
                "selector {} {} is invalid".format(phase, field)
            )
    if values["peak_memory_delta_kb"] != max(
        0,
        values["peak_memory_after_kb"] - values["peak_memory_before_kb"],
    ):
        raise ConfirmationBAnalysisError(
            "selector {} peak-memory delta is inconsistent".format(phase)
        )
    return values


def _complete_selector_pattern_pool(record: dict) -> list[dict]:
    """Return the pool event only after checking its required position/shape."""
    structural = record.get("incidence_selector_structural_trace")
    if (
        not isinstance(structural, list)
        or len(structural) < 3
        or not isinstance(structural[2], dict)
        or structural[2].get("event") != "pool"
        or not isinstance(structural[2].get("patterns"), list)
        or not structural[2]["patterns"]
    ):
        raise ConfirmationBAnalysisError(
            "complete selector structural trace lacks its pattern pool"
        )
    return structural[2]["patterns"]


def _validate_trace_record(record: dict, label: str) -> None:
    status = record.get("incidence_selector_trace_status")
    certified = record.get("incidence_selector_trace_certified")
    if record.get("incidence_selector_trace_schema") != P.SELECTOR_TRACE_SCHEMA:
        raise ConfirmationBAnalysisError("selector trace schema changed")
    if certified is True and record.get(
        "incidence_selector_trace_validation_error"
    ) is not None:
        raise ConfirmationBAnalysisError(
            "certified selector trace carries a validation error"
        )
    if label not in {P.GUIDED_LABEL, P.MATCHED_LABEL}:
        if status != "not_applicable" or certified is not True:
            raise ConfirmationBAnalysisError(
                "non-selector cell has selector-trace evidence"
            )
        for phase in ("probe", "selection"):
            _phase_overhead(record, phase, required=False)
        return
    if status in {"complete", "short_probe"} and certified is True:
        if (
            status == "complete"
            and record.get("planner_exit_code") == 34
            and type(record.get("planner_exit_code")) is int
        ):
            raise ConfirmationBAnalysisError(
                "complete selector trace is paired with short-probe exit code 34"
            )
        structural = record.get("incidence_selector_structural_trace")
        digest = record.get("incidence_selector_structural_trace_sha256")
        if not isinstance(structural, list) or P.SHA256_RE.fullmatch(
            digest or ""
        ) is None:
            raise ConfirmationBAnalysisError(
                "certified selector trace lacks structural evidence"
            )
        actual = hashlib.sha256(P.canonical_json(structural)).hexdigest()
        if actual != digest:
            raise ConfirmationBAnalysisError(
                "selector structural-trace hash changed"
            )
        if status == "complete" and any((
            P.SHA256_RE.fullmatch(
                record.get("incidence_selector_pool_sha256", "")
            ) is None,
            P.SHA256_RE.fullmatch(
                record.get("incidence_selector_preselection_sha256", "")
            ) is None,
            not isinstance(
                record.get("incidence_selector_reference_identity"), dict
            ),
            not isinstance(
                record.get("incidence_selector_selected_identity"), dict
            ),
            type(record.get(
                "incidence_selector_selected_differs_from_reference"
            )) is not bool,
            type(record.get("incidence_selector_probe_completed_layers"))
            is not int,
            record.get("incidence_selector_probe_completed_layers") != 16,
        )):
            raise ConfirmationBAnalysisError(
                "complete selector trace lacks identity evidence"
            )
        if status == "complete":
            _complete_selector_pattern_pool(record)
            reference = record["incidence_selector_reference_identity"]
            selected = record["incidence_selector_selected_identity"]
            differs = selected != reference
            if record[
                "incidence_selector_selected_differs_from_reference"
            ] is not differs:
                raise ConfirmationBAnalysisError(
                    "selector identity difference flag is inconsistent"
                )
            if label == P.MATCHED_LABEL and differs:
                raise ConfirmationBAnalysisError(
                    "matched control did not select its reference"
                )
        if status == "short_probe" and any((
            record.get("coverage") != 0,
            type(record.get("coverage")) is not int,
            record.get("planner_exit_code") != 34,
            type(record.get("planner_exit_code")) is not int,
            record.get("incidence_selector_pool_sha256") is not None,
            record.get("incidence_selector_preselection_sha256") is not None,
            record.get("incidence_selector_reference_identity") is not None,
            record.get("incidence_selector_selected_identity") is not None,
            record.get(
                "incidence_selector_selected_differs_from_reference"
            ) is not False,
            type(record.get("incidence_selector_probe_completed_layers"))
            is not int,
            not 0 <= record.get(
                "incidence_selector_probe_completed_layers", -1
            ) < P.PROBE_LAYERS,
        )):
            raise ConfirmationBAnalysisError(
                "short-probe selector metadata is inconsistent"
            )
        _phase_overhead(record, "probe", required=True)
        _phase_overhead(record, "selection", required=status == "complete")
        return
    # Genuine failed algorithms remain performance outcomes.  Their partial or
    # invalid trace is retained here and makes the provenance gate fail.
    if certified is not False or status not in {
        "invalid", "partial", "unexpected", None
    }:
        raise ConfirmationBAnalysisError("selector trace status is malformed")


def _plain_reference_evidence(record: dict) -> dict:
    """Certify the standalone K32 endpoint and its complete fixed pool."""
    candidates = record.get("pdb_selector_candidates")
    selected = record.get("pdb_selector_selected")
    final = record.get("pdb_selector_final")
    if any((
        record.get("pdb_cap_selector_parser_protocol")
        != CapParser.PARSER_PROTOCOL,
        record.get("pdb_selector_trace_complete") is not True,
        record.get("pdb_selector_trace_certified") is not True,
        record.get("pdb_selector_validation_error") is not None,
        not isinstance(candidates, list),
        not isinstance(selected, dict),
        not isinstance(final, dict),
    )):
        raise ConfirmationBAnalysisError(
            "standalone K32 reference lacks a certified cap-selector trace"
        )
    pattern = selected.get("pattern")
    sources = selected.get("sources")
    cap = selected.get("value_cap")
    if any((
        selected.get("cofactor_width_budget") != 32,
        type(selected.get("cofactor_width_budget")) is not int,
        not isinstance(pattern, list),
        any(type(value) is not int for value in pattern),
        not isinstance(sources, list),
        not sources,
        any(not isinstance(source, str) or not source for source in sources),
        type(cap) is not int,
        cap < -1,
    )):
        raise ConfirmationBAnalysisError(
            "standalone K32 reference identity is malformed"
        )
    patterns = []
    for candidate in candidates:
        if (
            not isinstance(candidate, dict)
            or type(candidate.get("abstract_states")) is not int
            or candidate["abstract_states"] < 1
        ):
            raise ConfirmationBAnalysisError(
                "standalone K32 candidate identity is malformed"
            )
        candidate_pattern = candidate.get("pattern")
        if any(row["pattern"] == candidate_pattern for row in patterns):
            continue
        patterns.append({
            "pattern_index": len(patterns),
            "sources": candidate.get("sources"),
            "pattern": candidate_pattern,
            "abstract_states": candidate["abstract_states"],
            "within_state_budget": candidate["abstract_states"] <= 100000,
        })
    matching = [
        row["pattern_index"] for row in patterns if row["pattern"] == pattern
    ]
    if len(matching) != 1:
        raise ConfirmationBAnalysisError(
            "standalone K32 selected pattern is not unique in its pool"
        )
    return {
        "identity": {
            "pattern_index": matching[0],
            "sources": sources,
            "pattern": pattern,
            "value_cap": None if cap == -1 else cap,
        },
        "pool": patterns,
        "pool_sha256": hashlib.sha256(P.canonical_json(patterns)).hexdigest(),
    }


def _plain_reference_identity(record: dict) -> dict:
    return _plain_reference_evidence(record)["identity"]


def validate_matrix(records: list[dict]):
    P.validate_protocol_without_sources()
    if len(records) != P.CELL_COUNT:
        raise ConfirmationBAnalysisError(
            "matrix has {} records, expected {}".format(
                len(records), P.CELL_COUNT
            )
        )
    _, materials = P._load_freeze(P.FREEZE_PATH)
    source_tasks = {
        (task["directory"], task["problem"]): task
        for task in materials.tasks
    }
    if len(source_tasks) != P.COHORT_TASKS:
        raise ConfirmationBAnalysisError("frozen source cohort changed")
    fixed = _fixed_properties()
    driver_options = [
        "--overall-time-limit", "{}s".format(P.TIME_LIMIT_SECONDS),
        "--overall-memory-limit", "{}M".format(P.MEMORY_LIMIT_MIB),
        "--build", "release_no_lp",
    ]
    matrix = {}
    outcome_classes = Counter()
    accounting_rows = []
    for record in records:
        label = record.get("algorithm")
        domain = record.get("domain")
        problem = record.get("problem")
        if label not in P.LABELS or not all(
            isinstance(value, str) and value for value in (domain, problem)
        ):
            raise ConfirmationBAnalysisError("cell identity is invalid")
        task = (domain, problem)
        key = (label, task)
        if key in matrix or task not in source_tasks:
            raise ConfirmationBAnalysisError("cell is duplicated or outside cohort")
        for field, expected in fixed.items():
            if not _same_typed(record.get(field), expected):
                raise ConfirmationBAnalysisError(
                    "cell changed fixed field {}".format(field)
                )
        if any((
            record.get("id") != [label, domain, problem],
            record.get("component_options") != ["--search", P.SEARCHES[label]],
            record.get("driver_options") != driver_options,
            record.get("build_options") != list(P.BUILD_OPTIONS),
            record.get("local_revision") != P.PLANNER_REVISION,
            record.get("global_revision") != P.PLANNER_REVISION,
        )):
            raise ConfirmationBAnalysisError("cell command provenance changed")
        source = source_tasks[task]
        expected_source = {
            "domain_source_path": source["domain_file"],
            "problem_source_path": source["problem_file"],
            "domain_source_sha256": source["domain_sha256"],
            "problem_source_sha256": source["problem_sha256"],
        }
        if any(record.get(field) != value
               for field, value in expected_source.items()):
            raise ConfirmationBAnalysisError("cell source identity changed")
        _validate_trace_record(record, label)
        plain_reference_evidence = (
            _plain_reference_evidence(record)
            if label == P.PLAIN_REFERENCE_LABEL else None
        )
        value, outcome = _par2(record)
        outcome_classes[(label, outcome)] += 1
        accounting_rows.append({
            "algorithm": label,
            "domain": domain,
            "family": source["family"],
            "problem": problem,
            "coverage": record["coverage"],
            "planner_exit_code": record["planner_exit_code"],
            "par2": _fraction_record(value),
            "outcome_class": outcome,
            "selector_trace_status": record.get(
                "incidence_selector_trace_status"
            ),
        })
        matrix[key] = {
            "record": record,
            "par2": value,
            "plain_reference_identity": (
                plain_reference_evidence["identity"]
                if plain_reference_evidence is not None else None
            ),
            "plain_reference_pool": (
                plain_reference_evidence["pool"]
                if plain_reference_evidence is not None else None
            ),
            "plain_reference_pool_sha256": (
                plain_reference_evidence["pool_sha256"]
                if plain_reference_evidence is not None else None
            ),
        }
    tasks = sorted(source_tasks)
    if len(matrix) != P.CELL_COUNT or any(
        (label, task) not in matrix for task in tasks for label in P.LABELS
    ):
        raise ConfirmationBAnalysisError("matrix is not a complete Cartesian product")
    return matrix, tasks, source_tasks, outcome_classes, accounting_rows


def _selector_pair_gate(matrix, tasks) -> tuple[dict, set[tuple[str, str]]]:
    counts = Counter()
    failures = []
    different = set()
    pair_rows = []
    for task in tasks:
        guided = matrix[(P.GUIDED_LABEL, task)]["record"]
        matched = matrix[(P.MATCHED_LABEL, task)]["record"]
        g_status = guided.get("incidence_selector_trace_status")
        m_status = matched.get("incidence_selector_trace_status")
        reason = None
        if g_status != m_status:
            reason = "status_mismatch"
        elif g_status not in {"complete", "short_probe"}:
            reason = "uncertified_pair"
        elif guided.get("incidence_selector_trace_certified") is not True or (
            matched.get("incidence_selector_trace_certified") is not True
        ):
            reason = "uncertified_pair"
        elif guided.get("incidence_selector_structural_trace") != matched.get(
            "incidence_selector_structural_trace"
        ):
            reason = "structural_trace_mismatch"
        elif guided.get("incidence_selector_structural_trace_sha256") != (
            matched.get("incidence_selector_structural_trace_sha256")
        ):
            reason = "structural_hash_mismatch"
        elif g_status == "complete" and any((
            guided.get("incidence_selector_pool_sha256")
            != matched.get("incidence_selector_pool_sha256"),
            guided.get("incidence_selector_preselection_sha256")
            != matched.get("incidence_selector_preselection_sha256"),
            guided.get("incidence_selector_reference_identity")
            != matched.get("incidence_selector_reference_identity"),
        )):
            reason = "pool_preselection_or_reference_mismatch"
        elif g_status == "complete" and matched.get(
            "incidence_selector_selected_identity"
        ) != matched.get("incidence_selector_reference_identity"):
            reason = "matched_selection_is_not_reference"
        elif g_status == "complete" and matrix[
            (P.PLAIN_REFERENCE_LABEL, task)
        ].get("plain_reference_identity") != {
            key: guided["incidence_selector_reference_identity"][key]
            for key in ("pattern_index", "sources", "pattern", "value_cap")
        }:
            reason = "standalone_reference_identity_mismatch"
        elif g_status == "complete" and matrix[
            (P.PLAIN_REFERENCE_LABEL, task)
        ].get("plain_reference_pool") != _complete_selector_pattern_pool(guided):
            reason = "standalone_reference_pool_mismatch"
        elif g_status == "complete" and guided.get(
            "incidence_selector_selected_differs_from_reference"
        ) is not (
            guided.get("incidence_selector_selected_identity")
            != guided.get("incidence_selector_reference_identity")
        ):
            reason = "guided_selection_difference_flag_mismatch"
        if reason is not None:
            counts["failed"] += 1
            failures.append({"task": list(task), "reason": reason})
            continue
        counts[g_status] += 1
        differs = g_status == "complete" and (
            guided.get("incidence_selector_selected_identity")
            != guided.get("incidence_selector_reference_identity")
        )
        if differs:
            different.add(task)
        pair_rows.append({
            "task": list(task),
            "status": g_status,
            "structural_trace_sha256": guided[
                "incidence_selector_structural_trace_sha256"
            ],
            "pool_sha256": guided.get("incidence_selector_pool_sha256"),
            "preselection_sha256": guided.get(
                "incidence_selector_preselection_sha256"
            ),
            "guided_selected_differs": differs,
            "standalone_reference_pool_sha256": matrix[
                (P.PLAIN_REFERENCE_LABEL, task)
            ].get("plain_reference_pool_sha256"),
        })
    passed = not failures and sum(counts.values()) == len(tasks)
    return {
        "pass": passed,
        "tasks": len(tasks),
        "status_counts": dict(counts),
        "full_preselection_pairs": counts["complete"],
        "certified_short_probe_pairs": counts["short_probe"],
        "failed_pairs": failures,
        "all_tasks_accounted": sum(counts.values()) == len(tasks),
        "exact_structural_identity_required": True,
        "standalone_reference_identity_required": True,
        "standalone_normalized_pattern_pool_required": True,
        "timing_and_memory_excluded_from_identity": True,
        "pair_rows": pair_rows,
        "selected_difference_tasks": len(different),
    }, different


def _bootstrap(family_values: dict[str, Fraction]) -> dict:
    families = sorted(family_values)
    if not families:
        return {"families": 0, "lower_95": None, "upper_95": None}
    rng = random.Random(P.BOOTSTRAP_SEED)
    samples = []
    for _ in range(P.BOOTSTRAP_REPLICATES):
        samples.append(_mean(
            family_values[families[rng.randrange(len(families))]]
            for _ in families
        ))
    samples.sort()
    lower = math.ceil(0.025 * P.BOOTSTRAP_REPLICATES) - 1
    upper = math.ceil(0.975 * P.BOOTSTRAP_REPLICATES) - 1
    return {
        "families": len(families),
        "replicates": P.BOOTSTRAP_REPLICATES,
        "seed": P.BOOTSTRAP_SEED,
        "lower_95": _fraction_record(samples[lower]),
        "upper_95": _fraction_record(samples[upper]),
    }


def _contrast(matrix, tasks, source_tasks, reference: str) -> dict:
    by_family = defaultdict(list)
    guided_coverage = 0
    reference_coverage = 0
    task_values = {}
    for task in sorted(tasks):
        guided = matrix[(P.GUIDED_LABEL, task)]
        other = matrix[(reference, task)]
        guided_coverage += guided["record"]["coverage"]
        reference_coverage += other["record"]["coverage"]
        value = (other["par2"] - guided["par2"]) / P.PAR2_SECONDS
        task_values[task] = value
        by_family[source_tasks[task]["family"]].append(value)
    family_values = {
        family: _mean(values) for family, values in sorted(by_family.items())
    }
    macro = _mean(family_values.values())
    leave_one_out = {
        family: _mean(value for other, value in family_values.items()
                      if other != family)
        for family in family_values
    }
    bootstrap = _bootstrap(family_values)
    lower = bootstrap["lower_95"]
    lower_fraction = (
        None if lower is None else Fraction(
            lower["numerator"], lower["denominator"]
        )
    )
    minimum = Fraction(
        P.MIN_NORMALIZED_PAR2_IMPROVEMENT_NUMERATOR,
        P.MIN_NORMALIZED_PAR2_IMPROVEMENT_DENOMINATOR,
    )
    clauses = {
        "coverage_nonlower": guided_coverage >= reference_coverage,
        "family_macro_at_least_0_02": macro is not None and macro >= minimum,
        "bootstrap_lower_95_positive": (
            lower_fraction is not None and lower_fraction > 0
        ),
        "every_leave_one_family_out_positive": (
            bool(leave_one_out)
            and all(value is not None and value > 0
                    for value in leave_one_out.values())
        ),
    }
    return {
        "reference": reference,
        "tasks": len(tasks),
        "families": len(family_values),
        "coverage": {
            "guided": guided_coverage,
            "reference": reference_coverage,
            "difference": guided_coverage - reference_coverage,
        },
        "task_normalized_improvements": {
            "{}:{}".format(*task): _fraction_record(value)
            for task, value in sorted(task_values.items())
        },
        "family_normalized_improvements": {
            family: _fraction_record(value)
            for family, value in family_values.items()
        },
        "family_macro_normalized_improvement": _fraction_record(macro),
        "minimum_family_macro": _fraction_record(minimum),
        "bootstrap": bootstrap,
        "leave_one_family_out": {
            family: _fraction_record(value)
            for family, value in leave_one_out.items()
        },
        "clauses": clauses,
        "pass": all(clauses.values()),
    }


def _overhead_summary(values) -> dict:
    exact = [Fraction(str(value)) for value in values]
    if not exact:
        return {
            "count": 0, "total": None, "mean": None,
            "minimum": None, "maximum": None,
        }
    return {
        "count": len(exact),
        "total": _fraction_record(sum(exact, Fraction())),
        "mean": _fraction_record(_mean(exact)),
        "minimum": _fraction_record(min(exact)),
        "maximum": _fraction_record(max(exact)),
    }


def _selector_overhead(matrix, tasks, source_tasks) -> dict:
    rows = []
    for task in sorted(tasks):
        for label in (P.GUIDED_LABEL, P.MATCHED_LABEL):
            record = matrix[(label, task)]["record"]
            status = record.get("incidence_selector_trace_status")
            certified = record.get("incidence_selector_trace_certified") is True
            probe = None
            selection = None
            if certified and status in {"complete", "short_probe"}:
                probe = _phase_overhead(record, "probe", required=True)
                selection = _phase_overhead(
                    record, "selection", required=status == "complete"
                )
            rows.append({
                "domain": task[0],
                "problem": task[1],
                "family": source_tasks[task]["family"],
                "arm": label,
                "trace_status": status,
                "trace_certified": certified,
                "probe": probe,
                "selection": selection,
            })
    by_arm = {}
    for label in (P.GUIDED_LABEL, P.MATCHED_LABEL):
        arm_rows = [row for row in rows if row["arm"] == label]
        phases = {}
        for phase in ("probe", "selection"):
            phases[phase] = {
                field: _overhead_summary(
                    row[phase][field]
                    for row in arm_rows if row[phase] is not None
                )
                for field in OVERHEAD_FIELDS
            }
        by_arm[label] = {
            "tasks": len(arm_rows),
            "status_counts": dict(sorted(Counter(
                "missing" if row["trace_status"] is None
                else row["trace_status"]
                for row in arm_rows
            ).items())),
            "phases": phases,
        }
    return {
        "affects_complete_gate": False,
        "timing_and_memory_excluded_from_structural_identity": True,
        "rows": rows,
        "by_arm": by_arm,
    }


def analyze_records(records: list[dict]) -> dict:
    matrix, tasks, source_tasks, outcomes, accounting = validate_matrix(records)
    provenance, different = _selector_pair_gate(matrix, tasks)
    contrasts = {
        reference: _contrast(matrix, tasks, source_tasks, reference)
        for reference in (P.PLAIN_REFERENCE_LABEL, P.MATCHED_LABEL)
    }
    non_gating_contrasts = {
        reference: _contrast(matrix, tasks, source_tasks, reference)
        for reference in P.NON_GATING_REFERENCE_LABELS
    }
    selector_overhead = _selector_overhead(matrix, tasks, source_tasks)
    mechanism = None
    mechanism_authorized = False
    mechanism_families = {
        source_tasks[task]["family"] for task in different
    }
    mechanism_support = {
        "tasks": len(different),
        "minimum_tasks": P.MIN_MECHANISM_TASKS,
        "families": len(mechanism_families),
        "minimum_families": P.MIN_MECHANISM_FAMILIES,
        "pass": (
            len(different) >= P.MIN_MECHANISM_TASKS
            and len(mechanism_families) >= P.MIN_MECHANISM_FAMILIES
        ),
    }
    if different:
        mechanism = _contrast(
            matrix, sorted(different), source_tasks, P.MATCHED_LABEL
        )
        mechanism_authorized = (
            provenance["pass"]
            and mechanism_support["pass"]
            and mechanism["pass"]
        )
    complete_pass = provenance["pass"] and all(
        contrast["pass"] for contrast in contrasts.values()
    )
    matrix_digest = hashlib.sha256(P.canonical_json(accounting)).hexdigest()
    return {
        "schema": SCHEMA,
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "matrix": {
            "tasks": len(tasks),
            "configs": P.CONFIG_COUNT,
            "cells": len(records),
            "all_cells_assigned_par2": len(accounting) == P.CELL_COUNT,
            "par2_seconds": P.PAR2_SECONDS,
            "algorithm_failures_are_par2": True,
            "no_task_dropping": True,
            "outcome_counts": {
                "{}:{}".format(*key): value
                for key, value in sorted(outcomes.items())
            },
            "accounting_sha256": matrix_digest,
            "accounting_rows": accounting,
        },
        "selector_provenance": provenance,
        "contrasts": contrasts,
        "non_gating_contrasts": {
            "affects_complete_gate": False,
            "references": non_gating_contrasts,
        },
        "selector_overhead": selector_overhead,
        "mechanism": {
            "claim_is_conditional_on_selected_heuristic_differing": True,
            "eligible_tasks": len(different),
            "eligible_families": len(mechanism_families),
            "support": mechanism_support,
            "contrast": mechanism,
            "claim_authorized": mechanism_authorized,
        },
        "gates": {
            "pass": complete_pass,
            "decision": "PASS" if complete_pass else "FAIL",
            "selector_provenance_pass": provenance["pass"],
            "contrast_pass": {
                label: value["pass"] for label, value in contrasts.items()
            },
            "support_failure_is_failure": True,
        },
    }


def _load_sealed_input(path: Path) -> tuple[list[dict], str, str]:
    try:
        path = SafeIO.validate_lexical_path(
            Path(path), label="sealed Confirmation B properties",
            expected_path=Audit.EVAL_PROPERTIES,
        )
    except SafeIO.SafeReadError as err:
        raise ConfirmationBAnalysisError(
            "analysis input is not the sealed matrix"
        ) from err
    P.validate_protocol_without_sources()
    try:
        fetch_sha, fetch = Audit.load_fetch_receipt(verify_live=True)
    except Audit.ExecutionAuditError as err:
        raise ConfirmationBAnalysisError(
            "fetched properties provenance is invalid"
        ) from err
    try:
        loaded = SafeIO.read_regular_file(
            path, label="sealed Confirmation B properties",
            expected_path=Audit.EVAL_PROPERTIES,
        )
        raw = loaded.raw
    except SafeIO.SafeReadError as err:
        raise ConfirmationBAnalysisError("cannot read sealed properties") from err
    properties_sha = loaded.sha256
    if (
        properties_sha != fetch.get("properties_sha256")
    ):
        raise ConfirmationBAnalysisError("analysis input is not the sealed matrix")
    records = _decode_records(raw)
    return records, properties_sha, fetch_sha


def _exclusive(path: Path, raw: bytes, label: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise ConfirmationBAnalysisError("{} already exists".format(label)) from err
    return hashlib.sha256(raw).hexdigest()


def run_twice(properties, output, repeat_output, receipt_path, receipt_pin):
    paths = tuple(map(Path, (
        output, repeat_output, receipt_path, receipt_pin,
    )))
    if len({path.resolve() for path in paths}) != len(paths) or any(
        path.exists() or path.is_symlink() for path in paths
    ):
        raise ConfirmationBAnalysisError("analysis output namespace is not fresh")
    records_one, properties_sha, fetch_sha = _load_sealed_input(Path(properties))
    result_one = analyze_records(records_one)
    result_one["input"] = {
        "path": str(Path(properties).resolve()),
        "sha256": properties_sha,
        "fetch_receipt_sha256": fetch_sha,
    }
    raw_one = P.canonical_json_line(result_one)
    records_two, properties_sha_two, fetch_sha_two = _load_sealed_input(
        Path(properties)
    )
    if (properties_sha_two, fetch_sha_two) != (properties_sha, fetch_sha):
        raise ConfirmationBAnalysisError("analysis input changed between runs")
    result_two = analyze_records(records_two)
    result_two["input"] = dict(result_one["input"])
    raw_two = P.canonical_json_line(result_two)
    if raw_one != raw_two:
        raise ConfirmationBAnalysisError("two analyses are not byte-identical")
    first_sha = _exclusive(paths[0], raw_one, "primary analysis output")
    second_sha = _exclusive(paths[1], raw_two, "repeat analysis output")
    try:
        first_readback = SafeIO.read_regular_file(
            paths[0], label="primary analysis output"
        ).raw
        second_readback = SafeIO.read_regular_file(
            paths[1], label="repeat analysis output"
        ).raw
    except SafeIO.SafeReadError as err:
        raise ConfirmationBAnalysisError("cannot verify published analyses") from err
    if any((
        first_sha != second_sha,
        first_readback != raw_one,
        second_readback != raw_two,
        hashlib.sha256(first_readback).hexdigest() != first_sha,
        hashlib.sha256(second_readback).hexdigest() != second_sha,
    )):
        raise ConfirmationBAnalysisError("published analyses differ")
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "input_properties_sha256": properties_sha,
        "fetch_receipt_sha256": fetch_sha,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
        "first_output": str(paths[0].resolve()),
        "second_output": str(paths[1].resolve()),
        "first_output_sha256": first_sha,
        "second_output_sha256": second_sha,
        "outputs_byte_identical": True,
        "confirmation_b_complete_gate_passed": result_one["gates"]["pass"],
        "mechanism_claim_authorized": result_one["mechanism"][
            "claim_authorized"
        ],
    }
    receipt_raw = P.canonical_json_line(receipt)
    receipt_sha = _exclusive(paths[2], receipt_raw, "analysis receipt")
    _exclusive(paths[3], (receipt_sha + "\n").encode("ascii"),
               "analysis receipt pin")
    return {**receipt, "analysis_receipt_sha256": receipt_sha}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("properties", type=Path)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repeat-output", type=Path,
                        default=DEFAULT_REPEAT_OUTPUT)
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
    except (ConfirmationBAnalysisError, Audit.ExecutionAuditError,
            P.ProtocolError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
