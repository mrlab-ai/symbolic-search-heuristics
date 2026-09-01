#!/usr/bin/env python3
"""Build and launch the frozen 650 x 4 Confirmation A study."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from pathlib import Path

import exp_pdb_profile_certificate_holdout as Base
import jj_cached_revision as JJ
import pdb_terminal_incidence_confirmation_a_protocol as P


class ConfirmationLaunchError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
EXPERIMENT_PATH = SCRIPT_DIR / "data" / "exp_pdb_terminal_incidence_confirmation_a"
GRID_DIR = Path(str(EXPERIMENT_PATH) + "-grid-steps")
REVISION_CACHE = SCRIPT_DIR / "data" / "revision-cache"
BENCHMARKS = Path(
    "/nobackup/proj/disk/dfsplan/personal/jendrik/downward-benchmarks-wbh"
).resolve()
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation" /
    "confirmation-a"
)
BUILD_RECEIPT = ARTIFACT_DIR / "build-receipt-v1.json"
LAUNCH_INTENT = ARTIFACT_DIR / "launch-intent-v1.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "launch-receipt-v1.json"
LAUNCH_RECEIPT_PIN = ARTIFACT_DIR / "launch-receipt-v1.sha256"
LAUNCH_SCHEMA = (
    "symbolic-search-heuristics/"
    "pdb-terminal-incidence-confirmation-a-launch/v1"
)
EXPECTED_JOB_NAME = "exp_pdb_terminal_incidence_confirmation_a-02-start"
JOB_FILE = GRID_DIR / EXPECTED_JOB_NAME
SUBMISSION_TOKEN_RE = re.compile(r"^[0-9a-f]{24}$")
JOURNAL_FIELDS = "JobID%64,JobName%128,Comment%128"


def _exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise ConfirmationLaunchError("{} already exists".format(label)) from err
    return hashlib.sha256(raw).hexdigest()


def _exclusive_json(path: Path, value, label: str) -> str:
    return _exclusive_bytes(path, P.canonical_json_line(value), label)


def _load_json(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        info = path.lstat()
        raw = path.read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ConfirmationLaunchError("cannot load {}".format(label)) from err
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or not isinstance(value, dict)
        or raw != P.canonical_json_line(value)
    ):
        raise ConfirmationLaunchError("{} is not canonical".format(label))
    return raw, value


def _source_names() -> tuple[str, ...]:
    freeze, materials = P._load_freeze(P.FREEZE_PATH)
    del freeze
    names = []
    for relative in P.EXPERIMENT_SOURCE_FILES:
        path = Path(relative)
        if path.parts[:1] != ("experiments",):
            raise ConfirmationLaunchError("executed source path changed")
        names.append(Path(*path.parts[1:]).as_posix())
    names.append(P.FREEZE_PATH.relative_to(SCRIPT_DIR).as_posix())
    for path in (
        materials.attestation_path,
        materials.execution_receipt_path,
        materials.launch_receipt_path,
    ):
        try:
            names.append(path.relative_to(SCRIPT_DIR).as_posix())
        except ValueError as err:
            raise ConfirmationLaunchError(
                "source audit artifact is outside experiments"
            ) from err
    if len(names) != len(set(names)):
        raise ConfirmationLaunchError("executed source list has duplicates")
    return tuple(names)


def configure() -> None:
    P.validate_protocol_without_sources()
    freeze, materials = P._load_freeze(P.FREEZE_PATH)
    Base.P = P
    Base.PLANNER_REVISION = P.PLANNER_REVISION
    Base.PLANNER_BINARY_SHA256 = P.PLANNER_BINARY_SHA256
    Base.PREPROCESS_BINARY_SHA256 = P.PREPROCESS_BINARY_SHA256
    Base.EXPERIMENT_PATH = EXPERIMENT_PATH
    Base.REVISION_CACHE = REVISION_CACHE
    Base.BENCHMARKS = BENCHMARKS
    Base.COHORT_ARCHIVE = BENCHMARKS
    Base.ACCOUNT = P.ACCOUNT
    Base.PARTITION = "fat"
    Base.RUNS_PER_ARRAY_TASK = P.RUNS_PER_ARRAY_TASK
    Base.EXPECTED_ARRAY_TASKS = P.EXPECTED_ARRAY_TASKS
    Base.SCHEDULER_TIME_LIMIT = P.SCHEDULER_TIME_LIMIT
    Base.SCHEDULER_MEMORY = P.SCHEDULER_MEMORY
    Base.LAUNCH_RECEIPT = LAUNCH_RECEIPT
    Base.LAUNCH_RECEIPT_SCHEMA = LAUNCH_SCHEMA
    Base.EXPECTED_JOB_NAME = EXPECTED_JOB_NAME
    Base.PARTITION_REQUIREMENT_LABEL = "terminal-incidence Confirmation A"
    Base.EXTRA_PARSER_MODULES = ("pdb_fixed_pattern_parser",)
    Base.SOURCE_PROTOCOL = P.PROTOCOL
    Base.RUNNER_SOURCE_FILES = _source_names()
    Base.VALIDATE_MATCHED_BUDGET_PROVENANCE = False
    Base.MATERIALIZE_PDDL_INPUTS = True
    Base.ENVIRONMENT_REQUIREMENTS_FILE = (
        SCRIPT_DIR / "requirements-pdb-terminal-incidence-shadow.txt"
    )
    Base.BENCHMARK_SOURCE_VALIDATOR = lambda cohort: (
        P.validate_benchmark_sources(cohort, BENCHMARKS)
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
        "source_audit_code_manifest_sha256": (
            P.SOURCE_AUDIT_CODE_MANIFEST_SHA256
        ),
        "source_audit_repository_commit_id": (
            P.SOURCE_AUDIT_REPOSITORY_COMMIT_ID
        ),
        "cohort_seed": P.COHORT_SEED,
        "cohort_family_count": P.COHORT_FAMILIES,
        "cohort_directory_family_sha256": hashlib.sha256(
            P.canonical_json(P.DIRECTORY_TO_FAMILY)
        ).hexdigest(),
        "analysis_horizon": P.HORIZON,
        "primary_labels": list(P.PRIMARY_LABELS),
        "intervention_label": P.INTERVENTION_LABEL,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
        "confirmation_a_freeze_sha256": P.sha256_file(P.FREEZE_PATH),
        "all_prior_unrepresented_families": list(
            P.ALL_PRIOR_UNREPRESENTED_FAMILIES
        ),
        "shadow_unrepresented_families": list(
            P.SHADOW_UNREPRESENTED_FAMILIES
        ),
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
        "source_audit_code_manifest_sha256": (
            P.SOURCE_AUDIT_CODE_MANIFEST_SHA256
        ),
        "source_audit_repository_commit_id": (
            P.SOURCE_AUDIT_REPOSITORY_COMMIT_ID
        ),
        "source_audit_output_tree_sha256": (
            P.SOURCE_AUDIT_OUTPUT_TREE_SHA256
        ),
        "source_audit_slurm_sha256": P.SOURCE_AUDIT_SLURM_SHA256,
        "source_audit_intent_sha256": P.SOURCE_AUDIT_INTENT_SHA256,
        "confirmation_a_freeze_sha256": P.sha256_file(P.FREEZE_PATH),
        "source_attestation_path": str(materials.attestation_path),
        "source_execution_receipt_path": str(materials.execution_receipt_path),
        "source_launch_receipt_path": str(materials.launch_receipt_path),
        "cohort_seed": P.COHORT_SEED,
        "cohort_task_name_sha256": P.TASK_NAME_SHA256,
        "cohort_family_count": P.COHORT_FAMILIES,
        "analysis_horizon": P.HORIZON,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
        "frozen_source_design": freeze["design"],
    }
    import audit_pdb_terminal_incidence_confirmation_a as Audit

    Base.PRE_PARSE_VALIDATOR = Audit.validate_before_parse
    Base.POST_PARSE_SEALER = Audit.seal_parse
    Base.PRE_FETCH_VALIDATOR = Audit.validate_before_fetch
    Base.POST_FETCH_SEALER = Audit.seal_fetch


def _sanitize_job_file() -> None:
    if JOB_FILE.is_symlink() or not JOB_FILE.is_file():
        raise ConfirmationLaunchError("generated Confirmation A job file is absent")
    try:
        raw = JOB_FILE.read_bytes()
        text = raw.decode("utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise ConfirmationLaunchError("cannot read generated job file") from err
    lines = text.splitlines(keepends=True)
    nice = [line for line in lines if line.startswith("#SBATCH --nice=")]
    if nice == ["#SBATCH --nice=0\n"]:
        lines = [line for line in lines if not line.startswith("#SBATCH --nice=")]
        payload = "".join(lines).encode("utf-8")
        temporary = JOB_FILE.with_name(".{}.no-nice".format(JOB_FILE.name))
        try:
            with temporary.open("xb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.chmod(JOB_FILE.stat().st_mode & 0o777)
            os.replace(temporary, JOB_FILE)
        except OSError as err:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise ConfirmationLaunchError("cannot remove zero nice directive") from err
    elif nice:
        raise ConfirmationLaunchError("generated job requests a nice adjustment")
    _validate_job_file()


def _validate_job_file() -> str:
    if JOB_FILE.is_symlink() or not JOB_FILE.is_file():
        raise ConfirmationLaunchError("Confirmation A job file is not regular")
    try:
        text = JOB_FILE.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as err:
        raise ConfirmationLaunchError("cannot inspect Confirmation A job") from err
    lines = text.splitlines()
    if not lines or lines[0] != "#! /bin/bash -l":
        raise ConfirmationLaunchError("generated job interpreter changed")
    directives = (
        "#SBATCH --job-name={}".format(EXPECTED_JOB_NAME),
        "#SBATCH --output={}".format((GRID_DIR / "slurm.log").resolve()),
        "#SBATCH --error={}".format((GRID_DIR / "slurm.err").resolve()),
        "#SBATCH --open-mode=append",
        "#SBATCH --partition=fat",
        "#SBATCH --qos=normal",
        "#SBATCH --time=01:40:00",
        "#SBATCH --mem-per-cpu=26G",
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --array=1-867",
        "#SBATCH --mail-type=NONE",
        "#SBATCH --mail-user=",
        "#SBATCH --account={}".format(P.ACCOUNT),
    )
    assignments = {
        "NUM_RUNS=": "NUM_RUNS=2600",
        "RUNS_PER_TASK=": "RUNS_PER_TASK=3",
    }
    actual_directives = [
        line for line in lines if line.startswith("#SBATCH")
    ]
    conflicting_directive = sorted(actual_directives) != sorted(directives)
    conflicting_assignment = any(
        [line for line in lines if line.startswith(prefix)] != [expected]
        for prefix, expected in assignments.items()
    )
    if conflicting_directive or conflicting_assignment:
        raise ConfirmationLaunchError("generated job contract changed")

    print_block = "\n".join((
        "function print {",
        "    local msg=${1}",
        '    printf "[Slurm task %05d] %s\\n" "$SLURM_ARRAY_TASK_ID" "$msg"',
        "}",
    ))
    print_run_dir_block = "\n".join((
        "function print_run_dir {",
        "    local run_id=${1}",
        '    let "lower=((run_id - 1) / 100) * 100 + 1"',
        '    let "upper=((run_id + 100 - 1) / 100) * 100"',
        '    printf "runs-%05d-%05d/%05d" $lower $upper $run_id',
        "}",
    ))
    execute_run_block = "\n".join((
        "function execute_run {",
        "    if [[ -f driver.log ]]; then",
        '        echo "The run in $(pwd) has already been started --> skip it"',
        "        return",
        "    fi",
        "",
        "    (",
        '    "{}" run'.format(Path(sys.executable)),
        "    RETCODE=$?",
        "    if [[ $RETCODE != 0 ]]; then",
        '        >&2 echo "The run script finished with exit code $RETCODE"',
        "    fi",
        "    ) > driver.log 2> driver.err",
        "",
        "    # Delete empty driver.err files. driver.log always has content "
        "(for started runs).",
        "    if [[ ! -s driver.err ]]; then",
        "        rm driver.err",
        "    fi",
        "}",
    ))
    if (
        text.count(print_block) != 1
        or text.count(print_run_dir_block) != 1
        or text.count(execute_run_block) != 1
    ):
        raise ConfirmationLaunchError("generated job execution body changed")

    declarations = [
        line for line in lines
        if line.startswith("declare -a SHUFFLED_RUN_IDS=")
    ]
    if len(declarations) != 1:
        raise ConfirmationLaunchError("generated job run mapping is absent")
    match = re.fullmatch(
        r"declare -a SHUFFLED_RUN_IDS=\(([0-9 ]+)\)", declarations[0]
    )
    if match is None:
        raise ConfirmationLaunchError("generated job run mapping is malformed")
    try:
        run_ids = [int(value) for value in match.group(1).split()]
    except ValueError as err:
        raise ConfirmationLaunchError(
            "generated job run mapping is malformed"
        ) from err
    if run_ids != list(range(1, P.CELL_COUNT + 1)):
        raise ConfirmationLaunchError(
            "generated job run mapping is not the frozen identity permutation"
        )
    mapping_block = "\n".join((
        "# Shuffle runs to avoid systematic bias.",
        declarations[0],
        "NUM_RUNS=2600",
        "RUNS_PER_TASK=3",
        "",
        "# Compute which indices belong to the Slurm task.",
        'let "START_INDEX=($SLURM_ARRAY_TASK_ID - 1) * RUNS_PER_TASK"',
        'let "END_INDEX=START_INDEX + RUNS_PER_TASK - 1"',
        "",
        "if [ $END_INDEX -ge $NUM_RUNS ]; then",
        '    let "END_INDEX=$NUM_RUNS - 1"',
        "fi",
        "",
        "# Execute runs.",
        "for index in $(seq $START_INDEX $END_INDEX); do",
        "    run_id=${SHUFFLED_RUN_IDS[$index]}",
        "    run_dir=$(print_run_dir ${run_id})",
        '    (cd "{}/$run_dir" && execute_run ${{run_id}})'.format(
            EXPERIMENT_PATH.resolve()
        ),
        "done",
    ))
    if text.count(mapping_block) != 1:
        raise ConfirmationLaunchError("generated job run-to-cell mapping changed")
    expected_executable_lines = [
        line
        for block in (
            print_block, print_run_dir_block, execute_run_block, mapping_block
        )
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    actual_executable_lines = [
        line for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if actual_executable_lines != expected_executable_lines:
        raise ConfirmationLaunchError(
            "generated job contains an unrecognized executable line"
        )
    return P.sha256_file(JOB_FILE)


def _clean_repository_commit() -> str:
    try:
        if JJ.working_copy_diff_summary(REPO):
            raise ConfirmationLaunchError("launch requires a clean working copy")
        commit = JJ.parent_commit(REPO)
        JJ.require_ancestor(REPO, P.PLANNER_REVISION, commit)
    except JJ.JjCacheError as err:
        raise ConfirmationLaunchError("cannot attest launch commit") from err
    return commit


def _submission_identity(token: str) -> tuple[str, str]:
    if SUBMISSION_TOKEN_RE.fullmatch(token or "") is None:
        raise ConfirmationLaunchError("submission token is invalid")
    return (
        EXPECTED_JOB_NAME,
        "pdb-terminal-incidence-confirmation-a/{}".format(token),
    )


def _validate_recorded_utc(value: str) -> None:
    try:
        recorded = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError) as err:
        raise ConfirmationLaunchError("submission timestamp is invalid") from err
    if (
        recorded.tzinfo is None
        or recorded.utcoffset() != datetime.timedelta(0)
        or recorded.isoformat(timespec="seconds") != value
    ):
        raise ConfirmationLaunchError(
            "submission timestamp is not canonical UTC seconds"
        )


def _submit_command(token: str) -> list[str]:
    job_name, comment = _submission_identity(token)
    return [
        "sbatch", "--parsable", "--export=NONE", "--no-requeue",
        "--job-name={}".format(job_name),
        "--comment={}".format(comment),
        str(JOB_FILE.resolve()),
    ]


def _build_launch_materials(
    *, token: str, recorded_utc: str, repository_commit_id: str | None = None
) -> dict:
    _validate_recorded_utc(recorded_utc)
    P.validate_protocol_without_sources()
    configure()
    if repository_commit_id is None:
        repository_commit_id = _clean_repository_commit()
    elif P.COMMIT_RE.fullmatch(repository_commit_id) is None:
        raise ConfirmationLaunchError("launch repository commit is invalid")
    cached = Base.cached_revision(require_hashes=True)
    build_sha, build_inputs = Base._validate_build_receipt(cached)
    job_sha = _validate_job_file()
    _, build = _load_json(BUILD_RECEIPT, "Confirmation A build receipt")
    if P.sha256_file(BUILD_RECEIPT) != build_sha:
        raise ConfirmationLaunchError("build receipt changed during launch")
    command = _submit_command(token)
    return {
        "schema": LAUNCH_SCHEMA,
        "recorded_utc": recorded_utc,
        "submission_token": token,
        "submission_comment": _submission_identity(token)[1],
        "submit_command": command,
        "job_name": EXPECTED_JOB_NAME,
        "partition": "fat",
        "qos": "normal",
        "account": P.ACCOUNT,
        "slurm_array": "1-867",
        "array_throttle": 0,
        "array_tasks": 867,
        "runs_per_array_task": 3,
        "cells": 2600,
        "time_limit": "01:40:00",
        "memory_per_cpu": "26G",
        "cpus_per_task": 1,
        "nice_adjustment": None,
        "submission_export": "NONE",
        "requeue": False,
        "repository_commit_id": repository_commit_id,
        "job_file_sha256": job_sha,
        "build_receipt_sha256": build_sha,
        **{
            field: build[field]
            for field in (
                "cohort_manifest_sha256", "option_matrix_sha256",
                "protocol_sha256", "lab_version", "python_version",
                "python_executable", "python_executable_sha256",
                "python_environment_sha256", "python_distributions",
                "python_requirements_sha256", "planner_revision",
                "revision_cache_attestation", "experiment_code_path",
                "experiment_code_attestation",
                "static_experiment_properties_sha256",
                "generated_run_input_tree_sha256", "generated_run_files",
                "generated_static_property_files", "materialized_pddl_inputs",
                "generated_pddl_input_files", "source_file_sha256",
            )
        },
        **Base.EXTRA_RECEIPT_PROPERTIES,
    }


def _load_intent_only() -> tuple[bytes, dict, dict]:
    raw, intent = _load_json(LAUNCH_INTENT, "Confirmation A launch intent")
    prepared = intent.get("prepared_receipt_without_job_id")
    if not isinstance(prepared, dict):
        raise ConfirmationLaunchError("launch intent is incomplete")
    expected = _build_launch_materials(
        token=prepared.get("submission_token"),
        recorded_utc=prepared.get("recorded_utc"),
        repository_commit_id=prepared.get("repository_commit_id"),
    )
    if intent != {
        "schema": LAUNCH_SCHEMA + "/intent",
        "prepared_receipt_without_job_id": expected,
    }:
        raise ConfirmationLaunchError("launch intent semantics changed")
    return raw, intent, expected


def _write_launch_receipt(intent_raw: bytes, materials: dict, job_id: str) -> str:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise ConfirmationLaunchError("Slurm returned an invalid job ID")
    value = {
        **materials,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": job_id,
    }
    digest = _exclusive_json(LAUNCH_RECEIPT, value, "launch receipt")
    _exclusive_bytes(
        LAUNCH_RECEIPT_PIN,
        (digest + "\n").encode("ascii"),
        "launch receipt pin",
    )
    return digest


def launch() -> None:
    if any(path.exists() or path.is_symlink() for path in (
        LAUNCH_INTENT, LAUNCH_RECEIPT, LAUNCH_RECEIPT_PIN,
    )):
        raise ConfirmationLaunchError("Confirmation A launch artifacts exist")
    token = secrets.token_hex(12)
    recorded = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )
    materials = _build_launch_materials(token=token, recorded_utc=recorded)
    intent = {
        "schema": LAUNCH_SCHEMA + "/intent",
        "prepared_receipt_without_job_id": materials,
    }
    intent_raw = P.canonical_json_line(intent)
    _exclusive_bytes(LAUNCH_INTENT, intent_raw, "launch intent")
    try:
        output = subprocess.check_output(
            materials["submit_command"], cwd=GRID_DIR, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise ConfirmationLaunchError("sbatch failed after launch intent") from err
    job_id = output.split(";", 1)[0]
    digest = _write_launch_receipt(intent_raw, materials, job_id)
    print(json.dumps({
        "job_id": job_id,
        "launch_receipt_sha256": digest,
        "array_throttle": 0,
    }, sort_keys=True, indent=2))


def _journal_job_ids(materials: dict) -> list[str]:
    try:
        recorded = datetime.datetime.fromisoformat(materials["recorded_utc"])
    except (KeyError, TypeError, ValueError) as err:
        raise ConfirmationLaunchError("submission timestamp is invalid") from err
    if recorded.tzinfo is None:
        raise ConfirmationLaunchError("submission timestamp lacks a timezone")
    command = [
        "sacct", "-X", "-S", recorded.date().isoformat(), "-n", "-P",
        "-o", JOURNAL_FIELDS,
    ]
    try:
        output = subprocess.check_output(command, text=True)
    except (OSError, subprocess.CalledProcessError) as err:
        raise ConfirmationLaunchError("cannot query submission journal") from err
    parents = set()
    expected_name = materials["job_name"]
    expected_comment = materials["submission_comment"]
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 3:
            raise ConfirmationLaunchError("submission journal row changed")
        job_id, name, comment = fields
        if name != expected_name and comment != expected_comment:
            continue
        match = re.fullmatch(r"([0-9]+)(?:_[0-9]+)?", job_id)
        if match is None or name != expected_name or comment != expected_comment:
            raise ConfirmationLaunchError("submission identity collided")
        parents.add(match.group(1))
    if len(parents) > 1:
        raise ConfirmationLaunchError("submission identity is not unique")
    return sorted(parents, key=int)


def recover_launch() -> None:
    if LAUNCH_RECEIPT.exists():
        raw, receipt = _load_json(LAUNCH_RECEIPT, "launch receipt")
        if LAUNCH_RECEIPT_PIN.exists():
            raise ConfirmationLaunchError("launch receipt is already complete")
        intent_raw, _, materials = _load_intent_only()
        expected = {
            **materials,
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": receipt.get("job_id"),
        }
        if receipt != expected or not str(receipt.get("job_id", "")).isdigit():
            raise ConfirmationLaunchError("unsealed launch receipt changed")
        digest = hashlib.sha256(raw).hexdigest()
        _exclusive_bytes(
            LAUNCH_RECEIPT_PIN, (digest + "\n").encode("ascii"),
            "launch receipt pin",
        )
        print(json.dumps({
            "job_id": receipt["job_id"],
            "launch_receipt_pin_recovered": True,
            "launch_receipt_sha256": digest,
        }, sort_keys=True, indent=2))
        return
    if LAUNCH_RECEIPT_PIN.exists():
        raise ConfirmationLaunchError("launch pin exists without a receipt")
    intent_raw, _, materials = _load_intent_only()
    jobs = _journal_job_ids(materials)
    if len(jobs) != 1:
        raise ConfirmationLaunchError(
            "submission journal identifies {} matching jobs".format(len(jobs))
        )
    digest = _write_launch_receipt(intent_raw, materials, jobs[0])
    print(json.dumps({
        "job_id": jobs[0],
        "launch_receipt_reconstructed": True,
        "launch_receipt_sha256": digest,
    }, sort_keys=True, indent=2))


def load_launch_receipt(*, verify_live: bool = True) -> tuple[str, dict]:
    intent_raw, _, materials = _load_intent_only()
    raw, receipt = _load_json(LAUNCH_RECEIPT, "Confirmation A launch receipt")
    try:
        pin_raw = LAUNCH_RECEIPT_PIN.read_bytes()
    except OSError as err:
        raise ConfirmationLaunchError("launch receipt is not pinned") from err
    digest = hashlib.sha256(raw).hexdigest()
    expected = {
        **materials,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": receipt.get("job_id"),
    }
    if (
        receipt != expected
        or not isinstance(receipt.get("job_id"), str)
        or not receipt["job_id"].isdigit()
        or pin_raw != (digest + "\n").encode("ascii")
    ):
        raise ConfirmationLaunchError("launch receipt provenance changed")
    if verify_live:
        _validate_job_file()
    return digest, receipt


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=(
            "design-check", "self-test", "check", "cache", "build",
            "launch", "recover-launch", "parse", "fetch", "report",
        ),
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.command == "design-check":
        P.validate_protocol_design()
        print("Confirmation A outcome-independent design OK")
        return 0
    configure()
    if args.command == "launch":
        launch()
        return 0
    if args.command == "recover-launch":
        recover_launch()
        return 0
    mapping = {
        "self-test": ["--self-test"],
        "check": ["--check"],
        "cache": ["--cache"],
        "build": ["build"],
        "parse": ["parse"],
        "fetch": ["fetch"],
        "report": ["report"],
    }
    result = Base.main(mapping[args.command])
    if args.command == "build":
        _sanitize_job_file()
    return result


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ConfirmationLaunchError,
        Base.LaunchError,
        P.ProtocolError,
        P.Source.ProtocolError,
        JJ.JjCacheError,
    ) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
