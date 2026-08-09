#!/usr/bin/env python3
"""Fail-closed analysis of the frozen Arrhenius selector validation.

The analyzer consumes two inputs: the exact selection artifact v3 emitted by
``analyze_arrhenius_selector_pilot.py`` and one Lab properties JSON/evaluation
directory/tar archive emitted by ``exp_arrhenius_selector_validation.py``.
It never writes files and prints one canonical JSON object to stdout.

The primary estimand and bootstrap are fixed here before held-out outcomes are
available.  For each of the 46 domains, compute the mean of the two paired
task-level coverage differences (selector minus CEGAR), then average those 46
domain means equally.  Bootstrap replicate ``r`` draws 46 domains with
replacement.  Draw ``j`` uses the first unsigned big-endian 64 bits of::

    SHA256(UTF8(seed) || NUL || UTF8(comparison-name) || NUL ||
           UINT64_BE(46 * r + j))

modulo 46 as an index into lexicographically sorted domain names.  There are
exactly 100,000 replicates.  The 95% percentile endpoints are the ordered
replicates at zero-based indices ``floor(.025*(R-1))`` and
``ceil(.975*(R-1))``; there is no interpolation.  Because every domain has
exactly two tasks, estimates are accumulated as integer numerators over the
exact denominator 92 before conversion to JSON numbers.

Ordinary analysis is intentionally blocked until both reviewed placeholders
below are pinned.  ``--self-test`` uses explicit synthetic overrides and does
not weaken that launch-data gate.
"""

from __future__ import annotations

import argparse
import copy
import contextlib
from fractions import Fraction
import hashlib
import io
import json
import math
import re
import statistics
import sys
import tarfile
import tempfile
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.dont_write_bytecode = True

import analyze_arrhenius_selector_pilot as pilot_analyzer
import analyze_ms_caps_pilot as analyzer_utils
import exp_arrhenius_common as common
import exp_arrhenius_selector_validation as runner
import suite_cost_manifest
import wbh_parser


class AnalysisError(RuntimeError):
    pass


ANALYSIS_SCHEMA = (
    "symbolic-search-heuristics/arrhenius-selector-heldout-analysis/v2"
)
ARTIFACT_SCHEMA = (
    "symbolic-search-heuristics/arrhenius-selector-screen-selection/v3"
)
VALIDATION_PROTOCOL = "arrhenius-selector-heldout-validation-v2"
ANALYSIS_PROTOCOL = "paired-domain-macro-coverage-sha256-bootstrap-v1"
PRIMARY_COMPARISON = "selector-vs-pdb-cegar"
PRIMARY_ESTIMAND = (
    "selector-minus-cegar-equally-weighted-domain-macro-coverage/v1"
)
BOOTSTRAP_METHOD = "sha256-counter-domain-resampling/v1"
BOOTSTRAP_SEED = (
    "symbolic-search-heuristics/arrhenius-selector-heldout-bootstrap/v1"
)
BOOTSTRAP_REPLICATES = 100000
CONFIDENCE_LEVEL = 0.95
BOOTSTRAP_COUNTER_ENCODING = (
    "sha256(utf8(seed)||nul||utf8(comparison-name)||nul||"
    "uint64-be(46*replicate+draw));first-uint64-be-mod-46/v1"
)
BOOTSTRAP_INTERVAL_RULE = (
    "sorted-replicates[floor(.025*(R-1)),ceil(.975*(R-1))];"
    "zero-based-no-interpolation/v1"
)
SYNTHETIC_BOOTSTRAP_SHA256 = (
    "1d2cd26a089ca84d33798364225fab4f2f50219620f9bb868a0e5366f65c3f37"
)

# Review and replace these after the selector screen and the runner-pin commit.
# Ordinary held-out analysis fails closed while either value is unset.
EXPECTED_SELECTION_ARTIFACT_SHA256 = None
EXPECTED_VALIDATION_PROTOCOL_REVISION = None

PLANNER_REVISION = "58a3f742d7ac63f391d06c237573f14ad590c187"
PILOT_PROTOCOL_REVISION = "d6d98ad42f3976cd5cf0c9b17d8fa255354fbfbf"
CACHE_BINARY_SHA256 = (
    "59b97e8b1e777f700c255932271604393f60ec9aeba5c0151d0b7415a3a58511"
)
CACHE_PREPROCESS_SHA256 = (
    "acf2fc66c0b189095111a9d227ccb5b7acc564f1a6cb7bfd557904fa3c76798c"
)
CACHE_NAME_SUFFIX = "_61a748e5"
BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
BENCHMARK_REPOSITORY = "https://github.com/aibasel/downward-benchmarks.git"
EXPECTED_PYTHON_VERSION = "3.9.25"
EXPECTED_LAB_VERSION = "8.0"

MANIFEST_NAME = "heuristic_finalists_validation_suite.txt"
MANIFEST_PATH = SCRIPT_DIR / MANIFEST_NAME
MANIFEST_SHA256 = (
    "fc63d4eed62816a2e065cb89f89483999a7b51067b7077969d10b2a338f19760"
)
TASK_SOURCES_SHA256 = (
    "14202b66a4ed4ea7afa9f204d15cbfe8857b061a644661fc9d68b3624523fdf4"
)
SOURCE_MANIFEST_SHA256 = (
    "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168"
)
MATERIALIZED_PDDL_PROTOCOL = (
    "per-cell-independent-manual-byte-copy-temp-digest-atomic-replace-"
    "readonly/v1"
)
EXPECTED_MATERIALIZED_PDDL_FILES = {644: 1288, 736: 1472}
EXPECTED_MATERIALIZED_PDDL_BYTES = {644: 72541896, 736: 82905024}
EXPECTED_PDDL_BYTES_PER_CONFIG = 10363128
EXPECTED_UNIQUE_PDDL_SOURCE_FILES = 142
EXPECTED_UNIQUE_PDDL_SOURCE_BYTES = 10195682
PILOT_MANIFEST_NAME = "selector_pilot_suite.txt"
PILOT_MANIFEST_SHA256 = (
    "3195dac7e62a34e5ac4cbeb715ab7f9b99e2ee64341082dd7d718ea2820751ca"
)
PILOT_TASK_SOURCES_SHA256 = (
    "dbb7730c257472c07f7946f0434949449169e06d1faa2174a92a6d13c48cb8ba"
)
PILOT_MATERIALIZED_PDDL_FILES = 2000
PILOT_MATERIALIZED_PDDL_BYTES = 50354240
PILOT_PDDL_BYTES_PER_CONFIG = 2517712
PILOT_UNIQUE_PDDL_SOURCE_FILES = 77
PILOT_UNIQUE_PDDL_SOURCE_BYTES = 2451625

EXPECTED_TASKS = 92
EXPECTED_DOMAINS = 46
TIME_LIMIT_SECONDS = 300.0
PAR2_UNSOLVED_SECONDS = 600.0
MEMORY_LIMIT_MIB = 8192.0
BLIND = "blind_fw"
CEGAR = "pdb_cegar_b100k"
MS_CAP32_BUILD60 = "ms_cap32_build60"

PILOT_PROTOCOL = "arrhenius-exact-width-selector-screening-v2"
SELECTION_RULE = (
    "valid-costs-max-coverage-min-micro-par2-"
    "min-certified-image-time-label/v1"
)
PILOT_OPTION_MATRIX_SHA256 = (
    "e16f6e34af5101a3549bfbf98ebaba23371c645f9166c884bfdf07b3b65e7442"
)
PILOT_SELECTOR_CONFIGS_SHA256 = (
    "7d44b160de438b32c385e95d4b3b48df9433d9f1c42397b4be5341f3937edf92"
)
PILOT_CONTROL_CONFIGS_SHA256 = (
    "ee40b07516ba1f2a3f562a2ec20f617e7eb1f742bf51aa67e9fb8db3d7ac9c89"
)
SELECTOR_ELIGIBILITY_SHA256 = (
    "51dc9a5392f021c921d1dcc2636eb7c2d5955a363ff9df7e44ec871f9afc2aa3"
)
FIXED_VALIDATION_CONFIGS_SHA256 = (
    "c4cc5f5560a7b8b0d6bc28210c64ab603b75e01df1f40a0e9c4cb22fb02f557d"
)
SELECTOR_PARSER_PROTOCOL = (
    "run.log/pdb-final-and-width-selector-v1-whole-trace/v3"
)
METRICS_VALIDATION_PROTOCOL = "wbh-exact-schema-semantic-v3"
OUTCOME_RECONCILIATION_PROTOCOL = (
    "direct-search-raw-effective-plan-reconciliation/v1"
)
SELECTOR_POOL_PROTOCOL = "fixed_pool_v1"
SELECTOR_SCORE_VERSION = (
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
)
SELECTOR_SOURCES = (
    "empty",
    "bdd_prefix",
    "goal_prefix",
    "goal_fill",
    "cegar",
)
SELECTOR_RECORD_KEYS = (
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

CONTROL_CONFIGS = (
    ("blind_fw", "sym_fw()"),
    (
        "ms_exact",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false)",
    ),
    (
        "ms_cap32",
        "sym_fw_ms(max_states=10000,value_cap=32,align_merge_order=false)",
    ),
    (
        "pdb_goal_fill_b100k",
        "sym_fw_pdb(budget=100000,pattern_selection=goal_fill)",
    ),
    (
        "pdb_cegar_b100k",
        "sym_fw_pdb(budget=100000,pattern_selection=cegar,"
        "cegar_max_time=10,cegar_seed=2011)",
    ),
)
SELECTOR_CONFIGS = (
    *tuple(
        (
            "pdb_selector_k{}".format(value),
            "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
            "cofactor_width_budget={},cegar_max_time=10,cegar_seed=2011)".
            format(value),
        )
        for value in (1, 2, 4, 8, 16, 32, 64, 128, 256)
    ),
    (
        "pdb_selector_kinf",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=infinity,cegar_max_time=10,cegar_seed=2011)",
    ),
    *tuple(
        (
            "pdb_selector_k{}_adapt_w64_r1_n1m".format(value),
            "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
            "cofactor_width_budget={},cegar_max_time=10,cegar_seed=2011,"
            "batch_f_window=64,batch_max_union_ratio=1.0,"
            "batch_max_union_nodes=1000000)".format(
                "infinity" if value == "inf" else value
            ),
        )
        for value in (32, 64, 128, "inf")
    ),
    (
        "pdb_selector_k32_w16",
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cofactor_width_budget=32,cegar_max_time=10,cegar_seed=2011,"
        "batch_f_window=16)",
    ),
)
PILOT_CONFIGS = CONTROL_CONFIGS + SELECTOR_CONFIGS
PILOT_SEARCHES = dict(PILOT_CONFIGS)
SELECTOR_LABELS = tuple(label for label, _ in SELECTOR_CONFIGS)

FIXED_CONFIGS = (
    ("blind_fw", PILOT_SEARCHES["blind_fw"], "fixed-blind-control"),
    ("ms_exact", PILOT_SEARCHES["ms_exact"], "fixed-ms-exact-control"),
    ("ms_cap32", PILOT_SEARCHES["ms_cap32"], "fixed-ms-cap32-control"),
    (
        "pdb_goal_fill_b100k",
        PILOT_SEARCHES["pdb_goal_fill_b100k"],
        "fixed-pdb-goal-fill-control",
    ),
    (
        "pdb_cegar_b100k",
        PILOT_SEARCHES["pdb_cegar_b100k"],
        "fixed-pdb-cegar-control",
    ),
    (
        MS_CAP32_BUILD60,
        "sym_fw_ms(max_states=10000,value_cap=32,align_merge_order=false,"
        "build_time_limit=60)",
        "predeclared-ms-build-budget-safeguard",
    ),
)
BATCHED_SELECTOR_BASE = {
    "pdb_selector_k32_adapt_w64_r1_n1m": "pdb_selector_k32",
    "pdb_selector_k64_adapt_w64_r1_n1m": "pdb_selector_k64",
    "pdb_selector_k128_adapt_w64_r1_n1m": "pdb_selector_k128",
    "pdb_selector_kinf_adapt_w64_r1_n1m": "pdb_selector_kinf",
    "pdb_selector_k32_w16": "pdb_selector_k32",
}

