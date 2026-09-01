#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import audit_pdb_terminal_incidence_confirmation_b as Audit
import exp_pdb_terminal_incidence_confirmation_b as Runner
import pdb_terminal_incidence_confirmation_b_protocol as P
import recover_pdb_terminal_incidence_confirmation_b as Recover


TASKS = 200
CELLS = 9 * TASKS
ARRAY_TASKS = CELLS // 3


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
            self.assertEqual(
                comment, "pdb-incidence-confirm-b-recovery/1/" + token
            )

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
            }
            Audit._validate_archive(wave, [base], [1])
            for item in (
                {**base, "source": "wrong/driver.log"},
                {**base, "unexpected": True},
                {**base, "size": 1},
            ):
                with self.assertRaises(Audit.ExecutionAuditError):
                    Audit._validate_archive(wave, [item], [1])


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
            "function execute_run {",
            "    if [[ -f driver.log ]]; then",
            '        echo "The run in $(pwd) has already been started --> skip it"',
            "        return",
            "    fi",
            "",
            "    (",
            '    "{}" run'.format(Path(Runner.sys.executable)),
            "    RETCODE=$?",
            "    if [[ $RETCODE != 0 ]]; then",
            '        >&2 echo "The run script finished with exit code $RETCODE"',
            "    fi",
            "    ) > driver.log 2> driver.err",
            "",
            "    # Delete empty driver.err files. driver.log always has content "
            "(for started runs).",
            "    if [[ ! -s driver.err ]]; then",
            "        rm driver.err",
            "    fi",
            "}",
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
        self.validate(self.job(), passes=True)

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
            self.job().replace('    "{}" run'.format(Path(Runner.sys.executable)),
                               "    python run"),
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


if __name__ == "__main__":
    unittest.main()
