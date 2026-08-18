#!/usr/bin/env python3
"""Render frozen full-population results into deterministic paper data.

This program is intentionally a fail-closed consumer of the canonical P6
analysis and separately frozen secondary structural diagnostic.  It does not
read Lab evaluations.  Instead, it verifies both artifacts, independently
checks the identities and arithmetic used by the paper, and emits a canonical
JSON view or deterministic TeX macros.

Ordinary use is enabled only because both P6 artifact digests and every launch
identity have been atomically reviewed and pinned.  The ``--self-test`` path
uses synthetic results produced by the current analyzers without weakening
that production gate.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import stat
import sys
import tempfile
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path


class RenderError(RuntimeError):
    """The analysis artifact cannot safely be rendered."""


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR
    / "artifacts"
    / "arrhenius-selector-full-p6"
    / "analysis-v4.json"
)
DEFAULT_STRUCTURE = (
    SCRIPT_DIR
    / "artifacts"
    / "arrhenius-selector-full-p6"
    / "structure-v1.json"
)
DEFAULT_STRUCTURE_SIDECAR = Path(str(DEFAULT_STRUCTURE) + ".sha256")
P5_ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "arrhenius-selector-heldout-p5"
)
DEFAULT_P5_ANALYSIS = P5_ARTIFACT_DIR / "analysis-v3.json"
DEFAULT_P5_SIDECAR = Path(str(DEFAULT_P5_ANALYSIS) + ".sha256")
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "arrhenius-selector-full-v4.tex"
)

# These two digests and the five mutable launch identities below were frozen
# together only after the complete artifacts, sidecars, raw execution census,
# and ordinary analyzers passed independent review.  Any future partial pin
# state remains a hard error.
EXPECTED_FULL_ANALYSIS_SHA256 = (
    "39958f1984d9c33fc2717ef221881751e24dc68434932b6ea9b92e4dd3f2b1c5"
)
EXPECTED_FULL_STRUCTURE_SHA256 = (
    "bde07d0d2e279b5f8e06b5e59eb67aa7f513a1fae58f101fa0e87bc01030cc69"
)

EXPECTED_P5_ANALYSIS_SHA256 = (
    "7c598f068164224272b8ba035b987973f35d0d45e695f90c9083931790908cea"
)
P5_ANALYSIS_SCHEMA = (
    "symbolic-search-heuristics/arrhenius-selector-heldout-analysis/v3"
)
P5_ANALYSIS_PROTOCOL = "paired-domain-macro-coverage-sha256-bootstrap-v1"
P5_PROTOCOL = "arrhenius-selector-heldout-validation-v3"
P5_TASKS = 92
P5_DOMAINS = 46
P5_CONFIG_COUNT = 7
P5_CELLS = 644
P5_MATERIALIZED_PDDL_PROTOCOL = (
    "per-cell-independent-manual-byte-copy-temp-digest-atomic-replace-readonly/v1"
)
P5_MATERIALIZED_PDDL_FILES = 1288
P5_MATERIALIZED_PDDL_BYTES = 72541896
EXPECTED_P5_PROPERTIES_SHA256 = (
    "0fab37f024188138f0ef2c1468bfe688404243f05cf682212532adf6e200cab1"
)
P5_PAPER_INPUT_SCHEMA = "symbolic-search-heuristics/heldout-paper-input/v1"
COMBINED_STAGE_CAVEAT = (
    "P5 and P6 entries are within-stage descriptive summaries with different "
    "task sets and stage denominators; no row is a between-stage causal contrast."
)

ANALYSIS_SCHEMA = "symbolic-search-heuristics/full-population-analysis/v4"
ANALYSIS_PROTOCOL = "full-supported-population-census-v1"
PAPER_DATA_SCHEMA = "symbolic-search-heuristics/full-paper-data/v3"
STRUCTURE_SCHEMA = "symbolic-search-heuristics/full-population-structure/v1"
STRUCTURE_PROTOCOL = "p6-secondary-structural-diagnostic/v1"
STRUCTURE_DECISION_LABEL = (
    "secondary-structural-diagnostic-specified-during-execution-not-launch-"
    "predeclared"
)
STRUCTURE_SPECIFICATION_BOUNDARY = (
    "frozen-during-active-p6-execution-before-canonical-full-result-analysis/v1"
)
STRUCTURE_TIMING_CAVEAT = (
    "This secondary structural diagnostic was specified during P6 execution, "
    "before any comparative structural summary, association, or correlation "
    "was computed. Protocol audits had already parsed individual structural "
    "fields and displayed a few diagnostic records. The diagnostic was not "
    "launch-predeclared and cannot alter the primary analysis."
)
STRUCTURE_INFERENCE_CAVEAT = (
    "Its cross-task correlations are descriptive and confounded: there are no "
    "inferential, causal, or theorem-validation claims and no p-values or "
    "confidence intervals."
)
STRUCTURE_RESOURCE_PREFIX_CAVEAT = (
    "Certified resource-prefix partition ratios are censored observed-prefix "
    "summaries only and are kept separate from complete WBH logs, which do not "
    "necessarily imply complete searches."
)
# The corrected full-only rerun will use v4.  Its launch-derived identities
# must be reviewed together after the clean launch revision and fresh cache
# exist; none of the canceled v3 identities may leak into ordinary rendering.
FULL_PROTOCOL = "arrhenius-selector-full-population-v4"
SELECTION_SCHEMA = (
    "symbolic-search-heuristics/arrhenius-selector-screen-selection/v3"
)
PRIMARY_COMPARISON = "selector-vs-pdb-cegar"
PRIMARY_ESTIMAND = (
    "selector-minus-cegar-equally-weighted-46-domain-macro-coverage/v1"
)
COMPLETION_PROTOCOL = (
    "canonical-four-line-marker-atomic-after-python-wrapper-zero-exit/v1"
)
ATTEMPT_SEMANTICS = (
    "shell-cell-attempt-generations-not-guaranteed-planner-invocations/v1"
)
TERMINAL_OUTCOME_CENSUS_PROTOCOL = (
    "protocol-recognized-final-cell-outcome-census/v1"
)
TERMINAL_OUTCOME_CENSUS_UNIT = "final-retained-attested-cell-records"
TERMINAL_OUTCOME_UNIT_NOTE = (
    "Counts are final retained attested cell records, never cell attempts "
    "or planner invocations."
)
TERMINAL_OUTCOME_CODE_21_CAVEAT = (
    "Exit code 21 is the canonical pre-search time result and the "
    "normalization target. Its aggregate cannot identify translator versus "
    "legacy preprocessor and does not establish that every code-21 record "
    "was caused by SIGXCPU."
)
TERMINAL_OUTCOME_SPECS = (
    (0, "success", False, 0, 0),
    (1, "search-plan-found-and-out-of-memory", False, 22, 1),
    (2, "search-plan-found-and-out-of-time", False, 23, 2),
    (3, "search-plan-found-and-out-of-memory-and-time", False, 24, 3),
    (10, "translate-unsolvable", True, None, None),
    (11, "search-unsolvable", False, 11, 11),
    (12, "search-unsolvable-incomplete", False, 12, 12),
    (20, "translate-out-of-memory", True, None, None),
    (21, "translate-out-of-time", True, None, None),
    (22, "search-out-of-memory", False, 22, 22),
    (23, "search-out-of-time", False, 23, 23),
    (24, "search-out-of-memory-and-time", False, 24, 24),
)
TERMINAL_OUTCOME_CODES = tuple(item[0] for item in TERMINAL_OUTCOME_SPECS)
TERMINAL_OUTCOME_CODE_SUFFIXES = (
    (0, "Zero"),
    (1, "One"),
    (2, "Two"),
    (3, "Three"),
    (10, "Ten"),
    (11, "Eleven"),
    (12, "Twelve"),
    (20, "Twenty"),
    (21, "TwentyOne"),
    (22, "TwentyTwo"),
    (23, "TwentyThree"),
    (24, "TwentyFour"),
)

EXPECTED_SELECTION_ARTIFACT_SHA256 = (
    "d35a1df68eebbd099fe81f86e6e0f6a96ce770572574f9ae013ab4eb0b2c8eb2"
)
# These five review-derived launch identities are deliberately unset.  Freeze
# them together with the analysis and structure SHA-256 values (seven mutable
# pins total) after the
# corrected v4 launch; partial pinning is rejected.  The P6 source revision is
# already fixed independently.
EXPECTED_PROTOCOL_REVISION = "0cb19e111da36fbb32d1b3bc0f07a52b733fbbe9"
EXPECTED_FULL_RUNNER_SHA256 = (
    "3a7cfd4307217db13a8ec42d9157cd2290b0e8fba962f9aa40815af80d06058f"
)
EXPECTED_PLANNER_REVISION = "a3486a027a0f281e762cb6d66d72311455b66b33"
EXPECTED_PLANNER_BINARY_SHA256 = (
    "2887194c74acc88273702b807dba28e4fd8f7ae3d916562bcf1b83ec79632758"
)
EXPECTED_PLANNER_PREPROCESS_SHA256 = (
    "40e1d5580ec447cb606ead447317469bd861bd8cda398095df3fbf22922d0d23"
)
EXPECTED_INITIAL_DEAD_PROTOCOL = (
    "pdb-ms-initial-dead-bdd-construction-prelog/v1"
)
EXPECTED_P5_HELDOUT_PROTOCOL_REVISION = (
    "a52488637a1c054b26dac93fe2eb1a556110a2dd"
)
EXPECTED_P5_HELDOUT_PLANNER_REVISION = (
    "165b6d2ee29d5d7b6e1bf4c52540c393ba19b54f"
)
EXPECTED_P5_HELDOUT_BINARY_SHA256 = (
    "af2a19d236ecad9b747d2a1b9c49da73d98248c38d21cc60ad0ac7613d74bdbe"
)
EXPECTED_P5_HELDOUT_PREPROCESS_SHA256 = (
    "1b351a4a5f9380bf41fe9fd61b98c816505ebd8cf88b20afa0d81a9bfb2474bd"
)
EXPECTED_P5_TO_P6_LINEAGE_PROTOCOL = (
    "git-merge-base-is-ancestor/p5-protocol-and-planner-to-p6-planner/v1"
)
EXPECTED_PRESEARCH_SIGXCPU_PROTOCOL = (
    "driver-translate-and-legacy-preprocess-negative-sigxcpu-to-21/v1"
)
EXPECTED_PRESEARCH_SIGXCPU_RAW_EXIT = -24
EXPECTED_PRESEARCH_SIGXCPU_EFFECTIVE_EXIT = 21
EXPECTED_PRESEARCH_SIGXCPU_COMPONENTS = ["translate", "preprocess"]
EXPECTED_BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
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
EXPECTED_OPTION_MATRIX_SHA256 = (
    "b4a695874c1292a0a26cc72ab7ebeea2b6775eec71970cd1b91aaad1c8211354"
)
EXPECTED_COMPARISONS_SHA256 = (
    "740b2e89f877dbef6bc71eb9b650eb19e73cf6b6d800a89da18d6a668af64326"
)
EXPECTED_PROSPECTIVE_JOB_SHA256 = (
    "c83c880c1bfaa503cfffab69c91abb037e58b4424b7216480aa551631aed043f"
)
EXPECTED_PILOT_REVISION = "58a3f742d7ac63f391d06c237573f14ad590c187"
EXPECTED_PILOT_BINARY_SHA256 = (
    "59b97e8b1e777f700c255932271604393f60ec9aeba5c0151d0b7415a3a58511"
)
EXPECTED_PILOT_PREPROCESS_SHA256 = (
    "acf2fc66c0b189095111a9d227ccb5b7acc564f1a6cb7bfd557904fa3c76798c"
)
EXPECTED_SENSITIVITY_TASK_SHA256 = (
    "1e126791b438d903cb6adcc441391b92d76a7e14cf46f6a89465a066823a986f"
)
EXPECTED_SENSITIVITY_SOURCES_SHA256 = (
    "158e5446e3b97ddd63095441c518ecbe6d2e3ce3529aa9a8fd412df23e706068"
)
EXPECTED_HELDOUT_TASK_SHA256 = (
    "fc63d4eed62816a2e065cb89f89483999a7b51067b7077969d10b2a338f19760"
)
EXPECTED_HELDOUT_SOURCES_SHA256 = (
    "14202b66a4ed4ea7afa9f204d15cbfe8857b061a644661fc9d68b3624523fdf4"
)

TASKS = 1377
DOMAINS = 46
CONFIG_COUNT = 7
CELLS = 9639
SENSITIVITY_TASKS = 1327
PAR2_PENALTY = 600
MAX_ARTIFACT_BYTES = 32 * 1024 * 1024
SHA256_HEX = set("0123456789abcdef")

CONFIGS = (
    {
        "label": "blind_fw",
        "suffix": "Blind",
        "paper_label": "Blind forward",
        "search": "sym_fw()",
        "roles": ["fixed-blind-control"],
    },
    {
        "label": "ms_exact",
        "suffix": "MsExact",
        "paper_label": "Uncapped M\\&S",
        "search": (
            "sym_fw_ms(max_states=10000,value_cap=-1,"
            "align_merge_order=false)"
        ),
        "roles": ["fixed-ms-exact-control", "pilot-global-winner"],
    },
    {
        "label": "ms_cap32",
        "suffix": "MsCap",
        "paper_label": "M\\&S, finite-value cap 32",
        "search": (
            "sym_fw_ms(max_states=10000,value_cap=32,"
            "align_merge_order=false)"
        ),
        "roles": ["fixed-ms-cap32-control"],
    },
    {
        "label": "pdb_goal_fill_b100k",
        "suffix": "GoalFill",
        "paper_label": "Goal-fill PDB",
        "search": "sym_fw_pdb(budget=100000,pattern_selection=goal_fill)",
        "roles": ["fixed-pdb-goal-fill-control"],
    },
    {
        "label": "pdb_cegar_b100k",
        "suffix": "Cegar",
        "paper_label": "CEGAR PDB",
        "search": (
            "sym_fw_pdb(budget=100000,pattern_selection=cegar,"
            "cegar_max_time=10,cegar_seed=2011)"
        ),
        "roles": ["fixed-pdb-cegar-control"],
    },
    {
        "label": "ms_cap32_build60",
        "suffix": "MsBuild",
        "paper_label": "M\\&S, value cap 32, 60-s build",
        "search": (
            "sym_fw_ms(max_states=10000,value_cap=32,"
            "align_merge_order=false,build_time_limit=60)"
        ),
        "roles": ["predeclared-ms-build-budget-safeguard"],
    },
    {
        "label": "pdb_selector_k1",
        "suffix": "Selector",
        "paper_label": "Selector $K=1$",
        "search": (
            "sym_fw_pdb(budget=100000,"
            "pattern_selection=exact_width_filter,"
            "cofactor_width_budget=1,cegar_max_time=10,cegar_seed=2011)"
        ),
        "roles": ["pilot-selector-family-winner"],
    },
)
CONFIG_BY_LABEL = {item["label"]: item for item in CONFIGS}
CONFIG_LABELS = tuple(item["label"] for item in CONFIGS)

COMPARISONS = (
    (
        "selector-vs-pdb-cegar",
        "pdb_selector_k1",
        "pdb_cegar_b100k",
        ["primary-selector-contrast"],
    ),
    (
        "selector-vs-pdb-goal-fill",
        "pdb_selector_k1",
        "pdb_goal_fill_b100k",
        ["secondary-matched-pdb-contrast"],
    ),
    (
        "ms-cap32-build60-vs-unbounded-build",
        "ms_cap32_build60",
        "ms_cap32",
        ["primary-setup-safeguard-contrast"],
    ),
    (
        "global-winner-vs-blind-forward",
        "ms_exact",
        "blind_fw",
        ["heldout-global-winner-context"],
    ),
    (
        "selector-vs-blind-fw",
        "pdb_selector_k1",
        "blind_fw",
        ["heldout-selector-context"],
    ),
    (
        "selector-vs-ms-exact",
        "pdb_selector_k1",
        "ms_exact",
        ["heldout-selector-context"],
    ),
    (
        "selector-vs-ms-cap32",
        "pdb_selector_k1",
        "ms_cap32",
        ["heldout-selector-context"],
    ),
)

P5_PRIMARY_ESTIMAND = (
    "selector-minus-cegar-equally-weighted-domain-macro-coverage/v1"
)
P5_METRIC_PROTOCOLS = {
    "certified_prefix_metrics": (
        "schema-v2-piece-certified-event-prefix;"
        "complete-summary-denominator-reported-separately/v1"
    ),
    "fallback_incidence": (
        "construction_completed=false/ms-cap32-build60-cells/v1"
    ),
    "jointly_solved_runtime_ratio": (
        "geometric-mean(candidate-planner-time/reference-planner-time);"
        "strictly-positive-jointly-solved-cells/v1"
    ),
    "micro_par2": "mean(solved-planner-time;unsolved=600s)/v1",
    "paired_operational_ratios": (
        "ratio-of-paired-totals-with-explicit-pair-count/v1"
    ),
    "suite_micro_coverage": "solved-cells/92/v1",
}
P5_TOP_KEYS = {
    "analysis_protocol",
    "decision_policy",
    "execution",
    "primary",
    "schema",
    "secondary",
    "selection_artifact",
}
P5_CONFIG_KEYS = {
    "cofactor_width",
    "construction",
    "coverage",
    "effort_on_solved_cells",
    "image_time_seconds",
    "label",
    "micro_par2_seconds",
    "roles",
    "search",
    "solved_planner_time_seconds",
}
P5_COMPARISON_KEYS = {
    "candidate",
    "coverage",
    "jointly_solved_runtime",
    "micro_par2_seconds",
    "name",
    "paired_complete_image_time_seconds",
    "paired_observed_cofactor_width",
    "paired_observed_construction_time_seconds",
    "paired_solved_effort",
    "reference",
    "roles",
}

TOP_KEYS = {
    "schema",
    "analysis_protocol",
    "selection_artifact",
    "execution",
    "decision_policy",
    "terminal_outcome_census",
    "primary",
    "sole_predeclared_sensitivity",
    "completion_and_recovery",
}
STRUCTURE_TOP_KEYS = {
    "schema",
    "analysis_protocol",
    "decision_label",
    "specification_boundary",
    "input_identity",
    "interpretation",
    "configs",
    "selector_candidate_pool",
}
STRUCTURE_INPUT_KEYS = {
    "selection_artifact_sha256",
    "full_protocol_revision",
    "properties_canonical_sha256",
    "task_count",
    "config_count",
    "cell_count",
    "config_order",
}
STRUCTURE_INTERPRETATION = {
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
}
STRUCTURE_DIRECT_SUMMARIES = (
    "W",
    "A",
    "V",
    "T",
    "U",
    "U_over_W",
    "A_over_W",
    "V_over_W",
    "T_over_W",
)
STRUCTURE_UNOBSERVED_REASONS = (
    "construction_fallback",
    "presearch_outcome",
    "resource_before_direct_tuple",
    "selector_width_only_resource_prefix",
)
STRUCTURE_CORRELATIONS = (
    ("W_vs_partition_ratio_max", "$W$ / maximum partition ratio"),
    ("U_vs_partition_ratio_max", "$U$ / maximum partition ratio"),
    ("W_vs_partition_ratio_geomean", "$W$ / geometric-mean partition ratio"),
    ("U_vs_partition_ratio_geomean", "$U$ / geometric-mean partition ratio"),
)
STRUCTURE_SOURCE_DISPLAY = (
    ("empty", "Empty"),
    ("bdd_prefix", "BDD prefix"),
    ("goal_prefix", "Goal prefix"),
    ("goal_fill", "Goal fill"),
    ("cegar", "CEGAR"),
)
STRUCTURE_SELECTOR_SOURCES = tuple(item[0] for item in STRUCTURE_SOURCE_DISPLAY)
STRUCTURE_OUTCOME_DISPLAY = {
    code: outcome for code, outcome, _presearch, _raw, _effective in TERMINAL_OUTCOME_SPECS
}
SUMMARY_KEYS = {"observed", "minimum", "median", "maximum", "mean", "total"}
CERTIFICATION_KEYS = {
    "certified_cells",
    "eligible_cells",
    "uncertified_or_unobserved_cells",
    "rate",
}
PAIR_KEYS = {
    "pairs",
    "candidate_total",
    "reference_total",
    "candidate_over_reference",
    "candidate_minus_reference",
}
SELECTOR_SOURCES = ("empty", "bdd_prefix", "goal_prefix", "goal_fill", "cegar")

LAUNCH_PIN_KEYS = {
    "protocol",
    "protocol_revision",
    "full_runner_source_sha256",
    "planner_revision",
    "planner_binary_sha256",
    "planner_preprocess_sha256",
    "prospective_start_job_sha256",
}

# This is synthetic test provenance, not an accepted launch.  It lets
# --self-test consume the current analyzer's v4 output contract while the
# ordinary v4 pin set remains completely unset.  Production validation never
# selects it, and it contains no identity from the canceled full run.
CURRENT_ANALYZER_FIXTURE_LAUNCH_PINS = {
    "protocol": "arrhenius-selector-full-population-v4",
    "protocol_revision": "0123456789abcdef0123456789abcdef01234567",
    "full_runner_source_sha256": (
        "f224545494a1ac488628e9932f82738134994e87ac04c4b9d9c18632de47a897"
    ),
    "planner_revision": "a3486a027a0f281e762cb6d66d72311455b66b33",
    "planner_binary_sha256": (
        "ae84f545aa76c7fab564f5cdcc96cd0fc48c46631cbc4ffc9193d94bac39832e"
    ),
    "planner_preprocess_sha256": (
        "eba6d4e9be4d88db82179a8415c306838f98e656bac1c448a9b2937430be6f3b"
    ),
    "prospective_start_job_sha256": (
        "2e3c9f1c4f65abc20346c18a29f4fe7763c666ac1c8d5f0782bf5b692e3e5d1b"
    ),
}


def canonical_json(value):
    """Return the analyzer's canonical finite-JSON encoding."""
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError) as err:
        raise RenderError("value is not canonical finite JSON: {}".format(err)) from err


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_json(value):
    return sha256_bytes(canonical_json(value).encode("ascii"))


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RenderError("duplicate JSON key {!r}".format(key))
        result[key] = value
    return result


def _reject_constant(value):
    raise RenderError("non-finite JSON constant {}".format(value))