ANALYSIS_PREDECLARATION = {
    "protocol": ANALYSIS_PROTOCOL,
    "primary_comparison": PRIMARY_COMPARISON,
    "primary_estimand": PRIMARY_ESTIMAND,
    "resampling_unit": "domain",
    "bootstrap_method": BOOTSTRAP_METHOD,
    "bootstrap_seed": BOOTSTRAP_SEED,
    "bootstrap_replicates": BOOTSTRAP_REPLICATES,
    "confidence_level": CONFIDENCE_LEVEL,
    "rerank_on_validation": False,
    "secondary_descriptive": [
        "suite-micro-coverage",
        "micro-par2-600s",
        "discordant-wins-losses",
        "jointly-solved-runtime-ratio",
        "certified-width-image-and-effort-metrics",
        "ms-build-budget-fallback-incidence",
    ],
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
ALL_SCHEMA_V2_METRICS = SCHEMA_V2_INTEGER_METRICS + SCHEMA_V2_REAL_METRICS
RESOURCE_EXIT_CODES = frozenset((22, 23, 24))
PRESEARCH_EXIT_CODES = frozenset((10, 20, 21))
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


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
        raise AnalysisError("value is not canonical finite JSON: {}".format(err))


def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def _require_sha256(value, label):
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise AnalysisError("{} must be a lowercase SHA-256".format(label))
    if len(set(value)) == 1:
        raise AnalysisError("{} still looks synthetic".format(label))
    return value


def _require_revision(value, label):
    if not isinstance(value, str) or not REVISION_RE.fullmatch(value):
        raise AnalysisError("{} must be a lowercase 40-hex revision".format(label))
    if len(set(value)) == 1:
        raise AnalysisError("{} still looks synthetic".format(label))
    return value


def _same(actual, expected):
    return type(actual) is type(expected) and actual == expected


def _finite_number(value):
    if type(value) not in (int, float):
        return None
    try:
        return float(value) if math.isfinite(float(value)) else None
    except (OverflowError, TypeError, ValueError):
        return None


def _reject_duplicate_keys(pairs):
    value = {}
    for key, child in pairs:
        if key in value:
            raise AnalysisError("duplicate JSON key {!r}".format(key))
        value[key] = child
    return value


def _reject_json_constant(value):
    raise AnalysisError("non-finite JSON constant {}".format(value))


def _parse_json_bytes(raw, label):
    try:
        value = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_json_constant,
        )
    except AnalysisError:
        raise
    except (UnicodeError, json.JSONDecodeError) as err:
        raise AnalysisError("cannot parse {}: {}".format(label, err)) from err
    # ``allow_nan=False`` also recursively rejects non-finite values produced
    # through unusual decoder extensions and verifies JSON serializability.
    canonical_json(value)
    return value


def _normalize_properties(value, source):
    if isinstance(value, dict):
        items = list(value.items())
    elif isinstance(value, list):
        items = [(str(index), item) for index, item in enumerate(value)]
    else:
        raise AnalysisError(
            "{} has a {} top level; expected object or list".format(
                source, type(value).__name__
            )
        )
    records = []
    for source_key, item in items:
        if not isinstance(item, dict):
            raise AnalysisError(
                "property entry {!r} in {} is not an object".format(
                    source_key, source
                )
            )
        record = dict(item)
        record["_source_key"] = str(source_key)
        records.append(record)
    return records


def _properties_file_in_directory(path):
    candidates = [path / "properties", path / "properties.json"]
    matches = [candidate for candidate in candidates if candidate.is_file()]
    matches.extend(
        candidate
        for candidate in sorted(path.glob("*-eval/properties"))
        if candidate.is_file()
    )
    unsafe = [
        candidate
        for candidate in matches
        if candidate.is_symlink() or candidate.parent.is_symlink()
    ]
    if unsafe:
        raise AnalysisError(
            "{} contains symlinked properties candidates: {}".format(
                path, ", ".join(map(str, unsafe))
            )
        )
    if len(matches) != 1:
        raise AnalysisError(
            "{} contains {} properties candidates: {}".format(
                path, len(matches), ", ".join(map(str, matches)) or "none"
            )
        )
    return matches[0]


def load_properties(raw_path):
    if raw_path == "-":
        raw = sys.stdin.buffer.read()
        value = _parse_json_bytes(raw, "stdin")
        return _normalize_properties(value, "stdin")
    path = Path(raw_path).expanduser()
    if path.is_symlink():
        raise AnalysisError("properties input must not be a symlink: {}".format(path))
    if path.is_dir():
        path = _properties_file_in_directory(path)
    if path.is_symlink() or not path.is_file():
        raise AnalysisError("properties input is not a regular file: {}".format(path))
    try:
        is_archive = tarfile.is_tarfile(str(path))
    except OSError as err:
        raise AnalysisError("cannot inspect properties input: {}".format(err)) from err
    if is_archive:
        try:
            with tarfile.open(str(path), mode="r:*") as archive:
                members = [
                    member
                    for member in archive.getmembers()
                    if member.isfile() and Path(member.name).name == "properties"
                ]
                if len(members) != 1:
                    raise AnalysisError(
                        "{} contains {} regular properties members".format(
                            path, len(members)
                        )
                    )
                stream = archive.extractfile(members[0])
                if stream is None:
                    raise AnalysisError("cannot read archive properties member")
                raw = stream.read()
        except (OSError, tarfile.TarError) as err:
            raise AnalysisError("cannot read archive {}: {}".format(path, err)) from err
    else:
        try:
            raw = path.read_bytes()
        except OSError as err:
            raise AnalysisError("cannot read {}: {}".format(path, err)) from err
    value = _parse_json_bytes(raw, str(path))
    return _normalize_properties(value, str(path))


def load_selection_artifact(path):
    path = Path(path).expanduser()
    if path.is_symlink() or not path.is_file():
        raise AnalysisError(
            "selection artifact must be a regular non-symlink file: {}".format(path)
        )
    try:
        raw = path.read_bytes()
    except OSError as err:
        raise AnalysisError("cannot read selection artifact: {}".format(err)) from err
    value = _parse_json_bytes(raw, "selection artifact")
    if not isinstance(value, dict):
        raise AnalysisError("selection artifact must contain one JSON object")
    return value, hashlib.sha256(raw).hexdigest()


def _load_manifest(path, expected_digest, expected_tasks, expected_domains):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as err:
        raise AnalysisError("cannot read manifest {}: {}".format(path, err)) from err
    labels = []
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(":")
        if len(fields) != 2 or not all(fields):
            raise AnalysisError(
                "{}:{} is not an exact DOMAIN:PROBLEM entry".format(path, lineno)
            )
        labels.append(line)
    digest = hashlib.sha256(
        "".join("{}\n".format(label) for label in labels).encode("utf-8")
    ).hexdigest()
    if digest != expected_digest:
        raise AnalysisError(
            "manifest digest changed: expected {}, got {}".format(
                expected_digest, digest
            )
        )
    tasks = [tuple(label.split(":", 1)) for label in labels]
    counts = defaultdict(int)
    for domain, _ in tasks:
        counts[domain] += 1
    if (
        len(tasks) != expected_tasks
        or len(set(tasks)) != expected_tasks
        or len(counts) != expected_domains
        or set(counts.values()) != {2}
    ):
        raise AnalysisError(
            "manifest must contain {} unique tasks, exactly two in each of "
            "{} domains".format(expected_tasks, expected_domains)
        )
    return tasks


def load_and_validate_tasks():
    tasks = _load_manifest(
        MANIFEST_PATH, MANIFEST_SHA256, EXPECTED_TASKS, EXPECTED_DOMAINS
    )
    pilot_tasks = set(
        _load_manifest(
            SCRIPT_DIR / PILOT_MANIFEST_NAME,
            PILOT_MANIFEST_SHA256,
            50,
            25,
        )
    )
    overlap = sorted(set(tasks) & pilot_tasks)
    if overlap:
        raise AnalysisError(
            "held-out manifest overlaps the selector screen: {}".format(
                ", ".join("{}:{}".format(*task) for task in overlap)
            )
        )
    supported = suite_cost_manifest.supported_tasks()
    unsupported = sorted(set(tasks) - supported)
    if unsupported:
        raise AnalysisError(
            "held-out manifest contains unsupported tasks: {}".format(
                ", ".join("{}:{}".format(*task) for task in unsupported)
            )
        )
    data = suite_cost_manifest.load_manifest()
    by_task = {
        (record["domain"], record["problem"]): record
        for record in data["tasks"]
    }
    try:
        selected = [by_task[task] for task in sorted(tasks)]
    except KeyError as err:
        raise AnalysisError(
            "held-out task missing from frozen source manifest: {}:{}".format(
                *err.args[0]
            )
        ) from err
    source_digest = hashlib.sha256(
        suite_cost_manifest.canonical_records_bytes(selected)
    ).hexdigest()
    if source_digest != TASK_SOURCES_SHA256:
        raise AnalysisError(
            "held-out source records changed: expected {}, got {}".format(
                TASK_SOURCES_SHA256, source_digest
            )
        )
    if suite_cost_manifest.sha256_file(
        suite_cost_manifest.MANIFEST_PATH
    ) != SOURCE_MANIFEST_SHA256:
        raise AnalysisError("frozen source-manifest bytes changed")
    return tasks


def _option_records(configs):
    return [{"label": label, "search": search} for label, search in configs]


def _expected_configs(global_label, selector_label):
    configs = []

    def add(label, search, role):
        matches = [item for item in configs if item["label"] == label]
        search_matches = [item for item in configs if item["search"] == search]
        if matches or search_matches:
            if (
                len(matches) != 1
                or len(search_matches) != 1
                or matches[0] is not search_matches[0]
            ):
                raise AnalysisError("configuration label/search collision")
            if role not in matches[0]["roles"]:
                matches[0]["roles"].append(role)
            return
        configs.append({"label": label, "search": search, "roles": [role]})

    for label, search, role in FIXED_CONFIGS:
        add(label, search, role)
    if selector_label not in SELECTOR_LABELS:
        raise AnalysisError("artifact selector winner is not eligible")
    add(
        selector_label,
        PILOT_SEARCHES[selector_label],
        "pilot-selector-family-winner",
    )
    matched = BATCHED_SELECTOR_BASE.get(selector_label)
    if matched is not None:
        add(
            matched,
            PILOT_SEARCHES[matched],
            "matched-same-k-unbatched-ablation",
        )
    if global_label not in {item["label"] for item in configs}:
        raise AnalysisError("global winner is absent from held-out configurations")
    add(global_label, PILOT_SEARCHES[global_label], "pilot-global-winner")
    return configs, matched


def _expected_comparisons(global_label, selector_label, matched_label):
    comparisons = []

    def add(name, candidate, reference, role):
        if candidate == reference:
            return
        for item in comparisons:
            if item["candidate"] == candidate and item["reference"] == reference:
                item["roles"].append(role)
                return
        comparisons.append(
            {
                "name": name,
                "candidate": candidate,
                "reference": reference,
                "roles": [role],
            }
        )

    add(
        PRIMARY_COMPARISON,
        selector_label,
        CEGAR,
        "primary-selector-contrast",
    )
    add(
        "selector-vs-pdb-goal-fill",
        selector_label,
        "pdb_goal_fill_b100k",
        "secondary-matched-pdb-contrast",
    )
    add(
        "ms-cap32-build60-vs-unbounded-build",
        MS_CAP32_BUILD60,
        "ms_cap32",
        "primary-setup-safeguard-contrast",
    )
    if matched_label is not None:
        add(
            "selector-batching-vs-same-k-unbatched",
            selector_label,
            matched_label,
            "conditional-batching-ablation",
        )
    add(
        "global-winner-vs-blind-forward",
        global_label,
        BLIND,
        "heldout-global-winner-context",
    )
    add(
        "global-winner-vs-ms-exact",
        global_label,
        "ms_exact",
        "heldout-global-winner-context",
    )
    for reference in (BLIND, "ms_exact", "ms_cap32"):
        add(
            "selector-vs-{}".format(reference.replace("_", "-")),
            selector_label,
            reference,
            "heldout-selector-context",
        )
    return comparisons


