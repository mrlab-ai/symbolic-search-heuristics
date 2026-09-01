#!/usr/bin/env python3
"""Bounded-memory, descriptor-relative tree hashing for campaign V6."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


class SafeTreeError(RuntimeError):
    pass


CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class TreeFile:
    path: str
    sha256: str
    identity: dict[str, int]


@dataclass(frozen=True)
class StreamingTree:
    files: tuple[TreeFile, ...]
    directories: tuple[str, ...]
    root_identity: dict[str, int]


ReadCallback = Callable[[Path, int], None]
ChunkCallback = Callable[[str, int], None]


def _fingerprint(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
        info.st_uid, info.st_gid, info.st_size,
        info.st_mtime_ns, info.st_ctime_ns,
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


def _lexical_target(
    path: Path,
    *,
    label: str,
    expected_path: Path | None,
    root: Path | None,
) -> Path:
    raw = os.fspath(path)
    if (
        not isinstance(raw, str)
        or not raw
        or ".." in Path(raw).parts
        or raw != os.path.normpath(raw)
    ):
        raise SafeTreeError("{} path is not lexical".format(label))
    candidate = Path(raw)
    root_path = None
    if root is not None:
        root_raw = os.fspath(root)
        root_path = Path(root_raw)
        if (
            not isinstance(root_raw, str)
            or not root_raw
            or not root_path.is_absolute()
            or ".." in root_path.parts
            or root_raw != os.path.normpath(root_raw)
        ):
            raise SafeTreeError("{} root is not canonical absolute".format(label))
        candidate = candidate if candidate.is_absolute() else root_path / candidate
        try:
            candidate.relative_to(root_path)
        except ValueError as err:
            raise SafeTreeError("{} path escapes its root".format(label)) from err
    if expected_path is not None:
        expected_raw = os.fspath(expected_path)
        expected = Path(expected_raw)
        if (
            not isinstance(expected_raw, str)
            or not expected_raw
            or ".." in expected.parts
            or expected_raw != os.path.normpath(expected_raw)
        ):
            raise SafeTreeError("{} expected path is not lexical".format(label))
        if root_path is not None and not expected.is_absolute():
            expected = root_path / expected
        if os.fspath(candidate) != os.fspath(expected):
            raise SafeTreeError("{} path changed".format(label))
    return candidate


def _anchor_parts(candidate: Path) -> tuple[Path, tuple[str, ...]]:
    if candidate.is_absolute():
        anchor = Path(candidate.anchor)
        return anchor, candidate.relative_to(anchor).parts
    return Path("."), candidate.parts


def _directory_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )


def _file_flags() -> int:
    return (
        os.O_RDONLY
        | getattr(os, "O_CLOEXEC", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )


def _open_anchor(
    anchor: Path, label: str, descriptors: list[int]
) -> tuple[int, tuple[int, ...]]:
    before = os.lstat(anchor)
    if not stat.S_ISDIR(before.st_mode):
        raise SafeTreeError("{} root is not a directory".format(label))
    descriptor = os.open(anchor, _directory_flags())
    descriptors.append(descriptor)
    opened = os.fstat(descriptor)
    if _fingerprint(opened) != _fingerprint(before):
        raise SafeTreeError("{} root identity changed".format(label))
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
            raise SafeTreeError("{} ancestor is not a directory".format(label))
        child_fd = os.open(component, _directory_flags(), dir_fd=parent_fd)
        descriptors.append(child_fd)
        opened = os.fstat(child_fd)
        if _fingerprint(opened) != _fingerprint(before):
            raise SafeTreeError("{} ancestor identity changed".format(label))
        ancestors.append((parent_fd, component, _fingerprint(opened), child_fd))
        parent_fd = child_fd
    return parent_fd, ancestors


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
        if (
            not stat.S_ISDIR(entry.st_mode)
            or _fingerprint(entry) != fingerprint
            or _fingerprint(os.fstat(child_fd)) != fingerprint
        ):
            raise SafeTreeError("{} ancestor changed while reading".format(label))
    if (
        _fingerprint(os.fstat(anchor_fd)) != anchor_fingerprint
        or _fingerprint(os.lstat(anchor)) != anchor_fingerprint
    ):
        raise SafeTreeError("{} root changed while reading".format(label))


def read_streaming_tree(
    path: Path,
    *,
    label: str,
    expected_path: Path | None = None,
    root: Path | None = None,
    read_callback: ReadCallback | None = None,
    chunk_callback: ChunkCallback | None = None,
) -> StreamingTree:
    """Hash a stable regular-file tree without retaining file payloads."""
    candidate = _lexical_target(
        path, label=label, expected_path=expected_path, root=root
    )
    anchor, parts = _anchor_parts(candidate)
    if not parts:
        raise SafeTreeError("{} is not a directory tree".format(label))
    descriptors: list[int] = []
    directories = []
    files = []

    def hash_leaf(parent_fd: int, name: str, relative: str):
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode):
            raise SafeTreeError("{} contains a non-regular entry".format(label))
        descriptor = os.open(name, _file_flags(), dir_fd=parent_fd)
        try:
            opened = os.fstat(descriptor)
            fingerprint = _fingerprint(opened)
            if fingerprint != _fingerprint(before):
                raise SafeTreeError("{} leaf changed before reading".format(label))
            digest = hashlib.sha256()
            count = 0
            while True:
                block = os.read(descriptor, CHUNK_BYTES)
                if not block:
                    break
                count += len(block)
                digest.update(block)
                if chunk_callback is not None:
                    chunk_callback(relative, len(block))
            after_fd = os.fstat(descriptor)
            after_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                count != opened.st_size
                or _fingerprint(after_fd) != fingerprint
                or _fingerprint(after_path) != fingerprint
            ):
                raise SafeTreeError("{} leaf changed while reading".format(label))
            return digest.hexdigest(), opened, fingerprint
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
            raise SafeTreeError("{} contains an invalid name".format(label))
        record = {
            "fd": directory_fd,
            "relative": relative,
            "fingerprint": fingerprint,
            "names": names,
            "children": [],
        }
        directories.append(record)
        for name in names:
            info = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            child_relative = relative / name
            if stat.S_ISDIR(info.st_mode):
                child_fd = os.open(name, _directory_flags(), dir_fd=directory_fd)
                descriptors.append(child_fd)
                opened_child = os.fstat(child_fd)
                child_fingerprint = _fingerprint(opened_child)
                if child_fingerprint != _fingerprint(info):
                    raise SafeTreeError(
                        "{} directory changed before reading".format(label)
                    )
                record["children"].append((name, child_fd, child_fingerprint))
                enumerate_directory(child_fd, child_relative)
            elif stat.S_ISREG(info.st_mode):
                relative_name = child_relative.as_posix()
                sha256, opened_file, file_fingerprint = hash_leaf(
                    directory_fd, name, relative_name
                )
                if file_fingerprint != _fingerprint(info):
                    raise SafeTreeError(
                        "{} leaf changed during enumeration".format(label)
                    )
                files.append({
                    "parent_fd": directory_fd,
                    "name": name,
                    "path": relative_name,
                    "sha256": sha256,
                    "identity": _identity(opened_file),
                    "fingerprint": file_fingerprint,
                })
            else:
                raise SafeTreeError("{} contains a special file".format(label))

    try:
        anchor_fd, anchor_fingerprint = _open_anchor(anchor, label, descriptors)
        tree_fd, ancestors = _walk_directories(
            anchor_fd, parts, descriptors, label
        )
        tree_fingerprint = _fingerprint(os.fstat(tree_fd))
        enumerate_directory(tree_fd, Path("."))
        if read_callback is not None:
            read_callback(candidate, tree_fd)
        for record in files:
            sha256, _opened, fingerprint = hash_leaf(
                record["parent_fd"], record["name"], record["path"]
            )
            if (
                fingerprint != record["fingerprint"]
                or sha256 != record["sha256"]
            ):
                raise SafeTreeError("{} leaf changed after reading".format(label))
        # A leaf verified early in the second pass can still change while a
        # later leaf is being hashed. Re-stat every name only after all second
        # reads so no earlier leaf is left outside the final stability sweep.
        for record in files:
            current = os.stat(
                record["name"], dir_fd=record["parent_fd"],
                follow_symlinks=False,
            )
            if _fingerprint(current) != record["fingerprint"]:
                raise SafeTreeError("{} leaf changed after reading".format(label))
        for record in reversed(directories):
            if (
                _fingerprint(os.fstat(record["fd"])) != record["fingerprint"]
                or tuple(sorted(os.listdir(record["fd"]))) != record["names"]
            ):
                raise SafeTreeError("{} directory changed while reading".format(label))
            for name, child_fd, fingerprint in record["children"]:
                current = os.stat(
                    name, dir_fd=record["fd"], follow_symlinks=False
                )
                if (
                    _fingerprint(current) != fingerprint
                    or _fingerprint(os.fstat(child_fd)) != fingerprint
                ):
                    raise SafeTreeError(
                        "{} directory entry changed while reading".format(label)
                    )
        if _fingerprint(os.fstat(tree_fd)) != tree_fingerprint:
            raise SafeTreeError("{} root changed while reading".format(label))
        _check_chain(
            anchor=anchor,
            anchor_fd=anchor_fd,
            anchor_fingerprint=anchor_fingerprint,
            ancestors=ancestors,
            label=label,
        )
        return StreamingTree(
            tuple(TreeFile(
                record["path"], record["sha256"], record["identity"]
            ) for record in sorted(files, key=lambda item: item["path"])),
            tuple(sorted(
                record["relative"].as_posix()
                for record in directories
                if record["relative"] != Path(".")
            )),
            _identity(os.fstat(tree_fd)),
        )
    except SafeTreeError:
        raise
    except OSError as err:
        raise SafeTreeError("cannot read {} tree safely".format(label)) from err
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
