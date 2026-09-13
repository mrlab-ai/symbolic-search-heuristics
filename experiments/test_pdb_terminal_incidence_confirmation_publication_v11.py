#!/usr/bin/env python3
"""Tests for the V11 immutable shard publisher."""

import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock

import pdb_terminal_incidence_confirmation_publication_v11 as Publication


class ImmutableShardPublicationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="v11-publication-test-")
        self.root = Path(self.temporary.name)
        self.stage = self.root / "stage"
        self.final = self.root / "final"
        self.payloads = {
            "claim.json": b'{"claim":1}\n',
            "result.json": b'{"result":2}\n',
        }
        self.expectations = self._prepare_stage(self.payloads)
        self.metadata = {
            "campaign": "synthetic-v11",
            "claim_sha256": self.expectations["claim.json"].sha256,
            "logical_shard_index": 7,
            "schema": "synthetic/completion-metadata/v1",
        }

    def tearDown(self):
        self.temporary.cleanup()

    def _prepare_stage(self, payloads):
        self.stage.mkdir(mode=0o700)
        os.chmod(self.stage, 0o700)
        expectations = {}
        for name, payload in payloads.items():
            path = self.stage / name
            path.write_bytes(payload)
            os.chmod(path, 0o400)
            expectations[name] = Publication.FileExpectation(
                hashlib.sha256(payload).hexdigest(), 0o400
            )
        return expectations

    def _publish(self):
        return Publication.publish_immutable_shard(
            self.stage, self.final, self.expectations, self.metadata
        )

    def test_success_links_exact_payload_and_removes_stage(self):
        source_inodes = {
            name: (self.stage / name).stat().st_ino for name in self.payloads
        }
        receipt = self._publish()
        self.assertFalse(self.stage.exists())
        self.assertEqual(
            set(os.listdir(self.final)),
            set(self.payloads) | {Publication.COMPLETION_NAME},
        )
        self.assertEqual(stat.S_IMODE(self.final.stat().st_mode), 0o500)
        for name, payload in self.payloads.items():
            published = self.final / name
            self.assertEqual(published.read_bytes(), payload)
            self.assertEqual(published.stat().st_ino, source_inodes[name])
            self.assertEqual(published.stat().st_nlink, 1)
            self.assertEqual(stat.S_IMODE(published.stat().st_mode), 0o400)
        marker = (self.final / Publication.COMPLETION_NAME).read_bytes()
        self.assertEqual(
            receipt.completion_sha256, hashlib.sha256(marker).hexdigest()
        )
        self.assertEqual(receipt.completion, json.loads(marker))
        self.assertEqual(
            receipt.final_directory_identity.inode, self.final.stat().st_ino
        )

    def test_stage_parent_is_fsynced_after_stage_removal(self):
        real_fsync = os.fsync
        real_rmdir = os.rmdir
        stage_removed = False
        fsyncs_after_removal = 0

        def tracked_rmdir(*args, **kwargs):
            nonlocal stage_removed
            result = real_rmdir(*args, **kwargs)
            stage_removed = True
            return result

        def tracked_fsync(fd):
            nonlocal fsyncs_after_removal
            if stage_removed:
                fsyncs_after_removal += 1
            return real_fsync(fd)

        with (
            mock.patch.object(Publication.os, "rmdir", side_effect=tracked_rmdir),
            mock.patch.object(Publication.os, "fsync", side_effect=tracked_fsync),
        ):
            self._publish()
        self.assertTrue(stage_removed)
        self.assertEqual(fsyncs_after_removal, 2)

    def test_existing_final_is_never_reused(self):
        self.final.mkdir()
        sentinel = self.final / "sentinel"
        sentinel.write_bytes(b"keep")
        with self.assertRaisesRegex(Publication.PublicationError, "refusing to reuse"):
            self._publish()
        self.assertEqual(sentinel.read_bytes(), b"keep")
        self.assertTrue(self.stage.is_dir())

    def test_symlink_payload_is_rejected_before_final_claim(self):
        (self.stage / "claim.json").unlink()
        (self.stage / "claim.json").symlink_to("result.json")
        with self.assertRaises(Publication.PublicationError):
            self._publish()
        self.assertFalse(os.path.lexists(self.final))

    def test_nonregular_payload_is_rejected_before_final_claim(self):
        (self.stage / "claim.json").unlink()
        os.mkfifo(self.stage / "claim.json", mode=0o400)
        with self.assertRaises(Publication.PublicationError):
            self._publish()
        self.assertFalse(os.path.lexists(self.final))

    def test_extra_and_missing_payloads_are_rejected_before_claim(self):
        (self.stage / "extra").write_bytes(b"extra")
        with self.assertRaisesRegex(Publication.PublicationError, "closure"):
            self._publish()
        self.assertFalse(os.path.lexists(self.final))
        (self.stage / "extra").unlink()
        (self.stage / "result.json").unlink()
        with self.assertRaisesRegex(Publication.PublicationError, "closure"):
            self._publish()
        self.assertFalse(os.path.lexists(self.final))

    def test_stage_mutation_after_first_link_fails_without_marker(self):
        real_link = os.link
        calls = []

        def link_then_mutate(*args, **kwargs):
            result = real_link(*args, **kwargs)
            calls.append(args[0])
            if len(calls) == 1:
                changed = self.stage / args[0]
                os.chmod(changed, 0o600)
                changed.write_bytes(b"mutated after link\n")
                os.chmod(changed, 0o400)
            return result

        with mock.patch.object(Publication.os, "link", side_effect=link_then_mutate):
            with self.assertRaisesRegex(
                Publication.PublicationError, "immutable manifest"
            ):
                self._publish()
        self.assertTrue(self.final.is_dir())
        self.assertFalse(os.path.lexists(self.final / Publication.COMPLETION_NAME))
        self.assertTrue(self.stage.is_dir())

    def test_preexisting_hardlink_is_rejected(self):
        alias = self.root / "claim-alias"
        os.link(self.stage / "claim.json", alias)
        with self.assertRaisesRegex(Publication.PublicationError, "manifest"):
            self._publish()
        self.assertFalse(os.path.lexists(self.final))

    def test_injected_publish_collision_leaves_claim_without_marker(self):
        real_link = os.link
        injected = False

        def collide(source, target, **kwargs):
            nonlocal injected
            if not injected:
                injected = True
                collision_fd = os.open(
                    target,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o400,
                    dir_fd=kwargs["dst_dir_fd"],
                )
                os.close(collision_fd)
            return real_link(source, target, **kwargs)

        with mock.patch.object(Publication.os, "link", side_effect=collide):
            with self.assertRaisesRegex(
                Publication.PublicationError, "exclusively publish"
            ):
                self._publish()
        self.assertTrue(self.final.is_dir())
        self.assertFalse(os.path.lexists(self.final / Publication.COMPLETION_NAME))

    def test_injected_partial_marker_write_never_exposes_completion_name(self):
        def partial_write(fd, _payload):
            os.write(fd, b"partial")
            raise OSError("injected")

        with mock.patch.object(
            Publication, "_write_all", side_effect=partial_write
        ):
            with self.assertRaisesRegex(
                Publication.PublicationError, "completion marker"
            ):
                self._publish()
        self.assertTrue(self.final.is_dir())
        self.assertFalse(os.path.lexists(self.final / Publication.COMPLETION_NAME))
        self.assertEqual(
            (self.final / Publication.COMPLETION_TEMP_NAME).read_bytes(), b"partial"
        )
        self.assertTrue(self.stage.is_dir())

    def test_completion_marker_has_exact_canonical_bytes(self):
        receipt = self._publish()
        expected = Publication.canonical_json_bytes(receipt.completion)
        observed = (self.final / Publication.COMPLETION_NAME).read_bytes()
        self.assertEqual(observed, expected)
        self.assertEqual(observed[-1:], b"\n")
        self.assertNotIn(b" ", observed)
        self.assertEqual(
            receipt.completion["final_directory"]["mode"], "0500"
        )
        self.assertEqual(
            [entry["name"] for entry in receipt.completion["files"]],
            sorted(self.payloads),
        )

    def test_second_invocation_refuses_completed_final(self):
        self._publish()
        second_stage = self.root / "stage-2"
        self.stage = second_stage
        self.expectations = self._prepare_stage(self.payloads)
        with self.assertRaisesRegex(Publication.PublicationError, "refusing to reuse"):
            self._publish()
        self.assertTrue(second_stage.is_dir())


