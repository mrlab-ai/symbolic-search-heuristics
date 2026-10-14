#!/usr/bin/env python3
"""Frozen constants for the prospective bounded-search study (Stage 2)."""

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
PROTOCOL_PATH = SCRIPT_DIR / "bounded_search_protocol.md"
PROTOCOL_SHA256 = "TO_PIN"
PROTOCOL = "bounded-search-measurement-v1"
ANALYSIS_PROTOCOL = "bounded-search-analysis-v1"
COHORT_ROLE = "prospective-bounded-search-holdout"
COHORT_FILE = Generality.COHORT_FILE
COHORT_TASKS = Generality.COHORT_TASKS
COHORT_DOMAINS = Generality.COHORT_DOMAINS
COHORT_MANIFEST_SHA256 = Generality.COHORT_MANIFEST_SHA256
TIME_LIMIT_SECONDS = Generality.TIME_LIMIT_SECONDS
MEMORY_LIMIT_MIB = Generality.MEMORY_LIMIT_MIB
REQUIRED_LAB_VERSION = Generality.REQUIRED_LAB_VERSION
REQUIRED_PYTHON_VERSION = Generality.REQUIRED_PYTHON_VERSION
BUILD_OPTIONS = Generality.BUILD_OPTIONS
PLANNER_REVISION = "61c127017e9404aeb8b0a9338f3edea0ac75fd75"
PLANNER_CACHE_NAME = "61c127017e9404ae_f638fdddf643"
PLANNER_BINARY_SHA256 = (
    "79ab63e5cd85be776131bdb0963d07bf60753f33aeaed18fcf9e69958e872f95"
)
PREPROCESS_BINARY_SHA256 = (
    "4323f8585f3d458370c4a79ce4488a1c70124cbc2ae9abc2c3ecb1af6bc2fd4e"
)
PLANNER_TREE_MANIFEST_SHA256 = (
    "526b0fb32838040701b40ced4a9fdf5c5ec4c889f35e4ef2b9fc65ea01dfce90"
)
CPLEX_DIR = Generality.CPLEX_DIR
CPLEX_LIBRARY = Generality.CPLEX_LIBRARY
CPLEX_LIBRARY_SHA256 = Generality.CPLEX_LIBRARY_SHA256

_LOG = 'wbh_log="{}"'.format(Source.LEGACY_LOG)
LAMA = (
    "let(hlm,landmark_sum(lm_factory=lm_reasonable_orders_hps(lm_rhw()),"
    "transform=adapt_costs(one),pref=false),"
    "let(hff,ff(transform=adapt_costs(one)),"
    "lazy_greedy([hff,hlm],preferred=[hff,hlm],cost_type=one,"
    "reopen_closed=false,max_time=30)))"
)
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
BLIND_BOUNDED = "blind_bounded"


def bounded(search):
    return (
        "iterated([{},{}],pass_bound=true,repeat_last=false,"
        "continue_on_fail=true,continue_on_solve=true)".format(LAMA, search)
    )


def _configs():
    configs = [
        (BLIND_FW, "sym_fw({})".format(_LOG)),
        (BLIND_BD, "sym_bd({})".format(_LOG)),
        (BLIND_BOUNDED, bounded("sym_fw({})".format(_LOG))),
    ]
    for family in FAMILY_NAMES:
        base = _BASE[family]
        configs.append(("{}_plain".format(family), base.format("," + _LOG)))
        configs.append((
            "{}_bounded".format(family),
            bounded(base.format(",prune_only=true," + _LOG)),
        ))
    return tuple(configs)


CONFIGS = _configs()
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
BOUNDED_LABELS = tuple(label for label in LABELS if label.endswith("_bounded"))
CONFIG_COUNT = len(CONFIGS)
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT
OPTION_MATRIX_SHA256 = "TO_PIN"

# Decision rule (Section 5).
ALPHA = Fraction(5, 100)
PAR2_UNSOLVED_SECONDS = 600


def primary_tests():
    """The nine primary comparisons as (name, config, reference)."""
    tests = []
    for family in FAMILY_NAMES:
        label = "{}_bounded".format(family)
        tests.append(("H1:" + label, label, "{}_plain".format(family)))
        tests.append(("H2:" + label, label, BLIND_FW))
        tests.append(("H3:" + label, label, BLIND_BOUNDED))
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
        raise ProtocolError("cannot read bounded-search protocol") from err
    for name in ("PROTOCOL_SHA256", "OPTION_MATRIX_SHA256",
                 "PLANNER_CACHE_NAME", "PLANNER_BINARY_SHA256",
                 "PREPROCESS_BINARY_SHA256", "PLANNER_TREE_MANIFEST_SHA256"):
        if globals()[name] == "TO_PIN":
            raise ProtocolError("{} is not pinned".format(name))
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("bounded-search protocol bytes changed")
    if (
        CONFIG_COUNT != 9
        or CELL_COUNT != 9468
        or len(LABELS) != len(set(LABELS))
        or option_matrix_digest() != OPTION_MATRIX_SHA256
        or len(primary_tests()) != 9
        or len(BOUNDED_LABELS) != 4
    ):
        raise ProtocolError("bounded-search option matrix changed")
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
