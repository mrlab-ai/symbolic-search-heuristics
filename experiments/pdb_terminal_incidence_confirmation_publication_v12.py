#!/usr/bin/env python3
"""Fail-closed publication of immutable, single-directory shard payloads.

The caller prepares a private staging directory containing the complete payload.
Publication claims a previously absent final directory, hard-links every payload
file into it, and creates ``complete.json`` only after the linked payload has
passed a second validation.  A claimed directory without a valid completion
marker is deliberately never repaired or replaced.
"""

import dataclasses
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Dict, Mapping, Tuple


COMPLETION_NAME = "complete.json"
COMPLETION_TEMP_NAME = ".complete.json.new"
COMPLETION_MODE = 0o400
FINAL_DIRECTORY_MODE = 0o500
PRIVATE_STAGE_MODE = 0o700
COMPLETION_SCHEMA = (
    "pdb-terminal-incidence/immutable-shard-completion/v1"
)

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")


class PublicationError(RuntimeError):
    """The requested publication was unsafe or did not validate exactly."""


@dataclasses.dataclass(frozen=True)
class FileExpectation:
    """Expected immutable bytes and permission bits for one staged file."""

    sha256: str
    mode: int


@dataclasses.dataclass(frozen=True)
class DirectoryIdentity:
    """Stable identity bound into the completion marker."""

    device: int
    inode: int
    uid: int
    gid: int
    mode: int

    def as_json(self) -> dict:
        return {
            "device": self.device,
            "gid": self.gid,
            "inode": self.inode,
            "mode": "{:04o}".format(self.mode),
            "uid": self.uid,
        }


@dataclasses.dataclass(frozen=True)
class PublicationReceipt:
    """Validated publication identity returned to the caller."""

    final_dir: Path
    completion_sha256: str
    completion: dict
    final_directory_identity: DirectoryIdentity


@dataclasses.dataclass
class _OpenedFile:
    name: str
    expectation: FileExpectation
    fd: int
    device: int
    inode: int
    uid: int
    gid: int
    size: int

    def marker_record(self) -> dict:
        return {
            "device": self.device,
            "gid": self.gid,
            "inode": self.inode,
            "mode": "{:04o}".format(self.expectation.mode),
            "name": self.name,
            "sha256": self.expectation.sha256,
            "size": self.size,
            "uid": self.uid,
        }


def _validate_json(value, location="metadata") -> None:
    if value is None or type(value) in (bool, int, str):
        return
    if type(value) is list:
        for index, item in enumerate(value):
            _validate_json(item, "{}[{}]".format(location, index))
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise PublicationError(
                    "{} has a non-string object key".format(location)
                )
            _validate_json(item, "{}.{}".format(location, key))
        return
    raise PublicationError(
        "{} contains a non-canonical JSON value".format(location)
    )


def canonical_json_bytes(value) -> bytes:
    """Serialize the deliberately small canonical-JSON subset used here."""
    _validate_json(value)
    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("ascii")
    except (TypeError, ValueError, UnicodeError) as err:
        raise PublicationError("cannot encode canonical JSON") from err


def _normalize_expectations(
    expected_files: Mapping[str, FileExpectation],
) -> Dict[str, FileExpectation]:
    if not isinstance(expected_files, Mapping):
        raise PublicationError("expected_files must be a mapping")
    normalized = {}
    for name, expectation in expected_files.items():
        if (
            type(name) is not str
            or not name
            or name in (".", "..", COMPLETION_NAME, COMPLETION_TEMP_NAME)
            or "/" in name
            or "\x00" in name
        ):
            raise PublicationError("unsafe payload file name: {!r}".format(name))
        if type(expectation) is not FileExpectation:
            raise PublicationError(
                "invalid expectation for payload file {!r}".format(name)
            )
        if not _SHA256_RE.fullmatch(expectation.sha256):
            raise PublicationError(
                "invalid SHA-256 for payload file {!r}".format(name)
            )
        if (
            type(expectation.mode) is not int
            or expectation.mode < 0
            or expectation.mode > 0o777
            or expectation.mode & 0o222
        ):
            raise PublicationError(
                "payload file {!r} must have a non-writable permission mode".format(
                    name
                )
            )
        normalized[name] = expectation
    return dict(sorted(normalized.items()))


