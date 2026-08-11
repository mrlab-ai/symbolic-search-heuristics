#!/usr/bin/env python3
"""Analyze the frozen Arrhenius full-population selector experiment.

The analysis is deliberately result-neutral.  It consumes the exact selector
screen artifact used by :mod:`exp_arrhenius_selector_full` and one fetched Lab
properties object (or evaluation directory/tar archive).  The carried 7/8
configuration matrix is never reranked.  Every one of the 9,639 or 11,016
cells, including its wrapper-completion and requeue provenance, must validate
before any descriptive census result is emitted.

Ordinary analysis remains blocked until every corrected downstream launch
identity below is pinned.  ``--self-test`` exercises both layouts without
relaxing those gates.
"""

from __future__ import annotations

import argparse
import copy
import gc
import hashlib
import io
import json
import math
import re
import sys
import tarfile
import tempfile
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_arrhenius_selector_validation as heldout
import exp_arrhenius_selector_full as full_runner
import suite_cost_manifest


class AnalysisError(RuntimeError):
    pass


ANALYSIS_SCHEMA = "symbolic-search-heuristics/full-population-analysis/v3"
ANALYSIS_PROTOCOL = "full-supported-population-census-v1"
FULL_PROTOCOL = "arrhenius-selector-full-population-v3"
ARTIFACT_SCHEMA = (
    "symbolic-search-heuristics/arrhenius-selector-screen-selection/v3"
)
MATRIX_CARRY_FORWARD_PROTOCOL = (
    "screen-artifact-v3-to-heldout-v2-contract-to-full-unchanged/v2"
)
TASK_SELECTION_PROTOCOL = (
    "suite-cost-manifest-v2-positive-cost-normalized-axiom-free/v1"
)
SCHEDULER_ENVELOPE_PROTOCOL = (
    "conditional-requested-70m-75m-using-300plus60-accounting/v1"
)

# The artifact pin remains immutable.  Downstream launch-derived identities
# are deliberately pinned in two steps: first commit the corrected runners as
# launch revision R and launch only from clean R; then, in a descendant,
# record R and the exact full-runner bytes for analysis.  Launching from that
# analysis descendant would record the wrong protocol HEAD.
EXPECTED_SELECTION_ARTIFACT_SHA256 = (
    "d35a1df68eebbd099fe81f86e6e0f6a96ce770572574f9ae013ab4eb0b2c8eb2"
)
EXPECTED_FULL_PROTOCOL_REVISION = (
    "a52488637a1c054b26dac93fe2eb1a556110a2dd"
)

FULL_RUNNER_SOURCE_SHA256 = (
    "84d6408781724203ba3420d6a559d1c56aac196f560f8b76c14f8cde730ab642"
)
PILOT_PLANNER_REVISION = "58a3f742d7ac63f391d06c237573f14ad590c187"
PILOT_PROTOCOL_REVISION = "d6d98ad42f3976cd5cf0c9b17d8fa255354fbfbf"
PILOT_PLANNER_BINARY_SHA256 = (
    "59b97e8b1e777f700c255932271604393f60ec9aeba5c0151d0b7415a3a58511"
)
PILOT_PLANNER_PREPROCESS_SHA256 = (
    "acf2fc66c0b189095111a9d227ccb5b7acc564f1a6cb7bfd557904fa3c76798c"
)
PLANNER_REVISION = "165b6d2ee29d5d7b6e1bf4c52540c393ba19b54f"
CACHE_BINARY_SHA256 = (
    "af2a19d236ecad9b747d2a1b9c49da73d98248c38d21cc60ad0ac7613d74bdbe"
)
CACHE_PREPROCESS_SHA256 = (
    "1b351a4a5f9380bf41fe9fd61b98c816505ebd8cf88b20afa0d81a9bfb2474bd"
)
CACHE_NAME_SUFFIX = "_61a748e5"
INITIAL_DEAD_CONSTRUCTION_LOGGING_PROTOCOL = (
    "pdb-ms-initial-dead-bdd-construction-prelog/v1"
)
BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
BENCHMARK_REPOSITORY = "https://github.com/aibasel/downward-benchmarks.git"
EXPECTED_PYTHON_VERSION = "3.9.25"
EXPECTED_LAB_VERSION = "8.0"

EXPECTED_TASKS = 1377
EXPECTED_DOMAINS = 46
EXPECTED_TASK_MANIFEST_SHA256 = (
    "295bff030c51eaf39871714335ff9cb945ce39ebc556774eeb3bfad112681345"
)
EXPECTED_DOMAIN_SEQUENCE_SHA256 = (
    "b0d849f351ff6d5c793d9c209c67c11ab5a7d6963fed5666f5ad49ce73845811"
)
EXPECTED_DOMAIN_TASK_COUNTS_SHA256 = (
    "5db83d994be7d9145233adb0a3839a69f8717145878d08b138f328b19fc9d9e2"
)
EXPECTED_TASK_SOURCES_SHA256 = (
    "9ce25a012592bfb2557fe21cc4a3fdb3dbd24f9d2a4ed79ee16e75be183be5dd"
)
EXPECTED_SOURCE_MANIFEST_SHA256 = (
    "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168"
)
SCREEN_MANIFEST_NAME = "selector_pilot_suite.txt"
SCREEN_MANIFEST_SHA256 = (
    "3195dac7e62a34e5ac4cbeb715ab7f9b99e2ee64341082dd7d718ea2820751ca"
)
EXPECTED_SCREEN_EXCLUDED_TASKS = 1327
EXPECTED_SCREEN_EXCLUDED_DOMAINS = 46
EXPECTED_SCREEN_EXCLUDED_TASK_MANIFEST_SHA256 = (
    "1e126791b438d903cb6adcc441391b92d76a7e14cf46f6a89465a066823a986f"
)
EXPECTED_SCREEN_EXCLUDED_TASK_SOURCES_SHA256 = (
    "158e5446e3b97ddd63095441c518ecbe6d2e3ce3529aa9a8fd412df23e706068"
)

TIME_LIMIT_SECONDS = 300.0
MEMORY_LIMIT_MIB = 8192.0
PAR2_UNSOLVED_SECONDS = 600
EXPECTED_UNBATCHED_RUNS = 9639
EXPECTED_BATCHED_RUNS = 11016
EXPECTED_RUN_COUNTS = (EXPECTED_UNBATCHED_RUNS, EXPECTED_BATCHED_RUNS)
EXPECTED_CONFIG_COUNTS = {EXPECTED_UNBATCHED_RUNS: 7, EXPECTED_BATCHED_RUNS: 8}
SYNTHETIC_MACRO_PINS = {
    EXPECTED_UNBATCHED_RUNS: {
        "primary_fraction": (8791, 579600),
        "sensitivity_fraction": (58678349, 2988031200),
        "primary_and_sensitivity_sha256": (
            "7dd29770f6158366cdcc70c35e90d28fab4c0d3d8b40308dcdb15997265f9623"
        ),
    },
    EXPECTED_BATCHED_RUNS: {
        "primary_fraction": (8791, 579600),
        "sensitivity_fraction": (58678349, 2988031200),
        "primary_and_sensitivity_sha256": (
            "fa04a4fa44b042196ed12e3f5fd1ed384156b0999af02f457e232ae53f4da84b"
        ),
    },
}
FULL_SCHEDULER_TIME_LIMITS = {
    EXPECTED_UNBATCHED_RUNS: "01:10:00",
    EXPECTED_BATCHED_RUNS: "01:15:00",
}
FULL_SCHEDULER_TIME_LIMIT_SECONDS = {
    EXPECTED_UNBATCHED_RUNS: 4200,
    EXPECTED_BATCHED_RUNS: 4500,
}
EXPECTED_ARRAY_TASKS = {
    EXPECTED_UNBATCHED_RUNS: 964,
    EXPECTED_BATCHED_RUNS: 918,
}
EXPECTED_RUNS_PER_ARRAY_TASK = {
    EXPECTED_UNBATCHED_RUNS: 10,
    EXPECTED_BATCHED_RUNS: 12,
}
EXPECTED_ARRAY_ASSIGNMENT_SHA256 = {
    EXPECTED_UNBATCHED_RUNS: (
        "3f0970202564673273feda3f860c451b787def4ee932da0925bada168dd7ff98"
    ),
    EXPECTED_BATCHED_RUNS: (
        "f9fc556b289f773fe77f9f8a5de8900d5866491f092c13c152a5015394082f6a"
    ),
}
EXPECTED_FINAL_LOGICAL_GROUP_SLURM_ID = {
    EXPECTED_UNBATCHED_RUNS: 118,
    EXPECTED_BATCHED_RUNS: 871,
}
EXPECTED_PROSPECTIVE_JOB_SHA256 = {
    EXPECTED_UNBATCHED_RUNS: (
        "c83c880c1bfaa503cfffab69c91abb037e58b4424b7216480aa551631aed043f"
    ),
    EXPECTED_BATCHED_RUNS: (
        "857fd48ef3cc1b3e76a012fed8bcb3ddf5b4a0bf03686daaed7eca7424361bcd"
    ),
}
EXPECTED_MATERIALIZED_PDDL_FILES = {
    EXPECTED_UNBATCHED_RUNS: 19278,
    EXPECTED_BATCHED_RUNS: 22032,
}
EXPECTED_MATERIALIZED_PDDL_BYTES = {
    EXPECTED_UNBATCHED_RUNS: 1070713469,
    EXPECTED_BATCHED_RUNS: 1223672536,
}
EXPECTED_PDDL_BYTES_PER_CONFIG = 152959067
EXPECTED_UNIQUE_PDDL_SOURCE_FILES = 1569
EXPECTED_UNIQUE_PDDL_SOURCE_BYTES = 147961488
MATERIALIZED_PDDL_PROTOCOL = (
    "per-cell-independent-manual-byte-copy-temp-digest-atomic-replace-readonly/v1"
)

FULL_COMPLETION_MARKER = ".arrhenius-full-run-complete-v1"
FULL_COMPLETION_MARKER_SCHEMA = (
    "symbolic-search-heuristics/arrhenius-full-wrapper-completion/v1"
)
FULL_COMPLETION_MARKER_PROTOCOL = (
    "canonical-four-line-marker-atomic-after-python-wrapper-zero-exit/v1"
)
FULL_RESTART_COUNT_FILE = ".arrhenius-full-slurm-restart-count-v1"
FULL_PARTIAL_ARCHIVE_PREFIX = ".arrhenius-full-partial-before-restart-"
FULL_STATIC_RUN_ENTRIES = (
    "domain.pddl",
    "problem.pddl",
    "run",
    "static-properties",
)
FULL_COMPLETION_ATTRIBUTES = (
    "full_completion_marker_present",
    "full_completion_marker_valid",
    "full_completion_marker_schema",
    "full_completion_marker_protocol",
    "full_completion_marker_sha256",
    "full_wrapper_run_id",
    "full_wrapper_exit_code",
    "full_completion_slurm_restart_count",
    "full_partial_archive_count",
    "full_partial_archive_restart_ids",
    "full_archived_slurm_restart_counts",
    "full_descriptive_cell_execution_count",
)

