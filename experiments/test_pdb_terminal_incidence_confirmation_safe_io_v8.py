#!/usr/bin/env python3
"""Adversarial tests for V8's retained-descriptor sbatch captures."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pdb_terminal_incidence_confirmation_safe_io_v8 as SafeIO


class RetainedCaptureV8Test(unittest.TestCase):
    @staticmethod
    def _paths(root: Path) -> tuple[Path, Path]:
        directory = root / "capture"
        return directory / "stdout.bin", directory / "stderr.bin"

    def test_sealed_preintent_descriptors_capture_arbitrary_binary(self):
        stdout_raw = bytes(range(256)) + b"\x00\xffstdout"
        stderr_raw = b"\xff\x00stderr" + bytes(reversed(range(256)))
        with tempfile.TemporaryDirectory(prefix="v8-capture-") as tmp:
            root = Path(tmp)
            stdout_path, stderr_path = self._paths(root)
            with SafeIO.open_exclusive_capture_pair(
                stdout_path, stderr_path, root=root, label="fixture"
            ) as captures:
                for stream, path in (
                    ("stdout", stdout_path), ("stderr", stderr_path)
                ):
                    identity = captures.initial_identities[stream]
                    current = path.stat()
                    self.assertEqual(stat.S_IMODE(current.st_mode), 0o400)
                    self.assertEqual(current.st_nlink, 1)
                    self.assertEqual(identity["mode"], "0400")
                    self.assertEqual(identity["bytes_at_intent"], 0)
                    self.assertEqual(identity["device"], current.st_dev)
                    self.assertEqual(identity["inode"], current.st_ino)

                completed = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import os;"
                            "os.write(1,bytes.fromhex(%r));"
                            "os.write(2,bytes.fromhex(%r))"
                        ) % (stdout_raw.hex(), stderr_raw.hex()),
                    ],
                    stdout=captures.stdout_fd,
                    stderr=captures.stderr_fd,
                    check=False,
                )
                self.assertEqual(completed.returncode, 0)
                self.assertIsNone(completed.stdout)
                self.assertIsNone(completed.stderr)
                records, payloads = captures.finalize()

            self.assertEqual(payloads, {
                "stdout": stdout_raw, "stderr": stderr_raw,
            })
            for stream, path, raw in (
                ("stdout", stdout_path, stdout_raw),
                ("stderr", stderr_path, stderr_raw),
            ):
                record = records[stream]
                self.assertEqual(record["sha256"], hashlib.sha256(raw).hexdigest())
                self.assertEqual(record["bytes"], len(raw))
                self.assertEqual(record["initial_identity"]["bytes_at_intent"], 0)
                self.assertEqual(record["final_identity"]["bytes"], len(raw))
                self.assertEqual(record["final_identity"]["mode"], "0400")
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o400)

    def test_pre_submit_collision_never_reuses_either_leaf(self):
        for collided_stream in ("stdout", "stderr"):
            with self.subTest(stream=collided_stream), tempfile.TemporaryDirectory(
                prefix="v8-collision-"
            ) as tmp:
                root = Path(tmp)
                stdout_path, stderr_path = self._paths(root)
                stdout_path.parent.mkdir(mode=0o700)
                collided = stdout_path if collided_stream == "stdout" else stderr_path
                collided.write_bytes(b"preexisting")
                with self.assertRaises(SafeIO.PublicationError):
                    SafeIO.open_exclusive_capture_pair(
                        stdout_path, stderr_path, root=root, label="fixture"
                    )
                self.assertEqual(collided.read_bytes(), b"preexisting")
                other = stderr_path if collided_stream == "stdout" else stdout_path
                self.assertFalse(other.exists())

    def test_crash_left_partial_capture_reopens_exact_intent_inodes(self):
        with tempfile.TemporaryDirectory(prefix="v8-crash-capture-") as tmp:
            root = Path(tmp)
            stdout_path, stderr_path = self._paths(root)
            captures = SafeIO.open_exclusive_capture_pair(
                stdout_path, stderr_path, root=root, label="fixture"
            )
            initial = captures.initial_identities
            os.write(captures.stdout_fd, b"12345\n")
            os.write(captures.stderr_fd, b"partial\x00diagnostic\xff")
            captures.close()  # Simulate controller death before result publication.

            with SafeIO.open_existing_capture_pair(
                stdout_path, stderr_path, initial,
                root=root, label="fixture recovery",
            ) as recovered:
                records, payloads = recovered.finalize()
            self.assertEqual(payloads["stdout"], b"12345\n")
            self.assertEqual(payloads["stderr"], b"partial\x00diagnostic\xff")
            self.assertEqual(records["stdout"]["initial_identity"], initial["stdout"])
            self.assertEqual(records["stderr"]["initial_identity"], initial["stderr"])

    def test_recovery_rejects_a_still_live_inherited_writer(self):
        with tempfile.TemporaryDirectory(prefix="v8-live-writer-") as tmp:
            root = Path(tmp)
            stdout_path, stderr_path = self._paths(root)
            captures = SafeIO.open_exclusive_capture_pair(
                stdout_path, stderr_path, root=root, label="fixture"
            )
            initial = captures.initial_identities
            try:
                with self.assertRaisesRegex(
                    SafeIO.PublicationError, "retained writer"
                ):
                    SafeIO.open_existing_capture_pair(
                        stdout_path, stderr_path, initial,
                        root=root, label="concurrent recovery",
                    )
            finally:
                captures.close()
            with SafeIO.open_existing_capture_pair(
                stdout_path, stderr_path, initial,
                root=root, label="completed recovery",
            ) as recovered:
                _records, payloads = recovered.finalize()
            self.assertEqual(payloads, {"stdout": b"", "stderr": b""})

    def test_child_only_inherited_locks_block_recovery_until_exit(self):
        stdout_raw = b"child-only\x00stdout\xff"
        stderr_raw = b"\xffstderr\x00child-only"
        with tempfile.TemporaryDirectory(prefix="v8-child-lock-") as tmp:
            root = Path(tmp)
            stdout_path, stderr_path = self._paths(root)
            captures = SafeIO.open_exclusive_capture_pair(
                stdout_path, stderr_path, root=root, label="fixture"
            )
            initial = captures.initial_identities
            ready_read, ready_write = os.pipe()
            release_read, release_write = os.pipe()
            process = None
            try:
                program = (
                    "import os,sys;"
                    "os.write(1,bytes.fromhex(sys.argv[3]));"
                    "os.write(2,bytes.fromhex(sys.argv[4]));"
                    "os.write(int(sys.argv[1]),b'R');"
                    "os.read(int(sys.argv[2]),1)"
                )
                process = subprocess.Popen(
                    [
                        sys.executable, "-c", program,
                        str(ready_write), str(release_read),
                        stdout_raw.hex(), stderr_raw.hex(),
                    ],
                    stdout=captures.stdout_fd,
                    stderr=captures.stderr_fd,
                    pass_fds=(ready_write, release_read),
                )
                os.close(ready_write)
                ready_write = -1
                os.close(release_read)
                release_read = -1
                self.assertEqual(os.read(ready_read, 1), b"R")

                # Simulate controller death: only the child now retains the
                # locked open descriptions used for stdout and stderr.
                captures.close()
                with self.assertRaisesRegex(
                    SafeIO.PublicationError, "retained writer"
                ):
                    SafeIO.open_existing_capture_pair(
                        stdout_path, stderr_path, initial,
                        root=root, label="concurrent recovery",
                    )

                os.write(release_write, b"G")
                os.close(release_write)
                release_write = -1
                self.assertEqual(process.wait(timeout=5), 0)
                with SafeIO.open_existing_capture_pair(
                    stdout_path, stderr_path, initial,
                    root=root, label="completed recovery",
                ) as recovered:
                    records, payloads = recovered.finalize()
                self.assertEqual(payloads, {
                    "stdout": stdout_raw, "stderr": stderr_raw,
                })
                self.assertEqual(records["stdout"]["bytes"], len(stdout_raw))
                self.assertEqual(records["stderr"]["bytes"], len(stderr_raw))
            finally:
                captures.close()
                for descriptor in (
                    ready_read, ready_write, release_read, release_write,
                ):
                    if descriptor >= 0:
                        os.close(descriptor)
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait(timeout=5)

    def test_path_inode_swap_is_rejected_through_retained_parent(self):
        with tempfile.TemporaryDirectory(prefix="v8-capture-swap-") as tmp:
            root = Path(tmp)
            stdout_path, stderr_path = self._paths(root)
            with SafeIO.open_exclusive_capture_pair(
                stdout_path, stderr_path, root=root, label="fixture"
            ) as captures:
                moved = stdout_path.with_name("moved.bin")
                stdout_path.rename(moved)
                descriptor = os.open(
                    stdout_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600,
                )
                try:
                    os.write(descriptor, b"replacement")
                    os.fchmod(descriptor, 0o400)
                finally:
                    os.close(descriptor)
                with self.assertRaises(SafeIO.PublicationError):
                    captures.finalize()

    def test_link_count_or_mode_change_is_rejected(self):
        for mutation in ("hard-link", "mode"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory(
                prefix="v8-capture-mutation-"
            ) as tmp:
                root = Path(tmp)
                stdout_path, stderr_path = self._paths(root)
                with SafeIO.open_exclusive_capture_pair(
                    stdout_path, stderr_path, root=root, label="fixture"
                ) as captures:
                    if mutation == "hard-link":
                        os.link(stdout_path, stdout_path.with_name("alias.bin"))
                    else:
                        os.chmod(stdout_path, 0o600)
                    with self.assertRaises(SafeIO.PublicationError):
                        captures.finalize()

    def test_missing_crash_leaf_fails_closed(self):
        with tempfile.TemporaryDirectory(prefix="v8-capture-missing-") as tmp:
            root = Path(tmp)
            stdout_path, stderr_path = self._paths(root)
            captures = SafeIO.open_exclusive_capture_pair(
                stdout_path, stderr_path, root=root, label="fixture"
            )
            initial = captures.initial_identities
            captures.close()
            stderr_path.unlink()
            with self.assertRaises(SafeIO.PublicationError):
                SafeIO.open_existing_capture_pair(
                    stdout_path, stderr_path, initial,
                    root=root, label="fixture recovery",
                )


if __name__ == "__main__":
    unittest.main()
