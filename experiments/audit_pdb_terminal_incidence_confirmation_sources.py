#!/usr/bin/env python3
"""Audit and source-split the universal unseen confirmation inventory.

Every candidate is translated.  Unsupported language/cost cases are retained
as data rather than making an array task fail.  Infrastructure or provenance
failures still fail closed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import stat
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import pdb_terminal_incidence_confirmation_inventory as Inventory


class SourceAuditError(RuntimeError):
    pass


class InfrastructureAuditError(SourceAuditError):
    pass


SCHEMA = (
    "symbolic-search-heuristics/universal-unseen-confirmation-source-audit/v1"
)
INVENTORY_SCHEMA = SCHEMA + "/inventory"
SHARD_SCHEMA = SCHEMA + "/shard"
SHARD_COUNT = 820
CANDIDATE_COUNT = 1640
TASKS_PER_SHARD = 2
TASK_TIMEOUT_SECONDS = 2700
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
ALL_PRIOR_UNREPRESENTED_FAMILIES = (
    Inventory.ALL_PRIOR_UNREPRESENTED_FAMILIES
)
EXPECTED_INVENTORY_DIGESTS = {
    "all_path_records": Inventory.ALL_PATH_RECORDS_SHA256,
    "all_prior_families": Inventory.ALL_PRIOR_FAMILY_SEQUENCE_SHA256,
    "all_prior_unrepresented_families": (
        Inventory.ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
    ),
    "all_unique_problem_hashes": (
        Inventory.ALL_UNIQUE_PROBLEM_HASHES_SHA256
    ),
    "candidate_records": Inventory.CANDIDATE_RECORDS_SHA256,
    "cost_problem_hashes": Inventory.COST_PROBLEM_HASHES_SHA256,
    "directories": Inventory.DIRECTORY_SEQUENCE_SHA256,
    "alias_groups": Inventory.ALIAS_GROUPS_SHA256,
    "family_map": Inventory.FAMILY_MAP_SHA256,
    "prior_problem_hashes": Inventory.PRIOR_PROBLEM_HASHES_SHA256,
    "prior_identities": Inventory.PRIOR_IDENTITIES_SHA256,
    "prior_identity_ledger": Inventory.PRIOR_IDENTITY_LEDGER_SHA256,
    "prior_directory_family_map": (
        Inventory.PRIOR_DIRECTORY_FAMILY_MAP_SHA256
    ),
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

DEFAULT_BENCHMARKS = Inventory.DEFAULT_BENCHMARKS
DEFAULT_SHARDS = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v1"
)
DEFAULT_INVENTORY = DEFAULT_SHARDS / "source-inventory-v1.json"
DEFAULT_OUTPUT = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v1.json"
)
DEFAULT_CODE_MANIFEST = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_code.sha256"
)
REQUIREMENTS = SCRIPT_DIR / "requirements-pdb-terminal-incidence-shadow.txt"
CODE_MANIFEST_FILES = (
    "experiments/audit_pdb_terminal_incidence_confirmation_sources.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit.py",
    "experiments/pdb_terminal_incidence_confirmation_inventory.py",
    "experiments/pdb_terminal_incidence_shadow_cost_attestation.json",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/suite_wbh_operator_costs.json",
)
TRANSLATOR_SOURCE_SHA256 = (
    "c93a014324c4866cc9f83c456d75fc2ad9d4b397bae48411bdc0c757e2f88cbc"
)
TRANSLATOR_FILE_COUNT = 38
CONTROLLED_PATH = "/usr/bin:/bin"
UNSET_PYTHON_ENV = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")
PYTHON_CACHE_PREFIX_TEMPLATE = (
    "/tmp/symk-confirmation-source-audit-{array_job_id}-{array_task_id}"
)
TAIL_BYTES = 8192
PINNED_PYTHON_VERSION = "3.12.13"
PINNED_PYTHON_EXECUTABLE = (
    "/home/jendrik/.local/share/uv/python/"
    "cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
)
PINNED_PYTHON_EXECUTABLE_SHA256 = (
    "021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
)
PINNED_PYTHON_ENVIRONMENT_SHA256 = (
    "4256d52c7331ace41f456a98f21dda4485ab9dd82ac0eb11697291feb1da0819"
)
PINNED_REQUIREMENTS_SHA256 = (
    "9176e14c79ca81d624fd5eca3c6eb79b799ecb8f08b39301c7c250b97d526422"
)


def canonical_json(value) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii") + b"\n"
    except (TypeError, ValueError) as err:
        raise SourceAuditError("value is not canonical finite JSON") from err


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as err:
        raise SourceAuditError("cannot hash {}".format(path)) from err
    return digest.hexdigest()


def _is_sha256(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and not any(char not in "0123456789abcdef" for char in value)
    )


def atomic_exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_root = path.parent.parent / ".{}.publication-tmp".format(
        path.parent.name
    )
    temp_root.mkdir(parents=True, exist_ok=True)
    if temp_root.is_symlink() or not temp_root.is_dir():
        raise SourceAuditError("publication temp root is not a directory")
    descriptor = None
    temp_path = None
    try:
        descriptor, temp_name = tempfile.mkstemp(
            prefix=".{}-".format(path.name), suffix=".tmp", dir=temp_root
        )
        temp_path = Path(temp_name)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temp_path, path)
        except FileExistsError as err:
            raise SourceAuditError("refusing to overwrite {}".format(label)) from err
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except SourceAuditError:
        raise
    except OSError as err:
        raise SourceAuditError("cannot publish {}".format(label)) from err
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass
            except OSError as err:
                if not path.exists():
                    raise SourceAuditError(
                        "cannot clean unpublished {}".format(label)
                    ) from err
    return hashlib.sha256(raw).hexdigest()


def _atomic_json(path: Path, value) -> str:
    return atomic_exclusive_bytes(path, canonical_json(value), str(path))


def _load_canonical_json(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        info = path.lstat()
        raw = path.read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SourceAuditError("cannot load {}".format(label)) from err
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or not isinstance(value, dict)
        or raw != canonical_json(value)
    ):
        raise SourceAuditError("{} is not canonical and regular".format(label))
    return raw, value


def validate_execution_environment() -> None:
    if any(name in os.environ for name in UNSET_PYTHON_ENV):
        raise SourceAuditError("source-audit Python environment is not clean")
    try:
        expected_cache = PYTHON_CACHE_PREFIX_TEMPLATE.format(
            array_job_id=os.environ["SLURM_ARRAY_JOB_ID"],
            array_task_id=os.environ["SLURM_ARRAY_TASK_ID"],
        )
    except KeyError as err:
        raise SourceAuditError("source-audit Slurm identity is absent") from err
    if (
        os.environ.get("PYTHONNOUSERSITE") != "1"
        or os.environ.get("PATH") != CONTROLLED_PATH
        or os.environ.get("PYTHONDONTWRITEBYTECODE") != "1"
        or os.environ.get("PYTHONPYCACHEPREFIX") != expected_cache
        or sys.flags.no_user_site != 1
        or sys.dont_write_bytecode is not True
    ):
        raise SourceAuditError("source-audit execution environment changed")


def translator_source_digest() -> str:
    paths = tuple(sorted((REPO / "src" / "translate").rglob("*.py")))
    if len(paths) != TRANSLATOR_FILE_COUNT:
        raise SourceAuditError("translator source file set changed")
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(REPO).as_posix()
        if path.is_symlink() or not path.is_file():
            raise SourceAuditError("translator source is not regular")
        payload = path.read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    value = digest.hexdigest()
    if value != TRANSLATOR_SOURCE_SHA256:
        raise SourceAuditError("translator source tree changed")
    return value


def _environment_attestation(
    requirements_path: Path, *, verify_installed_files: bool
) -> dict:
    try:
        lines = requirements_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as err:
        raise SourceAuditError("cannot read environment requirements") from err
    requirements = {}
    for line in lines:
        if not line or line.startswith("#") or line.count("==") != 1:
            raise SourceAuditError("environment requirement is not exact")
        name, version = line.split("==")
        if not name or not version or name in requirements:
            raise SourceAuditError("environment requirements are malformed")
        requirements[name] = version
    manifest = []
    versions = {}
    for name, expected in sorted(requirements.items()):
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError as err:
            raise SourceAuditError(
                "required Python distribution is absent: {}".format(name)
            ) from err
        if distribution.version != expected or not distribution.files:
            raise SourceAuditError(
                "Python distribution changed: {}".format(name)
            )
        versions[name] = distribution.version
        if verify_installed_files:
            for relative in sorted(distribution.files, key=str):
                path = Path(distribution.locate_file(relative)).resolve()
                if not path.is_file():
                    raise SourceAuditError("installed distribution file is absent")
                manifest.append({
                    "distribution": name,
                    "path": str(relative),
                    "sha256": sha256_file(path),
                })
    if verify_installed_files:
        raw = json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        environment_sha256 = hashlib.sha256(raw).hexdigest()
        if environment_sha256 != PINNED_PYTHON_ENVIRONMENT_SHA256:
            raise SourceAuditError("installed Python environment changed")
    else:
        # The launcher performs the expensive installed-file audit once.  Each
        # of the 820 array elements rechecks versions and the interpreter, but
        # does not create a shared-filesystem metadata storm.
        environment_sha256 = PINNED_PYTHON_ENVIRONMENT_SHA256
    executable = Path(sys.executable).resolve()
    value = {
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "python_executable": str(executable),
        "python_executable_sha256": sha256_file(executable),
        "python_environment_sha256": environment_sha256,
        "python_distributions": versions,
        "python_requirements_sha256": sha256_file(requirements_path),
    }
    if (
        value["python_version"] != PINNED_PYTHON_VERSION
        or value["python_executable"] != PINNED_PYTHON_EXECUTABLE
        or value["python_executable_sha256"]
        != PINNED_PYTHON_EXECUTABLE_SHA256
        or value["python_requirements_sha256"] != PINNED_REQUIREMENTS_SHA256
    ):
        raise SourceAuditError("pinned Python environment changed")
    return value


def validate_code_manifest(
    path: Path,
    expected_sha256: str,
    *,
    verify_environment_files: bool = True,
) -> dict:
    try:
        raw = path.read_bytes()
        lines = raw.decode("ascii").splitlines()
    except (OSError, UnicodeDecodeError) as err:
        raise SourceAuditError("cannot read source-audit code manifest") from err
    if (
        not _is_sha256(expected_sha256)
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        raise SourceAuditError("source-audit code manifest hash changed")
    records = {}
    for line in lines:
        fields = line.split("  ", 1)
        if (
            len(fields) != 2
            or not _is_sha256(fields[0])
            or not fields[1]
            or fields[1] in records
        ):
            raise SourceAuditError("source-audit code manifest is malformed")
        records[fields[1]] = fields[0]
    if tuple(sorted(records)) != tuple(sorted(CODE_MANIFEST_FILES)):
        raise SourceAuditError("source-audit code manifest file set changed")
    for relative, expected in records.items():
        candidate = REPO / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise SourceAuditError("source-audit dependency is not regular")
        if sha256_file(candidate) != expected:
            raise SourceAuditError("source-audit dependency bytes changed")
    return {
        "code_manifest_sha256": expected_sha256,
        **_environment_attestation(
            REQUIREMENTS,
            verify_installed_files=verify_environment_files,
        ),
    }


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


def build_inventory_manifest(inventory: Inventory.Inventory) -> dict:
    groups = {group.problem_sha256: group for group in inventory.alias_groups}
    prior_family_ledger = [
        asdict(record) for record in inventory.prior_family_ledger
    ]
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
            "is_all_prior_unrepresented": (
                candidate.is_all_prior_unrepresented
            ),
            "aliases": [_candidate_json(alias) for alias in group.aliases],
        })
    if len(records) != CANDIDATE_COUNT:
        raise SourceAuditError("universal candidate count changed")
    return {
        "schema": INVENTORY_SCHEMA,
        "benchmark_revision": Inventory.BENCHMARK_REVISION,
        "cost_manifest_sha256": Inventory.COST_MANIFEST_SHA256,
        "shadow_attestation_sha256": Inventory.SHADOW_ATTESTATION_SHA256,
        "candidate_records_sha256": Inventory.CANDIDATE_RECORDS_SHA256,
        "alias_groups_sha256": Inventory.ALIAS_GROUPS_SHA256,
        "shadow_family_sequence_sha256": (
            Inventory.SHADOW_FAMILY_SEQUENCE_SHA256
        ),
        "shadow_unrepresented_family_sequence_sha256": (
            Inventory.SHADOW_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
        ),
        "all_prior_family_sequence_sha256": (
            Inventory.ALL_PRIOR_FAMILY_SEQUENCE_SHA256
        ),
        "all_prior_unrepresented_family_sequence_sha256": (
            Inventory.ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
        ),
        "prior_directory_family_map_sha256": (
            Inventory.PRIOR_DIRECTORY_FAMILY_MAP_SHA256
        ),
        "prior_family_ledger_sha256": Inventory.PRIOR_FAMILY_LEDGER_SHA256,
        "inventory_digests": dict(inventory.digests),
        "counts": {
            "candidates": len(records),
            "families": len(inventory.residue_families),
            "represented_shadow_families": len(
                inventory.represented_shadow_families
            ),
            "shadow_unrepresented_families": len(
                inventory.shadow_unrepresented_families
            ),
            "represented_all_prior_families": len(
                inventory.represented_all_prior_families
            ),
            "all_prior_unrepresented_families": len(
                inventory.all_prior_unrepresented_families
            ),
            "prior_family_provenance_records": len(prior_family_ledger),
            "source_aliases": sum(len(r["aliases"]) for r in records),
            "discarded_aliases": inventory.discarded_alias_count,
            "name_overlap_after_hash_filter": (
                inventory.name_overlap_after_hash_filter_count
            ),
            "prior_identity_overlap": inventory.prior_identity_overlap_count,
            "prior_problem_hash_overlap": (
                inventory.prior_problem_hash_overlap_count
            ),
        },
        "shadow_families": list(Inventory.SHADOW_FAMILIES),
        "represented_shadow_families": list(
            inventory.represented_shadow_families
        ),
        "shadow_unrepresented_families": list(
            inventory.shadow_unrepresented_families
        ),
        "represented_all_prior_families": list(
            inventory.represented_all_prior_families
        ),
        "all_prior_families": list(Inventory.ALL_PRIOR_FAMILIES),
        "all_prior_unrepresented_families": list(
            inventory.all_prior_unrepresented_families
        ),
        "prior_family_provenance": {
            "directory_to_family": dict(Inventory.PRIOR_DIRECTORY_TO_FAMILY),
            "ledger": prior_family_ledger,
        },
        "records_sha256": hashlib.sha256(canonical_json(records)).hexdigest(),
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
    records = value.get("records")
    provenance = value.get("prior_family_provenance")
    if (
        value.get("schema") != INVENTORY_SCHEMA
        or value.get("benchmark_revision") != Inventory.BENCHMARK_REVISION
        or value.get("cost_manifest_sha256") != Inventory.COST_MANIFEST_SHA256
        or value.get("shadow_attestation_sha256")
        != Inventory.SHADOW_ATTESTATION_SHA256
        or value.get("candidate_records_sha256")
        != Inventory.CANDIDATE_RECORDS_SHA256
        or value.get("alias_groups_sha256") != Inventory.ALIAS_GROUPS_SHA256
        or value.get("shadow_family_sequence_sha256")
        != Inventory.SHADOW_FAMILY_SEQUENCE_SHA256
        or value.get("shadow_unrepresented_family_sequence_sha256")
        != Inventory.SHADOW_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
        or value.get("all_prior_family_sequence_sha256")
        != Inventory.ALL_PRIOR_FAMILY_SEQUENCE_SHA256
        or value.get("all_prior_unrepresented_family_sequence_sha256")
        != Inventory.ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
        or value.get("prior_directory_family_map_sha256")
        != Inventory.PRIOR_DIRECTORY_FAMILY_MAP_SHA256
        or value.get("prior_family_ledger_sha256")
        != Inventory.PRIOR_FAMILY_LEDGER_SHA256
        or value.get("inventory_digests") != EXPECTED_INVENTORY_DIGESTS
        or value.get("shadow_families") != list(Inventory.SHADOW_FAMILIES)
        or value.get("all_prior_families")
        != list(Inventory.ALL_PRIOR_FAMILIES)
        or value.get("all_prior_unrepresented_families")
        != list(Inventory.ALL_PRIOR_UNREPRESENTED_FAMILIES)
        or not isinstance(provenance, dict)
        or set(provenance) != {"directory_to_family", "ledger"}
        or provenance["directory_to_family"]
        != Inventory.PRIOR_DIRECTORY_TO_FAMILY
        or hashlib.sha256(Inventory.canonical_json(
            provenance["directory_to_family"]
        )).hexdigest() != Inventory.PRIOR_DIRECTORY_FAMILY_MAP_SHA256
        or hashlib.sha256(Inventory.canonical_json(
            provenance["ledger"]
        )).hexdigest() != Inventory.PRIOR_FAMILY_LEDGER_SHA256
        or value.get("counts", {}).get("prior_family_provenance_records")
        != len(provenance["ledger"])
        or not isinstance(records, list)
        or len(records) != CANDIDATE_COUNT
        or value.get("counts", {}).get("candidates") != CANDIDATE_COUNT
        or value.get("counts", {}).get("name_overlap_after_hash_filter") != 0
        or value.get("counts", {}).get("prior_identity_overlap") != 0
        or value.get("counts", {}).get("prior_problem_hash_overlap") != 0
        or value.get("records_sha256")
        != hashlib.sha256(canonical_json(records)).hexdigest()
    ):
        raise SourceAuditError("source inventory identity changed")
    candidates = []
    alias_groups = []
    seen_hashes = set()
    for index, record in enumerate(records):
        required = {
            "candidate_index", "directory", "family", "problem",
            "domain_file", "problem_file", "domain_sha256",
            "problem_sha256", "canonical_path", "is_shadow_family",
            "is_shadow_unrepresented", "is_all_prior_represented",
            "is_all_prior_unrepresented", "aliases",
        }
        if (
            not isinstance(record, dict)
            or set(record) != required
            or record["candidate_index"] != index
            or record["canonical_path"] != record["problem_file"]
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
            or record["problem_sha256"] in seen_hashes
            or not isinstance(record["aliases"], list)
            or not record["aliases"]
        ):
            raise SourceAuditError("source inventory record changed")
        seen_hashes.add(record["problem_sha256"])
        candidate = {
            key: record[key]
            for key in (
                "directory", "family", "problem", "domain_file",
                "problem_file", "domain_sha256", "problem_sha256",
            )
        }
        aliases = record["aliases"]
        if (
            any(set(alias) != set(candidate) for alias in aliases)
            or aliases != sorted(aliases, key=_source_key)
            or aliases[0] != candidate
            or any(
                alias["problem_sha256"] != record["problem_sha256"]
                or alias["family"] != record["family"]
                for alias in aliases
            )
        ):
            raise SourceAuditError("source inventory aliases changed")
        candidates.append(candidate)
        alias_groups.append({
            "problem_sha256": record["problem_sha256"],
            "canonical": candidate,
            "aliases": aliases,
        })
    residue_families = sorted({record["family"] for record in records})
    represented_shadow = sorted(
        set(residue_families) & set(Inventory.SHADOW_FAMILIES)
    )
    shadow_unrepresented = sorted(
        set(residue_families) - set(Inventory.SHADOW_FAMILIES)
    )
    represented_all_prior = sorted(
        set(residue_families) & set(Inventory.ALL_PRIOR_FAMILIES)
    )
    all_prior_unrepresented = sorted(
        set(residue_families) - set(Inventory.ALL_PRIOR_FAMILIES)
    )
    if (
        value.get("represented_shadow_families") != represented_shadow
        or value.get("shadow_unrepresented_families")
        != shadow_unrepresented
        or value.get("represented_all_prior_families")
        != represented_all_prior
        or value.get("all_prior_unrepresented_families")
        != all_prior_unrepresented
        or value.get("counts", {}).get("families") != len(residue_families)
        or value.get("counts", {}).get("represented_shadow_families")
        != len(represented_shadow)
        or value.get("counts", {}).get("shadow_unrepresented_families")
        != len(shadow_unrepresented)
        or value.get("counts", {}).get("represented_all_prior_families")
        != len(represented_all_prior)
        or value.get("counts", {}).get("all_prior_unrepresented_families")
        != len(Inventory.ALL_PRIOR_UNREPRESENTED_FAMILIES)
    ):
        raise SourceAuditError("source inventory family provenance changed")
    if (
        hashlib.sha256(Inventory.canonical_json(candidates)).hexdigest()
        != Inventory.CANDIDATE_RECORDS_SHA256
        or hashlib.sha256(Inventory.canonical_json(sorted(
            alias_groups, key=lambda group: group["problem_sha256"]
        ))).hexdigest()
        != Inventory.ALIAS_GROUPS_SHA256
    ):
        raise SourceAuditError("source inventory record digest changed")
    return records


def load_inventory_manifest(path: Path, expected_sha256: str) -> tuple[str, list[dict]]:
    raw, value = _load_canonical_json(path, "source inventory")
    digest = hashlib.sha256(raw).hexdigest()
    if not _is_sha256(expected_sha256) or digest != expected_sha256:
        raise SourceAuditError("source inventory file hash changed")
    return digest, validate_inventory_manifest(value)


class SasReader:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError) as err:
            raise SourceAuditError("cannot read serialized SAS") from err
        self.index = 0

    def line(self) -> str:
        if self.index >= len(self.lines):
            raise SourceAuditError("unexpected end of serialized SAS")
        value = self.lines[self.index]
        self.index += 1
        return value

    def integer(self) -> int:
        value = self.line()
        try:
            return int(value)
        except ValueError as err:
            raise SourceAuditError("expected serialized SAS integer") from err

    def count(self, label: str) -> int:
        value = self.integer()
        if value < 0:
            raise SourceAuditError(
                "negative serialized SAS {} count".format(label)
            )
        return value

    def integers(self, count: int | None = None) -> list[int]:
        try:
            values = [int(value) for value in self.line().split()]
        except ValueError as err:
            raise SourceAuditError("expected serialized SAS integers") from err
        if count is not None and len(values) != count:
            raise SourceAuditError("serialized SAS field arity changed")
        return values

    def expect(self, expected: str) -> None:
        if self.line() != expected:
            raise SourceAuditError("serialized SAS marker changed")


def parse_sas(path: Path) -> dict:
    reader = SasReader(path)
    reader.expect("begin_version")
    version = reader.integer()
    reader.expect("end_version")
    if version != 3:
        raise SourceAuditError("serialized SAS version changed")
    reader.expect("begin_metric")
    metric = reader.integer()
    reader.expect("end_metric")
    if metric not in (0, 1):
        raise SourceAuditError("serialized SAS metric flag changed")
    num_variables = reader.count("variable")
    for _ in range(num_variables):
        reader.expect("begin_variable")
        reader.line()
        reader.integer()
        domain_size = reader.count("variable-domain")
        for _ in range(domain_size):
            reader.line()
        reader.expect("end_variable")
    num_mutex_groups = reader.count("mutex-group")
    for _ in range(num_mutex_groups):
        reader.expect("begin_mutex_group")
        for _ in range(reader.count("mutex-fact")):
            reader.integers(2)
        reader.expect("end_mutex_group")
    reader.expect("begin_state")
    for _ in range(num_variables):
        reader.integer()
    reader.expect("end_state")
    reader.expect("begin_goal")
    for _ in range(reader.count("goal-fact")):
        reader.integers(2)
    reader.expect("end_goal")
    num_operators = reader.count("operator")
    costs = []
    effects = 0
    conditional_effects = 0
    for _ in range(num_operators):
        reader.expect("begin_operator")
        reader.line()
        for _ in range(reader.count("prevail")):
            reader.integers(2)
        operator_effects = reader.count("operator-effect")
        effects += operator_effects
        for _ in range(operator_effects):
            fields = reader.integers()
            if not fields or fields[0] < 0 or len(fields) != 4 + 2 * fields[0]:
                raise SourceAuditError("serialized SAS effect changed")
            conditional_effects += fields[0] > 0
        cost = reader.integer()
        if cost < 0:
            raise SourceAuditError("negative serialized SAS operator cost")
        costs.append(cost)
        reader.expect("end_operator")
    num_axioms = reader.count("axiom")
    for _ in range(num_axioms):
        reader.expect("begin_rule")
        for _ in range(reader.count("axiom-condition")):
            reader.integers(2)
        reader.integers(3)
        reader.expect("end_rule")
    if reader.index != len(reader.lines):
        raise SourceAuditError("serialized SAS has trailing content")
    return {
        "sas_version": version,
        "metric": metric,
        "num_variables": num_variables,
        "num_mutex_groups": num_mutex_groups,
        "num_operators": num_operators,
        "num_effects": effects,
        "num_conditional_effects": conditional_effects,
        "num_zero_cost_operators": sum(cost == 0 for cost in costs),
        "min_operator_cost": min(costs) if costs else None,
        "max_operator_cost": max(costs) if costs else None,
        "num_serialized_axioms": num_axioms,
    }


def _count_normalized_axioms(domain: Path, problem: Path) -> int:
    source_root = str(REPO / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    from translate import normalize
    from translate.pddl_parser import pddl_file

    task = pddl_file.open(str(domain), str(problem))
    normalize.normalize(task, "axiom_based")
    return len(task.axioms)


def _bounded_stream_evidence(payload: bytes | None) -> dict:
    payload = payload or b""
    return {
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "tail": payload[-TAIL_BYTES:].decode("utf-8", "replace"),
        "tail_bytes": min(len(payload), TAIL_BYTES),
    }


def _regular_source(root: Path, relative: str, expected_sha256: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise SourceAuditError("unsafe benchmark source path")
    path = root / relative_path
    try:
        info = path.lstat()
        resolved = path.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError) as err:
        raise SourceAuditError("cannot resolve benchmark source") from err
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise SourceAuditError("benchmark source is not regular")
    if sha256_file(path) != expected_sha256:
        raise SourceAuditError("benchmark source bytes changed")
    return resolved


def _support_reasons(translation: dict, normalization: dict) -> list[str]:
    reasons = []
    if translation["status"] != "success":
        reasons.append("translation-" + translation["status"])
    else:
        sas = translation["sas"]
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
    if translation["status"] == "success":
        if normalization["status"] != "success":
            reasons.append("normalization-" + normalization["status"])
        elif normalization["num_normalized_axioms"] != 0:
            reasons.append("normalized-axioms")
    return reasons


def _valid_stream_evidence(value) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"bytes", "sha256", "tail", "tail_bytes"}
        and type(value["bytes"]) is int
        and value["bytes"] >= 0
        and _is_sha256(value["sha256"])
        and isinstance(value["tail"], str)
        and type(value["tail_bytes"]) is int
        and 0 <= value["tail_bytes"] <= min(value["bytes"], TAIL_BYTES)
    )


def _validate_scan_evidence(task: dict) -> None:
    translation = task.get("translation")
    normalization = task.get("normalization")
    if (
        not isinstance(translation, dict)
        or set(translation) != {
            "status", "timeout_seconds", "returncode", "stdout", "stderr",
            "sas", "sas_sha256", "error",
        }
        or translation["status"] not in {"success", "input-rejected"}
        or translation["timeout_seconds"] != TASK_TIMEOUT_SECONDS
        or not _valid_stream_evidence(translation["stdout"])
        or not _valid_stream_evidence(translation["stderr"])
        or (
            translation["sas_sha256"] is not None
            and not _is_sha256(translation["sas_sha256"])
        )
        or not isinstance(normalization, dict)
        or set(normalization) != {
            "status", "strategy", "num_normalized_axioms", "error",
        }
        or normalization["status"] not in {"success", "not-applicable"}
        or normalization["strategy"] != "axiom_based"
    ):
        raise SourceAuditError("source-audit evidence schema changed")
    status = translation["status"]
    if status != "success" and normalization["status"] != "not-applicable":
        raise SourceAuditError("failed translation normalization state changed")
    if status == "success":
        sas = translation["sas"]
        integer_fields = (
            "sas_version", "metric", "num_variables", "num_mutex_groups",
            "num_operators", "num_effects", "num_conditional_effects",
            "num_zero_cost_operators", "num_serialized_axioms",
        )
        optional_integer_fields = ("min_operator_cost", "max_operator_cost")
        if (
            translation["returncode"] != 0
            or translation["error"] is not None
            or not _is_sha256(translation["sas_sha256"])
            or not isinstance(sas, dict)
            or set(sas) != {*integer_fields, *optional_integer_fields}
            or any(type(sas[field]) is not int or sas[field] < 0
                   for field in integer_fields)
            or any(
                sas[field] is not None
                and (type(sas[field]) is not int or sas[field] < 0)
                for field in optional_integer_fields
            )
            or sas["sas_version"] != 3
            or sas["metric"] not in (0, 1)
        ):
            raise SourceAuditError("successful SAS evidence changed")
    elif (
        translation["sas"] is not None
        or translation["sas_sha256"] is not None
        or translation["returncode"] != 31
        or not isinstance(translation["error"], str)
        or not translation["error"]
    ):
        raise SourceAuditError("failed translation evidence changed")
    if normalization["status"] == "success":
        if (
            type(normalization["num_normalized_axioms"]) is not int
            or normalization["num_normalized_axioms"] < 0
            or normalization["error"] is not None
        ):
            raise SourceAuditError("normalization evidence changed")
    elif (
        translation["status"] == "success"
        or normalization["num_normalized_axioms"] is not None
        or normalization["error"] != "translator rejected frozen input"
    ):
        raise SourceAuditError("skipped normalization evidence changed")
    expected_command = [
        "PINNED_PYTHON", "-B", "-m", "translate",
        task["domain_file"], task["problem_file"],
    ]
    if task.get("translator_command") != expected_command:
        raise SourceAuditError("translator command evidence changed")


def _scan_task(record: dict, benchmarks: Path, timeout: int) -> dict:
    domain = _regular_source(
        benchmarks, record["domain_file"], record["domain_sha256"]
    )
    problem = _regular_source(
        benchmarks, record["problem_file"], record["problem_sha256"]
    )
    command = [
        sys.executable, "-B", "-m", "translate", str(domain), str(problem)
    ]
    child_environment = {
        "PATH": CONTROLLED_PATH,
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": os.environ["PYTHONPYCACHEPREFIX"],
        "PYTHONPATH": str(REPO / "src"),
    }
    with tempfile.TemporaryDirectory(prefix="confirmation-source-audit-") as tmp:
        try:
            completed = subprocess.run(
                command,
                cwd=tmp,
                env=child_environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as err:
            evidence = _bounded_stream_evidence(err.stderr)
            raise InfrastructureAuditError(
                "translator exceeded {}s for {}:{}; stderr_sha256={}; "
                "stderr_tail={!r}".format(
                    timeout, record["directory"], record["problem"],
                    evidence["sha256"], evidence["tail"],
                )
            ) from err
        except OSError as err:
            raise InfrastructureAuditError(
                "cannot execute pinned translator"
            ) from err
        else:
            sas_path = Path(tmp) / "output.sas"
            common = {
                "timeout_seconds": timeout,
                "returncode": completed.returncode,
                "stdout": _bounded_stream_evidence(completed.stdout),
                "stderr": _bounded_stream_evidence(completed.stderr),
            }
            if completed.returncode == 31:
                if sas_path.exists():
                    raise SourceAuditError(
                        "input-rejected translator unexpectedly produced output.sas"
                    )
                translation = {
                    **common,
                    "status": "input-rejected",
                    "sas": None,
                    "sas_sha256": None,
                    "error": "translator rejected frozen input",
                }
            elif completed.returncode != 0:
                evidence = _bounded_stream_evidence(completed.stderr)
                raise SourceAuditError(
                    "translator critical exit {} for {}:{}; "
                    "stderr_sha256={}; stderr_tail={!r}".format(
                        completed.returncode,
                        record["directory"], record["problem"],
                        evidence["sha256"], evidence["tail"],
                    )
                )
            elif not sas_path.is_file() or sas_path.is_symlink():
                raise SourceAuditError(
                    "successful translator produced no regular output.sas"
                )
            else:
                sas_sha256 = sha256_file(sas_path)
                try:
                    sas = parse_sas(sas_path)
                except (SourceAuditError, OSError, ValueError) as err:
                    raise SourceAuditError(
                        "successful translator produced invalid SAS {}: {}".format(
                            sas_sha256, err
                        )
                    ) from err
                else:
                    translation = {
                        **common,
                        "status": "success",
                        "sas": sas,
                        "sas_sha256": sas_sha256,
                        "error": None,
                    }
    if translation["status"] == "input-rejected":
        normalization = {
            "status": "not-applicable",
            "strategy": "axiom_based",
            "num_normalized_axioms": None,
            "error": "translator rejected frozen input",
        }
    else:
        try:
            num_axioms = _count_normalized_axioms(domain, problem)
        except (Exception, SystemExit) as err:
            raise SourceAuditError(
                "normalization failed for {}:{}: {}: {}".format(
                    record["directory"], record["problem"],
                    type(err).__name__, err,
                )
            ) from err
        else:
            normalization = {
                "status": "success",
                "strategy": "axiom_based",
                "num_normalized_axioms": num_axioms,
                "error": None,
            }
    reasons = _support_reasons(translation, normalization)
    return {
        **record,
        "translation_attempted": True,
        "translator_command": [
            "PINNED_PYTHON", "-B", "-m", "translate",
            record["domain_file"], record["problem_file"],
        ],
        "translation": translation,
        "normalization": normalization,
        "supported": not reasons,
        "support_exclusion_reasons": reasons,
    }


def shard_path(directory: Path, index: int, count: int = SHARD_COUNT) -> Path:
    return directory / "shard-{:04d}-of-{:04d}.json".format(index, count)


def scan(args) -> None:
    validate_execution_environment()
    code = validate_code_manifest(
        args.code_manifest.resolve(),
        args.code_manifest_sha256,
        verify_environment_files=False,
    )
    translator_source_digest()
    if (
        args.num_shards != SHARD_COUNT
        or not 0 <= args.shard_index < SHARD_COUNT
        or args.task_timeout != TASK_TIMEOUT_SECONDS
    ):
        raise SourceAuditError("source-audit shard contract changed")
    inventory_sha, records = load_inventory_manifest(
        args.inventory_manifest.resolve(), args.inventory_sha256
    )
    benchmarks = Inventory.validate_benchmark_checkout(args.benchmarks)
    start = args.shard_index * TASKS_PER_SHARD
    selected = records[start:start + TASKS_PER_SHARD]
    if len(selected) != TASKS_PER_SHARD:
        raise SourceAuditError("source-audit shard cardinality changed")
    tasks = []
    for position, record in enumerate(selected, 1):
        print(
            "[{}/{}] {}:{}".format(
                position, len(selected), record["directory"], record["problem"]
            ),
            flush=True,
        )
        tasks.append(_scan_task(record, benchmarks, args.task_timeout))
    output = shard_path(args.output_dir, args.shard_index, args.num_shards)
    _atomic_json(output, {
        "schema": SHARD_SCHEMA,
        "shard_index": args.shard_index,
        "num_shards": args.num_shards,
        "tasks_per_shard": TASKS_PER_SHARD,
        "benchmark_revision": Inventory.BENCHMARK_REVISION,
        "translator_source_sha256": TRANSLATOR_SOURCE_SHA256,
        "source_inventory_sha256": inventory_sha,
        **code,
        "tasks": tasks,
    })
    print("wrote {}".format(output), flush=True)


def _load_shard(
    path: Path,
    index: int,
    expected_records: list[dict],
    inventory_sha256: str,
    code: dict,
) -> list[dict]:
    _, value = _load_canonical_json(path, "source-audit shard")
    tasks = value.get("tasks")
    if (
        value.get("schema") != SHARD_SCHEMA
        or value.get("shard_index") != index
        or value.get("num_shards") != SHARD_COUNT
        or value.get("tasks_per_shard") != TASKS_PER_SHARD
        or value.get("benchmark_revision") != Inventory.BENCHMARK_REVISION
        or value.get("translator_source_sha256") != TRANSLATOR_SOURCE_SHA256
        or value.get("source_inventory_sha256") != inventory_sha256
        or any(value.get(key) != val for key, val in code.items())
        or not isinstance(tasks, list)
        or len(tasks) != TASKS_PER_SHARD
    ):
        raise SourceAuditError("source-audit shard header changed")
    for task, expected in zip(tasks, expected_records):
        if (
            not isinstance(task, dict)
            or any(task.get(key) != val for key, val in expected.items())
            or task.get("translation_attempted") is not True
            or type(task.get("supported")) is not bool
            or not isinstance(task.get("support_exclusion_reasons"), list)
            or task["supported"] is not (
                len(task["support_exclusion_reasons"]) == 0
            )
            or not isinstance(task.get("translation"), dict)
            or not isinstance(task.get("normalization"), dict)
        ):
            raise SourceAuditError("source-audit task record changed")
        _validate_scan_evidence(task)
        if task["support_exclusion_reasons"] != _support_reasons(
            task["translation"], task["normalization"]
        ):
            raise SourceAuditError("source-audit support classification changed")
    return tasks


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


def _cohort_task(
    record: dict, role: str, selection_stage: str | None = None
) -> dict:
    keep = {
        key: record[key]
        for key in (
            "candidate_index", "directory", "family", "problem",
            "domain_file", "problem_file", "domain_sha256",
            "problem_sha256", "canonical_path", "is_shadow_family",
            "is_shadow_unrepresented", "is_all_prior_represented",
            "is_all_prior_unrepresented", "aliases",
        )
    }
    evidence = {
        "translation": record["translation"],
        "normalization": record["normalization"],
        "supported": record["supported"],
        "support_exclusion_reasons": record["support_exclusion_reasons"],
    }
    value = {
        **keep,
        "selection_role": role,
        "selection_rank_sha256": _rank(record, role),
        "source_audit_evidence_sha256": hashlib.sha256(
            canonical_json(evidence)
        ).hexdigest(),
    }
    if selection_stage is not None:
        value["selection_stage"] = selection_stage
    return value


def _stratum_summary(tasks: list[dict], families) -> dict:
    selected = [task for task in tasks if task["family"] in families]
    represented = sorted({task["family"] for task in selected})
    return {
        "tasks": len(selected),
        "families": len(represented),
        "tasks_sha256": hashlib.sha256(canonical_json(selected)).hexdigest(),
        "families_sha256": hashlib.sha256(
            canonical_json(represented)
        ).hexdigest(),
    }


def split_supported(records: list[dict]) -> tuple[dict, dict]:
    supported = [record for record in records if record["supported"]]
    shadow = set(Inventory.SHADOW_FAMILIES)
    inventory_families = {record["family"] for record in records}
    shadow_unrepresented = inventory_families - shadow
    all_prior_unrepresented = set(ALL_PRIOR_UNREPRESENTED_FAMILIES)
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
    queues = {}
    for family in sorted(by_family):
        remaining = [
            record for record in by_family[family]
            if record["problem_sha256"] not in guided_hashes
        ]
        queues[family] = deque(sorted(
            remaining,
            key=lambda record: (
                _rank(record, CONFIRMATION_ROLE), record["canonical_path"]
            ),
        ))
    confirmation = []
    while len(confirmation) < CONFIRMATION_TASKS:
        progress = False
        for family in sorted(queues):
            if queues[family] and len(confirmation) < CONFIRMATION_TASKS:
                confirmation.append(queues[family].popleft())
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
            "actual": len(confirmation), "required": CONFIRMATION_TASKS,
            "passed": len(confirmation) == CONFIRMATION_TASKS,
        },
        "confirmation_families": {
            "actual": len(confirmation_families),
            "required_minimum": MIN_CONFIRMATION_FAMILIES,
            "passed": len(confirmation_families) >= MIN_CONFIRMATION_FAMILIES,
        },
        "confirmation_shadow_unrepresented_families": {
            "actual": len(confirmation_families - shadow),
            "required_minimum": (
                MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES
            ),
            "passed": len(confirmation_families - shadow)
            >= MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES,
        },
        "confirmation_all_prior_unrepresented_tasks": {
            "actual": len(confirmation_all_prior),
            "required_minimum": (
                MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS
            ),
            "passed": len(confirmation_all_prior)
            >= MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS,
        },
        "confirmation_all_prior_unrepresented_families": {
            "actual": len({
                record["family"] for record in confirmation_all_prior
            }),
            "required_minimum": (
                MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES
            ),
            "passed": len({
                record["family"] for record in confirmation_all_prior
            }) >= MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES,
        },
        "guided_tasks": {
            "actual": len(guided), "required_minimum": MIN_GUIDED_TASKS,
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
    gate = {
        "outcome_blind": True,
        "availability": {
            "supported_tasks": len(supported),
            "supported_families": len(by_family),
            "supported_tasks_sha256": hashlib.sha256(
                canonical_json(supported)
            ).hexdigest(),
            "shadow_unrepresented": _stratum_summary(
                supported, shadow_unrepresented
            ),
            "all_prior_unrepresented": _stratum_summary(
                supported, all_prior_unrepresented
            ),
            "post_confirmation_remaining_tasks": (
                post_confirmation_remaining
            ),
            "guided_b_maximum_under_family_cap": guided_cap_capacity,
            "guided_b_target_tasks": GUIDED_TARGET_TASKS,
            "guided_b_max_tasks_per_family": (
                MAX_GUIDED_TASKS_PER_FAMILY
            ),
        },
        "passed": all(clause["passed"] for clause in clauses.values()),
        "clauses": clauses,
    }
    cohorts = {
        "confirmation_a": {
            "role": CONFIRMATION_ROLE,
            "selection_rule": (
                "reserve base guided B first; then SHA256-rank remaining "
                "tasks within family and draw exactly 650 in "
                "lexicographic-family round-robin before guided B top-up"
            ),
            "tasks": [_cohort_task(record, CONFIRMATION_ROLE)
                      for record in confirmation],
        },
        "guided_b": {
            "role": GUIDED_ROLE,
            "top_up_role": GUIDED_TOP_UP_ROLE,
            "target_tasks": GUIDED_TARGET_TASKS,
            "max_tasks_per_family": MAX_GUIDED_TASKS_PER_FAMILY,
            "selection_rule": (
                "within each supported family reserve the first "
                "min(3,floor(n_f/2)) tasks by the frozen guided-B rank; "
                "after selecting confirmation A, top up from remaining "
                "tasks in lexicographic-family round-robin by the frozen "
                "guided-b-topup rank, stopping at 300 tasks or exhaustion, "
                "with at most 12 guided-B tasks per family"
            ),
            "tasks": [
                *[
                    _cohort_task(record, GUIDED_ROLE, "base")
                    for record in guided_base
                ],
                *[
                    _cohort_task(record, GUIDED_TOP_UP_ROLE, "top-up")
                    for record in guided_top_up
                ],
            ],
        },
    }
    for name, cohort in cohorts.items():
        tasks = cohort["tasks"]
        cohort["counts"] = {
            "tasks": len(tasks),
            "families": len({task["family"] for task in tasks}),
            "shadow_unrepresented_tasks": sum(
                task["family"] in shadow_unrepresented for task in tasks
            ),
            "shadow_unrepresented_families": len({
                task["family"] for task in tasks
                if task["family"] in shadow_unrepresented
            }),
            "all_prior_unrepresented_tasks": sum(
                task["family"] in all_prior_unrepresented for task in tasks
            ),
            "all_prior_unrepresented_families": len({
                task["family"] for task in tasks
                if task["family"] in all_prior_unrepresented
            }),
        }
        cohort["strata"] = {
            "shadow_unrepresented": _stratum_summary(
                tasks, shadow_unrepresented
            ),
            "all_prior_unrepresented": _stratum_summary(
                tasks, all_prior_unrepresented
            ),
        }
        if name == "guided_b":
            base = [
                task for task in tasks if task["selection_stage"] == "base"
            ]
            top_up = [
                task for task in tasks if task["selection_stage"] == "top-up"
            ]
            cohort["selection_stages"] = {
                "base": {
                    "role": GUIDED_ROLE,
                    "tasks": len(base),
                    "families": len({task["family"] for task in base}),
                    "tasks_sha256": hashlib.sha256(
                        canonical_json(base)
                    ).hexdigest(),
                    "families_sha256": hashlib.sha256(canonical_json(
                        sorted({task["family"] for task in base})
                    )).hexdigest(),
                },
                "top_up": {
                    "role": GUIDED_TOP_UP_ROLE,
                    "tasks": len(top_up),
                    "families": len({task["family"] for task in top_up}),
                    "tasks_sha256": hashlib.sha256(
                        canonical_json(top_up)
                    ).hexdigest(),
                    "families_sha256": hashlib.sha256(canonical_json(
                        sorted({task["family"] for task in top_up})
                    )).hexdigest(),
                },
            }
        cohort["tasks_sha256"] = hashlib.sha256(
            canonical_json(tasks)
        ).hexdigest()
    confirmation_tasks = cohorts["confirmation_a"]["tasks"]
    guided_tasks = cohorts["guided_b"]["tasks"]
    if (
        {task["problem_sha256"] for task in confirmation_tasks}
        & {task["problem_sha256"] for task in guided_tasks}
        or {(task["directory"], task["problem"]) for task in confirmation_tasks}
        & {(task["directory"], task["problem"]) for task in guided_tasks}
    ):
        raise SourceAuditError("source-split cohorts overlap")
    gate["cohort_disjointness"] = {
        "source_identity_overlap": 0,
        "problem_sha256_overlap": 0,
        "passed": True,
    }
    return gate, cohorts


def assemble(args) -> None:
    code = validate_code_manifest(
        args.code_manifest.resolve(), args.code_manifest_sha256
    )
    translator_source_digest()
    if args.num_shards != SHARD_COUNT:
        raise SourceAuditError("source-audit shard count changed")
    inventory_sha, inventory_records = load_inventory_manifest(
        args.inventory_manifest.resolve(), args.inventory_sha256
    )
    records = []
    for index in range(SHARD_COUNT):
        start = index * TASKS_PER_SHARD
        records.extend(_load_shard(
            shard_path(args.shard_dir, index),
            index,
            inventory_records[start:start + TASKS_PER_SHARD],
            inventory_sha,
            code,
        ))
    if (
        len(records) != CANDIDATE_COUNT
        or [record["candidate_index"] for record in records]
        != list(range(CANDIDATE_COUNT))
    ):
        raise SourceAuditError("assembled source-audit population changed")
    gate, cohorts = split_supported(records)
    exclusions = Counter(
        reason
        for record in records
        for reason in record["support_exclusion_reasons"]
    )
    translation_statuses = Counter(
        record["translation"]["status"] for record in records
    )
    value = {
        "schema": SCHEMA,
        "benchmark_revision": Inventory.BENCHMARK_REVISION,
        "translator_source_sha256": TRANSLATOR_SOURCE_SHA256,
        "source_inventory_sha256": inventory_sha,
        "source_inventory_records_sha256": hashlib.sha256(
            canonical_json(inventory_records)
        ).hexdigest(),
        "code_manifest_sha256": args.code_manifest_sha256,
        "split_seed": SPLIT_SEED,
        "split_rank_encoding": (
            "SHA256(seed || NUL || role || NUL || family || NUL || "
            "problem_sha256 || NUL || canonical_path)"
        ),
        "split_role_labels": {
            "confirmation_a": CONFIRMATION_ROLE,
            "guided_b_base": GUIDED_ROLE,
            "guided_b_top_up": GUIDED_TOP_UP_ROLE,
        },
        "split_strata": {
            "shadow_unrepresented": {
                "definition": "families absent from the frozen shadow suites",
                "families": sorted({
                    record["family"] for record in records
                    if record["family"] not in Inventory.SHADOW_FAMILIES
                }),
                "families_sha256": hashlib.sha256(canonical_json(
                    sorted({
                        record["family"] for record in records
                        if record["family"] not in Inventory.SHADOW_FAMILIES
                    })
                )).hexdigest(),
                "inventory_family_sequence_sha256": (
                    Inventory.SHADOW_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
                ),
            },
            "all_prior_unrepresented": {
                "definition": (
                    "families absent from both frozen prior experiment artifacts"
                ),
                "families": list(ALL_PRIOR_UNREPRESENTED_FAMILIES),
                "families_sha256": hashlib.sha256(canonical_json(
                    list(ALL_PRIOR_UNREPRESENTED_FAMILIES)
                )).hexdigest(),
                "inventory_family_sequence_sha256": (
                    Inventory.ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
                ),
                "prior_directory_family_map_sha256": (
                    Inventory.PRIOR_DIRECTORY_FAMILY_MAP_SHA256
                ),
                "prior_family_ledger_sha256": (
                    Inventory.PRIOR_FAMILY_LEDGER_SHA256
                ),
            },
        },
        "counts": {
            "candidates": len(records),
            "translation_attempts": sum(
                record["translation_attempted"] for record in records
            ),
            "translated_successfully": translation_statuses["success"],
            "supported": sum(record["supported"] for record in records),
            "unsupported": sum(not record["supported"] for record in records),
            "families": len({record["family"] for record in records}),
        },
        "translation_status_counts": dict(sorted(translation_statuses.items())),
        "support_exclusion_counts": dict(sorted(exclusions.items())),
        "records_sha256": hashlib.sha256(canonical_json(records)).hexdigest(),
        "prelaunch_gate": gate,
        "confirmation_prelaunch_authorized": gate["passed"],
        "cohorts": cohorts,
        "records": records,
    }
    _atomic_json(args.output, value)
    print("wrote {}".format(args.output), flush=True)
    print("sha256 {}".format(sha256_file(args.output)), flush=True)
    if not gate["passed"]:
        print(
            "confirmation prelaunch gate failed; no outcome run is authorized",
            flush=True,
        )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("--benchmarks", type=Path, default=DEFAULT_BENCHMARKS)
    scan_parser.add_argument("--output-dir", type=Path, default=DEFAULT_SHARDS)
    scan_parser.add_argument("--inventory-manifest", type=Path, required=True)
    scan_parser.add_argument("--inventory-sha256", required=True)
    scan_parser.add_argument("--num-shards", type=int, required=True)
    scan_parser.add_argument("--shard-index", type=int, required=True)
    scan_parser.add_argument(
        "--task-timeout", type=int, default=TASK_TIMEOUT_SECONDS
    )
    scan_parser.add_argument(
        "--code-manifest", type=Path, default=DEFAULT_CODE_MANIFEST
    )
    scan_parser.add_argument("--code-manifest-sha256", required=True)
    scan_parser.set_defaults(func=scan)
    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("--shard-dir", type=Path, default=DEFAULT_SHARDS)
    assemble_parser.add_argument("--inventory-manifest", type=Path, required=True)
    assemble_parser.add_argument("--inventory-sha256", required=True)
    assemble_parser.add_argument("--num-shards", type=int, required=True)
    assemble_parser.add_argument(
        "--code-manifest", type=Path, default=DEFAULT_CODE_MANIFEST
    )
    assemble_parser.add_argument("--code-manifest-sha256", required=True)
    assemble_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    assemble_parser.set_defaults(func=assemble)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InfrastructureAuditError as err:
        print("infrastructure error: {}".format(err), file=sys.stderr)
        raise SystemExit(75)
    except (SourceAuditError, Inventory.InventoryError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
