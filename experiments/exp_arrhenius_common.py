"""Shared, fail-closed support for prospective Arrhenius experiments.

This module is deliberately separate from :mod:`exp_common`, which freezes the
Tetralith protocol used by earlier experiments.  It never compiles a planner:
prospective ``build`` and ``start`` steps require a pre-existing, hash-pinned
``release_no_lp`` Downward Lab revision cache.

Run the in-memory scheduler compatibility tests with::

    python experiments/exp_arrhenius_common.py

The tests write no experiment files and submit no jobs.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import re
import stat
import subprocess
import sys
import tempfile
from fractions import Fraction
from pathlib import Path

from downward.cached_revision import CachedFastDownwardRevision
from downward.experiment import FastDownwardExperiment
from downward.reports.absolute import AbsoluteReport
from lab import tools
from lab.environments import SlurmEnvironment, is_run_step
from lab.parser import Parser

import wbh_parser


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
REQUIREMENTS = SCRIPT_DIR / "requirements.txt"
REVISION_CACHE = Path(
    os.environ.get(
        "DOWNWARD_REVISION_CACHE", str(SCRIPT_DIR / "data" / "revision-cache")
    )
).resolve()

REV = subprocess.run(
    ["git", "-C", str(REPO), "rev-parse", "HEAD"],
    check=True,
    capture_output=True,
    text=True,
).stdout.strip()

# Planner and scheduler limits for the preliminary screens.
TIME_LIMIT = "300s"
TIME_LIMIT_SECONDS = 300
MEMORY_LIMIT = "8G"
BUILD_OPTIONS = ["release_no_lp"]
CACHE_BUILD_NAME = "release_no_lp"
CACHE_SENTINEL_SHA256 = (
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
)
LAB_DEFAULT_DRIVER_PREFIX = [
    "--validate",
    "--overall-time-limit",
    "30m",
    "--overall-memory-limit",
    "3584M",
]
PLAN_VALIDATION_PROTOCOL = (
    "no-external-val;canonical-plan-log-wbh-cost-and-raw-exit-reconciliation/v2"
)
PLAN_FILE_PARSER_PROTOCOL = (
    "sas_plan/exact-zero-or-single-stable-single-link-regular-"
    "nonsymlink-cost-footer/v2"
)
OUTCOME_RECONCILIATION_PROTOCOL = (
    "direct-search-raw-effective-plan-reconciliation/v1"
)
PDDL_MATERIALIZATION_PROTOCOL = (
    "per-cell-independent-manual-byte-copy-temp-digest-atomic-replace-"
    "readonly/v1"
)

# Arrhenius CPU nodes are homogeneous AMD EPYC 9755 nodes.  MAX_TASKS follows
# Slurm's MaxArraySize=1001: Lab uses one-based array indices, hence at most
# 1000 array elements.
SCHEDULER_CLUSTER = "arrhenius"
SCHEDULER_CPU_MODEL = "AMD EPYC 9755 128-Core Processor"
SCHEDULER_PARTITION = "cpu"
SCHEDULER_QOS = "normal"
SCHEDULER_ACCOUNT = os.environ.get(
    "WBH_ACCOUNT", "naiss2025-5-382-cpu"
)
SCHEDULER_TIME_LIMIT = os.environ.get("WBH_TASK_TIME", "00:10:00")
SCHEDULER_MEMORY_PER_CPU = os.environ.get("WBH_MEMORY_PER_CPU", "9G")
SCHEDULER_CPUS_PER_TASK = 1
ARRAY_TASK_THROTTLE = 5
MAX_ARRAY_TASKS = 1000
SCHEDULER_WRAPPER_ALLOWANCE_SECONDS = 60

TASK_ORDER_SEED = "symbolic-search-heuristics/arrhenius-task-order/v1"
TASK_ORDER_METHOD = (
    "sha256(seed-nul-array-count-nul-array-id)-sort;"
    "ascending-run-id-within-array-task/v1"
)
WBH_LOG = "wbh.jsonl"
COFACTOR_WIDTH_PROPERTY = "cofactor_width"
COFACTOR_WIDTH_PARSER_PROTOCOL = (
    "run.log/unique-wbh-heuristic-cofactor-width/v1"
)
PDB_SELECTOR_PARSER_PROTOCOL = (
    "run.log/pdb-final-and-width-selector-v1-whole-trace/v3"
)
PDB_SELECTOR_CANDIDATES_PROPERTY = "pdb_selector_candidates"
PDB_SELECTOR_SELECTED_PROPERTY = "pdb_selector_selected"
PDB_SELECTOR_FINAL_PROPERTY = "pdb_selector_final"
PDB_SELECTOR_TRACE_COMPLETE_PROPERTY = "pdb_selector_trace_complete"
PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY = "pdb_selector_trace_certified"
PDB_SELECTOR_VALIDATION_ERROR_PROPERTY = "pdb_selector_validation_error"
PDB_SELECTOR_TRACE_SHA256_PROPERTY = "pdb_selector_trace_sha256"
PDB_SELECTOR_POOL_SHA256_PROPERTY = "pdb_selector_pool_sha256"

PDB_SELECTOR_RECORD_KEYS = (
    "protocol",
    "score_version",
    "sources",
    "pattern",
    "abstract_states",
    "initial_dead_end",
    "initial_h",
    "finite_sum",
    "finite_count",
    "dead_count",
    "cofactor_width",
    "width_upper_bound",
    "cofactor_width_budget",
    "feasible",
    "rejection_reason",
)
PDB_SELECTOR_SOURCES = (
    "empty",
    "bdd_prefix",
    "goal_prefix",
    "goal_fill",
    "cegar",
)
PDB_SELECTOR_POOL_PROTOCOL = "fixed_pool_v1"
PDB_SELECTOR_SCORE_VERSION = (
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
)

_SLURM_ARRAY_DIRECTIVE = "#SBATCH --array="
_RANDOM_RUN_LOOP = (
    "for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID | shuf); do"
)
_DETERMINISTIC_RUN_LOOP = (
    "for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID); do"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WBH_HEURISTIC_LINE_RE = re.compile(
    r"^\[t=\d+\.\d{6}s, \d+ KB\] "
    r"wbh [^:\r\n]+ heuristic:[^\r\n]*$",
    re.MULTILINE,
)
_ANY_WBH_HEURISTIC_LINE_RE = re.compile(
    r"^[^\r\n]*\bwbh [^:\r\n]+ heuristic:[^\r\n]*$", re.MULTILINE
)
_COFACTOR_WIDTH_FIELD_RE = re.compile(
    r"(?:^|, )cofactor_width=(\d+)(?=, |$)"
)
_PLAN_COST_RE = re.compile(
    r"^; cost = (0|[1-9][0-9]*) \((?:unit|general) cost\)$",
    re.MULTILINE,
)
_CANONICAL_SIGNED_INT_RE = r"(0|[1-9][0-9]*|-[1-9][0-9]*)"
_SEARCH_RAW_EXIT_RE = re.compile(
    r"^search raw exit code: " + _CANONICAL_SIGNED_INT_RE + r"$"
)
_SEARCH_EFFECTIVE_EXIT_RE = re.compile(
    r"^search exit code: " + _CANONICAL_SIGNED_INT_RE + r"$"
)
_SEARCH_RECONCILIATION_RE = re.compile(
    r"^search resource-limit exit with complete plan: "
    r"raw_exit_code=" + _CANONICAL_SIGNED_INT_RE
    + r" effective_exit_code=" + _CANONICAL_SIGNED_INT_RE + r"$"
)
_MAPPED_RESOURCE_EXITS = {22: 1, 23: 2, 24: 3}
_PRESEARCH_EXIT_CODES = frozenset((10, 20, 21))
_LOG_PREFIX = r"\[t=\d+\.\d{6}s, \d+ KB\] "
_RUN_LOG_PLAN_COST_RE = re.compile(
    r"^" + _LOG_PREFIX + r"Plan cost: (0|[1-9][0-9]*)$", re.MULTILINE
)
_PDB_FINAL_MARKER = "wbh PDB heuristic:"
_PDB_SELECTOR_CANDIDATE_MARKER = "PDB width-selector v1 candidate:"
_PDB_SELECTOR_SELECTED_MARKER = "PDB width-selector v1 selected:"
_PDB_LEGACY_FINAL_RE = re.compile(
    "^" + _LOG_PREFIX
    + r"wbh PDB heuristic: pattern_size=(\d+), values=(\d+), "
      r"cofactor_width=(\d+), width_upper_bound=(\d+)$"
)
_PDB_SELECTOR_FINAL_RE = re.compile(
    "^" + _LOG_PREFIX
    + r"wbh PDB heuristic: pattern_size=(\d+), "
      r"selected_source=([a-z_]+), abstract_states=(\d+), "
      r"cofactor_width_budget=(\d+), values=(\d+), "
      r"cofactor_width=(\d+), width_upper_bound=(\d+)$"
)
_PDB_SELECTOR_LOG_RE = re.compile(
    "^" + _LOG_PREFIX
    + r"PDB width-selector v1 (candidate|selected): (.*)$"
)


def parse_cofactor_width(content, props) -> None:
    """Parse the one exact heuristic width printed to ``run.log``.

    Blind runs intentionally have no ``wbh ... heuristic:`` line.  Any
    heuristic run has exactly one such line and exactly one integer
    ``cofactor_width`` field.  Treat repetitions and malformed fields as
    unexplained errors instead of silently selecting one value.
    """
    candidates = _ANY_WBH_HEURISTIC_LINE_RE.findall(content)
    if not candidates:
        return
    if len(candidates) != 1:
        tools.add_unexplained_error(
            props,
            "cofactor-width parser expected one wbh heuristic line; got {}".
            format(len(candidates)),
        )
        return
    lines = _WBH_HEURISTIC_LINE_RE.findall(content)
    if lines != candidates:
        tools.add_unexplained_error(
            props,
            "cofactor-width parser rejected a nonstandard run.log prefix",
        )
        return

    fields = _COFACTOR_WIDTH_FIELD_RE.findall(lines[0])
    if len(fields) != 1:
        tools.add_unexplained_error(
            props,
            "cofactor-width parser expected one integer field; got {}".
            format(len(fields)),
        )
        return
    props[COFACTOR_WIDTH_PROPERTY] = int(fields[0])


def get_cofactor_width_parser() -> Parser:
    parser = Parser()
    parser.add_function(parse_cofactor_width, file="run.log")
    return parser


def _reject_json_constant(value):
    raise ValueError("non-finite JSON constant {!r}".format(value))


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key {!r}".format(key))
        result[key] = value
    return result


def _is_nonnegative_int(value):
    return type(value) is int and value >= 0


def _validate_selector_record(record, kind):
    """Return an error for a malformed stable selector record, else None."""
    if not isinstance(record, dict):
        return "{} payload must be a JSON object".format(kind)
    if tuple(record) != PDB_SELECTOR_RECORD_KEYS:
        return "{} payload keys/order changed: {!r}".format(
            kind, tuple(record)
        )
    if record["protocol"] != PDB_SELECTOR_POOL_PROTOCOL:
        return "{} protocol changed".format(kind)
    if record["score_version"] != PDB_SELECTOR_SCORE_VERSION:
        return "{} score_version changed".format(kind)

    sources = record["sources"]
    if (
        not isinstance(sources, list)
        or not sources
        or any(type(source) is not str for source in sources)
        or len(sources) != len(set(sources))
        or any(source not in PDB_SELECTOR_SOURCES for source in sources)
    ):
        return "{} sources are malformed".format(kind)
    source_positions = [PDB_SELECTOR_SOURCES.index(source) for source in sources]
    if source_positions != sorted(source_positions):
        return "{} sources violate fixed-pool order".format(kind)

    pattern = record["pattern"]
    if (
        not isinstance(pattern, list)
        or any(not _is_nonnegative_int(var) for var in pattern)
        or pattern != sorted(set(pattern))
    ):
        return "{} pattern must be sorted unique nonnegative integers".format(
            kind
        )
    if not _is_nonnegative_int(record["abstract_states"]) or record[
        "abstract_states"
    ] < 1:
        return "{} abstract_states must be a positive integer".format(kind)
    if not _is_nonnegative_int(record["cofactor_width_budget"]) or record[
        "cofactor_width_budget"
    ] < 1:
        return "{} cofactor_width_budget must be positive".format(kind)
    if type(record["feasible"]) is not bool:
        return "{} feasible must be boolean".format(kind)

    statistic_fields = (
        "initial_dead_end",
        "initial_h",
        "finite_sum",
        "finite_count",
        "dead_count",
        "cofactor_width",
        "width_upper_bound",
    )
    unmaterialized = all(record[field] is None for field in statistic_fields)
    if unmaterialized:
        if (
            kind == "selected"
            or record["feasible"] is not False
            or record["rejection_reason"] != "abstract_state_budget"
        ):
            return "{} unmaterialized record has inconsistent outcome".format(
                kind
            )
        if record["sources"] != ["cegar"]:
            return (
                "{} abstract-state-budget rejection must be the lone CEGAR "
                "candidate".format(kind)
            )
        if len(record["pattern"]) != 1:
            return (
                "{} abstract-state-budget CEGAR rejection must be the "
                "oversized initial singleton".format(kind)
            )
        return None

    if type(record["initial_dead_end"]) is not bool:
        return "{} initial_dead_end must be boolean".format(kind)
    if record["initial_dead_end"]:
        if record["initial_h"] is not None:
            return "{} dead initial state must use initial_h=null".format(kind)
    elif not _is_nonnegative_int(record["initial_h"]):
        return "{} finite initial_h must be nonnegative integer".format(kind)
    for field in ("finite_sum", "finite_count", "dead_count"):
        if not _is_nonnegative_int(record[field]):
            return "{} {} must be a nonnegative integer".format(kind, field)
    if record["finite_count"] + record["dead_count"] != record[
        "abstract_states"
    ]:
        return "{} finite/dead counts do not cover abstract states".format(kind)
    if record["finite_count"] < 1:
        return "{} record must contain at least one finite abstract goal state".format(
            kind
        )
    if (
        not record["initial_dead_end"]
        and record["finite_sum"] < record["initial_h"]
    ):
        return "{} finite_sum is smaller than the finite initial_h".format(kind)
    if record["initial_dead_end"] and record["dead_count"] == 0:
        return "{} initial dead end has zero dead states".format(kind)
    width = record["cofactor_width"]
    upper = record["width_upper_bound"]
    if not _is_nonnegative_int(width) or width < 1:
        return "{} cofactor_width must be positive".format(kind)
    if not _is_nonnegative_int(upper) or upper < width:
        return "{} width_upper_bound is invalid".format(kind)
    expected_feasible = width <= record["cofactor_width_budget"]
    if record["feasible"] is not expected_feasible:
        return "{} feasibility contradicts exact width budget".format(kind)
    expected_reason = None if expected_feasible else "cofactor_width_budget"
    if record["rejection_reason"] != expected_reason:
        return "{} rejection_reason contradicts feasibility".format(kind)
    if kind == "selected" and not expected_feasible:
        return "selected record is infeasible"
    return None


def canonical_pdb_selector_json(value):
    """Return the selector protocol's stable, finite ASCII JSON encoding."""
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def pdb_selector_trace_sha256(candidates, selected, final):
    """Hash a certified whole trace independently of run.log timestamps."""
    payload = {
        "candidates": candidates,
        "selected": selected,
        "final": final,
    }
    return hashlib.sha256(
        canonical_pdb_selector_json(payload).encode("ascii")
    ).hexdigest()


