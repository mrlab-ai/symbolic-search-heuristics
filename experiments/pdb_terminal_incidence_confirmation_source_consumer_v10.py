#!/usr/bin/env python3
"""Independent, fail-closed consumer for the V10 full-census source seal.

This trust boundary intentionally imports no producer, launcher, publication
helper, or earlier campaign consumer.  In particular, infrastructure preflight
authorization is consumed separately and the scheduler terminal gate is
authenticated before a worker payload path is opened.
"""

from __future__ import annotations

import base64
import binascii
import datetime
import hashlib
import json
import os
import re
import stat
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping


class SourceConsumerError(RuntimeError):
    """The V10 evidence is incomplete, inconsistent, or unauthorized."""


SCRIPT_DIR = Path(os.path.abspath(__file__)).parent
REPO = SCRIPT_DIR.parent
SCHEMA = (
    "symbolic-search-heuristics/"
    "universal-unseen-confirmation-source-audit/v1/campaign-v10"
)
CAMPAIGN = "v10-full-census"
PREFLIGHT_CAMPAIGN = "v10-preflight"
SHARD_SCHEMA = SCHEMA + "/shard/v1"
SHARD_CLAIM_SCHEMA = SCHEMA + "/shard-claim/v1"
SHARD_COMPLETION_METADATA_SCHEMA = SCHEMA + "/shard-completion-metadata/v1"
COMPLETION_SCHEMA = "pdb-terminal-incidence/immutable-shard-completion/v1"
INVENTORY_SCHEMA = SCHEMA + "/inventory/v1"
ATTESTATION_SCHEMA = SCHEMA + "/attestation/v1"
EXECUTION_SCHEMA = SCHEMA + "/execution/v1"
LAUNCH_SCHEMA = SCHEMA + "/launch/v1"
SBATCH_RESULT_SCHEMA = LAUNCH_SCHEMA + "/sbatch-result/v1"
COMPUTE_TERMINAL_RECEIPT_SCHEMA = SCHEMA + "/preflight/v1/compute-canary-terminal/v1"
FULL_TERMINAL_RECEIPT_SCHEMA = SCHEMA + "/execution/v1/terminal/v1"
PREFLIGHT_AUTHORIZATION_SCHEMA = SCHEMA + "/preflight/v1/authorization/v1"
COMPUTE_LAUNCH_INTENT_SCHEMA = SCHEMA + "/preflight/v1/compute-canary-launch-intent/v1"
COMPUTE_SBATCH_RESULT_SCHEMA = SCHEMA + "/preflight/v1/compute-canary-sbatch-result/v1"
COMPUTE_LAUNCH_SCHEMA = SCHEMA + "/preflight/v1/compute-canary-launch/v1"
CANDIDATE_SCHEMA = SCHEMA + "/candidate-result/v1"
TASK_ENVIRONMENT_SCHEMA = SCHEMA + "/task-environment/v1"
SOURCE_SNAPSHOT_SCHEMA = SCHEMA + "/source-snapshot/v1"
RESOURCE_CONTRACT_SCHEMA = SCHEMA + "/resource-contract/v1"

CANDIDATE_COUNT = 1640
SHARD_COUNT = 820
TASKS_PER_SHARD = 2
FULL_TREE_FILE_COUNT = 1 + SHARD_COUNT * 8
PRIOR_CAMPAIGNS = ["v{}".format(index) for index in range(1, 10)]
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
POLL_RE = re.compile(
    r"poll-([0-9]{4})-(intent\.json|stdout\.bin|stderr\.bin|result\.json|receipt\.json|abandoned\.json)\Z"
)
POLL_SUFFIXES = (
    "intent.json", "stdout.bin", "stderr.bin", "result.json", "receipt.json",
)
FULL_POLL_SCHEMA = SCHEMA + "/execution/v1/poll/v1"
COMPUTE_POLL_SCHEMA = SCHEMA + "/preflight/v1/compute-canary-poll/v1"
ACTIVE_STATES = frozenset({
    "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
    "RESIZING", "SUSPENDED", "STAGE_OUT",
})
TERMINAL_STATES = frozenset({
    "BOOT_FAIL", "CANCELLED", "COMPLETED", "DEADLINE", "FAILED",
    "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED", "REVOKED",
    "SPECIAL_EXIT", "TIMEOUT",
})

ACCOUNT = "naiss2025-5-561-cpu"
PARTITION = "fat"
QOS = "normal"
MEMORY = "26G"
TIME_LIMIT = "01:10:00"
CAPTURE_PROTOCOL = "pre-intent-o-excl-nofollow-sealed-0400-retained-fd-v1"
CONTROLLED_PATH = "/usr/bin:/bin"
PYTHON_COMMAND = (
    "/home/jendrik/.local/share/uv/python/"
    "cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
)
PYTHON_EXECUTABLE_SHA256 = (
    "021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
)
JOB_ID_RE = re.compile(r"([0-9]+)(?:;[A-Za-z0-9_.-]+)?\n?\Z")
TOKEN_RE = re.compile(r"[0-9a-f]{24}\Z")

ADDRESS_SPACE_BYTES = 24_576 * 1024 * 1024
CPU_SOFT_SECONDS = 1800
CPU_HARD_SECONDS = 1801
CHILD_WALL_SECONDS = 1950
STREAM_PREFIX_BYTES = 1024 * 1024
STREAM_TAIL_BYTES = 8192
PRLIMIT_SHA256 = (
    "fc3d011a1d832dabd768343b26d38223cb2bbd13d59ed97998a2d6a747ce8676"
)
LIBSECCOMP_SHA256 = (
    "54068c4d4cf1e5692ba8051ce0744cd175d0c0e2c9812b668d738d2cbe3915d9"
)
PRLIMIT_STDOUT_SHA256 = (
    "325c2dbc93e4f6f63cf0cc03be8575108cb7a143801e0ba42d9d11412f6d68b0"
)
DENIED_PROCESS_SYSCALLS = (
    "clone", "clone3", "fork", "setpgid", "setsid", "vfork",
)

SPLIT_SEED = (
    "symbolic-search-heuristics/universal-unseen-confirmation-guided-split/v1"
)
GUIDED_ROLE = "guided-b"
GUIDED_TOP_UP_ROLE = "guided-b-topup"
CONFIRMATION_ROLE = "confirmation-a"
CONFIRMATION_TASKS = 650
MIN_CONFIRMATION_FAMILIES = 28
MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES = 12
MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS = 100
MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES = 10
GUIDED_TARGET_TASKS = 300
MAX_GUIDED_TASKS_PER_FAMILY = 12
MIN_GUIDED_TASKS = 200
MIN_GUIDED_FAMILIES = 30
MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES = 12
MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS = 50
MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES = 10

BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
COST_MANIFEST_SHA256 = (
    "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168"
)
SHADOW_ATTESTATION_SHA256 = (
    "bf2c42860fad91c56620c90a41657ab472f4d58acd184a7580c7b5994aa72d04"
)
CANDIDATE_RECORDS_SHA256 = (
    "5add608b876d236a3fc6b3ab0eaeb67a4b7629c9328039ba2752c4c380e3035c"
)
ALIAS_GROUPS_SHA256 = (
    "d9843d73b854eeb58b37dcdfad9265daf7552d909ab0df865b0ff9b13d6dc425"
)
SHADOW_FAMILIES = (
    "agricola", "barman", "caldera", "cavediving", "childsnack",
    "floortile", "hiking", "maintenance", "miconic", "nomystery",
    "nurikabe", "openstacks", "organic-synthesis", "parking",
    "quantum-layout", "rubiks-cube", "schedule", "slitherlink", "snake",
    "termes", "tetris", "thoughtful", "tidybot", "transport", "visitall",
    "woodworking",
)
ALL_PRIOR_FAMILIES = (
    "agricola", "airport", "barman", "blocks", "caldera", "cavediving",
    "childsnack", "depot", "driverlog", "elevators", "floortile",
    "freecell", "ged", "grid", "gripper", "hiking", "logistics",
    "maintenance", "miconic", "movie", "mprime", "mystery", "nomystery",
    "nurikabe", "openstacks", "organic-synthesis", "parcprinter", "parking",
    "pathways", "pegsol", "pipesworld", "psr", "quantum-layout", "rovers",
    "rubiks-cube", "satellite", "scanalyzer", "schedule", "slitherlink",
    "snake", "sokoban", "storage", "termes", "tetris", "thoughtful",
    "tidybot", "tpp", "transport", "trucks", "visitall", "woodworking",
    "zenotravel",
)
ALL_PRIOR_UNREPRESENTED_FAMILIES = (
    "assembly", "citycar", "data-network", "flashfill", "folding",
    "labyrinth", "optical-telegraphs", "petri-net-alignment", "philosophers",
    "recharging-robots", "ricochet-robots", "settlers", "spider",
)
EXPECTED_INVENTORY_DIGESTS = {
    "all_path_records": "def0e74b0bb4fbc656349a1864de16fc4856c4072d5c9cc8859bc6f1dab0dcf1",
    "all_prior_families": "fe05c88ed11512cf25cb68bfe0c2522558bfe23daa1090df7182fc6df4206a59",
    "all_prior_unrepresented_families": "2b461a68f2bcad8bdeb18304ec1cfad68dd287994cce0770b7392fcc285f9ec1",
    "all_unique_problem_hashes": "545c64781179c559e5d138c721336b173fe90c89a87a371448a2ef5941f7db18",
    "candidate_records": CANDIDATE_RECORDS_SHA256,
    "cost_problem_hashes": "aa944356dccd89e87229e0af2db8038292fd537e99a18358f0ad74c6a9fb63b6",
    "directories": "7eb95fd8f2cb5c49bde50bef203e99ec3985a074c256c969914a4069e79004c7",
    "alias_groups": ALIAS_GROUPS_SHA256,
    "family_map": "7e05588a27ccae96fa50c58417b6bd0417532121b668b1205850adee03591dc1",
    "prior_problem_hashes": "2b34bdd0a7829105cd1cd55536f68d65b60448b509fe3fd1166d34e6108ae74d",
    "prior_identities": "176e5e02f07caf47f8e144b963033ca0d248624d0182b4da842df977e439f73d",
    "prior_identity_ledger": "d4b6aaae00581781dfb4dc7947f7fbec592e19a60167bb5c4a35bd6d2abb3f86",
    "prior_directory_family_map": "790426b33b085c70ae2a3b63a337616e14a0446db91ff40d854634996d345a52",
    "prior_family_ledger": "9de66fb087855ede93eabf3193e462bbacdde1bcdc7b2ddc48ab3168b1f31101",
    "represented_all_prior_families": "e72960e757d89ce266c8ff2a670956bffece24cc296ce1b19eafa4758a82a8af",
    "residue_identities": "922b7bc93d2006c97625038c86263f3dc211a44e28553cfaf29ff753cf0746d6",
    "residue_path_records": "44c5b7a4d74998d5f7b065093fa68afa1ff53c4b38ba3fb732dcc5f611f45468",
    "shadow_problem_hashes": "37534406e44c964a9ef6853f24b720ec7bbe4ff8d0aa89d653a243d5459d8b21",
    "shadow_families": "f1f6877788c0565179660ac1892268fc85235ab73729053c285dd6cfeb01fa28",
    "shadow_unrepresented_families": "9b831aa026deeda951f8aefd3ce8632ec0b82fb7f5231d3fbb5acf9dbd97f746",
}

INVENTORY_RECORD_KEYS = frozenset({
    "candidate_index", "directory", "family", "problem", "domain_file",
    "problem_file", "domain_sha256", "problem_sha256", "canonical_path",
    "is_shadow_family", "is_shadow_unrepresented",
    "is_all_prior_represented", "is_all_prior_unrepresented", "aliases",
})
CANDIDATE_RESULT_KEYS = INVENTORY_RECORD_KEYS | frozenset({
    "schema", "logical_shard_index", "position_in_shard",
    "candidate_origin", "translation_attempted", "translator_command",
    "code_manifest_sha256", "repository_commit_id", "resource_contract",
    "resource_contract_sha256", "child_limit_attestation",
    "parent_prlimit_observation", "parent_isolation_observation",
    "process_returncode", "complete_process_group_reaped", "stdout",
    "stderr", "normalization", "sas", "sas_bytes", "sas_sha256",
    "partial_sas_evidence", "status", "resource_exclusion_kind",
    "support_determined", "supported", "support_exclusion_reasons",
    "eligible_for_cohort", "source_snapshot",
})
SAS_KEYS = frozenset({
    "sas_version", "metric", "num_variables", "num_mutex_groups",
    "num_operators", "num_effects", "num_conditional_effects",
    "num_zero_cost_operators", "min_operator_cost", "max_operator_cost",
    "num_serialized_axioms",
})

ARTIFACT_DIR = SCRIPT_DIR / "artifacts/pdb-terminal-incidence-confirmation-v10"
DATA_ROOT = SCRIPT_DIR / "data/pdb-terminal-incidence-confirmation-source-audit-v10"
PREFLIGHT_ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts/pdb-terminal-incidence-confirmation-v10-preflight"
)
CONTROLLER_CANARY_ROOT = (
    SCRIPT_DIR / "data/pdb-terminal-incidence-confirmation-publisher-canary-v10"
)
COMPUTE_CANARY_ROOT = (
    SCRIPT_DIR / "data/pdb-terminal-incidence-confirmation-source-audit-v10-canary"
)
FULL_TMP_ROOT = (
    SCRIPT_DIR / "data/pdb-terminal-incidence-confirmation-source-audit-v10-tmp"
)
FULL_LOG_ROOT = (
    SCRIPT_DIR / "data/pdb-terminal-incidence-confirmation-source-audit-v10-logs"
)
COMPUTE_CANARY_TMP_ROOT = (
    SCRIPT_DIR / "data/pdb-terminal-incidence-confirmation-source-audit-v10-canary-tmp"
)
COMPUTE_CANARY_LOG_ROOT = (
    SCRIPT_DIR / "data/pdb-terminal-incidence-confirmation-source-audit-v10-canary-logs"
)
FULL_SLURM_PROGRAM = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan_v10.slurm"
)
COMPUTE_CANARY_SLURM_PROGRAM = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_compute_canary_v10.slurm"
)
CODE_MANIFEST = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_audit_v10_code.sha256"
)

FULL_ARTIFACT_FILENAMES = (
    "source-audit-launch-intent-v10.json",
    "source-audit-sbatch-stdout-v10.bin",
    "source-audit-sbatch-stderr-v10.bin",
    "source-audit-sbatch-result-v10.json",
    "source-audit-launch-receipt-v10.json",
    "source-audit-scheduler-terminal-receipt-v10.json",
    "source-audit-seal-plan-v10.json",
    "source-audit-tree-stage-v10.json",
    "source-audit-census-stage-v10.json",
    "source-audit-split-stage-v10.json",
    "source-audit-attestation-stage-v10.json",
    "source-audit-attestation-v10.json",
    "source-audit-execution-receipt-v10.json",
)
PREFLIGHT_ARTIFACT_FILENAMES = (
    "controller-publisher-canary-receipt-v10.json",
    "compute-canary-launch-intent-v10.json",
    "compute-canary-launch-receipt-v10.json",
    "compute-canary-sbatch-stdout-v10.bin",
    "compute-canary-sbatch-stderr-v10.bin",
    "compute-canary-sbatch-result-v10.json",
    "compute-canary-scheduler-terminal-receipt-v10.json",
    "compute-canary-seal-plan-v10.json",
    "compute-canary-attestation-v10.json",
    "preflight-authorization-v10.json",
)
REQUIRED_SOURCE_FILES = frozenset({
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v10.py",
    "experiments/fixtures/pdb-terminal-incidence-v10-canary/domain.pddl",
    "experiments/fixtures/pdb-terminal-incidence-v10-canary/problem-0.pddl",
    "experiments/fixtures/pdb-terminal-incidence-v10-canary/problem-1.pddl",
    "experiments/jj_cached_revision.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v10.py",
    "experiments/pdb_terminal_incidence_confirmation_inventory.py",
    "experiments/pdb_terminal_incidence_confirmation_publication_v10.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v10_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_compute_canary_v10.slurm",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v10.py",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v10.slurm",
    "experiments/pdb_terminal_incidence_confirmation_translate_v10.py",
    "experiments/pdb_terminal_incidence_shadow_cost_attestation.json",
    "experiments/pdb_terminal_incidence_v10_snapshot_reader.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/suite_wbh_operator_costs.json",
    "experiments/test_launch_pdb_terminal_incidence_confirmation_source_audit_v10.py",
    "experiments/test_pdb_terminal_incidence_confirmation_publication_v10.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v10.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_consumer_v10.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_seal_v10.py",
    "experiments/test_pdb_terminal_incidence_confirmation_translate_v10.py",
    "experiments/test_pdb_terminal_incidence_v10_snapshot_reader.py",
})


@dataclass(frozen=True)
class V10PreflightPaths:
    artifact_dir: Path
    poll_dir: Path
    controller_receipt: Path
    compute_launch_intent: Path
    compute_launch_receipt: Path
    compute_sbatch_stdout: Path
    compute_sbatch_stderr: Path
    compute_sbatch_result: Path
    compute_terminal_receipt: Path
    compute_seal_plan: Path
    compute_attestation: Path
    authorization: Path
    code_manifest: Path
    controller_output_root: Path
    compute_output_root: Path


def preflight_paths_for(
    artifact_dir: Path = PREFLIGHT_ARTIFACT_DIR, *,
    code_manifest: Path = CODE_MANIFEST,
    controller_output_root: Path = CONTROLLER_CANARY_ROOT,
    compute_output_root: Path = COMPUTE_CANARY_ROOT,
) -> V10PreflightPaths:
    artifact_dir = Path(os.path.abspath(artifact_dir))
    return V10PreflightPaths(
        artifact_dir=artifact_dir,
        poll_dir=artifact_dir / "compute-canary-scheduler-polls-v10",
        controller_receipt=artifact_dir / PREFLIGHT_ARTIFACT_FILENAMES[0],
        compute_launch_intent=artifact_dir / PREFLIGHT_ARTIFACT_FILENAMES[1],
        compute_launch_receipt=artifact_dir / PREFLIGHT_ARTIFACT_FILENAMES[2],
        compute_sbatch_stdout=artifact_dir / PREFLIGHT_ARTIFACT_FILENAMES[3],
        compute_sbatch_stderr=artifact_dir / PREFLIGHT_ARTIFACT_FILENAMES[4],
        compute_sbatch_result=artifact_dir / PREFLIGHT_ARTIFACT_FILENAMES[5],
        compute_terminal_receipt=artifact_dir / PREFLIGHT_ARTIFACT_FILENAMES[6],
        compute_seal_plan=artifact_dir / PREFLIGHT_ARTIFACT_FILENAMES[7],
        compute_attestation=artifact_dir / PREFLIGHT_ARTIFACT_FILENAMES[8],
        authorization=artifact_dir / PREFLIGHT_ARTIFACT_FILENAMES[9],
        code_manifest=Path(os.path.abspath(code_manifest)),
        controller_output_root=Path(os.path.abspath(controller_output_root)),
        compute_output_root=Path(os.path.abspath(compute_output_root)),
    )


@dataclass(frozen=True)
class V10Paths:
    artifact_dir: Path
    data_root: Path
    poll_dir: Path
    launch_intent: Path
    sbatch_stdout: Path
    sbatch_stderr: Path
    sbatch_result: Path
    launch_receipt: Path
    terminal_receipt: Path
    seal_plan: Path
    tree_stage: Path
    census_stage: Path
    split_stage: Path
    attestation_stage: Path
    attestation: Path
    execution_receipt: Path
    code_manifest: Path
    preflight: V10PreflightPaths


def paths_for(
    artifact_dir: Path = ARTIFACT_DIR, data_root: Path = DATA_ROOT, *,
    preflight_paths: V10PreflightPaths | None = None,
    code_manifest: Path = CODE_MANIFEST,
) -> V10Paths:
    artifact_dir = Path(os.path.abspath(artifact_dir))
    data_root = Path(os.path.abspath(data_root))
    names = [artifact_dir / name for name in FULL_ARTIFACT_FILENAMES]
    return V10Paths(
        artifact_dir, data_root,
        artifact_dir / "source-audit-scheduler-polls-v10",
        *names[:5], names[5], *names[6:],
        Path(os.path.abspath(code_manifest)),
        preflight_paths or preflight_paths_for(code_manifest=code_manifest),
    )


