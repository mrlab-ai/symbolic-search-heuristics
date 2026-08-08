#!/usr/bin/env python3
"""Prospective CPDDL GHSETA baseline on three frozen manifests.

Scheduled configurations (all use --fdr-tnfm):

  cpddl_blind_fw                  forward blind control
  cpddl_blind_bi                  bidirectional blind control
  cpddl_ghseta_fw_i              forward, I objective
  cpddl_ghseta_fw_a_plus_i       forward, A+I objective
  cpddl_ghseta_bi_a_plus_i_blind bidirectional, forward A+I / blind backward
  cpddl_ghseta_bi_a_plus_i_i     bidirectional, forward A+I / backward I

The blind controls isolate heuristic overhead.  The I/A+I forward pair
isolates the potential objective, and the final pair compares the vendored
README's recommended forward-A+I/blind-backward command with an I-guided
backward direction.

Every configuration runs once on the 50-task outcome-enriched pilot, 92-task
cap-v2 validation, and disjoint 92-task finalist-v1 validation at 300 seconds
and 8192 MiB: 1404 runs in total. Task ordering, disjointness, name-only
selection, benchmark paths, PDDL bytes and canonical manifest hashes are
validated before Lab can build.  Lab copies the exact executable once into the
built experiment and copies the domain and problem into every run.  Every
record stores their SHA-256 digests, the resource-relative command, limits,
name/source manifest attestations, tracked vendored-tree attestations, ignored
build-config digests, binary hash and exact expected/reported version.

The binary's version suffix comes from the enclosing SymK git checkout at
CPDDL build time, not from the removed CPDDL repository. It is therefore
recorded separately and is not presented as CPDDL source provenance.  The
upstream commit below is the vendoring record; the pinned Git tree object and
tree-manifest digest identify the accompanying tracked source bytes, while the
binary is attested independently.  This is not a reproducible-build proof.

The three reports are deliberately disjoint.  Never pool pilot, cap-v2 and
finalist-v1 rows into one headline result.

Validate only (does not build or launch):
  experiments/.venv/bin/python experiments/exp_cpddl_ghseta.py --validate-only

Run only after sign-off. Use the same scheduler environment for both commands;
never combine the steps:
  experiments/.venv/bin/python experiments/exp_cpddl_ghseta.py build
  experiments/.venv/bin/python experiments/exp_cpddl_ghseta.py start
  experiments/.venv/bin/python experiments/exp_cpddl_ghseta.py parse fetch \
      report-pilot report-cap-v2 report-finalist-v1
"""

import argparse
import hashlib
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from downward import suites  # noqa: E402
from downward.reports.absolute import AbsoluteReport  # noqa: E402
from lab.experiment import Experiment  # noqa: E402
from lab.parser import Parser  # noqa: E402

import exp_common as C  # noqa: E402
import suite_cost_manifest  # noqa: E402
from exp_ms_caps_pilot import read_manifest as read_pilot  # noqa: E402
from exp_ms_caps_validation import (  # noqa: E402
    supported_candidate_domains,
    validate_manifest as validate_cap_v2,
)


CPDDL = C.REPO / "baselines" / "cpddl" / "bin" / "pddl-symba"
CPDDL_OPTIONS_SOURCE = C.REPO / "baselines" / "cpddl" / "bin" / "options.c"
CPDDL_BUILD_CONFIG = C.REPO / "baselines" / "cpddl" / "Makefile.config"
CPDDL_GENERATED_CONFIG = C.REPO / "baselines" / "cpddl" / "pddl" / "config.h"

# The nested upstream Git metadata was removed when CPDDL was vendored.  This
# value is therefore a recorded upstream identity, not something the runner can
# independently recover from the vendored directory.
CPDDL_VENDORED_UPSTREAM_COMMIT = (
    "2c7de0ec0e7d1d002a08aead4c5c5bbdcf171b89")

# Local, byte-level provenance.  The anchor commit contains the exact tracked
# CPDDL tree; the working tree must have no tracked difference from it.
CPDDL_TREE_ANCHOR_REVISION = (
    "c2800d7e65abb61d4b94b08a5487f701ceb41d6b")
EXPECTED_CPDDL_TREE_OID = "c61b00eecb7c4223f4b5f358f900c5fc4a1c6dec"
EXPECTED_CPDDL_TREE_MANIFEST_SHA256 = (
    "3673059666688e581d3593ec87088c640032d42481be3e6f3e754a1e08bb2be2")

