#!/usr/bin/env python3
"""Create the one prospective V12 source/planner freeze for Confirmation A."""

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
        return Path(os.path.abspath(path)).relative_to(
            Path(os.path.abspath(REPO))
        ).as_posix()
    except ValueError as err:
        raise FreezeError("freeze input escapes the repository") from err


def _attest_tracked_file(
    path: Path, expected: str, revision: str, label: str,
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
        raise FreezeError(
            "{} is not committed at the freeze revision".format(label)
        ) from err
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
            path, live, revision, "experiment source {}".format(relative),
        )
        hashes[relative] = live
    return hashes


def _require_clean_parent(revision: str | None) -> str:
    try:
        if JJ.live_working_copy_diff_summary(REPO):
            raise FreezeError("freeze requires a clean empty working-copy commit")
        parent = JJ.parent_commit(REPO)
    except JJ.JjCacheError as err:
        raise FreezeError("cannot resolve the clean Jujutsu parent") from err
    if revision is None:
        revision = parent
    if revision != parent or P.COMMIT_RE.fullmatch(revision) is None:
        raise FreezeError(
            "freeze repository revision must be the clean working-copy parent"
        )
    return revision


def _require_source_ancestry(bindings: dict, revision: str) -> None:
    source = bindings["preflight_source_repository_commit_id"]
    preflight = bindings["preflight_seal_repository_commit_id"]
    seal = bindings["seal_repository_commit_id"]
    try:
        JJ.require_ancestor(REPO, source, preflight)
        JJ.require_ancestor(REPO, preflight, seal)
        JJ.require_ancestor(REPO, seal, revision)
        JJ.require_ancestor(REPO, P.PLANNER_REVISION_REQUIRED, revision)
    except JJ.JjCacheError as err:
        raise FreezeError(
            "V12 S-to-P-to-Q chain or planner is not ancestral to the freeze"
        ) from err


def _planner_freeze() -> dict:
    cached = JJ.JjCachedFastDownwardRevision(
        REVISION_CACHE, REPO, P.PLANNER_REVISION_REQUIRED,
        list(P.BUILD_OPTIONS),
    )
    cached.cache()
    planner = cached.attest()
    if (
        planner.get("revision") != P.PLANNER_REVISION_REQUIRED
        or planner.get("build_options") != list(P.BUILD_OPTIONS)
    ):
        raise FreezeError("planner cache identifies the wrong revision")
    required = ("downward_sha256", "preprocess_sha256", "tree_manifest_sha256")
    if any(P.SHA256_RE.fullmatch(planner.get(name, "")) is None
           for name in required):
        raise FreezeError("planner cache attestation is incomplete")
    return {
        "revision": P.PLANNER_REVISION_REQUIRED,
        "cache_name": cached.name,
        "build_options": list(P.BUILD_OPTIONS),
        **{name: planner[name] for name in required},
    }


def build_freeze(
    *, source_seal_revision: str, freeze_repository_revision: str,
) -> dict:
    P.validate_protocol_design()
    materials = P.load_source_materials(source_seal_revision)
    _require_source_ancestry(materials.bindings, freeze_repository_revision)
    return {
        "schema": P.FREEZE_SCHEMA,
        "freeze_repository_revision": freeze_repository_revision,
        "source_audit": materials.source_audit,
        "planner": _planner_freeze(),
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
        "experiment_source_sha256": _source_hashes(
            freeze_repository_revision
        ),
    }


def _revalidate_before_write(
    value: dict, *, source_seal_revision: str,
    freeze_repository_revision: str,
) -> None:
    if _require_clean_parent(freeze_repository_revision) != freeze_repository_revision:
        raise FreezeError("freeze revision changed during planner caching")
    bindings = value.get("source_audit", {}).get("bindings")
    if not isinstance(bindings, dict):
        raise FreezeError("built V12 source provenance is incomplete")
    _require_source_ancestry(bindings, freeze_repository_revision)
    if value.get("freeze_repository_revision") != freeze_repository_revision:
        raise FreezeError("freeze repository revision changed during caching")
    if value.get("experiment_source_sha256") != _source_hashes(
        freeze_repository_revision
    ):
        raise FreezeError("experiment sources changed during planner caching")
    # This is the second and final V12 payload consumption.  The caller writes
    # immediately after this exact canonical comparison.
    materials = P.load_source_materials(source_seal_revision)
    if (
        materials.bindings["seal_repository_commit_id"]
        != source_seal_revision
        or P.canonical_json(value.get("source_audit"))
        != P.canonical_json(materials.source_audit)
    ):
        raise FreezeError("V12 source changed during planner caching")


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
    parser.add_argument("--source-seal-revision", required=True)
    parser.add_argument("--freeze-repository-revision")
    parser.add_argument("--output", type=Path, default=P.FREEZE_PATH)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    revision = _require_clean_parent(args.freeze_repository_revision)
    value = build_freeze(
        source_seal_revision=args.source_seal_revision,
        freeze_repository_revision=revision,
    )
    _revalidate_before_write(
        value,
        source_seal_revision=args.source_seal_revision,
        freeze_repository_revision=revision,
    )
    digest = _write_exclusive(args.output, value)
    if args.output.resolve() == P.FREEZE_PATH.resolve():
        P._load_freeze(P.FREEZE_PATH)
    print(json.dumps({
        "freeze": str(args.output),
        "freeze_sha256": digest,
        "planner_revision": P.PLANNER_REVISION_REQUIRED,
        "freeze_repository_revision": revision,
        "source_seal_revision": args.source_seal_revision,
        "confirmation_a_candidate_indices_sha256": value["source_audit"][
            "confirmation_a"
        ]["candidate_indices_sha256"],
        "confirmation_a_source_projection_sha256": value["source_audit"][
            "confirmation_a"
        ]["source_projection_sha256"],
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FreezeError, P.ProtocolError, JJ.JjCacheError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
