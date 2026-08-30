#!/usr/bin/env python3
"""Frozen constants for the prospective certificate holdout."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pdb_profile_comparison_protocol as Source
import pdb_profile_semantic_union_protocol as Development


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
PROTOCOL_PATH = SCRIPT_DIR / "pdb_profile_certificate_holdout_protocol.md"
PROTOCOL_SHA256 = (
    "9e82fb3f514362c6cb2be9be3c70aeb929a36b24e67325e454579a417a1b5a62"
)
PROTOCOL = "pdb-profile-certificate-holdout-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-profile-certificate-holdout-analysis-v1"
COHORT_ROLE = "prospective-corrected-instrumentation-holdout"
COHORT_TASKS = 1052
COHORT_DOMAINS = 45
COHORT_MANIFEST_SHA256 = (
    "e9ffcc16c2e73e4c92c0ccbb71c60203ba643f5ed76bf943f731e86e11169694"
)
CONFIGS = tuple(Source.CONFIGS[1:])
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
PDB_LABELS = tuple(label for label in LABELS if label.startswith("pdb_"))
BLIND_LABEL = "blind_fw_profiled"
CONFIG_COUNT = 17
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT
OPTION_MATRIX_SHA256 = (
    "2a7ddc1570d4dfac321fdeb5bffbaba59e8b16d2847714ffde75b1ae5bedba7d"
)
TIME_LIMIT_SECONDS = Source.TIME_LIMIT_SECONDS
MEMORY_LIMIT_MIB = Source.MEMORY_LIMIT_MIB
REQUIRED_LAB_VERSION = "8.0"
BUILD_OPTIONS = Source.BUILD_OPTIONS
PLANNER_REVISION = "f106393ec53e2ef9a24e1e7dcc91d10b1e83db6f"
PLANNER_BINARY_SHA256 = (
    "634584c4dc871a799269254e3f4e232eca8e77c0e84ff3fe0b0cdb67f9d46d9d"
)
PREPROCESS_BINARY_SHA256 = (
    "4fbfba6aab9f96b9766f3714e911cffbc5d1cb59bed82a13484af9e73977c118"
)
MIN_DOMAINS = 30
MIN_TASKS_WITH_COMPARABLE_PAIRS = 211


def _manifest_digest(tasks) -> str:
    raw = "".join(
        "{}:{}\n".format(task.domain, task.problem)
        for task in sorted(tasks)
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def option_matrix_digest(configs=CONFIGS) -> str:
    payload = [
        {"label": label, "search": search}
        for label, search in configs
    ]
    return hashlib.sha256(Source.canonical_json(payload)).hexdigest()


def load_cohort(archive=Source.COHORT_ARCHIVE_DEFAULT):
    source = Source.load_cohort(archive)
    development = Development.load_cohort(archive)
    development_ids = {
        (task.domain, task.problem) for task in development
    }
    selected = tuple(sorted(
        task for task in source
        if (task.domain, task.problem) not in development_ids
    ))
    if (
        len(selected) != COHORT_TASKS
        or len({task.domain for task in selected}) != COHORT_DOMAINS
        or _manifest_digest(selected) != COHORT_MANIFEST_SHA256
    ):
        raise ProtocolError("certificate holdout identity changed")
    return selected


def validate_protocol_without_archive() -> None:
    try:
        raw = PROTOCOL_PATH.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read certificate holdout protocol") from err
    if PROTOCOL_SHA256 == "TO_PIN":
        raise ProtocolError("protocol digest is not pinned")
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("certificate holdout protocol bytes changed")
    if OPTION_MATRIX_SHA256 == "TO_PIN":
        raise ProtocolError("option-matrix digest is not pinned")
    if (
        len(CONFIGS) != CONFIG_COUNT
        or len(LABELS) != len(set(LABELS))
        or len(SEARCHES) != CONFIG_COUNT
        or len(PDB_LABELS) != 16
        or BLIND_LABEL not in LABELS
        or CELL_COUNT != 17884
        or option_matrix_digest() != OPTION_MATRIX_SHA256
    ):
        raise ProtocolError("certificate holdout option matrix changed")
    if LABELS != Source.LABELS[1:]:
        raise ProtocolError("certificate holdout configuration order changed")
    for label, search in CONFIGS:
        if search.count(
            'wbh_profile_log="{}"'.format(Source.PROFILE_LOG)
        ) != 1:
            raise ProtocolError("holdout configuration lacks profile logging")
        if search.count(
            'wbh_log="{}"'.format(Source.LEGACY_LOG)
        ) != 1:
            raise ProtocolError("holdout configuration lacks schema-v2 logging")
        if label.startswith("pdb_") != ("sym_fw_pdb(" in search):
            raise ProtocolError("holdout label and search family disagree")
    if not (
        1 <= MIN_DOMAINS <= COHORT_DOMAINS
        and 1 <= MIN_TASKS_WITH_COMPARABLE_PAIRS <= COHORT_TASKS
    ):
        raise ProtocolError("certificate holdout support floor is invalid")


if __name__ == "__main__":
    validate_protocol_without_archive()
    cohort = load_cohort()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            len(cohort), CONFIG_COUNT, CELL_COUNT
        )
    )
