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


def hardware_raw(model="Synthetic CPU", architecture="x86_64"):
    return RunCell._canonical_json_line({
        "schema": RunCell.HARDWARE_ATTESTATION_SCHEMA,
        "processor_model": model,
        "architecture": architecture,
    })


class HardwareAttestationTest(unittest.TestCase):
    def test_cpuinfo_model_is_unique_normalized_and_minimal(self):
        value = RunCell.build_hardware_attestation(
            b"processor: 0\nmodel name :  Synthetic   CPU  \n"
            b"processor: 1\nmodel name: Synthetic CPU\n",
            "x86_64",
        )
        self.assertEqual(value, {
            "schema": RunCell.HARDWARE_ATTESTATION_SCHEMA,
            "processor_model": "Synthetic CPU",
            "architecture": "x86_64",
        })
        rendered = RunCell._canonical_json_line(value)
        self.assertNotIn(b"hostname", rendered)
        self.assertNotIn(b"memory", rendered)
        self.assertNotIn(b"processor:", rendered)

    def test_missing_mixed_or_nonascii_model_is_rejected(self):
        cases = (
            b"processor: 0\n",
            b"model name: CPU A\nmodel name: CPU B\n",
            b"model name: CPU \xff\n",
        )
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(
                RunCell.RunCellError
            ):
                RunCell.build_hardware_attestation(raw, "x86_64")

    def test_hardware_record_must_be_exact_canonical_json(self):
        self.assertEqual(
            RunCell.parse_hardware_attestation(hardware_raw())["processor_model"],
            "Synthetic CPU",
        )
        cases = (
            hardware_raw().rstrip(b"\n"),
            b'{"architecture":"x86_64", "processor_model":"Synthetic CPU",'
            b'"schema":"' + RunCell.HARDWARE_ATTESTATION_SCHEMA.encode("ascii")
            + b'"}\n',
            b'{"architecture":"x86_64","architecture":"x86_64",'
            b'"processor_model":"Synthetic CPU","schema":"'
            + RunCell.HARDWARE_ATTESTATION_SCHEMA.encode("ascii") + b'"}\n',
        )
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(
                RunCell.RunCellError
            ):
                RunCell.parse_hardware_attestation(raw)

    def test_ordered_summary_enforces_array_element_consistency(self):
        records = [
            (1, hardware_raw()), (2, hardware_raw()), (3, hardware_raw()),
            (4, hardware_raw("Other CPU", "aarch64")),
        ]
        summary = RunCell.summarize_hardware_records(
            records, [[1, 2, 3], [4]]
        )
        self.assertEqual(summary["hardware_attestation_files"], 4)
        self.assertEqual(summary["processor_model_counts"], {
            "Other CPU": 1, "Synthetic CPU": 3,
        })
        with self.assertRaisesRegex(
            RunCell.RunCellError, "within an array element"
        ):
            RunCell.summarize_hardware_records(
                [(1, hardware_raw()), (2, hardware_raw("Other CPU"))],
                [[1, 2]],
            )
        with self.assertRaisesRegex(RunCell.RunCellError, "cell order"):
            RunCell.summarize_hardware_records(
                list(reversed(records)), [[1, 2, 3], [4]]
            )


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
                    SafeIO.os, "read", wraps=os.read
                ) as read:
                    with self.assertRaises(SafeIO.SafeReadError):
                        SafeIO.read_regular_file(path, label=name)
                    read.assert_not_called()

    def test_symlinked_ancestor_is_never_followed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            real = root / "real"
            real.mkdir()
            (real / "input").write_bytes(b"secret")
            (root / "link").symlink_to(real, target_is_directory=True)
            with mock.patch.object(SafeIO.os, "read", wraps=os.read) as read:
                with self.assertRaises(SafeIO.SafeReadError):
                    SafeIO.read_regular_file(
                        root / "link" / "input", label="symlinked ancestor",
                        root=root,
                    )
                read.assert_not_called()

    def test_replaced_ancestor_is_detected_after_same_fd_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            directory = root / "directory"
            directory.mkdir()
            (directory / "input").write_bytes(b"original")
            real_read = os.read
            replaced = False

            def race(descriptor, size):
                nonlocal replaced
                block = real_read(descriptor, size)
                if not replaced:
                    replaced = True
                    directory.rename(root / "old-directory")
                    directory.mkdir()
                    (directory / "input").write_bytes(b"replacement")
                return block

            with mock.patch.object(SafeIO.os, "read", side_effect=race):
                with self.assertRaisesRegex(
                    SafeIO.SafeReadError, "ancestor changed"
                ):
                    SafeIO.read_regular_file(
                        directory / "input", label="raced ancestor", root=root
                    )

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

            raced = False

            def race(candidate, flags, *args, **kwargs):
                nonlocal raced
                if candidate == "input" and not raced:
                    raced = True
                    path.unlink()
                    os.mkfifo(path)
                return real_open(candidate, flags, *args, **kwargs)

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

    def test_hardware_probe_failure_prevents_child_and_outputs(self):
        names = list(RecoverA.LegacyDynamic.names())
        with tempfile.TemporaryDirectory() as tmp, self._in_directory(tmp), \
                mock.patch.object(
                    RunCell, "_live_hardware_attestation",
                    side_effect=RunCell.RunCellError("mixed processors"),
                ), mock.patch.object(RunCell.subprocess, "run") as child:
            with self.assertRaisesRegex(RunCell.RunCellError, "mixed"):
                RunCell.run_cell(
                    Path("/usr/bin/python3"), Path("run"),
                    Path("driver.log"), Path("driver.err"), names,
                )
            child.assert_not_called()
            self.assertEqual(list(Path(".").iterdir()), [])

    def test_hardware_record_exists_before_child_and_has_no_identifiers(self):
        names = list(RecoverA.LegacyDynamic.names())

        def child(*args, **kwargs):
            path = Path(RunCell.HARDWARE_ATTESTATION_NAME)
            self.assertTrue(path.is_file())
            self.assertEqual(
                RunCell.parse_hardware_attestation(path.read_bytes())[
                    "processor_model"
                ],
                "Synthetic CPU",
            )
            return mock.Mock(returncode=0)

        with tempfile.TemporaryDirectory() as tmp, self._in_directory(tmp), \
                mock.patch.object(
                    RunCell, "_live_hardware_attestation",
                    return_value=hardware_raw(),
                ), mock.patch.object(
                    RunCell.subprocess, "run", side_effect=child
                ) as invoked:
            self.assertEqual(RunCell.run_cell(
                Path("/usr/bin/python3"), Path("run"),
                Path("driver.log"), Path("driver.err"), names,
            ), 0)
            invoked.assert_called_once()
            value = RunCell.parse_hardware_attestation(
                Path(RunCell.HARDWARE_ATTESTATION_NAME).read_bytes()
            )
            self.assertEqual(set(value), {
                "schema", "processor_model", "architecture",
            })

    def test_child_hardware_overwrite_is_detected_on_retained_descriptor(self):
        names = list(RecoverA.LegacyDynamic.names())

        def child(*args, **kwargs):
            Path(RunCell.HARDWARE_ATTESTATION_NAME).write_bytes(
                hardware_raw("Injected CPU")
            )
            return mock.Mock(returncode=0)

        with tempfile.TemporaryDirectory() as tmp, self._in_directory(tmp), \
                mock.patch.object(
                    RunCell, "_live_hardware_attestation",
                    return_value=hardware_raw(),
                ), mock.patch.object(
                    RunCell.subprocess, "run", side_effect=child
                ):
            with self.assertRaisesRegex(
                RunCell.RunCellError, "changed during execution"
            ):
                RunCell.run_cell(
                    Path("/usr/bin/python3"), Path("run"),
                    Path("driver.log"), Path("driver.err"), names,
                )


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
                                self.assertFalse(any(
                                    call.args and call.args[0] == name
                                    for call in opened.call_args_list
                                ))
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
                    self.assertFalse(any(
                        call.args and call.args[0] == "driver.log"
                        for call in opened.call_args_list
                    ))
                    read.assert_not_called()

    def test_execution_hardware_is_complete_canonical_and_block_consistent(self):
        for audit in (AuditA, AuditB):
            with self.subTest(module=audit.__name__), \
                    tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp) / "experiment"
                with mock.patch.multiple(
                    audit,
                    EXPERIMENT_PATH=root,
                    EXPECTED_CELLS=3,
                    EXPECTED_ARRAY_TASKS=1,
                    RUNS_PER_ARRAY_TASK=3,
                ):
                    for cell in range(1, 4):
                        path = audit._run_directory(cell)
                        path.mkdir(parents=True)
                    with self.assertRaisesRegex(
                        audit.ExecutionAuditError, "missing or unsafe"
                    ):
                        audit._hardware_summary()
                    for cell in range(1, 4):
                        (audit._run_directory(cell) /
                         RunCell.HARDWARE_ATTESTATION_NAME).write_bytes(
                            hardware_raw()
                        )
                    summary = audit._hardware_summary()
                    self.assertEqual(summary["hardware_attestation_files"], 3)
                    self.assertEqual(
                        summary["processor_model_counts"], {"Synthetic CPU": 3}
                    )
                    second = (
                        audit._run_directory(2) /
                        RunCell.HARDWARE_ATTESTATION_NAME
                    )
                    second.write_bytes(hardware_raw("Other CPU"))
                    with self.assertRaisesRegex(
                        audit.ExecutionAuditError, "within an array element"
                    ):
                        audit._hardware_summary()
                    second.write_bytes(b"not canonical\n")
                    with self.assertRaisesRegex(
                        audit.ExecutionAuditError, "canonical"
                    ):
                        audit._hardware_summary()

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
                            self.assertFalse(any(
                                call.args and call.args[0] == "driver.log"
                                for call in opened.call_args_list
                            ))
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
