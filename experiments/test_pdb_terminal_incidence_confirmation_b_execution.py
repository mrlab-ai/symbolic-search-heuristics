#!/usr/bin/env python3

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import analyze_pdb_terminal_incidence_confirmation_b as Analyze
import audit_pdb_terminal_incidence_confirmation_b as Audit
import exp_pdb_terminal_incidence_confirmation_b as Runner
import pdb_confirmation_run_cell as RunCell
import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_b_protocol as P
import recover_pdb_terminal_incidence_confirmation_b as Recover


TASKS = 300
CELLS = 9 * TASKS
ARRAY_TASKS = CELLS // 3
HARDWARE = {
    "hardware_attestation_schema": RunCell.HARDWARE_ATTESTATION_SCHEMA,
    "hardware_attestation_files": CELLS,
    "hardware_records_sha256": "3" * 64,
    "processor_model_counts": {"Synthetic CPU": CELLS},
    "architecture_counts": {"x86_64": CELLS},
}


class PrepareJobCommandTest(unittest.TestCase):
    def test_wrapper_separates_build_and_job_rendering(self):
        with mock.patch.object(Runner, "configure"), mock.patch.object(
            Runner.Base, "main", return_value=0
        ) as base_main, mock.patch.object(
            Runner, "_sanitize_job_file"
        ) as sanitize, mock.patch.object(
            Runner, "_validate_generated_run_mapping"
        ) as mapping:
            self.assertEqual(Runner.main(["build"]), 0)
        base_main.assert_called_once_with(["build"])
        sanitize.assert_not_called()
        mapping.assert_not_called()

        with mock.patch.object(Runner, "configure"), mock.patch.object(
            Runner.Base, "prepare_start_job", return_value=Runner.JOB_FILE
        ) as prepare, mock.patch.object(
            Runner, "_sanitize_job_file"
        ) as sanitize, mock.patch.object(
            Runner, "_validate_job_file", return_value="a" * 64
        ), mock.patch.object(
            Runner, "_validate_generated_run_mapping", return_value="b" * 64
        ) as mapping:
            self.assertEqual(Runner.main(["prepare-job"]), 0)
        prepare.assert_called_once_with()
        sanitize.assert_called_once_with()
        self.assertEqual(mapping.call_count, 2)


class FrozenCardinality:
    def __enter__(self):
        self.stack = ExitStack()
        for module in (P,):
            self.stack.enter_context(mock.patch.multiple(
                module,
                COHORT_TASKS=TASKS,
                CELL_COUNT=CELLS,
                EXPECTED_ARRAY_TASKS=ARRAY_TASKS,
            ))
        self.stack.enter_context(mock.patch.multiple(
            Audit,
            EXPECTED_CELLS=CELLS,
            EXPECTED_ARRAY_TASKS=ARRAY_TASKS,
            RUNS_PER_ARRAY_TASK=3,
        ))
        return self

    def __exit__(self, *args):
        return self.stack.__exit__(*args)


