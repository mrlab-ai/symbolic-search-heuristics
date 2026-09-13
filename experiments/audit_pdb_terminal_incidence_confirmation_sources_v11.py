#!/usr/bin/env python3
"""Fresh full-census source audit for terminal-incidence confirmation V11."""

from __future__ import annotations

import argparse
import base64
import copy
import ctypes
import datetime
import errno
import hashlib
import json
import os
import re
import resource
import select
import signal
import stat
import subprocess
import sys
import time
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from pathlib import Path

import pdb_terminal_incidence_confirmation_inventory as Inventory
import pdb_terminal_incidence_confirmation_publication_v11 as Publication


class SourceAuditError(RuntimeError):
    pass


class InfrastructureAuditError(SourceAuditError):
    pass


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
SCHEMA = (
    "symbolic-search-heuristics/"
    "universal-unseen-confirmation-source-audit/v1/campaign-v11"
)
INVENTORY_SCHEMA = SCHEMA + "/inventory/v1"
SHARD_SCHEMA = SCHEMA + "/shard/v1"
CANDIDATE_SCHEMA = SCHEMA + "/candidate-result/v1"
TASK_ENVIRONMENT_SCHEMA = SCHEMA + "/task-environment/v1"
SOURCE_SNAPSHOT_SCHEMA = SCHEMA + "/source-snapshot/v1"
RESOURCE_CONTRACT_SCHEMA = SCHEMA + "/resource-contract/v1"
SHARD_CLAIM_SCHEMA = SCHEMA + "/shard-claim/v1"
SHARD_COMPLETION_METADATA_SCHEMA = SCHEMA + "/shard-completion-metadata/v1"
COMPUTE_CANARY_SCHEMA = SCHEMA + "/compute-canary/v1"
COMPUTE_CANARY_CAMPAIGN = "v11-compute-canary"
COMPUTE_CANARY_ORIGIN = "v11-synthetic-canary"

ARRAY_TASKS = 820
CANDIDATE_COUNT = 1640
TASKS_PER_SHARD = 2
DEFAULT_BENCHMARKS = Inventory.DEFAULT_BENCHMARKS
DEFAULT_OUTPUT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-source-audit-v11"
)
DEFAULT_INVENTORY = DEFAULT_OUTPUT / "source-inventory-v11.json"
TMP_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-source-audit-v11-tmp"
)
LOG_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-source-audit-v11-logs"
)
COMPUTE_CANARY_OUTPUT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-source-audit-v11-canary"
)
COMPUTE_CANARY_TMP_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-source-audit-v11-canary-tmp"
)
COMPUTE_CANARY_LOG_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-source-audit-v11-canary-logs"
)
CONTROLLER_CANARY_OUTPUT = (
    SCRIPT_DIR / "data" /
    "pdb-terminal-incidence-confirmation-publisher-canary-v11"
)
PREFLIGHT_ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" /
    "pdb-terminal-incidence-confirmation-v11-preflight"
)
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v11"
)
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-launch-receipt-v11.json"
SEAL_PLAN = ARTIFACT_DIR / "source-audit-seal-plan-v11.json"
TREE_STAGE = ARTIFACT_DIR / "source-audit-tree-stage-v11.json"
CENSUS_STAGE = ARTIFACT_DIR / "source-audit-census-stage-v11.json"
SPLIT_STAGE = ARTIFACT_DIR / "source-audit-split-stage-v11.json"
ATTESTATION_STAGE = (
    ARTIFACT_DIR / "source-audit-attestation-stage-v11.json"
)
ATTESTATION = ARTIFACT_DIR / "source-audit-attestation-v11.json"
EXECUTION_RECEIPT = (
    ARTIFACT_DIR / "source-audit-execution-receipt-v11.json"
)
CODE_MANIFEST = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v11_code.sha256"
)
PROTOCOL = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v11_protocol.md"
)
TRANSLATOR_DRIVER = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_translate_v11.py"
)
SLURM_PROGRAM = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v11.slurm"
)
COMPUTE_CANARY_SLURM_PROGRAM = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_compute_canary_v11.slurm"
)
COMPUTE_CANARY_FIXTURE_ROOT = (
    SCRIPT_DIR / "fixtures" / "pdb-terminal-incidence-v11-canary"
)
PINNED_PYTHON = Path(
    "/home/jendrik/.local/share/uv/python/"
    "cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
)
PINNED_PYTHON_SHA256 = (
    "021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
)
PRLIMIT = Path("/usr/bin/prlimit")
PRLIMIT_SHA256 = (
    "fc3d011a1d832dabd768343b26d38223cb2bbd13d59ed97998a2d6a747ce8676"
)
LIBSECCOMP = Path("/usr/lib64/libseccomp.so.2.5.2")
LIBSECCOMP_SHA256 = (
    "54068c4d4cf1e5692ba8051ce0744cd175d0c0e2c9812b668d738d2cbe3915d9"
)
DENIED_PROCESS_SYSCALLS = (
    "clone", "clone3", "fork", "setpgid", "setsid", "vfork",
)
CONTROLLED_PATH = "/usr/bin:/bin"
ADDRESS_SPACE_BYTES = 24_576 * 1024 * 1024
CPU_SOFT_SECONDS = 1800
CPU_HARD_SECONDS = 1801
CHILD_WALL_SECONDS = 1950
HANDSHAKE_SECONDS = 30
STREAM_PREFIX_BYTES = 1024 * 1024
STREAM_TAIL_BYTES = 8192
PIPE_RECORD_LIMIT = 4096
TOKEN_RE = re.compile(r"^[0-9a-f]{24}$")
SPLIT_SEED = (
    "symbolic-search-heuristics/universal-unseen-confirmation-guided-split/v1"
)
GUIDED_ROLE = "guided-b"
GUIDED_TOP_UP_ROLE = "guided-b-topup"
CONFIRMATION_ROLE = "confirmation-a"
CONFIRMATION_TASKS = 650
MIN_CONFIRMATION_FAMILIES = 28
MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES = 12
MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS = 100
MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES = 10
GUIDED_TARGET_TASKS = 300
MAX_GUIDED_TASKS_PER_FAMILY = 12
MIN_GUIDED_TASKS = 200
MIN_GUIDED_FAMILIES = 30
MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES = 12
MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS = 50
MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES = 10

TRANSLATOR_FILES = tuple(
    path.relative_to(REPO).as_posix()
    for path in sorted((REPO / "src" / "translate").rglob("*.py"))
)
if len(TRANSLATOR_FILES) != 38:
    raise SourceAuditError("pinned translator source file set changed")

CODE_MANIFEST_FILES = tuple(sorted({
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v11.py",
    "experiments/jj_cached_revision.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v11.py",
    "experiments/pdb_terminal_incidence_confirmation_inventory.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v11_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v11.py",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v11.slurm",
    "experiments/pdb_terminal_incidence_confirmation_source_compute_canary_v11.slurm",
    "experiments/pdb_terminal_incidence_confirmation_publication_v11.py",
    "experiments/pdb_terminal_incidence_v11_snapshot_reader.py",
    "experiments/pdb_terminal_incidence_confirmation_translate_v11.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/suite_wbh_operator_costs.json",
    "experiments/pdb_terminal_incidence_shadow_cost_attestation.json",
    "experiments/test_launch_pdb_terminal_incidence_confirmation_source_audit_v11.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v11.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_seal_v11.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_consumer_v11.py",
    "experiments/test_pdb_terminal_incidence_confirmation_publication_v11.py",
    "experiments/test_pdb_terminal_incidence_confirmation_translate_v11.py",
    "experiments/test_pdb_terminal_incidence_v11_snapshot_reader.py",
    "experiments/fixtures/pdb-terminal-incidence-v11-canary/domain.pddl",
    "experiments/fixtures/pdb-terminal-incidence-v11-canary/problem-0.pddl",
    "experiments/fixtures/pdb-terminal-incidence-v11-canary/problem-1.pddl",
    *TRANSLATOR_FILES,
}))

EXPECTED_INVENTORY_DIGESTS = {
    "all_path_records": Inventory.ALL_PATH_RECORDS_SHA256,
    "all_prior_families": Inventory.ALL_PRIOR_FAMILY_SEQUENCE_SHA256,
    "all_prior_unrepresented_families": (
        Inventory.ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
    ),
    "all_unique_problem_hashes": Inventory.ALL_UNIQUE_PROBLEM_HASHES_SHA256,
    "candidate_records": Inventory.CANDIDATE_RECORDS_SHA256,
    "cost_problem_hashes": Inventory.COST_PROBLEM_HASHES_SHA256,
    "directories": Inventory.DIRECTORY_SEQUENCE_SHA256,
    "alias_groups": Inventory.ALIAS_GROUPS_SHA256,
    "family_map": Inventory.FAMILY_MAP_SHA256,
    "prior_problem_hashes": Inventory.PRIOR_PROBLEM_HASHES_SHA256,
    "prior_identities": Inventory.PRIOR_IDENTITIES_SHA256,
    "prior_identity_ledger": Inventory.PRIOR_IDENTITY_LEDGER_SHA256,
    "prior_directory_family_map": Inventory.PRIOR_DIRECTORY_FAMILY_MAP_SHA256,
    "prior_family_ledger": Inventory.PRIOR_FAMILY_LEDGER_SHA256,
    "represented_all_prior_families": (
        Inventory.REPRESENTED_ALL_PRIOR_FAMILY_SEQUENCE_SHA256
    ),
    "residue_identities": Inventory.RESIDUE_IDENTITIES_SHA256,
    "residue_path_records": Inventory.RESIDUE_PATH_RECORDS_SHA256,
    "shadow_problem_hashes": Inventory.SHADOW_PROBLEM_HASHES_SHA256,
    "shadow_families": Inventory.SHADOW_FAMILY_SEQUENCE_SHA256,
    "shadow_unrepresented_families": (
        Inventory.SHADOW_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
    ),
}


def canonical_json(value) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise SourceAuditError("value is not canonical finite JSON") from err


def _digest(value) -> str:
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _is_sha256(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and not any(char not in "0123456789abcdef" for char in value)
    )


def _identity(info: os.stat_result) -> dict:
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": stat.S_IMODE(info.st_mode),
        "uid": info.st_uid,
        "size": info.st_size,
    }


def _relative_to(path: Path, root: Path) -> str:
    absolute = Path(os.path.abspath(path))
    try:
        return absolute.relative_to(Path(os.path.abspath(root))).as_posix()
    except ValueError as err:
        raise SourceAuditError("path escapes its frozen root") from err


def _read_regular(
    path: Path,
    label: str,
    *,
    root: Path | None = None,
    expected_sha256: str | None = None,
) -> tuple[bytes, dict]:
    path = Path(path)
    if root is not None:
        _relative_to(path, root)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    try:
        before_path = path.lstat()
        if (
            path.is_symlink() or not stat.S_ISREG(before_path.st_mode)
            or before_path.st_nlink != 1
        ):
            raise SourceAuditError("{} is not a regular file".format(label))
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise SourceAuditError("{} descriptor is not regular".format(label))
        chunks = []
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            chunks.append(block)
        after = os.fstat(descriptor)
        after_path = path.lstat()
    except OSError as err:
        raise SourceAuditError("cannot read {}".format(label)) from err
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if (
        after.st_nlink != 1
        or after_path.st_nlink != 1
        or _identity(before_path) != _identity(before)
        or _identity(before) != _identity(after)
        or _identity(after) != _identity(after_path)
    ):
        raise SourceAuditError("{} changed while being read".format(label))
    raw = b"".join(chunks)
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise SourceAuditError("{} hash changed".format(label))
    return raw, _identity(after)


def sha256_file(path: Path, label: str = "file") -> str:
    raw, _ = _read_regular(path, label)
    return hashlib.sha256(raw).hexdigest()


def atomic_exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    path = Path(path)
    directory_fd = None
    try:
        parent_info = path.parent.lstat()
    except OSError as err:
        raise SourceAuditError("cannot inspect {} parent".format(label)) from err
    if (
        path.parent.is_symlink() or not stat.S_ISDIR(parent_info.st_mode)
        or parent_info.st_uid != os.getuid() or os.path.lexists(path)
    ):
        raise SourceAuditError("refusing to overwrite {}".format(label))
    directory_flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        directory_flags |= os.O_DIRECTORY
    if hasattr(os, "O_NOFOLLOW"):
        directory_flags |= os.O_NOFOLLOW
    try:
        directory_fd = os.open(path.parent, directory_flags)
        if _identity(os.fstat(directory_fd)) != _identity(parent_info):
            raise SourceAuditError("{} parent was replaced".format(label))
    except OSError as err:
        raise SourceAuditError("cannot open {} parent".format(label)) from err
    temporary = path.parent / ("." + path.name + ".new")
    if os.path.lexists(temporary):
        raise SourceAuditError("stale temporary {} exists".format(label))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    try:
        descriptor = os.open(temporary, flags, 0o400)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path, follow_symlinks=False)
        temporary.unlink()
        os.fsync(directory_fd)
    except OSError as err:
        raise SourceAuditError("cannot publish {}".format(label)) from err
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if directory_fd is not None:
            os.close(directory_fd)
    check, _ = _read_regular(path, label)
    if check != raw:
        raise SourceAuditError("{} changed after publication".format(label))
    return hashlib.sha256(raw).hexdigest()


def _load_canonical_json(path: Path, label: str) -> tuple[bytes, dict]:
    raw, _ = _read_regular(path, label)
    try:
        value = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SourceAuditError("{} is not JSON".format(label)) from err
    if type(value) is not dict or canonical_json(value) != raw:
        raise SourceAuditError("{} is not canonical JSON".format(label))
    return raw, value


def _candidate_json(candidate) -> dict:
    return {
        "directory": candidate.directory,
        "family": candidate.family,
        "problem": candidate.problem,
        "domain_file": candidate.domain_file,
        "problem_file": candidate.problem_file,
        "domain_sha256": candidate.domain_sha256,
        "problem_sha256": candidate.problem_sha256,
    }


def build_inventory_manifest(benchmarks: Path = DEFAULT_BENCHMARKS) -> dict:
    try:
        inventory = Inventory.load_inventory(Path(benchmarks))
    except Inventory.InventoryError as err:
        raise SourceAuditError(str(err)) from err
    groups = {group.problem_sha256: group for group in inventory.alias_groups}
    records = []
    for index, candidate in enumerate(inventory.candidates):
        group = groups.get(candidate.problem_sha256)
        if group is None or group.canonical != candidate:
            raise SourceAuditError("inventory alias provenance changed")
        records.append({
            "candidate_index": index,
            **_candidate_json(candidate),
            "canonical_path": candidate.canonical_path,
            "is_shadow_family": candidate.is_shadow_family,
            "is_shadow_unrepresented": candidate.is_shadow_unrepresented,
            "is_all_prior_represented": candidate.is_all_prior_represented,
            "is_all_prior_unrepresented": candidate.is_all_prior_unrepresented,
            "aliases": [_candidate_json(alias) for alias in group.aliases],
        })
    if len(records) != CANDIDATE_COUNT:
        raise SourceAuditError("frozen candidate count changed")
    return {
        "schema": INVENTORY_SCHEMA,
        "benchmark_revision": Inventory.BENCHMARK_REVISION,
        "cost_manifest_sha256": Inventory.COST_MANIFEST_SHA256,
        "shadow_attestation_sha256": Inventory.SHADOW_ATTESTATION_SHA256,
        "candidate_records_sha256": Inventory.CANDIDATE_RECORDS_SHA256,
        "alias_groups_sha256": Inventory.ALIAS_GROUPS_SHA256,
        "inventory_digests": dict(inventory.digests),
        "counts": {
            "candidates": len(records),
            "families": len(inventory.residue_families),
            "source_aliases": sum(len(record["aliases"]) for record in records),
            "discarded_aliases": inventory.discarded_alias_count,
            "prior_identity_overlap": inventory.prior_identity_overlap_count,
            "prior_problem_hash_overlap": inventory.prior_problem_hash_overlap_count,
        },
        "shadow_families": list(Inventory.SHADOW_FAMILIES),
        "all_prior_families": list(Inventory.ALL_PRIOR_FAMILIES),
        "all_prior_unrepresented_families": list(
            Inventory.ALL_PRIOR_UNREPRESENTED_FAMILIES
        ),
        "records_sha256": _digest(records),
        "records": records,
    }


