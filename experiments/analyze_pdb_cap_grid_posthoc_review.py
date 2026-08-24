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
RAW_CAP_COEFFICIENT_FORMULA = "c=2*V*W"
RAW_CAP_COEFFICIENT_ELIGIBILITY = (
    "same-cap-selected-pdb-raw-versus-transformed-finite-cap-trace/v1"
)
COMPLETED_BUCKET_DEFINITION = (
    "completed-single-piece-bucket-equals-completed-image-call/v1"
)
NODE_PER_BUCKET_ESTIMAND = (
    "cap-over-exact-ratio-of-total-expanded-bdd-nodes-per-completed-bucket/v1"
)
IMAGE_TIME_PER_BUCKET_ESTIMAND = (
    "cap-over-exact-ratio-of-total-image-seconds-per-completed-bucket/v1"
)
IMAGE_TIME_EXACT_ARITHMETIC = (
    "sum-of-shortest-roundtrip-decimal-json-numbers/v1"
)
METRICS_VALIDATION_PROTOCOL = "wbh-exact-schema-semantic-v3"
OUTCOME_RECONCILIATION_PROTOCOL = (
    "direct-search-raw-effective-plan-reconciliation/v1"
)
TRIPLE_SOLVED_EFFORT_ELIGIBILITY = (
    "complete-identical-pool-selector-traces-three-way-certified-solved-"
    "cost-reconciled-single-piece-buckets-schema-v2/v1"
)
TRIPLE_SOLVED_EFFORT_ESTIMAND = (
    "ratio-of-total-certified-wbh-solution-cutoff-effort-on-three-way-solved/v1"
)
FINITE_EFFORT_LODO_ESTIMANDS = {
    "cap_over_blind": (
        "cap-over-blind-total-certified-effort-on-finite-cap-three-way-solved/v1"
    ),
    "exact_over_blind": (
        "exact-over-blind-total-certified-effort-on-finite-cap-three-way-solved/v1"
    ),
    "cap_over_exact": (
        "cap-over-exact-total-certified-effort-on-finite-cap-three-way-solved/v1"
    ),
}
COVERAGE_LODO_ESTIMAND = "cap-minus-exact-equal-domain-macro-coverage/v1"
NODE_LODO_ESTIMAND = (
    "cap-over-exact-total-expanded-bdd-nodes-on-complete-certified-pairs/v1"
)
PARTITION_ELIGIBILITY = "finite-nonnegative-observed-partition_ratio_max/v1"

