#!/usr/bin/env python3
"""Frozen, read-only SymK-versus-CPDDL analysis on finalist-v1.

This contract is frozen before either finalist-v1 experiment is launched.  It
validates the complete SymK finalist matrix and the complete three-manifest
CPDDL GHSETA matrix through their existing validators, but it reports only the
92-task finalist-v1 intersection.  Pilot50 and cap-v2 outcomes are never
eligible for a cross-planner statistic.

Every selected SymK family role and the three fixed SymK controls are compared
in a declared order with two external configurations:

* primary: CPDDL's vendored-README bidirectional forward-A+I/blind-backward;
* secondary: CPDDL's forward A+I configuration (direction matched to SymK).

The analyzer performs no selection or ranking and only writes its report to
stdout.  Domain-macro coverage differences are primary.  Task-micro and
population-post-stratified differences are descriptive; runtime and PAR2 are
one-repetition screening summaries.
"""

import argparse
import copy
import hashlib
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import analyze_cpddl_ghseta as cpddl_analyzer
import analyze_heuristic_choices_pilot as screen_analyzer
import analyze_heuristic_finalists_validation as symk_analyzer
import analyze_ms_caps_pilot as cap_analyzer
import exp_heuristic_finalists_validation as symk_runner


TIME_LIMIT = 300.0
MEMORY_LIMIT_MIB = 8192.0
REPETITIONS = 1
EXPECTED_TASKS = 92
EXPECTED_DOMAINS = 46
PROTOCOL = "cross-planner-finalists-v1"

PRIMARY_EXTERNAL = "cpddl_ghseta_bi_a_plus_i_blind"
SECONDARY_EXTERNAL = "cpddl_ghseta_fw_a_plus_i"
EXTERNAL_COMPARATORS = (
    {
        "role": "primary-readme-bidirectional",
        "label": PRIMARY_EXTERNAL,
        "status": "primary external comparator; vendored-README recommended configuration",
    },
    {
        "role": "secondary-direction-matched-forward",
        "label": SECONDARY_EXTERNAL,
        "status": "secondary direction-matched external comparator",
    },
)

# The cross-planner interval deliberately reuses the already frozen CPDDL
# cluster-bootstrap implementation and seed.  The context starts with this
# protocol identifier, so it occupies a separate deterministic stream.
BOOTSTRAP_SEED = cpddl_analyzer.BOOTSTRAP_SEED
BOOTSTRAP_REPLICATES = cpddl_analyzer.BOOTSTRAP_REPLICATES
BOOTSTRAP_CONFIDENCE = cpddl_analyzer.BOOTSTRAP_CONFIDENCE
BOOTSTRAP_METHOD = "SHAKE256 domain-cluster percentile, Hyndman-Fan type 7"

# These are the exact pre-launch validator sources reviewed as one composed
# contract.  Their own data/configuration pins remain authoritative; these
# hashes ensure a later helper edit cannot silently change cross analysis.
EXPECTED_VALIDATOR_SHA256 = {
    "exp_common.py": (
        "3c8d7004fb5cda229fc78e003ae296ca28f5c0f13f0900633a5cf8902b2298a2"),
    "wbh_parser.py": (
        "d3e96b44fd11133660eac4807a08ba9a99c9f3ad90ea44acf21efc8755aa508c"),
    "validate_wbh_log.py": (
        "26332e0387d4ff8d106d580cfb4595dd47f52d95bc579a0cda3ddf0850afd796"),
    "analyze_cpddl_ghseta.py": (
        "0d1ed91f970cd869ab172847b6c82ccb53a7039dc51becd5696b0ed691482435"),
    "analyze_heuristic_choices_pilot.py": (
        "af2f4d253eebfea5b8d73cea9f928461b7a20947ade99d0429acbf15dc298331"),
    "analyze_heuristic_finalists_validation.py": (
        "5355d310df4ff698f86af5c82395beb80bfaad406ce08a0a5cfaab6ca6655a50"),
    "analyze_ms_caps_pilot.py": (
        "d49b311d8daa375956b8adde5a4e8fdb7a45760656acea147f2bb1ebb4026f20"),
    "exp_heuristic_choices_pilot.py": (
        "b2cca9343006602bac7ebf96ad65fc5ebd81246dcd3441e8d1b4dca558d56aab"),
    "exp_heuristic_finalists_validation.py": (
        "9ffa391a55d9470e27390bdb445cbe7822251ea31306762ecf9870e915591bfc"),
    "suite_cost_manifest.py": (
        "7ab321838bc8d01ac42bbd37a0c9707ed401bbea41cd9ae7527a242b5c1ec2f8"),
}