def validate_selection_artifact(artifact):
    """Validate with the runner and an independently reconstructed contract."""
    try:
        runner_matrix = runner.validate_selection_artifact(copy.deepcopy(artifact))
    except (
        runner.ProtocolError,
        RuntimeError,
        TypeError,
        ValueError,
        KeyError,
        IndexError,
        StopIteration,
    ) as err:
        raise AnalysisError("invalid selection artifact: {}".format(err)) from err
    if set(artifact) != {"schema", "pilot", "selection", "paired_deltas", "validation"}:
        raise AnalysisError("selection artifact top-level fields changed")
    if artifact["schema"] != ARTIFACT_SCHEMA:
        raise AnalysisError("selection artifact schema changed")
    pilot = artifact["pilot"]
    exact_pilot = {
        "protocol": PILOT_PROTOCOL,
        "selection_rule": SELECTION_RULE,
        "planner_revision": PLANNER_REVISION,
        "protocol_revision": PILOT_PROTOCOL_REVISION,
        "planner_binary_sha256": CACHE_BINARY_SHA256,
        "planner_preprocess_sha256": CACHE_PREPROCESS_SHA256,
        "benchmark_revision": BENCHMARK_REVISION,
        "benchmark_repository": BENCHMARK_REPOSITORY,
        "task_manifest": PILOT_MANIFEST_NAME,
        "task_manifest_sha256": PILOT_MANIFEST_SHA256,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "task_sources_sha256": PILOT_TASK_SOURCES_SHA256,
        "materialized_pddl_protocol": MATERIALIZED_PDDL_PROTOCOL,
        "materialized_pddl_files": PILOT_MATERIALIZED_PDDL_FILES,
        "materialized_pddl_bytes": PILOT_MATERIALIZED_PDDL_BYTES,
        "pddl_bytes_per_config": PILOT_PDDL_BYTES_PER_CONFIG,
        "unique_pddl_source_files": PILOT_UNIQUE_PDDL_SOURCE_FILES,
        "unique_pddl_source_bytes": PILOT_UNIQUE_PDDL_SOURCE_BYTES,
        "option_matrix_sha256": PILOT_OPTION_MATRIX_SHA256,
        "control_configs_sha256": PILOT_CONTROL_CONFIGS_SHA256,
        "selector_configs_sha256": PILOT_SELECTOR_CONFIGS_SHA256,
        "pdb_selector_parser_protocol": SELECTOR_PARSER_PROTOCOL,
        "metrics_validation_protocol": METRICS_VALIDATION_PROTOCOL,
        "outcome_reconciliation_protocol": OUTCOME_RECONCILIATION_PROTOCOL,
        "selector_pool_protocol": SELECTOR_POOL_PROTOCOL,
        "selector_score_version": SELECTOR_SCORE_VERSION,
        "selector_source_order": list(SELECTOR_SOURCES),
        "task_count": 50,
        "config_count": 20,
        "expected_run_count": 1000,
        "time_limit_seconds": 300,
        "memory_limit_mib": 8192,
        "par2_unsolved_seconds": 600,
    }
    for field, expected in exact_pilot.items():
        if not _same(pilot.get(field), expected):
            raise AnalysisError(
                "artifact pilot.{}={!r}, expected {!r}".format(
                    field, pilot.get(field), expected
                )
            )
    _require_sha256(
        pilot.get("properties_canonical_sha256"),
        "pilot properties canonical digest",
    )
    selection = artifact["selection"]
    ranking = selection.get("ranking")
    if not isinstance(ranking, list) or len(ranking) != 20:
        raise AnalysisError("artifact ranking must contain exactly 20 entries")
    global_label = selection["global_winner"]["label"]
    selector_label = selection["selector_family_winner"]["label"]
    if ranking[0]["label"] != global_label:
        raise AnalysisError("artifact global winner is not rank one")
    first_selector = next(
        item["label"] for item in ranking if item["label"] in SELECTOR_LABELS
    )
    if first_selector != selector_label:
        raise AnalysisError("artifact selector winner was reranked separately")
    configs, matched = _expected_configs(global_label, selector_label)
    comparisons = _expected_comparisons(global_label, selector_label, matched)
    run_count = len(configs) * EXPECTED_TASKS
    expected_validation = {
        "task_manifest": MANIFEST_NAME,
        "task_manifest_sha256": MANIFEST_SHA256,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "task_sources_sha256": TASK_SOURCES_SHA256,
        "task_count": EXPECTED_TASKS,
        "domain_count": EXPECTED_DOMAINS,
        "fixed_configs_sha256": FIXED_VALIDATION_CONFIGS_SHA256,
        "roles": {
            "global_winner": global_label,
            "selector_family_winner": selector_label,
            "ms_build_budget_safeguard": MS_CAP32_BUILD60,
            "matched_same_k_unbatched": matched,
        },
        "configs": configs,
        "option_matrix_sha256": sha256_json(_option_records(
            [(item["label"], item["search"]) for item in configs]
        )),
        "comparisons": comparisons,
        "comparisons_sha256": sha256_json(comparisons),
        "config_count": len(configs),
        "expected_run_count": run_count,
        "array_layout": {
            "raw_runs": run_count,
            "array_tasks": run_count,
            "runs_per_array_task": 1,
            "scheduler_time_limit_seconds": 600,
        },
        "materialized_pddl_protocol": MATERIALIZED_PDDL_PROTOCOL,
        "materialized_pddl_files": EXPECTED_MATERIALIZED_PDDL_FILES[
            run_count
        ],
        "materialized_pddl_bytes": EXPECTED_MATERIALIZED_PDDL_BYTES[
            run_count
        ],
        "pddl_bytes_per_config": EXPECTED_PDDL_BYTES_PER_CONFIG,
        "unique_pddl_source_files": EXPECTED_UNIQUE_PDDL_SOURCE_FILES,
        "unique_pddl_source_bytes": EXPECTED_UNIQUE_PDDL_SOURCE_BYTES,
        "protocol": VALIDATION_PROTOCOL,
        "requires_disjoint_tasks": True,
        "selection_artifact_schema": ARTIFACT_SCHEMA,
        "selection_rule": SELECTION_RULE,
        "selector_eligibility_labels": list(SELECTOR_LABELS),
        "selector_eligibility_sha256": SELECTOR_ELIGIBILITY_SHA256,
        "selector_configs_sha256": PILOT_SELECTOR_CONFIGS_SHA256,
        "time_limit_seconds": 300,
        "memory_limit_mib": 8192,
        "par2_unsolved_seconds": 600,
        "analysis": copy.deepcopy(ANALYSIS_PREDECLARATION),
    }
    if canonical_json(artifact["validation"]) != canonical_json(expected_validation):
        raise AnalysisError(
            "artifact held-out contract differs from independent reconstruction"
        )
    expected_matrix = [(item["label"], item["search"]) for item in configs]
    if runner_matrix["configs"] != expected_matrix:
        raise AnalysisError("runner artifact matrix differs from analyzer matrix")
    if runner_matrix["comparisons"] != comparisons:
        raise AnalysisError("runner comparisons differ from analyzer comparisons")
    if runner_matrix["run_count"] != run_count:
        raise AnalysisError("runner run count differs from analyzer run count")
    return {
        "global_winner": global_label,
        "selector_winner": selector_label,
        "matched_unbatched": matched,
        "configs": expected_matrix,
        "config_records": configs,
        "comparisons": comparisons,
        "option_matrix_sha256": expected_validation["option_matrix_sha256"],
        "comparisons_sha256": expected_validation["comparisons_sha256"],
        "run_count": run_count,
        "pilot_properties_sha256": pilot["properties_canonical_sha256"],
        "materialized_pddl_protocol": expected_validation[
            "materialized_pddl_protocol"
        ],
        "materialized_pddl_files": expected_validation[
            "materialized_pddl_files"
        ],
        "materialized_pddl_bytes": expected_validation[
            "materialized_pddl_bytes"
        ],
        "pddl_bytes_per_config": expected_validation[
            "pddl_bytes_per_config"
        ],
        "unique_pddl_source_files": expected_validation[
            "unique_pddl_source_files"
        ],
        "unique_pddl_source_bytes": expected_validation[
            "unique_pddl_source_bytes"
        ],
    }


