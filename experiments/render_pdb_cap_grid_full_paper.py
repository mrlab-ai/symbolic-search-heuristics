#!/usr/bin/env python3
"""Validate and render the focused cap-grid full analysis for the paper.

This is a prospective, fail-closed consumer of
``analyze_pdb_cap_grid_full.py``.  It reads only the canonical analysis JSON
and its sha256sum-style sidecar; it never opens Lab properties or run data.
Ordinary rendering remains disabled until the final artifact digest and the
three outcome-dependent analysis pins below have been reviewed and set
together.  ``--self-test`` uses a complete synthetic analysis instead.

The TeX payload is intentionally anonymous.  Provenance identities are
validated but never rendered: only scientific aggregates, table-row
fragments, and generic scope/censoring caveats reach the generated file.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import re
import stat
import sys
import tempfile
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from fractions import Fraction
from pathlib import Path


class RenderError(RuntimeError):
    """The analysis artifact cannot safely be rendered."""


SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
DEFAULT_ANALYSIS = (
    SCRIPT_DIR / "artifacts" / "pdb-cap-grid-focused-full" / "analysis-v1.json"
)
DEFAULT_OUTPUT = REPOSITORY_ROOT / "paper" / "generated" / "pdb-cap-grid-full-v1.tex"

# Freeze these four values together only after independent review of the final
# canonical analysis artifact.  All remain unset prospectively by design.
EXPECTED_FULL_ANALYSIS_SHA256 = None
EXPECTED_PROTOCOL_REVISION = None
EXPECTED_PROPERTIES_CANONICAL_SHA256 = None
EXPECTED_PROSPECTIVE_JOB_SHA256 = None

ANALYSIS_SCHEMA = "symbolic-search-heuristics/pdb-cap-grid-focused-full/v1"
ANALYSIS_PROTOCOL = "pdb-cap-grid-focused-full-analysis-v1"
FULL_PROTOCOL = "pdb-cap-grid-focused-full-evaluation-v1"
PAPER_DATA_SCHEMA = "symbolic-search-heuristics/pdb-cap-grid-full-paper/v1"

EXPECTED_PREDECLARATION_SHA256 = (
    "54ee45b88a6a1ca1507971919ad8f3d168abfcbb690857f5900618d407182c5b"
)
EXPECTED_SECONDARY_CONTRACT_SHA256 = (
    "1df86a1255cb301ffe2b6eb0db52ba81ca7f8c511e5a011cd028d8eff2dfc862"
)
EXPECTED_PLANNER_REVISION = "e04d56cc61d00c954f2369e9fb74bd469277d52e"
EXPECTED_PLANNER_BINARY_SHA256 = (
    "77cf4950563be2d2a60aded13783a3ffe26c0c8391ac9d626f3bd618231941fa"
)
EXPECTED_PLANNER_PREPROCESS_SHA256 = (
    "fc3233bfd260210cf4d0cce11146fe6f3198820d6e19a8b56740c1240039378b"
)
EXPECTED_TASK_MANIFEST_SHA256 = (
    "295bff030c51eaf39871714335ff9cb945ce39ebc556774eeb3bfad112681345"
)
EXPECTED_PRIMARY_TASK_MANIFEST_SHA256 = (
    "1e126791b438d903cb6adcc441391b92d76a7e14cf46f6a89465a066823a986f"
)
EXPECTED_OPTION_MATRIX_SHA256 = (
    "94238d64a699142ef81cc4a35489467af8b78dcdf46973536556eb7e3f6b6f78"
)
EXPECTED_COMPLETION_PROTOCOL = (
    "canonical-four-line-marker-atomic-after-python-wrapper-zero-exit/v1"
)

TASKS = 1377
PRIMARY_TASKS = 1327
DOMAINS = 46
CONFIG_COUNT = 5
CELLS = 6885
WIDTH_BUDGET = 8
PAR2_PENALTY = 600
MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
MAX_TEX_BYTES = 256 * 1024
MAX_TEX_MACRO_BYTES = 16 * 1024
MAX_TEX_CELL_BYTES = 512
MAX_TEX_TABLE_ROWS = 128
MAX_INTEGER = 10**30
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
MACRO_RE = re.compile(r"^[A-Za-z]+$")

CONFIGS = (
    ("blind_fw", "Blind", "Blind forward", "descriptive-context"),
    ("ms_exact", "MsExact", "Uncapped M\\&S", "descriptive-context"),
    ("pdb_cegar_b100k", "Cegar", "CEGAR PDB", "descriptive-context"),
    ("pdb_selector_k8", "Exact", "Exact selector $K=8$", "primary-contrast"),
    ("pdb_cap_grid_k8", "Cap", "Cap-aware selector $K=8$", "primary-contrast"),
)
CONFIG_LABELS = tuple(item[0] for item in CONFIGS)
CONFIG_BY_LABEL = {item[0]: item for item in CONFIGS}
EXACT = "pdb_selector_k8"
CAP = "pdb_cap_grid_k8"
SELECTOR_SOURCES = ("empty", "bdd_prefix", "goal_prefix", "goal_fill", "cegar")
CAP_KEYS = ("0", "1", "2", "4", "8", "16", "32", "64", "128", "256", "exact")
SELECTOR_METRICS = (
    ("pattern_size", "Pattern size"),
    ("W", "W"),
    ("A", "A"),
    ("T", "T"),
    ("U", "U"),
    ("V", "V"),
)
SELECTOR_SOURCE_LABELS = {
    "empty": "Empty",
    "bdd_prefix": "BDD prefix",
    "goal_prefix": "Goal prefix",
    "goal_fill": "Goal fill",
    "cegar": "CEGAR",
}

TOP_KEYS = {
    "schema",
    "analysis_protocol",
    "predeclaration",
    "execution",
    "secondary_descriptive_contract",
    "primary",
    "full_census_sensitivity",
    "secondary_descriptive",
    "descriptive_full_census_configs",
    "inference",
}


def canonical_json(value):
    """Return the analyzer's canonical finite-JSON representation."""
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


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def sha256_json(value):
    return sha256_bytes(canonical_json(value).encode("ascii"))


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise RenderError("analysis artifact contains duplicate JSON key {!r}".format(key))
        result[key] = value
    return result


def parse_canonical_analysis(raw, source="analysis artifact"):
    if not isinstance(raw, bytes):
        raise RenderError("{} must be bytes".format(source))
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as err:
        raise RenderError("{} is not ASCII JSON".format(source)) from err

    def reject_constant(token):
        raise RenderError("{} contains nonfinite JSON constant {}".format(source, token))

    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=reject_constant,
        )
    except RenderError:
        raise
    except (TypeError, ValueError, json.JSONDecodeError) as err:
        raise RenderError("{} is not valid JSON: {}".format(source, err)) from err
    expected = canonical_json(value).encode("ascii") + b"\n"
    if raw != expected:
        raise RenderError(
            "{} is not exact canonical ASCII JSON followed by one newline".format(source)
        )
    return value


def _read_regular(path, maximum):
    path = Path(path)
    try:
        info = path.lstat()
    except OSError as err:
        raise RenderError("cannot inspect {}: {}".format(path, err)) from err
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise RenderError("{} must be a regular non-symlink file".format(path))
    if info.st_size > maximum:
        raise RenderError("{} exceeds the {}-byte limit".format(path, maximum))
    try:
        return path.read_bytes()
    except OSError as err:
        raise RenderError("cannot read {}: {}".format(path, err)) from err


def _require_sha256(value, label, expected=None):
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        raise RenderError("{} must be 64 lowercase hexadecimal digits".format(label))
    if expected is not None and value != expected:
        raise RenderError("{} changed".format(label))
    return value


def _require_revision(value, label, expected=None):
    if type(value) is not str or REVISION_RE.fullmatch(value) is None:
        raise RenderError("{} must be 40 lowercase hexadecimal digits".format(label))
    if expected is not None and value != expected:
        raise RenderError("{} changed".format(label))
    return value


def _production_pins():
    values = {
        "analysis_sha256": EXPECTED_FULL_ANALYSIS_SHA256,
        "protocol_revision": EXPECTED_PROTOCOL_REVISION,
        "properties_sha256": EXPECTED_PROPERTIES_CANONICAL_SHA256,
        "job_sha256": EXPECTED_PROSPECTIVE_JOB_SHA256,
    }
    present = [value is not None for value in values.values()]
    if not any(present):
        raise RenderError("focused full renderer pins are unset; refusing to read outcomes")
    if not all(present):
        raise RenderError("focused full renderer pins are only partially set")
    _require_sha256(values["analysis_sha256"], "analysis artifact SHA-256")
    _require_revision(values["protocol_revision"], "protocol revision")
    _require_sha256(values["properties_sha256"], "properties canonical SHA-256")
    _require_sha256(values["job_sha256"], "prospective job SHA-256")
    return values


def _load_frozen_analysis_with_pins(analysis_path, sidecar_path, pins):
    analysis_path = Path(analysis_path)
    sidecar_path = (
        Path(sidecar_path)
        if sidecar_path is not None
        else Path(str(analysis_path) + ".sha256")
    )
    raw = _read_regular(analysis_path, MAX_ARTIFACT_BYTES)
    digest = sha256_bytes(raw)
    if digest != pins["analysis_sha256"]:
        raise RenderError("analysis artifact does not match its reviewed digest")
    sidecar = _read_regular(sidecar_path, 512)
    expected_sidecar = "{}  {}\n".format(digest, analysis_path.name).encode("ascii")
    if sidecar != expected_sidecar:
        raise RenderError("analysis SHA-256 sidecar is not exact sha256sum form")
    value = parse_canonical_analysis(raw, str(analysis_path))
    _validate_analysis_with_pins(value, digest, pins)
    return value, digest


def load_frozen_analysis(analysis_path, sidecar_path=None):
    # Gate before inspecting a caller-supplied path.
    return _load_frozen_analysis_with_pins(
        analysis_path, sidecar_path, _production_pins()
    )


def _mapping(value, label, keys=None):
    if type(value) is not dict:
        raise RenderError("{} must be an object".format(label))
    if keys is not None and set(value) != set(keys):
        raise RenderError("{} keys changed".format(label))
    return value


def _sequence(value, label, length=None):
    if type(value) is not list:
        raise RenderError("{} must be an array".format(label))
    if length is not None and len(value) != length:
        raise RenderError("{} must contain {} entries".format(label, length))
    return value


