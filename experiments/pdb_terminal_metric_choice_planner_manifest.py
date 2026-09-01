#!/usr/bin/env python3
"""Produce or verify the exact terminal-metric planner manifest."""

from __future__ import annotations

import argparse
import hashlib
import os
import stat

import jj_cached_revision as JJ
import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_protocol as P


class PlannerManifestError(RuntimeError):
    pass


PLANNER_REVISION = P.REQUIRED_PLANNER_REVISION
REPO = P.REPO
REVISION_CACHE = P.SCRIPT_DIR / "data" / "revision-cache"
MANIFEST_PATH = P.PLANNER_MANIFEST_PATH


def _attest_exact_cache(cache: JJ.JjCachedFastDownwardRevision) -> dict:
    expected = REVISION_CACHE / cache.name
    try:
        SafeIO.validate_lexical_path(
            expected, label="planner cache", expected_path=expected, root=REPO
        )
    except SafeIO.SafeReadError as err:
        raise PlannerManifestError(str(err)) from err
    if cache.path != expected:
        raise PlannerManifestError("planner cache path changed")

    parent_fd = None
    cache_fd = None
    try:
        parent_fd = CampaignIO._open_directory(
            expected.parent, label="planner cache", root=REPO
        )
        cache_fd = CampaignIO._open_directory(
            expected, label="planner cache", root=REPO
        )
        opened = os.fstat(cache_fd)
        entry = os.stat(
            expected.name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (
            not stat.S_ISDIR(opened.st_mode)
            or not stat.S_ISDIR(entry.st_mode)
            or (opened.st_dev, opened.st_ino) != (entry.st_dev, entry.st_ino)
        ):
            raise PlannerManifestError("planner cache identity changed")
        attestation = cache.attest()
        sentinel_path = expected / "build_successful"
        _, sentinel = SafeIO.read_canonical_json(
            sentinel_path,
            label="planner cache sentinel",
            expected_path=sentinel_path,
            root=REPO,
            canonical_json_line=P.canonical_json_line,
        )
        binary_paths = {
            "downward_sha256": expected / "builds/release_no_lp/bin/downward",
            "preprocess_sha256": expected / "builds/release_no_lp/bin/preprocess",
        }
        for field, path in binary_paths.items():
            regular = SafeIO.read_regular_file(
                path, label=field, expected_path=path, root=REPO
            )
            if regular.sha256 != attestation[field]:
                raise PlannerManifestError("{} changed".format(field))
        after = os.fstat(cache_fd)
        entry_after = os.stat(
            expected.name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (
            (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
            or (entry_after.st_dev, entry_after.st_ino)
            != (opened.st_dev, opened.st_ino)
        ):
            raise PlannerManifestError("planner cache changed during attestation")
    except (
        OSError, JJ.JjCacheError, SafeIO.SafeReadError,
        CampaignIO.CampaignIOError,
    ) as err:
        raise PlannerManifestError("planner cache attestation failed") from err
    finally:
        if cache_fd is not None:
            os.close(cache_fd)
        if parent_fd is not None:
            os.close(parent_fd)
    if sentinel != attestation:
        raise PlannerManifestError("planner cache sentinel changed")
    return attestation


def derive_manifest() -> dict:
    try:
        if JJ.resolve_pinned_commit(REPO, PLANNER_REVISION) != PLANNER_REVISION:
            raise PlannerManifestError("planner revision changed")
        JJ.require_ancestor(
            REPO, P.REQUIRED_SELECTOR_COMMIT, PLANNER_REVISION
        )
        cache = JJ.JjCachedFastDownwardRevision(
            REVISION_CACHE, REPO, PLANNER_REVISION, list(P.BUILD_OPTIONS)
        )
        attestation = _attest_exact_cache(cache)
        driver_sha256 = JJ.tracked_file_sha256(
            REPO, PLANNER_REVISION, "fast-downward.py"
        )
    except JJ.JjCacheError as err:
        raise PlannerManifestError("planner revision attestation failed") from err

    manifest = {
        "schema": P.PLANNER_MANIFEST_SCHEMA,
        "revision": PLANNER_REVISION,
        "selector_base_revision": P.REQUIRED_SELECTOR_COMMIT,
        "cache_name": cache.name,
        "downward_sha256": attestation["downward_sha256"],
        "preprocess_sha256": attestation["preprocess_sha256"],
        "tree_manifest_sha256": attestation["tree_manifest_sha256"],
        "build_options": list(P.BUILD_OPTIONS),
        "driver_path": "fast-downward.py",
        "driver_sha256": driver_sha256,
        "downward_path": "builds/release_no_lp/bin/downward",
        "preprocess_path": "builds/release_no_lp/bin/preprocess",
        "option_matrix_sha256": P.option_matrix_digest(),
        "searches": [
            {"mode": mode, "search": P.SEARCHES[mode]} for mode in P.MODES
        ],
        "dual_trace_schema": P.DUAL_TRACE_SCHEMA,
    }
    try:
        P.validate_planner_manifest(manifest)
    except P.ProtocolError as err:
        raise PlannerManifestError("derived planner manifest is invalid") from err
    return manifest


def _read_and_match(expected: dict) -> dict:
    try:
        _, actual = CampaignIO.read_canonical_exact(
            MANIFEST_PATH,
            expected=MANIFEST_PATH,
            label="planner manifest",
            canonical_json_line=P.canonical_json_line,
        )
        P.validate_planner_manifest(actual)
    except (CampaignIO.CampaignIOError, P.ProtocolError) as err:
        raise PlannerManifestError("planner manifest verification failed") from err
    if P.canonical_json_line(actual) != P.canonical_json_line(expected):
        raise PlannerManifestError("planner manifest differs from derived bytes")
    return actual


def produce_manifest() -> dict:
    manifest = derive_manifest()
    try:
        CampaignIO.write_canonical_exclusive(
            MANIFEST_PATH,
            manifest,
            expected=MANIFEST_PATH,
            root=REPO,
            label="planner manifest",
            canonical_json_line=P.canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise PlannerManifestError("planner manifest production failed") from err
    return _read_and_match(manifest)


def verify_manifest() -> dict:
    return _read_and_match(derive_manifest())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("produce", "verify"))
    args = parser.parse_args()
    manifest = (
        produce_manifest() if args.action == "produce" else verify_manifest()
    )
    print(hashlib.sha256(P.canonical_json_line(manifest)).hexdigest())


if __name__ == "__main__":
    main()
