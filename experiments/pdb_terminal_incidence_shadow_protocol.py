#!/usr/bin/env python3
"""Frozen design for the unseen fixed-frontier terminal-incidence study."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pdb_profile_comparison_protocol as Source


class ProtocolError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
PROTOCOL_PATH = SCRIPT_DIR / "pdb_terminal_incidence_shadow_protocol.md"
PROTOCOL_SHA256 = (
    "f0bbc8fce135b21e268e8bf9c31698b976fd7baa8413d13632c3c1b29c344c13"
)
COST_ATTESTATION_PATH = (
    SCRIPT_DIR / "pdb_terminal_incidence_shadow_cost_attestation.json"
)
COST_ATTESTATION_SHA256 = (
    "bf2c42860fad91c56620c90a41657ab472f4d58acd184a7580c7b5994aa72d04"
)
COST_ATTESTATION_RECORDS_SHA256 = (
    "b63b3007a1385938d2174e0f3deb3934a00f3fb432540463570ecdf263812779"
)
SOURCE_AUDIT_ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-shadow"
)
SOURCE_AUDIT_INTENT_PATH = (
    SOURCE_AUDIT_ARTIFACT_DIR / "source-audit-launch-intent-v2.json"
)
SOURCE_AUDIT_LAUNCH_RECEIPT_PATH = (
    SOURCE_AUDIT_ARTIFACT_DIR / "source-audit-launch-receipt-v2.json"
)
SOURCE_AUDIT_EXECUTION_RECEIPT_PATH = (
    SOURCE_AUDIT_ARTIFACT_DIR / "source-audit-execution-receipt-v2.json"
)
SOURCE_AUDIT_CODE_MANIFEST_PATH = (
    SCRIPT_DIR / "pdb_terminal_incidence_source_audit_code.sha256"
)
SOURCE_AUDIT_INTENT_SHA256 = (
    "e6ab40376b6e46e60011ce652e9496e1085412189b64428b00aa64ac973e8c94"
)
SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256 = (
    "fface210968fe9874e4857d4201d32a6db553a9d1c6c34d35d50f0af21f4ce98"
)
SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256 = (
    "2922b93fa2503c609ddc37cc4984613531278700dfeaba856357eda45f6695b2"
)
SOURCE_AUDIT_SLURM_SHA256 = (
    "03d31ac88cfe6254a2a8872d53cd9cc504486fe501e7ef676c6c6e8473427eab"
)
SOURCE_AUDIT_CODE_MANIFEST_SHA256 = (
    "77325d690ed7b3ed04c53b4f62214976d3073581a0259a6d398e3e642ce14e37"
)
SOURCE_AUDIT_OUTPUT_TREE_SHA256 = (
    "36e2dcc52f17ae7748cd4ed0d7b7d0123eb1cfa8217cf70986db291bad45656a"
)
SOURCE_AUDIT_LAUNCHER_SHA256 = (
    "c08f6fcab8379ebfc658ad508e240af35f39bde1f25ae6829beaa351aa5b29b8"
)
SOURCE_AUDIT_JOB_ID = "1853346"

PROTOCOL = "pdb-terminal-incidence-shadow-measurement-v1"
ANALYSIS_PROTOCOL = "pdb-terminal-incidence-shadow-analysis-v1"
COHORT_ROLE = "prospective-content-disjoint-fixed-frontier-holdout"
COHORT_SEED = "symbolic-search-heuristics/fixed-frontier-shadow-cohort/v1"
BENCHMARK_REVISION = "48d6a00d482de2384a9e751f9343df58bf5582be"
BENCHMARK_REPOSITORY = "https://github.com/aibasel/downward-benchmarks.git"
TRANSLATOR_SOURCE_SHA256 = (
    "c93a014324c4866cc9f83c456d75fc2ad9d4b397bae48411bdc0c757e2f88cbc"
)

DIRECTORIES = (
    "agricola-opt18-strips",
    "agricola-sat18-strips",
    "barman-mco14-strips",
    "barman-sat11-strips",
    "barman-sat14-strips",
    "caldera-opt18-adl",
    "caldera-sat18-adl",
    "caldera-split-opt18-adl",
    "caldera-split-sat18-adl",
    "cavediving-14-adl",
    "childsnack-sat14-strips",
    "floortile-sat11-strips",
    "floortile-sat14-strips",
    "hiking-agl14-strips",
    "hiking-sat14-strips",
    "maintenance-sat14-adl",
    "miconic-simpleadl",
    "nomystery-sat11-strips",
    "nurikabe-opt18-adl",
    "nurikabe-sat18-adl",
    "openstacks-strips",
    "organic-synthesis-sat18-strips",
    "organic-synthesis-split-opt18-strips",
    "organic-synthesis-split-sat18-strips",
    "parking-sat11-strips",
    "parking-sat14-strips",
    "quantum-layout-opt23-strips",
    "quantum-layout-sat23-strips",
    "rubiks-cube-opt23-adl",
    "rubiks-cube-sat23-adl",
    "schedule",
    "slitherlink-opt23-adl",
    "slitherlink-sat23-adl",
    "snake-sat18-strips",
    "termes-sat18-strips",
    "tetris-sat14-strips",
    "thoughtful-mco14-strips",
    "thoughtful-sat14-strips",
    "tidybot-sat11-strips",
    "transport-sat08-strips",
    "transport-sat11-strips",
    "transport-sat14-strips",
    "visitall-sat11-strips",
    "visitall-sat14-strips",
    "woodworking-sat08-strips",
    "woodworking-sat11-strips",
)
DIRECTORY_TO_FAMILY = {
    "agricola-opt18-strips": "agricola",
    "agricola-sat18-strips": "agricola",
    "barman-mco14-strips": "barman",
    "barman-sat11-strips": "barman",
    "barman-sat14-strips": "barman",
    "caldera-opt18-adl": "caldera",
    "caldera-sat18-adl": "caldera",
    "caldera-split-opt18-adl": "caldera",
    "caldera-split-sat18-adl": "caldera",
    "cavediving-14-adl": "cavediving",
    "childsnack-sat14-strips": "childsnack",
    "floortile-sat11-strips": "floortile",
    "floortile-sat14-strips": "floortile",
    "hiking-agl14-strips": "hiking",
    "hiking-sat14-strips": "hiking",
    "maintenance-sat14-adl": "maintenance",
    "miconic-simpleadl": "miconic",
    "nomystery-sat11-strips": "nomystery",
    "nurikabe-opt18-adl": "nurikabe",
    "nurikabe-sat18-adl": "nurikabe",
    "openstacks-strips": "openstacks",
    "organic-synthesis-sat18-strips": "organic-synthesis",
    "organic-synthesis-split-opt18-strips": "organic-synthesis",
    "organic-synthesis-split-sat18-strips": "organic-synthesis",
    "parking-sat11-strips": "parking",
    "parking-sat14-strips": "parking",
    "quantum-layout-opt23-strips": "quantum-layout",
    "quantum-layout-sat23-strips": "quantum-layout",
    "rubiks-cube-opt23-adl": "rubiks-cube",
    "rubiks-cube-sat23-adl": "rubiks-cube",
    "schedule": "schedule",
    "slitherlink-opt23-adl": "slitherlink",
    "slitherlink-sat23-adl": "slitherlink",
    "snake-sat18-strips": "snake",
    "termes-sat18-strips": "termes",
    "tetris-sat14-strips": "tetris",
    "thoughtful-mco14-strips": "thoughtful",
    "thoughtful-sat14-strips": "thoughtful",
    "tidybot-sat11-strips": "tidybot",
    "transport-sat08-strips": "transport",
    "transport-sat11-strips": "transport",
    "transport-sat14-strips": "transport",
    "visitall-sat11-strips": "visitall",
    "visitall-sat14-strips": "visitall",
    "woodworking-sat08-strips": "woodworking",
    "woodworking-sat11-strips": "woodworking",
}

TASKS_PER_DIRECTORY = 10
COHORT_TASKS = 460
COHORT_DIRECTORIES = 46
COHORT_FAMILIES = 26
COHORT_DOMAINS = COHORT_DIRECTORIES
COHORT_MANIFEST_SHA256 = (
    "c22049efdc82bb6807a91e7be6f2f81f0197344a9f0f7ebf0db86cb1cb79188b"
)
TASK_NAME_SHA256 = (
    "7f92fca9ba998356ee9d116c7e8df5e06a88a87e27922e124ac8446085f36218"
)
SOURCE_PATH_SHA256 = (
    "a071cb13758609a785a06fa0a5e08d91158588098c7a15a403cce0ce3b09c282"
)
PROBLEM_HASH_SHA256 = (
    "f88b982d926008990ce084cb2a116c25962138c6a087db38073de989042965c0"
)
CONTENT_PAIR_SHA256 = (
    "dc6678af01fe3ca0a037443d483780bc47e529c06f27d103365a39d5aba8a0ed"
)
DIRECTORY_SEQUENCE_SHA256 = (
    "42ad772a9a33392c6a5e280cd9ef0e8224e1f4b89a118269147ce68844d4229a"
)
DIRECTORY_FAMILY_JSON_SHA256 = (
    "f0d061cd6cf6448cf476767d094d6194ec1575a27e90815a7234a447188130a7"
)
FAMILY_LINE_SHA256 = (
    "12071da2114339d3952b9e947a2146f2c2c4366804204e9822fbac5579248953"
)

TIME_LIMIT_SECONDS = 300
MEMORY_LIMIT_MIB = 8192
REQUIRED_LAB_VERSION = "8.10"
REQUIRED_PYTHON_VERSION = "3.12.13"
ACCOUNT = "naiss2025-5-561-cpu"
BUILD_OPTIONS = ("release_no_lp",)
PLANNER_REVISION = "c14ed234b92d8568df0b4acf429035709ece009d"
PLANNER_CACHE_NAME = "c14ed234b92d8568_1249b737326d"
PLANNER_BINARY_SHA256 = (
    "5ca678d8331e0d195eb235ec3365dac455a51d510795e17f57a46fdf433a5acd"
)
PREPROCESS_BINARY_SHA256 = (
    "c69b8df0d47c0b6c31bc97f5b0ad6d53bdb17330157b4b3bb97462760cd4fde3"
)
PLANNER_TREE_MANIFEST_SHA256 = (
    "f890f6cbd0db8597614db530a870e08717abc4d6e014f1c95b7ee318ff26cda8"
)

HORIZON = 16
PRIMARY_LABELS = (
    "pdb_bdd_prefix_shadow",
    "pdb_goal_prefix_shadow",
    "pdb_goal_fill_shadow",
    "pdb_cegar_shadow",
)
INTERVENTION_LABEL = "pdb_goal_fill_cap8_shadow"
MIN_ELIGIBLE_TASKS = 300
MIN_ELIGIBLE_FAMILIES = 25
MIN_COMPARISON_TASKS = 300
MIN_COMPARISON_FAMILIES = 25
MIN_SHARED_STRICT_PAIRS = 600
MIN_PRIMARY_CONCORDANCE_NUMERATOR = 13
MIN_PRIMARY_CONCORDANCE_DENOMINATOR = 20
MIN_ADVANTAGE_NUMERATOR = 1
MIN_ADVANTAGE_DENOMINATOR = 50
BOOTSTRAP_REPLICATES = 10000
BOOTSTRAP_SEED = 20260831


def _pdb(mode: str, value_cap: int = -1) -> str:
    options = [
        "budget=100000",
        "pattern_selection={}".format(mode),
    ]
    if mode == "cegar":
        options.extend(("cegar_max_time=10", "cegar_seed=2011"))
    options.append("value_cap={}".format(value_cap))
    options.extend((
        "gamer_ordering=false",
        "dynamic_reordering=false",
        "shadow_partition=true",
        'wbh_log="{}"'.format(Source.LEGACY_LOG),
        'wbh_profile_log="{}"'.format(Source.PROFILE_LOG),
    ))
    return "sym_fw_pdb({})".format(",".join(options))


CONFIGS = (
    ("pdb_bdd_prefix_shadow", _pdb("bdd_prefix")),
    ("pdb_goal_prefix_shadow", _pdb("goal_prefix")),
    ("pdb_goal_fill_shadow", _pdb("goal_fill")),
    ("pdb_cegar_shadow", _pdb("cegar")),
    ("pdb_goal_fill_cap8_shadow", _pdb("goal_fill", 8)),
)
LABELS = tuple(label for label, _ in CONFIGS)
SEARCHES = dict(CONFIGS)
CONFIG_COUNT = len(CONFIGS)
CELL_COUNT = COHORT_TASKS * CONFIG_COUNT
OPTION_MATRIX_SHA256 = (
    "612f560c28d739be52abdcf6f0215a7e243b697681bf89f9bbe5631b2e1ce672"
)


@dataclass(frozen=True, order=True)
class CohortTask:
    domain: str
    problem: str
    family: str
    domain_file: str
    problem_file: str
    domain_sha256: str
    problem_sha256: str


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
        raise ProtocolError("value is not canonical finite JSON") from err


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with Path(path).open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as err:
        raise ProtocolError("cannot hash {}".format(path)) from err
    return digest.hexdigest()


def _digest(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def option_matrix_digest(configs=CONFIGS) -> str:
    return _digest(canonical_json([
        {"label": label, "search": search} for label, search in configs
    ]))


def _relative(path, root: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root.resolve()).as_posix()
    except ValueError as err:
        raise ProtocolError("benchmark source escapes the pinned root") from err


def _bare_record(task, root: Path) -> dict:
    domain_file = _relative(task.domain_file, root)
    problem_file = _relative(task.problem_file, root)
    return {
        "domain": task.domain,
        "problem": task.problem,
        "domain_file": domain_file,
        "problem_file": problem_file,
        "domain_sha256": sha256_file(root / domain_file),
        "problem_sha256": sha256_file(root / problem_file),
    }


def _repository_revision(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as err:
        raise ProtocolError("cannot resolve benchmark repository revision") from err
    return result.stdout.strip()


def _cohort_records(benchmarks: Path) -> list[dict]:
    try:
        from downward.suites import build_suite
        import suite_cost_manifest
    except ImportError as err:
        raise ProtocolError("cohort construction dependencies are unavailable") from err

    root = Path(benchmarks).resolve()
    if not root.is_dir() or _repository_revision(root) != BENCHMARK_REVISION:
        raise ProtocolError("benchmark root is not the frozen revision")
    manifest = suite_cost_manifest.load_manifest()
    seen_names = {
        (record["domain"], record["problem"])
        for record in manifest["tasks"]
    }
    seen_problem_hashes = {
        record["problem_sha256"] for record in manifest["tasks"]
    }
    selected_problem_hashes = set()
    records = []
    for directory in DIRECTORIES:
        candidates = []
        for task in build_suite(str(root), [directory]):
            record = _bare_record(task, root)
            if (
                (record["domain"], record["problem"]) in seen_names
                or record["problem_sha256"] in seen_problem_hashes
            ):
                continue
            score = _digest(
                (
                    COHORT_SEED
                    + "\0"
                    + directory
                    + "\0"
                    + record["problem_sha256"]
                    + "\0"
                    + record["problem"]
                ).encode("utf-8")
            )
            candidates.append((score, record["problem"], record))
        chosen = []
        for _, _, record in sorted(candidates):
            if record["problem_sha256"] in selected_problem_hashes:
                continue
            selected_problem_hashes.add(record["problem_sha256"])
            chosen.append(record)
            if len(chosen) == TASKS_PER_DIRECTORY:
                break
        if len(chosen) != TASKS_PER_DIRECTORY:
            raise ProtocolError(
                "directory {} no longer supplies ten unseen tasks".format(directory)
            )
        records.extend(chosen)
    records.sort(key=lambda record: (record["domain"], record["problem"]))
    return records


def _validate_cohort_hashes(records: list[dict]) -> None:
    expected = {
        "task names": (TASK_NAME_SHA256, "".join(
            "{}:{}\n".format(r["domain"], r["problem"]) for r in records
        ).encode("utf-8")),
        "source paths": (SOURCE_PATH_SHA256, b"".join(
            r["domain_file"].encode("utf-8")
            + b"\0"
            + r["problem_file"].encode("utf-8")
            + b"\n"
            for r in records
        )),
        "problem hashes": (PROBLEM_HASH_SHA256, "".join(
            r["problem_sha256"] + "\n" for r in records
        ).encode("ascii")),
        "content pairs": (CONTENT_PAIR_SHA256, "".join(
            r["domain_sha256"] + ":" + r["problem_sha256"] + "\n"
            for r in records
        ).encode("ascii")),
        "records": (COHORT_MANIFEST_SHA256, canonical_json(records)),
    }
    for label, (wanted, payload) in expected.items():
        if _digest(payload) != wanted:
            raise ProtocolError("cohort {} digest changed".format(label))
    if (
        len(records) != COHORT_TASKS
        or len({r["domain"] for r in records}) != COHORT_DIRECTORIES
        or len({r["problem_sha256"] for r in records}) != COHORT_TASKS
    ):
        raise ProtocolError("cohort cardinality changed")


def load_cohort(benchmarks, *, validate_costs=True):
    records = _cohort_records(Path(benchmarks))
    _validate_cohort_hashes(records)
    tasks = tuple(CohortTask(
        family=DIRECTORY_TO_FAMILY[record["domain"]], **record
    ) for record in records)
    if len({task.family for task in tasks}) != COHORT_FAMILIES:
        raise ProtocolError("cohort family count changed")
    if validate_costs:
        validate_cost_attestation(tasks)
    return tasks


def validate_benchmark_sources(cohort, benchmarks) -> None:
    root = Path(benchmarks).resolve()
    for task in cohort:
        for relative, expected in (
            (task.domain_file, task.domain_sha256),
            (task.problem_file, task.problem_sha256),
        ):
            if sha256_file(root / relative) != expected:
                raise ProtocolError(
                    "benchmark source hash changed: {}".format(relative)
                )


def validate_cost_attestation(cohort) -> dict:
    if COST_ATTESTATION_SHA256 == "TO_PIN":
        raise ProtocolError("cost attestation digest is not pinned")
    if sha256_file(COST_ATTESTATION_PATH) != COST_ATTESTATION_SHA256:
        raise ProtocolError("cost attestation bytes changed")
    try:
        data = json.loads(COST_ATTESTATION_PATH.read_text(encoding="ascii"))
    except (OSError, ValueError) as err:
        raise ProtocolError("cannot load cost attestation") from err
    expected_top = {
        "schema",
        "benchmark_revision",
        "translator_source_sha256",
        "cohort_manifest_sha256",
        "counts",
        "records_sha256",
        "tasks",
    }
    if not isinstance(data, dict) or set(data) != expected_top:
        raise ProtocolError("cost attestation fields changed")
    tasks = data["tasks"]
    required = {
        "domain",
        "problem",
        "domain_sha256",
        "problem_sha256",
        "use_min_cost_metric",
        "classification_method",
        "num_operators",
        "num_zero_cost_operators",
        "min_operator_cost",
        "num_normalized_axioms",
    }
    if (
        data["schema"] != "pdb-terminal-incidence-source-attestation-v1"
        or data["benchmark_revision"] != BENCHMARK_REVISION
        or data["translator_source_sha256"] != TRANSLATOR_SOURCE_SHA256
        or data["cohort_manifest_sha256"] != COHORT_MANIFEST_SHA256
        or not isinstance(tasks, list)
        or any(not isinstance(record, dict) or set(record) != required for record in tasks)
        or data["records_sha256"] != COST_ATTESTATION_RECORDS_SHA256
        or _digest(canonical_json(tasks)) != COST_ATTESTATION_RECORDS_SHA256
    ):
        raise ProtocolError("cost attestation identity changed")
    by_key = {(record["domain"], record["problem"]): record for record in tasks}
    if len(by_key) != COHORT_TASKS or len(tasks) != COHORT_TASKS:
        raise ProtocolError("cost attestation task count changed")
    metric = 0
    proof = 0
    for task in cohort:
        record = by_key.get((task.domain, task.problem))
        if record is None or any((
            record["domain_sha256"] != task.domain_sha256,
            record["problem_sha256"] != task.problem_sha256,
            type(record["use_min_cost_metric"]) is not bool,
            type(record["num_zero_cost_operators"]) is not int,
            record["num_zero_cost_operators"] != 0,
            type(record["num_normalized_axioms"]) is not int,
            record["num_normalized_axioms"] != 0,
        )):
            raise ProtocolError("task lacks positive-cost axiom-free evidence")
        if record["use_min_cost_metric"]:
            metric += 1
            if any((
                record["classification_method"] != "sas_v3_scan",
                type(record["num_operators"]) is not int,
                record["num_operators"] < 1,
                type(record["min_operator_cost"]) is not int,
                record["min_operator_cost"] < 1,
            )):
                raise ProtocolError("metric task lacks a complete positive SAS scan")
        else:
            proof += 1
            if any((
                record["classification_method"]
                != "pddl_no_metric_unit_cost_proof",
                record["num_operators"] is not None,
                record["min_operator_cost"] is not None,
            )):
                raise ProtocolError("nonmetric task lacks the unit-cost proof")
    expected_counts = {
        "tasks": COHORT_TASKS,
        "sas_v3_scan": 190,
        "pddl_no_metric_unit_cost_proof": 270,
        "positive_cost": COHORT_TASKS,
        "with_normalized_axioms": 0,
    }
    if data["counts"] != expected_counts or (metric, proof) != (190, 270):
        raise ProtocolError("cost-attestation counts changed")
    return data


def validate_source_audit_receipts() -> None:
    paths_and_hashes = (
        (SOURCE_AUDIT_INTENT_PATH, SOURCE_AUDIT_INTENT_SHA256),
        (
            SOURCE_AUDIT_LAUNCH_RECEIPT_PATH,
            SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256,
        ),
        (
            SOURCE_AUDIT_EXECUTION_RECEIPT_PATH,
            SOURCE_AUDIT_EXECUTION_RECEIPT_SHA256,
        ),
    )
    receipts = []
    for path, expected_hash in paths_and_hashes:
        try:
            actual_hash = sha256_file(path)
        except OSError as err:
            raise ProtocolError("cannot hash source-audit receipt") from err
        if actual_hash != expected_hash:
            raise ProtocolError("source-audit receipt bytes changed")
        try:
            raw = path.read_bytes()
            receipt = json.loads(raw.decode("ascii"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
            raise ProtocolError("cannot load source-audit receipt") from err
        if (
            not isinstance(receipt, dict)
            or raw != canonical_json(receipt) + b"\n"
        ):
            raise ProtocolError("source-audit receipt is not an object")
        receipts.append(receipt)
    intent, launch, execution = receipts
    expected_distributions = {
        "contourpy": "1.3.3",
        "cycler": "0.12.1",
        "fonttools": "4.64.0",
        "kiwisolver": "1.5.1",
        "lab": "8.10",
        "matplotlib": "3.11.1",
        "numpy": "2.5.2",
        "packaging": "26.3",
        "pillow": "12.3.0",
        "pyparsing": "3.3.2",
        "python-dateutil": "2.9.0.post0",
        "simplejson": "4.1.2",
        "six": "1.17.0",
        "txt2tags": "3.9",
    }
    output_dir = str(
        SCRIPT_DIR / "data" / "pdb_terminal_incidence_source_audit_v2"
    )
    candidate = str(
        SCRIPT_DIR
        / "data"
        / "pdb_terminal_incidence_source_audit_v2_candidate.json"
    )
    slurm_script = str(
        SCRIPT_DIR / "pdb_terminal_incidence_source_scan.slurm"
    )
    launch_fixed = {
        "schema": (
            "symbolic-search-heuristics/"
            "pdb-terminal-incidence-source-audit-launch/v2"
        ),
        "job_id": SOURCE_AUDIT_JOB_ID,
        "partition": "fat",
        "qos": "normal",
        "account": "naiss2025-5-561-cpu",
        "array": "0-45",
        "array_throttle": 0,
        "array_tasks": 46,
        "cpus_per_task": 1,
        "time_limit": "00:30:00",
        "memory_per_cpu": "8G",
        "benchmark_revision": BENCHMARK_REVISION,
        "cohort_manifest_sha256": COHORT_MANIFEST_SHA256,
        "translator_source_sha256": TRANSLATOR_SOURCE_SHA256,
        "slurm_script_sha256": SOURCE_AUDIT_SLURM_SHA256,
        "code_manifest_sha256": SOURCE_AUDIT_CODE_MANIFEST_SHA256,
        "launcher_sha256": SOURCE_AUDIT_LAUNCHER_SHA256,
        "launch_intent_sha256": SOURCE_AUDIT_INTENT_SHA256,
        "output_dir": output_dir,
        "candidate_attestation": candidate,
        "python_version": REQUIRED_PYTHON_VERSION,
        "python_executable": (
            "/home/jendrik/.local/share/uv/python/"
            "cpython-3.12.13-linux-x86_64-gnu/bin/python3.12"
        ),
        "python_executable_sha256": (
            "021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
        ),
        "python_environment_sha256": (
            "4256d52c7331ace41f456a98f21dda4485ab9dd82ac0eb11697291feb1da0819"
        ),
        "python_distributions": expected_distributions,
        "python_requirements_sha256": (
            "9176e14c79ca81d624fd5eca3c6eb79b799ecb8f08b39301c7c250b97d526422"
        ),
        "submit_command": ["sbatch", "--parsable", slurm_script],
    }
    execution_fixed = {
        "schema": (
            "symbolic-search-heuristics/"
            "pdb-terminal-incidence-source-audit-execution/v2"
        ),
        "launch_receipt_sha256": SOURCE_AUDIT_LAUNCH_RECEIPT_SHA256,
        "job_id": SOURCE_AUDIT_JOB_ID,
        "partition": "fat",
        "array_throttle": 0,
        "shards": 46,
        "scheduler_state_counts": {"COMPLETED": 46},
        "output_tree_sha256": SOURCE_AUDIT_OUTPUT_TREE_SHA256,
        "output_tree_files": 92,
        "code_manifest_sha256": SOURCE_AUDIT_CODE_MANIFEST_SHA256,
        "source_audit_passed": True,
        "attestation_sha256": COST_ATTESTATION_SHA256,
        "attestation_records_sha256": COST_ATTESTATION_RECORDS_SHA256,
        "counts": {
            "tasks": COHORT_TASKS,
            "sas_v3_scan": 190,
            "pddl_no_metric_unit_cost_proof": 270,
            "positive_cost": COHORT_TASKS,
            "with_normalized_axioms": 0,
        },
    }
    if any(launch.get(key) != value for key, value in launch_fixed.items()):
        raise ProtocolError("source-audit launch receipt semantics changed")
    expected_intent = {
        key: value for key, value in launch.items()
        if key not in {"job_id", "launch_intent_sha256"}
    }
    expected_intent["schema"] = launch_fixed["schema"] + "/intent"
    if intent != expected_intent:
        raise ProtocolError("source-audit launch intent semantics changed")
    if any(
        execution.get(key) != value
        for key, value in execution_fixed.items()
    ):
        raise ProtocolError("source-audit execution receipt semantics changed")
    rows = execution.get("scheduler_rows")
    if (
        not isinstance(rows, list)
        or len(rows) != 46
        or [row.get("array_task") for row in rows] != list(range(46))
        or any(
            not isinstance(row, dict)
            or set(row) != {
                "array_task", "state", "exit_code", "elapsed", "partition"
            }
            or row["state"] != "COMPLETED"
            or row["exit_code"] != "0:0"
            or row["partition"] != "fat"
            or not isinstance(row["elapsed"], str)
            for row in rows
        )
    ):
        raise ProtocolError("source-audit scheduler evidence changed")
    if sha256_file(SOURCE_AUDIT_CODE_MANIFEST_PATH) != (
        SOURCE_AUDIT_CODE_MANIFEST_SHA256
    ):
        raise ProtocolError("source-audit code manifest bytes changed")
    if sha256_file(SCRIPT_DIR / "pdb_terminal_incidence_source_scan.slurm") != (
        SOURCE_AUDIT_SLURM_SHA256
    ):
        raise ProtocolError("source-audit Slurm bytes changed")
    if sha256_file(
        SCRIPT_DIR / "launch_pdb_terminal_incidence_source_audit.py"
    ) != SOURCE_AUDIT_LAUNCHER_SHA256:
        raise ProtocolError("source-audit launcher bytes changed")


def validate_protocol_without_sources() -> None:
    validate_source_audit_receipts()
    if PROTOCOL_SHA256 == "TO_PIN" or sha256_file(PROTOCOL_PATH) != PROTOCOL_SHA256:
        raise ProtocolError("frozen protocol digest is absent or changed")
    if OPTION_MATRIX_SHA256 == "TO_PIN" or option_matrix_digest() != OPTION_MATRIX_SHA256:
        raise ProtocolError("option matrix digest is absent or changed")
    directory_payload = "".join(directory + "\n" for directory in DIRECTORIES)
    family_payload = "".join(
        family + "\n" for family in sorted(set(DIRECTORY_TO_FAMILY.values()))
    )
    if any((
        len(DIRECTORIES) != COHORT_DIRECTORIES,
        set(DIRECTORIES) != set(DIRECTORY_TO_FAMILY),
        len(set(DIRECTORY_TO_FAMILY.values())) != COHORT_FAMILIES,
        _digest(directory_payload.encode("utf-8")) != DIRECTORY_SEQUENCE_SHA256,
        _digest(canonical_json(DIRECTORY_TO_FAMILY))
        != DIRECTORY_FAMILY_JSON_SHA256,
        _digest(family_payload.encode("utf-8")) != FAMILY_LINE_SHA256,
        CONFIG_COUNT != 5,
        CELL_COUNT != 2300,
        LABELS[:-1] != PRIMARY_LABELS,
        LABELS[-1] != INTERVENTION_LABEL,
        len(LABELS) != len(set(LABELS)),
        ACCOUNT != "naiss2025-5-561-cpu",
        REQUIRED_LAB_VERSION != "8.10",
        REQUIRED_PYTHON_VERSION != "3.12.13",
        HORIZON != 16,
        MIN_ELIGIBLE_TASKS != 300,
        MIN_ELIGIBLE_FAMILIES != 25,
        MIN_COMPARISON_TASKS != 300,
        MIN_COMPARISON_FAMILIES != 25,
        MIN_SHARED_STRICT_PAIRS != 600,
        MIN_PRIMARY_CONCORDANCE_NUMERATOR != 13,
        MIN_PRIMARY_CONCORDANCE_DENOMINATOR != 20,
        MIN_ADVANTAGE_NUMERATOR != 1,
        MIN_ADVANTAGE_DENOMINATOR != 50,
        BOOTSTRAP_REPLICATES != 10000,
        BOOTSTRAP_SEED != 20260831,
    )):
        raise ProtocolError("frozen protocol constants changed")
    modes = {
        "pdb_bdd_prefix_shadow": "bdd_prefix",
        "pdb_goal_prefix_shadow": "goal_prefix",
        "pdb_goal_fill_shadow": "goal_fill",
        "pdb_cegar_shadow": "cegar",
        "pdb_goal_fill_cap8_shadow": "goal_fill",
    }
    for label, search in CONFIGS:
        mode = modes[label]
        if any((
            search.count("pattern_selection={}".format(mode)) != 1,
            search.count("budget=100000") != 1,
            search.count("gamer_ordering=false") != 1,
            search.count("dynamic_reordering=false") != 1,
            search.count("shadow_partition=true") != 1,
            search.count('wbh_log="{}"'.format(Source.LEGACY_LOG)) != 1,
            search.count('wbh_profile_log="{}"'.format(Source.PROFILE_LOG)) != 1,
            search.count(
                "value_cap={}".format(8 if label == INTERVENTION_LABEL else -1)
            ) != 1,
        )):
            raise ProtocolError("configuration contract changed for {}".format(label))


# Shared-runner compatibility: this protocol has no result archive; all
# outcome-independent checks are source based.
validate_protocol_without_archive = validate_protocol_without_sources


if __name__ == "__main__":
    validate_protocol_without_sources()
    print(
        "protocol OK: {} tasks x {} configs = {} cells".format(
            COHORT_TASKS, CONFIG_COUNT, CELL_COUNT
        )
    )
