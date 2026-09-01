#!/usr/bin/env python3
"""Descriptor-relative, no-follow reads for source-audit campaign v5.

The evidence producer must never validate one pathname and then consume a
different object through a second pathname lookup.  This module therefore
keeps every ancestor descriptor open, reads and hashes the leaf through one
descriptor, and revalidates the complete descriptor chain after the read.
"""

from __future__ import annotations

import hashlib
import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class SafeReadError(RuntimeError):
    pass


@dataclass(frozen=True)
class RegularFile:
    raw: bytes
    sha256: str
    identity: dict[str, int]


@dataclass(frozen=True)
class Directory:
    entries: tuple[str, ...]
    identity: dict[str, int]


@dataclass(frozen=True)
class TreeFile:
    path: str
    raw: bytes
    sha256: str
    identity: dict[str, int]


@dataclass(frozen=True)
class RegularTree:
    files: tuple[TreeFile, ...]
    directories: tuple[str, ...]
    root_identity: dict[str, int]


ReadCallback = Callable[[Path, int], None]


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
        "nlink": info.st_nlink,
        "uid": info.st_uid,
        "gid": info.st_gid,
        "size": info.st_size,
        "mtime_ns": info.st_mtime_ns,
        "ctime_ns": info.st_ctime_ns,
    }


def validate_lexical_path(
    path: Path,
    *,
    label: str,
    expected_path: Path | None = None,
    root: Path | None = None,
) -> Path:
    """Return the canonical lexical target without dereferencing it.

    An absolute ``root`` makes a relative ``path`` root-relative.  Absolute
    roots and targets are later walked from ``/`` so no component above the
    declared boundary escapes no-follow validation.
    """
    raw_path = os.fspath(path)
    if not isinstance(raw_path, str) or not raw_path:
        raise SafeReadError("{} path is invalid".format(label))
    candidate = Path(raw_path)
    if (
        ".." in candidate.parts
        or raw_path != os.path.normpath(raw_path)
    ):
        raise SafeReadError("{} path is not lexical".format(label))
    root_path = None
    if root is not None:
        raw_root = os.fspath(root)
        root_path = Path(raw_root)
        if (
            not isinstance(raw_root, str)
            or not raw_root
            or not root_path.is_absolute()
            or ".." in root_path.parts
            or raw_root != os.path.normpath(raw_root)
        ):
            raise SafeReadError("{} root is not canonical absolute".format(label))
        target = candidate if candidate.is_absolute() else root_path / candidate
        try:
            target.relative_to(root_path)
        except ValueError as err:
            raise SafeReadError("{} path escapes its root".format(label)) from err
    else:
        target = candidate
    if expected_path is not None:
        raw_expected = os.fspath(expected_path)
        expected = Path(raw_expected)
        if (
            not isinstance(raw_expected, str)
            or not raw_expected
            or ".." in expected.parts
            or raw_expected != os.path.normpath(raw_expected)
        ):
            raise SafeReadError("{} expected path is not lexical".format(label))
        if root_path is not None and not expected.is_absolute():
            expected = root_path / expected
        if os.fspath(target) != os.fspath(expected):
            raise SafeReadError("{} path changed".format(label))
    return target


def _anchor_and_parts(
    candidate: Path, root: Path | None, label: str
) -> tuple[Path, tuple[str, ...]]:
    del root, label
    if candidate.is_absolute():
        anchor = Path(candidate.anchor)
        relative = candidate.relative_to(anchor)
    else:
        anchor = Path(".")
        relative = candidate
    return anchor, relative.parts


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _check_chain(
    *,
    anchor: Path,
    anchor_fd: int,
    anchor_fingerprint: tuple[int, ...],
    ancestors: list[tuple[int, str, tuple[int, ...], int]],
    label: str,
) -> None:
    for parent_fd, component, fingerprint, child_fd in reversed(ancestors):
        entry = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(child_fd)
        if (
            not stat.S_ISDIR(entry.st_mode)
            or _fingerprint(entry) != fingerprint
            or _fingerprint(opened) != fingerprint
        ):
            raise SafeReadError("{} ancestor changed while reading".format(label))
    if (
        _fingerprint(os.fstat(anchor_fd)) != anchor_fingerprint
        or _fingerprint(os.lstat(anchor)) != anchor_fingerprint
    ):
        raise SafeReadError("{} root changed while reading".format(label))


