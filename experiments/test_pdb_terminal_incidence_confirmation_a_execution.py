#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import analyze_pdb_terminal_incidence_confirmation_a as Analyze
import audit_pdb_terminal_incidence_confirmation_a as Audit
import exp_pdb_terminal_incidence_confirmation_a as Runner
import pdb_terminal_incidence_confirmation_a_protocol as P
import recover_pdb_terminal_incidence_confirmation_a as Recover


class SchedulerContractTest(unittest.TestCase):
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
        self.assertEqual(comment, "pdb-incidence-confirm-a-recovery/1/" + token)

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
            }
            with self.assertRaises(Audit.ExecutionAuditError):
                Audit._validate_archive(
                    wave_dir, [{**base, "source": "wrong/driver.log"}], [1]
                )
            with self.assertRaises(Audit.ExecutionAuditError):
                Audit._validate_archive(
                    wave_dir, [{**base, "unexpected": True}], [1]
                )

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

    def test_exact_header_is_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / Runner.EXPECTED_JOB_NAME
            path.write_text(self.header())
            with mock.patch.object(Runner, "JOB_FILE", path):
                self.assertRegex(Runner._validate_job_file(), r"^[0-9a-f]{64}$")

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
                '    "{}" run'.format(Path(Runner.sys.executable)),
                "    true",
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


def _comparison(i_value=0.70, control_value=0.60, families=10, pairs=100):
    def fraction(value):
        return {
            "numerator": int(round(value * 100)),
            "denominator": 100,
            "value": value,
        }

    predictors = {
        key: {"equal_family": {"macro": fraction(
            i_value if key == "I" else control_value
        )}}
        for key in Analyze.Original.PREDICTORS
    }
    return {
        "support": {
            "families_with_shared_pairs": families,
            "grand_shared_strict": pairs,
        },
        "target_orientations": {
            "orders_identical": True,
            "inverse_U_null": "tied_within_task",
        },
        "predictors": predictors,
    }


class AnalysisGateTest(unittest.TestCase):
    def test_new_family_gate_passes_only_strict_control_advantages(self):
        gate = Analyze._stratum_gate(_comparison())
        self.assertTrue(gate["pass"])
        tied = Analyze._stratum_gate(_comparison(control_value=0.70))
        self.assertFalse(tied["pass"])
        self.assertFalse(tied["controls"]["kD"]["strictly_positive"])

    def test_new_family_support_floor_is_binding(self):
        self.assertFalse(Analyze._stratum_gate(
            _comparison(families=9)
        )["pass"])
        self.assertFalse(Analyze._stratum_gate(
            _comparison(pairs=99)
        )["pass"])

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
