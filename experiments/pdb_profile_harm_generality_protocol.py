#!/usr/bin/env python3
"""Frozen constants for the prospective harm-generality study."""

from __future__ import annotations

import collections
import hashlib
from fractions import Fraction
from pathlib import Path

import pdb_profile_certificate_holdout_protocol as Holdout


Source = Holdout.Source


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
PROTOCOL_PATH = SCRIPT_DIR / "pdb_profile_harm_generality_protocol.md"
PROTOCOL_SHA256 = (
    "1350601f4134b78d480e500749f6a5546c041894cfe70fe2d3169aa329599b14"
)
PROTOCOL = "pdb-profile-harm-generality-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-profile-harm-generality-analysis-v1"
COHORT_ROLE = "prospective-harm-generality-holdout"
# The cap-grid archive behind Holdout.load_cohort was lost on 2026-10-03.
# The holdout task list was recovered from the sealed seed-validation
# properties; its bytes hash to the frozen holdout manifest digest.
COHORT_FILE = SCRIPT_DIR / "pdb_profile_harm_generality_cohort.txt"
COHORT_TASKS = Holdout.COHORT_TASKS
COHORT_DOMAINS = Holdout.COHORT_DOMAINS
COHORT_MANIFEST_SHA256 = Holdout.COHORT_MANIFEST_SHA256
TIME_LIMIT_SECONDS = Holdout.TIME_LIMIT_SECONDS
MEMORY_LIMIT_MIB = Holdout.MEMORY_LIMIT_MIB
REQUIRED_LAB_VERSION = Holdout.REQUIRED_LAB_VERSION
REQUIRED_PYTHON_VERSION = "3.9.25"
BUILD_OPTIONS = ("release",)
PLANNER_REVISION = "580a6ee3b39489cb0a3f1d4e187b52601b751eab"
PLANNER_BINARY_SHA256 = (
    "3e787375cedb75738fb9bf20c95fad5616b4416850d8aa911dcfcfb6a6055b2e"
)
PREPROCESS_BINARY_SHA256 = (
    "c86d091e53767fccb8e8d8fc23484899f22139a57a2e167fd7d14d55aa6d1c67"
)
PLANNER_TREE_MANIFEST_SHA256 = (
    "c4f01fbcac3b6fcb7361564b3c3c5288f2dc525d2072aea4602a74d0e2f00982"
)
CPLEX_DIR = Path(
    "/nobackup/proj/disk/dfsplan/personal/jendrik/"
    "opt/ibm/ILOG/CPLEX_Studio2211/cplex"
)
CPLEX_LIBRARY = CPLEX_DIR / "bin" / "x86-64_linux" / "libcplex2211.so"
CPLEX_LIBRARY_SHA256 = (
    "8d187aeef04f2e04627880034d0d2c3a14c61873872fca0a2fed6a400bf74bd1"
)

BLIND_LABEL = "blind_fw_profiled"
_LOGS = 'wbh_log="{}",wbh_profile_log="{}"'.format(
    Source.LEGACY_LOG, Source.PROFILE_LOG
)


def _ms(max_states: int, aligned: bool) -> str:
    return (
        "sym_fw_ms(max_states={},align_merge_order={},"
        "build_time_limit=infinity,{})".format(
            max_states, "true" if aligned else "false", _LOGS
        )
    )


CONFIGS = (
    (BLIND_LABEL, "sym_fw({})".format(_LOGS)),
    ("ms_unaligned_10k", _ms(10000, False)),
    ("ms_aligned_10k", _ms(10000, True)),
    ("ms_unaligned_50k", _ms(50000, False)),
    (
        "pdb_cegar_1m",
        "sym_fw_pdb(budget=1000000,pattern_selection=cegar,"
        "cegar_max_time=10,cegar_seed=2011,{})".format(_LOGS),
    ),
    ("pot_m4", "sym_fw_pot(m=4,{})".format(_LOGS)),
)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
FAMILIES = {
    "ms_unaligned_10k": "ms",
    "ms_aligned_10k": "ms",
    "ms_unaligned_50k": "ms",
    "pdb_cegar_1m": "pdb",
    "pot_m4": "pot",
}
NON_PDB_FAMILIES = ("ms", "pot")
CONFIG_COUNT = len(CONFIGS)
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT
OPTION_MATRIX_SHA256 = (
    "eeab85727fbdd88d2b808f2b42ea1973809ea9deb52bc3d51f8852b3ffbfb003"
)

