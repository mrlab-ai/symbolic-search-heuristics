#!/usr/bin/env python3
"""Focused tests for the bounded one-pass V11 translator driver."""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import resource
import subprocess
import sys
import tempfile
import tracemalloc
import unittest
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
SOURCE_ROOT = REPO / "src"
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SOURCE_ROOT))

import pdb_terminal_incidence_confirmation_translate_v11 as TranslateV11
import pdb_terminal_incidence_confirmation_translate_v9 as TranslateV9
import audit_pdb_terminal_incidence_confirmation_sources_v11 as SourceV11


def _sas(operator_effect: str = "0 0 -1 1", cost: int = 1) -> bytes:
    return ("\n".join((
        "begin_version", "3", "end_version",
        "begin_metric", "1", "end_metric",
        "1",
        "begin_variable", "var0", "-1", "2", "Atom a()", "<none of those>",
        "end_variable",
        "0",
        "begin_state", "0", "end_state",
        "begin_goal", "1", "0 1", "end_goal",
        "1",
        "begin_operator", "move", "0", "1", operator_effect, str(cost),
        "end_operator",
        "0",
    )) + "\n").encode("utf-8")


def _write_fd_record(value: dict) -> int:
    read_fd, write_fd = os.pipe()
    os.write(write_fd, TranslateV11._canonical_json_line(value))
    os.close(write_fd)
    return read_fd


def _set_v11_child_limits() -> None:
    SourceV11._child_preexec()


