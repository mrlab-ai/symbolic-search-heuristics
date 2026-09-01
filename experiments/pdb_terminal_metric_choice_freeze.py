#!/usr/bin/env python3
"""Freeze the dual-metric campaign after outcome-blind calibration."""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

import jj_cached_revision as JJ
import pdb_terminal_metric_choice_io as CampaignIO
import pdb_terminal_metric_choice_protocol as P


class FreezeError(RuntimeError):
    pass


BASE_A_FETCH_RECEIPT_PATH = P.BASE_A_ARTIFACT_DIR / "fetch-receipt-v1.json"
BASE_A_FETCH_RECEIPT_PIN_PATH = (
    P.BASE_A_ARTIFACT_DIR / "fetch-receipt-v1.sha256"
)
BASE_A_PROPERTIES_PATH = (
    P.SCRIPT_DIR / "data" / "exp_pdb_terminal_incidence_confirmation_a-eval"
    / "properties"
)
BASE_B_PARSE_RECEIPT_PIN_PATH = P.BASE_B_PARSE_RECEIPT_PATH.with_suffix(
    ".sha256"
)
BASE_B_FETCH_RECEIPT_PIN_PATH = P.BASE_B_FETCH_RECEIPT_PATH.with_suffix(
    ".sha256"
)


def _relative(path: Path) -> str:
    try:
        lexical = Path(os.path.abspath(path))
        root = Path(os.path.abspath(P.REPO))
        return lexical.relative_to(root).as_posix()
    except ValueError as err:
        raise FreezeError("bound evidence must be inside the repository") from err


def _require_clean_parent(revision: str | None) -> str:
    try:
        if JJ.live_working_copy_diff_summary(P.REPO):
            raise FreezeError("freeze requires a clean empty working-copy commit")
        parent = JJ.parent_commit(P.REPO)
    except JJ.JjCacheError as err:
        raise FreezeError("cannot resolve the clean Jujutsu parent") from err
    if revision is None:
        revision = parent
    if revision != parent or P.COMMIT_RE.fullmatch(revision or "") is None:
        raise FreezeError(
            "freeze repository revision must be the clean working-copy parent"
        )
    return revision


def _attest_tracked_file(
    path: Path, expected: str, revision: str, label: str,
) -> str:
    path = Path(os.path.abspath(path))
    root = Path(os.path.abspath(P.REPO))
    relative = _relative(path)
    try:
        before = P.sha256_file(
            path, expected_path=path, root=root, label=label,
        )
    except P.ProtocolError as err:
        raise FreezeError("{} is missing or unsafe".format(label)) from err
    if before != expected:
        raise FreezeError("{} changed before revision check".format(label))
    try:
        tracked = JJ.tracked_file_sha256(P.REPO, revision, relative)
    except JJ.JjCacheError as err:
        raise FreezeError("{} is not committed at the freeze revision".format(
            label
        )) from err
    if tracked != expected:
        raise FreezeError("{} differs from the freeze revision".format(label))
    try:
        after = P.sha256_file(
            path, expected_path=path, root=root, label=label,
        )
    except P.ProtocolError as err:
        raise FreezeError("{} changed during revision check".format(label)) from err
    if after != expected:
        raise FreezeError("{} changed during revision check".format(label))
    return relative


def _pin_sha256(receipt_sha256: str) -> str:
    if P.SHA256_RE.fullmatch(receipt_sha256 or "") is None:
        raise FreezeError("bound receipt pin digest is invalid")
    return hashlib.sha256((receipt_sha256 + "\n").encode("ascii")).hexdigest()


def _add_binding(
    bindings: dict[str, str], path: Path | str, digest: str, label: str,
) -> None:
    if P.SHA256_RE.fullmatch(digest or "") is None:
        raise FreezeError("{} digest is invalid".format(label))
    if isinstance(path, str):
        candidate = P.REPO / path
        if _relative(candidate) != path:
            raise FreezeError("{} path changed".format(label))
        relative = path
    else:
        relative = _relative(path)
    previous = bindings.setdefault(relative, digest)
    if previous != digest:
        raise FreezeError(
            "repository closure has conflicting bindings for {}".format(relative)
        )