def _open_anchor(
    anchor: Path, label: str, descriptors: list[int]
) -> tuple[int, tuple[int, ...]]:
    before = os.lstat(anchor)
    if not stat.S_ISDIR(before.st_mode):
        raise SafeReadError("{} root is not a directory".format(label))
    descriptor = os.open(anchor, _directory_flags())
    descriptors.append(descriptor)
    opened = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(opened.st_mode)
        or _fingerprint(opened) != _fingerprint(before)
    ):
        raise SafeReadError("{} root identity changed".format(label))
    return descriptor, _fingerprint(opened)


def _walk_directories(
    parent_fd: int,
    components: tuple[str, ...],
    descriptors: list[int],
    label: str,
) -> tuple[int, list[tuple[int, str, tuple[int, ...], int]]]:
    ancestors = []
    for component in components:
        before = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISDIR(before.st_mode):
            raise SafeReadError("{} ancestor is not a directory".format(label))
        child_fd = os.open(component, _directory_flags(), dir_fd=parent_fd)
        descriptors.append(child_fd)
        opened = os.fstat(child_fd)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _fingerprint(opened) != _fingerprint(before)
        ):
            raise SafeReadError("{} ancestor identity changed".format(label))
        ancestors.append((parent_fd, component, _fingerprint(opened), child_fd))
        parent_fd = child_fd
    return parent_fd, ancestors