class LustreWorkspaceIntegrationTest(unittest.TestCase):
    def test_workspace_hardlink_publication_and_exact_cleanup(self):
        workspace = Path(__file__).resolve().parent
        root = Path(tempfile.mkdtemp(prefix=".v11-publisher-integration-", dir=workspace))
        stage = root / "private-stage"
        final = root / "published"
        payload_name = "probe.bin"

        def cleanup_exact():
            if final.is_dir() and not final.is_symlink():
                os.chmod(final, 0o700)
                for name in (payload_name, Publication.COMPLETION_NAME):
                    path = final / name
                    if os.path.lexists(path):
                        path.unlink()
                final.rmdir()
            if stage.is_dir() and not stage.is_symlink():
                path = stage / payload_name
                if os.path.lexists(path):
                    path.unlink()
                stage.rmdir()
            if root.is_dir() and not root.is_symlink():
                root.rmdir()

        self.addCleanup(cleanup_exact)
        stage.mkdir(mode=0o700)
        os.chmod(stage, 0o700)
        payload = b"same-filesystem Lustre publication probe\n"
        staged_file = stage / payload_name
        staged_file.write_bytes(payload)
        os.chmod(staged_file, 0o400)
        source_identity = (staged_file.stat().st_dev, staged_file.stat().st_ino)
        expectation = Publication.FileExpectation(
            hashlib.sha256(payload).hexdigest(), 0o400
        )
        receipt = Publication.publish_immutable_shard(
            stage,
            final,
            {payload_name: expectation},
            {"schema": "workspace-lustre-integration/v1"},
        )
        published = final / payload_name
        self.assertEqual(
            (published.stat().st_dev, published.stat().st_ino), source_identity
        )
        self.assertEqual(receipt.final_dir, final)
        self.assertFalse(stage.exists())


if __name__ == "__main__":
    unittest.main()
