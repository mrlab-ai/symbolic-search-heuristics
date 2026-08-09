#!/usr/bin/env python3
"""Fail-closed full-population evaluation of the selected heuristic matrix.

This prospective runner consumes only the exact selector-screen artifact v3.
It independently reconstructs the held-out 7/8-configuration contract and
carries that matrix forward unchanged to every frozen supported task.  It does
not read, rank, or otherwise consume held-out outcomes.

Launch is intentionally impossible until the reviewed raw selection-artifact
SHA-256 is pinned below.  Read-only commands remain available::

    python experiments/exp_arrhenius_selector_full.py --self-test
    python experiments/exp_arrhenius_selector_full.py \
        --selection selection.json --check

Once the artifact is pinned, build and start must be separate invocations.
The full population has 9,639 or 11,016 cells.  Lab groups these into at most
1,000 deterministic array elements, with respectively 10 or 12 runs per
element, reviewed 70- or 75-minute envelopes, and at most five concurrent
elements.  These are requested scheduler envelopes, not per-cell wall-time
guarantees; the planner limit is aggregate process CPU and no outer watchdog
is installed.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from downward import suites

import exp_arrhenius_common as C
import exp_arrhenius_selector_validation as V
import suite_cost_manifest


class ProtocolError(RuntimeError):
    pass


PROTOCOL = "arrhenius-selector-full-population-v2"
FULL_ANALYSIS_PROTOCOL = "full-supported-population-census-v1"
FULL_COMPLETION_MARKER = ".arrhenius-full-run-complete-v1"
FULL_COMPLETION_MARKER_SCHEMA = (
    "symbolic-search-heuristics/arrhenius-full-wrapper-completion/v1"
)
FULL_COMPLETION_MARKER_PROTOCOL = (
    "canonical-four-line-marker-atomic-after-python-wrapper-zero-exit/v1"
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
ARTIFACT_SCHEMA = V.ARTIFACT_SCHEMA
EXPECTED_SELECTION_ARTIFACT_SHA256 = None

EXPERIMENT_DATA_PATH = (
    Path(__file__).resolve().parent / "data" / Path(__file__).stem
)
PROTOCOL_FILES = tuple(
    dict.fromkeys(
        (
            Path(__file__).resolve(),
            Path(V.__file__).resolve(),
            *V.PROTOCOL_FILES,
            Path(suite_cost_manifest.__file__).resolve(),
            Path(__file__).with_name("suite_wbh_operator_costs.json").resolve(),
            Path(__file__).with_name(
                "suite_wbh_operator_costs.json.sha256"
            ).resolve(),
        )
    )
)

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
EXPECTED_SCREEN_EXCLUDED_TASKS = 1327
EXPECTED_SCREEN_EXCLUDED_DOMAINS = 46
EXPECTED_SCREEN_EXCLUDED_TASK_MANIFEST_SHA256 = (
    "1e126791b438d903cb6adcc441391b92d76a7e14cf46f6a89465a066823a986f"
)
EXPECTED_SCREEN_EXCLUDED_TASK_SOURCES_SHA256 = (
    "158e5446e3b97ddd63095441c518ecbe6d2e3ce3529aa9a8fd412df23e706068"
)
EXPECTED_SOURCE_MANIFEST_SHA256 = V.EXPECTED_SOURCE_MANIFEST_SHA256

BENCHMARK_REVISION = V.BENCHMARK_REVISION
BENCHMARK_REPOSITORY = V.BENCHMARK_REPOSITORY
PLANNER_REVISION = V.PLANNER_REVISION
PILOT_PROTOCOL_REVISION = V.PILOT_PROTOCOL_REVISION
CACHE_BINARY_SHA256 = V.CACHE_BINARY_SHA256
CACHE_PREPROCESS_SHA256 = V.CACHE_PREPROCESS_SHA256

TIME_LIMIT_SECONDS = V.TIME_LIMIT_SECONDS
MEMORY_LIMIT_MIB = V.MEMORY_LIMIT_MIB
PAR2_UNSOLVED_SECONDS = V.PAR2_UNSOLVED_SECONDS
EXPECTED_UNBATCHED_CONFIGS = 7
EXPECTED_BATCHED_CONFIGS = 8
EXPECTED_UNBATCHED_RUNS = 9639
EXPECTED_BATCHED_RUNS = 11016
EXPECTED_WRAPPER_ALLOWANCE_SECONDS_PER_RUN = 60
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
FULL_SCHEDULER_TIME_LIMITS = {
    EXPECTED_UNBATCHED_RUNS: "01:10:00",
    EXPECTED_BATCHED_RUNS: "01:15:00",
}
FULL_SCHEDULER_TIME_LIMIT_SECONDS = {
    EXPECTED_UNBATCHED_RUNS: 70 * 60,
    EXPECTED_BATCHED_RUNS: 75 * 60,
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
    EXPECTED_UNBATCHED_RUNS: None,
    EXPECTED_BATCHED_RUNS: None,
}

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

_LEGACY_DRIVER_LOG_SKIP = '''    if [[ -f driver.log ]]; then
        echo "The run in $(pwd) has already been started --> skip it"
        return
    fi
'''
_FULL_STRICT_MARKER_SKIP = '''    if [[ -e __MARKER__ || -L __MARKER__ ]]; then
        if [[ ! -f __MARKER__ || -L __MARKER__ ]]; then
            >&2 echo "Invalid wrapper completion-marker filesystem entry"
            return 1
        fi
        mapfile -t MARKER_LINES < __MARKER__
        if (( ${#MARKER_LINES[@]} == 4 )) && \
           [[ ${MARKER_LINES[0]} == "schema=__MARKER_SCHEMA__" ]] && \
           [[ ${MARKER_LINES[1]} == "run_id=$run_id" ]] && \
           [[ ${MARKER_LINES[2]} =~ ^completion_slurm_restart_count=(0|[1-9][0-9]*)$ ]] && \
           [[ ${MARKER_LINES[3]} == "wrapper_exit_code=0" ]] && \
           cmp -s -- __MARKER__ <(printf '%s\\n' "${MARKER_LINES[@]}"); then
            echo "The run in $(pwd) has a wrapper completion marker --> skip it"
            return 0
        fi
        >&2 echo "Invalid wrapper completion-marker content"
        return 1
    fi
'''.replace("__MARKER__", FULL_COMPLETION_MARKER).replace(
    "__MARKER_SCHEMA__", FULL_COMPLETION_MARKER_SCHEMA
)
FULL_RESTART_COUNT_FILE = ".arrhenius-full-slurm-restart-count-v1"
FULL_PARTIAL_ARCHIVE_PREFIX = ".arrhenius-full-partial-before-restart-"
FULL_STATIC_RUN_ENTRIES = (
    "domain.pddl",
    "problem.pddl",
    "run",
    "static-properties",
)
FULL_DYNAMIC_OUTPUT_POLICY = {
    "protocol": "archive-all-nonstatic-top-level-run-entries-on-requeue/v1",
    "preserved_entries": list(FULL_STATIC_RUN_ENTRIES),
    "preserved_archive_prefix": FULL_PARTIAL_ARCHIVE_PREFIX,
    "restart_count_source": "SLURM_RESTART_COUNT",
    "archive_name_format": FULL_PARTIAL_ARCHIVE_PREFIX + "%05d",
    "unmarked_partial_outputs_are_replaced": True,
}
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
_FULL_ATTEMPT_PREPARATION = '''
    RESTART_COUNT=${SLURM_RESTART_COUNT:-0}
    if [[ ! $RESTART_COUNT =~ ^(0|[1-9][0-9]*)$ ]]; then
        >&2 echo "Invalid SLURM_RESTART_COUNT: $RESTART_COUNT"
        return 1
    fi
    shopt -s dotglob nullglob
    DYNAMIC_ENTRIES=()
    for entry in *; do
        case "$entry" in
            domain.pddl|problem.pddl|run|static-properties|__ARCHIVE_PREFIX__*)
                continue
                ;;
        esac
        DYNAMIC_ENTRIES+=("$entry")
    done
    shopt -u dotglob nullglob
    if (( ${#DYNAMIC_ENTRIES[@]} > 0 )); then
        if (( RESTART_COUNT == 0 )); then
            >&2 echo "Fresh array attempt has unexpected dynamic run outputs"
            return 1
        fi
        if [[ ! -f __RESTART_FILE__ || -L __RESTART_FILE__ ]]; then
            >&2 echo "Dynamic partial outputs lack a regular prior restart counter"
            return 1
        fi
        PRIOR_RESTART_COUNT=$(<__RESTART_FILE__)
        if [[ ! $PRIOR_RESTART_COUNT =~ ^(0|[1-9][0-9]*)$ ]] ||
           ! cmp -s -- __RESTART_FILE__ <(printf '%s\\n' "$PRIOR_RESTART_COUNT") ||
           (( PRIOR_RESTART_COUNT >= RESTART_COUNT )); then
            >&2 echo "Noncanonical or non-increasing prior restart counter"
            return 1
        fi
        ARCHIVE_DIR=$(printf "__ARCHIVE_PREFIX__%05d" "$RESTART_COUNT")
        if [[ -e "$ARCHIVE_DIR" || -L "$ARCHIVE_DIR" ]]; then
            >&2 echo "Refusing to overwrite partial-attempt archive $ARCHIVE_DIR"
            return 1
        fi
        mkdir -- "$ARCHIVE_DIR" || return 1
        for entry in "${DYNAMIC_ENTRIES[@]}"; do
            mv -- "$entry" "$ARCHIVE_DIR/" || return 1
        done
    fi
    RESTART_TMP=$(mktemp "__RESTART_FILE__.tmp.XXXXXX") || return 1
    printf '%s\\n' "$RESTART_COUNT" > "$RESTART_TMP" || return 1
    mv -f -- "$RESTART_TMP" __RESTART_FILE__ || return 1
'''.replace("__ARCHIVE_PREFIX__", FULL_PARTIAL_ARCHIVE_PREFIX).replace(
    "__RESTART_FILE__", FULL_RESTART_COUNT_FILE
)
_LEGACY_RETCODE_BLOCK = '''    RETCODE=$?
    if [[ $RETCODE != 0 ]]; then
        >&2 echo "The run script finished with exit code $RETCODE"
    fi
'''
_FULL_RETCODE_BLOCK = '''    RETCODE=$?
    if [[ $RETCODE != 0 ]]; then
        >&2 echo "The run script finished with exit code $RETCODE"
    fi
    exit "$RETCODE"
'''
_LEGACY_DRIVER_REDIRECT = ''') > driver.log 2> driver.err
'''
_FULL_DRIVER_REDIRECT = ''') > driver.log 2> driver.err
    RETCODE=$?
'''
_LEGACY_DRIVER_ERR_CLEANUP = '''    if [[ ! -s driver.err ]]; then
        rm driver.err
    fi
'''
_FULL_DRIVER_ERR_CLEANUP_AND_MARKER = '''    if [[ ! -s driver.err ]]; then
        rm driver.err || return 1
    fi
    if [[ $RETCODE == 0 ]]; then
        MARKER_TMP=$(mktemp "__MARKER__.tmp.XXXXXX") || return 1
        if [[ ! -f "$MARKER_TMP" || -L "$MARKER_TMP" ]]; then
            >&2 echo "mktemp did not create a regular marker file"
            return 1
        fi
        printf '%s\\n' \\
            'schema=__MARKER_SCHEMA__' \\
            "run_id=$run_id" \\
            "completion_slurm_restart_count=$RESTART_COUNT" \\
            'wrapper_exit_code=0' > "$MARKER_TMP" || return 1
        if ! cmp -s -- "$MARKER_TMP" <(printf '%s\\n' \\
            'schema=__MARKER_SCHEMA__' \\
            "run_id=$run_id" \\
            "completion_slurm_restart_count=$RESTART_COUNT" \\
            'wrapper_exit_code=0'); then
            >&2 echo "Staged wrapper completion marker bytes changed"
            return 1
        fi
        mv -f -- "$MARKER_TMP" __MARKER__ || return 1
    fi
    return "$RETCODE"
'''.replace("__MARKER__", FULL_COMPLETION_MARKER).replace(
    "__MARKER_SCHEMA__", FULL_COMPLETION_MARKER_SCHEMA
)


def _run_loop_blocks(experiment_name):
    legacy = '''# Execute runs in shuffled order.
for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID); do
    run_dir=$(print_run_dir ${run_id})
    (cd "../__EXPERIMENT__/$run_dir" && execute_run ${run_id})
done
'''.replace("__EXPERIMENT__", experiment_name)
    full = '''# Execute runs in deterministic order and retain every wrapper failure.
ARRAY_RETCODE=0
for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID); do
    run_dir=$(print_run_dir ${run_id})
    (cd "../__EXPERIMENT__/$run_dir" && execute_run ${run_id}) || ARRAY_RETCODE=1
done
exit "$ARRAY_RETCODE"
'''.replace("__EXPERIMENT__", experiment_name)
    return legacy, full

FULL_FIXED_ENVIRONMENT = {
    "time_limit": "300s",
    "memory_limit": "8G",
    "build_options": ["release_no_lp"],
    "cache_build_name": "release_no_lp",
    "scheduler_cluster": "arrhenius",
    "scheduler_cpu_model": "AMD EPYC 9755 128-Core Processor",
    "scheduler_partition": "cpu",
    "scheduler_qos": "normal",
    "scheduler_account": "naiss2025-5-561-cpu",
    "scheduler_time_limits": dict(FULL_SCHEDULER_TIME_LIMITS),
    "scheduler_memory_per_cpu": "9G",
    "scheduler_cpus_per_task": 1,
    "array_task_throttle": 5,
    "max_array_tasks": 1000,
    "wrapper_allowance_seconds_per_run": (
        EXPECTED_WRAPPER_ALLOWANCE_SECONDS_PER_RUN
    ),
}

def canonical_json(value):
    return V.canonical_json(value)


def sha256_json(value):
    return V.sha256_json(value)


def _require_sha256(value, label, expected=None):
    return V._require_sha256(value, label, expected)


def _expect_protocol_error(function, expected_fragment=None):
    try:
        function()
    except (ProtocolError, V.ProtocolError, RuntimeError) as err:
        if expected_fragment is not None and expected_fragment not in str(err):
            raise AssertionError(
                "expected protocol error containing {!r}, got {!r}".format(
                    expected_fragment, str(err)
                )
            ) from err
    else:
        raise AssertionError("expected protocol error")


def _add_config(configs, label, search, role):
    label_matches = [item for item in configs if item["label"] == label]
    search_matches = [item for item in configs if item["search"] == search]
    if label_matches or search_matches:
        if (
            len(label_matches) != 1
            or len(search_matches) != 1
            or label_matches[0] is not search_matches[0]
        ):
            raise ProtocolError(
                "full-matrix label/search collision for {}".format(label)
            )
        if role not in label_matches[0]["roles"]:
            label_matches[0]["roles"].append(role)
        return
    configs.append({"label": label, "search": search, "roles": [role]})


def _independent_heldout_config_records(global_label, selector_label):
    """Reconstruct the exact held-out matrix without held-out results."""
    records = []
    for label, search, role in V.FIXED_VALIDATION_CONFIGS:
        _add_config(records, label, search, role)
    if selector_label not in V.SELECTOR_LABELS:
        raise ProtocolError("selector-family winner is not eligible")
    _add_config(
        records,
        selector_label,
        V.PILOT_SEARCHES[selector_label],
        "pilot-selector-family-winner",
    )
    matched_label = V.BATCHED_SELECTOR_BASE.get(selector_label)
    if matched_label is not None:
        _add_config(
            records,
            matched_label,
            V.PILOT_SEARCHES[matched_label],
            "matched-same-k-unbatched-ablation",
        )
    if global_label not in {item["label"] for item in records}:
        raise ProtocolError("global winner is absent from held-out matrix")
    _add_config(
        records,
        global_label,
        V.PILOT_SEARCHES[global_label],
        "pilot-global-winner",
    )
    expected_count = (
        EXPECTED_BATCHED_CONFIGS
        if matched_label is not None
        else EXPECTED_UNBATCHED_CONFIGS
    )
    if len(records) != expected_count:
        raise ProtocolError(
            "independent held-out matrix has {} configs, expected {}".format(
                len(records), expected_count
            )
        )
    if (
        len({item["label"] for item in records}) != expected_count
        or len({item["search"] for item in records}) != expected_count
    ):
        raise ProtocolError("independent held-out matrix is not deduplicated")
    return records, matched_label


def validate_full_layout(num_runs):
    if num_runs not in (EXPECTED_UNBATCHED_RUNS, EXPECTED_BATCHED_RUNS):
        raise ProtocolError(
            "full run count must be exactly {} or {}".format(
                EXPECTED_UNBATCHED_RUNS, EXPECTED_BATCHED_RUNS
            )
        )
    array_tasks, runs_per_array_task = C.run_layout(num_runs)
    expected_runs_per = 10 if num_runs == EXPECTED_UNBATCHED_RUNS else 12
    expected_array_tasks = 964 if num_runs == EXPECTED_UNBATCHED_RUNS else 918
    if (
        runs_per_array_task != expected_runs_per
        or array_tasks != expected_array_tasks
        or array_tasks > C.MAX_ARRAY_TASKS
    ):
        raise ProtocolError(
            "full array grouping changed: runs={}, array_tasks={}, per_task={}".
            format(num_runs, array_tasks, runs_per_array_task)
        )
    scheduler_seconds = FULL_SCHEDULER_TIME_LIMIT_SECONDS[num_runs]
    required_seconds = runs_per_array_task * (
        TIME_LIMIT_SECONDS + EXPECTED_WRAPPER_ALLOWANCE_SECONDS_PER_RUN
    )
    if scheduler_seconds < required_seconds:
        raise ProtocolError(
            "reviewed full scheduler envelope is too short: {} < {}".format(
                scheduler_seconds, required_seconds
            )
        )
    full_array_tasks, partial_runs = divmod(num_runs, runs_per_array_task)
    partial_array_tasks = int(partial_runs != 0)
    if full_array_tasks + partial_array_tasks != array_tasks:
        raise ProtocolError("full array group distribution changed")
    return {
        "raw_runs": num_runs,
        "array_tasks": array_tasks,
        "runs_per_array_task": runs_per_array_task,
        "array_task_run_distribution": {
            "full_array_tasks": full_array_tasks,
            "full_runs_per_array_task": runs_per_array_task,
            "partial_array_tasks": partial_array_tasks,
            "partial_runs": partial_runs,
        },
        "scheduler_time_limit_seconds": scheduler_seconds,
        "wrapper_allowance_seconds_per_run": (
            EXPECTED_WRAPPER_ALLOWANCE_SECONDS_PER_RUN
        ),
    }


def attest_exact_array_assignment(num_runs):
    """Freeze the Slurm-ID to logical-group permutation byte-for-byte."""
    layout = validate_full_layout(num_runs)
    logical_groups = list(range(1, layout["array_tasks"] + 1))

    def assignment_key(group_id):
        payload = "{}\0{}\0{}".format(
            C.TASK_ORDER_SEED, layout["array_tasks"], group_id
        )
        return hashlib.sha256(payload.encode("utf-8")).digest(), group_id

    logical_groups.sort(key=assignment_key)
    if sorted(logical_groups) != list(range(1, layout["array_tasks"] + 1)):
        raise ProtocolError("full array assignment is not a permutation")
    digest = sha256_json(logical_groups)
    expected_digest = EXPECTED_ARRAY_ASSIGNMENT_SHA256[num_runs]
    if digest != expected_digest:
        raise ProtocolError(
            "full array-assignment digest changed: expected {}, got {}".format(
                expected_digest, digest
            )
        )
    final_logical_group = layout["array_tasks"]
    slurm_id = logical_groups.index(final_logical_group) + 1
    if slurm_id != EXPECTED_FINAL_LOGICAL_GROUP_SLURM_ID[num_runs]:
        raise ProtocolError("final logical group's Slurm array ID changed")
    return {
        "protocol": C.TASK_ORDER_METHOD,
        "slurm_id_to_logical_group_sha256": digest,
        "final_logical_group": final_logical_group,
        "final_logical_group_slurm_id": slurm_id,
        "final_logical_group_runs": (
            layout["array_task_run_distribution"]["partial_runs"]
            or layout["runs_per_array_task"]
        ),
    }


def validate_selection_artifact(artifact):
    """Validate v3, then independently reconstruct the carried matrix."""
    heldout = V.validate_selection_artifact(artifact)
    global_label = heldout["global_winner"]["label"]
    selector_label = heldout["selector_winner"]["label"]
    records, matched_label = _independent_heldout_config_records(
        global_label, selector_label
    )
    if canonical_json(records) != canonical_json(
        artifact["validation"]["configs"]
    ):
        raise ProtocolError(
            "screen artifact held-out configs differ from independent "
            "reconstruction"
        )
    if canonical_json(records) != canonical_json(heldout["config_records"]):
        raise ProtocolError(
            "held-out runner and full runner reconstructed different matrices"
        )
    options = [
        {"label": item["label"], "search": item["search"]}
        for item in records
    ]
    matrix_sha256 = sha256_json(options)
    if (
        matrix_sha256 != heldout["matrix_digest"]
        or matrix_sha256 != artifact["validation"]["option_matrix_sha256"]
    ):
        raise ProtocolError("carried held-out option-matrix digest changed")
    if matched_label != heldout["matched_unbatched"]:
        raise ProtocolError("carried same-K ablation identity changed")
    config_count = len(records)
    heldout_run_count = V.EXPECTED_TASKS * config_count
    if heldout_run_count != heldout["run_count"] or heldout_run_count not in (
        644,
        736,
    ):
        raise ProtocolError("held-out 7/8 contract changed before carry-forward")
    heldout_materialization = {
        "materialized_pddl_protocol": V.MATERIALIZED_PDDL_PROTOCOL,
        "materialized_pddl_files": V.EXPECTED_MATERIALIZED_PDDL_FILES[
            heldout_run_count
        ],
        "materialized_pddl_bytes": V.EXPECTED_MATERIALIZED_PDDL_BYTES[
            heldout_run_count
        ],
        "pddl_bytes_per_config": V.EXPECTED_PDDL_BYTES_PER_CONFIG,
        "unique_pddl_source_files": V.EXPECTED_UNIQUE_PDDL_SOURCE_FILES,
        "unique_pddl_source_bytes": V.EXPECTED_UNIQUE_PDDL_SOURCE_BYTES,
    }
    for key, expected in heldout_materialization.items():
        if heldout.get(key) != expected or artifact["validation"].get(key) != expected:
            raise ProtocolError(
                "held-out materialized PDDL contract changed at {}".format(key)
            )
    run_count = EXPECTED_TASKS * config_count
    layout = validate_full_layout(run_count)
    return {
        "configs": [(item["label"], item["search"]) for item in records],
        "config_records": records,
        "matrix_digest": matrix_sha256,
        "comparisons": copy.deepcopy(heldout["comparisons"]),
        "comparisons_digest": heldout["comparisons_digest"],
        "global_winner": copy.deepcopy(heldout["global_winner"]),
        "selector_winner": copy.deepcopy(heldout["selector_winner"]),
        "matched_unbatched": matched_label,
        "pilot_properties_digest": heldout["properties_digest"],
        "heldout_run_count": heldout_run_count,
        "heldout_layout": copy.deepcopy(heldout["layout"]),
        "heldout_materialized_pddl_protocol": heldout_materialization[
            "materialized_pddl_protocol"
        ],
        "heldout_materialized_pddl_files": heldout_materialization[
            "materialized_pddl_files"
        ],
        "heldout_materialized_pddl_bytes": heldout_materialization[
            "materialized_pddl_bytes"
        ],
        "heldout_pddl_bytes_per_config": heldout_materialization[
            "pddl_bytes_per_config"
        ],
        "heldout_unique_pddl_source_files": heldout_materialization[
            "unique_pddl_source_files"
        ],
        "heldout_unique_pddl_source_bytes": heldout_materialization[
            "unique_pddl_source_bytes"
        ],
        "run_count": run_count,
        "layout": layout,
    }


def expected_full_analysis_contract(matrix):
    labels = [label for label, _ in matrix["configs"]]
    comparisons = copy.deepcopy(matrix["comparisons"])
    if sha256_json(comparisons) != matrix["comparisons_digest"]:
        raise ProtocolError("carried comparison digest changed")
    return {
        "protocol": FULL_ANALYSIS_PROTOCOL,
        "analysis_role": "descriptive-frozen-supported-population-census",
        "primary_analysis": (
            "descriptive-census-of-all-1377-frozen-supported-tasks-and-all-"
            "carried-configs/v1"
        ),
        "population_inference": "fixed-population-census-no-confidence-interval",
        "rerank_on_full_population": False,
        "config_order": labels,
        "config_order_sha256": sha256_json(labels),
        "carried_comparisons": comparisons,
        "carried_comparisons_sha256": matrix["comparisons_digest"],
        "sole_predeclared_sensitivity": {
            "name": "selector-vs-pdb-cegar-screen-excluded",
            "comparison": "selector-vs-pdb-cegar",
            "estimand": (
                "selector-minus-cegar-equally-weighted-46-domain-macro-"
                "coverage/v1"
            ),
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


def _full_completion_marker_bytes(run_id, restart_count):
    if type(run_id) is not int or run_id <= 0:
        raise ProtocolError("marker run_id must be a positive integer")
    if type(restart_count) is not int or restart_count < 0:
        raise ProtocolError("marker restart count must be nonnegative")
    return (
        "schema={}\nrun_id={}\ncompletion_slurm_restart_count={}\n"
        "wrapper_exit_code=0\n".format(
            FULL_COMPLETION_MARKER_SCHEMA, run_id, restart_count
        )
    ).encode("ascii")


def _parse_full_completion_marker(raw, expected_run_id):
    try:
        text = raw.decode("ascii")
    except UnicodeError as err:
        raise ProtocolError("completion marker is not ASCII") from err
    match = re.fullmatch(
        re.escape("schema=" + FULL_COMPLETION_MARKER_SCHEMA)
        + r"\nrun_id=([1-9][0-9]*)"
        + r"\ncompletion_slurm_restart_count=(0|[1-9][0-9]*)"
        + r"\nwrapper_exit_code=0\n",
        text,
    )
    if match is None:
        raise ProtocolError("completion marker content/schema changed")
    run_id = int(match.group(1))
    restart_count = int(match.group(2))
    if run_id != expected_run_id:
        raise ProtocolError(
            "completion marker run_id {} differs from {}".format(
                run_id, expected_run_id
            )
        )
    if raw != _full_completion_marker_bytes(run_id, restart_count):
        raise ProtocolError("completion marker is not canonical byte-for-byte")
    return {
        "run_id": run_id,
        "completion_slurm_restart_count": restart_count,
        "wrapper_exit_code": 0,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


class FullCompletionParser(C.Parser):
    """Require the atomic wrapper marker and expose requeue provenance."""

    def parse(self, run_dir, props):
        run_dir = Path(run_dir).resolve()
        try:
            expected_run_id = int(run_dir.name)
        except ValueError:
            expected_run_id = -1
        marker = run_dir / FULL_COMPLETION_MARKER
        props["full_completion_marker_present"] = marker.exists() or marker.is_symlink()
        props["full_completion_marker_valid"] = False
        props["full_completion_marker_schema"] = FULL_COMPLETION_MARKER_SCHEMA
        props["full_completion_marker_protocol"] = FULL_COMPLETION_MARKER_PROTOCOL
        props["full_completion_marker_sha256"] = None
        props["full_wrapper_run_id"] = None
        props["full_wrapper_exit_code"] = None
        props["full_completion_slurm_restart_count"] = None
        props["full_partial_archive_count"] = None
        props["full_partial_archive_restart_ids"] = None
        props["full_archived_slurm_restart_counts"] = None
        props["full_descriptive_cell_execution_count"] = None
        try:
            V._require_regular_file(marker, "full wrapper completion marker")
            parsed = _parse_full_completion_marker(
                marker.read_bytes(), expected_run_id
            )
            restart_file = run_dir / FULL_RESTART_COUNT_FILE
            V._require_regular_file(restart_file, "full restart-count file")
            restart_text = restart_file.read_text(encoding="ascii")
            if not re.fullmatch(r"(?:0|[1-9][0-9]*)\n", restart_text):
                raise ProtocolError("restart-count file is not canonical")
            restart_count = int(restart_text.strip())
            if restart_count != parsed["completion_slurm_restart_count"]:
                raise ProtocolError(
                    "marker/restart-count file disagree: {} != {}".format(
                        parsed["completion_slurm_restart_count"], restart_count
                    )
                )
            archive_ids = []
            archived_restart_counts = []
            for path in sorted(run_dir.iterdir()):
                if not path.name.startswith(FULL_PARTIAL_ARCHIVE_PREFIX):
                    continue
                suffix = path.name.removeprefix(FULL_PARTIAL_ARCHIVE_PREFIX)
                if (
                    path.is_symlink()
                    or not path.is_dir()
                    or not re.fullmatch(r"[0-9]{5}", suffix)
                    or int(suffix) <= 0
                    or int(suffix) > restart_count
                ):
                    raise ProtocolError(
                        "invalid partial-attempt archive {}".format(path.name)
                    )
                archive_ids.append(int(suffix))
                for archived_entry in path.rglob("*"):
                    if archived_entry.is_symlink() or not (
                        archived_entry.is_file() or archived_entry.is_dir()
                    ):
                        raise ProtocolError(
                            "partial archive contains a symlink/special entry: {}".
                            format(archived_entry.relative_to(path))
                        )
                archived_restart = path / FULL_RESTART_COUNT_FILE
                V._require_regular_file(
                    archived_restart, "archived restart-count file"
                )
                archived_restart_text = archived_restart.read_text(
                    encoding="ascii"
                )
                if not re.fullmatch(
                    r"(?:0|[1-9][0-9]*)\n", archived_restart_text
                ):
                    raise ProtocolError("archived restart counter is noncanonical")
                archived_restart_counts.append(int(archived_restart_text.strip()))
                if archived_restart_counts[-1] >= int(suffix):
                    raise ProtocolError(
                        "archive suffix does not follow its prior restart count"
                    )
            if archived_restart_counts != sorted(set(archived_restart_counts)):
                raise ProtocolError("archived restart counters are not increasing")
            props["full_completion_marker_valid"] = True
            props["full_completion_marker_sha256"] = parsed["sha256"]
            props["full_wrapper_run_id"] = parsed["run_id"]
            props["full_wrapper_exit_code"] = parsed["wrapper_exit_code"]
            props["full_completion_slurm_restart_count"] = restart_count
            props["full_partial_archive_count"] = len(archive_ids)
            props["full_partial_archive_restart_ids"] = archive_ids
            props["full_archived_slurm_restart_counts"] = archived_restart_counts
            props["full_descriptive_cell_execution_count"] = len(archive_ids) + 1
        except (OSError, UnicodeError, ProtocolError, V.ProtocolError, RuntimeError) as err:
            C.tools.add_unexplained_error(
                props, "full completion/requeue attestation: {}".format(err)
            )


def get_full_completion_parser():
    return FullCompletionParser()


def require_selection_artifact_hash(
    actual_sha256,
    *,
    required,
    expected_sha256=EXPECTED_SELECTION_ARTIFACT_SHA256,
):
    return V.require_selection_artifact_hash(
        actual_sha256,
        required=required,
        expected_sha256=expected_sha256,
    )


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate or run the launch-blocked Arrhenius selector full "
            "population protocol."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--selection",
        type=Path,
        help="Exact analyzer v3 screen-selection artifact.",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help=(
            "Read-only artifact, full-source, cache, and prospective-header "
            "attestation."
        ),
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run deterministic read-only protocol tests.",
    )
    parser.add_argument(
        "steps", nargs="*", help="Lab steps; build and start run alone."
    )
    args = parser.parse_args(argv)
    if args.check and args.self_test:
        parser.error("--check and --self-test are mutually exclusive")
    if (args.check or args.self_test) and args.steps:
        parser.error("read-only checks cannot be combined with Lab steps")
    if args.self_test and args.selection is not None:
        parser.error("--self-test does not consume an external artifact")
    args.steps = V.normalize_lab_steps(args.steps)
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
        "scheduler_time_limits": dict(FULL_SCHEDULER_TIME_LIMITS),
        "scheduler_memory_per_cpu": C.SCHEDULER_MEMORY_PER_CPU,
        "scheduler_cpus_per_task": C.SCHEDULER_CPUS_PER_TASK,
        "array_task_throttle": C.ARRAY_TASK_THROTTLE,
        "max_array_tasks": C.MAX_ARRAY_TASKS,
        "wrapper_allowance_seconds_per_run": (
            C.SCHEDULER_WRAPPER_ALLOWANCE_SECONDS
        ),
    }
    if actual != FULL_FIXED_ENVIRONMENT:
        raise ProtocolError(
            "Arrhenius full environment differs from the frozen protocol: {}".
            format(actual)
        )


def read_full_tasks():
    """Derive the frozen full list from the authoritative support manifest."""
    data = suite_cost_manifest.load_manifest()
    supported = sorted(suite_cost_manifest.supported_tasks())
    tasks = ["{}:{}".format(domain, problem) for domain, problem in supported]
    digest = hashlib.sha256(
        "".join("{}\n".format(task) for task in tasks).encode("utf-8")
    ).hexdigest()
    if digest != EXPECTED_TASK_MANIFEST_SHA256:
        raise ProtocolError(
            "full task-list digest changed: expected {}, got {}".format(
                EXPECTED_TASK_MANIFEST_SHA256, digest
            )
        )
    domains = {domain for domain, _ in supported}
    if (
        len(tasks) != EXPECTED_TASKS
        or len(set(tasks)) != EXPECTED_TASKS
        or len(domains) != EXPECTED_DOMAINS
        or len(supported) != suite_cost_manifest.EXPECTED_SUPPORTED_POSITIVE_AXIOM_FREE
    ):
        raise ProtocolError(
            "full task set must contain 1377 unique supported tasks in 46 "
            "domains"
        )
    ordered_domains = list(dict.fromkeys(domain for domain, _ in supported))
    domain_sequence_digest = hashlib.sha256(
        "".join("{}\n".format(domain) for domain in ordered_domains).encode(
            "utf-8"
        )
    ).hexdigest()
    if domain_sequence_digest != EXPECTED_DOMAIN_SEQUENCE_SHA256:
        raise ProtocolError(
            "full ordered-domain digest changed: expected {}, got {}".format(
                EXPECTED_DOMAIN_SEQUENCE_SHA256, domain_sequence_digest
            )
        )
    domain_counts = {
        domain: sum(1 for item_domain, _ in supported if item_domain == domain)
        for domain in ordered_domains
    }
    domain_count_records = [
        {"domain": domain, "task_count": domain_counts[domain]}
        for domain in ordered_domains
    ]
    domain_counts_digest = sha256_json(domain_count_records)
    if domain_counts_digest != EXPECTED_DOMAIN_TASK_COUNTS_SHA256:
        raise ProtocolError(
            "full domain task-count digest changed: expected {}, got {}".format(
                EXPECTED_DOMAIN_TASK_COUNTS_SHA256, domain_counts_digest
            )
        )
    records = {
        (record["domain"], record["problem"]): record
        for record in data["tasks"]
    }
    selected = [records[key] for key in supported]
    source_digest = hashlib.sha256(
        suite_cost_manifest.canonical_records_bytes(selected)
    ).hexdigest()
    if source_digest != EXPECTED_TASK_SOURCES_SHA256:
        raise ProtocolError(
            "full source-record digest changed: expected {}, got {}".format(
                EXPECTED_TASK_SOURCES_SHA256, source_digest
            )
        )
    screen_descriptions = V._read_disjointness_manifest(
        Path(__file__).with_name(V.PILOT_MANIFEST)
    )
    screen_digest = hashlib.sha256(
        "".join("{}\n".format(task) for task in screen_descriptions).encode(
            "utf-8"
        )
    ).hexdigest()
    if screen_digest != V.PILOT_MANIFEST_SHA256 or len(screen_descriptions) != 50:
        raise ProtocolError("frozen 50-task screen manifest changed")
    screen_keys = {tuple(task.split(":", 1)) for task in screen_descriptions}
    if len(screen_keys) != 50 or not screen_keys.issubset(set(supported)):
        raise ProtocolError("screen tasks are not an exact subset of full tasks")
    screen_excluded = [key for key in supported if key not in screen_keys]
    screen_excluded_descriptions = [
        "{}:{}".format(domain, problem) for domain, problem in screen_excluded
    ]
    screen_excluded_digest = hashlib.sha256(
        "".join(
            "{}\n".format(task) for task in screen_excluded_descriptions
        ).encode("utf-8")
    ).hexdigest()
    screen_excluded_records_digest = hashlib.sha256(
        suite_cost_manifest.canonical_records_bytes(
            [records[key] for key in screen_excluded]
        )
    ).hexdigest()
    if (
        len(screen_excluded) != EXPECTED_SCREEN_EXCLUDED_TASKS
        or len({domain for domain, _ in screen_excluded})
        != EXPECTED_SCREEN_EXCLUDED_DOMAINS
        or screen_excluded_digest
        != EXPECTED_SCREEN_EXCLUDED_TASK_MANIFEST_SHA256
        or screen_excluded_records_digest
        != EXPECTED_SCREEN_EXCLUDED_TASK_SOURCES_SHA256
    ):
        raise ProtocolError("frozen screen-excluded sensitivity subset changed")
    manifest_digest = suite_cost_manifest.sha256_file(
        suite_cost_manifest.MANIFEST_PATH
    )
    if manifest_digest != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise ProtocolError("frozen support-manifest bytes changed")
    return tasks, {
        "task_manifest_sha256": digest,
        "domain_sequence_sha256": domain_sequence_digest,
        "domain_task_counts_sha256": domain_counts_digest,
        "task_sources_sha256": source_digest,
        "screen_excluded_task_manifest_sha256": screen_excluded_digest,
        "screen_excluded_task_sources_sha256": screen_excluded_records_digest,
        "source_manifest_sha256": manifest_digest,
    }


def require_pinned_benchmark_worktree():
    root = V.require_pinned_benchmark_worktree()
    if V.BENCHMARK_REVISION != BENCHMARK_REVISION or (
        V.BENCHMARK_REPOSITORY != BENCHMARK_REPOSITORY
    ):
        raise ProtocolError("held-out/full benchmark pins differ")
    return root


def _resolve_ordered_tasks(benchmark_root, descriptions):
    resolved = suites.build_suite(str(benchmark_root), descriptions)
    by_description = {
        "{}:{}".format(task.domain, task.problem): task for task in resolved
    }
    if len(resolved) != len(descriptions) or len(by_description) != len(
        descriptions
    ):
        raise ProtocolError(
            "{} full entries resolved to {} tasks ({} unique)".format(
                len(descriptions), len(resolved), len(by_description)
            )
        )
    try:
        ordered = [by_description[item] for item in descriptions]
    except KeyError as err:
        raise ProtocolError(
            "full-population task did not resolve: {}".format(err.args[0])
        ) from err
    supported = suite_cost_manifest.supported_tasks()
    identities = [(task.domain, task.problem) for task in ordered]
    if set(identities) != supported or len(identities) != len(supported):
        missing = sorted(supported - set(identities))
        extra = sorted(set(identities) - supported)
        raise ProtocolError(
            "resolved full population differs from support set: missing={}, "
            "extra={}".format(missing[:8], extra[:8])
        )
    return ordered


def attest_task_sources(benchmark_root, descriptions):
    ordered = _resolve_ordered_tasks(benchmark_root, descriptions)
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
            "full PDDL source file/byte totals changed: per_config={}, "
            "unique_files={}, unique_bytes={}".format(
                bytes_per_config, len(unique_sources), unique_source_bytes
            )
        )
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
            "full task-source bytes changed: expected {}, got {}".format(
                EXPECTED_TASK_SOURCES_SHA256, digest
            )
        )
    manifest_digest = suite_cost_manifest.sha256_file(
        suite_cost_manifest.MANIFEST_PATH
    )
    if manifest_digest != EXPECTED_SOURCE_MANIFEST_SHA256:
        raise ProtocolError("frozen support-manifest bytes changed")
    return {
        "task_sources_sha256": digest,
        "source_manifest_sha256": manifest_digest,
        "pddl_bytes_per_config": bytes_per_config,
        "unique_pddl_source_files": len(unique_sources),
        "unique_pddl_source_bytes": unique_source_bytes,
    }


def _full_source_records():
    data = suite_cost_manifest.load_manifest()
    records = {
        (record["domain"], record["problem"]): record
        for record in data["tasks"]
    }
    supported = suite_cost_manifest.supported_tasks()
    if set(records) < supported:
        raise ProtocolError("support manifest lacks full source records")
    return {key: records[key] for key in supported}


def _require_materialized_pddl(path, expected_sha256, label, source=None):
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as err:
        raise ProtocolError("cannot stat {} {}: {}".format(label, path, err)) from err
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise ProtocolError(
            "{} must be a regular non-symlink materialized file: {}".format(
                label, path
            )
        )
    if info.st_nlink != 1:
        raise ProtocolError("{} must not be a hardlink: {}".format(label, path))
    if info.st_mode & 0o222:
        raise ProtocolError("{} must be read-only: {}".format(label, path))
    if source is not None:
        source = Path(source)
        try:
            if path.samefile(source):
                raise ProtocolError(
                    "{} aliases its benchmark source: {}".format(label, path)
                )
        except OSError as err:
            raise ProtocolError(
                "cannot compare {} with benchmark source: {}".format(label, err)
            ) from err
    actual = V._sha256_file(path)
    if actual != expected_sha256:
        raise ProtocolError(
            "{} SHA-256 changed: expected {}, got {} ({})".format(
                label, expected_sha256, actual, path
            )
        )
    return info.st_size


def _materialize_one_pddl(link, source, expected_sha256, label):
    """Replace one exact Lab source link with an independent byte copy."""
    link = Path(link)
    source = Path(source).resolve()
    if not link.is_symlink() or not link.exists() or link.resolve() != source:
        raise ProtocolError(
            "{} must begin as the exact live Lab source symlink: {}".format(
                label, link
            )
        )
    V._require_regular_file(source, "benchmark PDDL source")
    if V._sha256_file(source) != expected_sha256:
        raise ProtocolError("{} benchmark source digest changed".format(label))
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
            raise ProtocolError("{} copied digest changed".format(label))
        temporary.chmod(0o444)
        _require_materialized_pddl(
            temporary, expected_sha256, "staged " + label, source
        )
        os.replace(temporary, link)
        return _require_materialized_pddl(
            link, expected_sha256, label, source
        )
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary.exists() or temporary.is_symlink():
            temporary.unlink()


def materialize_grid_pddl_inputs(
    benchmark_root, task_descriptions, matrix
):
    """Materialize every cell input only after Lab finishes fresh build."""
    grid_path = EXPERIMENT_DATA_PATH
    if grid_path.is_symlink() or not grid_path.is_dir():
        raise ProtocolError("materialization requires the newly built full grid")
    ordered_tasks = _resolve_ordered_tasks(benchmark_root, task_descriptions)
    records = _full_source_records()
    copied_files = 0
    copied_bytes = 0
    for config_index, _ in enumerate(matrix["configs"]):
        for task_index, task in enumerate(ordered_tasks):
            run_id = config_index * len(ordered_tasks) + task_index + 1
            run_dir = grid_path / V._run_relative_path(run_id)
            V._require_pristine_run_directory(run_dir, run_id)
            record = records[(task.domain, task.problem)]
            for link_name, source, hash_field in (
                ("domain.pddl", Path(task.domain_file).resolve(), "domain_sha256"),
                ("problem.pddl", Path(task.problem_file).resolve(), "problem_sha256"),
            ):
                copied_bytes += _materialize_one_pddl(
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
            "materialized PDDL totals changed: files={}/{}, bytes={}/{}".format(
                copied_files, expected_files, copied_bytes, expected_bytes
            )
        )
    return {"files": copied_files, "bytes": copied_bytes}


def validate_matrix(tasks, matrix):
    validate_fixed_environment()
    configs = matrix["configs"]
    expected_count = (
        EXPECTED_BATCHED_CONFIGS
        if matrix["matched_unbatched"] is not None
        else EXPECTED_UNBATCHED_CONFIGS
    )
    if len(configs) != expected_count:
        raise ProtocolError("carried full configuration count changed")
    labels = [label for label, _ in configs]
    searches = [search for _, search in configs]
    if len(set(labels)) != expected_count or len(set(searches)) != expected_count:
        raise ProtocolError("carried full configuration matrix is not unique")
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
                "release_no_lp full matrix contains forbidden search {}".
                format(label)
            )
    digest = sha256_json(
        [{"label": label, "search": search} for label, search in configs]
    )
    if digest != matrix["matrix_digest"]:
        raise ProtocolError("carried option-matrix digest changed")
    run_count = len(tasks) * len(configs)
    if run_count != matrix["run_count"]:
        raise ProtocolError("full run-count product changed")
    if validate_full_layout(run_count) != matrix["layout"]:
        raise ProtocolError("full array layout changed")
    return matrix


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
    for run_count, digest in EXPECTED_PROSPECTIVE_JOB_SHA256.items():
        _require_sha256(
            digest,
            "reviewed full job SHA-256 for {} runs".format(run_count),
        )
    if (
        PLANNER_REVISION != V.PLANNER_REVISION
        or CACHE_BINARY_SHA256 != V.CACHE_BINARY_SHA256
        or CACHE_PREPROCESS_SHA256 != V.CACHE_PREPROCESS_SHA256
    ):
        raise ProtocolError("full runner differs from P4 planner/cache pins")


def require_full_revision_cache():
    return V.require_validation_revision_cache()


def _full_common_protocol_metadata(
    num_runs,
    *,
    planner_revision=PLANNER_REVISION,
    cache_binary_sha256=CACHE_BINARY_SHA256,
):
    layout = validate_full_layout(num_runs)
    protocol_revision = C.require_revision_ancestor_of_head(planner_revision)
    cache = C.cached_revision(planner_revision)
    return {
        "planner_revision": planner_revision,
        "protocol_revision": protocol_revision,
        "planner_revision_is_protocol_ancestor": True,
        "planner_build_options": list(C.BUILD_OPTIONS),
        "planner_build_config": C.CACHE_BUILD_NAME,
        "planner_binary_sha256": cache_binary_sha256,
        "planner_revision_cache_name": cache.name,
        "external_plan_validation": False,
        "plan_validation_protocol": C.PLAN_VALIDATION_PROTOCOL,
        "plan_file_parser_protocol": C.PLAN_FILE_PARSER_PROTOCOL,
        "outcome_reconciliation_protocol": C.OUTCOME_RECONCILIATION_PROTOCOL,
        "cofactor_width_property": C.COFACTOR_WIDTH_PROPERTY,
        "cofactor_width_parser_protocol": C.COFACTOR_WIDTH_PARSER_PROTOCOL,
        "metrics_validation_protocol": C.wbh_parser.METRICS_VALIDATION_PROTOCOL,
        "python_version": C.platform.python_version(),
        "lab_version": C.INSTALLED_LAB_VERSION,
        "required_lab_version": C.REQUIRED_LAB_VERSION,
        "task_order_seed": C.TASK_ORDER_SEED,
        "task_order_method": C.TASK_ORDER_METHOD,
        "driver_time_limit": C.TIME_LIMIT,
        "driver_memory_limit": C.MEMORY_LIMIT,
        "planner_limit_basis": "aggregate-process-cpu",
        "per_cell_wall_limit_enforced": False,
        "outer_per_cell_watchdog": False,
        "scheduler_environment": "arrhenius-slurm",
        "scheduler_cluster": C.SCHEDULER_CLUSTER,
        "scheduler_cpu_model": C.SCHEDULER_CPU_MODEL,
        "scheduler_partition": C.SCHEDULER_PARTITION,
        "scheduler_qos": C.SCHEDULER_QOS,
        "scheduler_account": C.SCHEDULER_ACCOUNT,
        "scheduler_time_limit_per_task": FULL_SCHEDULER_TIME_LIMITS[num_runs],
        "scheduler_memory_per_cpu": C.SCHEDULER_MEMORY_PER_CPU,
        "scheduler_cpus_per_task": C.SCHEDULER_CPUS_PER_TASK,
        "scheduler_array_task_throttle": C.ARRAY_TASK_THROTTLE,
        "scheduler_max_array_tasks": C.MAX_ARRAY_TASKS,
        "scheduler_array_tasks": layout["array_tasks"],
        "scheduler_runs_per_array_task": layout["runs_per_array_task"],
        "scheduler_wrapper_allowance_seconds_per_run": (
            EXPECTED_WRAPPER_ALLOWANCE_SECONDS_PER_RUN
        ),
        "scheduler_envelope_protocol": SCHEDULER_ENVELOPE_PROTOCOL,
        "scheduler_timeout_invalidates_census": True,
        "scheduler_envelope_is_wall_worst_case_guarantee": False,
        "declared_run_count": num_runs,
        "repetitions": 1,
    }


def validate_full_common_protocol_metadata(metadata):
    expected = _full_common_protocol_metadata(
        metadata["declared_run_count"],
        planner_revision=metadata["planner_revision"],
        cache_binary_sha256=metadata["planner_binary_sha256"],
    )
    mismatches = {
        key: (metadata.get(key), value)
        for key, value in expected.items()
        if metadata.get(key) != value
    }
    if mismatches:
        raise ProtocolError(
            "full common protocol metadata mismatch: {}".format(
                "; ".join(
                    "{}={!r}, expected {!r}".format(key, actual, wanted)
                    for key, (actual, wanted) in sorted(mismatches.items())
                )
            )
        )


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
    metadata = _full_common_protocol_metadata(
        matrix["run_count"],
        planner_revision=planner_revision,
        cache_binary_sha256=cache_binary_sha256,
    )
    additions = {
        "protocol": PROTOCOL,
        "analysis_protocol": FULL_ANALYSIS_PROTOCOL,
        "matrix_carry_forward_protocol": MATRIX_CARRY_FORWARD_PROTOCOL,
        "heldout_outcomes_consumed": False,
        "selection_artifact_schema": ARTIFACT_SCHEMA,
        "selection_artifact_sha256": artifact_sha256,
        "selection_rule": V.PILOT_SELECTION_RULE,
        "pilot_protocol": V.PILOT_PROTOCOL,
        "pilot_protocol_revision": PILOT_PROTOCOL_REVISION,
        "pilot_properties_canonical_sha256": matrix[
            "pilot_properties_digest"
        ],
        "pilot_option_matrix_sha256": V.PILOT_OPTION_MATRIX_SHA256,
        "pilot_selector_configs_sha256": V.PILOT_SELECTOR_CONFIGS_SHA256,
        "selector_eligibility_sha256": V.SELECTOR_ELIGIBILITY_SHA256,
        "pdb_selector_parser_protocol": V.PDB_SELECTOR_PARSER_PROTOCOL,
        "selector_pool_protocol": V.SELECTOR_POOL_PROTOCOL,
        "selector_score_version": V.SELECTOR_SCORE_VERSION,
        "selector_source_order": list(V.SELECTOR_SOURCES),
        "global_winner": matrix["global_winner"]["label"],
        "selector_family_winner": matrix["selector_winner"]["label"],
        "matched_same_k_unbatched": matrix["matched_unbatched"],
        "heldout_protocol": V.PROTOCOL,
        "heldout_task_manifest_sha256": V.MANIFEST_DIGEST,
        "heldout_task_count": V.EXPECTED_TASKS,
        "heldout_run_count": matrix["heldout_run_count"],
        "heldout_array_layout": copy.deepcopy(matrix["heldout_layout"]),
        "heldout_materialized_pddl_protocol": matrix[
            "heldout_materialized_pddl_protocol"
        ],
        "heldout_materialized_pddl_files": matrix[
            "heldout_materialized_pddl_files"
        ],
        "heldout_materialized_pddl_bytes": matrix[
            "heldout_materialized_pddl_bytes"
        ],
        "heldout_pddl_bytes_per_config": matrix[
            "heldout_pddl_bytes_per_config"
        ],
        "heldout_unique_pddl_source_files": matrix[
            "heldout_unique_pddl_source_files"
        ],
        "heldout_unique_pddl_source_bytes": matrix[
            "heldout_unique_pddl_source_bytes"
        ],
        "task_selection_protocol": TASK_SELECTION_PROTOCOL,
        "task_manifest": "suite_wbh_operator_costs.json#supported",
        "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
        "task_count": EXPECTED_TASKS,
        "domain_count": EXPECTED_DOMAINS,
        "domain_sequence_sha256": EXPECTED_DOMAIN_SEQUENCE_SHA256,
        "domain_task_counts_sha256": EXPECTED_DOMAIN_TASK_COUNTS_SHA256,
        "source_manifest_sha256": source_attestation[
            "source_manifest_sha256"
        ],
        "task_sources_sha256": source_attestation["task_sources_sha256"],
        "screen_excluded_task_count": EXPECTED_SCREEN_EXCLUDED_TASKS,
        "screen_excluded_domain_count": EXPECTED_SCREEN_EXCLUDED_DOMAINS,
        "screen_excluded_task_manifest_sha256": (
            EXPECTED_SCREEN_EXCLUDED_TASK_MANIFEST_SHA256
        ),
        "screen_excluded_task_sources_sha256": (
            EXPECTED_SCREEN_EXCLUDED_TASK_SOURCES_SHA256
        ),
        "fixed_configs_sha256": V.FIXED_VALIDATION_CONFIGS_SHA256,
        "config_count": len(matrix["configs"]),
        "option_matrix_sha256": matrix["matrix_digest"],
        "config_roles": copy.deepcopy(matrix["config_records"]),
        "predeclared_comparisons": copy.deepcopy(matrix["comparisons"]),
        "predeclared_comparisons_sha256": matrix["comparisons_digest"],
        "analysis_predeclaration": expected_full_analysis_contract(matrix),
        "completion_policy": copy.deepcopy(FULL_COMPLETION_POLICY),
        "completion_marker_name": FULL_COMPLETION_MARKER,
        "completion_marker_schema": FULL_COMPLETION_MARKER_SCHEMA,
        "completion_marker_protocol": FULL_COMPLETION_MARKER_PROTOCOL,
        "restart_count_file": FULL_RESTART_COUNT_FILE,
        "dynamic_output_recovery": copy.deepcopy(FULL_DYNAMIC_OUTPUT_POLICY),
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
        "scheduler_requeue_requested": True,
        "scheduler_open_mode": "append",
        "scheduler_requeue_scope": (
            "eligible-node-failure-preemption-admin-events-only;"
            "timeout-cancel-oom-and-arbitrary-exit-remain-fail-closed"
        ),
        "array_task_run_distribution": copy.deepcopy(
            matrix["layout"]["array_task_run_distribution"]
        ),
        "array_assignment": attest_exact_array_assignment(matrix["run_count"]),
        "prospective_start_job_sha256": EXPECTED_PROSPECTIVE_JOB_SHA256[
            matrix["run_count"]
        ],
        "planner_preprocess_sha256": cache_preprocess_sha256,
        "experiment_data_directory": "data/{}".format(Path(__file__).stem),
        "benchmark_revision": BENCHMARK_REVISION,
        "benchmark_repository": BENCHMARK_REPOSITORY,
        "benchmark_worktree": str(Path(benchmark_root).resolve()),
    }
    overlap = set(metadata) & set(additions)
    if overlap:
        raise ProtocolError(
            "duplicate full protocol metadata keys: {}".format(
                ", ".join(sorted(overlap))
            )
        )
    metadata.update(additions)
    validate_full_common_protocol_metadata(metadata)
    return metadata


def _require_exact_directive(lines, expected):
    prefix = expected.partition("=")[0] + "="
    matches = [line for line in lines if line.startswith(prefix)]
    if matches != [expected]:
        raise ProtocolError(
            "expected exactly one scheduler directive {!r}; got {!r}".format(
                expected, matches
            )
        )


def assert_exact_full_run_header(environment, job, num_runs):
    layout = validate_full_layout(num_runs)
    lines = job.splitlines()
    if not lines or lines[0] != "#! /bin/bash":
        raise ProtocolError("full Arrhenius jobs require non-login bash")
    if any(line == "#! /bin/bash -l" for line in lines):
        raise ProtocolError("full Arrhenius job retained login-shell bash")
    expected = [
        "#SBATCH --partition={}".format(C.SCHEDULER_PARTITION),
        "#SBATCH --qos={}".format(C.SCHEDULER_QOS),
        "#SBATCH --time={}".format(FULL_SCHEDULER_TIME_LIMITS[num_runs]),
        "#SBATCH --mem-per-cpu={}".format(C.SCHEDULER_MEMORY_PER_CPU),
        "#SBATCH --cpus-per-task={}".format(C.SCHEDULER_CPUS_PER_TASK),
        "#SBATCH --array=1-{}%{}".format(
            layout["array_tasks"], C.ARRAY_TASK_THROTTLE
        ),
        "#SBATCH --account={}".format(C.SCHEDULER_ACCOUNT),
    ]
    for directive in expected:
        _require_exact_directive(lines, directive)
    arrays = [line for line in lines if line.startswith("#SBATCH --array=")]
    if arrays != [expected[5]]:
        raise ProtocolError("full job has a non-exact array directive")
    if lines.count("#SBATCH --requeue") != 1:
        raise ProtocolError("full job must contain exactly one requeue directive")
    if lines.count("#SBATCH --open-mode=append") != 1:
        raise ProtocolError("full job must append scheduler logs exactly")
    if C._RANDOM_RUN_LOOP in job or job.count(C._DETERMINISTIC_RUN_LOOP) != 1:
        raise ProtocolError("full job does not use deterministic inner order")
    if _LEGACY_DRIVER_LOG_SKIP in job or "[[ -f driver.log ]]" in job:
        raise ProtocolError("full job retained Lab's unsafe driver.log skip")
    if job.count(_FULL_STRICT_MARKER_SKIP) != 1:
        raise ProtocolError("full job completion-marker skip changed")
    if job.count(_FULL_ATTEMPT_PREPARATION) != 1:
        raise ProtocolError("full job restart preparation/archive changed")
    if job.count(_FULL_RETCODE_BLOCK) != 1:
        raise ProtocolError("full job wrapper-status propagation changed")
    if job.count(_FULL_DRIVER_REDIRECT) != 1:
        raise ProtocolError("full job wrapper status capture changed")
    if job.count(_FULL_DRIVER_ERR_CLEANUP_AND_MARKER) != 1:
        raise ProtocolError("full job atomic marker creation changed")
    if job.count('exit "$RETCODE"') != 1:
        raise ProtocolError("wrapper subshell does not propagate status exactly")
    if job.count("mktemp \"{}.tmp.XXXXXX\"".format(
        FULL_COMPLETION_MARKER
    )) != 1:
        raise ProtocolError(
            "completion marker must be atomically staged exactly once"
        )
    job_names = [
        line.removeprefix("#SBATCH --job-name=").removesuffix("-02-start")
        for line in lines
        if line.startswith("#SBATCH --job-name=") and line.endswith("-02-start")
    ]
    if len(job_names) != 1:
        raise ProtocolError("full job name/step index changed")
    _, full_loop = _run_loop_blocks(job_names[0])
    if job.count(full_loop) != 1 or job.count('exit "$ARRAY_RETCODE"') != 1:
        raise ProtocolError("full job does not accumulate wrapper failures")
    return layout


class FullArrheniusEnvironment(C.SeededArrheniusEnvironment):
    """Seeded Arrhenius environment with the reviewed full-stage envelope."""

    def _get_run_job_body(self, run_step):
        body = super()._get_run_job_body(run_step)
        if body.count(_LEGACY_DRIVER_LOG_SKIP) != 1:
            raise ProtocolError("Lab driver.log skip template changed")
        body = body.replace(
            _LEGACY_DRIVER_LOG_SKIP,
            _FULL_STRICT_MARKER_SKIP + _FULL_ATTEMPT_PREPARATION,
            1,
        )
        if body.count(_LEGACY_RETCODE_BLOCK) != 1:
            raise ProtocolError("Lab run-wrapper return-code template changed")
        body = body.replace(_LEGACY_RETCODE_BLOCK, _FULL_RETCODE_BLOCK, 1)
        if body.count(_LEGACY_DRIVER_REDIRECT) != 1:
            raise ProtocolError("Lab run-wrapper redirect template changed")
        body = body.replace(_LEGACY_DRIVER_REDIRECT, _FULL_DRIVER_REDIRECT, 1)
        if body.count(_LEGACY_DRIVER_ERR_CLEANUP) != 1:
            raise ProtocolError("Lab driver-error cleanup template changed")
        body = body.replace(
            _LEGACY_DRIVER_ERR_CLEANUP,
            _FULL_DRIVER_ERR_CLEANUP_AND_MARKER,
            1,
        )
        legacy_loop, full_loop = _run_loop_blocks(self.exp.name)
        if body.count(legacy_loop) != 1:
            raise ProtocolError("Lab run-loop template changed")
        return body.replace(legacy_loop, full_loop, 1)

    def _get_job(self, step, is_last):
        # Bypass SeededArrheniusEnvironment._get_job's preliminary-screen
        # envelope assertion.  Its inherited header/body methods still seal the
        # non-login shell, throttle, and deterministic run grouping.
        job = super(C.SeededArrheniusEnvironment, self)._get_job(step, is_last)
        if C.is_run_step(step):
            assert_exact_full_run_header(self, job, len(self.exp.runs))
        return job


def get_full_environment(num_runs):
    validate_fixed_environment()
    validate_full_layout(num_runs)
    environment = FullArrheniusEnvironment(
        email=None,
        partition=C.SCHEDULER_PARTITION,
        qos=C.SCHEDULER_QOS,
        time_limit_per_task=FULL_SCHEDULER_TIME_LIMITS[num_runs],
        memory_per_cpu=C.SCHEDULER_MEMORY_PER_CPU,
        cpus_per_task=C.SCHEDULER_CPUS_PER_TASK,
        extra_options=(
            "#SBATCH --account={}\n#SBATCH --requeue".format(
                C.SCHEDULER_ACCOUNT
            )
        ),
    )
    environment.protocol_account = C.SCHEDULER_ACCOUNT
    return environment


def make_in_memory_full_run_job(num_runs, grid_path=None):
    class FakeBuildStep:
        name = "build"
        _funcname = "build"

    class FakeStartStep:
        name = "start"
        _funcname = "start_runs"

    class FakeExperiment:
        name = "arrhenius-full-header-self-test"
        path = "/tmp/arrhenius-full-header-self-test"

        def __init__(self):
            self.runs = [None] * num_runs
            self.steps = [FakeBuildStep(), FakeStartStep()]

    environment = get_full_environment(num_runs)
    environment.exp = FakeExperiment()
    if grid_path is None:
        environment.job_dir = Path(
            "/tmp/arrhenius-full-header-self-test-grid-steps"
        )
    else:
        grid_path = Path(grid_path)
        environment.exp.name = grid_path.name
        environment.exp.path = str(grid_path)
        environment.job_dir = grid_path.parent / "{}-grid-steps".format(
            grid_path.name
        )
    assignment = attest_exact_array_assignment(num_runs)
    actual_assignment = environment._get_task_order(
        validate_full_layout(num_runs)["array_tasks"]
    )
    if sha256_json(actual_assignment) != assignment[
        "slurm_id_to_logical_group_sha256"
    ]:
        raise ProtocolError(
            "environment array assignment differs from frozen reconstruction"
        )
    job = environment._get_job(environment.exp.steps[1], True)
    return environment, job


def new_full_experiment(protocol_metadata):
    validate_full_common_protocol_metadata(protocol_metadata)
    experiment = C.ProtocolFastDownwardExperiment(
        environment=get_full_environment(protocol_metadata["declared_run_count"]),
        revision_cache=str(C.REVISION_CACHE),
    )
    experiment.protocol_run_properties.update(protocol_metadata)
    experiment.add_parser(experiment.EXITCODE_PARSER)
    experiment.add_parser(experiment.TRANSLATOR_PARSER)
    experiment.add_parser(experiment.SINGLE_SEARCH_PARSER)
    experiment.add_parser(experiment.PLANNER_PARSER)
    experiment.add_parser(C.wbh_parser.get_parser())
    experiment.add_parser(C.get_cofactor_width_parser())
    experiment.add_parser(C.get_pdb_selector_parser())
    experiment.add_parser(C.get_run_log_plan_cost_parser())
    experiment.add_parser(C.get_plan_file_parser())
    experiment.add_parser(get_full_completion_parser())
    experiment.add_parser(C.get_outcome_reconciliation_parser())
    return experiment


def self_test_full_parser_registration():
    """Freeze the full runner's parser inventory and evidence ordering."""

    class FakeExperiment:
        EXITCODE_PARSER = object()
        TRANSLATOR_PARSER = object()
        SINGLE_SEARCH_PARSER = object()
        PLANNER_PARSER = object()

        def __init__(self, **kwargs):
            self.protocol_run_properties = {}
            self.parsers = []

        def add_parser(self, parser):
            self.parsers.append(parser)

    original_experiment = C.ProtocolFastDownwardExperiment
    original_validator = globals()["validate_full_common_protocol_metadata"]
    try:
        C.ProtocolFastDownwardExperiment = FakeExperiment
        globals()["validate_full_common_protocol_metadata"] = lambda metadata: None
        experiment = new_full_experiment(
            {
                "synthetic": True,
                "declared_run_count": EXPECTED_UNBATCHED_RUNS,
            }
        )
    finally:
        C.ProtocolFastDownwardExperiment = original_experiment
        globals()["validate_full_common_protocol_metadata"] = original_validator

    parsers = experiment.parsers
    if parsers[:4] != [
        experiment.EXITCODE_PARSER,
        experiment.TRANSLATOR_PARSER,
        experiment.SINGLE_SEARCH_PARSER,
        experiment.PLANNER_PARSER,
    ]:
        raise AssertionError("standard full parser order changed")

    def function_names(parser):
        return [item.function.__name__ for item in parser.functions]

    expected = [
        ["parse_coverage", "parse_wbh_log"],
        ["parse_cofactor_width"],
        ["parse_pdb_selector_log"],
        ["parse_run_log_plan_cost"],
        [],
        [],
        ["parse_outcome_reconciliation"],
    ]
    actual = [function_names(parser) for parser in parsers[4:]]
    if actual != expected:
        raise AssertionError(
            "full evidence parser order changed: {!r}".format(actual)
        )
    if not isinstance(parsers[8], C.PlanFileParser):
        raise AssertionError("full plan inventory parser is missing")
    if not isinstance(parsers[9], FullCompletionParser):
        raise AssertionError("full completion parser is missing")


