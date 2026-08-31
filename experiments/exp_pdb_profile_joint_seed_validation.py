#!/usr/bin/env python3
"""Run the frozen 1,052 x 4 unseen Gamer-seed validation."""

from __future__ import annotations

from pathlib import Path

import exp_pdb_profile_certificate_holdout as Base
import jj_cached_revision as JJ
import pdb_profile_joint_seed_validation_protocol as P


RUNNER_SOURCE_FILES = (
    "exp_pdb_profile_certificate_holdout.py",
    "exp_pdb_profile_joint_seed_validation.py",
    "pdb_profile_joint_seed_validation_protocol.py",
    "pdb_profile_joint_seed_validation_protocol.md",
    "analyze_pdb_profile_joint_seed_validation.py",
    "pdb_fixed_pattern_parser.py",
    "pdb_profile_comparison_parser.py",
    "wbh_parser.py",
    "validate_wbh_log.py",
)


def configure() -> None:
    Base.P = P
    Base.PLANNER_REVISION = P.PLANNER_REVISION
    Base.PLANNER_BINARY_SHA256 = P.PLANNER_BINARY_SHA256
    Base.PREPROCESS_BINARY_SHA256 = P.PREPROCESS_BINARY_SHA256
    Base.EXPERIMENT_PATH = Base.SCRIPT_DIR / "data" / Path(__file__).stem
    Base.RUNS_PER_ARRAY_TASK = 5
    Base.EXPECTED_ARRAY_TASKS = 842
    Base.SCHEDULER_TIME_LIMIT = "00:30:00"
    Base.LAUNCH_RECEIPT = (
        Base.SCRIPT_DIR
        / "artifacts"
        / "pdb-profile-joint-seed-validation"
        / "launch-receipt-v1.json"
    )
    Base.LAUNCH_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/"
        "pdb-profile-joint-seed-validation-launch/v1"
    )
    Base.EXPECTED_JOB_NAME = (
        "exp_pdb_profile_joint_seed_validation-02-start"
    )
    Base.PARTITION_REQUIREMENT_LABEL = "joint-profile seed validation"
    Base.EXTRA_PARSER_MODULES = ("pdb_fixed_pattern_parser",)
    Base.SOURCE_PROTOCOL = P.Holdout.PROTOCOL
    Base.RUNNER_SOURCE_FILES = RUNNER_SOURCE_FILES


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
