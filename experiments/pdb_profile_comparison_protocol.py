#!/usr/bin/env python3
"""Frozen design for the cofactor-profile and selector-budget comparison.

The default cohort is the complete 1,327-task development complement from the
focused cap-grid census.  The previous 575-task triple-solved cohort, including
its 393 finite-cap tasks, remains a predeclared diagnostic stratum rather than
an outcome filter for this experiment.
"""

from __future__ import annotations

import hashlib
import json
import re
import stat
import tarfile
from dataclasses import dataclass
from pathlib import Path


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
PROFILE_LOG = "wbh-profile.jsonl"
LEGACY_LOG = "wbh.jsonl"
WIDTH_BUDGETS = (2, 4, 8, 16, 32)
# Nearest acceptance-matched total ADD-node budgets U=A+T on the frozen
# 50-task K=32 cap-grid candidate census below.  The first three matches are
# deliberately near rather than exact; their acceptance-count deltas are
# +1, +2, and +3 candidates.
TOTAL_ADD_NODE_BUDGETS = (8, 29, 55, 100, 204)
MATCHED_BUDGETS = tuple(zip(WIDTH_BUDGETS, TOTAL_ADD_NODE_BUDGETS))
MATCH_WIDTH_ACCEPTED = (227, 371, 525, 655, 783)
MATCH_ADD_ACCEPTED = (228, 373, 528, 655, 783)
MATCH_ACCEPTANCE_DELTAS = (1, 2, 3, 0, 0)
MATCH_CANDIDATES = 946

MATCH_ARCHIVE_DEFAULT = Path(
    "/nobackup/proj/disk/dfsplan/personal/jendrik/"
    "symk-pdb-cap-grid-launch/experiments/data/"
    "exp_pdb_cap_grid_pilot-eval.tar.gz"
)
MATCH_ARCHIVE_SHA256 = (
    "6124f186ba66a4f9e0d2411b2ef15ee8fc4b0b87af8281345b66e05e57b14d3d"
)
MATCH_ARCHIVE_MEMBER = "exp_pdb_cap_grid_pilot-eval/properties"

COHORT_ARCHIVE_DEFAULT = Path(
    "/nobackup/proj/disk/dfsplan/personal/jendrik/"
    "symk-pdb-cap-grid-full-protocol/experiments/data/"
    "exp_pdb_cap_grid_full-eval.tar.gz"
)
COHORT_ARCHIVE_SHA256 = (
    "f2bf90dbc2e06ea109b221bb1de250bd7560776faf9d42f4955da8fef961e12d"
)
COHORT_ARCHIVE_MEMBER = "exp_pdb_cap_grid_full-eval/properties"
COHORT_MANIFEST_SHA256 = (
    "1e126791b438d903cb6adcc441391b92d76a7e14cf46f6a89465a066823a986f"
)
COHORT_TASKS = 1327
COHORT_DOMAINS = 46
LEGACY_TRIPLE_SOLVED_TASKS = 575
LEGACY_FINITE_CAP_TASKS = 393
LEGACY_EXACT_ENDPOINT_TASKS = 182
PRIMARY_OTHER_TASKS = 752
CONFIG_COUNT = 18
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT

PROTOCOL = "pdb-cofactor-profile-comparison-v1"
ANALYSIS_PROTOCOL = "pdb-cofactor-profile-comparison-analysis-v1"
COHORT_ROLE = "prospective-full-development-complement"
INFERENCE_POLICY = "descriptive-fixed-cohort-no-population-inference-v1"
ADD_MATCH_ROLE = (
    "development-screen-nearest-acceptance-matched-A-plus-T-control;"
    "not-a-causal-isolation-of-cofactor-width/v1"
)
REQUIRED_LAB_VERSION = "8.0"
BUILD_OPTIONS = ("release_no_lp",)
TIME_LIMIT_SECONDS = 300
MEMORY_LIMIT_MIB = 8192


def _pdb(extra: str) -> str:
    return (
        "sym_fw_pdb(budget=100000,pattern_selection=exact_width_filter,"
        "cegar_max_time=10,cegar_seed=2011,{},"
        'wbh_log="{}",wbh_profile_log="{}")'.format(
            extra, LEGACY_LOG, PROFILE_LOG
        )
    )


CONFIGS = (
    ("blind_fw", 'sym_fw(wbh_log="{}")'.format(LEGACY_LOG)),
    (
        "blind_fw_profiled",
        'sym_fw(wbh_log="{}",wbh_profile_log="{}")'.format(
            LEGACY_LOG, PROFILE_LOG
        ),
    ),
    *tuple(
        ("pdb_exact_k{}".format(k), _pdb("cofactor_width_budget={}".format(k)))
        for k in WIDTH_BUDGETS
    ),
    *tuple(
        (
            "pdb_cap_width_k{}".format(k),
            _pdb(
                "cofactor_width_budget={},select_value_cap=true".format(k)
            ),
        )
        for k in WIDTH_BUDGETS
    ),
    *tuple(
        (
            "pdb_cap_add_u{}".format(u),
            _pdb(
                "total_add_node_budget={},select_value_cap=true".format(u)
            ),
        )
        for u in TOTAL_ADD_NODE_BUDGETS
    ),
    (
        "pdb_exact_unconstrained",
        _pdb("cofactor_width_budget=infinity"),
    ),
)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
OPTION_MATRIX_SHA256 = (
    "9fc96991fe60a9968f4938662419446bc34002f4a4520cb8a93605fa23efcb6f"
)