def _integer(value, label, minimum=0, maximum=MAX_INTEGER):
    if type(value) is not int:
        raise RenderError("{} must be an exact integer".format(label))
    if value < minimum or value > maximum:
        raise RenderError("{} is outside [{}, {}]".format(label, minimum, maximum))
    return value


def _number(value, label, minimum=None, maximum=None):
    if type(value) not in (int, float) or not math.isfinite(float(value)):
        raise RenderError("{} must be a finite number".format(label))
    result = float(value)
    if minimum is not None and result < minimum:
        raise RenderError("{} is below {}".format(label, minimum))
    if maximum is not None and result > maximum:
        raise RenderError("{} exceeds {}".format(label, maximum))
    return result


def _exact_integral_numeric(value, label, minimum=0, maximum=MAX_INTEGER):
    """Validate a derived numeric quantity that must be exactly integral."""
    if type(value) is int:
        return _integer(value, label, minimum, maximum)
    if (
        type(value) is not float
        or not math.isfinite(value)
        or not value.is_integer()
    ):
        raise RenderError("{} must be an exact integral number".format(label))
    result = int(value)
    if result < minimum or result > maximum:
        raise RenderError("{} is outside [{}, {}]".format(label, minimum, maximum))
    return result


def _close(actual, expected, label, tolerance=1e-12):
    actual = _number(actual, label)
    expected = float(expected)
    if not math.isclose(actual, expected, rel_tol=tolerance, abs_tol=tolerance):
        raise RenderError("{} arithmetic changed".format(label))


def _validate_fraction(value, label, fixed_denominator=None):
    value = _mapping(
        value,
        label,
        {"numerator", "denominator", "fixed_estimand_denominator", "value"},
    )
    numerator = _integer(value["numerator"], label + ".numerator", -MAX_INTEGER)
    denominator = _integer(value["denominator"], label + ".denominator", 1)
    if math.gcd(numerator, denominator) != 1:
        raise RenderError("{} fraction is not reduced".format(label))
    if fixed_denominator is not None:
        _integer(
            value["fixed_estimand_denominator"],
            label + ".fixed_estimand_denominator",
            fixed_denominator,
            fixed_denominator,
        )
    elif value["fixed_estimand_denominator"] is not None:
        raise RenderError("{}.fixed_estimand_denominator must be null".format(label))
    result = Fraction(numerator, denominator)
    _close(value["value"], float(result), label + ".value")
    return result


def _validate_summary(value, label, maximum_observed, expected_observed=None):
    value = _mapping(
        value,
        label,
        {"observed", "minimum", "median", "maximum", "mean", "total"},
    )
    observed = _integer(value["observed"], label + ".observed", 0, maximum_observed)
    if expected_observed is not None and observed != expected_observed:
        raise RenderError("{}.observed changed".format(label))
    fields = ("minimum", "median", "maximum", "mean", "total")
    if observed == 0:
        if any(value[field] is not None for field in fields):
            raise RenderError("{} empty summary must contain null statistics".format(label))
        return observed
    numbers = {field: _number(value[field], label + "." + field, 0) for field in fields}
    if not (
        numbers["minimum"] <= numbers["median"] <= numbers["maximum"]
        and numbers["minimum"] <= numbers["mean"] <= numbers["maximum"]
    ):
        raise RenderError("{} order statistics are inconsistent".format(label))
    _close(numbers["total"], numbers["mean"] * observed, label + ".total")
    return observed


def _validate_count_summary(value, label, maximum_observed, expected_observed=None):
    observed = _validate_summary(value, label, maximum_observed, expected_observed)
    result = {
        "observed": observed,
        "minimum": None,
        "median": None,
        "maximum": None,
        "total": None,
    }
    if observed:
        result["minimum"] = _integer(value["minimum"], label + ".minimum")
        result["median"] = value["median"]
        result["maximum"] = _integer(value["maximum"], label + ".maximum")
        result["total"] = _integer(value["total"], label + ".total")
        _exact_integral_numeric(
            2 * _number(value["median"], label + ".median", 0),
            label + ".twice_median",
        )
    return result


def _validate_execution(value, pins):
    keys = {
        "protocol",
        "protocol_revision",
        "planner_revision",
        "planner_binary_sha256",
        "planner_preprocess_sha256",
        "prospective_start_job_sha256",
        "properties_canonical_sha256",
        "task_manifest_sha256",
        "primary_task_manifest_sha256",
        "option_matrix_sha256",
        "cell_count",
        "all_cells_validated",
        "solved_cost_agreement_validated_across_all_configs",
        "completion_recovery_protocol",
    }
    value = _mapping(value, "execution", keys)
    if value["protocol"] != FULL_PROTOCOL:
        raise RenderError("execution.protocol changed")
    _require_revision(
        value["protocol_revision"], "execution.protocol_revision", pins["protocol_revision"]
    )
    _require_revision(
        value["planner_revision"], "execution.planner_revision", EXPECTED_PLANNER_REVISION
    )
    _require_sha256(
        value["planner_binary_sha256"],
        "execution.planner_binary_sha256",
        EXPECTED_PLANNER_BINARY_SHA256,
    )
    _require_sha256(
        value["planner_preprocess_sha256"],
        "execution.planner_preprocess_sha256",
        EXPECTED_PLANNER_PREPROCESS_SHA256,
    )
    _require_sha256(
        value["prospective_start_job_sha256"],
        "execution.prospective_start_job_sha256",
        pins["job_sha256"],
    )
    _require_sha256(
        value["properties_canonical_sha256"],
        "execution.properties_canonical_sha256",
        pins["properties_sha256"],
    )
    _require_sha256(
        value["task_manifest_sha256"],
        "execution.task_manifest_sha256",
        EXPECTED_TASK_MANIFEST_SHA256,
    )
    _require_sha256(
        value["primary_task_manifest_sha256"],
        "execution.primary_task_manifest_sha256",
        EXPECTED_PRIMARY_TASK_MANIFEST_SHA256,
    )
    _require_sha256(
        value["option_matrix_sha256"],
        "execution.option_matrix_sha256",
        EXPECTED_OPTION_MATRIX_SHA256,
    )
    _integer(value["cell_count"], "execution.cell_count", CELLS, CELLS)
    if value["all_cells_validated"] is not True:
        raise RenderError("execution.all_cells_validated must be true")
    if value["solved_cost_agreement_validated_across_all_configs"] is not True:
        raise RenderError("execution solved-cost consistency is not certified")
    if value["completion_recovery_protocol"] != EXPECTED_COMPLETION_PROTOCOL:
        raise RenderError("execution.completion_recovery_protocol changed")


def _validate_mechanism(value, label, tasks):
    keys = {
        "status",
        "required_pairs",
        "paired_complete_certified_traces",
        "same_k_raw_pool_identity_pairs",
        "cap_semantic_nontrivial",
        "exact_semantic_nontrivial",
        "semantic_pair_wins",
        "semantic_pair_losses",
        "semantic_selection_difference_observed",
        "claim_policy",
    }
    value = _mapping(value, label, keys)
    if value["status"] not in ("certified", "not-certified"):
        raise RenderError("{}.status changed".format(label))
    _integer(value["required_pairs"], label + ".required_pairs", tasks, tasks)
    traces = _integer(
        value["paired_complete_certified_traces"],
        label + ".paired_complete_certified_traces",
        0,
        tasks,
    )
    raw = _integer(
        value["same_k_raw_pool_identity_pairs"],
        label + ".same_k_raw_pool_identity_pairs",
        0,
        traces,
    )
    cap_nontrivial = _integer(
        value["cap_semantic_nontrivial"], label + ".cap_semantic_nontrivial", 0, traces
    )
    exact_nontrivial = _integer(
        value["exact_semantic_nontrivial"],
        label + ".exact_semantic_nontrivial",
        0,
        traces,
    )
    wins = _integer(value["semantic_pair_wins"], label + ".semantic_pair_wins", 0, traces)
    losses = _integer(
        value["semantic_pair_losses"], label + ".semantic_pair_losses", 0, traces
    )
    if wins + losses > traces:
        raise RenderError("{} semantic discordance exceeds paired traces".format(label))
    if cap_nontrivial - exact_nontrivial != wins - losses:
        raise RenderError("{} semantic counts do not conserve paired discordance".format(label))
    semantic_both = cap_nontrivial - wins
    if semantic_both != exact_nontrivial - losses:
        raise RenderError("{} semantic shared-positive count is inconsistent".format(label))
    semantic_neither = traces - wins - losses - semantic_both
    if semantic_both < 0 or semantic_neither < 0:
        raise RenderError("{} semantic contingency table is impossible".format(label))
    observed = wins + losses > 0
    if value["semantic_selection_difference_observed"] is not observed:
        raise RenderError("{}.semantic_selection_difference_observed changed".format(label))
    certified = traces == tasks and raw == tasks and observed
    if (value["status"] == "certified") is not certified:
        raise RenderError("{}.status disagrees with certification denominators".format(label))
    expected_policy = (
        "requires-all-pairs-complete-all-raw-pools-identical-and-at-"
        "least-one-paired-semantic-nontrivial-difference/v1"
    )
    if value["claim_policy"] != expected_policy:
        raise RenderError("{}.claim_policy changed".format(label))
    return {
        "status": value["status"],
        "traces": traces,
        "raw": raw,
        "cap_nontrivial": cap_nontrivial,
        "exact_nontrivial": exact_nontrivial,
        "semantic_wins": wins,
        "semantic_losses": losses,
        "semantic_both": semantic_both,
        "semantic_neither": semantic_neither,
    }


