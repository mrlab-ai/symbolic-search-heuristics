#!/usr/bin/env python3
"""Frozen, outcome-independent inventory for the confirmation study.

This module only enumerates benchmark sources.  It deliberately does not
classify source support, select either confirmation arm, or inspect experiment
outcomes.  Those operations belong to later, separately frozen protocols.
"""

from __future__ import annotations

import hashlib
import json
import stat
import subprocess
from dataclasses import asdict, dataclass, replace
from pathlib import Path


class InventoryError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_BENCHMARKS = Path(
    "/nobackup/proj/disk/dfsplan/personal/jendrik/downward-benchmarks-wbh"
)
COST_MANIFEST_PATH = SCRIPT_DIR / "suite_wbh_operator_costs.json"
SHADOW_ATTESTATION_PATH = (
    SCRIPT_DIR / "pdb_terminal_incidence_shadow_cost_attestation.json"
)

BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
COST_MANIFEST_SHA256 = (
    "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168"
)
SHADOW_ATTESTATION_SHA256 = (
    "bf2c42860fad91c56620c90a41657ab472f4d58acd184a7580c7b5994aa72d04"
)

# The map is intentionally explicit.  It covers exactly the directories left
# after content-disjointness filtering and only merges named encodings or
# competition tracks of the same benchmark family.
DIRECTORY_TO_FAMILY = {
    "agricola-opt18-strips": "agricola",
    "agricola-sat18-strips": "agricola",
    "airport-adl": "airport",
    "assembly": "assembly",
    "barman-mco14-strips": "barman",
    "barman-sat11-strips": "barman",
    "caldera-opt18-adl": "caldera",
    "caldera-sat18-adl": "caldera",
    "caldera-split-opt18-adl": "caldera",
    "caldera-split-sat18-adl": "caldera",
    "cavediving-14-adl": "cavediving",
    "citycar-opt14-adl": "citycar",
    "citycar-sat14-adl": "citycar",
    "data-network-opt18-strips": "data-network",
    "data-network-sat18-strips": "data-network",
    "elevators-sat08-strips": "elevators",
    "elevators-sat11-strips": "elevators",
    "flashfill-sat18-adl": "flashfill",
    "floortile-sat11-strips": "floortile",
    "folding-opt23-adl": "folding",
    "folding-sat23-adl": "folding",
    "ged-sat14-strips": "ged",
    "hiking-agl14-strips": "hiking",
    "labyrinth-opt23-adl": "labyrinth",
    "labyrinth-sat23-adl": "labyrinth",
    "maintenance-opt14-adl": "maintenance",
    "maintenance-sat14-adl": "maintenance",
    "miconic-fulladl": "miconic",
    "miconic-simpleadl": "miconic",
    "nomystery-sat11-strips": "nomystery",
    "nurikabe-opt18-adl": "nurikabe",
    "nurikabe-sat18-adl": "nurikabe",
    "openstacks": "openstacks",
    "openstacks-agl14-strips": "openstacks",
    "openstacks-opt08-adl": "openstacks",
    "openstacks-sat08-adl": "openstacks",
    "openstacks-sat08-strips": "openstacks",
    "openstacks-sat11-strips": "openstacks",
    "openstacks-sat14-strips": "openstacks",
    "openstacks-strips": "openstacks",
    "optical-telegraphs": "optical-telegraphs",
    "organic-synthesis-sat18-strips": "organic-synthesis",
    "organic-synthesis-split-opt18-strips": "organic-synthesis",
    "organic-synthesis-split-sat18-strips": "organic-synthesis",
    "parcprinter-sat11-strips": "parcprinter",
    "parking-sat11-strips": "parking",
    "parking-sat14-strips": "parking",
    "petri-net-alignment-opt18-strips": "petri-net-alignment",
    "philosophers": "philosophers",
    "psr-large": "psr",
    "psr-middle": "psr",
    "quantum-layout-opt23-strips": "quantum-layout",
    "quantum-layout-sat23-strips": "quantum-layout",
    "recharging-robots-opt23-adl": "recharging-robots",
    "recharging-robots-sat23-adl": "recharging-robots",
    "ricochet-robots-opt23-adl": "ricochet-robots",
    "ricochet-robots-sat23-adl": "ricochet-robots",
    "schedule": "schedule",
    "settlers-opt18-adl": "settlers",
    "settlers-sat18-adl": "settlers",
    "slitherlink-opt23-adl": "slitherlink",
    "slitherlink-sat23-adl": "slitherlink",
    "snake-sat18-strips": "snake",
    "sokoban-sat08-strips": "sokoban",
    "sokoban-sat11-strips": "sokoban",
    "spider-opt18-strips": "spider",
    "spider-sat18-strips": "spider",
    "termes-sat18-strips": "termes",
    "tetris-sat14-strips": "tetris",
    "thoughtful-mco14-strips": "thoughtful",
    "thoughtful-sat14-strips": "thoughtful",
    "transport-sat08-strips": "transport",
    "transport-sat11-strips": "transport",
    "transport-sat14-strips": "transport",
    "trucks": "trucks",
    "visitall-sat11-strips": "visitall",
    "visitall-sat14-strips": "visitall",
    "woodworking-sat08-strips": "woodworking",
    "woodworking-sat11-strips": "woodworking",
}

