#!/usr/bin/env python3
"""Generate and validate suite_wbh's frozen SAS operator-cost manifest.

Translation is intentionally a separate, shardable step so the 1697 PDDL
tasks can be processed on compute nodes rather than a login node.  Example::

    # One command per array element, with i in [0, 63].
    python generate_suite_cost_manifest.py scan \
        --benchmarks /path/to/downward-benchmarks \
        --output-dir data/suite_wbh_cost_scan \
        --num-shards 64 --shard-index i

    python generate_suite_cost_manifest.py assemble \
        --benchmarks /path/to/downward-benchmarks \
        --shard-dir data/suite_wbh_cost_scan --num-shards 64
    python generate_suite_cost_manifest.py validate \
        --benchmarks /path/to/downward-benchmarks

For 1684 tasks the scanner invokes the Fast Downward translator at the frozen
revision and parses every serialized SAS operator cost.  For 13 explicitly
pinned resource-heavy organic-synthesis task translations it parses the same
PDDL with the frozen parser and attests the frozen source chain that assigns
cost 1 when ``use_min_cost_metric`` is false and preserves it into SAS.  Both methods
classify the same predicate: zero-cost iff at least one serialized SAS operator
has cost 0.  Every task is also parsed and normalized with the pinned default
``axiom_based`` strategy; its exact normalized-axiom count independently
attests membership in the supported positive-cost, axiom-free subset.  PDDL
hashes, proof/normalization sources, repository revisions, exact suite
definition, record hash, and whole-file hash are retained as provenance.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from downward.suites import build_suite

import suite_cost_manifest as frozen
import suite_wbh


REPO = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST = frozen.MANIFEST_PATH
DEFAULT_SCAN_DIR = Path(__file__).resolve().parent / "data" / "suite_wbh_cost_scan"
TRANSLATOR_REVISION = "ec8399257de93e0739046a187af4bed0b85e19ce"
BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
BENCHMARK_REPOSITORY = "https://github.com/aibasel/downward-benchmarks.git"
TRANSLATOR_PATHS = ("src/translate",)
# The semantic suite is pinned below by its exact ordered domain-list hash,
# exact 1697 task keys, and per-task source paths/hashes.  Documentation-only
# edits to suite_wbh.py therefore do not invalidate translator provenance.
FROZEN_SUITE_PATHS: Tuple[str, ...] = ()
CRITERION = (
    frozen.EXPECTED_CRITERION
)
LEGACY_CRITERION = (
    "zero-cost iff the Fast Downward SAS v3 output contains at least one "
    "serialized operator with integer cost 0; positive-cost otherwise"
)
PRE_RESOURCE_HEAVY_CRITERION = CRITERION.replace(
    "pinned resource-heavy tasks", "pinned pathological tasks")
PROOF_SOURCE_PATHS = tuple(frozen.EXPECTED_PROOF_SOURCE_PATHS)
PROOF_TASKS = {tuple(task) for task in frozen.EXPECTED_PROOF_TASKS}
NORMALIZED_AXIOM_SOURCE_PATHS = tuple(
    frozen.EXPECTED_NORMALIZED_AXIOM_SOURCE_PATHS)


def run_git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], check=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout.strip()


def verify_revision(repo: Path, expected: str, paths: Sequence[str]) -> None:
    resolved = run_git(repo, "rev-parse", f"{expected}^{{commit}}")
    if resolved != expected:
        raise RuntimeError(
            f"{expected} does not resolve to the frozen commit in {repo}")
    diff = subprocess.run(
        ["git", "-C", str(repo), "diff", "--quiet", expected, "--", *paths])
    if diff.returncode != 0:
        raise RuntimeError(
            f"{repo} has changes relative to {expected} under {paths}")


def verify_benchmark_checkout(benchmarks: Path) -> None:
    actual = run_git(benchmarks, "rev-parse", "HEAD")
    if actual != BENCHMARK_REVISION:
        raise RuntimeError(
            f"benchmark checkout is at {actual}, expected {BENCHMARK_REVISION}")
    status = run_git(benchmarks, "status", "--porcelain", "--untracked-files=all")
    if status:
        raise RuntimeError("benchmark checkout is dirty; refusing provenance scan")


def hash_file(path: Path) -> str:
    return frozen.sha256_file(path)


def hash_named_files(repo: Path, revision: str, paths: Sequence[str]) -> str:
    names = run_git(
        repo, "ls-tree", "-r", "--name-only", revision, "--", *paths).splitlines()
    if not names:
        raise RuntimeError(f"no files found at {revision} under {paths}")
    digest = hashlib.sha256()
    for name in sorted(names):
        payload = (repo / name).read_bytes()
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()


def hash_strings(values: Iterable[str]) -> str:
    payload = "".join(f"{value}\n" for value in values).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def canonical_tasks(benchmarks: Path):
    tasks = build_suite(str(benchmarks), suite_wbh.suite())
    tasks.sort(key=lambda task: (task.domain, task.problem))
    keys = [(task.domain, task.problem) for task in tasks]
    if len(keys) != frozen.EXPECTED_TASKS or len(set(keys)) != len(keys):
        raise RuntimeError(
            f"suite_wbh enumerates {len(keys)} tasks ({len(set(keys))} unique), "
            f"expected {frozen.EXPECTED_TASKS}")
    return tasks


def relative_source(path, benchmarks: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(benchmarks.resolve()).as_posix()
    except ValueError as err:
        raise RuntimeError(
            f"suite source {resolved} is outside benchmark root {benchmarks}") from err


class SasReader:
    def __init__(self, path: Path):
        self.path = path
        self.lines = path.read_text(encoding="utf-8").splitlines()
        self.index = 0

    def line(self) -> str:
        if self.index >= len(self.lines):
            raise RuntimeError(f"unexpected end of SAS file {self.path}")
        value = self.lines[self.index]
        self.index += 1
        return value

    def integer(self) -> int:
        value = self.line()
        try:
            return int(value)
        except ValueError as err:
            raise RuntimeError(
                f"expected integer at line {self.index} of {self.path}: "
                f"{value!r}") from err

    def expect(self, expected: str) -> None:
        actual = self.line()
        if actual != expected:
            raise RuntimeError(
                f"expected {expected!r} at line {self.index} of "
                f"{self.path}, got {actual!r}")

    def skip(self, count: int) -> None:
        for _ in range(count):
            self.line()


def parse_sas_operator_costs(path: Path) -> List[int]:
    """Parse every operator cost from a Fast Downward SAS v3 file."""
    reader = SasReader(path)
    reader.expect("begin_version")
    version = reader.integer()
    reader.expect("end_version")
    if version != 3:
        raise RuntimeError(f"expected SAS version 3 in {path}, got {version}")
    reader.expect("begin_metric")
    reader.integer()
    reader.expect("end_metric")

    num_variables = reader.integer()
    for _ in range(num_variables):
        reader.expect("begin_variable")
        reader.line()  # variable name
        reader.integer()  # axiom layer
        reader.skip(reader.integer())  # value names
        reader.expect("end_variable")
    for _ in range(reader.integer()):
        reader.expect("begin_mutex_group")
        reader.skip(reader.integer())
        reader.expect("end_mutex_group")
    reader.expect("begin_state")
    reader.skip(num_variables)
    reader.expect("end_state")
    reader.expect("begin_goal")
    reader.skip(reader.integer())
    reader.expect("end_goal")

    costs: List[int] = []
    for _ in range(reader.integer()):
        reader.expect("begin_operator")
        reader.line()  # operator name
        reader.skip(reader.integer())  # prevail facts
        reader.skip(reader.integer())  # one serialized line per effect
        cost = reader.integer()
        if cost < 0:
            raise RuntimeError(f"negative SAS operator cost {cost} in {path}")
        costs.append(cost)
        reader.expect("end_operator")

    for _ in range(reader.integer()):
        reader.expect("begin_rule")
        reader.skip(reader.integer())
        reader.line()  # rule effect
        reader.expect("end_rule")
    if reader.index != len(reader.lines):
        raise RuntimeError(
            f"unexpected trailing content in {path} at line {reader.index + 1}")
    return costs


def translate(task, benchmarks: Path, timeout: int) -> Dict[str, object]:
    domain = Path(task.domain_file).resolve()
    problem = Path(task.problem_file).resolve()
    domain_rel = relative_source(domain, benchmarks)
    problem_rel = relative_source(problem, benchmarks)
    with tempfile.TemporaryDirectory(prefix="wbh-cost-") as tmp_name:
        tmp = Path(tmp_name)
        env = os.environ.copy()
        python_path = str(REPO / "src")
        if env.get("PYTHONPATH"):
            python_path += os.pathsep + env["PYTHONPATH"]
        env["PYTHONPATH"] = python_path
        command = [sys.executable, "-m", "translate", str(domain), str(problem)]
        try:
            result = subprocess.run(
                command, cwd=tmp, env=env, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE, text=True, timeout=timeout)
        except subprocess.TimeoutExpired as err:
            raise RuntimeError(
                f"translator timed out after {timeout}s for "
                f"{task.domain}:{task.problem}") from err
        if result.returncode != 0:
            tail = "\n".join(result.stderr.splitlines()[-20:])
            raise RuntimeError(
                f"translator failed with exit {result.returncode} for "
                f"{task.domain}:{task.problem}:\n{tail}")
        sas_path = tmp / "output.sas"
        if not sas_path.is_file():
            raise RuntimeError(
                f"translator produced no output.sas for "
                f"{task.domain}:{task.problem}")
        costs = parse_sas_operator_costs(sas_path)

    num_zero = sum(cost == 0 for cost in costs)
    return {
        "domain": task.domain,
        "problem": task.problem,
        "domain_file": domain_rel,
        "problem_file": problem_rel,
        "domain_sha256": hash_file(domain),
        "problem_sha256": hash_file(problem),
        "num_operators": len(costs),
        "num_zero_cost_operators": num_zero,
        "min_operator_cost": min(costs) if costs else None,
        "cost_class": "zero-cost" if num_zero else "positive-cost",
        "classification_method": "sas_v3_scan",
        "num_normalized_axioms": count_normalized_axioms(domain, problem),
    }


def parse_task(domain: Path, problem: Path):
    """Parse the exact PDDL bytes with the pinned translator parser."""
    source_root = str(REPO / "src")
    if source_root not in sys.path:
        sys.path.insert(0, source_root)
    from translate.pddl_parser import pddl_file
    return pddl_file.open(str(domain), str(problem))


def parse_use_min_cost_metric(domain: Path, problem: Path) -> bool:
    parsed = parse_task(domain, problem)
    if type(parsed.use_min_cost_metric) is not bool:
        raise RuntimeError("translator parser returned a non-boolean metric flag")
    return parsed.use_min_cost_metric


def count_normalized_axioms(domain: Path, problem: Path) -> int:
    """Count axioms after the pinned translator's default normalization."""
    parsed = parse_task(domain, problem)
    from translate import normalize
    normalize.normalize(parsed, frozen.EXPECTED_NORMALIZATION_STRATEGY)
    return len(parsed.axioms)


