#!/usr/bin/env python3
"""Reuse the certified predictor statistics with fresh within-family evidence."""

import argparse
from collections import Counter
import contextlib
import json
from pathlib import Path
from types import SimpleNamespace

import analyze_pdb_terminal_incidence_confirmation_a as Existing
import analyze_pdb_terminal_incidence_shadow as Original
import exp_pdb_within_family_a_v1 as Runner
import pdb_terminal_incidence_confirmation_a_protocol as Template
import pdb_within_family_cohort as C


SCHEMA = "pdb-terminal-incidence-within-family-a-analysis/v1"
OUTPUT = C.ARTIFACTS / "confirmation-a"


@contextlib.contextmanager
def configured(freeze):
    settings = freeze["analysis"]
    protocol = SimpleNamespace(**{key: value for key, value in vars(Template).items() if key.isupper()})
    protocol.DIRECTORIES = tuple(freeze["families"])
    protocol.DIRECTORY_TO_FAMILY = {family: family for family in freeze["families"]}
    protocol.MIN_ELIGIBLE_FAMILIES = settings["minimum_families"]
    protocol.MIN_COMPARISON_FAMILIES = settings["minimum_families"]
    protocol.MIN_ELIGIBLE_TASKS = settings["minimum_eligible_tasks"]
    protocol.MIN_COMPARISON_TASKS = settings["minimum_comparison_tasks"]
    protocol.MIN_TARGET_STRICT_PAIRS = settings["minimum_target_strict_pairs"]
    protocol.MIN_SHARED_STRICT_PAIRS = settings["minimum_target_strict_pairs"]
    protocol.MIN_PRIMARY_CONCORDANCE_NUMERATOR, protocol.MIN_PRIMARY_CONCORDANCE_DENOMINATOR = settings["minimum_concordance"]
    protocol.MIN_ADVANTAGE_NUMERATOR, protocol.MIN_ADVANTAGE_DENOMINATOR = settings["minimum_advantage"]
    protocol.BOOTSTRAP_REPLICATES = settings["bootstrap_replicates"]
    protocol.BOOTSTRAP_SEED = settings["bootstrap_seed"]
    protocol.HORIZON = settings["horizon"]
    names = ("P", "SCHEMA", "PREDICTORS", "PRIMARY_PREDICTOR", "CONTROLS",
             "REQUESTED_MODES", "LABEL_MODES", "GOAL_FILL_LABEL")
    previous = {key: getattr(Original, key) for key in names}
    previous_protocol = Existing.P
    try:
        Existing.P = protocol
        Existing._configure_original()
        Original.SCHEMA = SCHEMA
        yield protocol
    finally:
        Existing.P = previous_protocol
        for key, value in previous.items():
            setattr(Original, key, value)


def validate_matrix(records, freeze, freeze_sha):
    sources = {(row["domain"], row["problem"]): row for row in freeze["tasks"]["a"]}
    searches = dict(Runner.CONFIGS)
    expected = {(label, task) for label in searches for task in sources}
    matrix = {}
    outcomes = {}
    for record in records:
        task = (record.get("domain"), record.get("problem"))
        label = record.get("algorithm")
        key = (label, task)
        if key not in expected or key in matrix or record.get("id") != [label, *task]:
            raise ValueError("fresh prediction matrix has an unknown or duplicate cell")
        source = sources[task]
        fixed = {
            "within_family_freeze_sha256": freeze_sha,
            "component_options": ["--search", searches[label]],
            "driver_options": Runner.DRIVER_OPTIONS, "build_options": ["release_no_lp"],
            "planner_revision": freeze["planner_revision"],
            "local_revision": freeze["planner_revision"], "global_revision": freeze["planner_revision"],
            "domain_source_sha256": source["domain_sha256"],
            "problem_source_sha256": source["problem_sha256"],
            "source_sas_sha256": source["sas_sha256"], "source_result_sha256": source["source_result_sha256"],
            "domain_source_path": source["domain_file"], "problem_source_path": source["problem_file"],
            "family": source["family"], "planner_time_limit": 1800,
            "planner_memory_limit": 24576, "analysis_horizon": 16,
        }
        for field, value in fixed.items():
            if record.get(field) != value:
                raise ValueError(f"prediction cell changed {field}: {record['id']}")
        Runner.parse_execution(C.G.canonical(record["execution_evidence"]).decode("ascii"), dict(record))
        if Original._recognized_outcome_invalidation(record):
            outcome = "invalid_outcome"
            Original._validate_parser_contract(record, Original.OUTCOME_SPECS[record["planner_exit_code"]][3])
        else:
            outcome = Original._terminal_class(record)
            Original._validate_parser_contract(record, outcome)
        matrix[key] = record
        outcomes[key] = outcome
    if set(matrix) != expected:
        raise ValueError("fresh prediction matrix is incomplete")
    return matrix, sorted(sources), outcomes


