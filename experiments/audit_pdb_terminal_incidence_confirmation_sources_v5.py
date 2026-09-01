#!/usr/bin/env python3
"""Run full source-audit campaign v5 with project-backed temporary files."""

from __future__ import annotations

import importlib.util
import hashlib
import os
import re
import stat
import sys
import tempfile
import types
from pathlib import Path


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import pdb_terminal_incidence_confirmation_safe_io_v5 as SafeIO

BASE_SOURCE = SCRIPT_DIR / "audit_pdb_terminal_incidence_confirmation_sources.py"
_MODULE_NAME = "_pdb_terminal_incidence_confirmation_source_audit_v5_base"


def _load_base():
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, BASE_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen source-audit implementation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


Base = _load_base()

CAMPAIGN = "v5"
TASK_TIMEOUT_SECONDS = 28800
DEFAULT_SHARDS = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v5"
)
DEFAULT_INVENTORY = DEFAULT_SHARDS / "source-inventory-v5.json"
DEFAULT_OUTPUT = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v5.json"
)
DEFAULT_CODE_MANIFEST = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v5_code.sha256"
)
TMP_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v5_tmp"
)
TMPDIR_TEMPLATE = str(TMP_ROOT / "task-{array_job_id}-{array_task_id}")
PYTHON_CACHE_PREFIX_TEMPLATE = TMPDIR_TEMPLATE + "/pycache"
TASK_ENVIRONMENT_SCHEMA = Base.SCHEMA + "/campaign-v5/task-environment/v1"
SOURCE_SNAPSHOT_SCHEMA = Base.SCHEMA + "/campaign-v5/source-snapshot/v1"
SOURCE_SNAPSHOT_POLICY = {
    "scope": "one domain/problem snapshot tree per candidate",
    "location": "inside the exact per-array-task TMPDIR",
    "directory_mode": "0700",
    "file_mode": "0400",
    "consumers": ["translator", "axiom_based normalization"],
    "verify_before_each_consumer": True,
    "verify_identity_and_sha256_after_use": True,
    "cleanup": "unlink exact files, then rmdir exact directories; no recursion",
}
SHA256SUM_COMMAND = Path("/usr/bin/sha256sum")
SHA256SUM_SHA256 = (
    "1950eda10a1bb0c6c2a086ba009b847edec6f30d25eb311b9154ae08819041a9"
)
MKDIR_COMMAND = Path("/usr/bin/mkdir")
MKDIR_SHA256 = (
    "9a71255933f2013dda3fe7e8ad928dc50b7e4c2ae6a7cac58fc1225106c10814"
)
RMDIR_COMMAND = Path("/usr/bin/rmdir")
RMDIR_SHA256 = (
    "b87fd3112c40dd30dca11fa5bc1b3dacc9ed2e309868344dd696824abafc5ded"
)
V4_DIAGNOSTIC = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v5" /
    "v4-infrastructure-failure-diagnostic.json"
)
V4_CODE_MANIFEST = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256"
)
V4_CODE_MANIFEST_SHA256 = (
    "d3b571aaffce9f58f09d15f118df57997773c522e3da74bcdcbfbc00299f0518"
)


def _v4_manifest_paths() -> tuple[str, ...]:
    """Load the complete immutable v4 producer boundary without outcomes."""
    try:
        loaded = SafeIO.read_regular_file(
            V4_CODE_MANIFEST,
            label="frozen v4 code manifest",
            expected_path=V4_CODE_MANIFEST,
            root=REPO,
        )
        raw = loaded.raw
        lines = raw.decode("ascii").splitlines()
    except (SafeIO.SafeReadError, UnicodeDecodeError) as err:
        raise RuntimeError("cannot read frozen v4 code manifest") from err
    if loaded.sha256 != V4_CODE_MANIFEST_SHA256:
        raise RuntimeError("frozen v4 code manifest changed")
    paths = []
    for line in lines:
        match = re.fullmatch(r"[0-9a-f]{64}  ([!-~]+)", line)
        if match is None:
            raise RuntimeError("frozen v4 code manifest is malformed")
        paths.append(match.group(1))
    if len(paths) != 24 or len(paths) != len(set(paths)):
        raise RuntimeError("frozen v4 code manifest path set changed")
    return tuple(paths)

# Bind every file named by the immutable v4 code manifest, then bind the v4
# manifest/Slurm/launch boundary and all new v5 producer bytes.  This matters
# because the v5 launcher deliberately reuses already-audited generic helpers
# from v4; merely hashing the outer v4 manifest would not check those transitive
# runtime dependencies.  The manifest-bound terminal diagnostic contains the
# exact cancellation-artifact hashes when cancellation occurred; optional
# artifacts are deliberately absent from this static set so natural completion
# does not require fabricating a cancellation record.
CODE_MANIFEST_FILES = tuple(sorted({
    *_v4_manifest_paths(),
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
    "source-audit-launch-intent-v4.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v4/"
    "source-audit-launch-receipt-v4.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v5/"
    "v4-infrastructure-failure-diagnostic.json",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v5.py",
    "experiments/cancel_pdb_terminal_incidence_confirmation_source_audit_v4_v5.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v4_cancellation_v5_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v5_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v5.py",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v4.slurm",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit_v5.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v5.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v4_cancellation_v5.py",
}))


for _name, _value in {
    "TASK_TIMEOUT_SECONDS": TASK_TIMEOUT_SECONDS,
    "DEFAULT_SHARDS": DEFAULT_SHARDS,
    "DEFAULT_INVENTORY": DEFAULT_INVENTORY,
    "DEFAULT_OUTPUT": DEFAULT_OUTPUT,
    "DEFAULT_CODE_MANIFEST": DEFAULT_CODE_MANIFEST,
    "PYTHON_CACHE_PREFIX_TEMPLATE": PYTHON_CACHE_PREFIX_TEMPLATE,
    "CODE_MANIFEST_FILES": CODE_MANIFEST_FILES,
}.items():
    setattr(Base, _name, _value)