def prove_no_metric_unit_cost(task, benchmarks: Path) -> Dict[str, object]:
    """Prove the SAS zero-cost predicate without grounding the task.

    With ``use_min_cost_metric`` false, the pinned translator's
    ``Action.instantiate`` assigns cost 1 to every propositional operator.
    The pinned main/simplification/serialization path preserves that cost.
    Operator cardinality is deliberately left unknown.
    """
    domain = Path(task.domain_file).resolve()
    problem = Path(task.problem_file).resolve()
    parsed = parse_task(domain, problem)
    if type(parsed.use_min_cost_metric) is not bool:
        raise RuntimeError("translator parser returned a non-boolean metric flag")
    if parsed.use_min_cost_metric:
        raise RuntimeError(
            f"unit-cost proof rejected metric task {task.domain}:{task.problem}")
    from translate import normalize
    normalize.normalize(parsed, frozen.EXPECTED_NORMALIZATION_STRATEGY)
    return {
        "domain": task.domain,
        "problem": task.problem,
        "domain_file": relative_source(domain, benchmarks),
        "problem_file": relative_source(problem, benchmarks),
        "domain_sha256": hash_file(domain),
        "problem_sha256": hash_file(problem),
        "num_operators": None,
        "num_zero_cost_operators": 0,
        "min_operator_cost": None,
        "cost_class": "positive-cost",
        "classification_method": "pddl_no_metric_unit_cost_proof",
        "num_normalized_axioms": len(parsed.axioms),
    }


