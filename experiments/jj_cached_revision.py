#!/usr/bin/env python3
"""Read-only Jujutsu source export and Lab-compatible revision caching.

Every repository query uses ``jj --ignore-working-copy``.  In particular,
this module never invokes Git in a Jujutsu workspace and never creates or
forgets a Jujutsu workspace.  Export is deliberately slower than ``git
archive``: each tracked file is read from the pinned commit object, so the
live working tree and concurrent edits cannot leak into the cache.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


class JjCacheError(RuntimeError):
    pass


EXPORT_PROTOCOL = "jj-file-show-pinned-commit-read-only-export-v1"
# This repository uses Jujutsu's Git backend, whose full commit IDs are the
# underlying 40-hex Git object IDs. They are resolved and exported by jj only.
COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
ENTRY_TEMPLATE = (
    'path ++ "\\t" ++ self.file_type() ++ "\\t" ++ '
    'if(self.executable(), "1", "0") ++ "\\n"'
)
COMMIT_TEMPLATE = 'commit_id ++ "\\t" ++ if(conflict, "1", "0") ++ "\\n"'
PATH_TEMPLATE = 'path ++ "\\n"'
JJ_EXECUTABLE = Path("/home/jendrik/bin/jj")
JJ_EXECUTABLE_SHA256 = (
    "d1d69a0f87df266eebf0d2592dd019eb288c300b15fd019afe26cb1ed11ba152"
)


def _verify_jj_identity() -> None:
    try:
        info = JJ_EXECUTABLE.lstat()
        raw = JJ_EXECUTABLE.read_bytes()
    except OSError as err:
        raise JjCacheError("cannot verify pinned Jujutsu executable") from err
    if (
        JJ_EXECUTABLE.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or hashlib.sha256(raw).hexdigest() != JJ_EXECUTABLE_SHA256
    ):
        raise JjCacheError("pinned Jujutsu executable identity changed")


def _run_jj(repo: Path, args: list[str]) -> bytes:
    _verify_jj_identity()
    command = [
        str(JJ_EXECUTABLE),
        "--ignore-working-copy",
        "--no-pager",
        "-R",
        str(repo),
        *args,
    ]
    try:
        completed = subprocess.run(
            command,
            check=True,
            cwd=repo,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        detail = getattr(err, "stderr", b"")
        if isinstance(detail, bytes):
            detail = detail.decode("utf-8", "replace").strip()
        raise JjCacheError("Jujutsu query failed: {}".format(detail or err)) from err
    _verify_jj_identity()
    return completed.stdout


def _parse_single_commit(raw: bytes, *, expected: str | None = None) -> str:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as err:
        raise JjCacheError("Jujutsu returned a non-ASCII commit identity") from err
    lines = text.splitlines()
    if len(lines) != 1:
        raise JjCacheError("revision must resolve to exactly one commit")
    fields = lines[0].split("\t")
    if (
        len(fields) != 2
        or COMMIT_RE.fullmatch(fields[0]) is None
        or fields[1] != "0"
        or (expected is not None and fields[0] != expected)
    ):
        raise JjCacheError("revision changed identity or contains conflicts")
    return fields[0]


def current_commit(repo: Path) -> str:
    """Return the full, conflict-free working-copy commit identity."""
    repo = Path(repo).resolve()
    if not repo.is_dir() or not (repo / ".jj").is_dir():
        raise JjCacheError("{} is not a Jujutsu workspace root".format(repo))
    raw = _run_jj(repo, ["log", "-r", "@", "--no-graph", "-T", COMMIT_TEMPLATE])
    return _parse_single_commit(raw)


def parent_commit(repo: Path) -> str:
    """Return the single full, conflict-free parent of the working copy."""
    repo = Path(repo).resolve()
    if not repo.is_dir() or not (repo / ".jj").is_dir():
        raise JjCacheError("{} is not a Jujutsu workspace root".format(repo))
    raw = _run_jj(repo, ["log", "-r", "@-", "--no-graph", "-T", COMMIT_TEMPLATE])
    return _parse_single_commit(raw)


def resolve_pinned_commit(repo: Path, revision: str) -> str:
    repo = Path(repo).resolve()
    if not repo.is_dir() or not (repo / ".jj").is_dir():
        raise JjCacheError("{} is not a Jujutsu workspace root".format(repo))
    if COMMIT_RE.fullmatch(revision) is None:
        raise JjCacheError("planner revision must be a full 40-hex commit ID")
    raw = _run_jj(
        repo,
        ["log", "-r", revision, "--no-graph", "-T", COMMIT_TEMPLATE],
    )
    return _parse_single_commit(raw, expected=revision)


def require_ancestor(repo: Path, ancestor: str, descendant: str) -> None:
    """Fail unless two full commit IDs exist and the first reaches the second."""
    repo = Path(repo).resolve()
    resolve_pinned_commit(repo, ancestor)
    resolve_pinned_commit(repo, descendant)
    raw = _run_jj(
        repo,
        [
            "log",
            "-r",
            "{} & ::{}".format(ancestor, descendant),
            "--no-graph",
            "-T",
            COMMIT_TEMPLATE,
        ],
    )
    try:
        _parse_single_commit(raw, expected=ancestor)
    except JjCacheError as err:
        raise JjCacheError(
            "revision {} is not an ancestor of {}".format(ancestor, descendant)
        ) from err


def working_copy_diff_summary(repo: Path) -> str:
    """Return Jujutsu's tracked working-copy change summary for ``@``."""
    raw = _run_jj(Path(repo).resolve(), ["diff", "--summary", "-r", "@"])
    try:
        return raw.decode("utf-8").strip()
    except UnicodeDecodeError as err:
        raise JjCacheError("Jujutsu returned a non-UTF-8 change summary") from err


def file_is_tracked_at(repo: Path, revision: str, relative: str) -> bool:
    """Return whether *relative* is exactly one tracked file at *revision*."""
    if COMMIT_RE.fullmatch(revision) is None:
        raise JjCacheError("revision must be a full 40-hex commit ID")
    pure = PurePosixPath(relative)
    if (
        not relative
        or pure.is_absolute()
        or ".." in pure.parts
        or any("\n" in part or "\t" in part for part in pure.parts)
        or pure.parts[0] in (".jj", ".git")
    ):
        raise JjCacheError("unsafe tracked path {!r}".format(relative))
    raw = _run_jj(
        Path(repo).resolve(),
        ["file", "list", "-r", revision, "-T", PATH_TEMPLATE, "--", relative],
    )
    try:
        lines = raw.decode("utf-8").splitlines()
    except UnicodeDecodeError as err:
        raise JjCacheError("tracked paths must be UTF-8") from err
    if not lines:
        return False
    if lines != [relative]:
        raise JjCacheError("Jujutsu returned an unexpected tracked path")
    return True


def tracked_file_sha256(repo: Path, revision: str, relative: str) -> str:
    """Return the content digest of one regular tracked file at *revision*."""
    if not file_is_tracked_at(repo, revision, relative):
        raise JjCacheError("tracked file does not exist: {}".format(relative))
    return hashlib.sha256(_file_bytes(repo, revision, relative)).hexdigest()


@dataclass(frozen=True)
class TreeEntry:
    path: str
    file_type: str
    executable: bool


def list_tree(repo: Path, revision: str) -> tuple[TreeEntry, ...]:
    raw = _run_jj(
        Path(repo).resolve(),
        ["file", "list", "-r", revision, "-T", ENTRY_TEMPLATE],
    )
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as err:
        raise JjCacheError("tracked paths must be UTF-8") from err
    entries = []
    for line in text.splitlines():
        fields = line.split("\t")
        if len(fields) != 3 or fields[2] not in ("0", "1"):
            raise JjCacheError("invalid Jujutsu tree-entry record")
        path, file_type, executable = fields
        pure = PurePosixPath(path)
        if (
            not path
            or pure.is_absolute()
            or ".." in pure.parts
            or any("\n" in part or "\t" in part for part in pure.parts)
            or pure.parts[0] in (".jj", ".git")
        ):
            raise JjCacheError("unsafe tracked path {!r}".format(path))
        if file_type not in ("file", "symlink"):
            raise JjCacheError(
                "unsupported tracked entry {} ({})".format(path, file_type)
            )
        entries.append(TreeEntry(path, file_type, executable == "1"))
    if not entries or len({entry.path for entry in entries}) != len(entries):
        raise JjCacheError("Jujutsu tree is empty or has duplicate paths")
    return tuple(entries)


def _file_bytes(repo: Path, revision: str, path: str) -> bytes:
    return _run_jj(
        Path(repo).resolve(),
        ["file", "show", "-r", revision, "--", path],
    )


def preflight_revision(
    repo: Path,
    revision: str,
    *,
    exclude_prefixes=("experiments", "misc", "baselines", "paper"),
) -> tuple[TreeEntry, ...]:
    """Fail before export/build if the pinned Jj tree cannot be materialized."""
    repo = Path(repo).resolve()
    resolve_pinned_commit(repo, revision)
    excluded = tuple(PurePosixPath(prefix) for prefix in exclude_prefixes)
    included = tuple(
        entry
        for entry in list_tree(repo, revision)
        if not any(
            PurePosixPath(entry.path) == prefix
            or prefix in PurePosixPath(entry.path).parents
            for prefix in excluded
        )
    )
    symlinks = [entry.path for entry in included if entry.file_type == "symlink"]
    if symlinks:
        raise JjCacheError(
            "unexcluded symlink cannot be exported by jj file show: {}".format(
                symlinks[0]
            )
        )
    required = ("build.py", "fast-downward.py", "src/CMakeLists.txt")
    paths = {entry.path for entry in included}
    missing = [path for path in required if path not in paths]
    if missing:
        raise JjCacheError(
            "pinned planner tree lacks required build source: {}".format(missing[0])
        )
    # Exercise the exact Jj content path on small required files before a
    # cache directory is created or the full export begins.
    for path in required:
        if not _file_bytes(repo, revision, path):
            raise JjCacheError("pinned planner source is empty: {}".format(path))
    resolve_pinned_commit(repo, revision)
    return included


def export_revision(
    repo: Path,
    revision: str,
    destination: Path,
    *,
    exclude_prefixes=("experiments", "misc", "baselines", "paper"),
) -> str:
    """Export *revision* to a new directory and return its manifest digest."""
    repo = Path(repo).resolve()
    destination = Path(destination).resolve()
    entries = preflight_revision(
        repo,
        revision,
        exclude_prefixes=exclude_prefixes,
    )
    if destination.exists():
        raise JjCacheError("export destination already exists: {}".format(destination))
    destination.mkdir(parents=True)
    manifest = []
    try:
        for entry in entries:
            pure = PurePosixPath(entry.path)
            content = _file_bytes(repo, revision, entry.path)
            target = destination.joinpath(*pure.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            if entry.file_type == "file":
                with target.open("xb") as stream:
                    stream.write(content)
                target.chmod(0o755 if entry.executable else 0o644)
            manifest.append(
                {
                    "path": entry.path,
                    "type": entry.file_type,
                    "executable": entry.executable,
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        resolve_pinned_commit(repo, revision)
    except Exception:
        shutil.rmtree(destination)
        raise
    raw = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class JjCachedFastDownwardRevision:
    """The small CachedRevision interface used by Downward Lab 8.0."""

    def __init__(
        self,
        revision_cache: Path,
        repo: Path,
        revision: str,
        build_options: list[str],
    ):
        self.revision_cache = Path(revision_cache).resolve()
        self.repo = Path(repo).resolve()
        self.local_rev = resolve_pinned_commit(self.repo, revision)
        self.global_rev = self.local_rev
        self.build_options = list(build_options)
        identity = json.dumps(
            {
                "protocol": EXPORT_PROTOCOL,
                "revision": revision,
                "build": self.build_options,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        suffix = hashlib.sha256(identity).hexdigest()[:12]
        self.name = "{}_{}".format(revision[:16], suffix)
        self.path = self.revision_cache / self.name

    def __eq__(self, other) -> bool:
        return isinstance(other, JjCachedFastDownwardRevision) and self.name == other.name

    def __hash__(self) -> int:
        return hash(self.name)

    def get_relative_exp_path(self, relpath="") -> str:
        return os.path.join("code-{}".format(self.name), relpath)

    def _sentinel(self) -> Path:
        return self.path / "build_successful"

    def cache(self) -> None:
        self.revision_cache.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            if not self._sentinel().is_file():
                raise JjCacheError("existing revision cache lacks its sentinel")
            # Some third-party build systems regenerate tracked Autotools
            # inputs in place.  Normalize those generated changes back to the
            # pinned commit before accepting or reusing an existing cache.
            self._read_sentinel(self.path, verify_binaries=True)
            self._restore_source_tree(self.path)
            self.attest()
            return
        temporary = Path(
            tempfile.mkdtemp(prefix=".{}-".format(self.name), dir=self.revision_cache)
        )
        source = temporary / "source"
        try:
            manifest_digest = export_revision(self.repo, self.local_rev, source)
            command = ["./build.py", *self.build_options]
            subprocess.run(command, cwd=source, check=True)
            binary = source / "builds" / "release_no_lp" / "bin" / "downward"
            preprocess = source / "builds" / "release_no_lp" / "bin" / "preprocess"
            if not binary.is_file() or not preprocess.is_file():
                raise JjCacheError("release_no_lp build did not create both binaries")
            self._restore_source_tree(source)
            sentinel = {
                "protocol": EXPORT_PROTOCOL,
                "revision": self.local_rev,
                "tree_manifest_sha256": manifest_digest,
                "build_options": self.build_options,
                "downward_sha256": sha256_file(binary),
                "preprocess_sha256": sha256_file(preprocess),
            }
            self._sentinel_for(source).write_text(
                json.dumps(sentinel, sort_keys=True, separators=(",", ":")) + "\n",
                encoding="ascii",
            )
            os.replace(source, self.path)
        except Exception:
            if self.path.exists() and not self._sentinel().exists():
                shutil.rmtree(self.path)
            raise
        finally:
            shutil.rmtree(temporary, ignore_errors=True)

    @staticmethod
    def _sentinel_for(source: Path) -> Path:
        return source / "build_successful"

    def _source_tree_digest(self, root: Path) -> str:
        root = Path(root).resolve()
        entries = preflight_revision(self.repo, self.local_rev)
        manifest = []
        for entry in entries:
            target = root.joinpath(*PurePosixPath(entry.path).parts)
            try:
                info = target.lstat()
            except OSError as err:
                raise JjCacheError(
                    "cached source tree is incomplete: {}".format(entry.path)
                ) from err
            if not stat.S_ISREG(info.st_mode) or target.is_symlink():
                raise JjCacheError(
                    "cached source has the wrong type: {}".format(entry.path)
                )
            executable = bool(info.st_mode & 0o111)
            if executable != entry.executable:
                raise JjCacheError(
                    "cached source mode changed: {}".format(entry.path)
                )
            try:
                payload_hash = sha256_file(target)
            except OSError as err:
                raise JjCacheError(
                    "cannot hash cached source: {}".format(entry.path)
                ) from err
            manifest.append({
                "path": entry.path,
                "type": entry.file_type,
                "executable": entry.executable,
                "sha256": payload_hash,
            })
        raw = json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        return hashlib.sha256(raw).hexdigest()

    def _restore_source_tree(self, root: Path) -> None:
        """Atomically restore every tracked source file from the pinned commit."""
        root = Path(root).resolve()
        for entry in preflight_revision(self.repo, self.local_rev):
            target = root.joinpath(*PurePosixPath(entry.path).parts)
            try:
                target.parent.resolve().relative_to(root)
            except (OSError, ValueError) as err:
                raise JjCacheError(
                    "cached source parent escapes: {}".format(entry.path)
                ) from err
            if target.parent.is_symlink():
                raise JjCacheError(
                    "cached source parent is a symlink: {}".format(entry.path)
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            payload = _file_bytes(self.repo, self.local_rev, entry.path)
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".jj-restore-", dir=target.parent
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(payload)
                    stream.flush()
                    os.fsync(stream.fileno())
                temporary.chmod(0o755 if entry.executable else 0o644)
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)

    def _read_sentinel(self, path: Path, *, verify_binaries: bool) -> dict:
        path = Path(path).resolve()
        try:
            raw = self._sentinel_for(path).read_text(encoding="ascii")
            value = json.loads(raw)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
            raise JjCacheError("cannot read revision-cache sentinel") from err
        expected = {
            "protocol": EXPORT_PROTOCOL,
            "revision": self.local_rev,
            "build_options": self.build_options,
        }
        if (
            not isinstance(value, dict)
            or set(value) != {
                *expected,
                "tree_manifest_sha256",
                "downward_sha256",
                "preprocess_sha256",
            }
            or any(value.get(key) != expected_value
                   for key, expected_value in expected.items())
            or any(
                re.fullmatch(r"[0-9a-f]{64}", value.get(field, "")) is None
                for field in (
                    "tree_manifest_sha256",
                    "downward_sha256",
                    "preprocess_sha256",
                )
            )
        ):
            raise JjCacheError("revision-cache sentinel identity changed")
        if verify_binaries:
            binary = path / "builds" / "release_no_lp" / "bin" / "downward"
            preprocess = path / "builds" / "release_no_lp" / "bin" / "preprocess"
            try:
                binary_hash = sha256_file(binary)
                preprocess_hash = sha256_file(preprocess)
            except OSError as err:
                raise JjCacheError("cannot hash revision-cache binaries") from err
            if (
                value["downward_sha256"] != binary_hash
                or value["preprocess_sha256"] != preprocess_hash
            ):
                raise JjCacheError("revision-cache binaries fail hash attestation")
        return value

    def attest_path(self, path: Path) -> dict:
        path = Path(path).resolve()
        value = self._read_sentinel(path, verify_binaries=True)
        if value.get("tree_manifest_sha256") != self._source_tree_digest(path):
            raise JjCacheError("revision-cache source tree fails hash attestation")
        return value

    def attest(self) -> dict:
        return self.attest_path(self.path)