def validate_runner_contract(expected_artifact_sha256=None):
    exact = {
        "validation protocol": (runner.PROTOCOL, VALIDATION_PROTOCOL),
        "analysis protocol": (runner.ANALYSIS_PROTOCOL, ANALYSIS_PROTOCOL),
        "artifact schema": (runner.ARTIFACT_SCHEMA, ARTIFACT_SCHEMA),
        "bootstrap seed": (runner.ANALYSIS_BOOTSTRAP_SEED, BOOTSTRAP_SEED),
        "bootstrap replicates": (
            runner.ANALYSIS_BOOTSTRAP_REPLICATES,
            BOOTSTRAP_REPLICATES,
        ),
        "planner revision": (runner.PLANNER_REVISION, PLANNER_REVISION),
        "pilot protocol revision": (
            runner.PILOT_PROTOCOL_REVISION,
            PILOT_PROTOCOL_REVISION,
        ),
        "binary digest": (runner.CACHE_BINARY_SHA256, CACHE_BINARY_SHA256),
        "preprocess digest": (
            runner.CACHE_PREPROCESS_SHA256,
            CACHE_PREPROCESS_SHA256,
        ),
        "manifest name": (runner.MANIFEST.name, MANIFEST_NAME),
        "manifest digest": (runner.MANIFEST_DIGEST, MANIFEST_SHA256),
        "task-source digest": (
            runner.EXPECTED_TASK_SOURCES_SHA256,
            TASK_SOURCES_SHA256,
        ),
        "source-manifest digest": (
            runner.EXPECTED_SOURCE_MANIFEST_SHA256,
            SOURCE_MANIFEST_SHA256,
        ),
        "selector parser protocol": (
            runner.PDB_SELECTOR_PARSER_PROTOCOL,
            SELECTOR_PARSER_PROTOCOL,
        ),
        "metrics parser protocol": (
            wbh_parser.METRICS_VALIDATION_PROTOCOL,
            METRICS_VALIDATION_PROTOCOL,
        ),
        "outcome reconciliation protocol": (
            common.OUTCOME_RECONCILIATION_PROTOCOL,
            OUTCOME_RECONCILIATION_PROTOCOL,
        ),
        "runner outcome reconciliation protocol": (
            runner.OUTCOME_RECONCILIATION_PROTOCOL,
            OUTCOME_RECONCILIATION_PROTOCOL,
        ),
        "common selector parser protocol": (
            common.PDB_SELECTOR_PARSER_PROTOCOL,
            SELECTOR_PARSER_PROTOCOL,
        ),
        "selector pool protocol": (
            common.PDB_SELECTOR_POOL_PROTOCOL,
            SELECTOR_POOL_PROTOCOL,
        ),
        "selector score version": (
            common.PDB_SELECTOR_SCORE_VERSION,
            SELECTOR_SCORE_VERSION,
        ),
        "selector source order": (
            common.PDB_SELECTOR_SOURCES,
            SELECTOR_SOURCES,
        ),
        "selector record keys": (
            common.PDB_SELECTOR_RECORD_KEYS,
            SELECTOR_RECORD_KEYS,
        ),
        "fixed configs digest": (
            runner.FIXED_VALIDATION_CONFIGS_SHA256,
            FIXED_VALIDATION_CONFIGS_SHA256,
        ),
        "selector eligibility digest": (
            runner.SELECTOR_ELIGIBILITY_SHA256,
            SELECTOR_ELIGIBILITY_SHA256,
        ),
        "materialized PDDL protocol": (
            runner.MATERIALIZED_PDDL_PROTOCOL,
            MATERIALIZED_PDDL_PROTOCOL,
        ),
        "materialized PDDL files": (
            runner.EXPECTED_MATERIALIZED_PDDL_FILES,
            EXPECTED_MATERIALIZED_PDDL_FILES,
        ),
        "materialized PDDL bytes": (
            runner.EXPECTED_MATERIALIZED_PDDL_BYTES,
            EXPECTED_MATERIALIZED_PDDL_BYTES,
        ),
        "PDDL bytes per config": (
            runner.EXPECTED_PDDL_BYTES_PER_CONFIG,
            EXPECTED_PDDL_BYTES_PER_CONFIG,
        ),
        "unique PDDL source files": (
            runner.EXPECTED_UNIQUE_PDDL_SOURCE_FILES,
            EXPECTED_UNIQUE_PDDL_SOURCE_FILES,
        ),
        "unique PDDL source bytes": (
            runner.EXPECTED_UNIQUE_PDDL_SOURCE_BYTES,
            EXPECTED_UNIQUE_PDDL_SOURCE_BYTES,
        ),
    }
    errors = []
    for label, (actual, expected) in exact.items():
        if not _same(actual, expected):
            errors.append("{}={!r}, expected {!r}".format(label, actual, expected))
    runner_configs = tuple(runner.PILOT_CONFIG_MATRIX)
    if runner_configs != PILOT_CONFIGS:
        errors.append("runner pilot option matrix changed")
    if tuple(runner.FIXED_VALIDATION_CONFIGS) != FIXED_CONFIGS:
        errors.append("runner fixed validation matrix changed")
    if dict(runner.BATCHED_SELECTOR_BASE) != BATCHED_SELECTOR_BASE:
        errors.append("runner same-K mapping changed")
    metadata_source = ""
    try:
        import inspect
        metadata_source = inspect.getsource(runner.make_protocol_metadata)
    except (OSError, TypeError):
        errors.append("cannot inspect runner metadata construction")
    for key in (
        "pdb_selector_parser_protocol",
        "selector_pool_protocol",
        "selector_score_version",
        "selector_source_order",
        "materialized_pddl_protocol",
        "materialized_pddl_files",
        "materialized_pddl_bytes",
        "pddl_bytes_per_config",
        "unique_pddl_source_files",
        "unique_pddl_source_bytes",
    ):
        if repr(key) not in metadata_source and '"{}"'.format(key) not in metadata_source:
            errors.append("runner static metadata omits {}".format(key))
    if expected_artifact_sha256 is not None and (
        runner.EXPECTED_SELECTION_ARTIFACT_SHA256 != expected_artifact_sha256
    ):
        errors.append(
            "runner selection-artifact pin={!r}, expected {!r}".format(
                runner.EXPECTED_SELECTION_ARTIFACT_SHA256,
                expected_artifact_sha256,
            )
        )
    if errors:
        raise AnalysisError("runner/analyzer contract mismatch: " + "; ".join(errors))


def require_reviewed_pins(
    artifact_sha256,
    *,
    expected_artifact_sha256=EXPECTED_SELECTION_ARTIFACT_SHA256,
    protocol_revision=EXPECTED_VALIDATION_PROTOCOL_REVISION,
    planner_revision=PLANNER_REVISION,
    pilot_protocol_revision=PILOT_PROTOCOL_REVISION,
    binary_sha256=CACHE_BINARY_SHA256,
    preprocess_sha256=CACHE_PREPROCESS_SHA256,
    cache_name_suffix=CACHE_NAME_SUFFIX,
):
    _require_sha256(artifact_sha256, "selection artifact raw digest")
    if expected_artifact_sha256 is None:
        raise AnalysisError(
            "EXPECTED_SELECTION_ARTIFACT_SHA256 is unset; review and pin the "
            "exact artifact bytes before ordinary analysis"
        )
    _require_sha256(expected_artifact_sha256, "reviewed selection artifact digest")
    if artifact_sha256 != expected_artifact_sha256:
        raise AnalysisError(
            "selection artifact bytes changed: expected {}, got {}".format(
                expected_artifact_sha256, artifact_sha256
            )
        )
    if protocol_revision is None:
        raise AnalysisError(
            "EXPECTED_VALIDATION_PROTOCOL_REVISION is unset; pin the clean "
            "held-out launch revision before ordinary analysis"
        )
    _require_revision(protocol_revision, "held-out protocol revision")
    _require_revision(planner_revision, "P4 planner revision")
    _require_revision(pilot_protocol_revision, "P4 screen protocol revision")
    _require_sha256(binary_sha256, "P4 cached planner digest")
    _require_sha256(preprocess_sha256, "P4 cached preprocess digest")
    if (
        not isinstance(cache_name_suffix, str)
        or not re.fullmatch(r"_[0-9a-f]{8}", cache_name_suffix)
    ):
        raise AnalysisError("P4 cache-name suffix is unset")
    return protocol_revision


def expected_component_options(search):
    return ["--search", common.search_config(search)]


def expected_protocol_metadata(contract, artifact_sha256, protocol_revision):
    run_count = contract["run_count"]
    return {
        "planner_revision": PLANNER_REVISION,
        "protocol_revision": protocol_revision,
        "planner_revision_is_protocol_ancestor": True,
        "planner_build_options": ["release_no_lp"],
        "planner_build_config": "release_no_lp",
        "planner_binary_sha256": CACHE_BINARY_SHA256,
        "planner_preprocess_sha256": CACHE_PREPROCESS_SHA256,
        "planner_revision_cache_name": (
            PLANNER_REVISION + CACHE_NAME_SUFFIX
            if isinstance(PLANNER_REVISION, str)
            and isinstance(CACHE_NAME_SUFFIX, str)
            else None
        ),
        "external_plan_validation": False,
        "plan_validation_protocol": (
            "no-external-val;canonical-plan-log-wbh-cost-and-raw-exit-"
            "reconciliation/v2"
        ),
        "plan_file_parser_protocol": (
            "sas_plan/exact-zero-or-single-stable-single-link-regular-"
            "nonsymlink-cost-footer/v2"
        ),
        "outcome_reconciliation_protocol": OUTCOME_RECONCILIATION_PROTOCOL,
        "cofactor_width_property": "cofactor_width",
        "cofactor_width_parser_protocol": (
            "run.log/unique-wbh-heuristic-cofactor-width/v1"
        ),
        "metrics_validation_protocol": METRICS_VALIDATION_PROTOCOL,
        "pdb_selector_parser_protocol": SELECTOR_PARSER_PROTOCOL,
        "selector_pool_protocol": SELECTOR_POOL_PROTOCOL,
        "selector_score_version": SELECTOR_SCORE_VERSION,
        "selector_source_order": list(SELECTOR_SOURCES),
        "python_version": EXPECTED_PYTHON_VERSION,
        "lab_version": EXPECTED_LAB_VERSION,
        "required_lab_version": EXPECTED_LAB_VERSION,
        "task_order_seed": (
            "symbolic-search-heuristics/arrhenius-task-order/v1"
        ),
        "task_order_method": (
            "sha256(seed-nul-array-count-nul-array-id)-sort;"
            "ascending-run-id-within-array-task/v1"
        ),
        "driver_time_limit": "300s",
        "driver_memory_limit": "8G",
        "scheduler_environment": "arrhenius-slurm",
        "scheduler_cluster": "arrhenius",
        "scheduler_cpu_model": "AMD EPYC 9755 128-Core Processor",
        "scheduler_partition": "cpu",
        "scheduler_qos": "normal",
        "scheduler_account": "naiss2025-5-561-cpu",
        "scheduler_time_limit_per_task": "00:10:00",
        "scheduler_memory_per_cpu": "9G",
        "scheduler_cpus_per_task": 1,
        "scheduler_array_task_throttle": 5,
        "scheduler_max_array_tasks": 1000,
        "scheduler_array_tasks": run_count,
        "scheduler_runs_per_array_task": 1,
        "declared_run_count": run_count,
        "repetitions": 1,
        "protocol": VALIDATION_PROTOCOL,
        "analysis_protocol": ANALYSIS_PROTOCOL,
        "selection_artifact_schema": ARTIFACT_SCHEMA,
        "selection_artifact_sha256": artifact_sha256,
        "selection_rule": SELECTION_RULE,
        "pilot_protocol": PILOT_PROTOCOL,
        "pilot_protocol_revision": PILOT_PROTOCOL_REVISION,
        "pilot_properties_canonical_sha256": contract[
            "pilot_properties_sha256"
        ],
        "pilot_option_matrix_sha256": PILOT_OPTION_MATRIX_SHA256,
        "pilot_selector_configs_sha256": PILOT_SELECTOR_CONFIGS_SHA256,
        "selector_eligibility_sha256": SELECTOR_ELIGIBILITY_SHA256,
        "global_winner": contract["global_winner"],
        "selector_family_winner": contract["selector_winner"],
        "matched_same_k_unbatched": contract["matched_unbatched"],
        "task_manifest": MANIFEST_NAME,
        "task_manifest_sha256": MANIFEST_SHA256,
        "task_count": EXPECTED_TASKS,
        "domain_count": EXPECTED_DOMAINS,
        "source_manifest_sha256": SOURCE_MANIFEST_SHA256,
        "task_sources_sha256": TASK_SOURCES_SHA256,
        "materialized_pddl_protocol": MATERIALIZED_PDDL_PROTOCOL,
        "materialized_pddl_files": EXPECTED_MATERIALIZED_PDDL_FILES[
            run_count
        ],
        "materialized_pddl_bytes": EXPECTED_MATERIALIZED_PDDL_BYTES[
            run_count
        ],
        "pddl_bytes_per_config": EXPECTED_PDDL_BYTES_PER_CONFIG,
        "unique_pddl_source_files": EXPECTED_UNIQUE_PDDL_SOURCE_FILES,
        "unique_pddl_source_bytes": EXPECTED_UNIQUE_PDDL_SOURCE_BYTES,
        "fixed_configs_sha256": FIXED_VALIDATION_CONFIGS_SHA256,
        "config_count": len(contract["configs"]),
        "option_matrix_sha256": contract["option_matrix_sha256"],
        "config_roles": copy.deepcopy(contract["config_records"]),
        "predeclared_comparisons": copy.deepcopy(contract["comparisons"]),
        "predeclared_comparisons_sha256": contract["comparisons_sha256"],
        "analysis_predeclaration": copy.deepcopy(ANALYSIS_PREDECLARATION),
        "experiment_data_directory": "data/exp_arrhenius_selector_validation",
        "benchmark_revision": BENCHMARK_REVISION,
        "benchmark_repository": BENCHMARK_REPOSITORY,
    }


def _cell_label(label, task):
    return "{} {}:{}".format(label, task[0], task[1])


def _append(errors, prefix, message):
    errors.append("{}: {}".format(prefix, message))


def _expected_ms_value_cap(search):
    match = re.search(r"(?:^|,)value_cap=(-?\d+)(?:,|\))", search)
    if not match:
        raise AnalysisError("cannot derive M&S value cap from {}".format(search))
    return int(match.group(1))