def _source_key(record: dict) -> tuple[str, str, str, str]:
    return (
        record["directory"],
        record["problem"],
        record["problem_file"],
        record["domain_file"],
    )


def validate_inventory_manifest(value: dict) -> list[dict]:
    expected_top = {
        "schema", "benchmark_revision", "cost_manifest_sha256",
        "shadow_attestation_sha256", "candidate_records_sha256",
        "alias_groups_sha256", "inventory_digests", "counts",
        "shadow_families", "all_prior_families",
        "all_prior_unrepresented_families", "records_sha256", "records",
    }
    records = value.get("records") if type(value) is dict else None
    if (
        type(value) is not dict
        or set(value) != expected_top
        or value.get("schema") != INVENTORY_SCHEMA
        or value.get("benchmark_revision") != Inventory.BENCHMARK_REVISION
        or value.get("cost_manifest_sha256") != Inventory.COST_MANIFEST_SHA256
        or value.get("shadow_attestation_sha256")
        != Inventory.SHADOW_ATTESTATION_SHA256
        or value.get("candidate_records_sha256")
        != Inventory.CANDIDATE_RECORDS_SHA256
        or value.get("alias_groups_sha256") != Inventory.ALIAS_GROUPS_SHA256
        or value.get("inventory_digests") != EXPECTED_INVENTORY_DIGESTS
        or value.get("shadow_families") != list(Inventory.SHADOW_FAMILIES)
        or value.get("all_prior_families")
        != list(Inventory.ALL_PRIOR_FAMILIES)
        or value.get("all_prior_unrepresented_families")
        != list(Inventory.ALL_PRIOR_UNREPRESENTED_FAMILIES)
        or type(records) is not list
        or len(records) != CANDIDATE_COUNT
        or value.get("records_sha256") != _digest(records)
    ):
        raise SourceAuditError("source inventory identity changed")
    counts = value.get("counts")
    if (
        type(counts) is not dict
        or set(counts) != {
            "candidates", "families", "source_aliases", "discarded_aliases",
            "prior_identity_overlap", "prior_problem_hash_overlap",
        }
        or counts["candidates"] != CANDIDATE_COUNT
        or counts["families"] != Inventory.EXPECTED_FAMILIES
        or counts["discarded_aliases"] != Inventory.EXPECTED_DISCARDED_ALIASES
        or counts["prior_identity_overlap"] != 0
        or counts["prior_problem_hash_overlap"] != 0
    ):
        raise SourceAuditError("source inventory counts changed")
    candidate_records = []
    alias_groups = []
    seen_problem_hashes = set()
    required = {
        "candidate_index", "directory", "family", "problem", "domain_file",
        "problem_file", "domain_sha256", "problem_sha256", "canonical_path",
        "is_shadow_family", "is_shadow_unrepresented",
        "is_all_prior_represented", "is_all_prior_unrepresented", "aliases",
    }
    for index, record in enumerate(records):
        if type(record) is not dict or set(record) != required:
            raise SourceAuditError("source inventory record shape changed")
        candidate = {
            key: record[key]
            for key in (
                "directory", "family", "problem", "domain_file",
                "problem_file", "domain_sha256", "problem_sha256",
            )
        }
        aliases = record["aliases"]
        if (
            record["candidate_index"] != index
            or record["canonical_path"] != record["problem_file"]
            or record["family"] != Inventory.DIRECTORY_TO_FAMILY.get(
                record["directory"]
            )
            or record["is_shadow_family"]
            is not (record["family"] in Inventory.SHADOW_FAMILIES)
            or record["is_shadow_unrepresented"]
            is not (record["family"] not in Inventory.SHADOW_FAMILIES)
            or record["is_all_prior_represented"]
            is not (record["family"] in Inventory.ALL_PRIOR_FAMILIES)
            or record["is_all_prior_unrepresented"]
            is not (record["family"] not in Inventory.ALL_PRIOR_FAMILIES)
            or not _is_sha256(record["domain_sha256"])
            or not _is_sha256(record["problem_sha256"])
            or record["problem_sha256"] in seen_problem_hashes
            or type(aliases) is not list
            or not aliases
            or aliases != sorted(aliases, key=_source_key)
            or aliases[0] != candidate
            or any(type(alias) is not dict or set(alias) != set(candidate)
                   for alias in aliases)
            or any(alias["problem_sha256"] != record["problem_sha256"]
                   or alias["family"] != record["family"] for alias in aliases)
        ):
            raise SourceAuditError("source inventory record changed")
        seen_problem_hashes.add(record["problem_sha256"])
        candidate_records.append(candidate)
        alias_groups.append({
            "problem_sha256": record["problem_sha256"],
            "canonical": candidate,
            "aliases": aliases,
        })
    if (
        _digest(candidate_records) != Inventory.CANDIDATE_RECORDS_SHA256
        or _digest(sorted(alias_groups, key=lambda item: item["problem_sha256"]))
        != Inventory.ALIAS_GROUPS_SHA256
        or counts["source_aliases"] != sum(
            len(record["aliases"]) for record in records
        )
    ):
        raise SourceAuditError("source inventory content digest changed")
    return records


def code_manifest_bytes() -> bytes:
    lines = []
    for relative in CODE_MANIFEST_FILES:
        path = REPO / relative
        raw, _ = _read_regular(
            path, "V11 manifest dependency", root=REPO
        )
        lines.append(
            "{}  {}\n".format(hashlib.sha256(raw).hexdigest(), relative)
        )
    return "".join(lines).encode("ascii")


def validate_code_manifest(path: Path, expected_sha256: str) -> dict:
    raw, _ = _read_regular(path, "V11 code manifest", root=REPO)
    if (
        not _is_sha256(expected_sha256)
        or hashlib.sha256(raw).hexdigest() != expected_sha256
        or not raw.endswith(b"\n")
    ):
        raise SourceAuditError("V11 code manifest identity changed")
    records = []
    for line in raw.decode("ascii").splitlines():
        if len(line) < 67 or line[64:66] != "  ":
            raise SourceAuditError("V11 code manifest record changed")
        digest = line[:64]
        relative = line[66:]
        if not _is_sha256(digest) or relative not in CODE_MANIFEST_FILES:
            raise SourceAuditError("V11 code manifest path changed")
        records.append((relative, digest))
    if (
        records != sorted(records)
        or len(records) != len(CODE_MANIFEST_FILES)
        or [relative for relative, _ in records] != list(CODE_MANIFEST_FILES)
    ):
        raise SourceAuditError("V11 code manifest file set changed")
    for relative, digest in records:
        dependency, _ = _read_regular(
            REPO / relative, "V11 manifest dependency", root=REPO
        )
        if hashlib.sha256(dependency).hexdigest() != digest:
            raise SourceAuditError("V11 manifest dependency changed")
    python_raw, _ = _read_regular(PINNED_PYTHON, "pinned Python")
    prlimit_raw, _ = _read_regular(PRLIMIT, "pinned prlimit")
    seccomp_raw, _ = _read_regular(LIBSECCOMP, "pinned libseccomp")
    if (
        hashlib.sha256(python_raw).hexdigest() != PINNED_PYTHON_SHA256
        or hashlib.sha256(prlimit_raw).hexdigest() != PRLIMIT_SHA256
        or hashlib.sha256(seccomp_raw).hexdigest() != LIBSECCOMP_SHA256
    ):
        raise SourceAuditError("V11 pinned runtime tool changed")
    return {
        "code_manifest_sha256": expected_sha256,
        "code_manifest_records": len(records),
        "pinned_python_sha256": PINNED_PYTHON_SHA256,
        "prlimit_sha256": PRLIMIT_SHA256,
        "libseccomp_sha256": LIBSECCOMP_SHA256,
        "translator_file_count": len(TRANSLATOR_FILES),
        "translator_files_sha256": _digest([
            {"path": relative, "sha256": digest}
            for relative, digest in records
            if relative in TRANSLATOR_FILES
        ]),
    }


def shard_path(directory: Path, index: int) -> Path:
    if type(index) is not int or not 0 <= index < ARRAY_TASKS:
        raise SourceAuditError("V11 shard index is invalid")
    return Path(directory) / "shard-{:04d}-of-{:04d}".format(
        index, ARRAY_TASKS
    )


def candidate_indices_for_shard(index: int) -> tuple[int, int]:
    if type(index) is not int or not 0 <= index < ARRAY_TASKS:
        raise SourceAuditError("V11 shard index is invalid")
    return 2 * index, 2 * index + 1


def resource_contract() -> dict:
    return {
        "schema": RESOURCE_CONTRACT_SCHEMA,
        "address_space_bytes": ADDRESS_SPACE_BYTES,
        "cpu_soft_seconds": CPU_SOFT_SECONDS,
        "cpu_hard_seconds": CPU_HARD_SECONDS,
        "child_wall_watchdog_seconds": CHILD_WALL_SECONDS,
        "wall_watchdog_is_scientific_exclusion": False,
        "memory_exit_code": 20,
        "cpu_time_exit_code": 21,
        "input_error_exit_code": 31,
        "handshake_failure_exit_code": 70,
        "release_byte_base64": base64.b64encode(b"G").decode("ascii"),
        "candidate_process_group_isolated": True,
        "candidate_process_creation_denied": True,
        "denied_process_syscalls": list(DENIED_PROCESS_SYSCALLS),
        "pinned_python_sha256": PINNED_PYTHON_SHA256,
        "prlimit_sha256": PRLIMIT_SHA256,
        "libseccomp_sha256": LIBSECCOMP_SHA256,
    }


def _mkdir_private(path: Path, label: str) -> dict:
    path = Path(path)
    if os.path.lexists(path):
        raise SourceAuditError("{} already exists".format(label))
    try:
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
        info = path.lstat()
    except OSError as err:
        raise SourceAuditError("cannot create {}".format(label)) from err
    if (
        path.is_symlink() or not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.getuid()
    ):
        raise SourceAuditError("{} is not a private directory".format(label))
    return _identity(info)


def _directory_identity(path: Path, label: str) -> dict:
    try:
        info = Path(path).lstat()
    except OSError as err:
        raise SourceAuditError("cannot inspect {}".format(label)) from err
    if Path(path).is_symlink() or not stat.S_ISDIR(info.st_mode):
        raise SourceAuditError("{} is not a directory".format(label))
    return _identity(info)


def _write_exclusive(path: Path, raw: bytes, mode: int, label: str) -> dict:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    try:
        descriptor = os.open(path, flags, mode)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        info = Path(path).lstat()
    except OSError as err:
        raise SourceAuditError("cannot create {}".format(label)) from err
    finally:
        if descriptor is not None:
            os.close(descriptor)
    return _identity(info)


def _unlink_verified(path: Path, expected: dict, label: str) -> None:
    try:
        current = _identity(Path(path).lstat())
    except OSError as err:
        raise SourceAuditError("cannot inspect {} for cleanup".format(label)) from err
    if current != expected or not stat.S_ISREG(Path(path).lstat().st_mode):
        raise SourceAuditError("{} changed before cleanup".format(label))
    try:
        Path(path).unlink()
    except OSError as err:
        raise SourceAuditError("cannot remove {}".format(label)) from err


def _rmdir_empty(path: Path, expected: dict, label: str) -> None:
    current = _directory_identity(path, label)
    stable_fields = ("device", "inode", "mode", "uid")
    if any(current[field] != expected[field] for field in stable_fields):
        raise SourceAuditError("{} changed before cleanup".format(label))
    try:
        if any(Path(path).iterdir()):
            raise SourceAuditError("{} is not empty".format(label))
        Path(path).rmdir()
    except OSError as err:
        raise SourceAuditError("cannot remove {}".format(label)) from err


def _snapshot_source(
    record: dict, benchmarks: Path, work: Path
) -> tuple[dict, dict[str, tuple[Path, dict]]]:
    try:
        benchmark_root = Path(benchmarks).resolve(strict=True)
    except OSError as err:
        raise SourceAuditError("cannot resolve frozen benchmark root") from err
    if not benchmark_root.is_dir():
        raise SourceAuditError("frozen benchmark root is not a directory")
    files = {}
    evidence = []
    for role, relative_key, digest_key, target_name in (
        ("domain", "domain_file", "domain_sha256", "domain.pddl"),
        ("problem", "problem_file", "problem_sha256", "problem.pddl"),
    ):
        relative = record[relative_key]
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise SourceAuditError("unsafe frozen source path")
        try:
            source = (benchmark_root / relative_path).resolve(strict=True)
            source.relative_to(benchmark_root)
        except (OSError, ValueError) as err:
            raise SourceAuditError("frozen source escapes benchmark root") from err
        raw, original_identity = _read_regular(
            source,
            "frozen {} source".format(role),
            root=benchmark_root,
            expected_sha256=record[digest_key],
        )
        target = work / target_name
        target_identity = _write_exclusive(
            target, raw, 0o400, "{} source snapshot".format(role)
        )
        files[role] = (target, target_identity)
        evidence.append({
            "role": role,
            "source_file": relative,
            "source_identity": original_identity,
            "snapshot_name": target.name,
            "snapshot_identity_before": target_identity,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        })
    return {
        "schema": SOURCE_SNAPSHOT_SCHEMA,
        "files": evidence,
        "candidate_private_working_directory": True,
        "source_hashes_verified_before_use": True,
    }, files