def provenance(benchmarks: Path) -> Dict[str, object]:
    return {
        "translator_revision": TRANSLATOR_REVISION,
        "translator_source_sha256": hash_named_files(
            REPO, TRANSLATOR_REVISION, TRANSLATOR_PATHS),
        "translator_command": "python -m translate DOMAIN PROBLEM",
        "translator_options": [],
        "sas_version": 3,
        "benchmark_revision": BENCHMARK_REVISION,
        "benchmark_repository": BENCHMARK_REPOSITORY,
        "suite_module": "experiments/suite_wbh.py",
        "suite_domains": suite_wbh.suite(),
        "suite_domains_sha256": hash_strings(suite_wbh.suite()),
        "suite_task_order": "lexicographic (domain, problem)",
        "classification_criterion": CRITERION,
        "classification_methods": frozen.EXPECTED_CLASSIFICATION_METHODS,
        "pddl_unit_cost_proof_source_paths": list(PROOF_SOURCE_PATHS),
        "pddl_unit_cost_proof_source_sha256": hash_named_files(
            REPO, TRANSLATOR_REVISION, PROOF_SOURCE_PATHS),
        "pddl_unit_cost_proof_tasks": frozen.EXPECTED_PROOF_TASKS,
        "support_criterion": frozen.EXPECTED_SUPPORT_CRITERION,
        "normalization_strategy": frozen.EXPECTED_NORMALIZATION_STRATEGY,
        "normalized_axiom_source_paths": list(NORMALIZED_AXIOM_SOURCE_PATHS),
        "normalized_axiom_source_sha256": hash_named_files(
            REPO, TRANSLATOR_REVISION, NORMALIZED_AXIOM_SOURCE_PATHS),
    }