def _validate_contrast(value, label, tasks, role):
    keys = {
        "role",
        "population",
        "equal_domain_macro_coverage",
        "task_micro_discordance",
        "mechanism",
        "per_domain",
    }
    value = _mapping(value, label, keys)
    if value["role"] != role:
        raise RenderError("{}.role changed".format(label))
    population = _mapping(value["population"], label + ".population", {"tasks", "domains"})
    _integer(population["tasks"], label + ".population.tasks", tasks, tasks)
    _integer(population["domains"], label + ".population.domains", DOMAINS, DOMAINS)

    macro = _mapping(
        value["equal_domain_macro_coverage"],
        label + ".equal_domain_macro_coverage",
        {"cap", "exact", "cap_minus_exact", "domain_weighting"},
    )
    if macro["domain_weighting"] != "each-domain-equal/v1":
        raise RenderError("{} macro domain weighting changed".format(label))
    cap_macro = _validate_fraction(macro["cap"], label + ".macro.cap", DOMAINS)
    exact_macro = _validate_fraction(macro["exact"], label + ".macro.exact", DOMAINS)
    difference = _validate_fraction(
        macro["cap_minus_exact"], label + ".macro.cap_minus_exact", DOMAINS
    )
    if not (0 <= cap_macro <= 1 and 0 <= exact_macro <= 1):
        raise RenderError("{} macro coverage is outside [0,1]".format(label))
    if difference != cap_macro - exact_macro:
        raise RenderError("{} macro difference does not conserve".format(label))

    per_domain = _sequence(value["per_domain"], label + ".per_domain", DOMAINS)
    names = set()
    domain_rows = []
    task_total = cap_total = exact_total = 0
    recomputed_cap = Fraction(0)
    recomputed_exact = Fraction(0)
    for index, entry in enumerate(per_domain):
        prefix = "{}.per_domain[{}]".format(label, index)
        entry = _mapping(
            entry,
            prefix,
            {"domain", "tasks", "cap_solved", "exact_solved", "cap_minus_exact_rate"},
        )
        domain = entry["domain"]
        if type(domain) is not str or not domain or len(domain) > 128 or any(
            ord(character) < 32 for character in domain
        ):
            raise RenderError("{}.domain is invalid".format(prefix))
        if domain in names:
            raise RenderError("{} contains duplicate domain {!r}".format(label, domain))
        names.add(domain)
        count = _integer(entry["tasks"], prefix + ".tasks", 1, tasks)
        cap_solved = _integer(entry["cap_solved"], prefix + ".cap_solved", 0, count)
        exact_solved = _integer(entry["exact_solved"], prefix + ".exact_solved", 0, count)
        domain_difference = _validate_fraction(
            entry["cap_minus_exact_rate"], prefix + ".cap_minus_exact_rate"
        )
        expected_difference = Fraction(cap_solved - exact_solved, count)
        if domain_difference != expected_difference:
            raise RenderError("{} cap-minus-exact rate changed".format(prefix))
        task_total += count
        cap_total += cap_solved
        exact_total += exact_solved
        recomputed_cap += Fraction(cap_solved, count)
        recomputed_exact += Fraction(exact_solved, count)
        domain_rows.append(
            {
                "domain": domain,
                "tasks": count,
                "cap_solved": cap_solved,
                "exact_solved": exact_solved,
            }
        )
    if task_total != tasks:
        raise RenderError("{} per-domain task counts do not conserve".format(label))
    recomputed_cap /= DOMAINS
    recomputed_exact /= DOMAINS
    if cap_macro != recomputed_cap or exact_macro != recomputed_exact:
        raise RenderError("{} macro coverage disagrees with per-domain rows".format(label))

    micro = _mapping(
        value["task_micro_discordance"],
        label + ".task_micro_discordance",
        {
            "cap_wins",
            "cap_losses",
            "wins_minus_losses",
            "discordant",
            "both_solved",
            "both_unsolved",
            "task_pairs",
        },
    )
    wins = _integer(micro["cap_wins"], label + ".micro.cap_wins", 0, tasks)
    losses = _integer(micro["cap_losses"], label + ".micro.cap_losses", 0, tasks)
    both_solved = _integer(micro["both_solved"], label + ".micro.both_solved", 0, tasks)
    both_unsolved = _integer(
        micro["both_unsolved"], label + ".micro.both_unsolved", 0, tasks
    )
    _integer(micro["task_pairs"], label + ".micro.task_pairs", tasks, tasks)
    wins_minus_losses = _integer(
        micro["wins_minus_losses"], label + ".micro.wins_minus_losses", -tasks, tasks
    )
    discordant = _integer(
        micro["discordant"], label + ".micro.discordant", 0, tasks
    )
    if wins_minus_losses != wins - losses:
        raise RenderError("{}.micro.wins_minus_losses changed".format(label))
    if discordant != wins + losses:
        raise RenderError("{}.micro.discordant changed".format(label))
    if wins + losses + both_solved + both_unsolved != tasks:
        raise RenderError("{} task discordance does not conserve".format(label))
    if cap_total != wins + both_solved or exact_total != losses + both_solved:
        raise RenderError("{} micro coverage disagrees with per-domain rows".format(label))

    mechanism = _validate_mechanism(value["mechanism"], label + ".mechanism", tasks)
    return {
        "value": value,
        "cap_macro": cap_macro,
        "exact_macro": exact_macro,
        "difference": difference,
        "cap_solved": cap_total,
        "exact_solved": exact_total,
        "wins": wins,
        "losses": losses,
        "both_solved": both_solved,
        "both_unsolved": both_unsolved,
        "mechanism": mechanism,
        "domain_rows": domain_rows,
    }


def _validate_selector_summary(value, label, tasks, config):
    keys = {
        "eligible_cells",
        "complete_certified_traces",
        "semantic_nontrivial",
        "effective_cap_histogram",
        "selected_first_provenance_source",
        "pattern_size",
        "W",
        "A",
        "T",
        "U",
        "V",
    }
    value = _mapping(value, label, keys)
    _integer(value["eligible_cells"], label + ".eligible_cells", tasks, tasks)
    traces = _integer(
        value["complete_certified_traces"], label + ".complete_certified_traces", 0, tasks
    )
    semantic = _integer(value["semantic_nontrivial"], label + ".semantic_nontrivial", 0, traces)
    histogram = _mapping(value["effective_cap_histogram"], label + ".effective_cap_histogram")
    if any(key not in CAP_KEYS for key in histogram):
        raise RenderError("{} contains an unexpected effective cap".format(label))
    if config == EXACT and any(key != "exact" for key in histogram):
        raise RenderError("{} exact selector contains a finite cap".format(label))
    histogram_total = sum(
        _integer(count, "{}.effective_cap_histogram.{}".format(label, key), 0, traces)
        for key, count in histogram.items()
    )
    if histogram_total != traces:
        raise RenderError("{} effective-cap histogram does not conserve".format(label))
    sources = _mapping(
        value["selected_first_provenance_source"],
        label + ".selected_first_provenance_source",
        set(SELECTOR_SOURCES),
    )
    if sum(
        _integer(sources[source], "{}.source.{}".format(label, source), 0, traces)
        for source in SELECTOR_SOURCES
    ) != traces:
        raise RenderError("{} source histogram does not conserve".format(label))
    summaries = {
        "pattern_size": _validate_count_summary(
            value["pattern_size"], label + ".pattern_size", traces, traces
        ),
        "W": _validate_count_summary(value["W"], label + ".W", traces, traces),
        "A": _validate_count_summary(value["A"], label + ".A", traces),
        "T": _validate_count_summary(value["T"], label + ".T", traces),
        "U": _validate_count_summary(value["U"], label + ".U", traces, traces),
        "V": _validate_count_summary(value["V"], label + ".V", traces),
    }
    if traces and (value["W"]["minimum"] < 1 or value["W"]["maximum"] > WIDTH_BUDGET):
        raise RenderError("{} selected width exceeds the frozen K=8 budget".format(label))
    if (
        traces > 0
        and summaries["A"]["observed"]
        == summaries["T"]["observed"]
        == summaries["U"]["observed"]
        == traces
    ):
        if summaries["U"]["total"] != (
            summaries["A"]["total"] + summaries["T"]["total"]
        ):
            raise RenderError("{} U total does not equal A plus T".format(label))
    return {
        "traces": traces,
        "semantic": semantic,
        "histogram": {
            key: _integer(
                count,
                "{}.effective_cap_histogram.{}".format(label, key),
                0,
                traces,
            )
            for key, count in histogram.items()
        },
        "sources": {
            source: _integer(
                sources[source], "{}.source.{}".format(label, source), 0, traces
            )
            for source in SELECTOR_SOURCES
        },
        "summaries": summaries,
    }


def _validate_total_ratio(value, label, tasks, integer_totals=False):
    value = _mapping(
        value,
        label,
        {"eligible_pair_count", "candidate_total", "reference_total", "candidate_over_reference"},
    )
    pairs = _integer(value["eligible_pair_count"], label + ".eligible_pair_count", 0, tasks)
    if integer_totals:
        candidate = _integer(value["candidate_total"], label + ".candidate_total")
        reference = _integer(value["reference_total"], label + ".reference_total")
    else:
        candidate = _number(value["candidate_total"], label + ".candidate_total", 0)
        reference = _number(value["reference_total"], label + ".reference_total", 0)
    if pairs == 0 and (candidate != 0 or reference != 0):
        raise RenderError("{} zero-pair totals must be zero".format(label))
    expected = None if reference == 0 else candidate / reference
    if expected is None:
        if value["candidate_over_reference"] is not None:
            raise RenderError("{} ratio must be null for zero reference total".format(label))
    else:
        _close(value["candidate_over_reference"], expected, label + ".candidate_over_reference")
    return {"pairs": pairs, "candidate": candidate, "reference": reference, "ratio": expected}


