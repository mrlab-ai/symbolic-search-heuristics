#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import analyze_pdb_terminal_incidence_confirmation_a as Analyze
import audit_pdb_terminal_incidence_confirmation_a as Audit
import exp_pdb_terminal_incidence_confirmation_a as Runner
import pdb_confirmation_run_cell as RunCell
import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_incidence_confirmation_a_protocol as P
import recover_pdb_terminal_incidence_confirmation_a as Recover


class PrepareJobTest(unittest.TestCase):
    def test_base_renderer_writes_one_job_without_submission(self):
        class FakeEnvironment:
            def __init__(self):
                self.job_dir = None
                self.rendered = 0

            def _get_job_name(self, step):
                self.asserted_step = step
                return Runner.EXPECTED_JOB_NAME

            def _get_job(self, step, is_last):
                self.rendered += 1
                self.asserted_step = step
                self.asserted_last = is_last
                return "#! /bin/bash -l\nexit 0\n"

            def _submit_job(self, *args, **kwargs):
                raise AssertionError("prepare-job must not submit")

        class FakeExperiment:
            def __init__(self):
                self.steps = [
                    SimpleNamespace(name="build"),
                    SimpleNamespace(name="start"),
                ]
                self.environment = FakeEnvironment()
                self.build_calls = []

            def build(self, *, write_to_disk):
                self.build_calls.append(write_to_disk)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            experiment_path = root / "experiment"
            experiment_path.mkdir()
            receipt = root / "artifacts" / "launch-receipt.json"
            fake = FakeExperiment()
            cache = object()
            with mock.patch.multiple(
                Runner.Base,
                P=P,
                EXPERIMENT_PATH=experiment_path,
                COHORT_ARCHIVE=root / "cohort",
                VALIDATE_MATCHED_BUDGET_PROVENANCE=False,
                BENCHMARK_SOURCE_VALIDATOR=lambda cohort: None,
                LAUNCH_RECEIPT=receipt,
                EXPECTED_JOB_NAME=Runner.EXPECTED_JOB_NAME,
            ), mock.patch.object(
                P, "validate_protocol_without_archive"
            ), mock.patch.object(
                P, "load_cohort", return_value=[]
            ), mock.patch.object(
                Runner.Base, "require_lab_8"
            ), mock.patch.object(
                Runner.Base, "require_pins"
            ), mock.patch.object(
                Runner.Base, "cached_revision", return_value=cache
            ), mock.patch.object(
                Runner.Base, "_validate_build_receipt"
            ) as validate_build, mock.patch.object(
                Runner.Base, "make_experiment", return_value=fake
            ):
                rendered = Runner.Base.prepare_start_job()
                self.assertEqual(
                    rendered,
                    Path(str(experiment_path) + "-grid-steps")
                    / Runner.EXPECTED_JOB_NAME,
                )
                self.assertEqual(
                    rendered.read_text(), "#! /bin/bash -l\nexit 0\n"
                )
                self.assertEqual(fake.build_calls, [False])
                self.assertEqual(fake.environment.rendered, 1)
                self.assertTrue(fake.environment.asserted_last)
                validate_build.assert_called_once_with(cache)

    def test_wrapper_separates_build_and_job_rendering(self):
        with mock.patch.object(Runner, "configure"), mock.patch.object(
            Runner.Base, "main", return_value=0
        ) as base_main, mock.patch.object(
            Runner, "_sanitize_job_file"
        ) as sanitize:
            self.assertEqual(Runner.main(["build"]), 0)
        base_main.assert_called_once_with(["build"])
        sanitize.assert_not_called()

        with mock.patch.object(Runner, "configure"), mock.patch.object(
            Runner.Base, "prepare_start_job", return_value=Runner.JOB_FILE
        ) as prepare, mock.patch.object(
            Runner, "_sanitize_job_file"
        ) as sanitize, mock.patch.object(
            Runner, "_validate_job_file", return_value="a" * 64
        ):
            self.assertEqual(Runner.main(["prepare-job"]), 0)
        prepare.assert_called_once_with()
        sanitize.assert_called_once_with()


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

    def row(self, state, exit_code="0:0", task=1):
        return {"array_task": task, "state": state, "exit_code": exit_code}

    def test_only_scheduler_interruptions_are_recoverable(self):
        self.assertEqual(Audit._row_class(self.row("COMPLETED")), "successful")
        for state in ("BOOT_FAIL", "NODE_FAIL", "PREEMPTED", "REVOKED"):
            self.assertEqual(Audit._row_class(self.row(state, "1:0")), "recoverable")
        for state in ("PENDING", "RUNNING", "COMPLETING"):
            self.assertEqual(Audit._row_class(self.row(state)), "active")
        for state, code in (
            ("COMPLETED", "1:0"),
            ("TIMEOUT", "0:0"),
            ("OUT_OF_MEMORY", "0:9"),
            ("CANCELLED", "0:15"),
            ("FAILED", "2:0"),
        ):
            with self.subTest(state=state, code=code):
                with self.assertRaises(Audit.ExecutionAuditError):
                    Audit._row_class(self.row(state, code))

    def test_final_array_element_contains_exactly_two_cells(self):
        self.assertEqual(list(Audit._task_cells(1)), [1, 2, 3])
        self.assertEqual(list(Audit._task_cells(867)), [2599, 2600])

    def test_recovery_command_is_exact_and_unthrottled(self):
        with tempfile.TemporaryDirectory() as tmp:
            wave_dir = Path(tmp) / "wave-0001"
            token = "a" * 24
            command = Recover.submit_command(1, wave_dir, [2, 7], token)
            expected, comment = Audit._expected_recovery_command(
                wave_dir, 1, [2, 7], token
            )
        self.assertEqual(command, expected)
        self.assertIn("--array=2,7", command)
        array_option = next(item for item in command if item.startswith("--array="))
        self.assertNotIn("%", array_option)
        self.assertFalse(any("nice" in item for item in command))
        self.assertIn("--export=NONE", command)
        self.assertIn("--mem-per-cpu=26G", command)
        self.assertEqual(command[0], str(Runner.SBATCH_COMMAND))
        self.assertTrue(all(item.startswith("--") for item in command[1:]))
        self.assertNotIn(str(Runner.JOB_FILE), command)
        self.assertEqual(comment, "pdb-incidence-confirm-a-recovery/1/" + token)

    def test_primary_submit_command_is_options_only(self):
        command = Runner._submit_command("a" * 24)
        self.assertEqual(command[0], "/usr/bin/sbatch")
        self.assertTrue(all(item.startswith("--") for item in command[1:]))
        self.assertNotIn(str(Runner.JOB_FILE), command)
        self.assertIn("--array=1-867", command)
        self.assertIn("--export=NONE", command)

    def test_submission_journal_requires_exact_command_and_full_array(self):
        token = "a" * 24
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
        with tempfile.TemporaryDirectory() as tmp:
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
                "cells": [4],
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

    def test_malformed_recovery_archive_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            wave_dir = Path(tmp) / "wave-0001"
            with self.assertRaises(Audit.ExecutionAuditError):
                Audit._validate_archive(wave_dir, [], None)
            with self.assertRaises(Audit.ExecutionAuditError):
                Audit._validate_archive(
                    wave_dir,
                    [{"run_id": "1", "name": "driver.log"}],
                    [1],
                )
            base = {
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
            with self.assertRaises(Audit.ExecutionAuditError):
                Audit._validate_archive(
                    wave_dir, [{**base, "source": "wrong/driver.log"}], [1]
                )
            with self.assertRaises(Audit.ExecutionAuditError):
                Audit._validate_archive(
                    wave_dir, [{**base, "unexpected": True}], [1]
                )

    def test_recovery_replays_the_whole_array_element(self):
        with mock.patch.object(
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

    def test_reused_auditor_validates_the_confirmation_a_source_set(self):
        with tempfile.TemporaryDirectory(
            prefix=".confirmation-a-source-test-", dir=Audit.SCRIPT_DIR
        ) as tmp:
            path = Path(tmp) / "source.py"
            path.write_bytes(b"synthetic source\n")
            name = path.relative_to(Audit.SCRIPT_DIR).as_posix()
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            with mock.patch.object(Runner, "_source_names", return_value=(name,)):
                Audit._legacy_validate_live_sources({name: digest})
                with self.assertRaises(Audit.Legacy.ExecutionAuditError):
                    Audit._legacy_validate_live_sources({name: "0" * 64})

    def test_legacy_parse_pipeline_uses_extended_execution_receipt(self):
        with mock.patch.object(
            Runner, "load_launch_receipt", return_value=("0" * 64, {})
        ):
            Audit._configure_legacy()
        self.assertIs(
            Audit.Legacy.load_execution_receipt,
            Audit._legacy_load_execution_receipt,
        )


class JobHeaderTest(unittest.TestCase):
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

    def mapping(self):
        declaration = "declare -a SHUFFLED_RUN_IDS=({})".format(
            " ".join(map(str, range(1, P.CELL_COUNT + 1)))
        )
        return "\n".join((
            "# Shuffle runs to avoid systematic bias.",
            declaration,
            "NUM_RUNS=2600",
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

    def header(self, extra="", include_helpers=True, include_mapping=True):
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
            "#SBATCH --array=1-867",
            "#SBATCH --mail-type=NONE",
            "#SBATCH --mail-user=",
            "#SBATCH --account=" + P.ACCOUNT,
        ]
        if extra:
            lines.extend(extra.splitlines())
        if include_helpers:
            lines.append(self.helpers())
        if include_mapping:
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
        with mock.patch.object(
            Runner, "EXPERIMENT_PATH", experiment
        ), mock.patch.object(Runner, "JOB_FILE", job):
            job.write_text(self.header())
            Runner._validate_job_file()
        environment = dict(os.environ)
        environment["SLURM_ARRAY_TASK_ID"] = "1"
        completed = subprocess.run(
            ["/bin/bash", str(job)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=environment, check=False,
        )
        return completed, run_dirs

    def test_exact_header_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / Runner.EXPECTED_JOB_NAME
            path.write_text(self.header())
            with mock.patch.object(Runner, "JOB_FILE", path):
                digest = Runner._validate_job_file()
                self.assertRegex(digest, r"^[0-9a-f]{64}$")
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
        content = self.header("#SBATCH --nice=0").replace(hardened, legacy)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / Runner.EXPECTED_JOB_NAME
            path.write_text(content)
            with mock.patch.object(Runner, "JOB_FILE", path):
                Runner._sanitize_job_file()
                sanitized = path.read_text()
        self.assertIn(hardened, sanitized)
        self.assertNotIn(legacy, sanitized)
        self.assertNotIn("#SBATCH --nice", sanitized)
        self.assertNotIn(") > driver.log 2> driver.err", sanitized)

    def test_throttle_and_nice_are_rejected(self):
        cases = (
            self.header("#SBATCH --nice=1"),
            self.header("#SBATCH --nice 1"),
            self.header().replace("#SBATCH --array=1-867", "#SBATCH --array=1-867%10"),
        )
        for content in cases:
            with self.subTest(content=content.splitlines()[-2:]):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / Runner.EXPECTED_JOB_NAME
                    path.write_text(content)
                    with mock.patch.object(Runner, "JOB_FILE", path):
                        with self.assertRaises(Runner.ConfirmationLaunchError):
                            Runner._validate_job_file()

    def test_scheduler_directives_must_be_the_leading_ordered_header(self):
        lines = self.header().splitlines()
        partition = "#SBATCH --partition=fat"
        late_one = [line for line in lines if line != partition] + [partition]
        directives = [line for line in lines if line.startswith("#SBATCH")]
        all_late = [
            lines[0],
            *[line for line in lines[1:] if not line.startswith("#SBATCH")],
            *directives,
        ]
        for mutated in (late_one, all_late):
            with self.subTest(last=mutated[-1]):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / Runner.EXPECTED_JOB_NAME
                    path.write_text("\n".join(mutated) + "\n")
                    with mock.patch.object(Runner, "JOB_FILE", path):
                        with self.assertRaises(Runner.ConfirmationLaunchError):
                            Runner._validate_job_file()

    def test_duplicate_or_conflicting_scheduler_contract_is_rejected(self):
        conflicts = (
            "#SBATCH --job-name=other",
            "#SBATCH --partition=thin",
            "#SBATCH --partition thin",
            "#SBATCH -p thin",
            "#SBATCH -J other",
            "#SBATCH --qos=low",
            "#SBATCH --time=02:00:00",
            "#SBATCH -t 02:00:00",
            "#SBATCH --mem-per-cpu=30G",
            "#SBATCH --mem=30G",
            "#SBATCH --cpus-per-task=2",
            "#SBATCH -c 2",
            "#SBATCH --array=1-866",
            "#SBATCH -a 1-866",
            "#SBATCH --account=other",
            "#SBATCH -A other",
            "#SBATCH --ntasks=2",
            "#SBATCH --nodes=2",
            "#SBATCH --exclusive",
            "#SBATCH --requeue",
            "#SBATCH --export=ALL",
            "NUM_RUNS=2599",
            "RUNS_PER_TASK=4",
        )
        for conflict in conflicts:
            with self.subTest(conflict=conflict):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / Runner.EXPECTED_JOB_NAME
                    path.write_text(self.header(conflict))
                    with mock.patch.object(Runner, "JOB_FILE", path):
                        with self.assertRaises(Runner.ConfirmationLaunchError):
                            Runner._validate_job_file()

    def test_absent_or_changed_run_mapping_is_rejected(self):
        cases = (
            self.header(include_helpers=False, include_mapping=False),
            self.header(include_mapping=False),
            self.header("exit 0"),
            self.header("echo unexpected-command"),
            self.header().replace(
                " --run-script run ",
                " --run-script changed ",
                1,
            ),
            self.header().replace(
                "declare -a SHUFFLED_RUN_IDS=(1 2 3",
                "declare -a SHUFFLED_RUN_IDS=(2 1 3",
                1,
            ),
            self.header().replace(
                'let "END_INDEX=START_INDEX + RUNS_PER_TASK - 1"',
                'let "END_INDEX=START_INDEX + RUNS_PER_TASK"',
                1,
            ),
        )
        for content in cases:
            with self.subTest(has_mapping="SHUFFLED_RUN_IDS" in content):
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / Runner.EXPECTED_JOB_NAME
                    path.write_text(content)
                    with mock.patch.object(Runner, "JOB_FILE", path):
                        with self.assertRaises(Runner.ConfirmationLaunchError):
                            Runner._validate_job_file()

    def test_submission_timestamp_must_be_canonical_utc(self):
        Runner._validate_recorded_utc("2026-09-01T12:34:56+00:00")
        for value in (
            "2026-09-01T12:34:56",
            "2026-09-01T14:34:56+02:00",
            "2026-09-01T12:34:56.123456+00:00",
        ):
            with self.subTest(value=value):
                with self.assertRaises(Runner.ConfirmationLaunchError):
                    Runner._validate_recorded_utc(value)


def _comparison(
    i_value=0.70, control_value=0.60, d_value=None,
    families=10, pairs=100, tasks=50,
):
    i_value = Fraction(str(i_value))
    control_value = Fraction(str(control_value))
    d_value = control_value if d_value is None else Fraction(str(d_value))
    family_names = ["family-{:02d}".format(i) for i in range(families)]

    predictors = {}
    for key in P.PREDICTORS:
        value = i_value if key == "I" else d_value if key == "D" else control_value
        predictors[key] = {
            "equal_family": {
                "macro": Analyze.Original._fraction_record(value)
            },
            "_family_values": {
                family: value for family in family_names
            },
            "_family_lodo": {
                family: value for family in family_names
            },
        }
    return {
        "protocol": Analyze.Original.TIE_AWARE_COMPARISON_PROTOCOL,
        "support": {
            "tasks_with_shared_pairs": tasks,
            "families_with_shared_pairs": families,
            "target_strict": pairs,
        },
        "target_orientations": {
            "orders_identical": True,
            "inverse_U_null": "tied_within_task",
        },
        "predictors": predictors,
    }


class AnalysisGateTest(unittest.TestCase):
    def test_stratum_returns_selected_frontier_and_comparison(self):
        task = ("directory", "p01.pddl")
        comparison = _comparison()
        with mock.patch.object(
            P, "DIRECTORY_TO_FAMILY", {"directory": "family"}
        ), mock.patch.object(
            Analyze.Original, "target_strict_tie_aware_comparison",
            return_value=comparison,
        ), mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100):
            result = Analyze._stratum(
                {task: {"a": {}}}, {task: {"g": 1}}, ("family",),
                gating=True,
            )
        self.assertTrue(result["gating"])
        self.assertEqual(result["eligible_tasks"], 1)
        self.assertEqual(result["eligible_families"], 1)
        self.assertEqual(result["comparison"]["protocol"], comparison["protocol"])

    def test_primary_gate_uses_target_strict_support(self):
        comparison = _comparison(
            families=25, pairs=600, tasks=300
        )
        with mock.patch.object(
            Analyze.Original, "P", P
        ), mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100), (
            Analyze._ordering_predictors(True)
        ):
            gate = Analyze.Original.primary_gates(
                comparison, 300, 25
            )
        self.assertTrue(gate["pass"])
        self.assertEqual(
            gate["support"]["comparison_pair_definition"], "target_strict"
        )
        comparison["support"]["target_strict"] = 599
        with mock.patch.object(
            Analyze.Original, "P", P
        ), mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100), (
            Analyze._ordering_predictors(True)
        ):
            gate = Analyze.Original.primary_gates(comparison, 300, 25)
        self.assertFalse(gate["support"]["pass"])

    def test_masked_add_size_independently_gates_both_confirmations(self):
        comparison = _comparison(
            d_value=0.70, families=25, pairs=600, tasks=300
        )
        with mock.patch.object(
            Analyze.Original, "P", P
        ), mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100), (
            Analyze._ordering_predictors(True)
        ):
            primary = Analyze.Original.primary_gates(comparison, 300, 25)
        self.assertFalse(primary["pass"])
        self.assertFalse(primary["controls"]["D"]["pass"])

        comparison = _comparison(d_value=0.70)
        with mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100):
            stratum = Analyze._stratum_gate(comparison)
        self.assertFalse(stratum["pass"])
        self.assertFalse(stratum["controls"]["D"]["pass"])

    def test_new_family_gate_passes_only_strict_control_advantages(self):
        with mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100):
            gate = Analyze._stratum_gate(_comparison())
            self.assertTrue(gate["pass"])
            too_small = Analyze._stratum_gate(
                _comparison(control_value=0.69)
            )
        self.assertFalse(too_small["pass"])
        self.assertFalse(too_small["controls"]["kD"]["advantage_pass"])

    def test_new_family_support_floor_is_binding(self):
        with mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100):
            self.assertFalse(Analyze._stratum_gate(
                _comparison(tasks=49)
            )["pass"])
            self.assertFalse(Analyze._stratum_gate(
                _comparison(families=9)
            )["pass"])
            self.assertFalse(Analyze._stratum_gate(
                _comparison(pairs=99)
            )["pass"])

    def test_new_family_gate_requires_bootstrap_and_lodo_robustness(self):
        comparison = _comparison()
        bad_bootstrap = {
            control: {
                "families": 10,
                "observed_difference": {"numerator": 1, "denominator": 10},
                "lower_95": {"numerator": 0, "denominator": 1},
                "upper_95": {"numerator": 1, "denominator": 10},
            }
            for control in P.PREDICTOR_BASELINES
        }
        with mock.patch.object(
            Analyze.Original, "_bootstrap_differences",
            return_value=bad_bootstrap,
        ):
            self.assertFalse(Analyze._stratum_gate(comparison)["pass"])

        comparison["predictors"]["kD"]["_family_lodo"][
            "family-00"
        ] = Fraction(7, 10)
        with mock.patch.object(P, "BOOTSTRAP_REPLICATES", 100):
            gate = Analyze._stratum_gate(comparison)
        self.assertFalse(gate["pass"])
        self.assertFalse(
            gate["controls"]["kD"][
                "every_leave_one_family_out_positive"
            ]
        )

    def test_target_strict_comparison_scores_predictor_ties_half(self):
        predictors = P.PREDICTORS

        def observation(semantic_id, target, primary, d_value, kd, other):
            row = {
                "semantic_id": semantic_id,
                "U": 10,
                "E": target,
                "I": primary,
                "D": d_value,
                "kD": kd,
            }
            row.update({key: other for key in P.CERTIFICATE_BASELINES[1:]})
            return row

        grouped = {("directory", "p01.pddl"): {
            "a": observation("a", 1, 1, 1, 1, 1),
            "b": observation("b", 2, 2, 1, 1, 2),
            "c": observation("c", 2, 3, 1, 1, 3),
        }}
        with mock.patch.object(Analyze.Original, "P", P), mock.patch.object(
            P, "DIRECTORY_TO_FAMILY", {"directory": "family"}
        ), mock.patch.object(P, "DIRECTORIES", ("directory",)), (
            Analyze._ordering_predictors(True)
        ):
            tie_aware = (
                Analyze.Original.target_strict_tie_aware_comparison(grouped)
            )
            strict = Analyze.Original.grand_shared_comparison(grouped)
        self.assertEqual(tie_aware["support"]["semantic_pairs"], 3)
        self.assertEqual(tie_aware["support"]["target_tied"], 1)
        self.assertEqual(tie_aware["support"]["target_strict"], 2)
        self.assertEqual(tie_aware["predictors"]["I"]["comparable"], 2)
        self.assertEqual(tie_aware["predictors"]["kD"]["tied"], 2)
        self.assertEqual(tie_aware["predictors"]["D"]["tied"], 2)
        self.assertEqual(
            tie_aware["predictors"]["kD"]["micro_concordance"],
            {"numerator": 1, "denominator": 2, "value": 0.5},
        )
        self.assertEqual(
            tie_aware["predictors"]["kD"]["tie_rate"],
            {"numerator": 1, "denominator": 1, "value": 1.0},
        )
        self.assertEqual(strict["support"].get("grand_shared_strict", 0), 0)

    def test_top_choice_regret_averages_predictor_ties(self):
        predictors = P.PREDICTORS
        left = {
            "semantic_id": "a", "E": 1, "I": 1, "D": 2, "kD": 1,
            **{key: 2 for key in P.CERTIFICATE_BASELINES[1:]},
        }
        right = {
            "semantic_id": "b", "E": 3, "I": 2, "D": 1, "kD": 1,
            **{key: 1 for key in P.CERTIFICATE_BASELINES[1:]},
        }
        grouped = {("directory", "p01.pddl"): {"a": left, "b": right}}
        with mock.patch.object(
            P, "DIRECTORY_TO_FAMILY", {"directory": "family"}
        ):
            result = Analyze._top_choice_regret(grouped)
        self.assertFalse(result["gating"])
        self.assertEqual(
            result["predictors"]["I"]["equal_family_normalized_regret"],
            {"numerator": 0, "denominator": 1, "value": 0.0},
        )
        self.assertEqual(
            result["predictors"]["kD"]["equal_family_normalized_regret"],
            {"numerator": 1, "denominator": 2, "value": 0.5},
        )
        self.assertEqual(
            result["predictors"]["kD"]["top_choice_tie_rate"],
            {"numerator": 1, "denominator": 1, "value": 1.0},
        )
        self.assertEqual(
            result["predictors"]["D"]["equal_family_normalized_regret"],
            {"numerator": 1, "denominator": 1, "value": 1.0},
        )

    def test_masked_add_size_is_reconstructed_from_certified_layers(self):
        observation = {
            "E": 10,
            "I": 12,
            "masked_add_node_sum": 7,
            "layers": [
                {"masked_add_nodes": 3},
                {"masked_add_nodes": 4},
            ],
        }
        primary = {"observations": [observation]}
        Analyze._add_masked_add_size(primary)
        self.assertGreater(observation["E"], observation["D"])
        self.assertEqual(observation["D"], 7)
        self.assertEqual([row["D"] for row in observation["layers"]], [3, 4])

        malformed = {
            "observations": [{
                "masked_add_node_sum": 8,
                "layers": [{"masked_add_nodes": 7}],
            }]
        }
        with self.assertRaisesRegex(
            Analyze.ConfirmationAnalysisError, "differs"
        ):
            Analyze._add_masked_add_size(malformed)

    def test_double_analysis_publishes_only_identical_bytes(self):
        result = {
            "schema": Analyze.SCHEMA,
            "analysis_protocol": P.ANALYSIS_PROTOCOL,
            "gates": {"pass": True},
            "guided_study_authorized": True,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            properties = root / "properties"
            properties.write_text("{}")
            outputs = (
                root / "analysis.json",
                root / "repeat.json",
                root / "receipt.json",
                root / "receipt.sha256",
            )
            with mock.patch.object(
                Analyze, "_load_sealed_input",
                side_effect=[([], "1" * 64, "2" * 64), ([], "1" * 64, "2" * 64)],
            ), mock.patch.object(
                Analyze, "analyze_records", side_effect=[dict(result), dict(result)]
            ):
                receipt = Analyze.run_twice(properties, *outputs)
            self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
            self.assertTrue(receipt["outputs_byte_identical"])
            self.assertTrue(receipt["confirmation_a_complete_gate_passed"])
            stored = json.loads(outputs[2].read_text())
            self.assertTrue(stored["confirmation_a_complete_gate_passed"])
            self.assertEqual(
                outputs[3].read_text().strip(),
                receipt["analysis_receipt_sha256"],
            )
            loaded_sha, loaded_receipt, loaded_analysis = (
                Analyze.load_analysis_receipt(
                    receipt_path=outputs[2],
                    receipt_pin=outputs[3],
                    output=outputs[0],
                    repeat_output=outputs[1],
                    verify_live=False,
                )
            )
            self.assertEqual(loaded_sha, receipt["analysis_receipt_sha256"])
            self.assertTrue(
                loaded_receipt["confirmation_a_complete_gate_passed"]
            )
            self.assertTrue(loaded_analysis["gates"]["pass"])

    def test_nondeterministic_analysis_publishes_nothing(self):
        first = {
            "schema": Analyze.SCHEMA,
            "analysis_protocol": P.ANALYSIS_PROTOCOL,
            "gates": {"pass": True},
            "guided_study_authorized": True,
            "nonce": 1,
        }
        second = {**first, "nonce": 2}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            properties = root / "properties"
            properties.write_text("{}")
            outputs = tuple(root / name for name in (
                "analysis.json", "repeat.json", "receipt.json", "receipt.sha256"
            ))
            with mock.patch.object(
                Analyze, "_load_sealed_input",
                side_effect=[([], "1" * 64, "2" * 64), ([], "1" * 64, "2" * 64)],
            ), mock.patch.object(
                Analyze, "analyze_records", side_effect=[first, second]
            ):
                with self.assertRaisesRegex(
                    Analyze.ConfirmationAnalysisError, "byte-identical"
                ):
                    Analyze.run_twice(properties, *outputs)
            self.assertFalse(any(path.exists() for path in outputs))


if __name__ == "__main__":
    unittest.main()