def _validate_metric_certification(record, prefix, errors):
    # First apply the shared semantic-property checks used for the screen.
    pilot_analyzer._validate_metrics(record, prefix, errors)
    exit_code = record.get("planner_exit_code")
    if exit_code in PRESEARCH_EXIT_CODES:
        if record.get("wbh_schema_version") != 1:
            _append(errors, prefix, "pre-search outcome must have the exact empty log")
        return
    if record.get("wbh_schema_version") != 2:
        _append(errors, prefix, "search outcome must use WBH schema v2")
        return
    if record.get("piece_metrics_certified") is not True:
        _append(errors, prefix, "schema-v2 event prefix is not semantically certified")
    if record.get("metrics_validation_error") is not None:
        _append(errors, prefix, "schema-v2 event prefix has validation diagnostics")
    complete = record.get("raw_metrics_complete")
    if complete is not True and exit_code not in RESOURCE_EXIT_CODES:
        _append(errors, prefix, "incomplete metrics require a resource exit")
    if complete is False and record.get("wbh_log_nonempty") is not True:
        _append(errors, prefix, "resource prefix is not marked nonempty")
    effort = record.get("effort")
    if record.get("coverage") == 1:
        if type(effort) is not int or effort < 0:
            _append(errors, prefix, "solved schema-v2 run needs nonnegative effort")
    elif "effort" in record:
        _append(errors, prefix, "unsolved run unexpectedly contains done-event effort")


HEURISTIC_FIELDS = (
    "cofactor_width",
    "width_upper_bound",
    "num_values",
    "num_terminals",
    "add_nodes",
)
CONSTRUCTION_FIELDS = (
    "construction_completed",
    "construction_time",
    "heuristic_kind",
    "heuristic_size_bound",
    "value_cap",
)


def _validate_heuristic(record, label, search, prefix, errors):
    if label == BLIND:
        unexpected = [
            field
            for field in CONSTRUCTION_FIELDS + HEURISTIC_FIELDS
            if field in record
        ]
        if unexpected:
            _append(
                errors,
                prefix,
                "blind run has heuristic fields {}".format(", ".join(unexpected)),
            )
        pilot_analyzer._validate_nonselector_pdb_trace(
            record, label, prefix, errors
        )
        return

    completed_present = "construction_completed" in record
    completed = record.get("construction_completed")
    if completed_present and type(completed) is not bool:
        _append(errors, prefix, "construction_completed must be boolean")
        return
    if not completed_present:
        stray = [field for field in CONSTRUCTION_FIELDS[1:] if field in record]
        if stray:
            _append(
                errors,
                prefix,
                "construction outcome absent but fields present: {}".format(
                    ", ".join(stray)
                ),
            )
        if record.get("coverage") == 1:
            _append(errors, prefix, "solved heuristic run lacks construction outcome")
        if record.get("planner_exit_code") not in (
            RESOURCE_EXIT_CODES | PRESEARCH_EXIT_CODES
        ):
            _append(
                errors,
                prefix,
                "missing construction requires a pre-search or resource exit",
            )
    else:
        construction_time = _finite_number(record.get("construction_time"))
        if construction_time is None or construction_time < 0:
            _append(errors, prefix, "construction_time must be finite and nonnegative")
        kind = record.get("heuristic_kind")
        size_bound = record.get("heuristic_size_bound")
        value_cap = record.get("value_cap")
        if label.startswith("ms_"):
            if kind != "merge_and_shrink":
                _append(errors, prefix, "M&S heuristic_kind changed")
            if size_bound != 10000 or type(size_bound) is not int:
                _append(errors, prefix, "M&S size bound must equal 10000")
            expected_cap = _expected_ms_value_cap(search)
            if value_cap != expected_cap or type(value_cap) is not int:
                _append(errors, prefix, "M&S value cap changed")
        elif label.startswith("pdb_"):
            expected_kind = (
                "pdb_exact_width_filter" if label in SELECTOR_LABELS else None
            )
            if expected_kind is not None and kind != expected_kind:
                _append(errors, prefix, "selector heuristic kind changed")
            if expected_kind is None and (
                not isinstance(kind, str) or not kind.startswith("pdb_")
            ):
                _append(errors, prefix, "legacy PDB heuristic kind changed")
            if size_bound != 100000 or type(size_bound) is not int:
                _append(errors, prefix, "PDB size bound must equal 100000")
            if value_cap != -1 or type(value_cap) is not int:
                _append(errors, prefix, "PDB value cap must equal -1")

    if completed is False:
        if label != MS_CAP32_BUILD60:
            _append(errors, prefix, "construction fallback is not enabled")
        if any(field in record for field in HEURISTIC_FIELDS):
            _append(errors, prefix, "blind fallback logged a heuristic")
        pilot_analyzer._validate_nonselector_pdb_trace(
            record, label, prefix, errors
        )
        return

    selector_prefix = (
        label in SELECTOR_LABELS
        and record.get("planner_exit_code") in RESOURCE_EXIT_CODES
        and record.get("pdb_selector_trace_certified") is True
        and not completed_present
        and "cofactor_width" in record
        and all(field not in record for field in HEURISTIC_FIELDS[1:])
    )
    if selector_prefix:
        if type(record.get("cofactor_width")) is not int or record["cofactor_width"] < 1:
            _append(errors, prefix, "selector prefix width must be positive")
    else:
        present = [field for field in HEURISTIC_FIELDS if field in record]
        if present and len(present) != len(HEURISTIC_FIELDS):
            _append(errors, prefix, "heuristic metric group is partially present")
        if completed is True and len(present) != len(HEURISTIC_FIELDS):
            _append(errors, prefix, "completed construction lacks heuristic metrics")
        if len(present) == len(HEURISTIC_FIELDS):
            width = record["cofactor_width"]
            upper = record["width_upper_bound"]
            values = record["num_values"]
            terminals = record["num_terminals"]
            nodes = record["add_nodes"]
            if type(width) is not int or width < 1:
                _append(errors, prefix, "cofactor width must be a positive integer")
            if type(upper) is not int or upper < 1:
                _append(errors, prefix, "width upper bound must be positive")
            if type(values) is not int or values < 1:
                _append(errors, prefix, "num_values must be positive")
            if type(terminals) is not int or terminals < 1:
                _append(errors, prefix, "num_terminals must be positive")
            if type(nodes) is not int or nodes < 0:
                _append(errors, prefix, "add_nodes must be nonnegative")
            if all(type(value) is int for value in (width, upper)) and width > upper:
                _append(errors, prefix, "cofactor width exceeds its upper bound")
            if all(type(value) is int for value in (width, terminals)) and width < terminals:
                _append(errors, prefix, "cofactor width is smaller than terminals")
            if all(type(value) is int for value in (upper, nodes, terminals)) and (
                upper != nodes + terminals
            ):
                _append(errors, prefix, "width_upper_bound != add_nodes + terminals")
            if all(type(value) is int for value in (values, terminals)) and values > terminals:
                _append(errors, prefix, "num_values exceeds terminals")

    if label in SELECTOR_LABELS:
        if completed is True or record.get("pdb_selector_trace_certified") is True:
            pool_hash = pilot_analyzer._validate_selector_trace(
                record, label, prefix, errors
            )
        else:
            pilot_analyzer._validate_interrupted_selector_trace(
                record, label, prefix, errors
            )
            pool_hash = None
        selected = record.get(common.PDB_SELECTOR_SELECTED_PROPERTY)
        if (
            isinstance(selected, dict)
            and selected.get("initial_dead_end") is True
            and record.get("planner_exit_code") not in (11, 22, 23, 24)
        ):
            _append(errors, prefix, "initial-dead selector has incompatible outcome")
        if record.get("planner_exit_code") in (11, 12) and completed is not True:
            _append(errors, prefix, "selector unsolvability lacks completed construction")
        return pool_hash
    pilot_analyzer._validate_nonselector_pdb_trace(record, label, prefix, errors)
    return None


def validate_records(
    records,
    tasks,
    contract,
    artifact_sha256,
    protocol_revision,
):
    labels = [label for label, _ in contract["configs"]]
    searches = dict(contract["configs"])
    expected_cells = contract["run_count"]
    task_set = set(tasks)
    label_set = set(labels)
    matrix = {}
    errors = []
    if len(records) != expected_cells:
        errors.append(
            "properties contain {} records; expected exactly {}".format(
                len(records), expected_cells
            )
        )
    for record in records:
        try:
            label, task = analyzer_utils.identity(record)
        except analyzer_utils.AnalysisError as err:
            errors.append(str(err))
            continue
        if label not in label_set:
            errors.append("unexpected algorithm {}".format(label))
            continue
        if task not in task_set:
            errors.append("record outside held-out manifest {}:{}".format(*task))
            continue
        key = (label, task)
        if key in matrix:
            errors.append("duplicate cell {}".format(_cell_label(label, task)))
        else:
            matrix[key] = record
    missing = [
        (label, task)
        for label in labels
        for task in tasks
        if (label, task) not in matrix
    ]
    if missing:
        errors.append(
            "missing {} expected cells; first: {}".format(
                len(missing),
                ", ".join(_cell_label(*item) for item in missing[:8]),
            )
        )
    if len(matrix) != expected_cells:
        errors.append(
            "matrix contains {} cells; expected {}".format(
                len(matrix), expected_cells
            )
        )

    static = expected_protocol_metadata(
        contract, artifact_sha256, protocol_revision
    )
    driver_options = [
        "--overall-time-limit",
        "30m",
        "--overall-memory-limit",
        "3584M",
        "--build",
        "release_no_lp",
        "--overall-time-limit",
        "300s",
        "--overall-memory-limit",
        "8G",
    ]
    costs_by_task = defaultdict(list)
    unsolvable_by_task = defaultdict(list)
    pool_hashes_by_task = defaultdict(dict)
    benchmark_worktrees = set()
    for label in labels:
        for task in tasks:
            record = matrix.get((label, task))
            if record is None:
                continue
            prefix = _cell_label(label, task)
            if record.get("id") != [label, task[0], task[1]]:
                _append(errors, prefix, "id is not the exact cell identity")
            if record.get("algorithm") != label:
                _append(errors, prefix, "algorithm identity changed")
            if record.get("domain") != task[0] or record.get("problem") != task[1]:
                _append(errors, prefix, "task identity changed")
            if record.get("component_options") != expected_component_options(
                searches[label]
            ):
                _append(errors, prefix, "component options changed")
            if record.get("driver_options") != driver_options:
                _append(errors, prefix, "driver options changed")
            if record.get("build_options") != ["release_no_lp"]:
                _append(errors, prefix, "build options changed")
            for field in ("local_revision", "global_revision"):
                if record.get(field) != PLANNER_REVISION:
                    _append(errors, prefix, "{} changed".format(field))
            for field, expected in (
                ("planner_time_limit", TIME_LIMIT_SECONDS),
                ("planner_memory_limit", MEMORY_LIMIT_MIB),
            ):
                actual = _finite_number(record.get(field))
                if actual is None or actual != expected:
                    _append(errors, prefix, "{} changed".format(field))
            for field, expected in static.items():
                if field not in record or not _same(record.get(field), expected):
                    _append(
                        errors,
                        prefix,
                        "{}={!r}, expected {!r}".format(
                            field, record.get(field), expected
                        ),
                    )
            worktree = record.get("benchmark_worktree")
            if (
                not isinstance(worktree, str)
                or not worktree
                or not Path(worktree).is_absolute()
            ):
                _append(errors, prefix, "benchmark_worktree is not absolute")
            else:
                benchmark_worktrees.add(worktree)

            pilot_analyzer._validate_outcome(record, prefix, errors)
            _validate_metric_certification(record, prefix, errors)
            pool_hash = _validate_heuristic(
                record, label, searches[label], prefix, errors
            )
            if pool_hash is not None:
                pool_hashes_by_task[task][label] = pool_hash
                if record.get("pdb_selector_pool_sha256") != pool_hash:
                    _append(errors, prefix, "selector pool hash disagrees")
            if record.get("coverage") == 1 and type(record.get("solution_cost")) is int:
                costs_by_task[task].append((label, record["solution_cost"]))
            if record.get("coverage") == 0 and record.get("unsolvable") == 1:
                unsolvable_by_task[task].append(label)

    if len(benchmark_worktrees) != 1:
        errors.append("records do not have one consistent absolute benchmark worktree")
    for task in tasks:
        solved = costs_by_task.get(task, [])
        if len({cost for _, cost in solved}) > 1:
            errors.append(
                "solved-cost disagreement on {}:{}: {}".format(
                    task[0],
                    task[1],
                    ", ".join("{}={}".format(label, cost) for label, cost in solved),
                )
            )
        if solved and unsolvable_by_task.get(task):
            errors.append(
                "solved/proved-unsolvable disagreement on {}:{}".format(*task)
            )
    for task, labelled in sorted(pool_hashes_by_task.items()):
        if len(set(labelled.values())) > 1:
            errors.append(
                "same-task selector pool disagreement on {}:{}".format(*task)
            )
    if errors:
        shown = errors[:60]
        suffix = ""
        if len(errors) > len(shown):
            suffix = "\n... {} more".format(len(errors) - len(shown))
        raise AnalysisError(
            "held-out validation failed ({} errors):\n{}{}".format(
                len(errors), "\n".join("- " + item for item in shown), suffix
            )
        )
    return matrix


