#!/usr/bin/env python3
"""Recover interrupted cells from the unseen Gamer-seed validation."""

from __future__ import annotations

import audit_pdb_profile_joint_seed_validation as SeedAudit
import pdb_profile_joint_seed_validation_protocol as P
import recover_pdb_profile_certificate_holdout as Recovery


def configure() -> None:
    SeedAudit.configure()
    Recovery.Audit = SeedAudit.Audit
    Recovery.E = SeedAudit.Audit.E
    Recovery.P = P
    Recovery.RECOVERY_SCHEMA = SeedAudit.Audit.RECOVERY_RECEIPT_SCHEMA
    Recovery.RECOVERY_JOB_PREFIX = "pdb-joint-seed-validation-recovery"


def main(argv=None):
    configure()
    return Recovery.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        Recovery.Audit.ExecutionAuditError,
        Recovery.E.LaunchError,
        P.ProtocolError,
        Recovery.RecoveryError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