def verify_run_evidence(records, freeze, experiment):
    expected_planner = Runner.planner_files(Runner.Source.CACHE)
    sources = {(row["domain"], row["problem"]): row for row in freeze["tasks"]["a"]}
    for record in records:
        directory = experiment / record["run_dir"]
        if not directory.resolve().is_relative_to(experiment.resolve()):
            raise ValueError("prediction run escaped its experiment")
        guard = json.loads((directory / "execution-evidence.json").read_bytes())
        if guard != record["execution_evidence"]:
            raise ValueError("parsed execution record differs from raw evidence")
        config_path = directory / "execution-config.json"
        if C.W.file_sha(config_path) != record["execution_config_sha256"]:
            raise ValueError("execution configuration changed")
        config = json.loads(config_path.read_bytes())
        if (config["id"] != record["id"] or config["search"] != dict(Runner.CONFIGS)[record["algorithm"]]
                or config["driver_options"] != Runner.DRIVER_OPTIONS
                or config["freeze_sha256"] != record["within_family_freeze_sha256"]
                or config["source_sas_sha256"] != record["source_sas_sha256"]
                or config["source_result_sha256"] != record["source_result_sha256"]
                or config["planner_files_sha256"] != expected_planner):
            raise ValueError("executed options or planner bytes differ from the frozen matrix")
        for kind in ("domain", "problem"):
            if C.W.file_sha(directory / (kind + ".pddl")) != record[kind + "_source_sha256"]:
                raise ValueError("copied scientific input changed")
        for name, expected in guard["files_sha256"].items():
            if C.W.file_sha(directory / name) != expected:
                raise ValueError("raw scientific output changed")
        # Successful search must use the same serialized task screened at source.
        source = sources[(record["domain"], record["problem"])]
        outcome = Original.OUTCOME_SPECS.get(record.get("planner_exit_code"))
        if outcome is not None and outcome[3] != "presearch":
            translation = guard.get("translation_evidence")
            if translation != {"sas_sha256": source["sas_sha256"],
                                "source_result_sha256": source["source_result_sha256"],
                                "verified_before_preprocessing": True}:
                raise ValueError("scientific run translated to a different SAS task")


def analyze_records(records, freeze, freeze_sha):
    with configured(freeze):
        matrix, tasks, outcomes = validate_matrix(records, freeze, freeze_sha)
        primary = Original.primary_observations(matrix, tasks)
        Existing._add_meet_certificate(primary)
        Existing._add_masked_add_size(primary)
        Existing._add_active_value_count(primary)
        with Existing._ordering_predictors(True):
            comparison = Original.target_strict_tie_aware_comparison(primary["grouped"])
            strict = Original.grand_shared_comparison(primary["grouped"])
            eligible_tasks = len(primary["frontiers"])
            eligible_families = len({task[0] for task in primary["frontiers"]})
            gate = Original.primary_gates(comparison, eligible_tasks, eligible_families)
            regret = Existing._top_choice_regret(primary["grouped"])
            with Existing._ordering_predictors(False):
                diagnostics = Original.secondary_diagnostics(primary["observations"])
        return {
            "schema": SCHEMA, "scope": freeze["scope"], "freeze_sha256": freeze_sha,
            "matrix": {"tasks": len(tasks), "configs": len(Runner.CONFIGS), "cells": len(records),
                       "families": len(freeze["families"]), "outcome_classes": dict(Counter(outcomes.values()))},
            "primary": {key: primary[key] for key in (
                "frontier_statuses", "cell_statuses", "construction_by_label", "cegar_fallback_tasks")},
            "eligible_tasks": eligible_tasks, "eligible_families": eligible_families,
            "semantic_observations": len(primary["observations"]),
            "duplicate_config_observations": sum(len(item["configs"]) for item in primary["observations"])
                                             - len(primary["observations"]),
            "observations": primary["observations"],
            "comparison": Existing._public_comparison(comparison),
            "gates": {"decision": "PASS" if gate["pass"] else "FAIL", "pass": gate["pass"],
                      "primary": gate, "unseen_family_gate": False},
            "sensitivity": {"gating": False, "all_predictor_strict": Existing._public_comparison(strict),
                            "top_choice_regret": regret},
            "secondary_diagnostics": diagnostics,
            "statistical_selector_gate_passed": gate["pass"],
            "scheduler_audit_required_before_selector_launch": True,
        }


def run_twice(properties, output=OUTPUT):
    freeze = C.load_freeze()
    freeze_sha = C.W.file_sha(C.FREEZE)
    output.mkdir(parents=True, exist_ok=True)
    destinations = [output / name for name in ("analysis.json", "analysis-repeat.json", "analysis-receipt.json")]
    if any(path.exists() for path in destinations):
        raise ValueError("refusing to overwrite an existing analysis")
    initial = C.W.file_sha(properties)
    versions = []
    for _ in range(2):
        if C.W.file_sha(properties) != initial:
            raise ValueError("analysis properties changed between executions")
        records = list(json.loads(properties.read_bytes()).values())
        verify_run_evidence(records, freeze, Runner.OUTPUT)
        result = analyze_records(records, freeze, freeze_sha)
        result["input"] = {"properties_path": str(properties), "properties_sha256": initial,
                           "code_commit": freeze["code_commit"], "code_sha256": freeze["code_sha256"]}
        versions.append(C.G.canonical(result))
    if versions[0] != versions[1]:
        raise ValueError("independent fresh parses produced different analysis bytes")
    for path, raw in zip(destinations[:2], versions):
        with path.open("xb") as stream:
            stream.write(raw)
    receipt = {"schema": SCHEMA + "/double-execution", "byte_identical": True,
               "analysis_sha256": C.G.sha(versions[0]), "repeat_sha256": C.G.sha(versions[1]),
               "properties_sha256": initial, "freeze_sha256": freeze_sha,
               "scheduler_audit_required_before_selector_launch": True}
    C.Monitor.publish(destinations[2], receipt)
    print(json.dumps({"decision": result["gates"]["decision"], "matrix": result["matrix"],
                      "support": result["gates"]["primary"]["support"], "receipt": receipt}, sort_keys=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--properties", type=Path, default=Path(str(Runner.OUTPUT) + "-eval/properties"))
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    run_twice(args.properties.resolve(), args.output.resolve())


if __name__ == "__main__":
    main()