def _read_regular(path, maximum):
    path = Path(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(str(path), flags)
    except OSError as err:
        raise RenderError("cannot open {}: {}".format(path, err)) from err
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise RenderError("{} is not a regular file".format(path))
        if info.st_size > maximum:
            raise RenderError("{} exceeds the size limit".format(path))
        chunks = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        final_info = os.fstat(descriptor)
        fingerprint = lambda item: (
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_nlink,
            item.st_size,
            item.st_mtime_ns,
            item.st_ctime_ns,
        )
        if fingerprint(final_info) != fingerprint(info):
            raise RenderError("{} changed while it was read".format(path))
        if len(data) > maximum:
            raise RenderError("{} exceeds the size limit".format(path))
        if len(data) != info.st_size:
            raise RenderError("{} changed while it was read".format(path))
        return data
    finally:
        os.close(descriptor)


def parse_canonical_analysis(raw, source="analysis artifact"):
    if not raw:
        raise RenderError("{} is empty".format(source))
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as err:
        raise RenderError("{} is not UTF-8: {}".format(source, err)) from err
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except RenderError:
        raise
    except (json.JSONDecodeError, RecursionError) as err:
        raise RenderError("cannot parse {}: {}".format(source, err)) from err
    if type(value) is not dict:
        raise RenderError("{} must contain one JSON object".format(source))
    expected = canonical_json(value).encode("ascii") + b"\n"
    if raw != expected:
        raise RenderError(
            "{} is not exact canonical ASCII JSON followed by one newline".format(
                source
            )
        )
    return value


def _is_sha256(value):
    return (
        type(value) is str
        and len(value) == 64
        and all(character in SHA256_HEX for character in value)
    )


def _require_sha256(value, label, expected=None):
    if not _is_sha256(value):
        raise RenderError("{} is not a lowercase SHA-256".format(label))
    if len(set(value)) == 1:
        raise RenderError("{} looks synthetic".format(label))
    if expected is not None and value != expected:
        raise RenderError("{} changed".format(label))
    return value


def _require_revision(value, label):
    if (
        type(value) is not str
        or len(value) != 40
        or any(character not in SHA256_HEX for character in value)
        or len(set(value)) == 1
    ):
        raise RenderError("{} is not a reviewed lowercase 40-hex revision".format(label))
    return value


def _validate_launch_pins(value, label="launch pins"):
    value = _mapping(value, label, LAUNCH_PIN_KEYS)
    if type(value["protocol"]) is not str or not value["protocol"]:
        raise RenderError("{}.protocol is invalid".format(label))
    if value["protocol"] != FULL_PROTOCOL:
        raise RenderError("{}.protocol is not corrected full protocol v4".format(label))
    _require_revision(value["protocol_revision"], label + ".protocol_revision")
    _require_revision(value["planner_revision"], label + ".planner_revision")
    if value["planner_revision"] != EXPECTED_PLANNER_REVISION:
        raise RenderError("{}.planner_revision is not the P6 source revision".format(label))
    for key in (
        "full_runner_source_sha256",
        "planner_binary_sha256",
        "planner_preprocess_sha256",
        "prospective_start_job_sha256",
    ):
        _require_sha256(value[key], label + "." + key)
    return value


def _production_pin_values():
    return {
        "analysis_sha256": EXPECTED_FULL_ANALYSIS_SHA256,
        "structure_sha256": EXPECTED_FULL_STRUCTURE_SHA256,
        "protocol": FULL_PROTOCOL,
        "protocol_revision": EXPECTED_PROTOCOL_REVISION,
        "full_runner_source_sha256": EXPECTED_FULL_RUNNER_SHA256,
        "planner_revision": EXPECTED_PLANNER_REVISION,
        "planner_binary_sha256": EXPECTED_PLANNER_BINARY_SHA256,
        "planner_preprocess_sha256": EXPECTED_PLANNER_PREPROCESS_SHA256,
        "prospective_start_job_sha256": EXPECTED_PROSPECTIVE_JOB_SHA256,
    }


def _reviewed_production_pins_from(pins):
    """Enforce one all-unset or all-reviewed production pin state."""
    expected_keys = {"analysis_sha256", "structure_sha256"} | LAUNCH_PIN_KEYS
    pins = _mapping(pins, "production pins", expected_keys)
    mutable_keys = expected_keys - {"protocol", "planner_revision"}
    present = sorted(key for key in mutable_keys if pins[key] is not None)
    missing = sorted(key for key in mutable_keys if pins[key] is None)
    if present and missing:
        raise RenderError(
            "production pins are partially set; review analysis, structure, and launch "
            "identities together (present={}, missing={})".format(present, missing)
        )
    if not present:
        raise RenderError(
            "full analysis/structure SHA-256 and corrected v4 launch pins are all unset"
        )
    if pins["protocol"] != FULL_PROTOCOL:
        raise RenderError("reviewed production protocol is not corrected v4")
    if pins["planner_revision"] != EXPECTED_PLANNER_REVISION:
        raise RenderError("reviewed P6 planner revision changed")
    analysis_sha256 = _require_sha256(
        pins["analysis_sha256"], "reviewed full analysis SHA-256"
    )
    structure_sha256 = _require_sha256(
        pins["structure_sha256"], "reviewed full structure SHA-256"
    )
    launch = {key: pins[key] for key in LAUNCH_PIN_KEYS}
    launch = _validate_launch_pins(launch, "reviewed v4 launch pins")
    return {
        "analysis_sha256": analysis_sha256,
        "structure_sha256": structure_sha256,
        "launch": launch,
    }


def reviewed_production_pins():
    return _reviewed_production_pins_from(_production_pin_values())


def _load_frozen_analysis_with_test_pins(
    analysis_path,
    sidecar_path=None,
    *,
    expected_analysis_sha256,
    launch_pins,
):
    """Load an exact canonical artifact and exact sha256sum-style sidecar."""
    _require_sha256(
        expected_analysis_sha256, "EXPECTED_FULL_ANALYSIS_SHA256"
    )
    effective_launch_pins = _validate_launch_pins(
        launch_pins, "private synthetic-test launch pins"
    )
    analysis_path = Path(analysis_path)
    sidecar_path = (
        Path(sidecar_path)
        if sidecar_path is not None
        else Path(str(analysis_path) + ".sha256")
    )
    raw = _read_regular(analysis_path, MAX_ARTIFACT_BYTES)
    actual = sha256_bytes(raw)
    if actual != expected_analysis_sha256:
        raise RenderError("analysis artifact does not match its reviewed digest")
    sidecar = _read_regular(sidecar_path, 256)
    expected_sidecar = "{}  {}\n".format(actual, analysis_path.name).encode("ascii")
    if sidecar != expected_sidecar:
        raise RenderError(
            "analysis sidecar is not the exact sha256sum record for {}".format(
                analysis_path.name
            )
        )
    value = parse_canonical_analysis(raw, str(analysis_path))
    _validate_analysis_with_test_pins(
        value, actual, launch_pins=effective_launch_pins
    )
    return value, actual


def load_frozen_analysis(analysis_path, sidecar_path=None):
    """Public production loader; no caller-supplied identity overrides."""
    pins = reviewed_production_pins()
    return _load_frozen_analysis_with_test_pins(
        analysis_path,
        sidecar_path,
        expected_analysis_sha256=pins["analysis_sha256"],
        launch_pins=pins["launch"],
    )


def _validate_structure_input_path(
    path,
    *,
    expected=DEFAULT_STRUCTURE,
    root=REPOSITORY_ROOT,
):
    """Confine the secondary diagnostic to its reviewed repository path."""
    path = Path(os.path.abspath(str(path)))
    expected = Path(os.path.abspath(str(expected)))
    root = Path(os.path.abspath(str(root)))
    if path != expected:
        raise RenderError("structure input is restricted to {}".format(expected))
    try:
        relative = path.relative_to(root)
    except ValueError as err:
        raise RenderError("structure input is outside the repository") from err
    components = (root,) + tuple(
        root.joinpath(*relative.parts[: index + 1])
        for index in range(len(relative.parts))
    )
    for index, current in enumerate(components):
        try:
            info = current.lstat()
        except OSError as err:
            raise RenderError(
                "cannot inspect structure input {}: {}".format(current, err)
            ) from err
        if stat.S_ISLNK(info.st_mode):
            raise RenderError(
                "structure input contains symlink component {}".format(current)
            )
        if index < len(components) - 1 and not stat.S_ISDIR(info.st_mode):
            raise RenderError(
                "structure input parent is not a directory: {}".format(current)
            )
        if index == len(components) - 1 and not stat.S_ISREG(info.st_mode):
            raise RenderError("structure input is not a regular file: {}".format(current))
    return path


def _load_frozen_structure_with_test_pin(
    structure_path,
    sidecar_path=None,
    *,
    expected_structure_sha256,
    analysis,
    analysis_sha256,
    launch_pins,
):
    """Load and cross-validate a canonical structural diagnostic fixture."""
    _require_sha256(expected_structure_sha256, "expected structure SHA-256")
    structure_path = Path(structure_path)
    sidecar_path = (
        Path(sidecar_path)
        if sidecar_path is not None
        else Path(str(structure_path) + ".sha256")
    )
    raw = _read_regular(structure_path, MAX_ARTIFACT_BYTES)
    actual = sha256_bytes(raw)
    if actual != expected_structure_sha256:
        raise RenderError("structure artifact does not match its reviewed digest")
    sidecar = _read_regular(sidecar_path, 256)
    expected_sidecar = "{}  {}\n".format(actual, structure_path.name).encode("ascii")
    if sidecar != expected_sidecar:
        raise RenderError(
            "structure sidecar is not the exact sha256sum record for {}".format(
                structure_path.name
            )
        )
    value = parse_canonical_analysis(raw, str(structure_path))
    _validate_structure_with_test_pins(
        value,
        actual,
        analysis=analysis,
        analysis_sha256=analysis_sha256,
        launch_pins=launch_pins,
    )
    return value, actual


def load_frozen_structure(
    structure_path=DEFAULT_STRUCTURE,
    sidecar_path=DEFAULT_STRUCTURE_SIDECAR,
    *,
    analysis,
    analysis_sha256,
):
    """Load only the confined, atomically reviewed P6 structural artifact."""
    pins = reviewed_production_pins()
    if analysis_sha256 != pins["analysis_sha256"]:
        raise RenderError("analysis artifact does not match its reviewed digest")
    structure_path = _validate_structure_input_path(structure_path)
    sidecar_path = _validate_structure_input_path(
        sidecar_path, expected=DEFAULT_STRUCTURE_SIDECAR
    )
    return _load_frozen_structure_with_test_pin(
        structure_path,
        sidecar_path,
        expected_structure_sha256=pins["structure_sha256"],
        analysis=analysis,
        analysis_sha256=analysis_sha256,
        launch_pins=pins["launch"],
    )


def _validate_p5_input_path(
    path,
    *,
    expected=DEFAULT_P5_ANALYSIS,
    root=REPOSITORY_ROOT,
):
    """Require the fixed tracked P5 path with no symlinked component."""
    path = Path(os.path.abspath(str(path)))
    expected = Path(os.path.abspath(str(expected)))
    root = Path(os.path.abspath(str(root)))
    if path != expected:
        raise RenderError("P5 input is restricted to {}".format(expected))
    try:
        relative = path.relative_to(root)
    except ValueError as err:
        raise RenderError("P5 input is outside the repository") from err
    current = root
    components = (current,) + tuple(
        root.joinpath(*relative.parts[: index + 1])
        for index in range(len(relative.parts))
    )
    for index, current in enumerate(components):
        try:
            info = current.lstat()
        except OSError as err:
            raise RenderError("cannot inspect P5 input {}: {}".format(current, err)) from err
        if stat.S_ISLNK(info.st_mode):
            raise RenderError("P5 input contains symlink component {}".format(current))
        if index < len(components) - 1 and not stat.S_ISDIR(info.st_mode):
            raise RenderError("P5 input parent is not a directory: {}".format(current))
        if index == len(components) - 1 and not stat.S_ISREG(info.st_mode):
            raise RenderError("P5 input is not a regular file: {}".format(current))
    return path


def _load_p5_analysis_with_expected_sha(
    analysis_path,
    *,
    expected_analysis_sha256,
):
    """Strict stable loader used by the pinned public path and unit fixtures."""
    _require_sha256(expected_analysis_sha256, "expected P5 analysis SHA-256")
    analysis_path = Path(analysis_path)
    sidecar_path = Path(str(analysis_path) + ".sha256")
    raw = _read_regular(analysis_path, MAX_ARTIFACT_BYTES)
    actual = sha256_bytes(raw)
    if actual != expected_analysis_sha256:
        raise RenderError("P5 analysis artifact does not match its pinned digest")
    sidecar = _read_regular(sidecar_path, 256)
    expected_sidecar = "{}  {}\n".format(actual, analysis_path.name).encode(
        "ascii"
    )
    if sidecar != expected_sidecar:
        raise RenderError(
            "P5 analysis sidecar is not the exact sha256sum record for {}".format(
                analysis_path.name
            )
        )
    value = parse_canonical_analysis(raw, str(analysis_path))
    _validate_p5_analysis(value, actual)
    return value, actual


def load_p5_analysis(analysis_path=DEFAULT_P5_ANALYSIS):
    """Load only the tracked, immutable P5 held-out analysis and sidecar."""
    analysis_path = _validate_p5_input_path(analysis_path)
    _validate_p5_input_path(
        Path(str(analysis_path) + ".sha256"),
        expected=DEFAULT_P5_SIDECAR,
    )
    return _load_p5_analysis_with_expected_sha(
        analysis_path,
        expected_analysis_sha256=EXPECTED_P5_ANALYSIS_SHA256,
    )


def _mapping(value, label, keys=None):
    if type(value) is not dict:
        raise RenderError("{} must be an object".format(label))
    if keys is not None and set(value) != set(keys):
        missing = sorted(set(keys) - set(value))
        extra = sorted(set(value) - set(keys))
        raise RenderError(
            "{} keys changed (missing={}, extra={})".format(label, missing, extra)
        )
    return value


def _sequence(value, label, length=None):
    if type(value) is not list:
        raise RenderError("{} must be an array".format(label))
    if length is not None and len(value) != length:
        raise RenderError("{} must contain {} entries".format(label, length))
    return value


def _integer(value, label, minimum=None, maximum=None):
    if type(value) is not int:
        raise RenderError("{} must be an exact integer".format(label))
    if minimum is not None and value < minimum:
        raise RenderError("{} is below {}".format(label, minimum))
    if maximum is not None and value > maximum:
        raise RenderError("{} exceeds {}".format(label, maximum))
    return value


def _number(value, label, minimum=None, maximum=None):
    if type(value) not in (int, float):
        raise RenderError("{} must be a number".format(label))
    result = float(value)
    if not math.isfinite(result):
        raise RenderError("{} must be finite".format(label))
    if minimum is not None and result < minimum:
        raise RenderError("{} is below {}".format(label, minimum))
    if maximum is not None and result > maximum:
        raise RenderError("{} exceeds {}".format(label, maximum))
    return result


def _close(actual, expected, label, *, absolute=1e-12):
    actual = _number(actual, label)
    expected = float(expected)
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=absolute):
        raise RenderError(
            "{} arithmetic changed: {} != {}".format(label, actual, expected)
        )


def _exact(actual, expected, label):
    if type(actual) is not type(expected) or actual != expected:
        raise RenderError("{} changed".format(label))


def _validate_summary(value, label, expected_observed=None, nonnegative=False):
    value = _mapping(value, label, SUMMARY_KEYS)
    observed = _integer(value["observed"], label + ".observed", 0)
    if expected_observed is not None and observed != expected_observed:
        raise RenderError("{}.observed changed".format(label))
    names = ("minimum", "median", "maximum", "mean", "total")
    if observed == 0:
        if any(value[name] is not None for name in names):
            raise RenderError("{} empty summary must contain only null statistics".format(label))
        return value
    numbers = {
        name: _number(
            value[name],
            "{}.{}".format(label, name),
            minimum=0 if nonnegative else None,
        )
        for name in names
    }
    if not numbers["minimum"] <= numbers["median"] <= numbers["maximum"]:
        raise RenderError("{} order statistics are inconsistent".format(label))
    if not numbers["minimum"] <= numbers["mean"] <= numbers["maximum"]:
        raise RenderError("{} mean lies outside the observed range".format(label))
    _close(
        numbers["mean"],
        numbers["total"] / observed,
        label + ".mean",
    )
    return value


def _validate_count_summary(value, label, expected_observed=None):
    """Validate a summary whose underlying observations are exact integers."""
    value = _validate_summary(
        value, label, expected_observed=expected_observed, nonnegative=True
    )
    if value["observed"] == 0:
        return value
    for name in ("minimum", "maximum", "total"):
        item = value[name]
        if type(item) is int:
            continue
        if type(item) is not float or not item.is_integer():
            raise RenderError("{}.{} must be integral".format(label, name))
    median = value["median"]
    if type(median) is int:
        return value
    if type(median) is not float or not (median * 2).is_integer():
        raise RenderError("{}.median must be integral or half-integral".format(label))
    return value


def _expected_structure_summary(values):
    """Recompute the structural analyzer's exact summary convention."""
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
    numeric = sorted(float(item) for item in values)
    if any(not math.isfinite(item) for item in numeric):
        raise RenderError("structural summary inputs must be finite")
    middle = len(numeric) // 2
    median = (
        numeric[middle]
        if len(numeric) % 2
        else (numeric[middle - 1] + numeric[middle]) / 2.0
    )
    total = math.fsum(numeric)
    return {
        "observed": len(values),
        "minimum": min(values),
        "median": median,
        "maximum": max(values),
        "mean": total / len(values),
        "total": total,
    }


def _average_ranks(values):
    numeric = [float(item) for item in values]
    order = sorted(range(len(numeric)), key=lambda index: (numeric[index], index))
    ranks = [0.0] * len(numeric)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and numeric[order[end]] == numeric[order[start]]:
            end += 1
        rank = ((start + 1) + end) / 2.0
        for position in range(start, end):
            ranks[order[position]] = rank
        start = end
    return ranks


def _spearman_average_ties(xs, ys):
    if len(xs) != len(ys):
        raise RenderError("structural Spearman inputs have different lengths")
    n = len(xs)
    if n < 2:
        return {"n": n, "coefficient": None, "null_reason": "fewer-than-two-pairs"}
    rank_x = _average_ranks(xs)
    rank_y = _average_ranks(ys)
    mean = (n + 1) / 2.0
    centered_x = [item - mean for item in rank_x]
    centered_y = [item - mean for item in rank_y]
    variance_x = math.fsum(item * item for item in centered_x)
    variance_y = math.fsum(item * item for item in centered_y)
    if variance_x == 0 or variance_y == 0:
        return {"n": n, "coefficient": None, "null_reason": "zero-rank-variance"}
    covariance = math.fsum(
        left * right for left, right in zip(centered_x, centered_y)
    )
    coefficient = covariance / math.sqrt(variance_x * variance_y)
    return {
        "n": n,
        "coefficient": max(-1.0, min(1.0, coefficient)),
        "null_reason": None,
    }


def _validate_structure_summary(value, label, values=None, expected_observed=None):
    if values is not None:
        values = list(values)
        expected_observed = len(values)
    value = _validate_summary(
        value,
        label,
        expected_observed=expected_observed,
        nonnegative=True,
    )
    if values is None:
        return copy.deepcopy(value)
    expected = _expected_structure_summary(values)
    for key in SUMMARY_KEYS:
        if expected[key] is None:
            _exact(value[key], None, "{}.{}".format(label, key))
        elif key == "observed":
            _exact(value[key], expected[key], "{}.{}".format(label, key))
        else:
            _close(value[key], expected[key], "{}.{}".format(label, key))
    return copy.deepcopy(value)


def _require_analyzer_integer_summary_types(value, label):
    """Require the precise `_summary` types for integer observations."""
    if value["observed"] == 0:
        return
    for key in ("minimum", "maximum"):
        if type(value[key]) is not int:
            raise RenderError("{}.{} must be an exact integer".format(label, key))
    for key in ("median", "mean", "total"):
        if type(value[key]) is not float:
            raise RenderError("{}.{} must use analyzer float arithmetic".format(label, key))


def _require_analyzer_float_summary_types(value, label):
    if value["observed"] == 0:
        return
    for key in ("minimum", "median", "maximum", "mean", "total"):
        if type(value[key]) is not float:
            raise RenderError("{}.{} must be an analyzer float".format(label, key))


def _validate_structure_outcome_histogram(value, label, expected_total):
    entries = _sequence(value, label, len(TERMINAL_OUTCOME_SPECS))
    counts = {}
    for index, entry in enumerate(entries):
        prefix = "{}[{}]".format(label, index)
        entry = _mapping(entry, prefix, {"code", "outcome", "count"})
        code = _integer(entry["code"], prefix + ".code")
        if code not in STRUCTURE_OUTCOME_DISPLAY or code in counts:
            raise RenderError("{} has an unexpected or duplicate outcome code".format(label))
        _exact(
            entry["outcome"],
            STRUCTURE_OUTCOME_DISPLAY[code],
            prefix + ".outcome",
        )
        counts[code] = _integer(
            entry["count"], prefix + ".count", 0, expected_total
        )
    if set(counts) != set(TERMINAL_OUTCOME_CODES):
        raise RenderError("{} outcome identities changed".format(label))
    if sum(counts.values()) != expected_total:
        raise RenderError("{} outcome counts do not conserve the stratum".format(label))
    return counts


def _validate_structure_stratum(value, label, *, resource_prefix):
    common_keys = {
        "eligible_logs",
        "logs_with_partition_ratios",
        "logs_without_partition_ratios",
        "terminal_outcome_counts",
        "ratio_observation_terminal_outcome_counts",
        "partition_ratio_census_unit",
        "partition_ratio_census",
        "summaries",
    }
    keys = common_keys | (
        {"interpretation"}
        if resource_prefix
        else {
            "paired_direct_tuple_and_ratio_cells",
            "paired_census_unit",
            "paired_W_U_partition_ratio_census",
            "cross_task_descriptive_confounded_correlations",
        }
    )
    value = _mapping(value, label, keys)
    eligible = _integer(value["eligible_logs"], label + ".eligible_logs", 0, TASKS)
    observed = _integer(
        value["logs_with_partition_ratios"],
        label + ".logs_with_partition_ratios",
        0,
        eligible,
    )
    missing = _integer(
        value["logs_without_partition_ratios"],
        label + ".logs_without_partition_ratios",
        0,
        eligible,
    )
    if observed + missing != eligible:
        raise RenderError("{} partition denominator arithmetic changed".format(label))
    outcome_counts = _validate_structure_outcome_histogram(
        value["terminal_outcome_counts"], label + ".terminal_outcome_counts", eligible
    )
    observed_outcomes = _validate_structure_outcome_histogram(
        value["ratio_observation_terminal_outcome_counts"],
        label + ".ratio_observation_terminal_outcome_counts",
        observed,
    )
    if any(observed_outcomes[code] > outcome_counts[code] for code in TERMINAL_OUTCOME_CODES):
        raise RenderError("{} ratio-outcome histogram exceeds its eligible histogram".format(label))
    if resource_prefix and any(
        outcome_counts[code]
        for code in TERMINAL_OUTCOME_CODES
        if code not in (22, 23, 24)
    ):
        raise RenderError("{} contains a non-resource terminal outcome".format(label))
    if not resource_prefix and any(
        outcome_counts[code] for code in (10, 20, 21)
    ):
        raise RenderError("{} contains a pre-search terminal outcome".format(label))

    _exact(
        value["partition_ratio_census_unit"],
        "one-certified-log-with-partition-ratios",
        label + ".partition_ratio_census_unit",
    )
    ratio_rows = _sequence(
        value["partition_ratio_census"], label + ".partition_ratio_census"
    )
    ratio_identities = set()
    ratio_max_values = []
    ratio_geomean_values = []
    normalized_ratio_rows = []
    for index, row in enumerate(ratio_rows):
        prefix = "{}.partition_ratio_census[{}]".format(label, index)
        row = _mapping(
            row,
            prefix,
            {"partition_ratio_max", "partition_ratio_geomean", "count"},
        )
        if type(row["partition_ratio_max"]) is not float or type(row["partition_ratio_geomean"]) is not float:
            raise RenderError("{} partition ratios must be analyzer floats".format(prefix))
        ratio_max = _number(row["partition_ratio_max"], prefix + ".partition_ratio_max", 0)
        ratio_geomean = _number(row["partition_ratio_geomean"], prefix + ".partition_ratio_geomean", 0)
        if ratio_max < ratio_geomean and not math.isclose(
            ratio_max, ratio_geomean, rel_tol=1e-12, abs_tol=1e-15
        ):
            raise RenderError("{} has max below geomean".format(prefix))
        identity = (ratio_max, ratio_geomean)
        if identity in ratio_identities:
            raise RenderError("{} contains a duplicate partition-ratio bin".format(label))
        ratio_identities.add(identity)
        count = _integer(row["count"], prefix + ".count", 1, observed)
        ratio_max_values.extend([ratio_max] * count)
        ratio_geomean_values.extend([ratio_geomean] * count)
        normalized_ratio_rows.append(
            {
                "partition_ratio_max": row["partition_ratio_max"],
                "partition_ratio_geomean": row["partition_ratio_geomean"],
                "count": count,
            }
        )
    if len(ratio_max_values) != observed:
        raise RenderError("{} partition-ratio census does not conserve logs".format(label))
    normalized_ratio_rows.sort(
        key=lambda row: (row["partition_ratio_max"], row["partition_ratio_geomean"])
    )
    summaries = _mapping(
        value["summaries"],
        label + ".summaries",
        {"partition_ratio_max", "partition_ratio_geomean"},
    )
    maximum = _validate_structure_summary(
        summaries["partition_ratio_max"],
        label + ".summaries.partition_ratio_max",
        values=ratio_max_values,
    )
    geomean = _validate_structure_summary(
        summaries["partition_ratio_geomean"],
        label + ".summaries.partition_ratio_geomean",
        values=ratio_geomean_values,
    )
    _require_analyzer_float_summary_types(maximum, label + ".summaries.partition_ratio_max")
    _require_analyzer_float_summary_types(geomean, label + ".summaries.partition_ratio_geomean")
    if observed:
        for statistic in ("minimum", "median", "maximum", "mean", "total"):
            if float(maximum[statistic]) < float(geomean[statistic]) and not math.isclose(
                float(maximum[statistic]), float(geomean[statistic]),
                rel_tol=1e-12, abs_tol=1e-15,
            ):
                raise RenderError(
                    "{} maximum/geomean partition summary arithmetic changed".format(label)
                )

    normalized = {
        "eligible_logs": eligible,
        "logs_with_partition_ratios": observed,
        "logs_without_partition_ratios": missing,
        "terminal_outcome_counts": [
            {
                "code": code,
                "outcome": STRUCTURE_OUTCOME_DISPLAY[code],
                "count": outcome_counts[code],
            }
            for code in TERMINAL_OUTCOME_CODES
        ],
        "ratio_observation_terminal_outcome_counts": [
            {
                "code": code,
                "outcome": STRUCTURE_OUTCOME_DISPLAY[code],
                "count": observed_outcomes[code],
            }
            for code in TERMINAL_OUTCOME_CODES
        ],
        "partition_ratio_census_unit": value["partition_ratio_census_unit"],
        "partition_ratio_census": normalized_ratio_rows,
        "summaries": {
            "partition_ratio_max": maximum,
            "partition_ratio_geomean": geomean,
        },
    }
    if resource_prefix:
        _exact(
            value["interpretation"],
            "censored-observed-prefix-ratios-only; no rank correlations",
            label + ".interpretation",
        )
        normalized["interpretation"] = value["interpretation"]
        return normalized

    paired = _integer(
        value["paired_direct_tuple_and_ratio_cells"],
        label + ".paired_direct_tuple_and_ratio_cells",
        0,
        observed,
    )
    if paired != observed:
        raise RenderError("{} paired partition census must equal observed-ratio logs".format(label))
    _exact(
        value["paired_census_unit"],
        "one-raw-complete-cell-with-direct-tuple-and-partition-ratios",
        label + ".paired_census_unit",
    )
    paired_rows = _sequence(
        value["paired_W_U_partition_ratio_census"],
        label + ".paired_W_U_partition_ratio_census",
    )
    paired_identities = set()
    expanded_W = []
    expanded_U = []
    expanded_max = []
    expanded_geomean = []
    normalized_paired_rows = []
    for index, row in enumerate(paired_rows):
        prefix = "{}.paired_census[{}]".format(label, index)
        row = _mapping(
            row,
            prefix,
            {"W", "U", "partition_ratio_max", "partition_ratio_geomean", "count"},
        )
        W = _integer(row["W"], prefix + ".W", 1)
        U = _integer(row["U"], prefix + ".U", W)
        if type(row["partition_ratio_max"]) is not float or type(row["partition_ratio_geomean"]) is not float:
            raise RenderError("{} paired ratios must be analyzer floats".format(prefix))
        ratio_max = _number(row["partition_ratio_max"], prefix + ".partition_ratio_max", 0)
        ratio_geomean = _number(row["partition_ratio_geomean"], prefix + ".partition_ratio_geomean", 0)
        if ratio_max < ratio_geomean and not math.isclose(
            ratio_max, ratio_geomean, rel_tol=1e-12, abs_tol=1e-15
        ):
            raise RenderError("{} has max below geomean".format(prefix))
        identity = (W, U, ratio_max, ratio_geomean)
        if identity in paired_identities:
            raise RenderError("{} contains a duplicate paired structural bin".format(label))
        paired_identities.add(identity)
        count = _integer(row["count"], prefix + ".count", 1, paired)
        expanded_W.extend([W] * count)
        expanded_U.extend([U] * count)
        expanded_max.extend([ratio_max] * count)
        expanded_geomean.extend([ratio_geomean] * count)
        normalized_paired_rows.append(
            {
                "W": W,
                "U": U,
                "partition_ratio_max": row["partition_ratio_max"],
                "partition_ratio_geomean": row["partition_ratio_geomean"],
                "count": count,
            }
        )
    if len(expanded_W) != paired:
        raise RenderError("{} paired structural census does not conserve cells".format(label))
    paired_projection_counts = {}
    for row in normalized_paired_rows:
        key = (row["partition_ratio_max"], row["partition_ratio_geomean"])
        paired_projection_counts[key] = paired_projection_counts.get(key, 0) + row["count"]
    paired_projection = sorted(
        (key[0], key[1], count)
        for key, count in paired_projection_counts.items()
    )
    common_projection = sorted(
        (row["partition_ratio_max"], row["partition_ratio_geomean"], row["count"])
        for row in normalized_ratio_rows
    )
    if paired_projection != common_projection:
        raise RenderError("{} paired W/U census does not project to the partition-ratio census".format(label))
    normalized_paired_rows.sort(
        key=lambda row: (
            row["W"], row["U"], row["partition_ratio_max"],
            row["partition_ratio_geomean"],
        )
    )
    _validate_structure_summary(
        summaries["partition_ratio_max"],
        label + ".summaries.partition_ratio_max",
        expanded_max,
    )
    _validate_structure_summary(
        summaries["partition_ratio_geomean"],
        label + ".summaries.partition_ratio_geomean",
        expanded_geomean,
    )
    correlations = _mapping(
        value["cross_task_descriptive_confounded_correlations"],
        label + ".cross_task_descriptive_confounded_correlations",
        {"method", "interpretation"} | {item[0] for item in STRUCTURE_CORRELATIONS},
    )
    _exact(
        correlations["method"],
        "Spearman-average-ranks-for-ties",
        label + ".correlations.method",
    )
    _exact(
        correlations["interpretation"],
        "descriptive-cross-task-confounded-no-inference",
        label + ".correlations.interpretation",
    )
    normalized_correlations = {
        "method": correlations["method"],
        "interpretation": correlations["interpretation"],
    }
    correlation_inputs = {
        "W_vs_partition_ratio_max": (expanded_W, expanded_max),
        "U_vs_partition_ratio_max": (expanded_U, expanded_max),
        "W_vs_partition_ratio_geomean": (expanded_W, expanded_geomean),
        "U_vs_partition_ratio_geomean": (expanded_U, expanded_geomean),
    }
    for key, _display in STRUCTURE_CORRELATIONS:
        prefix = "{}.correlations.{}".format(label, key)
        item = _mapping(
            correlations[key], prefix, {"n", "coefficient", "null_reason"}
        )
        n = _integer(item["n"], prefix + ".n", 0, paired)
        if n != paired:
            raise RenderError("{}.n disagrees with the paired-cell denominator".format(prefix))
        expected_correlation = _spearman_average_ties(*correlation_inputs[key])
        _exact(item["null_reason"], expected_correlation["null_reason"], prefix + ".null_reason")
        coefficient = item["coefficient"]
        reason = item["null_reason"]
        if n < 2:
            _exact(coefficient, None, prefix + ".coefficient")
            _exact(reason, "fewer-than-two-pairs", prefix + ".null_reason")
        elif coefficient is None:
            _exact(reason, "zero-rank-variance", prefix + ".null_reason")
        else:
            if type(coefficient) is not float:
                raise RenderError("{}.coefficient must be an analyzer float".format(prefix))
            coefficient = _number(coefficient, prefix + ".coefficient", -1, 1)
            _exact(reason, None, prefix + ".null_reason")
            _close(coefficient, expected_correlation["coefficient"], prefix + ".coefficient")
        normalized_correlations[key] = {
            "n": n,
            "coefficient": coefficient,
            "null_reason": reason,
        }
    normalized["paired_direct_tuple_and_ratio_cells"] = paired
    normalized["paired_census_unit"] = value["paired_census_unit"]
    normalized["paired_W_U_partition_ratio_census"] = normalized_paired_rows
    normalized["cross_task_descriptive_confounded_correlations"] = normalized_correlations
    return normalized