class SchedulerContractTest(unittest.TestCase):
    def test_launch_clean_commit_uses_live_working_copy_snapshot(self):
        revision = "4" * 40
        with mock.patch.object(
            Runner.JJ, "live_working_copy_diff_summary", return_value="",
        ) as live, mock.patch.object(
            Runner.JJ, "parent_commit", return_value=revision,
        ) as parent, mock.patch.object(
            Runner, "_require_repository_ancestry",
        ) as ancestry:
            self.assertEqual(Runner._clean_repository_commit(), revision)
        live.assert_called_once_with(Runner.REPO)
        parent.assert_called_once_with(Runner.REPO)
        ancestry.assert_called_once_with(revision)
        with mock.patch.object(
            Runner.JJ, "live_working_copy_diff_summary", return_value="M source",
        ), mock.patch.object(
            Runner.JJ, "parent_commit",
        ) as parent, self.assertRaisesRegex(
            Runner.ConfirmationLaunchError, "clean working copy"
        ):
            Runner._clean_repository_commit()
        parent.assert_not_called()

    @staticmethod
    def row(state, exit_code="0:0", task=1):
        return {"array_task": task, "state": state, "exit_code": exit_code}

    def test_only_scheduler_interruptions_are_recoverable(self):
        self.assertEqual(Audit._row_class(self.row("COMPLETED")), "successful")
        for state in ("BOOT_FAIL", "NODE_FAIL", "PREEMPTED", "REVOKED"):
            self.assertEqual(
                Audit._row_class(self.row(state, "1:0")), "recoverable"
            )
        for state, code in (
            ("TIMEOUT", "0:0"),
            ("OUT_OF_MEMORY", "0:9"),
            ("CANCELLED", "0:15"),
            ("FAILED", "2:0"),
        ):
            with self.assertRaises(Audit.ExecutionAuditError):
                Audit._row_class(self.row(state, code))

    def test_cell_mapping_and_recovery_are_exact_and_unthrottled(self):
        with FrozenCardinality():
            self.assertEqual(list(Audit._task_cells(1)), [1, 2, 3])
            self.assertEqual(
                list(Audit._task_cells(ARRAY_TASKS)),
                [CELLS - 2, CELLS - 1, CELLS],
            )
            with tempfile.TemporaryDirectory() as tmp:
                wave = Path(tmp) / "wave-0001"
                token = "a" * 24
                command = Recover.submit_command(1, wave, [2, 7], token)
                expected, comment = Audit._expected_recovery_command(
                    wave, 1, [2, 7], token
                )
            self.assertEqual(command, expected)
            self.assertIn("--array=2,7", command)
            array_option = next(
                item for item in command if item.startswith("--array=")
            )
            self.assertNotIn("%", array_option)
            self.assertFalse(any("nice" in item for item in command))
            self.assertIn("--export=NONE", command)
            self.assertIn("--mem-per-cpu=26G", command)
            self.assertEqual(command[0], str(Runner.SBATCH_COMMAND))
            self.assertTrue(all(item.startswith("--") for item in command[1:]))
            self.assertNotIn(str(Runner.JOB_FILE), command)
            self.assertEqual(
                comment, "pdb-incidence-confirm-b-recovery/1/" + token
            )

    def test_primary_submit_command_is_options_only(self):
        with mock.patch.object(P, "EXPECTED_ARRAY_TASKS", 2):
            command = Runner._submit_command("a" * 24)
        self.assertEqual(command[0], "/usr/bin/sbatch")
        self.assertTrue(all(item.startswith("--") for item in command[1:]))
        self.assertNotIn(str(Runner.JOB_FILE), command)
        self.assertIn("--array=1-2", command)
        self.assertIn("--export=NONE", command)

    def test_submission_journal_requires_exact_command_and_full_array(self):
        token = "a" * 24
        with mock.patch.object(P, "EXPECTED_ARRAY_TASKS", 2):
            command = Runner._submit_command(token)
        materials = {
            "recorded_utc": "2026-09-01T12:34:56+00:00",
            "job_name": Runner.EXPECTED_JOB_NAME,
            "submission_comment": Runner._submission_identity(token)[1],
            "submission_token": token,
            "submit_command": command,
        }
        submit_line = " ".join(command)
        rows = "\n".join((
            "123|{}|{}|{}".format(
                materials["job_name"], materials["submission_comment"],
                submit_line,
            ),
            "123_1|{}||{}".format(materials["job_name"], submit_line),
            "123_2|{}||{}".format(materials["job_name"], submit_line),
        ))
        with mock.patch.object(P, "EXPECTED_ARRAY_TASKS", 2), mock.patch.object(
            Runner, "_executable_identity"
        ), mock.patch.object(
            Runner.subprocess, "check_output", return_value=rows
        ) as query:
            self.assertEqual(Runner._journal_job_ids(materials), ["123"])
        self.assertEqual(query.call_args.kwargs["env"], Runner.SUBMISSION_ENVIRONMENT)
        self.assertEqual(query.call_args.args[0][0], "/usr/bin/sacct")

        incomplete = "\n".join(rows.splitlines()[:-1])
        with mock.patch.object(P, "EXPECTED_ARRAY_TASKS", 2), mock.patch.object(
            Runner, "_executable_identity"
        ), mock.patch.object(
            Runner.subprocess, "check_output", return_value=incomplete
        ), self.assertRaisesRegex(
            Runner.ConfirmationLaunchError, "array is incomplete"
        ):
            Runner._journal_job_ids(materials)

    def test_recovery_journal_and_stdin_materials_are_exact(self):
        token = "b" * 24
        with FrozenCardinality(), tempfile.TemporaryDirectory() as tmp:
            wave_dir = Path(tmp) / "wave-0001"
            command = Recover.submit_command(1, wave_dir, [2, 7], token)
            intent = {
                "recorded_utc": "2026-09-01T12:34:56+00:00",
                "wave": 1,
                "submission_token": token,
                "array_tasks": [2, 7],
                "submit_command": command,
            }
            name, comment = Recover._submission_identity(1, token)
            submit_line = " ".join(command)
            rows = "\n".join((
                "456|{}|{}|{}".format(name, comment, submit_line),
                "456_2|{}||{}".format(name, submit_line),
                "456_7|{}||{}".format(name, submit_line),
            ))
            with mock.patch.object(
                Runner, "_executable_identity"
            ), mock.patch.object(
                Recover.subprocess, "check_output", return_value=rows
            ) as query:
                self.assertEqual(Recover._journal_ids(intent), ["456"])
            self.assertEqual(
                query.call_args.kwargs["env"], Runner.SUBMISSION_ENVIRONMENT
            )

            launch = {
                "job_id": "123",
                "job_file_sha256": "1" * 64,
                "slurm_stdin_sha256": "2" * 64,
            }
            plan = {
                "launch": launch,
                "source_rows": [{
                    "array_task": 2, "state": "NODE_FAIL",
                    "exit_code": "1:0",
                }],
                "tasks": [2],
                "cells": [4, 5, 6],
            }

            def executable(path, digest, label):
                return {"path": str(path), "sha256": digest}

            with mock.patch.object(
                Runner, "load_launch_receipt", return_value=("3" * 64, launch)
            ), mock.patch.object(
                Runner, "_submission_job_bytes", return_value=b"job-bytes"
            ), mock.patch.object(
                Runner, "_executable_identity", side_effect=executable
            ):
                common = Recover._common(plan, 1, wave_dir, token)
            self.assertEqual(common["slurm_submission_mode"], "stdin")
            self.assertEqual(common["slurm_stdin_bytes"], len(b"job-bytes"))
            self.assertFalse(common["slurm_path_argument"])
            self.assertEqual(
                common["submission_environment"], Runner.SUBMISSION_ENVIRONMENT
            )

    def test_execution_receipt_records_actual_resource_rows(self):
        scheduler = [{
            "array_task": 1, "state": "COMPLETED", "exit_code": "0:0"
        }]
        row = "|".join((
            "123_1", P.ACCOUNT, "fat", "normal", "1", "26G",
            "01:40:00", "COMPLETED", "0:0", Runner.EXPECTED_JOB_NAME,
        ))
        with mock.patch.object(
            Runner, "_executable_identity"
        ), mock.patch.object(
            Audit.subprocess, "check_output", return_value=row
        ) as query:
            actual = Audit.scheduler_contract_rows(
                "123", Runner.EXPECTED_JOB_NAME, scheduler, {1}
            )
        self.assertEqual(actual[0]["req_mem"], "26G")
        self.assertEqual(actual[0]["time_limit"], "01:40:00")
        self.assertEqual(query.call_args.kwargs["env"], Runner.SUBMISSION_ENVIRONMENT)
        self.assertEqual(query.call_args.args[0][0], "/usr/bin/sacct")

        with mock.patch.object(
            Runner, "_executable_identity"
        ), mock.patch.object(
            Audit.subprocess, "check_output", return_value=row.replace("26G", "25G")
        ), self.assertRaisesRegex(
            Audit.ExecutionAuditError, "resource contract changed"
        ):
            Audit.scheduler_contract_rows(
                "123", Runner.EXPECTED_JOB_NAME, scheduler, {1}
            )

    def test_sealed_properties_must_be_a_regular_nonsymlink_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            regular = root / "properties"
            regular.write_bytes(b"sealed input\n")
            expected = hashlib.sha256(regular.read_bytes()).hexdigest()
            with mock.patch.object(Audit, "EVAL_PROPERTIES", regular):
                self.assertEqual(Audit._sealed_properties_sha256(), expected)
            link = root / "properties-link"
            link.symlink_to(regular)
            with mock.patch.object(
                Audit, "EVAL_PROPERTIES", link
            ), self.assertRaisesRegex(
                Audit.ExecutionAuditError, "cannot read sealed"
            ):
                Audit._sealed_properties_sha256()

    def test_recovery_archive_schema_source_and_bytes_are_exact(self):
        with FrozenCardinality(), tempfile.TemporaryDirectory() as tmp:
            wave = Path(tmp) / "wave-0001"
            target = wave / "interrupted-cell-files/00001/driver.log"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"partial\n")
            base = {
                "run_id": 1,
                "name": "driver.log",
                "source": "runs-00001-00100/00001/driver.log",
                "target": "interrupted-cell-files/00001/driver.log",
                "size": len(b"partial\n"),
                "sha256": hashlib.sha256(b"partial\n").hexdigest(),
                "identity": SafeIO.read_regular_file(
                    target, label="test archive"
                ).identity,
            }
            Audit._validate_archive(wave, [base], [1])
            for item in (
                {**base, "source": "wrong/driver.log"},
                {**base, "unexpected": True},
                {**base, "size": 1},
            ):
                with self.assertRaises(Audit.ExecutionAuditError):
                    Audit._validate_archive(wave, [item], [1])

    def test_recovery_reruns_the_whole_blocked_triad(self):
        with FrozenCardinality(), mock.patch.object(
            Audit, "make_status",
            return_value=(
                {"job_id": "1"},
                [{"array_task": 2, "state": "NODE_FAIL", "exit_code": "1:0"}],
                [],
                {
                    "active_array_tasks": [],
                    "recoverable_array_tasks": [2],
                    "incomplete_cells": [4],
                },
            ),
        ):
            plan = Recover.recovery_plan()
        self.assertEqual(plan["cells"], [4, 5, 6])

    def test_recovery_reruns_whole_triad_when_no_cell_is_incomplete(self):
        with FrozenCardinality(), mock.patch.object(
            Audit, "make_status",
            return_value=(
                {"job_id": "1"},
                [{"array_task": 2, "state": "NODE_FAIL", "exit_code": "1:0"}],
                [],
                {
                    "active_array_tasks": [],
                    "recoverable_array_tasks": [2],
                    "incomplete_cells": [],
                },
            ),
        ):
            plan = Recover.recovery_plan()
        self.assertEqual(plan["cells"], [4, 5, 6])

    def test_legacy_parse_pipeline_uses_extended_execution_receipt(self):
        with mock.patch.object(
            Runner, "load_launch_receipt", return_value=("0" * 64, {})
        ):
            Audit._configure_legacy()
        self.assertIs(
            Audit.Legacy.load_execution_receipt,
            Audit._legacy_load_execution_receipt,
        )


