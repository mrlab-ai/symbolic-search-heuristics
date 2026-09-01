#!/usr/bin/env python3
"""Race-resistant file reads shared by the Confirmation A/B consumers."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import stat
from dataclasses import dataclass
from pathlib import Path


class SafeReadError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegularFile:
    raw: bytes
    sha256: str
    identity: dict[str, int]


def _fingerprint(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _identity(info: os.stat_result) -> dict[str, int]:
    return {
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": info.st_mode,
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
    }


def validate_lexical_path(
    path: Path,
    *,
    label: str,
    expected_path: Path | None = None,
    root: Path | None = None,
) -> Path:
    """Validate path spelling without resolving or touching the filesystem."""
    raw_path = os.fspath(path)
    if not isinstance(raw_path, str) or not raw_path:
        raise SafeReadError("{} path is invalid".format(label))
    candidate = Path(raw_path)
    if ".." in candidate.parts:
        raise SafeReadError("{} path is not lexical".format(label))
    if expected_path is not None:
        expected_raw = os.fspath(expected_path)
        if raw_path != expected_raw:
            raise SafeReadError("{} path changed".format(label))
    if root is not None:
        root_path = Path(root)
        try:
            candidate.relative_to(root_path)
        except ValueError as err:
            raise SafeReadError("{} path escapes its root".format(label)) from err
    return candidate


def read_regular_file(
    path: Path,
    *,
    label: str,
    expected_path: Path | None = None,
    root: Path | None = None,
) -> RegularFile:
    """Read and hash a regular file through one stable descriptor chain."""
    candidate = validate_lexical_path(
        path, label=label, expected_path=expected_path, root=root
    )

    if root is not None:
        anchor = Path(root)
        try:
            relative = candidate.relative_to(anchor)
        except ValueError as err:  # Defensive: validate_lexical_path checked this.
            raise SafeReadError("{} path escapes its root".format(label)) from err
    elif candidate.is_absolute():
        anchor = Path(candidate.anchor)
        relative = candidate.relative_to(anchor)
    else:
        anchor = Path(".")
        relative = candidate
    parts = relative.parts
    if not parts:
        raise SafeReadError("{} is not a regular file".format(label))

    directory_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    directory_flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    file_flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptors: list[int] = []
    # Each entry retains the parent descriptor so a renamed/replaced ancestor is
    # detected against the directory in which it was originally found.
    ancestors: list[tuple[int, str, tuple[int, ...], int]] = []
    try:
        anchor_before = os.lstat(anchor)
        if not stat.S_ISDIR(anchor_before.st_mode):
            raise SafeReadError("{} root is not a directory".format(label))
        anchor_fd = os.open(anchor, directory_flags)
        descriptors.append(anchor_fd)
        anchor_opened = os.fstat(anchor_fd)
        if (
            not stat.S_ISDIR(anchor_opened.st_mode)
            or _fingerprint(anchor_opened) != _fingerprint(anchor_before)
        ):
            raise SafeReadError("{} root identity changed".format(label))

        parent_fd = anchor_fd
        for component in parts[:-1]:
            before = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise SafeReadError("{} ancestor is not a directory".format(label))
            child_fd = os.open(component, directory_flags, dir_fd=parent_fd)
            descriptors.append(child_fd)
            opened = os.fstat(child_fd)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or _fingerprint(opened) != _fingerprint(before)
            ):
                raise SafeReadError("{} ancestor identity changed".format(label))
            ancestors.append((parent_fd, component, _fingerprint(opened), child_fd))
            parent_fd = child_fd

        leaf = parts[-1]
        before = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise SafeReadError("{} is not a regular file".format(label))
        descriptor = os.open(leaf, file_flags, dir_fd=parent_fd)
        descriptors.append(descriptor)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or _fingerprint(opened) != _fingerprint(before)
        ):
            raise SafeReadError("{} identity changed before reading".format(label))

        blocks = []
        digest = hashlib.sha256()
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            blocks.append(block)
            digest.update(block)

        after_fd = os.fstat(descriptor)
        after_leaf = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(after_leaf.st_mode)
            or _fingerprint(after_fd) != _fingerprint(opened)
            or _fingerprint(after_leaf) != _fingerprint(opened)
        ):
            raise SafeReadError("{} identity changed while reading".format(label))

        for entry_parent, component, fingerprint, child_fd in reversed(ancestors):
            after_entry = os.stat(
                component, dir_fd=entry_parent, follow_symlinks=False
            )
            after_child = os.fstat(child_fd)
            if (
                not stat.S_ISDIR(after_entry.st_mode)
                or _fingerprint(after_entry) != fingerprint
                or _fingerprint(after_child) != fingerprint
            ):
                raise SafeReadError("{} ancestor changed while reading".format(label))
        anchor_after_fd = os.fstat(anchor_fd)
        anchor_after_path = os.lstat(anchor)
        if (
            _fingerprint(anchor_after_fd) != _fingerprint(anchor_opened)
            or _fingerprint(anchor_after_path) != _fingerprint(anchor_opened)
        ):
            raise SafeReadError("{} root changed while reading".format(label))
    except OSError as err:
        raise SafeReadError("cannot read {} safely".format(label)) from err
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
    return RegularFile(b"".join(blocks), digest.hexdigest(), _identity(opened))


def read_canonical_json(
    path: Path,
    *,
    label: str,
    canonical_json_line,
    expected_path: Path | None = None,
    root: Path | None = None,
) -> tuple[RegularFile, dict]:
    loaded = read_regular_file(
        path, label=label, expected_path=expected_path, root=root
    )
    try:
        value = json.loads(loaded.raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SafeReadError("cannot decode {}".format(label)) from err
    if not isinstance(value, dict) or loaded.raw != canonical_json_line(value):
        raise SafeReadError("{} is not canonical regular JSON".format(label))
    return loaded, value


def legacy_execute_run_block(python_executable: Path) -> str:
    return "\n".join((
        "function execute_run {",
        "    if [[ -f driver.log ]]; then",
        '        echo "The run in $(pwd) has already been started --> skip it"',
        "        return",
        "    fi",
        "",
        "    (",
        '    "{}" run'.format(Path(python_executable)),
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


def hardened_execute_run_block(
    python_executable: Path, helper: Path, dynamic_names
) -> str:
    command = [
        os.fspath(python_executable), os.fspath(helper),
        "--python", os.fspath(python_executable),
        "--run-script", "run", "--stdout", "driver.log",
        "--stderr", "driver.err",
    ]
    for name in sorted(dynamic_names):
        command.extend(("--dynamic", name))
    rendered = " ".join(shlex.quote(value) for value in command)
    return "\n".join((
        "function execute_run {",
        "    {}".format(rendered),
        "    HELPER_STATUS=$?",
        "    if [[ $HELPER_STATUS != 0 ]]; then",
        '        return "$HELPER_STATUS"',
        "    fi",
        "}",
    ))