def pdb_selector_pool_sha256(candidates):
    """Hash candidate identities/scores while omitting K-dependent outcomes."""
    omitted = {
        "cofactor_width_budget",
        "feasible",
        "rejection_reason",
    }
    normalized = [
        {key: value for key, value in record.items() if key not in omitted}
        for record in candidates
    ]
    return hashlib.sha256(
        canonical_pdb_selector_json(normalized).encode("ascii")
    ).hexdigest()


def _selector_score_key(record):
    """Exact ascending key for the C++ selector's descending score."""
    if record["finite_count"] == 0:
        # PatternDatabase::compute_mean_finite_h defines this mean as +infinity.
        mean_key = (0, Fraction(0))
    else:
        mean_key = (
            1,
            -Fraction(record["finite_sum"], record["finite_count"]),
        )
    initial_h = record["initial_h"]
    return (
        -int(record["initial_dead_end"]),
        -(initial_h if initial_h is not None else 0),
        mean_key,
        -Fraction(record["dead_count"], record["abstract_states"]),
        record["cofactor_width"],
        record["abstract_states"],
        tuple(record["pattern"]),
    )


def _validate_selector_whole_trace(candidates, selected, final):
    errors = []
    if not 1 <= len(candidates) <= len(PDB_SELECTOR_SOURCES):
        errors.append(
            "selector trace needs 1-{} deduplicated candidates; got {}".format(
                len(PDB_SELECTOR_SOURCES), len(candidates)
            )
        )
        return errors

    patterns = [tuple(record["pattern"]) for record in candidates]
    if len(patterns) != len(set(patterns)):
        errors.append("selector candidate patterns are not deduplicated")
    if "empty" not in candidates[0]["sources"]:
        errors.append("selector candidate prefix does not start with empty")

    source_owner = {}
    first_source_positions = []
    for candidate_index, record in enumerate(candidates):
        positions = [
            PDB_SELECTOR_SOURCES.index(source)
            for source in record["sources"]
        ]
        first_source_positions.append(positions[0])
        for source in record["sources"]:
            if source in source_owner:
                errors.append(
                    "selector source {!r} occurs in multiple candidates".format(
                        source
                    )
                )
            else:
                source_owner[source] = candidate_index
    missing_sources = [
        source for source in PDB_SELECTOR_SOURCES if source not in source_owner
    ]
    if missing_sources and (selected is not None or final is not None):
        errors.append(
            "selector trace is missing fixed-pool sources {}".format(
                ", ".join(missing_sources)
            )
        )
    if first_source_positions != sorted(first_source_positions) or len(
        first_source_positions
    ) != len(set(first_source_positions)):
        errors.append("selector candidates violate fixed first-source order")
    if first_source_positions:
        # All candidate specifications are created in fixed source order before
        # any record is logged. A later source may deduplicate into an earlier
        # candidate, but a newly introduced candidate cannot skip an earlier
        # source: that source would already own an earlier candidate or appear
        # in one of the records seen so far.
        observed_positions = {
            PDB_SELECTOR_SOURCES.index(source) for source in source_owner
        }
        required_positions = set(range(max(observed_positions) + 1))
        missing_prefix = sorted(required_positions - observed_positions)
        if missing_prefix:
            errors.append(
                "selector candidate prefix skips earlier fixed-pool sources {}".
                format(
                    ", ".join(PDB_SELECTOR_SOURCES[pos] for pos in missing_prefix)
                )
            )

    empty_records = [
        record for record in candidates if "empty" in record["sources"]
    ]
    if len(empty_records) == 1:
        empty = empty_records[0]
        expected_empty = {
            "pattern": [],
            "abstract_states": 1,
            "initial_dead_end": False,
            "initial_h": 0,
            "finite_sum": 0,
            "finite_count": 1,
            "dead_count": 0,
            "cofactor_width": 1,
            "width_upper_bound": 1,
            "feasible": True,
            "rejection_reason": None,
        }
        mismatches = [
            key
            for key, value in expected_empty.items()
            if empty.get(key) != value
        ]
        if mismatches:
            errors.append(
                "empty-pattern candidate violates its exact invariants: {}".
                format(", ".join(mismatches))
            )

    budgets = {record["cofactor_width_budget"] for record in candidates}
    if selected is not None:
        budgets.add(selected["cofactor_width_budget"])
    if final is not None:
        budgets.add(final["cofactor_width_budget"])
    if len(budgets) != 1:
        errors.append("selector trace does not use one common width budget K")

    if selected is None:
        if final is not None:
            errors.append("selector final exists without a selected record")
        return errors
    matching = [record for record in candidates if record == selected]
    if len(matching) != 1:
        errors.append(
            "selected record is not value-equal to one candidate record"
        )
    feasible = [record for record in candidates if record["feasible"]]
    if not feasible:
        errors.append("selector trace contains no feasible candidate")
    else:
        expected = min(feasible, key=_selector_score_key)
        if selected != expected:
            errors.append(
                "selected record is not the independently recomputed exact winner"
            )

    if final is not None:
        comparisons = {
            "pattern_size": len(selected["pattern"]),
            "selected_source": selected["sources"][0],
            "abstract_states": selected["abstract_states"],
            "cofactor_width_budget": selected["cofactor_width_budget"],
            "cofactor_width": selected["cofactor_width"],
            "width_upper_bound": selected["width_upper_bound"],
        }
        for key, expected in comparisons.items():
            if final.get(key) != expected:
                errors.append(
                    "selector final {}={!r}, selected record requires {!r}".
                    format(key, final.get(key), expected)
                )
        num_values = final["num_values"]
        finite_count = selected["finite_count"]
        if num_values < 1:
            errors.append("selector final must contain at least one finite value")
        elif num_values > finite_count:
            errors.append(
                "selector final num_values exceeds selected finite_count"
            )
    return errors


def parse_pdb_selector_log(content, props) -> None:
    """Parse strict legacy/exact PDB finals and selector JSON from run.log."""
    lines = content.splitlines()
    final_entries = [
        (index, line)
        for index, line in enumerate(lines)
        if _PDB_FINAL_MARKER in line
    ]
    selector_entries = [
        (index, line)
        for index, line in enumerate(lines)
        if "PDB width-selector" in line
    ]
    final_lines = [line for _, line in final_entries]
    selector_lines = [line for _, line in selector_entries]
    if not final_lines and not selector_lines:
        return

    errors = []
    final_format = None
    final = None
    if len(final_lines) != 1:
        errors.append(
            "PDB final parser expected one line; got {}".format(
                len(final_lines)
            )
        )
    else:
        legacy_match = _PDB_LEGACY_FINAL_RE.fullmatch(final_lines[0])
        selector_match = _PDB_SELECTOR_FINAL_RE.fullmatch(final_lines[0])
        if legacy_match:
            final_format = "legacy"
            pattern_size, values, width, upper = map(
                int, legacy_match.groups()
            )
            props.update(
                {
                    "pdb_final_format": final_format,
                    "pdb_pattern_size": pattern_size,
                    "pdb_final_num_values": values,
                    "pdb_final_cofactor_width": width,
                    "pdb_final_width_upper_bound": upper,
                }
            )
        elif selector_match:
            final_format = "exact_width_filter"
            (
                pattern_size,
                selected_source,
                abstract_states,
                width_budget,
                values,
                width,
                upper,
            ) = selector_match.groups()
            integer_values = list(
                map(
                    int,
                    (
                        pattern_size,
                        abstract_states,
                        width_budget,
                        values,
                        width,
                        upper,
                    ),
                )
            )
            (
                pattern_size,
                abstract_states,
                width_budget,
                values,
                width,
                upper,
            ) = integer_values
            final = {
                "pattern_size": pattern_size,
                "selected_source": selected_source,
                "abstract_states": abstract_states,
                "cofactor_width_budget": width_budget,
                "num_values": values,
                "cofactor_width": width,
                "width_upper_bound": upper,
            }
            props.update(
                {
                    "pdb_final_format": final_format,
                    "pdb_pattern_size": pattern_size,
                    "pdb_selected_source": selected_source,
                    "pdb_abstract_states": abstract_states,
                    "pdb_cofactor_width_budget": width_budget,
                    "pdb_final_num_values": values,
                    "pdb_final_cofactor_width": width,
                    "pdb_final_width_upper_bound": upper,
                }
            )
            if selected_source not in PDB_SELECTOR_SOURCES:
                errors.append("selector final selected_source is unknown")
            if abstract_states < 1:
                errors.append("selector final abstract_states must be positive")
            if width_budget < 1:
                errors.append(
                    "selector final cofactor_width_budget must be positive"
                )
            if width < 1 or upper < width:
                errors.append("selector final exact/upper widths are invalid")
        else:
            errors.append("PDB final parser rejected malformed/unknown format")

    candidates = []
    selected = []
    record_kinds = []
    records_are_valid = True
    for line in selector_lines:
        match = _PDB_SELECTOR_LOG_RE.fullmatch(line)
        if not match:
            errors.append("selector parser rejected nonstandard log line")
            records_are_valid = False
            continue
        kind, payload = match.groups()
        record_kinds.append(kind)
        try:
            record = json.loads(
                payload,
                object_pairs_hook=_unique_json_object,
                parse_constant=_reject_json_constant,
            )
        except (TypeError, ValueError, json.JSONDecodeError) as err:
            errors.append("selector {} JSON is malformed: {}".format(kind, err))
            records_are_valid = False
            continue
        error = _validate_selector_record(record, kind)
        if error:
            errors.append(error)
            records_are_valid = False
        if kind == "candidate":
            candidates.append(record)
        else:
            selected.append(record)

    is_selector_trace = bool(selector_lines) or final_format == "exact_width_filter"
    if not is_selector_trace:
        # Preserve the original legacy behavior and diagnostics exactly: legacy
        # PDB finals gain only their final-value properties and malformed finals
        # remain unexplained run errors.
        for error in errors:
            tools.add_unexplained_error(props, error)
        return

    raw_candidate_count = sum(
        _PDB_SELECTOR_CANDIDATE_MARKER in line for line in selector_lines
    )
    raw_selected_count = sum(
        _PDB_SELECTOR_SELECTED_MARKER in line for line in selector_lines
    )
    expected_kind_sequence = ["candidate"] * raw_candidate_count
    if raw_selected_count:
        expected_kind_sequence += ["selected"] * raw_selected_count
    record_order_valid = record_kinds == expected_kind_sequence and not (
        raw_selected_count and raw_candidate_count == 0
    )
    if not record_order_valid:
        errors.append(
            "selector records must be candidate+ followed by one terminal "
            "selected record"
        )
    final_order_valid = not (
        final_entries
        and selector_entries
        and final_entries[0][0] <= selector_entries[-1][0]
    )
    if not final_order_valid:
        errors.append("selector final line must follow all selector records")
    complete = (
        1 <= raw_candidate_count <= len(PDB_SELECTOR_SOURCES)
        and raw_selected_count == 1
        and len(final_lines) == 1
        and final_format == "exact_width_filter"
    )
    if not 1 <= raw_candidate_count <= len(PDB_SELECTOR_SOURCES):
        errors.append(
            "selector trace needs 1-{} candidate lines; got {}".format(
                len(PDB_SELECTOR_SOURCES), raw_candidate_count
            )
        )
    if raw_selected_count != 1:
        errors.append(
            "selector trace needs one selected line; got {}".format(
                raw_selected_count
            )
        )
    if final_format == "legacy":
        errors.append("legacy PDB final unexpectedly has selector records")
    elif final_format != "exact_width_filter":
        errors.append("selector records lack one exact selector final")

    selected_record = selected[0] if len(selected) == 1 else None
    if len(selected) != raw_selected_count:
        records_are_valid = False
    if len(candidates) != raw_candidate_count:
        records_are_valid = False
    semantic_errors = []
    if records_are_valid and candidates:
        semantic_errors = _validate_selector_whole_trace(
            candidates, selected_record, final
        )
        errors.extend(semantic_errors)
    elif complete and not errors:
        errors.append("selector trace could not be decoded as a whole")

    if final is not None:
        for property_name, final_key in (
            (COFACTOR_WIDTH_PROPERTY, "cofactor_width"),
            ("width_upper_bound", "width_upper_bound"),
            ("num_values", "num_values"),
        ):
            if (
                property_name in props
                and props[property_name] != final[final_key]
            ):
                errors.append(
                    "selector final {}={} disagrees with parsed {}={!r}".
                    format(
                        final_key,
                        final[final_key],
                        property_name,
                        props[property_name],
                    )
                )

    # A killed run may contain a valid prefix ending before selected/final. Keep
    # it explicitly incomplete and diagnostic, but leave outcome acceptance to
    # the analyzer, which can distinguish resource exits from completed runs.
    certified = complete and not errors
    if not certified and not errors:
        errors.append("selector trace is incomplete")
    validation_error = None if certified else " | ".join(dict.fromkeys(errors))

    # Only a semantically valid producer prefix may be explained later as a
    # resource interruption. Duplicate/malformed/out-of-order records and
    # finals are parser failures immediately, independent of planner outcome.
    valid_interrupted_prefix = (
        not complete
        and len(final_lines) == 0
        and 1 <= raw_candidate_count <= len(PDB_SELECTOR_SOURCES)
        and raw_selected_count <= 1
        and records_are_valid
        and record_order_valid
        and final_order_valid
        and not semantic_errors
    )
    if not certified and not valid_interrupted_prefix:
        for error in dict.fromkeys(errors):
            tools.add_unexplained_error(props, error)

    props[PDB_SELECTOR_TRACE_COMPLETE_PROPERTY] = complete
    props[PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY] = certified
    props[PDB_SELECTOR_VALIDATION_ERROR_PROPERTY] = validation_error
    props[PDB_SELECTOR_TRACE_SHA256_PROPERTY] = (
        pdb_selector_trace_sha256(candidates, selected_record, final)
        if certified
        else None
    )
    props[PDB_SELECTOR_POOL_SHA256_PROPERTY] = (
        pdb_selector_pool_sha256(candidates) if certified else None
    )
    if candidates:
        props[PDB_SELECTOR_CANDIDATES_PROPERTY] = candidates
    if selected_record is not None:
        props[PDB_SELECTOR_SELECTED_PROPERTY] = selected_record
    if final is not None:
        props[PDB_SELECTOR_FINAL_PROPERTY] = final


