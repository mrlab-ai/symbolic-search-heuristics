#!/usr/bin/env python3
"""Run one generated Lab cell with exclusive no-follow driver logs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path


class RunCellError(RuntimeError):
    pass


INFRASTRUCTURE_EXIT_CODE = 70
HARDWARE_ATTESTATION_NAME = "execution-hardware-v1.json"
HARDWARE_ATTESTATION_SCHEMA = (
    "symbolic-search-heuristics/execution-hardware/v1"
)
MAX_CPUINFO_BYTES = 4 * 1024 * 1024
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _canonical_json_line(value: object) -> bytes:
    return _canonical_json(value) + b"\n"


def _normalized_ascii(value: object, label: str, *, max_length: int) -> str:
    if not isinstance(value, str):
        raise RunCellError("{} is not text".format(label))
    normalized = " ".join(value.split())
    if (
        not normalized
        or len(normalized) > max_length
        or re.fullmatch(r"[ -~]+", normalized) is None
    ):
        raise RunCellError("{} is invalid".format(label))
    return normalized


def build_hardware_attestation(cpuinfo_raw: bytes, machine: str) -> dict:
    if not isinstance(cpuinfo_raw, bytes) or len(cpuinfo_raw) > MAX_CPUINFO_BYTES:
        raise RunCellError("processor information is invalid")
    try:
        cpuinfo = cpuinfo_raw.decode("ascii")
    except UnicodeDecodeError as err:
        raise RunCellError("processor information is not ASCII") from err
    models = []
    for line in cpuinfo.splitlines():
        key, separator, value = line.partition(":")
        if separator and key.strip() == "model name":
            models.append(
                _normalized_ascii(value, "processor model", max_length=256)
            )
    unique_models = set(models)
    if len(unique_models) != 1:
        raise RunCellError("processor model is absent or inconsistent")
    architecture = _normalized_ascii(
        machine, "processor architecture", max_length=64
    )
    return {
        "schema": HARDWARE_ATTESTATION_SCHEMA,
        "processor_model": unique_models.pop(),
        "architecture": architecture,
    }


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    value = {}
    for key, item in pairs:
        if key in value:
            raise RunCellError("hardware attestation has duplicate keys")
        value[key] = item
    return value


def parse_hardware_attestation(raw: bytes) -> dict:
    if not isinstance(raw, bytes) or len(raw) > 4096:
        raise RunCellError("hardware attestation is invalid")
    try:
        value = json.loads(
            raw.decode("ascii"), object_pairs_hook=_reject_duplicate_keys
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise RunCellError("hardware attestation is not canonical JSON") from err
    if (
        not isinstance(value, dict)
        or set(value) != {"schema", "processor_model", "architecture"}
        or value.get("schema") != HARDWARE_ATTESTATION_SCHEMA
    ):
        raise RunCellError("hardware attestation schema changed")
    model = _normalized_ascii(
        value.get("processor_model"), "processor model", max_length=256
    )
    architecture = _normalized_ascii(
        value.get("architecture"), "processor architecture", max_length=64
    )
    if (
        model != value["processor_model"]
        or architecture != value["architecture"]
        or raw != _canonical_json_line(value)
    ):
        raise RunCellError("hardware attestation is not canonical")
    return value


def summarize_hardware_records(
    records: list[tuple[int, bytes]], groups: list[list[int]],
) -> dict:
    rows = []
    identities = {}
    for cell, raw in records:
        if type(cell) is not int or cell in identities:
            raise RunCellError("hardware cell mapping is invalid")
        value = parse_hardware_attestation(raw)
        identity = (value["processor_model"], value["architecture"])
        identities[cell] = identity
        rows.append({
            "cell": cell,
            "sha256": hashlib.sha256(raw).hexdigest(),
            **value,
        })
    expected_cells = list(range(1, len(records) + 1))
    if [row["cell"] for row in rows] != expected_cells:
        raise RunCellError("hardware records are not in cell order")
    grouped_cells = [cell for group in groups for cell in group]
    if grouped_cells != expected_cells or any(not group for group in groups):
        raise RunCellError("hardware array-element mapping is invalid")
    for group in groups:
        if len({identities[cell] for cell in group}) != 1:
            raise RunCellError("hardware changed within an array element")
    model_counts = Counter(row["processor_model"] for row in rows)
    architecture_counts = Counter(row["architecture"] for row in rows)
    return {
        "hardware_attestation_schema": HARDWARE_ATTESTATION_SCHEMA,
        "hardware_attestation_files": len(rows),
        "hardware_records_sha256": hashlib.sha256(
            _canonical_json(rows)
        ).hexdigest(),
        "processor_model_counts": dict(sorted(model_counts.items())),
        "architecture_counts": dict(sorted(architecture_counts.items())),
    }


def validate_hardware_summary(value: object, expected_files: int) -> None:
    if (
        not isinstance(value, dict)
        or set(value) != {
            "hardware_attestation_schema", "hardware_attestation_files",
            "hardware_records_sha256", "processor_model_counts",
            "architecture_counts",
        }
        or value.get("hardware_attestation_schema")
        != HARDWARE_ATTESTATION_SCHEMA
        or type(value.get("hardware_attestation_files")) is not int
        or value["hardware_attestation_files"] != expected_files
        or SHA256_RE.fullmatch(value.get("hardware_records_sha256", "")) is None
    ):
        raise RunCellError("hardware summary shape changed")
    for field, label, max_length in (
        ("processor_model_counts", "processor model", 256),
        ("architecture_counts", "processor architecture", 64),
    ):
        counts = value.get(field)
        if (
            not isinstance(counts, dict)
            or not counts
            or any(
                not isinstance(key, str)
                or type(count) is not int
                or count <= 0
                for key, count in counts.items()
            )
        ):
            raise RunCellError("hardware summary counts changed")
        if sum(counts.values()) != expected_files or any(
            _normalized_ascii(key, label, max_length=max_length) != key
            for key in counts
        ):
            raise RunCellError("hardware summary counts changed")


def _live_hardware_attestation() -> bytes:
    try:
        with open("/proc/cpuinfo", "rb") as stream:
            raw = stream.read(MAX_CPUINFO_BYTES + 1)
        machine = os.uname().machine
    except OSError as err:
        raise RunCellError("cannot read processor information") from err
    return _canonical_json_line(build_hardware_attestation(raw, machine))


def _absent(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError as err:
        raise RunCellError("cannot inspect dynamic output {}".format(path)) from err
    return False


def _exclusive_output(path: Path, *, read_write: bool = False) -> int:
    flags = (os.O_RDWR if read_write else os.O_WRONLY) | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(path, flags, 0o600)
        info = os.fstat(descriptor)
    except OSError as err:
        if descriptor is not None:
            os.close(descriptor)
        raise RunCellError(
            "cannot create dynamic output {} exclusively".format(path)
        ) from err
    if not stat.S_ISREG(info.st_mode):
        os.close(descriptor)
        raise RunCellError("dynamic output is not regular: {}".format(path))
    return descriptor


def _same_open_entry(path: Path, descriptor: int) -> bool:
    try:
        entry = os.lstat(path)
        opened = os.fstat(descriptor)
    except OSError as err:
        raise RunCellError("cannot revalidate dynamic output {}".format(path)) from err
    return (
        stat.S_ISREG(entry.st_mode)
        and stat.S_ISREG(opened.st_mode)
        and (entry.st_dev, entry.st_ino, entry.st_mode)
        == (opened.st_dev, opened.st_ino, opened.st_mode)
    )


def _write_all(descriptor: int, raw: bytes) -> None:
    offset = 0
    while offset < len(raw):
        written = os.write(descriptor, raw[offset:])
        if written <= 0:
            raise RunCellError("cannot write hardware attestation")
        offset += written


def _read_back(descriptor: int, expected_bytes: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks = []
    remaining = expected_bytes + 1
    while remaining:
        chunk = os.read(descriptor, remaining)
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def run_cell(
    python: Path,
    run_script: Path,
    stdout_path: Path,
    stderr_path: Path,
    dynamic_names: list[str],
) -> int:
    if (
        not dynamic_names
        or len(dynamic_names) != len(set(dynamic_names))
        or stdout_path.name not in dynamic_names
        or stderr_path.name not in dynamic_names
        or HARDWARE_ATTESTATION_NAME not in dynamic_names
        or any(Path(name).name != name or name in ("", ".", "..")
               for name in dynamic_names)
    ):
        raise RunCellError("dynamic output namespace is invalid")
    paths = [Path(name) for name in dynamic_names]
    if any(not _absent(path) for path in paths):
        raise RunCellError("a dynamic output already exists")
    hardware_raw = _live_hardware_attestation()
    hardware_path = Path(HARDWARE_ATTESTATION_NAME)

    stdout_fd = _exclusive_output(stdout_path)
    try:
        stderr_fd = _exclusive_output(stderr_path)
    except Exception:
        os.close(stdout_fd)
        raise
    try:
        hardware_fd = _exclusive_output(hardware_path, read_write=True)
    except Exception:
        os.close(stderr_fd)
        os.close(stdout_fd)
        raise
    try:
        if (
            not _same_open_entry(stdout_path, stdout_fd)
            or not _same_open_entry(stderr_path, stderr_fd)
            or not _same_open_entry(hardware_path, hardware_fd)
            or any(
                not _absent(path)
                for path in paths
                if path not in (stdout_path, stderr_path, hardware_path)
            )
        ):
            raise RunCellError("dynamic output namespace changed before execution")
        try:
            _write_all(hardware_fd, hardware_raw)
            os.fsync(hardware_fd)
            if not _same_open_entry(hardware_path, hardware_fd):
                raise RunCellError("hardware attestation changed before execution")
            completed = subprocess.run(
                [os.fspath(python), os.fspath(run_script)],
                stdin=subprocess.DEVNULL,
                stdout=stdout_fd,
                stderr=stderr_fd,
                close_fds=True,
                check=False,
            )
            if completed.returncode:
                os.write(
                    stderr_fd,
                    ("The run script finished with exit code {}\n".format(
                        completed.returncode
                    )).encode("ascii"),
                )
            os.fsync(stdout_fd)
            os.fsync(stderr_fd)
            if (
                not _same_open_entry(hardware_path, hardware_fd)
                or _read_back(hardware_fd, len(hardware_raw)) != hardware_raw
            ):
                raise RunCellError("hardware attestation changed during execution")
        except OSError as err:
            raise RunCellError("cell helper failed after namespace setup") from err
        # Once the run script has been launched, its return code is an ordinary
        # planner outcome.  The run script and parsers account for it; the
        # helper itself succeeds so the remaining cells in this array element
        # retain the frozen outcome-accounting behavior.
        return 0
    finally:
        os.close(hardware_fd)
        os.close(stderr_fd)
        os.close(stdout_fd)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--run-script", required=True, type=Path)
    parser.add_argument("--stdout", required=True, type=Path)
    parser.add_argument("--stderr", required=True, type=Path)
    parser.add_argument("--dynamic", action="append", required=True)
    args = parser.parse_args()
    try:
        returncode = run_cell(
            args.python, args.run_script, args.stdout, args.stderr, args.dynamic
        )
    except (RunCellError, OSError) as err:
        print("cell infrastructure failure: {}".format(err), file=sys.stderr)
        raise SystemExit(INFRASTRUCTURE_EXIT_CODE) from err
    raise SystemExit(returncode)


if __name__ == "__main__":
    main()