def _validate_secondary_scope(value, label, tasks, contrast):
    value = _mapping(value, label, {"tasks", "selector_summary", "paired_operational"})
    _integer(value["tasks"], label + ".tasks", tasks, tasks)
    selectors = _mapping(value["selector_summary"], label + ".selector_summary", {EXACT, CAP})
    exact = _validate_selector_summary(selectors[EXACT], label + ".selector.exact", tasks, EXACT)
    cap = _validate_selector_summary(selectors[CAP], label + ".selector.cap", tasks, CAP)
    mechanism = contrast["mechanism"]
    if mechanism["status"] == "certified":
        if exact["traces"] != tasks or cap["traces"] != tasks:
            raise RenderError("{} certified mechanism lacks complete selector summaries".format(label))
        if exact["semantic"] != mechanism["exact_nontrivial"]:
            raise RenderError("{} exact nontrivial count disagrees with mechanism".format(label))
        if cap["semantic"] != mechanism["cap_nontrivial"]:
            raise RenderError("{} cap nontrivial count disagrees with mechanism".format(label))

    operational = _mapping(
        value["paired_operational"],
        label + ".paired_operational",
        {
            "micro_par2_seconds",
            "jointly_solved_planner_cpu",
            "complete_certified_image_time",
            "complete_certified_expanded_bdd_nodes",
            "observed_completed_construction_time",
        },
    )
    par2 = _mapping(
        operational["micro_par2_seconds"],
        label + ".micro_par2_seconds",
        {
            "fixed_task_denominator",
            "candidate_solved",
            "reference_solved",
            "candidate_solved_planner_cpu_total_seconds",
            "reference_solved_planner_cpu_total_seconds",
            "candidate",
            "reference",
            "candidate_minus_reference",
        },
    )
    _integer(
        par2["fixed_task_denominator"],
        label + ".par2.fixed_task_denominator",
        tasks,
        tasks,
    )
    candidate_solved = _integer(
        par2["candidate_solved"], label + ".par2.candidate_solved", 0, tasks
    )
    reference_solved = _integer(
        par2["reference_solved"], label + ".par2.reference_solved", 0, tasks
    )
    if candidate_solved != contrast["cap_solved"]:
        raise RenderError("{} candidate PAR2 solved count disagrees with coverage".format(label))
    if reference_solved != contrast["exact_solved"]:
        raise RenderError("{} reference PAR2 solved count disagrees with coverage".format(label))
    candidate_runtime_total = _number(
        par2["candidate_solved_planner_cpu_total_seconds"],
        label + ".par2.candidate_solved_runtime_total",
        0,
        PAR2_PENALTY * candidate_solved,
    )
    reference_runtime_total = _number(
        par2["reference_solved_planner_cpu_total_seconds"],
        label + ".par2.reference_solved_runtime_total",
        0,
        PAR2_PENALTY * reference_solved,
    )
    candidate_par2 = _number(par2["candidate"], label + ".par2.candidate", 0, PAR2_PENALTY)
    reference_par2 = _number(par2["reference"], label + ".par2.reference", 0, PAR2_PENALTY)
    expected_candidate_par2 = (
        candidate_runtime_total + PAR2_PENALTY * (tasks - candidate_solved)
    ) / tasks
    expected_reference_par2 = (
        reference_runtime_total + PAR2_PENALTY * (tasks - reference_solved)
    ) / tasks
    if candidate_par2 != expected_candidate_par2:
        raise RenderError("{}.par2.candidate arithmetic changed".format(label))
    if reference_par2 != expected_reference_par2:
        raise RenderError("{}.par2.reference arithmetic changed".format(label))
    par2_difference = _number(
        par2["candidate_minus_reference"],
        label + ".par2.candidate_minus_reference",
    )
    if par2_difference != candidate_par2 - reference_par2:
        raise RenderError(
            "{}.par2.candidate_minus_reference arithmetic changed".format(label)
        )
    cpu = _mapping(
        operational["jointly_solved_planner_cpu"],
        label + ".jointly_solved_planner_cpu",
        {
            "jointly_solved_pair_count",
            "eligible_pair_count",
            "excluded_nonpositive_pair_count",
            "candidate_over_reference",
        },
    )
    joint = _integer(cpu["jointly_solved_pair_count"], label + ".cpu.jointly_solved", 0, tasks)
    eligible = _integer(cpu["eligible_pair_count"], label + ".cpu.eligible", 0, joint)
    excluded = _integer(cpu["excluded_nonpositive_pair_count"], label + ".cpu.excluded", 0, joint)
    if eligible + excluded != joint:
        raise RenderError("{} CPU eligible/excluded counts do not conserve".format(label))
    if joint != contrast["both_solved"]:
        raise RenderError("{} jointly solved CPU count disagrees with coverage".format(label))
    if eligible == 0:
        if cpu["candidate_over_reference"] is not None:
            raise RenderError("{} CPU ratio must be null without positive pairs".format(label))
        cpu_ratio = None
    else:
        cpu_ratio = _number(
            cpu["candidate_over_reference"], label + ".cpu.candidate_over_reference", 0
        )
        if cpu_ratio == 0:
            raise RenderError("{} CPU geometric-mean ratio must be positive".format(label))
    image = _validate_total_ratio(
        operational["complete_certified_image_time"], label + ".image_time", tasks
    )
    effort = _validate_total_ratio(
        operational["complete_certified_expanded_bdd_nodes"],
        label + ".expanded_bdd_nodes",
        tasks,
        integer_totals=True,
    )
    if image["pairs"] != effort["pairs"]:
        raise RenderError("{} image and effort certified pair sets differ".format(label))
    construction = _validate_total_ratio(
        operational["observed_completed_construction_time"],
        label + ".construction_time",
        tasks,
    )
    return {
        "value": value,
        "candidate_par2": candidate_par2,
        "reference_par2": reference_par2,
        "par2_difference": candidate_par2 - reference_par2,
        "par2": {
            "candidate_solved": candidate_solved,
            "reference_solved": reference_solved,
            "candidate_runtime_total": candidate_runtime_total,
            "reference_runtime_total": reference_runtime_total,
        },
        "cpu": {"joint": joint, "eligible": eligible, "excluded": excluded, "ratio": cpu_ratio},
        "image": image,
        "effort": effort,
        "construction": construction,
        "exact_selector": exact,
        "cap_selector": cap,
    }


def _validate_config(value, index):
    label, suffix, paper_label, role = CONFIGS[index]
    prefix = "descriptive_full_census_configs[{}]".format(index)
    value = _mapping(
        value,
        prefix,
        {
            "label",
            "role",
            "cells",
            "solved",
            "coverage_rate",
            "micro_par2_seconds",
            "solved_planner_cpu_seconds",
            "completed_construction_seconds",
        },
    )
    if value["label"] != label:
        raise RenderError("{}.label changed".format(prefix))
    if value["role"] != role:
        raise RenderError("{}.role changed".format(prefix))
    _integer(value["cells"], prefix + ".cells", TASKS, TASKS)
    solved = _integer(value["solved"], prefix + ".solved", 0, TASKS)
    _close(value["coverage_rate"], solved / TASKS, prefix + ".coverage_rate")
    par2 = _number(value["micro_par2_seconds"], prefix + ".micro_par2_seconds", 0, PAR2_PENALTY)
    solved_cpu_summary = value["solved_planner_cpu_seconds"]
    _validate_summary(
        solved_cpu_summary,
        prefix + ".solved_planner_cpu_seconds",
        TASKS,
        solved,
    )
    solved_runtime_total = (
        0.0
        if solved == 0
        else _number(
            solved_cpu_summary["total"],
            prefix + ".solved_planner_cpu_seconds.total",
            0,
            PAR2_PENALTY * solved,
        )
    )
    expected_par2 = (
        solved_runtime_total + PAR2_PENALTY * (TASKS - solved)
    ) / TASKS
    if par2 != expected_par2:
        raise RenderError("{}.micro_par2_seconds arithmetic changed".format(prefix))
    construction_observed = _validate_summary(
        value["completed_construction_seconds"],
        prefix + ".completed_construction_seconds",
        TASKS,
    )
    construction_total = (
        None
        if construction_observed == 0
        else _number(
            value["completed_construction_seconds"]["total"],
            prefix + ".completed_construction_seconds.total",
            0,
        )
    )
    return {
        "value": value,
        "label": label,
        "suffix": suffix,
        "paper_label": paper_label,
        "solved": solved,
        "par2": par2,
        "solved_runtime_total": solved_runtime_total,
        "construction": {
            "observed": construction_observed,
            "total": construction_total,
        },
    }


def _require_count_subset(primary, census, label):
    if primary > census:
        raise RenderError("{} primary count exceeds full census".format(label))


def _require_total_subset(primary, census, label):
    if primary > census and not math.isclose(
        primary, census, rel_tol=1e-12, abs_tol=1e-12
    ):
        raise RenderError("{} primary total exceeds full census".format(label))


def _validate_count_summary_subset(primary, census, label):
    _require_count_subset(primary["observed"], census["observed"], label + ".observed")
    if primary["observed"] == 0:
        return
    if census["observed"] == 0:
        raise RenderError("{} primary observations lack census observations".format(label))
    if census["minimum"] > primary["minimum"]:
        raise RenderError("{} census minimum excludes a primary value".format(label))
    if primary["maximum"] > census["maximum"]:
        raise RenderError("{} census maximum excludes a primary value".format(label))
    _require_count_subset(primary["total"], census["total"], label + ".total")


def _validate_ratio_subset(primary, census, label):
    _require_count_subset(primary["pairs"], census["pairs"], label + ".pairs")
    _require_total_subset(primary["candidate"], census["candidate"], label + ".candidate")
    _require_total_subset(primary["reference"], census["reference"], label + ".reference")


def _validate_primary_subset(primary, census, primary_secondary, census_secondary):
    for index, (primary_domain, census_domain) in enumerate(
        zip(primary["domain_rows"], census["domain_rows"])
    ):
        prefix = "primary-subset.per_domain[{}]".format(index)
        if primary_domain["domain"] != census_domain["domain"]:
            raise RenderError("{} domain identity differs".format(prefix))
        for field in ("tasks", "cap_solved", "exact_solved"):
            _require_count_subset(
                primary_domain[field], census_domain[field], prefix + "." + field
            )

    for field in ("wins", "losses", "both_solved", "both_unsolved"):
        _require_count_subset(
            primary[field], census[field], "primary-subset.coverage." + field
        )

    for field in (
        "traces",
        "raw",
        "cap_nontrivial",
        "exact_nontrivial",
        "semantic_wins",
        "semantic_losses",
        "semantic_both",
        "semantic_neither",
    ):
        _require_count_subset(
            primary["mechanism"][field],
            census["mechanism"][field],
            "primary-subset.mechanism." + field,
        )

    for config, paper_label in ((EXACT, "exact"), (CAP, "cap")):
        primary_selector = (
            primary_secondary["exact_selector"]
            if config == EXACT
            else primary_secondary["cap_selector"]
        )
        census_selector = (
            census_secondary["exact_selector"]
            if config == EXACT
            else census_secondary["cap_selector"]
        )
        prefix = "primary-subset.selector." + paper_label
        for field in ("traces", "semantic"):
            _require_count_subset(
                primary_selector[field], census_selector[field], prefix + "." + field
            )
        for key in CAP_KEYS:
            _require_count_subset(
                primary_selector["histogram"].get(key, 0),
                census_selector["histogram"].get(key, 0),
                prefix + ".cap_histogram." + key,
            )
        for source in SELECTOR_SOURCES:
            _require_count_subset(
                primary_selector["sources"][source],
                census_selector["sources"][source],
                prefix + ".source." + source,
            )
        for field in ("pattern_size", "W", "A", "T", "U", "V"):
            _validate_count_summary_subset(
                primary_selector["summaries"][field],
                census_selector["summaries"][field],
                prefix + "." + field,
            )

    for field in ("candidate_solved", "reference_solved"):
        _require_count_subset(
            primary_secondary["par2"][field],
            census_secondary["par2"][field],
            "primary-subset.par2." + field,
        )
    for field in ("candidate_runtime_total", "reference_runtime_total"):
        _require_total_subset(
            primary_secondary["par2"][field],
            census_secondary["par2"][field],
            "primary-subset.par2." + field,
        )
    for field in ("joint", "eligible", "excluded"):
        _require_count_subset(
            primary_secondary["cpu"][field],
            census_secondary["cpu"][field],
            "primary-subset.cpu." + field,
        )
    for field in ("image", "effort", "construction"):
        _validate_ratio_subset(
            primary_secondary[field],
            census_secondary[field],
            "primary-subset." + field,
        )


