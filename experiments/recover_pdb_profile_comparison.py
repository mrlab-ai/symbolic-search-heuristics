#!/usr/bin/env python3
"""Outcome-blind, cell-exact recovery for the cofactor-profile experiment.

``freeze`` is allowed only after the original Slurm array is terminal.  It
records scheduler states, opaque tree hashes for completed cells, and full
hash manifests for missing or interrupted cells.  It does not parse or report
planner outcomes.  ``archive`` moves only interrupted dynamic prefixes into a
resumable quarantine.  ``submit`` launches a generated cell-exact runner, so
no completed cell is touched.  If a sealed one-cell-per-task array exceeds a
site's hard array-index limit, ``amend-array-limit`` can seal a batching
wrapper only after proving that the rejected submission created no job.
``verify`` derives the recovery job identity from the sealed submit receipt
and proves that all untouched cell hashes remained identical.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import shutil
import stat
import subprocess
import tempfile
from collections import Counter
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from unittest import mock

import exp_pdb_profile_comparison as E
import jj_cached_revision as JJ
import pdb_profile_comparison_protocol as P
import suite_cost_manifest as S


class RecoveryError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
DATA_DIR = E.EXPERIMENT_PATH.resolve()
GRID_DIR = (SCRIPT_DIR / "data" / "exp_pdb_profile_comparison-grid-steps").resolve()
START_SCRIPT = GRID_DIR / "exp_pdb_profile_comparison-02-start"
PREREGISTRATION = SCRIPT_DIR / "pdb_profile_predictor_protocol.md"
LAUNCH_RECEIPT = SCRIPT_DIR / "pdb_profile_comparison_launch_receipt.json"
SCHEDULER_MUTATION_RECEIPT = (
    SCRIPT_DIR / "pdb_profile_scheduler_mutation_receipt.json"
)
RUNTIME_RECEIPT = SCRIPT_DIR / "pdb_profile_slurm_runtime_receipt.json"
RUNTIME_PROBE_OUTPUT = (
    SCRIPT_DIR
    / "artifacts"
    / "pdb-profile-runtime-probe"
    / "runtime-login-1789586.jsonl"
)
RUNTIME_PROBE_ERROR = RUNTIME_PROBE_OUTPUT.with_suffix(".err")
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "pdb-profile-comparison-recovery"
MANIFEST = ARTIFACT_DIR / "recovery-manifest-v1.json"
MANIFEST_SIDECAR = ARTIFACT_DIR / "recovery-manifest-v1.json.sha256"
QUARANTINE = ARTIFACT_DIR / "original-prefixes-v1"
CELL_SEALS = QUARANTINE / "cell-seals"
CLEANUP_RECEIPT = ARTIFACT_DIR / "recovery-cleanup-v1.json"
RESTORE_RECEIPT = ARTIFACT_DIR / "recovery-restore-v1.json"
RESTORE_INTENT = ARTIFACT_DIR / "recovery-restore-intent-v1.json"
VERIFICATION = ARTIFACT_DIR / "recovery-verification-v1.json"
WAVES_DIR = ARTIFACT_DIR / "waves"
VENV_PYTHON = SCRIPT_DIR / ".venv" / "bin" / "python"
REQUIREMENTS = SCRIPT_DIR / "requirements.txt"

SCHEMA = "symbolic-search-heuristics/pdb-profile-recovery-manifest/v4"
WAVE_SCHEMA = "symbolic-search-heuristics/pdb-profile-recovery-wave/v3"
CELL_SEAL_SCHEMA = "symbolic-search-heuristics/pdb-profile-prefix-cell/v1"
WAVE_CELL_SEAL_SCHEMA = "symbolic-search-heuristics/pdb-profile-wave-prefix-cell/v1"
RECEIPT_SCHEMA = "symbolic-search-heuristics/pdb-profile-recovery-receipt/v2"
VERIFICATION_SCHEMA = "symbolic-search-heuristics/pdb-profile-recovery-verification/v3"
LAUNCH_RECEIPT_SCHEMA = "symbolic-search-heuristics/pdb-profile-main-launch-receipt/v1"
SCHEDULER_MUTATION_RECEIPT_SCHEMA = (
    "symbolic-search-heuristics/pdb-profile-scheduler-mutation-receipt/v1"
)
RUNTIME_RECEIPT_SCHEMA = "symbolic-search-heuristics/pdb-profile-slurm-runtime-receipt/v1"
ARRAY_LIMIT_AMENDMENT_SCHEMA = (
    "symbolic-search-heuristics/pdb-profile-recovery-array-limit-amendment/v1"
)
STATIC_NAMES = frozenset({"domain.pddl", "problem.pddl", "run", "static-properties"})
EXPECTED_ARRAY_TASKS = (
    P.CELL_COUNT + E.RUNS_PER_ARRAY_TASK - 1
) // E.RUNS_PER_ARRAY_TASK
DRIVER_END_RE = re.compile(
    rb"^\d{4}-\d\d-\d\d \d\d:\d\d:\d\d,\d{3} "
    rb"INFO\s+planner exit code: -?\d+$"
)
JOB_ID_RE = re.compile(r"^[1-9][0-9]*$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
TERMINAL_STATES = frozenset(
    {
        "BOOT_FAIL",
        "CANCELLED",
        "COMPLETED",
        "DEADLINE",
        "FAILED",
        "NODE_FAIL",
        "OUT_OF_MEMORY",
        "PREEMPTED",
        "REVOKED",
        "SPECIAL_EXIT",
        "TIMEOUT",
    }
)
RECOVERABLE_STATES = frozenset({"NODE_FAIL", "TIMEOUT"})
RECOVERY_WALL_TIME = "02:30:00"
RECOVERY_MEMORY = "9G"
ARRAY_LIMIT_REJECTION = "allocation failure: Invalid job array specification"
DEPENDENCY_PATHS = (
    Path(__file__).resolve(),
    Path(E.__file__).resolve(),
    Path(P.__file__).resolve(),
    Path(JJ.__file__).resolve(),
    Path(S.__file__).resolve(),
    SCRIPT_DIR / "suite_wbh_operator_costs.json",
    SCRIPT_DIR / "suite_wbh_operator_costs.json.sha256",
    SCRIPT_DIR / "analyze_pdb_cap_grid_posthoc_review.py",
    SCRIPT_DIR / "selector_pilot_suite.txt",
    REQUIREMENTS.resolve(),
    LAUNCH_RECEIPT.resolve(),
    SCHEDULER_MUTATION_RECEIPT.resolve(),
    RUNTIME_RECEIPT.resolve(),
    RUNTIME_PROBE_OUTPUT.resolve(),
    RUNTIME_PROBE_ERROR.resolve(),
    (SCRIPT_DIR / "probe_pdb_profile_runtime.py").resolve(),
    (SCRIPT_DIR / "probe_pdb_profile_runtime.sh").resolve(),
    PREREGISTRATION.resolve(),
)
MAIN_SACCT_FORMAT = (
    "JobID%256,JobIDRaw%64,State%64,ElapsedRaw%32,Timelimit%32,"
    "ExitCode%32,NodeList%2048,JobName%512,Submit%64,WorkDir%2048,"
    "ReqMem%64,ReqCPUS%64,Account%256,Partition%256,QOS%256,SubmitLine%4096"
)
RECONCILIATION_SACCT_FORMAT = (
    "JobID%256,JobName%512,Submit%64,WorkDir%2048,ReqMem%64,ReqCPUS%64,"
    "Timelimit%32,Account%256,Partition%256,QOS%256,Comment%2048,SubmitLine%4096"
)
RECOVERY_SACCT_FORMAT = (
    "JobID%256,JobIDRaw%64,State%64,JobName%512,Submit%64,WorkDir%2048,"
    "ReqMem%64,ReqCPUS%64,Timelimit%32,Account%256,Partition%256,QOS%256,"
    "Comment%2048,SubmitLine%4096"
)
RECOVERY_SCHEDULER_RECORD_KEYS = frozenset(
    {
        "array_task_id",
        "job_id_raw",
        "state",
        "state_base",
        "job_name",
        "submit",
        "work_dir",
        "requested_memory",
        "requested_cpus",
        "time_limit",
        "account",
        "partition",
        "qos",
        "comment",
        "submit_line",
    }
)
RUNTIME_PROBE_SACCT_FORMAT = (
    "JobID%256,State%64,JobName%512,Submit%64,WorkDir%2048,ReqMem%64,"
    "ReqCPUS%64,Timelimit%32,Account%256,Partition%256,QOS%256,SubmitLine%4096"
)


def canonical_bytes(value) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise RecoveryError("artifact is not finite canonical JSON") from err


def exact_json_equal(left, right) -> bool:
    """Compare JSON values without Python's bool/int numeric coercion."""
    return canonical_bytes(left) == canonical_bytes(right)


def normalized_slurm_state(value: str) -> str:
    if not isinstance(value, str) or not value.split():
        raise RecoveryError("scheduler state is empty or non-textual")
    base = value.split()[0].rstrip("+")
    if not base:
        raise RecoveryError("scheduler state has no canonical base")
    return base


def require_recoverable_cell_state(task_id: int, state: str, cell_label: str) -> None:
    if state not in RECOVERABLE_STATES:
        raise RecoveryError(
            "{} belongs to scheduler task {} in state {}".format(
                cell_label, task_id, state
            )
        )


def recovery_wave_cell_action(state: str, complete: bool) -> str:
    if type(complete) is not bool:
        raise RecoveryError("recovery completion flag is not Boolean")
    if state not in RECOVERABLE_STATES | {"COMPLETED"}:
        raise RecoveryError("recovery wave has unsupported state {}".format(state))
    if complete:
        return "protect"
    if state in RECOVERABLE_STATES:
        return "retry"
    raise RecoveryError("completed recovery task lacks its final driver sentinel")


def recovery_retry_policy() -> dict:
    return {
        "completion_test": (
            "last-line-shape-only;numeric-exit-value-not-recorded/v1"
        ),
        "complete_cell_action": "protect-regardless-of-allowed-scheduler-state",
        "retry_incomplete_scheduler_states": sorted(RECOVERABLE_STATES),
        "completed_incomplete_action": "fail-closed",
        "unsupported_scheduler_state_action": "fail-closed",
    }


def validate_retry_source_decisions(
    source_records: list[dict],
    decisions: list[dict],
    retry_inputs: list[dict],
    protected_hashes: list[list],
) -> None:
    if not isinstance(source_records, list) or not isinstance(decisions, list):
        raise RecoveryError("retry source records or decisions are not lists")
    if any(not isinstance(record, dict) for record in source_records):
        raise RecoveryError("retry source scheduler record is not an object")
    expected_tasks = list(range(1, len(source_records) + 1))
    if [record.get("array_task_id") for record in source_records] != expected_tasks:
        raise RecoveryError("retry source scheduler task set changed")
    for record in source_records:
        if (
            not isinstance(record, dict)
            or set(record) != RECOVERY_SCHEDULER_RECORD_KEYS
            or type(record["array_task_id"]) is not int
            or JOB_ID_RE.fullmatch(record.get("job_id_raw", "")) is None
            or normalized_slurm_state(record.get("state")) != record.get("state_base")
            or record.get("state_base") not in RECOVERABLE_STATES | {"COMPLETED"}
        ):
            raise RecoveryError("retry source scheduler record changed")
    decision_keys = {
        "run_id",
        "source_array_task_id",
        "scheduler_state",
        "completion_test_passed",
        "action",
        "tree_sha256",
    }
    if not decisions or len(decisions) < len(source_records):
        raise RecoveryError("retry source decision count changed")
    retry_hashes = {cell["run_id"]: cell["tree_sha256"] for cell in retry_inputs}
    protected = {item[0]: item[1] for item in protected_hashes}
    seen_runs = set()
    expected_retry_ids = []
    source_task_ids = []
    for decision in decisions:
        if not isinstance(decision, dict) or set(decision) != decision_keys:
            raise RecoveryError("retry source decision structure changed")
        run_id = decision["run_id"]
        source_task = decision["source_array_task_id"]
        if (
            type(run_id) is not int
            or run_id < 1
            or run_id in seen_runs
            or type(source_task) is not int
            or not 1 <= source_task <= len(source_records)
            or decision["scheduler_state"]
            != source_records[source_task - 1]["state_base"]
            or type(decision["completion_test_passed"]) is not bool
            or SHA256_RE.fullmatch(decision.get("tree_sha256", "")) is None
        ):
            raise RecoveryError("retry source decision identity changed")
        seen_runs.add(run_id)
        source_task_ids.append(source_task)
        expected_action = recovery_wave_cell_action(
            source_records[source_task - 1]["state_base"],
            decision["completion_test_passed"],
        )
        if decision["action"] != expected_action:
            raise RecoveryError("retry source decision violates retry policy")
        if expected_action == "retry":
            expected_retry_ids.append(run_id)
            if retry_hashes.get(run_id) != decision["tree_sha256"]:
                raise RecoveryError("retry decision differs from its retry input")
            if run_id in protected:
                raise RecoveryError("retry decision is also protected")
        else:
            if protected.get(run_id) != decision["tree_sha256"]:
                raise RecoveryError("protect decision differs from its protected hash")
            if run_id in retry_hashes:
                raise RecoveryError("protect decision is also retried")
    if sorted(retry_hashes) != sorted(expected_retry_ids):
        raise RecoveryError("retry decisions do not match the retry-input set")
    if (
        source_task_ids != sorted(source_task_ids)
        or sorted(set(source_task_ids)) != expected_tasks
    ):
        raise RecoveryError("retry decisions do not cover scheduler tasks in order")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as err:
        raise RecoveryError("cannot hash {}".format(path)) from err
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_artifact(path: Path, value) -> str:
    """Install one immutable canonical artifact without an overwrite window."""
    raw = canonical_bytes(value) + b"\n"
    digest = sha256_bytes(raw)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".{}-".format(path.name), dir=path.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o444)
        try:
            os.link(temporary, path)
        except FileExistsError as err:
            raise RecoveryError("refusing to overwrite {}".format(path)) from err
        _fsync_directory(path.parent)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return digest


def write_artifact_pair(path: Path, value) -> str:
    """Install or finish an immutable JSON/checksum pair idempotently.

    Installing the JSON first is unavoidable on a normal filesystem.  A retry
    after a crash in that narrow window validates the already-installed bytes
    and creates only the missing checksum sidecar.
    """
    raw = canonical_bytes(value) + b"\n"
    digest = sha256_bytes(raw)
    sidecar = path.with_name(path.name + ".sha256")
    sidecar_text = "{}  {}\n".format(digest, path.name)
    if path.exists() or path.is_symlink():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != raw:
            raise RecoveryError("existing artifact differs: {}".format(path))
    elif sidecar.exists() or sidecar.is_symlink():
        raise RecoveryError("checksum exists without its artifact: {}".format(sidecar))
    else:
        write_artifact(path, value)
    if sidecar.exists() or sidecar.is_symlink():
        if (
            sidecar.is_symlink()
            or not sidecar.is_file()
            or sidecar.read_text(encoding="ascii") != sidecar_text
        ):
            raise RecoveryError("artifact checksum differs: {}".format(sidecar))
    else:
        write_text_artifact(sidecar, sidecar_text)
    return digest


def write_text_artifact(path: Path, text: str, *, executable: bool = False) -> str:
    try:
        raw = text.encode("ascii")
    except UnicodeEncodeError as err:
        raise RecoveryError("text artifact is not ASCII") from err
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".{}-".format(path.name), dir=path.parent
        )
        temporary = Path(temporary_name)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o755 if executable else 0o444)
        try:
            os.link(temporary, path)
        except FileExistsError as err:
            raise RecoveryError("refusing to overwrite {}".format(path)) from err
        _fsync_directory(path.parent)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return sha256_bytes(raw)


def load_canonical_artifact(path: Path, schema: str) -> dict:
    try:
        status = path.lstat()
        if (
            stat.S_ISLNK(status.st_mode)
            or not stat.S_ISREG(status.st_mode)
            or path.resolve(strict=True) != path
        ):
            raise RecoveryError("sealed artifact path is linked: {}".format(path))
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RecoveryError("cannot read sealed artifact {}".format(path)) from err
    if raw != canonical_bytes(value) + b"\n" or value.get("schema") != schema:
        raise RecoveryError("artifact is noncanonical or has the wrong schema: {}".format(path))
    return value


def run_relative(run_id: int) -> Path:
    if type(run_id) is not int or not 1 <= run_id <= P.CELL_COUNT:
        raise RecoveryError("run ID is outside the frozen matrix")
    lower = ((run_id - 1) // 100) * 100 + 1
    upper = ((run_id + 99) // 100) * 100
    return Path("runs-{:05d}-{:05d}".format(lower, upper)) / "{:05d}".format(run_id)


def _lstat_directory(path: Path, label: str) -> None:
    try:
        status = path.lstat()
    except OSError as err:
        raise RecoveryError("{} is missing: {}".format(label, path)) from err
    if stat.S_ISLNK(status.st_mode) or not stat.S_ISDIR(status.st_mode):
        raise RecoveryError("{} is not a real directory: {}".format(label, path))


def _confined_directory(base: Path, relative: Path, label: str) -> Path:
    """Return an existing descendant after rejecting every linked ancestor."""
    base = Path(base)
    pure = PurePosixPath(relative.as_posix())
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise RecoveryError("{} has an unsafe relative path".format(label))
    _lstat_directory(base, "{} base".format(label))
    candidate = base
    for part in pure.parts:
        candidate = candidate / part
        _lstat_directory(candidate, label)
    try:
        resolved_relative = candidate.resolve(strict=True).relative_to(
            base.resolve(strict=True)
        )
    except (OSError, ValueError) as err:
        raise RecoveryError("{} escaped its trusted base".format(label)) from err
    if not resolved_relative.parts:
        raise RecoveryError("{} is not a strict descendant".format(label))
    return candidate


def _make_confined_directory(base: Path, relative: Path, label: str) -> Path:
    """Create a descendant one component at a time without accepting links."""
    base = Path(base)
    pure = PurePosixPath(relative.as_posix())
    if pure.is_absolute() or not pure.parts or ".." in pure.parts:
        raise RecoveryError("{} has an unsafe relative path".format(label))
    base.mkdir(parents=True, exist_ok=True)
    _lstat_directory(base, "{} base".format(label))
    candidate = base
    for part in pure.parts:
        candidate = candidate / part
        try:
            candidate.mkdir()
            _fsync_directory(candidate.parent)
        except FileExistsError:
            pass
        _lstat_directory(candidate, label)
    return _confined_directory(base, Path(*pure.parts), label)


def _safe_run_root(run_id: int) -> Path:
    return _confined_directory(DATA_DIR, run_relative(run_id), "run directory")


def _safe_quarantine_root(run_id: int, *, create: bool = False) -> Path:
    relative = QUARANTINE.relative_to(ARTIFACT_DIR) / run_relative(run_id)
    if create:
        return _make_confined_directory(ARTIFACT_DIR, relative, "quarantine run")
    return _confined_directory(ARTIFACT_DIR, relative, "quarantine run")


def _safe_wave_archive_root(wave_directory: Path, run_id: int, *, create: bool = False) -> Path:
    try:
        wave_relative = Path(wave_directory).relative_to(ARTIFACT_DIR)
    except ValueError as err:
        raise RecoveryError("wave archive is outside the sealed artifact directory") from err
    if (
        len(wave_relative.parts) != 2
        or wave_relative.parts[0] != "waves"
        or re.fullmatch(r"wave-[0-9]{4}", wave_relative.parts[1]) is None
    ):
        raise RecoveryError("wave archive has an invalid wave directory")
    relative = wave_relative / "previous-wave-prefixes" / run_relative(run_id)
    if create:
        return _make_confined_directory(ARTIFACT_DIR, relative, "wave archive run")
    return _confined_directory(ARTIFACT_DIR, relative, "wave archive run")


def _safe_dynamic_path(root: Path, name: str) -> Path:
    if (
        not isinstance(name, str)
        or SAFE_NAME_RE.fullmatch(name) is None
        or name in STATIC_NAMES
        or name in (".", "..")
    ):
        raise RecoveryError("unsafe dynamic basename {!r}".format(name))
    _lstat_directory(root, "dynamic-path root")
    target = root / name
    if target.parent != root:
        raise RecoveryError("dynamic path escaped its run directory")
    return target


def driver_log_complete(path: Path) -> bool:
    try:
        if not path.is_file() or path.is_symlink():
            return False
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - 4096))
            tail = stream.read()
    except OSError as err:
        raise RecoveryError("cannot inspect {}".format(path)) from err
    lines = tail.rstrip().splitlines()
    return bool(lines and DRIVER_END_RE.fullmatch(lines[-1]))


def _entry_record(root: Path, path: Path) -> dict:
    relative = path.relative_to(root).as_posix()
    status = path.lstat()
    base = {"path": relative, "mode": stat.S_IMODE(status.st_mode)}
    if stat.S_ISREG(status.st_mode):
        return {
            **base,
            "type": "file",
            "size": status.st_size,
            "sha256": sha256_file(path),
        }
    if stat.S_ISLNK(status.st_mode):
        target = os.readlink(path)
        return {
            **base,
            "type": "symlink",
            "target": target,
            "target_sha256": sha256_bytes(os.fsencode(target)),
        }
    if stat.S_ISDIR(status.st_mode):
        return {**base, "type": "directory"}
    raise RecoveryError("unsupported run-directory entry: {}".format(path))


def snapshot_tree(root: Path) -> list[dict]:
    root = Path(root)
    if not root.is_dir() or root.is_symlink():
        raise RecoveryError("run directory is missing or linked: {}".format(root))
    records = []

    def visit(directory: Path) -> None:
        for child in sorted(directory.iterdir(), key=lambda item: item.name):
            record = _entry_record(root, child)
            records.append(record)
            if record["type"] == "directory":
                visit(child)

    try:
        visit(root)
    except OSError as err:
        raise RecoveryError("cannot snapshot {}".format(root)) from err
    return sorted(records, key=lambda record: record["path"])


def snapshot_digest(records: list[dict]) -> str:
    return sha256_bytes(canonical_bytes(sorted(records, key=lambda item: item["path"])))


def validate_static_inputs(root: Path, records: list[dict]) -> None:
    top = {record["path"]: record for record in records if "/" not in record["path"]}
    if not STATIC_NAMES.issubset(top):
        raise RecoveryError("run directory lacks a frozen static input")
    for name in ("run", "static-properties"):
        if top[name]["type"] != "file":
            raise RecoveryError("{} is not a regular static file".format(root / name))
    for name in ("domain.pddl", "problem.pddl"):
        path = root / name
        if top[name]["type"] != "symlink" or not path.resolve().is_file():
            raise RecoveryError("{} is not a live benchmark symlink".format(path))


def dynamic_top_names(records: list[dict]) -> list[str]:
    return sorted(
        {
            record["path"].split("/", 1)[0]
            for record in records
            if record["path"].split("/", 1)[0] not in STATIC_NAMES
        }
    )


def _records_for_top(records: list[dict], name: str) -> list[dict]:
    return [
        record
        for record in records
        if record["path"] == name or record["path"].startswith(name + "/")
    ]


def load_main_launch_receipt() -> dict:
    try:
        value = json.loads(LAUNCH_RECEIPT.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RecoveryError("cannot read the main-array launch receipt") from err
    required = {
        "schema",
        "recorded_utc",
        "job_id",
        "job_name",
        "submit_time",
        "work_directory",
        "command",
        "submit_line",
        "launcher_sha256",
        "array_spec",
        "array_tasks",
        "array_throttle",
        "wall_time",
        "memory_per_cpu",
        "original_exported_path_value_recorded",
        "original_validator_identity_recorded",
        "cpus_per_task",
        "account",
        "partition",
        "qos",
        "requeue",
    }
    expected = {
        "schema": LAUNCH_RECEIPT_SCHEMA,
        "job_name": "{}-02-start".format(E.EXPERIMENT_PATH.name),
        "work_directory": str(GRID_DIR),
        "command": str(START_SCRIPT),
        "submit_line": "sbatch --export PATH {}".format(START_SCRIPT),
        "launcher_sha256": sha256_file(START_SCRIPT),
        "array_spec": "1-{}%{}".format(EXPECTED_ARRAY_TASKS, E.ARRAY_THROTTLE),
        "array_tasks": EXPECTED_ARRAY_TASKS,
        "array_throttle": E.ARRAY_THROTTLE,
        "wall_time": E.SCHEDULER_TIME_LIMIT,
        "memory_per_cpu": E.SCHEDULER_MEMORY,
        "original_exported_path_value_recorded": False,
        "original_validator_identity_recorded": False,
        "cpus_per_task": 1,
        "account": E.ACCOUNT,
        "partition": "cpu",
        "qos": "normal",
        "requeue": False,
    }
    if not isinstance(value, dict) or set(value) != required:
        raise RecoveryError("main-array launch receipt structure changed")
    if any(
        not exact_json_equal(value.get(key), expected_value)
        for key, expected_value in expected.items()
    ):
        raise RecoveryError("main-array launch receipt differs from the generated launch")
    if JOB_ID_RE.fullmatch(value.get("job_id", "")) is None:
        raise RecoveryError("main-array launch receipt has an invalid job ID")
    for key in ("recorded_utc", "submit_time"):
        if not isinstance(value.get(key), str) or re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ?", value[key]
        ) is None:
            raise RecoveryError("main-array launch receipt has an invalid timestamp")
    return value