def _validate_structure_direct(value, label, expected_label):
    value = _mapping(
        value,
        label,
        {
            "eligible_cells",
            "observed_cells",
            "unobserved_cells",
            "observation_source_counts",
            "unobserved_reason_counts",
            "tuple_census",
            "summaries",
        },
    )
    expected_eligible = 0 if expected_label == "blind_fw" else TASKS
    eligible = _integer(value["eligible_cells"], label + ".eligible_cells", 0, TASKS)
    if eligible != expected_eligible:
        raise RenderError("{}.eligible_cells changed".format(label))
    observed = _integer(value["observed_cells"], label + ".observed_cells", 0, eligible)
    unobserved = _integer(
        value["unobserved_cells"], label + ".unobserved_cells", 0, eligible
    )
    if observed + unobserved != eligible:
        raise RenderError("{} direct-tuple denominator arithmetic changed".format(label))
    sources = _mapping(
        value["observation_source_counts"],
        label + ".observation_source_counts",
        {"completed_construction", "heuristic_event_only_resource_prefix"},
    )
    source_counts = {
        key: _integer(sources[key], "{}.sources.{}".format(label, key), 0, observed)
        for key in sources
    }
    if sum(source_counts.values()) != observed:
        raise RenderError("{} direct observation sources do not conserve cells".format(label))
    reasons = _mapping(
        value["unobserved_reason_counts"],
        label + ".unobserved_reason_counts",
        set(STRUCTURE_UNOBSERVED_REASONS),
    )
    reason_counts = {
        key: _integer(reasons[key], "{}.reasons.{}".format(label, key), 0, unobserved)
        for key in STRUCTURE_UNOBSERVED_REASONS
    }
    if sum(reason_counts.values()) != unobserved:
        raise RenderError("{} direct unobserved reasons do not conserve cells".format(label))

    rows = _sequence(value["tuple_census"], label + ".tuple_census")
    normalized_rows = []
    identities = set()
    expanded = {key: [] for key in ("W", "A", "V", "T", "U")}
    expanded.update({key: [] for key in STRUCTURE_DIRECT_SUMMARIES[5:]})
    row_sources = {"completed_construction": 0, "heuristic_event_only_resource_prefix": 0}
    for index, row in enumerate(rows):
        prefix = "{}.tuple_census[{}]".format(label, index)
        row = _mapping(
            row,
            prefix,
            {
                "W", "A", "V", "T", "U", "count",
                "completed_construction_cells",
                "heuristic_event_only_resource_prefix_cells",
            },
        )
        W = _integer(row["W"], prefix + ".W", 1)
        A = _integer(row["A"], prefix + ".A", 0)
        V = _integer(row["V"], prefix + ".V", 1)
        T = _integer(row["T"], prefix + ".T", 1)
        U = _integer(row["U"], prefix + ".U", 1)
        if not W >= T >= V or U != A + T or W > U:
            raise RenderError("{} violates W >= T >= V >= 1, A >= 0, U=A+T, or W<=U".format(prefix))
        identity = (W, A, V, T, U)
        if identity in identities:
            raise RenderError("{} contains a duplicate direct tuple".format(label))
        identities.add(identity)
        count = _integer(row["count"], prefix + ".count", 1, observed)
        completed = _integer(
            row["completed_construction_cells"], prefix + ".completed", 0, count
        )
        event_only = _integer(
            row["heuristic_event_only_resource_prefix_cells"],
            prefix + ".heuristic_event_only",
            0,
            count,
        )
        if completed + event_only != count:
            raise RenderError("{} tuple source arithmetic changed".format(prefix))
        row_sources["completed_construction"] += completed
        row_sources["heuristic_event_only_resource_prefix"] += event_only
        for key, item in (("W", W), ("A", A), ("V", V), ("T", T), ("U", U)):
            expanded[key].extend([item] * count)
        expanded["U_over_W"].extend([U / W] * count)
        expanded["A_over_W"].extend([A / W] * count)
        expanded["V_over_W"].extend([V / W] * count)
        expanded["T_over_W"].extend([T / W] * count)
        normalized_rows.append(
            {
                "W": W, "A": A, "V": V, "T": T, "U": U, "count": count,
                "completed_construction_cells": completed,
                "heuristic_event_only_resource_prefix_cells": event_only,
            }
        )
    if len(expanded["W"]) != observed or row_sources != source_counts:
        raise RenderError("{} tuple census does not conserve observations or sources".format(label))
    summaries = _mapping(
        value["summaries"], label + ".summaries", set(STRUCTURE_DIRECT_SUMMARIES)
    )
    normalized_summaries = {
        key: _validate_structure_summary(
            summaries[key], "{}.summaries.{}".format(label, key), expanded[key]
        )
        for key in STRUCTURE_DIRECT_SUMMARIES
    }
    for key in ("W", "A", "V", "T", "U"):
        _require_analyzer_integer_summary_types(
            normalized_summaries[key], "{}.summaries.{}".format(label, key)
        )
    for key in ("U_over_W", "A_over_W", "V_over_W", "T_over_W"):
        _require_analyzer_float_summary_types(
            normalized_summaries[key], "{}.summaries.{}".format(label, key)
        )
    normalized_rows.sort(key=lambda row: (row["W"], row["A"], row["V"], row["T"], row["U"]))
    return {
        "eligible_cells": eligible,
        "observed_cells": observed,
        "unobserved_cells": unobserved,
        "observation_source_counts": source_counts,
        "unobserved_reason_counts": reason_counts,
        "tuple_census": normalized_rows,
        "summaries": normalized_summaries,
    }


def _validate_structure_config(value, expected, analysis_config, analysis_outcomes):
    label = expected["label"]
    prefix = "structure.config[{}]".format(label)
    value = _mapping(
        value,
        prefix,
        {"label", "search", "cell_count", "direct_W_A_V_T_U", "partition_ratios"},
    )
    _exact(value["label"], label, prefix + ".label")
    _exact(value["search"], expected["search"], prefix + ".search")
    _exact(value["cell_count"], TASKS, prefix + ".cell_count")
    direct = _validate_structure_direct(
        value["direct_W_A_V_T_U"], prefix + ".direct_W_A_V_T_U", label
    )

    presearch = sum(analysis_outcomes[code] for code in (10, 20, 21))
    if label != "blind_fw" and direct["unobserved_reason_counts"]["presearch_outcome"] != presearch:
        raise RenderError("{} pre-search direct-tuple census disagrees with canonical analysis".format(prefix))
    canonical_width = analysis_config["exact_cofactor_width"]["certification"]["certified_cells"]
    width_only = direct["unobserved_reason_counts"]["selector_width_only_resource_prefix"]
    if label != "pdb_selector_k1" and width_only:
        raise RenderError(
            "{} has a selector-width-only prefix outside the selector".format(
                prefix
            )
        )
    if direct["observed_cells"] + width_only != canonical_width:
        raise RenderError("{} direct W/A/V/T/U census disagrees with canonical width certification".format(prefix))
    canonical_width_summary = analysis_config["exact_cofactor_width"]["summary"]
    direct_width_summary = direct["summaries"]["W"]
    if width_only == 0:
        for key in SUMMARY_KEYS:
            if canonical_width_summary[key] is None:
                _exact(direct_width_summary[key], None, "{}.width summary {}".format(prefix, key))
            elif key == "observed":
                _exact(direct_width_summary[key], canonical_width_summary[key], "{}.width summary {}".format(prefix, key))
            else:
                _close(direct_width_summary[key], canonical_width_summary[key], "{}.width summary {}".format(prefix, key))
    else:
        if direct["observed_cells"] and (
            direct_width_summary["minimum"] < canonical_width_summary["minimum"]
            or direct_width_summary["maximum"] > canonical_width_summary["maximum"]
        ):
            raise RenderError("{} direct width range exceeds canonical width range".format(prefix))
        missing_width_total = (
            canonical_width_summary["total"]
            - (direct_width_summary["total"] or 0)
        )
        if (
            not float(missing_width_total).is_integer()
            or missing_width_total < width_only
            or missing_width_total
            < width_only * canonical_width_summary["minimum"]
            or missing_width_total
            > width_only * canonical_width_summary["maximum"]
        ):
            raise RenderError(
                "{} omitted selector-width total is infeasible".format(prefix)
            )
    construction = analysis_config["construction"]
    completed_expected = construction["certification"]["certified_cells"] - construction["fallbacks"]
    if direct["observation_source_counts"]["completed_construction"] != completed_expected:
        raise RenderError("{} completed-construction tuple census disagrees with canonical analysis".format(prefix))
    if direct["unobserved_reason_counts"]["construction_fallback"] != construction["fallbacks"]:
        raise RenderError("{} construction-fallback census disagrees with canonical analysis".format(prefix))

    partition = _mapping(
        value["partition_ratios"],
        prefix + ".partition_ratios",
        {
            "raw_complete_logs_not_necessarily_complete_searches",
            "certified_resource_prefixes",
        },
    )
    raw = _validate_structure_stratum(
        partition["raw_complete_logs_not_necessarily_complete_searches"],
        prefix + ".partition_ratios.raw_complete",
        resource_prefix=False,
    )
    resource = _validate_structure_stratum(
        partition["certified_resource_prefixes"],
        prefix + ".partition_ratios.resource_prefix",
        resource_prefix=True,
    )
    image = analysis_config["image"]
    complete_logs = image["complete_certified"]["certified_cells"]
    certified_prefix_logs = image["certified_prefix"]["certified_cells"]
    if raw["eligible_logs"] > complete_logs:
        raise RenderError("{} raw-complete structural logs exceed canonical complete logs".format(prefix))
    if resource["eligible_logs"] > certified_prefix_logs - complete_logs:
        raise RenderError("{} resource-prefix structural logs exceed canonical incomplete prefixes".format(prefix))
    partition_total = raw["eligible_logs"] + resource["eligible_logs"]
    if partition_total != direct["observation_source_counts"]["completed_construction"]:
        raise RenderError("{} partition strata do not equal completed constructions".format(prefix))
    if raw["paired_direct_tuple_and_ratio_cells"] > direct["observed_cells"]:
        raise RenderError("{} paired partition cells exceed direct tuples".format(prefix))
    direct_W_U = {}
    for row in direct["tuple_census"]:
        key = (row["W"], row["U"])
        direct_W_U[key] = direct_W_U.get(key, 0) + row["count"]
    paired_W_U = {}
    for row in raw["paired_W_U_partition_ratio_census"]:
        key = (row["W"], row["U"])
        paired_W_U[key] = paired_W_U.get(key, 0) + row["count"]
    if any(count > direct_W_U.get(key, 0) for key, count in paired_W_U.items()):
        raise RenderError("{} paired W/U census exceeds the direct-tuple census".format(prefix))
    raw_outcomes = {row["code"]: row["count"] for row in raw["terminal_outcome_counts"]}
    resource_outcomes = {row["code"]: row["count"] for row in resource["terminal_outcome_counts"]}
    resource_codes = (22, 23, 24)
    heuristic_only = direct["observation_source_counts"][
        "heuristic_event_only_resource_prefix"
    ]
    resource_before_tuple = direct["unobserved_reason_counts"][
        "resource_before_direct_tuple"
    ]
    certified_incomplete_lower_bound = (
        resource["eligible_logs"] + heuristic_only + width_only
    )
    if certified_incomplete_lower_bound > certified_prefix_logs - complete_logs:
        raise RenderError(
            "{} certified structural resource-prefix categories exceed the "
            "canonical incomplete-prefix census".format(prefix)
        )
    resource_outcome_lower_bound = (
        sum(raw_outcomes[code] for code in resource_codes)
        + resource["eligible_logs"]
        + heuristic_only
        + width_only
        + resource_before_tuple
    )
    canonical_resource_outcomes = sum(
        analysis_outcomes[code] for code in resource_codes
    )
    if resource_outcome_lower_bound > canonical_resource_outcomes:
        raise RenderError(
            "{} structural resource categories exceed the canonical resource-"
            "outcome census".format(prefix)
        )
    for code in TERMINAL_OUTCOME_CODES:
        if raw_outcomes[code] + resource_outcomes[code] > analysis_outcomes[code]:
            raise RenderError("{} partition outcome {} exceeds the canonical cell census".format(prefix, code))
    return {
        "label": label,
        "search": expected["search"],
        "cell_count": TASKS,
        "direct_W_A_V_T_U": direct,
        "partition_ratios": {
            "raw_complete_logs_not_necessarily_complete_searches": raw,
            "certified_resource_prefixes": resource,
        },
    }


def _validate_structure_candidate_pool(value, analysis_configs):
    label = "structure.selector_candidate_pool"
    keys = {
        "unit",
        "selector_config_labels",
        "eligible_tasks",
        "certified_trace_cells",
        "observed_unique_task_pool_hashes",
        "observed_tasks",
        "unobserved_tasks",
        "repeated_certified_trace_cells_deduplicated",
        "distinct_pool_hashes",
        "deduplicated_candidate_counts",
        "represented_source_counts",
        "deduplicated_candidates_per_pool_histogram",
        "source_status_counts",
        "materialized_W_U_census",
        "materialized_summaries",
    }
    value = _mapping(value, label, keys)
    _exact(
        value["unit"],
        "one-deduplicated-candidate-per-task-and-pool-hash",
        label + ".unit",
    )
    expected_selector_labels = [
        item for item in CONFIG_LABELS if item == "pdb_selector_k1"
    ]
    selector_labels = _sequence(
        value["selector_config_labels"], label + ".selector_config_labels", 1
    )
    _exact(selector_labels, expected_selector_labels, label + ".selector_config_labels")
    eligible = _integer(value["eligible_tasks"], label + ".eligible_tasks", 0, TASKS)
    _exact(eligible, TASKS, label + ".eligible_tasks")
    certified = _integer(
        value["certified_trace_cells"], label + ".certified_trace_cells", 0, TASKS
    )
    canonical_certified = analysis_configs["pdb_selector_k1"]["selector_effort"]["certification"]["certified_cells"]
    if certified != canonical_certified:
        raise RenderError("{} certified traces disagree with canonical analysis".format(label))
    pools = _integer(
        value["observed_unique_task_pool_hashes"],
        label + ".observed_unique_task_pool_hashes",
        0,
        certified,
    )
    observed_tasks = _integer(value["observed_tasks"], label + ".observed_tasks", 0, eligible)
    unobserved_tasks = _integer(value["unobserved_tasks"], label + ".unobserved_tasks", 0, eligible)
    if observed_tasks + unobserved_tasks != eligible or observed_tasks != pools:
        raise RenderError("{} task/pool denominator arithmetic changed".format(label))
    repeated = _integer(
        value["repeated_certified_trace_cells_deduplicated"],
        label + ".repeated_certified_trace_cells_deduplicated",
        0,
        certified,
    )
    if repeated != certified - pools:
        raise RenderError("{} certified-trace deduplication arithmetic changed".format(label))
    distinct = _integer(value["distinct_pool_hashes"], label + ".distinct_pool_hashes", 0, pools)
    if (pools == 0) != (distinct == 0):
        raise RenderError("{} distinct-pool-hash arithmetic changed".format(label))

    candidate_counts = _mapping(
        value["deduplicated_candidate_counts"],
        label + ".deduplicated_candidate_counts",
        {"materialized", "unmaterialized", "total"},
    )
    materialized = _integer(candidate_counts["materialized"], label + ".candidate.materialized", 0, pools * 5)
    unmaterialized = _integer(candidate_counts["unmaterialized"], label + ".candidate.unmaterialized", 0, pools * 5)
    total_candidates = _integer(candidate_counts["total"], label + ".candidate.total", 0, pools * 5)
    if materialized + unmaterialized != total_candidates:
        raise RenderError("{} candidate materialization arithmetic changed".format(label))

    source_counts = _mapping(
        value["represented_source_counts"],
        label + ".represented_source_counts",
        {"materialized", "unmaterialized", "total"},
    )
    materialized_sources = _integer(source_counts["materialized"], label + ".source.materialized", 0, pools * 5)
    unmaterialized_sources = _integer(source_counts["unmaterialized"], label + ".source.unmaterialized", 0, pools * 5)
    total_sources = _integer(source_counts["total"], label + ".source.total", 0, pools * 5)
    if materialized_sources + unmaterialized_sources != total_sources or total_sources != pools * 5:
        raise RenderError("{} represented-source arithmetic changed".format(label))
    if materialized_sources < materialized or unmaterialized_sources < unmaterialized:
        raise RenderError("{} every candidate must represent at least one source".format(label))

    histogram = _sequence(
        value["deduplicated_candidates_per_pool_histogram"],
        label + ".deduplicated_candidates_per_pool_histogram",
    )
    histogram_counts = {}
    normalized_histogram = []
    for index, row in enumerate(histogram):
        prefix = "{}.candidate_histogram[{}]".format(label, index)
        row = _mapping(row, prefix, {"candidate_count", "task_pools"})
        candidate_count = _integer(row["candidate_count"], prefix + ".candidate_count", 1, 5)
        if candidate_count in histogram_counts:
            raise RenderError("{} contains a duplicate candidate-count bin".format(label))
        task_pools = _integer(row["task_pools"], prefix + ".task_pools", 1, pools)
        histogram_counts[candidate_count] = task_pools
        normalized_histogram.append({"candidate_count": candidate_count, "task_pools": task_pools})
    if sum(histogram_counts.values()) != pools or sum(
        count * task_pools for count, task_pools in histogram_counts.items()
    ) != total_candidates:
        raise RenderError("{} candidate-pool histogram arithmetic changed".format(label))
    normalized_histogram.sort(key=lambda row: row["candidate_count"])
    canonical_selector = analysis_configs["pdb_selector_k1"]["selector_effort"]
    candidate_observations = [
        count
        for count, task_pools in histogram_counts.items()
        for _unused in range(task_pools)
    ]
    expected_candidate_summary = _expected_structure_summary(candidate_observations)
    canonical_candidate_summary = canonical_selector["candidate_records"]
    for key in SUMMARY_KEYS:
        if expected_candidate_summary[key] is None:
            _exact(canonical_candidate_summary[key], None, "{}.canonical candidate {}".format(label, key))
        elif key == "observed":
            _exact(canonical_candidate_summary[key], expected_candidate_summary[key], "{}.canonical candidate {}".format(label, key))
        else:
            _close(canonical_candidate_summary[key], expected_candidate_summary[key], "{}.canonical candidate {}".format(label, key))
    _close(
        canonical_selector["source_evaluations"]["total"],
        total_sources,
        label + ".canonical source-evaluation total",
    )

    source_rows = _sequence(value["source_status_counts"], label + ".source_status_counts", 5)
    source_by_name = {}
    for index, row in enumerate(source_rows):
        prefix = "{}.source_status_counts[{}]".format(label, index)
        row = _mapping(
            row,
            prefix,
            {"source", "materialized_task_pools", "unmaterialized_task_pools"},
        )
        source = row["source"]
        if source not in STRUCTURE_SELECTOR_SOURCES or source in source_by_name:
            raise RenderError("{} has an unexpected or duplicate source".format(label))
        yes = _integer(row["materialized_task_pools"], prefix + ".materialized", 0, pools)
        no = _integer(row["unmaterialized_task_pools"], prefix + ".unmaterialized", 0, pools)
        if yes + no != pools:
            raise RenderError("{} source status does not conserve task pools".format(prefix))
        source_by_name[source] = {
            "source": source,
            "materialized_task_pools": yes,
            "unmaterialized_task_pools": no,
        }
    if set(source_by_name) != set(STRUCTURE_SELECTOR_SOURCES):
        raise RenderError("{} source identities changed".format(label))
    if sum(row["materialized_task_pools"] for row in source_by_name.values()) != materialized_sources or sum(
        row["unmaterialized_task_pools"] for row in source_by_name.values()
    ) != unmaterialized_sources:
        raise RenderError("{} source-status totals disagree with represented sources".format(label))

    census = _sequence(value["materialized_W_U_census"], label + ".materialized_W_U_census")
    identities = set()
    normalized_census = []
    widths = []
    uppers = []
    census_sources = 0
    for index, row in enumerate(census):
        prefix = "{}.materialized_W_U_census[{}]".format(label, index)
        row = _mapping(
            row,
            prefix,
            {"W", "U", "deduplicated_candidate_count", "represented_source_count"},
        )
        W = _integer(row["W"], prefix + ".W", 1)
        U = _integer(row["U"], prefix + ".U", W)
        identity = (W, U)
        if identity in identities:
            raise RenderError("{} contains a duplicate W/U bin".format(label))
        identities.add(identity)
        count = _integer(row["deduplicated_candidate_count"], prefix + ".candidate_count", 1, materialized)
        represented = _integer(row["represented_source_count"], prefix + ".source_count", count, count * 5)
        widths.extend([W] * count)
        uppers.extend([U] * count)
        census_sources += represented
        normalized_census.append(
            {
                "W": W,
                "U": U,
                "deduplicated_candidate_count": count,
                "represented_source_count": represented,
            }
        )
    if len(widths) != materialized or census_sources != materialized_sources:
        raise RenderError("{} materialized W/U census does not conserve candidates or sources".format(label))
    normalized_census.sort(key=lambda row: (row["W"], row["U"]))
    summaries = _mapping(
        value["materialized_summaries"],
        label + ".materialized_summaries",
        {"W", "U", "U_over_W"},
    )
    normalized_summaries = {
        "W": _validate_structure_summary(summaries["W"], label + ".summaries.W", widths),
        "U": _validate_structure_summary(summaries["U"], label + ".summaries.U", uppers),
        "U_over_W": _validate_structure_summary(
            summaries["U_over_W"],
            label + ".summaries.U_over_W",
            [upper / width for width, upper in zip(widths, uppers)],
        ),
    }
    for key in ("W", "U"):
        _require_analyzer_integer_summary_types(
            normalized_summaries[key], "{}.summaries.{}".format(label, key)
        )
    _require_analyzer_float_summary_types(
        normalized_summaries["U_over_W"], label + ".summaries.U_over_W"
    )
    return {
        "unit": value["unit"],
        "selector_config_labels": expected_selector_labels,
        "eligible_tasks": eligible,
        "certified_trace_cells": certified,
        "observed_unique_task_pool_hashes": pools,
        "observed_tasks": observed_tasks,
        "unobserved_tasks": unobserved_tasks,
        "repeated_certified_trace_cells_deduplicated": repeated,
        "distinct_pool_hashes": distinct,
        "deduplicated_candidate_counts": {
            "materialized": materialized,
            "unmaterialized": unmaterialized,
            "total": total_candidates,
        },
        "represented_source_counts": {
            "materialized": materialized_sources,
            "unmaterialized": unmaterialized_sources,
            "total": total_sources,
        },
        "deduplicated_candidates_per_pool_histogram": normalized_histogram,
        "source_status_counts": [source_by_name[source] for source in STRUCTURE_SELECTOR_SOURCES],
        "materialized_W_U_census": normalized_census,
        "materialized_summaries": normalized_summaries,
    }


