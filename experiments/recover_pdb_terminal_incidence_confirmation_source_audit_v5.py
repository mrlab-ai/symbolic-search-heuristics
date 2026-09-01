#!/usr/bin/env python3
"""Forbid shard recovery for the original-only campaign-v5 source audit."""

from __future__ import annotations

import sys


class RecoveryError(RuntimeError):
    pass


def _recovery_forbidden(*args, **kwargs):
    raise RecoveryError(
        "campaign v5 forbids recovery; all 820 original shards must succeed"
    )


preview = _recovery_forbidden
launch = _recovery_forbidden
recover_launch = _recovery_forbidden
status = _recovery_forbidden
seal = _recovery_forbidden


def main(argv=None) -> int:
    return _recovery_forbidden(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RecoveryError as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
