#!/usr/bin/env python3
"""Run the frozen source-audit producer for prospective campaign V7.

V7 changes no benchmark, inventory, translator, normalization, support, or
split logic.  It loads the committed V5 producer in a private module, changes
only the campaign namespace, and fixes the per-candidate infrastructure limit
at the 115,200-second ceiling frozen after the disclosed operational telemetry,
including the V6 row-2 rejection, and before V7 diagnosis.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pdb_terminal_incidence_confirmation_safe_io_v7 as SafeIOV7


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
BASE_SOURCE = (
    SCRIPT_DIR / "audit_pdb_terminal_incidence_confirmation_sources_v5.py"
)
_MODULE_NAME = "_pdb_terminal_incidence_confirmation_source_audit_v7_base"


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

CAMPAIGN = "v7"
TASK_TIMEOUT_SECONDS = 115200
ALLOWED_TIMEOUT_SECONDS = frozenset({TASK_TIMEOUT_SECONDS})
DEFAULT_SHARDS = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v7_repair"
)
DEFAULT_INVENTORY = DEFAULT_SHARDS / "source-inventory-v7.json"
DEFAULT_OUTPUT = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v7_candidate.json"
)
DEFAULT_CODE_MANIFEST = (
    SCRIPT_DIR /
    "pdb_terminal_incidence_confirmation_source_audit_v7_code.sha256"
)
TMP_ROOT = (
    SCRIPT_DIR / "data" /
    "pdb_terminal_incidence_confirmation_source_audit_v7_tmp"
)
TMPDIR_TEMPLATE = str(TMP_ROOT / "task-{array_job_id}-{array_task_id}")
PYTHON_CACHE_PREFIX_TEMPLATE = TMPDIR_TEMPLATE + "/pycache"
TASK_ENVIRONMENT_SCHEMA = Base.SCHEMA + "/campaign-v7/task-environment/v1"
SOURCE_SNAPSHOT_SCHEMA = Base.SCHEMA + "/campaign-v7/source-snapshot/v1"
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
    SCRIPT_DIR / "artifacts" / "pdb-terminal-incidence-confirmation-v7" /
    "v5-scheduler-terminal-diagnostic-v7.json"
)
V5_CODE_MANIFEST_FILES = tuple(V5.CODE_MANIFEST_FILES)

# Freeze every executable downstream source-selection and confirmatory design
# before the scheduler-derived V5/V7 origin partition becomes observable.
# This is a static list to avoid importing the downstream modules here and
# creating a SourceV7 import cycle.
DOWNSTREAM_PRE_DIAGNOSIS_FILES = (
    "experiments/analyze_pdb_cap_grid_posthoc_review.py",
    "experiments/analyze_pdb_terminal_incidence_confirmation_a.py",
    "experiments/analyze_pdb_terminal_incidence_confirmation_b.py",
    "experiments/analyze_pdb_terminal_incidence_shadow.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_a.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_b.py",
    "experiments/audit_pdb_terminal_incidence_shadow.py",
    "experiments/exp_arrhenius_common.py",
    "experiments/exp_pdb_profile_certificate_holdout.py",
    "experiments/exp_pdb_terminal_incidence_confirmation_a.py",
    "experiments/exp_pdb_terminal_incidence_confirmation_b.py",
    "experiments/exp_pdb_terminal_incidence_shadow.py",
    "experiments/freeze_pdb_terminal_incidence_confirmation_a.py",
    "experiments/freeze_pdb_terminal_incidence_confirmation_b.py",
    "experiments/jj_cached_revision.py",
    "experiments/pdb_cap_selector_parser.py",
    "experiments/pdb_confirmation_run_cell.py",
    "experiments/pdb_fixed_pattern_parser.py",
    "experiments/pdb_profile_certificate_holdout_protocol.md",
    "experiments/pdb_profile_certificate_holdout_protocol.py",
    "experiments/pdb_profile_comparison_parser.py",
    "experiments/pdb_profile_comparison_protocol.py",
    "experiments/pdb_profile_semantic_union_protocol.md",
    "experiments/pdb_profile_semantic_union_protocol.py",
    "experiments/pdb_terminal_incidence_confirmation_a_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_a_protocol.py",
    "experiments/pdb_terminal_incidence_confirmation_b_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_b_protocol.py",
    "experiments/pdb_terminal_incidence_selector_parser.py",
    "experiments/pdb_terminal_incidence_shadow_protocol.py",
    "experiments/pdb_terminal_metric_choice_analyzer.py",
    "experiments/pdb_terminal_metric_choice_audit.py",
    "experiments/pdb_terminal_metric_choice_calibration.py",
    "experiments/pdb_terminal_metric_choice_execution.py",
    "experiments/pdb_terminal_metric_choice_freeze.py",
    "experiments/pdb_terminal_metric_choice_io.py",
    "experiments/pdb_terminal_metric_choice_parser.py",
    "experiments/pdb_terminal_metric_choice_planner_manifest.py",
    "experiments/pdb_terminal_metric_choice_protocol.md",
    "experiments/pdb_terminal_metric_choice_protocol.py",
    "experiments/pdb_terminal_metric_choice_recovery.py",
    "experiments/pdb_terminal_metric_choice_requirements.txt",
    "experiments/pdb_terminal_metric_choice_runner.py",
    "experiments/pdb_terminal_metric_choice_standalone.py",
    "experiments/pdb_terminal_metric_choice_transport.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_a.py",
    "experiments/recover_pdb_terminal_incidence_confirmation_b.py",
    "experiments/suite_cost_manifest.py",
    "experiments/test_pdb_cap_selector_parser.py",
    "experiments/test_pdb_terminal_incidence_confirmation_a_execution.py",
    "experiments/test_pdb_terminal_incidence_confirmation_a_protocol.py",
    "experiments/test_pdb_terminal_incidence_confirmation_b_analysis.py",
    "experiments/test_pdb_terminal_incidence_confirmation_b_execution.py",
    "experiments/test_pdb_terminal_incidence_confirmation_b_protocol.py",
    "experiments/test_pdb_terminal_metric_choice_analyzer.py",
    "experiments/test_pdb_terminal_metric_choice_calibration.py",
    "experiments/test_pdb_terminal_metric_choice_execution.py",
    "experiments/test_pdb_terminal_metric_choice_hardening.py",
    "experiments/test_pdb_terminal_metric_choice_parser.py",
    "experiments/test_pdb_terminal_metric_choice_planner_manifest.py",
    "experiments/test_pdb_terminal_metric_choice_protocol.py",
    "experiments/test_pdb_terminal_metric_choice_standalone.py",
    "experiments/validate_wbh_log.py",
    "experiments/wbh_parser.py",
)

# V7 explicitly reuses the descriptor-streaming and crash-recovery machinery
# from committed V6.  The exact imported implementation bytes are therefore
# part of V7's manifest, but no V6 runtime artifact or outcome is an input.
CODE_MANIFEST_FILES = tuple(sorted({
    *V5_CODE_MANIFEST_FILES,
    *DOWNSTREAM_PRE_DIAGNOSIS_FILES,
    V5_CODE_MANIFEST.relative_to(SCRIPT_DIR.parent).as_posix(),
    V5_LAUNCH_INTENT.relative_to(SCRIPT_DIR.parent).as_posix(),
    V5_LAUNCH_RECEIPT.relative_to(SCRIPT_DIR.parent).as_posix(),
    V5_TERMINAL_DIAGNOSTIC.relative_to(SCRIPT_DIR.parent).as_posix(),
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v6.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v6.py",
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v6.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v6.py",
    "experiments/pdb_confirmation_safe_io.py",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v5.py",
    "experiments/audit_pdb_terminal_incidence_confirmation_sources_v7.py",
    "experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v7.py",
    "experiments/pdb_terminal_incidence_confirmation_source_audit_v7_protocol.md",
    "experiments/pdb_terminal_incidence_confirmation_source_consumer_v7.py",
    "experiments/pdb_terminal_incidence_confirmation_safe_io_v7.py",
    "experiments/pdb_terminal_incidence_confirmation_source_scan_v7.slurm",
    "experiments/test_pdb_terminal_incidence_confirmation_source_audit_v7.py",
    "experiments/test_pdb_terminal_incidence_confirmation_source_consumer_v7.py",
    "paper/check_submission_ready.py",
    "paper/paper.tex",
    "paper/render_terminal_incidence_results.py",
    "paper/supplement.tex",
    "paper/test_render_terminal_incidence_results.py",
}))


def atomic_exclusive_bytes(path: Path, raw: bytes, label: str) -> str:
    try:
        return SafeIOV7.atomic_exclusive_bytes(
            Path(path), raw, label, root=REPO
        )
    except SafeIOV7.PublicationError as err:
        raise V5.SourceAuditError(str(err)) from err


def configure(timeout_seconds: int) -> None:
    """Install the single frozen V7 ceiling profile in the private producer."""
    if (
        type(timeout_seconds) is not int
        or timeout_seconds not in ALLOWED_TIMEOUT_SECONDS
    ):
        raise V5.SourceAuditError("V7 source-audit timeout is not predeclared")
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
    # The private V5 producer resolves this name dynamically from its private
    # base module.  Rebinding only that private instance gives V7 task outputs
    # the V7 no-follow exclusive publisher without changing V5 semantics.
    setattr(Base, "atomic_exclusive_bytes", atomic_exclusive_bytes)


configure(TASK_TIMEOUT_SECONDS)

SourceAuditError = V5.SourceAuditError
InfrastructureAuditError = V5.InfrastructureAuditError


def __getattr__(name):
    return getattr(V5, name)


def main(argv=None) -> int:
    args = Base.parse_args(argv)
    configure(args.task_timeout if args.command == "scan" else TASK_TIMEOUT_SECONDS)
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
