#!/usr/bin/env python3
"""Secondary structural diagnostics for the accepted P6 full census.

This module is deliberately separate from the launch protocol and canonical
full-population analyzer.  Ordinary use first passes the exact P6 selection,
runner, task, properties, and cell records through those canonical gates.  The
diagnostic is descriptive and is not a validation of the width theorem.
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_arrhenius_selector_full as full


class AnalysisError(RuntimeError):
    pass


SCHEMA = "symbolic-search-heuristics/full-population-structure/v1"
PROTOCOL = "p6-secondary-structural-diagnostic/v1"
DECISION_LABEL = (
    "secondary-structural-diagnostic-specified-during-execution-not-launch-"
    "predeclared"
)
SPECIFICATION_BOUNDARY = (
    "frozen-during-active-p6-execution-before-canonical-full-result-analysis/v1"
)
DIRECT_FIELDS = (
    "cofactor_width",
    "add_nodes",
    "num_values",
    "num_terminals",
    "width_upper_bound",
)
RATIO_FIELDS = ("partition_ratio_max", "partition_ratio_geomean")
RESOURCE_EXIT_CODES = full.heldout.RESOURCE_EXIT_CODES
PRESEARCH_EXIT_CODES = full.heldout.PRESEARCH_EXIT_CODES
SELECTOR_LABELS = frozenset(full.heldout.SELECTOR_LABELS)
SELECTOR_SOURCES = tuple(full.heldout.common.PDB_SELECTOR_SOURCES)
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _fail(prefix, message):
    raise AnalysisError("{}: {}".format(prefix, message))


def _finite_nonnegative(value, prefix, field):
    if type(value) not in (int, float):
        _fail(prefix, "{} must be an exact int/float".format(field))
    number = float(value)
    if not math.isfinite(number) or number < 0:
        _fail(prefix, "{} must be finite and nonnegative".format(field))
    return number


def _summary(values):
    values = list(values)
    if not values:
        return {
            "observed": 0,
            "minimum": None,
            "median": None,
            "maximum": None,
            "mean": None,
            "total": None,
        }
    if any(type(value) not in (int, float) for value in values):
        raise AnalysisError("summary values must be exact ints/floats")
    numeric = sorted(float(value) for value in values)
    if any(not math.isfinite(value) for value in numeric):
        raise AnalysisError("summary values must be finite")
    middle = len(numeric) // 2
    median = (
        numeric[middle]
        if len(numeric) % 2
        else (numeric[middle - 1] + numeric[middle]) / 2.0
    )
    total = math.fsum(numeric)
    if not math.isfinite(total) or not math.isfinite(median):
        raise AnalysisError("summary arithmetic is not finite")
    return {
        "observed": len(values),
        "minimum": min(values),
        "median": median,
        "maximum": max(values),
        "mean": total / len(values),
        "total": total,
    }


def _average_ranks(values):
    values = list(values)
    if any(type(value) not in (int, float) for value in values):
        raise AnalysisError("rank values must be exact ints/floats")
    numeric = [float(value) for value in values]
    if any(not math.isfinite(value) for value in numeric):
        raise AnalysisError("rank values must be finite")
    order = sorted(range(len(numeric)), key=lambda index: (numeric[index], index))
    ranks = [0.0] * len(numeric)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and numeric[order[end]] == numeric[order[start]]:
            end += 1
        average = ((start + 1) + end) / 2.0
        for position in range(start, end):
            ranks[order[position]] = average
        start = end
    return ranks


def spearman_average_ties(xs, ys):
    """Return a deterministic descriptive Spearman coefficient."""
    xs = list(xs)
    ys = list(ys)
    if len(xs) != len(ys):
        raise AnalysisError("Spearman inputs have different lengths")
    n = len(xs)
    if n < 2:
        return {
            "n": n,
            "coefficient": None,
            "null_reason": "fewer-than-two-pairs",
        }
    rank_x = _average_ranks(xs)
    rank_y = _average_ranks(ys)
    mean = (n + 1) / 2.0
    centered_x = [rank - mean for rank in rank_x]
    centered_y = [rank - mean for rank in rank_y]
    variance_x = math.fsum(value * value for value in centered_x)
    variance_y = math.fsum(value * value for value in centered_y)
    if variance_x == 0 or variance_y == 0:
        return {
            "n": n,
            "coefficient": None,
            "null_reason": "zero-rank-variance",
        }
    covariance = math.fsum(
        left * right for left, right in zip(centered_x, centered_y)
    )
    coefficient = covariance / math.sqrt(variance_x * variance_y)
    if not math.isfinite(coefficient):
        raise AnalysisError("Spearman coefficient is not finite")
    # Protect canonical JSON from harmless final-bit drift outside [-1, 1].
    coefficient = max(-1.0, min(1.0, coefficient))
    return {"n": n, "coefficient": coefficient, "null_reason": None}


def _prefix(label, task):
    return "{} {}:{}".format(label, task[0], task[1])


def _require_certified_v2(record, prefix):
    if record.get("wbh_schema_version") != 2:
        _fail(prefix, "structural observation requires WBH schema 2")
    if record.get("piece_metrics_certified") is not True:
        _fail(prefix, "structural observation requires certified piece metrics")
    if record.get("metrics_validation_error") is not None:
        _fail(prefix, "structural observation has a metrics validation error")
    raw_complete = record.get("raw_metrics_complete")
    exit_code = record.get("planner_exit_code")
    if raw_complete is True:
        return "raw-complete-log"
    if raw_complete is False and exit_code in RESOURCE_EXIT_CODES:
        return "certified-resource-prefix"
    _fail(prefix, "structural observation is neither raw-complete nor an accepted resource prefix")


def _direct_observation(record, label, task):
    prefix = _prefix(label, task)
    present = [field for field in DIRECT_FIELDS if field in record]
    construction_present = "construction_completed" in record
    construction = record.get("construction_completed")
    if construction_present and type(construction) is not bool:
        _fail(prefix, "construction_completed must be boolean")

    if not present:
        if label == full.BLIND:
            if construction_present:
                _fail(prefix, "blind cell unexpectedly has a construction outcome")
            return {"kind": "blind-not-eligible"}
        if construction is True:
            _fail(prefix, "completed construction lacks a direct W/A/V/T/U tuple")
        if construction is False:
            if label != full.MS_CAP32_BUILD60:
                _fail(prefix, "construction fallback is not enabled for this config")
            return {"kind": "unobserved", "reason": "construction-fallback"}
        exit_code = record.get("planner_exit_code")
        if exit_code in PRESEARCH_EXIT_CODES:
            return {"kind": "unobserved", "reason": "presearch-outcome"}
        if exit_code in RESOURCE_EXIT_CODES:
            return {
                "kind": "unobserved",
                "reason": "resource-before-direct-tuple",
            }
        _fail(prefix, "nonblind cell lacks both construction outcome and a resource/presearch exit")

    if label == full.BLIND:
        _fail(prefix, "blind cell unexpectedly has direct heuristic fields")

    if present != list(DIRECT_FIELDS):
        width_only = present == ["cofactor_width"]
        if not (
            width_only
            and label in SELECTOR_LABELS
            and not construction_present
            and record.get("planner_exit_code") in RESOURCE_EXIT_CODES
            and record.get("pdb_selector_trace_complete") is True
            and record.get("pdb_selector_trace_certified") is True
        ):
            _fail(prefix, "direct W/A/V/T/U tuple is partial")
        width = record["cofactor_width"]
        if type(width) is not int or width < 1:
            _fail(prefix, "selector width-only prefix has invalid W")
        stratum = _require_certified_v2(record, prefix)
        if stratum != "certified-resource-prefix":
            _fail(
                prefix,
                "selector width-only exception requires an incomplete "
                "certified resource prefix",
            )
        return {
            "kind": "unobserved",
            "reason": "selector-width-only-resource-prefix",
        }

    values = [record[field] for field in DIRECT_FIELDS]
    if any(type(value) is not int for value in values):
        _fail(prefix, "direct W/A/V/T/U values must be exact integers")
    width, add_nodes, num_values, num_terminals, upper = values
    if not (width >= num_terminals >= num_values >= 1):
        _fail(prefix, "direct tuple violates W >= T >= V >= 1")
    if add_nodes < 0:
        _fail(prefix, "direct tuple violates A >= 0")
    if upper != add_nodes + num_terminals:
        _fail(prefix, "direct tuple violates U = A + T")
    if width > upper:
        _fail(prefix, "direct tuple violates W <= U")
    stratum = _require_certified_v2(record, prefix)
    if construction is True:
        source = "completed-construction"
    elif (
        not construction_present
        and record.get("planner_exit_code") in RESOURCE_EXIT_CODES
        and stratum == "certified-resource-prefix"
    ):
        source = "heuristic-event-only-resource-prefix"
    else:
        _fail(prefix, "direct tuple has no valid completed/heuristic-only source")
    return {
        "kind": "tuple",
        "source": source,
        "W": width,
        "A": add_nodes,
        "V": num_values,
        "T": num_terminals,
        "U": upper,
    }


def _partition_observation(record, label, task):
    prefix = _prefix(label, task)
    present = [field in record for field in RATIO_FIELDS]
    if present[0] != present[1]:
        _fail(prefix, "partition_ratio_max/geomean must be jointly present or absent")
    ratios = None
    if all(present):
        ratios = {
            "max": _finite_nonnegative(record[RATIO_FIELDS[0]], prefix, RATIO_FIELDS[0]),
            "geomean": _finite_nonnegative(
                record[RATIO_FIELDS[1]], prefix, RATIO_FIELDS[1]
            ),
        }
        if ratios["max"] < ratios["geomean"] and not math.isclose(
            ratios["max"], ratios["geomean"], rel_tol=1e-12, abs_tol=1e-15
        ):
            _fail(prefix, "partition_ratio_max must be >= partition_ratio_geomean")

    # Partition ratios diagnose fragmentation by an actually installed
    # heuristic.  Blind searches, fallbacks, pre-search cells, and prefixes
    # that ended before the construction-complete event are outside this
    # estimand even when another structural observation (for example the WBH
    # heuristic event) is independently certified.
    installed_heuristic = (
        label != full.BLIND and record.get("construction_completed") is True
    )
    if not installed_heuristic:
        if ratios is not None:
            _fail(
                prefix,
                "partition ratios require a nonblind completed construction",
            )
        return None

    certified_v2 = (
        record.get("wbh_schema_version") == 2
        and record.get("piece_metrics_certified") is True
        and record.get("metrics_validation_error") is None
    )
    if not certified_v2:
        if ratios is not None:
            _fail(prefix, "partition ratios occur outside a certified schema-2 log")
        return None
    stratum = _require_certified_v2(record, prefix)
    return {"stratum": stratum, "ratios": ratios}


def _outcome_histogram(records):
    counts = Counter(record.get("planner_exit_code") for record in records)
    allowed = set(full.TERMINAL_OUTCOME_CODES)
    if any(type(code) is not int or code not in allowed for code in counts):
        raise AnalysisError("partition stratum has an unrecognized terminal outcome")
    return [
        {"code": code, "outcome": outcome, "count": counts[code]}
        for code, outcome, _presearch, _raw, _effective in full.TERMINAL_OUTCOME_SPECS
    ]


def _stratum_summary(eligible, observed):
    ratio_census = Counter(
        (
            record["partition_ratio_max"],
            record["partition_ratio_geomean"],
        )
        for record in observed
    )
    return {
        "eligible_logs": len(eligible),
        "logs_with_partition_ratios": len(observed),
        "logs_without_partition_ratios": len(eligible) - len(observed),
        "partition_ratio_census_unit": (
            "one-certified-log-with-partition-ratios"
        ),
        "partition_ratio_census": [
            {
                "partition_ratio_max": key[0],
                "partition_ratio_geomean": key[1],
                "count": ratio_census[key],
            }
            for key in sorted(ratio_census)
        ],
        "terminal_outcome_counts": _outcome_histogram(eligible),
        "ratio_observation_terminal_outcome_counts": _outcome_histogram(observed),
        "summaries": {
            "partition_ratio_max": _summary(
                record["partition_ratio_max"] for record in observed
            ),
            "partition_ratio_geomean": _summary(
                record["partition_ratio_geomean"] for record in observed
            ),
        },
    }


def _config_summary(matrix, tasks, label, search):
    tuple_counts = defaultdict(Counter)
    tuple_values = []
    unobserved = Counter()
    source_counts = Counter()
    partition = {"raw-complete-log": [], "certified-resource-prefix": []}
    partition_observed = {"raw-complete-log": [], "certified-resource-prefix": []}
    complete_pairs = []

    for task in tasks:
        record = matrix[(label, task)]
        direct = _direct_observation(record, label, task)
        structural = _partition_observation(record, label, task)
        if direct["kind"] == "tuple":
            key = tuple(direct[field] for field in ("W", "A", "V", "T", "U"))
            tuple_counts[key][direct["source"]] += 1
            source_counts[direct["source"]] += 1
            tuple_values.append(direct)
        elif direct["kind"] == "unobserved":
            unobserved[direct["reason"]] += 1

        if structural is not None:
            stratum = structural["stratum"]
            partition[stratum].append(record)
            if structural["ratios"] is not None:
                partition_observed[stratum].append(record)
                if stratum == "raw-complete-log" and direct["kind"] == "tuple":
                    complete_pairs.append((direct, structural["ratios"]))

    eligible = 0 if label == full.BLIND else len(tasks)
    observed = len(tuple_values)
    if label != full.BLIND and observed + sum(unobserved.values()) != eligible:
        raise AnalysisError("{} direct-tuple census does not conserve cells".format(label))
    tuple_rows = []
    for key in sorted(tuple_counts):
        sources = tuple_counts[key]
        tuple_rows.append(
            {
                "W": key[0],
                "A": key[1],
                "V": key[2],
                "T": key[3],
                "U": key[4],
                "count": sum(sources.values()),
                "completed_construction_cells": sources["completed-construction"],
                "heuristic_event_only_resource_prefix_cells": sources[
                    "heuristic-event-only-resource-prefix"
                ],
            }
        )
    summaries = {
        field: _summary(item[field] for item in tuple_values)
        for field in ("W", "A", "V", "T", "U")
    }
    for name, numerator in (
        ("U_over_W", "U"),
        ("A_over_W", "A"),
        ("V_over_W", "V"),
        ("T_over_W", "T"),
    ):
        summaries[name] = _summary(
            item[numerator] / item["W"] for item in tuple_values
        )

    raw_summary = _stratum_summary(
        partition["raw-complete-log"], partition_observed["raw-complete-log"]
    )
    if len(complete_pairs) != len(partition_observed["raw-complete-log"]):
        raise AnalysisError(
            "{} raw-complete ratio observation lacks its direct W/U tuple".format(
                label
            )
        )
    paired_census = Counter(
        (
            item[0]["W"],
            item[0]["U"],
            item[1]["max"],
            item[1]["geomean"],
        )
        for item in complete_pairs
    )
    widths = [item[0]["W"] for item in complete_pairs]
    uppers = [item[0]["U"] for item in complete_pairs]
    maxima = [item[1]["max"] for item in complete_pairs]
    geomeans = [item[1]["geomean"] for item in complete_pairs]
    raw_summary["paired_direct_tuple_and_ratio_cells"] = len(complete_pairs)
    raw_summary["paired_census_unit"] = (
        "one-raw-complete-cell-with-direct-tuple-and-partition-ratios"
    )
    raw_summary["paired_W_U_partition_ratio_census"] = [
        {
            "W": key[0],
            "U": key[1],
            "partition_ratio_max": key[2],
            "partition_ratio_geomean": key[3],
            "count": paired_census[key],
        }
        for key in sorted(paired_census)
    ]
    raw_summary["cross_task_descriptive_confounded_correlations"] = {
        "method": "Spearman-average-ranks-for-ties",
        "interpretation": "descriptive-cross-task-confounded-no-inference",
        "W_vs_partition_ratio_max": spearman_average_ties(widths, maxima),
        "U_vs_partition_ratio_max": spearman_average_ties(uppers, maxima),
        "W_vs_partition_ratio_geomean": spearman_average_ties(widths, geomeans),
        "U_vs_partition_ratio_geomean": spearman_average_ties(uppers, geomeans),
    }
    prefix_summary = _stratum_summary(
        partition["certified-resource-prefix"],
        partition_observed["certified-resource-prefix"],
    )
    prefix_summary["interpretation"] = (
        "censored-observed-prefix-ratios-only; no rank correlations"
    )

    return {
        "label": label,
        "search": search,
        "cell_count": len(tasks),
        "direct_W_A_V_T_U": {
            "eligible_cells": eligible,
            "observed_cells": observed,
            "unobserved_cells": eligible - observed,
            "observation_source_counts": {
                "completed_construction": source_counts["completed-construction"],
                "heuristic_event_only_resource_prefix": source_counts[
                    "heuristic-event-only-resource-prefix"
                ],
            },
            "unobserved_reason_counts": {
                "construction_fallback": unobserved["construction-fallback"],
                "presearch_outcome": unobserved["presearch-outcome"],
                "resource_before_direct_tuple": unobserved[
                    "resource-before-direct-tuple"
                ],
                "selector_width_only_resource_prefix": unobserved[
                    "selector-width-only-resource-prefix"
                ],
            },
            "tuple_census": tuple_rows,
            "summaries": summaries,
        },
        "partition_ratios": {
            "raw_complete_logs_not_necessarily_complete_searches": raw_summary,
            "certified_resource_prefixes": prefix_summary,
        },
    }


def _validate_candidate_pool(candidates, pool_hash, prefix):
    common = full.heldout.common
    if type(candidates) is not list or not 1 <= len(candidates) <= len(SELECTOR_SOURCES):
        _fail(prefix, "certified selector pool needs 1..5 candidates")
    for candidate in candidates:
        # The raw-log protocol fixes object insertion order, but Lab writes the
        # fetched properties as canonical JSON and therefore alphabetizes the
        # nested candidate keys.  Preserve the exact field-set check here, then
        # restore protocol order before reusing the raw-log semantic validator.
        # The pool hash itself is over sort-key canonical JSON, so this
        # normalization cannot change its identity.
        if type(candidate) is not dict or set(candidate) != set(
            common.PDB_SELECTOR_RECORD_KEYS
        ):
            _fail(prefix, "invalid selector candidate: candidate field set changed")
        ordered_candidate = {
            key: candidate[key] for key in common.PDB_SELECTOR_RECORD_KEYS
        }
        error = common._validate_selector_record(ordered_candidate, "candidate")
        if error:
            _fail(prefix, "invalid selector candidate: {}".format(error))
    patterns = [full.canonical_json(candidate["pattern"]) for candidate in candidates]
    if len(patterns) != len(set(patterns)):
        _fail(prefix, "selector candidates are not deduplicated by pattern")
    sources = [source for candidate in candidates for source in candidate["sources"]]
    if sorted(sources) != sorted(SELECTOR_SOURCES) or len(sources) != len(set(sources)):
        _fail(prefix, "selector candidate provenance does not partition five sources")
    first_positions = [SELECTOR_SOURCES.index(candidate["sources"][0]) for candidate in candidates]
    if first_positions != sorted(first_positions):
        _fail(prefix, "selector candidate order violates the fixed source order")
    recomputed = common.pdb_selector_pool_sha256(candidates)
    if pool_hash != recomputed:
        _fail(prefix, "selector pool hash disagrees with candidate payload")
    omitted = {"cofactor_width_budget", "feasible", "rejection_reason"}
    normalized = [
        {key: value for key, value in candidate.items() if key not in omitted}
        for candidate in candidates
    ]
    return full.canonical_json(normalized)


def _candidate_pool_summary(matrix, tasks, contract):
    selector_labels = [
        label for label, _search in contract["configs"] if label in SELECTOR_LABELS
    ]
    pools = {}
    task_hashes = defaultdict(set)
    certified_trace_cells = 0
    for task in tasks:
        for label in selector_labels:
            record = matrix[(label, task)]
            certified = record.get("pdb_selector_trace_certified")
            pool_hash = record.get("pdb_selector_pool_sha256")
            if certified is not True:
                if pool_hash is not None:
                    _fail(_prefix(label, task), "uncertified selector trace has a pool hash")
                continue
            if record.get("pdb_selector_trace_complete") is not True:
                _fail(_prefix(label, task), "certified selector trace is not complete")
            if record.get("pdb_selector_validation_error") is not None:
                _fail(_prefix(label, task), "certified selector trace has a diagnostic")
            if type(pool_hash) is not str or not SHA256_RE.fullmatch(pool_hash):
                _fail(_prefix(label, task), "selector pool hash is not a SHA-256")
            candidates = record.get("pdb_selector_candidates")
            payload = _validate_candidate_pool(candidates, pool_hash, _prefix(label, task))
            key = (task, pool_hash)
            if key in pools and pools[key]["payload"] != payload:
                _fail(_prefix(label, task), "same task/pool hash has different candidates")
            pools.setdefault(key, {"payload": payload, "candidates": copy.deepcopy(candidates)})
            task_hashes[task].add(pool_hash)
            certified_trace_cells += 1
    if any(len(hashes) > 1 for hashes in task_hashes.values()):
        task = next(task for task, hashes in task_hashes.items() if len(hashes) > 1)
        _fail("selector {}:{}".format(*task), "same task has multiple certified pool hashes")

    candidate_census = defaultdict(lambda: [0, 0])
    candidate_count_hist = Counter()
    source_status = {source: Counter() for source in SELECTOR_SOURCES}
    widths = []
    uppers = []
    materialized_candidates = 0
    unmaterialized_candidates = 0
    materialized_sources = 0
    unmaterialized_sources = 0
    for key in sorted(pools, key=lambda item: (item[0][0], item[0][1], item[1])):
        candidates = pools[key]["candidates"]
        candidate_count_hist[len(candidates)] += 1
        for candidate in candidates:
            width = candidate["cofactor_width"]
            upper = candidate["width_upper_bound"]
            sources = candidate["sources"]
            if width is None and upper is None:
                unmaterialized_candidates += 1
                unmaterialized_sources += len(sources)
                for source in sources:
                    source_status[source]["unmaterialized"] += 1
                continue
            if type(width) is not int or type(upper) is not int or not (1 <= width <= upper):
                raise AnalysisError("materialized selector candidate has invalid W/U")
            materialized_candidates += 1
            materialized_sources += len(sources)
            widths.append(width)
            uppers.append(upper)
            candidate_census[(width, upper)][0] += 1
            candidate_census[(width, upper)][1] += len(sources)
            for source in sources:
                source_status[source]["materialized"] += 1

    observed_pools = len(pools)
    if materialized_candidates + unmaterialized_candidates != sum(
        count * candidates for candidates, count in candidate_count_hist.items()
    ):
        raise AnalysisError("selector candidate-pool census does not conserve candidates")
    if materialized_sources + unmaterialized_sources != observed_pools * len(SELECTOR_SOURCES):
        raise AnalysisError("selector candidate-pool census does not conserve sources")
    source_rows = []
    for source in SELECTOR_SOURCES:
        counts = source_status[source]
        if counts["materialized"] + counts["unmaterialized"] != observed_pools:
            raise AnalysisError("selector source status does not conserve task pools")
        source_rows.append(
            {
                "source": source,
                "materialized_task_pools": counts["materialized"],
                "unmaterialized_task_pools": counts["unmaterialized"],
            }
        )
    return {
        "unit": "one-deduplicated-candidate-per-task-and-pool-hash",
        "selector_config_labels": selector_labels,
        "eligible_tasks": len(tasks) if selector_labels else 0,
        "certified_trace_cells": certified_trace_cells,
        "observed_unique_task_pool_hashes": observed_pools,
        "observed_tasks": len(task_hashes),
        "unobserved_tasks": (len(tasks) - len(task_hashes)) if selector_labels else 0,
        "repeated_certified_trace_cells_deduplicated": certified_trace_cells - observed_pools,
        "distinct_pool_hashes": len({key[1] for key in pools}),
        "deduplicated_candidate_counts": {
            "materialized": materialized_candidates,
            "unmaterialized": unmaterialized_candidates,
            "total": materialized_candidates + unmaterialized_candidates,
        },
        "represented_source_counts": {
            "materialized": materialized_sources,
            "unmaterialized": unmaterialized_sources,
            "total": materialized_sources + unmaterialized_sources,
        },
        "deduplicated_candidates_per_pool_histogram": [
            {"candidate_count": count, "task_pools": candidate_count_hist[count]}
            for count in sorted(candidate_count_hist)
        ],
        "source_status_counts": source_rows,
        "materialized_W_U_census": [
            {
                "W": width,
                "U": upper,
                "deduplicated_candidate_count": candidate_census[(width, upper)][0],
                "represented_source_count": candidate_census[(width, upper)][1],
            }
            for width, upper in sorted(candidate_census)
        ],
        "materialized_summaries": {
            "W": _summary(widths),
            "U": _summary(uppers),
            "U_over_W": _summary(
                upper / width for width, upper in zip(widths, uppers)
            ),
        },
    }


def _validate_matrix(matrix, tasks, contract):
    labels = [label for label, _search in contract["configs"]]
    if len(tasks) != len(set(tasks)) or len(labels) != len(set(labels)):
        raise AnalysisError("structural input task/config identities are not unique")
    expected = {(label, task) for label in labels for task in tasks}
    if set(matrix) != expected:
        raise AnalysisError("structural matrix is not the exact config-by-task product")
    for label, task in expected:
        record = matrix[(label, task)]
        if not isinstance(record, dict):
            _fail(_prefix(label, task), "record is not an object")
        if record.get("algorithm") != label:
            _fail(_prefix(label, task), "algorithm identity changed")
        if record.get("domain") != task[0] or record.get("problem") != task[1]:
            _fail(_prefix(label, task), "task identity changed")
        code = record.get("planner_exit_code")
        if type(code) is not int or code not in full.TERMINAL_OUTCOME_CODES:
            _fail(_prefix(label, task), "terminal outcome is not protocol-recognized")


def build_diagnostic(
    matrix,
    tasks,
    contract,
    artifact_sha256,
    protocol_revision,
    properties_sha256,
):
    """Build diagnostics from records already accepted by canonical P6 gates."""
    _validate_matrix(matrix, tasks, contract)
    configs = [
        _config_summary(matrix, tasks, label, search)
        for label, search in contract["configs"]
    ]
    result = {
        "schema": SCHEMA,
        "analysis_protocol": PROTOCOL,
        "decision_label": DECISION_LABEL,
        "specification_boundary": SPECIFICATION_BOUNDARY,
        "input_identity": {
            "selection_artifact_sha256": artifact_sha256,
            "full_protocol_revision": protocol_revision,
            "properties_canonical_sha256": properties_sha256,
            "task_count": len(tasks),
            "config_count": len(contract["configs"]),
            "cell_count": len(matrix),
            "config_order": [label for label, _search in contract["configs"]],
        },
        "interpretation": {
            "role": "secondary-descriptive-structural-diagnostic",
            "theorem_validation": False,
            "causal_claims": "none",
            "inferential_statistics": "none",
            "cross_task_correlations": "descriptive-and-confounded",
            "raw_metrics_complete_meaning": (
                "complete-WBH-log-not-necessarily-complete-search; inspect terminal-outcome-counts"
            ),
            "resource_prefix_ratios": "censored-observed-prefix-summaries-only",
            "paired_source_layer_or_slice_sizes_available": False,
            "blind_normalized_effort": "omitted-no-new-paired-performance-estimand",
        },
        "configs": configs,
        "selector_candidate_pool": _candidate_pool_summary(matrix, tasks, contract),
    }
    try:
        return json.loads(full.canonical_json(result))
    except full.AnalysisError as err:
        raise AnalysisError(str(err)) from err


def analyze(records, tasks, contract, artifact_sha256, protocol_revision):
    """Apply the canonical cell gate, then construct the secondary result."""
    matrix = full.validate_records(
        records, tasks, contract, artifact_sha256, protocol_revision
    )
    return build_diagnostic(
        matrix,
        tasks,
        contract,
        artifact_sha256,
        protocol_revision,
        full.logical_properties_sha256(records),
    )


def _self_test():
    tied = spearman_average_ties([1, 2, 2, 4], [4, 1, 1, 0])
    if tied["n"] != 4 or tied["coefficient"] is None:
        raise AssertionError("tie-aware Spearman self-test failed")
    constant = spearman_average_ties([1, 1], [2, 3])
    if constant != {
        "n": 2,
        "coefficient": None,
        "null_reason": "zero-rank-variance",
    }:
        raise AssertionError("zero-variance Spearman self-test failed")
    if _summary([0.0, 1.0])["observed"] != 2:
        raise AssertionError("zero-valued ratio self-test failed")
    return {"schema": SCHEMA, "status": "pass", "checks": 3}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run secondary structural diagnostics on exact accepted P6 inputs."
    )
    parser.add_argument(
        "properties",
        nargs="?",
        help="Lab properties JSON, eval directory, tar archive, or '-' for stdin.",
    )
    parser.add_argument(
        "--selection",
        type=Path,
        help="Exact selection artifact v3 used for the P6 launch.",
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test and (args.properties is not None or args.selection is not None):
        parser.error("--self-test does not accept input paths")
    if not args.self_test and (args.properties is None or args.selection is None):
        parser.error("ordinary analysis requires properties and --selection")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        print(full.canonical_json(_self_test()))
        return 0
    artifact, artifact_sha256 = full.load_selection_artifact(args.selection)
    protocol_revision = full.require_reviewed_pins(artifact_sha256)
    contract = full.validate_selection_artifact(artifact)
    full.validate_runner_contract(contract, expected_artifact_sha256=artifact_sha256)
    tasks, _screen_excluded, _domains = full.load_and_validate_tasks()
    records = full.load_properties(args.properties)
    result = analyze(
        records, tasks, contract, artifact_sha256, protocol_revision
    )
    print(full.canonical_json(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AnalysisError, full.AnalysisError, RuntimeError) as err:
        print("analysis error: {}".format(err), file=sys.stderr)
        sys.exit(2)