def logical_properties_sha256(records):
    normalized = [
        {key: value for key, value in record.items() if key != "_source_key"}
        for record in records
    ]
    normalized.sort(
        key=lambda record: (
            record.get("algorithm", ""),
            record.get("domain", ""),
            record.get("problem", ""),
            canonical_json(record),
        )
    )
    return sha256_json(normalized)


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
    numeric = [float(value) for value in values]
    return {
        "observed": len(values),
        "minimum": min(values),
        "median": statistics.median(values),
        "maximum": max(values),
        "mean": math.fsum(numeric) / len(numeric),
        "total": math.fsum(numeric),
    }


def _par2(record):
    return (
        float(record["planner_time"])
        if record["coverage"] == 1
        else PAR2_UNSOLVED_SECONDS
    )


def summarize_config(matrix, tasks, label, search, roles):
    records = [matrix[(label, task)] for task in tasks]
    solved = [record for record in records if record["coverage"] == 1]
    complete = [
        record for record in records if record.get("raw_metrics_complete") is True
    ]
    certified = [
        record
        for record in records
        if record.get("piece_metrics_certified") is True
        and record.get("metrics_validation_error") is None
        and record.get("wbh_schema_version") == 2
    ]
    construction = [
        record for record in records if "construction_completed" in record
    ]
    widths = [
        record["cofactor_width"]
        for record in records
        if type(record.get("cofactor_width")) is int
    ]
    efforts = [record["effort"] for record in solved]
    return {
        "label": label,
        "search": search,
        "roles": list(roles),
        "coverage": {
            "solved": len(solved),
            "tasks": len(tasks),
            "rate": len(solved) / len(tasks),
        },
        "micro_par2_seconds": math.fsum(_par2(record) for record in records)
        / len(tasks),
        "solved_planner_time_seconds": _summary(
            record["planner_time"] for record in solved
        ),
        "construction": {
            "observed": len(construction),
            "completed": sum(
                record["construction_completed"] is True
                for record in construction
            ),
            "fallbacks": sum(
                record["construction_completed"] is False
                for record in construction
            ),
            "unobserved_resource_prefixes": len(records) - len(construction),
            "time_seconds": _summary(
                record["construction_time"] for record in construction
            ),
        },
        "cofactor_width": _summary(widths),
        "image_time_seconds": {
            "semantically_certified_prefix_cells": len(certified),
            "complete_summary_cells": len(complete),
            "presearch_empty_cells": sum(
                record.get("planner_exit_code") in PRESEARCH_EXIT_CODES
                for record in records
            ),
            "certified_prefix": _summary(
                record["image_time"] for record in certified
            ),
            "complete_summary": _summary(
                record["image_time"] for record in complete
            ),
        },
        "effort_on_solved_cells": _summary(efforts),
    }


def _aggregate_ratio(candidate, reference):
    candidate_total = math.fsum(float(value) for value in candidate)
    reference_total = math.fsum(float(value) for value in reference)
    return {
        "candidate_total": candidate_total,
        "reference_total": reference_total,
        "candidate_over_reference": (
            candidate_total / reference_total if reference_total > 0 else None
        ),
        "candidate_minus_reference": candidate_total - reference_total,
    }


def compare(matrix, tasks, declaration):
    candidate = declaration["candidate"]
    reference = declaration["reference"]
    wins = losses = both_solved = both_unsolved = 0
    candidate_par2 = []
    reference_par2 = []
    runtime_ratios = []
    paired_image_candidate = []
    paired_image_reference = []
    paired_width_candidate = []
    paired_width_reference = []
    paired_effort_candidate = []
    paired_effort_reference = []
    paired_construction_candidate = []
    paired_construction_reference = []
    for task in tasks:
        cand = matrix[(candidate, task)]
        ref = matrix[(reference, task)]
        cand_solved = cand["coverage"] == 1
        ref_solved = ref["coverage"] == 1
        if cand_solved and not ref_solved:
            wins += 1
        elif ref_solved and not cand_solved:
            losses += 1
        elif cand_solved:
            both_solved += 1
            cand_time = float(cand["planner_time"])
            ref_time = float(ref["planner_time"])
            if cand_time <= 0 or ref_time <= 0:
                raise AnalysisError(
                    "jointly solved runtime ratio is undefined for nonpositive "
                    "planner time on {}:{}".format(*task)
                )
            runtime_ratios.append(cand_time / ref_time)
        else:
            both_unsolved += 1
        candidate_par2.append(_par2(cand))
        reference_par2.append(_par2(ref))
        if (
            cand.get("raw_metrics_complete") is True
            and ref.get("raw_metrics_complete") is True
        ):
            paired_image_candidate.append(cand["image_time"])
            paired_image_reference.append(ref["image_time"])
        if type(cand.get("cofactor_width")) is int and type(
            ref.get("cofactor_width")
        ) is int:
            paired_width_candidate.append(cand["cofactor_width"])
            paired_width_reference.append(ref["cofactor_width"])
        if type(cand.get("effort")) is int and type(ref.get("effort")) is int:
            paired_effort_candidate.append(cand["effort"])
            paired_effort_reference.append(ref["effort"])
        if _finite_number(cand.get("construction_time")) is not None and (
            _finite_number(ref.get("construction_time")) is not None
        ):
            paired_construction_candidate.append(cand["construction_time"])
            paired_construction_reference.append(ref["construction_time"])
    runtime_geomean = (
        math.exp(
            math.fsum(math.log(value) for value in runtime_ratios)
            / len(runtime_ratios)
        )
        if runtime_ratios
        else None
    )
    candidate_micro = math.fsum(candidate_par2) / len(tasks)
    reference_micro = math.fsum(reference_par2) / len(tasks)
    return {
        "name": declaration["name"],
        "candidate": candidate,
        "reference": reference,
        "roles": list(declaration["roles"]),
        "coverage": {
            "candidate_minus_reference_tasks": wins - losses,
            "candidate_minus_reference_rate": (wins - losses) / len(tasks),
            "discordant_candidate_wins": wins,
            "discordant_candidate_losses": losses,
            "both_solved": both_solved,
            "both_unsolved": both_unsolved,
        },
        "micro_par2_seconds": {
            "candidate": candidate_micro,
            "reference": reference_micro,
            "candidate_minus_reference": candidate_micro - reference_micro,
        },
        "jointly_solved_runtime": {
            "pairs": len(runtime_ratios),
            "candidate_over_reference_geometric_mean": runtime_geomean,
            "ratio_summary": _summary(runtime_ratios),
        },
        "paired_complete_image_time_seconds": {
            "pairs": len(paired_image_candidate),
            **_aggregate_ratio(
                paired_image_candidate, paired_image_reference
            ),
        },
        "paired_observed_cofactor_width": {
            "pairs": len(paired_width_candidate),
            **_aggregate_ratio(
                paired_width_candidate, paired_width_reference
            ),
        },
        "paired_solved_effort": {
            "pairs": len(paired_effort_candidate),
            **_aggregate_ratio(
                paired_effort_candidate, paired_effort_reference
            ),
        },
        "paired_observed_construction_time_seconds": {
            "pairs": len(paired_construction_candidate),
            **_aggregate_ratio(
                paired_construction_candidate,
                paired_construction_reference,
            ),
        },
    }


def _fraction_record(numerator, denominator):
    value = Fraction(numerator, denominator)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }


def bootstrap_primary(matrix, tasks, candidate, reference):
    by_domain = defaultdict(list)
    for task in tasks:
        by_domain[task[0]].append(task)
    domains = sorted(by_domain)
    if len(domains) != EXPECTED_DOMAINS or any(
        len(by_domain[domain]) != 2 for domain in domains
    ):
        raise AnalysisError("primary bootstrap requires 46 domains of two tasks")
    # Each domain numerator is the sum of two {-1,0,1} task differences.
    numerators = []
    contributions = []
    for domain in domains:
        domain_tasks = by_domain[domain]
        differences = [
            matrix[(candidate, task)]["coverage"]
            - matrix[(reference, task)]["coverage"]
            for task in domain_tasks
        ]
        numerator = sum(differences)
        numerators.append(numerator)
        contributions.append(
            {
                "domain": domain,
                "task_count": 2,
                "candidate_solved": sum(
                    matrix[(candidate, task)]["coverage"] for task in domain_tasks
                ),
                "reference_solved": sum(
                    matrix[(reference, task)]["coverage"] for task in domain_tasks
                ),
                "difference": _fraction_record(numerator, 2),
            }
        )
    denominator = 2 * len(domains)
    prefix = (
        BOOTSTRAP_SEED.encode("utf-8")
        + b"\0"
        + PRIMARY_COMPARISON.encode("utf-8")
        + b"\0"
    )
    replicate_numerators = []
    counter = 0
    for _ in range(BOOTSTRAP_REPLICATES):
        total = 0
        for _ in domains:
            digest = hashlib.sha256(
                prefix + counter.to_bytes(8, "big")
            ).digest()
            index = int.from_bytes(digest[:8], "big") % len(domains)
            total += numerators[index]
            counter += 1
        replicate_numerators.append(total)
    replicate_numerators.sort()
    # Exact integer forms of floor(.025*(R-1)) and ceil(.975*(R-1)).
    lower_index = (25 * (BOOTSTRAP_REPLICATES - 1)) // 1000
    upper_index = (
        975 * (BOOTSTRAP_REPLICATES - 1) + 999
    ) // 1000
    packed = b"".join(
        int(value).to_bytes(2, "big", signed=True)
        for value in replicate_numerators
    )
    return {
        "comparison": PRIMARY_COMPARISON,
        "candidate": candidate,
        "reference": reference,
        "estimand": PRIMARY_ESTIMAND,
        "tasks": len(tasks),
        "domains": len(domains),
        "domain_order": domains,
        "domain_contributions": contributions,
        "estimate": _fraction_record(sum(numerators), denominator),
        "bootstrap": {
            "method": BOOTSTRAP_METHOD,
            "seed": BOOTSTRAP_SEED,
            "counter_encoding": BOOTSTRAP_COUNTER_ENCODING,
            "replicates": BOOTSTRAP_REPLICATES,
            "resampling_unit": "domain",
            "draws_per_replicate": len(domains),
            "confidence_level": CONFIDENCE_LEVEL,
            "interval_rule": BOOTSTRAP_INTERVAL_RULE,
            "lower_order_index_zero_based": lower_index,
            "upper_order_index_zero_based": upper_index,
            "lower": _fraction_record(
                replicate_numerators[lower_index], denominator
            ),
            "upper": _fraction_record(
                replicate_numerators[upper_index], denominator
            ),
            "sorted_replicate_numerators_sha256": hashlib.sha256(packed).hexdigest(),
        },
    }