# Every directory represented by either frozen prior artifact.  Keeping this
# separate from the residual map makes the meaning of "unrepresented" explicit
# and auditable rather than inferring it from track-name syntax.
PRIOR_DIRECTORY_TO_FAMILY = {
    "agricola-opt18-strips": "agricola",
    "agricola-sat18-strips": "agricola",
    "airport": "airport",
    "barman-mco14-strips": "barman",
    "barman-opt11-strips": "barman",
    "barman-opt14-strips": "barman",
    "barman-sat11-strips": "barman",
    "barman-sat14-strips": "barman",
    "blocks": "blocks",
    "caldera-opt18-adl": "caldera",
    "caldera-sat18-adl": "caldera",
    "caldera-split-opt18-adl": "caldera",
    "caldera-split-sat18-adl": "caldera",
    "cavediving-14-adl": "cavediving",
    "childsnack-opt14-strips": "childsnack",
    "childsnack-sat14-strips": "childsnack",
    "depot": "depot",
    "driverlog": "driverlog",
    "elevators-opt08-strips": "elevators",
    "elevators-opt11-strips": "elevators",
    "floortile-opt11-strips": "floortile",
    "floortile-opt14-strips": "floortile",
    "floortile-sat11-strips": "floortile",
    "floortile-sat14-strips": "floortile",
    "freecell": "freecell",
    "ged-opt14-strips": "ged",
    "grid": "grid",
    "gripper": "gripper",
    "hiking-agl14-strips": "hiking",
    "hiking-opt14-strips": "hiking",
    "hiking-sat14-strips": "hiking",
    "logistics00": "logistics",
    "logistics98": "logistics",
    "maintenance-sat14-adl": "maintenance",
    "miconic": "miconic",
    "miconic-simpleadl": "miconic",
    "movie": "movie",
    "mprime": "mprime",
    "mystery": "mystery",
    "nomystery-opt11-strips": "nomystery",
    "nomystery-sat11-strips": "nomystery",
    "nurikabe-opt18-adl": "nurikabe",
    "nurikabe-sat18-adl": "nurikabe",
    "openstacks-opt08-strips": "openstacks",
    "openstacks-opt11-strips": "openstacks",
    "openstacks-opt14-strips": "openstacks",
    "openstacks-strips": "openstacks",
    "organic-synthesis-opt18-strips": "organic-synthesis",
    "organic-synthesis-sat18-strips": "organic-synthesis",
    "organic-synthesis-split-opt18-strips": "organic-synthesis",
    "organic-synthesis-split-sat18-strips": "organic-synthesis",
    "parcprinter-08-strips": "parcprinter",
    "parcprinter-opt11-strips": "parcprinter",
    "parking-opt11-strips": "parking",
    "parking-opt14-strips": "parking",
    "parking-sat11-strips": "parking",
    "parking-sat14-strips": "parking",
    "pathways": "pathways",
    "pegsol-08-strips": "pegsol",
    "pegsol-opt11-strips": "pegsol",
    "pipesworld-notankage": "pipesworld",
    "pipesworld-tankage": "pipesworld",
    "psr-small": "psr",
    "quantum-layout-opt23-strips": "quantum-layout",
    "quantum-layout-sat23-strips": "quantum-layout",
    "rovers": "rovers",
    "rubiks-cube-opt23-adl": "rubiks-cube",
    "rubiks-cube-sat23-adl": "rubiks-cube",
    "satellite": "satellite",
    "scanalyzer-08-strips": "scanalyzer",
    "scanalyzer-opt11-strips": "scanalyzer",
    "schedule": "schedule",
    "slitherlink-opt23-adl": "slitherlink",
    "slitherlink-sat23-adl": "slitherlink",
    "snake-opt18-strips": "snake",
    "snake-sat18-strips": "snake",
    "sokoban-opt08-strips": "sokoban",
    "sokoban-opt11-strips": "sokoban",
    "storage": "storage",
    "termes-opt18-strips": "termes",
    "termes-sat18-strips": "termes",
    "tetris-opt14-strips": "tetris",
    "tetris-sat14-strips": "tetris",
    "thoughtful-mco14-strips": "thoughtful",
    "thoughtful-sat14-strips": "thoughtful",
    "tidybot-opt11-strips": "tidybot",
    "tidybot-opt14-strips": "tidybot",
    "tidybot-sat11-strips": "tidybot",
    "tpp": "tpp",
    "transport-opt08-strips": "transport",
    "transport-opt11-strips": "transport",
    "transport-opt14-strips": "transport",
    "transport-sat08-strips": "transport",
    "transport-sat11-strips": "transport",
    "transport-sat14-strips": "transport",
    "trucks-strips": "trucks",
    "visitall-opt11-strips": "visitall",
    "visitall-opt14-strips": "visitall",
    "visitall-sat11-strips": "visitall",
    "visitall-sat14-strips": "visitall",
    "woodworking-opt08-strips": "woodworking",
    "woodworking-opt11-strips": "woodworking",
    "woodworking-sat08-strips": "woodworking",
    "woodworking-sat11-strips": "woodworking",
    "zenotravel": "zenotravel",
}

