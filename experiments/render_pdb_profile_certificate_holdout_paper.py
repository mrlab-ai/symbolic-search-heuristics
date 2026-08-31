#!/usr/bin/env python3
"""Render the sealed certificate holdout and denominator audit for the paper."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from fractions import Fraction
from pathlib import Path

import analyze_pdb_profile_certificate_holdout as Primary
import analyze_pdb_profile_denominator_audit as Denominator
import pdb_profile_certificate_holdout_protocol as Protocol
import pdb_profile_denominator_audit_protocol as DenominatorProtocol
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "pdb-profile-certificate-holdout"
DEFAULT_ANALYSIS = ARTIFACT_DIR / "analysis-v1.json"
DEFAULT_DENOMINATOR_AUDIT = ARTIFACT_DIR / "denominator-audit-v1.json"
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT
    / "paper"
    / "generated"
    / "pdb-profile-certificate-holdout-v1.tex"
)
# Canonical production artifacts, accepted after duplicate byte-identical runs.
EXPECTED_ANALYSIS_SHA256 = (
    "17e06a7d2c946dc34d5a171b0edb8f61eeae4895601563c1ff87ca0383ab9d97"
)
EXPECTED_DENOMINATOR_AUDIT_SHA256 = (
    "49f3d7d75c6e7d0374c60e6dc041aa47a1cd2e748dfcce48ba0c9286cec26bc0"
)
MAX_ANALYSIS_BYTES = 64 * 1024 * 1024
MAX_AUDIT_BYTES = 8 * 1024 * 1024
MAX_TEX_BYTES = 128 * 1024


def _load(path, expected_digest, maximum, label):
    path = Path(path)
    raw = Common._read_regular(path, maximum)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_digest:
        raise RenderError("{} digest is not the reviewed production pin".format(label))
    expected_sidecar = "{}  {}\n".format(digest, path.name).encode("ascii")
    if Common._read_regular(Path(str(path) + ".sha256"), 256) != expected_sidecar:
        raise RenderError("{} sidecar differs from its pinned artifact".format(label))
    try:
        data = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RenderError("{} is not ASCII JSON".format(label)) from err
    if raw != Common._canonical_json(data) + b"\n":
        raise RenderError("{} is not canonical ASCII JSON".format(label))
    return data, digest


def _mapping(value, label):
    return Common._mapping(value, label)


def _integer(value, label, minimum=0):
    return Common._integer(value, label, minimum)


def _fraction(record, label):
    return Common._fraction(record, label)


def _predictor(comparison, key):
    predictors = _mapping(comparison.get("predictors"), "predictors")
    row = _mapping(predictors.get(key), "predictor {}".format(key))
    macro = _fraction(row.get("equal_domain_macro"), key + " macro")
    micro = _fraction(row.get("micro_concordance"), key + " micro")
    lodo = _mapping(row.get("leave_one_domain_out"), key + " LODO")
    minimum = _fraction(lodo.get("minimum"), key + " LODO minimum")
    maximum = _fraction(lodo.get("maximum"), key + " LODO maximum")
    values = _mapping(lodo.get("values"), key + " LODO values")
    if len(values) != Protocol.COHORT_DOMAINS:
        raise RenderError("{} LODO domain universe changed".format(key))
    return macro, micro, minimum, maximum


def _support(comparison, label):
    support = _mapping(comparison.get("support"), label + " support")
    for key in (
        "observation_pairs",
        "comparable",
        "tasks_with_comparable_pairs",
        "eligible_domains",
    ):
        _integer(support.get(key), "{} {}".format(label, key))
    by_domain = support.get("by_domain")
    if not isinstance(by_domain, list) or len(by_domain) != Protocol.COHORT_DOMAINS:
        raise RenderError("{} support domain universe changed".format(label))
    return support


def _validate_comparison(comparison, label, predictor_keys):
    comparison = _mapping(comparison, label)
    _support(comparison, label)
    predictors = _mapping(comparison.get("predictors"), label + " predictors")
    if set(predictors) != set(predictor_keys):
        raise RenderError("{} predictor set changed".format(label))
    for key in predictor_keys:
        _predictor(comparison, key)
    return comparison


def _validate_contrast(item, candidate, reference, label):
    item = _mapping(item, label)
    if item.get("candidate") != candidate or item.get("reference") != reference:
        raise RenderError("{} identity changed".format(label))
    if item.get("fixed_task_denominator") != Protocol.COHORT_TASKS:
        raise RenderError("{} task denominator changed".format(label))
    coverage = _mapping(item.get("coverage"), label + " coverage")
    for key in (
        "both_solved",
        "candidate_only",
        "reference_only",
        "both_unsolved",
        "candidate_minus_reference",
    ):
        value = coverage.get(key) if key == "candidate_minus_reference" else coverage.get(key, 0)
        if key == "candidate_minus_reference":
            if type(value) is not int:
                raise RenderError("{} coverage difference is invalid".format(label))
        else:
            _integer(value, "{} {}".format(label, key))
    if sum(coverage.get(key, 0) for key in (
        "both_solved", "candidate_only", "reference_only", "both_unsolved"
    )) != Protocol.COHORT_TASKS:
        raise RenderError("{} coverage outcomes do not conserve tasks".format(label))
    effort = _mapping(item.get("conditional_effort"), label + " effort")
    _integer(effort.get("eligible_pairs"), label + " eligible pairs")
    _integer(effort.get("candidate_total"), label + " candidate effort")
    _integer(effort.get("reference_total"), label + " reference effort")
    _fraction(effort.get("candidate_over_reference"), label + " effort ratio")
    rows = item.get("by_domain")
    if not isinstance(rows, list) or len(rows) != Protocol.COHORT_DOMAINS:
        raise RenderError("{} domain universe changed".format(label))
    return item


def validate_primary(data):
    if data.get("schema") != Primary.SCHEMA:
        raise RenderError("primary analysis schema changed")
    if data.get("protocol") != Protocol.PROTOCOL:
        raise RenderError("holdout measurement protocol changed")
    if data.get("analysis_protocol") != Protocol.ANALYSIS_PROTOCOL:
        raise RenderError("holdout analysis protocol changed")
    if data.get("frozen_protocol_sha256") != Protocol.PROTOCOL_SHA256:
        raise RenderError("holdout protocol digest changed")
    expected_scope = {
        "tasks": Protocol.COHORT_TASKS,
        "domains": Protocol.COHORT_DOMAINS,
        "configurations": Protocol.CONFIG_COUNT,
        "cells": Protocol.CELL_COUNT,
        "minimum_domains": Protocol.MIN_DOMAINS,
        "minimum_tasks_with_comparable_pairs": (
            Protocol.MIN_TASKS_WITH_COMPARABLE_PAIRS
        ),
    }
    if data.get("scope") != expected_scope:
        raise RenderError("holdout scope changed")
    outcomes = _mapping(data.get("terminal_outcomes"), "terminal outcomes")
    if sum(_integer(value, "terminal outcome") for value in outcomes.values()) != (
        Protocol.CELL_COUNT
    ):
        raise RenderError("terminal outcomes do not conserve cells")
    coverage = data.get("coverage")
    if not isinstance(coverage, list) or [row.get("config") for row in coverage] != list(
        Protocol.LABELS
    ):
        raise RenderError("coverage configuration order changed")
    for row in coverage:
        if row.get("tasks") != Protocol.COHORT_TASKS:
            raise RenderError("coverage denominator changed")
        solved = _integer(row.get("solved"), "coverage solved")
        if solved > Protocol.COHORT_TASKS:
            raise RenderError("coverage exceeds its task denominator")
        _fraction(row.get("coverage"), "coverage fraction")

    mechanism = _mapping(data.get("mechanism"), "mechanism")
    expected_mechanism = {
        "representation_shared": ("profile", "width", "add"),
        "profile_quality_shared": ("profile", "quality"),
        "guidance_expanded_states_shared": ("profile", "quality"),
        "guidance_union_effort_shared": ("profile", "quality"),
        "absolute_certificate_shared": ("profile", "width", "add"),
    }
    if set(mechanism) != set(expected_mechanism):
        raise RenderError("mechanism comparison set changed")
    for key, predictors in expected_mechanism.items():
        _validate_comparison(mechanism[key], key, predictors)
    expected_gates = Primary.mechanism_gates(
        mechanism["representation_shared"],
        mechanism["profile_quality_shared"],
        mechanism["guidance_expanded_states_shared"],
        mechanism["guidance_union_effort_shared"],
    )
    if data.get("mechanism_gates") != expected_gates:
        raise RenderError("mechanism gates contradict the frozen analysis")

    contrasts = _mapping(data.get("selector_contrasts"), "selector contrasts")
    expected_contrasts = {
        "matched_width_vs_add",
        "cap_width_vs_exact_width",
        "constrained_vs_unconstrained",
        "selector_vs_profiled_blind",
    }
    if set(contrasts) != expected_contrasts:
        raise RenderError("selector contrast set changed")
    width_add = contrasts.get("matched_width_vs_add")
    cap_exact = contrasts.get("cap_width_vs_exact_width")
    constrained = contrasts.get("constrained_vs_unconstrained")
    selector_blind = contrasts.get("selector_vs_profiled_blind")
    if not isinstance(width_add, list) or len(width_add) != len(
        Protocol.Source.MATCHED_BUDGETS
    ):
        raise RenderError("matched width/ADD contrast grid changed")
    if not isinstance(cap_exact, list) or len(cap_exact) != len(
        Protocol.Source.MATCHED_BUDGETS
    ):
        raise RenderError("cap/exact contrast grid changed")
    if not isinstance(constrained, list) or len(constrained) != 15:
        raise RenderError("constrained/unconstrained contrast grid changed")
    if not isinstance(selector_blind, list) or len(selector_blind) != 16:
        raise RenderError("selector/blind contrast grid changed")
    for (k, u), item in zip(Protocol.Source.MATCHED_BUDGETS, width_add):
        _validate_contrast(
            item,
            "pdb_cap_width_k{}".format(k),
            "pdb_cap_add_u{}".format(u),
            "width/ADD K={}".format(k),
        )
    for (k, _), item in zip(Protocol.Source.MATCHED_BUDGETS, cap_exact):
        _validate_contrast(
            item,
            "pdb_cap_width_k{}".format(k),
            "pdb_exact_k{}".format(k),
            "cap/exact K={}".format(k),
        )
    constrained_index = 0
    for k, u in Protocol.Source.MATCHED_BUDGETS:
        for label in (
            "pdb_exact_k{}".format(k),
            "pdb_cap_width_k{}".format(k),
            "pdb_cap_add_u{}".format(u),
        ):
            _validate_contrast(
                constrained[constrained_index],
                label,
                "pdb_exact_unconstrained",
                "constrained/unconstrained {}".format(label),
            )
            constrained_index += 1
    for label, item in zip(Protocol.LABELS[1:], selector_blind):
        _validate_contrast(
            item,
            label,
            "blind_fw_profiled",
            "selector/blind {}".format(label),
        )
    expected_selector_gates = Primary.selector_gates(contrasts)
    if data.get("selector_gates") != expected_selector_gates:
        raise RenderError("selector gates contradict the frozen analysis")


def validate_denominator(data, primary):
    if data.get("schema") != Denominator.SCHEMA:
        raise RenderError("denominator-audit schema changed")
    if data.get("protocol") != DenominatorProtocol.PROTOCOL:
        raise RenderError("denominator-audit protocol changed")
    if data.get("frozen_protocol_sha256") != DenominatorProtocol.PROTOCOL_SHA256:
        raise RenderError("denominator-audit protocol digest changed")
    denominator = _validate_comparison(
        data.get("denominator_null_shared"),
        "denominator null",
        ("profile", "inverse_union"),
    )
    absolute = _validate_comparison(
        data.get("absolute_certificate_shared"),
        "absolute certificate",
        ("profile", "width", "add"),
    )
    if absolute != primary["mechanism"]["absolute_certificate_shared"]:
        raise RenderError("denominator audit changed the primary absolute comparison")
    if data.get("decision_gates") != Denominator.decision_gates(
        denominator, absolute
    ):
        raise RenderError("denominator gates contradict the frozen audit")


def _row(label, values):
    return "  {} & {} & [{}, {}] \\\\".format(
        label,
        Common._decimal(values[0]),
        Common._decimal(values[2]),
        Common._decimal(values[3]),
    )


def _gate_word(value):
    if type(value) is not bool:
        raise RenderError("gate result is not Boolean")
    return "pass" if value else "fail"


def _selector_rows(contrasts, include_add_budget):
    rows = []
    for (k, u), item in zip(Protocol.Source.MATCHED_BUDGETS, contrasts):
        coverage = item["coverage"]["candidate_minus_reference"]
        effort = item["conditional_effort"]
        cells = [str(k)]
        if include_add_budget:
            cells.append(str(u))
        cells.extend((
            str(coverage),
            Common._decimal(_fraction(
                effort["candidate_over_reference"], "selector effort ratio"
            )),
            str(effort["eligible_pairs"]),
        ))
        rows.append("  {} \\\\".format(" & ".join(cells)))
    return "%\n" + "\n".join(rows)


def _pooled_ratio(contrasts):
    candidate = sum(item["conditional_effort"]["candidate_total"] for item in contrasts)
    reference = sum(item["conditional_effort"]["reference_total"] for item in contrasts)
    if reference <= 0:
        raise RenderError("selector pooled effort denominator is zero")
    return Fraction(candidate, reference)


def _coverage_delta(contrasts):
    return sum(
        item["coverage"]["candidate_minus_reference"]
        for item in contrasts
    )


def _eligible_pairs(contrasts):
    return sum(
        item["conditional_effort"]["eligible_pairs"]
        for item in contrasts
    )


def _selector_stress_rows(groups):
    rows = []
    for label, contrasts in groups:
        rows.append(
            "  {} & {} & {:+d} & {} \\\\".format(
                label,
                Common._decimal(_pooled_ratio(contrasts)),
                _coverage_delta(contrasts),
                _eligible_pairs(contrasts),
            )
        )
    return "%\n" + "\n".join(rows)


def _combined_selector_rows(width_add, cap_exact):
    rows = []
    for (k, u), width_item, cap_item in zip(
        Protocol.Source.MATCHED_BUDGETS, width_add, cap_exact
    ):
        width_ratio = _fraction(
            width_item["conditional_effort"]["candidate_over_reference"],
            "width/ADD effort ratio",
        )
        cap_ratio = _fraction(
            cap_item["conditional_effort"]["candidate_over_reference"],
            "cap/exact effort ratio",
        )
        rows.append(
            "  {} & {} & {} & {} & {} & {} \\\\".format(
                k,
                u,
                width_item["coverage"]["candidate_minus_reference"],
                Common._decimal(width_ratio),
                cap_item["coverage"]["candidate_minus_reference"],
                Common._decimal(cap_ratio),
            )
        )
    return "%\n" + "\n".join(rows)


def render(primary, audit, primary_digest, audit_digest):
    validate_primary(primary)
    validate_denominator(audit, primary)
    mechanism = primary["mechanism"]
    representation = mechanism["representation_shared"]
    profile_quality = mechanism["profile_quality_shared"]
    states = mechanism["guidance_expanded_states_shared"]
    union = mechanism["guidance_union_effort_shared"]
    absolute = mechanism["absolute_certificate_shared"]
    denominator = audit["denominator_null_shared"]

    representation_profile = _predictor(representation, "profile")
    representation_width = _predictor(representation, "width")
    representation_add = _predictor(representation, "add")
    fragmentation_profile = _predictor(profile_quality, "profile")
    fragmentation_quality = _predictor(profile_quality, "quality")
    states_profile = _predictor(states, "profile")
    states_quality = _predictor(states, "quality")
    union_profile = _predictor(union, "profile")
    union_quality = _predictor(union, "quality")
    absolute_profile = _predictor(absolute, "profile")
    absolute_width = _predictor(absolute, "width")
    absolute_add = _predictor(absolute, "add")
    two_effect_rows = "%\n" + "\n".join((
        "  Fragmentation $\\mathit{{frag}}$ & {} & {} \\\\".format(
            Common._decimal(fragmentation_quality[0]),
            Common._decimal(fragmentation_profile[0]),
        ),
        "  Expanded states & {} & {} \\\\".format(
            Common._decimal(states_quality[0]), Common._decimal(states_profile[0])
        ),
        "  Unsplit effort $\\mathit{{unionEffort}}$ & {} & {} \\\\".format(
            Common._decimal(union_quality[0]), Common._decimal(union_profile[0])
        ),
    ))
    representation_rows = "%\n" + "\n".join((
        _row("Cut-aligned profile $\\mathcal{R}_{\\pi}$", representation_profile),
        _row("Maximum width relaxation", representation_width),
        _row("Total-ADD Apply relaxation", representation_add),
    ))
    absolute_rows = "%\n" + "\n".join((
        _row("Cut-aligned profile $\\mathcal{P}_{\\pi}$", absolute_profile),
        _row("Maximum width relaxation", absolute_width),
        _row("Total-ADD Apply relaxation", absolute_add),
    ))

    contrasts = primary["selector_contrasts"]
    width_add = contrasts["matched_width_vs_add"]
    cap_exact = contrasts["cap_width_vs_exact_width"]
    constrained = contrasts["constrained_vs_unconstrained"]
    selector_blind = contrasts["selector_vs_profiled_blind"]
    cap_unconstrained = [
        item for item in constrained
        if item["candidate"].startswith("pdb_cap_width_k")
    ]
    cap_blind = [
        item for item in selector_blind
        if item["candidate"].startswith("pdb_cap_width_k")
    ]
    if len(cap_unconstrained) != 5 or len(cap_blind) != 5:
        raise RenderError("cap-aware selector stress-test grid changed")
    selector_stress_groups = (
        ("All constrained/unconstrained", constrained),
        ("Cap width/unconstrained", cap_unconstrained),
        ("All heuristic selectors/blind", selector_blind),
        ("Cap width/blind", cap_blind),
    )
    mechanism_gates = primary["mechanism_gates"]
    selector_gates = primary["selector_gates"]
    audit_gates = audit["decision_gates"]

    def comparison_macros(prefix, comparison, predictors):
        support = _support(comparison, prefix)
        lines = [
            Common._macro(prefix + "Pairs", str(support["comparable"])),
            Common._macro(
                prefix + "PairTasks", str(support["tasks_with_comparable_pairs"])
            ),
            Common._macro(prefix + "PairDomains", str(support["eligible_domains"])),
        ]
        for macro_name, predictor in predictors:
            values = _predictor(comparison, predictor)
            lines.extend((
                Common._macro(prefix + macro_name + "Macro", Common._decimal(values[0])),
                Common._macro(prefix + macro_name + "Micro", Common._decimal(values[1])),
                Common._macro(prefix + macro_name + "LodoMin", Common._decimal(values[2])),
                Common._macro(prefix + macro_name + "LodoMax", Common._decimal(values[3])),
            ))
        return lines

    lines = [
        "% Generated from the sealed prospective certificate holdout.",
        "% Primary analysis SHA-256: {}".format(primary_digest),
        "% Denominator audit SHA-256: {}".format(audit_digest),
        Common._macro("HoldoutTasks", str(Protocol.COHORT_TASKS)),
        Common._macro("HoldoutDomains", str(Protocol.COHORT_DOMAINS)),
        Common._macro("HoldoutCells", str(Protocol.CELL_COUNT)),
        Common._macro("HoldoutEligibleObservations", str(len(primary["observations"]))),
    ]
    lines.extend(comparison_macros(
        "HoldoutRepresentation",
        representation,
        (("Profile", "profile"), ("Width", "width"), ("Add", "add")),
    ))
    lines.extend(comparison_macros(
        "HoldoutFragment",
        profile_quality,
        (("Profile", "profile"), ("Quality", "quality")),
    ))
    lines.extend(comparison_macros(
        "HoldoutStates",
        states,
        (("Profile", "profile"), ("Quality", "quality")),
    ))
    lines.extend(comparison_macros(
        "HoldoutUnion",
        union,
        (("Profile", "profile"), ("Quality", "quality")),
    ))
    lines.extend(comparison_macros(
        "HoldoutAbsolute",
        absolute,
        (("Profile", "profile"), ("Width", "width"), ("Add", "add")),
    ))
    lines.extend(comparison_macros(
        "HoldoutDenominator",
        denominator,
        (("Profile", "profile"), ("Null", "inverse_union")),
    ))
    lines.extend((
        Common._macro(
            "HoldoutUsefulGate",
            _gate_word(mechanism_gates["useful_fragmentation_certificate"]["pass"]),
        ),
        Common._macro(
            "HoldoutSharperGate",
            _gate_word(mechanism_gates["sharper_representation_predictor"]["pass"]),
        ),
        Common._macro(
            "HoldoutTwoEffectGate",
            _gate_word(mechanism_gates["two_effect_separation"]["pass"]),
        ),
        Common._macro(
            "HoldoutDenominatorGate",
            _gate_word(audit_gates["denominator_artifact_robustness"]["pass"]),
        ),
        Common._macro(
            "HoldoutAbsoluteGate",
            _gate_word(audit_gates["absolute_certificate_robustness"]["pass"]),
        ),
        Common._macro(
            "HoldoutWidthAddGate",
            _gate_word(selector_gates["width_vs_matched_add"]["pass"]),
        ),
        Common._macro(
            "HoldoutCapExactGate",
            _gate_word(selector_gates["cap_width_vs_exact_width"]["pass"]),
        ),
        Common._macro(
            "HoldoutWidthAddPooledRatio", Common._decimal(_pooled_ratio(width_add))
        ),
        Common._macro(
            "HoldoutCapExactPooledRatio", Common._decimal(_pooled_ratio(cap_exact))
        ),
        Common._macro(
            "HoldoutWidthAddCoverageDelta",
            str(sum(item["coverage"]["candidate_minus_reference"] for item in width_add)),
        ),
        Common._macro(
            "HoldoutCapExactCoverageDelta",
            str(_coverage_delta(cap_exact)),
        ),
        Common._macro(
            "HoldoutConstrainedUnconstrainedPooledRatio",
            Common._decimal(_pooled_ratio(constrained)),
        ),
        Common._macro(
            "HoldoutConstrainedUnconstrainedCoverageDelta",
            str(_coverage_delta(constrained)),
        ),
        Common._macro(
            "HoldoutConstrainedUnconstrainedPairs",
            str(_eligible_pairs(constrained)),
        ),
        Common._macro(
            "HoldoutCapUnconstrainedPooledRatio",
            Common._decimal(_pooled_ratio(cap_unconstrained)),
        ),
        Common._macro(
            "HoldoutCapUnconstrainedCoverageDelta",
            str(_coverage_delta(cap_unconstrained)),
        ),
        Common._macro(
            "HoldoutCapUnconstrainedPairs",
            str(_eligible_pairs(cap_unconstrained)),
        ),
        Common._macro(
            "HoldoutAllSelectorsBlindPooledRatio",
            Common._decimal(_pooled_ratio(selector_blind)),
        ),
        Common._macro(
            "HoldoutAllSelectorsBlindCoverageDelta",
            str(_coverage_delta(selector_blind)),
        ),
        Common._macro(
            "HoldoutAllSelectorsBlindPairs",
            str(_eligible_pairs(selector_blind)),
        ),
        Common._macro(
            "HoldoutCapBlindPooledRatio",
            Common._decimal(_pooled_ratio(cap_blind)),
        ),
        Common._macro(
            "HoldoutCapBlindCoverageDelta",
            str(_coverage_delta(cap_blind)),
        ),
        Common._macro(
            "HoldoutCapBlindPairs",
            str(_eligible_pairs(cap_blind)),
        ),
        Common._macro("HoldoutTwoEffectRows", two_effect_rows),
        Common._macro("HoldoutRepresentationRows", representation_rows),
        Common._macro("HoldoutAbsoluteRows", absolute_rows),
        Common._macro(
            "HoldoutSelectorRows", _combined_selector_rows(width_add, cap_exact)
        ),
        Common._macro(
            "HoldoutSelectorStressRows",
            _selector_stress_rows(selector_stress_groups),
        ),
        Common._macro("HoldoutWidthAddRows", _selector_rows(width_add, True)),
        Common._macro("HoldoutCapExactRows", _selector_rows(cap_exact, False)),
    ))
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


def _write_atomic(path, raw):
    path = Path(path)
    if path.resolve() != DEFAULT_OUTPUT.resolve():
        raise RenderError("--write is restricted to the generated-paper path")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
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


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, default=DEFAULT_ANALYSIS)
    parser.add_argument(
        "--denominator-audit", type=Path, default=DEFAULT_DENOMINATOR_AUDIT
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        if any(len(value) != 64 or set(value) == {"0"} for value in (
            EXPECTED_ANALYSIS_SHA256, EXPECTED_DENOMINATOR_AUDIT_SHA256
        )):
            raise RenderError("production digest pins are not finalized")
        return 0
    primary, primary_digest = _load(
        args.analysis, EXPECTED_ANALYSIS_SHA256, MAX_ANALYSIS_BYTES, "primary analysis"
    )
    audit, audit_digest = _load(
        args.denominator_audit,
        EXPECTED_DENOMINATOR_AUDIT_SHA256,
        MAX_AUDIT_BYTES,
        "denominator audit",
    )
    raw = render(primary, audit, primary_digest, audit_digest)
    if args.write:
        _write_atomic(args.output, raw)
    elif args.check:
        if Common._read_regular(args.output, MAX_TEX_BYTES) != raw:
            raise RenderError("generated TeX is stale")
    else:
        print(raw.decode("ascii"), end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RenderError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