class AnalysisError(Exception):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as err:
        raise AnalysisError("cannot hash validator {}: {}".format(path, err))
    return digest.hexdigest()


def validate_validator_sources():
    observed = {}
    for filename, wanted in EXPECTED_VALIDATOR_SHA256.items():
        path = SCRIPT_DIR / filename
        actual = sha256_file(path)
        observed[filename] = actual
        if actual != wanted:
            raise AnalysisError(
                "validator source {} changed: {} != {}; freeze a new cross-"
                "analysis contract before opening outcomes".format(
                    filename, actual, wanted))
    return observed


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Validate and compare frozen SymK/CPDDL finalist-v1 results "
            "without selecting or ranking on reserved outcomes."))
    parser.add_argument(
        "symk_properties", nargs="?",
        help="SymK finalist Lab properties JSON, directory, or archive.")
    parser.add_argument(
        "cpddl_properties", nargs="?",
        help="Complete 1404-cell CPDDL Lab properties JSON, directory, or archive.")
    parser.add_argument(
        "--selection", type=Path,
        help="Exact reviewed selection artifact used by the SymK runner.")
    parser.add_argument(
        "--pilot-manifest", type=Path,
        default=cpddl_analyzer.DEFAULT_PILOT_MANIFEST)
    parser.add_argument(
        "--cap-v2-manifest", type=Path,
        default=cpddl_analyzer.DEFAULT_CAP_V2_MANIFEST)
    parser.add_argument(
        "--finalist-v1-manifest", type=Path,
        default=cpddl_analyzer.DEFAULT_FINALIST_V1_MANIFEST)
    parser.add_argument(
        "--smoke-manifest", type=Path,
        default=cpddl_analyzer.DEFAULT_SMOKE_MANIFEST)
    parser.add_argument(
        "--cost-manifest", type=Path,
        default=cpddl_analyzer.DEFAULT_COST_MANIFEST,
        help="Frozen checksum-validated suite cost/source manifest.")
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run synthetic acceptance, mutation, and statistic tests only.")
    args = parser.parse_args(argv)
    if args.self_test and any((
            args.symk_properties, args.cpddl_properties, args.selection)):
        parser.error(
            "--self-test does not accept properties or a selection artifact")
    return args


def validate_frozen_declarations(config_by_label=None):
    """Fail closed if either predeclared CPDDL comparator drifts."""
    configs = (cpddl_analyzer.CONFIG_BY_LABEL if config_by_label is None
               else config_by_label)
    expected = {
        PRIMARY_EXTERNAL: {
            "direction": "bidirectional",
            "fw_objective": "A+I",
            "bw_objective": "none",
            "readme_recommended": True,
            "options": (
                "--fdr-tnfm", "--symba", "bi", "--symba-fw-pot",
                "--symba-fw-pot-cfg", "A+I",
            ),
        },
        SECONDARY_EXTERNAL: {
            "direction": "forward",
            "fw_objective": "A+I",
            "bw_objective": "none",
            "readme_recommended": False,
            "options": (
                "--fdr-tnfm", "--symba", "fw", "--symba-fw-pot",
                "--symba-fw-pot-cfg", "A+I",
            ),
        },
    }
    for label, fields in expected.items():
        config = configs.get(label)
        if config is None:
            raise AnalysisError("frozen external comparator is absent: {}".format(label))
        for field, wanted in fields.items():
            if config.get(field) != wanted:
                raise AnalysisError(
                    "external comparator {} has {}={!r}; expected {!r}".format(
                        label, field, config.get(field), wanted))
    if TIME_LIMIT != cpddl_analyzer.TIME_LIMIT:
        raise AnalysisError("cross-planner and CPDDL time limits differ")
    if MEMORY_LIMIT_MIB != cpddl_analyzer.MEMORY_LIMIT_MIB:
        raise AnalysisError("cross-planner and CPDDL memory limits differ")
    if REPETITIONS != cpddl_analyzer.REPETITIONS:
        raise AnalysisError("cross-planner and CPDDL repetitions differ")


def task_tuple(task):
    if isinstance(task, str):
        fields = task.split(":", 1)
        if len(fields) != 2:
            raise AnalysisError("invalid task label {!r}".format(task))
        return tuple(fields)
    return tuple(task)


def task_text(task):
    return "{}:{}".format(*task)


