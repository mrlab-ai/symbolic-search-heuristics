#!/usr/bin/env python3
"""Fixed constants for the developmental co-occurring-residual pilot."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pdb_profile_semantic_union_protocol as Development


Source = Development.Source
Holdout = Development


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
PROTOCOL_PATH = SCRIPT_DIR / "pdb_profile_joint_pilot_protocol.md"
PROTOCOL_SHA256 = (
    "015578c0b6bc2e632b3a896b272407cbfdc2c6ed7183b847e7c9f6c2b95e9df4"
)
PROTOCOL = "pdb-profile-joint-pilot-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-profile-joint-pilot-analysis-v1"
COHORT_ROLE = "development-cooccurring-residual-order-pilot"
COHORT_TASKS = Development.COHORT_TASKS
COHORT_DOMAINS = Development.COHORT_DOMAINS
COHORT_MANIFEST_SHA256 = Development.COHORT_MANIFEST_SHA256
TIME_LIMIT_SECONDS = Development.TIME_LIMIT_SECONDS
MEMORY_LIMIT_MIB = Development.MEMORY_LIMIT_MIB
REQUIRED_LAB_VERSION = Development.REQUIRED_LAB_VERSION
BUILD_OPTIONS = Development.BUILD_OPTIONS
PLANNER_REVISION = "2fa8ba8a4c28622e2073020d46ee9aaf95be7774"
PLANNER_BINARY_SHA256 = (
    "19433f566f4b4d3a1c206f533c24c8ce533d5db7b5ba0a8d68fbf4b6c5cb8a0d"
)
PREPROCESS_BINARY_SHA256 = (
    "cbc878f38df1f93d7b1e6655db734301191da602a88238dc5d96b8d604572475"
)


def _pdb(gamer: bool) -> str:
    return (
        "sym_fw_pdb(budget=100000,pattern_selection=goal_fill,"
        "gamer_ordering={},dynamic_reordering=false,"
        'wbh_log="{}",wbh_profile_log="{}")'.format(
            "true" if gamer else "false",
            Source.LEGACY_LOG,
            Source.PROFILE_LOG,
        )
    )


CONFIGS = (
    ("pdb_goal_fill_gamer", _pdb(True)),
    ("pdb_goal_fill_fd", _pdb(False)),
)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
CONFIG_COUNT = len(CONFIGS)
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT
OPTION_MATRIX_SHA256 = (
    "c6f9cb3e6c0ae75c4dd87faab01e31c19d05fc3517411218020de49dfb555382"
)


def option_matrix_digest() -> str:
    payload = [
        {"label": label, "search": search}
        for label, search in CONFIGS
    ]
    return hashlib.sha256(Source.canonical_json(payload)).hexdigest()


def load_cohort(archive=Source.COHORT_ARCHIVE_DEFAULT):
    return Development.load_cohort(archive)


def validate_protocol_without_archive() -> None:
    try:
        raw = PROTOCOL_PATH.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read joint-pilot protocol") from err
    pins = (
        PROTOCOL_SHA256,
        OPTION_MATRIX_SHA256,
        PLANNER_BINARY_SHA256,
        PREPROCESS_BINARY_SHA256,
    )
    if any(value == "TO_PIN" for value in pins):
        raise ProtocolError("joint-pilot protocol is not fully pinned")
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("joint-pilot protocol bytes changed")
    if (
        CONFIG_COUNT != 2
        or CELL_COUNT != 550
        or len(LABELS) != len(set(LABELS))
        or option_matrix_digest() != OPTION_MATRIX_SHA256
    ):
        raise ProtocolError("joint-pilot option matrix changed")
    for label, search in CONFIGS:
        expected_order = "gamer_ordering={}".format(
            "true" if label.endswith("gamer") else "false"
        )
        if (
            search.count("pattern_selection=goal_fill") != 1
            or search.count(expected_order) != 1
            or search.count("dynamic_reordering=false") != 1
            or search.count('wbh_log="{}"'.format(Source.LEGACY_LOG)) != 1
            or search.count(
                'wbh_profile_log="{}"'.format(Source.PROFILE_LOG)
            ) != 1
        ):
            raise ProtocolError("joint-pilot configuration contract changed")


if __name__ == "__main__":
    validate_protocol_without_archive()
    cohort = load_cohort()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            len(cohort), CONFIG_COUNT, CELL_COUNT
        )
    )
