#!/usr/bin/env python3
"""Regression tests for full source-audit campaign v4."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import audit_pdb_terminal_incidence_confirmation_sources_v4 as Source
import launch_pdb_terminal_incidence_confirmation_source_audit_v4 as Launch
import recover_pdb_terminal_incidence_confirmation_source_audit_v4 as Recovery


class SourceAuditV4Test(unittest.TestCase):
    @staticmethod
    def _rows() -> list[dict]:
        return [
            {
                "array_task": index,
                "state": "COMPLETED",
                "exit_code": "0:0",
                "elapsed": "00:00:01",
                "partition": "fat",
            }
            for index in range(Launch.ARRAY_TASKS)
        ]

    def test_resource_and_full_rerun_contract_is_exact(self) -> None:
        self.assertEqual(Source.TASK_TIMEOUT_SECONDS, 14400)
        self.assertEqual(Launch.MEMORY_PER_CPU, "1024G")
        self.assertEqual(Launch.TIME_LIMIT, "08:20:00")
        self.assertEqual(Launch.ARRAY_TASKS, 820)
        self.assertEqual(Source.CANDIDATE_COUNT, 1640)
        self.assertTrue(str(Source.TMP_ROOT).startswith(str(Launch.REPO)))
        self.assertNotIn("/tmp/", Source.TMPDIR_TEMPLATE)
        self.assertEqual(
            Source.PYTHON_CACHE_PREFIX_TEMPLATE,
            Source.TMPDIR_TEMPLATE + "/pycache",
        )

    def test_v4_manifest_binds_complete_v3_and_v4_boundary(self) -> None:
        v3_manifest = (
            Launch.SCRIPT_DIR /
            "pdb_terminal_incidence_confirmation_source_audit_v3_code.sha256"
        )
        v3_bound = {
            line.split("  ", 1)[1]
            for line in v3_manifest.read_text(encoding="ascii").splitlines()
        }
        self.assertEqual(len(v3_bound), 14)
        expected_v3 = {
            *v3_bound,
            "experiments/pdb_terminal_incidence_confirmation_source_audit_v3_code.sha256",
            "experiments/pdb_terminal_incidence_confirmation_source_scan_v3.slurm",
            "experiments/artifacts/pdb-terminal-incidence-confirmation-v3/"
            "source-audit-launch-intent-v3.json",
            "experiments/artifacts/pdb-terminal-incidence-confirmation-v3/"
            "source-audit-launch-receipt-v3.json",
        }
        self.assertTrue(expected_v3 <= set(Source.CODE_MANIFEST_FILES))
        for relative in (
            "experiments/audit_pdb_terminal_incidence_confirmation_sources_v4.py",
            "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v4.py",
            "experiments/recover_pdb_terminal_incidence_confirmation_source_audit_v4.py",
            "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_protocol.md",
            "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v4.py",
            "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
            "v3-infrastructure-failure-diagnostic.json",
        ):
            self.assertIn(relative, Source.CODE_MANIFEST_FILES)
        self.assertEqual(
            set(Launch.SCOPED_COMMIT_FILES),
            {
                *Source.CODE_MANIFEST_FILES,
                Launch.SLURM_SCRIPT.relative_to(Launch.REPO).as_posix(),
                Launch.CODE_MANIFEST.relative_to(Launch.REPO).as_posix(),
            },
        )

    def test_submit_command_is_unthrottled_closed_and_original_only(self) -> None:
        command = Launch._submit_command(
            Launch.SOURCE_INVENTORY_SHA256, Launch.OUTPUT_DIR, "a" * 24
        )
        job_name, comment = Launch._submission_identity("a" * 24)
        self.assertEqual(command, [
            "/usr/bin/sbatch", "--parsable", "--export=NONE",
            "--job-name=" + job_name,
            "--comment=" + comment,
            "--account=" + Launch.ACCOUNT,
            "--partition=fat", "--qos=normal", "--array=0-819",
            "--nodes=1", "--ntasks=1", "--cpus-per-task=1",
            "--mem-per-cpu=1024G", "--time=08:20:00", "--nice=0",
            "--no-requeue", "--chdir=" + str(Launch.REPO),
            "--output=" + str(Launch.OUTPUT_DIR / "slurm-%A_%a.out"),
        ])
        for option in (
            "/usr/bin/sbatch", "--parsable", "--export=NONE",
            "--account=" + Launch.ACCOUNT, "--partition=fat", "--qos=normal",
            "--array=0-819", "--nodes=1", "--ntasks=1",
            "--cpus-per-task=1", "--mem-per-cpu=1024G",
            "--time=08:20:00", "--nice=0", "--no-requeue",
            "--chdir=" + str(Launch.REPO),
        ):
            self.assertEqual(command.count(option), 1)
        self.assertFalse(any(
            "%" in option for option in command if option.startswith("--array=")
        ))
        self.assertTrue(all(option.startswith("--") for option in command[1:]))
        self.assertNotIn(str(Launch.SLURM_SCRIPT), command)
        self.assertNotIn(Launch.SOURCE_INVENTORY_SHA256, command)
        self.assertEqual(command[-1], "--output=" + str(
            Launch.OUTPUT_DIR / "slurm-%A_%a.out"
        ))
        self.assertEqual(
            Launch.SUBMISSION_ENVIRONMENT,
            {"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )

    def test_submit_rejects_wrong_inventory_or_output_namespace(self) -> None:
        with self.assertRaises(Launch.LaunchAuditError):
            Launch._submit_command("0" * 64, Launch.OUTPUT_DIR, "a" * 24)
        with self.assertRaises(Launch.LaunchAuditError):
            Launch._submit_command(
                Launch.SOURCE_INVENTORY_SHA256,
                Launch.OUTPUT_DIR.parent / "other",
                "a" * 24,
            )

    def test_recovery_is_unconditionally_disabled(self) -> None:
        for function in (
            Recovery.preview, Recovery.launch, Recovery.recover_launch,
            Recovery.status, Recovery.seal,
        ):
            with self.assertRaises(Recovery.RecoveryError):
                function()
        with self.assertRaises(Recovery.RecoveryError):
            Recovery.main(["preview"])

    def test_only_all_success_original_rows_are_accepted(self) -> None:
        rows = self._rows()
        Launch._validate_original_success_rows(rows)
        for field, value in (
            ("state", "OUT_OF_MEMORY"),
            ("exit_code", "1:0"),
            ("array_task", False),
        ):
            changed = [dict(row) for row in rows]
            changed[11][field] = value
            with self.assertRaises(Launch.LaunchAuditError):
                Launch._validate_original_success_rows(changed)

    def test_v3_diagnostic_refuses_active_array(self) -> None:
        rows = self._rows()
        rows[5]["state"] = "RUNNING"
        with (
            mock.patch.object(Launch, "_v3_fixed_launch_provenance", return_value={}),
            mock.patch.object(Launch, "_scheduler_rows", return_value=rows),
        ):
            with self.assertRaisesRegex(
                Launch.LaunchAuditError, "not fully terminal"
            ):
                Launch._expected_v3_diagnostic()

    def test_v3_diagnostic_dynamically_pins_all_infrastructure_classes(self) -> None:
        rows = self._rows()
        rows[150].update(state="FAILED", exit_code="75:0")
        rows[200].update(state="FAILED", exit_code="2:0")
        rows[209].update(state="FAILED", exit_code="75:0")
        rows[488].update(state="OUT_OF_MEMORY", exit_code="0:125")
        rows[716].update(state="OUT_OF_MEMORY", exit_code="0:125")
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-diag-") as tmp:
            root = Path(tmp)
            empty_sha = hashlib.sha256(b"").hexdigest().encode("ascii")
            (root / "slurm-1863146_150.out").write_bytes(
                b"[1/2] flashfill-sat18-adl:p20.pddl\n"
                b"infrastructure error: translator exceeded 7200s for "
                b"flashfill-sat18-adl:p20.pddl; stderr_sha256="
                + empty_sha + b"; stderr_tail=''\n"
            )
            (root / "slurm-1863146_200.out").write_bytes(
                b"[1/2] labyrinth:p20.pddl\n"
                b"sas_task.output(output_file)\n"
                b"OSError: [Errno 28] No space left on device\n"
            )
            (root / "slurm-1863146_209.out").write_bytes(
                b"[2/2] labyrinth-sat23-adl:p18.pddl\n"
                b"sas_task.output(output_file)\n"
                b"OSError: [Errno 28] No space left on device\n"
                b"infrastructure error: translator exceeded 7200s for "
                b"labyrinth-sat23-adl:p18.pddl; stderr_sha256="
                + b"1" * 64
                + b"; stderr_tail='sas_task.output(output_file)\\n"
                b"OSError: [Errno 28] No space left on device'\n"
            )
            (root / "slurm-1863146_488.out").write_bytes(
                b"[1/2] organic-synthesis:p13.pddl\n"
                b"translator critical exit -9\n"
                b"oom_kill\n"
            )
            (root / "slurm-1863146_716.out").write_bytes(
                b"[2/2] slitherlink-opt23-adl:p08.pddl\n"
                b"translator critical exit -9\n"
                b"oom_kill\n"
            )
            oom_rows = [
                {"array_task": task, "rows": [{
                    "job_id": "1863146_{}.batch".format(task),
                    "job_id_raw": "1863659.batch",
                    "state": "OUT_OF_MEMORY",
                    "exit_code": "0:125",
                    "requested_memory": None,
                    "max_rss": "458903924K",
                    "max_vm_size": "536114068K",
                }]}
                for task in (488, 716)
            ]
            timeout_rows = [
                {"array_task": task, "rows": [{
                    "job_id": "1863146_{}.batch".format(task),
                    "job_id_raw": "1863659.batch",
                    "state": "FAILED",
                    "exit_code": "75:0",
                    "elapsed": "02:00:09",
                    "requested_memory": None,
                    "max_rss": "214000000K",
                    "max_vm_size": "220000000K",
                }]}
                for task in (150, 209)
            ]
            with (
                mock.patch.object(Launch, "V3_OUTPUT_DIR", root),
                mock.patch.object(
                    Launch, "_v3_fixed_launch_provenance", return_value={}
                ),
                mock.patch.object(Launch, "_scheduler_rows", return_value=rows),
                mock.patch.object(
                    Launch, "_v3_oom_resource_rows", return_value=oom_rows
                ),
                mock.patch.object(
                    Launch, "_v3_timeout_resource_rows",
                    return_value=timeout_rows,
                ),
            ):
                value = Launch._expected_v3_diagnostic()
        self.assertEqual(value["v3_enospc_array_tasks"], [200])
        self.assertEqual(value["v3_out_of_memory_array_tasks"], [488, 716])
        self.assertEqual(value["v3_translator_timeout_array_tasks"], [150, 209])
        self.assertEqual(value["v3_pure_translator_timeout_array_tasks"], [150])
        self.assertEqual(
            value["v3_translator_timeout_with_enospc_array_tasks"], [209]
        )
        self.assertEqual(len(value["v3_failure_logs"]), 5)
        self.assertFalse(value["successful_v3_shard_contents_inspected"])
        self.assertFalse(value["successful_v3_log_contents_inspected"])
        self.assertEqual(
            value["full_rerun_decision"]["scope"],
            "all-820-original-shards-and-1640-candidates",
        )
        self.assertEqual(value["full_rerun_decision"]["reused_v3_shards"], 0)
        self.assertEqual(
            value["resource_amendment"]["memory_per_cpu"]["to"], "1024G"
        )
        self.assertEqual(
            value["resource_amendment"]["temporary_storage"]["to"],
            Source.TMPDIR_TEMPLATE,
        )
        self.assertEqual(
            value["resource_amendment"]["task_timeout_seconds"]["to"], 14400
        )
        self.assertEqual(
            value["resource_amendment"]["time_limit"]["to"], "08:20:00"
        )

    def test_v3_diagnostic_rejects_unclassified_failure(self) -> None:
        rows = self._rows()
        rows[7].update(state="TIMEOUT", exit_code="0:0")
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-diag-") as tmp:
            root = Path(tmp)
            (root / "slurm-1863146_7.out").write_bytes(
                b"[1/2] task:p01.pddl\nTIMEOUT\n"
            )
            with (
                mock.patch.object(Launch, "V3_OUTPUT_DIR", root),
                mock.patch.object(
                    Launch, "_v3_fixed_launch_provenance", return_value={}
                ),
                mock.patch.object(Launch, "_scheduler_rows", return_value=rows),
            ):
                with self.assertRaisesRegex(
                    Launch.LaunchAuditError, "unclassified terminal failure"
                ):
                    Launch._expected_v3_diagnostic()

    def test_v3_timeout_accounting_is_pinned_without_fixed_task_ids(self) -> None:
        output = (
            "1863146_17|1863146_17|FAILED|75:0|02:00:09|512G||\n"
            "1863146_17.batch|1864000.batch|FAILED|75:0|02:00:08||"
            "214000000K|220000000K\n"
        )
        with mock.patch.object(Launch, "_sacct", return_value=output):
            records = Launch._v3_timeout_resource_rows([17])
        self.assertEqual([record["array_task"] for record in records], [17])
        self.assertEqual(records[0]["rows"][0]["requested_memory"], "512G")
        self.assertEqual(records[0]["rows"][1]["max_rss"], "214000000K")

    def test_tmpdir_validation_binds_slurm_path_mode_owner_and_emptiness(self) -> None:
        self.addCleanup(setattr, tempfile, "tempdir", None)
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-tmp-") as tmp:
            root = Path(tmp) / "root"
            root.mkdir(mode=0o700)
            task = root / "task-123-7"
            task.mkdir(mode=0o700)
            template = str(root / "task-{array_job_id}-{array_task_id}")
            environment = {
                "SLURM_ARRAY_JOB_ID": "123",
                "SLURM_ARRAY_TASK_ID": "7",
                "TMPDIR": str(task),
                "PYTHONPYCACHEPREFIX": str(task / "pycache"),
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": Source.CONTROLLED_PATH,
            }
            with (
                mock.patch.object(Source, "TMP_ROOT", root),
                mock.patch.object(Source, "TMPDIR_TEMPLATE", template),
                mock.patch.object(
                    Source.Base, "PYTHON_CACHE_PREFIX_TEMPLATE",
                    template + "/pycache",
                ),
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(
                    Source, "_base_validate_execution_environment",
                    return_value=None,
                ),
            ):
                Source.validate_execution_environment()
                (task / "residue").write_text("x", encoding="ascii")
                with self.assertRaisesRegex(
                    Source.SourceAuditError, "not empty"
                ):
                    Source.validate_execution_environment()

    def test_scan_emits_shard_bound_task_environment_attestation(self) -> None:
        self.addCleanup(setattr, tempfile, "tempdir", None)
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-env-") as tmp:
            base = Path(tmp)
            root = base / "tmp-root"
            root.mkdir(mode=0o700)
            task = root / "task-123-7"
            task.mkdir(mode=0o700)
            output = base / "output"
            output.mkdir(mode=0o700)
            template = str(root / "task-{array_job_id}-{array_task_id}")
            args = SimpleNamespace(
                shard_index=7,
                num_shards=Source.SHARD_COUNT,
                output_dir=output,
                code_manifest=base / "manifest",
                code_manifest_sha256="a" * 64,
                inventory_sha256="b" * 64,
            )
            code = {
                "code_manifest_sha256": "a" * 64,
                "python_version": "3.12.13",
                "python_executable": Source.Base.PINNED_PYTHON_EXECUTABLE,
                "python_executable_sha256": (
                    Source.Base.PINNED_PYTHON_EXECUTABLE_SHA256
                ),
                "python_environment_sha256": (
                    Source.Base.PINNED_PYTHON_ENVIRONMENT_SHA256
                ),
                "python_distributions": {},
                "python_requirements_sha256": (
                    Source.Base.PINNED_REQUIREMENTS_SHA256
                ),
            }
            environment = {
                "SLURM_ARRAY_JOB_ID": "123",
                "SLURM_ARRAY_TASK_ID": "7",
                "TMPDIR": str(task),
                "PYTHONPYCACHEPREFIX": str(task / "pycache"),
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PATH": Source.CONTROLLED_PATH,
            }

            def fake_scan(scan_args) -> None:
                Source.Base._atomic_json(
                    Source.shard_path(
                        scan_args.output_dir,
                        scan_args.shard_index,
                        scan_args.num_shards,
                    ),
                    {"synthetic": True},
                )

            with (
                mock.patch.object(Source, "TMP_ROOT", root),
                mock.patch.object(Source, "TMPDIR_TEMPLATE", template),
                mock.patch.object(
                    Source.Base, "PYTHON_CACHE_PREFIX_TEMPLATE",
                    template + "/pycache",
                ),
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(
                    Source, "_base_validate_execution_environment",
                    return_value=None,
                ),
                mock.patch.object(Source.Base, "scan", side_effect=fake_scan),
                mock.patch.object(
                    Source.Base, "validate_code_manifest", return_value=code
                ),
            ):
                Source.scan(args)
                shard = Source.shard_path(output, 7)
                value = Source.load_task_environment_attestation(
                    Source.task_environment_path(output, 7),
                    index=7,
                    array_job_id="123",
                    inventory_sha256="b" * 64,
                    code_manifest_sha256="a" * 64,
                    code=code,
                    shard_sha256=Source.sha256_file(shard),
                )
            self.assertEqual(value["tmpdir"], str(task))
            self.assertTrue(value["tmpdir_empty_after_scan"])
            self.assertEqual(
                value["output_dir_identity_before"],
                value["output_dir_identity_after"],
            )
            self.assertEqual(
                value["source_snapshot_policy"], Source.SOURCE_SNAPSHOT_POLICY
            )

    def test_translator_child_receives_exact_project_tmpdir(self) -> None:
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-child-") as tmp:
            task = Path(tmp) / "task"
            task.mkdir(mode=0o700)
            domain = task / "domain.pddl"
            problem = task / "problem.pddl"
            domain.write_bytes(b"domain")
            problem.write_bytes(b"problem")
            domain.chmod(0o400)
            problem.chmod(0o400)
            child = {
                "PATH": Source.CONTROLLED_PATH,
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONPYCACHEPREFIX": str(task / "pycache"),
                "PYTHONPATH": str(Source.REPO / "src"),
            }
            files = {}
            for role, path in (("domain", domain), ("problem", problem)):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                files[role] = {
                    "sha256": digest,
                    "identity_before": Source._snapshot_file_identity(
                        path, digest, role
                    ),
                }
            active = {
                "domain_path": domain,
                "problem_path": problem,
                "files_by_role": files,
                "translator_verified_before_use": False,
                "normalization_verified_before_use": False,
            }
            with (
                mock.patch.dict(os.environ, {
                    "TMPDIR": str(task),
                    "PYTHONPYCACHEPREFIX": str(task / "pycache"),
                }, clear=True),
                mock.patch.object(Source, "_active_source_snapshot", active),
                mock.patch.object(
                    Source, "_base_subprocess_run", return_value="completed"
                ) as run,
            ):
                self.assertEqual(
                    Source._subprocess_run_with_tmpdir(
                        ["python", str(domain), str(problem)], env=child
                    ),
                    "completed",
                )
            self.assertEqual(
                run.call_args.kwargs["env"],
                {**child, "TMPDIR": str(task)},
            )
        with (
            mock.patch.dict(os.environ, {"TMPDIR": "/project/task"}, clear=True),
            self.assertRaisesRegex(
                Source.SourceAuditError, "child environment changed"
            ),
        ):
            Source._subprocess_run_with_tmpdir(["python"], env={})

    def test_source_snapshots_survive_live_source_mutation_and_bind_both_users(
        self,
    ) -> None:
        self.addCleanup(setattr, tempfile, "tempdir", None)
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-snapshot-") as tmp:
            base = Path(tmp)
            benchmarks = base / "benchmarks"
            source_dir = benchmarks / "demo"
            source_dir.mkdir(parents=True)
            domain = source_dir / "domain.pddl"
            problem = source_dir / "p01.pddl"
            domain_bytes = b"(define (domain frozen))\n"
            problem_bytes = b"(define (problem frozen))\n"
            domain.write_bytes(domain_bytes)
            problem.write_bytes(problem_bytes)
            task_tmp = base / "task-123-0"
            task_tmp.mkdir(mode=0o700)
            record = {
                "candidate_index": 0,
                "directory": "demo",
                "family": "demo",
                "problem": "p01.pddl",
                "canonical_path": "demo/p01.pddl",
                "domain_file": "demo/domain.pddl",
                "problem_file": "demo/p01.pddl",
                "domain_sha256": hashlib.sha256(domain_bytes).hexdigest(),
                "problem_sha256": hashlib.sha256(problem_bytes).hexdigest(),
            }
            translator_paths = []
            normalization_paths = []
            sas = (
                b"begin_version\n3\nend_version\nbegin_metric\n0\n"
                b"end_metric\n0\n0\nbegin_state\nend_state\n"
                b"begin_goal\n0\nend_goal\n0\n0\n"
            )

            def fake_run(command, **kwargs):
                translator_paths.append(tuple(map(Path, command[-2:])))
                domain.write_bytes(b"mutated live domain\n")
                problem.write_bytes(b"mutated live problem\n")
                self.assertEqual(Path(command[-2]).read_bytes(), domain_bytes)
                self.assertEqual(Path(command[-1]).read_bytes(), problem_bytes)
                (Path(kwargs["cwd"]) / "output.sas").write_bytes(sas)
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

            def fake_normalization(snapshot_domain, snapshot_problem):
                normalization_paths.append((
                    Path(snapshot_domain), Path(snapshot_problem),
                ))
                self.assertEqual(Path(snapshot_domain).read_bytes(), domain_bytes)
                self.assertEqual(Path(snapshot_problem).read_bytes(), problem_bytes)
                return 0

            environment = {
                "TMPDIR": str(task_tmp),
                "PYTHONPYCACHEPREFIX": str(task_tmp / "pycache"),
            }
            with (
                mock.patch.dict(os.environ, environment, clear=True),
                mock.patch.object(Source, "_base_subprocess_run", fake_run),
                mock.patch.object(
                    Source, "_base_count_normalized_axioms", fake_normalization
                ),
            ):
                tempfile.tempdir = None
                task = Source._scan_task(record, benchmarks, 14400)
            self.assertEqual(translator_paths, normalization_paths)
            self.assertNotEqual(domain.read_bytes(), domain_bytes)
            self.assertNotEqual(problem.read_bytes(), problem_bytes)
            self.assertEqual(list(task_tmp.iterdir()), [])
            with mock.patch.object(Source, "TMP_ROOT", base):
                Source._validate_source_snapshot(task)
            self.assertEqual(
                task["source_snapshot"]["policy"], Source.SOURCE_SNAPSHOT_POLICY
            )
            changed = json.loads(json.dumps(task))
            changed["source_snapshot"]["files"][0]["sha256"] = "0" * 64
            with self.assertRaisesRegex(
                Source.SourceAuditError, "snapshot file evidence"
            ):
                with mock.patch.object(Source, "TMP_ROOT", base):
                    Source._validate_source_snapshot(changed)

    def test_snapshot_mutation_before_normalization_fails_closed(self) -> None:
        self.addCleanup(setattr, tempfile, "tempdir", None)
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-snapshot-") as tmp:
            base = Path(tmp)
            benchmarks = base / "benchmarks"
            source_dir = benchmarks / "demo"
            source_dir.mkdir(parents=True)
            domain = source_dir / "domain.pddl"
            problem = source_dir / "p01.pddl"
            domain.write_bytes(b"domain\n")
            problem.write_bytes(b"problem\n")
            task_tmp = base / "task-123-1"
            task_tmp.mkdir(mode=0o700)
            record = {
                "candidate_index": 1,
                "directory": "demo",
                "problem": "p01.pddl",
                "domain_file": "demo/domain.pddl",
                "problem_file": "demo/p01.pddl",
                "domain_sha256": Source.sha256_file(domain),
                "problem_sha256": Source.sha256_file(problem),
            }
            sas = (
                b"begin_version\n3\nend_version\nbegin_metric\n0\n"
                b"end_metric\n0\n0\nbegin_state\nend_state\n"
                b"begin_goal\n0\nend_goal\n0\n0\n"
            )

            def mutate_snapshot(command, **kwargs):
                snapshot_domain = Path(command[-2])
                snapshot_domain.chmod(0o600)
                snapshot_domain.write_bytes(b"mutated snapshot\n")
                (Path(kwargs["cwd"]) / "output.sas").write_bytes(sas)
                return SimpleNamespace(returncode=0, stdout=b"", stderr=b"")

            with (
                mock.patch.dict(os.environ, {
                    "TMPDIR": str(task_tmp),
                    "PYTHONPYCACHEPREFIX": str(task_tmp / "pycache"),
                }, clear=True),
                mock.patch.object(
                    Source, "_base_subprocess_run", mutate_snapshot
                ),
                mock.patch.object(
                    Source, "_base_count_normalized_axioms", return_value=0
                ),
                self.assertRaises(Source.SourceAuditError),
            ):
                tempfile.tempdir = None
                Source._scan_task(record, benchmarks, 14400)

    def test_shard_loader_rejects_missing_snapshot_evidence(self) -> None:
        task = {
            "candidate_index": 0,
            "domain_file": "demo/domain.pddl",
            "problem_file": "demo/p01.pddl",
            "domain_sha256": "a" * 64,
            "problem_sha256": "b" * 64,
            "translation": {"status": "input-rejected"},
        }
        with (
            mock.patch.object(Source, "_base_load_shard", return_value=[task]),
            self.assertRaisesRegex(
                Source.SourceAuditError, "snapshot evidence"
            ),
        ):
            Source._load_shard(Path("unused"), 0, [], "c" * 64, {})

    def test_private_roots_reject_symlinks_and_replacements(self) -> None:
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-roots-") as tmp:
            base = Path(tmp)
            real = base / "real"
            real.mkdir(mode=0o700)
            direct = base / "direct"
            direct.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(
                Source.SourceAuditError, "symlink path component"
            ):
                Source._directory_identity(direct, "direct output root")
            child = real / "child"
            child.mkdir(mode=0o700)
            ancestor = base / "ancestor"
            ancestor.symlink_to(real, target_is_directory=True)
            with self.assertRaisesRegex(
                Source.SourceAuditError, "symlink path component"
            ):
                Source._directory_identity(
                    ancestor / "child", "ancestor-linked output root"
                )
            output = base / "output"
            output.mkdir(mode=0o700)
            identity = Launch._directory_identity(output, "output root")
            output.rename(base / "replaced-output")
            output.mkdir(mode=0o700)
            with self.assertRaisesRegex(
                Launch.LaunchAuditError, "was replaced"
            ):
                Launch._require_directory_identity(
                    output, identity, "output root"
                )

    def test_private_root_creation_clears_inherited_setgid(self) -> None:
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-setgid-") as tmp:
            parent = Path(tmp)
            parent.chmod(0o2755)
            root = parent / "root"
            identity = Launch._create_private_directory(root, "private root")
            self.assertEqual(stat.S_IMODE(root.lstat().st_mode), 0o700)
            self.assertEqual(identity["mode"], "0700")
            task = root / "task-1-0"
            task.mkdir(mode=0o700)
            self.assertEqual(stat.S_IMODE(task.lstat().st_mode), 0o700)

    def test_slurm_bytes_are_revalidated_then_submitted_on_stdin(self) -> None:
        self.assertIsNot(
            Launch.subprocess.run, Source._subprocess_run_with_tmpdir
        )
        raw = b"#!/bin/bash\nexit 0\n"
        digest = hashlib.sha256(raw).hexdigest()
        manifest_sha = "a" * 64
        materials = {
            "slurm_stdin_sha256": digest,
            "slurm_script_sha256": digest,
            "slurm_stdin_bytes": len(raw),
            "code_manifest_sha256": manifest_sha,
            "slurm_submission_mode": "stdin",
            "slurm_path_argument": False,
        }
        command = Launch._submit_command(
            Launch.SOURCE_INVENTORY_SHA256, Launch.OUTPUT_DIR, "a" * 24
        )
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-submit-") as tmp:
            script = Path(tmp) / "script.slurm"
            script.write_bytes(raw)

            def fake_sbatch(actual_command, **kwargs):
                script.write_bytes(b"#!/bin/bash\nexit 99\n")
                self.assertEqual(actual_command, command)
                self.assertEqual(kwargs["input"], raw)
                return SimpleNamespace(stdout=b"12345;cluster\n", stderr=b"")

            with (
                mock.patch.object(Launch, "SLURM_SCRIPT", script),
                mock.patch.object(
                    Launch, "_slurm_preflight",
                    return_value=(raw, digest, manifest_sha, {}),
                ),
                mock.patch.object(Launch, "_executable_identity", return_value={}),
                mock.patch.object(Launch.subprocess, "run", side_effect=fake_sbatch),
            ):
                self.assertEqual(
                    Launch._submit_sbatch(command, materials), "12345;cluster"
                )
        changed = b"#!/bin/bash\nexit 1\n"
        with (
            mock.patch.object(
                Launch, "_slurm_preflight", return_value=(
                    changed, hashlib.sha256(changed).hexdigest(), manifest_sha, {},
                )
            ),
            mock.patch.object(Launch.subprocess, "run") as run,
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "stdin changed before submission"
            ),
        ):
            Launch._submit_sbatch(command, materials)
        run.assert_not_called()

    def test_v4_intent_launch_and_status_round_trip_bypasses_v3_closure(
        self,
    ) -> None:
        self.assertIs(
            Launch._SHARED_LOAD_INTENT.__globals__, Launch.Legacy.__dict__
        )
        self.assertIsNot(
            Launch._load_intent_only.__globals__, Launch.Legacy.__dict__
        )
        token = "a" * 24
        materials = {
            "campaign": "v4",
            "source_inventory_sha256": Launch.SOURCE_INVENTORY_SHA256,
            "repository_commit_id": "b" * 64,
            "launch_root_identities": {
                "output_dir": {"v4": "output"},
                "tmpdir_root": {"v4": "tmp"},
            },
        }
        command = Launch._submit_command(
            Launch.SOURCE_INVENTORY_SHA256, Launch.OUTPUT_DIR, token
        )
        intent = {
            "schema": Launch.LAUNCH_SCHEMA + "/intent",
            **materials,
            "recorded_utc": "2026-09-01T00:00:00+00:00",
            "submission_token": token,
            "submit_command": command,
        }
        intent_raw = Source.canonical_json(intent)
        receipt = {
            "schema": Launch.LAUNCH_SCHEMA,
            **materials,
            "recorded_utc": intent["recorded_utc"],
            "submission_token": token,
            "submit_command": command,
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": "12345",
        }
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-intent-") as tmp:
            base = Path(tmp)
            intent_path = base / "intent.json"
            receipt_path = base / "receipt.json"
            inventory_path = base / "inventory.json"
            intent_path.write_bytes(intent_raw)
            receipt_path.write_bytes(Source.canonical_json(receipt))
            inventory_path.write_bytes(b"synthetic\n")
            with (
                mock.patch.object(Launch, "INTENT", intent_path),
                mock.patch.object(Launch, "LAUNCH_RECEIPT", receipt_path),
                mock.patch.object(Launch, "SOURCE_INVENTORY", inventory_path),
                mock.patch.object(
                    Launch, "_fixed_materials", return_value=materials
                ) as fixed,
                mock.patch.object(
                    Source, "load_inventory_manifest", return_value=("x", [])
                ),
                mock.patch.object(
                    Launch.Legacy, "_fixed_materials",
                    side_effect=AssertionError("v3 helper called"),
                ),
                mock.patch.object(
                    Launch.Legacy, "_submit_command",
                    side_effect=AssertionError("v3 helper called"),
                ),
                mock.patch.object(
                    Launch.Legacy, "_v2_failure_diagnostic",
                    side_effect=AssertionError("v3 helper called"),
                ),
                mock.patch.object(
                    Launch, "_journal_job_ids", return_value=["12345"]
                ),
                mock.patch.object(Launch, "_scheduler_rows", return_value=self._rows()),
                mock.patch("builtins.print"),
            ):
                loaded_raw, loaded_intent, loaded_materials = (
                    Launch._load_intent_only()
                )
                launch_sha, loaded_receipt = Launch._load_launch()
                status_sha, status_receipt, rows = Launch.status()
            self.assertEqual(loaded_raw, intent_raw)
            self.assertEqual(loaded_intent, intent)
            self.assertEqual(loaded_materials, materials)
            self.assertEqual(loaded_receipt, receipt)
            self.assertEqual(status_receipt, receipt)
            self.assertEqual(status_sha, launch_sha)
            self.assertEqual(rows, self._rows())
            self.assertEqual(fixed.call_count, 3)

    def test_options_only_submitline_is_journal_bound(self) -> None:
        token = "a" * 24
        command = Launch._submit_command(
            Launch.SOURCE_INVENTORY_SHA256, Launch.OUTPUT_DIR, token
        )
        job_name, comment = Launch._submission_identity(token)
        submit_line = shlex.join(command)
        journal = "".join(
            "12345_{}|{}|{}|{}\n".format(
                index, job_name, comment, submit_line
            )
            for index in range(Launch.ARRAY_TASKS)
        )
        intent = {
            "submission_token": token,
            "recorded_utc": "2026-09-01T00:00:00+00:00",
            "submit_command": command,
        }
        with (
            mock.patch.object(
                Launch.Legacy, "_sacct_executable_identity", return_value={}
            ),
            mock.patch.object(
                Launch.Legacy.subprocess, "check_output", return_value=journal
            ),
        ):
            self.assertEqual(Launch._journal_job_ids(intent), ["12345"])
        wrong = journal.replace(
            submit_line, submit_line + " " + str(Launch.SLURM_SCRIPT), 1
        )
        with (
            mock.patch.object(
                Launch.Legacy, "_sacct_executable_identity", return_value={}
            ),
            mock.patch.object(
                Launch.Legacy.subprocess, "check_output", return_value=wrong
            ),
            self.assertRaises(Launch.LaunchAuditError),
        ):
            Launch._journal_job_ids(intent)
        incomplete = journal.rsplit("\n", 2)[0] + "\n"
        with (
            mock.patch.object(
                Launch.Legacy, "_sacct_executable_identity", return_value={}
            ),
            mock.patch.object(
                Launch.Legacy.subprocess, "check_output", return_value=incomplete
            ),
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "incomplete array"
            ),
        ):
            Launch._journal_job_ids(intent)
        collided = journal.replace("12345_17|", "99999_17|", 1)
        with (
            mock.patch.object(
                Launch.Legacy, "_sacct_executable_identity", return_value={}
            ),
            mock.patch.object(
                Launch.Legacy.subprocess, "check_output", return_value=collided
            ),
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "multiple source-audit jobs"
            ),
        ):
            Launch._journal_job_ids(intent)

    def test_launch_receipt_rejects_wrong_journal_job(self) -> None:
        intent_raw = b"intent\n"
        intent = {
            "recorded_utc": "2026-09-01T00:00:00+00:00",
            "submission_token": "a" * 24,
            "submit_command": ["/usr/bin/sbatch", "--parsable"],
        }
        materials = {"campaign": "v4"}
        receipt = {
            "schema": Launch.LAUNCH_SCHEMA,
            **materials,
            "recorded_utc": intent["recorded_utc"],
            "submission_token": intent["submission_token"],
            "submit_command": intent["submit_command"],
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": "12345",
        }
        launch_raw = Source.canonical_json(receipt)
        with (
            mock.patch.object(
                Launch, "_load_intent_only",
                return_value=(intent_raw, intent, materials),
            ),
            mock.patch.object(
                Launch, "_load_json", return_value=(launch_raw, receipt)
            ),
            mock.patch.object(
                Launch, "_journal_job_ids", return_value=["99999"]
            ),
            self.assertRaisesRegex(
                Launch.LaunchAuditError, "not journal-bound"
            ),
        ):
            Launch._load_launch()

    def test_slurm_uses_only_safe_empty_directory_cleanup(self) -> None:
        text = Launch.SLURM_SCRIPT.read_text(encoding="ascii")
        self.assertNotIn("rm -", text)
        self.assertNotIn("/tmp/", text)
        self.assertEqual(text.count('trap cleanup_tmpdir EXIT'), 1)
        self.assertEqual(
            text.count('"${rmdir_executable}" -- "${TMPDIR}"'), 1
        )
        self.assertIn('"${mkdir_executable}" --mode=0700 -- "${TMPDIR}"', text)
        self.assertIn(
            'export TMPDIR="${tmpdir_root}/task-${SLURM_ARRAY_JOB_ID}-'
            '${SLURM_ARRAY_TASK_ID}"',
            text,
        )
        self.assertIn('test "$#" -eq 0', text)
        self.assertIn(
            'source_inventory_sha256="{}"'.format(
                Launch.SOURCE_INVENTORY_SHA256
            ),
            text,
        )
        self.assertNotIn('source_inventory_sha256="$1"', text)
        self.assertNotIn('source_audit_output_dir="$2"', text)

    def test_current_slurm_file_passes_exact_preflight(self) -> None:
        if not Launch.CODE_MANIFEST.exists():
            self.skipTest("final manifest awaits terminal v3 diagnostic")
        raw, slurm_sha, manifest_sha, _ = Launch._slurm_preflight()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), slurm_sha)
        self.assertTrue(Source._is_sha256(slurm_sha))
        self.assertTrue(Source._is_sha256(manifest_sha))

    def test_current_slurm_contract_passes_with_or_without_manifest(self) -> None:
        code = {"synthetic": "manifest validation only"}
        with (
            mock.patch.object(
                Source, "validate_code_manifest", return_value=code
            ),
            mock.patch.object(Launch, "_execution_environment", return_value={}),
        ):
            raw, slurm_sha, manifest_sha, loaded_code = (
                Launch._slurm_preflight()
            )
        self.assertEqual(hashlib.sha256(raw).hexdigest(), slurm_sha)
        expected_manifest_sha = (
            hashlib.sha256(Launch.CODE_MANIFEST.read_bytes()).hexdigest()
            if Launch.CODE_MANIFEST.exists() else "0" * 64
        )
        self.assertEqual(manifest_sha, expected_manifest_sha)
        self.assertIs(loaded_code, code)

    def test_normalized_slurm_hash_is_pinned_before_manifest_exists(self) -> None:
        raw = Launch.SLURM_SCRIPT.read_bytes()
        assignments = [
            Launch.MANIFEST_ASSIGNMENT_RE.fullmatch(line)
            for line in raw.decode("ascii").splitlines()
            if line.startswith("code_manifest_sha256=")
        ]
        self.assertEqual(len(assignments), 1)
        self.assertIsNotNone(assignments[0])
        manifest_sha = assignments[0].group(1)
        normalized = raw.replace(manifest_sha.encode("ascii"), b"0" * 64, 1)
        self.assertEqual(raw.count(manifest_sha.encode("ascii")), 1)
        self.assertEqual(
            hashlib.sha256(normalized).hexdigest(),
            Launch.NORMALIZED_SLURM_SHA256,
        )

    def test_normalized_slurm_mutation_is_rejected(self) -> None:
        original_path = Launch.SLURM_SCRIPT
        original = original_path.read_text(encoding="ascii")
        with tempfile.TemporaryDirectory(prefix="source-audit-v4-slurm-") as tmp:
            candidate = Path(tmp) / "candidate.slurm"
            candidate.write_text(
                original.replace(
                    "--task-timeout 14400", "--task-timeout 14399"
                ),
                encoding="ascii",
            )
            Launch.SLURM_SCRIPT = candidate
            try:
                with self.assertRaisesRegex(
                    Launch.LaunchAuditError, "executable bytes changed"
                ):
                    Launch._slurm_preflight()
            finally:
                Launch.SLURM_SCRIPT = original_path

    def test_code_manifest_is_exact_and_complete(self) -> None:
        if not Launch.CODE_MANIFEST.exists():
            self.skipTest("final manifest awaits terminal v3 diagnostic")
        raw = Launch.CODE_MANIFEST.read_bytes()
        manifest_sha = hashlib.sha256(raw).hexdigest()
        code = Source.validate_code_manifest(Launch.CODE_MANIFEST, manifest_sha)
        self.assertEqual(code["code_manifest_sha256"], manifest_sha)


if __name__ == "__main__":
    unittest.main()
