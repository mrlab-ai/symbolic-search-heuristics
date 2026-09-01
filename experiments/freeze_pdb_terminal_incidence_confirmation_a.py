#!/usr/bin/env python3
"""Create the one prospective source/planner freeze for Confirmation A."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import jj_cached_revision as JJ
import pdb_terminal_incidence_confirmation_a_protocol as P


class FreezeError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
REVISION_CACHE = SCRIPT_DIR / "data" / "revision-cache"


def _relative(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO.resolve()).as_posix()
    except (OSError, ValueError) as err:
        raise FreezeError("freeze input escapes the repository") from err


def _source_hashes(revision: str) -> dict[str, str]:
    hashes = {}
    for relative in P.EXPERIMENT_SOURCE_FILES:
        path = REPO / relative
        live = P.sha256_file(path)
        try:
            tracked = JJ.tracked_file_sha256(REPO, revision, relative)
        except JJ.JjCacheError as err:
            raise FreezeError(
                "experiment source is not committed at planner revision: {}"
                .format(relative)
            ) from err
        if live != tracked:
            raise FreezeError(
                "live experiment source differs from planner revision: {}"
                .format(relative)
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


def build_freeze(
    *,
    attestation: Path,
    execution_receipt: Path,
    launch_receipt: Path,
    revision: str,
) -> dict:
    P.validate_protocol_design()
    materials = P.load_source_materials(
        attestation, execution_receipt, launch_receipt
    )
    for path, expected in (
        (materials.attestation_path, materials.attestation_sha256),
        (materials.execution_receipt_path, materials.execution_receipt_sha256),
        (materials.launch_receipt_path, materials.launch_receipt_sha256),
    ):
        relative = _relative(path)
        try:
            tracked = JJ.tracked_file_sha256(REPO, revision, relative)
        except JJ.JjCacheError as err:
            raise FreezeError(
                "sealed source artifact is not committed: {}".format(relative)
            ) from err
        if tracked != expected:
            raise FreezeError("sealed source artifact differs from its commit")
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
        "attestation_records_sha256": materials.records_sha256,
        "translator_source_sha256": materials.translator_source_sha256,
        "job_id": source_launch["job_id"],
        "code_manifest_sha256": source_execution["code_manifest_sha256"],
        "repository_commit_id": source_launch["repository_commit_id"],
        "union_tree_sha256": source_execution["union_tree"]["sha256"],
        "slurm_script_sha256": source_launch["slurm_script_sha256"],
        "launch_intent_sha256": source_launch["launch_intent_sha256"],
    }
    return {
        "schema": P.FREEZE_SCHEMA,
        "source_audit": source_provenance,
        "planner": {
            "revision": revision,
            "cache_name": cached.name,
            "build_options": list(P.BUILD_OPTIONS),
            **{field: planner[field] for field in required_hashes},
        },
        "design": {
            "protocol_sha256": P.sha256_file(P.PROTOCOL_PATH),
            "option_matrix_sha256": P.option_matrix_digest(),
            "cohort_tasks": P.COHORT_TASKS,
            "configs": P.CONFIG_COUNT,
            "cells": P.CELL_COUNT,
            "horizon": P.HORIZON,
            "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
            "bootstrap_seed": P.BOOTSTRAP_SEED,
        },
        "experiment_source_sha256": _source_hashes(revision),
    }


def _write_exclusive(path: Path, value: dict) -> str:
    raw = P.canonical_json_line(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise FreezeError("Confirmation A freeze already exists") from err
    return hashlib.sha256(raw).hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attestation", type=Path, required=True)
    parser.add_argument("--execution-receipt", type=Path, required=True)
    parser.add_argument("--launch-receipt", type=Path, required=True)
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