def _validate_certification(value, label, expected_eligible=None):
    value = _mapping(value, label, CERTIFICATION_KEYS)
    eligible = _integer(value["eligible_cells"], label + ".eligible_cells", 0)
    certified = _integer(
        value["certified_cells"], label + ".certified_cells", 0, eligible
    )
    missing = _integer(
        value["uncertified_or_unobserved_cells"],
        label + ".uncertified_or_unobserved_cells",
        0,
    )
    if expected_eligible is not None and eligible != expected_eligible:
        raise RenderError("{}.eligible_cells changed".format(label))
    if missing != eligible - certified:
        raise RenderError("{} certification arithmetic changed".format(label))
    if eligible == 0:
        if value["rate"] is not None:
            raise RenderError("{}.rate must be null for an empty denominator".format(label))
    else:
        _close(value["rate"], certified / eligible, label + ".rate")
    return value


def _validate_fraction(value, label, expected=None):
    value = _mapping(value, label, {"numerator", "denominator", "value"})
    numerator = _integer(value["numerator"], label + ".numerator")
    denominator = _integer(value["denominator"], label + ".denominator", 1)
    fraction = Fraction(numerator, denominator)
    if (fraction.numerator, fraction.denominator) != (numerator, denominator):
        raise RenderError("{} is not a reduced fraction".format(label))
    if expected is not None and fraction != expected:
        raise RenderError("{} exact fraction changed".format(label))
    _close(value["value"], float(fraction), label + ".value")
    return fraction


def _validate_execution(value, launch_pins):
    keys = {
        "protocol",
        "protocol_revision",
        "full_runner_source_sha256",
        "planner_revision",
        "planner_binary_sha256",
        "planner_preprocess_sha256",
        "p5_heldout_protocol_revision",
        "p5_heldout_planner_revision",
        "p5_heldout_planner_binary_sha256",
        "p5_heldout_planner_preprocess_sha256",
        "p5_to_p6_git_lineage_protocol",
        "presearch_sigxcpu_normalization_protocol",
        "presearch_sigxcpu_raw_exit_code",
        "presearch_sigxcpu_effective_exit_code",
        "presearch_sigxcpu_components",
        "initial_dead_construction_logging_protocol",
        "benchmark_revision",
        "task_manifest_sha256",
        "domain_sequence_sha256",
        "domain_task_counts_sha256",
        "task_sources_sha256",
        "source_manifest_sha256",
        "option_matrix_sha256",
        "predeclared_comparisons_sha256",
        "properties_canonical_sha256",
        "task_count",
        "domain_count",
        "config_count",
        "cell_count",
        "array_layout",
        "prospective_start_job_sha256",
    }
    value = _mapping(value, "execution", keys)
    expected = {
        "protocol": launch_pins["protocol"],
        "protocol_revision": launch_pins["protocol_revision"],
        "full_runner_source_sha256": launch_pins["full_runner_source_sha256"],
        "planner_revision": launch_pins["planner_revision"],
        "planner_binary_sha256": launch_pins["planner_binary_sha256"],
        "planner_preprocess_sha256": launch_pins["planner_preprocess_sha256"],
        "p5_heldout_protocol_revision": EXPECTED_P5_HELDOUT_PROTOCOL_REVISION,
        "p5_heldout_planner_revision": EXPECTED_P5_HELDOUT_PLANNER_REVISION,
        "p5_heldout_planner_binary_sha256": EXPECTED_P5_HELDOUT_BINARY_SHA256,
        "p5_heldout_planner_preprocess_sha256": (
            EXPECTED_P5_HELDOUT_PREPROCESS_SHA256
        ),
        "p5_to_p6_git_lineage_protocol": EXPECTED_P5_TO_P6_LINEAGE_PROTOCOL,
        "presearch_sigxcpu_normalization_protocol": (
            EXPECTED_PRESEARCH_SIGXCPU_PROTOCOL
        ),
        "presearch_sigxcpu_raw_exit_code": EXPECTED_PRESEARCH_SIGXCPU_RAW_EXIT,
        "presearch_sigxcpu_effective_exit_code": (
            EXPECTED_PRESEARCH_SIGXCPU_EFFECTIVE_EXIT
        ),
        "presearch_sigxcpu_components": EXPECTED_PRESEARCH_SIGXCPU_COMPONENTS,
        "initial_dead_construction_logging_protocol": EXPECTED_INITIAL_DEAD_PROTOCOL,
        "benchmark_revision": EXPECTED_BENCHMARK_REVISION,
        "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
        "domain_sequence_sha256": EXPECTED_DOMAIN_SEQUENCE_SHA256,
        "domain_task_counts_sha256": EXPECTED_DOMAIN_TASK_COUNTS_SHA256,
        "task_sources_sha256": EXPECTED_TASK_SOURCES_SHA256,
        "source_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
        "option_matrix_sha256": EXPECTED_OPTION_MATRIX_SHA256,
        "predeclared_comparisons_sha256": EXPECTED_COMPARISONS_SHA256,
        "task_count": TASKS,
        "domain_count": DOMAINS,
        "config_count": CONFIG_COUNT,
        "cell_count": CELLS,
        "prospective_start_job_sha256": launch_pins[
            "prospective_start_job_sha256"
        ],
    }
    for key, expected_value in expected.items():
        _exact(value[key], expected_value, "execution." + key)
    _require_sha256(value["properties_canonical_sha256"], "logical properties digest")
    layout = _mapping(
        value["array_layout"],
        "execution.array_layout",
        {
            "raw_runs",
            "array_tasks",
            "runs_per_array_task",
            "array_task_run_distribution",
            "scheduler_time_limit_seconds",
            "wrapper_allowance_seconds_per_run",
        },
    )
    expected_layout = {
        "raw_runs": CELLS,
        "array_tasks": 964,
        "runs_per_array_task": 10,
        "scheduler_time_limit_seconds": 4200,
        "wrapper_allowance_seconds_per_run": 60,
    }
    for key, expected_value in expected_layout.items():
        _exact(layout[key], expected_value, "execution.array_layout." + key)
    distribution = _mapping(
        layout["array_task_run_distribution"],
        "execution.array_layout.array_task_run_distribution",
        {
            "full_array_tasks",
            "full_runs_per_array_task",
            "partial_array_tasks",
            "partial_runs",
        },
    )
    expected_distribution = {
        "full_array_tasks": 963,
        "full_runs_per_array_task": 10,
        "partial_array_tasks": 1,
        "partial_runs": 9,
    }
    for key, expected_value in expected_distribution.items():
        _exact(
            distribution[key],
            expected_value,
            "execution.array_layout.array_task_run_distribution." + key,
        )
    if (
        distribution["full_array_tasks"] * distribution["full_runs_per_array_task"]
        + distribution["partial_runs"]
        != CELLS
        or distribution["full_array_tasks"] + distribution["partial_array_tasks"]
        != layout["array_tasks"]
    ):
        raise RenderError("execution array-layout arithmetic changed")


def _validate_domain_coverage(entries, label, tasks, *, expected_counts=None):
    entries = _sequence(entries, label, DOMAINS)
    seen = set()
    counts = []
    solved_by_domain = {}
    for index, entry in enumerate(entries):
        prefix = "{}[{}]".format(label, index)
        entry = _mapping(entry, prefix, {"domain", "solved", "tasks", "rate"})
        domain = entry["domain"]
        if type(domain) is not str or not domain or domain in seen:
            raise RenderError("{} has a duplicate or invalid domain".format(prefix))
        seen.add(domain)
        count = _integer(entry["tasks"], prefix + ".tasks", 1)
        solved = _integer(entry["solved"], prefix + ".solved", 0, count)
        _close(entry["rate"], solved / count, prefix + ".rate")
        counts.append((domain, count))
        solved_by_domain[domain] = solved
    counts.sort(key=lambda item: item[0])
    if sum(count for _, count in counts) != tasks:
        raise RenderError("{} task-count arithmetic changed".format(label))
    if expected_counts is not None and counts != expected_counts:
        raise RenderError("{} domain order/counts changed".format(label))
    return counts, solved_by_domain


def _validate_config(value, expected):
    label = expected["label"]
    prefix = "config[{}]".format(label)
    keys = {
        "label",
        "search",
        "roles",
        "coverage",
        "per_domain_coverage",
        "micro_par2_seconds",
        "solved_runtime_seconds",
        "search_effort_on_solved_cells",
        "construction",
        "image",
        "exact_cofactor_width",
        "selector_effort",
    }
    value = _mapping(value, prefix, keys)
    for key in ("label", "search", "roles"):
        _exact(value[key], expected[key], prefix + "." + key)

    coverage = _mapping(value["coverage"], prefix + ".coverage", {"solved", "tasks", "rate"})
    _exact(coverage["tasks"], TASKS, prefix + ".coverage.tasks")
    solved = _integer(coverage["solved"], prefix + ".coverage.solved", 0, TASKS)
    _close(coverage["rate"], solved / TASKS, prefix + ".coverage.rate")
    domain_counts, domain_solved = _validate_domain_coverage(
        value["per_domain_coverage"], prefix + ".per_domain_coverage", TASKS
    )
    if sum(domain_solved.values()) != solved:
        raise RenderError("{} per-domain solved total changed".format(prefix))

    runtime = _mapping(
        value["solved_runtime_seconds"],
        prefix + ".solved_runtime_seconds",
        {"certification", "summary"},
    )
    runtime_cert = _validate_certification(
        runtime["certification"],
        prefix + ".solved_runtime_seconds.certification",
        solved,
    )
    if runtime_cert["certified_cells"] != solved:
        raise RenderError("{} solved runtime must be complete".format(prefix))
    runtime_summary = _validate_summary(
        runtime["summary"], prefix + ".solved_runtime_seconds.summary", solved, True
    )
    par2 = _number(value["micro_par2_seconds"], prefix + ".micro_par2_seconds", 0, PAR2_PENALTY)
    expected_par2 = (
        (runtime_summary["total"] or 0.0) + (TASKS - solved) * PAR2_PENALTY
    ) / TASKS
    _close(par2, expected_par2, prefix + ".micro_par2_seconds", absolute=1e-10)

    effort = _mapping(
        value["search_effort_on_solved_cells"],
        prefix + ".search_effort_on_solved_cells",
        {"certification", "summary"},
    )
    effort_cert = _validate_certification(
        effort["certification"],
        prefix + ".search_effort_on_solved_cells.certification",
        solved,
    )
    if effort_cert["certified_cells"] != solved:
        raise RenderError("{} solved effort must be complete".format(prefix))
    _validate_count_summary(
        effort["summary"],
        prefix + ".search_effort_on_solved_cells.summary",
        solved,
    )

    construction = _mapping(
        value["construction"],
        prefix + ".construction",
        {"certification", "completed", "fallbacks", "time_seconds"},
    )
    construction_eligible = 0 if label == "blind_fw" else TASKS
    construction_cert = _validate_certification(
        construction["certification"],
        prefix + ".construction.certification",
        construction_eligible,
    )
    completed = _integer(construction["completed"], prefix + ".construction.completed", 0)
    fallbacks = _integer(construction["fallbacks"], prefix + ".construction.fallbacks", 0)
    if completed + fallbacks != construction_cert["certified_cells"]:
        raise RenderError("{} construction outcome arithmetic changed".format(prefix))
    _validate_summary(
        construction["time_seconds"],
        prefix + ".construction.time_seconds",
        construction_cert["certified_cells"],
        True,
    )

    width = _mapping(
        value["exact_cofactor_width"],
        prefix + ".exact_cofactor_width",
        {"certification", "summary"},
    )
    width_eligible = 0 if label == "blind_fw" else TASKS
    width_cert = _validate_certification(
        width["certification"],
        prefix + ".exact_cofactor_width.certification",
        width_eligible,
    )
    _validate_count_summary(
        width["summary"],
        prefix + ".exact_cofactor_width.summary",
        width_cert["certified_cells"],
    )
    if label == "pdb_selector_k1":
        # A certified selector prefix can contain the selected exact width on
        # a resource exit before the construction-completion record.
        if width_cert["certified_cells"] < completed:
            raise RenderError("{} selector width count is below completed construction".format(prefix))
        maximum_width = width["summary"]["maximum"]
        if maximum_width is not None and float(maximum_width) > 1:
            raise RenderError("{} K=1 selector reports width above one".format(prefix))
    elif label != "blind_fw" and width_cert["certified_cells"] != completed:
        raise RenderError("{} width/construction completion counts disagree".format(prefix))

    image = _mapping(
        value["image"],
        prefix + ".image",
        {
            "certified_prefix",
            "complete_certified",
            "presearch_empty_cells",
            "prefix_image_time_seconds",
            "complete_amortization",
        },
    )
    image_prefix = _validate_certification(
        image["certified_prefix"], prefix + ".image.certified_prefix", TASKS
    )
    image_complete = _validate_certification(
        image["complete_certified"], prefix + ".image.complete_certified", TASKS
    )
    if image_complete["certified_cells"] > image_prefix["certified_cells"]:
        raise RenderError("{} complete image cells exceed certified prefixes".format(prefix))
    presearch = _integer(
        image["presearch_empty_cells"], prefix + ".image.presearch_empty_cells", 0, TASKS
    )
    # Every pre-search-empty cell lacks a search metric prefix, but an early
    # search-side resource exit can also lack one.  Do not silently equate the
    # two independently reported denominators.
    if presearch > TASKS - image_prefix["certified_cells"]:
        raise RenderError("{} pre-search count exceeds missing image prefixes".format(prefix))
    _validate_summary(
        image["prefix_image_time_seconds"],
        prefix + ".image.prefix_image_time_seconds",
        image_prefix["certified_cells"],
        True,
    )
    amort = _mapping(
        image["complete_amortization"],
        prefix + ".image.complete_amortization",
        {
            "complete_certified_cells",
            "image_time_seconds",
            "image_calls_attempted",
            "image_calls_completed",
            "batched_images",
            "aggregate_image_time_seconds",
            "aggregate_completed_image_calls",
            "seconds_per_completed_image_call",
        },
    )
    complete_cells = image_complete["certified_cells"]
    _exact(
        amort["complete_certified_cells"],
        complete_cells,
        prefix + ".image.complete_amortization.complete_certified_cells",
    )
    time_summary = _validate_summary(
        amort["image_time_seconds"],
        prefix + ".image.complete_amortization.image_time_seconds",
        complete_cells,
        True,
    )
    attempted_summary = _validate_count_summary(
        amort["image_calls_attempted"],
        prefix + ".image.complete_amortization.image_calls_attempted",
        complete_cells,
    )
    completed_summary = _validate_count_summary(
        amort["image_calls_completed"],
        prefix + ".image.complete_amortization.image_calls_completed",
        complete_cells,
    )
    _validate_count_summary(
        amort["batched_images"],
        prefix + ".image.complete_amortization.batched_images",
        complete_cells,
    )
    _close(
        amort["aggregate_image_time_seconds"],
        time_summary["total"] or 0,
        prefix + ".image.complete_amortization.aggregate_image_time_seconds",
    )
    calls = _integer(
        amort["aggregate_completed_image_calls"],
        prefix + ".image.complete_amortization.aggregate_completed_image_calls",
        0,
    )
    _close(
        completed_summary["total"] or 0,
        calls,
        prefix + ".image.complete_amortization.completed-call total",
    )
    if attempted_summary["total"] is not None and completed_summary["total"] is not None:
        if completed_summary["total"] > attempted_summary["total"]:
            raise RenderError("{} completed image calls exceed attempts".format(prefix))
    seconds_per_call = amort["seconds_per_completed_image_call"]
    if calls:
        _close(
            seconds_per_call,
            float(amort["aggregate_image_time_seconds"]) / calls,
            prefix + ".image.complete_amortization.seconds_per_completed_image_call",
        )
    elif seconds_per_call is not None:
        raise RenderError("{} zero calls require null amortization".format(prefix))

    selector = _mapping(
        value["selector_effort"],
        prefix + ".selector_effort",
        {
            "certification",
            "candidate_records",
            "source_evaluations",
            "feasible_candidate_records",
            "rejected_candidate_records",
            "selected_source_counts",
        },
    )
    selector_eligible = TASKS if label == "pdb_selector_k1" else 0
    selector_cert = _validate_certification(
        selector["certification"],
        prefix + ".selector_effort.certification",
        selector_eligible,
    )
    for name in (
        "candidate_records",
        "source_evaluations",
        "feasible_candidate_records",
        "rejected_candidate_records",
    ):
        _validate_count_summary(
            selector[name],
            prefix + ".selector_effort." + name,
            selector_cert["certified_cells"],
        )
    source_counts = _mapping(
        selector["selected_source_counts"],
        prefix + ".selector_effort.selected_source_counts",
        set(SELECTOR_SOURCES),
    )
    for source in SELECTOR_SOURCES:
        _integer(source_counts[source], prefix + ".selector source " + source, 0)
    if sum(source_counts.values()) != selector_cert["certified_cells"]:
        raise RenderError("{} selector source counts do not exhaust traces".format(prefix))
    candidate_total = selector["candidate_records"]["total"] or 0
    feasible_total = selector["feasible_candidate_records"]["total"] or 0
    rejected_total = selector["rejected_candidate_records"]["total"] or 0
    source_evaluations_total = selector["source_evaluations"]["total"] or 0
    _close(
        candidate_total,
        float(feasible_total) + float(rejected_total),
        prefix + ".selector candidate feasibility total",
    )
    if float(source_evaluations_total) < float(candidate_total):
        raise RenderError("{} selector source evaluations are below candidate records".format(prefix))

    return domain_counts


def _validate_pair_metric(value, label, maximum_pairs, *, integer_totals=False):
    value = _mapping(value, label, PAIR_KEYS)
    pairs = _integer(value["pairs"], label + ".pairs", 0, maximum_pairs)
    candidate = _number(value["candidate_total"], label + ".candidate_total", 0)
    reference = _number(value["reference_total"], label + ".reference_total", 0)
    _close(value["candidate_minus_reference"], candidate - reference, label + ".candidate_minus_reference")
    if integer_totals:
        for name in (
            "candidate_total",
            "reference_total",
            "candidate_minus_reference",
        ):
            if not float(value[name]).is_integer():
                raise RenderError("{}.{} must be integral".format(label, name))
    if reference > 0:
        _close(value["candidate_over_reference"], candidate / reference, label + ".candidate_over_reference")
    elif value["candidate_over_reference"] is not None:
        raise RenderError("{} zero reference total requires null ratio".format(label))
    if pairs == 0 and (candidate != 0 or reference != 0):
        raise RenderError("{} empty intersection has a nonzero total".format(label))
    return pairs


def _validate_p5_config(value, expected):
    label = expected["label"]
    prefix = "P5 config[{}]".format(label)
    value = _mapping(value, prefix, P5_CONFIG_KEYS)
    for key in ("label", "search", "roles"):
        _exact(value[key], expected[key], prefix + "." + key)

    coverage = _mapping(
        value["coverage"], prefix + ".coverage", {"solved", "tasks", "rate"}
    )
    _exact(coverage["tasks"], P5_TASKS, prefix + ".coverage.tasks")
    solved = _integer(
        coverage["solved"], prefix + ".coverage.solved", 0, P5_TASKS
    )
    _close(coverage["rate"], solved / P5_TASKS, prefix + ".coverage.rate")

    runtime = _validate_summary(
        value["solved_planner_time_seconds"],
        prefix + ".solved_planner_time_seconds",
        solved,
        True,
    )
    par2 = _number(
        value["micro_par2_seconds"],
        prefix + ".micro_par2_seconds",
        0,
        PAR2_PENALTY,
    )
    expected_par2 = (
        float(runtime["total"] or 0) + (P5_TASKS - solved) * PAR2_PENALTY
    ) / P5_TASKS
    _close(
        par2,
        expected_par2,
        prefix + ".micro_par2_seconds",
        absolute=1e-10,
    )
    _validate_count_summary(
        value["effort_on_solved_cells"],
        prefix + ".effort_on_solved_cells",
        solved,
    )

    construction = _mapping(
        value["construction"],
        prefix + ".construction",
        {
            "completed",
            "fallbacks",
            "observed",
            "time_seconds",
            "unobserved_resource_prefixes",
        },
    )
    construction_observed = _integer(
        construction["observed"], prefix + ".construction.observed", 0, P5_TASKS
    )
    completed = _integer(
        construction["completed"], prefix + ".construction.completed", 0
    )
    fallbacks = _integer(
        construction["fallbacks"], prefix + ".construction.fallbacks", 0
    )
    unobserved = _integer(
        construction["unobserved_resource_prefixes"],
        prefix + ".construction.unobserved_resource_prefixes",
        0,
        P5_TASKS,
    )
    if completed + fallbacks != construction_observed:
        raise RenderError("{} construction outcome arithmetic changed".format(prefix))
    if construction_observed + unobserved != P5_TASKS:
        raise RenderError("{} construction denominator arithmetic changed".format(prefix))
    _validate_summary(
        construction["time_seconds"],
        prefix + ".construction.time_seconds",
        construction_observed,
        True,
    )

    width = _validate_count_summary(
        value["cofactor_width"],
        prefix + ".cofactor_width",
        completed,
    )
    if label == "blind_fw":
        if completed != 0 or construction_observed != 0:
            raise RenderError("P5 blind control unexpectedly has construction records")
    elif completed == 0:
        raise RenderError("{} has no completed heuristic construction".format(prefix))
    if label == "pdb_selector_k1" and width["maximum"] != 1:
        raise RenderError("P5 K=1 selector width maximum changed")

    image = _mapping(
        value["image_time_seconds"],
        prefix + ".image_time_seconds",
        {
            "certified_prefix",
            "complete_summary",
            "complete_summary_cells",
            "presearch_empty_cells",
            "semantically_certified_prefix_cells",
        },
    )
    prefix_cells = _integer(
        image["semantically_certified_prefix_cells"],
        prefix + ".image prefix cells",
        0,
        P5_TASKS,
    )
    complete_cells = _integer(
        image["complete_summary_cells"],
        prefix + ".image complete cells",
        0,
        prefix_cells,
    )
    presearch_cells = _integer(
        image["presearch_empty_cells"],
        prefix + ".image pre-search cells",
        0,
        P5_TASKS,
    )
    if prefix_cells + presearch_cells != P5_TASKS:
        raise RenderError("{} P5 image-prefix denominator arithmetic changed".format(prefix))
    _validate_summary(
        image["certified_prefix"],
        prefix + ".image_time_seconds.certified_prefix",
        prefix_cells,
        True,
    )
    _validate_summary(
        image["complete_summary"],
        prefix + ".image_time_seconds.complete_summary",
        complete_cells,
        True,
    )
    return value


def _validate_p5_comparison(value, declaration, configs, prefix):
    name, candidate_label, reference_label, roles = declaration
    value = _mapping(value, prefix, P5_COMPARISON_KEYS)
    expected_identity = {
        "name": name,
        "candidate": candidate_label,
        "reference": reference_label,
        "roles": roles,
    }
    for key, expected in expected_identity.items():
        _exact(value[key], expected, prefix + "." + key)
    candidate = configs[candidate_label]
    reference = configs[reference_label]
    coverage = _mapping(
        value["coverage"],
        prefix + ".coverage",
        {
            "candidate_minus_reference_tasks",
            "candidate_minus_reference_rate",
            "discordant_candidate_wins",
            "discordant_candidate_losses",
            "both_solved",
            "both_unsolved",
        },
    )
    wins = _integer(coverage["discordant_candidate_wins"], prefix + ".wins", 0)
    losses = _integer(
        coverage["discordant_candidate_losses"], prefix + ".losses", 0
    )
    both = _integer(coverage["both_solved"], prefix + ".both_solved", 0)
    neither = _integer(coverage["both_unsolved"], prefix + ".both_unsolved", 0)
    if wins + losses + both + neither != P5_TASKS:
        raise RenderError("{} coverage partition changed".format(prefix))
    if (
        both + wins != candidate["coverage"]["solved"]
        or both + losses != reference["coverage"]["solved"]
    ):
        raise RenderError("{} coverage disagrees with P5 configuration rows".format(prefix))
    delta = wins - losses
    _exact(
        coverage["candidate_minus_reference_tasks"],
        delta,
        prefix + ".coverage task difference",
    )
    _close(
        coverage["candidate_minus_reference_rate"],
        delta / P5_TASKS,
        prefix + ".coverage rate",
    )

    par2 = _mapping(
        value["micro_par2_seconds"],
        prefix + ".micro_par2_seconds",
        {"candidate", "reference", "candidate_minus_reference"},
    )
    _close(
        par2["candidate"],
        candidate["micro_par2_seconds"],
        prefix + ".candidate PAR2",
    )
    _close(
        par2["reference"],
        reference["micro_par2_seconds"],
        prefix + ".reference PAR2",
    )
    _close(
        par2["candidate_minus_reference"],
        float(par2["candidate"]) - float(par2["reference"]),
        prefix + ".PAR2 difference",
    )

    runtime = _mapping(
        value["jointly_solved_runtime"],
        prefix + ".jointly_solved_runtime",
        {"pairs", "candidate_over_reference_geometric_mean", "ratio_summary"},
    )
    _exact(runtime["pairs"], both, prefix + ".runtime pairs")
    ratios = _validate_summary(
        runtime["ratio_summary"], prefix + ".runtime ratio summary", both, True
    )
    geomean = _number(
        runtime["candidate_over_reference_geometric_mean"],
        prefix + ".runtime geometric mean",
        0,
    )
    if both and (geomean <= 0 or float(ratios["minimum"]) <= 0):
        raise RenderError("{} runtime ratios must be positive".format(prefix))

    candidate_image = candidate["image_time_seconds"]["complete_summary_cells"]
    reference_image = reference["image_time_seconds"]["complete_summary_cells"]
    _validate_pair_metric(
        value["paired_complete_image_time_seconds"],
        prefix + ".paired image time",
        min(candidate_image, reference_image),
    )
    candidate_width = candidate["cofactor_width"]["observed"]
    reference_width = reference["cofactor_width"]["observed"]
    _validate_pair_metric(
        value["paired_observed_cofactor_width"],
        prefix + ".paired width",
        min(candidate_width, reference_width),
        integer_totals=True,
    )
    effort_pairs = _validate_pair_metric(
        value["paired_solved_effort"],
        prefix + ".paired solved effort",
        both,
        integer_totals=True,
    )
    if effort_pairs != both:
        raise RenderError("{} solved-effort intersection is incomplete".format(prefix))
    candidate_construction = candidate["construction"]["observed"]
    reference_construction = reference["construction"]["observed"]
    _validate_pair_metric(
        value["paired_observed_construction_time_seconds"],
        prefix + ".paired construction time",
        min(candidate_construction, reference_construction),
    )
    return value