def get_pdb_selector_parser() -> Parser:
    parser = Parser()
    parser.add_function(parse_pdb_selector_log, file="run.log")
    return parser


def parse_plan_file(content, props) -> None:
    """Require exactly one canonical final cost footer in an emitted plan."""
    if not content.strip():
        props["plan_file_present"] = False
        props["plan_file_candidate_count"] = 0
        props["plan_file_canonical"] = False
        return
    props["plan_file_present"] = True
    props["plan_file_candidate_count"] = 1
    props["plan_file_canonical"] = False
    costs = _PLAN_COST_RE.findall(content)
    lines = content.splitlines()
    final = _PLAN_COST_RE.fullmatch(lines[-1]) if lines else None
    if len(costs) != 1 or final is None or not content.endswith("\n"):
        tools.add_unexplained_error(
            props,
            "plan parser expected one canonical final cost footer; got {}".
            format(len(costs)),
        )
        return
    props["plan_file_cost"] = int(final.group(1))
    props["plan_file_canonical"] = True


def _is_plan_candidate_name(name: str) -> bool:
    numbered_prefix = "sas_plan."
    return name == "sas_plan" or (
        name.startswith(numbered_prefix)
        and name[len(numbered_prefix):].isdigit()
    )


def _plan_entry_fingerprint(status):
    return (
        status.st_dev,
        status.st_ino,
        status.st_mode,
        status.st_nlink,
        status.st_size,
        status.st_mtime_ns,
        status.st_ctime_ns,
    )


def _read_stable_plan_file(path: Path, initial_status):
    """Read one immutable-identity, single-link regular plan path."""
    expected = _plan_entry_fingerprint(initial_status)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    flags |= getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or _plan_entry_fingerprint(opened) != expected
        ):
            raise OSError("canonical sas_plan identity changed before read")
        with os.fdopen(descriptor, encoding="utf-8") as stream:
            descriptor = -1
            content = stream.read()
            after_read = os.fstat(stream.fileno())
            if _plan_entry_fingerprint(after_read) != expected:
                raise OSError("canonical sas_plan changed while being read")
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    after_path = path.lstat()
    if _plan_entry_fingerprint(after_path) != expected:
        raise OSError("canonical sas_plan path identity changed after read")
    return content


class PlanFileParser(Parser):
    """Certify the exact canonical plan-file inventory and footer."""

    def parse(self, run_dir, props):
        root = Path(run_dir).resolve()
        entries = list(root.iterdir())
        candidates = [
            path for path in entries
            if _is_plan_candidate_name(path.name)
        ]
        props["plan_file_candidate_count"] = len(candidates)
        path = root / "sas_plan"
        canonical_entry = next(
            (candidate for candidate in candidates if candidate.name == "sas_plan"),
            None,
        )
        if canonical_entry is None:
            props["plan_file_present"] = False
            props["plan_file_canonical"] = False
            if candidates:
                tools.add_unexplained_error(
                    props,
                    "plan parser found plan artifacts without canonical sas_plan",
                )
            return
        props["plan_file_present"] = True
        props["plan_file_canonical"] = False
        statuses = {}
        invalid_entries = []
        for candidate in candidates:
            try:
                status = candidate.lstat()
            except OSError:
                invalid_entries.append(candidate.name)
                continue
            statuses[candidate] = status
            if not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                invalid_entries.append(candidate.name)
        if invalid_entries:
            tools.add_unexplained_error(
                props,
                "plan parser requires single-link regular non-symlink "
                "candidates: {}".
                format(", ".join(sorted(invalid_entries))),
            )
        if len(candidates) != 1:
            tools.add_unexplained_error(
                props,
                "plan parser expected exactly one canonical plan artifact; "
                "got {} candidates".format(len(candidates)),
            )
        initial_status = statuses.get(canonical_entry)
        if (
            initial_status is None
            or not stat.S_ISREG(initial_status.st_mode)
            or initial_status.st_nlink != 1
        ):
            return
        try:
            content = _read_stable_plan_file(path, initial_status)
        except (OSError, UnicodeError) as err:
            tools.add_unexplained_error(
                props, "plan parser could not read canonical sas_plan: {}".format(err)
            )
            return
        parse_plan_file(content, props)
        props["plan_file_candidate_count"] = len(candidates)
        if not content.strip():
            tools.add_unexplained_error(
                props, "plan parser found an empty canonical sas_plan"
            )
        if len(candidates) != 1 or invalid_entries:
            props["plan_file_canonical"] = False


def get_plan_file_parser() -> Parser:
    return PlanFileParser()


def parse_run_log_plan_cost(content, props) -> None:
    """Preserve the one canonical plan cost printed by search."""
    matching_lines = [
        line for line in content.splitlines() if "Plan cost:" in line
    ]
    costs = _RUN_LOG_PLAN_COST_RE.findall(content)
    if not matching_lines:
        return
    if len(matching_lines) != 1 or len(costs) != 1:
        tools.add_unexplained_error(
            props,
            "run-log plan-cost parser expected one canonical line; got {}".
            format(len(matching_lines)),
        )
        return
    props["run_log_plan_cost"] = int(costs[0])


def get_run_log_plan_cost_parser() -> Parser:
    parser = Parser()
    parser.add_function(parse_run_log_plan_cost, file="run.log")
    return parser


def _finite_nonnegative_number(value) -> bool:
    if type(value) not in (int, float):
        return False
    try:
        return value >= 0 and math.isfinite(value)
    except (OverflowError, TypeError, ValueError):
        return False


def parse_outcome_reconciliation(content, props) -> None:
    """Certify direct-search raw/effective outcomes against solved evidence.

    A resource-limit code is promoted to a solved effective code only for the
    exact 22->1, 23->2, or 24->3 mapping emitted by the reviewed direct driver.
    The mapped outcome is not certified merely because a plan exists: the
    canonical plan file, search log, and WBH done event must agree on cost and
    the schema-v2 solved summary must be complete and certified.
    """
    props["outcome_reconciliation_protocol"] = OUTCOME_RECONCILIATION_PROTOCOL
    errors = []
    lines = content.splitlines()
    raw_matches = []
    effective_matches = []
    reconciliation_matches = []
    raw_mentions = []
    effective_mentions = []
    reconciliation_mentions = []
    for index, line in enumerate(lines):
        raw = _SEARCH_RAW_EXIT_RE.fullmatch(line)
        effective = _SEARCH_EFFECTIVE_EXIT_RE.fullmatch(line)
        reconciliation = _SEARCH_RECONCILIATION_RE.fullmatch(line)
        if raw:
            raw_matches.append((index, int(raw.group(1))))
        if effective:
            effective_matches.append((index, int(effective.group(1))))
        if reconciliation:
            reconciliation_matches.append(
                (index, int(reconciliation.group(1)), int(reconciliation.group(2)))
            )
        if "search raw exit code:" in line:
            raw_mentions.append(index)
        if "search exit code:" in line:
            effective_mentions.append(index)
        if "search resource-limit exit with complete plan:" in line:
            reconciliation_mentions.append(index)

    planner_exit = props.get("planner_exit_code")
    presearch = planner_exit in _PRESEARCH_EXIT_CODES
    if presearch:
        if raw_mentions or effective_mentions or reconciliation_mentions:
            errors.append("pre-search outcome unexpectedly contains search exit lines")
        if props.get("coverage") != 0:
            errors.append("pre-search outcome must remain unsolved")
        if props.get("plan_file_present") is not False:
            errors.append("pre-search outcome unexpectedly has a plan")
        if props.get("plan_file_candidate_count") != 0:
            errors.append("pre-search outcome must have zero plan candidates")
        if props.get("plan_file_canonical") is not False:
            errors.append("pre-search outcome has canonical plan certification")
    else:
        if len(raw_mentions) != 1 or len(raw_matches) != 1:
            errors.append("expected exactly one canonical search raw exit-code line")
        if len(effective_mentions) != 1 or len(effective_matches) != 1:
            errors.append("expected exactly one canonical search effective exit-code line")

    raw_exit = raw_matches[0][1] if len(raw_matches) == 1 else None
    effective_exit = (
        effective_matches[0][1] if len(effective_matches) == 1 else None
    )
    if raw_exit is not None:
        props["search_raw_exit_code"] = raw_exit
    if effective_exit is not None:
        props["search_effective_exit_code"] = effective_exit

    if not presearch and raw_exit is not None and effective_exit is not None:
        if raw_matches[0][0] >= effective_matches[0][0]:
            errors.append("search raw exit-code line must precede effective line")
        if planner_exit != effective_exit:
            errors.append(
                "planner_exit_code={!r} != search effective exit code {}".
                format(planner_exit, effective_exit)
            )
        mapped_effective = _MAPPED_RESOURCE_EXITS.get(raw_exit)
        mapped = raw_exit != effective_exit
        if mapped:
            if mapped_effective != effective_exit:
                errors.append(
                    "unsupported raw/effective search mapping {}->{}".
                    format(raw_exit, effective_exit)
                )
            if (
                len(reconciliation_mentions) != 1
                or len(reconciliation_matches) != 1
            ):
                errors.append(
                    "mapped outcome needs exactly one canonical reconciliation line"
                )
            else:
                marker_index, marker_raw, marker_effective = (
                    reconciliation_matches[0]
                )
                if (marker_raw, marker_effective) != (raw_exit, effective_exit):
                    errors.append("reconciliation line disagrees with exit-code lines")
                if not (
                    raw_matches[0][0] < marker_index < effective_matches[0][0]
                ):
                    errors.append(
                        "reconciliation line must occur between raw and effective lines"
                    )
        elif reconciliation_mentions:
            errors.append("identity outcome unexpectedly contains reconciliation line")

        solved = effective_exit in (0, 1, 2, 3)
        if solved:
            costs = {
                "planner": props.get("solution_cost"),
                "plan": props.get("plan_file_cost"),
                "run-log": props.get("run_log_plan_cost"),
                "WBH-done": props.get("wbh_done_solution_cost"),
            }
            if props.get("coverage") != 1:
                errors.append("solved effective outcome requires coverage=1")
            if props.get("plan_file_present") is not True:
                errors.append("solved effective outcome requires one canonical plan")
            if props.get("plan_file_candidate_count") != 1:
                errors.append("solved effective outcome requires exactly one plan candidate")
            if props.get("plan_file_canonical") is not True:
                errors.append("solved effective outcome requires canonical plan certification")
            if any(type(value) is not int or value < 0 for value in costs.values()):
                errors.append("solved cost evidence is missing or noncanonical")
            elif len(set(costs.values())) != 1:
                errors.append(
                    "plan/log/WBH done costs disagree: {}".format(
                        ", ".join(
                            "{}={}".format(name, value)
                            for name, value in costs.items()
                        )
                    )
                )
            if props.get("wbh_schema_version") != 2:
                errors.append("solved outcome requires WBH schema v2")
            if props.get("raw_metrics_complete") is not True:
                errors.append("solved outcome requires a complete WBH summary")
            if props.get("piece_metrics_certified") is not True:
                errors.append("solved outcome requires certified WBH metrics")
            if props.get("wbh_summary_solved") is not True:
                errors.append("solved outcome requires summary.solved=true")
            if props.get("wbh_solved_summary_certified") is not True:
                errors.append("solved WBH summary is not certified")
            if props.get("metrics_validation_error") is not None:
                errors.append("solved WBH stream has parser diagnostics")
            if not _finite_nonnegative_number(props.get("planner_time")):
                errors.append("solved outcome requires finite nonnegative planner_time")
        else:
            # Every identity non-success, including an unchanged resource
            # limit, remains an unsolved/censored result with no plan.
            if props.get("coverage") != 0:
                errors.append("identity non-success exit must remain unsolved")
            if props.get("plan_file_present") is not False:
                errors.append("identity non-success exit unexpectedly has a plan")
            if props.get("plan_file_candidate_count") != 0:
                errors.append("identity non-success exit must have zero plan candidates")
            if props.get("plan_file_canonical") is not False:
                errors.append("identity non-success exit has canonical plan certification")
            if any(
                props.get(name) is not None
                for name in (
                    "solution_cost",
                    "plan_file_cost",
                    "run_log_plan_cost",
                    "wbh_done_solution_cost",
                )
            ):
                errors.append("identity non-success exit has solved cost evidence")
            if props.get("wbh_schema_version") == 2:
                raw_complete = props.get("raw_metrics_complete")
                summary_solved = props.get("wbh_summary_solved")
                if props.get("wbh_solved_summary_certified") is not False:
                    errors.append(
                        "unsolved schema-v2 outcome requires exact false solved-"
                        "summary certification"
                    )
                if raw_complete is True:
                    if summary_solved is not False:
                        errors.append(
                            "complete unsolved schema-v2 outcome requires "
                            "summary.solved=false"
                        )
                elif raw_complete is False:
                    if summary_solved is not None:
                        errors.append(
                            "incomplete unsolved schema-v2 outcome requires no "
                            "summary.solved value"
                        )
                else:
                    errors.append(
                        "unsolved schema-v2 outcome requires boolean raw metrics "
                        "completeness"
                    )

        if effective_exit in (1, 2, 3) and (
            _MAPPED_RESOURCE_EXITS.get(raw_exit) != effective_exit
        ):
            errors.append(
                "effective mapped-success code requires exact resource mapping"
            )

    existing_unexplained = props.get("unexplained_errors")
    if existing_unexplained not in (None, []):
        errors.append("earlier parser reported unexplained errors")

    errors = list(dict.fromkeys(errors))
    props["outcome_reconciliation_certified"] = not errors
    if errors:
        props["outcome_reconciliation_error"] = " | ".join(errors)
        tools.add_unexplained_error(
            props,
            "outcome reconciliation failed: " + props[
                "outcome_reconciliation_error"
            ],
        )


def get_outcome_reconciliation_parser() -> Parser:
    parser = Parser()
    parser.add_function(parse_outcome_reconciliation, file="run.log")
    return parser


def _required_lab_version() -> str:
    matches = []
    for raw_line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("lab=="):
            matches.append(line.partition("==")[2])
    if len(matches) != 1 or not matches[0]:
        raise RuntimeError(
            "requirements.txt must contain exactly one exact lab==VERSION pin"
        )
    return matches[0]


REQUIRED_LAB_VERSION = _required_lab_version()
INSTALLED_LAB_VERSION = importlib.metadata.version("lab")


def lab_step_numbers(args):
    """Return Lab's normalized one-based numeric step aliases."""
    return {
        int(arg)
        for arg in args
        if isinstance(arg, str) and arg.isdigit()
    }


def requested_build_or_start(args=None):
    requested = list(sys.argv[1:] if args is None else args)
    tokens = set(requested)
    numbers = lab_step_numbers(requested)
    return bool(tokens & {"build", "start"} or numbers & {1, 2})