def _path_parts(path, label: str) -> Tuple[Path, str]:
    path = Path(path)
    if not path.name or path.name in (".", ".."):
        raise PublicationError("{} must name a directory entry".format(label))
    return path.parent, path.name


def _directory_flags() -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return flags


def _open_directory(path, label: str) -> int:
    try:
        fd = os.open(path, _directory_flags())
    except OSError as err:
        raise PublicationError("cannot open {}".format(label)) from err
    try:
        observed = os.fstat(fd)
        if not stat.S_ISDIR(observed.st_mode):
            raise PublicationError("{} is not a directory".format(label))
    except BaseException:
        os.close(fd)
        raise
    return fd


def _open_directory_at(parent_fd: int, name: str, label: str) -> int:
    try:
        fd = os.open(name, _directory_flags(), dir_fd=parent_fd)
    except OSError as err:
        raise PublicationError("cannot open {}".format(label)) from err
    try:
        observed = os.fstat(fd)
        if not stat.S_ISDIR(observed.st_mode):
            raise PublicationError("{} is not a directory".format(label))
    except BaseException:
        os.close(fd)
        raise
    return fd


def _directory_entries(fd: int, label: str):
    try:
        return set(os.listdir(fd))
    except OSError as err:
        raise PublicationError("cannot list {}".format(label)) from err


def _same_identity(left, right) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and stat.S_IFMT(left.st_mode) == stat.S_IFMT(right.st_mode)
    )