def _validate_p5_analysis(value, analysis_sha256):
    """Independently validate the exact frozen P5 held-out analysis contract."""
    _require_sha256(analysis_sha256, "P5 analysis artifact digest")
    actual = sha256_bytes(canonical_json(value).encode("ascii") + b"\n")
    if actual != analysis_sha256:
        raise RenderError("in-memory P5 analysis does not match its claimed digest")
    value = _mapping(value, "P5 analysis", P5_TOP_KEYS)
    _exact(value["schema"], P5_ANALYSIS_SCHEMA, "P5 analysis.schema")
    _exact(
        value["analysis_protocol"],
        P5_ANALYSIS_PROTOCOL,
        "P5 analysis.analysis_protocol",
    )

    selection = _mapping(
        value["selection_artifact"],
        "P5 selection_artifact",
        {
            "schema",
            "raw_sha256",
            "global_winner_alias",
            "selector_family_winner",
            "matched_same_k_unbatched",
            "pilot_planner_revision",
            "pilot_planner_binary_sha256",
            "pilot_planner_preprocess_sha256",
        },
    )
    expected_selection = {
        "schema": SELECTION_SCHEMA,
        "raw_sha256": EXPECTED_SELECTION_ARTIFACT_SHA256,
        "global_winner_alias": "ms_exact",
        "selector_family_winner": "pdb_selector_k1",
        "matched_same_k_unbatched": None,
        "pilot_planner_revision": EXPECTED_PILOT_REVISION,
        "pilot_planner_binary_sha256": EXPECTED_PILOT_BINARY_SHA256,
        "pilot_planner_preprocess_sha256": EXPECTED_PILOT_PREPROCESS_SHA256,
    }
    _exact(selection, expected_selection, "P5 selection artifact identity")

    execution = _mapping(
        value["execution"],
        "P5 execution",
        {
            "benchmark_revision",
            "cell_count",
            "config_count",
            "domain_count",
            "initial_dead_construction_logging_protocol",
            "materialized_pddl_bytes",
            "materialized_pddl_files",
            "materialized_pddl_protocol",
            "option_matrix_sha256",
            "planner_binary_sha256",
            "planner_preprocess_sha256",
            "planner_revision",
            "predeclared_comparisons_sha256",
            "properties_canonical_sha256",
            "protocol",
            "protocol_revision",
            "task_count",
            "task_manifest_sha256",
            "task_sources_sha256",
        },
    )
    expected_execution = {
        "benchmark_revision": EXPECTED_BENCHMARK_REVISION,
        "cell_count": P5_CELLS,
        "config_count": P5_CONFIG_COUNT,
        "domain_count": P5_DOMAINS,
        "initial_dead_construction_logging_protocol": EXPECTED_INITIAL_DEAD_PROTOCOL,
        "materialized_pddl_bytes": P5_MATERIALIZED_PDDL_BYTES,
        "materialized_pddl_files": P5_MATERIALIZED_PDDL_FILES,
        "materialized_pddl_protocol": P5_MATERIALIZED_PDDL_PROTOCOL,
        "option_matrix_sha256": EXPECTED_OPTION_MATRIX_SHA256,
        "planner_binary_sha256": EXPECTED_P5_HELDOUT_BINARY_SHA256,
        "planner_preprocess_sha256": EXPECTED_P5_HELDOUT_PREPROCESS_SHA256,
        "planner_revision": EXPECTED_P5_HELDOUT_PLANNER_REVISION,
        "predeclared_comparisons_sha256": EXPECTED_COMPARISONS_SHA256,
        "properties_canonical_sha256": EXPECTED_P5_PROPERTIES_SHA256,
        "protocol": P5_PROTOCOL,
        "protocol_revision": EXPECTED_P5_HELDOUT_PROTOCOL_REVISION,
        "task_count": P5_TASKS,
        "task_manifest_sha256": EXPECTED_HELDOUT_TASK_SHA256,
        "task_sources_sha256": EXPECTED_HELDOUT_SOURCES_SHA256,
    }
    _exact(execution, expected_execution, "P5 execution identity")
    _exact(
        value["decision_policy"],
        {
            "comparisons_source": "selection-artifact-v3",
            "configuration_order_source": "selection-artifact-v3",
            "rerank_on_validation": False,
        },
        "P5 decision policy",
    )

    secondary = _mapping(
        value["secondary"],
        "P5 secondary",
        {
            "comparisons",
            "configs",
            "metric_protocols",
            "ms_build_budget_fallback",
            "status",
        },
    )
    _exact(secondary["status"], "descriptive", "P5 secondary.status")
    _exact(
        secondary["metric_protocols"],
        P5_METRIC_PROTOCOLS,
        "P5 secondary.metric_protocols",
    )
    config_entries = _sequence(
        secondary["configs"], "P5 secondary.configs", P5_CONFIG_COUNT
    )
    supplied_configs = {}
    for index, entry in enumerate(config_entries):
        if type(entry) is not dict or type(entry.get("label")) is not str:
            raise RenderError("P5 config {} lacks a label".format(index))
        label = entry["label"]
        if label in supplied_configs or label not in CONFIG_BY_LABEL:
            raise RenderError("P5 configs contain an unexpected or duplicate label")
        supplied_configs[label] = entry
    if set(supplied_configs) != set(CONFIG_LABELS):
        raise RenderError("P5 configuration labels are missing or changed")
    configs = {}
    for expected in CONFIGS:
        configs[expected["label"]] = _validate_p5_config(
            supplied_configs[expected["label"]], expected
        )

    fallback = _mapping(
        secondary["ms_build_budget_fallback"],
        "P5 build-budget fallback",
        {"cells", "fallbacks", "incidence", "label"},
    )
    _exact(fallback["label"], "ms_cap32_build60", "P5 fallback label")
    _exact(fallback["cells"], P5_TASKS, "P5 fallback cells")
    expected_fallbacks = configs["ms_cap32_build60"]["construction"]["fallbacks"]
    _exact(fallback["fallbacks"], expected_fallbacks, "P5 fallback count")
    _close(
        fallback["incidence"],
        expected_fallbacks / P5_TASKS,
        "P5 fallback incidence",
    )

    primary = _mapping(
        value["primary"],
        "P5 primary",
        {
            "bootstrap",
            "candidate",
            "comparison",
            "domain_contributions",
            "domain_order",
            "domains",
            "estimand",
            "estimate",
            "paired_descriptive_metrics",
            "reference",
            "tasks",
        },
    )
    primary_expected = {
        "candidate": "pdb_selector_k1",
        "comparison": PRIMARY_COMPARISON,
        "domains": P5_DOMAINS,
        "estimand": P5_PRIMARY_ESTIMAND,
        "reference": "pdb_cegar_b100k",
        "tasks": P5_TASKS,
    }
    for key, expected in primary_expected.items():
        _exact(primary[key], expected, "P5 primary." + key)
    domain_order = _sequence(
        primary["domain_order"], "P5 primary.domain_order", P5_DOMAINS
    )
    if len(set(domain_order)) != P5_DOMAINS or any(
        type(domain) is not str or not domain for domain in domain_order
    ):
        raise RenderError("P5 domain order contains duplicates or invalid labels")
    domain_digest = hashlib.sha256(
        "".join("{}\n".format(domain) for domain in domain_order).encode("utf-8")
    ).hexdigest()
    if domain_digest != EXPECTED_DOMAIN_SEQUENCE_SHA256:
        raise RenderError("P5 domain order identity changed")
    contributions = _sequence(
        primary["domain_contributions"],
        "P5 primary.domain_contributions",
        P5_DOMAINS,
    )
    deltas = []
    candidate_total = reference_total = 0
    for index, (domain, contribution) in enumerate(zip(domain_order, contributions)):
        prefix = "P5 domain contribution[{}]".format(index)
        contribution = _mapping(
            contribution,
            prefix,
            {
                "candidate_solved",
                "difference",
                "domain",
                "reference_solved",
                "task_count",
            },
        )
        _exact(contribution["domain"], domain, prefix + ".domain")
        _exact(contribution["task_count"], 2, prefix + ".task_count")
        candidate_solved = _integer(
            contribution["candidate_solved"], prefix + ".candidate_solved", 0, 2
        )
        reference_solved = _integer(
            contribution["reference_solved"], prefix + ".reference_solved", 0, 2
        )
        delta = Fraction(candidate_solved - reference_solved, 2)
        _validate_fraction(contribution["difference"], prefix + ".difference", delta)
        deltas.append(delta)
        candidate_total += candidate_solved
        reference_total += reference_solved
    if candidate_total != configs["pdb_selector_k1"]["coverage"]["solved"]:
        raise RenderError("P5 primary domain candidate total disagrees with config")
    if reference_total != configs["pdb_cegar_b100k"]["coverage"]["solved"]:
        raise RenderError("P5 primary domain reference total disagrees with config")
    estimate = sum(deltas, Fraction(0, 1)) / P5_DOMAINS
    _validate_fraction(primary["estimate"], "P5 primary.estimate", estimate)

    bootstrap = _mapping(
        primary["bootstrap"],
        "P5 primary.bootstrap",
        {
            "confidence_level",
            "counter_encoding",
            "draws_per_replicate",
            "interval_rule",
            "lower",
            "lower_order_index_zero_based",
            "method",
            "replicates",
            "resampling_unit",
            "seed",
            "sorted_replicate_numerators_sha256",
            "upper",
            "upper_order_index_zero_based",
        },
    )
    bootstrap_expected = {
        "confidence_level": 0.95,
        "counter_encoding": (
            "sha256(utf8(seed)||nul||utf8(comparison-name)||nul||"
            "uint64-be(46*replicate+draw));first-uint64-be-mod-46/v1"
        ),
        "draws_per_replicate": 46,
        "interval_rule": (
            "sorted-replicates[floor(.025*(R-1)),ceil(.975*(R-1))];"
            "zero-based-no-interpolation/v1"
        ),
        "lower_order_index_zero_based": 2499,
        "method": "sha256-counter-domain-resampling/v1",
        "replicates": 100000,
        "resampling_unit": "domain",
        "seed": "symbolic-search-heuristics/arrhenius-selector-heldout-bootstrap/v1",
        "sorted_replicate_numerators_sha256": (
            "a7896019b8120ac3b5d2cf666d5bf748dee691094a44617593d3bba5b14fe485"
        ),
        "upper_order_index_zero_based": 97500,
    }
    for key, expected in bootstrap_expected.items():
        _exact(bootstrap[key], expected, "P5 bootstrap." + key)
    _validate_fraction(
        bootstrap["lower"], "P5 bootstrap.lower", Fraction(-1, 46)
    )
    _validate_fraction(
        bootstrap["upper"], "P5 bootstrap.upper", Fraction(1, 23)
    )

    primary_comparison = _validate_p5_comparison(
        primary["paired_descriptive_metrics"],
        COMPARISONS[0],
        configs,
        "P5 primary paired comparison",
    )
    comparison_entries = _sequence(
        secondary["comparisons"],
        "P5 secondary.comparisons",
        len(COMPARISONS) - 1,
    )
    supplied_comparisons = {}
    expected_secondary_names = {item[0] for item in COMPARISONS[1:]}
    for index, entry in enumerate(comparison_entries):
        if type(entry) is not dict or type(entry.get("name")) is not str:
            raise RenderError("P5 comparison {} lacks a name".format(index))
        name = entry["name"]
        if name in supplied_comparisons or name not in expected_secondary_names:
            raise RenderError(
                "P5 comparisons contain an unexpected or duplicate name"
            )
        supplied_comparisons[name] = entry
    if set(supplied_comparisons) != expected_secondary_names:
        raise RenderError("P5 comparison names are missing or changed")
    comparisons = {COMPARISONS[0][0]: primary_comparison}
    for declaration in COMPARISONS[1:]:
        comparisons[declaration[0]] = _validate_p5_comparison(
            supplied_comparisons[declaration[0]],
            declaration,
            configs,
            "P5 comparison[{}]".format(declaration[0]),
        )
    return {"configs": configs, "comparisons": comparisons}


def _p5_paper_input(value, analysis_sha256):
    indexes = _validate_p5_analysis(value, analysis_sha256)
    configs = []
    for expected in CONFIGS:
        row = indexes["configs"][expected["label"]]
        configs.append(
            {
                "label": expected["label"],
                "paper_label": expected["paper_label"],
                "macro_suffix": expected["suffix"],
                "solved": row["coverage"]["solved"],
                "tasks": row["coverage"]["tasks"],
                "micro_par2_seconds": row["micro_par2_seconds"],
            }
        )
    return {
        "schema": P5_PAPER_INPUT_SCHEMA,
        "analysis_schema": value["schema"],
        "analysis_sha256": analysis_sha256,
        "properties_canonical_sha256": value["execution"][
            "properties_canonical_sha256"
        ],
        "protocol": value["execution"]["protocol"],
        "protocol_revision": value["execution"]["protocol_revision"],
        "task_count": P5_TASKS,
        "domain_count": P5_DOMAINS,
        "config_count": P5_CONFIG_COUNT,
        "cell_count": P5_CELLS,
        "configs": configs,
    }


def _resolve_p5_paper_input(p5_analysis=None, p5_analysis_sha256=None):
    """Return the one pinned P5 paper input; overrides cannot change identity."""
    if p5_analysis is None and p5_analysis_sha256 is None:
        p5_analysis, p5_analysis_sha256 = load_p5_analysis()
    elif p5_analysis is None or p5_analysis_sha256 is None:
        raise RenderError(
            "P5 analysis value and pinned SHA-256 must be supplied together"
        )
    if p5_analysis_sha256 != EXPECTED_P5_ANALYSIS_SHA256:
        raise RenderError("P5 analysis artifact does not match its pinned digest")
    return _p5_paper_input(p5_analysis, p5_analysis_sha256)


def _validate_comparison(value, declaration, configs):
    name, candidate_label, reference_label, roles = declaration
    prefix = "comparison[{}]".format(name)
    keys = {
        "name",
        "candidate",
        "reference",
        "roles",
        "coverage",
        "micro_par2_seconds",
        "jointly_solved_runtime",
        "paired_complete_image_time_seconds",
        "paired_observed_cofactor_width",
        "paired_solved_effort",
        "paired_observed_construction_time_seconds",
    }
    value = _mapping(value, prefix, keys)
    expected = {
        "name": name,
        "candidate": candidate_label,
        "reference": reference_label,
        "roles": roles,
    }
    for key, expected_value in expected.items():
        _exact(value[key], expected_value, prefix + "." + key)
    candidate = configs[candidate_label]
    reference = configs[reference_label]
    coverage = _mapping(
        value["coverage"],
        prefix + ".coverage",
        {
            "candidate_minus_reference_tasks",
            "candidate_minus_reference_rate",
            "discordant_candidate_wins",
            "discordant_candidate_losses",
            "both_solved",
            "both_unsolved",
        },
    )
    wins = _integer(coverage["discordant_candidate_wins"], prefix + ".wins", 0)
    losses = _integer(coverage["discordant_candidate_losses"], prefix + ".losses", 0)
    both = _integer(coverage["both_solved"], prefix + ".both_solved", 0)
    neither = _integer(coverage["both_unsolved"], prefix + ".both_unsolved", 0)
    if wins + losses + both + neither != TASKS:
        raise RenderError("{} coverage partition changed".format(prefix))
    if both + wins != candidate["coverage"]["solved"] or both + losses != reference["coverage"]["solved"]:
        raise RenderError("{} coverage disagrees with configuration summaries".format(prefix))
    delta = wins - losses
    _exact(coverage["candidate_minus_reference_tasks"], delta, prefix + ".coverage delta")
    _close(coverage["candidate_minus_reference_rate"], delta / TASKS, prefix + ".coverage rate")

    par2 = _mapping(
        value["micro_par2_seconds"],
        prefix + ".micro_par2_seconds",
        {"candidate", "reference", "candidate_minus_reference"},
    )
    _close(par2["candidate"], candidate["micro_par2_seconds"], prefix + ".candidate PAR2")
    _close(par2["reference"], reference["micro_par2_seconds"], prefix + ".reference PAR2")
    _close(par2["candidate_minus_reference"], float(par2["candidate"]) - float(par2["reference"]), prefix + ".PAR2 delta")

    runtime = _mapping(
        value["jointly_solved_runtime"],
        prefix + ".jointly_solved_runtime",
        {"pairs", "candidate_over_reference_geometric_mean", "ratio_summary"},
    )
    _exact(runtime["pairs"], both, prefix + ".jointly_solved_runtime.pairs")
    _validate_summary(runtime["ratio_summary"], prefix + ".jointly_solved_runtime.ratio_summary", both, True)
    if both:
        geomean = _number(
            runtime["candidate_over_reference_geometric_mean"],
            prefix + ".runtime geomean",
            0,
        )
        if geomean <= 0 or float(runtime["ratio_summary"]["minimum"]) <= 0:
            raise RenderError("{} runtime ratios must be strictly positive".format(prefix))
    elif runtime["candidate_over_reference_geometric_mean"] is not None:
        raise RenderError("{} empty runtime intersection requires null geomean".format(prefix))

    candidate_complete = candidate["image"]["complete_certified"]["certified_cells"]
    reference_complete = reference["image"]["complete_certified"]["certified_cells"]
    _validate_pair_metric(
        value["paired_complete_image_time_seconds"],
        prefix + ".paired_complete_image_time_seconds",
        min(candidate_complete, reference_complete),
    )
    candidate_width = candidate["exact_cofactor_width"]["certification"]["certified_cells"]
    reference_width = reference["exact_cofactor_width"]["certification"]["certified_cells"]
    _validate_pair_metric(
        value["paired_observed_cofactor_width"],
        prefix + ".paired_observed_cofactor_width",
        min(candidate_width, reference_width),
        integer_totals=True,
    )
    effort_pairs = _validate_pair_metric(
        value["paired_solved_effort"],
        prefix + ".paired_solved_effort",
        both,
        integer_totals=True,
    )
    if effort_pairs != both:
        raise RenderError("{} solved-effort intersection is incomplete".format(prefix))
    candidate_construction = candidate["construction"]["certification"]["certified_cells"]
    reference_construction = reference["construction"]["certification"]["certified_cells"]
    _validate_pair_metric(
        value["paired_observed_construction_time_seconds"],
        prefix + ".paired_observed_construction_time_seconds",
        min(candidate_construction, reference_construction),
    )


def _validate_macro(value, label, tasks, expected_domain_counts=None):
    keys = {
        "comparison",
        "candidate",
        "reference",
        "estimand",
        "domains",
        "tasks",
        "estimate",
        "confidence_interval",
        "p_value",
        "micro_coverage",
        "per_domain",
    }
    value = _mapping(value, label, keys)
    expected = {
        "comparison": PRIMARY_COMPARISON,
        "candidate": "pdb_selector_k1",
        "reference": "pdb_cegar_b100k",
        "estimand": PRIMARY_ESTIMAND,
        "domains": DOMAINS,
        "tasks": tasks,
        "confidence_interval": None,
        "p_value": None,
    }
    for key, expected_value in expected.items():
        _exact(value[key], expected_value, label + "." + key)
    entries = _sequence(value["per_domain"], label + ".per_domain", DOMAINS)
    counts = []
    deltas = []
    candidate_total = 0
    reference_total = 0
    seen = set()
    for index, entry in enumerate(entries):
        prefix = "{}.per_domain[{}]".format(label, index)
        entry = _mapping(
            entry,
            prefix,
            {
                "domain",
                "tasks",
                "candidate_solved",
                "reference_solved",
                "candidate_minus_reference_rate",
            },
        )
        domain = entry["domain"]
        if type(domain) is not str or not domain or domain in seen:
            raise RenderError("{} has a duplicate or invalid domain".format(prefix))
        seen.add(domain)
        count = _integer(entry["tasks"], prefix + ".tasks", 1)
        candidate = _integer(entry["candidate_solved"], prefix + ".candidate_solved", 0, count)
        reference = _integer(entry["reference_solved"], prefix + ".reference_solved", 0, count)
        expected_delta = Fraction(candidate - reference, count)
        delta = _validate_fraction(entry["candidate_minus_reference_rate"], prefix + ".candidate_minus_reference_rate", expected_delta)
        counts.append((domain, count))
        deltas.append(delta)
        candidate_total += candidate
        reference_total += reference
    counts.sort(key=lambda item: item[0])
    if sum(count for _, count in counts) != tasks:
        raise RenderError("{} per-domain task total changed".format(label))
    if expected_domain_counts is not None and counts != expected_domain_counts:
        raise RenderError("{} per-domain identities changed".format(label))
    expected_estimate = sum(deltas, Fraction(0, 1)) / DOMAINS
    _validate_fraction(value["estimate"], label + ".estimate", expected_estimate)
    micro = _mapping(
        value["micro_coverage"],
        label + ".micro_coverage",
        {
            "candidate_solved",
            "reference_solved",
            "candidate_minus_reference_tasks",
            "candidate_minus_reference_rate",
        },
    )
    _exact(micro["candidate_solved"], candidate_total, label + ".candidate solved")
    _exact(micro["reference_solved"], reference_total, label + ".reference solved")
    delta = candidate_total - reference_total
    _exact(micro["candidate_minus_reference_tasks"], delta, label + ".micro delta")
    _close(micro["candidate_minus_reference_rate"], delta / tasks, label + ".micro rate")
    return counts


def _validate_terminal_outcome_slice(
    value,
    label,
    expected_cells,
    expected_solved,
    expected_presearch,
):
    value = _mapping(value, label, {"cell_records", "outcomes"})
    _exact(value["cell_records"], expected_cells, label + ".cell_records")
    entries = _sequence(
        value["outcomes"],
        label + ".outcomes",
        len(TERMINAL_OUTCOME_SPECS),
    )
    counts = {}
    row_keys = {
        "planner_exit_code",
        "error",
        "presearch",
        "search_raw_exit_code",
        "search_effective_exit_code",
        "cell_records",
    }
    for index, (entry, spec) in enumerate(
        zip(entries, TERMINAL_OUTCOME_SPECS)
    ):
        prefix = "{}.outcomes[{}]".format(label, index)
        entry = _mapping(entry, prefix, row_keys)
        code, error, presearch, raw_exit, effective_exit = spec
        _exact(entry["planner_exit_code"], code, prefix + ".planner_exit_code")
        _exact(entry["error"], error, prefix + ".error")
        _exact(entry["presearch"], presearch, prefix + ".presearch")
        _exact(
            entry["search_raw_exit_code"],
            raw_exit,
            prefix + ".search_raw_exit_code",
        )
        _exact(
            entry["search_effective_exit_code"],
            effective_exit,
            prefix + ".search_effective_exit_code",
        )
        counts[code] = _integer(
            entry["cell_records"],
            prefix + ".cell_records",
            0,
            expected_cells,
        )
    if sum(counts.values()) != expected_cells:
        raise RenderError("{} terminal outcome counts do not sum".format(label))
    if sum(counts[code] for code in (0, 1, 2, 3)) != expected_solved:
        raise RenderError(
            "{} terminal solved counts disagree with coverage".format(label)
        )
    if sum(counts[code] for code in (10, 20, 21)) != expected_presearch:
        raise RenderError(
            "{} pre-search outcome counts disagree with image summary".format(
                label
            )
        )
    return counts


def _validate_terminal_outcome_census(value, configs):
    value = _mapping(
        value,
        "terminal_outcome_census",
        {"protocol", "unit", "global", "per_config"},
    )
    _exact(
        value["protocol"],
        TERMINAL_OUTCOME_CENSUS_PROTOCOL,
        "terminal_outcome_census.protocol",
    )
    _exact(
        value["unit"],
        TERMINAL_OUTCOME_CENSUS_UNIT,
        "terminal_outcome_census.unit",
    )

    global_counts = _validate_terminal_outcome_slice(
        value["global"],
        "terminal_outcome_census.global",
        CELLS,
        sum(configs[label]["coverage"]["solved"] for label in CONFIG_LABELS),
        sum(
            configs[label]["image"]["presearch_empty_cells"]
            for label in CONFIG_LABELS
        ),
    )
    entries = _sequence(
        value["per_config"],
        "terminal_outcome_census.per_config",
        CONFIG_COUNT,
    )
    config_counts = {}
    for index, (entry, expected_label) in enumerate(zip(entries, CONFIG_LABELS)):
        prefix = "terminal_outcome_census.per_config[{}]".format(index)
        entry = _mapping(
            entry, prefix, {"label", "cell_records", "outcomes"}
        )
        _exact(entry["label"], expected_label, prefix + ".label")
        payload = {
            "cell_records": entry["cell_records"],
            "outcomes": entry["outcomes"],
        }
        config_counts[expected_label] = _validate_terminal_outcome_slice(
            payload,
            prefix,
            TASKS,
            configs[expected_label]["coverage"]["solved"],
            configs[expected_label]["image"]["presearch_empty_cells"],
        )
    for code in TERMINAL_OUTCOME_CODES:
        marginal = sum(
            config_counts[label][code] for label in CONFIG_LABELS
        )
        if global_counts[code] != marginal:
            raise RenderError(
                "terminal outcome {} global/per-configuration counts disagree".format(
                    code
                )
            )
    return value


