#!/usr/bin/env python3
"""Fail-closed post-hoc diagnostics for the focused PDB cap-grid census.

This consumer is deliberately separate from the prospective analysis.  It
reads the preserved logical properties, verifies their frozen digest and
record-shape manifest, and reports theorem-guided descriptive diagnostics.
It performs no hypothesis tests, interval estimation, or population
generalization.  The prospective analyzer and its frozen artifact are never
modified or relaxed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import stat
import statistics
import tempfile
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path


class AnalysisError(RuntimeError):
    """The frozen inputs or a requested diagnostic failed validation."""


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_OUTPUT = (
    SCRIPT_DIR
    / "artifacts"
    / "pdb-cap-grid-posthoc-review"
    / "analysis-v1.json"
)
DEVELOPMENT_MANIFEST = SCRIPT_DIR / "selector_pilot_suite.txt"
PROSPECTIVE_ARTIFACT = (
    SCRIPT_DIR / "artifacts" / "pdb-cap-grid-focused-full" / "analysis-v1.json"
)

ANALYSIS_SCHEMA = "symbolic-search-heuristics/pdb-cap-grid-posthoc-review/v1"
ANALYSIS_PROTOCOL = "pdb-cap-grid-posthoc-review-analysis-v1"
ROLE = "post-hoc-theorem-guided-descriptive"
NO_INFERENCE_POLICY = "fixed-census-description-only-no-inference/v1"
CLAIM_GUIDANCE = "theorem-guided-diagnostics/v1"
OPERATIONAL_ELIGIBILITY = "same-pair-complete-certified-schema-v2-image-metrics/v1"
FINITE_CAP_DEFINITION = "cap-selected-kappa-is-nonnegative/v1"
EXACT_ENDPOINT_DEFINITION = "cap-selected-kappa-equals-minus-one/v1"
MATERIAL_TRANSFORM_DEFINITION = (
    "kappa-below-raw-max-strict-finite-sum-and-representation-reduction/v1"
)
SELECTED_COEFFICIENT_FORMULA = "c=2*V_selected*W_selected"
SELECTED_COEFFICIENT_ELIGIBILITY = "complete-certified-selector-trace-per-config/v1"
COVERAGE_LODO_ESTIMAND = "cap-minus-exact-equal-domain-macro-coverage/v1"
NODE_LODO_ESTIMAND = (
    "cap-over-exact-total-expanded-bdd-nodes-on-complete-certified-pairs/v1"
)
PARTITION_ELIGIBILITY = "finite-nonnegative-observed-partition_ratio_max/v1"

EXPECTED_ANALYSIS_SHA256 = (
    "195c209a8ba34a89c98fd0920c4f58753635cd3f375f6424ca49da017effc59d"
)
EXPECTED_PROPERTIES_CANONICAL_SHA256 = (
    "bddc69b2eedcc1442e6a42517d4d294e9a6ae0ab7dbf4aebc49714b152c0f215"
)
EXPECTED_RECORD_SCHEMA_MANIFEST_SHA256 = (
    "e944922a633c08594e48a2c667bf84cd35d6b8121d85d2b1c672aed4abea533e"
)
EXPECTED_PROSPECTIVE_ARTIFACT_SHA256 = (
    "fb8db53b4f5eea7306961351d110b0d331abc87fa2a31242321de429f32ad60a"
)
EXPECTED_PROSPECTIVE_SCHEMA = (
    "symbolic-search-heuristics/pdb-cap-grid-focused-full/v1"
)
EXPECTED_PROPERTIES_PROTOCOL = "pdb-cap-grid-focused-full-evaluation-v1"
EXPECTED_PROPERTIES_ANALYSIS_PROTOCOL = "pdb-cap-grid-focused-full-analysis-v1"
EXPECTED_PROTOCOL_REVISION = "0fa5ecc1d93884e9cf35b433bacfe684765ba112"
EXPECTED_PLANNER_REVISION = "e04d56cc61d00c954f2369e9fb74bd469277d52e"
EXPECTED_PLANNER_BINARY_SHA256 = (
    "77cf4950563be2d2a60aded13783a3ffe26c0c8391ac9d626f3bd618231941fa"
)
EXPECTED_PLANNER_PREPROCESS_SHA256 = (
    "fc3233bfd260210cf4d0cce11146fe6f3198820d6e19a8b56740c1240039378b"
)
EXPECTED_PROSPECTIVE_JOB_SHA256 = (
    "24efc07fc6fdfd19d2a7532d4e717f072b1f5a2e893b946b529aedf4158ebc81"
)
EXPECTED_TASK_MANIFEST_SHA256 = (
    "295bff030c51eaf39871714335ff9cb945ce39ebc556774eeb3bfad112681345"
)
EXPECTED_PRIMARY_TASK_MANIFEST_SHA256 = (
    "1e126791b438d903cb6adcc441391b92d76a7e14cf46f6a89465a066823a986f"
)
EXPECTED_DEVELOPMENT_MANIFEST_SHA256 = (
    "3195dac7e62a34e5ac4cbeb715ab7f9b99e2ee64341082dd7d718ea2820751ca"
)
EXPECTED_OPTION_MATRIX_SHA256 = (
    "94238d64a699142ef81cc4a35489467af8b78dcdf46973536556eb7e3f6b6f78"
)

TASKS = 1377
PRIMARY_TASKS = 1327
DOMAINS = 46
CONFIG_COUNT = 5
CELLS = TASKS * CONFIG_COUNT
WIDTH_BUDGET = 8
MAX_PROPERTIES_BYTES = 512 * 1024 * 1024
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

CONFIGS = (
    "blind_fw",
    "ms_exact",
    "pdb_cegar_b100k",
    "pdb_selector_k8",
    "pdb_cap_grid_k8",
)
EXACT = "pdb_selector_k8"
CAP = "pdb_cap_grid_k8"

SCOPE_ROLES = {
    "primary": "primary-development-complement-post-hoc-description",
    "all_tasks": "all-task-census-post-hoc-description",
}
EXPECTED_SELECTOR_TRACE_COUNTS = {
    "primary": {EXACT: 1308, CAP: 1306},
    "all_tasks": {EXACT: 1358, CAP: 1356},
}

SCHEMA_V2_CONVENTIONS = {
    "wbh_schema_version": 2,
    "node_count_convention": "inner_nodes_per_piece",
    "image_count_convention": "per_piece_attempted_completed",
    "expansion_count_convention": "completed_with_attempts",
}
SCHEMA_V2_INTEGER_METRICS = (
    "expanded_bdd_nodes",
    "expanded_bdd_pieces",
    "attempted_bdd_nodes",
    "attempted_bdd_pieces",
    "bucket_expansions",
    "bucket_expansion_attempts",
    "image_events",
    "bucket_images",
    "image_source_buckets",
    "image_source_pieces",
    "image_calls_attempted",
    "image_calls_completed",
    "batched_images",
)
SCHEMA_V2_REAL_METRICS = (
    "expanded_states",
    "attempted_states",
    "image_time",
)

STATIC_RECORD_PINS = {
    "protocol": EXPECTED_PROPERTIES_PROTOCOL,
    "analysis_protocol": EXPECTED_PROPERTIES_ANALYSIS_PROTOCOL,
    "protocol_revision": EXPECTED_PROTOCOL_REVISION,
    "planner_revision": EXPECTED_PLANNER_REVISION,
    "planner_binary_sha256": EXPECTED_PLANNER_BINARY_SHA256,
    "planner_preprocess_sha256": EXPECTED_PLANNER_PREPROCESS_SHA256,
    "prospective_start_job_sha256": EXPECTED_PROSPECTIVE_JOB_SHA256,
    "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
    "primary_task_manifest_sha256": EXPECTED_PRIMARY_TASK_MANIFEST_SHA256,
    "development_task_manifest_sha256": EXPECTED_DEVELOPMENT_MANIFEST_SHA256,
    "option_matrix_sha256": EXPECTED_OPTION_MATRIX_SHA256,
    "task_count": TASKS,
    "primary_task_count": PRIMARY_TASKS,
    "domain_count": DOMAINS,
    "primary_domain_count": DOMAINS,
    "config_count": CONFIG_COUNT,
    "declared_run_count": CELLS,
    "config_order": list(CONFIGS),
}

EXACT_ENDPOINT_IDENTITY_FIELDS = (
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
)


def canonical_json(value):
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as err:
        raise AnalysisError("value is not canonical finite JSON: {}".format(err)) from err


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_json(value):
    return sha256_bytes(canonical_json(value).encode("ascii"))


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AnalysisError("duplicate JSON key {!r}".format(key))
        result[key] = value
    return result


def parse_json_bytes(raw, source, require_canonical=False):
    if not isinstance(raw, bytes):
        raise AnalysisError("{} must be bytes".format(source))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as err:
        raise AnalysisError("{} is not UTF-8 JSON".format(source)) from err

    def reject_constant(token):
        raise AnalysisError("{} contains nonfinite constant {}".format(source, token))

    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=reject_constant,
        )
    except AnalysisError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as err:
        raise AnalysisError("{} is invalid JSON: {}".format(source, err)) from err
    if require_canonical:
        expected = canonical_json(value).encode("ascii") + b"\n"
        if raw != expected:
            raise AnalysisError(
                "{} is not exact canonical ASCII JSON plus one newline".format(source)
            )
    return value


def read_regular(path, maximum):
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as err:
        raise AnalysisError("cannot inspect {}: {}".format(path, err)) from err
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise AnalysisError("{} must be a regular non-symlink file".format(path))
    if info.st_size > maximum:
        raise AnalysisError("{} exceeds the {}-byte limit".format(path, maximum))
    try:
        return path.read_bytes()
    except OSError as err:
        raise AnalysisError("cannot read {}: {}".format(path, err)) from err


def _same(actual, expected):
    return type(actual) is type(expected) and actual == expected


def _require_sha256(value, label, expected=None):
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        raise AnalysisError("{} is not a lowercase SHA-256".format(label))
    if expected is not None and value != expected:
        raise AnalysisError("{} changed".format(label))
    return value


def _require_int(value, label, minimum=None):
    if type(value) is not int or (minimum is not None and value < minimum):
        suffix = "" if minimum is None else " >= {}".format(minimum)
        raise AnalysisError("{} must be an integer{}".format(label, suffix))
    return value


def _number(value, label, minimum=None):
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise AnalysisError("{} must be a finite JSON number".format(label))
    if minimum is not None and value < minimum:
        raise AnalysisError("{} must be >= {}".format(label, minimum))
    return value


def _manifest_digest(tasks):
    payload = "".join("{}:{}\n".format(*task) for task in tasks).encode("utf-8")
    return sha256_bytes(payload)


def load_properties(path):
    raw = read_regular(path, MAX_PROPERTIES_BYTES)
    root = parse_json_bytes(raw, "properties")
    if not isinstance(root, dict):
        raise AnalysisError("properties must be a JSON object keyed by run id")
    records = []
    for source_key, record in root.items():
        if type(source_key) is not str or not source_key:
            raise AnalysisError("properties contain an invalid run id")
        if not isinstance(record, dict):
            raise AnalysisError("properties run {!r} is not an object".format(source_key))
        if "_source_key" in record:
            raise AnalysisError("properties record already contains _source_key")
        copied = dict(record)
        copied["_source_key"] = source_key
        records.append(copied)

    logical = [{k: v for k, v in record.items() if k != "_source_key"} for record in records]
    logical.sort(
        key=lambda record: (
            record.get("algorithm", ""),
            record.get("domain", ""),
            record.get("problem", ""),
            canonical_json(record),
        )
    )
    digest = sha256_json(logical)
    _require_sha256(
        digest,
        "logical properties digest",
        EXPECTED_PROPERTIES_CANONICAL_SHA256,
    )
    return records, digest


def record_schema_manifest(records):
    counts = Counter(
        (record.get("algorithm"), tuple(sorted(k for k in record if k != "_source_key")))
        for record in records
    )
    manifest = [
        {"algorithm": algorithm, "keys": list(keys), "count": count}
        for (algorithm, keys), count in sorted(counts.items())
    ]
    digest = sha256_json(manifest)
    _require_sha256(
        digest,
        "record schema manifest digest",
        EXPECTED_RECORD_SCHEMA_MANIFEST_SHA256,
    )
    return manifest, digest


def load_development_tasks():
    raw = read_regular(DEVELOPMENT_MANIFEST, 1024 * 1024)
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as err:
        raise AnalysisError("development manifest is not UTF-8") from err
    tasks = []
    for line_number, raw_line in enumerate(text.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(":")
        if len(parts) != 2 or not all(parts):
            raise AnalysisError(
                "invalid development task on line {}".format(line_number)
            )
        tasks.append(tuple(parts))
    if len(tasks) != 50 or len(set(tasks)) != 50:
        raise AnalysisError("development manifest must contain 50 unique tasks")
    _require_sha256(
        _manifest_digest(tasks),
        "logical development manifest digest",
        EXPECTED_DEVELOPMENT_MANIFEST_SHA256,
    )
    return tasks


def validate_records(records):
    if len(records) != CELLS:
        raise AnalysisError("properties contain {} records, expected {}".format(len(records), CELLS))
    _, schema_digest = record_schema_manifest(records)
    matrix = {}
    tasks = set()
    for record in records:
        source = record["_source_key"]
        label = record.get("algorithm")
        domain = record.get("domain")
        problem = record.get("problem")
        if label not in CONFIGS:
            raise AnalysisError("{} has an unknown algorithm".format(source))
        if type(domain) is not str or not domain or type(problem) is not str or not problem:
            raise AnalysisError("{} has an invalid task identity".format(source))
        task = (domain, problem)
        key = (label, task)
        if key in matrix:
            raise AnalysisError("duplicate matrix cell {} {}:{}".format(label, *task))
        matrix[key] = record
        tasks.add(task)
        if record.get("id") != [label, domain, problem]:
            raise AnalysisError("{} has a mismatching id".format(source))
        if record.get("coverage") not in (0, 1) or type(record.get("coverage")) is not int:
            raise AnalysisError("{} has invalid coverage".format(source))
        for field, expected in STATIC_RECORD_PINS.items():
            if not _same(record.get(field), expected):
                raise AnalysisError("{} changed static field {}".format(source, field))

    ordered_tasks = sorted(tasks)
    if len(ordered_tasks) != TASKS or len({task[0] for task in tasks}) != DOMAINS:
        raise AnalysisError("task population dimensions changed")
    _require_sha256(
        _manifest_digest(ordered_tasks),
        "task manifest digest reconstructed from properties",
        EXPECTED_TASK_MANIFEST_SHA256,
    )
    if len(matrix) != CELLS:
        raise AnalysisError("matrix is incomplete")
    for task in ordered_tasks:
        for label in CONFIGS:
            if (label, task) not in matrix:
                raise AnalysisError("missing matrix cell {} {}:{}".format(label, *task))

    development = set(load_development_tasks())
    if not development.issubset(tasks):
        raise AnalysisError("development manifest is not a subset of the census")
    primary = [task for task in ordered_tasks if task not in development]
    if len(primary) != PRIMARY_TASKS or len({task[0] for task in primary}) != DOMAINS:
        raise AnalysisError("primary population dimensions changed")
    _require_sha256(
        _manifest_digest(primary),
        "primary task manifest digest reconstructed from properties",
        EXPECTED_PRIMARY_TASK_MANIFEST_SHA256,
    )
    return matrix, ordered_tasks, primary, schema_digest


def validate_prospective_artifact():
    raw = read_regular(PROSPECTIVE_ARTIFACT, MAX_ARTIFACT_BYTES)
    digest = sha256_bytes(raw)
    _require_sha256(
        digest,
        "prospective analysis artifact digest",
        EXPECTED_PROSPECTIVE_ARTIFACT_SHA256,
    )
    sidecar_path = PROSPECTIVE_ARTIFACT.with_name(PROSPECTIVE_ARTIFACT.name + ".sha256")
    sidecar = read_regular(sidecar_path, 1024)
    expected_sidecar = "{}  {}\n".format(digest, PROSPECTIVE_ARTIFACT.name).encode("ascii")
    if sidecar != expected_sidecar:
        raise AnalysisError("prospective artifact sidecar changed")
    artifact = parse_json_bytes(raw, "prospective analysis artifact", require_canonical=True)
    if not isinstance(artifact, dict) or artifact.get("schema") != EXPECTED_PROSPECTIVE_SCHEMA:
        raise AnalysisError("prospective analysis schema changed")
    execution = artifact.get("execution")
    if not isinstance(execution, dict):
        raise AnalysisError("prospective artifact has no execution binding")
    expected = {
        "properties_canonical_sha256": EXPECTED_PROPERTIES_CANONICAL_SHA256,
        "protocol": EXPECTED_PROPERTIES_PROTOCOL,
        "protocol_revision": EXPECTED_PROTOCOL_REVISION,
        "planner_revision": EXPECTED_PLANNER_REVISION,
        "planner_binary_sha256": EXPECTED_PLANNER_BINARY_SHA256,
        "planner_preprocess_sha256": EXPECTED_PLANNER_PREPROCESS_SHA256,
        "prospective_start_job_sha256": EXPECTED_PROSPECTIVE_JOB_SHA256,
        "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
        "primary_task_manifest_sha256": EXPECTED_PRIMARY_TASK_MANIFEST_SHA256,
        "option_matrix_sha256": EXPECTED_OPTION_MATRIX_SHA256,
        "cell_count": CELLS,
        "all_cells_validated": True,
    }
    for field, value in expected.items():
        if not _same(execution.get(field), value):
            raise AnalysisError("prospective artifact execution field {} changed".format(field))
    return digest


def trace_complete(record):
    return (
        record.get("pdb_selector_trace_complete") is True
        and record.get("pdb_selector_trace_certified") is True
        and record.get("pdb_selector_validation_error") is None
        and isinstance(record.get("pdb_selector_selected"), dict)
        and isinstance(record.get("pdb_selector_candidates"), list)
    )


def certified_image_cell(record):
    return (
        record.get("raw_metrics_complete") is True
        and record.get("piece_metrics_certified") is True
        and record.get("metrics_validation_error") is None
        and all(_same(record.get(field), expected) for field, expected in SCHEMA_V2_CONVENTIONS.items())
        and all(type(record.get(field)) is int and record[field] >= 0 for field in SCHEMA_V2_INTEGER_METRICS)
        and all(
            type(record.get(field)) in (int, float)
            and math.isfinite(float(record[field]))
            and record[field] >= 0
            for field in SCHEMA_V2_REAL_METRICS
        )
    )


def _validate_selected(record, label, task):
    selected = record["pdb_selector_selected"]
    prefix = "{} {}:{} selected".format(label, *task)
    for field in ("abstract_states", "finite_sum", "finite_count", "dead_count"):
        _require_int(selected.get(field), "{} {}".format(prefix, field), 0)
    width = _require_int(selected.get("cofactor_width"), "{} cofactor_width".format(prefix), 1)
    if width > WIDTH_BUDGET:
        raise AnalysisError("{} exceeds the selected width budget".format(prefix))
    if type(selected.get("initial_dead_end")) is not bool:
        raise AnalysisError("{} has invalid initial_dead_end".format(prefix))
    if selected["initial_dead_end"]:
        if selected.get("initial_h") is not None:
            raise AnalysisError("{} dead endpoint must have null initial_h".format(prefix))
    else:
        _require_int(selected.get("initial_h"), "{} initial_h".format(prefix), 0)
    if not isinstance(selected.get("pattern"), list) or not isinstance(selected.get("sources"), list):
        raise AnalysisError("{} has invalid pattern/sources".format(prefix))
    if record.get("cofactor_width") != width:
        raise AnalysisError("{} disagrees with final cofactor width".format(prefix))
    if label == EXACT:
        values = _require_int(record.get("num_values"), "{} final num_values".format(prefix), 1)
    elif label == CAP:
        values = _require_int(selected.get("transformed_num_values"), "{} transformed_num_values".format(prefix), 1)
        if record.get("num_values") != values:
            raise AnalysisError("{} disagrees with final num_values".format(prefix))
        cap = _require_int(selected.get("value_cap"), "{} value_cap".format(prefix), -1)
        if cap < -1:
            raise AnalysisError("{} has invalid value_cap".format(prefix))
    else:
        raise AnalysisError("selected heuristic requested for non-selector")
    return selected, values, width


def _summary(values):
    values = list(values)
    if not values:
        return {
            "count": 0,
            "minimum": None,
            "median": None,
            "nearest_rank_p95": None,
            "maximum": None,
        }
    ordered = sorted(values)
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return {
        "count": len(ordered),
        "minimum": ordered[0],
        "median": statistics.median(ordered),
        "nearest_rank_p95": ordered[rank - 1],
        "maximum": ordered[-1],
    }


def _fraction_payload(value):
    if not isinstance(value, Fraction):
        value = Fraction(value)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }


def _extreme_payload(values, choose):
    extreme = choose(value for _, value in values)
    return {
        "omitted_domains": sorted(domain for domain, value in values if value == extreme),
        "ratio": _fraction_payload(extreme),
    }


def _paired_traces(matrix, tasks):
    pairs = []
    for task in tasks:
        exact = matrix[(EXACT, task)]
        cap = matrix[(CAP, task)]
        if not (trace_complete(exact) and trace_complete(cap)):
            continue
        exact_hash = _require_sha256(
            exact.get("pdb_selector_pool_sha256"),
            "{}:{} exact raw-pool digest".format(*task),
        )
        cap_hash = _require_sha256(
            cap.get("pdb_selector_raw_pool_sha256"),
            "{}:{} cap raw-pool digest".format(*task),
        )
        if exact_hash != cap_hash:
            raise AnalysisError("same-K raw selector pool differs on {}:{}".format(*task))
        exact_selected, _, _ = _validate_selected(exact, EXACT, task)
        cap_selected, _, _ = _validate_selected(cap, CAP, task)
        endpoint = "exact_endpoint" if cap_selected["value_cap"] == -1 else "finite_cap"
        pairs.append(
            {
                "task": task,
                "exact": exact,
                "cap": cap,
                "exact_selected": exact_selected,
                "cap_selected": cap_selected,
                "endpoint": endpoint,
            }
        )
    return pairs


def _coverage_summary(pairs):
    counts = Counter()
    for pair in pairs:
        exact = pair["exact"]["coverage"]
        cap = pair["cap"]["coverage"]
        if cap == 1 and exact == 0:
            counts["cap_wins"] += 1
        elif cap == 0 and exact == 1:
            counts["cap_losses"] += 1
        elif cap == exact == 1:
            counts["both_solved"] += 1
        else:
            counts["both_unsolved"] += 1
    return {
        "task_pairs": len(pairs),
        "cap_wins": counts["cap_wins"],
        "cap_losses": counts["cap_losses"],
        "both_solved": counts["both_solved"],
        "both_unsolved": counts["both_unsolved"],
        "wins_minus_losses": counts["cap_wins"] - counts["cap_losses"],
    }


def _operational_metric(pairs, field):
    eligible = [
        pair
        for pair in pairs
        if certified_image_cell(pair["exact"]) and certified_image_cell(pair["cap"])
    ]
    exact_values = [pair["exact"][field] for pair in eligible]
    cap_values = [pair["cap"][field] for pair in eligible]
    if field == "expanded_bdd_nodes":
        exact_total = sum(exact_values)
        cap_total = sum(cap_values)
    else:
        exact_total = math.fsum(exact_values)
        cap_total = math.fsum(cap_values)
    if not eligible or exact_total <= 0:
        raise AnalysisError("{} has no positive operational reference total".format(field))
    comparisons = Counter(
        "cap_lower" if cap < exact else "equal" if cap == exact else "cap_higher"
        for cap, exact in zip(cap_values, exact_values)
    )
    return {
        "eligible_pair_count": len(eligible),
        "cap_total": cap_total,
        "exact_total": exact_total,
        "cap_over_exact": cap_total / exact_total,
        "cap_lower": comparisons["cap_lower"],
        "equal": comparisons["equal"],
        "cap_higher": comparisons["cap_higher"],
    }


def _operational_summary(pairs):
    result = {
        "eligibility": OPERATIONAL_ELIGIBILITY,
        "expanded_bdd_nodes": _operational_metric(pairs, "expanded_bdd_nodes"),
        "image_time_seconds": _operational_metric(pairs, "image_time"),
    }
    counts = {
        result[metric]["eligible_pair_count"]
        for metric in ("expanded_bdd_nodes", "image_time_seconds")
    }
    if len(counts) != 1:
        raise AnalysisError("operational metric denominators disagree")
    return result


def _validate_operational_conservation(overall, strata):
    for metric in ("expanded_bdd_nodes", "image_time_seconds"):
        whole = overall[metric]
        parts = [stratum[metric] for stratum in strata]
        for field in ("eligible_pair_count", "cap_lower", "equal", "cap_higher"):
            if whole[field] != sum(part[field] for part in parts):
                raise AnalysisError(
                    "{} {} does not conserve across trace strata".format(metric, field)
                )
        for field in ("cap_total", "exact_total"):
            if not math.isclose(
                whole[field],
                math.fsum(part[field] for part in parts),
                rel_tol=1e-14,
                abs_tol=1e-12,
            ):
                raise AnalysisError(
                    "{} {} does not conserve across trace strata".format(metric, field)
                )


def _finite_cap_diagnostics(pairs):
    raw_widths = []
    material = 0
    cap_counts = Counter()
    coefficient_counts = Counter()
    coefficient_caps = defaultdict(Counter)
    weak_fields = (
        ("cofactor_width", "raw_cofactor_width"),
        ("width_upper_bound", "raw_width_upper_bound"),
        ("add_nodes", "raw_add_nodes"),
        ("num_terminals", "raw_num_terminals"),
        ("transformed_num_values", "raw_num_values"),
        ("initial_h", "raw_initial_h"),
    )
    for pair in pairs:
        selected = pair["cap_selected"]
        task = pair["task"]
        prefix = "{}:{} finite-cap selection".format(*task)
        cap = _require_int(selected.get("value_cap"), "{} value_cap".format(prefix), 0)
        raw_width = _require_int(selected.get("raw_cofactor_width"), "{} raw W".format(prefix), 1)
        raw_widths.append(raw_width)
        cap_counts[cap] += 1
        coefficient = 2 * WIDTH_BUDGET * min(WIDTH_BUDGET, cap + 1)
        coefficient_counts[coefficient] += 1
        coefficient_caps[coefficient][cap] += 1

        for left, right in weak_fields:
            _require_int(selected.get(left), "{} {}".format(prefix, left), 0)
            _require_int(selected.get(right), "{} {}".format(prefix, right), 0)
            if selected[left] > selected[right]:
                raise AnalysisError("{} violates {} <= {}".format(prefix, left, right))
        for left, right in (("dead_count", "raw_dead_count"), ("finite_count", "raw_finite_count")):
            _require_int(selected.get(right), "{} {}".format(prefix, right), 0)
            if selected[left] != selected[right]:
                raise AnalysisError("{} changed {}".format(prefix, left))
        raw_sum = _require_int(selected.get("raw_finite_sum"), "{} raw finite sum".format(prefix), 0)
        raw_max = _require_int(selected.get("raw_max_finite_value"), "{} raw max".format(prefix), 0)
        if not (
            selected["finite_sum"] < raw_sum
            and cap < raw_max
            and raw_width > WIDTH_BUDGET
            and (
                selected["cofactor_width"] < selected["raw_cofactor_width"]
                or selected["add_nodes"] < selected["raw_add_nodes"]
                or selected["num_terminals"] < selected["raw_num_terminals"]
                or selected["transformed_num_values"] < selected["raw_num_values"]
            )
        ):
            raise AnalysisError("{} is not a material finite-value transform".format(prefix))
        material += 1

    universal = [
        {
            "coefficient": coefficient,
            "selected_count": coefficient_counts[coefficient],
            "selected_cap_counts": {
                str(cap): count for cap, count in sorted(coefficient_caps[coefficient].items())
            },
        }
        for coefficient in sorted(coefficient_counts)
    ]
    return {
        "selected_count": len(pairs),
        "selected_cap_histogram": {str(cap): count for cap, count in sorted(cap_counts.items())},
        "selected_raw_W": _summary(raw_widths),
        "material_transform": {
            "checked": len(pairs),
            "material": material,
            "violations": 0,
            "invariant": True,
            "definition": MATERIAL_TRANSFORM_DEFINITION,
        },
        "cap_specific_universal_coefficient": {
            "formula": "2*K*min(K,kappa+1)",
            "K": WIDTH_BUDGET,
            "counts": universal,
        },
    }


def _exact_endpoint_invariant(pairs):
    raw_identity_fields = (
        ("cofactor_width", "raw_cofactor_width"),
        ("width_upper_bound", "raw_width_upper_bound"),
        ("add_nodes", "raw_add_nodes"),
        ("num_terminals", "raw_num_terminals"),
        ("transformed_num_values", "raw_num_values"),
        ("finite_sum", "raw_finite_sum"),
        ("finite_count", "raw_finite_count"),
        ("dead_count", "raw_dead_count"),
        ("initial_h", "raw_initial_h"),
        ("initial_dead_end", "raw_initial_dead_end"),
    )
    for pair in pairs:
        task = pair["task"]
        exact = pair["exact_selected"]
        cap = pair["cap_selected"]
        if any(not _same(cap.get(field), exact.get(field)) for field in EXACT_ENDPOINT_IDENTITY_FIELDS):
            raise AnalysisError("exact-endpoint selected identity differs on {}:{}".format(*task))
        if any(not _same(cap.get(left), cap.get(right)) for left, right in raw_identity_fields):
            raise AnalysisError("exact endpoint changes raw values on {}:{}".format(*task))
    return {
        "checked": len(pairs),
        "selected_heuristic_identity_mismatches": 0,
        "selected_heuristic_identity_invariant": True,
        "transformed_vs_raw_identity_mismatches": 0,
        "transformed_vs_raw_identity_invariant": True,
        "identity_fields": list(EXACT_ENDPOINT_IDENTITY_FIELDS),
    }


def _initial_h_summary(pairs):
    counts = Counter()
    for pair in pairs:
        exact = pair["exact_selected"]
        cap = pair["cap_selected"]
        if exact["initial_dead_end"] or cap["initial_dead_end"]:
            continue
        relation = "strict_higher" if cap["initial_h"] > exact["initial_h"] else "equal" if cap["initial_h"] == exact["initial_h"] else "lower"
        counts[relation] += 1
    if counts["lower"]:
        raise AnalysisError("cap-aware selected initial h is lower on a non-dead pair")
    return {
        "non_dead_pairs": sum(counts.values()),
        "cap_strict_higher": counts["strict_higher"],
        "equal": counts["equal"],
        "cap_lower": counts["lower"],
        "no_cap_lower_invariant": True,
    }


def _selector_coefficients(matrix, tasks):
    result = {}
    for label in (EXACT, CAP):
        values = []
        for task in tasks:
            record = matrix[(label, task)]
            if not trace_complete(record):
                continue
            _, selected_values, selected_width = _validate_selected(record, label, task)
            values.append(2 * selected_values * selected_width)
        result[label] = _summary(values)
    return {
        "formula": SELECTED_COEFFICIENT_FORMULA,
        "eligibility": SELECTED_COEFFICIENT_ELIGIBILITY,
        "by_selector": result,
    }


def _coverage_lodo(matrix, tasks):
    by_domain = defaultdict(list)
    for task in tasks:
        by_domain[task[0]].append(task)
    domain_deltas = {}
    for domain, domain_tasks in by_domain.items():
        wins = sum(matrix[(CAP, task)]["coverage"] - matrix[(EXACT, task)]["coverage"] for task in domain_tasks)
        domain_deltas[domain] = Fraction(wins, len(domain_tasks))
    base = sum(domain_deltas.values(), Fraction()) / len(domain_deltas)
    lodo = [
        (domain, (sum(domain_deltas.values(), Fraction()) - delta) / (len(domain_deltas) - 1))
        for domain, delta in domain_deltas.items()
    ]
    minimum = _extreme_payload(lodo, min)
    maximum = _extreme_payload(lodo, max)
    return {
        "estimand": COVERAGE_LODO_ESTIMAND,
        "base": _fraction_payload(base),
        "omitted_domain_replicates": len(lodo),
        "minimum": minimum,
        "maximum": maximum,
        "range_width": _fraction_payload(
            Fraction(maximum["ratio"]["numerator"], maximum["ratio"]["denominator"])
            - Fraction(minimum["ratio"]["numerator"], minimum["ratio"]["denominator"])
        ),
    }


def _node_lodo(matrix, tasks):
    pairs = []
    for task in tasks:
        exact = matrix[(EXACT, task)]
        cap = matrix[(CAP, task)]
        if certified_image_cell(exact) and certified_image_cell(cap):
            pairs.append((task, exact["expanded_bdd_nodes"], cap["expanded_bdd_nodes"]))
    exact_total = sum(exact for _, exact, _ in pairs)
    cap_total = sum(cap for _, _, cap in pairs)
    if not pairs or exact_total <= 0:
        raise AnalysisError("node LODO has no positive reference total")
    by_domain = defaultdict(lambda: [0, 0])
    for task, exact, cap in pairs:
        by_domain[task[0]][0] += exact
        by_domain[task[0]][1] += cap
    scope_domains = sorted({task[0] for task in tasks})
    lodo = []
    for domain in scope_domains:
        exact_domain, cap_domain = by_domain[domain]
        denominator = exact_total - exact_domain
        if denominator <= 0:
            raise AnalysisError("node LODO has nonpositive reference without {}".format(domain))
        lodo.append((domain, Fraction(cap_total - cap_domain, denominator)))
    minimum = _extreme_payload(lodo, min)
    maximum = _extreme_payload(lodo, max)
    return {
        "estimand": NODE_LODO_ESTIMAND,
        "eligible_pair_count": len(pairs),
        "base": _fraction_payload(Fraction(cap_total, exact_total)),
        "omitted_domain_replicates": len(lodo),
        "minimum": minimum,
        "maximum": maximum,
        "range_width": _fraction_payload(
            Fraction(maximum["ratio"]["numerator"], maximum["ratio"]["denominator"])
            - Fraction(minimum["ratio"]["numerator"], minimum["ratio"]["denominator"])
        ),
    }


def _partition_ratio_summaries(matrix, tasks):
    result = {}
    for label in CONFIGS:
        values = []
        for task in tasks:
            value = matrix[(label, task)].get("partition_ratio_max")
            if value is None:
                continue
            values.append(_number(value, "{} {}:{} partition_ratio_max".format(label, *task), 0))
        result[label] = _summary(values)
    return {
        "eligibility": PARTITION_ELIGIBILITY,
        "by_config": result,
    }


def _scope_analysis(matrix, tasks, scope_key):
    pairs = _paired_traces(matrix, tasks)
    finite = [pair for pair in pairs if pair["endpoint"] == "finite_cap"]
    exact_endpoint = [pair for pair in pairs if pair["endpoint"] == "exact_endpoint"]
    if len(finite) + len(exact_endpoint) != len(pairs):
        raise AnalysisError("trace endpoint partition is incomplete")

    paired_operational = _operational_summary(pairs)
    finite_operational = _operational_summary(finite)
    exact_operational = _operational_summary(exact_endpoint)
    _validate_operational_conservation(
        paired_operational,
        (finite_operational, exact_operational),
    )
    coefficients = _selector_coefficients(matrix, tasks)
    for label, expected in EXPECTED_SELECTOR_TRACE_COUNTS[scope_key].items():
        if coefficients["by_selector"][label]["count"] != expected:
            raise AnalysisError(
                "{} {} selector-trace denominator changed".format(scope_key, label)
            )

    return {
        "role": SCOPE_ROLES[scope_key],
        "population": {
            "tasks": len(tasks),
            "domains": len({task[0] for task in tasks}),
        },
        "paired_trace_summary": {
            "complete_certified_pairs": len(pairs),
            "identical_raw_pool_pairs": len(pairs),
            "coverage": _coverage_summary(pairs),
            "operational": paired_operational,
        },
        "trace_strata": {
            "finite_cap": {
                "definition": FINITE_CAP_DEFINITION,
                "trace_pairs": len(finite),
                "coverage": _coverage_summary(finite),
                "operational": finite_operational,
                "selected_transform": _finite_cap_diagnostics(finite),
            },
            "exact_endpoint": {
                "definition": EXACT_ENDPOINT_DEFINITION,
                "trace_pairs": len(exact_endpoint),
                "coverage": _coverage_summary(exact_endpoint),
                "operational": exact_operational,
                "selected_identity": _exact_endpoint_invariant(exact_endpoint),
            },
        },
        "selected_initial_h_on_non_dead_pairs": _initial_h_summary(pairs),
        "selected_certificate_coefficient": coefficients,
        "leave_one_domain_out": {
            "coverage": _coverage_lodo(matrix, tasks),
            "expanded_bdd_nodes": _node_lodo(matrix, tasks),
        },
        "partition_ratio_max": _partition_ratio_summaries(matrix, tasks),
    }


def make_analysis(matrix, all_tasks, primary_tasks, properties_digest, schema_digest, prospective_digest):
    return {
        "schema": ANALYSIS_SCHEMA,
        "analysis_protocol": ANALYSIS_PROTOCOL,
        "role": ROLE,
        "claim_policy": {
            "status": "post-hoc",
            "guidance": CLAIM_GUIDANCE,
            "inference": NO_INFERENCE_POLICY,
            "confirmatory_or_prospective": False,
        },
        "input_binding": {
            "properties_canonical_sha256": properties_digest,
            "record_schema_manifest_sha256": schema_digest,
            "prospective_analysis_artifact": {
                "schema": EXPECTED_PROSPECTIVE_SCHEMA,
                "sha256": prospective_digest,
            },
            "execution": {
                "protocol": EXPECTED_PROPERTIES_PROTOCOL,
                "analysis_protocol": EXPECTED_PROPERTIES_ANALYSIS_PROTOCOL,
                "protocol_revision": EXPECTED_PROTOCOL_REVISION,
                "planner_revision": EXPECTED_PLANNER_REVISION,
                "planner_binary_sha256": EXPECTED_PLANNER_BINARY_SHA256,
                "planner_preprocess_sha256": EXPECTED_PLANNER_PREPROCESS_SHA256,
                "prospective_start_job_sha256": EXPECTED_PROSPECTIVE_JOB_SHA256,
                "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
                "primary_task_manifest_sha256": EXPECTED_PRIMARY_TASK_MANIFEST_SHA256,
                "development_task_manifest_sha256": EXPECTED_DEVELOPMENT_MANIFEST_SHA256,
                "option_matrix_sha256": EXPECTED_OPTION_MATRIX_SHA256,
                "cells": CELLS,
            },
        },
        "diagnostics": {
            "primary": _scope_analysis(
                matrix,
                primary_tasks,
                "primary",
            ),
            "all_tasks": _scope_analysis(
                matrix,
                all_tasks,
                "all_tasks",
            ),
        },
        "inference": {
            "confidence_intervals": None,
            "hypothesis_tests": None,
            "p_values": None,
            "population_generalization": False,
            "policy": NO_INFERENCE_POLICY,
        },
    }


def artifact_bytes(analysis):
    return canonical_json(analysis).encode("ascii") + b"\n"


def _atomic_write(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.is_symlink():
        raise AnalysisError("refusing to replace symlink {}".format(path))
    descriptor, temporary = tempfile.mkstemp(prefix=".{}-".format(path.name), dir=str(path.parent))
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def write_or_check(analysis, output, check):
    raw = artifact_bytes(analysis)
    digest = sha256_bytes(raw)
    if EXPECTED_ANALYSIS_SHA256 != "TO_BE_PINNED" and digest != EXPECTED_ANALYSIS_SHA256:
        raise AnalysisError("post-hoc analysis digest changed: {}".format(digest))
    sidecar = "{}  {}\n".format(digest, Path(output).name).encode("ascii")
    sidecar_path = Path(output).with_name(Path(output).name + ".sha256")
    if check:
        if read_regular(output, MAX_ARTIFACT_BYTES) != raw:
            raise AnalysisError("post-hoc analysis artifact is stale")
        if read_regular(sidecar_path, 1024) != sidecar:
            raise AnalysisError("post-hoc analysis sidecar is stale")
    else:
        _atomic_write(output, raw)
        _atomic_write(sidecar_path, sidecar)
    return digest


def self_test():
    assert _summary([1, 2, 3, 4]) == {
        "count": 4,
        "minimum": 1,
        "median": 2.5,
        "nearest_rank_p95": 4,
        "maximum": 4,
    }
    assert _fraction_payload(Fraction(1, 8))["value"] == 0.125
    assert 2 * WIDTH_BUDGET * min(WIDTH_BUDGET, 4 + 1) == 80
    assert EXPECTED_SELECTOR_TRACE_COUNTS["primary"] == {
        EXACT: 1308,
        CAP: 1306,
    }

    def metric(count, cap_total, exact_total, lower, equal, higher):
        return {
            "eligible_pair_count": count,
            "cap_total": cap_total,
            "exact_total": exact_total,
            "cap_over_exact": cap_total / exact_total,
            "cap_lower": lower,
            "equal": equal,
            "cap_higher": higher,
        }

    strata = [
        {
            "expanded_bdd_nodes": metric(2, 8, 10, 1, 1, 0),
            "image_time_seconds": metric(2, 4.0, 5.0, 1, 1, 0),
        },
        {
            "expanded_bdd_nodes": metric(1, 3, 3, 0, 1, 0),
            "image_time_seconds": metric(1, 2.0, 2.0, 0, 1, 0),
        },
    ]
    overall = {
        "expanded_bdd_nodes": metric(3, 11, 13, 1, 2, 0),
        "image_time_seconds": metric(3, 6.0, 7.0, 1, 2, 0),
    }
    _validate_operational_conservation(overall, strata)
    nonconserving = json.loads(canonical_json(strata))
    nonconserving[0]["expanded_bdd_nodes"]["cap_total"] += 1
    try:
        _validate_operational_conservation(overall, nonconserving)
    except AnalysisError:
        pass
    else:
        raise AssertionError("nonconserving operational strata were accepted")
    try:
        parse_json_bytes(b'{"a":1,"a":2}', "synthetic duplicate")
    except AnalysisError:
        pass
    else:
        raise AssertionError("duplicate JSON key was accepted")
    try:
        parse_json_bytes(b'{"a":NaN}', "synthetic nonfinite")
    except AnalysisError:
        pass
    else:
        raise AssertionError("nonfinite JSON was accepted")
    print("self-test passed")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--properties", type=Path, help="preserved Lab properties JSON")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check", action="store_true", help="verify the pinned output without writing")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test and (args.properties is not None or args.check):
        parser.error("--self-test cannot be combined with --properties or --check")
    if not args.self_test and args.properties is None:
        parser.error("--properties is required outside --self-test")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    prospective_digest = validate_prospective_artifact()
    records, properties_digest = load_properties(args.properties)
    matrix, all_tasks, primary_tasks, schema_digest = validate_records(records)
    analysis = make_analysis(
        matrix,
        all_tasks,
        primary_tasks,
        properties_digest,
        schema_digest,
        prospective_digest,
    )
    digest = write_or_check(analysis, args.output, args.check)
    action = "verified" if args.check else "wrote"
    print("{} {} (sha256 {})".format(action, args.output, digest))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AnalysisError as err:
        print("error: {}".format(err), file=os.sys.stderr)
        raise SystemExit(2)
