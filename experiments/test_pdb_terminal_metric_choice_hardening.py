#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_freeze as Freeze
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_runner as Runner
import pdb_terminal_metric_choice_transport as Transport
from test_pdb_terminal_metric_choice_protocol import (
    fake_calibration, fake_freeze, fake_planner, fake_snapshot,
    fake_standalone, fake_standalone_source_binding,
)


class HardeningTest(unittest.TestCase):
    @staticmethod
    def closure_ready_freeze():
        freeze = fake_freeze()
        base_sources = freeze["base_confirmation_b"][
            "base_b_experiment_source_sha256"
        ]
        campaign_sources = freeze["experiment_source_sha256"]
        for relative, digest in base_sources.items():
            if relative in campaign_sources:
                campaign_sources[relative] = digest
        return freeze

    def test_repository_closure_covers_v11_a_b_inputs(self):
        freeze = self.closure_ready_freeze()
        bindings = Freeze._launch_closure_bindings(freeze, "f" * 64)
        snapshot = freeze["base_confirmation_b"]
        expected = {
            P.FREEZE_PATH.relative_to(P.REPO).as_posix(),
            snapshot["base_b_freeze_path"],
            snapshot["confirmation_a_freeze"]["path"],
            P.BASE_B_PROPERTIES_PATH.relative_to(P.REPO).as_posix(),
            P.BASE_B_PARSE_RECEIPT_PATH.relative_to(P.REPO).as_posix(),
            P.BASE_B_FETCH_RECEIPT_PATH.relative_to(P.REPO).as_posix(),
            P.BASE_A_RECEIPT_PATH.relative_to(P.REPO).as_posix(),
            P.BASE_A_RECEIPT_PIN_PATH.relative_to(P.REPO).as_posix(),
            P.BASE_A_FIRST_OUTPUT_PATH.relative_to(P.REPO).as_posix(),
            P.BASE_A_SECOND_OUTPUT_PATH.relative_to(P.REPO).as_posix(),
            *P.SOURCE_FILES,
            *snapshot["base_b_experiment_source_sha256"],
            *snapshot["source_audit_v11"]["bindings"][
                "combined_tracked_file_sha256"
            ],
        }
        self.assertTrue(expected <= set(bindings))
        self.assertNotIn("paper/paper.tex", bindings)
        broken = copy.deepcopy(freeze)
        broken["experiment_source_sha256"].pop(next(iter(P.SOURCE_FILES)))
        with self.assertRaisesRegex(Freeze.FreezeError, "source closure"):
            Freeze._launch_closure_bindings(broken, "f" * 64)

    def test_v11_committed_source_is_in_repository_closure(self):
        freeze = self.closure_ready_freeze()
        tracked = freeze["base_confirmation_b"]["source_audit_v11"][
            "bindings"
        ]["combined_tracked_file_sha256"]
        bindings = Freeze._launch_closure_bindings(freeze, "f" * 64)
        self.assertEqual(
            {path: bindings[path] for path in tracked}, tracked
        )

    def test_v11_closure_overlap_requires_identical_bytes(self):
        freeze = self.closure_ready_freeze()
        snapshot = freeze["base_confirmation_b"]
        bindings = snapshot["source_audit_v11"]["bindings"]
        shared = next(
            relative for relative in P.SOURCE_FILES
            if relative in snapshot["base_b_experiment_source_sha256"]
        )
        conflicting = "0" * 64
        bindings["full_tracked_file_sha256"][shared] = conflicting
        bindings["combined_tracked_file_sha256"][shared] = conflicting
        for field in (
            "full_tracked_file_sha256", "combined_tracked_file_sha256",
        ):
            bindings[field + "_digest"] = hashlib.sha256(
                P.canonical_json(dict(sorted(bindings[field].items())))
            ).hexdigest()
        snapshot["confirmation_a_authorization"][
            "source_audit_provenance"
        ] = P._expected_v11_run_provenance(
            bindings, snapshot["confirmation_a_freeze"]["sha256"]
        )
        with self.assertRaisesRegex(Freeze.FreezeError, "conflicting bindings"):
            Freeze._launch_closure_bindings(freeze, "f" * 64)

    def test_live_jj_cleanliness_query_has_exact_non_ignored_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            (root / ".jj").mkdir()
            completed = mock.Mock(stdout=b"")
            with mock.patch.object(
                Freeze.JJ, "_verify_jj_identity"
            ) as verify, mock.patch.object(
                Freeze.JJ.subprocess, "run", return_value=completed
            ) as run:
                self.assertEqual(
                    Freeze.JJ.live_working_copy_diff_summary(root), ""
                )
            self.assertEqual(verify.call_count, 2)
            self.assertEqual(run.call_args.args[0], [
                str(Freeze.JJ.JJ_EXECUTABLE), "--no-pager", "-R", str(root),
                "diff", "--summary", "-r", "@",
            ])
            self.assertNotIn("--ignore-working-copy", run.call_args.args[0])
            self.assertEqual(run.call_args.kwargs["cwd"], root)
            self.assertTrue(run.call_args.kwargs["check"])

    def test_freeze_uses_live_snapshot_and_rejects_dirty_working_copy(self):
        revision = "9" * 40
        with mock.patch.object(
            Freeze.JJ, "working_copy_diff_summary", return_value=""
        ) as stale_summary, mock.patch.object(
            Freeze.JJ, "live_working_copy_diff_summary", return_value="M source"
        ), mock.patch.object(
            Freeze.JJ, "parent_commit"
        ) as parent, self.assertRaisesRegex(Freeze.FreezeError, "clean empty"):
            Freeze._require_clean_parent(revision)
        stale_summary.assert_not_called()
        parent.assert_not_called()

    def test_stale_cleanliness_cannot_hide_modified_missing_or_untracked_file(self):
        revision = "9" * 40
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "experiments" / "relevant.json"
            path.parent.mkdir()
            path.write_bytes(b"original\n")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            bindings = {"experiments/relevant.json": digest}
            with mock.patch.object(Freeze.P, "REPO", root), mock.patch.object(
                Freeze.JJ, "working_copy_diff_summary", return_value=""
            ) as stale_summary, mock.patch.object(
                Freeze.JJ, "tracked_file_sha256", return_value=digest
            ):
                Freeze._attest_repository_closure(revision, bindings)
            stale_summary.assert_not_called()

            path.write_bytes(b"modified despite stale clean summary\n")
            with mock.patch.object(Freeze.P, "REPO", root), mock.patch.object(
                Freeze.JJ, "working_copy_diff_summary", return_value=""
            ) as stale_summary, mock.patch.object(
                Freeze.JJ, "tracked_file_sha256", return_value=digest
            ), self.assertRaisesRegex(Freeze.FreezeError, "changed before"):
                Freeze._attest_repository_closure(revision, bindings)
            stale_summary.assert_not_called()

            path.write_bytes(b"original\n")
            with mock.patch.object(Freeze.P, "REPO", root), mock.patch.object(
                Freeze.JJ, "tracked_file_sha256",
                side_effect=Freeze.JJ.JjCacheError("untracked"),
            ), self.assertRaisesRegex(Freeze.FreezeError, "not committed"):
                Freeze._attest_repository_closure(revision, bindings)

            path.unlink()
            with mock.patch.object(Freeze.P, "REPO", root), mock.patch.object(
                Freeze.JJ, "tracked_file_sha256", return_value=digest,
            ), self.assertRaisesRegex(Freeze.FreezeError, "missing or unsafe"):
                Freeze._attest_repository_closure(revision, bindings)

    def test_repository_closure_rechecks_live_bytes_after_jj_query(self):
        revision = "9" * 40
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "experiments" / "raced.json"
            path.parent.mkdir()
            path.write_bytes(b"original\n")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()

            def race(*unused):
                path.write_bytes(b"changed during jj query\n")
                return digest

            with mock.patch.object(Freeze.P, "REPO", root), mock.patch.object(
                Freeze.JJ, "tracked_file_sha256", side_effect=race,
            ), self.assertRaisesRegex(Freeze.FreezeError, "changed during"):
                Freeze._attest_repository_closure(
                    revision, {"experiments/raced.json": digest}
                )

    def test_freeze_second_pass_gates_precede_exclusive_publication(self):
        revision = "9" * 40
        calibration = fake_calibration()
        planner = copy.deepcopy(calibration["planner"])
        snapshot = fake_snapshot()
        standalone = fake_standalone(snapshot)
        source_hashes = {relative: "a" * 64 for relative in P.SOURCE_FILES}
        closure = {"experiments/bound-input": "b" * 64}
        built = {"synthetic": "freeze"}

        def exercise(second_pass_failure=None):
            events = []
            counts = {
                "clean": 0, "ancestors": 0, "rebuild": 0, "closure": 0,
            }

            def gate(name, result=None):
                def checked(*args, **kwargs):
                    counts[name] += 1
                    events.append(name)
                    if counts[name] == 2 and second_pass_failure == name:
                        raise Freeze.FreezeError(
                            "synthetic second-pass {} failure".format(name)
                        )
                    return result
                return checked

            def write(*args, **kwargs):
                events.append("write")
                return "d" * 64

            with mock.patch.object(
                Freeze, "_require_clean_parent", side_effect=gate("clean", revision)
            ) as clean, mock.patch.object(
                P, "load_canonical", side_effect=[
                    (P.canonical_json_line(calibration), calibration),
                    (P.canonical_json_line(planner), planner),
                    (P.canonical_json_line(standalone), standalone),
                ],
            ), mock.patch.object(
                P, "validate_calibration_receipt"
            ), mock.patch.object(
                P, "validate_planner_manifest"
            ), mock.patch.object(
                P, "snapshot_sealed_b", return_value=snapshot,
            ), mock.patch.object(
                P, "validate_standalone_evidence"
            ), mock.patch.object(
                Freeze, "_rebuild_standalone", side_effect=gate("rebuild")
            ) as rebuild, mock.patch.object(
                Freeze, "_require_ancestors", side_effect=gate("ancestors")
            ) as ancestors, mock.patch.object(
                Freeze, "_source_hashes", return_value=source_hashes,
            ), mock.patch.object(
                Freeze, "_freeze_closure_bindings", return_value=closure,
            ), mock.patch.object(
                Freeze, "_attest_repository_closure", side_effect=gate("closure")
            ) as attest, mock.patch.object(
                P, "build_freeze", return_value=built,
            ), mock.patch.object(
                P, "validate_freeze"
            ), mock.patch.object(
                Freeze, "_write_exclusive", side_effect=write,
            ) as exclusive:
                arguments = (
                    P.CALIBRATION_RECEIPT_PATH, P.PLANNER_MANIFEST_PATH,
                    P.STANDALONE_K32_PATH, P.FREEZE_PATH,
                    "01:00:00", "24G", revision,
                )
                if second_pass_failure is None:
                    result = Freeze.freeze(*arguments)
                else:
                    with self.assertRaisesRegex(
                        Freeze.FreezeError,
                        "synthetic second-pass {} failure".format(
                            second_pass_failure
                        ),
                    ):
                        Freeze.freeze(*arguments)
                    result = None
            return (
                result, events, counts, clean, ancestors, rebuild, attest,
                exclusive,
            )

        for failure in ("clean", "ancestors", "rebuild", "closure"):
            with self.subTest(second_pass_failure=failure):
                result = exercise(failure)
                self.assertIsNone(result[0])
                result[-1].assert_not_called()
                self.assertNotIn("write", result[1])

        result, events, counts, clean, ancestors, rebuild, attest, exclusive = (
            exercise()
        )
        self.assertEqual(result, (built, "d" * 64))
        self.assertEqual(
            counts,
            {"clean": 2, "ancestors": 2, "rebuild": 2, "closure": 2},
        )
        self.assertEqual(
            [clean.call_count, ancestors.call_count,
             rebuild.call_count, attest.call_count],
            [2, 2, 2, 2],
        )
        exclusive.assert_called_once_with(P.FREEZE_PATH, built)
        self.assertEqual(events[-1], "write")

    def test_freeze_requires_v11_a_b_ancestors_in_exact_order(self):
        snapshot = fake_snapshot()
        revision = "d" * 40
        with mock.patch.object(Freeze.JJ, "require_ancestor") as require:
            Freeze._require_ancestors(snapshot, revision)
        self.assertEqual(require.call_args_list, [
            mock.call(P.REPO, "1" * 40, "2" * 40),
            mock.call(P.REPO, "2" * 40, "3" * 40),
            mock.call(P.REPO, "3" * 40, "4" * 40),
            mock.call(P.REPO, "4" * 40, "5" * 40),
            mock.call(P.REPO, "5" * 40, revision),
            mock.call(P.REPO, P.REQUIRED_PLANNER_REVISION, revision),
        ])

    def test_freeze_rejects_v11_ancestry_branch(self):
        snapshot = fake_snapshot()

        def require(repo, ancestor, descendant):
            del repo
            if (ancestor, descendant) == ("3" * 40, "4" * 40):
                raise Freeze.JJ.JjCacheError("branch")

        with mock.patch.object(
            Freeze.JJ, "require_ancestor", side_effect=require
        ), self.assertRaisesRegex(Freeze.FreezeError, "not an ancestor"):
            Freeze._require_ancestors(snapshot, "d" * 40)

    def test_freeze_rejects_equal_adjacent_revisions(self):
        snapshot = fake_snapshot()
        snapshot["base_b_freeze_repository_revision"] = snapshot[
            "confirmation_a_freeze"
        ]["repository_revision"]
        with self.assertRaisesRegex(Freeze.FreezeError, "strictly ordered"):
            Freeze._require_ancestors(snapshot, "d" * 40)

    def test_freeze_rebuild_rejects_fabricated_standalone_with_real_hashes(self):
        snapshot = fake_snapshot()
        planner = fake_planner()
        rebuilt = fake_standalone(snapshot)
        fabricated = copy.deepcopy(rebuilt)
        fabricated["records"].reverse()
        fabricated["records_sha256"] = __import__("hashlib").sha256(
            P.canonical_json(fabricated["records"])
        ).hexdigest()
        P.validate_standalone_evidence(fabricated, snapshot, planner)
        with mock.patch(
            "pdb_terminal_metric_choice_standalone.sealed_b_records",
            return_value=([], fake_standalone_source_binding()),
        ), mock.patch(
            "pdb_terminal_metric_choice_standalone.build_evidence",
            return_value=rebuilt,
        ):
            with self.assertRaisesRegex(Freeze.FreezeError, "does not rebuild"):
                Freeze._rebuild_standalone(fabricated, snapshot, planner)

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

    def test_runtime_freeze_does_not_reopen_live_a_b(self):
        freeze = fake_freeze()

        def direct_only(path, label, *, expected_path):
            self.assertEqual((path, expected_path), (P.FREEZE_PATH, P.FREEZE_PATH))
            self.assertEqual(label, "dual metric freeze")
            return P.canonical_json_line(freeze), freeze

        with mock.patch.object(
            P, "load_canonical", side_effect=direct_only
        ) as embedded, mock.patch.object(
            P, "snapshot_sealed_b",
            side_effect=AssertionError("live A/B artifacts disappeared"),
        ), mock.patch.object(
            P, "_lazy_base_protocol",
            side_effect=AssertionError("live A/B protocol reopened"),
        ):
            self.assertEqual(
                P.load_freeze(P.FREEZE_PATH, verify_live_sources=False), freeze
            )
        self.assertEqual(embedded.call_count, 1)

    def test_runtime_rejects_malformed_embedded_guided_b(self):
        freeze = fake_freeze()
        del P.guided_b_tasks(freeze["base_confirmation_b"])[0]["aliases"]
        with mock.patch.object(
            P, "load_canonical",
            return_value=(P.canonical_json_line(freeze), freeze),
        ), self.assertRaisesRegex(P.ProtocolError, "task shape"):
            P.load_freeze(P.FREEZE_PATH, verify_live_sources=False)

    def test_runtime_cohort_is_derived_from_embedded_guided_b(self):
        freeze = fake_freeze()
        records = P.guided_b_tasks(freeze["base_confirmation_b"])
        expected_hashes = {
            record[field]: record[hash_field]
            for record in records
            for field, hash_field in (
                ("domain_file", "domain_sha256"),
                ("problem_file", "problem_sha256"),
            )
        }

        def source_hash(path, **unused):
            return expected_hashes[path.relative_to(Path("/benchmarks")).as_posix()]

        with mock.patch.object(
            P, "load_freeze", return_value=freeze
        ), mock.patch.object(
            P, "sha256_file", side_effect=source_hash
        ), mock.patch.object(
            P, "_lazy_base_protocol",
            side_effect=AssertionError("live B protocol reopened"),
        ):
            tasks = P.load_cohort("/benchmarks")
        self.assertEqual(len(tasks), P.COHORT_TASKS)
        self.assertEqual(
            [(task.domain, task.problem) for task in tasks],
            [(row["directory"], row["problem"]) for row in records],
        )

    def test_calibration_exclusion_checks_both_cohorts(self):
        receipt = fake_calibration()
        snapshot = fake_snapshot()
        P.validate_calibration_exclusion(receipt, snapshot)
        import pdb_terminal_metric_choice_calibration as Calibration
        digest = Calibration.development_manifest()["tasks"][0]["problem_sha256"]
        for role in ("confirmation-a", "guided-b"):
            mutated = copy.deepcopy(snapshot)
            cohort = (
                mutated["confirmation_a_cohort"]
                if role == "confirmation-a"
                else mutated["source_audit_v11"]["guided_b"]
            )
            cohort["records"][0]["problem_sha256"] = digest
            cohort["records"][0]["aliases"][0]["problem_sha256"] = digest
            projection_sha = hashlib.sha256(
                P.canonical_json(cohort["records"])
            ).hexdigest()
            cohort["source_projection_sha256"] = projection_sha
            bindings = mutated["source_audit_v11"]["bindings"]
            prefix = "confirmation_a" if role == "confirmation-a" else "guided_b"
            bindings[prefix + "_source_projection_sha256"] = projection_sha
            if role == "confirmation-a":
                mutated["confirmation_a_authorization"][
                    "confirmation_a_cohort_manifest_sha256"
                ] = projection_sha
            mutated["confirmation_a_authorization"][
                "source_audit_provenance"
            ] = P._expected_v11_run_provenance(
                bindings, mutated["confirmation_a_freeze"]["sha256"]
            )
            with self.subTest(role=role), self.assertRaisesRegex(
                P.ProtocolError, "overlaps"
            ):
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
