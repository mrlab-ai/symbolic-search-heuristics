#!/usr/bin/env python3
"""Prepare, launch, monitor, and seal the fresh full-census source audit."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources_v12 as Source
import pdb_terminal_incidence_confirmation_publication_v12 as Publication


class LaunchAuditError(RuntimeError):
    pass


SCHEMA = Source.SCHEMA
LAUNCH_SCHEMA = SCHEMA + "/launch/v1"
EXECUTION_SCHEMA = SCHEMA + "/execution/v1"
SBATCH_RESULT_SCHEMA = LAUNCH_SCHEMA + "/sbatch-result/v1"
POLL_SCHEMA = EXECUTION_SCHEMA + "/poll/v1"
PREFLIGHT_SCHEMA = SCHEMA + "/preflight/v1"

ARTIFACT_DIR = Source.ARTIFACT_DIR
INTENT = ARTIFACT_DIR / "source-audit-launch-intent-v12.json"
SBATCH_STDOUT = ARTIFACT_DIR / "source-audit-sbatch-stdout-v12.bin"
SBATCH_STDERR = ARTIFACT_DIR / "source-audit-sbatch-stderr-v12.bin"
SBATCH_RESULT = ARTIFACT_DIR / "source-audit-sbatch-result-v12.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-launch-receipt-v12.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v12.json"
FULL_POLL_DIR = ARTIFACT_DIR / "source-audit-scheduler-polls-v12"
FULL_TERMINAL_RECEIPT = (
    ARTIFACT_DIR / "source-audit-scheduler-terminal-receipt-v12.json"
)
PREFLIGHT_ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" /
    "pdb-terminal-incidence-confirmation-v12-preflight"
)
PUBLISHER_CANARY_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-publisher-canary-v12"
)
PUBLISHER_CANARY_RECEIPT = (
    PREFLIGHT_ARTIFACT_DIR /
    "controller-publisher-canary-receipt-v12.json"
)
COMPUTE_CANARY_OUTPUT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-source-audit-v12-canary"
)
COMPUTE_CANARY_TMP_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-source-audit-v12-canary-tmp"
)
COMPUTE_CANARY_LOG_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-source-audit-v12-canary-logs"
)
COMPUTE_CANARY_TEMPLATE = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_compute_canary_v12.slurm"
)
COMPUTE_CANARY_INTENT = (
    PREFLIGHT_ARTIFACT_DIR / "compute-canary-launch-intent-v12.json"
)
COMPUTE_CANARY_STDOUT = (
    PREFLIGHT_ARTIFACT_DIR / "compute-canary-sbatch-stdout-v12.bin"
)
COMPUTE_CANARY_STDERR = (
    PREFLIGHT_ARTIFACT_DIR / "compute-canary-sbatch-stderr-v12.bin"
)
COMPUTE_CANARY_RESULT = (
    PREFLIGHT_ARTIFACT_DIR / "compute-canary-sbatch-result-v12.json"
)
COMPUTE_CANARY_RECEIPT = (
    PREFLIGHT_ARTIFACT_DIR / "compute-canary-launch-receipt-v12.json"
)
COMPUTE_CANARY_POLL_DIR = (
    PREFLIGHT_ARTIFACT_DIR / "compute-canary-scheduler-polls-v12"
)
COMPUTE_CANARY_TERMINAL_RECEIPT = (
    PREFLIGHT_ARTIFACT_DIR /
    "compute-canary-scheduler-terminal-receipt-v12.json"
)
COMPUTE_CANARY_SEAL_PLAN = (
    PREFLIGHT_ARTIFACT_DIR / "compute-canary-seal-plan-v12.json"
)
COMPUTE_CANARY_ATTESTATION = (
    PREFLIGHT_ARTIFACT_DIR / "compute-canary-attestation-v12.json"
)
PREFLIGHT_AUTHORIZATION = (
    PREFLIGHT_ARTIFACT_DIR / "preflight-authorization-v12.json"
)
SLURM_TEMPLATE = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v12.slurm"
)
CODE_MANIFEST = Source.CODE_MANIFEST
OUTPUT_DIR = Source.DEFAULT_OUTPUT
SOURCE_INVENTORY = Source.DEFAULT_INVENTORY
TMP_ROOT = Source.TMP_ROOT
LOG_ROOT = Source.LOG_ROOT

ARRAY_TASKS = 820
CANDIDATE_COUNT = 1640
ACCOUNT = "naiss2025-5-561-cpu"
PARTITION = "fat"
QOS = "normal"
NODES = 1
NTASKS = 1
CPUS_PER_TASK = 1
MEMORY = "26G"
TIME_LIMIT = "01:10:00"
ARRAY = "0-819"
CONTROLLED_PATH = "/usr/bin:/bin"

PYTHON_COMMAND = Path(
    "/home/jendrik/.local/share/uv/python/"
    "cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
)
PYTHON_EXECUTABLE_SHA256 = (
    "021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
)
SBATCH_COMMAND = Path("/usr/bin/sbatch")
SBATCH_COMMAND_SHA256 = (
    "efbb8e172acc7ed768430740d04e19cc07a3ac4701b005d1a997c08424bde741"
)
SACCT_COMMAND = Path("/usr/bin/sacct")
SACCT_COMMAND_SHA256 = (
    "58f3976b19baa2bc26772a92ab224dd0c1bf0ab3d9b675d85aa3e4636c836315"
)
STAT_COMMAND = Path("/usr/bin/stat")
STAT_COMMAND_SHA256 = (
    "f7ef3b1376596ce952779ea53a91ec97ce8b57389a3ffde75a499564b1c8f25f"
)
JJ_COMMAND = Path("/home/jendrik/bin/jj")
JJ_COMMAND_SHA256 = (
    "d1d69a0f87df266eebf0d2592dd019eb288c300b15fd019afe26cb1ed11ba152"
)

SUBMISSION_ENVIRONMENT = {
    "LANG": "C", "LC_ALL": "C", "PATH": CONTROLLED_PATH,
}
JOB_NAME_PREFIX = "pdb-source-v12"
COMMENT_PREFIX = "pdb-source-v12"
CANARY_JOB_NAME_PREFIX = "pdb-source-v12-canary"
CANARY_COMMENT_PREFIX = "pdb-source-v12-canary"

MANIFEST_PLACEHOLDER = b"__V12_CODE_MANIFEST_SHA256__"
INVENTORY_PLACEHOLDER = b"__V12_SOURCE_INVENTORY_SHA256__"
COMMIT_PLACEHOLDER = b"__V12_REPOSITORY_COMMIT_ID__"
MIN_POLL_INTERVAL_SECONDS = 3600
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
TOKEN_RE = re.compile(r"^[0-9a-f]{24}$")
EXIT_CODE_RE = re.compile(r"^[0-9]+:[0-9]+$")
JOB_ID_RE = re.compile(r"^([0-9]+)(?:;[A-Za-z0-9_.-]+)?\n?$")

ACTIVE_STATES = frozenset({
    "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
    "RESIZING", "SUSPENDED", "STAGE_OUT",
})
TERMINAL_STATES = frozenset({
    "BOOT_FAIL", "CANCELLED", "COMPLETED", "DEADLINE", "FAILED",
    "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "REVOKED",
    "SPECIAL_EXIT", "TIMEOUT",
})

CAPTURE_PROTOCOL = (
    "pre-intent-o-excl-nofollow-sealed-0400-retained-fd-v1"
)
ZERO_PRIOR_PAYLOAD = {
    "prior_runtime_payloads_read": 0,
    "prior_runtime_payload_bytes_read": 0,
    "prior_runtime_payloads_reused": 0,
    "selective_recovery_authorized": False,
    "whole_campaign_fresh": True,
}


def _canonical_json(value) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=True, allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise LaunchAuditError("value is not canonical finite JSON") from err


def _digest(value) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _relative(path: Path) -> str:
    try:
        return Path(path).relative_to(REPO).as_posix()
    except ValueError as err:
        raise LaunchAuditError("bound path escapes the repository") from err


def _require_safe_parent(path: Path) -> None:
    path = Path(path)
    _relative(path)
    current = REPO
    for component in path.relative_to(REPO).parts[:-1]:
        current = current / component
        try:
            info = current.lstat()
        except OSError as err:
            raise LaunchAuditError(
                "publication parent does not exist: {}".format(current)
            ) from err
        if current.is_symlink() or not stat.S_ISDIR(info.st_mode):
            raise LaunchAuditError("publication parent is not a real directory")


def _regular_bytes(path: Path, label: str) -> bytes:
    path = Path(path)
    _require_safe_parent(path)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC
    try:
        descriptor = os.open(path, flags)
    except OSError as err:
        raise LaunchAuditError("cannot open {}".format(label)) from err
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise LaunchAuditError("{} is not a singly linked regular file".format(label))
        blocks = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            blocks.append(block)
        after = os.fstat(descriptor)
        try:
            live = path.lstat()
        except OSError as err:
            raise LaunchAuditError("{} vanished while read".format(label)) from err
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_size, value.st_mtime_ns,
        )
        if identity(before) != identity(after) or identity(after) != identity(live):
            raise LaunchAuditError("{} changed while read".format(label))
        raw = b"".join(blocks)
        if len(raw) != after.st_size:
            raise LaunchAuditError("{} size changed while read".format(label))
        return raw
    except LaunchAuditError:
        raise
    except OSError as err:
        raise LaunchAuditError("cannot read {}".format(label)) from err
    finally:
        os.close(descriptor)


def _exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    if type(raw) is not bytes:
        raise LaunchAuditError("{} publication is not bytes".format(label))
    path = Path(path)
    _require_safe_parent(path)
    flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC |
        getattr(os, "O_NOFOLLOW", 0)
    )
    directory_fd = None
    try:
        directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
        directory_flags |= getattr(os, "O_NOFOLLOW", 0)
        directory_fd = os.open(path.parent, directory_flags)
        descriptor = os.open(path, flags, 0o400)
    except OSError as err:
        raise LaunchAuditError("refusing to overwrite {}".format(label)) from err
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise LaunchAuditError("cannot publish {}".format(label))
            view = view[written:]
        os.fsync(descriptor)
        os.fchmod(descriptor, 0o400)
        os.fsync(directory_fd)
    except LaunchAuditError:
        raise
    except OSError as err:
        raise LaunchAuditError("cannot publish {}".format(label)) from err
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
        if directory_fd is not None:
            os.close(directory_fd)
    if _regular_bytes(path, label) != raw:
        raise LaunchAuditError("{} publication changed".format(label))
    return hashlib.sha256(raw).hexdigest()


def _exclusive_json(path: Path, value, label: str) -> str:
    return _exclusive_bytes(path, _canonical_json(value), label)


def _load_json(path: Path, label: str) -> tuple[bytes, dict]:
    raw = _regular_bytes(path, label)
    try:
        value = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise LaunchAuditError("{} is not canonical JSON".format(label)) from err
    if type(value) is not dict or raw != _canonical_json(value):
        raise LaunchAuditError("{} is not canonical JSON".format(label))
    return raw, value


def _directory_identity(path: Path, label: str) -> dict:
    path = Path(path)
    _require_safe_parent(path)
    try:
        info = path.lstat()
    except OSError as err:
        raise LaunchAuditError("cannot inspect {}".format(label)) from err
    if (
        path.is_symlink() or not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.getuid()
    ):
        raise LaunchAuditError("{} is not a private owned directory".format(label))
    return {
        "path": str(path), "canonical_path": str(path),
        "device": info.st_dev, "inode": info.st_ino,
        "mode": "0700", "uid": info.st_uid, "gid": info.st_gid,
    }


def _create_private_directory(path: Path, label: str) -> dict:
    path = Path(path)
    _require_safe_parent(path)
    if os.path.lexists(path):
        raise LaunchAuditError("refusing to reuse {}".format(label))
    try:
        os.mkdir(path, 0o700)
        os.chmod(path, 0o700, follow_symlinks=False)
    except OSError as err:
        raise LaunchAuditError("cannot create {}".format(label)) from err
    return _directory_identity(path, label)


def controller_publication_canary() -> dict:
    """Exercise the production publisher once on the repository filesystem."""
    if any(os.path.lexists(path) for path in (
        PREFLIGHT_ARTIFACT_DIR, PUBLISHER_CANARY_ROOT,
    )):
        raise LaunchAuditError("V12 controller publication canary was attempted")
    filesystem_probe = _lustre_filesystem_probe(REPO)
    _create_private_directory(
        PREFLIGHT_ARTIFACT_DIR, "V12 preflight artifact directory"
    )
    _create_private_directory(
        PUBLISHER_CANARY_ROOT, "V12 publisher-canary root"
    )
    stage = PUBLISHER_CANARY_ROOT / "stage"
    final = PUBLISHER_CANARY_ROOT / "published"
    stage_identity = _create_private_directory(
        stage, "V12 publisher-canary stage"
    )
    payloads = {
        "claim.json": _canonical_json({
            "schema": PREFLIGHT_SCHEMA + "/publisher-canary-claim/v1",
            "final_path": str(final),
        }),
        "payload.bin": b"terminal-incidence-v12-publisher-canary\n",
    }
    expectations = {}
    for name, raw in payloads.items():
        digest = _exclusive_bytes(
            stage / name, raw, "V12 publisher-canary " + name
        )
        expectations[name] = Publication.FileExpectation(
            sha256=digest, mode=0o400
        )
    try:
        published = Publication.publish_immutable_shard(
            stage,
            final,
            expectations,
            {
                "schema": PREFLIGHT_SCHEMA + "/publisher-canary-metadata/v1",
                "actual_workspace_filesystem": True,
            },
        )
    except Publication.PublicationError as err:
        raise LaunchAuditError("V12 controller publication canary failed") from err
    if published.final_directory_identity.device != REPO.stat().st_dev:
        raise LaunchAuditError("V12 publisher canary used another filesystem")
    receipt = {
        "schema": PREFLIGHT_SCHEMA + "/publisher-canary-receipt/v1",
        "campaign": "v12-preflight",
        "controller_source_sha256": hashlib.sha256(
            _regular_bytes(Path(__file__), "V12 controller source")
        ).hexdigest(),
        "publisher_source_sha256": hashlib.sha256(
            _regular_bytes(
                Path(Publication.__file__), "V12 publisher source"
            )
        ).hexdigest(),
        "stage_path": str(stage),
        "stage_identity": stage_identity,
        "final_path": str(final),
        "final_identity": published.final_directory_identity.as_json(),
        "completion_sha256": published.completion_sha256,
        "payload_sha256": {
            name: expectation.sha256
            for name, expectation in sorted(expectations.items())
        },
        "filesystem_probe": filesystem_probe,
        "actual_lustre": (
            filesystem_probe["filesystem_type"] == "lustre"
            and filesystem_probe["filesystem_magic"] == "bd00bd0"
            and published.final_directory_identity.device
            == filesystem_probe["target_device"]
        ),
        "publisher_canary_passed": True,
        "renameat2_used": False,
    }
    _exclusive_json(
        PUBLISHER_CANARY_RECEIPT,
        receipt,
        "V12 controller publisher-canary receipt",
    )
    print(json.dumps(receipt, sort_keys=True, indent=2))
    return receipt


def _executable_identity(path: Path, expected_sha256: str, label: str) -> dict:
    path = Path(path)
    try:
        info = path.lstat()
        resolved = path.resolve(strict=True)
        resolved_info = resolved.lstat()
    except OSError as err:
        raise LaunchAuditError("cannot inspect pinned {}".format(label)) from err
    try:
        digest = hashlib.sha256(resolved.read_bytes()).hexdigest()
    except OSError as err:
        raise LaunchAuditError("cannot hash pinned {}".format(label)) from err
    if (
        not path.is_absolute() or not stat.S_ISREG(resolved_info.st_mode)
        or not os.access(resolved, os.X_OK) or digest != expected_sha256
        or (not path.is_symlink() and not stat.S_ISREG(info.st_mode))
    ):
        raise LaunchAuditError("pinned {} identity changed".format(label))
    return {"path": str(path), "resolved_path": str(resolved), "sha256": expected_sha256}


def _lustre_filesystem_probe(path: Path) -> dict:
    path = Path(path).resolve(strict=True)
    program = _executable_identity(STAT_COMMAND, STAT_COMMAND_SHA256, "stat")
    command = [
        str(STAT_COMMAND), "--file-system", "--format=%T|%t", str(path),
    ]
    try:
        completed = subprocess.run(
            command, cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
    except OSError as err:
        raise LaunchAuditError("cannot probe V12 filesystem type") from err
    if (
        completed.returncode != 0
        or completed.stdout != b"lustre|bd00bd0\n"
        or completed.stderr != b""
    ):
        raise LaunchAuditError("V12 workspace is not the expected Lustre filesystem")
    return {
        "program": program,
        "command": command,
        "target": str(path),
        "target_device": path.stat().st_dev,
        "filesystem_type": "lustre",
        "filesystem_magic": "bd00bd0",
        "stdout": "lustre|bd00bd0\n",
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "returncode": 0,
    }


def _capture_identity(path: Path, descriptor: int, *, initial: bool) -> dict:
    try:
        info = os.fstat(descriptor)
        live = Path(path).lstat()
    except OSError as err:
        raise LaunchAuditError("sbatch capture vanished") from err
    if (
        not stat.S_ISREG(info.st_mode) or not stat.S_ISREG(live.st_mode)
        or (info.st_dev, info.st_ino) != (live.st_dev, live.st_ino)
        or info.st_nlink != 1 or live.st_nlink != 1
        or stat.S_IMODE(info.st_mode) != 0o400
        or info.st_uid != os.getuid()
    ):
        raise LaunchAuditError("sbatch capture identity changed")
    result = {
        "path": str(path), "canonical_path": str(path),
        "device": info.st_dev, "inode": info.st_ino,
        "mode": "0400", "uid": info.st_uid, "gid": info.st_gid,
        "link_count": info.st_nlink,
    }
    result["bytes_at_intent" if initial else "bytes"] = info.st_size
    return result


class _CapturePair:
    def __init__(
        self,
        stdout_path: Path | None = None,
        stderr_path: Path | None = None,
        label: str = "sbatch",
    ) -> None:
        self._paths = {
            "stdout": SBATCH_STDOUT if stdout_path is None else stdout_path,
            "stderr": SBATCH_STDERR if stderr_path is None else stderr_path,
        }
        self._label = label
        self._descriptors: dict[str, int] = {}
        self.initial_identities: dict[str, dict] = {}

    def __enter__(self):
        flags = (
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC |
            getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            for stream, path in self._paths.items():
                descriptor = os.open(path, flags, 0o400)
                os.fchmod(descriptor, 0o400)
                self._descriptors[stream] = descriptor
                identity = _capture_identity(path, descriptor, initial=True)
                if identity["bytes_at_intent"] != 0:
                    raise LaunchAuditError("sbatch capture was not empty")
                self.initial_identities[stream] = identity
        except OSError as err:
            self.close()
            raise LaunchAuditError(
                "cannot create V12 {} captures".format(self._label)
            ) from err
        except Exception:
            self.close()
            raise
        identities = [
            (value["device"], value["inode"])
            for value in self.initial_identities.values()
        ]
        if len(set(identities)) != 2:
            self.close()
            raise LaunchAuditError("sbatch captures alias")
        return self

    @property
    def stdout_fd(self) -> int:
        return self._descriptors["stdout"]

    @property
    def stderr_fd(self) -> int:
        return self._descriptors["stderr"]

    def verify_initial(self) -> None:
        for stream, path in self._paths.items():
            if _capture_identity(
                path, self._descriptors[stream], initial=True,
            ) != self.initial_identities[stream]:
                raise LaunchAuditError("sbatch capture changed before submission")

    def finalize(self) -> tuple[dict[str, dict], dict[str, bytes]]:
        records = {}
        payloads = {}
        for stream, path in self._paths.items():
            descriptor = self._descriptors[stream]
            os.fsync(descriptor)
            final = _capture_identity(path, descriptor, initial=False)
            os.lseek(descriptor, 0, os.SEEK_SET)
            blocks = []
            while True:
                block = os.read(descriptor, 1024 * 1024)
                if not block:
                    break
                blocks.append(block)
            raw = b"".join(blocks)
            if len(raw) != final["bytes"]:
                raise LaunchAuditError("sbatch capture size changed")
            payloads[stream] = raw
            records[stream] = {
                "path": str(path), "bytes": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "initial_identity": self.initial_identities[stream],
                "final_identity": final,
            }
        return records, payloads

    def close(self) -> None:
        for descriptor in self._descriptors.values():
            try:
                os.close(descriptor)
            except OSError:
                pass
        self._descriptors.clear()

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()


def _resource_profile() -> dict:
    return {
        "account": ACCOUNT, "partition": PARTITION, "qos": QOS,
        "nodes": NODES, "ntasks": NTASKS,
        "cpus_per_task": CPUS_PER_TASK, "mem": MEMORY,
        "time": TIME_LIMIT, "array": ARRAY,
        "array_throttle": None, "nice": 0,
        "requeue": False, "export": "NONE",
    }


def _array_mapping() -> dict:
    pairs = [[2 * shard, 2 * shard + 1] for shard in range(ARRAY_TASKS)]
    return {
        "logical_shards": ARRAY_TASKS,
        "candidate_count": CANDIDATE_COUNT,
        "rule": "array element s owns candidates 2s and 2s+1",
        "candidate_index_first": 0,
        "candidate_index_last": CANDIDATE_COUNT - 1,
        "candidate_pairs_sha256": _digest(pairs),
        "independent_of_prior_scheduler_rows": True,
    }


def _manifest_paths() -> tuple[str, ...]:
    value = Source.CODE_MANIFEST_FILES
    if (
        type(value) is not tuple or not value
        or tuple(sorted(set(value))) != value
    ):
        raise LaunchAuditError("source code-manifest path set is not canonical")
    required = {
        _relative(Path(__file__)), _relative(SLURM_TEMPLATE),
        "experiments/audit_pdb_terminal_incidence_confirmation_sources_v12.py",
    }
    if not required <= set(value):
        raise LaunchAuditError("source code-manifest closure is incomplete")
    for relative in value:
        if not isinstance(relative, str):
            raise LaunchAuditError("source code-manifest path is invalid")
        candidate = Path(relative)
        if (
            not relative or candidate.is_absolute() or ".." in candidate.parts
            or "\n" in relative or "\r" in relative
            or (REPO / candidate) == CODE_MANIFEST
        ):
            raise LaunchAuditError("source code-manifest path is invalid")
    return value


def _manifest_bytes() -> bytes:
    lines = []
    for relative in _manifest_paths():
        raw = _regular_bytes(REPO / relative, "manifest source " + relative)
        lines.append(
            "{}  {}\n".format(hashlib.sha256(raw).hexdigest(), relative)
        )
    return "".join(lines).encode("ascii")


def _load_code_manifest() -> tuple[str, list[dict]]:
    raw = _regular_bytes(CODE_MANIFEST, "V12 code manifest")
    expected = _manifest_bytes()
    if raw != expected:
        raise LaunchAuditError("V12 code manifest or bound source bytes changed")
    records = []
    for line, relative in zip(raw.decode("ascii").splitlines(), _manifest_paths()):
        digest, recorded = line.split("  ", 1)
        if recorded != relative or SHA256_RE.fullmatch(digest) is None:
            raise LaunchAuditError("V12 code manifest record changed")
        records.append({"path": relative, "sha256": digest})
    return hashlib.sha256(raw).hexdigest(), records


def prepare_manifest() -> None:
    if any(os.path.lexists(path) for path in (
        CODE_MANIFEST, ARTIFACT_DIR, OUTPUT_DIR, TMP_ROOT, LOG_ROOT,
    )):
        raise LaunchAuditError("V12 prepare-manifest namespace is not empty")
    raw = _manifest_bytes()
    digest = _exclusive_bytes(CODE_MANIFEST, raw, "V12 code manifest")
    print(json.dumps({
        "code_manifest": str(CODE_MANIFEST),
        "code_manifest_sha256": digest,
        "files": len(_manifest_paths()),
    }, sort_keys=True, indent=2))


def _repository_commit() -> str:
    _executable_identity(JJ_COMMAND, JJ_COMMAND_SHA256, "jj")
    scoped = tuple(sorted({*_manifest_paths(), _relative(CODE_MANIFEST)}))
    commands = (
        [str(JJ_COMMAND), "--no-pager", "diff", "--summary", "-r", "@", "--", *scoped],
        [str(JJ_COMMAND), "--no-pager", "file", "list", "-r", "@-", "--", *scoped],
        [str(JJ_COMMAND), "--no-pager", "log", "-r", "@-", "--no-graph", "-T", 'commit_id ++ "\\n"'],
    )
    try:
        changed = subprocess.check_output(
            commands[0], cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), text=True,
        )
        tracked = subprocess.check_output(
            commands[1], cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), text=True,
        ).splitlines()
        commit_id = subprocess.check_output(
            commands[2], cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot attest the committed V12 source closure") from err
    if (
        changed or tracked != list(scoped)
        or COMMIT_RE.fullmatch(commit_id or "") is None
    ):
        raise LaunchAuditError("V12 requires every bound file committed at @-")
    _load_code_manifest()
    _executable_identity(JJ_COMMAND, JJ_COMMAND_SHA256, "jj")
    return commit_id


def _load_preflight_binding(
    repository_commit_id: str, code_manifest_sha256: str,
) -> dict:
    """Consume only the independently committed preflight authorization."""
    try:
        import pdb_terminal_incidence_confirmation_source_consumer_v12 as Consumer
        from pdb_terminal_incidence_v12_snapshot_reader import (
            read_committed_snapshot,
        )
        paths = Consumer.preflight_paths_for(
            artifact_dir=PREFLIGHT_ARTIFACT_DIR,
            code_manifest=CODE_MANIFEST,
        )
        authorized = Consumer.load_authorized_preflight(
            paths,
            snapshot_reader=read_committed_snapshot,
            seal_revision=repository_commit_id,
        )
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as err:
        raise LaunchAuditError(
            "committed independent V12 preflight is unavailable"
        ) from err
    binding = {
        "seal_repository_commit_id": getattr(
            authorized, "seal_repository_commit_id", None
        ),
        "authorization_sha256": getattr(
            authorized, "authorization_sha256", None
        ),
        "compute_canary_attestation_sha256": getattr(
            authorized, "compute_canary_attestation_sha256", None
        ),
        "controller_publisher_canary_receipt_sha256": getattr(
            authorized, "controller_publisher_canary_receipt_sha256", None
        ),
        "code_manifest_sha256": getattr(
            authorized, "code_manifest_sha256", None
        ),
        "snapshot_consumed": True,
        # Returning from the independent fail-closed consumer is itself the
        # authorization decision; older data objects deliberately carry only
        # authenticated hashes rather than a redundant mutable Boolean.
        "full_launch_authorized": True,
    }
    if (
        set(binding) != {
            "seal_repository_commit_id", "authorization_sha256",
            "compute_canary_attestation_sha256",
            "controller_publisher_canary_receipt_sha256",
            "code_manifest_sha256", "snapshot_consumed",
            "full_launch_authorized",
        }
        or binding["seal_repository_commit_id"] != repository_commit_id
        or binding["code_manifest_sha256"] != code_manifest_sha256
        or binding["snapshot_consumed"] is not True
        or binding["full_launch_authorized"] is not True
        or any(
            SHA256_RE.fullmatch(binding[key] or "") is None
            for key in (
                "authorization_sha256",
                "compute_canary_attestation_sha256",
                "controller_publisher_canary_receipt_sha256",
            )
        )
    ):
        raise LaunchAuditError(
            "committed independent V12 preflight did not authorize launch"
        )
    return binding


def _build_inventory() -> tuple[bytes, str]:
    value = Source.build_inventory_manifest(Source.DEFAULT_BENCHMARKS)
    records = Source.validate_inventory_manifest(value)
    if type(records) is not list or len(records) != CANDIDATE_COUNT:
        raise LaunchAuditError("V12 inventory does not contain the full census")
    raw = Source.canonical_json(value)
    if type(raw) is not bytes:
        raise LaunchAuditError("V12 inventory encoder is not canonical")
    try:
        decoded = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise LaunchAuditError("V12 inventory encoder is not canonical") from err
    if (
        decoded != value or Source.canonical_json(decoded) != raw
    ):
        raise LaunchAuditError("V12 inventory encoder is not canonical")
    return raw, hashlib.sha256(raw).hexdigest()


def _slurm_template() -> bytes:
    raw = _regular_bytes(SLURM_TEMPLATE, "V12 Slurm template")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise LaunchAuditError("V12 Slurm template is not ASCII") from err
    header = [
        "#!/bin/bash",
        "#SBATCH --account=" + ACCOUNT,
        "#SBATCH --partition=" + PARTITION,
        "#SBATCH --qos=" + QOS,
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --mem=" + MEMORY,
        "#SBATCH --time=" + TIME_LIMIT,
        "#SBATCH --array=" + ARRAY,
        "#SBATCH --output={}/slurm-%A_%a.out".format(LOG_ROOT),
        "#SBATCH --error={}/slurm-%A_%a.err".format(LOG_ROOT),
        "#SBATCH --export=NONE",
        "#SBATCH --nice=0",
        "#SBATCH --no-requeue",
    ]
    if (
        lines[:len(header)] != header
        or any(line.startswith("#SBATCH") for line in lines[len(header):])
        or "%" in header[9]
        or raw.count(MANIFEST_PLACEHOLDER) != 1
        or raw.count(INVENTORY_PLACEHOLDER) != 1
        or raw.count(COMMIT_PLACEHOLDER) != 1
        or sum(line.startswith("    --num-shards 820 ") for line in lines) != 1
        or sum(
            line.startswith('    --shard-index "${SLURM_ARRAY_TASK_ID}" ')
            for line in lines
        ) != 1
        or lines.count('    --tmp-root "${tmp_root}"') != 1
    ):
        raise LaunchAuditError("V12 Slurm resource or execution contract changed")
    return raw


def _render_slurm(
    code_manifest_sha256: str,
    source_inventory_sha256: str,
    repository_commit_id: str,
) -> bytes:
    if (
        not isinstance(code_manifest_sha256, str)
        or SHA256_RE.fullmatch(code_manifest_sha256) is None
        or not isinstance(source_inventory_sha256, str)
        or SHA256_RE.fullmatch(source_inventory_sha256) is None
        or not isinstance(repository_commit_id, str)
        or COMMIT_RE.fullmatch(repository_commit_id) is None
    ):
        raise LaunchAuditError("V12 Slurm binding is invalid")
    raw = _slurm_template()
    rendered = raw.replace(
        MANIFEST_PLACEHOLDER, code_manifest_sha256.encode("ascii"),
    ).replace(
        INVENTORY_PLACEHOLDER, source_inventory_sha256.encode("ascii"),
    ).replace(
        COMMIT_PLACEHOLDER, repository_commit_id.encode("ascii"),
    )
    if any(marker in rendered for marker in (
        MANIFEST_PLACEHOLDER, INVENTORY_PLACEHOLDER, COMMIT_PLACEHOLDER,
    )):
        raise LaunchAuditError("V12 Slurm binding remained incomplete")
    return rendered


def _compute_canary_template() -> bytes:
    raw = _regular_bytes(
        COMPUTE_CANARY_TEMPLATE, "V12 compute-canary Slurm template"
    )
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise LaunchAuditError(
            "V12 compute-canary Slurm template is not ASCII"
        ) from err
    expected = [
        "#!/bin/bash",
        "#SBATCH --account=" + ACCOUNT,
        "#SBATCH --partition=" + PARTITION,
        "#SBATCH --qos=" + QOS,
        "#SBATCH --nodes=1",
        "#SBATCH --ntasks=1",
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --mem=" + MEMORY,
        "#SBATCH --time=" + TIME_LIMIT,
        "#SBATCH --array=0-0",
        "#SBATCH --output={}/slurm-%A_%a.out".format(
            COMPUTE_CANARY_LOG_ROOT
        ),
        "#SBATCH --error={}/slurm-%A_%a.err".format(
            COMPUTE_CANARY_LOG_ROOT
        ),
        "#SBATCH --export=NONE",
        "#SBATCH --nice=0",
        "#SBATCH --no-requeue",
    ]
    if (
        lines[:len(expected)] != expected
        or any(line.startswith("#SBATCH") for line in lines[len(expected):])
        or raw.count(MANIFEST_PLACEHOLDER) != 1
        or raw.count(COMMIT_PLACEHOLDER) != 1
        or INVENTORY_PLACEHOLDER in raw
        or "%" in expected[9]
        or not any("compute-canary" in line for line in lines)
    ):
        raise LaunchAuditError("V12 compute-canary Slurm contract changed")
    return raw


def _render_compute_canary_slurm(
    code_manifest_sha256: str, repository_commit_id: str,
) -> bytes:
    if (
        SHA256_RE.fullmatch(code_manifest_sha256 or "") is None
        or COMMIT_RE.fullmatch(repository_commit_id or "") is None
    ):
        raise LaunchAuditError("V12 compute-canary binding is invalid")
    rendered = _compute_canary_template().replace(
        MANIFEST_PLACEHOLDER, code_manifest_sha256.encode("ascii")
    ).replace(COMMIT_PLACEHOLDER, repository_commit_id.encode("ascii"))
    if MANIFEST_PLACEHOLDER in rendered or COMMIT_PLACEHOLDER in rendered:
        raise LaunchAuditError("V12 compute-canary binding remained incomplete")
    return rendered


def _submission_identity(token: str) -> tuple[str, str]:
    if not isinstance(token, str) or TOKEN_RE.fullmatch(token) is None:
        raise LaunchAuditError("V12 submission token is invalid")
    return (
        "{}-{}".format(JOB_NAME_PREFIX, token),
        "{}-{}".format(COMMENT_PREFIX, token),
    )


def _submit_command(token: str) -> list[str]:
    job_name, comment = _submission_identity(token)
    return [
        str(SBATCH_COMMAND), "--parsable", "--export=NONE",
        "--job-name=" + job_name, "--comment=" + comment,
        "--account=" + ACCOUNT, "--partition=" + PARTITION,
        "--qos=" + QOS, "--nodes=1", "--ntasks=1",
        "--cpus-per-task=1", "--mem=" + MEMORY,
        "--time=" + TIME_LIMIT, "--array=" + ARRAY,
        "--nice=0", "--no-requeue", "--chdir=" + str(REPO),
        "--output={}/slurm-%A_%a.out".format(LOG_ROOT),
        "--error={}/slurm-%A_%a.err".format(LOG_ROOT),
    ]


def _execution_environment() -> dict:
    return {
        "submission_export": "NONE", "slurm_export": "NONE",
        "path": CONTROLLED_PATH,
        "unset_variables": ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"],
        "python_no_user_site": "1", "python_dont_write_bytecode": "1",
        "python_command": str(PYTHON_COMMAND),
        "python_executable_sha256": PYTHON_EXECUTABLE_SHA256,
        "tmpdir_root": str(TMP_ROOT), "scheduler_log_root": str(LOG_ROOT),
        "tmpdir_template": str(TMP_ROOT / "task-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"),
        "task_tmpdir_mode": "0700",
        "task_tmpdir_cleanup": "exact empty unpublished directory on success only",
        "candidate_address_space_limit_mib": 24576,
        "candidate_cpu_limit_seconds": 1800,
        "candidate_wall_watchdog_seconds": 1950,
    }


def _parse_job_id(raw: bytes) -> str | None:
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    match = JOB_ID_RE.fullmatch(value)
    return match.group(1) if match else None


def _assert_source_contract() -> None:
    expected = {
        "SCRIPT_DIR": SCRIPT_DIR, "REPO": REPO,
        "ARRAY_TASKS": ARRAY_TASKS, "CANDIDATE_COUNT": CANDIDATE_COUNT,
        "DEFAULT_OUTPUT": OUTPUT_DIR, "DEFAULT_INVENTORY": SOURCE_INVENTORY,
        "CODE_MANIFEST": CODE_MANIFEST, "TMP_ROOT": TMP_ROOT,
        "LOG_ROOT": LOG_ROOT, "ARTIFACT_DIR": ARTIFACT_DIR,
    }
    if any(getattr(Source, key, None) != value for key, value in expected.items()):
        raise LaunchAuditError("V12 source/launcher path or cardinality contract changed")


def _assert_namespace_empty() -> None:
    if any(os.path.lexists(path) for path in (
        ARTIFACT_DIR, OUTPUT_DIR, TMP_ROOT, LOG_ROOT,
    )):
        raise LaunchAuditError("V12 one-shot launch namespace is not empty")


def _launch_materials(
    *, repository_commit_id: str, code_manifest_sha256: str,
    code_records: list[dict], inventory_sha256: str, rendered: bytes,
    root_identities: dict, capture_initial_identities: dict,
    preflight_binding: dict,
) -> dict:
    return {
        "campaign": "v12-full-census",
        "repository_commit_id": repository_commit_id,
        "resource_profile": _resource_profile(),
        "array_mapping": _array_mapping(),
        "source_inventory": {
            "path": str(SOURCE_INVENTORY), "sha256": inventory_sha256,
            "candidate_count": CANDIDATE_COUNT,
        },
        "source_inventory_sha256": inventory_sha256,
        "code_manifest": {
            "path": str(CODE_MANIFEST), "sha256": code_manifest_sha256,
            "files": code_records, "files_sha256": _digest(code_records),
        },
        "code_manifest_sha256": code_manifest_sha256,
        "slurm_program": {
            "template_path": str(SLURM_TEMPLATE),
            "template_sha256": hashlib.sha256(_slurm_template()).hexdigest(),
            "rendered_sha256": hashlib.sha256(rendered).hexdigest(),
            "rendered_bytes": len(rendered), "submission_mode": "stdin",
            "path_argument": False,
        },
        "root_identities": root_identities,
        "execution_environment": _execution_environment(),
        "capture_protocol": CAPTURE_PROTOCOL,
        "sbatch_capture_initial_identities": capture_initial_identities,
        "preflight_binding": preflight_binding,
        **ZERO_PRIOR_PAYLOAD,
    }


def _publish_sbatch_result(
    intent_raw: bytes, intent: dict, rendered: bytes,
    records: dict[str, dict], payloads: dict[str, bytes],
    *, completed: subprocess.CompletedProcess | None, error: OSError | None,
    recovered: bool,
) -> tuple[str, dict]:
    if (
        hashlib.sha256(rendered).hexdigest()
        != intent["slurm_program"]["rendered_sha256"]
        or set(records) != {"stdout", "stderr"}
        or set(payloads) != {"stdout", "stderr"}
    ):
        raise LaunchAuditError("V12 sbatch result input changed")
    for stream in ("stdout", "stderr"):
        if (
            records[stream].get("sha256")
            != hashlib.sha256(payloads[stream]).hexdigest()
            or records[stream].get("bytes") != len(payloads[stream])
        ):
            raise LaunchAuditError("V12 sbatch capture record changed")
    if recovered:
        if completed is not None or error is not None:
            raise LaunchAuditError("V12 recovery process observation changed")
        process = {
            "kind": "controller-crash-returncode-unavailable",
            "returncode": None, "os_error_type": None, "os_error_errno": None,
        }
    elif completed is not None and error is None:
        if type(completed.returncode) is not int:
            raise LaunchAuditError("V12 sbatch return code changed")
        process = {
            "kind": "completed-process", "returncode": completed.returncode,
            "os_error_type": None, "os_error_errno": None,
        }
    elif completed is None and isinstance(error, OSError):
        process = {
            "kind": "os-error", "returncode": None,
            "os_error_type": type(error).__name__, "os_error_errno": error.errno,
        }
    else:
        raise LaunchAuditError("V12 sbatch process observation changed")
    parsed = _parse_job_id(payloads["stdout"])
    accepted = (
        process["kind"] == "completed-process"
        and process["returncode"] == 0 and parsed is not None
    )
    result = {
        "schema": SBATCH_RESULT_SCHEMA,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "submit_command_sha256": _digest(intent["submit_command"]),
        "slurm_program_sha256": hashlib.sha256(rendered).hexdigest(),
        "capture_protocol": CAPTURE_PROTOCOL,
        "process_observation": process,
        "stdout": records["stdout"], "stderr": records["stderr"],
        "parsed_job_id": parsed, "accepted_by_launcher": accepted,
        "raw_streams_preserved": True,
    }
    digest = _exclusive_json(SBATCH_RESULT, result, "V12 sbatch result")
    return digest, result


def _capture_records_from_disk(intent: dict) -> tuple[dict[str, dict], dict[str, bytes]]:
    expected = intent.get("sbatch_capture_initial_identities")
    if type(expected) is not dict or set(expected) != {"stdout", "stderr"}:
        raise LaunchAuditError("V12 capture identities changed")
    records = {}
    payloads = {}
    for stream, path in (("stdout", SBATCH_STDOUT), ("stderr", SBATCH_STDERR)):
        raw = _regular_bytes(path, "V12 sbatch " + stream)
        info = path.lstat()
        initial = expected[stream]
        if (
            type(initial) is not dict
            or initial.get("path") != str(path)
            or initial.get("canonical_path") != str(path)
            or initial.get("bytes_at_intent") != 0
            or initial.get("mode") != "0400"
            or (initial.get("device"), initial.get("inode"))
            != (info.st_dev, info.st_ino)
            or initial.get("uid") != info.st_uid
            or initial.get("gid") != info.st_gid
            or initial.get("link_count") != 1 or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o400
        ):
            raise LaunchAuditError("V12 sbatch capture identity changed")
        final = {
            **{key: value for key, value in initial.items() if key != "bytes_at_intent"},
            "bytes": len(raw),
        }
        payloads[stream] = raw
        records[stream] = {
            "path": str(path), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "initial_identity": initial, "final_identity": final,
        }
    return records, payloads


def _load_sbatch_result(intent_raw: bytes, intent: dict) -> tuple[str, dict]:
    raw, result = _load_json(SBATCH_RESULT, "V12 sbatch result")
    records, payloads = _capture_records_from_disk(intent)
    process = result.get("process_observation")
    parsed = _parse_job_id(payloads["stdout"])
    accepted = (
        type(process) is dict
        and process.get("kind") == "completed-process"
        and process.get("returncode") == 0 and parsed is not None
    )
    if (
        set(result) != {
            "schema", "launch_intent_sha256", "submit_command_sha256",
            "slurm_program_sha256", "capture_protocol",
            "process_observation", "stdout", "stderr", "parsed_job_id",
            "accepted_by_launcher", "raw_streams_preserved",
        }
        or result.get("schema") != SBATCH_RESULT_SCHEMA
        or result.get("launch_intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or result.get("submit_command_sha256") != _digest(intent["submit_command"])
        or result.get("slurm_program_sha256")
        != intent["slurm_program"]["rendered_sha256"]
        or result.get("capture_protocol") != CAPTURE_PROTOCOL
        or result.get("stdout") != records["stdout"]
        or result.get("stderr") != records["stderr"]
        or result.get("parsed_job_id") != parsed
        or result.get("accepted_by_launcher") is not accepted
        or result.get("raw_streams_preserved") is not True
        or type(process) is not dict
        or set(process) != {
            "kind", "returncode", "os_error_type", "os_error_errno",
        }
        or not (
            (
                process["kind"] == "completed-process"
                and type(process["returncode"]) is int
                and process["os_error_type"] is None
                and process["os_error_errno"] is None
            ) or (
                process["kind"] == "os-error"
                and process["returncode"] is None
                and isinstance(process["os_error_type"], str)
                and (
                    process["os_error_errno"] is None
                    or type(process["os_error_errno"]) is int
                )
            ) or (
                process["kind"] == "controller-crash-returncode-unavailable"
                and process["returncode"] is None
                and process["os_error_type"] is None
                and process["os_error_errno"] is None
            )
        )
    ):
        raise LaunchAuditError("V12 sbatch result changed")
    return hashlib.sha256(raw).hexdigest(), result


def _validate_root_identities(value: dict) -> None:
    paths = {
        "artifact_dir": ARTIFACT_DIR,
        "log_root": LOG_ROOT,
        "output_dir": OUTPUT_DIR,
        "tmpdir_root": TMP_ROOT,
    }
    if type(value) is not dict or set(value) != set(paths):
        raise LaunchAuditError("V12 launch-root identities changed")
    for name, path in paths.items():
        if value[name] != _directory_identity(path, "V12 " + name):
            raise LaunchAuditError("V12 launch root was replaced")


def _load_intent_only() -> tuple[bytes, dict]:
    raw, intent = _load_json(INTENT, "V12 launch intent")
    token = intent.get("submission_token")
    commit_id = intent.get("repository_commit_id")
    manifest_sha, records = _load_code_manifest()
    inventory_raw = _regular_bytes(SOURCE_INVENTORY, "V12 source inventory")
    inventory_sha = hashlib.sha256(inventory_raw).hexdigest()
    rendered = _render_slurm(manifest_sha, inventory_sha, commit_id)
    slurm = intent.get("slurm_program")
    source_inventory = intent.get("source_inventory")
    code_manifest = intent.get("code_manifest")
    recorded = intent.get("recorded_utc")
    try:
        timestamp = datetime.datetime.fromisoformat(recorded)
    except (TypeError, ValueError) as err:
        raise LaunchAuditError("V12 launch timestamp changed") from err
    if timestamp.tzinfo is None:
        raise LaunchAuditError("V12 launch timestamp lacks a timezone")
    expected_keys = {
        "schema", "campaign", "recorded_utc", "submission_token",
        "repository_commit_id", "resource_profile", "array_mapping",
        "source_inventory", "source_inventory_sha256", "code_manifest",
        "code_manifest_sha256", "slurm_program", "root_identities",
        "execution_environment", "capture_protocol",
        "sbatch_capture_initial_identities", "submit_command",
        "preflight_binding",
        *ZERO_PRIOR_PAYLOAD,
    }
    if (
        set(intent) != expected_keys
        or intent.get("schema") != LAUNCH_SCHEMA + "/intent"
        or intent.get("campaign") != "v12-full-census"
        or TOKEN_RE.fullmatch(token or "") is None
        or COMMIT_RE.fullmatch(commit_id or "") is None
        or intent.get("resource_profile") != _resource_profile()
        or intent.get("array_mapping") != _array_mapping()
        or source_inventory != {
            "path": str(SOURCE_INVENTORY), "sha256": inventory_sha,
            "candidate_count": CANDIDATE_COUNT,
        }
        or intent.get("source_inventory_sha256") != inventory_sha
        or code_manifest != {
            "path": str(CODE_MANIFEST), "sha256": manifest_sha,
            "files": records, "files_sha256": _digest(records),
        }
        or intent.get("code_manifest_sha256") != manifest_sha
        or slurm != {
            "template_path": str(SLURM_TEMPLATE),
            "template_sha256": hashlib.sha256(_slurm_template()).hexdigest(),
            "rendered_sha256": hashlib.sha256(rendered).hexdigest(),
            "rendered_bytes": len(rendered), "submission_mode": "stdin",
            "path_argument": False,
        }
        or intent.get("execution_environment") != _execution_environment()
        or intent.get("capture_protocol") != CAPTURE_PROTOCOL
        or intent.get("submit_command") != _submit_command(token)
        or intent.get("preflight_binding")
        != _load_preflight_binding(commit_id, manifest_sha)
        or any(intent.get(key) != value for key, value in ZERO_PRIOR_PAYLOAD.items())
    ):
        raise LaunchAuditError("V12 launch intent changed")
    _validate_root_identities(intent.get("root_identities"))
    _capture_records_from_disk(intent)
    return raw, intent


def _receipt_value(
    intent_raw: bytes, intent: dict, sbatch_result_sha256: str,
    job_id: str, *, recovered: bool, recovery_evidence: dict | None,
    accepted_utc: str,
) -> dict:
    try:
        accepted = datetime.datetime.fromisoformat(accepted_utc)
    except (TypeError, ValueError) as err:
        raise LaunchAuditError("V12 acceptance timestamp changed") from err
    if accepted.tzinfo is None:
        raise LaunchAuditError("V12 acceptance timestamp lacks timezone")
    try:
        intent_recorded = datetime.datetime.fromisoformat(intent["recorded_utc"])
    except (KeyError, TypeError, ValueError) as err:
        raise LaunchAuditError("V12 launch-intent timestamp changed") from err
    if (
        intent_recorded.tzinfo is None
        or accepted.astimezone(datetime.timezone.utc)
        < intent_recorded.astimezone(datetime.timezone.utc)
    ):
        raise LaunchAuditError("V12 acceptance predates its launch intent")
    return {
        "schema": LAUNCH_SCHEMA, "campaign": "v12-full-census",
        "job_id": job_id, "submission_token": intent["submission_token"],
        "accepted_utc": accepted_utc,
        "repository_commit_id": intent["repository_commit_id"],
        "source_inventory_sha256": intent["source_inventory_sha256"],
        "code_manifest_sha256": intent["code_manifest_sha256"],
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "sbatch_result_sha256": sbatch_result_sha256,
        "resource_profile": _resource_profile(),
        "root_identities": intent["root_identities"],
        "slurm_program": intent["slurm_program"],
        "preflight_authorization": intent["preflight_binding"],
        "launch_recovered": recovered,
        "recovery_evidence": recovery_evidence,
        **ZERO_PRIOR_PAYLOAD,
    }


def _write_launch_receipt(
    intent_raw: bytes, intent: dict, job_id: str, *,
    recovered: bool, recovery_evidence: dict | None,
) -> str:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("Slurm returned an invalid V12 job id")
    result_sha, result = _load_sbatch_result(intent_raw, intent)
    parsed = result["parsed_job_id"]
    if not recovered:
        if (
            result["accepted_by_launcher"] is not True
            or parsed != job_id or recovery_evidence is not None
        ):
            raise LaunchAuditError("V12 sbatch result did not authorize launch")
    elif (
        type(recovery_evidence) is not dict
        or recovery_evidence.get("job_id") != job_id
        or (parsed is not None and parsed != job_id)
    ):
        raise LaunchAuditError("V12 recovery evidence disagrees with launch")
    receipt = _receipt_value(
        intent_raw, intent, result_sha, job_id,
        recovered=recovered, recovery_evidence=recovery_evidence,
        accepted_utc=datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
    )
    return _exclusive_json(LAUNCH_RECEIPT, receipt, "V12 launch receipt")


def _load_launch() -> tuple[str, dict]:
    intent_raw, intent = _load_intent_only()
    result_sha, result = _load_sbatch_result(intent_raw, intent)
    raw, receipt = _load_json(LAUNCH_RECEIPT, "V12 launch receipt")
    job_id = receipt.get("job_id")
    recovered = receipt.get("launch_recovered")
    evidence = receipt.get("recovery_evidence")
    expected = _receipt_value(
        intent_raw, intent, result_sha, job_id,
        recovered=recovered, recovery_evidence=evidence,
        accepted_utc=receipt.get("accepted_utc"),
    ) if isinstance(job_id, str) and type(recovered) is bool else None
    if (
        receipt != expected or not job_id.isdigit()
        or (
            not recovered
            and (result["accepted_by_launcher"] is not True
                 or result["parsed_job_id"] != job_id
                 or evidence is not None)
        )
        or (
            recovered
            and (type(evidence) is not dict
                 or evidence.get("job_id") != job_id
                 or (result["parsed_job_id"] is not None
                     and result["parsed_job_id"] != job_id))
        )
    ):
        raise LaunchAuditError("V12 launch receipt changed")
    return hashlib.sha256(raw).hexdigest(), receipt


def launch() -> None:
    _assert_source_contract()
    _assert_namespace_empty()
    code_manifest_sha, code_records = _load_code_manifest()
    repository_commit_id = _repository_commit()
    preflight_binding = _load_preflight_binding(
        repository_commit_id, code_manifest_sha
    )
    inventory_raw, inventory_sha = _build_inventory()
    rendered = _render_slurm(
        code_manifest_sha, inventory_sha, repository_commit_id,
    )
    output_identity = _create_private_directory(OUTPUT_DIR, "V12 output directory")
    tmp_identity = _create_private_directory(TMP_ROOT, "V12 TMPDIR root")
    log_identity = _create_private_directory(LOG_ROOT, "V12 scheduler-log root")
    artifact_identity = _create_private_directory(ARTIFACT_DIR, "V12 artifact directory")
    _create_private_directory(FULL_POLL_DIR, "V12 scheduler-poll directory")
    _exclusive_bytes(SOURCE_INVENTORY, inventory_raw, "V12 source inventory")
    token = secrets.token_hex(12)
    command = _submit_command(token)
    with _CapturePair() as captures:
        roots = {
            "artifact_dir": artifact_identity,
            "log_root": log_identity,
            "output_dir": output_identity,
            "tmpdir_root": tmp_identity,
        }
        materials = _launch_materials(
            repository_commit_id=repository_commit_id,
            code_manifest_sha256=code_manifest_sha,
            code_records=code_records, inventory_sha256=inventory_sha,
            rendered=rendered, root_identities=roots,
            capture_initial_identities=captures.initial_identities,
            preflight_binding=preflight_binding,
        )
        intent = {
            "schema": LAUNCH_SCHEMA + "/intent", **materials,
            "recorded_utc": datetime.datetime.now(
                datetime.timezone.utc,
            ).isoformat(timespec="seconds"),
            "submission_token": token, "submit_command": command,
        }
        intent_raw = _canonical_json(intent)
        _exclusive_json(INTENT, intent, "V12 launch intent")
        rerendered = _render_slurm(
            code_manifest_sha, inventory_sha, repository_commit_id,
        )
        if rerendered != rendered:
            raise LaunchAuditError("V12 rendered Slurm bytes changed before submission")
        _executable_identity(SBATCH_COMMAND, SBATCH_COMMAND_SHA256, "sbatch")
        captures.verify_initial()
        completed = None
        error = None
        try:
            completed = subprocess.run(
                command, input=rendered,
                stdout=captures.stdout_fd, stderr=captures.stderr_fd,
                cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), check=False,
            )
        except OSError as err:
            error = err
        records, payloads = captures.finalize()
        result_sha, result = _publish_sbatch_result(
            intent_raw, intent, rendered, records, payloads,
            completed=completed, error=error, recovered=False,
        )
        if result["accepted_by_launcher"] is not True:
            raise LaunchAuditError(
                "V12 sbatch was not accepted; raw streams are bound by " + result_sha
            )
        job_id = result["parsed_job_id"]
    receipt_sha = _write_launch_receipt(
        intent_raw, intent, job_id,
        recovered=False, recovery_evidence=None,
    )
    print(json.dumps({
        "job_id": job_id, "launch_receipt_sha256": receipt_sha,
        "array": ARRAY, "array_throttle": None,
    }, sort_keys=True, indent=2))


def _canary_resource_profile() -> dict:
    return {**_resource_profile(), "array": "0-0"}


def _canary_submission_identity(token: str) -> tuple[str, str]:
    if TOKEN_RE.fullmatch(token or "") is None:
        raise LaunchAuditError("V12 canary submission token is invalid")
    return (
        "{}-{}".format(CANARY_JOB_NAME_PREFIX, token),
        "{}-{}".format(CANARY_COMMENT_PREFIX, token),
    )


def _canary_submit_command(token: str) -> list[str]:
    name, comment = _canary_submission_identity(token)
    return [
        str(SBATCH_COMMAND), "--parsable", "--export=NONE",
        "--job-name=" + name, "--comment=" + comment,
        "--account=" + ACCOUNT, "--partition=" + PARTITION,
        "--qos=" + QOS, "--nodes=1", "--ntasks=1",
        "--cpus-per-task=1", "--mem=" + MEMORY,
        "--time=" + TIME_LIMIT, "--array=0-0",
        "--nice=0", "--no-requeue", "--chdir=" + str(REPO),
        "--output={}/slurm-%A_%a.out".format(COMPUTE_CANARY_LOG_ROOT),
        "--error={}/slurm-%A_%a.err".format(COMPUTE_CANARY_LOG_ROOT),
    ]


def _load_controller_canary() -> tuple[str, dict]:
    raw, receipt = _load_json(
        PUBLISHER_CANARY_RECEIPT, "V12 controller publisher-canary receipt"
    )
    if (
        receipt.get("schema")
        != PREFLIGHT_SCHEMA + "/publisher-canary-receipt/v1"
        or receipt.get("campaign") != "v12-preflight"
        or receipt.get("actual_lustre") is not True
        or receipt.get("publisher_canary_passed") is not True
        or receipt.get("renameat2_used") is not False
        or not os.path.lexists(PUBLISHER_CANARY_ROOT / "published")
    ):
        raise LaunchAuditError("V12 controller publisher canary is not valid")
    return hashlib.sha256(raw).hexdigest(), receipt


def launch_compute_canary() -> dict:
    """Submit exactly one independent fat-partition compute-canary row."""
    controller_sha, _controller = _load_controller_canary()
    if any(os.path.lexists(path) for path in (
        COMPUTE_CANARY_OUTPUT, COMPUTE_CANARY_TMP_ROOT,
        COMPUTE_CANARY_LOG_ROOT, COMPUTE_CANARY_INTENT,
        COMPUTE_CANARY_STDOUT, COMPUTE_CANARY_STDERR,
        COMPUTE_CANARY_RESULT, COMPUTE_CANARY_RECEIPT,
        COMPUTE_CANARY_POLL_DIR, COMPUTE_CANARY_TERMINAL_RECEIPT,
        COMPUTE_CANARY_SEAL_PLAN, COMPUTE_CANARY_ATTESTATION,
        PREFLIGHT_AUTHORIZATION,
    )):
        raise LaunchAuditError("V12 compute-canary namespace is not empty")
    code_sha, _records = _load_code_manifest()
    revision = _repository_commit()
    rendered = _render_compute_canary_slurm(code_sha, revision)
    roots = {
        "artifact_dir": _directory_identity(
            PREFLIGHT_ARTIFACT_DIR, "V12 preflight artifact directory"
        ),
        "output_dir": _create_private_directory(
            COMPUTE_CANARY_OUTPUT, "V12 compute-canary output"
        ),
        "tmpdir_root": _create_private_directory(
            COMPUTE_CANARY_TMP_ROOT, "V12 compute-canary TMP root"
        ),
        "log_root": _create_private_directory(
            COMPUTE_CANARY_LOG_ROOT, "V12 compute-canary log root"
        ),
    }
    _create_private_directory(
        COMPUTE_CANARY_POLL_DIR, "V12 compute-canary poll directory"
    )
    token = secrets.token_hex(12)
    command = _canary_submit_command(token)
    with _CapturePair(
        COMPUTE_CANARY_STDOUT, COMPUTE_CANARY_STDERR,
        "compute-canary sbatch",
    ) as captures:
        intent = {
            "schema": PREFLIGHT_SCHEMA + "/compute-canary-launch-intent/v1",
            "campaign": Source.COMPUTE_CANARY_CAMPAIGN,
            "recorded_utc": datetime.datetime.now(
                datetime.timezone.utc
            ).isoformat(timespec="seconds"),
            "submission_token": token,
            "repository_commit_id": revision,
            "code_manifest_sha256": code_sha,
            "controller_publisher_canary_receipt_sha256": controller_sha,
            "resource_profile": _canary_resource_profile(),
            "root_identities": roots,
            "slurm_program": {
                "template_path": str(COMPUTE_CANARY_TEMPLATE),
                "template_sha256": hashlib.sha256(
                    _compute_canary_template()
                ).hexdigest(),
                "rendered_sha256": hashlib.sha256(rendered).hexdigest(),
                "rendered_bytes": len(rendered),
                "submission_mode": "stdin",
                "path_argument": False,
            },
            "capture_protocol": CAPTURE_PROTOCOL,
            "sbatch_capture_initial_identities": captures.initial_identities,
            "submit_command": command,
            "prior_runtime_payloads_read": 0,
            "prior_runtime_payload_bytes_read": 0,
            "prior_runtime_payloads_reused": 0,
        }
        intent_raw = _canonical_json(intent)
        intent_sha = _exclusive_json(
            COMPUTE_CANARY_INTENT, intent, "V12 compute-canary launch intent"
        )
        captures.verify_initial()
        _executable_identity(SBATCH_COMMAND, SBATCH_COMMAND_SHA256, "sbatch")
        completed = subprocess.run(
            command, input=rendered, stdout=captures.stdout_fd,
            stderr=captures.stderr_fd, cwd=REPO,
            env=dict(SUBMISSION_ENVIRONMENT), check=False,
        )
        capture_records, payloads = captures.finalize()
    job_id = _parse_job_id(payloads["stdout"])
    accepted = completed.returncode == 0 and job_id is not None
    result = {
        "schema": PREFLIGHT_SCHEMA + "/compute-canary-sbatch-result/v1",
        "campaign": Source.COMPUTE_CANARY_CAMPAIGN,
        "launch_intent_sha256": intent_sha,
        "submit_command_sha256": _digest(command),
        "slurm_program_sha256": hashlib.sha256(rendered).hexdigest(),
        "process_returncode": completed.returncode,
        "stdout": capture_records["stdout"],
        "stderr": capture_records["stderr"],
        "parsed_job_id": job_id,
        "accepted_by_launcher": accepted,
        "raw_streams_preserved": True,
    }
    result_sha = _exclusive_json(
        COMPUTE_CANARY_RESULT, result, "V12 compute-canary sbatch result"
    )
    if not accepted:
        raise LaunchAuditError(
            "V12 compute-canary sbatch was not accepted; no resubmission"
        )
    receipt = {
        "schema": PREFLIGHT_SCHEMA + "/compute-canary-launch/v1",
        "campaign": Source.COMPUTE_CANARY_CAMPAIGN,
        "job_id": job_id,
        "accepted_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "submission_token": token,
        "repository_commit_id": revision,
        "code_manifest_sha256": code_sha,
        "controller_publisher_canary_receipt_sha256": controller_sha,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "sbatch_result_sha256": result_sha,
        "resource_profile": _canary_resource_profile(),
        "root_identities": roots,
        "slurm_program": intent["slurm_program"],
        "launch_recovered": False,
        "recovery_evidence": None,
    }
    receipt_sha = _exclusive_json(
        COMPUTE_CANARY_RECEIPT, receipt, "V12 compute-canary launch receipt"
    )
    summary = {
        "job_id": job_id,
        "launch_receipt_sha256": receipt_sha,
        "array": "0-0",
        "resubmitted": False,
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return summary


def _recovery_evidence(_intent: dict, result: dict) -> dict:
    process = result.get("process_observation")
    parsed = result.get("parsed_job_id")
    accepted_return = (
        result.get("accepted_by_launcher") is True
        and type(process) is dict
        and process.get("kind") == "completed-process"
        and type(process.get("returncode")) is int
        and process.get("returncode") == 0
        and isinstance(parsed, str) and re.fullmatch(r"[0-9]+", parsed) is not None
    )
    if accepted_return:
        return {
            "source": "retained-sbatch-stdout", "job_id": parsed,
            "stdout_sha256": result["stdout"]["sha256"],
            "accepted_returncode_zero": True,
            "scheduler_queries_during_recovery": 0,
            "no_resubmission": True,
        }
    raise LaunchAuditError(
        "ambiguous V12 submission cannot be recovered without an extra "
        "scheduler query; campaign is burned and resubmission is forbidden"
    )


def recover_launch() -> None:
    if os.path.lexists(LAUNCH_RECEIPT):
        raise LaunchAuditError("V12 launch receipt already exists")
    intent_raw, intent = _load_intent_only()
    rendered = _render_slurm(
        intent["code_manifest_sha256"], intent["source_inventory_sha256"],
        intent["repository_commit_id"],
    )
    if os.path.lexists(SBATCH_RESULT):
        _result_sha, result = _load_sbatch_result(intent_raw, intent)
    else:
        records, payloads = _capture_records_from_disk(intent)
        _result_sha, result = _publish_sbatch_result(
            intent_raw, intent, rendered, records, payloads,
            completed=None, error=None, recovered=True,
        )
    evidence = _recovery_evidence(intent, result)
    digest = _write_launch_receipt(
        intent_raw, intent, evidence["job_id"],
        recovered=True, recovery_evidence=evidence,
    )
    print(json.dumps({
        "job_id": evidence["job_id"],
        "launch_receipt_reconstructed": True,
        "launch_receipt_sha256": digest,
        "recovery_source": evidence["source"],
        "resubmitted": False,
    }, sort_keys=True, indent=2))


def _poll_paths(directory: Path, index: int) -> dict[str, Path]:
    if type(index) is not int or index < 0:
        raise LaunchAuditError("V12 poll index is invalid")
    stem = "poll-{:04d}-".format(index)
    return {
        "intent": directory / (stem + "intent.json"),
        "stdout": directory / (stem + "stdout.bin"),
        "stderr": directory / (stem + "stderr.bin"),
        "result": directory / (stem + "result.json"),
        "receipt": directory / (stem + "receipt.json"),
        "abandoned": directory / (stem + "abandoned.json"),
    }


def _poll_sequence(
    directory: Path,
) -> tuple[int, str | None, dict | None, tuple[dict[str, Path], set[str]] | None]:
    _directory_identity(directory, "V12 scheduler-poll directory")
    entries = sorted(directory.iterdir(), key=lambda path: path.name)
    if any(entry.is_symlink() or not entry.is_file() for entry in entries):
        raise LaunchAuditError("V12 scheduler-poll namespace changed")
    index = 0
    previous_sha = None
    previous = None
    consumed = set()
    while True:
        paths = _poll_paths(directory, index)
        present = {name for name, path in paths.items() if path.exists()}
        if not present:
            break
        normal = {"intent", "stdout", "stderr", "result", "receipt"}
        abandoned = {"intent", "stdout", "stderr", "abandoned"}
        if present == normal:
            raw, receipt = _load_json(paths["receipt"], "V12 poll receipt")
            previous_sha = hashlib.sha256(raw).hexdigest()
            previous = receipt
        elif "abandoned" in present and present in (
            abandoned, abandoned | {"result"},
        ):
            raw, receipt = _load_json(
                paths["abandoned"], "V12 abandoned-poll receipt"
            )
            if (
                receipt.get("outcome") != "abandoned-unknown"
                or receipt.get("authorizing") is not False
                or receipt.get("scheduler_queries_during_recovery") != 0
            ):
                raise LaunchAuditError("V12 abandoned poll changed")
            previous_sha = hashlib.sha256(raw).hexdigest()
            previous = receipt
        elif "intent" in present and {"stdout", "stderr"} <= present:
            consumed.update(path for name, path in paths.items() if name in present)
            if set(entries) != consumed:
                raise LaunchAuditError("unexpected V12 scheduler-poll artifact")
            return index, previous_sha, previous, (paths, present)
        else:
            raise LaunchAuditError(
                "poll failure before durable intent burns the V12 campaign"
            )
        consumed.update(path for name, path in paths.items() if name in present)
        index += 1
    if set(entries) != consumed:
        raise LaunchAuditError("unexpected V12 scheduler-poll artifact")
    return index, previous_sha, previous, None


def _abandon_stranded_poll(
    *, paths: dict[str, Path], present: set[str], campaign: str,
    job_id: str, poll_schema: str, expected_previous_sha: str | None,
    now: datetime.datetime,
) -> str:
    intent_raw, intent = _load_json(paths["intent"], "stranded V12 poll intent")
    if (
        intent.get("schema") != poll_schema + "/intent"
        or intent.get("campaign") != campaign
        or intent.get("job_id") != job_id
        or intent.get("previous_poll_receipt_sha256") != expected_previous_sha
    ):
        raise LaunchAuditError("stranded V12 poll intent changed")
    try:
        recorded = datetime.datetime.fromisoformat(intent["recorded_utc"])
    except (KeyError, TypeError, ValueError) as err:
        raise LaunchAuditError("stranded V12 poll timestamp changed") from err
    if recorded.tzinfo is None:
        raise LaunchAuditError("stranded V12 poll timestamp lacks timezone")
    successor_not_before = recorded.astimezone(
        datetime.timezone.utc
    ) + datetime.timedelta(seconds=MIN_POLL_INTERVAL_SECONDS)
    if now < successor_not_before:
        raise LaunchAuditError(
            "stranded V12 poll suppresses another query for one hour"
        )
    durable = {}
    for name in ("intent", "stdout", "stderr", "result"):
        if name in present:
            durable[paths[name].name] = hashlib.sha256(
                _regular_bytes(paths[name], "stranded V12 poll " + name)
            ).hexdigest()
    abandoned = {
        "schema": poll_schema + "/abandoned",
        "campaign": campaign,
        "poll_index": intent["poll_index"],
        "job_id": job_id,
        "recorded_utc": now.isoformat(timespec="seconds"),
        "successor_not_before_utc": successor_not_before.isoformat(
            timespec="seconds"
        ),
        "intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "durable_files": dict(sorted(durable.items())),
        "outcome": "abandoned-unknown",
        "authorizing": False,
        "scheduler_queries_during_recovery": 0,
    }
    return _exclusive_json(
        paths["abandoned"], abandoned, "V12 abandoned-poll receipt"
    )


def _poll_command(job_id: str) -> list[str]:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("V12 scheduler query has an invalid job id")
    return [
        str(SACCT_COMMAND), "-j", job_id, "-X", "--array", "-n", "-P",
        "--format=JobID,Account,Partition,QOS,ReqCPUS,ReqMem,Timelimit,"
        "State,ExitCode,Restarts,JobName",
    ]


def _parse_combined_scheduler_rows(
    raw: bytes, *, job_id: str, task_count: int, job_name: str,
) -> tuple[list[dict], list[dict]]:
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise LaunchAuditError("V12 scheduler output is not ASCII") from err
    rows = []
    contracts = []
    for line in lines:
        fields = line.split("|")
        if len(fields) != 11:
            raise LaunchAuditError("V12 combined scheduler row changed")
        (
            raw_id, account, partition, qos, cpus, memory, time_limit,
            state, exit_code, restarts, actual_name,
        ) = fields
        match = re.fullmatch(re.escape(job_id) + r"_([0-9]+)", raw_id)
        if raw_id == job_id and task_count == 1:
            index = 0
        elif match is not None:
            index = int(match.group(1))
        else:
            raise LaunchAuditError("V12 scheduler resource contract changed")
        if (
            account != ACCOUNT or partition != PARTITION
            or qos != QOS or cpus != "1" or memory != MEMORY
            or time_limit != TIME_LIMIT
            or state not in ACTIVE_STATES | TERMINAL_STATES
            or EXIT_CODE_RE.fullmatch(exit_code) is None
            or restarts != "0" or actual_name != job_name
        ):
            raise LaunchAuditError("V12 scheduler resource contract changed")
        rows.append({
            "array_task": index, "state": state, "exit_code": exit_code,
            "partition": partition, "restarts": 0,
        })
        contracts.append({
            "array_task": index, "account": account,
            "partition": partition, "qos": qos, "req_cpus": 1,
            "req_mem": memory, "time_limit": time_limit,
            "state": state, "exit_code": exit_code,
            "restarts": 0, "job_name": actual_name,
        })
    rows.sort(key=lambda value: value["array_task"])
    contracts.sort(key=lambda value: value["array_task"])
    if (
        len(rows) != task_count
        or [row["array_task"] for row in rows] != list(range(task_count))
        or [row["array_task"] for row in contracts] != list(range(task_count))
    ):
        raise LaunchAuditError("V12 scheduler array cardinality changed")
    return rows, contracts


_POLL_INTENT_KEYS = frozenset({
    "schema", "campaign", "poll_index", "job_id", "recorded_utc",
    "not_before_utc", "previous_poll_receipt_sha256",
    "launch_receipt_sha256", "command", "capture_initial_identities",
})
_POLL_RESULT_KEYS = frozenset({
    "schema", "campaign", "poll_index", "intent_sha256",
    "command_sha256", "process_returncode", "stdout", "stderr",
    "single_scheduler_query",
})
_POLL_RECEIPT_KEYS = frozenset({
    "schema", "campaign", "poll_index", "job_id", "recorded_utc",
    "not_before_utc", "previous_poll_receipt_sha256", "intent_sha256",
    "stdout_sha256", "stderr_sha256", "result_sha256",
    "scheduler_rows", "scheduler_contract_rows", "state_counts",
    "all_terminal", "all_success",
})
_POLL_ABANDONED_KEYS = frozenset({
    "schema", "campaign", "poll_index", "job_id", "recorded_utc",
    "successor_not_before_utc", "intent_sha256", "durable_files",
    "outcome", "authorizing", "scheduler_queries_during_recovery",
})


def _utc_timestamp(value, label: str) -> datetime.datetime:
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError) as err:
        raise LaunchAuditError("{} changed".format(label)) from err
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != datetime.timedelta(0)
        or parsed.isoformat(timespec="seconds") != value
    ):
        raise LaunchAuditError("{} is not canonical UTC".format(label))
    return parsed


def _retained_poll_bytes(path: Path, label: str) -> bytes:
    raw = _regular_bytes(path, label)
    try:
        info = path.lstat()
    except OSError as err:
        raise LaunchAuditError("{} vanished after read".format(label)) from err
    if (
        path.is_symlink() or not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o400
        or info.st_uid != os.getuid() or info.st_nlink != 1
    ):
        raise LaunchAuditError(
            "{} is not an immutable owned poll file".format(label)
        )
    return raw


def _retained_poll_json(path: Path, label: str) -> tuple[bytes, dict]:
    raw = _retained_poll_bytes(path, label)
    try:
        value = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise LaunchAuditError("{} is not canonical JSON".format(label)) from err
    if type(value) is not dict or raw != _canonical_json(value):
        raise LaunchAuditError("{} is not canonical JSON".format(label))
    return raw, value


def _capture_identity_matches_file(
    identity: dict, path: Path, *, initial: bool,
) -> bool:
    size_key = "bytes_at_intent" if initial else "bytes"
    expected_keys = {
        "path", "canonical_path", "device", "inode", "mode", "uid", "gid",
        "link_count", size_key,
    }
    try:
        info = path.lstat()
    except OSError:
        return False
    return (
        type(identity) is dict
        and set(identity) == expected_keys
        and identity.get("path") == str(path)
        and identity.get("canonical_path") == str(path)
        and identity.get("device") == info.st_dev
        and identity.get("inode") == info.st_ino
        and identity.get("mode") == "0400"
        and identity.get("uid") == info.st_uid == os.getuid()
        and identity.get("gid") == info.st_gid
        and identity.get("link_count") == info.st_nlink == 1
        and stat.S_ISREG(info.st_mode)
        and stat.S_IMODE(info.st_mode) == 0o400
        and (
            identity.get(size_key) == 0 if initial
            else identity.get(size_key) == info.st_size
        )
    )


def _validate_poll_capture(
    evidence, path: Path, raw: bytes, initial_identity,
) -> None:
    if (
        type(evidence) is not dict
        or set(evidence) != {
            "path", "bytes", "sha256", "initial_identity", "final_identity",
        }
        or evidence.get("path") != str(path)
        or evidence.get("bytes") != len(raw)
        or evidence.get("sha256") != hashlib.sha256(raw).hexdigest()
        or evidence.get("initial_identity") != initial_identity
        or not _capture_identity_matches_file(
            initial_identity, path, initial=True
        )
        or not _capture_identity_matches_file(
            evidence.get("final_identity"), path, initial=False
        )
    ):
        raise LaunchAuditError("V12 retained poll capture changed")


def _validate_poll_intent(
    intent: dict, *, index: int, campaign: str, poll_schema: str,
    job_id: str, launch_sha: str, previous_sha: str | None,
    expected_not_before: datetime.datetime,
) -> datetime.datetime:
    recorded = _utc_timestamp(intent.get("recorded_utc"), "V12 poll timestamp")
    not_before = _utc_timestamp(
        intent.get("not_before_utc"), "V12 poll cadence timestamp"
    )
    captures = intent.get("capture_initial_identities")
    if (
        set(intent) != _POLL_INTENT_KEYS
        or intent.get("schema") != poll_schema + "/intent"
        or intent.get("campaign") != campaign
        or intent.get("poll_index") != index
        or intent.get("job_id") != job_id
        or intent.get("previous_poll_receipt_sha256") != previous_sha
        or intent.get("launch_receipt_sha256") != launch_sha
        or intent.get("command") != _poll_command(job_id)
        or type(captures) is not dict
        or set(captures) != {"stdout", "stderr"}
        or not_before != expected_not_before
        or recorded < not_before
    ):
        raise LaunchAuditError("V12 retained poll intent or cadence changed")
    return recorded


def _validate_poll_result(
    result: dict, *, index: int, campaign: str, poll_schema: str,
    intent_sha: str, intent: dict, paths: dict[str, Path],
    stdout: bytes, stderr: bytes, require_success: bool,
) -> None:
    if (
        set(result) != _POLL_RESULT_KEYS
        or result.get("schema") != poll_schema + "/result"
        or result.get("campaign") != campaign
        or result.get("poll_index") != index
        or result.get("intent_sha256") != intent_sha
        or result.get("command_sha256") != _digest(intent["command"])
        or type(result.get("process_returncode")) is not int
        or result.get("single_scheduler_query") is not True
        or (require_success and result.get("process_returncode") != 0)
    ):
        raise LaunchAuditError("V12 retained poll result changed")
    for stream, raw in (("stdout", stdout), ("stderr", stderr)):
        _validate_poll_capture(
            result.get(stream), paths[stream], raw,
            intent["capture_initial_identities"].get(stream),
        )


def _next_poll_not_before(
    accepted_utc: datetime.datetime, previous: dict | None,
) -> datetime.datetime:
    if previous is None:
        return accepted_utc + datetime.timedelta(
            seconds=MIN_POLL_INTERVAL_SECONDS
        )
    if previous.get("outcome") == "abandoned-unknown":
        return _utc_timestamp(
            previous.get("successor_not_before_utc"),
            "V12 abandoned-poll cadence",
        )
    return _utc_timestamp(
        previous.get("recorded_utc"), "V12 previous poll timestamp"
    ) + datetime.timedelta(seconds=MIN_POLL_INTERVAL_SECONDS)


def _validated_poll_sequence(
    directory: Path, *, campaign: str, poll_schema: str, task_count: int,
    launch_sha: str, launch_accepted_utc: str, job_id: str, job_name: str,
) -> tuple[
    int, str | None, dict | None,
    tuple[dict[str, Path], set[str]] | None,
]:
    """Revalidate the complete retained chain before deriving any control state."""
    index, _untrusted_sha, _untrusted_previous, stranded = _poll_sequence(
        directory
    )
    accepted = _utc_timestamp(
        launch_accepted_utc, "V12 launch acceptance timestamp"
    )
    previous_sha = None
    previous = None
    terminal_seen = False
    completed = index
    for current_index in range(completed):
        paths = _poll_paths(directory, current_index)
        intent_raw, intent = _retained_poll_json(
            paths["intent"], "V12 poll intent"
        )
        expected_not_before = _next_poll_not_before(accepted, previous)
        recorded = _validate_poll_intent(
            intent, index=current_index, campaign=campaign,
            poll_schema=poll_schema, job_id=job_id, launch_sha=launch_sha,
            previous_sha=previous_sha,
            expected_not_before=expected_not_before,
        )
        if terminal_seen:
            raise LaunchAuditError("V12 retained poll follows a terminal poll")
        stdout = _retained_poll_bytes(paths["stdout"], "V12 poll stdout")
        stderr = _retained_poll_bytes(paths["stderr"], "V12 poll stderr")
        if paths["abandoned"].exists():
            abandoned_raw, abandoned = _retained_poll_json(
                paths["abandoned"], "V12 abandoned-poll receipt"
            )
            durable = {
                paths[name].name: hashlib.sha256(
                    _retained_poll_bytes(
                        paths[name], "V12 abandoned poll " + name
                    )
                ).hexdigest()
                for name in ("intent", "stdout", "stderr", "result")
                if paths[name].exists()
            }
            abandoned_recorded = _utc_timestamp(
                abandoned.get("recorded_utc"),
                "V12 abandoned-poll timestamp",
            )
            successor_not_before = _utc_timestamp(
                abandoned.get("successor_not_before_utc"),
                "V12 abandoned-poll successor timestamp",
            )
            if paths["result"].exists():
                _result_raw, result = _retained_poll_json(
                    paths["result"], "V12 abandoned poll result"
                )
                _validate_poll_result(
                    result, index=current_index, campaign=campaign,
                    poll_schema=poll_schema,
                    intent_sha=hashlib.sha256(intent_raw).hexdigest(),
                    intent=intent, paths=paths, stdout=stdout, stderr=stderr,
                    require_success=False,
                )
            else:
                for stream in ("stdout", "stderr"):
                    if not _capture_identity_matches_file(
                        intent["capture_initial_identities"].get(stream),
                        paths[stream], initial=True,
                    ):
                        raise LaunchAuditError(
                            "V12 stranded poll capture identity changed"
                        )
            if (
                set(abandoned) != _POLL_ABANDONED_KEYS
                or abandoned.get("schema") != poll_schema + "/abandoned"
                or abandoned.get("campaign") != campaign
                or abandoned.get("poll_index") != current_index
                or abandoned.get("job_id") != job_id
                or abandoned.get("intent_sha256")
                != hashlib.sha256(intent_raw).hexdigest()
                or abandoned.get("durable_files")
                != dict(sorted(durable.items()))
                or abandoned.get("outcome") != "abandoned-unknown"
                or abandoned.get("authorizing") is not False
                or abandoned.get("scheduler_queries_during_recovery") != 0
                or abandoned_recorded
                < recorded + datetime.timedelta(
                    seconds=MIN_POLL_INTERVAL_SECONDS
                )
                or successor_not_before
                != recorded + datetime.timedelta(
                    seconds=MIN_POLL_INTERVAL_SECONDS
                )
            ):
                raise LaunchAuditError("V12 abandoned poll chain changed")
            previous_sha = hashlib.sha256(abandoned_raw).hexdigest()
            previous = abandoned
            continue
        result_raw, result = _retained_poll_json(
            paths["result"], "V12 poll result"
        )
        receipt_raw, receipt = _retained_poll_json(
            paths["receipt"], "V12 poll receipt"
        )
        _validate_poll_result(
            result, index=current_index, campaign=campaign,
            poll_schema=poll_schema,
            intent_sha=hashlib.sha256(intent_raw).hexdigest(), intent=intent,
            paths=paths, stdout=stdout, stderr=stderr, require_success=True,
        )
        rows, contracts = _parse_combined_scheduler_rows(
            stdout, job_id=job_id, task_count=task_count, job_name=job_name,
        )
        state_counts = dict(sorted(Counter(
            row["state"] for row in rows
        ).items()))
        all_terminal = all(row["state"] in TERMINAL_STATES for row in rows)
        all_success = all(
            row["state"] == "COMPLETED" and row["exit_code"] == "0:0"
            for row in rows
        )
        if (
            set(receipt) != _POLL_RECEIPT_KEYS
            or receipt.get("schema") != poll_schema + "/receipt"
            or receipt.get("campaign") != campaign
            or receipt.get("poll_index") != current_index
            or receipt.get("job_id") != job_id
            or receipt.get("recorded_utc") != intent.get("recorded_utc")
            or receipt.get("not_before_utc") != intent.get("not_before_utc")
            or receipt.get("previous_poll_receipt_sha256") != previous_sha
            or receipt.get("intent_sha256")
            != hashlib.sha256(intent_raw).hexdigest()
            or receipt.get("stdout_sha256")
            != hashlib.sha256(stdout).hexdigest()
            or receipt.get("stderr_sha256")
            != hashlib.sha256(stderr).hexdigest()
            or receipt.get("result_sha256")
            != hashlib.sha256(result_raw).hexdigest()
            or receipt.get("scheduler_rows") != rows
            or receipt.get("scheduler_contract_rows") != contracts
            or receipt.get("state_counts") != state_counts
            or receipt.get("all_terminal") is not all_terminal
            or receipt.get("all_success") is not all_success
            or stderr != b""
        ):
            raise LaunchAuditError("V12 retained poll receipt changed")
        previous_sha = hashlib.sha256(receipt_raw).hexdigest()
        previous = receipt
        terminal_seen = all_terminal
    if stranded is not None:
        paths, present = stranded
        intent_raw, intent = _retained_poll_json(
            paths["intent"], "stranded V12 poll intent"
        )
        _validate_poll_intent(
            intent, index=completed, campaign=campaign,
            poll_schema=poll_schema, job_id=job_id, launch_sha=launch_sha,
            previous_sha=previous_sha,
            expected_not_before=_next_poll_not_before(accepted, previous),
        )
        for stream in ("stdout", "stderr"):
            raw = _retained_poll_bytes(
                paths[stream], "stranded V12 poll " + stream
            )
            if paths["result"].exists():
                continue
            if not _capture_identity_matches_file(
                intent["capture_initial_identities"].get(stream),
                paths[stream], initial=True,
            ):
                raise LaunchAuditError("stranded V12 poll capture changed")
        if paths["result"].exists():
            _result_raw, result = _retained_poll_json(
                paths["result"], "stranded V12 poll result"
            )
            _validate_poll_result(
                result, index=completed, campaign=campaign,
                poll_schema=poll_schema,
                intent_sha=hashlib.sha256(intent_raw).hexdigest(),
                intent=intent, paths=paths,
                stdout=_retained_poll_bytes(
                    paths["stdout"], "stranded poll stdout"
                ),
                stderr=_retained_poll_bytes(
                    paths["stderr"], "stranded poll stderr"
                ),
                require_success=False,
            )
    return completed, previous_sha, previous, stranded


def _load_compute_launch() -> tuple[str, dict, str]:
    intent_raw, intent = _load_json(
        COMPUTE_CANARY_INTENT, "V12 compute-canary launch intent"
    )
    raw, receipt = _load_json(
        COMPUTE_CANARY_RECEIPT, "V12 compute-canary launch receipt"
    )
    result_raw, result = _load_json(
        COMPUTE_CANARY_RESULT, "V12 compute-canary sbatch result"
    )
    controller_sha, _controller = _load_controller_canary()
    receipt_keys = {
        "schema", "campaign", "job_id", "accepted_utc",
        "submission_token", "repository_commit_id", "code_manifest_sha256",
        "controller_publisher_canary_receipt_sha256",
        "launch_intent_sha256", "sbatch_result_sha256", "resource_profile",
        "root_identities", "slurm_program", "launch_recovered",
        "recovery_evidence",
    }
    intent_keys = {
        "schema", "campaign", "recorded_utc", "submission_token",
        "repository_commit_id", "code_manifest_sha256",
        "controller_publisher_canary_receipt_sha256", "resource_profile",
        "root_identities", "slurm_program", "capture_protocol",
        "sbatch_capture_initial_identities", "submit_command",
        "prior_runtime_payloads_read", "prior_runtime_payload_bytes_read",
        "prior_runtime_payloads_reused",
    }
    try:
        accepted = datetime.datetime.fromisoformat(receipt.get("accepted_utc"))
        recorded = datetime.datetime.fromisoformat(intent.get("recorded_utc"))
    except (TypeError, ValueError) as err:
        raise LaunchAuditError("V12 compute-canary timestamp changed") from err
    if (
        set(receipt) != receipt_keys
        or set(intent) != intent_keys
        or receipt.get("schema") != PREFLIGHT_SCHEMA + "/compute-canary-launch/v1"
        or receipt.get("campaign") != Source.COMPUTE_CANARY_CAMPAIGN
        or intent.get("schema")
        != PREFLIGHT_SCHEMA + "/compute-canary-launch-intent/v1"
        or intent.get("campaign") != Source.COMPUTE_CANARY_CAMPAIGN
        or not isinstance(receipt.get("job_id"), str)
        or not receipt["job_id"].isdigit()
        or receipt.get("launch_intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or receipt.get("sbatch_result_sha256")
        != hashlib.sha256(result_raw).hexdigest()
        or result.get("accepted_by_launcher") is not True
        or result.get("parsed_job_id") != receipt.get("job_id")
        or receipt.get("submission_token") != intent.get("submission_token")
        or receipt.get("repository_commit_id")
        != intent.get("repository_commit_id")
        or receipt.get("code_manifest_sha256")
        != intent.get("code_manifest_sha256")
        or receipt.get("controller_publisher_canary_receipt_sha256")
        != controller_sha
        or intent.get("controller_publisher_canary_receipt_sha256")
        != controller_sha
        or receipt.get("resource_profile") != _canary_resource_profile()
        or intent.get("resource_profile") != _canary_resource_profile()
        or receipt.get("root_identities") != intent.get("root_identities")
        or receipt.get("slurm_program") != intent.get("slurm_program")
        or intent.get("submit_command")
        != _canary_submit_command(receipt.get("submission_token"))
        or intent.get("prior_runtime_payloads_read") != 0
        or intent.get("prior_runtime_payload_bytes_read") != 0
        or intent.get("prior_runtime_payloads_reused") != 0
        or receipt.get("launch_recovered") is not False
        or receipt.get("recovery_evidence") is not None
        or accepted.tzinfo is None or recorded.tzinfo is None
        or accepted.astimezone(datetime.timezone.utc)
        < recorded.astimezone(datetime.timezone.utc)
    ):
        raise LaunchAuditError("V12 compute-canary launch receipt changed")
    return hashlib.sha256(raw).hexdigest(), receipt, receipt["accepted_utc"]


def _poll_scheduler(
    *, campaign: str, launch_sha: str, launch_receipt: dict,
    launch_recorded_utc: str, poll_dir: Path, terminal_path: Path,
    task_count: int, job_name: str, terminal_schema: str,
    poll_schema: str,
    now: datetime.datetime | None = None,
) -> dict:
    if os.path.lexists(terminal_path):
        raise LaunchAuditError("V12 terminal scheduler receipt already exists")
    current = now or datetime.datetime.now(datetime.timezone.utc)
    if current.tzinfo is None:
        raise LaunchAuditError("V12 poll clock lacks timezone")
    current = current.astimezone(datetime.timezone.utc)
    poll_index, previous_sha, previous, stranded = _validated_poll_sequence(
        poll_dir, campaign=campaign, poll_schema=poll_schema,
        task_count=task_count, launch_sha=launch_sha,
        launch_accepted_utc=launch_recorded_utc,
        job_id=launch_receipt["job_id"], job_name=job_name,
    )
    if stranded is not None:
        paths, present = stranded
        _abandon_stranded_poll(
            paths=paths, present=present, campaign=campaign,
            job_id=launch_receipt["job_id"], poll_schema=poll_schema,
            expected_previous_sha=previous_sha, now=current,
        )
        poll_index, previous_sha, previous, stranded = _validated_poll_sequence(
            poll_dir, campaign=campaign, poll_schema=poll_schema,
            task_count=task_count, launch_sha=launch_sha,
            launch_accepted_utc=launch_recorded_utc,
            job_id=launch_receipt["job_id"], job_name=job_name,
        )
        if stranded is not None:
            raise LaunchAuditError("V12 stranded poll recovery did not close")
    if previous is not None and previous.get("outcome") == "abandoned-unknown":
        abandoned_keys = {
            "schema", "campaign", "poll_index", "job_id", "recorded_utc",
            "successor_not_before_utc", "intent_sha256", "durable_files",
            "outcome", "authorizing", "scheduler_queries_during_recovery",
        }
        abandoned_paths = _poll_paths(poll_dir, poll_index - 1)
        abandoned_intent = _regular_bytes(
            abandoned_paths["intent"], "abandoned V12 poll intent"
        )
        durable = previous.get("durable_files")
        if (
            set(previous) != abandoned_keys
            or previous.get("schema") != poll_schema + "/abandoned"
            or previous.get("campaign") != campaign
            or previous.get("poll_index") != poll_index - 1
            or previous.get("job_id") != launch_receipt["job_id"]
            or previous.get("intent_sha256")
            != hashlib.sha256(abandoned_intent).hexdigest()
            or type(durable) is not dict
            or durable.get(abandoned_paths["intent"].name)
            != hashlib.sha256(abandoned_intent).hexdigest()
            or previous.get("authorizing") is not False
            or previous.get("scheduler_queries_during_recovery") != 0
        ):
            raise LaunchAuditError("V12 abandoned-poll chain changed")
        for filename, digest in durable.items():
            candidate = poll_dir / filename
            if (
                candidate.parent != poll_dir
                or SHA256_RE.fullmatch(digest or "") is None
                or hashlib.sha256(
                    _regular_bytes(candidate, "abandoned V12 poll evidence")
                ).hexdigest() != digest
            ):
                raise LaunchAuditError("V12 abandoned-poll evidence changed")
    if previous is not None and previous.get("all_terminal") is True:
        state_counts = previous.get("state_counts")
        all_success = previous.get("all_success") is True
        terminal = {
            "schema": terminal_schema,
            "campaign": campaign,
            "job_id": launch_receipt["job_id"],
            "all_success": all_success,
            "state_counts": state_counts,
            "terminal_poll_receipt_sha256": previous_sha,
        }
        _exclusive_json(
            terminal_path, terminal, "recovered V12 scheduler terminal receipt"
        )
        summary = {
            "job_id": launch_receipt["job_id"],
            "poll_index": previous["poll_index"],
            "poll_receipt_sha256": previous_sha,
            "state_counts": state_counts,
            "all_terminal": True,
            "all_success": all_success,
            "scheduler_queries_this_poll": 0,
        }
        print(json.dumps(summary, sort_keys=True, indent=2))
        return summary
    anchor_text = (
        launch_recorded_utc if previous is None else previous.get("recorded_utc")
    )
    try:
        anchor = datetime.datetime.fromisoformat(anchor_text)
    except (TypeError, ValueError) as err:
        raise LaunchAuditError("V12 poll anchor changed") from err
    if anchor.tzinfo is None:
        raise LaunchAuditError("V12 poll anchor lacks timezone")
    if previous is not None and previous.get("outcome") == "abandoned-unknown":
        try:
            not_before = datetime.datetime.fromisoformat(
                previous["successor_not_before_utc"]
            )
        except (KeyError, TypeError, ValueError) as err:
            raise LaunchAuditError("V12 abandoned-poll cadence changed") from err
    else:
        not_before = anchor.astimezone(
            datetime.timezone.utc
        ) + datetime.timedelta(seconds=MIN_POLL_INTERVAL_SECONDS)
    if current < not_before:
        raise LaunchAuditError("V12 scheduler polling is limited to once per hour")
    paths = _poll_paths(poll_dir, poll_index)
    command = _poll_command(launch_receipt["job_id"])
    with _CapturePair(
        paths["stdout"], paths["stderr"], "scheduler poll",
    ) as captures:
        intent = {
            "schema": poll_schema + "/intent",
            "campaign": campaign,
            "poll_index": poll_index,
            "job_id": launch_receipt["job_id"],
            "recorded_utc": current.isoformat(timespec="seconds"),
            "not_before_utc": not_before.isoformat(timespec="seconds"),
            "previous_poll_receipt_sha256": previous_sha,
            "launch_receipt_sha256": launch_sha,
            "command": command,
            "capture_initial_identities": captures.initial_identities,
        }
        intent_sha = _exclusive_json(
            paths["intent"], intent, "V12 scheduler-poll intent"
        )
        _executable_identity(SACCT_COMMAND, SACCT_COMMAND_SHA256, "sacct")
        captures.verify_initial()
        completed = subprocess.run(
            command, stdout=captures.stdout_fd, stderr=captures.stderr_fd,
            cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), check=False,
        )
        records, payloads = captures.finalize()
    result = {
        "schema": poll_schema + "/result",
        "campaign": campaign,
        "poll_index": poll_index,
        "intent_sha256": intent_sha,
        "command_sha256": _digest(command),
        "process_returncode": completed.returncode,
        "stdout": records["stdout"],
        "stderr": records["stderr"],
        "single_scheduler_query": True,
    }
    result_sha = _exclusive_json(
        paths["result"], result, "V12 scheduler-poll result"
    )
    if completed.returncode != 0 or payloads["stderr"]:
        raise LaunchAuditError(
            "V12 scheduler poll failed; retained attempt blocks an immediate retry"
        )
    rows, contracts = _parse_combined_scheduler_rows(
        payloads["stdout"], job_id=launch_receipt["job_id"],
        task_count=task_count, job_name=job_name,
    )
    state_counts = dict(sorted(Counter(row["state"] for row in rows).items()))
    all_terminal = all(row["state"] in TERMINAL_STATES for row in rows)
    all_success = all(
        row["state"] == "COMPLETED" and row["exit_code"] == "0:0"
        for row in rows
    )
    receipt = {
        "schema": poll_schema + "/receipt",
        "campaign": campaign,
        "poll_index": poll_index,
        "job_id": launch_receipt["job_id"],
        "recorded_utc": current.isoformat(timespec="seconds"),
        "not_before_utc": not_before.isoformat(timespec="seconds"),
        "previous_poll_receipt_sha256": previous_sha,
        "intent_sha256": intent_sha,
        "stdout_sha256": records["stdout"]["sha256"],
        "stderr_sha256": records["stderr"]["sha256"],
        "result_sha256": result_sha,
        "scheduler_rows": rows,
        "scheduler_contract_rows": contracts,
        "state_counts": state_counts,
        "all_terminal": all_terminal,
        "all_success": all_success,
    }
    receipt_sha = _exclusive_json(
        paths["receipt"], receipt, "V12 scheduler-poll receipt"
    )
    if all_terminal:
        terminal = {
            "schema": terminal_schema,
            "campaign": campaign,
            "job_id": launch_receipt["job_id"],
            "all_success": all_success,
            "state_counts": state_counts,
            "terminal_poll_receipt_sha256": receipt_sha,
        }
        _exclusive_json(
            terminal_path, terminal, "V12 scheduler terminal receipt"
        )
    summary = {
        "job_id": launch_receipt["job_id"],
        "poll_index": poll_index,
        "poll_receipt_sha256": receipt_sha,
        "state_counts": state_counts,
        "all_terminal": all_terminal,
        "all_success": all_success,
        "scheduler_queries_this_poll": 1,
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return summary


def poll_compute_canary(now: datetime.datetime | None = None) -> dict:
    launch_sha, receipt, recorded = _load_compute_launch()
    name, _comment = _canary_submission_identity(receipt["submission_token"])
    return _poll_scheduler(
        campaign=Source.COMPUTE_CANARY_CAMPAIGN,
        launch_sha=launch_sha, launch_receipt=receipt,
        launch_recorded_utc=recorded, poll_dir=COMPUTE_CANARY_POLL_DIR,
        terminal_path=COMPUTE_CANARY_TERMINAL_RECEIPT, task_count=1,
        job_name=name,
        terminal_schema=PREFLIGHT_SCHEMA + "/compute-canary-terminal/v1",
        poll_schema=PREFLIGHT_SCHEMA + "/compute-canary-poll/v1",
        now=now,
    )


def poll_full(now: datetime.datetime | None = None) -> dict:
    launch_sha, receipt = _load_launch()
    name, _comment = _submission_identity(receipt["submission_token"])
    return _poll_scheduler(
        campaign="v12-full-census", launch_sha=launch_sha,
        launch_receipt=receipt, launch_recorded_utc=receipt["accepted_utc"],
        poll_dir=FULL_POLL_DIR, terminal_path=FULL_TERMINAL_RECEIPT,
        task_count=ARRAY_TASKS, job_name=name,
        terminal_schema=EXECUTION_SCHEMA + "/terminal/v1",
        poll_schema=POLL_SCHEMA, now=now,
    )


def _retained_terminal_gate(
    *, terminal_path: Path, poll_dir: Path, expected_schema: str,
    campaign: str, job_id: str, task_count: int, job_name: str,
    poll_schema: str, launch_sha: str, launch_accepted_utc: str,
) -> tuple[str, str, dict]:
    terminal_raw, terminal = _load_json(
        terminal_path, "V12 scheduler terminal receipt"
    )
    if (
        set(terminal) != {
            "schema", "campaign", "job_id", "all_success",
            "state_counts", "terminal_poll_receipt_sha256",
        }
        or terminal.get("schema") != expected_schema
        or terminal.get("campaign") != campaign
        or terminal.get("job_id") != job_id
        or terminal.get("all_success") is not True
        or SHA256_RE.fullmatch(
            terminal.get("terminal_poll_receipt_sha256", "")
        ) is None
    ):
        raise LaunchAuditError("V12 retained scheduler gate did not pass")
    index, latest_sha, latest, stranded = _validated_poll_sequence(
        poll_dir, campaign=campaign, poll_schema=poll_schema,
        task_count=task_count, launch_sha=launch_sha,
        launch_accepted_utc=launch_accepted_utc,
        job_id=job_id, job_name=job_name,
    )
    if (
        stranded is not None or index < 1 or latest is None
        or latest_sha != terminal["terminal_poll_receipt_sha256"]
        or latest.get("job_id") != job_id
        or latest.get("campaign") != campaign
        or latest.get("all_terminal") is not True
        or latest.get("all_success") is not True
        or latest.get("state_counts") != terminal.get("state_counts")
    ):
        raise LaunchAuditError("V12 terminal receipt is not the retained poll")
    paths = _poll_paths(poll_dir, index - 1)
    intent_raw, intent = _load_json(paths["intent"], "V12 terminal poll intent")
    result_raw, result = _load_json(paths["result"], "V12 terminal poll result")
    stdout = _regular_bytes(paths["stdout"], "V12 terminal poll stdout")
    stderr = _regular_bytes(paths["stderr"], "V12 terminal poll stderr")
    receipt_keys = {
        "schema", "campaign", "poll_index", "job_id", "recorded_utc",
        "not_before_utc", "previous_poll_receipt_sha256", "intent_sha256",
        "stdout_sha256", "stderr_sha256", "result_sha256",
        "scheduler_rows", "scheduler_contract_rows", "state_counts",
        "all_terminal", "all_success",
    }
    intent_keys = {
        "schema", "campaign", "poll_index", "job_id", "recorded_utc",
        "not_before_utc", "previous_poll_receipt_sha256",
        "launch_receipt_sha256", "command", "capture_initial_identities",
    }
    result_keys = {
        "schema", "campaign", "poll_index", "intent_sha256",
        "command_sha256", "process_returncode", "stdout", "stderr",
        "single_scheduler_query",
    }
    rows, contracts = _parse_combined_scheduler_rows(
        stdout, job_id=job_id, task_count=task_count, job_name=job_name,
    )
    state_counts = dict(sorted(Counter(row["state"] for row in rows).items()))
    if index == 1:
        expected_previous_sha = None
        previous_attempt = None
    else:
        previous_paths = _poll_paths(poll_dir, index - 2)
        previous_path = (
            previous_paths["receipt"]
            if previous_paths["receipt"].exists()
            else previous_paths["abandoned"]
        )
        previous_raw, previous_attempt = _load_json(
            previous_path, "previous V12 poll record"
        )
        expected_previous_sha = hashlib.sha256(previous_raw).hexdigest()
    try:
        recorded = datetime.datetime.fromisoformat(intent["recorded_utc"])
        not_before = datetime.datetime.fromisoformat(intent["not_before_utc"])
    except (KeyError, TypeError, ValueError) as err:
        raise LaunchAuditError("V12 terminal poll cadence changed") from err
    if recorded.tzinfo is None or not_before.tzinfo is None:
        raise LaunchAuditError("V12 terminal poll cadence lacks timezone")
    if previous_attempt is not None:
        if previous_attempt.get("outcome") == "abandoned-unknown":
            expected_not_before = datetime.datetime.fromisoformat(
                previous_attempt["successor_not_before_utc"]
            )
        else:
            expected_not_before = datetime.datetime.fromisoformat(
                previous_attempt["recorded_utc"]
            ) + datetime.timedelta(seconds=MIN_POLL_INTERVAL_SECONDS)
    else:
        try:
            expected_not_before = datetime.datetime.fromisoformat(
                launch_accepted_utc
            ) + datetime.timedelta(seconds=MIN_POLL_INTERVAL_SECONDS)
        except (TypeError, ValueError) as err:
            raise LaunchAuditError("V12 launch poll anchor changed") from err
    if (
        set(latest) != receipt_keys
        or latest.get("schema") != poll_schema + "/receipt"
        or set(intent) != intent_keys
        or intent.get("schema") != poll_schema + "/intent"
        or intent.get("campaign") != campaign
        or intent.get("poll_index") != index - 1
        or intent.get("job_id") != job_id
        or intent.get("launch_receipt_sha256") != launch_sha
        or intent.get("previous_poll_receipt_sha256")
        != expected_previous_sha
        or latest.get("previous_poll_receipt_sha256")
        != expected_previous_sha
        or latest.get("recorded_utc") != intent.get("recorded_utc")
        or latest.get("not_before_utc") != intent.get("not_before_utc")
        or recorded < not_before
        or not_before != expected_not_before
        or intent.get("command") != _poll_command(job_id)
        or set(result) != result_keys
        or result.get("schema") != poll_schema + "/result"
        or result.get("campaign") != campaign
        or result.get("poll_index") != index - 1
        or result.get("intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or result.get("command_sha256") != _digest(_poll_command(job_id))
        or result.get("process_returncode") != 0
        or result.get("single_scheduler_query") is not True
        or result.get("stdout", {}).get("sha256")
        != hashlib.sha256(stdout).hexdigest()
        or result.get("stderr", {}).get("sha256")
        != hashlib.sha256(stderr).hexdigest()
        or stderr != b""
        or latest.get("intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or latest.get("stdout_sha256") != hashlib.sha256(stdout).hexdigest()
        or latest.get("stderr_sha256") != hashlib.sha256(stderr).hexdigest()
        or latest.get("result_sha256")
        != hashlib.sha256(result_raw).hexdigest()
        or latest.get("scheduler_rows") != rows
        or latest.get("scheduler_contract_rows") != contracts
        or latest.get("state_counts") != state_counts
        or state_counts != {"COMPLETED": task_count}
        or any(row["exit_code"] != "0:0" for row in rows)
    ):
        raise LaunchAuditError("V12 retained terminal poll evidence changed")
    return hashlib.sha256(terminal_raw).hexdigest(), latest_sha, latest


def seal_compute_canary() -> dict:
    launch_sha, launch_receipt, _recorded = _load_compute_launch()
    terminal_sha, poll_sha, poll = _retained_terminal_gate(
        terminal_path=COMPUTE_CANARY_TERMINAL_RECEIPT,
        poll_dir=COMPUTE_CANARY_POLL_DIR,
        expected_schema=PREFLIGHT_SCHEMA + "/compute-canary-terminal/v1",
        campaign=Source.COMPUTE_CANARY_CAMPAIGN,
        job_id=launch_receipt["job_id"],
        task_count=1,
        job_name=_canary_submission_identity(
            launch_receipt["submission_token"]
        )[0],
        poll_schema=PREFLIGHT_SCHEMA + "/compute-canary-poll/v1",
        launch_sha=launch_sha,
        launch_accepted_utc=launch_receipt["accepted_utc"],
    )
    if any(COMPUTE_CANARY_TMP_ROOT.iterdir()):
        raise LaunchAuditError("V12 compute-canary TMP root is not empty")
    shard = Source.compute_canary_shard_path(COMPUTE_CANARY_OUTPUT)
    expected_names = {
        "claim.json", "result.json", "environment.json", "complete.json",
        "candidate-0000.stdout.prefix", "candidate-0000.stderr.prefix",
        "candidate-0001.stdout.prefix", "candidate-0001.stderr.prefix",
    }
    if (
        shard.is_symlink() or not shard.is_dir()
        or stat.S_IMODE(shard.stat().st_mode) != 0o500
        or {path.name for path in shard.iterdir()} != expected_names
    ):
        raise LaunchAuditError("V12 compute-canary shard tree changed")
    payload_hashes = {
        name: hashlib.sha256(
            _regular_bytes(shard / name, "V12 compute-canary " + name)
        ).hexdigest()
        for name in sorted(expected_names)
    }
    _result_raw, result = _load_json(
        shard / "result.json", "V12 compute-canary result"
    )
    candidates = result.get("candidates")
    if (
        result.get("campaign") != Source.COMPUTE_CANARY_CAMPAIGN
        or result.get("array_task_count") != 1
        or result.get("candidate_indices") != [0, 1]
        or result.get("candidate_origin_counts")
        != {Source.COMPUTE_CANARY_ORIGIN: 2}
        or type(candidates) is not list or len(candidates) != 2
        or any(
            candidate.get("candidate_origin") != Source.COMPUTE_CANARY_ORIGIN
            or candidate.get("status") != "success"
            or candidate.get("translation_attempted") is not True
            for candidate in candidates
        )
    ):
        raise LaunchAuditError("V12 compute-canary scientific result changed")
    seal_plan = {
        "schema": PREFLIGHT_SCHEMA + "/compute-canary-seal-plan/v1",
        "campaign": Source.COMPUTE_CANARY_CAMPAIGN,
        "launch_receipt_sha256": launch_sha,
        "scheduler_terminal_receipt_sha256": terminal_sha,
        "terminal_poll_receipt_sha256": poll_sha,
        "scheduler_rows_sha256": _digest(poll["scheduler_rows"]),
        "scheduler_contract_rows_sha256": _digest(
            poll["scheduler_contract_rows"]
        ),
        "scheduler_gate_passed_before_payload_read": True,
        "payload_hashes": payload_hashes,
        "payload_hashes_sha256": _digest(payload_hashes),
    }
    seal_sha = _exclusive_json(
        COMPUTE_CANARY_SEAL_PLAN, seal_plan, "V12 compute-canary seal plan"
    )
    controller_sha, _controller = _load_controller_canary()
    attestation = {
        "schema": PREFLIGHT_SCHEMA + "/compute-canary-attestation/v1",
        "campaign": Source.COMPUTE_CANARY_CAMPAIGN,
        "source_repository_commit_id": launch_receipt["repository_commit_id"],
        "code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "controller_publisher_canary_receipt_sha256": controller_sha,
        "compute_canary_launch_receipt_sha256": launch_sha,
        "compute_canary_terminal_poll_receipt_sha256": poll_sha,
        "compute_canary_seal_plan_sha256": seal_sha,
        "candidate_indices": [0, 1],
        "candidate_origins": [Source.COMPUTE_CANARY_ORIGIN] * 2,
        "candidate_statuses": ["success", "success"],
        "exact_child_and_publication_path_passed": True,
        "compute_canary_passed": True,
    }
    attestation_sha = _exclusive_json(
        COMPUTE_CANARY_ATTESTATION, attestation,
        "V12 compute-canary attestation",
    )
    authorization = {
        "schema": PREFLIGHT_SCHEMA + "/authorization/v1",
        "campaign": "v12-preflight",
        "controller_publisher_canary_receipt_sha256": controller_sha,
        "compute_canary_launch_receipt_sha256": launch_sha,
        "compute_canary_terminal_poll_receipt_sha256": poll_sha,
        "compute_canary_seal_plan_sha256": seal_sha,
        "compute_canary_attestation_sha256": attestation_sha,
        "code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "source_repository_commit_id": launch_receipt[
            "repository_commit_id"
        ],
        "scheduler_gate_passed_before_payload_read": True,
        "controller_lustre_publication_passed": True,
        "compute_canary_passed": True,
        "full_launch_authorized": True,
    }
    authorization_sha = _exclusive_json(
        PREFLIGHT_AUTHORIZATION, authorization, "V12 preflight authorization"
    )
    summary = {
        "compute_canary_attestation_sha256": attestation_sha,
        "preflight_authorization_sha256": authorization_sha,
        "full_launch_authorized_after_commit_and_snapshot_consume": True,
        "scheduler_queries_during_seal": 0,
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return summary


def seal() -> None:
    launch_sha, receipt = _load_launch()
    terminal_sha, poll_sha, poll = _retained_terminal_gate(
        terminal_path=FULL_TERMINAL_RECEIPT, poll_dir=FULL_POLL_DIR,
        expected_schema=EXECUTION_SCHEMA + "/terminal/v1",
        campaign="v12-full-census", job_id=receipt["job_id"],
        task_count=ARRAY_TASKS,
        job_name=_submission_identity(receipt["submission_token"])[0],
        poll_schema=POLL_SCHEMA,
        launch_sha=launch_sha,
        launch_accepted_utc=receipt["accepted_utc"],
    )
    Source.seal_campaign(
        launch_sha=launch_sha, launch_receipt=receipt,
        scheduler_rows=poll["scheduler_rows"],
        scheduler_contract_rows=poll["scheduler_contract_rows"],
        scheduler_terminal_receipt_sha256=terminal_sha,
        terminal_poll_receipt_sha256=poll_sha,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "prepare-manifest", "controller-canary", "launch-canary",
        "poll-canary", "seal-canary", "launch", "recover-launch",
        "poll", "seal",
    ))
    command = parser.parse_args(argv).command
    {
        "prepare-manifest": prepare_manifest,
        "controller-canary": controller_publication_canary,
        "launch-canary": launch_compute_canary,
        "poll-canary": poll_compute_canary,
        "seal-canary": seal_compute_canary,
        "launch": launch,
        "recover-launch": recover_launch,
        "poll": poll_full,
        "seal": seal,
    }[command]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LaunchAuditError, Source.SourceAuditError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
