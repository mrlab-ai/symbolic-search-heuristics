#!/usr/bin/env python3
"""Audit or seal the harm-generality execution without reading outcomes.

Reuses the certificate-holdout audit with this study's constants.  After the
runs, cell directories also hold run outputs, so the immutable inputs (run
wrapper, static properties, and the materialized PDDL files) are rehashed
with the launch digest's exact construction while extra files are allowed.
"""

from __future__ import annotations

import hashlib
import stat
from pathlib import Path

import exp_pdb_profile_certificate_holdout as Base
import exp_pdb_profile_harm_generality as Launcher
import pdb_profile_harm_generality_protocol as P

Launcher.configure()

import audit_pdb_profile_certificate_holdout as Audit  # noqa: E402


INPUT_NAMES = ("run", "static-properties", "domain.pddl", "problem.pddl")


def post_run_input_tree_digest():
    """Hash the generated inputs exactly as at launch, ignoring run outputs."""
    digest = hashlib.sha256()
    expected = set()
    for run_id in range(1, P.CELL_COUNT + 1):
        lower = ((run_id - 1) // 100) * 100 + 1
        directory = Path(
            "runs-{:05d}-{:05d}/{:05d}".format(lower, lower + 99, run_id)
        )
        expected.add(directory)
        for name in INPUT_NAMES:
            relative = directory / name
            path = Base.EXPERIMENT_PATH / relative
            try:
                info = path.lstat()
            except OSError as err:
                raise Audit.ExecutionAuditError(
                    "generated run input is missing: {}".format(relative)
                ) from err
            if path.is_symlink() or not stat.S_ISREG(info.st_mode):
                raise Audit.ExecutionAuditError(
                    "generated run input is not a regular file"
                )
            digest.update(
                relative.as_posix().encode("ascii") + b"\0"
                + bytes.fromhex(Base._sha256_file(path))
            )
    actual = {
        path.relative_to(Base.EXPERIMENT_PATH)
        for path in Base.EXPERIMENT_PATH.glob("runs-*/[0-9]*")
    }
    if actual != expected:
        raise Audit.ExecutionAuditError("generated run matrix has wrong directories")
    return digest.hexdigest(), P.CELL_COUNT, P.CELL_COUNT


class _Runner:
    """The configured shared runner with a post-run input digest."""

    def __getattr__(self, name):
        return getattr(Base, name)

    _run_input_tree_digest = staticmethod(post_run_input_tree_digest)


def configure() -> None:
    Audit.E = _Runner()
    Audit.P = P
    Audit.LAUNCH_RECEIPT_SHA256 = (
        "ce0464d06ac670b43be76d6393acc77e616f0e99cda565363c59219f8618ec04"
    )
    Audit.EXECUTION_RECEIPT = (
        Base.SCRIPT_DIR
        / "artifacts"
        / "pdb-profile-harm-generality"
        / "execution-receipt-v1.json"
    )
    Audit.EXECUTION_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/pdb-profile-harm-generality-execution/v1"
    )
    Audit.RECOVERY_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/"
        "pdb-profile-harm-generality-recovery-launch/v1"
    )


configure()


def main(argv=None):
    return Audit.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Base.LaunchError, P.ProtocolError, Audit.ExecutionAuditError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
