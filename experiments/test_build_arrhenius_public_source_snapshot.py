#!/usr/bin/env python3
"""Stdlib tests for the analysis-only anonymous P4/P5 source snapshot."""

import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import build_arrhenius_public_source_snapshot as snapshot


class PublicSourceSnapshotTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = snapshot.build_snapshot_bytes()
        cls.files, cls.manifest, cls.oid_summary = snapshot.verify_snapshot_bytes(
            cls.archive
        )

    def assertSnapshotError(self, function, *args, **kwargs):
        with self.assertRaises(snapshot.SnapshotError):
            function(*args, **kwargs)

    def test_duplicate_builds_are_byte_identical_and_pinned(self):
        rebuilt = snapshot.build_snapshot_bytes()
        self.assertEqual(self.archive, rebuilt)
        self.assertEqual(len(rebuilt), snapshot.PUBLIC_ARCHIVE_IDENTITY.size)
        self.assertEqual(
            snapshot._sha256(rebuilt), snapshot.PUBLIC_ARCHIVE_IDENTITY.sha256
        )
        self.assertEqual(
            snapshot._content_sha256(), snapshot.PUBLIC_CONTENT_SHA256
        )

    def test_manifest_is_canonical_public_and_launch_disabled(self):
        raw = self.files[snapshot.MANIFEST_NAME]
        self.assertEqual(snapshot.canonical_json_bytes(self.manifest), raw)
        self.assertEqual(
            self.manifest["analysis"]["purpose"],
            "numerical-and-scientific-reanalysis-only",
        )
        self.assertEqual(
            self.manifest["launch_entry_points"]["status"],
            "intentionally-disabled",
        )
        self.assertIn(
            "not cryptographically unlinkable",
            self.manifest["historical_provenance"]["warning"],
        )
        self.assertIn(
            "must remain unpublished",
            self.manifest["historical_provenance"][
                "blind_review_requirement"
            ],
        )
        # Public MANIFEST.json omits the private audit commit/blob identities.
        forbidden = {
            snapshot.P4_ARTIFACT_FREEZE,
            snapshot.P5_ANALYSIS_FREEZE,
            *(entry.p5_blob_sha1 for entry in snapshot.SOURCE_ENTRIES),
            *(
                entry.p4_blob_sha1
                for entry in snapshot.SOURCE_ENTRIES
                if entry.p4_blob_sha1 is not None
            ),
        }
        for identity in forbidden:
            self.assertNotIn(identity.encode("ascii"), raw)

    def test_exact_private_token_and_oid_inventories(self):
        snapshot._scan_private_tokens(self.files)
        self.assertEqual(
            self.oid_summary,
            {
                "historical_occurrences": 30,
                "historical_unique": 6,
                "synthetic_occurrences": 7,
                "synthetic_unique": 4,
                "total_occurrences": 37,
                "total_unique": 10,
            },
        )

    def test_nonallowlisted_source_byte_change_is_rejected(self):
        target = "experiments/analyze_arrhenius_selector_validation.py"

        def changed_loader(revision, path):
            raw, mode, blob = snapshot._git_source(revision, path)
            if revision == snapshot.P5_ANALYSIS_FREEZE and path == target:
                raw += b"\n# unreviewed source byte\n"
            return raw, mode, blob

        self.assertSnapshotError(
            snapshot._build_public_payloads, changed_loader
        )

    def test_extra_private_token_occurrence_is_rejected(self):
        changed = dict(self.files)
        target = "experiments/analyze_ms_caps_pilot.py"
        changed[target] += b"\nowner=jendrik\n"
        self.assertSnapshotError(snapshot._scan_private_tokens, changed)

        original = snapshot._git_source(
            snapshot.P5_ANALYSIS_FREEZE,
            "experiments/analyze_arrhenius_selector_pilot.py",
        )[0]
        original += b"\nnaiss2025-5-561-cpu\n"
        self.assertSnapshotError(
            snapshot._apply_rewrites,
            "experiments/analyze_arrhenius_selector_pilot.py",
            original,
        )

    def test_extra_revision_identity_is_rejected(self):
        changed = dict(self.files)
        target = "experiments/analyze_ms_caps_pilot.py"
        changed[target] += b"\n1111111111111111111111111111111111111111\n"
        self.assertSnapshotError(snapshot._scan_oid_inventory, changed)

    def test_archive_contains_only_regular_files_and_directories(self):
        names = []
        with tarfile.open(fileobj=io.BytesIO(self.archive), mode="r:") as archive:
            for member in archive:
                names.append(member.name)
                self.assertTrue(member.isdir() or member.isreg())
                self.assertFalse(member.issym())
                self.assertFalse(member.islnk())
                self.assertEqual(member.linkname, "")
                self.assertEqual(member.uid, 0)
                self.assertEqual(member.gid, 0)
                self.assertEqual(member.mtime, 0)
        lowered = "\n".join(names).lower()
        self.assertNotIn("/.git", lowered)
        self.assertNotIn("__pycache__", lowered)
        self.assertNotIn(".pyc", lowered)

    def _forbidden_member_archive(self, name, member_type, linkname=""):
        output = io.BytesIO()
        with tarfile.open(
            fileobj=output, mode="w", format=tarfile.USTAR_FORMAT
        ) as archive:
            root = snapshot._tar_info(
                snapshot.SNAPSHOT_ROOT, mode=0o755, directory=True
            )
            archive.addfile(root)
            info = snapshot._tar_info(name, mode=0o644, size=0)
            info.type = member_type
            info.linkname = linkname
            archive.addfile(info, io.BytesIO(b""))
        return output.getvalue()

    def test_symlink_hardlink_git_and_bytecode_members_are_rejected(self):
        cases = (
            (
                snapshot.SNAPSHOT_ROOT + "/linked",
                tarfile.SYMTYPE,
                "target",
            ),
            (
                snapshot.SNAPSHOT_ROOT + "/hardlinked",
                tarfile.LNKTYPE,
                "target",
            ),
            (
                snapshot.SNAPSHOT_ROOT + "/.git/config",
                tarfile.REGTYPE,
                "",
            ),
            (
                snapshot.SNAPSHOT_ROOT + "/experiments/__pycache__/x.pyc",
                tarfile.REGTYPE,
                "",
            ),
        )
        for name, member_type, linkname in cases:
            with self.subTest(name=name):
                raw = self._forbidden_member_archive(
                    name, member_type, linkname
                )
                self.assertSnapshotError(
                    snapshot.verify_snapshot_bytes,
                    raw,
                    enforce_archive_identity=False,
                )

    def test_changed_manifest_or_archive_byte_is_rejected(self):
        changed = bytearray(self.archive)
        changed[1024] ^= 1
        self.assertSnapshotError(
            snapshot.verify_snapshot_bytes, bytes(changed)
        )
        duplicate = b'{"schema":1,"schema":2}\n'
        self.assertSnapshotError(
            snapshot.parse_json_bytes, duplicate, "duplicate manifest"
        )

    def test_build_writes_new_single_link_archive_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.tar"
            second = Path(directory) / "second.tar"
            snapshot.build_snapshot_file(first)
            snapshot.build_snapshot_file(second)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first.stat().st_nlink, 1)
            self.assertEqual(stat_mode(first), 0o644)
            self.assertSnapshotError(snapshot.build_snapshot_file, first)

    def test_stable_read_rejects_symlink_and_hardlink_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "snapshot.tar"
            path.write_bytes(self.archive)
            link = root / "link.tar"
            link.symlink_to(path)
            self.assertSnapshotError(
                snapshot.stable_read,
                link,
                identity=snapshot.PUBLIC_ARCHIVE_IDENTITY,
            )
            hardlink = root / "hardlink.tar"
            os.link(path, hardlink)
            self.assertSnapshotError(
                snapshot.stable_read,
                path,
                identity=snapshot.PUBLIC_ARCHIVE_IDENTITY,
            )
            self.assertSnapshotError(
                snapshot.stable_read,
                hardlink,
                identity=snapshot.PUBLIC_ARCHIVE_IDENTITY,
            )

    def test_stage_revision_binding_and_runner_entrypoint_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = snapshot._materialize(self.files, directory)
            experiments = root / "experiments"
            code = (
                "import sys;sys.path.insert(0,{!r});"
                "import exp_arrhenius_common as common;print(common.REV)"
            ).format(str(experiments))
            expected = {
                "p4": "d6d98ad42f3976cd5cf0c9b17d8fa255354fbfbf",
                "p5": "a52488637a1c054b26dac93fe2eb1a556110a2dd",
            }
            for stage, revision in expected.items():
                with self.subTest(stage=stage):
                    result = subprocess.run(
                        [sys.executable, "-I", "-c", code],
                        check=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env={
                            "PYTHONDONTWRITEBYTECODE": "1",
                            "WBH_PUBLIC_ANALYSIS_STAGE": stage,
                        },
                    )
                    self.assertEqual(result.stdout, (revision + "\n").encode())
                    self.assertEqual(result.stderr, b"")
            runner = experiments / "exp_arrhenius_selector_pilot.py"
            result = subprocess.run(
                [sys.executable, str(runner), "--self-test"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "WBH_PUBLIC_ANALYSIS_STAGE": "p4",
                },
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"runner entry point disabled", result.stderr)

            analyzer = experiments / "analyze_arrhenius_selector_pilot.py"
            result = subprocess.run(
                [sys.executable, str(analyzer)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    "PYTHONDONTWRITEBYTECODE": "1",
                    "WBH_PUBLIC_ANALYSIS_STAGE": "p5",
                },
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn(b"requires p4 analysis stage", result.stderr)

    def test_self_test(self):
        result = snapshot.self_test()
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["files"], 18)


def stat_mode(path):
    return path.stat().st_mode & 0o777


if __name__ == "__main__":
    unittest.main()