def _base_snapshot_bindings(
    snapshot: dict, standalone_binding: dict,
) -> dict[str, str]:
    """Return every in-repository A/B/V6 artifact bound by the snapshot."""
    try:
        P.validate_base_snapshot(snapshot)
        P.validate_standalone_source_binding(standalone_binding)
    except P.ProtocolError as err:
        raise FreezeError("sealed A/B/V6 binding is invalid") from err
    bindings: dict[str, str] = {}
    _add_binding(
        bindings, snapshot["base_b_freeze_path"],
        snapshot["base_b_freeze_sha256"], "Confirmation B freeze",
    )
    base_sources = snapshot["base_b_experiment_source_sha256"]
    for relative, digest in base_sources.items():
        _add_binding(
            bindings, relative, digest,
            "Confirmation B source {}".format(relative),
        )
    for path_field, hash_field, label in (
        ("parse_receipt_path", "parse_receipt_sha256", "Confirmation B parse"),
        ("fetch_receipt_path", "fetch_receipt_sha256", "Confirmation B fetch"),
        ("properties_path", "properties_sha256", "Confirmation B properties"),
    ):
        _add_binding(
            bindings, standalone_binding[path_field],
            standalone_binding[hash_field], label,
        )
    _add_binding(
        bindings, BASE_B_PARSE_RECEIPT_PIN_PATH,
        _pin_sha256(standalone_binding["parse_receipt_sha256"]),
        "Confirmation B parse receipt pin",
    )
    _add_binding(
        bindings, BASE_B_FETCH_RECEIPT_PIN_PATH,
        _pin_sha256(standalone_binding["fetch_receipt_sha256"]),
        "Confirmation B fetch receipt pin",
    )

    authorization = snapshot["confirmation_a_authorization"]
    for path_field, hash_field, label in (
        ("receipt_path", "receipt_sha256", "Confirmation A authorization"),
        ("first_output_path", "first_output_sha256", "Confirmation A output"),
        ("second_output_path", "second_output_sha256", "Confirmation A repeat"),
    ):
        _add_binding(
            bindings, authorization[path_field], authorization[hash_field], label,
        )
    _add_binding(
        bindings, authorization["receipt_pin_path"],
        _pin_sha256(authorization["receipt_sha256"]),
        "Confirmation A authorization pin",
    )
    _add_binding(
        bindings, BASE_A_FETCH_RECEIPT_PATH,
        authorization["fetch_receipt_sha256"], "Confirmation A fetch receipt",
    )
    _add_binding(
        bindings, BASE_A_FETCH_RECEIPT_PIN_PATH,
        _pin_sha256(authorization["fetch_receipt_sha256"]),
        "Confirmation A fetch receipt pin",
    )
    _add_binding(
        bindings, BASE_A_PROPERTIES_PATH,
        authorization["input_properties_sha256"], "Confirmation A properties",
    )

    v6 = snapshot["source_audit_v6"]
    for path_field, hash_field, label in (
        ("attestation_path", "attestation_sha256", "source-audit V6 attestation"),
        ("terminal_diagnostic_path", "terminal_diagnostic_sha256", "source-audit V6 diagnostic"),
        ("launch_intent_path", "launch_intent_sha256", "source-audit V6 intent"),
        ("launch_receipt_path", "launch_receipt_sha256", "source-audit V6 launch"),
        (
            "execution_receipt_path", "execution_receipt_sha256",
            "source-audit V6 execution",
        ),
        ("seal_plan_path", "seal_plan_sha256", "source-audit V6 seal plan"),
        (
            "union_root_stage_path", "union_root_stage_sha256",
            "source-audit V6 union-root stage",
        ),
        (
            "union_stage_path", "union_stage_sha256",
            "source-audit V6 union stage",
        ),
        (
            "candidate_stage_path", "candidate_stage_sha256",
            "source-audit V6 candidate stage",
        ),
        (
            "attestation_stage_path", "attestation_stage_sha256",
            "source-audit V6 attestation stage",
        ),
    ):
        _add_binding(bindings, v6[path_field], v6[hash_field], label)
    _add_binding(
        bindings, P.V6_CODE_MANIFEST_PATH, v6["code_manifest_sha256"],
        "source-audit V6 code manifest",
    )
    _add_binding(
        bindings, P.V6_SLURM_PATH, v6["slurm_template_sha256"],
        "source-audit V6 Slurm source",
    )
    tracked = v6["tracked_file_sha256"]
    if not isinstance(tracked, dict) or set(tracked) != set(P.V6_SCOPED_FILES):
        raise FreezeError("source-audit V6 tracked closure changed")
    for relative, digest in tracked.items():
        _add_binding(
            bindings, relative, digest,
            "source-audit V6 tracked file {}".format(relative),
        )
    return dict(sorted(bindings.items()))


