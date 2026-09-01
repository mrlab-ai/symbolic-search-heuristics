#!/usr/bin/env python3
"""Run prospective V6 repair shards for the frozen source audit.

V6 changes no benchmark, inventory, translator, normalization, support, or
split logic.  It loads the V5 producer in a private module and changes only
the campaign namespace and the predeclared per-candidate infrastructure
timeout selected by the terminal V5 diagnostic.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
BASE_SOURCE = (
    SCRIPT_DIR / "audit_pdb_terminal_incidence_confirmation_sources_v5.py"
)
_MODULE_NAME = "_pdb_terminal_incidence_confirmation_source_audit_v6_base"


def _load_base():
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, BASE_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen source-audit V5 implementation")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    spec.loader.exec_module(module)
    return module


V5 = _load_base()
Base = V5.Base

CAMPAIGN = "v6"
V5_TIMEOUT_SECONDS = 28800
AMENDED_TIMEOUT_SECONDS = 115200
ALLOWED_TIMEOUT_SECONDS = frozenset({
    V5_TIMEOUT_SECONDS,
    AMENDED_TIMEOUT_SECONDS,
})
DEFAULT_SHARDS = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v6_repair"
)
DEFAULT_INVENTORY = DEFAULT_SHARDS / "source-inventory-v6.json"
DEFAULT_OUTPUT = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v6_candidate.json"
)
DEFAULT_CODE_MANIFEST = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v6_code.sha256"
)
TMP_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v6_tmp"
)
TMPDIR_TEMPLATE = str(TMP_ROOT / "task-{array_job_id}-{array_task_id}")
PYTHON_CACHE_PREFIX_TEMPLATE = TMPDIR_TEMPLATE + "/pycache"
TASK_ENVIRONMENT_SCHEMA = Base.SCHEMA + "/campaign-v6/task-environment/v1"
SOURCE_SNAPSHOT_SCHEMA = Base.SCHEMA + "/campaign-v6/source-snapshot/v1"
V5_CODE_MANIFEST = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v5_code.sha256"
)
V5_LAUNCH_INTENT = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v5" /
    "source-audit-launch-intent-v5.json"
)
V5_LAUNCH_RECEIPT = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v5" /
    "source-audit-launch-receipt-v5.json"
)
V5_TERMINAL_DIAGNOSTIC = (
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v6" /
    "v5-infrastructure-failure-diagnostic-v6.json"
)
V5_CODE_MANIFEST_FILES = tuple(V5.CODE_MANIFEST_FILES)

# Expand the complete V5 producer boundary rather than trusting only the
# outer V5 manifest.  The terminal diagnostic binds runtime artifacts; they
# are deliberately not listed individually here.
CODE_MANIFEST_FILES = tuple(sorted({
    *V5_CODE_MANIFEST_FILES,
    V5_CODE_MANIFEST.relative_to(SCRIPT_DIR.parent).as_posix(),
    V5_LAUNCH_INTENT.relative_to(SCRIPT_DIR.parent).as_posix(),
    V5_LAUNCH_RECEIPT.relative_to(SCRIPT_DIR.parent).as_posix(),
    V5_TERMINAL_DIAGNOSTIC.relative_to(SCRIPT_DIR.parent).as_posix(),
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v6.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v6.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v6_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v6.py",
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v6.py",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v6.slurm",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v6.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_consumer_v6.py",
}))


def configure(timeout_seconds: int) -> None:
    """Select one frozen V6 infrastructure profile before scan/validation."""
    if type(timeout_seconds) is not int or timeout_seconds not in ALLOWED_TIMEOUT_SECONDS:
        raise V5.SourceAuditError("V6 source-audit timeout is not predeclared")
    values = {
        "TASK_TIMEOUT_SECONDS": timeout_seconds,
        "DEFAULT_SHARDS": DEFAULT_SHARDS,
        "DEFAULT_INVENTORY": DEFAULT_INVENTORY,
        "DEFAULT_OUTPUT": DEFAULT_OUTPUT,
        "DEFAULT_CODE_MANIFEST": DEFAULT_CODE_MANIFEST,
        "TMP_ROOT": TMP_ROOT,
        "TMPDIR_TEMPLATE": TMPDIR_TEMPLATE,
        "PYTHON_CACHE_PREFIX_TEMPLATE": PYTHON_CACHE_PREFIX_TEMPLATE,
        "TASK_ENVIRONMENT_SCHEMA": TASK_ENVIRONMENT_SCHEMA,
        "SOURCE_SNAPSHOT_SCHEMA": SOURCE_SNAPSHOT_SCHEMA,
        "CODE_MANIFEST_FILES": CODE_MANIFEST_FILES,
    }
    for name, value in values.items():
        setattr(V5, name, value)
    for name in (
        "TASK_TIMEOUT_SECONDS", "DEFAULT_SHARDS", "DEFAULT_INVENTORY",
        "DEFAULT_OUTPUT", "DEFAULT_CODE_MANIFEST",
        "PYTHON_CACHE_PREFIX_TEMPLATE", "CODE_MANIFEST_FILES",
    ):
        setattr(Base, name, values[name])


# Give parser defaults the fixed fat-partition ceiling profile. Runtime launch
# material calls configure again with the diagnostic-selected value.
configure(AMENDED_TIMEOUT_SECONDS)

SourceAuditError = V5.SourceAuditError
InfrastructureAuditError = V5.InfrastructureAuditError


def __getattr__(name):
    return getattr(V5, name)


def main(argv=None) -> int:
    args = Base.parse_args(argv)
    configure(args.task_timeout if args.command == "scan" else AMENDED_TIMEOUT_SECONDS)
    if args.command == "scan":
        V5.scan(args)
    else:
        Base.assemble(V5._safe_base_arguments(args))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except InfrastructureAuditError as err:
        print("infrastructure error: {}".format(err), file=sys.stderr)
        raise SystemExit(75)
    except (SourceAuditError, Base.Inventory.InventoryError) as err:
        print("error: {}".format(err), file=sys.stderr)
        raise SystemExit(2)
