#!/usr/bin/env python3
"""Run full source-audit campaign v4 with project-backed temporary files."""

from __future__ import annotations

import importlib.util
import hashlib
import os
import re
import stat
import sys
import tempfile
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
BASE_SOURCE = SCRIPT_DIR / "audit_pdb_terminal_incidence_confirmation_sources.py"
_MODULE_NAME = "_pdb_terminal_incidence_confirmation_source_audit_v4_base"


def _load_base():
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, BASE_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen source-audit implementation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


Base = _load_base()

CAMPAIGN = "v4"
TASK_TIMEOUT_SECONDS = 14400
DEFAULT_SHARDS = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v4"
)
DEFAULT_INVENTORY = DEFAULT_SHARDS / "source-inventory-v4.json"
DEFAULT_OUTPUT = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v4.json"
)
DEFAULT_CODE_MANIFEST = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256"
)
TMP_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v4_tmp"
)
TMPDIR_TEMPLATE = str(TMP_ROOT / "task-{array_job_id}-{array_task_id}")
PYTHON_CACHE_PREFIX_TEMPLATE = TMPDIR_TEMPLATE + "/pycache"
TASK_ENVIRONMENT_SCHEMA = Base.SCHEMA + "/campaign-v4/task-environment/v1"
SOURCE_SNAPSHOT_SCHEMA = Base.SCHEMA + "/campaign-v4/source-snapshot/v1"
SOURCE_SNAPSHOT_POLICY = {
    "scope": "one domain/problem snapshot tree per candidate",
    "location": "inside the exact per-array-task TMPDIR",
    "directory_mode": "0700",
    "file_mode": "0400",
    "consumers": ["translator", "axiom_based normalization"],
    "verify_before_each_consumer": True,
    "verify_identity_and_sha256_after_use": True,
    "cleanup": "unlink exact files, then rmdir exact directories; no recursion",
}
SHA256SUM_COMMAND = Path("/usr/bin/sha256sum")
SHA256SUM_SHA256 = (
    "1950eda10a1bb0c6c2a086ba009b847edec6f30d25eb311b9154ae08819041a9"
)
MKDIR_COMMAND = Path("/usr/bin/mkdir")
MKDIR_SHA256 = (
    "9a71255933f2013dda3fe7e8ad928dc50b7e4c2ae6a7cac58fc1225106c10814"
)
RMDIR_COMMAND = Path("/usr/bin/rmdir")
RMDIR_SHA256 = (
    "b87fd3112c40dd30dca11fa5bc1b3dacc9ed2e309868344dd696824abafc5ded"
)
V3_DIAGNOSTIC = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v4" /
    "v3-infrastructure-failure-diagnostic.json"
)

# These dependencies include all 14 v3 manifest-bound producer files, the v3
# manifest and Slurm script, and the exact launch intent/receipt.  Campaign v4
# therefore cannot silently reinterpret or replace any v3 launch/source byte.
CODE_MANIFEST_FILES = (
    "experiments/artifacts/pdb-terminal-incidence-confirmation/"
    "source-audit-launch-receipt-v1.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v2/"
    "source-audit-launch-receipt-v2.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v3/"
    "source-audit-launch-intent-v3.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v3/"
    "source-audit-launch-receipt-v3.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
    "v3-infrastructure-failure-diagnostic.json",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v3.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v4.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v4.py",
    "experiments/pdb_terminal_incidence_confirmation_inventory.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v3_code.sha256",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v3_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v3.slurm",
    "experiments/pdb_terminal_incidence_shadow_cost_attestation.json",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit_v4.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/suite_wbh_operator_costs.json",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v4.py",
)


for _name, _value in {
    "TASK_TIMEOUT_SECONDS": TASK_TIMEOUT_SECONDS,
    "DEFAULT_SHARDS": DEFAULT_SHARDS,
    "DEFAULT_INVENTORY": DEFAULT_INVENTORY,
    "DEFAULT_OUTPUT": DEFAULT_OUTPUT,
    "DEFAULT_CODE_MANIFEST": DEFAULT_CODE_MANIFEST,
    "PYTHON_CACHE_PREFIX_TEMPLATE": PYTHON_CACHE_PREFIX_TEMPLATE,
    "CODE_MANIFEST_FILES": CODE_MANIFEST_FILES,
}.items():
    setattr(Base, _name, _value)


