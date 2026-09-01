#!/usr/bin/env python3
"""Run one generated Lab cell with exclusive no-follow driver logs."""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path


class RunCellError(RuntimeError):
    pass


INFRASTRUCTURE_EXIT_CODE = 70


def _absent(path: Path) -> bool:
    try:
        os.lstat(path)
    except FileNotFoundError:
        return True
    except OSError as err:
        raise RunCellError("cannot inspect dynamic output {}".format(path)) from err
    return False


def _exclusive_output(path: Path) -> int:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
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
        or any(Path(name).name != name or name in ("", ".", "..")
               for name in dynamic_names)
    ):
        raise RunCellError("dynamic output namespace is invalid")
    paths = [Path(name) for name in dynamic_names]
    if any(not _absent(path) for path in paths):
        raise RunCellError("a dynamic output already exists")

    stdout_fd = _exclusive_output(stdout_path)
    try:
        stderr_fd = _exclusive_output(stderr_path)
    except Exception:
        os.close(stdout_fd)
        raise
    try:
        if (
            not _same_open_entry(stdout_path, stdout_fd)
            or not _same_open_entry(stderr_path, stderr_fd)
            or any(
                not _absent(path)
                for path in paths
                if path not in (stdout_path, stderr_path)
            )
        ):
            raise RunCellError("dynamic output namespace changed before execution")
        try:
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
        except OSError as err:
            raise RunCellError("cell helper failed after namespace setup") from err
        # Once the run script has been launched, its return code is an ordinary
        # planner outcome.  The run script and parsers account for it; the
        # helper itself succeeds so the remaining cells in this array element
        # retain the frozen outcome-accounting behavior.
        return 0
    finally:
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
