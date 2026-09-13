#!/usr/bin/env python3
"""Record the terminal scheduler failure of the immutable V8 repair.

This command is deliberately scheduler-only.  It authenticates the retained
V8 launch materials, asks for the 25 array rows exactly once, and publishes a
single exclusive failure receipt.  It never opens a V5/V8 task payload, task
log, task-environment record, or scientific output.
"""

from __future__ import annotations

import argparse
import copy
import datetime
import hashlib
import json
import os
from collections import Counter
from pathlib import Path

import jj_cached_revision as JJ
import launch_pdb_terminal_incidence_confirmation_source_audit_v8 as V8


class FailureRecorderError(RuntimeError):
    pass


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
SCHEMA = V8.EXECUTION_SCHEMA + "/terminal-failure/v1"
FAILURE_RECEIPT = (
    V8.ARTIFACT_DIR / "source-audit-terminal-failure-receipt-v8.json"
)
SUCCESSOR_PROTOCOL = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v9_protocol.md"
)
EXPECTED_REPAIR_TASKS = 25
EXPECTED_SUCCESSOR_CANDIDATES = 1640
EXPECTED_STATE_COUNTS = {"COMPLETED": 8, "OUT_OF_MEMORY": 17}
FORBIDDEN_SEAL_ARTIFACTS = (
    V8.EXECUTION_RECEIPT,
    V8.SEAL_PLAN,
    V8.UNION_ROOT_STAGE,
    V8.UNION_STAGE,
    V8.CANDIDATE_STAGE,
    V8.ATTESTATION_STAGE,
    V8.UNION_DIR,
    V8.CANDIDATE,
    V8.ATTESTATION,
)


def _canonical_json(value) -> bytes:
    return V8._canonical_json(value)


def _digest(value) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _relative(path: Path) -> str:
    absolute = Path(os.path.abspath(path))
    try:
        return absolute.relative_to(REPO).as_posix()
    except ValueError as err:
        raise FailureRecorderError("V8 launch material escapes repository") from err


