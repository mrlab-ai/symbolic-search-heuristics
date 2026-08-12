#!/usr/bin/env python3
"""Render frozen full-population results into deterministic paper data.

This program is intentionally a second, fail-closed consumer of
``analyze_arrhenius_selector_full.py``.  It does not read Lab evaluations or
recompute experimental statistics.  Instead, it verifies the frozen analysis
artifact, independently checks the identities and arithmetic used by the
paper, and emits a small canonical JSON view or deterministic TeX macros.

Ordinary use remains disabled until ``EXPECTED_FULL_ANALYSIS_SHA256`` is set
to the reviewed digest of the final ``analysis-v4.json`` artifact.  The
``--self-test`` path uses a synthetic result produced by the current analyzer
without weakening that production gate.
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
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "arrhenius-selector-full-v4.tex"
)

# Set only after the complete artifact and its sidecar have passed independent
# review.  Keeping this unset makes --check, --write, and --dump-paper-data
# fail before reading an ordinary result.
EXPECTED_FULL_ANALYSIS_SHA256 = None

ANALYSIS_SCHEMA = "symbolic-search-heuristics/full-population-analysis/v4"
ANALYSIS_PROTOCOL = "full-supported-population-census-v1"
PAPER_DATA_SCHEMA = "symbolic-search-heuristics/full-paper-data/v1"
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
# them together with the analysis SHA-256 (six mutable pins total) after the
# corrected v4 launch; partial pinning is rejected.  The P6 source revision is
# already fixed independently.
EXPECTED_PROTOCOL_REVISION = None
EXPECTED_FULL_RUNNER_SHA256 = None
EXPECTED_PLANNER_REVISION = "a3486a027a0f281e762cb6d66d72311455b66b33"
EXPECTED_PLANNER_BINARY_SHA256 = None
EXPECTED_PLANNER_PREPROCESS_SHA256 = None
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
EXPECTED_PROSPECTIVE_JOB_SHA256 = None
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
    expected_keys = {"analysis_sha256"} | LAUNCH_PIN_KEYS
    pins = _mapping(pins, "production pins", expected_keys)
    mutable_keys = expected_keys - {"protocol", "planner_revision"}
    present = sorted(key for key in mutable_keys if pins[key] is not None)
    missing = sorted(key for key in mutable_keys if pins[key] is None)
    if present and missing:
        raise RenderError(
            "production pins are partially set; review analysis and launch "
            "identities together (present={}, missing={})".format(present, missing)
        )
    if not present:
        raise RenderError(
            "full analysis SHA-256 and corrected v4 launch pins are all unset"
        )
    if pins["protocol"] != FULL_PROTOCOL:
        raise RenderError("reviewed production protocol is not corrected v4")
    if pins["planner_revision"] != EXPECTED_PLANNER_REVISION:
        raise RenderError("reviewed P6 planner revision changed")
    analysis_sha256 = _require_sha256(
        pins["analysis_sha256"], "reviewed full analysis SHA-256"
    )
    launch = {key: pins[key] for key in LAUNCH_PIN_KEYS}
    launch = _validate_launch_pins(launch, "reviewed v4 launch pins")
    return {"analysis_sha256": analysis_sha256, "launch": launch}


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


def validate_analysis(value, analysis_sha256):
    """Public production validator; canceled launch pins cannot be injected."""
    pins = reviewed_production_pins()
    if analysis_sha256 != pins["analysis_sha256"]:
        raise RenderError("analysis artifact does not match its reviewed digest")
    return _validate_analysis_with_test_pins(
        value, analysis_sha256, launch_pins=pins["launch"]
    )


def _paper_data_with_test_pins(value, analysis_sha256, *, launch_pins):
    """Create the canonical, label-indexed data view used by TeX rendering."""
    indexes = _validate_analysis_with_test_pins(
        value, analysis_sha256, launch_pins=launch_pins
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
        "selection_artifact_sha256": EXPECTED_SELECTION_ARTIFACT_SHA256,
        "properties_canonical_sha256": value["execution"]["properties_canonical_sha256"],
        "task_count": TASKS,
        "domain_count": DOMAINS,
        "cell_count": CELLS,
        "execution_provenance": execution_provenance,
        "primary": primary,
        "configs": configs,
        "comparisons": comparisons,
        "sole_predeclared_sensitivity": sensitivity,
        "terminal_outcome_census": terminal_outcomes,
        "completion_and_recovery": completion,
    }


def paper_data(value, analysis_sha256):
    """Public production paper view; identities come only from frozen pins."""
    pins = reviewed_production_pins()
    if analysis_sha256 != pins["analysis_sha256"]:
        raise RenderError("analysis artifact does not match its reviewed digest")
    return _paper_data_with_test_pins(
        value, analysis_sha256, launch_pins=pins["launch"]
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


def _render_tex_with_test_pins(value, analysis_sha256, *, launch_pins):
    """Return stable UTF-8 TeX bytes; no filesystem state enters rendering."""
    data = _paper_data_with_test_pins(
        value, analysis_sha256, launch_pins=launch_pins
    )
    configs = {item["label"]: item for item in data["configs"]}
    primary = data["primary"]
    sensitivity = data["sole_predeclared_sensitivity"]
    terminal_outcomes = data["terminal_outcome_census"]
    completion = data["completion_and_recovery"]
    execution = data["execution_provenance"]
    paper_data_digest = sha256_json(data)

    lines = [
        "% Generated by experiments/render_arrhenius_selector_full_paper.py.",
        "% Do not edit: regenerate only from the pinned canonical analysis artifact.",
        "% Source analysis SHA-256: {}".format(analysis_sha256),
        "% Source properties SHA-256: {}".format(
            data["properties_canonical_sha256"]
        ),
        "% Extraction schema: {}".format(PAPER_DATA_SCHEMA),
        "% Canonical PaperData SHA-256: {}".format(paper_data_digest),
        _macro("ArrFullAnalysisSha", "\\texttt{{{}}}".format(analysis_sha256)),
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


def render_tex(value, analysis_sha256):
    """Public production renderer; canceled-run pins cannot be supplied."""
    pins = reviewed_production_pins()
    if analysis_sha256 != pins["analysis_sha256"]:
        raise RenderError("analysis artifact does not match its reviewed digest")
    return _render_tex_with_test_pins(
        value, analysis_sha256, launch_pins=pins["launch"]
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


def _current_analyzer_fixture():
    """Build one 9,639-cell synthetic current-contract analysis for tests."""
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import analyze_arrhenius_selector_full as analyzer
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
    finally:
        for name, original in saved.items():
            setattr(analyzer, name, original)
    raw = canonical_json(result).encode("ascii") + b"\n"
    return result, raw, sha256_bytes(raw)


def self_test():
    value, raw, digest = _current_analyzer_fixture()
    fixture_pins = CURRENT_ANALYZER_FIXTURE_LAUNCH_PINS
    _validate_analysis_with_test_pins(
        value, digest, launch_pins=fixture_pins
    )
    first = _render_tex_with_test_pins(
        value, digest, launch_pins=fixture_pins
    )
    second = _render_tex_with_test_pins(
        copy.deepcopy(value), digest, launch_pins=fixture_pins
    )
    if first != second:
        raise AssertionError("TeX rendering is not deterministic")
    data_first = canonical_json(
        _paper_data_with_test_pins(value, digest, launch_pins=fixture_pins)
    )
    data_second = canonical_json(
        _paper_data_with_test_pins(
            copy.deepcopy(value), digest, launch_pins=fixture_pins
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
        shuffled, shuffled_digest, launch_pins=fixture_pins
    )
    shuffled_tex = _render_tex_with_test_pins(
        shuffled, shuffled_digest, launch_pins=fixture_pins
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
        "synthetic_analysis_sha256": digest,
        "synthetic_paper_data_sha256": sha256_bytes(data_first.encode("ascii")),
        "synthetic_tex_sha256": sha256_bytes(first),
        "synthetic_tex_bytes": len(first),
        "adversarial": [
            "canonical-json-and-sidecar",
            "identity-and-layout",
            "coverage-and-certification-arithmetic",
            "terminal-outcome-order-mapping-zero-rows-and-arithmetic",
            "macro-fraction",
            "completion-recovery",
            "duplicate-label-and-name",
            "shuffled-label-indexed-arrays",
            "deterministic-atomic-output",
        ],
        "ordinary_render_gate": (
            "BLOCKED_UNTIL_FULL_ANALYSIS_SHA256_AND_CORRECTED_V4_LAUNCH_PINS_"
            "ARE_PINNED"
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
    if args.dump_paper_data:
        print(canonical_json(paper_data(value, digest)))
        return 0
    rendered = render_tex(value, digest)
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