class BlockedRunOrderTest(unittest.TestCase):
    def test_task_major_triads_are_family_balanced_and_digest_stable(self):
        tasks = [
            {"directory": "d{}".format(index), "problem": "p", "family": "f"}
            for index in range(6)
        ]
        rows = P.task_major_cell_mapping(reversed(tasks))
        self.assertEqual(len(rows), 9 * len(tasks))
        for offset in range(0, len(rows), 3):
            block = rows[offset:offset + 3]
            self.assertEqual(
                len({(row["domain"], row["problem"]) for row in block}), 1
            )
        triads = [
            tuple(row["algorithm"] for row in rows[index + 6:index + 9])
            for index in range(0, len(rows), 9)
        ]
        expected = (
            (P.PLAIN_REFERENCE_LABEL, P.GUIDED_LABEL, P.MATCHED_LABEL),
            (P.GUIDED_LABEL, P.MATCHED_LABEL, P.PLAIN_REFERENCE_LABEL),
            (P.MATCHED_LABEL, P.PLAIN_REFERENCE_LABEL, P.GUIDED_LABEL),
        )
        self.assertEqual(tuple(triads[:3]), expected)
        self.assertEqual(tuple(triads[3:]), expected)
        self.assertEqual(
            P.run_cell_mapping_digest(tasks),
            P.run_cell_mapping_digest(reversed(tasks)),
        )

    def test_generated_static_properties_must_match_frozen_run_ids(self):
        tasks = [
            {"directory": "d{}".format(index), "problem": "p", "family": "f"}
            for index in range(2)
        ]
        rows = P.task_major_cell_mapping(tasks)
        digest = P.run_cell_mapping_digest(tasks)
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            Runner, "EXPERIMENT_PATH", Path(tmp)
        ), mock.patch.object(
            P, "_load_freeze",
            return_value=({}, SimpleNamespace(tasks=tuple(tasks))),
        ), mock.patch.multiple(
            P, CELL_COUNT=len(rows), RUN_CELL_MAPPING_SHA256=digest
        ):
            for row in rows:
                path = Runner._run_directory(row["run_id"]) / "static-properties"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps({
                    "algorithm": row["algorithm"],
                    "domain": row["domain"],
                    "problem": row["problem"],
                }))
            self.assertEqual(Runner._validate_generated_run_mapping(), digest)
            first = Runner._run_directory(1) / "static-properties"
            value = json.loads(first.read_text())
            value["algorithm"] = "wrong"
            first.write_text(json.dumps(value))
            with self.assertRaisesRegex(
                Runner.ConfirmationLaunchError, "frozen blocked mapping"
            ):
                Runner._validate_generated_run_mapping()