def frozen_symk_entries(artifact, configs):
    """Return logical roles without deduplicating role aliases.

    The runner deduplicates identical search strings.  A selected M&S family
    finalist can therefore share a physical validation label with the primary
    cap.  Keeping both logical rows makes every predeclared family role visible
    while making the shared underlying label explicit.
    """
    by_label = {config["label"]: config for config in configs}
    entries = []
    fixed = (
        ("control-blind-forward", "blind_fw", "control"),
        ("control-ms-exact", "ms_exact", "control"),
    )
    for role, label, wanted_role in fixed:
        config = by_label.get(label)
        if config is None or config.get("role") != wanted_role:
            raise AnalysisError("missing or misclassified SymK {}".format(label))
        entries.append({"role": role, "family": config["family"], "label": label})

    caps = [config for config in configs if config.get("role") == "primary-cap"]
    if len(caps) != 1:
        raise AnalysisError("expected exactly one independently selected primary cap")
    selected_cap = symk_runner.selected_cap_number(
        artifact["cap_pilot"]["selected_label"])
    expected_cap = "ms_cap{}".format(selected_cap)
    if caps[0]["label"] != expected_cap:
        raise AnalysisError(
            "primary-cap validation label {} differs from artifact {}".format(
                caps[0]["label"], expected_cap))
    entries.append({
        "role": "control-primary-cap",
        "family": "ms",
        "label": caps[0]["label"],
    })

    for family in ("ms", "pdb", "potential"):
        selected = artifact["family_finalists"].get(family)
        if selected is None:
            raise AnalysisError("selection artifact omits {} finalist".format(family))
        label = symk_analyzer.validation_label_for_search(
            configs, selected["search"])
        entries.append({
            "role": "selected-{}-family-finalist".format(family),
            "family": family,
            "label": label,
            "selected_artifact_label": selected["label"],
        })
    if len(entries) != 6:
        raise AssertionError("internal SymK role contract must have six entries")
    return entries


def validate_task_contract(symk_tasks, manifests):
    tasks = tuple(task_tuple(task) for task in symk_tasks)
    finalist = tuple(manifests[cpddl_analyzer.FINALIST_V1])
    if tasks != finalist:
        raise AnalysisError(
            "SymK task order/set differs from exact CPDDL finalist-v1 manifest")
    if len(tasks) != EXPECTED_TASKS or len(set(tasks)) != EXPECTED_TASKS:
        raise AnalysisError("cross-planner set must contain 92 unique tasks")
    by_domain = defaultdict(int)
    for domain, _ in tasks:
        by_domain[domain] += 1
    if len(by_domain) != EXPECTED_DOMAINS or set(by_domain.values()) != {2}:
        raise AnalysisError("cross-planner set must contain two tasks in 46 domains")
    forbidden = (
        set(manifests[cpddl_analyzer.PILOT])
        | set(manifests[cpddl_analyzer.CAP_V2]))
    overlap = set(tasks) & forbidden
    if overlap:
        raise AnalysisError(
            "finalist-v1 cross-planner set includes pooled pilot/cap-v2 rows: {}".format(
                ", ".join(task_text(task) for task in sorted(overlap))))
    return tasks


def _distinct_costs(entries):
    distinct = []
    for planner, label, cost in entries:
        if not any(cap_analyzer.equal_values(cost, old) for old in distinct):
            distinct.append(cost)
    return distinct


def validate_cross_provenance_and_costs(
        tasks, symk_matrix, symk_configs, artifact, cost_info, cpddl_matrix):
    """Check attestations and solved evidence across planner boundaries."""
    finalist = cpddl_analyzer.FINALIST_V1
    expected_source = cost_info["file_sha256"]
    expected_selected = cost_info["task_sources_sha256"][finalist]
    validation = artifact["validation"]
    if validation["source_manifest_sha256"] != expected_source:
        raise AnalysisError(
            "SymK artifact and CPDDL cost-source manifest hashes differ")
    if validation["task_sources_sha256"] != expected_selected:
        raise AnalysisError(
            "SymK and CPDDL finalist-v1 task-source attestations differ")

    symk_labels = [config["label"] for config in symk_configs]
    for task in tasks:
        entries = []
        for label in symk_labels:
            record = symk_matrix[(label, task)]
            if cap_analyzer.outcome(record) is True:
                entries.append((
                    "SymK", label, cap_analyzer.solution_cost(record)))
        cpddl_records = []
        for label in cpddl_analyzer.ALGORITHMS:
            record = cpddl_matrix[(label, finalist, task[0], task[1])]
            cpddl_records.append((label, record))
            if cpddl_analyzer.solved(record):
                entries.append(("CPDDL", label, record.get("solution_cost")))
        if len(_distinct_costs(entries)) > 1:
            raise AnalysisError(
                "cross-planner solved-cost disagreement on {}: {}".format(
                    task_text(task), ", ".join(
                        "{}/{}={}".format(planner, label, cost)
                        for planner, label, cost in entries)))
        if any(cap_analyzer.outcome(
                symk_matrix[(label, task)]) is True for label in symk_labels):
            contradicted = [
                label for label, record in cpddl_records
                if record.get("outcome") == "proved_unsolvable"]
            if contradicted:
                raise AnalysisError(
                    "CPDDL proves {} unsolvable while SymK solves it: {}".format(
                        task_text(task), ", ".join(contradicted)))