def _validate_analysis_with_pins(value, analysis_sha256, pins):
    _require_sha256(analysis_sha256, "analysis artifact SHA-256", pins["analysis_sha256"])
    raw = canonical_json(value).encode("ascii") + b"\n"
    if sha256_bytes(raw) != analysis_sha256:
        raise RenderError("in-memory canonical analysis disagrees with claimed artifact digest")
    value = _mapping(value, "analysis", TOP_KEYS)
    if value["schema"] != ANALYSIS_SCHEMA:
        raise RenderError("analysis.schema changed")
    if value["analysis_protocol"] != ANALYSIS_PROTOCOL:
        raise RenderError("analysis.analysis_protocol changed")
    if sha256_json(value["predeclaration"]) != EXPECTED_PREDECLARATION_SHA256:
        raise RenderError("analysis predeclaration changed")
    _validate_execution(value["execution"], pins)

    contract = _mapping(
        value["secondary_descriptive_contract"],
        "secondary_descriptive_contract",
        {"sha256", "contract"},
    )
    _require_sha256(
        contract["sha256"],
        "secondary_descriptive_contract.sha256",
        EXPECTED_SECONDARY_CONTRACT_SHA256,
    )
    if sha256_json(contract["contract"]) != EXPECTED_SECONDARY_CONTRACT_SHA256:
        raise RenderError("secondary descriptive contract payload changed")

    primary = _validate_contrast(
        value["primary"], "primary", PRIMARY_TASKS, "primary-development-complement"
    )
    sensitivity = _validate_contrast(
        value["full_census_sensitivity"],
        "full_census_sensitivity",
        TASKS,
        "prespecified-scope-sensitivity",
    )
    secondary = _mapping(
        value["secondary_descriptive"],
        "secondary_descriptive",
        {"primary_development_complement", "full_census_sensitivity"},
    )
    primary_secondary = _validate_secondary_scope(
        secondary["primary_development_complement"],
        "secondary.primary_development_complement",
        PRIMARY_TASKS,
        primary,
    )
    sensitivity_secondary = _validate_secondary_scope(
        secondary["full_census_sensitivity"],
        "secondary.full_census_sensitivity",
        TASKS,
        sensitivity,
    )
    _validate_primary_subset(
        primary, sensitivity, primary_secondary, sensitivity_secondary
    )
    configs = [
        _validate_config(item, index)
        for index, item in enumerate(
            _sequence(
                value["descriptive_full_census_configs"],
                "descriptive_full_census_configs",
                CONFIG_COUNT,
            )
        )
    ]
    by_label = {item["label"]: item for item in configs}
    if len(by_label) != CONFIG_COUNT:
        raise RenderError("descriptive config labels are not unique")
    if by_label[CAP]["solved"] != sensitivity["cap_solved"]:
        raise RenderError("full cap solved count disagrees with sensitivity contrast")
    if by_label[EXACT]["solved"] != sensitivity["exact_solved"]:
        raise RenderError("full exact solved count disagrees with sensitivity contrast")
    if by_label[CAP]["par2"] != sensitivity_secondary["candidate_par2"]:
        raise RenderError("full cap PAR2 cross-check changed")
    if by_label[EXACT]["par2"] != sensitivity_secondary["reference_par2"]:
        raise RenderError("full exact PAR2 cross-check changed")
    if by_label[CAP]["solved_runtime_total"] != (
        sensitivity_secondary["par2"]["candidate_runtime_total"]
    ):
        raise RenderError("full cap solved-runtime total cross-check changed")
    if by_label[EXACT]["solved_runtime_total"] != (
        sensitivity_secondary["par2"]["reference_runtime_total"]
    ):
        raise RenderError("full exact solved-runtime total cross-check changed")

    inference = _mapping(
        value["inference"],
        "inference",
        {"confidence_intervals", "p_values", "fixed_population_census"},
    )
    if (
        inference["confidence_intervals"] is not None
        or inference["p_values"] is not None
        or inference["fixed_population_census"] is not True
    ):
        raise RenderError("inference policy changed")
    return {
        "primary": primary,
        "sensitivity": sensitivity,
        "primary_secondary": primary_secondary,
        "sensitivity_secondary": sensitivity_secondary,
        "configs": configs,
    }


def validate_analysis(value, analysis_sha256):
    return _validate_analysis_with_pins(value, analysis_sha256, _production_pins())


def _decimal(value, places=3, trim=True):
    try:
        number = Decimal(str(_number(value, "rendered numeric value")))
        quantum = Decimal(1).scaleb(-places)
        rendered = format(number.quantize(quantum, rounding=ROUND_HALF_UP), "f")
    except InvalidOperation as err:
        raise RenderError("rendered number exceeds the decimal formatting bound") from err
    if trim and "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    if rendered == "-0":
        rendered = "0"
    if len(rendered) > 64:
        raise RenderError("rendered number is unexpectedly long")
    return rendered


def _percent(value, places=2, signed=False):
    rendered = _decimal(float(value * 100), places)
    if signed and not rendered.startswith("-") and rendered != "0":
        rendered = "+" + rendered
    return rendered


def _ratio(value):
    return "--" if value is None else _decimal(value, 3)


def _tex_escape(value):
    """Escape one bounded, plain-ASCII table label for TeX."""
    if type(value) is not str:
        raise RenderError("TeX text must be a string")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as err:
        raise RenderError("TeX text must be plain ASCII") from err
    if len(encoded) > MAX_TEX_CELL_BYTES:
        raise RenderError("TeX text is too large")
    if any(byte < 32 or byte == 127 for byte in encoded):
        raise RenderError("TeX text contains a control character")
    replacements = {
        "\\": r"\textbackslash{}",
        "{": r"\{",
        "}": r"\}",
        "#": r"\#",
        "$": r"\$",
        "%": r"\%",
        "&": r"\&",
        "_": r"\_",
        "^": r"\textasciicircum{}",
        "~": r"\textasciitilde{}",
    }
    return "".join(replacements.get(character, character) for character in value)


def _macro(name, content):
    if MACRO_RE.fullmatch(name) is None:
        raise RenderError("invalid TeX macro name {!r}".format(name))
    if type(content) is not str or len(content.encode("utf-8")) > MAX_TEX_MACRO_BYTES:
        raise RenderError("TeX macro {} is too large".format(name))
    return "\\newcommand{{\\{}}}{{{}}}".format(name, content)


def _rows_macro(name, rows, columns, expected_rows):
    """Render a bounded table-row macro with an exact structural contract."""
    if type(columns) is not int or columns < 1 or columns > 16:
        raise RenderError("TeX table column count is invalid")
    if (
        type(expected_rows) is not int
        or expected_rows < 1
        or expected_rows > MAX_TEX_TABLE_ROWS
    ):
        raise RenderError("TeX table row count is invalid")
    if type(rows) not in (list, tuple) or len(rows) != expected_rows:
        raise RenderError("TeX table {} row count changed".format(name))
    rendered = []
    for index, row in enumerate(rows):
        if type(row) not in (list, tuple) or len(row) != columns:
            raise RenderError(
                "TeX table {} row {} column count changed".format(name, index)
            )
        cells = []
        for cell in row:
            if type(cell) is not str:
                raise RenderError("TeX table {} contains a non-string cell".format(name))
            if "\n" in cell or "\r" in cell:
                raise RenderError("TeX table {} contains a multiline cell".format(name))
            if len(cell.encode("utf-8")) > MAX_TEX_CELL_BYTES:
                raise RenderError("TeX table {} contains an oversized cell".format(name))
            cells.append(cell)
        rendered.append(" & ".join(cells) + r" \\")
    return _macro(name, "%\n" + "\n".join(rendered))