def _validate_completion_slice(value, label, cells):
    keys = {
        "all_cells_marker_present_and_valid",
        "cells",
        "cells_completed_after_nonzero_slurm_restart",
        "slurm_restart_count",
        "cells_with_partial_archives",
        "partial_archive_count",
        "total_partial_archives",
        "descriptive_cell_attempt_generation_count",
        "total_descriptive_cell_attempt_generations",
    }
    value = _mapping(value, label, keys)
    _exact(value["all_cells_marker_present_and_valid"], True, label + ".marker validity")
    _exact(value["cells"], cells, label + ".cells")
    restarted = _integer(value["cells_completed_after_nonzero_slurm_restart"], label + ".restarted cells", 0, cells)
    restart_summary = _validate_count_summary(
        value["slurm_restart_count"], label + ".slurm_restart_count", cells
    )
    archived_cells = _integer(value["cells_with_partial_archives"], label + ".archive cells", 0, cells)
    archive_summary = _validate_count_summary(
        value["partial_archive_count"], label + ".partial_archive_count", cells
    )
    attempts_summary = _validate_count_summary(
        value["descriptive_cell_attempt_generation_count"],
        label + ".attempt generations",
        cells,
    )
    archive_total = _integer(value["total_partial_archives"], label + ".total_partial_archives", 0)
    attempts_total = _integer(value["total_descriptive_cell_attempt_generations"], label + ".total attempts", cells)
    _close(archive_summary["total"] or 0, archive_total, label + ".archive total")
    _close(attempts_summary["total"] or 0, attempts_total, label + ".attempt total")
    if attempts_total != cells + archive_total:
        raise RenderError("{} attempt/archive arithmetic changed".format(label))
    restart_total = restart_summary["total"] or 0
    if (restarted == 0) != (restart_total == 0):
        raise RenderError("{} restarted-cell count disagrees with restart total".format(label))
    if restart_total < restarted:
        raise RenderError("{} restart total is smaller than restarted cells".format(label))
    if (archived_cells == 0) != (archive_total == 0):
        raise RenderError("{} archive-cell count disagrees with archive total".format(label))
    if archive_total < archived_cells:
        raise RenderError("{} archive total is smaller than archive cells".format(label))
    return {
        "restarted": restarted,
        "restart_total": restart_total,
        "archived_cells": archived_cells,
        "archive_total": archive_total,
        "attempts_total": attempts_total,
    }


def _validate_completion(value):
    value = _mapping(
        value,
        "completion_and_recovery",
        {"protocol", "attempt_count_semantics", "global", "per_config"},
    )
    _exact(value["protocol"], COMPLETION_PROTOCOL, "completion protocol")
    _exact(value["attempt_count_semantics"], ATTEMPT_SEMANTICS, "attempt semantics")
    global_values = _validate_completion_slice(value["global"], "completion.global", CELLS)
    entries = _sequence(value["per_config"], "completion.per_config", CONFIG_COUNT)
    indexed = {}
    for index, entry in enumerate(entries):
        if type(entry) is not dict or type(entry.get("label")) is not str:
            raise RenderError("completion.per_config[{}] lacks a label".format(index))
        label = entry["label"]
        if label in indexed or label not in CONFIG_BY_LABEL:
            raise RenderError("completion has an unexpected or duplicate label")
        payload = dict(entry)
        payload.pop("label")
        indexed[label] = _validate_completion_slice(
            payload, "completion[{}]".format(label), TASKS
        )
    if set(indexed) != set(CONFIG_LABELS):
        raise RenderError("completion configuration labels changed")
    for field in ("restarted", "restart_total", "archived_cells", "archive_total", "attempts_total"):
        total = sum(indexed[label][field] for label in CONFIG_LABELS)
        if not math.isclose(float(total), float(global_values[field]), rel_tol=0, abs_tol=1e-12):
            raise RenderError("completion global/per-configuration {} totals disagree".format(field))


def _validate_analysis_with_test_pins(value, analysis_sha256, *, launch_pins):
    """Validate all paper-visible identities, denominators, and arithmetic."""
    launch_pins = _validate_launch_pins(
        launch_pins, "private synthetic-test launch pins"
    )
    _require_sha256(analysis_sha256, "analysis artifact digest")
    in_memory_digest = sha256_bytes(
        canonical_json(value).encode("ascii") + b"\n"
    )
    if in_memory_digest != analysis_sha256:
        raise RenderError(
            "in-memory canonical analysis does not match the claimed artifact digest"
        )
    value = _mapping(value, "analysis", TOP_KEYS)
    _exact(value["schema"], ANALYSIS_SCHEMA, "analysis.schema")
    _exact(value["analysis_protocol"], ANALYSIS_PROTOCOL, "analysis.analysis_protocol")

    selection = _mapping(
        value["selection_artifact"],
        "selection_artifact",
        {
            "schema",
            "raw_sha256",
            "global_winner_alias",
            "selector_family_winner",
            "matched_same_k_unbatched",
            "pilot_planner_revision",
            "pilot_planner_binary_sha256",
            "pilot_planner_preprocess_sha256",
        },
    )
    selection_expected = {
        "schema": SELECTION_SCHEMA,
        "raw_sha256": EXPECTED_SELECTION_ARTIFACT_SHA256,
        "global_winner_alias": "ms_exact",
        "selector_family_winner": "pdb_selector_k1",
        "matched_same_k_unbatched": None,
        "pilot_planner_revision": EXPECTED_PILOT_REVISION,
        "pilot_planner_binary_sha256": EXPECTED_PILOT_BINARY_SHA256,
        "pilot_planner_preprocess_sha256": EXPECTED_PILOT_PREPROCESS_SHA256,
    }
    for key, expected in selection_expected.items():
        _exact(selection[key], expected, "selection_artifact." + key)

    _validate_execution(value["execution"], launch_pins)
    decision = _mapping(
        value["decision_policy"],
        "decision_policy",
        {
            "analysis_role",
            "rerank_on_full_population",
            "configuration_order_source",
            "comparisons_source",
            "population_inference",
            "confidence_intervals",
            "p_values",
        },
    )
    expected_decision = {
        "analysis_role": "descriptive-fixed-population-census",
        "rerank_on_full_population": False,
        "configuration_order_source": "selection-artifact-v3",
        "comparisons_source": "selection-artifact-v3",
        "population_inference": "none-fixed-population-census",
        "confidence_intervals": None,
        "p_values": None,
    }
    _exact(decision, expected_decision, "decision_policy")

    primary = _mapping(
        value["primary"],
        "primary",
        {
            "status",
            "selector_vs_cegar_equally_weighted_domain_coverage",
            "configs",
            "carried_comparisons",
        },
    )
    _exact(primary["status"], "descriptive-1377-task-census", "primary.status")
    config_entries = _sequence(primary["configs"], "primary.configs", CONFIG_COUNT)
    config_by_label = {}
    for index, entry in enumerate(config_entries):
        if type(entry) is not dict or type(entry.get("label")) is not str:
            raise RenderError("primary.configs[{}] lacks a label".format(index))
        label = entry["label"]
        if label in config_by_label or label not in CONFIG_BY_LABEL:
            raise RenderError("primary configs contain an unexpected or duplicate label")
        config_by_label[label] = entry
    if set(config_by_label) != set(CONFIG_LABELS):
        raise RenderError("primary configuration labels changed")
    configs = {}
    expected_domain_counts = None
    for expected in CONFIGS:
        entry = config_by_label[expected["label"]]
        counts = _validate_config(entry, expected)
        if expected_domain_counts is None:
            expected_domain_counts = counts
            sequence_digest = hashlib.sha256(
                "".join("{}\n".format(domain) for domain, _ in counts).encode("utf-8")
            ).hexdigest()
            if sequence_digest != EXPECTED_DOMAIN_SEQUENCE_SHA256:
                raise RenderError("configuration domain sequence digest changed")
            count_records = [
                {"domain": domain, "task_count": count} for domain, count in counts
            ]
            if sha256_json(count_records) != EXPECTED_DOMAIN_TASK_COUNTS_SHA256:
                raise RenderError("configuration domain task-count digest changed")
        elif counts != expected_domain_counts:
            raise RenderError("configuration per-domain denominators disagree")
        configs[expected["label"]] = entry

    terminal_outcomes = _validate_terminal_outcome_census(
        value["terminal_outcome_census"], configs
    )

    macro = primary["selector_vs_cegar_equally_weighted_domain_coverage"]
    _validate_macro(macro, "primary.selector_vs_cegar_macro", TASKS, expected_domain_counts)
    if macro["micro_coverage"]["candidate_solved"] != configs["pdb_selector_k1"]["coverage"]["solved"] or macro["micro_coverage"]["reference_solved"] != configs["pdb_cegar_b100k"]["coverage"]["solved"]:
        raise RenderError("primary macro micro coverage disagrees with configurations")
    macro_domains = {entry["domain"]: entry for entry in macro["per_domain"]}
    selector_domains = {
        entry["domain"]: entry
        for entry in configs["pdb_selector_k1"]["per_domain_coverage"]
    }
    cegar_domains = {
        entry["domain"]: entry
        for entry in configs["pdb_cegar_b100k"]["per_domain_coverage"]
    }
    for domain, count in expected_domain_counts:
        macro_entry = macro_domains[domain]
        if (
            macro_entry["tasks"] != count
            or macro_entry["candidate_solved"] != selector_domains[domain]["solved"]
            or macro_entry["reference_solved"] != cegar_domains[domain]["solved"]
        ):
            raise RenderError(
                "primary macro per-domain coverage disagrees on {}".format(domain)
            )

    comparison_entries = _sequence(
        primary["carried_comparisons"], "primary.carried_comparisons", len(COMPARISONS)
    )
    input_comparisons = {}
    for index, entry in enumerate(comparison_entries):
        if type(entry) is not dict or type(entry.get("name")) is not str:
            raise RenderError("carried comparison {} lacks a name".format(index))
        name = entry["name"]
        if name in input_comparisons or name not in {item[0] for item in COMPARISONS}:
            raise RenderError("carried comparisons contain an unexpected or duplicate name")
        input_comparisons[name] = entry
    if set(input_comparisons) != {item[0] for item in COMPARISONS}:
        raise RenderError("carried comparison names changed")
    comparison_by_name = {}
    for declaration in COMPARISONS:
        entry = input_comparisons[declaration[0]]
        _validate_comparison(entry, declaration, configs)
        comparison_by_name[declaration[0]] = entry

    sensitivity = value["sole_predeclared_sensitivity"]
    sensitivity = _mapping(
        sensitivity,
        "sole_predeclared_sensitivity",
        {
            "name",
            "task_subset",
            "identity",
            "called_unseen",
            "includes_all_92_heldout_tasks",
            "comparison",
            "candidate",
            "reference",
            "estimand",
            "domains",
            "tasks",
            "estimate",
            "confidence_interval",
            "p_value",
            "micro_coverage",
            "per_domain",
        },
    )
    extra_expected = {
        "name": "selector-vs-pdb-cegar-screen-excluded",
        "task_subset": "full-supported-population-minus-50-screen-tasks",
        "called_unseen": False,
        "includes_all_92_heldout_tasks": True,
    }
    for key, expected in extra_expected.items():
        _exact(sensitivity[key], expected, "sole_predeclared_sensitivity." + key)
    identity = _mapping(
        sensitivity["identity"],
        "sole_predeclared_sensitivity.identity",
        {"task_count", "domain_count", "task_manifest_sha256", "task_sources_sha256", "heldout_inclusion"},
    )
    identity_expected = {
        "task_count": SENSITIVITY_TASKS,
        "domain_count": DOMAINS,
        "task_manifest_sha256": EXPECTED_SENSITIVITY_TASK_SHA256,
        "task_sources_sha256": EXPECTED_SENSITIVITY_SOURCES_SHA256,
    }
    for key, expected in identity_expected.items():
        _exact(identity[key], expected, "sensitivity.identity." + key)
    heldout = _mapping(
        identity["heldout_inclusion"],
        "sensitivity.identity.heldout_inclusion",
        {"task_count", "domain_count", "task_manifest_sha256", "task_sources_sha256", "all_tasks_in_screen_excluded_sensitivity"},
    )
    heldout_expected = {
        "task_count": 92,
        "domain_count": DOMAINS,
        "task_manifest_sha256": EXPECTED_HELDOUT_TASK_SHA256,
        "task_sources_sha256": EXPECTED_HELDOUT_SOURCES_SHA256,
        "all_tasks_in_screen_excluded_sensitivity": True,
    }
    _exact(heldout, heldout_expected, "sensitivity held-out inclusion")
    sensitivity_macro = dict(sensitivity)
    for key in ("name", "task_subset", "identity", "called_unseen", "includes_all_92_heldout_tasks"):
        sensitivity_macro.pop(key)
    sensitivity_counts = _validate_macro(
        sensitivity_macro,
        "sole_predeclared_sensitivity",
        SENSITIVITY_TASKS,
    )
    if [domain for domain, _ in sensitivity_counts] != [domain for domain, _ in expected_domain_counts]:
        raise RenderError("sensitivity domain sequence changed")
    sensitivity_domains = {
        entry["domain"]: entry for entry in sensitivity["per_domain"]
    }
    removed_counts = []
    for domain, full_count in expected_domain_counts:
        full_entry = macro_domains[domain]
        sensitivity_entry = sensitivity_domains[domain]
        removed = full_count - sensitivity_entry["tasks"]
        if removed not in (0, 2):
            raise RenderError(
                "screen complement removes neither zero nor two tasks in {}".format(
                    domain
                )
            )
        removed_counts.append(removed)
        for key in ("candidate_solved", "reference_solved"):
            removed_solved = full_entry[key] - sensitivity_entry[key]
            if removed_solved < 0 or removed_solved > removed:
                raise RenderError(
                    "sensitivity/full solved arithmetic changed for {} in {}".format(
                        key, domain
                    )
                )
    if removed_counts.count(2) != 25 or removed_counts.count(0) != 21:
        raise RenderError("screen complement domain-count distribution changed")

    _validate_completion(value["completion_and_recovery"])
    return {
        "configs": configs,
        "comparisons": comparison_by_name,
        "domain_counts": expected_domain_counts,
        "terminal_outcome_census": terminal_outcomes,
    }


def validate_analysis(
    value,
    analysis_sha256,
    *,
    structure=None,
    structure_sha256=None,
):
    """Public joint validator; both reviewed P6 artifacts are mandatory."""
    pins = reviewed_production_pins()
    if analysis_sha256 != pins["analysis_sha256"]:
        raise RenderError("analysis artifact does not match its reviewed digest")
    indexes = _validate_analysis_with_test_pins(
        value, analysis_sha256, launch_pins=pins["launch"]
    )
    if structure is None or structure_sha256 is None:
        raise RenderError("structure value and reviewed SHA-256 are required together")
    if structure_sha256 != pins["structure_sha256"]:
        raise RenderError("structure artifact does not match its reviewed digest")
    _validate_structure_with_test_pins(
        structure,
        structure_sha256,
        analysis=value,
        analysis_sha256=analysis_sha256,
        launch_pins=pins["launch"],
    )
    return indexes


def _validate_structure_with_test_pins(
    value,
    structure_sha256,
    *,
    analysis,
    analysis_sha256,
    launch_pins,
):
    """Validate and cross-bind the separately frozen secondary diagnostic."""
    analysis_indexes = _validate_analysis_with_test_pins(
        analysis, analysis_sha256, launch_pins=launch_pins
    )
    _require_sha256(structure_sha256, "structure artifact digest")
    in_memory_digest = sha256_bytes(canonical_json(value).encode("ascii") + b"\n")
    if in_memory_digest != structure_sha256:
        raise RenderError(
            "in-memory canonical structure does not match the claimed artifact digest"
        )
    value = _mapping(value, "structure", STRUCTURE_TOP_KEYS)
    _exact(value["schema"], STRUCTURE_SCHEMA, "structure.schema")
    _exact(value["analysis_protocol"], STRUCTURE_PROTOCOL, "structure.analysis_protocol")
    _exact(value["decision_label"], STRUCTURE_DECISION_LABEL, "structure.decision_label")
    _exact(
        value["specification_boundary"],
        STRUCTURE_SPECIFICATION_BOUNDARY,
        "structure.specification_boundary",
    )
    identity = _mapping(value["input_identity"], "structure.input_identity", STRUCTURE_INPUT_KEYS)
    identity_expected = {
        "selection_artifact_sha256": EXPECTED_SELECTION_ARTIFACT_SHA256,
        "full_protocol_revision": launch_pins["protocol_revision"],
        "properties_canonical_sha256": analysis["execution"]["properties_canonical_sha256"],
        "task_count": TASKS,
        "config_count": CONFIG_COUNT,
        "cell_count": CELLS,
        "config_order": list(CONFIG_LABELS),
    }
    _exact(identity, identity_expected, "structure.input_identity")
    interpretation = _mapping(
        value["interpretation"],
        "structure.interpretation",
        set(STRUCTURE_INTERPRETATION),
    )
    _exact(interpretation, STRUCTURE_INTERPRETATION, "structure.interpretation")

    entries = _sequence(value["configs"], "structure.configs", CONFIG_COUNT)
    by_label = {}
    for index, entry in enumerate(entries):
        if type(entry) is not dict or type(entry.get("label")) is not str:
            raise RenderError("structure.configs[{}] lacks a label".format(index))
        label = entry["label"]
        if label not in CONFIG_BY_LABEL or label in by_label:
            raise RenderError("structure configs contain an unexpected or duplicate label")
        by_label[label] = entry
    if set(by_label) != set(CONFIG_LABELS):
        raise RenderError("structure configuration labels changed")
    terminal_by_label = {
        entry["label"]: {
            row["planner_exit_code"]: row["cell_records"]
            for row in entry["outcomes"]
        }
        for entry in analysis_indexes["terminal_outcome_census"]["per_config"]
    }
    configs = [
        _validate_structure_config(
            by_label[expected["label"]],
            expected,
            analysis_indexes["configs"][expected["label"]],
            terminal_by_label[expected["label"]],
        )
        for expected in CONFIGS
    ]
    candidate_pool = _validate_structure_candidate_pool(
        value["selector_candidate_pool"], analysis_indexes["configs"]
    )
    selector_direct = next(
        item for item in configs if item["label"] == "pdb_selector_k1"
    )["direct_W_A_V_T_U"]
    if (
        selector_direct["unobserved_reason_counts"][
            "selector_width_only_resource_prefix"
        ]
        > candidate_pool["certified_trace_cells"]
    ):
        raise RenderError(
            "selector width-only prefixes exceed certified selector traces"
        )
    return {"configs": configs, "selector_candidate_pool": candidate_pool}


def validate_structure(
    value,
    structure_sha256,
    *,
    analysis,
    analysis_sha256,
):
    """Public validator requiring the same atomically reviewed P6 pin set."""
    pins = reviewed_production_pins()
    if analysis_sha256 != pins["analysis_sha256"]:
        raise RenderError("analysis artifact does not match its reviewed digest")
    if structure_sha256 != pins["structure_sha256"]:
        raise RenderError("structure artifact does not match its reviewed digest")
    return _validate_structure_with_test_pins(
        value,
        structure_sha256,
        analysis=analysis,
        analysis_sha256=analysis_sha256,
        launch_pins=pins["launch"],
    )


def _paper_data_with_test_pins(
    value,
    analysis_sha256,
    *,
    launch_pins,
    structure,
    structure_sha256,
    p5_analysis=None,
    p5_analysis_sha256=None,
):
    """Create the canonical, label-indexed view of both validated stages."""
    indexes = _validate_analysis_with_test_pins(
        value, analysis_sha256, launch_pins=launch_pins
    )
    structure_indexes = _validate_structure_with_test_pins(
        structure,
        structure_sha256,
        analysis=value,
        analysis_sha256=analysis_sha256,
        launch_pins=launch_pins,
    )
    p5_heldout = _resolve_p5_paper_input(
        p5_analysis, p5_analysis_sha256
    )
    configs = []
    for expected in CONFIGS:
        summary = copy.deepcopy(indexes["configs"][expected["label"]])
        summary["paper_label"] = expected["paper_label"]
        summary["macro_suffix"] = expected["suffix"]
        summary["per_domain_coverage"].sort(key=lambda item: item["domain"])
        configs.append(summary)
    comparisons = []
    for declaration in COMPARISONS:
        summary = copy.deepcopy(indexes["comparisons"][declaration[0]])
        summary["candidate_paper_label"] = CONFIG_BY_LABEL[declaration[1]]["paper_label"]
        summary["reference_paper_label"] = CONFIG_BY_LABEL[declaration[2]]["paper_label"]
        comparisons.append(summary)
    primary = copy.deepcopy(
        value["primary"]["selector_vs_cegar_equally_weighted_domain_coverage"]
    )
    primary["per_domain"].sort(key=lambda item: item["domain"])
    sensitivity = copy.deepcopy(value["sole_predeclared_sensitivity"])
    sensitivity["per_domain"].sort(key=lambda item: item["domain"])
    completion = copy.deepcopy(value["completion_and_recovery"])
    completion_index = {item["label"]: item for item in completion["per_config"]}
    completion["per_config"] = [completion_index[label] for label in CONFIG_LABELS]
    terminal_outcomes = copy.deepcopy(indexes["terminal_outcome_census"])
    execution_keys = (
        "protocol",
        "protocol_revision",
        "full_runner_source_sha256",
        "planner_revision",
        "planner_binary_sha256",
        "planner_preprocess_sha256",
        "prospective_start_job_sha256",
        "p5_heldout_protocol_revision",
        "p5_heldout_planner_revision",
        "p5_heldout_planner_binary_sha256",
        "p5_heldout_planner_preprocess_sha256",
        "p5_to_p6_git_lineage_protocol",
        "presearch_sigxcpu_normalization_protocol",
        "presearch_sigxcpu_raw_exit_code",
        "presearch_sigxcpu_effective_exit_code",
        "presearch_sigxcpu_components",
    )
    execution_provenance = {
        key: copy.deepcopy(value["execution"][key]) for key in execution_keys
    }
    return {
        "schema": PAPER_DATA_SCHEMA,
        "analysis_schema": value["schema"],
        "analysis_sha256": analysis_sha256,
        "structure_schema": structure["schema"],
        "structure_sha256": structure_sha256,
        "selection_artifact_sha256": EXPECTED_SELECTION_ARTIFACT_SHA256,
        "properties_canonical_sha256": value["execution"]["properties_canonical_sha256"],
        "task_count": TASKS,
        "domain_count": DOMAINS,
        "cell_count": CELLS,
        "p5_heldout": p5_heldout,
        "execution_provenance": execution_provenance,
        "secondary_structure": {
            "analysis_protocol": structure["analysis_protocol"],
            "decision_label": structure["decision_label"],
            "specification_boundary": structure["specification_boundary"],
            "interpretation": copy.deepcopy(structure["interpretation"]),
            "configs": structure_indexes["configs"],
            "selector_candidate_pool": structure_indexes["selector_candidate_pool"],
        },
        "primary": primary,
        "configs": configs,
        "comparisons": comparisons,
        "sole_predeclared_sensitivity": sensitivity,
        "terminal_outcome_census": terminal_outcomes,
        "completion_and_recovery": completion,
    }


def paper_data(
    value,
    analysis_sha256,
    *,
    structure=None,
    structure_sha256=None,
    p5_analysis=None,
    p5_analysis_sha256=None,
):
    """Public production paper view; identities come only from frozen pins."""
    pins = reviewed_production_pins()
    if analysis_sha256 != pins["analysis_sha256"]:
        raise RenderError("analysis artifact does not match its reviewed digest")
    if structure is None or structure_sha256 is None:
        raise RenderError("structure value and reviewed SHA-256 are required together")
    if structure_sha256 != pins["structure_sha256"]:
        raise RenderError("structure artifact does not match its reviewed digest")
    return _paper_data_with_test_pins(
        value,
        analysis_sha256,
        launch_pins=pins["launch"],
        structure=structure,
        structure_sha256=structure_sha256,
        p5_analysis=p5_analysis,
        p5_analysis_sha256=p5_analysis_sha256,
    )


def _decimal(value, places, *, trim=False):
    if value is None:
        return "--"
    number = Decimal(str(value))
    quantum = Decimal(1).scaleb(-places)
    rendered = format(number.quantize(quantum, rounding=ROUND_HALF_UP), "f")
    if trim and "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered.startswith("-0") and Decimal(rendered) == 0:
        rendered = rendered[1:]
    return rendered


def _fraction_percent(record, places):
    numerator = _integer(record["numerator"], "rendered fraction numerator")
    denominator = _integer(
        record["denominator"], "rendered fraction denominator", 1
    )
    exact_percent = Decimal(numerator) * Decimal(100) / Decimal(denominator)
    return _decimal(exact_percent, places)


def _tex_int(value):
    return format(int(value), ",").replace(",", "{,}")


def _tex_stat(value):
    if value is None:
        return "--"
    if type(value) is int:
        return _tex_int(value)
    numeric = float(value)
    if numeric.is_integer():
        return _tex_int(int(numeric))
    return _decimal(numeric, 3, trim=True)


def _macro(name, value):
    return "\\newcommand{{\\{}}}{{{}}}".format(name, value)


def _config_row(config):
    width = config["exact_cofactor_width"]
    width_n = width["certification"]["certified_cells"]
    if width["certification"]["eligible_cells"] == 0:
        width_text = "--"
    else:
        summary = width["summary"]
        width_text = "${}/{};{}/{}/{}$".format(
            _tex_int(width_n),
            _tex_int(width["certification"]["eligible_cells"]),
            _tex_stat(summary["minimum"]),
            _tex_stat(summary["median"]),
            _tex_stat(summary["maximum"]),
        )
    construction = config["construction"]
    construction_n = construction["certification"]["certified_cells"]
    if construction["certification"]["eligible_cells"] == 0:
        construction_text = "--"
        construction_seconds = "--"
    else:
        construction_text = "${}/{}/{}$".format(
            _tex_int(construction_n),
            _tex_int(construction["certification"]["eligible_cells"]),
            _tex_int(construction["fallbacks"]),
        )
        construction_seconds = _decimal(construction["time_seconds"]["total"], 3)
    return "{} & {} & {} & {} & {} & {} \\\\%".format(
        config["paper_label"],
        _tex_int(config["coverage"]["solved"]),
        _decimal(config["micro_par2_seconds"], 4),
        width_text,
        construction_text,
        construction_seconds,
    )


