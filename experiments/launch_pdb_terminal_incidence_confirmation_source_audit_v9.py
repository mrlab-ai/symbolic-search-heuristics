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
import shlex
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources_v9 as Source


class LaunchAuditError(RuntimeError):
    pass


SCHEMA = Source.SCHEMA
LAUNCH_SCHEMA = SCHEMA + "/launch/v1"
EXECUTION_SCHEMA = SCHEMA + "/execution/v1"
SBATCH_RESULT_SCHEMA = LAUNCH_SCHEMA + "/sbatch-result/v1"

ARTIFACT_DIR = Source.ARTIFACT_DIR
INTENT = ARTIFACT_DIR / "source-audit-launch-intent-v9.json"
SBATCH_STDOUT = ARTIFACT_DIR / "source-audit-sbatch-stdout-v9.bin"
SBATCH_STDERR = ARTIFACT_DIR / "source-audit-sbatch-stderr-v9.bin"
SBATCH_RESULT = ARTIFACT_DIR / "source-audit-sbatch-result-v9.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-launch-receipt-v9.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v9.json"
SLURM_TEMPLATE = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v9.slurm"
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

PYTHON_COMMAND = (
    SCRIPT_DIR / "data" / "pdb-terminal-incidence-shadow-venv" /
    "bin" / "python"
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
JJ_COMMAND = Path("/home/jendrik/bin/jj")
JJ_COMMAND_SHA256 = (
    "d1d69a0f87df266eebf0d2592dd019eb288c300b15fd019afe26cb1ed11ba152"
)

SUBMISSION_ENVIRONMENT = {
    "LANG": "C", "LC_ALL": "C", "PATH": CONTROLLED_PATH,
}
JOB_NAME_PREFIX = "pdb-source-v9"
COMMENT_PREFIX = "pdb-source-v9"

MANIFEST_PLACEHOLDER = b"__V9_CODE_MANIFEST_SHA256__"
INVENTORY_PLACEHOLDER = b"__V9_SOURCE_INVENTORY_SHA256__"
COMMIT_PLACEHOLDER = b"__V9_REPOSITORY_COMMIT_ID__"
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
    try:
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
    except LaunchAuditError:
        raise
    except OSError as err:
        raise LaunchAuditError("cannot publish {}".format(label)) from err
    finally:
        os.close(descriptor)
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
    def __init__(self) -> None:
        self._descriptors: dict[str, int] = {}
        self.initial_identities: dict[str, dict] = {}

    def __enter__(self):
        flags = (
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC |
            getattr(os, "O_NOFOLLOW", 0)
        )
        try:
            for stream, path in (
                ("stdout", SBATCH_STDOUT), ("stderr", SBATCH_STDERR),
            ):
                descriptor = os.open(path, flags, 0o400)
                os.fchmod(descriptor, 0o400)
                self._descriptors[stream] = descriptor
                identity = _capture_identity(path, descriptor, initial=True)
                if identity["bytes_at_intent"] != 0:
                    raise LaunchAuditError("sbatch capture was not empty")
                self.initial_identities[stream] = identity
        except OSError as err:
            self.close()
            raise LaunchAuditError("cannot create V9 sbatch captures") from err
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
        for stream, path in (
            ("stdout", SBATCH_STDOUT), ("stderr", SBATCH_STDERR),
        ):
            if _capture_identity(
                path, self._descriptors[stream], initial=True,
            ) != self.initial_identities[stream]:
                raise LaunchAuditError("sbatch capture changed before submission")

    def finalize(self) -> tuple[dict[str, dict], dict[str, bytes]]:
        records = {}
        payloads = {}
        for stream, path in (
            ("stdout", SBATCH_STDOUT), ("stderr", SBATCH_STDERR),
        ):
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
        "experiments/audit_pdb_terminal_incidence_confirmation_sources_v9.py",
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
    raw = _regular_bytes(CODE_MANIFEST, "V9 code manifest")
    expected = _manifest_bytes()
    if raw != expected:
        raise LaunchAuditError("V9 code manifest or bound source bytes changed")
    records = []
    for line, relative in zip(raw.decode("ascii").splitlines(), _manifest_paths()):
        digest, recorded = line.split("  ", 1)
        if recorded != relative or SHA256_RE.fullmatch(digest) is None:
            raise LaunchAuditError("V9 code manifest record changed")
        records.append({"path": relative, "sha256": digest})
    return hashlib.sha256(raw).hexdigest(), records


def prepare_manifest() -> None:
    if any(os.path.lexists(path) for path in (
        CODE_MANIFEST, ARTIFACT_DIR, OUTPUT_DIR, TMP_ROOT, LOG_ROOT,
    )):
        raise LaunchAuditError("V9 prepare-manifest namespace is not empty")
    raw = _manifest_bytes()
    digest = _exclusive_bytes(CODE_MANIFEST, raw, "V9 code manifest")
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
        raise LaunchAuditError("cannot attest the committed V9 source closure") from err
    if (
        changed or tracked != list(scoped)
        or COMMIT_RE.fullmatch(commit_id or "") is None
    ):
        raise LaunchAuditError("V9 requires every bound file committed at @-")
    _load_code_manifest()
    _executable_identity(JJ_COMMAND, JJ_COMMAND_SHA256, "jj")
    return commit_id


def _build_inventory() -> tuple[bytes, str]:
    value = Source.build_inventory_manifest(Source.DEFAULT_BENCHMARKS)
    records = Source.validate_inventory_manifest(value)
    if type(records) is not list or len(records) != CANDIDATE_COUNT:
        raise LaunchAuditError("V9 inventory does not contain the full census")
    raw = Source.canonical_json(value)
    if type(raw) is not bytes:
        raise LaunchAuditError("V9 inventory encoder is not canonical")
    try:
        decoded = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise LaunchAuditError("V9 inventory encoder is not canonical") from err
    if (
        decoded != value or Source.canonical_json(decoded) != raw
    ):
        raise LaunchAuditError("V9 inventory encoder is not canonical")
    return raw, hashlib.sha256(raw).hexdigest()


def _slurm_template() -> bytes:
    raw = _regular_bytes(SLURM_TEMPLATE, "V9 Slurm template")
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise LaunchAuditError("V9 Slurm template is not ASCII") from err
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
        raise LaunchAuditError("V9 Slurm resource or execution contract changed")
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
        raise LaunchAuditError("V9 Slurm binding is invalid")
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
        raise LaunchAuditError("V9 Slurm binding remained incomplete")
    return rendered


def _submission_identity(token: str) -> tuple[str, str]:
    if not isinstance(token, str) or TOKEN_RE.fullmatch(token) is None:
        raise LaunchAuditError("V9 submission token is invalid")
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
        raise LaunchAuditError("V9 source/launcher path or cardinality contract changed")


def _assert_namespace_empty() -> None:
    if any(os.path.lexists(path) for path in (
        ARTIFACT_DIR, OUTPUT_DIR, TMP_ROOT, LOG_ROOT,
    )):
        raise LaunchAuditError("V9 one-shot launch namespace is not empty")


def _launch_materials(
    *, repository_commit_id: str, code_manifest_sha256: str,
    code_records: list[dict], inventory_sha256: str, rendered: bytes,
    root_identities: dict, capture_initial_identities: dict,
) -> dict:
    return {
        "campaign": "v9-full-census",
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
        raise LaunchAuditError("V9 sbatch result input changed")
    for stream in ("stdout", "stderr"):
        if (
            records[stream].get("sha256")
            != hashlib.sha256(payloads[stream]).hexdigest()
            or records[stream].get("bytes") != len(payloads[stream])
        ):
            raise LaunchAuditError("V9 sbatch capture record changed")
    if recovered:
        if completed is not None or error is not None:
            raise LaunchAuditError("V9 recovery process observation changed")
        process = {
            "kind": "controller-crash-returncode-unavailable",
            "returncode": None, "os_error_type": None, "os_error_errno": None,
        }
    elif completed is not None and error is None:
        if type(completed.returncode) is not int:
            raise LaunchAuditError("V9 sbatch return code changed")
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
        raise LaunchAuditError("V9 sbatch process observation changed")
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
    digest = _exclusive_json(SBATCH_RESULT, result, "V9 sbatch result")
    return digest, result


def _capture_records_from_disk(intent: dict) -> tuple[dict[str, dict], dict[str, bytes]]:
    expected = intent.get("sbatch_capture_initial_identities")
    if type(expected) is not dict or set(expected) != {"stdout", "stderr"}:
        raise LaunchAuditError("V9 capture identities changed")
    records = {}
    payloads = {}
    for stream, path in (("stdout", SBATCH_STDOUT), ("stderr", SBATCH_STDERR)):
        raw = _regular_bytes(path, "V9 sbatch " + stream)
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
            raise LaunchAuditError("V9 sbatch capture identity changed")
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
    raw, result = _load_json(SBATCH_RESULT, "V9 sbatch result")
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
        raise LaunchAuditError("V9 sbatch result changed")
    return hashlib.sha256(raw).hexdigest(), result


def _validate_root_identities(value: dict) -> None:
    paths = {
        "artifact_dir": ARTIFACT_DIR,
        "log_root": LOG_ROOT,
        "output_dir": OUTPUT_DIR,
        "tmpdir_root": TMP_ROOT,
    }
    if type(value) is not dict or set(value) != set(paths):
        raise LaunchAuditError("V9 launch-root identities changed")
    for name, path in paths.items():
        if value[name] != _directory_identity(path, "V9 " + name):
            raise LaunchAuditError("V9 launch root was replaced")


def _load_intent_only() -> tuple[bytes, dict]:
    raw, intent = _load_json(INTENT, "V9 launch intent")
    token = intent.get("submission_token")
    commit_id = intent.get("repository_commit_id")
    manifest_sha, records = _load_code_manifest()
    inventory_raw = _regular_bytes(SOURCE_INVENTORY, "V9 source inventory")
    inventory_sha = hashlib.sha256(inventory_raw).hexdigest()
    rendered = _render_slurm(manifest_sha, inventory_sha, commit_id)
    slurm = intent.get("slurm_program")
    source_inventory = intent.get("source_inventory")
    code_manifest = intent.get("code_manifest")
    recorded = intent.get("recorded_utc")
    try:
        timestamp = datetime.datetime.fromisoformat(recorded)
    except (TypeError, ValueError) as err:
        raise LaunchAuditError("V9 launch timestamp changed") from err
    if timestamp.tzinfo is None:
        raise LaunchAuditError("V9 launch timestamp lacks a timezone")
    expected_keys = {
        "schema", "campaign", "recorded_utc", "submission_token",
        "repository_commit_id", "resource_profile", "array_mapping",
        "source_inventory", "source_inventory_sha256", "code_manifest",
        "code_manifest_sha256", "slurm_program", "root_identities",
        "execution_environment", "capture_protocol",
        "sbatch_capture_initial_identities", "submit_command",
        *ZERO_PRIOR_PAYLOAD,
    }
    if (
        set(intent) != expected_keys
        or intent.get("schema") != LAUNCH_SCHEMA + "/intent"
        or intent.get("campaign") != "v9-full-census"
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
        or any(intent.get(key) != value for key, value in ZERO_PRIOR_PAYLOAD.items())
    ):
        raise LaunchAuditError("V9 launch intent changed")
    _validate_root_identities(intent.get("root_identities"))
    _capture_records_from_disk(intent)
    return raw, intent


def _receipt_value(
    intent_raw: bytes, intent: dict, sbatch_result_sha256: str,
    job_id: str, *, recovered: bool, recovery_evidence: dict | None,
) -> dict:
    return {
        "schema": LAUNCH_SCHEMA, "campaign": "v9-full-census",
        "job_id": job_id, "submission_token": intent["submission_token"],
        "repository_commit_id": intent["repository_commit_id"],
        "source_inventory_sha256": intent["source_inventory_sha256"],
        "code_manifest_sha256": intent["code_manifest_sha256"],
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "sbatch_result_sha256": sbatch_result_sha256,
        "resource_profile": _resource_profile(),
        "root_identities": intent["root_identities"],
        "slurm_program": intent["slurm_program"],
        "launch_recovered": recovered,
        "recovery_evidence": recovery_evidence,
        **ZERO_PRIOR_PAYLOAD,
    }


def _write_launch_receipt(
    intent_raw: bytes, intent: dict, job_id: str, *,
    recovered: bool, recovery_evidence: dict | None,
) -> str:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("Slurm returned an invalid V9 job id")
    result_sha, result = _load_sbatch_result(intent_raw, intent)
    parsed = result["parsed_job_id"]
    if not recovered:
        if (
            result["accepted_by_launcher"] is not True
            or parsed != job_id or recovery_evidence is not None
        ):
            raise LaunchAuditError("V9 sbatch result did not authorize launch")
    elif (
        type(recovery_evidence) is not dict
        or recovery_evidence.get("job_id") != job_id
        or (parsed is not None and parsed != job_id)
    ):
        raise LaunchAuditError("V9 recovery evidence disagrees with launch")
    receipt = _receipt_value(
        intent_raw, intent, result_sha, job_id,
        recovered=recovered, recovery_evidence=recovery_evidence,
    )
    return _exclusive_json(LAUNCH_RECEIPT, receipt, "V9 launch receipt")


def _load_launch() -> tuple[str, dict]:
    intent_raw, intent = _load_intent_only()
    result_sha, result = _load_sbatch_result(intent_raw, intent)
    raw, receipt = _load_json(LAUNCH_RECEIPT, "V9 launch receipt")
    job_id = receipt.get("job_id")
    recovered = receipt.get("launch_recovered")
    evidence = receipt.get("recovery_evidence")
    expected = _receipt_value(
        intent_raw, intent, result_sha, job_id,
        recovered=recovered, recovery_evidence=evidence,
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
        raise LaunchAuditError("V9 launch receipt changed")
    return hashlib.sha256(raw).hexdigest(), receipt


def launch() -> None:
    _assert_source_contract()
    _assert_namespace_empty()
    code_manifest_sha, code_records = _load_code_manifest()
    repository_commit_id = _repository_commit()
    inventory_raw, inventory_sha = _build_inventory()
    rendered = _render_slurm(
        code_manifest_sha, inventory_sha, repository_commit_id,
    )
    output_identity = _create_private_directory(OUTPUT_DIR, "V9 output directory")
    tmp_identity = _create_private_directory(TMP_ROOT, "V9 TMPDIR root")
    log_identity = _create_private_directory(LOG_ROOT, "V9 scheduler-log root")
    artifact_identity = _create_private_directory(ARTIFACT_DIR, "V9 artifact directory")
    _exclusive_bytes(SOURCE_INVENTORY, inventory_raw, "V9 source inventory")
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
        )
        intent = {
            "schema": LAUNCH_SCHEMA + "/intent", **materials,
            "recorded_utc": datetime.datetime.now(
                datetime.timezone.utc,
            ).isoformat(timespec="seconds"),
            "submission_token": token, "submit_command": command,
        }
        intent_raw = _canonical_json(intent)
        _exclusive_json(INTENT, intent, "V9 launch intent")
        rerendered = _render_slurm(
            code_manifest_sha, inventory_sha, repository_commit_id,
        )
        if rerendered != rendered:
            raise LaunchAuditError("V9 rendered Slurm bytes changed before submission")
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
                "V9 sbatch was not accepted; raw streams are bound by " + result_sha
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


def _sacct(command: list[str]) -> str:
    _executable_identity(SACCT_COMMAND, SACCT_COMMAND_SHA256, "sacct")
    try:
        return subprocess.check_output(
            command, cwd=REPO, env=dict(SUBMISSION_ENVIRONMENT), text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot query V9 accounting") from err


def _submission_journal(intent: dict) -> dict:
    name, comment = _submission_identity(intent["submission_token"])
    recorded = datetime.datetime.fromisoformat(intent["recorded_utc"])
    output = _sacct([
        str(SACCT_COMMAND), "-X", "--array", "-S", recorded.date().isoformat(),
        "--name=" + name, "-n", "-P",
        "--format=JobID%64,JobName%128,Comment%128,SubmitLine%4096",
    ])
    rows = []
    parents = set()
    for line in output.splitlines():
        fields = line.split("|", 3)
        if len(fields) != 4:
            raise LaunchAuditError("V9 submission journal row changed")
        job_id, actual_name, actual_comment, submit_line = fields
        if actual_name != name and actual_comment != comment:
            continue
        try:
            command = shlex.split(submit_line)
        except ValueError as err:
            raise LaunchAuditError("V9 submission journal command is invalid") from err
        if command and command[0] == SBATCH_COMMAND.name:
            command[0] = str(SBATCH_COMMAND)
        match = re.fullmatch(r"([0-9]+)(?:_[0-9]+|_\[[^]]+\])?", job_id)
        if (
            match is None or actual_name != name
            or actual_comment not in ("", comment)
            or command != intent["submit_command"]
        ):
            raise LaunchAuditError("V9 submission identity collided")
        parents.add(match.group(1))
        rows.append({
            "job_id": job_id, "job_name": actual_name,
            "comment": actual_comment, "submit_command": command,
        })
    if len(parents) != 1 or not rows:
        raise LaunchAuditError(
            "submission journal does not identify exactly one V9 job; "
            "refusing resubmission"
        )
    parent = next(iter(parents))
    return {
        "source": "scheduler-submission-journal",
        "job_id": parent, "rows": rows, "rows_sha256": _digest(rows),
        "no_resubmission": True,
    }


def _recovery_evidence(intent: dict, result: dict) -> dict:
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
            "no_resubmission": True,
        }
    journal = _submission_journal(intent)
    if parsed is not None and parsed != journal["job_id"]:
        raise LaunchAuditError(
            "uncertain V9 stdout and submission journal disagree; "
            "refusing resubmission"
        )
    if parsed is not None:
        journal = {
            **journal,
            "uncertain_stdout_job_id": parsed,
            "uncertain_stdout_sha256": result["stdout"]["sha256"],
        }
    return journal


def recover_launch() -> None:
    if os.path.lexists(LAUNCH_RECEIPT):
        raise LaunchAuditError("V9 launch receipt already exists")
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


def _scheduler_rows(job_id: str) -> list[dict]:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("V9 scheduler query has an invalid job id")
    output = _sacct([
        str(SACCT_COMMAND), "-j", job_id, "-X", "--array", "-n", "-P",
        "--format=JobID,State,ExitCode,Partition,Restarts",
    ])
    rows = []
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 5:
            raise LaunchAuditError("V9 scheduler row changed")
        task_id, state, exit_code, partition, restarts = fields
        match = re.fullmatch(re.escape(job_id) + r"_([0-9]+)", task_id)
        if (
            match is None or state not in ACTIVE_STATES | TERMINAL_STATES
            or EXIT_CODE_RE.fullmatch(exit_code) is None
            or partition != PARTITION or not restarts.isdigit()
        ):
            raise LaunchAuditError("V9 scheduler field changed")
        rows.append({
            "array_task": int(match.group(1)), "state": state,
            "exit_code": exit_code, "partition": partition,
            "restarts": int(restarts),
        })
    rows.sort(key=lambda row: row["array_task"])
    if (
        len(rows) != ARRAY_TASKS
        or [row["array_task"] for row in rows] != list(range(ARRAY_TASKS))
        or any(row["restarts"] != 0 for row in rows)
    ):
        raise LaunchAuditError("V9 scheduler array or restart contract changed")
    return rows


def _require_all_success(rows: list[dict]) -> None:
    if (
        type(rows) is not list or len(rows) != ARRAY_TASKS
        or [row.get("array_task") for row in rows] != list(range(ARRAY_TASKS))
        or any(
            set(row) != {
                "array_task", "state", "exit_code", "partition", "restarts",
            }
            or row["state"] != "COMPLETED" or row["exit_code"] != "0:0"
            or row["partition"] != PARTITION or row["restarts"] != 0
            for row in rows
        )
    ):
        raise LaunchAuditError(
            "V9 outer array is not entirely successful; payload reads forbidden"
        )


def _scheduler_contract_rows(
    job_id: str, launch_receipt: dict, rows: list[dict],
) -> list[dict]:
    _require_all_success(rows)
    output = _sacct([
        str(SACCT_COMMAND), "-j", job_id, "-X", "--array", "-n", "-P",
        "--format=JobID,Account,Partition,QOS,ReqCPUS,ReqMem,Timelimit,"
        "State,ExitCode,Restarts,JobName",
    ])
    name, _comment = _submission_identity(launch_receipt["submission_token"])
    result = []
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 11:
            raise LaunchAuditError("V9 scheduler resource row changed")
        (
            task_id, account, partition, qos, cpus, memory, time_limit,
            state, exit_code, restarts, job_name,
        ) = fields
        match = re.fullmatch(re.escape(job_id) + r"_([0-9]+)", task_id)
        if (
            match is None or account != ACCOUNT or partition != PARTITION
            or qos != QOS or cpus != "1" or memory != MEMORY
            or time_limit != TIME_LIMIT or state != "COMPLETED"
            or exit_code != "0:0" or restarts != "0" or job_name != name
        ):
            raise LaunchAuditError("V9 actual scheduler resource contract changed")
        result.append({
            "array_task": int(match.group(1)), "account": account,
            "partition": partition, "qos": qos, "req_cpus": 1,
            "req_mem": memory, "time_limit": time_limit,
            "state": state, "exit_code": exit_code,
            "restarts": 0, "job_name": job_name,
        })
    result.sort(key=lambda row: row["array_task"])
    if (
        len(result) != ARRAY_TASKS
        or [row["array_task"] for row in result] != list(range(ARRAY_TASKS))
    ):
        raise LaunchAuditError("V9 scheduler resource-array cardinality changed")
    return result


def status() -> tuple[str, dict, list[dict]]:
    launch_sha, receipt = _load_launch()
    rows = _scheduler_rows(receipt["job_id"])
    print(json.dumps({
        "job_id": receipt["job_id"],
        "state_counts": dict(Counter(row["state"] for row in rows)),
        "all_success": all(
            row["state"] == "COMPLETED" and row["exit_code"] == "0:0"
            for row in rows
        ),
    }, sort_keys=True, indent=2))
    return launch_sha, receipt, rows


def scheduler_gate() -> tuple[str, dict, list[dict], list[dict]]:
    launch_sha, receipt = _load_launch()
    rows = _scheduler_rows(receipt["job_id"])
    _require_all_success(rows)
    contracts = _scheduler_contract_rows(receipt["job_id"], receipt, rows)
    return launch_sha, receipt, rows, contracts


def seal() -> None:
    launch_sha, receipt, rows, contracts = scheduler_gate()
    Source.seal_campaign(
        launch_sha=launch_sha, launch_receipt=receipt,
        scheduler_rows=rows, scheduler_contract_rows=contracts,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "prepare-manifest", "launch", "recover-launch", "status", "seal",
    ))
    command = parser.parse_args(argv).command
    {
        "prepare-manifest": prepare_manifest,
        "launch": launch,
        "recover-launch": recover_launch,
        "status": status,
        "seal": seal,
    }[command]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LaunchAuditError, Source.SourceAuditError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