def _freeze_closure_bindings(
    snapshot: dict, *, calibration_sha256: str, planner_sha256: str,
    standalone_sha256: str, standalone_binding: dict,
    source_hashes: dict[str, str],
) -> dict[str, str]:
    bindings = _base_snapshot_bindings(snapshot, standalone_binding)
    for path, digest, label in (
        (P.CALIBRATION_RECEIPT_PATH, calibration_sha256, "calibration receipt"),
        (P.PLANNER_MANIFEST_PATH, planner_sha256, "planner manifest"),
        (P.STANDALONE_K32_PATH, standalone_sha256, "standalone K32 evidence"),
    ):
        _add_binding(bindings, path, digest, label)
    if not isinstance(source_hashes, dict) or set(source_hashes) != set(
        P.SOURCE_FILES
    ):
        raise FreezeError("campaign source closure changed")
    for relative, digest in source_hashes.items():
        _add_binding(bindings, relative, digest, "campaign source " + relative)
    return dict(sorted(bindings.items()))


def _launch_closure_bindings(freeze: dict, freeze_sha256: str) -> dict[str, str]:
    try:
        snapshot = freeze["base_confirmation_b"]
        calibration = freeze["calibration"]
        standalone = freeze["standalone_k32"]
        planner_sha = hashlib.sha256(
            P.canonical_json_line(freeze["planner"])
        ).hexdigest()
        bindings = _freeze_closure_bindings(
            snapshot, calibration_sha256=calibration["receipt_sha256"],
            planner_sha256=planner_sha,
            standalone_sha256=standalone["evidence_sha256"],
            standalone_binding=standalone["sealed_b_input"],
            source_hashes=freeze["experiment_source_sha256"],
        )
    except (KeyError, TypeError, ValueError) as err:
        raise FreezeError("frozen repository closure is incomplete") from err
    _add_binding(bindings, P.FREEZE_PATH, freeze_sha256, "campaign freeze")
    return dict(sorted(bindings.items()))


def _attest_repository_closure(
    revision: str, bindings: dict[str, str],
) -> None:
    if not isinstance(bindings, dict) or not bindings:
        raise FreezeError("repository closure is absent")
    for relative, digest in sorted(bindings.items()):
        _attest_tracked_file(
            P.REPO / relative, digest, revision,
            "repository closure {}".format(relative),
        )


def _source_hashes(revision: str) -> dict[str, str]:
    hashes = {}
    for relative in P.SOURCE_FILES:
        path = Path(os.path.abspath(P.REPO / relative))
        root = Path(os.path.abspath(P.REPO))
        live = P.sha256_file(
            path, expected_path=path, root=root, label="campaign source",
        )
        _attest_tracked_file(
            path, live, revision, "campaign source {}".format(relative)
        )
        hashes[relative] = live
    return hashes


def _require_ancestors(snapshot: dict, revision: str) -> None:
    ancestors = (
        P.REQUIRED_PLANNER_REVISION,
        snapshot["base_b_freeze_repository_revision"],
        snapshot["source_audit_v6"]["repository_commit_id"],
        snapshot["source_audit_v6"][
            "pre_diagnosis_repository_commit_id"
        ],
    )
    try:
        for ancestor in ancestors:
            JJ.require_ancestor(P.REPO, ancestor, revision)
    except JJ.JjCacheError as err:
        raise FreezeError(
            "planner, Confirmation B, or V6 producer is not an ancestor"
        ) from err


