#!/usr/bin/env python3
"""Launch, monitor, and seal the universal confirmation source audit."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import stat
import subprocess
import sys
from collections import Counter
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources as Source
import pdb_terminal_incidence_confirmation_inventory as Inventory


class LaunchAuditError(RuntimeError):
    pass


SLURM_SCRIPT = (
    SCRIPT_DIR / "pdb_terminal_incidence_confirmation_source_scan.slurm"
)
CODE_MANIFEST = Source.DEFAULT_CODE_MANIFEST
OUTPUT_DIR = Source.DEFAULT_SHARDS
SOURCE_INVENTORY = Source.DEFAULT_INVENTORY
CANDIDATE = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v1_candidate.json"
)
ATTESTATION = Source.DEFAULT_OUTPUT
ARTIFACT_DIR = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation"
)
INTENT = ARTIFACT_DIR / "source-audit-launch-intent-v1.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-launch-receipt-v1.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v1.json"
LAUNCH_SCHEMA = Source.SCHEMA + "/launch"
EXECUTION_SCHEMA = Source.SCHEMA + "/execution"
ARRAY_TASKS = Source.SHARD_COUNT
ACCOUNT = "naiss2025-5-561-cpu"
CONTROLLED_PATH = Source.CONTROLLED_PATH
UNSET_PYTHON_ENV = Source.UNSET_PYTHON_ENV
PYTHON_COMMAND = (
    SCRIPT_DIR / "data" / "pdb-terminal-incidence-shadow-venv" /
    "bin" / "python"
)
SHA256SUM_COMMAND = Path("/usr/bin/sha256sum")
JJ_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MANIFEST_ASSIGNMENT_RE = re.compile(
    r'^code_manifest_sha256="([0-9a-f]{64})"$'
)
SUBMISSION_TOKEN_RE = re.compile(r"^[0-9a-f]{24}$")
JOURNAL_FIELDS = "JobID%64,JobName%128,Comment%128"


def _sha256(path: Path) -> str:
    return Source.sha256_file(path)


def _exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    try:
        return Source.atomic_exclusive_bytes(path, raw, label)
    except Source.SourceAuditError as err:
        raise LaunchAuditError(str(err)) from err


def _exclusive_json(path: Path, value, label: str) -> str:
    return _exclusive_bytes(path, Source.canonical_json(value), label)


def _load_json(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        info = path.lstat()
        raw = path.read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise LaunchAuditError("cannot load {}".format(label)) from err
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or not isinstance(value, dict)
        or raw != Source.canonical_json(value)
    ):
        raise LaunchAuditError("{} is not canonical".format(label))
    return raw, value


def _execution_environment(code: dict) -> dict:
    try:
        python_resolved = PYTHON_COMMAND.resolve(strict=True)
        sha256sum_resolved = SHA256SUM_COMMAND.resolve(strict=True)
    except OSError as err:
        raise LaunchAuditError("source-audit executable is absent") from err
    if not python_resolved.is_file() or not sha256sum_resolved.is_file():
        raise LaunchAuditError("source-audit executable is not regular")
    python_sha = _sha256(python_resolved)
    sha256sum_sha = _sha256(sha256sum_resolved)
    if (
        code.get("python_executable") != str(python_resolved)
        or code.get("python_executable_sha256") != python_sha
    ):
        raise LaunchAuditError("source-audit Python executable changed")
    return {
        "submission_export": "NONE",
        "slurm_export": "NONE",
        "unset_variables": list(UNSET_PYTHON_ENV),
        "python_no_user_site": "1",
        "python_no_user_site_flag": 1,
        "python_dont_write_bytecode": "1",
        "python_dont_write_bytecode_flag": True,
        "python_pycache_prefix_template": Source.PYTHON_CACHE_PREFIX_TEMPLATE,
        "outer_python_flag": "-B",
        "path": CONTROLLED_PATH,
        "translator_child_environment": {
            "PATH": CONTROLLED_PATH,
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPYCACHEPREFIX": Source.PYTHON_CACHE_PREFIX_TEMPLATE,
            "PYTHONPATH": str(REPO / "src"),
        },
        "python_command": str(PYTHON_COMMAND),
        "python_executable": str(python_resolved),
        "python_executable_sha256": python_sha,
        "sha256sum_command": str(SHA256SUM_COMMAND),
        "sha256sum_executable": str(sha256sum_resolved),
        "sha256sum_executable_sha256": sha256sum_sha,
    }


def _slurm_preflight() -> tuple[str, str, dict]:
    if SLURM_SCRIPT.is_symlink() or not SLURM_SCRIPT.is_file():
        raise LaunchAuditError("source-audit Slurm script is not regular")
    try:
        lines = SLURM_SCRIPT.read_text(encoding="ascii").splitlines()
    except (OSError, UnicodeDecodeError) as err:
        raise LaunchAuditError("cannot read source-audit Slurm script") from err
    required = {
        "#SBATCH --job-name=confirmation-source-audit",
        "#SBATCH --account={}".format(ACCOUNT),
        "#SBATCH --partition=fat",
        "#SBATCH --qos=normal",
        "#SBATCH --array=0-819",
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --mem-per-cpu=26G",
        "#SBATCH --time=01:40:00",
        "#SBATCH --output={}/slurm-%A_%a.out".format(OUTPUT_DIR),
        "#SBATCH --export=NONE",
    }
    if not required <= set(lines):
        raise LaunchAuditError("source-audit Slurm header changed")
    prefixes = (
        "#SBATCH --job-name=", "#SBATCH --account=",
        "#SBATCH --partition=", "#SBATCH --qos=", "#SBATCH --array=",
        "#SBATCH --cpus-per-task=", "#SBATCH --mem-per-cpu=",
        "#SBATCH --time=", "#SBATCH --output=", "#SBATCH --export=",
    )
    if any(
        sum(line.startswith(prefix) for line in lines) != 1
        for prefix in prefixes
    ):
        raise LaunchAuditError("source-audit Slurm directives conflict")
    array_line = next(line for line in lines if line.startswith("#SBATCH --array="))
    if "%" in array_line or any("--nice" in line for line in lines):
        raise LaunchAuditError("source-audit submission is throttled")
    assignments = [
        MANIFEST_ASSIGNMENT_RE.fullmatch(line)
        for line in lines
        if line.startswith("code_manifest_sha256=")
    ]
    if len(assignments) != 1 or assignments[0] is None:
        raise LaunchAuditError("source-audit code manifest is not pinned")
    manifest_sha = assignments[0].group(1)
    code = Source.validate_code_manifest(CODE_MANIFEST, manifest_sha)
    environment = _execution_environment(code)
    required_environment_lines = {
        "unset {}".format(" ".join(UNSET_PYTHON_ENV)),
        'export PYTHONNOUSERSITE="1"',
        'export PYTHONDONTWRITEBYTECODE="1"',
        'export PYTHONPYCACHEPREFIX="/tmp/symk-confirmation-source-audit-'
        '${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}"',
        'export PATH="{}"'.format(CONTROLLED_PATH),
        'python_executable="{}"'.format(PYTHON_COMMAND),
        'python_executable_sha256="{}"'.format(
            environment["python_executable_sha256"]
        ),
        'sha256sum_executable="{}"'.format(SHA256SUM_COMMAND),
        'sha256sum_executable_sha256="{}"'.format(
            environment["sha256sum_executable_sha256"]
        ),
        'exec "${python_executable}" -B \\',
    }
    if (
        not required_environment_lines <= set(lines)
        or any(lines.count(line) != 1 for line in required_environment_lines)
    ):
        raise LaunchAuditError("source-audit execution environment changed")
    return _sha256(SLURM_SCRIPT), manifest_sha, code


def _clean_repository_commit() -> str:
    try:
        changed = subprocess.check_output(
            ["jj", "--no-pager", "diff", "--summary", "-r", "@"],
            cwd=REPO,
            text=True,
        )
        commit_id = subprocess.check_output(
            [
                "jj", "--no-pager", "log", "-r", "@-", "--no-graph",
                "-T", 'commit_id ++ "\\n"',
            ],
            cwd=REPO,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot attest source-audit commit") from err
    if changed or JJ_COMMIT_RE.fullmatch(commit_id) is None:
        raise LaunchAuditError(
            "source-audit launch requires a clean committed working copy"
        )
    return commit_id


def _fixed_materials(
    source_inventory_sha256: str,
    repository_commit_id: str | None = None,
) -> dict:
    if not Source._is_sha256(source_inventory_sha256):
        raise LaunchAuditError("source inventory hash is invalid")
    slurm_sha, manifest_sha, code = _slurm_preflight()
    environment = _execution_environment(code)
    if repository_commit_id is None:
        repository_commit_id = _clean_repository_commit()
    if JJ_COMMIT_RE.fullmatch(repository_commit_id) is None:
        raise LaunchAuditError("source-audit repository commit is invalid")
    return {
        "partition": "fat",
        "qos": "normal",
        "account": ACCOUNT,
        "array": "0-819",
        "array_throttle": 0,
        "array_tasks": ARRAY_TASKS,
        "tasks_per_array_task": Source.TASKS_PER_SHARD,
        "candidates": Source.CANDIDATE_COUNT,
        "cpus_per_task": 1,
        "time_limit": "01:40:00",
        "memory_per_cpu": "26G",
        "task_timeout_seconds": Source.TASK_TIMEOUT_SECONDS,
        "benchmark_revision": Inventory.BENCHMARK_REVISION,
        "candidate_records_sha256": Inventory.CANDIDATE_RECORDS_SHA256,
        "alias_groups_sha256": Inventory.ALIAS_GROUPS_SHA256,
        "prior_identity_ledger_sha256": (
            Inventory.PRIOR_IDENTITY_LEDGER_SHA256
        ),
        "prior_family_ledger_sha256": Inventory.PRIOR_FAMILY_LEDGER_SHA256,
        "prior_directory_family_map_sha256": (
            Inventory.PRIOR_DIRECTORY_FAMILY_MAP_SHA256
        ),
        "shadow_unrepresented_family_sequence_sha256": (
            Inventory.SHADOW_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
        ),
        "all_prior_family_sequence_sha256": (
            Inventory.ALL_PRIOR_FAMILY_SEQUENCE_SHA256
        ),
        "all_prior_unrepresented_family_sequence_sha256": (
            Inventory.ALL_PRIOR_UNREPRESENTED_FAMILY_SEQUENCE_SHA256
        ),
        "translator_source_sha256": Source.TRANSLATOR_SOURCE_SHA256,
        "source_inventory_sha256": source_inventory_sha256,
        "source_inventory_path": str(SOURCE_INVENTORY),
        "slurm_script_sha256": slurm_sha,
        "code_manifest_sha256": manifest_sha,
        "launcher_sha256": _sha256(Path(__file__)),
        "repository_commit_id": repository_commit_id,
        "output_dir": str(OUTPUT_DIR),
        "candidate_attestation": str(CANDIDATE),
        "frozen_attestation": str(ATTESTATION),
        "execution_environment": environment,
        **{
            key: code[key]
            for key in (
                "python_version", "python_executable",
                "python_executable_sha256", "python_environment_sha256",
                "python_distributions", "python_requirements_sha256",
            )
        },
    }


def _submission_identity(token: str) -> tuple[str, str]:
    if not isinstance(token, str) or SUBMISSION_TOKEN_RE.fullmatch(token) is None:
        raise LaunchAuditError("source-audit submission token is invalid")
    return (
        "confirmation-source-audit-{}".format(token),
        "confirmation-source-audit/{}".format(token),
    )


def _submit_command(
    source_inventory_sha256: str,
    output_dir: Path,
    submission_token: str,
) -> list[str]:
    if not Source._is_sha256(source_inventory_sha256):
        raise LaunchAuditError("source inventory hash is invalid")
    job_name, comment = _submission_identity(submission_token)
    output_dir = Path(output_dir).resolve()
    return [
        "sbatch", "--parsable", "--export=NONE",
        "--job-name={}".format(job_name),
        "--comment={}".format(comment),
        str(SLURM_SCRIPT), source_inventory_sha256, str(output_dir),
    ]


def _write_launch_receipt(intent_raw: bytes, intent: dict, job_id: str) -> str:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise LaunchAuditError("Slurm returned an invalid source-audit job id")
    excluded = {
        "schema", "recorded_utc", "submission_token", "submit_command",
    }
    materials = {key: value for key, value in intent.items() if key not in excluded}
    receipt = {
        "schema": LAUNCH_SCHEMA,
        **materials,
        "recorded_utc": intent["recorded_utc"],
        "submission_token": intent["submission_token"],
        "submit_command": intent["submit_command"],
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": job_id,
    }
    return _exclusive_json(
        LAUNCH_RECEIPT, receipt, "source-audit launch receipt"
    )


def launch() -> None:
    if any(path.exists() for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR,
        CANDIDATE, ATTESTATION,
    )):
        raise LaunchAuditError("source-audit launch artifacts already exist")
    inventory = Inventory.load_inventory()
    source_inventory_value = Source.build_inventory_manifest(inventory)
    source_inventory_raw = Source.canonical_json(source_inventory_value)
    source_inventory_sha = hashlib.sha256(source_inventory_raw).hexdigest()
    materials = _fixed_materials(source_inventory_sha)
    submission_token = secrets.token_hex(12)
    recorded_utc = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(timespec="seconds")
    command = _submit_command(
        source_inventory_sha, OUTPUT_DIR, submission_token
    )
    intent = {
        "schema": LAUNCH_SCHEMA + "/intent",
        **materials,
        "recorded_utc": recorded_utc,
        "submission_token": submission_token,
        "submit_command": command,
    }
    _exclusive_json(INTENT, intent, "source-audit launch intent")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    _exclusive_bytes(
        SOURCE_INVENTORY,
        source_inventory_raw,
        "source inventory",
    )
    try:
        output = subprocess.check_output(command, cwd=REPO, text=True).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("source-audit sbatch failed after intent") from err
    job_id = output.split(";", 1)[0]
    digest = _write_launch_receipt(
        Source.canonical_json(intent), intent, job_id
    )
    print(json.dumps({
        "job_id": job_id,
        "launch_receipt_sha256": digest,
        "source_inventory_sha256": source_inventory_sha,
    }, sort_keys=True, indent=2))


def _load_intent_only() -> tuple[bytes, dict, dict]:
    intent_raw, intent = _load_json(INTENT, "source-audit launch intent")
    source_inventory_sha = intent.get("source_inventory_sha256")
    materials = _fixed_materials(
        source_inventory_sha,
        intent.get("repository_commit_id"),
    )
    token = intent.get("submission_token")
    recorded_utc = intent.get("recorded_utc")
    command = _submit_command(source_inventory_sha, OUTPUT_DIR, token)
    if (
        intent != {
            "schema": LAUNCH_SCHEMA + "/intent",
            **materials,
            "recorded_utc": recorded_utc,
            "submission_token": token,
            "submit_command": command,
        }
        or not isinstance(recorded_utc, str)
        or SUBMISSION_TOKEN_RE.fullmatch(token or "") is None
    ):
        raise LaunchAuditError("source-audit launch intent changed")
    Source.load_inventory_manifest(SOURCE_INVENTORY, source_inventory_sha)
    return intent_raw, intent, materials


def _load_launch() -> tuple[str, dict]:
    intent_raw, intent, materials = _load_intent_only()
    launch_raw, receipt = _load_json(
        LAUNCH_RECEIPT, "source-audit launch receipt"
    )
    if (
        receipt != {
            "schema": LAUNCH_SCHEMA,
            **materials,
            "recorded_utc": intent["recorded_utc"],
            "submission_token": intent["submission_token"],
            "submit_command": intent["submit_command"],
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": receipt.get("job_id"),
        }
        or not isinstance(receipt.get("job_id"), str)
        or not receipt["job_id"].isdigit()
    ):
        raise LaunchAuditError("source-audit launch provenance changed")
    return hashlib.sha256(launch_raw).hexdigest(), receipt


def _journal_job_ids(intent: dict) -> list[str]:
    job_name, comment = _submission_identity(intent["submission_token"])
    try:
        recorded = datetime.datetime.fromisoformat(intent["recorded_utc"])
    except (TypeError, ValueError) as err:
        raise LaunchAuditError("source-audit submission timestamp is invalid") from err
    if recorded.tzinfo is None:
        raise LaunchAuditError("source-audit submission timestamp has no timezone")
    command = [
        "sacct", "-X", "-S", recorded.date().isoformat(), "-n", "-P",
        "-o", JOURNAL_FIELDS,
    ]
    try:
        output = subprocess.check_output(command, text=True)
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot query source-audit submission journal") from err
    parents = set()
    indices_by_parent = {}
    expected_indices = set(range(ARRAY_TASKS))
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 3:
            raise LaunchAuditError("source-audit submission journal row changed")
        job_id, actual_name, actual_comment = fields
        if actual_name == job_name or actual_comment == comment:
            parent_match = re.fullmatch(r"([0-9]+)", job_id)
            array_match = re.fullmatch(r"([0-9]+)_([0-9]+)", job_id)
            if (
                actual_name != job_name
                or actual_comment != comment
                or (parent_match is None and array_match is None)
            ):
                raise LaunchAuditError("source-audit submission identity collided")
            parent = (parent_match or array_match).group(1)
            parents.add(parent)
            if array_match is not None:
                task = int(array_match.group(2))
                indices_by_parent.setdefault(parent, set()).add(task)
    if len(parents) > 1:
        raise LaunchAuditError("source-audit submission identity is not unique")
    if len(parents) == 1:
        parent = next(iter(parents))
        if indices_by_parent.get(parent, set()) != expected_indices:
            raise LaunchAuditError(
                "source-audit submission journal has an incomplete array"
            )
    return sorted(parents, key=int)


def recover_launch() -> None:
    if LAUNCH_RECEIPT.exists():
        raise LaunchAuditError("source-audit launch receipt already exists")
    intent_raw, intent, _ = _load_intent_only()
    jobs = _journal_job_ids(intent)
    if len(jobs) != 1:
        raise LaunchAuditError(
            "submission journal identifies {} source-audit jobs; refusing "
            "resubmission or guesswork".format(len(jobs))
        )
    digest = _write_launch_receipt(intent_raw, intent, jobs[0])
    print(json.dumps({
        "job_id": jobs[0],
        "launch_receipt_reconstructed": True,
        "launch_receipt_sha256": digest,
    }, sort_keys=True, indent=2))


def _scheduler_rows(
    job_id: str, expected_tasks: set[int] | None = None
) -> list[dict]:
    if expected_tasks is None:
        expected_tasks = set(range(ARRAY_TASKS))
    if (
        not expected_tasks
        or any(type(task) is not int or not 0 <= task < ARRAY_TASKS
               for task in expected_tasks)
    ):
        raise LaunchAuditError("source-audit expected task set is invalid")
    command = [
        "sacct", "-j", job_id, "-X", "-n", "-P",
        "-o", "JobID,State,ExitCode,Elapsed,Partition",
    ]
    try:
        output = subprocess.check_output(command, text=True)
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot query source-audit accounting") from err
    rows = {}
    prefix = job_id + "_"
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 5:
            raise LaunchAuditError("source-audit accounting row changed")
        array_id, state, exit_code, elapsed, partition = fields
        if not array_id.startswith(prefix):
            continue
        suffix = array_id[len(prefix):]
        if not suffix.isdigit():
            continue
        task = int(suffix)
        if task in rows or task not in expected_tasks or partition != "fat":
            raise LaunchAuditError("source-audit accounting identity changed")
        rows[task] = {
            "array_task": task,
            "state": state.split("+", 1)[0].split()[0],
            "exit_code": exit_code,
            "elapsed": elapsed,
            "partition": partition,
        }
    if set(rows) != expected_tasks:
        raise LaunchAuditError("source-audit accounting task set is incomplete")
    return [rows[index] for index in sorted(expected_tasks)]


def _output_tree(job_id: str) -> tuple[str, int]:
    expected = {
        SOURCE_INVENTORY,
        *{
            Source.shard_path(OUTPUT_DIR, index)
            for index in range(ARRAY_TASKS)
        },
        *{
            OUTPUT_DIR / "slurm-{}_{}.out".format(job_id, index)
            for index in range(ARRAY_TASKS)
        },
    }
    try:
        actual = set(OUTPUT_DIR.iterdir())
    except OSError as err:
        raise LaunchAuditError("cannot inspect source-audit output tree") from err
    if actual != expected:
        raise LaunchAuditError("source-audit output tree has unexpected paths")
    digest = hashlib.sha256()
    for path in sorted(expected):
        if path.is_symlink() or not path.is_file():
            raise LaunchAuditError("source-audit output is not regular")
        relative = path.relative_to(OUTPUT_DIR).as_posix().encode("ascii")
        digest.update(relative + b"\0" + bytes.fromhex(_sha256(path)))
    return digest.hexdigest(), len(expected)


def status() -> tuple[str, dict, list[dict]]:
    launch_sha, receipt = _load_launch()
    rows = _scheduler_rows(receipt["job_id"])
    print(json.dumps({
        "job_id": receipt["job_id"],
        "state_counts": dict(Counter(row["state"] for row in rows)),
    }, sort_keys=True, indent=2))
    return launch_sha, receipt, rows


def seal() -> None:
    import recover_pdb_terminal_incidence_confirmation_source_audit as Recovery

    if (
        EXECUTION_RECEIPT.exists()
        or CANDIDATE.exists()
        or ATTESTATION.exists()
        or Recovery.UNION_DIR.exists()
    ):
        raise LaunchAuditError("source-audit execution artifacts already exist")
    launch_sha, launch_receipt, rows = status()
    union = Recovery.prepare_union(launch_sha, launch_receipt, rows)
    Source.main([
        "assemble",
        "--shard-dir", str(Recovery.UNION_DIR),
        "--inventory-manifest", str(SOURCE_INVENTORY),
        "--inventory-sha256", launch_receipt["source_inventory_sha256"],
        "--num-shards", str(ARRAY_TASKS),
        "--output", str(CANDIDATE),
        "--code-manifest", str(CODE_MANIFEST),
        "--code-manifest-sha256", launch_receipt["code_manifest_sha256"],
    ])
    Recovery.verify_union(union, launch_receipt)
    candidate_raw, candidate = _load_json(
        CANDIDATE, "source-audit candidate attestation"
    )
    if (
        candidate.get("schema") != Source.SCHEMA
        or candidate.get("counts", {}).get("candidates")
        != Source.CANDIDATE_COUNT
        or candidate.get("counts", {}).get("translation_attempts")
        != Source.CANDIDATE_COUNT
        or candidate.get("confirmation_prelaunch_authorized")
        is not candidate.get("prelaunch_gate", {}).get("passed")
    ):
        raise LaunchAuditError("source-audit candidate identity changed")
    attestation_sha = _exclusive_bytes(
        ATTESTATION, candidate_raw, "frozen source-audit attestation"
    )
    receipt = {
        "schema": EXECUTION_SCHEMA,
        "launch_receipt_sha256": launch_sha,
        "job_id": launch_receipt["job_id"],
        "partition": "fat",
        "array_throttle": 0,
        "shards": ARRAY_TASKS,
        "candidates": Source.CANDIDATE_COUNT,
        "scheduler_state_counts": dict(Counter(
            row["state"] for row in rows
        )),
        "scheduler_rows": rows,
        "original_output_tree": union["original_output_tree"],
        "recovery": union["recovery"],
        "union_sources": union["sources"],
        "union_tree": union["union_tree"],
        "code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "source_inventory_sha256": launch_receipt[
            "source_inventory_sha256"
        ],
        "execution_environment": launch_receipt["execution_environment"],
        "source_audit_complete": True,
        "confirmation_prelaunch_authorized": candidate[
            "confirmation_prelaunch_authorized"
        ],
        "prelaunch_gate": candidate["prelaunch_gate"],
        "attestation_sha256": attestation_sha,
        "attestation_records_sha256": candidate["records_sha256"],
        "cohort_manifest_sha256": {
            name: cohort["tasks_sha256"]
            for name, cohort in candidate["cohorts"].items()
        },
        "counts": candidate["counts"],
        "translation_status_counts": candidate["translation_status_counts"],
        "support_exclusion_counts": candidate["support_exclusion_counts"],
    }
    digest = _exclusive_json(
        EXECUTION_RECEIPT, receipt, "source-audit execution receipt"
    )
    print(json.dumps({
        "attestation_sha256": attestation_sha,
        "confirmation_prelaunch_authorized": candidate[
            "confirmation_prelaunch_authorized"
        ],
        "execution_receipt_sha256": digest,
        "union_tree_sha256": union["union_tree"]["sha256"],
    }, sort_keys=True, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=("launch", "recover-launch", "status", "seal")
    )
    args = parser.parse_args(argv)
    {
        "launch": launch,
        "recover-launch": recover_launch,
        "status": status,
        "seal": seal,
    }[args.command]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        LaunchAuditError,
        Source.SourceAuditError,
        Inventory.InventoryError,
    ) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
