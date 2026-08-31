#!/usr/bin/env python3
"""Build the frozen cost/axiom attestation for the unseen shadow cohort."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import generate_suite_cost_manifest as Cost
import pdb_terminal_incidence_shadow_protocol as P


class SourceAuditError(RuntimeError):
    pass


SCHEMA = "pdb-terminal-incidence-source-attestation-v1"
DEFAULT_BENCHMARKS = Path(
    "/nobackup/proj/disk/dfsplan/personal/jendrik/downward-benchmarks-wbh"
)
DEFAULT_SHARDS = (
    SCRIPT_DIR / "data" / "pdb_terminal_incidence_source_audit_v2"
)
DEFAULT_CODE_MANIFEST = (
    SCRIPT_DIR / "pdb_terminal_incidence_source_audit_code.sha256"
)
CODE_MANIFEST_FILES = (
    "experiments/audit_pdb_terminal_incidence_sources.py",
    "experiments/exp_pdb_profile_certificate_holdout.py",
    "experiments/generate_suite_cost_manifest.py",
    "experiments/jj_cached_revision.py",
    "experiments/launch_pdb_terminal_incidence_source_audit.py",
    "experiments/pdb_profile_certificate_holdout_protocol.py",
    "experiments/pdb_profile_comparison_protocol.py",
    "experiments/pdb_profile_semantic_union_protocol.py",
    "experiments/pdb_terminal_incidence_shadow_protocol.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/suite_cost_manifest.py",
    "experiments/suite_wbh.py",
    "experiments/suite_wbh_operator_costs.json",
    "experiments/suite_wbh_operator_costs.json.sha256",
)
TRANSLATOR_FILES = (
    "src/translate/__init__.py",
    "src/translate/__main__.py",
    "src/translate/axiom_rules.py",
    "src/translate/build_model.py",
    "src/translate/constraints.py",
    "src/translate/fact_groups.py",
    "src/translate/graph.py",
    "src/translate/greedy_join.py",
    "src/translate/instantiate.py",
    "src/translate/invariant_finder.py",
    "src/translate/invariants.py",
    "src/translate/main.py",
    "src/translate/normalize.py",
    "src/translate/options.py",
    "src/translate/pddl/__init__.py",
    "src/translate/pddl/actions.py",
    "src/translate/pddl/axioms.py",
    "src/translate/pddl/conditions.py",
    "src/translate/pddl/effects.py",
    "src/translate/pddl/f_expression.py",
    "src/translate/pddl/functions.py",
    "src/translate/pddl/pddl_types.py",
    "src/translate/pddl/predicates.py",
    "src/translate/pddl/tasks.py",
    "src/translate/pddl_parser/__init__.py",
    "src/translate/pddl_parser/lisp_parser.py",
    "src/translate/pddl_parser/parse_error.py",
    "src/translate/pddl_parser/parsing_functions.py",
    "src/translate/pddl_parser/pddl_file.py",
    "src/translate/pddl_parser/warning.py",
    "src/translate/pddl_to_prolog.py",
    "src/translate/sas_tasks.py",
    "src/translate/sccs.py",
    "src/translate/simplify.py",
    "src/translate/split_rules.py",
    "src/translate/timers.py",
    "src/translate/tools.py",
    "src/translate/variable_order.py",
)


def translator_source_digest() -> str:
    digest = hashlib.sha256()
    for name in TRANSLATOR_FILES:
        path = REPO / name
        try:
            payload = path.read_bytes()
        except OSError as err:
            raise SourceAuditError("cannot read {}".format(name)) from err
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(len(payload)).encode("ascii"))
        digest.update(b"\0")
        digest.update(payload)
        digest.update(b"\0")
    value = digest.hexdigest()
    if value != P.TRANSLATOR_SOURCE_SHA256:
        raise SourceAuditError("translator source tree changed")
    return value


def validate_code_manifest(path: Path, expected_sha256: str) -> dict:
    try:
        raw = path.read_bytes()
    except OSError as err:
        raise SourceAuditError("cannot read source-audit code manifest") from err
    if (
        len(expected_sha256) != 64
        or any(char not in "0123456789abcdef" for char in expected_sha256)
        or hashlib.sha256(raw).hexdigest() != expected_sha256
    ):
        raise SourceAuditError("source-audit code manifest hash changed")
    records = {}
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise SourceAuditError("source-audit code manifest is not ASCII") from err
    for line in lines:
        fields = line.split("  ", 1)
        if (
            len(fields) != 2
            or len(fields[0]) != 64
            or any(char not in "0123456789abcdef" for char in fields[0])
            or not fields[1]
            or fields[1] in records
        ):
            raise SourceAuditError("source-audit code manifest is malformed")
        records[fields[1]] = fields[0]
    if tuple(sorted(records)) != tuple(sorted(CODE_MANIFEST_FILES)):
        raise SourceAuditError("source-audit code manifest file set changed")
    for relative, expected in records.items():
        candidate = REPO / relative
        if candidate.is_symlink() or not candidate.is_file():
            raise SourceAuditError("source-audit dependency is not regular")
        if P.sha256_file(candidate) != expected:
            raise SourceAuditError("source-audit dependency bytes changed")
    import exp_pdb_profile_certificate_holdout as Base

    environment = Base._environment_attestation(
        SCRIPT_DIR / "requirements-pdb-terminal-incidence-shadow.txt"
    )
    return {
        "code_manifest_sha256": expected_sha256,
        "python_version": Base.platform.python_version(),
        "python_executable": str(Path(Base.sys.executable).resolve()),
        **environment,
    }


def _atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii") + b"\n"
    try:
        with path.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise SourceAuditError(
            "refusing to overwrite source-audit output"
        ) from err


def shard_path(directory: Path, index: int, count: int) -> Path:
    return directory / "shard-{:03d}-of-{:03d}.json".format(index, count)


class TaskAdapter:
    def __init__(self, task, benchmarks: Path):
        self.domain = task.domain
        self.problem = task.problem
        self.domain_file = benchmarks / task.domain_file
        self.problem_file = benchmarks / task.problem_file


def _scan_task(task, benchmarks: Path, timeout: int) -> dict:
    adapter = TaskAdapter(task, benchmarks)
    metric = Cost.parse_use_min_cost_metric(
        adapter.domain_file, adapter.problem_file
    )
    if metric:
        full = Cost.translate(adapter, benchmarks, timeout)
        if any((
            full["classification_method"] != "sas_v3_scan",
            full["cost_class"] != "positive-cost",
            type(full["num_operators"]) is not int,
            full["num_operators"] < 1,
            full["num_zero_cost_operators"] != 0,
            type(full["min_operator_cost"]) is not int,
            full["min_operator_cost"] < 1,
        )):
            raise SourceAuditError(
                "metric task is not strictly positive-cost: {}:{}".format(
                    task.domain, task.problem
                )
            )
    else:
        full = Cost.prove_no_metric_unit_cost(adapter, benchmarks)
    if full["num_normalized_axioms"] != 0:
        raise SourceAuditError(
            "task has normalized axioms: {}:{}".format(
                task.domain, task.problem
            )
        )
    if any((
        full["domain_sha256"] != task.domain_sha256,
        full["problem_sha256"] != task.problem_sha256,
        full["num_zero_cost_operators"] != 0,
    )):
        raise SourceAuditError("task source or cost evidence changed")
    return {
        "domain": task.domain,
        "problem": task.problem,
        "domain_sha256": task.domain_sha256,
        "problem_sha256": task.problem_sha256,
        "use_min_cost_metric": metric,
        "classification_method": full["classification_method"],
        "num_operators": full["num_operators"],
        "num_zero_cost_operators": full["num_zero_cost_operators"],
        "min_operator_cost": full["min_operator_cost"],
        "num_normalized_axioms": full["num_normalized_axioms"],
    }


def scan(args) -> None:
    code = validate_code_manifest(
        args.code_manifest.resolve(), args.code_manifest_sha256
    )
    translator_source_digest()
    if args.num_shards <= 0 or not 0 <= args.shard_index < args.num_shards:
        raise SourceAuditError("invalid shard request")
    if args.task_timeout <= 0:
        raise SourceAuditError("task timeout must be positive")
    benchmarks = args.benchmarks.resolve()
    cohort = P.load_cohort(benchmarks, validate_costs=False)
    selected = cohort[args.shard_index::args.num_shards]
    records = []
    for position, task in enumerate(selected, 1):
        print(
            "[{}/{}] {}:{}".format(
                position, len(selected), task.domain, task.problem
            ),
            flush=True,
        )
        records.append(_scan_task(task, benchmarks, args.task_timeout))
    value = {
        "schema": SCHEMA + "-shard",
        "shard_index": args.shard_index,
        "num_shards": args.num_shards,
        "benchmark_revision": P.BENCHMARK_REVISION,
        "translator_source_sha256": P.TRANSLATOR_SOURCE_SHA256,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        **code,
        "tasks": records,
    }
    output = shard_path(args.output_dir, args.shard_index, args.num_shards)
    if output.exists():
        raise SourceAuditError("refusing to overwrite a source-audit shard")
    _atomic_json(output, value)
    print("wrote {}".format(output), flush=True)


def _load_shard(
    path: Path, index: int, count: int, expected_tasks, code: dict
) -> list:
    try:
        value = json.loads(path.read_text(encoding="ascii"))
    except (OSError, ValueError) as err:
        raise SourceAuditError("cannot load {}".format(path)) from err
    header = (
        value.get("schema"),
        value.get("shard_index"),
        value.get("num_shards"),
        value.get("benchmark_revision"),
        value.get("translator_source_sha256"),
        value.get("cohort_manifest_sha256"),
        *[value.get(field) for field in code],
    )
    expected_header = (
        SCHEMA + "-shard",
        index,
        count,
        P.BENCHMARK_REVISION,
        P.TRANSLATOR_SOURCE_SHA256,
        P.COHORT_MANIFEST_SHA256,
        *code.values(),
    )
    tasks = value.get("tasks")
    expected_keys = [(task.domain, task.problem) for task in expected_tasks]
    actual_keys = (
        [(record.get("domain"), record.get("problem")) for record in tasks]
        if isinstance(tasks, list)
        else None
    )
    if header != expected_header or actual_keys != expected_keys:
        raise SourceAuditError("shard identity changed: {}".format(path))
    return tasks


def assemble(args) -> None:
    code = validate_code_manifest(
        args.code_manifest.resolve(), args.code_manifest_sha256
    )
    translator_source_digest()
    benchmarks = args.benchmarks.resolve()
    cohort = P.load_cohort(benchmarks, validate_costs=False)
    records = []
    for index in range(args.num_shards):
        records.extend(_load_shard(
            shard_path(args.shard_dir, index, args.num_shards),
            index,
            args.num_shards,
            cohort[index::args.num_shards],
            code,
        ))
    records.sort(key=lambda record: (record["domain"], record["problem"]))
    if [(r["domain"], r["problem"]) for r in records] != [
        (task.domain, task.problem) for task in cohort
    ]:
        raise SourceAuditError("assembled task order changed")
    metric = sum(record["use_min_cost_metric"] for record in records)
    proof = len(records) - metric
    counts = {
        "tasks": len(records),
        "sas_v3_scan": metric,
        "pddl_no_metric_unit_cost_proof": proof,
        "positive_cost": sum(
            record["num_zero_cost_operators"] == 0 for record in records
        ),
        "with_normalized_axioms": sum(
            record["num_normalized_axioms"] > 0 for record in records
        ),
    }
    if counts != {
        "tasks": 460,
        "sas_v3_scan": 190,
        "pddl_no_metric_unit_cost_proof": 270,
        "positive_cost": 460,
        "with_normalized_axioms": 0,
    }:
        raise SourceAuditError("assembled support counts changed")
    value = {
        "schema": SCHEMA,
        "benchmark_revision": P.BENCHMARK_REVISION,
        "translator_source_sha256": P.TRANSLATOR_SOURCE_SHA256,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "counts": counts,
        "records_sha256": hashlib.sha256(P.canonical_json(records)).hexdigest(),
        "tasks": records,
    }
    _atomic_json(args.output, value)
    print("wrote {}".format(args.output))
    print("sha256 {}".format(P.sha256_file(args.output)))


def self_test(args) -> None:
    translator_source_digest()
    cohort = P.load_cohort(args.benchmarks.resolve(), validate_costs=False)
    if len(cohort) != 460:
        raise SourceAuditError("cohort self-test failed")
    print("source audit OK: 460 frozen unseen tasks")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    scan_parser = subparsers.add_parser("scan")
    scan_parser.add_argument("--benchmarks", type=Path, default=DEFAULT_BENCHMARKS)
    scan_parser.add_argument("--output-dir", type=Path, default=DEFAULT_SHARDS)
    scan_parser.add_argument("--num-shards", type=int, required=True)
    scan_parser.add_argument("--shard-index", type=int, required=True)
    scan_parser.add_argument("--task-timeout", type=int, default=900)
    scan_parser.add_argument(
        "--code-manifest", type=Path, default=DEFAULT_CODE_MANIFEST
    )
    scan_parser.add_argument("--code-manifest-sha256", required=True)
    scan_parser.set_defaults(func=scan)
    assemble_parser = subparsers.add_parser("assemble")
    assemble_parser.add_argument("--benchmarks", type=Path, default=DEFAULT_BENCHMARKS)
    assemble_parser.add_argument("--shard-dir", type=Path, default=DEFAULT_SHARDS)
    assemble_parser.add_argument("--num-shards", type=int, required=True)
    assemble_parser.add_argument(
        "--code-manifest", type=Path, default=DEFAULT_CODE_MANIFEST
    )
    assemble_parser.add_argument("--code-manifest-sha256", required=True)
    assemble_parser.add_argument(
        "--output", type=Path, default=P.COST_ATTESTATION_PATH
    )
    assemble_parser.set_defaults(func=assemble)
    test_parser = subparsers.add_parser("self-test")
    test_parser.add_argument("--benchmarks", type=Path, default=DEFAULT_BENCHMARKS)
    test_parser.set_defaults(func=self_test)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    args.func(args)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SourceAuditError, P.ProtocolError, RuntimeError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
