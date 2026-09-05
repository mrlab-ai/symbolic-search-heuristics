#!/usr/bin/env python3
"""Descriptor-relative streaming reads of an exact selected flat file set.

Unlike the complete-tree V6 reader, this V7 reader never opens an unselected
leaf.  It is used for scheduler-reusable V5 triplets after the V7 success gate,
so noncompleted V5 shards, environments, and logs remain unread.
"""

from __future__ import annotations

import hashlib
import os
import secrets
import stat
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import pdb_terminal_incidence_confirmation_safe_io_v6 as Base


class SelectedTreeError(RuntimeError):
    pass


class PublicationError(RuntimeError):
    pass


CHUNK_BYTES = Base.CHUNK_BYTES


@dataclass(frozen=True)
class SelectedFile:
    path: str
    sha256: str
    identity: dict[str, int]


@dataclass(frozen=True)
class SelectedFlatTree:
    files: tuple[SelectedFile, ...]
    root_identity: dict[str, int]


SelectedReader = Callable[[str], bytes]
ReadCallback = Callable[[SelectedReader], None]


def _stable_identity(info: os.stat_result) -> tuple[int, ...]:
    """Identity fields that an expected publication changes do not modify."""
    return (
        info.st_dev, info.st_ino, info.st_mode,
        info.st_uid, info.st_gid,
    )


def _stable_file_identity(info: os.stat_result) -> tuple[int, ...]:
    return _stable_identity(info) + (info.st_size,)


def _lexical_descendant(
    path: Path, root: Path, label: str, *, allow_root: bool = False
) -> Path:
    raw = os.fspath(path)
    root_raw = os.fspath(root)
    candidate = Path(raw)
    root_path = Path(root_raw)
    if (
        not isinstance(raw, str)
        or not raw
        or not candidate.is_absolute()
        or ".." in candidate.parts
        or raw != os.path.normpath(raw)
        or not isinstance(root_raw, str)
        or not root_raw
        or not root_path.is_absolute()
        or ".." in root_path.parts
        or root_raw != os.path.normpath(root_raw)
    ):
        raise PublicationError("{} path is not canonical absolute".format(label))
    try:
        relative = candidate.relative_to(root_path)
    except ValueError as err:
        raise PublicationError("{} path escapes its root".format(label)) from err
    if not relative.parts and not allow_root:
        raise PublicationError("{} path is not below its root".format(label))
    return candidate


def _strictly_below(path: Path, root: Path) -> bool:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return False
    return bool(relative.parts)


def _open_directory_chain(
    directory: Path,
    *,
    root: Path,
    label: str,
    create_missing: bool,
) -> tuple[list[int], list[tuple[int, str, int, tuple[int, ...]]]]:
    """Open an absolute directory chain without following a path component."""
    _lexical_descendant(directory, root, label, allow_root=True)
    anchor = Path(directory.anchor)
    descriptors: list[int] = []
    relations: list[tuple[int, str, int, tuple[int, ...]]] = []
    try:
        anchor_before = os.lstat(anchor)
        if not stat.S_ISDIR(anchor_before.st_mode):
            raise PublicationError("{} anchor is not a directory".format(label))
        current_fd = os.open(anchor, Base._directory_flags())
        descriptors.append(current_fd)
        if _stable_identity(os.fstat(current_fd)) != _stable_identity(
            anchor_before
        ):
            raise PublicationError("{} anchor changed".format(label))
        current_path = anchor
        for component in directory.relative_to(anchor).parts:
            next_path = current_path / component
            created = False
            try:
                before = os.stat(
                    component, dir_fd=current_fd, follow_symlinks=False
                )
            except FileNotFoundError:
                if not create_missing or not _strictly_below(next_path, root):
                    raise PublicationError(
                        "{} parent does not exist".format(label)
                    )
                os.mkdir(component, mode=0o700, dir_fd=current_fd)
                created = True
                before = os.stat(
                    component, dir_fd=current_fd, follow_symlinks=False
                )
            if not stat.S_ISDIR(before.st_mode):
                raise PublicationError(
                    "{} parent contains a non-directory".format(label)
                )
            child_fd = os.open(
                component, Base._directory_flags(), dir_fd=current_fd
            )
            descriptors.append(child_fd)
            if created:
                os.fchmod(child_fd, 0o700)
                before = os.stat(
                    component, dir_fd=current_fd, follow_symlinks=False
                )
            opened = os.fstat(child_fd)
            stable = _stable_identity(opened)
            if (
                stable != _stable_identity(before)
                or (created and (
                    stat.S_IMODE(opened.st_mode) != 0o700
                    or opened.st_uid != os.getuid()
                ))
            ):
                raise PublicationError("{} parent changed".format(label))
            relations.append((current_fd, component, child_fd, stable))
            current_fd = child_fd
            current_path = next_path
        return descriptors, relations
    except Exception:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        raise


