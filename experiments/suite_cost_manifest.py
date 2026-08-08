"""Load and validate suite_wbh's frozen cost/support classification.

The manifest uses direct Fast Downward SAS v3 scans for 1684 tasks and a
pinned-translator no-metric/unit-cost proof for 13 resource-heavy task
translations.
Both methods establish the same serialized-SAS zero-cost predicate.  A second,
independent attestation records whether the pinned translator's default PDDL
normalization introduces axioms.  SymK's fair supported subset is therefore
positive-cost *and* free of normalized axioms.  This module intentionally has
no Lab dependency so result post-processing can use the classification from a
source checkout with only the Python standard library installed.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Set, Tuple


SCHEMA_VERSION = 2
EXPECTED_TASKS = 1697
EXPECTED_POSITIVE_COST = 1407
EXPECTED_ZERO_COST = 290
EXPECTED_SAS_V3_SCAN = 1684
EXPECTED_PDDL_UNIT_COST_PROOF = 13
EXPECTED_WITH_NORMALIZED_AXIOMS = 30
EXPECTED_POSITIVE_WITH_NORMALIZED_AXIOMS = 30
EXPECTED_ZERO_WITH_NORMALIZED_AXIOMS = 0
EXPECTED_SUPPORTED_POSITIVE_AXIOM_FREE = 1377
EXPECTED_FULLY_SUPPORTED_DOMAINS = 46
EXPECTED_DOMAINS_WITH_AT_LEAST_TWO_SUPPORTED = 46
EXPECTED_TRANSLATOR_REVISION = "ec8399257de93e0739046a187af4bed0b85e19ce"
EXPECTED_TRANSLATOR_SOURCE_SHA256 = (
    "c93a014324c4866cc9f83c456d75fc2ad9d4b397bae48411bdc0c757e2f88cbc")
EXPECTED_BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
EXPECTED_BENCHMARK_REPOSITORY = (
    "https://github.com/aibasel/downward-benchmarks.git")
EXPECTED_CRITERION = (
    "zero-cost iff the Fast Downward SAS v3 output contains at least one "
    "serialized operator with integer cost 0; positive-cost otherwise. "
    "Evidence is either a direct SAS v3 scan or, for the pinned resource-heavy "
    "tasks, a parser-confirmed no-metric proof that the pinned translator "
    "assigns and preserves unit cost for every serialized operator"
)
EXPECTED_SUPPORT_CRITERION = (
    "supported iff the task is positive-cost and parsing its exact PDDL bytes "
    "followed by the pinned translator's default axiom_based normalization "
    "produces zero normalized PDDL axioms"
)
EXPECTED_CLASSIFICATION_METHODS = {
    "sas_v3_scan": (
        "parse every serialized operator cost from Fast Downward SAS v3"),
    "pddl_no_metric_unit_cost_proof": (
        "parse the task with the pinned Fast Downward PDDL parser, require "
        "use_min_cost_metric=false, and attest the pinned source path from "
        "Action.instantiate's cost=1 branch through SAS serialization"),
}
EXPECTED_PROOF_SOURCE_PATHS = [
    "src/translate/pddl/actions.py",
    "src/translate/pddl/tasks.py",
    "src/translate/pddl_parser/pddl_file.py",
    "src/translate/pddl_parser/parsing_functions.py",
    "src/translate/instantiate.py",
    "src/translate/main.py",
    "src/translate/sas_tasks.py",
    "src/translate/simplify.py",
]
EXPECTED_PROOF_SOURCE_SHA256 = (
    "8b4b13994dab0f63599831e7665817daccf687d854da5e4fa45c0f5961e18341")
EXPECTED_PROOF_TASKS = [
    ["organic-synthesis-opt18-strips", "p04.pddl"],
    ["organic-synthesis-opt18-strips", "p05.pddl"],
    ["organic-synthesis-opt18-strips", "p06.pddl"],
    ["organic-synthesis-opt18-strips", "p08.pddl"],
    ["organic-synthesis-opt18-strips", "p11.pddl"],
    ["organic-synthesis-opt18-strips", "p12.pddl"],
    ["organic-synthesis-opt18-strips", "p13.pddl"],
    ["organic-synthesis-opt18-strips", "p15.pddl"],
    ["organic-synthesis-opt18-strips", "p16.pddl"],
    ["organic-synthesis-opt18-strips", "p17.pddl"],
    ["organic-synthesis-opt18-strips", "p18.pddl"],
    ["organic-synthesis-opt18-strips", "p19.pddl"],
    ["organic-synthesis-opt18-strips", "p20.pddl"],
]
EXPECTED_NORMALIZATION_STRATEGY = "axiom_based"
EXPECTED_NORMALIZED_AXIOM_SOURCE_PATHS = [
    "src/translate/normalize.py",
    "src/translate/options.py",
    "src/translate/pddl/tasks.py",
    "src/translate/pddl_parser/pddl_file.py",
    "src/translate/pddl_parser/parsing_functions.py",
]
EXPECTED_NORMALIZED_AXIOM_SOURCE_SHA256 = (
    "1a38a16674ac62e79d80bf4fecdf0bb0e4d4fcdf9284f64de7d4248d2f027397")
EXPECTED_NORMALIZED_AXIOM_TASKS = [
    ["pathways", f"p{index:02d}.pddl"] for index in range(1, 31)
]
EXPECTED_SUITE_DOMAINS_SHA256 = (
    "cdcea275a76ae21f03f80888d45864aac210d8cfb81ebf048642c95b73804d78")
# These are checked independently of the adjacent, human-readable checksum
# sidecar, so coordinated edits to the JSON and sidecar still fail closed.
EXPECTED_MANIFEST_SHA256 = (
    "7b4f5934752f41792e3debd0a269286d28d7ee9f1242b87a4bc92b7066822168")
EXPECTED_RECORDS_SHA256 = (
    "05bdaf95048a60fc3e9532ec521a3d8c3dd3ffea03741716a482ce9e9827567e")
MANIFEST_PATH = Path(__file__).with_name("suite_wbh_operator_costs.json")
CHECKSUM_PATH = MANIFEST_PATH.with_suffix(MANIFEST_PATH.suffix + ".sha256")

TaskKey = Tuple[str, str]


def _is_sha256(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and not any(
        char not in "0123456789abcdef" for char in value)


def _validate_provenance(value: object) -> None:
    required = {
        "translator_revision", "translator_source_sha256",
        "translator_command", "translator_options", "sas_version",
        "benchmark_revision", "benchmark_repository", "suite_module",
        "suite_domains", "suite_domains_sha256", "suite_task_order",
        "classification_criterion", "classification_methods",
        "pddl_unit_cost_proof_source_paths",
        "pddl_unit_cost_proof_source_sha256", "pddl_unit_cost_proof_tasks",
        "support_criterion", "normalization_strategy",
        "normalized_axiom_source_paths", "normalized_axiom_source_sha256",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise RuntimeError("manifest has unexpected provenance fields")
    fixed = {
        "translator_revision": EXPECTED_TRANSLATOR_REVISION,
        "translator_source_sha256": EXPECTED_TRANSLATOR_SOURCE_SHA256,
        "translator_command": "python -m translate DOMAIN PROBLEM",
        "translator_options": [],
        "sas_version": 3,
        "benchmark_revision": EXPECTED_BENCHMARK_REVISION,
        "benchmark_repository": EXPECTED_BENCHMARK_REPOSITORY,
        "suite_module": "experiments/suite_wbh.py",
        "suite_task_order": "lexicographic (domain, problem)",
        "classification_criterion": EXPECTED_CRITERION,
        "classification_methods": EXPECTED_CLASSIFICATION_METHODS,
        "pddl_unit_cost_proof_source_paths": EXPECTED_PROOF_SOURCE_PATHS,
        "pddl_unit_cost_proof_source_sha256": EXPECTED_PROOF_SOURCE_SHA256,
        "pddl_unit_cost_proof_tasks": EXPECTED_PROOF_TASKS,
        "support_criterion": EXPECTED_SUPPORT_CRITERION,
        "normalization_strategy": EXPECTED_NORMALIZATION_STRATEGY,
        "normalized_axiom_source_paths": EXPECTED_NORMALIZED_AXIOM_SOURCE_PATHS,
        "normalized_axiom_source_sha256":
            EXPECTED_NORMALIZED_AXIOM_SOURCE_SHA256,
    }
    for field, expected in fixed.items():
        if value.get(field) != expected:
            raise RuntimeError(
                f"unexpected manifest provenance {field}: "
                f"{value.get(field)!r}")
    domains = value.get("suite_domains")
    if not isinstance(domains, list) or not domains or not all(
            isinstance(domain, str) for domain in domains):
        raise RuntimeError("invalid suite domain list in manifest provenance")
    domain_hash = hashlib.sha256(
        "".join(f"{domain}\n" for domain in domains).encode("utf-8")).hexdigest()
    if domain_hash != EXPECTED_SUITE_DOMAINS_SHA256 or \
            value.get("suite_domains_sha256") != domain_hash:
        raise RuntimeError("suite domain-list hash mismatch")


def canonical_records_bytes(records: Iterable[Mapping[str, object]]) -> bytes:
    """Return the canonical byte representation hashed by the manifest."""
    return json.dumps(
        list(records), sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("ascii")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_checksum(checksum_path: Path, manifest_path: Path) -> str:
    try:
        fields = checksum_path.read_text(encoding="ascii").strip().split()
    except OSError as err:
        raise RuntimeError(
            f"cannot read manifest checksum {checksum_path}: {err}") from err
    if len(fields) != 2 or fields[1] != manifest_path.name:
        raise RuntimeError(
            f"malformed checksum file {checksum_path}; expected "
            f"'<sha256>  {manifest_path.name}'")
    expected = fields[0]
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise RuntimeError(f"invalid SHA-256 in {checksum_path}")
    return expected


def load_manifest(
    path: Path = MANIFEST_PATH,
    *,
    checksum_path: Optional[Path] = None,
    verify_file_checksum: bool = True,
) -> Dict[str, object]:
    """Load the frozen manifest and fail closed on any inconsistency."""
    path = Path(path)
    actual_file_hash = sha256_file(path)
    if actual_file_hash != EXPECTED_MANIFEST_SHA256:
        raise RuntimeError(
            f"manifest bytes do not match the frozen SHA-256 for {path}: "
            f"expected {EXPECTED_MANIFEST_SHA256}, got {actual_file_hash}")
    if checksum_path is None:
        checksum_path = path.with_suffix(path.suffix + ".sha256")
    if verify_file_checksum:
        expected_file_hash = _read_checksum(checksum_path, path)
        if actual_file_hash != expected_file_hash:
            raise RuntimeError(
                f"manifest checksum mismatch for {path}: expected "
                f"{expected_file_hash}, got {actual_file_hash}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise RuntimeError(f"cannot load operator-cost manifest {path}: {err}") from err
    if not isinstance(data, dict):
        raise RuntimeError(f"manifest {path} is not a JSON object")
    expected_top_level = {
        "schema_version", "provenance", "counts", "records_sha256", "tasks"}
    if set(data) != expected_top_level:
        raise RuntimeError("manifest has unexpected top-level fields")
    if data.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(
            f"unsupported manifest schema {data.get('schema_version')!r}")
    _validate_provenance(data.get("provenance"))

    records = data.get("tasks")
    if not isinstance(records, list):
        raise RuntimeError("manifest tasks must be a list")
    expected_records_hash = data.get("records_sha256")
    actual_records_hash = hashlib.sha256(
        canonical_records_bytes(records)).hexdigest()
    if expected_records_hash != EXPECTED_RECORDS_SHA256 or \
            actual_records_hash != EXPECTED_RECORDS_SHA256:
        raise RuntimeError(
            "manifest record hash mismatch: declared "
            f"{expected_records_hash}, frozen {EXPECTED_RECORDS_SHA256}, "
            f"actual {actual_records_hash}")

    keys: List[TaskKey] = []
    positive = 0
    zero = 0
    with_axioms = 0
    positive_with_axioms = 0
    zero_with_axioms = 0
    supported = 0
    required = {
        "domain", "problem", "domain_file", "problem_file",
        "domain_sha256", "problem_sha256", "num_operators",
        "num_zero_cost_operators", "min_operator_cost", "cost_class",
        "classification_method", "num_normalized_axioms",
    }
    for index, record in enumerate(records):
        if not isinstance(record, dict) or set(record) != required:
            raise RuntimeError(
                f"manifest task {index} has unexpected fields: "
                f"{sorted(record) if isinstance(record, dict) else type(record)}")
        domain = record["domain"]
        problem = record["problem"]
        if not isinstance(domain, str) or not isinstance(problem, str):
            raise RuntimeError(f"manifest task {index} has a non-string key")
        key = (domain, problem)
        keys.append(key)
        for field in ("domain_file", "problem_file"):
            source = record[field]
            if not isinstance(source, str):
                raise RuntimeError(f"manifest task {key} has non-string {field}")
            source_path = Path(source)
            if source_path.is_absolute() or ".." in source_path.parts:
                raise RuntimeError(
                    f"manifest task {key} has unsafe relative path {source!r}")
        for field in ("domain_sha256", "problem_sha256"):
            digest = record[field]
            if not _is_sha256(digest):
                raise RuntimeError(f"manifest task {key} has invalid {field}")
        num_operators = record["num_operators"]
        num_zero = record["num_zero_cost_operators"]
        min_cost = record["min_operator_cost"]
        cost_class = record["cost_class"]
        method = record["classification_method"]
        num_normalized_axioms = record["num_normalized_axioms"]
        if type(num_normalized_axioms) is not int or \
                num_normalized_axioms < 0:
            raise RuntimeError(f"invalid normalized-axiom count for {key}")
        expected_proof_keys = {tuple(task) for task in EXPECTED_PROOF_TASKS}
        if method == "sas_v3_scan":
            if key in expected_proof_keys:
                raise RuntimeError(f"task {key} must use the pinned proof method")
            if type(num_operators) is not int or num_operators < 0:
                raise RuntimeError(f"invalid operator count for {key}")
            if type(num_zero) is not int or not 0 <= num_zero <= num_operators:
                raise RuntimeError(f"invalid zero-cost operator count for {key}")
            if min_cost is not None and (
                    type(min_cost) is not int or min_cost < 0):
                raise RuntimeError(f"invalid minimum operator cost for {key}")
            if num_operators == 0 and min_cost is not None:
                raise RuntimeError(f"empty task {key} has a minimum operator cost")
            if num_operators > 0 and min_cost is None:
                raise RuntimeError(f"nonempty task {key} lacks a minimum operator cost")
            derived_class = "zero-cost" if num_zero else "positive-cost"
            if cost_class != derived_class:
                raise RuntimeError(
                    f"cost class disagrees with SAS operator counts for {key}")
            if (min_cost == 0) != bool(num_zero):
                raise RuntimeError(
                    f"minimum cost disagrees with zero-cost count for {key}")
        elif method == "pddl_no_metric_unit_cost_proof":
            if key not in expected_proof_keys:
                raise RuntimeError(f"unapproved proof-method task {key}")
            if (num_operators, num_zero, min_cost, cost_class) != (
                    None, 0, None, "positive-cost"):
                raise RuntimeError(f"invalid unit-cost proof record for {key}")
        else:
            raise RuntimeError(f"unknown classification method for {key}: {method!r}")
        if cost_class == "zero-cost":
            zero += 1
        else:
            positive += 1
        if num_normalized_axioms:
            with_axioms += 1
            if cost_class == "zero-cost":
                zero_with_axioms += 1
            else:
                positive_with_axioms += 1
        elif cost_class == "positive-cost":
            supported += 1

    if keys != sorted(keys):
        raise RuntimeError("manifest tasks are not sorted by (domain, problem)")
    if len(set(keys)) != len(keys):
        raise RuntimeError("manifest contains duplicate task keys")
    observed_axiom_keys = {
        (record["domain"], record["problem"])
        for record in records if record["num_normalized_axioms"]}
    expected_axiom_keys = {
        tuple(task) for task in EXPECTED_NORMALIZED_AXIOM_TASKS}
    if observed_axiom_keys != expected_axiom_keys:
        missing = sorted(expected_axiom_keys - observed_axiom_keys)
        extra = sorted(observed_axiom_keys - expected_axiom_keys)
        raise RuntimeError(
            "normalized-axiom task set mismatch: "
            f"{len(missing)} missing, {len(extra)} extra")
    observed = (
        len(keys), positive, zero, with_axioms, positive_with_axioms,
        zero_with_axioms, supported)
    expected = (
        EXPECTED_TASKS, EXPECTED_POSITIVE_COST, EXPECTED_ZERO_COST,
        EXPECTED_WITH_NORMALIZED_AXIOMS,
        EXPECTED_POSITIVE_WITH_NORMALIZED_AXIOMS,
        EXPECTED_ZERO_WITH_NORMALIZED_AXIOMS,
        EXPECTED_SUPPORTED_POSITIVE_AXIOM_FREE)
    if observed != expected:
        raise RuntimeError(
            f"unexpected manifest totals {observed}; expected {expected}")
    declared = data.get("counts")
    expected_declared = {
        "tasks": EXPECTED_TASKS,
        "positive_cost": EXPECTED_POSITIVE_COST,
        "zero_cost": EXPECTED_ZERO_COST,
        "sas_v3_scan": EXPECTED_SAS_V3_SCAN,
        "pddl_no_metric_unit_cost_proof": EXPECTED_PDDL_UNIT_COST_PROOF,
        "with_normalized_axioms": EXPECTED_WITH_NORMALIZED_AXIOMS,
        "positive_cost_with_normalized_axioms":
            EXPECTED_POSITIVE_WITH_NORMALIZED_AXIOMS,
        "zero_cost_with_normalized_axioms":
            EXPECTED_ZERO_WITH_NORMALIZED_AXIOMS,
        "supported_positive_axiom_free":
            EXPECTED_SUPPORTED_POSITIVE_AXIOM_FREE,
    }
    if declared != expected_declared:
        raise RuntimeError(
            f"manifest counts {declared!r} do not match {expected_declared!r}")
    return data


def task_classes(
    path: Path = MANIFEST_PATH,
) -> Tuple[Set[TaskKey], Set[TaskKey]]:
    """Return the disjoint positive- and zero-cost task sets."""
    data = load_manifest(path)
    positive: Set[TaskKey] = set()
    zero: Set[TaskKey] = set()
    for record in data["tasks"]:  # type: ignore[index]
        key = (record["domain"], record["problem"])
        (zero if record["cost_class"] == "zero-cost" else positive).add(key)
    return positive, zero


def supported_tasks(path: Path = MANIFEST_PATH) -> Set[TaskKey]:
    """Return positive-cost tasks supported by the axiom-free SymK protocol."""
    data = load_manifest(path)
    return {
        (record["domain"], record["problem"])
        for record in data["tasks"]  # type: ignore[index]
        if record["cost_class"] == "positive-cost"
        and record["num_normalized_axioms"] == 0
    }


def fully_supported_domains(path: Path = MANIFEST_PATH) -> Set[str]:
    """Return domains for which every suite task is in ``supported_tasks``."""
    data = load_manifest(path)
    support_by_domain: Dict[str, List[bool]] = {}
    for record in data["tasks"]:  # type: ignore[index]
        support_by_domain.setdefault(record["domain"], []).append(
            record["cost_class"] == "positive-cost"
            and record["num_normalized_axioms"] == 0)
    domains = {
        domain for domain, flags in support_by_domain.items() if all(flags)}
    if len(domains) != EXPECTED_FULLY_SUPPORTED_DOMAINS:
        raise RuntimeError(
            f"manifest has {len(domains)} fully supported domains; expected "
            f"{EXPECTED_FULLY_SUPPORTED_DOMAINS}")
    return domains


def domains_with_min_supported_tasks(
    min_tasks: int,
    path: Path = MANIFEST_PATH,
) -> Set[str]:
    """Return domains containing at least ``min_tasks`` supported tasks."""
    if type(min_tasks) is not int or min_tasks <= 0:
        raise RuntimeError("min_tasks must be a positive integer")
    data = load_manifest(path)
    counts: Dict[str, int] = {}
    for record in data["tasks"]:  # type: ignore[index]
        if record["cost_class"] == "positive-cost" and \
                record["num_normalized_axioms"] == 0:
            domain = record["domain"]
            counts[domain] = counts.get(domain, 0) + 1
    domains = {
        domain for domain, count in counts.items() if count >= min_tasks}
    if min_tasks == 2 and \
            len(domains) != EXPECTED_DOMAINS_WITH_AT_LEAST_TWO_SUPPORTED:
        raise RuntimeError(
            f"manifest has {len(domains)} domains with at least two supported "
            f"tasks; expected {EXPECTED_DOMAINS_WITH_AT_LEAST_TWO_SUPPORTED}")
    return domains


def validate_task_sources(
    tasks: Iterable[Tuple[str, str, Path, Path]],
    benchmark_root: Path,
    manifest_path: Path = MANIFEST_PATH,
) -> str:
    """Validate requested task paths and bytes against the frozen manifest.

    Each task is ``(domain, problem, domain_file, problem_file)``.  File paths
    may be absolute or relative to ``benchmark_root``.  The function rejects
    duplicate/unknown task keys, paths outside the benchmark root, mismatched
    canonical relative paths, and PDDL byte hashes that differ from the
    manifest.  It returns a deterministic SHA-256 over the validated manifest
    records, sorted by ``(domain, problem)``, for experiment provenance.
    """
    data = load_manifest(manifest_path)
    records = {
        (record["domain"], record["problem"]): record
        for record in data["tasks"]  # type: ignore[index]
    }
    root = Path(benchmark_root).resolve()
    if not root.is_dir():
        raise RuntimeError(f"benchmark root is not a directory: {root}")

    selected = []
    seen: Set[TaskKey] = set()
    for domain, problem, domain_file, problem_file in tasks:
        key = (domain, problem)
        if key in seen:
            raise RuntimeError(f"duplicate requested task {key}")
        seen.add(key)
        try:
            record = records[key]
        except KeyError as err:
            raise RuntimeError(f"requested task {key} is not in the manifest") from err

        for path_value, path_field, hash_field in (
            (domain_file, "domain_file", "domain_sha256"),
            (problem_file, "problem_file", "problem_sha256"),
        ):
            source = Path(path_value)
            if not source.is_absolute():
                source = root / source
            source = source.resolve()
            try:
                relative = source.relative_to(root).as_posix()
            except ValueError as err:
                raise RuntimeError(
                    f"requested task {key} source is outside benchmark root: "
                    f"{source}") from err
            if not source.is_file():
                raise RuntimeError(
                    f"requested task {key} source is not a file: {source}")
            if relative != record[path_field]:
                raise RuntimeError(
                    f"requested task {key} {path_field} is {relative!r}, "
                    f"manifest has {record[path_field]!r}")
            actual_hash = sha256_file(source)
            if actual_hash != record[hash_field]:
                raise RuntimeError(
                    f"requested task {key} {hash_field} mismatch: "
                    f"expected {record[hash_field]}, got {actual_hash}")
        selected.append(record)

    if not selected:
        raise RuntimeError("cannot attest an empty task set")
    selected.sort(key=lambda record: (record["domain"], record["problem"]))
    return hashlib.sha256(canonical_records_bytes(selected)).hexdigest()
