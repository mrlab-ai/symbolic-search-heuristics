#!/usr/bin/env python3
"""Audit or seal the fixed-heuristic variable-order intervention."""

from __future__ import annotations

import audit_pdb_profile_certificate_holdout as Audit
import exp_pdb_profile_order_intervention as Runner
import pdb_profile_order_intervention_protocol as P


def configure() -> None:
    Runner.configure()
    Audit.P = P
    Audit.LAUNCH_RECEIPT_SHA256 = (
        "acef6e5fc9159542530c592953815236dae1def828d375e74a938f5c1d6b8675"
    )
    Audit.EXECUTION_RECEIPT = (
        Audit.E.SCRIPT_DIR
        / "artifacts"
        / "pdb-profile-order-intervention"
        / "execution-receipt-v1.json"
    )
    Audit.EXECUTION_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/pdb-profile-order-intervention-execution/v1"
    )
    Audit.RECOVERY_RECEIPT_SCHEMA = (
        "symbolic-search-heuristics/"
        "pdb-profile-order-intervention-recovery-launch/v1"
    )


def main(argv=None):
    configure()
    return Audit.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Audit.E.LaunchError, P.ProtocolError, Audit.ExecutionAuditError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
