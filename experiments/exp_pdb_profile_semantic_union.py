#!/usr/bin/env python3
"""Run the frozen 275 x 16 semantic-union follow-up on Arrhenius."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import jj_cached_revision as JJ
import pdb_profile_semantic_union_protocol as P


class LaunchError(RuntimeError):
    pass


PLANNER_REVISION = "f106393ec53e2ef9a24e1e7dcc91d10b1e83db6f"
PLANNER_BINARY_SHA256 = (
    "634584c4dc871a799269254e3f4e232eca8e77c0e84ff3fe0b0cdb67f9d46d9d"
)
PREPROCESS_BINARY_SHA256 = (
    "4fbfba6aab9f96b9766f3714e911cffbc5d1cb59bed82a13484af9e73977c118"
)
EXPERIMENT_PATH = SCRIPT_DIR / "data" / Path(__file__).stem
REVISION_CACHE = Path(
    os.environ.get(
        "DOWNWARD_REVISION_CACHE", str(SCRIPT_DIR / "data" / "revision-cache")
    )
).resolve()
BENCHMARKS = Path(
    os.environ.get(
        "DOWNWARD_BENCHMARKS",
        "/nobackup/proj/disk/dfsplan/personal/jendrik/"
        "downward-benchmarks-wbh",
    )
).resolve()
COHORT_ARCHIVE = Path(
    os.environ.get(
        "WBH_COHORT_ARCHIVE", str(P.Source.COHORT_ARCHIVE_DEFAULT)
    )
).resolve()
MATCH_ARCHIVE = Path(
    os.environ.get(
        "WBH_MATCH_ARCHIVE", str(P.Source.MATCH_ARCHIVE_DEFAULT)
    )
).resolve()
ACCOUNT = os.environ.get("WBH_ACCOUNT", "naiss2025-5-561-cpu")
PARTITION = "fat"
MAX_ARRAY_TASKS = 1000
RUNS_PER_ARRAY_TASK = 5
SCHEDULER_TIME_LIMIT = "00:40:00"
SCHEDULER_MEMORY = "9G"
PIN_RE = re.compile(r"^[0-9a-f]{64}$")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--self-test", action="store_true")
    actions.add_argument("--check", action="store_true")
    actions.add_argument("--cache", action="store_true")
    parser.add_argument("steps", nargs="*")
    args = parser.parse_args(argv)
    if (args.self_test or args.check or args.cache) and args.steps:
        parser.error("read-only/cache actions cannot be combined with Lab steps")
    allowed = ("build", "start", "parse", "fetch")
    if any(step not in allowed for step in args.steps):
        parser.error("steps must be selected by exact name: {}".format(
            ", ".join(allowed)
        ))
    if any(step in args.steps for step in ("build", "start")) and len(
        args.steps
    ) != 1:
        parser.error("build and start must each run in a separate invocation")
    return args


def require_lab_8() -> None:
    try:
        actual = importlib.metadata.version("lab")
    except importlib.metadata.PackageNotFoundError as err:
        raise LaunchError("Downward Lab is not installed") from err
    if actual != P.REQUIRED_LAB_VERSION:
        raise LaunchError(
            "this protocol requires Lab {}; found {}".format(
                P.REQUIRED_LAB_VERSION, actual
            )
        )


def require_pins() -> None:
    if JJ.COMMIT_RE.fullmatch(PLANNER_REVISION) is None:
        raise LaunchError("PLANNER_REVISION is not a full Jujutsu commit")
    for name, value in (
        ("PLANNER_BINARY_SHA256", PLANNER_BINARY_SHA256),
        ("PREPROCESS_BINARY_SHA256", PREPROCESS_BINARY_SHA256),
    ):
        if PIN_RE.fullmatch(value) is None:
            raise LaunchError("{} is not pinned".format(name))


def cached_revision(require_hashes=True):
    cached = JJ.JjCachedFastDownwardRevision(
        REVISION_CACHE,
        REPO,
        PLANNER_REVISION,
        list(P.BUILD_OPTIONS),
    )
    if require_hashes:
        attestation = cached.attest()
        expected = {
            "downward_sha256": PLANNER_BINARY_SHA256,
            "preprocess_sha256": PREPROCESS_BINARY_SHA256,
        }
        if any(attestation.get(key) != value for key, value in expected.items()):
            raise LaunchError("revision cache differs from pinned binary hashes")
    return cached


def _source_records():
    import suite_cost_manifest

    data = suite_cost_manifest.load_manifest()
    return {
        (record["domain"], record["problem"]): record
        for record in data["tasks"]
    }


def validate_benchmark_sources(cohort) -> None:
    if not BENCHMARKS.is_dir():
        raise LaunchError("benchmark root does not exist: {}".format(BENCHMARKS))
    records = _source_records()
    for task in cohort:
        record = records.get((task.domain, task.problem))
        if record is None:
            raise LaunchError("cohort task is absent from the source manifest")
        for path_field, hash_field in (
            ("domain_file", "domain_sha256"),
            ("problem_file", "problem_sha256"),
        ):
            path = BENCHMARKS / record[path_field]
            if P.Source.sha256_file(path) != record[hash_field]:
                raise LaunchError("benchmark source hash changed: {}".format(path))


def make_experiment(cohort, cached):
    from downward.experiment import (
        FastDownwardAlgorithm,
        FastDownwardExperiment,
        FastDownwardRun,
    )
    from lab.environments import SlurmEnvironment

    import pdb_profile_comparison_parser as profile_parser
    import wbh_parser

    class ArrheniusEnvironment(SlurmEnvironment):
        MAX_TASKS = MAX_ARRAY_TASKS

    class JjFastDownwardExperiment(FastDownwardExperiment):
        def add_cached_algorithm(self, name, component_options, driver_options):
            algorithm = FastDownwardAlgorithm(
                name, cached, driver_options, component_options
            )
            if name in self._algorithms:
                raise LaunchError("duplicate algorithm {}".format(name))
            self._algorithms[name] = algorithm

        def _add_runs(self):
            for algorithm in self._algorithms.values():
                for task in self._get_tasks():
                    run = FastDownwardRun(self, algorithm, task)
                    for key, value in {
                        "protocol": P.PROTOCOL,
                        "analysis_protocol": P.ANALYSIS_PROTOCOL,
                        "cohort_role": P.COHORT_ROLE,
                        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
                        "cohort_task_count": P.COHORT_TASKS,
                        "cohort_domain_count": P.COHORT_DOMAINS,
                        "config_count": P.CONFIG_COUNT,
                        "declared_run_count": P.CELL_COUNT,
                        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
                        "protocol_sha256": P.PROTOCOL_SHA256,
                        "source_protocol": P.Source.PROTOCOL,
                        "planner_revision": PLANNER_REVISION,
                        "planner_binary_sha256": PLANNER_BINARY_SHA256,
                        "preprocess_binary_sha256": PREPROCESS_BINARY_SHA256,
                        "planner_preprocess_sha256": PREPROCESS_BINARY_SHA256,
                        "required_lab_version": P.REQUIRED_LAB_VERSION,
                        "planner_time_limit": P.TIME_LIMIT_SECONDS,
                        "planner_memory_limit": P.MEMORY_LIMIT_MIB,
                        "external_validation_requested": False,
                        "slurm_partition": PARTITION,
                        "array_throttle": 0,
                    }.items():
                        run.set_property(key, value)
                    self.add_run(run)

    environment = ArrheniusEnvironment(
        partition=PARTITION,
        qos="normal",
        time_limit_per_task=SCHEDULER_TIME_LIMIT,
        memory_per_cpu=SCHEDULER_MEMORY,
        cpus_per_task=1,
        extra_options="#SBATCH --account={}".format(ACCOUNT),
        randomize_task_order=False,
    )
    experiment = JjFastDownwardExperiment(
        path=EXPERIMENT_PATH,
        environment=environment,
        revision_cache=REVISION_CACHE,
    )
    driver_options = [
        "--overall-time-limit",
        "{}s".format(P.TIME_LIMIT_SECONDS),
        "--overall-memory-limit",
        "{}M".format(P.MEMORY_LIMIT_MIB),
        "--build",
        "release_no_lp",
    ]
    for label, search in P.CONFIGS:
        experiment.add_cached_algorithm(
            label,
            ["--search", search],
            driver_options,
        )
    experiment.add_suite(
        BENCHMARKS,
        ["{}:{}".format(task.domain, task.problem) for task in cohort],
    )
    experiment.add_parser(experiment.EXITCODE_PARSER)
    experiment.add_parser(experiment.TRANSLATOR_PARSER)
    experiment.add_parser(experiment.SINGLE_SEARCH_PARSER)
    experiment.add_parser(experiment.PLANNER_PARSER)
    experiment.add_parser(wbh_parser.get_parser())
    experiment.add_parser(profile_parser.get_parser())
    experiment.add_step("build", experiment.build)
    experiment.add_step("start", experiment.start_runs)
    experiment.add_step("parse", experiment.parse)
    experiment.add_fetcher(name="fetch")
    return experiment


def self_test() -> None:
    P.validate_protocol_without_archive()
    expected_grouping = (
        P.CELL_COUNT + MAX_ARRAY_TASKS - 1
    ) // MAX_ARRAY_TASKS
    if RUNS_PER_ARRAY_TASK != expected_grouping:
        raise LaunchError("Slurm run grouping changed")
    if PARTITION != "fat":
        raise LaunchError("semantic-union follow-up must use the fat partition")
    print(
        "protocol OK: {} tasks x {} configs = {} cells; "
        "{} runs/array task; unthrottled {} partition".format(
            P.COHORT_TASKS,
            P.CONFIG_COUNT,
            P.CELL_COUNT,
            RUNS_PER_ARRAY_TASK,
            PARTITION,
        )
    )


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    require_lab_8()
    cohort = P.load_cohort(COHORT_ARCHIVE)
    P.Source.validate_matched_budget_provenance(MATCH_ARCHIVE)
    validate_benchmark_sources(cohort)
    if args.check:
        require_pins()
        cached_revision(require_hashes=True)
        print("protocol, cohort, benchmark bytes, and pinned cache verified")
        return 0
    if args.cache:
        cached = cached_revision(require_hashes=False)
        cached.cache()
        print(json.dumps(cached.attest(), sort_keys=True, indent=2))
        return 0
    if not args.steps:
        raise LaunchError(
            "select one of --self-test, --check, --cache, or a Lab step"
        )
    require_pins()
    cached = cached_revision(require_hashes=True)
    experiment = make_experiment(cohort, cached)
    sys.argv = [sys.argv[0], *args.steps]
    experiment.run_steps()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LaunchError, P.ProtocolError, P.Source.ProtocolError, JJ.JjCacheError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