def _check_directory_chain(
    descriptors: list[int],
    relations: list[tuple[int, str, int, tuple[int, ...]]],
    label: str,
) -> None:
    if not descriptors:
        raise PublicationError("{} directory chain is empty".format(label))
    for descriptor in descriptors:
        current = os.fstat(descriptor)
        if not stat.S_ISDIR(current.st_mode):
            raise PublicationError("{} directory changed".format(label))
    for parent_fd, component, child_fd, expected in relations:
        entry = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(child_fd)
        if (
            not stat.S_ISDIR(entry.st_mode)
            or _stable_identity(entry) != expected
            or _stable_identity(opened) != expected
        ):
            raise PublicationError("{} directory chain changed".format(label))


def _read_published_leaf(
    parent_fd: int,
    name: str,
    *,
    expected_identity: tuple[int, ...],
    expected_sha256: str,
    label: str,
) -> None:
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if (
        not stat.S_ISREG(before.st_mode)
        or _stable_file_identity(before) != expected_identity
    ):
        raise PublicationError("{} published leaf changed".format(label))
    descriptor = os.open(name, Base._file_flags(), dir_fd=parent_fd)
    try:
        opened = os.fstat(descriptor)
        if _stable_file_identity(opened) != expected_identity:
            raise PublicationError("{} published leaf changed".format(label))
        digest = hashlib.sha256()
        count = 0
        while True:
            block = os.read(descriptor, CHUNK_BYTES)
            if not block:
                break
            digest.update(block)
            count += len(block)
        after_fd = os.fstat(descriptor)
        after_path = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            count != expected_identity[-1]
            or digest.hexdigest() != expected_sha256
            or _stable_file_identity(after_fd) != expected_identity
            or _stable_file_identity(after_path) != expected_identity
        ):
            raise PublicationError("{} published bytes changed".format(label))
    finally:
        os.close(descriptor)


