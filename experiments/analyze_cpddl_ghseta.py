#!/usr/bin/env python3
"""Validate and analyze the frozen CPDDL GHSETA experiment.

This program is deliberately read-only.  It accepts a Downward Lab
``properties`` file, evaluation directory, or evaluation tarball and writes a
deterministic text report to stdout.  It never builds, starts, or modifies an
experiment.

The analysis contract was frozen before any ``exp_cpddl_ghseta.py`` outcome
was run.  It requires the complete 234-task by six-configuration matrix,
validates every static provenance/resource/command/limit field, and rejects
contradictory solved costs.  Pilot50, cap-v2, and finalist-v1 records are
analyzed in separate sections and are never pooled.

Primary estimands are paired task-level coverage differences and equally
weighted domain-macro coverage differences on the source-attested supported
positive-cost, axiom-free subset.  The full frozen task set is secondary
context when it differs. Runtime and PAR2 are one-run
screening summaries only.  Configuration order is fixed; the analyzer never
ranks configurations or selects/tunes one from cap-v2 or finalist-v1 outcomes.

Examples:

  experiments/.venv/bin/python experiments/analyze_cpddl_ghseta.py \
      experiments/data/exp_cpddl_ghseta-eval/properties \
      --require-cost-manifest
  experiments/.venv/bin/python experiments/analyze_cpddl_ghseta.py --self-test
"""

import argparse
import copy
import hashlib
import json
import math
import statistics
import sys
import tarfile
from collections import Counter, defaultdict
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
RUNNER_PATH = SCRIPT_DIR / "exp_cpddl_ghseta.py"
COMMON_PATH = SCRIPT_DIR / "exp_common.py"
DEFAULT_PROPERTIES = SCRIPT_DIR / "data" / "exp_cpddl_ghseta-eval" / "properties"
DEFAULT_ARCHIVE = SCRIPT_DIR / "data" / "exp_cpddl_ghseta-eval.tar.gz"
DEFAULT_PILOT_MANIFEST = SCRIPT_DIR / "ms_caps_pilot_suite.txt"
DEFAULT_CAP_V2_MANIFEST = SCRIPT_DIR / "ms_caps_validation_suite.txt"
DEFAULT_FINALIST_V1_MANIFEST = (
    SCRIPT_DIR / "heuristic_finalists_validation_suite.txt")
DEFAULT_SMOKE_MANIFEST = SCRIPT_DIR / "smoke_suite.txt"
DEFAULT_COST_MANIFEST = SCRIPT_DIR / "suite_wbh_operator_costs.json"

# This is the exact pre-launch runner reviewed with this analysis contract.
EXPECTED_RUNNER_SHA256 = (
    "fd7f0afc88bf73a3819ee15efabea9fefea8ef85d906413cb8389579e673e8a2")
EXPECTED_COMMON_SHA256 = (
    "3c8d7004fb5cda229fc78e003ae296ca28f5c0f13f0900633a5cf8902b2298a2")

TIME_LIMIT = 300
MEMORY_LIMIT_MIB = 8192
REPETITIONS = 1
BOOTSTRAP_SEED = (
    "symbolic-search-heuristics/cpddl-ghseta/domain-cluster-bootstrap/v1")
BOOTSTRAP_REPLICATES = 10000
BOOTSTRAP_CONFIDENCE = 0.95

PILOT = "pilot50"
CAP_V2 = "cap-v2"
FINALIST_V1 = "finalist-v1"
MANIFEST_ORDER = (PILOT, CAP_V2, FINALIST_V1)
EXPECTED_TASKS = 234
EXPECTED_CELLS = 1404
CAP_V2_SELECTION_SEED = (
    "symbolic-search-heuristics/ms-caps-validation/v2")
FINALIST_V1_SELECTION_SEED = (
    "symbolic-search-heuristics/heuristic-finalists-validation/v1")
MANIFEST_SPECS = (
    {
        "label": PILOT,
        "count": 50,
        "domains": 25,
        "digest": (
            "c63a59ee2096b40c24f80db895ee2c0d22aabc2630c823b882e7f50f529a481b"),
        "default_path": DEFAULT_PILOT_MANIFEST,
    },
    {
        "label": CAP_V2,
        "count": 92,
        "domains": 46,
        "digest": (
            "daca0c3ba0f029d7dc61b342c5ba99cd53c00b1cbfdbe7744d3fca0aa4431161"),
        "default_path": DEFAULT_CAP_V2_MANIFEST,
    },
    {
        "label": FINALIST_V1,
        "count": 92,
        "domains": 46,
        "digest": (
            "fc63d4eed62816a2e065cb89f89483999a7b51067b7077969d10b2a338f19760"),
        "default_path": DEFAULT_FINALIST_V1_MANIFEST,
    },
)

CPDDL_VENDORED_UPSTREAM_COMMIT = (
    "2c7de0ec0e7d1d002a08aead4c5c5bbdcf171b89")
CPDDL_TREE_ANCHOR_REVISION = (
    "c2800d7e65abb61d4b94b08a5487f701ceb41d6b")
CPDDL_TREE_OID = "c61b00eecb7c4223f4b5f358f900c5fc4a1c6dec"
CPDDL_TREE_MANIFEST_SHA256 = (
    "3673059666688e581d3593ec87088c640032d42481be3e6f3e754a1e08bb2be2")
CPDDL_BUILD_CONFIG_SHA256 = (
    "908c2dadd8fed416ee42b12c2dd9d815a93732802e099735c6221de215f78908")
CPDDL_GENERATED_CONFIG_SHA256 = (
    "88abd4f6bea7a27b75e3c536b82b56dbd3db67a3c17875dc346488613358b997")
CPDDL_BINARY_SHA256 = (
    "df2dba3e604c10caf17e2ec6b86b7007bbdabc49fc77bbb34745d1ee3f0cd056")
CPDDL_BINARY_VERSION = "1.5-409658ea3bdf92b21170d66a12fc489311e755e6"

