#!/usr/bin/env python3
"""Build or launch the 1,327 x 18 cofactor-profile comparison on Arrhenius.

The ambient environment is intentionally rejected: launch with the Python 3.9
environment installed from ``experiments/requirements.txt`` (Lab 8.0).
Source caching uses only a full Jujutsu/Git-backend commit ID and never invokes
Git directly.
"""

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
import pdb_profile_comparison_protocol as P


class LaunchError(RuntimeError):
    pass


# Pin these in a descendant protocol commit after building the source commit.
PLANNER_REVISION = "TO_BE_PINNED"
PLANNER_BINARY_SHA256 = "TO_BE_PINNED"
PREPROCESS_BINARY_SHA256 = "TO_BE_PINNED"

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
    os.environ.get("WBH_COHORT_ARCHIVE", str(P.COHORT_ARCHIVE_DEFAULT))
).resolve()
MATCH_ARCHIVE = Path(
    os.environ.get("WBH_MATCH_ARCHIVE", str(P.MATCH_ARCHIVE_DEFAULT))
).resolve()
ACCOUNT = os.environ.get("WBH_ACCOUNT", "naiss2025-5-561-cpu")
ARRAY_THROTTLE = 5
MAX_ARRAY_TASKS = 1000
RUNS_PER_ARRAY_TASK = 24
SCHEDULER_TIME_LIMIT = "02:30:00"
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
        parser.error("steps must be selected by exact name: {}".format(", ".join(allowed)))
    if any(step in args.steps for step in ("build", "start")) and len(args.steps) != 1:
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
        raise LaunchError("PLANNER_REVISION is not pinned to a full Jujutsu commit")
    for name, value in (
        ("PLANNER_BINARY_SHA256", PLANNER_BINARY_SHA256),
        ("PREPROCESS_BINARY_SHA256", PREPROCESS_BINARY_SHA256),
    ):
        if PIN_RE.fullmatch(value) is None:
            raise LaunchError("{} is not pinned".format(name))


def cached_revision(require_hashes=True):
    if JJ.COMMIT_RE.fullmatch(PLANNER_REVISION) is None:
        raise LaunchError("pin PLANNER_REVISION before creating the cache")
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
            if P.sha256_file(path) != record[hash_field]:
                raise LaunchError("benchmark source hash changed: {}".format(path))


def make_experiment(cohort, cached):
    from downward.experiment import (
        FastDownwardAlgorithm,
        FastDownwardExperiment,
        FastDownwardRun,
    )
    from lab.environments import SlurmEnvironment, is_run_step

    import pdb_profile_comparison_parser as profile_parser
    import wbh_parser

    strata = {(task.domain, task.problem): task.stratum for task in cohort}

    class ArrheniusEnvironment(SlurmEnvironment):
        MAX_TASKS = MAX_ARRAY_TASKS

        def _get_job_header(self, step, is_last):
            header = super()._get_job_header(step, is_last)
            if is_run_step(step):
                expected = "#SBATCH --array=1-{}".format(
                    self._get_num_tasks(step)
                )
                replacement = expected + "%{}".format(ARRAY_THROTTLE)
                if header.count(expected) != 1:
                    raise LaunchError("Lab 8.0 Slurm array header changed")
                header = header.replace(expected, replacement)
            return header

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
                    run.set_property("protocol", P.PROTOCOL)
                    run.set_property("analysis_protocol", P.ANALYSIS_PROTOCOL)
                    run.set_property("cohort_role", P.COHORT_ROLE)
                    run.set_property("cohort_manifest_sha256", P.COHORT_MANIFEST_SHA256)
                    run.set_property("cohort_task_count", P.COHORT_TASKS)
                    run.set_property("config_count", P.CONFIG_COUNT)
                    run.set_property("declared_run_count", P.CELL_COUNT)
                    run.set_property("option_matrix_sha256", P.OPTION_MATRIX_SHA256)
                    run.set_property(
                        "matched_budget_archive_sha256", P.MATCH_ARCHIVE_SHA256
                    )
                    run.set_property("matched_budget_candidates", P.MATCH_CANDIDATES)
                    run.set_property("add_match_role", P.ADD_MATCH_ROLE)
                    run.set_property(
                        "cohort_stratum", strata[(task.domain, task.problem)]
                    )
                    run.set_property("planner_revision", PLANNER_REVISION)
                    run.set_property("planner_binary_sha256", PLANNER_BINARY_SHA256)
                    run.set_property("preprocess_binary_sha256", PREPROCESS_BINARY_SHA256)
                    run.set_property("planner_preprocess_sha256", PREPROCESS_BINARY_SHA256)
                    run.set_property("required_lab_version", P.REQUIRED_LAB_VERSION)
                    run.set_property("planner_time_limit", P.TIME_LIMIT_SECONDS)
                    run.set_property("planner_memory_limit", P.MEMORY_LIMIT_MIB)
                    self.add_run(run)

    environment = ArrheniusEnvironment(
        partition="cpu",
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
        "--validate",
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
    if any(search.count('wbh_log="wbh.jsonl"') != 1 for _, search in P.CONFIGS):
        raise LaunchError("matrix does not emit exactly one schema-v2 stream")
    if RUNS_PER_ARRAY_TASK != (P.CELL_COUNT + MAX_ARRAY_TASKS - 1) // MAX_ARRAY_TASKS:
        raise LaunchError("Slurm run grouping changed")
    print(
        "protocol OK: {} tasks x {} configs = {} cells; {} runs/array task".format(
            P.COHORT_TASKS, P.CONFIG_COUNT, P.CELL_COUNT, RUNS_PER_ARRAY_TASK
        )
    )


def main(argv=None):
    args = parse_args(argv)
    if args.self_test:
        self_test()
        return 0
    require_lab_8()
    cohort = P.load_cohort(COHORT_ARCHIVE)
    P.validate_matched_budget_provenance(MATCH_ARCHIVE)
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
        raise LaunchError("select one of --self-test, --check, --cache, or a Lab step")
    require_pins()
    cached = cached_revision(require_hashes=True)
    experiment = make_experiment(cohort, cached)
    # Lab consumes exact step names from sys.argv; argparse has already
    # rejected prefixes, numeric aliases, and combined build/start invocations.
    sys.argv = [sys.argv[0], *args.steps]
    experiment.run_steps()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LaunchError, P.ProtocolError, JJ.JjCacheError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
