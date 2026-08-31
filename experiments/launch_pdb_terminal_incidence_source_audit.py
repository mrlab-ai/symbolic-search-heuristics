#!/usr/bin/env python3
"""Launch and seal the provenance-complete terminal-incidence source audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import audit_pdb_terminal_incidence_sources as Source
import pdb_terminal_incidence_shadow_protocol as P


class LaunchAuditError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
SLURM_SCRIPT = SCRIPT_DIR / "pdb_terminal_incidence_source_scan.slurm"
CODE_MANIFEST = (
    SCRIPT_DIR / "pdb_terminal_incidence_source_audit_code.sha256"
)
OUTPUT_DIR = SCRIPT_DIR / "data" / "pdb_terminal_incidence_source_audit_v3"
CANDIDATE = (
    SCRIPT_DIR / "data" / "pdb_terminal_incidence_source_audit_v3_candidate.json"
)
ARTIFACT_DIR = SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-shadow"
INTENT = ARTIFACT_DIR / "source-audit-launch-intent-v3.json"
LAUNCH_RECEIPT = ARTIFACT_DIR / "source-audit-launch-receipt-v3.json"
EXECUTION_RECEIPT = ARTIFACT_DIR / "source-audit-execution-receipt-v3.json"
LAUNCH_SCHEMA = (
    "symbolic-search-heuristics/pdb-terminal-incidence-source-audit-launch/v3"
)
EXECUTION_SCHEMA = (
    "symbolic-search-heuristics/pdb-terminal-incidence-source-audit-execution/v3"
)
ARRAY_TASKS = 46
CONTROLLED_PATH = "/usr/bin:/bin"
UNSET_PYTHON_ENV = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV")
PYTHON_COMMAND = (
    REPO
    / "experiments"
    / "data"
    / "pdb-terminal-incidence-shadow-venv"
    / "bin"
    / "python"
)
SHA256SUM_COMMAND = Path("/usr/bin/sha256sum")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
JJ_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
MANIFEST_ASSIGNMENT_RE = re.compile(
    r'^code_manifest_sha256="([0-9a-f]{64})"$'
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical(value) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii") + b"\n"


def _exclusive_json(path: Path, value, label: str) -> str:
    raw = _canonical(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise LaunchAuditError("{} already exists".format(label)) from err
    return hashlib.sha256(raw).hexdigest()


def _load_json(path: Path, label: str) -> tuple[bytes, dict]:
    if path.is_symlink() or not path.is_file():
        raise LaunchAuditError("{} is not a regular file".format(label))
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("ascii"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as err:
        raise LaunchAuditError("cannot load {}".format(label)) from err
    if not isinstance(value, dict) or raw != _canonical(value):
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
        "path": CONTROLLED_PATH,
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
    content = SLURM_SCRIPT.read_text(encoding="ascii")
    lines = content.splitlines()
    required = {
        "#SBATCH --job-name=terminal-incidence-source-audit",
        "#SBATCH --account=naiss2025-5-561-cpu",
        "#SBATCH --partition=fat",
        "#SBATCH --qos=normal",
        "#SBATCH --array=0-45",
        "#SBATCH --cpus-per-task=1",
        "#SBATCH --mem-per-cpu=8G",
        "#SBATCH --time=00:30:00",
        "#SBATCH --output={}/slurm-%A_%a.out".format(OUTPUT_DIR),
        "#SBATCH --export=NONE",
    }
    if not required <= set(lines):
        raise LaunchAuditError("source-audit Slurm header changed")
    prefixes = (
        "#SBATCH --job-name=",
        "#SBATCH --account=",
        "#SBATCH --partition=",
        "#SBATCH --qos=",
        "#SBATCH --array=",
        "#SBATCH --cpus-per-task=",
        "#SBATCH --mem-per-cpu=",
        "#SBATCH --time=",
        "#SBATCH --output=",
        "#SBATCH --export=",
    )
    if any(sum(line.startswith(prefix) for line in lines) != 1
           for prefix in prefixes):
        raise LaunchAuditError("source-audit Slurm directives conflict")
    array_line = next(line for line in lines if line.startswith("#SBATCH --array="))
    if "%" in array_line:
        raise LaunchAuditError("source-audit array has a throttle")
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
        'export PATH="{}"'.format(CONTROLLED_PATH),
        'python_executable="{}"'.format(PYTHON_COMMAND),
        'python_executable_sha256="{}"'.format(
            environment["python_executable_sha256"]
        ),
        'sha256sum_executable="{}"'.format(SHA256SUM_COMMAND),
        'sha256sum_executable_sha256="{}"'.format(
            environment["sha256sum_executable_sha256"]
        ),
        'exec "${python_executable}" \\',
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
            ["jj", "diff", "--summary"], cwd=REPO, text=True
        )
        commit_id = subprocess.check_output(
            [
                "jj", "log", "-r", "@-", "--no-graph",
                "-T", 'commit_id ++ "\\n"',
            ],
            cwd=REPO,
            text=True,
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("cannot attest the source-audit commit") from err
    if changed or JJ_COMMIT_RE.fullmatch(commit_id) is None:
        raise LaunchAuditError(
            "source-audit launch requires a clean committed working copy"
        )
    return commit_id


def _fixed_materials(repository_commit_id: str | None = None) -> dict:
    slurm_sha, manifest_sha, code = _slurm_preflight()
    environment = _execution_environment(code)
    if repository_commit_id is None:
        repository_commit_id = _clean_repository_commit()
    if JJ_COMMIT_RE.fullmatch(repository_commit_id) is None:
        raise LaunchAuditError("source-audit repository commit is invalid")
    return {
        "partition": "fat",
        "qos": "normal",
        "account": P.ACCOUNT,
        "array": "0-45",
        "array_throttle": 0,
        "array_tasks": ARRAY_TASKS,
        "cpus_per_task": 1,
        "time_limit": "00:30:00",
        "memory_per_cpu": "8G",
        "benchmark_revision": P.BENCHMARK_REVISION,
        "cohort_manifest_sha256": P.COHORT_MANIFEST_SHA256,
        "translator_source_sha256": P.TRANSLATOR_SOURCE_SHA256,
        "slurm_script_sha256": slurm_sha,
        "code_manifest_sha256": manifest_sha,
        "launcher_sha256": _sha256(Path(__file__)),
        "repository_commit_id": repository_commit_id,
        "output_dir": str(OUTPUT_DIR),
        "candidate_attestation": str(CANDIDATE),
        "execution_environment": environment,
        **{key: code[key] for key in (
            "python_version",
            "python_executable",
            "python_executable_sha256",
            "python_environment_sha256",
            "python_distributions",
            "python_requirements_sha256",
        )},
    }


def _submit_command() -> list[str]:
    return ["sbatch", "--parsable", "--export=NONE", str(SLURM_SCRIPT)]


def launch() -> None:
    if any(path.exists() for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT, OUTPUT_DIR, CANDIDATE
    )):
        raise LaunchAuditError("source-audit launch artifacts already exist")
    materials = _fixed_materials()
    command = _submit_command()
    intent = {
        "schema": LAUNCH_SCHEMA + "/intent",
        **materials,
        "submit_command": command,
    }
    intent_sha = _exclusive_json(INTENT, intent, "source-audit launch intent")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    try:
        output = subprocess.check_output(command, cwd=REPO, text=True).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise LaunchAuditError("source-audit sbatch failed after intent") from err
    job_id = output.split(";", 1)[0]
    if not job_id.isdigit():
        raise LaunchAuditError("Slurm returned an invalid source-audit job id")
    receipt = {
        "schema": LAUNCH_SCHEMA,
        **materials,
        "submit_command": command,
        "launch_intent_sha256": intent_sha,
        "job_id": job_id,
    }
    digest = _exclusive_json(
        LAUNCH_RECEIPT, receipt, "source-audit launch receipt"
    )
    print(json.dumps({
        "job_id": job_id,
        "launch_receipt_sha256": digest,
    }, sort_keys=True, indent=2))


def _load_launch() -> tuple[str, dict]:
    intent_raw, intent = _load_json(INTENT, "source-audit launch intent")
    launch_raw, receipt = _load_json(
        LAUNCH_RECEIPT, "source-audit launch receipt"
    )
    repository_commit_id = intent.get("repository_commit_id")
    materials = _fixed_materials(repository_commit_id)
    command = _submit_command()
    expected_intent = {
        "schema": LAUNCH_SCHEMA + "/intent",
        **materials,
        "submit_command": command,
    }
    if (
        intent != expected_intent
        or receipt != {
            "schema": LAUNCH_SCHEMA,
            **materials,
            "submit_command": command,
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": receipt.get("job_id"),
        }
        or not isinstance(receipt.get("job_id"), str)
        or not receipt["job_id"].isdigit()
    ):
        raise LaunchAuditError("source-audit launch provenance changed")
    return hashlib.sha256(launch_raw).hexdigest(), receipt


def _scheduler_rows(job_id: str) -> list[dict]:
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
        if task in rows or not 0 <= task < ARRAY_TASKS or partition != "fat":
            raise LaunchAuditError("source-audit accounting identity changed")
        rows[task] = {
            "array_task": task,
            "state": state.split("+", 1)[0].split()[0],
            "exit_code": exit_code,
            "elapsed": elapsed,
            "partition": partition,
        }
    if set(rows) != set(range(ARRAY_TASKS)):
        raise LaunchAuditError("source-audit accounting task set is incomplete")
    return [rows[index] for index in range(ARRAY_TASKS)]


def _output_tree(job_id: str) -> tuple[str, int]:
    expected = {
        Source.shard_path(OUTPUT_DIR, index, ARRAY_TASKS)
        for index in range(ARRAY_TASKS)
    } | {
        OUTPUT_DIR / "slurm-{}_{}.out".format(job_id, index)
        for index in range(ARRAY_TASKS)
    }
    actual = set(OUTPUT_DIR.iterdir())
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
    if EXECUTION_RECEIPT.exists() or CANDIDATE.exists():
        raise LaunchAuditError("source-audit execution artifacts already exist")
    launch_sha, launch_receipt, rows = status()
    if any(row["state"] != "COMPLETED" or row["exit_code"] != "0:0"
           for row in rows):
        raise LaunchAuditError("source-audit array is not entirely successful")
    tree_sha, tree_files = _output_tree(launch_receipt["job_id"])
    Source.main([
        "assemble",
        "--shard-dir", str(OUTPUT_DIR),
        "--num-shards", str(ARRAY_TASKS),
        "--output", str(CANDIDATE),
        "--code-manifest", str(CODE_MANIFEST),
        "--code-manifest-sha256", launch_receipt["code_manifest_sha256"],
    ])
    sealed_tree_sha, sealed_tree_files = _output_tree(launch_receipt["job_id"])
    if (sealed_tree_sha, sealed_tree_files) != (tree_sha, tree_files):
        raise LaunchAuditError(
            "source-audit output tree changed while assembling"
        )
    if CANDIDATE.read_bytes() != P.COST_ATTESTATION_PATH.read_bytes():
        raise LaunchAuditError("source-audit candidate differs from frozen attestation")
    candidate = json.loads(CANDIDATE.read_text(encoding="ascii"))
    receipt = {
        "schema": EXECUTION_SCHEMA,
        "launch_receipt_sha256": launch_sha,
        "job_id": launch_receipt["job_id"],
        "partition": "fat",
        "array_throttle": 0,
        "shards": ARRAY_TASKS,
        "scheduler_state_counts": {"COMPLETED": ARRAY_TASKS},
        "scheduler_rows": rows,
        "output_tree_sha256": tree_sha,
        "output_tree_files": tree_files,
        "code_manifest_sha256": launch_receipt["code_manifest_sha256"],
        "execution_environment": launch_receipt["execution_environment"],
        "source_audit_passed": True,
        "attestation_sha256": _sha256(CANDIDATE),
        "attestation_records_sha256": candidate["records_sha256"],
        "counts": candidate["counts"],
    }
    digest = _exclusive_json(
        EXECUTION_RECEIPT, receipt, "source-audit execution receipt"
    )
    print(json.dumps({
        "execution_receipt_sha256": digest,
        "output_tree_sha256": tree_sha,
    }, sort_keys=True, indent=2))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("launch", "status", "seal"))
    args = parser.parse_args(argv)
    {"launch": launch, "status": status, "seal": seal}[args.command]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (LaunchAuditError, Source.SourceAuditError, P.ProtocolError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
