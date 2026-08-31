#!/usr/bin/env python3
"""Audit or seal the unseen Gamer-seed validation."""

from __future__ import annotations

import audit_pdb_profile_certificate_holdout as Audit
import exp_pdb_profile_joint_seed_validation as Runner
import pdb_profile_joint_seed_validation_protocol as P


def configure() -> None:
    Runner.configure()
    Audit.E = Runner.Base
    Audit.P = P
    Audit.LAUNCH_RECEIPT_SHA256 = (
        "785042f8fccbcdbd37391f3cd87bc3e13d5af24f3c89c9d820b9618ba84e24f4"
    )
    Audit.EXECUTION_RECEIPT = (
        Audit.E.SCRIPT_DIR
        / "artifacts"
        / "pdb-profile-joint-seed-validation"
        / "execution-receipt-v1.json"
    )
    Audit.EXECUTION_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/"
        "pdb-profile-joint-seed-validation-execution/v1"
    )
    Audit.RECOVERY_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/"
        "pdb-profile-joint-seed-validation-recovery-launch/v1"
    )


def main(argv=None):
    configure()
    return Audit.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        Audit.E.LaunchError,
        P.ProtocolError,
        Audit.ExecutionAuditError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