EXPECTED_TOP_LEVEL_DIRECTORIES = 147
EXPECTED_ALL_PATHS = 4088
EXPECTED_ALL_UNIQUE_PROBLEM_HASHES = 3625
EXPECTED_COST_RECORDS = 1697
EXPECTED_COST_UNIQUE_PROBLEM_HASHES = 1525
EXPECTED_SHADOW_RECORDS = 460
EXPECTED_SHADOW_UNIQUE_PROBLEM_HASHES = 460
EXPECTED_PRIOR_UNIQUE_PROBLEM_HASHES = 1985
EXPECTED_PRIOR_IDENTITIES = 2157
EXPECTED_RESIDUE_PATHS = 1733
EXPECTED_RESIDUE_IDENTITIES = 1733
EXPECTED_CANDIDATES = 1640
EXPECTED_RESIDUE_DIRECTORIES = 79
EXPECTED_CANDIDATE_DIRECTORIES = 78
EXPECTED_FAMILIES = 43
EXPECTED_REPRESENTED_SHADOW_FAMILIES = 23
EXPECTED_SHADOW_UNREPRESENTED_FAMILIES = 20
EXPECTED_PRIOR_DIRECTORY_FAMILIES = 105
EXPECTED_PRIOR_FAMILY_LEDGER_RECORDS = 2157
EXPECTED_ALL_PRIOR_FAMILIES = 52
EXPECTED_REPRESENTED_ALL_PRIOR_FAMILIES = 30
EXPECTED_ALL_PRIOR_UNREPRESENTED_FAMILIES = 13
EXPECTED_DUPLICATE_GROUPS = 75
EXPECTED_DISCARDED_ALIASES = 93
EXPECTED_NAME_OVERLAP_AFTER_HASH_FILTER = 0
EXPECTED_RESIDUE_PRIOR_IDENTITY_OVERLAP = 0
EXPECTED_RESIDUE_PRIOR_PROBLEM_HASH_OVERLAP = 0

FAMILY_MAP_SHA256 = (
    "7e05588a27ccae96fa50c58417b6bd0417532121b668b1205850adee03591dc1"
)
SHADOW_FAMILIES = (
    "agricola",
    "barman",
    "caldera",
    "cavediving",
    "childsnack",
    "floortile",
    "hiking",
    "maintenance",
    "miconic",
    "nomystery",
    "nurikabe",
    "openstacks",
    "organic-synthesis",
    "parking",
    "quantum-layout",
    "rubiks-cube",
    "schedule",
    "slitherlink",
    "snake",
    "termes",
    "tetris",
    "thoughtful",
    "tidybot",
    "transport",
    "visitall",
    "woodworking",
)
ALL_PRIOR_FAMILIES = tuple(sorted(set(PRIOR_DIRECTORY_TO_FAMILY.values())))
ALL_PRIOR_UNREPRESENTED_FAMILIES = (
    "assembly",
    "citycar",
    "data-network",
    "flashfill",
    "folding",
    "labyrinth",
    "optical-telegraphs",
    "petri-net-alignment",
    "philosophers",
    "recharging-robots",
    "ricochet-robots",
    "settlers",
    "spider",
)
SHADOW_FAMILY_SEQUENCE_SHA256 = (
    "f1f6877788c0565179660ac1892268fc85235ab73729053c285dd6cfeb01fa28"
)
PRIOR_DIRECTORY_FAMILY_MAP_SHA256 = (
    "790426b33b085c70ae2a3b63a337616e14a0446db91ff40d854634996d345a52"
)
PRIOR_FAMILY_LEDGER_SHA256 = (
    "9de66fb087855ede93eabf3193e462bbacdde1bcdc7b2ddc48ab3168b1f31101"
)
ALL_PRIOR_FAMILY_SEQUENCE_SHA256 = (
    "fe05c88ed11512cf25cb68bfe0c2522558bfe23daa1090df7182fc6df4206a59"
)
ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256 = (
    "2b461a68f2bcad8bdeb18304ec1cfad68dd287994cce0770b7392fcc285f9ec1"
)
SHADOW_UNREPRESENTED_FAMILY_SEQUENCE_SHA256 = (
    "9b831aa026deeda951f8aefd3ce8632ec0b82fb7f5231d3fbb5acf9dbd97f746"
)
REPRESENTED_ALL_PRIOR_FAMILY_SEQUENCE_SHA256 = (
    "e72960e757d89ce266c8ff2a670956bffece24cc296ce1b19eafa4758a82a8af"
)
DIRECTORY_SEQUENCE_SHA256 = (
    "7eb95fd8f2cb5c49bde50bef203e99ec3985a074c256c969914a4069e79004c7"
)
ALL_PATH_RECORDS_SHA256 = (
    "def0e74b0bb4fbc656349a1864de16fc4856c4072d5c9cc8859bc6f1dab0dcf1"
)
ALL_UNIQUE_PROBLEM_HASHES_SHA256 = (
    "545c64781179c559e5d138c721336b173fe90c89a87a371448a2ef5941f7db18"
)
COST_PROBLEM_HASHES_SHA256 = (
    "aa944356dccd89e87229e0af2db8038292fd537e99a18358f0ad74c6a9fb63b6"
)
SHADOW_PROBLEM_HASHES_SHA256 = (
    "37534406e44c964a9ef6853f24b720ec7bbe4ff8d0aa89d653a243d5459d8b21"
)
PRIOR_PROBLEM_HASHES_SHA256 = (
    "2b34bdd0a7829105cd1cd55536f68d65b60448b509fe3fd1166d34e6108ae74d"
)
PRIOR_IDENTITIES_SHA256 = (
    "176e5e02f07caf47f8e144b963033ca0d248624d0182b4da842df977e439f73d"
)
PRIOR_IDENTITY_LEDGER_SHA256 = (
    "d4b6aaae00581781dfb4dc7947f7fbec592e19a60167bb5c4a35bd6d2abb3f86"
)
RESIDUE_PATH_RECORDS_SHA256 = (
    "44c5b7a4d74998d5f7b065093fa68afa1ff53c4b38ba3fb732dcc5f611f45468"
)
RESIDUE_IDENTITIES_SHA256 = (
    "922b7bc93d2006c97625038c86263f3dc211a44e28553cfaf29ff753cf0746d6"
)
CANDIDATE_RECORDS_SHA256 = (
    "5add608b876d236a3fc6b3ab0eaeb67a4b7629c9328039ba2752c4c380e3035c"
)
ALIAS_GROUPS_SHA256 = (
    "d9843d73b854eeb58b37dcdfad9265daf7552d909ab0df865b0ff9b13d6dc425"
)


