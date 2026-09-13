#!/usr/bin/env python3
"""Read exact regular-file bytes from an explicitly pinned Jujutsu commit."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any, Callable


class SnapshotReaderError(RuntimeError):
    """The requested immutable repository snapshot was not unambiguous."""


REPO = Path(os.path.abspath(__file__)).parent.parent
JJ_EXECUTABLE = Path("/home/jendrik/bin/jj")
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
PATH_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
COMMIT_TEMPLATE = 'commit_id ++ "\\t" ++ if(conflict, "1", "0") ++ "\\n"'
ENTRY_TEMPLATE = 'path ++ "\\t" ++ self.file_type() ++ "\\n"'

Runner = Callable[..., Any]


def _checked_run(
    repository: Path, args: list[str], runner: Runner,
) -> bytes:
    command = [
        str(JJ_EXECUTABLE), "--no-pager", "--ignore-working-copy",
        "-R", str(repository), *args,
    ]
    try:
        completed = runner(
            command, cwd=repository, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except OSError as err:
        raise SnapshotReaderError("Jujutsu snapshot query failed") from err
    returncode = getattr(completed, "returncode", None)
    stdout = getattr(completed, "stdout", None)
    stderr = getattr(completed, "stderr", None)
    if type(returncode) is not int or type(stdout) is not bytes:
        raise SnapshotReaderError("Jujutsu runner returned an invalid result")
    if returncode != 0:
        detail = (
            stderr.decode("utf-8", "replace").strip()
            if isinstance(stderr, bytes) else ""
        )
        raise SnapshotReaderError(
            "Jujutsu snapshot query failed{}".format(
                ": " + detail if detail else ""
            )
        )
    return stdout


def _resolve_revision(
    repository: Path, seal_revision: str, runner: Runner,
) -> str:
    raw = _checked_run(
        repository,
        [
            "log", "-r", seal_revision, "--no-graph", "-T",
            COMMIT_TEMPLATE,
        ],
        runner,
    )
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise SnapshotReaderError(
            "Jujutsu returned a non-ASCII revision identity"
        ) from err
    if len(lines) != 1:
        raise SnapshotReaderError("seal revision is missing or ambiguous")
    fields = lines[0].split("\t")
    if (
        len(fields) != 2
        or fields[0] != seal_revision
        or COMMIT_RE.fullmatch(fields[0]) is None
        or fields[1] != "0"
    ):
        raise SnapshotReaderError(
            "seal revision changed identity or contains conflicts"
        )
    return fields[0]


def _validate_paths(paths: list[str]) -> list[str]:
    if type(paths) is not list or not paths:
        raise SnapshotReaderError("snapshot paths must be a nonempty list")
    seen: set[str] = set()
    for path in paths:
        if type(path) is not str:
            raise SnapshotReaderError("snapshot path is not text")
        if path in seen:
            raise SnapshotReaderError("snapshot paths contain duplicates")
        seen.add(path)
        pure = PurePosixPath(path)
        if (
            PATH_RE.fullmatch(path) is None
            or pure.is_absolute()
            or pure.as_posix() != path
            or any(part in ("", ".", "..") for part in pure.parts)
            or pure.parts[0] in (".git", ".jj")
        ):
            raise SnapshotReaderError(
                "snapshot path is unsafe or ambiguous: {!r}".format(path)
            )
    return paths


def _validate_entries(raw: bytes, paths: list[str]) -> None:
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise SnapshotReaderError("Jujutsu returned a non-ASCII path") from err
    entries = []
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 2:
            raise SnapshotReaderError("Jujutsu returned an ambiguous path record")
        entries.append((fields[0], fields[1]))
    names = [path for path, _kind in entries]
    if len(names) != len(set(names)):
        raise SnapshotReaderError("Jujutsu returned duplicate paths")
    if set(names) != set(paths) or len(names) != len(paths):
        raise SnapshotReaderError("requested snapshot path is missing or ambiguous")
    if any(kind != "file" for _path, kind in entries):
        raise SnapshotReaderError("requested snapshot entry is not a regular file")


def read_committed_snapshot(
    seal_revision: str,
    paths: list[str],
    *,
    repository: Path = REPO,
    runner: Runner = subprocess.run,
) -> dict[str, bytes]:
    """Return exact bytes for *paths* at one explicit immutable commit.

    The signature matches the V9 consumer's ``snapshot_reader`` callback.
    Neither the working copy nor an implicit revision is consulted.
    """
    if (
        type(seal_revision) is not str
        or COMMIT_RE.fullmatch(seal_revision) is None
    ):
        raise SnapshotReaderError("seal revision must be an exact 40-hex commit")
    requested = _validate_paths(paths)
    repository = Path(os.path.abspath(repository))
    resolved = _resolve_revision(repository, seal_revision, runner)
    listing = _checked_run(
        repository,
        [
            "file", "list", "-r", resolved, "-T", ENTRY_TEMPLATE,
            "--", *requested,
        ],
        runner,
    )
    _validate_entries(listing, requested)
    result = {
        path: _checked_run(
            repository,
            ["file", "show", "-r", resolved, "--", path],
            runner,
        )
        for path in requested
    }
    if _resolve_revision(repository, seal_revision, runner) != resolved:
        raise SnapshotReaderError("seal revision drifted during snapshot")
    if type(result) is not dict or set(result) != set(requested):
        raise SnapshotReaderError("snapshot result closure changed")
    return result


__all__ = ["SnapshotReaderError", "read_committed_snapshot"]
