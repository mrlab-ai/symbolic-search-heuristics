#!/usr/bin/env python3
"""Produce outcome-redacted standalone K=32 evidence from sealed B traces."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
from pathlib import Path

import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_protocol as P


class StandaloneError(RuntimeError):
    pass


PLAIN_REFERENCE_LABEL = "pdb_cap_aware_k32"
BASE_B_CONFIG_COUNT = 9
BASE_B_FIXED_CONFIGS = 6
PLAIN_REFERENCE_STRUCTURAL_FIELDS = (
    "pdb_cap_selector_parser_protocol", "pdb_selector_trace_complete",
    "pdb_selector_trace_certified", "pdb_selector_validation_error",
    "pdb_selector_candidates", "pdb_selector_selected", "pdb_selector_final",
)


def _cap_parser():
    # Lab is part of the pinned run environment, not a prerequisite for the
    # outcome-blind protocol/calibration import boundary.
    return importlib.import_module("pdb_cap_selector_parser")


def plain_reference_rows(snapshot: dict) -> list[dict]:
    identities = sorted(P._task_identity(task) for task in P.guided_b_tasks(snapshot))
    family_positions = {}
    rows = []
    for task_index, (domain, problem, family) in enumerate(identities):
        position = family_positions.get(family, 0)
        family_positions[family] = position + 1
        rotation = position % 3
        triad_position = (-rotation) % 3
        rows.append({
            "run_id": task_index * BASE_B_CONFIG_COUNT + BASE_B_FIXED_CONFIGS
            + triad_position + 1,
            "algorithm": PLAIN_REFERENCE_LABEL,
            "domain": domain,
            "problem": problem,
            "family": family,
            "family_sequence_index": position,
            "triad_position": triad_position,
        })
    if len(rows) != P.COHORT_TASKS:
        raise StandaloneError("sealed B K32 mapping cardinality changed")
    return rows


def _plain_reference_evidence(record: dict) -> dict:
    CapParser = _cap_parser()
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
        raise StandaloneError("B K32 reference lacks a certified selector trace")
    pattern = selected.get("pattern")
    sources = selected.get("sources")
    cap = selected.get("value_cap")
    if any((
        type(selected.get("cofactor_width_budget")) is not int,
        selected.get("cofactor_width_budget") != 32,
        not isinstance(pattern, list),
        any(type(value) is not int for value in pattern),
        not isinstance(sources, list), not sources,
        any(not isinstance(source, str) or not source for source in sources),
        type(cap) is not int, cap < -1,
    )):
        raise StandaloneError("B K32 reference identity is malformed")
    patterns = []
    for candidate in candidates:
        if (
            not isinstance(candidate, dict)
            or type(candidate.get("abstract_states")) is not int
            or candidate["abstract_states"] < 1
        ):
            raise StandaloneError("B K32 candidate identity is malformed")
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
        raise StandaloneError("B K32 selected pattern is not unique in its pool")
    return {
        "identity": {
            "pattern_index": matching[0], "sources": sources,
            "pattern": pattern, "value_cap": None if cap == -1 else cap,
        },
        "pool": patterns,
        "pool_sha256": hashlib.sha256(P.canonical_json(patterns)).hexdigest(),
    }


def _representative_projection(
    candidate: dict, pattern_index: int,
) -> dict:
    cap = candidate.get("value_cap")
    projected = {
        "pattern_index": pattern_index,
        "sources": candidate.get("sources"),
        "pattern": candidate.get("pattern"),
        "value_cap": None if cap == -1 else cap,
        "initial_dead_end": candidate.get("initial_dead_end"),
        "initial_h": candidate.get("initial_h"),
        "finite_sum": candidate.get("finite_sum"),
        "finite_count": candidate.get("finite_count"),
        "dead_count": candidate.get("dead_count"),
        "abstract_states": candidate.get("abstract_states"),
        "cofactor_width": candidate.get("cofactor_width"),
        "reference_feasible": candidate.get("feasible"),
    }
    return projected


def _record_projection(record: dict) -> dict:
    CapParser = _cap_parser()
    structural = {
        field: record.get(field) for field in PLAIN_REFERENCE_STRUCTURAL_FIELDS
    }
    try:
        plain = _plain_reference_evidence(structural)
        candidates = structural["pdb_selector_candidates"]
    except (StandaloneError, KeyError, TypeError) as err:
        raise StandaloneError("B K32 structural certificate is invalid") from err
    errors, representatives, source_owner = CapParser._validate_groups(
        candidates, True
    )
    if errors or set(source_owner) != set(P.CANDIDATE_SOURCES):
        raise StandaloneError("B K32 candidate groups are invalid")
    pool = plain["pool"]
    indexes = {tuple(row["pattern"]): row["pattern_index"] for row in pool}
    if len(indexes) != len(pool):
        raise StandaloneError("B K32 normalized pool is duplicated")
    try:
        projected = [
            _representative_projection(row, indexes[tuple(row["pattern"])])
            for row in representatives
        ]
    except (KeyError, TypeError) as err:
        raise StandaloneError("B K32 representative is outside its pool") from err
    projected.sort(key=lambda row: row["pattern_index"])
    expected_indexes = [
        row["pattern_index"] for row in pool if row["within_state_budget"]
    ]
    if [row["pattern_index"] for row in projected] != expected_indexes:
        raise StandaloneError("B K32 representative coverage changed")
    return {
        "reference_identity": plain["identity"],
        "reference_representatives": projected,
        "reference_representatives_sha256": hashlib.sha256(
            P.canonical_json(projected)
        ).hexdigest(),
        "normalized_pool": pool,
        "normalized_pool_sha256": plain["pool_sha256"],
    }


def build_evidence(
    records: list[dict], snapshot: dict, planner_manifest: dict,
    sealed_b_input: dict,
) -> dict:
    """Project only certified B structure; ignore all outcome fields."""
    P.validate_base_snapshot(snapshot)
    P.validate_planner_manifest(planner_manifest)
    P.validate_standalone_source_binding(sealed_b_input)
    expected_rows = plain_reference_rows(snapshot)
    expected = {
        (row["domain"], row["problem"]): row for row in expected_rows
    }
    selected = {}
    if not isinstance(records, list):
        raise StandaloneError("sealed B properties are not a record list")
    for record in records:
        if not isinstance(record, dict):
            raise StandaloneError("sealed B properties contain a non-record")
        if record.get("algorithm") != PLAIN_REFERENCE_LABEL:
            continue
        task = (record.get("domain"), record.get("problem"))
        row = expected.get(task)
        if row is None or task in selected or any(
            record.get(field) != row[field]
            for field in ("run_id", "algorithm", "domain", "problem")
        ):
            raise StandaloneError("B K32 run mapping changed or is duplicated")
        selected[task] = record
    if set(selected) != set(expected):
        raise StandaloneError("B K32 structural task coverage is incomplete")

    output = []
    for task in sorted(expected):
        row = expected[task]
        output.append({
            "domain": row["domain"],
            "problem": row["problem"],
            "family": row["family"],
            **_record_projection(selected[task]),
        })
    evidence = {
        "schema": P.STANDALONE_SCHEMA,
        "base_b_freeze_sha256": snapshot["base_b_freeze_sha256"],
        "cohort_manifest_sha256": P.guided_b_projection_sha256(snapshot),
        "producer": {
            "planner_manifest": planner_manifest,
            "planner_manifest_sha256": hashlib.sha256(
                P.canonical_json_line(planner_manifest)
            ).hexdigest(),
            "option_matrix_sha256": P.option_matrix_digest(),
            "reference_rule": (
                "strongest-K32-feasible-cap-per-pattern-then-score-v1"
            ),
        },
        "sealed_b_input": sealed_b_input,
        "records": output,
        "records_sha256": hashlib.sha256(P.canonical_json(output)).hexdigest(),
    }
    P.validate_standalone_evidence(evidence, snapshot, planner_manifest)
    return evidence


def _relative(path: Path) -> str:
    try:
        lexical = Path(os.path.abspath(path))
        root = Path(os.path.abspath(P.REPO))
        return lexical.relative_to(root).as_posix()
    except ValueError as err:
        raise StandaloneError("sealed Confirmation B input escapes repository") from err


def sealed_b_records() -> tuple[list[dict], dict]:
    # This import is intentionally inside the only live B reader. Callers must
    # validate calibration before invoking it.
    import audit_pdb_terminal_incidence_confirmation_b as BAudit

    expected_paths = {
        BAudit.PARSE_RECEIPT: P.BASE_B_PARSE_RECEIPT_PATH,
        BAudit.FETCH_RECEIPT: P.BASE_B_FETCH_RECEIPT_PATH,
        BAudit.EVAL_PROPERTIES: P.BASE_B_PROPERTIES_PATH,
    }
    if any(Path(actual) != expected for actual, expected in expected_paths.items()):
        raise StandaloneError("sealed Confirmation B input path changed")
    try:
        parse_sha, _ = BAudit.load_parse_receipt(verify_live=True)
        fetch_sha, fetch = BAudit.load_fetch_receipt(verify_live=True)
        loaded = CampaignIO.read_regular_exact(
            BAudit.EVAL_PROPERTIES, expected=BAudit.EVAL_PROPERTIES,
            label="sealed Confirmation B properties",
        )
        payload = json.loads(loaded.raw.decode("utf-8"))
    except (
        BAudit.ExecutionAuditError, CampaignIO.CampaignIOError,
        UnicodeDecodeError, json.JSONDecodeError,
    ) as err:
        raise StandaloneError("cannot load sealed Confirmation B properties") from err
    if (
        fetch.get("parse_receipt_sha256") != parse_sha
        or fetch.get("properties_sha256") != loaded.sha256
    ):
        raise StandaloneError("Confirmation B fetch seal changed")
    records = list(payload.values()) if isinstance(payload, dict) else payload
    binding = {
        "parse_receipt_path": _relative(BAudit.PARSE_RECEIPT),
        "parse_receipt_sha256": parse_sha,
        "fetch_receipt_path": _relative(BAudit.FETCH_RECEIPT),
        "fetch_receipt_sha256": fetch_sha,
        "properties_path": _relative(BAudit.EVAL_PROPERTIES),
        "properties_sha256": loaded.sha256,
    }
    P.validate_standalone_source_binding(binding)
    return records, binding


def produce() -> dict:
    # Calibration must be completely validated before importing any live B
    # cohort or property through snapshot_sealed_b/_sealed_b_records.
    _, calibration = P.load_canonical(
        P.CALIBRATION_RECEIPT_PATH, "calibration receipt",
        expected_path=P.CALIBRATION_RECEIPT_PATH,
    )
    P.validate_calibration_receipt(calibration)
    _, planner = P.load_canonical(
        P.PLANNER_MANIFEST_PATH, "planner manifest",
        expected_path=P.PLANNER_MANIFEST_PATH,
    )
    P.validate_planner_manifest(planner)
    if P.canonical_json(calibration["planner"]) != P.canonical_json(planner):
        raise StandaloneError("calibration planner binding changed")
    snapshot = P.snapshot_sealed_b(calibration)
    records, sealed_b_input = sealed_b_records()
    evidence = build_evidence(records, snapshot, planner, sealed_b_input)
    try:
        CampaignIO.write_canonical_exclusive(
            P.STANDALONE_K32_PATH, evidence, expected=P.STANDALONE_K32_PATH,
            root=P.SCRIPT_DIR, label="standalone K32 evidence",
            canonical_json_line=P.canonical_json_line,
        )
        _, reopened = CampaignIO.read_canonical_exact(
            P.STANDALONE_K32_PATH, expected=P.STANDALONE_K32_PATH,
            label="standalone K32 evidence",
            canonical_json_line=P.canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise StandaloneError("cannot publish standalone K32 evidence") from err
    if P.canonical_json(reopened) != P.canonical_json(evidence):
        raise StandaloneError("published standalone K32 evidence changed")
    return evidence


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    evidence = produce()
    print(hashlib.sha256(P.canonical_json_line(evidence)).hexdigest())


if __name__ == "__main__":
    main()