@dataclass(frozen=True)
class SourcePath:
    directory: str
    problem: str
    problem_file: str
    domain_file: str
    domain_sha256: str
    problem_sha256: str


@dataclass(frozen=True, order=True)
class TaskIdentity:
    directory: str
    problem: str


@dataclass(frozen=True)
class PriorIdentity:
    source_artifact: str
    directory: str
    family: str
    problem: str
    domain_file: str | None
    problem_file: str | None
    domain_sha256: str
    problem_sha256: str


@dataclass(frozen=True)
class PriorFamilyProvenance:
    source_artifact: str
    directory: str
    family: str
    problem: str
    problem_sha256: str


@dataclass(frozen=True)
class Candidate:
    directory: str
    family: str
    problem: str
    domain_file: str
    problem_file: str
    domain_sha256: str
    problem_sha256: str

    @property
    def canonical_path(self) -> str:
        return self.problem_file

    @property
    def is_shadow_family(self) -> bool:
        return self.family in SHADOW_FAMILIES

    @property
    def is_shadow_unrepresented(self) -> bool:
        return self.family not in SHADOW_FAMILIES

    @property
    def is_all_prior_represented(self) -> bool:
        return self.family in ALL_PRIOR_FAMILIES

    @property
    def is_all_prior_unrepresented(self) -> bool:
        return self.family not in ALL_PRIOR_FAMILIES


@dataclass(frozen=True)
class AliasGroup:
    problem_sha256: str
    canonical: Candidate
    aliases: tuple[Candidate, ...]


@dataclass(frozen=True)
class Inventory:
    directories: tuple[str, ...]
    residue_directories: tuple[str, ...]
    residue_families: tuple[str, ...]
    represented_shadow_families: tuple[str, ...]
    shadow_unrepresented_families: tuple[str, ...]
    represented_all_prior_families: tuple[str, ...]
    all_prior_unrepresented_families: tuple[str, ...]
    candidates: tuple[Candidate, ...]
    alias_groups: tuple[AliasGroup, ...]
    prior_identity_ledger: tuple[PriorIdentity, ...]
    prior_family_ledger: tuple[PriorFamilyProvenance, ...]
    residue_identities: tuple[TaskIdentity, ...]
    all_path_count: int
    all_unique_problem_hash_count: int
    residue_path_count: int
    discarded_alias_count: int
    name_overlap_after_hash_filter_count: int
    prior_identity_overlap_count: int
    prior_problem_hash_overlap_count: int
    digests: tuple[tuple[str, str], ...]


def canonical_json(value) -> bytes:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    except (TypeError, ValueError) as err:
        raise InventoryError("value is not canonical finite JSON") from err


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as err:
        raise InventoryError("cannot hash {}".format(path)) from err
    return digest.hexdigest()


def _is_sha256(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and not any(char not in "0123456789abcdef" for char in value)
    )