SourceAuditError = Base.SourceAuditError
InfrastructureAuditError = Base.InfrastructureAuditError


def task_environment_path(
    directory: Path, index: int, count: int = Base.SHARD_COUNT
) -> Path:
    return Path(directory) / "environment-{:04d}-of-{:04d}.json".format(
        index, count
    )


def _assert_no_symlink_components(path: Path, label: str) -> None:
    path = Path(path)
    if not path.is_absolute() or path != Path(os.path.normpath(path)):
        raise SourceAuditError("{} path is not canonical absolute".format(label))
    current = Path(path.anchor)
    try:
        for part in path.parts[1:]:
            current /= part
            if stat.S_ISLNK(current.lstat().st_mode):
                raise SourceAuditError(
                    "{} has a symlink path component".format(label)
                )
    except FileNotFoundError as err:
        raise SourceAuditError("cannot inspect {} path".format(label)) from err
    except OSError as err:
        raise SourceAuditError("cannot inspect {} path".format(label)) from err


def _directory_identity(path: Path, label: str) -> dict:
    path = Path(path)
    _assert_no_symlink_components(path, label)
    try:
        before = path.lstat()
        resolved = path.resolve(strict=True)
        after = path.lstat()
    except OSError as err:
        raise SourceAuditError("cannot inspect {}".format(label)) from err
    if (
        path.is_symlink()
        or resolved != path
        or not stat.S_ISDIR(after.st_mode)
        or stat.S_IMODE(after.st_mode) != 0o700
        or after.st_uid != os.getuid()
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
    ):
        raise SourceAuditError("{} identity changed".format(label))
    return {
        "path": str(path),
        "canonical_path": str(resolved),
        "device": after.st_dev,
        "inode": after.st_ino,
        "mode": "0700",
        "uid": after.st_uid,
    }


def _require_directory_identity(
    path: Path, expected: dict, label: str
) -> dict:
    actual = _directory_identity(path, label)
    if actual != expected:
        raise SourceAuditError("{} was replaced".format(label))
    return actual


def _array_identity() -> tuple[str, int]:
    array_job_id = os.environ.get("SLURM_ARRAY_JOB_ID")
    raw_task = os.environ.get("SLURM_ARRAY_TASK_ID")
    if (
        not isinstance(array_job_id, str)
        or not array_job_id.isdigit()
        or not isinstance(raw_task, str)
        or not raw_task.isdigit()
    ):
        raise SourceAuditError("source-audit Slurm identity is invalid")
    array_task_id = int(raw_task)
    if not 0 <= array_task_id < Base.SHARD_COUNT:
        raise SourceAuditError("source-audit array task is out of range")
    return array_job_id, array_task_id


def _expected_tmpdir(array_job_id: str, array_task_id: int) -> Path:
    return Path(TMPDIR_TEMPLATE.format(
        array_job_id=array_job_id,
        array_task_id=array_task_id,
    ))


_base_validate_execution_environment = Base.validate_execution_environment


def validate_execution_environment() -> None:
    _base_validate_execution_environment()
    array_job_id, array_task_id = _array_identity()
    expected = _expected_tmpdir(array_job_id, array_task_id)
    if (
        not expected.is_absolute()
        or expected.parent != TMP_ROOT
        or os.environ.get("TMPDIR") != str(expected)
    ):
        raise SourceAuditError("source-audit TMPDIR path changed")
    _directory_identity(TMP_ROOT, "source-audit TMPDIR root")
    _directory_identity(expected, "source-audit per-task TMPDIR")
    try:
        if any(expected.iterdir()):
            raise SourceAuditError("source-audit per-task TMPDIR is not empty")
    except OSError as err:
        raise SourceAuditError("cannot inspect source-audit TMPDIR") from err
    tempfile.tempdir = None
    if Path(tempfile.gettempdir()) != expected:
        raise SourceAuditError("Python tempfile did not select frozen TMPDIR")


