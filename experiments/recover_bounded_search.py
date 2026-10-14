#!/usr/bin/env python3
"""Rerun only scheduler-failed, file-incomplete bounded-search tasks.

Reuses the certificate-holdout recovery with this study's audit and
constants: it resubmits the exact launched job file for the array indices
whose latest execution failed in the scheduler and left incomplete cells.
"""

from __future__ import annotations

import audit_bounded_search as HarmAudit
import bounded_search_protocol as P

import recover_pdb_profile_certificate_holdout as Recover  # noqa: E402


def configure() -> None:
    Recover.Audit = HarmAudit.Audit
    Recover.E = HarmAudit.Audit.E
    Recover.P = P
    Recover.RECOVERY_SCHEMA = HarmAudit.Audit.RECOVERY_RECEIPT_SCHEMA
    Recover.RECOVERY_JOB_PREFIX = "bounded-search-recovery"


configure()


def main(argv=None):
    return Recover.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        HarmAudit.Audit.ExecutionAuditError,
        HarmAudit.Base.LaunchError,
        P.ProtocolError,
        Recover.RecoveryError,
    ) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
