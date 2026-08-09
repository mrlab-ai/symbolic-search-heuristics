#!/usr/bin/env python3
"""Validate, summarize, and rank the 20x50 Arrhenius selector screen.

This analyzer is deliberately read-only and fail-closed.  It accepts exactly
the tasks, options, revisions, resource limits, and scheduler protocol declared
by :mod:`exp_arrhenius_selector_pilot`. Every expected algorithm-task cell has a
well-formed, explained Fast Downward outcome, and solved costs must agree within
each task.

The predeclared selection rule orders all 20 configurations: maximize coverage,
minimize micro-PAR2 (600 seconds for every unsolved cell), then minimize total
image time only if every one of the 1000 cells has complete schema-v2 certified
metrics, then use the configuration label. Artifact v2 records both the global
winner and the first selector in this same frozen order. It also derives the
prospective held-out configuration matrix without inspecting held-out outcomes.

``--emit-selection-artifact`` prints deterministic JSON to stdout and never
writes a file. The planner revision, launch-protocol revision, and cached
binary hash are pinned independently below. ``--self-test`` injects synthetic
values.
"""

from __future__ import annotations

import argparse
import copy
from fractions import Fraction
import hashlib
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

# Reuse the mature, read-only properties/archive loader, exact manifest reader,
# numeric helpers, and table renderer.  Do not change the frozen analyzer.
import analyze_ms_caps_pilot as analyzer_utils
import exp_arrhenius_common as common
import exp_arrhenius_selector_pilot as runner
import suite_cost_manifest
import wbh_parser


class AnalysisError(RuntimeError):
    pass


# The cached planner is intentionally older than the protocol commit: the
# runner pins this exact source commit while recording its clean launch HEAD in
# the separate ``protocol_revision`` property.  This avoids cache self-reference.
EXPECTED_PLANNER_REVISION = "8e56de8862c9449246596e779177cc9e6a7bcf8e"

# Exact clean launch worktree revision. The analyzer lives in a descendant
# commit so this pin does not create a commit-hash self-reference.
EXPECTED_PROTOCOL_REVISION = "d3049f8f0c4022e8bed4b9a564131262a7f810b6"
EXPECTED_CACHE_BINARY_SHA256 = (
    "21ea6aff991b4f8196ee8642ff0534bebae67ee3d13f3bd9c7f6f9b3b1fe8cb9"
)
EXPECTED_CACHE_PREPROCESS_SHA256 = (
    "c62df391a1e760aa3c2f353056d1f63c8a9958d93c7f1dc4c12f98cc57e5f987"
)