EXPECTED_ANALYSIS_SHA256 = (
    "211ba15a3b15235175d5f98ec4d374dada5d00cacf8997a5f919543041a06312"
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
BLIND = "blind_fw"

SCOPE_ROLES = {
    "primary": "primary-development-complement-post-hoc-description",
    "all_tasks": "all-task-census-post-hoc-description",
}
EXPECTED_SELECTOR_TRACE_COUNTS = {
    "primary": {EXACT: 1308, CAP: 1306},
    "all_tasks": {EXACT: 1358, CAP: 1356},
}
EXPECTED_TRIPLE_SOLVED_EFFORT_COUNTS = {
    "primary": {"overall": 575, "finite_cap": 393, "exact_endpoint": 182},
    "all_tasks": {"overall": 602, "finite_cap": 419, "exact_endpoint": 183},
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
COMPLETED_BUCKET_IDENTITY_FIELDS = (
    "expanded_bdd_pieces",
    "bucket_expansions",
    "bucket_expansion_attempts",
    "image_events",
    "bucket_images",
    "image_source_buckets",
    "image_source_pieces",
    "image_calls_attempted",
    "image_calls_completed",
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
        and record.get("metrics_validation_protocol")
        == METRICS_VALIDATION_PROTOCOL
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


def _fraction_from_payload(value, label):
    if not isinstance(value, dict):
        raise AnalysisError("{} must be a fraction object".format(label))
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    decimal = value.get("value")
    if type(numerator) is not int or type(denominator) is not int or denominator <= 0:
        raise AnalysisError("{} has invalid fraction integers".format(label))
    fraction = Fraction(numerator, denominator)
    if fraction.numerator != numerator or fraction.denominator != denominator:
        raise AnalysisError("{} fraction is not reduced".format(label))
    _number(decimal, "{} decimal".format(label))
    if not math.isclose(decimal, float(fraction), rel_tol=1e-14, abs_tol=1e-18):
        raise AnalysisError("{} decimal disagrees with its exact fraction".format(label))
    return fraction


def _fraction_summary(values):
    ordered = sorted(Fraction(value) for value in values)
    if not ordered:
        raise AnalysisError("exact fraction summary must not be empty")
    count = len(ordered)
    rank = max(1, math.ceil(0.95 * count))
    if count % 2:
        median = ordered[count // 2]
    else:
        median = (ordered[count // 2 - 1] + ordered[count // 2]) / 2
    return {
        "count": count,
        "minimum": _fraction_payload(ordered[0]),
        "median": _fraction_payload(median),
        "nearest_rank_p95": _fraction_payload(ordered[rank - 1]),
        "maximum": _fraction_payload(ordered[-1]),
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


def _completed_bucket_count(record, label):
    values = [record[field] for field in COMPLETED_BUCKET_IDENTITY_FIELDS]
    if record.get("expanded_buckets_single_piece") is not True:
        raise AnalysisError("{} does not certify single-piece expanded buckets".format(label))
    if record.get("batched_images") != 0 or len(set(values)) != 1:
        raise AnalysisError("{} does not identify completed buckets with image calls".format(label))
    count = values[0]
    if count == 0 and (record["expanded_bdd_nodes"] != 0 or record["image_time"] != 0):
        raise AnalysisError("{} has work without a completed bucket".format(label))
    return count


def _operational_pairs(pairs):
    eligible = []
    for pair in pairs:
        if not (
            certified_image_cell(pair["exact"])
            and certified_image_cell(pair["cap"])
        ):
            continue
        for side in ("exact", "cap"):
            _completed_bucket_count(
                pair[side],
                "{}:{} {}".format(*pair["task"], side),
            )
        eligible.append(pair)
    return eligible


def _comparison_counts(cap_values, exact_values):
    comparisons = Counter(
        "cap_lower" if cap < exact else "equal" if cap == exact else "cap_higher"
        for cap, exact in zip(cap_values, exact_values)
    )
    return {
        "cap_lower": comparisons["cap_lower"],
        "equal": comparisons["equal"],
        "cap_higher": comparisons["cap_higher"],
    }


def _operational_metric(eligible, field):
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
    result = {
        "eligible_pair_count": len(eligible),
        "cap_total": cap_total,
        "exact_total": exact_total,
        "cap_over_exact": cap_total / exact_total,
    }
    result.update(_comparison_counts(cap_values, exact_values))
    return result


def _completed_bucket_summary(eligible):
    exact_values = [
        _completed_bucket_count(pair["exact"], "exact completed bucket")
        for pair in eligible
    ]
    cap_values = [
        _completed_bucket_count(pair["cap"], "cap completed bucket")
        for pair in eligible
    ]
    exact_total = sum(exact_values)
    cap_total = sum(cap_values)
    if not eligible or exact_total <= 0 or cap_total <= 0:
        raise AnalysisError("completed buckets have no positive aggregate denominator")
    result = {
        "definition": COMPLETED_BUCKET_DEFINITION,
        "eligible_pair_count": len(eligible),
        "identity_checked_cells": 2 * len(eligible),
        "identity_violations": 0,
        "cap_total": cap_total,
        "exact_total": exact_total,
        "cap_over_exact": _fraction_payload(Fraction(cap_total, exact_total)),
    }
    result.update(_comparison_counts(cap_values, exact_values))
    return result


def _normalized_operational_metric(eligible, field, estimand):
    if field == "expanded_bdd_nodes":
        arithmetic = "exact-integer-ratio-of-totals/v1"
        exact_metrics = [Fraction(pair["exact"][field]) for pair in eligible]
        cap_metrics = [Fraction(pair["cap"][field]) for pair in eligible]
    elif field == "image_time":
        arithmetic = IMAGE_TIME_EXACT_ARITHMETIC
        exact_metrics = [Fraction(str(pair["exact"][field])) for pair in eligible]
        cap_metrics = [Fraction(str(pair["cap"][field])) for pair in eligible]
    else:
        raise AnalysisError("unsupported normalized operational metric {}".format(field))
    exact_buckets = [pair["exact"]["image_calls_completed"] for pair in eligible]
    cap_buckets = [pair["cap"]["image_calls_completed"] for pair in eligible]
    cap_total = sum(cap_metrics, Fraction())
    exact_total = sum(exact_metrics, Fraction())
    cap_bucket_total = sum(cap_buckets)
    exact_bucket_total = sum(exact_buckets)
    if cap_total <= 0 or exact_total <= 0 or cap_bucket_total <= 0 or exact_bucket_total <= 0:
        raise AnalysisError("{} has a nonpositive aggregate denominator".format(field))

    positive = []
    zero_counts = Counter()
    for cap_metric, exact_metric, cap_bucket, exact_bucket in zip(
        cap_metrics, exact_metrics, cap_buckets, exact_buckets
    ):
        if cap_bucket > 0 and exact_bucket > 0:
            positive.append((cap_metric / cap_bucket, exact_metric / exact_bucket))
        elif cap_bucket == 0 and exact_bucket == 0:
            zero_counts["both_zero"] += 1
        elif cap_bucket == 0:
            zero_counts["cap_only_zero"] += 1
        else:
            zero_counts["exact_only_zero"] += 1
    comparisons = _comparison_counts(
        [cap for cap, _ in positive],
        [exact for _, exact in positive],
    )
    zero_total = sum(zero_counts.values())
    result = {
        "estimand": estimand,
        "arithmetic": arithmetic,
        "eligible_pair_count": len(eligible),
        "positive_denominator_pair_count": len(positive),
        "zero_denominator_pair_count": zero_total,
        "zero_denominator_pairs": {
            "both_zero": zero_counts["both_zero"],
            "cap_only_zero": zero_counts["cap_only_zero"],
            "exact_only_zero": zero_counts["exact_only_zero"],
        },
        "cap_completed_bucket_total": cap_bucket_total,
        "exact_completed_bucket_total": exact_bucket_total,
        "cap_per_completed_bucket": _fraction_payload(cap_total / cap_bucket_total),
        "exact_per_completed_bucket": _fraction_payload(exact_total / exact_bucket_total),
        "cap_over_exact": _fraction_payload(
            (cap_total * exact_bucket_total) / (exact_total * cap_bucket_total)
        ),
    }
    if field == "expanded_bdd_nodes":
        result["cap_metric_total"] = cap_total.numerator
        result["exact_metric_total"] = exact_total.numerator
    else:
        result["cap_metric_total"] = _fraction_payload(cap_total)
        result["exact_metric_total"] = _fraction_payload(exact_total)
    result.update(comparisons)
    return result


def _validate_operational_summary_contract(operational):
    if operational.get("eligibility") != OPERATIONAL_ELIGIBILITY:
        raise AnalysisError("operational eligibility label changed")
    node_count = operational["expanded_bdd_nodes"]["eligible_pair_count"]
    if operational["image_time_seconds"]["eligible_pair_count"] != node_count:
        raise AnalysisError("operational metric denominators disagree")
    buckets = operational["completed_buckets"]
    if not (
        buckets.get("definition") == COMPLETED_BUCKET_DEFINITION
        and buckets.get("eligible_pair_count") == node_count
        and buckets.get("identity_checked_cells") == 2 * node_count
        and buckets.get("identity_violations") == 0
    ):
        raise AnalysisError("completed-bucket identity contract changed")
    if sum(buckets[field] for field in ("cap_lower", "equal", "cap_higher")) != node_count:
        raise AnalysisError("completed-bucket comparisons do not partition pairs")
    if _fraction_from_payload(
        buckets["cap_over_exact"], "completed-bucket ratio"
    ) != Fraction(buckets["cap_total"], buckets["exact_total"]):
        raise AnalysisError("completed-bucket ratio drifted")

    expected = (
        (
            "expanded_bdd_nodes_per_completed_bucket",
            NODE_PER_BUCKET_ESTIMAND,
            "exact-integer-ratio-of-totals/v1",
            "expanded_bdd_nodes",
        ),
        (
            "image_time_seconds_per_completed_bucket",
            IMAGE_TIME_PER_BUCKET_ESTIMAND,
            IMAGE_TIME_EXACT_ARITHMETIC,
            "image_time_seconds",
        ),
    )
    for key, estimand, arithmetic, old_key in expected:
        item = operational[key]
        if item.get("estimand") != estimand or item.get("arithmetic") != arithmetic:
            raise AnalysisError("{} semantic contract changed".format(key))
        if item.get("eligible_pair_count") != node_count:
            raise AnalysisError("{} denominator disagrees".format(key))
        zeros = item.get("zero_denominator_pairs")
        if not isinstance(zeros, dict) or sum(zeros.values()) != item.get(
            "zero_denominator_pair_count"
        ):
            raise AnalysisError("{} zero-denominator disclosure disagrees".format(key))
        if (
            item["positive_denominator_pair_count"]
            + item["zero_denominator_pair_count"]
            != node_count
            or sum(item[field] for field in ("cap_lower", "equal", "cap_higher"))
            != item["positive_denominator_pair_count"]
        ):
            raise AnalysisError("{} pairwise denominators disagree".format(key))
        if not (
            item["cap_completed_bucket_total"] == buckets["cap_total"]
            and item["exact_completed_bucket_total"] == buckets["exact_total"]
        ):
            raise AnalysisError("{} bucket totals disagree".format(key))
        if key.startswith("expanded"):
            cap_metric = Fraction(item["cap_metric_total"])
            exact_metric = Fraction(item["exact_metric_total"])
            if not (
                item["cap_metric_total"] == operational[old_key]["cap_total"]
                and item["exact_metric_total"] == operational[old_key]["exact_total"]
            ):
                raise AnalysisError("{} metric totals disagree".format(key))
        else:
            cap_metric = _fraction_from_payload(
                item["cap_metric_total"], "{} cap metric total".format(key)
            )
            exact_metric = _fraction_from_payload(
                item["exact_metric_total"], "{} exact metric total".format(key)
            )
            if not (
                math.isclose(
                    float(cap_metric), operational[old_key]["cap_total"], rel_tol=1e-14
                )
                and math.isclose(
                    float(exact_metric), operational[old_key]["exact_total"], rel_tol=1e-14
                )
            ):
                raise AnalysisError("{} metric totals disagree".format(key))
        cap_per = cap_metric / item["cap_completed_bucket_total"]
        exact_per = exact_metric / item["exact_completed_bucket_total"]
        if not (
            _fraction_from_payload(
                item["cap_per_completed_bucket"], "{} cap per bucket".format(key)
            )
            == cap_per
            and _fraction_from_payload(
                item["exact_per_completed_bucket"], "{} exact per bucket".format(key)
            )
            == exact_per
            and _fraction_from_payload(
                item["cap_over_exact"], "{} ratio".format(key)
            )
            == cap_per / exact_per
        ):
            raise AnalysisError("{} exact fraction drifted".format(key))


def _operational_summary(pairs):
    eligible = _operational_pairs(pairs)
    result = {
        "eligibility": OPERATIONAL_ELIGIBILITY,
        "expanded_bdd_nodes": _operational_metric(eligible, "expanded_bdd_nodes"),
        "image_time_seconds": _operational_metric(eligible, "image_time"),
        "completed_buckets": _completed_bucket_summary(eligible),
        "expanded_bdd_nodes_per_completed_bucket": _normalized_operational_metric(
            eligible,
            "expanded_bdd_nodes",
            NODE_PER_BUCKET_ESTIMAND,
        ),
        "image_time_seconds_per_completed_bucket": _normalized_operational_metric(
            eligible,
            "image_time",
            IMAGE_TIME_PER_BUCKET_ESTIMAND,
        ),
    }
    _validate_operational_summary_contract(result)
    return result


def _validate_operational_conservation(overall, strata):
    _validate_operational_summary_contract(overall)
    for stratum in strata:
        _validate_operational_summary_contract(stratum)
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
    bucket_whole = overall["completed_buckets"]
    bucket_parts = [stratum["completed_buckets"] for stratum in strata]
    for field in (
        "eligible_pair_count",
        "identity_checked_cells",
        "identity_violations",
        "cap_total",
        "exact_total",
        "cap_lower",
        "equal",
        "cap_higher",
    ):
        if bucket_whole[field] != sum(part[field] for part in bucket_parts):
            raise AnalysisError(
                "completed buckets {} do not conserve across trace strata".format(field)
            )
    for key in (
        "expanded_bdd_nodes_per_completed_bucket",
        "image_time_seconds_per_completed_bucket",
    ):
        whole = overall[key]
        parts = [stratum[key] for stratum in strata]
        for field in (
            "eligible_pair_count",
            "positive_denominator_pair_count",
            "zero_denominator_pair_count",
            "cap_completed_bucket_total",
            "exact_completed_bucket_total",
            "cap_lower",
            "equal",
            "cap_higher",
        ):
            if whole[field] != sum(part[field] for part in parts):
                raise AnalysisError(
                    "{} {} does not conserve across trace strata".format(key, field)
                )
        for field in ("both_zero", "cap_only_zero", "exact_only_zero"):
            if whole["zero_denominator_pairs"][field] != sum(
                part["zero_denominator_pairs"][field] for part in parts
            ):
                raise AnalysisError(
                    "{} zero-denominator counts do not conserve".format(key)
                )
        if key.startswith("expanded"):
            for field in ("cap_metric_total", "exact_metric_total"):
                if whole[field] != sum(part[field] for part in parts):
                    raise AnalysisError("{} {} does not conserve".format(key, field))
        else:
            for field in ("cap_metric_total", "exact_metric_total"):
                whole_fraction = _fraction_from_payload(
                    whole[field], "{} overall {}".format(key, field)
                )
                part_total = sum(
                    (
                        _fraction_from_payload(
                            part[field], "{} stratum {}".format(key, field)
                        )
                        for part in parts
                    ),
                    Fraction(),
                )
                if whole_fraction != part_total:
                    raise AnalysisError("{} {} does not conserve".format(key, field))


def _validate_exact_endpoint_operational_identity(operational):
    buckets = operational["completed_buckets"]
    nodes = operational["expanded_bdd_nodes"]
    normalized = operational["expanded_bdd_nodes_per_completed_bucket"]
    if not (
        buckets["cap_total"] == buckets["exact_total"]
        and buckets["cap_lower"] == buckets["cap_higher"] == 0
        and nodes["cap_total"] == nodes["exact_total"]
        and nodes["cap_lower"] == nodes["cap_higher"] == 0
        and _fraction_from_payload(
            normalized["cap_over_exact"], "exact-endpoint node/bucket identity"
        )
        == 1
        and normalized["cap_lower"] == normalized["cap_higher"] == 0
        and normalized["equal"] == normalized["positive_denominator_pair_count"]
    ):
        raise AnalysisError("exact-endpoint operational identity invariant failed")


def _finite_cap_diagnostics(pairs):
    raw_widths = []
    raw_coefficients = []
    capped_coefficients = []
    coefficient_ratios = []
    strict_value_reductions = 0
    strict_width_reductions = 0
    strict_coefficient_reductions = 0
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
        capped_width = _require_int(
            selected.get("cofactor_width"), "{} capped W".format(prefix), 1
        )
        raw_values = _require_int(
            selected.get("raw_num_values"), "{} raw V".format(prefix), 1
        )
        capped_values = _require_int(
            selected.get("transformed_num_values"), "{} capped V".format(prefix), 1
        )
        raw_coefficient = 2 * raw_values * raw_width
        capped_coefficient = 2 * capped_values * capped_width
        raw_coefficients.append(raw_coefficient)
        capped_coefficients.append(capped_coefficient)
        coefficient_ratios.append(Fraction(raw_coefficient, capped_coefficient))
        strict_value_reductions += capped_values < raw_values
        strict_width_reductions += capped_width < raw_width
        strict_coefficient_reductions += capped_coefficient < raw_coefficient
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

    if not (
        strict_value_reductions
        == strict_width_reductions
        == strict_coefficient_reductions
        == len(pairs)
    ):
        raise AnalysisError("finite-cap same-PDB coefficient compression is not strict")

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
        "same_pdb_raw_to_cap_coefficient": {
            "formula": RAW_CAP_COEFFICIENT_FORMULA,
            "eligibility": RAW_CAP_COEFFICIENT_ELIGIBILITY,
            "paired_count": len(pairs),
            "raw": _summary(raw_coefficients),
            "capped": _summary(capped_coefficients),
            "raw_over_capped": _fraction_summary(coefficient_ratios),
            "strict_value_reduction_count": strict_value_reductions,
            "strict_width_reduction_count": strict_width_reductions,
            "strict_coefficient_reduction_count": strict_coefficient_reductions,
        },
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


def _certified_solved_effort(record, label):
    if record.get("coverage") != 1:
        raise AnalysisError("{} is not solved".format(label))
    required = {
        "raw_metrics_complete": True,
        "piece_metrics_certified": True,
        "metrics_validation_error": None,
        "metrics_validation_protocol": METRICS_VALIDATION_PROTOCOL,
        "expanded_buckets_single_piece": True,
        "wbh_summary_solved": True,
        "wbh_solved_summary_certified": True,
        "plan_file_present": True,
        "plan_file_canonical": True,
        "plan_file_candidate_count": 1,
        "outcome_reconciliation_certified": True,
        "outcome_reconciliation_protocol": OUTCOME_RECONCILIATION_PROTOCOL,
    }
    for field, expected in required.items():
        if not _same(record.get(field), expected):
            raise AnalysisError("{} changed solved-effort field {}".format(label, field))
    for field, expected in SCHEMA_V2_CONVENTIONS.items():
        if not _same(record.get(field), expected):
            raise AnalysisError("{} changed solved-effort convention {}".format(label, field))
    effort = _require_int(record.get("effort"), "{} effort".format(label), 0)
    expanded = _require_int(
        record.get("expanded_bdd_nodes"), "{} expanded nodes".format(label), 0
    )
    expanded_pieces = _require_int(
        record.get("expanded_bdd_pieces"), "{} expanded pieces".format(label), 0
    )
    bucket_expansions = _require_int(
        record.get("bucket_expansions"), "{} bucket expansions".format(label), 0
    )
    if expanded_pieces != bucket_expansions:
        raise AnalysisError("{} does not identify one piece per expanded bucket".format(label))
    if effort != expanded:
        raise AnalysisError("{} effort differs from certified expanded nodes".format(label))
    cost_fields = (
        "solution_cost",
        "plan_file_cost",
        "run_log_plan_cost",
        "wbh_done_solution_cost",
    )
    costs = [
        _require_int(record.get(field), "{} {}".format(label, field), 0)
        for field in cost_fields
    ]
    if len(set(costs)) != 1:
        raise AnalysisError("{} has unreconciled solved costs".format(label))
    return {
        "cost": costs[0],
        "effort": effort,
        "equals_expanded_bdd_nodes": effort == expanded,
    }


def _triple_solved_effort(matrix, pairs):
    entries = []
    for pair in pairs:
        records = {
            "blind": matrix[(BLIND, pair["task"])],
            "exact": pair["exact"],
            "cap": pair["cap"],
        }
        if not all(record["coverage"] == 1 for record in records.values()):
            continue
        certified = {
            name: _certified_solved_effort(
                record,
                "{}:{} {}".format(*pair["task"], name),
            )
            for name, record in records.items()
        }
        if len({item["cost"] for item in certified.values()}) != 1:
            raise AnalysisError(
                "three-way solved costs disagree on {}:{}".format(*pair["task"])
            )
        entries.append(
            {
                "task": pair["task"],
                "effort": {name: item["effort"] for name, item in certified.items()},
                "expanded_node_equalities": sum(
                    item["equals_expanded_bdd_nodes"] for item in certified.values()
                ),
            }
        )
    if not entries:
        raise AnalysisError("three-way solved effort has no eligible tasks")
    totals = {
        name: sum(entry["effort"][name] for entry in entries)
        for name in ("blind", "exact", "cap")
    }
    if any(total <= 0 for total in totals.values()):
        raise AnalysisError("three-way solved effort has a nonpositive total")
    ratio_sides = {
        "cap_over_blind": ("cap", "blind"),
        "exact_over_blind": ("exact", "blind"),
        "cap_over_exact": ("cap", "exact"),
    }
    ratios = {}
    for key, (numerator, denominator) in ratio_sides.items():
        item = {
            "ratio": _fraction_payload(Fraction(totals[numerator], totals[denominator]))
        }
        comparisons = Counter(
            "numerator_lower"
            if entry["effort"][numerator] < entry["effort"][denominator]
            else "equal"
            if entry["effort"][numerator] == entry["effort"][denominator]
            else "numerator_higher"
            for entry in entries
        )
        item.update(
            {
                "numerator_lower": comparisons["numerator_lower"],
                "equal": comparisons["equal"],
                "numerator_higher": comparisons["numerator_higher"],
            }
        )
        ratios[key] = item
    result = {
        "eligibility": TRIPLE_SOLVED_EFFORT_ELIGIBILITY,
        "estimand": TRIPLE_SOLVED_EFFORT_ESTIMAND,
        "eligible_task_count": len(entries),
        "certified_cell_count": 3 * len(entries),
        "single_piece_bucket_certified_cell_count": 3 * len(entries),
        "cost_reconciled_task_count": len(entries),
        "effort_equals_expanded_bdd_nodes_cells": sum(
            entry["expanded_node_equalities"] for entry in entries
        ),
        "totals": totals,
        "ratios": ratios,
    }
    _validate_effort_summary_contract(result)
    return result, entries


def _validate_effort_summary_contract(summary):
    if not (
        summary.get("eligibility") == TRIPLE_SOLVED_EFFORT_ELIGIBILITY
        and summary.get("estimand") == TRIPLE_SOLVED_EFFORT_ESTIMAND
    ):
        raise AnalysisError("three-way effort semantic contract changed")
    count = _require_int(
        summary.get("eligible_task_count"), "three-way effort count", 1
    )
    if not (
        summary.get("certified_cell_count") == 3 * count
        and summary.get("single_piece_bucket_certified_cell_count") == 3 * count
        and summary.get("cost_reconciled_task_count") == count
    ):
        raise AnalysisError("three-way effort certification denominator changed")
    equality_count = _require_int(
        summary.get("effort_equals_expanded_bdd_nodes_cells"),
        "three-way effort/node equality count",
    )
    if equality_count != 3 * count:
        raise AnalysisError("three-way effort/node equality count changed")
    totals = summary.get("totals")
    if not isinstance(totals, dict) or set(totals) != {"blind", "exact", "cap"}:
        raise AnalysisError("three-way effort totals changed")
    for name in totals:
        _require_int(totals[name], "three-way {} effort".format(name), 1)
    expected = {
        "cap_over_blind": Fraction(totals["cap"], totals["blind"]),
        "exact_over_blind": Fraction(totals["exact"], totals["blind"]),
        "cap_over_exact": Fraction(totals["cap"], totals["exact"]),
    }
    ratios = summary.get("ratios")
    if not isinstance(ratios, dict) or set(ratios) != set(expected):
        raise AnalysisError("three-way effort ratios changed")
    for key, fraction in expected.items():
        item = ratios[key]
        if _fraction_from_payload(item.get("ratio"), "three-way {}".format(key)) != fraction:
            raise AnalysisError("three-way effort ratio drifted for {}".format(key))
        if sum(
            _require_int(item.get(field), "three-way {} {}".format(key, field))
            for field in ("numerator_lower", "equal", "numerator_higher")
        ) != count:
            raise AnalysisError("three-way effort comparisons disagree for {}".format(key))


def _validate_effort_conservation(overall, strata):
    _validate_effort_summary_contract(overall)
    for stratum in strata:
        _validate_effort_summary_contract(stratum)
    for field in (
        "eligible_task_count",
        "certified_cell_count",
        "single_piece_bucket_certified_cell_count",
        "cost_reconciled_task_count",
        "effort_equals_expanded_bdd_nodes_cells",
    ):
        if overall[field] != sum(stratum[field] for stratum in strata):
            raise AnalysisError("three-way effort {} does not conserve".format(field))
    for config in ("blind", "exact", "cap"):
        if overall["totals"][config] != sum(
            stratum["totals"][config] for stratum in strata
        ):
            raise AnalysisError("three-way {} effort does not conserve".format(config))
    for ratio in ("cap_over_blind", "exact_over_blind", "cap_over_exact"):
        for field in ("numerator_lower", "equal", "numerator_higher"):
            if overall["ratios"][ratio][field] != sum(
                stratum["ratios"][ratio][field] for stratum in strata
            ):
                raise AnalysisError(
                    "three-way {} {} does not conserve".format(ratio, field)
                )


def _validate_exact_endpoint_effort_identity(summary):
    ratio = summary["ratios"]["cap_over_exact"]
    if not (
        summary["totals"]["cap"] == summary["totals"]["exact"]
        and _fraction_from_payload(ratio["ratio"], "exact-endpoint effort identity") == 1
        and ratio["numerator_lower"] == ratio["numerator_higher"] == 0
        and ratio["equal"] == summary["eligible_task_count"]
    ):
        raise AnalysisError("exact-endpoint cap/exact effort identity failed")


def _effort_lodo(entries, tasks, ratio_key):
    numerator, denominator = {
        "cap_over_blind": ("cap", "blind"),
        "exact_over_blind": ("exact", "blind"),
        "cap_over_exact": ("cap", "exact"),
    }[ratio_key]
    totals = {
        name: sum(entry["effort"][name] for entry in entries)
        for name in ("blind", "exact", "cap")
    }
    by_domain = defaultdict(lambda: defaultdict(int))
    contributing_domains = set()
    for entry in entries:
        domain = entry["task"][0]
        contributing_domains.add(domain)
        for name, value in entry["effort"].items():
            by_domain[domain][name] += value
    lodo = []
    for domain in sorted({task[0] for task in tasks}):
        remaining_denominator = totals[denominator] - by_domain[domain][denominator]
        if remaining_denominator <= 0:
            raise AnalysisError("effort LODO has no denominator without {}".format(domain))
        lodo.append(
            (
                domain,
                Fraction(
                    totals[numerator] - by_domain[domain][numerator],
                    remaining_denominator,
                ),
            )
        )
    minimum = _extreme_payload(lodo, min)
    maximum = _extreme_payload(lodo, max)
    result = {
        "estimand": FINITE_EFFORT_LODO_ESTIMANDS[ratio_key],
        "eligible_task_count": len(entries),
        "contributing_domains": len(contributing_domains),
        "omitted_domain_replicates": len(lodo),
        "base": _fraction_payload(Fraction(totals[numerator], totals[denominator])),
        "minimum": minimum,
        "maximum": maximum,
        "range_width": _fraction_payload(
            Fraction(maximum["ratio"]["numerator"], maximum["ratio"]["denominator"])
            - Fraction(minimum["ratio"]["numerator"], minimum["ratio"]["denominator"])
        ),
    }
    _validate_effort_lodo(result, ratio_key, len(entries), len({task[0] for task in tasks}))
    return result


def _validate_effort_lodo(item, ratio_key, eligible_count, domain_count):
    if item.get("estimand") != FINITE_EFFORT_LODO_ESTIMANDS[ratio_key]:
        raise AnalysisError("finite effort LODO estimand changed")
    if not (
        item.get("eligible_task_count") == eligible_count
        and item.get("omitted_domain_replicates") == domain_count
        and 1 <= item.get("contributing_domains", 0) <= domain_count
    ):
        raise AnalysisError("finite effort LODO denominator changed")
    base = _fraction_from_payload(item.get("base"), "finite effort LODO base")
    minimum = _fraction_from_payload(
        item.get("minimum", {}).get("ratio"), "finite effort LODO minimum"
    )
    maximum = _fraction_from_payload(
        item.get("maximum", {}).get("ratio"), "finite effort LODO maximum"
    )
    width = _fraction_from_payload(
        item.get("range_width"), "finite effort LODO range width"
    )
    if not minimum <= base <= maximum or width != maximum - minimum:
        raise AnalysisError("finite effort LODO range is inconsistent")


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


def _node_lodo(operational_pairs, tasks):
    entries = [
        (
            pair["task"],
            pair["exact"]["expanded_bdd_nodes"],
            pair["cap"]["expanded_bdd_nodes"],
        )
        for pair in operational_pairs
    ]
    exact_total = sum(exact for _, exact, _ in entries)
    cap_total = sum(cap for _, _, cap in entries)
    if not entries or exact_total <= 0:
        raise AnalysisError("node LODO has no positive reference total")
    by_domain = defaultdict(lambda: [0, 0])
    for task, exact, cap in entries:
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
        "eligible_pair_count": len(entries),
        "cap_total": cap_total,
        "exact_total": exact_total,
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

    paired_operational_pairs = _operational_pairs(pairs)
    paired_operational = _operational_summary(pairs)
    finite_operational = _operational_summary(finite)
    exact_operational = _operational_summary(exact_endpoint)
    _validate_operational_conservation(
        paired_operational,
        (finite_operational, exact_operational),
    )
    _validate_exact_endpoint_operational_identity(exact_operational)
    paired_effort, _ = _triple_solved_effort(matrix, pairs)
    finite_effort, finite_effort_entries = _triple_solved_effort(matrix, finite)
    exact_effort, _ = _triple_solved_effort(matrix, exact_endpoint)
    finite_effort["leave_one_domain_out"] = {
        ratio_key: _effort_lodo(finite_effort_entries, tasks, ratio_key)
        for ratio_key in (
            "cap_over_blind",
            "exact_over_blind",
            "cap_over_exact",
        )
    }
    _validate_effort_conservation(paired_effort, (finite_effort, exact_effort))
    _validate_exact_endpoint_effort_identity(exact_effort)
    expected_effort_counts = EXPECTED_TRIPLE_SOLVED_EFFORT_COUNTS[scope_key]
    actual_effort_counts = {
        "overall": paired_effort["eligible_task_count"],
        "finite_cap": finite_effort["eligible_task_count"],
        "exact_endpoint": exact_effort["eligible_task_count"],
    }
    if actual_effort_counts != expected_effort_counts:
        raise AnalysisError("{} three-way effort denominators changed".format(scope_key))
    coefficients = _selector_coefficients(matrix, tasks)
    for label, expected in EXPECTED_SELECTOR_TRACE_COUNTS[scope_key].items():
        if coefficients["by_selector"][label]["count"] != expected:
            raise AnalysisError(
                "{} {} selector-trace denominator changed".format(scope_key, label)
            )

    node_lodo = _node_lodo(paired_operational_pairs, tasks)
    operational_nodes = paired_operational["expanded_bdd_nodes"]
    if not (
        node_lodo["eligible_pair_count"] == operational_nodes["eligible_pair_count"]
        and node_lodo["cap_total"] == operational_nodes["cap_total"]
        and node_lodo["exact_total"] == operational_nodes["exact_total"]
        and _fraction_from_payload(node_lodo["base"], "node LODO base")
        == Fraction(operational_nodes["cap_total"], operational_nodes["exact_total"])
    ):
        raise AnalysisError("node LODO disagrees with paired operational nodes")

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
            "theory_aligned_triple_solved_effort": paired_effort,
        },
        "trace_strata": {
            "finite_cap": {
                "definition": FINITE_CAP_DEFINITION,
                "trace_pairs": len(finite),
                "coverage": _coverage_summary(finite),
                "operational": finite_operational,
                "theory_aligned_triple_solved_effort": finite_effort,
                "selected_transform": _finite_cap_diagnostics(finite),
            },
            "exact_endpoint": {
                "definition": EXACT_ENDPOINT_DEFINITION,
                "trace_pairs": len(exact_endpoint),
                "coverage": _coverage_summary(exact_endpoint),
                "operational": exact_operational,
                "theory_aligned_triple_solved_effort": exact_effort,
                "selected_identity": _exact_endpoint_invariant(exact_endpoint),
            },
        },
        "selected_initial_h_on_non_dead_pairs": _initial_h_summary(pairs),
        "selected_certificate_coefficient": coefficients,
        "leave_one_domain_out": {
            "coverage": _coverage_lodo(matrix, tasks),
            "expanded_bdd_nodes": node_lodo,
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
    exact_summary = _fraction_summary(
        [Fraction(3, 2), Fraction(9, 2), Fraction(21, 2), Fraction(57, 2)]
    )
    assert _fraction_from_payload(exact_summary["median"], "synthetic median") == Fraction(15, 2)

    def expect_analysis_error(callback, label):
        try:
            callback()
        except AnalysisError:
            return
        raise AssertionError("validator accepted {}".format(label))

    def cell(nodes, buckets, image_time):
        result = {
            "raw_metrics_complete": True,
            "piece_metrics_certified": True,
            "metrics_validation_error": None,
            "metrics_validation_protocol": METRICS_VALIDATION_PROTOCOL,
            "expanded_buckets_single_piece": True,
            "expanded_bdd_nodes": nodes,
            "attempted_bdd_nodes": nodes,
            "attempted_bdd_pieces": buckets,
            "batched_images": 0,
            "expanded_states": 0,
            "attempted_states": 0,
            "image_time": image_time,
        }
        result.update(SCHEMA_V2_CONVENTIONS)
        for field in COMPLETED_BUCKET_IDENTITY_FIELDS:
            result[field] = buckets
        return result

    solved_cell = cell(10, 2, 1.0)
    solved_cell.update(
        {
            "coverage": 1,
            "effort": 10,
            "wbh_summary_solved": True,
            "wbh_solved_summary_certified": True,
            "plan_file_present": True,
            "plan_file_canonical": True,
            "plan_file_candidate_count": 1,
            "outcome_reconciliation_certified": True,
            "outcome_reconciliation_protocol": OUTCOME_RECONCILIATION_PROTOCOL,
            "solution_cost": 7,
            "plan_file_cost": 7,
            "run_log_plan_cost": 7,
            "wbh_done_solution_cost": 7,
        }
    )
    assert _certified_solved_effort(solved_cell, "synthetic solved")["effort"] == 10
    multi_piece_solved = dict(solved_cell)
    multi_piece_solved["expanded_buckets_single_piece"] = False
    expect_analysis_error(
        lambda: _certified_solved_effort(multi_piece_solved, "synthetic multi-piece"),
        "multi-piece solved effort",
    )
    piece_mismatch_solved = dict(solved_cell)
    piece_mismatch_solved["expanded_bdd_pieces"] += 1
    expect_analysis_error(
        lambda: _certified_solved_effort(piece_mismatch_solved, "synthetic mismatch"),
        "solved piece/bucket mismatch",
    )

    finite_pairs = [
        {
            "task": ("d", "p1"),
            "exact": cell(10, 2, 5.0),
            "cap": cell(8, 3, 4.0),
        },
        {
            "task": ("d", "p2"),
            "exact": cell(3, 1, 1.0),
            "cap": cell(3, 1, 1.0),
        },
    ]
    endpoint_pairs = [
        {
            "task": ("e", "p3"),
            "exact": cell(3, 1, 2.0),
            "cap": cell(3, 1, 2.1),
        }
    ]
    strata = [
        _operational_summary(finite_pairs),
        _operational_summary(endpoint_pairs),
    ]
    overall = _operational_summary(finite_pairs + endpoint_pairs)
    _validate_operational_conservation(overall, strata)
    _validate_exact_endpoint_operational_identity(strata[1])

    nonconserving = json.loads(canonical_json(strata))
    nonconserving[0]["completed_buckets"]["cap_lower"] -= 1
    nonconserving[0]["completed_buckets"]["cap_higher"] += 1
    expect_analysis_error(
        lambda: _validate_operational_conservation(overall, nonconserving),
        "nonconserving operational strata",
    )
    changed_label = json.loads(canonical_json(overall))
    changed_label["expanded_bdd_nodes_per_completed_bucket"]["estimand"] = "changed"
    expect_analysis_error(
        lambda: _validate_operational_summary_contract(changed_label),
        "changed operational estimand",
    )
    changed_denominator = json.loads(canonical_json(overall))
    changed_denominator["image_time_seconds_per_completed_bucket"][
        "positive_denominator_pair_count"
    ] += 1
    expect_analysis_error(
        lambda: _validate_operational_summary_contract(changed_denominator),
        "changed operational denominator",
    )
    fraction_drift = json.loads(canonical_json(overall))
    ratio = fraction_drift["completed_buckets"]["cap_over_exact"]
    ratio["numerator"] *= 2
    ratio["denominator"] *= 2
    expect_analysis_error(
        lambda: _validate_operational_summary_contract(fraction_drift),
        "unreduced operational fraction",
    )
    identity_drift = json.loads(canonical_json(strata[1]))
    identity_drift["expanded_bdd_nodes"]["equal"] -= 1
    identity_drift["expanded_bdd_nodes"]["cap_lower"] += 1
    expect_analysis_error(
        lambda: _validate_exact_endpoint_operational_identity(identity_drift),
        "changed exact-endpoint operational identity",
    )
    mismatched_cell = cell(4, 2, 1.0)
    mismatched_cell["image_calls_completed"] = 1
    expect_analysis_error(
        lambda: _operational_summary(
            [{"task": ("x", "p"), "exact": cell(4, 2, 1.0), "cap": mismatched_cell}]
        ),
        "mismatched bucket/image count",
    )
    changed_convention = cell(4, 2, 1.0)
    changed_convention["image_count_convention"] = "legacy-proxy"
    expect_analysis_error(
        lambda: _operational_summary(
            [
                {
                    "task": ("x", "q"),
                    "exact": cell(4, 2, 1.0),
                    "cap": changed_convention,
                }
            ]
        ),
        "changed operational metric convention",
    )
    changed_protocol = cell(4, 2, 1.0)
    changed_protocol["metrics_validation_protocol"] = "legacy-validation"
    expect_analysis_error(
        lambda: _operational_summary(
            [
                {
                    "task": ("x", "r"),
                    "exact": cell(4, 2, 1.0),
                    "cap": changed_protocol,
                }
            ]
        ),
        "changed operational validation protocol",
    )
    multi_piece_operational = cell(4, 2, 1.0)
    multi_piece_operational["expanded_buckets_single_piece"] = False
    expect_analysis_error(
        lambda: _operational_summary(
            [
                {
                    "task": ("x", "s"),
                    "exact": cell(4, 2, 1.0),
                    "cap": multi_piece_operational,
                }
            ]
        ),
        "multi-piece operational bucket",
    )

    def effort_summary(count, blind, exact, cap):
        totals = {"blind": blind, "exact": exact, "cap": cap}
        ratios = {}
        for key, numerator, denominator in (
            ("cap_over_blind", "cap", "blind"),
            ("exact_over_blind", "exact", "blind"),
            ("cap_over_exact", "cap", "exact"),
        ):
            ratios[key] = {
                "ratio": _fraction_payload(Fraction(totals[numerator], totals[denominator])),
                "numerator_lower": 0,
                "equal": count,
                "numerator_higher": 0,
            }
        return {
            "eligibility": TRIPLE_SOLVED_EFFORT_ELIGIBILITY,
            "estimand": TRIPLE_SOLVED_EFFORT_ESTIMAND,
            "eligible_task_count": count,
            "certified_cell_count": 3 * count,
            "single_piece_bucket_certified_cell_count": 3 * count,
            "cost_reconciled_task_count": count,
            "effort_equals_expanded_bdd_nodes_cells": 3 * count,
            "totals": totals,
            "ratios": ratios,
        }

    effort_strata = [effort_summary(2, 10, 12, 9), effort_summary(1, 3, 3, 3)]
    effort_overall = effort_summary(3, 13, 15, 12)
    _validate_effort_conservation(effort_overall, effort_strata)
    _validate_exact_endpoint_effort_identity(effort_strata[1])
    changed_effort_label = json.loads(canonical_json(effort_overall))
    changed_effort_label["eligibility"] = "changed"
    expect_analysis_error(
        lambda: _validate_effort_summary_contract(changed_effort_label),
        "changed effort eligibility",
    )
    changed_effort_equality_count = json.loads(canonical_json(effort_overall))
    changed_effort_equality_count[
        "effort_equals_expanded_bdd_nodes_cells"
    ] -= 1
    expect_analysis_error(
        lambda: _validate_effort_summary_contract(changed_effort_equality_count),
        "changed effort/node equality count",
    )
    changed_effort_fraction = json.loads(canonical_json(effort_overall))
    changed_effort_fraction["ratios"]["cap_over_blind"]["ratio"]["numerator"] += 1
    expect_analysis_error(
        lambda: _validate_effort_summary_contract(changed_effort_fraction),
        "changed effort fraction",
    )
    changed_effort_identity = json.loads(canonical_json(effort_strata[1]))
    changed_effort_identity["ratios"]["cap_over_exact"]["equal"] -= 1
    changed_effort_identity["ratios"]["cap_over_exact"]["numerator_lower"] += 1
    expect_analysis_error(
        lambda: _validate_exact_endpoint_effort_identity(changed_effort_identity),
        "changed exact-endpoint effort identity",
    )
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
