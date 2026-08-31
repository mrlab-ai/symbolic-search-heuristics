#!/usr/bin/env python3
"""Recover scheduler-interrupted cells from the joint-profile pilot."""

from __future__ import annotations

import audit_pdb_profile_joint_pilot as JointAudit
import pdb_profile_joint_pilot_protocol as P
import recover_pdb_profile_certificate_holdout as Recovery


def configure() -> None:
    JointAudit.configure()
    Recovery.Audit = JointAudit.Audit
    Recovery.E = JointAudit.Audit.E
    Recovery.P = P
    Recovery.RECOVERY_SCHEMA = JointAudit.Audit.RECOVERY_RECEIPT_SCHEMA
    Recovery.RECOVERY_JOB_PREFIX = "pdb-joint-pilot-recovery"
    # The planner retains its fixed 300-second aggregate CPU budget.  This
    # larger scheduler envelope only accommodates wall-clock slowdown on a
    # heavily populated fat node.
    Recovery.E.SCHEDULER_TIME_LIMIT = "00:25:00"


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
