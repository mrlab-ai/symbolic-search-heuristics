#!/usr/bin/env python3
"""Frozen constants for the prospective fragmentation-remedy study (Stage 2)."""

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
PROTOCOL_PATH = SCRIPT_DIR / "fragmentation_remedy_protocol.md"
PROTOCOL_SHA256 = (
    "2f3b61d1cd8d3eb96f83fba0c8352c86d8ccab9738b8f7cca7e81a6c5a3fc772"
)
PROTOCOL = "fragmentation-remedy-measurement-v1"
ANALYSIS_PROTOCOL = "fragmentation-remedy-analysis-v1"
COHORT_ROLE = "prospective-fragmentation-remedy-holdout"
COHORT_FILE = Generality.COHORT_FILE
COHORT_TASKS = Generality.COHORT_TASKS
COHORT_DOMAINS = Generality.COHORT_DOMAINS
COHORT_MANIFEST_SHA256 = Generality.COHORT_MANIFEST_SHA256
TIME_LIMIT_SECONDS = Generality.TIME_LIMIT_SECONDS
MEMORY_LIMIT_MIB = Generality.MEMORY_LIMIT_MIB
REQUIRED_LAB_VERSION = Generality.REQUIRED_LAB_VERSION
REQUIRED_PYTHON_VERSION = Generality.REQUIRED_PYTHON_VERSION
BUILD_OPTIONS = Generality.BUILD_OPTIONS
PLANNER_REVISION = Generality.PLANNER_REVISION
PLANNER_BINARY_SHA256 = Generality.PLANNER_BINARY_SHA256
PREPROCESS_BINARY_SHA256 = Generality.PREPROCESS_BINARY_SHA256
PLANNER_TREE_MANIFEST_SHA256 = Generality.PLANNER_TREE_MANIFEST_SHA256
CPLEX_DIR = Generality.CPLEX_DIR
CPLEX_LIBRARY = Generality.CPLEX_LIBRARY
CPLEX_LIBRARY_SHA256 = Generality.CPLEX_LIBRARY_SHA256

# Stage 1 selects one batching window per family (Section 4).
BATCH_WINDOWS = {"ms": "1", "pdb": "1", "pot": "1"}

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
REMEDIES = ("prune", "batch")
BLIND_FW = "blind_fw"
BLIND_BD = "blind_bd"
BD_MS_PRUNE = "bd_ms_prune"
POT_ALL = "pot_all_plain"


def _configs(windows):
    configs = [
        (BLIND_FW, "sym_fw({})".format(_LOG)),
        (BLIND_BD, "sym_bd({})".format(_LOG)),
        (BD_MS_PRUNE, "sym_bd_ms(max_states=10000,{})".format(_LOG)),
    ]
    for family in FAMILY_NAMES:
        base = _BASE[family]
        configs += [
            ("{}_plain".format(family), base.format("," + _LOG)),
            ("{}_prune".format(family),
             base.format(",prune_only=true," + _LOG)),
            ("{}_batch".format(family), base.format(
                ",batch_f_window={},batch_max_union_ratio=1.0,{}".format(
                    windows[family], _LOG))),
        ]
    configs.append(
        (POT_ALL, "sym_fw_pot(m=4,all_states_objective=true,{})".format(_LOG)))
    return tuple(configs)


CONFIGS = _configs(BATCH_WINDOWS)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
CONFIG_COUNT = len(CONFIGS)
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT
OPTION_MATRIX_SHA256 = (
    "bc6a8bc1e3523a90a66479e59a7cbd8a915d756f9c61f1000a8dbc380832ec54"
)

# Decision rule (Section 5).
ALPHA = Fraction(5, 100)
PAR2_UNSOLVED_SECONDS = 600
EFFORT_TIME_MIN_BLIND_SECONDS = 1


def primary_tests():
    """The twelve primary comparisons as (name, config, reference)."""
    tests = []
    for family in FAMILY_NAMES:
        for remedy in REMEDIES:
            label = "{}_{}".format(family, remedy)
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
        raise ProtocolError("cannot read fragmentation-remedy protocol") from err
    for name in ("PROTOCOL_SHA256", "OPTION_MATRIX_SHA256"):
        if globals()[name] == "TO_PIN":
            raise ProtocolError("{} is not pinned".format(name))
    if "TO_PIN" in BATCH_WINDOWS.values():
        raise ProtocolError("batching windows are not pinned")
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("fragmentation-remedy protocol bytes changed")
    if (
        CONFIG_COUNT != 13
        or CELL_COUNT != 13676
        or len(LABELS) != len(set(LABELS))
        or option_matrix_digest() != OPTION_MATRIX_SHA256
        or len(primary_tests()) != 12
    ):
        raise ProtocolError("fragmentation-remedy option matrix changed")
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
