#!/usr/bin/env python3
"""Recover scheduler-failed fixed-heuristic intervention tasks."""

from __future__ import annotations

import audit_pdb_profile_order_intervention as OrderAudit
import pdb_profile_order_intervention_protocol as P
import recover_pdb_profile_certificate_holdout as Recovery


def configure() -> None:
    OrderAudit.configure()
    Recovery.Audit = OrderAudit.Audit
    Recovery.E = OrderAudit.Audit.E
    Recovery.P = P
    Recovery.RECOVERY_SCHEMA = OrderAudit.Audit.RECOVERY_RECEIPT_SCHEMA
    Recovery.RECOVERY_JOB_PREFIX = "pdb-order-intervention-recovery"


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
