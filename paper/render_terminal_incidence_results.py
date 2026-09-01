#!/usr/bin/env python3
"""Render terminal-incidence outcomes from sealed, normalized evidence.

Phase 1 deliberately has no real-artifact loader.  Production modes remain
blocked while every expected digest is the all-zero sentinel.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import tempfile
import unittest
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path


ZERO_SHA256 = "0" * 64
PRODUCTION_DIGEST_PINS = {
    "source_audit": ZERO_SHA256,
    "confirmation_a": ZERO_SHA256,
    "direct_metric_choice": ZERO_SHA256,
    "confirmation_b": ZERO_SHA256,
    "hardware_receipts": ZERO_SHA256,
}
PAPER_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = PAPER_ROOT / "generated" / "terminal-incidence-results.tex"
MAX_OUTPUT_BYTES = 128 * 1024

BASELINES = (
    "masked_add_size",
    "kD",
    "mQ",
    "mJ",
    "cartesian",
    "width",
    "apply",
)

TITLE_SELECTION = (
    "Terminal Incidence: From Partition-Effort Prediction to Heuristic Selection"
)
TITLE_PREDICTOR = "Terminal Incidence Predicts Heuristic Fragmentation in Symbolic Search"
TITLE_CERTIFICATES = (
    "Heuristic Fragmentation in Symbolic Search: "
    "Terminal-Incidence Certificates and Their Limits"
)


class RenderError(ValueError):
    """The evidence cannot authorize a deterministic result rendering."""


class OutcomeBranch(Enum):
    A_FAIL = "a-fail"
    A_PASS_DIRECT_FAIL_B_FAIL = "a-pass-direct-fail-b-fail"
    A_PASS_DIRECT_FAIL_B_PASS = "a-pass-direct-fail-b-pass"
    A_PASS_DIRECT_PASS_B_FAIL = "a-pass-direct-pass-b-fail"
    A_PASS_DIRECT_PASS_B_PASS = "a-pass-direct-pass-b-pass"


@dataclass(frozen=True)
class Outcome:
    branch: OutcomeBranch
    a_pass: bool
    direct_pass: bool | None
    b_pass: bool | None


def _keys(record: object, expected: set[str], path: str) -> dict:
    if type(record) is not dict:
        raise RenderError(f"{path} must be a dict")
    actual = set(record)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected, key=repr)
        raise RenderError(f"{path} schema mismatch; missing={missing}, extra={extra}")
    return record


def _boolean(record: dict, key: str, path: str) -> bool:
    value = record[key]
    if type(value) is not bool:
        raise RenderError(f"{path}.{key} must be a bool")
    return value


def _integer(
    record: dict,
    key: str,
    path: str,
    *,
    minimum: int = 0,
    maximum: int | None = None,
) -> int:
    value = record[key]
    if type(value) is not int:
        raise RenderError(f"{path}.{key} must be an int")
    if value < minimum or (maximum is not None and value > maximum):
        raise RenderError(f"{path}.{key} is outside its allowed range")
    return value


def _rational(
    record: dict,
    key: str,
    path: str,
    *,
    minimum: Fraction = Fraction(-1),
    maximum: Fraction = Fraction(1),
) -> Fraction | None:
    value = record[key]
    if value is None:
        return None
    fraction_path = f"{path}.{key}"
    fraction = _keys(value, {"numerator", "denominator"}, fraction_path)
    numerator = fraction["numerator"]
    denominator = fraction["denominator"]
    if type(numerator) is not int:
        raise RenderError(f"{fraction_path}.numerator must be an int")
    if type(denominator) is not int or denominator <= 0:
        raise RenderError(f"{fraction_path}.denominator must be a positive int")
    exact = Fraction(numerator, denominator)
    if exact.numerator != numerator or exact.denominator != denominator:
        raise RenderError(f"{fraction_path} must be a canonical rational record")
    if exact < minimum or exact > maximum:
        raise RenderError(f"{path}.{key} is outside its allowed range")
    return exact


def _fraction(record: dict, key: str) -> Fraction | None:
    value = record[key]
    if value is None:
        return None
    return Fraction(value["numerator"], value["denominator"])


def _validate_orientation(value: object, path: str) -> dict:
    record = _keys(value, {"orders_identical", "inverse_u_tied"}, path)
    _boolean(record, "orders_identical", path)
    _boolean(record, "inverse_u_tied", path)
    return record


def _orientation_gate(record: dict) -> bool:
    return record["orders_identical"] and record["inverse_u_tied"]


def _reject_artifact_text(value: object, path: str = "evidence") -> None:
    """Reject every artifact-provided string value before template rendering."""
    if type(value) is str:
        raise RenderError(f"{path} contains forbidden artifact-provided text")
    if type(value) is dict:
        for key, child in value.items():
            if type(key) is not str:
                raise RenderError(f"{path} contains a non-string schema key")
            _reject_artifact_text(child, f"{path}.{key}")
    elif type(value) in (list, tuple, set):
        for index, child in enumerate(value):
            _reject_artifact_text(child, f"{path}[{index}]")


def _validate_source_audit(value: object) -> dict:
    path = "evidence.source_audit"
    record = _keys(
        value,
        {
            "sealed",
            "a_tasks",
            "a_families",
            "a_shadow_families",
            "a_prior_tasks",
            "a_prior_families",
            "b_tasks",
            "b_families",
            "b_shadow_families",
            "b_prior_tasks",
            "b_prior_families",
        },
        path,
    )
    if not _boolean(record, "sealed", path):
        raise RenderError("the source audit is not sealed")
    a_tasks = _integer(record, "a_tasks", path)
    a_families = _integer(record, "a_families", path, maximum=a_tasks)
    a_shadow = _integer(record, "a_shadow_families", path, maximum=a_families)
    a_prior_tasks = _integer(record, "a_prior_tasks", path, maximum=a_tasks)
    a_prior_families = _integer(
        record,
        "a_prior_families",
        path,
        maximum=min(a_families, a_prior_tasks),
    )
    b_tasks = _integer(record, "b_tasks", path)
    b_families = _integer(record, "b_families", path, maximum=b_tasks)
    b_shadow = _integer(record, "b_shadow_families", path, maximum=b_families)
    b_prior_tasks = _integer(record, "b_prior_tasks", path, maximum=b_tasks)
    b_prior_families = _integer(
        record,
        "b_prior_families",
        path,
        maximum=min(b_families, b_prior_tasks),
    )
    authorized = (
        a_tasks == 650
        and a_families >= 28
        and a_shadow >= 12
        and a_prior_tasks >= 100
        and a_prior_families >= 10
        and b_tasks == 300
        and b_families >= 30
        and b_shadow >= 12
        and b_prior_tasks >= 50
        and b_prior_families >= 10
    )
    if not authorized:
        raise RenderError("the sealed source audit does not authorize both cohorts")
    return record


def _validate_baselines(value: object, path: str) -> dict:
    record = _keys(value, set(BASELINES), path)
    for baseline in BASELINES:
        result_path = f"{path}.{baseline}"
        result = _keys(
            record[baseline],
            {"margin", "bootstrap_lower", "lofo_minimum"},
            result_path,
        )
        _rational(result, "margin", result_path)
        _rational(result, "bootstrap_lower", result_path)
        _rational(result, "lofo_minimum", result_path)
    return record


def _validate_a_stratum(value: object, path: str) -> dict:
    record = _keys(
        value,
        {
            "comparison_tasks",
            "comparison_families",
            "target_strict_pairs",
            "i_concordance",
            "baselines",
            "orientation",
        },
        path,
    )
    comparison_tasks = _integer(record, "comparison_tasks", path, maximum=650)
    _integer(
        record,
        "comparison_families",
        path,
        maximum=comparison_tasks,
    )
    _integer(record, "target_strict_pairs", path)
    _rational(record, "i_concordance", path, minimum=Fraction(0))
    _validate_baselines(record["baselines"], f"{path}.baselines")
    _validate_orientation(record["orientation"], f"{path}.orientation")
    return record


def _validate_a(value: object, source: dict) -> dict:
    path = "evidence.confirmation_a"
    record = _keys(
        value,
        {
            "sealed",
            "eligible_tasks",
            "comparison_tasks",
            "eligible_families",
            "comparison_families",
            "target_strict_pairs",
            "i_concordance",
            "baselines",
            "orientation",
            "all_prior",
        },
        path,
    )
    if not _boolean(record, "sealed", path):
        raise RenderError("Confirmation A is not sealed")
    eligible_tasks = _integer(record, "eligible_tasks", path, maximum=source["a_tasks"])
    comparison_tasks = _integer(
        record, "comparison_tasks", path, maximum=eligible_tasks
    )
    eligible_families = _integer(
        record,
        "eligible_families",
        path,
        maximum=min(source["a_families"], eligible_tasks),
    )
    comparison_families = _integer(
        record,
        "comparison_families",
        path,
        maximum=min(eligible_families, comparison_tasks),
    )
    _integer(record, "target_strict_pairs", path)
    _rational(record, "i_concordance", path, minimum=Fraction(0))
    _validate_baselines(record["baselines"], f"{path}.baselines")
    _validate_orientation(record["orientation"], f"{path}.orientation")
    prior = _validate_a_stratum(record["all_prior"], f"{path}.all_prior")
    if prior["comparison_tasks"] > source["a_prior_tasks"]:
        raise RenderError("Confirmation A all-prior task support exceeds its cohort")
    if prior["comparison_tasks"] > comparison_tasks:
        raise RenderError("Confirmation A all-prior task support exceeds full support")
    if prior["comparison_families"] > source["a_prior_families"]:
        raise RenderError("Confirmation A all-prior family support exceeds its cohort")
    if prior["comparison_families"] > comparison_families:
        raise RenderError("Confirmation A all-prior family support exceeds full support")
    if prior["target_strict_pairs"] > record["target_strict_pairs"]:
        raise RenderError("Confirmation A all-prior pair support exceeds full support")
    return record


def _baseline_gate(baselines: dict) -> bool:
    for name in BASELINES:
        margin = _fraction(baselines[name], "margin")
        bootstrap = _fraction(baselines[name], "bootstrap_lower")
        lofo = _fraction(baselines[name], "lofo_minimum")
        if (
            margin is None
            or bootstrap is None
            or lofo is None
            or margin < Fraction(1, 50)
            or bootstrap <= 0
            or lofo <= 0
        ):
            return False
    return True


def _a_gate(record: dict) -> bool:
    prior = record["all_prior"]
    primary_concordance = _fraction(record, "i_concordance")
    prior_concordance = _fraction(prior, "i_concordance")
    return (
        record["eligible_tasks"] >= 300
        and record["comparison_tasks"] >= 300
        and record["eligible_families"] >= 25
        and record["comparison_families"] >= 25
        and record["target_strict_pairs"] >= 600
        and primary_concordance is not None
        and primary_concordance >= Fraction(13, 20)
        and _baseline_gate(record["baselines"])
        and _orientation_gate(record["orientation"])
        and prior["comparison_tasks"] >= 50
        and prior["comparison_families"] >= 10
        and prior["target_strict_pairs"] >= 100
        and prior_concordance is not None
        and prior_concordance >= Fraction(13, 20)
        and _baseline_gate(prior["baselines"])
        and _orientation_gate(prior["orientation"])
    )


def _validate_contrast(value: object, path: str, maximum_tasks: int) -> dict:
    record = _keys(
        value,
        {
            "coverage_incidence",
            "coverage_comparator",
            "mean_improvement",
            "bootstrap_lower",
            "lofo_minimum",
        },
        path,
    )
    _integer(record, "coverage_incidence", path, maximum=maximum_tasks)
    _integer(record, "coverage_comparator", path, maximum=maximum_tasks)
    _rational(record, "mean_improvement", path)
    _rational(record, "bootstrap_lower", path)
    _rational(record, "lofo_minimum", path)
    return record


def _contrast_gate(record: dict) -> bool:
    improvement = _fraction(record, "mean_improvement")
    bootstrap = _fraction(record, "bootstrap_lower")
    lofo = _fraction(record, "lofo_minimum")
    return (
        record["coverage_incidence"] >= record["coverage_comparator"]
        and improvement is not None
        and improvement >= Fraction(1, 50)
        and bootstrap is not None
        and bootstrap > 0
        and lofo is not None
        and lofo > 0
    )


def _validate_direct(value: object, source: dict) -> dict:
    path = "evidence.direct_metric_choice"
    record = _keys(
        value,
        {
            "sealed",
            "audit_certified",
            "tasks",
            "families",
            "full",
            "differing_winners",
        },
        path,
    )
    if not _boolean(record, "sealed", path):
        raise RenderError("the direct metric-choice input is not sealed")
    _boolean(record, "audit_certified", path)
    tasks = _integer(record, "tasks", path)
    families = _integer(record, "families", path)
    if tasks != source["b_tasks"] or families != source["b_families"]:
        raise RenderError("the direct metric-choice cohort does not match cohort B")
    full = _validate_contrast(record["full"], f"{path}.full", tasks)
    differing_path = f"{path}.differing_winners"
    differing = _keys(
        record["differing_winners"],
        {
            "tasks",
            "families",
            "coverage_incidence",
            "coverage_comparator",
            "mean_improvement",
            "bootstrap_lower",
            "lofo_minimum",
        },
        differing_path,
    )
    differing_tasks = _integer(differing, "tasks", differing_path, maximum=tasks)
    _integer(
        differing,
        "families",
        differing_path,
        maximum=min(families, differing_tasks),
    )
    differing_incidence_coverage = _integer(
        differing,
        "coverage_incidence",
        differing_path,
        maximum=differing_tasks,
    )
    differing_comparator_coverage = _integer(
        differing,
        "coverage_comparator",
        differing_path,
        maximum=differing_tasks,
    )
    _rational(differing, "mean_improvement", differing_path)
    _rational(differing, "bootstrap_lower", differing_path)
    _rational(differing, "lofo_minimum", differing_path)
    if differing_incidence_coverage > full["coverage_incidence"]:
        raise RenderError(
            "direct differing-winner incidence coverage exceeds full-cohort coverage"
        )
    if differing_comparator_coverage > full["coverage_comparator"]:
        raise RenderError(
            "direct differing-winner comparator coverage exceeds full-cohort coverage"
        )
    return record


def _direct_gate(record: dict) -> bool:
    differing = record["differing_winners"]
    return (
        record["audit_certified"]
        and _contrast_gate(record["full"])
        and differing["tasks"] >= 50
        and differing["families"] >= 10
        and _contrast_gate(differing)
    )


def _validate_b(value: object, source: dict) -> dict:
    path = "evidence.confirmation_b"
    record = _keys(
        value,
        {
            "sealed",
            "selector_provenance_pass",
            "tasks",
            "families",
            "versus_reference",
            "versus_matched",
        },
        path,
    )
    if not _boolean(record, "sealed", path):
        raise RenderError("Confirmation B is not sealed")
    _boolean(record, "selector_provenance_pass", path)
    tasks = _integer(record, "tasks", path)
    families = _integer(record, "families", path)
    if tasks != source["b_tasks"] or families != source["b_families"]:
        raise RenderError("the Confirmation B cohort does not match its source audit")
    reference = _validate_contrast(
        record["versus_reference"], f"{path}.versus_reference", tasks
    )
    matched = _validate_contrast(
        record["versus_matched"], f"{path}.versus_matched", tasks
    )
    if reference["coverage_incidence"] != matched["coverage_incidence"]:
        raise RenderError(
            "Confirmation B guided coverage differs across same-cohort contrasts"
        )
    return record


def _b_gate(record: dict) -> bool:
    return record["selector_provenance_pass"] and _contrast_gate(
        record["versus_reference"]
    ) and _contrast_gate(
        record["versus_matched"]
    )


def _validate_hardware(value: object, *, downstream_required: bool) -> dict:
    path = "evidence.hardware"
    record = _keys(
        value,
        {"a_receipt_sealed", "downstream_receipts_sealed"},
        path,
    )
    if not _boolean(record, "a_receipt_sealed", path):
        raise RenderError("the Confirmation A hardware receipt is not sealed")
    downstream = _boolean(record, "downstream_receipts_sealed", path)
    if downstream != downstream_required:
        raise RenderError("hardware-receipt presence contradicts the terminal branch")
    return record


def classify(evidence: object) -> Outcome:
    """Validate normalized evidence and recompute its unique terminal branch."""
    _reject_artifact_text(evidence)
    if type(evidence) is not dict:
        raise RenderError("evidence must be a dict")
    common = {"source_audit", "confirmation_a", "hardware"}
    downstream = {"direct_metric_choice", "confirmation_b"}
    unknown = set(evidence) - common - downstream
    missing = common - set(evidence)
    if missing or unknown:
        raise RenderError(
            f"evidence schema mismatch; missing={sorted(missing)}, "
            f"extra={sorted(unknown, key=repr)}"
        )

    source = _validate_source_audit(evidence["source_audit"])
    confirmation_a = _validate_a(evidence["confirmation_a"], source)
    a_pass = _a_gate(confirmation_a)
    expected = common | downstream if a_pass else common
    _keys(evidence, expected, "evidence")
    _validate_hardware(evidence["hardware"], downstream_required=a_pass)

    if not a_pass:
        return Outcome(OutcomeBranch.A_FAIL, False, None, None)

    direct = _validate_direct(evidence["direct_metric_choice"], source)
    confirmation_b = _validate_b(evidence["confirmation_b"], source)
    direct_pass = _direct_gate(direct)
    b_pass = _b_gate(confirmation_b)
    branch = {
        (False, False): OutcomeBranch.A_PASS_DIRECT_FAIL_B_FAIL,
        (False, True): OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS,
        (True, False): OutcomeBranch.A_PASS_DIRECT_PASS_B_FAIL,
        (True, True): OutcomeBranch.A_PASS_DIRECT_PASS_B_PASS,
    }[(direct_pass, b_pass)]
    return Outcome(branch, True, direct_pass, b_pass)


ABSTRACT_TEXT = {
    OutcomeBranch.A_FAIL: (
        "Confirmation A did not pass its prespecified fixed-frontier gate; "
        "the downstream selector experiments were therefore not authorized."
    ),
    OutcomeBranch.A_PASS_DIRECT_FAIL_B_FAIL: (
        "Confirmation A passed its prespecified fixed-frontier gate, but neither "
        "the direct metric-choice gate nor the broader selector gate passed."
    ),
    OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS: (
        "Confirmation A and the broader selector comparison passed their "
        "prespecified gates, while the direct metric-choice comparison did not."
    ),
    OutcomeBranch.A_PASS_DIRECT_PASS_B_FAIL: (
        "Confirmation A and the direct metric-choice comparison passed their "
        "prespecified gates, while the broader selector comparison did not."
    ),
    OutcomeBranch.A_PASS_DIRECT_PASS_B_PASS: (
        "Confirmation A, the direct metric-choice comparison and the broader "
        "selector comparison passed their prespecified gates."
    ),
}

CONCLUSION_TEXT = {
    OutcomeBranch.A_FAIL: (
        "The confirmatory evidence does not support the ordinal predictor claim; "
        "the selector claims remain untested."
    ),
    OutcomeBranch.A_PASS_DIRECT_FAIL_B_FAIL: (
        "The evidence supports terminal incidence as an ordinal fixed-frontier "
        "predictor, but not either downstream selector claim."
    ),
    OutcomeBranch.A_PASS_DIRECT_FAIL_B_PASS: (
        "The evidence supports the ordinal predictor and the broader frozen "
        "selector design, but not a benefit from substituting incidence for the "
        "developmental metric within the common candidate pool."
    ),
    OutcomeBranch.A_PASS_DIRECT_PASS_B_FAIL: (
        "The evidence supports the ordinal predictor and the direct metric "
        "substitution, but not the broader frozen selector design."
    ),
    OutcomeBranch.A_PASS_DIRECT_PASS_B_PASS: (
        "The evidence supports the ordinal predictor, the direct metric "
        "substitution and the broader frozen selector design within their stated scope."
    ),
}


def _minimum(record: dict, field: str) -> Fraction | None:
    values = [_fraction(record[name], field) for name in BASELINES]
    if any(value is None for value in values):
        return None
    return min(values)


def _fmt(value: Fraction | None) -> str:
    if value is None:
        return "not estimable"
    return f"{float(value):.3f}"


def _title(outcome: Outcome) -> str:
    if not outcome.a_pass:
        return TITLE_CERTIFICATES
    if outcome.direct_pass:
        return TITLE_SELECTION
    return TITLE_PREDICTOR


def _a_text(evidence: dict, outcome: Outcome) -> str:
    a = evidence["confirmation_a"]
    prior = a["all_prior"]
    decision = "passed" if outcome.a_pass else "failed"
    return (
        f"Confirmation A used {a['comparison_tasks']} comparison tasks from "
        f"{a['comparison_families']} families and {a['target_strict_pairs']} "
        f"target-strict pairs. Terminal incidence had macro concordance "
        f"{_fmt(_fraction(a, 'i_concordance'))}; across the seven baselines, the smallest "
        f"margin, bootstrap lower endpoint and leave-one-family-out difference "
        f"were {_fmt(_minimum(a['baselines'], 'margin'))}, "
        f"{_fmt(_minimum(a['baselines'], 'bootstrap_lower'))} and "
        f"{_fmt(_minimum(a['baselines'], 'lofo_minimum'))}. The all-prior-"
        f"unrepresented stratum used {prior['comparison_tasks']} comparison tasks "
        f"from {prior['comparison_families']} families and "
        f"{prior['target_strict_pairs']} target-strict pairs. The complete gate "
        f"{decision}."
    )


def _direct_text(evidence: dict, outcome: Outcome) -> str:
    if not outcome.a_pass:
        return "The direct metric-choice campaign was not authorized."
    direct = evidence["direct_metric_choice"]
    full = direct["full"]
    differing = direct["differing_winners"]
    decision = "passed" if outcome.direct_pass else "failed"
    return (
        f"The sealed direct comparison covered {full['coverage_incidence']} tasks "
        f"with incidence and {full['coverage_comparator']} with the developmental "
        f"metric. Its equal-family normalized improvement, bootstrap lower "
        f"endpoint and leave-one-family-out minimum were "
        f"{_fmt(_fraction(full, 'mean_improvement'))}, "
        f"{_fmt(_fraction(full, 'bootstrap_lower'))} and "
        f"{_fmt(_fraction(full, 'lofo_minimum'))}. The differing-winner subset contained "
        f"{differing['tasks']} tasks from {differing['families']} families; its "
        f"improvement, bootstrap lower endpoint and leave-one-family-out minimum "
        f"were {_fmt(_fraction(differing, 'mean_improvement'))}, "
        f"{_fmt(_fraction(differing, 'bootstrap_lower'))} and "
        f"{_fmt(_fraction(differing, 'lofo_minimum'))}. The "
        f"direct gate {decision}."
    )


def _b_text(evidence: dict, outcome: Outcome) -> str:
    if not outcome.a_pass:
        return "Confirmation B was not authorized."
    confirmation_b = evidence["confirmation_b"]
    reference = confirmation_b["versus_reference"]
    matched = confirmation_b["versus_matched"]
    decision = "passed" if outcome.b_pass else "failed"
    return (
        f"Confirmation B used {confirmation_b['tasks']} tasks from "
        f"{confirmation_b['families']} families. Equal-family normalized "
        f"improvements were {_fmt(_fraction(reference, 'mean_improvement'))} against the "
        f"cap-aware reference and {_fmt(_fraction(matched, 'mean_improvement'))} against the "
        f"matched-work control. The complete gate {decision}."
    )


def _source_text(source: dict) -> str:
    return (
        f"The sealed source audit authorized {source['a_tasks']} Confirmation A "
        f"tasks from {source['a_families']} families and {source['b_tasks']} "
        f"Confirmation B tasks from {source['b_families']} families; the "
        f"all-prior-unrepresented strata contained {source['a_prior_tasks']} and "
        f"{source['b_prior_tasks']} tasks, respectively."
    )


def _hardware_text(outcome: Outcome) -> str:
    if outcome.a_pass:
        return (
            "The sealed Confirmation A, direct metric-choice and Confirmation B "
            "execution receipts verified their frozen hardware allocations."
        )
    return (
        "The sealed Confirmation A execution receipt verified its frozen hardware "
        "allocation; no downstream execution receipt is present."
    )


def render(evidence: object) -> str:
    """Return exactly eight fixed-template TeX macro definitions."""
    outcome = classify(evidence)
    macros = (
        ("TIOutcomeTitle", _title(outcome)),
        ("TIOutcomeAbstract", ABSTRACT_TEXT[outcome.branch]),
        ("TIOutcomeA", _a_text(evidence, outcome)),
        ("TIOutcomeMetricChoice", _direct_text(evidence, outcome)),
        ("TIOutcomeB", _b_text(evidence, outcome)),
        ("TIOutcomeConclusion", CONCLUSION_TEXT[outcome.branch]),
        ("TIOutcomeSourceAudit", _source_text(evidence["source_audit"])),
        ("TIOutcomeHardware", _hardware_text(outcome)),
    )
    lines = ["% Generated by render_terminal_incidence_results.py; do not edit."]
    lines.extend(f"\\newcommand{{\\{name}}}{{{body}}}" for name, body in macros)
    return "\n".join(lines) + "\n"


def _load_production_evidence() -> dict:
    """Boundary for the future digest-verifying real-artifact loader."""
    unset = [name for name, digest in PRODUCTION_DIGEST_PINS.items() if digest == ZERO_SHA256]
    if unset:
        raise RenderError(
            "production rendering is disabled by unset digest pins: " + ", ".join(unset)
        )
    raise RenderError("the real-artifact loader is not implemented")


def _validate_output_target(
    path: Path,
    *,
    expected: Path = DEFAULT_OUTPUT,
    trusted_root: Path = PAPER_ROOT,
) -> Path:
    """Require the one canonical output and reject every symlink component."""
    path = Path(path)
    expected = Path(expected)
    trusted_root = Path(trusted_root)
    if not path.is_absolute() or path != expected:
        raise RenderError("output must be the exact canonical generated-paper path")
    if not expected.is_absolute() or not trusted_root.is_absolute():
        raise RenderError("the configured output boundary is not absolute")
    try:
        relative = path.relative_to(trusted_root)
    except ValueError as error:
        raise RenderError("output is outside its trusted root") from error
    if not relative.parts or any(part in ("", ".", "..") for part in relative.parts):
        raise RenderError("output has a noncanonical lexical path")

    components = [trusted_root]
    current = trusted_root
    for part in relative.parts:
        current = current / part
        components.append(current)
    for index, current in enumerate(components):
        is_leaf = index == len(components) - 1
        try:
            info = current.lstat()
        except FileNotFoundError:
            if is_leaf:
                continue
            raise RenderError(f"output parent is missing: {current}")
        except OSError as error:
            raise RenderError(f"cannot inspect output path component: {current}") from error
        if stat.S_ISLNK(info.st_mode):
            raise RenderError("output path contains a symlink component")
        if is_leaf:
            if not stat.S_ISREG(info.st_mode):
                raise RenderError("existing output is not a regular file")
        elif not stat.S_ISDIR(info.st_mode):
            raise RenderError("output parent is not a directory")

    try:
        if path.parent.resolve(strict=True) != path.parent:
            raise RenderError("output parent does not resolve to its lexical path")
        if path.exists() and path.resolve(strict=True) != path:
            raise RenderError("output does not resolve to its lexical path")
    except OSError as error:
        raise RenderError("cannot resolve the canonical output boundary") from error
    return path


def _read_output(
    path: Path,
    *,
    expected: Path = DEFAULT_OUTPUT,
    trusted_root: Path = PAPER_ROOT,
) -> bytes:
    target = _validate_output_target(
        path, expected=expected, trusted_root=trusted_root
    )
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(target, flags)
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_OUTPUT_BYTES:
            raise RenderError("generated output is not a bounded regular file")
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = None
            raw = stream.read(MAX_OUTPUT_BYTES + 1)
            after = os.fstat(stream.fileno())
        if len(raw) > MAX_OUTPUT_BYTES:
            raise RenderError("generated output exceeds its byte limit")
        stable = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_nlink,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) == (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_nlink,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        )
        leaf = target.lstat()
        if (
            not stable
            or stat.S_ISLNK(leaf.st_mode)
            or not stat.S_ISREG(leaf.st_mode)
            or (leaf.st_dev, leaf.st_ino) != (after.st_dev, after.st_ino)
        ):
            raise RenderError("generated output changed while it was read")
        return raw
    except FileNotFoundError as error:
        raise RenderError(f"generated output is missing: {target}") from error
    except OSError as error:
        raise RenderError("cannot safely read generated output") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _check_output(
    path: Path,
    rendered: str,
    *,
    expected: Path = DEFAULT_OUTPUT,
    trusted_root: Path = PAPER_ROOT,
) -> None:
    raw = rendered.encode("utf-8")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise RenderError("rendered output exceeds its byte limit")
    if _read_output(path, expected=expected, trusted_root=trusted_root) != raw:
        raise RenderError(f"generated output is stale: {path}")


def _write_output_atomic(
    path: Path,
    rendered: str,
    *,
    expected: Path = DEFAULT_OUTPUT,
    trusted_root: Path = PAPER_ROOT,
) -> None:
    target = _validate_output_target(
        path, expected=expected, trusted_root=trusted_root
    )
    raw = rendered.encode("utf-8")
    if len(raw) > MAX_OUTPUT_BYTES:
        raise RenderError("rendered output exceeds its byte limit")

    temporary = None
    parent_descriptor = None
    try:
        descriptor, temporary = tempfile.mkstemp(
            prefix=f".{target.name}.", dir=str(target.parent)
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fchmod(stream.fileno(), 0o644)
            os.fsync(stream.fileno())

        _validate_output_target(
            target, expected=expected, trusted_root=trusted_root
        )
        parent_flags = (
            os.O_RDONLY
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_DIRECTORY", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        parent_descriptor = os.open(target.parent, parent_flags)
        try:
            existing = os.stat(
                target.name, dir_fd=parent_descriptor, follow_symlinks=False
            )
        except FileNotFoundError:
            existing = None
        if existing is not None and not stat.S_ISREG(existing.st_mode):
            raise RenderError("existing output is not a regular non-symlink file")
        os.replace(
            Path(temporary).name,
            target.name,
            src_dir_fd=parent_descriptor,
            dst_dir_fd=parent_descriptor,
        )
        temporary = None
        os.fsync(parent_descriptor)
        _check_output(
            target,
            rendered,
            expected=expected,
            trusted_root=trusted_root,
        )
    except OSError as error:
        raise RenderError("cannot atomically write generated output") from error
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass


def _run_self_test() -> bool:
    suite = unittest.defaultTestLoader.discover(
        str(Path(__file__).resolve().parent),
        pattern="test_render_terminal_incidence_results.py",
    )
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return result.wasSuccessful()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-test", action="store_true")
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.self_test:
        return 0 if _run_self_test() else 1
    try:
        output = _validate_output_target(args.output)
        rendered = render(_load_production_evidence())
        if args.check:
            _check_output(output, rendered)
        else:
            _write_output_atomic(output, rendered)
    except (OSError, RenderError) as error:
        print(f"BLOCKED: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