def load_scheduler_mutation_receipt(launch_receipt: dict) -> dict:
    try:
        value = json.loads(SCHEDULER_MUTATION_RECEIPT.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RecoveryError("cannot read the scheduler-mutation receipt") from err
    required = {
        "schema",
        "recorded_utc",
        "recorded_after_terminal",
        "job_id",
        "main_launch_receipt_sha256",
        "authorization",
        "mutations",
        "outcome_access",
        "post_terminal_attestation",
    }
    fixed = {
        "schema": SCHEDULER_MUTATION_RECEIPT_SCHEMA,
        "recorded_after_terminal": True,
        "job_id": launch_receipt["job_id"],
        "main_launch_receipt_sha256": sha256_file(LAUNCH_RECEIPT),
        "authorization": {
            "source": "interactive-user-instruction",
            "partition_request": "Move the job to the fat partition, which is less busy.",
            "throttle_request": "Remove the throttle.",
        },
        "mutations": {
            "array_task_throttle": {
                "from": launch_receipt["array_throttle"],
                "scope": "array-job",
                "to": 0,
            },
            "partition": {
                "array_task_count": 491,
                "array_task_first": 506,
                "array_task_last": EXPECTED_ARRAY_TASKS,
                "from": launch_receipt["partition"],
                "scope": "pending-array-elements",
                "to": "fat",
            },
        },
        "outcome_access": {"planner_outcomes_parsed": False},
        "post_terminal_attestation": {
            "array_task_count": EXPECTED_ARRAY_TASKS,
            "partition_counts": {"cpu": 505, "fat": 491},
            # Slurm's terminal per-task accounting preserves Partition, but
            # it does not preserve the final ArrayTaskThrottle value.
            "throttle_terminal_accounting_available": False,
        },
    }
    if not isinstance(value, dict) or set(value) != required:
        raise RecoveryError("scheduler-mutation receipt structure changed")
    if any(
        not exact_json_equal(value.get(key), expected)
        for key, expected in fixed.items()
    ):
        raise RecoveryError(
            "scheduler-mutation receipt differs from the authorized change"
        )
    if not isinstance(value.get("recorded_utc"), str) or re.fullmatch(
        r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", value["recorded_utc"]
    ) is None:
        raise RecoveryError("scheduler-mutation receipt has an invalid timestamp")
    return value


def expected_main_partition(
    task_id: int, launch_receipt: dict, mutation_receipt: dict
) -> str:
    if mutation_receipt.get("job_id") != launch_receipt.get("job_id"):
        raise RecoveryError("scheduler-mutation receipt refers to a different launch")
    partition = mutation_receipt.get("mutations", {}).get("partition", {})
    first = partition.get("array_task_first")
    last = partition.get("array_task_last")
    if type(first) is not int or type(last) is not int or not 1 <= first <= last:
        raise RecoveryError("scheduler-mutation receipt has an invalid task range")
    if first <= task_id <= last:
        return partition.get("to")
    return launch_receipt["partition"]


def validate_main_partition_attestation(
    records: list[dict], launch_receipt: dict, mutation_receipt: dict
) -> None:
    attestation = mutation_receipt.get("post_terminal_attestation", {})
    if len(records) != attestation.get("array_task_count"):
        raise RecoveryError("scheduler-mutation task count differs from accounting")
    actual = dict(sorted(Counter(record["partition"] for record in records).items()))
    if actual != attestation.get("partition_counts"):
        raise RecoveryError("scheduler-mutation partition counts differ from accounting")
    for record in records:
        if record["partition"] != expected_main_partition(
            record["array_task_id"], launch_receipt, mutation_receipt
        ):
            raise RecoveryError(
                "array task {} has an unauthorized partition".format(
                    record["array_task_id"]
                )
            )


def load_slurm_runtime_receipt() -> dict:
    try:
        value = json.loads(RUNTIME_RECEIPT.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RecoveryError("cannot read the Slurm runtime receipt") from err
    required = {
        "schema",
        "recorded_utc",
        "job_id",
        "job_name",
        "submit_time",
        "submit_line",
        "state",
        "hostname",
        "work_directory",
        "export_policy",
        "effective_path",
        "effective_ld_library_path",
        "python_environment",
        "validator",
        "probe_output_sha256",
        "probe_error_sha256",
        "probe_python_sha256",
        "probe_shell_sha256",
        "wall_time",
        "memory_per_cpu",
        "cpus_per_task",
        "account",
        "partition",
        "qos",
    }
    expected_python_environment = {
        "LD_PRELOAD": None,
        "PYTHONHOME": None,
        "PYTHONNOUSERSITE": None,
        "PYTHONPATH": None,
        "PYTHONSTARTUP": None,
        "PYTHONUSERBASE": None,
    }
    expected_validator = {
        "available": False,
        "candidate": None,
        "is_symlink": None,
        "path": None,
        "resolved_path": None,
        "sha256": None,
        "size": None,
    }
    fixed = {
        "schema": RUNTIME_RECEIPT_SCHEMA,
        "job_id": "1789586",
        "job_name": "pdbprof-login-runtime-probe",
        "state": "COMPLETED",
        "work_directory": str(SCRIPT_DIR),
        "export_policy": "PATH",
        "python_environment": expected_python_environment,
        "validator": expected_validator,
        "probe_output_sha256": sha256_file(RUNTIME_PROBE_OUTPUT),
        "probe_error_sha256": sha256_file(RUNTIME_PROBE_ERROR),
        "probe_python_sha256": sha256_file(SCRIPT_DIR / "probe_pdb_profile_runtime.py"),
        "probe_shell_sha256": sha256_file(SCRIPT_DIR / "probe_pdb_profile_runtime.sh"),
        "wall_time": "00:05:00",
        "memory_per_cpu": "256M",
        "cpus_per_task": 1,
        "account": E.ACCOUNT,
        "partition": "cpu",
        "qos": "normal",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise RecoveryError("Slurm runtime receipt structure changed")
    if any(
        not exact_json_equal(value.get(key), expected)
        for key, expected in fixed.items()
    ):
        raise RecoveryError("Slurm runtime receipt differs from its sealed probe")
    for key in ("recorded_utc", "submit_time"):
        if not isinstance(value.get(key), str) or re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ?", value[key]
        ) is None:
            raise RecoveryError("Slurm runtime receipt has an invalid timestamp")
    for key in ("probe_output_sha256", "effective_path", "effective_ld_library_path"):
        if not isinstance(value.get(key), str) or not value[key]:
            raise RecoveryError("Slurm runtime receipt omits {}".format(key))
    if SHA256_RE.fullmatch(value["probe_output_sha256"]) is None:
        raise RecoveryError("Slurm runtime probe output hash is invalid")
    try:
        report = json.loads(RUNTIME_PROBE_OUTPUT.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RecoveryError("cannot read the sealed Slurm runtime probe output") from err
    expected_report_environment = {
        "LD_LIBRARY_PATH": value["effective_ld_library_path"],
        **value["python_environment"],
    }
    if (
        report.get("schema")
        != "symbolic-search-heuristics/pdb-profile-slurm-runtime-probe/v1"
        or report.get("hostname") != value["hostname"]
        or report.get("slurm_job_id") != value["job_id"]
        or report.get("slurm_job_name") != value["job_name"]
        or report.get("slurm_array_job_id") is not None
        or report.get("path") != value["effective_path"]
        or report.get("python_environment") != expected_report_environment
        or report.get("validator") != value["validator"]
    ):
        raise RecoveryError("Slurm runtime probe output differs from its receipt")
    return value


def validate_slurm_runtime_probe_accounting(receipt: dict) -> None:
    try:
        result = subprocess.run(
            [
                "sacct",
                "-n",
                "-X",
                "-j",
                receipt["job_id"],
                "--format={}".format(RUNTIME_PROBE_SACCT_FORMAT),
                "-P",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("cannot verify the Slurm runtime probe") from err
    rows = [line.split("|") for line in result.stdout.splitlines() if line.strip()]
    if len(rows) != 1 or len(rows[0]) != 12:
        raise RecoveryError("Slurm runtime probe accounting row changed")
    (
        job_id,
        state,
        job_name,
        submit_time,
        work_dir,
        requested_memory,
        requested_cpus,
        time_limit,
        account,
        partition,
        qos,
        submit_line,
    ) = rows[0]
    if (
        job_id != receipt["job_id"]
        or state.split()[0].rstrip("+") != receipt["state"]
        or job_name != receipt["job_name"]
        or submit_time != receipt["submit_time"]
        or work_dir != receipt["work_directory"]
        or not memory_matches_per_cpu(requested_memory, receipt["memory_per_cpu"])
        or requested_cpus != str(receipt["cpus_per_task"])
        or _time_seconds(time_limit) != _time_seconds(receipt["wall_time"])
        or account != receipt["account"]
        or partition != receipt["partition"]
        or qos != receipt["qos"]
        or submit_line != receipt["submit_line"]
    ):
        raise RecoveryError("Slurm runtime probe does not match its sealed receipt")


def parse_original_launcher(raw: str) -> dict:
    array_matches = re.findall(r"^#SBATCH --array=1-([0-9]+)%([0-9]+)$", raw, re.M)
    if array_matches != [(str(EXPECTED_ARRAY_TASKS), str(E.ARRAY_THROTTLE))]:
        raise RecoveryError("generated launcher array directive changed")
    match = re.search(
        r"^declare -a SHUFFLED_TASK_IDS=\(([0-9 ]+)\)$", raw, re.M
    )
    if match is None:
        raise RecoveryError("generated launcher task mapping is absent")
    slot_to_group = [int(value) for value in match.group(1).split()]
    expected = list(range(1, EXPECTED_ARRAY_TASKS + 1))
    if len(slot_to_group) != EXPECTED_ARRAY_TASKS or sorted(slot_to_group) != expected:
        raise RecoveryError("generated launcher task mapping is not a bijection")
    required_lines = (
        "#SBATCH --partition=cpu",
        "#SBATCH --qos=normal",
        "#SBATCH --time={}".format(E.SCHEDULER_TIME_LIMIT),
        "#SBATCH --mem-per-cpu={}".format(E.SCHEDULER_MEMORY),
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --account={}".format(E.ACCOUNT),
        "ulimit -Sv 9248440",
        '"{}" run'.format(VENV_PYTHON),
        "TASK_ID=${SHUFFLED_TASK_IDS[$SLURM_ARRAY_TASK_ID - 1]}",
        "NUM_RUNS={}".format(P.CELL_COUNT),
        "RUNS_PER_TASK={}".format(E.RUNS_PER_ARRAY_TASK),
        'let "FIRST_RUN_ID=(TASK_ID - 1) * RUNS_PER_TASK + 1"',
        'let "LAST_RUN_ID=FIRST_RUN_ID + RUNS_PER_TASK - 1"',
        "for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID | shuf); do",
        '(cd "../exp_pdb_profile_comparison/$run_dir" && execute_run ${run_id})',
        "if [[ -f driver.log ]]; then",
    )
    for line in required_lines:
        if raw.count(line) != 1:
            raise RecoveryError("generated launcher logic changed: {}".format(line))
    group_to_slot = {group: slot for slot, group in enumerate(slot_to_group, 1)}
    assignment = []
    for run_id in range(1, P.CELL_COUNT + 1):
        group = (run_id - 1) // E.RUNS_PER_ARRAY_TASK + 1
        assignment.append(group_to_slot[group])
    return {
        "array_slot_to_logical_group": slot_to_group,
        "run_to_array_task_sha256": sha256_bytes(canonical_bytes(assignment)),
        "group_to_slot": group_to_slot,
    }


def array_task_for_run(run_id: int, group_to_slot: dict[int, int]) -> int:
    group = (run_id - 1) // E.RUNS_PER_ARRAY_TASK + 1
    try:
        return group_to_slot[group]
    except KeyError as err:
        raise RecoveryError("run has no generated launcher assignment") from err


def parse_sacct(
    raw: str,
    job_id: str,
    expected_tasks: set[int],
    launch_receipt: dict,
    mutation_receipt: dict,
) -> list[dict]:
    if JOB_ID_RE.fullmatch(job_id) is None:
        raise RecoveryError("job ID must be a positive decimal integer")
    records = {}
    pattern = re.compile(
        r"^{}_(0|[1-9][0-9]*)$".format(re.escape(job_id))
    )
    for line in raw.splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) != 16:
            raise RecoveryError("main-array sacct record has the wrong field count")
        (
            display_id,
            raw_id,
            state,
            elapsed,
            limit,
            exit_code,
            node,
            job_name,
            submit_time,
            work_dir,
            requested_memory,
            requested_cpus,
            account,
            partition,
            qos,
            submit_line,
        ) = fields
        match = pattern.fullmatch(display_id)
        if match is None:
            continue
        task_id = int(match.group(1))
        if task_id in records:
            raise RecoveryError("sacct repeats array task {}".format(task_id))
        base_state = normalized_slurm_state(state)
        if base_state not in TERMINAL_STATES:
            raise RecoveryError("array task {} is not terminal: {}".format(task_id, state))
        if (
            job_name != launch_receipt["job_name"]
            or submit_time != launch_receipt["submit_time"]
            or work_dir != launch_receipt["work_directory"]
            or not memory_matches_per_cpu(requested_memory)
            or requested_cpus != str(launch_receipt["cpus_per_task"])
            or limit != launch_receipt["wall_time"]
            or account != launch_receipt["account"]
            or partition
            != expected_main_partition(task_id, launch_receipt, mutation_receipt)
            or qos != launch_receipt["qos"]
            or submit_line != launch_receipt["submit_line"]
        ):
            raise RecoveryError(
                "array task {} does not match the sealed main launch".format(task_id)
            )
        records[task_id] = {
            "array_task_id": task_id,
            "job_id_raw": raw_id,
            "state": state,
            "state_base": base_state,
            "elapsed_raw": elapsed,
            "time_limit": limit,
            "exit_code": exit_code,
            "node_list": node,
            "job_name": job_name,
            "submit_time": submit_time,
            "work_dir": work_dir,
            "requested_memory": requested_memory,
            "requested_cpus": requested_cpus,
            "account": account,
            "partition": partition,
            "qos": qos,
            "submit_line": submit_line,
        }
    if set(records) != expected_tasks:
        raise RecoveryError(
            "sacct task set changed (missing={}, extra={})".format(
                sorted(expected_tasks - set(records))[:5],
                sorted(set(records) - expected_tasks)[:5],
            )
        )
    ordered = [records[task] for task in sorted(records)]
    validate_main_partition_attestation(
        ordered, launch_receipt, mutation_receipt
    )
    return ordered


def scheduler_records(
    job_id: str,
    expected_tasks: set[int],
    launch_receipt: dict,
    mutation_receipt: dict,
) -> list[dict]:
    if job_id != launch_receipt["job_id"]:
        raise RecoveryError("job ID differs from the sealed main-array launch receipt")
    try:
        queued = subprocess.run(
            ["squeue", "-h", "-r", "-j", job_id, "-o", "%i|%T"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("cannot query squeue") from err
    if queued.stdout.strip():
        raise RecoveryError("array is still present in squeue; recovery is premature")
    try:
        result = subprocess.run(
            [
                "sacct",
                "-n",
                "-X",
                "-j",
                job_id,
                "--format={}".format(MAIN_SACCT_FORMAT),
                "-P",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("cannot query sacct") from err
    return parse_sacct(
        result.stdout,
        job_id,
        expected_tasks,
        launch_receipt,
        mutation_receipt,
    )


def dependency_records(protocol_revision: str) -> dict:
    result = {}
    for path in DEPENDENCY_PATHS:
        relative = path.relative_to(REPO).as_posix()
        current = sha256_file(path)
        if not JJ.file_is_tracked_at(REPO, protocol_revision, relative):
            raise RecoveryError("recovery dependency is not committed: {}".format(relative))
        if JJ.tracked_file_sha256(REPO, protocol_revision, relative) != current:
            raise RecoveryError("working bytes differ from committed dependency: {}".format(relative))
        result[relative] = {"sha256": current, "size": path.stat().st_size}
    return result


def verify_dependencies(manifest: dict) -> None:
    expected = manifest["dependencies"]
    if set(expected) != {path.relative_to(REPO).as_posix() for path in DEPENDENCY_PATHS}:
        raise RecoveryError("frozen recovery dependency set changed")
    recovery_relative = Path(__file__).resolve().relative_to(REPO).as_posix()
    for relative, record in expected.items():
        path = REPO / relative
        if path.stat().st_size == record["size"] and sha256_file(path) == record["sha256"]:
            continue
        if relative != recovery_relative:
            raise RecoveryError("recovery dependency changed: {}".format(relative))
        amendment_path = wave_array_limit_amendment_path(1)
        amendment = load_canonical_artifact(
            amendment_path, ARRAY_LIMIT_AMENDMENT_SCHEMA
        )
        validate_protocol_dependency_amendment(
            amendment.get("protocol_dependency_amendment"), manifest
        )


def _normalized_distribution_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _pinned_requirements() -> list[tuple[str, str]]:
    try:
        lines = REQUIREMENTS.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as err:
        raise RecoveryError("cannot read the frozen Python requirements") from err
    result = []
    seen = set()
    for line in lines:
        match = re.fullmatch(
            r"([A-Za-z0-9][A-Za-z0-9._-]*)==([A-Za-z0-9][A-Za-z0-9.!+_-]*)",
            line,
        )
        if match is None:
            raise RecoveryError("requirements must contain only exact package pins")
        name, version = match.groups()
        normalized = _normalized_distribution_name(name)
        if normalized in seen:
            raise RecoveryError("requirements repeat a distribution")
        seen.add(normalized)
        result.append((name, version))
    if not result:
        raise RecoveryError("requirements contain no pinned distributions")
    return result


def _required_distributions_identity(site_packages: Path) -> tuple[list[dict], list[list]]:
    try:
        candidates = list(importlib.metadata.distributions(path=[str(site_packages)]))
    except Exception as err:
        raise RecoveryError("cannot enumerate the frozen Python environment") from err
    installed = {}
    for distribution in candidates:
        name = distribution.metadata.get("Name")
        if not name:
            continue
        normalized = _normalized_distribution_name(name)
        if normalized in installed:
            raise RecoveryError("Python environment repeats distribution {}".format(name))
        installed[normalized] = distribution

    venv_root = VENV_PYTHON.parent.parent.resolve(strict=True)
    packages = []
    all_files = {}
    for required_name, required_version in _pinned_requirements():
        normalized = _normalized_distribution_name(required_name)
        distribution = installed.get(normalized)
        if distribution is None or distribution.version != required_version:
            raise RecoveryError(
                "Python distribution {} does not match requirements".format(required_name)
            )
        package_files = []
        for entry in distribution.files or ():
            entry_text = str(entry)
            if "__pycache__" in PurePosixPath(entry_text).parts or entry_text.endswith(
                ".pyc"
            ):
                continue
            path = Path(distribution.locate_file(entry))
            try:
                status = path.lstat()
                resolved = path.resolve(strict=True)
                resolved.relative_to(venv_root)
            except (OSError, ValueError) as err:
                raise RecoveryError(
                    "installed file for {} escaped the frozen environment".format(
                        required_name
                    )
                ) from err
            if stat.S_ISLNK(status.st_mode) or not stat.S_ISREG(status.st_mode):
                raise RecoveryError(
                    "installed file for {} is not a regular file".format(required_name)
                )
            record = [str(resolved), sha256_file(resolved), resolved.stat().st_size]
            previous = all_files.setdefault(record[0], record)
            if previous != record:
                raise RecoveryError("installed distributions disagree on a shared file")
            package_files.append(record)
        package_files.sort()
        if not package_files:
            raise RecoveryError(
                "installed distribution {} has no recorded files".format(required_name)
            )
        packages.append(
            {
                "requirement": "{}=={}".format(required_name, required_version),
                "installed_name": distribution.metadata["Name"],
                "installed_version": distribution.version,
                "files": len(package_files),
                "tree_sha256": sha256_bytes(canonical_bytes(package_files)),
            }
        )
    return packages, sorted(all_files.values())


def _validator_identity(path_environment: str) -> dict:
    if (
        not isinstance(path_environment, str)
        or not path_environment
        or "\n" in path_environment
        or "\r" in path_environment
    ):
        raise RecoveryError("cannot seal the recovery PATH environment")
    chosen_name = None
    chosen_path = None
    for candidate in ("validate", "Validate"):
        resolved = shutil.which(candidate, path=path_environment)
        if resolved is not None:
            chosen_name = candidate
            chosen_path = Path(resolved)
            break
    if chosen_path is None:
        return {
            "available": False,
            "candidate": None,
            "path": None,
            "size": None,
            "sha256": None,
        }
    try:
        status = chosen_path.lstat()
        canonical = chosen_path.resolve(strict=True)
    except OSError as err:
        raise RecoveryError("cannot inspect the external plan validator") from err
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or canonical != chosen_path
        or not os.access(chosen_path, os.X_OK)
    ):
        raise RecoveryError("external plan validator is not a canonical executable file")
    return {
        "available": True,
        "candidate": chosen_name,
        "path": str(chosen_path),
        "size": chosen_path.stat().st_size,
        "sha256": sha256_file(chosen_path),
    }


def runtime_identity(
    *,
    path_environment: str | None = None,
    ld_library_path: str | None = None,
) -> dict:
    try:
        python_status = VENV_PYTHON.lstat()
        python_link_target = os.readlink(VENV_PYTHON)
        python_resolved = VENV_PYTHON.resolve(strict=True)
    except OSError as err:
        raise RecoveryError("frozen experiment Python is absent") from err
    if not stat.S_ISLNK(python_status.st_mode) or not python_resolved.is_file():
        raise RecoveryError("frozen experiment Python is absent")
    code = (
        "import importlib.metadata,platform;"
        "print(platform.python_version());"
        "print(importlib.metadata.version('lab'))"
    )
    try:
        result = subprocess.run(
            [str(VENV_PYTHON), "-c", code],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("cannot attest the recovery Python/Lab runtime") from err
    lines = result.stdout.splitlines()
    if len(lines) != 2:
        raise RecoveryError("recovery runtime identity is malformed")
    lab_root = VENV_PYTHON.parent.parent / "lib" / "python{}".format(
        ".".join(lines[0].split(".")[:2])
    ) / "site-packages" / "lab"
    distribution_root = lab_root.parent / "lab-{}.dist-info".format(lines[1])
    required_distributions, required_distribution_files = (
        _required_distributions_identity(lab_root.parent)
    )
    lab_records = [
        record
        for record in snapshot_tree(lab_root)
        if "__pycache__" not in PurePosixPath(record["path"]).parts
        and not record["path"].endswith(".pyc")
    ]
    distribution_records = snapshot_tree(distribution_root)
    runtime_records = [
        {**record, "path": "lab/" + record["path"]} for record in lab_records
    ] + [
        {**record, "path": "dist-info/" + record["path"]}
        for record in distribution_records
    ]
    runtime_files = sorted(
        [
            [str(lab_root / record["path"]), record["sha256"], record["size"]]
            for record in lab_records
            if record["type"] == "file"
        ]
        + [
            [
                str(distribution_root / record["path"]),
                record["sha256"],
                record["size"],
            ]
            for record in distribution_records
            if record["type"] == "file"
        ]
    )
    if path_environment is None or ld_library_path is None:
        receipt = load_slurm_runtime_receipt()
        if path_environment is None:
            path_environment = receipt["effective_path"]
        if ld_library_path is None:
            ld_library_path = receipt["effective_ld_library_path"]
    if (
        not isinstance(ld_library_path, str)
        or not ld_library_path
        or "\n" in ld_library_path
        or "\r" in ld_library_path
    ):
        raise RecoveryError("cannot seal the recovery loader environment")
    return {
        "python_executable": str(VENV_PYTHON),
        "python_link_target": python_link_target,
        "python_resolved_path": str(python_resolved),
        "python_sha256": sha256_file(python_resolved),
        "python_version": lines[0],
        "lab_version": lines[1],
        "lab_package_path": str(lab_root),
        "lab_distribution_path": str(distribution_root),
        "lab_runtime_tree_sha256": snapshot_digest(runtime_records),
        "lab_runtime_entries": len(runtime_records),
        "lab_runtime_files": runtime_files,
        "required_distributions": required_distributions,
        "required_distribution_files": required_distribution_files,
        "required_distribution_tree_sha256": sha256_bytes(
            canonical_bytes(required_distribution_files)
        ),
        "execution_environment": {
            "path": path_environment,
            "ld_library_path": ld_library_path,
            "python_no_user_site": "1",
            "unset_variables": [
                "LD_PRELOAD",
                "PYTHONHOME",
                "PYTHONPATH",
                "PYTHONSTARTUP",
                "PYTHONUSERBASE",
            ],
            "validator": _validator_identity(path_environment),
        },
        "controller_python_version": platform.python_version(),
    }


def materialized_code_identity() -> dict:
    cached = E.cached_revision(require_hashes=True)
    code_dir = DATA_DIR / "code-{}".format(cached.name)
    records = snapshot_tree(code_dir)
    binary = code_dir / "builds" / "release_no_lp" / "bin" / "downward"
    preprocess = code_dir / "builds" / "release_no_lp" / "bin" / "preprocess"
    driver = code_dir / "fast-downward.py"
    driver_root = code_dir / "driver"
    translator_root = code_dir / "builds" / "release_no_lp" / "bin" / "translate"
    execution_paths = [driver, binary, preprocess]
    for root in (driver_root, translator_root):
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if "__pycache__" in relative.parts or path.suffix == ".pyc":
                continue
            try:
                status = path.lstat()
            except OSError as err:
                raise RecoveryError("cannot inspect materialized execution tree") from err
            if stat.S_ISDIR(status.st_mode):
                continue
            if not stat.S_ISREG(status.st_mode):
                raise RecoveryError("materialized execution tree contains a special entry")
            execution_paths.append(path)
    execution_files = []
    for path in sorted(set(execution_paths)):
        try:
            status = path.lstat()
        except OSError as err:
            raise RecoveryError("materialized execution file disappeared") from err
        if not stat.S_ISREG(status.st_mode):
            raise RecoveryError("materialized execution dependency is not a regular file")
        execution_files.append([str(path), sha256_file(path), path.stat().st_size])
    identity = {
        "path": str(code_dir),
        "tree_sha256": snapshot_digest(records),
        "files": len(records),
        "fast_downward_path": str(driver),
        "fast_downward_sha256": sha256_file(driver),
        "downward_path": str(binary),
        "downward_sha256": sha256_file(binary),
        "preprocess_path": str(preprocess),
        "preprocess_sha256": sha256_file(preprocess),
        "execution_files": execution_files,
        "execution_files_sha256": sha256_bytes(canonical_bytes(execution_files)),
    }
    if (
        identity["downward_sha256"] != E.PLANNER_BINARY_SHA256
        or identity["preprocess_sha256"] != E.PREPROCESS_BINARY_SHA256
    ):
        raise RecoveryError("materialized experiment binaries changed")
    return identity


def external_input_identity() -> dict:
    inputs = {
        "revision_cache": str(E.REVISION_CACHE),
        "benchmark_root": str(E.BENCHMARKS),
        "cohort_archive": {
            "path": str(E.COHORT_ARCHIVE),
            "size": E.COHORT_ARCHIVE.stat().st_size,
            "sha256": sha256_file(E.COHORT_ARCHIVE),
        },
        "matched_budget_archive": {
            "path": str(E.MATCH_ARCHIVE),
            "size": E.MATCH_ARCHIVE.stat().st_size,
            "sha256": sha256_file(E.MATCH_ARCHIVE),
        },
    }
    if inputs["cohort_archive"]["sha256"] != P.COHORT_ARCHIVE_SHA256:
        raise RecoveryError("cohort archive differs from its frozen digest")
    if inputs["matched_budget_archive"]["sha256"] != P.MATCH_ARCHIVE_SHA256:
        raise RecoveryError("matched-budget archive differs from its frozen digest")
    return inputs


def _single_driver_command(run_script: Path) -> list[str]:
    try:
        source = run_script.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(run_script))
    except (OSError, UnicodeDecodeError, SyntaxError) as err:
        raise RecoveryError("cannot parse generated run script {}".format(run_script)) from err
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Call"
    ]
    if len(calls) != 1 or len(calls[0].args) != 1:
        raise RecoveryError("generated run script has an unexpected Call contract")
    command_node = calls[0].args[0]
    if not isinstance(command_node, (ast.List, ast.Tuple)):
        raise RecoveryError("generated run command is not a literal sequence")
    command = []
    for item in command_node.elts:
        if not isinstance(item, ast.Constant) or not isinstance(item.value, str):
            raise RecoveryError("generated run command contains a nonliteral argument")
        command.append(item.value)
    return command


def _resolved_benchmark_identity(link: Path, expected_root: Path) -> dict:
    try:
        status = link.lstat()
        target_text = os.readlink(link)
        resolved = link.resolve(strict=True)
        relative = resolved.relative_to(expected_root.resolve(strict=True))
    except (OSError, ValueError) as err:
        raise RecoveryError("benchmark link escaped its frozen root: {}".format(link)) from err
    if not stat.S_ISLNK(status.st_mode) or not resolved.is_file():
        raise RecoveryError("benchmark input is not a live symlink: {}".format(link))
    return {
        "link_target": target_text,
        "resolved_path": str(resolved),
        "benchmark_relative_path": relative.as_posix(),
        "size": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def cell_execution_identity(
    run_id: int, materialized: dict, source_records: dict[tuple[str, str], dict]
) -> dict:
    root = _safe_run_root(run_id)
    run_script = root / "run"
    static_properties = root / "static-properties"
    command = _single_driver_command(run_script)
    expected_prefix = [str(VENV_PYTHON), materialized["fast_downward_path"]]
    if command[:2] != expected_prefix:
        raise RecoveryError("run {} references a different runtime or source tree".format(run_id))
    if command.count("--validate") != 1:
        raise RecoveryError("run {} does not require plan validation".format(run_id))
    required_pairs = {
        "--overall-time-limit": "{}s".format(P.TIME_LIMIT_SECONDS),
        "--overall-memory-limit": "{}M".format(P.MEMORY_LIMIT_MIB),
        "--build": "release_no_lp",
    }
    for option, expected in required_pairs.items():
        if command.count(option) != 1:
            raise RecoveryError("run {} changed option {}".format(run_id, option))
        index = command.index(option)
        if index + 1 >= len(command) or command[index + 1] != expected:
            raise RecoveryError("run {} changed value for {}".format(run_id, option))
    if command.count("domain.pddl") != 1 or command.count("problem.pddl") != 1:
        raise RecoveryError("run {} changed its PDDL command arguments".format(run_id))
    try:
        properties = json.loads(static_properties.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RecoveryError("run {} has invalid static properties".format(run_id)) from err
    task = (properties.get("domain"), properties.get("problem"))
    record = source_records.get(task)
    if record is None:
        raise RecoveryError("run {} task is absent from the frozen source manifest".format(run_id))
    label = properties.get("algorithm")
    expected_search = P.SEARCHES.get(label)
    static_expected = {
        "id": [label, *task],
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "planner_revision": E.PLANNER_REVISION,
        "local_revision": E.PLANNER_REVISION,
        "global_revision": E.PLANNER_REVISION,
        "planner_binary_sha256": E.PLANNER_BINARY_SHA256,
        "preprocess_binary_sha256": E.PREPROCESS_BINARY_SHA256,
        "planner_preprocess_sha256": E.PREPROCESS_BINARY_SHA256,
        "required_lab_version": P.REQUIRED_LAB_VERSION,
        "build_options": list(P.BUILD_OPTIONS),
        "driver_options": [
            "--validate",
            "--overall-time-limit",
            "{}s".format(P.TIME_LIMIT_SECONDS),
            "--overall-memory-limit",
            "{}M".format(P.MEMORY_LIMIT_MIB),
            "--build",
            "release_no_lp",
        ],
        "component_options": ["--search", expected_search],
        "run_dir": run_relative(run_id).as_posix(),
    }
    if expected_search is None or any(
        properties.get(key) != value for key, value in static_expected.items()
    ):
        raise RecoveryError("run {} static execution contract changed".format(run_id))
    if command.count("--search") != 1:
        raise RecoveryError("run {} changed its search option".format(run_id))
    search_index = command.index("--search")
    if search_index + 1 >= len(command) or command[search_index + 1] != expected_search:
        raise RecoveryError("run {} command and static search disagree".format(run_id))
    expected_command = [
        *expected_prefix,
        "--validate",
        "--overall-time-limit",
        "{}s".format(P.TIME_LIMIT_SECONDS),
        "--overall-memory-limit",
        "{}M".format(P.MEMORY_LIMIT_MIB),
        "--build",
        "release_no_lp",
        "domain.pddl",
        "problem.pddl",
        "--search",
        expected_search,
    ]
    if command != expected_command:
        raise RecoveryError("run {} changed its exact driver command".format(run_id))
    domain = _resolved_benchmark_identity(root / "domain.pddl", E.BENCHMARKS)
    problem = _resolved_benchmark_identity(root / "problem.pddl", E.BENCHMARKS)
    expected_paths = {
        "domain": (record["domain_file"], record["domain_sha256"]),
        "problem": (record["problem_file"], record["problem_sha256"]),
    }
    for name, identity in (("domain", domain), ("problem", problem)):
        relative, digest = expected_paths[name]
        if (
            identity["benchmark_relative_path"] != relative
            or identity["sha256"] != digest
        ):
            raise RecoveryError("run {} {} input changed".format(run_id, name))
    return {
        "run_sha256": sha256_file(run_script),
        "run_size": run_script.stat().st_size,
        "static_properties_sha256": sha256_file(static_properties),
        "static_properties_size": static_properties.stat().st_size,
        "domain": domain,
        "problem": problem,
    }


def source_manifest_records() -> dict[tuple[str, str], dict]:
    try:
        data = S.load_manifest()
    except RuntimeError as err:
        raise RecoveryError("source manifest validation failed") from err
    return {
        (record["domain"], record["problem"]): record for record in data["tasks"]
    }


def classify_cells(
    scheduler: list[dict],
    group_to_slot: dict[int, int],
    materialized: dict,
    source_records: dict[tuple[str, str], dict],
) -> tuple[dict, list[list], list[dict]]:
    states = {record["array_task_id"]: record["state_base"] for record in scheduler}
    counts = Counter()
    complete_hashes = []
    recovery = []
    for run_id in range(1, P.CELL_COUNT + 1):
        root = _safe_run_root(run_id)
        records = snapshot_tree(root)
        validate_static_inputs(root, records)
        driver = root / "driver.log"
        if not driver.exists() and not driver.is_symlink():
            if dynamic_top_names(records):
                raise RecoveryError("unstarted cell {} has dynamic files".format(run_id))
            status_name = "missing"
        elif driver_log_complete(driver):
            status_name = "complete"
        else:
            status_name = "interrupted"
        counts[status_name] += 1
        task_id = array_task_for_run(run_id, group_to_slot)
        task_state = states.get(task_id)
        if task_state is None:
            raise RecoveryError("cell maps to an absent scheduler task")
        digest = snapshot_digest(records)
        if status_name == "complete":
            complete_hashes.append([run_id, digest])
            continue
        require_recoverable_cell_state(
            task_id, task_state, "{} cell {}".format(status_name, run_id)
        )
        recovery.append(
            {
                "run_id": run_id,
                "run_dir": run_relative(run_id).as_posix(),
                "original_array_task_id": task_id,
                "original_status": status_name,
                "tree_sha256": digest,
                "entries": records,
                "dynamic_top_names": dynamic_top_names(records),
                "execution_inputs": cell_execution_identity(
                    run_id, materialized, source_records
                ),
            }
        )
    unsupported = [
        record
        for record in scheduler
        if record["state_base"] not in RECOVERABLE_STATES | {"COMPLETED"}
    ]
    if unsupported:
        raise RecoveryError("unsupported terminal state: {}".format(unsupported[0]["state"]))
    if len(complete_hashes) + len(recovery) != P.CELL_COUNT:
        raise RecoveryError("cell classification did not cover the frozen matrix")
    return dict(sorted(counts.items())), complete_hashes, recovery


def recovery_nonce(main_job_id: str, launcher_sha: str, dependencies: dict, cells: list[dict]) -> str:
    payload = {
        "main_job_id": main_job_id,
        "launcher_sha256": launcher_sha,
        "dependencies": dependencies,
        "cells": [[cell["run_id"], cell["tree_sha256"]] for cell in cells],
    }
    return sha256_bytes(canonical_bytes(payload))[:16]


def wave_directory(wave: int) -> Path:
    if type(wave) is not int or not 1 <= wave <= 9999:
        raise RecoveryError("recovery wave number is invalid")
    return WAVES_DIR / "wave-{:04d}".format(wave)


def wave_manifest_path(wave: int) -> Path:
    return wave_directory(wave) / "wave-manifest.json"


def wave_runner_path(wave: int) -> Path:
    return wave_directory(wave) / "recover-cells.sh"


def wave_intent_path(wave: int) -> Path:
    return wave_directory(wave) / "submit-intent.json"


def wave_receipt_path(wave: int) -> Path:
    return wave_directory(wave) / "submit-receipt.json"


def wave_array_limit_amendment_path(wave: int) -> Path:
    return wave_directory(wave) / "array-limit-amendment.json"


def wave_batch_runner_path(wave: int) -> Path:
    return wave_directory(wave) / "recover-cell-batches.sh"


def wave_amended_intent_path(wave: int) -> Path:
    return wave_directory(wave) / "submit-intent-array-limit.json"


def wave_amended_receipt_path(wave: int) -> Path:
    return wave_directory(wave) / "submit-receipt-array-limit.json"


def _has_array_limit_amendment(wave: int) -> bool:
    path = wave_array_limit_amendment_path(wave)
    return path.exists() or path.is_symlink()


def submission_intent_path(wave: int) -> Path:
    if _has_array_limit_amendment(wave):
        return wave_amended_intent_path(wave)
    return wave_intent_path(wave)


def submission_receipt_path(wave: int) -> Path:
    if _has_array_limit_amendment(wave):
        return wave_amended_receipt_path(wave)
    return wave_receipt_path(wave)


def validate_protocol_dependency_amendment(value, manifest: dict) -> None:
    required = {
        "path",
        "frozen_sha256",
        "frozen_size",
        "amended_sha256",
        "amended_size",
        "amended_code_commit",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise RecoveryError("array-limit protocol dependency amendment changed")
    relative = Path(__file__).resolve().relative_to(REPO).as_posix()
    frozen = manifest["dependencies"].get(relative)
    if (
        frozen is None
        or value["path"] != relative
        or value["frozen_sha256"] != frozen["sha256"]
        or value["frozen_size"] != frozen["size"]
        or SHA256_RE.fullmatch(value.get("amended_sha256", "")) is None
        or type(value.get("amended_size")) is not int
        or value["amended_size"] < 1
        or JJ.COMMIT_RE.fullmatch(value.get("amended_code_commit", "")) is None
    ):
        raise RecoveryError("array-limit protocol dependency amendment is invalid")
    path = REPO / relative
    if (
        path.stat().st_size != value["amended_size"]
        or sha256_file(path) != value["amended_sha256"]
        or not JJ.file_is_tracked_at(
            REPO, value["amended_code_commit"], relative
        )
        or JJ.tracked_file_sha256(
            REPO, value["amended_code_commit"], relative
        )
        != value["amended_sha256"]
    ):
        raise RecoveryError("amended recovery protocol bytes changed")
    JJ.require_ancestor(
        REPO, value["amended_code_commit"], JJ.current_commit(REPO)
    )


def wave_ready_path(wave: int) -> Path:
    return wave_directory(wave) / "archive-ready.json"


def any_submission_state() -> bool:
    if not WAVES_DIR.exists():
        return False
    _lstat_directory(WAVES_DIR, "recovery waves")
    return any(
        wave_intent_path(wave).exists()
        or wave_intent_path(wave).is_symlink()
        or wave_receipt_path(wave).exists()
        or wave_receipt_path(wave).is_symlink()
        for wave in range(1, 10000)
        if wave_directory(wave).exists()
    )


def _shell_single_quote(value: str) -> str:
    if "'" in value or "\n" in value or "\r" in value:
        raise RecoveryError("recovery path cannot be represented safely in Bash")
    return "'{}'".format(value)


def wave_job_name(wave: int, nonce: str) -> str:
    return "pdbprof-w{:02d}-{}".format(wave, nonce[:12])


def runner_text(run_ids: list[int], nonce: str, wave: int, manifest: dict) -> str:
    if not run_ids:
        raise RecoveryError("cannot generate an empty recovery wave")
    cells = {cell["run_id"]: cell for cell in manifest["recovery_cells"]}
    if set(run_ids) - set(cells):
        raise RecoveryError("runner references a cell outside the base recovery set")
    directories = [str(_safe_run_root(run_id)) for run_id in run_ids]
    identities = [cells[run_id]["execution_inputs"] for run_id in run_ids]
    materialized = manifest["materialized_code"]
    runtime = manifest["runtime"]
    wave_dir = wave_directory(wave)
    lock_dir = wave_dir / "locks"
    return """#!/bin/bash -l
#SBATCH --job-name={job_name}
#SBATCH --output={wave_dir}/recovery-slurm-%A_%a.log
#SBATCH --error={wave_dir}/recovery-slurm-%A_%a.err
#SBATCH --open-mode=append
#SBATCH --partition=cpu
#SBATCH --qos=normal
#SBATCH --time={wall}
#SBATCH --mem-per-cpu={memory}
#SBATCH --cpus-per-task=1
#SBATCH --array=1-{count}%{throttle}
#SBATCH --account={account}
#SBATCH --no-requeue

set -euo pipefail
umask 022
ulimit -Sv 9248440
PATH={sealed_path}
export PATH
LD_LIBRARY_PATH={sealed_ld_library_path}
export LD_LIBRARY_PATH
unset {unset_variables}
PYTHONNOUSERSITE=1
export PYTHONNOUSERSITE
RUN_IDS=({ids})
RUN_DIRS=({directories})
RUN_HASHES=({run_hashes})
STATIC_HASHES=({static_hashes})
DOMAIN_PATHS=({domain_paths})
DOMAIN_HASHES=({domain_hashes})
PROBLEM_PATHS=({problem_paths})
PROBLEM_HASHES=({problem_hashes})
RUNTIME_PATHS=({runtime_paths})
RUNTIME_HASHES=({runtime_hashes})
PACKAGE_PATHS=({package_paths})
PACKAGE_HASHES=({package_hashes})
CODE_PATHS=({code_paths})
CODE_HASHES=({code_hashes})
LOCK_DIR={lock_dir}
PYTHON={python}
PYTHON_LINK_TARGET={python_link_target}
PYTHON_RESOLVED={python_resolved}
PYTHON_SHA256={python_hash}
FAST_DOWNWARD={fast_downward}
FAST_DOWNWARD_SHA256={fast_downward_hash}
DOWNWARD={downward}
DOWNWARD_SHA256={downward_hash}
PREPROCESS={preprocess}
PREPROCESS_SHA256={preprocess_hash}
VALIDATOR_AVAILABLE={validator_available}
VALIDATOR_PATH={validator_path}
VALIDATOR_SHA256={validator_hash}

fail() {{
    printf '%s\\n' "$1" >&2
    exit 2
}}

require_hash() {{
    local path=$1
    local expected=$2
    [[ -f "$path" && ! -L "$path" ]] || fail "required regular file changed: $path"
    local actual
    actual=$(sha256sum -- "$path") || fail "cannot hash required file: $path"
    actual=${{actual%% *}}
    [[ "$actual" == "$expected" ]] || fail "required file hash changed: $path"
}}

driver_complete() {{
    local path=$1
    [[ -f "$path" && ! -L "$path" ]] || return 1
    tail -n 1 -- "$path" | LC_ALL=C grep -Eq \\
        '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}} [0-9]{{2}}:[0-9]{{2}}:[0-9]{{2}},[0-9]{{3}} INFO[[:space:]]+planner exit code: -?[0-9]+$'
}}

resolved_validator() {{
    local actual
    actual=$(command -v validate 2>/dev/null || true)
    if [[ -z "$actual" ]]; then
        actual=$(command -v Validate 2>/dev/null || true)
    fi
    printf '%s' "$actual"
}}

attest_validator() {{
    local actual
    actual=$(resolved_validator)
    if [[ "$VALIDATOR_AVAILABLE" == 0 ]]; then
        [[ -z "$actual" ]] || fail 'an unsealed external plan validator appeared on PATH'
    else
        [[ "$actual" == "$VALIDATOR_PATH" ]] || fail 'external plan validator path changed'
        require_hash "$VALIDATOR_PATH" "$VALIDATOR_SHA256"
    fi
}}

attest_inputs() {{
    [[ -d "$RUN_DIR" && ! -L "$RUN_DIR" ]] || fail "recovery run directory changed"
    [[ "$(readlink -f -- "$RUN_DIR")" == "$RUN_DIR" ]] || fail "recovery run path traverses a symlink"
    [[ -L "$PYTHON" ]] || fail 'recovery Python is no longer a symlink'
    [[ "$(readlink -- "$PYTHON")" == "$PYTHON_LINK_TARGET" ]] || fail 'recovery Python link target changed'
    [[ "$(readlink -f -- "$PYTHON")" == "$PYTHON_RESOLVED" ]] || fail 'resolved recovery Python path changed'
    require_hash "$PYTHON_RESOLVED" "$PYTHON_SHA256"
    for runtime_index in "${{!RUNTIME_PATHS[@]}}"; do
        require_hash "${{RUNTIME_PATHS[$runtime_index]}}" "${{RUNTIME_HASHES[$runtime_index]}}"
    done
    for package_index in "${{!PACKAGE_PATHS[@]}}"; do
        require_hash "${{PACKAGE_PATHS[$package_index]}}" "${{PACKAGE_HASHES[$package_index]}}"
    done
    for code_index in "${{!CODE_PATHS[@]}}"; do
        require_hash "${{CODE_PATHS[$code_index]}}" "${{CODE_HASHES[$code_index]}}"
    done
    attest_validator
    require_hash "$FAST_DOWNWARD" "$FAST_DOWNWARD_SHA256"
    require_hash "$DOWNWARD" "$DOWNWARD_SHA256"
    require_hash "$PREPROCESS" "$PREPROCESS_SHA256"
    require_hash "$RUN_DIR/run" "${{RUN_HASHES[$INDEX]}}"
    require_hash "$RUN_DIR/static-properties" "${{STATIC_HASHES[$INDEX]}}"
    [[ -L "$RUN_DIR/domain.pddl" ]] || fail 'domain input is no longer a symlink'
    [[ -L "$RUN_DIR/problem.pddl" ]] || fail 'problem input is no longer a symlink'
    [[ "$(readlink -f -- "$RUN_DIR/domain.pddl")" == "${{DOMAIN_PATHS[$INDEX]}}" ]] || fail 'resolved domain path changed'
    [[ "$(readlink -f -- "$RUN_DIR/problem.pddl")" == "${{PROBLEM_PATHS[$INDEX]}}" ]] || fail 'resolved problem path changed'
    require_hash "${{DOMAIN_PATHS[$INDEX]}}" "${{DOMAIN_HASHES[$INDEX]}}"
    require_hash "${{PROBLEM_PATHS[$INDEX]}}" "${{PROBLEM_HASHES[$INDEX]}}"
}}

INDEX=$((SLURM_ARRAY_TASK_ID - 1))
if [[ $INDEX -lt 0 || $INDEX -ge ${{#RUN_IDS[@]}} ]]; then
    fail 'invalid recovery array index'
fi
RUN_ID=${{RUN_IDS[$INDEX]}}
RUN_DIR=${{RUN_DIRS[$INDEX]}}
[[ -d "$LOCK_DIR" && ! -L "$LOCK_DIR" ]] || fail 'recovery lock directory changed'
[[ "$(readlink -f -- "$LOCK_DIR")" == "$LOCK_DIR" ]] || fail 'recovery lock path traverses a symlink'
command -v flock >/dev/null || fail 'flock is unavailable'
exec 9>"$LOCK_DIR/$RUN_ID.lock"
flock -n 9 || fail "recovery cell $RUN_ID is already locked"

attest_inputs

if driver_complete "$RUN_DIR/driver.log"; then
    printf 'recovery run %s was already completed by the same sealed wave\\n' "$RUN_ID"
    exit 0
fi
if [[ -e "$RUN_DIR/driver.log" || -L "$RUN_DIR/driver.log" ]]; then
    fail "recovery run $RUN_ID has an incomplete driver.log"
fi
shopt -s dotglob nullglob
for entry in "$RUN_DIR"/*; do
    case "${{entry##*/}}" in
        domain.pddl|problem.pddl|run|static-properties) ;;
        *) fail "recovery run $RUN_ID has unexpected dynamic output" ;;
    esac
done
shopt -u dotglob nullglob
cd "$RUN_DIR"
set +e
"$PYTHON" run > driver.log 2> driver.err
RETCODE=$?
set -e
attest_inputs
if [[ $RETCODE -ne 0 ]]; then
    printf 'recovery wrapper failed for run %s\\n' "$RUN_ID" >&2
    exit "$RETCODE"
fi
driver_complete driver.log || fail "recovery run $RUN_ID lacks its final driver sentinel"
""".format(
        job_name=wave_job_name(wave, nonce),
        wave_dir=wave_dir,
        wall=RECOVERY_WALL_TIME,
        memory=RECOVERY_MEMORY,
        count=len(run_ids),
        throttle=E.ARRAY_THROTTLE,
        account=E.ACCOUNT,
        ids=" ".join(map(str, run_ids)),
        directories=" ".join(_shell_single_quote(value) for value in directories),
        run_hashes=" ".join(item["run_sha256"] for item in identities),
        static_hashes=" ".join(item["static_properties_sha256"] for item in identities),
        domain_paths=" ".join(
            _shell_single_quote(item["domain"]["resolved_path"]) for item in identities
        ),
        domain_hashes=" ".join(item["domain"]["sha256"] for item in identities),
        problem_paths=" ".join(
            _shell_single_quote(item["problem"]["resolved_path"]) for item in identities
        ),
        problem_hashes=" ".join(item["problem"]["sha256"] for item in identities),
        runtime_paths=" ".join(
            _shell_single_quote(item[0]) for item in runtime["lab_runtime_files"]
        ),
        runtime_hashes=" ".join(item[1] for item in runtime["lab_runtime_files"]),
        package_paths=" ".join(
            _shell_single_quote(item[0])
            for item in runtime["required_distribution_files"]
        ),
        package_hashes=" ".join(
            item[1] for item in runtime["required_distribution_files"]
        ),
        code_paths=" ".join(
            _shell_single_quote(item[0]) for item in materialized["execution_files"]
        ),
        code_hashes=" ".join(item[1] for item in materialized["execution_files"]),
        lock_dir=_shell_single_quote(str(lock_dir)),
        python=_shell_single_quote(runtime["python_executable"]),
        python_link_target=_shell_single_quote(runtime["python_link_target"]),
        python_resolved=_shell_single_quote(runtime["python_resolved_path"]),
        python_hash=runtime["python_sha256"],
        fast_downward=_shell_single_quote(materialized["fast_downward_path"]),
        fast_downward_hash=materialized["fast_downward_sha256"],
        downward=_shell_single_quote(materialized["downward_path"]),
        downward_hash=materialized["downward_sha256"],
        preprocess=_shell_single_quote(materialized["preprocess_path"]),
        preprocess_hash=materialized["preprocess_sha256"],
        sealed_path=_shell_single_quote(runtime["execution_environment"]["path"]),
        sealed_ld_library_path=_shell_single_quote(
            runtime["execution_environment"]["ld_library_path"]
        ),
        unset_variables=" ".join(
            runtime["execution_environment"]["unset_variables"]
        ),
        validator_available=(
            1 if runtime["execution_environment"]["validator"]["available"] else 0
        ),
        validator_path=_shell_single_quote(
            runtime["execution_environment"]["validator"]["path"] or ""
        ),
        validator_hash=(
            runtime["execution_environment"]["validator"]["sha256"] or ""
        ),
    )


def batch_runner_text(
    wave: dict,
    *,
    job_name: str,
    array_tasks: int,
    cells_per_array_task: int,
    srun_path: str,
    srun_sha256: str,
    env_path: str,
    env_sha256: str,
) -> str:
    legacy = wave["runner"]
    legacy_tasks = len(wave["run_ids"])
    if (
        type(array_tasks) is not int
        or type(cells_per_array_task) is not int
        or array_tasks < 1
        or cells_per_array_task < 2
        or array_tasks
        != (legacy_tasks + cells_per_array_task - 1) // cells_per_array_task
        or SAFE_NAME_RE.fullmatch(job_name) is None
        or any(
            not isinstance(path, str)
            or not Path(path).is_absolute()
            or "\n" in path
            or "\r" in path
            for path in (srun_path, env_path)
        )
        or any(
            SHA256_RE.fullmatch(digest or "") is None
            for digest in (srun_sha256, env_sha256)
        )
    ):
        raise RecoveryError("invalid recovery batching contract")
    legacy_path = wave_runner_path(wave["wave"])
    wave_dir = wave_directory(wave["wave"])
    index_setup = batch_array_index_setup_text(array_tasks)
    return """#!/bin/bash -l
#SBATCH --job-name={job_name}
#SBATCH --output={wave_dir}/recovery-batch-slurm-%A_%a.log
#SBATCH --error={wave_dir}/recovery-batch-slurm-%A_%a.err
#SBATCH --open-mode=append
#SBATCH --partition={partition}
#SBATCH --qos={qos}
#SBATCH --time={wall}
#SBATCH --mem-per-cpu={memory}
#SBATCH --cpus-per-task={batch_cpus}
#SBATCH --array=1-{array_tasks}%{throttle}
#SBATCH --account={account}
#SBATCH --no-requeue

set -euo pipefail
LEGACY_RUNNER={legacy_path}
LEGACY_RUNNER_SHA256={legacy_sha256}
SRUN={srun_path}
SRUN_SHA256={srun_sha256}
ENV={env_path}
ENV_SHA256={env_sha256}
LEGACY_TASKS={legacy_tasks}
CELLS_PER_ARRAY_TASK={cells_per_array_task}

fail() {{
    printf '%s\\n' "$1" >&2
    exit 2
}}

require_executable() {{
    local path=$1
    local expected=$2
    [[ -f "$path" && ! -L "$path" && -x "$path" ]] || fail "sealed executable changed: $path"
    local actual
    actual=$(sha256sum -- "$path") || fail "cannot hash sealed executable: $path"
    actual=${{actual%% *}}
    [[ "$actual" == "$expected" ]] || fail "sealed executable hash changed: $path"
}}

attest_batch_inputs() {{
    require_executable "$LEGACY_RUNNER" "$LEGACY_RUNNER_SHA256"
    require_executable "$SRUN" "$SRUN_SHA256"
    require_executable "$ENV" "$ENV_SHA256"
}}

attest_batch_inputs
{index_setup}
PIDS=()
for ((LEGACY_TASK=FIRST; LEGACY_TASK<=LAST; LEGACY_TASK++)); do
    (
        exec "$SRUN" --exclusive --exact --nodes=1 --ntasks=1 \
            --cpus-per-task=1 --mem-per-cpu={memory} --export=ALL \
            "$ENV" "SLURM_ARRAY_TASK_ID=$LEGACY_TASK" "$LEGACY_RUNNER"
    ) &
    PIDS+=("$!")
done
STATUS=0
for PID in "${{PIDS[@]}}"; do
    if wait "$PID"; then
        :
    else
        RETCODE=$?
        if [[ $STATUS -eq 0 ]]; then
            STATUS=$RETCODE
        fi
    fi
done
attest_batch_inputs
exit "$STATUS"
""".format(
        job_name=job_name,
        wave_dir=wave_dir,
        partition=legacy["partition"],
        qos=legacy["qos"],
        wall=legacy["wall_time"],
        memory=legacy["memory_per_cpu"],
        batch_cpus=cells_per_array_task * legacy["cpus_per_task"],
        array_tasks=array_tasks,
        throttle=max(1, E.ARRAY_THROTTLE // cells_per_array_task),
        account=legacy["account"],
        legacy_path=_shell_single_quote(str(legacy_path)),
        legacy_sha256=legacy["sha256"],
        srun_path=_shell_single_quote(srun_path),
        srun_sha256=srun_sha256,
        env_path=_shell_single_quote(env_path),
        env_sha256=env_sha256,
        legacy_tasks=legacy_tasks,
        cells_per_array_task=cells_per_array_task,
        index_setup=index_setup,
    )


def batch_array_index_setup_text(array_tasks: int) -> str:
    if type(array_tasks) is not int or array_tasks < 1:
        raise RecoveryError("invalid batched recovery array-task count")
    return """ARRAY_TASKS={array_tasks}
[[ $SLURM_ARRAY_TASK_ID =~ ^[1-9][0-9]*$ ]] || fail 'invalid batched recovery array index'
if (( ${{#SLURM_ARRAY_TASK_ID}} > ${{#ARRAY_TASKS}} )); then
    fail 'batched recovery array index is outside the sealed array range'
fi
if (( ${{#SLURM_ARRAY_TASK_ID}} == ${{#ARRAY_TASKS}} )) \
    && [[ "$SLURM_ARRAY_TASK_ID" > "$ARRAY_TASKS" ]]; then
    fail 'batched recovery array index is outside the sealed array range'
fi
FIRST=$(( (SLURM_ARRAY_TASK_ID - 1) * CELLS_PER_ARRAY_TASK + 1 ))
LAST=$(( FIRST + CELLS_PER_ARRAY_TASK - 1 ))
if [[ $FIRST -lt 1 || $FIRST -gt $LEGACY_TASKS ]]; then
    fail 'batched recovery array index is outside the sealed cell set'
fi
if [[ $LAST -gt $LEGACY_TASKS ]]; then
    LAST=$LEGACY_TASKS
fi""".format(array_tasks=array_tasks)


def build_wave(
    manifest: dict,
    manifest_digest: str,
    wave: int,
    run_ids: list[int],
    *,
    previous_wave,
    source_scheduler_records,
    source_cell_decisions: list[dict],
    retry_input_cells: list[dict],
    protected_recovered_cell_hashes: list[list],
    created_utc: str | None = None,
) -> tuple[dict, str]:
    input_digests = (
        [[cell["run_id"], cell["tree_sha256"]] for cell in manifest["recovery_cells"]]
        if wave == 1
        else [[cell["run_id"], cell["tree_sha256"]] for cell in retry_input_cells]
    )
    nonce_payload = {
        "manifest_sha256": manifest_digest,
        "wave": wave,
        "previous_wave": previous_wave,
        "run_ids": run_ids,
        "source_scheduler_records_sha256": sha256_bytes(
            canonical_bytes(source_scheduler_records)
        ),
        "source_cell_decisions": source_cell_decisions,
        "input_tree_hashes": input_digests,
        "protected_recovered_cell_hashes": protected_recovered_cell_hashes,
    }
    nonce = sha256_bytes(canonical_bytes(nonce_payload))[:16]
    runner = runner_text(run_ids, nonce, wave, manifest)
    contract = {
        "path": wave_runner_path(wave).relative_to(REPO).as_posix(),
        "size": len(runner.encode("ascii")),
        "sha256": sha256_bytes(runner.encode("ascii")),
        "nonce": nonce,
        "job_name": wave_job_name(wave, nonce),
        "array_spec": "1-{}%{}".format(len(run_ids), E.ARRAY_THROTTLE),
        "one_cell_per_array_task": True,
        "run_ids": run_ids,
        "wall_time": RECOVERY_WALL_TIME,
        "memory_per_cpu": RECOVERY_MEMORY,
        "cpus_per_task": 1,
        "partition": "cpu",
        "qos": "normal",
        "account": E.ACCOUNT,
        "requeue": False,
        "per_cell_flock": True,
        "pre_execution_byte_attestation": True,
        "post_execution_byte_attestation": True,
        "all_pinned_distribution_files_attested": True,
        "materialized_execution_files_attested": True,
        "submission_environment_export": "PATH",
        "sealed_effective_path": True,
        "validator_choice_attested_pre_and_post": True,
        "python_and_loader_overrides_sanitized": True,
    }
    value = {
        "schema": WAVE_SCHEMA,
        "created_utc": created_utc or utc_now(),
        "manifest_sha256": manifest_digest,
        "wave": wave,
        "previous_wave": previous_wave,
        "source_scheduler_records": source_scheduler_records,
        "source_cell_decisions": source_cell_decisions,
        "retry_input_cells": retry_input_cells,
        "protected_recovered_cell_hashes": protected_recovered_cell_hashes,
        "run_ids": run_ids,
        "outcome_access": {
            "planner_outcomes_parsed": False,
            "completion_test": "last-line-shape-only;numeric-exit-value-not-recorded/v1",
        },
        "retry_policy": recovery_retry_policy(),
        "runner": contract,
    }
    return value, runner


def _install_freeze_bundle(manifest: dict, wave: dict, runner: str) -> str:
    if ARTIFACT_DIR.exists():
        raise RecoveryError("recovery artifact directory already exists")
    ARTIFACT_DIR.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".pdb-profile-recovery-", dir=ARTIFACT_DIR.parent))
    try:
        wave_dir = stage / "waves" / "wave-0001"
        wave_dir.mkdir(parents=True)
        (wave_dir / "locks").mkdir()
        runner_path = wave_dir / "recover-cells.sh"
        runner_path.write_text(runner, encoding="ascii")
        runner_path.chmod(0o755)
        manifest_raw = canonical_bytes(manifest) + b"\n"
        digest = sha256_bytes(manifest_raw)
        (stage / MANIFEST.name).write_bytes(manifest_raw)
        (stage / MANIFEST.name).chmod(0o444)
        (stage / MANIFEST_SIDECAR.name).write_text(
            "{}  {}\n".format(digest, MANIFEST.name), encoding="ascii"
        )
        (stage / MANIFEST_SIDECAR.name).chmod(0o444)
        wave_raw = canonical_bytes(wave) + b"\n"
        (wave_dir / "wave-manifest.json").write_bytes(wave_raw)
        (wave_dir / "wave-manifest.json").chmod(0o444)
        for path in (runner_path, stage / MANIFEST.name, stage / MANIFEST_SIDECAR.name, wave_dir / "wave-manifest.json"):
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        _fsync_directory(wave_dir / "locks")
        _fsync_directory(wave_dir)
        _fsync_directory(stage / "waves")
        _fsync_directory(stage)
        os.replace(stage, ARTIFACT_DIR)
        _fsync_directory(ARTIFACT_DIR.parent)
        return digest
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise


def freeze(main_job_id: str) -> None:
    if JJ.working_copy_diff_summary(REPO):
        raise RecoveryError("freeze requires a clean committed Jujutsu working copy")
    if EXPECTED_ARRAY_TASKS != 996:
        raise RecoveryError("frozen grouping no longer yields 996 array tasks")
    launch_receipt = load_main_launch_receipt()
    mutation_receipt = load_scheduler_mutation_receipt(launch_receipt)
    runtime_receipt = load_slurm_runtime_receipt()
    validate_slurm_runtime_probe_accounting(runtime_receipt)
    if main_job_id != launch_receipt["job_id"]:
        raise RecoveryError("job ID differs from the sealed main-array launch receipt")
    protocol_revision = JJ.parent_commit(REPO)
    JJ.require_ancestor(REPO, E.PLANNER_REVISION, protocol_revision)
    dependencies = dependency_records(protocol_revision)
    runtime = runtime_identity(
        path_environment=runtime_receipt["effective_path"],
        ld_library_path=runtime_receipt["effective_ld_library_path"],
    )
    if runtime["lab_version"] != P.REQUIRED_LAB_VERSION:
        raise RecoveryError("recovery Lab version differs from the frozen experiment")
    if runtime["execution_environment"]["validator"]["available"] != runtime_receipt[
        "validator"
    ]["available"]:
        raise RecoveryError("external validator availability changed since the Slurm probe")
    try:
        launcher_raw = START_SCRIPT.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise RecoveryError("cannot read generated original launcher") from err
    launcher = parse_original_launcher(launcher_raw)
    launcher_sha = sha256_file(START_SCRIPT)
    E.require_pins()
    E.cached_revision(require_hashes=True)
    cohort = P.load_cohort(E.COHORT_ARCHIVE)
    E.validate_benchmark_sources(cohort)
    P.validate_matched_budget_provenance(E.MATCH_ARCHIVE)
    external_inputs = external_input_identity()
    materialized_code = materialized_code_identity()
    source_records = source_manifest_records()
    scheduler = scheduler_records(
        main_job_id,
        set(range(1, EXPECTED_ARRAY_TASKS + 1)),
        launch_receipt,
        mutation_receipt,
    )
    counts, complete_hashes, cells = classify_cells(
        scheduler, launcher["group_to_slot"], materialized_code, source_records
    )
    nonce = recovery_nonce(main_job_id, launcher_sha, dependencies, cells)
    run_ids = [cell["run_id"] for cell in cells]
    if not run_ids:
        raise RecoveryError(
            "all experiment cells are already complete; no recovery bundle is needed"
        )
    manifest = {
        "schema": SCHEMA,
        "created_utc": utc_now(),
        "protocol_revision": protocol_revision,
        "dependencies": dependencies,
        "runtime": runtime,
        "materialized_code": materialized_code,
        "external_inputs": external_inputs,
        "paths": {
            "repository": str(REPO),
            "experiment_data": str(DATA_DIR),
            "grid_directory": str(GRID_DIR),
            "artifact_directory": str(ARTIFACT_DIR),
        },
        "main_job_id": main_job_id,
        "main_launch_receipt": launch_receipt,
        "scheduler_mutation_receipt": mutation_receipt,
        "slurm_runtime_receipt": runtime_receipt,
        "experiment": {
            "protocol": P.PROTOCOL,
            "analysis_protocol": P.ANALYSIS_PROTOCOL,
            "planner_revision": E.PLANNER_REVISION,
            "planner_binary_sha256": E.PLANNER_BINARY_SHA256,
            "preprocess_binary_sha256": E.PREPROCESS_BINARY_SHA256,
            "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
            "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
            "cells": P.CELL_COUNT,
            "array_tasks": EXPECTED_ARRAY_TASKS,
            "runs_per_array_task": E.RUNS_PER_ARRAY_TASK,
            "array_throttle": E.ARRAY_THROTTLE,
            "recoverable_scheduler_states": sorted(RECOVERABLE_STATES),
        },
        "original_launcher": {
            "path": START_SCRIPT.relative_to(REPO).as_posix(),
            "size": START_SCRIPT.stat().st_size,
            "sha256": launcher_sha,
            "array_slot_to_logical_group": launcher["array_slot_to_logical_group"],
            "run_to_array_task_sha256": launcher["run_to_array_task_sha256"],
        },
        "scheduler_records": scheduler,
        "scheduler_state_counts": dict(
            sorted(Counter(item["state_base"] for item in scheduler).items())
        ),
        "cell_state_counts": counts,
        "outcome_access": {
            "planner_outcomes_parsed": False,
            "completed_tree_contents_exposed": False,
            "completed_tree_hashes_are_opaque": True,
            "completion_test": "last-line-shape-only;numeric-exit-value-not-recorded/v1",
        },
        "complete_cell_tree_hashes": complete_hashes,
        "recovery_cells": cells,
        "recovery_nonce": nonce,
    }
    manifest_digest = sha256_bytes(canonical_bytes(manifest) + b"\n")
    first_wave, runner = build_wave(
        manifest,
        manifest_digest,
        1,
        run_ids,
        previous_wave=None,
        source_scheduler_records={
            "source": "original-main-array",
            "scheduler_records_sha256": sha256_bytes(canonical_bytes(scheduler)),
        },
        source_cell_decisions=[],
        retry_input_cells=[],
        protected_recovered_cell_hashes=[],
    )
    digest = _install_freeze_bundle(manifest, first_wave, runner)
    print(
        "frozen {} opaque complete-cell hashes and {} recovery cells; manifest sha256 {}".format(
            len(complete_hashes), len(cells), digest
        )
    )


def _validate_entry(record: dict) -> None:
    if not isinstance(record, dict) or set(record) not in (
        {"path", "mode", "type"},
        {"path", "mode", "type", "size", "sha256"},
        {"path", "mode", "type", "target", "target_sha256"},
    ):
        raise RecoveryError("manifest has a malformed tree entry")
    path = record.get("path")
    pure = PurePosixPath(path) if isinstance(path, str) else None
    if (
        pure is None
        or not path
        or pure.is_absolute()
        or ".." in pure.parts
        or any("\n" in part or "\t" in part for part in pure.parts)
    ):
        raise RecoveryError("manifest has an unsafe tree path")
    if type(record.get("mode")) is not int or not 0 <= record["mode"] <= 0o7777:
        raise RecoveryError("manifest has an invalid file mode")
    kind = record.get("type")
    if kind == "file":
        if type(record.get("size")) is not int or record["size"] < 0:
            raise RecoveryError("manifest has an invalid file size")
        if SHA256_RE.fullmatch(record.get("sha256", "")) is None:
            raise RecoveryError("manifest has an invalid file hash")
    elif kind == "symlink":
        if not isinstance(record.get("target"), str) or SHA256_RE.fullmatch(
            record.get("target_sha256", "")
        ) is None:
            raise RecoveryError("manifest has an invalid symlink")
    elif kind != "directory":
        raise RecoveryError("manifest has an unsupported entry type")


def validate_manifest(value: dict) -> None:
    required = {
        "schema",
        "created_utc",
        "protocol_revision",
        "dependencies",
        "runtime",
        "materialized_code",
        "external_inputs",
        "paths",
        "main_job_id",
        "main_launch_receipt",
        "scheduler_mutation_receipt",
        "slurm_runtime_receipt",
        "experiment",
        "original_launcher",
        "scheduler_records",
        "scheduler_state_counts",
        "cell_state_counts",
        "outcome_access",
        "complete_cell_tree_hashes",
        "recovery_cells",
        "recovery_nonce",
    }
    if not isinstance(value, dict) or set(value) != required or value.get("schema") != SCHEMA:
        raise RecoveryError("recovery manifest top-level structure changed")
    if JJ.COMMIT_RE.fullmatch(value.get("protocol_revision", "")) is None:
        raise RecoveryError("manifest protocol revision is invalid")
    if (
        not exact_json_equal(
            value.get("main_launch_receipt"), load_main_launch_receipt()
        )
        or value.get("main_job_id") != value["main_launch_receipt"]["job_id"]
    ):
        raise RecoveryError("manifest refers to a different main-array launch")
    if not exact_json_equal(
        value.get("scheduler_mutation_receipt"),
        load_scheduler_mutation_receipt(value["main_launch_receipt"]),
    ):
        raise RecoveryError("manifest refers to a different scheduler mutation")
    if not exact_json_equal(
        value.get("slurm_runtime_receipt"), load_slurm_runtime_receipt()
    ):
        raise RecoveryError("manifest refers to a different Slurm runtime probe")
    experiment = value["experiment"]
    expected_experiment = {
        "protocol": P.PROTOCOL,
        "analysis_protocol": P.ANALYSIS_PROTOCOL,
        "planner_revision": E.PLANNER_REVISION,
        "planner_binary_sha256": E.PLANNER_BINARY_SHA256,
        "preprocess_binary_sha256": E.PREPROCESS_BINARY_SHA256,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "cells": P.CELL_COUNT,
        "array_tasks": EXPECTED_ARRAY_TASKS,
        "runs_per_array_task": E.RUNS_PER_ARRAY_TASK,
        "array_throttle": E.ARRAY_THROTTLE,
        "recoverable_scheduler_states": sorted(RECOVERABLE_STATES),
    }
    if not exact_json_equal(experiment, expected_experiment):
        raise RecoveryError("manifest experiment identity changed")
    expected_paths = {
        "repository": str(REPO),
        "experiment_data": str(DATA_DIR),
        "grid_directory": str(GRID_DIR),
        "artifact_directory": str(ARTIFACT_DIR),
    }
    if value["paths"] != expected_paths:
        raise RecoveryError("manifest paths differ from the frozen workspace")
    runtime = value["runtime"]
    if (
        not isinstance(runtime, dict)
        or set(runtime)
        != {
            "python_executable",
            "python_link_target",
            "python_resolved_path",
            "python_sha256",
            "python_version",
            "lab_version",
            "lab_package_path",
            "lab_distribution_path",
            "lab_runtime_tree_sha256",
            "lab_runtime_entries",
            "lab_runtime_files",
            "required_distributions",
            "required_distribution_files",
            "required_distribution_tree_sha256",
            "execution_environment",
            "controller_python_version",
        }
        or SHA256_RE.fullmatch(runtime.get("python_sha256", "")) is None
        or SHA256_RE.fullmatch(runtime.get("lab_runtime_tree_sha256", "")) is None
        or type(runtime.get("lab_runtime_entries")) is not int
        or runtime["lab_runtime_entries"] < 1
        or not isinstance(runtime.get("lab_runtime_files"), list)
        or not runtime["lab_runtime_files"]
    ):
        raise RecoveryError("manifest runtime identity changed")
    for item in runtime["lab_runtime_files"]:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or not isinstance(item[0], str)
            or SHA256_RE.fullmatch(item[1]) is None
            or type(item[2]) is not int
            or item[2] < 0
        ):
            raise RecoveryError("manifest Lab runtime file identity changed")
    required_packages = runtime["required_distributions"]
    expected_requirements = [
        "{}=={}".format(name, version) for name, version in _pinned_requirements()
    ]
    if (
        not isinstance(required_packages, list)
        or [item.get("requirement") for item in required_packages] != expected_requirements
    ):
        raise RecoveryError("manifest pinned-distribution identity changed")
    for item in required_packages:
        if (
            not isinstance(item, dict)
            or set(item)
            != {
                "requirement",
                "installed_name",
                "installed_version",
                "files",
                "tree_sha256",
            }
            or not isinstance(item.get("installed_name"), str)
            or not isinstance(item.get("installed_version"), str)
            or type(item.get("files")) is not int
            or item["files"] < 1
            or SHA256_RE.fullmatch(item.get("tree_sha256", "")) is None
        ):
            raise RecoveryError("manifest has a malformed pinned distribution")
    distribution_files = runtime["required_distribution_files"]
    if not isinstance(distribution_files, list) or not distribution_files:
        raise RecoveryError("manifest pinned-distribution files changed")
    for item in distribution_files:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or not isinstance(item[0], str)
            or not Path(item[0]).is_absolute()
            or SHA256_RE.fullmatch(item[1]) is None
            or type(item[2]) is not int
            or item[2] < 0
        ):
            raise RecoveryError("manifest has a malformed distribution file")
    if (
        distribution_files != sorted(distribution_files)
        or len({item[0] for item in distribution_files}) != len(distribution_files)
        or runtime["required_distribution_tree_sha256"]
        != sha256_bytes(canonical_bytes(distribution_files))
    ):
        raise RecoveryError("manifest distribution-file closure changed")
    environment = runtime["execution_environment"]
    expected_unset = [
        "LD_PRELOAD",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
    ]
    if (
        not isinstance(environment, dict)
        or set(environment)
        != {
            "path",
            "ld_library_path",
            "python_no_user_site",
            "unset_variables",
            "validator",
        }
        or not isinstance(environment.get("path"), str)
        or not environment["path"]
        or not isinstance(environment.get("ld_library_path"), str)
        or not environment["ld_library_path"]
        or environment.get("python_no_user_site") != "1"
        or environment.get("unset_variables") != expected_unset
    ):
        raise RecoveryError("manifest sealed execution environment changed")
    if (
        environment["path"] != value["slurm_runtime_receipt"]["effective_path"]
        or environment["ld_library_path"]
        != value["slurm_runtime_receipt"]["effective_ld_library_path"]
    ):
        raise RecoveryError("manifest execution environment differs from its Slurm probe")
    validator = environment["validator"]
    if not isinstance(validator, dict) or set(validator) != {
        "available",
        "candidate",
        "path",
        "size",
        "sha256",
    }:
        raise RecoveryError("manifest external-validator identity changed")
    if validator.get("available") is True:
        if (
            validator.get("candidate") not in {"validate", "Validate"}
            or not isinstance(validator.get("path"), str)
            or not Path(validator["path"]).is_absolute()
            or type(validator.get("size")) is not int
            or validator["size"] < 1
            or SHA256_RE.fullmatch(validator.get("sha256", "")) is None
        ):
            raise RecoveryError("manifest has a malformed external validator")
    elif validator != {
        "available": False,
        "candidate": None,
        "path": None,
        "size": None,
        "sha256": None,
    }:
        raise RecoveryError("manifest absent-validator identity changed")
    if validator["available"] != value["slurm_runtime_receipt"]["validator"][
        "available"
    ]:
        raise RecoveryError("manifest validator availability differs from its Slurm probe")
    materialized = value["materialized_code"]
    if (
        not isinstance(materialized, dict)
        or set(materialized)
        != {
            "path",
            "tree_sha256",
            "files",
            "fast_downward_path",
            "fast_downward_sha256",
            "downward_path",
            "downward_sha256",
            "preprocess_path",
            "preprocess_sha256",
            "execution_files",
            "execution_files_sha256",
        }
        or materialized.get("downward_sha256") != E.PLANNER_BINARY_SHA256
        or materialized.get("preprocess_sha256") != E.PREPROCESS_BINARY_SHA256
        or SHA256_RE.fullmatch(materialized.get("fast_downward_sha256", "")) is None
        or SHA256_RE.fullmatch(materialized.get("tree_sha256", "")) is None
        or type(materialized.get("files")) is not int
        or materialized["files"] < 1
    ):
        raise RecoveryError("manifest materialized-code identity changed")
    execution_files = materialized["execution_files"]
    if not isinstance(execution_files, list) or not execution_files:
        raise RecoveryError("manifest materialized execution closure changed")
    for item in execution_files:
        if (
            not isinstance(item, list)
            or len(item) != 3
            or not isinstance(item[0], str)
            or not Path(item[0]).is_absolute()
            or SHA256_RE.fullmatch(item[1]) is None
            or type(item[2]) is not int
            or item[2] < 0
        ):
            raise RecoveryError("manifest has a malformed materialized execution file")
    if (
        execution_files != sorted(execution_files)
        or len({item[0] for item in execution_files}) != len(execution_files)
        or materialized["execution_files_sha256"]
        != sha256_bytes(canonical_bytes(execution_files))
    ):
        raise RecoveryError("manifest materialized execution closure changed")
    core_files = {
        item[0]: item[1] for item in execution_files
    }
    for path_key, hash_key in (
        ("fast_downward_path", "fast_downward_sha256"),
        ("downward_path", "downward_sha256"),
        ("preprocess_path", "preprocess_sha256"),
    ):
        if core_files.get(materialized[path_key]) != materialized[hash_key]:
            raise RecoveryError("manifest execution closure omits a core executable")
    if value["external_inputs"] != external_input_identity():
        raise RecoveryError("manifest external-input identity changed")
    launcher = value["original_launcher"]
    slots = launcher.get("array_slot_to_logical_group")
    if slots != list(range(1, EXPECTED_ARRAY_TASKS + 1)):
        # The current launch is identity ordered.  Reject a substituted mapping
        # even if it is another mathematical permutation.
        raise RecoveryError("manifest original array mapping changed")
    group_to_slot = {group: slot for slot, group in enumerate(slots, 1)}
    assignment = [
        array_task_for_run(run_id, group_to_slot)
        for run_id in range(1, P.CELL_COUNT + 1)
    ]
    if launcher.get("run_to_array_task_sha256") != sha256_bytes(
        canonical_bytes(assignment)
    ):
        raise RecoveryError("manifest original run assignment digest changed")
    scheduler = value["scheduler_records"]
    scheduler_keys = {
        "array_task_id",
        "job_id_raw",
        "state",
        "state_base",
        "elapsed_raw",
        "time_limit",
        "exit_code",
        "node_list",
        "job_name",
        "submit_time",
        "work_dir",
        "requested_memory",
        "requested_cpus",
        "account",
        "partition",
        "qos",
        "submit_line",
    }
    receipt = value["main_launch_receipt"]
    mutation_receipt = value["scheduler_mutation_receipt"]
    if (
        not isinstance(scheduler, list)
        or [record.get("array_task_id") for record in scheduler]
        != list(range(1, EXPECTED_ARRAY_TASKS + 1))
    ):
        raise RecoveryError("manifest main-array scheduler task set changed")
    for record in scheduler:
        if not isinstance(record, dict) or set(record) != scheduler_keys:
            raise RecoveryError("manifest main-array scheduler record changed")
        state_base = normalized_slurm_state(record["state"])
        if (
            record["state_base"] != state_base
            or state_base not in RECOVERABLE_STATES | {"COMPLETED"}
            or record.get("job_name") != receipt["job_name"]
            or record.get("submit_time") != receipt["submit_time"]
            or record.get("work_dir") != receipt["work_directory"]
            or not memory_matches_per_cpu(record.get("requested_memory", ""))
            or record.get("requested_cpus") != str(receipt["cpus_per_task"])
            or record.get("time_limit") != receipt["wall_time"]
            or record.get("account") != receipt["account"]
            or record.get("partition")
            != expected_main_partition(
                record.get("array_task_id"), receipt, mutation_receipt
            )
            or record.get("qos") != receipt["qos"]
            or record.get("submit_line") != receipt["submit_line"]
        ):
            raise RecoveryError("manifest main-array scheduler identity changed")
    scheduler_states = {
        record["array_task_id"]: record["state_base"] for record in scheduler
    }
    validate_main_partition_attestation(scheduler, receipt, mutation_receipt)
    expected_scheduler_counts = dict(
        sorted(Counter(record["state_base"] for record in scheduler).items())
    )
    if not exact_json_equal(
        value["scheduler_state_counts"], expected_scheduler_counts
    ):
        raise RecoveryError("manifest main-array state counts changed")
    expected_outcome_access = {
        "planner_outcomes_parsed": False,
        "completed_tree_contents_exposed": False,
        "completed_tree_hashes_are_opaque": True,
        "completion_test": (
            "last-line-shape-only;numeric-exit-value-not-recorded/v1"
        ),
    }
    if not exact_json_equal(value["outcome_access"], expected_outcome_access):
        raise RecoveryError("manifest outcome-access contract changed")
    complete = value["complete_cell_tree_hashes"]
    complete_ids = []
    for item in complete:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or type(item[0]) is not int
            or not isinstance(item[1], str)
            or SHA256_RE.fullmatch(item[1]) is None
        ):
            raise RecoveryError("manifest has a malformed opaque complete-cell hash")
        complete_ids.append(item[0])
    if complete_ids != sorted(set(complete_ids)):
        raise RecoveryError("manifest repeats or reorders complete cells")
    recovery_ids = []
    for cell in value["recovery_cells"]:
        expected_keys = {
            "run_id",
            "run_dir",
            "original_array_task_id",
            "original_status",
            "tree_sha256",
            "entries",
            "dynamic_top_names",
            "execution_inputs",
        }
        if not isinstance(cell, dict) or set(cell) != expected_keys:
            raise RecoveryError("manifest has a malformed recovery cell")
        run_id = cell["run_id"]
        if cell["run_dir"] != run_relative(run_id).as_posix():
            raise RecoveryError("manifest recovery path differs from its run ID")
        if cell["original_array_task_id"] != array_task_for_run(run_id, group_to_slot):
            raise RecoveryError("manifest recovery cell has the wrong array task")
        require_recoverable_cell_state(
            cell["original_array_task_id"],
            scheduler_states[cell["original_array_task_id"]],
            "manifest recovery cell {}".format(run_id),
        )
        if cell["original_status"] not in {"missing", "interrupted"}:
            raise RecoveryError("manifest recovery cell has an invalid status")
        entries = cell["entries"]
        if not isinstance(entries, list):
            raise RecoveryError("manifest recovery tree is not a list")
        for record in entries:
            _validate_entry(record)
        if [record["path"] for record in entries] != sorted(
            {record["path"] for record in entries}
        ):
            raise RecoveryError("manifest recovery entries repeat or reorder paths")
        if snapshot_digest(entries) != cell["tree_sha256"]:
            raise RecoveryError("manifest recovery tree digest changed")
        names = dynamic_top_names(entries)
        if names != cell["dynamic_top_names"]:
            raise RecoveryError("manifest dynamic basename list changed")
        for name in names:
            _safe_dynamic_path(_safe_run_root(run_id), name)
        if cell["original_status"] == "missing" and names:
            raise RecoveryError("missing recovery cell has dynamic output")
        execution = cell["execution_inputs"]
        expected_execution_keys = {
            "run_sha256",
            "run_size",
            "static_properties_sha256",
            "static_properties_size",
            "domain",
            "problem",
        }
        if not isinstance(execution, dict) or set(execution) != expected_execution_keys:
            raise RecoveryError("manifest has malformed cell execution inputs")
        for key in ("run_sha256", "static_properties_sha256"):
            if SHA256_RE.fullmatch(execution.get(key, "")) is None:
                raise RecoveryError("manifest has an invalid cell input hash")
        for key in ("run_size", "static_properties_size"):
            if type(execution.get(key)) is not int or execution[key] < 1:
                raise RecoveryError("manifest has an invalid cell input size")
        for name in ("domain", "problem"):
            item = execution.get(name)
            if (
                not isinstance(item, dict)
                or set(item)
                != {
                    "link_target",
                    "resolved_path",
                    "benchmark_relative_path",
                    "size",
                    "sha256",
                }
                or type(item.get("size")) is not int
                or item["size"] < 1
                or SHA256_RE.fullmatch(item.get("sha256", "")) is None
            ):
                raise RecoveryError("manifest has malformed resolved PDDL identity")
        recovery_ids.append(run_id)
    if recovery_ids != sorted(set(recovery_ids)):
        raise RecoveryError("manifest repeats or reorders recovery cells")
    if sorted(complete_ids + recovery_ids) != list(range(1, P.CELL_COUNT + 1)):
        raise RecoveryError("manifest cell partition is incomplete")
    expected_cell_counts = Counter({"complete": len(complete_ids)})
    expected_cell_counts.update(
        cell["original_status"] for cell in value["recovery_cells"]
    )
    if not exact_json_equal(
        value["cell_state_counts"], dict(sorted(expected_cell_counts.items()))
    ):
        raise RecoveryError("manifest cell-state counts changed")
    nonce = recovery_nonce(
        value["main_job_id"], launcher["sha256"], value["dependencies"], value["recovery_cells"]
    )
    if value["recovery_nonce"] != nonce:
        raise RecoveryError("manifest recovery nonce changed")


def load_manifest() -> tuple[dict, str]:
    try:
        for path in (MANIFEST, MANIFEST_SIDECAR):
            status = path.lstat()
            if (
                stat.S_ISLNK(status.st_mode)
                or not stat.S_ISREG(status.st_mode)
                or path.resolve(strict=True) != path
            ):
                raise RecoveryError("sealed recovery manifest path is linked")
        raw = MANIFEST.read_bytes()
        checksum = MANIFEST_SIDECAR.read_text(encoding="ascii")
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RecoveryError("cannot read the sealed recovery manifest") from err
    digest = sha256_bytes(raw)
    if checksum != "{}  {}\n".format(digest, MANIFEST.name):
        raise RecoveryError("recovery manifest sidecar changed")
    if raw != canonical_bytes(value) + b"\n":
        raise RecoveryError("recovery manifest is not canonical")
    validate_manifest(value)
    return value, digest


def validate_wave(value: dict, manifest: dict, manifest_digest: str) -> str:
    required = {
        "schema",
        "created_utc",
        "manifest_sha256",
        "wave",
        "previous_wave",
        "source_scheduler_records",
        "source_cell_decisions",
        "retry_input_cells",
        "protected_recovered_cell_hashes",
        "run_ids",
        "outcome_access",
        "retry_policy",
        "runner",
    }
    if not isinstance(value, dict) or set(value) != required or value.get("schema") != WAVE_SCHEMA:
        raise RecoveryError("recovery wave structure changed")
    wave = value.get("wave")
    if type(wave) is not int or not 1 <= wave <= 9999:
        raise RecoveryError("recovery wave number changed")
    if value.get("manifest_sha256") != manifest_digest:
        raise RecoveryError("recovery wave references a different base manifest")
    if not exact_json_equal(value.get("retry_policy"), recovery_retry_policy()):
        raise RecoveryError("recovery wave retry policy changed")
    run_ids = value.get("run_ids")
    base_ids = [cell["run_id"] for cell in manifest["recovery_cells"]]
    if (
        not isinstance(run_ids, list)
        or not run_ids
        or run_ids != sorted(set(run_ids))
        or not set(run_ids).issubset(base_ids)
    ):
        raise RecoveryError("recovery wave has invalid run IDs")
    protected = value.get("protected_recovered_cell_hashes")
    protected_ids = []
    if not isinstance(protected, list):
        raise RecoveryError("recovery wave protected hashes are not a list")
    for item in protected:
        if (
            not isinstance(item, list)
            or len(item) != 2
            or type(item[0]) is not int
            or SHA256_RE.fullmatch(item[1]) is None
        ):
            raise RecoveryError("recovery wave has a malformed protected hash")
        protected_ids.append(item[0])
    if (
        protected_ids != sorted(set(protected_ids))
        or sorted(protected_ids + run_ids) != base_ids
    ):
        raise RecoveryError("recovery wave does not partition the base recovery cells")
    retry_inputs = value.get("retry_input_cells")
    if not isinstance(retry_inputs, list):
        raise RecoveryError("recovery wave retry inputs are not a list")
    retry_ids = []
    for cell in retry_inputs:
        if not isinstance(cell, dict) or set(cell) != {
            "run_id",
            "tree_sha256",
            "entries",
            "dynamic_top_names",
        }:
            raise RecoveryError("recovery wave has a malformed retry input")
        run_id = cell["run_id"]
        entries = cell["entries"]
        if not isinstance(entries, list):
            raise RecoveryError("recovery retry tree is not a list")
        for record in entries:
            _validate_entry(record)
        if [record["path"] for record in entries] != sorted(
            {record["path"] for record in entries}
        ):
            raise RecoveryError("recovery retry tree repeats or reorders paths")
        if snapshot_digest(entries) != cell["tree_sha256"]:
            raise RecoveryError("recovery retry tree digest changed")
        if dynamic_top_names(entries) != cell["dynamic_top_names"]:
            raise RecoveryError("recovery retry dynamic names changed")
        retry_ids.append(run_id)
    decisions = value.get("source_cell_decisions")
    if wave == 1:
        expected_source = {
            "source": "original-main-array",
            "scheduler_records_sha256": sha256_bytes(
                canonical_bytes(manifest["scheduler_records"])
            ),
        }
        if (
            retry_inputs
            or protected
            or decisions != []
            or value["previous_wave"] is not None
            or not exact_json_equal(
                value["source_scheduler_records"], expected_source
            )
        ):
            raise RecoveryError("first recovery wave has retry-only state")
    else:
        if retry_ids != run_ids or value["previous_wave"] is None:
            raise RecoveryError("retry wave inputs do not match its run IDs")
        validate_retry_source_decisions(
            value["source_scheduler_records"],
            decisions,
            retry_inputs,
            protected,
        )
    rebuilt, runner_text_value = build_wave(
        manifest,
        manifest_digest,
        wave,
        run_ids,
        previous_wave=value["previous_wave"],
        source_scheduler_records=value["source_scheduler_records"],
        source_cell_decisions=value["source_cell_decisions"],
        retry_input_cells=retry_inputs,
        protected_recovered_cell_hashes=protected,
        created_utc=value["created_utc"],
    )
    if not exact_json_equal(value, rebuilt):
        raise RecoveryError("recovery wave contract changed")
    runner_path = wave_runner_path(wave)
    runner = value["runner"]
    if (
        runner_path.is_symlink()
        or not runner_path.is_file()
        or runner_path.stat().st_size != runner["size"]
        or sha256_file(runner_path) != runner["sha256"]
        or runner_path.read_text(encoding="ascii") != runner_text_value
    ):
        raise RecoveryError("recovery wave runner changed")
    return sha256_file(wave_manifest_path(wave))


def load_wave(wave: int, manifest: dict, manifest_digest: str) -> tuple[dict, str]:
    value = load_canonical_artifact(wave_manifest_path(wave), WAVE_SCHEMA)
    digest = validate_wave(value, manifest, manifest_digest)
    return value, digest


def load_all_waves(manifest: dict, manifest_digest: str) -> list[tuple[dict, str]]:
    _lstat_directory(WAVES_DIR, "recovery waves")
    numbers = []
    for path in WAVES_DIR.iterdir():
        match = re.fullmatch(r"wave-([0-9]{4})", path.name)
        if match is None:
            raise RecoveryError("unexpected entry in recovery waves: {}".format(path.name))
        _lstat_directory(path, "recovery wave")
        numbers.append(int(match.group(1)))
    if sorted(numbers) != list(range(1, len(numbers) + 1)) or not numbers:
        raise RecoveryError("recovery wave sequence is not contiguous")
    result = [load_wave(number, manifest, manifest_digest) for number in sorted(numbers)]
    for index, (wave, _) in enumerate(result, 1):
        if wave["wave"] != index:
            raise RecoveryError("recovery wave numbering changed")
        if index == 1:
            continue
        previous, previous_digest = result[index - 2]
        receipt = submission_receipt_path(index - 1)
        previous_receipt = load_wave_submit_receipt(previous, manifest_digest)
        expected_previous = {
            "wave": index - 1,
            "wave_manifest_sha256": previous_digest,
            "submit_receipt_sha256": sha256_file(receipt),
            "recovery_job_id": previous_receipt["recovery_job_id"],
        }
        if not exact_json_equal(wave["previous_wave"], expected_previous):
            raise RecoveryError("recovery wave chain changed")
        decisions = wave["source_cell_decisions"]
        validate_wave_scheduler(
            previous, previous_receipt, wave["source_scheduler_records"]
        )
        if [item["run_id"] for item in decisions] != previous["run_ids"]:
            raise RecoveryError("retry decisions differ from the preceding wave")
        previous_intent = load_wave_submit_intent(previous, manifest_digest)
        cells_per = previous_intent.get("batching", {}).get(
            "cells_per_array_task", 1
        )
        expected_source_tasks = [
            position // cells_per + 1
            for position in range(len(previous["run_ids"]))
        ]
        if [item["source_array_task_id"] for item in decisions] != expected_source_tasks:
            raise RecoveryError("retry decisions changed the sealed batch mapping")
        newly_protected = sorted(
            [item["run_id"], item["tree_sha256"]]
            for item in decisions
            if item["action"] == "protect"
        )
        expected_protected = sorted(
            previous["protected_recovered_cell_hashes"] + newly_protected
        )
        if not exact_json_equal(
            wave["protected_recovered_cell_hashes"], expected_protected
        ):
            raise RecoveryError("retry wave protected-hash chain changed")
        expected_retry_ids = [
            item["run_id"] for item in decisions if item["action"] == "retry"
        ]
        if wave["run_ids"] != expected_retry_ids:
            raise RecoveryError("retry wave run IDs differ from sealed decisions")
    return result


def verify_launcher_and_runtime(manifest: dict) -> None:
    launcher = manifest["original_launcher"]
    if START_SCRIPT.stat().st_size != launcher["size"] or sha256_file(START_SCRIPT) != launcher["sha256"]:
        raise RecoveryError("generated original launcher changed")
    parsed = parse_original_launcher(START_SCRIPT.read_text(encoding="utf-8"))
    if (
        parsed["array_slot_to_logical_group"]
        != launcher["array_slot_to_logical_group"]
        or parsed["run_to_array_task_sha256"] != launcher["run_to_array_task_sha256"]
    ):
        raise RecoveryError("generated original launcher mapping changed")
    current = runtime_identity(
        path_environment=manifest["runtime"]["execution_environment"]["path"],
        ld_library_path=manifest["runtime"]["execution_environment"][
            "ld_library_path"
        ],
    )
    for field in (
        "python_executable",
        "python_link_target",
        "python_resolved_path",
        "python_sha256",
        "python_version",
        "lab_version",
        "lab_package_path",
        "lab_distribution_path",
        "lab_runtime_tree_sha256",
        "lab_runtime_entries",
        "lab_runtime_files",
        "required_distributions",
        "required_distribution_files",
        "required_distribution_tree_sha256",
        "execution_environment",
    ):
        if current[field] != manifest["runtime"][field]:
            raise RecoveryError("recovery runtime changed: {}".format(field))
    if materialized_code_identity() != manifest["materialized_code"]:
        raise RecoveryError("materialized experiment code tree changed")
    if external_input_identity() != manifest["external_inputs"]:
        raise RecoveryError("external experiment input paths or bytes changed")


def _combined_original_records(manifest_cell: dict) -> tuple[list[dict], list[dict]]:
    run_id = manifest_cell["run_id"]
    live = snapshot_tree(_safe_run_root(run_id))
    archived_root = _safe_quarantine_root(run_id)
    archived = snapshot_tree(archived_root)
    combined = sorted(live + archived, key=lambda record: record["path"])
    if combined != manifest_cell["entries"]:
        raise RecoveryError("live/quarantined prefix partition changed for run {}".format(run_id))
    return live, archived


def _cell_seal_path(run_id: int) -> Path:
    return CELL_SEALS / "{:05d}.json".format(run_id)


def _cell_seal_value(cell: dict, manifest_digest: str) -> dict:
    return {
        "schema": CELL_SEAL_SCHEMA,
        "manifest_sha256": manifest_digest,
        "run_id": cell["run_id"],
        "original_tree_sha256": cell["tree_sha256"],
        "dynamic_top_names": cell["dynamic_top_names"],
        "quarantine_complete": True,
    }


def _reattest_move_roots(run_id: int, source_root: Path, destination_root: Path) -> None:
    if source_root != _safe_run_root(run_id):
        raise RecoveryError("move source is not the confined live run directory")
    relative = run_relative(run_id)
    if destination_root == QUARANTINE / relative:
        if destination_root != _safe_quarantine_root(run_id):
            raise RecoveryError("original quarantine path changed")
        return
    try:
        relative_to_waves = destination_root.relative_to(WAVES_DIR)
    except ValueError as err:
        raise RecoveryError("move destination is outside a sealed archive") from err
    if len(relative_to_waves.parts) < 4:
        raise RecoveryError("wave archive destination is malformed")
    match = re.fullmatch(r"wave-([0-9]{4})", relative_to_waves.parts[0])
    if match is None or relative_to_waves.parts[1] != "previous-wave-prefixes":
        raise RecoveryError("wave archive destination changed")
    wave = int(match.group(1))
    if destination_root != _safe_wave_archive_root(wave_directory(wave), run_id):
        raise RecoveryError("wave archive path is not confined")


def quarantine_cell(
    cell: dict,
    source_root: Path,
    destination_root: Path,
    *,
    allow_untrusted_test_roots: bool = False,
) -> list[str]:
    """Move one frozen dynamic prefix, resuming safely after any prior move."""
    _lstat_directory(source_root, "quarantine source run")
    _lstat_directory(destination_root, "quarantine destination run")
    expected = cell["entries"]
    source_records = snapshot_tree(source_root)
    archived_records = snapshot_tree(destination_root)
    if sorted(source_records + archived_records, key=lambda item: item["path"]) != expected:
        raise RecoveryError(
            "prefix changed before quarantine for run {}".format(cell["run_id"])
        )
    moved = []
    for name in cell["dynamic_top_names"]:
        if not allow_untrusted_test_roots:
            _reattest_move_roots(cell["run_id"], source_root, destination_root)
        source = _safe_dynamic_path(source_root, name)
        destination = _safe_dynamic_path(destination_root, name)
        expected_records = _records_for_top(expected, name)
        source_has = source.exists() or source.is_symlink()
        destination_has = destination.exists() or destination.is_symlink()
        if source_has and not destination_has:
            if _records_for_top(snapshot_tree(source_root), name) != expected_records:
                raise RecoveryError("dynamic source changed before move")
            os.replace(source, destination)
            _fsync_directory(source.parent)
            _fsync_directory(destination.parent)
            moved.append(name)
        elif destination_has and not source_has:
            if _records_for_top(snapshot_tree(destination_root), name) != expected_records:
                raise RecoveryError("quarantined dynamic prefix changed")
        else:
            raise RecoveryError("dynamic prefix exists at both or neither location")
    source_records = snapshot_tree(source_root)
    archived_records = snapshot_tree(destination_root)
    if sorted(source_records + archived_records, key=lambda item: item["path"]) != expected:
        raise RecoveryError("cell quarantine changed the frozen prefix")
    if dynamic_top_names(source_records):
        raise RecoveryError("cell quarantine left live dynamic output")
    return moved


def restore_cell(
    cell: dict,
    destination_root: Path,
    source_root: Path,
    *,
    allow_untrusted_test_roots: bool = False,
) -> list[str]:
    """Restore one frozen prefix, resuming after any completed prior move."""
    _lstat_directory(destination_root, "restore destination run")
    _lstat_directory(source_root, "restore source archive")
    expected = cell["entries"]
    if sorted(
        snapshot_tree(destination_root) + snapshot_tree(source_root),
        key=lambda record: record["path"],
    ) != expected:
        raise RecoveryError("restore partition changed before a move")
    moved = []
    for name in reversed(cell["dynamic_top_names"]):
        if not allow_untrusted_test_roots:
            _reattest_move_roots(cell["run_id"], destination_root, source_root)
        source = _safe_dynamic_path(source_root, name)
        destination = _safe_dynamic_path(destination_root, name)
        expected_records = _records_for_top(expected, name)
        source_has = source.exists() or source.is_symlink()
        destination_has = destination.exists() or destination.is_symlink()
        if source_has and not destination_has:
            if _records_for_top(snapshot_tree(source_root), name) != expected_records:
                raise RecoveryError("restore source changed before move")
            os.replace(source, destination)
            _fsync_directory(source.parent)
            _fsync_directory(destination.parent)
            moved.append(name)
        elif destination_has and not source_has:
            if _records_for_top(snapshot_tree(destination_root), name) != expected_records:
                raise RecoveryError("already-restored prefix changed")
        else:
            raise RecoveryError("restore prefix exists at both or neither location")
    if snapshot_tree(destination_root) != expected or snapshot_tree(source_root):
        raise RecoveryError("restored prefix differs from the frozen original")
    return moved


def verify_quarantine(manifest: dict, manifest_digest: str, *, require_clean: bool) -> None:
    for cell in manifest["recovery_cells"]:
        live = snapshot_tree(_safe_run_root(cell["run_id"]))
        archived = snapshot_tree(_safe_quarantine_root(cell["run_id"]))
        expected_static = [
            record
            for record in cell["entries"]
            if record["path"].split("/", 1)[0] in STATIC_NAMES
        ]
        expected_dynamic = [
            record
            for record in cell["entries"]
            if record["path"].split("/", 1)[0] not in STATIC_NAMES
        ]
        live_static = [
            record
            for record in live
            if record["path"].split("/", 1)[0] in STATIC_NAMES
        ]
        if archived != expected_dynamic or live_static != expected_static:
            raise RecoveryError(
                "quarantined original tree changed: {}".format(cell["run_id"])
            )
        if require_clean and live != expected_static:
            raise RecoveryError("recovery cell is not fully quarantined: {}".format(cell["run_id"]))
        seal = load_canonical_artifact(_cell_seal_path(cell["run_id"]), CELL_SEAL_SCHEMA)
        if seal != _cell_seal_value(cell, manifest_digest):
            raise RecoveryError("recovery cell seal changed: {}".format(cell["run_id"]))


def _write_or_verify_ready(wave: int, core: dict) -> None:
    path = wave_ready_path(wave)
    if path.exists() or path.is_symlink():
        value = load_canonical_artifact(path, RECEIPT_SCHEMA)
        if {key: value.get(key) for key in core} != core:
            raise RecoveryError("recovery wave ready receipt changed")
        return
    write_artifact(
        path,
        {
            "schema": RECEIPT_SCHEMA,
            "created_utc": utc_now(),
            **core,
        },
    )


def _wave_archive_base(wave: int) -> Path:
    return wave_directory(wave) / "previous-wave-prefixes"


def _wave_cell_seal_path(wave: int, run_id: int) -> Path:
    return wave_directory(wave) / "prefix-cell-seals" / "{:05d}.json".format(run_id)


def _wave_cell_seal_value(wave: int, wave_digest: str, cell: dict) -> dict:
    return {
        "schema": WAVE_CELL_SEAL_SCHEMA,
        "wave": wave,
        "wave_manifest_sha256": wave_digest,
        "run_id": cell["run_id"],
        "input_tree_sha256": cell["tree_sha256"],
        "dynamic_top_names": cell["dynamic_top_names"],
        "quarantine_complete": True,
    }


def verify_retry_archive(wave: dict, wave_digest: str, *, require_clean: bool) -> None:
    number = wave["wave"]
    if number == 1:
        return
    for cell in wave["retry_input_cells"]:
        run_id = cell["run_id"]
        live = snapshot_tree(_safe_run_root(run_id))
        archived = snapshot_tree(_safe_wave_archive_root(wave_directory(number), run_id))
        expected_static = [
            record
            for record in cell["entries"]
            if record["path"].split("/", 1)[0] in STATIC_NAMES
        ]
        expected_dynamic = [
            record
            for record in cell["entries"]
            if record["path"].split("/", 1)[0] not in STATIC_NAMES
        ]
        live_static = [
            record
            for record in live
            if record["path"].split("/", 1)[0] in STATIC_NAMES
        ]
        if archived != expected_dynamic or live_static != expected_static:
            raise RecoveryError("retry archive changed for run {}".format(run_id))
        if require_clean and live != expected_static:
            raise RecoveryError("retry cell is not clean: {}".format(run_id))
        seal = load_canonical_artifact(
            _wave_cell_seal_path(number, run_id), WAVE_CELL_SEAL_SCHEMA
        )
        if seal != _wave_cell_seal_value(number, wave_digest, cell):
            raise RecoveryError("retry archive seal changed for run {}".format(run_id))


def verify_wave_ready(
    wave: dict,
    wave_digest: str,
    manifest: dict,
    manifest_digest: str,
    *,
    require_clean: bool = True,
) -> None:
    number = wave["wave"]
    if number == 1:
        verify_quarantine(manifest, manifest_digest, require_clean=require_clean)
        archive = QUARANTINE
        action = "original-prefixes-ready"
    else:
        verify_retry_archive(wave, wave_digest, require_clean=require_clean)
        archive = _wave_archive_base(number)
        action = "previous-wave-prefixes-ready"
    ready = load_canonical_artifact(wave_ready_path(number), RECEIPT_SCHEMA)
    expected = {
        "action": action,
        "manifest_sha256": manifest_digest,
        "wave": number,
        "wave_manifest_sha256": wave_digest,
        "archive_tree_sha256": snapshot_digest(snapshot_tree(archive)),
        "outcomes_parsed": False,
    }
    if any(ready.get(key) != value for key, value in expected.items()):
        raise RecoveryError("recovery wave ready receipt changed")


def archive_prefixes() -> None:
    manifest, manifest_digest = load_manifest()
    waves = load_all_waves(manifest, manifest_digest)
    if len(waves) != 1:
        raise RecoveryError("original prefixes can only be archived before retry waves")
    first_wave, first_wave_digest = waves[0]
    reattest_execution_inputs(manifest, require_clean=False)
    if (
        any_submission_state()
        or RESTORE_INTENT.exists()
        or RESTORE_RECEIPT.exists()
    ):
        raise RecoveryError("prefixes cannot be archived after submit/restore state")
    QUARANTINE.mkdir(parents=True, exist_ok=True)
    _lstat_directory(QUARANTINE, "original-prefix quarantine")
    _make_confined_directory(QUARANTINE, Path("cell-seals"), "original cell seals")
    moved = []
    for cell in manifest["recovery_cells"]:
        run_id = cell["run_id"]
        source_root = _safe_run_root(run_id)
        destination_root = _safe_quarantine_root(run_id, create=True)
        for name in quarantine_cell(cell, source_root, destination_root):
            moved.append("{}/{}".format(run_relative(run_id), name))
        expected = cell["entries"]
        live, archived = _combined_original_records(cell)
        if dynamic_top_names(live) or archived != [
            record
            for record in expected
            if record["path"].split("/", 1)[0] not in STATIC_NAMES
        ]:
            raise RecoveryError("cell quarantine did not reach its final state")
        seal_path = _cell_seal_path(run_id)
        expected_seal = _cell_seal_value(cell, manifest_digest)
        if seal_path.exists():
            if load_canonical_artifact(seal_path, CELL_SEAL_SCHEMA) != expected_seal:
                raise RecoveryError("existing cell seal changed")
        else:
            write_artifact(seal_path, expected_seal)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "action": "quarantine-interrupted-prefixes",
        "created_utc": utc_now(),
        "manifest_sha256": manifest_digest,
        "cells": len(manifest["recovery_cells"]),
        "dynamic_paths_moved_this_invocation": moved,
        "recoverable_from_quarantine": True,
    }
    if CLEANUP_RECEIPT.exists():
        existing = load_canonical_artifact(CLEANUP_RECEIPT, RECEIPT_SCHEMA)
        if (
            existing.get("action") != receipt["action"]
            or existing.get("manifest_sha256") != manifest_digest
            or existing.get("cells") != receipt["cells"]
            or existing.get("recoverable_from_quarantine") is not True
        ):
            raise RecoveryError("existing quarantine receipt changed")
    else:
        write_artifact(CLEANUP_RECEIPT, receipt)
    verify_quarantine(manifest, manifest_digest, require_clean=True)
    _write_or_verify_ready(
        1,
        {
            "action": "original-prefixes-ready",
            "manifest_sha256": manifest_digest,
            "wave": 1,
            "wave_manifest_sha256": first_wave_digest,
            "archive_tree_sha256": snapshot_digest(snapshot_tree(QUARANTINE)),
            "outcomes_parsed": False,
        },
    )
    verify_wave_ready(first_wave, first_wave_digest, manifest, manifest_digest)
    print("quarantined {} exact recovery cells".format(len(manifest["recovery_cells"])))


def restore_prefixes() -> None:
    manifest, manifest_digest = load_manifest()
    if any_submission_state():
        raise RecoveryError("cannot restore after a recovery submission was intended")
    verify_cleanup_receipt(manifest_digest)
    intent_expected = {
        "action": "restore-interrupted-prefixes-intent",
        "manifest_sha256": manifest_digest,
        "cleanup_receipt_sha256": sha256_file(CLEANUP_RECEIPT),
    }
    if RESTORE_INTENT.exists() or RESTORE_INTENT.is_symlink():
        intent = load_canonical_artifact(RESTORE_INTENT, RECEIPT_SCHEMA)
        if any(intent.get(key) != value for key, value in intent_expected.items()):
            raise RecoveryError("restore intent changed")
    else:
        waves = load_all_waves(manifest, manifest_digest)
        if len(waves) != 1:
            raise RecoveryError("restore is only available before retry waves")
        first_wave, first_wave_digest = waves[0]
        verify_quarantine(manifest, manifest_digest, require_clean=True)
        verify_wave_ready(first_wave, first_wave_digest, manifest, manifest_digest)
        intent = {
            "schema": RECEIPT_SCHEMA,
            "action": intent_expected["action"],
            "created_utc": utc_now(),
            "manifest_sha256": manifest_digest,
            "cleanup_receipt_sha256": intent_expected["cleanup_receipt_sha256"],
            "directly_crash_resumable": True,
        }
        write_artifact(RESTORE_INTENT, intent)
    expected_intent_fields = {
        **intent_expected,
        "directly_crash_resumable": True,
    }
    if any(intent.get(key) != value for key, value in expected_intent_fields.items()):
        raise RecoveryError("restore intent contract changed")
    for cell in reversed(manifest["recovery_cells"]):
        source_root = _safe_quarantine_root(cell["run_id"])
        destination_root = _safe_run_root(cell["run_id"])
        restore_cell(cell, destination_root, source_root)
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "action": "restore-interrupted-prefixes",
        "created_utc": utc_now(),
        "manifest_sha256": manifest_digest,
        "restore_intent_sha256": sha256_file(RESTORE_INTENT),
        "restored_cells": len(manifest["recovery_cells"]),
        "directly_crash_resumable": True,
    }
    if RESTORE_RECEIPT.exists() or RESTORE_RECEIPT.is_symlink():
        existing = load_canonical_artifact(RESTORE_RECEIPT, RECEIPT_SCHEMA)
        for key, value in receipt.items():
            if key != "created_utc" and existing.get(key) != value:
                raise RecoveryError("existing restore receipt changed")
    else:
        write_artifact(RESTORE_RECEIPT, receipt)
    print("restored all quarantined prefixes; recovery submission is disabled")


def verify_cleanup_receipt(manifest_digest: str) -> None:
    receipt = load_canonical_artifact(CLEANUP_RECEIPT, RECEIPT_SCHEMA)
    if (
        receipt.get("action") != "quarantine-interrupted-prefixes"
        or receipt.get("manifest_sha256") != manifest_digest
        or receipt.get("recoverable_from_quarantine") is not True
    ):
        raise RecoveryError("quarantine receipt changed")


def reattest_execution_inputs(manifest: dict, *, require_clean: bool) -> None:
    verify_dependencies(manifest)
    verify_launcher_and_runtime(manifest)
    E.require_pins()
    E.cached_revision(require_hashes=True)
    cohort = P.load_cohort(E.COHORT_ARCHIVE)
    E.validate_benchmark_sources(cohort)
    P.validate_matched_budget_provenance(E.MATCH_ARCHIVE)
    source_records = source_manifest_records()
    for cell in manifest["recovery_cells"]:
        run_id = cell["run_id"]
        root = _safe_run_root(run_id)
        live = snapshot_tree(root)
        validate_static_inputs(root, live)
        if cell_execution_identity(
            run_id, manifest["materialized_code"], source_records
        ) != cell["execution_inputs"]:
            raise RecoveryError("recovery cell execution identity changed: {}".format(run_id))
        if require_clean and dynamic_top_names(live):
            raise RecoveryError("recovery cell has live dynamic output before submit")


def verify_untouched_cells(manifest: dict) -> None:
    for run_id, expected_digest in manifest["complete_cell_tree_hashes"]:
        actual = snapshot_digest(snapshot_tree(_safe_run_root(run_id)))
        if actual != expected_digest:
            raise RecoveryError("previously complete cell changed: {}".format(run_id))


def _memory_mib(value: str, *, require_per_cpu: bool) -> Decimal:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KMGTP])([cn]?)", value or "")
    if match is None:
        raise RecoveryError("scheduler reported malformed requested memory")
    suffix = match.group(3)
    if require_per_cpu and suffix not in ("", "c"):
        raise RecoveryError("scheduler memory is not per CPU")
    if not require_per_cpu and suffix == "c":
        raise RecoveryError("scheduler memory unexpectedly uses a CPU scope")
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation as err:
        raise RecoveryError("scheduler memory amount is invalid") from err
    scale = {"K": Decimal(1) / 1024, "M": Decimal(1), "G": Decimal(1024), "T": Decimal(1024**2), "P": Decimal(1024**3)}
    return amount * scale[match.group(2)]


def memory_matches_per_cpu(value: str, expected: str = RECOVERY_MEMORY) -> bool:
    try:
        return _memory_mib(value, require_per_cpu=True) == _memory_mib(
            expected, require_per_cpu=True
        )
    except RecoveryError:
        return False


def _time_seconds(value: str) -> int:
    match = re.fullmatch(r"(?:(\d+)-)?(\d+):(\d\d):(\d\d)", value or "")
    if match is None:
        raise RecoveryError("scheduler reported malformed time limit")
    days = int(match.group(1) or 0)
    hours, minutes, seconds = map(int, match.groups()[1:])
    if minutes >= 60 or seconds >= 60:
        raise RecoveryError("scheduler time limit is invalid")
    return ((days * 24 + hours) * 60 + minutes) * 60 + seconds


def scheduler_metadata_matches(record: dict, expected: dict) -> bool:
    try:
        return (
            record.get("job_name") == expected["job_name"]
            and record.get("work_dir") == expected["work_dir"]
            and memory_matches_per_cpu(record.get("requested_memory", ""))
            and int(record.get("requested_cpus", "")) == expected["requested_cpus"]
            and _time_seconds(record.get("time_limit", ""))
            == _time_seconds(expected["time_limit"])
            and record.get("account") == expected["account"]
            and record.get("partition") == expected["partition"]
            and record.get("qos") == expected["qos"]
            and record.get("comment") == expected["comment"]
        )
    except (KeyError, TypeError, ValueError, RecoveryError):
        return False


def _array_expression_tasks(
    expression: str, *, expected_throttle: int = E.ARRAY_THROTTLE
) -> set[int]:
    if type(expected_throttle) is not int or expected_throttle < 1:
        raise RecoveryError("expected array throttle is invalid")
    expression = expression.strip()
    if expression.startswith("[") and expression.endswith("]"):
        expression = expression[1:-1]
    if "%" in expression:
        expression, throttle = expression.rsplit("%", 1)
        if not throttle.isdigit() or int(throttle) != expected_throttle:
            raise RecoveryError("scheduler array throttle changed")
    tasks = set()
    for segment in expression.split(","):
        match = re.fullmatch(r"([1-9][0-9]*)(?:-([1-9][0-9]*)(?::([1-9][0-9]*))?)?", segment)
        if match is None:
            raise RecoveryError("scheduler array expression is malformed")
        start = int(match.group(1))
        end = int(match.group(2) or start)
        step = int(match.group(3) or 1)
        if end < start:
            raise RecoveryError("scheduler array range is reversed")
        tasks.update(range(start, end + 1, step))
    return tasks


def _tasks_from_display_id(
    display_id: str, job_id: str, *, expected_throttle: int
) -> set[int]:
    if display_id == job_id:
        return set()
    prefix = job_id + "_"
    if not display_id.startswith(prefix):
        raise RecoveryError("scheduler row belongs to another array")
    return _array_expression_tasks(
        display_id[len(prefix) :], expected_throttle=expected_throttle
    )


def _intent_array_throttle(intent: dict) -> int:
    expression = intent.get("array_spec")
    if not isinstance(expression, str) or "%" not in expression:
        raise RecoveryError("recovery intent lacks its sealed array throttle")
    throttle = expression.rsplit("%", 1)[1]
    if not throttle.isdigit() or int(throttle) < 1:
        raise RecoveryError("recovery intent array throttle is invalid")
    return int(throttle)


def load_wave_submit_intent(wave: dict, manifest_digest: str) -> dict:
    path = submission_intent_path(wave["wave"])
    intent = load_canonical_artifact(path, RECEIPT_SCHEMA)
    if (
        intent.get("action") != "submit-cell-exact-recovery"
        or intent.get("manifest_sha256") != manifest_digest
        or intent.get("wave") != wave["wave"]
        or intent.get("wave_manifest_sha256") != sha256_file(
            wave_manifest_path(wave["wave"])
        )
    ):
        raise RecoveryError("recovery submit intent changed")
    return intent


def _expected_scheduler_metadata(intent: dict) -> dict:
    batching = intent.get("batching")
    requested_cpus = 1
    time_limit = RECOVERY_WALL_TIME
    if batching is not None:
        if not isinstance(batching, dict):
            raise RecoveryError("recovery intent batching metadata changed")
        requested_cpus = batching.get("cpus_per_task")
        time_limit = batching.get("wall_time")
    return {
        "job_name": intent["job_name"],
        "work_dir": intent["work_directory"],
        "requested_cpus": requested_cpus,
        "time_limit": time_limit,
        "account": E.ACCOUNT,
        "partition": "cpu",
        "qos": "normal",
        "comment": intent["scheduler_comment"],
    }


def _scontrol_runner_matches(job_id: str, intent: dict) -> bool:
    try:
        result = subprocess.run(
            ["scontrol", "show", "job", "-o", job_id],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return False
    rows = [line for line in result.stdout.splitlines() if line.strip()]
    if not rows:
        return False
    tasks = set()
    expected_throttle = _intent_array_throttle(intent)
    for row in rows:
        fields = {}
        for token in row.split():
            if "=" in token:
                key, value = token.split("=", 1)
                fields[key] = value
        if (
            fields.get("ArrayJobId", fields.get("JobId")) != job_id
            or fields.get("JobName") != intent["job_name"]
            or fields.get("Account") != E.ACCOUNT
            or fields.get("QOS") != "normal"
            or fields.get("Partition") != "cpu"
            or fields.get("WorkDir") != intent["work_directory"]
            or fields.get("Command") != intent["runner_path"]
            or fields.get("Comment") != intent["scheduler_comment"]
            or fields.get("Requeue") != "0"
        ):
            return False
        expression = fields.get("ArrayTaskId")
        if expression:
            tasks.update(
                _array_expression_tasks(
                    expression, expected_throttle=expected_throttle
                )
            )
    return tasks == set(range(1, intent["array_tasks"] + 1))


def find_jobs_by_identity(intent: dict) -> set[str]:
    job_name = intent["job_name"]
    since = intent["created_utc"]
    since_day = since.split("T", 1)[0]
    if re.fullmatch(r"\d{4}-\d\d-\d\d", since_day) is None:
        raise RecoveryError("submit intent has an invalid reconciliation date")
    try:
        queued = subprocess.run(
            [
                "squeue",
                "-h",
                "-r",
                "-n",
                job_name,
                "-o",
                "%i|%j|%k|%Z|%l|%m|%c|%P|%q|%a",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        accounted = subprocess.run(
            [
                "sacct",
                "-n",
                "-X",
                "-S",
                since_day,
                "--name",
                job_name,
                "--format={}".format(RECONCILIATION_SACCT_FORMAT),
                "-P",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("cannot reconcile recovery scheduler identity") from err
    expected_tasks = set(range(1, intent["array_tasks"] + 1))
    expected_throttle = _intent_array_throttle(intent)
    expected_metadata = _expected_scheduler_metadata(intent)
    groups = {}
    for line in accounted.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) != 12:
            raise RecoveryError("reconciliation sacct row has the wrong field count")
        root_match = re.match(r"^([1-9][0-9]*)(?:_|$)", fields[0])
        if root_match is None:
            continue
        root = root_match.group(1)
        record = {
            "job_name": fields[1],
            "submit": fields[2],
            "work_dir": fields[3],
            "requested_memory": fields[4],
            "requested_cpus": fields[5],
            "time_limit": fields[6],
            "account": fields[7],
            "partition": fields[8],
            "qos": fields[9],
            "comment": fields[10],
            "submit_line": fields[11],
        }
        groups.setdefault(root, []).append((fields[0], record, "sacct"))
    for line in queued.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) != 10:
            raise RecoveryError("reconciliation squeue row has the wrong field count")
        root_match = re.match(r"^([1-9][0-9]*)(?:_|$)", fields[0])
        if root_match is None:
            continue
        root = root_match.group(1)
        record = {
            "job_name": fields[1],
            "work_dir": fields[3],
            "requested_memory": fields[5],
            "requested_cpus": fields[6],
            "time_limit": fields[4],
            "account": fields[9],
            "partition": fields[7],
            "qos": fields[8],
            "comment": fields[2],
        }
        groups.setdefault(root, []).append((fields[0], record, "squeue"))
    matches = set()
    for job_id, rows in groups.items():
        tasks = set()
        has_accounting_identity = False
        for display_id, record, source in rows:
            if not scheduler_metadata_matches(record, expected_metadata):
                raise RecoveryError("job-name collision has mismatching scheduler metadata")
            if source == "sacct":
                if record["submit_line"] != intent["submit_line"]:
                    raise RecoveryError("job-name collision has a different submit command")
                has_accounting_identity = True
            tasks.update(
                _tasks_from_display_id(
                    display_id,
                    job_id,
                    expected_throttle=expected_throttle,
                )
            )
        if tasks != expected_tasks:
            raise RecoveryError("matching recovery job has a different array shape")
        if not has_accounting_identity and not _scontrol_runner_matches(job_id, intent):
            raise RecoveryError("active recovery job does not match the sealed runner")
        matches.add(job_id)
    return matches


def _seal_submit_receipt(
    manifest_digest: str,
    wave: dict,
    intent: dict,
    job_id: str,
    source: str,
    stdout: str,
) -> None:
    if JOB_ID_RE.fullmatch(job_id) is None:
        raise RecoveryError("scheduler returned an invalid recovery job ID")
    intent_path = submission_intent_path(wave["wave"])
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "action": "cell-exact-recovery-submitted",
        "created_utc": utc_now(),
        "manifest_sha256": manifest_digest,
        "wave": wave["wave"],
        "wave_manifest_sha256": sha256_file(wave_manifest_path(wave["wave"])),
        "intent_sha256": sha256_file(intent_path),
        "recovery_job_id": job_id,
        "job_name": intent["job_name"],
        "array_spec": intent["array_spec"],
        "scheduler_comment": intent["scheduler_comment"],
        "runner_sha256": intent["runner_sha256"],
        "receipt_source": source,
        "sbatch_stdout": stdout,
    }
    path = submission_receipt_path(wave["wave"])
    if path.exists() or path.is_symlink():
        existing = load_canonical_artifact(path, RECEIPT_SCHEMA)
        for field, value in receipt.items():
            if field not in {
                "created_utc",
                "receipt_source",
                "sbatch_stdout",
            } and not exact_json_equal(existing.get(field), value):
                raise RecoveryError("existing submit receipt changed")
        return
    write_artifact(path, receipt)


def _protected_recovered_cells(wave: dict) -> None:
    for run_id, expected_digest in wave["protected_recovered_cell_hashes"]:
        actual = snapshot_digest(snapshot_tree(_safe_run_root(run_id)))
        if actual != expected_digest or not driver_log_complete(
            _safe_run_root(run_id) / "driver.log"
        ):
            raise RecoveryError("protected recovered cell changed: {}".format(run_id))


def _parse_slurm_max_array_size(text: str) -> int:
    matches = re.findall(r"(?m)^MaxArraySize\s*=\s*([1-9][0-9]*)\s*$", text)
    if len(matches) != 1 or int(matches[0]) < 2:
        raise RecoveryError("cannot determine Slurm MaxArraySize")
    return int(matches[0])


def slurm_max_array_size() -> int:
    try:
        result = subprocess.run(
            ["scontrol", "show", "config"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("cannot query Slurm MaxArraySize") from err
    return _parse_slurm_max_array_size(result.stdout)


def executable_identity(name: str, path_environment: str) -> dict:
    if SAFE_NAME_RE.fullmatch(name) is None:
        raise RecoveryError("unsafe executable name")
    candidate = shutil.which(name, path=path_environment)
    if candidate is None:
        raise RecoveryError("required batching executable is absent: {}".format(name))
    path = Path(candidate)
    try:
        resolved = path.resolve(strict=True)
        status = resolved.lstat()
    except OSError as err:
        raise RecoveryError("cannot inspect batching executable: {}".format(name)) from err
    if (
        not stat.S_ISREG(status.st_mode)
        or stat.S_ISLNK(status.st_mode)
        or not os.access(resolved, os.X_OK)
    ):
        raise RecoveryError("batching executable is not canonical: {}".format(name))
    return {
        "path": str(resolved),
        "size": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }


def _legacy_submission_contract(wave: dict) -> dict:
    runner = wave["runner"]
    return {
        **runner,
        "array_tasks": len(wave["run_ids"]),
        "array_throttle": E.ARRAY_THROTTLE,
        "cells_per_array_task": 1,
        "runner_path": str(wave_runner_path(wave["wave"])),
        "work_directory": str(wave_directory(wave["wave"])),
    }


def _array_limit_nonce_payload(
    manifest_digest: str,
    wave_digest: str,
    legacy_intent_digest: str,
    run_ids_digest: str,
    max_array_size: int,
    cells_per_array_task: int,
    array_tasks: int,
    amended_protocol_digest: str,
    srun: dict,
    environment: dict,
    execution_policy: dict,
) -> dict:
    return {
        "manifest_sha256": manifest_digest,
        "wave_manifest_sha256": wave_digest,
        "legacy_submit_intent_sha256": legacy_intent_digest,
        "run_ids_sha256": run_ids_digest,
        "slurm_max_array_size": max_array_size,
        "cells_per_array_task": cells_per_array_task,
        "array_tasks": array_tasks,
        "amended_protocol_sha256": amended_protocol_digest,
        "srun": srun,
        "env": environment,
        "execution_policy": execution_policy,
    }


def array_limit_execution_policy() -> dict:
    return {
        "mode": "two-concurrent-exclusive-slurm-steps/v1",
        "step_resources": {
            "nodes": 1,
            "tasks": 1,
            "cpus_per_task": 1,
            "memory_per_cpu": RECOVERY_MEMORY,
        },
        "step_environment": "sealed-env-overrides-SLURM_ARRAY_TASK_ID/v1",
        "failure_policy": "launch-all-wait-all-return-first-nonzero/v1",
        "byte_attestation": "legacy-runner-srun-env-pre-and-post/v1",
        "batch_array_throttle": 2,
        "maximum_concurrent_cells": 4,
        "legacy_maximum_concurrent_cells": E.ARRAY_THROTTLE,
    }


def load_array_limit_amendment(
    wave: dict, manifest: dict, manifest_digest: str
) -> dict:
    path = wave_array_limit_amendment_path(wave["wave"])
    value = load_canonical_artifact(path, ARRAY_LIMIT_AMENDMENT_SCHEMA)
    required = {
        "schema",
        "action",
        "created_utc",
        "manifest_sha256",
        "wave",
        "wave_manifest_sha256",
        "legacy_submission",
        "slurm_limit",
        "protocol_dependency_amendment",
        "outcome_access",
        "batching",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise RecoveryError("array-limit amendment structure changed")
    wave_digest = sha256_file(wave_manifest_path(wave["wave"]))
    if (
        value["action"]
        != "replace-rejected-oversized-array-with-batched-wrapper"
        or value["manifest_sha256"] != manifest_digest
        or type(value["wave"]) is not int
        or value["wave"] != wave["wave"]
        or value["wave_manifest_sha256"] != wave_digest
        or not exact_json_equal(
            value["outcome_access"],
            {
                "planner_outcomes_parsed": False,
                "completion_sentinels_inspected": False,
            },
        )
    ):
        raise RecoveryError("array-limit amendment identity changed")
    validate_protocol_dependency_amendment(
        value["protocol_dependency_amendment"], manifest
    )

    legacy = value["legacy_submission"]
    legacy_required = {
        "intent_path",
        "intent_sha256",
        "job_name",
        "array_spec",
        "array_tasks",
        "requested_max_index",
        "absence_checked_utc",
        "matching_job_ids",
        "test_only_exit_code",
        "test_only_stdout",
        "test_only_stderr",
    }
    intent_path = wave_intent_path(wave["wave"])
    if not isinstance(legacy, dict) or set(legacy) != legacy_required:
        raise RecoveryError("legacy rejected submission record changed")
    legacy_intent = load_canonical_artifact(intent_path, RECEIPT_SCHEMA)
    expected_legacy = _expected_submit_intent(
        wave, manifest_digest, use_amendment=False
    )
    if any(
        field != "created_utc"
        and not exact_json_equal(legacy_intent.get(field), expected)
        for field, expected in expected_legacy.items()
    ):
        raise RecoveryError("legacy rejected submit intent changed")
    if (
        legacy["intent_path"] != intent_path.relative_to(REPO).as_posix()
        or legacy["intent_sha256"] != sha256_file(intent_path)
        or legacy["job_name"] != legacy_intent["job_name"]
        or legacy["array_spec"] != legacy_intent["array_spec"]
        or legacy["array_tasks"] != legacy_intent["array_tasks"]
        or legacy["requested_max_index"] != len(wave["run_ids"])
        or type(legacy["array_tasks"]) is not int
        or type(legacy["requested_max_index"]) is not int
        or not isinstance(legacy["absence_checked_utc"], str)
        or re.fullmatch(
            r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ",
            legacy["absence_checked_utc"],
        )
        is None
        or legacy["matching_job_ids"] != []
        or type(legacy["test_only_exit_code"]) is not int
        or legacy["test_only_exit_code"] != 1
        or type(legacy["test_only_stdout"]) is not str
        or type(legacy["test_only_stderr"]) is not str
        or legacy["test_only_stdout"] != ""
        or legacy["test_only_stderr"].strip() != ARRAY_LIMIT_REJECTION
    ):
        raise RecoveryError("legacy rejection evidence changed")

    limit = value["slurm_limit"]
    if (
        not isinstance(limit, dict)
        or set(limit)
        != {"query", "max_array_size", "maximum_array_index"}
        or limit["query"] != "scontrol show config"
        or type(limit["max_array_size"]) is not int
        or limit["max_array_size"] < 2
        or limit["maximum_array_index"] != limit["max_array_size"] - 1
        or legacy["requested_max_index"] <= limit["maximum_array_index"]
    ):
        raise RecoveryError("sealed Slurm array limit changed")

    batching = value["batching"]
    batching_required = {
        "path",
        "size",
        "sha256",
        "nonce",
        "job_name",
        "array_spec",
        "array_tasks",
        "array_throttle",
        "cells_per_array_task",
        "run_ids_sha256",
        "legacy_runner_path",
        "legacy_runner_sha256",
        "srun",
        "env",
        "execution_policy",
        "wall_time",
        "memory_per_cpu",
        "cpus_per_task",
        "partition",
        "qos",
        "account",
        "requeue",
        "submission_environment_export",
    }
    if not isinstance(batching, dict) or set(batching) != batching_required:
        raise RecoveryError("batched submission contract changed")
    run_ids_digest = sha256_bytes(canonical_bytes(wave["run_ids"]))
    cells_per = (
        len(wave["run_ids"]) + limit["maximum_array_index"] - 1
    ) // limit["maximum_array_index"]
    array_tasks = (len(wave["run_ids"]) + cells_per - 1) // cells_per
    if cells_per != 2 or array_tasks != 566 or len(wave["run_ids"]) != 1132:
        raise RecoveryError("array-limit amendment is not the audited 1132-to-566 mapping")
    dependency = value["protocol_dependency_amendment"]
    path_environment = manifest["runtime"]["execution_environment"]["path"]
    srun = executable_identity("srun", path_environment)
    environment = executable_identity("env", path_environment)
    execution_policy = array_limit_execution_policy()
    batch_throttle = max(1, E.ARRAY_THROTTLE // cells_per)
    if batch_throttle != execution_policy["batch_array_throttle"]:
        raise RecoveryError("batched recovery throttle changed")
    nonce = sha256_bytes(
        canonical_bytes(
            _array_limit_nonce_payload(
                manifest_digest,
                wave_digest,
                legacy["intent_sha256"],
                run_ids_digest,
                limit["max_array_size"],
                cells_per,
                array_tasks,
                dependency["amended_sha256"],
                srun,
                environment,
                execution_policy,
            )
        )
    )[:16]
    original_runner = wave["runner"]
    expected_batching = {
        "path": wave_batch_runner_path(wave["wave"])
        .relative_to(REPO)
        .as_posix(),
        "size": batching.get("size"),
        "sha256": batching.get("sha256"),
        "nonce": nonce,
        "job_name": "pdbprof-b{:02d}-{}".format(wave["wave"], nonce[:12]),
        "array_spec": "1-{}%{}".format(array_tasks, batch_throttle),
        "array_tasks": array_tasks,
        "array_throttle": batch_throttle,
        "cells_per_array_task": cells_per,
        "run_ids_sha256": run_ids_digest,
        "legacy_runner_path": wave_runner_path(wave["wave"])
        .relative_to(REPO)
        .as_posix(),
        "legacy_runner_sha256": original_runner["sha256"],
        "srun": srun,
        "env": environment,
        "execution_policy": execution_policy,
        "wall_time": original_runner["wall_time"],
        "memory_per_cpu": original_runner["memory_per_cpu"],
        "cpus_per_task": cells_per * original_runner["cpus_per_task"],
        "partition": original_runner["partition"],
        "qos": original_runner["qos"],
        "account": original_runner["account"],
        "requeue": False,
        "submission_environment_export": original_runner[
            "submission_environment_export"
        ],
    }
    if not exact_json_equal(batching, expected_batching):
        raise RecoveryError("batched submission contract differs from derivation")
    wrapper = batch_runner_text(
        wave,
        job_name=batching["job_name"],
        array_tasks=array_tasks,
        cells_per_array_task=cells_per,
        srun_path=srun["path"],
        srun_sha256=srun["sha256"],
        env_path=environment["path"],
        env_sha256=environment["sha256"],
    )
    runner_path = wave_batch_runner_path(wave["wave"])
    if (
        runner_path.is_symlink()
        or not runner_path.is_file()
        or not os.access(runner_path, os.X_OK)
        or runner_path.stat().st_size != len(wrapper.encode("ascii"))
        or batching["size"] != len(wrapper.encode("ascii"))
        or batching["sha256"] != sha256_bytes(wrapper.encode("ascii"))
        or runner_path.read_text(encoding="ascii") != wrapper
    ):
        raise RecoveryError("batched recovery runner changed")
    if find_jobs_by_identity(legacy_intent):
        raise RecoveryError(
            "the rejected legacy submission appeared after its absence receipt"
        )
    return value


def _submission_contract(
    wave: dict,
    manifest_digest: str,
    *,
    manifest: dict | None = None,
    use_amendment: bool = True,
) -> dict:
    if use_amendment and _has_array_limit_amendment(wave["wave"]):
        if manifest is None:
            manifest, loaded_digest = load_manifest()
            if loaded_digest != manifest_digest:
                raise RecoveryError("submission manifest digest changed")
        amendment = load_array_limit_amendment(wave, manifest, manifest_digest)
        batching = amendment["batching"]
        return {
            **batching,
            "runner_path": str(REPO / batching["path"]),
            "work_directory": str(wave_directory(wave["wave"])),
        }
    return _legacy_submission_contract(wave)


def _submission_argv(
    wave: dict,
    manifest_digest: str,
    *,
    manifest: dict | None = None,
    use_amendment: bool = True,
) -> list[str]:
    runner = _submission_contract(
        wave,
        manifest_digest,
        manifest=manifest,
        use_amendment=use_amendment,
    )
    comment = "pdbprof:{}:w{:04d}:{}".format(
        manifest_digest[:20], wave["wave"], runner["nonce"]
    )
    return [
        "sbatch",
        "--parsable",
        "--export=PATH",
        "--job-name={}".format(runner["job_name"]),
        "--array={}".format(runner["array_spec"]),
        "--partition={}".format(runner["partition"]),
        "--qos={}".format(runner["qos"]),
        "--time={}".format(runner["wall_time"]),
        "--mem-per-cpu={}".format(runner["memory_per_cpu"]),
        "--cpus-per-task={}".format(runner["cpus_per_task"]),
        "--account={}".format(runner["account"]),
        "--no-requeue",
        "--chdir={}".format(runner["work_directory"]),
        "--comment={}".format(comment),
        runner["runner_path"],
    ]


def _expected_submit_intent(
    wave: dict,
    manifest_digest: str,
    *,
    manifest: dict | None = None,
    use_amendment: bool = True,
) -> dict:
    runner = _submission_contract(
        wave,
        manifest_digest,
        manifest=manifest,
        use_amendment=use_amendment,
    )
    argv = _submission_argv(
        wave,
        manifest_digest,
        manifest=manifest,
        use_amendment=use_amendment,
    )
    value = {
        "schema": RECEIPT_SCHEMA,
        "action": "submit-cell-exact-recovery",
        "created_utc": None,
        "manifest_sha256": manifest_digest,
        "wave": wave["wave"],
        "wave_manifest_sha256": sha256_file(wave_manifest_path(wave["wave"])),
        "job_name": runner["job_name"],
        "array_spec": runner["array_spec"],
        "array_tasks": runner["array_tasks"],
        "environment_export": runner["submission_environment_export"],
        "scheduler_comment": argv[-2].split("=", 1)[1],
        "runner_path": runner["runner_path"],
        "runner_sha256": runner["sha256"],
        "work_directory": runner["work_directory"],
        "submit_line": " ".join(argv),
    }
    if use_amendment and _has_array_limit_amendment(wave["wave"]):
        value["batching"] = {
            "recovery_cells": len(wave["run_ids"]),
            "cells_per_array_task": runner["cells_per_array_task"],
            "legacy_runner_sha256": runner["legacy_runner_sha256"],
            "array_throttle": runner["array_throttle"],
            "cpus_per_task": runner["cpus_per_task"],
            "memory_per_cpu": runner["memory_per_cpu"],
            "wall_time": runner["wall_time"],
            "execution_policy": runner["execution_policy"],
        }
    return value


def submission_array_tasks(
    wave: dict, manifest: dict, manifest_digest: str
) -> int:
    return _submission_contract(
        wave, manifest_digest, manifest=manifest
    )["array_tasks"]


def submission_task_for_run_position(
    wave: dict, position: int, manifest: dict, manifest_digest: str
) -> int:
    if type(position) is not int or not 0 <= position < len(wave["run_ids"]):
        raise RecoveryError("recovery run position is invalid")
    cells_per = _submission_contract(
        wave, manifest_digest, manifest=manifest
    )["cells_per_array_task"]
    return position // cells_per + 1


def amend_array_limit() -> None:
    manifest, manifest_digest = load_manifest()
    waves = load_all_waves(manifest, manifest_digest)
    wave, wave_digest = waves[-1]
    number = wave["wave"]
    amendment_path = wave_array_limit_amendment_path(number)
    batch_path = wave_batch_runner_path(number)
    if amendment_path.exists() or amendment_path.is_symlink():
        load_array_limit_amendment(wave, manifest, manifest_digest)
        print("recovery array-limit amendment is already sealed")
        return
    if submission_receipt_path(number).exists() or wave_receipt_path(number).is_symlink():
        raise RecoveryError("a submitted recovery wave cannot be amended")
    legacy_intent_path = wave_intent_path(number)
    if not legacy_intent_path.exists() or legacy_intent_path.is_symlink():
        raise RecoveryError("array-limit amendment requires a sealed legacy intent")
    legacy_intent = load_canonical_artifact(legacy_intent_path, RECEIPT_SCHEMA)
    expected_legacy = _expected_submit_intent(
        wave, manifest_digest, manifest=manifest, use_amendment=False
    )
    if any(
        field != "created_utc"
        and not exact_json_equal(legacy_intent.get(field), expected)
        for field, expected in expected_legacy.items()
    ):
        raise RecoveryError("legacy rejected submit intent changed")
    if find_jobs_by_identity(legacy_intent):
        raise RecoveryError("legacy recovery job exists and cannot be amended")

    maximum = slurm_max_array_size()
    maximum_index = maximum - 1
    legacy_tasks = len(wave["run_ids"])
    if legacy_tasks <= maximum_index:
        raise RecoveryError("legacy recovery array does not exceed MaxArraySize")
    test_argv = _submission_argv(
        wave, manifest_digest, manifest=manifest, use_amendment=False
    )
    test_argv.insert(1, "--test-only")
    try:
        rejection = subprocess.run(
            test_argv,
            cwd=wave_directory(number),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as err:
        raise RecoveryError("cannot test the rejected legacy submission") from err
    if (
        rejection.returncode == 0
        or rejection.stdout != ""
        or rejection.stderr.strip() != ARRAY_LIMIT_REJECTION
    ):
        raise RecoveryError("legacy submission rejection is not the sealed array limit")
    if find_jobs_by_identity(legacy_intent):
        raise RecoveryError("legacy recovery job appeared during rejection audit")

    if JJ.working_copy_diff_summary(REPO):
        raise RecoveryError("commit the amended recovery protocol before sealing it")
    recovery_relative = Path(__file__).resolve().relative_to(REPO).as_posix()
    amended_code_commit = JJ.parent_commit(REPO)
    amended_digest = sha256_file(Path(__file__).resolve())
    if (
        not JJ.file_is_tracked_at(REPO, amended_code_commit, recovery_relative)
        or JJ.tracked_file_sha256(
            REPO, amended_code_commit, recovery_relative
        )
        != amended_digest
    ):
        raise RecoveryError("amended recovery protocol is not the committed parent")
    frozen_dependency = manifest["dependencies"][recovery_relative]
    dependency_amendment = {
        "path": recovery_relative,
        "frozen_sha256": frozen_dependency["sha256"],
        "frozen_size": frozen_dependency["size"],
        "amended_sha256": amended_digest,
        "amended_size": Path(__file__).stat().st_size,
        "amended_code_commit": amended_code_commit,
    }

    cells_per = (legacy_tasks + maximum_index - 1) // maximum_index
    array_tasks = (legacy_tasks + cells_per - 1) // cells_per
    if legacy_tasks != 1132 or cells_per != 2 or array_tasks != 566:
        raise RecoveryError("only the audited 1132-to-566 array amendment is allowed")
    run_ids_digest = sha256_bytes(canonical_bytes(wave["run_ids"]))
    legacy_intent_digest = sha256_file(legacy_intent_path)
    path_environment = manifest["runtime"]["execution_environment"]["path"]
    srun = executable_identity("srun", path_environment)
    environment = executable_identity("env", path_environment)
    execution_policy = array_limit_execution_policy()
    batch_throttle = max(1, E.ARRAY_THROTTLE // cells_per)
    if batch_throttle != execution_policy["batch_array_throttle"]:
        raise RecoveryError("batched recovery throttle changed")
    nonce = sha256_bytes(
        canonical_bytes(
            _array_limit_nonce_payload(
                manifest_digest,
                wave_digest,
                legacy_intent_digest,
                run_ids_digest,
                maximum,
                cells_per,
                array_tasks,
                amended_digest,
                srun,
                environment,
                execution_policy,
            )
        )
    )[:16]
    job_name = "pdbprof-b{:02d}-{}".format(number, nonce[:12])
    wrapper = batch_runner_text(
        wave,
        job_name=job_name,
        array_tasks=array_tasks,
        cells_per_array_task=cells_per,
        srun_path=srun["path"],
        srun_sha256=srun["sha256"],
        env_path=environment["path"],
        env_sha256=environment["sha256"],
    )
    wrapper_raw = wrapper.encode("ascii")
    if batch_path.exists() or batch_path.is_symlink():
        if (
            batch_path.is_symlink()
            or not batch_path.is_file()
            or not os.access(batch_path, os.X_OK)
            or batch_path.read_bytes() != wrapper_raw
        ):
            raise RecoveryError("existing batched runner differs")
    else:
        write_text_artifact(batch_path, wrapper, executable=True)
    original_runner = wave["runner"]
    batching = {
        "path": batch_path.relative_to(REPO).as_posix(),
        "size": len(wrapper_raw),
        "sha256": sha256_bytes(wrapper_raw),
        "nonce": nonce,
        "job_name": job_name,
        "array_spec": "1-{}%{}".format(array_tasks, batch_throttle),
        "array_tasks": array_tasks,
        "array_throttle": batch_throttle,
        "cells_per_array_task": cells_per,
        "run_ids_sha256": run_ids_digest,
        "legacy_runner_path": wave_runner_path(number)
        .relative_to(REPO)
        .as_posix(),
        "legacy_runner_sha256": original_runner["sha256"],
        "srun": srun,
        "env": environment,
        "execution_policy": execution_policy,
        "wall_time": original_runner["wall_time"],
        "memory_per_cpu": original_runner["memory_per_cpu"],
        "cpus_per_task": cells_per * original_runner["cpus_per_task"],
        "partition": original_runner["partition"],
        "qos": original_runner["qos"],
        "account": original_runner["account"],
        "requeue": False,
        "submission_environment_export": original_runner[
            "submission_environment_export"
        ],
    }
    value = {
        "schema": ARRAY_LIMIT_AMENDMENT_SCHEMA,
        "action": "replace-rejected-oversized-array-with-batched-wrapper",
        "created_utc": utc_now(),
        "manifest_sha256": manifest_digest,
        "wave": number,
        "wave_manifest_sha256": wave_digest,
        "legacy_submission": {
            "intent_path": legacy_intent_path.relative_to(REPO).as_posix(),
            "intent_sha256": legacy_intent_digest,
            "job_name": legacy_intent["job_name"],
            "array_spec": legacy_intent["array_spec"],
            "array_tasks": legacy_intent["array_tasks"],
            "requested_max_index": legacy_tasks,
            "absence_checked_utc": utc_now(),
            "matching_job_ids": [],
            "test_only_exit_code": rejection.returncode,
            "test_only_stdout": rejection.stdout,
            "test_only_stderr": rejection.stderr,
        },
        "slurm_limit": {
            "query": "scontrol show config",
            "max_array_size": maximum,
            "maximum_array_index": maximum_index,
        },
        "protocol_dependency_amendment": dependency_amendment,
        "outcome_access": {
            "planner_outcomes_parsed": False,
            "completion_sentinels_inspected": False,
        },
        "batching": batching,
    }
    write_artifact(amendment_path, value)
    load_array_limit_amendment(wave, manifest, manifest_digest)
    print(
        "sealed array-limit amendment: {} cells as {} concurrent batches".format(
            legacy_tasks, array_tasks
        )
    )


def submit_recovery() -> None:
    manifest, manifest_digest = load_manifest()
    waves = load_all_waves(manifest, manifest_digest)
    wave, wave_digest = waves[-1]
    if RESTORE_INTENT.exists() or RESTORE_RECEIPT.exists():
        raise RecoveryError("recovery was restored and may not be submitted")
    expected_intent = _expected_submit_intent(
        wave, manifest_digest, manifest=manifest
    )
    intent_path = submission_intent_path(wave["wave"])
    receipt_path = submission_receipt_path(wave["wave"])
    if receipt_path.exists() or receipt_path.is_symlink():
        load_wave_submit_receipt(wave, manifest_digest)
        raise RecoveryError("recovery submission is already sealed")
    # Lost-response reconciliation deliberately precedes every live-output and
    # provenance precondition.  Once an intent exists, this path never calls
    # sbatch again; zero matches remain unresolved and therefore fail closed.
    if intent_path.exists() or intent_path.is_symlink():
        intent = load_wave_submit_intent(wave, manifest_digest)
        for field, expected in expected_intent.items():
            if field != "created_utc" and not exact_json_equal(
                intent.get(field), expected
            ):
                raise RecoveryError("existing recovery submit intent changed")
        jobs = find_jobs_by_identity(intent)
        if _has_array_limit_amendment(wave["wave"]):
            _submission_contract(wave, manifest_digest, manifest=manifest)
        if len(jobs) == 1:
            job_id = next(iter(jobs))
            _seal_submit_receipt(
                manifest_digest, wave, intent, job_id, "reconciled", ""
            )
            print("reconciled recovery job {}".format(job_id))
            return
        if len(jobs) > 1:
            raise RecoveryError("multiple jobs match the unique recovery nonce")
        raise RecoveryError(
            "submission intent is unresolved and was not resubmitted; rerun --submit after Slurm accounting catches up"
        )

    if _has_array_limit_amendment(wave["wave"]):
        legacy_intent = load_canonical_artifact(
            wave_intent_path(wave["wave"]), RECEIPT_SCHEMA
        )
        legacy_jobs = find_jobs_by_identity(legacy_intent)
        if legacy_jobs:
            raise RecoveryError(
                "the rejected legacy submission appeared after its absence receipt"
            )
        contract = _submission_contract(
            wave, manifest_digest, manifest=manifest
        )
        if contract["array_tasks"] > slurm_max_array_size() - 1:
            raise RecoveryError("batched recovery still exceeds Slurm MaxArraySize")

    for prior_wave, prior_digest in waves[:-1]:
        verify_wave_ready(
            prior_wave,
            prior_digest,
            manifest,
            manifest_digest,
            require_clean=False,
        )
    verify_wave_ready(wave, wave_digest, manifest, manifest_digest)
    verify_cleanup_receipt(manifest_digest)
    reattest_execution_inputs(manifest, require_clean=False)
    verify_untouched_cells(manifest)
    _protected_recovered_cells(wave)
    for run_id in wave["run_ids"]:
        if dynamic_top_names(snapshot_tree(_safe_run_root(run_id))):
            raise RecoveryError("recovery wave cell is not clean: {}".format(run_id))
    lock_dir = wave_directory(wave["wave"]) / "locks"
    _lstat_directory(lock_dir, "recovery wave locks")
    if list(lock_dir.iterdir()):
        raise RecoveryError("recovery wave lock directory is not initially empty")
    expected_intent["created_utc"] = utc_now()
    write_artifact(intent_path, expected_intent)
    intent = expected_intent
    try:
        result = subprocess.run(
            _submission_argv(wave, manifest_digest, manifest=manifest),
            cwd=wave_directory(wave["wave"]),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError(
            "recovery submission is unresolved; rerun --submit to reconcile"
        ) from err
    job_id = result.stdout.strip().split(";", 1)[0]
    _seal_submit_receipt(
        manifest_digest,
        wave,
        intent,
        job_id,
        "direct-sbatch",
        result.stdout.strip(),
    )
    print("submitted cell-exact recovery wave {} as job {}".format(wave["wave"], job_id))


def load_wave_submit_receipt(wave: dict, manifest_digest: str) -> dict:
    intent = load_wave_submit_intent(wave, manifest_digest)
    manifest, loaded_digest = load_manifest()
    if loaded_digest != manifest_digest:
        raise RecoveryError("submit receipt manifest digest changed")
    expected_intent = _expected_submit_intent(
        wave, manifest_digest, manifest=manifest
    )
    if any(
        field != "created_utc"
        and not exact_json_equal(intent.get(field), expected)
        for field, expected in expected_intent.items()
    ):
        raise RecoveryError("recovery submit intent differs from its contract")
    receipt_path = submission_receipt_path(wave["wave"])
    receipt = load_canonical_artifact(receipt_path, RECEIPT_SCHEMA)
    required = {
        "action": "cell-exact-recovery-submitted",
        "manifest_sha256": manifest_digest,
        "wave": wave["wave"],
        "wave_manifest_sha256": sha256_file(wave_manifest_path(wave["wave"])),
        "intent_sha256": sha256_file(submission_intent_path(wave["wave"])),
        "job_name": intent["job_name"],
        "array_spec": intent["array_spec"],
        "scheduler_comment": intent["scheduler_comment"],
        "runner_sha256": intent["runner_sha256"],
    }
    if any(
        not exact_json_equal(receipt.get(field), expected)
        for field, expected in required.items()
    ):
        raise RecoveryError("recovery submit receipt changed")
    if JOB_ID_RE.fullmatch(receipt.get("recovery_job_id", "")) is None:
        raise RecoveryError("submit receipt has an invalid job ID")
    return receipt


def detailed_recovery_records(job_id: str, expected_tasks: set[int]) -> list[dict]:
    try:
        queued = subprocess.run(
            ["squeue", "-h", "-r", "-j", job_id, "-o", "%i|%T"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if queued.stdout.strip():
            raise RecoveryError("recovery array is still active")
        result = subprocess.run(
            [
                "sacct",
                "-n",
                "-X",
                "-j",
                job_id,
                "--format={}".format(RECOVERY_SACCT_FORMAT),
                "-P",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("cannot query detailed recovery accounting") from err
    records = {}
    pattern = re.compile(
        r"^{}_(0|[1-9][0-9]*)$".format(re.escape(job_id))
    )
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        fields = line.split("|")
        if len(fields) != 14:
            raise RecoveryError("detailed sacct record has the wrong field count")
        match = pattern.fullmatch(fields[0])
        if match is None:
            continue
        task = int(match.group(1))
        if task in records:
            raise RecoveryError("detailed sacct repeats a recovery task")
        state_base = normalized_slurm_state(fields[2])
        if state_base not in TERMINAL_STATES:
            raise RecoveryError("recovery task is not terminal")
        records[task] = {
            "array_task_id": task,
            "job_id_raw": fields[1],
            "state": fields[2],
            "state_base": state_base,
            "job_name": fields[3],
            "submit": fields[4],
            "work_dir": fields[5],
            "requested_memory": fields[6],
            "requested_cpus": fields[7],
            "time_limit": fields[8],
            "account": fields[9],
            "partition": fields[10],
            "qos": fields[11],
            "comment": fields[12],
            "submit_line": fields[13],
        }
    if set(records) != expected_tasks:
        raise RecoveryError("detailed recovery task set changed")
    return [records[task] for task in sorted(records)]


def validate_wave_scheduler(
    wave: dict, receipt: dict, records: list[dict]
) -> None:
    intent = load_wave_submit_intent(wave, receipt["manifest_sha256"])
    expected = _expected_scheduler_metadata(intent)
    expected_tasks = list(range(1, intent["array_tasks"] + 1))
    if [record["array_task_id"] for record in records] != expected_tasks:
        raise RecoveryError("recovery scheduler task order changed")
    for record in records:
        if not scheduler_metadata_matches(record, expected):
            raise RecoveryError("recovery scheduler metadata changed")
        if record["submit_line"] != intent["submit_line"]:
            raise RecoveryError("recovery scheduler submit command changed")
        if (
            normalized_slurm_state(record["state"]) != record["state_base"]
            or record["state_base"] not in RECOVERABLE_STATES | {"COMPLETED"}
        ):
            raise RecoveryError("recovery scheduler state violates retry policy")


def _install_retry_wave_bundle(wave: dict, runner: str) -> str:
    number = wave["wave"]
    destination = wave_directory(number)
    if destination.exists() or destination.is_symlink():
        raise RecoveryError("retry wave directory already exists")
    stage = Path(
        tempfile.mkdtemp(prefix=".pdb-profile-wave-", dir=ARTIFACT_DIR.parent)
    )
    try:
        (stage / "locks").mkdir()
        (stage / "previous-wave-prefixes").mkdir()
        (stage / "prefix-cell-seals").mkdir()
        runner_path = stage / "recover-cells.sh"
        runner_path.write_text(runner, encoding="ascii")
        runner_path.chmod(0o755)
        manifest_path = stage / "wave-manifest.json"
        manifest_path.write_bytes(canonical_bytes(wave) + b"\n")
        manifest_path.chmod(0o444)
        for path in (runner_path, manifest_path):
            with path.open("rb") as stream:
                os.fsync(stream.fileno())
        for directory in (
            stage / "locks",
            stage / "previous-wave-prefixes",
            stage / "prefix-cell-seals",
            stage,
        ):
            _fsync_directory(directory)
        os.replace(stage, destination)
        _fsync_directory(WAVES_DIR)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return sha256_file(wave_manifest_path(number))


def _complete_retry_archive(
    wave: dict, wave_digest: str, manifest: dict, manifest_digest: str
) -> None:
    number = wave["wave"]
    if number <= 1:
        raise RecoveryError("first recovery wave uses the original-prefix archive")
    _lstat_directory(wave_directory(number), "retry wave")
    _lstat_directory(_wave_archive_base(number), "retry prefix archive")
    _lstat_directory(
        wave_directory(number) / "prefix-cell-seals", "retry prefix seals"
    )
    for cell in wave["retry_input_cells"]:
        run_id = cell["run_id"]
        destination = _safe_wave_archive_root(
            wave_directory(number), run_id, create=True
        )
        quarantine_cell(cell, _safe_run_root(run_id), destination)
        seal_path = _wave_cell_seal_path(number, run_id)
        expected = _wave_cell_seal_value(number, wave_digest, cell)
        if seal_path.exists() or seal_path.is_symlink():
            if load_canonical_artifact(seal_path, WAVE_CELL_SEAL_SCHEMA) != expected:
                raise RecoveryError("existing retry cell seal changed")
        else:
            write_artifact(seal_path, expected)
    verify_retry_archive(wave, wave_digest, require_clean=True)
    _write_or_verify_ready(
        number,
        {
            "action": "previous-wave-prefixes-ready",
            "manifest_sha256": manifest_digest,
            "wave": number,
            "wave_manifest_sha256": wave_digest,
            "archive_tree_sha256": snapshot_digest(
                snapshot_tree(_wave_archive_base(number))
            ),
            "outcomes_parsed": False,
        },
    )
    verify_wave_ready(wave, wave_digest, manifest, manifest_digest)


def prepare_retry_wave() -> None:
    manifest, manifest_digest = load_manifest()
    waves = load_all_waves(manifest, manifest_digest)
    current, current_digest = waves[-1]
    current_number = current["wave"]
    current_receipt_path = submission_receipt_path(current_number)
    if not current_receipt_path.exists() and not current_receipt_path.is_symlink():
        if (
            current_number > 1
            and not submission_intent_path(current_number).exists()
            and not submission_intent_path(current_number).is_symlink()
        ):
            _complete_retry_archive(
                current, current_digest, manifest, manifest_digest
            )
            print("recovery retry wave {} is archive-ready".format(current_number))
            return
        raise RecoveryError("latest recovery wave has not been submitted")
    receipt = load_wave_submit_receipt(current, manifest_digest)
    current_intent = load_wave_submit_intent(current, manifest_digest)
    scheduler = detailed_recovery_records(
        receipt["recovery_job_id"],
        set(range(1, current_intent["array_tasks"] + 1)),
    )
    validate_wave_scheduler(current, receipt, scheduler)
    for wave, wave_digest in waves:
        verify_wave_ready(
            wave,
            wave_digest,
            manifest,
            manifest_digest,
            require_clean=False,
        )
    verify_cleanup_receipt(manifest_digest)
    reattest_execution_inputs(manifest, require_clean=False)
    verify_untouched_cells(manifest)
    _protected_recovered_cells(current)
    protected = list(current["protected_recovered_cell_hashes"])
    retry_inputs = []
    source_decisions = []
    cells_per = current_intent.get("batching", {}).get(
        "cells_per_array_task", 1
    )
    for position, run_id in enumerate(current["run_ids"]):
        task = position // cells_per + 1
        root = _safe_run_root(run_id)
        records = snapshot_tree(root)
        validate_static_inputs(root, records)
        record = scheduler[task - 1]
        complete = driver_log_complete(root / "driver.log")
        action = recovery_wave_cell_action(record["state_base"], complete)
        tree_digest = snapshot_digest(records)
        source_decisions.append(
            {
                "run_id": run_id,
                "source_array_task_id": task,
                "scheduler_state": record["state_base"],
                "completion_test_passed": complete,
                "action": action,
                "tree_sha256": tree_digest,
            }
        )
        if action == "protect":
            protected.append([run_id, tree_digest])
        elif action == "retry":
            retry_inputs.append(
                {
                    "run_id": run_id,
                    "tree_sha256": tree_digest,
                    "entries": records,
                    "dynamic_top_names": dynamic_top_names(records),
                }
            )
    protected.sort()
    if not retry_inputs:
        print("latest recovery wave needs no retry; run --verify")
        return
    next_number = current_number + 1
    previous = {
        "wave": current_number,
        "wave_manifest_sha256": current_digest,
        "submit_receipt_sha256": sha256_file(current_receipt_path),
        "recovery_job_id": receipt["recovery_job_id"],
    }
    next_wave, runner = build_wave(
        manifest,
        manifest_digest,
        next_number,
        [cell["run_id"] for cell in retry_inputs],
        previous_wave=previous,
        source_scheduler_records=scheduler,
        source_cell_decisions=source_decisions,
        retry_input_cells=retry_inputs,
        protected_recovered_cell_hashes=protected,
    )
    next_digest = _install_retry_wave_bundle(next_wave, runner)
    _complete_retry_archive(next_wave, next_digest, manifest, manifest_digest)
    print(
        "prepared outcome-blind recovery wave {} for {} cells".format(
            next_number, len(retry_inputs)
        )
    )


def verify_recovery() -> None:
    manifest, manifest_digest = load_manifest()
    waves = load_all_waves(manifest, manifest_digest)
    reattest_execution_inputs(manifest, require_clean=False)
    verify_quarantine(manifest, manifest_digest, require_clean=False)
    verify_cleanup_receipt(manifest_digest)
    wave_records = []
    for wave, wave_digest in waves:
        verify_wave_ready(
            wave,
            wave_digest,
            manifest,
            manifest_digest,
            require_clean=False,
        )
        receipt = load_wave_submit_receipt(wave, manifest_digest)
        intent = load_wave_submit_intent(wave, manifest_digest)
        scheduler = detailed_recovery_records(
            receipt["recovery_job_id"],
            set(range(1, intent["array_tasks"] + 1)),
        )
        validate_wave_scheduler(wave, receipt, scheduler)
        wave_records.append(
            {
                "wave": wave["wave"],
                "wave_manifest_sha256": wave_digest,
                "submit_receipt_sha256": sha256_file(
                    submission_receipt_path(wave["wave"])
                ),
                "recovery_job_id": receipt["recovery_job_id"],
                "scheduler_records": scheduler,
            }
        )
    latest, _ = waves[-1]
    _protected_recovered_cells(latest)
    all_hashes = []
    verify_untouched_cells(manifest)
    all_hashes.extend(manifest["complete_cell_tree_hashes"])
    recovered = []
    for cell in manifest["recovery_cells"]:
        root = _safe_run_root(cell["run_id"])
        if not driver_log_complete(root / "driver.log"):
            raise RecoveryError("recovered cell lacks its final driver sentinel")
        records = snapshot_tree(root)
        digest = snapshot_digest(records)
        recovered.append(
            {
                "run_id": cell["run_id"],
                "latest_recovery_array_task_id": (
                    submission_task_for_run_position(
                        latest,
                        latest["run_ids"].index(cell["run_id"]),
                        manifest,
                        manifest_digest,
                    )
                    if cell["run_id"] in latest["run_ids"]
                    else None
                ),
                "tree_sha256": digest,
            }
        )
        all_hashes.append([cell["run_id"], digest])
    all_hashes.sort()
    if [item[0] for item in all_hashes] != list(range(1, P.CELL_COUNT + 1)):
        raise RecoveryError("verified matrix cell partition is incomplete")
    existing = None
    if VERIFICATION.exists() or VERIFICATION.is_symlink():
        existing = load_canonical_artifact(VERIFICATION, VERIFICATION_SCHEMA)
    value = {
        "schema": VERIFICATION_SCHEMA,
        "created_utc": existing["created_utc"] if existing else utc_now(),
        "manifest_sha256": manifest_digest,
        "latest_submit_receipt_sha256": sha256_file(
            submission_receipt_path(latest["wave"])
        ),
        "latest_recovery_job_id": wave_records[-1]["recovery_job_id"],
        "recovery_waves": wave_records,
        "complete_cells": P.CELL_COUNT,
        "untouched_cells_identical": True,
        "outcomes_parsed": False,
        "recovered_cells": recovered,
        "full_matrix_tree_sha256": sha256_bytes(canonical_bytes(all_hashes)),
        "original_prefix_archive_tree_sha256": snapshot_digest(
            snapshot_tree(QUARANTINE)
        ),
        "recovery_waves_tree_sha256": snapshot_digest(snapshot_tree(WAVES_DIR)),
    }
    digest = write_artifact_pair(VERIFICATION, value)
    print("verified complete unchanged-plus-recovered matrix; sha256 {}".format(digest))


def self_test() -> None:
    assert exact_json_equal(
        {"boolean": False, "integer": 0},
        {"integer": 0, "boolean": False},
    )
    for left, right in ((False, 0), (True, 1), ({"x": False}, {"x": 0})):
        assert not exact_json_equal(left, right)
    assert RECOVERABLE_STATES == {"NODE_FAIL", "TIMEOUT"}
    assert not ({"FAILED", "OUT_OF_MEMORY", "PREEMPTED"} & RECOVERABLE_STATES)
    assert normalized_slurm_state("NODE_FAIL+") == "NODE_FAIL"
    for state in sorted(RECOVERABLE_STATES):
        require_recoverable_cell_state(1, state, "test cell")
    for state in ("COMPLETED", "FAILED", "OUT_OF_MEMORY", "PREEMPTED"):
        try:
            require_recoverable_cell_state(1, state, "test cell")
        except RecoveryError:
            pass
        else:
            raise AssertionError("nonrecoverable scheduler state was accepted")
    for state in ("NODE_FAIL", "TIMEOUT", "COMPLETED"):
        assert recovery_wave_cell_action(state, True) == "protect"
    for state in ("NODE_FAIL", "TIMEOUT"):
        assert recovery_wave_cell_action(state, False) == "retry"
    for state in ("COMPLETED", "FAILED", "OUT_OF_MEMORY", "PREEMPTED"):
        for complete in (False, True):
            if state == "COMPLETED" and complete:
                continue
            try:
                recovery_wave_cell_action(state, complete)
            except RecoveryError:
                pass
            else:
                raise AssertionError("invalid recovery-wave action was accepted")
    assert recovery_retry_policy() == {
        "completion_test": (
            "last-line-shape-only;numeric-exit-value-not-recorded/v1"
        ),
        "complete_cell_action": "protect-regardless-of-allowed-scheduler-state",
        "retry_incomplete_scheduler_states": ["NODE_FAIL", "TIMEOUT"],
        "completed_incomplete_action": "fail-closed",
        "unsupported_scheduler_state_action": "fail-closed",
    }
    source_record = {
        "array_task_id": 1,
        "job_id_raw": "8",
        "state": "NODE_FAIL",
        "state_base": "NODE_FAIL",
        "job_name": "recovery",
        "submit": "2026-08-30T12:00:00",
        "work_dir": "/sealed/wave",
        "requested_memory": "9Gc",
        "requested_cpus": "1",
        "time_limit": RECOVERY_WALL_TIME,
        "account": E.ACCOUNT,
        "partition": "cpu",
        "qos": "normal",
        "comment": "sealed",
        "submit_line": "sbatch sealed-runner",
    }
    retry_decision = {
        "run_id": 1,
        "source_array_task_id": 1,
        "scheduler_state": "NODE_FAIL",
        "completion_test_passed": False,
        "action": "retry",
        "tree_sha256": "a" * 64,
    }
    validate_retry_source_decisions(
        [source_record],
        [retry_decision],
        [{"run_id": 1, "tree_sha256": "a" * 64}],
        [],
    )
    protect_decision = {
        **retry_decision,
        "completion_test_passed": True,
        "action": "protect",
    }
    validate_retry_source_decisions(
        [source_record], [protect_decision], [], [[1, "a" * 64]]
    )
    source_record_two = {
        **source_record,
        "array_task_id": 2,
        "job_id_raw": "9",
        "state": "TIMEOUT",
        "state_base": "TIMEOUT",
    }
    batched_decisions = [
        retry_decision,
        {
            **protect_decision,
            "run_id": 2,
            "tree_sha256": "b" * 64,
        },
        {
            **retry_decision,
            "run_id": 3,
            "source_array_task_id": 2,
            "scheduler_state": "TIMEOUT",
            "tree_sha256": "c" * 64,
        },
        {
            **retry_decision,
            "run_id": 4,
            "source_array_task_id": 2,
            "scheduler_state": "TIMEOUT",
            "tree_sha256": "d" * 64,
        },
    ]
    validate_retry_source_decisions(
        [source_record, source_record_two],
        batched_decisions,
        [
            {"run_id": 1, "tree_sha256": "a" * 64},
            {"run_id": 3, "tree_sha256": "c" * 64},
            {"run_id": 4, "tree_sha256": "d" * 64},
        ],
        [[2, "b" * 64]],
    )
    try:
        validate_retry_source_decisions(
            [source_record, source_record_two],
            [batched_decisions[0], batched_decisions[2], batched_decisions[1], batched_decisions[3]],
            [
                {"run_id": 1, "tree_sha256": "a" * 64},
                {"run_id": 3, "tree_sha256": "c" * 64},
                {"run_id": 4, "tree_sha256": "d" * 64},
            ],
            [[2, "b" * 64]],
        )
    except RecoveryError:
        pass
    else:
        raise AssertionError("noncontiguous recovery batch mapping was accepted")
    adversarial_sources_and_decisions = (
        (
            [{**source_record, "state": "FAILED", "state_base": "FAILED"}],
            [retry_decision],
        ),
        ([source_record], [{**retry_decision, "action": "protect"}]),
        ([source_record], [{**retry_decision, "scheduler_state": "TIMEOUT"}]),
    )
    for bad_source, bad_decisions in adversarial_sources_and_decisions:
        try:
            validate_retry_source_decisions(
                bad_source,
                bad_decisions,
                [{"run_id": 1, "tree_sha256": "a" * 64}],
                [],
            )
        except RecoveryError:
            pass
        else:
            raise AssertionError("tampered retry source decision was accepted")
    launch = {
        "job_id": "7",
        "job_name": "main-array",
        "submit_time": "2026-08-25T10:02:35",
        "work_directory": "/sealed/main",
        "memory_per_cpu": "9G",
        "cpus_per_task": 1,
        "wall_time": E.SCHEDULER_TIME_LIMIT,
        "account": E.ACCOUNT,
        "partition": "cpu",
        "qos": "normal",
        "submit_line": "sbatch --export PATH /sealed/main/start",
    }
    mutation = {
        "job_id": launch["job_id"],
        "mutations": {
            "partition": {
                "array_task_first": 2,
                "array_task_last": 2,
                "to": "fat",
            }
        },
        "post_terminal_attestation": {
            "array_task_count": 2,
            "partition_counts": {"cpu": 1, "fat": 1},
        },
    }

    def scheduler_suffix(partition):
        return "|".join(
            [
                launch["job_name"],
                launch["submit_time"],
                launch["work_directory"],
                launch["memory_per_cpu"],
                str(launch["cpus_per_task"]),
                launch["account"],
                partition,
                launch["qos"],
                launch["submit_line"],
            ]
        )

    completed = (
        "7_1|8|COMPLETED|12|{wall}|0:0|n1|{cpu_suffix}\n"
        "7_2|9|TIMEOUT|9000|{wall}|0:0|n2|{fat_suffix}\n"
    ).format(
        wall=launch["wall_time"],
        cpu_suffix=scheduler_suffix("cpu"),
        fat_suffix=scheduler_suffix("fat"),
    )
    parsed = parse_sacct(completed, "7", {1, 2}, launch, mutation)
    assert [item["state_base"] for item in parsed] == ["COMPLETED", "TIMEOUT"]
    assert all(
        marker in MAIN_SACCT_FORMAT
        for marker in ("JobID%256", "JobName%512", "WorkDir%2048", "SubmitLine%4096")
    )
    assert "Comment%2048" in RECONCILIATION_SACCT_FORMAT
    assert "SubmitLine%4096" in RECOVERY_SACCT_FORMAT
    try:
        parse_sacct(
            completed.replace(launch["submit_line"], launch["submit_line"][:20] + "+"),
            "7",
            {1, 2},
            launch,
            mutation,
        )
    except RecoveryError:
        pass
    else:
        raise AssertionError("truncated scheduler identity was accepted")
    try:
        parse_sacct(
            "7_1|8|RUNNING|12|{wall}|0:0|n1|{suffix}\n".format(
                wall=launch["wall_time"], suffix=scheduler_suffix("cpu")
            ),
            "7",
            {1},
            launch,
            mutation,
        )
    except RecoveryError:
        pass
    else:
        raise AssertionError("nonterminal scheduler row was accepted")
    try:
        parse_sacct(
            completed.replace(scheduler_suffix("fat"), scheduler_suffix("cpu")),
            "7",
            {1, 2},
            launch,
            mutation,
        )
    except RecoveryError:
        pass
    else:
        raise AssertionError("unauthorized scheduler partition was accepted")
    try:
        parse_sacct(
            completed
            + "7_0|10|COMPLETED|1|{wall}|0:0|n3|{suffix}\n".format(
                wall=launch["wall_time"], suffix=scheduler_suffix("cpu")
            ),
            "7",
            {1, 2},
            launch,
            mutation,
        )
    except RecoveryError:
        pass
    else:
        raise AssertionError("unexpected zero-indexed scheduler task was accepted")
    synthetic_launcher = "\n".join(
        [
            "#SBATCH --array=1-{}%{}".format(EXPECTED_ARRAY_TASKS, E.ARRAY_THROTTLE),
            "#SBATCH --partition=cpu",
            "#SBATCH --qos=normal",
            "#SBATCH --time={}".format(E.SCHEDULER_TIME_LIMIT),
            "#SBATCH --mem-per-cpu={}".format(E.SCHEDULER_MEMORY),
            "#SBATCH --cpus-per-task=1",
            "#SBATCH --account={}".format(E.ACCOUNT),
            "ulimit -Sv 9248440",
            '"{}" run'.format(VENV_PYTHON),
            "declare -a SHUFFLED_TASK_IDS=({})".format(
                " ".join(map(str, range(1, EXPECTED_ARRAY_TASKS + 1)))
            ),
            "TASK_ID=${SHUFFLED_TASK_IDS[$SLURM_ARRAY_TASK_ID - 1]}",
            "NUM_RUNS={}".format(P.CELL_COUNT),
            "RUNS_PER_TASK={}".format(E.RUNS_PER_ARRAY_TASK),
            'let "FIRST_RUN_ID=(TASK_ID - 1) * RUNS_PER_TASK + 1"',
            'let "LAST_RUN_ID=FIRST_RUN_ID + RUNS_PER_TASK - 1"',
            "for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID | shuf); do",
            '(cd "../exp_pdb_profile_comparison/$run_dir" && execute_run ${run_id})',
            "if [[ -f driver.log ]]; then",
        ]
    )
    mapping = parse_original_launcher(synthetic_launcher)
    assert array_task_for_run(1, mapping["group_to_slot"]) == 1
    assert array_task_for_run(24, mapping["group_to_slot"]) == 1
    assert array_task_for_run(25, mapping["group_to_slot"]) == 2
    assert array_task_for_run(P.CELL_COUNT, mapping["group_to_slot"]) == 996
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        log = root / "driver.log"
        log.write_bytes(
            b"2026-08-29 12:00:00,000 INFO     node: n1\n"
            b"2026-08-29 12:00:01,000 INFO     planner exit code: 23\n"
        )
        assert driver_log_complete(log)
        payload = root / "payload"
        payload.write_bytes(b"abc")
        link = root / "link"
        link.symlink_to("payload")
        records = snapshot_tree(root)
        assert snapshot_digest(records) == snapshot_digest(records)
        assert {record["type"] for record in records} == {"file", "symlink"}
        source = root / "source"
        destination = root / "archive"
        source.mkdir()
        destination.mkdir()
        (source / "run").write_bytes(b"static")
        (source / "driver.log").write_bytes(b"prefix")
        original = snapshot_tree(source)
        cell = {
            "run_id": 1,
            "entries": original,
            "dynamic_top_names": ["driver.log"],
        }
        assert quarantine_cell(
            cell, source, destination, allow_untrusted_test_roots=True
        ) == ["driver.log"]
        assert quarantine_cell(
            cell, source, destination, allow_untrusted_test_roots=True
        ) == []
        assert not (source / "driver.log").exists()
        assert (destination / "driver.log").read_bytes() == b"prefix"
        source2 = root / "source2"
        destination2 = root / "archive2"
        source2.mkdir()
        destination2.mkdir()
        (source2 / "run").write_bytes(b"static")
        (source2 / "driver.log").write_bytes(b"prefix")
        (source2 / "run.log").write_bytes(b"work")
        interrupted = {
            "run_id": 1,
            "entries": snapshot_tree(source2),
            "dynamic_top_names": ["driver.log", "run.log"],
        }
        os.replace(source2 / "driver.log", destination2 / "driver.log")
        assert quarantine_cell(
            interrupted,
            source2,
            destination2,
            allow_untrusted_test_roots=True,
        ) == ["run.log"]
        os.replace(destination2 / "run.log", source2 / "run.log")
        assert restore_cell(
            interrupted,
            source2,
            destination2,
            allow_untrusted_test_roots=True,
        ) == ["driver.log"]
        assert restore_cell(
            interrupted,
            source2,
            destination2,
            allow_untrusted_test_roots=True,
        ) == []
        confined = root / "confined"
        (confined / "bucket" / "run").mkdir(parents=True)
        assert _confined_directory(
            confined, Path("bucket/run"), "test"
        ) == confined / "bucket" / "run"
        outside = root / "outside"
        outside.mkdir()
        (confined / "linked").symlink_to(outside, target_is_directory=True)
        try:
            _confined_directory(confined, Path("linked/run"), "test")
        except RecoveryError:
            pass
        else:
            raise AssertionError("symlinked bucket directory was accepted")
        module = os.sys.modules[__name__]
        real_artifacts = root / "real-artifacts"
        real_artifacts.mkdir()
        linked_artifacts = root / "linked-artifacts"
        linked_artifacts.symlink_to(real_artifacts, target_is_directory=True)
        with mock.patch.object(module, "ARTIFACT_DIR", linked_artifacts), mock.patch.object(
            module, "QUARANTINE", linked_artifacts / "original-prefixes-v1"
        ):
            try:
                _safe_quarantine_root(1, create=True)
            except RecoveryError:
                pass
            else:
                raise AssertionError("linked artifact ancestor was accepted")
        anchored_artifacts = root / "anchored-artifacts"
        waves = anchored_artifacts / "waves"
        waves.mkdir(parents=True)
        outside_wave = root / "outside-wave"
        outside_wave.mkdir()
        linked_wave = waves / "wave-0001"
        linked_wave.symlink_to(outside_wave, target_is_directory=True)
        with mock.patch.object(module, "ARTIFACT_DIR", anchored_artifacts):
            try:
                _safe_wave_archive_root(linked_wave, 1, create=True)
            except RecoveryError:
                pass
            else:
                raise AssertionError("linked wave ancestor was accepted")
        pair = root / "verification.json"
        pair_value = {"schema": "test/v1", "value": 1}
        pair.write_bytes(canonical_bytes(pair_value) + b"\n")
        pair.chmod(0o444)
        write_artifact_pair(pair, pair_value)
        write_artifact_pair(pair, pair_value)
        assert pair.with_name(pair.name + ".sha256").is_file()
    assert memory_matches_per_cpu("9G")
    assert memory_matches_per_cpu("9Gc")
    assert memory_matches_per_cpu("9216Mc")
    assert not memory_matches_per_cpu("9Gn")
    assert _array_expression_tasks(
        "[1-5%{}]".format(E.ARRAY_THROTTLE)
    ) == set(range(1, 6))
    intent = {
        "job_name": "pdbprof-w01-aaaaaaaaaaaa",
        "created_utc": "2026-08-29T12:00:00Z",
        "array_spec": "1-2%{}".format(E.ARRAY_THROTTLE),
        "array_tasks": 2,
        "work_directory": "/sealed/wave",
        "scheduler_comment": "pdbprof:sealed",
        "submit_line": "sbatch --sealed /sealed/wave/recover-cells.sh",
        "runner_path": "/sealed/wave/recover-cells.sh",
    }
    row = "{job}_{task}|{name}|2026-08-29T12:00:01|{work}|9Gc|1|2:30:00|{account}|cpu|normal|{comment}|{submit}"
    accounting = "\n".join(
        row.format(
            job=77,
            task=task,
            name=intent["job_name"],
            work=intent["work_directory"],
            account=E.ACCOUNT,
            comment=intent["scheduler_comment"],
            submit=intent["submit_line"],
        )
        for task in (1, 2)
    ) + "\n"
    empty = subprocess.CompletedProcess([], 0, stdout="", stderr="")
    accounted = subprocess.CompletedProcess([], 0, stdout=accounting, stderr="")
    with mock.patch.object(subprocess, "run", side_effect=[empty, accounted]):
        assert find_jobs_by_identity(intent) == {"77"}
    with mock.patch.object(subprocess, "run", side_effect=[empty, empty]):
        assert find_jobs_by_identity(intent) == set()
    accounting_two = accounting + accounting.replace("77_", "78_")
    with mock.patch.object(
        subprocess,
        "run",
        side_effect=[
            empty,
            subprocess.CompletedProcess([], 0, stdout=accounting_two, stderr=""),
        ],
    ):
        assert find_jobs_by_identity(intent) == {"77", "78"}
    bad_memory = accounting.replace("9Gc", "9Gn")
    with mock.patch.object(
        subprocess,
        "run",
        side_effect=[
            empty,
            subprocess.CompletedProcess([], 0, stdout=bad_memory, stderr=""),
        ],
    ):
        try:
            find_jobs_by_identity(intent)
        except RecoveryError:
            pass
        else:
            raise AssertionError("per-node recovery memory was accepted")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        intent_path = root / "intent.json"
        intent_path.write_text("sealed\n", encoding="ascii")
        receipt_path = root / "receipt.json"
        restore_path = root / "restore.json"
        synthetic_wave = {"wave": 1}
        synthetic_digest = "a" * 64
        synthetic_intent = {"created_utc": "2026-08-29T12:00:00Z", "x": 1}
        module = os.sys.modules[__name__]
        common_patches = (
            mock.patch.object(module, "load_manifest", return_value=({}, synthetic_digest)),
            mock.patch.object(
                module, "load_all_waves", return_value=[(synthetic_wave, "b" * 64)]
            ),
            mock.patch.object(module, "wave_intent_path", return_value=intent_path),
            mock.patch.object(module, "wave_receipt_path", return_value=receipt_path),
            mock.patch.object(module, "RESTORE_RECEIPT", restore_path),
            mock.patch.object(
                module, "_expected_submit_intent", return_value={"created_utc": None, "x": 1}
            ),
            mock.patch.object(
                module, "load_wave_submit_intent", return_value=synthetic_intent
            ),
            mock.patch.object(
                module,
                "verify_wave_ready",
                side_effect=AssertionError("clean precondition ran before reconciliation"),
            ),
        )
        for patcher in common_patches:
            patcher.start()
        try:
            with mock.patch.object(
                module, "find_jobs_by_identity", return_value={"77"}
            ), mock.patch.object(module, "_seal_submit_receipt") as seal, mock.patch(
                "builtins.print"
            ):
                submit_recovery()
                assert seal.call_count == 1
            with mock.patch.object(
                module, "find_jobs_by_identity", return_value=set()
            ), mock.patch.object(module, "_seal_submit_receipt") as seal:
                try:
                    submit_recovery()
                except RecoveryError as err:
                    assert "was not resubmitted" in str(err)
                else:
                    raise AssertionError("zero-match intent was automatically resubmitted")
                assert seal.call_count == 0
        finally:
            for patcher in reversed(common_patches):
                patcher.stop()
    fake_identity = {
        "run_sha256": "1" * 64,
        "run_size": 1,
        "static_properties_sha256": "2" * 64,
        "static_properties_size": 1,
        "domain": {
            "link_target": "domain",
            "resolved_path": "/tmp/domain.pddl",
            "benchmark_relative_path": "d/domain.pddl",
            "size": 1,
            "sha256": "3" * 64,
        },
        "problem": {
            "link_target": "problem",
            "resolved_path": "/tmp/problem.pddl",
            "benchmark_relative_path": "d/problem.pddl",
            "size": 1,
            "sha256": "4" * 64,
        },
    }
    fake_manifest = {
        "recovery_cells": [
            {"run_id": 1, "execution_inputs": fake_identity},
            {"run_id": 25, "execution_inputs": fake_identity},
        ],
        "runtime": {
            "python_executable": str(VENV_PYTHON),
            "python_link_target": "/usr/bin/python3.9",
            "python_resolved_path": "/usr/bin/python3.9",
            "python_sha256": "5" * 64,
            "lab_runtime_files": [["/tmp/lab.py", "9" * 64, 1]],
            "required_distribution_files": [["/tmp/package.py", "a" * 64, 1]],
            "execution_environment": {
                "path": "/usr/bin:/bin",
                "ld_library_path": "/usr/lib64",
                "python_no_user_site": "1",
                "unset_variables": [
                    "LD_PRELOAD",
                    "PYTHONHOME",
                    "PYTHONPATH",
                    "PYTHONSTARTUP",
                    "PYTHONUSERBASE",
                ],
                "validator": {
                    "available": False,
                    "candidate": None,
                    "path": None,
                    "size": None,
                    "sha256": None,
                },
            },
        },
        "materialized_code": {
            "fast_downward_path": "/tmp/fast-downward.py",
            "fast_downward_sha256": "6" * 64,
            "downward_path": "/tmp/downward",
            "downward_sha256": "7" * 64,
            "preprocess_path": "/tmp/preprocess",
            "preprocess_sha256": "8" * 64,
            "execution_files": [["/tmp/source.py", "b" * 64, 1]],
        },
    }
    text = runner_text([1, 25], "a" * 16, 1, fake_manifest)
    assert "#SBATCH --array=1-2%{}".format(E.ARRAY_THROTTLE) in text
    assert text.count('"$PYTHON" run > driver.log') == 1
    assert "#SBATCH --no-requeue" in text
    assert "flock -n 9" in text
    assert 'require_hash "$DOWNWARD"' in text
    assert text.count("attest_inputs") == 3
    assert "PACKAGE_PATHS=" in text and "CODE_PATHS=" in text
    submission_wave = {
        "wave": 1,
        "run_ids": [1, 25],
        "runner": {
            "nonce": "a" * 16,
            "job_name": "pdbprof-w01-aaaaaaaaaaaa",
            "array_spec": "1-2%{}".format(E.ARRAY_THROTTLE),
            "partition": "cpu",
            "qos": "normal",
            "wall_time": RECOVERY_WALL_TIME,
            "memory_per_cpu": RECOVERY_MEMORY,
            "cpus_per_task": 1,
            "account": E.ACCOUNT,
        },
    }
    assert "--export=PATH" in _submission_argv(submission_wave, "c" * 64)
    assert str(_safe_run_root(1)) in text and str(_safe_run_root(25)) in text
    subprocess.run(
        ["bash", "-n"], input=text, text=True, check=True, capture_output=True
    )
    batch_wave = {
        **submission_wave,
        "runner": {
            **submission_wave["runner"],
            "sha256": sha256_bytes(text.encode("ascii")),
        },
    }
    batch = batch_runner_text(
        batch_wave,
        job_name="pdbprof-b01-aaaaaaaaaaaa",
        array_tasks=1,
        cells_per_array_task=2,
        srun_path="/usr/bin/srun",
        srun_sha256="c" * 64,
        env_path="/usr/bin/env",
        env_sha256="d" * 64,
    )
    assert "#SBATCH --array=1-1%2" in batch
    assert "#SBATCH --cpus-per-task=2" in batch
    assert "ARRAY_TASKS=1" in batch
    assert '"$SRUN" --exclusive --exact --nodes=1 --ntasks=1' in batch
    assert '"$ENV" "SLURM_ARRAY_TASK_ID=$LEGACY_TASK"' in batch
    assert batch.count("attest_batch_inputs") == 3
    assert _parse_slurm_max_array_size("MaxArraySize = 1001\n") == 1001
    assert _array_expression_tasks("[1-5%2]", expected_throttle=2) == set(
        range(1, 6)
    )
    subprocess.run(
        ["bash", "-n"], input=batch, text=True, check=True, capture_output=True
    )
    index_probe = """set -euo pipefail
fail() {{ exit 2; }}
LEGACY_TASKS=1132
CELLS_PER_ARRAY_TASK=2
{}
printf '%s:%s\\n' "$FIRST" "$LAST"
""".format(batch_array_index_setup_text(566))
    for task_id, expected in (("1", "1:2\n"), ("566", "1131:1132\n")):
        result = subprocess.run(
            ["bash"],
            input=index_probe,
            text=True,
            check=False,
            capture_output=True,
            env={**os.environ, "SLURM_ARRAY_TASK_ID": task_id},
        )
        assert result.returncode == 0 and result.stdout == expected
    for task_id in (
        "0",
        "567",
        "9223372036854775809",
        "18446744073709551618",
    ):
        result = subprocess.run(
            ["bash"],
            input=index_probe,
            text=True,
            check=False,
            capture_output=True,
            env={**os.environ, "SLURM_ARRAY_TASK_ID": task_id},
        )
        assert result.returncode == 2 and result.stdout == ""
    print("pdb-profile cell-exact recovery self-test: PASS")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--self-test", action="store_true")
    actions.add_argument("--freeze", action="store_true")
    actions.add_argument("--archive", action="store_true")
    actions.add_argument("--restore", action="store_true")
    actions.add_argument("--amend-array-limit", action="store_true")
    actions.add_argument("--submit", action="store_true")
    actions.add_argument("--retry", action="store_true")
    actions.add_argument("--verify", action="store_true")
    parser.add_argument("--job-id")
    args = parser.parse_args(argv)
    if args.freeze != bool(args.job_id):
        parser.error("only --freeze requires --job-id")
    return args


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.self_test:
        self_test()
    elif args.freeze:
        freeze(args.job_id)
    elif args.archive:
        archive_prefixes()
    elif args.restore:
        restore_prefixes()
    elif args.amend_array_limit:
        amend_array_limit()
    elif args.submit:
        submit_recovery()
    elif args.retry:
        prepare_retry_wave()
    else:
        verify_recovery()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RecoveryError, JJ.JjCacheError, E.LaunchError, P.ProtocolError) as err:
        print("error: {}".format(err), file=os.sys.stderr)
        raise SystemExit(2)