def _run_historical(domain: Path, problem: Path, cwd: Path):
    environment = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(SOURCE_ROOT),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    completed = subprocess.run(
        [sys.executable, "-B", "-m", "translate", str(domain), str(problem)],
        cwd=cwd,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    sas_path = cwd / "output.sas"
    return completed, sas_path.read_bytes() if sas_path.exists() else None


def _run_v11(domain: Path, problem: Path, cwd: Path):
    start_read, start_write = os.pipe()
    limit_read, limit_write = os.pipe()
    normalization_read, normalization_write = os.pipe()
    os.write(start_write, TranslateV11.START_BYTE)
    os.close(start_write)
    environment = {
        "PATH": os.environ["PATH"],
        "PYTHONPATH": str(SOURCE_ROOT),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    command = [
        sys.executable,
        "-B",
        str(SCRIPT_DIR / "pdb_terminal_incidence_confirmation_translate_v11.py"),
        "--start-fd", str(start_read),
        "--limit-evidence-fd", str(limit_write),
        "--normalization-evidence-fd", str(normalization_write),
        "--", str(domain), str(problem),
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            pass_fds=(start_read, limit_write, normalization_write),
            preexec_fn=_set_v11_child_limits,
            check=False,
        )
    finally:
        os.close(start_read)
        os.close(limit_write)
        os.close(normalization_write)
    limit = TranslateV11.read_limit_evidence(limit_read)
    os.close(limit_read)
    normalization = TranslateV11._read_bounded_fd(
        normalization_read, "test normalization evidence"
    )
    os.close(normalization_read)
    sas_path = cwd / "output.sas"
    return (
        completed,
        sas_path.read_bytes() if sas_path.exists() else None,
        limit,
        normalization,
    )


def _normalized_axiom_count(domain: Path, problem: Path) -> int:
    from translate import normalize
    from translate.pddl_parser import pddl_file

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ResourceWarning)
        task = pddl_file.open(str(domain), str(problem))
        normalize.normalize(task, "axiom_based")
    return len(task.axioms)


class SasStreamingTest(unittest.TestCase):
    def test_parser_hashes_and_summarizes_without_cost_vector(self):
        payload = _sas("1 0 0 0 -1 1", 7)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "output.sas"
            path.write_bytes(payload)
            result = TranslateV11.parse_and_hash_sas(path)
        self.assertEqual(result["sas_bytes"], len(payload))
        self.assertEqual(result["sas_sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(result["sas"], {
            "sas_version": 3,
            "metric": 1,
            "num_variables": 1,
            "num_mutex_groups": 0,
            "num_operators": 1,
            "num_effects": 1,
            "num_conditional_effects": 1,
            "num_zero_cost_operators": 0,
            "min_operator_cost": 7,
            "max_operator_cost": 7,
            "num_serialized_axioms": 0,
        })

    def test_parser_rejects_malformed_truncated_and_trailing_sas(self):
        payloads = {
            "marker": _sas().replace(b"begin_metric", b"begin_metrics", 1),
            "effect": _sas().replace(b"0 0 -1 1", b"1 0 0 -1 1", 1),
            "truncated": _sas()[:-1],
            "trailing": _sas() + b"unexpected\n",
            "noncanonical-integer": _sas().replace(b"\n3\n", b"\n+3\n", 1),
        }
        for label, payload in payloads.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "output.sas"
                path.write_bytes(payload)
                with self.assertRaises(TranslateV11.SasFormatError):
                    TranslateV11.parse_and_hash_sas(path)

    def test_parser_rejects_nonregular_sas(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.sas"
            target.write_bytes(_sas())
            link = root / "output.sas"
            link.symlink_to(target)
            with self.assertRaisesRegex(
                TranslateV11.V11TranslationError, "regular output.sas"
            ):
                TranslateV11.parse_and_hash_sas(link)

    def test_large_synthetic_sas_has_bounded_parser_memory(self):
        operators = 100_000
        header = (
            "begin_version\n3\nend_version\n"
            "begin_metric\n1\nend_metric\n"
            "1\nbegin_variable\nvar0\n-1\n2\nAtom a()\n<none of those>\n"
            "end_variable\n0\nbegin_state\n0\nend_state\n"
            "begin_goal\n1\n0 1\nend_goal\n"
            f"{operators}\n"
        )
        block = "begin_operator\nmove\n0\n1\n0 0 -1 1\n1\nend_operator\n"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.sas"
            with path.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(header)
                chunk = block * 1_000
                for _ in range(operators // 1_000):
                    stream.write(chunk)
                stream.write("0\n")
            self.assertGreater(path.stat().st_size, 4 * 1024 * 1024)
            tracemalloc.start()
            result = TranslateV11.parse_and_hash_sas(path)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        self.assertEqual(result["sas"]["num_operators"], operators)
        self.assertEqual(result["sas"]["min_operator_cost"], 1)
        self.assertLess(peak, 4 * 1024 * 1024)

    def test_stream_evidence_hashes_large_file_and_keeps_fixed_tail(self):
        payload = (b"0123456789abcdef" * (1024 * 1024)) + b"final-tail"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stdout"
            path.write_bytes(payload)
            tracemalloc.start()
            evidence = TranslateV11.stream_file_evidence(path)
            _current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
        self.assertEqual(evidence["bytes"], len(payload))
        self.assertEqual(evidence["sha256"], hashlib.sha256(payload).hexdigest())
        self.assertEqual(evidence["tail_bytes"], TranslateV11.TAIL_BYTES)
        self.assertTrue(evidence["tail"].endswith("final-tail"))
        self.assertLess(peak, 4 * 1024 * 1024)


class ControlEvidenceTest(unittest.TestCase):
    def test_normalization_evidence_requires_exact_canonical_record(self):
        record = {
            "schema": TranslateV11.NORMALIZATION_EVIDENCE_SCHEMA,
            "strategy": "axiom_based",
            "num_normalized_axioms": 4,
        }
        descriptor = _write_fd_record(record)
        try:
            self.assertEqual(
                TranslateV11.read_normalization_evidence(descriptor), record
            )
        finally:
            os.close(descriptor)

        malformed = json.dumps(record, indent=2).encode("ascii") + b"\n"
        read_fd, write_fd = os.pipe()
        os.write(write_fd, malformed)
        os.close(write_fd)
        try:
            with self.assertRaisesRegex(
                TranslateV11.V11TranslationError, "complete record|canonical"
            ):
                TranslateV11.read_normalization_evidence(read_fd)
        finally:
            os.close(read_fd)

    def test_handshake_attests_limits_then_accepts_one_release_byte(self):
        start_read, start_write = os.pipe()
        limit_read, limit_write = os.pipe()
        os.write(start_write, TranslateV11.START_BYTE)
        os.close(start_write)
        def limit(which):
            if which == resource.RLIMIT_AS:
                return TranslateV11.EXPECTED_RLIMIT_AS
            self.assertEqual(which, resource.RLIMIT_CPU)
            return TranslateV11.EXPECTED_RLIMIT_CPU
        with (
            mock.patch.object(TranslateV11.resource, "getrlimit", side_effect=limit),
            mock.patch.object(TranslateV11.os, "getpid", return_value=1234),
            mock.patch.object(TranslateV11.os, "getpgrp", return_value=1234),
            mock.patch.object(
                TranslateV11, "_process_isolation_fields", return_value={
                    "no_new_privs": 1,
                    "seccomp_mode": 2,
                    "seccomp_filters": 1,
                    "threads": 1,
                },
            ),
        ):
            record = TranslateV11.perform_supervisor_handshake(
                start_read, limit_write
            )
        parsed = TranslateV11.read_limit_evidence(limit_read)
        os.close(limit_read)
        self.assertEqual(parsed, record)
        self.assertEqual(parsed["rlimit_as"], list(TranslateV11.EXPECTED_RLIMIT_AS))
        self.assertLess(
            len(TranslateV11._canonical_json_line(parsed)), TranslateV11.PIPE_BUF
        )

    def test_handshake_rejects_eof_bad_byte_limits_and_process_group(self):
        cases = (
            (b"", TranslateV11.EXPECTED_RLIMIT_AS, 9, 9),
            (b"X", TranslateV11.EXPECTED_RLIMIT_AS, 9, 9),
            (TranslateV11.START_BYTE, (1, 1), 9, 9),
            (TranslateV11.START_BYTE, TranslateV11.EXPECTED_RLIMIT_AS, 9, 8),
        )
        for release, address_limit, pid, process_group in cases:
            with self.subTest(
                release=release,
                address_limit=address_limit,
                process_group=process_group,
            ):
                start_read, start_write = os.pipe()
                limit_read, limit_write = os.pipe()
                if release:
                    os.write(start_write, release)
                os.close(start_write)
                def limit(which):
                    return (
                        address_limit if which == resource.RLIMIT_AS
                        else TranslateV11.EXPECTED_RLIMIT_CPU
                    )
                with (
                    mock.patch.object(
                        TranslateV11.resource, "getrlimit", side_effect=limit
                    ),
                    mock.patch.object(TranslateV11.os, "getpid", return_value=pid),
                    mock.patch.object(
                        TranslateV11.os, "getpgrp", return_value=process_group
                    ),
                    mock.patch.object(
                        TranslateV11, "_process_isolation_fields", return_value={
                            "no_new_privs": 1,
                            "seccomp_mode": 2,
                            "seccomp_filters": 1,
                            "threads": 1,
                        },
                    ),
                    self.assertRaises(TranslateV11.WrapperFatalError),
                ):
                    TranslateV11.perform_supervisor_handshake(
                        start_read, limit_write
                    )
                os.close(limit_read)

    def test_cli_requires_three_distinct_private_fds_and_separator(self):
        invalid = (
            ["--start-fd", "3", "--limit-evidence-fd", "4",
             "--normalization-evidence-fd", "5", "domain", "problem"],
            ["--start-fd", "3", "--limit-evidence-fd", "3",
             "--normalization-evidence-fd", "5", "--", "domain", "problem"],
            ["--start-fd", "0", "--limit-evidence-fd", "4",
             "--normalization-evidence-fd", "5", "--", "domain", "problem"],
        )
        for argv in invalid:
            with self.subTest(argv=argv), self.assertRaises(
                TranslateV11.WrapperFatalError
            ):
                TranslateV11._parse_cli(argv)

    def test_malformed_release_has_distinct_fatal_wrapper_exit(self):
        namespace = SimpleNamespace(
            start_fd=3, limit_evidence_fd=4, normalization_evidence_fd=5
        )
        with (
            mock.patch.object(
                TranslateV11, "_parse_cli", return_value=(namespace, ["d", "p"])
            ),
            mock.patch.object(
                TranslateV11,
                "perform_supervisor_handshake",
                side_effect=TranslateV11.WrapperFatalError("bad release"),
            ),
            mock.patch.object(TranslateV11, "run_translator") as run,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(TranslateV11.main([]), TranslateV11.WRAPPER_FATAL_EXIT)
        run.assert_not_called()


class OnePassTranslatorTest(unittest.TestCase):
    def _run_mocked(self, fake_main, fake_normalize=lambda task, strategy: None):
        from translate import normalize
        import translate.main

        read_fd, write_fd = os.pipe()
        with (
            mock.patch.object(normalize, "normalize", side_effect=fake_normalize) as norm,
            mock.patch.object(translate.main, "main", side_effect=fake_main) as main,
            mock.patch.object(
                TranslateV11.signal, "signal", return_value=signal_default()
            ),
        ):
            code = TranslateV11.run_translator(["domain", "problem"], write_fd)
        payload = TranslateV11._read_bounded_fd(read_fd, "test evidence")
        os.close(read_fd)
        return code, payload, main, norm

    def test_run_translator_invokes_main_and_normalization_once(self):
        from translate import normalize

        task = SimpleNamespace(axioms=[object(), object()])
        def fake_main():
            normalize.normalize(task, "axiom_based")
        code, payload, main, norm = self._run_mocked(fake_main)
        descriptor = _write_bytes_fd(payload)
        try:
            evidence = TranslateV11.read_normalization_evidence(descriptor)
        finally:
            os.close(descriptor)
        self.assertEqual(code, 0)
        self.assertEqual(evidence["num_normalized_axioms"], 2)
        main.assert_called_once_with()
        norm.assert_called_once_with(task, "axiom_based")

    def test_duplicate_normalization_is_fatal(self):
        from translate import normalize
        import translate.main

        task = SimpleNamespace(axioms=[])
        def fake_main():
            normalize.normalize(task, "axiom_based")
            normalize.normalize(task, "axiom_based")
        read_fd, write_fd = os.pipe()
        with (
            mock.patch.object(normalize, "normalize", return_value=None),
            mock.patch.object(translate.main, "main", side_effect=fake_main),
            mock.patch.object(
                TranslateV11.signal, "signal", return_value=signal_default()
            ),
            self.assertRaisesRegex(
                TranslateV11.WrapperFatalError, "more than once"
            ),
        ):
            TranslateV11.run_translator(["domain", "problem"], write_fd)
        os.close(read_fd)

    def test_documented_memory_and_input_exit_codes_are_preserved(self):
        from translate.pddl_parser import ParseError

        for exception, expected in (
            (MemoryError(), TranslateV11.TRANSLATE_OUT_OF_MEMORY),
            (ParseError("bad input"), TranslateV11.TRANSLATE_INPUT_ERROR),
        ):
            with self.subTest(expected=expected), contextlib.redirect_stdout(
                io.StringIO()
            ):
                code, payload, main, norm = self._run_mocked(
                    mock.Mock(side_effect=exception)
                )
            self.assertEqual(code, expected)
            self.assertEqual(payload, b"")
            main.assert_called_once_with()
            norm.assert_not_called()

    def test_documented_cpu_handler_uses_exit_21(self):
        with (
            mock.patch.object(TranslateV11.os, "_exit") as exit_process,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            TranslateV11._handle_sigxcpu(None, None)
        exit_process.assert_called_once_with(TranslateV11.TRANSLATE_OUT_OF_TIME)

    def test_unexpected_translator_error_is_not_reclassified(self):
        from translate import normalize
        import translate.main

        read_fd, write_fd = os.pipe()
        with (
            mock.patch.object(normalize, "normalize", return_value=None),
            mock.patch.object(
                translate.main, "main", side_effect=RuntimeError("unexpected")
            ),
            mock.patch.object(
                TranslateV11.signal, "signal", return_value=signal_default()
            ),
            self.assertRaisesRegex(RuntimeError, "unexpected"),
        ):
            TranslateV11.run_translator(["domain", "problem"], write_fd)
        os.close(read_fd)


def signal_default():
    return TranslateV11.signal.SIG_DFL


def _write_bytes_fd(payload: bytes) -> int:
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload)
    os.close(write_fd)
    return read_fd


class DifferentialTranslatorTest(unittest.TestCase):
    def test_v9_v11_scientific_projection_is_identical(self):
        constant_names = (
            "TRANSLATE_OUT_OF_MEMORY", "TRANSLATE_OUT_OF_TIME",
            "TRANSLATE_INPUT_ERROR", "WRAPPER_FATAL_EXIT",
            "ADDRESS_SPACE_LIMIT_BYTES", "CPU_LIMIT_SECONDS",
            "CPU_HARD_LIMIT_SECONDS", "EXPECTED_RLIMIT_AS",
            "EXPECTED_RLIMIT_CPU", "START_BYTE", "PIPE_BUF",
            "MAX_CONTROL_EVIDENCE_BYTES", "TAIL_BYTES",
            "STREAM_CHUNK_BYTES", "MAX_SAS_LINE_BYTES",
        )
        for name in constant_names:
            with self.subTest(name=name):
                self.assertEqual(
                    getattr(TranslateV11, name), getattr(TranslateV9, name)
                )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "output.sas"
            path.write_bytes(_sas())
            self.assertEqual(
                TranslateV11.parse_and_hash_sas(path),
                TranslateV9.parse_and_hash_sas(path),
            )

    def test_successful_ordinary_fixture_has_byte_identical_sas(self):
        domain = REPO / "misc/tests/benchmarks/gripper/domain.pddl"
        problem = REPO / "misc/tests/benchmarks/gripper/prob01.pddl"
        with (
            tempfile.TemporaryDirectory() as historical_tmp,
            tempfile.TemporaryDirectory() as v11_tmp,
        ):
            historical, historical_sas = _run_historical(
                domain, problem, Path(historical_tmp)
            )
            v11, v11_sas, limits, normalization_payload = _run_v11(
                domain, problem, Path(v11_tmp)
            )
            self.assertEqual(historical.returncode, 0, historical.stderr.decode())
            self.assertEqual(v11.returncode, 0, v11.stderr.decode())
            self.assertEqual(v11_sas, historical_sas)
            historical_summary = TranslateV11.parse_and_hash_sas(
                Path(historical_tmp) / "output.sas"
            )
            v11_summary = TranslateV11.parse_and_hash_sas(
                Path(v11_tmp) / "output.sas"
            )
        normalization_fd = _write_bytes_fd(normalization_payload)
        try:
            normalization = TranslateV11.read_normalization_evidence(
                normalization_fd
            )
        finally:
            os.close(normalization_fd)
        self.assertEqual(historical_summary, v11_summary)
        self.assertEqual(normalization["num_normalized_axioms"], 0)
        self.assertEqual(limits["pid"], limits["process_group"])
        self.assertGreater(historical_summary["sas"]["num_operators"], 0)
        self.assertEqual(
            historical_summary["sas"]["num_conditional_effects"], 0
        )
        self.assertGreaterEqual(historical_summary["sas"]["min_operator_cost"], 1)

    def test_normalized_axiom_fixture_has_identical_sas_and_same_pass_count(self):
        domain = REPO / "misc/tests/benchmarks/philosophers/domain.pddl"
        problem = REPO / "misc/tests/benchmarks/philosophers/p01-phil2.pddl"
        expected_axioms = _normalized_axiom_count(domain, problem)
        self.assertGreater(expected_axioms, 0)
        with (
            tempfile.TemporaryDirectory() as historical_tmp,
            tempfile.TemporaryDirectory() as v11_tmp,
        ):
            historical, historical_sas = _run_historical(
                domain, problem, Path(historical_tmp)
            )
            v11, v11_sas, _limits, normalization_payload = _run_v11(
                domain, problem, Path(v11_tmp)
            )
            self.assertEqual(historical.returncode, 0, historical.stderr.decode())
            self.assertEqual(v11.returncode, 0, v11.stderr.decode())
            self.assertEqual(v11_sas, historical_sas)
            historical_summary = TranslateV11.parse_and_hash_sas(
                Path(historical_tmp) / "output.sas"
            )
            v11_summary = TranslateV11.parse_and_hash_sas(
                Path(v11_tmp) / "output.sas"
            )
        normalization_fd = _write_bytes_fd(normalization_payload)
        try:
            normalization = TranslateV11.read_normalization_evidence(
                normalization_fd
            )
        finally:
            os.close(normalization_fd)
        self.assertEqual(historical_summary, v11_summary)
        self.assertEqual(
            normalization["num_normalized_axioms"], expected_axioms
        )

    def test_input_rejected_fixture_has_identical_exit_and_sas_absence(self):
        with (
            tempfile.TemporaryDirectory() as sources,
            tempfile.TemporaryDirectory() as historical_tmp,
            tempfile.TemporaryDirectory() as v11_tmp,
        ):
            source_root = Path(sources)
            domain = source_root / "domain.pddl"
            problem = source_root / "problem.pddl"
            domain.write_text("this is not pddl\n", encoding="utf-8")
            problem.write_text("this is not pddl either\n", encoding="utf-8")
            historical, historical_sas = _run_historical(
                domain, problem, Path(historical_tmp)
            )
            v11, v11_sas, _limits, normalization_payload = _run_v11(
                domain, problem, Path(v11_tmp)
            )
        self.assertEqual(
            historical.returncode, TranslateV11.TRANSLATE_INPUT_ERROR
        )
        self.assertEqual(v11.returncode, TranslateV11.TRANSLATE_INPUT_ERROR)
        self.assertIsNone(historical_sas)
        self.assertIsNone(v11_sas)
        self.assertEqual(normalization_payload, b"")


if __name__ == "__main__":
    unittest.main()
