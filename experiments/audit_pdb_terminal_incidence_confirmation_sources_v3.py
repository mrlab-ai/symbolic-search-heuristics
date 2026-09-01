#!/usr/bin/env python3
"""Run the frozen confirmation source audit as independent campaign v3."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BASE_SOURCE = SCRIPT_DIR / "audit_pdb_terminal_incidence_confirmation_sources.py"
_MODULE_NAME = "_pdb_terminal_incidence_confirmation_source_audit_v3_base"


def _load_base():
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, BASE_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen source-audit implementation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


Base = _load_base()

Base.TASK_TIMEOUT_SECONDS = 7200
Base.DEFAULT_SHARDS = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v3"
)
Base.DEFAULT_INVENTORY = Base.DEFAULT_SHARDS / "source-inventory-v3.json"
Base.DEFAULT_OUTPUT = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v3.json"
)
Base.DEFAULT_CODE_MANIFEST = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v3_code.sha256"
)
Base.PYTHON_CACHE_PREFIX_TEMPLATE = (
    "/tmp/symk-confirmation-source-audit-v3-"
    "{array_job_id}-{array_task_id}"
)
Base.CODE_MANIFEST_FILES = (
    "experiments/artifacts/pdb-terminal-incidence-confirmation/"
    "source-audit-launch-receipt-v1.json",
    "experiments/artifacts/pdb-terminal-incidence-confirmation-v2/"
    "source-audit-launch-receipt-v2.json",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v3.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/pdb_terminal_incidence_confirmation_inventory.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v3_protocol.md",
    "experiments/pdb_terminal_incidence_shadow_cost_attestation.json",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_source_audit_v3.py",
    "experiments/requirements-pdb-terminal-incidence-shadow.txt",
    "experiments/suite_wbh_operator_costs.json",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v3.py",
)


def __getattr__(name):
    return getattr(Base, name)


def main(argv=None) -> int:
    return Base.main(argv)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Base.InfrastructureAuditError as err:
        print("infrastructure error: {}".format(err), file=sys.stderr)
        raise SystemExit(75)
    except (Base.SourceAuditError, Base.Inventory.InventoryError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
