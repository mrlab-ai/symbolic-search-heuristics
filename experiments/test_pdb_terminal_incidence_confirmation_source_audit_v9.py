#!/usr/bin/env python3
"""Tests for the V9 full-census source-audit producer."""

from __future__ import annotations

import base64
import copy
import errno
import hashlib
import json
import os
import signal
import subprocess
import tempfile
import textwrap
import tracemalloc
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import audit_pdb_terminal_incidence_confirmation_sources_v9 as V9


def _write_synthetic_driver(directory: Path, mode: str) -> Path:
    """Write a manifest-bound child that speaks the production handshake."""
    path = directory / "synthetic-{}-driver.py".format(mode)
    source = f"""
        import json
        import os
        import resource
        import signal
        import sys
        import time

        MODE = {mode!r}
        SCHEMA = {V9.SCHEMA + "/child-limit-evidence/v1"!r}

        def option_fd(name):
            return int(sys.argv[sys.argv.index(name) + 1])

        start_fd = option_fd("--start-fd")
        limit_fd = option_fd("--limit-evidence-fd")
        normalization_fd = option_fd("--normalization-evidence-fd")
        wanted = {{"NoNewPrivs", "Seccomp", "Seccomp_filters", "Threads"}}
        status = {{}}
        with open("/proc/self/status", encoding="ascii") as stream:
            for line in stream:
                key, separator, value = line.partition(":")
                if separator and key in wanted:
                    status[key] = int(value.strip())
        record = {{
            "schema": SCHEMA,
            "pid": os.getpid(),
            "process_group": os.getpgrp(),
            "rlimit_as": list(resource.getrlimit(resource.RLIMIT_AS)),
            "rlimit_cpu": list(resource.getrlimit(resource.RLIMIT_CPU)),
            "no_new_privs": status["NoNewPrivs"],
            "seccomp_mode": status["Seccomp"],
            "seccomp_filters": status["Seccomp_filters"],
            "threads": status["Threads"],
        }}
        payload = (json.dumps(
            record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ) + "\\n").encode("ascii")
        if os.write(limit_fd, payload) != len(payload):
            os._exit(70)
        os.close(limit_fd)
        release = os.read(start_fd, 1)
        os.close(start_fd)
        os.close(normalization_fd)
        if release != b"G":
            os._exit(70)
        if MODE == "memory":
            allocations = []
            try:
                while True:
                    allocations.append(bytearray(8 * 1024 * 1024))
            except MemoryError:
                os._exit(20)
        if MODE == "cpu":
            signal.signal(signal.SIGXCPU, lambda *_: os._exit(21))
            while True:
                pass
        if MODE == "wall":
            time.sleep(60)
            os._exit(0)
        if MODE == "exit":
            os._exit(7)
        if MODE == "signal":
            os.kill(os.getpid(), signal.SIGTERM)
            os._exit(71)
        os._exit(70)
    """
    path.write_text(textwrap.dedent(source), encoding="utf-8")
    return path


