#!/usr/bin/env python3
"""Exclusive retained-descriptor capture files for V8 controller output."""

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path

import pdb_terminal_incidence_confirmation_safe_io_v7 as V7


PublicationError = V7.PublicationError
SelectedTreeError = V7.SelectedTreeError
SelectedFile = V7.SelectedFile
SelectedFlatTree = V7.SelectedFlatTree
atomic_exclusive_bytes = V7.atomic_exclusive_bytes
create_private_directory = V7.create_private_directory
read_selected_flat_tree = V7.read_selected_flat_tree
CHUNK_BYTES = V7.CHUNK_BYTES


def _capture_identity(
    path: Path, info: os.stat_result, *, size_key: str = "bytes"
) -> dict:
    return {
        "path": str(path),
        "canonical_path": str(path),
        "device": info.st_dev,
        "inode": info.st_ino,
        "mode": "{:04o}".format(stat.S_IMODE(info.st_mode)),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "link_count": info.st_nlink,
        size_key: info.st_size,
    }


def _same_inode(info: os.stat_result, expected: dict) -> bool:
    return (
        stat.S_ISREG(info.st_mode)
        and info.st_dev == expected.get("device")
        and info.st_ino == expected.get("inode")
        and info.st_uid == expected.get("uid")
        and info.st_gid == expected.get("gid")
        and info.st_nlink == expected.get("link_count")
    )


@dataclass
class ExclusiveCapturePair:
    paths: dict[str, Path]
    descriptors: list[int]
    relations: list[tuple[int, str, int, tuple[int, ...]]]
    leaf_fds: dict[str, int]
    initial_identities: dict[str, dict]
    label: str
    _closed: bool = False
    _finalized: bool = False

    @property
    def stdout_fd(self) -> int:
        return self.leaf_fds["stdout"]

    @property
    def stderr_fd(self) -> int:
        return self.leaf_fds["stderr"]

    def _check_leaf(self, stream: str, *, allowed_modes: tuple[int, ...]) -> os.stat_result:
        if self._closed:
            raise PublicationError(self.label + " capture descriptors are closed")
        parent_fd = self.descriptors[-1]
        path = self.paths[stream]
        expected = self.initial_identities[stream]
        fd_info = os.fstat(self.leaf_fds[stream])
        entry = os.stat(path.name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            not _same_inode(fd_info, expected)
            or not _same_inode(entry, expected)
            or V7._stable_file_identity(fd_info)
            != V7._stable_file_identity(entry)
            or stat.S_IMODE(fd_info.st_mode) not in allowed_modes
            or stat.S_IMODE(entry.st_mode) not in allowed_modes
        ):
            raise PublicationError(self.label + " " + stream + " identity changed")
        return fd_info

    def verify_initial(self) -> None:
        V7._check_directory_chain(self.descriptors, self.relations, self.label)
        for stream in ("stdout", "stderr"):
            info = self._check_leaf(stream, allowed_modes=(0o400,))
            if info.st_size != 0 or _capture_identity(
                self.paths[stream], info, size_key="bytes_at_intent"
            ) != self.initial_identities[stream]:
                raise PublicationError(
                    self.label + " " + stream + " was not initially empty"
                )

    def finalize(self) -> tuple[dict[str, dict], dict[str, bytes]]:
        """Fsync and read both sealed retained files without a pathname reopen."""
        records: dict[str, dict] = {}
        payloads: dict[str, bytes] = {}
        V7._check_directory_chain(self.descriptors, self.relations, self.label)
        for stream in ("stdout", "stderr"):
            descriptor = self.leaf_fds[stream]
            os.fsync(descriptor)
            before = self._check_leaf(stream, allowed_modes=(0o400,))
            os.lseek(descriptor, 0, os.SEEK_SET)
            chunks = []
            digest = hashlib.sha256()
            count = 0
            while True:
                block = os.read(descriptor, CHUNK_BYTES)
                if not block:
                    break
                chunks.append(block)
                digest.update(block)
                count += len(block)
            after_fd = os.fstat(descriptor)
            after_path = os.stat(
                self.paths[stream].name,
                dir_fd=self.descriptors[-1],
                follow_symlinks=False,
            )
            if (
                count != before.st_size
                or V7._stable_file_identity(after_fd)
                != V7._stable_file_identity(before)
                or V7._stable_file_identity(after_path)
                != V7._stable_file_identity(before)
            ):
                raise PublicationError(
                    self.label + " " + stream + " changed while reading"
                )
            final_info = self._check_leaf(stream, allowed_modes=(0o400,))
            raw = b"".join(chunks)
            identity = _capture_identity(self.paths[stream], final_info)
            if identity["bytes"] != len(raw):
                raise PublicationError(
                    self.label + " " + stream + " final size changed"
                )
            records[stream] = {
                "path": str(self.paths[stream]),
                "bytes": len(raw),
                "sha256": digest.hexdigest(),
                "initial_identity": self.initial_identities[stream],
                "final_identity": identity,
            }
            payloads[stream] = raw
        os.fsync(self.descriptors[-1])
        V7._check_directory_chain(self.descriptors, self.relations, self.label)
        for stream in ("stdout", "stderr"):
            final_info = self._check_leaf(stream, allowed_modes=(0o400,))
            if _capture_identity(
                self.paths[stream], final_info
            ) != records[stream]["final_identity"]:
                raise PublicationError(
                    self.label + " " + stream + " changed after capture read"
                )
        self._finalized = True
        return records, payloads

    def close(self) -> None:
        if self._closed:
            return
        for descriptor in self.leaf_fds.values():
            os.close(descriptor)
        for descriptor in reversed(self.descriptors):
            os.close(descriptor)
        self._closed = True

    def __enter__(self) -> "ExclusiveCapturePair":
        return self

    def __exit__(self, _type, _value, _traceback) -> None:
        self.close()