def _render_tex_with_pins(value, analysis_sha256, pins):
    data = _validate_analysis_with_pins(value, analysis_sha256, pins)
    primary = data["primary"]
    sensitivity = data["sensitivity"]
    psecondary = data["primary_secondary"]
    ssecondary = data["sensitivity_secondary"]

    lines = [
        "% Generated from a reviewed canonical focused full analysis artifact.",
        "% Scientific aggregates only; provenance remains in the artifact and sidecar.",
        _macro("CapFullTasks", str(TASKS)),
        _macro("CapPrimaryTasks", str(PRIMARY_TASKS)),
        _macro("CapFullDomains", str(DOMAINS)),
        _macro("CapFullCells", str(CELLS)),
        _macro("CapPrimaryMacroFixedDomains", str(DOMAINS)),
        _macro("CapPrimaryExactMacroNumerator", str(primary["exact_macro"].numerator)),
        _macro("CapPrimaryExactMacroDenominator", str(primary["exact_macro"].denominator)),
        _macro("CapPrimaryCapMacroNumerator", str(primary["cap_macro"].numerator)),
        _macro("CapPrimaryCapMacroDenominator", str(primary["cap_macro"].denominator)),
        _macro("CapPrimaryMacroDeltaNumerator", str(primary["difference"].numerator)),
        _macro("CapPrimaryMacroDeltaDenominator", str(primary["difference"].denominator)),
        _macro("CapPrimaryExactMacroPercent", _percent(primary["exact_macro"])),
        _macro("CapPrimaryCapMacroPercent", _percent(primary["cap_macro"])),
        _macro("CapPrimaryMacroDeltaPoints", _percent(primary["difference"], signed=True)),
        _macro("CapPrimaryExactSolved", str(primary["exact_solved"])),
        _macro("CapPrimaryCapSolved", str(primary["cap_solved"])),
        _macro("CapPrimaryWins", str(primary["wins"])),
        _macro("CapPrimaryLosses", str(primary["losses"])),
        _macro("CapPrimaryBothSolved", str(primary["both_solved"])),
        _macro("CapPrimaryBothUnsolved", str(primary["both_unsolved"])),
        _macro("CapPrimaryTracePairs", str(primary["mechanism"]["traces"])),
        _macro("CapPrimaryRawPoolPairs", str(primary["mechanism"]["raw"])),
        _macro("CapPrimaryExactNontrivial", str(primary["mechanism"]["exact_nontrivial"])),
        _macro("CapPrimaryCapNontrivial", str(primary["mechanism"]["cap_nontrivial"])),
        _macro("CapPrimarySemanticWins", str(primary["mechanism"]["semantic_wins"])),
        _macro("CapPrimarySemanticLosses", str(primary["mechanism"]["semantic_losses"])),
        _macro("CapPrimaryMechanismStatus", primary["mechanism"]["status"]),
        _macro("CapCensusMacroFixedDomains", str(DOMAINS)),
        _macro("CapCensusExactMacroNumerator", str(sensitivity["exact_macro"].numerator)),
        _macro("CapCensusExactMacroDenominator", str(sensitivity["exact_macro"].denominator)),
        _macro("CapCensusCapMacroNumerator", str(sensitivity["cap_macro"].numerator)),
        _macro("CapCensusCapMacroDenominator", str(sensitivity["cap_macro"].denominator)),
        _macro("CapCensusMacroDeltaNumerator", str(sensitivity["difference"].numerator)),
        _macro("CapCensusMacroDeltaDenominator", str(sensitivity["difference"].denominator)),
        _macro("CapCensusExactMacroPercent", _percent(sensitivity["exact_macro"])),
        _macro("CapCensusCapMacroPercent", _percent(sensitivity["cap_macro"])),
        _macro("CapCensusMacroDeltaPoints", _percent(sensitivity["difference"], signed=True)),
        _macro("CapCensusWins", str(sensitivity["wins"])),
        _macro("CapCensusLosses", str(sensitivity["losses"])),
    ]

    for config in data["configs"]:
        lines.extend(
            [
                _macro("CapFull{}Solved".format(config["suffix"]), str(config["solved"])),
                _macro("CapFull{}ParTwo".format(config["suffix"]), _decimal(config["par2"])),
            ]
        )

    context_rows = "\n".join(
        "{} & {}/{} & {} \\\\".format(
            config["paper_label"], config["solved"], TASKS, _decimal(config["par2"])
        )
        for config in data["configs"]
    )
    primary_rows = "\n".join(
        [
            "Exact selector $K=8$ & {} & {}/{} \\\\".format(
                _percent(primary["exact_macro"]), primary["exact_solved"], PRIMARY_TASKS
            ),
            "Cap-aware selector $K=8$ & {} & {}/{} \\\\".format(
                _percent(primary["cap_macro"]), primary["cap_solved"], PRIMARY_TASKS
            ),
            "Cap-aware minus exact & {} pp & -- \\\\".format(
                _percent(primary["difference"], signed=True)
            ),
        ]
    )
    mechanism_rows = "\n".join(
        [
            "Complete certified trace pairs & {}/{} \\\\".format(
                primary["mechanism"]["traces"], PRIMARY_TASKS
            ),
            "Identical raw-pool pairs & {}/{} \\\\".format(
                primary["mechanism"]["raw"], PRIMARY_TASKS
            ),
            "Semantic-nontrivial, exact & {}/{} \\\\".format(
                primary["mechanism"]["exact_nontrivial"], primary["mechanism"]["traces"]
            ),
            "Semantic-nontrivial, cap-aware & {}/{} \\\\".format(
                primary["mechanism"]["cap_nontrivial"], primary["mechanism"]["traces"]
            ),
        ]
    )

    # Supplement interfaces (columns are stable and intentionally header-free):
    # CapCensusContrastRows: selector, equal-domain macro coverage (%), solved/tasks.
    census_contrast_rows = [
        (
            "Exact selector $K=8$",
            _percent(sensitivity["exact_macro"]),
            "{}/{}".format(sensitivity["exact_solved"], TASKS),
        ),
        (
            "Cap-aware selector $K=8$",
            _percent(sensitivity["cap_macro"]),
            "{}/{}".format(sensitivity["cap_solved"], TASKS),
        ),
        (
            _tex_escape("Cap-aware minus exact"),
            _percent(sensitivity["difference"], signed=True) + " pp",
            "--",
        ),
    ]

    # CapFullConstructionRows: configuration, observed/tasks, total seconds.
    full_construction_rows = []
    for config in data["configs"]:
        construction = config["construction"]
        full_construction_rows.append(
            (
                config["paper_label"],
                "{}/{}".format(construction["observed"], TASKS),
                "--"
                if construction["total"] is None
                else _decimal(construction["total"]),
            )
        )

    scope_specs = (
        ("Primary", psecondary),
        ("Full census", ssecondary),
    )
    selector_specs = (
        ("Exact", "exact_selector"),
        ("Cap-aware", "cap_selector"),
    )

    # CapSelectorSummaryRows: scope, selector, metric, observed/traces,
    # minimum, median, maximum, total.  Empty summaries render explicit dashes.
    selector_summary_rows = []
    for scope_label, scope in scope_specs:
        for selector_label, selector_key in selector_specs:
            selector = scope[selector_key]
            for metric_key, metric_label in SELECTOR_METRICS:
                summary = selector["summaries"][metric_key]
                if summary["observed"] == 0:
                    statistics = ("--", "--", "--", "--")
                else:
                    statistics = (
                        str(summary["minimum"]),
                        _decimal(summary["median"], places=1),
                        str(summary["maximum"]),
                        str(summary["total"]),
                    )
                selector_summary_rows.append(
                    (
                        _tex_escape(scope_label),
                        _tex_escape(selector_label),
                        _tex_escape(metric_label),
                        "{}/{}".format(summary["observed"], selector["traces"]),
                    )
                    + statistics
                )

    # CapSelectorSourceRows: scope, selector, friendly source, count/traces.
    selector_source_rows = []
    for scope_label, scope in scope_specs:
        for selector_label, selector_key in selector_specs:
            selector = scope[selector_key]
            for source in SELECTOR_SOURCES:
                selector_source_rows.append(
                    (
                        _tex_escape(scope_label),
                        _tex_escape(selector_label),
                        _tex_escape(SELECTOR_SOURCE_LABELS[source]),
                        "{}/{}".format(selector["sources"][source], selector["traces"]),
                    )
                )

    # CapEffectiveCapRows: scope, selector, effective cap, count/traces.  Exact
    # selectors have one exact row; cap-aware selectors include every canonical
    # cap category in frozen order, with absent histogram categories shown as zero.
    effective_cap_rows = []
    for scope_label, scope in scope_specs:
        for selector_label, selector_key in selector_specs:
            selector = scope[selector_key]
            keys = ("exact",) if selector_key == "exact_selector" else CAP_KEYS
            for key in keys:
                effective_cap_rows.append(
                    (
                        _tex_escape(scope_label),
                        _tex_escape(selector_label),
                        _tex_escape("Exact" if key == "exact" else key),
                        "{}/{}".format(
                            selector["histogram"].get(key, 0), selector["traces"]
                        ),
                    )
                )

    def secondary_rows(scope):
        return "\n".join(
            [
                "Micro-PAR2 (s) & {} & {} & {} & {} \\\\".format(
                    scope["value"]["tasks"],
                    _decimal(scope["candidate_par2"]),
                    _decimal(scope["reference_par2"]),
                    _decimal(scope["par2_difference"]),
                ),
                "Planner CPU GM ratio & {}/{} & -- & -- & {} \\\\".format(
                    scope["cpu"]["eligible"], scope["cpu"]["joint"], _ratio(scope["cpu"]["ratio"])
                ),
                "Complete-certified image time & {} & {} & {} & {} \\\\".format(
                    scope["image"]["pairs"],
                    _decimal(scope["image"]["candidate"]),
                    _decimal(scope["image"]["reference"]),
                    _ratio(scope["image"]["ratio"]),
                ),
                "Expanded BDD nodes & {} & {} & {} & {} \\\\".format(
                    scope["effort"]["pairs"],
                    str(scope["effort"]["candidate"]),
                    str(scope["effort"]["reference"]),
                    _ratio(scope["effort"]["ratio"]),
                ),
                "Completed construction time & {} & {} & {} & {} \\\\".format(
                    scope["construction"]["pairs"],
                    _decimal(scope["construction"]["candidate"]),
                    _decimal(scope["construction"]["reference"]),
                    _ratio(scope["construction"]["ratio"]),
                ),
            ]
        )

    status_text = (
        "certified"
        if primary["mechanism"]["status"] == "certified"
        else "not certified"
    )
    excluded = psecondary["cpu"]["excluded"]
    excluded_phrase = "{} nonpositive-time pair{} {} excluded".format(
        excluded,
        "" if excluded == 1 else "s",
        "was" if excluded == 1 else "were",
    )
    lines.extend(
        [
            _macro("CapFullContextRows", "%\n" + context_rows),
            _macro("CapPrimaryContrastRows", "%\n" + primary_rows),
            _macro("CapPrimaryMechanismRows", "%\n" + mechanism_rows),
            _macro("CapPrimarySecondaryRows", "%\n" + secondary_rows(psecondary)),
            _macro("CapCensusSecondaryRows", "%\n" + secondary_rows(ssecondary)),
            _rows_macro("CapCensusContrastRows", census_contrast_rows, 3, 3),
            _rows_macro("CapFullConstructionRows", full_construction_rows, 3, CONFIG_COUNT),
            _rows_macro("CapSelectorSummaryRows", selector_summary_rows, 8, 24),
            _rows_macro("CapSelectorSourceRows", selector_source_rows, 4, 20),
            _rows_macro("CapEffectiveCapRows", effective_cap_rows, 4, 24),
            _macro(
                "CapPrimaryText",
                (
                    "On the frozen {}-task development complement, cap-aware and exact "
                    "$K=8$ attained equal-domain macro coverage {}\\% and {}\\%, "
                    "respectively (cap-aware minus exact: {} percentage points across {} "
                    "domains), with {} task-level wins and {} losses."
                ).format(
                    PRIMARY_TASKS,
                    _percent(primary["cap_macro"]),
                    _percent(primary["exact_macro"]),
                    _percent(primary["difference"], signed=True),
                    DOMAINS,
                    primary["wins"],
                    primary["losses"],
                ),
            ),
            _macro(
                "CapMechanismText",
                (
                    "Mechanism attribution was {}: {}/{} paired traces were complete "
                    "and certified, {}/{} raw pools matched, and semantic-nontrivial "
                    "selection occurred in {}/{} cap-aware versus {}/{} exact traces."
                ).format(
                    status_text,
                    primary["mechanism"]["traces"],
                    PRIMARY_TASKS,
                    primary["mechanism"]["raw"],
                    PRIMARY_TASKS,
                    primary["mechanism"]["cap_nontrivial"],
                    primary["mechanism"]["traces"],
                    primary["mechanism"]["exact_nontrivial"],
                    primary["mechanism"]["traces"],
                ),
            ),
            _macro(
                "CapSensitivityText",
                (
                    "On the prespecified all-{} census sensitivity, cap-aware minus exact "
                    "equal-domain macro coverage was {} percentage points, with {} wins "
                    "and {} losses."
                ).format(
                    TASKS,
                    _percent(sensitivity["difference"], signed=True),
                    sensitivity["wins"],
                    sensitivity["losses"],
                ),
            ),
            _macro(
                "CapPrimarySecondaryText",
                (
                    "On the fixed {}-task denominator, cap-aware minus exact micro-PAR2 "
                    "was {} seconds. The cap-aware-over-exact planner-CPU ratio was {} "
                    "on {}/{} positive/jointly-solved pairs; {}. Image-time, expanded-node, "
                    "and construction ratios used "
                    "{}/{}/{} eligible pairs, respectively."
                ).format(
                    PRIMARY_TASKS,
                    _decimal(psecondary["par2_difference"]),
                    _ratio(psecondary["cpu"]["ratio"]),
                    psecondary["cpu"]["eligible"],
                    psecondary["cpu"]["joint"],
                    excluded_phrase,
                    psecondary["image"]["pairs"],
                    psecondary["effort"]["pairs"],
                    psecondary["construction"]["pairs"],
                ),
            ),
            _macro(
                "CapScopeCaveat",
                "The 1,327-task development complement is primary; the all-1,377 census is a prespecified sensitivity. All configuration rows are descriptive fixed-census summaries, with no confidence intervals, $p$-values, reranking, or population generalization.",
            ),
            _macro(
                "CapRatioCaveat",
                "Every ratio is cap-aware over same-$K$ exact, so values below one favor cap-aware on the stated eligible pairs only.",
            ),
            _macro(
                "CapCensoringCaveat",
                "No missing value is imputed: trace, positive-time, complete-certified image/effort, and completed-construction denominators are reported separately.",
            ),
        ]
    )
    names = []
    for line in lines:
        match = re.match(r"\\newcommand\{\\([A-Za-z]+)\}", line)
        if match:
            names.append(match.group(1))
    if len(names) != len(set(names)):
        raise RenderError("generated TeX contains duplicate macro names")
    payload = ("\n".join(lines) + "\n").encode("utf-8")
    if len(payload) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds the bounded output size")
    return payload


