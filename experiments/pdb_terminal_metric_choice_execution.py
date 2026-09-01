#!/usr/bin/env python3
"""Launch, monitor, recover, and seal the frozen dual-metric campaign."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import secrets
import shlex
from collections import Counter
from pathlib import Path

import jj_cached_revision as JJ
import pdb_confirmation_run_cell as RunCell
import pdb_confirmation_safe_io as SafeIO
import pdb_terminal_metric_choice_freeze as Freeze
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_recovery as Recovery
import pdb_terminal_metric_choice_runner as Runner
import pdb_terminal_metric_choice_transport as Transport


class ExecutionError(RuntimeError):
    pass


LAUNCH_INTENT = Runner.ARTIFACT_DIR / "launch-intent-v1.json"
LAUNCH_RECEIPT = Runner.LAUNCH_RECEIPT
LAUNCH_RECEIPT_PIN = Runner.ARTIFACT_DIR / "launch-receipt-v1.sha256"
EXECUTION_RECEIPT = Runner.ARTIFACT_DIR / "execution-receipt-v1.json"
EXECUTION_RECEIPT_PIN = Runner.ARTIFACT_DIR / "execution-receipt-v1.sha256"
RECOVERY_LAUNCH_INTENT = Runner.ARTIFACT_DIR / "recovery-launch-intent-v1.json"
RECOVERY_LAUNCH_RECEIPT = (
    Runner.ARTIFACT_DIR / "recovery-launch-receipt-v1.json"
)
RECOVERY_LAUNCH_RECEIPT_PIN = (
    Runner.ARTIFACT_DIR / "recovery-launch-receipt-v1.sha256"
)

LAUNCH_SCHEMA = P.FREEZE_SCHEMA + "/primary-launch/v1"
RECOVERY_LAUNCH_SCHEMA = P.FREEZE_SCHEMA + "/recovery-launch/v1"
EXECUTION_SCHEMA = P.FREEZE_SCHEMA + "/execution/v1"

SBATCH_EXECUTABLE = Path("/usr/bin/sbatch")
SBATCH_EXECUTABLE_SHA256 = (
    "efbb8e172acc7ed768430740d04e19cc07a3ac4701b005d1a997c08424bde741"
)
SACCT_EXECUTABLE = Path("/usr/bin/sacct")
SACCT_EXECUTABLE_SHA256 = (
    "58f3976b19baa2bc26772a92ab224dd0c1bf0ab3d9b675d85aa3e4636c836315"
)
SUBMISSION_ENVIRONMENT = {
    "LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin",
}
SUBMISSION_TOKEN_RE = re.compile(r"^[0-9a-f]{24}$")
DRIVER_TERMINAL_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} "
    r"INFO     planner exit code: -?\d+$"
)
INFRASTRUCTURE_STATES = frozenset({
    "BOOT_FAIL", "NODE_FAIL", "PREEMPTED", "REVOKED",
})
ACTIVE_STATES = frozenset({
    "PENDING", "RUNNING", "COMPLETING", "CONFIGURING", "REQUEUED",
    "RESIZING", "SUSPENDED", "STAGE_OUT",
})
SACCT_FIELDS = (
    "JobID,JobIDRaw,State,ExitCode,NodeList,ElapsedRaw,Partition,Account,"
    "QOS,ReqCPUS,ReqMem,Timelimit,JobName"
)
JOURNAL_FIELDS = "JobID%64,JobName%128,Comment%128,SubmitLine%4096"


def _read_json(path: Path, label: str) -> tuple[bytes, dict]:
    try:
        loaded, value = CampaignIO.read_canonical_exact(
            path, expected=path, label=label,
            canonical_json_line=P.canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise ExecutionError(str(err)) from err
    return loaded.raw, value


def _write_json(path: Path, value: dict, label: str) -> str:
    try:
        raw = CampaignIO.write_canonical_exclusive(
            path, value, expected=path, root=P.SCRIPT_DIR, label=label,
            canonical_json_line=P.canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise ExecutionError(str(err)) from err
    return hashlib.sha256(raw).hexdigest()


def _write_bytes(path: Path, raw: bytes, label: str) -> str:
    try:
        CampaignIO.write_exclusive_exact(
            path, raw, expected=path, root=P.SCRIPT_DIR, label=label,
        )
    except CampaignIO.CampaignIOError as err:
        raise ExecutionError(str(err)) from err
    return hashlib.sha256(raw).hexdigest()


def _load_freeze() -> tuple[dict, str]:
    freeze = P.load_authorized_freeze(P.FREEZE_PATH)
    digest = P.sha256_file(
        P.FREEZE_PATH, expected_path=P.FREEZE_PATH, label="campaign freeze"
    )
    return freeze, digest


def _validate_utc(value: str) -> None:
    try:
        parsed = datetime.datetime.fromisoformat(value)
    except (TypeError, ValueError) as err:
        raise ExecutionError("submission timestamp is invalid") from err
    if (
        parsed.tzinfo is None
        or parsed.utcoffset() != datetime.timedelta(0)
        or parsed.isoformat(timespec="seconds") != value
    ):
        raise ExecutionError("submission timestamp is not canonical UTC seconds")


def _recorded_utc() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds"
    )


def _verify_executable(path: Path, digest: str, label: str) -> None:
    try:
        descriptor = Transport.open_verified_executable(
            path, expected_path=path, expected_sha256=digest, label=label,
        )
    except Transport.TransportError as err:
        raise ExecutionError(str(err)) from err
    os.close(descriptor)


def _job_optional_directives(raw: bytes) -> dict[str, str | None]:
    try:
        lines = raw.decode("ascii").splitlines()
    except UnicodeDecodeError as err:
        raise ExecutionError("primary Slurm job is not ASCII") from err
    result = {}
    for line in lines:
        if not line.lstrip().startswith("#SBATCH"):
            continue
        try:
            name, value = Transport._parse_sbatch_directive(line)
        except Transport.TransportError as err:
            raise ExecutionError(str(err)) from err
        result[name] = value
    return result


def _validate_job_body(raw: bytes) -> None:
    try:
        text = raw.decode("ascii")
    except UnicodeDecodeError as err:
        raise ExecutionError("primary Slurm job is not ASCII") from err
    lines = text.splitlines()
    if not lines or lines[0] != "#! /bin/bash -l":
        raise ExecutionError("primary Slurm interpreter changed")
    print_block = "\n".join((
        "function print {",
        "    local msg=${1}",
        '    printf "[Slurm task %05d] %s\\n" "$SLURM_ARRAY_TASK_ID" "$msg"',
        "}",
    ))
    print_run_dir_block = "\n".join((
        "function print_run_dir {",
        "    local run_id=${1}",
        '    let "lower=((run_id - 1) / 100) * 100 + 1"',
        '    let "upper=((run_id + 100 - 1) / 100) * 100"',
        '    printf "runs-%05d-%05d/%05d" $lower $upper $run_id',
        "}",
    ))
    execute_run_block = SafeIO.hardened_execute_run_block(
        Path(os.sys.executable),
        P.SCRIPT_DIR / "pdb_confirmation_run_cell.py",
        (
            "driver.err", "driver.log", P.SELECTOR_TRACE,
            RunCell.HARDWARE_ATTESTATION_NAME,
        ),
    )
    if any(text.count(block) != 1 for block in (
        print_block, print_run_dir_block, execute_run_block,
    )):
        raise ExecutionError("primary Slurm execution body changed")
    declarations = [
        line for line in lines if line.startswith("declare -a SHUFFLED_RUN_IDS=")
    ]
    if len(declarations) != 1:
        raise ExecutionError("primary Slurm run mapping is absent")
    match = re.fullmatch(
        r"declare -a SHUFFLED_RUN_IDS=\(([0-9 ]+)\)", declarations[0]
    )
    if match is None or [int(value) for value in match.group(1).split()] != list(
        range(1, P.CELL_COUNT + 1)
    ):
        raise ExecutionError("primary Slurm run mapping changed")
    mapping_block = "\n".join((
        "# Shuffle runs to avoid systematic bias.",
        declarations[0],
        "NUM_RUNS={}".format(P.CELL_COUNT),
        "RUNS_PER_TASK={}".format(P.RUNS_PER_ARRAY_TASK),
        "",
        "# Compute which indices belong to the Slurm task.",
        'let "START_INDEX=($SLURM_ARRAY_TASK_ID - 1) * RUNS_PER_TASK"',
        'let "END_INDEX=START_INDEX + RUNS_PER_TASK - 1"',
        "",
        "if [ $END_INDEX -ge $NUM_RUNS ]; then",
        '    let "END_INDEX=$NUM_RUNS - 1"',
        "fi",
        "",
        "# Execute runs.",
        "for index in $(seq $START_INDEX $END_INDEX); do",
        "    run_id=${SHUFFLED_RUN_IDS[$index]}",
        "    run_dir=$(print_run_dir ${run_id})",
        '    (cd "{}/$run_dir" && execute_run ${{run_id}})'.format(
            Runner.EXPERIMENT_PATH.resolve()
        ),
        "    CELL_STATUS=$?",
        "    if [[ $CELL_STATUS != 0 ]]; then",
        '        exit "$CELL_STATUS"',
        "    fi",
        "done",
    ))
    if text.count(mapping_block) != 1:
        raise ExecutionError("primary Slurm cell mapping changed")
    expected_executable = [
        line
        for block in (
            print_block, print_run_dir_block, execute_run_block, mapping_block,
        )
        for line in block.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    actual_executable = [
        line for line in lines
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if actual_executable != expected_executable:
        raise ExecutionError("primary Slurm job contains an unknown command")


def validate_primary_job(freeze: dict) -> tuple[bytes, str]:
    path = Runner.GRID_DIR / Runner.EXPECTED_JOB_NAME
    try:
        loaded = CampaignIO.read_regular_exact(
            path, expected=path, label="primary Slurm job"
        )
        Transport.validate_job_bytes(
            loaded.raw, Transport.scheduler_contract(freeze, P.ACCOUNT)
        )
    except (CampaignIO.CampaignIOError, Transport.TransportError) as err:
        raise ExecutionError(str(err)) from err
    optional = _job_optional_directives(loaded.raw)
    expected = {
        "job-name": Runner.EXPECTED_JOB_NAME,
        "output": str((Runner.GRID_DIR / "slurm.log").resolve()),
        "error": str((Runner.GRID_DIR / "slurm.err").resolve()),
        "open-mode": "append", "mail-type": "NONE", "mail-user": "",
    }
    if any(optional.get(key) != value for key, value in expected.items()) or (
        optional.get("nice") not in (None, "0")
    ):
        raise ExecutionError("primary Slurm optional directives changed")
    _validate_job_body(loaded.raw)
    return loaded.raw, loaded.sha256


def _required_launch_ancestors(freeze: dict) -> tuple[str, ...]:
    return (
        freeze["planner"]["revision"],
        freeze["freeze_repository_revision"],
        freeze["base_confirmation_b"]["base_b_freeze_repository_revision"],
        freeze["base_confirmation_b"]["source_audit_v6"][
            "repository_commit_id"
        ],
    )


def _validate_repository_commit(
    freeze: dict, commit: str, freeze_sha256: str,
) -> None:
    if P.COMMIT_RE.fullmatch(commit or "") is None:
        raise ExecutionError("launch repository commit is invalid")
    try:
        for ancestor in _required_launch_ancestors(freeze):
            JJ.require_ancestor(P.REPO, ancestor, commit)
    except JJ.JjCacheError as err:
        raise ExecutionError("launch commit ancestry changed") from err
    try:
        bindings = Freeze._launch_closure_bindings(freeze, freeze_sha256)
        Freeze._attest_repository_closure(commit, bindings)
    except Freeze.FreezeError as err:
        raise ExecutionError("launch repository closure changed") from err


def _clean_repository_commit(freeze: dict, freeze_sha256: str) -> str:
    try:
        if JJ.live_working_copy_diff_summary(P.REPO):
            raise ExecutionError("launch requires a clean working copy")
        commit = JJ.parent_commit(P.REPO)
    except JJ.JjCacheError as err:
        raise ExecutionError("cannot attest launch commit") from err
    _validate_repository_commit(freeze, commit, freeze_sha256)
    return commit


def _primary_identity(token: str) -> tuple[str, str]:
    if SUBMISSION_TOKEN_RE.fullmatch(token or "") is None:
        raise ExecutionError("primary submission token is invalid")
    return (
        Runner.EXPECTED_JOB_NAME,
        "pdb-terminal-metric-choice-primary/{}".format(token),
    )


def _primary_command(freeze: dict, token: str) -> list[str]:
    job_name, comment = _primary_identity(token)
    contract = Transport.scheduler_contract(freeze, P.ACCOUNT)
    return [
        str(SBATCH_EXECUTABLE), "--parsable", "--export=NONE", "--no-requeue",
        "--job-name={}".format(job_name), "--comment={}".format(comment),
        "--account={}".format(P.ACCOUNT), "--partition=fat", "--qos=normal",
        "--array=1-300", "--nodes=1", "--ntasks=1", "--cpus-per-task=1",
        "--mem-per-cpu={}".format(contract["memory_per_cpu"]),
        "--time={}".format(contract["time_limit"]),
        "--chdir={}".format(Runner.GRID_DIR.resolve()),
        "--output={}".format((Runner.GRID_DIR / "slurm.log").resolve()),
        "--error={}".format((Runner.GRID_DIR / "slurm.err").resolve()),
        "--open-mode=append", "--mail-type=NONE", "--mail-user=",
    ]


def _build_primary_materials(
    base, freeze: dict, freeze_sha256: str, *, token: str,
    recorded_utc: str, repository_commit_id: str | None = None,
) -> dict:
    _validate_utc(recorded_utc)
    if repository_commit_id is None:
        repository_commit_id = _clean_repository_commit(freeze, freeze_sha256)
    else:
        _validate_repository_commit(
            freeze, repository_commit_id, freeze_sha256
        )
    cached = base.cached_revision(require_hashes=True)
    build_sha, build_inputs = base._validate_build_receipt(cached)
    raw, job_sha = validate_primary_job(freeze)
    _verify_executable(SBATCH_EXECUTABLE, SBATCH_EXECUTABLE_SHA256, "sbatch")
    _verify_executable(SACCT_EXECUTABLE, SACCT_EXECUTABLE_SHA256, "sacct")
    job_name, comment = _primary_identity(token)
    return {
        "schema": LAUNCH_SCHEMA,
        "recorded_utc": recorded_utc,
        "submission_token": token,
        "submission_comment": comment,
        "submit_command": _primary_command(freeze, token),
        "slurm_submission_mode": "stdin",
        "slurm_stdin_sha256": job_sha,
        "slurm_stdin_bytes": len(raw),
        "slurm_path_argument": False,
        "submission_journal_contract": "exact options-only SubmitLine",
        "sbatch_executable": str(SBATCH_EXECUTABLE),
        "sbatch_executable_sha256": SBATCH_EXECUTABLE_SHA256,
        "sacct_executable": str(SACCT_EXECUTABLE),
        "sacct_executable_sha256": SACCT_EXECUTABLE_SHA256,
        "submission_environment": dict(SUBMISSION_ENVIRONMENT),
        "repository_commit_id": repository_commit_id,
        "freeze_sha256": freeze_sha256,
        "job_name": job_name,
        "scheduler_contract": Transport.scheduler_contract(freeze, P.ACCOUNT),
        "job_file_sha256": job_sha,
        "build_receipt_sha256": build_sha,
        "build_inputs": build_inputs,
    }


def _load_primary_intent(base, freeze: dict, freeze_sha256: str):
    raw, intent = _read_json(LAUNCH_INTENT, "primary launch intent")
    prepared = intent.get("prepared_receipt_without_job_id")
    if not isinstance(prepared, dict):
        raise ExecutionError("primary launch intent is incomplete")
    expected = _build_primary_materials(
        base, freeze, freeze_sha256,
        token=prepared.get("submission_token"),
        recorded_utc=prepared.get("recorded_utc"),
        repository_commit_id=prepared.get("repository_commit_id"),
    )
    if intent != {
        "schema": LAUNCH_SCHEMA + "/intent",
        "prepared_receipt_without_job_id": expected,
    }:
        raise ExecutionError("primary launch intent changed")
    return raw, intent, expected


def _write_launch_receipt(
    intent_raw: bytes, materials: dict, job_id: str, *,
    receipt_path: Path, pin_path: Path, label: str,
) -> str:
    if not isinstance(job_id, str) or not job_id.isdigit():
        raise ExecutionError("{} job id is invalid".format(label))
    value = {
        **materials,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": job_id,
    }
    digest = _write_json(receipt_path, value, label + " receipt")
    _write_bytes(pin_path, (digest + "\n").encode("ascii"), label + " pin")
    return digest


def launch_primary(base) -> dict:
    if any(path.exists() or path.is_symlink() for path in (
        LAUNCH_INTENT, LAUNCH_RECEIPT, LAUNCH_RECEIPT_PIN,
        EXECUTION_RECEIPT, EXECUTION_RECEIPT_PIN,
    )):
        raise ExecutionError("primary launch namespace is not fresh")
    freeze, freeze_sha = _load_freeze()
    token = secrets.token_hex(12)
    materials = _build_primary_materials(
        base, freeze, freeze_sha, token=token, recorded_utc=_recorded_utc()
    )
    intent = {
        "schema": LAUNCH_SCHEMA + "/intent",
        "prepared_receipt_without_job_id": materials,
    }
    intent_raw = P.canonical_json_line(intent)
    _write_bytes(LAUNCH_INTENT, intent_raw, "primary launch intent")
    raw, job_sha = validate_primary_job(freeze)
    if job_sha != materials["slurm_stdin_sha256"] or len(raw) != materials[
        "slurm_stdin_bytes"
    ]:
        raise ExecutionError("primary job changed after launch intent")
    if _clean_repository_commit(freeze, freeze_sha) != materials[
        "repository_commit_id"
    ]:
        raise ExecutionError("launch repository parent changed before submission")
    try:
        job_id = Transport.submit_pinned_stdin(
            SBATCH_EXECUTABLE, SBATCH_EXECUTABLE_SHA256,
            materials["submit_command"][1:], raw,
            environment=SUBMISSION_ENVIRONMENT, cwd=Runner.GRID_DIR,
            label="primary sbatch",
        )
    except Transport.TransportError as err:
        raise ExecutionError(str(err)) from err
    digest = _write_launch_receipt(
        intent_raw, materials, job_id, receipt_path=LAUNCH_RECEIPT,
        pin_path=LAUNCH_RECEIPT_PIN, label="primary launch",
    )
    return {"job_id": job_id, "launch_receipt_sha256": digest}


def _pinned_sacct(arguments: list[str]) -> str:
    try:
        completed = Transport.run_pinned_executable(
            SACCT_EXECUTABLE, SACCT_EXECUTABLE_SHA256, arguments,
            environment=SUBMISSION_ENVIRONMENT, label="sacct",
        )
        return completed.stdout.decode("utf-8")
    except (Transport.TransportError, AttributeError, UnicodeDecodeError) as err:
        raise ExecutionError("cannot query pinned Slurm accounting") from err


def _journal_job_ids(materials: dict, expected_tasks: set[int]) -> list[str]:
    try:
        recorded = datetime.datetime.fromisoformat(materials["recorded_utc"])
    except (KeyError, TypeError, ValueError) as err:
        raise ExecutionError("submission timestamp is invalid") from err
    output = _pinned_sacct([
        "-X", "--array", "-S", recorded.date().isoformat(),
        "--name=" + materials["job_name"], "-n", "-P",
        "--format=" + JOURNAL_FIELDS,
    ])
    expected_command = materials.get("submit_command")
    if (
        not isinstance(expected_command, list) or not expected_command
        or expected_command[0] != str(SBATCH_EXECUTABLE)
        or any(not option.startswith("--") for option in expected_command[1:])
    ):
        raise ExecutionError("submit command is not options-only")
    parents = set()
    indices = {}
    exact_commands = 0
    exact_comments = 0
    for line in output.splitlines():
        fields = line.split("|", 3)
        if len(fields) != 4:
            raise ExecutionError("submission journal row changed")
        job_id, name, comment, submit_line = fields
        token = materials["submission_token"]
        if name != materials["job_name"] and comment != materials[
            "submission_comment"
        ] and token not in submit_line:
            continue
        try:
            actual = shlex.split(submit_line)
        except ValueError as err:
            raise ExecutionError("submission journal command is malformed") from err
        if actual and actual[0] == "sbatch":
            actual[0] = str(SBATCH_EXECUTABLE)
        if actual == expected_command:
            exact_commands += 1
        elif actual:
            raise ExecutionError("submission journal command changed")
        if comment == materials["submission_comment"]:
            exact_comments += 1
        elif comment:
            raise ExecutionError("submission journal comment changed")
        parent_match = re.fullmatch(r"([0-9]+)", job_id)
        array_match = re.fullmatch(r"([0-9]+)_([0-9]+)", job_id)
        if name != materials["job_name"] or (
            parent_match is None and array_match is None
        ):
            raise ExecutionError("submission identity collided")
        parent = (parent_match or array_match).group(1)
        parents.add(parent)
        if array_match is not None:
            task = int(array_match.group(2))
            if task not in expected_tasks:
                raise ExecutionError("submission journal task set changed")
            indices.setdefault(parent, set()).add(task)
    if not parents and exact_commands == 0 and exact_comments == 0:
        return []
    if (
        len(parents) > 1 or exact_commands < 1 or exact_comments < 1
        or (len(parents) == 1 and indices.get(next(iter(parents)), set())
            != expected_tasks)
    ):
        raise ExecutionError("submission journal is incomplete or ambiguous")
    return sorted(parents, key=int)


def load_primary_launch(base, *, verify_live: bool = True) -> tuple[str, dict]:
    freeze, freeze_sha = _load_freeze()
    intent_raw, _, materials = _load_primary_intent(base, freeze, freeze_sha)
    raw, receipt = _read_json(LAUNCH_RECEIPT, "primary launch receipt")
    try:
        pin = CampaignIO.read_regular_exact(
            LAUNCH_RECEIPT_PIN, expected=LAUNCH_RECEIPT_PIN,
            label="primary launch receipt pin",
        ).raw
    except CampaignIO.CampaignIOError as err:
        raise ExecutionError("primary launch receipt is not pinned") from err
    digest = hashlib.sha256(raw).hexdigest()
    expected = {
        **materials,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": receipt.get("job_id"),
    }
    if (
        receipt != expected or not str(receipt.get("job_id", "")).isdigit()
        or pin != (digest + "\n").encode("ascii")
    ):
        raise ExecutionError("primary launch receipt changed")
    if verify_live and _journal_job_ids(
        receipt, set(range(1, P.EXPECTED_ARRAY_TASKS + 1))
    ) != [receipt["job_id"]]:
        raise ExecutionError("primary launch is not journal-bound")
    return digest, receipt


def recover_primary_launch(base) -> dict:
    freeze, freeze_sha = _load_freeze()
    intent_raw, _, materials = _load_primary_intent(base, freeze, freeze_sha)
    if LAUNCH_RECEIPT.exists():
        raw, receipt = _read_json(LAUNCH_RECEIPT, "primary launch receipt")
        if LAUNCH_RECEIPT_PIN.exists():
            raise ExecutionError("primary launch receipt is already pinned")
        expected = {
            **materials,
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": receipt.get("job_id"),
        }
        if receipt != expected or not str(receipt.get("job_id", "")).isdigit():
            raise ExecutionError("unsealed primary launch receipt changed")
        digest = hashlib.sha256(raw).hexdigest()
        _write_bytes(
            LAUNCH_RECEIPT_PIN, (digest + "\n").encode("ascii"),
            "primary launch receipt pin",
        )
        return {"job_id": receipt["job_id"], "launch_receipt_sha256": digest}
    if LAUNCH_RECEIPT_PIN.exists():
        raise ExecutionError("primary launch pin exists without its receipt")
    jobs = _journal_job_ids(
        materials, set(range(1, P.EXPECTED_ARRAY_TASKS + 1))
    )
    if len(jobs) != 1:
        raise ExecutionError(
            "primary submission journal identifies {} jobs".format(len(jobs))
        )
    digest = _write_launch_receipt(
        intent_raw, materials, jobs[0], receipt_path=LAUNCH_RECEIPT,
        pin_path=LAUNCH_RECEIPT_PIN, label="primary launch",
    )
    return {"job_id": jobs[0], "launch_receipt_sha256": digest}


def _scheduler_rows(
    job_id: str, expected_tasks: set[int], job_name: str, freeze: dict,
) -> tuple[list[dict], list[dict]]:
    if not job_id.isdigit() or not expected_tasks:
        raise ExecutionError("scheduler query identity is invalid")
    output = _pinned_sacct([
        "-j", job_id, "-X", "--array", "-n", "-P",
        "--format=" + SACCT_FIELDS,
    ])
    rows = {}
    contracts = {}
    prefix = job_id + "_"
    expected_contract = Transport.scheduler_contract(freeze, P.ACCOUNT)
    for line in output.splitlines():
        fields = line.split("|")
        if len(fields) != 13:
            raise ExecutionError("scheduler accounting row shape changed")
        (
            array_id, raw_id, state, exit_code, node, elapsed, partition,
            account, qos, req_cpus, req_mem, time_limit, actual_name,
        ) = fields
        if not array_id.startswith(prefix) or not array_id[len(prefix):].isdigit():
            continue
        task = int(array_id[len(prefix):])
        state = state.split("+", 1)[0].split()[0]
        if (
            task in rows or task not in expected_tasks
            or raw_id != "{}_{}".format(job_id, task)
            or not state or not exit_code or not elapsed.isdigit()
            or partition != "fat" or account != P.ACCOUNT or qos != "normal"
            or req_cpus != "1"
            or req_mem != expected_contract["memory_per_cpu"]
            or time_limit != expected_contract["time_limit"]
            or actual_name != job_name
        ):
            raise ExecutionError("scheduler resource accounting changed")
        rows[task] = {
            "array_task": task, "job_id_raw": raw_id, "state": state,
            "exit_code": exit_code, "node": node,
            "elapsed_raw": int(elapsed), "partition": partition,
        }
        contracts[task] = {
            "array_task": task, "account": account, "partition": partition,
            "qos": qos, "req_cpus": 1, "req_mem": req_mem,
            "time_limit": time_limit, "state": state,
            "exit_code": exit_code, "job_name": actual_name,
        }
    if set(rows) != expected_tasks:
        raise ExecutionError("scheduler accounting task set is incomplete")
    return (
        [rows[task] for task in sorted(rows)],
        [contracts[task] for task in sorted(contracts)],
    )


def _run_directory(cell: int) -> Path:
    lower = ((cell - 1) // 100) * 100 + 1
    return Runner.EXPERIMENT_PATH / "runs-{:05d}-{:05d}".format(
        lower, lower + 99
    ) / "{:05d}".format(cell)


def _cell_markers() -> tuple[set[int], set[int]]:
    started = set()
    completed = set()
    for cell in range(1, P.CELL_COUNT + 1):
        directory = _run_directory(cell)
        try:
            dynamic = Transport.scan_regular_namespace(
                directory, expected_directory=directory,
                root=Runner.EXPERIMENT_PATH,
                excluded_names=Recovery.STATIC_RUN_NAMES,
                label="run cell {:05d}".format(cell),
            )
        except Transport.TransportError as err:
            raise ExecutionError(str(err)) from err
        if "driver.log" not in dynamic:
            if dynamic:
                raise ExecutionError("cell output exists without driver.log")
            continue
        started.add(cell)
        path = directory / "driver.log"
        try:
            loaded = CampaignIO.read_regular_exact(
                path, expected=path, label="driver completion marker"
            )
            lines = loaded.raw.decode("utf-8").splitlines()
        except (CampaignIO.CampaignIOError, UnicodeDecodeError) as err:
            raise ExecutionError("driver completion marker changed") from err
        if lines and DRIVER_TERMINAL_RE.fullmatch(lines[-1]):
            completed.add(cell)
    return started, completed


def _classify(row: dict, started: list[int], completed: list[int]) -> str:
    triad = list(P.triad_cells(row["array_task"]))
    if not set(completed) <= set(started) or not set(started) <= set(triad):
        raise ExecutionError("cell marker accounting changed")
    if row["state"] == "COMPLETED" and row["exit_code"] == "0:0":
        return Recovery.COMPLETE if completed == triad else Recovery.SEMANTIC_FAILURE
    if row["state"] in INFRASTRUCTURE_STATES:
        return Recovery.INTERRUPTED
    if row["state"] in ACTIVE_STATES:
        return Recovery.ACTIVE
    return Recovery.SEMANTIC_FAILURE


def _entries(
    rows: list[dict], *, job_id: str, attempt: int,
    started_cells: set[int], completed_cells: set[int],
) -> list[dict]:
    result = []
    for row in rows:
        triad = list(P.triad_cells(row["array_task"]))
        started = [cell for cell in triad if cell in started_cells]
        completed = [cell for cell in triad if cell in completed_cells]
        result.append({
            "array_task": row["array_task"], "attempt": attempt,
            "job_id": job_id,
            "state": _classify(row, started, completed),
            "started_cells": started, "completed_cells": completed,
        })
    return result


def make_primary_snapshot(base) -> dict:
    freeze, freeze_sha = _load_freeze()
    launch_sha, launch = load_primary_launch(base, verify_live=True)
    tasks = set(range(1, P.EXPECTED_ARRAY_TASKS + 1))
    rows, contracts = _scheduler_rows(
        launch["job_id"], tasks, Runner.EXPECTED_JOB_NAME, freeze
    )
    started, completed = _cell_markers()
    entries = _entries(
        rows, job_id=launch["job_id"], attempt=1,
        started_cells=started, completed_cells=completed,
    )
    value = {
        "schema": Recovery.SCHEDULER_SNAPSHOT_SCHEMA,
        "freeze_sha256": freeze_sha,
        "primary_launch_receipt_sha256": launch_sha,
        "run_cell_mapping_sha256": freeze["design"]["run_cell_mapping_sha256"],
        "scheduler_contract": Transport.scheduler_contract(freeze, P.ACCOUNT),
        "scheduler_rows": rows,
        "scheduler_contract_rows": contracts,
        "entries": entries,
        "entries_sha256": hashlib.sha256(P.canonical_json(entries)).hexdigest(),
    }
    try:
        Recovery.validate_scheduler_snapshot(value, freeze, freeze_sha)
    except Recovery.RecoveryError as err:
        raise ExecutionError(str(err)) from err
    return value


def publish_primary_snapshot(base) -> str:
    if any(path.exists() or path.is_symlink() for path in (
        Recovery.SCHEDULER_SNAPSHOT_PATH, RECOVERY_LAUNCH_INTENT,
        RECOVERY_LAUNCH_RECEIPT, RECOVERY_LAUNCH_RECEIPT_PIN,
    )):
        raise ExecutionError("recovery snapshot namespace is not fresh")
    value = make_primary_snapshot(base)
    return _write_json(
        Recovery.SCHEDULER_SNAPSHOT_PATH, value, "scheduler array snapshot"
    )


def _load_primary_snapshot(
    base, *, verify_launch_live: bool = True,
) -> tuple[bytes, dict]:
    raw, snapshot = _read_json(
        Recovery.SCHEDULER_SNAPSHOT_PATH, "scheduler array snapshot"
    )
    freeze, freeze_sha = _load_freeze()
    try:
        Recovery.validate_scheduler_snapshot(snapshot, freeze, freeze_sha)
    except Recovery.RecoveryError as err:
        raise ExecutionError(str(err)) from err
    launch_sha, _ = load_primary_launch(base, verify_live=verify_launch_live)
    if snapshot.get("primary_launch_receipt_sha256") != launch_sha:
        raise ExecutionError("scheduler snapshot launch binding changed")
    return raw, snapshot


def _make_recovery_job(freeze: dict, tasks: list[int]) -> tuple[bytes, str]:
    primary_raw, _ = validate_primary_job(freeze)
    old = b"#SBATCH --array=1-300\n"
    new = ("#SBATCH --array={}\n".format(",".join(map(str, tasks)))).encode(
        "ascii"
    )
    if primary_raw.count(old) != 1:
        raise ExecutionError("primary job array directive changed")
    raw = primary_raw.replace(old, new, 1)
    contract = Transport.scheduler_contract(freeze, P.ACCOUNT)
    contract.update({
        "array_spec": ",".join(map(str, tasks)), "array_tasks": len(tasks),
    })
    try:
        Transport.validate_job_bytes(raw, contract)
    except Transport.TransportError as err:
        raise ExecutionError(str(err)) from err
    digest = _write_bytes(Recovery.RECOVERY_JOB_PATH, raw, "recovery Slurm job")
    return raw, digest


def _recovery_identity(token: str) -> tuple[str, str]:
    if SUBMISSION_TOKEN_RE.fullmatch(token or "") is None:
        raise ExecutionError("recovery submission token is invalid")
    return (
        "pdb-terminal-metric-choice-recovery-0001",
        "pdb-terminal-metric-choice-recovery/1/{}".format(token),
    )


def _full_recovery_options(
    base_options: list[str], token: str,
) -> list[str]:
    name, comment = _recovery_identity(token)
    expected_name = [option for option in base_options if option.startswith(
        "--job-name="
    )]
    if expected_name != ["--job-name=" + name]:
        raise ExecutionError("recovery base job name changed")
    return [
        "--parsable", *base_options,
        "--comment={}".format(comment),
        "--output={}".format(
            (Runner.ARTIFACT_DIR / "recovery-slurm-%A_%a.out").resolve()
        ),
        "--error={}".format(
            (Runner.ARTIFACT_DIR / "recovery-slurm-%A_%a.err").resolve()
        ),
        "--chdir={}".format(Runner.GRID_DIR.resolve()),
        "--open-mode=append", "--mail-type=NONE", "--mail-user=",
    ]


def _recovery_materials(
    base, freeze: dict, freeze_sha: str, snapshot_raw: bytes, snapshot: dict,
    *, token: str, recorded_utc: str, base_options: list[str], job_raw: bytes,
    verify_launch_live: bool = True,
) -> dict:
    _validate_utc(recorded_utc)
    tasks = [
        row["array_task"] for row in snapshot["entries"]
        if row["state"] == Recovery.INTERRUPTED
    ]
    cells = [cell for task in tasks for cell in P.triad_cells(task)]
    if not tasks:
        raise ExecutionError("there are no interrupted triads to recover")
    launch_sha, launch = load_primary_launch(
        base, verify_live=verify_launch_live
    )
    paths = (
        Recovery.JOURNAL_PATH, Recovery.POST_ARCHIVE_RESCAN_PATH,
        Recovery.PRE_SUBMIT_RESCAN_PATH,
    )
    loaded = [_read_json(path, "recovery provenance")[0] for path in paths]
    options = _full_recovery_options(base_options, token)
    name, comment = _recovery_identity(token)
    return {
        "schema": RECOVERY_LAUNCH_SCHEMA,
        "recorded_utc": recorded_utc,
        "submission_token": token,
        "submission_comment": comment,
        "submit_command": [str(SBATCH_EXECUTABLE), *options],
        "slurm_submission_mode": "stdin",
        "slurm_stdin_sha256": hashlib.sha256(job_raw).hexdigest(),
        "slurm_stdin_bytes": len(job_raw),
        "slurm_path_argument": False,
        "submission_journal_contract": "exact options-only SubmitLine",
        "sbatch_executable": str(SBATCH_EXECUTABLE),
        "sbatch_executable_sha256": SBATCH_EXECUTABLE_SHA256,
        "sacct_executable": str(SACCT_EXECUTABLE),
        "sacct_executable_sha256": SACCT_EXECUTABLE_SHA256,
        "submission_environment": dict(SUBMISSION_ENVIRONMENT),
        "repository_commit_id": launch["repository_commit_id"],
        "freeze_sha256": freeze_sha,
        "source_launch_receipt_sha256": launch_sha,
        "source_job_id": launch["job_id"],
        "source_snapshot_sha256": hashlib.sha256(snapshot_raw).hexdigest(),
        "recovery_wave": 1,
        "array_tasks": tasks,
        "array_spec": ",".join(map(str, tasks)),
        "recoverable_cells": cells,
        "job_name": name,
        "scheduler_contract": Transport.scheduler_contract(freeze, P.ACCOUNT),
        "recovery_job_sha256": hashlib.sha256(job_raw).hexdigest(),
        "recovery_journal_sha256": hashlib.sha256(loaded[0]).hexdigest(),
        "post_archive_rescan_sha256": hashlib.sha256(loaded[1]).hexdigest(),
        "pre_submit_rescan_sha256": hashlib.sha256(loaded[2]).hexdigest(),
    }


def launch_recovery(base) -> dict:
    forbidden = (
        Recovery.RECOVERY_JOB_PATH, Recovery.JOURNAL_PATH,
        Recovery.POST_ARCHIVE_RESCAN_PATH, Recovery.PRE_SUBMIT_RESCAN_PATH,
        RECOVERY_LAUNCH_INTENT, RECOVERY_LAUNCH_RECEIPT,
        RECOVERY_LAUNCH_RECEIPT_PIN,
    )
    if any(path.exists() or path.is_symlink() for path in forbidden):
        raise ExecutionError("the single recovery-wave namespace is not fresh")
    freeze, freeze_sha = _load_freeze()
    snapshot_raw, snapshot = _load_primary_snapshot(base)
    live = make_primary_snapshot(base)
    if P.canonical_json(snapshot) != P.canonical_json(live):
        raise ExecutionError("scheduler snapshot changed before recovery")
    states = {row["state"] for row in snapshot["entries"]}
    if Recovery.ACTIVE in states or Recovery.SEMANTIC_FAILURE in states:
        raise ExecutionError("active or semantic-failure triads block recovery")
    tasks = [
        row["array_task"] for row in snapshot["entries"]
        if row["state"] == Recovery.INTERRUPTED
    ]
    if not tasks:
        raise ExecutionError("primary execution needs no recovery")
    job_raw, _ = _make_recovery_job(freeze, tasks)
    token = secrets.token_hex(12)
    recorded = _recorded_utc()
    name, _ = _recovery_identity(token)
    published = {}

    def submitter(base_options: list[str], submitted_raw: bytes) -> str:
        if submitted_raw != job_raw:
            raise Recovery.RecoveryError("recovery job changed before submission")
        materials = _recovery_materials(
            base, freeze, freeze_sha, snapshot_raw, snapshot, token=token,
            recorded_utc=recorded, base_options=base_options, job_raw=job_raw,
        )
        intent = {
            "schema": RECOVERY_LAUNCH_SCHEMA + "/intent",
            "prepared_receipt_without_job_id": materials,
        }
        intent_raw = P.canonical_json_line(intent)
        _write_bytes(
            RECOVERY_LAUNCH_INTENT, intent_raw, "recovery launch intent"
        )
        try:
            if _clean_repository_commit(freeze, freeze_sha) != materials[
                "repository_commit_id"
            ]:
                raise ExecutionError(
                    "recovery repository parent changed before submission"
                )
        except ExecutionError as err:
            raise Recovery.RecoveryError(
                "recovery repository closure changed"
            ) from err
        try:
            job_id = Transport.submit_pinned_stdin(
                SBATCH_EXECUTABLE, SBATCH_EXECUTABLE_SHA256,
                materials["submit_command"][1:], submitted_raw,
                environment=SUBMISSION_ENVIRONMENT, cwd=Runner.GRID_DIR,
                label="recovery sbatch",
            )
        except Transport.TransportError as err:
            raise Recovery.RecoveryError(str(err)) from err
        digest = _write_launch_receipt(
            intent_raw, materials, job_id,
            receipt_path=RECOVERY_LAUNCH_RECEIPT,
            pin_path=RECOVERY_LAUNCH_RECEIPT_PIN,
            label="recovery launch",
        )
        published.update({
            "job_id": job_id, "launch_receipt_sha256": digest,
        })
        return job_id

    try:
        result = Recovery.coordinate_recovery(
            snapshot, freeze, freeze_sha,
            experiment_root=Recovery.EXPERIMENT_ROOT,
            archive_root=Recovery.ARCHIVE_ROOT,
            receipt_root=P.ARTIFACT_DIR,
            job_file=Recovery.RECOVERY_JOB_PATH,
            expected_job_file=Recovery.RECOVERY_JOB_PATH,
            job_name=name, submitter=submitter,
        )
    except Recovery.RecoveryError as err:
        raise ExecutionError(str(err)) from err
    if result.get("submission", {}).get("job_id") != published.get("job_id"):
        raise ExecutionError("recovery coordinator lost its submission identity")
    return published


def _load_recovery_intent(
    base, freeze: dict, freeze_sha: str, *, verify_live: bool = True,
):
    raw, intent = _read_json(RECOVERY_LAUNCH_INTENT, "recovery launch intent")
    prepared = intent.get("prepared_receipt_without_job_id")
    if not isinstance(prepared, dict):
        raise ExecutionError("recovery launch intent is incomplete")
    snapshot_raw, snapshot = _load_primary_snapshot(
        base, verify_launch_live=verify_live
    )
    try:
        job = CampaignIO.read_regular_exact(
            Recovery.RECOVERY_JOB_PATH, expected=Recovery.RECOVERY_JOB_PATH,
            label="recovery Slurm job",
        )
    except CampaignIO.CampaignIOError as err:
        raise ExecutionError(str(err)) from err
    command = prepared.get("submit_command")
    if not isinstance(command, list) or not command:
        raise ExecutionError("recovery submit command is absent")
    options = command[1:]
    # Remove the options added by _full_recovery_options to recover the exact
    # coordinator base list, then reconstruct all semantics from fixed files.
    added_names = {
        "--parsable", "--comment", "--output", "--error", "--chdir",
        "--open-mode", "--mail-type", "--mail-user",
    }
    base_options = [
        option for option in options
        if not any(
            option == name or option.startswith(name + "=")
            for name in added_names
        )
    ]
    expected = _recovery_materials(
        base, freeze, freeze_sha, snapshot_raw, snapshot,
        token=prepared.get("submission_token"),
        recorded_utc=prepared.get("recorded_utc"),
        base_options=base_options, job_raw=job.raw,
        verify_launch_live=verify_live,
    )
    if intent != {
        "schema": RECOVERY_LAUNCH_SCHEMA + "/intent",
        "prepared_receipt_without_job_id": expected,
    }:
        raise ExecutionError("recovery launch intent changed")
    return raw, intent, expected


def load_recovery_launch(base, *, verify_live: bool = True) -> tuple[str, dict]:
    freeze, freeze_sha = _load_freeze()
    intent_raw, _, materials = _load_recovery_intent(
        base, freeze, freeze_sha, verify_live=verify_live
    )
    raw, receipt = _read_json(
        RECOVERY_LAUNCH_RECEIPT, "recovery launch receipt"
    )
    try:
        pin = CampaignIO.read_regular_exact(
            RECOVERY_LAUNCH_RECEIPT_PIN,
            expected=RECOVERY_LAUNCH_RECEIPT_PIN,
            label="recovery launch receipt pin",
        ).raw
    except CampaignIO.CampaignIOError as err:
        raise ExecutionError("recovery launch receipt is not pinned") from err
    digest = hashlib.sha256(raw).hexdigest()
    expected = {
        **materials,
        "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
        "job_id": receipt.get("job_id"),
    }
    if (
        receipt != expected or not str(receipt.get("job_id", "")).isdigit()
        or pin != (digest + "\n").encode("ascii")
    ):
        raise ExecutionError("recovery launch receipt changed")
    if verify_live and _journal_job_ids(
        receipt, set(receipt["array_tasks"])
    ) != [receipt["job_id"]]:
        raise ExecutionError("recovery launch is not journal-bound")
    return digest, receipt


def recover_recovery_launch(base) -> dict:
    freeze, freeze_sha = _load_freeze()
    intent_raw, _, materials = _load_recovery_intent(base, freeze, freeze_sha)
    if RECOVERY_LAUNCH_RECEIPT.exists():
        raw, receipt = _read_json(
            RECOVERY_LAUNCH_RECEIPT, "recovery launch receipt"
        )
        if RECOVERY_LAUNCH_RECEIPT_PIN.exists():
            raise ExecutionError("recovery launch receipt is already pinned")
        expected = {
            **materials,
            "launch_intent_sha256": hashlib.sha256(intent_raw).hexdigest(),
            "job_id": receipt.get("job_id"),
        }
        if receipt != expected or not str(receipt.get("job_id", "")).isdigit():
            raise ExecutionError("unsealed recovery receipt changed")
        digest = hashlib.sha256(raw).hexdigest()
        _write_bytes(
            RECOVERY_LAUNCH_RECEIPT_PIN, (digest + "\n").encode("ascii"),
            "recovery launch receipt pin",
        )
        return {"job_id": receipt["job_id"], "launch_receipt_sha256": digest}
    if RECOVERY_LAUNCH_RECEIPT_PIN.exists():
        raise ExecutionError("recovery launch pin exists without its receipt")
    jobs = _journal_job_ids(materials, set(materials["array_tasks"]))
    if len(jobs) != 1:
        raise ExecutionError(
            "recovery submission journal identifies {} jobs".format(len(jobs))
        )
    digest = _write_launch_receipt(
        intent_raw, materials, jobs[0],
        receipt_path=RECOVERY_LAUNCH_RECEIPT,
        pin_path=RECOVERY_LAUNCH_RECEIPT_PIN,
        label="recovery launch",
    )
    return {"job_id": jobs[0], "launch_receipt_sha256": digest}


def _combined_status(base) -> dict:
    freeze, freeze_sha = _load_freeze()
    primary_sha, primary = load_primary_launch(base, verify_live=True)
    all_tasks = set(range(1, P.EXPECTED_ARRAY_TASKS + 1))
    primary_rows, primary_contracts = _scheduler_rows(
        primary["job_id"], all_tasks, Runner.EXPECTED_JOB_NAME, freeze
    )
    started, completed = _cell_markers()
    recovery = None
    recovery_rows = []
    recovery_contracts = []
    recovered_tasks = set()
    source_snapshot_sha = None
    if RECOVERY_LAUNCH_INTENT.exists() or RECOVERY_LAUNCH_RECEIPT.exists():
        if not (RECOVERY_LAUNCH_RECEIPT.exists()
                and RECOVERY_LAUNCH_RECEIPT_PIN.exists()):
            raise ExecutionError(
                "recovery submission is ambiguous; run recover-reconcile"
            )
        recovery_sha, recovery = load_recovery_launch(base, verify_live=True)
        recovered_tasks = set(recovery["array_tasks"])
        recovery_rows, recovery_contracts = _scheduler_rows(
            recovery["job_id"], recovered_tasks, recovery["job_name"], freeze
        )
        snapshot_raw, snapshot = _load_primary_snapshot(base)
        source_snapshot_sha = hashlib.sha256(snapshot_raw).hexdigest()
        if source_snapshot_sha != recovery["source_snapshot_sha256"]:
            raise ExecutionError("recovery source snapshot changed")
        interrupted = {
            row["array_task"] for row in snapshot["entries"]
            if row["state"] == Recovery.INTERRUPTED
        }
        if interrupted != recovered_tasks:
            raise ExecutionError("recovery omitted or added a source triad")
        if snapshot["scheduler_rows"] != primary_rows or (
            snapshot["scheduler_contract_rows"] != primary_contracts
        ):
            raise ExecutionError("primary scheduler accounting changed")
    latest_rows = {row["array_task"]: row for row in primary_rows}
    attempts = {task: (primary["job_id"], 1) for task in all_tasks}
    for row in recovery_rows:
        latest_rows[row["array_task"]] = row
        attempts[row["array_task"]] = (recovery["job_id"], 2)
    effective = []
    for task in sorted(all_tasks):
        row = latest_rows[task]
        triad = list(P.triad_cells(task))
        task_started = [cell for cell in triad if cell in started]
        task_completed = [cell for cell in triad if cell in completed]
        job_id, attempt = attempts[task]
        effective.append({
            "array_task": task, "attempt": attempt, "job_id": job_id,
            "state": _classify(row, task_started, task_completed),
            "started_cells": task_started, "completed_cells": task_completed,
        })
    return {
        "freeze_sha256": freeze_sha,
        "primary_launch_receipt_sha256": primary_sha,
        "primary_job_id": primary["job_id"],
        "primary_scheduler_rows": primary_rows,
        "primary_scheduler_contract_rows": primary_contracts,
        "recovery_launch_receipt_sha256": (
            None if recovery is None else recovery_sha
        ),
        "recovery_job_id": None if recovery is None else recovery["job_id"],
        "recovery_source_snapshot_sha256": source_snapshot_sha,
        "recovery_scheduler_rows": recovery_rows,
        "recovery_scheduler_contract_rows": recovery_contracts,
        "effective_entries": effective,
        "effective_entries_sha256": hashlib.sha256(
            P.canonical_json(effective)
        ).hexdigest(),
        "state_counts": dict(Counter(row["state"] for row in effective)),
        "complete_cells": len(completed),
        "started_cells": len(started),
    }


def status(base) -> dict:
    return _combined_status(base)


def _dynamic_manifest() -> dict:
    relatives = []
    required = {
        "driver.log", "driver.err", P.SELECTOR_TRACE,
        RunCell.HARDWARE_ATTESTATION_NAME,
    }
    for cell in range(1, P.CELL_COUNT + 1):
        directory = _run_directory(cell)
        try:
            names = Transport.scan_regular_namespace(
                directory, expected_directory=directory,
                root=Runner.EXPERIMENT_PATH,
                excluded_names=Recovery.STATIC_RUN_NAMES,
                label="completed run cell {:05d}".format(cell),
            )
        except Transport.TransportError as err:
            raise ExecutionError(str(err)) from err
        if not required <= set(names):
            raise ExecutionError("completed cell lacks required dynamic evidence")
        relatives.extend(
            (directory / name).relative_to(Runner.EXPERIMENT_PATH).as_posix()
            for name in names
        )
    try:
        return Transport.immutable_tree_manifest(
            Runner.EXPERIMENT_PATH, sorted(relatives),
            label="completed dynamic cell tree",
        )
    except Transport.TransportError as err:
        raise ExecutionError(str(err)) from err


def _hardware_summary() -> dict:
    records = []
    for cell in range(1, P.CELL_COUNT + 1):
        path = _run_directory(cell) / RunCell.HARDWARE_ATTESTATION_NAME
        try:
            loaded = SafeIO.read_regular_file(
                path, label="cell hardware attestation",
                root=Runner.EXPERIMENT_PATH,
            )
        except SafeIO.SafeReadError as err:
            raise ExecutionError(
                "cell hardware attestation is missing or unsafe"
            ) from err
        records.append((cell, loaded.raw))
    groups = [
        list(P.triad_cells(task))
        for task in range(1, P.EXPECTED_ARRAY_TASKS + 1)
    ]
    try:
        return RunCell.summarize_hardware_records(records, groups)
    except RunCell.RunCellError as err:
        raise ExecutionError(str(err)) from err


def _primary_log_manifest() -> dict:
    try:
        return Transport.immutable_tree_manifest(
            Runner.GRID_DIR, ["slurm.err", "slurm.log"],
            label="primary Slurm logs",
        )
    except Transport.TransportError as err:
        raise ExecutionError(str(err)) from err


def _recovery_log_manifest(recovery: dict | None) -> dict | None:
    if recovery is None:
        return None
    relatives = sorted(
        "recovery-slurm-{}_{}.{}".format(recovery["job_id"], task, suffix)
        for task in recovery["array_tasks"] for suffix in ("err", "out")
    )
    try:
        return Transport.immutable_tree_manifest(
            Runner.ARTIFACT_DIR, relatives, label="recovery Slurm logs"
        )
    except Transport.TransportError as err:
        raise ExecutionError(str(err)) from err


def _live_execution_value(base) -> dict:
    current = _combined_status(base)
    if current["state_counts"] != {Recovery.COMPLETE: P.EXPECTED_ARRAY_TASKS} or (
        current["complete_cells"] != P.CELL_COUNT
    ):
        raise ExecutionError("execution is not a complete structural matrix")
    recovery = None
    if current["recovery_job_id"] is not None:
        _, recovery = load_recovery_launch(base, verify_live=True)
    return {
        "schema": EXECUTION_SCHEMA,
        **current,
        "scheduler_contract": Transport.scheduler_contract(
            _load_freeze()[0], P.ACCOUNT
        ),
        "dynamic_cell_manifest": _dynamic_manifest(),
        "hardware": _hardware_summary(),
        "primary_log_manifest": _primary_log_manifest(),
        "recovery_log_manifest": _recovery_log_manifest(recovery),
    }


def seal_execution(base) -> str:
    if EXECUTION_RECEIPT_PIN.exists() or EXECUTION_RECEIPT_PIN.is_symlink():
        raise ExecutionError("execution receipt is already pinned")
    value = _live_execution_value(base)
    if not EXECUTION_RECEIPT.exists():
        _write_json(EXECUTION_RECEIPT, value, "execution receipt")
    raw, receipt = _read_json(EXECUTION_RECEIPT, "execution receipt")
    if receipt != _live_execution_value(base):
        raise ExecutionError("execution changed while sealing")
    digest = hashlib.sha256(raw).hexdigest()
    _write_bytes(
        EXECUTION_RECEIPT_PIN, (digest + "\n").encode("ascii"),
        "execution receipt pin",
    )
    return digest


def _validate_accounting_rows(
    rows: object, contracts: object, *, tasks: list[int], job_id: str,
    job_name: str, freeze: dict, label: str,
) -> dict[int, dict]:
    if (
        not isinstance(rows, list) or not isinstance(contracts, list)
        or len(rows) != len(tasks) or len(contracts) != len(tasks)
        or not isinstance(job_id, str) or not job_id.isdigit()
    ):
        raise ExecutionError("{} accounting shape changed".format(label))
    expected_contract = Transport.scheduler_contract(freeze, P.ACCOUNT)
    result = {}
    for task, row, contract in zip(tasks, rows, contracts):
        if (
            not isinstance(row, dict)
            or set(row) != {
                "array_task", "job_id_raw", "state", "exit_code", "node",
                "elapsed_raw", "partition",
            }
            or type(row.get("array_task")) is not int
            or row["array_task"] != task
            or row.get("job_id_raw") != "{}_{}".format(job_id, task)
            or re.fullmatch(r"[A-Z_]+", row.get("state", "")) is None
            or re.fullmatch(r"[0-9]+:[0-9]+", row.get("exit_code", ""))
            is None
            or not isinstance(row.get("node"), str)
            or type(row.get("elapsed_raw")) is not int
            or row["elapsed_raw"] < 0
            or row.get("partition") != "fat"
            or not isinstance(contract, dict)
            or set(contract) != {
                "array_task", "account", "partition", "qos", "req_cpus",
                "req_mem", "time_limit", "state", "exit_code", "job_name",
            }
            or type(contract.get("array_task")) is not int
            or contract["array_task"] != task
            or contract.get("account") != P.ACCOUNT
            or contract.get("partition") != "fat"
            or contract.get("qos") != "normal"
            or type(contract.get("req_cpus")) is not int
            or contract["req_cpus"] != 1
            or contract.get("req_mem") != expected_contract["memory_per_cpu"]
            or contract.get("time_limit") != expected_contract["time_limit"]
            or contract.get("state") != row["state"]
            or contract.get("exit_code") != row["exit_code"]
            or contract.get("job_name") != job_name
        ):
            raise ExecutionError("{} accounting changed".format(label))
        result[task] = row
    return result


def _validate_tree_manifest(value: object, label: str) -> list[dict]:
    if not isinstance(value, dict) or set(value) != {
        "files", "file_count", "tree_sha256",
    }:
        raise ExecutionError("{} manifest shape changed".format(label))
    files = value.get("files")
    if (
        not isinstance(files, list)
        or type(value.get("file_count")) is not int
        or value["file_count"] != len(files)
        or P.SHA256_RE.fullmatch(value.get("tree_sha256", "")) is None
    ):
        raise ExecutionError("{} manifest header changed".format(label))
    paths = []
    payload = bytearray()
    for row in files:
        if (
            not isinstance(row, dict)
            or set(row) != {"path", "sha256", "size"}
            or not isinstance(row.get("path"), str)
            or P.SHA256_RE.fullmatch(row.get("sha256", "")) is None
            or type(row.get("size")) is not int or row["size"] < 0
        ):
            raise ExecutionError("{} manifest entry changed".format(label))
        relative = Path(row["path"])
        if (
            relative.is_absolute() or not relative.parts
            or ".." in relative.parts or relative.as_posix() != row["path"]
        ):
            raise ExecutionError("{} manifest path changed".format(label))
        try:
            payload.extend(row["path"].encode("ascii"))
        except UnicodeEncodeError as err:
            raise ExecutionError(
                "{} manifest path is not ASCII".format(label)
            ) from err
        payload.extend(b"\0")
        payload.extend(bytes.fromhex(row["sha256"]))
        paths.append(row["path"])
    if paths != sorted(set(paths)) or hashlib.sha256(payload).hexdigest() != value[
        "tree_sha256"
    ]:
        raise ExecutionError("{} manifest digest changed".format(label))
    return files


def _validate_dynamic_manifest(value: object) -> None:
    files = _validate_tree_manifest(value, "dynamic cell")
    names = {cell: set() for cell in range(1, P.CELL_COUNT + 1)}
    for row in files:
        parts = Path(row["path"]).parts
        if len(parts) != 3 or not re.fullmatch(r"runs-[0-9]{5}-[0-9]{5}", parts[0]) \
                or re.fullmatch(r"[0-9]{5}", parts[1]) is None \
                or Path(parts[2]).name != parts[2] \
                or parts[2] in Recovery.STATIC_RUN_NAMES:
            raise ExecutionError("dynamic cell manifest path changed")
        cell = int(parts[1])
        if cell not in names or _run_directory(cell).relative_to(
            Runner.EXPERIMENT_PATH
        ).parts != parts[:2]:
            raise ExecutionError("dynamic cell manifest mapping changed")
        names[cell].add(parts[2])
    required = {
        "driver.log", "driver.err", P.SELECTOR_TRACE,
        RunCell.HARDWARE_ATTESTATION_NAME,
    }
    if any(not required <= names[cell] for cell in names):
        raise ExecutionError("dynamic cell manifest is incomplete")


def _validate_execution_value(
    receipt: object, freeze: dict, freeze_sha: str, launch_sha: str,
) -> None:
    keys = {
        "schema", "freeze_sha256", "primary_launch_receipt_sha256",
        "primary_job_id", "primary_scheduler_rows",
        "primary_scheduler_contract_rows", "recovery_launch_receipt_sha256",
        "recovery_job_id", "recovery_source_snapshot_sha256",
        "recovery_scheduler_rows", "recovery_scheduler_contract_rows",
        "effective_entries", "effective_entries_sha256", "state_counts",
        "complete_cells", "started_cells", "scheduler_contract",
        "dynamic_cell_manifest", "primary_log_manifest",
        "recovery_log_manifest", "hardware",
    }
    if (
        not isinstance(receipt, dict) or set(receipt) != keys
        or receipt.get("schema") != EXECUTION_SCHEMA
        or receipt.get("freeze_sha256") != freeze_sha
        or receipt.get("primary_launch_receipt_sha256") != launch_sha
        or receipt.get("scheduler_contract")
        != Transport.scheduler_contract(freeze, P.ACCOUNT)
        or receipt.get("state_counts")
        != {Recovery.COMPLETE: P.EXPECTED_ARRAY_TASKS}
        or receipt.get("complete_cells") != P.CELL_COUNT
        or receipt.get("started_cells") != P.CELL_COUNT
    ):
        raise ExecutionError("execution receipt semantics changed")
    try:
        RunCell.validate_hardware_summary(
            receipt.get("hardware"), P.CELL_COUNT
        )
    except RunCell.RunCellError as err:
        raise ExecutionError("execution hardware summary changed") from err
    primary_job = receipt.get("primary_job_id")
    tasks = list(range(1, P.EXPECTED_ARRAY_TASKS + 1))
    primary_rows = _validate_accounting_rows(
        receipt.get("primary_scheduler_rows"),
        receipt.get("primary_scheduler_contract_rows"), tasks=tasks,
        job_id=primary_job, job_name=Runner.EXPECTED_JOB_NAME, freeze=freeze,
        label="primary scheduler",
    )
    recovery_sha = receipt.get("recovery_launch_receipt_sha256")
    recovery_job = receipt.get("recovery_job_id")
    source_snapshot_sha = receipt.get("recovery_source_snapshot_sha256")
    recovery_rows_value = receipt.get("recovery_scheduler_rows")
    recovery_contracts = receipt.get("recovery_scheduler_contract_rows")
    if recovery_sha is None:
        if any(value not in (None, []) for value in (
            recovery_job, source_snapshot_sha, recovery_rows_value,
            recovery_contracts,
        )):
            raise ExecutionError("absent recovery receipt is inconsistent")
        recovery_tasks = []
        recovery_rows = {}
    else:
        if (
            P.SHA256_RE.fullmatch(recovery_sha or "") is None
            or not isinstance(recovery_rows_value, list)
            or not recovery_rows_value
            or not isinstance(recovery_contracts, list)
            or not isinstance(recovery_job, str) or not recovery_job.isdigit()
            or P.SHA256_RE.fullmatch(source_snapshot_sha or "") is None
        ):
            raise ExecutionError("recovery receipt binding changed")
        recovery_tasks = [row.get("array_task") for row in recovery_rows_value]
        if any(type(task) is not int for task in recovery_tasks) or (
            recovery_tasks != sorted(set(recovery_tasks))
        ):
            raise ExecutionError("recovery scheduler task set changed")
        recovery_rows = _validate_accounting_rows(
            recovery_rows_value, recovery_contracts, tasks=recovery_tasks,
            job_id=recovery_job,
            job_name="pdb-terminal-metric-choice-recovery-0001",
            freeze=freeze, label="recovery scheduler",
        )
    entries = receipt.get("effective_entries")
    if (
        not isinstance(entries, list) or len(entries) != len(tasks)
        or receipt.get("effective_entries_sha256") != hashlib.sha256(
            P.canonical_json(entries)
        ).hexdigest()
    ):
        raise ExecutionError("effective execution matrix changed")
    for task, entry in zip(tasks, entries):
        recovered = task in recovery_rows
        expected_job = recovery_job if recovered else primary_job
        expected_attempt = 2 if recovered else 1
        triad = list(P.triad_cells(task))
        if (
            not isinstance(entry, dict)
            or set(entry) != {
                "array_task", "attempt", "job_id", "state",
                "started_cells", "completed_cells",
            }
            or type(entry.get("array_task")) is not int
            or entry["array_task"] != task
            or type(entry.get("attempt")) is not int
            or entry["attempt"] != expected_attempt
            or entry.get("job_id") != expected_job
            or entry.get("state") != Recovery.COMPLETE
            or entry.get("started_cells") != triad
            or entry.get("completed_cells") != triad
        ):
            raise ExecutionError("effective execution entry changed")
        selected = recovery_rows.get(task, primary_rows[task])
        if _classify(selected, triad, triad) != Recovery.COMPLETE:
            raise ExecutionError("effective execution is not terminal-complete")
        if recovered and primary_rows[task]["state"] not in INFRASTRUCTURE_STATES:
            raise ExecutionError("recovery source is not infrastructural")
    _validate_dynamic_manifest(receipt.get("dynamic_cell_manifest"))
    primary_logs = _validate_tree_manifest(
        receipt.get("primary_log_manifest"), "primary Slurm log"
    )
    if [row["path"] for row in primary_logs] != ["slurm.err", "slurm.log"]:
        raise ExecutionError("primary Slurm log manifest changed")
    if recovery_sha is None:
        if receipt.get("recovery_log_manifest") is not None:
            raise ExecutionError("absent recovery has a log manifest")
    else:
        recovery_logs = _validate_tree_manifest(
            receipt.get("recovery_log_manifest"), "recovery Slurm log"
        )
        expected_logs = sorted(
            "recovery-slurm-{}_{}.{}".format(recovery_job, task, suffix)
            for task in recovery_tasks for suffix in ("err", "out")
        )
        if [row["path"] for row in recovery_logs] != expected_logs:
            raise ExecutionError("recovery Slurm log manifest changed")


def load_execution_receipt(
    base=None, *, verify_live: bool = True,
) -> tuple[str, dict]:
    if base is None:
        base = Runner.configure_lab_transport(P.FREEZE_PATH)
    raw, receipt = _read_json(EXECUTION_RECEIPT, "execution receipt")
    try:
        pin = CampaignIO.read_regular_exact(
            EXECUTION_RECEIPT_PIN, expected=EXECUTION_RECEIPT_PIN,
            label="execution receipt pin",
        ).raw
    except CampaignIO.CampaignIOError as err:
        raise ExecutionError("execution receipt is not pinned") from err
    digest = hashlib.sha256(raw).hexdigest()
    freeze, freeze_sha = _load_freeze()
    launch_sha, _ = load_primary_launch(base, verify_live=verify_live)
    _validate_execution_value(receipt, freeze, freeze_sha, launch_sha)
    if pin != (digest + "\n").encode("ascii"):
        raise ExecutionError("execution receipt semantics changed")
    recovery_sha = receipt["recovery_launch_receipt_sha256"]
    if recovery_sha is not None:
        actual_sha, recovery = load_recovery_launch(
            base, verify_live=verify_live
        )
        if (
            actual_sha != recovery_sha
            or recovery["job_id"] != receipt["recovery_job_id"]
            or recovery["source_snapshot_sha256"]
            != receipt["recovery_source_snapshot_sha256"]
        ):
            raise ExecutionError("execution recovery binding changed")
    if verify_live and receipt != _live_execution_value(base):
        raise ExecutionError("sealed execution changed")
    return digest, receipt


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=(
        "status", "snapshot", "recover", "recover-reconcile", "seal",
    ))
    args = parser.parse_args(argv)
    base = Runner.configure_lab_transport(P.FREEZE_PATH)
    if args.command == "status":
        result = status(base)
    elif args.command == "snapshot":
        result = {"scheduler_snapshot_sha256": publish_primary_snapshot(base)}
    elif args.command == "recover":
        result = launch_recovery(base)
    elif args.command == "recover-reconcile":
        result = recover_recovery_launch(base)
    else:
        result = {"execution_receipt_sha256": seal_execution(base)}
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        ExecutionError, P.ProtocolError, Runner.RunnerError,
        Recovery.RecoveryError, Transport.TransportError, JJ.JjCacheError,
    ) as err:
        print("error: {}".format(err), file=os.sys.stderr)
        raise SystemExit(2)