FULL_COMPLETION_POLICY = {
    "protocol": "exact-cell-census-completion-v1",
    "expected_cells_must_equal_declared_run_count": True,
    "exactly_one_fetched_record_per_cell": True,
    "protocol_recognized_terminal_outcome_required": True,
    "missing_cells_invalidate_analysis": True,
    "starved_cells_invalidate_analysis": True,
    "unexpected_outcomes_invalidate_analysis": True,
    "duplicate_cells_invalidate_analysis": True,
    "silent_partial_denominators_allowed": False,
    "posthoc_cell_fill_allowed": False,
    "recovery": (
        "Slurm may automatically requeue node-failed or preempted array "
        "elements; a requeue skips marked cells and overwrites unmarked "
        "partial cells. After terminal collection, invalidate this census "
        "on any missing or unexpected infrastructure cell; any further "
        "recovery requires a separately frozen recovery artifact before "
        "outcomes are inspected, not resubmission or post-hoc cell fill"
    ),
}
FULL_DYNAMIC_OUTPUT_POLICY = {
    "protocol": "archive-all-nonstatic-top-level-run-entries-on-requeue/v1",
    "preserved_entries": list(FULL_STATIC_RUN_ENTRIES),
    "preserved_archive_prefix": FULL_PARTIAL_ARCHIVE_PREFIX,
    "restart_count_source": "SLURM_RESTART_COUNT",
    "archive_name_format": FULL_PARTIAL_ARCHIVE_PREFIX + "%05d",
    "unmarked_partial_outputs_are_replaced": True,
}

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
BLIND = "blind_fw"
CEGAR = "pdb_cegar_b100k"
MS_CAP32_BUILD60 = "ms_cap32_build60"
PRIMARY_COMPARISON = "selector-vs-pdb-cegar"
PRIMARY_ESTIMAND = (
    "selector-minus-cegar-equally-weighted-46-domain-macro-coverage/v1"
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
        raise AnalysisError("value is not canonical finite JSON: {}".format(err))


def sha256_json(value):
    return hashlib.sha256(canonical_json(value).encode("ascii")).hexdigest()


def _same(actual, expected):
    return type(actual) is type(expected) and actual == expected


def _finite_number(value):
    if type(value) not in (int, float):
        return None
    try:
        value = float(value)
    except (OverflowError, TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


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


def _sha256_file(path):
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as err:
        raise AnalysisError("cannot hash {}: {}".format(path, err)) from err
    return digest.hexdigest()


def load_properties(raw_path):
    """Use the held-out analyzer's duplicate-key/symlink-safe JSON loader."""
    try:
        return heldout.load_properties(raw_path)
    except heldout.AnalysisError as err:
        raise AnalysisError(str(err)) from err


def load_selection_artifact(path):
    try:
        return heldout.load_selection_artifact(path)
    except heldout.AnalysisError as err:
        raise AnalysisError(str(err)) from err


def _load_screen_manifest():
    path = SCRIPT_DIR / SCREEN_MANIFEST_NAME
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as err:
        raise AnalysisError("cannot read screen manifest: {}".format(err)) from err
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
    if digest != SCREEN_MANIFEST_SHA256 or len(labels) != 50 or len(set(labels)) != 50:
        raise AnalysisError("frozen 50-task screen manifest changed")
    return [tuple(label.split(":", 1)) for label in labels]


def load_and_validate_tasks():
    """Reconstruct full and sensitivity task identities without a run grid."""
    supported = sorted(suite_cost_manifest.supported_tasks())
    tasks = list(supported)
    descriptions = ["{}:{}".format(*task) for task in tasks]
    task_digest = hashlib.sha256(
        "".join("{}\n".format(item) for item in descriptions).encode("utf-8")
    ).hexdigest()
    domains = list(dict.fromkeys(domain for domain, _ in tasks))
    domain_digest = hashlib.sha256(
        "".join("{}\n".format(domain) for domain in domains).encode("utf-8")
    ).hexdigest()
    counts = Counter(domain for domain, _ in tasks)
    count_records = [
        {"domain": domain, "task_count": counts[domain]} for domain in domains
    ]
    if (
        len(tasks) != EXPECTED_TASKS
        or len(set(tasks)) != EXPECTED_TASKS
        or len(domains) != EXPECTED_DOMAINS
        or task_digest != EXPECTED_TASK_MANIFEST_SHA256
        or domain_digest != EXPECTED_DOMAIN_SEQUENCE_SHA256
        or sha256_json(count_records) != EXPECTED_DOMAIN_TASK_COUNTS_SHA256
    ):
        raise AnalysisError("frozen 1377-task/domain census identity changed")

    data = suite_cost_manifest.load_manifest()
    records = {
        (item["domain"], item["problem"]): item for item in data["tasks"]
    }
    try:
        selected_records = [records[task] for task in tasks]
    except KeyError as err:
        raise AnalysisError(
            "full task missing from source manifest: {}:{}".format(*err.args[0])
        ) from err
    source_digest = hashlib.sha256(
        suite_cost_manifest.canonical_records_bytes(selected_records)
    ).hexdigest()
    manifest_digest = suite_cost_manifest.sha256_file(
        suite_cost_manifest.MANIFEST_PATH
    )
    if source_digest != EXPECTED_TASK_SOURCES_SHA256:
        raise AnalysisError("frozen full source-record digest changed")
    if manifest_digest != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise AnalysisError("frozen support-manifest bytes changed")

    screen = set(_load_screen_manifest())
    if not screen.issubset(set(tasks)):
        raise AnalysisError("screen tasks are not a subset of the full census")
    screen_excluded = [task for task in tasks if task not in screen]
    _validate_sensitivity_subset(tasks, screen_excluded, records)
    return tasks, screen_excluded, domains


def _validate_sensitivity_subset(tasks, subset, source_records=None):
    if len(tasks) != EXPECTED_TASKS or len(set(tasks)) != EXPECTED_TASKS:
        raise AnalysisError("sensitivity parent population changed")
    if len(subset) != len(set(subset)) or not set(subset).issubset(set(tasks)):
        raise AnalysisError("screen-excluded sensitivity is not a unique subset")
    descriptions = ["{}:{}".format(*task) for task in subset]
    digest = hashlib.sha256(
        "".join("{}\n".format(item) for item in descriptions).encode("utf-8")
    ).hexdigest()
    if source_records is None:
        data = suite_cost_manifest.load_manifest()
        source_records = {
            (item["domain"], item["problem"]): item for item in data["tasks"]
        }
    try:
        source_digest = hashlib.sha256(
            suite_cost_manifest.canonical_records_bytes(
                [source_records[task] for task in subset]
            )
        ).hexdigest()
    except KeyError as err:
        raise AnalysisError("sensitivity task lacks a source record") from err
    if (
        len(subset) != EXPECTED_SCREEN_EXCLUDED_TASKS
        or len({domain for domain, _ in subset}) != EXPECTED_SCREEN_EXCLUDED_DOMAINS
        or digest != EXPECTED_SCREEN_EXCLUDED_TASK_MANIFEST_SHA256
        or source_digest != EXPECTED_SCREEN_EXCLUDED_TASK_SOURCES_SHA256
    ):
        raise AnalysisError("frozen screen-excluded sensitivity subset changed")
    heldout_identity = _validate_heldout_inclusion(subset)
    return {
        "task_count": len(subset),
        "domain_count": len({domain for domain, _ in subset}),
        "task_manifest_sha256": digest,
        "task_sources_sha256": source_digest,
        "heldout_inclusion": heldout_identity,
    }


def _validate_heldout_inclusion(subset, heldout_tasks=None):
    """Attest that the claimed sensitivity really contains the held-out set."""
    if heldout_tasks is None:
        try:
            heldout_tasks = heldout.load_and_validate_tasks()
        except heldout.AnalysisError as err:
            raise AnalysisError(
                "cannot validate the frozen held-out manifest: {}".format(err)
            ) from err
    heldout_tasks = list(heldout_tasks)
    if (
        len(heldout_tasks) != heldout.EXPECTED_TASKS
        or len(set(heldout_tasks)) != heldout.EXPECTED_TASKS
        or len({domain for domain, _ in heldout_tasks}) != heldout.EXPECTED_DOMAINS
    ):
        raise AnalysisError("held-out inclusion requires the exact 92-task set")
    missing = sorted(set(heldout_tasks) - set(subset))
    if missing:
        raise AnalysisError(
            "screen-excluded sensitivity omits held-out tasks: {}".format(
                ", ".join("{}:{}".format(*task) for task in missing[:8])
            )
        )
    return {
        "task_count": heldout.EXPECTED_TASKS,
        "domain_count": heldout.EXPECTED_DOMAINS,
        "task_manifest_sha256": heldout.MANIFEST_SHA256,
        "task_sources_sha256": heldout.TASK_SOURCES_SHA256,
        "all_tasks_in_screen_excluded_sensitivity": True,
    }


def _add_config(configs, label, search, role):
    label_matches = [item for item in configs if item["label"] == label]
    search_matches = [item for item in configs if item["search"] == search]
    if label_matches or search_matches:
        if (
            len(label_matches) != 1
            or len(search_matches) != 1
            or label_matches[0] is not search_matches[0]
        ):
            raise AnalysisError("configuration label/search collision")
        if role not in label_matches[0]["roles"]:
            label_matches[0]["roles"].append(role)
        return
    configs.append({"label": label, "search": search, "roles": [role]})


def _expected_configs(global_label, selector_label):
    configs = []
    for label, search, role in heldout.FIXED_CONFIGS:
        _add_config(configs, label, search, role)
    if selector_label not in heldout.SELECTOR_LABELS:
        raise AnalysisError("selector-family winner is not eligible")
    _add_config(
        configs,
        selector_label,
        heldout.PILOT_SEARCHES[selector_label],
        "pilot-selector-family-winner",
    )
    matched = heldout.BATCHED_SELECTOR_BASE.get(selector_label)
    if matched is not None:
        _add_config(
            configs,
            matched,
            heldout.PILOT_SEARCHES[matched],
            "matched-same-k-unbatched-ablation",
        )
    if global_label not in {item["label"] for item in configs}:
        raise AnalysisError("global winner is absent from carried configurations")
    _add_config(
        configs,
        global_label,
        heldout.PILOT_SEARCHES[global_label],
        "pilot-global-winner",
    )
    expected = 8 if matched is not None else 7
    if len(configs) != expected:
        raise AnalysisError("carried matrix is not exactly 7/8 configurations")
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

    add(PRIMARY_COMPARISON, selector_label, CEGAR, "primary-selector-contrast")
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


def _layout(run_count):
    if run_count not in EXPECTED_RUN_COUNTS:
        raise AnalysisError("full matrix is not a 9639/11016-cell layout")
    per = EXPECTED_RUNS_PER_ARRAY_TASK[run_count]
    full_groups, partial_runs = divmod(run_count, per)
    result = {
        "raw_runs": run_count,
        "array_tasks": EXPECTED_ARRAY_TASKS[run_count],
        "runs_per_array_task": per,
        "array_task_run_distribution": {
            "full_array_tasks": full_groups,
            "full_runs_per_array_task": per,
            "partial_array_tasks": int(partial_runs != 0),
            "partial_runs": partial_runs,
        },
        "scheduler_time_limit_seconds": FULL_SCHEDULER_TIME_LIMIT_SECONDS[
            run_count
        ],
        "wrapper_allowance_seconds_per_run": 60,
    }
    if full_groups + int(partial_runs != 0) != result["array_tasks"]:
        raise AnalysisError("full array layout arithmetic changed")
    return result


def _heldout_layout(config_count):
    run_count = 92 * config_count
    if run_count not in (644, 736):
        raise AnalysisError("held-out carry-forward is not a 644/736-cell matrix")
    return {
        "raw_runs": run_count,
        "array_tasks": run_count,
        "runs_per_array_task": 1,
        "scheduler_time_limit_seconds": 600,
    }


def validate_selection_artifact(artifact):
    """Validate v3 and independently reconstruct the carried full matrix."""
    try:
        heldout_contract = heldout.validate_selection_artifact(copy.deepcopy(artifact))
    except (
        heldout.AnalysisError,
        RuntimeError,
        TypeError,
        ValueError,
        KeyError,
        IndexError,
        StopIteration,
    ) as err:
        raise AnalysisError("invalid selection artifact: {}".format(err)) from err

    global_label = heldout_contract["global_winner"]
    selector_label = heldout_contract["selector_winner"]
    configs, matched = _expected_configs(global_label, selector_label)
    comparisons = _expected_comparisons(global_label, selector_label, matched)
    option_records = [
        {"label": item["label"], "search": item["search"]} for item in configs
    ]
    matrix_digest = sha256_json(option_records)
    comparisons_digest = sha256_json(comparisons)
    if canonical_json(configs) != canonical_json(artifact["validation"]["configs"]):
        raise AnalysisError("artifact configs differ from independent reconstruction")
    if canonical_json(comparisons) != canonical_json(
        artifact["validation"]["comparisons"]
    ):
        raise AnalysisError(
            "artifact comparisons differ from independent reconstruction"
        )
    if (
        matrix_digest != artifact["validation"]["option_matrix_sha256"]
        or matrix_digest != heldout_contract["option_matrix_sha256"]
        or comparisons_digest != artifact["validation"]["comparisons_sha256"]
        or comparisons_digest != heldout_contract["comparisons_sha256"]
    ):
        raise AnalysisError("artifact carried matrix/comparison digest changed")
    if matched != heldout_contract["matched_unbatched"]:
        raise AnalysisError("artifact same-K ablation identity changed")

    config_pairs = [(item["label"], item["search"]) for item in configs]
    run_count = EXPECTED_TASKS * len(configs)
    if run_count not in EXPECTED_RUN_COUNTS:
        raise AnalysisError("full matrix run count changed")
    try:
        runner_matrix = full_runner.validate_selection_artifact(
            copy.deepcopy(artifact)
        )
    except (RuntimeError, TypeError, ValueError, KeyError, IndexError) as err:
        raise AnalysisError("full runner rejects selection artifact: {}".format(err)) from err
    expected_runner = {
        "configs": config_pairs,
        "config_records": configs,
        "matrix_digest": matrix_digest,
        "comparisons": comparisons,
        "comparisons_digest": comparisons_digest,
        "matched_unbatched": matched,
        "heldout_run_count": 92 * len(configs),
        "heldout_materialized_pddl_protocol": heldout_contract[
            "materialized_pddl_protocol"
        ],
        "heldout_materialized_pddl_files": heldout_contract[
            "materialized_pddl_files"
        ],
        "heldout_materialized_pddl_bytes": heldout_contract[
            "materialized_pddl_bytes"
        ],
        "heldout_pddl_bytes_per_config": heldout_contract[
            "pddl_bytes_per_config"
        ],
        "heldout_unique_pddl_source_files": heldout_contract[
            "unique_pddl_source_files"
        ],
        "heldout_unique_pddl_source_bytes": heldout_contract[
            "unique_pddl_source_bytes"
        ],
        "run_count": run_count,
        "layout": _layout(run_count),
    }
    for key, expected in expected_runner.items():
        if canonical_json(runner_matrix.get(key)) != canonical_json(expected):
            raise AnalysisError("full runner/analyzer {} differs".format(key))
    if canonical_json(runner_matrix["heldout_layout"]) != canonical_json(
        _heldout_layout(len(configs))
    ):
        raise AnalysisError("full runner/analyzer held-out layout differs")

    return {
        "global_winner": global_label,
        "selector_winner": selector_label,
        "matched_unbatched": matched,
        "configs": config_pairs,
        "config_records": configs,
        "comparisons": comparisons,
        "option_matrix_sha256": matrix_digest,
        "comparisons_sha256": comparisons_digest,
        "pilot_properties_sha256": heldout_contract[
            "pilot_properties_sha256"
        ],
        "heldout_run_count": 92 * len(configs),
        "heldout_layout": _heldout_layout(len(configs)),
        "heldout_materialized_pddl_protocol": heldout_contract[
            "materialized_pddl_protocol"
        ],
        "heldout_materialized_pddl_files": heldout_contract[
            "materialized_pddl_files"
        ],
        "heldout_materialized_pddl_bytes": heldout_contract[
            "materialized_pddl_bytes"
        ],
        "heldout_pddl_bytes_per_config": heldout_contract[
            "pddl_bytes_per_config"
        ],
        "heldout_unique_pddl_source_files": heldout_contract[
            "unique_pddl_source_files"
        ],
        "heldout_unique_pddl_source_bytes": heldout_contract[
            "unique_pddl_source_bytes"
        ],
        "run_count": run_count,
        "layout": _layout(run_count),
        "heldout_contract": heldout_contract,
    }


def expected_analysis_predeclaration(contract):
    labels = [label for label, _ in contract["configs"]]
    return {
        "protocol": ANALYSIS_PROTOCOL,
        "analysis_role": "descriptive-frozen-supported-population-census",
        "primary_analysis": (
            "descriptive-census-of-all-1377-frozen-supported-tasks-and-all-"
            "carried-configs/v1"
        ),
        "population_inference": "fixed-population-census-no-confidence-interval",
        "rerank_on_full_population": False,
        "config_order": labels,
        "config_order_sha256": sha256_json(labels),
        "carried_comparisons": copy.deepcopy(contract["comparisons"]),
        "carried_comparisons_sha256": contract["comparisons_sha256"],
        "sole_predeclared_sensitivity": {
            "name": "selector-vs-pdb-cegar-screen-excluded",
            "comparison": PRIMARY_COMPARISON,
            "estimand": PRIMARY_ESTIMAND,
            "task_subset": "full-supported-population-minus-50-screen-tasks",
            "task_count": EXPECTED_SCREEN_EXCLUDED_TASKS,
            "domain_count": EXPECTED_SCREEN_EXCLUDED_DOMAINS,
            "task_manifest_sha256": (
                EXPECTED_SCREEN_EXCLUDED_TASK_MANIFEST_SHA256
            ),
            "task_sources_sha256": (
                EXPECTED_SCREEN_EXCLUDED_TASK_SOURCES_SHA256
            ),
            "called_unseen": False,
            "includes_all_92_heldout_tasks": True,
            "confidence_interval": None,
        },
        "development_overlap_disclosure": {
            "full_census_includes_screen_tasks": 50,
            "full_census_includes_heldout_tasks": 92,
            "full_census_called_unseen": False,
            "heldout_excluded_sensitivity_predeclared": False,
        },
        "summaries": [
            "overall-config-coverage-count-and-rate",
            "per-domain-config-coverage-count-and-rate",
            "micro-par2-600s",
            "carried-comparison-discordant-wins-losses",
            "carried-comparison-jointly-solved-runtime-ratio",
            "certified-construction-time-and-fallback-incidence",
            "certified-image-time-calls-and-amortization",
            "certified-exact-cofactor-width-and-selector-effort",
        ],
        "par2_unsolved_seconds": PAR2_UNSOLVED_SECONDS,
        "denominator_policy": {
            "coverage": "all-frozen-supported-cells-for-each-config",
            "par2": "all-frozen-supported-cells-for-each-config",
            "runtime": (
                "jointly-solved-cells-with-certified-runtime; report exact "
                "numerator-and-denominator"
            ),
            "construction": (
                "cells-with-protocol-certified-construction-record; report "
                "exact numerator-and-denominator"
            ),
            "image": (
                "cells-with-complete-certified-image-metrics; report exact "
                "numerator-and-denominator"
            ),
            "cofactor_width": (
                "cells-with-certified-exact-width-observation; report exact "
                "numerator-and-denominator"
            ),
            "selector_effort": (
                "cells-with-certified-complete-selector-trace; report exact "
                "numerator-and-denominator"
            ),
        },
        "completion_policy": copy.deepcopy(FULL_COMPLETION_POLICY),
    }


def _array_assignment(run_count):
    layout = _layout(run_count)
    groups = list(range(1, layout["array_tasks"] + 1))

    def key(group_id):
        payload = "{}\0{}\0{}".format(
            "symbolic-search-heuristics/arrhenius-task-order/v1",
            layout["array_tasks"],
            group_id,
        )
        return hashlib.sha256(payload.encode("utf-8")).digest(), group_id

    groups.sort(key=key)
    digest = sha256_json(groups)
    if digest != EXPECTED_ARRAY_ASSIGNMENT_SHA256[run_count]:
        raise AnalysisError("full array-assignment digest changed")
    final_group = layout["array_tasks"]
    slurm_id = groups.index(final_group) + 1
    if slurm_id != EXPECTED_FINAL_LOGICAL_GROUP_SLURM_ID[run_count]:
        raise AnalysisError("final logical-group Slurm identity changed")
    return {
        "protocol": (
            "sha256(seed-nul-array-count-nul-array-id)-sort;"
            "ascending-run-id-within-array-task/v1"
        ),
        "slurm_id_to_logical_group_sha256": digest,
        "final_logical_group": final_group,
        "final_logical_group_slurm_id": slurm_id,
        "final_logical_group_runs": (
            layout["array_task_run_distribution"]["partial_runs"]
            or layout["runs_per_array_task"]
        ),
    }


def expected_protocol_metadata(contract, artifact_sha256, protocol_revision):
    run_count = contract["run_count"]
    layout = contract["layout"]
    return {
        "planner_revision": PLANNER_REVISION,
        "protocol_revision": protocol_revision,
        "planner_revision_is_protocol_ancestor": True,
        "planner_build_options": ["release_no_lp"],
        "planner_build_config": "release_no_lp",
        "planner_binary_sha256": CACHE_BINARY_SHA256,
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
        "outcome_reconciliation_protocol": (
            heldout.OUTCOME_RECONCILIATION_PROTOCOL
        ),
        "cofactor_width_property": "cofactor_width",
        "cofactor_width_parser_protocol": (
            "run.log/unique-wbh-heuristic-cofactor-width/v1"
        ),
        "metrics_validation_protocol": heldout.METRICS_VALIDATION_PROTOCOL,
        "initial_dead_construction_logging_protocol": (
            INITIAL_DEAD_CONSTRUCTION_LOGGING_PROTOCOL
        ),
        "python_version": EXPECTED_PYTHON_VERSION,
        "lab_version": EXPECTED_LAB_VERSION,
        "required_lab_version": EXPECTED_LAB_VERSION,
        "task_order_seed": "symbolic-search-heuristics/arrhenius-task-order/v1",
        "task_order_method": (
            "sha256(seed-nul-array-count-nul-array-id)-sort;"
            "ascending-run-id-within-array-task/v1"
        ),
        "driver_time_limit": "300s",
        "driver_memory_limit": "8G",
        "planner_limit_basis": "aggregate-process-cpu",
        "per_cell_wall_limit_enforced": False,
        "outer_per_cell_watchdog": False,
        "scheduler_environment": "arrhenius-slurm",
        "scheduler_cluster": "arrhenius",
        "scheduler_cpu_model": "AMD EPYC 9755 128-Core Processor",
        "scheduler_partition": "cpu",
        "scheduler_qos": "normal",
        "scheduler_account": "naiss2025-5-561-cpu",
        "scheduler_time_limit_per_task": FULL_SCHEDULER_TIME_LIMITS[run_count],
        "scheduler_memory_per_cpu": "9G",
        "scheduler_cpus_per_task": 1,
        "scheduler_array_task_throttle": 5,
        "scheduler_max_array_tasks": 1000,
        "scheduler_array_tasks": layout["array_tasks"],
        "scheduler_runs_per_array_task": layout["runs_per_array_task"],
        "scheduler_wrapper_allowance_seconds_per_run": 60,
        "scheduler_envelope_protocol": SCHEDULER_ENVELOPE_PROTOCOL,
        "scheduler_timeout_invalidates_census": True,
        "scheduler_envelope_is_wall_worst_case_guarantee": False,
        "declared_run_count": run_count,
        "repetitions": 1,
        "protocol": FULL_PROTOCOL,
        "analysis_protocol": ANALYSIS_PROTOCOL,
        "matrix_carry_forward_protocol": MATRIX_CARRY_FORWARD_PROTOCOL,
        "heldout_outcomes_consumed": False,
        "selection_artifact_schema": ARTIFACT_SCHEMA,
        "selection_artifact_sha256": artifact_sha256,
        "selection_rule": heldout.SELECTION_RULE,
        "pilot_protocol": heldout.PILOT_PROTOCOL,
        "pilot_protocol_revision": PILOT_PROTOCOL_REVISION,
        "pilot_planner_revision": PILOT_PLANNER_REVISION,
        "pilot_planner_binary_sha256": PILOT_PLANNER_BINARY_SHA256,
        "pilot_planner_preprocess_sha256": (
            PILOT_PLANNER_PREPROCESS_SHA256
        ),
        "pilot_properties_canonical_sha256": contract[
            "pilot_properties_sha256"
        ],
        "pilot_option_matrix_sha256": heldout.PILOT_OPTION_MATRIX_SHA256,
        "pilot_selector_configs_sha256": heldout.PILOT_SELECTOR_CONFIGS_SHA256,
        "selector_eligibility_sha256": heldout.SELECTOR_ELIGIBILITY_SHA256,
        "pdb_selector_parser_protocol": heldout.SELECTOR_PARSER_PROTOCOL,
        "selector_pool_protocol": heldout.SELECTOR_POOL_PROTOCOL,
        "selector_score_version": heldout.SELECTOR_SCORE_VERSION,
        "selector_source_order": list(heldout.SELECTOR_SOURCES),
        "global_winner": contract["global_winner"],
        "selector_family_winner": contract["selector_winner"],
        "matched_same_k_unbatched": contract["matched_unbatched"],
        "heldout_protocol": heldout.VALIDATION_PROTOCOL,
        "heldout_initial_dead_construction_logging_protocol": (
            heldout.INITIAL_DEAD_CONSTRUCTION_LOGGING_PROTOCOL
        ),
        "heldout_task_manifest_sha256": heldout.MANIFEST_SHA256,
        "heldout_task_count": heldout.EXPECTED_TASKS,
        "heldout_run_count": contract["heldout_run_count"],
        "heldout_array_layout": copy.deepcopy(contract["heldout_layout"]),
        "heldout_materialized_pddl_protocol": contract[
            "heldout_materialized_pddl_protocol"
        ],
        "heldout_materialized_pddl_files": contract[
            "heldout_materialized_pddl_files"
        ],
        "heldout_materialized_pddl_bytes": contract[
            "heldout_materialized_pddl_bytes"
        ],
        "heldout_pddl_bytes_per_config": contract[
            "heldout_pddl_bytes_per_config"
        ],
        "heldout_unique_pddl_source_files": contract[
            "heldout_unique_pddl_source_files"
        ],
        "heldout_unique_pddl_source_bytes": contract[
            "heldout_unique_pddl_source_bytes"
        ],
        "task_selection_protocol": TASK_SELECTION_PROTOCOL,
        "task_manifest": "suite_wbh_operator_costs.json#supported",
        "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
        "task_count": EXPECTED_TASKS,
        "domain_count": EXPECTED_DOMAINS,
        "domain_sequence_sha256": EXPECTED_DOMAIN_SEQUENCE_SHA256,
        "domain_task_counts_sha256": EXPECTED_DOMAIN_TASK_COUNTS_SHA256,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
        "screen_excluded_task_count": EXPECTED_SCREEN_EXCLUDED_TASKS,
        "screen_excluded_domain_count": EXPECTED_SCREEN_EXCLUDED_DOMAINS,
        "screen_excluded_task_manifest_sha256": (
            EXPECTED_SCREEN_EXCLUDED_TASK_MANIFEST_SHA256
        ),
        "screen_excluded_task_sources_sha256": (
            EXPECTED_SCREEN_EXCLUDED_TASK_SOURCES_SHA256
        ),
        "fixed_configs_sha256": heldout.FIXED_VALIDATION_CONFIGS_SHA256,
        "config_count": len(contract["configs"]),
        "option_matrix_sha256": contract["option_matrix_sha256"],
        "config_roles": copy.deepcopy(contract["config_records"]),
        "predeclared_comparisons": copy.deepcopy(contract["comparisons"]),
        "predeclared_comparisons_sha256": contract["comparisons_sha256"],
        "analysis_predeclaration": expected_analysis_predeclaration(contract),
        "completion_policy": copy.deepcopy(FULL_COMPLETION_POLICY),
        "completion_marker_name": FULL_COMPLETION_MARKER,
        "completion_marker_schema": FULL_COMPLETION_MARKER_SCHEMA,
        "completion_marker_protocol": FULL_COMPLETION_MARKER_PROTOCOL,
        "restart_count_file": FULL_RESTART_COUNT_FILE,
        "dynamic_output_recovery": copy.deepcopy(FULL_DYNAMIC_OUTPUT_POLICY),
        "materialized_pddl_protocol": MATERIALIZED_PDDL_PROTOCOL,
        "materialized_pddl_files": EXPECTED_MATERIALIZED_PDDL_FILES[run_count],
        "materialized_pddl_bytes": EXPECTED_MATERIALIZED_PDDL_BYTES[run_count],
        "pddl_bytes_per_config": EXPECTED_PDDL_BYTES_PER_CONFIG,
        "unique_pddl_source_files": EXPECTED_UNIQUE_PDDL_SOURCE_FILES,
        "unique_pddl_source_bytes": EXPECTED_UNIQUE_PDDL_SOURCE_BYTES,
        "scheduler_requeue_requested": True,
        "scheduler_open_mode": "append",
        "scheduler_requeue_scope": (
            "eligible-node-failure-preemption-admin-events-only;"
            "timeout-cancel-oom-and-arbitrary-exit-remain-fail-closed"
        ),
        "array_task_run_distribution": copy.deepcopy(
            layout["array_task_run_distribution"]
        ),
        "array_assignment": _array_assignment(run_count),
        "prospective_start_job_sha256": EXPECTED_PROSPECTIVE_JOB_SHA256[
            run_count
        ],
        "planner_preprocess_sha256": CACHE_PREPROCESS_SHA256,
        "experiment_data_directory": "data/exp_arrhenius_selector_full",
        "benchmark_revision": BENCHMARK_REVISION,
        "benchmark_repository": BENCHMARK_REPOSITORY,
    }


def validate_runner_contract(
    contract=None,
    expected_artifact_sha256=None,
    *,
    check_reviewed_pins=True,
):
    source_digest = _sha256_file(full_runner.__file__)
    exact = {
        "full protocol": (full_runner.PROTOCOL, FULL_PROTOCOL),
        "analysis protocol": (full_runner.FULL_ANALYSIS_PROTOCOL, ANALYSIS_PROTOCOL),
        "artifact schema": (full_runner.ARTIFACT_SCHEMA, ARTIFACT_SCHEMA),
        "matrix carry-forward protocol": (
            full_runner.MATRIX_CARRY_FORWARD_PROTOCOL,
            MATRIX_CARRY_FORWARD_PROTOCOL,
        ),
        "task-selection protocol": (
            full_runner.TASK_SELECTION_PROTOCOL,
            TASK_SELECTION_PROTOCOL,
        ),
        "scheduler-envelope protocol": (
            full_runner.SCHEDULER_ENVELOPE_PROTOCOL,
            SCHEDULER_ENVELOPE_PROTOCOL,
        ),
        "planner revision": (full_runner.PLANNER_REVISION, PLANNER_REVISION),
        "pilot planner revision": (
            full_runner.PILOT_PLANNER_REVISION,
            PILOT_PLANNER_REVISION,
        ),
        "held-out pilot planner revision": (
            heldout.PILOT_PLANNER_REVISION,
            PILOT_PLANNER_REVISION,
        ),
        "pilot revision": (
            full_runner.PILOT_PROTOCOL_REVISION,
            PILOT_PROTOCOL_REVISION,
        ),
        "binary digest": (full_runner.CACHE_BINARY_SHA256, CACHE_BINARY_SHA256),
        "pilot binary digest": (
            full_runner.PILOT_PLANNER_BINARY_SHA256,
            PILOT_PLANNER_BINARY_SHA256,
        ),
        "held-out pilot binary digest": (
            heldout.PILOT_PLANNER_BINARY_SHA256,
            PILOT_PLANNER_BINARY_SHA256,
        ),
        "preprocess digest": (
            full_runner.CACHE_PREPROCESS_SHA256,
            CACHE_PREPROCESS_SHA256,
        ),
        "pilot preprocess digest": (
            full_runner.PILOT_PLANNER_PREPROCESS_SHA256,
            PILOT_PLANNER_PREPROCESS_SHA256,
        ),
        "held-out pilot preprocess digest": (
            heldout.PILOT_PLANNER_PREPROCESS_SHA256,
            PILOT_PLANNER_PREPROCESS_SHA256,
        ),
        "initial-dead construction logging protocol": (
            full_runner.INITIAL_DEAD_CONSTRUCTION_LOGGING_PROTOCOL,
            INITIAL_DEAD_CONSTRUCTION_LOGGING_PROTOCOL,
        ),
        "held-out initial-dead construction logging protocol": (
            heldout.INITIAL_DEAD_CONSTRUCTION_LOGGING_PROTOCOL,
            INITIAL_DEAD_CONSTRUCTION_LOGGING_PROTOCOL,
        ),
        "benchmark revision": (
            full_runner.BENCHMARK_REVISION,
            BENCHMARK_REVISION,
        ),
        "task count": (full_runner.EXPECTED_TASKS, EXPECTED_TASKS),
        "domain count": (full_runner.EXPECTED_DOMAINS, EXPECTED_DOMAINS),
        "task digest": (
            full_runner.EXPECTED_TASK_MANIFEST_SHA256,
            EXPECTED_TASK_MANIFEST_SHA256,
        ),
        "domain sequence digest": (
            full_runner.EXPECTED_DOMAIN_SEQUENCE_SHA256,
            EXPECTED_DOMAIN_SEQUENCE_SHA256,
        ),
        "domain counts digest": (
            full_runner.EXPECTED_DOMAIN_TASK_COUNTS_SHA256,
            EXPECTED_DOMAIN_TASK_COUNTS_SHA256,
        ),
        "task-source digest": (
            full_runner.EXPECTED_TASK_SOURCES_SHA256,
            EXPECTED_TASK_SOURCES_SHA256,
        ),
        "source manifest digest": (
            full_runner.EXPECTED_SOURCE_MANIFEST_SHA256,
            EXPECTED_SOURCE_MANIFEST_SHA256,
        ),
        "completion attributes": (
            tuple(full_runner.FULL_COMPLETION_ATTRIBUTES),
            FULL_COMPLETION_ATTRIBUTES,
        ),
        "completion policy": (
            full_runner.FULL_COMPLETION_POLICY,
            FULL_COMPLETION_POLICY,
        ),
        "dynamic output policy": (
            full_runner.FULL_DYNAMIC_OUTPUT_POLICY,
            FULL_DYNAMIC_OUTPUT_POLICY,
        ),
        "prospective job digests": (
            full_runner.EXPECTED_PROSPECTIVE_JOB_SHA256,
            EXPECTED_PROSPECTIVE_JOB_SHA256,
        ),
    }
    errors = [
        "{}={!r}, expected {!r}".format(label, actual, expected)
        for label, (actual, expected) in exact.items()
        if not _same(actual, expected)
    ]
    if check_reviewed_pins:
        for label, value in (
            ("runner source SHA-256", FULL_RUNNER_SOURCE_SHA256),
            ("planner binary SHA-256", CACHE_BINARY_SHA256),
            ("preprocess SHA-256", CACHE_PREPROCESS_SHA256),
        ):
            try:
                _require_sha256(value, label)
            except AnalysisError as err:
                errors.append(str(err))
        if FULL_RUNNER_SOURCE_SHA256 is not None and (
            source_digest != FULL_RUNNER_SOURCE_SHA256
        ):
            errors.append(
                "runner source SHA-256={!r}, expected {!r}".format(
                    source_digest, FULL_RUNNER_SOURCE_SHA256
                )
            )
        for run_count, digest in EXPECTED_PROSPECTIVE_JOB_SHA256.items():
            try:
                _require_sha256(
                    digest,
                    "prospective job digest for {} runs".format(run_count),
                )
            except AnalysisError as err:
                errors.append(str(err))
    if expected_artifact_sha256 is not None and (
        full_runner.EXPECTED_SELECTION_ARTIFACT_SHA256
        != expected_artifact_sha256
    ):
        errors.append(
            "runner selection-artifact pin={!r}, expected {!r}".format(
                full_runner.EXPECTED_SELECTION_ARTIFACT_SHA256,
                expected_artifact_sha256,
            )
        )
    if contract is not None:
        runner_predeclaration = full_runner.expected_full_analysis_contract(
            {
                "configs": contract["configs"],
                "comparisons": contract["comparisons"],
                "comparisons_digest": contract["comparisons_sha256"],
            }
        )
        expected = expected_analysis_predeclaration(contract)
        if canonical_json(runner_predeclaration) != canonical_json(expected):
            errors.append("full analysis predeclaration changed")
    if errors:
        raise AnalysisError("runner/analyzer contract mismatch: " + "; ".join(errors))


def require_reviewed_pins(
    artifact_sha256,
    *,
    expected_artifact_sha256=EXPECTED_SELECTION_ARTIFACT_SHA256,
    protocol_revision=EXPECTED_FULL_PROTOCOL_REVISION,
    planner_revision=PLANNER_REVISION,
    pilot_protocol_revision=PILOT_PROTOCOL_REVISION,
    pilot_planner_revision=PILOT_PLANNER_REVISION,
    pilot_binary_sha256=PILOT_PLANNER_BINARY_SHA256,
    pilot_preprocess_sha256=PILOT_PLANNER_PREPROCESS_SHA256,
    binary_sha256=CACHE_BINARY_SHA256,
    preprocess_sha256=CACHE_PREPROCESS_SHA256,
    cache_name_suffix=CACHE_NAME_SUFFIX,
    runner_source_sha256=FULL_RUNNER_SOURCE_SHA256,
    job_sha256=EXPECTED_PROSPECTIVE_JOB_SHA256,
):
    _require_sha256(artifact_sha256, "selection artifact raw digest")
    if expected_artifact_sha256 is None:
        raise AnalysisError(
            "EXPECTED_SELECTION_ARTIFACT_SHA256 is unset; review and pin the "
            "exact screen artifact bytes before ordinary analysis"
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
            "EXPECTED_FULL_PROTOCOL_REVISION is unset; pin the clean full "
            "launch revision before ordinary analysis"
        )
    _require_revision(protocol_revision, "full protocol revision")
    _require_revision(planner_revision, "downstream planner revision")
    _require_revision(pilot_protocol_revision, "P4 screen protocol revision")
    _require_revision(pilot_planner_revision, "P4 pilot planner revision")
    _require_sha256(pilot_binary_sha256, "P4 pilot planner digest")
    _require_sha256(pilot_preprocess_sha256, "P4 pilot preprocess digest")
    _require_sha256(binary_sha256, "downstream cached planner digest")
    _require_sha256(preprocess_sha256, "downstream cached preprocess digest")
    _require_sha256(runner_source_sha256, "downstream full-runner source digest")
    if (
        not isinstance(cache_name_suffix, str)
        or not re.fullmatch(r"_[0-9a-f]{8}", cache_name_suffix)
    ):
        raise AnalysisError("downstream cache-name suffix is unset")
    if not isinstance(job_sha256, dict):
        raise AnalysisError("downstream full job-digest mapping is unset")
    for run_count in (EXPECTED_UNBATCHED_RUNS, EXPECTED_BATCHED_RUNS):
        digest = job_sha256.get(run_count)
        _require_sha256(
            digest, "downstream full job digest for {} runs".format(run_count)
        )
    return protocol_revision


def expected_component_options(search):
    return heldout.expected_component_options(search)


def _run_relative_path(run_id):
    lower = ((run_id - 1) // 100) * 100 + 1
    upper = ((run_id + 99) // 100) * 100
    return "runs-{:05d}-{:05d}/{:05d}".format(lower, upper, run_id)


def _cell_label(label, task):
    return "{} {}:{}".format(label, task[0], task[1])


def _append(errors, prefix, message):
    errors.append("{}: {}".format(prefix, message))


def _marker_sha256(run_id, restart_count):
    raw = (
        "schema={}\nrun_id={}\ncompletion_slurm_restart_count={}\n"
        "wrapper_exit_code=0\n".format(
            FULL_COMPLETION_MARKER_SCHEMA, run_id, restart_count
        )
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _validate_completion(record, run_id, prefix, errors):
    exact = {
        "full_completion_marker_present": True,
        "full_completion_marker_valid": True,
        "full_completion_marker_schema": FULL_COMPLETION_MARKER_SCHEMA,
        "full_completion_marker_protocol": FULL_COMPLETION_MARKER_PROTOCOL,
        "full_wrapper_run_id": run_id,
        "full_wrapper_exit_code": 0,
    }
    for field, expected in exact.items():
        if field not in record or not _same(record.get(field), expected):
            _append(
                errors,
                prefix,
                "{}={!r}, expected {!r}".format(field, record.get(field), expected),
            )
    restart = record.get("full_completion_slurm_restart_count")
    if type(restart) is not int or restart < 0:
        _append(errors, prefix, "completion restart count must be nonnegative integer")
        return
    digest = record.get("full_completion_marker_sha256")
    expected_digest = _marker_sha256(run_id, restart)
    if digest != expected_digest or type(digest) is not str:
        _append(errors, prefix, "completion marker SHA-256 changed")

    archive_count = record.get("full_partial_archive_count")
    archive_ids = record.get("full_partial_archive_restart_ids")
    archived_restarts = record.get("full_archived_slurm_restart_counts")
    execution_count = record.get("full_descriptive_cell_execution_count")
    if type(archive_count) is not int or archive_count < 0:
        _append(errors, prefix, "partial archive count must be nonnegative integer")
        return
    if not isinstance(archive_ids, list) or any(
        type(value) is not int for value in archive_ids
    ):
        _append(errors, prefix, "partial archive restart IDs must be an integer list")
        return
    if not isinstance(archived_restarts, list) or any(
        type(value) is not int for value in archived_restarts
    ):
        _append(errors, prefix, "archived restart counts must be an integer list")
        return
    if len(archive_ids) != archive_count or len(archived_restarts) != archive_count:
        _append(errors, prefix, "archive count/list lengths disagree")
    if archive_ids != sorted(set(archive_ids)) or any(
        value <= 0 or value > restart for value in archive_ids
    ):
        _append(errors, prefix, "partial archive restart IDs are noncanonical")
    if archived_restarts != sorted(set(archived_restarts)) or any(
        value < 0 for value in archived_restarts
    ):
        _append(errors, prefix, "archived restart counts are noncanonical")
    if len(archive_ids) == len(archived_restarts) and any(
        prior >= archive_id
        for prior, archive_id in zip(archived_restarts, archive_ids)
    ):
        _append(errors, prefix, "archive suffix does not follow prior restart")
    if execution_count != archive_count + 1 or type(execution_count) is not int:
        _append(errors, prefix, "descriptive cell execution count changed")


def validate_records(records, tasks, contract, artifact_sha256, protocol_revision):
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
            label, task = heldout.analyzer_utils.identity(record)
        except heldout.analyzer_utils.AnalysisError as err:
            errors.append(str(err))
            continue
        if label not in label_set:
            errors.append("unexpected algorithm {}".format(label))
            continue
        if task not in task_set:
            errors.append("record outside full census {}:{}".format(*task))
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

    static = expected_protocol_metadata(contract, artifact_sha256, protocol_revision)
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
    repos = set()

    for config_index, label in enumerate(labels):
        for task_index, task in enumerate(tasks):
            record = matrix.get((label, task))
            if record is None:
                continue
            run_id = config_index * len(tasks) + task_index + 1
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
            if record.get("experiment_name") != "exp_arrhenius_selector_full":
                _append(errors, prefix, "experiment_name changed")
            if record.get("run_dir") != _run_relative_path(run_id):
                _append(errors, prefix, "run_dir/run-id mapping changed")
            for field, expected in static.items():
                if field not in record or not _same(record.get(field), expected):
                    _append(
                        errors,
                        prefix,
                        "{}={!r}, expected {!r}".format(
                            field, record.get(field), expected
                        ),
                    )
            for field, values in (
                ("benchmark_worktree", benchmark_worktrees),
                ("repo", repos),
            ):
                value = record.get(field)
                if not isinstance(value, str) or not value or not Path(value).is_absolute():
                    _append(errors, prefix, "{} is not absolute".format(field))
                else:
                    values.add(value)

            _validate_completion(record, run_id, prefix, errors)
            heldout.pilot_analyzer._validate_outcome(record, prefix, errors)
            heldout._validate_metric_certification(record, prefix, errors)
            pool_hash = heldout._validate_heuristic(
                record, label, searches[label], prefix, errors
            )
            if pool_hash is not None:
                pool_hashes_by_task[task][label] = pool_hash
                if record.get("pdb_selector_pool_sha256") != pool_hash:
                    _append(errors, prefix, "selector pool hash disagrees")
            if record.get("coverage") == 1 and type(
                record.get("solution_cost")
            ) is int:
                costs_by_task[task].append((label, record["solution_cost"]))
            if record.get("coverage") == 0 and record.get("unsolvable") == 1:
                unsolvable_by_task[task].append(label)

    if len(benchmark_worktrees) != 1:
        errors.append("records do not have one consistent absolute benchmark worktree")
    if len(repos) != 1:
        errors.append("records do not have one consistent absolute planner repo")
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
            errors.append("solved/proved-unsolvable disagreement on {}:{}".format(*task))
    for task, labelled in sorted(pool_hashes_by_task.items()):
        if len(set(labelled.values())) > 1:
            errors.append("same-task selector pool disagreement on {}:{}".format(*task))
    if errors:
        shown = errors[:60]
        suffix = ""
        if len(errors) > len(shown):
            suffix = "\n... {} more".format(len(errors) - len(shown))
        raise AnalysisError(
            "full census validation failed ({} errors):\n{}{}".format(
                len(errors), "\n".join("- " + item for item in shown), suffix
            )
        )
    return matrix


def logical_properties_sha256(records):
    try:
        return heldout.logical_properties_sha256(records)
    except heldout.AnalysisError as err:
        raise AnalysisError(str(err)) from err


def _summary(values):
    return heldout._summary(values)


def _certification(eligible, observed):
    if type(eligible) is not int or type(observed) is not int:
        raise AnalysisError("certification counts must be exact integers")
    if eligible < 0 or observed < 0 or observed > eligible:
        raise AnalysisError("invalid certified denominator")
    return {
        "certified_cells": observed,
        "eligible_cells": eligible,
        "uncertified_or_unobserved_cells": eligible - observed,
        "rate": observed / eligible if eligible else None,
    }


def _amortized_image_summary(records):
    total_time = math.fsum(float(record["image_time"]) for record in records)
    completed_calls = sum(record["image_calls_completed"] for record in records)
    return {
        "complete_certified_cells": len(records),
        "image_time_seconds": _summary(record["image_time"] for record in records),
        "image_calls_attempted": _summary(
            record["image_calls_attempted"] for record in records
        ),
        "image_calls_completed": _summary(
            record["image_calls_completed"] for record in records
        ),
        "batched_images": _summary(record["batched_images"] for record in records),
        "aggregate_image_time_seconds": total_time,
        "aggregate_completed_image_calls": completed_calls,
        "seconds_per_completed_image_call": (
            total_time / completed_calls if completed_calls else None
        ),
    }


def _selector_effort_summary(records, eligible):
    complete = [
        record
        for record in records
        if record.get("pdb_selector_trace_complete") is True
        and record.get("pdb_selector_trace_certified") is True
    ]
    candidate_counts = []
    source_evaluations = []
    feasible_counts = []
    rejected_counts = []
    selected_sources = Counter()
    for record in complete:
        candidates = record["pdb_selector_candidates"]
        candidate_counts.append(len(candidates))
        source_evaluations.append(sum(len(item["sources"]) for item in candidates))
        feasible = sum(item["feasible"] is True for item in candidates)
        feasible_counts.append(feasible)
        rejected_counts.append(len(candidates) - feasible)
        selected_sources[record["pdb_selected_source"]] += 1
    return {
        "certification": _certification(eligible, len(complete)),
        "candidate_records": _summary(candidate_counts),
        "source_evaluations": _summary(source_evaluations),
        "feasible_candidate_records": _summary(feasible_counts),
        "rejected_candidate_records": _summary(rejected_counts),
        "selected_source_counts": {
            source: selected_sources[source] for source in heldout.SELECTOR_SOURCES
        },
    }


def summarize_config(matrix, tasks, domains, label, search, roles):
    records = [matrix[(label, task)] for task in tasks]
    solved = [record for record in records if record["coverage"] == 1]
    per_domain = []
    for domain in domains:
        domain_tasks = [task for task in tasks if task[0] == domain]
        solved_count = sum(
            matrix[(label, task)]["coverage"] == 1 for task in domain_tasks
        )
        per_domain.append(
            {
                "domain": domain,
                "solved": solved_count,
                "tasks": len(domain_tasks),
                "rate": solved_count / len(domain_tasks),
            }
        )

    construction_eligible = 0 if label == BLIND else len(records)
    construction = [
        record for record in records if "construction_completed" in record
    ]
    image_prefix = [
        record
        for record in records
        if record.get("piece_metrics_certified") is True
        and record.get("metrics_validation_error") is None
        and record.get("wbh_schema_version") == 2
    ]
    image_complete = [
        record
        for record in image_prefix
        if record.get("raw_metrics_complete") is True
    ]
    width_records = [
        record
        for record in records
        if type(record.get("cofactor_width")) is int
    ]
    width_eligible = 0 if label == BLIND else len(records)
    selector_eligible = len(records) if label in heldout.SELECTOR_LABELS else 0
    solved_effort = [record["effort"] for record in solved]
    return {
        "label": label,
        "search": search,
        "roles": list(roles),
        "coverage": {
            "solved": len(solved),
            "tasks": len(tasks),
            "rate": len(solved) / len(tasks),
        },
        "per_domain_coverage": per_domain,
        "micro_par2_seconds": math.fsum(
            heldout._par2(record) for record in records
        )
        / len(records),
        "solved_runtime_seconds": {
            "certification": _certification(len(solved), len(solved)),
            "summary": _summary(record["planner_time"] for record in solved),
        },
        "search_effort_on_solved_cells": {
            "certification": _certification(len(solved), len(solved_effort)),
            "summary": _summary(solved_effort),
        },
        "construction": {
            "certification": _certification(
                construction_eligible, len(construction)
            ),
            "completed": sum(
                record["construction_completed"] is True for record in construction
            ),
            "fallbacks": sum(
                record["construction_completed"] is False for record in construction
            ),
            "time_seconds": _summary(
                record["construction_time"] for record in construction
            ),
        },
        "image": {
            "certified_prefix": _certification(len(records), len(image_prefix)),
            "complete_certified": _certification(
                len(records), len(image_complete)
            ),
            "presearch_empty_cells": sum(
                record.get("planner_exit_code") in heldout.PRESEARCH_EXIT_CODES
                for record in records
            ),
            "prefix_image_time_seconds": _summary(
                record["image_time"] for record in image_prefix
            ),
            "complete_amortization": _amortized_image_summary(image_complete),
        },
        "exact_cofactor_width": {
            "certification": _certification(width_eligible, len(width_records)),
            "summary": _summary(record["cofactor_width"] for record in width_records),
        },
        "selector_effort": _selector_effort_summary(records, selector_eligible),
    }


def _fraction_record(value):
    if not isinstance(value, Fraction):
        value = Fraction(value)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "value": float(value),
    }


def macro_coverage_contrast(matrix, tasks, domains, candidate, reference):
    task_set = set(tasks)
    if len(task_set) != len(tasks):
        raise AnalysisError("macro coverage task subset contains duplicates")
    per_domain = []
    deltas = []
    for domain in domains:
        domain_tasks = [task for task in tasks if task[0] == domain]
        if not domain_tasks:
            raise AnalysisError("macro coverage has an empty frozen domain")
        candidate_solved = sum(
            matrix[(candidate, task)]["coverage"] == 1 for task in domain_tasks
        )
        reference_solved = sum(
            matrix[(reference, task)]["coverage"] == 1 for task in domain_tasks
        )
        delta = Fraction(candidate_solved - reference_solved, len(domain_tasks))
        deltas.append(delta)
        per_domain.append(
            {
                "domain": domain,
                "tasks": len(domain_tasks),
                "candidate_solved": candidate_solved,
                "reference_solved": reference_solved,
                "candidate_minus_reference_rate": _fraction_record(delta),
            }
        )
    estimate = sum(deltas, Fraction(0, 1)) / len(domains)
    candidate_total = sum(matrix[(candidate, task)]["coverage"] for task in tasks)
    reference_total = sum(matrix[(reference, task)]["coverage"] for task in tasks)
    return {
        "comparison": PRIMARY_COMPARISON,
        "candidate": candidate,
        "reference": reference,
        "estimand": PRIMARY_ESTIMAND,
        "domains": len(domains),
        "tasks": len(tasks),
        "estimate": _fraction_record(estimate),
        "confidence_interval": None,
        "p_value": None,
        "micro_coverage": {
            "candidate_solved": candidate_total,
            "reference_solved": reference_total,
            "candidate_minus_reference_tasks": candidate_total - reference_total,
            "candidate_minus_reference_rate": (
                candidate_total - reference_total
            )
            / len(tasks),
        },
        "per_domain": per_domain,
    }


def _completion_slice(records):
    restarts = [record["full_completion_slurm_restart_count"] for record in records]
    archives = [record["full_partial_archive_count"] for record in records]
    executions = [record["full_descriptive_cell_execution_count"] for record in records]
    return {
        "all_cells_marker_present_and_valid": True,
        "cells": len(records),
        "cells_completed_after_nonzero_slurm_restart": sum(value > 0 for value in restarts),
        "slurm_restart_count": _summary(restarts),
        "cells_with_partial_archives": sum(value > 0 for value in archives),
        "partial_archive_count": _summary(archives),
        "total_partial_archives": sum(archives),
        # This shell-derived count measures cell-attempt generations.  A
        # preemption can occur after the restart sentinel and before Python,
        # so it is deliberately not described as a planner invocation count.
        "descriptive_cell_attempt_generation_count": _summary(executions),
        "total_descriptive_cell_attempt_generations": sum(executions),
    }


def completion_summary(records, labels):
    grouped = {label: [] for label in labels}
    for record in records:
        grouped[record["algorithm"]].append(record)
    return {
        "protocol": FULL_COMPLETION_MARKER_PROTOCOL,
        "attempt_count_semantics": (
            "shell-cell-attempt-generations-not-guaranteed-planner-invocations/v1"
        ),
        "global": _completion_slice(records),
        "per_config": [
            {"label": label, **_completion_slice(grouped[label])}
            for label in labels
        ],
    }


def analyze(
    records,
    tasks,
    screen_excluded,
    domains,
    contract,
    artifact_sha256,
    protocol_revision,
):
    matrix = validate_records(
        records, tasks, contract, artifact_sha256, protocol_revision
    )
    sensitivity_identity = _validate_sensitivity_subset(tasks, screen_excluded)
    roles = {item["label"]: item["roles"] for item in contract["config_records"]}
    config_summaries = [
        summarize_config(matrix, tasks, domains, label, search, roles[label])
        for label, search in contract["configs"]
    ]
    if [item["label"] for item in config_summaries] != [
        label for label, _ in contract["configs"]
    ]:
        raise AnalysisError("configuration order was reranked")
    comparisons = [
        heldout.compare(matrix, tasks, declaration)
        for declaration in contract["comparisons"]
    ]
    if [item["name"] for item in comparisons] != [
        item["name"] for item in contract["comparisons"]
    ]:
        raise AnalysisError("carried comparisons were reordered")
    primary_decl = next(
        item for item in contract["comparisons"] if item["name"] == PRIMARY_COMPARISON
    )
    primary = macro_coverage_contrast(
        matrix,
        tasks,
        domains,
        primary_decl["candidate"],
        primary_decl["reference"],
    )
    sensitivity_domains = list(
        dict.fromkeys(domain for domain, _ in screen_excluded)
    )
    sensitivity = macro_coverage_contrast(
        matrix,
        screen_excluded,
        sensitivity_domains,
        primary_decl["candidate"],
        primary_decl["reference"],
    )
    sensitivity.update(
        {
            "name": "selector-vs-pdb-cegar-screen-excluded",
            "task_subset": "full-supported-population-minus-50-screen-tasks",
            "identity": sensitivity_identity,
            "called_unseen": False,
            "includes_all_92_heldout_tasks": True,
            "confidence_interval": None,
            "p_value": None,
        }
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
            "pilot_planner_revision": PILOT_PLANNER_REVISION,
            "pilot_planner_binary_sha256": PILOT_PLANNER_BINARY_SHA256,
            "pilot_planner_preprocess_sha256": (
                PILOT_PLANNER_PREPROCESS_SHA256
            ),
        },
        "execution": {
            "protocol": FULL_PROTOCOL,
            "protocol_revision": protocol_revision,
            "full_runner_source_sha256": FULL_RUNNER_SOURCE_SHA256,
            "planner_revision": PLANNER_REVISION,
            "planner_binary_sha256": CACHE_BINARY_SHA256,
            "planner_preprocess_sha256": CACHE_PREPROCESS_SHA256,
            "initial_dead_construction_logging_protocol": (
                INITIAL_DEAD_CONSTRUCTION_LOGGING_PROTOCOL
            ),
            "benchmark_revision": BENCHMARK_REVISION,
            "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
            "domain_sequence_sha256": EXPECTED_DOMAIN_SEQUENCE_SHA256,
            "domain_task_counts_sha256": EXPECTED_DOMAIN_TASK_COUNTS_SHA256,
            "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
            "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "option_matrix_sha256": contract["option_matrix_sha256"],
            "predeclared_comparisons_sha256": contract["comparisons_sha256"],
            "properties_canonical_sha256": logical_properties_sha256(records),
            "task_count": EXPECTED_TASKS,
            "domain_count": EXPECTED_DOMAINS,
            "config_count": len(contract["configs"]),
            "cell_count": contract["run_count"],
            "array_layout": copy.deepcopy(contract["layout"]),
            "prospective_start_job_sha256": EXPECTED_PROSPECTIVE_JOB_SHA256[
                contract["run_count"]
            ],
        },
        "decision_policy": {
            "analysis_role": "descriptive-fixed-population-census",
            "rerank_on_full_population": False,
            "configuration_order_source": "selection-artifact-v3",
            "comparisons_source": "selection-artifact-v3",
            "population_inference": "none-fixed-population-census",
            "confidence_intervals": None,
            "p_values": None,
        },
        "primary": {
            "status": "descriptive-1377-task-census",
            "selector_vs_cegar_equally_weighted_domain_coverage": primary,
            "configs": config_summaries,
            "carried_comparisons": comparisons,
        },
        "sole_predeclared_sensitivity": sensitivity,
        "completion_and_recovery": completion_summary(
            records, [label for label, _ in contract["configs"]]
        ),
    }
    return json.loads(canonical_json(result))


def _synthetic_completion(run_id):
    if run_id % 101 == 0:
        restart, archive_ids, archived = 2, [1, 2], [0, 1]
    elif run_id % 19 == 0:
        restart, archive_ids, archived = 1, [], []
    else:
        restart, archive_ids, archived = 0, [], []
    return {
        "full_completion_marker_present": True,
        "full_completion_marker_valid": True,
        "full_completion_marker_schema": FULL_COMPLETION_MARKER_SCHEMA,
        "full_completion_marker_protocol": FULL_COMPLETION_MARKER_PROTOCOL,
        "full_completion_marker_sha256": _marker_sha256(run_id, restart),
        "full_wrapper_run_id": run_id,
        "full_wrapper_exit_code": 0,
        "full_completion_slurm_restart_count": restart,
        "full_partial_archive_count": len(archive_ids),
        "full_partial_archive_restart_ids": archive_ids,
        "full_archived_slurm_restart_counts": archived,
        "full_descriptive_cell_execution_count": len(archive_ids) + 1,
    }


def _synthetic_record(
    label,
    search,
    task,
    task_index,
    run_id,
    contract,
    static,
):
    domain, problem = task
    if label == contract["selector_winner"]:
        solved = task_index % 13 != 0
    elif label == CEGAR:
        solved = task_index % 11 != 0
    else:
        solved = task_index % 17 != 0
    record = {
        "_source_key": "synthetic-{}".format(run_id),
        "id": [label, domain, problem],
        "algorithm": label,
        "domain": domain,
        "problem": problem,
        "coverage": int(solved),
        "planner_exit_code": 0 if solved else 23,
        "search_raw_exit_code": 0 if solved else 23,
        "search_effective_exit_code": 0 if solved else 23,
        "outcome_reconciliation_protocol": (
            heldout.OUTCOME_RECONCILIATION_PROTOCOL
        ),
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
        "repo": "/synthetic/symk",
        "experiment_name": "exp_arrhenius_selector_full",
        "run_dir": _run_relative_path(run_id),
        "wbh_log_nonempty": True,
        "raw_metrics_complete": True,
        "piece_metrics_certified": True,
        "wbh_summary_solved": bool(solved),
        "wbh_done_solution_cost": task_index + 1 if solved else None,
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
        **heldout.SCHEMA_V2_CONVENTIONS,
        **static,
        **_synthetic_completion(run_id),
    }
    if solved:
        record.update(
            {
                "solution_cost": task_index + 1,
                "plan_file_cost": task_index + 1,
                "run_log_plan_cost": task_index + 1,
                "planner_time": 1.0 + (task_index % 9) + len(label) / 100.0,
                "effort": 17 + task_index % 5,
            }
        )
    if label == BLIND:
        return record
    fallback = label == MS_CAP32_BUILD60 and task_index % 37 == 0
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
                "value_cap": heldout._expected_ms_value_cap(search),
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
    elif label in heldout.SELECTOR_LABELS:
        heldout.pilot_analyzer._attach_selector_trace(record, label)
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
    global_label = selector_label if selector_label in heldout.BATCHED_SELECTOR_BASE else "ms_cap32"
    artifact = heldout.runner._synthetic_artifact(global_label, selector_label)
    raw = canonical_json(artifact).encode("ascii")
    digest = hashlib.sha256(raw).hexdigest()
    contract = validate_selection_artifact(copy.deepcopy(artifact))
    tasks, screen_excluded, domains = load_and_validate_tasks()
    revision = "0123456789abcdef0123456789abcdef01234567"
    static = expected_protocol_metadata(contract, digest, revision)
    records = []
    for config_index, (label, search) in enumerate(contract["configs"]):
        for task_index, task in enumerate(tasks):
            run_id = config_index * len(tasks) + task_index + 1
            records.append(
                _synthetic_record(
                    label,
                    search,
                    task,
                    task_index,
                    run_id,
                    contract,
                    static,
                )
            )
    return (
        artifact,
        digest,
        contract,
        tasks,
        screen_excluded,
        domains,
        revision,
        records,
    )


def _expect_error(function, fragment):
    try:
        function()
    except (AnalysisError, heldout.AnalysisError) as err:
        if fragment not in str(err):
            raise AssertionError(
                "expected {!r}, got {!r}".format(fragment, str(err))
            ) from err
    else:
        raise AssertionError("expected AnalysisError containing {!r}".format(fragment))


def _mutate_and_expect(records, index, field, value, validate, fragment):
    record = records[index]
    present = field in record
    old = record.get(field)
    record[field] = value
    try:
        _expect_error(validate, fragment)
    finally:
        if present:
            record[field] = old
        else:
            record.pop(field, None)


def _assert_synthetic_macro_pins(result, run_count):
    pin = SYNTHETIC_MACRO_PINS[run_count]
    primary = result["primary"][
        "selector_vs_cegar_equally_weighted_domain_coverage"
    ]
    sensitivity = result["sole_predeclared_sensitivity"]
    if (
        (
            primary["estimate"]["numerator"],
            primary["estimate"]["denominator"],
        )
        != pin["primary_fraction"]
        or (
            sensitivity["estimate"]["numerator"],
            sensitivity["estimate"]["denominator"],
        )
        != pin["sensitivity_fraction"]
    ):
        raise AssertionError("synthetic unequal-domain macro fraction changed")
    digest = sha256_json({"primary": primary, "sensitivity": sensitivity})
    if digest != pin["primary_and_sensitivity_sha256"]:
        raise AssertionError("synthetic primary/sensitivity output digest changed")


def _self_test_loaders():
    if heldout._parse_json_bytes(b'{"a":1}', "synthetic") != {"a": 1}:
        raise AssertionError("strict JSON parser changed")
    try:
        heldout._parse_json_bytes(b'{"a":1,"a":2}', "synthetic")
    except heldout.AnalysisError:
        pass
    else:
        raise AssertionError("duplicate JSON keys were accepted")
    with tempfile.TemporaryDirectory(prefix="full-analysis-loader-") as raw:
        root = Path(raw)
        evaluation = root / "one-eval"
        evaluation.mkdir()
        (evaluation / "properties").write_bytes(b"{}")
        if load_properties(str(root)) != []:
            raise AssertionError("unique evaluation-directory load changed")
        (root / "properties").write_bytes(b"{}")
        _expect_error(lambda: load_properties(str(root)), "contains 2 properties")
        (root / "properties").unlink()
        linked = root / "linked.json"
        linked.symlink_to(evaluation / "properties")
        _expect_error(lambda: load_properties(str(linked)), "must not be a symlink")

        archive_path = root / "properties.tar"
        with tarfile.open(str(archive_path), mode="w") as archive:
            info = tarfile.TarInfo("full-eval/properties")
            payload = b"{}"
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        if load_properties(str(archive_path)) != []:
            raise AssertionError("single-member tar properties load changed")
        duplicate_path = root / "duplicate.tar"
        with tarfile.open(str(duplicate_path), mode="w") as archive:
            for name in ("a/properties", "b/properties"):
                info = tarfile.TarInfo(name)
                payload = b"{}"
                info.size = len(payload)
                archive.addfile(info, io.BytesIO(payload))
        _expect_error(
            lambda: load_properties(str(duplicate_path)),
            "contains 2 regular properties members",
        )


def self_test():
    validate_runner_contract(
        expected_artifact_sha256=None, check_reviewed_pins=False
    )
    _self_test_loaders()

    layouts = []
    case = _synthetic_case("pdb_selector_k32")
    (
        artifact,
        digest,
        contract,
        tasks,
        screen_excluded,
        domains,
        revision,
        records,
    ) = case
    if len(records) != EXPECTED_UNBATCHED_RUNS or contract["run_count"] != EXPECTED_UNBATCHED_RUNS:
        raise AssertionError("synthetic 9639-cell layout changed")
    validate_runner_contract(
        contract, expected_artifact_sha256=None, check_reviewed_pins=False
    )
    result = analyze(
        records,
        tasks,
        screen_excluded,
        domains,
        contract,
        digest,
        revision,
    )
    _assert_synthetic_macro_pins(result, EXPECTED_UNBATCHED_RUNS)
    if result["execution"]["cell_count"] != EXPECTED_UNBATCHED_RUNS:
        raise AssertionError("unbatched census cell count changed")
    if (
        result["selection_artifact"]["pilot_planner_revision"]
        != PILOT_PLANNER_REVISION
        or result["execution"][
            "initial_dead_construction_logging_protocol"
        ]
        != INITIAL_DEAD_CONSTRUCTION_LOGGING_PROTOCOL
    ):
        raise AssertionError("full pilot/downstream provenance split changed")
    if result["decision_policy"]["rerank_on_full_population"] is not False:
        raise AssertionError("full analysis reranked configurations")
    if [item["label"] for item in result["primary"]["configs"]] != [
        label for label, _ in contract["configs"]
    ]:
        raise AssertionError("full output order differs from carried artifact")
    if len(result["primary"]["carried_comparisons"]) != len(
        contract["comparisons"]
    ):
        raise AssertionError("not all artifact-carried comparisons were reported")
    completion = result["completion_and_recovery"]
    if (
        completion["global"]["cells"] != EXPECTED_UNBATCHED_RUNS
        or [item["label"] for item in completion["per_config"]]
        != [label for label, _ in contract["configs"]]
        or {item["cells"] for item in completion["per_config"]}
        != {EXPECTED_TASKS}
    ):
        raise AssertionError("global/per-config completion summary changed")
    if (
        result["sole_predeclared_sensitivity"]["tasks"]
        != EXPECTED_SCREEN_EXCLUDED_TASKS
        or result["sole_predeclared_sensitivity"]["called_unseen"] is not False
        or result["sole_predeclared_sensitivity"]["identity"][
            "heldout_inclusion"
        ]["task_manifest_sha256"]
        != heldout.MANIFEST_SHA256
    ):
        raise AssertionError("screen-excluded sensitivity changed")
    layouts.append(len(records))

    def validate_current():
        validate_records(records, tasks, contract, digest, revision)

    last = records.pop()
    try:
        _expect_error(validate_current, "expected exactly 9639")
    finally:
        records.append(last)
    records.append(records[0])
    try:
        _expect_error(validate_current, "duplicate cell")
    finally:
        records.pop()
    _mutate_and_expect(
        records,
        0,
        "task_manifest_sha256",
        hashlib.sha256(b"changed metadata").hexdigest(),
        validate_current,
        "task_manifest_sha256",
    )
    _mutate_and_expect(
        records,
        0,
        "pilot_planner_preprocess_sha256",
        hashlib.sha256(b"changed pilot preprocess").hexdigest(),
        validate_current,
        "pilot_planner_preprocess_sha256",
    )
    _mutate_and_expect(
        records,
        0,
        "initial_dead_construction_logging_protocol",
        "changed",
        validate_current,
        "initial_dead_construction_logging_protocol",
    )
    _mutate_and_expect(
        records,
        0,
        "heldout_initial_dead_construction_logging_protocol",
        "changed",
        validate_current,
        "heldout_initial_dead_construction_logging_protocol",
    )
    presearch_time = copy.deepcopy(records)
    presearch_target = next(
        record
        for record in presearch_time
        if record["algorithm"] == "ms_cap32" and record["coverage"] == 0
    )
    for field in (
        *heldout.ALL_SCHEMA_V2_METRICS,
        *heldout.SCHEMA_V2_CONVENTIONS,
        *heldout.CONSTRUCTION_FIELDS,
        *heldout.HEURISTIC_FIELDS,
        "search_raw_exit_code",
        "search_effective_exit_code",
        "wbh_summary_solved",
        "wbh_done_solution_cost",
        "wbh_solved_summary_certified",
    ):
        presearch_target.pop(field, None)
    presearch_target.update(
        {
            "planner_exit_code": 21,
            "error": "translate-out-of-time",
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
    validate_records(presearch_time, tasks, contract, digest, revision)
    solved_index = next(i for i, record in enumerate(records) if record["coverage"] == 1)
    mapped = copy.deepcopy(records[solved_index])
    mapped.update(
        planner_exit_code=2,
        search_raw_exit_code=23,
        search_effective_exit_code=2,
        error="search-plan-found-and-out-of-time",
    )
    mapped_errors = []
    heldout.pilot_analyzer._validate_outcome(
        mapped, "full mapped", mapped_errors
    )
    if mapped_errors:
        raise AssertionError("valid mapped full outcome failed: {!r}".format(
            mapped_errors
        ))
    for field, value, fragment in (
        ("search_raw_exit_code", 24, "raw resource exit 23"),
        ("outcome_reconciliation_certified", False, "not certified"),
        ("plan_file_candidate_count", 2, "exactly one plan candidate"),
        ("plan_file_canonical", False, "canonical plan certification"),
        ("wbh_done_solution_cost", mapped["solution_cost"] + 1, "disagrees"),
        ("raw_metrics_complete", False, "requires"),
    ):
        changed_mapped = copy.deepcopy(mapped)
        changed_mapped[field] = value
        changed_errors = []
        heldout.pilot_analyzer._validate_outcome(
            changed_mapped, "full mapped", changed_errors
        )
        if not any(fragment in error for error in changed_errors):
            raise AssertionError(
                "full mapped mutation {} was accepted: {!r}".format(
                    field, changed_errors
                )
            )
    _mutate_and_expect(
        records,
        solved_index,
        "plan_file_cost",
        records[solved_index]["solution_cost"] + 1,
        validate_current,
        "plan_file_cost",
    )
    other_cost_index = next(
        i
        for i, record in enumerate(records)
        if i != solved_index
        and record["coverage"] == 1
        and record["domain"] == records[solved_index]["domain"]
        and record["problem"] == records[solved_index]["problem"]
    )
    old_solution = records[other_cost_index]["solution_cost"]
    old_plan = records[other_cost_index]["plan_file_cost"]
    records[other_cost_index]["solution_cost"] = old_solution + 1
    records[other_cost_index]["plan_file_cost"] = old_plan + 1
    try:
        _expect_error(validate_current, "solved-cost disagreement")
    finally:
        records[other_cost_index]["solution_cost"] = old_solution
        records[other_cost_index]["plan_file_cost"] = old_plan
    _mutate_and_expect(
        records,
        0,
        "full_completion_marker_valid",
        False,
        validate_current,
        "full_completion_marker_valid",
    )
    _mutate_and_expect(
        records,
        0,
        "full_completion_slurm_restart_count",
        records[0]["full_completion_slurm_restart_count"] + 1,
        validate_current,
        "completion marker SHA-256 changed",
    )
    archive_index = next(
        i for i, record in enumerate(records) if record["full_partial_archive_count"]
    )
    _mutate_and_expect(
        records,
        archive_index,
        "full_partial_archive_restart_ids",
        [0, 2],
        validate_current,
        "archive restart IDs are noncanonical",
    )
    _mutate_and_expect(
        records,
        solved_index,
        "raw_metrics_complete",
        False,
        validate_current,
        "incomplete metrics require a resource exit",
    )
    selector_index = next(
        i for i, record in enumerate(records) if record["algorithm"] == contract["selector_winner"]
    )
    _mutate_and_expect(
        records,
        selector_index,
        "pdb_selector_trace_sha256",
        hashlib.sha256(b"changed selector trace").hexdigest(),
        validate_current,
        "pdb_selector_trace_sha256",
    )
    _expect_error(
        lambda: _validate_sensitivity_subset(tasks, screen_excluded[:-1]),
        "sensitivity subset changed",
    )
    heldout_tasks = heldout.load_and_validate_tasks()
    screen_task = next(
        task
        for task in _load_screen_manifest()
        if task[0] in {domain for domain, _ in heldout_tasks}
    )
    changed_heldout = list(heldout_tasks)
    replace_index = next(
        index
        for index, task in enumerate(changed_heldout)
        if task[0] == screen_task[0]
    )
    changed_heldout[replace_index] = screen_task
    _expect_error(
        lambda: _validate_heldout_inclusion(
            screen_excluded, changed_heldout
        ),
        "omits held-out tasks",
    )
    changed_artifact = copy.deepcopy(artifact)
    changed_artifact["validation"]["analysis"]["rerank_on_validation"] = True
    _expect_error(
        lambda: validate_selection_artifact(changed_artifact),
        "invalid selection artifact",
    )
    changed_artifact = copy.deepcopy(artifact)
    changed_artifact["pilot"]["planner_binary_sha256"] = "4" * 64
    _expect_error(
        lambda: validate_selection_artifact(changed_artifact),
        "invalid selection artifact",
    )
    synthetic_identity_pins = {
        "planner_revision": "89abcdef0123456789abcdef0123456789abcdef",
        "pilot_protocol_revision": "fedcba9876543210fedcba9876543210fedcba98",
        "binary_sha256": hashlib.sha256(b"synthetic full binary").hexdigest(),
        "preprocess_sha256": hashlib.sha256(
            b"synthetic full preprocess"
        ).hexdigest(),
        "cache_name_suffix": "_1234abcd",
        "runner_source_sha256": hashlib.sha256(
            b"synthetic full runner"
        ).hexdigest(),
        "job_sha256": {
            EXPECTED_UNBATCHED_RUNS: hashlib.sha256(
                b"synthetic unbatched full job"
            ).hexdigest(),
            EXPECTED_BATCHED_RUNS: hashlib.sha256(
                b"synthetic batched full job"
            ).hexdigest(),
        },
    }
    if require_reviewed_pins(
        digest,
        expected_artifact_sha256=digest,
        protocol_revision=revision,
        **synthetic_identity_pins,
    ) != revision:
        raise AssertionError("reviewed-pin override changed")
    _expect_error(
        lambda: require_reviewed_pins(
            digest,
            expected_artifact_sha256=None,
            protocol_revision=revision,
            **synthetic_identity_pins,
        ),
        "EXPECTED_SELECTION_ARTIFACT_SHA256 is unset",
    )
    _expect_error(
        lambda: require_reviewed_pins(
            digest,
            expected_artifact_sha256=digest,
            protocol_revision=None,
            **synthetic_identity_pins,
        ),
        "EXPECTED_FULL_PROTOCOL_REVISION is unset",
    )

    del result, records, case, artifact, contract
    gc.collect()

    case = _synthetic_case("pdb_selector_k64_adapt_w64_r1_n1m")
    (
        _,
        digest,
        contract,
        tasks,
        screen_excluded,
        domains,
        revision,
        records,
    ) = case
    if len(records) != EXPECTED_BATCHED_RUNS or contract["run_count"] != EXPECTED_BATCHED_RUNS:
        raise AssertionError("synthetic 11016-cell layout changed")
    validate_runner_contract(
        contract, expected_artifact_sha256=None, check_reviewed_pins=False
    )
    result = analyze(
        records,
        tasks,
        screen_excluded,
        domains,
        contract,
        digest,
        revision,
    )
    _assert_synthetic_macro_pins(result, EXPECTED_BATCHED_RUNS)
    if (
        result["execution"]["cell_count"] != EXPECTED_BATCHED_RUNS
        or result["selection_artifact"]["matched_same_k_unbatched"]
        != "pdb_selector_k64"
    ):
        raise AssertionError("batched 11016-cell analysis changed")
    matched_record = next(
        record
        for record in records
        if record["algorithm"] == "pdb_selector_k64"
        and record["domain"] == tasks[0][0]
        and record["problem"] == tasks[0][1]
    )
    changed_candidate = matched_record["pdb_selector_candidates"][-1]
    old_abstract_states = changed_candidate["abstract_states"]
    changed_candidate["abstract_states"] = old_abstract_states + 1
    heldout.pilot_analyzer._refresh_selector_hashes(matched_record)
    try:
        _expect_error(
            lambda: validate_records(records, tasks, contract, digest, revision),
            "same-task selector pool disagreement",
        )
    finally:
        changed_candidate["abstract_states"] = old_abstract_states
        heldout.pilot_analyzer._refresh_selector_hashes(matched_record)
    layouts.append(len(records))
    gates_pinned = (
        EXPECTED_SELECTION_ARTIFACT_SHA256 is not None
        and EXPECTED_FULL_PROTOCOL_REVISION is not None
        and FULL_RUNNER_SOURCE_SHA256 is not None
        and PLANNER_REVISION is not None
        and CACHE_BINARY_SHA256 is not None
        and CACHE_PREPROCESS_SHA256 is not None
        and CACHE_NAME_SUFFIX is not None
        and all(EXPECTED_PROSPECTIVE_JOB_SHA256.values())
    )
    return {
        "schema": ANALYSIS_SCHEMA,
        "self_test": "PASS",
        "synthetic_cells_sequential": layouts,
        "adversarial": [
            "metadata",
            "pilot-vs-downstream-provenance",
            "missing-and-duplicate-cells",
            "outcome-and-cross-config-cost",
            "mapped-success-reconciliation-and-cost-evidence",
            "completion-marker-and-archive",
            "metrics-selector-trace-and-cross-config-pool-consistency",
            "screen-excluded-sensitivity",
            "no-rerank",
            "strict-json-directory-and-tar-loaders",
        ],
        "ordinary_analysis_gate": (
            "PINNED" if gates_pinned
            else "BLOCKED_UNTIL_REVIEWED_HASHES_ARE_PINNED"
        ),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Analyze the exact frozen Arrhenius 1377-task full census."
    )
    parser.add_argument(
        "properties",
        nargs="?",
        help="Lab properties JSON, eval directory, tar archive, or '-' for stdin.",
    )
    parser.add_argument(
        "--selection",
        type=Path,
        help="Exact selection artifact v3 used to launch the full experiment.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run sequential 9639/11016-cell synthetic and adversarial tests.",
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
    contract = validate_selection_artifact(artifact)
    validate_runner_contract(
        contract, expected_artifact_sha256=artifact_sha256
    )
    tasks, screen_excluded, domains = load_and_validate_tasks()
    records = load_properties(args.properties)
    result = analyze(
        records,
        tasks,
        screen_excluded,
        domains,
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