def _install_process_creation_filter() -> None:
    allow = 0x7FFF0000
    deny_with_eperm = 0x00050000 | errno.EPERM
    library = ctypes.CDLL(str(LIBSECCOMP), use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [
        ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint,
    ]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(allow)
    if not context:
        raise OSError("cannot initialize candidate seccomp filter")
    try:
        for name in DENIED_PROCESS_SYSCALLS:
            number = library.seccomp_syscall_resolve_name(name.encode("ascii"))
            if (
                number < 0
                or library.seccomp_rule_add(
                    context, deny_with_eperm, number, 0,
                ) != 0
            ):
                raise OSError("cannot bind candidate seccomp rule")
        if library.seccomp_load(context) != 0:
            raise OSError("cannot load candidate seccomp filter")
    finally:
        library.seccomp_release(context)


def _child_preexec() -> None:
    os.setsid()
    resource.setrlimit(
        resource.RLIMIT_AS, (ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES)
    )
    resource.setrlimit(
        resource.RLIMIT_CPU, (CPU_SOFT_SECONDS, CPU_HARD_SECONDS)
    )
    _install_process_creation_filter()


def _read_pipe_record(fd: int, label: str, timeout: float) -> bytes:
    deadline = time.monotonic() + timeout
    payload = bytearray()
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise InfrastructureAuditError("{} timed out".format(label))
        readable, _, _ = select.select([fd], [], [], remaining)
        if not readable:
            raise InfrastructureAuditError("{} timed out".format(label))
        block = os.read(fd, min(1024, PIPE_RECORD_LIMIT + 1 - len(payload)))
        if not block:
            break
        payload.extend(block)
        if len(payload) > PIPE_RECORD_LIMIT:
            raise InfrastructureAuditError("{} exceeded its bound".format(label))
    return bytes(payload)


def _load_pipe_json(raw: bytes, label: str) -> dict | None:
    if not raw:
        return None
    if not raw.endswith(b"\n") or raw.count(b"\n") != 1:
        raise SourceAuditError("{} framing changed".format(label))
    body = raw[:-1]
    try:
        value = json.loads(body.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SourceAuditError("{} JSON changed".format(label)) from err
    if type(value) is not dict or canonical_json(value) != body:
        raise SourceAuditError("{} is not canonical JSON".format(label))
    return value


def _parent_limit_observation(pid: int) -> dict:
    command = [
        str(PRLIMIT), "--pid", str(pid), "--as", "--cpu",
        "--output=RESOURCE,SOFT,HARD,UNITS", "--noheadings", "--raw",
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            env={"PATH": CONTROLLED_PATH, "LANG": "C", "LC_ALL": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        raise InfrastructureAuditError("cannot inspect child limits") from err
    expected = (
        "AS {} {} bytes\nCPU {} {} seconds\n".format(
            ADDRESS_SPACE_BYTES,
            ADDRESS_SPACE_BYTES,
            CPU_SOFT_SECONDS,
            CPU_HARD_SECONDS,
        ).encode("ascii")
    )
    if completed.returncode != 0 or completed.stderr or completed.stdout != expected:
        raise InfrastructureAuditError("parent child-limit observation changed")
    return {
        "tool_sha256": PRLIMIT_SHA256,
        "command": [item if item != str(pid) else "CHILD_PID" for item in command],
        "stdout_sha256": hashlib.sha256(completed.stdout).hexdigest(),
        "rlimit_as": [ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES],
        "rlimit_cpu": [CPU_SOFT_SECONDS, CPU_HARD_SECONDS],
    }


def _parent_isolation_observation(pid: int) -> dict:
    raw, _ = _read_regular(
        Path("/proc") / str(pid) / "status", "candidate process status"
    )
    wanted = {"NoNewPrivs", "Seccomp", "Seccomp_filters", "Threads"}
    values = {}
    try:
        for line in raw.decode("ascii").splitlines():
            key, separator, value = line.partition(":")
            if separator and key in wanted:
                if key in values:
                    raise ValueError("duplicate process-status field")
                values[key] = int(value.strip())
    except (UnicodeDecodeError, ValueError) as err:
        raise InfrastructureAuditError(
            "cannot parse candidate process isolation"
        ) from err
    try:
        process_group = os.getpgid(pid)
    except OSError as err:
        raise InfrastructureAuditError(
            "cannot inspect candidate process group"
        ) from err
    if (
        set(values) != wanted
        or values["NoNewPrivs"] != 1
        or values["Seccomp"] != 2
        or values["Seccomp_filters"] < 1
        or values["Threads"] != 1
        or process_group != pid
    ):
        raise InfrastructureAuditError(
            "candidate process isolation changed"
        )
    return {
        "status_sha256": hashlib.sha256(raw).hexdigest(),
        "process_group": process_group,
        "no_new_privs": values["NoNewPrivs"],
        "seccomp_mode": values["Seccomp"],
        "seccomp_filters": values["Seccomp_filters"],
        "threads": values["Threads"],
        "process_creation_syscalls_denied": list(DENIED_PROCESS_SYSCALLS),
        "libseccomp_sha256": LIBSECCOMP_SHA256,
    }


def _validate_child_limit_evidence(
    value, pid: int, parent_isolation: dict,
) -> dict:
    expected_schema = SCHEMA + "/child-limit-evidence/v1"
    if (
        type(value) is not dict
        or set(value) != {
            "schema", "pid", "process_group", "rlimit_as", "rlimit_cpu",
            "no_new_privs", "seccomp_mode", "seccomp_filters", "threads",
        }
        or value.get("schema") != expected_schema
        or value.get("pid") != pid
        or value.get("process_group") != pid
        or value.get("rlimit_as")
        != [ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES]
        or value.get("rlimit_cpu")
        != [CPU_SOFT_SECONDS, CPU_HARD_SECONDS]
        or value.get("no_new_privs") != 1
        or value.get("seccomp_mode") != 2
        or type(value.get("seccomp_filters")) is not int
        or value["seccomp_filters"] < 1
        or value.get("threads") != 1
        or value["seccomp_filters"] != parent_isolation["seccomp_filters"]
    ):
        raise InfrastructureAuditError("child limit evidence changed")
    try:
        observed_group = os.getpgid(pid)
    except OSError as err:
        raise InfrastructureAuditError("cannot inspect child process group") from err
    if observed_group != pid:
        raise InfrastructureAuditError("candidate process group isolation changed")
    return copy.deepcopy(value)


def _normalization_evidence(value) -> dict:
    if (
        type(value) is not dict
        or set(value) != {"schema", "num_normalized_axioms", "strategy"}
        or value.get("schema") != SCHEMA + "/normalization-evidence/v1"
        or value.get("strategy") != "axiom_based"
        or type(value.get("num_normalized_axioms")) is not int
        or value["num_normalized_axioms"] < 0
    ):
        raise SourceAuditError("normalization evidence changed")
    return copy.deepcopy(value)


def _process_group_absent(pid: int) -> bool:
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return True
    except PermissionError as err:
        raise InfrastructureAuditError(
            "cannot verify candidate process group termination"
        ) from err
    return False


def _kill_process_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired as err:
        raise InfrastructureAuditError(
            "cannot reap candidate process group leader"
        ) from err
    deadline = time.monotonic() + 30
    while not _process_group_absent(process.pid):
        if time.monotonic() >= deadline:
            raise InfrastructureAuditError(
                "cannot reap complete candidate process group"
            )
        time.sleep(0.01)


def _capture_evidence(
    raw_path: Path, prefix_path: Path, public_name: str, label: str
) -> dict:
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    source_fd = prefix_fd = None
    digest = hashlib.sha256()
    retained_digest = hashlib.sha256()
    total = 0
    retained = 0
    tail = bytearray()
    try:
        source_fd = os.open(raw_path, flags)
        before = os.fstat(source_fd)
        if not stat.S_ISREG(before.st_mode):
            raise SourceAuditError("{} is not regular".format(label))
        prefix_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            prefix_flags |= os.O_NOFOLLOW
        prefix_fd = os.open(prefix_path, prefix_flags, 0o400)
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
            keep = block[:max(0, STREAM_PREFIX_BYTES - retained)]
            if keep:
                view = memoryview(keep)
                while view:
                    written = os.write(prefix_fd, view)
                    if written <= 0:
                        raise SourceAuditError(
                            "cannot retain {} prefix".format(label)
                        )
                    view = view[written:]
                retained_digest.update(keep)
                retained += len(keep)
            tail.extend(block)
            if len(tail) > STREAM_TAIL_BYTES:
                del tail[:-STREAM_TAIL_BYTES]
        os.fsync(prefix_fd)
        after = os.fstat(source_fd)
        path_after = Path(raw_path).lstat()
        prefix_after = os.fstat(prefix_fd)
    except OSError as err:
        raise SourceAuditError("cannot stream {}".format(label)) from err
    finally:
        if source_fd is not None:
            os.close(source_fd)
        if prefix_fd is not None:
            os.close(prefix_fd)
    if (
        _identity(before) != _identity(after)
        or _identity(after) != _identity(path_after)
        or prefix_after.st_size != retained
    ):
        raise SourceAuditError("{} changed while streaming".format(label))
    raw_identity = _identity(path_after)
    _unlink_verified(raw_path, raw_identity, label)
    return {
        "total_bytes": total,
        "sha256": digest.hexdigest(),
        "retained_path": public_name,
        "retained_bytes": retained,
        "retained_sha256": retained_digest.hexdigest(),
        "retention_limit_bytes": STREAM_PREFIX_BYTES,
        "truncated": total > retained,
        "tail_base64": base64.b64encode(bytes(tail)).decode("ascii"),
        "tail_bytes": len(tail),
    }


def _hash_optional_sas(path: Path) -> dict | None:
    if not os.path.lexists(path):
        return None
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    digest = hashlib.sha256()
    size = 0
    try:
        descriptor = os.open(path, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise SourceAuditError("partial output.sas is not regular")
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            size += len(block)
        after = os.fstat(descriptor)
        path_after = path.lstat()
    except OSError as err:
        raise SourceAuditError("cannot hash partial output.sas") from err
    finally:
        if descriptor is not None:
            os.close(descriptor)
    if _identity(before) != _identity(after) or _identity(after) != _identity(path_after):
        raise SourceAuditError("partial output.sas changed while hashing")
    identity = _identity(path_after)
    _unlink_verified(path, identity, "partial output.sas")
    return {"bytes": size, "sha256": digest.hexdigest(), "discarded": True}


def _verify_and_remove_snapshots(
    snapshot: dict, files: dict[str, tuple[Path, dict]]
) -> dict:
    after_by_role = {}
    for item in snapshot["files"]:
        role = item["role"]
        path, expected_identity = files[role]
        raw, after = _read_regular(
            path,
            "{} source snapshot after use".format(role),
            expected_sha256=item["sha256"],
        )
        if after != expected_identity or len(raw) != item["bytes"]:
            raise SourceAuditError("{} source snapshot changed".format(role))
        after_by_role[role] = after
    for item in snapshot["files"]:
        role = item["role"]
        path, expected_identity = files[role]
        _unlink_verified(path, expected_identity, "{} source snapshot".format(role))
        item["snapshot_identity_after"] = after_by_role[role]
    snapshot["identity_and_sha256_verified_after_use"] = True
    snapshot["exact_snapshot_files_removed"] = True
    return snapshot


def _support_reasons(sas: dict, normalized_axioms: int) -> list[str]:
    reasons = []
    if sas["num_operators"] < 1:
        reasons.append("no-serialized-operators")
    if (
        sas["num_zero_cost_operators"] != 0
        or sas["min_operator_cost"] is None
        or sas["min_operator_cost"] < 1
    ):
        reasons.append("nonpositive-serialized-operator-cost")
    if sas["num_serialized_axioms"] != 0:
        reasons.append("serialized-axioms")
    if sas["num_conditional_effects"] != 0:
        reasons.append("serialized-conditional-effects")
    if normalized_axioms != 0:
        reasons.append("normalized-axioms")
    return reasons


def _rank(record: dict, role: str) -> str:
    fields = (
        SPLIT_SEED,
        role,
        record["family"],
        record["problem_sha256"],
        record["canonical_path"],
    )
    return hashlib.sha256(b"\0".join(
        field.encode("utf-8") for field in fields
    )).hexdigest()


def _stratum_indices(records: list[dict], families: set[str]) -> dict:
    selected = [
        record["candidate_index"]
        for record in records
        if record["family"] in families
    ]
    represented = sorted({
        record["family"] for record in records if record["family"] in families
    })
    return {
        "tasks": len(selected),
        "families": len(represented),
        "candidate_indices_sha256": _digest(selected),
        "families_sha256": _digest(represented),
    }


def split_supported(records: list[dict]) -> tuple[dict, dict]:
    if (
        type(records) is not list
        or len(records) != CANDIDATE_COUNT
        or [record.get("candidate_index") for record in records]
        != list(range(CANDIDATE_COUNT))
    ):
        raise SourceAuditError("V11 split population changed")
    for record in records:
        status = record.get("status")
        determined = record.get("support_determined")
        supported_value = record.get("supported")
        eligible = record.get("eligible_for_cohort")
        reasons = record.get("support_exclusion_reasons")
        if status == "success":
            valid = (
                determined is True
                and type(supported_value) is bool
                and eligible is supported_value
                and type(reasons) is list
                and supported_value is (len(reasons) == 0)
            )
        elif status == "input-rejected":
            valid = (
                determined is True
                and supported_value is False
                and eligible is False
                and reasons == ["translation-input-rejected"]
            )
        elif status == "resource-excluded":
            valid = (
                determined is False
                and supported_value is None
                and eligible is False
                and reasons is None
                and record.get("resource_exclusion_kind") in {"memory", "time"}
            )
        else:
            valid = False
        if not valid:
            raise SourceAuditError("V11 support disposition changed")
    supported = [record for record in records if record.get("supported") is True]
    if any(
        record.get("support_determined") is not True
        or record.get("eligible_for_cohort") is not True
        for record in supported
    ):
        raise SourceAuditError("V11 supported eligibility changed")
    shadow = set(Inventory.SHADOW_FAMILIES)
    inventory_families = {record["family"] for record in records}
    shadow_unrepresented = inventory_families - shadow
    all_prior_unrepresented = set(Inventory.ALL_PRIOR_UNREPRESENTED_FAMILIES)
    by_family = defaultdict(list)
    for record in supported:
        by_family[record["family"]].append(record)
    guided_base = []
    guided_hashes = set()
    for family in sorted(by_family):
        ordered = sorted(
            by_family[family],
            key=lambda record: (
                _rank(record, GUIDED_ROLE), record["canonical_path"]
            ),
        )
        reserve = min(3, len(ordered) // 2)
        for record in ordered[:reserve]:
            guided_base.append(record)
            guided_hashes.add(record["problem_sha256"])
    confirmation_queues = {}
    for family in sorted(by_family):
        remaining = [
            record for record in by_family[family]
            if record["problem_sha256"] not in guided_hashes
        ]
        confirmation_queues[family] = deque(sorted(
            remaining,
            key=lambda record: (
                _rank(record, CONFIRMATION_ROLE), record["canonical_path"]
            ),
        ))
    confirmation = []
    while len(confirmation) < CONFIRMATION_TASKS:
        progress = False
        for family in sorted(confirmation_queues):
            if (
                confirmation_queues[family]
                and len(confirmation) < CONFIRMATION_TASKS
            ):
                confirmation.append(confirmation_queues[family].popleft())
                progress = True
        if not progress:
            break
    selected_hashes = guided_hashes | {
        record["problem_sha256"] for record in confirmation
    }
    guided_counts = Counter(record["family"] for record in guided_base)
    top_up_queues = {
        family: deque(sorted(
            (
                record for record in by_family[family]
                if record["problem_sha256"] not in selected_hashes
            ),
            key=lambda record: (
                _rank(record, GUIDED_TOP_UP_ROLE), record["canonical_path"]
            ),
        ))
        for family in sorted(by_family)
    }
    post_confirmation_remaining = sum(
        len(queue) for queue in top_up_queues.values()
    )
    guided_cap_capacity = len(guided_base) + sum(
        min(
            len(top_up_queues[family]),
            MAX_GUIDED_TASKS_PER_FAMILY - guided_counts[family],
        )
        for family in top_up_queues
    )
    guided_top_up = []
    while len(guided_base) + len(guided_top_up) < GUIDED_TARGET_TASKS:
        progress = False
        for family in sorted(top_up_queues):
            if (
                top_up_queues[family]
                and guided_counts[family] < MAX_GUIDED_TASKS_PER_FAMILY
                and len(guided_base) + len(guided_top_up)
                < GUIDED_TARGET_TASKS
            ):
                record = top_up_queues[family].popleft()
                guided_top_up.append(record)
                guided_counts[family] += 1
                progress = True
        if not progress:
            break
    guided_base.sort(key=lambda record: (
        record["family"], _rank(record, GUIDED_ROLE), record["canonical_path"]
    ))
    guided = guided_base + guided_top_up
    confirmation_families = {record["family"] for record in confirmation}
    guided_families = {record["family"] for record in guided}
    confirmation_all_prior = [
        record for record in confirmation
        if record["family"] in all_prior_unrepresented
    ]
    guided_all_prior = [
        record for record in guided
        if record["family"] in all_prior_unrepresented
    ]
    clauses = {
        "confirmation_tasks": {
            "actual": len(confirmation),
            "required": CONFIRMATION_TASKS,
            "passed": len(confirmation) == CONFIRMATION_TASKS,
        },
        "confirmation_families": {
            "actual": len(confirmation_families),
            "required_minimum": MIN_CONFIRMATION_FAMILIES,
            "passed": len(confirmation_families) >= MIN_CONFIRMATION_FAMILIES,
        },
        "confirmation_shadow_unrepresented_families": {
            "actual": len(confirmation_families - shadow),
            "required_minimum": MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES,
            "passed": len(confirmation_families - shadow)
            >= MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES,
        },
        "confirmation_all_prior_unrepresented_tasks": {
            "actual": len(confirmation_all_prior),
            "required_minimum": MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS,
            "passed": len(confirmation_all_prior)
            >= MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS,
        },
        "confirmation_all_prior_unrepresented_families": {
            "actual": len({record["family"] for record in confirmation_all_prior}),
            "required_minimum": MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES,
            "passed": len({record["family"] for record in confirmation_all_prior})
            >= MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES,
        },
        "guided_tasks": {
            "actual": len(guided),
            "required_minimum": MIN_GUIDED_TASKS,
            "passed": len(guided) >= MIN_GUIDED_TASKS,
        },
        "guided_families": {
            "actual": len(guided_families),
            "required_minimum": MIN_GUIDED_FAMILIES,
            "passed": len(guided_families) >= MIN_GUIDED_FAMILIES,
        },
        "guided_shadow_unrepresented_families": {
            "actual": len(guided_families - shadow),
            "required_minimum": MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES,
            "passed": len(guided_families - shadow)
            >= MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES,
        },
        "guided_all_prior_unrepresented_tasks": {
            "actual": len(guided_all_prior),
            "required_minimum": MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS,
            "passed": len(guided_all_prior)
            >= MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS,
        },
        "guided_all_prior_unrepresented_families": {
            "actual": len({record["family"] for record in guided_all_prior}),
            "required_minimum": MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES,
            "passed": len({record["family"] for record in guided_all_prior})
            >= MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES,
        },
    }
    confirmation_indices = [
        record["candidate_index"] for record in confirmation
    ]
    guided_indices = [record["candidate_index"] for record in guided]
    if (
        set(confirmation_indices) & set(guided_indices)
        or {record["problem_sha256"] for record in confirmation}
        & {record["problem_sha256"] for record in guided}
        or {
            (
                record["directory"], record["problem"],
                record["problem_file"], record["domain_file"],
            )
            for record in confirmation
        }
        & {
            (
                record["directory"], record["problem"],
                record["problem_file"], record["domain_file"],
            )
            for record in guided
        }
    ):
        raise SourceAuditError("V11 source-split cohorts overlap")
    gate = {
        "outcome_blind": True,
        "resource_exclusions_ineligible": True,
        "availability": {
            "supported_tasks": len(supported),
            "supported_families": len(by_family),
            "supported_candidate_indices_sha256": _digest([
                record["candidate_index"] for record in supported
            ]),
            "shadow_unrepresented": _stratum_indices(
                supported, shadow_unrepresented
            ),
            "all_prior_unrepresented": _stratum_indices(
                supported, all_prior_unrepresented
            ),
            "post_confirmation_remaining_tasks": post_confirmation_remaining,
            "guided_b_maximum_under_family_cap": guided_cap_capacity,
            "guided_b_target_tasks": GUIDED_TARGET_TASKS,
            "guided_b_max_tasks_per_family": MAX_GUIDED_TASKS_PER_FAMILY,
        },
        "clauses": clauses,
        "cohort_disjointness": {
            "candidate_index_overlap": 0,
            "source_identity_overlap": 0,
            "problem_sha256_overlap": 0,
            "passed": True,
        },
    }
    gate["passed"] = (
        all(clause["passed"] for clause in clauses.values())
        and gate["cohort_disjointness"]["passed"]
    )
    cohorts = {
        "confirmation_a": {
            "role": CONFIRMATION_ROLE,
            "candidate_indices": confirmation_indices,
            "candidate_indices_sha256": _digest(confirmation_indices),
        },
        "guided_b": {
            "role": GUIDED_ROLE,
            "top_up_role": GUIDED_TOP_UP_ROLE,
            "base_candidate_indices": [
                record["candidate_index"] for record in guided_base
            ],
            "top_up_candidate_indices": [
                record["candidate_index"] for record in guided_top_up
            ],
            "candidate_indices": guided_indices,
            "candidate_indices_sha256": _digest(guided_indices),
        },
    }
    return gate, cohorts


def _run_candidate(
    record: dict,
    *,
    shard_index: int,
    position: int,
    benchmarks: Path,
    task_tmp: Path,
    stage: Path,
    code_manifest_sha256: str,
    repository_commit_id: str,
    candidate_origin: str = "v11-fresh",
) -> dict:
    try:
        import pdb_terminal_incidence_confirmation_translate_v11 as Translator
    except ImportError as err:
        raise SourceAuditError("V11 translator driver is unavailable") from err

    if candidate_origin not in {"v11-fresh", COMPUTE_CANARY_ORIGIN}:
        raise SourceAuditError("V11 candidate origin is not authorized")
    candidate_index = record["candidate_index"]
    expected_indices = candidate_indices_for_shard(shard_index)
    if (
        position not in (0, 1)
        or candidate_index != expected_indices[position]
    ):
        raise SourceAuditError("V11 candidate-to-shard mapping changed")
    work = task_tmp / "candidate-{:04d}".format(candidate_index)
    work_identity = _mkdir_private(work, "candidate-private working directory")
    snapshot, snapshot_files = _snapshot_source(record, benchmarks, work)
    stdout_raw = work / "stdout.raw"
    stderr_raw = work / "stderr.raw"
    stdout_fd = stderr_fd = None
    start_r = start_w = limit_r = limit_w = norm_r = norm_w = None
    process = None
    normalization_raw = b""
    contract = resource_contract()
    contract_sha = _digest(contract)
    try:
        capture_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            capture_flags |= os.O_NOFOLLOW
        stdout_fd = os.open(stdout_raw, capture_flags, 0o600)
        stderr_fd = os.open(stderr_raw, capture_flags, 0o600)
        start_r, start_w = os.pipe()
        limit_r, limit_w = os.pipe()
        norm_r, norm_w = os.pipe()
        command = [
            str(PINNED_PYTHON), "-B", str(TRANSLATOR_DRIVER),
            "--start-fd", str(start_r),
            "--limit-evidence-fd", str(limit_w),
            "--normalization-evidence-fd", str(norm_w),
            "--", str(snapshot_files["domain"][0]),
            str(snapshot_files["problem"][0]),
        ]
        child_env = {
            "PATH": CONTROLLED_PATH,
            "LANG": "C",
            "LC_ALL": "C",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": str(work / "pycache"),
            "TMPDIR": str(work),
        }
        process = subprocess.Popen(
            command,
            cwd=work,
            env=child_env,
            stdin=subprocess.DEVNULL,
            stdout=stdout_fd,
            stderr=stderr_fd,
            close_fds=True,
            pass_fds=(start_r, limit_w, norm_w),
            preexec_fn=_child_preexec,
        )
        os.close(stdout_fd)
        stdout_fd = None
        os.close(stderr_fd)
        stderr_fd = None
        os.close(start_r)
        start_r = None
        os.close(limit_w)
        limit_w = None
        os.close(norm_w)
        norm_w = None
        limit_raw = _read_pipe_record(
            limit_r, "child limit evidence", HANDSHAKE_SECONDS
        )
        os.close(limit_r)
        limit_r = None
        parent_limits = _parent_limit_observation(process.pid)
        parent_isolation = _parent_isolation_observation(process.pid)
        child_limits = _validate_child_limit_evidence(
            _load_pipe_json(limit_raw, "child limit evidence"),
            process.pid,
            parent_isolation,
        )
        if os.write(start_w, b"G") != 1:
            raise InfrastructureAuditError("cannot release V11 translator child")
        os.close(start_w)
        start_w = None
        try:
            returncode = process.wait(timeout=CHILD_WALL_SECONDS)
        except subprocess.TimeoutExpired as err:
            _kill_process_group(process)
            raise InfrastructureAuditError(
                "candidate wall watchdog expired"
            ) from err
        normalization_raw = _read_pipe_record(
            norm_r, "normalization evidence", HANDSHAKE_SECONDS
        )
        os.close(norm_r)
        norm_r = None
        if not _process_group_absent(process.pid):
            _kill_process_group(process)
            raise InfrastructureAuditError(
                "candidate left a live process-group descendant"
            )
    except BaseException:
        # The leader may already have exited while a same-group descendant
        # still holds an evidence pipe.  Always kill and verify the group.
        if process is not None:
            _kill_process_group(process)
        raise
    finally:
        for descriptor in (
            stdout_fd, stderr_fd, start_r, start_w, limit_r, limit_w,
            norm_r, norm_w,
        ):
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except OSError:
                    pass

    stdout_name = "candidate-{:04d}.stdout.prefix".format(candidate_index)
    stderr_name = "candidate-{:04d}.stderr.prefix".format(candidate_index)
    stdout = _capture_evidence(
        stdout_raw, stage / stdout_name, stdout_name, "translator stdout"
    )
    stderr = _capture_evidence(
        stderr_raw, stage / stderr_name, stderr_name, "translator stderr"
    )
    normalization_value = _load_pipe_json(
        normalization_raw, "normalization evidence"
    )
    if normalization_value is not None:
        normalization_value = _normalization_evidence(normalization_value)
    sas_path = work / "output.sas"
    partial_sas = None
    sas = None
    sas_sha256 = None
    sas_bytes = None
    if returncode == 0:
        if normalization_value is None:
            raise SourceAuditError("successful translation lacks normalization")
        try:
            parsed = Translator.parse_and_hash_sas(sas_path)
        except Exception as err:
            raise SourceAuditError("successful translator produced invalid SAS") from err
        if (
            type(parsed) is not dict
            or set(parsed) != {"sas", "sas_bytes", "sas_sha256"}
            or type(parsed["sas"]) is not dict
            or type(parsed["sas_bytes"]) is not int
            or parsed["sas_bytes"] < 0
            or not _is_sha256(parsed["sas_sha256"])
        ):
            raise SourceAuditError("V11 SAS parser contract changed")
        sas = parsed["sas"]
        sas_bytes = parsed["sas_bytes"]
        sas_sha256 = parsed["sas_sha256"]
        sas_identity = _identity(sas_path.lstat())
        _unlink_verified(sas_path, sas_identity, "output.sas")
        status = "success"
        exclusion_kind = None
        support_determined = True
        reasons = _support_reasons(
            sas, normalization_value["num_normalized_axioms"]
        )
        supported = not reasons
    elif returncode == 31:
        if normalization_value is not None or os.path.lexists(sas_path):
            raise SourceAuditError("input rejection produced forbidden evidence")
        status = "input-rejected"
        exclusion_kind = None
        support_determined = True
        reasons = ["translation-input-rejected"]
        supported = False
    elif returncode in (20, 21):
        partial_sas = _hash_optional_sas(sas_path)
        status = "resource-excluded"
        exclusion_kind = "memory" if returncode == 20 else "time"
        support_determined = False
        reasons = None
        supported = None
    else:
        raise InfrastructureAuditError(
            "translator returned ambiguous exit {}".format(returncode)
        )
    snapshot = _verify_and_remove_snapshots(snapshot, snapshot_files)
    _rmdir_empty(work, work_identity, "candidate-private working directory")
    return {
        "schema": CANDIDATE_SCHEMA,
        **copy.deepcopy(record),
        "logical_shard_index": shard_index,
        "position_in_shard": position,
        "candidate_origin": candidate_origin,
        "translation_attempted": True,
        "translator_command": [
            "PINNED_PYTHON", "-B",
            "experiments/pdb_terminal_incidence_confirmation_translate_v11.py",
            "--", record["domain_file"], record["problem_file"],
        ],
        "code_manifest_sha256": code_manifest_sha256,
        "repository_commit_id": repository_commit_id,
        "resource_contract": contract,
        "resource_contract_sha256": contract_sha,
        "child_limit_attestation": child_limits,
        "parent_prlimit_observation": parent_limits,
        "parent_isolation_observation": parent_isolation,
        "process_returncode": returncode,
        "complete_process_group_reaped": True,
        "stdout": stdout,
        "stderr": stderr,
        "normalization": normalization_value,
        "sas": sas,
        "sas_bytes": sas_bytes,
        "sas_sha256": sas_sha256,
        "partial_sas_evidence": partial_sas,
        "status": status,
        "resource_exclusion_kind": exclusion_kind,
        "support_determined": support_determined,
        "supported": supported,
        "support_exclusion_reasons": reasons,
        "eligible_for_cohort": supported is True,
        "source_snapshot": snapshot,
    }


def _valid_revision(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 40
        and not any(char not in "0123456789abcdef" for char in value)
    )


def _execution_environment(
    *,
    shard_index: int,
    code_manifest_sha256: str,
    inventory_sha256: str,
    repository_commit_id: str,
    task_tmp: Path,
) -> dict:
    job_id = os.environ.get("SLURM_ARRAY_JOB_ID")
    task_id = os.environ.get("SLURM_ARRAY_TASK_ID")
    restart_text = os.environ.get("SLURM_RESTART_COUNT", "0")
    if (
        not isinstance(job_id, str)
        or not job_id.isdigit()
        or task_id != str(shard_index)
        or not restart_text.isdigit()
        or int(restart_text) != 0
        or os.environ.get("TMPDIR") != str(task_tmp)
        or os.environ.get("PATH") != CONTROLLED_PATH
        or os.environ.get("LANG") != "C"
        or os.environ.get("LC_ALL") != "C"
        or os.environ.get("PYTHONNOUSERSITE") != "1"
        or os.environ.get("PYTHONDONTWRITEBYTECODE") != "1"
        or os.environ.get("PYTHONPATH") is not None
        or os.environ.get("PYTHONHOME") is not None
        or os.environ.get("VIRTUAL_ENV") is not None
        or not _valid_revision(repository_commit_id)
    ):
        raise InfrastructureAuditError("V11 task execution environment changed")
    task_identity = _directory_identity(task_tmp, "V11 task TMPDIR")
    task_info = task_tmp.lstat()
    if (
        stat.S_IMODE(task_info.st_mode) != 0o700
        or task_info.st_uid != os.getuid()
    ):
        raise InfrastructureAuditError("V11 task TMPDIR is not private and owned")
    if any(task_tmp.iterdir()):
        raise InfrastructureAuditError("V11 task TMPDIR is not initially empty")
    python_raw, python_identity = _read_regular(
        PINNED_PYTHON, "pinned V11 Python", expected_sha256=PINNED_PYTHON_SHA256
    )
    del python_raw
    return {
        "schema": TASK_ENVIRONMENT_SCHEMA,
        "array_job_id": job_id,
        "array_task_id": shard_index,
        "slurm_restart_count": 0,
        "candidate_indices": list(candidate_indices_for_shard(shard_index)),
        "task_tmp_identity": task_identity,
        "code_manifest_sha256": code_manifest_sha256,
        "source_inventory_sha256": inventory_sha256,
        "repository_commit_id": repository_commit_id,
        "pinned_python_identity": python_identity,
        "pinned_python_sha256": PINNED_PYTHON_SHA256,
        "prior_campaign_payloads_read": [],
        "prior_campaign_payloads_reused": [],
    }


def _require_output_root(path: Path) -> dict:
    identity = _directory_identity(path, "V11 output root")
    info = Path(path).lstat()
    if (
        stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.getuid()
    ):
        raise InfrastructureAuditError("V11 output root mode or owner changed")
    return identity


def _publish_completed_shard(
    *,
    output_dir: Path,
    final: Path,
    stage: Path,
    stage_identity: dict,
    environment: dict,
    manifest_evidence: dict,
    candidates: list[dict],
    candidate_indices: tuple[int, int],
    shard_index: int,
    array_task_count: int,
    campaign: str,
    candidate_origin: str,
    source_inventory_sha256: str,
    code_manifest_sha256: str,
    repository_commit_id: str,
    whole_campaign_rerun: bool,
) -> dict:
    """Publish one two-candidate shard through the shared V11 protocol."""
    if (
        campaign not in {"v11-full-census", COMPUTE_CANARY_CAMPAIGN}
        or candidate_origin not in {"v11-fresh", COMPUTE_CANARY_ORIGIN}
        or (campaign == "v11-full-census") != (candidate_origin == "v11-fresh")
        or (campaign == "v11-full-census") != whole_campaign_rerun
        or len(candidates) != TASKS_PER_SHARD
        or any(
            candidate.get("candidate_origin") != candidate_origin
            for candidate in candidates
        )
    ):
        raise SourceAuditError("V11 shard campaign provenance changed")
    result = {
        "schema": SHARD_SCHEMA,
        "campaign": campaign,
        "whole_campaign_rerun": whole_campaign_rerun,
        "logical_shard_index": shard_index,
        "array_task_count": array_task_count,
        "candidate_indices": list(candidate_indices),
        "candidate_count": TASKS_PER_SHARD,
        "candidates": candidates,
        "candidate_origin_counts": {candidate_origin: TASKS_PER_SHARD},
        "prior_campaign_payloads_read": [],
        "prior_campaign_shards_used": 0,
        "source_inventory_sha256": source_inventory_sha256,
        "code_manifest_sha256": code_manifest_sha256,
        "repository_commit_id": repository_commit_id,
        "resource_contract_sha256": _digest(resource_contract()),
    }
    claim = {
        "schema": SHARD_CLAIM_SCHEMA,
        "campaign": campaign,
        "final_path": str(final),
        "logical_shard_index": shard_index,
        "array_task_count": array_task_count,
        "candidate_indices": list(candidate_indices),
        "array_job_id": environment["array_job_id"],
        "array_task_id": environment["array_task_id"],
        "slurm_restart_count": environment["slurm_restart_count"],
        "source_inventory_sha256": source_inventory_sha256,
        "code_manifest_sha256": code_manifest_sha256,
        "repository_commit_id": repository_commit_id,
    }
    environment.update({
        "manifest_evidence": manifest_evidence,
        "output_root_identity": _require_output_root(output_dir),
        "stage_directory_identity": stage_identity,
        "result_sha256": _digest(result),
    })
    payload_sha256 = {
        "claim.json": atomic_exclusive_bytes(
            stage / "claim.json", canonical_json(claim), "V11 shard claim"
        ),
        "result.json": atomic_exclusive_bytes(
            stage / "result.json", canonical_json(result), "V11 shard result"
        ),
        "environment.json": atomic_exclusive_bytes(
            stage / "environment.json",
            canonical_json(environment),
            "V11 shard environment",
        ),
    }
    expected_names = {
        "claim.json", "result.json", "environment.json",
        *(
            "candidate-{:04d}.{}.prefix".format(candidate_index, stream)
            for candidate_index in candidate_indices
            for stream in ("stdout", "stderr")
        ),
    }
    actual_names = {entry.name for entry in stage.iterdir()}
    if actual_names != expected_names or any(
        entry.is_symlink() for entry in stage.iterdir()
    ):
        raise SourceAuditError("V11 staged shard tree changed")
    if (
        _directory_identity(stage, "V11 shard staging directory")["inode"]
        != stage_identity["inode"]
    ):
        raise SourceAuditError("V11 shard staging directory was replaced")
    for name in expected_names - payload_sha256.keys():
        payload_sha256[name] = sha256_file(stage / name, "V11 shard payload")
    expectations = {
        name: Publication.FileExpectation(sha256=digest, mode=0o400)
        for name, digest in payload_sha256.items()
    }
    completion_metadata = {
        "schema": SHARD_COMPLETION_METADATA_SCHEMA,
        "campaign": campaign,
        "logical_shard_index": shard_index,
        "candidate_indices": list(candidate_indices),
        "claim_sha256": payload_sha256["claim.json"],
        "result_sha256": payload_sha256["result.json"],
        "environment_sha256": payload_sha256["environment.json"],
    }
    try:
        publication = Publication.publish_immutable_shard(
            stage, final, expectations, completion_metadata
        )
    except Publication.PublicationError as err:
        raise SourceAuditError("cannot publish V11 shard") from err
    published_raw, _ = _read_regular(
        final / "result.json", "published V11 shard result"
    )
    digest = hashlib.sha256(published_raw).hexdigest()
    summary = {
        "candidate_indices": list(candidate_indices),
        "logical_shard_index": shard_index,
        "claim_sha256": payload_sha256["claim.json"],
        "completion_sha256": publication.completion_sha256,
        "result_sha256": digest,
        "statuses": dict(sorted(Counter(
            candidate["status"] for candidate in candidates
        ).items())),
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return summary


def compute_canary_shard_path(directory: Path) -> Path:
    return Path(directory) / "shard-0000-of-0001"


def _compute_canary_records() -> list[dict]:
    fixture_root = COMPUTE_CANARY_FIXTURE_ROOT
    if fixture_root.is_symlink():
        raise SourceAuditError("V11 compute-canary fixture root is a symlink")
    _directory_identity(fixture_root, "V11 compute-canary fixture root")
    domain = fixture_root / "domain.pddl"
    domain_sha256 = sha256_file(domain, "V11 compute-canary domain")
    records = []
    for index in range(TASKS_PER_SHARD):
        problem_name = "problem-{}.pddl".format(index)
        problem = fixture_root / problem_name
        records.append({
            "candidate_index": index,
            "directory": "v11-synthetic-canary",
            "family": "v11-synthetic-canary",
            "problem": problem_name,
            "domain_file": "domain.pddl",
            "problem_file": problem_name,
            "domain_sha256": domain_sha256,
            "problem_sha256": sha256_file(
                problem, "V11 compute-canary problem"
            ),
            "canonical_path": problem_name,
            "is_shadow_family": False,
            "is_shadow_unrepresented": False,
            "is_all_prior_represented": False,
            "is_all_prior_unrepresented": False,
            "aliases": [],
        })
    return records


def compute_canary(args) -> dict:
    """Run the one-row synthetic canary through the production child path."""
    output_dir = Path(os.path.abspath(args.output_dir))
    code_manifest = Path(os.path.abspath(args.code_manifest))
    tmp_root = Path(os.path.abspath(args.tmp_root))
    if (
        output_dir != COMPUTE_CANARY_OUTPUT
        or tmp_root != COMPUTE_CANARY_TMP_ROOT
        or output_dir.is_symlink()
    ):
        raise SourceAuditError("V11 compute-canary namespace changed")
    _require_output_root(output_dir)
    tmp_root_identity = _directory_identity(tmp_root, "V11 canary TMP root")
    if (
        tmp_root_identity["mode"] != 0o700
        or tmp_root_identity["uid"] != os.getuid()
    ):
        raise InfrastructureAuditError(
            "V11 canary TMP root is not private and owned"
        )
    manifest_evidence = validate_code_manifest(
        code_manifest, args.code_manifest_sha256
    )
    records = _compute_canary_records()
    fixture_sha256 = _digest(records)
    job_id = os.environ.get("SLURM_ARRAY_JOB_ID", "")
    task_tmp = tmp_root / "task-{}-0".format(job_id)
    environment = _execution_environment(
        shard_index=0,
        code_manifest_sha256=args.code_manifest_sha256,
        inventory_sha256=fixture_sha256,
        repository_commit_id=args.repository_commit_id,
        task_tmp=task_tmp,
    )
    final = compute_canary_shard_path(output_dir)
    stage = output_dir / ".stage-{}-0000".format(job_id)
    if os.path.lexists(final) or os.path.lexists(stage):
        raise SourceAuditError("V11 compute-canary namespace is not empty")
    stage_identity = _mkdir_private(
        stage, "V11 compute-canary staging directory"
    )
    candidate_indices = (0, 1)
    candidates = [
        _run_candidate(
            records[candidate_index],
            shard_index=0,
            position=position,
            benchmarks=COMPUTE_CANARY_FIXTURE_ROOT,
            task_tmp=task_tmp,
            stage=stage,
            code_manifest_sha256=args.code_manifest_sha256,
            repository_commit_id=args.repository_commit_id,
            candidate_origin=COMPUTE_CANARY_ORIGIN,
        )
        for position, candidate_index in enumerate(candidate_indices)
    ]
    if any(task_tmp.iterdir()):
        raise SourceAuditError("compute-canary private work leaked content")
    return _publish_completed_shard(
        output_dir=output_dir,
        final=final,
        stage=stage,
        stage_identity=stage_identity,
        environment=environment,
        manifest_evidence=manifest_evidence,
        candidates=candidates,
        candidate_indices=candidate_indices,
        shard_index=0,
        array_task_count=1,
        campaign=COMPUTE_CANARY_CAMPAIGN,
        candidate_origin=COMPUTE_CANARY_ORIGIN,
        source_inventory_sha256=fixture_sha256,
        code_manifest_sha256=args.code_manifest_sha256,
        repository_commit_id=args.repository_commit_id,
        whole_campaign_rerun=False,
    )


def scan(args) -> dict:
    if (
        args.num_shards != ARRAY_TASKS
        or type(args.shard_index) is not int
        or not 0 <= args.shard_index < ARRAY_TASKS
        or Path(args.output_dir).is_symlink()
    ):
        raise SourceAuditError("V11 scan mapping changed")
    output_dir = Path(os.path.abspath(args.output_dir))
    inventory_path = Path(os.path.abspath(args.inventory_manifest))
    code_manifest = Path(os.path.abspath(args.code_manifest))
    benchmarks = Path(os.path.abspath(args.benchmarks))
    tmp_root = Path(os.path.abspath(args.tmp_root))
    _require_output_root(output_dir)
    tmp_root_identity = _directory_identity(tmp_root, "V11 TMP root")
    if (
        tmp_root_identity["mode"] != 0o700
        or tmp_root_identity["uid"] != os.getuid()
    ):
        raise InfrastructureAuditError("V11 TMP root is not private and owned")
    if not _is_sha256(args.inventory_sha256):
        raise SourceAuditError("V11 inventory hash is invalid")
    inventory_raw, inventory = _load_canonical_json(
        inventory_path, "V11 source inventory"
    )
    if hashlib.sha256(inventory_raw).hexdigest() != args.inventory_sha256:
        raise SourceAuditError("V11 source inventory hash changed")
    records = validate_inventory_manifest(inventory)
    manifest_evidence = validate_code_manifest(
        code_manifest, args.code_manifest_sha256
    )
    job_id = os.environ.get("SLURM_ARRAY_JOB_ID", "")
    task_tmp = tmp_root / "task-{}-{}".format(job_id, args.shard_index)
    environment = _execution_environment(
        shard_index=args.shard_index,
        code_manifest_sha256=args.code_manifest_sha256,
        inventory_sha256=args.inventory_sha256,
        repository_commit_id=args.repository_commit_id,
        task_tmp=task_tmp,
    )
    final = shard_path(output_dir, args.shard_index)
    stage = output_dir / ".stage-{}-{:04d}".format(job_id, args.shard_index)
    if os.path.lexists(final) or os.path.lexists(stage):
        raise SourceAuditError("V11 shard namespace is not empty")
    stage_identity = _mkdir_private(stage, "V11 shard staging directory")
    candidate_indices = candidate_indices_for_shard(args.shard_index)
    candidates = [
        _run_candidate(
            records[candidate_index],
            shard_index=args.shard_index,
            position=position,
            benchmarks=benchmarks,
            task_tmp=task_tmp,
            stage=stage,
            code_manifest_sha256=args.code_manifest_sha256,
            repository_commit_id=args.repository_commit_id,
        )
        for position, candidate_index in enumerate(candidate_indices)
    ]
    if any(task_tmp.iterdir()):
        raise SourceAuditError("candidate-private working directory leaked content")
    return _publish_completed_shard(
        output_dir=output_dir,
        final=final,
        stage=stage,
        stage_identity=stage_identity,
        environment=environment,
        manifest_evidence=manifest_evidence,
        candidates=candidates,
        candidate_indices=candidate_indices,
        shard_index=args.shard_index,
        array_task_count=ARRAY_TASKS,
        campaign="v11-full-census",
        candidate_origin="v11-fresh",
        source_inventory_sha256=args.inventory_sha256,
        code_manifest_sha256=args.code_manifest_sha256,
        repository_commit_id=args.repository_commit_id,
        whole_campaign_rerun=True,
    )


INVENTORY_RECORD_KEYS = frozenset({
    "candidate_index", "directory", "family", "problem", "domain_file",
    "problem_file", "domain_sha256", "problem_sha256", "canonical_path",
    "is_shadow_family", "is_shadow_unrepresented",
    "is_all_prior_represented", "is_all_prior_unrepresented", "aliases",
})
CANDIDATE_RESULT_KEYS = INVENTORY_RECORD_KEYS | frozenset({
    "schema", "logical_shard_index", "position_in_shard",
    "candidate_origin", "translation_attempted", "translator_command",
    "code_manifest_sha256", "repository_commit_id", "resource_contract",
    "resource_contract_sha256", "child_limit_attestation",
    "parent_prlimit_observation", "parent_isolation_observation",
    "process_returncode",
    "complete_process_group_reaped", "stdout", "stderr", "normalization",
    "sas", "sas_bytes", "sas_sha256", "partial_sas_evidence", "status",
    "resource_exclusion_kind", "support_determined", "supported",
    "support_exclusion_reasons", "eligible_for_cohort", "source_snapshot",
})
SAS_KEYS = frozenset({
    "sas_version", "metric", "num_variables", "num_mutex_groups",
    "num_operators", "num_effects", "num_conditional_effects",
    "num_zero_cost_operators", "min_operator_cost", "max_operator_cost",
    "num_serialized_axioms",
})


def _valid_identity(value, *, expected_mode: int | None) -> bool:
    return (
        type(value) is dict
        and set(value) == {"device", "inode", "mode", "uid", "size"}
        and all(type(value[key]) is int for key in value)
        and value["device"] >= 0
        and value["inode"] > 0
        and value["uid"] >= 0
        and value["size"] >= 0
        and (
            expected_mode is None
            or value["mode"] == expected_mode
        )
    )


def _output_tree_directory_record(
    relative_path: str, observed: os.stat_result,
) -> dict:
    if (
        type(relative_path) is not str
        or not relative_path
        or "/" in relative_path
        or not stat.S_ISDIR(observed.st_mode)
        or stat.S_IMODE(observed.st_mode) != 0o500
        or observed.st_uid != os.getuid()
    ):
        raise SourceAuditError("V11 shard directory identity changed")
    return {
        "path": relative_path,
        "device": observed.st_dev,
        "inode": observed.st_ino,
        "uid": observed.st_uid,
        "gid": observed.st_gid,
        "mode": "0500",
    }


def _output_tree_file_record(
    relative_path: str,
    raw: bytes,
    identity: dict,
    observed: os.stat_result,
) -> dict:
    if (
        type(relative_path) is not str
        or not relative_path
        or not stat.S_ISREG(observed.st_mode)
        or identity != _identity(observed)
        or stat.S_IMODE(observed.st_mode) != 0o400
        or observed.st_uid != os.getuid()
        or observed.st_nlink != 1
    ):
        raise SourceAuditError("V11 output-tree file identity changed")
    return {
        "path": relative_path,
        "device": observed.st_dev,
        "inode": observed.st_ino,
        "uid": observed.st_uid,
        "gid": observed.st_gid,
        "mode": "0400",
        "nlink": 1,
        "bytes": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _validate_stream_evidence(
    value, prefix: Path, expected_name: str, label: str
) -> None:
    if (
        type(value) is not dict
        or set(value) != {
            "total_bytes", "sha256", "retained_path", "retained_bytes",
            "retained_sha256", "retention_limit_bytes", "truncated",
            "tail_base64", "tail_bytes",
        }
        or value.get("retained_path") != expected_name
        or type(value.get("total_bytes")) is not int
        or value["total_bytes"] < 0
        or not _is_sha256(value.get("sha256"))
        or type(value.get("retained_bytes")) is not int
        or value["retained_bytes"] != min(
            value["total_bytes"], STREAM_PREFIX_BYTES
        )
        or not _is_sha256(value.get("retained_sha256"))
        or value.get("retention_limit_bytes") != STREAM_PREFIX_BYTES
        or type(value.get("truncated")) is not bool
        or value["truncated"] is not (
            value["total_bytes"] > value["retained_bytes"]
        )
        or type(value.get("tail_base64")) is not str
        or type(value.get("tail_bytes")) is not int
        or value["tail_bytes"] != min(value["total_bytes"], STREAM_TAIL_BYTES)
    ):
        raise SourceAuditError("{} evidence changed".format(label))
    try:
        tail = base64.b64decode(value["tail_base64"], validate=True)
    except (ValueError, base64.binascii.Error) as err:
        raise SourceAuditError("{} tail encoding changed".format(label)) from err
    raw, identity = _read_regular(prefix, label)
    if (
        identity["mode"] != 0o400
        or len(raw) != value["retained_bytes"]
        or hashlib.sha256(raw).hexdigest() != value["retained_sha256"]
        or len(tail) != value["tail_bytes"]
    ):
        raise SourceAuditError("{} retained bytes changed".format(label))
    if not value["truncated"] and (
        value["total_bytes"] != len(raw)
        or value["sha256"] != hashlib.sha256(raw).hexdigest()
        or tail != raw[-STREAM_TAIL_BYTES:]
    ):
        raise SourceAuditError("{} complete stream changed".format(label))


def _validate_sas_summary(value) -> None:
    integer_fields = (
        "sas_version", "metric", "num_variables", "num_mutex_groups",
        "num_operators", "num_effects", "num_conditional_effects",
        "num_zero_cost_operators", "num_serialized_axioms",
    )
    optional = ("min_operator_cost", "max_operator_cost")
    if (
        type(value) is not dict
        or set(value) != SAS_KEYS
        or any(type(value[key]) is not int or value[key] < 0
               for key in integer_fields)
        or any(value[key] is not None and (
            type(value[key]) is not int or value[key] < 0
        ) for key in optional)
        or value["sas_version"] != 3
        or value["metric"] not in (0, 1)
        or (value["num_operators"] == 0) is not (
            value["min_operator_cost"] is None
            and value["max_operator_cost"] is None
        )
        or (
            value["num_operators"] > 0
            and value["min_operator_cost"] > value["max_operator_cost"]
        )
    ):
        raise SourceAuditError("V11 SAS summary changed")


def _validate_snapshot(value, inventory_record: dict) -> None:
    if (
        type(value) is not dict
        or set(value) != {
            "schema", "files", "candidate_private_working_directory",
            "source_hashes_verified_before_use",
            "identity_and_sha256_verified_after_use",
            "exact_snapshot_files_removed",
        }
        or value.get("schema") != SOURCE_SNAPSHOT_SCHEMA
        or value.get("candidate_private_working_directory") is not True
        or value.get("source_hashes_verified_before_use") is not True
        or value.get("identity_and_sha256_verified_after_use") is not True
        or value.get("exact_snapshot_files_removed") is not True
        or type(value.get("files")) is not list
        or len(value["files"]) != 2
    ):
        raise SourceAuditError("V11 source snapshot evidence changed")
    for item, role, file_key, hash_key, name in zip(
        value["files"],
        ("domain", "problem"),
        ("domain_file", "problem_file"),
        ("domain_sha256", "problem_sha256"),
        ("domain.pddl", "problem.pddl"),
    ):
        if (
            type(item) is not dict
            or set(item) != {
                "role", "source_file", "source_identity", "snapshot_name",
                "snapshot_identity_before", "snapshot_identity_after",
                "bytes", "sha256",
            }
            or item["role"] != role
            or item["source_file"] != inventory_record[file_key]
            or item["snapshot_name"] != name
            or item["sha256"] != inventory_record[hash_key]
            or type(item["bytes"]) is not int
            or item["bytes"] <= 0
            or not _valid_identity(item["source_identity"], expected_mode=None)
            or not _valid_identity(
                item["snapshot_identity_before"], expected_mode=0o400
            )
            or item["snapshot_identity_after"]
            != item["snapshot_identity_before"]
            or item["source_identity"]["size"] != item["bytes"]
            or item["snapshot_identity_before"]["size"] != item["bytes"]
        ):
            raise SourceAuditError("V11 source snapshot file changed")


def _validate_candidate_record(
    task: dict,
    inventory_record: dict,
    *,
    shard_index: int,
    position: int,
    shard_directory: Path,
    code_manifest_sha256: str,
    repository_commit_id: str,
) -> None:
    if (
        type(task) is not dict
        or set(task) != CANDIDATE_RESULT_KEYS
        or any(task.get(key) != inventory_record[key]
               for key in INVENTORY_RECORD_KEYS)
        or task.get("schema") != CANDIDATE_SCHEMA
        or task.get("logical_shard_index") != shard_index
        or task.get("position_in_shard") != position
        or task.get("candidate_origin") != "v11-fresh"
        or task.get("translation_attempted") is not True
        or task.get("code_manifest_sha256") != code_manifest_sha256
        or task.get("repository_commit_id") != repository_commit_id
        or task.get("resource_contract") != resource_contract()
        or task.get("resource_contract_sha256") != _digest(resource_contract())
        or task.get("complete_process_group_reaped") is not True
    ):
        raise SourceAuditError("V11 candidate record changed")
    index = inventory_record["candidate_index"]
    expected_command = [
        "PINNED_PYTHON", "-B",
        "experiments/pdb_terminal_incidence_confirmation_translate_v11.py",
        "--", inventory_record["domain_file"], inventory_record["problem_file"],
    ]
    if task.get("translator_command") != expected_command:
        raise SourceAuditError("V11 translator command record changed")
    child = task.get("child_limit_attestation")
    if (
        type(child) is not dict
        or set(child) != {
            "schema", "pid", "process_group", "rlimit_as", "rlimit_cpu",
            "no_new_privs", "seccomp_mode", "seccomp_filters", "threads",
        }
        or child.get("schema") != SCHEMA + "/child-limit-evidence/v1"
        or type(child.get("pid")) is not int
        or child["pid"] <= 0
        or child.get("process_group") != child["pid"]
        or child.get("rlimit_as")
        != [ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES]
        or child.get("rlimit_cpu")
        != [CPU_SOFT_SECONDS, CPU_HARD_SECONDS]
        or child.get("no_new_privs") != 1
        or child.get("seccomp_mode") != 2
        or type(child.get("seccomp_filters")) is not int
        or child["seccomp_filters"] < 1
        or child.get("threads") != 1
    ):
        raise SourceAuditError("V11 child-limit attestation changed")
    parent = task.get("parent_prlimit_observation")
    if (
        type(parent) is not dict
        or set(parent) != {
            "tool_sha256", "command", "stdout_sha256", "rlimit_as",
            "rlimit_cpu",
        }
        or parent.get("tool_sha256") != PRLIMIT_SHA256
        or parent.get("rlimit_as")
        != [ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES]
        or parent.get("rlimit_cpu")
        != [CPU_SOFT_SECONDS, CPU_HARD_SECONDS]
        or not _is_sha256(parent.get("stdout_sha256"))
        or type(parent.get("command")) is not list
        or parent["command"].count("CHILD_PID") != 1
    ):
        raise SourceAuditError("V11 parent limit observation changed")
    isolation = task.get("parent_isolation_observation")
    if (
        type(isolation) is not dict
        or set(isolation) != {
            "status_sha256", "process_group", "no_new_privs",
            "seccomp_mode", "seccomp_filters", "threads",
            "process_creation_syscalls_denied", "libseccomp_sha256",
        }
        or not _is_sha256(isolation.get("status_sha256"))
        or isolation.get("process_group") != child["pid"]
        or isolation.get("no_new_privs") != 1
        or isolation.get("seccomp_mode") != 2
        or isolation.get("seccomp_filters") != child["seccomp_filters"]
        or isolation.get("threads") != 1
        or isolation.get("process_creation_syscalls_denied")
        != list(DENIED_PROCESS_SYSCALLS)
        or isolation.get("libseccomp_sha256") != LIBSECCOMP_SHA256
    ):
        raise SourceAuditError("V11 parent isolation observation changed")
    for stream in ("stdout", "stderr"):
        name = "candidate-{:04d}.{}.prefix".format(index, stream)
        _validate_stream_evidence(
            task.get(stream), shard_directory / name, name,
            "candidate {} {}".format(index, stream),
        )
    normalization = task.get("normalization")
    if normalization is not None:
        _normalization_evidence(normalization)
    status = task.get("status")
    returncode = task.get("process_returncode")
    if status == "success":
        _validate_sas_summary(task.get("sas"))
        expected_reasons = _support_reasons(
            task["sas"], normalization["num_normalized_axioms"]
        ) if normalization is not None else None
        valid = (
            returncode == 0
            and normalization is not None
            and type(task.get("sas_bytes")) is int
            and task["sas_bytes"] > 0
            and _is_sha256(task.get("sas_sha256"))
            and task.get("partial_sas_evidence") is None
            and task.get("resource_exclusion_kind") is None
            and task.get("support_determined") is True
            and type(task.get("supported")) is bool
            and task.get("support_exclusion_reasons") == expected_reasons
            and task.get("supported") is (len(expected_reasons) == 0)
            and task.get("eligible_for_cohort") is task.get("supported")
        )
    elif status == "input-rejected":
        valid = (
            returncode == 31
            and normalization is None
            and task.get("sas") is None
            and task.get("sas_bytes") is None
            and task.get("sas_sha256") is None
            and task.get("partial_sas_evidence") is None
            and task.get("resource_exclusion_kind") is None
            and task.get("support_determined") is True
            and task.get("supported") is False
            and task.get("support_exclusion_reasons")
            == ["translation-input-rejected"]
            and task.get("eligible_for_cohort") is False
        )
    elif status == "resource-excluded":
        partial = task.get("partial_sas_evidence")
        valid_partial = partial is None or (
            type(partial) is dict
            and set(partial) == {"bytes", "sha256", "discarded"}
            and type(partial["bytes"]) is int
            and partial["bytes"] >= 0
            and _is_sha256(partial["sha256"])
            and partial["discarded"] is True
        )
        expected_kind = "memory" if returncode == 20 else (
            "time" if returncode == 21 else None
        )
        valid = (
            expected_kind is not None
            and valid_partial
            and task.get("sas") is None
            and task.get("sas_bytes") is None
            and task.get("sas_sha256") is None
            and task.get("resource_exclusion_kind") == expected_kind
            and task.get("support_determined") is False
            and task.get("supported") is None
            and task.get("support_exclusion_reasons") is None
            and task.get("eligible_for_cohort") is False
        )
    else:
        valid = False
    _validate_snapshot(task.get("source_snapshot"), inventory_record)
    if not valid:
        raise SourceAuditError("V11 candidate disposition changed")


def _load_shard_directory(
    directory: Path,
    inventory_records: list[dict],
    *,
    shard_index: int,
    job_id: str,
    code_manifest_sha256: str,
    inventory_sha256: str,
    repository_commit_id: str,
) -> tuple[list[dict], dict, list[dict], dict]:
    info = Path(directory).lstat()
    if (
        Path(directory).is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o500
        or info.st_uid != os.getuid()
    ):
        raise SourceAuditError("V11 shard directory identity changed")
    candidate_indices = candidate_indices_for_shard(shard_index)
    expected_names = {
        "claim.json", "result.json", "environment.json",
        *(
            "candidate-{:04d}.{}.prefix".format(index, stream)
            for index in candidate_indices for stream in ("stdout", "stderr")
        ),
        Publication.COMPLETION_NAME,
    }
    entries = list(Path(directory).iterdir())
    if (
        {entry.name for entry in entries} != expected_names
        or any(entry.is_symlink() or not entry.is_file() for entry in entries)
    ):
        raise SourceAuditError("V11 shard directory tree changed")
    claim_raw, claim = _load_canonical_json(
        Path(directory) / "claim.json", "V11 shard claim"
    )
    result_raw, result = _load_canonical_json(
        Path(directory) / "result.json", "V11 shard result"
    )
    environment_raw, environment = _load_canonical_json(
        Path(directory) / "environment.json", "V11 shard environment"
    )
    expected_claim = {
        "schema": SHARD_CLAIM_SCHEMA,
        "campaign": "v11-full-census",
        "final_path": str(Path(directory)),
        "logical_shard_index": shard_index,
        "array_task_count": ARRAY_TASKS,
        "candidate_indices": list(candidate_indices),
        "array_job_id": job_id,
        "array_task_id": shard_index,
        "slurm_restart_count": 0,
        "source_inventory_sha256": inventory_sha256,
        "code_manifest_sha256": code_manifest_sha256,
        "repository_commit_id": repository_commit_id,
    }
    if claim != expected_claim:
        raise SourceAuditError("V11 shard claim changed")
    result_keys = {
        "schema", "campaign", "whole_campaign_rerun",
        "logical_shard_index", "array_task_count", "candidate_indices",
        "candidate_count", "candidates", "candidate_origin_counts",
        "prior_campaign_payloads_read", "prior_campaign_shards_used",
        "source_inventory_sha256", "code_manifest_sha256",
        "repository_commit_id", "resource_contract_sha256",
    }
    tasks = result.get("candidates") if type(result) is dict else None
    if (
        type(result) is not dict
        or set(result) != result_keys
        or result.get("schema") != SHARD_SCHEMA
        or result.get("campaign") != "v11-full-census"
        or result.get("whole_campaign_rerun") is not True
        or result.get("logical_shard_index") != shard_index
        or result.get("array_task_count") != ARRAY_TASKS
        or result.get("candidate_indices") != list(candidate_indices)
        or result.get("candidate_count") != TASKS_PER_SHARD
        or type(tasks) is not list
        or len(tasks) != TASKS_PER_SHARD
        or result.get("candidate_origin_counts") != {"v11-fresh": 2}
        or result.get("prior_campaign_payloads_read") != []
        or result.get("prior_campaign_shards_used") != 0
        or result.get("source_inventory_sha256") != inventory_sha256
        or result.get("code_manifest_sha256") != code_manifest_sha256
        or result.get("repository_commit_id") != repository_commit_id
        or result.get("resource_contract_sha256") != _digest(resource_contract())
    ):
        raise SourceAuditError("V11 shard result changed")
    for position, candidate_index in enumerate(candidate_indices):
        _validate_candidate_record(
            tasks[position], inventory_records[candidate_index],
            shard_index=shard_index, position=position,
            shard_directory=Path(directory),
            code_manifest_sha256=code_manifest_sha256,
            repository_commit_id=repository_commit_id,
        )
    environment_keys = {
        "schema", "array_job_id", "array_task_id", "slurm_restart_count",
        "candidate_indices", "task_tmp_identity", "code_manifest_sha256",
        "source_inventory_sha256", "repository_commit_id",
        "pinned_python_identity", "pinned_python_sha256",
        "prior_campaign_payloads_read", "prior_campaign_payloads_reused",
        "manifest_evidence", "output_root_identity",
        "stage_directory_identity", "result_sha256",
    }
    if (
        type(environment) is not dict
        or set(environment) != environment_keys
        or environment.get("schema") != TASK_ENVIRONMENT_SCHEMA
        or environment.get("array_job_id") != job_id
        or environment.get("array_task_id") != shard_index
        or environment.get("slurm_restart_count") != 0
        or environment.get("candidate_indices") != list(candidate_indices)
        or environment.get("code_manifest_sha256") != code_manifest_sha256
        or environment.get("source_inventory_sha256") != inventory_sha256
        or environment.get("repository_commit_id") != repository_commit_id
        or environment.get("pinned_python_sha256") != PINNED_PYTHON_SHA256
        or environment.get("prior_campaign_payloads_read") != []
        or environment.get("prior_campaign_payloads_reused") != []
        or environment.get("result_sha256")
        != hashlib.sha256(result_raw).hexdigest()
        or not _valid_identity(
            environment.get("task_tmp_identity"), expected_mode=0o700
        )
        or not _valid_identity(
            environment.get("pinned_python_identity"), expected_mode=None
        )
        or not _valid_identity(
            environment.get("output_root_identity"), expected_mode=0o700
        )
        or not _valid_identity(
            environment.get("stage_directory_identity"), expected_mode=0o700
        )
    ):
        raise SourceAuditError("V11 shard environment changed")
    manifest = environment.get("manifest_evidence")
    if (
        type(manifest) is not dict
        or set(manifest) != {
            "code_manifest_sha256", "code_manifest_records",
            "pinned_python_sha256", "prlimit_sha256", "libseccomp_sha256",
            "translator_file_count", "translator_files_sha256",
        }
        or manifest.get("code_manifest_sha256") != code_manifest_sha256
        or manifest.get("code_manifest_records") != len(CODE_MANIFEST_FILES)
        or manifest.get("pinned_python_sha256") != PINNED_PYTHON_SHA256
        or manifest.get("prlimit_sha256") != PRLIMIT_SHA256
        or manifest.get("libseccomp_sha256") != LIBSECCOMP_SHA256
        or manifest.get("translator_file_count") != 38
        or not _is_sha256(manifest.get("translator_files_sha256"))
    ):
        raise SourceAuditError("V11 task manifest evidence changed")
    payload_entries = [
        entry for entry in entries if entry.name != Publication.COMPLETION_NAME
    ]
    payload_manifest = []
    tree_records = []
    for entry in sorted(payload_entries, key=lambda path: path.name):
        raw, identity = _read_regular(entry, "V11 shard payload")
        observed = entry.lstat()
        if (
            identity["mode"] != 0o400
            or observed.st_dev != identity["device"]
            or observed.st_ino != identity["inode"]
            or observed.st_uid != identity["uid"]
            or observed.st_size != identity["size"]
            or observed.st_nlink != 1
        ):
            raise SourceAuditError("V11 shard payload mode changed")
        payload_manifest.append({
            "device": identity["device"],
            "gid": observed.st_gid,
            "inode": identity["inode"],
            "mode": "0400",
            "name": entry.name,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size": len(raw),
            "uid": identity["uid"],
        })
        tree_records.append(_output_tree_file_record(
            "{}/{}".format(Path(directory).name, entry.name),
            raw,
            identity,
            observed,
        ))
    completion_path = Path(directory) / Publication.COMPLETION_NAME
    completion_raw, completion_identity = _read_regular(
        completion_path,
        "V11 shard completion marker",
    )
    completion_observed = completion_path.lstat()
    completion_tree_record = _output_tree_file_record(
        "{}/{}".format(
            Path(directory).name, Publication.COMPLETION_NAME
        ),
        completion_raw,
        completion_identity,
        completion_observed,
    )
    try:
        completion = json.loads(completion_raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SourceAuditError("V11 shard completion marker is not JSON") from err
    canonical_completion = canonical_json(completion) + b"\n"
    expected_metadata = {
        "schema": SHARD_COMPLETION_METADATA_SCHEMA,
        "campaign": "v11-full-census",
        "logical_shard_index": shard_index,
        "candidate_indices": list(candidate_indices),
        "claim_sha256": hashlib.sha256(claim_raw).hexdigest(),
        "result_sha256": hashlib.sha256(result_raw).hexdigest(),
        "environment_sha256": hashlib.sha256(environment_raw).hexdigest(),
    }
    expected_directory_identity = {
        "device": info.st_dev,
        "inode": info.st_ino,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": "0500",
    }
    if (
        type(completion) is not dict
        or set(completion) != {
            "schema", "metadata", "files", "final_directory"
        }
        or completion_raw != canonical_completion
        or completion.get("schema")
        != Publication.COMPLETION_SCHEMA
        or completion.get("metadata") != expected_metadata
        or completion.get("files") != payload_manifest
        or completion.get("final_directory") != expected_directory_identity
    ):
        raise SourceAuditError("V11 shard completion marker changed")
    tree_records.append(completion_tree_record)
    tree_records.sort(key=lambda record: record["path"])
    directory_record = _output_tree_directory_record(
        Path(directory).name, info
    )
    return tasks, environment, tree_records, directory_record


def _publish_or_match(path: Path, value: dict, label: str) -> str:
    raw = canonical_json(value)
    if os.path.lexists(path):
        existing, loaded = _load_canonical_json(path, label)
        if existing != raw or loaded != value:
            raise SourceAuditError("{} changed during seal recovery".format(label))
        return hashlib.sha256(existing).hexdigest()
    return atomic_exclusive_bytes(path, raw, label)


def _launch_resource_profile() -> dict:
    return {
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


def _live_launch_root(path: Path, label: str) -> dict:
    absolute = Path(os.path.abspath(path))
    try:
        info = absolute.lstat()
    except OSError as err:
        raise SourceAuditError("cannot inspect {}".format(label)) from err
    if (
        absolute.is_symlink() or not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o700
        or info.st_uid != os.getuid()
    ):
        raise SourceAuditError("{} is not a private owned directory".format(label))
    return {
        "path": str(absolute), "canonical_path": str(absolute),
        "device": info.st_dev, "inode": info.st_ino,
        "mode": "0700", "uid": info.st_uid, "gid": info.st_gid,
    }


def _validate_launch_receipt(launch_sha: str, launch_receipt: dict) -> None:
    receipt_keys = {
        "schema", "campaign", "job_id", "submission_token", "accepted_utc",
        "repository_commit_id", "source_inventory_sha256",
        "code_manifest_sha256", "launch_intent_sha256",
        "sbatch_result_sha256", "resource_profile", "root_identities",
        "slurm_program", "launch_recovered", "recovery_evidence",
        "prior_runtime_payloads_read", "prior_runtime_payload_bytes_read",
        "prior_runtime_payloads_reused", "selective_recovery_authorized",
        "whole_campaign_fresh", "preflight_authorization",
    }
    roots = {
        "artifact_dir": ARTIFACT_DIR,
        "log_root": LOG_ROOT,
        "output_dir": DEFAULT_OUTPUT,
        "tmpdir_root": TMP_ROOT,
    }
    root_values = launch_receipt.get("root_identities")
    slurm = launch_receipt.get("slurm_program")
    recovered = launch_receipt.get("launch_recovered")
    recovery = launch_receipt.get("recovery_evidence")
    preflight = launch_receipt.get("preflight_authorization")
    accepted_text = launch_receipt.get("accepted_utc")
    try:
        accepted = datetime.datetime.fromisoformat(accepted_text)
    except (TypeError, ValueError) as err:
        raise SourceAuditError("V11 launch acceptance timestamp changed") from err
    if (
        accepted.tzinfo is None
        or accepted.utcoffset() != datetime.timedelta(0)
        or accepted.isoformat(timespec="seconds") != accepted_text
    ):
        raise SourceAuditError("V11 launch acceptance timestamp changed")
    if (
        not _is_sha256(launch_sha)
        or type(launch_receipt) is not dict
        or set(launch_receipt) != receipt_keys
        or hashlib.sha256(canonical_json(launch_receipt)).hexdigest()
        != launch_sha
        or launch_receipt.get("schema") != SCHEMA + "/launch/v1"
        or launch_receipt.get("campaign") != "v11-full-census"
        or not isinstance(launch_receipt.get("job_id"), str)
        or not launch_receipt["job_id"].isdigit()
        or TOKEN_RE.fullmatch(launch_receipt.get("submission_token", "")) is None
        or not _valid_revision(launch_receipt.get("repository_commit_id"))
        or not _is_sha256(launch_receipt.get("source_inventory_sha256"))
        or not _is_sha256(launch_receipt.get("code_manifest_sha256"))
        or not _is_sha256(launch_receipt.get("launch_intent_sha256"))
        or not _is_sha256(launch_receipt.get("sbatch_result_sha256"))
        or type(preflight) is not dict
        or set(preflight) != {
            "seal_repository_commit_id", "authorization_sha256",
            "compute_canary_attestation_sha256",
            "controller_publisher_canary_receipt_sha256",
            "code_manifest_sha256", "snapshot_consumed",
            "full_launch_authorized",
        }
        or not _valid_revision(preflight.get("seal_repository_commit_id"))
        or preflight.get("seal_repository_commit_id")
        != launch_receipt.get("repository_commit_id")
        or not _is_sha256(preflight.get("authorization_sha256"))
        or not _is_sha256(
            preflight.get("compute_canary_attestation_sha256")
        )
        or not _is_sha256(
            preflight.get("controller_publisher_canary_receipt_sha256")
        )
        or preflight.get("code_manifest_sha256")
        != launch_receipt.get("code_manifest_sha256")
        or preflight.get("snapshot_consumed") is not True
        or preflight.get("full_launch_authorized") is not True
        or launch_receipt.get("resource_profile") != _launch_resource_profile()
        or type(root_values) is not dict
        or set(root_values) != set(roots)
        or type(slurm) is not dict
        or set(slurm) != {
            "template_path", "template_sha256", "rendered_sha256",
            "rendered_bytes", "submission_mode", "path_argument",
        }
        or slurm.get("template_path") != str(SLURM_PROGRAM)
        or not _is_sha256(slurm.get("template_sha256"))
        or not _is_sha256(slurm.get("rendered_sha256"))
        or type(slurm.get("rendered_bytes")) is not int
        or slurm["rendered_bytes"] <= 0
        or slurm.get("submission_mode") != "stdin"
        or slurm.get("path_argument") is not False
        or type(recovered) is not bool
        or (not recovered and recovery is not None)
        or (recovered and (
            type(recovery) is not dict
            or recovery.get("job_id") != launch_receipt["job_id"]
            or recovery.get("no_resubmission") is not True
        ))
        or launch_receipt.get("prior_runtime_payloads_read") != 0
        or launch_receipt.get("prior_runtime_payload_bytes_read") != 0
        or launch_receipt.get("prior_runtime_payloads_reused") != 0
        or launch_receipt.get("selective_recovery_authorized") is not False
        or launch_receipt.get("whole_campaign_fresh") is not True
    ):
        raise SourceAuditError("V11 launch receipt changed")
    for name, path in roots.items():
        if root_values[name] != _live_launch_root(path, "V11 " + name):
            raise SourceAuditError("V11 launch root was replaced")
    raw, loaded = _load_canonical_json(LAUNCH_RECEIPT, "V11 launch receipt")
    if (
        loaded != launch_receipt
        or hashlib.sha256(raw).hexdigest() != launch_sha
        or _identity(LAUNCH_RECEIPT.lstat())["mode"] != 0o400
    ):
        raise SourceAuditError("V11 launch receipt file changed")


def _validate_scheduler_evidence(
    launch_receipt: dict,
    scheduler_rows: list[dict],
    scheduler_contract_rows: list[dict],
) -> None:
    profile = _launch_resource_profile()
    if (
        type(scheduler_rows) is not list
        or type(scheduler_contract_rows) is not list
        or len(scheduler_rows) != ARRAY_TASKS
        or len(scheduler_contract_rows) != ARRAY_TASKS
    ):
        raise SourceAuditError("V11 launch or scheduler evidence changed")
    for index, (row, contract) in enumerate(
        zip(scheduler_rows, scheduler_contract_rows)
    ):
        if (
            type(row) is not dict
            or set(row) != {
                "array_task", "state", "exit_code", "partition", "restarts",
            }
            or row != {
                "array_task": index,
                "state": "COMPLETED",
                "exit_code": "0:0",
                "partition": "fat",
                "restarts": 0,
            }
            or type(contract) is not dict
            or set(contract) != {
                "array_task", "account", "partition", "qos", "req_cpus",
                "req_mem", "time_limit", "state", "exit_code", "restarts",
                "job_name",
            }
            or contract.get("array_task") != index
            or contract.get("account") != profile["account"]
            or contract.get("partition") != profile["partition"]
            or contract.get("qos") != profile["qos"]
            or contract.get("req_cpus") != 1
            or contract.get("req_mem") != profile["mem"]
            or contract.get("time_limit") != profile["time"]
            or contract.get("state") != "COMPLETED"
            or contract.get("exit_code") != "0:0"
            or contract.get("restarts") != 0
            or contract.get("job_name") != "pdb-source-v11-{}".format(
                launch_receipt["submission_token"]
            )
        ):
            raise SourceAuditError("V11 scheduler all-success contract changed")


def _expected_root_entries() -> list[dict]:
    expected = {"source-inventory-v11.json": "file"}
    expected.update({
        shard_path(DEFAULT_OUTPUT, index).name: "directory"
        for index in range(ARRAY_TASKS)
    })
    return [
        {"name": name, "kind": expected[name]}
        for name in sorted(expected)
    ]


def _root_entry_plan() -> list[dict]:
    expected_records = _expected_root_entries()
    expected = {item["name"]: item["kind"] for item in expected_records}
    try:
        entries = list(DEFAULT_OUTPUT.iterdir())
    except OSError as err:
        raise SourceAuditError("cannot enumerate sealed V11 output root") from err
    actual = {}
    for entry in entries:
        if entry.is_symlink():
            raise SourceAuditError("V11 output root contains a symlink")
        if entry.is_file():
            kind = "file"
        elif entry.is_dir():
            kind = "directory"
        else:
            raise SourceAuditError("V11 output root contains a special entry")
        actual[entry.name] = kind
    if actual != expected:
        raise SourceAuditError("V11 output root entry set changed")
    return expected_records


def _classification_summaries(records: list[dict]) -> dict:
    outcomes = Counter(record["status"] for record in records)
    outcome_counts = {
        key: outcomes[key]
        for key in ("input-rejected", "resource-excluded", "success")
    }
    support_labels = [
        "supported" if record["supported"] is True else (
            "unsupported" if record["supported"] is False else "indeterminate"
        )
        for record in records
    ]
    statuses = Counter(support_labels)
    support_status_counts = {
        key: statuses[key]
        for key in ("indeterminate", "supported", "unsupported")
    }
    support_exclusion_counts = dict(sorted(Counter(
        reason
        for record in records
        for reason in (record["support_exclusion_reasons"] or [])
    ).items()))
    resource_records = [
        record for record in records if record["status"] == "resource-excluded"
    ]
    resource = Counter(
        record["resource_exclusion_kind"] for record in resource_records
    )
    resource_exclusion_counts = {
        key: resource[key] for key in ("memory", "time")
    }
    by_family = {}
    for family in sorted({record["family"] for record in resource_records}):
        selected = [record for record in resource_records if record["family"] == family]
        by_family[family] = {
            "memory": sum(
                record["resource_exclusion_kind"] == "memory" for record in selected
            ),
            "time": sum(
                record["resource_exclusion_kind"] == "time" for record in selected
            ),
            "total": len(selected),
        }
    return {
        "counts": {
            "candidates": len(records),
            "translation_attempts": sum(
                record["translation_attempted"] for record in records
            ),
            "support_determinate": sum(
                record["support_determined"] for record in records
            ),
            "supported": statuses["supported"],
            "unsupported": statuses["unsupported"],
            "indeterminate": statuses["indeterminate"],
            "cohort_eligible": sum(
                record["eligible_for_cohort"] for record in records
            ),
            "families": len({record["family"] for record in records}),
        },
        "outcome_counts": outcome_counts,
        "support_status_counts": support_status_counts,
        "support_exclusion_counts": support_exclusion_counts,
        "resource_exclusion_counts": resource_exclusion_counts,
        "resource_exclusions_by_family": by_family,
    }


def _existing_seal_prefix_is_valid() -> None:
    ordered = (
        SEAL_PLAN, TREE_STAGE, CENSUS_STAGE, SPLIT_STAGE,
        ATTESTATION_STAGE, ATTESTATION, EXECUTION_RECEIPT,
    )
    seen_missing = False
    for path in ordered:
        exists = os.path.lexists(path)
        if not exists:
            seen_missing = True
        elif seen_missing:
            raise SourceAuditError("V11 seal recovery stages are not a prefix")


def _verify_output_tree_stable(output_tree: dict, launch_receipt: dict) -> None:
    if _root_entry_plan() != _expected_root_entries():
        raise SourceAuditError("V11 output root changed during seal")
    if (
        _live_launch_root(DEFAULT_OUTPUT, "V11 output root")
        != launch_receipt["root_identities"]["output_dir"]
    ):
        raise SourceAuditError("V11 output root was replaced during seal")
    for directory in output_tree["directories"]:
        path = DEFAULT_OUTPUT / directory["path"]
        try:
            info = path.lstat()
        except OSError as err:
            raise SourceAuditError(
                "cannot inspect V11 shard directory during seal"
            ) from err
        if path.is_symlink() or _output_tree_directory_record(
            directory["path"], info
        ) != directory:
            raise SourceAuditError("V11 shard directory changed during seal")
    for item in output_tree["files"]:
        path = DEFAULT_OUTPUT / item["path"]
        raw, identity = _read_regular(path, "V11 output-tree file")
        try:
            observed = path.lstat()
        except OSError as err:
            raise SourceAuditError(
                "cannot inspect V11 output-tree file during seal"
            ) from err
        if _output_tree_file_record(
            item["path"], raw, identity, observed
        ) != item:
            raise SourceAuditError("V11 output-tree file changed during seal")


def seal_campaign(
    *,
    launch_sha: str,
    launch_receipt: dict,
    scheduler_rows: list[dict],
    scheduler_contract_rows: list[dict],
    scheduler_terminal_receipt_sha256: str,
    terminal_poll_receipt_sha256: str,
) -> dict:
    """Seal V11 only after the launcher has passed both scheduler gates."""
    _validate_launch_receipt(launch_sha, launch_receipt)
    _validate_scheduler_evidence(
        launch_receipt, scheduler_rows, scheduler_contract_rows
    )
    if (
        not _is_sha256(scheduler_terminal_receipt_sha256)
        or not _is_sha256(terminal_poll_receipt_sha256)
    ):
        raise SourceAuditError("V11 retained scheduler receipt hash changed")
    _existing_seal_prefix_is_valid()
    if any(TMP_ROOT.iterdir()):
        raise SourceAuditError("V11 task TMP root is not empty after success")

    # Publish the authenticated all-success gate before enumerating or opening
    # any worker payload.  Recovery can only reproduce this exact first link.
    expected_root_entries = _expected_root_entries()
    seal_plan = {
        "schema": SCHEMA + "/seal-plan/v1",
        "campaign": "v11-full-census",
        "launch_receipt_sha256": launch_sha,
        "source_inventory_sha256": launch_receipt[
            "source_inventory_sha256"
        ],
        "code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "job_id": launch_receipt["job_id"],
        "scheduler_rows": copy.deepcopy(scheduler_rows),
        "scheduler_rows_sha256": _digest(scheduler_rows),
        "scheduler_contract_rows": copy.deepcopy(scheduler_contract_rows),
        "scheduler_contract_rows_sha256": _digest(scheduler_contract_rows),
        "scheduler_terminal_receipt_sha256": (
            scheduler_terminal_receipt_sha256
        ),
        "terminal_poll_receipt_sha256": terminal_poll_receipt_sha256,
        "scheduler_gate_passed": True,
        "scheduler_gate_passed_before_payload_read": True,
        "scheduler_restarts": 0,
        "logical_shards": ARRAY_TASKS,
        "candidates": CANDIDATE_COUNT,
        "root_identities": copy.deepcopy(launch_receipt["root_identities"]),
        "expected_output_root_entries": expected_root_entries,
        "expected_output_root_entries_sha256": _digest(
            expected_root_entries
        ),
        "log_payloads_read": 0,
        "prior_runtime_payloads_read": 0,
        "preflight_authorization": copy.deepcopy(
            launch_receipt["preflight_authorization"]
        ),
    }
    seal_plan_sha = _publish_or_match(SEAL_PLAN, seal_plan, "V11 seal plan")

    root_entries = _root_entry_plan()
    if root_entries != expected_root_entries:
        raise SourceAuditError("V11 output root entry plan changed")
    inventory_raw, inventory = _load_canonical_json(
        DEFAULT_INVENTORY, "sealed V11 source inventory"
    )
    inventory_sha = hashlib.sha256(inventory_raw).hexdigest()
    if inventory_sha != launch_receipt["source_inventory_sha256"]:
        raise SourceAuditError("sealed V11 source inventory changed")
    inventory_records = validate_inventory_manifest(inventory)
    all_candidates = []
    environments = []
    inventory_check, inventory_identity = _read_regular(
        DEFAULT_INVENTORY, "sealed V11 source inventory identity"
    )
    if inventory_check != inventory_raw:
        raise SourceAuditError("sealed V11 source inventory changed")
    tree_records = [_output_tree_file_record(
        "source-inventory-v11.json",
        inventory_raw,
        inventory_identity,
        DEFAULT_INVENTORY.lstat(),
    )]
    directories = []
    for shard_index in range(ARRAY_TASKS):
        tasks, environment, shard_tree, directory_record = _load_shard_directory(
            shard_path(DEFAULT_OUTPUT, shard_index),
            inventory_records,
            shard_index=shard_index,
            job_id=launch_receipt["job_id"],
            code_manifest_sha256=launch_receipt["code_manifest_sha256"],
            inventory_sha256=inventory_sha,
            repository_commit_id=launch_receipt["repository_commit_id"],
        )
        all_candidates.extend(tasks)
        environments.append(environment)
        tree_records.extend(shard_tree)
        directories.append(directory_record)
    if (
        len(all_candidates) != CANDIDATE_COUNT
        or [record["candidate_index"] for record in all_candidates]
        != list(range(CANDIDATE_COUNT))
        or any(record["candidate_origin"] != "v11-fresh"
               for record in all_candidates)
    ):
        raise SourceAuditError("V11 full-census assembly changed")
    tree_records.sort(key=lambda record: record["path"])
    root_identity = copy.deepcopy(
        launch_receipt["root_identities"]["output_dir"]
    )
    output_tree = {
        "schema": SCHEMA + "/output-tree/v1",
        "root": str(DEFAULT_OUTPUT),
        "root_identity": root_identity,
        "directories_count": ARRAY_TASKS,
        "directories": directories,
        "files_count": len(tree_records),
        "files": tree_records,
        "sha256": _digest({
            "root_identity": root_identity,
            "directories": directories,
            "files": tree_records,
        }),
    }
    output_tree_sha = _digest(output_tree)
    tree_stage = {
        "schema": SCHEMA + "/tree-stage/v1",
        "seal_plan_sha256": seal_plan_sha,
        "output_tree": output_tree,
        "output_tree_sha256": output_tree_sha,
        "environment_records_sha256": _digest(environments),
    }
    tree_stage_sha = _publish_or_match(
        TREE_STAGE, tree_stage, "V11 output-tree stage"
    )

    summaries = _classification_summaries(all_candidates)
    census_stage = {
        "schema": SCHEMA + "/census-stage/v1",
        "tree_stage_sha256": tree_stage_sha,
        "candidate_count": CANDIDATE_COUNT,
        "candidate_indices_sha256": _digest(list(range(CANDIDATE_COUNT))),
        "candidate_origin_counts": {"v11-fresh": CANDIDATE_COUNT},
        "whole_campaign_rerun": True,
        "prior_campaign_payloads_read": [],
        "prior_campaign_shards_used": 0,
        "records_sha256": _digest(all_candidates),
        **copy.deepcopy(summaries),
    }
    census_stage_sha = _publish_or_match(
        CENSUS_STAGE, census_stage, "V11 census stage"
    )

    gate, cohorts = split_supported(all_candidates)
    split_stage = {
        "schema": SCHEMA + "/split-stage/v1",
        "census_stage_sha256": census_stage_sha,
        "split_seed": SPLIT_SEED,
        "split_rank_encoding": (
            "SHA256(seed || NUL || role || NUL || family || NUL || "
            "problem_sha256 || NUL || canonical_path)"
        ),
        "cohorts": cohorts,
        "cohorts_sha256": _digest(cohorts),
        "prelaunch_gate": gate,
        "confirmation_prelaunch_authorized": gate["passed"],
    }
    split_stage_sha = _publish_or_match(
        SPLIT_STAGE, split_stage, "V11 split stage"
    )

    manifest_evidence = environments[0]["manifest_evidence"]
    if any(
        environment["manifest_evidence"] != manifest_evidence
        for environment in environments
    ):
        raise SourceAuditError("V11 manifest evidence differs across tasks")
    attestation = {
        "schema": SCHEMA + "/attestation/v1",
        "campaign": "v11-full-census",
        "benchmark_revision": Inventory.BENCHMARK_REVISION,
        "translator_source_sha256": manifest_evidence[
            "translator_files_sha256"
        ],
        "source_inventory_sha256": inventory_sha,
        "source_inventory_records_sha256": inventory["records_sha256"],
        "code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "split_seed": SPLIT_SEED,
        "split_rank_encoding": split_stage["split_rank_encoding"],
        "split_role_labels": {
            "confirmation_a": CONFIRMATION_ROLE,
            "guided_b_base": GUIDED_ROLE,
            "guided_b_top_up": GUIDED_TOP_UP_ROLE,
        },
        "limits": resource_contract(),
        "full_census_fresh": True,
        "candidate_indices_sha256": census_stage["candidate_indices_sha256"],
        **copy.deepcopy(summaries),
        "records_sha256": census_stage["records_sha256"],
        "cohorts": cohorts,
        "cohorts_sha256": split_stage["cohorts_sha256"],
        "prelaunch_gate": gate,
        "confirmation_prelaunch_authorized": gate["passed"],
        "records": all_candidates,
    }
    attestation_raw = canonical_json(attestation)
    attestation_sha = hashlib.sha256(attestation_raw).hexdigest()
    attestation_stage = {
        "schema": SCHEMA + "/attestation-stage/v1",
        "split_stage_sha256": split_stage_sha,
        "attestation_path": str(ATTESTATION),
        "attestation_bytes": len(attestation_raw),
        "attestation_sha256": attestation_sha,
        "attestation_records_sha256": census_stage["records_sha256"],
        "cohorts_sha256": split_stage["cohorts_sha256"],
        "confirmation_prelaunch_authorized": gate["passed"],
    }
    attestation_stage_sha = _publish_or_match(
        ATTESTATION_STAGE, attestation_stage, "V11 attestation stage"
    )
    published_attestation_sha = _publish_or_match(
        ATTESTATION, attestation, "V11 source-audit attestation"
    )
    if published_attestation_sha != attestation_sha:
        raise SourceAuditError("V11 attestation hash changed")

    execution = {
        "schema": SCHEMA + "/execution/v1",
        "campaign": "v11-full-census",
        "benchmark_revision": Inventory.BENCHMARK_REVISION,
        "logical_shards": ARRAY_TASKS,
        "candidates": CANDIDATE_COUNT,
        "tasks_per_shard": TASKS_PER_SHARD,
        "fresh_full_census": True,
        "candidate_indices_sha256": census_stage["candidate_indices_sha256"],
        "launch_receipt_sha256": launch_sha,
        "source_inventory_sha256": inventory_sha,
        "code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "resource_profile": copy.deepcopy(launch_receipt["resource_profile"]),
        "scheduler_state_counts": {"COMPLETED": ARRAY_TASKS},
        "scheduler_rows": copy.deepcopy(scheduler_rows),
        "scheduler_rows_sha256": seal_plan["scheduler_rows_sha256"],
        "scheduler_contract_rows": copy.deepcopy(scheduler_contract_rows),
        "scheduler_contract_rows_sha256": seal_plan[
            "scheduler_contract_rows_sha256"
        ],
        "scheduler_terminal_receipt_sha256": (
            scheduler_terminal_receipt_sha256
        ),
        "terminal_poll_receipt_sha256": terminal_poll_receipt_sha256,
        "scheduler_gate_passed": True,
        "scheduler_gate_passed_before_payload_read": True,
        "output_tree": output_tree,
        "output_tree_sha256": output_tree_sha,
        "environment_records_sha256": tree_stage[
            "environment_records_sha256"
        ],
        "prior_runtime_payload": {
            "campaigns": ["v{}".format(index) for index in range(1, 11)],
            "paths_read": [],
            "bytes_read": 0,
            "records_read": 0,
            "payloads_reused": 0,
            "scientific_bytes_reused": 0,
            "reuse_authorized": False,
        },
        "partial_v11_reuse_authorized": False,
        "preflight_authorization": copy.deepcopy(
            launch_receipt["preflight_authorization"]
        ),
        "seal_recovery_protocol": "exclusive-five-stage-hash-chain-v1",
        "seal_plan_sha256": seal_plan_sha,
        "tree_stage_sha256": tree_stage_sha,
        "census_stage_sha256": census_stage_sha,
        "split_stage_sha256": split_stage_sha,
        "attestation_stage_sha256": attestation_stage_sha,
        "attestation_sha256": attestation_sha,
        "attestation_records_sha256": census_stage["records_sha256"],
        "cohorts_sha256": split_stage["cohorts_sha256"],
        **{
            key: copy.deepcopy(value)
            for key, value in summaries.items()
            if key != "counts"
        },
        "prelaunch_gate": gate,
        "source_audit_complete": True,
        "confirmation_prelaunch_authorized": gate["passed"],
    }
    _verify_output_tree_stable(output_tree, launch_receipt)
    execution_sha = _publish_or_match(
        EXECUTION_RECEIPT, execution, "V11 execution receipt"
    )
    summary = {
        "execution_receipt_sha256": execution_sha,
        "attestation_sha256": attestation_sha,
        "outcome_counts": summaries["outcome_counts"],
        "confirmation_prelaunch_authorized": gate["passed"],
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return summary


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("--output-dir", required=True, type=Path)
    scan_parser.add_argument("--inventory-manifest", required=True, type=Path)
    scan_parser.add_argument("--inventory-sha256", required=True)
    scan_parser.add_argument("--num-shards", required=True, type=int)
    scan_parser.add_argument("--shard-index", required=True, type=int)
    scan_parser.add_argument("--code-manifest", required=True, type=Path)
    scan_parser.add_argument("--code-manifest-sha256", required=True)
    scan_parser.add_argument("--repository-commit-id", required=True)
    scan_parser.add_argument("--tmp-root", required=True, type=Path)
    scan_parser.add_argument(
        "--benchmarks", type=Path, default=DEFAULT_BENCHMARKS
    )
    canary_parser = subparsers.add_parser("compute-canary")
    canary_parser.add_argument("--output-dir", required=True, type=Path)
    canary_parser.add_argument("--code-manifest", required=True, type=Path)
    canary_parser.add_argument("--code-manifest-sha256", required=True)
    canary_parser.add_argument("--repository-commit-id", required=True)
    canary_parser.add_argument("--tmp-root", required=True, type=Path)
    inventory_parser = subparsers.add_parser("inventory")
    inventory_parser.add_argument(
        "--benchmarks", type=Path, default=DEFAULT_BENCHMARKS
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "scan":
        scan(args)
    elif args.command == "compute-canary":
        compute_canary(args)
    elif args.command == "inventory":
        print(canonical_json(build_inventory_manifest(args.benchmarks)).decode("ascii"))
    else:
        raise SourceAuditError("unknown V11 source-audit command")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SourceAuditError as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