SourceAuditError = Base.SourceAuditError
InfrastructureAuditError = Base.InfrastructureAuditError


def _safe_file(
    path: Path,
    label: str,
    *,
    expected_path: Path | None = None,
    root: Path | None = None,
    read_callback=None,
) -> SafeIO.RegularFile:
    try:
        return SafeIO.read_regular_file(
            Path(path),
            label=label,
            expected_path=expected_path,
            root=root,
            read_callback=read_callback,
        )
    except SafeIO.SafeReadError as err:
        raise SourceAuditError(str(err)) from err


def _safe_directory(
    path: Path,
    label: str,
    *,
    expected_path: Path | None = None,
    root: Path | None = None,
) -> SafeIO.Directory:
    try:
        return SafeIO.inspect_directory(
            Path(path),
            label=label,
            expected_path=expected_path,
            root=root,
        )
    except SafeIO.SafeReadError as err:
        raise SourceAuditError(str(err)) from err


def sha256_file(path: Path) -> str:
    return _safe_file(Path(path), str(path)).sha256


def _load_canonical_json(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        loaded, value = SafeIO.read_canonical_json(
            Path(path),
            label=label,
            canonical_json_line=Base.canonical_json,
        )
    except SafeIO.SafeReadError as err:
        raise SourceAuditError(str(err)) from err
    return loaded.raw, value


# Every inherited source/manifest/shard reader resolves these names at call
# time.  Replace them before the frozen engine is invoked; no v5 path is ever
# consumed by the older pathname-based implementations.
Base.sha256_file = sha256_file
Base._load_canonical_json = _load_canonical_json


def _safe_recursive_regular_tree(
    root: Path, *, read_callback=None
) -> SafeIO.RegularTree:
    """Read a tree while retaining and revalidating all directory FDs."""
    try:
        return SafeIO.read_regular_tree(
            Path(root),
            label="source tree",
            expected_path=Path(root),
            read_callback=read_callback,
        )
    except SafeIO.SafeReadError as err:
        raise SourceAuditError(str(err)) from err


def translator_source_digest(*, tree_callback=None) -> str:
    tree_root = REPO / "src" / "translate"
    tree = _safe_recursive_regular_tree(
        tree_root, read_callback=tree_callback
    )
    files = tuple(
        item for item in tree.files if Path(item.path).suffix == ".py"
    )
    if len(files) != Base.TRANSLATOR_FILE_COUNT:
        raise SourceAuditError("translator source file set changed")
    digest = hashlib.sha256()
    for item in files:
        path = tree_root / item.path
        relative = path.relative_to(REPO).as_posix()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(item.raw)).encode("ascii"))
        digest.update(b"\0")
        digest.update(item.raw)
        digest.update(b"\0")
    value = digest.hexdigest()
    if value != Base.TRANSLATOR_SOURCE_SHA256:
        raise SourceAuditError("translator source tree changed")
    return value


def _environment_attestation(
    requirements_path: Path, *, verify_installed_files: bool
) -> dict:
    loaded_requirements = _safe_file(
        requirements_path,
        "environment requirements",
        expected_path=requirements_path,
        root=REPO,
    )
    try:
        lines = loaded_requirements.raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise SourceAuditError("cannot read environment requirements") from err
    requirements = {}
    for line in lines:
        if not line or line.startswith("#") or line.count("==") != 1:
            raise SourceAuditError("environment requirement is not exact")
        name, version = line.split("==")
        if not name or not version or name in requirements:
            raise SourceAuditError("environment requirements are malformed")
        requirements[name] = version
    manifest = []
    versions = {}
    for name, expected in sorted(requirements.items()):
        try:
            distribution = Base.importlib.metadata.distribution(name)
        except Base.importlib.metadata.PackageNotFoundError as err:
            raise SourceAuditError(
                "required Python distribution is absent: {}".format(name)
            ) from err
        if distribution.version != expected or not distribution.files:
            raise SourceAuditError("Python distribution changed: {}".format(name))
        versions[name] = distribution.version
        if verify_installed_files:
            for relative in sorted(distribution.files, key=str):
                path = Path(distribution.locate_file(relative))
                item = _safe_file(path, "installed distribution file")
                manifest.append({
                    "distribution": name,
                    "path": str(relative),
                    "sha256": item.sha256,
                })
    if verify_installed_files:
        raw = Base.json.dumps(
            manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True
        ).encode("ascii")
        environment_sha256 = hashlib.sha256(raw).hexdigest()
        if environment_sha256 != Base.PINNED_PYTHON_ENVIRONMENT_SHA256:
            raise SourceAuditError("installed Python environment changed")
    else:
        environment_sha256 = Base.PINNED_PYTHON_ENVIRONMENT_SHA256
    executable = Path(Base.PINNED_PYTHON_EXECUTABLE)
    executable_sha256 = _safe_file(
        executable, "pinned Python executable", expected_path=executable
    ).sha256
    value = {
        "python_version": ".".join(map(str, sys.version_info[:3])),
        "python_executable": str(executable),
        "python_executable_sha256": executable_sha256,
        "python_environment_sha256": environment_sha256,
        "python_distributions": versions,
        "python_requirements_sha256": loaded_requirements.sha256,
    }
    if (
        value["python_version"] != Base.PINNED_PYTHON_VERSION
        or getattr(sys, "_base_executable", None) != str(executable)
        or executable_sha256 != Base.PINNED_PYTHON_EXECUTABLE_SHA256
        or loaded_requirements.sha256 != Base.PINNED_REQUIREMENTS_SHA256
    ):
        raise SourceAuditError("pinned Python environment changed")
    return value