def _paths(stdout_path: Path, stderr_path: Path, root: Path, label: str):
    paths = {
        "stdout": V7._lexical_descendant(Path(stdout_path), Path(root), label),
        "stderr": V7._lexical_descendant(Path(stderr_path), Path(root), label),
    }
    if (
        paths["stdout"].parent != paths["stderr"].parent
        or paths["stdout"].name == paths["stderr"].name
        or not paths["stdout"].name
        or not paths["stderr"].name
    ):
        raise PublicationError(label + " capture paths are invalid")
    return paths


def open_exclusive_capture_pair(
    stdout_path: Path, stderr_path: Path, *, root: Path, label: str
) -> ExclusiveCapturePair:
    """Create two sealed leaves and retain their writable open descriptions.

    Each leaf is opened O_RDWR|O_EXCL and immediately made 0400.  The retained
    open file description remains writable by the eventual child redirection,
    while no new writer can open the pathname under the stated same-UID threat
    model.  Both leaf descriptors and the complete no-follow ancestor chain
    remain live until the returned pair is closed.
    """
    paths = _paths(stdout_path, stderr_path, root, label)
    descriptors: list[int] = []
    relations: list[tuple[int, str, int, tuple[int, ...]]] = []
    leaf_fds: dict[str, int] = {}
    initial: dict[str, dict] = {}
    created: list[str] = []
    try:
        descriptors, relations = V7._open_directory_chain(
            paths["stdout"].parent,
            root=Path(root),
            label=label,
            create_missing=True,
        )
        parent_fd = descriptors[-1]
        V7._check_directory_chain(descriptors, relations, label)
        flags = (
            os.O_RDWR | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        for stream in ("stdout", "stderr"):
            name = paths[stream].name
            try:
                descriptor = os.open(name, flags, 0o600, dir_fd=parent_fd)
            except FileExistsError as err:
                raise PublicationError(
                    "refusing to reuse " + label + " " + stream
                ) from err
            leaf_fds[stream] = descriptor
            created.append(stream)
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            os.fchmod(descriptor, 0o400)
            os.fsync(descriptor)
            info = os.fstat(descriptor)
            entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            identity = _capture_identity(
                paths[stream], info, size_key="bytes_at_intent"
            )
            if (
                not stat.S_ISREG(info.st_mode)
                or stat.S_IMODE(info.st_mode) != 0o400
                or info.st_uid != os.getuid()
                or info.st_nlink != 1
                or info.st_size != 0
                or V7._stable_file_identity(info)
                != V7._stable_file_identity(entry)
            ):
                raise PublicationError(label + " " + stream + " creation changed")
            initial[stream] = identity
        os.fsync(parent_fd)
        V7._check_directory_chain(descriptors, relations, label)
        pair = ExclusiveCapturePair(
            paths, descriptors, relations, leaf_fds, initial, label
        )
        pair.verify_initial()
        return pair
    except Exception as err:
        if descriptors:
            parent_fd = descriptors[-1]
            for stream in reversed(created):
                descriptor = leaf_fds.get(stream)
                expected = initial.get(stream)
                try:
                    if descriptor is not None:
                        info = os.fstat(descriptor)
                        if expected is None:
                            expected = _capture_identity(
                                paths[stream], info,
                                size_key="bytes_at_intent",
                            )
                        current = os.stat(
                            paths[stream].name,
                            dir_fd=parent_fd,
                            follow_symlinks=False,
                        )
                        if _same_inode(current, expected):
                            os.unlink(paths[stream].name, dir_fd=parent_fd)
                except OSError:
                    pass
        for descriptor in leaf_fds.values():
            os.close(descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        if isinstance(err, PublicationError):
            raise
        if isinstance(err, OSError):
            raise PublicationError(label + " capture creation failed") from err
        raise


def open_existing_capture_pair(
    stdout_path: Path,
    stderr_path: Path,
    expected_initial: dict[str, dict],
    *,
    root: Path,
    label: str,
) -> ExclusiveCapturePair:
    """Reopen a crash-left pair while verifying intent-bound inode identity."""
    paths = _paths(stdout_path, stderr_path, root, label)
    if (
        not isinstance(expected_initial, dict)
        or set(expected_initial) != {"stdout", "stderr"}
    ):
        raise PublicationError(label + " expected identities are invalid")
    descriptors: list[int] = []
    relations: list[tuple[int, str, int, tuple[int, ...]]] = []
    leaf_fds: dict[str, int] = {}
    try:
        descriptors, relations = V7._open_directory_chain(
            paths["stdout"].parent,
            root=Path(root),
            label=label,
            create_missing=False,
        )
        parent_fd = descriptors[-1]
        V7._check_directory_chain(descriptors, relations, label)
        for stream in ("stdout", "stderr"):
            expected = expected_initial[stream]
            if (
                not isinstance(expected, dict)
                or expected.get("path") != str(paths[stream])
                or expected.get("canonical_path") != str(paths[stream])
                or expected.get("mode") != "0400"
                or expected.get("link_count") != 1
                or expected.get("bytes_at_intent") != 0
            ):
                raise PublicationError(label + " intent identity changed")
            before = os.stat(
                paths[stream].name, dir_fd=parent_fd, follow_symlinks=False
            )
            if not _same_inode(before, expected):
                raise PublicationError(label + " " + stream + " identity changed")
            mode = stat.S_IMODE(before.st_mode)
            if mode != 0o400:
                raise PublicationError(label + " " + stream + " mode changed")
            flags = (
                os.O_RDONLY
                | getattr(os, "O_CLOEXEC", 0)
                | getattr(os, "O_NOFOLLOW", 0)
            )
            descriptor = os.open(
                paths[stream].name, flags, dir_fd=parent_fd
            )
            leaf_fds[stream] = descriptor
            opened = os.fstat(descriptor)
            if (
                not _same_inode(opened, expected)
                or V7._stable_file_identity(opened)
                != V7._stable_file_identity(before)
            ):
                raise PublicationError(label + " " + stream + " changed")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as err:
                raise PublicationError(
                    label + " " + stream + " still has a retained writer"
                ) from err
            opened_after_lock = os.fstat(descriptor)
            path_after_lock = os.stat(
                paths[stream].name,
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            if (
                V7._stable_file_identity(opened_after_lock)
                != V7._stable_file_identity(opened)
                or V7._stable_file_identity(path_after_lock)
                != V7._stable_file_identity(opened)
            ):
                raise PublicationError(label + " " + stream + " changed")
        return ExclusiveCapturePair(
            paths, descriptors, relations, leaf_fds,
            expected_initial, label,
        )
    except Exception as err:
        for descriptor in leaf_fds.values():
            os.close(descriptor)
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        if isinstance(err, PublicationError):
            raise
        if isinstance(err, OSError):
            raise PublicationError(label + " capture reopen failed") from err
        raise
