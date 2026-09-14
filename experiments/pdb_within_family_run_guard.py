#!/usr/bin/env python3
"""Verify frozen planner/input bytes and record a bounded scientific run."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time


SCHEMA = "pdb-terminal-incidence-within-family-execution/v1"
WALL_SECONDS = 1950


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def verify(config, command):
    if len(command) < 3 or command[0] != sys.executable:
        raise ValueError("planner command does not use the pinned Python")
    if command[2:] != config["driver_options"] + ["domain.pddl", "problem.pddl", "--search", config["search"]]:
        raise ValueError("executed planner options differ from the frozen configuration")
    root = Path(command[1]).parent
    if Path(command[1]).name != "fast-downward.py":
        raise ValueError("unexpected planner entry point")
    for name, expected in config["planner_files_sha256"].items():
        if sha(root / name) != expected:
            raise ValueError(f"planner byte identity changed: {name}")
    for kind in ("domain", "problem"):
        path = Path(kind + ".pddl")
        if path.is_symlink() or sha(path) != config[kind + "_sha256"]:
            raise ValueError(f"scientific input changed: {kind}")
    if sha(sys.executable) != config["python_sha256"] or sha(__file__) != config["guard_sha256"]:
        raise ValueError("execution environment or guard changed")


def run_driver_child(config_path, command):
    """Observe translator output before legacy preprocessing overwrites it."""
    config = json.loads(config_path.read_bytes())
    verify(config, command)
    sys.path.insert(0, str(Path(command[1]).parent))
    from driver import main as driver_main
    from driver import run_components

    original = run_components.run_preprocess

    def checked_preprocess(args):
        translated_sha = sha(args.sas_file)
        if translated_sha != config["source_sas_sha256"]:
            raise ValueError("actual translation differs from the source-screened SAS task")
        evidence = {"sas_sha256": translated_sha, "source_result_sha256": config["source_result_sha256"],
                    "verified_before_preprocessing": True}
        with Path("translation-evidence.json").open("xb") as stream:
            stream.write(canonical(evidence))
        return original(args)

    run_components.run_preprocess = checked_preprocess
    sys.argv = command[1:]
    driver_main.main()


def execute(config_path, command):
    config = json.loads(config_path.read_bytes())
    verify(config, command)
    output = Path("execution-evidence.json")
    if output.exists() or Path("output.sas").exists():
        raise ValueError("refusing to reuse a scientific run directory")
    environment = dict(os.environ, PYTHONHASHSEED="0", PYTHONNOUSERSITE="1",
                       PYTHONDONTWRITEBYTECODE="1", LC_ALL="C", LANG="C")
    for name in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV"):
        environment.pop(name, None)
    hardware = {"hostname": platform.node(), "machine": platform.machine(),
                "kernel": platform.release(), "affinity": sorted(os.sched_getaffinity(0)),
                "cpu_model": next((line.split(":", 1)[1].strip()
                                   for line in Path("/proc/cpuinfo").read_text().splitlines()
                                   if line.startswith("model name")), "unknown"),
                "slurm": {name: os.environ.get(name) for name in (
                    "SLURM_ARRAY_JOB_ID", "SLURM_ARRAY_TASK_ID", "SLURM_JOB_ID",
                    "SLURM_CPUS_PER_TASK", "SLURM_MEM_PER_CPU", "SLURM_JOB_PARTITION")}}
    started = time.monotonic()
    child = subprocess.Popen(
        [sys.executable, "-B", str(Path(__file__).resolve()), "--driver-child",
         "--config", str(config_path.resolve()), "--", *command],
        env=environment, start_new_session=True)
    timed_out = False
    try:
        returncode = child.wait(timeout=WALL_SECONDS)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(child.pid, signal.SIGKILL)
        returncode = child.wait()
    verify(config, command)
    files = {name: sha(name) for name in ("output.sas", "translation-evidence.json", "wbh.jsonl", "wbh-profile.jsonl",
                                         "incidence-selector.jsonl", "dual-selector.jsonl")
             if Path(name).is_file()}
    translation = (json.loads(Path("translation-evidence.json").read_bytes())
                   if Path("translation-evidence.json").exists() else None)
    if returncode in {0, 1, 2, 3, 11, 12, 22, 23, 24} and translation is None:
        raise ValueError("scientific search lacks a verified translator handoff")
    record = {"schema": SCHEMA, "id": config["id"], "config_sha256": sha(config_path),
              "freeze_sha256": config["freeze_sha256"], "hardware": hardware,
              "source_sas_sha256": config["source_sas_sha256"],
              "source_result_sha256": config["source_result_sha256"],
              "translation_evidence": translation,
              "returncode": returncode, "wall_timeout": timed_out,
              "wall_seconds": time.monotonic() - started, "wall_limit_seconds": WALL_SECONDS,
              "inputs_and_planner_verified_before_and_after": True, "files_sha256": files}
    with output.open("xb") as stream:
        stream.write(canonical(record))
    return 70 if timed_out else returncode


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--driver-child", action="store_true")
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if args.driver_child:
        return run_driver_child(args.config, command)
    return execute(args.config, command)


if __name__ == "__main__":
    sys.exit(main())
