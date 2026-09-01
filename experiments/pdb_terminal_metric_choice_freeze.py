#!/usr/bin/env python3
"""Freeze the dual-metric campaign after outcome-blind calibration."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_protocol as P


class FreezeError(RuntimeError):
    pass


def _relative(path: Path) -> str:
    try:
        return Path(path).relative_to(P.REPO).as_posix()
    except ValueError as err:
        raise FreezeError("bound evidence must be inside the repository") from err


def _write_exclusive(path: Path, value: dict) -> str:
    try:
        raw = CampaignIO.write_canonical_exclusive(
            path, value, expected=P.FREEZE_PATH, root=P.SCRIPT_DIR,
            label="campaign freeze", canonical_json_line=P.canonical_json_line,
        )
    except CampaignIO.CampaignIOError as err:
        raise FreezeError(str(err)) from err
    return hashlib.sha256(raw).hexdigest()


def freeze(
    calibration_path: Path,
    planner_manifest_path: Path,
    standalone_path: Path,
    output_path: Path,
    scheduler_time_limit: str,
    scheduler_memory: str,
) -> tuple[dict, str]:
    if any((
        Path(calibration_path) != P.CALIBRATION_RECEIPT_PATH,
        Path(planner_manifest_path) != P.PLANNER_MANIFEST_PATH,
        Path(standalone_path) != P.STANDALONE_K32_PATH,
        Path(output_path) != P.FREEZE_PATH,
    )):
        raise FreezeError("campaign freeze input/output path changed")
    # Calibration is opened and completely validated before any A/B/v4
    # verifier or evidence path is touched.
    calibration_raw, calibration = P.load_canonical(
        calibration_path, "calibration receipt",
        expected_path=P.CALIBRATION_RECEIPT_PATH,
    )
    P.validate_calibration_receipt(calibration)
    planner_raw, planner = P.load_canonical(
        planner_manifest_path, "planner manifest",
        expected_path=P.PLANNER_MANIFEST_PATH,
    )
    del planner_raw
    P.validate_planner_manifest(planner)
    if P.canonical_json(calibration["planner"]) != P.canonical_json(planner):
        raise FreezeError("calibration planner binding changed")
    # This is the sole intentional point at which sealed B is invoked, after
    # calibration has been accepted without consulting either sealed cohort.
    snapshot = P.snapshot_sealed_b(calibration)
    standalone_raw, standalone = P.load_canonical(
        standalone_path, "standalone K32 evidence",
        expected_path=P.STANDALONE_K32_PATH,
    )
    P.validate_standalone_evidence(standalone, snapshot, planner)
    value = P.build_freeze(
        base_snapshot=snapshot,
        calibration_receipt=calibration,
        calibration_receipt_path=_relative(calibration_path),
        calibration_receipt_sha256=hashlib.sha256(calibration_raw).hexdigest(),
        planner_manifest=planner,
        standalone_evidence=standalone,
        standalone_evidence_path=_relative(standalone_path),
        standalone_evidence_sha256=hashlib.sha256(standalone_raw).hexdigest(),
        source_hashes=P.live_source_hashes(),
        scheduler_time_limit=scheduler_time_limit,
        scheduler_memory=scheduler_memory,
    )
    P.validate_freeze(value, verify_live_sources=True)
    return value, _write_exclusive(output_path, value)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler-time", required=True)
    parser.add_argument("--scheduler-memory", required=True)
    args = parser.parse_args(argv)
    _, digest = freeze(
        P.CALIBRATION_RECEIPT_PATH, P.PLANNER_MANIFEST_PATH,
        P.STANDALONE_K32_PATH, P.FREEZE_PATH,
        args.scheduler_time, args.scheduler_memory,
    )
    print(digest)


if __name__ == "__main__":
    main()