def _image_row(config):
    image = config["image"]
    amort = image["complete_amortization"]
    return "{} & {} & {} & {} & {} & {} & {} & {} \\\\%".format(
        config["paper_label"],
        "{}/{}".format(
            _tex_int(image["certified_prefix"]["certified_cells"]),
            _tex_int(image["certified_prefix"]["eligible_cells"]),
        ),
        _decimal(image["prefix_image_time_seconds"]["total"], 3),
        "{}/{}".format(
            _tex_int(image["complete_certified"]["certified_cells"]),
            _tex_int(image["complete_certified"]["eligible_cells"]),
        ),
        _decimal(amort["aggregate_image_time_seconds"], 3),
        _tex_stat(amort["image_calls_attempted"]["total"]),
        _tex_int(amort["aggregate_completed_image_calls"]),
        _decimal(amort["seconds_per_completed_image_call"], 6, trim=True),
    )


def _runtime_effort_row(config):
    runtime = config["solved_runtime_seconds"]["summary"]
    effort = config["search_effort_on_solved_cells"]["summary"]
    return "{} & {} & {} & {} & {} & {} & {} & {} & {} & {} & {} & {} & {} \\\\%".format(
        config["paper_label"],
        _tex_int(runtime["observed"]),
        _decimal(runtime["minimum"], 3, trim=True),
        _decimal(runtime["median"], 3, trim=True),
        _decimal(runtime["maximum"], 3, trim=True),
        _decimal(runtime["mean"], 3, trim=True),
        _decimal(runtime["total"], 3),
        _tex_int(effort["observed"]),
        _tex_stat(effort["minimum"]),
        _tex_stat(effort["median"]),
        _tex_stat(effort["maximum"]),
        _decimal(effort["mean"], 3, trim=True),
        _tex_stat(effort["total"]),
    )


def _selector_summary_row(paper_label, summary):
    return "{} & {} & {} & {} & {} & {} & {} \\\\%".format(
        paper_label,
        _tex_int(summary["observed"]),
        _tex_stat(summary["minimum"]),
        _tex_stat(summary["median"]),
        _tex_stat(summary["maximum"]),
        _decimal(summary["mean"], 3, trim=True),
        _tex_stat(summary["total"]),
    )


def _comparison_row(comparison):
    coverage = comparison["coverage"]
    runtime = comparison["jointly_solved_runtime"]
    return "{} / {} & {:+d} & {}/{} & {} & {} & {} \\\\%".format(
        comparison["candidate_paper_label"],
        comparison["reference_paper_label"],
        coverage["candidate_minus_reference_tasks"],
        coverage["discordant_candidate_wins"],
        coverage["discordant_candidate_losses"],
        _decimal(comparison["micro_par2_seconds"]["candidate_minus_reference"], 4),
        _tex_int(runtime["pairs"]),
        _decimal(runtime["candidate_over_reference_geometric_mean"], 3),
    )


def _pair_cell(metric):
    return "${};{}$".format(
        _tex_int(metric["pairs"]),
        _decimal(metric["candidate_over_reference"], 3),
    )


def _paired_metric_row(comparison):
    return "{} / {} & {} & {} & {} & {} \\\\%".format(
        comparison["candidate_paper_label"],
        comparison["reference_paper_label"],
        _pair_cell(comparison["paired_complete_image_time_seconds"]),
        _pair_cell(comparison["paired_observed_cofactor_width"]),
        _pair_cell(comparison["paired_observed_construction_time_seconds"]),
        _pair_cell(comparison["paired_solved_effort"]),
    )


def _completion_row(label, paper_label, value):
    return "{} & {} & {} & {} & {} & {} \\\\%".format(
        paper_label,
        _tex_int(value["cells"]),
        "{}/{}".format(
            _tex_int(value["cells_completed_after_nonzero_slurm_restart"]),
            _tex_stat(value["slurm_restart_count"]["total"]),
        ),
        "{}/{}".format(
            _tex_int(value["cells_with_partial_archives"]),
            _tex_int(value["total_partial_archives"]),
        ),
        _tex_int(value["total_descriptive_cell_attempt_generations"]),
        "yes" if value["all_cells_marker_present_and_valid"] else "no",
    )


def _terminal_outcome_row(value):
    return "{} & {} & {} & {} & {} & {} \\\\%".format(
        value["planner_exit_code"],
        _tex_escape(value["error"]),
        "yes" if value["presearch"] else "no",
        "--"
        if value["search_raw_exit_code"] is None
        else value["search_raw_exit_code"],
        "--"
        if value["search_effective_exit_code"] is None
        else value["search_effective_exit_code"],
        _tex_int(value["cell_records"]),
    )


def _terminal_outcome_per_config_row(paper_label, value):
    counts = {
        row["planner_exit_code"]: row["cell_records"]
        for row in value["outcomes"]
    }
    fields = [paper_label]
    fields.extend(_tex_int(counts[code]) for code in TERMINAL_OUTCOME_CODES)
    return "{} \\\\%".format(" & ".join(fields))


def _combined_stage_row(p5_config, p6_config):
    """Render one descriptive P5/P6 row without constructing a contrast."""
    if (
        p5_config["label"] != p6_config["label"]
        or p5_config["paper_label"] != p6_config["paper_label"]
    ):
        raise RenderError("P5/P6 combined row labels disagree")
    return "{} & ${}/{}$ & {} & ${}/{}$ & {} \\\\%".format(
        p5_config["paper_label"],
        _tex_int(p5_config["solved"]),
        _tex_int(p5_config["tasks"]),
        _decimal(p5_config["micro_par2_seconds"], 4),
        _tex_int(p6_config["coverage"]["solved"]),
        _tex_int(TASKS),
        _decimal(p6_config["micro_par2_seconds"], 4),
    )


def _structure_triplet(summary):
    if summary["observed"] == 0:
        return "--"
    return "{}/{}/{}".format(
        _tex_stat(summary["minimum"]),
        _tex_stat(summary["median"]),
        _tex_stat(summary["maximum"]),
    )


def _structure_ratio_triplet(summary):
    if summary["observed"] == 0:
        return "--"
    return "{}/{}/{}".format(
        _decimal(summary["minimum"], 3, trim=True),
        _decimal(summary["median"], 3, trim=True),
        _decimal(summary["maximum"], 3, trim=True),
    )


def _structure_direct_row(config):
    direct = config["direct_W_A_V_T_U"]
    sources = direct["observation_source_counts"]
    summaries = direct["summaries"]
    return "{} & {}/{} & {}/{} & {} & {} & {} \\\\%".format(
        CONFIG_BY_LABEL[config["label"]]["paper_label"],
        _tex_int(direct["observed_cells"]),
        _tex_int(direct["eligible_cells"]),
        _tex_int(sources["completed_construction"]),
        _tex_int(sources["heuristic_event_only_resource_prefix"]),
        _structure_triplet(summaries["W"]),
        _structure_triplet(summaries["U"]),
        _structure_ratio_triplet(summaries["U_over_W"]),
    )


def _structure_partition_row(config, key, paper_stratum):
    value = config["partition_ratios"][key]
    summaries = value["summaries"]
    return "{} & {} & {}/{} & {} & {} & {} \\\\%".format(
        CONFIG_BY_LABEL[config["label"]]["paper_label"],
        paper_stratum,
        _tex_int(value["logs_with_partition_ratios"]),
        _tex_int(value["eligible_logs"]),
        _tex_int(value["logs_without_partition_ratios"]),
        _structure_ratio_triplet(summaries["partition_ratio_max"]),
        _structure_ratio_triplet(summaries["partition_ratio_geomean"]),
    )


def _structure_correlation_row(config, key, display):
    raw = config["partition_ratios"][
        "raw_complete_logs_not_necessarily_complete_searches"
    ]["cross_task_descriptive_confounded_correlations"][key]
    if raw["coefficient"] is None:
        coefficient = {
            "fewer-than-two-pairs": "-- (fewer than two pairs)",
            "zero-rank-variance": "-- (zero rank variance)",
        }[raw["null_reason"]]
    else:
        coefficient = _decimal(raw["coefficient"], 3, trim=True)
    return "{} & {} & {} & {} \\\\%".format(
        CONFIG_BY_LABEL[config["label"]]["paper_label"],
        display,
        _tex_int(raw["n"]),
        coefficient,
    )


def _structure_candidate_row(pool):
    counts = pool["deduplicated_candidate_counts"]
    sources = pool["represented_source_counts"]
    summaries = pool["materialized_summaries"]
    return "{}/{} & {} & {}/{} & {}/{} & {} & {} & {} \\\\%".format(
        _tex_int(pool["observed_unique_task_pool_hashes"]),
        _tex_int(pool["eligible_tasks"]),
        _tex_int(pool["repeated_certified_trace_cells_deduplicated"]),
        _tex_int(counts["materialized"]),
        _tex_int(counts["total"]),
        _tex_int(sources["materialized"]),
        _tex_int(sources["total"]),
        _structure_triplet(summaries["W"]),
        _structure_triplet(summaries["U"]),
        _structure_ratio_triplet(summaries["U_over_W"]),
    )


def _structure_source_row(row):
    display = dict(STRUCTURE_SOURCE_DISPLAY)[row["source"]]
    return "{} & {} & {} \\\\%".format(
        display,
        _tex_int(row["materialized_task_pools"]),
        _tex_int(row["unmaterialized_task_pools"]),
    )


