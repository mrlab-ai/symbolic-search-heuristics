#!/usr/bin/env python3
"""Outcome-blind resource calibration for the dual selector campaign.

The development instances are generated from this file and have reserved task
identifiers, so they cannot be members of any benchmark cohort.  The receipt
deliberately contains only trace completion and selector/probe overheads.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import subprocess
import tempfile
from pathlib import Path

import pdb_terminal_metric_choice_parser as Trace
import pdb_terminal_metric_choice_protocol as P
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_planner_manifest as PlannerManifest


class CalibrationError(RuntimeError):
    pass


TASK_SCHEMA = P.CALIBRATION_SCHEMA + "/development-tasks"
TASK_SPECS = P.CALIBRATION_TASK_SPECS
EXPOSED_FIELDS = [
    "trace_status", "probe_completed_layers", "probe_cpu_seconds",
    "probe_wall_seconds", "probe_peak_memory_before_kb",
    "probe_peak_memory_after_kb", "probe_peak_memory_delta_kb",
    "selection_cpu_seconds", "selection_wall_seconds",
    "selection_peak_memory_before_kb", "selection_peak_memory_after_kb",
    "selection_peak_memory_delta_kb",
]


def _pddl(chain_length: int) -> tuple[str, str]:
    atoms = " ".join("(p{})".format(i) for i in range(chain_length + 1))
    actions = []
    for index in range(chain_length):
        actions.append(
            "(:action step-{0} :precondition (p{0}) "
            ":effect (and (not (p{0})) (p{1})))".format(index, index + 1)
        )
    domain = """(define (domain metric-choice-chain)
(:requirements :strips)
(:predicates {atoms})
{actions}
)\n""".format(atoms=atoms, actions="\n".join(actions))
    problem = """(define (problem metric-choice-chain-{length})
(:domain metric-choice-chain)
(:init (p0))
(:goal (p{length})))
""".format(length=chain_length)
    return domain, problem


def development_manifest() -> dict:
    tasks = []
    for task_id, length in TASK_SPECS:
        domain, problem = _pddl(length)
        tasks.append({
            "task_id": task_id,
            "generator": "deterministic-strips-chain/v1",
            "chain_length": length,
            "domain_sha256": hashlib.sha256(domain.encode("ascii")).hexdigest(),
            "problem_sha256": hashlib.sha256(problem.encode("ascii")).hexdigest(),
            "eligibility": "synthetic-generated-never-benchmark-eligible",
        })
    manifest = {"schema": TASK_SCHEMA, "tasks": tasks}
    manifest["tasks_sha256"] = hashlib.sha256(
        P.canonical_json(tasks)
    ).hexdigest()
    return manifest


def development_manifest_sha256() -> str:
    return hashlib.sha256(P.canonical_json(development_manifest())).hexdigest()


def redact_certificate(task_id: str, mode: str, certificate: dict) -> dict:
    if certificate.get("status") != "complete":
        raise CalibrationError("calibration trace did not complete")
    observation = {"task_id": task_id, "mode": mode}
    for field in EXPOSED_FIELDS:
        source = field[len("trace_"):] if field.startswith("trace_") else field
        if field == "trace_status":
            observation[field] = certificate["status"]
        else:
            try:
                observation[field] = certificate[source]
            except KeyError as err:
                raise CalibrationError("calibration overhead is incomplete") from err
    return observation


def build_receipt(observations: list[dict], planner_manifest: dict) -> dict:
    P.validate_planner_manifest(planner_manifest)
    expected = {
        (task_id, mode) for task_id, _ in TASK_SPECS for mode in P.MODES
    }
    if {
        (row.get("task_id"), row.get("mode")) for row in observations
    } != expected or len(observations) != len(expected):
        raise CalibrationError("calibration matrix is incomplete")
    observations = sorted(
        observations, key=lambda row: (row["task_id"], P.MODES.index(row["mode"]))
    )
    receipt = {
        "schema": P.CALIBRATION_SCHEMA,
        "development_task_manifest_sha256": development_manifest_sha256(),
        "planner_manifest_sha256": hashlib.sha256(
            P.canonical_json_line(planner_manifest)
        ).hexdigest(),
        "planner": planner_manifest,
        "option_matrix_sha256": P.option_matrix_digest(),
        "dual_trace_schema": P.DUAL_TRACE_SCHEMA,
        "modes": list(P.MODES),
        "exposed_fields": list(EXPOSED_FIELDS),
        "observations": observations,
        "observations_sha256": hashlib.sha256(
            P.canonical_json(observations)
        ).hexdigest(),
        "all_traces_complete": True,
        "resource_recommendation": P.calibration_resource_recommendation(
            observations
        ),
    }
    P.validate_calibration_receipt(receipt)
    return receipt


def _exclusive_write(path: Path, value: dict) -> None:
    try:
        CampaignIO.write_canonical_exclusive(
            path, value, expected=P.CALIBRATION_RECEIPT_PATH,
            root=P.SCRIPT_DIR, label="calibration receipt",
            canonical_json_line=P.canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise CalibrationError(str(err)) from err


def _refuse_late_calibration() -> None:
    for path in (P.FREEZE_PATH, P.STANDALONE_K32_PATH):
        try:
            info = os.lstat(path)
        except FileNotFoundError:
            continue
        except OSError as err:
            raise CalibrationError("cannot inspect campaign ordering marker") from err
        if stat.S_ISREG(info.st_mode) or stat.S_ISLNK(info.st_mode) or (
            stat.S_ISDIR(info.st_mode)
        ):
            raise CalibrationError(
                "calibration must precede standalone evidence and campaign freeze"
            )
        raise CalibrationError("campaign ordering marker has an invalid type")


def _validate_live_planner(manifest: dict) -> Path:
    P.validate_planner_manifest(manifest)
    try:
        derived = PlannerManifest.verify_manifest()
    except PlannerManifest.PlannerManifestError as err:
        raise CalibrationError("exact planner cache cannot be verified") from err
    if P.canonical_json(manifest) != P.canonical_json(derived):
        raise CalibrationError("calibration planner manifest changed")
    cache = PlannerManifest.REVISION_CACHE / manifest["cache_name"]
    driver = cache / manifest["driver_path"]
    downward = cache / manifest["downward_path"]
    preprocess = cache / manifest["preprocess_path"]
    for path, field, label in (
        (driver, "driver_sha256", "calibration driver"),
        (downward, "downward_sha256", "calibration downward"),
        (preprocess, "preprocess_sha256", "calibration preprocess"),
    ):
        if P.sha256_file(
            path, expected_path=path, root=PlannerManifest.REVISION_CACHE,
            label=label,
        ) != manifest[field]:
            raise CalibrationError("{} differs from planner manifest".format(label))
    return driver


def run(planner_manifest: dict, output: Path = P.CALIBRATION_RECEIPT_PATH) -> dict:
    if Path(output) != P.CALIBRATION_RECEIPT_PATH:
        raise CalibrationError("calibration output path changed")
    _refuse_late_calibration()
    driver = _validate_live_planner(planner_manifest)
    observations = []
    with tempfile.TemporaryDirectory(prefix="metric-choice-calibration-") as root:
        root_path = Path(root)
        for task_number, (task_id, length) in enumerate(TASK_SPECS):
            domain_text, problem_text = _pddl(length)
            domain = root_path / "domain-{}.pddl".format(task_number)
            problem = root_path / "problem-{}.pddl".format(task_number)
            domain.write_text(domain_text, encoding="ascii")
            problem.write_text(problem_text, encoding="ascii")
            for mode in P.MODES:
                run_dir = root_path / "run-{}-{}".format(task_number, mode)
                run_dir.mkdir()
                command = [
                    str(driver), str(domain), str(problem), "--search",
                    P.SEARCHES[mode], "--build", P.BUILD_OPTIONS[0],
                ]
                result = subprocess.run(
                    command, cwd=run_dir, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, check=False, timeout=3600,
                    env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
                )
                trace_path = run_dir / P.SELECTOR_TRACE
                if result.returncode != 0:
                    raise CalibrationError("calibration planner invocation failed")
                try:
                    loaded = CampaignIO.read_regular_exact(
                        trace_path, expected=trace_path,
                        label="calibration selector trace",
                    )
                    trace_text = loaded.raw.decode("ascii")
                except (CampaignIO.CampaignIOError, UnicodeDecodeError) as err:
                    raise CalibrationError(
                        "calibration selector trace is invalid"
                    ) from err
                certificate = Trace.certify_trace(
                    trace_text, mode
                )
                observations.append(redact_certificate(task_id, mode, certificate))
    receipt = build_receipt(observations, planner_manifest)
    _exclusive_write(output, receipt)
    return receipt


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    args = parser.parse_args(argv)
    _, planner = P.load_canonical(
        P.PLANNER_MANIFEST_PATH, "planner manifest",
        expected_path=P.PLANNER_MANIFEST_PATH,
    )
    receipt = run(planner, P.CALIBRATION_RECEIPT_PATH)
    print(hashlib.sha256(P.canonical_json_line(receipt)).hexdigest())


if __name__ == "__main__":
    main()
