#!/usr/bin/env python3
"""Frozen constants for the prospective unsplit-bound study (Stage 2)."""

from __future__ import annotations

import hashlib
from fractions import Fraction
from pathlib import Path

import pdb_profile_harm_generality_protocol as Generality


Source = Generality.Source
Holdout = Generality.Holdout
Task = Generality.Task


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
PROTOCOL_PATH = SCRIPT_DIR / "unsplit_bound_protocol.md"
PROTOCOL_SHA256 = (
    "3c955c8c5d982db92f0350bfd119cd45743ac8d0bef1cf5543eb2539b52d8c83"
)
PROTOCOL = "unsplit-bound-measurement-v1"
ANALYSIS_PROTOCOL = "unsplit-bound-analysis-v1"
COHORT_ROLE = "prospective-unsplit-bound-holdout"
COHORT_FILE = Generality.COHORT_FILE
COHORT_TASKS = Generality.COHORT_TASKS
COHORT_DOMAINS = Generality.COHORT_DOMAINS
COHORT_MANIFEST_SHA256 = Generality.COHORT_MANIFEST_SHA256
TIME_LIMIT_SECONDS = Generality.TIME_LIMIT_SECONDS
MEMORY_LIMIT_MIB = Generality.MEMORY_LIMIT_MIB
REQUIRED_LAB_VERSION = Generality.REQUIRED_LAB_VERSION
REQUIRED_PYTHON_VERSION = Generality.REQUIRED_PYTHON_VERSION
BUILD_OPTIONS = Generality.BUILD_OPTIONS
PLANNER_REVISION = "4a719d8b3da3b606f4f246a61c2189859a5c825e"
PLANNER_CACHE_NAME = "4a719d8b3da3b606_83be6fdae697"
PLANNER_BINARY_SHA256 = (
    "03d708712b1e44c08b11180215c42b11b27d65ce9410e99a7a3c8c20d7663ca1"
)
PREPROCESS_BINARY_SHA256 = (
    "0fd76b7be165f31ad32e3c6a01d7f62423b0c600ace633d860e264dec6a4554d"
)
PLANNER_TREE_MANIFEST_SHA256 = (
    "416c8f5b6402aba0962c2c2f1ede03ed318b835176f94cfb71d2cf4fa04a2213"
)
CPLEX_DIR = Generality.CPLEX_DIR
CPLEX_LIBRARY = Generality.CPLEX_LIBRARY
CPLEX_LIBRARY_SHA256 = Generality.CPLEX_LIBRARY_SHA256

# Stage 1 selects one bound schedule per family (Section 4).
SCHEDULES = {"ms": "double", "pdb": "double", "pot": "double"}
SCHEDULE_OPTIONS = {
    "next": "unsplit_bound=true",
    "double": "unsplit_bound=true,unsplit_bound_doubling=true",
}

_LOG = 'wbh_log="{}"'.format(Source.LEGACY_LOG)
_BASE = {
    "ms": (
        "sym_fw_ms(max_states=10000,align_merge_order=false,"
        "build_time_limit=infinity{})"
    ),
    "pdb": (
        "sym_fw_pdb(budget=1000000,pattern_selection=cegar,"
        "cegar_max_time=10,cegar_seed=2011{})"
    ),
    "pot": "sym_fw_pot(m=4{})",
}
FAMILY_NAMES = ("ms", "pdb", "pot")
BLIND_FW = "blind_fw"
BLIND_BD = "blind_bd"


def _configs(schedules):
    configs = [
        (BLIND_FW, "sym_fw({})".format(_LOG)),
        (BLIND_BD, "sym_bd({})".format(_LOG)),
    ]
    for family in FAMILY_NAMES:
        base = _BASE[family]
        configs.append(("{}_plain".format(family), base.format("," + _LOG)))
        options = SCHEDULE_OPTIONS.get(schedules[family], "TO_PIN")
        configs.append((
            "{}_unsplit".format(family),
            base.format(",{},{}".format(options, _LOG)),
        ))
    return tuple(configs)


CONFIGS = _configs(SCHEDULES)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
CONFIG_COUNT = len(CONFIGS)
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT
OPTION_MATRIX_SHA256 = (
    "1858ead5801cd3a82cf8e69b4c84501a87e16fdbf854ab32ab490782a75b23eb"
)

# Decision rule (Section 5).
ALPHA = Fraction(5, 100)
PAR2_UNSOLVED_SECONDS = 600


def primary_tests():
    """The six primary comparisons as (name, config, reference)."""
    tests = []
    for family in FAMILY_NAMES:
        label = "{}_unsplit".format(family)
        tests.append(("H1:" + label, label, "{}_plain".format(family)))
        tests.append(("H2:" + label, label, BLIND_FW))
    return tuple(tests)


def option_matrix_digest(configs=CONFIGS) -> str:
    payload = [{"label": label, "search": search} for label, search in configs]
    return hashlib.sha256(Source.canonical_json(payload)).hexdigest()


def load_cohort(archive=None):
    return Generality.load_cohort(archive)


def validate_protocol_without_archive() -> None:
    try:
        raw = PROTOCOL_PATH.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read unsplit-bound protocol") from err
    for name in ("PROTOCOL_SHA256", "OPTION_MATRIX_SHA256"):
        if globals()[name] == "TO_PIN":
            raise ProtocolError("{} is not pinned".format(name))
    if set(SCHEDULES.values()) - set(SCHEDULE_OPTIONS):
        raise ProtocolError("bound schedules are not pinned")
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("unsplit-bound protocol bytes changed")
    if (
        CONFIG_COUNT != 8
        or CELL_COUNT != 8416
        or len(LABELS) != len(set(LABELS))
        or option_matrix_digest() != OPTION_MATRIX_SHA256
        or len(primary_tests()) != 6
    ):
        raise ProtocolError("unsplit-bound option matrix changed")
    for _, search in CONFIGS:
        if search.count(_LOG) != 1:
            raise ProtocolError("configuration lacks its log option")


if __name__ == "__main__":
    validate_protocol_without_archive()
    cohort = load_cohort()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            len(cohort), CONFIG_COUNT, CELL_COUNT
        )
    )