def validate_code_manifest(
    path: Path,
    expected_sha256: str,
    *,
    verify_environment_files: bool = True,
) -> dict:
    loaded = _safe_file(
        path, "source-audit code manifest", expected_path=path, root=REPO
    )
    try:
        lines = loaded.raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise SourceAuditError("cannot read source-audit code manifest") from err
    if not Base._is_sha256(expected_sha256) or loaded.sha256 != expected_sha256:
        raise SourceAuditError("source-audit code manifest hash changed")
    records = {}
    for line in lines:
        fields = line.split("  ", 1)
        if (
            len(fields) != 2
            or not Base._is_sha256(fields[0])
            or not fields[1]
            or fields[1] in records
        ):
            raise SourceAuditError("source-audit code manifest is malformed")
        records[fields[1]] = fields[0]
    if tuple(sorted(records)) != tuple(sorted(CODE_MANIFEST_FILES)):
        raise SourceAuditError("source-audit code manifest file set changed")
    for relative, expected in records.items():
        relative_path = Path(relative)
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise SourceAuditError("source-audit dependency path changed")
        dependency = _safe_file(
            REPO / relative_path,
            "source-audit dependency",
            expected_path=REPO / relative_path,
            root=REPO,
        )
        if dependency.sha256 != expected:
            raise SourceAuditError("source-audit dependency bytes changed")
    return {
        "code_manifest_sha256": expected_sha256,
        **_environment_attestation(
            Base.REQUIREMENTS,
            verify_installed_files=verify_environment_files,
        ),
    }


def load_inventory_manifest(
    path: Path, expected_sha256: str
) -> tuple[str, list[dict]]:
    raw, value = _load_canonical_json(path, "source inventory")
    digest = hashlib.sha256(raw).hexdigest()
    if not Base._is_sha256(expected_sha256) or digest != expected_sha256:
        raise SourceAuditError("source inventory file hash changed")
    return digest, Base.validate_inventory_manifest(value)


class _SafeSasReader(Base.SasReader):
    def __init__(self, path: Path):
        loaded = _safe_file(path, "serialized SAS", expected_path=path)
        try:
            self.lines = loaded.raw.decode("utf-8").splitlines()
        except UnicodeDecodeError as err:
            raise SourceAuditError("cannot read serialized SAS") from err
        self.path = path
        self.index = 0


Base.translator_source_digest = translator_source_digest
Base._environment_attestation = _environment_attestation
Base.validate_code_manifest = validate_code_manifest
Base.load_inventory_manifest = load_inventory_manifest
Base.SasReader = _SafeSasReader


def _inventory_safe_file(path: Path, label: str, *, root: Path | None = None):
    try:
        return SafeIO.read_regular_file(
            Path(path), label=label, expected_path=Path(path), root=root
        )
    except SafeIO.SafeReadError as err:
        raise Base.Inventory.InventoryError(str(err)) from err


def _inventory_sha256_file(path: Path) -> str:
    return _inventory_safe_file(Path(path), "inventory input").sha256


def _inventory_validate_benchmark_checkout(benchmarks: Path) -> Path:
    root = Path(benchmarks)
    if not root.is_absolute() or root != Path(os.path.normpath(root)):
        raise Base.Inventory.InventoryError("benchmark root path changed")
    try:
        SafeIO.inspect_directory(
            root, label="benchmark root", expected_path=root
        )
    except SafeIO.SafeReadError as err:
        raise Base.Inventory.InventoryError(str(err)) from err
    revision, top_level, status_text = Base.Inventory._repository_state(root)
    if revision != Base.Inventory.BENCHMARK_REVISION:
        raise Base.Inventory.InventoryError(
            "benchmark checkout is at the wrong revision"
        )
    if top_level != str(root):
        raise Base.Inventory.InventoryError(
            "benchmark root is not the checkout top level"
        )
    if status_text:
        raise Base.Inventory.InventoryError("benchmark checkout is dirty")
    return root


def _inventory_top_level_directories(root: Path) -> tuple[str, ...]:
    try:
        listing = SafeIO.inspect_directory(
            root, label="benchmark root", expected_path=root
        )
        directories = []
        for name in listing.entries:
            child = root / name
            try:
                SafeIO.inspect_directory(
                    child,
                    label="benchmark top-level directory",
                    expected_path=child,
                    root=root,
                )
            except SafeIO.SafeReadError:
                # Non-directories are allowed at checkout top level, but they
                # must themselves be stable regular files rather than links or
                # special files.
                SafeIO.read_regular_file(
                    child,
                    label="benchmark top-level file",
                    expected_path=child,
                    root=root,
                )
            else:
                if not name.startswith(".") and name != "unofficial-reformulations":
                    directories.append(name)
    except SafeIO.SafeReadError as err:
        raise Base.Inventory.InventoryError(
            "cannot enumerate benchmark directories"
        ) from err
    result = tuple(sorted(directories))
    if len(result) != Base.Inventory.EXPECTED_TOP_LEVEL_DIRECTORIES:
        raise Base.Inventory.InventoryError(
            "top-level benchmark directory count changed"
        )
    return result


def _inventory_relative_regular(
    path, root: Path, directory: str
) -> tuple[str, Path]:
    candidate = Path(path)
    try:
        relative = candidate.relative_to(root).as_posix()
    except ValueError as err:
        raise Base.Inventory.InventoryError(
            "benchmark source escapes the pinned root"
        ) from err
    if not relative.startswith(directory + "/"):
        raise Base.Inventory.InventoryError(
            "benchmark source escapes its top-level directory"
        )
    _inventory_safe_file(candidate, "benchmark source", root=root)
    return relative, candidate