def build_view(tasks, symk_matrix, symk_configs, cpddl_matrix):
    """Normalize only finalist-v1 rows; other CPDDL manifests cannot enter."""
    view = {}
    for config in symk_configs:
        label = config["label"]
        for task in tasks:
            record = symk_matrix[(label, task)]
            view[("symk", label, task)] = {
                "solved": cap_analyzer.outcome(record) is True,
                "cost": cap_analyzer.solution_cost(record),
                "time": cap_analyzer.number(record.get("planner_time")),
                "time_field": "planner_time",
            }
    for comparator in EXTERNAL_COMPARATORS:
        label = comparator["label"]
        for task in tasks:
            record = cpddl_matrix[(
                label, cpddl_analyzer.FINALIST_V1, task[0], task[1])]
            view[("cpddl", label, task)] = {
                "solved": cpddl_analyzer.solved(record),
                "cost": record.get("solution_cost"),
                "time": cpddl_analyzer.finite_number(record.get("total_time")),
                "time_field": "total_time",
            }
    expected = len(tasks) * (len(symk_configs) + len(EXTERNAL_COMPARATORS))
    if len(view) != expected:
        raise AnalysisError(
            "normalized finalist-only view has {} cells; expected {}".format(
                len(view), expected))
    return view


def population_domain_counts(cost_info, cost_class=None):
    counts = defaultdict(int)
    for record in cost_info["records"].values():
        selected = (
            cost_class is None
            or (cost_class == "supported"
                and record["cost_class"] == "positive-cost"
                and record["num_normalized_axioms"] == 0)
            or record["cost_class"] == cost_class)
        if selected:
            counts[record["domain"]] += 1
    return counts


def poststratified(domain_values, population_counts):
    represented = sum(population_counts.get(domain, 0)
                      for domain in domain_values)
    if represented <= 0:
        return None
    return math.fsum(
        population_counts.get(domain, 0) * value
        for domain, value in domain_values.items()) / represented


def configuration_score(view, planner, label, tasks, population_counts):
    solved_values = []
    times = []
    par2_values = []
    by_domain = defaultdict(list)
    for task in tasks:
        record = view[(planner, label, task)]
        value = int(record["solved"])
        solved_values.append(value)
        by_domain[task[0]].append(value)
        if record["solved"]:
            if record["time"] is None or record["time"] < 0:
                raise AnalysisError("validated solved cell lacks runtime")
            times.append(record["time"])
            par2_values.append(record["time"])
        else:
            par2_values.append(2.0 * TIME_LIMIT)
    domain_coverages = {
        domain: statistics.mean(values) for domain, values in by_domain.items()}
    return {
        "tasks": len(tasks),
        "solved": sum(solved_values),
        "micro": statistics.mean(solved_values),
        "domain_macro": statistics.mean(domain_coverages.values()),
        "poststratified": poststratified(domain_coverages, population_counts),
        "par2": statistics.mean(par2_values),
        "median_solved_time": statistics.median(times) if times else None,
    }


def paired_score(
        view, symk_label, cpddl_label, tasks, population_counts, context):
    differences = []
    domain_values = defaultdict(list)
    wins = losses = 0
    runtime_ratios = []
    for task in tasks:
        candidate = view[("symk", symk_label, task)]
        reference = view[("cpddl", cpddl_label, task)]
        difference = int(candidate["solved"]) - int(reference["solved"])
        wins += difference == 1
        losses += difference == -1
        differences.append(difference)
        domain_values[task[0]].append(difference)
        if (candidate["solved"] and reference["solved"]
                and candidate["time"] is not None
                and reference["time"] is not None
                and candidate["time"] > 0 and reference["time"] > 0):
            runtime_ratios.append(candidate["time"] / reference["time"])
    domain_deltas = {
        domain: statistics.mean(values)
        for domain, values in domain_values.items()}
    interval = cpddl_analyzer.domain_cluster_bootstrap_ci(
        domain_deltas, "{}\0{}".format(PROTOCOL, context))
    ratio = None
    if runtime_ratios:
        ratio = math.exp(math.fsum(
            math.log(value) for value in runtime_ratios)
                         / len(runtime_ratios))
    return {
        "tasks": len(tasks),
        "domains": len(domain_deltas),
        "domain_macro": statistics.mean(domain_deltas.values()),
        "ci_low": interval[0],
        "ci_high": interval[1],
        "wins": wins,
        "losses": losses,
        "micro": statistics.mean(differences),
        "poststratified": poststratified(domain_deltas, population_counts),
        "runtime_ratio": ratio,
        "runtime_n": len(runtime_ratios),
    }


