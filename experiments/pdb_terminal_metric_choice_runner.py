#!/usr/bin/env python3
"""Materialize the frozen 300 unthrottled task-major execution triads.

This module produces and validates the complete runner manifest.  Submission
is delegated to the campaign execution coordinator and never to Lab directly.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from types import SimpleNamespace
from pathlib import Path

import pdb_confirmation_run_cell as RunCell
import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_transport as Transport


class RunnerError(RuntimeError):
    pass


RUNNER_SCHEMA = P.FREEZE_SCHEMA + "/runner-manifest"
EXPERIMENT_PATH = P.SCRIPT_DIR / "data" / "pdb_terminal_metric_choice"
GRID_DIR = Path(str(EXPERIMENT_PATH) + "-grid-steps")
EVAL_PROPERTIES = Path(str(EXPERIMENT_PATH) + "-eval") / "properties"
PARTITION = "fat"
QOS = "normal"
BENCHMARKS = Path(
    "/nobackup/proj/disk/dfsplan/personal/jendrik/downward-benchmarks-wbh"
)
REVISION_CACHE = P.SCRIPT_DIR / "data" / "revision-cache"
ARTIFACT_DIR = P.SCRIPT_DIR / "artifacts" / "pdb-terminal-metric-choice"
BUILD_RECEIPT = ARTIFACT_DIR / "build-receipt-v1.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "launch-receipt-v1.json"
LAUNCH_INTENT = ARTIFACT_DIR / "launch-intent-v1.json"
LAUNCH_RECEIPT_PIN = ARTIFACT_DIR / "launch-receipt-v1.sha256"
LAUNCH_SCHEMA = P.FREEZE_SCHEMA + "/launch"
EXECUTION_RECEIPT = ARTIFACT_DIR / "execution-receipt-v1.json"
EXECUTION_RECEIPT_PIN = ARTIFACT_DIR / "execution-receipt-v1.sha256"
PRE_PARSE_RECEIPT = ARTIFACT_DIR / "pre-parse-receipt-v1.json"
POST_PARSE_RECEIPT = ARTIFACT_DIR / "post-parse-receipt-v1.json"
POST_FETCH_RECEIPT = ARTIFACT_DIR / "post-fetch-receipt-v1.json"
EXPECTED_JOB_NAME = "pdb_terminal_metric_choice-02-start"
REQUIREMENTS = P.SCRIPT_DIR / "pdb_terminal_metric_choice_requirements.txt"
_ACTIVE_CELL_MAPPING = {}


def _freeze_sha256(path: Path) -> str:
    return P.sha256_file(
        path, expected_path=P.FREEZE_PATH, label="campaign freeze"
    )


def _run_directory(run_id: int) -> Path:
    lower = ((run_id - 1) // 100) * 100 + 1
    upper = lower + 99
    return EXPERIMENT_PATH / "runs-{:05d}-{:05d}".format(
        lower, upper
    ) / "{:05d}".format(run_id)


def _local_materialize_run_inputs() -> None:
    for run_id in range(1, P.CELL_COUNT + 1):
        directory = _run_directory(run_id)
        properties_path = directory / "static-properties"
        try:
            loaded = CampaignIO.read_regular_exact(
                properties_path, expected=properties_path,
                label="generated static properties",
            )
            properties = json.loads(loaded.raw.decode("utf-8"))
        except (CampaignIO.CampaignIOError, UnicodeDecodeError,
                json.JSONDecodeError) as err:
            raise RunnerError("cannot read generated static properties") from err
        for filename, path_field, hash_field in (
            ("domain.pddl", "domain_source_path", "domain_source_sha256"),
            ("problem.pddl", "problem_source_path", "problem_source_sha256"),
        ):
            relative = properties.get(path_field)
            digest = properties.get(hash_field)
            if not isinstance(relative, str) or P.SHA256_RE.fullmatch(
                digest or ""
            ) is None:
                raise RunnerError("generated task source binding is absent")
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts or (
                relative_path.as_posix() != relative
            ):
                raise RunnerError("generated task source path changed")
            source = BENCHMARKS / relative_path
            destination = directory / filename
            try:
                Transport.materialize_expected_symlink(
                    destination, source, expected_link=destination,
                    expected_source=source, source_root=BENCHMARKS,
                    run_root=EXPERIMENT_PATH, sha256=digest,
                    label="generated {}".format(filename),
                )
            except Transport.TransportError as err:
                raise RunnerError(str(err)) from err


def _local_run_input_tree_digest() -> tuple[str, int, int]:
    relatives = []
    names = {"run", "static-properties", "domain.pddl", "problem.pddl"}
    for run_id in range(1, P.CELL_COUNT + 1):
        directory = _run_directory(run_id)
        try:
            Transport.validate_exact_directory(
                directory, names, expected=directory, root=EXPERIMENT_PATH,
                label="generated run",
            )
        except Transport.TransportError as err:
            raise RunnerError(str(err)) from err
        for name in sorted(names):
            relatives.append(
                (directory / name).relative_to(EXPERIMENT_PATH).as_posix()
            )
    try:
        manifest = Transport.immutable_tree_manifest(
            EXPERIMENT_PATH, sorted(relatives), label="generated run input"
        )
    except Transport.TransportError as err:
        raise RunnerError(str(err)) from err
    return manifest["tree_sha256"], P.CELL_COUNT, P.CELL_COUNT


def _trace_relatives() -> list[str]:
    return sorted(
        (_run_directory(run_id) / P.SELECTOR_TRACE).relative_to(
            EXPERIMENT_PATH
        ).as_posix()
        for run_id in range(1, P.CELL_COUNT + 1)
    )


def _trace_manifest() -> dict:
    try:
        return Transport.immutable_tree_manifest(
            EXPERIMENT_PATH, _trace_relatives(), label="selector trace archive"
        )
    except Transport.TransportError as err:
        raise RunnerError(str(err)) from err


def _run_properties_manifest() -> dict:
    relatives = sorted(
        (_run_directory(run_id) / "properties").relative_to(
            EXPERIMENT_PATH
        ).as_posix()
        for run_id in range(1, P.CELL_COUNT + 1)
    )
    try:
        return Transport.immutable_tree_manifest(
            EXPERIMENT_PATH, relatives, label="parsed run properties"
        )
    except Transport.TransportError as err:
        raise RunnerError(str(err)) from err


def _read_receipt(path: Path, label: str) -> dict:
    try:
        _, receipt = CampaignIO.read_canonical_exact(
            path, expected=path, label=label,
            canonical_json_line=P.canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise RunnerError(str(err)) from err
    return receipt


def _write_receipt(path: Path, value: dict, label: str) -> None:
    try:
        CampaignIO.write_canonical_exclusive(
            path, value, expected=path, root=P.SCRIPT_DIR, label=label,
            canonical_json_line=P.canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise RunnerError(str(err)) from err


def _pre_parse(freeze_sha256: str, base) -> None:
    import pdb_terminal_metric_choice_execution as Execution

    try:
        execution_sha, _ = Execution.load_execution_receipt(
            base, verify_live=True
        )
    except Execution.ExecutionError as err:
        raise RunnerError("campaign execution is not sealed") from err
    current = _trace_manifest()
    value = {
        "schema": RUNNER_SCHEMA + "/pre-parse",
        "freeze_sha256": freeze_sha256,
        "execution_receipt_sha256": execution_sha,
        "trace_manifest": current,
    }
    try:
        receipt = _read_receipt(PRE_PARSE_RECEIPT, "pre-parse receipt")
    except RunnerError:
        _write_receipt(PRE_PARSE_RECEIPT, value, "pre-parse receipt")
    else:
        if receipt != value:
            raise RunnerError("selector traces changed before parsing")


def _post_parse(freeze_sha256: str) -> None:
    pre = _read_receipt(PRE_PARSE_RECEIPT, "pre-parse receipt")
    if (
        set(pre) != {
            "schema", "freeze_sha256", "execution_receipt_sha256",
            "trace_manifest",
        }
        or pre.get("schema") != RUNNER_SCHEMA + "/pre-parse"
        or pre.get("freeze_sha256") != freeze_sha256
        or P.SHA256_RE.fullmatch(pre.get("execution_receipt_sha256", ""))
        is None
        or pre.get("trace_manifest") != _trace_manifest()
    ):
        raise RunnerError("selector traces changed during parsing")
    value = {
        "schema": RUNNER_SCHEMA + "/post-parse",
        "freeze_sha256": freeze_sha256,
        "pre_parse_receipt_sha256": P.sha256_file(
            PRE_PARSE_RECEIPT, expected_path=PRE_PARSE_RECEIPT,
            label="pre-parse receipt",
        ),
        "execution_receipt_sha256": pre["execution_receipt_sha256"],
        "trace_manifest": pre["trace_manifest"],
        "run_properties_manifest": _run_properties_manifest(),
    }
    _write_receipt(POST_PARSE_RECEIPT, value, "post-parse receipt")


def _pre_fetch(freeze_sha256: str, base) -> None:
    import pdb_terminal_metric_choice_execution as Execution

    post = _read_receipt(POST_PARSE_RECEIPT, "post-parse receipt")
    try:
        execution_sha, _ = Execution.load_execution_receipt(
            base, verify_live=True
        )
    except Execution.ExecutionError as err:
        raise RunnerError("campaign execution is not sealed") from err
    if (
        set(post) != {
            "schema", "freeze_sha256", "pre_parse_receipt_sha256",
            "execution_receipt_sha256", "trace_manifest",
            "run_properties_manifest",
        }
        or post.get("schema") != RUNNER_SCHEMA + "/post-parse"
        or post.get("freeze_sha256") != freeze_sha256
        or post.get("pre_parse_receipt_sha256") != P.sha256_file(
            PRE_PARSE_RECEIPT, expected_path=PRE_PARSE_RECEIPT,
            label="pre-parse receipt",
        )
        or post.get("execution_receipt_sha256") != execution_sha
        or post.get("trace_manifest") != _trace_manifest()
    ):
        raise RunnerError("parsed campaign inputs changed before fetch")
    if post.get("run_properties_manifest") != _run_properties_manifest():
        raise RunnerError("parsed run properties changed before fetch")


def _post_fetch(freeze_sha256: str, base) -> None:
    _pre_fetch(freeze_sha256, base)
    post = _read_receipt(POST_PARSE_RECEIPT, "post-parse receipt")
    try:
        properties = CampaignIO.read_regular_exact(
            EVAL_PROPERTIES, expected=EVAL_PROPERTIES,
            label="fetched campaign properties",
        )
    except CampaignIO.CampaignIOError as err:
        raise RunnerError(str(err)) from err
    value = {
        "schema": RUNNER_SCHEMA + "/post-fetch",
        "freeze_sha256": freeze_sha256,
        "post_parse_receipt_sha256": P.sha256_file(
            POST_PARSE_RECEIPT, expected_path=POST_PARSE_RECEIPT,
            label="post-parse receipt",
        ),
        "execution_receipt_sha256": post["execution_receipt_sha256"],
        "run_properties_manifest": post["run_properties_manifest"],
        "fetched_properties_sha256": properties.sha256,
        "trace_manifest": post["trace_manifest"],
    }
    _write_receipt(POST_FETCH_RECEIPT, value, "post-fetch receipt")


def load_fetched_properties(
    freeze_sha256: str, execution_receipt_sha256: str | None = None,
):
    receipt = _read_receipt(POST_FETCH_RECEIPT, "post-fetch receipt")
    try:
        loaded = CampaignIO.read_regular_exact(
            EVAL_PROPERTIES, expected=EVAL_PROPERTIES,
            label="fetched campaign properties",
        )
    except CampaignIO.CampaignIOError as err:
        raise RunnerError(str(err)) from err
    if (
        set(receipt) != {
            "schema", "freeze_sha256", "post_parse_receipt_sha256",
            "execution_receipt_sha256", "run_properties_manifest",
            "fetched_properties_sha256", "trace_manifest",
        }
        or receipt.get("schema") != RUNNER_SCHEMA + "/post-fetch"
        or receipt.get("freeze_sha256") != freeze_sha256
        or receipt.get("post_parse_receipt_sha256") != P.sha256_file(
            POST_PARSE_RECEIPT, expected_path=POST_PARSE_RECEIPT,
            label="post-parse receipt",
        )
        or P.SHA256_RE.fullmatch(
            receipt.get("execution_receipt_sha256", "")
        ) is None
        or (
            execution_receipt_sha256 is not None
            and receipt.get("execution_receipt_sha256")
            != execution_receipt_sha256
        )
        or receipt.get("run_properties_manifest")
        != _run_properties_manifest()
        or receipt.get("trace_manifest") != _trace_manifest()
        or receipt.get("fetched_properties_sha256") != loaded.sha256
    ):
        raise RunnerError("fetched campaign properties differ from their seal")
    try:
        return json.loads(loaded.raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RunnerError("fetched campaign properties are invalid JSON") from err


def _install_cell_mapping_properties(freeze: dict) -> None:
    global _ACTIVE_CELL_MAPPING
    _ACTIVE_CELL_MAPPING = {
        (row["algorithm"], row["domain"], row["problem"]): row
        for row in P.task_major_cell_mapping(
            P.guided_b_tasks(freeze["base_confirmation_b"])
        )
    }
    from downward.experiment import FastDownwardRun

    original = FastDownwardRun.__init__
    if getattr(original, "_metric_choice_mapping", False):
        return

    def mapped_init(self, experiment, algorithm, task):
        original(self, experiment, algorithm, task)
        key = (algorithm.name, task.domain, task.problem)
        try:
            row = _ACTIVE_CELL_MAPPING[key]
        except KeyError as err:
            raise RunnerError("generated run is outside frozen mapping") from err
        for field in (
            "run_id", "array_task", "family", "family_sequence_index",
            "triad_position",
        ):
            self.set_property(field, row[field])

    mapped_init._metric_choice_mapping = True
    FastDownwardRun.__init__ = mapped_init


def _install_hardened_deterministic_run_body() -> None:
    from lab.environments import SlurmEnvironment

    original = SlurmEnvironment._get_run_job_body
    if getattr(original, "_metric_choice_run_body", False):
        return

    def hardened(self, run_step):
        body = original(self, run_step)
        start = body.find("function execute_run {")
        end_marker = "\n\n# Shuffle tasks to avoid systematic bias."
        end = body.find(end_marker)
        if start < 0 or end < 0 or end <= start:
            raise RunnerError("Lab run-body template changed")
        execute = SafeIO.hardened_execute_run_block(
            Path(sys.executable), P.SCRIPT_DIR / "pdb_confirmation_run_cell.py",
            (
                "driver.err", "driver.log", P.SELECTOR_TRACE,
                RunCell.HARDWARE_ATTESTATION_NAME,
            ),
        )
        body = body[:start] + execute + body[end:]
        shuffled = "for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID | shuf); do"
        ordered = "for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID); do"
        if body.count(shuffled) != 1:
            raise RunnerError("Lab within-triad ordering template changed")
        body = body.replace(shuffled, ordered)
        if "| shuf" in body or "[[ -f driver.log ]]" in body:
            raise RunnerError("Lab run body retained an unsafe execution path")
        return body

    hardened._metric_choice_run_body = True
    SlurmEnvironment._get_run_job_body = hardened


def build_manifest(freeze: dict, freeze_sha256: str) -> dict:
    P.validate_freeze(freeze, verify_live_sources=False)
    P._require_sha(freeze_sha256, "dual metric freeze")
    tasks = P.guided_b_tasks(freeze["base_confirmation_b"])
    cells = P.task_major_cell_mapping(tasks)
    task_sources = {
        (row["directory"], row["problem"]): row for row in tasks
    }
    for cell in cells:
        cell["search"] = P.SEARCHES[cell["algorithm"]]
        source = task_sources[(cell["domain"], cell["problem"])]
        cell.update({
            "domain_source_path": source["domain_file"],
            "problem_source_path": source["problem_file"],
            "domain_source_sha256": source["domain_sha256"],
            "problem_source_sha256": source["problem_sha256"],
        })
    properties = build_manifest_properties(freeze, freeze_sha256)
    manifest = {
        "schema": RUNNER_SCHEMA,
        "freeze_sha256": freeze_sha256,
        "transport": Transport.scheduler_contract(freeze, P.ACCOUNT),
        "common_properties": properties,
        "cells": cells,
    }
    manifest["cells_sha256"] = hashlib.sha256(
        P.canonical_json(cells)
    ).hexdigest()
    validate_manifest(manifest, freeze, freeze_sha256)
    return manifest


def validate_manifest(manifest: dict, freeze: dict, freeze_sha256: str) -> None:
    if not isinstance(manifest, dict) or set(manifest) != {
        "schema", "freeze_sha256", "transport", "common_properties",
        "cells", "cells_sha256",
    } or manifest.get("schema") != RUNNER_SCHEMA:
        raise RunnerError("runner manifest schema changed")
    if manifest.get("freeze_sha256") != freeze_sha256:
        raise RunnerError("runner freeze binding changed")
    transport = manifest.get("transport")
    try:
        Transport.validate_scheduler_contract(transport, freeze, P.ACCOUNT)
    except Transport.TransportError as err:
        raise RunnerError("runner transport is not the frozen unthrottled array")
    cells = manifest.get("cells")
    if not isinstance(cells, list) or len(cells) != P.CELL_COUNT:
        raise RunnerError("runner cell cardinality changed")
    expected_cells = P.task_major_cell_mapping(
        P.guided_b_tasks(freeze["base_confirmation_b"])
    )
    sources = {
        (row["directory"], row["problem"]): row
        for row in P.guided_b_tasks(freeze["base_confirmation_b"])
    }
    for cell in expected_cells:
        cell["search"] = P.SEARCHES[cell["algorithm"]]
        source = sources[(cell["domain"], cell["problem"])]
        cell.update({
            "domain_source_path": source["domain_file"],
            "problem_source_path": source["problem_file"],
            "domain_source_sha256": source["domain_sha256"],
            "problem_source_sha256": source["problem_sha256"],
        })
    if cells != expected_cells or manifest.get("cells_sha256") != hashlib.sha256(
        P.canonical_json(cells)
    ).hexdigest():
        raise RunnerError("runner cell mapping changed")
    if any(
        [row["run_id"] for row in cells if row["array_task"] == task]
        != list(P.triad_cells(task))
        for task in range(1, P.EXPECTED_ARRAY_TASKS + 1)
    ):
        raise RunnerError("array element does not contain one whole triad")
    expected_properties = build_manifest_properties(freeze, freeze_sha256)
    if manifest.get("common_properties") != expected_properties:
        raise RunnerError("runner provenance binding changed")


V12_PROVENANCE_PROPERTY_FIELDS = (
    "source_audit_v12_schema",
    "source_audit_bindings_sha256",
    *P.V12_RUN_PROVENANCE_FIELDS,
    "confirmation_a_freeze_repository_revision",
)


def build_manifest_properties(freeze: dict, freeze_sha256: str) -> dict:
    base = freeze["base_confirmation_b"]
    source = base["source_audit_v12"]
    standalone_source = freeze["standalone_k32"]["sealed_b_input"]
    provenance = base["confirmation_a_authorization"][
        "source_audit_provenance"
    ]
    expected = P._expected_v12_run_provenance(
        source["bindings"], base["confirmation_a_freeze"]["sha256"]
    )
    if provenance != expected:
        raise RunnerError("V12 run provenance differs from sealed source")
    return {
        "campaign_freeze_sha256": freeze_sha256,
        "campaign_freeze_repository_revision": freeze[
            "freeze_repository_revision"
        ],
        "base_b_freeze_sha256": base["base_b_freeze_sha256"],
        "base_b_freeze_repository_revision": base[
            "base_b_freeze_repository_revision"
        ],
        "base_b_experiment_source_manifest_sha256": hashlib.sha256(
            P.canonical_json(base["base_b_experiment_source_sha256"])
        ).hexdigest(),
        "confirmation_a_authorization_receipt_sha256": base[
            "confirmation_a_authorization"
        ]["receipt_sha256"],
        "cohort_manifest_sha256": P.guided_b_projection_sha256(base),
        "planner_revision": freeze["planner"]["revision"],
        "planner_cache_name": freeze["planner"]["cache_name"],
        "PLANNER_CACHE_NAME": freeze["planner"]["cache_name"],
        "planner_manifest_sha256": hashlib.sha256(
            P.canonical_json_line(freeze["planner"])
        ).hexdigest(),
        "planner_downward_sha256": freeze["planner"]["downward_sha256"],
        "planner_preprocess_sha256": freeze["planner"]["preprocess_sha256"],
        "planner_tree_manifest_sha256": freeze["planner"][
            "tree_manifest_sha256"
        ],
        "calibration_receipt_sha256": freeze["calibration"]["receipt_sha256"],
        "calibration_task_manifest_sha256": freeze["calibration"][
            "development_task_manifest_sha256"
        ],
        "calibration_observations_sha256": freeze["calibration"][
            "observations_sha256"
        ],
        "option_matrix_sha256": freeze["design"]["option_matrix_sha256"],
        "run_cell_mapping_sha256": freeze["design"]["run_cell_mapping_sha256"],
        "standalone_k32_records_sha256": freeze["standalone_k32"][
            "records_sha256"
        ],
        "standalone_k32_evidence_sha256": freeze["standalone_k32"][
            "evidence_sha256"
        ],
        "standalone_b_parse_receipt_sha256": standalone_source[
            "parse_receipt_sha256"
        ],
        "standalone_b_fetch_receipt_sha256": standalone_source[
            "fetch_receipt_sha256"
        ],
        "standalone_b_properties_sha256": standalone_source[
            "properties_sha256"
        ],
        "source_audit_v12_schema": source["schema"],
        "source_audit_bindings_sha256": hashlib.sha256(
            P.canonical_json(source["bindings"])
        ).hexdigest(),
        **provenance,
        "confirmation_a_freeze_repository_revision": base[
            "confirmation_a_freeze"
        ]["repository_revision"],
        "campaign_source_manifest_sha256": hashlib.sha256(P.canonical_json(
            freeze["experiment_source_sha256"]
        )).hexdigest(),
        "protocol_sha256": freeze["design"]["protocol_sha256"],
        "dual_trace_schema": P.DUAL_TRACE_SCHEMA,
        "run_order_protocol": P.RUN_ORDER_PROTOCOL,
        "scheduler_contract": Transport.scheduler_contract(freeze, P.ACCOUNT),
    }

def load_and_build(freeze_path: Path = P.FREEZE_PATH) -> dict:
    freeze = P.load_freeze(freeze_path)
    return build_manifest(freeze, _freeze_sha256(freeze_path))


def _validate_benchmark_sources(cohort, root: Path) -> None:
    for task in cohort:
        for relative, expected in (
            (task.domain_file, task.domain_sha256),
            (task.problem_file, task.problem_sha256),
        ):
            relative_path = Path(relative)
            if relative_path.is_absolute() or ".." in relative_path.parts or (
                relative_path.as_posix() != relative
            ):
                raise RunnerError("benchmark source path escapes its archive")
            path = root / relative_path
            if P.sha256_file(
                path, expected_path=path, root=root, label="benchmark source"
            ) != expected:
                raise RunnerError("benchmark source bytes changed")


def _source_names(freeze: dict, freeze_path: Path) -> tuple[str, ...]:
    names = []
    for relative in P.SOURCE_FILES:
        path = Path(relative)
        if path.parts[:1] != ("experiments",):
            raise RunnerError("campaign source is outside experiments")
        names.append(Path(*path.parts[1:]).as_posix())
    try:
        names.append(freeze_path.relative_to(P.SCRIPT_DIR).as_posix())
    except ValueError as err:
        raise RunnerError("campaign freeze is outside experiments") from err
    if len(names) != len(set(names)):
        raise RunnerError("runner source list contains duplicates")
    return tuple(names)


def configure_lab_transport(freeze_path: Path = P.FREEZE_PATH):
    """Configure the existing generic transport without editing shared files."""
    freeze = P.load_freeze(freeze_path)
    if Path(freeze_path) != P.FREEZE_PATH:
        raise RunnerError("campaign freeze path changed")
    freeze_sha = P.sha256_file(
        freeze_path, expected_path=P.FREEZE_PATH, label="campaign freeze"
    )
    properties = build_manifest_properties(freeze, freeze_sha)
    tasks = P.guided_b_tasks(freeze["base_confirmation_b"])
    directories = {row["directory"] for row in tasks}

    source_adapter = SimpleNamespace(
        PROTOCOL=P.PROTOCOL,
        ProtocolError=P.ProtocolError,
        sha256_file=P.sha256_file,
        validate_matched_budget_provenance=lambda unused: None,
        COHORT_ARCHIVE_DEFAULT=BENCHMARKS,
        MATCH_ARCHIVE_DEFAULT=BENCHMARKS,
    )
    adapter = SimpleNamespace(
        Source=source_adapter,
        ProtocolError=P.ProtocolError,
        PLANNER_REVISION=freeze["planner"]["revision"],
        PLANNER_CACHE_NAME=freeze["planner"]["cache_name"],
        PLANNER_BINARY_SHA256=freeze["planner"]["downward_sha256"],
        PREPROCESS_BINARY_SHA256=freeze["planner"]["preprocess_sha256"],
        PLANNER_TREE_MANIFEST_SHA256=freeze["planner"]["tree_manifest_sha256"],
        BUILD_OPTIONS=P.BUILD_OPTIONS,
        CELL_COUNT=P.CELL_COUNT,
        COHORT_MANIFEST_SHA256=P.guided_b_projection_sha256(
            freeze["base_confirmation_b"]
        ),
        OPTION_MATRIX_SHA256=freeze["design"]["option_matrix_sha256"],
        PROTOCOL_SHA256=freeze["design"]["protocol_sha256"],
        REQUIRED_LAB_VERSION=P.REQUIRED_LAB_VERSION,
        REQUIRED_PYTHON_VERSION=P.REQUIRED_PYTHON_VERSION,
        PROTOCOL=P.PROTOCOL,
        ANALYSIS_PROTOCOL=P.ANALYSIS_PROTOCOL,
        COHORT_ROLE="source-disjoint-universal-confirmation-b",
        COHORT_TASKS=P.COHORT_TASKS,
        COHORT_DOMAINS=len(directories),
        CONFIG_COUNT=P.CONFIG_COUNT,
        TIME_LIMIT_SECONDS=P.TIME_LIMIT_SECONDS,
        MEMORY_LIMIT_MIB=P.MEMORY_LIMIT_MIB,
        CONFIGS=P.CONFIGS,
        validate_protocol_without_archive=lambda: P.validate_freeze(
            freeze, verify_live_sources=True
        ),
        load_cohort=lambda archive: P.load_cohort(
            archive, freeze_path=freeze_path
        ),
    )
    import exp_pdb_profile_certificate_holdout as Base

    Base.P = adapter
    Transport.install_no_requeue_header()
    _install_cell_mapping_properties(freeze)
    _install_hardened_deterministic_run_body()
    Base._sha256_file = lambda path: P.sha256_file(
        Path(path), expected_path=Path(path), label="transport dependency"
    )
    Base._materialize_run_inputs = _local_materialize_run_inputs
    Base._run_input_tree_digest = _local_run_input_tree_digest
    Base.PLANNER_REVISION = freeze["planner"]["revision"]
    Base.PLANNER_BINARY_SHA256 = freeze["planner"]["downward_sha256"]
    Base.PREPROCESS_BINARY_SHA256 = freeze["planner"]["preprocess_sha256"]
    Base.EXPERIMENT_PATH = EXPERIMENT_PATH
    Base.REVISION_CACHE = REVISION_CACHE
    Base.BENCHMARKS = BENCHMARKS
    Base.COHORT_ARCHIVE = BENCHMARKS
    Base.MATCH_ARCHIVE = BENCHMARKS
    Base.ACCOUNT = P.ACCOUNT
    Base.PARTITION = PARTITION
    Base.MAX_ARRAY_TASKS = P.EXPECTED_ARRAY_TASKS
    Base.RUNS_PER_ARRAY_TASK = P.RUNS_PER_ARRAY_TASK
    Base.EXPECTED_ARRAY_TASKS = P.EXPECTED_ARRAY_TASKS
    Base.SCHEDULER_TIME_LIMIT = freeze["design"]["scheduler_time_limit"]
    Base.SCHEDULER_MEMORY = freeze["design"]["scheduler_memory"]
    Base.LAUNCH_RECEIPT = LAUNCH_RECEIPT
    Base.LAUNCH_RECEIPT_SCHEMA = LAUNCH_SCHEMA
    Base.EXPECTED_JOB_NAME = EXPECTED_JOB_NAME
    Base.PARTITION_REQUIREMENT_LABEL = "terminal dual-metric choice"
    Base.EXTRA_PARSER_MODULES = ("pdb_terminal_metric_choice_parser",)
    Base.RUN_ORDER_BUILDER = P.task_major_blocked_run_order
    Base.SOURCE_PROTOCOL = P.PROTOCOL
    Base.RUNNER_SOURCE_FILES = _source_names(freeze, freeze_path)
    Base.VALIDATE_MATCHED_BUDGET_PROVENANCE = False
    Base.MATERIALIZE_PDDL_INPUTS = True
    Base.ENVIRONMENT_REQUIREMENTS_FILE = REQUIREMENTS
    Base.BENCHMARK_SOURCE_VALIDATOR = lambda cohort: (
        _validate_benchmark_sources(cohort, BENCHMARKS)
    )
    fixed_run_properties = {
        "cohort_manifest_sha256", "option_matrix_sha256", "protocol_sha256",
        "planner_revision", "planner_preprocess_sha256",
    }
    Base.EXTRA_RUN_PROPERTIES = {
        key: value for key, value in properties.items()
        if key not in fixed_run_properties
    }
    fixed_receipt_properties = {
        "planner_revision", "cohort_manifest_sha256", "option_matrix_sha256",
        "protocol_sha256",
    }
    Base.EXTRA_RECEIPT_PROPERTIES = {
        **{
            key: value for key, value in properties.items()
            if key not in fixed_receipt_properties
        },
        "frozen_design": freeze["design"],
        "frozen_source_manifest": freeze["experiment_source_sha256"],
    }
    Base.PRE_PARSE_VALIDATOR = lambda: _pre_parse(freeze_sha, Base)
    Base.POST_PARSE_SEALER = lambda: _post_parse(freeze_sha)
    Base.PRE_FETCH_VALIDATOR = lambda: _pre_fetch(freeze_sha, Base)
    Base.POST_FETCH_SEALER = lambda: _post_fetch(freeze_sha, Base)
    inherited_prepare = Base._prepare_launch_materials

    def hardened_prepare(job_file, cached):
        job_path = Path(job_file)
        Transport.validate_job_file(
            job_path, expected=GRID_DIR / EXPECTED_JOB_NAME,
            contract=Transport.scheduler_contract(freeze, P.ACCOUNT),
        )
        return inherited_prepare(job_file, cached)

    Base._prepare_launch_materials = hardened_prepare
    return Base


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", type=Path, default=P.FREEZE_PATH)
    parser.add_argument("--manifest-json", action="store_true")
    args, remaining = parser.parse_known_args(argv)
    freeze_path = args.freeze
    if freeze_path != P.FREEZE_PATH:
        parser.error("--freeze must retain the exact sealed path")
    if args.manifest_json:
        if remaining:
            parser.error("manifest inspection accepts no Lab steps")
        manifest = load_and_build(freeze_path)
        print(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
        return
    base = configure_lab_transport(freeze_path)
    if remaining == ["start"]:
        parser.error(
            "Lab start is disabled; use prepare-job followed by launch"
        )
    commands = {
        "prepare-job", "launch", "recover-launch", "status", "snapshot",
        "recover", "recover-reconcile", "seal",
    }
    if remaining and remaining[0] in commands:
        if len(remaining) != 1:
            parser.error("campaign coordinator commands take no extra arguments")
        import pdb_terminal_metric_choice_execution as Execution

        command = remaining[0]
        if command == "prepare-job":
            path = base.prepare_start_job()
            expected = GRID_DIR / EXPECTED_JOB_NAME
            if path != expected:
                raise RunnerError("rendered primary job path changed")
            _, digest = Execution.validate_primary_job(
                P.load_freeze(P.FREEZE_PATH)
            )
            result = {
                "job_file": str(path), "job_file_sha256": digest,
                "submitted": False,
            }
        elif command == "launch":
            result = Execution.launch_primary(base)
        elif command == "recover-launch":
            result = Execution.recover_primary_launch(base)
        elif command == "status":
            result = Execution.status(base)
        elif command == "snapshot":
            result = {
                "scheduler_snapshot_sha256": (
                    Execution.publish_primary_snapshot(base)
                )
            }
        elif command == "recover":
            result = Execution.launch_recovery(base)
        elif command == "recover-reconcile":
            result = Execution.recover_recovery_launch(base)
        else:
            result = {
                "execution_receipt_sha256": Execution.seal_execution(base)
            }
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    return base.main(remaining)


if __name__ == "__main__":
    main()