def _inventory_load_frozen_prior_records(
    path: Path,
    expected_file_sha256: str,
    expected_records: int,
    *,
    paths_required: bool,
):
    loaded = _inventory_safe_file(
        path, "frozen prior manifest", root=REPO
    )
    if loaded.sha256 != expected_file_sha256:
        raise Base.Inventory.InventoryError(
            "frozen prior manifest bytes changed"
        )
    try:
        data = Base.Inventory.json.loads(loaded.raw.decode("ascii"))
    except (UnicodeDecodeError, Base.Inventory.json.JSONDecodeError) as err:
        raise Base.Inventory.InventoryError(
            "cannot load frozen prior manifest"
        ) from err
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list) or len(tasks) != expected_records:
        raise Base.Inventory.InventoryError(
            "frozen prior manifest task records changed"
        )
    return Base.Inventory._normalize_prior_records(
        tasks, path.name, paths_required=paths_required
    )


Base.Inventory.sha256_file = _inventory_sha256_file
Base.Inventory.validate_benchmark_checkout = _inventory_validate_benchmark_checkout
Base.Inventory._top_level_directories = _inventory_top_level_directories
Base.Inventory._relative_regular = _inventory_relative_regular
Base.Inventory._load_frozen_prior_records = _inventory_load_frozen_prior_records


