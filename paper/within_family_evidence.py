"""Project the sealed fresh within-family Confirmation A into paper evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from collections.abc import Mapping

import terminal_incidence_evidence as E


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
PRODUCTION_RESULTS_REVISION = None
PRODUCTION_ARTIFACT_PINS = {}
SCHEMA = "pdb-terminal-incidence-within-family-evidence/v1"
COMMIT_RE = re.compile(r"[0-9a-f]{40}")


class EvidenceError(ValueError):
    pass


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(raw, label):
    return E._canonical(raw, label)


def _snapshot_reader():
    if str(EXPERIMENTS) not in sys.path:
        sys.path.insert(0, str(EXPERIMENTS))
    from pdb_terminal_incidence_v12_snapshot_reader import read_committed_snapshot
    return read_committed_snapshot


def _pins(pins):
    if type(pins) is not dict or set(pins) != set(PATHS):
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
    result = {}
    for role, path in paths.items():
        raw = committed[path]
        if _sha(raw) != pins[role]:
            raise EvidenceError(f"committed within-family artifact differs from its pin: {role}")
        result[role] = raw
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
    if seal.get("schema") != "pdb-terminal-incidence-within-family-a-seal/v1":
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
    if set(evidence) != expected:
        raise EvidenceError("within-family completion evidence roles changed")
    for role in ("freeze", "launch", "poll", "analysis", "repeat", "receipt"):
        record = evidence[role]
        if not isinstance(record, dict) or record.get("sha256") != _sha(artifacts[role]):
            raise EvidenceError(f"within-family completion seal does not bind {role}")
    if seal.get("code_commit") != freeze.get("code_commit"):
        raise EvidenceError("within-family completion code identity changed")
    if seal.get("evidence", {}).get("properties", {}).get("sha256") != analysis.get("input", {}).get("properties_sha256"):
        raise EvidenceError("within-family properties digest is not bound")
    passed = analysis["gates"].get("pass")
    if type(passed) is not bool or seal.get("decision") != ("PASS" if passed else "FAIL"):
        raise EvidenceError("within-family completion decision disagrees with analysis")
    if seal.get("selector_experiments_authorized") is not passed:
        raise EvidenceError("within-family selector authorization disagrees with A")


def _validate_pipeline(launch, poll):
    if not isinstance(launch, dict) or not isinstance(poll, dict):
        raise EvidenceError("within-family scheduler evidence is malformed")
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
    if not check["all_completed_successfully"] or not check["resources_match"]:
        raise EvidenceError("within-family scheduler pipeline did not complete successfully")


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
    _validate_pipeline(_canonical(artifacts["launch"], "within-family launch"),
                       _canonical(artifacts["poll"], "within-family poll"))
    _code_closure(freeze, results_revision)
    if freeze.get("scope") != "fresh-instances-within-previously-studied-families":
        raise EvidenceError("within-family scope changed")
    if freeze.get("targets") != {"a": 650} or len(freeze.get("tasks", {}).get("a", [])) != 650:
        raise EvidenceError("within-family cohort size changed")
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
