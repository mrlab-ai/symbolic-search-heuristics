#!/usr/bin/env python3
"""Frozen constants for the prospective strong-heuristics decomposition study."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pdb_profile_harm_generality_protocol as Generality


Source = Generality.Source
Holdout = Generality.Holdout
Task = Generality.Task


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
PROTOCOL_PATH = SCRIPT_DIR / "strong_heuristics_protocol.md"
PROTOCOL_SHA256 = (
    "81cc52f787efa6f01ac5425ec9bfcbc07881c691e1d184dc68c8cec4e55bf5fe"
)
PROTOCOL = "strong-heuristics-measurement-v1"
ANALYSIS_PROTOCOL = "strong-heuristics-analysis-v1"
COHORT_ROLE = "prospective-strong-heuristics-holdout"
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

BLIND_LABEL = Generality.BLIND_LABEL
POT_STRONG = "pot_all_m1000"
MS_STRONG = "ms_unaligned_200k"
_LOGS = Generality._LOGS
CONFIGS = (
    (BLIND_LABEL, "sym_fw({})".format(_LOGS)),
    (POT_STRONG,
     "sym_fw_pot(m=1000,all_states_objective=true,{})".format(_LOGS)),
    (MS_STRONG,
     "sym_fw_ms(max_states=200000,align_merge_order=false,"
     "build_time_limit=infinity,{})".format(_LOGS)),
)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
FAMILIES = {POT_STRONG: "pot", MS_STRONG: "ms"}
CONFIG_COUNT = len(CONFIGS)
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT
OPTION_MATRIX_SHA256 = (
    "cf6cc9aa8df461a88f605f4fa6a3b59e4298b289f1b036de7a2b71c1dd2b88dd"
)

# Decision rule and timing rule of the harm-generality study (Section 5).
MIN_HARMFUL_PAIRS = Generality.MIN_HARMFUL_PAIRS
MIN_HARMFUL_DOMAINS = Generality.MIN_HARMFUL_DOMAINS
MIN_SHARE = Generality.MIN_SHARE
STRONG_RATIO = Generality.STRONG_RATIO
MIN_STRONG_PAIRS = Generality.MIN_STRONG_PAIRS
MIN_STRONG_SHARE = Generality.MIN_STRONG_SHARE
HARD_BLIND_SECONDS = Generality.HARD_BLIND_SECONDS
TIME_HARM_RATIO = Generality.TIME_HARM_RATIO
TIME_HELP_RATIO = Generality.TIME_HELP_RATIO
OVERHEAD_FIELDS = Generality.OVERHEAD_FIELDS


def option_matrix_digest(configs=CONFIGS) -> str:
    payload = [{"label": label, "search": search} for label, search in configs]
    return hashlib.sha256(Source.canonical_json(payload)).hexdigest()


def load_cohort(archive=None):
    return Generality.load_cohort(archive)


def validate_protocol_without_archive() -> None:
    try:
        raw = PROTOCOL_PATH.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read strong-heuristics protocol") from err
    for name in ("PROTOCOL_SHA256", "OPTION_MATRIX_SHA256"):
        if globals()[name] == "TO_PIN":
            raise ProtocolError("{} is not pinned".format(name))
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("strong-heuristics protocol bytes changed")
    if (
        CONFIG_COUNT != 3
        or CELL_COUNT != 3156
        or LABELS[0] != BLIND_LABEL
        or SEARCHES[BLIND_LABEL] != Generality.SEARCHES[BLIND_LABEL]
        or option_matrix_digest() != OPTION_MATRIX_SHA256
    ):
        raise ProtocolError("strong-heuristics option matrix changed")
    for _, search in CONFIGS:
        if search.count(_LOGS) != 1:
            raise ProtocolError("configuration lacks its log options")


if __name__ == "__main__":
    validate_protocol_without_archive()
    cohort = load_cohort()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            len(cohort), CONFIG_COUNT, CELL_COUNT
        )
    )