class _LexicallyValidatedPath:
    """Prevent frozen code from resolving an already safe-validated path."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def resolve(self):
        return self.path


def _safe_base_arguments(args):
    values = vars(args).copy()
    for name in ("code_manifest", "inventory_manifest"):
        if name not in values:
            continue
        path = Path(values[name])
        # The inherited driver calls .resolve() before reaching the safe
        # reader.  This proxy makes that lookup a no-op; the descriptor-based
        # reader remains the first and only filesystem consumer.
        values[name] = _LexicallyValidatedPath(path)
    return types.SimpleNamespace(**values)


def task_environment_path(
    directory: Path, index: int, count: int = Base.SHARD_COUNT
) -> Path:
    return Path(directory) / "environment-{:04d}-of-{:04d}.json".format(
        index, count
    )


def _assert_no_symlink_components(path: Path, label: str) -> None:
    _safe_directory(Path(path), label, expected_path=Path(path))


def _directory_identity(path: Path, label: str) -> dict:
    path = Path(path)
    try:
        loaded = _safe_directory(path, label, expected_path=path)
    except SourceAuditError as err:
        raise SourceAuditError(
            "{} has a symlink path component or changed ancestor".format(label)
        ) from err
    info = loaded.identity
    if (
        not path.is_absolute()
        or path != Path(os.path.normpath(path))
        or not stat.S_ISDIR(info["mode"])
        or stat.S_IMODE(info["mode"]) != 0o700
        or info["uid"] != os.getuid()
    ):
        raise SourceAuditError("{} identity changed".format(label))
    return {
        "path": str(path),
        "canonical_path": str(path),
        "device": info["device"],
        "inode": info["inode"],
        "mode": "0700",
        "uid": info["uid"],
    }


def _require_directory_identity(
    path: Path, expected: dict, label: str
) -> dict:
    actual = _directory_identity(path, label)
    if actual != expected:
        raise SourceAuditError("{} was replaced".format(label))
    return actual


def _array_identity() -> tuple[str, int]:
    array_job_id = os.environ.get("SLURM_ARRAY_JOB_ID")
    raw_task = os.environ.get("SLURM_ARRAY_TASK_ID")
    if (
        not isinstance(array_job_id, str)
        or not array_job_id.isdigit()
        or not isinstance(raw_task, str)
        or not raw_task.isdigit()
    ):
        raise SourceAuditError("source-audit Slurm identity is invalid")
    array_task_id = int(raw_task)
    if not 0 <= array_task_id < Base.SHARD_COUNT:
        raise SourceAuditError("source-audit array task is out of range")
    return array_job_id, array_task_id


def _expected_tmpdir(array_job_id: str, array_task_id: int) -> Path:
    return Path(TMPDIR_TEMPLATE.format(
        array_job_id=array_job_id,
        array_task_id=array_task_id,
    ))


_base_validate_execution_environment = Base.validate_execution_environment


def validate_execution_environment() -> None:
    _base_validate_execution_environment()
    array_job_id, array_task_id = _array_identity()
    expected = _expected_tmpdir(array_job_id, array_task_id)
    if (
        not expected.is_absolute()
        or expected.parent != TMP_ROOT
        or os.environ.get("TMPDIR") != str(expected)
    ):
        raise SourceAuditError("source-audit TMPDIR path changed")
    _directory_identity(TMP_ROOT, "source-audit TMPDIR root")
    _directory_identity(expected, "source-audit per-task TMPDIR")
    if _safe_directory(
        expected, "source-audit per-task TMPDIR", expected_path=expected
    ).entries:
        raise SourceAuditError("source-audit per-task TMPDIR is not empty")
    tempfile.tempdir = None
    if Path(tempfile.gettempdir()) != expected:
        raise SourceAuditError("Python tempfile did not select frozen TMPDIR")


Base.validate_execution_environment = validate_execution_environment


_base_subprocess_run = Base.subprocess.run
_base_count_normalized_axioms = Base._count_normalized_axioms
_base_scan_task = Base._scan_task
_base_load_shard = Base._load_shard
_active_source_snapshot = None


def _snapshot_file_identity(
    path: Path, expected_sha256: str, label: str
) -> dict:
    loaded = _safe_file(path, label, expected_path=path)
    info = loaded.identity
    if (
        not stat.S_ISREG(info["mode"])
        or stat.S_IMODE(info["mode"]) != 0o400
        or info["uid"] != os.getuid()
        or loaded.sha256 != expected_sha256
    ):
        raise SourceAuditError("{} identity or bytes changed".format(label))
    return {
        "device": info["device"],
        "inode": info["inode"],
        "mode": "0400",
        "uid": info["uid"],
        "bytes": info["size"],
        "sha256": loaded.sha256,
    }


def _verify_active_source_snapshot(consumer: str, paths: tuple[Path, Path]) -> None:
    context = _active_source_snapshot
    if not isinstance(context, dict):
        raise SourceAuditError("source snapshot consumer has no active snapshot")
    expected_paths = (context["domain_path"], context["problem_path"])
    if tuple(map(Path, paths)) != expected_paths:
        raise SourceAuditError("{} source snapshot paths changed".format(consumer))
    for role, path in zip(("domain", "problem"), expected_paths):
        expected = context["files_by_role"][role]
        identity = _snapshot_file_identity(
            path, expected["sha256"], "{} {} snapshot".format(consumer, role)
        )
        if identity != expected["identity_before"]:
            raise SourceAuditError(
                "{} {} snapshot was replaced".format(consumer, role)
            )
    context[consumer + "_verified_before_use"] = True


def _subprocess_run_with_tmpdir(*args, **kwargs):
    environment = kwargs.get("env")
    expected_keys = {
        "PATH", "PYTHONNOUSERSITE", "PYTHONDONTWRITEBYTECODE",
        "PYTHONPYCACHEPREFIX", "PYTHONPATH",
    }
    if (
        not isinstance(environment, dict)
        or set(environment) != expected_keys
        or environment.get("PATH") != Base.CONTROLLED_PATH
        or environment.get("PYTHONNOUSERSITE") != "1"
        or environment.get("PYTHONDONTWRITEBYTECODE") != "1"
        or environment.get("PYTHONPYCACHEPREFIX")
        != os.environ.get("PYTHONPYCACHEPREFIX")
        or environment.get("PYTHONPATH") != str(REPO / "src")
        or os.environ.get("TMPDIR") is None
    ):
        raise SourceAuditError("translator child environment changed")
    command = args[0] if args else kwargs.get("args")
    if not isinstance(command, (list, tuple)) or len(command) < 2:
        raise SourceAuditError("translator command changed")
    _verify_active_source_snapshot(
        "translator", (Path(command[-2]), Path(command[-1]))
    )
    kwargs["env"] = {**environment, "TMPDIR": os.environ["TMPDIR"]}
    return _base_subprocess_run(*args, **kwargs)


# The frozen engine already places output.sas in a TemporaryDirectory.  This
# one-line environment extension also makes the translator's own tempfile
# policy explicit without copying or modifying the frozen scan implementation.
class _BaseSubprocessFacade:
    """Confine the translator hook to the frozen producer module."""

    PIPE = Base.subprocess.PIPE
    TimeoutExpired = Base.subprocess.TimeoutExpired
    run = staticmethod(_subprocess_run_with_tmpdir)


Base.subprocess = _BaseSubprocessFacade


def _count_normalized_axioms_from_snapshot(
    domain: Path, problem: Path
) -> int:
    _verify_active_source_snapshot(
        "normalization", (Path(domain), Path(problem))
    )
    return _base_count_normalized_axioms(domain, problem)


Base._count_normalized_axioms = _count_normalized_axioms_from_snapshot


def _read_frozen_source(
    benchmarks: Path, relative: str, expected_sha256: str, role: str
) -> bytes:
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise SourceAuditError("unsafe frozen {} source path".format(role))
    source = Path(benchmarks) / relative_path
    loaded = _safe_file(
        source,
        "frozen {} source".format(role),
        expected_path=source,
        root=Path(benchmarks),
    )
    if loaded.sha256 != expected_sha256:
        raise SourceAuditError("frozen {} source bytes changed".format(role))
    return loaded.raw


def _write_snapshot_file(path: Path, payload: bytes, label: str) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = None
    try:
        descriptor = os.open(path, flags, 0o400)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as err:
        raise SourceAuditError("cannot create {}".format(label)) from err
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _snapshot_relative_path(relative: str) -> Path:
    value = Path(relative)
    if value.is_absolute() or not value.parts or ".." in value.parts:
        raise SourceAuditError("unsafe source snapshot path")
    return value


def _create_snapshot_directories(root: Path, relatives: list[Path]) -> list[Path]:
    directories = {root}
    for relative in relatives:
        parent = relative.parent
        while parent != Path("."):
            directories.add(root / parent)
            parent = parent.parent
    created = []
    try:
        for directory in sorted(directories, key=lambda item: len(item.parts)):
            directory.mkdir(mode=0o700, parents=False, exist_ok=False)
            created.append(directory)
    except OSError as err:
        try:
            for directory in reversed(created):
                directory.rmdir()
        except OSError as cleanup_err:
            raise SourceAuditError(
                "cannot clean partial source snapshot directories"
            ) from cleanup_err
        raise SourceAuditError("cannot create source snapshot directory") from err
    return created


def _clean_source_snapshot(
    files: dict[Path, dict],
    directories: list[Path],
    directory_identities: dict[Path, dict],
) -> None:
    expected_paths = set(files) | set(directories)
    actual_paths = set()
    for directory in directories:
        if _directory_identity(
            directory, "source snapshot cleanup directory"
        ) != directory_identities.get(directory):
            raise SourceAuditError("source snapshot cleanup directory was replaced")
        entries = _safe_directory(
            directory,
            "source snapshot cleanup directory",
            expected_path=directory,
        ).entries
        actual_paths.update(directory / entry for entry in entries)
    if actual_paths != expected_paths - {directories[0]}:
        raise SourceAuditError("source snapshot has unexpected cleanup paths")
    for path, identity in files.items():
        if _snapshot_file_identity(
            path, identity["sha256"], "source snapshot cleanup file"
        ) != identity:
            raise SourceAuditError("source snapshot cleanup file was replaced")
        try:
            path.unlink()
        except OSError as err:
            raise SourceAuditError("cannot remove source snapshot file") from err
    for directory in reversed(directories):
        try:
            directory.rmdir()
        except OSError as err:
            raise SourceAuditError("cannot remove source snapshot directory") from err


def _scan_task(record: dict, benchmarks: Path, timeout: int) -> dict:
    global _active_source_snapshot
    if _active_source_snapshot is not None:
        raise SourceAuditError("nested source snapshot is forbidden")
    raw_index = record.get("candidate_index")
    if type(raw_index) is not int or raw_index < 0:
        raise SourceAuditError("source snapshot candidate identity changed")
    task_tmp = Path(os.environ.get("TMPDIR", ""))
    if not task_tmp.is_absolute():
        raise SourceAuditError("source snapshot TMPDIR changed")
    snapshot_root = task_tmp / "source-snapshot-{:04d}".format(raw_index)
    entries = [
        (
            "domain", record["domain_file"], record["domain_sha256"],
        ),
        (
            "problem", record["problem_file"], record["problem_sha256"],
        ),
    ]
    relative_paths = [_snapshot_relative_path(item[1]) for item in entries]
    payloads = {
        role: _read_frozen_source(benchmarks, relative, digest, role)
        for role, relative, digest in entries
    }
    directories = []
    directory_before = {}
    files_by_path = {}
    files_by_role = {}
    try:
        directories = _create_snapshot_directories(snapshot_root, relative_paths)
        directory_before = {
            path: _directory_identity(path, "source snapshot directory")
            for path in directories
        }
        for (role, relative, digest), relative_path in zip(entries, relative_paths):
            path = snapshot_root / relative_path
            if path not in files_by_path:
                _write_snapshot_file(
                    path, payloads[role], "{} source snapshot".format(role)
                )
                files_by_path[path] = _snapshot_file_identity(
                    path, digest, "{} source snapshot".format(role)
                )
            elif files_by_path[path]["sha256"] != digest:
                raise SourceAuditError("aliased source snapshot hashes differ")
            files_by_role[role] = {
                "path": path,
                "source_file": relative,
                "sha256": digest,
                "identity_before": files_by_path[path],
            }
        context = {
            "domain_path": files_by_role["domain"]["path"],
            "problem_path": files_by_role["problem"]["path"],
            "files_by_role": files_by_role,
            "translator_verified_before_use": False,
            "normalization_verified_before_use": False,
        }
        _active_source_snapshot = context
        task = _base_scan_task(record, snapshot_root, timeout)
        translation_succeeded = task["translation"]["status"] == "success"
        if (
            context["translator_verified_before_use"] is not True
            or context["normalization_verified_before_use"]
            is not translation_succeeded
        ):
            raise SourceAuditError("source snapshot consumer verification changed")
        directory_after = {
            path: _directory_identity(path, "source snapshot directory")
            for path in directories
        }
        if directory_after != directory_before:
            raise SourceAuditError("source snapshot directory was replaced")
        evidence_files = []
        for role in ("domain", "problem"):
            item = files_by_role[role]
            after = _snapshot_file_identity(
                item["path"], item["sha256"], "{} source snapshot".format(role)
            )
            if after != item["identity_before"]:
                raise SourceAuditError("{} source snapshot was replaced".format(role))
            evidence_files.append({
                "role": role,
                "source_file": item["source_file"],
                "snapshot_file": item["path"].relative_to(snapshot_root).as_posix(),
                "bytes": after["bytes"],
                "sha256": item["sha256"],
                "identity_before": item["identity_before"],
                "identity_after": after,
            })
        evidence = {
            "schema": SOURCE_SNAPSHOT_SCHEMA,
            "policy": SOURCE_SNAPSHOT_POLICY,
            "snapshot_root_name": snapshot_root.name,
            "snapshot_root_identity_before": directory_before[snapshot_root],
            "snapshot_root_identity_after": directory_after[snapshot_root],
            "files": evidence_files,
            "translator_verified_before_use": True,
            "normalization_applicable": translation_succeeded,
            "normalization_verified_before_use": translation_succeeded,
            "identity_and_sha256_verified_after_use": True,
            "exact_files_removed": True,
            "exact_directories_removed": True,
        }
    finally:
        _active_source_snapshot = None
        if directories:
            _clean_source_snapshot(
                files_by_path, directories, directory_before
            )
    return {**task, "source_snapshot": evidence}


Base._scan_task = _scan_task


def _valid_private_identity(value, mode: str, *, regular_file: bool) -> bool:
    expected = {"device", "inode", "mode", "uid"}
    if regular_file:
        expected |= {"bytes", "sha256"}
    else:
        expected |= {"path", "canonical_path"}
    return (
        isinstance(value, dict)
        and set(value) == expected
        and type(value.get("device")) is int
        and value["device"] >= 0
        and type(value.get("inode")) is int
        and value["inode"] > 0
        and value.get("mode") == mode
        and value.get("uid") == os.getuid()
        and (
            not regular_file
            or (
                type(value.get("bytes")) is int
                and value["bytes"] >= 0
                and Base._is_sha256(value.get("sha256"))
            )
        )
        and (
            regular_file
            or (
                isinstance(value.get("path"), str)
                and value["path"] == value.get("canonical_path")
                and Path(value["path"]).is_absolute()
            )
        )
    )


def _validate_source_snapshot(task: dict) -> None:
    value = task.get("source_snapshot")
    root_before = value.get("snapshot_root_identity_before") \
        if isinstance(value, dict) else None
    root_after = value.get("snapshot_root_identity_after") \
        if isinstance(value, dict) else None
    files = value.get("files") if isinstance(value, dict) else None
    expected_root_name = "source-snapshot-{:04d}".format(
        task.get("candidate_index", -1)
    )
    root_path = Path(root_before.get("path", "")) \
        if isinstance(root_before, dict) else Path()
    translation_succeeded = task.get("translation", {}).get("status") == "success"
    if (
        not isinstance(value, dict)
        or set(value) != {
            "schema", "policy", "snapshot_root_name",
            "snapshot_root_identity_before", "snapshot_root_identity_after",
            "files", "translator_verified_before_use",
            "normalization_applicable", "normalization_verified_before_use",
            "identity_and_sha256_verified_after_use", "exact_files_removed",
            "exact_directories_removed",
        }
        or value.get("schema") != SOURCE_SNAPSHOT_SCHEMA
        or value.get("policy") != SOURCE_SNAPSHOT_POLICY
        or value.get("snapshot_root_name") != expected_root_name
        or not _valid_private_identity(root_before, "0700", regular_file=False)
        or root_path.name != expected_root_name
        or root_path.parent.parent != TMP_ROOT
        or re.fullmatch(r"task-[0-9]+-[0-9]+", root_path.parent.name) is None
        or root_before != root_after
        or not isinstance(files, list)
        or len(files) != 2
        or value.get("translator_verified_before_use") is not True
        or value.get("normalization_applicable") is not translation_succeeded
        or value.get("normalization_verified_before_use") is not translation_succeeded
        or value.get("identity_and_sha256_verified_after_use") is not True
        or value.get("exact_files_removed") is not True
        or value.get("exact_directories_removed") is not True
    ):
        raise SourceAuditError("source snapshot evidence changed")
    expected_by_role = {
        "domain": (task.get("domain_file"), task.get("domain_sha256")),
        "problem": (task.get("problem_file"), task.get("problem_sha256")),
    }
    seen = set()
    for item in files:
        role = item.get("role") if isinstance(item, dict) else None
        before = item.get("identity_before") if isinstance(item, dict) else None
        after = item.get("identity_after") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or set(item) != {
                "role", "source_file", "snapshot_file", "bytes", "sha256",
                "identity_before", "identity_after",
            }
            or role not in expected_by_role
            or role in seen
            or (item.get("source_file"), item.get("sha256"))
            != expected_by_role[role]
            or item.get("snapshot_file") != item.get("source_file")
            or not _valid_private_identity(before, "0400", regular_file=True)
            or before != after
            or item.get("bytes") != before["bytes"]
            or item.get("sha256") != before["sha256"]
        ):
            raise SourceAuditError("source snapshot file evidence changed")
        seen.add(role)
    if seen != set(expected_by_role):
        raise SourceAuditError("source snapshot roles changed")


def _load_shard(
    path: Path,
    index: int,
    expected_records: list[dict],
    inventory_sha256: str,
    code: dict,
) -> list[dict]:
    tasks = _base_load_shard(
        path, index, expected_records, inventory_sha256, code
    )
    for task in tasks:
        _validate_source_snapshot(task)
    return tasks


Base._load_shard = _load_shard


def _tool_identity(path: Path, expected_sha256: str, label: str) -> dict:
    loaded = _safe_file(path, label, expected_path=path)
    if (
        not path.is_absolute()
        or not stat.S_ISREG(loaded.identity["mode"])
        or stat.S_IMODE(loaded.identity["mode"]) & 0o111 == 0
        or not os.access(path, os.X_OK)
        or loaded.sha256 != expected_sha256
    ):
        raise SourceAuditError("{} identity changed".format(label))
    return {"path": str(path), "sha256": expected_sha256}


def scan(args) -> None:
    validate_execution_environment()
    array_job_id, array_task_id = _array_identity()
    if args.shard_index != array_task_id:
        raise SourceAuditError("Slurm and requested shard identities differ")
    tmpdir = _expected_tmpdir(array_job_id, array_task_id)
    output_dir = Path(args.output_dir)
    output_before = _directory_identity(
        output_dir, "source-audit output directory"
    )
    root_before = _directory_identity(TMP_ROOT, "source-audit TMPDIR root")
    tmp_before = _directory_identity(tmpdir, "source-audit per-task TMPDIR")
    Base.scan(_safe_base_arguments(args))
    code = Base.validate_code_manifest(
        Path(args.code_manifest),
        args.code_manifest_sha256,
        verify_environment_files=False,
    )
    root_after = _directory_identity(TMP_ROOT, "source-audit TMPDIR root")
    tmp_after = _directory_identity(tmpdir, "source-audit per-task TMPDIR")
    output_after = _directory_identity(
        output_dir, "source-audit output directory"
    )
    if (
        root_after != root_before
        or tmp_after != tmp_before
        or output_after != output_before
    ):
        raise SourceAuditError("source-audit root identity changed during scan")
    if _safe_directory(
        tmpdir, "source-audit per-task TMPDIR", expected_path=tmpdir
    ).entries:
        raise SourceAuditError("source-audit TMPDIR retained task files")
    shard = Base.shard_path(args.output_dir, args.shard_index, args.num_shards)
    value = {
        "schema": TASK_ENVIRONMENT_SCHEMA,
        "array_job_id": array_job_id,
        "array_task_id": array_task_id,
        "output_dir": str(output_dir),
        "output_dir_identity_before": output_before,
        "output_dir_identity_after": output_after,
        "tmpdir_root": str(TMP_ROOT),
        "tmpdir": str(tmpdir),
        "tempfile_gettempdir": tempfile.gettempdir(),
        "tmpdir_root_identity_before": root_before,
        "tmpdir_root_identity_after": root_after,
        "tmpdir_identity_before": tmp_before,
        "tmpdir_identity_after": tmp_after,
        "tmpdir_empty_after_scan": True,
        "python_pycache_prefix": os.environ["PYTHONPYCACHEPREFIX"],
        "path": os.environ["PATH"],
        "python_no_user_site": os.environ["PYTHONNOUSERSITE"],
        "python_dont_write_bytecode": os.environ["PYTHONDONTWRITEBYTECODE"],
        "unset_variables_absent": list(Base.UNSET_PYTHON_ENV),
        "python_no_user_site_flag": sys.flags.no_user_site,
        "python_dont_write_bytecode_flag": sys.dont_write_bytecode,
        "source_snapshot_policy": SOURCE_SNAPSHOT_POLICY,
        "source_inventory_sha256": args.inventory_sha256,
        "code_manifest_sha256": args.code_manifest_sha256,
        "shard_sha256": sha256_file(shard),
        "tools": {
            "python": {
                "path": code["python_executable"],
                "sha256": code["python_executable_sha256"],
            },
            "sha256sum": _tool_identity(
                SHA256SUM_COMMAND, SHA256SUM_SHA256, "sha256sum"
            ),
            "mkdir": _tool_identity(MKDIR_COMMAND, MKDIR_SHA256, "mkdir"),
            "rmdir": _tool_identity(RMDIR_COMMAND, RMDIR_SHA256, "rmdir"),
        },
        "python_environment": code,
    }
    Base._atomic_json(
        task_environment_path(args.output_dir, args.shard_index, args.num_shards),
        value,
    )
    _require_directory_identity(
        output_dir, output_before, "source-audit output directory"
    )


def load_task_environment_attestation(
    path: Path,
    *,
    index: int,
    array_job_id: str,
    inventory_sha256: str,
    code_manifest_sha256: str,
    code: dict,
    shard_sha256: str,
) -> dict:
    _, value = Base._load_canonical_json(path, "task environment attestation")
    tmpdir = _expected_tmpdir(array_job_id, index)
    expected_keys = {
        "schema", "array_job_id", "array_task_id", "output_dir",
        "output_dir_identity_before", "output_dir_identity_after",
        "tmpdir_root", "tmpdir",
        "tempfile_gettempdir", "tmpdir_root_identity_before",
        "tmpdir_root_identity_after", "tmpdir_identity_before",
        "tmpdir_identity_after", "tmpdir_empty_after_scan",
        "python_pycache_prefix", "path", "python_no_user_site",
        "python_dont_write_bytecode", "unset_variables_absent",
        "python_no_user_site_flag", "python_dont_write_bytecode_flag",
        "source_snapshot_policy",
        "source_inventory_sha256", "code_manifest_sha256", "shard_sha256",
        "tools", "python_environment",
    }
    identities = (
        value.get("output_dir_identity_before"),
        value.get("output_dir_identity_after"),
        value.get("tmpdir_root_identity_before"),
        value.get("tmpdir_root_identity_after"),
        value.get("tmpdir_identity_before"),
        value.get("tmpdir_identity_after"),
    )
    if (
        set(value) != expected_keys
        or value.get("schema") != TASK_ENVIRONMENT_SCHEMA
        or value.get("array_job_id") != array_job_id
        or type(value.get("array_task_id")) is not int
        or value["array_task_id"] != index
        or value.get("output_dir") != str(Path(path).parent)
        or value.get("tmpdir_root") != str(TMP_ROOT)
        or value.get("tmpdir") != str(tmpdir)
        or value.get("tempfile_gettempdir") != str(tmpdir)
        or value.get("python_pycache_prefix") != str(tmpdir / "pycache")
        or value.get("tmpdir_empty_after_scan") is not True
        or value.get("path") != Base.CONTROLLED_PATH
        or value.get("python_no_user_site") != "1"
        or value.get("python_dont_write_bytecode") != "1"
        or value.get("unset_variables_absent") != list(Base.UNSET_PYTHON_ENV)
        or value.get("python_no_user_site_flag") != 1
        or value.get("python_dont_write_bytecode_flag") is not True
        or value.get("source_snapshot_policy") != SOURCE_SNAPSHOT_POLICY
        or value.get("source_inventory_sha256") != inventory_sha256
        or value.get("code_manifest_sha256") != code_manifest_sha256
        or value.get("shard_sha256") != shard_sha256
        or value.get("python_environment") != code
        or value.get("tools") != {
            "python": {
                "path": code["python_executable"],
                "sha256": code["python_executable_sha256"],
            },
            "sha256sum": {
                "path": str(SHA256SUM_COMMAND), "sha256": SHA256SUM_SHA256,
            },
            "mkdir": {"path": str(MKDIR_COMMAND), "sha256": MKDIR_SHA256},
            "rmdir": {"path": str(RMDIR_COMMAND), "sha256": RMDIR_SHA256},
        }
        or any(
            not _valid_private_identity(
                identity, "0700", regular_file=False
            )
            for identity in identities
        )
        or identities[0] != identities[1]
        or identities[2] != identities[3]
        or identities[4] != identities[5]
        or identities[0]["path"] != value.get("output_dir")
        or identities[2]["path"] != value.get("tmpdir_root")
        or identities[4]["path"] != value.get("tmpdir")
    ):
        raise SourceAuditError("task environment attestation changed")
    return value


def __getattr__(name):
    return getattr(Base, name)


def main(argv=None) -> int:
    args = Base.parse_args(argv)
    if args.command == "scan":
        scan(args)
    else:
        Base.assemble(_safe_base_arguments(args))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InfrastructureAuditError as err:
        print("infrastructure error: {}".format(err), file=sys.stderr)
        raise SystemExit(75)
    except (SourceAuditError, Base.Inventory.InventoryError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
