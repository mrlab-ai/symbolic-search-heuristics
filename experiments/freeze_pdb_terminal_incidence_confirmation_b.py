#!/usr/bin/env python3
"""Create the one prospective source/planner freeze for Confirmation B."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import jj_cached_revision as JJ
import pdb_terminal_incidence_confirmation_b_protocol as P


class FreezeError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
REVISION_CACHE = SCRIPT_DIR / "data" / "revision-cache"


def _relative(path: Path) -> str:
    try:
        lexical = Path(os.path.abspath(path))
        root = Path(os.path.abspath(REPO))
        return lexical.relative_to(root).as_posix()
    except ValueError as err:
        raise FreezeError("freeze input escapes the repository") from err


def _attest_tracked_file(
    path: Path, expected: str, revision: str, label: str
) -> str:
    relative = _relative(path)
    try:
        before = P.sha256_file(path)
    except P.ProtocolError as err:
        raise FreezeError("{} is not a regular live file".format(label)) from err
    if before != expected:
        raise FreezeError("{} changed live before revision check".format(label))
    try:
        tracked = JJ.tracked_file_sha256(REPO, revision, relative)
    except JJ.JjCacheError as err:
        raise FreezeError("{} is not committed at the freeze revision".format(
            label
        )) from err
    if tracked != expected:
        raise FreezeError("{} differs from the freeze revision".format(label))
    try:
        after = P.sha256_file(path)
    except P.ProtocolError as err:
        raise FreezeError("{} changed during revision check".format(label)) from err
    if after != expected:
        raise FreezeError("{} changed during revision check".format(label))
    return relative


def _source_hashes(revision: str) -> dict[str, str]:
    hashes = {}
    for relative in P.EXPERIMENT_SOURCE_FILES:
        path = REPO / relative
        live = P.sha256_file(path)
        _attest_tracked_file(
            path, live, revision, "experiment source {}".format(relative)
        )
        hashes[relative] = live
    return hashes


def _require_clean_parent(revision: str | None) -> str:
    try:
        if JJ.working_copy_diff_summary(REPO):
            raise FreezeError("freeze requires a clean empty working-copy commit")
        parent = JJ.parent_commit(REPO)
    except JJ.JjCacheError as err:
        raise FreezeError("cannot resolve the clean Jujutsu parent") from err
    if revision is None:
        revision = parent
    if revision != parent or P.COMMIT_RE.fullmatch(revision) is None:
        raise FreezeError("planner revision must be the clean working-copy parent")
    return revision


def _tracked_source_v4_hashes(materials, revision: str) -> dict[str, str]:
    hashes = dict(materials.tracked_file_sha256)
    if len(hashes) != 26:
        raise FreezeError("source-audit v4 bound file set changed")
    for relative, expected in hashes.items():
        path = REPO / relative
        _attest_tracked_file(
            path, expected, revision,
            "source-audit v4 bound file {}".format(relative),
        )
    return hashes


def _require_source_ancestor(materials, revision: str) -> None:
    try:
        JJ.require_ancestor(
            REPO, materials.launch_receipt["repository_commit_id"], revision
        )
    except JJ.JjCacheError as err:
        raise FreezeError(
            "source-audit producer revision is not an ancestor of the freeze"
        ) from err


def build_freeze(
    *,
    attestation: Path,
    execution_receipt: Path,
    launch_receipt: Path,
    confirmation_a_receipt: Path,
    confirmation_a_receipt_pin: Path,
    confirmation_a_first_output: Path,
    confirmation_a_second_output: Path,
    revision: str,
) -> dict:
    P.validate_static_design()
    materials = P.load_source_materials(
        attestation, execution_receipt, launch_receipt
    )
    _require_source_ancestor(materials, revision)
    authorization = P.load_confirmation_a_authorization(
        confirmation_a_receipt,
        confirmation_a_receipt_pin,
        confirmation_a_first_output,
        confirmation_a_second_output,
    )
    P._validate_confirmation_a_source_link(authorization, materials)
    for path, expected in (
        (materials.attestation_path, materials.attestation_sha256),
        (materials.execution_receipt_path, materials.execution_receipt_sha256),
        (materials.launch_receipt_path, materials.launch_receipt_sha256),
    ):
        _attest_tracked_file(path, expected, revision, "sealed source artifact")
    tracked_file_sha256 = _tracked_source_v4_hashes(materials, revision)
    authorization_hashes = {
        authorization["receipt_path"]: authorization["receipt_sha256"],
        authorization["first_output_path"]: authorization[
            "first_output_sha256"
        ],
        authorization["second_output_path"]: authorization[
            "second_output_sha256"
        ],
        authorization["receipt_pin_path"]: hashlib.sha256(
            (authorization["receipt_sha256"] + "\n").encode("ascii")
        ).hexdigest(),
    }
    for path, expected in authorization_hashes.items():
        _attest_tracked_file(
            path, expected, revision, "Confirmation A authorization"
        )
    cached = JJ.JjCachedFastDownwardRevision(
        REVISION_CACHE, REPO, revision, list(P.BUILD_OPTIONS)
    )
    cached.cache()
    planner = cached.attest()
    expected_planner = {
        "revision": revision,
        "build_options": list(P.BUILD_OPTIONS),
    }
    if any(planner.get(key) != value for key, value in expected_planner.items()):
        raise FreezeError("planner cache identifies the wrong revision")
    required_hashes = (
        "downward_sha256", "preprocess_sha256", "tree_manifest_sha256"
    )
    if any(
        P.SHA256_RE.fullmatch(planner.get(field, "")) is None
        for field in required_hashes
    ):
        raise FreezeError("planner cache attestation is incomplete")
    source_launch = materials.launch_receipt
    source_execution = materials.execution_receipt
    source_provenance = {
        "attestation_path": _relative(materials.attestation_path),
        "execution_receipt_path": _relative(materials.execution_receipt_path),
        "launch_receipt_path": _relative(materials.launch_receipt_path),
        "attestation_sha256": materials.attestation_sha256,
        "execution_receipt_sha256": materials.execution_receipt_sha256,
        "launch_receipt_sha256": materials.launch_receipt_sha256,
        "cohort_manifest_sha256": materials.cohort_manifest_sha256,
        "confirmation_a_cohort_manifest_sha256": (
            materials.confirmation_a_cohort_manifest_sha256
        ),
        "attestation_records_sha256": materials.records_sha256,
        "translator_source_sha256": materials.translator_source_sha256,
        "job_id": source_launch["job_id"],
        "code_manifest_sha256": source_execution["code_manifest_sha256"],
        "repository_commit_id": source_launch["repository_commit_id"],
        "original_output_tree_sha256": source_execution[
            "original_output_tree"
        ]["sha256"],
        "slurm_script_sha256": source_launch["slurm_script_sha256"],
        "launch_intent_sha256": source_launch["launch_intent_sha256"],
        "tracked_file_sha256": tracked_file_sha256,
    }
    authorization_provenance = {
        **{
            key: _relative(value)
            for key, value in authorization.items()
            if key.endswith("_path")
        },
        **{
            key: value
            for key, value in authorization.items()
            if not key.endswith("_path")
        },
    }
    cohort_tasks = len(materials.tasks)
    cells = cohort_tasks * P.CONFIG_COUNT
    array_tasks = (cells + P.RUNS_PER_ARRAY_TASK - 1) // P.RUNS_PER_ARRAY_TASK
    return {
        "schema": P.FREEZE_SCHEMA,
        "source_audit": source_provenance,
        "confirmation_a_authorization": authorization_provenance,
        "planner": {
            "revision": revision,
            "cache_name": cached.name,
            "build_options": list(P.BUILD_OPTIONS),
            **{field: planner[field] for field in required_hashes},
        },
        "design": {
            "protocol_sha256": P.sha256_file(P.PROTOCOL_PATH),
            "option_matrix_sha256": P.option_matrix_digest(),
            "cohort_tasks": cohort_tasks,
            "target_cohort_tasks": P.TARGET_COHORT_TASKS,
            "minimum_cohort_tasks": P.MIN_COHORT_TASKS,
            "maximum_cohort_tasks": P.MAX_COHORT_TASKS,
            "configs": P.CONFIG_COUNT,
            "cells": cells,
            "expected_array_tasks": array_tasks,
            "runs_per_array_task": P.RUNS_PER_ARRAY_TASK,
            "run_order_protocol": P.RUN_ORDER_PROTOCOL,
            "run_cell_mapping_sha256": P.run_cell_mapping_digest(
                materials.tasks
            ),
            "probe_layers": P.PROBE_LAYERS,
            "par2_seconds": P.PAR2_SECONDS,
            "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
            "bootstrap_seed": P.BOOTSTRAP_SEED,
            "minimum_mechanism_tasks": P.MIN_MECHANISM_TASKS,
            "minimum_mechanism_families": P.MIN_MECHANISM_FAMILIES,
            "non_gating_reference_labels": list(
                P.NON_GATING_REFERENCE_LABELS
            ),
        },
        "experiment_source_sha256": _source_hashes(revision),
    }


def _revalidate_before_write(
    value: dict,
    *,
    attestation: Path,
    execution_receipt: Path,
    launch_receipt: Path,
    confirmation_a_receipt: Path,
    confirmation_a_receipt_pin: Path,
    confirmation_a_first_output: Path,
    confirmation_a_second_output: Path,
    revision: str,
) -> None:
    if _require_clean_parent(revision) != revision:
        raise FreezeError("freeze revision changed during planner caching")
    materials = P.load_source_materials(
        attestation, execution_receipt, launch_receipt
    )
    _require_source_ancestor(materials, revision)
    authorization = P.load_confirmation_a_authorization(
        confirmation_a_receipt,
        confirmation_a_receipt_pin,
        confirmation_a_first_output,
        confirmation_a_second_output,
    )
    P._validate_confirmation_a_source_link(authorization, materials)
    for path, expected in (
        (materials.attestation_path, materials.attestation_sha256),
        (materials.execution_receipt_path, materials.execution_receipt_sha256),
        (materials.launch_receipt_path, materials.launch_receipt_sha256),
    ):
        _attest_tracked_file(path, expected, revision, "sealed source artifact")
    tracked = _tracked_source_v4_hashes(materials, revision)
    authorization_hashes = {
        authorization["receipt_path"]: authorization["receipt_sha256"],
        authorization["first_output_path"]: authorization[
            "first_output_sha256"
        ],
        authorization["second_output_path"]: authorization[
            "second_output_sha256"
        ],
        authorization["receipt_pin_path"]: hashlib.sha256(
            (authorization["receipt_sha256"] + "\n").encode("ascii")
        ).hexdigest(),
    }
    for path, expected in authorization_hashes.items():
        _attest_tracked_file(
            path, expected, revision, "Confirmation A authorization"
        )
    launch = materials.launch_receipt
    execution = materials.execution_receipt
    expected_sources = {
        "attestation_path": _relative(materials.attestation_path),
        "execution_receipt_path": _relative(materials.execution_receipt_path),
        "launch_receipt_path": _relative(materials.launch_receipt_path),
        "attestation_sha256": materials.attestation_sha256,
        "execution_receipt_sha256": materials.execution_receipt_sha256,
        "launch_receipt_sha256": materials.launch_receipt_sha256,
        "cohort_manifest_sha256": materials.cohort_manifest_sha256,
        "confirmation_a_cohort_manifest_sha256": (
            materials.confirmation_a_cohort_manifest_sha256
        ),
        "attestation_records_sha256": materials.records_sha256,
        "translator_source_sha256": materials.translator_source_sha256,
        "job_id": launch["job_id"],
        "code_manifest_sha256": execution["code_manifest_sha256"],
        "repository_commit_id": launch["repository_commit_id"],
        "original_output_tree_sha256": execution[
            "original_output_tree"
        ]["sha256"],
        "slurm_script_sha256": launch["slurm_script_sha256"],
        "launch_intent_sha256": launch["launch_intent_sha256"],
        "tracked_file_sha256": tracked,
    }
    expected_authorization = {
        **{
            key: _relative(item)
            for key, item in authorization.items()
            if key.endswith("_path")
        },
        **{
            key: item
            for key, item in authorization.items()
            if not key.endswith("_path")
        },
    }
    if value.get("source_audit") != expected_sources:
        raise FreezeError("source provenance changed during planner caching")
    if value.get("confirmation_a_authorization") != expected_authorization:
        raise FreezeError("Confirmation A authorization changed during caching")
    if value.get("experiment_source_sha256") != _source_hashes(revision):
        raise FreezeError("experiment sources changed during planner caching")


def _write_exclusive(path: Path, value: dict) -> str:
    raw = P.canonical_json_line(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise FreezeError("Confirmation B freeze already exists") from err
    return hashlib.sha256(raw).hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--execution-receipt", type=Path, required=True)
    parser.add_argument("--launch-receipt", type=Path, required=True)
    parser.add_argument(
        "--confirmation-a-receipt", type=Path,
        default=P.CONFIRMATION_A_RECEIPT_PATH,
    )
    parser.add_argument(
        "--confirmation-a-receipt-pin", type=Path,
        default=P.CONFIRMATION_A_RECEIPT_PIN_PATH,
    )
    parser.add_argument(
        "--confirmation-a-first-output", type=Path,
        default=P.CONFIRMATION_A_FIRST_OUTPUT_PATH,
    )
    parser.add_argument(
        "--confirmation-a-second-output", type=Path,
        default=P.CONFIRMATION_A_SECOND_OUTPUT_PATH,
    )
    parser.add_argument("--planner-revision")
    parser.add_argument("--output", type=Path, default=P.FREEZE_PATH)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    revision = _require_clean_parent(args.planner_revision)
    value = build_freeze(
        attestation=args.attestation,
        execution_receipt=args.execution_receipt,
        launch_receipt=args.launch_receipt,
        confirmation_a_receipt=args.confirmation_a_receipt,
        confirmation_a_receipt_pin=args.confirmation_a_receipt_pin,
        confirmation_a_first_output=args.confirmation_a_first_output,
        confirmation_a_second_output=args.confirmation_a_second_output,
        revision=revision,
    )
    _revalidate_before_write(
        value,
        attestation=args.attestation,
        execution_receipt=args.execution_receipt,
        launch_receipt=args.launch_receipt,
        confirmation_a_receipt=args.confirmation_a_receipt,
        confirmation_a_receipt_pin=args.confirmation_a_receipt_pin,
        confirmation_a_first_output=args.confirmation_a_first_output,
        confirmation_a_second_output=args.confirmation_a_second_output,
        revision=revision,
    )
    digest = _write_exclusive(args.output, value)
    # Re-open through the exact runtime path when the default location is used.
    if args.output.resolve() == P.FREEZE_PATH.resolve():
        P._load_freeze(P.FREEZE_PATH)
    print(json.dumps({
        "freeze": str(args.output),
        "freeze_sha256": digest,
        "planner_revision": revision,
        "cohort_manifest_sha256": value["source_audit"][
            "cohort_manifest_sha256"
        ],
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FreezeError, P.ProtocolError, JJ.JjCacheError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
