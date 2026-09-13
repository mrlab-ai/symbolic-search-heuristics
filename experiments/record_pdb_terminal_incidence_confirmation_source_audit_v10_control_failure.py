#!/usr/bin/env python3
"""Seal the retained V10 singleton-JobID controller failure without a query."""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

import launch_pdb_terminal_incidence_confirmation_source_audit_v10 as L


class FailureRecordError(RuntimeError):
    pass


FAILURE_RECORD = (
    L.PREFLIGHT_ARTIFACT_DIR / "compute-canary-control-failure-v10.json"
)
SCHEMA = L.PREFLIGHT_SCHEMA + "/compute-canary-control-failure/v1"


def _artifact(path: Path, label: str) -> dict:
    raw = L._retained_poll_bytes(path, label)
    return {
        "path": path.relative_to(L.REPO).as_posix(),
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def record_failure(path: Path = FAILURE_RECORD) -> dict:
    launch_sha, receipt, accepted = L._load_compute_launch()
    manifest_sha, _records = L._load_code_manifest()
    if manifest_sha != receipt["code_manifest_sha256"]:
        raise FailureRecordError("V10 launch and source manifest disagree")
    job_name, _comment = L._canary_submission_identity(
        receipt["submission_token"]
    )
    kwargs = {
        "directory": L.COMPUTE_CANARY_POLL_DIR,
        "campaign": L.Source.COMPUTE_CANARY_CAMPAIGN,
        "poll_schema": L.PREFLIGHT_SCHEMA + "/compute-canary-poll/v1",
        "task_count": 1,
        "launch_sha": launch_sha,
        "launch_accepted_utc": accepted,
        "job_id": receipt["job_id"],
        "job_name": job_name,
    }
    index, previous_sha, previous, stranded = L._validated_poll_sequence(
        **kwargs
    )
    if (
        index != 1
        or stranded is not None
        or previous is None
        or previous.get("outcome") != "abandoned-unknown"
        or previous.get("authorizing") is not False
        or previous.get("scheduler_queries_during_recovery") != 0
        or not isinstance(previous_sha, str)
        or not previous_sha
        or L.COMPUTE_CANARY_TERMINAL_RECEIPT.exists()
    ):
        raise FailureRecordError("V10 failed poll is not durably abandoned")

    poll = L._poll_paths(L.COMPUTE_CANARY_POLL_DIR, 0)
    intent_raw, intent = L._retained_poll_json(
        poll["intent"], "V10 failed poll intent"
    )
    _result_raw, result = L._retained_poll_json(
        poll["result"], "V10 failed poll result"
    )
    stdout = L._retained_poll_bytes(
        poll["stdout"], "V10 failed poll stdout"
    )
    stderr = L._retained_poll_bytes(
        poll["stderr"], "V10 failed poll stderr"
    )
    L._validate_poll_result(
        result,
        index=0,
        campaign=L.Source.COMPUTE_CANARY_CAMPAIGN,
        poll_schema=L.PREFLIGHT_SCHEMA + "/compute-canary-poll/v1",
        intent_sha=hashlib.sha256(intent_raw).hexdigest(),
        intent=intent,
        paths=poll,
        stdout=stdout,
        stderr=stderr,
        require_success=True,
    )
    try:
        line = stdout.decode("ascii").rstrip("\n")
    except UnicodeDecodeError as err:
        raise FailureRecordError("V10 scheduler row is not ASCII") from err
    fields = line.split("|")
    expected = [
        receipt["job_id"], L.ACCOUNT, L.PARTITION, L.QOS, "1", L.MEMORY,
        L.TIME_LIMIT, "COMPLETED", "0:0", "0", job_name,
    ]
    if fields != expected or stderr:
        raise FailureRecordError(
            "V10 retained row is not the exact successful singleton row"
        )
    try:
        L._parse_combined_scheduler_rows(
            stdout,
            job_id=receipt["job_id"],
            task_count=1,
            job_name=job_name,
        )
    except L.LaunchAuditError as err:
        if str(err) != "V10 scheduler resource contract changed":
            raise FailureRecordError(
                "V10 parser failed for an unexpected reason"
            ) from err
    else:
        raise FailureRecordError("V10 parser no longer reproduces the failure")

    artifacts = {
        name: _artifact(poll[name], "V10 failed poll " + name)
        for name in ("intent", "stdout", "stderr", "result", "abandoned")
    }
    value = {
        "schema": SCHEMA,
        "campaign": L.Source.COMPUTE_CANARY_CAMPAIGN,
        "recorded_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).replace(microsecond=0).isoformat(),
        "job_id": receipt["job_id"],
        "source_repository_commit_id": receipt["repository_commit_id"],
        "code_manifest_sha256": manifest_sha,
        "compute_canary_launch_receipt_sha256": launch_sha,
        "abandoned_poll_receipt_sha256": previous_sha,
        "retained_poll_artifacts": artifacts,
        "retained_poll_artifacts_sha256": L._digest(artifacts),
        "observed_job_id_raw": fields[0],
        "expected_array_task": 0,
        "expected_array_tasks": 1,
        "scheduler_state": fields[7],
        "scheduler_exit_code": fields[8],
        "scheduler_restarts": 0,
        "scientific_compute_completed_successfully": True,
        "determination": "controller-rejected-bare-singleton-job-id",
        "controller_parser_required_index_suffix": True,
        "scheduler_queries_total": 1,
        "scheduler_queries_during_abandonment": 0,
        "worker_payload_paths_read": [],
        "worker_payload_bytes_read": 0,
        "worker_payloads_reused": 0,
        "compute_canary_authorized": False,
        "full_launch_authorized": False,
        "v10_burned": True,
    }
    L._exclusive_json(path, value, "V10 compute-canary control failure")
    print(json.dumps({
        "failure_record": str(path),
        "determination": value["determination"],
        "scheduler_queries_during_recording": 0,
        "worker_payload_bytes_read": 0,
        "v10_burned": True,
    }, sort_keys=True, indent=2))
    return value


if __name__ == "__main__":
    try:
        record_failure()
    except (FailureRecordError, L.LaunchAuditError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