@dataclass(frozen=True)
class AuthorizedPreflight:
    campaign: str
    seal_repository_commit_id: str
    source_repository_commit_id: str
    authorization_sha256: str
    controller_publisher_canary_receipt_sha256: str
    compute_canary_launch_receipt_sha256: str
    compute_canary_terminal_poll_receipt_sha256: str
    compute_canary_seal_plan_sha256: str
    compute_canary_attestation_sha256: str
    code_manifest_sha256: str
    full_launch_authorized: bool
    tracked_file_sha256: Mapping[str, str]


@dataclass(frozen=True)
class AuthorizedConfirmation:
    campaign: str
    benchmark_revision: str
    seal_repository_commit_id: str
    source_inventory_sha256: str
    code_manifest_sha256: str
    launch_receipt_sha256: str
    execution_receipt_sha256: str
    attestation_sha256: str
    preflight: AuthorizedPreflight
    confirmation_a: tuple[Mapping[str, Any], ...]
    guided_b: tuple[Mapping[str, Any], ...]
    eligible_records: tuple[Mapping[str, Any], ...]
    all_records: tuple[Mapping[str, Any], ...]
    outcome_counts: Mapping[str, int]
    resource_exclusions_by_family: Mapping[str, Any]
    tracked_file_sha256: Mapping[str, str]


SnapshotReader = Callable[[str, list[str]], dict[str, bytes]]


def _canonical(value: Any) -> bytes:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise SourceConsumerError("value is not finite canonical JSON") from err


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _is_sha(value: Any) -> bool:
    return type(value) is str and SHA256_RE.fullmatch(value) is not None


def _freeze(value: Any) -> Any:
    if type(value) is dict:
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if type(value) is list:
        return tuple(_freeze(item) for item in value)
    return value


def _read_regular(path: Path, label: str, mode: int = 0o400) -> bytes:
    path = Path(path)
    try:
        before = path.lstat()
        if (
            path.is_symlink() or not stat.S_ISREG(before.st_mode)
            or stat.S_IMODE(before.st_mode) != mode
            or before.st_uid != os.getuid() or before.st_nlink != 1
        ):
            raise SourceConsumerError(label + " is not an immutable owned file")
        flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            opened = os.fstat(fd)
            chunks = []
            while True:
                chunk = os.read(fd, 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
            after = os.fstat(fd)
        finally:
            os.close(fd)
    except SourceConsumerError:
        raise
    except OSError as err:
        raise SourceConsumerError("cannot read " + label) from err
    identity = lambda info: (
        info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
        info.st_nlink, info.st_size, info.st_mtime_ns,
    )
    raw = b"".join(chunks)
    if identity(before) != identity(opened) or identity(opened) != identity(after) or len(raw) != before.st_size:
        raise SourceConsumerError(label + " changed while read")
    try:
        live = path.lstat()
    except OSError as err:
        raise SourceConsumerError(label + " vanished after read") from err
    if identity(live) != identity(before):
        raise SourceConsumerError(label + " path was replaced while read")
    return raw


def _read_json(path: Path, label: str, *, newline: bool = False) -> tuple[bytes, dict]:
    raw = _read_regular(path, label)
    try:
        value = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SourceConsumerError(label + " is not JSON") from err
    expected = _canonical(value) + (b"\n" if newline else b"")
    if type(value) is not dict or raw != expected:
        raise SourceConsumerError(label + " is not canonical JSON")
    return raw, value


def _decode_object(raw: bytes, label: str) -> dict:
    try:
        value = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise SourceConsumerError(label + " is not JSON") from err
    if type(value) is not dict or raw != _canonical(value):
        raise SourceConsumerError(label + " is not canonical JSON")
    return value


def _utc_timestamp(value: Any, label: str) -> datetime.datetime:
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError) as err:
        raise SourceConsumerError(label + " changed") from err
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != datetime.timedelta(0)
        or parsed.isoformat(timespec="seconds") != value
    ):
        raise SourceConsumerError(label + " is not canonical UTC")
    return parsed


def _resource_profile(array: str) -> dict:
    return {
        "account": ACCOUNT,
        "partition": PARTITION,
        "qos": QOS,
        "nodes": 1,
        "ntasks": 1,
        "cpus_per_task": 1,
        "mem": MEMORY,
        "time": TIME_LIMIT,
        "array": array,
        "array_throttle": None,
        "nice": 0,
        "requeue": False,
        "export": "NONE",
    }


def _submit_command(token: str, *, canary: bool) -> list[str]:
    prefix = "pdb-source-v10-canary" if canary else "pdb-source-v10"
    comment_prefix = prefix
    array = "0-0" if canary else "0-819"
    log_root = COMPUTE_CANARY_LOG_ROOT if canary else FULL_LOG_ROOT
    return [
        "/usr/bin/sbatch", "--parsable", "--export=NONE",
        "--job-name={}-{}".format(prefix, token),
        "--comment={}-{}".format(comment_prefix, token),
        "--account=" + ACCOUNT, "--partition=" + PARTITION,
        "--qos=" + QOS, "--nodes=1", "--ntasks=1",
        "--cpus-per-task=1", "--mem=" + MEMORY,
        "--time=" + TIME_LIMIT, "--array=" + array,
        "--nice=0", "--no-requeue", "--chdir=" + str(REPO),
        "--output={}/slurm-%A_%a.out".format(log_root),
        "--error={}/slurm-%A_%a.err".format(log_root),
    ]


def _execution_environment() -> dict:
    return {
        "submission_export": "NONE",
        "slurm_export": "NONE",
        "path": CONTROLLED_PATH,
        "unset_variables": ["PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"],
        "python_no_user_site": "1",
        "python_dont_write_bytecode": "1",
        "python_command": PYTHON_COMMAND,
        "python_executable_sha256": PYTHON_EXECUTABLE_SHA256,
        "tmpdir_root": str(FULL_TMP_ROOT),
        "scheduler_log_root": str(FULL_LOG_ROOT),
        "tmpdir_template": str(
            FULL_TMP_ROOT / "task-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"
        ),
        "task_tmpdir_mode": "0700",
        "task_tmpdir_cleanup": (
            "exact empty unpublished directory on success only"
        ),
        "candidate_address_space_limit_mib": 24576,
        "candidate_cpu_limit_seconds": 1800,
        "candidate_wall_watchdog_seconds": 1950,
    }


def _validate_root_records(value: Any, expected: Mapping[str, Path]) -> None:
    if type(value) is not dict or set(value) != set(expected):
        raise SourceConsumerError("V10 launch root records changed")
    for name, path in expected.items():
        record = value[name]
        if (
            type(record) is not dict
            or set(record) != {
                "path", "canonical_path", "device", "inode", "mode",
                "uid", "gid",
            }
            or record.get("path") != str(path)
            or record.get("canonical_path") != str(path)
            or type(record.get("device")) is not int
            or record["device"] < 0
            or type(record.get("inode")) is not int
            or record["inode"] <= 0
            or record.get("mode") != "0700"
            or record.get("uid") != os.getuid()
            or type(record.get("gid")) is not int
            or record["gid"] < 0
        ):
            raise SourceConsumerError("V10 launch root identity changed")


def _validate_slurm_record(
    value: Any, *, template: Path,
) -> None:
    if (
        type(value) is not dict
        or set(value) != {
            "template_path", "template_sha256", "rendered_sha256",
            "rendered_bytes", "submission_mode", "path_argument",
        }
        or value.get("template_path") != str(template)
        or not _is_sha(value.get("template_sha256"))
        or not _is_sha(value.get("rendered_sha256"))
        or type(value.get("rendered_bytes")) is not int
        or value["rendered_bytes"] <= 0
        or value.get("submission_mode") != "stdin"
        or value.get("path_argument") is not False
    ):
        raise SourceConsumerError("V10 launch Slurm record changed")


def _validate_code_manifest_record(
    value: Any, *, path: Path, sha256: str,
) -> None:
    files = value.get("files") if type(value) is dict else None
    if (
        type(value) is not dict
        or set(value) != {"path", "sha256", "files", "files_sha256"}
        or value.get("path") != str(path)
        or value.get("sha256") != sha256
        or type(files) is not list
        or not files
        or value.get("files_sha256") != _digest(files)
    ):
        raise SourceConsumerError("V10 launch code-manifest record changed")
    names = []
    for record in files:
        if (
            type(record) is not dict
            or set(record) != {"path", "sha256"}
            or type(record.get("path")) is not str
            or not record["path"]
            or Path(record["path"]).is_absolute()
            or ".." in Path(record["path"]).parts
            or not _is_sha(record.get("sha256"))
        ):
            raise SourceConsumerError("V10 launch manifest file record changed")
        names.append(record["path"])
    if names != sorted(set(names)):
        raise SourceConsumerError("V10 launch manifest sequence changed")


def _capture_identity(
    value: Any, *, path: Path, info: os.stat_result, initial: bool,
) -> None:
    size_key = "bytes_at_intent" if initial else "bytes"
    if (
        type(value) is not dict
        or set(value) != {
            "path", "canonical_path", "device", "inode", "mode", "uid",
            "gid", "link_count", size_key,
        }
        or value.get("path") != str(path)
        or value.get("canonical_path") != str(path)
        or not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o400
        or info.st_uid != os.getuid()
        or info.st_nlink != 1
        or value.get("device") != info.st_dev
        or value.get("inode") != info.st_ino
        or value.get("mode") != "0400"
        or value.get("uid") != info.st_uid
        or value.get("gid") != info.st_gid
        or value.get("link_count") != 1
        or value.get(size_key) != (0 if initial else info.st_size)
    ):
        raise SourceConsumerError("V10 sbatch capture identity changed")


def _validate_capture_record(
    value: Any, *, path: Path, raw: bytes, initial: Any,
) -> tuple[int, int]:
    try:
        info = path.lstat()
    except OSError as err:
        raise SourceConsumerError("cannot inspect V10 sbatch capture") from err
    if (
        type(value) is not dict
        or set(value) != {
            "path", "bytes", "sha256", "initial_identity",
            "final_identity",
        }
        or value.get("path") != str(path)
        or value.get("bytes") != len(raw)
        or value.get("sha256") != hashlib.sha256(raw).hexdigest()
        or value.get("initial_identity") != initial
    ):
        raise SourceConsumerError("V10 sbatch capture record changed")
    _capture_identity(initial, path=path, info=info, initial=True)
    _capture_identity(
        value.get("final_identity"), path=path, info=info, initial=False,
    )
    return info.st_dev, info.st_ino


def _parsed_job_id(raw: bytes) -> str | None:
    try:
        value = raw.decode("ascii")
    except UnicodeDecodeError:
        return None
    match = JOB_ID_RE.fullmatch(value)
    return match.group(1) if match else None


def _validate_capture_bundle(
    *, intent: dict, result: dict, stdout_path: Path, stderr_path: Path,
    stdout_raw: bytes, stderr_raw: bytes,
) -> None:
    initial = intent.get("sbatch_capture_initial_identities")
    if type(initial) is not dict or set(initial) != {"stdout", "stderr"}:
        raise SourceConsumerError("V10 sbatch initial captures changed")
    identities = []
    for stream, path, raw in (
        ("stdout", stdout_path, stdout_raw),
        ("stderr", stderr_path, stderr_raw),
    ):
        identities.append(_validate_capture_record(
            result.get(stream), path=path, raw=raw, initial=initial[stream],
        ))
    if len(set(identities)) != 2:
        raise SourceConsumerError("V10 sbatch captures alias")


def _validate_poll_capture_bundle(
    intent: dict, result: dict | None, paths: Mapping[str, Path],
    raws: Mapping[str, bytes],
) -> None:
    initial = intent.get("capture_initial_identities")
    if type(initial) is not dict or set(initial) != {"stdout", "stderr"}:
        raise SourceConsumerError("V10 poll initial captures changed")
    identities = []
    for stream in ("stdout", "stderr"):
        path = paths[stream]
        try:
            info = path.lstat()
        except OSError as err:
            raise SourceConsumerError("cannot inspect V10 poll capture") from err
        if result is None:
            _capture_identity(initial[stream], path=path, info=info, initial=True)
            identities.append((info.st_dev, info.st_ino))
        else:
            identities.append(_validate_capture_record(
                result.get(stream), path=path, raw=raws[stream + ".bin"],
                initial=initial[stream],
            ))
    if len(set(identities)) != 2:
        raise SourceConsumerError("V10 poll captures alias")