def exact_header_assertions(job, num_runs):
    layout = assert_exact_full_run_header(
        SimpleNamespace(
            time_limit_per_task=FULL_SCHEDULER_TIME_LIMITS[num_runs],
            memory_per_cpu=C.SCHEDULER_MEMORY_PER_CPU,
            cpus_per_task=C.SCHEDULER_CPUS_PER_TASK,
            protocol_account=C.SCHEDULER_ACCOUNT,
        ),
        job,
        num_runs,
    )
    return [
        "#! /bin/bash",
        "#SBATCH --partition=cpu",
        "#SBATCH --qos=normal",
        "#SBATCH --time={}".format(FULL_SCHEDULER_TIME_LIMITS[num_runs]),
        "#SBATCH --mem-per-cpu={}".format(C.SCHEDULER_MEMORY_PER_CPU),
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --array=1-{}%{}".format(
            layout["array_tasks"], C.ARRAY_TASK_THROTTLE
        ),
        "#SBATCH --account={}".format(C.SCHEDULER_ACCOUNT),
        "#SBATCH --requeue",
    ]


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
        "run_dir": V._run_relative_path(run_id).as_posix(),
    }
    overlap = set(metadata) & set(generated)
    if overlap:
        raise ProtocolError(
            "protocol metadata overlaps Lab cell fields: {}".format(
                ", ".join(sorted(overlap))
            )
        )
    return {**generated, **metadata}


