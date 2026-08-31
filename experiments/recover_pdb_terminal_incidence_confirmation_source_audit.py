#!/usr/bin/env python3
"""Recover scheduler-interrupted universal confirmation source-audit shards."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import secrets
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_pdb_terminal_incidence_confirmation_sources as Source
import launch_pdb_terminal_incidence_confirmation_source_audit as Launch


class RecoveryError(RuntimeError):
    pass


SCHEMA = Source.SCHEMA + "/recovery/v1"
WAVE = 1
RECOVERY_ROOT = Launch.ARTIFACT_DIR / "recovery"
WAVE_DIR = RECOVERY_ROOT / "wave-0001"
INTENT = WAVE_DIR / "launch-intent.json"
LAUNCH_RECEIPT = WAVE_DIR / "launch-receipt.json"
EXECUTION_RECEIPT = WAVE_DIR / "execution-receipt.json"
DATA_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_recovery_v1"
)
OUTPUT_DIR = DATA_ROOT / "wave-0001"
UNION_DIR = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_union_v1"
)
INFRASTRUCTURE_STATES = frozenset({
    "BOOT_FAIL", "NODE_FAIL", "PREEMPTED", "REVOKED",
})
ACTIVE_STATES = frozenset({
    "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
    "RESIZING", "SUSPENDED",
})


def _exclusive_json(path: Path, value, label: str) -> str:
    return Launch._exclusive_json(path, value, label)


def _load_json(path: Path, label: str) -> tuple[bytes, dict]:
    return Launch._load_json(path, label)


def _tree_digest(root: Path, paths: set[Path]) -> dict:
    digest = hashlib.sha256()
    records = []
    for path in sorted(paths):
        if path.is_symlink() or not path.is_file():
            raise RecoveryError("source-audit tree contains a non-regular file")
        relative = path.relative_to(root).as_posix()
        sha256 = Launch._sha256(path)
        size = path.stat().st_size
        digest.update(relative.encode("ascii") + b"\0" + bytes.fromhex(sha256))
        records.append({"path": relative, "size": size, "sha256": sha256})
    return {
        "sha256": digest.hexdigest(),
        "files_count": len(records),
        "files": records,
    }


def _classify_rows(rows: list[dict]) -> tuple[list[int], list[int]]:
    successful = []
    recoverable = []
    for row in rows:
        task = row["array_task"]
        state = row["state"]
        exit_code = row["exit_code"]
        if state == "COMPLETED" and exit_code == "0:0":
            successful.append(task)
        elif state in INFRASTRUCTURE_STATES:
            recoverable.append(task)
        elif state in ACTIVE_STATES:
            raise RecoveryError("original source-audit array is not terminal")
        else:
            raise RecoveryError(
                "original shard {} has unrecognized or application failure "
                "{} {}; recovery is forbidden".format(task, state, exit_code)
            )
    if sorted(successful + recoverable) != list(range(Source.SHARD_COUNT)):
        raise RecoveryError("original source-audit task partition changed")
    return successful, recoverable


def _original_output_tree(
    launch: dict, rows: list[dict], successful: list[int], recoverable: list[int]
) -> tuple[dict, list[int], list[int]]:
    required = {Launch.SOURCE_INVENTORY}
    allowed = {Launch.SOURCE_INVENTORY}
    for task in successful:
        shard = Source.shard_path(Launch.OUTPUT_DIR, task)
        log = Launch.OUTPUT_DIR / "slurm-{}_{}.out".format(
            launch["job_id"], task
        )
        required.update((shard, log))
        allowed.update((shard, log))
    for task in recoverable:
        allowed.add(Source.shard_path(Launch.OUTPUT_DIR, task))
        allowed.add(Launch.OUTPUT_DIR / "slurm-{}_{}.out".format(
            launch["job_id"], task
        ))
    try:
        actual = set(Launch.OUTPUT_DIR.iterdir())
    except OSError as err:
        raise RecoveryError("cannot inspect original source-audit tree") from err
    if not required <= actual or not actual <= allowed:
        raise RecoveryError("original source-audit output tree is incomplete or changed")
    missing_shards = [
        task for task in recoverable
        if Source.shard_path(Launch.OUTPUT_DIR, task) not in actual
    ]
    existing_interrupted_shards = [
        task for task in recoverable if task not in missing_shards
    ]
    return (
        _tree_digest(Launch.OUTPUT_DIR, actual),
        missing_shards,
        existing_interrupted_shards,
    )


def _plan() -> dict:
    if Launch.EXECUTION_RECEIPT.exists():
        raise RecoveryError("main source audit is already sealed")
    launch_sha, launch = Launch._load_launch()
    rows = Launch._scheduler_rows(launch["job_id"])
    successful, recoverable = _classify_rows(rows)
    tree, missing, existing = _original_output_tree(
        launch, rows, successful, recoverable
    )
    return {
        "source_launch_receipt_sha256": launch_sha,
        "source_job_id": launch["job_id"],
        "source_inventory_sha256": launch["source_inventory_sha256"],
        "code_manifest_sha256": launch["code_manifest_sha256"],
        "slurm_script_sha256": launch["slurm_script_sha256"],
        "repository_commit_id": launch["repository_commit_id"],
        "original_scheduler_rows": rows,
        "original_output_tree": tree,
        "original_successful_shards": successful,
        "recoverable_shards": recoverable,
        "missing_shard_indices": missing,
        "existing_interrupted_shard_indices": existing,
    }


def _submission_identity(token: str) -> tuple[str, str]:
    if (
        not isinstance(token, str)
        or Launch.SUBMISSION_TOKEN_RE.fullmatch(token) is None
    ):
        raise RecoveryError("recovery submission token is invalid")
    return (
        "confirmation-source-recovery-{}".format(token),
        "confirmation-source-recovery/{}".format(token),
    )


def _array_spec(tasks: list[int]) -> str:
    if (
        not tasks
        or tasks != sorted(set(tasks))
        or any(type(task) is not int or not 0 <= task < Source.SHARD_COUNT
               for task in tasks)
    ):
        raise RecoveryError("recovery task set is invalid")
    value = ",".join(map(str, tasks))
    if "%" in value:
        raise RecoveryError("recovery array is throttled")
    return value


def _submit_command(plan: dict, token: str) -> list[str]:
    tasks = plan["recoverable_shards"]
    array_spec = _array_spec(tasks)
    job_name, comment = _submission_identity(token)
    return [
        "sbatch", "--parsable", "--export=NONE",
        "--array={}".format(array_spec),
        "--job-name={}".format(job_name),
        "--comment={}".format(comment),
        "--account={}".format(Launch.ACCOUNT),
        "--partition=fat", "--qos=normal", "--cpus-per-task=1",
        "--mem-per-cpu=26G", "--time=01:40:00",
        "--output={}".format((OUTPUT_DIR / "slurm-%A_%a.out").resolve()),
        str(Launch.SLURM_SCRIPT),
        plan["source_inventory_sha256"], str(OUTPUT_DIR.resolve()),
    ]


def preview() -> None:
    plan = _plan()
    print(json.dumps({
        "mode": "preview",
        "array_throttle": 0,
        "partition": "fat",
        "qos": "normal",
        **plan,
    }, sort_keys=True, indent=2))


def _intent_value(plan: dict, token: str, recorded_utc: str) -> dict:
    return {
        "schema": SCHEMA + "/launch/intent",
        "wave": WAVE,
        **plan,
        "recorded_utc": recorded_utc,
        "submission_token": token,
        "array_spec": _array_spec(plan["recoverable_shards"]),
        "array_throttle": 0,
        "partition": "fat",
        "qos": "normal",
        "account": Launch.ACCOUNT,
        "cpus_per_task": 1,
        "memory_per_cpu": "26G",
        "time_limit": "01:40:00",
        "task_timeout_seconds": Source.TASK_TIMEOUT_SECONDS,
        "output_dir": str(OUTPUT_DIR),
        "submit_command": _submit_command(plan, token),
    }


def _write_launch_receipt(intent_raw: bytes, intent: dict, job_id: str) -> str:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise RecoveryError("Slurm returned an invalid recovery job id")
    receipt = {
        "schema": SCHEMA + "/launch",
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": job_id,
    }
    return _exclusive_json(LAUNCH_RECEIPT, receipt, "recovery launch receipt")


def launch() -> None:
    if any(path.exists() for path in (
        RECOVERY_ROOT, DATA_ROOT, UNION_DIR, Launch.EXECUTION_RECEIPT,
    )):
        raise RecoveryError("recovery artifacts already exist")
    plan = _plan()
    if not plan["recoverable_shards"]:
        print(json.dumps({
            "recoverable_shards": [],
            "note": "no scheduler-interrupted source-audit shard needs recovery",
        }, sort_keys=True, indent=2))
        return
    token = secrets.token_hex(12)
    recorded_utc = datetime.datetime.now(
        datetime.timezone.utc
    ).isoformat(timespec="seconds")
    intent = _intent_value(plan, token, recorded_utc)
    WAVE_DIR.mkdir(parents=True, exist_ok=False)
    intent_raw = Source.canonical_json(intent)
    _exclusive_json(INTENT, intent, "recovery launch intent")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=False)
    try:
        output = subprocess.check_output(
            intent["submit_command"], cwd=Launch.REPO, text=True
        ).strip()
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("recovery sbatch failed after intent") from err
    job_id = output.split(";", 1)[0]
    digest = _write_launch_receipt(intent_raw, intent, job_id)
    print(json.dumps({
        "job_id": job_id,
        "launch_receipt_sha256": digest,
        "recoverable_shards": plan["recoverable_shards"],
    }, sort_keys=True, indent=2))


def _load_intent_only() -> tuple[bytes, dict, dict]:
    raw, intent = _load_json(INTENT, "recovery launch intent")
    plan = _plan()
    token = intent.get("submission_token")
    recorded_utc = intent.get("recorded_utc")
    expected = _intent_value(plan, token, recorded_utc)
    if (
        intent != expected
        or not isinstance(recorded_utc, str)
        or Launch.SUBMISSION_TOKEN_RE.fullmatch(token or "") is None
        or not OUTPUT_DIR.is_dir()
    ):
        raise RecoveryError("recovery launch intent changed")
    return raw, intent, plan


def _load_launch() -> tuple[str, dict, dict]:
    intent_raw, intent, plan = _load_intent_only()
    raw, receipt = _load_json(LAUNCH_RECEIPT, "recovery launch receipt")
    expected = {
        "schema": SCHEMA + "/launch",
        **{key: value for key, value in intent.items() if key != "schema"},
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": receipt.get("job_id"),
    }
    if (
        receipt != expected
        or not isinstance(receipt.get("job_id"), str)
        or not receipt["job_id"].isdigit()
    ):
        raise RecoveryError("recovery launch receipt changed")
    return hashlib.sha256(raw).hexdigest(), receipt, plan


def _journal_job_ids(intent: dict) -> list[str]:
    job_name, comment = _submission_identity(intent["submission_token"])
    try:
        recorded = datetime.datetime.fromisoformat(intent["recorded_utc"])
    except (TypeError, ValueError) as err:
        raise RecoveryError("recovery timestamp is invalid") from err
    if recorded.tzinfo is None:
        raise RecoveryError("recovery timestamp has no timezone")
    command = [
        "sacct", "-X", "-S", recorded.date().isoformat(), "-n", "-P",
        "-o", Launch.JOURNAL_FIELDS,
    ]
    try:
        output = subprocess.check_output(command, text=True)
    except (OSError, subprocess.CalledProcessError) as err:
        raise RecoveryError("cannot query recovery submission journal") from err
    parents = set()
    indices_by_parent = {}
    expected_indices = set(intent["recoverable_shards"])
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 3:
            raise RecoveryError("recovery submission journal row changed")
        job_id, actual_name, actual_comment = fields
        if actual_name == job_name or actual_comment == comment:
            parent_match = re.fullmatch(r"([0-9]+)", job_id)
            array_match = re.fullmatch(r"([0-9]+)_([0-9]+)", job_id)
            if (
                actual_name != job_name
                or actual_comment != comment
                or (parent_match is None and array_match is None)
            ):
                raise RecoveryError("recovery submission identity collided")
            parent = (parent_match or array_match).group(1)
            parents.add(parent)
            if array_match is not None:
                task = int(array_match.group(2))
                indices_by_parent.setdefault(parent, set()).add(task)
    if len(parents) > 1:
        raise RecoveryError("recovery submission identity is not unique")
    if len(parents) == 1:
        parent = next(iter(parents))
        if indices_by_parent.get(parent, set()) != expected_indices:
            raise RecoveryError("recovery submission journal has an incomplete array")
    return sorted(parents, key=int)


def recover_launch() -> None:
    if LAUNCH_RECEIPT.exists():
        raise RecoveryError("recovery launch receipt already exists")
    intent_raw, intent, _ = _load_intent_only()
    jobs = _journal_job_ids(intent)
    if len(jobs) != 1:
        raise RecoveryError(
            "submission journal identifies {} recovery jobs; refusing "
            "resubmission or guesswork".format(len(jobs))
        )
    digest = _write_launch_receipt(intent_raw, intent, jobs[0])
    print(json.dumps({
        "job_id": jobs[0],
        "launch_receipt_reconstructed": True,
        "launch_receipt_sha256": digest,
    }, sort_keys=True, indent=2))


def _output_tree(receipt: dict) -> dict:
    tasks = receipt["recoverable_shards"]
    expected = {
        *{Source.shard_path(OUTPUT_DIR, task) for task in tasks},
        *{
            OUTPUT_DIR / "slurm-{}_{}.out".format(receipt["job_id"], task)
            for task in tasks
        },
    }
    try:
        actual = set(OUTPUT_DIR.iterdir())
    except OSError as err:
        raise RecoveryError("cannot inspect recovery output tree") from err
    if actual != expected:
        raise RecoveryError("recovery output tree is incomplete or changed")
    return _tree_digest(OUTPUT_DIR, actual)


def _code_header(source_launch: dict) -> dict:
    return {
        key: source_launch[key]
        for key in (
            "code_manifest_sha256", "python_version", "python_executable",
            "python_executable_sha256", "python_environment_sha256",
            "python_distributions", "python_requirements_sha256",
        )
    }


def _validate_recovery_shards(receipt: dict, source_launch: dict) -> None:
    _, inventory_records = Source.load_inventory_manifest(
        Launch.SOURCE_INVENTORY, receipt["source_inventory_sha256"]
    )
    code = _code_header(source_launch)
    for task in receipt["recoverable_shards"]:
        start = task * Source.TASKS_PER_SHARD
        Source._load_shard(
            Source.shard_path(OUTPUT_DIR, task),
            task,
            inventory_records[start:start + Source.TASKS_PER_SHARD],
            receipt["source_inventory_sha256"],
            code,
        )


def status() -> tuple[str, dict, dict, list[dict]]:
    launch_sha, receipt, plan = _load_launch()
    rows = Launch._scheduler_rows(
        receipt["job_id"], set(receipt["recoverable_shards"])
    )
    print(json.dumps({
        "job_id": receipt["job_id"],
        "rows": rows,
    }, sort_keys=True, indent=2))
    return launch_sha, receipt, plan, rows


def seal() -> None:
    if EXECUTION_RECEIPT.exists():
        raise RecoveryError("recovery execution receipt already exists")
    launch_sha, receipt, plan, rows = status()
    if any(
        row["state"] != "COMPLETED" or row["exit_code"] != "0:0"
        for row in rows
    ):
        raise RecoveryError("recovery array is not entirely successful")
    tree = _output_tree(receipt)
    _, source_launch = Launch._load_launch()
    _validate_recovery_shards(receipt, source_launch)
    if _output_tree(receipt) != tree or _plan() != plan:
        raise RecoveryError("source or recovery tree changed while sealing")
    value = {
        "schema": SCHEMA + "/execution",
        "wave": WAVE,
        "source_launch_receipt_sha256": plan[
            "source_launch_receipt_sha256"
        ],
        "recovery_launch_receipt_sha256": launch_sha,
        "source_job_id": plan["source_job_id"],
        "job_id": receipt["job_id"],
        "recoverable_shards": receipt["recoverable_shards"],
        "missing_shard_indices": receipt["missing_shard_indices"],
        "array_throttle": 0,
        "partition": "fat",
        "scheduler_rows": rows,
        "output_tree": tree,
        "source_inventory_sha256": receipt["source_inventory_sha256"],
        "code_manifest_sha256": receipt["code_manifest_sha256"],
        "original_scheduler_rows": receipt["original_scheduler_rows"],
        "original_output_tree": receipt["original_output_tree"],
    }
    digest = _exclusive_json(
        EXECUTION_RECEIPT, value, "recovery execution receipt"
    )
    print(json.dumps({
        "execution_receipt_sha256": digest,
        "output_tree_sha256": tree["sha256"],
    }, sort_keys=True, indent=2))


def load_execution() -> tuple[str, dict, dict] | None:
    if not RECOVERY_ROOT.exists():
        if DATA_ROOT.exists():
            raise RecoveryError("orphan recovery data directory exists")
        return None
    if set(RECOVERY_ROOT.iterdir()) != {WAVE_DIR}:
        raise RecoveryError("recovery wave set changed")
    if not all(path.is_file() for path in (
        INTENT, LAUNCH_RECEIPT, EXECUTION_RECEIPT,
    )):
        raise RecoveryError("recovery wave is unresolved")
    launch_sha, receipt, plan = _load_launch()
    raw, execution = _load_json(EXECUTION_RECEIPT, "recovery execution receipt")
    rows = Launch._scheduler_rows(
        receipt["job_id"], set(receipt["recoverable_shards"])
    )
    tree = _output_tree(receipt)
    expected = {
        "schema": SCHEMA + "/execution",
        "wave": WAVE,
        "source_launch_receipt_sha256": plan[
            "source_launch_receipt_sha256"
        ],
        "recovery_launch_receipt_sha256": launch_sha,
        "source_job_id": plan["source_job_id"],
        "job_id": receipt["job_id"],
        "recoverable_shards": receipt["recoverable_shards"],
        "missing_shard_indices": receipt["missing_shard_indices"],
        "array_throttle": 0,
        "partition": "fat",
        "scheduler_rows": rows,
        "output_tree": tree,
        "source_inventory_sha256": receipt["source_inventory_sha256"],
        "code_manifest_sha256": receipt["code_manifest_sha256"],
        "original_scheduler_rows": receipt["original_scheduler_rows"],
        "original_output_tree": receipt["original_output_tree"],
    }
    if execution != expected:
        raise RecoveryError("recovery execution receipt changed")
    _, source_launch = Launch._load_launch()
    _validate_recovery_shards(receipt, source_launch)
    return hashlib.sha256(raw).hexdigest(), execution, plan


def _copy_exclusive(source: Path, target: Path) -> dict:
    if source.is_symlink() or not source.is_file():
        raise RecoveryError("union source shard is not regular")
    raw = source.read_bytes()
    try:
        Source.atomic_exclusive_bytes(target, raw, "union shard")
    except Source.SourceAuditError as err:
        raise RecoveryError("duplicate or invalid union shard") from err
    return {
        "source": str(source),
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "union": target.name,
        "union_sha256": Launch._sha256(target),
    }


def prepare_union(
    source_launch_sha: str, source_launch: dict, original_rows: list[dict]
) -> dict:
    if UNION_DIR.exists():
        raise RecoveryError("source-audit union directory already exists")
    successful, recoverable = _classify_rows(original_rows)
    original_tree, missing, existing = _original_output_tree(
        source_launch, original_rows, successful, recoverable
    )
    loaded = load_execution()
    if recoverable and loaded is None:
        raise RecoveryError("scheduler-interrupted shards lack sealed recovery")
    if not recoverable and loaded is not None:
        raise RecoveryError("unneeded recovery execution exists")
    recovery = None
    if loaded is not None:
        recovery_sha, recovery_execution, plan = loaded
        if (
            plan["source_launch_receipt_sha256"] != source_launch_sha
            or plan["recoverable_shards"] != recoverable
            or plan["missing_shard_indices"] != missing
            or plan["existing_interrupted_shard_indices"] != existing
            or plan["original_scheduler_rows"] != original_rows
            or plan["original_output_tree"] != original_tree
        ):
            raise RecoveryError("recovery does not match original execution")
        recovery = {
            "execution_receipt_sha256": recovery_sha,
            "execution": recovery_execution,
        }
    UNION_DIR.mkdir(parents=True, exist_ok=False)
    sources = []
    recoverable_set = set(recoverable)
    for task in range(Source.SHARD_COUNT):
        if task in recoverable_set:
            source = Source.shard_path(OUTPUT_DIR, task)
            origin = "recovery"
        else:
            source = Source.shard_path(Launch.OUTPUT_DIR, task)
            origin = "original"
        target = Source.shard_path(UNION_DIR, task)
        item = _copy_exclusive(source, target)
        sources.append({"shard_index": task, "origin": origin, **item})
    union_tree = _tree_digest(UNION_DIR, set(UNION_DIR.iterdir()))
    return {
        "source_launch_receipt_sha256": source_launch_sha,
        "original_scheduler_rows": original_rows,
        "original_output_tree": original_tree,
        "recovery": recovery,
        "sources": sources,
        "union_tree": union_tree,
    }


def verify_union(context: dict, source_launch: dict) -> None:
    successful, recoverable = _classify_rows(context["original_scheduler_rows"])
    original_tree, _, _ = _original_output_tree(
        source_launch, context["original_scheduler_rows"], successful, recoverable
    )
    if original_tree != context["original_output_tree"]:
        raise RecoveryError("original output tree changed after union")
    loaded = load_execution()
    if context["recovery"] is None:
        if loaded is not None:
            raise RecoveryError("recovery appeared after union")
    else:
        if loaded is None or loaded[0] != context["recovery"][
            "execution_receipt_sha256"
        ]:
            raise RecoveryError("recovery changed after union")
    if _tree_digest(UNION_DIR, set(UNION_DIR.iterdir())) != context["union_tree"]:
        raise RecoveryError("union tree changed")
    for item in context["sources"]:
        source = Path(item["source"])
        union = UNION_DIR / item["union"]
        if (
            Launch._sha256(source) != item["source_sha256"]
            or Launch._sha256(union) != item["union_sha256"]
            or item["source_sha256"] != item["union_sha256"]
        ):
            raise RecoveryError("union source bytes changed")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=("preview", "launch", "recover-launch", "status", "seal"),
    )
    args = parser.parse_args(argv)
    {
        "preview": preview,
        "launch": launch,
        "recover-launch": recover_launch,
        "status": status,
        "seal": seal,
    }[args.command]()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RecoveryError, Launch.LaunchAuditError, Source.SourceAuditError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