def fmt(value, digits=6):
    return "NA" if value is None else "{:.{}f}".format(value, digits)


def render_subset(
        name, tasks, view, symk_configs, symk_entries, population_counts):
    lines = [
        "",
        "=== {}: {} tasks / {} represented domains ===".format(
            name, len(tasks), len({task[0] for task in tasks})),
        "configuration coverage and timing (coverage descriptive; timing screening only)",
        ("  planner/config | solved | micro coverage | domain-macro coverage | "
         "poststratified coverage | PAR2 | median solved time"),
    ]
    identities = [("symk", config["label"]) for config in symk_configs]
    identities.extend(("cpddl", item["label"])
                      for item in EXTERNAL_COMPARATORS)
    for planner, label in identities:
        score = configuration_score(
            view, planner, label, tasks, population_counts)
        lines.append(
            "  {}/{} | {}/{} | {} | {} | {} | {} | {}".format(
                planner, label, score["solved"], score["tasks"],
                fmt(score["micro"]), fmt(score["domain_macro"]),
                fmt(score["poststratified"]), fmt(score["par2"]),
                fmt(score["median_solved_time"])))

    lines.extend([
        "",
        "predeclared cross-planner coverage contrasts (SymK - CPDDL)",
        ("  SymK logical role [validation label] vs external role [label] | "
         "domain-macro | 95% domain-cluster CI | discordant W/L | "
         "micro(desc) | poststratified(desc) | runtime ratio(screen,n) | status"),
    ])
    for entry in symk_entries:
        for comparator in EXTERNAL_COMPARATORS:
            context = "\0".join((
                name, entry["role"], entry["label"],
                comparator["role"], comparator["label"]))
            score = paired_score(
                view, entry["label"], comparator["label"], tasks,
                population_counts, context)
            lines.append(
                "  {} [{}] vs {} [{}] | {} | [{},{}] | {}/{} | {} | {} | "
                "{} ({}) | {}".format(
                    entry["role"], entry["label"], comparator["role"],
                    comparator["label"], fmt(score["domain_macro"]),
                    fmt(score["ci_low"]), fmt(score["ci_high"]),
                    score["wins"], score["losses"], fmt(score["micro"]),
                    fmt(score["poststratified"]),
                    fmt(score["runtime_ratio"]), score["runtime_n"],
                    comparator["status"]))
    return lines


def render_report(
        symk_source, cpddl_source, artifact_sha256, tasks, view,
        symk_configs, symk_entries, cost_info):
    lines = [
        "Frozen SymK/CPDDL finalist-v1 cross-planner analysis",
        "SymK source: {}".format(symk_source),
        "CPDDL source: {}".format(cpddl_source),
        "selection artifact SHA-256: {}".format(artifact_sha256),
        "validated SymK cells: {}".format(len(tasks) * len(symk_configs)),
        "validated CPDDL cells: {} (all three manifests)".format(
            cpddl_analyzer.EXPECTED_CELLS),
        "reported task set: finalist-v1 only (92 tasks; pilot50/cap-v2 excluded)",
        "effect orientation: SymK minus CPDDL",
        "selection/ranking rule: none; every logical SymK role is retained",
        "primary external comparator: {}".format(PRIMARY_EXTERNAL),
        "secondary direction-matched comparator: {}".format(
            SECONDARY_EXTERNAL),
        ("domain-cluster CI: {} fixed-seed {:.0f}% percentile replicates; "
         "seed={!r}; method={}".format(
             BOOTSTRAP_REPLICATES, 100 * BOOTSTRAP_CONFIDENCE,
             BOOTSTRAP_SEED, BOOTSTRAP_METHOD)),
        "cost/source manifest SHA-256: {}".format(cost_info["file_sha256"]),
        "finalist-v1 task-source SHA-256: {}".format(
            cost_info["task_sources_sha256"][cpddl_analyzer.FINALIST_V1]),
    ]
    supported_tasks = tuple(
        task for task in tasks if task in cost_info["supported"])
    if supported_tasks != tasks:
        raise AnalysisError(
            "frozen finalist-v1 contains tasks outside the supported "
            "positive-cost, axiom-free population")
    lines.extend(render_subset(
        "supported positive-cost, axiom-free finalist-v1 set (PRIMARY)",
        supported_tasks, view,
        symk_configs, symk_entries,
        population_domain_counts(cost_info, "supported")))
    lines.extend([
        "",
        "Interpretation contract",
        "- Domain-macro paired coverage differences are primary.",
        ("- Task-micro and 1377-task supported-population post-stratified "
         "coverage values are descriptive."),
        ("- Every interval resamples represented domains with replacement; "
         "all sampled tasks in a drawn domain remain together."),
        ("- Runtime/PAR2 use one run per cell and are screening only. SymK "
         "uses planner_time; CPDDL uses total_time."),
        ("- The primary CPDDL comparator is the bidirectional configuration "
         "recommended in the vendored README; the secondary forward A+I "
         "comparator controls search direction."),
        ("- No pilot50 or cap-v2 record enters either reported subset, and "
         "no reserved outcome promotes, drops, or reorders a method."),
        "",
        ("PASS: exact matrices, selection, revision/config/resource/limit "
         "provenance, source attestations, and within/across-planner solved "
         "cost agreement validated."),
    ])
    return "\n".join(lines) + "\n"