def analyze(records, tasks, contract, artifact_sha256, protocol_revision):
    matrix = validate_records(
        records, tasks, contract, artifact_sha256, protocol_revision
    )
    roles = {item["label"]: item["roles"] for item in contract["config_records"]}
    config_summaries = [
        summarize_config(matrix, tasks, label, search, roles[label])
        for label, search in contract["configs"]
    ]
    comparisons = [
        compare(matrix, tasks, declaration)
        for declaration in contract["comparisons"]
    ]
    primary_decl = next(
        item for item in contract["comparisons"] if item["name"] == PRIMARY_COMPARISON
    )
    primary = bootstrap_primary(
        matrix,
        tasks,
        primary_decl["candidate"],
        primary_decl["reference"],
    )
    primary_pair = next(
        item for item in comparisons if item["name"] == PRIMARY_COMPARISON
    )
    primary_task_delta = Fraction(
        primary["estimate"]["numerator"],
        primary["estimate"]["denominator"],
    ) * EXPECTED_TASKS
    if primary_task_delta != primary_pair["coverage"][
        "candidate_minus_reference_tasks"
    ]:
        raise AnalysisError("primary paired summary disagrees with estimand")
    primary["paired_descriptive_metrics"] = primary_pair
    budget = next(
        item for item in config_summaries if item["label"] == MS_CAP32_BUILD60
    )
    result = {
        "schema": ANALYSIS_SCHEMA,
        "analysis_protocol": ANALYSIS_PROTOCOL,
        "selection_artifact": {
            "schema": ARTIFACT_SCHEMA,
            "raw_sha256": artifact_sha256,
            "global_winner_alias": contract["global_winner"],
            "selector_family_winner": contract["selector_winner"],
            "matched_same_k_unbatched": contract["matched_unbatched"],
        },
        "execution": {
            "protocol": VALIDATION_PROTOCOL,
            "protocol_revision": protocol_revision,
            "planner_revision": PLANNER_REVISION,
            "planner_binary_sha256": CACHE_BINARY_SHA256,
            "planner_preprocess_sha256": CACHE_PREPROCESS_SHA256,
            "benchmark_revision": BENCHMARK_REVISION,
            "task_manifest_sha256": MANIFEST_SHA256,
            "task_sources_sha256": TASK_SOURCES_SHA256,
            "option_matrix_sha256": contract["option_matrix_sha256"],
            "predeclared_comparisons_sha256": contract["comparisons_sha256"],
            "properties_canonical_sha256": logical_properties_sha256(records),
            "task_count": EXPECTED_TASKS,
            "domain_count": EXPECTED_DOMAINS,
            "config_count": len(contract["configs"]),
            "cell_count": contract["run_count"],
            "materialized_pddl_protocol": contract[
                "materialized_pddl_protocol"
            ],
            "materialized_pddl_files": contract["materialized_pddl_files"],
            "materialized_pddl_bytes": contract["materialized_pddl_bytes"],
        },
        "decision_policy": {
            "rerank_on_validation": False,
            "configuration_order_source": "selection-artifact-v3",
            "comparisons_source": "selection-artifact-v3",
        },
        "primary": primary,
        "secondary": {
            "status": "descriptive",
            "metric_protocols": {
                "suite_micro_coverage": "solved-cells/92/v1",
                "micro_par2": "mean(solved-planner-time;unsolved=600s)/v1",
                "jointly_solved_runtime_ratio": (
                    "geometric-mean(candidate-planner-time/reference-planner-time);"
                    "strictly-positive-jointly-solved-cells/v1"
                ),
                "paired_operational_ratios": (
                    "ratio-of-paired-totals-with-explicit-pair-count/v1"
                ),
                "certified_prefix_metrics": (
                    "schema-v2-piece-certified-event-prefix;complete-summary-"
                    "denominator-reported-separately/v1"
                ),
                "fallback_incidence": (
                    "construction_completed=false/ms-cap32-build60-cells/v1"
                ),
            },
            "configs": config_summaries,
            "comparisons": [
                item for item in comparisons if item["name"] != PRIMARY_COMPARISON
            ],
            "ms_build_budget_fallback": {
                "label": MS_CAP32_BUILD60,
                "fallbacks": budget["construction"]["fallbacks"],
                "cells": EXPECTED_TASKS,
                "incidence": budget["construction"]["fallbacks"] / EXPECTED_TASKS,
            },
        },
    }
    # Round-trip through canonical serialization to guarantee finite JSON and
    # make accidental tuples/custom numbers impossible at the public boundary.
    return json.loads(canonical_json(result))


def _synthetic_record(
    label,
    search,
    task,
    contract,
    artifact_sha256,
    protocol_revision,
    solved,
    planner_time,
    cost,
    fallback=False,
):
    domain, problem = task
    record = {
        "_source_key": "{}-{}-{}".format(label, domain, problem),
        "id": [label, domain, problem],
        "algorithm": label,
        "domain": domain,
        "problem": problem,
        "coverage": int(solved),
        "planner_exit_code": 0 if solved else 23,
        "search_raw_exit_code": 0 if solved else 23,
        "search_effective_exit_code": 0 if solved else 23,
        "outcome_reconciliation_protocol": OUTCOME_RECONCILIATION_PROTOCOL,
        "outcome_reconciliation_certified": True,
        "error": "success" if solved else "search-out-of-time",
        "unsolvable": 0,
        "plan_file_present": bool(solved),
        "plan_file_candidate_count": 1 if solved else 0,
        "plan_file_canonical": bool(solved),
        "component_options": expected_component_options(search),
        "driver_options": [
            "--overall-time-limit",
            "30m",
            "--overall-memory-limit",
            "3584M",
            "--build",
            "release_no_lp",
            "--overall-time-limit",
            "300s",
            "--overall-memory-limit",
            "8G",
        ],
        "build_options": ["release_no_lp"],
        "global_revision": PLANNER_REVISION,
        "local_revision": PLANNER_REVISION,
        "planner_time_limit": TIME_LIMIT_SECONDS,
        "planner_memory_limit": MEMORY_LIMIT_MIB,
        "benchmark_worktree": "/synthetic/downward-benchmarks",
        "wbh_log_nonempty": True,
        "raw_metrics_complete": True,
        "piece_metrics_certified": True,
        "wbh_summary_solved": bool(solved),
        "wbh_done_solution_cost": cost if solved else None,
        "wbh_solved_summary_certified": bool(solved),
        "expanded_bdd_nodes": 40,
        "expanded_states": 100.0,
        "expanded_bdd_pieces": 10,
        "attempted_bdd_nodes": 50,
        "attempted_states": 120.0,
        "attempted_bdd_pieces": 12,
        "bucket_expansions": 8,
        "bucket_expansion_attempts": 10,
        "image_events": 6,
        "bucket_images": 6,
        "image_source_buckets": 7,
        "image_source_pieces": 8,
        "image_calls_attempted": 7,
        "image_calls_completed": 6,
        "batched_images": 1,
        "image_time": 2.0,
        **SCHEMA_V2_CONVENTIONS,
        **expected_protocol_metadata(contract, artifact_sha256, protocol_revision),
    }
    if solved:
        record.update(
            {
                "solution_cost": cost,
                "plan_file_cost": cost,
                "run_log_plan_cost": cost,
                "planner_time": planner_time,
                "effort": 17,
            }
        )
    if label == BLIND:
        return record
    record.update(
        {
            "construction_completed": not fallback,
            "construction_time": 60.25 if fallback else 0.25,
        }
    )
    if label.startswith("ms_"):
        record.update(
            {
                "heuristic_kind": "merge_and_shrink",
                "heuristic_size_bound": 10000,
                "value_cap": _expected_ms_value_cap(search),
            }
        )
        if not fallback:
            record.update(
                {
                    "cofactor_width": 5,
                    "width_upper_bound": 25,
                    "num_values": 5,
                    "num_terminals": 5,
                    "add_nodes": 20,
                }
            )
    elif label in SELECTOR_LABELS:
        pilot_analyzer._attach_selector_trace(record, label)
    else:
        record.update(
            {
                "heuristic_kind": (
                    "pdb_cegar" if "cegar" in label else "pdb_goal_fill"
                ),
                "heuristic_size_bound": 100000,
                "value_cap": -1,
                "cofactor_width": 5,
                "width_upper_bound": 25,
                "num_values": 5,
                "num_terminals": 5,
                "add_nodes": 20,
                "pdb_final_format": "legacy",
                "pdb_pattern_size": 2,
                "pdb_final_num_values": 5,
                "pdb_final_cofactor_width": 5,
                "pdb_final_width_upper_bound": 25,
            }
        )
    return record


def _synthetic_case(selector_label):
    global_label = (
        selector_label if selector_label in BATCHED_SELECTOR_BASE else "ms_cap32"
    )
    artifact = runner._synthetic_artifact(global_label, selector_label)
    raw = canonical_json(artifact).encode("ascii")
    artifact_sha256 = hashlib.sha256(raw).hexdigest()
    contract = validate_selection_artifact(copy.deepcopy(artifact))
    tasks = load_and_validate_tasks()
    protocol_revision = "0123456789abcdef0123456789abcdef01234567"
    records = []
    for label, search in contract["configs"]:
        for index, task in enumerate(tasks):
            if label == contract["selector_winner"]:
                solved = index % 13 != 0
            elif label == CEGAR:
                solved = index % 11 != 0
            else:
                solved = index % 17 != 0
            fallback = label == MS_CAP32_BUILD60 and index % 7 == 0
            records.append(
                _synthetic_record(
                    label,
                    search,
                    task,
                    contract,
                    artifact_sha256,
                    protocol_revision,
                    solved,
                    1.0 + (index % 9) + len(label) / 100.0,
                    index + 1,
                    fallback=fallback,
                )
            )
    return artifact, artifact_sha256, contract, tasks, protocol_revision, records


def _expect_error(fn, fragment):
    try:
        fn()
    except AnalysisError as err:
        if fragment not in str(err):
            raise AssertionError(
                "expected {!r}, got {!r}".format(fragment, str(err))
            ) from err
    else:
        raise AssertionError("expected AnalysisError containing {!r}".format(fragment))


