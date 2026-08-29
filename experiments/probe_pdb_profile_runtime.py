#!/usr/bin/env python3
"""Emit an outcome-free identity report for the Slurm execution environment."""

import hashlib
import json
import os
import platform
import shutil
from pathlib import Path


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


path_environment = os.environ.get("PATH", "")
candidate = None
validator = None
for name in ("validate", "Validate"):
    resolved = shutil.which(name, path=path_environment)
    if resolved is not None:
        candidate = name
        validator = Path(resolved)
        break

validator_identity = {
    "available": validator is not None,
    "candidate": candidate,
    "path": str(validator) if validator is not None else None,
    "resolved_path": str(validator.resolve(strict=True)) if validator is not None else None,
    "is_symlink": validator.is_symlink() if validator is not None else None,
    "size": validator.stat().st_size if validator is not None else None,
    "sha256": sha256_file(validator) if validator is not None else None,
}
report = {
    "schema": "symbolic-search-heuristics/pdb-profile-slurm-runtime-probe/v1",
    "hostname": platform.node(),
    "slurm_array_job_id": os.environ.get("SLURM_ARRAY_JOB_ID"),
    "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
    "slurm_job_name": os.environ.get("SLURM_JOB_NAME"),
    "path": path_environment,
    "python_environment": {
        name: os.environ.get(name)
        for name in (
            "LD_LIBRARY_PATH",
            "LD_PRELOAD",
            "PYTHONHOME",
            "PYTHONNOUSERSITE",
            "PYTHONPATH",
            "PYTHONSTARTUP",
            "PYTHONUSERBASE",
        )
    },
    "validator": validator_identity,
}
print(json.dumps(report, sort_keys=True, separators=(",", ":")))