def atomic_exclusive_bytes(
    path: Path, raw: bytes, label: str, *, root: Path
) -> str:
    """Publish bytes exclusively through one retained, no-follow parent FD.

    The temporary descriptor remains open through the hard link.  Both the
    linked inode and its bytes are then revalidated through the retained
    parent descriptor before success is reported.
    """
    target = _lexical_descendant(Path(path), Path(root), label)
    if not isinstance(raw, bytes) or not target.name:
        raise PublicationError("{} publication input is invalid".format(label))
    digest = hashlib.sha256(raw).hexdigest()
    descriptors: list[int] = []
    relations: list[tuple[int, str, int, tuple[int, ...]]] = []
    temp_fd: int | None = None
    temp_name: str | None = None
    temp_identity: tuple[int, ...] | None = None
    target_identity: tuple[int, ...] | None = None
    target_created = False
    success = False
    try:
        descriptors, relations = _open_directory_chain(
            target.parent, root=Path(root), label=label,
            create_missing=True,
        )
        parent_fd = descriptors[-1]
        _check_directory_chain(descriptors, relations, label)
        try:
            os.stat(target.name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise PublicationError("refusing to overwrite {}".format(label))

        flags = (
            os.O_WRONLY | os.O_CREAT | os.O_EXCL
            | getattr(os, "O_CLOEXEC", 0)
            | getattr(os, "O_NOFOLLOW", 0)
        )
        for _attempt in range(8):
            candidate = ".{}.v7-{}.tmp".format(
                target.name, secrets.token_hex(12)
            )
            try:
                temp_fd = os.open(candidate, flags, 0o600, dir_fd=parent_fd)
            except FileExistsError:
                continue
            temp_name = candidate
            break
        if temp_fd is None or temp_name is None:
            raise PublicationError("cannot allocate {} temporary file".format(label))
        os.fchmod(temp_fd, 0o600)
        view = memoryview(raw)
        written = 0
        while written < len(view):
            count = os.write(temp_fd, view[written:])
            if count <= 0:
                raise PublicationError("cannot write {}".format(label))
            written += count
        os.fsync(temp_fd)
        temp_info = os.fstat(temp_fd)
        temp_identity = _stable_file_identity(temp_info)
        temp_entry = os.stat(
            temp_name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (
            not stat.S_ISREG(temp_info.st_mode)
            or stat.S_IMODE(temp_info.st_mode) != 0o600
            or temp_info.st_uid != os.getuid()
            or temp_identity != _stable_file_identity(temp_entry)
            or temp_info.st_size != len(raw)
        ):
            raise PublicationError("{} temporary file changed".format(label))

        try:
            os.link(
                temp_name, target.name,
                src_dir_fd=parent_fd, dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
        except FileExistsError as err:
            raise PublicationError(
                "refusing to overwrite {}".format(label)
            ) from err
        target_created = True
        target_entry = os.stat(
            target.name, dir_fd=parent_fd, follow_symlinks=False
        )
        target_identity = _stable_file_identity(target_entry)
        # This catches a temp-name swap between the pre-link check and link.
        if (
            target_identity != temp_identity
            or _stable_file_identity(os.fstat(temp_fd)) != temp_identity
            or _stable_file_identity(os.stat(
                temp_name, dir_fd=parent_fd, follow_symlinks=False
            )) != temp_identity
        ):
            raise PublicationError("{} temporary link changed".format(label))
        _read_published_leaf(
            parent_fd, target.name,
            expected_identity=temp_identity,
            expected_sha256=digest,
            label=label,
        )
        os.unlink(temp_name, dir_fd=parent_fd)
        temp_name = None
        os.fsync(parent_fd)
        _read_published_leaf(
            parent_fd, target.name,
            expected_identity=temp_identity,
            expected_sha256=digest,
            label=label,
        )
        _check_directory_chain(descriptors, relations, label)
        success = True
        return digest
    except PublicationError:
        raise
    except OSError as err:
        raise PublicationError("cannot publish {}".format(label)) from err
    finally:
        if descriptors:
            parent_fd = descriptors[-1]
            if temp_name is not None and temp_identity is not None:
                try:
                    current = os.stat(
                        temp_name, dir_fd=parent_fd, follow_symlinks=False
                    )
                    if _stable_file_identity(current) == temp_identity:
                        os.unlink(temp_name, dir_fd=parent_fd)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
            if target_created and not success and target_identity is not None:
                try:
                    current = os.stat(
                        target.name, dir_fd=parent_fd, follow_symlinks=False
                    )
                    if _stable_file_identity(current) == target_identity:
                        os.unlink(target.name, dir_fd=parent_fd)
                        os.fsync(parent_fd)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
        if temp_fd is not None:
            os.close(temp_fd)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def create_private_directory(
    path: Path, label: str, *, root: Path
) -> dict[str, int]:
    """Create one private directory through a retained no-follow parent FD."""
    target = _lexical_descendant(Path(path), Path(root), label)
    descriptors: list[int] = []
    relations: list[tuple[int, str, int, tuple[int, ...]]] = []
    created = False
    target_fd: int | None = None
    target_identity: tuple[int, ...] | None = None
    success = False
    try:
        descriptors, relations = _open_directory_chain(
            target.parent, root=Path(root), label=label,
            create_missing=False,
        )
        parent_fd = descriptors[-1]
        _check_directory_chain(descriptors, relations, label)
        try:
            os.mkdir(target.name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError as err:
            raise PublicationError(
                "refusing to reuse {}".format(label)
            ) from err
        created = True
        before = os.stat(
            target.name, dir_fd=parent_fd, follow_symlinks=False
        )
        target_fd = os.open(
            target.name, Base._directory_flags(), dir_fd=parent_fd
        )
        os.fchmod(target_fd, 0o700)
        current = os.fstat(target_fd)
        target_identity = _stable_identity(current)
        entry = os.stat(
            target.name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (
            not stat.S_ISDIR(before.st_mode)
            or not stat.S_ISDIR(current.st_mode)
            or target_identity != _stable_identity(entry)
            or stat.S_IMODE(current.st_mode) != 0o700
            or current.st_uid != os.getuid()
            or os.listdir(target_fd)
        ):
            raise PublicationError("{} identity changed".format(label))
        os.fsync(target_fd)
        os.fsync(parent_fd)
        _check_directory_chain(descriptors, relations, label)
        final_fd = os.fstat(target_fd)
        final_entry = os.stat(
            target.name, dir_fd=parent_fd, follow_symlinks=False
        )
        if (
            _stable_identity(final_fd) != target_identity
            or _stable_identity(final_entry) != target_identity
            or stat.S_IMODE(final_fd.st_mode) != 0o700
            or final_fd.st_uid != os.getuid()
            or os.listdir(target_fd)
        ):
            raise PublicationError("{} changed after creation".format(label))
        current = final_fd
        success = True
        return Base._identity(current)
    except PublicationError:
        raise
    except OSError as err:
        raise PublicationError("cannot create {}".format(label)) from err
    finally:
        if created and not success and descriptors and target_identity is not None:
            parent_fd = descriptors[-1]
            try:
                current = os.stat(
                    target.name, dir_fd=parent_fd, follow_symlinks=False
                )
                if _stable_identity(current) == target_identity:
                    os.rmdir(target.name, dir_fd=parent_fd)
                    os.fsync(parent_fd)
            except OSError:
                pass
        if target_fd is not None:
            os.close(target_fd)
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _hash_selected_leaf(root_fd: int, name: str, label: str):
    before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise SelectedTreeError("{} selected leaf is not regular".format(label))
    descriptor = os.open(name, Base._file_flags(), dir_fd=root_fd)
    try:
        opened = os.fstat(descriptor)
        fingerprint = Base._fingerprint(opened)
        if fingerprint != Base._fingerprint(before):
            raise SelectedTreeError(
                "{} selected leaf changed before reading".format(label)
            )
        digest = hashlib.sha256()
        count = 0
        while True:
            block = os.read(descriptor, CHUNK_BYTES)
            if not block:
                break
            count += len(block)
            digest.update(block)
        after_fd = os.fstat(descriptor)
        after_path = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        if (
            count != opened.st_size
            or Base._fingerprint(after_fd) != fingerprint
            or Base._fingerprint(after_path) != fingerprint
        ):
            raise SelectedTreeError(
                "{} selected leaf changed while reading".format(label)
            )
        return digest.hexdigest(), Base._identity(opened), fingerprint
    finally:
        os.close(descriptor)


def read_selected_flat_tree(
    root: Path,
    selected_names: tuple[str, ...],
    *,
    label: str,
    expected_path: Path,
    read_callback: ReadCallback | None = None,
) -> SelectedFlatTree:
    """Hash exactly ``selected_names`` without opening any other leaf."""
    try:
        candidate = Base._lexical_target(
            Path(root), label=label, expected_path=Path(expected_path), root=None
        )
    except Base.SafeTreeError as err:
        raise SelectedTreeError(str(err)) from err
    if (
        type(selected_names) is not tuple
        or not selected_names
        or selected_names != tuple(sorted(set(selected_names)))
        or any(
            not isinstance(name, str)
            or not name
            or name in (".", "..")
            or "/" in name
            or name != os.path.normpath(name)
            for name in selected_names
        )
    ):
        raise SelectedTreeError("{} selected name set is invalid".format(label))

    anchor, parts = Base._anchor_parts(candidate)
    if not parts:
        raise SelectedTreeError("{} is not a directory tree".format(label))
    descriptors: list[int] = []
    try:
        anchor_fd, anchor_fingerprint = Base._open_anchor(
            anchor, label, descriptors
        )
        root_fd, ancestors = Base._walk_directories(
            anchor_fd, parts, descriptors, label
        )
        root_fingerprint = Base._fingerprint(os.fstat(root_fd))
        records = []
        for name in selected_names:
            digest, identity, fingerprint = _hash_selected_leaf(
                root_fd, name, label
            )
            records.append({
                "path": name,
                "sha256": digest,
                "identity": identity,
                "fingerprint": fingerprint,
            })

        by_name = {record["path"]: record for record in records}

        def read_selected(name: str) -> bytes:
            record = by_name.get(name)
            if record is None:
                raise SelectedTreeError(
                    "{} callback requested an unselected leaf".format(label)
                )
            before = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            descriptor = os.open(name, Base._file_flags(), dir_fd=root_fd)
            try:
                opened = os.fstat(descriptor)
                if (
                    Base._fingerprint(before) != record["fingerprint"]
                    or Base._fingerprint(opened) != record["fingerprint"]
                ):
                    raise SelectedTreeError(
                        "{} callback leaf changed before reading".format(label)
                    )
                chunks = []
                digest = hashlib.sha256()
                count = 0
                while True:
                    block = os.read(descriptor, CHUNK_BYTES)
                    if not block:
                        break
                    chunks.append(block)
                    count += len(block)
                    digest.update(block)
                after_fd = os.fstat(descriptor)
                after_path = os.stat(
                    name, dir_fd=root_fd, follow_symlinks=False
                )
                if (
                    count != record["identity"]["size"]
                    or digest.hexdigest() != record["sha256"]
                    or Base._fingerprint(after_fd) != record["fingerprint"]
                    or Base._fingerprint(after_path) != record["fingerprint"]
                ):
                    raise SelectedTreeError(
                        "{} callback leaf changed while reading".format(label)
                    )
                return b"".join(chunks)
            finally:
                os.close(descriptor)

        if read_callback is not None:
            read_callback(read_selected)

        # A second complete selected-set pass plus a final stat sweep closes
        # the same early-leaf mutation window as the complete-tree V6 reader.
        for record in records:
            digest, _identity, fingerprint = _hash_selected_leaf(
                root_fd, record["path"], label
            )
            if (
                digest != record["sha256"]
                or fingerprint != record["fingerprint"]
            ):
                raise SelectedTreeError(
                    "{} selected leaf changed after reading".format(label)
                )
        for record in records:
            current = os.stat(
                record["path"], dir_fd=root_fd, follow_symlinks=False
            )
            if Base._fingerprint(current) != record["fingerprint"]:
                raise SelectedTreeError(
                    "{} selected leaf changed after reading".format(label)
                )
        if (
            Base._fingerprint(os.fstat(root_fd)) != root_fingerprint
        ):
            raise SelectedTreeError(
                "{} namespace changed while reading".format(label)
            )
        Base._check_chain(
            anchor=anchor,
            anchor_fd=anchor_fd,
            anchor_fingerprint=anchor_fingerprint,
            ancestors=ancestors,
            label=label,
        )
        return SelectedFlatTree(
            files=tuple(SelectedFile(
                record["path"], record["sha256"], record["identity"]
            ) for record in records),
            root_identity=Base._identity(os.fstat(root_fd)),
        )
    except SelectedTreeError:
        raise
    except (Base.SafeTreeError, OSError) as err:
        raise SelectedTreeError(
            "cannot read {} selected tree safely".format(label)
        ) from err
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)