# Ignored build inputs and resulting executable are pinned independently of the
# tracked source.  The generated config is included because Makefile.config is
# not the only ignored file that controls the compiled feature macros.
EXPECTED_CPDDL_BUILD_CONFIG_SHA256 = (
    "908c2dadd8fed416ee42b12c2dd9d815a93732802e099735c6221de215f78908")
EXPECTED_CPDDL_GENERATED_CONFIG_SHA256 = (
    "88abd4f6bea7a27b75e3c536b82b56dbd3db67a3c17875dc346488613358b997")
EXPECTED_CPDDL_BINARY_SHA256 = (
    "df2dba3e604c10caf17e2ec6b86b7007bbdabc49fc77bbb34745d1ee3f0cd056")
EXPECTED_CPDDL_BINARY_VERSION = (
    "1.5-409658ea3bdf92b21170d66a12fc489311e755e6")

TIME_LIMIT = 300
MEMORY_LIMIT = 8192
PILOT_DIGEST = "c63a59ee2096b40c24f80db895ee2c0d22aabc2630c823b882e7f50f529a481b"
CAP_V2_DIGEST = "daca0c3ba0f029d7dc61b342c5ba99cd53c00b1cbfdbe7744d3fca0aa4431161"
FINALIST_V1_DIGEST = (
    "fc63d4eed62816a2e065cb89f89483999a7b51067b7077969d10b2a338f19760")
FINALIST_V1_SELECTION_SEED = (
    "symbolic-search-heuristics/heuristic-finalists-validation/v1")
FINALIST_V1_MANIFEST = Path(__file__).with_name(
    "heuristic_finalists_validation_suite.txt")
SMOKE_MANIFEST = Path(__file__).with_name("smoke_suite.txt")

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


def manifest_digest(tasks):
    text = "".join("{}\n".format(task) for task in tasks)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_pilot():
    tasks = read_pilot()
    counts = Counter(task.split(":", 1)[0] for task in tasks)
    if len(tasks) != 50 or len(set(tasks)) != 50:
        raise RuntimeError("pilot manifest must have 50 unique tasks")
    if len(counts) != 25 or set(counts.values()) != {2}:
        raise RuntimeError("pilot manifest must have two tasks in 25 domains")
    actual = manifest_digest(tasks)
    if actual != PILOT_DIGEST:
        raise RuntimeError(
            "pilot manifest digest changed: {} != {}".format(
                actual, PILOT_DIGEST))
    return tasks


def read_colon_manifest(path):
    tasks = []
    for lineno, raw_line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.count(":") != 1:
            raise RuntimeError(
                "{}:{} must contain DOMAIN:PROBLEM".format(path, lineno))
        domain, problem = line.split(":", 1)
        if not domain or not problem:
            raise RuntimeError(
                "{}:{} has an empty domain/problem".format(path, lineno))
        tasks.append(line)
    if len(tasks) != len(set(tasks)):
        raise RuntimeError("{} contains duplicate tasks".format(path))
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


def finalist_rank_key(domain, problem):
    payload = "{}\0{}\0{}".format(
        FINALIST_V1_SELECTION_SEED, domain, problem)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest(), problem


