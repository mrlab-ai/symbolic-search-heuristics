#!/usr/bin/env python3
"""Record a terminal failure of the immutable V9 outer array.

The command authenticates only committed launch and source material, performs
one scheduler-only census, and publishes one exclusive failure receipt.  It
does not inspect or enumerate V9 worker logs, task environments, temporary
directories, shards, or scientific payloads.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import stat
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Callable

from pdb_terminal_incidence_v9_snapshot_reader import (
    SnapshotReaderError,
    read_committed_snapshot,
)


class FailureRecorderError(RuntimeError):
    pass


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v9"
)
FAILURE_RECEIPT = (
    ARTIFACT_DIR / "source-audit-terminal-failure-receipt-v9.json"
)
PRIOR_QUERY_ATTEMPT_RELATIVE = (
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v9/"
    "source-audit-scheduler-query-attempt-v9-001.json"
)
PRIOR_QUERY_ATTEMPT = REPO / PRIOR_QUERY_ATTEMPT_RELATIVE
QUERY_INTENT = (
    ARTIFACT_DIR / "source-audit-scheduler-query-intent-v9-002.json"
)
SCHEDULER_STDOUT = (
    ARTIFACT_DIR / "source-audit-scheduler-stdout-v9-002.bin"
)
EXPECTED_PRIOR_QUERY_ATTEMPT_SHA256 = (
    "36aa3614f25f93471869e9e3420e6ee084fe517b9245c7b616a6b3b9e4f0f04c"
)
EARLIEST_SECOND_RECORDER_QUERY_UTC = "2026-09-13T18:00:36+00:00"
SCHEMA = (
    "symbolic-search-heuristics/"
    "universal-unseen-confirmation-source-audit/v1/campaign-v9/"
    "execution/v1/terminal-failure/v1"
)

EXPECTED_JOB_ID = "2358308"
EXPECTED_ARRAY_TASKS = 820
EXPECTED_SOURCE_FILES = 54
EXPECTED_SOURCE_REVISION = "3ad761ae5426d092d76249b0588bcbfffbd53c0e"
EXPECTED_LAUNCH_REVISION = "4a4a6dfc235e96075addf62248d2e0b63a7b25f3"
EXPECTED_LAUNCH_RECEIPT_SHA256 = (
    "eaacaaba8974a22cf63d82c684a1605b45dabe6bd44affb62692cc6f578bfd91"
)
EXPECTED_CODE_MANIFEST_SHA256 = (
    "927c27d6fea55bcf679cdf3f41c6f6b33d7aa7541019064b78b029591d823ed0"
)
EXPECTED_SOURCE_INVENTORY_SHA256 = (
    "aff2e8b2762279d84961e6775436c994eba71ead86ae946a3ad45e53eb2976ef"
)
EXPECTED_RESOURCE_PROFILE = {
    "account": "naiss2025-5-561-cpu",
    "partition": "fat",
    "qos": "normal",
    "nodes": 1,
    "ntasks": 1,
    "cpus_per_task": 1,
    "mem": "26G",
    "time": "01:10:00",
    "array": "0-819",
    "array_throttle": None,
    "nice": 0,
    "requeue": False,
    "export": "NONE",
}

LAUNCH_ARTIFACT_PATHS = (
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v9/"
    "source-audit-launch-intent-v9.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v9/"
    "source-audit-sbatch-stdout-v9.bin",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v9/"
    "source-audit-sbatch-stderr-v9.bin",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v9/"
    "source-audit-sbatch-result-v9.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v9/"
    "source-audit-launch-receipt-v9.json",
)
EXPECTED_LAUNCH_ARTIFACT_SHA256 = dict(zip(
    LAUNCH_ARTIFACT_PATHS,
    (
        "77c670f4fd9802eb36138a025a95f2401d7421e1a553a9c4d9f09837e2d9aaa3",
        "7498fd668044388e76384302d7bcd04d1b3d159c7117ab03abd5f9843906f201",
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        "66f57fd7fd1b6ff440d1636228f69ab76f71a090605b7f482d2dd93c1a1d0c9b",
        EXPECTED_LAUNCH_RECEIPT_SHA256,
    ),
))
SOURCE_MANIFEST_PATH = (
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v9_code.sha256"
)
RECORDER_BOUND_PATHS = (
    "experiments/record_pdb_terminal_incidence_confirmation_source_audit_v9_failure.py",
    "experiments/pdb_terminal_incidence_v9_snapshot_reader.py",
    PRIOR_QUERY_ATTEMPT_RELATIVE,
)
REQUIRED_SOURCE_PATHS = frozenset({
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v9.py",
    "experiments/jj_cached_revision.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v9.py",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v9.slurm",
})
FORBIDDEN_SEAL_ARTIFACTS = tuple(
    ARTIFACT_DIR / name for name in (
        "source-audit-seal-plan-v9.json",
        "source-audit-tree-stage-v9.json",
        "source-audit-census-stage-v9.json",
        "source-audit-split-stage-v9.json",
        "source-audit-attestation-stage-v9.json",
        "source-audit-attestation-v9.json",
        "source-audit-execution-receipt-v9.json",
    )
)

SACCT_COMMAND = Path("/usr/bin/sacct")
SACCT_FIELDS = (
    "JobID,State,ExitCode,Reason,ElapsedRaw,Partition,Restarts"
)
CONTROLLED_ENVIRONMENT = {
    "LANG": "C",
    "LC_ALL": "C",
    "PATH": "/usr/bin:/bin",
}
JJ_COMMAND = Path("/home/jendrik/bin/jj")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
EXIT_CODE_RE = re.compile(r"^[0-9]+:[0-9]+$")
PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
STATE_RE = re.compile(r"^(CANCELLED)(?: by [0-9]+)?$")
ACTIVE_STATES = frozenset({
    "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
    "RESIZING", "SUSPENDED", "STAGE_OUT",
})
TERMINAL_STATES = frozenset({
    "BOOT_FAIL", "CANCELLED", "COMPLETED", "DEADLINE", "FAILED",
    "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "REVOKED",
    "SPECIAL_EXIT", "TIMEOUT",
})

SnapshotReader = Callable[[str, list[str]], dict[str, bytes]]
SchedulerQuery = Callable[[list[str]], bytes]


def _canonical_json(value) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise FailureRecorderError("value is not canonical finite JSON") from err


def _digest(value) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _json_bytes(raw: bytes, label: str) -> dict:
    if type(raw) is not bytes:
        raise FailureRecorderError(label + " is not immutable bytes")
    try:
        value = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise FailureRecorderError(label + " is not canonical JSON") from err
    if type(value) is not dict or _canonical_json(value) != raw:
        raise FailureRecorderError(label + " is not canonical JSON")
    return value


def _material(path: str, raw: bytes) -> dict:
    return {
        "path": path,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _snapshot(
    reader: SnapshotReader, revision: str, paths: list[str], label: str,
) -> dict[str, bytes]:
    try:
        result = reader(revision, paths)
    except (OSError, SnapshotReaderError) as err:
        raise FailureRecorderError("cannot read committed " + label) from err
    if (
        type(result) is not dict
        or list(result) != paths
        or any(type(raw) is not bytes for raw in result.values())
    ):
        raise FailureRecorderError("committed " + label + " closure changed")
    return result


def _parse_source_manifest(raw: bytes) -> list[dict]:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as err:
        raise FailureRecorderError("V9 source manifest is not ASCII") from err
    if not text.endswith("\n"):
        raise FailureRecorderError("V9 source manifest is malformed")
    records = []
    for line in text.splitlines():
        fields = line.split("  ", 1)
        if len(fields) != 2:
            raise FailureRecorderError("V9 source manifest is malformed")
        digest, path = fields
        pure = PurePosixPath(path)
        if (
            SHA256_RE.fullmatch(digest) is None
            or PATH_RE.fullmatch(path) is None
            or pure.is_absolute()
            or pure.as_posix() != path
            or any(part in ("", ".", "..") for part in pure.parts)
            or pure.parts[0] in (".git", ".jj")
            or path.startswith("experiments/data/")
            or path.startswith("experiments/artifacts/")
        ):
            raise FailureRecorderError("V9 source manifest is malformed")
        records.append({"path": path, "sha256": digest})
    paths = [record["path"] for record in records]
    if (
        len(records) != EXPECTED_SOURCE_FILES
        or paths != sorted(set(paths))
        or not REQUIRED_SOURCE_PATHS <= set(paths)
    ):
        raise FailureRecorderError("V9 source manifest closure changed")
    return records


def _load_authenticated_launch_materials(
    snapshot_reader: SnapshotReader,
) -> dict:
    launch = _snapshot(
        snapshot_reader,
        EXPECTED_LAUNCH_REVISION,
        list(LAUNCH_ARTIFACT_PATHS),
        "V9 launch artifacts",
    )
    launch_records = [_material(path, launch[path]) for path in LAUNCH_ARTIFACT_PATHS]
    if any(
        record["sha256"] != EXPECTED_LAUNCH_ARTIFACT_SHA256[record["path"]]
        for record in launch_records
    ):
        raise FailureRecorderError("committed V9 launch artifact changed")

    intent_path, stdout_path, stderr_path, result_path, receipt_path = (
        LAUNCH_ARTIFACT_PATHS
    )
    intent = _json_bytes(launch[intent_path], "V9 launch intent")
    result = _json_bytes(launch[result_path], "V9 sbatch result")
    receipt = _json_bytes(launch[receipt_path], "V9 launch receipt")
    if (
        hashlib.sha256(launch[receipt_path]).hexdigest()
        != EXPECTED_LAUNCH_RECEIPT_SHA256
        or receipt.get("campaign") != "v9-full-census"
        or receipt.get("job_id") != EXPECTED_JOB_ID
        or receipt.get("repository_commit_id") != EXPECTED_SOURCE_REVISION
        or receipt.get("resource_profile") != EXPECTED_RESOURCE_PROFILE
        or receipt.get("launch_intent_sha256")
        != hashlib.sha256(launch[intent_path]).hexdigest()
        or receipt.get("sbatch_result_sha256")
        != hashlib.sha256(launch[result_path]).hexdigest()
        or receipt.get("code_manifest_sha256")
        != EXPECTED_CODE_MANIFEST_SHA256
        or receipt.get("source_inventory_sha256")
        != EXPECTED_SOURCE_INVENTORY_SHA256
        or receipt.get("launch_recovered") is not False
        or receipt.get("recovery_evidence") is not None
        or receipt.get("whole_campaign_fresh") is not True
        or receipt.get("selective_recovery_authorized") is not False
        or any(receipt.get(key) != 0 for key in (
            "prior_runtime_payloads_read",
            "prior_runtime_payload_bytes_read",
            "prior_runtime_payloads_reused",
        ))
        or intent.get("campaign") != "v9-full-census"
        or intent.get("repository_commit_id") != EXPECTED_SOURCE_REVISION
        or intent.get("resource_profile") != EXPECTED_RESOURCE_PROFILE
        or intent.get("code_manifest_sha256") != EXPECTED_CODE_MANIFEST_SHA256
        or intent.get("source_inventory_sha256")
        != EXPECTED_SOURCE_INVENTORY_SHA256
        or result.get("launch_intent_sha256")
        != hashlib.sha256(launch[intent_path]).hexdigest()
        or result.get("parsed_job_id") != EXPECTED_JOB_ID
        or result.get("accepted_by_launcher") is not True
        or result.get("raw_streams_preserved") is not True
    ):
        raise FailureRecorderError("committed V9 launch binding changed")
    for stream, path in (("stdout", stdout_path), ("stderr", stderr_path)):
        record = result.get(stream)
        if (
            type(record) is not dict
            or record.get("bytes") != len(launch[path])
            or record.get("sha256") != hashlib.sha256(launch[path]).hexdigest()
        ):
            raise FailureRecorderError("committed V9 sbatch capture changed")

    manifest_snapshot = _snapshot(
        snapshot_reader,
        EXPECTED_SOURCE_REVISION,
        [SOURCE_MANIFEST_PATH],
        "V9 source manifest",
    )
    manifest_raw = manifest_snapshot[SOURCE_MANIFEST_PATH]
    if hashlib.sha256(manifest_raw).hexdigest() != EXPECTED_CODE_MANIFEST_SHA256:
        raise FailureRecorderError("committed V9 source manifest changed")
    source_records = _parse_source_manifest(manifest_raw)
    source_paths = [record["path"] for record in source_records]
    sources = _snapshot(
        snapshot_reader,
        EXPECTED_SOURCE_REVISION,
        source_paths,
        "V9 source files",
    )
    if any(
        hashlib.sha256(sources[record["path"]]).hexdigest() != record["sha256"]
        for record in source_records
    ):
        raise FailureRecorderError("committed V9 source file changed")

    return {
        "launch_receipt": _material(receipt_path, launch[receipt_path]),
        "launch_materials": launch_records,
        "launch_materials_sha256": _digest(launch_records),
        "source_manifest": _material(SOURCE_MANIFEST_PATH, manifest_raw),
        "source_files": source_records,
        "source_files_sha256": _digest(source_records),
    }


def _jj_output(args: list[str]) -> str:
    try:
        return subprocess.check_output(
            [str(JJ_COMMAND), "--no-pager", *args],
            cwd=REPO,
            env=dict(CONTROLLED_ENVIRONMENT),
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise FailureRecorderError("cannot authenticate recorder revision") from err


def _live_source(path: Path) -> bytes:
    try:
        before = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(before.st_mode):
            raise FailureRecorderError("recorder source is not a regular file")
        raw = path.read_bytes()
        after = path.lstat()
    except OSError as err:
        raise FailureRecorderError("cannot read recorder source") from err
    identity = lambda info: (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns,
    )
    if identity(before) != identity(after) or len(raw) != after.st_size:
        raise FailureRecorderError("recorder source changed while read")
    return raw


def _require_committed_recorder(snapshot_reader: SnapshotReader) -> str:
    if _jj_output(["diff", "--summary", "-r", "@"]).strip():
        raise FailureRecorderError(
            "V9 failure recording requires a clean empty working-copy commit"
        )
    revision = _jj_output([
        "log", "-r", "@-", "--no-graph", "-T", 'commit_id ++ "\\n"',
    ]).strip()
    if COMMIT_RE.fullmatch(revision or "") is None:
        raise FailureRecorderError("cannot resolve committed recorder revision")
    committed = _snapshot(
        snapshot_reader, revision, list(RECORDER_BOUND_PATHS),
        "V9 failure-recorder source",
    )
    for relative in RECORDER_BOUND_PATHS:
        if committed[relative] != _live_source(REPO / relative):
            raise FailureRecorderError("V9 failure-recorder source is not committed")
    return revision


def _require_ancestor(ancestor: str, descendant: str) -> None:
    if (
        COMMIT_RE.fullmatch(ancestor or "") is None
        or COMMIT_RE.fullmatch(descendant or "") is None
    ):
        raise FailureRecorderError("V9 recorder lineage is malformed")
    output = _jj_output([
        "log", "-r", ancestor + " & ::" + descendant,
        "--no-graph", "-T", 'commit_id ++ "\\n"',
    ]).splitlines()
    if output != [ancestor]:
        raise FailureRecorderError("V9 recorder lineage changed")


def _require_lineage(recorder_revision: str) -> None:
    _require_ancestor(EXPECTED_SOURCE_REVISION, EXPECTED_LAUNCH_REVISION)
    _require_ancestor(EXPECTED_LAUNCH_REVISION, recorder_revision)


def _sacct_command() -> list[str]:
    return [
        str(SACCT_COMMAND),
        "-j", EXPECTED_JOB_ID,
        "-X",
        "--array",
        "-n",
        "-P",
        "--format=" + SACCT_FIELDS,
    ]


def _run_sacct(command: list[str]) -> bytes:
    if command != _sacct_command():
        raise FailureRecorderError("V9 scheduler command changed")
    try:
        completed = subprocess.run(
            command,
            cwd=REPO,
            env=dict(CONTROLLED_ENVIRONMENT),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as err:
        raise FailureRecorderError("cannot query V9 accounting") from err
    if (
        type(completed.returncode) is not int
        or type(completed.stdout) is not bytes
        or type(completed.stderr) is not bytes
        or completed.returncode != 0
        or completed.stderr
    ):
        raise FailureRecorderError("V9 accounting query failed")
    return completed.stdout


def _normalized_state(raw: str) -> str:
    if raw in ACTIVE_STATES | TERMINAL_STATES:
        return raw
    match = STATE_RE.fullmatch(raw)
    if match is not None:
        return match.group(1)
    raise FailureRecorderError("V9 scheduler row has an invalid state")


def _parse_terminal_rows(raw: bytes) -> tuple[list[dict], dict]:
    if type(raw) is not bytes or not raw:
        raise FailureRecorderError("V9 terminal scheduler census is missing")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise FailureRecorderError("V9 terminal scheduler census is malformed") from err
    rows = []
    for line in lines:
        fields = [field.strip() for field in line.split("|")]
        if len(fields) != 7:
            raise FailureRecorderError("V9 terminal scheduler census is malformed")
        task_id, state_raw, exit_code, reason, elapsed, partition, restarts = fields
        match = re.fullmatch(re.escape(EXPECTED_JOB_ID) + r"_([0-9]+)", task_id)
        if (
            match is None
            or EXIT_CODE_RE.fullmatch(exit_code) is None
            or any(ord(character) < 32 or ord(character) > 126 for character in reason)
            or len(reason) > 512
            or not elapsed.isdigit()
            or partition != EXPECTED_RESOURCE_PROFILE["partition"]
            or not restarts.isdigit()
        ):
            raise FailureRecorderError("V9 terminal scheduler census is malformed")
        state = _normalized_state(state_raw)
        rows.append({
            "array_task": int(match.group(1)),
            "state": state,
            "state_raw": state_raw,
            "exit_code": exit_code,
            "reason": reason,
            "elapsed_seconds": int(elapsed),
            "partition": partition,
            "restarts": int(restarts),
        })
    rows.sort(key=lambda row: row["array_task"])
    indices = [row["array_task"] for row in rows]
    if (
        len(rows) != EXPECTED_ARRAY_TASKS
        or indices != list(range(EXPECTED_ARRAY_TASKS))
        or len(indices) != len(set(indices))
    ):
        raise FailureRecorderError(
            "V9 terminal scheduler census has missing or duplicate rows"
        )
    if any(row["state"] in ACTIVE_STATES for row in rows):
        raise FailureRecorderError("V9 scheduler census still contains active rows")
    if any(row["state"] not in TERMINAL_STATES for row in rows):
        raise FailureRecorderError("V9 scheduler census is not terminal")

    successes = [
        row for row in rows
        if row["state"] == "COMPLETED" and row["exit_code"] == "0:0"
    ]
    if len(successes) == len(rows):
        raise FailureRecorderError("an all-success V9 cannot be recorded as failed")
    state_counts = Counter(row["state"] for row in rows)
    state_exit_counts = Counter(
        (row["state"], row["exit_code"]) for row in rows
    )
    reason_counts = Counter(row["reason"] for row in rows)
    restart_counts = Counter(row["restarts"] for row in rows)
    elapsed = [row["elapsed_seconds"] for row in rows]
    aggregate = {
        "row_count": len(rows),
        "successful_rows": len(successes),
        "failed_rows": len(rows) - len(successes),
        "all_terminal": True,
        "all_success": False,
        "state_counts": dict(sorted(state_counts.items())),
        "state_exit_code_counts": [
            {"state": state, "exit_code": exit_code, "count": count}
            for (state, exit_code), count in sorted(state_exit_counts.items())
        ],
        "reason_counts": [
            {"reason": reason, "count": count}
            for reason, count in sorted(reason_counts.items())
        ],
        "restart_counts": [
            {"restarts": restarts, "count": count}
            for restarts, count in sorted(restart_counts.items())
        ],
        "elapsed_seconds": {
            "minimum": min(elapsed),
            "maximum": max(elapsed),
            "sum": sum(elapsed),
        },
    }
    return rows, aggregate


def _assert_failure_namespace_clear() -> None:
    if Path(os.path.abspath(FAILURE_RECEIPT.parent)) != Path(
        os.path.abspath(ARTIFACT_DIR)
    ):
        raise FailureRecorderError("V9 failure receipt escaped artifact namespace")
    if os.path.lexists(FAILURE_RECEIPT):
        raise FailureRecorderError("V9 terminal-failure receipt already exists")
    if any(os.path.lexists(path) for path in FORBIDDEN_SEAL_ARTIFACTS):
        raise FailureRecorderError(
            "V9 seal, attestation, stage, or execution receipt already exists"
        )


def _assert_query_namespace_clear() -> None:
    for path in (QUERY_INTENT, SCHEDULER_STDOUT):
        if Path(os.path.abspath(path.parent)) != Path(os.path.abspath(ARTIFACT_DIR)):
            raise FailureRecorderError("V9 query artifact escaped its namespace")
        if os.path.lexists(path):
            raise FailureRecorderError("V9 second query artifact already exists")


def _publish_exclusive(path: Path, raw: bytes, label: str) -> str:
    if type(raw) is not bytes:
        raise FailureRecorderError(label + " is not immutable bytes")
    if Path(os.path.abspath(path.parent)) != Path(os.path.abspath(ARTIFACT_DIR)):
        raise FailureRecorderError(label + " escaped the V9 artifact namespace")
    try:
        parent = ARTIFACT_DIR.lstat()
    except OSError as err:
        raise FailureRecorderError("V9 artifact directory is unavailable") from err
    if ARTIFACT_DIR.is_symlink() or not stat.S_ISDIR(parent.st_mode):
        raise FailureRecorderError("V9 artifact namespace is not a directory")
    flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC
        | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        descriptor = os.open(path, flags, 0o400)
    except OSError as err:
        raise FailureRecorderError("refusing to overwrite " + label) from err
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise FailureRecorderError("cannot publish " + label)
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
    except FailureRecorderError:
        raise
    except OSError as err:
        raise FailureRecorderError("cannot publish " + label) from err
    finally:
        os.close(descriptor)
    try:
        observed = path.lstat()
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        parent_fd = os.open(ARTIFACT_DIR, directory_flags)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except OSError as err:
        raise FailureRecorderError("cannot persist " + label) from err
    if (
        path.is_symlink()
        or not stat.S_ISREG(observed.st_mode)
        or stat.S_IMODE(observed.st_mode) != 0o400
        or observed.st_nlink != 1
        or observed.st_uid != os.getuid()
        or observed.st_size != len(raw)
        or path.read_bytes() != raw
    ):
        raise FailureRecorderError(label + " changed after publication")
    return hashlib.sha256(raw).hexdigest()


def _publish_receipt(receipt: dict) -> str:
    return _publish_exclusive(
        FAILURE_RECEIPT, _canonical_json(receipt), "V9 terminal-failure receipt"
    )


def _load_prior_query_attempt() -> dict:
    raw = _live_source(PRIOR_QUERY_ATTEMPT)
    try:
        value = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise FailureRecorderError(
            "prior V9 scheduler-query attempt is not canonical JSON"
        ) from err
    if (
        type(value) is not dict
        or hashlib.sha256(raw).hexdigest() != EXPECTED_PRIOR_QUERY_ATTEMPT_SHA256
        or value.get("campaign") != "v9-full-census"
        or value.get("job_id") != EXPECTED_JOB_ID
        or value.get("failure_recorder_query_ordinal") != 1
        or value.get("scheduler_query_ordinal_after_launch") != 2
        or value.get("earliest_next_scheduler_query_utc")
        != EARLIEST_SECOND_RECORDER_QUERY_UTC
        or value.get("scheduler_raw_stdout_recorded") is not False
        or value.get("v9_runtime_namespace_enumerated") is not False
        or value.get("v9_scientific_payload_read") is not False
    ):
        raise FailureRecorderError("prior V9 scheduler-query attempt changed")
    return _material(PRIOR_QUERY_ATTEMPT_RELATIVE, raw)


def _parse_utc(value: str, label: str) -> datetime.datetime:
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError) as err:
        raise FailureRecorderError(label + " is malformed") from err
    if parsed.tzinfo is None:
        raise FailureRecorderError(label + " lacks a timezone")
    return parsed.astimezone(datetime.timezone.utc)


def _prepare_second_query(prior_attempt: dict, command: list[str]) -> dict:
    recorded_utc = _utc_now()
    if _parse_utc(recorded_utc, "current UTC time") < _parse_utc(
        EARLIEST_SECOND_RECORDER_QUERY_UTC, "V9 query cadence boundary"
    ):
        raise FailureRecorderError("V9 scheduler query would violate hourly cadence")
    intent = {
        "schema": SCHEMA + "/scheduler-query-intent/v2",
        "campaign": "v9-full-census",
        "job_id": EXPECTED_JOB_ID,
        "recorded_utc": recorded_utc,
        "scheduler_query_ordinal_after_launch": 3,
        "failure_recorder_query_ordinal": 2,
        "earliest_query_utc": EARLIEST_SECOND_RECORDER_QUERY_UTC,
        "command": command,
        "prior_attempt": prior_attempt,
        "stdout_capture_path": str(SCHEDULER_STDOUT),
        "query_may_have_occurred_if_only_this_intent_exists": True,
        "v9_runtime_payload_access_authorized": False,
    }
    raw = _canonical_json(intent)
    digest = _publish_exclusive(
        QUERY_INTENT, raw, "V9 second scheduler-query intent"
    )
    return {
        "path": str(QUERY_INTENT.relative_to(REPO)),
        "bytes": len(raw),
        "sha256": digest,
    }


def _utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )


def record_failure(
    *,
    snapshot_reader: SnapshotReader = read_committed_snapshot,
    scheduler_query: SchedulerQuery | None = None,
) -> tuple[str, dict]:
    _assert_failure_namespace_clear()
    _assert_query_namespace_clear()
    recorder_revision = _require_committed_recorder(snapshot_reader)
    authenticated = _load_authenticated_launch_materials(snapshot_reader)
    _require_lineage(recorder_revision)

    command = _sacct_command()
    prior_attempt = _load_prior_query_attempt()
    query_intent = _prepare_second_query(prior_attempt, command)
    query = _run_sacct if scheduler_query is None else scheduler_query
    try:
        raw_scheduler_output = query(command)
    except FailureRecorderError:
        raise
    except Exception as err:
        raise FailureRecorderError("cannot query V9 accounting") from err
    scheduler_stdout_sha = _publish_exclusive(
        SCHEDULER_STDOUT,
        raw_scheduler_output,
        "V9 second scheduler stdout",
    )
    scheduler_stdout = {
        "path": str(SCHEDULER_STDOUT.relative_to(REPO)),
        "bytes": len(raw_scheduler_output),
        "sha256": scheduler_stdout_sha,
    }
    rows, aggregate = _parse_terminal_rows(raw_scheduler_output)
    _assert_failure_namespace_clear()

    receipt = {
        "schema": SCHEMA,
        "recorded_utc": _utc_now(),
        "campaign": "v9-full-census",
        "determination": "terminal-v9-array-failed-all-success-gate",
        "recorder_repository_revision": recorder_revision,
        "launch_binding": {
            "launch_revision": EXPECTED_LAUNCH_REVISION,
            "launch_receipt": authenticated["launch_receipt"],
            "job_id": EXPECTED_JOB_ID,
            "resource_profile": EXPECTED_RESOURCE_PROFILE,
            "source_revision": EXPECTED_SOURCE_REVISION,
            "source_manifest": authenticated["source_manifest"],
            "source_file_count": len(authenticated["source_files"]),
            "source_files_sha256": authenticated["source_files_sha256"],
            "source_inventory_sha256": EXPECTED_SOURCE_INVENTORY_SHA256,
            "launch_materials": authenticated["launch_materials"],
            "launch_materials_sha256": authenticated["launch_materials_sha256"],
        },
        "scheduler_query_count": 1,
        "scheduler_query_ordinal_after_launch": 3,
        "failure_recorder_query_ordinal": 2,
        "prior_scheduler_query_attempt": prior_attempt,
        "scheduler_query_intent": query_intent,
        "scheduler_command": command,
        "scheduler_fields": SACCT_FIELDS.split(","),
        "scheduler_stdout_bytes": len(raw_scheduler_output),
        "scheduler_stdout_sha256": hashlib.sha256(raw_scheduler_output).hexdigest(),
        "scheduler_raw_stdout_recorded": True,
        "scheduler_stdout_capture": scheduler_stdout,
        "scheduler_rows": rows,
        "scheduler_rows_sha256": _digest(rows),
        "scheduler_aggregate": aggregate,
        "scheduler_aggregate_sha256": _digest(aggregate),
        "v9_worker_output_read": False,
        "v9_worker_log_read": False,
        "v9_task_environment_read": False,
        "v9_temporary_directory_read": False,
        "v9_scientific_payload_read": False,
        "v9_runtime_namespace_enumerated": False,
        "v9_payload_reused": False,
        "v9_partial_output_reuse_authorized": False,
        "v9_burned": True,
        "v9_source_audit_complete": False,
        "confirmation_a_prelaunch_authorized": False,
    }
    digest = _publish_receipt(receipt)
    print(json.dumps({
        "failure_receipt_sha256": digest,
        "job_id": EXPECTED_JOB_ID,
        "scheduler_state_counts": aggregate["state_counts"],
        "v9_burned": True,
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
