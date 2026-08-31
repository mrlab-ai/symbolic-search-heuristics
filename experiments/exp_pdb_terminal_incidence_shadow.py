#!/usr/bin/env python3
"""Run the frozen 460 x 5 terminal-incidence shadow study on Arrhenius."""

from __future__ import annotations

from pathlib import Path

import exp_pdb_profile_certificate_holdout as Base
import jj_cached_revision as JJ
import pdb_terminal_incidence_shadow_protocol as P


RUNNER_SOURCE_FILES = (
    "exp_pdb_profile_certificate_holdout.py",
    "exp_pdb_terminal_incidence_shadow.py",
    "pdb_terminal_incidence_shadow_protocol.py",
    "pdb_terminal_incidence_shadow_protocol.md",
    "pdb_terminal_incidence_shadow_cost_attestation.json",
    "audit_pdb_terminal_incidence_sources.py",
    "generate_suite_cost_manifest.py",
    "suite_cost_manifest.py",
    "suite_wbh.py",
    "suite_wbh_operator_costs.json",
    "suite_wbh_operator_costs.json.sha256",
    "pdb_terminal_incidence_source_scan.slurm",
    "artifacts/pdb-terminal-incidence-shadow/source-audit-launch-receipt-v1.json",
    "artifacts/pdb-terminal-incidence-shadow/source-audit-execution-receipt-v1.json",
    "analyze_pdb_terminal_incidence_shadow.py",
    "audit_pdb_terminal_incidence_shadow.py",
    "recover_pdb_terminal_incidence_shadow.py",
    "pdb_fixed_pattern_parser.py",
    "pdb_profile_comparison_parser.py",
    "pdb_profile_comparison_protocol.py",
    "pdb_profile_certificate_holdout_protocol.py",
    "pdb_profile_certificate_holdout_protocol.md",
    "pdb_profile_semantic_union_protocol.py",
    "pdb_profile_semantic_union_protocol.md",
    "analyze_pdb_cap_grid_posthoc_review.py",
    "wbh_parser.py",
    "validate_wbh_log.py",
    "jj_cached_revision.py",
    "requirements-pdb-terminal-incidence-shadow.txt",
)


def configure() -> None:
    """Install the shadow-study constants into the shared audited runner."""
    Base.P = P
    Base.PLANNER_REVISION = P.PLANNER_REVISION
    Base.PLANNER_BINARY_SHA256 = P.PLANNER_BINARY_SHA256
    Base.PREPROCESS_BINARY_SHA256 = P.PREPROCESS_BINARY_SHA256
    Base.EXPERIMENT_PATH = Base.SCRIPT_DIR / "data" / Path(__file__).stem
    Base.REVISION_CACHE = Base.SCRIPT_DIR / "data" / "revision-cache"
    Base.BENCHMARKS = Path(
        "/nobackup/proj/disk/dfsplan/personal/jendrik/"
        "downward-benchmarks-wbh"
    ).resolve()
    Base.COHORT_ARCHIVE = Base.BENCHMARKS
    Base.ACCOUNT = P.ACCOUNT
    Base.RUNS_PER_ARRAY_TASK = 3
    Base.EXPECTED_ARRAY_TASKS = 767
    Base.SCHEDULER_TIME_LIMIT = "00:20:00"
    Base.LAUNCH_RECEIPT = (
        Base.SCRIPT_DIR
        / "artifacts"
        / "pdb-terminal-incidence-shadow"
        / "launch-receipt-v1.json"
    )
    Base.LAUNCH_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/"
        "pdb-terminal-incidence-shadow-launch/v1"
    )
    Base.EXPECTED_JOB_NAME = "exp_pdb_terminal_incidence_shadow-02-start"
    Base.PARTITION_REQUIREMENT_LABEL = "terminal-incidence shadow study"
    Base.EXTRA_PARSER_MODULES = ("pdb_fixed_pattern_parser",)
    Base.SOURCE_PROTOCOL = P.PROTOCOL
    Base.RUNNER_SOURCE_FILES = RUNNER_SOURCE_FILES
    Base.VALIDATE_MATCHED_BUDGET_PROVENANCE = False
    Base.MATERIALIZE_PDDL_INPUTS = True
    Base.ENVIRONMENT_REQUIREMENTS_FILE = (
        Base.SCRIPT_DIR / "requirements-pdb-terminal-incidence-shadow.txt"
    )
    Base.BENCHMARK_SOURCE_VALIDATOR = lambda cohort: (
        P.validate_benchmark_sources(cohort, Base.BENCHMARKS)
    )
    Base.EXTRA_RUN_PROPERTIES = {
        "benchmark_revision": P.BENCHMARK_REVISION,
        "planner_cache_name": P.PLANNER_CACHE_NAME,
        "translator_source_sha256": P.TRANSLATOR_SOURCE_SHA256,
        "cost_attestation_sha256": P.COST_ATTESTATION_SHA256,
        "source_audit_launch_receipt_sha256": (
            P.SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256
        ),
        "source_audit_execution_receipt_sha256": (
            P.SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256
        ),
        "cohort_seed": P.COHORT_SEED,
        "cohort_family_count": P.COHORT_FAMILIES,
        "cohort_directory_family_sha256": P.DIRECTORY_FAMILY_JSON_SHA256,
        "analysis_horizon": P.HORIZON,
        "primary_labels": list(P.PRIMARY_LABELS),
        "intervention_label": P.INTERVENTION_LABEL,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
    }
    Base.EXTRA_RECEIPT_PROPERTIES = {
        "benchmark_revision": P.BENCHMARK_REVISION,
        "planner_cache_name": P.PLANNER_CACHE_NAME,
        "translator_source_sha256": P.TRANSLATOR_SOURCE_SHA256,
        "cost_attestation_sha256": P.COST_ATTESTATION_SHA256,
        "cost_attestation_records_sha256": (
            P.COST_ATTESTATION_RECORDS_SHA256
        ),
        "source_audit_job_id": P.SOURCE_AUDIT_JOB_ID,
        "source_audit_launch_receipt_sha256": (
            P.SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256
        ),
        "source_audit_execution_receipt_sha256": (
            P.SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256
        ),
        "source_audit_slurm_sha256": P.SOURCE_AUDIT_SLURM_SHA256,
        "cohort_seed": P.COHORT_SEED,
        "cohort_task_name_sha256": P.TASK_NAME_SHA256,
        "cohort_source_path_sha256": P.SOURCE_PATH_SHA256,
        "cohort_problem_hash_sha256": P.PROBLEM_HASH_SHA256,
        "cohort_content_pair_sha256": P.CONTENT_PAIR_SHA256,
        "cohort_directory_sequence_sha256": P.DIRECTORY_SEQUENCE_SHA256,
        "cohort_directory_family_sha256": P.DIRECTORY_FAMILY_JSON_SHA256,
        "cohort_family_count": P.COHORT_FAMILIES,
        "analysis_horizon": P.HORIZON,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
    }
    import audit_pdb_terminal_incidence_shadow as Audit

    Base.PRE_PARSE_VALIDATOR = Audit.validate_before_parse
    Base.POST_PARSE_SEALER = Audit.seal_parse
    Base.PRE_FETCH_VALIDATOR = Audit.validate_before_fetch
    Base.POST_FETCH_SEALER = Audit.seal_fetch


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
