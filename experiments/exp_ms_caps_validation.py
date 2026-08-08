#!/usr/bin/env python3
"""Held-out, name-selected validation of M&S terminal caps.

This experiment was frozen before inspecting ``exp_ms_caps_pilot`` outcomes.
It retains the name-hash-selected pair in each of the 46 suite domains with at
least two eligible tasks after task-level filtering by the frozen, pre-outcome
source manifest. Eligible tasks are positive-cost and free of normalized
axioms. Prior-pilot and
development/acceptance smoke task names are excluded. The checked-in 92-task
manifest is validated by recomputing that selection and checking its normalized
SHA-256 digest. No planner performance enters domain eligibility or selection.

Seven configurations at 300 seconds and 8 GiB give 644 runs:

  blind_fw  sym_fw()
  ms_exact  sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false)
  ms_cap2   sym_fw_ms(max_states=10000,value_cap=2,align_merge_order=false)
  ms_cap4   sym_fw_ms(max_states=10000,value_cap=4,align_merge_order=false)
  ms_cap8   sym_fw_ms(max_states=10000,value_cap=8,align_merge_order=false)
  ms_cap16  sym_fw_ms(max_states=10000,value_cap=16,align_merge_order=false)
  ms_cap32  sym_fw_ms(max_states=10000,value_cap=32,align_merge_order=false)

Inspect only (does not build or launch):
  experiments/.venv/bin/python experiments/exp_ms_caps_validation.py --help

Run only after explicit sign-off and after the c280 revision cache exists.
Use the same scheduler environment for both commands; never combine the steps:
  experiments/.venv/bin/python experiments/exp_ms_caps_validation.py build
  experiments/.venv/bin/python experiments/exp_ms_caps_validation.py start
  experiments/.venv/bin/python experiments/exp_ms_caps_validation.py parse fetch report
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from downward import suites

import exp_common as C
import suite_cost_manifest
import suite_wbh
from exp_ms_caps_pilot import read_manifest as read_pilot_manifest


FROZEN_REVISION = "c2800d7e65abb61d4b94b08a5487f701ceb41d6b"
SELECTION_SEED = "symbolic-search-heuristics/ms-caps-validation/v2"
MANIFEST = Path(__file__).with_name("ms_caps_validation_suite.txt")
SMOKE_MANIFEST = Path(__file__).with_name("smoke_suite.txt")
MANIFEST_DIGEST = "daca0c3ba0f029d7dc61b342c5ba99cd53c00b1cbfdbe7744d3fca0aa4431161"
EXPECTED_TASKS = 92
EXPECTED_DOMAINS = 46
EXPECTED_RUNS = 644
CAPS = [2, 4, 8, 16, 32]
CONFIGS = [
    ("blind_fw", "sym_fw()"),
    ("ms_exact",
     "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false)"),
] + [
    ("ms_cap{}".format(cap),
     "sym_fw_ms(max_states=10000,value_cap={},align_merge_order=false)".format(cap))
    for cap in CAPS
]
OPTION_MATRIX_DIGEST = "03247deb9c01ba74bcfd858c57d459bd43b1a64ad3c307a40d307f923814a7de"
CAP_SELECTION_RULE = "max-solved-min-micro-par2-smaller-k/v1"


def rank_key(domain, problem):
    payload = "{}\0{}\0{}".format(SELECTION_SEED, domain, problem)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), problem


def read_manifest():
    tasks = []
    for raw_line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            tasks.append(line)
    return tasks


def read_smoke_manifest():
    tasks = set()
    for lineno, raw_line in enumerate(
            SMOKE_MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 2:
            raise RuntimeError(
                "{}:{} must contain DOMAIN PROBLEM".format(
                    SMOKE_MANIFEST, lineno))
        tasks.add("{}:{}".format(*fields))
    return tasks


def supported_candidate_domains():
    eligible = suite_cost_manifest.domains_with_min_supported_tasks(2)
    domains = [
        domain for domain in suite_wbh.SUITE_OPTIMAL_STRIPS
        if domain in eligible]
    if len(domains) != EXPECTED_DOMAINS or set(domains) != eligible:
        raise RuntimeError(
            "frozen source manifest must define exactly {} suite domains "
            "with at least two supported tasks".format(EXPECTED_DOMAINS))
    return domains


def expected_selection_and_paths():
    pilot_tasks = set(read_pilot_manifest())
    excluded = pilot_tasks | read_smoke_manifest()
    supported = suite_cost_manifest.supported_tasks()
    selected = []
    selected_paths = []
    for domain in supported_candidate_domains():
        suite_tasks = suites.build_suite(str(C.BENCHMARKS), [domain])
        by_problem = {task.problem: task for task in suite_tasks}
        if len(by_problem) != len(suite_tasks):
            raise RuntimeError("duplicate problem name in domain {}".format(domain))

        fresh = sorted(
            (problem for problem in by_problem
             if (domain, problem) in supported
             and "{}:{}".format(domain, problem) not in excluded),
            key=lambda problem: rank_key(domain, problem),
        )
        chosen = fresh[:2]
        if len(chosen) != 2:
            raise RuntimeError(
                "domain {} has fewer than two tasks outside the pilot".format(
                    domain))
        for problem in chosen:
            selected.append("{}:{}".format(domain, problem))
            selected_paths.append(by_problem[problem])
    return selected, selected_paths


def validate_manifest(validate_sources=True):
    tasks = read_manifest()
    payload = "".join("{}\n".format(task) for task in tasks)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    if digest != MANIFEST_DIGEST:
        raise RuntimeError(
            "validation manifest digest changed: {} != {}".format(
                digest, MANIFEST_DIGEST))
    expected, task_paths = expected_selection_and_paths()
    if tasks != expected:
        for index, (actual, wanted) in enumerate(zip(tasks, expected), 1):
            if actual != wanted:
                raise RuntimeError(
                    "validation manifest differs at entry {}: {} != {}".format(
                        index, actual, wanted))
        raise RuntimeError(
            "validation manifest has {} entries; expected {}".format(
                len(tasks), len(expected)))

    domain_counts = Counter(task.split(":", 1)[0] for task in tasks)
    supported_domains = supported_candidate_domains()
    if list(domain_counts) != supported_domains:
        raise RuntimeError(
            "validation manifest domain order differs from the frozen "
            "suite domains with at least two supported tasks")
    if set(domain_counts.values()) != {2}:
        raise RuntimeError("validation manifest must have exactly two tasks per domain")
    if len(tasks) != EXPECTED_TASKS:
        raise RuntimeError(
            "validation manifest must contain exactly {} tasks".format(
                EXPECTED_TASKS))
    supported_tasks = suite_cost_manifest.supported_tasks()
    task_keys = {tuple(task.split(":", 1)) for task in tasks}
    if not task_keys <= supported_tasks:
        raise RuntimeError(
            "validation manifest contains tasks outside the frozen supported "
            "positive-cost, axiom-free population")
    excluded = set(read_pilot_manifest()) | read_smoke_manifest()
    overlap = set(tasks) & excluded
    if overlap:
        raise RuntimeError(
            "held-out manifest overlaps pilot/smoke tasks: {}".format(
                ", ".join(sorted(overlap))))

    for task in task_paths:
        problem_path = Path(task.problem_file)
        domain_path = Path(task.domain_file)
        if not problem_path.is_file() or not domain_path.is_file():
            raise RuntimeError(
                "missing benchmark path for {}:{} (problem={}, domain={})".format(
                    task.domain, task.problem, problem_path, domain_path))
    source_attestation = None
    source_manifest_sha256 = None
    if validate_sources:
        source_attestation = suite_cost_manifest.validate_task_sources(
            ((task.domain, task.problem, Path(task.domain_file),
              Path(task.problem_file)) for task in task_paths),
            C.BENCHMARKS)
        source_manifest_sha256 = suite_cost_manifest.sha256_file(
            suite_cost_manifest.MANIFEST_PATH)
    return tasks, source_attestation, source_manifest_sha256


def main():
    C.reject_unsafe_combined_steps()
    C.require_frozen_revision_cache(FROZEN_REVISION)
    # Lab's help parser exits before any step runs.  Keep that documented,
    # read-only path usable while still requiring live byte attestation for
    # every build/start/parse/fetch/report invocation.
    help_only = any(arg in {"-h", "--help"} for arg in sys.argv[1:])
    tasks, task_sources_sha256, source_manifest_sha256 = validate_manifest(
        validate_sources=not help_only)
    option_payload = [
        {"label": label, "search": search} for label, search in CONFIGS]
    option_digest = hashlib.sha256(json.dumps(
        option_payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("utf-8")).hexdigest()
    if option_digest != OPTION_MATRIX_DIGEST:
        raise RuntimeError("frozen cap-v2 option matrix changed")
    if len(tasks) * len(CONFIGS) != EXPECTED_RUNS:
        raise RuntimeError(
            "validation matrix must contain exactly {} runs".format(
                EXPECTED_RUNS))

    C.REV = FROZEN_REVISION
    C.TIME_LIMIT = "300s"
    C.MEMORY_LIMIT = "8G"

    exp = C.new_experiment()
    C.set_protocol_run_properties(exp, {
        "protocol": "ms-caps-validation-v2",
        "task_manifest_sha256": MANIFEST_DIGEST,
        "declared_run_count": EXPECTED_RUNS,
        "option_matrix_sha256": OPTION_MATRIX_DIGEST,
        "cap_selection_rule": CAP_SELECTION_RULE,
        "source_manifest_sha256": source_manifest_sha256,
        "task_sources_sha256": task_sources_sha256,
    })
    C.add_suite(exp, tasks)
    for label, search in CONFIGS:
        C.add_algorithm(exp, label, search)
    C.add_standard_steps(exp, C.ATTRIBUTES + [
        "protocol", "task_manifest_sha256", "declared_run_count",
        "option_matrix_sha256", "cap_selection_rule",
        "source_manifest_sha256", "task_sources_sha256",
    ])
    exp.run_steps()


if __name__ == "__main__":
    main()
