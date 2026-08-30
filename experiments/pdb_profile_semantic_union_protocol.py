#!/usr/bin/env python3
"""Frozen protocol constants for the semantic-union follow-up."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path

import pdb_profile_comparison_protocol as Source


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
PROTOCOL_PATH = SCRIPT_DIR / "pdb_profile_semantic_union_protocol.md"
PROTOCOL_SHA256 = (
    "bb52d426568e41377e13eacdc503467bb8013277c282938639a2886828a954e2"
)
PROTOCOL = "pdb-profile-semantic-union-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-profile-semantic-union-analysis-v1"
COHORT_ROLE = "domain-balanced-corrected-measurement"
TASKS_PER_DOMAIN = 6
COHORT_TASKS = 275
COHORT_DOMAINS = 46
COHORT_MANIFEST_SHA256 = (
    "5c43a5d0891d32285c248c14cfe81ab5fa308b8eeb3d3d34e7d22ee782fcda2e"
)
CONFIGS = tuple(Source.CONFIGS[2:])
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
CONFIG_COUNT = 16
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT
OPTION_MATRIX_SHA256 = (
    "da252ff9610d98f676eae2ad8d01364d2b4914583880953c1a7d2ec6a5aec1ea"
)
TIME_LIMIT_SECONDS = Source.TIME_LIMIT_SECONDS
MEMORY_LIMIT_MIB = Source.MEMORY_LIMIT_MIB
REQUIRED_LAB_VERSION = Source.REQUIRED_LAB_VERSION
BUILD_OPTIONS = Source.BUILD_OPTIONS
MIN_DOMAINS = 31
MIN_TASKS_WITH_COMPARABLE_PAIRS = 184


def _task_rank(task) -> str:
    payload = "{}\0{}".format(task.domain, task.problem).encode("ascii")
    return hashlib.sha256(payload).hexdigest()


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
    by_domain = defaultdict(list)
    for task in source:
        by_domain[task.domain].append(task)
    selected = []
    for domain in sorted(by_domain):
        ranked = sorted(by_domain[domain], key=lambda task: (_task_rank(task), task))
        selected.extend(ranked[:TASKS_PER_DOMAIN])
    selected = tuple(sorted(selected))
    if (
        len(selected) != COHORT_TASKS
        or len({task.domain for task in selected}) != COHORT_DOMAINS
        or _manifest_digest(selected) != COHORT_MANIFEST_SHA256
    ):
        raise ProtocolError("semantic-union cohort identity changed")
    return selected


def validate_protocol_without_archive() -> None:
    try:
        raw = PROTOCOL_PATH.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read semantic-union protocol") from err
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("semantic-union protocol bytes changed")
    if (
        len(CONFIGS) != CONFIG_COUNT
        or len(LABELS) != len(set(LABELS))
        or len(SEARCHES) != CONFIG_COUNT
        or CELL_COUNT != 4400
        or option_matrix_digest() != OPTION_MATRIX_SHA256
    ):
        raise ProtocolError("semantic-union option matrix changed")
    if LABELS != Source.LABELS[2:]:
        raise ProtocolError("semantic-union configuration order changed")
    for label, search in CONFIGS:
        if (
            not label.startswith("pdb_")
            or search.count('wbh_log="{}"'.format(Source.LEGACY_LOG)) != 1
            or search.count(
                'wbh_profile_log="{}"'.format(Source.PROFILE_LOG)
            ) != 1
        ):
            raise ProtocolError("semantic-union logging matrix changed")
    if not (
        1 <= MIN_DOMAINS <= COHORT_DOMAINS
        and 1 <= MIN_TASKS_WITH_COMPARABLE_PAIRS <= COHORT_TASKS
    ):
        raise ProtocolError("semantic-union support floor is invalid")


if __name__ == "__main__":
    validate_protocol_without_archive()
    cohort = load_cohort()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            len(cohort), CONFIG_COUNT, CELL_COUNT
        )
    )