def synthetic_artifact(cost_info):
    artifact = symk_runner.template_artifact()
    artifact["screen"]["properties_canonical_sha256"] = "1" * 64
    artifact["screen"]["source_manifest_sha256"] = cost_info["file_sha256"]
    artifact["screen"]["task_sources_sha256"] = cost_info[
        "task_sources_sha256"][cpddl_analyzer.PILOT]
    artifact["cap_pilot"]["properties_canonical_sha256"] = "2" * 64
    artifact["cap_pilot"]["selected_label"] = "ms_cap8"
    searches = dict(screen_analyzer.CONFIGS)
    artifact["family_finalists"] = {
        "ms": {"label": "ms_cap8", "search": searches["ms_cap8"]},
        "pdb": {"label": "pdb_goal_w4", "search": searches["pdb_goal_w4"]},
        "potential": {
            "label": "pot_rect_m16_w16",
            "search": searches["pot_rect_m16_w16"],
        },
    }
    configs = screen_analyzer.validation_configs(
        8, artifact["family_finalists"])
    artifact["validation"].update({
        "source_manifest_sha256": cost_info["file_sha256"],
        "task_sources_sha256": cost_info["task_sources_sha256"][
            cpddl_analyzer.FINALIST_V1],
        "configs": configs,
        "expected_run_count": EXPECTED_TASKS * len(configs),
    })
    return artifact


def synthetic_symk_records(tasks, configs, artifact, artifact_sha256, cost_info):
    all_cost_records = cost_info["records"]
    records = []
    for config_index, config in enumerate(configs):
        for task_index, task in enumerate(tasks):
            solved = int((task_index + 2 * config_index) % 5 != 0)
            # CPDDL's synthetic fixture assigns this same task-specific cost.
            # Find it from a solved CPDDL fixture's deterministic task order via
            # the canonical record marker added below by the self-test.
            cost = all_cost_records[task]["_synthetic_solution_cost"]
            record = symk_analyzer.synthetic_record(
                config["label"], config["search"], task, solved, cost,
                2.0 + task_index / 100.0 + config_index / 10.0,
                artifact, artifact_sha256, EXPECTED_TASKS * len(configs))
            record["source_manifest_sha256"] = cost_info["file_sha256"]
            record["task_sources_sha256"] = cost_info[
                "task_sources_sha256"][cpddl_analyzer.FINALIST_V1]
            records.append(record)
    return records


def _expect_error(name, function):
    try:
        function()
    except (AnalysisError, cpddl_analyzer.AnalysisError,
            symk_runner.ProtocolError):
        return name
    raise AssertionError("synthetic mutation was accepted: {}".format(name))