def reject_unsafe_combined_steps(args=None):
    """Forbid Lab invocations that could start after a failed build."""
    requested = list(sys.argv[1:] if args is None else args)
    if any(arg in {"-h", "--help"} for arg in requested):
        return
    if any(
        isinstance(arg, str)
        and len(arg) > 2
        and "--all".startswith(arg)
        for arg in requested
    ):
        raise RuntimeError(
            "Arrhenius protocols forbid --all and its argparse abbreviations"
        )
    tokens = set(requested)
    numbers = lab_step_numbers(requested)
    wants_build = "build" in tokens or 1 in numbers
    wants_start = "start" in tokens or 2 in numbers
    if wants_build and wants_start:
        raise RuntimeError(
            "Arrhenius protocols require build and start in separate invocations"
        )


def experiment_output_paths(experiment_path):
    """Return the exact Lab grid, submission, and evaluation paths."""
    grid_path = Path(experiment_path)
    return (
        grid_path,
        grid_path.parent / "{}-grid-steps".format(grid_path.name),
        Path(str(grid_path) + "-eval"),
    )


def require_fresh_experiment_build(experiment_path):
    """Refuse Lab's destructive rebuild path, including dangling symlinks."""
    for path in experiment_output_paths(experiment_path):
        if path.exists() or path.is_symlink():
            raise RuntimeError(
                "refusing build because an experiment output path already "
                "exists: {}".format(path)
            )


def strip_copied_python_bytecode(experiment_path):
    """Remove only generated Python bytecode from one newly built Lab grid.

    Revision caches can contain timestamp-valid bytecode generated while the
    cache was inspected.  Lab copies it into the experiment grid, where it can
    take precedence over the source files attested before submission.  This
    post-build normalization is deliberately narrow: it operates on exactly
    one regular ``code-*`` directory, removes only regular ``.pyc``/``.pyo``
    files, and removes ``__pycache__`` directories only after they are empty.
    """
    grid_path = Path(experiment_path)
    if grid_path.is_symlink() or not grid_path.is_dir():
        raise RuntimeError(
            "bytecode cleanup requires a regular built experiment grid: {}".
            format(grid_path)
        )
    code_entries = sorted(
        path for path in grid_path.iterdir() if path.name.startswith("code-")
    )
    if len(code_entries) != 1:
        raise RuntimeError(
            "bytecode cleanup requires exactly one code-* directory; got {}".
            format([path.name for path in code_entries])
        )
    code_dir = code_entries[0]
    if code_dir.is_symlink() or not code_dir.is_dir():
        raise RuntimeError(
            "bytecode cleanup requires a regular code directory: {}".format(
                code_dir
            )
        )

    bytecode_files = []
    cache_directories = []
    try:
        entries = list(code_dir.rglob("*"))
    except OSError as err:
        raise RuntimeError(
            "cannot enumerate copied runtime tree {}: {}".format(code_dir, err)
        ) from err
    for path in entries:
        if path.name == "__pycache__":
            if path.is_symlink() or not path.is_dir():
                raise RuntimeError(
                    "copied __pycache__ entry is not a regular directory: {}".
                    format(path)
                )
            cache_directories.append(path)
        if path.suffix.lower() in {".pyc", ".pyo"}:
            if path.is_symlink() or not path.is_file():
                raise RuntimeError(
                    "copied bytecode entry is not a regular file: {}".format(
                        path
                    )
                )
            bytecode_files.append(path)

    bytecode_set = set(bytecode_files)
    cache_set = set(cache_directories)
    for path in cache_directories:
        unexpected = sorted(
            child.name
            for child in path.iterdir()
            if child not in bytecode_set and child not in cache_set
        )
        if unexpected:
            raise RuntimeError(
                "refusing to clean copied __pycache__ directory {} with "
                "unexpected entries: {}".format(path, unexpected)
            )

    for path in bytecode_files:
        path.unlink()
    for path in sorted(
        cache_directories, key=lambda item: len(item.parts), reverse=True
    ):
        remaining = list(path.iterdir())
        if remaining:
            raise RuntimeError(
                "refusing to remove nonempty copied __pycache__ directory {}: "
                "{}".format(path, sorted(item.name for item in remaining))
            )
        path.rmdir()
    return {
        "code_directory": str(code_dir),
        "removed_bytecode_files": len(bytecode_files),
        "removed_cache_directories": len(cache_directories),
    }


def reject_unattested_python_runtime_artifacts(code_dir):
    """Reject alternate Python code paths in a copied planner tree."""
    code_dir = Path(code_dir)
    if code_dir.is_symlink() or not code_dir.is_dir():
        raise RuntimeError(
            "copied runtime tree must be a regular directory: {}".format(
                code_dir
            )
        )
    try:
        entries = list(code_dir.rglob("*"))
    except OSError as err:
        raise RuntimeError(
            "cannot enumerate copied runtime tree {}: {}".format(code_dir, err)
        ) from err
    for path in entries:
        relative = path.relative_to(code_dir).as_posix()
        if path.is_symlink():
            raise RuntimeError(
                "copied runtime tree contains a symlink: {}".format(relative)
            )
        if path.name == "__pycache__":
            raise RuntimeError(
                "copied runtime tree contains __pycache__: {}".format(relative)
            )
        lower_name = path.name.lower()
        if path.is_file() and (
            path.suffix.lower() in {".pyc", ".pyo"}
            or lower_name.endswith((".so", ".pyd", ".dylib"))
        ):
            raise RuntimeError(
                "copied runtime tree contains unattested importable code: {}".
                format(relative)
            )
        if not path.is_file() and not path.is_dir():
            raise RuntimeError(
                "copied runtime tree contains a special filesystem entry: {}".
                format(relative)
            )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_materialized_pddl(
    path: Path,
    expected_sha256: str,
    label: str,
    source: Path | None = None,
) -> int:
    """Certify one independent, read-only PDDL input copy."""
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as err:
        raise RuntimeError(
            "cannot stat {} {}: {}".format(label, path, err)
        ) from err
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise RuntimeError(
            "{} must be a regular non-symlink materialized file: {}".format(
                label, path
            )
        )
    if info.st_nlink != 1:
        raise RuntimeError("{} must not be a hardlink: {}".format(label, path))
    if info.st_mode & 0o222:
        raise RuntimeError("{} must be read-only: {}".format(label, path))
    if source is not None:
        source = Path(source)
        try:
            if path.samefile(source):
                raise RuntimeError(
                    "{} aliases its benchmark source: {}".format(label, path)
                )
        except OSError as err:
            raise RuntimeError(
                "cannot compare {} with benchmark source: {}".format(
                    label, err
                )
            ) from err
    actual_sha256 = _sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise RuntimeError(
            "{} SHA-256 changed: expected {}, got {} ({})".format(
                label, expected_sha256, actual_sha256, path
            )
        )
    return info.st_size


