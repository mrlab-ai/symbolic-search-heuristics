#!/usr/bin/env python3
"""Adversarial tests for the committed V9 snapshot reader."""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

import pdb_terminal_incidence_v9_snapshot_reader as S


REVISION = "a" * 40
OTHER_REVISION = "b" * 40
REPOSITORY = Path("/synthetic/v9-repository")


class FakeRunner:
    """Minimal deterministic stand-in that makes a live jj call impossible."""

    def __init__(
        self,
        files: dict[str, bytes],
        *,
        resolution_outputs: list[bytes] | None = None,
        listing: bytes | None = None,
        failed_shows: set[str] | None = None,
    ) -> None:
        self.files = files
        self.resolution_outputs = resolution_outputs
        self.listing = listing
        self.failed_shows = failed_shows or set()
        self.commands: list[list[str]] = []
        self.log_calls = 0

    def __call__(self, command: list[str], **kwargs: object):
        expected_prefix = [
            str(S.JJ_EXECUTABLE),
            "--no-pager",
            "--ignore-working-copy",
            "-R",
            str(REPOSITORY),
        ]
        if command[:len(expected_prefix)] != expected_prefix:
            raise AssertionError("unexpected jj command prefix: {!r}".format(command))
        if kwargs != {
            "cwd": REPOSITORY,
            "check": False,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
        }:
            raise AssertionError("unexpected runner options: {!r}".format(kwargs))
        self.commands.append(list(command))
        args = command[len(expected_prefix):]
        if args[:2] == ["log", "-r"]:
            if self.resolution_outputs is None:
                raw = (REVISION + "\t0\n").encode("ascii")
            else:
                if self.log_calls >= len(self.resolution_outputs):
                    raise AssertionError("unexpected extra revision resolution")
                raw = self.resolution_outputs[self.log_calls]
            self.log_calls += 1
            return subprocess.CompletedProcess(command, 0, raw, b"")
        if args[:2] == ["file", "list"]:
            if self.listing is None:
                requested = args[args.index("--") + 1:]
                raw = b"".join(
                    path.encode("ascii") + b"\tfile\n" for path in requested
                )
            else:
                raw = self.listing
            return subprocess.CompletedProcess(command, 0, raw, b"")
        if args[:2] == ["file", "show"]:
            path = args[-1]
            if path in self.failed_shows:
                return subprocess.CompletedProcess(
                    command, 1, b"partial bytes", b"object unavailable"
                )
            if path not in self.files:
                raise AssertionError("unexpected shown path: {!r}".format(path))
            return subprocess.CompletedProcess(command, 0, self.files[path], b"")
        raise AssertionError("unexpected jj operation: {!r}".format(args))