def _stable_digest(fd: int, label: str) -> Tuple[str, object]:
    try:
        before = os.fstat(fd)
        os.lseek(fd, 0, os.SEEK_SET)
        digest = hashlib.sha256()
        while True:
            block = os.read(fd, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(fd)
    except OSError as err:
        raise PublicationError("cannot hash {}".format(label)) from err
    stable_fields = (
        "st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
        "st_size", "st_mtime_ns", "st_ctime_ns",
    )
    if any(getattr(before, field) != getattr(after, field) for field in stable_fields):
        raise PublicationError("{} changed while it was hashed".format(label))
    return digest.hexdigest(), after


def _open_payload_at(directory_fd: int, name: str, label: str) -> int:
    # O_NONBLOCK makes opening an adversarial FIFO return promptly; it has no
    # effect on the reads from a subsequently verified regular file.
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as err:
        raise PublicationError("cannot open {}".format(label)) from err
    try:
        observed = os.fstat(fd)
        if not stat.S_ISREG(observed.st_mode):
            raise PublicationError("{} is not a regular file".format(label))
    except BaseException:
        os.close(fd)
        raise
    return fd


def _stat_entry(directory_fd: int, name: str, label: str):
    try:
        observed = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as err:
        raise PublicationError("cannot inspect {}".format(label)) from err
    if not stat.S_ISREG(observed.st_mode):
        raise PublicationError("{} is not a regular file".format(label))
    return observed


def _check_opened_file(
    opened: _OpenedFile,
    directory_fd: int,
    label: str,
    expected_links: int,
) -> None:
    path_stat = _stat_entry(directory_fd, opened.name, label)
    fd = _open_payload_at(directory_fd, opened.name, label)
    try:
        digest, fd_stat = _stable_digest(fd, label)
    finally:
        os.close(fd)
    if not _same_identity(path_stat, fd_stat):
        raise PublicationError("{} changed during validation".format(label))
    if (
        path_stat.st_dev != opened.device
        or path_stat.st_ino != opened.inode
        or path_stat.st_uid != opened.uid
        or path_stat.st_gid != opened.gid
        or path_stat.st_size != opened.size
        or stat.S_IMODE(path_stat.st_mode) != opened.expectation.mode
        or path_stat.st_nlink != expected_links
        or digest != opened.expectation.sha256
    ):
        raise PublicationError("{} does not match its immutable manifest".format(label))


def _validate_payload_closure(
    stage_fd: int,
    final_fd: int,
    opened_files: Mapping[str, _OpenedFile],
    marker_present: bool,
) -> None:
    names = set(opened_files)
    if _directory_entries(stage_fd, "staging directory") != names:
        raise PublicationError("staging directory closure changed")
    expected_final = names | ({COMPLETION_NAME} if marker_present else set())
    if _directory_entries(final_fd, "final directory") != expected_final:
        raise PublicationError("final directory closure changed")
    for name, opened in opened_files.items():
        _check_opened_file(
            opened, stage_fd, "staged payload {!r}".format(name), 2
        )
        _check_opened_file(
            opened, final_fd, "published payload {!r}".format(name), 2
        )


def _write_all(fd: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(fd, payload[offset:])
        if written <= 0:
            raise OSError("zero-length completion-marker write")
        offset += written


def _write_completion_marker(final_fd: int, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    marker_fd = None
    try:
        marker_fd = os.open(
            COMPLETION_TEMP_NAME, flags, COMPLETION_MODE, dir_fd=final_fd
        )
        marker_identity = os.fstat(marker_fd)
        if not stat.S_ISREG(marker_identity.st_mode):
            raise PublicationError("completion-marker temporary is not regular")
        os.fchmod(marker_fd, COMPLETION_MODE)
        _write_all(marker_fd, payload)
        os.fsync(marker_fd)
        os.close(marker_fd)
        marker_fd = None

        temporary = _stat_entry(
            final_fd, COMPLETION_TEMP_NAME, "completion-marker temporary"
        )
        if (
            not _same_identity(temporary, marker_identity)
            or stat.S_IMODE(temporary.st_mode) != COMPLETION_MODE
            or temporary.st_nlink != 1
            or temporary.st_size != len(payload)
        ):
            raise PublicationError("completion-marker temporary changed")
        temporary_fd = _open_payload_at(
            final_fd, COMPLETION_TEMP_NAME, "completion-marker temporary"
        )
        try:
            digest, stable = _stable_digest(
                temporary_fd, "completion-marker temporary"
            )
        finally:
            os.close(temporary_fd)
        if (
            not _same_identity(stable, marker_identity)
            or digest != hashlib.sha256(payload).hexdigest()
        ):
            raise PublicationError("completion-marker temporary bytes changed")

        # This hard link is the publication linearization point.  A crash while
        # writing the temporary can never expose a file named complete.json.
        os.link(
            COMPLETION_TEMP_NAME,
            COMPLETION_NAME,
            src_dir_fd=final_fd,
            dst_dir_fd=final_fd,
            follow_symlinks=False,
        )
        published = _stat_entry(final_fd, COMPLETION_NAME, "completion marker")
        if not _same_identity(published, marker_identity) or published.st_nlink != 2:
            raise PublicationError("completion marker link changed")
        os.unlink(COMPLETION_TEMP_NAME, dir_fd=final_fd)
        published = _stat_entry(final_fd, COMPLETION_NAME, "completion marker")
        if not _same_identity(published, marker_identity) or published.st_nlink != 1:
            raise PublicationError("completion marker changed after publication")
    except BaseException as err:
        # Retain every incomplete claimed artifact.  In particular, do not
        # promote or remove a partial temporary after an interrupted write.
        if isinstance(err, PublicationError):
            raise
        raise PublicationError("cannot create completion marker") from err
    finally:
        if marker_fd is not None:
            os.close(marker_fd)


def _validate_completion_marker(final_fd: int, expected: bytes) -> None:
    marker_stat = _stat_entry(final_fd, COMPLETION_NAME, "completion marker")
    if (
        stat.S_IMODE(marker_stat.st_mode) != COMPLETION_MODE
        or marker_stat.st_nlink != 1
        or marker_stat.st_size != len(expected)
    ):
        raise PublicationError("completion marker metadata changed")
    marker_fd = _open_payload_at(final_fd, COMPLETION_NAME, "completion marker")
    try:
        try:
            os.lseek(marker_fd, 0, os.SEEK_SET)
            chunks = []
            while True:
                block = os.read(marker_fd, 1024 * 1024)
                if not block:
                    break
                chunks.append(block)
        except OSError as err:
            raise PublicationError("cannot read completion marker") from err
    finally:
        os.close(marker_fd)
    if b"".join(chunks) != expected:
        raise PublicationError("completion marker bytes changed")


def _final_identity(observed) -> DirectoryIdentity:
    return DirectoryIdentity(
        device=observed.st_dev,
        inode=observed.st_ino,
        uid=observed.st_uid,
        gid=observed.st_gid,
        mode=FINAL_DIRECTORY_MODE,
    )


def _validate_final_directory(final_fd: int, identity: DirectoryIdentity) -> None:
    try:
        observed = os.fstat(final_fd)
    except OSError as err:
        raise PublicationError("cannot inspect final directory") from err
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_dev != identity.device
        or observed.st_ino != identity.inode
        or observed.st_uid != identity.uid
        or observed.st_gid != identity.gid
        or stat.S_IMODE(observed.st_mode) != identity.mode
    ):
        raise PublicationError("final directory identity changed")


def publish_immutable_shard(
    stage_dir,
    final_dir,
    expected_files: Mapping[str, FileExpectation],
    completion_metadata: Mapping[str, object],
) -> PublicationReceipt:
    """Publish one exact staged payload without ever replacing a final path.

    ``stage_dir`` must be a current-user-owned 0700 directory whose flat file
    closure exactly matches ``expected_files``.  Every expected mode must be
    non-writable.  On any failure after the exclusive final-directory claim,
    the claimed directory is retained so that callers cannot mistake a retry
    for the original publication attempt.
    """
    expectations = _normalize_expectations(expected_files)
    if type(completion_metadata) is not dict:
        raise PublicationError("completion_metadata must be a JSON object")
    metadata_bytes = canonical_json_bytes(completion_metadata)
    metadata = json.loads(metadata_bytes.decode("ascii"))

    stage_parent_path, stage_name = _path_parts(stage_dir, "stage_dir")
    final_parent_path, final_name = _path_parts(final_dir, "final_dir")
    stage_dir = Path(stage_dir)
    final_dir = Path(final_dir)

    stage_parent_fd = stage_fd = final_parent_fd = final_fd = None
    opened_files = {}
    try:
        stage_parent_fd = _open_directory(stage_parent_path, "staging parent")
        stage_fd = _open_directory_at(
            stage_parent_fd, stage_name, "staging directory"
        )
        stage_stat = os.fstat(stage_fd)
        if (
            stage_stat.st_uid != os.geteuid()
            or stat.S_IMODE(stage_stat.st_mode) != PRIVATE_STAGE_MODE
        ):
            raise PublicationError(
                "staging directory must be current-user-owned mode 0700"
            )
        if _directory_entries(stage_fd, "staging directory") != set(expectations):
            raise PublicationError("staging directory closure changed")

        for name, expectation in expectations.items():
            fd = _open_payload_at(
                stage_fd, name, "staged payload {!r}".format(name)
            )
            try:
                digest, observed = _stable_digest(
                    fd, "staged payload {!r}".format(name)
                )
                if (
                    observed.st_uid != os.geteuid()
                    or observed.st_nlink != 1
                    or stat.S_IMODE(observed.st_mode) != expectation.mode
                    or digest != expectation.sha256
                ):
                    raise PublicationError(
                        "staged payload {!r} does not match its manifest".format(
                            name
                        )
                    )
                opened_files[name] = _OpenedFile(
                    name=name,
                    expectation=expectation,
                    fd=fd,
                    device=observed.st_dev,
                    inode=observed.st_ino,
                    uid=observed.st_uid,
                    gid=observed.st_gid,
                    size=observed.st_size,
                )
                fd = None
            finally:
                if fd is not None:
                    os.close(fd)

        final_parent_fd = _open_directory(final_parent_path, "final parent")
        final_parent_stat = os.fstat(final_parent_fd)
        if final_parent_stat.st_dev != stage_stat.st_dev:
            raise PublicationError(
                "staging and final directories are not on the same filesystem"
            )
        if _same_identity(stage_stat, final_parent_stat):
            raise PublicationError("final directory cannot be created inside stage_dir")
        try:
            os.mkdir(final_name, PRIVATE_STAGE_MODE, dir_fd=final_parent_fd)
        except FileExistsError as err:
            raise PublicationError("refusing to reuse existing final_dir") from err
        except OSError as err:
            raise PublicationError("cannot claim final_dir") from err
        try:
            os.fsync(final_parent_fd)
        except OSError as err:
            raise PublicationError("cannot persist final_dir claim") from err

        final_fd = _open_directory_at(final_parent_fd, final_name, "final directory")
        os.fchmod(final_fd, PRIVATE_STAGE_MODE)
        final_stat = os.fstat(final_fd)
        if (
            final_stat.st_uid != os.geteuid()
            or final_stat.st_dev != stage_stat.st_dev
            or stat.S_IMODE(final_stat.st_mode) != PRIVATE_STAGE_MODE
            or _directory_entries(final_fd, "final directory")
        ):
            raise PublicationError("claimed final directory changed")
        final_identity = _final_identity(final_stat)

        for name, opened in opened_files.items():
            _check_opened_file(
                opened, stage_fd, "staged payload {!r}".format(name), 1
            )
            try:
                os.link(
                    name,
                    name,
                    src_dir_fd=stage_fd,
                    dst_dir_fd=final_fd,
                    follow_symlinks=False,
                )
            except OSError as err:
                raise PublicationError(
                    "cannot exclusively publish payload {!r}".format(name)
                ) from err
            _check_opened_file(
                opened, final_fd, "published payload {!r}".format(name), 2
            )

        _validate_payload_closure(
            stage_fd, final_fd, opened_files, marker_present=False
        )
        completion = {
            "files": [
                opened_files[name].marker_record() for name in sorted(opened_files)
            ],
            "final_directory": final_identity.as_json(),
            "metadata": metadata,
            "schema": COMPLETION_SCHEMA,
        }
        completion_bytes = canonical_json_bytes(completion)
        _write_completion_marker(final_fd, completion_bytes)

        try:
            os.fchmod(final_fd, FINAL_DIRECTORY_MODE)
            os.fsync(final_fd)
            os.fsync(final_parent_fd)
        except OSError as err:
            raise PublicationError("cannot seal final directory") from err
        _validate_final_directory(final_fd, final_identity)
        _validate_payload_closure(
            stage_fd, final_fd, opened_files, marker_present=True
        )
        _validate_completion_marker(final_fd, completion_bytes)

        for name, opened in opened_files.items():
            _check_opened_file(
                opened, stage_fd, "staged payload {!r}".format(name), 2
            )
            try:
                os.unlink(name, dir_fd=stage_fd)
            except OSError as err:
                raise PublicationError(
                    "cannot remove staged payload {!r}".format(name)
                ) from err
        if _directory_entries(stage_fd, "staging directory"):
            raise PublicationError("staging directory was not emptied exactly")
        current_stage = os.stat(
            stage_name, dir_fd=stage_parent_fd, follow_symlinks=False
        )
        if not _same_identity(current_stage, stage_stat):
            raise PublicationError("staging directory identity changed")
        try:
            os.rmdir(stage_name, dir_fd=stage_parent_fd)
        except OSError as err:
            raise PublicationError("cannot remove staging directory") from err
        for parent_fd, label in (
            (stage_parent_fd, "staging-directory cleanup"),
            (final_parent_fd, "final-directory publication"),
        ):
            try:
                os.fsync(parent_fd)
            except OSError as err:
                raise PublicationError("cannot persist " + label) from err

        if _directory_entries(final_fd, "final directory") != (
            set(opened_files) | {COMPLETION_NAME}
        ):
            raise PublicationError("final directory closure changed after cleanup")
        for name, opened in opened_files.items():
            _check_opened_file(
                opened, final_fd, "published payload {!r}".format(name), 1
            )
        _validate_completion_marker(final_fd, completion_bytes)
        _validate_final_directory(final_fd, final_identity)
        return PublicationReceipt(
            final_dir=final_dir,
            completion_sha256=hashlib.sha256(completion_bytes).hexdigest(),
            completion=completion,
            final_directory_identity=final_identity,
        )
    except PublicationError:
        raise
    except OSError as err:
        raise PublicationError("publication failed") from err
    finally:
        for opened in opened_files.values():
            try:
                os.close(opened.fd)
            except OSError:
                pass
        for fd in (final_fd, final_parent_fd, stage_fd, stage_parent_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass
