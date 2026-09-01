#!/usr/bin/env python3
"""Campaign-local hardened Slurm and immutable-run transport primitives."""

from __future__ import annotations

import hashlib
import ctypes
import os
import shlex
import stat
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_protocol as P


class TransportError(RuntimeError):
    pass


def scheduler_contract(freeze: dict, account: str) -> dict:
    return {
        "array_spec": "1-300", "array_tasks": 300, "array_throttle": 0,
        "runs_per_array_task": 3, "partition": "fat", "qos": "normal",
        "nodes": 1, "ntasks": 1, "cpus_per_task": 1,
        "time_limit": freeze["design"]["scheduler_time_limit"],
        "memory_per_cpu": freeze["design"]["scheduler_memory"],
        "account": account, "requeue": False,
        "sbatch_requeue_option": "--no-requeue",
    }


def validate_scheduler_contract(contract: dict, freeze: dict, account: str) -> None:
    expected = scheduler_contract(freeze, account)
    if (
        not isinstance(contract, dict)
        or P.canonical_json(contract) != P.canonical_json(expected)
        or "%" in contract.get("array_spec", "%")
    ):
        raise TransportError("scheduler contract is not 300 no-requeue triads")


def _required_directives(contract: dict) -> set[str]:
    return {
        "#SBATCH --array={}".format(contract["array_spec"]),
        "#SBATCH --partition={}".format(contract["partition"]),
        "#SBATCH --qos={}".format(contract["qos"]),
        "#SBATCH --time={}".format(contract["time_limit"]),
        "#SBATCH --mem-per-cpu={}".format(contract["memory_per_cpu"]),
        "#SBATCH --nodes={}".format(contract["nodes"]),
        "#SBATCH --ntasks={}".format(contract["ntasks"]),
        "#SBATCH --cpus-per-task={}".format(contract["cpus_per_task"]),
        "#SBATCH --account={}".format(contract["account"]),
        "#SBATCH --no-requeue",
    }


_OPTIONAL_DIRECTIVES = {
    "job-name": lambda value: bool(value),
    "output": lambda value: bool(value),
    "error": lambda value: bool(value),
    "open-mode": lambda value: value == "append",
    "nice": lambda value: value == "0",
    "mail-type": lambda value: value == "NONE",
    "mail-user": lambda value: value == "",
}


def _parse_sbatch_directive(line: str) -> tuple[str, str | None]:
    stripped = line.lstrip()
    if not stripped.startswith("#SBATCH"):
        raise TransportError("not an SBATCH directive")
    suffix = stripped[len("#SBATCH"):]
    if not suffix or not suffix[0].isspace():
        raise TransportError("malformed SBATCH directive")
    try:
        tokens = shlex.split(suffix, posix=True)
    except ValueError as err:
        raise TransportError("malformed SBATCH directive") from err
    if not tokens:
        raise TransportError("empty SBATCH directive")
    if any(token.startswith("-") and not token.startswith("--") for token in tokens):
        raise TransportError("short SBATCH aliases are forbidden")
    if len(tokens) != 1 or not tokens[0].startswith("--"):
        raise TransportError("SBATCH directives must use one long equals token")
    option = tokens[0][2:]
    if option == "no-requeue":
        return option, None
    if option == "requeue":
        raise TransportError("Slurm requeue policy changed")
    if "=" not in option:
        raise TransportError("SBATCH value must use canonical equals syntax")
    name, value = option.split("=", 1)
    if not name:
        raise TransportError("malformed SBATCH option")
    return name, value


def validate_job_bytes(raw: bytes, contract: dict) -> str:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as err:
        raise TransportError("Slurm job is not ASCII") from err
    if not text.endswith("\n") or "\r" in text:
        raise TransportError("Slurm job text framing changed")
    lines = text.splitlines()
    required = _required_directives(contract)
    canonical_by_name = {}
    for directive in required:
        name, _ = _parse_sbatch_directive(directive)
        canonical_by_name[name] = directive
    seen = {}
    in_preamble = True
    for number, line in enumerate(lines):
        stripped = line.lstrip()
        is_directive = stripped.startswith("#SBATCH")
        if in_preamble and number == 0 and line.startswith("#!"):
            continue
        if in_preamble and not is_directive and (
            not stripped or stripped.startswith("#")
        ):
            continue
        if in_preamble and not is_directive:
            in_preamble = False
        if not in_preamble:
            if is_directive:
                raise TransportError("SBATCH directive appears after executable body")
            continue
        name, value = _parse_sbatch_directive(line)
        if name in seen:
            raise TransportError("duplicate SBATCH directive: {}".format(name))
        seen[name] = line
        if name in canonical_by_name:
            if line != canonical_by_name[name]:
                raise TransportError("Slurm directive conflicts: {}".format(name))
        elif name in _OPTIONAL_DIRECTIVES:
            if value is None or not _OPTIONAL_DIRECTIVES[name](value) or line != (
                "#SBATCH --{}={}".format(name, value)
            ):
                raise TransportError("noncanonical SBATCH directive: {}".format(name))
        else:
            raise TransportError("unknown SBATCH directive: {}".format(name))
    if set(canonical_by_name) - set(seen):
        raise TransportError("Slurm job lacks a frozen directive")
    if "%" in contract["array_spec"] or seen.get("array") != (
        "#SBATCH --array={}".format(contract["array_spec"])
    ):
        raise TransportError("Slurm array mapping changed")
    return text


def validate_job_file(path: Path, *, expected: Path, contract: dict) -> str:
    try:
        loaded = CampaignIO.read_regular_exact(path, expected=expected, label="Slurm job")
    except CampaignIO.CampaignIOError as err:
        raise TransportError(str(err)) from err
    return validate_job_bytes(loaded.raw, contract)


def install_no_requeue_header() -> None:
    """Make Lab generate the frozen singleton/no-requeue resource header."""
    from lab.environments import SlurmEnvironment

    original = SlurmEnvironment._get_job_header
    if getattr(original, "_metric_choice_no_requeue", False):
        return

    def hardened(self, step, is_last):
        header = original(self, step, is_last)
        names = []
        for line in header.splitlines():
            if line.lstrip().startswith("#SBATCH"):
                name, _ = _parse_sbatch_directive(line)
                names.append(name)
        if len(names) != len(set(names)):
            raise TransportError("Lab emitted duplicate directives")
        additions = []
        for name, directive in (
            ("nodes", "#SBATCH --nodes=1"),
            ("ntasks", "#SBATCH --ntasks=1"),
            ("no-requeue", "#SBATCH --no-requeue"),
        ):
            if name not in names:
                additions.append(directive)
        suffix = "" if header.endswith("\n") else "\n"
        return header + suffix + "\n".join(additions) + ("\n" if additions else "")

    hardened._metric_choice_no_requeue = True
    SlurmEnvironment._get_job_header = hardened


def immutable_tree_manifest(
    root: Path, expected_relatives: list[str], *, label: str,
) -> dict:
    """Hash an exact regular-file set without following any component link."""
    if not isinstance(expected_relatives, list) or (
        expected_relatives != sorted(set(expected_relatives))
    ):
        raise TransportError("{} expected file set changed".format(label))
    rows = []
    for spelling in expected_relatives:
        relative = Path(spelling)
        if (
            relative.is_absolute() or relative.as_posix() != spelling
            or ".." in relative.parts or not relative.parts
        ):
            raise TransportError("{} relative path changed".format(label))
        path = Path(root) / relative
        try:
            loaded = SafeIO.read_regular_file(
                path, label=label, expected_path=path, root=Path(root)
            )
        except SafeIO.SafeReadError as err:
            raise TransportError(str(err)) from err
        rows.append({
            "path": spelling, "sha256": loaded.sha256,
            "size": loaded.identity["size"],
        })
    payload = b"".join(
        row["path"].encode("ascii") + b"\0" + bytes.fromhex(row["sha256"])
        for row in rows
    )
    return {
        "files": rows, "file_count": len(rows),
        "tree_sha256": hashlib.sha256(payload).hexdigest(),
    }


def validate_exact_directory(
    path: Path, expected_names: set[str], *, expected: Path, root: Path,
    label: str,
) -> None:
    try:
        SafeIO.validate_lexical_path(
            path, label=label, expected_path=expected, root=root
        )
        descriptor = CampaignIO._open_directory(path, label=label)
        names = set(os.listdir(descriptor))
    except (SafeIO.SafeReadError, CampaignIO.CampaignIOError, OSError) as err:
        raise TransportError("cannot inspect {} directory".format(label)) from err
    finally:
        if "descriptor" in locals():
            os.close(descriptor)
    if names != expected_names:
        raise TransportError("{} directory entries changed".format(label))


def verify_manifest_rescan(
    root: Path, expected_relatives: list[str], sealed: dict, *, label: str,
) -> dict:
    current = immutable_tree_manifest(root, expected_relatives, label=label)
    if current != sealed:
        raise TransportError("{} changed on rescan".format(label))
    return current


def validate_materialization_source(
    path: Path, *, expected: Path, root: Path, sha256: str, label: str,
) -> bytes:
    try:
        loaded = SafeIO.read_regular_file(
            path, label=label, expected_path=expected, root=root
        )
    except SafeIO.SafeReadError as err:
        raise TransportError(str(err)) from err
    if loaded.sha256 != sha256:
        raise TransportError("{} digest changed".format(label))
    return loaded.raw


def materialize_absent_regular(
    source: Path, destination: Path, *, expected_source: Path,
    expected_destination: Path, source_root: Path, destination_root: Path,
    sha256: str, label: str,
) -> None:
    payload = validate_materialization_source(
        source, expected=expected_source, root=source_root,
        sha256=sha256, label=label,
    )
    try:
        CampaignIO.write_exclusive_exact(
            destination, payload, expected=expected_destination,
            root=destination_root, label=label,
        )
        verified = SafeIO.read_regular_file(
            destination, label=label, expected_path=expected_destination,
            root=destination_root,
        )
    except (CampaignIO.CampaignIOError, SafeIO.SafeReadError) as err:
        raise TransportError(str(err)) from err
    if verified.sha256 != sha256:
        raise TransportError("{} materialization changed".format(label))


def _entry_fingerprint(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
        info.st_uid, info.st_gid, info.st_size, info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _directory_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid)


def _archive_identity(info: os.stat_result) -> tuple[int, ...]:
    return (info.st_dev, info.st_ino, info.st_mode, info.st_size, info.st_mtime_ns)


@contextmanager
def _stable_directory(
    path: Path, *, expected: Path, root: Path, label: str,
):
    """Retain and revalidate every directory descriptor below a trust root."""
    try:
        candidate = SafeIO.validate_lexical_path(
            path, label=label, expected_path=expected, root=root
        )
        relative = candidate.relative_to(root)
    except (SafeIO.SafeReadError, ValueError) as err:
        raise TransportError(str(err)) from err
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors = []
    entries = []
    body_error = None
    try:
        root_before = os.lstat(root)
        root_fd = os.open(root, flags)
        descriptors.append(root_fd)
        root_opened = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_opened.st_mode)
            or _directory_identity(root_before) != _directory_identity(root_opened)
        ):
            raise TransportError("{} root identity changed".format(label))
        parent_fd = root_fd
        for component in relative.parts:
            before = os.stat(component, dir_fd=parent_fd, follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode):
                raise TransportError("{} ancestor is not a directory".format(label))
            child_fd = os.open(component, flags, dir_fd=parent_fd)
            descriptors.append(child_fd)
            opened = os.fstat(child_fd)
            if _directory_identity(before) != _directory_identity(opened):
                raise TransportError("{} ancestor identity changed".format(label))
            entries.append((parent_fd, component, _directory_identity(opened), child_fd))
            parent_fd = child_fd
        yield parent_fd
    except (OSError, TransportError) as err:
        body_error = err
        if isinstance(err, TransportError):
            raise
        raise TransportError("cannot inspect {} safely".format(label)) from err
    finally:
        verification_error = None
        if descriptors:
            try:
                for parent_fd, component, fingerprint, child_fd in reversed(entries):
                    entry = os.stat(
                        component, dir_fd=parent_fd, follow_symlinks=False
                    )
                    if (
                        _directory_identity(entry) != fingerprint
                        or _directory_identity(os.fstat(child_fd)) != fingerprint
                    ):
                        raise TransportError(
                            "{} ancestor changed while in use".format(label)
                        )
                if (
                    _directory_identity(os.fstat(descriptors[0]))
                    != _directory_identity(root_opened)
                    or _directory_identity(os.lstat(root))
                    != _directory_identity(root_opened)
                ):
                    raise TransportError("{} root changed while in use".format(label))
            except (OSError, TransportError) as err:
                verification_error = err
        for descriptor in reversed(descriptors):
            os.close(descriptor)
        if verification_error is not None and body_error is None:
            if isinstance(verification_error, TransportError):
                raise verification_error
            raise TransportError("cannot revalidate {}".format(label)) from verification_error


def scan_regular_namespace(
    directory: Path, *, expected_directory: Path, root: Path,
    excluded_names: set[str], label: str,
) -> list[str]:
    """Return every non-static regular entry in one stable run directory."""
    if not isinstance(excluded_names, set) or any(
        not isinstance(name, str) or Path(name).name != name
        for name in excluded_names
    ):
        raise TransportError("{} excluded namespace changed".format(label))
    with _stable_directory(
        directory, expected=expected_directory, root=root, label=label
    ) as descriptor:
        try:
            names = os.listdir(descriptor)
        except OSError as err:
            raise TransportError("cannot list {}".format(label)) from err
        if len(names) != len(set(names)):
            raise TransportError("{} namespace is not unique".format(label))
        if not excluded_names <= set(names):
            raise TransportError("{} static namespace is incomplete".format(label))
        dynamic = []
        for name in names:
            if Path(name).name != name or name in ("", ".", ".."):
                raise TransportError("{} namespace spelling changed".format(label))
            info = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode):
                raise TransportError("{} contains a nonregular entry".format(label))
            if name not in excluded_names:
                dynamic.append(name)
        return sorted(dynamic)


def validate_stable_directory(
    directory: Path, *, expected_directory: Path, root: Path, label: str,
) -> None:
    with _stable_directory(
        directory, expected=expected_directory, root=root, label=label
    ):
        pass


def _read_regular_at(parent_fd: int, name: str, *, label: str) -> tuple[str, tuple[int, ...]]:
    before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise TransportError("{} source is not regular".format(label))
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(name, flags, dir_fd=parent_fd)
    try:
        opened = os.fstat(descriptor)
        if _entry_fingerprint(opened) != _entry_fingerprint(before):
            raise TransportError("{} source identity changed".format(label))
        digest = hashlib.sha256()
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
        after = os.fstat(descriptor)
        entry = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if (
            _entry_fingerprint(after) != _entry_fingerprint(opened)
            or _entry_fingerprint(entry) != _entry_fingerprint(opened)
        ):
            raise TransportError("{} source changed while reading".format(label))
        return digest.hexdigest(), _archive_identity(opened)
    finally:
        os.close(descriptor)


def open_verified_executable(
    path: Path, *, expected_path: Path, expected_sha256: str, label: str,
) -> int:
    """Return a pinned executable descriptor after exact path/hash validation."""
    candidate = Path(path)
    if (
        not candidate.is_absolute() or candidate != Path(expected_path)
        or len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise TransportError("{} binding changed".format(label))
    descriptor = None
    success = False
    try:
        with _stable_directory(
            candidate.parent, expected=candidate.parent,
            root=Path(candidate.anchor), label=label,
        ) as parent_fd:
            before = os.stat(
                candidate.name, dir_fd=parent_fd, follow_symlinks=False
            )
            if not stat.S_ISREG(before.st_mode) or not before.st_mode & 0o111:
                raise TransportError("{} is not executable".format(label))
            flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
            flags |= getattr(os, "O_NOFOLLOW", 0)
            descriptor = os.open(candidate.name, flags, dir_fd=parent_fd)
            opened = os.fstat(descriptor)
            if _entry_fingerprint(opened) != _entry_fingerprint(before):
                raise TransportError("{} identity changed".format(label))
            digest = hashlib.sha256()
            while True:
                block = os.read(descriptor, 1024 * 1024)
                if not block:
                    break
                digest.update(block)
            after_fd = os.fstat(descriptor)
            after_entry = os.stat(
                candidate.name, dir_fd=parent_fd, follow_symlinks=False
            )
            if (
                _entry_fingerprint(after_fd) != _entry_fingerprint(opened)
                or _entry_fingerprint(after_entry) != _entry_fingerprint(opened)
                or digest.hexdigest() != expected_sha256
            ):
                raise TransportError("{} identity or digest changed".format(label))
            os.lseek(descriptor, 0, os.SEEK_SET)
        success = True
        return descriptor
    except OSError as err:
        raise TransportError("cannot validate {}".format(label)) from err
    finally:
        if descriptor is not None and not success:
            os.close(descriptor)


def run_pinned_executable(
    path: Path, expected_sha256: str, arguments: list[str], *,
    environment: dict[str, str], input_bytes: bytes | None = None,
    cwd: Path | None = None, label: str,
):
    """Execute exact verified bytes with a minimal explicit environment."""
    if (
        not isinstance(arguments, list)
        or any(not isinstance(argument, str) for argument in arguments)
        or not isinstance(environment, dict)
        or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in environment.items()
        )
        or (input_bytes is not None and not isinstance(input_bytes, bytes))
    ):
        raise TransportError("{} invocation changed".format(label))
    executable_fd = open_verified_executable(
        path, expected_path=path, expected_sha256=expected_sha256, label=label,
    )
    try:
        return subprocess.run(
            [str(path), *arguments],
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            cwd=cwd,
            env=dict(environment),
            pass_fds=(executable_fd,),
            executable="/proc/self/fd/{}".format(executable_fd),
        )
    except (OSError, subprocess.SubprocessError) as err:
        raise TransportError("{} invocation failed".format(label)) from err
    finally:
        os.close(executable_fd)


def submit_pinned_stdin(
    path: Path, expected_sha256: str, options: list[str], raw: bytes, *,
    environment: dict[str, str], cwd: Path, label: str,
) -> str:
    """Submit immutable in-memory job bytes without a script path argument."""
    if (
        not isinstance(raw, bytes) or not raw
        or not isinstance(options, list)
        or any(
            not isinstance(option, str) or not option.startswith("--")
            for option in options
        )
        or options.count("--parsable") != 1
        or options.count("--export=NONE") != 1
        or options.count("--no-requeue") != 1
        or any(
            option.startswith("--export") and option != "--export=NONE"
            for option in options
        )
    ):
        raise TransportError("{} options-only submission changed".format(label))
    completed = run_pinned_executable(
        path, expected_sha256, options, environment=environment,
        input_bytes=raw, cwd=cwd, label=label,
    )
    try:
        output = completed.stdout.decode("ascii").strip()
    except (AttributeError, UnicodeDecodeError) as err:
        raise TransportError("{} returned non-ASCII output".format(label)) from err
    job_id = output.split(";", 1)[0]
    if not job_id.isdigit():
        raise TransportError("{} returned an invalid job id".format(label))
    return job_id


def _rename_exchange(parent_fd: int, left: str, right: str) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise TransportError("atomic rename exchange is unavailable")
    renameat2.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    if renameat2(
        parent_fd, left.encode("ascii"), parent_fd, right.encode("ascii"), 2
    ) != 0:
        error = ctypes.get_errno()
        raise TransportError("atomic materialization exchange failed") from OSError(
            error, os.strerror(error)
        )