# Decision rule (Section 5 of the protocol).
MIN_HARMFUL_PAIRS = 100
MIN_HARMFUL_DOMAINS = 20
MIN_SHARE = Fraction(9, 10)
STRONG_RATIO = 2
MIN_STRONG_PAIRS = 20
MIN_STRONG_SHARE = Fraction(95, 100)
# Secondary, descriptive quantities.
HARD_BLIND_SECONDS = 10
TIME_HARM_RATIO = Fraction(3, 2)
TIME_HELP_RATIO = Fraction(2, 3)
GUARD_HEADROOM_FRACTION = Fraction(3, 100)
OVERHEAD_FIELDS = (
    "union_seconds",
    "cofactor_seconds",
    "heuristic_cofactor_seconds",
    "joint_cofactor_seconds",
    "masked_seconds",
    "partition_audit_seconds",
    "serialization_seconds",
    "output_seconds",
)

Task = collections.namedtuple("Task", "domain problem")


def option_matrix_digest(configs=CONFIGS) -> str:
    payload = [
        {"label": label, "search": search}
        for label, search in configs
    ]
    return hashlib.sha256(Source.canonical_json(payload)).hexdigest()


def load_cohort(_archive=None):
    """Load the recovered holdout task list; the archive argument is unused."""
    try:
        raw = COHORT_FILE.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read the harm-generality cohort") from err
    if hashlib.sha256(raw).hexdigest() != COHORT_MANIFEST_SHA256:
        raise ProtocolError("harm-generality cohort bytes changed")
    tasks = tuple(
        Task(*line.split(":", 1))
        for line in raw.decode("ascii").splitlines()
    )
    if (
        len(tasks) != COHORT_TASKS
        or len(set(tasks)) != COHORT_TASKS
        or len({task.domain for task in tasks}) != COHORT_DOMAINS
        or list(tasks) != sorted(tasks)
    ):
        raise ProtocolError("harm-generality cohort identity changed")
    return tasks


def validate_protocol_without_archive() -> None:
    try:
        raw = PROTOCOL_PATH.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read harm-generality protocol") from err
    for name in ("PROTOCOL_SHA256", "OPTION_MATRIX_SHA256"):
        if globals()[name] == "TO_PIN":
            raise ProtocolError("{} is not pinned".format(name))
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("harm-generality protocol bytes changed")
    if (
        CONFIG_COUNT != 6
        or CELL_COUNT != 6312
        or len(LABELS) != len(set(LABELS))
        or LABELS[0] != BLIND_LABEL
        or set(FAMILIES) != set(LABELS[1:])
        or set(NON_PDB_FAMILIES) | {"pdb"} != set(FAMILIES.values())
        or option_matrix_digest() != OPTION_MATRIX_SHA256
    ):
        raise ProtocolError("harm-generality option matrix changed")
    for label, search in CONFIGS:
        if search.count(_LOGS) != 1:
            raise ProtocolError("configuration lacks its log options")
        if label != BLIND_LABEL and {
            "ms": "sym_fw_ms(",
            "pdb": "sym_fw_pdb(",
            "pot": "sym_fw_pot(",
        }[FAMILIES[label]] not in search:
            raise ProtocolError("label and search family disagree")


if __name__ == "__main__":
    validate_protocol_without_archive()
    cohort = load_cohort()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            len(cohort), CONFIG_COUNT, CELL_COUNT
        )
    )