def render_tex(value, analysis_sha256):
    pins = _production_pins()
    return _render_tex_with_pins(value, analysis_sha256, pins)


def _validate_write_target(path):
    path = Path(os.path.abspath(str(path)))
    expected = Path(os.path.abspath(str(DEFAULT_OUTPUT)))
    root = Path(os.path.abspath(str(REPOSITORY_ROOT)))
    if path != expected:
        raise RenderError("--write is restricted to the prospective generated-paper path")
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
        if stat.S_ISLNK(info.st_mode):
            raise RenderError("write target contains a symlink component")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(info.st_mode):
            raise RenderError("write-target parent is not a directory")
        if index == len(relative.parts) - 1 and not stat.S_ISREG(info.st_mode):
            raise RenderError("existing write target is not a regular file")
    return path


def _write_atomic(path, payload):
    path = Path(path)
    if type(payload) is not bytes or len(payload) > MAX_TEX_BYTES:
        raise RenderError("atomic payload is invalid or too large")
    try:
        info = path.lstat()
    except FileNotFoundError:
        info = None
    except OSError as err:
        raise RenderError("cannot inspect output: {}".format(err)) from err
    if info is not None and (stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode)):
        raise RenderError("output must be absent or a regular non-symlink file")
    temporary = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix="." + path.name + ".", dir=str(path.parent))
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
    except OSError as err:
        raise RenderError("cannot atomically write output: {}".format(err)) from err
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def check_output(path, expected):
    actual = _read_regular(path, max(MAX_TEX_BYTES, len(expected)))
    if actual != expected:
        raise RenderError("generated TeX is stale or nondeterministic")


def _summary(observed, value):
    if observed == 0:
        return {
            "observed": 0,
            "minimum": None,
            "median": None,
            "maximum": None,
            "mean": None,
            "total": None,
        }
    return {
        "observed": observed,
        "minimum": value,
        "median": value,
        "maximum": value,
        "mean": float(value),
        "total": value * observed,
    }


def _synthetic_half_count_summary(observed, lower):
    """Return a plausible integer-count fixture with a half-integral median."""
    if observed <= 0 or observed % 2 != 0:
        raise AssertionError("synthetic half-integral summary requires positive even n")
    total = (2 * lower + 1) * observed // 2
    return {
        "observed": observed,
        "minimum": lower,
        "median": lower + 0.5,
        "maximum": lower + 1,
        "mean": lower + 0.5,
        "total": total,
    }


def _fraction(value, fixed=None):
    value = Fraction(value)
    return {
        "numerator": value.numerator,
        "denominator": value.denominator,
        "fixed_estimand_denominator": fixed,
        "value": float(value),
    }


def _synthetic_contrast(tasks, role, full=False):
    counts = [30] * 45 + [27] if full else [29] * 45 + [22]
    wins = 4 if full else 3
    losses = 2
    per_domain = []
    cap_total = exact_total = 0
    cap_macro = exact_macro = Fraction(0)
    loss_domains = set(range(10, 10 + losses))
    for index, count in enumerate(counts):
        exact = min(10, count)
        cap = exact + (1 if index < wins else -1 if index in loss_domains else 0)
        cap_total += cap
        exact_total += exact
        cap_macro += Fraction(cap, count)
        exact_macro += Fraction(exact, count)
        per_domain.append(
            {
                "domain": "domain{:02d}".format(index + 1),
                "tasks": count,
                "cap_solved": cap,
                "exact_solved": exact,
                "cap_minus_exact_rate": _fraction(Fraction(cap - exact, count)),
            }
        )
    cap_macro /= DOMAINS
    exact_macro /= DOMAINS
    both_solved = exact_total - losses
    both_unsolved = tasks - wins - losses - both_solved
    exact_nontrivial = 620 if full else 600
    semantic_wins = 430 if full else 410
    semantic_losses = 10
    cap_nontrivial = exact_nontrivial + semantic_wins - semantic_losses
    return {
        "role": role,
        "population": {"tasks": tasks, "domains": DOMAINS},
        "equal_domain_macro_coverage": {
            "cap": _fraction(cap_macro, DOMAINS),
            "exact": _fraction(exact_macro, DOMAINS),
            "cap_minus_exact": _fraction(cap_macro - exact_macro, DOMAINS),
            "domain_weighting": "each-domain-equal/v1",
        },
        "task_micro_discordance": {
            "cap_wins": wins,
            "cap_losses": losses,
            "wins_minus_losses": wins - losses,
            "discordant": wins + losses,
            "both_solved": both_solved,
            "both_unsolved": both_unsolved,
            "task_pairs": tasks,
        },
        "mechanism": {
            "status": "certified",
            "required_pairs": tasks,
            "paired_complete_certified_traces": tasks,
            "same_k_raw_pool_identity_pairs": tasks,
            "cap_semantic_nontrivial": cap_nontrivial,
            "exact_semantic_nontrivial": exact_nontrivial,
            "semantic_pair_wins": semantic_wins,
            "semantic_pair_losses": semantic_losses,
            "semantic_selection_difference_observed": True,
            "claim_policy": (
                "requires-all-pairs-complete-all-raw-pools-identical-and-at-"
                "least-one-paired-semantic-nontrivial-difference/v1"
            ),
        },
        "per_domain": per_domain,
    }


def _synthetic_selector(tasks, config, semantic):
    cap_histogram = {"exact": tasks} if config == EXACT else {"8": 900, "exact": tasks - 900}
    if config == EXACT:
        sources = {
            "empty": 100,
            "bdd_prefix": 200,
            "goal_prefix": 300,
            "goal_fill": 400,
            "cegar": tasks - 1000,
        }
        a = _summary(tasks, 100)
        t = _summary(tasks, 3)
        u = _summary(tasks, 103)
        v = _summary(tasks, 10)
    else:
        # Deliberately distinct from exact so selector-key mixups are observable.
        sources = {
            "empty": 110,
            "bdd_prefix": 210,
            "goal_prefix": 310,
            "goal_fill": 410,
            "cegar": tasks - 1040,
        }
        # A half-integral median distinct from the minimum catches field reuse.
        a = _synthetic_half_count_summary(tasks - 1, 80)
        t = _summary(tasks - 2, 3)
        u = _summary(tasks, 83)
        v = _summary(tasks - 3, 9)
    return {
        "eligible_cells": tasks,
        "complete_certified_traces": tasks,
        "semantic_nontrivial": semantic,
        "effective_cap_histogram": cap_histogram,
        "selected_first_provenance_source": sources,
        "pattern_size": _summary(tasks, 5),
        "W": _summary(tasks, 4),
        "A": a,
        "T": t,
        "U": u,
        "V": v,
    }


def _synthetic_secondary(tasks, contrast, full=False):
    micro = contrast["task_micro_discordance"]
    joint = micro["both_solved"]
    cap_solved = micro["cap_wins"] + joint
    exact_solved = micro["cap_losses"] + joint
    candidate_runtime_total = cap_solved * 9.0
    reference_runtime_total = exact_solved * 10.0
    cap_par2 = (
        candidate_runtime_total + PAR2_PENALTY * (tasks - cap_solved)
    ) / tasks
    exact_par2 = (
        reference_runtime_total + PAR2_PENALTY * (tasks - exact_solved)
    ) / tasks
    image_pairs = 520 if full else 500
    construction_pairs = tasks - 20
    return {
        "tasks": tasks,
        "selector_summary": {
            EXACT: _synthetic_selector(
                tasks, EXACT, contrast["mechanism"]["exact_semantic_nontrivial"]
            ),
            CAP: _synthetic_selector(
                tasks, CAP, contrast["mechanism"]["cap_semantic_nontrivial"]
            ),
        },
        "paired_operational": {
            "micro_par2_seconds": {
                "fixed_task_denominator": tasks,
                "candidate_solved": cap_solved,
                "reference_solved": exact_solved,
                "candidate_solved_planner_cpu_total_seconds": (
                    candidate_runtime_total
                ),
                "reference_solved_planner_cpu_total_seconds": (
                    reference_runtime_total
                ),
                "candidate": cap_par2,
                "reference": exact_par2,
                "candidate_minus_reference": cap_par2 - exact_par2,
            },
            "jointly_solved_planner_cpu": {
                "jointly_solved_pair_count": joint,
                "eligible_pair_count": joint - 1,
                "excluded_nonpositive_pair_count": 1,
                "candidate_over_reference": 0.95,
            },
            "complete_certified_image_time": {
                "eligible_pair_count": image_pairs,
                "candidate_total": 1000.0,
                "reference_total": 1100.0,
                "candidate_over_reference": 10.0 / 11.0,
            },
            "complete_certified_expanded_bdd_nodes": {
                "eligible_pair_count": image_pairs,
                "candidate_total": 8000,
                "reference_total": 10000,
                "candidate_over_reference": 0.8,
            },
            "observed_completed_construction_time": {
                "eligible_pair_count": construction_pairs,
                "candidate_total": 1300.0,
                "reference_total": 1200.0,
                "candidate_over_reference": 13.0 / 12.0,
            },
        },
    }


