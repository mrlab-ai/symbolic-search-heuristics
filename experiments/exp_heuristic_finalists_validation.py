#!/usr/bin/env python3
"""Prospective held-out validation of preselected heuristic finalists.

No outcome-derived selection file is checked in before the pilots finish.  The
runner requires one explicitly, validates its source hashes, immutable rules,
full option matrices, selected configurations, and derived run count, then
runs only the deduplicated matrix recorded in that artifact.

Examples (none of these launch):
  python exp_heuristic_finalists_validation.py --help
  python exp_heuristic_finalists_validation.py --print-template
  python exp_heuristic_finalists_validation.py --self-test
  python exp_heuristic_finalists_validation.py --selection selection.json --check

Launch only a reviewed, frozen artifact after the c280 cache exists. Use the
same scheduler environment for both commands; never combine the steps:
  python exp_heuristic_finalists_validation.py --selection selection.json build
  python exp_heuristic_finalists_validation.py --selection selection.json start
"""

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from downward import suites

import analyze_heuristic_choices_pilot as analyzer
import exp_common as C
import suite_cost_manifest
import suite_wbh


FROZEN_REVISION = analyzer.FROZEN_REVISION
SELECTION_SEED = "symbolic-search-heuristics/heuristic-finalists-validation/v1"
MANIFEST = SCRIPT_DIR / "heuristic_finalists_validation_suite.txt"
MANIFEST_DIGEST = analyzer.VALIDATION_MANIFEST_DIGEST
PILOT_MANIFEST = SCRIPT_DIR / "ms_caps_pilot_suite.txt"
CAP_VALIDATION_MANIFEST = SCRIPT_DIR / "ms_caps_validation_suite.txt"
SMOKE_MANIFEST = SCRIPT_DIR / "smoke_suite.txt"
EXPECTED_TASKS = 92
EXPECTED_DOMAINS = 46
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ProtocolError(Exception):
    pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the frozen finalist matrix on the reserved 92 tasks.")
    parser.add_argument(
        "--selection", type=Path,
        help="Reviewed JSON artifact emitted by analyze_heuristic_choices_pilot.py.")
    parser.add_argument(
        "--check", action="store_true",
        help="Validate artifact, manifest, paths, and run count without building.")
    parser.add_argument(
        "--print-template", action="store_true",
        help="Print a non-runnable artifact template and exit.")
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run deterministic synthetic artifact-validation tests and exit.")
    parser.add_argument(
        "steps", nargs="*",
        help="Downward Lab steps; run build and start in separate invocations")
    return parser.parse_args(argv)


def rank_key(domain, problem):
    payload = "{}\0{}\0{}".format(SELECTION_SEED, domain, problem)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), problem


def read_colon_manifest(path):
    tasks = []
    for lineno, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise ProtocolError(
                "{}:{} must contain DOMAIN:PROBLEM".format(path, lineno))
        domain, problem = line.split(":", 1)
        if not domain or not problem:
            raise ProtocolError(
                "{}:{} has an empty domain/problem".format(path, lineno))
        tasks.append(line)
    if len(tasks) != len(set(tasks)):
        raise ProtocolError("{} contains duplicate tasks".format(path))
    return tasks