def normalize_provenance(value) -> object:
    """Normalize shards made before repository URLs became canonical."""
    if not isinstance(value, dict):
        return value
    value = dict(value)
    if "benchmark_remote" in value:
        remote = value.pop("benchmark_remote")
        accepted = {
            "git@github.com:aibasel/downward-benchmarks.git",
            "https://github.com/aibasel/downward-benchmarks.git",
        }
        if remote not in accepted:
            raise RuntimeError(f"unexpected benchmark remote in shard: {remote!r}")
        value["benchmark_repository"] = BENCHMARK_REPOSITORY
    if value.get("classification_criterion") in {
            LEGACY_CRITERION, PRE_RESOURCE_HEAVY_CRITERION}:
        value["classification_criterion"] = CRITERION
        value["classification_methods"] = frozen.EXPECTED_CLASSIFICATION_METHODS
        value["pddl_unit_cost_proof_source_paths"] = list(PROOF_SOURCE_PATHS)
        value["pddl_unit_cost_proof_source_sha256"] = hash_named_files(
            REPO, TRANSLATOR_REVISION, PROOF_SOURCE_PATHS)
        value["pddl_unit_cost_proof_tasks"] = frozen.EXPECTED_PROOF_TASKS
    value.setdefault("support_criterion", frozen.EXPECTED_SUPPORT_CRITERION)
    value.setdefault(
        "normalization_strategy", frozen.EXPECTED_NORMALIZATION_STRATEGY)
    value.setdefault(
        "normalized_axiom_source_paths", list(NORMALIZED_AXIOM_SOURCE_PATHS))
    value.setdefault(
        "normalized_axiom_source_sha256", hash_named_files(
            REPO, TRANSLATOR_REVISION, NORMALIZED_AXIOM_SOURCE_PATHS))
    return value


def normalize_record(record: Mapping[str, object], task) -> Dict[str, object]:
    """Augment legacy shard records with method and support evidence."""
    normalized = dict(record)
    normalized.setdefault("classification_method", "sas_v3_scan")
    expected_axioms = count_normalized_axioms(
        Path(task.domain_file), Path(task.problem_file))
    if "num_normalized_axioms" in normalized and \
            normalized["num_normalized_axioms"] != expected_axioms:
        raise RuntimeError(
            f"normalized-axiom mismatch for {task.domain}:{task.problem}")
    normalized["num_normalized_axioms"] = expected_axioms
    return normalized


def atomic_json(path: Path, data: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, sort_keys=True) + "\n"
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}")
    temporary.write_text(payload, encoding="utf-8")
    os.replace(temporary, path)


def shard_path(directory: Path, index: int, count: int) -> Path:
    return directory / f"shard-{index:04d}-of-{count:04d}.json"


def validate_shard(
    path: Path,
    index: int,
    count: int,
    expected_provenance: Mapping[str, object],
    expected_tasks,
) -> List[Dict[str, object]]:
    shard = read_json(path)
    expected_header = (1, index, count, expected_provenance)
    actual_header = (
        shard.get("shard_schema_version"), shard.get("shard_index"),
        shard.get("num_shards"), normalize_provenance(shard.get("provenance")))
    if actual_header != expected_header:
        raise RuntimeError(f"provenance/header mismatch in {path}")
    records = shard.get("tasks")
    if not isinstance(records, list) or not all(
            isinstance(record, dict) for record in records):
        raise RuntimeError(f"invalid task records in {path}")
    selected_tasks = expected_tasks[index::count]
    if len(records) != len(selected_tasks):
        raise RuntimeError(
            f"task count mismatch in {path}: {len(records)} records for "
            f"{len(selected_tasks)} expected tasks")
    records = [
        normalize_record(record, task)
        for record, task in zip(records, selected_tasks)
    ]
    actual_keys = [
        (record.get("domain"), record.get("problem")) for record in records]
    expected_keys = [
        (task.domain, task.problem) for task in selected_tasks]
    if actual_keys != expected_keys:
        raise RuntimeError(f"task universe/order mismatch in {path}")
    for record, key in zip(records, actual_keys):
        expected_method = (
            "pddl_no_metric_unit_cost_proof" if key in PROOF_TASKS
            else "sas_v3_scan")
        if record.get("classification_method") != expected_method:
            raise RuntimeError(
                f"classification method mismatch for {key} in {path}: "
                f"expected {expected_method}")
    return records


