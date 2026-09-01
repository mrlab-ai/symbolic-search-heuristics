#!/usr/bin/env python3
"""Fail-closed structural audit for dual-metric campaign records."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_parser as Trace
import pdb_terminal_metric_choice_runner as Runner
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_transport as Transport


class AuditError(RuntimeError):
    pass


STRUCTURAL_FIELDS = (
    "dual_selector_structural_trace",
    "dual_selector_structural_trace_sha256",
    "dual_selector_pool_sha256",
    "dual_selector_normalized_pool",
    "dual_selector_normalized_pool_sha256",
    "dual_selector_state_profiles_sha256",
    "dual_selector_incidence_projection_sha256",
    "dual_selector_incidence_v3_projection_sha256",
    "dual_selector_preselection_sha256",
    "dual_selector_reference_identity",
    "dual_selector_incidence_winner_identity",
    "dual_selector_masked_joint_winner_identity",
    "dual_selector_incidence_and_mj_winners_differ",
    "dual_selector_work_signature",
    "dual_selector_probe_completed_layers",
)


def _standalone_identity(identity: dict) -> dict:
    try:
        return {
            key: identity[key] for key in (
                "pattern_index", "sources", "pattern", "value_cap",
            )
        }
    except (KeyError, TypeError) as err:
        raise AuditError("trace reference identity is incomplete") from err


def expected_run_properties(freeze: dict, freeze_sha256: str) -> dict:
    return Runner.build_manifest_properties(freeze, freeze_sha256)


def records_from_payload(payload) -> list[dict]:
    if isinstance(payload, list):
        records = payload
    elif isinstance(payload, dict):
        records = list(payload.values())
    else:
        raise AuditError("record payload is neither a list nor Lab properties")
    if any(not isinstance(record, dict) for record in records):
        raise AuditError("record payload contains a non-object")
    return records


def validate_scheduler_contract(contract: dict, freeze: dict) -> None:
    try:
        Transport.validate_scheduler_contract(contract, freeze, P.ACCOUNT)
    except Transport.TransportError as err:
        raise AuditError("scheduler contract is not 300 unthrottled triads")


def audit_records(
    records: list[dict], freeze: dict, freeze_sha256: str,
    standalone: dict,
) -> dict:
    P.validate_freeze(freeze, verify_live_sources=False)
    P.validate_standalone_evidence(
        standalone, freeze["base_confirmation_b"], freeze["planner"]
    )
    if not isinstance(records, list) or len(records) != P.CELL_COUNT:
        raise AuditError("campaign does not contain exactly 900 cells")
    expected_cells = {
        (row["algorithm"], row["domain"], row["problem"]): row
        for row in P.task_major_cell_mapping(
            freeze["base_confirmation_b"]["cohort"]["tasks"]
        )
    }
    expected_properties = expected_run_properties(freeze, freeze_sha256)
    standalone_by_task = {
        (row["domain"], row["problem"]): row
        for row in standalone["records"]
    }
    source_by_task = {
        (row["directory"], row["problem"]): row
        for row in freeze["base_confirmation_b"]["cohort"]["tasks"]
    }
    groups = defaultdict(list)
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            raise AuditError("campaign record is not an object")
        key = (record.get("algorithm"), record.get("domain"), record.get("problem"))
        if key in seen or key not in expected_cells:
            raise AuditError("campaign run identity changed or is duplicated")
        seen.add(key)
        expected = expected_cells[key]
        for field in (
            "run_id", "array_task", "family_sequence_index",
            "triad_position", "family",
        ):
            if field not in record or record[field] != expected[field]:
                raise AuditError("campaign run-cell mapping changed")
        source = source_by_task[(record["domain"], record["problem"])]
        if record["family"] != source["family"]:
            raise AuditError("campaign task family changed")
        source_fields = {
            "domain_source_path": source["domain_file"],
            "problem_source_path": source["problem_file"],
            "domain_source_sha256": source["domain_sha256"],
            "problem_source_sha256": source["problem_sha256"],
        }
        if any(record.get(field) != value for field, value in source_fields.items()):
            raise AuditError("campaign task source binding changed")
        for field, value in expected_properties.items():
            if record.get(field) != value:
                raise AuditError("campaign run provenance changed: {}".format(field))
        try:
            validate_scheduler_contract(record["scheduler_contract"], freeze)
        except (KeyError, TypeError) as err:
            raise AuditError("scheduler contract is absent") from err
        if any((
            record.get("id") != [
                record["algorithm"], record["domain"], record["problem"],
            ],
            record.get("component_options") != [
                "--search", P.SEARCHES[record["algorithm"]],
            ],
            record.get("driver_options") != [
                "--overall-time-limit", "{}s".format(P.TIME_LIMIT_SECONDS),
                "--overall-memory-limit", "{}M".format(P.MEMORY_LIMIT_MIB),
                "--build", P.BUILD_OPTIONS[0],
            ],
            record.get("build_options") != list(P.BUILD_OPTIONS),
            record.get("local_revision") != freeze["planner"]["revision"],
            record.get("global_revision") != freeze["planner"]["revision"],
        )):
            raise AuditError("campaign command provenance changed")
        if any((
            record.get("dual_selector_trace_schema") != P.DUAL_TRACE_SCHEMA,
            record.get("dual_selector_trace_certified") is not True,
            record.get("dual_selector_trace_status") != "complete",
            record.get("dual_selector_probe_completed_layers") != P.PROBE_LAYERS,
            any(field not in record for field in STRUCTURAL_FIELDS),
        )):
            raise AuditError("dual trace is not a complete certified certificate")
        try:
            replayed = Trace.certify_structural_trace(
                record["dual_selector_structural_trace"], record["algorithm"],
                record["dual_selector_selected_identity"],
            )
        except Trace.TraceError as err:
            raise AuditError("dual trace structural replay failed") from err
        replay_fields = {
            "structural_trace", "structural_trace_sha256", "pool_sha256",
            "normalized_pool", "normalized_pool_sha256",
            "state_profiles_sha256", "incidence_projection_sha256",
            "incidence_v3_projection_sha256", "preselection_sha256",
            "reference_identity", "incidence_winner_identity",
            "masked_joint_winner_identity", "selected_identity",
            "incidence_and_mj_winners_differ", "work_signature",
            "probe_completed_layers",
        }
        if any(
            record.get("dual_selector_" + field) != replayed[field]
            for field in replay_fields
        ):
            raise AuditError("dual trace parsed fields differ from replay")
        groups[(record["domain"], record["problem"])].append(record)
    if seen != set(expected_cells) or len(groups) != P.COHORT_TASKS:
        raise AuditError("campaign task coverage changed")

    differing = 0
    for task, triad in groups.items():
        triad.sort(key=lambda row: P.MODES.index(row["algorithm"]))
        if [row["algorithm"] for row in triad] != list(P.MODES):
            raise AuditError("task does not contain one exact three-mode triad")
        baseline = triad[0]
        for other in triad[1:]:
            for field in STRUCTURAL_FIELDS:
                if other[field] != baseline[field]:
                    raise AuditError(
                        "cross-arm structure differs for {}: {}".format(task, field)
                    )
        expected_selected = {
            P.INCIDENCE_MODE: baseline["dual_selector_incidence_winner_identity"],
            P.MJ_MODE: baseline["dual_selector_masked_joint_winner_identity"],
            P.MATCHED_MODE: baseline["dual_selector_reference_identity"],
        }
        for record in triad:
            if record.get("dual_selector_selected_identity") != expected_selected[
                record["algorithm"]
            ]:
                raise AuditError("arm selected an unauthorized final pointer")
        evidence = standalone_by_task.get(task)
        if evidence is None or evidence["family"] != source_by_task[task]["family"]:
            raise AuditError("standalone K32 task binding changed")
        if _standalone_identity(
            baseline["dual_selector_reference_identity"]
        ) != evidence["reference_identity"] or (
            baseline["dual_selector_normalized_pool"] != evidence["normalized_pool"]
        ) or baseline["dual_selector_normalized_pool_sha256"] != evidence[
            "normalized_pool_sha256"
        ]:
            raise AuditError("in-trace reference differs from standalone K32 evidence")
        if baseline["dual_selector_incidence_winner_identity"] != baseline[
            "dual_selector_masked_joint_winner_identity"
        ]:
            differing += 1
    return {
        "certified": True,
        "tasks": len(groups),
        "cells": len(records),
        "triads": len(groups),
        "differing_winner_tasks": differing,
        "run_cell_mapping_sha256": freeze["design"][
            "run_cell_mapping_sha256"
        ],
    }


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    args = parser.parse_args(argv)
    del args
    freeze = P.load_authorized_freeze(P.FREEZE_PATH)
    standalone = P.load_bound_standalone(freeze)
    freeze_sha = P.sha256_file(P.FREEZE_PATH, expected_path=P.FREEZE_PATH)
    try:
        payload = Runner.load_fetched_properties(freeze_sha)
    except Runner.RunnerError as err:
        raise AuditError("cannot load exact campaign properties") from err
    records = records_from_payload(payload)
    result = audit_records(
        records, freeze,
        freeze_sha, standalone,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