CONFIGS = (
    {
        "label": "cpddl_blind_fw",
        "direction": "forward",
        "fw_objective": "none",
        "bw_objective": "none",
        "readme_recommended": False,
        "options": ("--fdr-tnfm", "--symba", "fw"),
    },
    {
        "label": "cpddl_blind_bi",
        "direction": "bidirectional",
        "fw_objective": "none",
        "bw_objective": "none",
        "readme_recommended": False,
        "options": ("--fdr-tnfm", "--symba", "bi"),
    },
    {
        "label": "cpddl_ghseta_fw_i",
        "direction": "forward",
        "fw_objective": "I",
        "bw_objective": "none",
        "readme_recommended": False,
        "options": (
            "--fdr-tnfm", "--symba", "fw", "--symba-fw-pot",
            "--symba-fw-pot-cfg", "I",
        ),
    },
    {
        "label": "cpddl_ghseta_fw_a_plus_i",
        "direction": "forward",
        "fw_objective": "A+I",
        "bw_objective": "none",
        "readme_recommended": False,
        "options": (
            "--fdr-tnfm", "--symba", "fw", "--symba-fw-pot",
            "--symba-fw-pot-cfg", "A+I",
        ),
    },
    {
        "label": "cpddl_ghseta_bi_a_plus_i_blind",
        "direction": "bidirectional",
        "fw_objective": "A+I",
        "bw_objective": "none",
        "readme_recommended": True,
        "options": (
            "--fdr-tnfm", "--symba", "bi", "--symba-fw-pot",
            "--symba-fw-pot-cfg", "A+I",
        ),
    },
    {
        "label": "cpddl_ghseta_bi_a_plus_i_i",
        "direction": "bidirectional",
        "fw_objective": "A+I",
        "bw_objective": "I",
        "readme_recommended": False,
        "options": (
            "--fdr-tnfm", "--symba", "bi", "--symba-fw-pot",
            "--symba-fw-pot-cfg", "A+I", "--symba-bw-pot",
            "--symba-bw-pot-cfg", "I",
        ),
    },
)
ALGORITHMS = tuple(config["label"] for config in CONFIGS)
CONFIG_BY_LABEL = {config["label"]: config for config in CONFIGS}

# These controlled contrasts are fixed before outcomes.  Their order is part
# of the report contract and is not changed according to observed performance.
PRIMARY_PAIRS = (
    ("cpddl_ghseta_fw_i", "cpddl_blind_fw"),
    ("cpddl_ghseta_fw_a_plus_i", "cpddl_blind_fw"),
    ("cpddl_ghseta_fw_a_plus_i", "cpddl_ghseta_fw_i"),
    ("cpddl_ghseta_bi_a_plus_i_blind", "cpddl_blind_bi"),
    ("cpddl_ghseta_bi_a_plus_i_i", "cpddl_blind_bi"),
    ("cpddl_ghseta_bi_a_plus_i_i", "cpddl_ghseta_bi_a_plus_i_blind"),
)

OUTCOMES = (
    "solved", "proved_unsolvable", "search_failed",
    "censored_or_error", "invalid_solved_evidence",
)
DONE_STATUSES = {"PLAN FOUND", "PLAN NOT EXIST", "FAIL", "CONT"}


class AnalysisError(Exception):
    pass


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Validate and analyze the frozen CPDDL GHSETA matrix.")
    parser.add_argument(
        "properties", nargs="?",
        help=("Lab properties JSON, evaluation directory, tar archive, or '-' "
              "for JSON on stdin; defaults to the expected evaluation output."))
    parser.add_argument(
        "--pilot-manifest", type=Path, default=DEFAULT_PILOT_MANIFEST,
        help="Frozen 50-task pilot manifest (default: %(default)s).")
    parser.add_argument(
        "--cap-v2-manifest", "--heldout-manifest", dest="cap_v2_manifest",
        type=Path, default=DEFAULT_CAP_V2_MANIFEST,
        help="Frozen 92-task cap-v2 manifest (default: %(default)s).")
    parser.add_argument(
        "--finalist-v1-manifest", type=Path,
        default=DEFAULT_FINALIST_V1_MANIFEST,
        help="Frozen 92-task finalist-v1 manifest (default: %(default)s).")
    parser.add_argument(
        "--smoke-manifest", type=Path, default=DEFAULT_SMOKE_MANIFEST,
        help=("Frozen smoke exclusions used to verify the seeded name-only "
              "selections when the cost manifest is available (default: "
              "%(default)s)."))
    parser.add_argument(
        "--cost-manifest", type=Path, default=DEFAULT_COST_MANIFEST,
        help=("Checksum-validated suite cost manifest. If the default is not "
              "yet available, full-set analysis remains available and the "
              "supported-population sections are explicitly suppressed."))
    parser.add_argument(
        "--require-cost-manifest", action="store_true",
        help=("Fail instead of suppressing supported positive-cost, "
              "axiom-free sections if absent."))
    parser.add_argument(
        "--self-test", action="store_true",
        help="Run in-memory synthetic acceptance and rejection tests only.")
    args = parser.parse_args(argv)
    if args.self_test and args.properties is not None:
        parser.error("--self-test does not accept a properties input")
    return args


def sha256_file(path):
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as err:
        raise AnalysisError("cannot hash {}: {}".format(path, err)) from err
    return digest.hexdigest()


def validate_runner_source():
    actual = sha256_file(RUNNER_PATH)
    if actual != EXPECTED_RUNNER_SHA256:
        raise AnalysisError(
            "runner source changed: {} != {}; freeze a new analysis contract "
            "before launching".format(actual, EXPECTED_RUNNER_SHA256))
    common_actual = sha256_file(COMMON_PATH)
    if common_actual != EXPECTED_COMMON_SHA256:
        raise AnalysisError(
            "shared experiment helper changed: {} != {}; freeze a new "
            "analysis contract before launching".format(
                common_actual, EXPECTED_COMMON_SHA256))
    return actual


def _load_json_stream(stream, source):
    try:
        data = json.load(stream)
    except (json.JSONDecodeError, UnicodeDecodeError) as err:
        raise AnalysisError("invalid JSON in {}: {}".format(source, err)) from err
    return _normalize_properties(data, source)


def _normalize_properties(data, source):
    if isinstance(data, dict):
        items = data.items()
    elif isinstance(data, list):
        items = ((str(index), record) for index, record in enumerate(data))
    else:
        raise AnalysisError(
            "{} has a {} top level; expected object or list".format(
                source, type(data).__name__))
    records = []
    for source_key, value in items:
        if not isinstance(value, dict):
            raise AnalysisError(
                "property entry {!r} in {} is not an object".format(
                    source_key, source))
        record = dict(value)
        record["_source_key"] = str(source_key)
        records.append(record)
    return records


def _properties_in_directory(path):
    candidates = [path / "properties", path / "properties.json"]
    matches = [candidate for candidate in candidates if candidate.is_file()]
    if not matches:
        matches = sorted(
            candidate for candidate in path.glob("*-eval/properties")
            if candidate.is_file())
    if len(matches) != 1:
        raise AnalysisError(
            "{} contains {} candidate properties files: {}".format(
                path, len(matches),
                ", ".join(map(str, matches)) if matches else "none"))
    return matches[0]


