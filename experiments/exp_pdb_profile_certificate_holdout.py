#!/usr/bin/env python3
"""Run the frozen 1,052 x 17 certificate holdout on Arrhenius."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib
import importlib.metadata
import json
import os
import platform
import re
import stat
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import jj_cached_revision as JJ
import pdb_profile_certificate_holdout_protocol as P


class LaunchError(RuntimeError):
    pass


PLANNER_REVISION = P.PLANNER_REVISION
PLANNER_BINARY_SHA256 = P.PLANNER_BINARY_SHA256
PREPROCESS_BINARY_SHA256 = P.PREPROCESS_BINARY_SHA256
EXPERIMENT_PATH = SCRIPT_DIR / "data" / Path(__file__).stem
REVISION_CACHE = Path(
    os.environ.get(
        "DOWNWARD_REVISION_CACHE",
        "/nobackup/proj/disk/dfsplan/personal/jendrik/"
        "symk-cap-grid-results/experiments/data/revision-cache",
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
RUNS_PER_ARRAY_TASK = 18
EXPECTED_ARRAY_TASKS = 994
SCHEDULER_TIME_LIMIT = "02:15:00"
SCHEDULER_MEMORY = "9G"
PIN_RE = re.compile(r"^[0-9a-f]{64}$")
LAUNCH_RECEIPT = (
    SCRIPT_DIR
    / "artifacts"
    / "pdb-profile-certificate-holdout"
    / "launch-receipt-v1.json"
)
LAUNCH_RECEIPT_SCHEMA = (
    "symbolic-search-heuristics/pdb-profile-certificate-holdout-launch/v1"
)
EXPECTED_JOB_NAME = "exp_pdb_profile_certificate_holdout-02-start"
PARTITION_REQUIREMENT_LABEL = "certificate holdout"
RUNNER_SOURCE_FILES = (
    "exp_pdb_profile_certificate_holdout.py",
    "pdb_profile_certificate_holdout_protocol.py",
    "pdb_profile_certificate_holdout_protocol.md",
    "analyze_pdb_profile_certificate_holdout.py",
    "pdb_profile_comparison_parser.py",
    "wbh_parser.py",
    "validate_wbh_log.py",
)
EXTRA_PARSER_MODULES = ()
SOURCE_PROTOCOL = P.Source.PROTOCOL
VALIDATE_MATCHED_BUDGET_PROVENANCE = True
BENCHMARK_SOURCE_VALIDATOR = None
EXTRA_RUN_PROPERTIES = {}
EXTRA_RECEIPT_PROPERTIES = {}
MATERIALIZE_PDDL_INPUTS = False
ENVIRONMENT_REQUIREMENTS_FILE = None
PRE_PARSE_VALIDATOR = None
POST_PARSE_SEALER = None
PRE_FETCH_VALIDATOR = None
POST_FETCH_SEALER = None
RUN_ORDER_BUILDER = None
# Driver build name; it must match the single entry of P.BUILD_OPTIONS.
BUILD_NAME = "release_no_lp"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _environment_attestation(requirements_path: Path) -> dict:
    requirements_path = Path(requirements_path)
    try:
        lines = requirements_path.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as err:
        raise LaunchError("cannot read frozen environment requirements") from err
    requirements = {}
    for line in lines:
        if not line or line.startswith("#") or line.count("==") != 1:
            raise LaunchError("environment requirement is not an exact pin")
        name, version = line.split("==")
        if not name or not version or name in requirements:
            raise LaunchError("environment requirements are malformed")
        requirements[name] = version
    if not requirements:
        raise LaunchError("environment requirements are empty")
    manifest = []
    versions = {}
    for name, expected_version in sorted(requirements.items()):
        try:
            distribution = importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError as err:
            raise LaunchError(
                "required Python distribution is absent: {}".format(name)
            ) from err
        if distribution.version != expected_version:
            raise LaunchError(
                "Python distribution version changed: {}".format(name)
            )
        versions[name] = distribution.version
        files = distribution.files
        if not files:
            raise LaunchError(
                "Python distribution has no installed-file record: {}".format(
                    name
                )
            )
        for relative in sorted(files, key=str):
            path = Path(distribution.locate_file(relative)).resolve()
            if not path.is_file():
                raise LaunchError(
                    "installed Python distribution file is absent: {}".format(
                        relative
                    )
                )
            manifest.append({
                "distribution": name,
                "path": str(relative),
                "sha256": _sha256_file(path),
            })
    executable = Path(sys.executable).resolve()
    raw = json.dumps(
        manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    return {
        "python_executable_sha256": _sha256_file(executable),
        "python_environment_sha256": hashlib.sha256(raw).hexdigest(),
        "python_distributions": versions,
        "python_requirements_sha256": _sha256_file(requirements_path),
    }


def _run_input_tree_digest() -> tuple[str, int, int]:
    """Hash every generated run wrapper and immutable property record."""
    digest = hashlib.sha256()
    expected_directories = []
    expected_files = []
    for run_id in range(1, P.CELL_COUNT + 1):
        lower = ((run_id - 1) // 100) * 100 + 1
        upper = lower + 99
        directory = Path(
            "runs-{:05d}-{:05d}/{:05d}".format(lower, upper, run_id)
        )
        expected_directories.append(directory)
        names = ["run", "static-properties"]
        if MATERIALIZE_PDDL_INPUTS:
            names.extend(("domain.pddl", "problem.pddl"))
        run_dir = EXPERIMENT_PATH / directory
        if run_dir.is_symlink() or not run_dir.is_dir():
            raise LaunchError("generated run directory is absent or invalid")
        try:
            entries = list(run_dir.iterdir())
        except OSError as err:
            raise LaunchError("cannot inspect generated run directory") from err
        if {entry.name for entry in entries} != set(names):
            raise LaunchError("generated run directory has unexpected entries")
        expected_files.extend(directory / name for name in names)
    actual_directories = {
        path.relative_to(EXPERIMENT_PATH)
        for path in EXPERIMENT_PATH.glob("runs-*/[0-9]*")
    }
    if actual_directories != set(expected_directories):
        raise LaunchError("generated run matrix has wrong directories")
    for relative in expected_files:
        path = EXPERIMENT_PATH / relative
        try:
            info = path.lstat()
        except OSError as err:
            raise LaunchError("cannot inspect generated run input") from err
        if path.is_symlink() or not stat.S_ISREG(info.st_mode):
            raise LaunchError("generated run input is not a regular file")
        encoded = relative.as_posix().encode("ascii")
        digest.update(encoded + b"\0" + bytes.fromhex(_sha256_file(path)))
    return digest.hexdigest(), P.CELL_COUNT, P.CELL_COUNT


def _materialize_run_inputs() -> None:
    """Replace Lab's external PDDL symlinks with verified regular files."""
    for run_id in range(1, P.CELL_COUNT + 1):
        lower = ((run_id - 1) // 100) * 100 + 1
        upper = lower + 99
        directory = (
            EXPERIMENT_PATH
            / "runs-{:05d}-{:05d}".format(lower, upper)
            / "{:05d}".format(run_id)
        )
        try:
            properties = json.loads(
                (directory / "static-properties").read_text(
                    encoding="utf-8"
                )
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
            raise LaunchError("cannot read generated static properties") from err
        for filename, hash_field in (
            ("domain.pddl", "domain_source_sha256"),
            ("problem.pddl", "problem_source_sha256"),
        ):
            path = directory / filename
            expected_hash = properties.get(hash_field)
            if PIN_RE.fullmatch(expected_hash or "") is None:
                raise LaunchError("generated task lacks a source hash")
            try:
                info = path.lstat()
                resolved = path.resolve(strict=True)
                resolved.relative_to(BENCHMARKS)
                payload = path.read_bytes()
            except (OSError, ValueError) as err:
                raise LaunchError(
                    "generated PDDL link escapes the benchmark root"
                ) from err
            if not path.is_symlink() or not stat.S_ISLNK(info.st_mode):
                raise LaunchError("fresh Lab build did not create a PDDL link")
            if hashlib.sha256(payload).hexdigest() != expected_hash:
                raise LaunchError("generated PDDL source hash changed")
            temporary = path.with_name(
                ".{}.materialize-{}".format(filename, os.getpid())
            )
            try:
                with temporary.open("xb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.chmod(0o444)
                os.replace(temporary, path)
            except OSError as err:
                try:
                    temporary.unlink()
                except OSError:
                    pass
                raise LaunchError("cannot materialize generated PDDL input") from err
            if path.is_symlink() or _sha256_file(path) != expected_hash:
                raise LaunchError("materialized PDDL input failed attestation")


def _launch_intent_path() -> Path:
    return LAUNCH_RECEIPT.with_name("launch-intent-v1.json")


def _build_receipt_path() -> Path:
    return LAUNCH_RECEIPT.with_name("build-receipt-v1.json")


def _json_bytes(record: dict) -> bytes:
    try:
        return json.dumps(
            record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii") + b"\n"
    except (TypeError, ValueError) as err:
        raise LaunchError("launch provenance is not canonical JSON") from err


def _current_build_inputs(cached) -> dict:
    tree_hash, run_count, property_count = _run_input_tree_digest()
    source_files = {name: SCRIPT_DIR / name for name in RUNNER_SOURCE_FILES}
    missing_sources = [
        name for name, path in source_files.items() if not path.is_file()
    ]
    if missing_sources:
        raise LaunchError(
            "launch source files are absent: {}".format(
                ", ".join(sorted(missing_sources))
            )
        )
    attestation = cached.attest()
    expected_attestation = {
        "revision": PLANNER_REVISION,
        "build_options": list(P.BUILD_OPTIONS),
        "downward_sha256": PLANNER_BINARY_SHA256,
        "preprocess_sha256": PREPROCESS_BINARY_SHA256,
    }
    tree_pin = getattr(P, "PLANNER_TREE_MANIFEST_SHA256", None)
    if tree_pin is not None:
        expected_attestation["tree_manifest_sha256"] = tree_pin
    if any(
        attestation.get(key) != value
        for key, value in expected_attestation.items()
    ):
        raise LaunchError("revision-cache attestation changed before launch")
    experiment_code = EXPERIMENT_PATH / cached.get_relative_exp_path()
    experiment_attestation = cached.attest_path(experiment_code)
    if experiment_attestation != attestation:
        raise LaunchError("experiment code copy differs from revision cache")
    if ENVIRONMENT_REQUIREMENTS_FILE is None:
        raise LaunchError("frozen environment requirements are not configured")
    environment = _environment_attestation(ENVIRONMENT_REQUIREMENTS_FILE)
    return {
        "cells": P.CELL_COUNT,
        "planner_revision": PLANNER_REVISION,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "lab_version": importlib.metadata.version("lab"),
        "python_version": platform.python_version(),
        "python_executable": str(Path(sys.executable).resolve()),
        **environment,
        "revision_cache_attestation": attestation,
        "experiment_code_path": experiment_code.relative_to(
            EXPERIMENT_PATH
        ).as_posix(),
        "experiment_code_attestation": experiment_attestation,
        "static_experiment_properties_sha256": _sha256_file(
            EXPERIMENT_PATH / "static-experiment-properties"
        ),
        "generated_run_input_tree_sha256": tree_hash,
        "generated_run_files": run_count,
        "generated_static_property_files": property_count,
        "materialized_pddl_inputs": MATERIALIZE_PDDL_INPUTS,
        "generated_pddl_input_files": (
            2 * P.CELL_COUNT if MATERIALIZE_PDDL_INPUTS else 0
        ),
        "source_file_sha256": {
            name: _sha256_file(path) for name, path in source_files.items()
        },
    }


def _write_build_receipt(cached) -> None:
    path = _build_receipt_path()
    if path.exists():
        raise LaunchError("build receipt already exists; refusing to overwrite")
    if LAUNCH_RECEIPT.exists() or _launch_intent_path().exists():
        raise LaunchError("cannot seal a build after launch preparation")
    receipt = {
        "schema": "{}/build".format(LAUNCH_RECEIPT_SCHEMA),
        "recorded_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        **_current_build_inputs(cached),
    }
    raw = _json_bytes(receipt)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise LaunchError(
            "build receipt appeared concurrently; refusing to overwrite"
        ) from err


def _validate_build_receipt(cached) -> tuple[str, dict]:
    path = _build_receipt_path()
    try:
        raw = path.read_bytes()
        receipt = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise LaunchError("cannot load the frozen build receipt") from err
    current = _current_build_inputs(cached)
    if (
        not isinstance(receipt, dict)
        or receipt.get("schema") != "{}/build".format(
            LAUNCH_RECEIPT_SCHEMA
        )
        or not isinstance(receipt.get("recorded_utc"), str)
        or set(receipt) != {"schema", "recorded_utc", *current}
        or any(receipt.get(key) != value for key, value in current.items())
    ):
        raise LaunchError("generated experiment differs from its build seal")
    return hashlib.sha256(raw).hexdigest(), current


def _prepare_launch_materials(job_file: Path, cached) -> dict:
    """Validate and freeze every launch input before invoking ``sbatch``."""
    if LAUNCH_RECEIPT.exists():
        raise LaunchError("launch receipt already exists; refusing to overwrite")
    intent_path = _launch_intent_path()
    if intent_path.exists():
        raise LaunchError(
            "launch intent already exists; inspect Slurm before retrying"
        )
    job_file = Path(job_file)
    if not job_file.is_file() or job_file.name != EXPECTED_JOB_NAME:
        raise LaunchError("generated Slurm job file is absent or misnamed")
    build_receipt_sha256, build_inputs = _validate_build_receipt(cached)
    receipt_without_job_id = {
        "schema": LAUNCH_RECEIPT_SCHEMA,
        "recorded_utc": datetime.datetime.now(
            datetime.timezone.utc
        ).isoformat(timespec="seconds"),
        "job_name": job_file.name,
        "partition": PARTITION,
        "qos": "normal",
        "account": ACCOUNT,
        "slurm_array": "1-{}".format(EXPECTED_ARRAY_TASKS),
        "array_throttle": 0,
        "array_tasks": EXPECTED_ARRAY_TASKS,
        "runs_per_array_task": RUNS_PER_ARRAY_TASK,
        "cells": P.CELL_COUNT,
        "time_limit": SCHEDULER_TIME_LIMIT,
        "memory_per_cpu": SCHEDULER_MEMORY,
        "cpus_per_task": 1,
        "lab_version": build_inputs["lab_version"],
        "python_version": build_inputs["python_version"],
        "python_executable": build_inputs["python_executable"],
        "python_executable_sha256": build_inputs[
            "python_executable_sha256"
        ],
        "python_environment_sha256": build_inputs[
            "python_environment_sha256"
        ],
        "python_distributions": build_inputs["python_distributions"],
        "python_requirements_sha256": build_inputs[
            "python_requirements_sha256"
        ],
        "planner_revision": PLANNER_REVISION,
        "revision_cache_attestation": build_inputs[
            "revision_cache_attestation"
        ],
        "experiment_code_path": build_inputs["experiment_code_path"],
        "experiment_code_attestation": build_inputs[
            "experiment_code_attestation"
        ],
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "option_matrix_sha256": P.OPTION_MATRIX_SHA256,
        "protocol_sha256": P.PROTOCOL_SHA256,
        "job_file_sha256": _sha256_file(job_file),
        "build_receipt_sha256": build_receipt_sha256,
        "static_experiment_properties_sha256": build_inputs[
            "static_experiment_properties_sha256"
        ],
        "generated_run_input_tree_sha256": build_inputs[
            "generated_run_input_tree_sha256"
        ],
        "generated_run_files": build_inputs["generated_run_files"],
        "generated_static_property_files": build_inputs[
            "generated_static_property_files"
        ],
        "materialized_pddl_inputs": build_inputs[
            "materialized_pddl_inputs"
        ],
        "generated_pddl_input_files": build_inputs[
            "generated_pddl_input_files"
        ],
        "source_file_sha256": build_inputs["source_file_sha256"],
    }
    reserved = set(receipt_without_job_id) | {
        "job_id",
        "launch_intent_sha256",
    }
    overlap = reserved.intersection(EXTRA_RECEIPT_PROPERTIES)
    if overlap:
        raise LaunchError(
            "extra receipt properties override fixed fields: {}".format(
                ", ".join(sorted(overlap))
            )
        )
    receipt_without_job_id.update(EXTRA_RECEIPT_PROPERTIES)
    # Serialize before creating the intent so malformed extra provenance
    # cannot leave behind a launch marker.
    _json_bytes({**receipt_without_job_id, "job_id": "0"})
    LAUNCH_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
    intent = {
        "schema": "{}/intent".format(LAUNCH_RECEIPT_SCHEMA),
        "prepared_receipt_without_job_id": receipt_without_job_id,
    }
    raw = _json_bytes(intent)
    try:
        with intent_path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise LaunchError(
            "launch intent appeared concurrently; refusing to submit"
        ) from err
    materials = dict(receipt_without_job_id)
    materials["launch_intent_sha256"] = hashlib.sha256(raw).hexdigest()
    _json_bytes({**materials, "job_id": "0"})
    return materials


def _write_launch_receipt(job_id: str, materials: dict) -> None:
    """Record a successful submission without re-reading launch inputs."""
    if LAUNCH_RECEIPT.exists():
        raise LaunchError("launch receipt already exists; refusing to overwrite")
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchError("Slurm returned an invalid job id")
    if "job_id" in materials:
        raise LaunchError("preflight materials unexpectedly contain a job id")
    receipt = dict(materials)
    receipt["job_id"] = job_id
    raw = _json_bytes(receipt)
    try:
        with LAUNCH_RECEIPT.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise LaunchError(
            "launch receipt appeared concurrently; refusing to overwrite"
        ) from err


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
    allowed = ("build", "start", "parse", "fetch", "report")
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
    required_python = getattr(P, "REQUIRED_PYTHON_VERSION", None)
    if required_python is not None and platform.python_version() != required_python:
        raise LaunchError(
            "this protocol requires Python {}; found {}".format(
                required_python, platform.python_version()
            )
        )


def require_pins() -> None:
    if JJ.COMMIT_RE.fullmatch(PLANNER_REVISION) is None:
        raise LaunchError("PLANNER_REVISION is not a full Jujutsu commit")
    pins = [
        ("PLANNER_BINARY_SHA256", PLANNER_BINARY_SHA256),
        ("PREPROCESS_BINARY_SHA256", PREPROCESS_BINARY_SHA256),
    ]
    if hasattr(P, "PLANNER_TREE_MANIFEST_SHA256"):
        pins.append((
            "PLANNER_TREE_MANIFEST_SHA256",
            P.PLANNER_TREE_MANIFEST_SHA256,
        ))
    for name, value in pins:
        if PIN_RE.fullmatch(value) is None:
            raise LaunchError("{} is not pinned".format(name))


def cached_revision(require_hashes=True):
    cached = JJ.JjCachedFastDownwardRevision(
        REVISION_CACHE,
        REPO,
        PLANNER_REVISION,
        list(P.BUILD_OPTIONS),
    )
    expected_cache_name = getattr(P, "PLANNER_CACHE_NAME", None)
    if expected_cache_name is not None and cached.name != expected_cache_name:
        raise LaunchError("revision-cache identity differs from its pin")
    if require_hashes:
        attestation = cached.attest()
        expected = {
            "downward_sha256": PLANNER_BINARY_SHA256,
            "preprocess_sha256": PREPROCESS_BINARY_SHA256,
        }
        tree_hash = getattr(P, "PLANNER_TREE_MANIFEST_SHA256", None)
        if tree_hash is not None:
            expected["tree_manifest_sha256"] = tree_hash
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
                raise LaunchError(
                    "benchmark source hash changed: {}".format(path)
                )


BENCHMARK_SOURCE_VALIDATOR = validate_benchmark_sources


def make_experiment(cohort, cached):
    from downward.experiment import (
        FastDownwardAlgorithm,
        FastDownwardExperiment,
        FastDownwardRun,
    )
    from downward.reports.absolute import AbsoluteReport
    from lab.environments import SlurmEnvironment, is_run_step

    import pdb_profile_comparison_parser as profile_parser
    import wbh_parser

    cohort_sources = {
        (task.domain, task.problem): task for task in cohort
    }
    if len(cohort_sources) != len(cohort):
        raise LaunchError("cohort contains duplicate task identities")

    class ArrheniusEnvironment(SlurmEnvironment):
        MAX_TASKS = MAX_ARRAY_TASKS

        def _get_job_header(self, step, is_last):
            header = super()._get_job_header(step, is_last)
            if is_run_step(step):
                num_tasks = self._get_num_tasks(step)
                if num_tasks != EXPECTED_ARRAY_TASKS:
                    raise LaunchError("Slurm array task count changed")
                required = {
                    "#SBATCH --partition=fat",
                    "#SBATCH --qos=normal",
                    "#SBATCH --time={}".format(SCHEDULER_TIME_LIMIT),
                    "#SBATCH --mem-per-cpu={}".format(SCHEDULER_MEMORY),
                    "#SBATCH --cpus-per-task=1",
                    "#SBATCH --array=1-{}".format(EXPECTED_ARRAY_TASKS),
                    "#SBATCH --account={}".format(ACCOUNT),
                }
                lines = set(header.splitlines())
                missing = sorted(required.difference(lines))
                if missing:
                    raise LaunchError(
                        "Slurm header changed: missing {}".format(
                            ", ".join(missing)
                        )
                    )
                array_lines = [
                    line for line in header.splitlines()
                    if line.startswith("#SBATCH --array=")
                ]
                if array_lines != [
                    "#SBATCH --array=1-{}".format(EXPECTED_ARRAY_TASKS)
                ] or "%" in array_lines[0]:
                    raise LaunchError(
                        "Slurm array unexpectedly has a throttle"
                    )
                exact_directives = {
                    "#SBATCH --partition=": "#SBATCH --partition=fat",
                    "#SBATCH --qos=": "#SBATCH --qos=normal",
                    "#SBATCH --time=": "#SBATCH --time={}".format(
                        SCHEDULER_TIME_LIMIT
                    ),
                    "#SBATCH --mem-per-cpu=": "#SBATCH --mem-per-cpu={}".format(
                        SCHEDULER_MEMORY
                    ),
                    "#SBATCH --cpus-per-task=": "#SBATCH --cpus-per-task=1",
                    "#SBATCH --account=": "#SBATCH --account={}".format(
                        ACCOUNT
                    ),
                }
                for prefix, expected in exact_directives.items():
                    matches = [
                        line for line in header.splitlines()
                        if line.startswith(prefix)
                    ]
                    if matches != [expected]:
                        raise LaunchError(
                            "Slurm header has conflicting {} directives".format(
                                prefix.removeprefix("#SBATCH --").rstrip("=")
                            )
                        )
            return header

        def _submit_job(self, job_name, job_file, job_dir, dependency=None):
            # Lab 8.0 passes the job name, file, and directory.
            job_file = Path(job_file)
            if job_name != EXPECTED_JOB_NAME or job_file.name != EXPECTED_JOB_NAME:
                raise LaunchError("unexpected launch job name")
            materials = _prepare_launch_materials(job_file, cached)
            job_id = super()._submit_job(
                job_name, str(job_file), job_dir, dependency=dependency
            )
            _write_launch_receipt(job_id, materials)
            return job_id

    class JjFastDownwardExperiment(FastDownwardExperiment):
        def add_cached_algorithm(self, name, component_options, driver_options):
            algorithm = FastDownwardAlgorithm(
                name, cached, driver_options, component_options
            )
            if name in self._algorithms:
                raise LaunchError("duplicate algorithm {}".format(name))
            self._algorithms[name] = algorithm

        def _add_runs(self):
            tasks = tuple(self._get_tasks())
            if RUN_ORDER_BUILDER is None:
                cells = (
                    (algorithm, task)
                    for algorithm in self._algorithms.values()
                    for task in tasks
                )
            else:
                cells = RUN_ORDER_BUILDER(self._algorithms, tasks)
            for algorithm, task in cells:
                run = FastDownwardRun(self, algorithm, task)
                properties = {
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
                    "source_protocol": SOURCE_PROTOCOL,
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
                }
                if MATERIALIZE_PDDL_INPUTS:
                    source = cohort_sources.get(
                        (task.domain, task.problem)
                    )
                    required = (
                        "domain_file",
                        "problem_file",
                        "domain_sha256",
                        "problem_sha256",
                    )
                    if source is None or any(
                        not hasattr(source, field) for field in required
                    ):
                        raise LaunchError(
                            "Lab task lacks frozen source provenance"
                        )
                    properties.update({
                        "domain_source_path": source.domain_file,
                        "problem_source_path": source.problem_file,
                        "domain_source_sha256": source.domain_sha256,
                        "problem_source_sha256": source.problem_sha256,
                    })
                overlap = set(properties).intersection(EXTRA_RUN_PROPERTIES)
                if overlap:
                    raise LaunchError(
                        "extra run properties override fixed fields: {}"
                        .format(", ".join(sorted(overlap)))
                    )
                properties.update(EXTRA_RUN_PROPERTIES)
                for key, value in properties.items():
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
        BUILD_NAME,
    ]
    if list(P.BUILD_OPTIONS) != [BUILD_NAME]:
        raise LaunchError("driver build differs from the cached build")
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
    experiment.add_parser(wbh_parser.get_parser())
    experiment.add_parser(profile_parser.get_parser())
    for module_name in EXTRA_PARSER_MODULES:
        module = importlib.import_module(module_name)
        experiment.add_parser(module.get_parser())
    experiment.add_parser(experiment.PLANNER_PARSER)

    def build_and_seal():
        if (
            _build_receipt_path().exists()
            or _launch_intent_path().exists()
            or LAUNCH_RECEIPT.exists()
        ):
            raise LaunchError(
                "build or launch provenance already exists; refusing rebuild"
            )
        experiment.build()
        if MATERIALIZE_PDDL_INPUTS:
            _materialize_run_inputs()
        _write_build_receipt(cached)

    experiment.add_step("build", build_and_seal)
    experiment.add_step("start", experiment.start_runs)
    def parse_and_seal():
        if PRE_PARSE_VALIDATOR is not None:
            PRE_PARSE_VALIDATOR()
        experiment.parse()
        if POST_PARSE_SEALER is not None:
            POST_PARSE_SEALER()

    experiment.add_step("parse", parse_and_seal)
    if PRE_FETCH_VALIDATOR is None and POST_FETCH_SEALER is None:
        experiment.add_fetcher(name="fetch")
    else:
        from lab.fetcher import Fetcher

        def fetch_and_seal():
            if PRE_FETCH_VALIDATOR is not None:
                PRE_FETCH_VALIDATOR()
            Fetcher()(
                experiment.path,
                experiment.eval_dir,
                merge=False,
            )
            if POST_FETCH_SEALER is not None:
                POST_FETCH_SEALER()

        experiment.add_step("fetch", fetch_and_seal)
    experiment.add_report(
        AbsoluteReport(attributes=(
            "error",
            "coverage",
            "planner_exit_code",
            "unexplained_errors",
            "construction_completed",
            "solution_cost",
            "wbh_profile_prefix_certified",
            "wbh_profile_complete",
            "wbh_profile_completed_layer_profiles",
            "pdb_fixed_pattern_certified",
        )),
        name="report",
    )
    return experiment


def prepare_start_job() -> Path:
    """Render the single Slurm start job without submitting it.

    Lab's Slurm environment normally combines rendering and submission in
    ``run_steps``.  The confirmation campaigns deliberately submit the exact
    validated bytes themselves, so they need a separate, outcome-free render
    step after the experiment directory has been built and sealed.
    """
    P.validate_protocol_without_archive()
    require_lab_8()
    cohort = P.load_cohort(COHORT_ARCHIVE)
    if VALIDATE_MATCHED_BUDGET_PROVENANCE:
        P.Source.validate_matched_budget_provenance(MATCH_ARCHIVE)
    if BENCHMARK_SOURCE_VALIDATOR is None:
        raise LaunchError("benchmark source validator is not configured")
    BENCHMARK_SOURCE_VALIDATOR(cohort)
    require_pins()
    cached = cached_revision(require_hashes=True)
    _validate_build_receipt(cached)

    grid_dir = Path(str(EXPERIMENT_PATH) + "-grid-steps")
    eval_dir = Path(str(EXPERIMENT_PATH) + "-eval")
    if any(path.exists() or path.is_symlink() for path in (
        grid_dir, eval_dir, _launch_intent_path(), LAUNCH_RECEIPT,
    )):
        raise LaunchError(
            "job-render or launch artifacts already exist; refusing overwrite"
        )
    if not Path(EXPERIMENT_PATH).is_dir():
        raise LaunchError("sealed experiment directory is absent")

    experiment = make_experiment(cohort, cached)
    # FastDownwardExperiment.build(write_to_disk=False) materializes the
    # in-memory runs needed by Lab's job renderer without changing the sealed
    # experiment directory.
    experiment.build(write_to_disk=False)
    from lab.steps import get_step

    step = get_step(experiment.steps, "start")
    environment = experiment.environment
    environment.job_dir = grid_dir
    job_name = environment._get_job_name(step)
    if job_name != EXPECTED_JOB_NAME:
        raise LaunchError("rendered start-job name changed")
    content = environment._get_job(step, is_last=True)
    if not isinstance(content, str) or not content:
        raise LaunchError("rendered start-job content is invalid")

    try:
        grid_dir.mkdir(mode=0o700)
        job_file = grid_dir / job_name
        with job_file.open("x", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except (FileExistsError, OSError) as err:
        raise LaunchError("cannot create the exclusive rendered start job") from err
    return job_file


def self_test() -> None:
    P.validate_protocol_without_archive()
    expected_grouping = (
        P.CELL_COUNT + MAX_ARRAY_TASKS - 1
    ) // MAX_ARRAY_TASKS
    expected_tasks = (
        P.CELL_COUNT + RUNS_PER_ARRAY_TASK - 1
    ) // RUNS_PER_ARRAY_TASK
    if RUNS_PER_ARRAY_TASK != expected_grouping:
        raise LaunchError("Slurm run grouping changed")
    if EXPECTED_ARRAY_TASKS != expected_tasks:
        raise LaunchError("Slurm array task count changed")
    if not (
        (EXPECTED_ARRAY_TASKS - 1) * RUNS_PER_ARRAY_TASK
        < P.CELL_COUNT
        <= EXPECTED_ARRAY_TASKS * RUNS_PER_ARRAY_TASK
    ):
        raise LaunchError("frozen array coverage changed")
    if PARTITION != "fat":
        raise LaunchError(
            "{} must use the fat partition".format(
                PARTITION_REQUIREMENT_LABEL
            )
        )
    print(
        "protocol OK: {} tasks x {} configs = {} cells; "
        "{} runs/array task; {} unthrottled {} array tasks".format(
            P.COHORT_TASKS,
            P.CONFIG_COUNT,
            P.CELL_COUNT,
            RUNS_PER_ARRAY_TASK,
            EXPECTED_ARRAY_TASKS,
            PARTITION,
        )
    )


def main(argv=None):
    args = parse_args(argv)
    P.validate_protocol_without_archive()
    if args.self_test:
        self_test()
        return 0
    require_lab_8()
    cohort = P.load_cohort(COHORT_ARCHIVE)
    if VALIDATE_MATCHED_BUDGET_PROVENANCE:
        P.Source.validate_matched_budget_provenance(MATCH_ARCHIVE)
    if BENCHMARK_SOURCE_VALIDATOR is None:
        raise LaunchError("benchmark source validator is not configured")
    BENCHMARK_SOURCE_VALIDATOR(cohort)
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
    if args.steps == ["start"]:
        grid_dir = Path(str(EXPERIMENT_PATH) + "-grid-steps")
        if (
            LAUNCH_RECEIPT.exists()
            or _launch_intent_path().exists()
            or grid_dir.exists()
            or Path(str(EXPERIMENT_PATH) + "-eval").exists()
        ):
            raise LaunchError(
                "start artifacts already exist; refusing before Lab can delete them"
            )
        _validate_build_receipt(cached)
    experiment = make_experiment(cohort, cached)
    sys.argv = [sys.argv[0], *args.steps]
    experiment.run_steps()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        LaunchError,
        P.ProtocolError,
        P.Source.ProtocolError,
        JJ.JjCacheError,
    ) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
