#!/usr/bin/env python3

from __future__ import annotations

import copy
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_runner as Runner
import pdb_terminal_metric_choice_transport as Transport
from test_pdb_terminal_metric_choice_protocol import (
    fake_calibration, fake_freeze, fake_snapshot, fake_standalone,
)


class HardeningTest(unittest.TestCase):
    def test_safe_reader_rejects_symlink_directory_fifo_and_alias(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            regular = root / "regular"
            regular.write_bytes(b"payload")
            symlink = root / "symlink"
            symlink.symlink_to(regular)
            directory = root / "directory"
            directory.mkdir()
            fifo = root / "fifo"
            os.mkfifo(fifo)
            for path in (symlink, directory, fifo):
                with self.subTest(path=path.name):
                    with self.assertRaises(CampaignIO.CampaignIOError):
                        CampaignIO.read_regular_exact(
                            path, expected=path, label="adversarial input"
                        )
            with self.assertRaises(CampaignIO.CampaignIOError):
                CampaignIO.read_regular_exact(
                    root / "directory" / ".." / "regular",
                    expected=regular, label="aliased input",
                )

    def test_safe_reader_detects_same_path_replacement_race(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "input"
            replacement = Path(temporary) / "replacement"
            path.write_bytes(b"a" * (2 * 1024 * 1024))
            replacement.write_bytes(b"b")
            original_read = SafeIO.os.read
            replaced = False

            def racing_read(descriptor, size):
                nonlocal replaced
                block = original_read(descriptor, size)
                if not replaced:
                    os.replace(replacement, path)
                    replaced = True
                return block

            with mock.patch.object(SafeIO.os, "read", side_effect=racing_read):
                with self.assertRaises(CampaignIO.CampaignIOError):
                    CampaignIO.read_regular_exact(
                        path, expected=path, label="raced input"
                    )

    def test_authorized_freeze_opens_calibration_before_a_b(self):
        calibration = fake_calibration()
        freeze = fake_freeze()
        order = []

        def load_calibration(path, label, *, expected_path):
            self.assertEqual(path, P.CALIBRATION_RECEIPT_PATH)
            order.append("calibration")
            return P.canonical_json_line(calibration), calibration

        def snapshot(receipt):
            self.assertIs(receipt, calibration)
            order.append("a_b")
            return freeze["base_confirmation_b"]

        def load_freeze(path, *, verify_live_sources):
            order.append("freeze")
            return freeze

        with mock.patch.object(P, "load_canonical", side_effect=load_calibration), \
             mock.patch.object(P, "snapshot_sealed_b", side_effect=snapshot), \
             mock.patch.object(P, "load_freeze", side_effect=load_freeze):
            P.load_authorized_freeze(P.FREEZE_PATH, verify_live_sources=False)
        self.assertEqual(order, ["calibration", "a_b", "freeze"])

    def test_calibration_exclusion_checks_both_cohorts(self):
        receipt = fake_calibration()
        snapshot = fake_snapshot()
        P.validate_calibration_exclusion(receipt, snapshot)
        import pdb_terminal_metric_choice_calibration as Calibration
        digest = Calibration.development_manifest()["tasks"][0]["problem_sha256"]
        for section, row in (
            ("confirmation_a_cohort", snapshot["confirmation_a_cohort"]["identities"][0]),
            ("cohort", snapshot["cohort"]["tasks"][0]),
        ):
            mutated = copy.deepcopy(snapshot)
            target = (
                mutated[section]["identities"][0]
                if section == "confirmation_a_cohort"
                else mutated[section]["tasks"][0]
            )
            target["problem_sha256"] = digest
            if section == "confirmation_a_cohort":
                mutated[section]["identities_sha256"] = __import__("hashlib").sha256(
                    P.canonical_json(mutated[section]["identities"])
                ).hexdigest()
            else:
                mutated[section]["tasks_sha256"] = P.cohort_digest(
                    mutated[section]["tasks"]
                )
            with self.subTest(section=section):
                with self.assertRaisesRegex(P.ProtocolError, "overlaps"):
                    P.validate_calibration_exclusion(receipt, mutated)

    def test_k32_reference_is_reconstructed_not_pool_membership(self):
        snapshot = fake_snapshot()
        evidence = fake_standalone(snapshot)
        evidence["records"][0]["reference_identity"] = {
            "pattern_index": 1, "sources": ["bdd_prefix"], "pattern": [0],
            "value_cap": 0,
        }
        evidence["records_sha256"] = __import__("hashlib").sha256(
            P.canonical_json(evidence["records"])
        ).hexdigest()
        with self.assertRaisesRegex(P.ProtocolError, "reconstruction"):
            P.validate_standalone_evidence(evidence, snapshot)

    def test_transport_requires_no_requeue_and_cache_name(self):
        freeze = fake_freeze()
        contract = Transport.scheduler_contract(freeze, P.ACCOUNT)
        lines = ["#!/bin/bash", *sorted(Transport._required_directives(contract))]
        raw = ("\n".join(lines) + "\n").encode("ascii")
        Transport.validate_job_bytes(raw, contract)
        with self.assertRaisesRegex(Transport.TransportError, "requeue"):
            Transport.validate_job_bytes(
                raw.replace(b"#SBATCH --no-requeue", b"#SBATCH --requeue"),
                contract,
            )
        manifest = Runner.build_manifest(freeze, "f" * 64)
        self.assertEqual(
            manifest["common_properties"]["PLANNER_CACHE_NAME"],
            freeze["planner"]["cache_name"],
        )

    def test_transport_rejects_every_alias_duplicate_and_space_override(self):
        freeze = fake_freeze()
        contract = Transport.scheduler_contract(freeze, P.ACCOUNT)
        base = "\n".join(
            ["#!/bin/bash", *sorted(Transport._required_directives(contract))]
        ) + "\n"
        additions = (
            "#SBATCH --array=1-300%1\n",
            "#SBATCH --array 1-300%1\n",
            "#SBATCH -a 1-300%1\n",
            "#SBATCH -a=1-300%1\n",
            "#SBATCH --cpus-per-task=8\n",
            "#SBATCH --cpus-per-task 8\n",
            "#SBATCH -c 8\n",
            "#SBATCH --ntasks=3\n",
            "#SBATCH --ntasks 3\n",
            "#SBATCH -n 3\n",
            "#SBATCH --nodes=2\n",
            "#SBATCH -N 2\n",
            "#SBATCH --dependency=afterok:123\n",
            "#SBATCH --requeue\n",
        )
        for addition in additions:
            with self.subTest(directive=addition.strip()):
                with self.assertRaises(Transport.TransportError):
                    Transport.validate_job_bytes(
                        (base + addition).encode("ascii"), contract
                    )

    def test_transport_accepts_only_canonical_optional_header_fields(self):
        freeze = fake_freeze()
        contract = Transport.scheduler_contract(freeze, P.ACCOUNT)
        lines = [
            "#!/bin/bash", *sorted(Transport._required_directives(contract)),
            "#SBATCH --job-name=metric-choice",
            "#SBATCH --output=metric-choice.out",
            "#SBATCH --error=metric-choice.err",
            "#SBATCH --open-mode=append", "#SBATCH --nice=0",
            "#SBATCH --mail-type=NONE", "#SBATCH --mail-user=",
        ]
        Transport.validate_job_bytes(("\n".join(lines) + "\n").encode("ascii"), contract)
        malformed = "\n".join(lines).replace(
            "#SBATCH --nice=0", "#SBATCH --nice 0"
        ) + "\n"
        with self.assertRaises(Transport.TransportError):
            Transport.validate_job_bytes(malformed.encode("ascii"), contract)

    def test_transport_requires_all_directives_in_initial_slurm_preamble(self):
        freeze = fake_freeze()
        contract = Transport.scheduler_contract(freeze, P.ACCOUNT)
        directives = sorted(Transport._required_directives(contract))
        late_only = "#!/bin/bash\necho started\n" + "\n".join(directives) + "\n"
        with self.assertRaisesRegex(Transport.TransportError, "after executable"):
            Transport.validate_job_bytes(late_only.encode("ascii"), contract)

        mixed = "\n".join([
            "#!/bin/bash", *directives, "echo started",
            "#SBATCH --cpus-per-task=1", "true", "",
        ])
        with self.assertRaisesRegex(Transport.TransportError, "after executable"):
            Transport.validate_job_bytes(mixed.encode("ascii"), contract)

    def test_generated_run_body_is_hardened_and_ordered(self):
        from lab.environments import SlurmEnvironment
        template = """function execute_run {
    if [[ -f driver.log ]]; then
        return
    fi
}

# Shuffle tasks to avoid systematic bias.
for run_id in $(seq $FIRST_RUN_ID $LAST_RUN_ID | shuf); do
    true
done
"""
        with mock.patch.object(
            SlurmEnvironment, "_get_run_job_body",
            new=lambda self, step: template,
        ):
            Runner._install_hardened_deterministic_run_body()
            body = SlurmEnvironment._get_run_job_body(object(), object())
        self.assertIn("pdb_confirmation_run_cell.py", body)
        self.assertIn("seq $FIRST_RUN_ID $LAST_RUN_ID); do", body)
        self.assertNotIn("| shuf", body)
        self.assertNotIn("[[ -f driver.log ]]", body)

    def test_archive_is_no_replace_regular_only_and_rescannable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            archive_root = root / "archive"
            source.mkdir()
            archive_root.mkdir()
            (source / "driver.log").write_bytes(b"complete")
            archive = archive_root / "triad-1"
            manifest = Transport.archive_regular_entries(
                source, archive, ["driver.log"],
                expected_source_directory=source,
                expected_archive_directory=archive,
                source_root=root, archive_root=archive_root,
                label="recovery archive",
            )
            self.assertEqual(manifest["entries"][0]["name"], "driver.log")
            self.assertFalse((source / "driver.log").exists())
            sealed = Transport.immutable_tree_manifest(
                archive, ["driver.log"], label="recovery archive"
            )
            Transport.verify_manifest_rescan(
                archive, ["driver.log"], sealed, label="recovery archive"
            )
            (source / "driver.log").symlink_to(archive / "driver.log")
            with self.assertRaises(Transport.TransportError):
                Transport.archive_regular_entries(
                    source, archive_root / "triad-2", ["driver.log"],
                    expected_source_directory=source,
                    expected_archive_directory=archive_root / "triad-2",
                    source_root=root, archive_root=archive_root,
                    label="recovery archive",
                )

    def test_archive_rejects_source_replacement_between_read_and_rename(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            archive_root = root / "archive"
            source.mkdir()
            archive_root.mkdir()
            original = source / "driver.log"
            original.write_bytes(b"original")
            real_rename = Transport._rename_noreplace

            def replace_then_rename(source_fd, name, archive_fd, destination):
                os.unlink(name, dir_fd=source_fd)
                descriptor = os.open(
                    name, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o600, dir_fd=source_fd,
                )
                os.write(descriptor, b"replacement")
                os.close(descriptor)
                return real_rename(source_fd, name, archive_fd, destination)

            with mock.patch.object(
                Transport, "_rename_noreplace", side_effect=replace_then_rename
            ), self.assertRaisesRegex(Transport.TransportError, "identity changed"):
                Transport.archive_regular_entries(
                    source, archive_root / "triad-1", ["driver.log"],
                    expected_source_directory=source,
                    expected_archive_directory=archive_root / "triad-1",
                    source_root=root, archive_root=archive_root,
                    label="recovery archive",
                )


if __name__ == "__main__":
    unittest.main()