def scan(args) -> None:
    benchmarks = args.benchmarks.resolve()
    verify_revision(REPO, TRANSLATOR_REVISION, TRANSLATOR_PATHS + FROZEN_SUITE_PATHS)
    verify_benchmark_checkout(benchmarks)
    if args.num_shards <= 0:
        raise RuntimeError("num-shards must be positive")
    if args.task_timeout <= 0:
        raise RuntimeError("task-timeout must be positive")
    if not 0 <= args.shard_index < args.num_shards:
        raise RuntimeError("shard index must be in [0, num-shards)")
    tasks = canonical_tasks(benchmarks)
    selected = tasks[args.shard_index::args.num_shards]
    records = []
    for position, task in enumerate(selected, 1):
        key = (task.domain, task.problem)
        if key in PROOF_TASKS:
            print(
                f"[{position}/{len(selected)}] proving unit cost for "
                f"{task.domain}:{task.problem}", flush=True)
            records.append(prove_no_metric_unit_cost(task, benchmarks))
        else:
            print(
                f"[{position}/{len(selected)}] translating "
                f"{task.domain}:{task.problem}", flush=True)
            records.append(translate(task, benchmarks, args.task_timeout))
    data = {
        "shard_schema_version": 1,
        "shard_index": args.shard_index,
        "num_shards": args.num_shards,
        "provenance": provenance(benchmarks),
        "tasks": records,
    }
    output = shard_path(args.output_dir, args.shard_index, args.num_shards)
    atomic_json(output, data)
    print(f"wrote {len(records)} records to {output}")


def read_json(path: Path) -> Dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise RuntimeError(f"cannot load {path}: {err}") from err
    if not isinstance(value, dict):
        raise RuntimeError(f"{path} does not contain a JSON object")
    return value


def scan_missing(args) -> None:
    """Validate completed shards and scan all missing ones concurrently."""
    benchmarks = args.benchmarks.resolve()
    verify_revision(REPO, TRANSLATOR_REVISION, TRANSLATOR_PATHS + FROZEN_SUITE_PATHS)
    verify_benchmark_checkout(benchmarks)
    if args.num_shards <= 0:
        raise RuntimeError("num-shards must be positive")
    if args.workers <= 0:
        raise RuntimeError("workers must be positive")
    if args.task_timeout <= 0:
        raise RuntimeError("task-timeout must be positive")
    tasks = canonical_tasks(benchmarks)
    expected_provenance = provenance(benchmarks)
    missing = []
    for index in range(args.num_shards):
        path = shard_path(args.output_dir, index, args.num_shards)
        if path.exists():
            validate_shard(
                path, index, args.num_shards, expected_provenance, tasks)
        else:
            missing.append(index)
    print(
        f"validated {args.num_shards - len(missing)} complete shards; "
        f"scanning {len(missing)} missing shards with {args.workers} workers",
        flush=True)

    def run_shard(index: int) -> None:
        command = [
            sys.executable, str(Path(__file__).resolve()), "scan",
            "--benchmarks", str(benchmarks),
            "--output-dir", str(args.output_dir),
            "--num-shards", str(args.num_shards),
            "--shard-index", str(index),
            "--task-timeout", str(args.task_timeout),
        ]
        subprocess.run(command, check=True)

    failures = []
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(args.workers, len(missing) or 1)) as executor:
        future_to_index = {
            executor.submit(run_shard, index): index for index in missing}
        for future in concurrent.futures.as_completed(future_to_index):
            index = future_to_index[future]
            try:
                future.result()
            except Exception as err:  # preserve all failed shard identifiers
                failures.append((index, err))
            else:
                print(f"completed shard {index}/{args.num_shards}", flush=True)
    if failures:
        details = ", ".join(f"{index}: {err}" for index, err in failures)
        raise RuntimeError(f"{len(failures)} shard scans failed: {details}")