def validate_finalist_v1(pilot, cap_v2):
    tasks = read_colon_manifest(FINALIST_V1_MANIFEST)
    if len(tasks) != 92 or len(set(tasks)) != 92:
        raise RuntimeError("finalist-v1 manifest must have 92 unique tasks")
    actual = manifest_digest(tasks)
    if actual != FINALIST_V1_DIGEST:
        raise RuntimeError(
            "finalist-v1 manifest digest changed: {} != {}".format(
                actual, FINALIST_V1_DIGEST))
    excluded = set(pilot) | set(cap_v2) | read_smoke_manifest()
    expected = []
    supported = suite_cost_manifest.supported_tasks()
    supported_domains = supported_candidate_domains()
    for domain in supported_domains:
        matches = suites.build_suite(str(C.BENCHMARKS), [domain])
        by_problem = {task.problem: task for task in matches}
        if len(by_problem) != len(matches):
            raise RuntimeError(
                "duplicate problem name in finalist-v1 domain {}".format(domain))
        fresh = sorted(
            (problem for problem in by_problem
             if (domain, problem) in supported
             and "{}:{}".format(domain, problem) not in excluded),
            key=lambda problem: finalist_rank_key(domain, problem))
        if len(fresh) < 2:
            raise RuntimeError(
                "{} has fewer than two unreserved finalist tasks".format(domain))
        expected.extend("{}:{}".format(domain, problem)
                        for problem in fresh[:2])
    if tasks != expected:
        raise RuntimeError(
            "finalist-v1 manifest differs from its name-only seeded selection")
    counts = Counter(task.split(":", 1)[0] for task in tasks)
    if (list(counts) != supported_domains
            or set(counts.values()) != {2}):
        raise RuntimeError(
            "finalist-v1 must contain two tasks in each suite domain with at "
            "least two supported tasks, in suite order")
    supported = suite_cost_manifest.supported_tasks()
    task_keys = {tuple(task.split(":", 1)) for task in tasks}
    if not task_keys <= supported:
        raise RuntimeError(
            "finalist-v1 contains tasks outside the frozen supported "
            "positive-cost, axiom-free population")
    overlap = set(tasks) & excluded
    if overlap:
        raise RuntimeError(
            "finalist-v1 overlaps prior manifests: {}".format(
                ", ".join(sorted(overlap))))
    return tasks


def resolve_tasks(descriptions):
    matches = suites.build_suite(str(C.BENCHMARKS), descriptions)
    by_name = {
        "{}:{}".format(task.domain, task.problem): task
        for task in matches
    }
    if len(matches) != len(descriptions) or len(by_name) != len(descriptions):
        raise RuntimeError(
            "{} frozen descriptions resolved to {} tasks ({} unique)".format(
                len(descriptions), len(matches), len(by_name)))
    resolved = []
    for description in descriptions:
        if description not in by_name:
            raise RuntimeError("{} did not resolve".format(description))
        task = by_name[description]
        domain_file = Path(task.domain_file)
        problem_file = Path(task.problem_file)
        if not domain_file.is_file() or not problem_file.is_file():
            raise RuntimeError(
                "missing files for {}: {}, {}".format(
                    description, domain_file, problem_file))
        resolved.append(
            (task.domain, task.problem, domain_file, problem_file))
    return resolved


def validate_manifests():
    pilot = validate_pilot()
    (cap_v2, cap_v2_task_sources_sha256,
     cap_v2_source_manifest_sha256) = validate_cap_v2()
    if len(cap_v2) != 92 or len(set(cap_v2)) != 92:
        raise RuntimeError("cap-v2 manifest must have 92 unique tasks")
    actual = manifest_digest(cap_v2)
    if actual != CAP_V2_DIGEST:
        raise RuntimeError(
            "cap-v2 manifest digest changed: {} != {}".format(
                actual, CAP_V2_DIGEST))
    finalist_v1 = validate_finalist_v1(pilot, cap_v2)
    descriptions = {
        "pilot50": (PILOT_DIGEST, pilot),
        "cap-v2": (CAP_V2_DIGEST, cap_v2),
        "finalist-v1": (FINALIST_V1_DIGEST, finalist_v1),
    }
    all_tasks = []
    for manifest, (_, tasks) in descriptions.items():
        for task in tasks:
            all_tasks.append((manifest, task))
    by_task = Counter(task for _, task in all_tasks)
    overlap = sorted(task for task, count in by_task.items() if count != 1)
    if overlap:
        raise RuntimeError(
            "GHSETA manifests overlap: {}".format(", ".join(overlap)))
    source_manifest_sha256 = suite_cost_manifest.sha256_file(
        suite_cost_manifest.MANIFEST_PATH)
    if source_manifest_sha256 != cap_v2_source_manifest_sha256:
        raise RuntimeError(
            "cap-v2 source-manifest attestation disagrees with GHSETA")
    manifests = []
    for manifest in ("pilot50", "cap-v2", "finalist-v1"):
        digest, tasks = descriptions[manifest]
        resolved = resolve_tasks(tasks)
        source_digest = suite_cost_manifest.validate_task_sources(
            resolved, C.BENCHMARKS)
        if (manifest == "cap-v2"
                and source_digest != cap_v2_task_sources_sha256):
            raise RuntimeError(
                "cap-v2 task-source attestation disagrees with GHSETA")
        manifests.append((
            manifest, digest, source_digest, source_manifest_sha256, resolved))
    return tuple(manifests)