def _material_record(path: Path, raw: bytes) -> dict:
    return {
        "path": _relative(path),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _safe_file(path: Path, label: str):
    try:
        return V8.Runtime._safe_file(Path(path), label, root=REPO)
    except V8.LaunchAuditError as err:
        raise FailureRecorderError(str(err)) from err


def _canonical_json_file(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        return V8.Runtime._load_json(Path(path), label)
    except V8.LaunchAuditError as err:
        raise FailureRecorderError(str(err)) from err


def _assert_failure_namespace_clear() -> None:
    if os.path.lexists(FAILURE_RECEIPT):
        raise FailureRecorderError("V8 terminal-failure receipt already exists")
    if any(os.path.lexists(path) for path in FORBIDDEN_SEAL_ARTIFACTS):
        raise FailureRecorderError(
            "V8 seal, attestation, stage, or scientific output already exists"
        )


def _require_clean_parent() -> str:
    try:
        if JJ.live_working_copy_diff_summary(REPO):
            raise FailureRecorderError(
                "V8 failure recording requires a clean empty working-copy commit"
            )
        parent = JJ.parent_commit(REPO)
        bound_files = (
            (Path(__file__), "V8 failure recorder source"),
            (SUCCESSOR_PROTOCOL, "frozen V9 successor protocol"),
        )
        for path, label in bound_files:
            source = _safe_file(path, label)
            tracked_sha = JJ.tracked_file_sha256(
                REPO, parent, _relative(path)
            )
            if tracked_sha != source.sha256:
                raise FailureRecorderError(
                    "V8 failure recorder and V9 protocol must be committed "
                    "at the clean parent"
                )
    except JJ.JjCacheError as err:
        raise FailureRecorderError(
            "cannot resolve the clean Jujutsu parent"
        ) from err
    if JJ.COMMIT_RE.fullmatch(parent) is None:
        raise FailureRecorderError(
            "V8 failure recorder and V9 protocol must be committed at the "
            "clean parent"
        )
    return parent


def _successor_record(recorder_revision: str) -> dict:
    protocol = _safe_file(SUCCESSOR_PROTOCOL, "frozen V9 successor protocol")
    try:
        tracked_sha = JJ.tracked_file_sha256(
            REPO, recorder_revision, _relative(SUCCESSOR_PROTOCOL)
        )
    except JJ.JjCacheError as err:
        raise FailureRecorderError(
            "cannot bind the frozen V9 successor protocol"
        ) from err
    if tracked_sha != protocol.sha256:
        raise FailureRecorderError(
            "frozen V9 successor protocol changed after commit"
        )
    if V8.Source.CANDIDATE_COUNT != EXPECTED_SUCCESSOR_CANDIDATES:
        raise FailureRecorderError("frozen V9 successor candidate count changed")
    candidate_indices = list(range(EXPECTED_SUCCESSOR_CANDIDATES))
    return {
        "campaign": "v9-full-census",
        "protocol": _material_record(SUCCESSOR_PROTOCOL, protocol.raw),
        "candidate_index_first": candidate_indices[0],
        "candidate_index_last": candidate_indices[-1],
        "candidate_count": len(candidate_indices),
        "candidate_indices_sha256": _digest(candidate_indices),
        "frozen_before_v8_scheduler_query": True,
        "candidate_set_independent_of_v8_scheduler_rows": True,
        "v1_through_v8_runtime_payload_reuse_authorized": False,
    }


def _load_authenticated_launch_materials() -> dict:
    """Load V8 launch evidence without returning any raw sensitive bytes."""
    try:
        launch_sha, launch, diagnostic = V8._load_launch()
    except (V8.LaunchAuditError, V8.Source.SourceAuditError) as err:
        raise FailureRecorderError(str(err)) from err

    intent_raw, _intent = _canonical_json_file(V8.INTENT, "V8 launch intent")
    receipt_raw, receipt = _canonical_json_file(
        V8.LAUNCH_RECEIPT, "V8 launch receipt"
    )
    result_raw, result = _canonical_json_file(
        V8.SBATCH_RESULT, "V8 sbatch result"
    )
    manifest = _safe_file(V8.CODE_MANIFEST, "V8 code manifest")
    inventory_raw, inventory = _canonical_json_file(
        V8.SOURCE_INVENTORY, "V8 source inventory"
    )
    try:
        inventory_records = V8.Source.validate_inventory_manifest(inventory)
    except V8.Source.SourceAuditError as err:
        raise FailureRecorderError(str(err)) from err

    if (
        type(inventory_records) is not list
        or len(inventory_records) != V8.Source.CANDIDATE_COUNT
        or receipt != launch
        or hashlib.sha256(receipt_raw).hexdigest() != launch_sha
        or hashlib.sha256(intent_raw).hexdigest()
        != launch.get("launch_intent_sha256")
        or hashlib.sha256(result_raw).hexdigest()
        != launch.get("sbatch_result_sha256")
        or manifest.sha256 != launch.get("code_manifest_sha256")
        or hashlib.sha256(inventory_raw).hexdigest()
        != launch.get("source_inventory_sha256")
    ):
        raise FailureRecorderError("authenticated V8 launch material changed")

    materials = [
        _material_record(V8.INTENT, intent_raw),
        _material_record(V8.LAUNCH_RECEIPT, receipt_raw),
        _material_record(V8.CODE_MANIFEST, manifest.raw),
        _material_record(V8.SOURCE_INVENTORY, inventory_raw),
        _material_record(V8.SBATCH_RESULT, result_raw),
    ]
    for stream, path in (
        ("stdout", V8.SBATCH_STDOUT),
        ("stderr", V8.SBATCH_STDERR),
    ):
        capture = _safe_file(path, "V8 raw sbatch {} capture".format(stream))
        recorded = result.get(stream) if type(result) is dict else None
        if (
            type(recorded) is not dict
            or recorded.get("path") != str(path)
            or recorded.get("bytes") != len(capture.raw)
            or recorded.get("sha256") != capture.sha256
        ):
            raise FailureRecorderError("V8 raw sbatch capture changed")
        materials.append(_material_record(path, capture.raw))

    return {
        "launch": launch,
        "diagnostic": diagnostic,
        "launch_materials": materials,
        "source_inventory_record_count": len(inventory_records),
    }


def _require_launch_lineage(launch: dict, recorder_revision: str) -> None:
    launch_revision = launch.get("repository_commit_id")
    if (
        not isinstance(launch_revision, str)
        or JJ.COMMIT_RE.fullmatch(launch_revision) is None
    ):
        raise FailureRecorderError("V8 launch repository revision changed")
    try:
        JJ.require_ancestor(REPO, launch_revision, recorder_revision)
    except JJ.JjCacheError as err:
        raise FailureRecorderError(
            "V8 launch revision is not an ancestor of the recorder revision"
        ) from err


def _requested_resource_profile(launch: dict) -> dict:
    expected_mapping = V8._resource_mapping()
    expected = {
        "array": launch.get("array"),
        "array_tasks": EXPECTED_REPAIR_TASKS,
        "array_throttle": 0,
        "partition": V8.PARTITION,
        "qos": V8.QOS,
        "account": V8.ACCOUNT,
        "cpus_per_task": V8.CPUS_PER_TASK,
        "resource_mapping": expected_mapping,
    }
    if (
        launch.get("array_throttle") != 0
        or launch.get("partition") != V8.PARTITION
        or launch.get("qos") != V8.QOS
        or launch.get("account") != V8.ACCOUNT
        or launch.get("cpus_per_task") != V8.CPUS_PER_TASK
        or launch.get("resource_mapping") != expected_mapping
        or not isinstance(launch.get("array"), str)
        or "%" in launch["array"]
    ):
        raise FailureRecorderError("authenticated V8 resource profile changed")
    return expected


def _validate_failure_rows(rows, expected_tasks: list[int]) -> dict:
    if (
        type(expected_tasks) is not list
        or len(expected_tasks) != EXPECTED_REPAIR_TASKS
        or expected_tasks != sorted(set(expected_tasks))
        or any(
            type(index) is not int or not 0 <= index < V8.ARRAY_TASKS
            for index in expected_tasks
        )
        or type(rows) is not list
        or len(rows) != EXPECTED_REPAIR_TASKS
    ):
        raise FailureRecorderError("V8 terminal scheduler census is malformed")

    for expected_task, row in zip(expected_tasks, rows):
        if (
            type(row) is not dict
            or set(row) != {"array_task", "state", "exit_code", "partition"}
            or row.get("array_task") != expected_task
            or row.get("partition") != V8.PARTITION
            or row.get("state") not in EXPECTED_STATE_COUNTS
            or not isinstance(row.get("exit_code"), str)
            or V8.EXIT_CODE_RE.fullmatch(row.get("exit_code", "")) is None
            or (
                row.get("state") == "COMPLETED"
                and row.get("exit_code") != "0:0"
            )
        ):
            raise FailureRecorderError("V8 terminal scheduler census is malformed")

    all_success = all(
        row["state"] == "COMPLETED" and row["exit_code"] == "0:0"
        for row in rows
    )
    if all_success:
        raise FailureRecorderError("an all-success V8 cannot be recorded as failed")

    state_counts = dict(sorted(Counter(row["state"] for row in rows).items()))
    if state_counts != EXPECTED_STATE_COUNTS:
        raise FailureRecorderError("V8 terminal scheduler aggregate changed")
    state_exit_counts = [
        {"state": state, "exit_code": exit_code, "count": count}
        for (state, exit_code), count in sorted(Counter(
            (row["state"], row["exit_code"]) for row in rows
        ).items())
    ]
    return {
        "all_success": False,
        "state_counts": state_counts,
        "state_exit_counts": state_exit_counts,
    }


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )


def _publish_receipt(receipt: dict) -> str:
    raw = _canonical_json(receipt)
    try:
        return V8.SelectedIO.atomic_exclusive_bytes(
            FAILURE_RECEIPT,
            raw,
            "V8 terminal-failure receipt",
            root=REPO,
        )
    except V8.SelectedIO.PublicationError as err:
        raise FailureRecorderError(str(err)) from err


def record_failure() -> tuple[str, dict]:
    _assert_failure_namespace_clear()
    recorder_revision = _require_clean_parent()
    authenticated = _load_authenticated_launch_materials()
    launch = authenticated["launch"]
    diagnostic = authenticated["diagnostic"]
    _require_launch_lineage(launch, recorder_revision)
    resources = _requested_resource_profile(launch)
    successor = _successor_record(recorder_revision)

    expected_tasks = diagnostic.get("repair_v5_shard_indices")
    if (
        expected_tasks != launch.get("repair_v5_shard_indices")
        or type(expected_tasks) is not list
        or len(expected_tasks) != EXPECTED_REPAIR_TASKS
    ):
        raise FailureRecorderError("V8 repair task set changed")

    # This is the recorder's sole scheduler query.  Do not replace it with
    # status(), which would obscure the one-query evidence boundary.
    rows = V8._v8_scheduler_rows(launch["job_id"], expected_tasks)
    aggregate = _validate_failure_rows(rows, expected_tasks)
    _assert_failure_namespace_clear()

    launch_materials = authenticated["launch_materials"]
    receipt = {
        "schema": SCHEMA,
        "recorded_utc": _utc_now(),
        "recorder_repository_revision": recorder_revision,
        "v8_launch_repository_revision": launch["repository_commit_id"],
        "v8_job_id": launch["job_id"],
        "campaign": "v8-selective-repair",
        "determination": "terminal-v8-array-failed-all-success-gate",
        "requested_resource_profile": copy.deepcopy(resources),
        "scheduler_query_count": 1,
        "scheduler_rows": copy.deepcopy(rows),
        "scheduler_rows_sha256": _digest(rows),
        "scheduler_state_counts": aggregate["state_counts"],
        "scheduler_state_exit_counts": aggregate["state_exit_counts"],
        "scheduler_all_success": aggregate["all_success"],
        "launch_materials": copy.deepcopy(launch_materials),
        "launch_materials_sha256": _digest(launch_materials),
        "source_inventory_record_count": authenticated[
            "source_inventory_record_count"
        ],
        "frozen_successor": copy.deepcopy(successor),
        "raw_launch_material_contents_recorded": False,
        "v5_or_v8_task_payload_read": False,
        "v5_or_v8_task_log_read": False,
        "v5_or_v8_task_environment_record_read": False,
        "v5_or_v8_scientific_output_read": False,
        "v5_or_v8_scientific_output_reused": False,
        "v5_or_v8_payload_log_environment_or_scientific_output_read": False,
        "v5_or_v8_payload_log_environment_or_scientific_output_reused": False,
        "v8_partial_output_reuse_authorized": False,
        "v8_burned": True,
        "v8_resubmission_authorized": False,
        "v8_source_audit_complete": False,
        "confirmation_prelaunch_authorized": False,
        "confirmation_a_prelaunch_authorized": False,
    }
    digest = _publish_receipt(receipt)
    print(json.dumps({
        "failure_receipt_sha256": digest,
        "scheduler_state_counts": aggregate["state_counts"],
        "v8_burned": True,
        "confirmation_a_prelaunch_authorized": False,
    }, sort_keys=True, indent=2))
    return digest, receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("record",))
    parser.parse_args(argv)
    record_failure()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except FailureRecorderError as err:
        print("error: {}".format(err), file=os.sys.stderr)
        raise SystemExit(2)