def self_test(manifests):
    validate_frozen_declarations()
    cpddl_records, cost_info = cpddl_analyzer.synthetic_fixture(manifests)
    all_tasks = [
        task for manifest in cpddl_analyzer.MANIFEST_ORDER
        for task in manifests[manifest]]
    for task in all_tasks:
        cost_info["records"][task]["_synthetic_solution_cost"] = (
            10 + all_tasks.index(task))
    # The extra synthetic-only field is not consulted by the CPDDL validator.
    cpddl_matrix = cpddl_analyzer.validate_records(
        cpddl_records, manifests, cost_info)
    tasks = validate_task_contract(
        manifests[cpddl_analyzer.FINALIST_V1], manifests)
    artifact = synthetic_artifact(cost_info)
    artifact_sha256 = hashlib.sha256(json.dumps(
        artifact, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    configs = symk_runner.validate_artifact(
        artifact,
        expected_source_manifest_sha256=cost_info["file_sha256"],
        expected_task_sources_sha256=cost_info["task_sources_sha256"][
            cpddl_analyzer.FINALIST_V1],
        expected_screen_source_manifest_sha256=cost_info["file_sha256"],
        expected_screen_task_sources_sha256=cost_info["task_sources_sha256"][
            cpddl_analyzer.PILOT])
    symk_records = synthetic_symk_records(
        tasks, configs, artifact, artifact_sha256, cost_info)
    symk_matrix, errors, warnings = symk_analyzer.validate_records(
        symk_records, tasks, configs, artifact, artifact_sha256,
        cost_info["task_sources_sha256"][cpddl_analyzer.FINALIST_V1],
        cost_info["file_sha256"], expected_run_count=len(symk_records))
    assert not errors and not warnings, (errors, warnings)
    validate_cross_provenance_and_costs(
        tasks, symk_matrix, configs, artifact, cost_info, cpddl_matrix)
    entries = frozen_symk_entries(artifact, configs)
    view = build_view(tasks, symk_matrix, configs, cpddl_matrix)
    assert all(key[2] in set(tasks) for key in view)

    # Pin repeatability on one full-set contrast without using an outcome to
    # define either member or the bootstrap context.
    population = population_domain_counts(cost_info)
    first = paired_score(
        view, entries[0]["label"], PRIMARY_EXTERNAL, tasks, population,
        "synthetic-repeatability")
    second = paired_score(
        view, entries[0]["label"], PRIMARY_EXTERNAL, tasks, population,
        "synthetic-repeatability")
    assert (first["ci_low"], first["ci_high"]) == (
        second["ci_low"], second["ci_high"])

    tests = []
    tests.append(_expect_error(
        "pooled pilot row", lambda: validate_task_contract(
            tasks[:-1] + (manifests[cpddl_analyzer.PILOT][0],), manifests)))

    def cross_cost_disagreement():
        candidate = copy.deepcopy(symk_matrix)
        target_task = next(
            task for task in tasks
            if any(cpddl_analyzer.solved(cpddl_matrix[(
                label, cpddl_analyzer.FINALIST_V1, task[0], task[1])])
                   for label in cpddl_analyzer.ALGORITHMS))
        target = next(
            candidate[(config["label"], target_task)] for config in configs
            if cap_analyzer.outcome(
                candidate[(config["label"], target_task)]) is True)
        target["solution_cost"] += 1
        validate_cross_provenance_and_costs(
            tasks, candidate, configs, artifact, cost_info, cpddl_matrix)

    tests.append(_expect_error(
        "cross-planner cost disagreement", cross_cost_disagreement))

    def source_disagreement():
        changed = copy.deepcopy(cost_info)
        changed["file_sha256"] = "f" * 64
        validate_cross_provenance_and_costs(
            tasks, symk_matrix, configs, artifact, changed, cpddl_matrix)

    tests.append(_expect_error("cross-planner source disagreement", source_disagreement))

    def comparator_drift():
        changed = copy.deepcopy(cpddl_analyzer.CONFIG_BY_LABEL)
        changed[PRIMARY_EXTERNAL]["readme_recommended"] = False
        validate_frozen_declarations(changed)

    tests.append(_expect_error("primary comparator drift", comparator_drift))

    def selection_drift():
        changed = copy.deepcopy(artifact)
        changed["family_finalists"]["pdb"]["search"] = "tampered()"
        symk_runner.validate_artifact(changed)

    tests.append(_expect_error("selection artifact drift", selection_drift))

    def symk_extra_row():
        changed = copy.deepcopy(symk_records)
        changed.append(copy.deepcopy(changed[0]))
        _, changed_errors, _ = symk_analyzer.validate_records(
            changed, tasks, configs, artifact, artifact_sha256,
            cost_info["task_sources_sha256"][cpddl_analyzer.FINALIST_V1],
            cost_info["file_sha256"], expected_run_count=len(symk_records))
        if changed_errors:
            raise AnalysisError("expected rejection: {}".format(changed_errors[0]))

    tests.append(_expect_error("extra SymK row", symk_extra_row))

    def cpddl_binary_drift():
        changed = copy.deepcopy(cpddl_records)
        changed[0]["cpddl_binary_sha256"] = "0" * 64
        cpddl_analyzer.validate_records(changed, manifests, cost_info)

    tests.append(_expect_error("CPDDL executable drift", cpddl_binary_drift))

    # Render with the production 10k interval method and assert the report
    # exposes all twelve logical comparisons in the frozen primary subset.
    report = render_report(
        "synthetic-symk", "synthetic-cpddl", artifact_sha256, tasks,
        view, configs, entries, cost_info)
    assert report.count("selected-ms-family-finalist") == 2
    assert report.count("selected-pdb-family-finalist") == 2
    assert report.count("selected-potential-family-finalist") == 2
    assert report.count("primary-readme-bidirectional") == 6
    assert report.count(
        "primary external comparator; vendored-README recommended configuration") == 6
    assert report.count(
        "secondary direction-matched external comparator") == 6
    assert " | None | " not in report
    assert "pilot50/cap-v2 excluded" in report
    assert "selection/ranking rule: none" in report
    assert "within/across-planner solved cost agreement validated" in report

    print("cross-planner finalist analyzer synthetic self-tests: PASS")
    print("accepted matrices: {} SymK cells; {} CPDDL cells".format(
        len(symk_records), len(cpddl_records)))
    print("reported intersection: 92 finalist-v1 tasks, 46 domains")
    print("rejection checks: {}".format(", ".join(tests)))
    print("fixed comparisons: 6 SymK logical roles x 2 CPDDL comparators")


def main(argv=None):
    args = parse_args(argv)
    validate_validator_sources()
    validate_frozen_declarations()
    cpddl_analyzer.validate_runner_source()
    manifests = cpddl_analyzer.load_manifests(
        args.pilot_manifest, args.cap_v2_manifest,
        args.finalist_v1_manifest)
    if args.self_test:
        self_test(manifests)
        return 0
    if (args.symk_properties is None or args.cpddl_properties is None
            or args.selection is None):
        raise AnalysisError(
            "SymK properties, CPDDL properties, and --selection are required")
    if args.symk_properties == "-" and args.cpddl_properties == "-":
        raise AnalysisError("at most one properties input may be stdin")

    cost_info = cpddl_analyzer.load_cost_manifest(
        args.cost_manifest, True, manifests, args.smoke_manifest)
    if cost_info is None:
        raise AnalysisError("cross-planner analysis requires the cost manifest")

    symk_task_labels, task_sources_sha256, source_manifest_sha256 = (
        symk_runner.validate_manifest_and_paths())
    _, screen_task_sources_sha256, screen_source_manifest_sha256 = (
        symk_runner.validate_screen_manifest_and_paths())
    tasks = validate_task_contract(symk_task_labels, manifests)
    if source_manifest_sha256 != cost_info["file_sha256"]:
        raise AnalysisError(
            "live SymK and CPDDL cost-manifest file hashes differ")
    if (task_sources_sha256 != cost_info["task_sources_sha256"][
            cpddl_analyzer.FINALIST_V1]):
        raise AnalysisError(
            "live SymK and CPDDL finalist task-source attestations differ")

    artifact, artifact_sha256 = symk_runner.load_artifact(args.selection)
    symk_configs = symk_runner.validate_artifact(
        artifact,
        expected_task_sources_sha256=task_sources_sha256,
        expected_source_manifest_sha256=source_manifest_sha256,
        expected_screen_task_sources_sha256=screen_task_sources_sha256,
        expected_screen_source_manifest_sha256=screen_source_manifest_sha256)
    symk_records, symk_source = cap_analyzer.load_properties(
        args.symk_properties)
    symk_matrix, errors, warnings = symk_analyzer.validate_records(
        symk_records, tasks, symk_configs, artifact, artifact_sha256,
        task_sources_sha256, source_manifest_sha256,
        expected_run_count=artifact["validation"]["expected_run_count"])
    if errors or warnings:
        raise AnalysisError(
            "SymK finalist validation failed ({} errors, {} warnings): {}".format(
                len(errors), len(warnings),
                "; ".join(errors + warnings)))

    cpddl_records, cpddl_source = cpddl_analyzer.load_properties(
        args.cpddl_properties)
    cpddl_matrix = cpddl_analyzer.validate_records(
        cpddl_records, manifests, cost_info)
    validate_cross_provenance_and_costs(
        tasks, symk_matrix, symk_configs, artifact, cost_info,
        cpddl_matrix)
    symk_entries = frozen_symk_entries(artifact, symk_configs)
    view = build_view(tasks, symk_matrix, symk_configs, cpddl_matrix)
    sys.stdout.write(render_report(
        symk_source, cpddl_source, artifact_sha256, tasks, view,
        symk_configs, symk_entries, cost_info))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AnalysisError, cpddl_analyzer.AnalysisError,
            symk_analyzer.AnalysisError, symk_runner.ProtocolError,
            cap_analyzer.AnalysisError, RuntimeError) as err:
        print("analysis error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
