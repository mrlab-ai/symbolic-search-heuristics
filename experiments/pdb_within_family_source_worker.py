#!/usr/bin/env python3
"""Translation-only compatibility checks; no heuristic or search is run."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import signal
import subprocess
import sys
import time

import pdb_terminal_incidence_confirmation_translate_v12 as Translate


SCHEMA = "pdb-terminal-incidence-within-family-source/v1"
CPU_SECONDS = 1800
MEMORY_MIB = 24576
WALL_SECONDS = 1950
Translate.NORMALIZATION_EVIDENCE_SCHEMA = SCHEMA + "/normalization"


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode("ascii")


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def support_reasons(sas, normalized_axioms):
    reasons = []
    if sas["num_operators"] < 1:
        reasons.append("no-serialized-operators")
    if sas["num_zero_cost_operators"] or (sas["min_operator_cost"] or 0) < 1:
        reasons.append("nonpositive-serialized-operator-cost")
    if sas["num_serialized_axioms"]:
        reasons.append("serialized-axioms")
    if sas["num_conditional_effects"]:
        reasons.append("serialized-conditional-effects")
    if normalized_axioms:
        reasons.append("normalized-axioms")
    return reasons


def classify_exit(returncode, cpu_seconds, wall_timeout=False):
    if wall_timeout:
        return "wall-excluded"
    if returncode == 0:
        return "translated"
    if returncode == Translate.TRANSLATE_OUT_OF_MEMORY:
        return "memory-excluded"
    if returncode == Translate.TRANSLATE_INPUT_ERROR:
        return "input-error"
    if returncode == Translate.TRANSLATE_OUT_OF_TIME or (
        returncode in {-signal.SIGXCPU, -signal.SIGKILL} and cpu_seconds >= CPU_SECONDS
    ):
        return "time-excluded"
    return "infrastructure-error"


def limits():
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS + 1))
    memory = MEMORY_MIB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))


def verify_inputs(config, translator):
    for path, expected in config["translator_sha256"].items():
        if file_sha(translator / path) != expected:
            raise ValueError(f"translator source changed: {path}")
    for name in ("domain", "problem"):
        if file_sha(f"{name}.pddl") != config[f"{name}_sha256"]:
            raise ValueError(f"{name} input changed")
    for name, expected in config["worker_sha256"].items():
        if file_sha(Path(__file__).parent / name) != expected:
            raise ValueError(f"worker source changed: {name}")
    if file_sha(sys.executable) != config["python_sha256"]:
        raise ValueError("Python executable changed")


def run(config_path, translator):
    config = json.loads(config_path.read_bytes())
    verify_inputs(config, translator)
    if Path("source-result.json").exists() or Path("output.sas").exists():
        raise ValueError("source check refuses an already used run directory")
    record = {
        "schema": SCHEMA, "id": config["id"],
        "config_sha256": file_sha(config_path),
        "domain_sha256": config["domain_sha256"],
        "problem_sha256": config["problem_sha256"],
        "planner_revision": config["planner_revision"],
        "performance_observed": False, "hostname": platform.node(),
        "slurm": {name: os.environ.get(name) for name in (
            "SLURM_JOB_ID", "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID",
            "SLURM_JOB_PARTITION", "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_CPU")},
        "limits": {"cpu_seconds": CPU_SECONDS, "memory_mib": MEMORY_MIB,
                   "wall_seconds": WALL_SECONDS},
    }
    environment = dict(os.environ, PYTHONHASHSEED="0", PYTHONNOUSERSITE="1",
                       PYTHONDONTWRITEBYTECODE="1", LC_ALL="C", LANG="C")
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(name, None)
    started = time.monotonic()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    timed_out = False
    with open("normalization.json", "xb") as normalization, \
            open("translate.stdout", "xb") as stdout, \
            open("translate.stderr", "xb") as stderr:
        child = subprocess.Popen(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--child",
             str(normalization.fileno()), "--translator", str(translator)],
            stdout=stdout, stderr=stderr, env=environment,
            pass_fds=(normalization.fileno(),), start_new_session=True,
            preexec_fn=limits,
        )
        try:
            returncode = child.wait(timeout=WALL_SECONDS)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(child.pid, signal.SIGKILL)
            returncode = child.wait()
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = after.ru_utime + after.ru_stime - before.ru_utime - before.ru_stime
    record.update({"returncode": returncode, "cpu_seconds": cpu,
                   "wall_seconds": time.monotonic() - started,
                   "status": classify_exit(returncode, cpu, timed_out),
                   "stdout": Translate.stream_file_evidence(Path("translate.stdout")),
                   "stderr": Translate.stream_file_evidence(Path("translate.stderr"))})
    if record["status"] == "translated":
        with open("normalization.json", "rb") as normalization:
            record["normalization"] = Translate.read_normalization_evidence(normalization.fileno())
        record.update(Translate.parse_and_hash_sas(Path("output.sas")))
        record["support_reasons"] = support_reasons(
            record["sas"], record["normalization"]["num_normalized_axioms"])
        record["status"] = "unsupported" if record["support_reasons"] else "supported"
    verify_inputs(config, translator)
    with open("source-result.json", "xb") as stream:
        stream.write(canonical(record))
    print(f"Source compatibility: {record['status']}", flush=True)
    return 1 if record["status"] in {"input-error", "infrastructure-error"} else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path)
    parser.add_argument("--translator", type=Path, required=True)
    parser.add_argument("--child", type=int)
    args = parser.parse_args()
    translator = args.translator.resolve()
    if args.child is not None:
        Translate.SOURCE_ROOT = translator.parent
        return Translate.run_translator(
            ["domain.pddl", "problem.pddl", "--sas-file", "output.sas",
             "--normalization-strategy", "axiom_based"], args.child)
    if args.config is None:
        parser.error("--config is required for the supervisor")
    return run(args.config, translator)


if __name__ == "__main__":
    sys.exit(main())