def read_smoke_manifest():
    tasks = []
    for lineno, raw_line in enumerate(
            SMOKE_MANIFEST.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 2:
            raise ProtocolError(
                "{}:{} must contain DOMAIN PROBLEM".format(
                    SMOKE_MANIFEST, lineno))
        tasks.append("{}:{}".format(*fields))
    return tasks


def normalized_digest(tasks):
    payload = "".join("{}\n".format(task) for task in tasks)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def supported_candidate_domains():
    eligible = suite_cost_manifest.domains_with_min_supported_tasks(2)
    domains = [
        domain for domain in suite_wbh.SUITE_OPTIMAL_STRIPS
        if domain in eligible]
    if len(domains) != EXPECTED_DOMAINS or set(domains) != eligible:
        raise ProtocolError(
            "frozen source manifest must define exactly {} suite domains "
            "with at least two supported tasks".format(EXPECTED_DOMAINS))
    return domains


def expected_selection_and_paths():
    excluded = (
        set(read_colon_manifest(PILOT_MANIFEST))
        | set(read_colon_manifest(CAP_VALIDATION_MANIFEST))
        | set(read_smoke_manifest()))
    selected = []
    selected_paths = []
    supported = suite_cost_manifest.supported_tasks()
    for domain in supported_candidate_domains():
        suite_tasks = suites.build_suite(str(C.BENCHMARKS), [domain])
        by_problem = {task.problem: task for task in suite_tasks}
        if len(by_problem) != len(suite_tasks):
            raise ProtocolError("duplicate problem name in {}".format(domain))
        fresh = sorted(
            (problem for problem in by_problem
             if (domain, problem) in supported
             and "{}:{}".format(domain, problem) not in excluded),
            key=lambda problem: rank_key(domain, problem))
        if len(fresh) < 2:
            raise ProtocolError(
                "{} has fewer than two unreserved tasks".format(domain))
        for problem in fresh[:2]:
            selected.append("{}:{}".format(domain, problem))
            selected_paths.append(by_problem[problem])
    return selected, selected_paths, excluded


def validate_manifest_and_paths():
    tasks = read_colon_manifest(MANIFEST)
    if normalized_digest(tasks) != MANIFEST_DIGEST:
        raise ProtocolError("reserved manifest digest changed")
    if len(tasks) != EXPECTED_TASKS:
        raise ProtocolError(
            "reserved manifest has {} tasks; expected {}".format(
                len(tasks), EXPECTED_TASKS))
    expected, task_paths, excluded = expected_selection_and_paths()
    if tasks != expected:
        raise ProtocolError(
            "reserved manifest differs from the name-only seeded selection")
    overlap = set(tasks) & excluded
    if overlap:
        raise ProtocolError(
            "reserved manifest overlaps prior pilot/validation/smoke tasks: {}".format(
                ", ".join(sorted(overlap))))
    counts = Counter(task.split(":", 1)[0] for task in tasks)
    if list(counts) != supported_candidate_domains():
        raise ProtocolError(
            "reserved domain order differs from the suite domains with at "
            "least two supported tasks")
    if set(counts.values()) != {2}:
        raise ProtocolError("reserved manifest must contain two tasks per domain")
    supported = suite_cost_manifest.supported_tasks()
    task_keys = {tuple(task.split(":", 1)) for task in tasks}
    if not task_keys <= supported:
        raise ProtocolError(
            "reserved manifest contains tasks outside the frozen supported "
            "positive-cost, axiom-free population")
    for task in task_paths:
        if (not Path(task.problem_file).is_file()
                or not Path(task.domain_file).is_file()):
            raise ProtocolError(
                "missing benchmark path for {}:{}".format(
                    task.domain, task.problem))
    source_attestation = suite_cost_manifest.validate_task_sources(
        ((task.domain, task.problem, Path(task.domain_file),
          Path(task.problem_file)) for task in task_paths),
        C.BENCHMARKS)
    source_manifest_sha256 = suite_cost_manifest.sha256_file(
        suite_cost_manifest.MANIFEST_PATH)
    return tasks, source_attestation, source_manifest_sha256


def validate_screen_manifest_and_paths():
    """Byte-attest the exact 50 tasks that produced the screen selection."""
    tasks = read_colon_manifest(PILOT_MANIFEST)
    if (len(tasks) != 50 or normalized_digest(tasks)
            != analyzer.MANIFEST_DIGEST):
        raise ProtocolError("screening manifest changed")
    task_sources_sha256, source_manifest_sha256 = (
        analyzer.screen_runner.validate_task_sources(tasks))
    return tasks, task_sources_sha256, source_manifest_sha256


def require_mapping(parent, field):
    value = parent.get(field) if isinstance(parent, dict) else None
    if not isinstance(value, dict):
        raise ProtocolError("artifact field {} must be an object".format(field))
    return value


def require_source_digest(value, label):
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        raise ProtocolError("{} must be a lowercase SHA-256".format(label))
    if value == "0" * 64:
        raise ProtocolError("{} must not be a placeholder".format(label))


def expect_fields(section, expected, section_name):
    for field, wanted in expected.items():
        actual = section.get(field)
        if actual != wanted:
            raise ProtocolError(
                "{}.{}={!r}; expected {!r}".format(
                    section_name, field, actual, wanted))


def selected_cap_number(label):
    match = re.fullmatch(r"ms_cap(2|4|8|16|32)", str(label))
    if not match:
        raise ProtocolError("cap_pilot.selected_label is not a cap candidate")
    return int(match.group(1))


def validate_artifact(
        artifact, expected_task_sources_sha256=None,
        expected_source_manifest_sha256=None,
        expected_screen_task_sources_sha256=None,
        expected_screen_source_manifest_sha256=None):
    if not isinstance(artifact, dict) or artifact.get("schema") != analyzer.SCHEMA:
        raise ProtocolError("selection artifact has the wrong schema")
    screen = require_mapping(artifact, "screen")
    cap = require_mapping(artifact, "cap_pilot")
    finalists = require_mapping(artifact, "family_finalists")
    validation = require_mapping(artifact, "validation")

    expect_fields(screen, {
        "planner_revision": FROZEN_REVISION,
        "manifest_sha256": analyzer.MANIFEST_DIGEST,
        "time_limit_seconds": int(analyzer.TIME_LIMIT),
        "memory_limit_mib": int(analyzer.MEMORY_LIMIT_MIB),
        "task_order_seed": analyzer.TASK_ORDER_SEED,
        "task_order_method": analyzer.TASK_ORDER_METHOD,
        "selection_rule": analyzer.SCREEN_RULE_ID,
        "option_matrix_sha256": analyzer.OPTION_MATRIX_DIGEST,
        "options": analyzer.option_records(),
    }, "screen")
    require_source_digest(
        screen.get("properties_canonical_sha256"),
        "screen.properties_canonical_sha256")
    require_source_digest(
        screen.get("task_sources_sha256"),
        "screen.task_sources_sha256")
    require_source_digest(
        screen.get("source_manifest_sha256"),
        "screen.source_manifest_sha256")
    if (expected_screen_task_sources_sha256 is not None
            and screen["task_sources_sha256"]
            != expected_screen_task_sources_sha256):
        raise ProtocolError(
            "artifact screen task-source attestation differs from checkout")
    if (expected_screen_source_manifest_sha256 is not None
            and screen["source_manifest_sha256"]
            != expected_screen_source_manifest_sha256):
        raise ProtocolError(
            "artifact screen cost-manifest hash differs from frozen file")

    expect_fields(cap, {
        "planner_revision": analyzer.CAP_PILOT_REVISION,
        "manifest_sha256": analyzer.cap_analyzer.MANIFEST_DIGEST,
        "time_limit_seconds": int(analyzer.cap_analyzer.TIME_LIMIT),
        "memory_limit_mib": int(analyzer.cap_analyzer.MEMORY_LIMIT_MIB),
        "selection_rule": analyzer.CAP_RULE_ID,
        "option_matrix_sha256": analyzer.CAP_OPTION_MATRIX_DIGEST,
        "options": analyzer.CAP_PILOT_OPTIONS,
    }, "cap_pilot")
    require_source_digest(
        cap.get("properties_canonical_sha256"),
        "cap_pilot.properties_canonical_sha256")
    selected_cap = selected_cap_number(cap.get("selected_label"))

    family_keys = set(finalists)
    expected_families = set(analyzer.FAMILIES)
    unknown_families = family_keys - expected_families
    if unknown_families:
        raise ProtocolError(
            "unknown finalist families: {}".format(
                ", ".join(sorted(unknown_families))))
    missing_families = expected_families - family_keys
    if missing_families:
        raise ProtocolError(
            "artifact omits emitted family finalists: {}".format(
                ", ".join(sorted(missing_families))))
    screen_searches = dict(analyzer.CONFIGS)
    normalized_finalists = {}
    for family in ("ms", "pdb", "potential"):
        item = finalists.get(family)
        if item is None:
            continue
        if not isinstance(item, dict) or set(item) != {"label", "search"}:
            raise ProtocolError("{} finalist must contain label and search".format(family))
        label = item["label"]
        if label in analyzer.CONTROLS:
            raise ProtocolError("controls cannot be family finalists")
        if label not in analyzer.FAMILIES[family]:
            raise ProtocolError(
                "{} is not a {} candidate".format(label, family))
        if item["search"] != screen_searches[label]:
            raise ProtocolError("{} finalist search does not match the screen".format(label))
        normalized_finalists[family] = dict(item)

    derived_configs = analyzer.validation_configs(
        selected_cap, normalized_finalists)
    require_source_digest(
        validation.get("task_sources_sha256"),
        "validation.task_sources_sha256")
    require_source_digest(
        validation.get("source_manifest_sha256"),
        "validation.source_manifest_sha256")
    if (expected_task_sources_sha256 is not None
            and validation["task_sources_sha256"]
            != expected_task_sources_sha256):
        raise ProtocolError("artifact task-source attestation differs from checkout")
    if (expected_source_manifest_sha256 is not None
            and validation["source_manifest_sha256"]
            != expected_source_manifest_sha256):
        raise ProtocolError("artifact cost-manifest hash differs from frozen file")
    expect_fields(validation, {
        "planner_revision": FROZEN_REVISION,
        "manifest_sha256": MANIFEST_DIGEST,
        "time_limit_seconds": int(analyzer.TIME_LIMIT),
        "memory_limit_mib": int(analyzer.MEMORY_LIMIT_MIB),
        "task_order_seed": analyzer.TASK_ORDER_SEED,
        "task_order_method": analyzer.TASK_ORDER_METHOD,
        "configs": derived_configs,
        "expected_run_count": EXPECTED_TASKS * len(derived_configs),
    }, "validation")
    if len({item["search"] for item in derived_configs}) != len(derived_configs):
        raise ProtocolError("validation configs are not deduplicated")
    if not 5 <= len(derived_configs) <= 6:
        raise ProtocolError("validation must have five or six unique configs")
    return derived_configs


def load_artifact(path):
    if path is None:
        raise ProtocolError("--selection is required")
    try:
        payload = path.read_bytes()
        artifact = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ProtocolError("cannot read selection artifact: {}".format(err))
    digest = hashlib.sha256(payload).hexdigest()
    return artifact, digest


def template_artifact():
    placeholder = "0" * 64
    return {
        "schema": analyzer.SCHEMA,
        "screen": {
            "planner_revision": FROZEN_REVISION,
            "manifest_sha256": analyzer.MANIFEST_DIGEST,
            "properties_canonical_sha256": placeholder,
            "source_manifest_sha256": placeholder,
            "task_sources_sha256": placeholder,
            "time_limit_seconds": int(analyzer.TIME_LIMIT),
            "memory_limit_mib": int(analyzer.MEMORY_LIMIT_MIB),
            "task_order_seed": analyzer.TASK_ORDER_SEED,
            "task_order_method": analyzer.TASK_ORDER_METHOD,
            "selection_rule": analyzer.SCREEN_RULE_ID,
            "option_matrix_sha256": analyzer.OPTION_MATRIX_DIGEST,
            "options": analyzer.option_records(),
        },
        "cap_pilot": {
            "planner_revision": analyzer.CAP_PILOT_REVISION,
            "manifest_sha256": analyzer.cap_analyzer.MANIFEST_DIGEST,
            "properties_canonical_sha256": placeholder,
            "time_limit_seconds": int(analyzer.cap_analyzer.TIME_LIMIT),
            "memory_limit_mib": int(analyzer.cap_analyzer.MEMORY_LIMIT_MIB),
            "selection_rule": analyzer.CAP_RULE_ID,
            "option_matrix_sha256": analyzer.CAP_OPTION_MATRIX_DIGEST,
            "options": analyzer.CAP_PILOT_OPTIONS,
            "selected_label": "REPLACE_FROM_CAP_PILOT",
        },
        "family_finalists": {},
        "validation": {
            "planner_revision": FROZEN_REVISION,
            "manifest_sha256": MANIFEST_DIGEST,
            "time_limit_seconds": int(analyzer.TIME_LIMIT),
            "memory_limit_mib": int(analyzer.MEMORY_LIMIT_MIB),
            "task_order_seed": analyzer.TASK_ORDER_SEED,
            "task_order_method": analyzer.TASK_ORDER_METHOD,
            "source_manifest_sha256": placeholder,
            "task_sources_sha256": placeholder,
            "configs": [],
            "expected_run_count": 0,
        },
    }


def self_test():
    try:
        validate_artifact(template_artifact())
    except ProtocolError:
        pass
    else:
        raise AssertionError("placeholder artifact was accepted")

    artifact = template_artifact()
    artifact["screen"]["properties_canonical_sha256"] = "1" * 64
    artifact["screen"]["source_manifest_sha256"] = "5" * 64
    artifact["screen"]["task_sources_sha256"] = "6" * 64
    artifact["cap_pilot"]["properties_canonical_sha256"] = "2" * 64
    artifact["validation"]["source_manifest_sha256"] = "3" * 64
    artifact["validation"]["task_sources_sha256"] = "4" * 64
    artifact["cap_pilot"]["selected_label"] = "ms_cap8"
    artifact["family_finalists"] = {
        "ms": {"label": "ms_cap8", "search": dict(analyzer.CONFIGS)["ms_cap8"]},
        "pdb": {"label": "pdb_goal_w4", "search": dict(analyzer.CONFIGS)["pdb_goal_w4"]},
        "potential": {"label": "pot_rect_m16_w16",
                      "search": dict(analyzer.CONFIGS)["pot_rect_m16_w16"]},
    }
    configs = analyzer.validation_configs(8, artifact["family_finalists"])
    artifact["validation"]["configs"] = configs
    artifact["validation"]["expected_run_count"] = EXPECTED_TASKS * len(configs)
    assert len(validate_artifact(
        artifact, expected_source_manifest_sha256="3" * 64,
        expected_task_sources_sha256="4" * 64,
        expected_screen_source_manifest_sha256="5" * 64,
        expected_screen_task_sources_sha256="6" * 64)) == 5

    artifact["screen"]["task_sources_sha256"] = "7" * 64
    try:
        validate_artifact(
            artifact, expected_screen_task_sources_sha256="6" * 64)
    except ProtocolError:
        pass
    else:
        raise AssertionError("screen source drift was accepted")
    artifact["screen"]["task_sources_sha256"] = "6" * 64

    artifact["screen"]["options"][0]["search"] = "tampered()"
    try:
        validate_artifact(artifact)
    except ProtocolError:
        pass
    else:
        raise AssertionError("tampered option matrix was accepted")
    print("synthetic finalist-runner tests: PASS (artifact pinning and deduplication)")


def main(argv=None):
    args = parse_args(argv)
    C.reject_unsafe_combined_steps(args.steps)
    C.require_frozen_revision_cache(FROZEN_REVISION, args.steps)
    if args.print_template:
        print(json.dumps(template_artifact(), indent=2, sort_keys=True))
        return 0
    if args.self_test:
        self_test()
        return 0
    if args.selection is None:
        raise ProtocolError("--selection is required; no validation may launch without it")

    tasks, task_sources_sha256, source_manifest_sha256 = (
        validate_manifest_and_paths())
    _, screen_task_sources_sha256, screen_source_manifest_sha256 = (
        validate_screen_manifest_and_paths())
    artifact, artifact_sha256 = load_artifact(args.selection)
    configs = validate_artifact(
        artifact,
        expected_task_sources_sha256=task_sources_sha256,
        expected_source_manifest_sha256=source_manifest_sha256,
        expected_screen_task_sources_sha256=screen_task_sources_sha256,
        expected_screen_source_manifest_sha256=screen_source_manifest_sha256)
    expected_runs = len(tasks) * len(configs)
    if expected_runs != artifact["validation"]["expected_run_count"]:
        raise ProtocolError("derived run count differs from frozen artifact")
    if args.check:
        if args.steps:
            raise ProtocolError("--check cannot be combined with Lab steps")
        print("prospective finalist validation: PASS")
        print("selection artifact SHA-256: {}".format(artifact_sha256))
        print("tasks: {}; unique configs: {}; runs: {}".format(
            len(tasks), len(configs), expected_runs))
        return 0
    if not args.steps:
        raise ProtocolError("provide Lab steps or use --check")

    C.REV = FROZEN_REVISION
    C.TIME_LIMIT = "300s"
    C.MEMORY_LIMIT = "8G"
    exp = C.new_experiment()
    C.set_protocol_run_properties(exp, {
        "protocol": "heuristic-finalists-validation-v1",
        "task_manifest_sha256": MANIFEST_DIGEST,
        "selection_artifact_sha256": artifact_sha256,
        "screen_properties_canonical_sha256":
            artifact["screen"]["properties_canonical_sha256"],
        "cap_properties_canonical_sha256":
            artifact["cap_pilot"]["properties_canonical_sha256"],
        "source_manifest_sha256": source_manifest_sha256,
        "task_sources_sha256": task_sources_sha256,
        "declared_run_count": expected_runs,
    })
    C.add_suite(exp, tasks)
    for config in configs:
        C.add_algorithm(exp, config["label"], config["search"])
    attributes = C.ATTRIBUTES + [
        "protocol", "task_manifest_sha256", "selection_artifact_sha256",
        "screen_properties_canonical_sha256",
        "cap_properties_canonical_sha256", "source_manifest_sha256",
        "task_sources_sha256", "declared_run_count",
    ]
    C.add_standard_steps(exp, attributes)
    sys.argv = [sys.argv[0]] + args.steps
    exp.run_steps()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ProtocolError, RuntimeError) as err:
        print("protocol error: {}".format(err), file=sys.stderr)
        sys.exit(2)