class JobFileTest(unittest.TestCase):
    def helpers(self):
        return "\n".join((
            "function print {",
            "    local msg=${1}",
            '    printf "[Slurm task %05d] %s\\n" "$SLURM_ARRAY_TASK_ID" "$msg"',
            "}",
            "",
            "function print_run_dir {",
            "    local run_id=${1}",
            '    let "lower=((run_id - 1) / 100) * 100 + 1"',
            '    let "upper=((run_id + 100 - 1) / 100) * 100"',
            '    printf "runs-%05d-%05d/%05d" $lower $upper $run_id',
            "}",
            "",
            SafeIO.hardened_execute_run_block(
                Path(Runner.sys.executable), Runner.RUN_CELL_HELPER,
                Runner.DYNAMIC_OUTPUT_NAMES,
            ),
        ))

    def mapping(self, run_ids=None):
        if run_ids is None:
            run_ids = range(1, CELLS + 1)
        declaration = "declare -a SHUFFLED_RUN_IDS=({})".format(
            " ".join(map(str, run_ids))
        )
        return "\n".join((
            "# Shuffle runs to avoid systematic bias.",
            declaration,
            "NUM_RUNS={}".format(CELLS),
            "RUNS_PER_TASK=3",
            "",
            "# Compute which indices belong to the Slurm task.",
            'let "START_INDEX=($SLURM_ARRAY_TASK_ID - 1) * RUNS_PER_TASK"',
            'let "END_INDEX=START_INDEX + RUNS_PER_TASK - 1"',
            "",
            "if [ $END_INDEX -ge $NUM_RUNS ]; then",
            '    let "END_INDEX=$NUM_RUNS - 1"',
            "fi",
            "",
            "# Execute runs.",
            "for index in $(seq $START_INDEX $END_INDEX); do",
            "    run_id=${SHUFFLED_RUN_IDS[$index]}",
            "    run_dir=$(print_run_dir ${run_id})",
            '    (cd "{}/$run_dir" && execute_run ${{run_id}})'.format(
                Runner.EXPERIMENT_PATH.resolve()
            ),
            "    CELL_STATUS=$?",
            "    if [[ $CELL_STATUS != 0 ]]; then",
            '        exit "$CELL_STATUS"',
            "    fi",
            "done",
        ))

    def job(self, extra="", *, helpers=True, mapping=True):
        lines = [
            "#! /bin/bash -l",
            "#SBATCH --job-name=" + Runner.EXPECTED_JOB_NAME,
            "#SBATCH --output={}".format(
                (Runner.GRID_DIR / "slurm.log").resolve()
            ),
            "#SBATCH --error={}".format(
                (Runner.GRID_DIR / "slurm.err").resolve()
            ),
            "#SBATCH --open-mode=append",
            "#SBATCH --partition=fat",
            "#SBATCH --qos=normal",
            "#SBATCH --time=01:40:00",
            "#SBATCH --mem-per-cpu=26G",
            "#SBATCH --cpus-per-task=1",
            "#SBATCH --array=1-{}".format(ARRAY_TASKS),
            "#SBATCH --mail-type=NONE",
            "#SBATCH --mail-user=",
            "#SBATCH --account=" + P.ACCOUNT,
        ]
        if extra:
            lines.extend(extra.splitlines())
        if helpers:
            lines.append(self.helpers())
        if mapping:
            lines.append(self.mapping())
        return "\n".join(lines) + "\n"

    def execute_first_array(self, *, collision_position=None, child_codes=None):
        if child_codes is None:
            child_codes = (0, 0, 0)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        experiment = root / "experiment"
        run_dirs = []
        for run_id, code in enumerate(child_codes, start=1):
            run_dir = experiment / "runs-00001-00100" / "{:05d}".format(run_id)
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "run").write_text("\n".join((
                "from pathlib import Path",
                'Path("invoked").write_text("yes")',
                "raise SystemExit({})".format(code),
                "",
            )))
            run_dirs.append(run_dir)
        if collision_position is not None:
            (run_dirs[collision_position - 1] / "driver.log").write_bytes(
                b"preexisting\n"
            )
        job = root / Runner.EXPECTED_JOB_NAME
        with FrozenCardinality(), mock.patch.object(
            Runner, "EXPERIMENT_PATH", experiment
        ), mock.patch.object(Runner, "JOB_FILE", job):
            job.write_text(self.job())
            Runner._validate_job_file()
        environment = dict(os.environ)
        environment["SLURM_ARRAY_TASK_ID"] = "1"
        completed = subprocess.run(
            ["/bin/bash", str(job)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment, check=False,
        )
        return completed, run_dirs

    def validate(self, content, *, passes):
        with FrozenCardinality(), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / Runner.EXPECTED_JOB_NAME
            path.write_text(content)
            with mock.patch.object(Runner, "JOB_FILE", path):
                if passes:
                    self.assertRegex(
                        Runner._validate_job_file(), r"^[0-9a-f]{64}$"
                    )
                else:
                    with self.assertRaises(Runner.ConfirmationLaunchError):
                        Runner._validate_job_file()

    def test_exact_full_job_is_accepted(self):
        content = self.job()
        self.validate(content, passes=True)
        with FrozenCardinality(), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / Runner.EXPECTED_JOB_NAME
            path.write_text(content)
            with mock.patch.object(Runner, "JOB_FILE", path):
                digest = Runner._validate_job_file()
                self.assertEqual(
                    Runner._submission_job_bytes(digest), path.read_bytes()
                )

    def test_namespace_collision_aborts_array_before_later_cells(self):
        for position in (1, 2):
            with self.subTest(position=position):
                completed, run_dirs = self.execute_first_array(
                    collision_position=position
                )
                self.assertEqual(
                    completed.returncode, RunCell.INFRASTRUCTURE_EXIT_CODE
                )
                self.assertEqual(
                    [(path / "invoked").exists() for path in run_dirs],
                    [index < position for index in range(1, 4)],
                )

    def test_ordinary_child_outcome_keeps_array_outcome_accounting(self):
        completed, run_dirs = self.execute_first_array(child_codes=(23, 0, 0))
        self.assertEqual(completed.returncode, 0)
        self.assertTrue(all((path / "invoked").is_file() for path in run_dirs))
        self.assertIn(
            b"run script finished with exit code 23",
            (run_dirs[0] / "driver.err").read_bytes(),
        )

    def test_sanitizer_replaces_legacy_redirection_with_exclusive_wrapper(self):
        hardened = SafeIO.hardened_execute_run_block(
            Path(Runner.sys.executable), Runner.RUN_CELL_HELPER,
            Runner.DYNAMIC_OUTPUT_NAMES,
        )
        legacy = SafeIO.legacy_execute_run_block(Path(Runner.sys.executable))
        content = self.job("#SBATCH --nice=0").replace(hardened, legacy)
        with FrozenCardinality(), tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / Runner.EXPECTED_JOB_NAME
            path.write_text(content)
            with mock.patch.object(Runner, "JOB_FILE", path):
                Runner._sanitize_job_file()
                sanitized = path.read_text()
        self.assertIn(hardened, sanitized)
        self.assertNotIn(legacy, sanitized)
        self.assertNotIn("#SBATCH --nice", sanitized)
        self.assertNotIn(") > driver.log 2> driver.err", sanitized)

    def test_header_only_and_mutated_body_are_rejected(self):
        cases = (
            self.job(helpers=False, mapping=False),
            self.job("exit 0"),
            self.job("echo unexpected-command"),
            self.job().replace(
                '    printf "[Slurm task %05d] %s\\n" '
                '"$SLURM_ARRAY_TASK_ID" "$msg"',
                '    printf "%s\\n" "$msg"',
            ),
            self.job().replace(
                " --run-script run ", " --run-script changed "
            ),
            self.job().replace(
                'let "START_INDEX=($SLURM_ARRAY_TASK_ID - 1) * RUNS_PER_TASK"',
                'let "START_INDEX=$SLURM_ARRAY_TASK_ID * RUNS_PER_TASK"',
            ),
            self.job().replace(
                " ".join(map(str, range(1, CELLS + 1))),
                " ".join(map(str, reversed(range(1, CELLS + 1)))),
            ),
        )
        for content in cases:
            self.validate(content, passes=False)

    def test_scheduler_directives_must_be_the_leading_ordered_header(self):
        lines = self.job().splitlines()
        partition = "#SBATCH --partition=fat"
        late_one = [line for line in lines if line != partition] + [partition]
        directives = [line for line in lines if line.startswith("#SBATCH")]
        all_late = [
            lines[0],
            *[line for line in lines[1:] if not line.startswith("#SBATCH")],
            *directives,
        ]
        for mutated in (late_one, all_late):
            self.validate("\n".join(mutated) + "\n", passes=False)

    def test_alias_unknown_conflicting_throttle_and_nice_are_rejected(self):
        conflicts = (
            "#SBATCH --partition=thin",
            "#SBATCH --partition thin",
            "#SBATCH -p thin",
            "#SBATCH --job-name=other",
            "#SBATCH -J other",
            "#SBATCH --qos=low",
            "#SBATCH --time=02:00:00",
            "#SBATCH -t 02:00:00",
            "#SBATCH --mem-per-cpu=30G",
            "#SBATCH --mem=30G",
            "#SBATCH --cpus-per-task=2",
            "#SBATCH -c 2",
            "#SBATCH --array=1-10",
            "#SBATCH -a 1-10",
            "#SBATCH --account=other",
            "#SBATCH -A other",
            "#SBATCH --ntasks=2",
            "#SBATCH --nodes=2",
            "#SBATCH --exclusive",
            "#SBATCH --requeue",
            "#SBATCH --export=ALL",
            "#SBATCH --nice=1",
            "#SBATCH --nice 1",
            "NUM_RUNS=1",
            "RUNS_PER_TASK=4",
        )
        for conflict in conflicts:
            with self.subTest(conflict=conflict):
                self.validate(self.job(conflict), passes=False)
        self.validate(
            self.job().replace(
                "#SBATCH --array=1-{}".format(ARRAY_TASKS),
                "#SBATCH --array=1-{}%10".format(ARRAY_TASKS),
            ),
            passes=False,
        )


class AnalysisProvenanceTest(unittest.TestCase):
    def test_analysis_carries_execution_hardware_as_nongating_input(self):
        result = {
            "schema": Analyze.SCHEMA,
            "analysis_protocol": P.ANALYSIS_PROTOCOL,
            "gates": {"pass": True},
            "mechanism": {"claim_authorized": True},
        }
        sealed = ([], "1" * 64, "2" * 64, "4" * 64, HARDWARE)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            properties = root / "properties"
            properties.write_text("{}")
            outputs = tuple(root / name for name in (
                "analysis.json", "repeat.json", "receipt.json",
                "receipt.sha256",
            ))
            with mock.patch.object(
                Analyze, "_load_sealed_input",
                side_effect=[copy.deepcopy(sealed), copy.deepcopy(sealed)],
            ), mock.patch.object(
                Analyze, "analyze_records",
                side_effect=[copy.deepcopy(result), copy.deepcopy(result)],
            ):
                published = Analyze.run_twice(properties, *outputs)
            analysis = json.loads(outputs[0].read_text())
            receipt = json.loads(outputs[2].read_text())
            self.assertEqual(
                analysis["input"]["execution_receipt_sha256"], "4" * 64
            )
            self.assertEqual(analysis["input"]["hardware"], HARDWARE)
            self.assertEqual(receipt["hardware"], HARDWARE)
            self.assertEqual(published["hardware"], HARDWARE)


if __name__ == "__main__":
    unittest.main()
