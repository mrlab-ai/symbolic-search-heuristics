#!/usr/bin/env python3
"""Frozen constants for the fixed-heuristic order intervention."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pdb_profile_certificate_holdout_protocol as Holdout

Source = Holdout.Source


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
PROTOCOL_PATH = SCRIPT_DIR / "pdb_profile_order_intervention_protocol.md"
PROTOCOL_SHA256 = (
    "91697b326c3270da80ce63bab5d6a7a11d1432ffeb6da01df7671bff08ba6693"
)
PROTOCOL = "pdb-profile-order-intervention-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-profile-order-intervention-analysis-v1"
COHORT_ROLE = "prospective-fixed-heuristic-order-intervention-holdout"
COHORT_TASKS = Holdout.COHORT_TASKS
COHORT_DOMAINS = Holdout.COHORT_DOMAINS
COHORT_MANIFEST_SHA256 = Holdout.COHORT_MANIFEST_SHA256
TIME_LIMIT_SECONDS = Holdout.TIME_LIMIT_SECONDS
MEMORY_LIMIT_MIB = Holdout.MEMORY_LIMIT_MIB
REQUIRED_LAB_VERSION = Holdout.REQUIRED_LAB_VERSION
BUILD_OPTIONS = Holdout.BUILD_OPTIONS
PLANNER_REVISION = Holdout.PLANNER_REVISION
PLANNER_BINARY_SHA256 = Holdout.PLANNER_BINARY_SHA256
PREPROCESS_BINARY_SHA256 = Holdout.PREPROCESS_BINARY_SHA256
MIN_DOMAINS = Holdout.MIN_DOMAINS
MIN_TASKS_WITH_COMPARABLE_PAIRS = Holdout.MIN_TASKS_WITH_COMPARABLE_PAIRS


def _pdb(gamer: bool) -> str:
    return (
        "sym_fw_pdb(budget=100000,pattern_selection=goal_fill,"
        "gamer_ordering={},dynamic_reordering=false,"
        'wbh_log="{}",wbh_profile_log="{}")'.format(
            "true" if gamer else "false",
            Holdout.Source.LEGACY_LOG,
            Holdout.Source.PROFILE_LOG,
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
    return hashlib.sha256(Holdout.Source.canonical_json(payload)).hexdigest()


def load_cohort(archive=Holdout.Source.COHORT_ARCHIVE_DEFAULT):
    return Holdout.load_cohort(archive)


def validate_protocol_without_archive() -> None:
    try:
        raw = PROTOCOL_PATH.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read order-intervention protocol") from err
    if PROTOCOL_SHA256 == "TO_PIN":
        raise ProtocolError("protocol digest is not pinned")
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("order-intervention protocol bytes changed")
    if OPTION_MATRIX_SHA256 == "TO_PIN":
        raise ProtocolError("option-matrix digest is not pinned")
    if (
        CONFIG_COUNT != 2
        or CELL_COUNT != 2104
        or len(LABELS) != len(set(LABELS))
        or option_matrix_digest() != OPTION_MATRIX_SHA256
    ):
        raise ProtocolError("order-intervention option matrix changed")
    for label, search in CONFIGS:
        expected_order = "gamer_ordering={}".format(
            "true" if label.endswith("gamer") else "false"
        )
        if (
            search.count("pattern_selection=goal_fill") != 1
            or search.count(expected_order) != 1
            or search.count("dynamic_reordering=false") != 1
            or search.count(
                'wbh_log="{}"'.format(Holdout.Source.LEGACY_LOG)
            ) != 1
            or search.count(
                'wbh_profile_log="{}"'.format(Holdout.Source.PROFILE_LOG)
            ) != 1
        ):
            raise ProtocolError(
                "order-intervention configuration contract changed"
            )


if __name__ == "__main__":
    validate_protocol_without_archive()
    cohort = load_cohort()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            len(cohort), CONFIG_COUNT, CELL_COUNT
        )
    )