def materialize_pddl_link(
    link: Path,
    source: Path,
    expected_sha256: str,
    label: str,
) -> int:
    """Atomically replace one exact Lab PDDL link with an independent copy."""
    link = Path(link)
    source = Path(source).resolve()
    if (
        not link.is_symlink()
        or not link.exists()
        or link.resolve() != source
        or not link.samefile(source)
    ):
        raise RuntimeError(
            "{} must begin as the exact live Lab source symlink: {}".format(
                label, link
            )
        )
    try:
        source_info = source.lstat()
    except OSError as err:
        raise RuntimeError(
            "cannot stat benchmark PDDL source {}: {}".format(source, err)
        ) from err
    if source.is_symlink() or not stat.S_ISREG(source_info.st_mode):
        raise RuntimeError(
            "benchmark PDDL source must be a regular non-symlink file: {}".
            format(source)
        )
    if _sha256_file(source) != expected_sha256:
        raise RuntimeError("{} benchmark source digest changed".format(label))

    descriptor, temporary_raw = tempfile.mkstemp(
        prefix=".{}-materializing-".format(link.name), dir=str(link.parent)
    )
    temporary = Path(temporary_raw)
    try:
        digest = hashlib.sha256()
        destination_stream = os.fdopen(descriptor, "wb")
        descriptor = -1
        with source.open("rb") as source_stream, destination_stream:
            while True:
                chunk = source_stream.read(1024 * 1024)
                if not chunk:
                    break
                destination_stream.write(chunk)
                digest.update(chunk)
            destination_stream.flush()
            os.fsync(destination_stream.fileno())
        if digest.hexdigest() != expected_sha256:
            raise RuntimeError("{} copied digest changed".format(label))
        temporary.chmod(0o444)
        require_materialized_pddl(
            temporary, expected_sha256, "staged " + label, source
        )
        os.replace(temporary, link)
        return require_materialized_pddl(
            link, expected_sha256, label, source
        )
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def _git_output(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def require_revision_ancestor_of_head(revision: str) -> str:
    """Return protocol HEAD after attesting a full, existing ancestor commit."""
    if not isinstance(revision, str) or not re.fullmatch(
        r"[0-9a-f]{40}", revision
    ):
        raise RuntimeError("planner revision must be a full 40-digit commit")
    head = _git_output("rev-parse", "HEAD")
    try:
        _git_output("cat-file", "-e", revision + "^{commit}")
    except subprocess.CalledProcessError as err:
        raise RuntimeError(
            "pinned planner revision does not name an existing commit: {}".
            format(revision)
        ) from err
    try:
        _git_output("merge-base", "--is-ancestor", revision, head)
    except subprocess.CalledProcessError as err:
        raise RuntimeError(
            "pinned planner revision {} is not an ancestor of protocol HEAD {}".
            format(revision, head)
        ) from err
    return head


def require_clean_committed_revision(
    revision: str, protocol_files=()
) -> None:
    """Require a clean protocol HEAD descending from the pinned planner."""
    require_revision_ancestor_of_head(revision)
    dirty = _git_output("status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise RuntimeError(
            "prospective build/start requires a clean tracked worktree; got:\n{}".
            format(dirty)
        )
    required_files = [Path(__file__).resolve()]
    required_files.extend(Path(path).resolve() for path in protocol_files)
    for path in required_files:
        try:
            relative = path.relative_to(REPO).as_posix()
        except ValueError as err:
            raise RuntimeError(
                "protocol file is outside the planner repository: {}".format(
                    path
                )
            ) from err
        try:
            tracked = _git_output(
                "ls-files", "--error-unmatch", "--", relative
            )
        except subprocess.CalledProcessError as err:
            raise RuntimeError(
                "protocol file must be committed before build/start: {}".
                format(relative)
            ) from err
        if tracked != relative:
            raise RuntimeError(
                "could not attest committed protocol file: {}".format(relative)
            )


def require_pinned_lab_version() -> None:
    if INSTALLED_LAB_VERSION != REQUIRED_LAB_VERSION:
        raise RuntimeError(
            "build/start requires Lab {} from requirements.txt; installed is {}".
            format(REQUIRED_LAB_VERSION, INSTALLED_LAB_VERSION)
        )


def cached_revision(revision: str) -> CachedFastDownwardRevision:
    """Describe, but do not build, the exact prospective Lab cache."""
    return CachedFastDownwardRevision(
        str(REVISION_CACHE), str(REPO), revision, list(BUILD_OPTIONS)
    )


def revision_cache_paths(revision: str):
    cache = cached_revision(revision)
    return (
        cache,
        cache.path / "build_successful",
        cache.path / "builds" / CACHE_BUILD_NAME / "bin" / "downward",
    )


def inspect_revision_cache(revision: str):
    """Return cache identity and hashes without modifying the cache."""
    cache, sentinel, binary = revision_cache_paths(revision)
    return {
        "name": cache.name,
        "path": str(cache.path),
        "sentinel": str(sentinel),
        "binary": str(binary),
        "sentinel_sha256": _sha256_file(sentinel) if sentinel.is_file() else None,
        "binary_sha256": _sha256_file(binary) if binary.is_file() else None,
        "binary_executable": binary.is_file() and os.access(binary, os.X_OK),
    }


def require_revision_cache(
    revision: str, expected_binary_sha256: str | None
) -> dict:
    """Require the prebuilt, stripped ``release_no_lp`` cache and exact hash."""
    if not isinstance(expected_binary_sha256, str) or not _SHA256_RE.fullmatch(
        expected_binary_sha256
    ):
        raise RuntimeError(
            "set CACHE_BINARY_SHA256 to the reviewed cached-binary SHA-256 "
            "before build/start"
        )
    info = inspect_revision_cache(revision)
    if info["sentinel_sha256"] != CACHE_SENTINEL_SHA256:
        raise RuntimeError(
            "missing or changed revision-cache sentinel: {}".format(
                info["sentinel"]
            )
        )
    if not info["binary_executable"]:
        raise RuntimeError(
            "missing or non-executable cached planner: {}".format(info["binary"])
        )
    if info["binary_sha256"] != expected_binary_sha256:
        raise RuntimeError(
            "cached planner SHA-256 mismatch: expected {}, got {}".format(
                expected_binary_sha256, info["binary_sha256"]
            )
        )
    return info


def require_launch_prerequisites(
    revision: str,
    expected_binary_sha256: str | None,
    args=None,
    protocol_files=(),
) -> dict | None:
    """Apply all launch-only gates without affecting read-only steps."""
    if not requested_build_or_start(args):
        return None
    require_clean_committed_revision(revision, protocol_files)
    require_pinned_lab_version()
    return require_revision_cache(revision, expected_binary_sha256)


def _parse_slurm_time(value: str) -> int:
    match = re.fullmatch(r"(?:(\d+)-)?(\d+):(\d{2}):(\d{2})", value)
    if not match:
        raise RuntimeError("invalid Slurm wall time {!r}".format(value))
    days, hours, minutes, seconds = (
        int(field or 0) for field in match.groups()
    )
    if minutes >= 60 or seconds >= 60:
        raise RuntimeError("invalid Slurm wall time {!r}".format(value))
    return (((days * 24) + hours) * 60 + minutes) * 60 + seconds


def run_layout(num_runs: int):
    if type(num_runs) is not int or num_runs <= 0:
        raise RuntimeError("num_runs must be a positive integer")
    runs_per_array_task = math.ceil(num_runs / MAX_ARRAY_TASKS)
    array_tasks = math.ceil(num_runs / runs_per_array_task)
    return array_tasks, runs_per_array_task


def validate_run_layout(
    num_runs: int,
    *,
    planner_time_limit_seconds: int = TIME_LIMIT_SECONDS,
    scheduler_time_limit: str = SCHEDULER_TIME_LIMIT,
    require_one_run_per_array_task: bool = False,
) -> dict:
    array_tasks, runs_per_array_task = run_layout(num_runs)
    if array_tasks > MAX_ARRAY_TASKS:
        raise RuntimeError("Arrhenius array exceeds MAX_TASKS=1000")
    if require_one_run_per_array_task and runs_per_array_task != 1:
        raise RuntimeError(
            "pilot must contain at most 1000 runs so every array element "
            "executes exactly one run"
        )
    scheduler_seconds = _parse_slurm_time(scheduler_time_limit)
    required_seconds = runs_per_array_task * (
        planner_time_limit_seconds + SCHEDULER_WRAPPER_ALLOWANCE_SECONDS
    )
    if scheduler_seconds < required_seconds:
        raise RuntimeError(
            "scheduler envelope {} is too short for {} run(s) per array task; "
            "need at least {} seconds".format(
                scheduler_time_limit, runs_per_array_task, required_seconds
            )
        )
    return {
        "raw_runs": num_runs,
        "array_tasks": array_tasks,
        "runs_per_array_task": runs_per_array_task,
        "scheduler_time_limit_seconds": scheduler_seconds,
    }


class _SeededTaskOrderMixin:
    def __init__(self, *args, task_order_seed=TASK_ORDER_SEED, **kwargs):
        self.task_order_seed = task_order_seed
        kwargs["randomize_task_order"] = False
        super().__init__(*args, **kwargs)

    def _get_task_order(self, num_tasks):
        task_order = list(range(1, num_tasks + 1))

        def key(task_id):
            payload = "{}\0{}\0{}".format(
                self.task_order_seed, num_tasks, task_id
            )
            return hashlib.sha256(payload.encode("utf-8")).digest(), task_id

        task_order.sort(key=key)
        return task_order


class SeededArrheniusEnvironment(_SeededTaskOrderMixin, SlurmEnvironment):
    """Arrhenius environment with deterministic grouping and sealed headers."""

    DEFAULT_PARTITION = SCHEDULER_PARTITION
    DEFAULT_QOS = SCHEDULER_QOS
    DEFAULT_TIME_LIMIT_PER_TASK = SCHEDULER_TIME_LIMIT
    DEFAULT_MEMORY_PER_CPU = SCHEDULER_MEMORY_PER_CPU
    MAX_TASKS = MAX_ARRAY_TASKS

    @classmethod
    def is_present(cls):
        node = platform.node()
        return bool(
            re.fullmatch(
                r"arrhenius\d+\.hpc\.arrhenius\.naiss\.se|n\d+", node
            )
        )

    def _get_job_header(self, step, is_last):
        header = super()._get_job_header(step, is_last)
        if not header.startswith("#! /bin/bash -l\n"):
            raise RuntimeError("Lab Slurm shebang changed; review Arrhenius header")
        header = header.replace("#! /bin/bash -l", "#! /bin/bash", 1)
        if not is_run_step(step):
            return header

        num_tasks = self._get_num_tasks(step)
        unthrottled = "{}1-{}".format(_SLURM_ARRAY_DIRECTIVE, num_tasks)
        throttled = "{}%{}".format(unthrottled, ARRAY_TASK_THROTTLE)
        lines = header.splitlines()
        directives = [
            line for line in lines if line.startswith(_SLURM_ARRAY_DIRECTIVE)
        ]
        if directives != [unthrottled]:
            raise RuntimeError(
                "Lab array header changed: expected {!r}, got {!r}".format(
                    unthrottled, directives
                )
            )
        lines[lines.index(unthrottled)] = throttled
        return "\n".join(lines) + ("\n" if header.endswith("\n") else "")

    def _get_run_job_body(self, run_step):
        body = super()._get_run_job_body(run_step)
        if body.count(_RANDOM_RUN_LOOP) != 1:
            raise RuntimeError(
                "Lab run-body shuffle changed; review deterministic grouping"
            )
        return body.replace(_RANDOM_RUN_LOOP, _DETERMINISTIC_RUN_LOOP, 1)

    def _get_job(self, step, is_last):
        job = super()._get_job(step, is_last)
        if is_run_step(step):
            assert_exact_run_header(self, job, len(self.exp.runs))
            if _RANDOM_RUN_LOOP in job or job.count(_DETERMINISTIC_RUN_LOOP) != 1:
                raise RuntimeError("run job does not use deterministic inner order")
        return job


def get_environment() -> SeededArrheniusEnvironment:
    if SCHEDULER_PARTITION != "cpu" or SCHEDULER_QOS != "normal":
        raise RuntimeError("Arrhenius protocol requires cpu/normal")
    if not re.fullmatch(r"[a-z0-9-]+-cpu", SCHEDULER_ACCOUNT):
        raise RuntimeError(
            "Arrhenius account must include its -cpu suffix: {}".format(
                SCHEDULER_ACCOUNT
            )
        )
    environment = SeededArrheniusEnvironment(
        email=None,
        partition=SCHEDULER_PARTITION,
        qos=SCHEDULER_QOS,
        time_limit_per_task=SCHEDULER_TIME_LIMIT,
        memory_per_cpu=SCHEDULER_MEMORY_PER_CPU,
        cpus_per_task=SCHEDULER_CPUS_PER_TASK,
        extra_options="#SBATCH --account={}".format(SCHEDULER_ACCOUNT),
    )
    environment.protocol_account = SCHEDULER_ACCOUNT
    return environment


def _require_exact_directive(lines, expected):
    prefix = expected.partition("=")[0] + "="
    matches = [line for line in lines if line.startswith(prefix)]
    if matches != [expected]:
        raise RuntimeError(
            "expected exactly one scheduler directive {!r}; got {!r}".format(
                expected, matches
            )
        )


def assert_exact_run_header(environment, job: str, num_runs: int) -> dict:
    """Assert every research-relevant Arrhenius header field exactly."""
    layout = validate_run_layout(
        num_runs,
        scheduler_time_limit=environment.time_limit_per_task,
    )
    lines = job.splitlines()
    if not lines or lines[0] != "#! /bin/bash":
        raise RuntimeError("Arrhenius jobs must use non-login bash")
    if any(line == "#! /bin/bash -l" for line in lines):
        raise RuntimeError("Arrhenius job retained a login-shell shebang")

    expected = [
        "#SBATCH --partition={}".format(SCHEDULER_PARTITION),
        "#SBATCH --qos={}".format(SCHEDULER_QOS),
        "#SBATCH --time={}".format(environment.time_limit_per_task),
        "#SBATCH --mem-per-cpu={}".format(environment.memory_per_cpu),
        "#SBATCH --cpus-per-task={}".format(environment.cpus_per_task),
        "#SBATCH --array=1-{}%{}".format(
            layout["array_tasks"], ARRAY_TASK_THROTTLE
        ),
        "#SBATCH --account={}".format(environment.protocol_account),
    ]
    for directive in expected:
        _require_exact_directive(lines, directive)
    array_directives = [
        line for line in lines if line.startswith(_SLURM_ARRAY_DIRECTIVE)
    ]
    if array_directives != [expected[5]]:
        raise RuntimeError(
            "expected one exact throttled array directive; got {!r}".format(
                array_directives
            )
        )
    return layout


def make_in_memory_run_job(
    num_runs: int, scheduler_time_limit=SCHEDULER_TIME_LIMIT
):
    class FakeStep:
        name = "start"
        _funcname = "start_runs"

    class FakeExperiment:
        name = "arrhenius-header-self-test"
        path = "/tmp/arrhenius-header-self-test"

        def __init__(self):
            self.runs = [None] * num_runs
            self.steps = [FakeStep()]

    environment = SeededArrheniusEnvironment(
        email=None,
        partition=SCHEDULER_PARTITION,
        qos=SCHEDULER_QOS,
        time_limit_per_task=scheduler_time_limit,
        memory_per_cpu=SCHEDULER_MEMORY_PER_CPU,
        cpus_per_task=SCHEDULER_CPUS_PER_TASK,
        extra_options="#SBATCH --account={}".format(SCHEDULER_ACCOUNT),
    )
    environment.protocol_account = SCHEDULER_ACCOUNT
    environment.exp = FakeExperiment()
    # Lab >=8.0 resolves shared log paths through this attribute even for
    # in-memory headers.  No directory is created.
    environment.job_dir = Path("/tmp/arrhenius-header-self-test-grid-steps")
    step = environment.exp.steps[0]
    return environment, environment._get_job(step, True)


class ProtocolFastDownwardExperiment(FastDownwardExperiment):
    """Fast Downward experiment that copies protocol metadata into every run."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.protocol_run_properties = {}

    def add_algorithm(self, *args, **kwargs):
        """Add an algorithm after removing only Lab's unavailable VAL flag."""
        super().add_algorithm(*args, **kwargs)
        name = args[0] if args else kwargs.get("name")
        algorithm = self._algorithms[name]
        prefix = algorithm.driver_options[:len(LAB_DEFAULT_DRIVER_PREFIX)]
        if prefix != LAB_DEFAULT_DRIVER_PREFIX:
            raise RuntimeError(
                "Lab default driver options changed; review VAL handling: {}".
                format(prefix)
            )
        algorithm.driver_options = algorithm.driver_options[1:]

    def _remove_experiment_dir(self):
        """Replace Lab's prompt-and-delete rebuild path with a hard gate."""
        require_fresh_experiment_build(self.path)

    def _add_runs(self):
        first_new_run = len(self.runs)
        super()._add_runs()
        for run in self.runs[first_new_run:]:
            for name, value in self.protocol_run_properties.items():
                run.set_property(name, value)


def common_protocol_metadata(
    revision: str,
    cache_binary_sha256: str | None,
    num_runs: int,
) -> dict:
    layout = validate_run_layout(num_runs)
    protocol_revision = require_revision_ancestor_of_head(revision)
    cache = cached_revision(revision)
    return {
        "planner_revision": revision,
        "protocol_revision": protocol_revision,
        "planner_revision_is_protocol_ancestor": True,
        "planner_build_options": list(BUILD_OPTIONS),
        "planner_build_config": CACHE_BUILD_NAME,
        "planner_binary_sha256": cache_binary_sha256,
        "planner_revision_cache_name": cache.name,
        "external_plan_validation": False,
        "plan_validation_protocol": PLAN_VALIDATION_PROTOCOL,
        "plan_file_parser_protocol": PLAN_FILE_PARSER_PROTOCOL,
        "outcome_reconciliation_protocol": OUTCOME_RECONCILIATION_PROTOCOL,
        "cofactor_width_property": COFACTOR_WIDTH_PROPERTY,
        "cofactor_width_parser_protocol": COFACTOR_WIDTH_PARSER_PROTOCOL,
        "metrics_validation_protocol": wbh_parser.METRICS_VALIDATION_PROTOCOL,
        "python_version": platform.python_version(),
        "lab_version": INSTALLED_LAB_VERSION,
        "required_lab_version": REQUIRED_LAB_VERSION,
        "task_order_seed": TASK_ORDER_SEED,
        "task_order_method": TASK_ORDER_METHOD,
        "driver_time_limit": TIME_LIMIT,
        "driver_memory_limit": MEMORY_LIMIT,
        "scheduler_environment": "arrhenius-slurm",
        "scheduler_cluster": SCHEDULER_CLUSTER,
        "scheduler_cpu_model": SCHEDULER_CPU_MODEL,
        "scheduler_partition": SCHEDULER_PARTITION,
        "scheduler_qos": SCHEDULER_QOS,
        "scheduler_account": SCHEDULER_ACCOUNT,
        "scheduler_time_limit_per_task": SCHEDULER_TIME_LIMIT,
        "scheduler_memory_per_cpu": SCHEDULER_MEMORY_PER_CPU,
        "scheduler_cpus_per_task": SCHEDULER_CPUS_PER_TASK,
        "scheduler_array_task_throttle": ARRAY_TASK_THROTTLE,
        "scheduler_max_array_tasks": MAX_ARRAY_TASKS,
        "scheduler_array_tasks": layout["array_tasks"],
        "scheduler_runs_per_array_task": layout["runs_per_array_task"],
        "declared_run_count": num_runs,
        "repetitions": 1,
    }


def validate_common_protocol_metadata(metadata: dict) -> None:
    """Require a complete, internally consistent common protocol record."""
    if not isinstance(metadata, dict):
        raise TypeError("protocol metadata must be a dictionary")
    required_identity = (
        "planner_revision",
        "planner_binary_sha256",
        "declared_run_count",
    )
    missing_identity = [
        name for name in required_identity if name not in metadata
    ]
    if missing_identity:
        raise RuntimeError(
            "protocol metadata is missing: {}".format(
                ", ".join(missing_identity)
            )
        )
    expected = common_protocol_metadata(
        metadata["planner_revision"],
        metadata["planner_binary_sha256"],
        metadata["declared_run_count"],
    )
    mismatches = {
        name: (metadata.get(name), value)
        for name, value in expected.items()
        if metadata.get(name) != value
    }
    if mismatches:
        details = "; ".join(
            "{}={!r}, expected {!r}".format(name, actual, wanted)
            for name, (actual, wanted) in sorted(mismatches.items())
        )
        raise RuntimeError("common protocol metadata mismatch: " + details)


def new_experiment(protocol_metadata: dict) -> ProtocolFastDownwardExperiment:
    validate_common_protocol_metadata(protocol_metadata)
    environment = get_environment()
    experiment = ProtocolFastDownwardExperiment(
        environment=environment, revision_cache=str(REVISION_CACHE)
    )
    experiment.protocol_run_properties.update(protocol_metadata)
    experiment.add_parser(experiment.EXITCODE_PARSER)
    experiment.add_parser(experiment.TRANSLATOR_PARSER)
    experiment.add_parser(experiment.SINGLE_SEARCH_PARSER)
    experiment.add_parser(experiment.PLANNER_PARSER)
    experiment.add_parser(wbh_parser.get_parser())
    experiment.add_parser(get_cofactor_width_parser())
    experiment.add_parser(get_pdb_selector_parser())
    experiment.add_parser(get_run_log_plan_cost_parser())
    experiment.add_parser(get_plan_file_parser())
    experiment.add_parser(get_outcome_reconciliation_parser())
    return experiment


def set_protocol_run_properties(experiment, properties):
    if not isinstance(experiment, ProtocolFastDownwardExperiment):
        raise TypeError("expected ProtocolFastDownwardExperiment")
    overlap = set(experiment.protocol_run_properties) & set(properties)
    if overlap:
        raise RuntimeError(
            "protocol properties already set: {}".format(
                ", ".join(sorted(overlap))
            )
        )
    experiment.protocol_run_properties.update(properties)


def search_config(search_expr: str) -> str:
    if not search_expr.endswith(")") or "(" not in search_expr:
        raise ValueError("expected a plugin expression ending in ')'")
    open_paren = search_expr.index("(")
    inner = search_expr[open_paren + 1 : -1].strip()
    separator = "," if inner else ""
    return '{}{}{}wbh_log="{}")'.format(
        search_expr[: open_paren + 1], inner, separator, WBH_LOG
    )


def add_algorithm(
    experiment, name: str, search_expr: str, *, revision: str
) -> None:
    require_revision_ancestor_of_head(revision)
    experiment.add_algorithm(
        name,
        str(REPO),
        revision,
        ["--search", search_config(search_expr)],
        build_options=list(BUILD_OPTIONS),
        driver_options=[
            "--build",
            CACHE_BUILD_NAME,
            "--overall-time-limit",
            TIME_LIMIT,
            "--overall-memory-limit",
            MEMORY_LIMIT,
        ],
    )


def add_suite(experiment, benchmarks: Path, suite) -> None:
    experiment.add_suite(str(benchmarks), suite)


ATTRIBUTES = [
    "coverage", "solution_cost", "planner_time", "total_time", "effort",
    "plan_file_present", "plan_file_candidate_count", "plan_file_canonical",
    "plan_file_cost", "run_log_plan_cost",
    "search_raw_exit_code", "search_effective_exit_code",
    "outcome_reconciliation_protocol", "outcome_reconciliation_certified",
    "outcome_reconciliation_error",
    "cofactor_width",
    "pdb_final_format", "pdb_pattern_size", "pdb_final_num_values",
    "pdb_final_cofactor_width", "pdb_final_width_upper_bound",
    "pdb_selected_source", "pdb_abstract_states",
    "pdb_cofactor_width_budget", PDB_SELECTOR_CANDIDATES_PROPERTY,
    PDB_SELECTOR_SELECTED_PROPERTY, PDB_SELECTOR_FINAL_PROPERTY,
    PDB_SELECTOR_TRACE_COMPLETE_PROPERTY,
    PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY,
    PDB_SELECTOR_VALIDATION_ERROR_PROPERTY,
    PDB_SELECTOR_TRACE_SHA256_PROPERTY,
    PDB_SELECTOR_POOL_SHA256_PROPERTY,
    "peak_bdd_nodes", "expanded_bdd_nodes", "expanded_states",
    "expanded_bdd_pieces", "attempted_bdd_nodes", "attempted_states",
    "attempted_bdd_pieces", "bucket_expansions", "bucket_expansion_attempts",
    "image_events", "bucket_images", "image_source_buckets",
    "image_source_pieces", "image_calls_attempted", "image_calls_completed",
    "batched_images", "image_time", "raw_metrics_complete",
    "wbh_summary_solved", "wbh_done_solution_cost",
    "wbh_solved_summary_certified",
    "wbh_log_nonempty", "wbh_schema_version", "node_count_convention",
    "image_count_convention",
    "expansion_count_convention", "piece_metrics_certified",
    "metrics_validation_protocol", "metrics_validation_error",
    "expanded_buckets_single_piece", "partition_ratio_max",
    "partition_ratio_geomean", "width_upper_bound", "num_values",
    "num_terminals", "add_nodes", "construction_time", "heuristic_kind",
    "heuristic_size_bound", "value_cap", "construction_completed",
    "num_pruned_deadends", "pruned_deadend_states",
    "pruned_deadend_bdd_nodes", "error",
]


def add_standard_steps(experiment, extra_attributes=()):
    experiment.add_step("build", experiment.build)
    experiment.add_step("start", experiment.start_runs)
    experiment.add_step("parse", experiment.parse)
    experiment.add_fetcher(name="fetch")
    attributes = list(dict.fromkeys(
        ATTRIBUTES
        + list(experiment.protocol_run_properties)
        + list(extra_attributes)
    ))
    experiment.add_report(
        AbsoluteReport(attributes=attributes),
        name="report",
        outfile="report.html",
    )


def self_test_scheduler_headers():
    expected_layouts = {
        1: (1, 1),
        700: (700, 1),
        1000: (1000, 1),
        1001: (501, 2),
        1050: (525, 2),
        1404: (702, 2),
    }
    for num_runs, expected in expected_layouts.items():
        wall = "00:20:00" if expected[1] == 2 else "00:10:00"
        environment, job = make_in_memory_run_job(
            num_runs, scheduler_time_limit=wall
        )
        layout = assert_exact_run_header(environment, job, num_runs)
        actual = (layout["array_tasks"], layout["runs_per_array_task"])
        if actual != expected:
            raise AssertionError(
                "{} runs produced layout {}, expected {}".format(
                    num_runs, actual, expected
                )
            )
        if _RANDOM_RUN_LOOP in job or job.count(_DETERMINISTIC_RUN_LOOP) != 1:
            raise AssertionError("inner run order is not deterministic")
        first_order = environment._get_task_order(layout["array_tasks"])
        second_order = environment._get_task_order(layout["array_tasks"])
        if first_order != second_order or sorted(first_order) != list(
            range(1, layout["array_tasks"] + 1)
        ):
            raise AssertionError("seeded array-task order is not reproducible")

    conflicting_header = job.replace(
        "#SBATCH --partition=cpu",
        "#SBATCH --partition=cpu\n#SBATCH --partition=gpu",
        1,
    )
    try:
        assert_exact_run_header(environment, conflicting_header, num_runs)
    except RuntimeError:
        pass
    else:
        raise AssertionError("conflicting scheduler directive was accepted")

    try:
        validate_run_layout(
            1001,
            scheduler_time_limit="00:10:00",
            require_one_run_per_array_task=True,
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("one-run-per-array pilot gate accepted 1001 runs")

    for unsafe in (
        ["build", "start"], ["1", "2"], ["build", "2"], ["--a"],
        ["--al"], ["--all"],
    ):
        try:
            reject_unsafe_combined_steps(unsafe)
        except RuntimeError:
            pass
        else:
            raise AssertionError("unsafe Lab steps were accepted: {!r}".format(unsafe))

    cache = cached_revision(REV)
    if not cache.name.endswith("_61a748e5"):
        raise AssertionError(
            "release_no_lp cache identity changed: {}".format(cache.name)
        )
    if REQUIRED_LAB_VERSION != "8.0":
        raise AssertionError(
            "review requirements-version test for lab=={}".format(
                REQUIRED_LAB_VERSION
            )
        )
    if not INSTALLED_LAB_VERSION:
        raise AssertionError("installed Lab version is unavailable")
    try:
        require_pinned_lab_version()
    except RuntimeError:
        if INSTALLED_LAB_VERSION == REQUIRED_LAB_VERSION:
            raise AssertionError("matching Lab version was rejected")
    else:
        if INSTALLED_LAB_VERSION != REQUIRED_LAB_VERSION:
            raise AssertionError("mismatched Lab version was accepted")
    try:
        require_revision_cache(REV, None)
    except RuntimeError:
        pass
    else:
        raise AssertionError("missing cache-binary hash pin was accepted")
    if require_launch_prerequisites(REV, None, args=["parse"]) is not None:
        raise AssertionError("read-only parse unexpectedly required the cache")

    class FakeExperiment:
        def add_algorithm(self, *args, **kwargs):
            self.call = (args, kwargs)

    fake_experiment = FakeExperiment()
    add_algorithm(
        fake_experiment, "blind", "sym_fw()", revision=REV
    )
    args, kwargs = fake_experiment.call
    if args[2] != REV or kwargs.get("build_options") != BUILD_OPTIONS:
        raise AssertionError("explicit algorithm revision/build was not retained")
    if kwargs.get("driver_options", [])[:2] != [
        "--build", CACHE_BUILD_NAME
    ]:
        raise AssertionError("cached build was not selected in driver options")
    if LAB_DEFAULT_DRIVER_PREFIX != [
        "--validate", "--overall-time-limit", "30m",
        "--overall-memory-limit", "3584M",
    ]:
        raise AssertionError("Lab default driver prefix contract changed")

    print(
        "Arrhenius scheduler self-tests: PASS "
        "(layouts 1/700/1000/1001/1050/1404; throttle=5)"
    )
    print(
        "exact run headers: cpu, normal, one CPU, 9G, non-login bash, "
        "account {}, deterministic grouping".format(SCHEDULER_ACCOUNT)
    )
    print(
        "Lab compatibility: installed {}; requirements pin {} "
        "(build/start require an exact match)".format(
            INSTALLED_LAB_VERSION, REQUIRED_LAB_VERSION
        )
    )


def self_test_cofactor_width_parser():
    examples = {
        (
            "[t=1.234567s, 45678 KB] wbh linear M&S heuristic: "
            "max_states=10000, value_cap=-1, "
            "abstract_states=482, values=19, cofactor_width=7, "
            "width_upper_bound=21\n"
        ): 7,
        (
            "[t=0.071340s, 534048 KB] wbh PDB heuristic: "
            "pattern_size=6, values=12, "
            "cofactor_width=11, width_upper_bound=17\n"
        ): 11,
        (
            "[t=12.000001s, 987654 KB] wbh potential heuristic: m=8, "
            "values=9, cofactor_width=3, width_upper_bound=10\n"
        ): 3,
    }
    for content, expected in examples.items():
        props = {}
        parse_cofactor_width(content, props)
        if props != {COFACTOR_WIDTH_PROPERTY: expected}:
            raise AssertionError(
                "wrong cofactor-width parse: {!r}".format(props)
            )

    blind_props = {}
    parse_cofactor_width("Solution found.\n", blind_props)
    if blind_props:
        raise AssertionError("blind output unexpectedly gained a width")

    bad_prefix_props = {}
    parse_cofactor_width(
        "[t=0.071340, 534048 KB] wbh PDB heuristic: pattern_size=6, "
        "values=12, cofactor_width=11, width_upper_bound=17\n",
        bad_prefix_props,
    )
    expected_bad_prefix = [
        "cofactor-width parser rejected a nonstandard run.log prefix"
    ]
    if bad_prefix_props != {"unexplained_errors": expected_bad_prefix}:
        raise AssertionError(
            "nonstandard log prefix did not fail closed: {!r}".format(
                bad_prefix_props
            )
        )

    malformed_props = {}
    parse_cofactor_width(
        "[t=0.071340s, 534048 KB] wbh PDB heuristic: "
        "pattern_size=6, values=12, "
        "cofactor_width=oops, width_upper_bound=17\n",
        malformed_props,
    )
    expected_malformed = [
        "cofactor-width parser expected one integer field; got 0"
    ]
    if malformed_props != {"unexplained_errors": expected_malformed}:
        raise AssertionError(
            "malformed cofactor width did not fail closed: {!r}".format(
                malformed_props
            )
        )

    duplicate_props = {}
    duplicate_line = next(iter(examples))
    parse_cofactor_width(duplicate_line + duplicate_line, duplicate_props)
    expected_duplicate = [
        "cofactor-width parser expected one wbh heuristic line; got 2"
    ]
    if duplicate_props != {"unexplained_errors": expected_duplicate}:
        raise AssertionError(
            "duplicate heuristic lines did not fail closed: {!r}".format(
                duplicate_props
            )
        )

    duplicate_field_props = {}
    parse_cofactor_width(
        "[t=0.071340s, 534048 KB] wbh PDB heuristic: "
        "pattern_size=6, cofactor_width=4, "
        "cofactor_width=5, width_upper_bound=17\n",
        duplicate_field_props,
    )
    expected_duplicate_field = [
        "cofactor-width parser expected one integer field; got 2"
    ]
    if duplicate_field_props != {
        "unexplained_errors": expected_duplicate_field
    }:
        raise AssertionError(
            "duplicate cofactor fields did not fail closed: {!r}".format(
                duplicate_field_props
            )
        )

    parser = get_cofactor_width_parser()
    if len(parser.functions) != 1 or parser.functions[0].filename != "run.log":
        raise AssertionError("cofactor-width parser is not bound to run.log")
    if COFACTOR_WIDTH_PROPERTY not in ATTRIBUTES:
        raise AssertionError("cofactor_width is missing from ATTRIBUTES")
    metadata = common_protocol_metadata(REV, "0" * 64, 700)
    if metadata.get("cofactor_width_parser_protocol") != (
        COFACTOR_WIDTH_PARSER_PROTOCOL
    ):
        raise AssertionError("cofactor-width protocol metadata changed")
    tampered = dict(metadata)
    tampered["cofactor_width_parser_protocol"] = "changed"
    try:
        validate_common_protocol_metadata(tampered)
    except RuntimeError:
        pass
    else:
        raise AssertionError("changed cofactor-width protocol was accepted")
    print(
        "cofactor-width parser self-tests: PASS "
        "(M&S/PDB/potential; missing/duplicate/malformed gates)"
    )


def _synthetic_selector_record(
    sources, pattern, states, width, upper, budget, initial_h
):
    return {
        "protocol": PDB_SELECTOR_POOL_PROTOCOL,
        "score_version": PDB_SELECTOR_SCORE_VERSION,
        "sources": sources,
        "pattern": pattern,
        "abstract_states": states,
        "initial_dead_end": False,
        "initial_h": initial_h,
        "finite_sum": initial_h * states,
        "finite_count": states,
        "dead_count": 0,
        "cofactor_width": width,
        "width_upper_bound": upper,
        "cofactor_width_budget": budget,
        "feasible": width <= budget,
        "rejection_reason": None if width <= budget else "cofactor_width_budget",
    }


def self_test_pdb_selector_parser():
    prefix = "[t=0.071340s, 534048 KB] "
    legacy = (
        prefix
        + "wbh PDB heuristic: pattern_size=6, values=12, "
        "cofactor_width=11, width_upper_bound=17\n"
    )
    legacy_props = {}
    parse_cofactor_width(legacy, legacy_props)
    parse_pdb_selector_log(legacy, legacy_props)
    expected_legacy = {
        "cofactor_width": 11,
        "pdb_final_format": "legacy",
        "pdb_pattern_size": 6,
        "pdb_final_num_values": 12,
        "pdb_final_cofactor_width": 11,
        "pdb_final_width_upper_bound": 17,
    }
    if legacy_props != expected_legacy:
        raise AssertionError(
            "legacy PDB final parsing regressed: {!r}".format(legacy_props)
        )

    budget = 8
    empty = _synthetic_selector_record(
        ["empty"], [], 1, 1, 1, budget, 0
    )
    winner = _synthetic_selector_record(
        ["bdd_prefix", "goal_prefix", "goal_fill"],
        [0],
        2,
        2,
        2,
        budget,
        1,
    )
    oversized = {
        "protocol": PDB_SELECTOR_POOL_PROTOCOL,
        "score_version": PDB_SELECTOR_SCORE_VERSION,
        "sources": ["cegar"],
        "pattern": [1],
        "abstract_states": 100001,
        "initial_dead_end": None,
        "initial_h": None,
        "finite_sum": None,
        "finite_count": None,
        "dead_count": None,
        "cofactor_width": None,
        "width_upper_bound": None,
        "cofactor_width_budget": budget,
        "feasible": False,
        "rejection_reason": "abstract_state_budget",
    }
    candidates = [empty, winner, oversized]
    final = {
        "pattern_size": 1,
        "selected_source": "bdd_prefix",
        "abstract_states": 2,
        "cofactor_width_budget": budget,
        "num_values": 2,
        "cofactor_width": 2,
        "width_upper_bound": 2,
    }

    def selector_line(kind, record):
        return (
            prefix
            + "PDB width-selector v1 {}: ".format(kind)
            + json.dumps(record, separators=(",", ":"))
            + "\n"
        )

    def final_line(values=2, width=2, upper=2):
        return (
            prefix
            + "wbh PDB heuristic: pattern_size=1, "
            "selected_source=bdd_prefix, abstract_states=2, "
            "cofactor_width_budget=8, values={}, cofactor_width={}, "
            "width_upper_bound={}\n".format(values, width, upper)
        )

    candidate_lines = "".join(
        selector_line("candidate", record) for record in candidates
    )
    selected_line = selector_line("selected", winner)
    exact = candidate_lines + selected_line + final_line()
    exact_props = {"width_upper_bound": 2, "num_values": 2}
    parse_cofactor_width(exact, exact_props)
    parse_pdb_selector_log(exact, exact_props)
    if exact_props.get("unexplained_errors"):
        raise AssertionError(
            "valid exact-selector output was rejected: {!r}".format(
                exact_props
            )
        )
    expected_trace = {
        PDB_SELECTOR_TRACE_COMPLETE_PROPERTY: True,
        PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY: True,
        PDB_SELECTOR_VALIDATION_ERROR_PROPERTY: None,
        PDB_SELECTOR_TRACE_SHA256_PROPERTY: pdb_selector_trace_sha256(
            candidates, winner, final
        ),
        PDB_SELECTOR_POOL_SHA256_PROPERTY: pdb_selector_pool_sha256(
            candidates
        ),
        PDB_SELECTOR_CANDIDATES_PROPERTY: candidates,
        PDB_SELECTOR_SELECTED_PROPERTY: winner,
        PDB_SELECTOR_FINAL_PROPERTY: final,
    }
    for key, value in expected_trace.items():
        if exact_props.get(key) != value:
            raise AssertionError(
                "wrong exact-selector property {}={!r}, expected {!r}".format(
                    key, exact_props.get(key), value
                )
            )
    for key, value in (
        ("cofactor_width", 2),
        ("pdb_final_format", "exact_width_filter"),
        ("pdb_pattern_size", 1),
        ("pdb_selected_source", "bdd_prefix"),
        ("pdb_abstract_states", 2),
        ("pdb_cofactor_width_budget", budget),
        ("pdb_final_num_values", 2),
        ("pdb_final_cofactor_width", 2),
        ("pdb_final_width_upper_bound", 2),
    ):
        if exact_props.get(key) != value:
            raise AssertionError(
                "wrong exact final property {}={!r}".format(
                    key, exact_props.get(key)
                )
            )

    # Timestamp/memory prefixes are intentionally excluded from trace identity.
    shifted = exact.replace(
        "[t=0.071340s, 534048 KB]", "[t=9.000000s, 600000 KB]"
    )
    shifted_props = {"width_upper_bound": 2, "num_values": 2}
    parse_cofactor_width(shifted, shifted_props)
    parse_pdb_selector_log(shifted, shifted_props)
    if (
        shifted_props.get(PDB_SELECTOR_TRACE_SHA256_PROPERTY)
        != exact_props[PDB_SELECTOR_TRACE_SHA256_PROPERTY]
        or shifted_props.get(PDB_SELECTOR_POOL_SHA256_PROPERTY)
        != exact_props[PDB_SELECTOR_POOL_SHA256_PROPERTY]
    ):
        raise AssertionError("selector trace hashes depend on log timestamps")

    # The initial state may be abstractly dead even though every PDB retains at
    # least one finite abstract goal state at distance zero.
    initial_dead = copy.deepcopy(winner)
    initial_dead.update(
        {
            "initial_dead_end": True,
            "initial_h": None,
            "finite_sum": 0,
            "finite_count": 1,
            "dead_count": 1,
        }
    )
    initial_dead_candidates = [empty, initial_dead, oversized]
    initial_dead_content = (
        "".join(
            selector_line("candidate", record)
            for record in initial_dead_candidates
        )
        + selector_line("selected", initial_dead)
        + final_line(values=1)
    )
    initial_dead_props = {"width_upper_bound": 2, "num_values": 1}
    parse_cofactor_width(initial_dead_content, initial_dead_props)
    parse_pdb_selector_log(initial_dead_content, initial_dead_props)
    if initial_dead_props.get(PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY) is not True:
        raise AssertionError(
            "valid initial-dead selector trace was rejected: {!r}".format(
                initial_dead_props
            )
        )

    # Resource kills can leave a valid candidate-only prefix, or all
    # candidates plus selected but no final. They remain explicit and
    # uncertified without becoming parser infrastructure errors.
    partials = (
        selector_line("candidate", empty),
        candidate_lines + selected_line,
    )
    for partial in partials:
        partial_props = {}
        parse_pdb_selector_log(partial, partial_props)
        if (
            partial_props.get(PDB_SELECTOR_TRACE_COMPLETE_PROPERTY) is not False
            or partial_props.get(PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY) is not False
            or not partial_props.get(PDB_SELECTOR_VALIDATION_ERROR_PROPERTY)
            or partial_props.get(PDB_SELECTOR_TRACE_SHA256_PROPERTY) is not None
            or partial_props.get(PDB_SELECTOR_POOL_SHA256_PROPERTY) is not None
            or partial_props.get("unexplained_errors")
        ):
            raise AssertionError(
                "valid interrupted selector prefix was mishandled: {!r}".
                format(partial_props)
            )

    def assert_rejected(name, content, initial_props=None):
        props = dict(initial_props or {})
        parse_cofactor_width(content, props)
        parse_pdb_selector_log(content, props)
        if (
            props.get(PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY) is True
            or not props.get(PDB_SELECTOR_VALIDATION_ERROR_PROPERTY)
            or not props.get("unexplained_errors")
        ):
            raise AssertionError(
                "{} selector mutation was accepted: {!r}".format(name, props)
            )

    assert_rejected("duplicate selected", exact + selected_line)
    assert_rejected(
        "duplicate JSON key",
        exact.replace(
            '"protocol":"fixed_pool_v1"',
            '"protocol":"fixed_pool_v1","protocol":"fixed_pool_v1"',
            1,
        ),
    )
    assert_rejected(
        "malformed final",
        exact.replace("cofactor_width_budget=8", "width_budget=8"),
    )
    assert_rejected(
        "out-of-order final",
        final_line() + candidate_lines + selected_line,
    )

    duplicate_pattern = copy.deepcopy(candidates)
    duplicate_pattern[2]["pattern"] = [0]
    assert_rejected(
        "duplicate candidate pattern",
        "".join(
            selector_line("candidate", record)
            for record in duplicate_pattern
        )
        + selected_line
        + final_line(),
    )

    missing_source = copy.deepcopy(candidates)
    missing_source[1]["sources"].remove("goal_fill")
    missing_selected = copy.deepcopy(winner)
    missing_selected["sources"].remove("goal_fill")
    assert_rejected(
        "missing provenance",
        "".join(
            selector_line("candidate", record)
            for record in missing_source
        )
        + selector_line("selected", missing_selected)
        + final_line(),
    )

    assert_rejected(
        "candidate order",
        "".join(
            selector_line("candidate", record)
            for record in (winner, empty, oversized)
        )
        + selected_line
        + final_line(),
    )

    skipped_prefix = copy.deepcopy(winner)
    skipped_prefix["sources"] = ["goal_fill"]
    assert_rejected(
        "skipped partial source prefix",
        selector_line("candidate", empty)
        + selector_line("candidate", skipped_prefix),
    )
    merged_skip = copy.deepcopy(empty)
    merged_skip["sources"] = ["empty", "cegar"]
    assert_rejected(
        "deduplicated later source skips partial prefix",
        selector_line("candidate", merged_skip),
    )
    assert_rejected(
        "wrong selected winner",
        candidate_lines + selector_line("selected", empty) + final_line(),
    )

    impossible_sum = copy.deepcopy(winner)
    impossible_sum["finite_sum"] = 0
    assert_rejected(
        "initial h exceeds finite sum",
        selector_line("candidate", empty)
        + selector_line("candidate", impossible_sum)
        + selector_line("candidate", oversized)
        + selector_line("selected", impossible_sum)
        + final_line(),
    )

    impossible_all_dead = copy.deepcopy(winner)
    impossible_all_dead.update(
        {
            "initial_dead_end": True,
            "initial_h": None,
            "finite_sum": 0,
            "finite_count": 0,
            "dead_count": impossible_all_dead["abstract_states"],
        }
    )
    assert_rejected(
        "all-dead PDB",
        selector_line("candidate", empty)
        + selector_line("candidate", impossible_all_dead)
        + selector_line("candidate", oversized)
        + selector_line("selected", impossible_all_dead)
        + final_line(values=0),
    )

    mixed_budget = copy.deepcopy(candidates)
    mixed_budget[2]["cofactor_width_budget"] = 7
    assert_rejected(
        "mixed width budget",
        "".join(
            selector_line("candidate", record)
            for record in mixed_budget
        )
        + selected_line
        + final_line(),
    )
    assert_rejected(
        "final-selected width mismatch",
        candidate_lines + selected_line + final_line(width=3, upper=3),
    )

    bad_oversized = copy.deepcopy(oversized)
    bad_oversized["sources"] = ["goal_fill"]
    assert_rejected(
        "invalid unmaterialized source",
        selector_line("candidate", empty)
        + selector_line("candidate", winner)
        + selector_line("candidate", bad_oversized)
        + selected_line
        + final_line(),
    )
    multi_var_oversized = copy.deepcopy(oversized)
    multi_var_oversized["pattern"] = [0, 1]
    assert_rejected(
        "invalid multi-variable unmaterialized CEGAR",
        selector_line("candidate", empty)
        + selector_line("candidate", winner)
        + selector_line("candidate", multi_var_oversized)
        + selected_line
        + final_line(),
    )

    parser = get_pdb_selector_parser()
    if len(parser.functions) != 1 or parser.functions[0].filename != "run.log":
        raise AssertionError("selector parser is not bound to run.log")
    for attribute in (
        PDB_SELECTOR_CANDIDATES_PROPERTY,
        PDB_SELECTOR_SELECTED_PROPERTY,
        PDB_SELECTOR_FINAL_PROPERTY,
        PDB_SELECTOR_TRACE_COMPLETE_PROPERTY,
        PDB_SELECTOR_TRACE_CERTIFIED_PROPERTY,
        PDB_SELECTOR_VALIDATION_ERROR_PROPERTY,
        PDB_SELECTOR_TRACE_SHA256_PROPERTY,
        PDB_SELECTOR_POOL_SHA256_PROPERTY,
        "pdb_final_format",
        "pdb_cofactor_width_budget",
    ):
        if attribute not in ATTRIBUTES:
            raise AssertionError(
                "selector property missing from ATTRIBUTES: {}".format(
                    attribute
                )
            )
    print(
        "PDB selector parser self-tests: PASS "
        "(legacy; dedup/unmaterialized/initial-dead; certified hashes; "
        "valid interruption prefixes; malformed whole-trace gates)"
    )


def self_test_plan_file_parser():
    for footer in ("unit cost", "general cost"):
        props = {}
        parse_plan_file("(move a b)\n; cost = 17 ({})\n".format(footer), props)
        if props != {
            "plan_file_present": True,
            "plan_file_candidate_count": 1,
            "plan_file_canonical": True,
            "plan_file_cost": 17,
        }:
            raise AssertionError("wrong plan-file parse: {!r}".format(props))
    empty = {}
    parse_plan_file("", empty)
    if empty != {
        "plan_file_present": False,
        "plan_file_candidate_count": 0,
        "plan_file_canonical": False,
    }:
        raise AssertionError("missing plan file was not recorded exactly")
    for label, content in (
        ("missing footer", "(move a b)\n"),
        (
            "non-final footer",
            "(move a b)\n; cost = 17 (unit cost)\ntrailing text\n",
        ),
        (
            "duplicate footer",
            "; cost = 17 (unit cost)\n; cost = 17 (unit cost)\n",
        ),
        (
            "footer without terminal newline",
            "(move a b)\n; cost = 17 (unit cost)",
        ),
        (
            "noncanonical footer integer",
            "(move a b)\n; cost = 017 (unit cost)\n",
        ),
    ):
        malformed = {}
        parse_plan_file(content, malformed)
        if (
            malformed.get("plan_file_present") is not True
            or malformed.get("plan_file_candidate_count") != 1
            or malformed.get("plan_file_canonical") is not False
            or not malformed.get("unexplained_errors")
        ):
            raise AssertionError("{} was accepted".format(label))

    canonical_plan = "(move a b)\n; cost = 17 (unit cost)\n"

    def parse_inventory(setup):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup(root)
            props = {}
            get_plan_file_parser().parse(root, props)
            return props

    inventory = parse_inventory(
        lambda root: (root / "sas_plan").write_text(
            canonical_plan, encoding="utf-8"
        )
    )
    if inventory != {
        "plan_file_present": True,
        "plan_file_candidate_count": 1,
        "plan_file_canonical": True,
        "plan_file_cost": 17,
    }:
        raise AssertionError("canonical inventory was not accepted: {!r}".format(
            inventory
        ))

    def canonical_plus_numeric(root):
        (root / "sas_plan").write_text(canonical_plan, encoding="utf-8")
        (root / "sas_plan.1").write_text(canonical_plan, encoding="utf-8")
        (root / "sas_plan.\u0661").write_text(canonical_plan, encoding="utf-8")

    inventory = parse_inventory(canonical_plus_numeric)
    if (
        inventory.get("plan_file_candidate_count") != 3
        or inventory.get("plan_file_canonical") is not False
        or not inventory.get("unexplained_errors")
    ):
        raise AssertionError("numeric side plan was not rejected: {!r}".format(
            inventory
        ))

    inventory = parse_inventory(
        lambda root: (root / "sas_plan.7").write_text(
            canonical_plan, encoding="utf-8"
        )
    )
    if (
        inventory.get("plan_file_present") is not False
        or inventory.get("plan_file_candidate_count") != 1
        or inventory.get("plan_file_canonical") is not False
        or not inventory.get("unexplained_errors")
    ):
        raise AssertionError("numeric-only inventory was accepted: {!r}".format(
            inventory
        ))

    def canonical_symlink(root):
        (root / "real_plan").write_text(canonical_plan, encoding="utf-8")
        (root / "sas_plan").symlink_to("real_plan")

    inventory = parse_inventory(canonical_symlink)
    if (
        inventory.get("plan_file_candidate_count") != 1
        or inventory.get("plan_file_canonical") is not False
        or not inventory.get("unexplained_errors")
    ):
        raise AssertionError("canonical symlink was accepted: {!r}".format(
            inventory
        ))

    def canonical_hardlink(root):
        (root / "plan_source").write_text(canonical_plan, encoding="utf-8")
        os.link(root / "plan_source", root / "sas_plan")

    inventory = parse_inventory(canonical_hardlink)
    if (
        inventory.get("plan_file_candidate_count") != 1
        or inventory.get("plan_file_canonical") is not False
        or not inventory.get("unexplained_errors")
    ):
        raise AssertionError("canonical hardlink was accepted: {!r}".format(
            inventory
        ))

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "sas_plan"
        path.write_text(canonical_plan, encoding="utf-8")
        initial_status = path.lstat()
        replacement = root / "replacement"
        replacement.write_text(canonical_plan, encoding="utf-8")
        os.replace(replacement, path)
        try:
            _read_stable_plan_file(path, initial_status)
        except OSError:
            pass
        else:
            raise AssertionError("replaced canonical plan identity was accepted")

    def broken_numeric_symlink(root):
        (root / "sas_plan").write_text(canonical_plan, encoding="utf-8")
        (root / "sas_plan.2").symlink_to("missing-target")

    inventory = parse_inventory(broken_numeric_symlink)
    if (
        inventory.get("plan_file_candidate_count") != 2
        or inventory.get("plan_file_canonical") is not False
        or not inventory.get("unexplained_errors")
    ):
        raise AssertionError("broken numeric symlink was not inventoried: {!r}".
                             format(inventory))

    inventory = parse_inventory(lambda root: (root / "sas_plan").mkdir())
    if (
        inventory.get("plan_file_candidate_count") != 1
        or inventory.get("plan_file_canonical") is not False
        or not inventory.get("unexplained_errors")
    ):
        raise AssertionError("nonregular canonical plan was accepted: {!r}".format(
            inventory
        ))

    inventory = parse_inventory(
        lambda root: (root / "sas_plan").write_text("", encoding="utf-8")
    )
    if (
        inventory.get("plan_file_candidate_count") != 1
        or inventory.get("plan_file_canonical") is not False
        or not inventory.get("unexplained_errors")
    ):
        raise AssertionError("empty canonical plan was accepted: {!r}".format(
            inventory
        ))

    inventory = parse_inventory(lambda root: None)
    if inventory != {
        "plan_file_candidate_count": 0,
        "plan_file_present": False,
        "plan_file_canonical": False,
    }:
        raise AssertionError("empty inventory was not exact: {!r}".format(inventory))
    if not isinstance(get_plan_file_parser(), PlanFileParser):
        raise AssertionError("plan-file parser type changed")
    print(
        "plan-file parser self-tests: PASS "
        "(exact stable single-link inventory/footer; "
        "numeric/symlink/hardlink/replacement/nonregular adversaries)"
    )


def _synthetic_solved_outcome_props(exit_code):
    return {
        "planner_exit_code": exit_code,
        "coverage": 1,
        "solution_cost": 17,
        "plan_file_present": True,
        "plan_file_candidate_count": 1,
        "plan_file_canonical": True,
        "plan_file_cost": 17,
        "run_log_plan_cost": 17,
        "wbh_schema_version": 2,
        "raw_metrics_complete": True,
        "piece_metrics_certified": True,
        "wbh_summary_solved": True,
        "wbh_done_solution_cost": 17,
        "wbh_solved_summary_certified": True,
        "planner_time": 1.25,
    }


def self_test_outcome_reconciliation_parser():
    identity = _synthetic_solved_outcome_props(0)
    parse_outcome_reconciliation(
        "search raw exit code: 0\nsearch exit code: 0\n", identity
    )
    if (
        identity.get("search_raw_exit_code") != 0
        or identity.get("search_effective_exit_code") != 0
        or identity.get("outcome_reconciliation_certified") is not True
    ):
        raise AssertionError("identity solved outcome was not certified")

    for raw, effective in sorted(_MAPPED_RESOURCE_EXITS.items()):
        props = _synthetic_solved_outcome_props(effective)
        log = (
            "search raw exit code: {raw}\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code={raw} effective_exit_code={effective}\n"
            "search exit code: {effective}\n"
        ).format(raw=raw, effective=effective)
        parse_outcome_reconciliation(log, props)
        if props.get("outcome_reconciliation_certified") is not True:
            raise AssertionError(
                "exact mapping {}->{} was not certified: {!r}".format(
                    raw, effective, props
                )
            )

    resource_base = {
        "planner_exit_code": 23,
        "coverage": 0,
        "plan_file_present": False,
        "plan_file_candidate_count": 0,
        "plan_file_canonical": False,
        "wbh_schema_version": 2,
        "raw_metrics_complete": False,
        "piece_metrics_certified": True,
        "wbh_summary_solved": None,
        "wbh_done_solution_cost": None,
        "wbh_solved_summary_certified": False,
    }
    resource = copy.deepcopy(resource_base)
    parse_outcome_reconciliation(
        "search raw exit code: 23\nsearch exit code: 23\n", resource
    )
    if resource.get("outcome_reconciliation_certified") is not True:
        raise AssertionError("ordinary resource exit was not preserved as unsolved")

    unsolved_wbh_mutations = (
        (
            "incomplete summary claims solved",
            {"wbh_summary_solved": True},
        ),
        (
            "missing exact false certification",
            {"wbh_solved_summary_certified": None},
        ),
        (
            "string false certification",
            {"wbh_solved_summary_certified": "false"},
        ),
        (
            "complete summary omits solved=false",
            {"raw_metrics_complete": True, "wbh_summary_solved": None},
        ),
        (
            "complete summary claims solved",
            {"raw_metrics_complete": True, "wbh_summary_solved": True},
        ),
    )
    for label, updates in unsolved_wbh_mutations:
        props = copy.deepcopy(resource_base)
        props.update(updates)
        parse_outcome_reconciliation(
            "search raw exit code: 23\nsearch exit code: 23\n", props
        )
        if props.get("outcome_reconciliation_certified") is not False:
            raise AssertionError("{} was accepted".format(label))
        if not props.get("outcome_reconciliation_error"):
            raise AssertionError("{} lacks a diagnostic".format(label))

    mutations = (
        (
            "missing marker",
            "search raw exit code: 23\nsearch exit code: 2\n",
            lambda props: None,
        ),
        (
            "wrong mapping",
            "search raw exit code: 22\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=22 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: None,
        ),
        (
            "duplicate raw",
            "search raw exit code: 23\nsearch raw exit code: 23\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: None,
        ),
        (
            "noncanonical plan",
            "search raw exit code: 23\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: props.update(plan_file_canonical=False),
        ),
        (
            "multiple plan candidates",
            "search raw exit code: 23\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: props.update(plan_file_candidate_count=2),
        ),
        (
            "cost disagreement",
            "search raw exit code: 23\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: props.update(wbh_done_solution_cost=18),
        ),
        (
            "run-log cost disagreement",
            "search raw exit code: 23\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: props.update(run_log_plan_cost=18),
        ),
        (
            "plan-file cost disagreement",
            "search raw exit code: 23\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: props.update(plan_file_cost=18),
        ),
        (
            "incomplete summary",
            "search raw exit code: 23\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: props.update(
                raw_metrics_complete=False,
                wbh_solved_summary_certified=False,
            ),
        ),
        (
            "parser error",
            "search raw exit code: 23\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: props.update(unexplained_errors=["synthetic"]),
        ),
        (
            "WBH parser error",
            "search raw exit code: 23\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: props.update(
                metrics_validation_error="synthetic corruption",
                piece_metrics_certified=False,
                wbh_solved_summary_certified=False,
            ),
        ),
        (
            "mapped coverage zero",
            "search raw exit code: 23\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: props.update(coverage=0),
        ),
        (
            "noncanonical integer",
            "search raw exit code: 023\n"
            "search resource-limit exit with complete plan: "
            "raw_exit_code=23 effective_exit_code=2\n"
            "search exit code: 2\n",
            lambda props: None,
        ),
        (
            "resource plan without mapping",
            "search raw exit code: 23\nsearch exit code: 23\n",
            lambda props: props.update(
                planner_exit_code=23,
                coverage=1,
            ),
        ),
        (
            "identity mapped code",
            "search raw exit code: 2\nsearch exit code: 2\n",
            lambda props: None,
        ),
    )
    for label, log, mutate in mutations:
        props = _synthetic_solved_outcome_props(2)
        mutate(props)
        parse_outcome_reconciliation(log, props)
        if props.get("outcome_reconciliation_certified") is not False:
            raise AssertionError("{} was not rejected".format(label))
        if not props.get("outcome_reconciliation_error"):
            raise AssertionError("{} lacks a diagnostic".format(label))

    run_log = {}
    parse_run_log_plan_cost("[t=0.352273s, 557192 KB] Plan cost: 17\n", run_log)
    if run_log != {"run_log_plan_cost": 17}:
        raise AssertionError("canonical run-log cost was not preserved")
    duplicate = {}
    parse_run_log_plan_cost(
        "[t=0.352273s, 557192 KB] Plan cost: 17\n"
        "[t=0.352274s, 557192 KB] Plan cost: 17\n",
        duplicate,
    )
    if not duplicate.get("unexplained_errors"):
        raise AssertionError("duplicate run-log plan costs were accepted")
    for malformed_log in (
        "Plan cost: 17\n",
        "[t=.352273s, 557192 KB] Plan cost: 17\n",
        "[t=0.352273s, 557192 KB] Plan cost: 017\n",
    ):
        malformed_cost = {}
        parse_run_log_plan_cost(malformed_log, malformed_cost)
        if not malformed_cost.get("unexplained_errors"):
            raise AssertionError(
                "malformed run-log plan cost was accepted: {!r}".format(
                    malformed_log
                )
            )
    for exit_code, component in ((20, "translate"), (21, "preprocess")):
        presearch = {
            "planner_exit_code": exit_code,
            "coverage": 0,
            "plan_file_present": False,
            "plan_file_candidate_count": 0,
            "plan_file_canonical": False,
        }
        parse_outcome_reconciliation(
            "{} exit code: {}\nplanner exit code: {}\n".format(
                component, exit_code, exit_code
            ),
            presearch,
        )
        if presearch.get("outcome_reconciliation_certified") is not True:
            raise AssertionError(
                "exact pre-search outcome {} was not certified".format(exit_code)
            )
    malformed_presearch = {
        "planner_exit_code": 20,
        "coverage": 0,
        "plan_file_present": False,
        "plan_file_candidate_count": 0,
        "plan_file_canonical": False,
    }
    parse_outcome_reconciliation(
        "search raw exit code: 20\nsearch exit code: 20\n",
        malformed_presearch,
    )
    if malformed_presearch.get("outcome_reconciliation_certified") is not False:
        raise AssertionError("pre-search outcome with search lines was accepted")
    for parser, filename in (
        (get_run_log_plan_cost_parser(), "run.log"),
        (get_outcome_reconciliation_parser(), "run.log"),
    ):
        if len(parser.functions) != 1 or parser.functions[0].filename != filename:
            raise AssertionError("outcome parser is not bound to {}".format(filename))
    print(
        "outcome reconciliation parser self-tests: PASS "
        "(identity; 3 mappings; resource; adversarial evidence)"
    )