Base.validate_execution_environment = validate_execution_environment


_base_subprocess_run = Base.subprocess.run
_base_count_normalized_axioms = Base._count_normalized_axioms
_base_scan_task = Base._scan_task
_base_load_shard = Base._load_shard
_active_source_snapshot = None


def _snapshot_file_identity(
    path: Path, expected_sha256: str, label: str
) -> dict:
    try:
        before = path.lstat()
        digest = Base.sha256_file(path)
        after = path.lstat()
    except OSError as err:
        raise SourceAuditError("cannot inspect {}".format(label)) from err
    if (
        path.is_symlink()
        or not stat.S_ISREG(after.st_mode)
        or stat.S_IMODE(after.st_mode) != 0o400
        or after.st_uid != os.getuid()
        or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino)
        or before.st_size != after.st_size
        or digest != expected_sha256
    ):
        raise SourceAuditError("{} identity or bytes changed".format(label))
    return {
        "device": after.st_dev,
        "inode": after.st_ino,
        "mode": "0400",
        "uid": after.st_uid,
        "bytes": after.st_size,
        "sha256": digest,
    }


def _verify_active_source_snapshot(consumer: str, paths: tuple[Path, Path]) -> None:
    context = _active_source_snapshot
    if not isinstance(context, dict):
        raise SourceAuditError("source snapshot consumer has no active snapshot")
    expected_paths = (context["domain_path"], context["problem_path"])
    if tuple(map(Path, paths)) != expected_paths:
        raise SourceAuditError("{} source snapshot paths changed".format(consumer))
    for role, path in zip(("domain", "problem"), expected_paths):
        expected = context["files_by_role"][role]
        identity = _snapshot_file_identity(
            path, expected["sha256"], "{} {} snapshot".format(consumer, role)
        )
        if identity != expected["identity_before"]:
            raise SourceAuditError(
                "{} {} snapshot was replaced".format(consumer, role)
            )
    context[consumer + "_verified_before_use"] = True


def _subprocess_run_with_tmpdir(*args, **kwargs):
    environment = kwargs.get("env")
    expected_keys = {
        "PATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE",
        "PYTHONPYCACHEPREFIX", "PYTHONPATH",
    }
    if (
        not isinstance(environment, dict)
        or set(environment) != expected_keys
        or environment.get("PATH") != Base.CONTROLLED_PATH
        or environment.get("PYTHONNOUSERSITE") != "1"
        or environment.get("PYTHONDONTWRITEBYTECODE") != "1"
        or environment.get("PYTHONPYCACHEPREFIX")
        != os.environ.get("PYTHONPYCACHEPREFIX")
        or environment.get("PYTHONPATH") != str(REPO / "src")
        or os.environ.get("TMPDIR") is None
    ):
        raise SourceAuditError("translator child environment changed")
    command = args[0] if args else kwargs.get("args")
    if not isinstance(command, (list, tuple)) or len(command) < 2:
        raise SourceAuditError("translator command changed")
    _verify_active_source_snapshot(
        "translator", (Path(command[-2]), Path(command[-1]))
    )
    kwargs["env"] = {**environment, "TMPDIR": os.environ["TMPDIR"]}
    return _base_subprocess_run(*args, **kwargs)


# The frozen engine already places output.sas in a TemporaryDirectory.  This
# one-line environment extension also makes the translator's own tempfile
# policy explicit without copying or modifying the frozen scan implementation.
class _BaseSubprocessFacade:
    """Confine the translator hook to the frozen producer module."""

    PIPE = Base.subprocess.PIPE
    TimeoutExpired = Base.subprocess.TimeoutExpired
    run = staticmethod(_subprocess_run_with_tmpdir)


Base.subprocess = _BaseSubprocessFacade


