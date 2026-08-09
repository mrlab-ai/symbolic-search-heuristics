#!/usr/bin/env python3
"""Fail-closed held-out validation of the Arrhenius selector screen.

The runner consumes the exact v3 artifact emitted by
``analyze_arrhenius_selector_pilot.py``.  It independently reconstructs every
pilot and held-out invariant.  Launch is intentionally impossible until the
raw artifact SHA-256 below is reviewed and pinned.

Read-only checks::

    python experiments/exp_arrhenius_selector_validation.py --self-test
    python experiments/exp_arrhenius_selector_validation.py \
        --selection selection.json --check

After reviewing and pinning the artifact, keep build and start separate::

    experiments/.venv/bin/python \
        experiments/exp_arrhenius_selector_validation.py \
        --selection selection.json build
    experiments/.venv/bin/python \
        experiments/exp_arrhenius_selector_validation.py \
        --selection selection.json start
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from downward import suites

import exp_arrhenius_common as C
import suite_cost_manifest


class ProtocolError(RuntimeError):
    pass


PROTOCOL = "arrhenius-selector-heldout-validation-v2"
ANALYSIS_PROTOCOL = "paired-domain-macro-coverage-sha256-bootstrap-v1"
ANALYSIS_BOOTSTRAP_SEED = (
    "symbolic-search-heuristics/arrhenius-selector-heldout-bootstrap/v1"
)
ANALYSIS_BOOTSTRAP_REPLICATES = 100000
ARTIFACT_SCHEMA = (
    "symbolic-search-heuristics/arrhenius-selector-screen-selection/v3"
)
EXPECTED_SELECTION_ARTIFACT_SHA256 = None

EXPERIMENT_DATA_PATH = (
    Path(__file__).resolve().parent / "data" / Path(__file__).stem
)
MANIFEST = Path(__file__).with_name(
    "heuristic_finalists_validation_suite.txt"
)
DEVELOPMENT_MANIFESTS = (
    Path(__file__).with_name("selector_pilot_suite.txt"),
    Path(__file__).with_name("smoke_suite.txt"),
    Path(__file__).with_name("ms_caps_pilot_suite.txt"),
    Path(__file__).with_name("ms_caps_validation_suite.txt"),
)
PROTOCOL_FILES = (
    Path(__file__).resolve(),
    Path(C.__file__).resolve(),
    Path(__file__).with_name("wbh_parser.py").resolve(),
    Path(__file__).with_name("validate_wbh_log.py").resolve(),
    MANIFEST.resolve(),
    *(path.resolve() for path in DEVELOPMENT_MANIFESTS),
    Path(suite_cost_manifest.__file__).resolve(),
    Path(__file__).with_name("suite_wbh_operator_costs.json").resolve(),
    Path(__file__).with_name("suite_wbh_operator_costs.json.sha256").resolve(),
    Path(__file__).with_name("requirements.txt").resolve(),
)

MANIFEST_DIGEST = (
    "fc63d4eed62816a2e065cb89f89483999a7b51067b7077969d10b2a338f19760"
)
EXPECTED_TASK_SOURCES_SHA256 = (
    "14202b66a4ed4ea7afa9f204d15cbfe8857b061a644661fc9d68b3624523fdf4"
)
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168"
)
EXPECTED_TASKS = 92
EXPECTED_DOMAINS = 46
EXPECTED_MATERIALIZED_PDDL_FILES = {644: 1288, 736: 1472}
EXPECTED_MATERIALIZED_PDDL_BYTES = {644: 72541896, 736: 82905024}
EXPECTED_PDDL_BYTES_PER_CONFIG = 10363128
EXPECTED_UNIQUE_PDDL_SOURCE_FILES = 142
EXPECTED_UNIQUE_PDDL_SOURCE_BYTES = 10195682
MATERIALIZED_PDDL_PROTOCOL = C.PDDL_MATERIALIZATION_PROTOCOL

BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
BENCHMARK_REPOSITORY = "https://github.com/aibasel/downward-benchmarks.git"
PLANNER_REVISION = "58a3f742d7ac63f391d06c237573f14ad590c187"
PILOT_PROTOCOL_REVISION = "d6d98ad42f3976cd5cf0c9b17d8fa255354fbfbf"
CACHE_BINARY_SHA256 = (
    "59b97e8b1e777f700c255932271604393f60ec9aeba5c0151d0b7415a3a58511"
)
CACHE_PREPROCESS_SHA256 = (
    "acf2fc66c0b189095111a9d227ccb5b7acc564f1a6cb7bfd557904fa3c76798c"
)

PILOT_PROTOCOL = "arrhenius-exact-width-selector-screening-v2"
PILOT_SELECTION_RULE = (
    "valid-costs-max-coverage-min-micro-par2-"
    "min-certified-image-time-label/v1"
)
PILOT_MANIFEST = "selector_pilot_suite.txt"
PILOT_MANIFEST_SHA256 = (
    "3195dac7e62a34e5ac4cbeb715ab7f9b99e2ee64341082dd7d718ea2820751ca"
)
PILOT_TASK_SOURCES_SHA256 = (
    "dbb7730c257472c07f7946f0434949449169e06d1faa2174a92a6d13c48cb8ba"
)
PILOT_OPTION_MATRIX_SHA256 = (
    "e16f6e34af5101a3549bfbf98ebaba23371c645f9166c884bfdf07b3b65e7442"
)
PILOT_CONTROL_CONFIGS_SHA256 = (
    "ee40b07516ba1f2a3f562a2ec20f617e7eb1f742bf51aa67e9fb8db3d7ac9c89"
)
PILOT_SELECTOR_CONFIGS_SHA256 = (
    "7d44b160de438b32c385e95d4b3b48df9433d9f1c42397b4be5341f3937edf92"
)
SELECTOR_ELIGIBILITY_SHA256 = (
    "51dc9a5392f021c921d1dcc2636eb7c2d5955a363ff9df7e44ec871f9afc2aa3"
)
PDB_SELECTOR_PARSER_PROTOCOL = (
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

TIME_LIMIT_SECONDS = 300
MEMORY_LIMIT_MIB = 8192
PAR2_UNSOLVED_SECONDS = 600
PILOT_TASKS = 50
PILOT_CONFIGS = 20
PILOT_CELLS = 1000
PILOT_MATERIALIZED_PDDL_FILES = 2000
PILOT_MATERIALIZED_PDDL_BYTES = 50354240
PILOT_PDDL_BYTES_PER_CONFIG = 2517712
PILOT_UNIQUE_PDDL_SOURCE_FILES = 77
PILOT_UNIQUE_PDDL_SOURCE_BYTES = 2451625

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

PILOT_CONFIG_MATRIX = CONTROL_CONFIGS + SELECTOR_CONFIGS
PILOT_LABELS = tuple(label for label, _ in PILOT_CONFIG_MATRIX)
PILOT_SEARCHES = dict(PILOT_CONFIG_MATRIX)
SELECTOR_LABELS = tuple(label for label, _ in SELECTOR_CONFIGS)

MS_CAP32_BUILD60_LABEL = "ms_cap32_build60"
MS_CAP32_BUILD60_SEARCH = (
    "sym_fw_ms(max_states=10000,value_cap=32,align_merge_order=false,"
    "build_time_limit=60)"
)
FIXED_VALIDATION_CONFIGS = (
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
        MS_CAP32_BUILD60_LABEL,
        MS_CAP32_BUILD60_SEARCH,
        "predeclared-ms-build-budget-safeguard",
    ),
)
FIXED_VALIDATION_CONFIGS_SHA256 = (
    "c4cc5f5560a7b8b0d6bc28210c64ab603b75e01df1f40a0e9c4cb22fb02f557d"
)
BATCHED_SELECTOR_BASE = {
    "pdb_selector_k32_adapt_w64_r1_n1m": "pdb_selector_k32",
    "pdb_selector_k64_adapt_w64_r1_n1m": "pdb_selector_k64",
    "pdb_selector_k128_adapt_w64_r1_n1m": "pdb_selector_k128",
    "pdb_selector_kinf_adapt_w64_r1_n1m": "pdb_selector_kinf",
    "pdb_selector_k32_w16": "pdb_selector_k32",
}

FIXED_ENVIRONMENT = {
    "time_limit": "300s",
    "memory_limit": "8G",
    "build_options": ["release_no_lp"],
    "cache_build_name": "release_no_lp",
    "scheduler_cluster": "arrhenius",
    "scheduler_cpu_model": "AMD EPYC 9755 128-Core Processor",
    "scheduler_partition": "cpu",
    "scheduler_qos": "normal",
    "scheduler_account": "naiss2025-5-561-cpu",
    "scheduler_time_limit": "00:10:00",
    "scheduler_memory_per_cpu": "9G",
    "scheduler_cpus_per_task": 1,
    "array_task_throttle": 5,
    "max_array_tasks": 1000,
}

LAB_STEP_NAMES = ("build", "start", "parse", "fetch", "report")
LAB_STEP_ALIASES = {
    str(index): name for index, name in enumerate(LAB_STEP_NAMES, start=1)
}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


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
        raise ProtocolError("value is not canonical finite JSON: {}".format(err))


def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def _require_exact_keys(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        actual = sorted(value) if isinstance(value, dict) else type(value).__name__
        raise ProtocolError(
            "{} fields changed: expected {}, got {}".format(
                label, sorted(keys), actual
            )
        )


def _require_sha256(value, label, expected=None):
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ProtocolError("{} must be a lowercase SHA-256".format(label))
    if len(set(value)) == 1:
        raise ProtocolError("{} is a synthetic placeholder".format(label))
    if expected is not None and value != expected:
        raise ProtocolError(
            "{} changed: expected {}, got {}".format(label, expected, value)
        )
    return value


def _reject_nonfinite_or_placeholders(value, path="artifact"):
    if isinstance(value, dict):
        for key, child in value.items():
            _reject_nonfinite_or_placeholders(child, "{}.{}".format(path, key))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_nonfinite_or_placeholders(
                child, "{}[{}]".format(path, index)
            )
    elif type(value) is float and not math.isfinite(value):
        raise ProtocolError("{} contains a non-finite number".format(path))
    elif isinstance(value, str):
        upper = value.upper()
        if any(marker in upper for marker in ("PLACEHOLDER", "REPLACE_ME", "TBD")):
            raise ProtocolError("{} contains a placeholder string".format(path))
        if len(value) in (40, 64) and re.fullmatch(r"[0-9a-f]+", value):
            if len(set(value)) == 1:
                raise ProtocolError("{} contains a synthetic hash".format(path))


def _parse_json_bytes(raw, label):
    def reject_duplicate_keys(pairs):
        counts = Counter(key for key, _ in pairs)
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        if duplicates:
            raise ProtocolError(
                "{} has duplicate JSON keys: {}".format(
                    label, ", ".join(duplicates)
                )
            )
        return dict(pairs)

    def reject_constant(value):
        raise ProtocolError(
            "{} contains non-finite JSON constant {}".format(label, value)
        )

    try:
        text = raw.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=reject_duplicate_keys,
            parse_constant=reject_constant,
        )
    except ProtocolError:
        raise
    except (UnicodeError, json.JSONDecodeError) as err:
        raise ProtocolError("cannot parse {}: {}".format(label, err)) from err
    if not isinstance(value, dict):
        raise ProtocolError("{} must be one JSON object".format(label))
    _reject_nonfinite_or_placeholders(value)
    return value


def load_selection_artifact(path):
    path = Path(os.path.abspath(Path(path).expanduser()))
    if path.is_symlink() or not path.is_file():
        raise ProtocolError(
            "selection artifact must be a regular non-symlink file: {}".format(
                path
            )
        )
    try:
        raw = path.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read selection artifact: {}".format(err)) from err
    artifact = _parse_json_bytes(raw, "selection artifact")
    return artifact, hashlib.sha256(raw).hexdigest(), path.resolve()


def _option_records(configs):
    return [{"label": label, "search": search} for label, search in configs]


def _fixed_validation_records():
    return [
        {"label": label, "search": search, "role": role}
        for label, search, role in FIXED_VALIDATION_CONFIGS
    ]


def _validate_frozen_constants():
    if len(CONTROL_CONFIGS) != 5 or len(SELECTOR_CONFIGS) != 15:
        raise ProtocolError("frozen pilot matrix is not 5 controls + 15 selectors")
    if len(set(PILOT_LABELS)) != PILOT_CONFIGS:
        raise ProtocolError("frozen pilot labels are not unique")
    if sha256_json(_option_records(CONTROL_CONFIGS)) != (
        PILOT_CONTROL_CONFIGS_SHA256
    ):
        raise ProtocolError("frozen pilot control matrix changed")
    if sha256_json(_option_records(SELECTOR_CONFIGS)) != (
        PILOT_SELECTOR_CONFIGS_SHA256
    ):
        raise ProtocolError("frozen selector matrix changed")
    if sha256_json(_option_records(PILOT_CONFIG_MATRIX)) != (
        PILOT_OPTION_MATRIX_SHA256
    ):
        raise ProtocolError("frozen combined pilot matrix changed")
    if sha256_json(list(SELECTOR_LABELS)) != SELECTOR_ELIGIBILITY_SHA256:
        raise ProtocolError("frozen selector eligibility changed")
    if sha256_json(_fixed_validation_records()) != (
        FIXED_VALIDATION_CONFIGS_SHA256
    ):
        raise ProtocolError("fixed held-out configurations changed")
    batched = {
        label
        for label, search in SELECTOR_CONFIGS
        if "batch_f_window=" in search
    }
    if set(BATCHED_SELECTOR_BASE) != batched:
        raise ProtocolError("same-K mapping does not cover five batched selectors")
    for batched_label, base_label in BATCHED_SELECTOR_BASE.items():
        batched_search = PILOT_SEARCHES[batched_label]
        base_search = PILOT_SEARCHES[base_label]
        budget_re = re.compile(r"cofactor_width_budget=([^,)]+)")
        if (
            "batch_f_window=" in base_search
            or budget_re.search(batched_search).group(1)
            != budget_re.search(base_search).group(1)
        ):
            raise ProtocolError(
                "same-K mapping changed for {}".format(batched_label)
            )


def _require_number(value, label, minimum=None, maximum=None):
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise ProtocolError("{} must be a finite JSON number".format(label))
    if minimum is not None and value < minimum:
        raise ProtocolError("{} is smaller than {}".format(label, minimum))
    if maximum is not None and value > maximum:
        raise ProtocolError("{} exceeds {}".format(label, maximum))
    return float(value)


SCORE_KEYS = {
    "label",
    "search",
    "coverage",
    "micro_par2",
    "total_image_time",
    "image_metrics_complete",
    "construction",
    "cofactor_width",
    "selector",
    "rank",
}


def _validate_score(score, expected_rank, label):
    _require_exact_keys(score, SCORE_KEYS, label)
    config_label = score["label"]
    if config_label not in PILOT_SEARCHES:
        raise ProtocolError("{} has unknown label {!r}".format(label, config_label))
    if score["search"] != PILOT_SEARCHES[config_label]:
        raise ProtocolError("{} search differs from frozen matrix".format(label))
    if type(score["rank"]) is not int or score["rank"] != expected_rank:
        raise ProtocolError("{} rank/order changed".format(label))
    if (
        type(score["coverage"]) is not int
        or not 0 <= score["coverage"] <= PILOT_TASKS
    ):
        raise ProtocolError("{} coverage is invalid".format(label))
    _require_number(
        score["micro_par2"],
        "{}.micro_par2".format(label),
        0,
        PAR2_UNSOLVED_SECONDS,
    )
    if type(score["image_metrics_complete"]) is not bool:
        raise ProtocolError("{} image completeness is not boolean".format(label))
    if score["image_metrics_complete"]:
        _require_number(
            score["total_image_time"],
            "{}.total_image_time".format(label),
            0,
        )
    elif score["total_image_time"] is not None:
        raise ProtocolError("{} has image time for incomplete metrics".format(label))

    construction = score["construction"]
    _require_exact_keys(
        construction,
        {"completed", "fallbacks", "unobserved", "pattern_fallbacks"},
        "{}.construction".format(label),
    )
    for field in construction:
        value = construction[field]
        if type(value) is not int or not 0 <= value <= PILOT_TASKS:
            raise ProtocolError("{}.construction.{} is invalid".format(label, field))
    if (
        construction["completed"]
        + construction["fallbacks"]
        + construction["unobserved"]
        != PILOT_TASKS
    ):
        raise ProtocolError("{} construction counts do not cover tasks".format(label))

    width = score["cofactor_width"]
    _require_exact_keys(
        width,
        {"observed", "minimum", "median", "maximum"},
        "{}.cofactor_width".format(label),
    )
    observed = width["observed"]
    if type(observed) is not int or not 0 <= observed <= PILOT_TASKS:
        raise ProtocolError("{} width observed count is invalid".format(label))
    summary = (width["minimum"], width["median"], width["maximum"])
    if observed == 0:
        if summary != (None, None, None):
            raise ProtocolError("{} has width values without observations".format(label))
    else:
        values = [
            _require_number(value, "{}.cofactor_width".format(label), 0)
            for value in summary
        ]
        if values != sorted(values):
            raise ProtocolError("{} width summary is not ordered".format(label))

    selector = score["selector"]
    _require_exact_keys(
        selector,
        {"certified", "interrupted", "selected_sources"},
        "{}.selector".format(label),
    )
    for field in ("certified", "interrupted"):
        value = selector[field]
        if type(value) is not int or not 0 <= value <= PILOT_TASKS:
            raise ProtocolError("{}.selector.{} is invalid".format(label, field))
    sources = selector["selected_sources"]
    _require_exact_keys(sources, set(SELECTOR_SOURCES), "{}.selected_sources".format(label))
    for source, count in sources.items():
        if type(count) is not int or not 0 <= count <= PILOT_TASKS:
            raise ProtocolError(
                "{}.selected_sources.{} is invalid".format(label, source)
            )
    return score


def _score_key(score, use_image_time):
    key = (-score["coverage"], float(score["micro_par2"]))
    if use_image_time:
        key += (float(score["total_image_time"]),)
    return key + (score["label"],)


def _validate_selection(artifact):
    selection = artifact["selection"]
    _require_exact_keys(
        selection,
        {
            "image_time_tiebreak_used",
            "global_winner",
            "selector_family_winner",
            "selector_eligibility_labels",
            "selector_eligibility_sha256",
            "ranking",
        },
        "selection",
    )
    if type(selection["image_time_tiebreak_used"]) is not bool:
        raise ProtocolError("selection image-time decision is not boolean")
    if selection["selector_eligibility_labels"] != list(SELECTOR_LABELS):
        raise ProtocolError("selection selector eligibility labels changed")
    _require_sha256(
        selection["selector_eligibility_sha256"],
        "selection selector eligibility digest",
        SELECTOR_ELIGIBILITY_SHA256,
    )
    ranking = selection["ranking"]
    if not isinstance(ranking, list) or len(ranking) != PILOT_CONFIGS:
        raise ProtocolError("selection ranking must contain exactly 20 scores")
    for index, score in enumerate(ranking, 1):
        _validate_score(score, index, "selection.ranking[{}]".format(index - 1))
    labels = [score["label"] for score in ranking]
    if len(set(labels)) != PILOT_CONFIGS or set(labels) != set(PILOT_LABELS):
        raise ProtocolError("selection ranking labels differ from frozen matrix")
    use_image = selection["image_time_tiebreak_used"]
    if use_image != all(score["image_metrics_complete"] for score in ranking):
        raise ProtocolError("selection image-time decision contradicts scores")
    keys = [_score_key(score, use_image) for score in ranking]
    if keys != sorted(keys):
        raise ProtocolError("selection ranking violates the frozen score order")
    global_winner = ranking[0]
    selector_winner = next(
        score for score in ranking if score["label"] in SELECTOR_LABELS
    )
    if canonical_json(selection["global_winner"]) != canonical_json(
        global_winner
    ):
        raise ProtocolError("selection global winner is not rank 1")
    if canonical_json(selection["selector_family_winner"]) != canonical_json(
        selector_winner
    ):
        raise ProtocolError("selection selector-family winner is not first eligible")
    return global_winner, selector_winner, {score["label"]: score for score in ranking}


PILOT_KEYS = {
    "protocol",
    "selection_rule",
    "planner_revision",
    "protocol_revision",
    "planner_revision_is_protocol_ancestor",
    "planner_binary_sha256",
    "planner_preprocess_sha256",
    "planner_build_config",
    "benchmark_revision",
    "benchmark_repository",
    "task_manifest",
    "task_manifest_sha256",
    "source_manifest_sha256",
    "task_sources_sha256",
    "materialized_pddl_protocol",
    "materialized_pddl_files",
    "materialized_pddl_bytes",
    "pddl_bytes_per_config",
    "unique_pddl_source_files",
    "unique_pddl_source_bytes",
    "option_matrix_sha256",
    "control_configs_sha256",
    "selector_configs_sha256",
    "pdb_selector_parser_protocol",
    "metrics_validation_protocol",
    "outcome_reconciliation_protocol",
    "selector_pool_protocol",
    "selector_score_version",
    "selector_source_order",
    "options",
    "task_count",
    "config_count",
    "expected_run_count",
    "time_limit_seconds",
    "memory_limit_mib",
    "par2_unsolved_seconds",
    "properties_canonical_sha256",
}


def _validate_pilot(pilot):
    _require_exact_keys(pilot, PILOT_KEYS, "pilot")
    exact = {
        "protocol": PILOT_PROTOCOL,
        "selection_rule": PILOT_SELECTION_RULE,
        "planner_revision": PLANNER_REVISION,
        "protocol_revision": PILOT_PROTOCOL_REVISION,
        "planner_revision_is_protocol_ancestor": True,
        "planner_binary_sha256": CACHE_BINARY_SHA256,
        "planner_preprocess_sha256": CACHE_PREPROCESS_SHA256,
        "planner_build_config": "release_no_lp",
        "benchmark_revision": BENCHMARK_REVISION,
        "benchmark_repository": BENCHMARK_REPOSITORY,
        "task_manifest": PILOT_MANIFEST,
        "task_manifest_sha256": PILOT_MANIFEST_SHA256,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
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
        "pdb_selector_parser_protocol": PDB_SELECTOR_PARSER_PROTOCOL,
        "metrics_validation_protocol": METRICS_VALIDATION_PROTOCOL,
        "outcome_reconciliation_protocol": OUTCOME_RECONCILIATION_PROTOCOL,
        "selector_pool_protocol": SELECTOR_POOL_PROTOCOL,
        "selector_score_version": SELECTOR_SCORE_VERSION,
        "selector_source_order": list(SELECTOR_SOURCES),
        "options": _option_records(PILOT_CONFIG_MATRIX),
        "task_count": PILOT_TASKS,
        "config_count": PILOT_CONFIGS,
        "expected_run_count": PILOT_CELLS,
        "time_limit_seconds": TIME_LIMIT_SECONDS,
        "memory_limit_mib": MEMORY_LIMIT_MIB,
        "par2_unsolved_seconds": PAR2_UNSOLVED_SECONDS,
    }
    for field, expected in exact.items():
        if type(pilot[field]) is not type(expected) or pilot[field] != expected:
            raise ProtocolError(
                "pilot.{}={!r}, expected {!r}".format(
                    field, pilot[field], expected
                )
            )
    _require_sha256(
        pilot["properties_canonical_sha256"],
        "pilot properties canonical digest",
    )


PAIRED_KEYS = {
    "label",
    "reference",
    "coverage_delta",
    "micro_par2_delta",
    "wins",
    "losses",
    "both_solved",
    "both_unsolved",
    "total_image_time_delta",
}


def _validate_paired_deltas(paired, score_by_label, use_image):
    expected_pairs = [
        (label, reference)
        for label in PILOT_LABELS
        for reference in ("blind_fw", "ms_exact")
    ]
    if not isinstance(paired, list) or len(paired) != len(expected_pairs):
        raise ProtocolError("paired_deltas must contain exactly 40 records")
    for index, ((label, reference), record) in enumerate(
        zip(expected_pairs, paired)
    ):
        prefix = "paired_deltas[{}]".format(index)
        _require_exact_keys(record, PAIRED_KEYS, prefix)
        if record["label"] != label or record["reference"] != reference:
            raise ProtocolError("{} ordering/identity changed".format(prefix))
        for field in ("wins", "losses", "both_solved", "both_unsolved"):
            value = record[field]
            if type(value) is not int or not 0 <= value <= PILOT_TASKS:
                raise ProtocolError("{}.{} is invalid".format(prefix, field))
        if (
            type(record["coverage_delta"]) is not int
            or not -PILOT_TASKS <= record["coverage_delta"] <= PILOT_TASKS
        ):
            raise ProtocolError("{}.coverage_delta is invalid".format(prefix))
        if sum(record[field] for field in (
            "wins", "losses", "both_solved", "both_unsolved"
        )) != PILOT_TASKS:
            raise ProtocolError("{} outcome counts do not cover tasks".format(prefix))
        if record["coverage_delta"] != record["wins"] - record["losses"]:
            raise ProtocolError("{} coverage delta is inconsistent".format(prefix))
        if (
            record["wins"] + record["both_solved"]
            != score_by_label[label]["coverage"]
            or record["losses"] + record["both_solved"]
            != score_by_label[reference]["coverage"]
        ):
            raise ProtocolError("{} counts disagree with ranking coverage".format(prefix))
        delta = _require_number(
            record["micro_par2_delta"],
            "{}.micro_par2_delta".format(prefix),
            -PAR2_UNSOLVED_SECONDS,
            PAR2_UNSOLVED_SECONDS,
        )
        expected_delta = (
            float(score_by_label[label]["micro_par2"])
            - float(score_by_label[reference]["micro_par2"])
        )
        if not math.isclose(delta, expected_delta, rel_tol=1e-12, abs_tol=1e-12):
            raise ProtocolError("{} PAR2 delta disagrees with ranking".format(prefix))
        image_delta = record["total_image_time_delta"]
        if use_image:
            actual = _require_number(
                image_delta, "{}.total_image_time_delta".format(prefix)
            )
            expected = (
                float(score_by_label[label]["total_image_time"])
                - float(score_by_label[reference]["total_image_time"])
            )
            if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
                raise ProtocolError("{} image delta disagrees with ranking".format(prefix))
        elif image_delta is not None:
            raise ProtocolError("{} has unavailable image-time delta".format(prefix))


def _expected_comparisons(global_label, selector_label, matched_label):
    comparisons = []

    def add(name, candidate, reference, role):
        if candidate == reference:
            return
        for comparison in comparisons:
            if (
                comparison["candidate"] == candidate
                and comparison["reference"] == reference
            ):
                comparison["roles"].append(role)
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
        "selector-vs-pdb-cegar",
        selector_label,
        "pdb_cegar_b100k",
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
        MS_CAP32_BUILD60_LABEL,
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
        "blind_fw",
        "heldout-global-winner-context",
    )
    add(
        "global-winner-vs-ms-exact",
        global_label,
        "ms_exact",
        "heldout-global-winner-context",
    )
    for reference in ("blind_fw", "ms_exact", "ms_cap32"):
        add(
            "selector-vs-{}".format(reference.replace("_", "-")),
            selector_label,
            reference,
            "heldout-selector-context",
        )
    return comparisons


def _expected_validation_contract(global_label, selector_label):
    configs = []

    def add_config(label, search, role):
        matches = [config for config in configs if config["label"] == label]
        search_matches = [
            config for config in configs if config["search"] == search
        ]
        if matches or search_matches:
            if (
                len(matches) != 1
                or len(search_matches) != 1
                or matches[0] is not search_matches[0]
            ):
                raise ProtocolError(
                    "validation label/search collision for {}".format(label)
                )
            if role not in matches[0]["roles"]:
                matches[0]["roles"].append(role)
            return
        configs.append({"label": label, "search": search, "roles": [role]})

    for label, search, role in FIXED_VALIDATION_CONFIGS:
        add_config(label, search, role)
    if selector_label not in SELECTOR_LABELS:
        raise ProtocolError("selector-family winner is not eligible")
    add_config(
        selector_label,
        PILOT_SEARCHES[selector_label],
        "pilot-selector-family-winner",
    )
    matched_label = BATCHED_SELECTOR_BASE.get(selector_label)
    if matched_label is not None:
        add_config(
            matched_label,
            PILOT_SEARCHES[matched_label],
            "matched-same-k-unbatched-ablation",
        )
    if global_label not in {config["label"] for config in configs}:
        raise ProtocolError("global winner is not represented in validation")
    add_config(
        global_label,
        PILOT_SEARCHES[global_label],
        "pilot-global-winner",
    )

    count = len(configs)
    expected_count = 8 if matched_label is not None else 7
    if count != expected_count:
        raise ProtocolError(
            "derived validation config count is {}, expected {}".format(
                count, expected_count
            )
        )
    if (
        len({config["label"] for config in configs}) != count
        or len({config["search"] for config in configs}) != count
    ):
        raise ProtocolError("derived validation configs are not deduplicated")
    options = [
        {"label": config["label"], "search": config["search"]}
        for config in configs
    ]
    run_count = EXPECTED_TASKS * count
    if run_count not in (644, 736):
        raise ProtocolError("derived validation run count is invalid")
    layout = {
        "raw_runs": run_count,
        "array_tasks": run_count,
        "runs_per_array_task": 1,
        "scheduler_time_limit_seconds": 600,
    }
    comparisons = _expected_comparisons(
        global_label, selector_label, matched_label
    )
    return {
        "task_manifest": MANIFEST.name,
        "task_manifest_sha256": MANIFEST_DIGEST,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
        "task_count": EXPECTED_TASKS,
        "domain_count": EXPECTED_DOMAINS,
        "fixed_configs_sha256": FIXED_VALIDATION_CONFIGS_SHA256,
        "roles": {
            "global_winner": global_label,
            "selector_family_winner": selector_label,
            "ms_build_budget_safeguard": MS_CAP32_BUILD60_LABEL,
            "matched_same_k_unbatched": matched_label,
        },
        "configs": configs,
        "option_matrix_sha256": sha256_json(options),
        "comparisons": comparisons,
        "comparisons_sha256": sha256_json(comparisons),
        "config_count": count,
        "expected_run_count": run_count,
        "array_layout": layout,
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
        "protocol": PROTOCOL,
        "requires_disjoint_tasks": True,
        "selection_artifact_schema": ARTIFACT_SCHEMA,
        "selection_rule": PILOT_SELECTION_RULE,
        "selector_eligibility_labels": list(SELECTOR_LABELS),
        "selector_eligibility_sha256": SELECTOR_ELIGIBILITY_SHA256,
        "selector_configs_sha256": PILOT_SELECTOR_CONFIGS_SHA256,
        "time_limit_seconds": TIME_LIMIT_SECONDS,
        "memory_limit_mib": MEMORY_LIMIT_MIB,
        "par2_unsolved_seconds": PAR2_UNSOLVED_SECONDS,
        "analysis": {
            "protocol": ANALYSIS_PROTOCOL,
            "primary_comparison": "selector-vs-pdb-cegar",
            "primary_estimand": (
                "selector-minus-cegar-equally-weighted-domain-macro-"
                "coverage/v1"
            ),
            "resampling_unit": "domain",
            "bootstrap_method": "sha256-counter-domain-resampling/v1",
            "bootstrap_seed": ANALYSIS_BOOTSTRAP_SEED,
            "bootstrap_replicates": ANALYSIS_BOOTSTRAP_REPLICATES,
            "confidence_level": 0.95,
            "rerank_on_validation": False,
            "secondary_descriptive": [
                "suite-micro-coverage",
                "micro-par2-600s",
                "discordant-wins-losses",
                "jointly-solved-runtime-ratio",
                "certified-width-image-and-effort-metrics",
                "ms-build-budget-fallback-incidence",
            ],
        },
    }


def validate_selection_artifact(artifact):
    _validate_frozen_constants()
    _reject_nonfinite_or_placeholders(artifact)
    _require_exact_keys(
        artifact,
        {"schema", "pilot", "selection", "paired_deltas", "validation"},
        "selection artifact",
    )
    if artifact["schema"] != ARTIFACT_SCHEMA:
        raise ProtocolError(
            "selection artifact schema changed: {!r}".format(artifact["schema"])
        )
    _validate_pilot(artifact["pilot"])
    global_winner, selector_winner, score_by_label = _validate_selection(
        artifact
    )
    _validate_paired_deltas(
        artifact["paired_deltas"],
        score_by_label,
        artifact["selection"]["image_time_tiebreak_used"],
    )
    expected_validation = _expected_validation_contract(
        global_winner["label"], selector_winner["label"]
    )
    if canonical_json(artifact["validation"]) != canonical_json(
        expected_validation
    ):
        actual = artifact["validation"]
        missing = sorted(set(expected_validation) - set(actual)) \
            if isinstance(actual, dict) else sorted(expected_validation)
        extra = sorted(set(actual) - set(expected_validation)) \
            if isinstance(actual, dict) else []
        mismatches = []
        if isinstance(actual, dict):
            mismatches = [
                key
                for key in sorted(set(actual) & set(expected_validation))
                if actual[key] != expected_validation[key]
            ]
        raise ProtocolError(
            "validation contract differs from independent reconstruction: "
            "missing={}, extra={}, mismatched={}".format(
                missing, extra, mismatches
            )
        )
    layout = C.validate_run_layout(
        expected_validation["expected_run_count"],
        require_one_run_per_array_task=True,
    )
    if layout != expected_validation["array_layout"]:
        raise ProtocolError("validation artifact Arrhenius layout changed")
    configs = [
        (config["label"], config["search"])
        for config in expected_validation["configs"]
    ]
    return {
        "configs": configs,
        "config_records": expected_validation["configs"],
        "matrix_digest": expected_validation["option_matrix_sha256"],
        "comparisons": expected_validation["comparisons"],
        "comparisons_digest": expected_validation["comparisons_sha256"],
        "global_winner": global_winner,
        "selector_winner": selector_winner,
        "matched_unbatched": expected_validation["roles"][
            "matched_same_k_unbatched"
        ],
        "run_count": expected_validation["expected_run_count"],
        "layout": layout,
        "properties_digest": artifact["pilot"][
            "properties_canonical_sha256"
        ],
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


def require_selection_artifact_hash(
    actual_sha256,
    *,
    required,
    expected_sha256=EXPECTED_SELECTION_ARTIFACT_SHA256,
):
    _require_sha256(actual_sha256, "raw selection artifact SHA-256")
    if expected_sha256 is None:
        if required:
            raise ProtocolError(
                "EXPECTED_SELECTION_ARTIFACT_SHA256 is unset; review the exact "
                "v3 artifact bytes and pin their raw SHA-256 before build/start"
            )
        return False
    _require_sha256(expected_sha256, "expected selection artifact SHA-256")
    if actual_sha256 != expected_sha256:
        raise ProtocolError(
            "selection artifact SHA-256 changed: expected {}, got {}".format(
                expected_sha256, actual_sha256
            )
        )
    return True


def normalize_lab_steps(steps):
    """Accept only exact Lab step names and their canonical one-digit aliases."""
    normalized = []
    for raw_step in steps:
        if raw_step in LAB_STEP_NAMES:
            step = raw_step
        elif raw_step in LAB_STEP_ALIASES:
            step = LAB_STEP_ALIASES[raw_step]
        else:
            raise ProtocolError(
                "unknown Lab step {!r}; use one of {} or canonical aliases "
                "1..5".format(raw_step, ", ".join(LAB_STEP_NAMES))
            )
        if step in normalized:
            raise ProtocolError(
                "duplicate Lab step {!r} (possibly via a numeric alias)".
                format(step)
            )
        normalized.append(step)
    launch_steps = [step for step in ("build", "start") if step in normalized]
    if launch_steps and len(normalized) != 1:
        raise ProtocolError(
            "Arrhenius protocol step {!r} must run in its own invocation".
            format(launch_steps[0])
        )
    return normalized


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate or run the launch-blocked Arrhenius selector held-out "
            "protocol."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--selection",
        type=Path,
        help="Exact analyzer v3 selection artifact.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Read-only artifact, source, cache, and prospective-header "
            "attestation."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run deterministic read-only protocol tests.",
    )
    parser.add_argument(
        "steps",
        nargs="*",
        help="Lab steps; build and start must each run alone.",
    )
    args = parser.parse_args(argv)
    if args.check and args.self_test:
        parser.error("--check and --self-test are mutually exclusive")
    if (args.check or args.self_test) and args.steps:
        parser.error("read-only checks cannot be combined with Lab steps")
    if args.self_test and args.selection is not None:
        parser.error("--self-test does not consume an external selection artifact")
    args.steps = normalize_lab_steps(args.steps)
    return args


def validate_fixed_environment():
    actual = {
        "time_limit": C.TIME_LIMIT,
        "memory_limit": C.MEMORY_LIMIT,
        "build_options": C.BUILD_OPTIONS,
        "cache_build_name": C.CACHE_BUILD_NAME,
        "scheduler_cluster": C.SCHEDULER_CLUSTER,
        "scheduler_cpu_model": C.SCHEDULER_CPU_MODEL,
        "scheduler_partition": C.SCHEDULER_PARTITION,
        "scheduler_qos": C.SCHEDULER_QOS,
        "scheduler_account": C.SCHEDULER_ACCOUNT,
        "scheduler_time_limit": C.SCHEDULER_TIME_LIMIT,
        "scheduler_memory_per_cpu": C.SCHEDULER_MEMORY_PER_CPU,
        "scheduler_cpus_per_task": C.SCHEDULER_CPUS_PER_TASK,
        "array_task_throttle": C.ARRAY_TASK_THROTTLE,
        "max_array_tasks": C.MAX_ARRAY_TASKS,
    }
    if actual != FIXED_ENVIRONMENT:
        raise ProtocolError(
            "Arrhenius environment/limits differ from the frozen protocol: "
            "{}".format(actual)
        )


def read_manifest():
    try:
        lines = MANIFEST.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as err:
        raise ProtocolError("cannot read held-out manifest: {}".format(err)) from err
    tasks = []
    for lineno, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(":")
        if len(fields) != 2 or not all(fields):
            raise ProtocolError(
                "{}:{} must contain exact DOMAIN:PROBLEM".format(
                    MANIFEST, lineno
                )
            )
        tasks.append(line)
    digest = hashlib.sha256(
        "".join("{}\n".format(task) for task in tasks).encode("utf-8")
    ).hexdigest()
    if digest != MANIFEST_DIGEST:
        raise ProtocolError(
            "held-out manifest digest changed: expected {}, got {}".format(
                MANIFEST_DIGEST, digest
            )
        )
    counts = Counter(task.partition(":")[0] for task in tasks)
    if (
        len(tasks) != EXPECTED_TASKS
        or len(set(tasks)) != EXPECTED_TASKS
        or len(counts) != EXPECTED_DOMAINS
        or set(counts.values()) != {2}
    ):
        raise ProtocolError(
            "held-out manifest must contain 92 unique tasks, two per each "
            "of 46 domains"
        )
    return tasks


def _read_disjointness_manifest(path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as err:
        raise ProtocolError(
            "cannot read development manifest {}: {}".format(path, err)
        ) from err
    tasks = []
    for lineno, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            fields = line.split(":")
        else:
            fields = line.split()
        if len(fields) != 2 or not all(fields):
            raise ProtocolError(
                "{}:{} must contain DOMAIN:PROBLEM or DOMAIN PROBLEM".format(
                    path, lineno
                )
            )
        tasks.append("{}:{}".format(*fields))
    if len(tasks) != len(set(tasks)):
        raise ProtocolError(
            "development manifest contains duplicate tasks: {}".format(path)
        )
    return tasks


def _require_disjoint_task_sets(heldout_tasks, named_development_tasks):
    heldout = set(heldout_tasks)
    for label, tasks in named_development_tasks:
        overlap = sorted(heldout & set(tasks))
        if overlap:
            raise ProtocolError(
                "held-out manifest overlaps {}: {}".format(
                    label, ", ".join(overlap)
                )
            )


def validate_development_manifest_disjointness(tasks):
    _require_disjoint_task_sets(
        tasks,
        [
            (path.name, _read_disjointness_manifest(path))
            for path in DEVELOPMENT_MANIFESTS
        ],
    )


def validate_manifest_record_pins(tasks):
    """Attest support and the selected source records without benchmark I/O."""
    validate_development_manifest_disjointness(tasks)
    data = suite_cost_manifest.load_manifest()
    records = {
        (record["domain"], record["problem"]): record
        for record in data["tasks"]
    }
    keys = [tuple(task.split(":", 1)) for task in tasks]
    supported = suite_cost_manifest.supported_tasks()
    unsupported = sorted(set(keys) - supported)
    if unsupported:
        raise ProtocolError(
            "held-out manifest contains unsupported positive-cost/axiom-free "
            "tasks: {}".format(
                ", ".join("{}:{}".format(*task) for task in unsupported)
            )
        )
    try:
        selected = [records[key] for key in sorted(keys)]
    except KeyError as err:
        raise ProtocolError(
            "held-out task is absent from source manifest: {}:{}".format(
                *err.args[0]
            )
        ) from err
    task_sources = hashlib.sha256(
        suite_cost_manifest.canonical_records_bytes(selected)
    ).hexdigest()
    if task_sources != EXPECTED_TASK_SOURCES_SHA256:
        raise ProtocolError(
            "held-out source-record digest changed: expected {}, got {}".
            format(EXPECTED_TASK_SOURCES_SHA256, task_sources)
        )
    source_manifest = suite_cost_manifest.sha256_file(
        suite_cost_manifest.MANIFEST_PATH
    )
    if source_manifest != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise ProtocolError("frozen support-manifest bytes changed")
    return {
        "task_sources_sha256": task_sources,
        "source_manifest_sha256": source_manifest,
    }


def validate_matrix(tasks, matrix):
    validate_fixed_environment()
    configs = matrix["configs"]
    labels = [label for label, _ in configs]
    searches = [search for _, search in configs]
    expected_count = 8 if matrix["matched_unbatched"] is not None else 7
    if len(configs) != expected_count or len(set(labels)) != expected_count:
        raise ProtocolError("artifact-derived configuration count changed")
    if len(set(searches)) != expected_count:
        raise ProtocolError("artifact-derived search expressions are not unique")
    for label, search in configs:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", label):
            raise ProtocolError("invalid configuration label {!r}".format(label))
        try:
            C.search_config(search)
        except ValueError as err:
            raise ProtocolError(
                "invalid search expression for {}: {}".format(label, err)
            ) from err
        lowered = search.lower()
        if any(term in lowered for term in ("lpsolver", "sym_fw_pot", "potential")):
            raise ProtocolError(
                "release_no_lp validation contains forbidden search {}".
                format(label)
            )
    digest = sha256_json(_option_records(configs))
    if digest != matrix["matrix_digest"]:
        raise ProtocolError("artifact-derived configuration digest changed")
    run_count = len(tasks) * len(configs)
    if run_count != matrix["run_count"] or run_count not in (644, 736):
        raise ProtocolError("held-out run count must be exactly 644 or 736")
    layout = C.validate_run_layout(
        run_count, require_one_run_per_array_task=True
    )
    if layout != matrix["layout"]:
        raise ProtocolError("held-out array layout differs from the artifact")
    return matrix


def _git_output(repository, *args):
    try:
        return subprocess.run(
            ["git", "-C", str(repository), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as err:
        detail = (err.stderr or err.stdout or str(err)).strip()
        raise ProtocolError(
            "git check failed for {}: {}".format(repository, detail)
        ) from err


def _normalized_repository_url(url):
    return url.rstrip("/").removesuffix(".git")


def require_pinned_benchmark_worktree():
    raw_root = os.environ.get("DOWNWARD_BENCHMARKS")
    if not raw_root:
        raise ProtocolError(
            "set DOWNWARD_BENCHMARKS to a dedicated benchmark worktree at {}".
            format(BENCHMARK_REVISION)
        )
    root = Path(raw_root).expanduser().resolve()
    if not root.is_dir():
        raise ProtocolError("benchmark worktree is not a directory: {}".format(root))
    top = Path(_git_output(root, "rev-parse", "--show-toplevel")).resolve()
    if top != root:
        raise ProtocolError("DOWNWARD_BENCHMARKS must name the worktree root")
    revision = _git_output(root, "rev-parse", "HEAD")
    if revision != BENCHMARK_REVISION:
        raise ProtocolError(
            "benchmark worktree is at {}, expected {}".format(
                revision, BENCHMARK_REVISION
            )
        )
    dirty = _git_output(root, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise ProtocolError(
            "benchmark worktree has tracked modifications:\n{}".format(dirty)
        )
    origin = _git_output(root, "remote", "get-url", "origin")
    if _normalized_repository_url(origin) != _normalized_repository_url(
        BENCHMARK_REPOSITORY
    ):
        raise ProtocolError(
            "benchmark origin is {!r}, expected {!r}".format(
                origin, BENCHMARK_REPOSITORY
            )
        )
    return root


def _require_supported_tasks(tasks):
    supported = suite_cost_manifest.supported_tasks()
    rejected = sorted(
        (task.domain, task.problem)
        for task in tasks
        if (task.domain, task.problem) not in supported
    )
    if rejected:
        raise ProtocolError(
            "held-out suite contains unsupported tasks: {}".format(
                ", ".join("{}:{}".format(*task) for task in rejected)
            )
        )


def _resolve_ordered_tasks(benchmark_root, descriptions):
    resolved = suites.build_suite(str(benchmark_root), descriptions)
    by_description = {
        "{}:{}".format(task.domain, task.problem): task for task in resolved
    }
    if len(resolved) != len(descriptions) or len(by_description) != len(descriptions):
        raise ProtocolError(
            "{} manifest entries resolved to {} tasks ({} unique)".format(
                len(descriptions), len(resolved), len(by_description)
            )
        )
    try:
        ordered = [by_description[item] for item in descriptions]
    except KeyError as err:
        raise ProtocolError(
            "held-out manifest task did not resolve: {}".format(err.args[0])
        ) from err
    _require_supported_tasks(ordered)
    return ordered


def attest_task_sources(benchmark_root, descriptions):
    ordered = _resolve_ordered_tasks(benchmark_root, descriptions)
    digest = suite_cost_manifest.validate_task_sources(
        (
            (
                task.domain,
                task.problem,
                Path(task.domain_file),
                Path(task.problem_file),
            )
            for task in ordered
        ),
        benchmark_root,
    )
    if digest != EXPECTED_TASK_SOURCES_SHA256:
        raise ProtocolError(
            "held-out task-source bytes changed: expected {}, got {}".format(
                EXPECTED_TASK_SOURCES_SHA256, digest
            )
        )
    source_digest = suite_cost_manifest.sha256_file(
        suite_cost_manifest.MANIFEST_PATH
    )
    if source_digest != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise ProtocolError("frozen support-manifest bytes changed")
    all_sources = [
        source
        for task in ordered
        for source in (
            Path(task.domain_file).resolve(),
            Path(task.problem_file).resolve(),
        )
    ]
    bytes_per_config = sum(path.stat().st_size for path in all_sources)
    unique_sources = set(all_sources)
    unique_source_bytes = sum(path.stat().st_size for path in unique_sources)
    if (
        bytes_per_config != EXPECTED_PDDL_BYTES_PER_CONFIG
        or len(unique_sources) != EXPECTED_UNIQUE_PDDL_SOURCE_FILES
        or unique_source_bytes != EXPECTED_UNIQUE_PDDL_SOURCE_BYTES
    ):
        raise ProtocolError(
            "held-out PDDL source file/byte totals changed: per_config={}, "
            "unique_files={}, unique_bytes={}".format(
                bytes_per_config, len(unique_sources), unique_source_bytes
            )
        )
    return {
        "task_sources_sha256": digest,
        "source_manifest_sha256": source_digest,
        "pddl_bytes_per_config": bytes_per_config,
        "unique_pddl_source_files": len(unique_sources),
        "unique_pddl_source_bytes": unique_source_bytes,
    }


def _heldout_source_records(descriptions):
    records = {
        (record["domain"], record["problem"]): record
        for record in suite_cost_manifest.load_manifest()["tasks"]
    }
    expected = {tuple(item.split(":", 1)) for item in descriptions}
    if len(expected) != EXPECTED_TASKS or not expected <= set(records):
        raise ProtocolError("support manifest lacks exact held-out source records")
    return {key: records[key] for key in expected}


def materialize_grid_pddl_inputs(
    benchmark_root, task_descriptions, matrix
):
    """Materialize every cell input only after Lab finishes fresh build."""
    grid_path = EXPERIMENT_DATA_PATH
    if grid_path.is_symlink() or not grid_path.is_dir():
        raise ProtocolError("materialization requires the newly built held-out grid")
    ordered_tasks = _resolve_ordered_tasks(benchmark_root, task_descriptions)
    records = _heldout_source_records(task_descriptions)
    copied_files = 0
    copied_bytes = 0
    for config_index, _ in enumerate(matrix["configs"]):
        for task_index, task in enumerate(ordered_tasks):
            run_id = config_index * len(ordered_tasks) + task_index + 1
            run_dir = grid_path / _run_relative_path(run_id)
            _require_pristine_run_directory(run_dir, run_id)
            record = records[(task.domain, task.problem)]
            for link_name, source, hash_field in (
                (
                    "domain.pddl",
                    Path(task.domain_file).resolve(),
                    "domain_sha256",
                ),
                (
                    "problem.pddl",
                    Path(task.problem_file).resolve(),
                    "problem_sha256",
                ),
            ):
                copied_bytes += C.materialize_pddl_link(
                    run_dir / link_name,
                    source,
                    record[hash_field],
                    "run {} {}".format(run_id, link_name),
                )
                copied_files += 1
    expected_files = EXPECTED_MATERIALIZED_PDDL_FILES[matrix["run_count"]]
    expected_bytes = EXPECTED_MATERIALIZED_PDDL_BYTES[matrix["run_count"]]
    if copied_files != expected_files or copied_bytes != expected_bytes:
        raise ProtocolError(
            "materialized held-out PDDL totals changed: files={}/{}, "
            "bytes={}/{}".format(
                copied_files, expected_files, copied_bytes, expected_bytes
            )
        )
    return {"files": copied_files, "bytes": copied_bytes}


def validate_cache_pins():
    if not isinstance(PLANNER_REVISION, str) or not re.fullmatch(
        r"[0-9a-f]{40}", PLANNER_REVISION
    ):
        raise ProtocolError("P4 planner revision is unset")
    if not isinstance(PILOT_PROTOCOL_REVISION, str) or not re.fullmatch(
        r"[0-9a-f]{40}", PILOT_PROTOCOL_REVISION
    ):
        raise ProtocolError("P4 screen protocol revision is unset")
    _require_sha256(CACHE_BINARY_SHA256, "cached planner SHA-256")
    _require_sha256(CACHE_PREPROCESS_SHA256, "cached preprocess SHA-256")


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_regular_file(path, label):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ProtocolError(
            "{} must be one regular non-symlink file: {}".format(label, path)
        )


def _require_file_sha256(path, expected, label):
    _require_regular_file(path, label)
    actual = _sha256_file(path)
    if actual != expected:
        raise ProtocolError(
            "{} SHA-256 changed: expected {}, got {} ({})".format(
                label, expected, actual, path
            )
        )
    return actual


def require_validation_revision_cache():
    info = C.require_revision_cache(PLANNER_REVISION, CACHE_BINARY_SHA256)
    preprocessor = (
        Path(info["path"])
        / "builds"
        / C.CACHE_BUILD_NAME
        / "bin"
        / "preprocess"
    )
    preprocess_sha256 = _require_file_sha256(
        preprocessor,
        CACHE_PREPROCESS_SHA256,
        "revision-cache preprocess binary",
    )
    if not os.access(preprocessor, os.X_OK):
        raise ProtocolError(
            "revision-cache preprocess binary is not executable: {}".format(
                preprocessor
            )
        )
    return {**info, "preprocess_sha256": preprocess_sha256}


def make_protocol_metadata(
    matrix,
    artifact_sha256,
    benchmark_root,
    source_attestation,
    *,
    planner_revision=PLANNER_REVISION,
    cache_binary_sha256=CACHE_BINARY_SHA256,
    cache_preprocess_sha256=CACHE_PREPROCESS_SHA256,
):
    metadata = C.common_protocol_metadata(
        planner_revision, cache_binary_sha256, matrix["run_count"]
    )
    additions = {
        "protocol": PROTOCOL,
        "analysis_protocol": ANALYSIS_PROTOCOL,
        "selection_artifact_schema": ARTIFACT_SCHEMA,
        "selection_artifact_sha256": artifact_sha256,
        "selection_rule": PILOT_SELECTION_RULE,
        "pilot_protocol": PILOT_PROTOCOL,
        "pilot_protocol_revision": PILOT_PROTOCOL_REVISION,
        "pilot_properties_canonical_sha256": matrix["properties_digest"],
        "pilot_option_matrix_sha256": PILOT_OPTION_MATRIX_SHA256,
        "pilot_selector_configs_sha256": PILOT_SELECTOR_CONFIGS_SHA256,
        "selector_eligibility_sha256": SELECTOR_ELIGIBILITY_SHA256,
        "pdb_selector_parser_protocol": PDB_SELECTOR_PARSER_PROTOCOL,
        "selector_pool_protocol": SELECTOR_POOL_PROTOCOL,
        "selector_score_version": SELECTOR_SCORE_VERSION,
        "selector_source_order": list(SELECTOR_SOURCES),
        "global_winner": matrix["global_winner"]["label"],
        "selector_family_winner": matrix["selector_winner"]["label"],
        "matched_same_k_unbatched": matrix["matched_unbatched"],
        "task_manifest": MANIFEST.name,
        "task_manifest_sha256": MANIFEST_DIGEST,
        "task_count": EXPECTED_TASKS,
        "domain_count": EXPECTED_DOMAINS,
        "source_manifest_sha256": source_attestation["source_manifest_sha256"],
        "task_sources_sha256": source_attestation["task_sources_sha256"],
        "materialized_pddl_protocol": MATERIALIZED_PDDL_PROTOCOL,
        "materialized_pddl_files": EXPECTED_MATERIALIZED_PDDL_FILES[
            matrix["run_count"]
        ],
        "materialized_pddl_bytes": EXPECTED_MATERIALIZED_PDDL_BYTES[
            matrix["run_count"]
        ],
        "pddl_bytes_per_config": EXPECTED_PDDL_BYTES_PER_CONFIG,
        "unique_pddl_source_files": EXPECTED_UNIQUE_PDDL_SOURCE_FILES,
        "unique_pddl_source_bytes": EXPECTED_UNIQUE_PDDL_SOURCE_BYTES,
        "fixed_configs_sha256": FIXED_VALIDATION_CONFIGS_SHA256,
        "config_count": len(matrix["configs"]),
        "option_matrix_sha256": matrix["matrix_digest"],
        "config_roles": copy.deepcopy(matrix["config_records"]),
        "predeclared_comparisons": copy.deepcopy(matrix["comparisons"]),
        "predeclared_comparisons_sha256": matrix["comparisons_digest"],
        "analysis_predeclaration": copy.deepcopy(
            _expected_validation_contract(
                matrix["global_winner"]["label"],
                matrix["selector_winner"]["label"],
            )["analysis"]
        ),
        "planner_preprocess_sha256": cache_preprocess_sha256,
        "experiment_data_directory": "data/{}".format(Path(__file__).stem),
        "benchmark_revision": BENCHMARK_REVISION,
        "benchmark_repository": BENCHMARK_REPOSITORY,
        "benchmark_worktree": str(Path(benchmark_root).resolve()),
    }
    overlap = set(metadata) & set(additions)
    if overlap:
        raise ProtocolError(
            "duplicate protocol metadata keys: {}".format(
                ", ".join(sorted(overlap))
            )
        )
    metadata.update(additions)
    C.validate_common_protocol_metadata(metadata)
    return metadata


def exact_header_assertions(job, num_runs):
    environment = C.get_environment()
    C.assert_exact_run_header(environment, job, num_runs)
    layout = C.validate_run_layout(num_runs)
    return [
        "#! /bin/bash",
        "#SBATCH --partition=cpu",
        "#SBATCH --qos=normal",
        "#SBATCH --time={}".format(C.SCHEDULER_TIME_LIMIT),
        "#SBATCH --mem-per-cpu={}".format(C.SCHEDULER_MEMORY_PER_CPU),
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --array=1-{}%{}".format(
            layout["array_tasks"], C.ARRAY_TASK_THROTTLE
        ),
        "#SBATCH --account={}".format(C.SCHEDULER_ACCOUNT),
    ]


def _load_json_object(path, label):
    path = Path(path)
    _require_regular_file(path, label)
    try:
        value = _parse_json_bytes(path.read_bytes(), label)
    except OSError as err:
        raise ProtocolError(
            "cannot read {} {}: {}".format(label, path, err)
        ) from err
    return value


def _require_exact_mapping(actual, expected, label):
    if not isinstance(actual, dict):
        raise ProtocolError("{} must be a mapping".format(label))
    missing = sorted(set(expected) - set(actual))
    extra = sorted(set(actual) - set(expected))
    mismatches = [
        (key, actual[key], expected[key])
        for key in sorted(set(actual) & set(expected))
        if actual[key] != expected[key]
    ]
    if missing or extra or mismatches:
        details = []
        if missing:
            details.append("missing={}".format(missing))
        if extra:
            details.append("extra={}".format(extra))
        details.extend(
            "{}={!r}, expected {!r}".format(key, got, wanted)
            for key, got, wanted in mismatches[:8]
        )
        if len(mismatches) > 8:
            details.append(
                "{} additional value mismatches".format(len(mismatches) - 8)
            )
        raise ProtocolError("{} mismatch: {}".format(label, "; ".join(details)))


def _run_relative_path(run_id):
    lower = ((run_id - 1) // 100) * 100 + 1
    upper = ((run_id + 99) // 100) * 100
    return Path("runs-{:05d}-{:05d}".format(lower, upper)) / "{:05d}".format(
        run_id
    )


def _require_pristine_run_directory(run_dir, run_id):
    if run_dir.is_symlink() or not run_dir.is_dir():
        raise ProtocolError("missing regular run directory {}".format(run_dir))
    expected_entries = {
        "domain.pddl",
        "problem.pddl",
        "run",
        "static-properties",
    }
    actual_entries = {path.name for path in run_dir.iterdir()}
    if actual_entries != expected_entries:
        raise ProtocolError(
            "run {} is not pristine: expected {}, got {}".format(
                run_id, sorted(expected_entries), sorted(actual_entries)
            )
        )


def _expected_static_properties(metadata, label, search, task, run_id):
    generated = {
        "id": [label, task.domain, task.problem],
        "algorithm": label,
        "domain": task.domain,
        "problem": task.problem,
        "repo": str(C.REPO),
        "local_revision": PLANNER_REVISION,
        "global_revision": PLANNER_REVISION,
        "build_options": list(C.BUILD_OPTIONS),
        "driver_options": list(C.LAB_DEFAULT_DRIVER_PREFIX[1:])
        + [
            "--build",
            C.CACHE_BUILD_NAME,
            "--overall-time-limit",
            C.TIME_LIMIT,
            "--overall-memory-limit",
            C.MEMORY_LIMIT,
        ],
        "component_options": ["--search", C.search_config(search)],
        "experiment_name": Path(__file__).stem,
        "run_dir": _run_relative_path(run_id).as_posix(),
    }
    overlap = set(metadata) & set(generated)
    if overlap:
        raise ProtocolError(
            "protocol metadata overlaps Lab cell fields: {}".format(
                ", ".join(sorted(overlap))
            )
        )
    return {**generated, **metadata}


def _expected_run_script(argv):
    """Render the exact Lab 8.0 run wrapper reviewed by this protocol."""
    template = '''#! /usr/bin/env python

import logging
import os
import platform

from lab.calls.call import Call
from lab import tools

tools.configure_logging()

logging.info(f"node: {platform.node()}")

run_log = open("run.log", "w")
run_err = open("run.err", "w", buffering=1)  # line buffering
redirects = {"stdout": run_log, "stderr": run_err}

# Make sure we're in the run directory.
os.chdir(os.path.dirname(os.path.abspath(__file__)))

Call(__ARGV__, hard_stderr_limit=10240, hard_stdout_limit=10240, memory_limit=None, name='planner', soft_stderr_limit=64, soft_stdout_limit=1024, time_limit=None, **redirects).wait()


for f in [run_log, run_err]:
    f.close()
    if os.path.getsize(f.name) == 0:
        os.remove(f.name)
'''
    return template.replace("__ARGV__", repr(argv))


def _git_tree_python_files(revision, prefix):
    try:
        output = subprocess.run(
            [
                "git",
                "-C",
                str(C.REPO),
                "ls-tree",
                "-r",
                "--name-only",
                revision,
                "--",
                prefix,
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except subprocess.CalledProcessError as err:
        detail = (err.stderr or err.stdout or str(err)).strip()
        raise ProtocolError(
            "cannot enumerate runtime sources at {}: {}".format(
                revision, detail
            )
        ) from err
    return sorted(line for line in output.splitlines() if line.endswith(".py"))


def _git_blob(revision, relative):
    try:
        return subprocess.run(
            ["git", "-C", str(C.REPO), "show", "{}:{}".format(revision, relative)],
            check=True,
            capture_output=True,
        ).stdout
    except subprocess.CalledProcessError as err:
        detail = err.stderr.decode("utf-8", errors="replace").strip()
        raise ProtocolError(
            "cannot read reviewed runtime source {}:{}: {}".format(
                revision, relative, detail
            )
        ) from err


def _attest_runtime_tree(code_dir):
    """Bind all copied Python runtime components to the planner revision."""
    C.reject_unattested_python_runtime_artifacts(code_dir)
    for relative in ("fast-downward.py", "build_configs.py"):
        actual = code_dir / relative
        _require_regular_file(actual, "copied runtime source")
        if actual.read_bytes() != _git_blob(PLANNER_REVISION, relative):
            raise ProtocolError(
                "copied runtime source differs from {}: {}".format(
                    PLANNER_REVISION, actual
                )
            )

    expected_driver = _git_tree_python_files(PLANNER_REVISION, "driver")
    actual_driver = sorted(
        path.relative_to(code_dir).as_posix()
        for path in (code_dir / "driver").rglob("*.py")
        if "__pycache__" not in path.parts
    )
    if actual_driver != expected_driver:
        raise ProtocolError(
            "copied driver Python file set differs from planner revision"
        )
    for relative in expected_driver:
        actual = code_dir / relative
        _require_regular_file(actual, "copied driver source")
        if actual.read_bytes() != _git_blob(PLANNER_REVISION, relative):
            raise ProtocolError(
                "copied driver source differs from {}: {}".format(
                    PLANNER_REVISION, relative
                )
            )

    expected_sources = _git_tree_python_files(PLANNER_REVISION, "src/translate")
    expected_built = [item.removeprefix("src/") for item in expected_sources]
    translator_root = (
        code_dir / "builds" / C.CACHE_BUILD_NAME / "bin" / "translate"
    )
    actual_built = sorted(
        path.relative_to(translator_root.parent).as_posix()
        for path in translator_root.rglob("*.py")
        if "__pycache__" not in path.parts
    )
    if actual_built != expected_built:
        raise ProtocolError(
            "copied translator Python file set differs from planner revision"
        )
    for source_relative, built_relative in zip(expected_sources, expected_built):
        actual = translator_root.parent / built_relative
        _require_regular_file(actual, "copied translator source")
        if actual.read_bytes() != _git_blob(PLANNER_REVISION, source_relative):
            raise ProtocolError(
                "copied translator source differs from {}: {}".format(
                    PLANNER_REVISION, source_relative
                )
            )

    built_translator_prefix = (
        Path("builds") / C.CACHE_BUILD_NAME / "bin" / "translate"
    )
    for actual in sorted(code_dir.rglob("*.py")):
        copied_relative = actual.relative_to(code_dir)
        if copied_relative.is_relative_to(built_translator_prefix):
            source_relative = (
                Path("src/translate")
                / copied_relative.relative_to(built_translator_prefix)
            )
        else:
            source_relative = copied_relative
        if actual.read_bytes() != _git_blob(
            PLANNER_REVISION, source_relative.as_posix()
        ):
            raise ProtocolError(
                "copied Python source differs from {}: {}".format(
                    PLANNER_REVISION, copied_relative.as_posix()
                )
            )


def _make_expected_grid_job(grid_path, num_runs):
    class FakeBuildStep:
        name = "build"
        _funcname = "build"

    class FakeStartStep:
        name = "start"
        _funcname = "start_runs"

    class FakeExperiment:
        name = grid_path.name
        path = str(grid_path)

        def __init__(self):
            self.runs = [None] * num_runs
            self.steps = [FakeBuildStep(), FakeStartStep()]

    environment = C.get_environment()
    environment.exp = FakeExperiment()
    environment.job_dir = grid_path.parent / "{}-grid-steps".format(
        grid_path.name
    )
    return environment._get_job(environment.exp.steps[1], True)


def _attest_fresh_start_job(grid_path, num_runs):
    """Certify the prospective start job and reject resubmission state."""
    job_dir = grid_path.parent / "{}-grid-steps".format(grid_path.name)
    if job_dir.exists() or job_dir.is_symlink():
        raise ProtocolError(
            "refusing start because the grid-steps directory already exists: "
            "{}".format(job_dir)
        )
    eval_dir = Path(str(grid_path) + "-eval")
    if eval_dir.exists() or eval_dir.is_symlink():
        raise ProtocolError(
            "refusing start because the evaluation directory already exists: "
            "{}".format(eval_dir)
        )
    expected_job = _make_expected_grid_job(grid_path, num_runs)
    exact_header_assertions(expected_job, num_runs)
    return expected_job, hashlib.sha256(expected_job.encode("utf-8")).hexdigest()


def attest_existing_start_grid(
    metadata, benchmark_root, task_descriptions, matrix
):
    """Fail closed unless the already-built grid is exactly launchable."""
    grid_path = EXPERIMENT_DATA_PATH
    if grid_path.is_symlink() or not grid_path.is_dir():
        raise ProtocolError(
            "start requires an existing regular experiment grid: {}".format(
                grid_path
            )
        )

    expected_experiment_properties = {
        "algorithms": [label for label, _ in matrix["configs"]],
        "experiment_file": Path(__file__).name,
        "runs": matrix["run_count"],
        "suite": {str(benchmark_root): list(task_descriptions)},
    }
    experiment_properties = _load_json_object(
        grid_path / "static-experiment-properties",
        "static experiment properties",
    )
    _require_exact_mapping(
        experiment_properties,
        expected_experiment_properties,
        "static experiment properties",
    )

    cache_name = metadata["planner_revision_cache_name"]
    expected_code_name = "code-{}".format(cache_name)
    code_entries = sorted(
        path.name for path in grid_path.iterdir() if path.name.startswith("code-")
    )
    if code_entries != [expected_code_name]:
        raise ProtocolError(
            "grid must contain exactly one copied code directory {!r}; got {}".
            format(expected_code_name, code_entries)
        )
    code_dir = grid_path / expected_code_name
    if code_dir.is_symlink() or not code_dir.is_dir():
        raise ProtocolError(
            "copied code entry must be a regular directory: {}".format(code_dir)
        )
    _require_file_sha256(
        code_dir / "build_successful",
        C.CACHE_SENTINEL_SHA256,
        "copied cache success sentinel",
    )
    binary_path = code_dir / "builds" / C.CACHE_BUILD_NAME / "bin" / "downward"
    binary_sha256 = _require_file_sha256(
        binary_path, CACHE_BINARY_SHA256, "copied planner binary"
    )
    if not os.access(binary_path, os.X_OK):
        raise ProtocolError(
            "copied planner binary is not executable: {}".format(binary_path)
        )
    preprocess_path = (
        code_dir / "builds" / C.CACHE_BUILD_NAME / "bin" / "preprocess"
    )
    preprocess_sha256 = _require_file_sha256(
        preprocess_path, CACHE_PREPROCESS_SHA256, "copied preprocess binary"
    )
    if not os.access(preprocess_path, os.X_OK):
        raise ProtocolError(
            "copied preprocess binary is not executable: {}".format(
                preprocess_path
            )
        )
    _attest_runtime_tree(code_dir)

    ordered_tasks = _resolve_ordered_tasks(benchmark_root, task_descriptions)
    source_records = _heldout_source_records(task_descriptions)
    materialized_files = 0
    materialized_bytes = 0
    expected_run_groups = {
        _run_relative_path(run_id).parent.name
        for run_id in range(1, matrix["run_count"] + 1)
    }
    actual_run_groups = {
        path.name for path in grid_path.iterdir() if path.name.startswith("runs-")
    }
    if actual_run_groups != expected_run_groups:
        raise ProtocolError(
            "run-group directories differ: expected {}, got {}".format(
                sorted(expected_run_groups), sorted(actual_run_groups)
            )
        )
    expected_grid_entries = expected_run_groups | {
        expected_code_name,
        "static-experiment-properties",
    }
    actual_grid_entries = {path.name for path in grid_path.iterdir()}
    if actual_grid_entries != expected_grid_entries:
        raise ProtocolError(
            "experiment-grid entries differ: expected {}, got {}".format(
                sorted(expected_grid_entries), sorted(actual_grid_entries)
            )
        )

    expected_static_paths = {
        grid_path / _run_relative_path(run_id) / "static-properties"
        for run_id in range(1, matrix["run_count"] + 1)
    }
    actual_static_paths = set(grid_path.glob("runs-*/*/static-properties"))
    if actual_static_paths != expected_static_paths:
        raise ProtocolError(
            "grid must contain exactly {} static-properties files; got {}".
            format(len(expected_static_paths), len(actual_static_paths))
        )

    seen_ids = set()
    for config_index, (label, search) in enumerate(matrix["configs"]):
        for task_index, task in enumerate(ordered_tasks):
            run_id = config_index * len(ordered_tasks) + task_index + 1
            run_dir = grid_path / _run_relative_path(run_id)
            _require_pristine_run_directory(run_dir, run_id)
            properties = _load_json_object(
                run_dir / "static-properties",
                "static properties for run {}".format(run_id),
            )
            _require_exact_mapping(
                properties,
                _expected_static_properties(
                    metadata, label, search, task, run_id
                ),
                "static properties for run {}".format(run_id),
            )
            cell_id = tuple(properties["id"])
            if cell_id in seen_ids:
                raise ProtocolError(
                    "duplicate static cell identity: {}".format(cell_id)
                )
            seen_ids.add(cell_id)

            record = source_records[(task.domain, task.problem)]
            for link_name, source, hash_field in (
                (
                    "domain.pddl",
                    Path(task.domain_file).resolve(),
                    "domain_sha256",
                ),
                (
                    "problem.pddl",
                    Path(task.problem_file).resolve(),
                    "problem_sha256",
                ),
            ):
                materialized_bytes += C.require_materialized_pddl(
                    run_dir / link_name,
                    record[hash_field],
                    "run {} {}".format(run_id, link_name),
                    source,
                )
                materialized_files += 1

            argv = [
                sys.executable,
                str(code_dir / "fast-downward.py"),
                *properties["driver_options"],
                "domain.pddl",
                "problem.pddl",
                *properties["component_options"],
            ]
            run_script = run_dir / "run"
            _require_regular_file(run_script, "run wrapper")
            try:
                actual_script = run_script.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as err:
                raise ProtocolError(
                    "cannot read run wrapper {}: {}".format(run_script, err)
                ) from err
            if actual_script != _expected_run_script(argv):
                raise ProtocolError(
                    "run {} wrapper differs from the reviewed Lab 8.0 "
                    "template/options".format(run_id)
                )

    if len(seen_ids) != matrix["run_count"]:
        raise ProtocolError(
            "grid has {} unique cell identities; expected {}".format(
                len(seen_ids), matrix["run_count"]
            )
        )
    expected_files = EXPECTED_MATERIALIZED_PDDL_FILES[matrix["run_count"]]
    expected_bytes = EXPECTED_MATERIALIZED_PDDL_BYTES[matrix["run_count"]]
    if materialized_files != expected_files or materialized_bytes != expected_bytes:
        raise ProtocolError(
            "attested materialized held-out PDDL totals changed: files={}, "
            "bytes={}".format(materialized_files, materialized_bytes)
        )
    for group_name in sorted(expected_run_groups):
        group = grid_path / group_name
        if group.is_symlink() or not group.is_dir():
            raise ProtocolError("invalid run-group directory {}".format(group))
        expected_children = {
            _run_relative_path(run_id).name
            for run_id in range(1, matrix["run_count"] + 1)
            if _run_relative_path(run_id).parent.name == group_name
        }
        actual_children = {path.name for path in group.iterdir()}
        if actual_children != expected_children:
            raise ProtocolError(
                "run directories in {} differ from exact grid".format(group_name)
            )

    _, expected_job_sha256 = _attest_fresh_start_job(
        grid_path, matrix["run_count"]
    )
    return {
        "grid_path": str(grid_path),
        "run_count": len(seen_ids),
        "code_directory": expected_code_name,
        "binary_sha256": binary_sha256,
        "preprocess_sha256": preprocess_sha256,
        "materialized_pddl_files": materialized_files,
        "materialized_pddl_bytes": materialized_bytes,
        "job_sha256": expected_job_sha256,
    }


def inspect_launch_blockers(artifact_sha256):
    """Return all launch gates without changing worktree, cache, or grid."""
    checks = (
        (
            "reviewed selection artifact hash",
            lambda: require_selection_artifact_hash(
                artifact_sha256, required=True
            ),
        ),
        ("reviewed P4 planner/screen/cache pins", validate_cache_pins),
        (
            "committed planner/protocol revision",
            lambda: C.require_clean_committed_revision(
                PLANNER_REVISION, protocol_files=PROTOCOL_FILES
            ),
        ),
        ("requirements Lab version", C.require_pinned_lab_version),
        ("release_no_lp revision cache", require_validation_revision_cache),
    )
    blockers = []
    for label, check in checks:
        try:
            check()
        except (ProtocolError, RuntimeError) as err:
            blockers.append(
                "{}: {}".format(label, str(err).replace("\n", " | "))
            )
    return blockers


def _expect_protocol_error(function, expected_fragment=None):
    try:
        function()
    except (ProtocolError, RuntimeError) as err:
        if expected_fragment is not None and expected_fragment not in str(err):
            raise AssertionError(
                "expected protocol error containing {!r}, got {!r}".format(
                    expected_fragment, str(err)
                )
            ) from err
    else:
        raise AssertionError("expected ProtocolError")


def _synthetic_score(label, rank):
    return {
        "label": label,
        "search": PILOT_SEARCHES[label],
        "coverage": PILOT_TASKS,
        "micro_par2": float(rank),
        "total_image_time": float(rank) / 10.0,
        "image_metrics_complete": True,
        "construction": {
            "completed": PILOT_TASKS,
            "fallbacks": 0,
            "unobserved": 0,
            "pattern_fallbacks": 0,
        },
        "cofactor_width": {
            "observed": PILOT_TASKS,
            "minimum": 1,
            "median": 1,
            "maximum": 1,
        },
        "selector": {
            "certified": 0,
            "interrupted": 0,
            "selected_sources": {source: 0 for source in SELECTOR_SOURCES},
        },
        "rank": rank,
    }


def _synthetic_artifact(global_label, selector_label):
    if selector_label not in SELECTOR_LABELS:
        raise AssertionError("synthetic selector winner must be eligible")
    order = [global_label]
    if selector_label not in order:
        order.append(selector_label)
    order.extend(label for label in PILOT_LABELS if label not in order)
    ranking = [
        _synthetic_score(label, rank) for rank, label in enumerate(order, 1)
    ]
    by_label = {score["label"]: score for score in ranking}
    paired = []
    for label in PILOT_LABELS:
        for reference in ("blind_fw", "ms_exact"):
            paired.append(
                {
                    "label": label,
                    "reference": reference,
                    "coverage_delta": 0,
                    "micro_par2_delta": (
                        by_label[label]["micro_par2"]
                        - by_label[reference]["micro_par2"]
                    ),
                    "wins": 0,
                    "losses": 0,
                    "both_solved": PILOT_TASKS,
                    "both_unsolved": 0,
                    "total_image_time_delta": (
                        by_label[label]["total_image_time"]
                        - by_label[reference]["total_image_time"]
                    ),
                }
            )
    pilot = {
        "protocol": PILOT_PROTOCOL,
        "selection_rule": PILOT_SELECTION_RULE,
        "planner_revision": PLANNER_REVISION,
        "protocol_revision": PILOT_PROTOCOL_REVISION,
        "planner_revision_is_protocol_ancestor": True,
        "planner_binary_sha256": CACHE_BINARY_SHA256,
        "planner_preprocess_sha256": CACHE_PREPROCESS_SHA256,
        "planner_build_config": "release_no_lp",
        "benchmark_revision": BENCHMARK_REVISION,
        "benchmark_repository": BENCHMARK_REPOSITORY,
        "task_manifest": PILOT_MANIFEST,
        "task_manifest_sha256": PILOT_MANIFEST_SHA256,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
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
        "pdb_selector_parser_protocol": PDB_SELECTOR_PARSER_PROTOCOL,
        "metrics_validation_protocol": METRICS_VALIDATION_PROTOCOL,
        "outcome_reconciliation_protocol": OUTCOME_RECONCILIATION_PROTOCOL,
        "selector_pool_protocol": SELECTOR_POOL_PROTOCOL,
        "selector_score_version": SELECTOR_SCORE_VERSION,
        "selector_source_order": list(SELECTOR_SOURCES),
        "options": _option_records(PILOT_CONFIG_MATRIX),
        "task_count": PILOT_TASKS,
        "config_count": PILOT_CONFIGS,
        "expected_run_count": PILOT_CELLS,
        "time_limit_seconds": TIME_LIMIT_SECONDS,
        "memory_limit_mib": MEMORY_LIMIT_MIB,
        "par2_unsolved_seconds": PAR2_UNSOLVED_SECONDS,
        "properties_canonical_sha256": hashlib.sha256(
            ("synthetic-properties:" + selector_label).encode("ascii")
        ).hexdigest(),
    }
    return {
        "schema": ARTIFACT_SCHEMA,
        "pilot": pilot,
        "selection": {
            "image_time_tiebreak_used": True,
            "global_winner": copy.deepcopy(ranking[0]),
            "selector_family_winner": copy.deepcopy(by_label[selector_label]),
            "selector_eligibility_labels": list(SELECTOR_LABELS),
            "selector_eligibility_sha256": SELECTOR_ELIGIBILITY_SHA256,
            "ranking": ranking,
        },
        "paired_deltas": paired,
        "validation": _expected_validation_contract(
            global_label, selector_label
        ),
    }


def _tampered_artifact_rejected(artifact, mutate):
    changed = copy.deepcopy(artifact)
    mutate(changed)
    _expect_protocol_error(lambda: validate_selection_artifact(changed))


def self_test_start_preflight_helpers():
    if normalize_lab_steps(["parse", "4", "report"]) != [
        "parse",
        "fetch",
        "report",
    ]:
        raise AssertionError("read-only Lab step normalization changed")
    if normalize_lab_steps(["build"]) != ["build"]:
        raise AssertionError("standalone build normalization changed")
    if normalize_lab_steps(["2"]) != ["start"]:
        raise AssertionError("standalone start normalization changed")
    _expect_protocol_error(
        lambda: normalize_lab_steps(["start", "2"]), "duplicate Lab step"
    )
    _expect_protocol_error(
        lambda: normalize_lab_steps(["build", "start"]),
        "must run in its own invocation",
    )
    _expect_protocol_error(
        lambda: normalize_lab_steps(["start", "parse"]),
        "must run in its own invocation",
    )
    _expect_protocol_error(
        lambda: normalize_lab_steps(["02"]), "unknown Lab step"
    )

    expected_static = {
        "protocol_revision": "1234567890abcdef1234567890abcdef12345678",
        "algorithm": "selector",
        "component_options": ["--search", "exact"],
    }
    changed_static = dict(
        expected_static, component_options=["--search", "blind"]
    )
    _expect_protocol_error(
        lambda: _require_exact_mapping(
            changed_static, expected_static, "synthetic static properties"
        ),
        "component_options=",
    )

    with tempfile.TemporaryDirectory(prefix="selector-validation-preflight-") as raw:
        temporary_root = Path(raw)
        copied_binary = temporary_root / "downward"
        copied_binary.write_bytes(b"reviewed copied planner")
        expected_hash = hashlib.sha256(copied_binary.read_bytes()).hexdigest()
        _require_file_sha256(
            copied_binary, expected_hash, "synthetic copied planner"
        )
        copied_binary.write_bytes(b"changed copied planner")
        _expect_protocol_error(
            lambda: _require_file_sha256(
                copied_binary, expected_hash, "synthetic copied planner"
            ),
            "SHA-256 changed",
        )

        for num_runs in (644, 736):
            grid = temporary_root / "fresh-grid-{}".format(num_runs)
            grid.mkdir()
            prospective_job, prospective_hash = _attest_fresh_start_job(
                grid, num_runs
            )
            if hashlib.sha256(prospective_job.encode("utf-8")).hexdigest() != (
                prospective_hash
            ):
                raise AssertionError("prospective start-job hash changed")
            expected_array = "#SBATCH --array=1-{}%5".format(num_runs)
            if prospective_job.splitlines().count(expected_array) != 1:
                raise AssertionError("prospective array layout changed")

        stale_grid = temporary_root / "stale-grid"
        stale_grid.mkdir()
        stale_grid.parent.joinpath("stale-grid-grid-steps").mkdir()
        _expect_protocol_error(
            lambda: _attest_fresh_start_job(stale_grid, 644),
            "grid-steps directory already exists",
        )
        evaluated_grid = temporary_root / "evaluated-grid"
        evaluated_grid.mkdir()
        Path(str(evaluated_grid) + "-eval").mkdir()
        _expect_protocol_error(
            lambda: _attest_fresh_start_job(evaluated_grid, 644),
            "evaluation directory already exists",
        )
        pristine_run = temporary_root / "run-directory"
        pristine_run.mkdir()
        for name in ("domain.pddl", "problem.pddl", "run", "static-properties"):
            (pristine_run / name).write_bytes(b"synthetic")
        _require_pristine_run_directory(pristine_run, 1)
        (pristine_run / "driver.log").write_bytes(b"stale")
        _expect_protocol_error(
            lambda: _require_pristine_run_directory(pristine_run, 1),
            "is not pristine",
        )

        fresh_build = temporary_root / "fresh-build"
        C.require_fresh_experiment_build(fresh_build)
        fresh_build.mkdir()
        _expect_protocol_error(
            lambda: C.require_fresh_experiment_build(fresh_build),
            "experiment output path already exists",
        )
        dangling_build = temporary_root / "dangling-build"
        dangling_build.symlink_to(temporary_root / "missing-target")
        _expect_protocol_error(
            lambda: C.require_fresh_experiment_build(dangling_build),
            "experiment output path already exists",
        )
        sibling_build = temporary_root / "sibling-build"
        sibling_build.parent.joinpath("sibling-build-grid-steps").mkdir()
        _expect_protocol_error(
            lambda: C.require_fresh_experiment_build(sibling_build),
            "experiment output path already exists",
        )
        evaluated_build = temporary_root / "evaluated-build"
        Path(str(evaluated_build) + "-eval").mkdir()
        _expect_protocol_error(
            lambda: C.require_fresh_experiment_build(evaluated_build),
            "experiment output path already exists",
        )

        bytecode_grid = temporary_root / "bytecode-grid"
        copied_code = bytecode_grid / "code-fixture"
        copied_cache = copied_code / "driver" / "__pycache__"
        copied_cache.mkdir(parents=True)
        (copied_code / "driver" / "module.py").write_bytes(b"x = 1\n")
        (copied_cache / "module.cpython-39.pyc").write_bytes(b"bytecode")
        cleanup = C.strip_copied_python_bytecode(bytecode_grid)
        if (
            cleanup["removed_bytecode_files"] != 1
            or cleanup["removed_cache_directories"] != 1
        ):
            raise AssertionError("copied-bytecode cleanup summary changed")
        C.reject_unattested_python_runtime_artifacts(copied_code)
        (copied_code / "sitecustomize.cpython-39-x86_64-linux-gnu.so").write_bytes(
            b"native shadow"
        )
        _expect_protocol_error(
            lambda: C.reject_unattested_python_runtime_artifacts(copied_code),
            "unattested importable code",
        )
        (copied_code / "sitecustomize.cpython-39-x86_64-linux-gnu.so").unlink()
        runtime_link = copied_code / "driver-link"
        runtime_link.symlink_to(copied_code / "driver", target_is_directory=True)
        _expect_protocol_error(
            lambda: C.reject_unattested_python_runtime_artifacts(copied_code),
            "contains a symlink",
        )

        reviewed_code = temporary_root / "reviewed-code"
        (reviewed_code / "driver").mkdir(parents=True)
        for relative in ("fast-downward.py", "build_configs.py"):
            (reviewed_code / relative).write_bytes(b"reviewed source\n")
        (reviewed_code / "sitecustomize.py").write_bytes(b"shadow source\n")
        original_tree = _git_tree_python_files
        original_blob = _git_blob

        def synthetic_tree(revision, prefix):
            return []

        def synthetic_blob(revision, relative):
            if relative in {"fast-downward.py", "build_configs.py"}:
                return b"reviewed source\n"
            raise ProtocolError("synthetic unreviewed source: {}".format(relative))

        globals()["_git_tree_python_files"] = synthetic_tree
        globals()["_git_blob"] = synthetic_blob
        try:
            _expect_protocol_error(
                lambda: _attest_runtime_tree(reviewed_code),
                "synthetic unreviewed source: sitecustomize.py",
            )
        finally:
            globals()["_git_tree_python_files"] = original_tree
            globals()["_git_blob"] = original_blob

    unsupported = SimpleNamespace(
        domain="definitely-not-a-suite-domain", problem="unsupported.pddl"
    )
    _expect_protocol_error(
        lambda: _require_supported_tasks([unsupported]), "unsupported"
    )
    _expect_protocol_error(
        lambda: _require_disjoint_task_sets(
            ["heldout:p01.pddl"],
            [("synthetic-development", ["heldout:p01.pddl"])],
        ),
        "overlaps synthetic-development",
    )


def self_test():
    C.self_test_scheduler_headers()
    C.self_test_cofactor_width_parser()
    C.self_test_pdb_selector_parser()
    C.self_test_plan_file_parser()
    C.self_test_outcome_reconciliation_parser()
    C.self_test_pddl_materialization()
    _validate_frozen_constants()
    validate_fixed_environment()
    validate_cache_pins()
    tasks = read_manifest()
    source_attestation = validate_manifest_record_pins(tasks)

    unbatched = _synthetic_artifact("ms_cap32", "pdb_selector_k32")
    unbatched_matrix = validate_selection_artifact(unbatched)
    validate_matrix(tasks, unbatched_matrix)
    if (
        len(unbatched_matrix["configs"]) != 7
        or unbatched_matrix["run_count"] != 644
        or unbatched_matrix["matched_unbatched"] is not None
        or unbatched_matrix["materialized_pddl_files"] != 1288
        or unbatched_matrix["materialized_pddl_bytes"] != 72541896
    ):
        raise AssertionError("synthetic unbatched 7x92 contract changed")
    if [item["label"] for item in unbatched_matrix["config_records"]] != [
        "blind_fw",
        "ms_exact",
        "ms_cap32",
        "pdb_goal_fill_b100k",
        "pdb_cegar_b100k",
        "ms_cap32_build60",
        "pdb_selector_k32",
    ]:
        raise AssertionError("unbatched validation order/dedup changed")
    ms_roles = unbatched_matrix["config_records"][2]["roles"]
    if "pilot-global-winner" not in ms_roles:
        raise AssertionError("global winner alias did not deduplicate")

    batched_label = "pdb_selector_k64_adapt_w64_r1_n1m"
    batched = _synthetic_artifact(batched_label, batched_label)
    batched_matrix = validate_selection_artifact(batched)
    validate_matrix(tasks, batched_matrix)
    if (
        len(batched_matrix["configs"]) != 8
        or batched_matrix["run_count"] != 736
        or batched_matrix["matched_unbatched"] != "pdb_selector_k64"
        or batched_matrix["materialized_pddl_files"] != 1472
        or batched_matrix["materialized_pddl_bytes"] != 82905024
    ):
        raise AssertionError("synthetic batched 8x92 contract changed")
    if [item["label"] for item in batched_matrix["config_records"]][-2:] != [
        batched_label,
        "pdb_selector_k64",
    ]:
        raise AssertionError("conditional same-K validation order changed")
    if "pilot-global-winner" not in batched_matrix["config_records"][-2]["roles"]:
        raise AssertionError("batched global winner alias did not deduplicate")
    if any("selection_artifact_sha256" in value for value in unbatched):
        raise AssertionError("selection artifact contains a forbidden self hash")

    with tempfile.TemporaryDirectory(prefix="selector-artifact-v3-") as raw:
        artifact_path = Path(raw) / "selection.json"
        artifact_bytes = (canonical_json(unbatched) + "\n").encode("ascii")
        artifact_path.write_bytes(artifact_bytes)
        loaded, raw_sha256, loaded_path = load_selection_artifact(artifact_path)
        if loaded != unbatched or loaded_path != artifact_path.resolve():
            raise AssertionError("strict selection artifact load changed")
        if raw_sha256 != hashlib.sha256(artifact_bytes).hexdigest():
            raise AssertionError("selection raw-byte hash changed")
        artifact_link = artifact_path.with_name("selection-link.json")
        artifact_link.symlink_to(artifact_path)
        _expect_protocol_error(
            lambda: load_selection_artifact(artifact_link), "non-symlink"
        )
        require_selection_artifact_hash(
            raw_sha256, required=True, expected_sha256=raw_sha256
        )
        _expect_protocol_error(
            lambda: require_selection_artifact_hash(
                raw_sha256, required=True, expected_sha256=None
            ),
            "is unset",
        )
        _expect_protocol_error(
            lambda: require_selection_artifact_hash(
                raw_sha256,
                required=False,
                expected_sha256=hashlib.sha256(b"different").hexdigest(),
            ),
            "changed",
        )

    _expect_protocol_error(
        lambda: _parse_json_bytes(b'{"x":1,"x":2}', "duplicate fixture"),
        "duplicate JSON keys",
    )
    _expect_protocol_error(
        lambda: _parse_json_bytes(b'{"x":NaN}', "NaN fixture"),
        "non-finite",
    )
    _expect_protocol_error(
        lambda: _parse_json_bytes(b'{"x":1e999}', "overflow fixture"),
        "non-finite",
    )
    _expect_protocol_error(
        lambda: _parse_json_bytes(b'{"x":"TBD"}', "placeholder fixture"),
        "placeholder",
    )

    _tampered_artifact_rejected(
        unbatched, lambda item: item.update(schema=ARTIFACT_SCHEMA + "-changed")
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["pilot"].update(planner_revision="1234"),
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["selection"]["ranking"].reverse(),
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["selection"].update(
            global_winner=item["selection"]["ranking"][1]
        ),
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["selection"]["selector_eligibility_labels"].pop(),
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["validation"]["configs"][5].update(
            search="sym_fw_ms(build_time_limit=59)"
        ),
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["validation"].update(option_matrix_sha256=(
            hashlib.sha256(b"changed matrix").hexdigest()
        )),
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["validation"].update(config_count=8),
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["validation"].update(config_count=7.0),
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["validation"].update(task_sources_sha256=(
            hashlib.sha256(b"changed sources").hexdigest()
        )),
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["validation"]["comparisons"].pop(),
    )
    _tampered_artifact_rejected(
        unbatched,
        lambda item: item["validation"]["analysis"].update(
            rerank_on_validation=True
        ),
    )

    synthetic_sha = hashlib.sha256(canonical_json(unbatched).encode("ascii")).hexdigest()
    metadata = make_protocol_metadata(
        unbatched_matrix,
        synthetic_sha,
        C.REPO,
        source_attestation,
        planner_revision=C.REV,
        cache_binary_sha256=hashlib.sha256(
            b"synthetic heldout binary"
        ).hexdigest(),
        cache_preprocess_sha256=hashlib.sha256(
            b"synthetic heldout preprocess"
        ).hexdigest(),
    )
    if (
        metadata["selection_artifact_sha256"] != synthetic_sha
        or metadata["analysis_protocol"] != ANALYSIS_PROTOCOL
        or metadata["declared_run_count"] != 644
        or metadata["materialized_pddl_files"] != 1288
        or metadata["materialized_pddl_bytes"] != 72541896
    ):
        raise AssertionError("prospective protocol metadata changed")
    expected_selector_metadata = {
        "pdb_selector_parser_protocol": PDB_SELECTOR_PARSER_PROTOCOL,
        "selector_pool_protocol": SELECTOR_POOL_PROTOCOL,
        "selector_score_version": SELECTOR_SCORE_VERSION,
        "selector_source_order": list(SELECTOR_SOURCES),
    }
    if any(
        metadata.get(key) != value
        for key, value in expected_selector_metadata.items()
    ):
        raise AssertionError("held-out selector interpretation pins changed")
    self_test_start_preflight_helpers()

    for matrix in (unbatched_matrix, batched_matrix):
        _, job = C.make_in_memory_run_job(matrix["run_count"])
        for line in exact_header_assertions(job, matrix["run_count"]):
            if job.splitlines().count(line) != 1:
                raise AssertionError(
                    "generated job does not contain one exact {!r}".format(line)
                )
    print(
        "Arrhenius selector held-out runner self-test: PASS "
        "(artifact v3; tampering; 7/8-config dedup; 644/736 arrays; fresh start)"
    )
    if EXPECTED_SELECTION_ARTIFACT_SHA256 is None:
        print("launch gate: BLOCKED (EXPECTED_SELECTION_ARTIFACT_SHA256 is unset)")
    else:
        print("launch gate: artifact hash pinned")


def check_protocol(
    tasks, matrix, artifact_sha256, artifact_path, benchmark_root,
    source_attestation
):
    cache_info = (
        C.inspect_revision_cache(PLANNER_REVISION)
        if isinstance(PLANNER_REVISION, str)
        else None
    )
    cached_preprocessor = (
        Path(cache_info["path"])
        / "builds"
        / C.CACHE_BUILD_NAME
        / "bin"
        / "preprocess"
        if cache_info is not None
        else None
    )
    cached_preprocess_sha256 = (
        _sha256_file(cached_preprocessor)
        if cached_preprocessor is not None and cached_preprocessor.is_file()
        else None
    )
    blockers = inspect_launch_blockers(artifact_sha256)
    _, job = C.make_in_memory_run_job(matrix["run_count"])
    headers = exact_header_assertions(job, matrix["run_count"])
    print("Arrhenius selector held-out read-only check: PASS")
    print("selection artifact: {}".format(artifact_path))
    print("selection artifact raw SHA-256: {}".format(artifact_sha256))
    print("selection artifact schema: {}".format(ARTIFACT_SCHEMA))
    print("global winner alias: {}".format(matrix["global_winner"]["label"]))
    print("selector-family winner: {}".format(matrix["selector_winner"]["label"]))
    print("same-K unbatched: {}".format(matrix["matched_unbatched"]))
    print(
        "tasks: {}; configs: {}; runs: {}".format(
            len(tasks), len(matrix["configs"]), matrix["run_count"]
        )
    )
    print("held-out manifest SHA-256: {}".format(MANIFEST_DIGEST))
    print(
        "held-out source records SHA-256: {}".format(
            source_attestation["task_sources_sha256"]
        )
    )
    print("option matrix SHA-256: {}".format(matrix["matrix_digest"]))
    print("comparisons SHA-256: {}".format(matrix["comparisons_digest"]))
    print("analysis protocol: {}".format(ANALYSIS_PROTOCOL))
    print("benchmark revision/worktree: {} {}".format(
        BENCHMARK_REVISION, benchmark_root
    ))
    print("revision cache: {}".format(
        cache_info["path"] if cache_info is not None else "UNSET"
    ))
    print("cached binary SHA-256: {}".format(
        cache_info["binary_sha256"] if cache_info is not None else "UNSET"
    ))
    print("cached preprocess SHA-256: {}".format(cached_preprocess_sha256))
    print("launch gate: {}".format("BLOCKED" if blockers else "READY"))
    for blocker in blockers:
        print("  " + blocker)
    print("exact generated header assertions:")
    for line in headers:
        print("  " + line)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.self_test:
        self_test()
        return 0
    if args.selection is None:
        raise ProtocolError(
            "--selection is required; held-out execution has no default winner"
        )
    if not args.check and not args.steps:
        raise ProtocolError("provide Lab steps, --check, or --self-test")

    artifact, artifact_sha256, artifact_path = load_selection_artifact(
        args.selection
    )
    matrix = validate_selection_artifact(artifact)
    launch_requested = any(step in ("build", "start") for step in args.steps)
    require_selection_artifact_hash(
        artifact_sha256, required=launch_requested
    )
    tasks = read_manifest()
    validate_manifest_record_pins(tasks)
    validate_matrix(tasks, matrix)
    benchmark_root = require_pinned_benchmark_worktree()
    source_attestation = attest_task_sources(benchmark_root, tasks)

    if args.check:
        check_protocol(
            tasks,
            matrix,
            artifact_sha256,
            artifact_path,
            benchmark_root,
            source_attestation,
        )
        return 0

    validate_cache_pins()
    cache_info = C.require_launch_prerequisites(
        PLANNER_REVISION,
        CACHE_BINARY_SHA256,
        args=args.steps,
        protocol_files=PROTOCOL_FILES,
    )
    if cache_info is not None:
        require_validation_revision_cache()
    _, job = C.make_in_memory_run_job(matrix["run_count"])
    exact_header_assertions(job, matrix["run_count"])
    metadata = make_protocol_metadata(
        matrix, artifact_sha256, benchmark_root, source_attestation
    )
    if "build" in args.steps:
        C.require_fresh_experiment_build(EXPERIMENT_DATA_PATH)
    if "start" in args.steps:
        attestation = attest_existing_start_grid(
            metadata, benchmark_root, tasks, matrix
        )
        print(
            "start grid attestation: PASS ({} runs; {} PDDL files/{} bytes; "
            "binary {}; preprocess {}; job {})".format(
                attestation["run_count"],
                attestation["materialized_pddl_files"],
                attestation["materialized_pddl_bytes"],
                attestation["binary_sha256"],
                attestation["preprocess_sha256"],
                attestation["job_sha256"],
            )
        )
    experiment = C.new_experiment(metadata)
    if Path(experiment.path).resolve() != EXPERIMENT_DATA_PATH:
        raise ProtocolError(
            "experiment data path changed: {} != {}".format(
                Path(experiment.path).resolve(), EXPERIMENT_DATA_PATH
            )
        )
    C.add_suite(experiment, benchmark_root, tasks)
    for label, search in matrix["configs"]:
        C.add_algorithm(
            experiment, label, search, revision=PLANNER_REVISION
        )
    C.add_standard_steps(experiment)
    sys.argv = [sys.argv[0]] + args.steps
    experiment.run_steps()
    if "build" in args.steps:
        materialized = materialize_grid_pddl_inputs(
            benchmark_root, tasks, matrix
        )
        cleanup = C.strip_copied_python_bytecode(EXPERIMENT_DATA_PATH)
        attestation = attest_existing_start_grid(
            metadata, benchmark_root, tasks, matrix
        )
        print(
            "built grid normalization/attestation: PASS "
            "({} PDDL files/{} bytes materialized; {} bytecode files; {} "
            "cache directories removed; job {})".
            format(
                materialized["files"],
                materialized["bytes"],
                cleanup["removed_bytecode_files"],
                cleanup["removed_cache_directories"],
                attestation["job_sha256"],
            )
        )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ProtocolError, RuntimeError) as err:
        print("protocol error: {}".format(err), file=sys.stderr)
        sys.exit(2)
