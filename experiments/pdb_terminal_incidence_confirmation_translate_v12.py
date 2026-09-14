#!/usr/bin/env python3
"""One-pass, bounded translator support for source-audit campaign V12."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import resource
import signal
import stat
import sys
import traceback
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
SOURCE_ROOT = REPO / "src"

BASE_SCHEMA = (
    "symbolic-search-heuristics/universal-unseen-confirmation-source-audit/"
    "v1/campaign-v12"
)
LIMIT_EVIDENCE_SCHEMA = BASE_SCHEMA + "/child-limit-evidence/v1"
NORMALIZATION_EVIDENCE_SCHEMA = BASE_SCHEMA + "/normalization-evidence/v1"

TRANSLATE_OUT_OF_MEMORY = 20
TRANSLATE_OUT_OF_TIME = 21
TRANSLATE_INPUT_ERROR = 31
WRAPPER_FATAL_EXIT = 70

ADDRESS_SPACE_LIMIT_BYTES = 24_576 * 1024 * 1024
CPU_LIMIT_SECONDS = 1_800
CPU_HARD_LIMIT_SECONDS = CPU_LIMIT_SECONDS + 1
EXPECTED_RLIMIT_AS = (ADDRESS_SPACE_LIMIT_BYTES, ADDRESS_SPACE_LIMIT_BYTES)
EXPECTED_RLIMIT_CPU = (CPU_LIMIT_SECONDS, CPU_HARD_LIMIT_SECONDS)

START_BYTE = b"G"
PIPE_BUF = 4_096
MAX_CONTROL_EVIDENCE_BYTES = 1_024
TAIL_BYTES = 8_192
STREAM_CHUNK_BYTES = 1024 * 1024
MAX_SAS_LINE_BYTES = 16 * 1024 * 1024

_INTEGER = re.compile(r"-?(?:0|[1-9][0-9]*)\Z")


class V12TranslationError(RuntimeError):
    """Base class for malformed V12 translator evidence."""


class SasFormatError(V12TranslationError):
    """Raised when output.sas is not a complete canonical SAS v3 stream."""


class WrapperFatalError(V12TranslationError):
    """Raised for a V12 wrapper or supervisor-contract failure."""


def _canonical_json_line(value: dict) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("ascii")


def _write_control_record(fd: int, value: dict, label: str) -> None:
    payload = _canonical_json_line(value)
    if len(payload) > min(PIPE_BUF, MAX_CONTROL_EVIDENCE_BYTES):
        raise WrapperFatalError(f"{label} exceeds the atomic evidence bound")
    try:
        written = os.write(fd, payload)
    except OSError as err:
        raise WrapperFatalError(f"cannot write {label}") from err
    if written != len(payload):
        raise WrapperFatalError(f"short write for {label}")


def _read_bounded_fd(fd: int, label: str) -> bytes:
    payload = bytearray()
    while True:
        try:
            chunk = os.read(fd, MAX_CONTROL_EVIDENCE_BYTES + 1 - len(payload))
        except OSError as err:
            raise V12TranslationError(f"cannot read {label}") from err
        if not chunk:
            break
        payload.extend(chunk)
        if len(payload) > MAX_CONTROL_EVIDENCE_BYTES:
            raise V12TranslationError(f"{label} exceeds its evidence bound")
    return bytes(payload)


def _decode_canonical_record(payload: bytes, label: str) -> dict:
    if not payload or not payload.endswith(b"\n") or payload.count(b"\n") != 1:
        raise V12TranslationError(f"{label} is not one complete record")
    try:
        value = json.loads(payload.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise V12TranslationError(f"{label} is not canonical JSON") from err
    if not isinstance(value, dict) or _canonical_json_line(value) != payload:
        raise V12TranslationError(f"{label} is not canonical JSON")
    return value


def read_normalization_evidence(fd: int) -> dict:
    """Read and validate the one bounded same-pass normalization record."""
    value = _decode_canonical_record(
        _read_bounded_fd(fd, "normalization evidence"),
        "normalization evidence",
    )
    if (
        set(value) != {"schema", "strategy", "num_normalized_axioms"}
        or value["schema"] != NORMALIZATION_EVIDENCE_SCHEMA
        or value["strategy"] != "axiom_based"
        or type(value["num_normalized_axioms"]) is not int
        or value["num_normalized_axioms"] < 0
    ):
        raise V12TranslationError("normalization evidence schema changed")
    return value


def read_limit_evidence(fd: int) -> dict:
    """Read and validate the one bounded pre-release child-limit record."""
    value = _decode_canonical_record(
        _read_bounded_fd(fd, "child-limit evidence"),
        "child-limit evidence",
    )
    if (
        set(value)
        != {
            "schema", "pid", "process_group", "rlimit_as", "rlimit_cpu",
            "no_new_privs", "seccomp_mode", "seccomp_filters", "threads",
        }
        or value["schema"] != LIMIT_EVIDENCE_SCHEMA
        or type(value["pid"]) is not int
        or value["pid"] <= 0
        or type(value["process_group"]) is not int
        or value["process_group"] <= 0
        or value["process_group"] != value["pid"]
        or value["rlimit_as"] != list(EXPECTED_RLIMIT_AS)
        or value["rlimit_cpu"] != list(EXPECTED_RLIMIT_CPU)
        or value["no_new_privs"] != 1
        or value["seccomp_mode"] != 2
        or type(value["seccomp_filters"]) is not int
        or value["seccomp_filters"] < 1
        or value["threads"] != 1
    ):
        raise V12TranslationError("child-limit evidence schema changed")
    return value


def _open_regular_binary(path: Path, label: str):
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(path, flags)
    except OSError as err:
        raise V12TranslationError(f"cannot open regular {label}") from err
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise V12TranslationError(f"{label} is not a regular file")
        return os.fdopen(fd, "rb", buffering=STREAM_CHUNK_BYTES)
    except BaseException:
        os.close(fd)
        raise


def stream_file_evidence(path: Path, tail_bytes: int = TAIL_BYTES) -> dict:
    """Hash a regular file and retain only a bounded byte tail."""
    if type(tail_bytes) is not int or not 0 <= tail_bytes <= TAIL_BYTES:
        raise V12TranslationError("stream tail bound changed")
    digest = hashlib.sha256()
    size = 0
    tail = bytearray()
    with _open_regular_binary(Path(path), "stream") as stream:
        while True:
            chunk = stream.read(STREAM_CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
            if tail_bytes:
                tail.extend(chunk)
                if len(tail) > tail_bytes:
                    del tail[:-tail_bytes]
    return {
        "bytes": size,
        "sha256": digest.hexdigest(),
        "tail": bytes(tail).decode("utf-8", "replace"),
        "tail_bytes": len(tail),
    }


class _SasReader:
    def __init__(self, stream):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.bytes_read = 0

    def _raw_line(self) -> bytes:
        raw = self.stream.readline(MAX_SAS_LINE_BYTES + 1)
        if not raw:
            raise SasFormatError("unexpected end of serialized SAS")
        self.digest.update(raw)
        self.bytes_read += len(raw)
        if len(raw) > MAX_SAS_LINE_BYTES:
            raise SasFormatError("serialized SAS line exceeds fixed bound")
        if not raw.endswith(b"\n"):
            raise SasFormatError("truncated serialized SAS line")
        return raw[:-1]

    def line(self) -> str:
        raw = self._raw_line()
        if b"\r" in raw or b"\x00" in raw:
            raise SasFormatError("invalid serialized SAS character")
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError as err:
            raise SasFormatError("serialized SAS is not UTF-8") from err

    @staticmethod
    def _parse_integer(value: str) -> int:
        if _INTEGER.fullmatch(value) is None:
            raise SasFormatError("expected canonical serialized SAS integer")
        try:
            return int(value)
        except ValueError as err:
            raise SasFormatError("serialized SAS integer is too large") from err

    def integer(self) -> int:
        return self._parse_integer(self.line())

    def count(self, label: str) -> int:
        value = self.integer()
        if value < 0:
            raise SasFormatError(f"negative serialized SAS {label} count")
        return value

    def integer_fields(self):
        line = self.line()
        if not line or line.startswith(" ") or line.endswith(" "):
            raise SasFormatError("expected serialized SAS integer fields")
        start = 0
        while True:
            separator = line.find(" ", start)
            if separator == start:
                raise SasFormatError("noncanonical serialized SAS spacing")
            if separator < 0:
                yield self._parse_integer(line[start:])
                return
            yield self._parse_integer(line[start:separator])
            start = separator + 1

    def exact_integer_fields(self, expected: int) -> None:
        seen = 0
        for _value in self.integer_fields():
            seen += 1
            if seen > expected:
                raise SasFormatError("serialized SAS field arity changed")
        if seen != expected:
            raise SasFormatError("serialized SAS field arity changed")

    def effect(self) -> bool:
        fields = self.integer_fields()
        try:
            conditions = next(fields)
        except StopIteration as err:
            raise SasFormatError("empty serialized SAS effect") from err
        if conditions < 0:
            raise SasFormatError("negative serialized SAS effect condition count")
        expected = 4 + 2 * conditions
        seen = 1
        for _value in fields:
            seen += 1
            if seen > expected:
                raise SasFormatError("serialized SAS effect arity changed")
        if seen != expected:
            raise SasFormatError("serialized SAS effect arity changed")
        return conditions > 0

    def expect(self, expected: str) -> None:
        if self.line() != expected:
            raise SasFormatError("serialized SAS marker changed")

    def require_eof(self) -> None:
        raw = self.stream.readline(MAX_SAS_LINE_BYTES + 1)
        if raw:
            self.digest.update(raw)
            self.bytes_read += len(raw)
            raise SasFormatError("serialized SAS has trailing content")


def parse_and_hash_sas(path: Path) -> dict:
    """Strictly parse and hash SAS v3 in one bounded-memory pass."""
    with _open_regular_binary(Path(path), "output.sas") as stream:
        reader = _SasReader(stream)
        reader.expect("begin_version")
        version = reader.integer()
        reader.expect("end_version")
        if version != 3:
            raise SasFormatError("serialized SAS version changed")

        reader.expect("begin_metric")
        metric = reader.integer()
        reader.expect("end_metric")
        if metric not in (0, 1):
            raise SasFormatError("serialized SAS metric flag changed")

        num_variables = reader.count("variable")
        for variable in range(num_variables):
            reader.expect("begin_variable")
            if reader.line() != f"var{variable}":
                raise SasFormatError("serialized SAS variable name changed")
            if reader.integer() < -1:
                raise SasFormatError("serialized SAS axiom layer changed")
            domain_size = reader.count("variable-domain")
            for _ in range(domain_size):
                reader.line()
            reader.expect("end_variable")

        num_mutex_groups = reader.count("mutex-group")
        for _ in range(num_mutex_groups):
            reader.expect("begin_mutex_group")
            for _ in range(reader.count("mutex-fact")):
                reader.exact_integer_fields(2)
            reader.expect("end_mutex_group")

        reader.expect("begin_state")
        for _ in range(num_variables):
            reader.integer()
        reader.expect("end_state")

        reader.expect("begin_goal")
        for _ in range(reader.count("goal-fact")):
            reader.exact_integer_fields(2)
        reader.expect("end_goal")

        num_operators = reader.count("operator")
        num_effects = 0
        num_conditional_effects = 0
        num_zero_cost_operators = 0
        min_operator_cost = None
        max_operator_cost = None
        for _ in range(num_operators):
            reader.expect("begin_operator")
            if not reader.line():
                raise SasFormatError("empty serialized SAS operator name")
            for _ in range(reader.count("prevail")):
                reader.exact_integer_fields(2)
            operator_effects = reader.count("operator-effect")
            num_effects += operator_effects
            for _ in range(operator_effects):
                num_conditional_effects += reader.effect()
            cost = reader.integer()
            if cost < 0:
                raise SasFormatError("negative serialized SAS operator cost")
            num_zero_cost_operators += cost == 0
            min_operator_cost = (
                cost if min_operator_cost is None else min(min_operator_cost, cost)
            )
            max_operator_cost = (
                cost if max_operator_cost is None else max(max_operator_cost, cost)
            )
            reader.expect("end_operator")

        num_axioms = reader.count("axiom")
        for _ in range(num_axioms):
            reader.expect("begin_rule")
            for _ in range(reader.count("axiom-condition")):
                reader.exact_integer_fields(2)
            reader.exact_integer_fields(3)
            reader.expect("end_rule")
        reader.require_eof()

        summary = {
            "sas_version": version,
            "metric": metric,
            "num_variables": num_variables,
            "num_mutex_groups": num_mutex_groups,
            "num_operators": num_operators,
            "num_effects": num_effects,
            "num_conditional_effects": num_conditional_effects,
            "num_zero_cost_operators": num_zero_cost_operators,
            "min_operator_cost": min_operator_cost,
            "max_operator_cost": max_operator_cost,
            "num_serialized_axioms": num_axioms,
        }
        return {
            "sas": summary,
            "sas_bytes": reader.bytes_read,
            "sas_sha256": reader.digest.hexdigest(),
        }


class _NormalizationObserver:
    def __init__(self, original, evidence_fd: int):
        self.original = original
        self.evidence_fd = evidence_fd
        self.calls = 0

    def __call__(self, task, strategy):
        if self.calls:
            raise WrapperFatalError("translator normalized more than once")
        self.calls += 1
        result = self.original(task, strategy)
        if strategy != "axiom_based":
            raise WrapperFatalError("translator normalization strategy changed")
        record = {
            "schema": NORMALIZATION_EVIDENCE_SCHEMA,
            "strategy": strategy,
            "num_normalized_axioms": len(task.axioms),
        }
        _write_control_record(
            self.evidence_fd, record, "normalization evidence"
        )
        os.close(self.evidence_fd)
        self.evidence_fd = None
        return result

    def close(self) -> None:
        if self.evidence_fd is not None:
            try:
                os.close(self.evidence_fd)
            except OSError:
                pass
            self.evidence_fd = None


def _handle_sigxcpu(_signum, _stackframe) -> None:
    print()
    print("Translator hit the time limit")
    os._exit(TRANSLATE_OUT_OF_TIME)


def run_translator(translator_args: list[str], normalization_evidence_fd: int) -> int:
    """Run the pinned translator main exactly once with same-pass evidence."""
    source_root = str(SOURCE_ROOT)
    if source_root not in sys.path:
        sys.path.insert(0, source_root)

    from translate import normalize
    from translate import pddl_parser
    from translate import options
    from translate.main import main as translator_main

    options.set_options(translator_args)
    parsed_options = options.get_options()
    if (
        parsed_options.normalization_strategy != "axiom_based"
        or parsed_options.sas_file != "output.sas"
    ):
        raise WrapperFatalError("translator options changed")

    previous_handler = None
    try:
        previous_handler = signal.signal(signal.SIGXCPU, _handle_sigxcpu)
    except AttributeError:
        print(
            "Warning! SIGXCPU is not available on your platform. "
            "This means that the planner cannot be gracefully terminated "
            "when using a time limit, which, however, is probably supported "
            "on your platform anyway."
        )

    observer = _NormalizationObserver(
        normalize.normalize, normalization_evidence_fd
    )
    normalize.normalize = observer
    emergency_memory = None
    try:
        emergency_memory = b"x" * 10**7
        translator_main()
    except MemoryError:
        emergency_memory = None
        print()
        print("Translator ran out of memory, traceback:")
        print("=" * 79)
        traceback.print_exc(file=sys.stdout)
        print("=" * 79)
        return TRANSLATE_OUT_OF_MEMORY
    except pddl_parser.ParseError as err:
        print(err)
        return TRANSLATE_INPUT_ERROR
    finally:
        emergency_memory = None
        normalize.normalize = observer.original
        observer.close()
        if previous_handler is not None:
            signal.signal(signal.SIGXCPU, previous_handler)
    if observer.calls != 1:
        raise WrapperFatalError("translator did not normalize exactly once")
    return 0


def _process_isolation_fields() -> dict:
    wanted = {"NoNewPrivs", "Seccomp", "Seccomp_filters", "Threads"}
    values = {}
    try:
        with open("/proc/self/status", encoding="ascii") as stream:
            for line in stream:
                key, separator, value = line.partition(":")
                if separator and key in wanted:
                    if key in values:
                        raise ValueError("duplicate process-status field")
                    values[key] = int(value.strip())
    except (OSError, UnicodeError, ValueError) as err:
        raise WrapperFatalError("cannot inspect child process isolation") from err
    if set(values) != wanted:
        raise WrapperFatalError("child process-isolation fields changed")
    return {
        "no_new_privs": values["NoNewPrivs"],
        "seccomp_mode": values["Seccomp"],
        "seccomp_filters": values["Seccomp_filters"],
        "threads": values["Threads"],
    }


def perform_supervisor_handshake(start_fd: int, limit_evidence_fd: int) -> dict:
    """Attest exact limits/process group, then wait for the release byte."""
    record = {
        "schema": LIMIT_EVIDENCE_SCHEMA,
        "pid": os.getpid(),
        "process_group": os.getpgrp(),
        "rlimit_as": list(resource.getrlimit(resource.RLIMIT_AS)),
        "rlimit_cpu": list(resource.getrlimit(resource.RLIMIT_CPU)),
        **_process_isolation_fields(),
    }
    try:
        _write_control_record(limit_evidence_fd, record, "child-limit evidence")
    finally:
        try:
            os.close(limit_evidence_fd)
        except OSError:
            pass
    if (
        tuple(record["rlimit_as"]) != EXPECTED_RLIMIT_AS
        or tuple(record["rlimit_cpu"]) != EXPECTED_RLIMIT_CPU
        or record["process_group"] != record["pid"]
        or record["no_new_privs"] != 1
        or record["seccomp_mode"] != 2
        or record["seccomp_filters"] < 1
        or record["threads"] != 1
    ):
        try:
            os.close(start_fd)
        except OSError:
            pass
        raise WrapperFatalError("child limits or process group changed")
    try:
        release = os.read(start_fd, 1)
    except OSError as err:
        raise WrapperFatalError("cannot read supervisor release") from err
    finally:
        try:
            os.close(start_fd)
        except OSError:
            pass
    if release != START_BYTE:
        raise WrapperFatalError("invalid supervisor release")
    return record


def _parse_cli(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    if "--" not in argv:
        raise WrapperFatalError("translator arguments require -- separator")
    separator = argv.index("--")
    parser = argparse.ArgumentParser(
        description="Run the one-pass V12 translator child"
    )
    parser.add_argument("--start-fd", type=int, required=True)
    parser.add_argument("--limit-evidence-fd", type=int, required=True)
    parser.add_argument("--normalization-evidence-fd", type=int, required=True)
    args = parser.parse_args(argv[:separator])
    translator_args = argv[separator + 1:]
    fds = (
        args.start_fd,
        args.limit_evidence_fd,
        args.normalization_evidence_fd,
    )
    if len(set(fds)) != len(fds) or any(fd < 3 for fd in fds):
        raise WrapperFatalError("control descriptors must be distinct and private")
    if not translator_args:
        raise WrapperFatalError("missing translator arguments")
    return args, translator_args


def main(argv: list[str] | None = None) -> int:
    try:
        args, translator_args = _parse_cli(
            list(sys.argv[1:] if argv is None else argv)
        )
        perform_supervisor_handshake(args.start_fd, args.limit_evidence_fd)
        return run_translator(
            translator_args, args.normalization_evidence_fd
        )
    except WrapperFatalError as err:
        print(f"V12 translator wrapper fatal: {err}", file=sys.stderr)
        return WRAPPER_FATAL_EXIT


if __name__ == "__main__":
    sys.exit(main())