@dataclass(frozen=True, order=True)
class CohortTask:
    domain: str
    problem: str
    stratum: str


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
        raise ProtocolError("value is not canonical finite JSON: {}".format(err))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def option_matrix_digest(configs=CONFIGS) -> str:
    payload = [
        {"label": label, "search": search} for label, search in configs
    ]
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def validate_config_matrix(configs=CONFIGS) -> None:
    if len(configs) != CONFIG_COUNT:
        raise ProtocolError("matrix must contain exactly 18 configurations")
    labels = [label for label, _ in configs]
    searches = [search for _, search in configs]
    if len(labels) != len(set(labels)) or len(searches) != len(set(searches)):
        raise ProtocolError("configuration labels and searches must be unique")
    if any(re.fullmatch(r"[a-z][a-z0-9_]*", label) is None for label in labels):
        raise ProtocolError("configuration label is not canonical")
    if option_matrix_digest(configs) != OPTION_MATRIX_SHA256:
        raise ProtocolError("option matrix digest changed")
    for k, u in MATCHED_BUDGETS:
        required = {
            "pdb_exact_k{}".format(k),
            "pdb_cap_width_k{}".format(k),
            "pdb_cap_add_u{}".format(u),
        }
        if not required.issubset(labels):
            raise ProtocolError("matched K/U triplet is incomplete")
    for label, search in configs:
        finite_width = re.search(r"cofactor_width_budget=([0-9]+)", search)
        finite_add = re.search(r"total_add_node_budget=([0-9]+)", search)
        if finite_width and finite_add:
            raise ProtocolError("{} sets both finite selector budgets".format(label))
        should_profile = label != "blind_fw"
        if ("wbh_profile_log=" in search) != should_profile:
            raise ProtocolError("{} has the wrong profiling mode".format(label))
        if search.count('wbh_log="{}"'.format(LEGACY_LOG)) != 1:
            raise ProtocolError("{} must emit exactly one schema-v2 stream".format(label))


def _regular_file(path: Path, maximum_bytes: int | None = None) -> None:
    try:
        info = Path(path).lstat()
    except OSError as err:
        raise ProtocolError("cannot inspect {}: {}".format(path, err)) from err
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ProtocolError("{} must be a regular non-symlink file".format(path))
    if maximum_bytes is not None and info.st_size > maximum_bytes:
        raise ProtocolError("{} exceeds its size limit".format(path))


def _certified_cohort(properties: dict) -> list[CohortTask]:
    # Reuse the independently pinned post-hoc validator. It checks every old
    # matrix cell, trace, fixed identity, and source-population digest before
    # this protocol derives the full development complement and labels the
    # explicitly outcome-conditioned legacy diagnostic strata within it.
    import analyze_pdb_cap_grid_posthoc_review as old

    records = []
    for source, record in properties.items():
        if not isinstance(source, str) or not isinstance(record, dict):
            raise ProtocolError("preserved properties have an invalid record")
        copied = dict(record)
        copied["_source_key"] = source
        records.append(copied)
    try:
        matrix, _, primary, _ = old.validate_records(records)
        pairs = old._paired_traces(matrix, primary)
    except old.AnalysisError as err:
        raise ProtocolError("old cohort source failed validation: {}".format(err))

    legacy_strata = {}
    for pair in pairs:
        task = pair["task"]
        cells = {
            "blind": matrix[(old.BLIND, task)],
            "exact": pair["exact"],
            "cap": pair["cap"],
        }
        if not all(cell.get("coverage") == 1 for cell in cells.values()):
            continue
        try:
            certified = {
                name: old._certified_solved_effort(
                    cell, "{}:{} {}".format(*task, name)
                )
                for name, cell in cells.items()
            }
        except old.AnalysisError as err:
            raise ProtocolError("old cohort cell failed validation: {}".format(err))
        if len({item["cost"] for item in certified.values()}) != 1:
            raise ProtocolError("old cohort has a cost-disagreeing task")
        legacy_strata[task] = "legacy_triple_{}".format(pair["endpoint"])
    return [
        CohortTask(
            domain,
            problem,
            legacy_strata.get((domain, problem), "primary_other"),
        )
        for domain, problem in primary
    ]