EXPECTED_PYTHON_VERSION = "3.9.25"
EXPECTED_LAB_VERSION = "8.0"
EXPECTED_CACHE_NAME_SUFFIX = "_61a748e5"
EXPECTED_TASK_MANIFEST = "selector_pilot_suite.txt"
EXPECTED_TASK_MANIFEST_SHA256 = (
    "3195dac7e62a34e5ac4cbeb715ab7f9b99e2ee64341082dd7d718ea2820751ca"
)
EXPECTED_TASK_SOURCES_SHA256 = (
    "dbb7730c257472c07f7946f0434949449169e06d1faa2174a92a6d13c48cb8ba"
)
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168"
)
EXPECTED_MATRIX_SHA256 = (
    "e16f6e34af5101a3549bfbf98ebaba23371c645f9166c884bfdf07b3b65e7442"
)
EXPECTED_CONTROL_SHA256 = (
    "ee40b07516ba1f2a3f562a2ec20f617e7eb1f742bf51aa67e9fb8db3d7ac9c89"
)
EXPECTED_SELECTOR_SHA256 = (
    "7d44b160de438b32c385e95d4b3b48df9433d9f1c42397b4be5341f3937edf92"
)
EXPECTED_SELECTOR_PARSER_PROTOCOL = (
    "run.log/pdb-final-and-width-selector-v1-whole-trace/v3"
)
EXPECTED_SELECTOR_POOL_PROTOCOL = "fixed_pool_v1"
EXPECTED_METRICS_VALIDATION_PROTOCOL = "wbh-exact-schema-semantic-v2"
EXPECTED_SELECTOR_SCORE_VERSION = (
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1"
)
EXPECTED_SELECTOR_SOURCES = (
    "empty",
    "bdd_prefix",
    "goal_prefix",
    "goal_fill",
    "cegar",
)
EXPECTED_SELECTOR_RECORD_KEYS = (
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

EXPECTED_TASKS = 50
EXPECTED_CONFIGS = 20
EXPECTED_CELLS = EXPECTED_TASKS * EXPECTED_CONFIGS
TIME_LIMIT_SECONDS = 300.0
PAR2_UNSOLVED_SECONDS = 600.0
MEMORY_LIMIT_MIB = 8192.0
BLIND = "blind_fw"
MS_EXACT = "ms_exact"
ARTIFACT_SCHEMA = (
    "symbolic-search-heuristics/arrhenius-selector-screen-selection/v2"
)

CONFIGS = tuple(runner.CONTROL_CONFIGS) + tuple(runner.SELECTOR_CONFIGS)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
SELECTOR_LABELS = tuple(label for label, _ in runner.SELECTOR_CONFIGS)

# Prospective held-out validation was frozen before inspecting this screen.
# The task digest hashes the normalized ``domain:problem\n`` sequence; the
# source digest hashes the corresponding canonical records in the separately
# frozen positive-cost/axiom-free source manifest.
VALIDATION_PROTOCOL = "arrhenius-selector-heldout-validation-v1"
VALIDATION_MANIFEST = "heuristic_finalists_validation_suite.txt"
VALIDATION_MANIFEST_SHA256 = (
    "fc63d4eed62816a2e065cb89f89483999a7b51067b7077969d10b2a338f19760"
)
VALIDATION_TASK_SOURCES_SHA256 = (
    "14202b66a4ed4ea7afa9f204d15cbfe8857b061a644661fc9d68b3624523fdf4"
)
VALIDATION_TASKS = 92
VALIDATION_DOMAINS = 46
VALIDATION_ANALYSIS_PROTOCOL = (
    "paired-domain-macro-coverage-sha256-bootstrap-v1"
)
VALIDATION_BOOTSTRAP_SEED = (
    "symbolic-search-heuristics/arrhenius-selector-heldout-bootstrap/v1"
)
VALIDATION_BOOTSTRAP_REPLICATES = 100000

SELECTOR_ELIGIBILITY_SHA256 = (
    "51dc9a5392f021c921d1dcc2636eb7c2d5955a363ff9df7e44ec871f9afc2aa3"
)
MS_CAP32_BUILD60_LABEL = "ms_cap32_build60"
MS_CAP32_BUILD60_SEARCH = (
    "sym_fw_ms(max_states=10000,value_cap=32,align_merge_order=false,"
    "build_time_limit=60)"
)

# These configurations are included independently of all pilot outcomes.  The
# build-budget configuration tests the implemented safe fallback and is not a
# member of the 20-way screening matrix.
FIXED_VALIDATION_CONFIGS = (
    ("blind_fw", SEARCHES["blind_fw"], "fixed-blind-control"),
    ("ms_exact", SEARCHES["ms_exact"], "fixed-ms-exact-control"),
    ("ms_cap32", SEARCHES["ms_cap32"], "fixed-ms-cap32-control"),
    (
        "pdb_goal_fill_b100k",
        SEARCHES["pdb_goal_fill_b100k"],
        "fixed-pdb-goal-fill-control",
    ),
    (
        "pdb_cegar_b100k",
        SEARCHES["pdb_cegar_b100k"],
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

# A batched selector winner gets the exact same-K, otherwise identical,
# unbatched selector as a deterministic held-out ablation.  An unbatched
# winner is already its own base and adds no duplicate validation cell.
BATCHED_SELECTOR_BASE = {
    "pdb_selector_k32_adapt_w64_r1_n1m": "pdb_selector_k32",
    "pdb_selector_k64_adapt_w64_r1_n1m": "pdb_selector_k64",
    "pdb_selector_k128_adapt_w64_r1_n1m": "pdb_selector_k128",
    "pdb_selector_kinf_adapt_w64_r1_n1m": "pdb_selector_kinf",
    "pdb_selector_k32_w16": "pdb_selector_k32",
}

SCHEMA_V2_CONVENTIONS = {
    "wbh_schema_version": 2,
    "node_count_convention": "inner_nodes_per_piece",
    "image_count_convention": "per_piece_attempted_completed",
    "expansion_count_convention": "completed_with_attempts",
}
EMPTY_LEGACY_CONVENTIONS = {
    "wbh_schema_version": 1,
    "node_count_convention": "legacy_cudd_dag_size",
    "image_count_convention": "legacy_expand_event_count",
    "expansion_count_convention": "legacy_attempts_unmarked",
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

# Current Fast Downward exit-code outcomes accepted by this prospective
# protocol.  Unexplained/critical/signal outcomes are rejected rather than
# silently charged as an ordinary timeout.
EXPLAINED_OUTCOMES = {
    0: ("success", 1, 0),
    1: ("search-plan-found-and-out-of-memory", 1, 0),
    2: ("search-plan-found-and-out-of-time", 1, 0),
    3: ("search-plan-found-and-out-of-memory-and-time", 1, 0),
    10: ("translate-unsolvable", 0, 1),
    11: ("search-unsolvable", 0, 1),
    12: ("search-unsolvable-incomplete", 0, 0),
    20: ("translate-out-of-memory", 0, 0),
    21: ("translate-out-of-time", 0, 0),
    22: ("search-out-of-memory", 0, 0),
    23: ("search-out-of-time", 0, 0),
    24: ("search-out-of-memory-and-time", 0, 0),
}
PRESEARCH_EXIT_CODES = frozenset((10, 20, 21))


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


def load_manifest(path):
    """Load only the exact corrected positive-cost selector manifest."""
    try:
        lines = path.expanduser().resolve().read_text(
            encoding="utf-8"
        ).splitlines()
    except OSError as err:
        raise AnalysisError("cannot read manifest {}: {}".format(path, err))
    labels = []
    for lineno, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(":")
        if len(fields) != 2 or not all(fields):
            raise AnalysisError(
                "{}:{} is not an exact DOMAIN:PROBLEM entry".format(
                    path, lineno
                )
            )
        labels.append(line)
    payload = "".join("{}\n".format(label) for label in labels)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if digest != EXPECTED_TASK_MANIFEST_SHA256:
        raise AnalysisError(
            "selector manifest digest changed: {} != {}".format(
                digest, EXPECTED_TASK_MANIFEST_SHA256
            )
        )
    tasks = [tuple(label.split(":", 1)) for label in labels]
    domain_counts = defaultdict(int)
    for domain, _ in tasks:
        domain_counts[domain] += 1
    if (
        len(tasks) != EXPECTED_TASKS
        or len(set(tasks)) != EXPECTED_TASKS
        or len(domain_counts) != 25
        or set(domain_counts.values()) != {2}
    ):
        raise AnalysisError(
            "selector manifest must contain 50 unique tasks, two in each of "
            "25 domains"
        )
    unsupported = sorted(set(tasks) - suite_cost_manifest.supported_tasks())
    if unsupported:
        raise AnalysisError(
            "selector manifest contains unsupported tasks: {}".format(
                ", ".join(analyzer_utils.task_label(task) for task in unsupported)
            )
        )
    return tasks


def option_records():
    return [{"label": label, "search": search} for label, search in CONFIGS]


def logical_properties_sha256(records):
    """Hash logical records without packaging-dependent properties keys."""
    normalized = []
    for record in records:
        item = {key: value for key, value in record.items() if key != "_source_key"}
        normalized.append(item)
    normalized.sort(
        key=lambda record: (
            str(record.get("algorithm", "")),
            str(record.get("domain", "")),
            str(record.get("problem", "")),
            canonical_json(record),
        )
    )
    return sha256_json(normalized)


def _validation_option_records(configs):
    return [
        {"label": config["label"], "search": config["search"]}
        for config in configs
    ]


def _fixed_validation_records():
    return [
        {"label": label, "search": search, "role": role}
        for label, search, role in FIXED_VALIDATION_CONFIGS
    ]


def heldout_validation_metadata():
    """Validate and describe the prospective 92-task held-out population."""
    path = SCRIPT_DIR / VALIDATION_MANIFEST
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as err:
        raise AnalysisError(
            "cannot read held-out manifest {}: {}".format(path, err)
        ) from err

    labels = []
    for lineno, raw_line in enumerate(raw_lines, 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split(":")
        if len(fields) != 2 or not all(fields):
            raise AnalysisError(
                "{}:{} is not an exact DOMAIN:PROBLEM entry".format(
                    path, lineno
                )
            )
        labels.append(line)

    digest = hashlib.sha256(
        "".join("{}\n".format(label) for label in labels).encode("utf-8")
    ).hexdigest()
    if digest != VALIDATION_MANIFEST_SHA256:
        raise AnalysisError(
            "held-out manifest digest changed: {} != {}".format(
                digest, VALIDATION_MANIFEST_SHA256
            )
        )
    tasks = [tuple(label.split(":", 1)) for label in labels]
    domain_counts = defaultdict(int)
    for domain, _ in tasks:
        domain_counts[domain] += 1
    if (
        len(tasks) != VALIDATION_TASKS
        or len(set(tasks)) != VALIDATION_TASKS
        or len(domain_counts) != VALIDATION_DOMAINS
        or set(domain_counts.values()) != {2}
    ):
        raise AnalysisError(
            "held-out manifest must contain 92 unique tasks, two in each of "
            "46 domains"
        )

    supported = suite_cost_manifest.supported_tasks()
    unsupported = sorted(set(tasks) - supported)
    if unsupported:
        raise AnalysisError(
            "held-out manifest contains unsupported tasks: {}".format(
                ", ".join(
                    analyzer_utils.task_label(task) for task in unsupported
                )
            )
        )
    pilot_tasks = {
        tuple(label.split(":", 1)) for label in runner.read_manifest()
    }
    overlap = sorted(set(tasks) & pilot_tasks)
    if overlap:
        raise AnalysisError(
            "held-out manifest overlaps selector pilot: {}".format(
                ", ".join(analyzer_utils.task_label(task) for task in overlap)
            )
        )

    cost_data = suite_cost_manifest.load_manifest()
    records_by_task = {
        (record["domain"], record["problem"]): record
        for record in cost_data["tasks"]
    }
    try:
        selected_records = [records_by_task[task] for task in sorted(tasks)]
    except KeyError as err:
        raise AnalysisError(
            "held-out task is absent from frozen source manifest: {}".format(
                err.args[0]
            )
        ) from err
    source_digest = hashlib.sha256(
        suite_cost_manifest.canonical_records_bytes(selected_records)
    ).hexdigest()
    if source_digest != VALIDATION_TASK_SOURCES_SHA256:
        raise AnalysisError(
            "held-out task-source digest changed: {} != {}".format(
                source_digest, VALIDATION_TASK_SOURCES_SHA256
            )
        )
    if (
        suite_cost_manifest.sha256_file(suite_cost_manifest.MANIFEST_PATH)
        != EXPECTED_SOURCE_MANIFEST_SHA256
    ):
        raise AnalysisError("frozen source-manifest bytes changed")
    return {
        "task_manifest": VALIDATION_MANIFEST,
        "task_manifest_sha256": VALIDATION_MANIFEST_SHA256,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "task_sources_sha256": VALIDATION_TASK_SOURCES_SHA256,
        "task_count": VALIDATION_TASKS,
        "domain_count": VALIDATION_DOMAINS,
    }


def _derive_artifact_winners(scores):
    ranking = scores.get("ranking") if isinstance(scores, dict) else None
    if not isinstance(ranking, list) or len(ranking) != EXPECTED_CONFIGS:
        raise AnalysisError("artifact ranking must contain exactly 20 scores")
    labels = [score.get("label") for score in ranking]
    if len(set(labels)) != EXPECTED_CONFIGS or set(labels) != set(LABELS):
        raise AnalysisError("artifact ranking labels differ from frozen matrix")
    if [score.get("rank") for score in ranking] != list(
        range(1, EXPECTED_CONFIGS + 1)
    ):
        raise AnalysisError("artifact ranking ranks/order are inconsistent")
    for score in ranking:
        label = score["label"]
        if score.get("search") != SEARCHES[label]:
            raise AnalysisError(
                "artifact ranking search changed for {}".format(label)
            )
    if any(
        ranking[index]["_key"] > ranking[index + 1]["_key"]
        for index in range(len(ranking) - 1)
    ):
        raise AnalysisError("artifact ranking is not in exact score order")

    global_winner = ranking[0]
    selected = scores.get("selected")
    if not isinstance(selected, dict) or canonical_json(
        _public_score(selected)
    ) != canonical_json(_public_score(global_winner)):
        raise AnalysisError("global winner differs from first ranked score")
    selector_winner = next(
        score for score in ranking if score["label"] in SELECTOR_LABELS
    )
    return global_winner, selector_winner


def _validation_comparisons(global_label, selector_label, matched_label):
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
        BLIND,
        "heldout-global-winner-context",
    )
    add(
        "global-winner-vs-ms-exact",
        global_label,
        MS_EXACT,
        "heldout-global-winner-context",
    )
    for reference in (BLIND, MS_EXACT, "ms_cap32"):
        add(
            "selector-vs-{}".format(reference.replace("_", "-")),
            selector_label,
            reference,
            "heldout-selector-context",
        )
    return comparisons


def _build_validation_contract(global_winner, selector_winner):
    fixed_digest = sha256_json(_fixed_validation_records())
    if fixed_digest != FIXED_VALIDATION_CONFIGS_SHA256:
        raise AnalysisError(
            "fixed validation configurations changed: {} != {}".format(
                fixed_digest, FIXED_VALIDATION_CONFIGS_SHA256
            )
        )
    eligibility_digest = sha256_json(list(SELECTOR_LABELS))
    if eligibility_digest != SELECTOR_ELIGIBILITY_SHA256:
        raise AnalysisError("selector eligibility labels changed")
    batched_labels = {
        label
        for label in SELECTOR_LABELS
        if "batch_f_window=" in SEARCHES[label]
    }
    if set(BATCHED_SELECTOR_BASE) != batched_labels:
        raise AnalysisError(
            "same-K ablation mapping does not cover exactly the batched selectors"
        )
    for batched_label, base_label in BATCHED_SELECTOR_BASE.items():
        if (
            base_label not in SELECTOR_LABELS
            or "batch_f_window=" in SEARCHES[base_label]
            or _expected_selector_budget(batched_label)
            != _expected_selector_budget(base_label)
        ):
            raise AnalysisError(
                "invalid same-K unbatched mapping {} -> {}".format(
                    batched_label, base_label
                )
            )

    configs = []

    def add_config(label, search, role):
        same_label = [config for config in configs if config["label"] == label]
        same_search = [config for config in configs if config["search"] == search]
        if same_label or same_search:
            if (
                len(same_label) != 1
                or len(same_search) != 1
                or same_label[0] is not same_search[0]
            ):
                raise AnalysisError(
                    "validation config label/search alias collision for {}".format(
                        label
                    )
                )
            if role not in same_label[0]["roles"]:
                same_label[0]["roles"].append(role)
            return
        configs.append({"label": label, "search": search, "roles": [role]})

    for label, search, role in FIXED_VALIDATION_CONFIGS:
        add_config(label, search, role)

    selector_label = selector_winner["label"]
    if selector_label not in SELECTOR_LABELS:
        raise AnalysisError("selector-family winner is not selector-eligible")
    add_config(
        selector_label,
        SEARCHES[selector_label],
        "pilot-selector-family-winner",
    )

    matched_label = BATCHED_SELECTOR_BASE.get(selector_label)
    if matched_label is not None:
        add_config(
            matched_label,
            SEARCHES[matched_label],
            "matched-same-k-unbatched-ablation",
        )

    global_label = global_winner["label"]
    matching_global = [
        config for config in configs if config["label"] == global_label
    ]
    if len(matching_global) != 1:
        raise AnalysisError(
            "pilot global winner is not represented exactly once in validation"
        )
    add_config(
        global_label,
        SEARCHES[global_label],
        "pilot-global-winner",
    )

    expected_configs = 8 if matched_label is not None else 7
    if len(configs) != expected_configs:
        raise AnalysisError(
            "validation matrix has {} configs; expected {}".format(
                len(configs), expected_configs
            )
        )
    labels = [config["label"] for config in configs]
    searches = [config["search"] for config in configs]
    if len(set(labels)) != len(configs) or len(set(searches)) != len(configs):
        raise AnalysisError("validation matrix is not label/search deduplicated")

    options = _validation_option_records(configs)
    option_digest = sha256_json(options)
    run_count = VALIDATION_TASKS * len(configs)
    if run_count not in (644, 736):
        raise AnalysisError(
            "validation run count must be 644 or 736; got {}".format(run_count)
        )
    layout = common.validate_run_layout(
        run_count, require_one_run_per_array_task=True
    )
    if layout != {
        "raw_runs": run_count,
        "array_tasks": run_count,
        "runs_per_array_task": 1,
        "scheduler_time_limit_seconds": 600,
    }:
        raise AnalysisError("validation Arrhenius array layout changed")

    comparisons = _validation_comparisons(
        global_label, selector_label, matched_label
    )
    represented = set(labels)
    if any(
        comparison["candidate"] not in represented
        or comparison["reference"] not in represented
        for comparison in comparisons
    ):
        raise AnalysisError("validation comparison refers to an absent config")
    return {
        "fixed_configs_sha256": fixed_digest,
        "roles": {
            "global_winner": global_label,
            "selector_family_winner": selector_label,
            "ms_build_budget_safeguard": MS_CAP32_BUILD60_LABEL,
            "matched_same_k_unbatched": matched_label,
        },
        "configs": configs,
        "option_matrix_sha256": option_digest,
        "comparisons": comparisons,
        "comparisons_sha256": sha256_json(comparisons),
        "config_count": len(configs),
        "expected_run_count": run_count,
        "array_layout": layout,
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate and rank the exact 20x50 Arrhenius pilot."
    )
    parser.add_argument(
        "properties",
        nargs="?",
        help=(
            "Lab properties JSON, evaluation directory, tar archive, or '-' "
            "for JSON on stdin."
        ),
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=runner.MANIFEST,
        help="Exact frozen 50-task manifest (default: %(default)s).",
    )
    parser.add_argument(
        "--emit-selection-artifact",
        action="store_true",
        help="Print only deterministic selection JSON; never write a file.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run comprehensive deterministic synthetic tests and exit.",
    )
    args = parser.parse_args(argv)
    if args.self_test and (args.properties is not None or args.emit_selection_artifact):
        parser.error("--self-test does not accept properties or artifact output")
    return args


def _reviewed_hex(value, digits, name):
    if not isinstance(value, str) or not re.fullmatch(
        "[0-9a-f]{{{}}}".format(digits), value
    ):
        raise AnalysisError(
            "{} is unset; replace its reviewed None placeholder with {} hex digits"
            .format(name, digits)
        )
    if len(set(value)) == 1:
        raise AnalysisError("{} still looks like a synthetic placeholder".format(name))
    return value


def require_reviewed_pins(protocol_revision=None, binary_sha256=None):
    planner_revision = _reviewed_hex(
        EXPECTED_PLANNER_REVISION, 40, "EXPECTED_PLANNER_REVISION"
    )
    if protocol_revision is None:
        protocol_revision = EXPECTED_PROTOCOL_REVISION
    if binary_sha256 is None:
        binary_sha256 = EXPECTED_CACHE_BINARY_SHA256
    return (
        planner_revision,
        _reviewed_hex(protocol_revision, 40, "EXPECTED_PROTOCOL_REVISION"),
        _reviewed_hex(binary_sha256, 64, "EXPECTED_CACHE_BINARY_SHA256"),
    )


def validate_runner_contract(check_cache_pin=True, expected_cache_hash=None):
    """Guard the analyzer's copied constants against runner drift."""
    failures = []
    exact = {
        "planner revision": (
            runner.PLANNER_REVISION,
            EXPECTED_PLANNER_REVISION,
        ),
        "protocol": (
            runner.PROTOCOL,
            "arrhenius-exact-width-selector-screening-v1",
        ),
        "selection rule": (
            runner.SELECTION_RULE,
            "valid-costs-max-coverage-min-micro-par2-"
            "min-certified-image-time-label/v1",
        ),
        "manifest name": (runner.MANIFEST.name, EXPECTED_TASK_MANIFEST),
        "manifest digest": (
            runner.MANIFEST_DIGEST,
            EXPECTED_TASK_MANIFEST_SHA256,
        ),
        "task-source digest": (
            runner.EXPECTED_TASK_SOURCES_SHA256,
            EXPECTED_TASK_SOURCES_SHA256,
        ),
        "preprocess binary digest": (
            runner.CACHE_PREPROCESS_SHA256,
            EXPECTED_CACHE_PREPROCESS_SHA256,
        ),
        "selector parser protocol": (
            runner.PDB_SELECTOR_PARSER_PROTOCOL,
            EXPECTED_SELECTOR_PARSER_PROTOCOL,
        ),
        "common selector parser protocol": (
            common.PDB_SELECTOR_PARSER_PROTOCOL,
            EXPECTED_SELECTOR_PARSER_PROTOCOL,
        ),
        "selector pool protocol": (
            common.PDB_SELECTOR_POOL_PROTOCOL,
            EXPECTED_SELECTOR_POOL_PROTOCOL,
        ),
        "selector score version": (
            common.PDB_SELECTOR_SCORE_VERSION,
            EXPECTED_SELECTOR_SCORE_VERSION,
        ),
        "selector source order": (
            common.PDB_SELECTOR_SOURCES,
            EXPECTED_SELECTOR_SOURCES,
        ),
        "selector record keys": (
            common.PDB_SELECTOR_RECORD_KEYS,
            EXPECTED_SELECTOR_RECORD_KEYS,
        ),
        "metrics validation protocol": (
            wbh_parser.METRICS_VALIDATION_PROTOCOL,
            EXPECTED_METRICS_VALIDATION_PROTOCOL,
        ),
        "control digest": (
            runner.CONTROL_CONFIGS_DIGEST,
            EXPECTED_CONTROL_SHA256,
        ),
        "selector digest": (
            runner.SELECTOR_CONFIGS_DIGEST,
            EXPECTED_SELECTOR_SHA256,
        ),
        "benchmark revision": (
            runner.BENCHMARK_REVISION,
            suite_cost_manifest.EXPECTED_BENCHMARK_REVISION,
        ),
        "benchmark repository": (
            runner.BENCHMARK_REPOSITORY,
            suite_cost_manifest.EXPECTED_BENCHMARK_REPOSITORY,
        ),
    }
    for name, (actual, expected) in exact.items():
        if type(actual) is not type(expected) or actual != expected:
            failures.append("{}={!r}, expected {!r}".format(name, actual, expected))
    if len(runner.CONTROL_CONFIGS) != 5 or len(runner.SELECTOR_CONFIGS) != 15:
        failures.append("runner matrix is not exactly 5 controls + 15 selectors")
    if len(CONFIGS) != EXPECTED_CONFIGS or len(set(LABELS)) != EXPECTED_CONFIGS:
        failures.append("analyzer matrix is not exactly 20 unique labels")
    if sha256_json(option_records()) != EXPECTED_MATRIX_SHA256:
        failures.append("combined 20-option matrix digest changed")
    tasks = runner.read_manifest()
    matrix = runner.validate_config_matrix(tasks)
    if matrix.get("matrix_digest") != EXPECTED_MATRIX_SHA256:
        failures.append("runner combined option-matrix digest changed")
    if matrix.get("run_count") != EXPECTED_CELLS:
        failures.append("runner does not declare exactly 1000 cells")
    if matrix.get("layout") != {
        "raw_runs": 1000,
        "array_tasks": 1000,
        "runs_per_array_task": 1,
        "scheduler_time_limit_seconds": 600,
    }:
        failures.append("runner one-run-per-array scheduler layout changed")
    if suite_cost_manifest.EXPECTED_MANIFEST_SHA256 != EXPECTED_SOURCE_MANIFEST_SHA256:
        failures.append("frozen source-manifest digest changed")
    if check_cache_pin:
        if runner.CACHE_BINARY_SHA256 != expected_cache_hash:
            failures.append(
                "runner CACHE_BINARY_SHA256={!r}, expected analyzer pin {!r}".format(
                    runner.CACHE_BINARY_SHA256, expected_cache_hash
                )
            )
    if failures:
        raise AnalysisError("runner/analyzer contract mismatch: " + "; ".join(failures))


def expected_component_options(search):
    open_paren = search.index("(")
    inner = search[open_paren + 1 : -1].strip()
    separator = "," if inner else ""
    configured = '{}({}{}wbh_log="wbh.jsonl")'.format(
        search[:open_paren], inner, separator
    )
    return ["--search", configured]


def expected_protocol_metadata(planner_revision, protocol_revision, binary_sha256):
    return {
        "planner_revision": planner_revision,
        "protocol_revision": protocol_revision,
        "planner_revision_is_protocol_ancestor": True,
        "planner_build_options": ["release_no_lp"],
        "planner_build_config": "release_no_lp",
        "planner_binary_sha256": binary_sha256,
        "planner_preprocess_sha256": EXPECTED_CACHE_PREPROCESS_SHA256,
        "planner_revision_cache_name": (
            planner_revision + EXPECTED_CACHE_NAME_SUFFIX
        ),
        "external_plan_validation": False,
        "plan_validation_protocol": (
            "no-external-val;require-plan-file-and-cross-config-cost-agreement/v1"
        ),
        "plan_file_parser_protocol": "sas_plan/exact-single-cost-footer/v1",
        "cofactor_width_property": "cofactor_width",
        "cofactor_width_parser_protocol": (
            "run.log/unique-wbh-heuristic-cofactor-width/v1"
        ),
        "metrics_validation_protocol": EXPECTED_METRICS_VALIDATION_PROTOCOL,
        "pdb_selector_parser_protocol": EXPECTED_SELECTOR_PARSER_PROTOCOL,
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
        "scheduler_account": "naiss2025-5-382-cpu",
        "scheduler_time_limit_per_task": "00:10:00",
        "scheduler_memory_per_cpu": "9G",
        "scheduler_cpus_per_task": 1,
        "scheduler_array_task_throttle": 5,
        "scheduler_max_array_tasks": 1000,
        "scheduler_array_tasks": 1000,
        "scheduler_runs_per_array_task": 1,
        "declared_run_count": EXPECTED_CELLS,
        "repetitions": 1,
        "protocol": runner.PROTOCOL,
        "selection_rule": runner.SELECTION_RULE,
        "task_manifest": EXPECTED_TASK_MANIFEST,
        "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
        "task_count": EXPECTED_TASKS,
        "domain_count": 25,
        "experiment_data_directory": "data/exp_arrhenius_selector_pilot",
        "selector_pool_protocol": EXPECTED_SELECTOR_POOL_PROTOCOL,
        "selector_score_version": EXPECTED_SELECTOR_SCORE_VERSION,
        "selector_source_order": list(EXPECTED_SELECTOR_SOURCES),
        "selector_width_budgets": [
            1, 2, 4, 8, 16, 32, 64, 128, 256, "infinity"
        ],
        "selector_state_budget": 100000,
        "selector_cegar_max_time": 10,
        "selector_cegar_seed": 2011,
        "selector_dynamic_reordering": False,
        "selector_adaptive_f_window": 64,
        "selector_adaptive_max_union_ratio": 1.0,
        "selector_adaptive_max_union_nodes": 1000000,
        "selector_static_f_window": 16,
        "control_config_count": 5,
        "selector_config_count": 15,
        "config_count": EXPECTED_CONFIGS,
        "control_configs_sha256": EXPECTED_CONTROL_SHA256,
        "selector_configs_sha256": EXPECTED_SELECTOR_SHA256,
        "option_matrix_sha256": EXPECTED_MATRIX_SHA256,
        "benchmark_revision": suite_cost_manifest.EXPECTED_BENCHMARK_REVISION,
        "benchmark_repository": suite_cost_manifest.EXPECTED_BENCHMARK_REPOSITORY,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
    }


def _same_json_scalar(actual, expected):
    return type(actual) is type(expected) and actual == expected


def _cell_label(label, task):
    return "{} {}".format(label, analyzer_utils.task_label(task))


def _append(errors, prefix, message):
    errors.append("{}: {}".format(prefix, message))


def _json_number(value):
    """Return a finite JSON number, rejecting bool and numeric strings."""
    if type(value) not in (int, float):
        return None
    try:
        return float(value) if math.isfinite(value) else None
    except (OverflowError, TypeError, ValueError):
        return None


def _validate_outcome(record, prefix, errors):
    coverage = record.get("coverage")
    if type(coverage) is not int or coverage not in (0, 1):
        _append(errors, prefix, "coverage must be integer 0 or 1")
        return

    exit_code = record.get("planner_exit_code")
    if type(exit_code) is not int or exit_code not in EXPLAINED_OUTCOMES:
        _append(
            errors,
            prefix,
            "planner_exit_code must be a predeclared explained outcome; got {!r}".
            format(exit_code),
        )
    else:
        expected_error, expected_coverage, expected_unsolvable = EXPLAINED_OUTCOMES[
            exit_code
        ]
        if coverage != expected_coverage:
            _append(
                errors,
                prefix,
                "coverage {} contradicts planner_exit_code {} ({})".format(
                    coverage, exit_code, expected_error
                ),
            )
        if record.get("error") != expected_error:
            _append(
                errors,
                prefix,
                "error={!r}, expected {!r} for planner_exit_code {}".format(
                    record.get("error"), expected_error, exit_code
                ),
            )
        if record.get("unsolvable") != expected_unsolvable:
            _append(
                errors,
                prefix,
                "unsolvable={!r}, expected {} for planner_exit_code {}".format(
                    record.get("unsolvable"), expected_unsolvable, exit_code
                ),
            )

    unexplained = record.get("unexplained_errors")
    if unexplained not in (None, []):
        _append(errors, prefix, "contains unexplained_errors={!r}".format(unexplained))

    cost = record.get("solution_cost")
    plan_present = record.get("plan_file_present")
    if type(plan_present) is not bool:
        _append(errors, prefix, "plan_file_present must be boolean")
    planner_time = _json_number(record.get("planner_time"))
    if coverage == 1:
        if type(cost) is not int or cost < 0:
            _append(errors, prefix, "solved outcome needs a nonnegative integer cost")
        if planner_time is None or planner_time < 0:
            _append(errors, prefix, "solved outcome needs finite nonnegative planner_time")
        if plan_present is not True:
            _append(errors, prefix, "solved outcome needs an emitted plan file")
        if record.get("plan_file_cost") != cost:
            _append(
                errors,
                prefix,
                "plan_file_cost={!r} disagrees with solution_cost={!r}".format(
                    record.get("plan_file_cost"), cost
                ),
            )
    else:
        if cost is not None:
            _append(errors, prefix, "unsolved outcome must not contain solution_cost")
        if "planner_time" in record and (planner_time is None or planner_time < 0):
            _append(errors, prefix, "planner_time is malformed")
        if plan_present is not False or "plan_file_cost" in record:
            _append(errors, prefix, "unsolved outcome unexpectedly has a plan file")


def _validate_metrics(record, prefix, errors):
    if record.get("metrics_validation_protocol") != EXPECTED_METRICS_VALIDATION_PROTOCOL:
        _append(
            errors,
            prefix,
            "metrics_validation_protocol={!r}, expected {!r}".format(
                record.get("metrics_validation_protocol"),
                EXPECTED_METRICS_VALIDATION_PROTOCOL,
            ),
        )
    # A driver outcome before search construction has no wbh.jsonl.  The Lab
    # parser sees empty content and emits this exact schema-less legacy marker;
    # it is a valid censored cell but can never participate in the image-time
    # criterion. No other outcome may use this exception.
    if (
        record.get("planner_exit_code") in PRESEARCH_EXIT_CODES
        and record.get("wbh_schema_version") == 1
    ):
        for field, expected in EMPTY_LEGACY_CONVENTIONS.items():
            if not _same_json_scalar(record.get(field), expected):
                _append(
                    errors,
                    prefix,
                    "{}={!r}, expected empty-log value {!r}".format(
                        field, record.get(field), expected
                    ),
                )
        if record.get("raw_metrics_complete") is not False:
            _append(errors, prefix, "empty pre-search log must have incomplete metrics")
        if record.get("piece_metrics_certified") is not False:
            _append(errors, prefix, "empty pre-search log cannot certify piece metrics")
        if record.get("metrics_validation_error") is not None:
            _append(errors, prefix, "empty pre-search log carries validation diagnostics")
        if record.get("wbh_log_nonempty") is not False:
            _append(errors, prefix, "empty pre-search log contains nonempty content")
        unexpected = [
            field
            for field in SCHEMA_V2_INTEGER_METRICS + SCHEMA_V2_REAL_METRICS
            if field in record
        ]
        if unexpected:
            _append(
                errors,
                prefix,
                "empty pre-search log unexpectedly has raw metrics {}".format(
                    ", ".join(unexpected)
                ),
            )
        return

    if record.get("wbh_log_nonempty") is not True:
        _append(errors, prefix, "schema-v2 WBH log is not marked nonempty")
    for field, expected in SCHEMA_V2_CONVENTIONS.items():
        if not _same_json_scalar(record.get(field), expected):
            _append(
                errors,
                prefix,
                "{}={!r}, expected {!r}".format(field, record.get(field), expected),
            )

    raw_complete = record.get("raw_metrics_complete")
    piece_certified = record.get("piece_metrics_certified")
    if type(raw_complete) is not bool:
        _append(errors, prefix, "raw_metrics_complete must be boolean")
    if type(piece_certified) is not bool:
        _append(errors, prefix, "piece_metrics_certified must be boolean")
    validation_error = record.get("metrics_validation_error")
    if validation_error is not None and (
        not isinstance(validation_error, str) or not validation_error
    ):
        _append(errors, prefix, "metrics_validation_error must be absent or nonempty")
    if raw_complete is True and piece_certified is not True:
        _append(errors, prefix, "complete raw metrics are not piece-certified")
    if raw_complete is True and validation_error is not None:
        _append(errors, prefix, "complete raw metrics carry a validation error")
    if piece_certified is True and validation_error is not None:
        _append(errors, prefix, "piece-certified metrics carry a validation error")
    if piece_certified is False and validation_error is None:
        _append(errors, prefix, "uncertified piece metrics lack validation diagnostics")

    for field in SCHEMA_V2_INTEGER_METRICS:
        value = record.get(field)
        if type(value) is not int or value < 0:
            _append(
                errors,
                prefix,
                "{} must be a nonnegative integer schema-v2 metric".format(field),
            )
    for field in SCHEMA_V2_REAL_METRICS:
        value = _json_number(record.get(field))
        if value is None or value < 0:
            _append(
                errors,
                prefix,
                "{} must be a finite nonnegative JSON-number schema-v2 metric".
                format(field),
            )

    # These relations are independently implied by the validated event stream
    # and protect the certification flags against malformed/tampered properties.
    relations = (
        ("attempted_bdd_nodes", "expanded_bdd_nodes"),
        ("attempted_states", "expanded_states"),
        ("attempted_bdd_pieces", "expanded_bdd_pieces"),
        ("bucket_expansion_attempts", "bucket_expansions"),
        ("attempted_bdd_pieces", "bucket_expansion_attempts"),
        ("expanded_bdd_pieces", "bucket_expansions"),
        ("image_source_buckets", "image_events"),
        ("image_source_pieces", "image_events"),
        ("image_source_pieces", "image_calls_attempted"),
        ("image_calls_attempted", "image_calls_completed"),
        ("image_events", "batched_images"),
    )
    for larger, smaller in relations:
        left = _json_number(record.get(larger))
        right = _json_number(record.get(smaller))
        if left is not None and right is not None and left < right:
            _append(errors, prefix, "{} is smaller than {}".format(larger, smaller))
    if (
        type(record.get("bucket_images")) is int
        and type(record.get("image_calls_completed")) is int
        and record["bucket_images"] != record["image_calls_completed"]
    ):
        _append(errors, prefix, "bucket_images differs from image_calls_completed")


def _expected_ms_value_cap(label):
    match = re.search(r"(?:^|,)value_cap=(-?\d+)(?:,|\))", SEARCHES[label])
    if not match:
        raise AnalysisError("cannot derive value_cap for {}".format(label))
    return int(match.group(1))


PDB_FINAL_FIELDS = (
    "pdb_final_format",
    "pdb_pattern_size",
    "pdb_selected_source",
    "pdb_abstract_states",
    "pdb_cofactor_width_budget",
    "pdb_final_num_values",
    "pdb_final_cofactor_width",
    "pdb_final_width_upper_bound",
)
SELECTOR_TRACE_FIELDS = (
    common.PDB_SELECTOR_CANDIDATES_PROPERTY,
    common.PDB_SELECTOR_SELECTED_PROPERTY,
    common.PDB_SELECTOR_FINAL_PROPERTY,
    "pdb_selector_trace_complete",
    "pdb_selector_trace_certified",
    "pdb_selector_validation_error",
    "pdb_selector_trace_sha256",
    "pdb_selector_pool_sha256",
)


def _is_selector(label):
    return label in SELECTOR_LABELS


def _expected_selector_budget(label):
    if not _is_selector(label):
        raise AnalysisError("not a selector configuration: {}".format(label))
    match = re.search(
        r"(?:^|,)cofactor_width_budget=([^,)]+)(?:,|\))", SEARCHES[label]
    )
    if not match:
        raise AnalysisError("cannot derive selector width budget for {}".format(label))
    value = match.group(1)
    return (2 ** 31 - 1) if value == "infinity" else int(value)


def _selector_record_error(record, kind, expected_budget):
    if type(record) is not dict:
        return "{} selector record must be an object".format(kind)
    if (
        len(record) != len(EXPECTED_SELECTOR_RECORD_KEYS)
        or set(record) != set(EXPECTED_SELECTOR_RECORD_KEYS)
    ):
        return "{} selector record keys changed".format(kind)
    if record.get("protocol") != EXPECTED_SELECTOR_POOL_PROTOCOL:
        return "{} selector record protocol changed".format(kind)
    if record.get("score_version") != EXPECTED_SELECTOR_SCORE_VERSION:
        return "{} selector score_version changed".format(kind)
    sources = record.get("sources")
    if (
        type(sources) is not list
        or not sources
        or any(type(source) is not str for source in sources)
        or len(sources) != len(set(sources))
        or any(source not in common.PDB_SELECTOR_SOURCES for source in sources)
    ):
        return "{} selector sources are malformed".format(kind)
    positions = [common.PDB_SELECTOR_SOURCES.index(source) for source in sources]
    if positions != sorted(positions):
        return "{} selector sources violate fixed pool order".format(kind)
    pattern = record.get("pattern")
    if (
        type(pattern) is not list
        or any(type(var) is not int or var < 0 for var in pattern)
        or pattern != sorted(set(pattern))
    ):
        return "{} selector pattern is not sorted unique nonnegative ints".format(kind)
    states = record.get("abstract_states")
    if type(states) is not int or states < 1:
        return "{} selector abstract_states must be positive".format(kind)
    if record.get("cofactor_width_budget") != expected_budget:
        return "{} selector cofactor_width_budget does not match config".format(kind)
    if type(record.get("feasible")) is not bool:
        return "{} selector feasible must be boolean".format(kind)

    stats = (
        "initial_dead_end",
        "initial_h",
        "finite_sum",
        "finite_count",
        "dead_count",
        "cofactor_width",
        "width_upper_bound",
    )
    unmaterialized = all(record.get(field) is None for field in stats)
    if unmaterialized:
        if (
            kind != "candidate"
            or states <= 100000
            or record.get("sources") != ["cegar"]
            or len(record.get("pattern", [])) != 1
            or record.get("feasible") is not False
            or record.get("rejection_reason") != "abstract_state_budget"
        ):
            return "{} selector unmaterialized outcome is inconsistent".format(kind)
        return None
    if states > 100000:
        return "{} selector oversized candidate was materialized".format(kind)
    initial_dead = record.get("initial_dead_end")
    if type(initial_dead) is not bool:
        return "{} selector initial_dead_end must be boolean".format(kind)
    initial_h = record.get("initial_h")
    if initial_dead:
        if initial_h is not None:
            return "{} selector initial dead end needs null initial_h".format(kind)
    elif type(initial_h) is not int or initial_h < 0:
        return "{} selector initial_h must be nonnegative".format(kind)
    for field in ("finite_sum", "finite_count", "dead_count"):
        if type(record.get(field)) is not int or record[field] < 0:
            return "{} selector {} must be nonnegative".format(kind, field)
    if record["finite_count"] + record["dead_count"] != states:
        return "{} selector finite/dead counts do not cover states".format(kind)
    if record["finite_count"] < 1:
        return "{} selector must retain a finite abstract goal state".format(
            kind
        )
    if not initial_dead and record["finite_sum"] < initial_h:
        return "{} selector finite_sum is smaller than initial_h".format(kind)
    if initial_dead and record["dead_count"] == 0:
        return "{} selector initial dead end has no dead states".format(kind)
    width = record.get("cofactor_width")
    upper = record.get("width_upper_bound")
    if type(width) is not int or width < 1:
        return "{} selector cofactor_width must be positive".format(kind)
    if type(upper) is not int or upper < width:
        return "{} selector width_upper_bound is invalid".format(kind)
    feasible = width <= expected_budget
    if record.get("feasible") is not feasible:
        return "{} selector feasibility contradicts exact width".format(kind)
    expected_reason = None if feasible else "cofactor_width_budget"
    if record.get("rejection_reason") != expected_reason:
        return "{} selector rejection reason contradicts exact width".format(kind)
    if kind == "selected" and not feasible:
        return "selected selector record is infeasible"
    if "empty" in sources:
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
        if any(record.get(field) != value for field, value in expected_empty.items()):
            return "{} selector empty-pattern invariants changed".format(kind)
    return None


def _selector_candidate_is_better(candidate, incumbent):
    if candidate["initial_dead_end"] != incumbent["initial_dead_end"]:
        return candidate["initial_dead_end"]
    if (
        not candidate["initial_dead_end"]
        and candidate["initial_h"] != incumbent["initial_h"]
    ):
        return candidate["initial_h"] > incumbent["initial_h"]
    candidate_mean = (
        None
        if candidate["finite_count"] == 0
        else Fraction(candidate["finite_sum"], candidate["finite_count"])
    )
    incumbent_mean = (
        None
        if incumbent["finite_count"] == 0
        else Fraction(incumbent["finite_sum"], incumbent["finite_count"])
    )
    if candidate_mean != incumbent_mean:
        if candidate_mean is None:
            return True
        if incumbent_mean is None:
            return False
        return candidate_mean > incumbent_mean
    candidate_dead = Fraction(candidate["dead_count"], candidate["abstract_states"])
    incumbent_dead = Fraction(incumbent["dead_count"], incumbent["abstract_states"])
    if candidate_dead != incumbent_dead:
        return candidate_dead > incumbent_dead
    if candidate["cofactor_width"] != incumbent["cofactor_width"]:
        return candidate["cofactor_width"] < incumbent["cofactor_width"]
    if candidate["abstract_states"] != incumbent["abstract_states"]:
        return candidate["abstract_states"] < incumbent["abstract_states"]
    return candidate["pattern"] < incumbent["pattern"]


def _normalized_selector_pool(candidates):
    ignored = {"cofactor_width_budget", "feasible", "rejection_reason"}
    return [
        {key: value for key, value in candidate.items() if key not in ignored}
        for candidate in candidates
    ]


def _validate_selector_trace(record, label, prefix, errors):
    candidates = record.get(common.PDB_SELECTOR_CANDIDATES_PROPERTY)
    selected = record.get(common.PDB_SELECTOR_SELECTED_PROPERTY)
    expected_budget = _expected_selector_budget(label)
    if type(candidates) is not list or not 1 <= len(candidates) <= 5:
        _append(errors, prefix, "selector needs 1..5 deduplicated candidates")
        return None
    if type(selected) is not dict:
        _append(errors, prefix, "selector lacks one selected record")
        return None
    records_well_formed = True
    for kind, item in [("candidate", item) for item in candidates] + [
        ("selected", selected)
    ]:
        error = _selector_record_error(item, kind, expected_budget)
        if error:
            _append(errors, prefix, error)
            records_well_formed = False
    if not records_well_formed:
        return None

    patterns = [canonical_json(item.get("pattern")) for item in candidates]
    if len(patterns) != len(set(patterns)):
        _append(errors, prefix, "selector candidate patterns are not deduplicated")
    first_source_positions = [
        common.PDB_SELECTOR_SOURCES.index(item["sources"][0])
        for item in candidates
        if type(item) is dict
        and type(item.get("sources")) is list
        and item["sources"]
        and item["sources"][0] in common.PDB_SELECTOR_SOURCES
    ]
    if first_source_positions != sorted(first_source_positions):
        _append(errors, prefix, "selector candidate order violates pool order")
    provenance = [
        source
        for item in candidates
        if type(item) is dict and type(item.get("sources")) is list
        for source in item["sources"]
    ]
    if sorted(provenance) != sorted(common.PDB_SELECTOR_SOURCES):
        _append(errors, prefix, "selector provenance does not partition five sources")

    selected_matches = [
        item for item in candidates if canonical_json(item) == canonical_json(selected)
    ]
    if len(selected_matches) != 1:
        _append(errors, prefix, "selected record is not value-equal to one candidate")
    feasible = [
        item
        for item in candidates
        if type(item) is dict
        and item.get("feasible") is True
        and item.get("cofactor_width") is not None
    ]
    if not feasible:
        _append(errors, prefix, "selector has no feasible candidate")
    else:
        winner = feasible[0]
        for item in feasible[1:]:
            if _selector_candidate_is_better(item, winner):
                winner = item
        if canonical_json(winner) != canonical_json(selected):
            _append(errors, prefix, "selected record violates exact selector score")

    expected_flags = {
        "pdb_selector_trace_complete": True,
        "pdb_selector_trace_certified": True,
        "pdb_selector_validation_error": None,
    }
    for field, expected in expected_flags.items():
        if not _same_json_scalar(record.get(field), expected):
            _append(errors, prefix, "{}={!r}, expected {!r}".format(
                field, record.get(field), expected
            ))
    for field in ("pdb_selector_trace_sha256", "pdb_selector_pool_sha256"):
        value = record.get(field)
        if type(value) is not str or not re.fullmatch(r"[0-9a-f]{64}", value):
            _append(errors, prefix, "{} must be a SHA-256".format(field))

    actual_final = record.get(common.PDB_SELECTOR_FINAL_PROPERTY)
    final_keys = {
        "pattern_size",
        "selected_source",
        "abstract_states",
        "cofactor_width_budget",
        "num_values",
        "cofactor_width",
        "width_upper_bound",
    }
    if type(actual_final) is not dict or set(actual_final) != final_keys:
        _append(errors, prefix, "pdb_selector_final keys/type changed")
    final_num_values = (
        actual_final.get("num_values") if type(actual_final) is dict else None
    )
    if type(final_num_values) is not int or final_num_values < 1:
        _append(errors, prefix, "pdb_selector_final num_values must be positive")
    expected_final = {
        "pattern_size": len(selected.get("pattern", [])),
        "selected_source": (
            selected.get("sources", [None])[0]
            if type(selected.get("sources")) is list and selected.get("sources")
            else None
        ),
        "abstract_states": selected.get("abstract_states"),
        "cofactor_width_budget": expected_budget,
        "num_values": final_num_values,
        "cofactor_width": selected.get("cofactor_width"),
        "width_upper_bound": selected.get("width_upper_bound"),
    }
    if actual_final != expected_final:
        _append(errors, prefix, "pdb_selector_final disagrees with selected record")
    expected_trace_hash = sha256_json(
        {"candidates": candidates, "selected": selected, "final": expected_final}
    )
    if record.get("pdb_selector_trace_sha256") != expected_trace_hash:
        _append(errors, prefix, "pdb_selector_trace_sha256 disagrees with trace")

    cross_checks = {
        "pdb_final_format": "exact_width_filter",
        "pdb_pattern_size": len(selected.get("pattern", [])),
        "pdb_selected_source": (
            selected.get("sources", [None])[0]
            if type(selected.get("sources")) is list and selected.get("sources")
            else None
        ),
        "pdb_abstract_states": selected.get("abstract_states"),
        "pdb_cofactor_width_budget": expected_budget,
        "pdb_final_num_values": final_num_values,
        "pdb_final_cofactor_width": selected.get("cofactor_width"),
        "pdb_final_width_upper_bound": selected.get("width_upper_bound"),
        "cofactor_width": selected.get("cofactor_width"),
    }
    for field, expected in cross_checks.items():
        if not _same_json_scalar(record.get(field), expected):
            _append(errors, prefix, "{}={!r}, expected selected value {!r}".format(
                field, record.get(field), expected
            ))
    generic_fields = ("width_upper_bound", "num_values", "num_terminals", "add_nodes")
    generic_present = [field for field in generic_fields if field in record]
    if generic_present and len(generic_present) != len(generic_fields):
        _append(
            errors,
            prefix,
            "WBH heuristic field group is only partially present: {}".format(
                ", ".join(generic_present)
            ),
        )
    has_wbh_heuristic = len(generic_present) == len(generic_fields)
    if has_wbh_heuristic:
        for field, expected in (
            ("width_upper_bound", selected.get("width_upper_bound")),
            ("num_values", final_num_values),
        ):
            if not _same_json_scalar(record.get(field), expected):
                _append(
                    errors,
                    prefix,
                    "{}={!r}, expected selected value {!r}".format(
                        field, record.get(field), expected
                    ),
                )
        num_terminals = record.get("num_terminals")
        expected_terminals = (
            final_num_values + int(selected.get("dead_count", 0) > 0)
            if type(final_num_values) is int
            else None
        )
        if expected_terminals is not None and num_terminals != expected_terminals:
            _append(
                errors,
                prefix,
                "num_terminals={!r}, expected {} from finite values/dead sentinel".
                format(num_terminals, expected_terminals),
            )
        width = selected.get("cofactor_width")
        if type(width) is int and type(num_terminals) is int and width < num_terminals:
            _append(errors, prefix, "cofactor_width is smaller than num_terminals")
    elif not (
        record.get("planner_exit_code") in (22, 23, 24)
        and "construction_completed" not in record
    ):
        _append(
            errors,
            prefix,
            "certified selector final lacks WBH heuristic fields outside a "
            "resource-interrupted pre-construction prefix",
        )

    finite_count = selected.get("finite_count")
    if type(finite_count) is int and type(final_num_values) is int:
        if final_num_values < 1:
            _append(errors, prefix, "selected PDB has no finite heuristic value")
        elif final_num_values > finite_count:
            _append(errors, prefix, "selected num_values exceeds finite_count")
    return sha256_json(_normalized_selector_pool(candidates))


def _validate_interrupted_selector_trace(record, label, prefix, errors):
    present = [field for field in SELECTOR_TRACE_FIELDS if field in record]
    if not present:
        return
    if record.get("planner_exit_code") not in (22, 23, 24):
        _append(errors, prefix, "incomplete selector trace needs exit 22/23/24")
    if record.get("pdb_selector_trace_complete") is not False:
        _append(errors, prefix, "interrupted selector trace must be incomplete")
    if record.get("pdb_selector_trace_certified") is not False:
        _append(errors, prefix, "interrupted selector trace must be uncertified")
    error = record.get("pdb_selector_validation_error")
    if type(error) is not str or not error:
        _append(errors, prefix, "interrupted selector trace needs a diagnostic")
    if (
        common.PDB_SELECTOR_FINAL_PROPERTY in record
        or any(field in record for field in PDB_FINAL_FIELDS)
    ):
        _append(errors, prefix, "uncertified selector prefix contains a final line")
    for field in ("pdb_selector_trace_sha256", "pdb_selector_pool_sha256"):
        if record.get(field) is not None:
            _append(errors, prefix, "interrupted selector trace has a nonnull hash")
    candidates = record.get(common.PDB_SELECTOR_CANDIDATES_PROPERTY, [])
    if type(candidates) is not list or not 1 <= len(candidates) <= 5:
        _append(
            errors,
            prefix,
            "explicit interrupted selector trace needs 1..5 candidates",
        )
        return
    expected_budget = _expected_selector_budget(label)
    valid_candidates = True
    for candidate in candidates:
        error = _selector_record_error(
            candidate, "candidate", expected_budget
        )
        if error:
            _append(errors, prefix, "interrupted {}".format(error))
            valid_candidates = False
    if not valid_candidates:
        return
    if candidates and "empty" not in candidates[0]["sources"]:
        _append(errors, prefix, "interrupted selector prefix does not start empty")
    patterns = [canonical_json(candidate["pattern"]) for candidate in candidates]
    if len(patterns) != len(set(patterns)):
        _append(errors, prefix, "interrupted selector patterns are not unique")
    provenance = [
        source for candidate in candidates for source in candidate["sources"]
    ]
    if len(provenance) != len(set(provenance)):
        _append(errors, prefix, "interrupted selector repeats provenance sources")
    first_positions = [
        common.PDB_SELECTOR_SOURCES.index(candidate["sources"][0])
        for candidate in candidates
    ]
    if first_positions != sorted(first_positions):
        _append(errors, prefix, "interrupted selector candidates violate pool order")
    if first_positions:
        observed_positions = {
            common.PDB_SELECTOR_SOURCES.index(source) for source in provenance
        }
        required_positions = set(range(max(observed_positions) + 1))
        missing_prefix = sorted(required_positions - observed_positions)
        if missing_prefix:
            _append(
                errors,
                prefix,
                "interrupted selector prefix skips earlier sources {}".format(
                    ", ".join(
                        common.PDB_SELECTOR_SOURCES[pos]
                        for pos in missing_prefix
                    )
                ),
            )
    selected = record.get(common.PDB_SELECTOR_SELECTED_PROPERTY)
    if selected is not None:
        selected_error = _selector_record_error(
            selected, "selected", expected_budget
        )
        if selected_error:
            _append(errors, prefix, "interrupted {}".format(selected_error))
            return
        if sorted(provenance) != sorted(common.PDB_SELECTOR_SOURCES):
            _append(
                errors,
                prefix,
                "interrupted selector with selected record lacks full provenance",
            )
        matches = [candidate for candidate in candidates if candidate == selected]
        if len(matches) != 1:
            _append(
                errors,
                prefix,
                "interrupted selected record does not equal one candidate",
            )
        feasible = [candidate for candidate in candidates if candidate["feasible"]]
        if feasible:
            winner = feasible[0]
            for candidate in feasible[1:]:
                if _selector_candidate_is_better(candidate, winner):
                    winner = candidate
            if winner != selected:
                _append(
                    errors,
                    prefix,
                    "interrupted selected record violates exact selector score",
                )
        else:
            _append(errors, prefix, "interrupted selector has no feasible candidate")


def _validate_nonselector_pdb_trace(record, label, prefix, errors):
    unexpected_selector = [field for field in SELECTOR_TRACE_FIELDS if field in record]
    if unexpected_selector:
        _append(errors, prefix, "non-selector contains selector fields {}".format(
            ", ".join(unexpected_selector)
        ))
    has_final = any(field in record for field in PDB_FINAL_FIELDS)
    if label.startswith("pdb_") and has_final:
        expected = {
            "pdb_final_format": "legacy",
            "pdb_final_num_values": record.get("num_values"),
            "pdb_final_cofactor_width": record.get("cofactor_width"),
            "pdb_final_width_upper_bound": record.get("width_upper_bound"),
        }
        for field, value in expected.items():
            if not _same_json_scalar(record.get(field), value):
                _append(errors, prefix, "{}={!r}, expected {!r}".format(
                    field, record.get(field), value
                ))
        pattern_size = record.get("pdb_pattern_size")
        if type(pattern_size) is not int or pattern_size < 0:
            _append(errors, prefix, "legacy PDB pattern size must be nonnegative")
        exact_only = (
            "pdb_selected_source",
            "pdb_abstract_states",
            "pdb_cofactor_width_budget",
        )
        if any(field in record for field in exact_only):
            _append(errors, prefix, "legacy PDB final contains selector-only fields")
    elif label.startswith("pdb_") and record.get("construction_completed") is True:
        _append(errors, prefix, "completed legacy PDB construction lacks final line")
    elif has_final:
        _append(errors, prefix, "non-PDB run contains PDB final fields")


def _validate_heuristic(record, label, prefix, errors):
    construction_fields = (
        "construction_completed",
        "construction_time",
        "heuristic_kind",
        "heuristic_size_bound",
        "value_cap",
    )
    heuristic_fields = (
        "cofactor_width",
        "width_upper_bound",
        "num_values",
        "num_terminals",
        "add_nodes",
    )
    if label == BLIND:
        unexpected = [
            field for field in construction_fields + heuristic_fields if field in record
        ]
        if unexpected:
            _append(
                errors,
                prefix,
                "blind run unexpectedly has heuristic fields {}".format(
                    ", ".join(unexpected)
                ),
            )
        return

    completed_present = "construction_completed" in record
    completed = record.get("construction_completed")
    if completed_present and type(completed) is not bool:
        _append(errors, prefix, "construction_completed must be boolean when present")
        return
    if not completed_present:
        stray_construction = [
            field for field in construction_fields[1:] if field in record
        ]
        if stray_construction:
            _append(
                errors,
                prefix,
                "construction outcome is absent but fields {} are present".format(
                    ", ".join(stray_construction)
                ),
            )
    if record.get("coverage") == 1 and not completed_present:
        _append(errors, prefix, "solved heuristic run lacks construction outcome")

    if completed_present:
        construction_time = _json_number(record.get("construction_time"))
        if construction_time is None or construction_time < 0:
            _append(errors, prefix, "construction_time must be finite and nonnegative")
        size_bound = record.get("heuristic_size_bound")
        value_cap = record.get("value_cap")
        kind = record.get("heuristic_kind")
        if label.startswith("ms_"):
            if kind != "merge_and_shrink":
                _append(errors, prefix, "unexpected M&S heuristic_kind={!r}".format(kind))
            if type(size_bound) is not int or size_bound != 10000:
                _append(errors, prefix, "M&S heuristic_size_bound must equal 10000")
            expected_cap = _expected_ms_value_cap(label)
            if type(value_cap) is not int or value_cap != expected_cap:
                _append(
                    errors,
                    prefix,
                    "M&S value_cap={!r}, expected {}".format(value_cap, expected_cap),
                )
        elif label.startswith("pdb_"):
            expected_kind = (
                "pdb_exact_width_filter" if _is_selector(label) else None
            )
            if expected_kind is not None and kind != expected_kind:
                _append(
                    errors,
                    prefix,
                    "selector heuristic_kind={!r}, expected {!r}".format(
                        kind, expected_kind
                    ),
                )
            elif expected_kind is None and (
                not isinstance(kind, str) or not kind.startswith("pdb_")
            ):
                _append(errors, prefix, "unexpected PDB heuristic_kind={!r}".format(kind))
            if type(size_bound) is not int or size_bound != 100000:
                _append(errors, prefix, "PDB heuristic_size_bound must equal 100000")
            if type(value_cap) is not int or value_cap != -1:
                _append(errors, prefix, "PDB value_cap must equal -1")

    if completed is False:
        _append(errors, prefix, "construction fallback is not enabled in this matrix")
        if any(field in record for field in heuristic_fields):
            _append(errors, prefix, "construction fallback unexpectedly logged a heuristic")
        return

    selector_before_wbh_event = (
        _is_selector(label)
        and record.get("planner_exit_code") in (22, 23, 24)
        and record.get("pdb_selector_trace_certified") is True
        and not completed_present
        and "cofactor_width" in record
        and all(
            field not in record
            for field in ("width_upper_bound", "num_values", "num_terminals", "add_nodes")
        )
    )
    if selector_before_wbh_event:
        width = record.get("cofactor_width")
        if type(width) is not int or width < 1:
            _append(
                errors,
                prefix,
                "resource-interrupted selector cofactor_width must be positive",
            )
        return

    width_present = "cofactor_width" in record
    stray_heuristic = [field for field in heuristic_fields[1:] if field in record]
    if not width_present and stray_heuristic:
        _append(
            errors,
            prefix,
            "cofactor_width is absent but heuristic fields {} are present".format(
                ", ".join(stray_heuristic)
            ),
        )
    if completed is True and not width_present:
        _append(errors, prefix, "completed construction lacks exact cofactor_width")
    if not width_present:
        return

    width = record.get("cofactor_width")
    upper = record.get("width_upper_bound")
    if type(width) is not int or width < 0:
        _append(errors, prefix, "cofactor_width must be a nonnegative integer")
    if type(upper) is not int or upper < 0:
        _append(errors, prefix, "width_upper_bound must be a nonnegative integer")
    elif type(width) is int and width > upper:
        _append(errors, prefix, "cofactor_width exceeds width_upper_bound")
    num_values = record.get("num_values")
    if (
        type(num_values) is not int
        or num_values <= 0
    ):
        _append(
            errors,
            prefix,
            "num_values must be a positive integer",
        )
    num_terminals = record.get("num_terminals")
    if type(num_terminals) is not int or num_terminals <= 0:
        _append(errors, prefix, "num_terminals must be a positive integer")
    add_nodes = record.get("add_nodes")
    if type(add_nodes) is not int or add_nodes < 0:
        _append(errors, prefix, "add_nodes must be a nonnegative integer")
    if (
        type(upper) is int
        and type(add_nodes) is int
        and type(record.get("num_terminals")) is int
        and upper != add_nodes + record["num_terminals"]
    ):
        _append(errors, prefix, "width_upper_bound != add_nodes + num_terminals")
    if (
        type(record.get("num_values")) is int
        and type(record.get("num_terminals")) is int
        and record["num_values"] > record["num_terminals"]
    ):
        _append(errors, prefix, "num_values exceeds num_terminals")


def validate_records(
    records, tasks, planner_revision, protocol_revision, binary_sha256
):
    matrix, structural_errors, structural_warnings = analyzer_utils.build_matrix(
        records, tasks, LABELS, allow_incomplete=False
    )
    # This input is the pilot itself, not a pooled properties database.
    errors = list(structural_errors) + list(structural_warnings)
    if len(records) != EXPECTED_CELLS:
        errors.append(
            "properties contain {} records; expected exactly {}".format(
                len(records), EXPECTED_CELLS
            )
        )
    if len(matrix) != EXPECTED_CELLS:
        errors.append(
            "matrix contains {} cells; expected exactly {}".format(
                len(matrix), EXPECTED_CELLS
            )
        )

    static_expected = expected_protocol_metadata(
        planner_revision, protocol_revision, binary_sha256
    )
    costs_by_task = defaultdict(list)
    proved_unsolvable_by_task = defaultdict(list)
    selector_pools_by_task = defaultdict(dict)
    benchmark_worktrees = set()
    for label in LABELS:
        for task in tasks:
            record = matrix.get((label, task))
            if record is None:
                continue
            prefix = _cell_label(label, task)
            if record.get("algorithm") != label:
                _append(errors, prefix, "algorithm identity field changed")
            if record.get("domain") != task[0] or record.get("problem") != task[1]:
                _append(errors, prefix, "domain/problem identity fields changed")
            run_id = record.get("id")
            if run_id is not None and run_id != [label, task[0], task[1]]:
                _append(errors, prefix, "id={!r} is not the exact cell identity".format(run_id))

            expected_options = expected_component_options(SEARCHES[label])
            if record.get("component_options") != expected_options:
                _append(
                    errors,
                    prefix,
                    "component_options={!r}, expected {!r}".format(
                        record.get("component_options"), expected_options
                    ),
                )
            expected_driver = [
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
            if record.get("driver_options") != expected_driver:
                _append(
                    errors,
                    prefix,
                    "driver_options={!r}, expected {!r}".format(
                        record.get("driver_options"), expected_driver
                    ),
                )
            for field in ("global_revision", "local_revision"):
                if record.get(field) != planner_revision:
                    _append(
                        errors,
                        prefix,
                        "{}={!r}, expected {!r}".format(
                            field, record.get(field), planner_revision
                        ),
                    )
            for field, expected in (
                ("planner_time_limit", TIME_LIMIT_SECONDS),
                ("planner_memory_limit", MEMORY_LIMIT_MIB),
            ):
                actual = _json_number(record.get(field))
                if actual is None or not analyzer_utils.equal_values(actual, expected):
                    _append(
                        errors,
                        prefix,
                        "{}={!r}, expected {}".format(field, record.get(field), expected),
                    )
            for field, expected in static_expected.items():
                actual = record.get(field)
                if not _same_json_scalar(actual, expected):
                    _append(
                        errors,
                        prefix,
                        "{}={!r}, expected {!r}".format(field, actual, expected),
                    )

            worktree = record.get("benchmark_worktree")
            if not isinstance(worktree, str) or not worktree or not Path(worktree).is_absolute():
                _append(errors, prefix, "benchmark_worktree must be a nonempty absolute path")
            else:
                benchmark_worktrees.add(worktree)

            _validate_outcome(record, prefix, errors)
            _validate_metrics(record, prefix, errors)
            _validate_heuristic(record, label, prefix, errors)
            if _is_selector(label):
                if (
                    record.get("construction_completed") is True
                    or record.get("pdb_selector_trace_certified") is True
                ):
                    pool_hash = _validate_selector_trace(
                        record, label, prefix, errors
                    )
                    if pool_hash is not None:
                        selector_pools_by_task[task][label] = pool_hash
                        if record.get("pdb_selector_pool_sha256") != pool_hash:
                            _append(
                                errors,
                                prefix,
                                "pdb_selector_pool_sha256 disagrees with candidates",
                            )
                    selected = record.get(common.PDB_SELECTOR_SELECTED_PROPERTY)
                    if (
                        type(selected) is dict
                        and selected.get("initial_dead_end") is True
                        and record.get("planner_exit_code") not in (11, 22, 23, 24)
                    ):
                        _append(
                            errors,
                            prefix,
                            "initial-dead selector winner has incompatible planner outcome",
                        )
                else:
                    _validate_interrupted_selector_trace(
                        record, label, prefix, errors
                    )
                if (
                    record.get("planner_exit_code") in (11, 12)
                    and record.get("construction_completed") is not True
                ):
                    _append(
                        errors,
                        prefix,
                        "selector unsolvability outcome lacks completed construction",
                    )
            else:
                _validate_nonselector_pdb_trace(record, label, prefix, errors)
            if record.get("coverage") == 1 and type(record.get("solution_cost")) is int:
                costs_by_task[task].append((label, record["solution_cost"]))
            if record.get("coverage") == 0 and record.get("unsolvable") == 1:
                proved_unsolvable_by_task[task].append(label)

    if len(benchmark_worktrees) != 1:
        errors.append(
            "records do not contain one consistent absolute benchmark_worktree"
        )
    for task, entries in sorted(costs_by_task.items()):
        distinct = sorted({cost for _, cost in entries})
        if len(distinct) > 1:
            errors.append(
                "solved-cost disagreement on {}: {}".format(
                    analyzer_utils.task_label(task),
                    ", ".join("{}={}".format(label, cost) for label, cost in entries),
                )
            )
        if proved_unsolvable_by_task.get(task):
            errors.append(
                "solved/proved-unsolvable disagreement on {}: solved by {}; "
                "reported unsolvable by {}".format(
                    analyzer_utils.task_label(task),
                    ", ".join(label for label, _ in entries),
                    ", ".join(proved_unsolvable_by_task[task]),
                )
            )
    for task, labelled_hashes in sorted(selector_pools_by_task.items()):
        distinct = sorted(set(labelled_hashes.values()))
        if len(distinct) > 1:
            errors.append(
                "selector pool fingerprint disagreement on {}: {}".format(
                    analyzer_utils.task_label(task),
                    ", ".join(
                        "{}={}".format(label, value)
                        for label, value in sorted(labelled_hashes.items())
                    ),
                )
            )
    return matrix, errors


def raise_validation_errors(errors):
    if not errors:
        return
    shown = errors[:50]
    suffix = ""
    if len(errors) > len(shown):
        suffix = "\n... {} additional validation errors".format(
            len(errors) - len(shown)
        )
    raise AnalysisError(
        "pilot validation failed ({} errors):\n{}{}".format(
            len(errors), "\n".join("- " + error for error in shown), suffix
        )
    )


def certified_image_cell(record):
    return (
        record.get("raw_metrics_complete") is True
        and record.get("piece_metrics_certified") is True
        and record.get("metrics_validation_error") is None
        and all(
            _same_json_scalar(record.get(field), expected)
            for field, expected in SCHEMA_V2_CONVENTIONS.items()
        )
        and all(
            type(record.get(field)) is int and record[field] >= 0
            for field in SCHEMA_V2_INTEGER_METRICS
        )
        and all(
            _json_number(record.get(field)) is not None
            and _json_number(record.get(field)) >= 0
            for field in SCHEMA_V2_REAL_METRICS
        )
    )


def width_summary(records):
    widths = [record["cofactor_width"] for record in records if "cofactor_width" in record]
    if not widths:
        return {"observed": 0, "minimum": None, "median": None, "maximum": None}
    return {
        "observed": len(widths),
        "minimum": min(widths),
        "median": statistics.median(widths),
        "maximum": max(widths),
    }


def construction_summary(records):
    kinds = [
        record.get("heuristic_kind")
        for record in records
        if isinstance(record.get("heuristic_kind"), str)
    ]
    return {
        "completed": sum(record.get("construction_completed") is True for record in records),
        "fallbacks": sum(record.get("construction_completed") is False for record in records),
        "unobserved": sum("construction_completed" not in record for record in records),
        "pattern_fallbacks": sum("fallback" in kind for kind in kinds),
    }


def selector_summary(records):
    selected = [
        record[common.PDB_SELECTOR_SELECTED_PROPERTY]
        for record in records
        if type(record.get(common.PDB_SELECTOR_SELECTED_PROPERTY)) is dict
    ]
    return {
        "certified": sum(
            record.get("pdb_selector_trace_certified") is True
            for record in records
        ),
        "interrupted": sum(
            record.get("pdb_selector_trace_complete") is False
            for record in records
        ),
        "selected_sources": {
            source: sum(
                item.get("sources", [None])[0] == source for item in selected
            )
            for source in common.PDB_SELECTOR_SOURCES
        },
    }


def analyze_scores(matrix, tasks):
    records_by_label = {
        label: [matrix[(label, task)] for task in tasks] for label in LABELS
    }
    all_cells_certified = all(
        certified_image_cell(record)
        for records in records_by_label.values()
        for record in records
    )
    scores = []
    for label in LABELS:
        records = records_by_label[label]
        solved = sum(record["coverage"] == 1 for record in records)
        penalties = [
            float(record["planner_time"])
            if record["coverage"] == 1
            else PAR2_UNSOLVED_SECONDS
            for record in records
        ]
        config_certified = all(certified_image_cell(record) for record in records)
        total_image_time = (
            math.fsum(float(record["image_time"]) for record in records)
            if config_certified
            else None
        )
        score = {
            "label": label,
            "search": SEARCHES[label],
            "coverage": solved,
            "micro_par2": math.fsum(penalties) / len(tasks),
            "total_image_time": total_image_time,
            "image_metrics_complete": config_certified,
            "construction": construction_summary(records),
            "cofactor_width": width_summary(records),
            "selector": selector_summary(records),
        }
        key = (-solved, score["micro_par2"])
        if all_cells_certified:
            key += (total_image_time,)
        key += (label,)
        score["_key"] = key
        scores.append(score)
    scores.sort(key=lambda item: item["_key"])
    for rank, score in enumerate(scores, 1):
        score["rank"] = rank
    return {
        "image_time_tiebreak_available": all_cells_certified,
        "ranking": scores,
        "selected": scores[0],
    }


def paired_delta(matrix, tasks, label, reference, image_time_tiebreak_available):
    candidate_penalties = []
    reference_penalties = []
    wins = 0
    losses = 0
    both_solved = 0
    both_unsolved = 0
    for task in tasks:
        candidate = matrix[(label, task)]
        baseline = matrix[(reference, task)]
        candidate_solved = candidate["coverage"] == 1
        baseline_solved = baseline["coverage"] == 1
        candidate_penalties.append(
            float(candidate["planner_time"])
            if candidate_solved
            else PAR2_UNSOLVED_SECONDS
        )
        reference_penalties.append(
            float(baseline["planner_time"])
            if baseline_solved
            else PAR2_UNSOLVED_SECONDS
        )
        if candidate_solved and not baseline_solved:
            wins += 1
        elif baseline_solved and not candidate_solved:
            losses += 1
        elif candidate_solved:
            both_solved += 1
        else:
            both_unsolved += 1
    image_delta = None
    if image_time_tiebreak_available:
        image_delta = math.fsum(
            float(matrix[(label, task)]["image_time"])
            - float(matrix[(reference, task)]["image_time"])
            for task in tasks
        )
    return {
        "label": label,
        "reference": reference,
        "coverage_delta": wins - losses,
        "micro_par2_delta": (
            math.fsum(
                candidate - baseline
                for candidate, baseline in zip(candidate_penalties, reference_penalties)
            )
            / len(tasks)
        ),
        "wins": wins,
        "losses": losses,
        "both_solved": both_solved,
        "both_unsolved": both_unsolved,
        "total_image_time_delta": image_delta,
    }


def all_paired_deltas(matrix, tasks, image_time_tiebreak_available):
    return [
        paired_delta(matrix, tasks, label, reference, image_time_tiebreak_available)
        for label in LABELS
        for reference in (BLIND, MS_EXACT)
    ]


def _public_score(score):
    return {key: value for key, value in score.items() if key != "_key"}


def make_selection_artifact(
    records,
    scores,
    paired,
    planner_revision,
    protocol_revision,
    binary_sha256,
):
    global_winner, selector_winner = _derive_artifact_winners(scores)
    validation = heldout_validation_metadata()
    validation.update(
        _build_validation_contract(global_winner, selector_winner)
    )
    validation.update(
        {
            "protocol": VALIDATION_PROTOCOL,
            "requires_disjoint_tasks": True,
            "selection_artifact_schema": ARTIFACT_SCHEMA,
            "selection_rule": runner.SELECTION_RULE,
            "selector_eligibility_labels": list(SELECTOR_LABELS),
            "selector_eligibility_sha256": SELECTOR_ELIGIBILITY_SHA256,
            "selector_configs_sha256": EXPECTED_SELECTOR_SHA256,
            "time_limit_seconds": int(TIME_LIMIT_SECONDS),
            "memory_limit_mib": int(MEMORY_LIMIT_MIB),
            "par2_unsolved_seconds": int(PAR2_UNSOLVED_SECONDS),
            "analysis": {
                "protocol": VALIDATION_ANALYSIS_PROTOCOL,
                "primary_comparison": "selector-vs-pdb-cegar",
                "primary_estimand": (
                    "selector-minus-cegar-equally-weighted-domain-macro-"
                    "coverage/v1"
                ),
                "resampling_unit": "domain",
                "bootstrap_method": "sha256-counter-domain-resampling/v1",
                "bootstrap_seed": VALIDATION_BOOTSTRAP_SEED,
                "bootstrap_replicates": VALIDATION_BOOTSTRAP_REPLICATES,
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
    )
    return {
        "schema": ARTIFACT_SCHEMA,
        "pilot": {
            "protocol": runner.PROTOCOL,
            "selection_rule": runner.SELECTION_RULE,
            "planner_revision": planner_revision,
            "protocol_revision": protocol_revision,
            "planner_revision_is_protocol_ancestor": True,
            "planner_binary_sha256": binary_sha256,
            "planner_preprocess_sha256": EXPECTED_CACHE_PREPROCESS_SHA256,
            "planner_build_config": "release_no_lp",
            "benchmark_revision": suite_cost_manifest.EXPECTED_BENCHMARK_REVISION,
            "benchmark_repository": suite_cost_manifest.EXPECTED_BENCHMARK_REPOSITORY,
            "task_manifest": EXPECTED_TASK_MANIFEST,
            "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
            "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
            "option_matrix_sha256": EXPECTED_MATRIX_SHA256,
            "control_configs_sha256": EXPECTED_CONTROL_SHA256,
            "selector_configs_sha256": EXPECTED_SELECTOR_SHA256,
            "pdb_selector_parser_protocol": EXPECTED_SELECTOR_PARSER_PROTOCOL,
            "metrics_validation_protocol": EXPECTED_METRICS_VALIDATION_PROTOCOL,
            "selector_pool_protocol": EXPECTED_SELECTOR_POOL_PROTOCOL,
            "selector_score_version": EXPECTED_SELECTOR_SCORE_VERSION,
            "selector_source_order": list(EXPECTED_SELECTOR_SOURCES),
            "options": option_records(),
            "task_count": EXPECTED_TASKS,
            "config_count": EXPECTED_CONFIGS,
            "expected_run_count": EXPECTED_CELLS,
            "time_limit_seconds": int(TIME_LIMIT_SECONDS),
            "memory_limit_mib": int(MEMORY_LIMIT_MIB),
            "par2_unsolved_seconds": int(PAR2_UNSOLVED_SECONDS),
            "properties_canonical_sha256": logical_properties_sha256(records),
        },
        "selection": {
            "image_time_tiebreak_used": scores["image_time_tiebreak_available"],
            "global_winner": _public_score(global_winner),
            "selector_family_winner": _public_score(selector_winner),
            "selector_eligibility_labels": list(SELECTOR_LABELS),
            "selector_eligibility_sha256": SELECTOR_ELIGIBILITY_SHA256,
            "ranking": [_public_score(score) for score in scores["ranking"]],
        },
        "paired_deltas": paired,
        "validation": validation,
    }


def _fmt(value, digits=6):
    if value is None:
        return "NA"
    if type(value) is int:
        return str(value)
    return ("{:." + str(digits) + "g}").format(value)


def print_report(source, records, scores, paired):
    print("Arrhenius 20x50 exact-selector screen: {}".format(source))
    print("canonical properties SHA-256: {}".format(logical_properties_sha256(records)))
    print("selection rule: {}".format(runner.SELECTION_RULE))
    if scores["image_time_tiebreak_available"]:
        print("image-time tie-break: available (all 1000 cells schema-v2 certified)")
    else:
        print(
            "image-time tie-break: omitted (at least one cell lacks complete "
            "schema-v2 certified metrics)"
        )

    ranking_rows = []
    for score in scores["ranking"]:
        construction = score["construction"]
        width = score["cofactor_width"]
        ranking_rows.append(
            (
                score["rank"],
                score["label"],
                "{}/{}".format(score["coverage"], EXPECTED_TASKS),
                _fmt(score["micro_par2"]),
                _fmt(score["total_image_time"]),
                construction["fallbacks"],
                construction["pattern_fallbacks"],
                construction["unobserved"],
                width["observed"],
                _fmt(width["median"]),
                _fmt(width["maximum"]),
            )
        )
    print("\nPer-configuration ranking and construction/width summary")
    analyzer_utils.print_table(
        (
            "rank",
            "config",
            "coverage",
            "micro-PAR2",
            "image_time",
            "construct_fb",
            "pattern_fb",
            "construct_NA",
            "width_n",
            "width_med",
            "width_max",
        ),
        ranking_rows,
    )

    print("\nExact cofactor-width summaries")
    width_rows = []
    by_label = {score["label"]: score for score in scores["ranking"]}
    for label in LABELS:
        width = by_label[label]["cofactor_width"]
        width_rows.append(
            (
                label,
                width["observed"],
                _fmt(width["minimum"]),
                _fmt(width["median"]),
                _fmt(width["maximum"]),
            )
        )
    analyzer_utils.print_table(
        ("config", "observed", "minimum", "median", "maximum"), width_rows
    )

    print("\nExact-selector trace/source summaries")
    selector_rows = []
    for label in SELECTOR_LABELS:
        selector = by_label[label]["selector"]
        selector_rows.append(
            (
                label,
                selector["certified"],
                selector["interrupted"],
                canonical_json(selector["selected_sources"]),
            )
        )
    analyzer_utils.print_table(
        ("config", "certified", "interrupted", "selected-source-counts"),
        selector_rows,
    )

    print("\nPaired deltas (candidate minus reference; negative PAR2 is better)")
    paired_rows = [
        (
            item["label"],
            item["reference"],
            item["coverage_delta"],
            _fmt(item["micro_par2_delta"]),
            item["wins"],
            item["losses"],
            item["both_solved"],
            _fmt(item["total_image_time_delta"]),
        )
        for item in paired
    ]
    analyzer_utils.print_table(
        (
            "config",
            "reference",
            "d-coverage",
            "d-PAR2",
            "wins",
            "losses",
            "both-solved",
            "d-image-time",
        ),
        paired_rows,
    )
    print(
        "\nPASS: exact 1000-cell matrix, options, tasks, provenance, revision/cache, "
        "limits, scheduler fields, explained outcomes, and solved costs validated."
    )
    print("selected: {}".format(scores["selected"]["label"]))


def _synthetic_selector_candidate(
    sources,
    pattern,
    abstract_states,
    budget,
    initial_h=None,
    width=None,
    upper=None,
):
    materialized = width is not None
    feasible = materialized and width <= budget
    return {
        "protocol": common.PDB_SELECTOR_POOL_PROTOCOL,
        "score_version": common.PDB_SELECTOR_SCORE_VERSION,
        "sources": list(sources),
        "pattern": list(pattern),
        "abstract_states": abstract_states,
        "initial_dead_end": False if materialized else None,
        "initial_h": initial_h if materialized else None,
        "finite_sum": (initial_h * abstract_states) if materialized else None,
        "finite_count": abstract_states if materialized else None,
        "dead_count": 0 if materialized else None,
        "cofactor_width": width,
        "width_upper_bound": upper,
        "cofactor_width_budget": budget,
        "feasible": feasible,
        "rejection_reason": (
            None
            if feasible
            else (
                "cofactor_width_budget"
                if materialized
                else "abstract_state_budget"
            )
        ),
    }


def _refresh_selector_hashes(record):
    candidates = record[common.PDB_SELECTOR_CANDIDATES_PROPERTY]
    selected = record[common.PDB_SELECTOR_SELECTED_PROPERTY]
    final = record[common.PDB_SELECTOR_FINAL_PROPERTY]
    record["pdb_selector_pool_sha256"] = sha256_json(
        _normalized_selector_pool(candidates)
    )
    record["pdb_selector_trace_sha256"] = sha256_json(
        {"candidates": candidates, "selected": selected, "final": final}
    )


def _attach_selector_trace(record, label):
    budget = _expected_selector_budget(label)
    candidates = [
        _synthetic_selector_candidate(
            ["empty"], [], 1, budget, initial_h=0, width=1, upper=1
        ),
        _synthetic_selector_candidate(
            ["bdd_prefix", "goal_prefix", "goal_fill"],
            [0],
            2,
            budget,
            initial_h=5,
            width=4,
            upper=7,
        ),
        _synthetic_selector_candidate(
            ["cegar"], [1], 100001, budget
        ),
    ]
    feasible = [candidate for candidate in candidates if candidate["feasible"]]
    winner = feasible[0]
    for candidate in feasible[1:]:
        if _selector_candidate_is_better(candidate, winner):
            winner = candidate
    selected = copy.deepcopy(winner)
    num_values = 1 if selected["pattern"] == [] else 2
    num_terminals = num_values + int(selected["dead_count"] > 0)
    add_nodes = selected["width_upper_bound"] - num_terminals
    final = {
        "pattern_size": len(selected["pattern"]),
        "selected_source": selected["sources"][0],
        "abstract_states": selected["abstract_states"],
        "cofactor_width_budget": budget,
        "num_values": num_values,
        "cofactor_width": selected["cofactor_width"],
        "width_upper_bound": selected["width_upper_bound"],
    }
    record.update(
        {
            "heuristic_kind": "pdb_exact_width_filter",
            "heuristic_size_bound": 100000,
            "value_cap": -1,
            "cofactor_width": selected["cofactor_width"],
            "width_upper_bound": selected["width_upper_bound"],
            "num_values": num_values,
            "num_terminals": num_terminals,
            "add_nodes": add_nodes,
            "pdb_final_format": "exact_width_filter",
            "pdb_pattern_size": final["pattern_size"],
            "pdb_selected_source": final["selected_source"],
            "pdb_abstract_states": final["abstract_states"],
            "pdb_cofactor_width_budget": final["cofactor_width_budget"],
            "pdb_final_num_values": final["num_values"],
            "pdb_final_cofactor_width": final["cofactor_width"],
            "pdb_final_width_upper_bound": final["width_upper_bound"],
            common.PDB_SELECTOR_CANDIDATES_PROPERTY: candidates,
            common.PDB_SELECTOR_SELECTED_PROPERTY: selected,
            common.PDB_SELECTOR_FINAL_PROPERTY: final,
            "pdb_selector_trace_complete": True,
            "pdb_selector_trace_certified": True,
            "pdb_selector_validation_error": None,
        }
    )
    _refresh_selector_hashes(record)


def synthetic_record(
    label,
    search,
    task,
    planner_revision,
    protocol_revision,
    binary_sha256,
    planner_time,
    cost,
):
    domain, problem = task
    solved = planner_time is not None
    record = {
        "_source_key": "{}-{}-{}".format(label, domain, problem),
        "id": [label, domain, problem],
        "algorithm": label,
        "domain": domain,
        "problem": problem,
        "coverage": 1 if solved else 0,
        "planner_exit_code": 0 if solved else 23,
        "error": "success" if solved else "search-out-of-time",
        "unsolvable": 0,
        "plan_file_present": solved,
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
        "global_revision": planner_revision,
        "local_revision": planner_revision,
        "planner_time_limit": TIME_LIMIT_SECONDS,
        "planner_memory_limit": MEMORY_LIMIT_MIB,
        "benchmark_worktree": "/synthetic/downward-benchmarks",
        "metrics_validation_protocol": EXPECTED_METRICS_VALIDATION_PROTOCOL,
        "wbh_log_nonempty": True,
        "raw_metrics_complete": True,
        "piece_metrics_certified": True,
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
    }
    record.update(
        expected_protocol_metadata(
            planner_revision, protocol_revision, binary_sha256
        )
    )
    record.update(SCHEMA_V2_CONVENTIONS)
    if solved:
        record["solution_cost"] = cost
        record["plan_file_cost"] = cost
        record["planner_time"] = planner_time
    if label == BLIND:
        return record

    record.update(
        {
            "construction_completed": True,
            "construction_time": 0.25,
        }
    )
    if label.startswith("ms_"):
        record.update(
            {
                "heuristic_kind": "merge_and_shrink",
                "heuristic_size_bound": 10000,
                "value_cap": _expected_ms_value_cap(label),
                "cofactor_width": 4,
                "width_upper_bound": 25,
                "num_values": 5,
                "num_terminals": 5,
                "add_nodes": 20,
            }
        )
    elif _is_selector(label):
        _attach_selector_trace(record, label)
    else:
        kind = "pdb_cegar" if "cegar" in label else "pdb_goal_fill"
        record.update(
            {
                "heuristic_kind": kind,
                "heuristic_size_bound": 100000,
                "value_cap": -1,
                "cofactor_width": 4,
                "width_upper_bound": 25,
                "num_values": 5,
                "num_terminals": 5,
                "add_nodes": 20,
                "pdb_final_format": "legacy",
                "pdb_pattern_size": 2,
                "pdb_final_num_values": 5,
                "pdb_final_cofactor_width": 4,
                "pdb_final_width_upper_bound": 25,
            }
        )
    return record


def _expect_error(
    records,
    tasks,
    planner_revision,
    protocol_revision,
    binary_sha256,
    fragment,
):
    _, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    if not any(fragment in error for error in errors):
        raise AssertionError(
            "synthetic mutation did not produce {!r}: {!r}".format(
                fragment, errors[:12]
            )
        )


def _synthetic_target(records, label, task):
    return next(
        record
        for record in records
        if record["algorithm"] == label
        and record["domain"] == task[0]
        and record["problem"] == task[1]
    )


def self_test():
    planner_revision = EXPECTED_PLANNER_REVISION
    protocol_revision = "0123456789abcdef0123456789abcdef01234567"
    binary_sha256 = EXPECTED_CACHE_BINARY_SHA256
    assert require_reviewed_pins(protocol_revision, binary_sha256) == (
        planner_revision,
        protocol_revision,
        binary_sha256,
    )
    assert require_reviewed_pins() == (
        planner_revision,
        EXPECTED_PROTOCOL_REVISION,
        binary_sha256,
    )

    validate_runner_contract(
        check_cache_pin=True, expected_cache_hash=binary_sha256
    )
    common.self_test_cofactor_width_parser()
    common.self_test_pdb_selector_parser()
    tasks = load_manifest(runner.MANIFEST)
    if [analyzer_utils.task_label(task) for task in tasks] != runner.read_manifest():
        raise AssertionError("runner/analyzer task order differs")

    base_times = {label: 30.0 + index for index, label in enumerate(LABELS)}
    base_times[BLIND] = 20.0
    base_times[MS_EXACT] = 15.0
    base_times["ms_cap32"] = 10.0
    base_times["pdb_selector_k32"] = 5.0
    records = []
    for label, search in CONFIGS:
        for task_index, task in enumerate(tasks):
            planner_time = base_times[label]
            if label == "pdb_goal_fill_b100k" and task_index == 0:
                planner_time = None
            records.append(
                synthetic_record(
                    label,
                    search,
                    task,
                    planner_revision,
                    protocol_revision,
                    binary_sha256,
                    planner_time,
                    task_index + 1,
                )
            )

    matrix, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    assert not errors, errors[:12]
    # Lab writes fetched properties with recursive sort_keys=True. Raw selector
    # key order is certified by the parser before this serialization boundary.
    lab_roundtrip = json.loads(json.dumps(records, sort_keys=True))
    _, roundtrip_errors = validate_records(
        lab_roundtrip,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
    )
    assert not roundtrip_errors, roundtrip_errors[:12]
    scores = analyze_scores(matrix, tasks)
    assert scores["image_time_tiebreak_available"] is True
    assert scores["selected"]["label"] == "pdb_selector_k32"
    rank = {item["label"]: item["rank"] for item in scores["ranking"]}
    assert rank["pdb_goal_fill_b100k"] > rank[MS_EXACT]
    selector_score = next(
        item for item in scores["ranking"] if item["label"] == "pdb_selector_k32"
    )
    assert selector_score["construction"]["fallbacks"] == 0
    assert selector_score["selector"]["certified"] == EXPECTED_TASKS
    assert selector_score["cofactor_width"]["observed"] == EXPECTED_TASKS

    paired = all_paired_deltas(
        matrix, tasks, scores["image_time_tiebreak_available"]
    )
    assert len(paired) == EXPECTED_CONFIGS * 2
    artifact = make_selection_artifact(
        records,
        scores,
        paired,
        planner_revision,
        protocol_revision,
        binary_sha256,
    )
    assert artifact["schema"] == ARTIFACT_SCHEMA
    assert "selection_artifact_sha256" not in artifact
    assert all(
        "selection_artifact_sha256" not in section
        for section in artifact.values()
        if isinstance(section, dict)
    )
    assert (
        artifact["selection"]["global_winner"]["label"]
        == "pdb_selector_k32"
    )
    assert (
        artifact["selection"]["selector_family_winner"]["label"]
        == "pdb_selector_k32"
    )
    assert len(artifact["selection"]["ranking"]) == EXPECTED_CONFIGS
    assert artifact["selection"]["image_time_tiebreak_used"] is True
    assert (
        artifact["selection"]["selector_eligibility_sha256"]
        == SELECTOR_ELIGIBILITY_SHA256
    )
    assert (
        artifact["pilot"]["planner_preprocess_sha256"]
        == EXPECTED_CACHE_PREPROCESS_SHA256
    )
    assert (
        artifact["pilot"]["metrics_validation_protocol"]
        == EXPECTED_METRICS_VALIDATION_PROTOCOL
    )
    assert artifact["validation"]["task_manifest"] == VALIDATION_MANIFEST
    assert (
        artifact["validation"]["task_manifest_sha256"]
        == VALIDATION_MANIFEST_SHA256
    )
    assert (
        artifact["validation"]["task_sources_sha256"]
        == VALIDATION_TASK_SOURCES_SHA256
    )
    assert artifact["validation"]["task_count"] == VALIDATION_TASKS
    assert artifact["validation"]["domain_count"] == VALIDATION_DOMAINS
    assert artifact["validation"]["analysis"] == {
        "protocol": VALIDATION_ANALYSIS_PROTOCOL,
        "primary_comparison": "selector-vs-pdb-cegar",
        "primary_estimand": (
            "selector-minus-cegar-equally-weighted-domain-macro-coverage/v1"
        ),
        "resampling_unit": "domain",
        "bootstrap_method": "sha256-counter-domain-resampling/v1",
        "bootstrap_seed": VALIDATION_BOOTSTRAP_SEED,
        "bootstrap_replicates": VALIDATION_BOOTSTRAP_REPLICATES,
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
    }
    assert [item["label"] for item in artifact["validation"]["configs"]] == [
        BLIND,
        MS_EXACT,
        "ms_cap32",
        "pdb_goal_fill_b100k",
        "pdb_cegar_b100k",
        MS_CAP32_BUILD60_LABEL,
        "pdb_selector_k32",
    ]
    assert artifact["validation"]["config_count"] == 7
    assert artifact["validation"]["expected_run_count"] == 644
    assert artifact["validation"]["array_layout"] == {
        "raw_runs": 644,
        "array_tasks": 644,
        "runs_per_array_task": 1,
        "scheduler_time_limit_seconds": 600,
    }
    assert (
        artifact["validation"]["option_matrix_sha256"]
        == "6ee8bda1adbd64924936d5b91de9a0ad2bc3b0828671729eefc5990c3bddcb39"
    )
    assert artifact["validation"]["roles"] == {
        "global_winner": "pdb_selector_k32",
        "selector_family_winner": "pdb_selector_k32",
        "ms_build_budget_safeguard": MS_CAP32_BUILD60_LABEL,
        "matched_same_k_unbatched": None,
    }
    assert "pilot-global-winner" in artifact["validation"]["configs"][-1][
        "roles"
    ]
    validation_options = _validation_option_records(
        artifact["validation"]["configs"]
    )
    assert len({item["label"] for item in validation_options}) == 7
    assert len({item["search"] for item in validation_options}) == 7
    assert (
        sha256_json(validation_options)
        == artifact["validation"]["option_matrix_sha256"]
    )
    tampered_options = copy.deepcopy(validation_options)
    tampered_options[0]["search"] = "sym_fw(max_time=1)"
    assert (
        sha256_json(tampered_options)
        != artifact["validation"]["option_matrix_sha256"]
    )
    assert (
        sha256_json(artifact["validation"]["comparisons"])
        == artifact["validation"]["comparisons_sha256"]
    )
    assert canonical_json(artifact) == canonical_json(
        make_selection_artifact(
            list(reversed(records)),
            scores,
            paired,
            planner_revision,
            protocol_revision,
            binary_sha256,
        )
    )

    # If a fixed control wins globally, it receives an alias role on its
    # existing cell; the independently derived selector-family winner remains
    # present and the matrix stays at seven unique configurations.
    control_matrix = copy.deepcopy(matrix)
    for task in tasks:
        control_matrix[("ms_cap32", task)]["planner_time"] = 1.0
    control_scores = analyze_scores(control_matrix, tasks)
    assert control_scores["selected"]["label"] == "ms_cap32"
    control_records = [
        control_matrix[(label, task)] for label in LABELS for task in tasks
    ]
    control_artifact = make_selection_artifact(
        control_records,
        control_scores,
        all_paired_deltas(
            control_matrix,
            tasks,
            control_scores["image_time_tiebreak_available"],
        ),
        planner_revision,
        protocol_revision,
        binary_sha256,
    )
    assert control_artifact["selection"]["global_winner"]["label"] == (
        "ms_cap32"
    )
    assert (
        control_artifact["selection"]["selector_family_winner"]["label"]
        == "pdb_selector_k32"
    )
    assert control_artifact["validation"]["config_count"] == 7
    assert control_artifact["validation"]["expected_run_count"] == 644
    control_config = next(
        config
        for config in control_artifact["validation"]["configs"]
        if config["label"] == "ms_cap32"
    )
    assert "pilot-global-winner" in control_config["roles"]
    assert [
        config["label"]
        for config in control_artifact["validation"]["configs"]
    ].count("ms_cap32") == 1

    # A batched selector-family winner deterministically adds the exact
    # same-K unbatched selector, without duplicating labels or searches.
    batched_label = "pdb_selector_k64_adapt_w64_r1_n1m"
    batched_matrix = copy.deepcopy(matrix)
    for task in tasks:
        batched_matrix[(batched_label, task)]["planner_time"] = 1.0
    batched_scores = analyze_scores(batched_matrix, tasks)
    assert batched_scores["selected"]["label"] == batched_label
    batched_records = [
        batched_matrix[(label, task)] for label in LABELS for task in tasks
    ]
    batched_paired = all_paired_deltas(
        batched_matrix,
        tasks,
        batched_scores["image_time_tiebreak_available"],
    )
    batched_artifact = make_selection_artifact(
        batched_records,
        batched_scores,
        batched_paired,
        planner_revision,
        protocol_revision,
        binary_sha256,
    )
    assert (
        batched_artifact["selection"]["global_winner"]["label"]
        == batched_label
    )
    assert (
        batched_artifact["selection"]["selector_family_winner"]["label"]
        == batched_label
    )
    batched_validation = batched_artifact["validation"]
    assert [item["label"] for item in batched_validation["configs"]] == [
        BLIND,
        MS_EXACT,
        "ms_cap32",
        "pdb_goal_fill_b100k",
        "pdb_cegar_b100k",
        MS_CAP32_BUILD60_LABEL,
        batched_label,
        "pdb_selector_k64",
    ]
    assert batched_validation["config_count"] == 8
    assert batched_validation["expected_run_count"] == 736
    assert batched_validation["roles"]["matched_same_k_unbatched"] == (
        "pdb_selector_k64"
    )
    assert (
        batched_validation["option_matrix_sha256"]
        == "d92ce204fbe10081b602808e4f43c9da0ca699f1337d1d1748a68bda71ac3b3d"
    )
    batched_options = _validation_option_records(
        batched_validation["configs"]
    )
    assert len({item["label"] for item in batched_options}) == 8
    assert len({item["search"] for item in batched_options}) == 8
    assert sha256_json(batched_options) == batched_validation[
        "option_matrix_sha256"
    ]
    assert any(
        comparison["name"] == "selector-batching-vs-same-k-unbatched"
        and comparison["candidate"] == batched_label
        and comparison["reference"] == "pdb_selector_k64"
        for comparison in batched_validation["comparisons"]
    )

    target = _synthetic_target(records, "pdb_selector_k32", tasks[0])
    saved = copy.deepcopy(target)
    strong = target[common.PDB_SELECTOR_CANDIDATES_PROPERTY][1]
    strong.update(
        {
            "initial_dead_end": True,
            "initial_h": None,
            "finite_sum": 0,
            "finite_count": 1,
            "dead_count": strong["abstract_states"] - 1,
        }
    )
    target[common.PDB_SELECTOR_SELECTED_PROPERTY] = copy.deepcopy(strong)
    target["num_values"] = 1
    target["pdb_final_num_values"] = 1
    target[common.PDB_SELECTOR_FINAL_PROPERTY]["num_values"] = 1
    _refresh_selector_hashes(target)
    errors = []
    _validate_heuristic(target, "pdb_selector_k32", "all-dead", errors)
    _validate_selector_trace(
        target, "pdb_selector_k32", "all-dead", errors
    )
    assert not errors, errors[:12]
    impossible_all_dead = copy.deepcopy(strong)
    impossible_all_dead["finite_count"] = 0
    impossible_all_dead["dead_count"] = impossible_all_dead["abstract_states"]
    assert "finite abstract goal state" in _selector_record_error(
        impossible_all_dead, "candidate", 32
    )
    impossible_sum = copy.deepcopy(saved[common.PDB_SELECTOR_CANDIDATES_PROPERTY][1])
    impossible_sum["finite_sum"] = 0
    assert "finite_sum is smaller" in _selector_record_error(
        impossible_sum, "candidate", 32
    )
    impossible_empty = copy.deepcopy(
        saved[common.PDB_SELECTOR_CANDIDATES_PROPERTY][0]
    )
    impossible_empty["pattern"] = [99]
    assert "empty-pattern invariants" in _selector_record_error(
        impossible_empty, "candidate", 32
    )
    impossible_oversized = copy.deepcopy(
        saved[common.PDB_SELECTOR_CANDIDATES_PROPERTY][2]
    )
    impossible_oversized["pattern"] = [1, 2]
    assert "unmaterialized outcome" in _selector_record_error(
        impossible_oversized, "candidate", 32
    )
    saved_terminals = target["num_terminals"]
    target["num_terminals"] += 1
    terminal_errors = []
    _validate_selector_trace(
        target, "pdb_selector_k32", "terminal-mismatch", terminal_errors
    )
    assert any("num_terminals" in error for error in terminal_errors)
    target["num_terminals"] = saved_terminals
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "initial-dead selector winner has incompatible planner outcome",
    )
    target.clear()
    target.update(saved)

    interrupted = _synthetic_target(records, "pdb_selector_k256", tasks[0])
    saved_interrupted = copy.deepcopy(interrupted)
    interrupted.update(
        {
            "coverage": 0,
            "planner_exit_code": 23,
            "error": "search-out-of-time",
            "unsolvable": 0,
            "plan_file_present": False,
        }
    )
    for field in (
        "solution_cost",
        "plan_file_cost",
        "planner_time",
        "construction_completed",
        "construction_time",
        "heuristic_kind",
        "heuristic_size_bound",
        "value_cap",
        "cofactor_width",
        "width_upper_bound",
        "num_values",
        "num_terminals",
        "add_nodes",
    ) + PDB_FINAL_FIELDS + SELECTOR_TRACE_FIELDS:
        interrupted.pop(field, None)
    interrupted.update(
        {
            common.PDB_SELECTOR_CANDIDATES_PROPERTY: [
                copy.deepcopy(
                    saved_interrupted[common.PDB_SELECTOR_CANDIDATES_PROPERTY][0]
                )
            ],
            "pdb_selector_trace_complete": False,
            "pdb_selector_trace_certified": False,
            "pdb_selector_validation_error": "selector construction interrupted",
        }
    )
    _, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    assert not errors, errors[:12]
    interrupted[common.PDB_SELECTOR_CANDIDATES_PROPERTY] = []
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "explicit interrupted selector trace needs 1..5 candidates",
    )
    interrupted[common.PDB_SELECTOR_CANDIDATES_PROPERTY] = [
        copy.deepcopy(
            saved_interrupted[common.PDB_SELECTOR_CANDIDATES_PROPERTY][0]
        )
    ]

    skipped = copy.deepcopy(
        saved_interrupted[common.PDB_SELECTOR_CANDIDATES_PROPERTY][1]
    )
    skipped["sources"] = ["goal_fill"]
    interrupted[common.PDB_SELECTOR_CANDIDATES_PROPERTY].append(skipped)
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "interrupted selector prefix skips earlier sources",
    )
    interrupted[common.PDB_SELECTOR_CANDIDATES_PROPERTY].pop()
    merged_skip = interrupted[common.PDB_SELECTOR_CANDIDATES_PROPERTY][0]
    merged_skip["sources"] = ["empty", "cegar"]
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "interrupted selector prefix skips earlier sources",
    )
    merged_skip["sources"] = ["empty"]
    interrupted["planner_exit_code"] = 11
    interrupted["error"] = "search-unsolvable"
    interrupted["unsolvable"] = 1
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "incomplete selector trace needs exit 22/23/24",
    )

    # A kill after the selected line but before the final line is also a
    # semantically checkable prefix: all candidates/provenance and the winner
    # must already be complete and exact.
    interrupted["planner_exit_code"] = 23
    interrupted["error"] = "search-out-of-time"
    interrupted["unsolvable"] = 0
    interrupted[common.PDB_SELECTOR_CANDIDATES_PROPERTY] = copy.deepcopy(
        saved_interrupted[common.PDB_SELECTOR_CANDIDATES_PROPERTY]
    )
    interrupted[common.PDB_SELECTOR_SELECTED_PROPERTY] = copy.deepcopy(
        saved_interrupted[common.PDB_SELECTOR_SELECTED_PROPERTY]
    )
    _, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    assert not errors, errors[:12]

    # The final/heuristic lines can be complete immediately before a resource
    # kill and immediately before the construction event. A certified trace is
    # authoritative even though construction_completed is absent.
    interrupted.clear()
    interrupted.update(copy.deepcopy(saved_interrupted))
    interrupted.update(
        {
            "coverage": 0,
            "planner_exit_code": 23,
            "error": "search-out-of-time",
            "unsolvable": 0,
            "plan_file_present": False,
        }
    )
    for field in (
        "solution_cost",
        "plan_file_cost",
        "planner_time",
        "construction_completed",
        "construction_time",
        "heuristic_kind",
        "heuristic_size_bound",
        "value_cap",
    ):
        interrupted.pop(field, None)
    _, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    assert not errors, errors[:12]
    saved_wbh_fields = {
        field: interrupted.pop(field)
        for field in ("width_upper_bound", "num_values", "num_terminals", "add_nodes")
    }
    _, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    assert not errors, errors[:12]
    interrupted.update(saved_wbh_fields)
    interrupted["planner_exit_code"] = 11
    interrupted["error"] = "search-unsolvable"
    interrupted["unsolvable"] = 1
    _expect_error(
        records,
        tasks,
        planner_revision,
        protocol_revision,
        binary_sha256,
        "selector unsolvability outcome lacks completed construction",
    )
    interrupted.clear()
    interrupted.update(saved_interrupted)

    target["raw_metrics_complete"] = False
    matrix, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    assert not errors, errors[:12]
    assert analyze_scores(matrix, tasks)["image_time_tiebreak_available"] is False
    target["raw_metrics_complete"] = True

    presearch = _synthetic_target(records, "pdb_goal_fill_b100k", tasks[0])
    saved_presearch = copy.deepcopy(presearch)
    presearch.update(
        {
            "planner_exit_code": 20,
            "error": "translate-out-of-memory",
            "unsolvable": 0,
            "coverage": 0,
            "plan_file_present": False,
        }
    )
    presearch.update(EMPTY_LEGACY_CONVENTIONS)
    presearch["wbh_log_nonempty"] = False
    presearch["raw_metrics_complete"] = False
    presearch["piece_metrics_certified"] = False
    for field in (
        SCHEMA_V2_INTEGER_METRICS
        + SCHEMA_V2_REAL_METRICS
        + (
            "construction_completed",
            "construction_time",
            "heuristic_kind",
            "heuristic_size_bound",
            "value_cap",
            "cofactor_width",
            "width_upper_bound",
            "num_values",
            "num_terminals",
            "add_nodes",
        )
        + PDB_FINAL_FIELDS
    ):
        presearch.pop(field, None)
    _, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    assert not errors, errors[:12]
    presearch.clear()
    presearch.update(saved_presearch)

    blind = _synthetic_target(records, BLIND, tasks[0])
    mutations = (
        ("protocol", "wrong", "protocol="),
        ("planner_revision", "f" * 40, "planner_revision="),
        ("protocol_revision", "e" * 40, "protocol_revision="),
        ("planner_binary_sha256", "e" * 64, "planner_binary_sha256="),
        ("scheduler_partition", "gpu", "scheduler_partition="),
        ("scheduler_array_tasks", 999, "scheduler_array_tasks="),
        ("coverage", 2, "coverage must be integer 0 or 1"),
    )
    for field, bad, fragment in mutations:
        old = blind[field]
        blind[field] = bad
        _expect_error(
            records, tasks, planner_revision, protocol_revision,
            binary_sha256, fragment
        )
        blind[field] = old

    old_options = blind["component_options"]
    blind["component_options"] = ["--search", "sym_fw()"]
    _expect_error(
        records, tasks, planner_revision, protocol_revision,
        binary_sha256, "component_options="
    )
    blind["component_options"] = old_options

    old_cost = blind["solution_cost"]
    blind["solution_cost"] = old_cost + 1
    _expect_error(
        records, tasks, planner_revision, protocol_revision,
        binary_sha256, "solved-cost disagreement"
    )
    blind["solution_cost"] = old_cost

    old_time = blind["planner_time"]
    blind["planner_time"] = str(old_time)
    _expect_error(
        records, tasks, planner_revision, protocol_revision,
        binary_sha256, "finite nonnegative planner_time"
    )
    blind["planner_time"] = old_time

    old_exit = blind["planner_exit_code"]
    blind["planner_exit_code"] = 32
    _expect_error(
        records, tasks, planner_revision, protocol_revision,
        binary_sha256, "explained outcome"
    )
    blind["planner_exit_code"] = old_exit

    def selector_mutation(mutator, fragment):
        original = copy.deepcopy(target)
        mutator(target)
        _expect_error(
            records, tasks, planner_revision, protocol_revision,
            binary_sha256, fragment
        )
        target.clear()
        target.update(original)

    selector_mutation(
        lambda item: item[common.PDB_SELECTOR_CANDIDATES_PROPERTY][1].update(
            {"pattern": []}
        ),
        "patterns are not deduplicated",
    )
    selector_mutation(
        lambda item: item[common.PDB_SELECTOR_CANDIDATES_PROPERTY][1][
            "sources"
        ].remove("goal_fill"),
        "provenance does not partition five sources",
    )
    selector_mutation(
        lambda item: item.update(
            {
                common.PDB_SELECTOR_SELECTED_PROPERTY: copy.deepcopy(
                    item[common.PDB_SELECTOR_CANDIDATES_PROPERTY][0]
                )
            }
        ),
        "violates exact selector score",
    )
    selector_mutation(
        lambda item: item[common.PDB_SELECTOR_CANDIDATES_PROPERTY][1].update(
            {"cofactor_width_budget": 31}
        ),
        "cofactor_width_budget does not match config",
    )
    selector_mutation(
        lambda item: item.update({"pdb_final_cofactor_width": 999}),
        "expected selected value",
    )
    selector_mutation(
        lambda item: item.update({"pdb_selector_trace_sha256": "f" * 64}),
        "disagrees with trace",
    )

    original = copy.deepcopy(target)
    strong = target[common.PDB_SELECTOR_CANDIDATES_PROPERTY][1]
    strong["finite_sum"] += strong["finite_count"]
    target[common.PDB_SELECTOR_SELECTED_PROPERTY] = copy.deepcopy(strong)
    _refresh_selector_hashes(target)
    _expect_error(
        records, tasks, planner_revision, protocol_revision,
        binary_sha256, "selector pool fingerprint disagreement"
    )
    target.clear()
    target.update(original)

    blind[common.PDB_SELECTOR_CANDIDATES_PROPERTY] = []
    _expect_error(
        records, tasks, planner_revision, protocol_revision,
        binary_sha256, "non-selector contains selector fields"
    )
    del blind[common.PDB_SELECTOR_CANDIDATES_PROPERTY]

    duplicate = dict(records[0])
    records.append(duplicate)
    _expect_error(
        records, tasks, planner_revision, protocol_revision,
        binary_sha256, "duplicate cell"
    )
    records.pop()
    removed = records.pop()
    _expect_error(
        records, tasks, planner_revision, protocol_revision,
        binary_sha256, "missing 1 of 1000 expected algorithm-task cells"
    )
    records.append(removed)

    unsolved = _synthetic_target(records, "pdb_goal_fill_b100k", tasks[0])
    old_outcome = (
        unsolved["planner_exit_code"],
        unsolved["error"],
        unsolved["unsolvable"],
    )
    unsolved["planner_exit_code"] = 11
    unsolved["error"] = "search-unsolvable"
    unsolved["unsolvable"] = 1
    _expect_error(
        records, tasks, planner_revision, protocol_revision,
        binary_sha256, "solved/proved-unsolvable disagreement"
    )
    (
        unsolved["planner_exit_code"],
        unsolved["error"],
        unsolved["unsolvable"],
    ) = old_outcome

    print(
        "synthetic Arrhenius selector analyzer tests: PASS "
        "(1000 cells; exact pool/score/final/provenance; ranking/censoring; "
        "artifact-v2 heldout matrices 644/736)"
    )


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    planner_revision, protocol_revision, binary_sha256 = require_reviewed_pins()
    validate_runner_contract(
        check_cache_pin=True, expected_cache_hash=binary_sha256
    )
    if args.properties is None:
        raise AnalysisError("properties input is required")
    tasks = load_manifest(args.manifest)
    if [analyzer_utils.task_label(task) for task in tasks] != runner.read_manifest():
        raise AnalysisError("analyzed task sequence differs from the exact runner manifest")
    records, source = analyzer_utils.load_properties(args.properties)
    matrix, errors = validate_records(
        records, tasks, planner_revision, protocol_revision, binary_sha256
    )
    raise_validation_errors(errors)
    scores = analyze_scores(matrix, tasks)
    paired = all_paired_deltas(
        matrix, tasks, scores["image_time_tiebreak_available"]
    )
    if args.emit_selection_artifact:
        artifact = make_selection_artifact(
            records,
            scores,
            paired,
            planner_revision,
            protocol_revision,
            binary_sha256,
        )
        # This mode has no other stdout output and performs no writes.
        print(canonical_json(artifact))
    else:
        print_report(source, records, scores, paired)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (AnalysisError, analyzer_utils.AnalysisError, RuntimeError) as err:
        print("analysis error: {}".format(err), file=sys.stderr)
        sys.exit(2)
