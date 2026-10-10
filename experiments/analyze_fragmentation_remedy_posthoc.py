#!/usr/bin/env python3
"""Post-hoc mechanism view of the frozen fragmentation-remedy analysis.

Descriptive and post hoc; changes no frozen estimand or decision.  Uses the
frozen outcomes of `analyze_fragmentation_remedy.py` (solved status with the
cost-conflict rule) on the pinned properties and reports per family:

* batching, on tasks that the plain and the batched heuristic both solve:
  tasks on which at least one batched image happened, tasks whose effort
  (expanded BDD nodes) is identical, and the median ratio of completed image
  calls (batched over plain) on tasks where batching happened;
* prune-only, on tasks that prune-only search and blind forward search both
  solve: tasks whose effort is identical, solved prune-only runs that pruned
  at least one dead end, and, on identical-effort tasks whose blind image
  time is at least one second, the median ratio of image time (prune-only
  over blind).

  analyze  write artifacts/fragmentation-remedy/posthoc-v1.json
  render   write paper/generated/fragmentation-remedy-posthoc-v1.tex
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import analyze_fragmentation_remedy as Frozen
import fragmentation_remedy_protocol as P
import render_pdb_profile_semantic_union_paper as Common


RenderError = Common.RenderError
SCRIPT_DIR = Path(__file__).resolve().parent
REPOSITORY_ROOT = SCRIPT_DIR.parent
EXPECTED_PROPERTIES_SHA256 = (
    "fbcf76f4bde39a7bf1203d8e5cbed79df76a3d31bf0aa2c644dedb1d2dc9b17f"
)
DEFAULT_ARTIFACT = Frozen.ARTIFACT_DIR / "posthoc-v1.json"
EXPECTED_ARTIFACT_SHA256 = (
    "ece88e410b3d498724fce5f0168c9181a5b7b0cc9ce822851800bd5d0f53cf2a"
)
DEFAULT_OUTPUT = (
    REPOSITORY_ROOT / "paper" / "generated" / "fragmentation-remedy-posthoc-v1.tex"
)
MIN_IMAGE_SECONDS = 1.0
MAX_TEX_BYTES = 16 * 1024


def _number(run, name):
    value = run.get(name)
    return value if isinstance(value, (int, float)) else None


def analyze(properties):
    cohort, runs = Frozen._index_runs(properties)
    outcomes, _ = Frozen._outcomes(cohort, runs)

    def run(label, task):
        return runs[(label, task.domain, task.problem)]

    def solved(label, task):
        return outcomes[(label, task)][0]

    families = {}
    for family in P.FAMILY_NAMES:
        plain, batch, prune = (
            "{}_plain".format(family), "{}_batch".format(family),
            "{}_prune".format(family))
        joint = [t for t in cohort if solved(plain, t) and solved(batch, t)]
        fired = [t for t in joint
                 if (_number(run(batch, t), "batched_images") or 0) > 0]
        call_ratios = [
            Frozen.Fraction(
                run(batch, t)["image_calls_completed"],
                run(plain, t)["image_calls_completed"])
            for t in fired
            if (_number(run(plain, t), "image_calls_completed") or 0) > 0
            and _number(run(batch, t), "image_calls_completed") is not None
        ]
        batch_record = {
            "tasks": len(joint),
            "fired": len(fired),
            "identical_effort": sum(
                outcomes[(batch, t)][2] == outcomes[(plain, t)][2]
                for t in joint),
            "image_call_ratio_median": Frozen._real(Frozen._median(call_ratios)),
        }
        joint = [t for t in cohort if solved(prune, t) and solved(P.BLIND_FW, t)]
        identical = [t for t in joint
                     if outcomes[(prune, t)][2] == outcomes[(P.BLIND_FW, t)][2]]
        time_ratios = []
        for t in identical:
            mine = _number(run(prune, t), "image_time")
            blind = _number(run(P.BLIND_FW, t), "image_time")
            if mine is not None and blind is not None and blind >= MIN_IMAGE_SECONDS:
                time_ratios.append(mine / blind)
        prune_record = {
            "tasks": len(joint),
            "identical_effort": len(identical),
            "solved": sum(solved(prune, t) for t in cohort),
            "pruned_dead_ends": sum(
                (_number(run(prune, t), "num_pruned_deadends") or 0) > 0
                for t in cohort if solved(prune, t)),
            "image_time_pairs": len(time_ratios),
            "image_time_ratio_median": Frozen._real(Frozen._median(time_ratios)),
        }
        families[family] = {"batch": batch_record, "prune": prune_record}
    return {
        "schema": "symbolic-search-heuristics/fragmentation-remedy-posthoc/v1",
        "descriptive": True,
        "min_image_seconds": MIN_IMAGE_SECONDS,
        "families": families,
    }


def command_analyze(args):
    raw_properties = Path(args.properties).read_bytes()
    if hashlib.sha256(raw_properties).hexdigest() != EXPECTED_PROPERTIES_SHA256:
        raise RenderError("properties differ from the pinned remedy run")
    artifact = analyze(json.loads(raw_properties))
    raw = Common._canonical_json(artifact) + b"\n"
    if DEFAULT_ARTIFACT.exists():
        raise RenderError("post-hoc artifact already exists")
    Frozen._write_atomic(DEFAULT_ARTIFACT, raw)
    digest = hashlib.sha256(raw).hexdigest()
    Frozen._write_atomic(
        str(DEFAULT_ARTIFACT) + ".sha256",
        "{}  {}\n".format(digest, DEFAULT_ARTIFACT.name).encode("ascii"))
    print(digest)
    return 0


def _load(path):
    raw = Common._read_regular(path, 1024 * 1024)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_ARTIFACT_SHA256:
        raise RenderError("post-hoc artifact is not the reviewed pin")
    sidecar = "{}  {}\n".format(digest, Path(path).name).encode("ascii")
    if Common._read_regular(Path(str(path) + ".sha256"), 256) != sidecar:
        raise RenderError("post-hoc sidecar differs from the pinned artifact")
    return json.loads(raw.decode("ascii")), digest


def render(data, digest):
    macros = []
    for family, prefix in (("ms", "Ms"), ("pdb", "Pdb"), ("pot", "Pot")):
        batch = data["families"][family]["batch"]
        prune = data["families"][family]["prune"]
        macros += [
            ("RemPh{}BatchTasks".format(prefix), str(batch["tasks"])),
            ("RemPh{}BatchFired".format(prefix), str(batch["fired"])),
            ("RemPh{}BatchSameEffort".format(prefix),
             str(batch["identical_effort"])),
            ("RemPh{}BatchCalls".format(prefix),
             "{:.2f}".format(batch["image_call_ratio_median"])),
            ("RemPh{}PruneTasks".format(prefix), str(prune["tasks"])),
            ("RemPh{}PruneSameEffort".format(prefix),
             str(prune["identical_effort"])),
            ("RemPh{}PruneDeadEnds".format(prefix),
             str(prune["pruned_dead_ends"])),
            ("RemPh{}PruneImagePairs".format(prefix),
             str(prune["image_time_pairs"])),
            ("RemPh{}PruneImageTime".format(prefix),
             "{:.2f}".format(prune["image_time_ratio_median"])),
        ]
    macros.append(("RemPhMaxPruneDeadEnds", str(max(
        data["families"][family]["prune"]["pruned_dead_ends"]
        for family in ("ms", "pdb", "pot")))))
    lines = [
        "% Generated post hoc from the fragmentation-remedy mechanism summary.",
        "% Descriptive only; changes no frozen estimand or decision.",
        "% Summary SHA-256: {}".format(digest),
    ] + [Common._macro(name, value) for name, value in macros]
    raw = ("\n".join(lines) + "\n").encode("ascii")
    if len(raw) > MAX_TEX_BYTES:
        raise RenderError("generated TeX exceeds its size limit")
    return raw


def command_render(args):
    data, digest = _load(args.artifact)
    raw = render(data, digest)
    if args.check:
        if Common._read_regular(args.output, MAX_TEX_BYTES) != raw:
            raise RenderError("generated TeX is stale")
        return 0
    if Path(args.output).resolve() != DEFAULT_OUTPUT.resolve():
        raise RenderError("--write is restricted to the generated-paper path")
    Frozen._write_atomic(args.output, raw)
    return 0


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    a = sub.add_parser("analyze")
    a.add_argument("--properties", type=Path, default=Frozen.DEFAULT_PROPERTIES)
    r = sub.add_parser("render")
    r.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    r.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    modes = r.add_mutually_exclusive_group(required=True)
    modes.add_argument("--write", action="store_true")
    modes.add_argument("--check", action="store_true")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.command == "analyze":
        return command_analyze(args)
    return command_render(args)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RenderError, Frozen.AnalysisError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
