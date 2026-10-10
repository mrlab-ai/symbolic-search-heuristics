#!/usr/bin/env python3
"""Run the frozen 1,052 x 6 harm-generality study on Arrhenius."""

from __future__ import annotations

import collections
import os
from pathlib import Path

import exp_pdb_profile_certificate_holdout as Base
import jj_cached_revision as JJ
import pdb_profile_harm_generality_protocol as P


RUNNER_SOURCE_FILES = (
    "exp_pdb_profile_certificate_holdout.py",
    "exp_pdb_profile_harm_generality.py",
    "pdb_profile_harm_generality_protocol.py",
    "pdb_profile_harm_generality_protocol.md",
    "pdb_profile_harm_generality_cohort.txt",
    "analyze_pdb_profile_harm_generality.py",
    "jj_cached_revision.py",
    "pdb_profile_comparison_parser.py",
    "wbh_parser.py",
    "validate_wbh_log.py",
    "requirements.txt",
)
REVISION_CACHE = Path(
    "/nobackup/proj/disk/dfsplan/personal/jendrik/"
    "symk-harm-generality-revision-cache"
)
ACCOUNT = "naiss2026-3-660-cpu"


def _validate_cplex() -> None:
    if os.environ.get("cplex_DIR") != str(P.CPLEX_DIR):
        raise Base.LaunchError("cplex_DIR must name the pinned CPLEX install")
    if Base._sha256_file(P.CPLEX_LIBRARY) != P.CPLEX_LIBRARY_SHA256:
        raise Base.LaunchError("CPLEX runtime library changed")


SourcedTask = collections.namedtuple(
    "SourcedTask",
    "domain problem domain_file problem_file domain_sha256 problem_sha256",
)


class _Protocol:
    """The frozen protocol module, with source provenance on cohort tasks.

    Lab links domain.pddl and problem.pddl into every run directory; the
    shared runner replaces those links with regular files only when each
    task names its source files and their hashes.
    """

    def __getattr__(self, name):
        return getattr(P, name)

    @staticmethod
    def load_cohort(archive=None):
        records = Base._source_records()
        tasks = []
        for task in P.load_cohort(archive):
            record = records.get((task.domain, task.problem))
            if record is None:
                raise Base.LaunchError("cohort task lacks a source record")
            tasks.append(SourcedTask(
                task.domain,
                task.problem,
                record["domain_file"],
                record["problem_file"],
                record["domain_sha256"],
                record["problem_sha256"],
            ))
        return tuple(tasks)


def configure() -> None:
    Base.P = _Protocol()
    Base.PLANNER_REVISION = P.PLANNER_REVISION
    Base.PLANNER_BINARY_SHA256 = P.PLANNER_BINARY_SHA256
    Base.PREPROCESS_BINARY_SHA256 = P.PREPROCESS_BINARY_SHA256
    Base.REVISION_CACHE = REVISION_CACHE
    Base.ACCOUNT = ACCOUNT
    Base.BUILD_NAME = "release"
    Base.EXPERIMENT_PATH = Base.SCRIPT_DIR / "data" / Path(__file__).stem
    Base.RUNS_PER_ARRAY_TASK = 7
    Base.EXPECTED_ARRAY_TASKS = 902
    Base.SCHEDULER_TIME_LIMIT = "00:45:00"
    Base.LAUNCH_RECEIPT = (
        Base.SCRIPT_DIR
        / "artifacts"
        / "pdb-profile-harm-generality"
        / "launch-receipt-v1.json"
    )
    Base.LAUNCH_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/pdb-profile-harm-generality-launch/v1"
    )
    Base.EXPECTED_JOB_NAME = "exp_pdb_profile_harm_generality-02-start"
    Base.PARTITION_REQUIREMENT_LABEL = "harm generality"
    Base.EXTRA_PARSER_MODULES = ()
    Base.SOURCE_PROTOCOL = P.Holdout.PROTOCOL
    Base.RUNNER_SOURCE_FILES = RUNNER_SOURCE_FILES
    Base.VALIDATE_MATCHED_BUDGET_PROVENANCE = False
    Base.MATERIALIZE_PDDL_INPUTS = True
    Base.ENVIRONMENT_REQUIREMENTS_FILE = Base.SCRIPT_DIR / "requirements.txt"
    Base.EXTRA_RECEIPT_PROPERTIES = {
        "build_name": "release",
        "cplex_library": str(P.CPLEX_LIBRARY),
        "cplex_library_sha256": P.CPLEX_LIBRARY_SHA256,
    }
    base_validator = Base.validate_benchmark_sources

    def validate_sources(cohort):
        _validate_cplex()
        base_validator(cohort)

    Base.BENCHMARK_SOURCE_VALIDATOR = validate_sources


def main(argv=None):
    configure()
    return Base.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        Base.LaunchError,
        P.ProtocolError,
        P.Source.ProtocolError,
        JJ.JjCacheError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