def load_cohort(archive=COHORT_ARCHIVE_DEFAULT) -> tuple[CohortTask, ...]:
    archive = Path(archive)
    _regular_file(archive, 64 * 1024 * 1024)
    if sha256_file(archive) != COHORT_ARCHIVE_SHA256:
        raise ProtocolError("preserved cohort archive digest changed")
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            members = {member.name: member for member in bundle.getmembers()}
            member = members.get(COHORT_ARCHIVE_MEMBER)
            if member is None or not member.isfile() or member.size > 512 * 1024 * 1024:
                raise ProtocolError("cohort properties member is missing or invalid")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ProtocolError("cannot read cohort properties member")
            properties = json.load(stream)
    except (OSError, tarfile.TarError, json.JSONDecodeError) as err:
        raise ProtocolError("cannot load cohort archive: {}".format(err)) from err
    if not isinstance(properties, dict):
        raise ProtocolError("cohort properties must be an object")
    cohort = tuple(_certified_cohort(properties))
    manifest = "".join(
        "{}:{}\n".format(task.domain, task.problem) for task in cohort
    ).encode("utf-8")
    digest = hashlib.sha256(manifest).hexdigest()
    counts = {
        "tasks": len(cohort),
        "domains": len({task.domain for task in cohort}),
        "legacy_triple_finite_cap": sum(
            task.stratum == "legacy_triple_finite_cap" for task in cohort
        ),
        "legacy_triple_exact_endpoint": sum(
            task.stratum == "legacy_triple_exact_endpoint" for task in cohort
        ),
        "primary_other": sum(task.stratum == "primary_other" for task in cohort),
    }
    expected = {
        "tasks": COHORT_TASKS,
        "domains": COHORT_DOMAINS,
        "legacy_triple_finite_cap": LEGACY_FINITE_CAP_TASKS,
        "legacy_triple_exact_endpoint": LEGACY_EXACT_ENDPOINT_TASKS,
        "primary_other": PRIMARY_OTHER_TASKS,
    }
    if digest != COHORT_MANIFEST_SHA256 or counts != expected:
        raise ProtocolError(
            "derived cohort changed: digest {}, counts {}".format(digest, counts)
        )
    return cohort


def validate_matched_budget_provenance(archive=MATCH_ARCHIVE_DEFAULT) -> None:
    """Re-derive the K/U acceptance counts from the pinned 50-task screen."""
    archive = Path(archive)
    _regular_file(archive, 16 * 1024 * 1024)
    if sha256_file(archive) != MATCH_ARCHIVE_SHA256:
        raise ProtocolError("matched-budget archive digest changed")
    try:
        with tarfile.open(archive, "r:gz") as bundle:
            members = {member.name: member for member in bundle.getmembers()}
            member = members.get(MATCH_ARCHIVE_MEMBER)
            if member is None or not member.isfile() or member.size > 64 * 1024 * 1024:
                raise ProtocolError("matched-budget properties member is invalid")
            stream = bundle.extractfile(member)
            if stream is None:
                raise ProtocolError("cannot read matched-budget properties")
            properties = json.load(stream)
    except (OSError, tarfile.TarError, json.JSONDecodeError) as err:
        raise ProtocolError(
            "cannot load matched-budget archive: {}".format(err)
        ) from err
    if not isinstance(properties, dict):
        raise ProtocolError("matched-budget properties must be an object")
    records = [
        record
        for record in properties.values()
        if isinstance(record, dict) and record.get("algorithm") == "pdb_cap_grid_k32"
    ]
    if len(records) != 50 or any(
        record.get("pdb_selector_trace_certified") is not True
        or not isinstance(record.get("pdb_selector_candidates"), list)
        for record in records
    ):
        raise ProtocolError("matched-budget source lacks 50 certified traces")
    candidates = [
        candidate
        for record in records
        for candidate in record["pdb_selector_candidates"]
    ]
    if len(candidates) != MATCH_CANDIDATES or any(
        not isinstance(candidate, dict)
        or type(candidate.get("cofactor_width")) is not int
        or type(candidate.get("width_upper_bound")) is not int
        for candidate in candidates
    ):
        raise ProtocolError("matched-budget candidate census changed")
    width_counts = tuple(
        sum(candidate["cofactor_width"] <= budget for candidate in candidates)
        for budget in WIDTH_BUDGETS
    )
    add_counts = tuple(
        sum(candidate["width_upper_bound"] <= budget for candidate in candidates)
        for budget in TOTAL_ADD_NODE_BUDGETS
    )
    deltas = tuple(
        add - width for width, add in zip(width_counts, add_counts)
    )
    if (
        width_counts != MATCH_WIDTH_ACCEPTED
        or add_counts != MATCH_ADD_ACCEPTED
        or deltas != MATCH_ACCEPTANCE_DELTAS
    ):
        raise ProtocolError(
            "matched-budget acceptance counts changed: {}, {}, {}".format(
                width_counts, add_counts, deltas
            )
        )


def validate_protocol_without_archive() -> None:
    validate_config_matrix()
    if not WIDTH_BUDGETS or len(WIDTH_BUDGETS) != len(TOTAL_ADD_NODE_BUDGETS):
        raise ProtocolError("matched budget lists have different lengths")
    if CELL_COUNT != 23886:
        raise ProtocolError("cell-count identity changed")
    if tuple(
        add - width
        for width, add in zip(MATCH_WIDTH_ACCEPTED, MATCH_ADD_ACCEPTED)
    ) != MATCH_ACCEPTANCE_DELTAS:
        raise ProtocolError("matched-budget acceptance deltas changed")


validate_protocol_without_archive()