def file_digest(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_cpddl():
    required_files = (CPDDL, CPDDL_BUILD_CONFIG, CPDDL_GENERATED_CONFIG)
    missing_files = [str(path) for path in required_files if not path.is_file()]
    if missing_files:
        raise RuntimeError(
            "missing CPDDL build artifact(s): {}; see baselines/README.md".format(
                ", ".join(missing_files)))

    tree_spec = "{}:baselines/cpddl".format(CPDDL_TREE_ANCHOR_REVISION)
    tree_run = subprocess.run(
        ["git", "-C", str(C.REPO), "rev-parse", tree_spec],
        capture_output=True, text=True, check=True)
    tree_oid = tree_run.stdout.strip()
    if tree_oid != EXPECTED_CPDDL_TREE_OID:
        raise RuntimeError(
            "pinned CPDDL tree object changed: {} != {}".format(
                tree_oid, EXPECTED_CPDDL_TREE_OID))
    tree_listing = subprocess.run(
        ["git", "-C", str(C.REPO), "ls-tree", "-r", "-z", tree_spec],
        capture_output=True, check=True).stdout
    tree_manifest_sha256 = hashlib.sha256(tree_listing).hexdigest()
    if tree_manifest_sha256 != EXPECTED_CPDDL_TREE_MANIFEST_SHA256:
        raise RuntimeError(
            "pinned CPDDL tree manifest changed: {} != {}".format(
                tree_manifest_sha256,
                EXPECTED_CPDDL_TREE_MANIFEST_SHA256))
    tracked_diff = subprocess.run(
        ["git", "-C", str(C.REPO), "diff", "--quiet",
         CPDDL_TREE_ANCHOR_REVISION, "--", "baselines/cpddl"],
        check=False)
    if tracked_diff.returncode == 1:
        raise RuntimeError(
            "tracked baselines/cpddl files differ from pinned tree {}".format(
                EXPECTED_CPDDL_TREE_OID))
    if tracked_diff.returncode != 0:
        raise RuntimeError(
            "git diff failed with exit {} while checking CPDDL".format(
                tracked_diff.returncode))

    pinned_files = (
        (CPDDL_BUILD_CONFIG, EXPECTED_CPDDL_BUILD_CONFIG_SHA256),
        (CPDDL_GENERATED_CONFIG, EXPECTED_CPDDL_GENERATED_CONFIG_SHA256),
        (CPDDL, EXPECTED_CPDDL_BINARY_SHA256),
    )
    actual_digests = {}
    for path, expected in pinned_files:
        actual = file_digest(path)
        if actual != expected:
            raise RuntimeError(
                "{} SHA-256 changed: {} != {}".format(
                    path, actual, expected))
        actual_digests[path] = actual

    version_run = subprocess.run(
        [str(CPDDL), "--version"], capture_output=True, text=True, check=True)
    version = (version_run.stdout + version_run.stderr).strip()
    if version != EXPECTED_CPDDL_BINARY_VERSION:
        raise RuntimeError(
            "CPDDL version changed: {!r} != {!r}".format(
                version, EXPECTED_CPDDL_BINARY_VERSION))
    # CPDDL intentionally returns 255 after printing help.
    help_run = subprocess.run(
        [str(CPDDL), "--help"], capture_output=True, text=True, check=False)
    if help_run.returncode not in (0, 255):
        raise RuntimeError(
            "CPDDL --help returned {}".format(help_run.returncode))
    help_text = help_run.stdout + help_run.stderr
    required = (
        "fdr-tnfm", "--symba", "symba-fw-pot",
        "--symba-fw-pot-cfg", "symba-bw-pot",
        "--symba-bw-pot-cfg",
    )
    missing = [option for option in required if option not in help_text]
    if missing:
        raise RuntimeError(
            "CPDDL help lacks: {}".format(", ".join(missing)))
    source = CPDDL_OPTIONS_SOURCE.read_text(encoding="utf-8")
    objective_definitions = (
        'optsParamsAddFlagFn(params, "I", cfg, hpotSetObjInit);',
        'optsParamsAddFlagFn(params, "A+I", cfg, hpotSetObjAllStatesInit);',
    )
    missing = [text for text in objective_definitions if text not in source]
    if missing:
        raise RuntimeError(
            "CPDDL options.c lacks objective definitions: {}".format(
                ", ".join(missing)))
    return {
        "version": version,
        "sha256": actual_digests[CPDDL],
        "tree_oid": tree_oid,
        "tree_manifest_sha256": tree_manifest_sha256,
        "build_config_sha256": actual_digests[CPDDL_BUILD_CONFIG],
        "generated_config_sha256": actual_digests[CPDDL_GENERATED_CONFIG],
    }


def command(config, binary, domain_file, problem_file):
    return [
        str(binary), "--max-mem", str(MEMORY_LIMIT),
        *config["options"], str(domain_file), str(problem_file),
    ]


def get_parser():
    parser = Parser()
    parser.add_pattern(
        "solution_cost", r"SYMBA: Plan Cost: (-?\d+)",
        type=int, required=False)
    parser.add_pattern(
        "total_time", r"Overall Elapsed Time: ([0-9]+(?:\.[0-9]+)?)s",
        type=float, required=False)
    parser.add_pattern(
        "cpddl_log_version", r"Version: (1\.5-[0-9a-f]{40})",
        type=str, required=False)
    parser.add_pattern(
        "search_status", r"DONE: (PLAN FOUND|PLAN NOT EXIST|FAIL|CONT)",
        type=str, required=False)
    parser.add_pattern(
        "plan_exit_code", r"(?:plan|planner) exit code: (-?\d+)",
        file="driver.log", type=int, required=False)

    def memory(content, props):
        samples = [
            int(match.group(1))
            for match in re.finditer(
                r"\[[0-9]+(?:\.[0-9]+)?s ([0-9]+)MB\]", content)
        ]
        if samples:
            props["cpddl_peak_memory_mb"] = max(samples)

    def classify(_driver_content, props):
        status = props.get("search_status")
        cost_present = "solution_cost" in props
        exit_code = props.get("plan_exit_code")
        log_version = props.get("cpddl_log_version")
        exit_ok = exit_code == 0
        version_ok = log_version == EXPECTED_CPDDL_BINARY_VERSION
        has_done = status in {
            "PLAN FOUND", "PLAN NOT EXIST", "FAIL", "CONT"}

        props.update(
            coverage=0,
            proved_unsolvable=0,
            cpddl_log_version_match=int(version_ok),
            native_done_marker=int(has_done),
        )
        errors = []
        if exit_code is None:
            errors.append("plan exit code missing from driver.log")
        elif not exit_ok:
            errors.append("planner exited with code {}".format(exit_code))
        if log_version is None:
            errors.append("CPDDL Version line missing from run.log")
        elif not version_ok:
            errors.append(
                "CPDDL log version {!r} does not match expected {!r}".format(
                    log_version, EXPECTED_CPDDL_BINARY_VERSION))
        # Cost, clean termination, and the exact artifact version are the
        # authoritative solve signals shared by CPDDL's fw and bi paths.  The
        # bi path additionally emits DONE; fw currently does not.  Treat a
        # missing marker as diagnostic data, but reject a contradictory one.
        marker_consistent_with_plan = status in {None, "PLAN FOUND"}
        if (cost_present and exit_ok and version_ok
                and marker_consistent_with_plan):
            props.update(coverage=1, outcome="solved")
        elif (status == "PLAN NOT EXIST" and not cost_present
              and exit_ok and version_ok):
            props.update(
                proved_unsolvable=1, outcome="proved_unsolvable")
        elif status == "PLAN FOUND" or cost_present:
            props["outcome"] = "invalid_solved_evidence"
            if cost_present and status not in {None, "PLAN FOUND"}:
                errors.append(
                    "parsed plan cost conflicts with DONE: {}".format(status))
            if not cost_present:
                errors.append("DONE: PLAN FOUND without parsed plan cost")
        elif status == "FAIL":
            props["outcome"] = "search_failed"
            errors.append("CPDDL reported DONE: FAIL")
        elif status == "CONT":
            props["outcome"] = "search_failed"
            errors.append("CPDDL reported DONE: CONT")
        else:
            props["outcome"] = "censored_or_error"
            if not has_done:
                errors.append("native CPDDL DONE status missing from run.log")

        if errors:
            props["parser_error"] = "; ".join(errors)
            for error in errors:
                props.add_unexplained_error(error)

    parser.add_function(memory, file="run.log")
    # Patterns from all files are evaluated before functions.  Every built run
    # has static-properties, so this also classifies missing run/driver logs as
    # coverage 0 with explicit unexplained errors.
    parser.add_function(classify, file="static-properties")
    return parser


REPORT_ATTRIBUTES = [
    "coverage", "solution_cost", "total_time", "outcome",
    "proved_unsolvable", "search_status", "plan_exit_code",
    "cpddl_log_version", "cpddl_log_version_match", "native_done_marker",
    "cpddl_peak_memory_mb", "manifest", "manifest_sha256",
    "source_manifest_sha256", "task_sources_sha256",
    "cpddl_vendored_upstream_commit", "cpddl_tree_anchor_revision",
    "cpddl_tracked_tree_oid", "cpddl_tree_manifest_sha256",
    "cpddl_build_config_sha256", "cpddl_generated_config_sha256",
    "cpddl_binary_version", "cpddl_binary_sha256",
    "domain_sha256", "problem_sha256", "search_direction",
    "fw_potential_objective", "bw_potential_objective",
    "readme_recommended", "uses_fdr_tnfm", "planner_time_limit",
    "planner_memory_limit", "scheduler_array_task_throttle",
    "repetitions", "parser_error",
    "unexplained_errors",
]


def add_steps(exp):
    exp.add_parser(get_parser())
    exp.add_step("build", exp.build)
    exp.add_step("start", exp.start_runs)
    exp.add_step("parse", exp.parse)
    exp.add_fetcher(name="fetch")
    algorithm_order = [config["label"] for config in CONFIGS]
    exp.add_report(
        AbsoluteReport(
            attributes=REPORT_ATTRIBUTES,
            filter_manifest="pilot50",
            filter_algorithm=algorithm_order),
        name="report-pilot", outfile="report-pilot.html")
    exp.add_report(
        AbsoluteReport(
            attributes=REPORT_ATTRIBUTES,
            filter_manifest="cap-v2",
            filter_algorithm=algorithm_order),
        name="report-cap-v2", outfile="report-cap-v2.html")
    exp.add_report(
        AbsoluteReport(
            attributes=REPORT_ATTRIBUTES,
            filter_manifest="finalist-v1",
            filter_algorithm=algorithm_order),
        name="report-finalist-v1", outfile="report-finalist-v1.html")


def create_experiment(manifests=None, binary=None):
    exp = Experiment(environment=C.get_environment())
    if manifests is None:
        add_steps(exp)
        return exp
    if binary is None:
        raise ValueError("binary attestation required when constructing runs")

    exp.add_resource(
        "cpddl_binary", str(CPDDL), dest="resources/pddl-symba")
    run_count = sum(len(tasks) for _, _, _, _, tasks in manifests) * len(CONFIGS)
    if run_count != 1404:
        raise RuntimeError("expected 1404 runs, got {}".format(run_count))
    for (manifest, digest, task_sources_sha256,
         source_manifest_sha256, tasks) in manifests:
        for domain, problem, domain_file, problem_file in tasks:
            domain_sha256 = file_digest(domain_file)
            problem_sha256 = file_digest(problem_file)
            for config in CONFIGS:
                resource_command = command(
                    config, "{cpddl_binary}",
                    "{domain_pddl}", "{problem_pddl}")
                run = exp.add_run()
                run.add_resource(
                    "domain_pddl", str(domain_file), dest="domain.pddl")
                run.add_resource(
                    "problem_pddl", str(problem_file), dest="problem.pddl")
                run.add_command(
                    "plan", resource_command, time_limit=TIME_LIMIT,
                    memory_limit=MEMORY_LIMIT)
                run.set_property("algorithm", config["label"])
                run.set_property("domain", domain)
                run.set_property("problem", problem)
                run.set_property(
                    "id", [config["label"], manifest, domain, problem])
                run.set_property("manifest", manifest)
                run.set_property("manifest_sha256", digest)
                run.set_property(
                    "source_manifest_sha256", source_manifest_sha256)
                run.set_property("task_sources_sha256", task_sources_sha256)
                run.set_property(
                    "cpddl_vendored_upstream_commit",
                    CPDDL_VENDORED_UPSTREAM_COMMIT)
                run.set_property(
                    "cpddl_tree_anchor_revision",
                    CPDDL_TREE_ANCHOR_REVISION)
                run.set_property("cpddl_tracked_tree_oid", binary["tree_oid"])
                run.set_property(
                    "cpddl_tree_manifest_sha256",
                    binary["tree_manifest_sha256"])
                run.set_property(
                    "cpddl_build_config_sha256",
                    binary["build_config_sha256"])
                run.set_property(
                    "cpddl_generated_config_sha256",
                    binary["generated_config_sha256"])
                run.set_property("cpddl_binary_version", binary["version"])
                run.set_property("cpddl_binary_sha256", binary["sha256"])
                run.set_property("domain_sha256", domain_sha256)
                run.set_property("problem_sha256", problem_sha256)
                run.set_property("cpddl_binary_resource", "resources/pddl-symba")
                run.set_property("domain_resource", "domain.pddl")
                run.set_property("problem_resource", "problem.pddl")
                run.set_property("planner_time_limit", TIME_LIMIT)
                run.set_property("planner_memory_limit", MEMORY_LIMIT)
                run.set_property(
                    "scheduler_array_task_throttle",
                    None if C.LOCAL else C.ARRAY_TASK_THROTTLE)
                run.set_property("repetitions", 1)
                run.set_property(
                    "search_direction", config["direction"])
                run.set_property(
                    "fw_potential_objective", config["fw_objective"])
                run.set_property(
                    "bw_potential_objective", config["bw_objective"])
                run.set_property(
                    "readme_recommended", config["readme_recommended"])
                run.set_property("uses_fdr_tnfm", True)
                run.set_property("component_options", resource_command)

    add_steps(exp)
    return exp


def needs_source_inputs(lab_args):
    """Return whether this invocation must construct the 1404 run objects.

    Parse, fetch, and report operate exclusively on the built experiment and
    evaluation directories.  Avoid re-reading a mutable planner executable or
    benchmark checkout for those stages.
    """
    if "--all" in lab_args:
        return True
    selected = {arg for arg in lab_args if not arg.startswith("-")}
    return bool(
        selected & {"build", "start"}
        or C.lab_step_numbers(lab_args) & {1, 2})


def main():
    parser = argparse.ArgumentParser(
        description="CPDDL GHSETA frozen-manifest baseline")
    parser.add_argument(
        "--validate-only", action="store_true",
        help="validate and print the matrix without invoking Lab")
    args, lab_args = parser.parse_known_args()
    if args.validate_only:
        manifests = validate_manifests()
        binary = validate_cpddl()
        print("CPDDL vendored upstream commit (record): {}".format(
            CPDDL_VENDORED_UPSTREAM_COMMIT))
        print("CPDDL tracked tree anchor: {}".format(
            CPDDL_TREE_ANCHOR_REVISION))
        print("CPDDL tracked tree object: {}".format(binary["tree_oid"]))
        print("CPDDL tree-manifest SHA-256: {}".format(
            binary["tree_manifest_sha256"]))
        print("CPDDL Makefile.config SHA-256: {}".format(
            binary["build_config_sha256"]))
        print("CPDDL generated config.h SHA-256: {}".format(
            binary["generated_config_sha256"]))
        print("CPDDL binary version: {}".format(binary["version"]))
        print("CPDDL binary SHA-256: {}".format(binary["sha256"]))
        for name, digest, source_digest, source_manifest, tasks in manifests:
            print("{}: {} tasks, name SHA-256 {}, source SHA-256 {}".format(
                name, len(tasks), digest, source_digest))
            print("{}: suite cost manifest SHA-256 {}".format(
                name, source_manifest))
        for config in CONFIGS:
            print("{}: {}".format(
                config["label"],
                " ".join(command(
                    config, "{cpddl_binary}",
                    "{domain_pddl}", "{problem_pddl}"))))
        print("matrix: 234 tasks x 6 configurations = 1404 runs")
        print("reports: pilot50, cap-v2, finalist-v1 (no pooled report)")
        return
    C.reject_unsafe_combined_steps(lab_args)
    sys.argv = [sys.argv[0], *lab_args]
    if needs_source_inputs(lab_args):
        manifests = validate_manifests()
        binary = validate_cpddl()
        exp = create_experiment(manifests, binary)
    else:
        exp = create_experiment()
    exp.run_steps()


if __name__ == "__main__":
    main()