def _validate_compute_launch_evidence(
    paths: V10PreflightPaths, raws: Mapping[str, bytes],
) -> tuple[dict, dict, dict]:
    intent_raw = raws["compute-canary-launch-intent-v10.json"]
    result_raw = raws["compute-canary-sbatch-result-v10.json"]
    receipt_raw = raws["compute-canary-launch-receipt-v10.json"]
    stdout_raw = raws["compute-canary-sbatch-stdout-v10.bin"]
    stderr_raw = raws["compute-canary-sbatch-stderr-v10.bin"]
    intent = _decode_object(intent_raw, "V10 compute launch intent")
    result = _decode_object(result_raw, "V10 compute sbatch result")
    receipt = _decode_object(receipt_raw, "V10 compute launch receipt")
    intent_keys = {
        "schema", "campaign", "recorded_utc", "submission_token",
        "repository_commit_id", "code_manifest_sha256",
        "controller_publisher_canary_receipt_sha256", "resource_profile",
        "root_identities", "slurm_program", "capture_protocol",
        "sbatch_capture_initial_identities", "submit_command",
        "prior_runtime_payloads_read", "prior_runtime_payload_bytes_read",
        "prior_runtime_payloads_reused",
    }
    result_keys = {
        "schema", "campaign", "launch_intent_sha256",
        "submit_command_sha256", "slurm_program_sha256",
        "process_returncode", "stdout", "stderr", "parsed_job_id",
        "accepted_by_launcher", "raw_streams_preserved",
    }
    receipt_keys = {
        "schema", "campaign", "job_id", "accepted_utc",
        "submission_token", "repository_commit_id", "code_manifest_sha256",
        "controller_publisher_canary_receipt_sha256",
        "launch_intent_sha256", "sbatch_result_sha256", "resource_profile",
        "root_identities", "slurm_program", "launch_recovered",
        "recovery_evidence",
    }
    token = intent.get("submission_token")
    command = _submit_command(token, canary=True) if (
        type(token) is str and TOKEN_RE.fullmatch(token) is not None
    ) else None
    roots = {
        "artifact_dir": paths.artifact_dir,
        "output_dir": paths.compute_output_root,
        "tmpdir_root": COMPUTE_CANARY_TMP_ROOT,
        "log_root": COMPUTE_CANARY_LOG_ROOT,
    }
    if (
        set(intent) != intent_keys
        or intent.get("schema") != COMPUTE_LAUNCH_INTENT_SCHEMA
        or intent.get("campaign") != "v10-compute-canary"
        or command is None
        or COMMIT_RE.fullmatch(intent.get("repository_commit_id", "")) is None
        or not _is_sha(intent.get("code_manifest_sha256"))
        or not _is_sha(
            intent.get("controller_publisher_canary_receipt_sha256")
        )
        or intent.get("resource_profile") != _resource_profile("0-0")
        or intent.get("capture_protocol") != CAPTURE_PROTOCOL
        or intent.get("submit_command") != command
        or intent.get("prior_runtime_payloads_read") != 0
        or intent.get("prior_runtime_payload_bytes_read") != 0
        or intent.get("prior_runtime_payloads_reused") != 0
    ):
        raise SourceConsumerError("V10 compute launch intent changed")
    _utc_timestamp(intent["recorded_utc"], "V10 compute intent timestamp")
    _validate_root_records(intent.get("root_identities"), roots)
    _validate_slurm_record(
        intent.get("slurm_program"), template=COMPUTE_CANARY_SLURM_PROGRAM,
    )
    if (
        set(result) != result_keys
        or result.get("schema") != COMPUTE_SBATCH_RESULT_SCHEMA
        or result.get("campaign") != "v10-compute-canary"
        or result.get("launch_intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or result.get("submit_command_sha256") != _digest(command)
        or result.get("slurm_program_sha256")
        != intent["slurm_program"]["rendered_sha256"]
        or type(result.get("process_returncode")) is not int
        or result.get("process_returncode") != 0
        or result.get("raw_streams_preserved") is not True
    ):
        raise SourceConsumerError("V10 compute sbatch result changed")
    _validate_capture_bundle(
        intent=intent, result=result,
        stdout_path=paths.compute_sbatch_stdout,
        stderr_path=paths.compute_sbatch_stderr,
        stdout_raw=stdout_raw, stderr_raw=stderr_raw,
    )
    parsed_job_id = _parsed_job_id(stdout_raw)
    if (
        parsed_job_id is None
        or result.get("parsed_job_id") != parsed_job_id
        or result.get("accepted_by_launcher") is not True
        or set(receipt) != receipt_keys
        or receipt.get("schema") != COMPUTE_LAUNCH_SCHEMA
        or receipt.get("campaign") != "v10-compute-canary"
        or receipt.get("job_id") != parsed_job_id
        or receipt.get("submission_token") != token
        or receipt.get("repository_commit_id")
        != intent["repository_commit_id"]
        or receipt.get("code_manifest_sha256")
        != intent["code_manifest_sha256"]
        or receipt.get("controller_publisher_canary_receipt_sha256")
        != intent["controller_publisher_canary_receipt_sha256"]
        or receipt.get("launch_intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or receipt.get("sbatch_result_sha256")
        != hashlib.sha256(result_raw).hexdigest()
        or receipt.get("resource_profile") != intent["resource_profile"]
        or receipt.get("root_identities") != intent["root_identities"]
        or receipt.get("slurm_program") != intent["slurm_program"]
        or receipt.get("launch_recovered") is not False
        or receipt.get("recovery_evidence") is not None
    ):
        raise SourceConsumerError("V10 compute launch receipt changed")
    accepted = _utc_timestamp(
        receipt["accepted_utc"], "V10 compute acceptance timestamp",
    )
    recorded = _utc_timestamp(
        intent["recorded_utc"], "V10 compute intent timestamp",
    )
    if accepted < recorded:
        raise SourceConsumerError("V10 compute acceptance precedes intent")
    return intent, result, receipt


def _validate_full_launch_evidence(
    paths: V10Paths, raws: Mapping[str, bytes],
) -> tuple[dict, dict, dict]:
    intent_raw = raws["source-audit-launch-intent-v10.json"]
    result_raw = raws["source-audit-sbatch-result-v10.json"]
    receipt_raw = raws["source-audit-launch-receipt-v10.json"]
    stdout_raw = raws["source-audit-sbatch-stdout-v10.bin"]
    stderr_raw = raws["source-audit-sbatch-stderr-v10.bin"]
    intent = _decode_object(intent_raw, "V10 full launch intent")
    result = _decode_object(result_raw, "V10 full sbatch result")
    receipt = _decode_object(receipt_raw, "V10 full launch receipt")
    intent_keys = {
        "schema", "campaign", "recorded_utc", "submission_token",
        "repository_commit_id", "resource_profile", "array_mapping",
        "source_inventory", "source_inventory_sha256", "code_manifest",
        "code_manifest_sha256", "slurm_program", "root_identities",
        "execution_environment", "capture_protocol",
        "sbatch_capture_initial_identities", "submit_command",
        "preflight_binding", "prior_runtime_payloads_read",
        "prior_runtime_payload_bytes_read", "prior_runtime_payloads_reused",
        "selective_recovery_authorized", "whole_campaign_fresh",
    }
    result_keys = {
        "schema", "launch_intent_sha256", "submit_command_sha256",
        "slurm_program_sha256", "capture_protocol", "process_observation",
        "stdout", "stderr", "parsed_job_id", "accepted_by_launcher",
        "raw_streams_preserved",
    }
    receipt_keys = {
        "schema", "campaign", "job_id", "submission_token", "accepted_utc",
        "repository_commit_id", "source_inventory_sha256",
        "code_manifest_sha256", "launch_intent_sha256",
        "sbatch_result_sha256", "resource_profile", "root_identities",
        "slurm_program", "preflight_authorization", "launch_recovered",
        "recovery_evidence", "prior_runtime_payloads_read",
        "prior_runtime_payload_bytes_read", "prior_runtime_payloads_reused",
        "selective_recovery_authorized", "whole_campaign_fresh",
    }
    token = intent.get("submission_token")
    command = _submit_command(token, canary=False) if (
        type(token) is str and TOKEN_RE.fullmatch(token) is not None
    ) else None
    pairs = [[2 * shard, 2 * shard + 1] for shard in range(SHARD_COUNT)]
    array_mapping = {
        "logical_shards": SHARD_COUNT,
        "candidate_count": CANDIDATE_COUNT,
        "rule": "array element s owns candidates 2s and 2s+1",
        "candidate_index_first": 0,
        "candidate_index_last": CANDIDATE_COUNT - 1,
        "candidate_pairs_sha256": _digest(pairs),
        "independent_of_prior_scheduler_rows": True,
    }
    roots = {
        "artifact_dir": paths.artifact_dir,
        "log_root": FULL_LOG_ROOT,
        "output_dir": paths.data_root,
        "tmpdir_root": FULL_TMP_ROOT,
    }
    zero_prior = {
        "prior_runtime_payloads_read": 0,
        "prior_runtime_payload_bytes_read": 0,
        "prior_runtime_payloads_reused": 0,
        "selective_recovery_authorized": False,
        "whole_campaign_fresh": True,
    }
    if (
        set(intent) != intent_keys
        or intent.get("schema") != LAUNCH_SCHEMA + "/intent"
        or intent.get("campaign") != CAMPAIGN
        or command is None
        or COMMIT_RE.fullmatch(intent.get("repository_commit_id", "")) is None
        or not _is_sha(intent.get("source_inventory_sha256"))
        or not _is_sha(intent.get("code_manifest_sha256"))
        or intent.get("resource_profile") != _resource_profile("0-819")
        or intent.get("array_mapping") != array_mapping
        or intent.get("source_inventory") != {
            "path": str(paths.data_root / "source-inventory-v10.json"),
            "sha256": intent.get("source_inventory_sha256"),
            "candidate_count": CANDIDATE_COUNT,
        }
        or intent.get("execution_environment") != _execution_environment()
        or intent.get("capture_protocol") != CAPTURE_PROTOCOL
        or intent.get("submit_command") != command
        or any(intent.get(key) != value for key, value in zero_prior.items())
        or type(intent.get("preflight_binding")) is not dict
    ):
        raise SourceConsumerError("V10 full launch intent changed")
    _utc_timestamp(intent["recorded_utc"], "V10 full intent timestamp")
    _validate_root_records(intent.get("root_identities"), roots)
    _validate_slurm_record(intent.get("slurm_program"), template=FULL_SLURM_PROGRAM)
    _validate_code_manifest_record(
        intent.get("code_manifest"), path=paths.code_manifest,
        sha256=intent["code_manifest_sha256"],
    )
    process = result.get("process_observation")
    if (
        set(result) != result_keys
        or result.get("schema") != SBATCH_RESULT_SCHEMA
        or result.get("launch_intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or result.get("submit_command_sha256") != _digest(command)
        or result.get("slurm_program_sha256")
        != intent["slurm_program"]["rendered_sha256"]
        or result.get("capture_protocol") != CAPTURE_PROTOCOL
        or type(process) is not dict
        or process != {
            "kind": "completed-process", "returncode": 0,
            "os_error_type": None, "os_error_errno": None,
        }
        or result.get("raw_streams_preserved") is not True
    ):
        raise SourceConsumerError("V10 full sbatch result changed")
    _validate_capture_bundle(
        intent=intent, result=result,
        stdout_path=paths.sbatch_stdout, stderr_path=paths.sbatch_stderr,
        stdout_raw=stdout_raw, stderr_raw=stderr_raw,
    )
    parsed_job_id = _parsed_job_id(stdout_raw)
    recovered = receipt.get("launch_recovered")
    expected_recovery = None if recovered is False else {
        "source": "retained-sbatch-stdout",
        "job_id": parsed_job_id,
        "stdout_sha256": hashlib.sha256(stdout_raw).hexdigest(),
        "accepted_returncode_zero": True,
        "scheduler_queries_during_recovery": 0,
        "no_resubmission": True,
    }
    if (
        parsed_job_id is None
        or result.get("parsed_job_id") != parsed_job_id
        or result.get("accepted_by_launcher") is not True
        or set(receipt) != receipt_keys
        or receipt.get("schema") != LAUNCH_SCHEMA
        or receipt.get("campaign") != CAMPAIGN
        or receipt.get("job_id") != parsed_job_id
        or receipt.get("submission_token") != token
        or receipt.get("repository_commit_id")
        != intent["repository_commit_id"]
        or receipt.get("source_inventory_sha256")
        != intent["source_inventory_sha256"]
        or receipt.get("code_manifest_sha256")
        != intent["code_manifest_sha256"]
        or receipt.get("launch_intent_sha256")
        != hashlib.sha256(intent_raw).hexdigest()
        or receipt.get("sbatch_result_sha256")
        != hashlib.sha256(result_raw).hexdigest()
        or receipt.get("resource_profile") != intent["resource_profile"]
        or receipt.get("root_identities") != intent["root_identities"]
        or receipt.get("slurm_program") != intent["slurm_program"]
        or receipt.get("preflight_authorization")
        != intent["preflight_binding"]
        or type(recovered) is not bool
        or receipt.get("recovery_evidence") != expected_recovery
        or any(receipt.get(key) != value for key, value in zero_prior.items())
    ):
        raise SourceConsumerError("V10 full launch receipt changed")
    accepted = _utc_timestamp(
        receipt["accepted_utc"], "V10 full acceptance timestamp",
    )
    recorded = _utc_timestamp(
        intent["recorded_utc"], "V10 full intent timestamp",
    )
    if accepted < recorded:
        raise SourceConsumerError("V10 full acceptance precedes intent")
    return intent, result, receipt


def _snapshot(reader: SnapshotReader, revision: str, names: list[str], label: str) -> dict[str, bytes]:
    try:
        value = reader(revision, names)
    except Exception as err:
        raise SourceConsumerError("cannot read " + label + " snapshot") from err
    if type(value) is not dict or set(value) != set(names) or any(type(raw) is not bytes for raw in value.values()):
        raise SourceConsumerError(label + " snapshot closure changed")
    return value


def _relative(path: Path) -> str:
    try:
        relative = Path(os.path.abspath(path)).relative_to(REPO).as_posix()
    except ValueError as err:
        raise SourceConsumerError("evidence path is outside the repository") from err
    if not relative or ".." in Path(relative).parts:
        raise SourceConsumerError("unsafe evidence path")
    return relative


def _manifest_closure(
    manifest_path: Path, expected_sha: str, source_revision: str,
    seal_revision: str, reader: SnapshotReader,
) -> tuple[dict[str, str], dict[str, bytes]]:
    relative_manifest = _relative(manifest_path)
    source_manifest = _snapshot(reader, source_revision, [relative_manifest], "V10 source manifest")[relative_manifest]
    if hashlib.sha256(source_manifest).hexdigest() != expected_sha or not source_manifest.endswith(b"\n"):
        raise SourceConsumerError("V10 committed code manifest changed")
    records: dict[str, str] = {}
    old = re.compile(r"(?:^|[_/-])v(?:[1-9])(?:[_.-/]|$)")
    try:
        lines = source_manifest.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise SourceConsumerError("V10 code manifest is not ASCII") from err
    for line in lines:
        match = re.fullmatch(r"([0-9a-f]{64})  ([!-~]+)", line)
        if match is None:
            raise SourceConsumerError("V10 code manifest record changed")
        digest, relative = match.groups()
        candidate = Path(relative)
        if relative in records or candidate.is_absolute() or ".." in candidate.parts or old.search(relative):
            raise SourceConsumerError("V1-V9 source or an unsafe path entered V10 closure")
        records[relative] = digest
    translator_files = {
        relative for relative in records
        if relative.startswith("src/translate/") and relative.endswith(".py")
    }
    if (
        len(records) != 62
        or len(translator_files) != 38
        or set(records) != REQUIRED_SOURCE_FILES | translator_files
    ):
        raise SourceConsumerError("V10 code manifest omits a required trust-boundary file")
    names = [relative_manifest, *records]
    source = _snapshot(reader, source_revision, names, "V10 source closure")
    sealed = _snapshot(reader, seal_revision, names, "V10 sealed source closure")
    if source[relative_manifest] != source_manifest:
        raise SourceConsumerError("V10 manifest changed between reads")
    for relative, digest in {relative_manifest: expected_sha, **records}.items():
        if source[relative] != sealed[relative] or hashlib.sha256(source[relative]).hexdigest() != digest:
            raise SourceConsumerError("V10 source closure changed at seal")
    return {relative_manifest: expected_sha, **records}, sealed


def _validate_rendered_slurm(
    intent: dict, sealed_source: Mapping[str, bytes], *, template: Path,
    inventory_sha256: str | None,
) -> None:
    relative = _relative(template)
    try:
        raw = sealed_source[relative]
        code_sha = intent["code_manifest_sha256"].encode("ascii")
        revision = intent["repository_commit_id"].encode("ascii")
    except (KeyError, UnicodeEncodeError, AttributeError) as err:
        raise SourceConsumerError("V10 rendered Slurm inputs changed") from err
    manifest_placeholder = b"__V10_CODE_MANIFEST_SHA256__"
    revision_placeholder = b"__V10_REPOSITORY_COMMIT_ID__"
    inventory_placeholder = b"__V10_SOURCE_INVENTORY_SHA256__"
    expected_counts = {
        manifest_placeholder: 1,
        revision_placeholder: 1,
        inventory_placeholder: 0 if inventory_sha256 is None else 1,
    }
    if any(raw.count(marker) != count for marker, count in expected_counts.items()):
        raise SourceConsumerError("V10 Slurm template placeholders changed")
    rendered = raw.replace(manifest_placeholder, code_sha).replace(
        revision_placeholder, revision,
    )
    if inventory_sha256 is not None:
        try:
            inventory_raw = inventory_sha256.encode("ascii")
        except (UnicodeEncodeError, AttributeError) as err:
            raise SourceConsumerError("V10 inventory digest changed") from err
        rendered = rendered.replace(inventory_placeholder, inventory_raw)
    slurm = intent["slurm_program"]
    if (
        slurm["template_sha256"] != hashlib.sha256(raw).hexdigest()
        or slurm["rendered_sha256"] != hashlib.sha256(rendered).hexdigest()
        or slurm["rendered_bytes"] != len(rendered)
    ):
        raise SourceConsumerError("V10 rendered Slurm program changed")


def _artifact_namespace(directory: Path, fixed: tuple[str, ...], poll_name: str) -> None:
    try:
        directory_info = directory.lstat()
        entries = list(os.scandir(directory))
    except OSError as err:
        raise SourceConsumerError("cannot enumerate V10 artifact namespace") from err
    if directory.is_symlink() or not stat.S_ISDIR(directory_info.st_mode) or stat.S_IMODE(directory_info.st_mode) != 0o700 or directory_info.st_uid != os.getuid():
        raise SourceConsumerError("V10 artifact directory identity changed")
    expected = set(fixed) | {poll_name}
    if {entry.name for entry in entries} != expected:
        raise SourceConsumerError("V10 artifact namespace is not exact")
    for entry in entries:
        if entry.is_symlink() or (entry.name == poll_name) is not entry.is_dir(follow_symlinks=False):
            raise SourceConsumerError("V10 artifact namespace entry changed type")
    poll = directory / poll_name
    poll_info = poll.lstat()
    if poll.is_symlink() or not stat.S_ISDIR(poll_info.st_mode) or stat.S_IMODE(poll_info.st_mode) != 0o700 or poll_info.st_uid != os.getuid():
        raise SourceConsumerError("V10 scheduler-poll directory identity changed")


def _poll_bundle(
    poll_dir: Path, *, campaign: str, poll_schema: str, expected_tasks: int,
    launch_receipt_sha256: str, launch_recorded_utc: str,
    expected_job_id: str, expected_job_name: str,
) -> tuple[dict[str, bytes], str, dict]:
    try:
        entries = list(os.scandir(poll_dir))
    except OSError as err:
        raise SourceConsumerError("cannot enumerate scheduler poll evidence") from err
    grouped: dict[int, dict[str, Path]] = {}
    for entry in entries:
        match = POLL_RE.fullmatch(entry.name)
        if match is None or entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            raise SourceConsumerError("scheduler poll namespace changed")
        grouped.setdefault(int(match.group(1)), {})[match.group(2)] = Path(entry.path)
    def valid_group(value: Mapping[str, Path]) -> bool:
        names = set(value)
        return names == set(POLL_SUFFIXES) or (
            "abandoned.json" in names and "receipt.json" not in names
            and {"intent.json", "stdout.bin", "stderr.bin", "abandoned.json"}
            <= names
            and names <= {
                "intent.json", "stdout.bin", "stderr.bin", "result.json",
                "abandoned.json",
            }
        )
    if not grouped or sorted(grouped) != list(range(len(grouped))) or any(not valid_group(value) for value in grouped.values()):
        raise SourceConsumerError("scheduler polls are not exact and contiguous")
    raws: dict[str, bytes] = {}
    last_receipt_sha = ""
    job_id: str | None = None
    final_receipt: dict | None = None
    terminal_seen = False
    launch_recorded = _utc_timestamp(
        launch_recorded_utc, "scheduler launch timestamp",
    )
    next_not_before = launch_recorded + datetime.timedelta(seconds=3600)
    for index in range(len(grouped)):
        if terminal_seen:
            raise SourceConsumerError("scheduler poll follows a terminal poll")
        files = grouped[index]
        suffixes = tuple(sorted(files))
        per_poll = {suffix: _read_regular(files[suffix], "scheduler poll " + suffix) for suffix in suffixes}
        json_suffixes = tuple(
            suffix for suffix in ("intent.json", "result.json", "receipt.json", "abandoned.json")
            if suffix in per_poll
        )
        for suffix in json_suffixes:
            try:
                value = json.loads(per_poll[suffix].decode("ascii"))
            except (UnicodeDecodeError, json.JSONDecodeError) as err:
                raise SourceConsumerError("scheduler poll JSON changed") from err
            if type(value) is not dict or per_poll[suffix] != _canonical(value):
                raise SourceConsumerError("scheduler poll JSON is not canonical")
        intent = json.loads(per_poll["intent.json"])
        command = [
            "/usr/bin/sacct", "-j", expected_job_id, "-X", "--array",
            "-n", "-P",
            "--format=JobIDRaw,Account,Partition,QOS,ReqCPUS,ReqMem,Timelimit,State,ExitCode,Restarts,JobName",
        ]
        if "abandoned.json" in per_poll:
            abandoned = json.loads(per_poll["abandoned.json"])
            abandoned_keys = {
                "schema", "campaign", "poll_index", "job_id",
                "recorded_utc", "successor_not_before_utc", "intent_sha256", "durable_files", "outcome",
                "authorizing", "scheduler_queries_during_recovery",
            }
            abandoned_time = _utc_timestamp(
                abandoned.get("recorded_utc"), "abandoned poll timestamp",
            )
            intent_time = _utc_timestamp(
                intent.get("recorded_utc"), "abandoned poll intent timestamp",
            )
            intent_not_before = _utc_timestamp(
                intent.get("not_before_utc"), "abandoned poll cadence timestamp",
            )
            successor_not_before = _utc_timestamp(
                abandoned.get("successor_not_before_utc"),
                "abandoned poll successor timestamp",
            )
            durable = {
                files[suffix].name: hashlib.sha256(raw).hexdigest()
                for suffix, raw in per_poll.items() if suffix != "abandoned.json"
            }
            if (
                set(abandoned) != abandoned_keys
                or abandoned.get("schema") != poll_schema + "/abandoned"
                or abandoned.get("campaign") != campaign
                or abandoned.get("poll_index") != index
                or abandoned.get("job_id") != expected_job_id
                or abandoned.get("intent_sha256")
                != hashlib.sha256(per_poll["intent.json"]).hexdigest()
                or abandoned.get("durable_files") != durable
                or abandoned.get("outcome") != "abandoned-unknown"
                or abandoned.get("authorizing") is not False
                or abandoned.get("scheduler_queries_during_recovery") != 0
                or abandoned_time.tzinfo is None or intent_time.tzinfo is None
                or intent_not_before.tzinfo is None
                or successor_not_before.tzinfo is None
                or set(intent) != {
                    "schema", "campaign", "poll_index", "job_id",
                    "recorded_utc", "not_before_utc",
                    "previous_poll_receipt_sha256", "launch_receipt_sha256",
                    "command", "capture_initial_identities",
                }
                or intent.get("schema") != poll_schema + "/intent"
                or intent.get("campaign") != campaign
                or intent.get("poll_index") != index
                or intent.get("job_id") != expected_job_id
                or intent.get("launch_receipt_sha256") != launch_receipt_sha256
                or intent.get("command") != command
                or intent_not_before != next_not_before
                or intent_time < intent_not_before
                or abandoned_time
                < intent_time + datetime.timedelta(seconds=3600)
                or successor_not_before
                != intent_time + datetime.timedelta(seconds=3600)
                or intent.get("previous_poll_receipt_sha256")
                != (None if index == 0 else last_receipt_sha)
            ):
                raise SourceConsumerError("abandoned poll recovery contract changed")
            abandoned_result = None
            if "result.json" in per_poll:
                abandoned_result = json.loads(per_poll["result.json"])
                if (
                    set(abandoned_result) != {
                        "schema", "campaign", "poll_index", "intent_sha256",
                        "command_sha256", "process_returncode", "stdout",
                        "stderr", "single_scheduler_query",
                    }
                    or abandoned_result.get("schema") != poll_schema + "/result"
                    or abandoned_result.get("campaign") != campaign
                    or abandoned_result.get("poll_index") != index
                    or abandoned_result.get("intent_sha256")
                    != hashlib.sha256(per_poll["intent.json"]).hexdigest()
                    or abandoned_result.get("command_sha256") != _digest(command)
                    or type(abandoned_result.get("process_returncode")) is not int
                    or abandoned_result.get("single_scheduler_query") is not True
                ):
                    raise SourceConsumerError("abandoned poll result changed")
            _validate_poll_capture_bundle(
                intent, abandoned_result,
                {stream: files[stream + ".bin"] for stream in ("stdout", "stderr")},
                per_poll,
            )
            last_receipt_sha = hashlib.sha256(per_poll["abandoned.json"]).hexdigest()
            next_not_before = successor_not_before
            for suffix, raw in per_poll.items():
                raws[files[suffix].name] = raw
            continue
        result = json.loads(per_poll["result.json"])
        receipt = json.loads(per_poll["receipt.json"])
        intent_keys = {
            "schema", "campaign", "poll_index", "job_id", "recorded_utc",
            "not_before_utc", "previous_poll_receipt_sha256",
            "launch_receipt_sha256", "command", "capture_initial_identities",
        }
        result_keys = {
            "schema", "campaign", "poll_index", "intent_sha256",
            "command_sha256", "process_returncode", "stdout", "stderr",
            "single_scheduler_query",
        }
        recorded = _utc_timestamp(
            intent.get("recorded_utc"), "scheduler poll timestamp",
        )
        not_before = _utc_timestamp(
            intent.get("not_before_utc"), "scheduler poll cadence timestamp",
        )
        if (
            set(intent) != intent_keys or intent.get("schema") != poll_schema + "/intent"
            or intent.get("campaign") != campaign or intent.get("poll_index") != index
            or intent.get("job_id") != expected_job_id
            or intent.get("previous_poll_receipt_sha256") != (None if index == 0 else last_receipt_sha)
            or intent.get("launch_receipt_sha256") != launch_receipt_sha256
            or intent.get("command") != command
            or not_before != next_not_before
            or recorded < not_before
            or set(result) != result_keys or result.get("schema") != poll_schema + "/result"
            or result.get("campaign") != campaign or result.get("poll_index") != index
            or result.get("intent_sha256") != hashlib.sha256(per_poll["intent.json"]).hexdigest()
            or result.get("command_sha256") != _digest(command)
            or type(result.get("process_returncode")) is not int
            or result.get("process_returncode") != 0
            or result.get("single_scheduler_query") is not True
        ):
            raise SourceConsumerError("scheduler poll intent/result contract changed")
        _validate_poll_capture_bundle(
            intent, result,
            {stream: files[stream + ".bin"] for stream in ("stdout", "stderr")},
            per_poll,
        )
        if per_poll["stderr.bin"] != b"":
            raise SourceConsumerError("scheduler poll retained nonempty stderr")
        receipt_keys = {
            "schema", "campaign", "poll_index", "job_id", "recorded_utc",
            "not_before_utc", "previous_poll_receipt_sha256", "intent_sha256",
            "stdout_sha256", "stderr_sha256", "result_sha256",
            "scheduler_rows", "scheduler_contract_rows", "state_counts",
            "all_terminal", "all_success",
        }
        expected = {
            "poll_index": index,
            "intent_sha256": hashlib.sha256(per_poll["intent.json"]).hexdigest(),
            "stdout_sha256": hashlib.sha256(per_poll["stdout.bin"]).hexdigest(),
            "stderr_sha256": hashlib.sha256(per_poll["stderr.bin"]).hexdigest(),
            "result_sha256": hashlib.sha256(per_poll["result.json"]).hexdigest(),
        }
        if (
            set(receipt) != receipt_keys
            or receipt.get("schema") != poll_schema + "/receipt"
            or receipt.get("campaign") != campaign
            or any(receipt.get(key) != value for key, value in expected.items())
            or receipt.get("previous_poll_receipt_sha256")
            != (None if index == 0 else last_receipt_sha)
            or type(receipt.get("job_id")) is not str
            or not receipt["job_id"].isdigit()
            or receipt["job_id"] != expected_job_id
            or (job_id is not None and receipt["job_id"] != job_id)
            or receipt.get("recorded_utc") != intent["recorded_utc"]
            or receipt.get("not_before_utc") != intent["not_before_utc"]
            or type(receipt.get("scheduler_rows")) is not list
            or type(receipt.get("scheduler_contract_rows")) is not list
            or type(receipt.get("state_counts")) is not dict
            or type(receipt.get("all_terminal")) is not bool
            or type(receipt.get("all_success")) is not bool
        ):
            raise SourceConsumerError("scheduler poll receipt hash chain changed")
        parsed_rows = []
        parsed_contracts = []
        try:
            lines = per_poll["stdout.bin"].decode("ascii").splitlines()
        except UnicodeDecodeError as err:
            raise SourceConsumerError("scheduler stdout is not ASCII") from err
        for line in lines:
            fields = line.split("|")
            if len(fields) != 11:
                raise SourceConsumerError("scheduler stdout row changed")
            raw_id, account, partition, qos, cpus, memory, limit, state, exit_code, restarts, job_name = fields
            match = re.fullmatch(re.escape(expected_job_id) + r"_([0-9]+)", raw_id)
            if match is None or cpus != "1" or restarts != "0":
                raise SourceConsumerError("scheduler stdout identity changed")
            task = int(match.group(1))
            parsed_rows.append({"array_task": task, "state": state, "exit_code": exit_code, "partition": partition, "restarts": 0})
            parsed_contracts.append({"array_task": task, "account": account, "partition": partition, "qos": qos, "req_cpus": 1, "req_mem": memory, "time_limit": limit, "state": state, "exit_code": exit_code, "restarts": 0, "job_name": job_name})
        parsed_rows.sort(key=lambda row: row["array_task"])
        parsed_contracts.sort(key=lambda row: row["array_task"])
        rows = receipt["scheduler_rows"]
        contracts = receipt["scheduler_contract_rows"]
        if rows != parsed_rows or contracts != parsed_contracts:
            raise SourceConsumerError("scheduler receipt does not match retained stdout")
        if (
            len(rows) != expected_tasks
            or [row.get("array_task") if type(row) is dict else None for row in rows]
            != list(range(expected_tasks))
            or any(
                set(row) != {"array_task", "state", "exit_code", "partition", "restarts"}
                or row["state"] not in ACTIVE_STATES | TERMINAL_STATES
                or re.fullmatch(r"[0-9]+:[0-9]+", row["exit_code"]) is None
                or row["partition"] != "fat" or row["restarts"] != 0
                for row in rows
            )
        ):
            raise SourceConsumerError("scheduler poll row contract changed")
        observed_counts: dict[str, int] = {}
        for row in rows:
            observed_counts[row["state"]] = observed_counts.get(row["state"], 0) + 1
        all_terminal = all(row["state"] in TERMINAL_STATES for row in rows)
        all_success = all(
            row["state"] == "COMPLETED" and row["exit_code"] == "0:0"
            for row in rows
        )
        if receipt["state_counts"] != observed_counts or receipt["all_terminal"] is not all_terminal or receipt["all_success"] is not all_success:
            raise SourceConsumerError("scheduler poll summary changed")
        if (
                len(contracts) != expected_tasks
                or [row.get("array_task") if type(row) is dict else None for row in contracts]
                != list(range(expected_tasks))
                or any(
                    set(row) != {"array_task", "account", "partition", "qos", "req_cpus", "req_mem", "time_limit", "state", "exit_code", "restarts", "job_name"}
                    or row["account"] != "naiss2025-5-561-cpu"
                    or row["partition"] != "fat" or row["qos"] != "normal"
                    or row["req_cpus"] != 1 or row["req_mem"] != "26G"
                    or row["time_limit"] != "01:10:00"
                    or row["state"] != rows[row["array_task"]]["state"]
                    or row["exit_code"] != rows[row["array_task"]]["exit_code"]
                    or row["restarts"] != 0 or row["job_name"] != expected_job_name
                    for row in contracts
                )
        ):
            raise SourceConsumerError("scheduler poll resource contract changed")
        job_id = receipt["job_id"]
        final_receipt = receipt
        terminal_seen = all_terminal
        next_not_before = recorded + datetime.timedelta(seconds=3600)
        last_receipt_sha = hashlib.sha256(per_poll["receipt.json"]).hexdigest()
        for suffix, raw in per_poll.items():
            raws[files[suffix].name] = raw
    if final_receipt is None or final_receipt.get("all_terminal") is not True or final_receipt.get("all_success") is not True:
        raise SourceConsumerError("final scheduler poll is not all-success terminal")
    return raws, last_receipt_sha, final_receipt


def _terminal_gate(
    value: dict, *, schema: str, campaign: str, completed: int,
    last_poll_sha: str, expected_job_id: str,
) -> None:
    required = {
        "schema": schema,
        "campaign": campaign,
        "all_success": True,
        "state_counts": {"COMPLETED": completed},
        "terminal_poll_receipt_sha256": last_poll_sha,
    }
    if type(value) is not dict or value != {**required, "job_id": value.get("job_id")}:
        raise SourceConsumerError("V10 scheduler terminal gate did not authorize payload")
    if (
        type(value.get("job_id")) is not str
        or not value["job_id"].isdigit()
        or value["job_id"] != expected_job_id
    ):
        raise SourceConsumerError("V10 scheduler terminal job identity changed")


def _artifact_snapshot(
    directory: Path, fixed: tuple[str, ...], poll_name: str,
    fixed_raws: Mapping[str, bytes], poll_raws: Mapping[str, bytes],
    seal_revision: str, reader: SnapshotReader,
) -> dict[str, str]:
    relative_raws = {
        _relative(directory / name): raw for name, raw in fixed_raws.items()
    }
    relative_raws.update({
        _relative(directory / poll_name / name): raw for name, raw in poll_raws.items()
    })
    snapshot = _snapshot(reader, seal_revision, list(relative_raws), "V10 artifact closure")
    if snapshot != relative_raws:
        raise SourceConsumerError("V10 committed artifact bytes differ from consumed bytes")
    return {name: hashlib.sha256(raw).hexdigest() for name, raw in snapshot.items()}


def _candidate_resource_contract() -> dict:
    return {
        "schema": RESOURCE_CONTRACT_SCHEMA,
        "address_space_bytes": ADDRESS_SPACE_BYTES,
        "cpu_soft_seconds": CPU_SOFT_SECONDS,
        "cpu_hard_seconds": CPU_HARD_SECONDS,
        "child_wall_watchdog_seconds": CHILD_WALL_SECONDS,
        "wall_watchdog_is_scientific_exclusion": False,
        "memory_exit_code": 20,
        "cpu_time_exit_code": 21,
        "input_error_exit_code": 31,
        "handshake_failure_exit_code": 70,
        "release_byte_base64": "Rw==",
        "candidate_process_group_isolated": True,
        "candidate_process_creation_denied": True,
        "denied_process_syscalls": list(DENIED_PROCESS_SYSCALLS),
        "pinned_python_sha256": PYTHON_EXECUTABLE_SHA256,
        "prlimit_sha256": PRLIMIT_SHA256,
        "libseccomp_sha256": LIBSECCOMP_SHA256,
    }


def _valid_recorded_identity(value: Any, *, expected_mode: int | None) -> bool:
    return (
        type(value) is dict
        and set(value) == {"device", "inode", "mode", "uid", "size"}
        and all(type(value[key]) is int for key in value)
        and value["device"] >= 0
        and value["inode"] > 0
        and value["uid"] >= 0
        and value["size"] >= 0
        and (expected_mode is None or value["mode"] == expected_mode)
    )


def _validate_candidate_stream(value: Any, raw: bytes, expected_name: str) -> None:
    if (
        type(value) is not dict
        or set(value) != {
            "total_bytes", "sha256", "retained_path", "retained_bytes",
            "retained_sha256", "retention_limit_bytes", "truncated",
            "tail_base64", "tail_bytes",
        }
        or value.get("retained_path") != expected_name
        or type(value.get("total_bytes")) is not int
        or value["total_bytes"] < 0
        or not _is_sha(value.get("sha256"))
        or type(value.get("retained_bytes")) is not int
        or value["retained_bytes"]
        != min(value["total_bytes"], STREAM_PREFIX_BYTES)
        or value["retained_bytes"] != len(raw)
        or value.get("retained_sha256") != hashlib.sha256(raw).hexdigest()
        or value.get("retention_limit_bytes") != STREAM_PREFIX_BYTES
        or type(value.get("truncated")) is not bool
        or value["truncated"]
        is not (value["total_bytes"] > value["retained_bytes"])
        or type(value.get("tail_base64")) is not str
        or type(value.get("tail_bytes")) is not int
        or value["tail_bytes"] != min(value["total_bytes"], STREAM_TAIL_BYTES)
    ):
        raise SourceConsumerError("V10 candidate stream evidence changed")
    try:
        tail = base64.b64decode(value["tail_base64"], validate=True)
    except (ValueError, binascii.Error) as err:
        raise SourceConsumerError("V10 candidate stream tail changed") from err
    if (
        base64.b64encode(tail).decode("ascii") != value["tail_base64"]
        or len(tail) != value["tail_bytes"]
        or (not value["truncated"] and (
            value["total_bytes"] != len(raw)
            or value["sha256"] != hashlib.sha256(raw).hexdigest()
            or tail != raw[-STREAM_TAIL_BYTES:]
        ))
    ):
        raise SourceConsumerError("V10 candidate stream content changed")


def _validate_normalization(value: Any) -> None:
    if (
        type(value) is not dict
        or set(value) != {"schema", "num_normalized_axioms", "strategy"}
        or value.get("schema") != SCHEMA + "/normalization-evidence/v1"
        or value.get("strategy") != "axiom_based"
        or type(value.get("num_normalized_axioms")) is not int
        or value["num_normalized_axioms"] < 0
    ):
        raise SourceConsumerError("V10 normalization evidence changed")


def _validate_sas_summary(value: Any) -> None:
    integers = (
        "sas_version", "metric", "num_variables", "num_mutex_groups",
        "num_operators", "num_effects", "num_conditional_effects",
        "num_zero_cost_operators", "num_serialized_axioms",
    )
    optional = ("min_operator_cost", "max_operator_cost")
    if (
        type(value) is not dict
        or set(value) != SAS_KEYS
        or any(type(value.get(key)) is not int or value[key] < 0 for key in integers)
        or any(value.get(key) is not None and (
            type(value[key]) is not int or value[key] < 0
        ) for key in optional)
        or value.get("sas_version") != 3
        or value.get("metric") not in (0, 1)
        or (value.get("num_operators") == 0) is not (
            value.get("min_operator_cost") is None
            and value.get("max_operator_cost") is None
        )
        or (
            value.get("num_operators", 0) > 0
            and (
                type(value.get("min_operator_cost")) is not int
                or type(value.get("max_operator_cost")) is not int
            )
        )
        or (
            value.get("num_operators", 0) > 0
            and type(value.get("min_operator_cost")) is int
            and type(value.get("max_operator_cost")) is int
            and value.get("min_operator_cost") > value.get("max_operator_cost")
        )
    ):
        raise SourceConsumerError("V10 SAS summary changed")


def _support_reasons(sas: dict, normalized_axioms: int) -> list[str]:
    reasons = []
    if sas["num_operators"] < 1:
        reasons.append("no-serialized-operators")
    if (
        sas["num_zero_cost_operators"] != 0
        or sas["min_operator_cost"] is None
        or sas["min_operator_cost"] < 1
    ):
        reasons.append("nonpositive-serialized-operator-cost")
    if sas["num_serialized_axioms"] != 0:
        reasons.append("serialized-axioms")
    if sas["num_conditional_effects"] != 0:
        reasons.append("serialized-conditional-effects")
    if normalized_axioms != 0:
        reasons.append("normalized-axioms")
    return reasons


def _validate_source_snapshot(value: Any, inventory_record: Mapping[str, Any]) -> None:
    files = value.get("files") if type(value) is dict else None
    if (
        type(value) is not dict
        or set(value) != {
            "schema", "files", "candidate_private_working_directory",
            "source_hashes_verified_before_use",
            "identity_and_sha256_verified_after_use",
            "exact_snapshot_files_removed",
        }
        or value.get("schema") != SOURCE_SNAPSHOT_SCHEMA
        or value.get("candidate_private_working_directory") is not True
        or value.get("source_hashes_verified_before_use") is not True
        or value.get("identity_and_sha256_verified_after_use") is not True
        or value.get("exact_snapshot_files_removed") is not True
        or type(files) is not list
        or len(files) != 2
    ):
        raise SourceConsumerError("V10 source snapshot evidence changed")
    for item, role, file_key, hash_key, name in zip(
        files, ("domain", "problem"), ("domain_file", "problem_file"),
        ("domain_sha256", "problem_sha256"), ("domain.pddl", "problem.pddl"),
    ):
        if (
            type(item) is not dict
            or set(item) != {
                "role", "source_file", "source_identity", "snapshot_name",
                "snapshot_identity_before", "snapshot_identity_after",
                "bytes", "sha256",
            }
            or item.get("role") != role
            or item.get("source_file") != inventory_record[file_key]
            or item.get("snapshot_name") != name
            or item.get("sha256") != inventory_record[hash_key]
            or type(item.get("bytes")) is not int
            or item["bytes"] <= 0
            or not _valid_recorded_identity(
                item.get("source_identity"), expected_mode=None,
            )
            or not _valid_recorded_identity(
                item.get("snapshot_identity_before"), expected_mode=0o400,
            )
            or item.get("snapshot_identity_after")
            != item.get("snapshot_identity_before")
            or item["source_identity"]["size"] != item["bytes"]
            or item["snapshot_identity_before"]["size"] != item["bytes"]
        ):
            raise SourceConsumerError("V10 source snapshot file changed")


def _validate_candidate_record(
    task: Any, inventory_record: Mapping[str, Any], *, shard_index: int,
    position: int, candidate_origin: str, stream_raws: Mapping[str, bytes],
    code_manifest_sha256: str, repository_commit_id: str,
) -> None:
    contract = _candidate_resource_contract()
    if (
        type(task) is not dict
        or set(task) != CANDIDATE_RESULT_KEYS
        or any(task.get(key) != inventory_record[key] for key in INVENTORY_RECORD_KEYS)
        or task.get("schema") != CANDIDATE_SCHEMA
        or task.get("logical_shard_index") != shard_index
        or task.get("position_in_shard") != position
        or task.get("candidate_origin") != candidate_origin
        or task.get("translation_attempted") is not True
        or task.get("translator_command") != [
            "PINNED_PYTHON", "-B",
            "experiments/pdb_terminal_incidence_confirmation_translate_v10.py",
            "--", inventory_record["domain_file"], inventory_record["problem_file"],
        ]
        or task.get("code_manifest_sha256") != code_manifest_sha256
        or task.get("repository_commit_id") != repository_commit_id
        or task.get("resource_contract") != contract
        or task.get("resource_contract_sha256") != _digest(contract)
        or type(task.get("process_returncode")) is not int
        or task.get("complete_process_group_reaped") is not True
    ):
        raise SourceConsumerError("V10 candidate record changed")
    child = task.get("child_limit_attestation")
    if (
        type(child) is not dict
        or set(child) != {
            "schema", "pid", "process_group", "rlimit_as", "rlimit_cpu",
            "no_new_privs", "seccomp_mode", "seccomp_filters", "threads",
        }
        or child.get("schema") != SCHEMA + "/child-limit-evidence/v1"
        or type(child.get("pid")) is not int
        or child["pid"] <= 0
        or child.get("process_group") != child["pid"]
        or child.get("rlimit_as") != [ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES]
        or child.get("rlimit_cpu") != [CPU_SOFT_SECONDS, CPU_HARD_SECONDS]
        or child.get("no_new_privs") != 1
        or child.get("seccomp_mode") != 2
        or type(child.get("seccomp_filters")) is not int
        or child["seccomp_filters"] < 1
        or child.get("threads") != 1
    ):
        raise SourceConsumerError("V10 child-limit attestation changed")
    parent = task.get("parent_prlimit_observation")
    if (
        type(parent) is not dict
        or set(parent) != {
            "tool_sha256", "command", "stdout_sha256", "rlimit_as",
            "rlimit_cpu",
        }
        or parent.get("tool_sha256") != PRLIMIT_SHA256
        or parent.get("command") != [
            "/usr/bin/prlimit", "--pid", "CHILD_PID", "--as", "--cpu",
            "--output=RESOURCE,SOFT,HARD,UNITS", "--noheadings", "--raw",
        ]
        or parent.get("stdout_sha256") != PRLIMIT_STDOUT_SHA256
        or parent.get("rlimit_as") != [ADDRESS_SPACE_BYTES, ADDRESS_SPACE_BYTES]
        or parent.get("rlimit_cpu") != [CPU_SOFT_SECONDS, CPU_HARD_SECONDS]
    ):
        raise SourceConsumerError("V10 parent prlimit observation changed")
    isolation = task.get("parent_isolation_observation")
    if (
        type(isolation) is not dict
        or set(isolation) != {
            "status_sha256", "process_group", "no_new_privs", "seccomp_mode",
            "seccomp_filters", "threads", "process_creation_syscalls_denied",
            "libseccomp_sha256",
        }
        or not _is_sha(isolation.get("status_sha256"))
        or isolation.get("process_group") != child["pid"]
        or isolation.get("no_new_privs") != 1
        or isolation.get("seccomp_mode") != 2
        or isolation.get("seccomp_filters") != child["seccomp_filters"]
        or isolation.get("threads") != 1
        or isolation.get("process_creation_syscalls_denied")
        != list(DENIED_PROCESS_SYSCALLS)
        or isolation.get("libseccomp_sha256") != LIBSECCOMP_SHA256
    ):
        raise SourceConsumerError("V10 parent isolation observation changed")
    for stream in ("stdout", "stderr"):
        name = "candidate-{:04d}.{}.prefix".format(
            inventory_record["candidate_index"], stream,
        )
        _validate_candidate_stream(task.get(stream), stream_raws[stream], name)
    normalization = task.get("normalization")
    if normalization is not None:
        _validate_normalization(normalization)
    status = task.get("status")
    returncode = task["process_returncode"]
    if status == "success":
        _validate_sas_summary(task.get("sas"))
        expected_reasons = _support_reasons(
            task["sas"], normalization["num_normalized_axioms"],
        ) if normalization is not None else None
        valid = (
            returncode == 0
            and normalization is not None
            and type(task.get("sas_bytes")) is int
            and task["sas_bytes"] > 0
            and _is_sha(task.get("sas_sha256"))
            and task.get("partial_sas_evidence") is None
            and task.get("resource_exclusion_kind") is None
            and task.get("support_determined") is True
            and type(task.get("supported")) is bool
            and task.get("support_exclusion_reasons") == expected_reasons
            and task.get("supported") is (len(expected_reasons) == 0)
            and task.get("eligible_for_cohort") is task.get("supported")
        )
    elif status == "input-rejected":
        valid = (
            returncode == 31
            and normalization is None
            and task.get("sas") is None
            and task.get("sas_bytes") is None
            and task.get("sas_sha256") is None
            and task.get("partial_sas_evidence") is None
            and task.get("resource_exclusion_kind") is None
            and task.get("support_determined") is True
            and task.get("supported") is False
            and task.get("support_exclusion_reasons")
            == ["translation-input-rejected"]
            and task.get("eligible_for_cohort") is False
        )
    elif status == "resource-excluded":
        partial = task.get("partial_sas_evidence")
        valid_partial = partial is None or (
            type(partial) is dict
            and set(partial) == {"bytes", "sha256", "discarded"}
            and type(partial.get("bytes")) is int
            and partial["bytes"] >= 0
            and _is_sha(partial.get("sha256"))
            and partial.get("discarded") is True
        )
        expected_kind = "memory" if returncode == 20 else (
            "time" if returncode == 21 else None
        )
        valid = (
            expected_kind is not None
            and valid_partial
            and task.get("sas") is None
            and task.get("sas_bytes") is None
            and task.get("sas_sha256") is None
            and task.get("resource_exclusion_kind") == expected_kind
            and task.get("support_determined") is False
            and task.get("supported") is None
            and task.get("support_exclusion_reasons") is None
            and task.get("eligible_for_cohort") is False
        )
    else:
        valid = False
    _validate_source_snapshot(task.get("source_snapshot"), inventory_record)
    if not valid:
        raise SourceConsumerError("V10 candidate disposition changed")


def _validate_task_environment(
    environment: Any, *, shard_index: int, candidate_indices: list[int],
    job_id: str, inventory_sha256: str, code_manifest_sha256: str,
    repository_commit_id: str, tracked: Mapping[str, str],
    output_root_identity: Mapping[str, Any], shard_info: os.stat_result,
    result_raw: bytes,
) -> None:
    keys = {
        "schema", "array_job_id", "array_task_id", "slurm_restart_count",
        "candidate_indices", "task_tmp_identity", "code_manifest_sha256",
        "source_inventory_sha256", "repository_commit_id",
        "pinned_python_identity", "pinned_python_sha256",
        "prior_campaign_payloads_read", "prior_campaign_payloads_reused",
        "manifest_evidence", "output_root_identity",
        "stage_directory_identity", "result_sha256",
    }
    if (
        type(environment) is not dict
        or set(environment) != keys
        or environment.get("schema") != TASK_ENVIRONMENT_SCHEMA
        or environment.get("array_job_id") != job_id
        or environment.get("array_task_id") != shard_index
        or environment.get("slurm_restart_count") != 0
        or environment.get("candidate_indices") != candidate_indices
        or environment.get("code_manifest_sha256") != code_manifest_sha256
        or environment.get("source_inventory_sha256") != inventory_sha256
        or environment.get("repository_commit_id") != repository_commit_id
        or environment.get("pinned_python_sha256") != PYTHON_EXECUTABLE_SHA256
        or environment.get("prior_campaign_payloads_read") != []
        or environment.get("prior_campaign_payloads_reused") != []
        or environment.get("result_sha256")
        != hashlib.sha256(result_raw).hexdigest()
        or not _valid_recorded_identity(
            environment.get("task_tmp_identity"), expected_mode=0o700,
        )
        or not _valid_recorded_identity(
            environment.get("pinned_python_identity"), expected_mode=None,
        )
        or not _valid_recorded_identity(
            environment.get("output_root_identity"), expected_mode=0o700,
        )
        or not _valid_recorded_identity(
            environment.get("stage_directory_identity"), expected_mode=0o700,
        )
    ):
        raise SourceConsumerError("V10 task environment changed")
    output_identity = environment["output_root_identity"]
    stage_identity = environment["stage_directory_identity"]
    if (
        output_identity["device"] != output_root_identity.get("device")
        or output_identity["inode"] != output_root_identity.get("inode")
        or output_identity["uid"] != output_root_identity.get("uid")
        or stage_identity["device"] != shard_info.st_dev
        or stage_identity["inode"] == shard_info.st_ino
        or stage_identity["uid"] != shard_info.st_uid
    ):
        raise SourceConsumerError("V10 task directory identity changed")
    translator_records = [
        {"path": name, "sha256": tracked[name]}
        for name in sorted(tracked)
        if name.startswith("src/translate/") and name.endswith(".py")
    ]
    expected_manifest = {
        "code_manifest_sha256": code_manifest_sha256,
        "code_manifest_records": 62,
        "pinned_python_sha256": PYTHON_EXECUTABLE_SHA256,
        "prlimit_sha256": PRLIMIT_SHA256,
        "libseccomp_sha256": LIBSECCOMP_SHA256,
        "translator_file_count": 38,
        "translator_files_sha256": _digest(translator_records),
    }
    if (
        len(tracked) != 63
        or len(translator_records) != 38
        or environment.get("manifest_evidence") != expected_manifest
    ):
        raise SourceConsumerError("V10 task manifest evidence changed")


def _validate_controller_canary(paths: V10PreflightPaths, receipt: dict) -> None:
    root = paths.controller_output_root
    stage = root / "stage"
    final = root / "published"
    try:
        root_info = root.lstat()
        entries = list(os.scandir(root))
        final_info = final.lstat()
        children = list(os.scandir(final))
    except OSError as err:
        raise SourceConsumerError("cannot inspect controller publication canary") from err
    if (
        root.is_symlink() or not stat.S_ISDIR(root_info.st_mode)
        or stat.S_IMODE(root_info.st_mode) != 0o700 or root_info.st_uid != os.getuid()
        or sorted(entry.name for entry in entries) != ["published"]
        or os.path.lexists(stage)
        or final.is_symlink() or not stat.S_ISDIR(final_info.st_mode)
        or stat.S_IMODE(final_info.st_mode) != 0o500 or final_info.st_uid != os.getuid()
        or sorted(entry.name for entry in children)
        != ["claim.json", "complete.json", "payload.bin"]
        or receipt.get("stage_path") != str(stage)
        or receipt.get("final_path") != str(final)
        or root_info.st_dev != REPO.stat().st_dev
        or final_info.st_dev != root_info.st_dev
        or type(receipt.get("stage_identity")) is not dict
        or set(receipt["stage_identity"]) != {
            "path", "canonical_path", "device", "inode", "mode", "uid",
            "gid",
        }
        or receipt["stage_identity"].get("path") != str(stage)
        or receipt["stage_identity"].get("canonical_path") != str(stage)
        or receipt["stage_identity"].get("device") != root_info.st_dev
        or type(receipt["stage_identity"].get("inode")) is not int
        or receipt["stage_identity"]["inode"] <= 0
        or receipt["stage_identity"].get("mode") != "0700"
        or receipt["stage_identity"].get("uid") != os.getuid()
        or type(receipt["stage_identity"].get("gid")) is not int
        or receipt["stage_identity"]["gid"] < 0
        or receipt.get("final_identity") != {
            "device": final_info.st_dev, "gid": final_info.st_gid,
            "inode": final_info.st_ino, "mode": "0500", "uid": final_info.st_uid,
        }
    ):
        raise SourceConsumerError("controller publication canary tree changed")
    claim_raw, claim = _read_json(final / "claim.json", "controller canary claim")
    payload_raw = _read_regular(final / "payload.bin", "controller canary payload")
    complete_raw, complete = _read_json(
        final / "complete.json", "controller canary completion", newline=True
    )
    expected_payload_sha = {
        "claim.json": hashlib.sha256(claim_raw).hexdigest(),
        "payload.bin": hashlib.sha256(payload_raw).hexdigest(),
    }
    payload_records = []
    for name, raw in (("claim.json", claim_raw), ("payload.bin", payload_raw)):
        info = (final / name).lstat()
        payload_records.append({
            "device": info.st_dev, "gid": info.st_gid, "inode": info.st_ino,
            "mode": "0400", "name": name,
            "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw),
            "uid": info.st_uid,
        })
    if (
        claim != {
            "schema": SCHEMA + "/preflight/v1/publisher-canary-claim/v1",
            "final_path": str(final),
        }
        or payload_raw != b"terminal-incidence-v10-publisher-canary\n"
        or receipt.get("payload_sha256") != expected_payload_sha
        or receipt.get("completion_sha256")
        != hashlib.sha256(complete_raw).hexdigest()
        or complete != {
            "schema": COMPLETION_SCHEMA,
            "metadata": {
                "schema": SCHEMA + "/preflight/v1/publisher-canary-metadata/v1",
                "actual_workspace_filesystem": True,
            },
            "files": payload_records,
            "final_directory": receipt["final_identity"],
        }
    ):
        raise SourceConsumerError("controller publication canary evidence changed")


def _validate_compute_canary(
    paths: V10PreflightPaths, launch: dict, seal: dict, attestation: dict,
    *, launch_sha: str, terminal_sha: str, poll_sha: str,
    controller_sha: str, tracked: Mapping[str, str],
) -> None:
    root = paths.compute_output_root
    shard = root / "shard-0000-of-0001"
    names = sorted([
        "claim.json", "result.json", "environment.json", "complete.json",
        "candidate-0000.stdout.prefix", "candidate-0000.stderr.prefix",
        "candidate-0001.stdout.prefix", "candidate-0001.stderr.prefix",
    ])
    try:
        root_info = root.lstat()
        root_entries = list(os.scandir(root))
        shard_info = shard.lstat()
        entries = list(os.scandir(shard))
    except OSError as err:
        raise SourceConsumerError("cannot inspect compute-canary output") from err
    if (
        root.is_symlink() or not stat.S_ISDIR(root_info.st_mode)
        or stat.S_IMODE(root_info.st_mode) != 0o700 or root_info.st_uid != os.getuid()
        or sorted(entry.name for entry in root_entries) != [shard.name]
        or shard.is_symlink() or not stat.S_ISDIR(shard_info.st_mode)
        or stat.S_IMODE(shard_info.st_mode) != 0o500 or shard_info.st_uid != os.getuid()
        or sorted(entry.name for entry in entries) != names
        or any(entry.is_symlink() or not entry.is_file(follow_symlinks=False) for entry in entries)
        or launch.get("root_identities", {}).get("output_dir", {}).get("path")
        != str(root)
        or launch.get("root_identities", {}).get("output_dir", {}).get("device")
        != root_info.st_dev
        or launch.get("root_identities", {}).get("output_dir", {}).get("inode")
        != root_info.st_ino
    ):
        raise SourceConsumerError("compute-canary exact eight-file tree changed")
    raws = {entry.name: _read_regular(Path(entry.path), "compute-canary " + entry.name) for entry in entries}
    payload_hashes = {name: hashlib.sha256(raws[name]).hexdigest() for name in names}
    if (
        seal != {
            "schema": SCHEMA + "/preflight/v1/compute-canary-seal-plan/v1",
            "campaign": "v10-compute-canary",
            "launch_receipt_sha256": launch_sha,
            "scheduler_terminal_receipt_sha256": terminal_sha,
            "terminal_poll_receipt_sha256": poll_sha,
            "scheduler_rows_sha256": seal.get("scheduler_rows_sha256"),
            "scheduler_contract_rows_sha256": seal.get("scheduler_contract_rows_sha256"),
            "scheduler_gate_passed_before_payload_read": True,
            "payload_hashes": payload_hashes,
            "payload_hashes_sha256": _digest(payload_hashes),
        }
        or not _is_sha(seal.get("scheduler_rows_sha256"))
        or not _is_sha(seal.get("scheduler_contract_rows_sha256"))
    ):
        raise SourceConsumerError("compute-canary seal plan changed")
    def decode(name: str, newline: bool = False) -> dict:
        try:
            value = json.loads(raws[name].decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise SourceConsumerError("compute-canary JSON changed") from err
        if type(value) is not dict or raws[name] != _canonical(value) + (b"\n" if newline else b""):
            raise SourceConsumerError("compute-canary JSON is not canonical")
        return value
    claim = decode("claim.json")
    result = decode("result.json")
    environment = decode("environment.json")
    completion = decode("complete.json", newline=True)
    fixture_prefix = "experiments/fixtures/pdb-terminal-incidence-v10-canary/"
    fixture_records = []
    for index in range(2):
        problem = "problem-{}.pddl".format(index)
        fixture_records.append({
            "candidate_index": index,
            "directory": "v10-synthetic-canary",
            "family": "v10-synthetic-canary",
            "problem": problem,
            "domain_file": "domain.pddl",
            "problem_file": problem,
            "domain_sha256": tracked.get(fixture_prefix + "domain.pddl"),
            "problem_sha256": tracked.get(fixture_prefix + problem),
            "canonical_path": problem,
            "is_shadow_family": False,
            "is_shadow_unrepresented": False,
            "is_all_prior_represented": False,
            "is_all_prior_unrepresented": False,
            "aliases": [],
        })
    if any(
        not _is_sha(record[hash_key])
        for record in fixture_records
        for hash_key in ("domain_sha256", "problem_sha256")
    ):
        raise SourceConsumerError("compute-canary fixture closure changed")
    fixture_sha = _digest(fixture_records)
    expected_claim = {
        "schema": SHARD_CLAIM_SCHEMA, "campaign": "v10-compute-canary",
        "final_path": str(shard), "logical_shard_index": 0,
        "array_task_count": 1, "candidate_indices": [0, 1],
        "array_job_id": launch.get("job_id"), "array_task_id": 0,
        "slurm_restart_count": 0, "source_inventory_sha256": fixture_sha,
        "code_manifest_sha256": launch.get("code_manifest_sha256"),
        "repository_commit_id": launch.get("repository_commit_id"),
    }
    result_keys = {
        "schema", "campaign", "whole_campaign_rerun",
        "logical_shard_index", "array_task_count", "candidate_indices",
        "candidate_count", "candidates", "candidate_origin_counts",
        "prior_campaign_payloads_read", "prior_campaign_shards_used",
        "source_inventory_sha256", "code_manifest_sha256",
        "repository_commit_id", "resource_contract_sha256",
    }
    candidates = result.get("candidates") if type(result) is dict else None
    if (
        claim != expected_claim or set(result) != result_keys
        or result.get("schema") != SHARD_SCHEMA
        or result.get("campaign") != "v10-compute-canary"
        or result.get("whole_campaign_rerun") is not False
        or result.get("logical_shard_index") != 0
        or result.get("array_task_count") != 1
        or result.get("candidate_indices") != [0, 1]
        or result.get("candidate_count") != 2
        or result.get("candidate_origin_counts") != {"v10-synthetic-canary": 2}
        or result.get("prior_campaign_payloads_read") != []
        or result.get("prior_campaign_shards_used") != 0
        or result.get("source_inventory_sha256") != fixture_sha
        or result.get("code_manifest_sha256") != launch.get("code_manifest_sha256")
        or result.get("repository_commit_id") != launch.get("repository_commit_id")
        or result.get("resource_contract_sha256")
        != _digest(_candidate_resource_contract())
        or type(candidates) is not list or len(candidates) != 2
        or [candidate.get("candidate_index") for candidate in candidates] != [0, 1]
        or any(candidate.get("candidate_origin") != "v10-synthetic-canary" or candidate.get("status") != "success" or candidate.get("translation_attempted") is not True for candidate in candidates)
        or environment.get("array_job_id") != launch.get("job_id")
        or environment.get("array_task_id") != 0
        or environment.get("candidate_indices") != [0, 1]
        or environment.get("prior_campaign_payloads_read") != []
        or environment.get("prior_campaign_payloads_reused") != []
        or environment.get("result_sha256") != hashlib.sha256(raws["result.json"]).hexdigest()
        or environment.get("source_inventory_sha256") != fixture_sha
        or environment.get("code_manifest_sha256") != launch.get("code_manifest_sha256")
        or environment.get("repository_commit_id") != launch.get("repository_commit_id")
    ):
        raise SourceConsumerError("compute-canary claim/result/environment changed")
    for position, candidate in enumerate(candidates):
        _validate_candidate_record(
            candidate, fixture_records[position], shard_index=0,
            position=position, candidate_origin="v10-synthetic-canary",
            stream_raws={
                stream: raws[
                    "candidate-{:04d}.{}.prefix".format(position, stream)
                ]
                for stream in ("stdout", "stderr")
            },
            code_manifest_sha256=launch["code_manifest_sha256"],
            repository_commit_id=launch["repository_commit_id"],
        )
    _validate_task_environment(
        environment, shard_index=0, candidate_indices=[0, 1],
        job_id=launch["job_id"], inventory_sha256=fixture_sha,
        code_manifest_sha256=launch["code_manifest_sha256"],
        repository_commit_id=launch["repository_commit_id"], tracked=tracked,
        output_root_identity=launch["root_identities"]["output_dir"],
        shard_info=shard_info, result_raw=raws["result.json"],
    )
    payload_records = []
    for name in sorted(set(names) - {"complete.json"}):
        info = (shard / name).lstat()
        payload_records.append({"device": info.st_dev, "gid": info.st_gid, "inode": info.st_ino, "mode": "0400", "name": name, "sha256": hashlib.sha256(raws[name]).hexdigest(), "size": len(raws[name]), "uid": info.st_uid})
    metadata = {"schema": SHARD_COMPLETION_METADATA_SCHEMA, "campaign": "v10-compute-canary", "logical_shard_index": 0, "candidate_indices": [0, 1], "claim_sha256": hashlib.sha256(raws["claim.json"]).hexdigest(), "result_sha256": hashlib.sha256(raws["result.json"]).hexdigest(), "environment_sha256": hashlib.sha256(raws["environment.json"]).hexdigest()}
    if completion != {"schema": COMPLETION_SCHEMA, "metadata": metadata, "files": payload_records, "final_directory": {"device": shard_info.st_dev, "gid": shard_info.st_gid, "inode": shard_info.st_ino, "mode": "0500", "uid": shard_info.st_uid}}:
        raise SourceConsumerError("compute-canary newline completion changed")
    expected_attestation = {
        "schema": SCHEMA + "/preflight/v1/compute-canary-attestation/v1",
        "campaign": "v10-compute-canary",
        "source_repository_commit_id": launch.get("repository_commit_id"),
        "code_manifest_sha256": launch.get("code_manifest_sha256"),
        "controller_publisher_canary_receipt_sha256": controller_sha,
        "compute_canary_launch_receipt_sha256": launch_sha,
        "compute_canary_terminal_poll_receipt_sha256": poll_sha,
        "compute_canary_seal_plan_sha256": hashlib.sha256(_canonical(seal)).hexdigest(),
        "candidate_indices": [0, 1],
        "candidate_origins": ["v10-synthetic-canary", "v10-synthetic-canary"],
        "candidate_statuses": ["success", "success"],
        "exact_child_and_publication_path_passed": True,
        "compute_canary_passed": True,
    }
    if attestation != expected_attestation:
        raise SourceConsumerError("compute-canary attestation changed")


def load_authorized_preflight(
    paths: V10PreflightPaths | None = None, *, snapshot_reader: SnapshotReader,
    seal_revision: str,
) -> AuthorizedPreflight:
    """Authenticate the infrastructure-only preflight and committed closure."""
    paths = paths or preflight_paths_for()
    if type(seal_revision) is not str or COMMIT_RE.fullmatch(seal_revision) is None:
        raise SourceConsumerError("preflight seal revision must be exact 40-hex")
    _artifact_namespace(paths.artifact_dir, PREFLIGHT_ARTIFACT_FILENAMES, paths.poll_dir.name)
    fixed_paths = {path.name: path for path in (
        paths.controller_receipt, paths.compute_launch_intent,
        paths.compute_launch_receipt, paths.compute_sbatch_stdout,
        paths.compute_sbatch_stderr, paths.compute_sbatch_result,
        paths.compute_terminal_receipt, paths.compute_seal_plan,
        paths.compute_attestation, paths.authorization,
    )}
    # The compute attestation is worker-derived payload.  Keep it unopened
    # until the independently captured terminal scheduler chain has passed.
    deferred_preflight = {
        "compute-canary-seal-plan-v10.json",
        "compute-canary-attestation-v10.json",
    }
    control_names = set(fixed_paths) - deferred_preflight
    fixed_raws = {
        name: _read_regular(fixed_paths[name], "V10 preflight " + name)
        for name in control_names
    }
    def decoded(name: str) -> dict:
        try:
            value = json.loads(fixed_raws[name].decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise SourceConsumerError("V10 preflight JSON changed") from err
        if type(value) is not dict or fixed_raws[name] != _canonical(value):
            raise SourceConsumerError("V10 preflight JSON is not canonical")
        return value
    authorization = decoded("preflight-authorization-v10.json")
    auth_keys = {
        "schema", "campaign", "controller_publisher_canary_receipt_sha256",
        "compute_canary_launch_receipt_sha256",
        "compute_canary_terminal_poll_receipt_sha256",
        "compute_canary_seal_plan_sha256", "compute_canary_attestation_sha256",
        "code_manifest_sha256", "source_repository_commit_id",
        "scheduler_gate_passed_before_payload_read",
        "controller_lustre_publication_passed", "compute_canary_passed",
        "full_launch_authorized",
    }
    if (
        set(authorization) != auth_keys
        or authorization.get("schema") != PREFLIGHT_AUTHORIZATION_SCHEMA
        or authorization.get("campaign") != PREFLIGHT_CAMPAIGN
        or COMMIT_RE.fullmatch(authorization.get("source_repository_commit_id", "")) is None
        or authorization["source_repository_commit_id"] == seal_revision
        or any(authorization.get(key) is not True for key in (
            "scheduler_gate_passed_before_payload_read",
            "controller_lustre_publication_passed", "compute_canary_passed",
            "full_launch_authorized",
        ))
        or any(not _is_sha(authorization.get(key)) for key in (
            "controller_publisher_canary_receipt_sha256",
            "compute_canary_launch_receipt_sha256",
            "compute_canary_terminal_poll_receipt_sha256",
            "compute_canary_seal_plan_sha256", "compute_canary_attestation_sha256",
            "code_manifest_sha256",
        ))
    ):
        raise SourceConsumerError("V10 preflight authorization changed")
    bindings = {
        "controller_publisher_canary_receipt_sha256": "controller-publisher-canary-receipt-v10.json",
        "compute_canary_launch_receipt_sha256": "compute-canary-launch-receipt-v10.json",
    }
    if any(hashlib.sha256(fixed_raws[name]).hexdigest() != authorization[key] for key, name in bindings.items()):
        raise SourceConsumerError("V10 preflight authorization hash binding changed")
    compute_intent, _compute_result, compute_launch = (
        _validate_compute_launch_evidence(paths, fixed_raws)
    )
    compute_launch_sha = hashlib.sha256(
        fixed_raws["compute-canary-launch-receipt-v10.json"]
    ).hexdigest()
    if (
        compute_launch_sha != authorization["compute_canary_launch_receipt_sha256"]
        or compute_launch.get("controller_publisher_canary_receipt_sha256")
        != authorization["controller_publisher_canary_receipt_sha256"]
    ):
        raise SourceConsumerError("V10 compute-canary launch chain changed")
    poll_raws, last_poll_sha, final_poll = _poll_bundle(
        paths.poll_dir, campaign="v10-compute-canary",
        poll_schema=COMPUTE_POLL_SCHEMA, expected_tasks=1,
        launch_receipt_sha256=compute_launch_sha,
        launch_recorded_utc=compute_launch["accepted_utc"],
        expected_job_id=compute_launch.get("job_id"),
        expected_job_name="pdb-source-v10-canary-{}".format(
            compute_launch.get("submission_token")
        ),
    )
    terminal = decoded("compute-canary-scheduler-terminal-receipt-v10.json")
    _terminal_gate(
        terminal, schema=COMPUTE_TERMINAL_RECEIPT_SCHEMA,
        campaign="v10-compute-canary", completed=1,
        last_poll_sha=last_poll_sha,
        expected_job_id=compute_launch["job_id"],
    )
    if authorization["compute_canary_terminal_poll_receipt_sha256"] != last_poll_sha:
        raise SourceConsumerError("V10 preflight terminal poll binding changed")
    for name in deferred_preflight:
        fixed_raws[name] = _read_regular(
            fixed_paths[name], "V10 preflight " + name
        )
    if (
        hashlib.sha256(fixed_raws["compute-canary-attestation-v10.json"]).hexdigest()
        != authorization["compute_canary_attestation_sha256"]
        or hashlib.sha256(fixed_raws["compute-canary-seal-plan-v10.json"]).hexdigest()
        != authorization["compute_canary_seal_plan_sha256"]
    ):
        raise SourceConsumerError("V10 compute-canary attestation binding changed")
    controller = decoded("controller-publisher-canary-receipt-v10.json")
    compute = decoded("compute-canary-attestation-v10.json")
    compute_seal = decoded("compute-canary-seal-plan-v10.json")
    terminal_sha = hashlib.sha256(
        fixed_raws["compute-canary-scheduler-terminal-receipt-v10.json"]
    ).hexdigest()
    controller_keys = {
        "schema", "campaign", "controller_source_sha256",
        "publisher_source_sha256", "stage_path", "stage_identity",
        "final_path", "final_identity", "payload_sha256",
        "completion_sha256", "filesystem_probe", "actual_lustre",
        "publisher_canary_passed", "renameat2_used",
    }
    filesystem_probe = controller.get("filesystem_probe")
    expected_stat_sha = (
        "f7ef3b1376596ce952779ea53a91ec97ce8b57389a3ffde75a499564b1c8f25f"
    )
    if (
        set(controller) != controller_keys
        or controller.get("schema")
        != SCHEMA + "/preflight/v1/publisher-canary-receipt/v1"
        or controller.get("campaign") != PREFLIGHT_CAMPAIGN
        or controller.get("actual_lustre") is not True
        or type(filesystem_probe) is not dict
        or set(filesystem_probe) != {
            "program", "command", "target", "target_device",
            "filesystem_type", "filesystem_magic", "stdout",
            "stdout_sha256", "stderr_sha256", "returncode",
        }
        or filesystem_probe.get("program") != {
            "path": "/usr/bin/stat", "resolved_path": "/usr/bin/stat",
            "sha256": expected_stat_sha,
        }
        or filesystem_probe.get("command") != [
            "/usr/bin/stat", "--file-system", "--format=%T|%t",
            filesystem_probe.get("target"),
        ]
        or filesystem_probe.get("target") != str(REPO.resolve())
        or filesystem_probe.get("filesystem_type") != "lustre"
        or filesystem_probe.get("filesystem_magic") != "bd00bd0"
        or filesystem_probe.get("stdout") != "lustre|bd00bd0\n"
        or filesystem_probe.get("stdout_sha256")
        != hashlib.sha256(b"lustre|bd00bd0\n").hexdigest()
        or filesystem_probe.get("stderr_sha256")
        != hashlib.sha256(b"").hexdigest()
        or filesystem_probe.get("returncode") != 0
        or type(filesystem_probe.get("target_device")) is not int
        or filesystem_probe.get("target_device") != REPO.stat().st_dev
        or controller.get("final_identity", {}).get("device")
        != filesystem_probe.get("target_device")
        or controller.get("publisher_canary_passed") is not True
        or controller.get("renameat2_used") is not False
        or any(not _is_sha(controller.get(key)) for key in (
            "controller_source_sha256", "publisher_source_sha256",
            "completion_sha256",
        ))
        or type(controller.get("payload_sha256")) is not dict
        or compute.get("compute_canary_passed") is not True
        or compute_seal.get("scheduler_gate_passed_before_payload_read") is not True
        or compute_seal.get("scheduler_terminal_receipt_sha256") != terminal_sha
        or compute_seal.get("terminal_poll_receipt_sha256") != last_poll_sha
        or compute_seal.get("launch_receipt_sha256") != compute_launch_sha
        or compute_seal.get("scheduler_rows_sha256")
        != _digest(final_poll["scheduler_rows"])
        or compute_seal.get("scheduler_contract_rows_sha256")
        != _digest(final_poll["scheduler_contract_rows"])
    ):
        raise SourceConsumerError("V10 infrastructure canary did not pass")
    tracked, sealed_source = _manifest_closure(
        paths.code_manifest, authorization["code_manifest_sha256"],
        authorization["source_repository_commit_id"], seal_revision,
        snapshot_reader,
    )
    _validate_rendered_slurm(
        compute_intent, sealed_source, template=COMPUTE_CANARY_SLURM_PROGRAM,
        inventory_sha256=None,
    )
    if (
        tracked.get("experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v10.py")
        != controller["controller_source_sha256"]
        or tracked.get("experiments/pdb_terminal_incidence_confirmation_publication_v10.py")
        != controller["publisher_source_sha256"]
    ):
        raise SourceConsumerError("controller canary source binding changed")
    _validate_controller_canary(paths, controller)
    _validate_compute_canary(
        paths, compute_launch, compute_seal, compute,
        launch_sha=compute_launch_sha, terminal_sha=terminal_sha,
        poll_sha=last_poll_sha,
        controller_sha=authorization[
            "controller_publisher_canary_receipt_sha256"
        ], tracked=tracked,
    )
    artifact_hashes = _artifact_snapshot(
        paths.artifact_dir, PREFLIGHT_ARTIFACT_FILENAMES, paths.poll_dir.name,
        fixed_raws, poll_raws, seal_revision, snapshot_reader,
    )
    # Close the live-tree TOCTOU window after consuming the committed control
    # snapshot.  Both validators re-open every canary payload and directory.
    _validate_controller_canary(paths, controller)
    _validate_compute_canary(
        paths, compute_launch, compute_seal, compute,
        launch_sha=compute_launch_sha, terminal_sha=terminal_sha,
        poll_sha=last_poll_sha,
        controller_sha=authorization[
            "controller_publisher_canary_receipt_sha256"
        ], tracked=tracked,
    )
    return AuthorizedPreflight(
        campaign=PREFLIGHT_CAMPAIGN,
        seal_repository_commit_id=seal_revision,
        source_repository_commit_id=authorization["source_repository_commit_id"],
        authorization_sha256=hashlib.sha256(fixed_raws["preflight-authorization-v10.json"]).hexdigest(),
        controller_publisher_canary_receipt_sha256=authorization["controller_publisher_canary_receipt_sha256"],
        compute_canary_launch_receipt_sha256=authorization["compute_canary_launch_receipt_sha256"],
        compute_canary_terminal_poll_receipt_sha256=last_poll_sha,
        compute_canary_seal_plan_sha256=authorization["compute_canary_seal_plan_sha256"],
        compute_canary_attestation_sha256=authorization["compute_canary_attestation_sha256"],
        code_manifest_sha256=authorization["code_manifest_sha256"],
        full_launch_authorized=True,
        tracked_file_sha256=_freeze({**tracked, **artifact_hashes}),
    )


def shard_name(index: int) -> str:
    return "shard-{:04d}-of-{:04d}".format(index, SHARD_COUNT)


def _expected_shard_names(index: int) -> list[str]:
    candidates = (2 * index, 2 * index + 1)
    return sorted([
        "claim.json", "result.json", "environment.json", "complete.json",
        *("candidate-{:04d}.{}.prefix".format(candidate, stream)
          for candidate in candidates for stream in ("stdout", "stderr")),
    ])


def _file_record(relative: str, raw: bytes, path: Path | None = None) -> dict:
    record = {"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    if path is not None:
        info = Path(path).lstat()
        record.update({
            "device": info.st_dev, "inode": info.st_ino, "uid": info.st_uid,
            "gid": info.st_gid, "mode": "{:04o}".format(stat.S_IMODE(info.st_mode)),
            "nlink": info.st_nlink,
        })
    return record


def _validate_output_tree(paths: V10Paths, execution: dict, launch: dict) -> tuple[dict[str, dict], list[dict]]:
    tree = execution.get("output_tree")
    files = tree.get("files") if type(tree) is dict else None
    directories = tree.get("directories") if type(tree) is dict else None
    expected_directories = []
    for index in range(SHARD_COUNT):
        name = shard_name(index)
        try:
            info = (paths.data_root / name).lstat()
        except OSError as err:
            raise SourceConsumerError("cannot inspect V10 shard identity") from err
        expected_directories.append({
            "path": name, "device": info.st_dev, "inode": info.st_ino,
            "uid": info.st_uid, "gid": info.st_gid, "mode": "0500",
        })
    expected_names = ["source-inventory-v10.json"]
    for index in range(SHARD_COUNT):
        expected_names.extend(shard_name(index) + "/" + name for name in _expected_shard_names(index))
    expected_names.sort()
    if (
        type(tree) is not dict
        or set(tree) != {"schema", "root", "root_identity", "directories_count", "directories", "files_count", "files", "sha256"}
        or tree.get("schema") != SCHEMA + "/output-tree/v1"
        or tree.get("root") != str(paths.data_root)
        or tree.get("root_identity") != launch.get("root_identities", {}).get("output_dir")
        or tree.get("directories_count") != SHARD_COUNT
        or directories != expected_directories
        or tree.get("files_count") != FULL_TREE_FILE_COUNT
        or type(files) is not list or len(files) != FULL_TREE_FILE_COUNT
        or execution.get("output_tree_sha256") != _digest(tree)
        or tree.get("sha256") != _digest({"root_identity": tree.get("root_identity"), "directories": directories, "files": files})
    ):
        raise SourceConsumerError("V10 exact 6,561-file output-tree commitment changed")
    file_map: dict[str, dict] = {}
    for item in files:
        if type(item) is not dict or set(item) != {"path", "bytes", "sha256", "device", "inode", "uid", "gid", "mode", "nlink"} or type(item.get("bytes")) is not int or item["bytes"] < 0 or not _is_sha(item.get("sha256")) or item.get("path") in file_map or item.get("mode") != "0400" or item.get("nlink") != 1:
            raise SourceConsumerError("V10 output-tree file record changed")
        file_map[item["path"]] = item
    if [item["path"] for item in files] != expected_names:
        raise SourceConsumerError("V10 output-tree paths changed")
    try:
        root = paths.data_root.lstat()
        root_entries = list(os.scandir(paths.data_root))
    except OSError as err:
        raise SourceConsumerError("cannot enumerate V10 output root") from err
    root_identity = tree["root_identity"]
    if (
        paths.data_root.is_symlink() or not stat.S_ISDIR(root.st_mode)
        or stat.S_IMODE(root.st_mode) != 0o700 or root.st_uid != os.getuid()
        or type(root_identity) is not dict
        or root_identity.get("device") != root.st_dev or root_identity.get("inode") != root.st_ino
        or root_identity.get("path") != str(paths.data_root) or root_identity.get("canonical_path") != str(paths.data_root)
        or root_identity.get("mode") != "0700" or root_identity.get("uid") != root.st_uid or root_identity.get("gid") != root.st_gid
        or sorted(entry.name for entry in root_entries) != sorted(["source-inventory-v10.json", *(shard_name(i) for i in range(SHARD_COUNT))])
    ):
        raise SourceConsumerError("V10 output root identity or closure changed")
    return file_map, files


def _validate_output_namespace_stable(paths: V10Paths, execution: dict) -> None:
    tree = execution["output_tree"]
    try:
        root_info = paths.data_root.lstat()
        root_entries = list(os.scandir(paths.data_root))
    except OSError as err:
        raise SourceConsumerError("cannot revalidate V10 output root") from err
    expected_root = {
        "path": str(paths.data_root), "canonical_path": str(paths.data_root),
        "device": root_info.st_dev, "inode": root_info.st_ino,
        "mode": "0700", "uid": root_info.st_uid, "gid": root_info.st_gid,
    }
    expected_root_names = {
        "source-inventory-v10.json": "file",
        **{shard_name(index): "directory" for index in range(SHARD_COUNT)},
    }
    actual_root_names = {}
    for entry in root_entries:
        if entry.is_symlink():
            raise SourceConsumerError("V10 output root gained a symlink")
        if entry.is_file(follow_symlinks=False):
            kind = "file"
        elif entry.is_dir(follow_symlinks=False):
            kind = "directory"
        else:
            raise SourceConsumerError("V10 output root gained a special entry")
        actual_root_names[entry.name] = kind
    if (
        paths.data_root.is_symlink()
        or not stat.S_ISDIR(root_info.st_mode)
        or stat.S_IMODE(root_info.st_mode) != 0o700
        or root_info.st_uid != os.getuid()
        or tree.get("root_identity") != expected_root
        or actual_root_names != expected_root_names
    ):
        raise SourceConsumerError("V10 output root changed after snapshot")
    directory_records = tree.get("directories")
    if type(directory_records) is not list or len(directory_records) != SHARD_COUNT:
        raise SourceConsumerError("V10 shard directory records changed")
    for index, expected in enumerate(directory_records):
        directory = paths.data_root / shard_name(index)
        try:
            info = directory.lstat()
            entries = list(os.scandir(directory))
        except OSError as err:
            raise SourceConsumerError("cannot revalidate V10 shard") from err
        observed = {
            "path": shard_name(index), "device": info.st_dev,
            "inode": info.st_ino, "uid": info.st_uid, "gid": info.st_gid,
            "mode": "0500",
        }
        if (
            directory.is_symlink()
            or not stat.S_ISDIR(info.st_mode)
            or stat.S_IMODE(info.st_mode) != 0o500
            or info.st_uid != os.getuid()
            or expected != observed
            or sorted(entry.name for entry in entries)
            != _expected_shard_names(index)
            or any(
                entry.is_symlink()
                or not entry.is_file(follow_symlinks=False)
                for entry in entries
            )
        ):
            raise SourceConsumerError("V10 shard changed after snapshot")


def _bound(path: Path, relative: str, frozen: Mapping[str, dict], *, newline: bool = False) -> tuple[bytes, dict]:
    raw, value = _read_json(path, "V10 payload " + relative, newline=newline)
    if _file_record(relative, raw, path) != frozen.get(relative):
        raise SourceConsumerError("V10 payload differs from sealed output tree")
    return raw, value


def _source_key(record: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        record["directory"], record["problem"], record["problem_file"],
        record["domain_file"],
    )


def _validate_inventory_manifest(value: Any) -> list[dict]:
    top_keys = {
        "schema", "benchmark_revision", "cost_manifest_sha256",
        "shadow_attestation_sha256", "candidate_records_sha256",
        "alias_groups_sha256", "inventory_digests", "counts",
        "shadow_families", "all_prior_families",
        "all_prior_unrepresented_families", "records_sha256", "records",
    }
    records = value.get("records") if type(value) is dict else None
    if (
        type(value) is not dict
        or set(value) != top_keys
        or value.get("schema") != INVENTORY_SCHEMA
        or value.get("benchmark_revision") != BENCHMARK_REVISION
        or value.get("cost_manifest_sha256") != COST_MANIFEST_SHA256
        or value.get("shadow_attestation_sha256") != SHADOW_ATTESTATION_SHA256
        or value.get("candidate_records_sha256") != CANDIDATE_RECORDS_SHA256
        or value.get("alias_groups_sha256") != ALIAS_GROUPS_SHA256
        or value.get("inventory_digests") != EXPECTED_INVENTORY_DIGESTS
        or value.get("shadow_families") != list(SHADOW_FAMILIES)
        or value.get("all_prior_families") != list(ALL_PRIOR_FAMILIES)
        or value.get("all_prior_unrepresented_families")
        != list(ALL_PRIOR_UNREPRESENTED_FAMILIES)
        or type(records) is not list
        or len(records) != CANDIDATE_COUNT
        or value.get("records_sha256") != _digest(records)
    ):
        raise SourceConsumerError("V10 source inventory identity changed")
    counts = value.get("counts")
    if (
        type(counts) is not dict
        or set(counts) != {
            "candidates", "families", "source_aliases", "discarded_aliases",
            "prior_identity_overlap", "prior_problem_hash_overlap",
        }
        or counts.get("candidates") != CANDIDATE_COUNT
        or counts.get("families") != 43
        or counts.get("discarded_aliases") != 93
        or counts.get("prior_identity_overlap") != 0
        or counts.get("prior_problem_hash_overlap") != 0
    ):
        raise SourceConsumerError("V10 source inventory counts changed")
    candidate_records = []
    alias_groups = []
    seen_hashes = set()
    shadow = set(SHADOW_FAMILIES)
    prior = set(ALL_PRIOR_FAMILIES)
    candidate_keys = {
        "directory", "family", "problem", "domain_file", "problem_file",
        "domain_sha256", "problem_sha256",
    }
    for index, record in enumerate(records):
        if type(record) is not dict or set(record) != INVENTORY_RECORD_KEYS:
            raise SourceConsumerError("V10 source inventory record shape changed")
        candidate = {key: record[key] for key in candidate_keys}
        aliases = record["aliases"]
        if (
            record["candidate_index"] != index
            or any(type(record[key]) is not str or not record[key] for key in candidate_keys)
            or record["canonical_path"] != record["problem_file"]
            or type(record["family"]) is not str
            or record["is_shadow_family"] is not (record["family"] in shadow)
            or record["is_shadow_unrepresented"]
            is not (record["family"] not in shadow)
            or record["is_all_prior_represented"]
            is not (record["family"] in prior)
            or record["is_all_prior_unrepresented"]
            is not (record["family"] not in prior)
            or not _is_sha(record["domain_sha256"])
            or not _is_sha(record["problem_sha256"])
            or record["problem_sha256"] in seen_hashes
            or type(aliases) is not list
            or not aliases
            or any(type(alias) is not dict or set(alias) != candidate_keys for alias in aliases)
            or aliases != sorted(aliases, key=_source_key)
            or aliases[0] != candidate
            or any(
                alias["problem_sha256"] != record["problem_sha256"]
                or alias["family"] != record["family"]
                for alias in aliases
            )
        ):
            raise SourceConsumerError("V10 source inventory record changed")
        seen_hashes.add(record["problem_sha256"])
        candidate_records.append(candidate)
        alias_groups.append({
            "problem_sha256": record["problem_sha256"],
            "canonical": candidate,
            "aliases": aliases,
        })
    if (
        _digest(candidate_records) != CANDIDATE_RECORDS_SHA256
        or _digest(sorted(alias_groups, key=lambda item: item["problem_sha256"]))
        != ALIAS_GROUPS_SHA256
        or counts.get("source_aliases")
        != sum(len(record["aliases"]) for record in records)
    ):
        raise SourceConsumerError("V10 source inventory content changed")
    return records


def _rank(record: Mapping[str, Any], role: str) -> str:
    fields = (
        SPLIT_SEED, role, record["family"], record["problem_sha256"],
        record["canonical_path"],
    )
    return hashlib.sha256(
        b"\0".join(field.encode("utf-8") for field in fields)
    ).hexdigest()


def _stratum_indices(records: list[dict], families: set[str]) -> dict:
    selected = [
        record["candidate_index"] for record in records
        if record["family"] in families
    ]
    represented = sorted({
        record["family"] for record in records if record["family"] in families
    })
    return {
        "tasks": len(selected),
        "families": len(represented),
        "candidate_indices_sha256": _digest(selected),
        "families_sha256": _digest(represented),
    }


def _recompute_split(records: list[dict]) -> tuple[dict, dict]:
    if (
        len(records) != CANDIDATE_COUNT
        or [record.get("candidate_index") for record in records]
        != list(range(CANDIDATE_COUNT))
    ):
        raise SourceConsumerError("V10 split population changed")
    supported = [record for record in records if record["supported"] is True]
    shadow = set(SHADOW_FAMILIES)
    inventory_families = {record["family"] for record in records}
    shadow_unrepresented = inventory_families - shadow
    all_prior_unrepresented = set(ALL_PRIOR_UNREPRESENTED_FAMILIES)
    by_family: dict[str, list[dict]] = defaultdict(list)
    for record in supported:
        by_family[record["family"]].append(record)
    guided_base = []
    guided_hashes = set()
    for family in sorted(by_family):
        ordered = sorted(
            by_family[family],
            key=lambda record: (
                _rank(record, GUIDED_ROLE), record["canonical_path"],
            ),
        )
        reserve = min(3, len(ordered) // 2)
        for record in ordered[:reserve]:
            guided_base.append(record)
            guided_hashes.add(record["problem_sha256"])
    confirmation_queues = {}
    for family in sorted(by_family):
        remaining = [
            record for record in by_family[family]
            if record["problem_sha256"] not in guided_hashes
        ]
        confirmation_queues[family] = deque(sorted(
            remaining,
            key=lambda record: (
                _rank(record, CONFIRMATION_ROLE), record["canonical_path"],
            ),
        ))
    confirmation = []
    while len(confirmation) < CONFIRMATION_TASKS:
        progress = False
        for family in sorted(confirmation_queues):
            if confirmation_queues[family] and len(confirmation) < CONFIRMATION_TASKS:
                confirmation.append(confirmation_queues[family].popleft())
                progress = True
        if not progress:
            break
    selected_hashes = guided_hashes | {
        record["problem_sha256"] for record in confirmation
    }
    guided_counts = Counter(record["family"] for record in guided_base)
    top_up_queues = {
        family: deque(sorted(
            (
                record for record in by_family[family]
                if record["problem_sha256"] not in selected_hashes
            ),
            key=lambda record: (
                _rank(record, GUIDED_TOP_UP_ROLE), record["canonical_path"],
            ),
        ))
        for family in sorted(by_family)
    }
    post_confirmation_remaining = sum(len(queue) for queue in top_up_queues.values())
    guided_cap_capacity = len(guided_base) + sum(
        min(
            len(top_up_queues[family]),
            MAX_GUIDED_TASKS_PER_FAMILY - guided_counts[family],
        )
        for family in top_up_queues
    )
    guided_top_up = []
    while len(guided_base) + len(guided_top_up) < GUIDED_TARGET_TASKS:
        progress = False
        for family in sorted(top_up_queues):
            if (
                top_up_queues[family]
                and guided_counts[family] < MAX_GUIDED_TASKS_PER_FAMILY
                and len(guided_base) + len(guided_top_up) < GUIDED_TARGET_TASKS
            ):
                record = top_up_queues[family].popleft()
                guided_top_up.append(record)
                guided_counts[family] += 1
                progress = True
        if not progress:
            break
    guided_base.sort(key=lambda record: (
        record["family"], _rank(record, GUIDED_ROLE), record["canonical_path"],
    ))
    guided = guided_base + guided_top_up
    confirmation_families = {record["family"] for record in confirmation}
    guided_families = {record["family"] for record in guided}
    confirmation_all_prior = [
        record for record in confirmation
        if record["family"] in all_prior_unrepresented
    ]
    guided_all_prior = [
        record for record in guided
        if record["family"] in all_prior_unrepresented
    ]
    clauses = {
        "confirmation_tasks": {
            "actual": len(confirmation), "required": CONFIRMATION_TASKS,
            "passed": len(confirmation) == CONFIRMATION_TASKS,
        },
        "confirmation_families": {
            "actual": len(confirmation_families),
            "required_minimum": MIN_CONFIRMATION_FAMILIES,
            "passed": len(confirmation_families) >= MIN_CONFIRMATION_FAMILIES,
        },
        "confirmation_shadow_unrepresented_families": {
            "actual": len(confirmation_families - shadow),
            "required_minimum": MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES,
            "passed": len(confirmation_families - shadow)
            >= MIN_CONFIRMATION_SHADOW_UNREPRESENTED_FAMILIES,
        },
        "confirmation_all_prior_unrepresented_tasks": {
            "actual": len(confirmation_all_prior),
            "required_minimum": MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS,
            "passed": len(confirmation_all_prior)
            >= MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_TASKS,
        },
        "confirmation_all_prior_unrepresented_families": {
            "actual": len({record["family"] for record in confirmation_all_prior}),
            "required_minimum": MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES,
            "passed": len({record["family"] for record in confirmation_all_prior})
            >= MIN_CONFIRMATION_ALL_PRIOR_UNREPRESENTED_FAMILIES,
        },
        "guided_tasks": {
            "actual": len(guided), "required_minimum": MIN_GUIDED_TASKS,
            "passed": len(guided) >= MIN_GUIDED_TASKS,
        },
        "guided_families": {
            "actual": len(guided_families),
            "required_minimum": MIN_GUIDED_FAMILIES,
            "passed": len(guided_families) >= MIN_GUIDED_FAMILIES,
        },
        "guided_shadow_unrepresented_families": {
            "actual": len(guided_families - shadow),
            "required_minimum": MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES,
            "passed": len(guided_families - shadow)
            >= MIN_GUIDED_SHADOW_UNREPRESENTED_FAMILIES,
        },
        "guided_all_prior_unrepresented_tasks": {
            "actual": len(guided_all_prior),
            "required_minimum": MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS,
            "passed": len(guided_all_prior)
            >= MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_TASKS,
        },
        "guided_all_prior_unrepresented_families": {
            "actual": len({record["family"] for record in guided_all_prior}),
            "required_minimum": MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES,
            "passed": len({record["family"] for record in guided_all_prior})
            >= MIN_GUIDED_ALL_PRIOR_UNREPRESENTED_FAMILIES,
        },
    }
    confirmation_indices = [record["candidate_index"] for record in confirmation]
    guided_indices = [record["candidate_index"] for record in guided]
    candidate_overlap = set(confirmation_indices) & set(guided_indices)
    hash_overlap = (
        {record["problem_sha256"] for record in confirmation}
        & {record["problem_sha256"] for record in guided}
    )
    source_overlap = (
        {_source_key(record) for record in confirmation}
        & {_source_key(record) for record in guided}
    )
    if candidate_overlap or hash_overlap or source_overlap:
        raise SourceConsumerError("V10 deterministic cohorts overlap")
    gate = {
        "outcome_blind": True,
        "resource_exclusions_ineligible": True,
        "availability": {
            "supported_tasks": len(supported),
            "supported_families": len(by_family),
            "supported_candidate_indices_sha256": _digest([
                record["candidate_index"] for record in supported
            ]),
            "shadow_unrepresented": _stratum_indices(
                supported, shadow_unrepresented,
            ),
            "all_prior_unrepresented": _stratum_indices(
                supported, all_prior_unrepresented,
            ),
            "post_confirmation_remaining_tasks": post_confirmation_remaining,
            "guided_b_maximum_under_family_cap": guided_cap_capacity,
            "guided_b_target_tasks": GUIDED_TARGET_TASKS,
            "guided_b_max_tasks_per_family": MAX_GUIDED_TASKS_PER_FAMILY,
        },
        "clauses": clauses,
        "cohort_disjointness": {
            "candidate_index_overlap": 0,
            "source_identity_overlap": 0,
            "problem_sha256_overlap": 0,
            "passed": True,
        },
    }
    gate["passed"] = (
        all(clause["passed"] for clause in clauses.values())
        and gate["cohort_disjointness"]["passed"]
    )
    cohorts = {
        "confirmation_a": {
            "role": CONFIRMATION_ROLE,
            "candidate_indices": confirmation_indices,
            "candidate_indices_sha256": _digest(confirmation_indices),
        },
        "guided_b": {
            "role": GUIDED_ROLE,
            "top_up_role": GUIDED_TOP_UP_ROLE,
            "base_candidate_indices": [
                record["candidate_index"] for record in guided_base
            ],
            "top_up_candidate_indices": [
                record["candidate_index"] for record in guided_top_up
            ],
            "candidate_indices": guided_indices,
            "candidate_indices_sha256": _digest(guided_indices),
        },
    }
    return gate, cohorts


def _classification_summaries(records: list[dict]) -> dict:
    outcomes = Counter(record["status"] for record in records)
    outcome_counts = {
        key: outcomes[key]
        for key in ("input-rejected", "resource-excluded", "success")
    }
    support_labels = [
        "supported" if record["supported"] is True else (
            "unsupported" if record["supported"] is False else "indeterminate"
        )
        for record in records
    ]
    statuses = Counter(support_labels)
    support_status_counts = {
        key: statuses[key]
        for key in ("indeterminate", "supported", "unsupported")
    }
    support_exclusion_counts = dict(sorted(Counter(
        reason for record in records
        for reason in (record["support_exclusion_reasons"] or [])
    ).items()))
    resource_records = [
        record for record in records if record["status"] == "resource-excluded"
    ]
    resource = Counter(
        record["resource_exclusion_kind"] for record in resource_records
    )
    resource_exclusion_counts = {
        key: resource[key] for key in ("memory", "time")
    }
    by_family = {}
    for family in sorted({record["family"] for record in resource_records}):
        selected = [record for record in resource_records if record["family"] == family]
        by_family[family] = {
            "memory": sum(
                record["resource_exclusion_kind"] == "memory" for record in selected
            ),
            "time": sum(
                record["resource_exclusion_kind"] == "time" for record in selected
            ),
            "total": len(selected),
        }
    return {
        "counts": {
            "candidates": len(records),
            "translation_attempts": sum(
                record["translation_attempted"] for record in records
            ),
            "support_determinate": sum(
                record["support_determined"] for record in records
            ),
            "supported": statuses["supported"],
            "unsupported": statuses["unsupported"],
            "indeterminate": statuses["indeterminate"],
            "cohort_eligible": sum(
                record["eligible_for_cohort"] for record in records
            ),
            "families": len({record["family"] for record in records}),
        },
        "outcome_counts": outcome_counts,
        "support_status_counts": support_status_counts,
        "support_exclusion_counts": support_exclusion_counts,
        "resource_exclusion_counts": resource_exclusion_counts,
        "resource_exclusions_by_family": by_family,
    }


def _validate_shards(
    paths: V10Paths, file_map: Mapping[str, dict], launch: dict,
    tracked: Mapping[str, str],
) -> tuple[list[dict], list[dict]]:
    tasks: list[dict] = []
    environments: list[dict] = []
    inventory_raw, inventory = _bound(paths.data_root / "source-inventory-v10.json", "source-inventory-v10.json", file_map)
    records = _validate_inventory_manifest(inventory)
    if hashlib.sha256(inventory_raw).hexdigest() != launch.get("source_inventory_sha256"):
        raise SourceConsumerError("V10 source inventory changed")
    for index in range(SHARD_COUNT):
        directory = paths.data_root / shard_name(index)
        try:
            info = directory.lstat()
            entries = list(os.scandir(directory))
        except OSError as err:
            raise SourceConsumerError("cannot inspect V10 shard") from err
        if directory.is_symlink() or not stat.S_ISDIR(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o500 or info.st_uid != os.getuid() or sorted(entry.name for entry in entries) != _expected_shard_names(index):
            raise SourceConsumerError("V10 eight-file shard closure changed")
        if any(entry.is_symlink() or not entry.is_file(follow_symlinks=False) for entry in entries):
            raise SourceConsumerError("V10 shard contains non-files")
        prefix = shard_name(index) + "/"
        expected_indices = [2 * index, 2 * index + 1]
        claim_raw, claim = _bound(directory / "claim.json", prefix + "claim.json", file_map)
        expected_claim = {
            "schema": SHARD_CLAIM_SCHEMA, "campaign": CAMPAIGN,
            "final_path": str(directory), "logical_shard_index": index,
            "array_task_count": SHARD_COUNT, "candidate_indices": expected_indices,
            "array_job_id": launch["job_id"], "array_task_id": index,
            "slurm_restart_count": 0,
            "source_inventory_sha256": launch["source_inventory_sha256"],
            "code_manifest_sha256": launch["code_manifest_sha256"],
            "repository_commit_id": launch["repository_commit_id"],
        }
        if claim != expected_claim:
            raise SourceConsumerError("V10 shard claim changed")
        result_raw, result = _bound(directory / "result.json", prefix + "result.json", file_map)
        result_keys = {"schema", "campaign", "whole_campaign_rerun", "logical_shard_index", "array_task_count", "candidate_indices", "candidate_count", "candidates", "candidate_origin_counts", "prior_campaign_payloads_read", "prior_campaign_shards_used", "source_inventory_sha256", "code_manifest_sha256", "repository_commit_id", "resource_contract_sha256"}
        shard_tasks = result.get("candidates") if type(result) is dict else None
        if type(result) is not dict or set(result) != result_keys or result.get("schema") != SHARD_SCHEMA or result.get("campaign") != CAMPAIGN or result.get("whole_campaign_rerun") is not True or result.get("logical_shard_index") != index or result.get("array_task_count") != SHARD_COUNT or result.get("candidate_indices") != expected_indices or result.get("candidate_count") != 2 or result.get("candidate_origin_counts") != {"v10-fresh": 2} or result.get("prior_campaign_payloads_read") != [] or result.get("prior_campaign_shards_used") != 0 or result.get("source_inventory_sha256") != launch["source_inventory_sha256"] or result.get("code_manifest_sha256") != launch["code_manifest_sha256"] or result.get("repository_commit_id") != launch["repository_commit_id"] or result.get("resource_contract_sha256") != _digest(_candidate_resource_contract()) or type(shard_tasks) is not list or len(shard_tasks) != 2:
            raise SourceConsumerError("V10 shard result changed")
        environment_raw, environment = _bound(directory / "environment.json", prefix + "environment.json", file_map)
        payload_records = []
        payload_raws = {}
        for entry in sorted((entry for entry in entries if entry.name != "complete.json"), key=lambda entry: entry.name):
            raw = _read_regular(Path(entry.path), "V10 shard payload")
            payload_raws[entry.name] = raw
            relative = prefix + entry.name
            if _file_record(relative, raw, Path(entry.path)) != file_map[relative]:
                raise SourceConsumerError("V10 shard payload tree binding changed")
            observed = entry.stat(follow_symlinks=False)
            payload_records.append({"device": observed.st_dev, "gid": observed.st_gid, "inode": observed.st_ino, "mode": "0400", "name": entry.name, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw), "uid": observed.st_uid})
        _completion_raw, completion = _bound(directory / "complete.json", prefix + "complete.json", file_map, newline=True)
        expected_metadata = {"schema": SHARD_COMPLETION_METADATA_SCHEMA, "campaign": CAMPAIGN, "logical_shard_index": index, "candidate_indices": expected_indices, "claim_sha256": hashlib.sha256(claim_raw).hexdigest(), "result_sha256": hashlib.sha256(result_raw).hexdigest(), "environment_sha256": hashlib.sha256(environment_raw).hexdigest()}
        expected_identity = {"device": info.st_dev, "gid": info.st_gid, "inode": info.st_ino, "mode": "0500", "uid": info.st_uid}
        if completion != {"schema": COMPLETION_SCHEMA, "metadata": expected_metadata, "files": payload_records, "final_directory": expected_identity}:
            raise SourceConsumerError("V10 newline completion manifest changed")
        _validate_task_environment(
            environment, shard_index=index, candidate_indices=expected_indices,
            job_id=launch["job_id"],
            inventory_sha256=launch["source_inventory_sha256"],
            code_manifest_sha256=launch["code_manifest_sha256"],
            repository_commit_id=launch["repository_commit_id"],
            tracked=tracked,
            output_root_identity=launch["root_identities"]["output_dir"],
            shard_info=info, result_raw=result_raw,
        )
        for position, (candidate_index, task) in enumerate(zip(expected_indices, shard_tasks)):
            inventory_record = records[candidate_index]
            _validate_candidate_record(
                task, inventory_record, shard_index=index, position=position,
                candidate_origin="v10-fresh",
                stream_raws={
                    stream: payload_raws[
                        "candidate-{:04d}.{}.prefix".format(
                            candidate_index, stream,
                        )
                    ]
                    for stream in ("stdout", "stderr")
                },
                code_manifest_sha256=launch["code_manifest_sha256"],
                repository_commit_id=launch["repository_commit_id"],
            )
            tasks.append(task)
        environments.append(environment)
    return tasks, environments


def _preflight_binding(preflight: AuthorizedPreflight) -> dict:
    return {
        "seal_repository_commit_id": preflight.seal_repository_commit_id,
        "authorization_sha256": preflight.authorization_sha256,
        "compute_canary_attestation_sha256": preflight.compute_canary_attestation_sha256,
        "controller_publisher_canary_receipt_sha256": preflight.controller_publisher_canary_receipt_sha256,
        "code_manifest_sha256": preflight.code_manifest_sha256,
        "snapshot_consumed": True,
        "full_launch_authorized": True,
    }


def load_authorized_confirmation(
    paths: V10Paths | None = None, *, snapshot_reader: SnapshotReader,
    seal_revision: str, preflight: AuthorizedPreflight | None = None,
) -> AuthorizedConfirmation:
    """Authenticate V10 and return cohorts only after its terminal scheduler gate."""
    paths = paths or paths_for()
    if type(seal_revision) is not str or COMMIT_RE.fullmatch(seal_revision) is None:
        raise SourceConsumerError("V10 seal revision must be exact 40-hex")
    _artifact_namespace(paths.artifact_dir, FULL_ARTIFACT_FILENAMES, paths.poll_dir.name)
    fixed_paths = {name: paths.artifact_dir / name for name in FULL_ARTIFACT_FILENAMES}
    # Stages and attestation are worker-derived scientific evidence.  Read only
    # controller evidence until the terminal scheduler gate has passed.
    payload_artifacts = {
        "source-audit-tree-stage-v10.json",
        "source-audit-census-stage-v10.json",
        "source-audit-split-stage-v10.json",
        "source-audit-attestation-stage-v10.json",
        "source-audit-attestation-v10.json",
        "source-audit-execution-receipt-v10.json",
    }
    fixed_raws = {
        name: _read_regular(path, "V10 artifact " + name)
        for name, path in fixed_paths.items() if name not in payload_artifacts
    }
    def decoded(name: str) -> dict:
        try:
            value = json.loads(fixed_raws[name].decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as err:
            raise SourceConsumerError("V10 artifact JSON changed") from err
        if type(value) is not dict or fixed_raws[name] != _canonical(value):
            raise SourceConsumerError("V10 artifact JSON is not canonical")
        return value
    launch_intent, _full_result, launch = _validate_full_launch_evidence(
        paths, fixed_raws,
    )
    if launch["repository_commit_id"] == seal_revision:
        raise SourceConsumerError("V10 launch receipt changed")
    binding = launch.get("preflight_authorization")
    if type(binding) is not dict or set(binding) != {
        "seal_repository_commit_id", "authorization_sha256",
        "compute_canary_attestation_sha256",
        "controller_publisher_canary_receipt_sha256",
        "code_manifest_sha256", "snapshot_consumed",
        "full_launch_authorized",
    }:
        raise SourceConsumerError("V10 launch preflight binding changed")
    if preflight is None:
        preflight = load_authorized_preflight(paths.preflight, snapshot_reader=snapshot_reader, seal_revision=binding.get("seal_repository_commit_id"))
    if (
        binding != _preflight_binding(preflight)
        or preflight.full_launch_authorized is not True
        or preflight.seal_repository_commit_id != launch["repository_commit_id"]
        or preflight.code_manifest_sha256 != launch["code_manifest_sha256"]
    ):
        raise SourceConsumerError("V10 full launch is not bound to authorized preflight")
    launch_sha = hashlib.sha256(
        fixed_raws["source-audit-launch-receipt-v10.json"]
    ).hexdigest()
    poll_raws, last_poll_sha, final_poll = _poll_bundle(
        paths.poll_dir, campaign=CAMPAIGN, poll_schema=FULL_POLL_SCHEMA,
        expected_tasks=SHARD_COUNT,
        launch_receipt_sha256=launch_sha,
        launch_recorded_utc=launch["accepted_utc"],
        expected_job_id=launch.get("job_id"),
        expected_job_name="pdb-source-v10-{}".format(
            launch.get("submission_token")
        ),
    )
    terminal = decoded("source-audit-scheduler-terminal-receipt-v10.json")
    _terminal_gate(
        terminal, schema=FULL_TERMINAL_RECEIPT_SCHEMA, campaign=CAMPAIGN,
        completed=SHARD_COUNT, last_poll_sha=last_poll_sha,
        expected_job_id=launch["job_id"],
    )
    tracked, sealed_source = _manifest_closure(
        paths.code_manifest, launch["code_manifest_sha256"],
        launch["repository_commit_id"], seal_revision, snapshot_reader,
    )
    _validate_rendered_slurm(
        launch_intent, sealed_source, template=FULL_SLURM_PROGRAM,
        inventory_sha256=launch["source_inventory_sha256"],
    )
    for name in payload_artifacts:
        fixed_raws[name] = _read_regular(
            fixed_paths[name], "V10 artifact " + name
        )
    execution_raw = fixed_raws["source-audit-execution-receipt-v10.json"]
    execution = decoded("source-audit-execution-receipt-v10.json")
    seal_plan = decoded("source-audit-seal-plan-v10.json")
    expected_prior = {"campaigns": PRIOR_CAMPAIGNS, "paths_read": [], "bytes_read": 0, "records_read": 0, "payloads_reused": 0, "scientific_bytes_reused": 0, "reuse_authorized": False}
    full_terminal_sha = hashlib.sha256(
        fixed_raws["source-audit-scheduler-terminal-receipt-v10.json"]
    ).hexdigest()
    if (
        execution.get("scheduler_rows") != final_poll["scheduler_rows"]
        or execution.get("scheduler_contract_rows")
        != final_poll["scheduler_contract_rows"]
        or execution.get("scheduler_rows_sha256")
        != _digest(final_poll["scheduler_rows"])
        or execution.get("scheduler_contract_rows_sha256")
        != _digest(final_poll["scheduler_contract_rows"])
    ):
        raise SourceConsumerError("V10 execution differs from terminal poll")
    if execution.get("schema") != EXECUTION_SCHEMA or execution.get("campaign") != CAMPAIGN or execution.get("logical_shards") != SHARD_COUNT or execution.get("candidates") != CANDIDATE_COUNT or execution.get("tasks_per_shard") != TASKS_PER_SHARD or execution.get("fresh_full_census") is not True or execution.get("scheduler_state_counts") != {"COMPLETED": SHARD_COUNT} or execution.get("scheduler_gate_passed") is not True or execution.get("scheduler_gate_passed_before_payload_read") is not True or execution.get("source_audit_complete") is not True or execution.get("confirmation_prelaunch_authorized") is not True or execution.get("prior_runtime_payload") != expected_prior or execution.get("partial_v10_reuse_authorized") is not False or execution.get("preflight_authorization") != binding or execution.get("terminal_poll_receipt_sha256") != last_poll_sha or execution.get("scheduler_terminal_receipt_sha256") != full_terminal_sha or execution.get("launch_receipt_sha256") != hashlib.sha256(fixed_raws["source-audit-launch-receipt-v10.json"]).hexdigest():
        raise SourceConsumerError("V10 execution/scheduler/no-reuse contract changed")
    if seal_plan.get("scheduler_gate_passed_before_payload_read") is not True or seal_plan.get("preflight_authorization") != binding or seal_plan.get("terminal_poll_receipt_sha256") != last_poll_sha or seal_plan.get("scheduler_terminal_receipt_sha256") != full_terminal_sha or seal_plan.get("logical_shards") != SHARD_COUNT or seal_plan.get("candidates") != CANDIDATE_COUNT:
        raise SourceConsumerError("V10 seal plan authorization changed")
    if (
        seal_plan.get("launch_receipt_sha256") != launch_sha
        or seal_plan.get("job_id") != launch["job_id"]
        or seal_plan.get("scheduler_rows") != final_poll["scheduler_rows"]
        or seal_plan.get("scheduler_contract_rows")
        != final_poll["scheduler_contract_rows"]
        or seal_plan.get("scheduler_rows_sha256")
        != _digest(final_poll["scheduler_rows"])
        or seal_plan.get("scheduler_contract_rows_sha256")
        != _digest(final_poll["scheduler_contract_rows"])
    ):
        raise SourceConsumerError("V10 seal plan scheduler chain changed")

    # Security ordering invariant: no path below data_root has been touched above.
    file_map, frozen_files = _validate_output_tree(paths, execution, launch)
    records, environments = _validate_shards(paths, file_map, launch, tracked)
    if [record.get("candidate_index") for record in records] != list(range(CANDIDATE_COUNT)) or execution.get("environment_records_sha256") != _digest(environments):
        raise SourceConsumerError("V10 full-census assembly changed")
    summaries = _classification_summaries(records)
    expected_gate, expected_cohorts = _recompute_split(records)
    if expected_gate["passed"] is not True:
        raise SourceConsumerError("V10 independently recomputed prelaunch gate failed")
    attestation_raw = fixed_raws["source-audit-attestation-v10.json"]
    attestation = decoded("source-audit-attestation-v10.json")
    attestation_keys = {
        "schema", "campaign", "benchmark_revision", "translator_source_sha256",
        "source_inventory_sha256", "source_inventory_records_sha256",
        "code_manifest_sha256", "split_seed", "split_rank_encoding",
        "split_role_labels", "limits", "full_census_fresh",
        "candidate_indices_sha256", "counts", "outcome_counts",
        "support_status_counts", "support_exclusion_counts",
        "resource_exclusion_counts", "resource_exclusions_by_family",
        "records_sha256", "cohorts", "cohorts_sha256", "prelaunch_gate",
        "confirmation_prelaunch_authorized", "records",
    }
    split_rank_encoding = (
        "SHA256(seed || NUL || role || NUL || family || NUL || "
        "problem_sha256 || NUL || canonical_path)"
    )
    if (
        set(attestation) != attestation_keys
        or attestation.get("schema") != ATTESTATION_SCHEMA
        or attestation.get("campaign") != CAMPAIGN
        or attestation.get("benchmark_revision") != BENCHMARK_REVISION
        or attestation.get("translator_source_sha256")
        != environments[0]["manifest_evidence"]["translator_files_sha256"]
        or attestation.get("source_inventory_sha256")
        != launch["source_inventory_sha256"]
        or attestation.get("source_inventory_records_sha256") != _digest([
            {key: record[key] for key in INVENTORY_RECORD_KEYS}
            for record in records
        ])
        or attestation.get("code_manifest_sha256")
        != launch["code_manifest_sha256"]
        or attestation.get("split_seed") != SPLIT_SEED
        or attestation.get("split_rank_encoding") != split_rank_encoding
        or attestation.get("split_role_labels") != {
            "confirmation_a": CONFIRMATION_ROLE,
            "guided_b_base": GUIDED_ROLE,
            "guided_b_top_up": GUIDED_TOP_UP_ROLE,
        }
        or attestation.get("limits") != _candidate_resource_contract()
        or attestation.get("full_census_fresh") is not True
        or attestation.get("candidate_indices_sha256")
        != _digest(list(range(CANDIDATE_COUNT)))
        or any(attestation.get(key) != value for key, value in summaries.items())
        or attestation.get("records") != records
        or attestation.get("records_sha256") != _digest(records)
        or attestation.get("cohorts") != expected_cohorts
        or attestation.get("cohorts_sha256") != _digest(expected_cohorts)
        or attestation.get("prelaunch_gate") != expected_gate
        or attestation.get("confirmation_prelaunch_authorized") is not True
        or execution.get("attestation_sha256")
        != hashlib.sha256(attestation_raw).hexdigest()
    ):
        raise SourceConsumerError("V10 attestation changed")
    stage_bindings = {
        "seal_plan_sha256": "source-audit-seal-plan-v10.json",
        "tree_stage_sha256": "source-audit-tree-stage-v10.json",
        "census_stage_sha256": "source-audit-census-stage-v10.json",
        "split_stage_sha256": "source-audit-split-stage-v10.json",
        "attestation_stage_sha256": "source-audit-attestation-stage-v10.json",
        "attestation_sha256": "source-audit-attestation-v10.json",
    }
    if any(
        execution.get(field) != hashlib.sha256(fixed_raws[name]).hexdigest()
        for field, name in stage_bindings.items()
    ):
        raise SourceConsumerError("V10 five-stage hash chain changed")
    tree_stage = decoded("source-audit-tree-stage-v10.json")
    census_stage = decoded("source-audit-census-stage-v10.json")
    split_stage = decoded("source-audit-split-stage-v10.json")
    attestation_stage = decoded("source-audit-attestation-stage-v10.json")
    census_keys = {
        "schema", "tree_stage_sha256", "candidate_count",
        "candidate_indices_sha256", "candidate_origin_counts",
        "whole_campaign_rerun", "prior_campaign_payloads_read",
        "prior_campaign_shards_used", "records_sha256", "counts",
        "outcome_counts", "support_status_counts", "support_exclusion_counts",
        "resource_exclusion_counts", "resource_exclusions_by_family",
    }
    if (
        set(tree_stage) != {
            "schema", "seal_plan_sha256", "output_tree",
            "output_tree_sha256", "environment_records_sha256",
        }
        or tree_stage.get("schema") != SCHEMA + "/tree-stage/v1"
        or tree_stage.get("seal_plan_sha256") != execution["seal_plan_sha256"]
        or tree_stage.get("output_tree") != execution["output_tree"]
        or tree_stage.get("output_tree_sha256") != execution["output_tree_sha256"]
        or tree_stage.get("environment_records_sha256")
        != execution["environment_records_sha256"]
        or set(census_stage) != census_keys
        or census_stage.get("schema") != SCHEMA + "/census-stage/v1"
        or census_stage.get("tree_stage_sha256") != execution["tree_stage_sha256"]
        or census_stage.get("candidate_count") != CANDIDATE_COUNT
        or census_stage.get("candidate_indices_sha256")
        != _digest(list(range(CANDIDATE_COUNT)))
        or census_stage.get("candidate_origin_counts") != {"v10-fresh": CANDIDATE_COUNT}
        or census_stage.get("whole_campaign_rerun") is not True
        or census_stage.get("prior_campaign_payloads_read") != []
        or census_stage.get("prior_campaign_shards_used") != 0
        or census_stage.get("records_sha256") != _digest(records)
        or any(census_stage.get(key) != value for key, value in summaries.items())
        or set(split_stage) != {
            "schema", "census_stage_sha256", "split_seed",
            "split_rank_encoding", "cohorts", "cohorts_sha256",
            "prelaunch_gate", "confirmation_prelaunch_authorized",
        }
        or split_stage.get("schema") != SCHEMA + "/split-stage/v1"
        or split_stage.get("census_stage_sha256") != execution["census_stage_sha256"]
        or split_stage.get("split_seed") != SPLIT_SEED
        or split_stage.get("split_rank_encoding") != split_rank_encoding
        or split_stage.get("cohorts") != expected_cohorts
        or split_stage.get("cohorts_sha256") != _digest(expected_cohorts)
        or split_stage.get("prelaunch_gate") != expected_gate
        or split_stage.get("confirmation_prelaunch_authorized") is not True
        or set(attestation_stage) != {
            "schema", "split_stage_sha256", "attestation_path",
            "attestation_bytes", "attestation_sha256",
            "attestation_records_sha256", "cohorts_sha256",
            "confirmation_prelaunch_authorized",
        }
        or attestation_stage.get("schema") != SCHEMA + "/attestation-stage/v1"
        or attestation_stage.get("split_stage_sha256") != execution["split_stage_sha256"]
        or attestation_stage.get("attestation_path") != str(paths.attestation)
        or attestation_stage.get("attestation_bytes") != len(attestation_raw)
        or attestation_stage.get("attestation_sha256")
        != hashlib.sha256(attestation_raw).hexdigest()
        or attestation_stage.get("attestation_records_sha256") != _digest(records)
        or attestation_stage.get("cohorts_sha256") != _digest(expected_cohorts)
        or attestation_stage.get("confirmation_prelaunch_authorized") is not True
    ):
        raise SourceConsumerError("V10 stage content chain changed")
    if (
        set(execution) != {
            "schema", "campaign", "benchmark_revision", "logical_shards",
            "candidates", "tasks_per_shard", "fresh_full_census",
            "candidate_indices_sha256", "launch_receipt_sha256",
            "source_inventory_sha256", "code_manifest_sha256",
            "resource_profile", "scheduler_state_counts", "scheduler_rows",
            "scheduler_rows_sha256", "scheduler_contract_rows",
            "scheduler_contract_rows_sha256",
            "scheduler_terminal_receipt_sha256",
            "terminal_poll_receipt_sha256", "scheduler_gate_passed",
            "scheduler_gate_passed_before_payload_read", "output_tree",
            "output_tree_sha256", "environment_records_sha256",
            "prior_runtime_payload", "partial_v10_reuse_authorized",
            "preflight_authorization", "seal_recovery_protocol",
            "seal_plan_sha256", "tree_stage_sha256", "census_stage_sha256",
            "split_stage_sha256", "attestation_stage_sha256",
            "attestation_sha256", "attestation_records_sha256",
            "cohorts_sha256", "outcome_counts", "support_status_counts",
            "support_exclusion_counts", "resource_exclusion_counts",
            "resource_exclusions_by_family", "prelaunch_gate",
            "source_audit_complete", "confirmation_prelaunch_authorized",
        }
        or execution.get("benchmark_revision") != BENCHMARK_REVISION
        or execution.get("candidate_indices_sha256")
        != _digest(list(range(CANDIDATE_COUNT)))
        or execution.get("source_inventory_sha256")
        != launch["source_inventory_sha256"]
        or execution.get("code_manifest_sha256") != launch["code_manifest_sha256"]
        or execution.get("resource_profile") != _resource_profile("0-819")
        or execution.get("seal_recovery_protocol")
        != "exclusive-five-stage-hash-chain-v1"
        or execution.get("attestation_records_sha256") != _digest(records)
        or execution.get("cohorts_sha256") != _digest(expected_cohorts)
        or execution.get("prelaunch_gate") != expected_gate
        or any(
            execution.get(key) != value
            for key, value in summaries.items() if key != "counts"
        )
    ):
        raise SourceConsumerError("V10 execution scientific summary changed")
    confirmation_indices = expected_cohorts["confirmation_a"]["candidate_indices"]
    guided_indices = expected_cohorts["guided_b"]["candidate_indices"]
    artifact_hashes = _artifact_snapshot(paths.artifact_dir, FULL_ARTIFACT_FILENAMES, paths.poll_dir.name, fixed_raws, poll_raws, seal_revision, snapshot_reader)
    # Re-read every scientific byte after snapshot consumption to reject drift.
    for item in frozen_files:
        raw = _read_regular(paths.data_root / item["path"], "stable V10 output")
        if _file_record(item["path"], raw, paths.data_root / item["path"]) != item:
            raise SourceConsumerError("V10 output changed during authorization")
    _validate_output_namespace_stable(paths, execution)
    eligible = [record for record in records if record.get("eligible_for_cohort") is True]
    return AuthorizedConfirmation(
        campaign=CAMPAIGN,
        benchmark_revision=attestation.get("benchmark_revision"),
        seal_repository_commit_id=seal_revision,
        source_inventory_sha256=launch["source_inventory_sha256"],
        code_manifest_sha256=launch["code_manifest_sha256"],
        launch_receipt_sha256=hashlib.sha256(fixed_raws["source-audit-launch-receipt-v10.json"]).hexdigest(),
        execution_receipt_sha256=hashlib.sha256(execution_raw).hexdigest(),
        attestation_sha256=hashlib.sha256(attestation_raw).hexdigest(),
        preflight=preflight,
        confirmation_a=tuple(_freeze(records[index]) for index in confirmation_indices),
        guided_b=tuple(_freeze(records[index]) for index in guided_indices),
        eligible_records=tuple(_freeze(record) for record in eligible),
        all_records=tuple(_freeze(record) for record in records),
        outcome_counts=_freeze(attestation.get("outcome_counts")),
        resource_exclusions_by_family=_freeze(attestation.get("resource_exclusions_by_family")),
        tracked_file_sha256=_freeze({**tracked, **artifact_hashes}),
    )


__all__ = [
    "AuthorizedConfirmation", "AuthorizedPreflight", "SourceConsumerError",
    "V10Paths", "V10PreflightPaths", "load_authorized_confirmation",
    "load_authorized_preflight", "paths_for", "preflight_paths_for",
]
