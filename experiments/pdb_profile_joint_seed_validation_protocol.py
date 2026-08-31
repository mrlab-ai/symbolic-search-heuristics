#!/usr/bin/env python3
"""Frozen constants for the unseen Gamer-seed validation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pdb_profile_certificate_holdout_protocol as Holdout


Source = Holdout.Source


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
PROTOCOL_PATH = SCRIPT_DIR / "pdb_profile_joint_seed_validation_protocol.md"
PROTOCOL_SHA256 = (
    "08cc498981d3dd90bcb496e1a48929cd52677b27419e2b61221ef188403f4ce9"
)
PROTOCOL = "pdb-profile-joint-seed-validation-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-profile-joint-seed-validation-analysis-v1"
COHORT_ROLE = "prospective-unseen-gamer-seed-order-validation"
COHORT_TASKS = Holdout.COHORT_TASKS
COHORT_DOMAINS = Holdout.COHORT_DOMAINS
COHORT_MANIFEST_SHA256 = Holdout.COHORT_MANIFEST_SHA256
TIME_LIMIT_SECONDS = Holdout.TIME_LIMIT_SECONDS
MEMORY_LIMIT_MIB = Holdout.MEMORY_LIMIT_MIB
REQUIRED_LAB_VERSION = Holdout.REQUIRED_LAB_VERSION
BUILD_OPTIONS = Holdout.BUILD_OPTIONS
PLANNER_REVISION = "28278042f797aebf70198945cdabb822187385ad"
PLANNER_BINARY_SHA256 = (
    "9f8688fd5eb9b8a5484ce566a4c623e62bb0dbe60fdad59da49f28622a31bf20"
)
PREPROCESS_BINARY_SHA256 = (
    "d32e7de1dc194ca63664e223b177a2ccae2e82e259ccd682596ff10cc6b0fbd6"
)
SEEDS = (1, 2, 3, 4)
MIN_COMPARABLE_PAIRS = 150
MIN_TASKS_WITH_COMPARABLE_PAIRS = 75
MIN_DOMAINS = 25
MIN_PRIMARY_CONCORDANCE_NUMERATOR = 65
MIN_PRIMARY_CONCORDANCE_DENOMINATOR = 100
MIN_NULL_MARGIN_NUMERATOR = 2
MIN_NULL_MARGIN_DENOMINATOR = 100
MIN_ABSOLUTE_CONCORDANCE_NUMERATOR = 65
MIN_ABSOLUTE_CONCORDANCE_DENOMINATOR = 100


def _pdb(seed: int) -> str:
    return (
        "sym_fw_pdb(budget=100000,pattern_selection=goal_fill,"
        "gamer_ordering=true,gamer_ordering_seed={},dynamic_reordering=false,"
        'wbh_log="{}",wbh_profile_log="{}")'.format(
            seed,
            Source.LEGACY_LOG,
            Source.PROFILE_LOG,
        )
    )


CONFIGS = tuple(
    ("pdb_goal_fill_seed_{}".format(seed), _pdb(seed))
    for seed in SEEDS
)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
CONFIG_COUNT = len(CONFIGS)
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT
OPTION_MATRIX_SHA256 = (
    "9cd55581fb1a7382103a1eb140b854b26056930a7f1c531b13827c632f17e9af"
)


def option_matrix_digest() -> str:
    payload = [
        {"label": label, "search": search}
        for label, search in CONFIGS
    ]
    return hashlib.sha256(Source.canonical_json(payload)).hexdigest()


def load_cohort(archive=Source.COHORT_ARCHIVE_DEFAULT):
    return Holdout.load_cohort(archive)


def validate_protocol_without_archive() -> None:
    try:
        raw = PROTOCOL_PATH.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read seed-validation protocol") from err
    pins = (
        PROTOCOL_SHA256,
        OPTION_MATRIX_SHA256,
        PLANNER_BINARY_SHA256,
        PREPROCESS_BINARY_SHA256,
    )
    if any(value == "TO_PIN" for value in pins):
        raise ProtocolError("seed-validation protocol is not fully pinned")
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("seed-validation protocol bytes changed")
    if (
        SEEDS != (1, 2, 3, 4)
        or CONFIG_COUNT != 4
        or CELL_COUNT != 4208
        or len(LABELS) != len(set(LABELS))
        or option_matrix_digest() != OPTION_MATRIX_SHA256
    ):
        raise ProtocolError("seed-validation option matrix changed")
    for seed, (label, search) in zip(SEEDS, CONFIGS):
        if (
            label != "pdb_goal_fill_seed_{}".format(seed)
            or search.count("pattern_selection=goal_fill") != 1
            or search.count("gamer_ordering=true") != 1
            or search.count("gamer_ordering_seed={}".format(seed)) != 1
            or search.count("dynamic_reordering=false") != 1
            or search.count('wbh_log="{}"'.format(Source.LEGACY_LOG)) != 1
            or search.count(
                'wbh_profile_log="{}"'.format(Source.PROFILE_LOG)
            ) != 1
        ):
            raise ProtocolError("seed-validation configuration changed")


if __name__ == "__main__":
    validate_protocol_without_archive()
    cohort = load_cohort()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            len(cohort), CONFIG_COUNT, CELL_COUNT
        )
    )
