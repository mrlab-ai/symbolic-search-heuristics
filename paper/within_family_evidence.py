"""Project the sealed fresh within-family Confirmation A into paper evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from collections.abc import Mapping

import terminal_incidence_evidence as E

if hasattr(sys, "set_int_max_str_digits"):
    sys.set_int_max_str_digits(100000)


REPO = Path(__file__).resolve().parent.parent
EXPERIMENTS = REPO / "experiments"
BASE = "experiments/artifacts/pdb-within-family-confirmation-v1"
PATHS = {
    "freeze": BASE + "/cohort-freeze.json",
    "seal": BASE + "/confirmation-a/completion-seal.json",
    "analysis": BASE + "/confirmation-a/analysis.json",
    "repeat": BASE + "/confirmation-a/analysis-repeat.json",
    "receipt": BASE + "/confirmation-a/analysis-receipt.json",
    "launch": BASE + "/confirmation-a/launch.json",
    # The terminal poll is timestamped by the completed campaign.  Its path
    # is obtained from the committed completion seal; no filename is guessed.
    "poll": None,
}
PRODUCTION_RESULTS_REVISION = "141f32e908868ed19f9056b612164cf1bdc3fdc4"
PRODUCTION_ARTIFACT_PINS = {
    "freeze": "0c95dd5afe61ea0f77c7441a824bcecbe255641994874d28734274a64e3a0c67",
    "seal": "f36c24c2ba89cab1e7c3aaf6868f0e481ee45a0d3192142e977574386145577d",
    "analysis": "8cc48ae1866688dbb6082eda8e892078c7dfaaf152af34188c98c9aad0d6323b",
    "repeat": "8cc48ae1866688dbb6082eda8e892078c7dfaaf152af34188c98c9aad0d6323b",
    "receipt": "e86a74ba849fd0ecc275ac3cdbe01f721000bfbba257a63436f41c43787dab64",
    "launch": "47922017ce4ca0b86233005723da29e433826a2360879b300e3194a7876ac881",
    "poll": "c48ed72a2b6cf93ffce93e324e965f67b5cc74c9a6010b5b3001f662ff96532e",
    "recovery": "67c53a22081eb7329f8f9e9abed64a38461923985b772f696dbb43acfa9de937",
}
SCHEMA = "pdb-terminal-incidence-within-family-evidence/v1"
COMMIT_RE = re.compile(r"[0-9a-f]{40}")
RECOVERY_PYTHON_SHA256 = "021044895e95be79dc2f110367607e684119afbc8ce75f6f0eec94844e0acec7"
RECOVERY_OUTPUT = (REPO / BASE / "confirmation-a").resolve()
RECOVERY_EXPERIMENT = (EXPERIMENTS / "data/exp_pdb_within_family_a_v1").resolve()
RECOVERY_PROPERTIES = Path(str(RECOVERY_EXPERIMENT) + "-eval/properties").resolve()
RECOVERY_PYTHON = (EXPERIMENTS / "data/pdb-terminal-incidence-shadow-venv/bin/python").absolute()
RECOVERY_INTERPRETER = RECOVERY_PYTHON.resolve()
RECOVERY_ANALYSIS = (EXPERIMENTS / "pdb_within_family_a_analysis.py").resolve()
RECOVERY_WRAPPER = (EXPERIMENTS / "pdb_within_family_recover_a_serialization.py").resolve()
RECOVERY_INVOCATION = (RECOVERY_OUTPUT / "serialization-recovery-venv-invocation.json").resolve()
RECOVERY_ENVIRONMENT = {
    "unset": ["PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV"],
    "set": {"LANG": "C", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0", "PYTHONNOUSERSITE": "1"},
}
SERIALIZATION_ERROR = (
    "ValueError: Exceeds the limit (4300 digits) for integer string conversion; "
    "use sys.set_int_max_str_digits() to increase the limit"
)


class EvidenceError(ValueError):
    pass


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(raw, label):
    return E._canonical(raw, label)


def _is_path(value, expected):
    return type(value) is str and Path(value).resolve() == expected


def _snapshot_reader():
    if str(EXPERIMENTS) not in sys.path:
        sys.path.insert(0, str(EXPERIMENTS))
    from pdb_terminal_incidence_v12_snapshot_reader import read_committed_snapshot
    return read_committed_snapshot


def _pins(pins):
    if type(pins) is not dict or not set(PATHS) <= set(pins) or not (set(pins) - set(PATHS)) <= {"recovery"}:
        raise EvidenceError("within-family artifact-pin roles changed")
    for role, value in pins.items():
        if type(value) is not str or E.R.SHA256_RE.fullmatch(value) is None or value == E.R.ZERO_SHA256:
            raise EvidenceError(f"within-family artifact pin is unset: {role}")


def _read(revision, pins):
    if type(revision) is not str or COMMIT_RE.fullmatch(revision) is None:
        raise EvidenceError("within-family results revision must be an explicit 40-hex commit")
    _pins(pins)
    reader = _snapshot_reader()
    fixed_paths = [path for path in PATHS.values() if path is not None]
    committed = reader(revision, fixed_paths)
    seal = _canonical(committed[PATHS["seal"]], "within-family completion seal")
    try:
        poll_path = seal["evidence"]["poll"]["path"]
        poll_relative = Path(poll_path).resolve().relative_to(REPO).as_posix()
    except (KeyError, OSError, ValueError, TypeError) as error:
        raise EvidenceError("completion seal does not identify its terminal poll") from error
    if poll_relative in fixed_paths or poll_relative.startswith(".jj/"):
        raise EvidenceError("terminal poll path is ambiguous")
    committed[poll_relative] = reader(revision, [poll_relative])[poll_relative]
    paths = dict(PATHS, poll=poll_relative)
    seal_schema = seal.get("schema")
    recovery_path = None
    if seal_schema == "pdb-terminal-incidence-within-family-a-seal/v2-serialization-recovery":
        if "recovery" not in pins:
            raise EvidenceError("serialization-recovery seal requires a recovery pin")
        try:
            recovery_path = Path(seal["evidence"]["recovery"]["path"]).resolve().relative_to(REPO).as_posix()
        except (KeyError, OSError, ValueError, TypeError) as error:
            raise EvidenceError("serialization-recovery seal does not identify its receipt") from error
        committed[recovery_path] = reader(revision, [recovery_path])[recovery_path]
        paths["recovery"] = recovery_path
        recovery = _canonical(committed[recovery_path], "serialization-recovery receipt")
        try:
            invocation_path = Path(recovery["invocation"]["path"]).resolve().relative_to(REPO).as_posix()
            stdout_path = Path(recovery["evidence"]["stdout"]["path"]).resolve().relative_to(REPO).as_posix()
            stderr_path = Path(recovery["evidence"]["stderr"]["path"]).resolve().relative_to(REPO).as_posix()
            wrapper_path = Path(recovery["immutable_code"]["recovery_wrapper"]["path"]).resolve().relative_to(REPO).as_posix()
            wrapper_revision = recovery["immutable_code"]["recovery_wrapper"]["committed_revision"]
        except (KeyError, OSError, ValueError, TypeError) as error:
            raise EvidenceError("serialization-recovery receipt paths are malformed") from error
        committed.update(reader(revision, [invocation_path, stdout_path, stderr_path]))
        wrapper_reader = _snapshot_reader()
        committed[wrapper_path] = wrapper_reader(wrapper_revision, [wrapper_path])[wrapper_path]
        paths.update(invocation=invocation_path, stdout=stdout_path, stderr=stderr_path,
                     wrapper=wrapper_path)
    elif "recovery" in pins:
        raise EvidenceError("recovery pin requires a serialization-recovery seal")
    result = {}
    pinned_roles = set(PATHS) | ({"recovery"} if "recovery" in paths else set())
    for role in pinned_roles:
        path = paths[role]
        raw = committed[path]
        if _sha(raw) != pins[role]:
            raise EvidenceError(f"committed within-family artifact differs from its pin: {role}")
        result[role] = raw
    for role in set(paths) - pinned_roles:
        result[role] = committed[paths[role]]
    return result


def _code_closure(freeze, revision):
    code = freeze.get("code_sha256")
    commit = freeze.get("code_commit")
    if type(code) is not dict or type(commit) is not str or COMMIT_RE.fullmatch(commit) is None:
        raise EvidenceError("within-family scientific code identity is incomplete")
    paths = ["experiments/" + name for name in code]
    snapshot = _snapshot_reader()(commit, paths)
    for name, digest in code.items():
        if type(digest) is not str or E.R.SHA256_RE.fullmatch(digest) is None:
            raise EvidenceError("within-family scientific code digest is malformed")
        if _sha(snapshot["experiments/" + name]) != digest:
            raise EvidenceError(f"within-family scientific code differs from freeze: {name}")
    return commit


def _validate_seal(seal, artifacts, analysis, freeze):
    recovered = seal.get("schema") == "pdb-terminal-incidence-within-family-a-seal/v2-serialization-recovery"
    if seal.get("schema") not in {
            "pdb-terminal-incidence-within-family-a-seal/v1",
            "pdb-terminal-incidence-within-family-a-seal/v2-serialization-recovery"}:
        raise EvidenceError("within-family completion seal schema changed")
    if seal.get("scope") != "fresh-instances-within-previously-studied-families":
        raise EvidenceError("within-family scope changed")
    matrix = seal.get("matrix")
    if not isinstance(matrix, dict) or matrix.get("tasks") != 650 or matrix.get("cells") != 2600 or matrix.get("configs") != 4:
        raise EvidenceError("within-family completion matrix changed")
    evidence = seal.get("evidence")
    if not isinstance(evidence, dict):
        raise EvidenceError("within-family completion evidence is missing")
    expected = {"freeze", "launch", "poll", "analysis", "repeat", "receipt", "properties"}
    if recovered:
        expected.add("recovery")
    if set(evidence) != expected:
        raise EvidenceError("within-family completion evidence roles changed")
    for role in ("freeze", "launch", "poll", "analysis", "repeat", "receipt"):
        record = evidence[role]
        if not isinstance(record, dict) or record.get("sha256") != _sha(artifacts[role]):
            raise EvidenceError(f"within-family completion seal does not bind {role}")
    if recovered and seal["evidence"]["recovery"].get("sha256") != _sha(artifacts["recovery"]):
        raise EvidenceError("within-family completion seal does not bind recovery")
    if seal.get("code_commit") != freeze.get("code_commit"):
        raise EvidenceError("within-family completion code identity changed")
    if seal.get("evidence", {}).get("properties", {}).get("sha256") != analysis.get("input", {}).get("properties_sha256"):
        raise EvidenceError("within-family properties digest is not bound")
    passed = analysis["gates"].get("pass")
    if type(passed) is not bool or seal.get("decision") != ("PASS" if passed else "FAIL"):
        raise EvidenceError("within-family completion decision disagrees with analysis")
    if seal.get("selector_experiments_authorized") is not passed:
        raise EvidenceError("within-family selector authorization disagrees with A")


def _validate_level_allocations(freeze):
    if freeze.get("level_allocation_rule") != "balanced-supported-levels-ascending/v1":
        raise EvidenceError("within-family level allocation rule changed")
    allocations = freeze.get("level_allocations")
    tasks = freeze.get("tasks")
    if not isinstance(allocations, dict) or not isinstance(tasks, dict):
        raise EvidenceError("within-family level allocations are missing")
    expected = {}
    for role, rows in tasks.items():
        if not isinstance(rows, list):
            raise EvidenceError("within-family task rows are malformed")
        role_counts = {}
        for row in rows:
            family, level = row.get("family"), row.get("level")
            if type(family) is not str or type(level) is not int or not 0 <= level < 5:
                raise EvidenceError("within-family task level identity is malformed")
            family_counts = role_counts.setdefault(family, {str(index): 0 for index in range(5)})
            family_counts[str(level)] += 1
        if allocations.get(role) != role_counts:
            raise EvidenceError("within-family level allocations disagree with selected tasks")
        for family, counts in role_counts.items():
            values = list(counts.values())
            if max(values) - min(values) > 1:
                raise EvidenceError("within-family level allocation is not balanced")
        expected[role] = role_counts
    if allocations != expected:
        raise EvidenceError("within-family level allocation roles changed")


def _validate_pipeline(launch, poll, *, recovered=False):
    if not isinstance(launch, dict) or not isinstance(poll, dict):
        raise EvidenceError("within-family scheduler evidence is malformed")
    if launch.get("schema") != "pdb-within-family-launch/v1" or poll.get("schema") != "pdb-within-family-poll/v1":
        raise EvidenceError("within-family scheduler schemas changed")
    jobs = launch.get("jobs")
    if not isinstance(jobs, list):
        raise EvidenceError("within-family launch jobs are missing")
    expected = {"01-build": 1, "02-start": 867, "03-parse": 1,
                "04-fetch": 1, "05-report": 1, "06-analyze": 1}
    actual = {}
    for job in jobs:
        matches = [step for step in expected if str(job.get("job_file", "")).endswith("-" + step)]
        if len(matches) != 1 or matches[0] in actual:
            raise EvidenceError("within-family pipeline shape changed")
        actual[matches[0]] = job.get("array_elements")
    if actual != expected:
        raise EvidenceError("within-family pipeline shape changed")
    accounting = poll.get("queries", {}).get("accounting")
    if not isinstance(accounting, dict) or accounting.get("returncode") != 0:
        raise EvidenceError("within-family scheduler accounting query failed")
    if poll.get("launch_sha256") != _sha(_canonical_bytes(launch)):
        raise EvidenceError("within-family launch/poll identity changed")
    if str(launch.get("experiment", "")) == "":
        raise EvidenceError("within-family launch experiment is missing")
    if str(EXPERIMENTS) not in sys.path:
        sys.path.insert(0, str(EXPERIMENTS))
    import pdb_within_family_cohort as C
    check = C.Monitor.check_accounting(launch, accounting.get("stdout", ""))
    if not check["resources_match"] or check["observed_elements"] != 872:
        raise EvidenceError("within-family scheduler pipeline identities/resources changed")
    if recovered:
        analysis_ids = {job["job_id"] for job in jobs
                        if str(job.get("job_file", "")).endswith("-06-analyze")}
        if len(analysis_ids) != 1:
            raise EvidenceError("within-family analysis job identity changed")
        for identity, row in check["rows"].items():
            if identity.rsplit("_", 1)[0] in analysis_ids:
                if row["state"] != "FAILED" or row["exit"] != "1:0":
                    raise EvidenceError("original A analysis failure changed")
            elif row["state"] != "COMPLETED" or row["exit"] != "0:0":
                raise EvidenceError("within-family pre-analysis pipeline failed")
    elif not check["all_completed_successfully"]:
        raise EvidenceError("within-family scheduler pipeline did not complete successfully")


def _validate_recovery(receipt, artifacts, freeze, analysis, launch, poll):
    for role in ("wrapper", "invocation", "stdout", "stderr"):
        if role not in artifacts:
            raise EvidenceError(f"serialization-recovery {role} artifact is missing")
    if receipt.get("schema") != "pdb-terminal-incidence-within-family-a-serialization-recovery/v1":
        raise EvidenceError("serialization-recovery receipt schema changed")
    if (receipt.get("integer_max_str_digits") != 100000
            or receipt.get("scheduler_queries_made_by_recovery") != 0
            or receipt.get("scientific_runs_repeated") != 0):
        raise EvidenceError("serialization-recovery execution contract changed")
    failure = receipt.get("original_analysis_failure")
    analysis_jobs = [job for job in launch.get("jobs", []) if str(job.get("job_file", "")).endswith("-06-analyze")]
    if (not isinstance(failure, dict) or len(analysis_jobs) != 1
            or failure.get("step") != "06-analyze"
            or failure.get("job_id") != analysis_jobs[0].get("job_id")
            or failure.get("state") != "FAILED" or failure.get("exit") != "1:0"
            or failure.get("accounting_id") != f"{analysis_jobs[0].get('job_id')}_1"
            or failure.get("error") != SERIALIZATION_ERROR):
            raise EvidenceError("serialization-recovery original failure proof changed")
    poll_logs = poll.get("pipeline_logs", {})
    error_tail = poll_logs.get("slurm.err", {}).get("tail", "") if isinstance(poll_logs, dict) else ""
    if error_tail.count(SERIALIZATION_ERROR) != 1:
        raise EvidenceError("serialization-recovery original error is not retained")
    immutable = receipt.get("immutable_code")
    if (not isinstance(immutable, dict) or immutable.get("frozen_commit") != freeze.get("code_commit")
            or immutable.get("frozen_code_sha256") != freeze.get("code_sha256")
            or not isinstance(immutable.get("recovery_wrapper"), dict)):
        raise EvidenceError("serialization-recovery input identity changed")
    wrapper = immutable["recovery_wrapper"]
    if (wrapper.get("sha256") != _sha(artifacts["wrapper"])
            or not COMMIT_RE.fullmatch(str(wrapper.get("committed_revision", "")))
            or not _is_path(wrapper.get("path"), RECOVERY_WRAPPER)):
        raise EvidenceError("serialization-recovery wrapper identity changed")
    invocation = receipt.get("invocation")
    if (not isinstance(invocation, dict) or invocation.get("sha256") != _sha(artifacts["invocation"])
            or not E.R.SHA256_RE.fullmatch(str(invocation.get("sha256", "")))
            or not _is_path(invocation.get("path"), RECOVERY_INVOCATION)):
        raise EvidenceError("serialization-recovery invocation did not succeed")
    invocation_json = _canonical(artifacts["invocation"], "serialization-recovery invocation")
    command = invocation_json.get("command")
    interpreter = invocation_json.get("interpreter")
    expected_command = [str(RECOVERY_PYTHON), "-X", "int_max_str_digits=100000", "-B",
                        str(RECOVERY_ANALYSIS), "--properties", str(RECOVERY_PROPERTIES),
                        "--output", str(RECOVERY_OUTPUT)]
    if (invocation_json.get("schema") != "pdb-terminal-incidence-within-family-a-serialization-recovery/v1/invocation"
            or invocation_json.get("returncode") != 0
            or invocation_json.get("timed_out") is not False
            or invocation_json.get("integer_max_str_digits") != 100000
            or command != expected_command
            or invocation_json.get("cwd") != str(EXPERIMENTS.resolve())
            or invocation_json.get("environment") != RECOVERY_ENVIRONMENT
            or not isinstance(interpreter, dict)
            or interpreter.get("path") != str(RECOVERY_INTERPRETER)):
        raise EvidenceError("serialization-recovery invocation changed")
    if interpreter.get("sha256") != RECOVERY_PYTHON_SHA256:
        raise EvidenceError("serialization-recovery interpreter identity changed")
    if (invocation_json.get("stdout_sha256") != _sha(artifacts["stdout"])
            or invocation_json.get("stderr_sha256") != _sha(artifacts["stderr"])):
        raise EvidenceError("serialization-recovery invocation logs changed")
    try:
        started = datetime.fromisoformat(invocation_json["started_utc"])
        ended = datetime.fromisoformat(invocation_json["ended_utc"])
    except (KeyError, TypeError, ValueError) as error:
        raise EvidenceError("serialization-recovery invocation times changed") from error
    if (started.tzinfo is None or ended.tzinfo is None or
            started.utcoffset() is None or ended.utcoffset() is None or ended < started):
        raise EvidenceError("serialization-recovery invocation times changed")
    evidence = receipt.get("evidence")
    if not isinstance(evidence, dict):
        raise EvidenceError("serialization-recovery evidence bindings are missing")
    expected = {"freeze", "launch", "poll", "properties", "analysis", "repeat", "analysis_receipt", "stdout", "stderr"}
    if set(evidence) != expected:
        raise EvidenceError("serialization-recovery evidence roles changed")
    expected_paths = {
        "freeze": (REPO / PATHS["freeze"]).resolve(),
        "launch": (REPO / PATHS["launch"]).resolve(),
        "poll": (RECOVERY_OUTPUT / "poll-20260914T211529Z.json").resolve(),
        "properties": RECOVERY_PROPERTIES,
        "analysis": (RECOVERY_OUTPUT / "analysis.json").resolve(),
        "repeat": (RECOVERY_OUTPUT / "analysis-repeat.json").resolve(),
        "analysis_receipt": (RECOVERY_OUTPUT / "analysis-receipt.json").resolve(),
        "stdout": (RECOVERY_OUTPUT / "serialization-recovery-venv.stdout").resolve(),
        "stderr": (RECOVERY_OUTPUT / "serialization-recovery-venv.stderr").resolve(),
    }
    if any(not isinstance(evidence[role], dict)
           or not _is_path(evidence[role].get("path"), path)
           for role, path in expected_paths.items()):
        raise EvidenceError("serialization-recovery evidence paths changed")
    for role, artifact_role in (("freeze", "freeze"), ("launch", "launch"), ("poll", "poll"),
                                ("analysis", "analysis"), ("repeat", "repeat"),
                                ("analysis_receipt", "receipt")):
        if evidence[role].get("sha256") != _sha(artifacts[artifact_role]):
            raise EvidenceError(f"serialization-recovery {role} binding changed")
    if (evidence["stdout"].get("sha256") != _sha(artifacts["stdout"])
            or evidence["stderr"].get("sha256") != _sha(artifacts["stderr"])):
        raise EvidenceError("serialization-recovery invocation logs changed")
    if (evidence["properties"].get("sha256") != analysis.get("input", {}).get("properties_sha256")
            or command[6] != evidence["properties"].get("path")
            or command[8] != str(Path(evidence["analysis"].get("path", "")).parent)):
        raise EvidenceError("serialization-recovery outputs are not bound")


def _canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode("ascii")


def load_evidence(*, results_revision=PRODUCTION_RESULTS_REVISION,
                  artifact_pins=PRODUCTION_ARTIFACT_PINS):
    artifacts = _read(results_revision, artifact_pins)
    freeze = _canonical(artifacts["freeze"], "within-family freeze")
    seal = _canonical(artifacts["seal"], "within-family completion seal")
    analysis_raw = artifacts["analysis"]
    if analysis_raw != artifacts["repeat"]:
        raise EvidenceError("within-family analyses are not byte-identical")
    analysis = _canonical(analysis_raw, "within-family analysis")
    receipt = _canonical(artifacts["receipt"], "within-family analysis receipt")
    if freeze.get("schema") != "pdb-terminal-incidence-within-family-cohort/v1/freeze" or freeze.get("performance_observed") is not False:
        raise EvidenceError("within-family freeze identity changed")
    if analysis.get("schema") != "pdb-terminal-incidence-within-family-a-analysis/v1" or analysis.get("scope") != freeze.get("scope"):
        raise EvidenceError("within-family analysis schema or scope changed")
    if analysis.get("freeze_sha256") != _sha(artifacts["freeze"]):
        raise EvidenceError("within-family analysis freeze identity changed")
    settings = freeze.get("analysis")
    if settings != {"minimum_eligible_tasks": 300, "minimum_comparison_tasks": 300,
                    "minimum_families": 25, "minimum_target_strict_pairs": 600,
                    "minimum_concordance": [13, 20], "minimum_advantage": [1, 50],
                    "bootstrap_replicates": 100000, "bootstrap_seed": 20260901,
                    "horizon": 16, "unseen_family_gate": False}:
        raise EvidenceError("within-family statistical settings changed")
    if receipt.get("schema") != "pdb-terminal-incidence-within-family-a-analysis/v1/double-execution" or receipt.get("scheduler_audit_required_before_selector_launch") is not True:
        raise EvidenceError("within-family analysis receipt schema changed")
    if receipt.get("analysis_sha256") != _sha(analysis_raw) or receipt.get("repeat_sha256") != _sha(artifacts["repeat"]):
        raise EvidenceError("within-family analysis receipt is inconsistent")
    if receipt.get("byte_identical") is not True or receipt.get("freeze_sha256") != _sha(artifacts["freeze"]):
        raise EvidenceError("within-family analysis receipt is inconsistent")
    if receipt.get("properties_sha256") != analysis.get("input", {}).get("properties_sha256"):
        raise EvidenceError("within-family properties digest is not consistent")
    if analysis.get("matrix") != seal.get("matrix") or analysis.get("matrix", {}).get("families") != len(freeze.get("families", [])):
        raise EvidenceError("within-family analysis matrix changed")
    if analysis.get("input", {}).get("code_commit") != freeze.get("code_commit") or analysis.get("input", {}).get("code_sha256") != freeze.get("code_sha256"):
        raise EvidenceError("within-family analysis code identity changed")
    _validate_seal(seal, artifacts, analysis, freeze)
    launch = _canonical(artifacts["launch"], "within-family launch")
    poll = _canonical(artifacts["poll"], "within-family poll")
    if seal.get("schema") == "pdb-terminal-incidence-within-family-a-seal/v2-serialization-recovery":
        recovery = _canonical(artifacts["recovery"], "serialization-recovery receipt")
        _validate_recovery(recovery, artifacts, freeze, analysis, launch, poll)
        if seal.get("original_scheduler_analysis") != recovery.get("original_analysis_failure"):
            raise EvidenceError("serialization-recovery seal does not retain original failure")
        _validate_pipeline(launch, poll, recovered=True)
    else:
        _validate_pipeline(launch, poll)
    _code_closure(freeze, results_revision)
    if freeze.get("scope") != "fresh-instances-within-previously-studied-families":
        raise EvidenceError("within-family scope changed")
    if freeze.get("targets") != {"a": 650} or len(freeze.get("tasks", {}).get("a", [])) != 650:
        raise EvidenceError("within-family cohort size changed")
    _validate_level_allocations(freeze)
    normalized = E.normalize_a(analysis, include_prior=False)
    passed = analysis["gates"].get("pass")
    if (type(passed) is not bool or analysis["gates"].get("primary", {}).get("pass") is not passed
            or analysis.get("statistical_selector_gate_passed") is not passed
            or analysis["gates"].get("decision") != ("PASS" if passed else "FAIL")
            or normalized.get("sealed") is not True):
        raise EvidenceError("within-family A decision is malformed")
    validation_source = {"a_tasks": 650, "a_families": len(freeze["families"])}
    try:
        E.R._validate_a(normalized, validation_source, include_prior=False)
        recomputed = E.R._a_gate(normalized, include_prior=False)
    except Exception as error:
        raise EvidenceError("within-family normalized A evidence is invalid") from error
    if recomputed is not passed:
        raise EvidenceError("within-family numerical A decision disagrees with analysis")
    return {
        "design": "within-family-v1",
        "a_pass": passed,
        "confirmation_a": normalized,
        "source": {
            "families": list(freeze.get("families", [])),
            "tasks": 650,
            "candidate_status_counts": freeze.get("source_status_counts"),
            "freeze": freeze,
        },
    }


__all__ = ["EvidenceError", "PATHS", "PRODUCTION_ARTIFACT_PINS",
           "PRODUCTION_RESULTS_REVISION", "load_evidence"]