def _rebuild_standalone(standalone: dict, snapshot: dict, planner: dict) -> None:
    import pdb_terminal_metric_choice_standalone as Standalone

    records, live_binding = Standalone.sealed_b_records()
    rebuilt = Standalone.build_evidence(
        records, snapshot, planner, live_binding
    )
    if P.canonical_json(rebuilt) != P.canonical_json(standalone):
        raise FreezeError("standalone K32 evidence does not rebuild from sealed B")


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
    freeze_repository_revision: str | None = None,
) -> tuple[dict, str]:
    if any((
        Path(calibration_path) != P.CALIBRATION_RECEIPT_PATH,
        Path(planner_manifest_path) != P.PLANNER_MANIFEST_PATH,
        Path(standalone_path) != P.STANDALONE_K32_PATH,
        Path(output_path) != P.FREEZE_PATH,
    )):
        raise FreezeError("campaign freeze input/output path changed")
    revision = _require_clean_parent(freeze_repository_revision)
    # Calibration is opened and completely validated before any A/B/V6
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
    P.validate_planner_manifest(planner)
    if P.canonical_json(calibration["planner"]) != P.canonical_json(planner):
        raise FreezeError("calibration planner binding changed")
    # The freeze independently reopens B after the standalone producer's first
    # permitted B access. Calibration has already been accepted in full.
    snapshot = P.snapshot_sealed_b(calibration)
    standalone_raw, standalone = P.load_canonical(
        standalone_path, "standalone K32 evidence",
        expected_path=P.STANDALONE_K32_PATH,
    )
    P.validate_standalone_evidence(standalone, snapshot, planner)
    _rebuild_standalone(standalone, snapshot, planner)
    _require_ancestors(snapshot, revision)
    source_hashes = _source_hashes(revision)
    closure = _freeze_closure_bindings(
        snapshot,
        calibration_sha256=hashlib.sha256(calibration_raw).hexdigest(),
        planner_sha256=hashlib.sha256(planner_raw).hexdigest(),
        standalone_sha256=hashlib.sha256(standalone_raw).hexdigest(),
        standalone_binding=standalone["sealed_b_input"],
        source_hashes=source_hashes,
    )
    _attest_repository_closure(revision, closure)
    value = P.build_freeze(
        freeze_repository_revision=revision,
        base_snapshot=snapshot,
        calibration_receipt=calibration,
        calibration_receipt_path=_relative(calibration_path),
        calibration_receipt_sha256=hashlib.sha256(calibration_raw).hexdigest(),
        planner_manifest=planner,
        standalone_evidence=standalone,
        standalone_evidence_path=_relative(standalone_path),
        standalone_evidence_sha256=hashlib.sha256(standalone_raw).hexdigest(),
        source_hashes=source_hashes,
        scheduler_time_limit=scheduler_time_limit,
        scheduler_memory=scheduler_memory,
    )
    P.validate_freeze(value, verify_live_sources=True)
    if _require_clean_parent(revision) != revision:
        raise FreezeError("freeze repository revision changed before publication")
    _require_ancestors(snapshot, revision)
    _rebuild_standalone(standalone, snapshot, planner)
    _attest_repository_closure(revision, closure)
    return value, _write_exclusive(output_path, value)


def main(argv=None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scheduler-time", required=True)
    parser.add_argument("--scheduler-memory", required=True)
    parser.add_argument("--freeze-repository-revision")
    args = parser.parse_args(argv)
    _, digest = freeze(
        P.CALIBRATION_RECEIPT_PATH, P.PLANNER_MANIFEST_PATH,
        P.STANDALONE_K32_PATH, P.FREEZE_PATH,
        args.scheduler_time, args.scheduler_memory,
        args.freeze_repository_revision,
    )
    print(digest)


if __name__ == "__main__":
    main()