class SnapshotReaderTests(unittest.TestCase):
    def read(self, runner: FakeRunner, paths: list[str] | None = None):
        return S.read_committed_snapshot(
            REVISION,
            paths or ["experiments/one.py"],
            repository=REPOSITORY,
            runner=runner,
        )

    def test_seal_revision_is_required_and_must_be_exact_lower_hex(self):
        runner = FakeRunner({"experiments/one.py": b"one"})
        with self.assertRaises(TypeError):
            S.read_committed_snapshot(  # type: ignore[call-arg]
                paths=["experiments/one.py"], runner=runner
            )
        for revision in (
            None,
            "",
            "a" * 39,
            "a" * 41,
            "A" * 40,
            "g" * 40,
            "@",
        ):
            with self.subTest(revision=revision), self.assertRaises(
                S.SnapshotReaderError
            ):
                S.read_committed_snapshot(  # type: ignore[arg-type]
                    revision,
                    ["experiments/one.py"],
                    repository=REPOSITORY,
                    runner=runner,
                )
        self.assertEqual(runner.commands, [])

    def test_revision_must_resolve_once_without_conflict(self):
        cases = {
            "missing": b"",
            "ambiguous": (
                REVISION + "\t0\n" + OTHER_REVISION + "\t0\n"
            ).encode("ascii"),
            "changed identity": (OTHER_REVISION + "\t0\n").encode("ascii"),
            "conflict": (REVISION + "\t1\n").encode("ascii"),
            "malformed": (REVISION + "\n").encode("ascii"),
            "non-ASCII": b"\xff\n",
        }
        for label, output in cases.items():
            with self.subTest(label=label):
                runner = FakeRunner(
                    {"experiments/one.py": b"one"},
                    resolution_outputs=[output],
                )
                with self.assertRaises(S.SnapshotReaderError):
                    self.read(runner)
                self.assertEqual(len(runner.commands), 1)

    def test_revision_drift_after_reads_is_rejected(self):
        runner = FakeRunner(
            {"experiments/one.py": b"one"},
            resolution_outputs=[
                (REVISION + "\t0\n").encode("ascii"),
                (OTHER_REVISION + "\t0\n").encode("ascii"),
            ],
        )
        with self.assertRaises(S.SnapshotReaderError):
            self.read(runner)
        self.assertEqual(runner.log_calls, 2)

    def test_input_paths_reject_duplicates_and_ambiguous_syntax(self):
        runner = FakeRunner({"experiments/one.py": b"one"})
        invalid_paths = (
            [],
            ("experiments/one.py",),
            ["experiments/one.py", "experiments/one.py"],
            ["/experiments/one.py"],
            ["experiments/../one.py"],
            ["experiments//one.py"],
            ["experiments/*.py"],
            [".jj/store"],
            [".git/config"],
            ["experiments/one.py\nsecond"],
            [["experiments/one.py"]],
        )
        for paths in invalid_paths:
            with self.subTest(paths=paths), self.assertRaises(
                S.SnapshotReaderError
            ):
                S.read_committed_snapshot(  # type: ignore[arg-type]
                    REVISION,
                    paths,
                    repository=REPOSITORY,
                    runner=runner,
                )
        self.assertEqual(runner.commands, [])

    def test_listing_rejects_missing_duplicate_extra_and_non_file_entries(self):
        paths = ["experiments/one.py", "experiments/two.py"]
        cases = {
            "missing": b"experiments/one.py\tfile\n",
            "duplicate": (
                b"experiments/one.py\tfile\n"
                b"experiments/one.py\tfile\n"
                b"experiments/two.py\tfile\n"
            ),
            "extra": (
                b"experiments/one.py\tfile\n"
                b"experiments/two.py\tfile\n"
                b"experiments/three.py\tfile\n"
            ),
            "symlink": (
                b"experiments/one.py\tsymlink\n"
                b"experiments/two.py\tfile\n"
            ),
            "tree": (
                b"experiments/one.py\ttree\n"
                b"experiments/two.py\tfile\n"
            ),
            "malformed": (
                b"experiments/one.py\tfile\textra\n"
                b"experiments/two.py\tfile\n"
            ),
            "non-ASCII": b"experiments/one.py\tfile\n\xff",
        }
        files = {path: path.encode("ascii") for path in paths}
        for label, listing in cases.items():
            with self.subTest(label=label):
                runner = FakeRunner(files, listing=listing)
                with self.assertRaises(S.SnapshotReaderError):
                    self.read(runner, paths)
                self.assertEqual(len(runner.commands), 2)

    def test_file_show_failure_is_rejected_without_partial_bytes(self):
        path = "experiments/one.py"
        runner = FakeRunner({path: b"one"}, failed_shows={path})
        with self.assertRaisesRegex(
            S.SnapshotReaderError, "Jujutsu snapshot query failed"
        ):
            self.read(runner, [path])
        self.assertEqual(len(runner.commands), 3)

    def test_runner_os_error_and_invalid_result_are_wrapped(self):
        def os_error_runner(*_args: object, **_kwargs: object):
            raise OSError("unavailable")

        with self.assertRaises(S.SnapshotReaderError):
            S.read_committed_snapshot(
                REVISION,
                ["experiments/one.py"],
                repository=REPOSITORY,
                runner=os_error_runner,
            )

        def invalid_runner(*_args: object, **_kwargs: object):
            return object()

        with self.assertRaises(S.SnapshotReaderError):
            S.read_committed_snapshot(
                REVISION,
                ["experiments/one.py"],
                repository=REPOSITORY,
                runner=invalid_runner,
            )

    def test_exact_bytes_and_requested_order_are_preserved(self):
        paths = ["experiments/a.bin", "paper/main.tex"]
        files = {
            paths[0]: b"\x00\xff\r\nraw\x00",
            paths[1]: b"no final newline",
        }
        runner = FakeRunner(files)

        result = self.read(runner, paths)

        self.assertIs(type(result), dict)
        self.assertEqual(list(result), paths)
        self.assertEqual(result, files)
        self.assertTrue(all(type(value) is bytes for value in result.values()))
        self.assertEqual(runner.log_calls, 2)
        self.assertEqual(len(runner.commands), 5)
        operations = [command[5:7] for command in runner.commands]
        self.assertEqual(
            operations,
            [
                ["log", "-r"],
                ["file", "list"],
                ["file", "show"],
                ["file", "show"],
                ["log", "-r"],
            ],
        )
        for command in runner.commands:
            self.assertIn("--ignore-working-copy", command)
            self.assertNotIn("@", command)
            self.assertNotIn("@-", command)
        list_command = runner.commands[1]
        self.assertEqual(list_command[list_command.index("--") + 1:], paths)
        for command, path in zip(runner.commands[2:4], paths):
            self.assertEqual(command[-2:], ["--", path])


if __name__ == "__main__":
    unittest.main()