def assemble(args) -> None:
    benchmarks = args.benchmarks.resolve()
    verify_revision(REPO, TRANSLATOR_REVISION, TRANSLATOR_PATHS + FROZEN_SUITE_PATHS)
    verify_benchmark_checkout(benchmarks)
    if args.num_shards <= 0:
        raise RuntimeError("num-shards must be positive")
    expected_provenance = provenance(benchmarks)
    expected_tasks = canonical_tasks(benchmarks)
    records: List[Dict[str, object]] = []
    for index in range(args.num_shards):
        path = shard_path(args.shard_dir, index, args.num_shards)
        shard_records = validate_shard(
            path, index, args.num_shards, expected_provenance,
            expected_tasks)
        records.extend(shard_records)

    records.sort(key=lambda record: (record["domain"], record["problem"]))
    actual_keys = [(record["domain"], record["problem"]) for record in records]
    expected_keys = [(task.domain, task.problem) for task in expected_tasks]
    if actual_keys != expected_keys:
        raise RuntimeError(
            "assembled shards do not exactly match the suite_wbh task universe")
    positive = sum(record["cost_class"] == "positive-cost" for record in records)
    zero = sum(record["cost_class"] == "zero-cost" for record in records)
    sas_scans = sum(
        record["classification_method"] == "sas_v3_scan"
        for record in records)
    unit_proofs = sum(
        record["classification_method"] == "pddl_no_metric_unit_cost_proof"
        for record in records)
    with_axioms = sum(bool(record["num_normalized_axioms"])
                      for record in records)
    positive_with_axioms = sum(
        record["cost_class"] == "positive-cost"
        and bool(record["num_normalized_axioms"])
        for record in records)
    zero_with_axioms = sum(
        record["cost_class"] == "zero-cost"
        and bool(record["num_normalized_axioms"])
        for record in records)
    supported = sum(
        record["cost_class"] == "positive-cost"
        and not record["num_normalized_axioms"]
        for record in records)
    observed_counts = (
        len(records), positive, zero, sas_scans, unit_proofs, with_axioms,
        positive_with_axioms, zero_with_axioms, supported)
    expected_counts = (
        frozen.EXPECTED_TASKS, frozen.EXPECTED_POSITIVE_COST,
        frozen.EXPECTED_ZERO_COST, frozen.EXPECTED_SAS_V3_SCAN,
        frozen.EXPECTED_PDDL_UNIT_COST_PROOF,
        frozen.EXPECTED_WITH_NORMALIZED_AXIOMS,
        frozen.EXPECTED_POSITIVE_WITH_NORMALIZED_AXIOMS,
        frozen.EXPECTED_ZERO_WITH_NORMALIZED_AXIOMS,
        frozen.EXPECTED_SUPPORTED_POSITIVE_AXIOM_FREE)
    if observed_counts != expected_counts:
        raise RuntimeError(
            f"classification totals {observed_counts} do not match frozen "
            f"expectation {expected_counts}")
    manifest = {
        "schema_version": frozen.SCHEMA_VERSION,
        "provenance": expected_provenance,
        "counts": {
            "tasks": len(records),
            "positive_cost": positive,
            "zero_cost": zero,
            "sas_v3_scan": sas_scans,
            "pddl_no_metric_unit_cost_proof": unit_proofs,
            "with_normalized_axioms": with_axioms,
            "positive_cost_with_normalized_axioms": positive_with_axioms,
            "zero_cost_with_normalized_axioms": zero_with_axioms,
            "supported_positive_axiom_free": supported,
        },
        "records_sha256": hashlib.sha256(
            frozen.canonical_records_bytes(records)).hexdigest(),
        "tasks": records,
    }
    atomic_json(args.output, manifest)
    checksum = hash_file(args.output)
    checksum_path = args.output.with_suffix(args.output.suffix + ".sha256")
    checksum_path.write_text(
        f"{checksum}  {args.output.name}\n", encoding="ascii")
    generated = frozen.load_manifest(args.output)
    validate_sources(generated, benchmarks)
    print(
        f"wrote {len(records)} tasks ({positive} positive-cost, "
        f"{zero} zero-cost) to {args.output}")
    print(f"manifest sha256: {checksum}")


def validate_sources(data: Mapping[str, object], benchmarks: Path) -> None:
    verify_revision(REPO, TRANSLATOR_REVISION, TRANSLATOR_PATHS + FROZEN_SUITE_PATHS)
    verify_benchmark_checkout(benchmarks)
    expected_provenance = provenance(benchmarks)
    if data.get("provenance") != expected_provenance:
        raise RuntimeError("manifest provenance does not match frozen sources")
    tasks = canonical_tasks(benchmarks)
    records = data["tasks"]
    if len(records) != len(tasks):
        raise RuntimeError("manifest/source task counts differ")
    for record, task in zip(records, tasks):
        expected = {
            "domain": task.domain,
            "problem": task.problem,
            "domain_file": relative_source(task.domain_file, benchmarks),
            "problem_file": relative_source(task.problem_file, benchmarks),
            "domain_sha256": hash_file(Path(task.domain_file)),
            "problem_sha256": hash_file(Path(task.problem_file)),
        }
        for field, value in expected.items():
            if record.get(field) != value:
                raise RuntimeError(
                    f"source mismatch for {task.domain}:{task.problem} "
                    f"field {field}: {record.get(field)!r} != {value!r}")
        if record.get("classification_method") == \
                "pddl_no_metric_unit_cost_proof" and \
                parse_use_min_cost_metric(
                    Path(task.domain_file), Path(task.problem_file)):
            raise RuntimeError(
                f"proof task unexpectedly uses a metric: "
                f"{task.domain}:{task.problem}")
        expected_axioms = count_normalized_axioms(
            Path(task.domain_file), Path(task.problem_file))
        if record.get("num_normalized_axioms") != expected_axioms:
            raise RuntimeError(
                f"normalized-axiom mismatch for {task.domain}:{task.problem}: "
                f"{record.get('num_normalized_axioms')!r} != "
                f"{expected_axioms}")


