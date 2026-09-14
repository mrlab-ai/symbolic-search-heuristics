"""Paper projections for the explicitly narrower fresh-instance A design."""

from fractions import Fraction

import render_terminal_incidence_results as R


def classify(evidence):
    R._keys(evidence, {"design", "a_pass", "confirmation_a", "source"}, "within-family evidence")
    if evidence["design"] != "within-family-v1" or type(evidence["a_pass"]) is not bool:
        raise R.RenderError("within-family evidence identity changed")
    source = evidence["source"]
    families = source["families"]
    if (source["tasks"] != 650 or not isinstance(families, list)
            or len(families) != len(set(families)) or not 25 <= len(families) <= 30):
        raise R.RenderError("within-family source support changed")
    a = R._validate_a(evidence["confirmation_a"],
                      {"a_tasks": 650, "a_families": len(families)}, include_prior=False)
    passed = R._a_gate(a, include_prior=False)
    if passed != evidence["a_pass"]:
        raise R.RenderError("within-family A decision differs from its numerical evidence")
    branch = R.OutcomeBranch.A_PASS_SELECTORS_UNTESTED if passed else R.OutcomeBranch.A_FAIL
    return R.Outcome(branch, passed, None, None)


def _a_text(evidence, outcome):
    a = evidence["confirmation_a"]
    decision = "passed" if outcome.a_pass else "did not pass"
    return (
        f"Of 650 source-attested tasks, {a['eligible_tasks']} tasks from "
        f"{a['eligible_families']} families supplied a common eligible frontier. "
        f"The target-strict comparison retained {a['comparison_tasks']} tasks "
        f"from {a['comparison_families']} families and {a['target_strict_pairs']} pairs. "
        f"Terminal incidence had equal-family concordance "
        f"{R._fmt(R._fraction(a, 'i_concordance'), threshold=Fraction(13, 20))}. "
        f"The complete within-family gate {decision}. "
        f"The all-strict sensitivity retained {a['all_strict']['pairs']} pairs "
        f"from {a['all_strict']['comparison_tasks']} tasks; choosing by incidence "
        f"had equal-family normalized exact-effort regret "
        f"{R._fmt(R._fraction(a['oracle_regret']['predictors']['incidence'], 'equal_family_regret'))}. "
        "These results concern the retained families and generator settings, not unseen families."
    )


def _compact_rows(evidence):
    a = evidence["confirmation_a"]
    rows = []
    for predictor, label in zip(R.ORDERING_PREDICTORS, R.ORDERING_PREDICTOR_TEX_LABELS):
        if predictor == "incidence":
            values = [R._fraction(a, "i_concordance"), None, None, None]
        else:
            values = [R._fraction(a["baselines"][predictor], key)
                      for key in ("concordance", "margin", "bootstrap_lower", "lofo_minimum")]
        rows.append(label + " & " + " & ".join(
            R._table_fmt(value, threshold=threshold) for value, threshold in zip(
                values, (Fraction(13, 20), Fraction(1, 50), Fraction(0), Fraction(0)))) + r" \\")
    return " ".join(rows)


def render(evidence):
    outcome = classify(evidence)
    source = evidence["source"]
    statuses = source["candidate_status_counts"]
    allowed = {"supported", "unsupported", "memory-excluded", "time-excluded", "wall-excluded"}
    if set(statuses) - allowed or any(type(n) is not int or n < 0 for n in statuses.values()):
        raise R.RenderError("unknown generated-source classification")
    if statuses.get("supported", 0) < 650:
        raise R.RenderError("generated-source support is below the frozen cohort")
    if outcome.a_pass:
        abstract = ("Fresh generated-instance confirmation within previously studied families "
                    "supports terminal incidence as an ordinal predictor of fixed-frontier "
                    "partition effort. Selector improvements remain untested.")
        downstream = "Selector experiments are authorized by A but have not been completed."
        conclusion = ("The evidence supports the ordinal predictor within the tested families "
                      "and generator settings, but establishes no end-to-end selector improvement.")
    else:
        abstract = ("Fresh generated-instance confirmation within previously studied families "
                    "does not pass the complete ordinal-prediction gate; "
                    "the downstream selector comparisons are therefore not run.")
        downstream = "A did not authorize the selector experiments; they were not run."
        conclusion = ("The within-family experiment does not establish the prespecified ordinal "
                      "predictor claim. The certificate results remain valid, while practical "
                      "selector improvements remain untested.")
    source_text = (
        f"The finite generated-source census attempted {sum(statuses.values())} tasks "
        f"from {len(source['families'])} previously studied families. "
        f"It classified {statuses.get('supported', 0)} tasks as supported and "
        f"{statuses.get('unsupported', 0)} as unsupported. "
        f"Memory, CPU-time and wall-time exclusions were "
        f"{statuses.get('memory-excluded', 0)}, {statuses.get('time-excluded', 0)} and "
        f"{statuses.get('wall-excluded', 0)}, respectively. "
        "Fixed family/size quotas selected 650 A tasks without heuristic outcomes; "
        "unselected reserve tasks do not enter the predictor test."
    )
    macros = {
        "TIOutcomeTitle": R._title(outcome), "TIOutcomeAbstract": abstract,
        "TIOutcomeA": _a_text(evidence, outcome),
        "TIOutcomeACompactRows": _compact_rows(evidence),
        "TIOutcomeAPredictorRows": R._a_predictor_rows(evidence),
        "TIOutcomeADiagnosticRows": R._a_diagnostic_rows(evidence),
        "TIOutcomeAConstructionRows": R._a_construction_rows(evidence),
        "TIOutcomeAFrontierRows": R._a_frontier_rows(evidence),
        "TIOutcomeATimingRows": R._a_timing_rows(evidence),
        "TIOutcomeMetricChoice": downstream, "TIOutcomeB": downstream,
        "TIOutcomeConclusion": conclusion, "TIOutcomeSourceAudit": source_text,
        "TIOutcomeSourceExclusionRows": " ".join(
            f"{key.replace('-', ' ')} & {statuses.get(key, 0)} \\\\" for key in sorted(allowed)),
        "TIOutcomeHardware": ("Per-cell execution receipts retain the processor model, "
                              "host, CPU affinity and scheduler allocation."),
    }
    for name in ("TIOutcomeMetricMechanismRows", "TIOutcomeMetricOutcomeRows", "TIOutcomeBConfigurationRows",
                 "TIOutcomeBAlternativeRows", "TIOutcomeBOutcomeRows", "TIOutcomeBOverheadRows"):
        macros[name] = ""
    return "% Generated from sealed within-family A evidence; do not edit.\n" + "".join(
        f"\\newcommand{{\\{name}}}{{{body}}}\n" for name, body in macros.items())