def self_test_pddl_materialization():
    canonical_bytes = b"(define (problem materialized-input))\n"
    expected_sha256 = hashlib.sha256(canonical_bytes).hexdigest()
    with tempfile.TemporaryDirectory(prefix="arrhenius-pddl-materialization-") as raw:
        root = Path(raw)
        source = root / "source.pddl"
        source.write_bytes(canonical_bytes)
        link = root / "problem.pddl"
        link.symlink_to(source)
        copied_bytes = materialize_pddl_link(
            link, source, expected_sha256, "synthetic PDDL"
        )
        if (
            copied_bytes != len(canonical_bytes)
            or link.is_symlink()
            or link.read_bytes() != canonical_bytes
            or link.stat().st_ino == source.stat().st_ino
            or link.stat().st_nlink != 1
            or link.stat().st_mode & 0o222
        ):
            raise AssertionError("independent PDDL materialization changed")
        if require_materialized_pddl(
            link, expected_sha256, "synthetic PDDL", source
        ) != len(canonical_bytes):
            raise AssertionError("materialized PDDL byte count changed")

        link.chmod(0o644)
        try:
            require_materialized_pddl(
                link, expected_sha256, "writable synthetic PDDL", source
            )
        except RuntimeError as err:
            if "must be read-only" not in str(err):
                raise
        else:
            raise AssertionError("writable materialized PDDL was accepted")
        link.chmod(0o444)

        link.chmod(0o644)
        link.write_bytes(b"changed bytes")
        link.chmod(0o444)
        try:
            require_materialized_pddl(
                link, expected_sha256, "tampered synthetic PDDL", source
            )
        except RuntimeError as err:
            if "SHA-256 changed" not in str(err):
                raise
        else:
            raise AssertionError("tampered materialized PDDL was accepted")

        link.chmod(0o644)
        link.unlink()
        link.symlink_to(source)
        try:
            require_materialized_pddl(
                link, expected_sha256, "symlink synthetic PDDL", source
            )
        except RuntimeError as err:
            if "regular non-symlink" not in str(err):
                raise
        else:
            raise AssertionError("materialized PDDL symlink was accepted")

        link.unlink()
        os.link(source, link)
        try:
            require_materialized_pddl(
                link, expected_sha256, "hardlink synthetic PDDL", source
            )
        except RuntimeError as err:
            if "must not be a hardlink" not in str(err):
                raise
        else:
            raise AssertionError("materialized PDDL hardlink was accepted")

        link.unlink()
        link.write_bytes(canonical_bytes)
        try:
            materialize_pddl_link(
                link, source, expected_sha256, "non-link synthetic PDDL"
            )
        except RuntimeError as err:
            if "must begin as the exact live Lab source symlink" not in str(err):
                raise
        else:
            raise AssertionError("PDDL materialization accepted a non-link input")

        wrong_source = root / "wrong-source.pddl"
        wrong_source.write_bytes(b"(define (problem wrong-source))\n")
        wrong_link = root / "wrong-link.pddl"
        wrong_link.symlink_to(wrong_source)
        try:
            materialize_pddl_link(
                wrong_link, source, expected_sha256, "wrong-link synthetic PDDL"
            )
        except RuntimeError as err:
            if "must begin as the exact live Lab source symlink" not in str(err):
                raise
        else:
            raise AssertionError("PDDL materialization accepted the wrong source link")

        wrong_hash_link = root / "wrong-hash.pddl"
        wrong_hash_link.symlink_to(source)
        try:
            materialize_pddl_link(
                wrong_hash_link,
                source,
                hashlib.sha256(b"wrong digest authority").hexdigest(),
                "wrong-hash synthetic PDDL",
            )
        except RuntimeError as err:
            if "benchmark source digest changed" not in str(err):
                raise
        else:
            raise AssertionError("PDDL materialization accepted the wrong digest")
    print(
        "PDDL materialization self-tests: PASS "
        "(atomic independent read-only copy; writable/tamper/link/hash gates)"
    )


if __name__ == "__main__":
    self_test_scheduler_headers()
    self_test_cofactor_width_parser()
    self_test_pdb_selector_parser()
    self_test_plan_file_parser()
    self_test_outcome_reconciliation_parser()
    self_test_pddl_materialization()