def _synthetic_analysis():
    sys.path.insert(0, str(SCRIPT_DIR))
    try:
        import pdb_cap_grid_full_protocol as protocol
        import pdb_cap_grid_full_secondary_contract as secondary
    finally:
        try:
            sys.path.remove(str(SCRIPT_DIR))
        except ValueError:
            pass
    pins = {
        "protocol_revision": hashlib.sha1(b"synthetic focused full launch").hexdigest(),
        "properties_sha256": hashlib.sha256(b"synthetic focused properties").hexdigest(),
        "job_sha256": hashlib.sha256(b"synthetic prospective job").hexdigest(),
    }
    primary = _synthetic_contrast(PRIMARY_TASKS, "primary-development-complement")
    sensitivity = _synthetic_contrast(
        TASKS, "prespecified-scope-sensitivity", full=True
    )
    configs = []
    sensitivity_micro = sensitivity["task_micro_discordance"]
    cap_solved = sensitivity_micro["cap_wins"] + sensitivity_micro["both_solved"]
    exact_solved = sensitivity_micro["cap_losses"] + sensitivity_micro["both_solved"]
    solved_by_label = {
        "blind_fw": 430,
        "ms_exact": 480,
        "pdb_cegar_b100k": 450,
        EXACT: exact_solved,
        CAP: cap_solved,
    }
    # Distinct positive summaries make cross-configuration row reuse observable.
    construction_by_label = {
        "blind_fw": _summary(0, 0),
        "ms_exact": _summary(TASKS - 10, 1.0),
        "pdb_cegar_b100k": _summary(TASKS - 11, 2.0),
        EXACT: _summary(TASKS - 12, 3.0),
        CAP: _summary(TASKS - 13, 4.0),
    }
    for label, _, _, role in CONFIGS:
        solved = solved_by_label[label]
        solved_cpu_per_task = 9.0 if label == CAP else 10.0
        solved_runtime_total = solved * solved_cpu_per_task
        par2 = (
            solved_runtime_total + PAR2_PENALTY * (TASKS - solved)
        ) / TASKS
        configs.append(
            {
                "label": label,
                "role": role,
                "cells": TASKS,
                "solved": solved,
                "coverage_rate": solved / TASKS,
                "micro_par2_seconds": par2,
                "solved_planner_cpu_seconds": _summary(
                    solved, solved_cpu_per_task
                ),
                "completed_construction_seconds": construction_by_label[label],
            }
        )
    result = {
        "schema": ANALYSIS_SCHEMA,
        "analysis_protocol": ANALYSIS_PROTOCOL,
        "predeclaration": copy.deepcopy(protocol.ANALYSIS_PREDECLARATION),
        "execution": {
            "protocol": FULL_PROTOCOL,
            "protocol_revision": pins["protocol_revision"],
            "planner_revision": EXPECTED_PLANNER_REVISION,
            "planner_binary_sha256": EXPECTED_PLANNER_BINARY_SHA256,
            "planner_preprocess_sha256": EXPECTED_PLANNER_PREPROCESS_SHA256,
            "prospective_start_job_sha256": pins["job_sha256"],
            "properties_canonical_sha256": pins["properties_sha256"],
            "task_manifest_sha256": EXPECTED_TASK_MANIFEST_SHA256,
            "primary_task_manifest_sha256": EXPECTED_PRIMARY_TASK_MANIFEST_SHA256,
            "option_matrix_sha256": EXPECTED_OPTION_MATRIX_SHA256,
            "cell_count": CELLS,
            "all_cells_validated": True,
            "solved_cost_agreement_validated_across_all_configs": True,
            "completion_recovery_protocol": EXPECTED_COMPLETION_PROTOCOL,
        },
        "secondary_descriptive_contract": {
            "sha256": EXPECTED_SECONDARY_CONTRACT_SHA256,
            "contract": copy.deepcopy(secondary.CONTRACT),
        },
        "primary": primary,
        "full_census_sensitivity": sensitivity,
        "secondary_descriptive": {
            "primary_development_complement": _synthetic_secondary(
                PRIMARY_TASKS, primary
            ),
            "full_census_sensitivity": _synthetic_secondary(
                TASKS, sensitivity, full=True
            ),
        },
        "descriptive_full_census_configs": configs,
        "inference": {
            "confidence_intervals": None,
            "p_values": None,
            "fixed_population_census": True,
        },
    }
    raw = canonical_json(result).encode("ascii") + b"\n"
    digest = sha256_bytes(raw)
    pins["analysis_sha256"] = digest
    return result, raw, digest, pins


def self_test():
    value, raw, digest, pins = _synthetic_analysis()
    _validate_analysis_with_pins(value, digest, pins)
    first = _render_tex_with_pins(value, digest, pins)
    second = _render_tex_with_pins(copy.deepcopy(value), digest, pins)
    if first != second:
        raise AssertionError("synthetic TeX rendering is not deterministic")

    adversarial = []

    def reject(name, mutate):
        changed = copy.deepcopy(value)
        mutate(changed)
        changed_raw = canonical_json(changed).encode("ascii") + b"\n"
        changed_pins = dict(pins, analysis_sha256=sha256_bytes(changed_raw))
        try:
            _validate_analysis_with_pins(changed, changed_pins["analysis_sha256"], changed_pins)
        except RenderError:
            adversarial.append(name)
        else:
            raise AssertionError("adversarial mutation was accepted: {}".format(name))

    reject("cell-count", lambda item: item["execution"].__setitem__("cell_count", CELLS - 1))
    reject(
        "fraction-conservation",
        lambda item: item["primary"]["equal_domain_macro_coverage"]["cap_minus_exact"].__setitem__(
            "numerator", 999
        ),
    )
    reject(
        "mechanism-denominator",
        lambda item: item["primary"]["mechanism"].__setitem__(
            "same_k_raw_pool_identity_pairs", PRIMARY_TASKS - 1
        ),
    )
    reject(
        "image-effort-pair-set",
        lambda item: item["secondary_descriptive"]["primary_development_complement"][
            "paired_operational"
        ]["complete_certified_expanded_bdd_nodes"].__setitem__("eligible_pair_count", 499),
    )
    reject(
        "secondary-contract",
        lambda item: item["secondary_descriptive_contract"]["contract"].__setitem__(
            "role", "changed"
        ),
    )
    reject(
        "par2-reconstruction",
        lambda item: item["secondary_descriptive"]["primary_development_complement"]
        ["paired_operational"]["micro_par2_seconds"].__setitem__("candidate", 0.0),
    )
    reject(
        "primary-subset",
        lambda item: item["secondary_descriptive"]["primary_development_complement"]
        ["selector_summary"][CAP]["effective_cap_histogram"].update(
            {"8": 901, "exact": PRIMARY_TASKS - 901}
        ),
    )

    with tempfile.TemporaryDirectory(prefix="cap-full-paper-render-") as directory:
        root = Path(directory)
        artifact = root / "analysis-v1.json"
        sidecar = Path(str(artifact) + ".sha256")
        artifact.write_bytes(raw)
        sidecar.write_text("{}  {}\n".format(digest, artifact.name), encoding="ascii")
        loaded, loaded_digest = _load_frozen_analysis_with_pins(
            artifact, sidecar, pins
        )
        if loaded != value or loaded_digest != digest:
            raise AssertionError("synthetic canonical artifact round trip changed")
        output = root / "generated.tex"
        _write_atomic(output, first)
        check_output(output, first)
        _write_atomic(output, first)
        check_output(output, first)
    return {
        "schema": PAPER_DATA_SCHEMA,
        "self_test": "PASS",
        "synthetic_analysis_sha256": digest,
        "synthetic_tex_sha256": sha256_bytes(first),
        "synthetic_tex_bytes": len(first),
        "adversarial": adversarial,
        "ordinary_render_gate": "BLOCKED_UNTIL_FINAL_ANALYSIS_HASH_AND_PINS_ARE_REVIEWED",
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate and render the focused cap-grid full analysis."
    )
    parser.add_argument(
        "analysis", nargs="?", type=Path, default=DEFAULT_ANALYSIS,
        help="canonical focused full analysis JSON artifact",
    )
    parser.add_argument("--sidecar", type=Path, help="exact sha256sum sidecar")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--write", action="store_true")
    actions.add_argument("--emit-tex", action="store_true")
    actions.add_argument("--self-test", action="store_true")
    args = parser.parse_args(argv)
    if args.self_test and not (
        args.analysis == DEFAULT_ANALYSIS
        and args.sidecar is None
        and args.output == DEFAULT_OUTPUT
    ):
        parser.error("--self-test does not accept input or output paths")
    return args


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        print(canonical_json(self_test()))
        return 0
    value, digest = load_frozen_analysis(args.analysis, args.sidecar)
    rendered = render_tex(value, digest)
    if args.emit_tex:
        sys.stdout.buffer.write(rendered)
        return 0
    if args.check:
        check_output(args.output, rendered)
        print(canonical_json({"check": "PASS", "tex_sha256": sha256_bytes(rendered)}))
        return 0
    output = _validate_write_target(args.output)
    _write_atomic(output, rendered)
    print(canonical_json({"write": "PASS", "tex_sha256": sha256_bytes(rendered)}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RenderError as err:
        print("render error: {}".format(err), file=sys.stderr)
        sys.exit(2)