def _repository_state(root: Path) -> tuple[str, str, str]:
    commands = (
        ("rev-parse", "HEAD"),
        ("rev-parse", "--show-toplevel"),
        ("status", "--porcelain=v1", "--untracked-files=all"),
    )
    outputs = []
    for arguments in commands:
        try:
            result = subprocess.run(
                ["git", "-C", str(root), *arguments],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except (OSError, subprocess.CalledProcessError) as err:
            raise InventoryError("cannot inspect benchmark checkout") from err
        outputs.append(result.stdout.strip())
    return tuple(outputs)


def validate_benchmark_checkout(benchmarks: Path) -> Path:
    root = Path(benchmarks).resolve()
    if not root.is_dir():
        raise InventoryError("benchmark root is not a directory")
    revision, top_level, status_text = _repository_state(root)
    if revision != BENCHMARK_REVISION:
        raise InventoryError("benchmark checkout is at the wrong revision")
    if Path(top_level).resolve() != root:
        raise InventoryError("benchmark root is not the checkout top level")
    if status_text:
        raise InventoryError("benchmark checkout is dirty")
    return root


def _top_level_directories(root: Path) -> tuple[str, ...]:
    try:
        directories = tuple(sorted(
            entry.name
            for entry in root.iterdir()
            if entry.is_dir()
            and not entry.name.startswith(".")
            and entry.name != "unofficial-reformulations"
        ))
    except OSError as err:
        raise InventoryError("cannot enumerate benchmark directories") from err
    if len(directories) != EXPECTED_TOP_LEVEL_DIRECTORIES:
        raise InventoryError("top-level benchmark directory count changed")
    return directories


def _relative_regular(path, root: Path, directory: str) -> tuple[str, Path]:
    candidate = Path(path)
    try:
        info = candidate.lstat()
    except OSError as err:
        raise InventoryError("cannot inspect benchmark source") from err
    if candidate.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise InventoryError("benchmark source is not a regular file")
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(root).as_posix()
    except ValueError as err:
        raise InventoryError("benchmark source escapes the pinned root") from err
    if not relative.startswith(directory + "/"):
        raise InventoryError("benchmark source escapes its top-level directory")
    return relative, resolved


def _source_key(record) -> tuple[str, str, str, str]:
    return (
        record.directory,
        record.problem,
        record.problem_file,
        record.domain_file,
    )


def _candidate_sort_key(record: Candidate) -> tuple[str, str, str, str]:
    return (
        record.family,
        record.directory,
        record.problem,
        record.problem_sha256,
    )


def _enumerate_source_paths(
    root: Path, directories: tuple[str, ...]
) -> tuple[SourcePath, ...]:
    try:
        from downward.suites import build_suite
    except ImportError as err:
        raise InventoryError("downward suite dependency is unavailable") from err

    hash_cache = {}
    records = []
    for directory in directories:
        try:
            tasks = tuple(build_suite(str(root), [directory]))
        except Exception as err:
            raise InventoryError(
                "cannot enumerate benchmark directory {}".format(directory)
            ) from err
        if not tasks:
            raise InventoryError(
                "benchmark directory {} supplies no tasks".format(directory)
            )
        for task in tasks:
            if task.domain != directory:
                raise InventoryError("suite task directory identity changed")
            problem_file, problem_path = _relative_regular(
                task.problem_file, root, directory
            )
            domain_file, domain_path = _relative_regular(
                task.domain_file, root, directory
            )
            for relative, path in (
                (problem_file, problem_path),
                (domain_file, domain_path),
            ):
                if relative not in hash_cache:
                    hash_cache[relative] = sha256_file(path)
            records.append(SourcePath(
                directory=directory,
                problem=task.problem,
                problem_file=problem_file,
                domain_file=domain_file,
                domain_sha256=hash_cache[domain_file],
                problem_sha256=hash_cache[problem_file],
            ))
    return tuple(sorted(records, key=_source_key))


def _normalize_prior_records(
    tasks, source_artifact: str, *, paths_required: bool
) -> tuple[PriorIdentity, ...]:
    if not isinstance(tasks, list):
        raise InventoryError("frozen prior manifest tasks changed")
    records = []
    for record in tasks:
        if not isinstance(record, dict):
            raise InventoryError("frozen prior manifest task record changed")
        directory = record.get("domain")
        problem = record.get("problem")
        domain_file = record.get("domain_file")
        problem_file = record.get("problem_file")
        if (
            not isinstance(directory, str)
            or not directory
            or "/" in directory
            or not isinstance(problem, str)
            or not problem
            or not _is_sha256(record.get("domain_sha256"))
            or not _is_sha256(record.get("problem_sha256"))
        ):
            raise InventoryError("frozen prior identity record changed")
        if paths_required:
            if (
                not isinstance(domain_file, str)
                or not domain_file.startswith(directory + "/")
                or not isinstance(problem_file, str)
                or not problem_file.startswith(directory + "/")
            ):
                raise InventoryError("frozen prior source path changed")
        elif domain_file is not None or problem_file is not None:
            raise InventoryError("unexpected prior source path fields")
        family = PRIOR_DIRECTORY_TO_FAMILY.get(directory)
        if family is None:
            raise InventoryError("prior directory lacks frozen family provenance")
        records.append(PriorIdentity(
            source_artifact=source_artifact,
            directory=directory,
            family=family,
            problem=problem,
            domain_file=domain_file,
            problem_file=problem_file,
            domain_sha256=record["domain_sha256"],
            problem_sha256=record["problem_sha256"],
        ))
    return tuple(sorted(records, key=lambda record: (
        record.directory,
        record.problem,
        record.problem_sha256,
        record.source_artifact,
    )))


def _load_frozen_prior_records(
    path: Path,
    expected_file_sha256: str,
    expected_records: int,
    *,
    paths_required: bool,
) -> tuple[PriorIdentity, ...]:
    try:
        info = path.lstat()
    except OSError as err:
        raise InventoryError("cannot inspect frozen prior manifest") from err
    if path.is_symlink() or not stat.S_ISREG(info.st_mode):
        raise InventoryError("frozen prior manifest is not a regular file")
    if sha256_file(path) != expected_file_sha256:
        raise InventoryError("frozen prior manifest bytes changed")
    try:
        data = json.loads(path.read_text(encoding="ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise InventoryError("cannot load frozen prior manifest") from err
    tasks = data.get("tasks") if isinstance(data, dict) else None
    if not isinstance(tasks, list) or len(tasks) != expected_records:
        raise InventoryError("frozen prior manifest task records changed")
    return _normalize_prior_records(
        tasks, path.name, paths_required=paths_required
    )


def _load_frozen_problem_hashes(
    path: Path, expected_file_sha256: str, expected_records: int
) -> tuple[str, ...]:
    records = _load_frozen_prior_records(
        path,
        expected_file_sha256,
        expected_records,
        paths_required=path.name == COST_MANIFEST_PATH.name,
    )
    return tuple(record.problem_sha256 for record in records)


def _attach_prior_source_paths(
    ledger: tuple[PriorIdentity, ...], all_paths: tuple[SourcePath, ...]
) -> tuple[PriorIdentity, ...]:
    by_identity = {}
    for record in all_paths:
        identity = TaskIdentity(record.directory, record.problem)
        if identity in by_identity:
            raise InventoryError("universal scan repeats a task identity")
        by_identity[identity] = record
    attached = []
    for prior in ledger:
        identity = TaskIdentity(prior.directory, prior.problem)
        source = by_identity.get(identity)
        if source is None or any((
            source.domain_sha256 != prior.domain_sha256,
            source.problem_sha256 != prior.problem_sha256,
            prior.domain_file is not None
            and source.domain_file != prior.domain_file,
            prior.problem_file is not None
            and source.problem_file != prior.problem_file,
        )):
            raise InventoryError("prior identity disagrees with universal sources")
        attached.append(replace(
            prior,
            domain_file=source.domain_file,
            problem_file=source.problem_file,
        ))
    return tuple(attached)


def _build_prior_family_ledger(
    identities: tuple[PriorIdentity, ...]
) -> tuple[PriorFamilyProvenance, ...]:
    directories = {record.directory for record in identities}
    if directories != set(PRIOR_DIRECTORY_TO_FAMILY):
        raise InventoryError("prior family provenance map is incomplete or overbroad")
    ledger = tuple(PriorFamilyProvenance(
        source_artifact=record.source_artifact,
        directory=record.directory,
        family=record.family,
        problem=record.problem,
        problem_sha256=record.problem_sha256,
    ) for record in identities)
    if any(
        record.family != PRIOR_DIRECTORY_TO_FAMILY.get(record.directory)
        for record in ledger
    ):
        raise InventoryError("prior family provenance changed")
    return ledger


def _exclude_prior_paths(
    records: tuple[SourcePath, ...],
    prior_identities: set[TaskIdentity],
    prior_hashes: set[str],
) -> tuple[SourcePath, ...]:
    residue = tuple(record for record in records if (
        TaskIdentity(record.directory, record.problem) not in prior_identities
        and record.problem_sha256 not in prior_hashes
    ))
    identity_overlap = {
        TaskIdentity(record.directory, record.problem) for record in residue
    } & prior_identities
    hash_overlap = {
        record.problem_sha256 for record in residue
    } & prior_hashes
    if identity_overlap or hash_overlap:
        raise InventoryError("prior task identity leaked into the residue")
    return residue


def _validate_family_map(residue_directories: tuple[str, ...]) -> None:
    if set(residue_directories) != set(DIRECTORY_TO_FAMILY):
        raise InventoryError("conservative family map is incomplete or overbroad")


def _canonicalize(
    records: tuple[Candidate, ...]
) -> tuple[tuple[Candidate, ...], tuple[AliasGroup, ...]]:
    by_hash = {}
    for record in records:
        by_hash.setdefault(record.problem_sha256, []).append(record)
    candidates = []
    groups = []
    for problem_sha256, aliases in by_hash.items():
        ordered = tuple(sorted(aliases, key=_source_key))
        if len({record.family for record in ordered}) != 1:
            raise InventoryError("duplicate problem hash crosses benchmark families")
        candidates.append(ordered[0])
        groups.append(AliasGroup(problem_sha256, ordered[0], ordered))
    return (
        tuple(sorted(candidates, key=_candidate_sort_key)),
        tuple(sorted(groups, key=lambda group: group.problem_sha256)),
    )


def _records_json(records) -> list[dict]:
    return [asdict(record) for record in records]


def _alias_json(groups: tuple[AliasGroup, ...]) -> list[dict]:
    return [
        {
            "problem_sha256": group.problem_sha256,
            "canonical": asdict(group.canonical),
            "aliases": _records_json(group.aliases),
        }
        for group in groups
    ]


def _require_digest(label: str, actual: str, expected: str) -> None:
    if not _is_sha256(expected) or actual != expected:
        raise InventoryError("{} digest changed".format(label))


def load_inventory(benchmarks: Path = DEFAULT_BENCHMARKS) -> Inventory:
    """Return the complete sorted, content-disjoint candidate inventory."""
    root = validate_benchmark_checkout(benchmarks)
    directories = _top_level_directories(root)
    all_paths = _enumerate_source_paths(root, directories)

    cost_ledger = _load_frozen_prior_records(
        COST_MANIFEST_PATH,
        COST_MANIFEST_SHA256,
        EXPECTED_COST_RECORDS,
        paths_required=True,
    )
    shadow_ledger = _load_frozen_prior_records(
        SHADOW_ATTESTATION_PATH,
        SHADOW_ATTESTATION_SHA256,
        EXPECTED_SHADOW_RECORDS,
        paths_required=False,
    )
    prior_identity_ledger = _attach_prior_source_paths(
        tuple(sorted(cost_ledger + shadow_ledger, key=lambda record: (
            record.directory,
            record.problem,
            record.problem_sha256,
            record.source_artifact,
        ))),
        all_paths,
    )
    prior_family_ledger = _build_prior_family_ledger(prior_identity_ledger)
    prior_identities = {
        TaskIdentity(record.directory, record.problem)
        for record in prior_identity_ledger
    }
    if (
        len(prior_identity_ledger) != EXPECTED_PRIOR_IDENTITIES
        or len(prior_identities) != EXPECTED_PRIOR_IDENTITIES
        or len(PRIOR_DIRECTORY_TO_FAMILY)
        != EXPECTED_PRIOR_DIRECTORY_FAMILIES
        or len(prior_family_ledger)
        != EXPECTED_PRIOR_FAMILY_LEDGER_RECORDS
        or len(ALL_PRIOR_FAMILIES) != EXPECTED_ALL_PRIOR_FAMILIES
    ):
        raise InventoryError("prior identity or family population changed")
    cost_hashes = {record.problem_sha256 for record in cost_ledger}
    shadow_hashes = {record.problem_sha256 for record in shadow_ledger}
    if (
        len(cost_hashes) != EXPECTED_COST_UNIQUE_PROBLEM_HASHES
        or len(shadow_hashes) != EXPECTED_SHADOW_UNIQUE_PROBLEM_HASHES
        or cost_hashes & shadow_hashes
    ):
        raise InventoryError("prior problem-hash population changed")
    prior_hashes = cost_hashes | shadow_hashes
    if len(prior_hashes) != EXPECTED_PRIOR_UNIQUE_PROBLEM_HASHES:
        raise InventoryError("prior problem-hash union changed")

    all_problem_hashes = {record.problem_sha256 for record in all_paths}
    if not prior_hashes <= all_problem_hashes:
        raise InventoryError("prior problem hash is absent from the universal scan")
    hash_filtered_paths = tuple(
        record for record in all_paths
        if record.problem_sha256 not in prior_hashes
    )
    name_overlap_after_hash_filter = len({
        TaskIdentity(record.directory, record.problem)
        for record in hash_filtered_paths
    } & prior_identities)
    if name_overlap_after_hash_filter != EXPECTED_NAME_OVERLAP_AFTER_HASH_FILTER:
        raise InventoryError("name overlap after problem-hash filtering changed")
    residue_paths = _exclude_prior_paths(
        all_paths, prior_identities, prior_hashes
    )
    residue_identities = tuple(sorted({
        TaskIdentity(record.directory, record.problem)
        for record in residue_paths
    }))
    prior_identity_overlap_count = len(
        set(residue_identities) & prior_identities
    )
    prior_problem_hash_overlap_count = len(
        {record.problem_sha256 for record in residue_paths} & prior_hashes
    )
    residue_directories = tuple(sorted({r.directory for r in residue_paths}))
    _validate_family_map(residue_directories)
    residue = tuple(Candidate(
        directory=record.directory,
        family=DIRECTORY_TO_FAMILY[record.directory],
        problem=record.problem,
        domain_file=record.domain_file,
        problem_file=record.problem_file,
        domain_sha256=record.domain_sha256,
        problem_sha256=record.problem_sha256,
    ) for record in residue_paths)
    candidates, alias_groups = _canonicalize(residue)
    residue_families = tuple(sorted({r.family for r in residue}))
    represented_shadow_families = tuple(sorted(
        set(residue_families) & set(SHADOW_FAMILIES)
    ))
    shadow_unrepresented_families = tuple(sorted(
        set(residue_families) - set(SHADOW_FAMILIES)
    ))
    represented_all_prior_families = tuple(sorted(
        set(residue_families) & set(ALL_PRIOR_FAMILIES)
    ))
    all_prior_unrepresented_families = tuple(sorted(
        set(residue_families) - set(ALL_PRIOR_FAMILIES)
    ))
    if all_prior_unrepresented_families != ALL_PRIOR_UNREPRESENTED_FAMILIES:
        raise InventoryError("all-prior-unrepresented family set changed")
    duplicate_groups = tuple(
        group for group in alias_groups if len(group.aliases) > 1
    )
    discarded_alias_count = sum(
        len(group.aliases) - 1 for group in alias_groups
    )

    counts = (
        (len(directories), EXPECTED_TOP_LEVEL_DIRECTORIES, "directories"),
        (len(all_paths), EXPECTED_ALL_PATHS, "source paths"),
        (
            len(all_problem_hashes),
            EXPECTED_ALL_UNIQUE_PROBLEM_HASHES,
            "unique source problems",
        ),
        (len(residue_paths), EXPECTED_RESIDUE_PATHS, "residue paths"),
        (
            len(residue_identities),
            EXPECTED_RESIDUE_IDENTITIES,
            "residue identities",
        ),
        (len(candidates), EXPECTED_CANDIDATES, "canonical candidates"),
        (
            len(residue_directories),
            EXPECTED_RESIDUE_DIRECTORIES,
            "residue directories",
        ),
        (
            len({r.directory for r in candidates}),
            EXPECTED_CANDIDATE_DIRECTORIES,
            "candidate directories",
        ),
        (len(residue_families), EXPECTED_FAMILIES, "families"),
        (
            len(represented_shadow_families),
            EXPECTED_REPRESENTED_SHADOW_FAMILIES,
            "represented shadow families",
        ),
        (
            len(shadow_unrepresented_families),
            EXPECTED_SHADOW_UNREPRESENTED_FAMILIES,
            "shadow-unrepresented families",
        ),
        (
            len(represented_all_prior_families),
            EXPECTED_REPRESENTED_ALL_PRIOR_FAMILIES,
            "represented all-prior families",
        ),
        (
            len(all_prior_unrepresented_families),
            EXPECTED_ALL_PRIOR_UNREPRESENTED_FAMILIES,
            "all-prior-unrepresented families",
        ),
        (
            len(duplicate_groups),
            EXPECTED_DUPLICATE_GROUPS,
            "duplicate groups",
        ),
        (
            discarded_alias_count,
            EXPECTED_DISCARDED_ALIASES,
            "discarded aliases",
        ),
        (
            prior_identity_overlap_count,
            EXPECTED_RESIDUE_PRIOR_IDENTITY_OVERLAP,
            "residue prior-identity overlap",
        ),
        (
            prior_problem_hash_overlap_count,
            EXPECTED_RESIDUE_PRIOR_PROBLEM_HASH_OVERLAP,
            "residue prior-hash overlap",
        ),
    )
    for actual, expected, label in counts:
        if actual != expected:
            raise InventoryError("{} count changed".format(label))

    digests = {
        "all_path_records": _digest(canonical_json(_records_json(all_paths))),
        "all_prior_families": _digest(canonical_json(
            list(ALL_PRIOR_FAMILIES)
        )),
        "all_prior_unrepresented_families": _digest(canonical_json(
            list(all_prior_unrepresented_families)
        )),
        "all_unique_problem_hashes": _digest(canonical_json(
            sorted(all_problem_hashes)
        )),
        "candidate_records": _digest(canonical_json(
            _records_json(candidates)
        )),
        "cost_problem_hashes": _digest(canonical_json(sorted(cost_hashes))),
        "directories": _digest(canonical_json(list(directories))),
        "alias_groups": _digest(canonical_json(
            _alias_json(alias_groups)
        )),
        "family_map": _digest(canonical_json(DIRECTORY_TO_FAMILY)),
        "prior_problem_hashes": _digest(canonical_json(sorted(prior_hashes))),
        "prior_identities": _digest(canonical_json(
            _records_json(sorted(prior_identities))
        )),
        "prior_identity_ledger": _digest(canonical_json(
            _records_json(prior_identity_ledger)
        )),
        "prior_directory_family_map": _digest(canonical_json(
            PRIOR_DIRECTORY_TO_FAMILY
        )),
        "prior_family_ledger": _digest(canonical_json(
            _records_json(prior_family_ledger)
        )),
        "represented_all_prior_families": _digest(canonical_json(
            list(represented_all_prior_families)
        )),
        "residue_identities": _digest(canonical_json(
            _records_json(residue_identities)
        )),
        "residue_path_records": _digest(canonical_json(
            _records_json(residue)
        )),
        "shadow_problem_hashes": _digest(canonical_json(
            sorted(shadow_hashes)
        )),
        "shadow_families": _digest(canonical_json(list(SHADOW_FAMILIES))),
        "shadow_unrepresented_families": _digest(canonical_json(
            list(shadow_unrepresented_families)
        )),
    }
    expected_digests = {
        "all_path_records": ALL_PATH_RECORDS_SHA256,
        "all_prior_families": ALL_PRIOR_FAMILY_SEQUENCE_SHA256,
        "all_prior_unrepresented_families":
            ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256,
        "all_unique_problem_hashes": ALL_UNIQUE_PROBLEM_HASHES_SHA256,
        "candidate_records": CANDIDATE_RECORDS_SHA256,
        "cost_problem_hashes": COST_PROBLEM_HASHES_SHA256,
        "directories": DIRECTORY_SEQUENCE_SHA256,
        "alias_groups": ALIAS_GROUPS_SHA256,
        "family_map": FAMILY_MAP_SHA256,
        "prior_problem_hashes": PRIOR_PROBLEM_HASHES_SHA256,
        "prior_identities": PRIOR_IDENTITIES_SHA256,
        "prior_identity_ledger": PRIOR_IDENTITY_LEDGER_SHA256,
        "prior_directory_family_map": PRIOR_DIRECTORY_FAMILY_MAP_SHA256,
        "prior_family_ledger": PRIOR_FAMILY_LEDGER_SHA256,
        "represented_all_prior_families":
            REPRESENTED_ALL_PRIOR_FAMILY_SEQUENCE_SHA256,
        "residue_identities": RESIDUE_IDENTITIES_SHA256,
        "residue_path_records": RESIDUE_PATH_RECORDS_SHA256,
        "shadow_problem_hashes": SHADOW_PROBLEM_HASHES_SHA256,
        "shadow_families": SHADOW_FAMILY_SEQUENCE_SHA256,
        "shadow_unrepresented_families":
            SHADOW_UNREPRESENTED_FAMILY_SEQUENCE_SHA256,
    }
    for label, actual in digests.items():
        _require_digest(label, actual, expected_digests[label])

    return Inventory(
        directories=directories,
        residue_directories=residue_directories,
        residue_families=residue_families,
        represented_shadow_families=represented_shadow_families,
        shadow_unrepresented_families=shadow_unrepresented_families,
        represented_all_prior_families=represented_all_prior_families,
        all_prior_unrepresented_families=all_prior_unrepresented_families,
        candidates=candidates,
        alias_groups=alias_groups,
        prior_identity_ledger=prior_identity_ledger,
        prior_family_ledger=prior_family_ledger,
        residue_identities=residue_identities,
        all_path_count=len(all_paths),
        all_unique_problem_hash_count=len(all_problem_hashes),
        residue_path_count=len(residue_paths),
        discarded_alias_count=discarded_alias_count,
        name_overlap_after_hash_filter_count=name_overlap_after_hash_filter,
        prior_identity_overlap_count=prior_identity_overlap_count,
        prior_problem_hash_overlap_count=prior_problem_hash_overlap_count,
        digests=tuple(sorted(digests.items())),
    )


def load_candidates(benchmarks: Path = DEFAULT_BENCHMARKS) -> tuple[Candidate, ...]:
    return load_inventory(benchmarks).candidates