def _count_normalized_axioms_from_snapshot(
    domain: Path, problem: Path
) -> int:
    _verify_active_source_snapshot(
        "normalization", (Path(domain), Path(problem))
    )
    return _base_count_normalized_axioms(domain, problem)


Base._count_normalized_axioms = _count_normalized_axioms_from_snapshot


def _read_frozen_source(
    benchmarks: Path, relative: str, expected_sha256: str, role: str
) -> bytes:
    source = Base._regular_source(benchmarks, relative, expected_sha256)
    try:
        payload = source.read_bytes()
    except OSError as err:
        raise SourceAuditError("cannot read frozen {} source".format(role)) from err
    if Base.sha256_file(source) != expected_sha256:
        raise SourceAuditError("frozen {} source changed while read".format(role))
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise SourceAuditError("frozen {} source bytes changed".format(role))
    return payload


def _write_snapshot_file(path: Path, payload: bytes, label: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    try:
        descriptor = os.open(path, flags, 0o400)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as err:
        raise SourceAuditError("cannot create {}".format(label)) from err
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _snapshot_relative_path(relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise SourceAuditError("unsafe source snapshot path")
    return value


def _create_snapshot_directories(root: Path, relatives: list[Path]) -> list[Path]:
    directories = {root}
    for relative in relatives:
        parent = relative.parent
        while parent != Path("."):
            directories.add(root / parent)
            parent = parent.parent
    created = []
    try:
        for directory in sorted(directories, key=lambda item: len(item.parts)):
            directory.mkdir(mode=0o700, parents=False, exist_ok=False)
            created.append(directory)
    except OSError as err:
        try:
            for directory in reversed(created):
                directory.rmdir()
        except OSError as cleanup_err:
            raise SourceAuditError(
                "cannot clean partial source snapshot directories"
            ) from cleanup_err
        raise SourceAuditError("cannot create source snapshot directory") from err
    return created


def _clean_source_snapshot(
    files: dict[Path, dict],
    directories: list[Path],
    directory_identities: dict[Path, dict],
) -> None:
    expected_paths = set(files) | set(directories)
    actual_paths = set()
    for directory in directories:
        if _directory_identity(
            directory, "source snapshot cleanup directory"
        ) != directory_identities.get(directory):
            raise SourceAuditError("source snapshot cleanup directory was replaced")
        try:
            actual_paths.update(directory.iterdir())
        except OSError as err:
            raise SourceAuditError("cannot inspect source snapshot cleanup") from err
    if actual_paths != expected_paths - {directories[0]}:
        raise SourceAuditError("source snapshot has unexpected cleanup paths")
    for path, identity in files.items():
        if _snapshot_file_identity(
            path, identity["sha256"], "source snapshot cleanup file"
        ) != identity:
            raise SourceAuditError("source snapshot cleanup file was replaced")
        try:
            path.unlink()
        except OSError as err:
            raise SourceAuditError("cannot remove source snapshot file") from err
    for directory in reversed(directories):
        try:
            directory.rmdir()
        except OSError as err:
            raise SourceAuditError("cannot remove source snapshot directory") from err


def _scan_task(record: dict, benchmarks: Path, timeout: int) -> dict:
    global _active_source_snapshot
    if _active_source_snapshot is not None:
        raise SourceAuditError("nested source snapshot is forbidden")
    raw_index = record.get("candidate_index")
    if type(raw_index) is not int or raw_index < 0:
        raise SourceAuditError("source snapshot candidate identity changed")
    task_tmp = Path(os.environ.get("TMPDIR", ""))
    if not task_tmp.is_absolute():
        raise SourceAuditError("source snapshot TMPDIR changed")
    snapshot_root = task_tmp / "source-snapshot-{:04d}".format(raw_index)
    entries = [
        (
            "domain", record["domain_file"], record["domain_sha256"],
        ),
        (
            "problem", record["problem_file"], record["problem_sha256"],
        ),
    ]
    relative_paths = [_snapshot_relative_path(item[1]) for item in entries]
    payloads = {
        role: _read_frozen_source(benchmarks, relative, digest, role)
        for role, relative, digest in entries
    }
    directories = []
    directory_before = {}
    files_by_path = {}
    files_by_role = {}
    try:
        directories = _create_snapshot_directories(snapshot_root, relative_paths)
        directory_before = {
            path: _directory_identity(path, "source snapshot directory")
            for path in directories
        }
        for (role, relative, digest), relative_path in zip(entries, relative_paths):
            path = snapshot_root / relative_path
            if path not in files_by_path:
                _write_snapshot_file(
                    path, payloads[role], "{} source snapshot".format(role)
                )
                files_by_path[path] = _snapshot_file_identity(
                    path, digest, "{} source snapshot".format(role)
                )
            elif files_by_path[path]["sha256"] != digest:
                raise SourceAuditError("aliased source snapshot hashes differ")
            files_by_role[role] = {
                "path": path,
                "source_file": relative,
                "sha256": digest,
                "identity_before": files_by_path[path],
            }
        context = {
            "domain_path": files_by_role["domain"]["path"],
            "problem_path": files_by_role["problem"]["path"],
            "files_by_role": files_by_role,
            "translator_verified_before_use": False,
            "normalization_verified_before_use": False,
        }
        _active_source_snapshot = context
        task = _base_scan_task(record, snapshot_root, timeout)
        translation_succeeded = task["translation"]["status"] == "success"
        if (
            context["translator_verified_before_use"] is not True
            or context["normalization_verified_before_use"]
            is not translation_succeeded
        ):
            raise SourceAuditError("source snapshot consumer verification changed")
        directory_after = {
            path: _directory_identity(path, "source snapshot directory")
            for path in directories
        }
        if directory_after != directory_before:
            raise SourceAuditError("source snapshot directory was replaced")
        evidence_files = []
        for role in ("domain", "problem"):
            item = files_by_role[role]
            after = _snapshot_file_identity(
                item["path"], item["sha256"], "{} source snapshot".format(role)
            )
            if after != item["identity_before"]:
                raise SourceAuditError("{} source snapshot was replaced".format(role))
            evidence_files.append({
                "role": role,
                "source_file": item["source_file"],
                "snapshot_file": item["path"].relative_to(snapshot_root).as_posix(),
                "bytes": after["bytes"],
                "sha256": item["sha256"],
                "identity_before": item["identity_before"],
                "identity_after": after,
            })
        evidence = {
            "schema": SOURCE_SNAPSHOT_SCHEMA,
            "policy": SOURCE_SNAPSHOT_POLICY,
            "snapshot_root_name": snapshot_root.name,
            "snapshot_root_identity_before": directory_before[snapshot_root],
            "snapshot_root_identity_after": directory_after[snapshot_root],
            "files": evidence_files,
            "translator_verified_before_use": True,
            "normalization_applicable": translation_succeeded,
            "normalization_verified_before_use": translation_succeeded,
            "identity_and_sha256_verified_after_use": True,
            "exact_files_removed": True,
            "exact_directories_removed": True,
        }
    finally:
        _active_source_snapshot = None
        if directories:
            _clean_source_snapshot(
                files_by_path, directories, directory_before
            )
    return {**task, "source_snapshot": evidence}


Base._scan_task = _scan_task


def _valid_private_identity(value, mode: str, *, regular_file: bool) -> bool:
    expected = {"device", "inode", "mode", "uid"}
    if regular_file:
        expected |= {"bytes", "sha256"}
    else:
        expected |= {"path", "canonical_path"}
    return (
        isinstance(value, dict)
        and set(value) == expected
        and type(value.get("device")) is int
        and value["device"] >= 0
        and type(value.get("inode")) is int
        and value["inode"] > 0
        and value.get("mode") == mode
        and value.get("uid") == os.getuid()
        and (
            not regular_file
            or (
                type(value.get("bytes")) is int
                and value["bytes"] >= 0
                and Base._is_sha256(value.get("sha256"))
            )
        )
        and (
            regular_file
            or (
                isinstance(value.get("path"), str)
                and value["path"] == value.get("canonical_path")
                and Path(value["path"]).is_absolute()
            )
        )
    )


def _validate_source_snapshot(task: dict) -> None:
    value = task.get("source_snapshot")
    root_before = value.get("snapshot_root_identity_before") \
        if isinstance(value, dict) else None
    root_after = value.get("snapshot_root_identity_after") \
        if isinstance(value, dict) else None
    files = value.get("files") if isinstance(value, dict) else None
    expected_root_name = "source-snapshot-{:04d}".format(
        task.get("candidate_index", -1)
    )
    root_path = Path(root_before.get("path", "")) \
        if isinstance(root_before, dict) else Path()
    translation_succeeded = task.get("translation", {}).get("status") == "success"
    if (
        not isinstance(value, dict)
        or set(value) != {
            "schema", "policy", "snapshot_root_name",
            "snapshot_root_identity_before", "snapshot_root_identity_after",
            "files", "translator_verified_before_use",
            "normalization_applicable", "normalization_verified_before_use",
            "identity_and_sha256_verified_after_use", "exact_files_removed",
            "exact_directories_removed",
        }
        or value.get("schema") != SOURCE_SNAPSHOT_SCHEMA
        or value.get("policy") != SOURCE_SNAPSHOT_POLICY
        or value.get("snapshot_root_name") != expected_root_name
        or not _valid_private_identity(root_before, "0700", regular_file=False)
        or root_path.name != expected_root_name
        or root_path.parent.parent != TMP_ROOT
        or re.fullmatch(r"task-[0-9]+-[0-9]+", root_path.parent.name) is None
        or root_before != root_after
        or not isinstance(files, list)
        or len(files) != 2
        or value.get("translator_verified_before_use") is not True
        or value.get("normalization_applicable") is not translation_succeeded
        or value.get("normalization_verified_before_use") is not translation_succeeded
        or value.get("identity_and_sha256_verified_after_use") is not True
        or value.get("exact_files_removed") is not True
        or value.get("exact_directories_removed") is not True
    ):
        raise SourceAuditError("source snapshot evidence changed")
    expected_by_role = {
        "domain": (task.get("domain_file"), task.get("domain_sha256")),
        "problem": (task.get("problem_file"), task.get("problem_sha256")),
    }
    seen = set()
    for item in files:
        role = item.get("role") if isinstance(item, dict) else None
        before = item.get("identity_before") if isinstance(item, dict) else None
        after = item.get("identity_after") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or set(item) != {
                "role", "source_file", "snapshot_file", "bytes", "sha256",
                "identity_before", "identity_after",
            }
            or role not in expected_by_role
            or role in seen
            or (item.get("source_file"), item.get("sha256"))
            != expected_by_role[role]
            or item.get("snapshot_file") != item.get("source_file")
            or not _valid_private_identity(before, "0400", regular_file=True)
            or before != after
            or item.get("bytes") != before["bytes"]
            or item.get("sha256") != before["sha256"]
        ):
            raise SourceAuditError("source snapshot file evidence changed")
        seen.add(role)
    if seen != set(expected_by_role):
        raise SourceAuditError("source snapshot roles changed")


def _load_shard(
    path: Path,
    index: int,
    expected_records: list[dict],
    inventory_sha256: str,
    code: dict,
) -> list[dict]:
    tasks = _base_load_shard(
        path, index, expected_records, inventory_sha256, code
    )
    for task in tasks:
        _validate_source_snapshot(task)
    return tasks


Base._load_shard = _load_shard


def _tool_identity(path: Path, expected_sha256: str, label: str) -> dict:
    try:
        info = path.lstat()
    except OSError as err:
        raise SourceAuditError("cannot inspect {}".format(label)) from err
    if (
        not path.is_absolute()
        or path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or not os.access(path, os.X_OK)
        or Base.sha256_file(path) != expected_sha256
    ):
        raise SourceAuditError("{} identity changed".format(label))
    return {"path": str(path), "sha256": expected_sha256}


def scan(args) -> None:
    validate_execution_environment()
    array_job_id, array_task_id = _array_identity()
    if args.shard_index != array_task_id:
        raise SourceAuditError("Slurm and requested shard identities differ")
    tmpdir = _expected_tmpdir(array_job_id, array_task_id)
    output_dir = Path(args.output_dir)
    output_before = _directory_identity(
        output_dir, "source-audit output directory"
    )
    root_before = _directory_identity(TMP_ROOT, "source-audit TMPDIR root")
    tmp_before = _directory_identity(tmpdir, "source-audit per-task TMPDIR")
    Base.scan(args)
    code = Base.validate_code_manifest(
        args.code_manifest.resolve(),
        args.code_manifest_sha256,
        verify_environment_files=False,
    )
    root_after = _directory_identity(TMP_ROOT, "source-audit TMPDIR root")
    tmp_after = _directory_identity(tmpdir, "source-audit per-task TMPDIR")
    output_after = _directory_identity(
        output_dir, "source-audit output directory"
    )
    if (
        root_after != root_before
        or tmp_after != tmp_before
        or output_after != output_before
    ):
        raise SourceAuditError("source-audit root identity changed during scan")
    try:
        if any(tmpdir.iterdir()):
            raise SourceAuditError("source-audit TMPDIR retained task files")
    except OSError as err:
        raise SourceAuditError("cannot verify empty source-audit TMPDIR") from err
    shard = Base.shard_path(args.output_dir, args.shard_index, args.num_shards)
    value = {
        "schema": TASK_ENVIRONMENT_SCHEMA,
        "array_job_id": array_job_id,
        "array_task_id": array_task_id,
        "output_dir": str(output_dir),
        "output_dir_identity_before": output_before,
        "output_dir_identity_after": output_after,
        "tmpdir_root": str(TMP_ROOT),
        "tmpdir": str(tmpdir),
        "tempfile_gettempdir": tempfile.gettempdir(),
        "tmpdir_root_identity_before": root_before,
        "tmpdir_root_identity_after": root_after,
        "tmpdir_identity_before": tmp_before,
        "tmpdir_identity_after": tmp_after,
        "tmpdir_empty_after_scan": True,
        "python_pycache_prefix": os.environ["PYTHONPYCACHEPREFIX"],
        "path": os.environ["PATH"],
        "python_no_user_site": os.environ["PYTHONNOUSERSITE"],
        "python_dont_write_bytecode": os.environ["PYTHONDONTWRITEBYTECODE"],
        "unset_variables_absent": list(Base.UNSET_PYTHON_ENV),
        "python_no_user_site_flag": sys.flags.no_user_site,
        "python_dont_write_bytecode_flag": sys.dont_write_bytecode,
        "source_snapshot_policy": SOURCE_SNAPSHOT_POLICY,
        "source_inventory_sha256": args.inventory_sha256,
        "code_manifest_sha256": args.code_manifest_sha256,
        "shard_sha256": Base.sha256_file(shard),
        "tools": {
            "python": {
                "path": code["python_executable"],
                "sha256": code["python_executable_sha256"],
            },
            "sha256sum": _tool_identity(
                SHA256SUM_COMMAND, SHA256SUM_SHA256, "sha256sum"
            ),
            "mkdir": _tool_identity(MKDIR_COMMAND, MKDIR_SHA256, "mkdir"),
            "rmdir": _tool_identity(RMDIR_COMMAND, RMDIR_SHA256, "rmdir"),
        },
        "python_environment": code,
    }
    Base._atomic_json(
        task_environment_path(args.output_dir, args.shard_index, args.num_shards),
        value,
    )
    _require_directory_identity(
        output_dir, output_before, "source-audit output directory"
    )


def load_task_environment_attestation(
    path: Path,
    *,
    index: int,
    array_job_id: str,
    inventory_sha256: str,
    code_manifest_sha256: str,
    code: dict,
    shard_sha256: str,
) -> dict:
    _, value = Base._load_canonical_json(path, "task environment attestation")
    tmpdir = _expected_tmpdir(array_job_id, index)
    expected_keys = {
        "schema", "array_job_id", "array_task_id", "output_dir",
        "output_dir_identity_before", "output_dir_identity_after",
        "tmpdir_root", "tmpdir",
        "tempfile_gettempdir", "tmpdir_root_identity_before",
        "tmpdir_root_identity_after", "tmpdir_identity_before",
        "tmpdir_identity_after", "tmpdir_empty_after_scan",
        "python_pycache_prefix", "path", "python_no_user_site",
        "python_dont_write_bytecode", "unset_variables_absent",
        "python_no_user_site_flag", "python_dont_write_bytecode_flag",
        "source_snapshot_policy",
        "source_inventory_sha256", "code_manifest_sha256", "shard_sha256",
        "tools", "python_environment",
    }
    identities = (
        value.get("output_dir_identity_before"),
        value.get("output_dir_identity_after"),
        value.get("tmpdir_root_identity_before"),
        value.get("tmpdir_root_identity_after"),
        value.get("tmpdir_identity_before"),
        value.get("tmpdir_identity_after"),
    )
    if (
        set(value) != expected_keys
        or value.get("schema") != TASK_ENVIRONMENT_SCHEMA
        or value.get("array_job_id") != array_job_id
        or type(value.get("array_task_id")) is not int
        or value["array_task_id"] != index
        or value.get("output_dir") != str(Path(path).parent)
        or value.get("tmpdir_root") != str(TMP_ROOT)
        or value.get("tmpdir") != str(tmpdir)
        or value.get("tempfile_gettempdir") != str(tmpdir)
        or value.get("python_pycache_prefix") != str(tmpdir / "pycache")
        or value.get("tmpdir_empty_after_scan") is not True
        or value.get("path") != Base.CONTROLLED_PATH
        or value.get("python_no_user_site") != "1"
        or value.get("python_dont_write_bytecode") != "1"
        or value.get("unset_variables_absent") != list(Base.UNSET_PYTHON_ENV)
        or value.get("python_no_user_site_flag") != 1
        or value.get("python_dont_write_bytecode_flag") is not True
        or value.get("source_snapshot_policy") != SOURCE_SNAPSHOT_POLICY
        or value.get("source_inventory_sha256") != inventory_sha256
        or value.get("code_manifest_sha256") != code_manifest_sha256
        or value.get("shard_sha256") != shard_sha256
        or value.get("python_environment") != code
        or value.get("tools") != {
            "python": {
                "path": code["python_executable"],
                "sha256": code["python_executable_sha256"],
            },
            "sha256sum": {
                "path": str(SHA256SUM_COMMAND), "sha256": SHA256SUM_SHA256,
            },
            "mkdir": {"path": str(MKDIR_COMMAND), "sha256": MKDIR_SHA256},
            "rmdir": {"path": str(RMDIR_COMMAND), "sha256": RMDIR_SHA256},
        }
        or any(
            not _valid_private_identity(
                identity, "0700", regular_file=False
            )
            for identity in identities
        )
        or identities[0] != identities[1]
        or identities[2] != identities[3]
        or identities[4] != identities[5]
        or identities[0]["path"] != value.get("output_dir")
        or identities[2]["path"] != value.get("tmpdir_root")
        or identities[4]["path"] != value.get("tmpdir")
    ):
        raise SourceAuditError("task environment attestation changed")
    return value


def __getattr__(name):
    return getattr(Base, name)


def main(argv=None) -> int:
    args = Base.parse_args(argv)
    if args.command == "scan":
        scan(args)
    else:
        Base.assemble(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InfrastructureAuditError as err:
        print("infrastructure error: {}".format(err), file=sys.stderr)
        raise SystemExit(75)
    except (SourceAuditError, Base.Inventory.InventoryError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