def _load_archive(path):
    try:
        archive = tarfile.open(str(path), mode="r:*")
    except (tarfile.TarError, OSError) as err:
        raise AnalysisError("cannot open archive {}: {}".format(path, err)) from err
    with archive:
        members = [
            member for member in archive.getmembers()
            if member.isfile() and Path(member.name).name == "properties"
        ]
        if len(members) != 1:
            raise AnalysisError(
                "{} contains {} properties members: {}".format(
                    path, len(members),
                    ", ".join(member.name for member in members) or "none"))
        extracted = archive.extractfile(members[0])
        if extracted is None:
            raise AnalysisError("cannot read {} from {}".format(
                members[0].name, path))
        try:
            data = json.loads(extracted.read().decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as err:
            raise AnalysisError("invalid JSON in {}: {}".format(path, err)) from err
    return _normalize_properties(data, str(path))


def load_properties(raw_path):
    if raw_path == "-":
        return _load_json_stream(sys.stdin, "stdin"), "stdin"
    if raw_path is None:
        if DEFAULT_PROPERTIES.is_file():
            path = DEFAULT_PROPERTIES
        elif DEFAULT_ARCHIVE.is_file():
            path = DEFAULT_ARCHIVE
        else:
            raise AnalysisError(
                "no properties input supplied and neither {} nor {} exists".format(
                    DEFAULT_PROPERTIES, DEFAULT_ARCHIVE))
    else:
        path = Path(raw_path)
    if path.is_dir():
        path = _properties_in_directory(path)
    if not path.is_file():
        raise AnalysisError("properties input does not exist: {}".format(path))
    if tarfile.is_tarfile(str(path)):
        return _load_archive(path), str(path)
    try:
        with path.open("r", encoding="utf-8") as stream:
            return _load_json_stream(stream, str(path)), str(path)
    except OSError as err:
        raise AnalysisError("cannot read {}: {}".format(path, err)) from err


def load_task_manifest(path, spec):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as err:
        raise AnalysisError("cannot read task manifest {}: {}".format(path, err)) from err
    descriptions = []
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.count(":") != 1:
            raise AnalysisError(
                "{}:{} must be exactly DOMAIN:PROBLEM".format(path, lineno))
        domain, problem = line.split(":", 1)
        if not domain or not problem or domain.strip() != domain or problem.strip() != problem:
            raise AnalysisError("invalid task description at {}:{}".format(path, lineno))
        descriptions.append((domain, problem))
    digest = hashlib.sha256(
        "".join("{}:{}\n".format(*task) for task in descriptions).encode("utf-8")
    ).hexdigest()
    if digest != spec["digest"]:
        raise AnalysisError(
            "{} manifest digest changed: {} != {}".format(
                spec["label"], digest, spec["digest"]))
    if len(descriptions) != spec["count"] or len(set(descriptions)) != spec["count"]:
        raise AnalysisError(
            "{} must contain {} unique tasks".format(
                spec["label"], spec["count"]))
    domain_counts = Counter(domain for domain, _ in descriptions)
    if len(domain_counts) != spec["domains"] or set(domain_counts.values()) != {2}:
        raise AnalysisError(
            "{} must contain two tasks in each of {} domains".format(
                spec["label"], spec["domains"]))
    return tuple(descriptions)


def load_manifests(pilot_path, cap_v2_path, finalist_v1_path):
    paths = {
        PILOT: pilot_path,
        CAP_V2: cap_v2_path,
        FINALIST_V1: finalist_v1_path,
    }
    manifests = {
        spec["label"]: load_task_manifest(paths[spec["label"]], spec)
        for spec in MANIFEST_SPECS
    }
    occurrences = Counter(
        task for manifest in MANIFEST_ORDER for task in manifests[manifest])
    overlap = sorted(task for task, count in occurrences.items() if count != 1)
    if overlap:
        raise AnalysisError(
            "GHSETA manifests overlap: {}".format(
                ", ".join("{}:{}".format(*task) for task in overlap)))
    return manifests


def load_smoke_manifest(path):
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError as err:
        raise AnalysisError(
            "cannot read smoke manifest {}: {}".format(path, err)) from err
    tasks = []
    for lineno, raw in enumerate(lines, 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) != 2:
            raise AnalysisError(
                "{}:{} must be exactly DOMAIN PROBLEM".format(path, lineno))
        tasks.append(tuple(fields))
    if len(tasks) != len(set(tasks)):
        raise AnalysisError("{} contains duplicate smoke tasks".format(path))
    return tuple(tasks)


def seeded_rank_key(seed, domain, problem):
    payload = "{}\0{}\0{}".format(seed, domain, problem)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), problem


def expected_seeded_selection(records, suite_domains, excluded, seed, label):
    expected = []
    for domain in suite_domains:
        problems = [
            problem for record_domain, problem in records
            if record_domain == domain
        ]
        fresh = sorted(
            (problem for problem in problems
             if (domain, problem) not in excluded),
            key=lambda problem: seeded_rank_key(seed, domain, problem))
        if len(fresh) < 2:
            raise AnalysisError(
                "{} has fewer than two unreserved {} tasks in the cost "
                "manifest".format(domain, label))
        expected.extend((domain, problem) for problem in fresh[:2])
    return tuple(expected)


def validate_name_selections(manifests, smoke_tasks, records, suite_domains):
    cap_excluded = set(manifests[PILOT]) | set(smoke_tasks)
    expected_cap = expected_seeded_selection(
        records, suite_domains, cap_excluded, CAP_V2_SELECTION_SEED, CAP_V2)
    if expected_cap != manifests[CAP_V2]:
        raise AnalysisError(
            "cap-v2 differs from its frozen name-only seeded selection")
    finalist_excluded = cap_excluded | set(manifests[CAP_V2])
    expected_finalist = expected_seeded_selection(
        records, suite_domains, finalist_excluded,
        FINALIST_V1_SELECTION_SEED, FINALIST_V1)
    if expected_finalist != manifests[FINALIST_V1]:
        raise AnalysisError(
            "finalist-v1 differs from its frozen name-only seeded selection")


def load_cost_manifest(path, require, manifests, smoke_path):
    path = Path(path)
    if not path.is_file():
        if require or path != DEFAULT_COST_MANIFEST:
            raise AnalysisError("cost manifest is unavailable: {}".format(path))
        return None
    try:
        import suite_cost_manifest as cost_api
        data = cost_api.load_manifest(path)
        positive, zero = cost_api.task_classes(path)
        supported = cost_api.supported_tasks(path)
    except (ImportError, RuntimeError, OSError) as err:
        raise AnalysisError("invalid cost manifest {}: {}".format(path, err)) from err
    records = {
        (record["domain"], record["problem"]): record
        for record in data["tasks"]
    }
    derived_positive = {
        key for key, record in records.items()
        if record["cost_class"] == "positive-cost"
    }
    derived_zero = set(records) - derived_positive
    if positive != derived_positive or zero != derived_zero:
        raise AnalysisError("cost-manifest API class sets disagree with records")
    derived_supported = {
        key for key, record in records.items()
        if record["cost_class"] == "positive-cost"
        and record["num_normalized_axioms"] == 0
    }
    if supported != derived_supported:
        raise AnalysisError("cost-manifest supported set disagrees with records")
    task_sources_sha256 = {}
    for manifest in MANIFEST_ORDER:
        missing = [task for task in manifests[manifest] if task not in records]
        if missing:
            raise AnalysisError(
                "{} has tasks absent from the cost manifest: {}".format(
                    manifest, ", ".join(
                        "{}:{}".format(*task) for task in missing)))
        selected = sorted(
            (records[task] for task in manifests[manifest]),
            key=lambda record: (record["domain"], record["problem"]))
        task_sources_sha256[manifest] = hashlib.sha256(
            cost_api.canonical_records_bytes(selected)).hexdigest()
    supported_domains = cost_api.domains_with_min_supported_tasks(2, path)
    eligible_domains = [
        domain for domain in data["provenance"]["suite_domains"]
        if domain in supported_domains]
    if len(eligible_domains) != 46 or set(eligible_domains) != supported_domains:
        raise AnalysisError(
            "cost manifest must define exactly 46 suite domains with at "
            "least two supported tasks")
    for manifest in (CAP_V2, FINALIST_V1):
        outside = set(manifests[manifest]) - supported
        if outside:
            raise AnalysisError(
                "{} contains tasks outside the supported positive-cost, "
                "axiom-free population: {}".format(
                    manifest, ", ".join(
                        "{}:{}".format(*task) for task in sorted(outside))))
    validate_name_selections(
        manifests, load_smoke_manifest(smoke_path), supported,
        eligible_domains)
    return {
        "path": path,
        "file_sha256": cost_api.sha256_file(path),
        "records_sha256": data["records_sha256"],
        "records": records,
        "positive": positive,
        "zero": zero,
        "supported": supported,
        "task_sources_sha256": task_sources_sha256,
    }


