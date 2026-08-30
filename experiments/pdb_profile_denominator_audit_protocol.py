#!/usr/bin/env python3
"""Frozen constants for the shared-denominator robustness audit."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pdb_profile_certificate_holdout_protocol as Holdout


class ProtocolError(RuntimeError):
    pass


PROTOCOL_PATH = Path(__file__).with_name(
    "pdb_profile_denominator_audit_protocol.md"
)
PROTOCOL_SHA256 = (
    "6956e0b05c3f38d8c89e91821ccf368ae83d44f22a5bbac1e4210a925b2b0f50"
)
PROTOCOL = "pdb-profile-shared-denominator-audit-v1"
MIN_DOMAINS = Holdout.MIN_DOMAINS
MIN_TASKS_WITH_COMPARABLE_PAIRS = Holdout.MIN_TASKS_WITH_COMPARABLE_PAIRS


def validate_protocol() -> None:
    try:
        raw = PROTOCOL_PATH.read_bytes()
    except OSError as err:
        raise ProtocolError("cannot read denominator-audit protocol") from err
    if hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise ProtocolError("denominator-audit protocol bytes changed")
    if (
        MIN_DOMAINS != 30
        or MIN_TASKS_WITH_COMPARABLE_PAIRS != 211
    ):
        raise ProtocolError("denominator-audit support floor changed")


if __name__ == "__main__":
    validate_protocol()
    print("denominator-audit protocol OK")