def self_test():
    # Runner hash remains intentionally unset before the real screen. Static
    # runner-source checks still apply; hash equality is tested with a local
    # override after artifact generation.
    validate_runner_contract(expected_artifact_sha256=None)
    with contextlib.redirect_stdout(io.StringIO()):
        common.self_test_cofactor_width_parser()
        common.self_test_pdb_selector_parser()
        common.self_test_pddl_materialization()
    if _parse_json_bytes(b'{"a":1}', "synthetic") != {"a": 1}:
        raise AssertionError("strict JSON parser changed")
    _expect_error(
        lambda: _parse_json_bytes(b'{"a":1,"a":2}', "synthetic"),
        "duplicate JSON key",
    )
    _expect_error(
        lambda: _parse_json_bytes(b'{"a":NaN}', "synthetic"),
        "non-finite JSON",
    )
    with tempfile.TemporaryDirectory(prefix="heldout-loader-selftest-") as raw:
        root = Path(raw)
        root_properties = root / "properties"
        root_properties.write_bytes(b"{}")
        eval_properties = root / "synthetic-eval" / "properties"
        eval_properties.parent.mkdir()
        eval_properties.write_bytes(b"{}")
        _expect_error(
            lambda: _properties_file_in_directory(root),
            "contains 2 properties candidates",
        )
        root_properties.unlink()
        if _properties_file_in_directory(root) != eval_properties:
            raise AssertionError("unique nested evaluation properties changed")
        linked_root = root / "linked-input"
        linked_root.mkdir()
        linked_eval = linked_root / "linked-eval"
        linked_eval.symlink_to(eval_properties.parent, target_is_directory=True)
        _expect_error(
            lambda: _properties_file_in_directory(linked_root),
            "symlinked properties candidates",
        )

    cases = []
    for selector_label, expected_runs in (
        ("pdb_selector_k32", 644),
        ("pdb_selector_k64_adapt_w64_r1_n1m", 736),
    ):
        case = _synthetic_case(selector_label)
        artifact, digest, contract, tasks, revision, records = case
        if contract["run_count"] != expected_runs or len(records) != expected_runs:
            raise AssertionError("synthetic 644/736 layout changed")
        if (
            contract["materialized_pddl_protocol"]
            != MATERIALIZED_PDDL_PROTOCOL
            or contract["materialized_pddl_files"]
            != EXPECTED_MATERIALIZED_PDDL_FILES[expected_runs]
            or contract["materialized_pddl_bytes"]
            != EXPECTED_MATERIALIZED_PDDL_BYTES[expected_runs]
            or contract["pddl_bytes_per_config"]
            != EXPECTED_PDDL_BYTES_PER_CONFIG
        ):
            raise AssertionError("synthetic materialized PDDL contract changed")
        result = analyze(records, tasks, contract, digest, revision)
        if result["decision_policy"]["rerank_on_validation"] is not False:
            raise AssertionError("held-out analyzer reranked configurations")
        if result["primary"]["candidate"] != selector_label:
            raise AssertionError("primary candidate differs from frozen selector")
        if result["primary"]["bootstrap"]["replicates"] != 100000:
            raise AssertionError("bootstrap replicate count changed")
        if result["execution"]["cell_count"] != expected_runs:
            raise AssertionError("analysis cell count changed")
        if 1 + len(result["secondary"]["comparisons"]) != len(
            contract["comparisons"]
        ):
            raise AssertionError("declared comparison output is incomplete")
        cases.append((case, result))

    # The same primary outcomes produce identical bootstrap streams regardless
    # of whether the artifact adds the conditional batching ablation.
    first_bootstrap = cases[0][1]["primary"]["bootstrap"]
    second_bootstrap = cases[1][1]["primary"]["bootstrap"]
    if (
        first_bootstrap["sorted_replicate_numerators_sha256"]
        != second_bootstrap["sorted_replicate_numerators_sha256"]
    ):
        raise AssertionError("bootstrap stream depends on non-primary configs")
    if first_bootstrap["sorted_replicate_numerators_sha256"] != (
        SYNTHETIC_BOOTSTRAP_SHA256
    ):
        raise AssertionError("SHA-256 counter bootstrap stream changed")
    if (
        first_bootstrap["lower_order_index_zero_based"] != 2499
        or first_bootstrap["upper_order_index_zero_based"] != 97500
        or first_bootstrap["lower"] != {
            "numerator": -7,
            "denominator": 92,
            "value": -7 / 92,
        }
        or first_bootstrap["upper"] != {
            "numerator": 9,
            "denominator": 92,
            "value": 9 / 92,
        }
    ):
        raise AssertionError("bootstrap percentile semantics changed")

    case, _ = cases[0]
    artifact, digest, contract, tasks, revision, records = case
    synthetic_identity_pins = {
        "planner_revision": "89abcdef0123456789abcdef0123456789abcdef",
        "pilot_protocol_revision": "fedcba9876543210fedcba9876543210fedcba98",
        "binary_sha256": hashlib.sha256(b"synthetic heldout binary").hexdigest(),
        "preprocess_sha256": hashlib.sha256(
            b"synthetic heldout preprocess"
        ).hexdigest(),
        "cache_name_suffix": "_1234abcd",
    }

    changed_artifact = copy.deepcopy(artifact)
    changed_artifact["validation"]["analysis"]["rerank_on_validation"] = True
    _expect_error(
        lambda: validate_selection_artifact(changed_artifact),
        "invalid selection artifact",
    )
    _expect_error(
        lambda: require_reviewed_pins(
            digest,
            expected_artifact_sha256="abcdef" * 10 + "abcd",
            protocol_revision=revision,
            **synthetic_identity_pins,
        ),
        "changed",
    )
    if require_reviewed_pins(
        digest,
        expected_artifact_sha256=digest,
        protocol_revision=revision,
        **synthetic_identity_pins,
    ) != revision:
        raise AssertionError("reviewed-pin override changed")

    def validate_mutation(mutator):
        changed = copy.deepcopy(records)
        mutator(changed)
        validate_records(changed, tasks, contract, digest, revision)

    # Legitimate resource-censored schema-v2 prefixes retain certified event
    # counters but have no summary. A translation failure has the exact empty
    # schema-less parser record and no construction fields.
    resource_prefix = copy.deepcopy(records)
    resource_target = next(
        item
        for item in resource_prefix
        if item["algorithm"] == BLIND and item["coverage"] == 0
    )
    resource_target["raw_metrics_complete"] = False
    resource_target["wbh_summary_solved"] = None
    validate_records(resource_prefix, tasks, contract, digest, revision)

    presearch = copy.deepcopy(records)
    presearch_target = next(
        item
        for item in presearch
        if item["algorithm"] == "ms_cap32" and item["coverage"] == 0
    )
    for field in (
        *ALL_SCHEMA_V2_METRICS,
        *SCHEMA_V2_CONVENTIONS,
        *CONSTRUCTION_FIELDS,
        *HEURISTIC_FIELDS,
        "search_raw_exit_code",
        "search_effective_exit_code",
        "wbh_summary_solved",
        "wbh_done_solution_cost",
        "wbh_solved_summary_certified",
    ):
        presearch_target.pop(field, None)
    presearch_target.update(
        {
            "planner_exit_code": 20,
            "error": "translate-out-of-memory",
            "unsolvable": 0,
            "wbh_schema_version": 1,
            "node_count_convention": "legacy_cudd_dag_size",
            "image_count_convention": "legacy_expand_event_count",
            "expansion_count_convention": "legacy_attempts_unmarked",
            "wbh_log_nonempty": False,
            "raw_metrics_complete": False,
            "piece_metrics_certified": False,
        }
    )
    validate_records(presearch, tasks, contract, digest, revision)

    _expect_error(
        lambda: validate_records(records[:-1], tasks, contract, digest, revision),
        "expected exactly 644",
    )
    _expect_error(
        lambda: validate_records(
            records + [copy.deepcopy(records[0])],
            tasks,
            contract,
            digest,
            revision,
        ),
        "duplicate cell",
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[0].update(
                {"selection_artifact_sha256": "1" * 64}
            )
        ),
        "selection_artifact_sha256",
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[0].update(
                {"component_options": ["--search", "sym_fw()"]}
            )
        ),
        "component options",
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[0].update(
                {"task_sources_sha256": "2" * 64}
            )
        ),
        "task_sources_sha256",
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[0].update(
                {"metrics_validation_protocol": "changed"}
            )
        ),
        "metrics_validation_protocol",
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[0].update({"planner_exit_code": 99})
        ),
        "predeclared explained outcome",
    )
    solved_index = next(
        index for index, record in enumerate(records) if record["coverage"] == 1
    )
    mapped = copy.deepcopy(records[solved_index])
    mapped.update(
        planner_exit_code=2,
        search_raw_exit_code=23,
        search_effective_exit_code=2,
        error="search-plan-found-and-out-of-time",
    )
    mapped_errors = []
    pilot_analyzer._validate_outcome(mapped, "heldout mapped", mapped_errors)
    if mapped_errors:
        raise AssertionError("valid mapped held-out outcome failed: {!r}".format(
            mapped_errors
        ))
    for field, value, fragment in (
        ("search_raw_exit_code", 24, "raw resource exit 23"),
        ("outcome_reconciliation_certified", False, "not certified"),
        ("plan_file_candidate_count", 2, "exactly one plan candidate"),
        ("plan_file_canonical", False, "canonical plan certification"),
        ("run_log_plan_cost", mapped["solution_cost"] + 1, "disagrees"),
        ("wbh_solved_summary_certified", False, "requires"),
    ):
        changed = copy.deepcopy(mapped)
        changed[field] = value
        changed_errors = []
        pilot_analyzer._validate_outcome(
            changed, "heldout mapped", changed_errors
        )
        if not any(fragment in error for error in changed_errors):
            raise AssertionError(
                "held-out mapped mutation {} was accepted: {!r}".format(
                    field, changed_errors
                )
            )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[solved_index].update(
                {"plan_file_cost": values[solved_index]["solution_cost"] + 1}
            )
        ),
        "plan_file_cost",
    )
    other_same_task = next(
        index
        for index, record in enumerate(records)
        if index != solved_index
        and record["coverage"] == 1
        and record["domain"] == records[solved_index]["domain"]
        and record["problem"] == records[solved_index]["problem"]
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: (
                values[other_same_task].update(
                    {
                        "solution_cost": values[other_same_task]["solution_cost"] + 1,
                        "plan_file_cost": values[other_same_task]["plan_file_cost"] + 1,
                    }
                )
            )
        ),
        "solved-cost disagreement",
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[solved_index].update(
                {"raw_metrics_complete": False}
            )
        ),
        "incomplete metrics require a resource exit",
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[solved_index].update(
                {
                    "piece_metrics_certified": False,
                    "metrics_validation_error": "synthetic corruption",
                }
            )
        ),
        "not semantically certified",
    )
    selector_index = next(
        index
        for index, record in enumerate(records)
        if record["algorithm"] == contract["selector_winner"]
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[selector_index].update(
                {"pdb_selector_trace_sha256": "3" * 64}
            )
        ),
        "pdb_selector_trace_sha256",
    )
    cap_index = next(
        index for index, record in enumerate(records)
        if record["algorithm"] == "ms_cap32"
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[cap_index].update(
                {"construction_completed": False}
            )
        ),
        "construction fallback is not enabled",
    )
    fallback_index = next(
        index for index, record in enumerate(records)
        if record["algorithm"] == MS_CAP32_BUILD60
        and record["construction_completed"] is False
    )
    _expect_error(
        lambda: validate_mutation(
            lambda values: values[fallback_index].update(
                {
                    "cofactor_width": 5,
                    "width_upper_bound": 25,
                    "num_values": 5,
                    "num_terminals": 5,
                    "add_nodes": 20,
                }
            )
        ),
        "blind fallback logged a heuristic",
    )

    if _normalize_properties({}, "synthetic") != []:
        raise AssertionError("empty strict properties container changed")

    return {
        "schema": ANALYSIS_SCHEMA,
        "self_test": "PASS",
        "synthetic_cells": [644, 736],
        "bootstrap": {
            "method": BOOTSTRAP_METHOD,
            "replicates": BOOTSTRAP_REPLICATES,
            "counter_encoding": BOOTSTRAP_COUNTER_ENCODING,
            "interval_rule": BOOTSTRAP_INTERVAL_RULE,
            "synthetic_sorted_numerators_sha256": first_bootstrap[
                "sorted_replicate_numerators_sha256"
            ],
        },
        "ordinary_analysis_gate": "BLOCKED_UNTIL_REVIEWED_HASHES_ARE_PINNED",
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze the exact frozen Arrhenius held-out selector matrix."
    )
    parser.add_argument(
        "properties",
        nargs="?",
        help="Lab properties JSON, eval directory, tar archive, or '-' for stdin.",
    )
    parser.add_argument(
        "--selection",
        type=Path,
        help="Exact selection artifact v3 used to launch held-out validation.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run deterministic 644/736-cell synthetic and adversarial tests.",
    )
    args = parser.parse_args(argv)
    if args.self_test and (args.properties is not None or args.selection is not None):
        parser.error("--self-test does not accept input paths")
    if not args.self_test and (args.properties is None or args.selection is None):
        parser.error("ordinary analysis requires properties and --selection")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        print(canonical_json(self_test()))
        return 0
    artifact, artifact_sha256 = load_selection_artifact(args.selection)
    protocol_revision = require_reviewed_pins(artifact_sha256)
    validate_runner_contract(expected_artifact_sha256=artifact_sha256)
    contract = validate_selection_artifact(artifact)
    tasks = load_and_validate_tasks()
    records = load_properties(args.properties)
    result = analyze(
        records,
        tasks,
        contract,
        artifact_sha256,
        protocol_revision,
    )
    print(canonical_json(result))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AnalysisError, RuntimeError) as err:
        print("analysis error: {}".format(err), file=sys.stderr)
        sys.exit(2)