def _render_tex_with_test_pins(
    value,
    analysis_sha256,
    *,
    launch_pins,
    structure,
    structure_sha256,
    p5_analysis=None,
    p5_analysis_sha256=None,
):
    """Return stable UTF-8 TeX bytes from the two pinned validated stages."""
    data = _paper_data_with_test_pins(
        value,
        analysis_sha256,
        launch_pins=launch_pins,
        structure=structure,
        structure_sha256=structure_sha256,
        p5_analysis=p5_analysis,
        p5_analysis_sha256=p5_analysis_sha256,
    )
    configs = {item["label"]: item for item in data["configs"]}
    p5 = data["p5_heldout"]
    p5_configs = {item["label"]: item for item in p5["configs"]}
    primary = data["primary"]
    sensitivity = data["sole_predeclared_sensitivity"]
    terminal_outcomes = data["terminal_outcome_census"]
    completion = data["completion_and_recovery"]
    execution = data["execution_provenance"]
    secondary_structure = data["secondary_structure"]
    structure_configs = {
        item["label"]: item for item in secondary_structure["configs"]
    }
    candidate_pool = secondary_structure["selector_candidate_pool"]
    paper_data_digest = sha256_json(data)

    lines = [
        "% Generated by experiments/render_arrhenius_selector_full_paper.py.",
        "% Do not edit: regenerate only from the pinned canonical analysis artifact.",
        "% Source analysis SHA-256: {}".format(analysis_sha256),
        "% Source secondary structure SHA-256: {}".format(structure_sha256),
        "% Source properties SHA-256: {}".format(
            data["properties_canonical_sha256"]
        ),
        "% P5 held-out analysis SHA-256: {}".format(p5["analysis_sha256"]),
        "% Combined-stage rows are within-stage descriptive summaries only; "
        "no between-stage causal contrast.",
        "% Extraction schema: {}".format(PAPER_DATA_SCHEMA),
        "% Canonical PaperData SHA-256: {}".format(paper_data_digest),
        _macro("ArrFullAnalysisSha", "\\texttt{{{}}}".format(analysis_sha256)),
        _macro("ArrFullStructureSha", "\\texttt{{{}}}".format(structure_sha256)),
        _macro(
            "ArrFullStructureSchema",
            "\\texttt{{{}}}".format(_tex_escape(data["structure_schema"])),
        ),
        _macro(
            "ArrFullStructureProtocol",
            "\\texttt{{{}}}".format(
                _tex_escape(secondary_structure["analysis_protocol"])
            ),
        ),
        _macro(
            "ArrFullStructureDecisionLabel",
            "\\texttt{{{}}}".format(
                _tex_escape(secondary_structure["decision_label"])
            ),
        ),
        _macro(
            "ArrFullStructureSpecificationBoundary",
            "\\texttt{{{}}}".format(
                _tex_escape(secondary_structure["specification_boundary"])
            ),
        ),
        _macro("ArrFullStructureTimingCaveat", _tex_escape(STRUCTURE_TIMING_CAVEAT)),
        _macro("ArrFullStructureInferenceCaveat", _tex_escape(STRUCTURE_INFERENCE_CAVEAT)),
        _macro("ArrFullStructureResourcePrefixCaveat", _tex_escape(STRUCTURE_RESOURCE_PREFIX_CAVEAT)),
        _macro(
            "ArrFullStructureCandidatePoolsObserved",
            _tex_int(candidate_pool["observed_unique_task_pool_hashes"]),
        ),
        _macro(
            "ArrFullStructureCandidatePoolsEligible",
            _tex_int(candidate_pool["eligible_tasks"]),
        ),
        _macro(
            "ArrFullPropertiesSha",
            "\\texttt{{{}}}".format(data["properties_canonical_sha256"]),
        ),
        _macro("ArrFullPaperDataSha", "\\texttt{{{}}}".format(paper_data_digest)),
        _macro(
            "ArrFullSelectionSha",
            "\\texttt{{{}}}".format(data["selection_artifact_sha256"]),
        ),
        _macro(
            "ArrFullPfiveAnalysisSha",
            "\\texttt{{{}}}".format(p5["analysis_sha256"]),
        ),
        _macro(
            "ArrFullPfivePropertiesSha",
            "\\texttt{{{}}}".format(p5["properties_canonical_sha256"]),
        ),
        _macro(
            "ArrFullPfiveAnalysisSchema",
            "\\texttt{{{}}}".format(_tex_escape(p5["analysis_schema"])),
        ),
        _macro(
            "ArrFullPfiveProtocol",
            "\\texttt{{{}}}".format(_tex_escape(p5["protocol"])),
        ),
        _macro(
            "ArrFullPfiveProtocolRevision",
            "\\texttt{{{}}}".format(p5["protocol_revision"]),
        ),
        _macro(
            "ArrFullAnalysisSchema",
            "\\texttt{{{}}}".format(_tex_escape(data["analysis_schema"])),
        ),
        _macro(
            "ArrFullProtocol",
            "\\texttt{{{}}}".format(_tex_escape(execution["protocol"])),
        ),
        _macro(
            "ArrFullProtocolRevision",
            "\\texttt{{{}}}".format(execution["protocol_revision"]),
        ),
        _macro(
            "ArrFullRunnerSha",
            "\\texttt{{{}}}".format(execution["full_runner_source_sha256"]),
        ),
        _macro(
            "ArrFullPlannerRevision",
            "\\texttt{{{}}}".format(execution["planner_revision"]),
        ),
        _macro(
            "ArrFullPlannerBinarySha",
            "\\texttt{{{}}}".format(execution["planner_binary_sha256"]),
        ),
        _macro(
            "ArrFullPlannerPreprocessSha",
            "\\texttt{{{}}}".format(execution["planner_preprocess_sha256"]),
        ),
        _macro(
            "ArrFullJobSha",
            "\\texttt{{{}}}".format(execution["prospective_start_job_sha256"]),
        ),
        _macro(
            "ArrFullPfiveToPsixLineageProtocol",
            "\\texttt{{{}}}".format(
                _tex_escape(execution["p5_to_p6_git_lineage_protocol"])
            ),
        ),
        _macro(
            "ArrFullPresearchSigxcpuProtocol",
            "\\texttt{{{}}}".format(
                _tex_escape(execution["presearch_sigxcpu_normalization_protocol"])
            ),
        ),
        _macro(
            "ArrFullPresearchSigxcpuRawExit",
            execution["presearch_sigxcpu_raw_exit_code"],
        ),
        _macro(
            "ArrFullPresearchSigxcpuEffectiveExit",
            execution["presearch_sigxcpu_effective_exit_code"],
        ),
        _macro("ArrFullTasks", _tex_int(TASKS)),
        _macro("ArrFullDomains", _tex_int(DOMAINS)),
        _macro("ArrFullCells", _tex_int(CELLS)),
        _macro("ArrFullPfiveTaskDenominator", _tex_int(p5["task_count"])),
        _macro("ArrFullPsixTaskDenominator", _tex_int(data["task_count"])),
        _macro("ArrFullPfiveDomainDenominator", _tex_int(p5["domain_count"])),
        _macro("ArrFullPsixDomainDenominator", _tex_int(data["domain_count"])),
        _macro("ArrFullPfiveCellDenominator", _tex_int(p5["cell_count"])),
        _macro("ArrFullPsixCellDenominator", _tex_int(data["cell_count"])),
        _macro("ArrFullCombinedStageCaveat", _tex_escape(COMBINED_STAGE_CAVEAT)),
        _macro(
            "ArrFullTerminalOutcomeProtocol",
            "\\texttt{{{}}}".format(
                _tex_escape(terminal_outcomes["protocol"])
            ),
        ),
        _macro(
            "ArrFullTerminalOutcomeUnit",
            "\\texttt{{{}}}".format(_tex_escape(terminal_outcomes["unit"])),
        ),
        _macro(
            "ArrFullTerminalOutcomeUnitNote",
            _tex_escape(TERMINAL_OUTCOME_UNIT_NOTE),
        ),
        _macro(
            "ArrFullTerminalOutcomeTwentyOneCaveat",
            _tex_escape(TERMINAL_OUTCOME_CODE_21_CAVEAT),
        ),
        _macro("ArrFullPrimaryMacroNumerator", primary["estimate"]["numerator"]),
        _macro("ArrFullPrimaryMacroDenominator", primary["estimate"]["denominator"]),
        _macro("ArrFullPrimaryMacroPercent", _fraction_percent(primary["estimate"], 2)),
        _macro("ArrFullPrimaryCandidateSolved", _tex_int(primary["micro_coverage"]["candidate_solved"])),
        _macro("ArrFullPrimaryReferenceSolved", _tex_int(primary["micro_coverage"]["reference_solved"])),
        _macro("ArrFullPrimaryMicroDelta", primary["micro_coverage"]["candidate_minus_reference_tasks"]),
        _macro("ArrFullSensitivityTasks", _tex_int(SENSITIVITY_TASKS)),
        _macro("ArrFullSensitivityMacroNumerator", sensitivity["estimate"]["numerator"]),
        _macro("ArrFullSensitivityMacroDenominator", sensitivity["estimate"]["denominator"]),
        _macro("ArrFullSensitivityMacroPercent", _fraction_percent(sensitivity["estimate"], 2)),
        _macro("ArrFullSensitivityCandidateSolved", _tex_int(sensitivity["micro_coverage"]["candidate_solved"])),
        _macro("ArrFullSensitivityReferenceSolved", _tex_int(sensitivity["micro_coverage"]["reference_solved"])),
        _macro("ArrFullSensitivityMicroDelta", sensitivity["micro_coverage"]["candidate_minus_reference_tasks"]),
        _macro("ArrFullRestartedCells", _tex_int(completion["global"]["cells_completed_after_nonzero_slurm_restart"])),
        _macro("ArrFullSlurmRestartTotal", _tex_stat(completion["global"]["slurm_restart_count"]["total"])),
        _macro("ArrFullPartialArchiveCells", _tex_int(completion["global"]["cells_with_partial_archives"])),
        _macro("ArrFullPartialArchiveTotal", _tex_int(completion["global"]["total_partial_archives"])),
        _macro("ArrFullAttemptGenerationTotal", _tex_int(completion["global"]["total_descriptive_cell_attempt_generations"])),
    ]

    global_outcomes = {
        row["planner_exit_code"]: row
        for row in terminal_outcomes["global"]["outcomes"]
    }
    for code, code_suffix in TERMINAL_OUTCOME_CODE_SUFFIXES:
        lines.append(
            _macro(
                "ArrFullTerminalOutcomeCode{}".format(code_suffix),
                _tex_int(global_outcomes[code]["cell_records"]),
            )
        )

    for expected in CONFIGS:
        config = configs[expected["label"]]
        p5_config = p5_configs[expected["label"]]
        suffix = expected["suffix"]
        construction = config["construction"]
        width = config["exact_cofactor_width"]
        image = config["image"]
        amort = image["complete_amortization"]
        effort = config["search_effort_on_solved_cells"]
        lines.extend(
            [
                _macro("ArrFull{}Solved".format(suffix), _tex_int(config["coverage"]["solved"])),
                _macro("ArrFull{}ParTwo".format(suffix), _decimal(config["micro_par2_seconds"], 4)),
                _macro("ArrFullPfive{}Solved".format(suffix), _tex_int(p5_config["solved"])),
                _macro("ArrFullPfive{}ParTwo".format(suffix), _decimal(p5_config["micro_par2_seconds"], 4)),
                _macro("ArrFullPsix{}Solved".format(suffix), _tex_int(config["coverage"]["solved"])),
                _macro("ArrFullPsix{}ParTwo".format(suffix), _decimal(config["micro_par2_seconds"], 4)),
                _macro("ArrFull{}RuntimeObserved".format(suffix), _tex_int(config["solved_runtime_seconds"]["summary"]["observed"])),
                _macro("ArrFull{}RuntimeMedian".format(suffix), _decimal(config["solved_runtime_seconds"]["summary"]["median"], 3, trim=True)),
                _macro("ArrFull{}RuntimeMinimum".format(suffix), _decimal(config["solved_runtime_seconds"]["summary"]["minimum"], 3, trim=True)),
                _macro("ArrFull{}RuntimeMaximum".format(suffix), _decimal(config["solved_runtime_seconds"]["summary"]["maximum"], 3, trim=True)),
                _macro("ArrFull{}RuntimeMean".format(suffix), _decimal(config["solved_runtime_seconds"]["summary"]["mean"], 3, trim=True)),
                _macro("ArrFull{}RuntimeTotal".format(suffix), _decimal(config["solved_runtime_seconds"]["summary"]["total"], 3)),
                _macro("ArrFull{}EffortObserved".format(suffix), _tex_int(effort["summary"]["observed"])),
                _macro("ArrFull{}EffortMinimum".format(suffix), _tex_stat(effort["summary"]["minimum"])),
                _macro("ArrFull{}EffortMedian".format(suffix), _tex_stat(effort["summary"]["median"])),
                _macro("ArrFull{}EffortMaximum".format(suffix), _tex_stat(effort["summary"]["maximum"])),
                _macro("ArrFull{}EffortMean".format(suffix), _decimal(effort["summary"]["mean"], 3, trim=True)),
                _macro("ArrFull{}EffortTotal".format(suffix), _tex_stat(effort["summary"]["total"])),
                _macro("ArrFull{}ConstructionObserved".format(suffix), _tex_int(construction["certification"]["certified_cells"])),
                _macro("ArrFull{}ConstructionEligible".format(suffix), _tex_int(construction["certification"]["eligible_cells"])),
                _macro("ArrFull{}ConstructionFallbacks".format(suffix), _tex_int(construction["fallbacks"])),
                _macro("ArrFull{}ConstructionSeconds".format(suffix), _decimal(construction["time_seconds"]["total"], 3)),
                _macro("ArrFull{}WidthObserved".format(suffix), _tex_int(width["certification"]["certified_cells"])),
                _macro("ArrFull{}WidthEligible".format(suffix), _tex_int(width["certification"]["eligible_cells"])),
                _macro("ArrFull{}WidthMinimum".format(suffix), _tex_stat(width["summary"]["minimum"])),
                _macro("ArrFull{}WidthMedian".format(suffix), _tex_stat(width["summary"]["median"])),
                _macro("ArrFull{}WidthMaximum".format(suffix), _tex_stat(width["summary"]["maximum"])),
                _macro("ArrFull{}ImagePrefixObserved".format(suffix), _tex_int(image["certified_prefix"]["certified_cells"])),
                _macro("ArrFull{}ImagePrefixEligible".format(suffix), _tex_int(image["certified_prefix"]["eligible_cells"])),
                _macro("ArrFull{}ImagePrefixSeconds".format(suffix), _decimal(image["prefix_image_time_seconds"]["total"], 3)),
                _macro("ArrFull{}ImageCompleteObserved".format(suffix), _tex_int(image["complete_certified"]["certified_cells"])),
                _macro("ArrFull{}ImageCompleteEligible".format(suffix), _tex_int(image["complete_certified"]["eligible_cells"])),
                _macro("ArrFull{}ImageCompleteSeconds".format(suffix), _decimal(amort["aggregate_image_time_seconds"], 3)),
                _macro("ArrFull{}ImageAttemptedCalls".format(suffix), _tex_stat(amort["image_calls_attempted"]["total"])),
                _macro("ArrFull{}ImageCompletedCalls".format(suffix), _tex_int(amort["aggregate_completed_image_calls"])),
                _macro("ArrFull{}ImageSecondsPerCall".format(suffix), _decimal(amort["seconds_per_completed_image_call"], 6, trim=True)),
            ]
        )

    terminal_by_label = {
        entry["label"]: entry for entry in terminal_outcomes["per_config"]
    }
    for expected in CONFIGS:
        suffix = expected["suffix"]
        outcome_by_code = {
            row["planner_exit_code"]: row["cell_records"]
            for row in terminal_by_label[expected["label"]]["outcomes"]
        }
        for code, code_suffix in TERMINAL_OUTCOME_CODE_SUFFIXES:
            lines.append(
                _macro(
                    "ArrFull{}TerminalOutcomeCode{}".format(
                        suffix, code_suffix
                    ),
                    _tex_int(outcome_by_code[code]),
                )
            )

    selector = configs["pdb_selector_k1"]["selector_effort"]
    lines.extend(
        [
            _macro("ArrFullSelectorTraceObserved", _tex_int(selector["certification"]["certified_cells"])),
            _macro("ArrFullSelectorTraceEligible", _tex_int(selector["certification"]["eligible_cells"])),
            _macro("ArrFullSelectorCandidateRecordsTotal", _tex_stat(selector["candidate_records"]["total"])),
            _macro("ArrFullSelectorSourceEvaluationsTotal", _tex_stat(selector["source_evaluations"]["total"])),
            _macro("ArrFullSelectorFeasibleRecordsTotal", _tex_stat(selector["feasible_candidate_records"]["total"])),
            _macro("ArrFullSelectorRejectedRecordsTotal", _tex_stat(selector["rejected_candidate_records"]["total"])),
        ]
    )
    for source, suffix in (
        ("empty", "Empty"),
        ("bdd_prefix", "BddPrefix"),
        ("goal_prefix", "GoalPrefix"),
        ("goal_fill", "GoalFill"),
        ("cegar", "Cegar"),
    ):
        lines.append(
            _macro(
                "ArrFullSelectorSource{}".format(suffix),
                _tex_int(selector["selected_source_counts"][source]),
            )
        )

    lines.append("\\newcommand{\\ArrFullSelectorEffortRows}{%")
    for name, paper_label in (
        ("candidate_records", "Candidate records"),
        ("source_evaluations", "Source evaluations"),
        ("feasible_candidate_records", "Feasible candidate records"),
        ("rejected_candidate_records", "Rejected candidate records"),
    ):
        lines.append(_selector_summary_row(paper_label, selector[name]))
    lines.append("}")

    lines.append("\\newcommand{\\ArrFullConfigRows}{%")
    lines.extend(_config_row(configs[label]) for label in CONFIG_LABELS)
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullCombinedStageRows}{%")
    lines.extend(
        _combined_stage_row(p5_configs[label], configs[label])
        for label in CONFIG_LABELS
    )
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullImageRows}{%")
    lines.extend(_image_row(configs[label]) for label in CONFIG_LABELS)
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullRuntimeEffortRows}{%")
    lines.extend(_runtime_effort_row(configs[label]) for label in CONFIG_LABELS)
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullComparisonRows}{%")
    lines.extend(_comparison_row(item) for item in data["comparisons"])
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullPairedMetricRows}{%")
    lines.extend(_paired_metric_row(item) for item in data["comparisons"])
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullCompletionRows}{%")
    lines.append(_completion_row("global", "All configurations", completion["global"]))
    completion_by_label = {entry["label"]: entry for entry in completion["per_config"]}
    for label in CONFIG_LABELS:
        lines.append(
            _completion_row(
                label,
                CONFIG_BY_LABEL[label]["paper_label"],
                completion_by_label[label],
            )
        )
    lines.append("}")

    lines.append("\\newcommand{\\ArrFullTerminalOutcomeRows}{%")
    lines.extend(
        _terminal_outcome_row(row)
        for row in terminal_outcomes["global"]["outcomes"]
    )
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullTerminalOutcomePerConfigRows}{%")
    for label in CONFIG_LABELS:
        lines.append(
            _terminal_outcome_per_config_row(
                CONFIG_BY_LABEL[label]["paper_label"],
                terminal_by_label[label],
            )
        )
    lines.append("}")

    lines.append("\\newcommand{\\ArrFullStructureDirectRows}{%")
    lines.extend(
        _structure_direct_row(structure_configs[label])
        for label in CONFIG_LABELS
    )
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullStructurePartitionRows}{%")
    for label in CONFIG_LABELS:
        lines.append(
            _structure_partition_row(
                structure_configs[label],
                "raw_complete_logs_not_necessarily_complete_searches",
                "Complete WBH log",
            )
        )
        lines.append(
            _structure_partition_row(
                structure_configs[label],
                "certified_resource_prefixes",
                "Certified resource prefix",
            )
        )
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullStructureCorrelationRows}{%")
    for label in CONFIG_LABELS:
        for key, display in STRUCTURE_CORRELATIONS:
            lines.append(
                _structure_correlation_row(structure_configs[label], key, display)
            )
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullStructureCandidateRows}{%")
    lines.append(_structure_candidate_row(candidate_pool))
    lines.append("}")
    lines.append("\\newcommand{\\ArrFullStructureSourceRows}{%")
    lines.extend(
        _structure_source_row(row)
        for row in candidate_pool["source_status_counts"]
    )
    lines.append("}")

    config_domains = {
        label: {entry["domain"]: entry for entry in configs[label]["per_domain_coverage"]}
        for label in CONFIG_LABELS
    }
    primary_domains = {entry["domain"]: entry for entry in primary["per_domain"]}
    lines.append("\\newcommand{\\ArrFullDomainCoverageRows}{%")
    for domain, task_count in indexes_from_data(data):
        fields = [_tex_escape(domain), _tex_int(task_count)]
        fields.extend(_tex_int(config_domains[label][domain]["solved"]) for label in CONFIG_LABELS)
        fields.append(
            _fraction_percent(
                primary_domains[domain]["candidate_minus_reference_rate"], 2
            )
        )
        lines.append("{} \\\\%".format(" & ".join(fields)))
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def render_tex(
    value,
    analysis_sha256,
    *,
    structure=None,
    structure_sha256=None,
    p5_analysis=None,
    p5_analysis_sha256=None,
):
    """Public production renderer; canceled-run pins cannot be supplied."""
    pins = reviewed_production_pins()
    if analysis_sha256 != pins["analysis_sha256"]:
        raise RenderError("analysis artifact does not match its reviewed digest")
    if structure is None or structure_sha256 is None:
        raise RenderError("structure value and reviewed SHA-256 are required together")
    if structure_sha256 != pins["structure_sha256"]:
        raise RenderError("structure artifact does not match its reviewed digest")
    return _render_tex_with_test_pins(
        value,
        analysis_sha256,
        launch_pins=pins["launch"],
        structure=structure,
        structure_sha256=structure_sha256,
        p5_analysis=p5_analysis,
        p5_analysis_sha256=p5_analysis_sha256,
    )


def indexes_from_data(data):
    first = {item["label"]: item for item in data["configs"]}[CONFIG_LABELS[0]]
    return [(entry["domain"], entry["tasks"]) for entry in first["per_domain_coverage"]]


def _tex_escape(value):
    replacements = {
        "\\": "\\textbackslash{}",
        "&": "\\&",
        "%": "\\%",
        "$": "\\$",
        "#": "\\#",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "~": "\\textasciitilde{}",
        "^": "\\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in value)


def _validate_write_target(path, *, expected=DEFAULT_OUTPUT, root=REPOSITORY_ROOT):
    """Confine mutating CLI output and reject every symlinked path component."""
    path = Path(os.path.abspath(str(path)))
    expected = Path(os.path.abspath(str(expected)))
    root = Path(os.path.abspath(str(root)))
    if path != expected:
        raise RenderError("--write is restricted to {}".format(expected))
    try:
        relative = path.relative_to(root)
    except ValueError as err:
        raise RenderError("write target is outside the repository") from err
    current = root
    for index, part in enumerate(relative.parts):
        current = current / part
        try:
            info = current.lstat()
        except FileNotFoundError:
            continue
        except OSError as err:
            raise RenderError("cannot inspect write target {}: {}".format(current, err)) from err
        if stat.S_ISLNK(info.st_mode):
            raise RenderError("write target contains symlink component {}".format(current))
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise RenderError("write-target parent is not a directory: {}".format(current))
        if index == len(relative.parts) - 1 and not stat.S_ISREG(info.st_mode):
            raise RenderError("existing write target is not a regular file")
    return path


def _write_atomic(path, payload):
    path = Path(path)
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    except OSError as err:
        raise RenderError("cannot inspect output {}: {}".format(path, err)) from err
    if info is not None:
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise RenderError("output must be absent or a regular non-symlink file")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(
            prefix="." + path.name + ".", dir=str(path.parent)
        )
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o644)
            os.replace(temporary, path)
            temporary = None
            try:
                directory_fd = os.open(str(path.parent), os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
            except OSError:
                pass
        finally:
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass
    except OSError as err:
        raise RenderError("cannot atomically write {}: {}".format(path, err)) from err


def check_output(path, expected):
    actual = _read_regular(path, max(MAX_ARTIFACT_BYTES, len(expected) + 1))
    if actual != expected:
        raise RenderError("generated TeX is stale or differs from deterministic output")


_CURRENT_FIXTURE_BUNDLE = None


def _current_analyzer_fixture():
    """Build one 9,639-cell synthetic current-contract analysis for tests."""
    global _CURRENT_FIXTURE_BUNDLE
    if _CURRENT_FIXTURE_BUNDLE is not None:
        return _CURRENT_FIXTURE_BUNDLE[:3]
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import analyze_arrhenius_selector_full as analyzer
        import analyze_arrhenius_selector_full_structure as structure_analyzer
    finally:
        try:
            sys.path.remove(str(SCRIPT_DIR))
        except ValueError:
            pass
    selection_path = (
        SCRIPT_DIR
        / "artifacts"
        / "arrhenius-selector-screen-p4"
        / "selection-v3.json"
    )
    artifact, artifact_digest = analyzer.load_selection_artifact(selection_path)
    if artifact_digest != EXPECTED_SELECTION_ARTIFACT_SHA256:
        raise AssertionError("synthetic fixture selection pin changed")
    contract = analyzer.validate_selection_artifact(artifact)
    tasks, screen_excluded, domains = analyzer.load_and_validate_tasks()
    fixture_pins = CURRENT_ANALYZER_FIXTURE_LAUNCH_PINS
    overrides = {
        "FULL_RUNNER_SOURCE_SHA256": fixture_pins["full_runner_source_sha256"],
        "PLANNER_REVISION": fixture_pins["planner_revision"],
        "CACHE_BINARY_SHA256": fixture_pins["planner_binary_sha256"],
        "CACHE_PREPROCESS_SHA256": fixture_pins["planner_preprocess_sha256"],
        "EXPECTED_PROSPECTIVE_JOB_SHA256": {
            analyzer.EXPECTED_UNBATCHED_RUNS: fixture_pins[
                "prospective_start_job_sha256"
            ],
            analyzer.EXPECTED_BATCHED_RUNS: hashlib.sha256(
                b"synthetic batched v4 full job"
            ).hexdigest(),
        },
    }
    saved = {name: getattr(analyzer, name) for name in overrides}
    try:
        for name, replacement in overrides.items():
            setattr(analyzer, name, replacement)
        static = analyzer.expected_protocol_metadata(
            contract, artifact_digest, fixture_pins["protocol_revision"]
        )
        records = []
        for config_index, (label, search) in enumerate(contract["configs"]):
            for task_index, task in enumerate(tasks):
                run_id = config_index * len(tasks) + task_index + 1
                records.append(
                    analyzer._synthetic_record(
                        label,
                        search,
                        task,
                        task_index,
                        run_id,
                        contract,
                        static,
                    )
                )
        result = analyzer.analyze(
            records,
            tasks,
            screen_excluded,
            domains,
            contract,
            artifact_digest,
            fixture_pins["protocol_revision"],
        )
        structure = structure_analyzer.analyze(
            records,
            tasks,
            contract,
            artifact_digest,
            fixture_pins["protocol_revision"],
        )
    finally:
        for name, original in saved.items():
            setattr(analyzer, name, original)
    raw = canonical_json(result).encode("ascii") + b"\n"
    structure_raw = canonical_json(structure).encode("ascii") + b"\n"
    _CURRENT_FIXTURE_BUNDLE = (
        result,
        raw,
        sha256_bytes(raw),
        structure,
        structure_raw,
        sha256_bytes(structure_raw),
    )
    return _CURRENT_FIXTURE_BUNDLE[:3]


def _current_structure_fixture():
    """Return the synthetic diagnostic built from the exact same P6 records."""
    _current_analyzer_fixture()
    return _CURRENT_FIXTURE_BUNDLE[3:]


def self_test():
    value, raw, digest = _current_analyzer_fixture()
    structure, structure_raw, structure_digest = _current_structure_fixture()
    p5_value, p5_digest = load_p5_analysis()
    fixture_pins = CURRENT_ANALYZER_FIXTURE_LAUNCH_PINS
    _validate_analysis_with_test_pins(
        value, digest, launch_pins=fixture_pins
    )
    first = _render_tex_with_test_pins(
        value,
        digest,
        launch_pins=fixture_pins,
        structure=structure,
        structure_sha256=structure_digest,
        p5_analysis=p5_value,
        p5_analysis_sha256=p5_digest,
    )
    second = _render_tex_with_test_pins(
        copy.deepcopy(value),
        digest,
        launch_pins=fixture_pins,
        structure=structure,
        structure_sha256=structure_digest,
        p5_analysis=copy.deepcopy(p5_value),
        p5_analysis_sha256=p5_digest,
    )
    if first != second:
        raise AssertionError("TeX rendering is not deterministic")
    data_first = canonical_json(
        _paper_data_with_test_pins(
            value,
            digest,
            launch_pins=fixture_pins,
            structure=structure,
            structure_sha256=structure_digest,
            p5_analysis=p5_value,
            p5_analysis_sha256=p5_digest,
        )
    )
    data_second = canonical_json(
        _paper_data_with_test_pins(
            copy.deepcopy(value),
            digest,
            launch_pins=fixture_pins,
            structure=copy.deepcopy(structure),
            structure_sha256=structure_digest,
            p5_analysis=copy.deepcopy(p5_value),
            p5_analysis_sha256=p5_digest,
        )
    )
    if data_first != data_second:
        raise AssertionError("paper-data rendering is not deterministic")
    census = value["terminal_outcome_census"]
    if (
        census["protocol"] != TERMINAL_OUTCOME_CENSUS_PROTOCOL
        or census["unit"] != TERMINAL_OUTCOME_CENSUS_UNIT
        or [
            row["planner_exit_code"]
            for row in census["global"]["outcomes"]
        ]
        != list(TERMINAL_OUTCOME_CODES)
        or len(census["global"]["outcomes"])
        != len(TERMINAL_OUTCOME_SPECS)
    ):
        raise AssertionError("terminal-outcome census rendering contract changed")
    if (
        TERMINAL_OUTCOME_UNIT_NOTE.encode("ascii") not in first
        or TERMINAL_OUTCOME_CODE_21_CAVEAT.encode("ascii") not in first
    ):
        raise AssertionError("terminal-outcome reporting caveats disappeared")
    if (
        p5_digest != EXPECTED_P5_ANALYSIS_SHA256
        or b"\\newcommand{\\ArrFullCombinedStageRows}{%" not in first
        or COMBINED_STAGE_CAVEAT.encode("ascii") not in first
    ):
        raise AssertionError("pinned P5 combined-stage reporting contract changed")

    shuffled = copy.deepcopy(value)
    shuffled["primary"]["configs"].reverse()
    shuffled["primary"]["carried_comparisons"].reverse()
    shuffled["completion_and_recovery"]["per_config"].reverse()
    shuffled["primary"][
        "selector_vs_cegar_equally_weighted_domain_coverage"
    ]["per_domain"].reverse()
    shuffled["sole_predeclared_sensitivity"]["per_domain"].reverse()
    for config in shuffled["primary"]["configs"]:
        config["per_domain_coverage"].reverse()
    shuffled_raw = canonical_json(shuffled).encode("ascii") + b"\n"
    shuffled_digest = sha256_bytes(shuffled_raw)
    shuffled_data = _paper_data_with_test_pins(
        shuffled,
        shuffled_digest,
        launch_pins=fixture_pins,
        structure=structure,
        structure_sha256=structure_digest,
        p5_analysis=p5_value,
        p5_analysis_sha256=p5_digest,
    )
    shuffled_tex = _render_tex_with_test_pins(
        shuffled,
        shuffled_digest,
        launch_pins=fixture_pins,
        structure=structure,
        structure_sha256=structure_digest,
        p5_analysis=p5_value,
        p5_analysis_sha256=p5_digest,
    )
    original_data = json.loads(data_first)
    normalized_tex = shuffled_tex.replace(
        shuffled_digest.encode("ascii"), digest.encode("ascii")
    ).replace(
        sha256_json(shuffled_data).encode("ascii"),
        sha256_json(original_data).encode("ascii"),
    )
    if normalized_tex != first:
        raise AssertionError("label-indexed TeX changed after array permutation")
    shuffled_data["analysis_sha256"] = digest
    if canonical_json(shuffled_data) != data_first:
        raise AssertionError("label-indexed paper data changed after array permutation")

    def expect_error(mutator, fragment):
        changed = copy.deepcopy(value)
        mutator(changed)
        changed_raw = canonical_json(changed).encode("ascii") + b"\n"
        try:
            _validate_analysis_with_test_pins(
                changed,
                sha256_bytes(changed_raw),
                launch_pins=fixture_pins,
            )
        except RenderError as err:
            if fragment not in str(err):
                raise AssertionError(
                    "expected {!r}, got {!r}".format(fragment, str(err))
                ) from err
        else:
            raise AssertionError("mutation was accepted: {}".format(fragment))

    def expect_structure_error(mutator, fragment):
        changed = copy.deepcopy(structure)
        mutator(changed)
        changed_raw = canonical_json(changed).encode("ascii") + b"\n"
        try:
            _validate_structure_with_test_pins(
                changed,
                sha256_bytes(changed_raw),
                analysis=value,
                analysis_sha256=digest,
                launch_pins=fixture_pins,
            )
        except RenderError as err:
            if fragment not in str(err):
                raise AssertionError(
                    "expected {!r}, got {!r}".format(fragment, str(err))
                ) from err
        else:
            raise AssertionError(
                "structure mutation was accepted: {}".format(fragment)
            )

    expect_structure_error(
        lambda changed: changed.__setitem__("schema", "changed"),
        "structure.schema",
    )
    expect_structure_error(
        lambda changed: changed["input_identity"].__setitem__(
            "properties_canonical_sha256", sha256_bytes(b"structural drift")
        ),
        "structure.input_identity",
    )
    expect_structure_error(
        lambda changed: changed["configs"][1]["direct_W_A_V_T_U"][
            "tuple_census"
        ][0].__setitem__("U", 1),
        "violates W >= T >= V",
    )
    expect_structure_error(
        lambda changed: changed["configs"][1]["partition_ratios"][
            "raw_complete_logs_not_necessarily_complete_searches"
        ]["cross_task_descriptive_confounded_correlations"][
            "W_vs_partition_ratio_max"
        ].__setitem__("null_reason", "zero-rank-variance"),
        "null_reason",
    )

    expect_error(
        lambda changed: changed["execution"].__setitem__("cell_count", CELLS - 1),
        "cell_count",
    )
    expect_error(
        lambda changed: changed["primary"]["configs"][6]["coverage"].__setitem__("rate", 0.0),
        "coverage.rate",
    )
    expect_error(
        lambda changed: changed["primary"]["configs"][6]["selector_effort"]["certification"].__setitem__("certified_cells", TASKS - 1),
        "certification arithmetic",
    )
    expect_error(
        lambda changed: changed["primary"]["selector_vs_cegar_equally_weighted_domain_coverage"]["estimate"].__setitem__("numerator", 1),
        "exact fraction",
    )
    expect_error(
        lambda changed: changed["completion_and_recovery"]["global"].__setitem__("total_descriptive_cell_attempt_generations", CELLS),
        "attempt total",
    )
    expect_error(
        lambda changed: changed["terminal_outcome_census"].__setitem__(
            "unit", "attempts"
        ),
        "terminal_outcome_census.unit",
    )
    expect_error(
        lambda changed: changed["terminal_outcome_census"]["global"][
            "outcomes"
        ][-1].__setitem__("planner_exit_code", 232),
        "planner_exit_code",
    )
    expect_error(
        lambda changed: changed["terminal_outcome_census"]["global"][
            "outcomes"
        ][1].__setitem__("search_raw_exit_code", 1),
        "search_raw_exit_code",
    )
    expect_error(
        lambda changed: changed["terminal_outcome_census"]["global"][
            "outcomes"
        ][2].__setitem__("search_effective_exit_code", 23),
        "search_effective_exit_code",
    )
    expect_error(
        lambda changed: changed["terminal_outcome_census"]["global"][
            "outcomes"
        ][0].__setitem__("unexpected", 0),
        "keys changed",
    )

    def shift_terminal_counts(changed, source, target):
        for outcome_slice in (
            changed["terminal_outcome_census"]["global"],
            changed["terminal_outcome_census"]["per_config"][0],
        ):
            by_code = {
                row["planner_exit_code"]: row
                for row in outcome_slice["outcomes"]
            }
            by_code[source]["cell_records"] -= 1
            by_code[target]["cell_records"] += 1

    expect_error(
        lambda changed: shift_terminal_counts(changed, 0, 23),
        "terminal solved counts disagree with coverage",
    )
    expect_error(
        lambda changed: shift_terminal_counts(changed, 23, 20),
        "pre-search outcome counts disagree with image summary",
    )

    def change_global_marginal(changed):
        by_code = {
            row["planner_exit_code"]: row
            for row in changed["terminal_outcome_census"]["global"][
                "outcomes"
            ]
        }
        by_code[23]["cell_records"] -= 1
        by_code[22]["cell_records"] += 1

    expect_error(change_global_marginal, "global/per-configuration counts disagree")
    expect_error(
        lambda changed: changed["primary"]["carried_comparisons"][-1].__setitem__(
            "name", PRIMARY_COMPARISON
        ),
        "duplicate name",
    )

    try:
        parse_canonical_analysis(canonical_json(value).encode("ascii"), "synthetic")
    except RenderError as err:
        if "one newline" not in str(err):
            raise
    else:
        raise AssertionError("non-newline-terminated artifact was accepted")

    with tempfile.TemporaryDirectory(prefix="full-paper-render-") as raw_dir:
        root = Path(raw_dir)
        artifact = root / "analysis-v4.json"
        sidecar = Path(str(artifact) + ".sha256")
        artifact.write_bytes(raw)
        sidecar.write_text("{}  {}\n".format(digest, artifact.name), encoding="ascii")
        loaded, loaded_digest = _load_frozen_analysis_with_test_pins(
            artifact,
            expected_analysis_sha256=digest,
            launch_pins=fixture_pins,
        )
        if loaded != value or loaded_digest != digest:
            raise AssertionError("canonical artifact round trip changed")
        output = root / "generated.tex"
        _write_atomic(output, first)
        check_output(output, first)
        _write_atomic(output, first)
        check_output(output, first)
        sidecar.write_text("{} *{}\n".format(digest, artifact.name), encoding="ascii")
        try:
            _load_frozen_analysis_with_test_pins(
                artifact,
                expected_analysis_sha256=digest,
                launch_pins=fixture_pins,
            )
        except RenderError as err:
            if "sidecar" not in str(err):
                raise
        else:
            raise AssertionError("noncanonical sidecar was accepted")

    return {
        "schema": PAPER_DATA_SCHEMA,
        "self_test": "PASS",
        "p5_analysis_sha256": p5_digest,
        "synthetic_analysis_sha256": digest,
        "synthetic_paper_data_sha256": sha256_bytes(data_first.encode("ascii")),
        "synthetic_tex_sha256": sha256_bytes(first),
        "synthetic_tex_bytes": len(first),
        "adversarial": [
            "canonical-json-and-sidecar",
            "pinned-p5-canonical-json-sidecar-identity-and-arithmetic",
            "identity-and-layout",
            "coverage-and-certification-arithmetic",
            "terminal-outcome-order-mapping-zero-rows-and-arithmetic",
            "macro-fraction",
            "completion-recovery",
            "duplicate-label-and-name",
            "shuffled-label-indexed-arrays",
            "secondary-structure-schema-identity-and-cross-binding",
            "secondary-structure-census-conservation-and-correlation-null-arithmetic",
            "deterministic-atomic-output",
        ],
        "ordinary_render_gate": (
            "READY_WITH_ATOMIC_FULL_ANALYSIS_STRUCTURE_AND_V4_LAUNCH_PINS"
        ),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate and render the frozen Arrhenius full-census analysis."
    )
    parser.add_argument(
        "analysis",
        nargs="?",
        type=Path,
        default=DEFAULT_ANALYSIS,
        help="canonical full analysis-v4.json artifact",
    )
    parser.add_argument(
        "--sidecar",
        type=Path,
        help="exact sha256sum sidecar (default: ANALYSIS.sha256)",
    )
    parser.add_argument(
        "--structure",
        type=Path,
        default=DEFAULT_STRUCTURE,
        help="confined secondary structure-v1.json artifact",
    )
    parser.add_argument(
        "--structure-sidecar",
        type=Path,
        default=DEFAULT_STRUCTURE_SIDECAR,
        help="exact secondary structure sha256sum sidecar",
    )
    parser.add_argument(
        "--p5-analysis",
        type=Path,
        default=DEFAULT_P5_ANALYSIS,
        help="fixed tracked P5 held-out analysis-v3.json artifact",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="generated TeX path",
    )
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true", help="verify generated TeX is current")
    actions.add_argument("--write", action="store_true", help="atomically write generated TeX")
    actions.add_argument("--dump-paper-data", action="store_true", help="print canonical validated paper data")
    actions.add_argument("--self-test", action="store_true", help="run synthetic and adversarial tests")
    args = parser.parse_args(argv)
    if args.self_test:
        defaults_only = (
            args.analysis == DEFAULT_ANALYSIS
            and args.sidecar is None
            and args.structure == DEFAULT_STRUCTURE
            and args.structure_sidecar == DEFAULT_STRUCTURE_SIDECAR
            and args.p5_analysis == DEFAULT_P5_ANALYSIS
            and args.output == DEFAULT_OUTPUT
        )
        if not defaults_only:
            parser.error("--self-test does not accept input or output paths")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        print(canonical_json(self_test()))
        return 0
    value, digest = load_frozen_analysis(args.analysis, args.sidecar)
    structure, structure_digest = load_frozen_structure(
        args.structure,
        args.structure_sidecar,
        analysis=value,
        analysis_sha256=digest,
    )
    p5_value, p5_digest = load_p5_analysis(args.p5_analysis)
    if args.dump_paper_data:
        print(
            canonical_json(
                paper_data(
                    value,
                    digest,
                    structure=structure,
                    structure_sha256=structure_digest,
                    p5_analysis=p5_value,
                    p5_analysis_sha256=p5_digest,
                )
            )
        )
        return 0
    rendered = render_tex(
        value,
        digest,
        structure=structure,
        structure_sha256=structure_digest,
        p5_analysis=p5_value,
        p5_analysis_sha256=p5_digest,
    )
    if args.check:
        check_output(args.output, rendered)
        print(
            canonical_json(
                {
                    "check": "PASS",
                    "output": str(args.output),
                    "sha256": sha256_bytes(rendered),
                }
            )
        )
        return 0
    output = _validate_write_target(args.output)
    _write_atomic(output, rendered)
    print(
        canonical_json(
            {
                "write": "PASS",
                "output": str(args.output),
                "sha256": sha256_bytes(rendered),
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RenderError, RuntimeError) as err:
        print("render error: {}".format(err), file=sys.stderr)
        sys.exit(2)