def _run_dir(index):
    lower = ((index - 1) // 100) * 100 + 1
    upper = ((index + 99) // 100) * 100
    return "runs-{:05d}-{:05d}/{:05d}".format(lower, upper, index)


def expected_command(config):
    return [
        "{cpddl_binary}", "--max-mem", str(MEMORY_LIMIT_MIB),
        *config["options"], "{domain_pddl}", "{problem_pddl}",
    ]


def expected_cells(manifests):
    cells = {}
    index = 0
    digests = {spec["label"]: spec["digest"] for spec in MANIFEST_SPECS}
    for manifest in MANIFEST_ORDER:
        for task in manifests[manifest]:
            for config in CONFIGS:
                index += 1
                key = (config["label"], manifest, task[0], task[1])
                cells[key] = {
                    "index": index,
                    "algorithm": config["label"],
                    "manifest": manifest,
                    "manifest_sha256": digests[manifest],
                    "domain": task[0],
                    "problem": task[1],
                    "id": [config["label"], manifest, task[0], task[1]],
                    "run_dir": _run_dir(index),
                    "component_options": expected_command(config),
                    "cpddl_vendored_upstream_commit": CPDDL_VENDORED_UPSTREAM_COMMIT,
                    "cpddl_tree_anchor_revision": CPDDL_TREE_ANCHOR_REVISION,
                    "cpddl_tracked_tree_oid": CPDDL_TREE_OID,
                    "cpddl_tree_manifest_sha256": CPDDL_TREE_MANIFEST_SHA256,
                    "cpddl_build_config_sha256": CPDDL_BUILD_CONFIG_SHA256,
                    "cpddl_generated_config_sha256": CPDDL_GENERATED_CONFIG_SHA256,
                    "cpddl_binary_version": CPDDL_BINARY_VERSION,
                    "cpddl_binary_sha256": CPDDL_BINARY_SHA256,
                    "cpddl_binary_resource": "resources/pddl-symba",
                    "domain_resource": "domain.pddl",
                    "problem_resource": "problem.pddl",
                    "planner_time_limit": TIME_LIMIT,
                    "planner_memory_limit": MEMORY_LIMIT_MIB,
                    "scheduler_array_task_throttle": 5,
                    "repetitions": REPETITIONS,
                    "search_direction": config["direction"],
                    "fw_potential_objective": config["fw_objective"],
                    "bw_potential_objective": config["bw_objective"],
                    "readme_recommended": config["readme_recommended"],
                    "uses_fdr_tnfm": True,
                }
    if index != EXPECTED_CELLS or len(cells) != EXPECTED_CELLS:
        raise AssertionError(
            "internal expected matrix is not {} cells".format(EXPECTED_CELLS))
    return cells


def identity(record):
    fields = ("algorithm", "manifest", "domain", "problem")
    values = tuple(record.get(field) for field in fields)
    if not all(isinstance(value, str) and value for value in values):
        return None
    return values


def exact_equal(actual, expected):
    if type(expected) in (bool, int):
        return type(actual) is type(expected) and actual == expected
    return actual == expected


def is_sha256(value):
    return isinstance(value, str) and len(value) == 64 and all(
        char in "0123456789abcdef" for char in value)


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _append_error(errors, key, message):
    label = "/".join(key) if key is not None else "record"
    errors.append("{}: {}".format(label, message))


def validate_dynamic(record, key, errors):
    coverage = record.get("coverage")
    if type(coverage) is not int or coverage not in (0, 1):
        _append_error(errors, key, "coverage must be integer 0 or 1")
        return
    outcome = record.get("outcome")
    if outcome not in OUTCOMES:
        _append_error(errors, key, "unexpected/missing outcome {!r}".format(outcome))
        return
    status = record.get("search_status")
    if status is not None and status not in DONE_STATUSES:
        _append_error(errors, key, "invalid search_status {!r}".format(status))
    cost_present = "solution_cost" in record
    cost = record.get("solution_cost")
    if cost_present and (type(cost) is not int or cost < 0):
        _append_error(errors, key, "solution_cost must be a nonnegative integer")
    exit_code = record.get("plan_exit_code")
    if exit_code is not None and type(exit_code) is not int:
        _append_error(errors, key, "plan_exit_code must be an integer when present")
    log_version = record.get("cpddl_log_version")
    if log_version is not None and not isinstance(log_version, str):
        _append_error(errors, key, "cpddl_log_version must be a string when present")
    version_ok = log_version == CPDDL_BINARY_VERSION
    exit_ok = exit_code == 0
    marker_consistent = status in {None, "PLAN FOUND"}
    if cost_present and exit_ok and version_ok and marker_consistent:
        derived_outcome = "solved"
        derived_coverage = 1
    elif status == "PLAN NOT EXIST" and not cost_present and exit_ok and version_ok:
        derived_outcome = "proved_unsolvable"
        derived_coverage = 0
    elif status == "PLAN FOUND" or cost_present:
        derived_outcome = "invalid_solved_evidence"
        derived_coverage = 0
    elif status in {"FAIL", "CONT"}:
        derived_outcome = "search_failed"
        derived_coverage = 0
    else:
        derived_outcome = "censored_or_error"
        derived_coverage = 0
    if outcome != derived_outcome or coverage != derived_coverage:
        _append_error(
            errors, key,
            "parsed outcome/coverage ({!r}, {}) disagrees with strict evidence "
            "({}, {})".format(
                outcome, coverage, derived_outcome, derived_coverage))
    if outcome == "invalid_solved_evidence":
        _append_error(errors, key, "contains contradictory solved evidence")
    expected_match = int(version_ok)
    observed_match = record.get("cpddl_log_version_match")
    if type(observed_match) is not int or observed_match != expected_match:
        _append_error(errors, key, "cpddl_log_version_match is inconsistent")
    expected_done = int(status in DONE_STATUSES)
    observed_done = record.get("native_done_marker")
    if type(observed_done) is not int or observed_done != expected_done:
        _append_error(errors, key, "native_done_marker is inconsistent")
    expected_unsolvable = int(outcome == "proved_unsolvable")
    observed_unsolvable = record.get("proved_unsolvable")
    if (type(observed_unsolvable) is not int or
            observed_unsolvable != expected_unsolvable):
        _append_error(errors, key, "proved_unsolvable is inconsistent")
    if coverage == 1:
        elapsed = finite_number(record.get("total_time"))
        if elapsed is None or elapsed < 0:
            _append_error(errors, key, "solved cell lacks nonnegative total_time")
        if record.get("parser_error"):
            _append_error(errors, key, "solved cell carries parser_error")


def _raise_validation_errors(errors):
    if not errors:
        return
    shown = errors[:40]
    suffix = ""
    if len(errors) > len(shown):
        suffix = "\n... {} additional validation errors".format(
            len(errors) - len(shown))
    raise AnalysisError(
        "matrix validation failed ({} error{}):\n{}{}".format(
            len(errors), "" if len(errors) == 1 else "s",
            "\n".join("- " + error for error in shown), suffix))


def validate_records(records, manifests, cost_info=None):
    expected = expected_cells(manifests)
    errors = []
    matrix = {}
    if len(records) != len(expected):
        errors.append(
            "record count {} != expected {}".format(len(records), len(expected)))
    for record in records:
        key = identity(record)
        if key is None:
            _append_error(
                errors, None,
                "entry {!r} lacks string algorithm/manifest/domain/problem".format(
                    record.get("_source_key")))
            continue
        if key not in expected:
            _append_error(errors, key, "unexpected matrix cell")
            continue
        if key in matrix:
            _append_error(errors, key, "duplicate matrix cell")
            continue
        matrix[key] = record
    for key in expected:
        if key not in matrix:
            _append_error(errors, key, "missing matrix cell")

    task_hashes = {}
    source_manifest_hash = None
    task_source_hashes = {}
    cost_records = cost_info["records"] if cost_info is not None else None
    for key, record in matrix.items():
        cell = expected[key]
        for field, wanted in cell.items():
            if field == "index":
                continue
            if field not in record:
                _append_error(errors, key, "missing static field {}".format(field))
            elif not exact_equal(record[field], wanted):
                _append_error(
                    errors, key,
                    "{}={!r}, expected {!r}".format(
                        field, record[field], wanted))
        domain_hash = record.get("domain_sha256")
        problem_hash = record.get("problem_sha256")
        if not is_sha256(domain_hash):
            _append_error(errors, key, "invalid domain_sha256")
        if not is_sha256(problem_hash):
            _append_error(errors, key, "invalid problem_sha256")
        task_key = (key[2], key[3])
        hash_pair = (domain_hash, problem_hash)
        if task_key in task_hashes and task_hashes[task_key] != hash_pair:
            _append_error(errors, key, "resource hashes differ across configurations")
        else:
            task_hashes[task_key] = hash_pair
        observed_source_manifest = record.get("source_manifest_sha256")
        observed_task_sources = record.get("task_sources_sha256")
        if not is_sha256(observed_source_manifest):
            _append_error(errors, key, "invalid source_manifest_sha256")
        elif source_manifest_hash is None:
            source_manifest_hash = observed_source_manifest
        elif source_manifest_hash != observed_source_manifest:
            _append_error(
                errors, key,
                "source_manifest_sha256 differs across matrix cells")
        manifest = key[1]
        if not is_sha256(observed_task_sources):
            _append_error(errors, key, "invalid task_sources_sha256")
        elif manifest in task_source_hashes:
            if task_source_hashes[manifest] != observed_task_sources:
                _append_error(
                    errors, key,
                    "task_sources_sha256 differs within manifest")
        else:
            task_source_hashes[manifest] = observed_task_sources
        if cost_records is not None:
            if observed_source_manifest != cost_info["file_sha256"]:
                _append_error(
                    errors, key,
                    "source_manifest_sha256 differs from cost manifest")
            if (observed_task_sources !=
                    cost_info["task_sources_sha256"][manifest]):
                _append_error(
                    errors, key,
                    "task_sources_sha256 differs from canonical selected "
                    "cost records")
            cost_record = cost_records.get(task_key)
            if cost_record is None:
                _append_error(errors, key, "task is absent from suite cost manifest")
            else:
                if domain_hash != cost_record["domain_sha256"]:
                    _append_error(errors, key, "domain hash differs from cost manifest")
                if problem_hash != cost_record["problem_sha256"]:
                    _append_error(errors, key, "problem hash differs from cost manifest")
        validate_dynamic(record, key, errors)

    # A valid optimal planner cannot return different costs for one task, and
    # no configuration may prove a task unsolvable if another solves it.
    for manifest in MANIFEST_ORDER:
        for domain, problem in manifests[manifest]:
            task_records = [
                matrix.get((algorithm, manifest, domain, problem))
                for algorithm in ALGORITHMS
            ]
            solved = [record for record in task_records
                      if record is not None and record.get("coverage") == 1]
            costs = {record.get("solution_cost") for record in solved}
            task_key = ("*", manifest, domain, problem)
            if len(costs) > 1:
                _append_error(
                    errors, task_key,
                    "solved configurations disagree on cost: {}".format(
                        ", ".join(map(str, sorted(costs)))))
            if solved and any(
                    record is not None and
                    record.get("outcome") == "proved_unsolvable"
                    for record in task_records):
                _append_error(
                    errors, task_key,
                    "one configuration proves unsolvable while another solves")
    _raise_validation_errors(errors)
    return matrix


def solved(record):
    return record["coverage"] == 1


def domain_groups(tasks):
    groups = defaultdict(list)
    for task in tasks:
        groups[task[0]].append(task)
    return groups


def config_score(matrix, algorithm, manifest, tasks):
    records = [matrix[(algorithm, manifest, task[0], task[1])] for task in tasks]
    solved_count = sum(solved(record) for record in records)
    by_domain = domain_groups(tasks)
    domain_coverages = []
    for domain in sorted(by_domain):
        domain_tasks = by_domain[domain]
        domain_coverages.append(sum(
            solved(matrix[(algorithm, manifest, task[0], task[1])])
            for task in domain_tasks) / len(domain_tasks))
    outcome_counts = Counter(record["outcome"] for record in records)
    par2_values = []
    solved_times = []
    for record in records:
        if solved(record):
            elapsed = float(record["total_time"])
            par2_values.append(elapsed)
            solved_times.append(elapsed)
        else:
            par2_values.append(2.0 * TIME_LIMIT)
    return {
        "tasks": len(tasks),
        "domains": len(by_domain),
        "solved": solved_count,
        "coverage": solved_count / len(tasks),
        "domain_macro": statistics.mean(domain_coverages),
        "outcomes": outcome_counts,
        "par2": statistics.mean(par2_values),
        "median_solved_time": (
            statistics.median(solved_times) if solved_times else None),
    }


def pair_score(matrix, candidate, reference, manifest, tasks):
    wins = losses = both_solved = both_unsolved = 0
    for task in tasks:
        candidate_solved = solved(
            matrix[(candidate, manifest, task[0], task[1])])
        reference_solved = solved(
            matrix[(reference, manifest, task[0], task[1])])
        if candidate_solved and not reference_solved:
            wins += 1
        elif reference_solved and not candidate_solved:
            losses += 1
        elif candidate_solved:
            both_solved += 1
        else:
            both_unsolved += 1
    domain_wins = domain_losses = domain_ties = 0
    domain_deltas = {}
    for domain, domain_tasks in sorted(domain_groups(tasks).items()):
        candidate_coverage = sum(
            solved(matrix[(candidate, manifest, task[0], task[1])])
            for task in domain_tasks) / len(domain_tasks)
        reference_coverage = sum(
            solved(matrix[(reference, manifest, task[0], task[1])])
            for task in domain_tasks) / len(domain_tasks)
        delta = candidate_coverage - reference_coverage
        domain_deltas[domain] = delta
        if delta > 0:
            domain_wins += 1
        elif delta < 0:
            domain_losses += 1
        else:
            domain_ties += 1
    return {
        "wins": wins,
        "losses": losses,
        "both_solved": both_solved,
        "both_unsolved": both_unsolved,
        "paired_delta": (wins - losses) / len(tasks),
        "domain_macro_delta": statistics.mean(domain_deltas.values()),
        "domain_deltas": domain_deltas,
        "domain_wins": domain_wins,
        "domain_losses": domain_losses,
        "domain_ties": domain_ties,
    }


def percentile_type7(sorted_values, probability):
    """Return the linearly interpolated empirical quantile (Hyndman-Fan 7)."""
    if not sorted_values:
        raise AnalysisError("cannot take a percentile of an empty sample")
    position = (len(sorted_values) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    fraction = position - lower
    return (sorted_values[lower] * (1.0 - fraction)
            + sorted_values[upper] * fraction)


def _cluster_draws(context, replicate, cluster_count):
    """Draw cluster indices from a byte-stable SHAKE stream.

    Rejection sampling removes modulo bias. A new SHAKE block is used only if
    a 32-bit word falls in the incomplete upper residue class.
    """
    if cluster_count <= 0:
        raise AnalysisError("cluster bootstrap needs at least one domain")
    modulus = 1 << 32
    acceptance_limit = modulus - (modulus % cluster_count)
    draws = []
    block = 0
    while len(draws) < cluster_count:
        payload = "{}\0{}\0{}\0{}".format(
            BOOTSTRAP_SEED, context, replicate, block).encode("utf-8")
        remaining = cluster_count - len(draws)
        raw = hashlib.shake_256(payload).digest(4 * (remaining + 4))
        for offset in range(0, len(raw), 4):
            value = int.from_bytes(raw[offset:offset + 4], "big")
            if value < acceptance_limit:
                draws.append(value % cluster_count)
                if len(draws) == cluster_count:
                    break
        block += 1
    return draws


def domain_cluster_bootstrap_ci(domain_deltas, context):
    """Percentile CI after resampling represented domains with replacement."""
    domains = sorted(domain_deltas)
    values = [domain_deltas[domain] for domain in domains]
    stream_context = "{}\0{}".format(context, "\0".join(domains))
    estimates = []
    for replicate in range(BOOTSTRAP_REPLICATES):
        draws = _cluster_draws(stream_context, replicate, len(domains))
        estimates.append(math.fsum(values[index] for index in draws)
                         / len(draws))
    estimates.sort()
    alpha = 1.0 - BOOTSTRAP_CONFIDENCE
    return (
        percentile_type7(estimates, alpha / 2.0),
        percentile_type7(estimates, 1.0 - alpha / 2.0),
    )


def bootstrap_context(manifest, subset_name, candidate, reference):
    return "\0".join((manifest, subset_name, candidate, reference))


def fmt_number(value, digits=4):
    if value is None:
        return "NA"
    if isinstance(value, int):
        return str(value)
    return ("{:.{}f}".format(value, digits)).rstrip("0").rstrip(".")


def fmt_percent(value):
    return "{:.2f}%".format(100.0 * value)


def fmt_interval(interval):
    return "[{}, {}]".format(
        fmt_percent(interval[0]), fmt_percent(interval[1]))


def table(headers, rows):
    text_rows = [[str(cell) for cell in row] for row in rows]
    widths = [len(str(header)) for header in headers]
    for row in text_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = []
    lines.append("  ".join(
        str(header).ljust(widths[index])
        for index, header in enumerate(headers)))
    lines.append("  ".join("-" * width for width in widths))
    for row in text_rows:
        lines.append("  ".join(
            cell.ljust(widths[index]) for index, cell in enumerate(row)))
    return lines


def render_subset(matrix, manifest, subset_name, tasks):
    lines = []
    lines.append("\n[{} / {}] {} tasks, {} represented domains".format(
        manifest, subset_name, len(tasks), len(domain_groups(tasks))))
    lines.append("Primary coverage estimands (fixed configuration order)")
    rows = []
    scores = {}
    for algorithm in ALGORITHMS:
        score = config_score(matrix, algorithm, manifest, tasks)
        scores[algorithm] = score
        rows.append((
            algorithm, "{}/{}".format(score["solved"], score["tasks"]),
            fmt_percent(score["coverage"]),
            fmt_percent(score["domain_macro"]),
        ))
    lines.extend(table(
        ("configuration", "solved", "task coverage", "domain-macro"), rows))

    lines.append("\nPrimary paired coverage contrasts (candidate - reference)")
    rows = []
    for candidate, reference in PRIMARY_PAIRS:
        score = pair_score(matrix, candidate, reference, manifest, tasks)
        interval = domain_cluster_bootstrap_ci(
            score["domain_deltas"],
            bootstrap_context(
                manifest, subset_name, candidate, reference))
        rows.append((
            candidate, reference, score["wins"], score["losses"],
            fmt_percent(score["paired_delta"]),
            fmt_percent(score["domain_macro_delta"]),
            fmt_interval(interval),
            "{}/{}/{}".format(
                score["domain_wins"], score["domain_losses"],
                score["domain_ties"]),
        ))
    lines.extend(table(
        ("candidate", "reference", "discordant wins", "discordant losses",
         "paired delta", "domain-macro delta", "95% cluster CI",
         "domain W/L/T"), rows))

    lines.append("\nPer-configuration outcome counts (descriptive)")
    rows = []
    for algorithm in ALGORITHMS:
        counts = scores[algorithm]["outcomes"]
        rows.append((
            algorithm, counts["solved"], counts["proved_unsolvable"],
            counts["search_failed"], counts["censored_or_error"],
            counts["invalid_solved_evidence"],
        ))
    lines.extend(table(
        ("configuration", "solved", "unsolvable", "failed", "censored/error",
         "invalid evidence"), rows))

    lines.append("\nRuntime screening (one run/cell; no ranking or selection)")
    rows = []
    for algorithm in ALGORITHMS:
        score = scores[algorithm]
        rows.append((
            algorithm, fmt_number(score["par2"]),
            fmt_number(score["median_solved_time"]),
        ))
    lines.extend(table(
        ("configuration", "PAR2 seconds", "median solved total_time"), rows))
    return lines


def render_report(source, records, matrix, manifests, cost_info, runner_hash):
    lines = [
        "CPDDL GHSETA frozen analysis",
        "source: {}".format(source),
        "validated cells: {}/{}".format(len(records), EXPECTED_CELLS),
        "runner SHA-256: {}".format(runner_hash),
        "resource envelope: {} seconds, {} MiB, {} repetition".format(
            TIME_LIMIT, MEMORY_LIMIT_MIB, REPETITIONS),
        "configuration order: {}".format(", ".join(ALGORITHMS)),
        ("separation rule: pilot50, cap-v2, and finalist-v1 are never "
         "pooled"),
        ("selection rule: none; cap-v2 and finalist-v1 outcomes cannot "
         "promote, rank, or tune a GHSETA configuration"),
        ("domain-cluster bootstrap: {} percentile replicates, {:.0f}% CI, "
         "SHAKE stream seed {}".format(
             BOOTSTRAP_REPLICATES, 100 * BOOTSTRAP_CONFIDENCE,
             BOOTSTRAP_SEED)),
    ]
    if cost_info is None:
        lines.append(
            "cost manifest: UNAVAILABLE; supported-population sections suppressed "
            "without outcome-derived substitution")
    else:
        lines.append("cost manifest: {} (file SHA-256 {}, records SHA-256 {})".format(
            cost_info["path"], cost_info["file_sha256"],
            cost_info["records_sha256"]))

    for manifest in MANIFEST_ORDER:
        lines.append("\n=== {} (independent report; no pooled estimand) ===".format(
            manifest))
        if cost_info is not None:
            lines.append(
                "source attestation: canonical selected records SHA-256 {}".format(
                    cost_info["task_sources_sha256"][manifest]))
        full_tasks = manifests[manifest]
        if cost_info is None:
            lines.extend(render_subset(
                matrix, manifest, "full frozen set (secondary context)",
                full_tasks))
            lines.append(
                "\n[{} / supported positive-cost, axiom-free (PRIMARY)] "
                "UNAVAILABLE: frozen cost manifest absent".format(
                    manifest))
        else:
            supported_tasks = tuple(
                task for task in full_tasks if task in cost_info["supported"])
            if not supported_tasks:
                raise AnalysisError(
                    "{} has no supported positive-cost, axiom-free tasks in "
                    "the cost manifest".format(manifest))
            lines.extend(render_subset(
                matrix, manifest,
                "supported positive-cost, axiom-free (PRIMARY)",
                supported_tasks))
            if supported_tasks != full_tasks:
                lines.extend(render_subset(
                    matrix, manifest, "full frozen set (secondary context)",
                    full_tasks))

    lines.extend([
        "\nInterpretation contract",
        ("- Paired task coverage and equally weighted domain-macro coverage "
         "on the supported positive-cost, axiom-free population are primary."),
        ("- Cluster-bootstrap percentile intervals resample represented domains "
         "with replacement and retain every task in each sampled domain; "
         "Hyndman-Fan type-7 quantiles are used."),
        ("- The full frozen set is secondary context when it differs from "
         "the supported primary population."),
        ("- PAR2 uses 600 seconds for every unsolved cell and CPDDL Overall "
         "Elapsed Time for solved cells."),
        ("- PAR2 and solved-runtime summaries are one-run screening evidence "
         "without a noise estimate."),
        ("- Tables retain the frozen configuration order and make no winner/"
         "selection claim on cap-v2 or finalist-v1."),
        ("- Static source/config/executable pins are independent attestations, "
         "not a reproducible-build proof."),
    ])
    return "\n".join(lines) + "\n"


def _fake_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def synthetic_fixture(manifests):
    cost_records = {}
    positive = set()
    zero = set()
    supported = set()
    all_tasks = [
        task for manifest in MANIFEST_ORDER for task in manifests[manifest]
    ]
    for index, task in enumerate(all_tasks):
        in_pilot = index < len(manifests[PILOT])
        cost_class = (
            "zero-cost" if in_pilot and index % 5 == 0 else "positive-cost")
        num_normalized_axioms = int(in_pilot and index % 7 == 0)
        record = {
            "domain": task[0],
            "problem": task[1],
            "domain_sha256": _fake_hash("domain\0{}".format(task[0])),
            "problem_sha256": _fake_hash("problem\0{}\0{}".format(*task)),
            "cost_class": cost_class,
            "num_normalized_axioms": num_normalized_axioms,
        }
        cost_records[task] = record
        (zero if cost_class == "zero-cost" else positive).add(task)
        if cost_class == "positive-cost" and num_normalized_axioms == 0:
            supported.add(task)
    source_manifest_sha256 = _fake_hash("synthetic-file")
    task_sources_sha256 = {
        manifest: _fake_hash("synthetic-selected\0{}".format(manifest))
        for manifest in MANIFEST_ORDER
    }
    cost_info = {
        "path": Path("synthetic-cost-manifest.json"),
        "file_sha256": source_manifest_sha256,
        "records_sha256": _fake_hash("synthetic-records"),
        "records": cost_records,
        "positive": positive,
        "zero": zero,
        "supported": supported,
        "task_sources_sha256": task_sources_sha256,
    }
    cells = expected_cells(manifests)
    records = []
    for key, cell in cells.items():
        algorithm, manifest, domain, problem = key
        task = (domain, problem)
        record = {
            field: copy.deepcopy(value)
            for field, value in cell.items() if field != "index"
        }
        record["domain_sha256"] = cost_records[task]["domain_sha256"]
        record["problem_sha256"] = cost_records[task]["problem_sha256"]
        record["source_manifest_sha256"] = source_manifest_sha256
        record["task_sources_sha256"] = task_sources_sha256[manifest]
        task_index = all_tasks.index(task)
        algorithm_index = ALGORITHMS.index(algorithm)
        is_solved = (task_index + algorithm_index) % 4 != 0
        config = CONFIG_BY_LABEL[algorithm]
        if is_solved:
            record.update({
                "coverage": 1,
                "solution_cost": 10 + task_index,
                "total_time": 1.0 + task_index / 100.0 + algorithm_index / 10.0,
                "cpddl_log_version": CPDDL_BINARY_VERSION,
                "cpddl_log_version_match": 1,
                "plan_exit_code": 0,
                "outcome": "solved",
                "proved_unsolvable": 0,
                "native_done_marker": int(
                    config["direction"] == "bidirectional"),
            })
            if config["direction"] == "bidirectional":
                record["search_status"] = "PLAN FOUND"
        else:
            record.update({
                "coverage": 0,
                "cpddl_log_version": CPDDL_BINARY_VERSION,
                "cpddl_log_version_match": 1,
                "plan_exit_code": 143,
                "outcome": "censored_or_error",
                "proved_unsolvable": 0,
                "native_done_marker": 0,
            })
        records.append(record)
    return records, cost_info


def _expect_rejection(name, records, manifests, cost_info, mutate):
    candidate = copy.deepcopy(records)
    mutate(candidate)
    try:
        validate_records(candidate, manifests, cost_info)
    except AnalysisError:
        return name
    raise AssertionError("synthetic mutation was accepted: {}".format(name))


def run_self_tests(manifests):
    records, cost_info = synthetic_fixture(manifests)
    matrix = validate_records(records, manifests, cost_info)
    report = render_report(
        "synthetic", records, matrix, manifests, cost_info,
        EXPECTED_RUNNER_SHA256)
    assert report.count("=== pilot50") == 1
    assert report.count("=== cap-v2") == 1
    assert report.count("=== finalist-v1") == 1
    assert "pilot50, cap-v2, and finalist-v1 are never pooled" in report
    assert "selection rule: none" in report
    assert "pilot50 / supported positive-cost, axiom-free (PRIMARY)" in report
    assert "cap-v2 / supported positive-cost, axiom-free (PRIMARY)" in report
    assert "finalist-v1 / supported positive-cost, axiom-free (PRIMARY)" in report
    full_only_matrix = validate_records(records, manifests, None)
    full_only_report = render_report(
        "synthetic", records, full_only_matrix, manifests, None,
        EXPECTED_RUNNER_SHA256)
    assert full_only_report.count(
        "supported positive-cost, axiom-free (PRIMARY)] UNAVAILABLE") == 3
    assert "without outcome-derived substitution" in full_only_report

    # The stream and percentile rule must be exactly repeatable. Pin the
    # synthetic interval digest so accidental changes fail before outcomes.
    ci_values = []
    candidate, reference = PRIMARY_PAIRS[0]
    for manifest in MANIFEST_ORDER:
        pair = pair_score(
            matrix, candidate, reference, manifest, manifests[manifest])
        context = bootstrap_context(
            manifest, "full frozen set", candidate, reference)
        first = domain_cluster_bootstrap_ci(pair["domain_deltas"], context)
        second = domain_cluster_bootstrap_ci(pair["domain_deltas"], context)
        assert first == second
        ci_values.append(first)
    ci_digest = hashlib.sha256(json.dumps(
        ci_values, separators=(",", ":")).encode("ascii")).hexdigest()
    assert ci_digest == (
        "8f74c0348cbb08a2535d7d0a3a13d816898a350731376332efe1cde6e7b6a0f4"
    ), ci_digest

    tests = []
    tests.append(_expect_rejection(
        "missing cell", records, manifests, cost_info,
        lambda candidate: candidate.pop()))
    tests.append(_expect_rejection(
        "duplicate cell", records, manifests, cost_info,
        lambda candidate: candidate.append(copy.deepcopy(candidate[0]))))
    tests.append(_expect_rejection(
        "wrong options", records, manifests, cost_info,
        lambda candidate: candidate[0].__setitem__("component_options", [])))
    tests.append(_expect_rejection(
        "wrong source tree", records, manifests, cost_info,
        lambda candidate: candidate[0].__setitem__(
            "cpddl_tracked_tree_oid", "0" * 40)))
    tests.append(_expect_rejection(
        "wrong binary", records, manifests, cost_info,
        lambda candidate: candidate[0].__setitem__(
            "cpddl_binary_sha256", "0" * 64)))
    tests.append(_expect_rejection(
        "wrong limit", records, manifests, cost_info,
        lambda candidate: candidate[0].__setitem__("planner_time_limit", 301)))
    tests.append(_expect_rejection(
        "wrong array throttle", records, manifests, cost_info,
        lambda candidate: candidate[0].__setitem__(
            "scheduler_array_task_throttle", None)))
    tests.append(_expect_rejection(
        "wrong manifest digest", records, manifests, cost_info,
        lambda candidate: candidate[0].__setitem__("manifest_sha256", "0" * 64)))
    tests.append(_expect_rejection(
        "wrong source manifest", records, manifests, cost_info,
        lambda candidate: candidate[0].__setitem__(
            "source_manifest_sha256", "0" * 64)))
    tests.append(_expect_rejection(
        "wrong task source attestation", records, manifests, cost_info,
        lambda candidate: candidate[0].__setitem__(
            "task_sources_sha256", "0" * 64)))
    tests.append(_expect_rejection(
        "wrong resource hash", records, manifests, cost_info,
        lambda candidate: candidate[0].__setitem__("problem_sha256", "0" * 64)))

    def disagree(candidate):
        first = next(record for record in candidate if record["coverage"] == 1)
        task = (first["manifest"], first["domain"], first["problem"])
        second = next(
            record for record in candidate
            if record["coverage"] == 1 and
            (record["manifest"], record["domain"], record["problem"]) == task and
            record["algorithm"] != first["algorithm"])
        second["solution_cost"] += 1

    tests.append(_expect_rejection(
        "solved cost disagreement", records, manifests, cost_info, disagree))

    def contradict_marker(candidate):
        record = next(
            record for record in candidate
            if record["coverage"] == 1 and
            record["search_direction"] == "forward")
        record["search_status"] = "PLAN NOT EXIST"
        record["native_done_marker"] = 1

    tests.append(_expect_rejection(
        "contradictory forward marker", records, manifests, cost_info,
        contradict_marker))
    print("GHSETA analyzer synthetic self-tests: PASS")
    print("accepted complete matrix: {0}/{0} cells".format(EXPECTED_CELLS))
    print("rejection checks: {}".format(", ".join(tests)))
    print("report separation: pilot50, cap-v2, finalist-v1 independent")
    print("supported-population source: synthetic manifest records only")


def main(argv=None):
    args = parse_args(argv)
    runner_hash = validate_runner_source()
    manifests = load_manifests(
        args.pilot_manifest, args.cap_v2_manifest,
        args.finalist_v1_manifest)
    if args.self_test:
        run_self_tests(manifests)
        return 0
    cost_info = load_cost_manifest(
        args.cost_manifest, args.require_cost_manifest, manifests,
        args.smoke_manifest)
    records, source = load_properties(args.properties)
    matrix = validate_records(records, manifests, cost_info)
    sys.stdout.write(render_report(
        source, records, matrix, manifests, cost_info, runner_hash))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AnalysisError as err:
        print("analysis error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
