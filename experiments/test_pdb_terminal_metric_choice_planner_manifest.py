#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import jj_cached_revision as JJ
import pdb_terminal_metric_choice_planner_manifest as M
import pdb_terminal_metric_choice_protocol as P


def fake_manifest():
    return {
        "schema": P.PLANNER_MANIFEST_SCHEMA,
        "revision": M.PLANNER_REVISION,
        "selector_base_revision": P.REQUIRED_SELECTOR_COMMIT,
        "cache_name": "exact-cache",
        "downward_sha256": "1" * 64,
        "preprocess_sha256": "2" * 64,
        "tree_manifest_sha256": "3" * 64,
        "build_options": list(P.BUILD_OPTIONS),
        "driver_path": "fast-downward.py",
        "driver_sha256": "4" * 64,
        "downward_path": "builds/release_no_lp/bin/downward",
        "preprocess_path": "builds/release_no_lp/bin/preprocess",
        "option_matrix_sha256": P.option_matrix_digest(),
        "searches": [
            {"mode": mode, "search": P.SEARCHES[mode]} for mode in P.MODES
        ],
        "dual_trace_schema": P.DUAL_TRACE_SCHEMA,
    }


class FakeCache:
    def __init__(self, path, name, attestation):
        self.path = path
        self.name = name
        self._attestation = attestation

    def attest(self):
        return self._attestation


class PlannerManifestTest(unittest.TestCase):
    def test_derivation_rejects_revision_or_ancestry_failure(self):
        with mock.patch.object(
            M.JJ, "resolve_pinned_commit", return_value="0" * 40
        ):
            with self.assertRaises(M.PlannerManifestError):
                M.derive_manifest()
        with mock.patch.object(
            M.JJ, "resolve_pinned_commit", return_value=M.PLANNER_REVISION
        ), mock.patch.object(
            M.JJ, "require_ancestor", side_effect=JJ.JjCacheError("not ancestor")
        ):
            with self.assertRaises(M.PlannerManifestError):
                M.derive_manifest()

    def test_derivation_binds_revision_ancestry_cache_driver_and_options(self):
        expected = fake_manifest()
        cache = mock.Mock(name=expected["cache_name"])
        cache.name = expected["cache_name"]
        with mock.patch.object(
            M.JJ, "resolve_pinned_commit", return_value=M.PLANNER_REVISION
        ) as resolve, mock.patch.object(
            M.JJ, "require_ancestor"
        ) as ancestor, mock.patch.object(
            M.JJ, "JjCachedFastDownwardRevision", return_value=cache
        ), mock.patch.object(
            M, "_attest_exact_cache", return_value={
                "downward_sha256": expected["downward_sha256"],
                "preprocess_sha256": expected["preprocess_sha256"],
                "tree_manifest_sha256": expected["tree_manifest_sha256"],
            }
        ), mock.patch.object(
            M.JJ, "tracked_file_sha256", return_value=expected["driver_sha256"]
        ) as driver:
            self.assertEqual(M.derive_manifest(), expected)
        resolve.assert_called_once_with(M.REPO, M.PLANNER_REVISION)
        ancestor.assert_called_once_with(
            M.REPO, P.REQUIRED_SELECTOR_COMMIT, M.PLANNER_REVISION
        )
        driver.assert_called_once_with(
            M.REPO, M.PLANNER_REVISION, "fast-downward.py"
        )

    def test_exact_cache_rechecks_sentinel_and_binary_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache_root = root / "revision-cache"
            cache_path = cache_root / "exact-cache"
            binary = cache_path / "builds/release_no_lp/bin/downward"
            preprocess = cache_path / "builds/release_no_lp/bin/preprocess"
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"downward")
            preprocess.write_bytes(b"preprocess")
            attestation = {
                "protocol": JJ.EXPORT_PROTOCOL,
                "revision": M.PLANNER_REVISION,
                "tree_manifest_sha256": "3" * 64,
                "build_options": list(P.BUILD_OPTIONS),
                "downward_sha256": hashlib.sha256(b"downward").hexdigest(),
                "preprocess_sha256": hashlib.sha256(b"preprocess").hexdigest(),
            }
            (cache_path / "build_successful").write_bytes(
                P.canonical_json_line(attestation)
            )
            cache = FakeCache(cache_path, "exact-cache", attestation)
            with mock.patch.object(M, "REPO", root), mock.patch.object(
                M, "REVISION_CACHE", cache_root
            ):
                self.assertEqual(M._attest_exact_cache(cache), attestation)
                binary.write_bytes(b"changed")
                with self.assertRaises(M.PlannerManifestError):
                    M._attest_exact_cache(cache)

    def test_production_is_exclusive_and_verification_is_read_only(self):
        manifest = fake_manifest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "artifact/planner-manifest-v1.json"
            with mock.patch.object(M, "REPO", root), mock.patch.object(
                M, "MANIFEST_PATH", path
            ), mock.patch.object(M, "derive_manifest", return_value=manifest):
                self.assertEqual(M.produce_manifest(), manifest)
                before = (path.lstat().st_ino, path.read_bytes())
                with self.assertRaises(M.PlannerManifestError):
                    M.produce_manifest()
                self.assertEqual(M.verify_manifest(), manifest)
                self.assertEqual((path.lstat().st_ino, path.read_bytes()), before)

    def test_verification_rejects_canonical_mutation(self):
        manifest = fake_manifest()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "artifact/planner-manifest-v1.json"
            with mock.patch.object(M, "REPO", root), mock.patch.object(
                M, "MANIFEST_PATH", path
            ), mock.patch.object(M, "derive_manifest", return_value=manifest):
                M.produce_manifest()
                changed = copy.deepcopy(manifest)
                changed["downward_sha256"] = "f" * 64
                path.chmod(0o600)
                path.write_bytes(P.canonical_json_line(changed))
                path.chmod(0o400)
                with self.assertRaises(M.PlannerManifestError):
                    M.verify_manifest()


if __name__ == "__main__":
    unittest.main()