def validate(args) -> None:
    data = frozen.load_manifest(args.manifest)
    if args.benchmarks is not None:
        validate_sources(data, args.benchmarks.resolve())
    print(
        f"valid: {data['counts']['tasks']} tasks "
        f"({data['counts']['positive_cost']} positive-cost, "
        f"{data['counts']['zero_cost']} zero-cost; "
        f"{data['counts']['supported_positive_axiom_free']} supported)")
    print(f"records sha256: {data['records_sha256']}")
    print(f"manifest sha256: {hash_file(args.manifest)}")


def expect_manifest_rejection(
    data: Mapping[str, object],
    label: str,
    mutate,
    *,
    test_semantics: bool,
) -> None:
    """Require a coordinated manifest mutation to fail validation."""
    candidate = json.loads(json.dumps(data))
    mutate(candidate)
    candidate["records_sha256"] = hashlib.sha256(
        frozen.canonical_records_bytes(candidate["tasks"])).hexdigest()
    with tempfile.TemporaryDirectory(prefix="wbh-manifest-test-") as tmp_name:
        path = Path(tmp_name) / "candidate.json"
        atomic_json(path, candidate)
        checksum = hash_file(path)
        path.with_suffix(path.suffix + ".sha256").write_text(
            f"{checksum}  {path.name}\n", encoding="ascii")
        old_file_hash = frozen.EXPECTED_MANIFEST_SHA256
        old_records_hash = frozen.EXPECTED_RECORDS_SHA256
        if test_semantics:
            frozen.EXPECTED_MANIFEST_SHA256 = checksum
            frozen.EXPECTED_RECORDS_SHA256 = candidate["records_sha256"]
        try:
            frozen.load_manifest(path)
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"manifest mutation was accepted: {label}")
        finally:
            frozen.EXPECTED_MANIFEST_SHA256 = old_file_hash
            frozen.EXPECTED_RECORDS_SHA256 = old_records_hash


def expect_runtime_error(label: str, operation) -> None:
    try:
        operation()
    except RuntimeError:
        return
    raise AssertionError(f"invalid source request was accepted: {label}")


