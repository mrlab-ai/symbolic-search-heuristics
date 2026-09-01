#!/usr/bin/env python3

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import audit_pdb_terminal_incidence_confirmation_a as AuditA
import audit_pdb_terminal_incidence_confirmation_b as AuditB
import pdb_confirmation_run_cell as RunCell
import pdb_confirmation_safe_io as SafeIO
import recover_pdb_terminal_incidence_confirmation_a as RecoverA
import recover_pdb_terminal_incidence_confirmation_b as RecoverB


class SafeReaderTest(unittest.TestCase):
    def test_regular_read_hashes_the_same_descriptor(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input"
            path.write_bytes(b"stable\n")
            loaded = SafeIO.read_regular_file(path, label="test input")
        self.assertEqual(loaded.raw, b"stable\n")
        self.assertEqual(loaded.identity["size"], len(b"stable\n"))
        self.assertEqual(len(loaded.sha256), 64)

    def test_nonregular_entries_are_rejected_before_open_or_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular = root / "regular"
            regular.write_bytes(b"bytes")
            cases = {}
            cases["symlink"] = root / "link"
            cases["symlink"].symlink_to(regular)
            cases["directory"] = root / "directory"
            cases["directory"].mkdir()
            cases["fifo"] = root / "fifo"
            os.mkfifo(cases["fifo"])
            for name, path in cases.items():
                with self.subTest(kind=name), mock.patch.object(
                    SafeIO.os, "open", wraps=os.open
                ) as opened, mock.patch.object(
                    SafeIO.os, "read", wraps=os.read
                ) as read:
                    with self.assertRaises(SafeIO.SafeReadError):
                        SafeIO.read_regular_file(path, label=name)
                    opened.assert_not_called()
                    read.assert_not_called()

    def test_lexical_rejection_precedes_all_filesystem_io(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            SafeIO.os, "lstat", wraps=os.lstat
        ) as inspected:
            root = Path(tmp)
            with self.assertRaises(SafeIO.SafeReadError):
                SafeIO.read_regular_file(
                    root / "inside" / ".." / "outside", label="bad path",
                    root=root,
                )
            inspected.assert_not_called()

    def test_regular_to_fifo_race_cannot_block_or_reach_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input"
            path.write_bytes(b"before")
            real_open = os.open

            def race(candidate, flags, *args):
                Path(candidate).unlink()
                os.mkfifo(candidate)
                return real_open(candidate, flags, *args)

            with mock.patch.object(
                SafeIO.os, "open", side_effect=race
            ), mock.patch.object(SafeIO.os, "read", wraps=os.read) as read:
                with self.assertRaises(SafeIO.SafeReadError):
                    SafeIO.read_regular_file(path, label="raced input")
                read.assert_not_called()


class RunCellTest(unittest.TestCase):
    def _in_directory(self, directory):
        class WorkingDirectory:
            def __enter__(self_inner):
                self_inner.old = Path.cwd()
                os.chdir(directory)

            def __exit__(self_inner, *args):
                os.chdir(self_inner.old)
        return WorkingDirectory()

    def test_every_preexisting_dynamic_name_prevents_child_and_new_outputs(self):
        names = list(RecoverB.LegacyDynamic.names())
        with tempfile.TemporaryDirectory() as tmp, self._in_directory(tmp):
            for name in names:
                with self.subTest(name=name):
                    for candidate in names:
                        path = Path(candidate)
                        if path.exists() or path.is_symlink():
                            if path.is_dir():
                                path.rmdir()
                            else:
                                path.unlink()
                    Path(name).write_bytes(b"do-not-touch")
                    with mock.patch.object(RunCell.subprocess, "run") as child:
                        with self.assertRaises(RunCell.RunCellError):
                            RunCell.run_cell(
                                Path("/usr/bin/python3"), Path("run"),
                                Path("driver.log"), Path("driver.err"), names,
                            )
                        child.assert_not_called()
                    self.assertEqual(Path(name).read_bytes(), b"do-not-touch")
                    self.assertEqual(
                        {path.name for path in Path(".").iterdir()}, {name}
                    )

    def test_symlinked_driver_target_is_never_followed(self):
        names = list(RecoverA.LegacyDynamic.names())
        with tempfile.TemporaryDirectory() as tmp, self._in_directory(tmp):
            victim = Path("victim")
            victim.write_bytes(b"unchanged")
            Path("driver.log").symlink_to(victim)
            with mock.patch.object(RunCell.subprocess, "run") as child:
                with self.assertRaises(RunCell.RunCellError):
                    RunCell.run_cell(
                        Path("/usr/bin/python3"), Path("run"),
                        Path("driver.log"), Path("driver.err"), names,
                    )
                child.assert_not_called()
            self.assertEqual(victim.read_bytes(), b"unchanged")
            self.assertFalse(Path("driver.err").exists())

    def test_exclusive_creation_race_never_follows_injected_symlink(self):
        names = list(RecoverA.LegacyDynamic.names())
        with tempfile.TemporaryDirectory() as tmp, self._in_directory(tmp):
            victim = Path("victim")
            victim.write_bytes(b"unchanged")
            real_open = os.open

            def race(path, flags, *args):
                if Path(path) == Path("driver.log") and flags & os.O_CREAT:
                    Path(path).symlink_to(victim)
                return real_open(path, flags, *args)

            with mock.patch.object(
                RunCell.os, "open", side_effect=race
            ), mock.patch.object(RunCell.subprocess, "run") as child:
                with self.assertRaises(RunCell.RunCellError):
                    RunCell.run_cell(
                        Path("/usr/bin/python3"), Path("run"),
                        Path("driver.log"), Path("driver.err"), names,
                    )
                child.assert_not_called()
            self.assertEqual(victim.read_bytes(), b"unchanged")
            self.assertFalse(Path("driver.err").exists())


class RecoveryInventoryTest(unittest.TestCase):
    MODULES = ((RecoverA, AuditA), (RecoverB, AuditB))

    @staticmethod
    def _run_dir(root: Path) -> Path:
        path = root / "runs-00001-00100" / "00001"
        path.mkdir(parents=True)
        return path

    def test_every_dynamic_name_rejects_symlink_directory_and_fifo_without_read(self):
        for recover, audit in self.MODULES:
            for name in sorted(recover.LegacyDynamic.names()):
                for kind in ("dangling", "symlink", "directory", "fifo"):
                    with self.subTest(module=recover.__name__, name=name, kind=kind):
                        with tempfile.TemporaryDirectory() as tmp:
                            root = Path(tmp) / "experiment"
                            run_dir = self._run_dir(root)
                            source = run_dir / name
                            if kind == "dangling":
                                source.symlink_to(run_dir / "missing")
                            elif kind == "symlink":
                                victim = root / "victim"
                                victim.write_bytes(b"unchanged")
                                source.symlink_to(victim)
                            elif kind == "directory":
                                source.mkdir()
                            else:
                                os.mkfifo(source)
                            archive = Path(tmp) / "wave" / "interrupted-cell-files"
                            with mock.patch.object(
                                audit, "EXPERIMENT_PATH", root
                            ), mock.patch.object(
                                recover.subprocess, "run"
                            ) as sbatch, mock.patch.object(
                                SafeIO.os, "open", wraps=os.open
                            ) as opened:
                                with self.assertRaises(recover.RecoveryError):
                                    recover._archive_plan([1])
                                sbatch.assert_not_called()
                                opened.assert_not_called()
                            self.assertFalse(archive.exists())
                            if kind == "symlink":
                                self.assertEqual(victim.read_bytes(), b"unchanged")

    def test_driver_completeness_fifo_is_rejected_before_open_or_read(self):
        for audit in (AuditA, AuditB):
            with self.subTest(module=audit.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "experiment"
                run_dir = self._run_dir(root)
                os.mkfifo(run_dir / "driver.log")
                with mock.patch.object(
                    audit, "EXPERIMENT_PATH", root
                ), mock.patch.object(
                    audit, "EXPECTED_CELLS", 1
                ), mock.patch.object(
                    SafeIO.os, "open", wraps=os.open
                ) as opened, mock.patch.object(
                    SafeIO.os, "read", wraps=os.read
                ) as read:
                    with self.assertRaises(audit.ExecutionAuditError):
                        audit.cell_completeness()
                    opened.assert_not_called()
                    read.assert_not_called()

    def test_source_swap_and_archive_target_symlink_fail_before_unlink(self):
        for recover, audit in self.MODULES:
            with self.subTest(module=recover.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "experiment"
                run_dir = self._run_dir(root)
                source = run_dir / "driver.log"
                source.write_bytes(b"partial")
                wave = Path(tmp) / "wave"
                wave.mkdir()
                with mock.patch.object(audit, "EXPERIMENT_PATH", root):
                    plan = recover._archive_plan([1])
                    source.unlink()
                    victim = root / "victim"
                    victim.write_bytes(b"unchanged")
                    source.symlink_to(victim)
                    with mock.patch.object(recover.subprocess, "run") as sbatch:
                        with self.assertRaises(recover.RecoveryError):
                            recover._archive(plan, wave, [1])
                        sbatch.assert_not_called()
                    target = wave / plan[0]["target"]
                    self.assertFalse(target.exists() or target.is_symlink())
                    self.assertEqual(victim.read_bytes(), b"unchanged")

                    source.unlink()
                    source.write_bytes(b"partial")
                    plan = recover._archive_plan([1])
                    target.parent.mkdir(parents=True)
                    target.symlink_to(victim)
                    with self.assertRaises(recover.RecoveryError):
                        recover._archive(plan, wave, [1])
                    self.assertTrue(target.is_symlink())
                    self.assertEqual(source.read_bytes(), b"partial")
                    self.assertEqual(victim.read_bytes(), b"unchanged")

    def test_symlinked_archive_parent_is_never_followed(self):
        for recover, audit in self.MODULES:
            with self.subTest(module=recover.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "experiment"
                run_dir = self._run_dir(root)
                source = run_dir / "driver.log"
                source.write_bytes(b"partial")
                wave = Path(tmp) / "wave"
                wave.mkdir()
                victim_dir = Path(tmp) / "victim-directory"
                victim_dir.mkdir()
                (wave / "interrupted-cell-files").symlink_to(victim_dir)
                with mock.patch.object(audit, "EXPERIMENT_PATH", root):
                    plan = recover._archive_plan([1])
                    with self.assertRaises(recover.RecoveryError):
                        recover._archive(plan, wave, [1])
                self.assertEqual(source.read_bytes(), b"partial")
                self.assertEqual(list(victim_dir.iterdir()), [])

    def test_archive_auditors_reject_every_nonregular_target_before_read(self):
        for audit in (AuditA, AuditB):
            for kind in ("symlink", "directory", "fifo"):
                with self.subTest(module=audit.__name__, kind=kind):
                    with tempfile.TemporaryDirectory() as tmp:
                        wave = Path(tmp) / "wave-0001"
                        target = wave / "interrupted-cell-files/00001/driver.log"
                        target.parent.mkdir(parents=True)
                        if kind == "symlink":
                            victim = Path(tmp) / "victim"
                            victim.write_bytes(b"unchanged")
                            target.symlink_to(victim)
                        elif kind == "directory":
                            target.mkdir()
                        else:
                            os.mkfifo(target)
                        item = {
                            "run_id": 1,
                            "name": "driver.log",
                            "source": "runs-00001-00100/00001/driver.log",
                            "target": "interrupted-cell-files/00001/driver.log",
                            "size": 1,
                            "sha256": "0" * 64,
                            "identity": {
                                "device": 1, "inode": 1, "mode": 0o100600,
                                "size": 1, "mtime_ns": 1,
                            },
                        }
                        with mock.patch.object(
                            audit, "EXPECTED_CELLS", 3
                        ), mock.patch.object(
                            SafeIO.os, "open", wraps=os.open
                        ) as opened:
                            with self.assertRaises(audit.ExecutionAuditError):
                                audit._validate_archive(wave, [item], [1])
                            opened.assert_not_called()
                        if kind == "symlink":
                            self.assertEqual(victim.read_bytes(), b"unchanged")

    def test_archive_auditors_require_the_exact_target_tree(self):
        for audit in (AuditA, AuditB):
            with self.subTest(module=audit.__name__), tempfile.TemporaryDirectory() as tmp:
                wave = Path(tmp) / "wave-0001"
                target = wave / "interrupted-cell-files/00001/driver.log"
                target.parent.mkdir(parents=True)
                target.write_bytes(b"partial")
                loaded = SafeIO.read_regular_file(target, label="test archive")
                item = {
                    "run_id": 1,
                    "name": "driver.log",
                    "source": "runs-00001-00100/00001/driver.log",
                    "target": "interrupted-cell-files/00001/driver.log",
                    "size": loaded.identity["size"],
                    "sha256": loaded.sha256,
                    "identity": loaded.identity,
                }
                with mock.patch.object(audit, "EXPECTED_CELLS", 3):
                    audit._validate_archive(wave, [item], [1])
                (target.parent / "extra").write_bytes(b"unexpected")
                with mock.patch.object(
                    audit, "EXPECTED_CELLS", 3
                ), self.assertRaisesRegex(
                    audit.ExecutionAuditError, "archive tree changed"
                ):
                    audit._validate_archive(wave, [item], [1])

    def test_post_archive_rescan_detects_reappearing_dynamic_entry(self):
        for recover, audit in self.MODULES:
            with self.subTest(module=recover.__name__), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "experiment"
                run_dir = self._run_dir(root)
                (run_dir / "driver.log").write_bytes(b"partial")
                wave = Path(tmp) / "wave"
                wave.mkdir()
                real_assert = recover._assert_cells_clean

                def inject(cells):
                    (run_dir / "run.err").write_bytes(b"raced")
                    return real_assert(cells)

                with mock.patch.object(
                    audit, "EXPERIMENT_PATH", root
                ), mock.patch.object(
                    recover, "_assert_cells_clean", side_effect=inject
                ), mock.patch.object(recover.subprocess, "run") as sbatch:
                    plan = recover._archive_plan([1])
                    with self.assertRaises(recover.RecoveryError):
                        recover._archive(plan, wave, [1])
                    sbatch.assert_not_called()
                self.assertTrue((wave / plan[0]["target"]).is_file())
                self.assertEqual((run_dir / "run.err").read_bytes(), b"raced")

    def test_launch_rescan_race_prevents_sbatch(self):
        for recover, audit in self.MODULES:
            with self.subTest(module=recover.__name__), tempfile.TemporaryDirectory() as tmp:
                wave = Path(tmp) / "wave-0001"
                common = {
                    "slurm_stdin_sha256": "0" * 64,
                    "slurm_stdin_bytes": 3,
                    "submit_command": ["/usr/bin/sbatch", "--parsable"],
                }
                plan = {
                    "tasks": [1], "cells": [1, 2, 3],
                    "launch": {}, "source_rows": [],
                }
                with mock.patch.object(
                    recover, "recovery_plan", return_value=plan
                ), mock.patch.object(
                    recover, "_next_wave", return_value=(1, wave)
                ), mock.patch.object(
                    recover, "_common", return_value=common
                ), mock.patch.object(
                    recover, "_archive_plan", return_value=[]
                ), mock.patch.object(
                    recover, "_archive"
                ), mock.patch.object(
                    recover.Runner, "_submission_job_bytes", return_value=b"job"
                ), mock.patch.object(
                    recover.Runner, "_executable_identity"
                ), mock.patch.object(
                    recover, "_assert_cells_clean",
                    side_effect=recover.RecoveryError("injected race"),
                ), mock.patch.object(
                    recover.subprocess, "run"
                ) as sbatch:
                    with self.assertRaises(recover.RecoveryError):
                        recover.launch()
                    sbatch.assert_not_called()


if __name__ == "__main__":
    unittest.main()