def _rename_noreplace(
    source_fd: int, source: str, destination_fd: int, destination: str,
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = getattr(libc, "renameat2", None)
    if renameat2 is None:
        raise TransportError("atomic no-replace rename is unavailable")
    renameat2.argtypes = [
        ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    if renameat2(
        source_fd, source.encode("ascii"), destination_fd,
        destination.encode("ascii"), 1
    ) != 0:
        error = ctypes.get_errno()
        raise TransportError("atomic archive rename failed") from OSError(
            error, os.strerror(error)
        )


def materialize_expected_symlink(
    link: Path, source: Path, *, expected_link: Path, expected_source: Path,
    source_root: Path, run_root: Path, sha256: str, label: str,
) -> None:
    """Atomically exchange a verified Lab symlink for immutable source bytes."""
    try:
        SafeIO.validate_lexical_path(
            link, label=label, expected_path=expected_link, root=run_root
        )
        before = os.lstat(link)
        target = os.readlink(link)
    except (SafeIO.SafeReadError, OSError) as err:
        raise TransportError("cannot inspect {} symlink".format(label)) from err
    if not stat.S_ISLNK(before.st_mode):
        raise TransportError("{} is not the expected Lab symlink".format(label))
    target_path = Path(target)
    if target_path.is_absolute():
        lexical_target = target_path
    else:
        if ".." in target_path.parts:
            raise TransportError("{} symlink target is not lexical".format(label))
        lexical_target = link.parent / target_path
    if lexical_target != expected_source:
        raise TransportError("{} symlink target changed".format(label))
    payload = validate_materialization_source(
        source, expected=expected_source, root=source_root,
        sha256=sha256, label=label,
    )
    try:
        after_read = os.lstat(link)
    except OSError as err:
        raise TransportError("{} symlink disappeared".format(label)) from err
    if _entry_fingerprint(after_read) != _entry_fingerprint(before):
        raise TransportError("{} symlink changed while reading".format(label))
    temporary = link.with_name(".{}.metric-choice-materialize".format(link.name))
    try:
        CampaignIO.write_exclusive_exact(
            temporary, payload, expected=temporary, root=run_root, label=label
        )
        parent_fd = CampaignIO._open_directory(link.parent, label=label)
        try:
            _rename_exchange(parent_fd, temporary.name, link.name)
            displaced = os.stat(
                temporary.name, dir_fd=parent_fd, follow_symlinks=False
            )
            if _entry_fingerprint(displaced) != _entry_fingerprint(before):
                _rename_exchange(parent_fd, temporary.name, link.name)
                raise TransportError("{} exchange captured a changed entry".format(label))
            os.unlink(temporary.name, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)
        verified = SafeIO.read_regular_file(
            link, label=label, expected_path=expected_link, root=run_root
        )
    except (CampaignIO.CampaignIOError, SafeIO.SafeReadError, OSError) as err:
        raise TransportError("cannot materialize {} safely".format(label)) from err
    if verified.sha256 != sha256:
        raise TransportError("{} materialized bytes changed".format(label))


def archive_regular_entries(
    source_directory: Path, archive_directory: Path, names: list[str], *,
    expected_source_directory: Path, expected_archive_directory: Path,
    source_root: Path, archive_root: Path, label: str,
) -> dict:
    """Atomically archive a fixed dynamic namespace without replacing files."""
    if names != sorted(set(names)) or any(
        Path(name).name != name or name in ("", ".", "..") for name in names
    ):
        raise TransportError("{} archive namespace changed".format(label))
    try:
        SafeIO.validate_lexical_path(
            source_directory, label=label,
            expected_path=expected_source_directory, root=source_root,
        )
        SafeIO.validate_lexical_path(
            archive_directory, label=label,
            expected_path=expected_archive_directory, root=archive_root,
        )
        CampaignIO.ensure_directory(
            archive_directory.parent, root=archive_root, label=label
        )
    except (SafeIO.SafeReadError, CampaignIO.CampaignIOError) as err:
        raise TransportError(str(err)) from err
    try:
        with _stable_directory(
            archive_directory.parent, expected=archive_directory.parent,
            root=archive_root, label=label,
        ) as parent_fd:
            os.mkdir(archive_directory.name, mode=0o700, dir_fd=parent_fd)
    except FileExistsError as err:
        raise TransportError("{} archive destination exists".format(label)) from err
    except OSError as err:
        raise TransportError("cannot create {} archive".format(label)) from err
    rows = []
    with _stable_directory(
        source_directory, expected=expected_source_directory,
        root=source_root, label=label,
    ) as source_fd, _stable_directory(
        archive_directory, expected=expected_archive_directory,
        root=archive_root, label=label,
    ) as archive_fd:
        for name in names:
            try:
                digest, fingerprint = _read_regular_at(
                    source_fd, name, label=label
                )
            except (OSError, TransportError) as err:
                raise TransportError(str(err)) from err
            _rename_noreplace(source_fd, name, archive_fd, name)
            try:
                archived = os.stat(
                    name, dir_fd=archive_fd, follow_symlinks=False
                )
            except FileNotFoundError as err:
                raise TransportError("{} archive entry disappeared".format(label)) from err
            if _archive_identity(archived) != fingerprint:
                raise TransportError("{} archive identity changed".format(label))
            try:
                os.stat(name, dir_fd=source_fd, follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise TransportError("{} source survived archive".format(label))
            rows.append({"name": name, "sha256": digest})
    return {
        "entries": rows,
        "entries_sha256": hashlib.sha256(
            b"".join(
                row["name"].encode("ascii") + b"\0"
                + bytes.fromhex(row["sha256"]) for row in rows
            )
        ).hexdigest(),
    }