def read_regular_file(
    path: Path,
    *,
    label: str,
    expected_path: Path | None = None,
    root: Path | None = None,
    read_callback: ReadCallback | None = None,
) -> RegularFile:
    """Read and hash a regular file through one stable descriptor chain.

    ``read_callback`` is solely a deterministic race-test hook.  Production
    callers leave it unset.  It runs after the verified leaf descriptor is
    open and before the first byte is read; all resulting mutations must be
    caught by the post-read descriptor and pathname checks.
    """
    candidate = validate_lexical_path(
        path, label=label, expected_path=expected_path, root=root
    )
    anchor, parts = _anchor_and_parts(candidate, root, label)
    if not parts:
        raise SafeReadError("{} is not a regular file".format(label))

    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptors: list[int] = []
    try:
        anchor_fd, anchor_fingerprint = _open_anchor(
            anchor, label, descriptors
        )
        parent_fd, ancestors = _walk_directories(
            anchor_fd, parts[:-1], descriptors, label
        )
        leaf = parts[-1]
        before = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise SafeReadError("{} is not a regular file".format(label))
        descriptor = os.open(leaf, file_flags, dir_fd=parent_fd)
        descriptors.append(descriptor)
        opened = os.fstat(descriptor)
        opened_fingerprint = _fingerprint(opened)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened_fingerprint != _fingerprint(before)
        ):
            raise SafeReadError("{} identity changed before reading".format(label))

        if read_callback is not None:
            read_callback(candidate, descriptor)
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
            or _fingerprint(after_fd) != opened_fingerprint
            or _fingerprint(after_leaf) != opened_fingerprint
        ):
            raise SafeReadError("{} identity changed while reading".format(label))
        _check_chain(
            anchor=anchor,
            anchor_fd=anchor_fd,
            anchor_fingerprint=anchor_fingerprint,
            ancestors=ancestors,
            label=label,
        )
        return RegularFile(
            b"".join(blocks), digest.hexdigest(), _identity(after_fd)
        )
    except SafeReadError:
        raise
    except OSError as err:
        raise SafeReadError("cannot read {} safely".format(label)) from err
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def read_canonical_json(
    path: Path,
    *,
    label: str,
    canonical_json_line,
    expected_path: Path | None = None,
    root: Path | None = None,
    read_callback: ReadCallback | None = None,
) -> tuple[RegularFile, dict]:
    loaded = read_regular_file(
        path,
        label=label,
        expected_path=expected_path,
        root=root,
        read_callback=read_callback,
    )
    try:
        value = json.loads(loaded.raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SafeReadError("cannot decode {}".format(label)) from err
    if not isinstance(value, dict) or loaded.raw != canonical_json_line(value):
        raise SafeReadError("{} is not canonical regular JSON".format(label))
    return loaded, value


def inspect_directory(
    path: Path,
    *,
    label: str,
    expected_path: Path | None = None,
    root: Path | None = None,
) -> Directory:
    """List one directory through a verified no-follow descriptor chain."""
    candidate = validate_lexical_path(
        path, label=label, expected_path=expected_path, root=root
    )
    anchor, parts = _anchor_and_parts(candidate, root, label)
    descriptors: list[int] = []
    try:
        anchor_fd, anchor_fingerprint = _open_anchor(
            anchor, label, descriptors
        )
        directory_fd, ancestors = _walk_directories(
            anchor_fd, parts, descriptors, label
        )
        opened = os.fstat(directory_fd)
        opened_fingerprint = _fingerprint(opened)
        entries = os.listdir(directory_fd)
        if any(
            not isinstance(entry, str)
            or not entry
            or entry in (".", "..")
            or "/" in entry
            for entry in entries
        ):
            raise SafeReadError("{} contains an invalid name".format(label))
        if _fingerprint(os.fstat(directory_fd)) != opened_fingerprint:
            raise SafeReadError("{} changed while listing".format(label))
        _check_chain(
            anchor=anchor,
            anchor_fd=anchor_fd,
            anchor_fingerprint=anchor_fingerprint,
            ancestors=ancestors,
            label=label,
        )
        return Directory(tuple(sorted(entries)), _identity(opened))
    except SafeReadError:
        raise
    except OSError as err:
        raise SafeReadError("cannot inspect {} safely".format(label)) from err
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def read_regular_tree(
    path: Path,
    *,
    label: str,
    expected_path: Path | None = None,
    root: Path | None = None,
    read_callback: ReadCallback | None = None,
) -> RegularTree:
    """Read a regular-file tree while retaining every directory descriptor.

    Each directory is listed twice through the same descriptor. Every leaf is
    opened descriptor-relative, read and hashed, then reopened and rehashed
    after the complete traversal. Full file/directory fingerprints, entry
    sets, and the absolute ancestor chain must remain unchanged throughout.
    """
    candidate = validate_lexical_path(
        path, label=label, expected_path=expected_path, root=root
    )
    anchor, parts = _anchor_and_parts(candidate, root, label)
    if not parts:
        raise SafeReadError("{} is not a directory tree".format(label))
    file_flags = (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    descriptors: list[int] = []
    directory_records = []
    file_records = []

    def read_leaf(parent_fd: int, name: str):
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise SafeReadError("{} contains a non-regular entry".format(label))
        descriptor = os.open(name, file_flags, dir_fd=parent_fd)
        try:
            opened = os.fstat(descriptor)
            fingerprint = _fingerprint(opened)
            if fingerprint != _fingerprint(before):
                raise SafeReadError("{} leaf changed before reading".format(label))
            blocks = []
            digest = hashlib.sha256()
            while True:
                block = os.read(descriptor, 1024 * 1024)
                if not block:
                    break
                blocks.append(block)
                digest.update(block)
            after_fd = os.fstat(descriptor)
            after_path = os.stat(
                name, dir_fd=parent_fd, follow_symlinks=False
            )
            if (
                _fingerprint(after_fd) != fingerprint
                or _fingerprint(after_path) != fingerprint
            ):
                raise SafeReadError("{} leaf changed while reading".format(label))
            return b"".join(blocks), digest.hexdigest(), opened, fingerprint
        finally:
            os.close(descriptor)

    def enumerate_directory(directory_fd: int, relative: Path) -> None:
        opened = os.fstat(directory_fd)
        fingerprint = _fingerprint(opened)
        names = tuple(sorted(os.listdir(directory_fd)))
        if any(
            not isinstance(name, str)
            or not name
            or name in (".", "..")
            or "/" in name
            for name in names
        ):
            raise SafeReadError("{} contains an invalid name".format(label))
        record = {
            "fd": directory_fd,
            "relative": relative,
            "fingerprint": fingerprint,
            "names": names,
        }
        directory_records.append(record)
        for name in names:
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            child_relative = relative / name
            if stat.S_ISDIR(info.st_mode):
                child_fd = os.open(
                    name, _directory_flags(), dir_fd=directory_fd
                )
                descriptors.append(child_fd)
                opened_child = os.fstat(child_fd)
                if _fingerprint(opened_child) != _fingerprint(info):
                    raise SafeReadError(
                        "{} directory changed before reading".format(label)
                    )
                record.setdefault("children", []).append(
                    (name, child_fd, _fingerprint(opened_child))
                )
                enumerate_directory(child_fd, child_relative)
            elif stat.S_ISREG(info.st_mode):
                raw, sha256, opened_file, fingerprint_file = read_leaf(
                    directory_fd, name
                )
                if fingerprint_file != _fingerprint(info):
                    raise SafeReadError(
                        "{} leaf changed during enumeration".format(label)
                    )
                file_records.append({
                    "parent_fd": directory_fd,
                    "name": name,
                    "relative": child_relative,
                    "raw": raw,
                    "sha256": sha256,
                    "identity": _identity(opened_file),
                    "fingerprint": fingerprint_file,
                })
            else:
                raise SafeReadError("{} contains a special file".format(label))

    try:
        anchor_fd, anchor_fingerprint = _open_anchor(
            anchor, label, descriptors
        )
        tree_fd, ancestors = _walk_directories(
            anchor_fd, parts, descriptors, label
        )
        tree_fingerprint = _fingerprint(os.fstat(tree_fd))
        enumerate_directory(tree_fd, Path("."))
        if read_callback is not None:
            read_callback(candidate, tree_fd)

        for record in file_records:
            raw, sha256, _opened, fingerprint = read_leaf(
                record["parent_fd"], record["name"]
            )
            if (
                fingerprint != record["fingerprint"]
                or len(raw) != len(record["raw"])
                or sha256 != record["sha256"]
            ):
                raise SafeReadError("{} leaf changed after reading".format(label))
        for record in reversed(directory_records):
            if (
                _fingerprint(os.fstat(record["fd"])) != record["fingerprint"]
                or tuple(sorted(os.listdir(record["fd"]))) != record["names"]
            ):
                raise SafeReadError(
                    "{} directory changed while reading".format(label)
                )
            for name, child_fd, fingerprint in record.get("children", []):
                child_path = os.stat(
                    name, dir_fd=record["fd"], follow_symlinks=False
                )
                if (
                    _fingerprint(os.fstat(child_fd)) != fingerprint
                    or _fingerprint(child_path) != fingerprint
                ):
                    raise SafeReadError(
                        "{} directory entry changed while reading".format(label)
                    )
        if _fingerprint(os.fstat(tree_fd)) != tree_fingerprint:
            raise SafeReadError("{} root changed while reading".format(label))
        _check_chain(
            anchor=anchor,
            anchor_fd=anchor_fd,
            anchor_fingerprint=anchor_fingerprint,
            ancestors=ancestors,
            label=label,
        )
        files = tuple(sorted(
            (
                TreeFile(
                    record["relative"].as_posix(),
                    record["raw"],
                    record["sha256"],
                    record["identity"],
                )
                for record in file_records
            ),
            key=lambda item: item.path,
        ))
        directories = tuple(sorted(
            record["relative"].as_posix()
            for record in directory_records
            if record["relative"] != Path(".")
        ))
        return RegularTree(files, directories, _identity(os.fstat(tree_fd)))
    except SafeReadError:
        raise
    except OSError as err:
        raise SafeReadError("cannot read {} tree safely".format(label)) from err
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