def self_test(args) -> None:
    """Exercise frozen pins, semantic mutations, parser evidence, and sources."""
    benchmarks = args.benchmarks.resolve()
    data = frozen.load_manifest(args.manifest)

    expect_manifest_rejection(
        data, "coordinated JSON/sidecar edit",
        lambda candidate: candidate["counts"].__setitem__(
            "supported_positive_axiom_free",
            candidate["counts"]["supported_positive_axiom_free"] + 1),
        test_semantics=False)

    def bad_axiom_type(candidate) -> None:
        candidate["tasks"][0]["num_normalized_axioms"] = False

    expect_manifest_rejection(
        data, "boolean normalized-axiom count", bad_axiom_type,
        test_semantics=True)

    def swap_axiom_membership(candidate) -> None:
        pathways = next(
            record for record in candidate["tasks"]
            if (record["domain"], record["problem"]) ==
            ("pathways", "p01.pddl"))
        supported = next(
            record for record in candidate["tasks"]
            if record["cost_class"] == "positive-cost"
            and record["num_normalized_axioms"] == 0)
        pathways["num_normalized_axioms"] = 0
        supported["num_normalized_axioms"] = 1

    expect_manifest_rejection(
        data, "normalized-axiom membership swap", swap_axiom_membership,
        test_semantics=True)
    expect_manifest_rejection(
        data, "declared supported count",
        lambda candidate: candidate["counts"].__setitem__(
            "supported_positive_axiom_free",
            candidate["counts"]["supported_positive_axiom_free"] + 1),
        test_semantics=True)
    expect_manifest_rejection(
        data, "normalization source hash",
        lambda candidate: candidate["provenance"].__setitem__(
            "normalized_axiom_source_sha256", "0" * 64),
        test_semantics=True)

    def bad_proof(candidate) -> None:
        proof = next(
            record for record in candidate["tasks"]
            if record["classification_method"] ==
            "pddl_no_metric_unit_cost_proof")
        proof["num_zero_cost_operators"] = 1

    expect_manifest_rejection(
        data, "unit-cost proof record", bad_proof, test_semantics=True)

    tasks = canonical_tasks(benchmarks)
    by_key = {(task.domain, task.problem): task for task in tasks}
    pathways_task = by_key[("pathways", "p01.pddl")]
    control_task = next(task for task in tasks if task.domain == "gripper")
    metric_task = next(
        task for task in tasks if task.domain == "barman-opt11-strips")
    if count_normalized_axioms(
            Path(pathways_task.domain_file),
            Path(pathways_task.problem_file)) <= 0:
        raise AssertionError("Pathways positive axiom fixture has no axioms")
    if count_normalized_axioms(
            Path(control_task.domain_file),
            Path(control_task.problem_file)) != 0:
        raise AssertionError("Gripper negative axiom fixture has axioms")
    if not parse_use_min_cost_metric(
            Path(metric_task.domain_file), Path(metric_task.problem_file)):
        raise AssertionError("Barman metric-proof rejection fixture is nonmetric")
    expect_runtime_error(
        "metric task unit-cost proof",
        lambda: prove_no_metric_unit_cost(metric_task, benchmarks))
    expect_runtime_error(
        "boolean supported-domain threshold",
        lambda: frozen.domains_with_min_supported_tasks(True))

    records = data["tasks"]
    selected_records = [
        records[0], next(
            record for record in records if record["domain"] == "gripper")]
    with tempfile.TemporaryDirectory(prefix="wbh-source-test-") as tmp_name:
        root = Path(tmp_name)
        for record in selected_records:
            for field in ("domain_file", "problem_file"):
                relative = Path(record[field])
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((benchmarks / relative).read_bytes())
        relative_tasks = [
            (record["domain"], record["problem"],
             Path(record["domain_file"]), Path(record["problem_file"]))
            for record in selected_records]
        absolute_tasks = [
            (domain, problem, root / domain_file, root / problem_file)
            for domain, problem, domain_file, problem_file in relative_tasks]
        relative_digest = frozen.validate_task_sources(relative_tasks, root)
        absolute_digest = frozen.validate_task_sources(absolute_tasks, root)
        reverse_digest = frozen.validate_task_sources(
            list(reversed(relative_tasks)), root)
        if len({relative_digest, absolute_digest, reverse_digest}) != 1:
            raise AssertionError("source attestation is path/order dependent")
        expect_runtime_error(
            "duplicate task", lambda: frozen.validate_task_sources(
                relative_tasks + relative_tasks[:1], root))
        expect_runtime_error(
            "unknown task", lambda: frozen.validate_task_sources(
                [("not-a-domain", "not-a-problem", Path("d"), Path("p"))],
                root))
        expect_runtime_error(
            "empty task set", lambda: frozen.validate_task_sources([], root))
        domain, problem, domain_file, problem_file = relative_tasks[0]
        tampered = root / problem_file
        original = tampered.read_bytes()
        tampered.write_bytes(original + b"\n")
        expect_runtime_error(
            "tampered PDDL bytes", lambda: frozen.validate_task_sources(
                [(domain, problem, domain_file, problem_file)], root))
        tampered.write_bytes(original)
        expect_runtime_error(
            "wrong canonical path", lambda: frozen.validate_task_sources(
                [(domain, problem, domain_file, relative_tasks[1][3])], root))

    print("manifest mutation/source-attestation self-tests: PASS")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("--benchmarks", type=Path, required=True)
    scan_parser.add_argument("--output-dir", type=Path, default=DEFAULT_SCAN_DIR)
    scan_parser.add_argument("--num-shards", type=int, required=True)
    scan_parser.add_argument("--shard-index", type=int, required=True)
    scan_parser.add_argument("--task-timeout", type=int, default=1800)
    scan_parser.set_defaults(func=scan)

    parallel_parser = subparsers.add_parser("scan-missing")
    parallel_parser.add_argument("--benchmarks", type=Path, required=True)
    parallel_parser.add_argument("--output-dir", type=Path, default=DEFAULT_SCAN_DIR)
    parallel_parser.add_argument("--num-shards", type=int, required=True)
    parallel_parser.add_argument("--workers", type=int, required=True)
    parallel_parser.add_argument("--task-timeout", type=int, default=1800)
    parallel_parser.set_defaults(func=scan_missing)

    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("--benchmarks", type=Path, required=True)
    assemble_parser.add_argument("--shard-dir", type=Path, default=DEFAULT_SCAN_DIR)
    assemble_parser.add_argument("--num-shards", type=int, required=True)
    assemble_parser.add_argument("--output", type=Path, default=DEFAULT_MANIFEST)
    assemble_parser.set_defaults(func=assemble)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    validate_parser.add_argument("--benchmarks", type=Path)
    validate_parser.set_defaults(func=validate)

    test_parser = subparsers.add_parser("self-test")
    test_parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    test_parser.add_argument("--benchmarks", type=Path, required=True)
    test_parser.set_defaults(func=self_test)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
