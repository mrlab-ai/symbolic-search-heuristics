#!/usr/bin/env python3
"""Create the prospective V11 source/planner freeze for Confirmation B."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

import jj_cached_revision as JJ
import pdb_terminal_incidence_confirmation_b_protocol as P


class FreezeError(RuntimeError):
    pass


SCRIPT_DIR = Path(__file__).resolve().parent
REPO = SCRIPT_DIR.parent
REVISION_CACHE = SCRIPT_DIR / "data" / "revision-cache"


def _relative(path: Path) -> str:
    try:
        return Path(os.path.abspath(path)).relative_to(
            Path(os.path.abspath(REPO))
        ).as_posix()
    except ValueError as err:
        raise FreezeError("freeze input escapes the repository") from err


def _attest_tracked_file(
    path: Path, expected: str, revision: str, label: str,
) -> str:
    relative = _relative(path)
    try:
        before = P.sha256_file(path)
    except P.ProtocolError as err:
        raise FreezeError("{} is not a regular live file".format(label)) from err
    if before != expected:
        raise FreezeError("{} changed live before revision check".format(label))
    try:
        tracked = JJ.tracked_file_sha256(REPO, revision, relative)
    except JJ.JjCacheError as err:
        raise FreezeError(
            "{} is not committed at the freeze revision".format(label)
        ) from err
    if tracked != expected:
        raise FreezeError("{} differs from the freeze revision".format(label))
    try:
        after = P.sha256_file(path)
    except P.ProtocolError as err:
        raise FreezeError("{} changed during revision check".format(label)) from err
    if after != expected:
        raise FreezeError("{} changed during revision check".format(label))
    return relative


def _source_hashes(revision: str) -> dict[str, str]:
    hashes = {}
    for relative in P.EXPERIMENT_SOURCE_FILES:
        path = REPO / relative
        live = P.sha256_file(path)
        _attest_tracked_file(
            path, live, revision, "experiment source {}".format(relative),
        )
        hashes[relative] = live
    return hashes


def _require_clean_parent(revision: str | None) -> str:
    try:
        if JJ.live_working_copy_diff_summary(REPO):
            raise FreezeError("freeze requires a clean empty working-copy commit")
        parent = JJ.parent_commit(REPO)
    except JJ.JjCacheError as err:
        raise FreezeError("cannot resolve the clean Jujutsu parent") from err
    if revision is None:
        revision = parent
    if revision != parent or P.COMMIT_RE.fullmatch(revision) is None:
        raise FreezeError(
            "freeze repository revision must be the clean working-copy parent"
        )
    return revision


def _require_source_ancestry(
    bindings: dict, authorization: dict, revision: str,
) -> None:
    source = bindings["preflight_source_repository_commit_id"]
    preflight = bindings["preflight_seal_repository_commit_id"]
    seal = bindings["seal_repository_commit_id"]
    confirmation_a_freeze = authorization[
        "confirmation_a_freeze_repository_revision"
    ]
    try:
        JJ.require_ancestor(REPO, source, preflight)
        JJ.require_ancestor(REPO, preflight, seal)
        JJ.require_ancestor(REPO, seal, confirmation_a_freeze)
        JJ.require_ancestor(REPO, confirmation_a_freeze, revision)
        JJ.require_ancestor(REPO, P.PLANNER_REVISION_REQUIRED, revision)
    except JJ.JjCacheError as err:
        raise FreezeError(
            "V11 S-to-P-to-Q-to-A-to-B chain or planner is not ancestral"
        ) from err


def _planner_freeze() -> dict:
    cached = JJ.JjCachedFastDownwardRevision(
        REVISION_CACHE, REPO, P.PLANNER_REVISION_REQUIRED,
        list(P.BUILD_OPTIONS),
    )
    cached.cache()
    planner = cached.attest()
    if (
        planner.get("revision") != P.PLANNER_REVISION_REQUIRED
        or planner.get("build_options") != list(P.BUILD_OPTIONS)
    ):
        raise FreezeError("planner cache identifies the wrong revision")
    required = ("downward_sha256", "preprocess_sha256", "tree_manifest_sha256")
    if any(P.SHA256_RE.fullmatch(planner.get(name, "")) is None
           for name in required):
        raise FreezeError("planner cache attestation is incomplete")
    return {
        "revision": P.PLANNER_REVISION_REQUIRED,
        "cache_name": cached.name,
        "build_options": list(P.BUILD_OPTIONS),
        **{name: planner[name] for name in required},
    }


def _authorization_provenance(authorization: dict) -> dict:
    return {
        **{
            key: _relative(value)
            for key, value in authorization.items()
            if key.endswith("_path")
        },
        **{
            key: value
            for key, value in authorization.items()
            if not key.endswith("_path")
        },
    }


def _load_authorization(
    *, confirmation_a_receipt: Path,
    confirmation_a_receipt_pin: Path,
    confirmation_a_first_output: Path,
    confirmation_a_second_output: Path,
) -> dict:
    return P.load_confirmation_a_authorization(
        confirmation_a_receipt,
        confirmation_a_receipt_pin,
        confirmation_a_first_output,
        confirmation_a_second_output,
    )


def _attest_authorization(authorization: dict, revision: str) -> None:
    hashes = {
        authorization["receipt_path"]: authorization["receipt_sha256"],
        authorization["first_output_path"]: authorization[
            "first_output_sha256"
        ],
        authorization["second_output_path"]: authorization[
            "second_output_sha256"
        ],
        authorization["receipt_pin_path"]: hashlib.sha256(
            (authorization["receipt_sha256"] + "\n").encode("ascii")
        ).hexdigest(),
        authorization["confirmation_a_freeze_path"]: authorization[
            "source_audit_provenance"
        ]["confirmation_a_freeze_sha256"],
    }
    for path, expected in hashes.items():
        _attest_tracked_file(
            path, expected, revision, "Confirmation A authorization",
        )


def _design(materials: P.SourceMaterials) -> dict:
    cohort_tasks = len(materials.tasks)
    cells = cohort_tasks * P.CONFIG_COUNT
    array_tasks = (cells + P.RUNS_PER_ARRAY_TASK - 1) // P.RUNS_PER_ARRAY_TASK
    return {
        "protocol_sha256": P.sha256_file(P.PROTOCOL_PATH),
        "option_matrix_sha256": P.option_matrix_digest(),
        "cohort_tasks": cohort_tasks,
        "target_cohort_tasks": P.TARGET_COHORT_TASKS,
        "minimum_cohort_tasks": P.MIN_COHORT_TASKS,
        "maximum_cohort_tasks": P.MAX_COHORT_TASKS,
        "configs": P.CONFIG_COUNT,
        "cells": cells,
        "expected_array_tasks": array_tasks,
        "runs_per_array_task": P.RUNS_PER_ARRAY_TASK,
        "run_order_protocol": P.RUN_ORDER_PROTOCOL,
        "run_cell_mapping_sha256": P.run_cell_mapping_digest(materials.tasks),
        "probe_layers": P.PROBE_LAYERS,
        "par2_seconds": P.PAR2_SECONDS,
        "bootstrap_replicates": P.BOOTSTRAP_REPLICATES,
        "bootstrap_seed": P.BOOTSTRAP_SEED,
        "minimum_mechanism_tasks": P.MIN_MECHANISM_TASKS,
        "minimum_mechanism_families": P.MIN_MECHANISM_FAMILIES,
        "non_gating_reference_labels": list(P.NON_GATING_REFERENCE_LABELS),
    }


def build_freeze(
    *, source_seal_revision: str,
    confirmation_a_receipt: Path,
    confirmation_a_receipt_pin: Path,
    confirmation_a_first_output: Path,
    confirmation_a_second_output: Path,
    freeze_repository_revision: str,
) -> dict:
    P.validate_static_design()
    materials = P.load_source_materials(source_seal_revision)
    authorization = _load_authorization(
        confirmation_a_receipt=confirmation_a_receipt,
        confirmation_a_receipt_pin=confirmation_a_receipt_pin,
        confirmation_a_first_output=confirmation_a_first_output,
        confirmation_a_second_output=confirmation_a_second_output,
    )
    P._validate_confirmation_a_source_link(authorization, materials)
    _require_source_ancestry(
        materials.bindings, authorization, freeze_repository_revision,
    )
    _attest_authorization(authorization, freeze_repository_revision)
    planner = _planner_freeze()
    if authorization.get("planner_identity") != planner:
        raise FreezeError("Confirmation A and B do not use the exact same planner")
    return {
        "schema": P.FREEZE_SCHEMA,
        "freeze_repository_revision": freeze_repository_revision,
        "source_audit": materials.source_audit,
        "confirmation_a_authorization": _authorization_provenance(authorization),
        "planner": planner,
        "design": _design(materials),
        "experiment_source_sha256": _source_hashes(
            freeze_repository_revision
        ),
    }


def _revalidate_before_write(
    value: dict, *, source_seal_revision: str,
    confirmation_a_receipt: Path,
    confirmation_a_receipt_pin: Path,
    confirmation_a_first_output: Path,
    confirmation_a_second_output: Path,
    freeze_repository_revision: str,
) -> None:
    if _require_clean_parent(freeze_repository_revision) != freeze_repository_revision:
        raise FreezeError("freeze revision changed during planner caching")
    authorization = _load_authorization(
        confirmation_a_receipt=confirmation_a_receipt,
        confirmation_a_receipt_pin=confirmation_a_receipt_pin,
        confirmation_a_first_output=confirmation_a_first_output,
        confirmation_a_second_output=confirmation_a_second_output,
    )
    _attest_authorization(authorization, freeze_repository_revision)
    if authorization.get("planner_identity") != value.get("planner"):
        raise FreezeError("Confirmation A/B planner identity changed during caching")
    if value.get("freeze_repository_revision") != freeze_repository_revision:
        raise FreezeError("freeze repository revision changed during caching")
    if value.get("experiment_source_sha256") != _source_hashes(
        freeze_repository_revision
    ):
        raise FreezeError("experiment sources changed during planner caching")
    materials = P.load_source_materials(source_seal_revision)
    P._validate_confirmation_a_source_link(authorization, materials)
    _require_source_ancestry(
        materials.bindings, authorization, freeze_repository_revision,
    )
    if (
        materials.bindings["seal_repository_commit_id"]
        != source_seal_revision
        or P.canonical_json(value.get("source_audit"))
        != P.canonical_json(materials.source_audit)
    ):
        raise FreezeError("V11 source changed during planner caching")
    if P.canonical_json(value.get("confirmation_a_authorization")) != (
        P.canonical_json(_authorization_provenance(authorization))
    ):
        raise FreezeError("Confirmation A authorization changed during caching")


def _write_exclusive(path: Path, value: dict) -> str:
    raw = P.canonical_json_line(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as err:
        raise FreezeError("Confirmation B freeze already exists") from err
    return hashlib.sha256(raw).hexdigest()


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-seal-revision", required=True)
    parser.add_argument(
        "--confirmation-a-receipt", type=Path,
        default=P.CONFIRMATION_A_RECEIPT_PATH,
    )
    parser.add_argument(
        "--confirmation-a-receipt-pin", type=Path,
        default=P.CONFIRMATION_A_RECEIPT_PIN_PATH,
    )
    parser.add_argument(
        "--confirmation-a-first-output", type=Path,
        default=P.CONFIRMATION_A_FIRST_OUTPUT_PATH,
    )
    parser.add_argument(
        "--confirmation-a-second-output", type=Path,
        default=P.CONFIRMATION_A_SECOND_OUTPUT_PATH,
    )
    parser.add_argument("--freeze-repository-revision")
    parser.add_argument("--output", type=Path, default=P.FREEZE_PATH)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    revision = _require_clean_parent(args.freeze_repository_revision)
    inputs = {
        "source_seal_revision": args.source_seal_revision,
        "confirmation_a_receipt": args.confirmation_a_receipt,
        "confirmation_a_receipt_pin": args.confirmation_a_receipt_pin,
        "confirmation_a_first_output": args.confirmation_a_first_output,
        "confirmation_a_second_output": args.confirmation_a_second_output,
        "freeze_repository_revision": revision,
    }
    value = build_freeze(**inputs)
    _revalidate_before_write(value, **inputs)
    digest = _write_exclusive(args.output, value)
    if args.output.resolve() == P.FREEZE_PATH.resolve():
        P._load_freeze(P.FREEZE_PATH)
    print(json.dumps({
        "freeze": str(args.output),
        "freeze_sha256": digest,
        "planner_revision": P.PLANNER_REVISION_REQUIRED,
        "freeze_repository_revision": revision,
        "source_seal_revision": args.source_seal_revision,
        "guided_b_candidate_indices_sha256": value["source_audit"][
            "guided_b"
        ]["candidate_indices_sha256"],
        "guided_b_source_projection_sha256": value["source_audit"][
            "guided_b"
        ]["source_projection_sha256"],
        "confirmation_a_authorization_receipt_sha256": value[
            "confirmation_a_authorization"
        ]["receipt_sha256"],
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (FreezeError, P.ProtocolError, JJ.JjCacheError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