def _attest_runtime_tree(code_dir):
    if V.PLANNER_REVISION != PLANNER_REVISION:
        raise ProtocolError("held-out/full runtime revision pins differ")
    return V._attest_runtime_tree(code_dir)


def _attest_fresh_start_job(grid_path, num_runs):
    grid_path = Path(grid_path)
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
    _, job = make_in_memory_full_run_job(num_runs, grid_path)
    exact_header_assertions(job, num_runs)
    digest = hashlib.sha256(job.encode("utf-8")).hexdigest()
    if grid_path.resolve() == EXPERIMENT_DATA_PATH.resolve() and digest != (
        EXPECTED_PROSPECTIVE_JOB_SHA256[num_runs]
    ):
        raise ProtocolError(
            "prospective full job SHA-256 changed: expected {}, got {}".format(
                EXPECTED_PROSPECTIVE_JOB_SHA256[num_runs], digest
            )
        )
    return job, digest


def attest_existing_start_grid(
    metadata, benchmark_root, task_descriptions, matrix
):
    """Fail closed unless every byte/cell and the full job are launchable."""
    grid_path = EXPERIMENT_DATA_PATH
    if grid_path.is_symlink() or not grid_path.is_dir():
        raise ProtocolError(
            "start requires an existing regular full grid: {}".format(
                grid_path
            )
        )
    expected_experiment_properties = {
        "algorithms": [label for label, _ in matrix["configs"]],
        "experiment_file": Path(__file__).name,
        "runs": matrix["run_count"],
        "suite": {str(benchmark_root): list(task_descriptions)},
    }
    actual_properties = V._load_json_object(
        grid_path / "static-experiment-properties",
        "static experiment properties",
    )
    V._require_exact_mapping(
        actual_properties,
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
            "full grid must contain exactly one copied code directory {!r}; "
            "got {}".format(expected_code_name, code_entries)
        )
    code_dir = grid_path / expected_code_name
    if code_dir.is_symlink() or not code_dir.is_dir():
        raise ProtocolError(
            "copied code entry must be a regular directory: {}".format(
                code_dir
            )
        )
    V._require_file_sha256(
        code_dir / "build_successful",
        C.CACHE_SENTINEL_SHA256,
        "copied cache success sentinel",
    )
    binary_path = code_dir / "builds" / C.CACHE_BUILD_NAME / "bin" / "downward"
    binary_sha256 = V._require_file_sha256(
        binary_path, CACHE_BINARY_SHA256, "copied planner binary"
    )
    if not os.access(binary_path, os.X_OK):
        raise ProtocolError(
            "copied planner binary is not executable: {}".format(binary_path)
        )
    preprocess_path = (
        code_dir / "builds" / C.CACHE_BUILD_NAME / "bin" / "preprocess"
    )
    preprocess_sha256 = V._require_file_sha256(
        preprocess_path,
        CACHE_PREPROCESS_SHA256,
        "copied preprocess binary",
    )
    if not os.access(preprocess_path, os.X_OK):
        raise ProtocolError(
            "copied preprocess binary is not executable: {}".format(
                preprocess_path
            )
        )
    _attest_runtime_tree(code_dir)

    ordered_tasks = _resolve_ordered_tasks(benchmark_root, task_descriptions)
    source_records = _full_source_records()
    materialized_files = 0
    materialized_bytes = 0
    expected_groups = {
        V._run_relative_path(run_id).parent.name
        for run_id in range(1, matrix["run_count"] + 1)
    }
    actual_groups = {
        path.name for path in grid_path.iterdir() if path.name.startswith("runs-")
    }
    if actual_groups != expected_groups:
        raise ProtocolError("full run-group directory set changed")
    expected_grid_entries = expected_groups | {
        expected_code_name,
        "static-experiment-properties",
    }
    actual_grid_entries = {path.name for path in grid_path.iterdir()}
    if actual_grid_entries != expected_grid_entries:
        raise ProtocolError(
            "full grid entries differ: expected {}, got {}".format(
                sorted(expected_grid_entries), sorted(actual_grid_entries)
            )
        )
    expected_static_paths = {
        grid_path / V._run_relative_path(run_id) / "static-properties"
        for run_id in range(1, matrix["run_count"] + 1)
    }
    actual_static_paths = set(grid_path.glob("runs-*/*/static-properties"))
    if actual_static_paths != expected_static_paths:
        raise ProtocolError(
            "full grid must contain exactly {} static-properties files; got {}".
            format(len(expected_static_paths), len(actual_static_paths))
        )

    seen_ids = set()
    for config_index, (label, search) in enumerate(matrix["configs"]):
        for task_index, task in enumerate(ordered_tasks):
            run_id = config_index * len(ordered_tasks) + task_index + 1
            run_dir = grid_path / V._run_relative_path(run_id)
            V._require_pristine_run_directory(run_dir, run_id)
            properties = V._load_json_object(
                run_dir / "static-properties",
                "static properties for run {}".format(run_id),
            )
            V._require_exact_mapping(
                properties,
                _expected_static_properties(
                    metadata, label, search, task, run_id
                ),
                "static properties for run {}".format(run_id),
            )
            cell_id = tuple(properties["id"])
            if cell_id in seen_ids:
                raise ProtocolError(
                    "duplicate full static cell identity: {}".format(cell_id)
                )
            seen_ids.add(cell_id)

            record = source_records[(task.domain, task.problem)]
            for input_name, source, hash_field in (
                ("domain.pddl", Path(task.domain_file).resolve(), "domain_sha256"),
                ("problem.pddl", Path(task.problem_file).resolve(), "problem_sha256"),
            ):
                materialized_bytes += _require_materialized_pddl(
                    run_dir / input_name,
                    record[hash_field],
                    "run {} {}".format(run_id, input_name),
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
            V._require_regular_file(run_script, "run wrapper")
            try:
                actual_script = run_script.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as err:
                raise ProtocolError(
                    "cannot read run wrapper {}: {}".format(run_script, err)
                ) from err
            if actual_script != V._expected_run_script(argv):
                raise ProtocolError(
                    "run {} wrapper differs from reviewed Lab 8.0 options".
                    format(run_id)
                )

    if len(seen_ids) != matrix["run_count"]:
        raise ProtocolError(
            "full grid has {} identities, expected {}".format(
                len(seen_ids), matrix["run_count"]
            )
        )
    if (
        materialized_files
        != EXPECTED_MATERIALIZED_PDDL_FILES[matrix["run_count"]]
        or materialized_bytes
        != EXPECTED_MATERIALIZED_PDDL_BYTES[matrix["run_count"]]
    ):
        raise ProtocolError(
            "attested materialized PDDL totals changed: files={}, bytes={}".
            format(materialized_files, materialized_bytes)
        )
    for group_name in sorted(expected_groups):
        group = grid_path / group_name
        if group.is_symlink() or not group.is_dir():
            raise ProtocolError("invalid full run-group {}".format(group))
        expected_children = {
            V._run_relative_path(run_id).name
            for run_id in range(1, matrix["run_count"] + 1)
            if V._run_relative_path(run_id).parent.name == group_name
        }
        actual_children = {path.name for path in group.iterdir()}
        if actual_children != expected_children:
            raise ProtocolError(
                "run directories in {} differ from exact full grid".format(
                    group_name
                )
            )
    _, job_sha256 = _attest_fresh_start_job(
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
        "job_sha256": job_sha256,
    }


def inspect_launch_blockers(artifact_sha256):
    checks = (
        (
            "reviewed selection artifact hash",
            lambda: require_selection_artifact_hash(
                artifact_sha256, required=True
            ),
        ),
        ("reviewed P4 planner/screen/cache/job pins", validate_cache_pins),
        (
            "committed planner/full protocol revision",
            lambda: C.require_clean_committed_revision(
                PLANNER_REVISION, protocol_files=PROTOCOL_FILES
            ),
        ),
        ("requirements Lab version", C.require_pinned_lab_version),
        ("release_no_lp P4 revision cache", require_full_revision_cache),
    )
    blockers = []
    for label, check in checks:
        try:
            check()
        except (ProtocolError, V.ProtocolError, RuntimeError) as err:
            blockers.append(
                "{}: {}".format(label, str(err).replace("\n", " | "))
            )
    return blockers


def self_test_preflight_helpers():
    if V.normalize_lab_steps(["parse", "4", "report"]) != [
        "parse",
        "fetch",
        "report",
    ]:
        raise AssertionError("full Lab step normalization changed")
    _expect_protocol_error(
        lambda: V.normalize_lab_steps(["build", "start"]),
        "must run in its own invocation",
    )
    with tempfile.TemporaryDirectory(prefix="selector-full-preflight-") as raw:
        root = Path(raw)
        for run_count, array_tasks in (
            (EXPECTED_UNBATCHED_RUNS, 964),
            (EXPECTED_BATCHED_RUNS, 918),
        ):
            grid = root / "fresh-grid-{}".format(run_count)
            grid.mkdir()
            job, job_sha256 = _attest_fresh_start_job(grid, run_count)
            if hashlib.sha256(job.encode("utf-8")).hexdigest() != job_sha256:
                raise AssertionError("prospective full job hash changed")
            expected_array = "#SBATCH --array=1-{}%5".format(array_tasks)
            if job.splitlines().count(expected_array) != 1:
                raise AssertionError("full array header changed")
            expected_time = FULL_SCHEDULER_TIME_LIMITS[run_count]
            if job.splitlines().count(
                "#SBATCH --time={}".format(expected_time)
            ) != 1:
                raise AssertionError("full scheduler envelope header changed")

        stale_grid = root / "stale-grid"
        stale_grid.mkdir()
        root.joinpath("stale-grid-grid-steps").mkdir()
        _expect_protocol_error(
            lambda: _attest_fresh_start_job(
                stale_grid, EXPECTED_UNBATCHED_RUNS
            ),
            "grid-steps directory already exists",
        )
        evaluated_grid = root / "evaluated-grid"
        evaluated_grid.mkdir()
        Path(str(evaluated_grid) + "-eval").mkdir()
        _expect_protocol_error(
            lambda: _attest_fresh_start_job(
                evaluated_grid, EXPECTED_UNBATCHED_RUNS
            ),
            "evaluation directory already exists",
        )
        fresh_build = root / "fresh-build"
        C.require_fresh_experiment_build(fresh_build)
        fresh_build.mkdir()
        _expect_protocol_error(
            lambda: C.require_fresh_experiment_build(fresh_build),
            "experiment output path already exists",
        )
        sibling_build = root / "sibling-build"
        root.joinpath("sibling-build-grid-steps").mkdir()
        _expect_protocol_error(
            lambda: C.require_fresh_experiment_build(sibling_build),
            "experiment output path already exists",
        )
        evaluated_build = root / "evaluated-build"
        Path(str(evaluated_build) + "-eval").mkdir()
        _expect_protocol_error(
            lambda: C.require_fresh_experiment_build(evaluated_build),
            "experiment output path already exists",
        )

        bytecode_grid = root / "bytecode-grid"
        cache = bytecode_grid / "code-fixture" / "driver" / "__pycache__"
        cache.mkdir(parents=True)
        (cache.parent / "module.py").write_bytes(b"x = 1\n")
        (cache / "module.cpython-39.pyc").write_bytes(b"bytecode")
        cleanup = C.strip_copied_python_bytecode(bytecode_grid)
        if cleanup["removed_bytecode_files"] != 1:
            raise AssertionError("full copied-bytecode cleanup changed")
        C.reject_unattested_python_runtime_artifacts(
            bytecode_grid / "code-fixture"
        )

        source = root / "source.pddl"
        source.write_bytes(b"(define (problem frozen-source))\n")
        expected_source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        materialized = root / "materialized.pddl"
        materialized.symlink_to(source)
        copied_bytes = _materialize_one_pddl(
            materialized, source, expected_source_sha, "synthetic PDDL"
        )
        if (
            copied_bytes != source.stat().st_size
            or materialized.is_symlink()
            or materialized.read_bytes() != source.read_bytes()
            or materialized.stat().st_ino == source.stat().st_ino
            or materialized.stat().st_nlink != 1
            or materialized.stat().st_mode & 0o222
        ):
            raise AssertionError("independent PDDL materialization changed")
        materialized.chmod(0o644)
        materialized.write_bytes(b"changed bytes")
        materialized.chmod(0o444)
        _expect_protocol_error(
            lambda: _require_materialized_pddl(
                materialized,
                expected_source_sha,
                "tampered synthetic PDDL",
                source,
            ),
            "SHA-256 changed",
        )
        materialized.chmod(0o644)
        materialized.unlink()
        materialized.symlink_to(source)
        _expect_protocol_error(
            lambda: _require_materialized_pddl(
                materialized,
                expected_source_sha,
                "symlink synthetic PDDL",
                source,
            ),
            "regular non-symlink",
        )
        materialized.unlink()
        os.link(source, materialized)
        _expect_protocol_error(
            lambda: _require_materialized_pddl(
                materialized,
                expected_source_sha,
                "hardlink synthetic PDDL",
                source,
            ),
            "must not be a hardlink",
        )

        marker_bytes = _full_completion_marker_bytes(1, 0)
        if _parse_full_completion_marker(marker_bytes, 1)[
            "completion_slurm_restart_count"
        ] != 0:
            raise AssertionError("canonical completion marker parse changed")
        for bad_marker in (
            marker_bytes.rstrip(b"\n"),
            marker_bytes + b"\x00",
            marker_bytes.replace(b"run_id=1", b"run_id=01"),
        ):
            _expect_protocol_error(
                lambda value=bad_marker: _parse_full_completion_marker(value, 1)
            )
        _expect_protocol_error(
            lambda: _parse_full_completion_marker(marker_bytes, 2),
            "differs",
        )

        valid_run = root / "00001"
        valid_run.mkdir()
        (valid_run / FULL_COMPLETION_MARKER).write_bytes(marker_bytes)
        (valid_run / FULL_RESTART_COUNT_FILE).write_text("0\n", encoding="ascii")
        valid_props = {}
        FullCompletionParser().parse(valid_run, valid_props)
        if (
            valid_props.get("full_completion_marker_valid") is not True
            or valid_props.get("full_wrapper_run_id") != 1
            or valid_props.get("full_wrapper_exit_code") != 0
            or valid_props.get("full_partial_archive_count") != 0
        ):
            raise AssertionError("valid completion parser properties changed")

        retry_run = root / "00002"
        retry_run.mkdir()
        (retry_run / FULL_COMPLETION_MARKER).write_bytes(
            _full_completion_marker_bytes(2, 3)
        )
        (retry_run / FULL_RESTART_COUNT_FILE).write_text("3\n", encoding="ascii")
        for archive_id, prior_restart in ((1, 0), (3, 1)):
            archive = retry_run / "{}{:05d}".format(
                FULL_PARTIAL_ARCHIVE_PREFIX, archive_id
            )
            archive.mkdir()
            (archive / FULL_RESTART_COUNT_FILE).write_text(
                "{}\n".format(prior_restart), encoding="ascii"
            )
            (archive / "run.log").write_text("partial\n", encoding="ascii")
        retry_props = {}
        FullCompletionParser().parse(retry_run, retry_props)
        if (
            retry_props.get("full_completion_marker_valid") is not True
            or retry_props.get("full_partial_archive_count") != 2
            or retry_props.get("full_descriptive_cell_execution_count") != 3
        ):
            raise AssertionError("retry completion parser properties changed")
        corrupt_archive = retry_run / (
            FULL_PARTIAL_ARCHIVE_PREFIX + "00004"
        )
        corrupt_archive.symlink_to(retry_run / "missing-archive")
        corrupt_props = {}
        FullCompletionParser().parse(retry_run, corrupt_props)
        if corrupt_props.get("full_completion_marker_valid") is not False:
            raise AssertionError("corrupt partial archive was accepted")

        missing_run = root / "00003"
        missing_run.mkdir()
        missing_props = {}
        FullCompletionParser().parse(missing_run, missing_props)
        if missing_props.get("full_completion_marker_valid") is not False:
            raise AssertionError("missing completion marker was accepted")
        marker_target = root / "marker-target"
        marker_target.write_bytes(_full_completion_marker_bytes(4, 0))
        symlink_run = root / "00004"
        symlink_run.mkdir()
        (symlink_run / FULL_COMPLETION_MARKER).symlink_to(marker_target)
        (symlink_run / FULL_RESTART_COUNT_FILE).write_text("0\n", encoding="ascii")
        symlink_props = {}
        FullCompletionParser().parse(symlink_run, symlink_props)
        if symlink_props.get("full_completion_marker_valid") is not False:
            raise AssertionError("symlink completion marker was accepted")


def self_test():
    validate_fixed_environment()
    self_test_full_parser_registration()
    _expect_protocol_error(
        validate_cache_pins, "P4 screen protocol revision is unset"
    )
    tasks, records = read_full_tasks()
    if (
        records["task_manifest_sha256"] != EXPECTED_TASK_MANIFEST_SHA256
        or records["domain_sequence_sha256"]
        != EXPECTED_DOMAIN_SEQUENCE_SHA256
        or records["domain_task_counts_sha256"]
        != EXPECTED_DOMAIN_TASK_COUNTS_SHA256
        or records["task_sources_sha256"] != EXPECTED_TASK_SOURCES_SHA256
        or records["screen_excluded_task_manifest_sha256"]
        != EXPECTED_SCREEN_EXCLUDED_TASK_MANIFEST_SHA256
        or records["screen_excluded_task_sources_sha256"]
        != EXPECTED_SCREEN_EXCLUDED_TASK_SOURCES_SHA256
        or records["source_manifest_sha256"]
        != EXPECTED_SOURCE_MANIFEST_SHA256
    ):
        raise AssertionError("full task/source digest pins changed")

    unbatched = V._synthetic_artifact("ms_cap32", "pdb_selector_k32")
    unbatched_matrix = validate_selection_artifact(unbatched)
    validate_matrix(tasks, unbatched_matrix)
    if (
        len(unbatched_matrix["configs"]) != 7
        or unbatched_matrix["heldout_run_count"] != 644
        or unbatched_matrix["run_count"] != EXPECTED_UNBATCHED_RUNS
        or unbatched_matrix["layout"]["runs_per_array_task"] != 10
        or unbatched_matrix["layout"]["array_tasks"] != 964
        or unbatched_matrix["layout"]["array_task_run_distribution"]
        != {
            "full_array_tasks": 963,
            "full_runs_per_array_task": 10,
            "partial_array_tasks": 1,
            "partial_runs": 9,
        }
    ):
        raise AssertionError("full 7-config carry-forward changed")

    batched_label = "pdb_selector_k64_adapt_w64_r1_n1m"
    batched = V._synthetic_artifact(batched_label, batched_label)
    batched_matrix = validate_selection_artifact(batched)
    validate_matrix(tasks, batched_matrix)
    if (
        len(batched_matrix["configs"]) != 8
        or batched_matrix["heldout_run_count"] != 736
        or batched_matrix["run_count"] != EXPECTED_BATCHED_RUNS
        or batched_matrix["layout"]["runs_per_array_task"] != 12
        or batched_matrix["layout"]["array_tasks"] != 918
        or batched_matrix["layout"]["array_task_run_distribution"]
        != {
            "full_array_tasks": 918,
            "full_runs_per_array_task": 12,
            "partial_array_tasks": 0,
            "partial_runs": 0,
        }
    ):
        raise AssertionError("full 8-config carry-forward changed")

    for matrix in (unbatched_matrix, batched_matrix):
        analysis = expected_full_analysis_contract(matrix)
        sensitivity = analysis["sole_predeclared_sensitivity"]
        if (
            analysis["rerank_on_full_population"] is not False
            or analysis["carried_comparisons"] != matrix["comparisons"]
            or analysis["carried_comparisons_sha256"]
            != matrix["comparisons_digest"]
            or sensitivity["task_count"] != 1327
            or sensitivity["called_unseen"] is not False
            or analysis["completion_policy"] != FULL_COMPLETION_POLICY
        ):
            raise AssertionError("full analysis predeclaration changed")
        assignment = attest_exact_array_assignment(matrix["run_count"])
        if assignment["slurm_id_to_logical_group_sha256"] != (
            EXPECTED_ARRAY_ASSIGNMENT_SHA256[matrix["run_count"]]
        ):
            raise AssertionError("full array-assignment pin changed")

    synthetic_metadata = make_protocol_metadata(
        unbatched_matrix,
        hashlib.sha256(b"synthetic full selection").hexdigest(),
        C.REPO,
        {
            "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
        },
        planner_revision=C.REV,
        cache_binary_sha256=hashlib.sha256(
            b"synthetic full binary"
        ).hexdigest(),
        cache_preprocess_sha256=hashlib.sha256(
            b"synthetic full preprocess"
        ).hexdigest(),
    )
    required_full_metadata = {
        "analysis_protocol": FULL_ANALYSIS_PROTOCOL,
        "completion_marker_schema": FULL_COMPLETION_MARKER_SCHEMA,
        "completion_marker_protocol": FULL_COMPLETION_MARKER_PROTOCOL,
        "scheduler_requeue_requested": True,
        "scheduler_open_mode": "append",
        "materialized_pddl_protocol": MATERIALIZED_PDDL_PROTOCOL,
        "planner_limit_basis": "aggregate-process-cpu",
        "per_cell_wall_limit_enforced": False,
        "scheduler_timeout_invalidates_census": True,
    }
    if any(
        synthetic_metadata.get(key) != value
        for key, value in required_full_metadata.items()
    ):
        raise AssertionError("full static analysis/recovery metadata changed")
    if set(FULL_COMPLETION_ATTRIBUTES) != {
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
    }:
        raise AssertionError("full fetched/report recovery attributes changed")

    changed = copy.deepcopy(unbatched)
    changed["validation"]["configs"][0]["search"] = "sym_fw_ms()"
    _expect_protocol_error(
        lambda: validate_selection_artifact(changed),
        "independent reconstruction",
    )
    changed = copy.deepcopy(unbatched)
    changed["selection"]["ranking"].reverse()
    _expect_protocol_error(lambda: validate_selection_artifact(changed))
    changed = copy.deepcopy(unbatched)
    changed["validation"]["option_matrix_sha256"] = hashlib.sha256(
        b"tampered"
    ).hexdigest()
    _expect_protocol_error(lambda: validate_selection_artifact(changed))

    synthetic_sha = hashlib.sha256(
        (canonical_json(unbatched) + "\n").encode("ascii")
    ).hexdigest()
    require_selection_artifact_hash(
        synthetic_sha,
        required=True,
        expected_sha256=synthetic_sha,
    )
    _expect_protocol_error(
        lambda: require_selection_artifact_hash(
            synthetic_sha, required=True, expected_sha256=None
        ),
        "is unset",
    )

    for matrix in (unbatched_matrix, batched_matrix):
        _, job = make_in_memory_full_run_job(matrix["run_count"])
        for line in exact_header_assertions(job, matrix["run_count"]):
            if job.splitlines().count(line) != 1:
                raise AssertionError(
                    "full job does not contain one exact {!r}".format(line)
                )
        _, production_job = make_in_memory_full_run_job(
            matrix["run_count"], EXPERIMENT_DATA_PATH
        )
        production_digest = hashlib.sha256(
            production_job.encode("utf-8")
        ).hexdigest()
        if not re.fullmatch(r"[0-9a-f]{64}", production_digest):
            raise AssertionError("synthetic production full job digest malformed")
        if EXPECTED_PROSPECTIVE_JOB_SHA256[matrix["run_count"]] is not None:
            raise AssertionError("prospective P4 full job pin must remain unset")
    self_test_preflight_helpers()
    print(
        "Arrhenius selector full runner self-test: PASS "
        "(artifact tampering; frozen 1377-task sources; 7/8 configs; "
        "9639/11016 cells; 70/75-minute <=1000 arrays; fresh/no-submit gates)"
    )
    if EXPECTED_SELECTION_ARTIFACT_SHA256 is None:
        print("launch gate: BLOCKED (EXPECTED_SELECTION_ARTIFACT_SHA256 is unset)")
    else:
        print("launch gate: artifact hash pinned")


def check_protocol(
    tasks,
    matrix,
    artifact_sha256,
    artifact_path,
    benchmark_root,
    source_attestation,
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
    preprocess_sha256 = (
        V._sha256_file(cached_preprocessor)
        if cached_preprocessor is not None and cached_preprocessor.is_file()
        else None
    )
    blockers = inspect_launch_blockers(artifact_sha256)
    _, job = make_in_memory_full_run_job(matrix["run_count"])
    headers = exact_header_assertions(job, matrix["run_count"])
    print("Arrhenius selector full-population read-only check: PASS")
    print("selection artifact: {}".format(artifact_path))
    print("selection artifact raw SHA-256: {}".format(artifact_sha256))
    print("held-out outcomes consumed: false")
    print("global winner alias: {}".format(matrix["global_winner"]["label"]))
    print(
        "selector-family winner: {}".format(
            matrix["selector_winner"]["label"]
        )
    )
    print("same-K unbatched: {}".format(matrix["matched_unbatched"]))
    print(
        "tasks: {}; configs: {}; runs: {}; array tasks: {}; runs/array: {}".
        format(
            len(tasks),
            len(matrix["configs"]),
            matrix["run_count"],
            matrix["layout"]["array_tasks"],
            matrix["layout"]["runs_per_array_task"],
        )
    )
    print("full task-list SHA-256: {}".format(EXPECTED_TASK_MANIFEST_SHA256))
    print("full ordered-domain SHA-256: {}".format(
        EXPECTED_DOMAIN_SEQUENCE_SHA256
    ))
    print("full domain-count-vector SHA-256: {}".format(
        EXPECTED_DOMAIN_TASK_COUNTS_SHA256
    ))
    print(
        "full source-record/byte SHA-256: {}".format(
            source_attestation["task_sources_sha256"]
        )
    )
    print("unchanged held-out matrix SHA-256: {}".format(matrix["matrix_digest"]))
    print("benchmark revision/worktree: {} {}".format(
        BENCHMARK_REVISION, benchmark_root
    ))
    print("revision cache: {}".format(
        cache_info["path"] if cache_info is not None else "UNSET"
    ))
    print("cached binary SHA-256: {}".format(
        cache_info["binary_sha256"] if cache_info is not None else "UNSET"
    ))
    print("cached preprocess SHA-256: {}".format(preprocess_sha256))
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
            "--selection is required; full execution has no default winner"
        )
    if not args.check and not args.steps:
        raise ProtocolError("provide Lab steps, --check, or --self-test")

    artifact, artifact_sha256, artifact_path = V.load_selection_artifact(
        args.selection
    )
    matrix = validate_selection_artifact(artifact)
    launch_requested = any(step in ("build", "start") for step in args.steps)
    require_selection_artifact_hash(
        artifact_sha256, required=launch_requested
    )
    tasks, record_attestation = read_full_tasks()
    validate_matrix(tasks, matrix)
    benchmark_root = require_pinned_benchmark_worktree()
    source_attestation = attest_task_sources(benchmark_root, tasks)
    if (
        source_attestation["task_sources_sha256"]
        != record_attestation["task_sources_sha256"]
        or source_attestation["source_manifest_sha256"]
        != record_attestation["source_manifest_sha256"]
    ):
        raise ProtocolError("full source records and source-byte attestation differ")

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
        require_full_revision_cache()
    _, job = make_in_memory_full_run_job(matrix["run_count"])
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

    experiment = new_full_experiment(metadata)
    if Path(experiment.path).resolve() != EXPERIMENT_DATA_PATH:
        raise ProtocolError(
            "full experiment data path changed: {} != {}".format(
                Path(experiment.path).resolve(), EXPERIMENT_DATA_PATH
            )
        )
    C.add_suite(experiment, benchmark_root, tasks)
    for label, search in matrix["configs"]:
        C.add_algorithm(
            experiment, label, search, revision=PLANNER_REVISION
        )
    C.add_standard_steps(
        experiment, extra_attributes=FULL_COMPLETION_ATTRIBUTES
    )
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
            "built full grid normalization/attestation: PASS "
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
    except (ProtocolError, V.ProtocolError, RuntimeError) as err:
        print("protocol error: {}".format(err), file=sys.stderr)
        sys.exit(2)