class V9SourceAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = V9.build_inventory_manifest()

    def test_full_census_mapping_is_exact_bijection(self):
        indices = [
            candidate
            for shard in range(V9.ARRAY_TASKS)
            for candidate in V9.candidate_indices_for_shard(shard)
        ]
        self.assertEqual(indices, list(range(V9.CANDIDATE_COUNT)))
        self.assertEqual(V9.candidate_indices_for_shard(0), (0, 1))
        self.assertEqual(V9.candidate_indices_for_shard(819), (1638, 1639))
        for invalid in (-1, 820, True, 1.0):
            with self.assertRaises(V9.SourceAuditError):
                V9.candidate_indices_for_shard(invalid)

    def test_resource_contract_is_exact_and_wall_is_not_scientific(self):
        contract = V9.resource_contract()
        self.assertEqual(contract["address_space_bytes"], 24_576 * 1024 * 1024)
        self.assertEqual(contract["cpu_soft_seconds"], 1800)
        self.assertEqual(contract["cpu_hard_seconds"], 1801)
        self.assertEqual(contract["child_wall_watchdog_seconds"], 1950)
        self.assertFalse(contract["wall_watchdog_is_scientific_exclusion"])
        self.assertEqual(contract["memory_exit_code"], 20)
        self.assertEqual(contract["cpu_time_exit_code"], 21)
        self.assertEqual(contract["input_error_exit_code"], 31)

    def test_inventory_is_exact_1640_record_frozen_population(self):
        records = V9.validate_inventory_manifest(self.inventory)
        self.assertEqual(len(records), 1640)
        self.assertEqual(
            [record["candidate_index"] for record in records],
            list(range(1640)),
        )
        self.assertEqual(
            self.inventory["candidate_records_sha256"],
            V9.Inventory.CANDIDATE_RECORDS_SHA256,
        )
        self.assertEqual(
            self.inventory["inventory_digests"], V9.EXPECTED_INVENTORY_DIGESTS
        )

    def test_inventory_mutations_fail_closed(self):
        attacks = []
        value = copy.deepcopy(self.inventory)
        value["records"].pop()
        value["records_sha256"] = V9._digest(value["records"])
        attacks.append(value)
        value = copy.deepcopy(self.inventory)
        value["records"][0]["candidate_index"] = 1
        value["records_sha256"] = V9._digest(value["records"])
        attacks.append(value)
        value = copy.deepcopy(self.inventory)
        value["records"][0]["problem_sha256"] = "0" * 64
        value["records_sha256"] = V9._digest(value["records"])
        attacks.append(value)
        value = copy.deepcopy(self.inventory)
        value["inventory_digests"]["candidate_records"] = "0" * 64
        attacks.append(value)
        for attack in attacks:
            with self.subTest(attack=list(attacks).index(attack)):
                with self.assertRaises(V9.SourceAuditError):
                    V9.validate_inventory_manifest(attack)

    def test_support_classification_keeps_exact_semantic_rules(self):
        sas = {
            "num_operators": 2,
            "num_zero_cost_operators": 0,
            "min_operator_cost": 1,
            "num_serialized_axioms": 0,
            "num_conditional_effects": 0,
        }
        self.assertEqual(V9._support_reasons(sas, 0), [])
        changed = dict(sas, num_zero_cost_operators=1)
        self.assertIn(
            "nonpositive-serialized-operator-cost",
            V9._support_reasons(changed, 0),
        )
        changed = dict(sas, num_serialized_axioms=1)
        self.assertIn("serialized-axioms", V9._support_reasons(changed, 0))
        changed = dict(sas, num_conditional_effects=1)
        self.assertIn(
            "serialized-conditional-effects",
            V9._support_reasons(changed, 0),
        )
        self.assertIn("normalized-axioms", V9._support_reasons(sas, 1))

    def _all_supported_records(self):
        return [
            {
                **copy.deepcopy(record),
                "status": "success",
                "resource_exclusion_kind": None,
                "support_determined": True,
                "supported": True,
                "eligible_for_cohort": True,
                "support_exclusion_reasons": [],
            }
            for record in self.inventory["records"]
        ]

    @staticmethod
    def _gripper_record() -> tuple[Path, dict]:
        benchmarks = V9.REPO / "misc/tests/benchmarks/gripper"
        domain = benchmarks / "domain.pddl"
        problem = benchmarks / "prob01.pddl"
        return benchmarks, {
            "candidate_index": 0,
            "directory": "gripper",
            "family": "gripper",
            "problem": "prob01.pddl",
            "domain_file": "domain.pddl",
            "problem_file": "prob01.pddl",
            "domain_sha256": hashlib.sha256(domain.read_bytes()).hexdigest(),
            "problem_sha256": hashlib.sha256(problem.read_bytes()).hexdigest(),
            "canonical_path": "prob01.pddl",
            "is_shadow_family": False,
            "is_shadow_unrepresented": True,
            "is_all_prior_represented": True,
            "is_all_prior_unrepresented": False,
            "aliases": [],
        }

    def _run_synthetic_candidate(
        self, root: Path, mode: str, **limit_overrides
    ) -> dict:
        benchmarks, record = self._gripper_record()
        task_tmp = root / "task"
        stage = root / "stage"
        task_tmp.mkdir()
        stage.mkdir()
        driver = _write_synthetic_driver(root, mode)
        with mock.patch.multiple(
            V9, TRANSLATOR_DRIVER=driver, **limit_overrides
        ):
            result = V9._run_candidate(
                record,
                shard_index=0,
                position=0,
                benchmarks=benchmarks,
                task_tmp=task_tmp,
                stage=stage,
                code_manifest_sha256="1" * 64,
                repository_commit_id="2" * 40,
            )
        self.assertFalse(any(task_tmp.iterdir()))
        return result

    @staticmethod
    def _scan_args(root: Path, inventory_raw: bytes) -> SimpleNamespace:
        output = root / "output"
        tmp_root = root / "tmp"
        output.mkdir()
        output.chmod(0o700)
        tmp_root.mkdir()
        return SimpleNamespace(
            num_shards=V9.ARRAY_TASKS,
            shard_index=0,
            output_dir=str(output),
            inventory_manifest=str(root / "inventory.json"),
            inventory_sha256=hashlib.sha256(inventory_raw).hexdigest(),
            code_manifest=str(root / "code.sha256"),
            code_manifest_sha256="1" * 64,
            benchmarks=str(root / "benchmarks"),
            tmp_root=str(tmp_root),
            repository_commit_id="2" * 40,
        )

    def test_split_matches_frozen_all_supported_golden_vector(self):
        gate, cohorts = V9.split_supported(self._all_supported_records())
        self.assertTrue(gate["passed"])
        self.assertEqual(
            cohorts["confirmation_a"]["candidate_indices_sha256"],
            "4960d774de9cf77727d1fda9a8f86c53a3aa9338d3def3c49a129e96e118335c",
        )
        self.assertEqual(
            cohorts["guided_b"]["candidate_indices_sha256"],
            "e7d909f61763dfa3aa5ddb83cad807c3c81bfca02287e43042eb02faadd45c5f",
        )
        self.assertEqual(
            len(cohorts["confirmation_a"]["candidate_indices"]), 650
        )
        self.assertEqual(len(cohorts["guided_b"]["candidate_indices"]), 300)

    def test_resource_exclusion_is_indeterminate_and_never_selected(self):
        records = self._all_supported_records()
        records[0].update({
            "status": "resource-excluded",
            "resource_exclusion_kind": "memory",
            "support_determined": False,
            "supported": None,
            "eligible_for_cohort": False,
            "support_exclusion_reasons": None,
        })
        _gate, cohorts = V9.split_supported(records)
        self.assertNotIn(0, cohorts["confirmation_a"]["candidate_indices"])
        self.assertNotIn(0, cohorts["guided_b"]["candidate_indices"])
        records[0]["supported"] = True
        records[0]["eligible_for_cohort"] = True
        with self.assertRaisesRegex(V9.SourceAuditError, "disposition changed"):
            V9.split_supported(records)

    def test_pipe_records_are_canonical_bounded_and_single_record(self):
        value = {"a": 1, "schema": "fixture"}
        raw = V9.canonical_json(value) + b"\n"
        self.assertEqual(V9._load_pipe_json(raw, "fixture"), value)
        for malformed in (
            b"", b'{"a": 1}\n', raw + raw, raw.rstrip(b"\n"), b"[]\n"
        ):
            if malformed == b"":
                self.assertIsNone(V9._load_pipe_json(malformed, "fixture"))
            else:
                with self.assertRaises(V9.SourceAuditError):
                    V9._load_pipe_json(malformed, "fixture")

    def test_parent_independently_observes_exact_child_limits(self):
        process = subprocess.Popen(
            ["/bin/sleep", "30"],
            preexec_fn=V9._child_preexec,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            observed = V9._parent_limit_observation(process.pid)
            self.assertEqual(
                observed["rlimit_as"],
                [V9.ADDRESS_SPACE_BYTES, V9.ADDRESS_SPACE_BYTES],
            )
            self.assertEqual(
                observed["rlimit_cpu"],
                [V9.CPU_SOFT_SECONDS, V9.CPU_HARD_SECONDS],
            )
        finally:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=10)
        self.assertTrue(V9._process_group_absent(process.pid))

    def test_seccomp_actually_denies_fork_clone_and_session_escape(self):
        program = textwrap.dedent("""
            import errno
            import json
            import os
            import threading

            result = {}
            try:
                child = os.fork()
            except OSError as err:
                result["fork_errno"] = err.errno
            else:
                if child == 0:
                    os._exit(91)
                os.waitpid(child, 0)
                result["fork_errno"] = 0

            thread = threading.Thread(target=lambda: None)
            try:
                thread.start()
            except BaseException as err:
                result["thread_started"] = False
                result["thread_error"] = type(err).__name__
            else:
                thread.join()
                result["thread_started"] = True
                result["thread_error"] = None

            for name, operation in (
                ("setsid_errno", os.setsid),
                ("setpgid_errno", lambda: os.setpgid(0, 0)),
            ):
                try:
                    operation()
                except OSError as err:
                    result[name] = err.errno
                else:
                    result[name] = 0
            print(json.dumps(result, sort_keys=True))
        """)
        completed = subprocess.run(
            [str(V9.PINNED_PYTHON), "-B", "-c", program],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={
                "PATH": V9.CONTROLLED_PATH,
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
            preexec_fn=V9._child_preexec,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertEqual(completed.stderr, b"")
        evidence = json.loads(completed.stdout)
        self.assertEqual(evidence["fork_errno"], errno.EPERM)
        self.assertFalse(evidence["thread_started"])
        self.assertEqual(evidence["thread_error"], "RuntimeError")
        self.assertEqual(evidence["setsid_errno"], errno.EPERM)
        self.assertEqual(evidence["setpgid_errno"], errno.EPERM)

    def test_source_snapshot_rejects_symlink_escape_from_benchmark_root(self):
        with tempfile.TemporaryDirectory(prefix="v9-source-escape-") as tmp:
            root = Path(tmp)
            benchmarks = root / "benchmarks"
            outside = root / "outside"
            work = root / "work"
            benchmarks.mkdir()
            outside.mkdir()
            work.mkdir()
            domain = outside / "domain.pddl"
            problem = outside / "problem.pddl"
            domain.write_text("outside domain\n", encoding="utf-8")
            problem.write_text("outside problem\n", encoding="utf-8")
            (benchmarks / "escape").symlink_to(
                outside, target_is_directory=True
            )
            record = {
                "domain_file": "escape/domain.pddl",
                "problem_file": "escape/problem.pddl",
                "domain_sha256": hashlib.sha256(domain.read_bytes()).hexdigest(),
                "problem_sha256": hashlib.sha256(problem.read_bytes()).hexdigest(),
            }
            with self.assertRaisesRegex(
                V9.SourceAuditError, "escapes benchmark root"
            ):
                V9._snapshot_source(record, benchmarks, work)

    def test_one_candidate_runs_once_in_fresh_bounded_child(self):
        benchmarks, record = self._gripper_record()
        with tempfile.TemporaryDirectory(prefix="v9-candidate-") as tmp:
            root = Path(tmp)
            task_tmp = root / "task"
            stage = root / "stage"
            task_tmp.mkdir()
            stage.mkdir()
            result = V9._run_candidate(
                record,
                shard_index=0,
                position=0,
                benchmarks=benchmarks,
                task_tmp=task_tmp,
                stage=stage,
                code_manifest_sha256="1" * 64,
                repository_commit_id="2" * 40,
            )
            self.assertEqual(result["status"], "success")
            self.assertTrue(result["support_determined"])
            self.assertTrue(result["supported"])
            self.assertTrue(result["eligible_for_cohort"])
            self.assertEqual(result["normalization"]["num_normalized_axioms"], 0)
            self.assertEqual(result["child_limit_attestation"]["pid"], result[
                "child_limit_attestation"
            ]["process_group"])
            self.assertTrue(result["complete_process_group_reaped"])
            self.assertFalse(any(task_tmp.iterdir()))
            self.assertEqual(
                sorted(path.name for path in stage.iterdir()),
                ["candidate-0000.stderr.prefix", "candidate-0000.stdout.prefix"],
            )

    def test_input_rejection_exit_31_is_classified_and_cleaned(self):
        with tempfile.TemporaryDirectory(prefix="v9-input-rejected-") as tmp:
            root = Path(tmp)
            benchmarks = root / "benchmarks"
            task_tmp = root / "task"
            stage = root / "stage"
            benchmarks.mkdir()
            task_tmp.mkdir()
            stage.mkdir()
            domain = benchmarks / "domain.pddl"
            problem = benchmarks / "problem.pddl"
            domain.write_text("this is not pddl\n", encoding="utf-8")
            problem.write_text("this is not pddl either\n", encoding="utf-8")
            record = {
                "candidate_index": 0,
                "directory": "synthetic-invalid",
                "family": "synthetic-invalid",
                "problem": "problem.pddl",
                "domain_file": "domain.pddl",
                "problem_file": "problem.pddl",
                "domain_sha256": hashlib.sha256(domain.read_bytes()).hexdigest(),
                "problem_sha256": hashlib.sha256(problem.read_bytes()).hexdigest(),
                "canonical_path": "problem.pddl",
                "is_shadow_family": False,
                "is_shadow_unrepresented": False,
                "is_all_prior_represented": False,
                "is_all_prior_unrepresented": True,
                "aliases": [],
            }
            result = V9._run_candidate(
                record,
                shard_index=0,
                position=0,
                benchmarks=benchmarks,
                task_tmp=task_tmp,
                stage=stage,
                code_manifest_sha256="1" * 64,
                repository_commit_id="2" * 40,
            )
            self.assertEqual(result["process_returncode"], 31)
            self.assertEqual(result["status"], "input-rejected")
            self.assertTrue(result["support_determined"])
            self.assertFalse(result["supported"])
            self.assertFalse(result["eligible_for_cohort"])
            self.assertEqual(
                result["support_exclusion_reasons"],
                ["translation-input-rejected"],
            )
            self.assertFalse(any(task_tmp.iterdir()))

    def test_memory_limit_exit_20_is_an_indeterminate_resource_exclusion(self):
        with tempfile.TemporaryDirectory(prefix="v9-memory-limit-") as tmp:
            result = self._run_synthetic_candidate(
                Path(tmp),
                "memory",
                ADDRESS_SPACE_BYTES=512 * 1024 * 1024,
            )
        self.assertEqual(result["process_returncode"], 20)
        self.assertEqual(result["status"], "resource-excluded")
        self.assertEqual(result["resource_exclusion_kind"], "memory")
        self.assertFalse(result["support_determined"])
        self.assertIsNone(result["supported"])
        self.assertFalse(result["eligible_for_cohort"])

    def test_cpu_limit_exit_21_is_an_indeterminate_resource_exclusion(self):
        with tempfile.TemporaryDirectory(prefix="v9-cpu-limit-") as tmp:
            result = self._run_synthetic_candidate(
                Path(tmp),
                "cpu",
                CPU_SOFT_SECONDS=1,
                CPU_HARD_SECONDS=2,
            )
        self.assertEqual(result["process_returncode"], 21)
        self.assertEqual(result["status"], "resource-excluded")
        self.assertEqual(result["resource_exclusion_kind"], "time")
        self.assertFalse(result["support_determined"])
        self.assertIsNone(result["supported"])
        self.assertFalse(result["eligible_for_cohort"])

    def test_wall_timeout_is_infrastructure_failure_not_scientific_exclusion(self):
        with tempfile.TemporaryDirectory(prefix="v9-wall-timeout-") as tmp:
            with self.assertRaisesRegex(
                V9.InfrastructureAuditError, "wall watchdog expired"
            ):
                self._run_synthetic_candidate(
                    Path(tmp), "wall", CHILD_WALL_SECONDS=0.05
                )

    def test_arbitrary_exit_and_signal_fail_closed(self):
        cases = (("exit", "ambiguous exit 7"), ("signal", "ambiguous exit -15"))
        for mode, message in cases:
            with self.subTest(mode=mode), tempfile.TemporaryDirectory(
                prefix="v9-arbitrary-outcome-"
            ) as tmp:
                with self.assertRaisesRegex(
                    V9.InfrastructureAuditError, message
                ):
                    self._run_synthetic_candidate(Path(tmp), mode)

    def test_stream_capture_retains_bounded_prefix_and_exact_full_hash(self):
        with tempfile.TemporaryDirectory(prefix="v9-stream-") as tmp:
            root = Path(tmp)
            raw = root / "raw"
            prefix = root / "prefix"
            chunk = bytes(range(256)) * 4096
            terminal = b"terminal-tail"
            expected_digest = hashlib.sha256()
            with raw.open("wb") as stream:
                for _ in range(64):
                    stream.write(chunk)
                    expected_digest.update(chunk)
                stream.write(terminal)
                expected_digest.update(terminal)
            total_bytes = 64 * len(chunk) + len(terminal)
            expected_tail = (chunk + terminal)[-V9.STREAM_TAIL_BYTES:]
            tracemalloc.start()
            try:
                evidence = V9._capture_evidence(
                    raw, prefix, "prefix", "fixture"
                )
                _current, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            self.assertFalse(raw.exists())
            self.assertEqual(prefix.read_bytes(), chunk[:V9.STREAM_PREFIX_BYTES])
            self.assertEqual(evidence["total_bytes"], total_bytes)
            self.assertEqual(evidence["sha256"], expected_digest.hexdigest())
            self.assertEqual(evidence["retained_bytes"], V9.STREAM_PREFIX_BYTES)
            self.assertTrue(evidence["truncated"])
            self.assertEqual(evidence["tail_bytes"], V9.STREAM_TAIL_BYTES)
            self.assertEqual(
                base64.b64decode(evidence["tail_base64"]), expected_tail
            )
            self.assertLess(peak, 8 * 1024 * 1024)

    def test_two_candidate_scan_does_not_publish_if_second_candidate_fails(self):
        inventory_raw = V9.canonical_json({"synthetic": "inventory"})
        with tempfile.TemporaryDirectory(prefix="v9-scan-atomic-") as tmp:
            root = Path(tmp)
            args = self._scan_args(root, inventory_raw)
            run_candidate = mock.Mock(side_effect=[
                {"status": "success"},
                V9.InfrastructureAuditError("second candidate failed"),
            ])
            publish = mock.Mock()
            with (
                mock.patch.object(
                    V9, "_load_canonical_json",
                    return_value=(inventory_raw, {}),
                ),
                mock.patch.object(
                    V9, "validate_inventory_manifest",
                    return_value=[{"candidate_index": 0}, {"candidate_index": 1}],
                ),
                mock.patch.object(V9, "validate_code_manifest", return_value={}),
                mock.patch.object(V9, "_execution_environment", return_value={}),
                mock.patch.object(V9, "_run_candidate", run_candidate),
                mock.patch.object(
                    V9, "_publish_directory_exclusive", publish
                ),
                mock.patch.dict(os.environ, {"SLURM_ARRAY_JOB_ID": "777"}),
                self.assertRaisesRegex(
                    V9.InfrastructureAuditError, "second candidate failed"
                ),
            ):
                V9.scan(args)
            self.assertEqual(run_candidate.call_count, 2)
            publish.assert_not_called()
            self.assertFalse(V9.shard_path(Path(args.output_dir), 0).exists())

    def test_scan_refuses_existing_shard_before_running_either_candidate(self):
        inventory_raw = V9.canonical_json({"synthetic": "inventory"})
        with tempfile.TemporaryDirectory(prefix="v9-scan-collision-") as tmp:
            root = Path(tmp)
            args = self._scan_args(root, inventory_raw)
            V9.shard_path(Path(args.output_dir), 0).mkdir()
            run_candidate = mock.Mock()
            with (
                mock.patch.object(
                    V9, "_load_canonical_json",
                    return_value=(inventory_raw, {}),
                ),
                mock.patch.object(
                    V9, "validate_inventory_manifest",
                    return_value=[{"candidate_index": 0}, {"candidate_index": 1}],
                ),
                mock.patch.object(V9, "validate_code_manifest", return_value={}),
                mock.patch.object(V9, "_execution_environment", return_value={}),
                mock.patch.object(V9, "_run_candidate", run_candidate),
                mock.patch.dict(os.environ, {"SLURM_ARRAY_JOB_ID": "778"}),
                self.assertRaisesRegex(
                    V9.SourceAuditError, "shard namespace is not empty"
                ),
            ):
                V9.scan(args)
            run_candidate.assert_not_called()

    def test_atomic_publication_refuses_collisions(self):
        with tempfile.TemporaryDirectory(prefix="v9-publish-") as tmp:
            target = Path(tmp) / "record.json"
            raw = V9.canonical_json({"value": 1})
            digest = V9.atomic_exclusive_bytes(target, raw, "fixture")
            self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
            self.assertEqual(target.read_bytes(), raw)
            with self.assertRaisesRegex(V9.SourceAuditError, "overwrite"):
                V9.atomic_exclusive_bytes(target, raw, "fixture")

    def test_directory_publication_is_atomic_and_never_replaces(self):
        with tempfile.TemporaryDirectory(prefix="v9-directory-publish-") as tmp:
            root = Path(tmp)
            source = root / "source"
            target = root / "target"
            source.mkdir(mode=0o700)
            source_inode = source.stat().st_ino
            V9._publish_directory_exclusive(
                source, target, source_inode, "fixture"
            )
            self.assertFalse(source.exists())
            self.assertEqual(target.stat().st_ino, source_inode)
            self.assertEqual(target.stat().st_mode & 0o777, 0o500)

            second_source = root / "second-source"
            second_source.mkdir(mode=0o700)
            with self.assertRaisesRegex(V9.SourceAuditError, "overwrite"):
                V9._publish_directory_exclusive(
                    second_source, target, second_source.stat().st_ino,
                    "fixture",
                )
            self.assertTrue(second_source.is_dir())
            self.assertEqual(target.stat().st_ino, source_inode)

    def test_producer_has_no_prior_campaign_import_or_runtime_path(self):
        source = Path(V9.__file__).read_text(encoding="utf-8")
        for generation in range(1, 9):
            self.assertNotIn(
                "audit_pdb_terminal_incidence_confirmation_sources_v{}.py".format(
                    generation
                ),
                source,
            )
            self.assertNotIn(
                "source_audit_v{}_".format(generation), source
            )
        self.assertNotIn("read_text().splitlines()", source)
        self.assertNotIn("subprocess.run(command", source)


if __name__ == "__main__":
    unittest.main()
