#!/usr/bin/env python3
"""Exact-path, race-resistant I/O for the terminal metric campaign."""

from __future__ import annotations

import os
import stat
import hashlib
from pathlib import Path

import pdb_confirmation_safe_io as SafeIO


class CampaignIOError(RuntimeError):
    pass


def _fingerprint(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
        info.st_uid, info.st_gid, info.st_size, info.st_mtime_ns,
        info.st_ctime_ns,
    )


def read_regular_exact(path: Path, *, expected: Path, label: str):
    try:
        return SafeIO.read_regular_file(
            Path(path), label=label, expected_path=Path(expected)
        )
    except SafeIO.SafeReadError as err:
        raise CampaignIOError(str(err)) from err


def read_canonical_exact(
    path: Path, *, expected: Path, label: str, canonical_json_line,
):
    try:
        return SafeIO.read_canonical_json(
            Path(path), label=label, expected_path=Path(expected),
            canonical_json_line=canonical_json_line,
        )
    except SafeIO.SafeReadError as err:
        raise CampaignIOError(str(err)) from err


def _open_directory(path: Path, *, label: str, root: Path | None = None) -> int:
    """Open a directory by walking every component with no-follow dirfds."""
    try:
        candidate = SafeIO.validate_lexical_path(
            path, label=label, root=root
        )
    except SafeIO.SafeReadError as err:
        raise CampaignIOError(str(err)) from err
    if root is not None:
        anchor = Path(root)
        try:
            components = candidate.relative_to(anchor).parts
        except ValueError as err:
            raise CampaignIOError("{} path escapes root".format(label)) from err
    elif candidate.is_absolute():
        anchor = Path(candidate.anchor)
        components = candidate.relative_to(anchor).parts
    else:
        anchor = Path(".")
        components = candidate.parts
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = None
    try:
        descriptor = os.open(anchor, flags)
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise CampaignIOError("{} root is not a directory".format(label))
        for component in components:
            child = os.open(component, flags, dir_fd=descriptor)
            info = os.fstat(child)
            if not stat.S_ISDIR(info.st_mode):
                os.close(child)
                raise CampaignIOError("{} ancestor is not a directory".format(label))
            os.close(descriptor)
            descriptor = child
    except OSError as err:
        if descriptor is not None:
            os.close(descriptor)
        raise CampaignIOError("cannot open {} directory safely".format(label)) from err
    return descriptor


def ensure_directory(path: Path, *, root: Path, label: str) -> None:
    """Create a lexical directory chain without following directory symlinks."""
    try:
        candidate = SafeIO.validate_lexical_path(
            Path(path), label=label, root=Path(root)
        )
    except SafeIO.SafeReadError as err:
        raise CampaignIOError(str(err)) from err
    root_path = Path(root)
    descriptor = _open_directory(root_path, label=label)
    try:
        relative = candidate.relative_to(root_path)
        for component in relative.parts:
            if component in ("", ".", ".."):
                raise CampaignIOError("{} directory spelling changed".format(label))
            try:
                os.mkdir(component, mode=0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            except OSError as err:
                raise CampaignIOError(
                    "cannot create {} directory safely".format(label)
                ) from err
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
            try:
                child = os.open(component, flags, dir_fd=descriptor)
                child_info = os.fstat(child)
            except OSError as err:
                raise CampaignIOError(
                    "cannot descend into {} directory safely".format(label)
                ) from err
            if not stat.S_ISDIR(child_info.st_mode):
                os.close(child)
                raise CampaignIOError("{} path contains a non-directory".format(label))
            os.close(descriptor)
            descriptor = child
    finally:
        os.close(descriptor)


def write_exclusive_exact(
    path: Path, raw: bytes, *, expected: Path, root: Path, label: str,
) -> None:
    """Create one exact regular file and verify its directory entry is stable."""
    try:
        candidate = SafeIO.validate_lexical_path(
            Path(path), label=label, expected_path=Path(expected), root=Path(root)
        )
    except SafeIO.SafeReadError as err:
        raise CampaignIOError(str(err)) from err
    if not isinstance(raw, bytes):
        raise CampaignIOError("{} payload is not bytes".format(label))
    ensure_directory(candidate.parent, root=Path(root), label=label)
    parent_fd = _open_directory(candidate.parent, label=label, root=root)
    descriptor = None
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(candidate.name, flags, 0o400, dir_fd=parent_fd)
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise CampaignIOError("{} output is not a private regular file".format(label))
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise CampaignIOError("cannot write {} completely".format(label))
            view = view[written:]
        os.fsync(descriptor)
        after_fd = os.fstat(descriptor)
        entry = os.stat(candidate.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(entry.st_mode)
            or after_fd.st_dev != opened.st_dev
            or after_fd.st_ino != opened.st_ino
            or after_fd.st_nlink != 1
            or after_fd.st_size != len(raw)
            or _fingerprint(after_fd) != _fingerprint(entry)
        ):
            raise CampaignIOError("{} output identity changed".format(label))
    except FileExistsError as err:
        raise CampaignIOError("{} already exists".format(label)) from err
    except OSError as err:
        raise CampaignIOError("cannot create {} safely".format(label)) from err
    finally:
        if descriptor is not None:
            os.close(descriptor)
        os.close(parent_fd)
    try:
        verified = SafeIO.read_regular_file(
            candidate, label=label, expected_path=expected, root=root
        )
    except SafeIO.SafeReadError as err:
        raise CampaignIOError("{} output path changed".format(label)) from err
    if verified.sha256 != hashlib.sha256(raw).hexdigest():
        raise CampaignIOError("{} output bytes changed".format(label))


def write_canonical_exclusive(
    path: Path, value: dict, *, expected: Path, root: Path, label: str,
    canonical_json_line,
) -> bytes:
    raw = canonical_json_line(value)
    write_exclusive_exact(
        path, raw, expected=expected, root=root, label=label
    )
    return raw
