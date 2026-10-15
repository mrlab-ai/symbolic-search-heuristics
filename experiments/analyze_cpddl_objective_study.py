#!/usr/bin/env python3
"""Frozen analysis of the CPDDL objective study (cpddl_objective_protocol.md).

Applies the frozen functions of analyze_cpddl_ghseta_study.py to the four
configurations of this study: one primary exact two-sided sign test of
forward GHSETA* with initial-state operator potentials against blind
forward search, coverage, PAR2, and the decomposition of the forward effort.

  analyze     write artifacts/cpddl-objective/analysis-v1.json
  self-test   check the configuration wiring on synthetic cells
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import analyze_cpddl_ghseta_study as Study
import render_pdb_profile_semantic_union_paper as Common

SCRIPT_DIR = Path(__file__).resolve().parent
COHORT_DIR = Study.ROOT / "holdout-objective-I"
ARTIFACT = SCRIPT_DIR / "artifacts" / "cpddl-objective" / "analysis-v1.json"
PROTOCOL_PATH = SCRIPT_DIR / "cpddl_objective_protocol.md"
PROTOCOL_SHA256 = (
    "d740b38df22ffdcb225afecc74dfb8425d62f6e79fe4a76348966761a918054b"
)

Study.LABELS = ("cp_blind_fw", "cp_pot_fw", "cp_blind_fw_prof", "cp_pot_fw_prof")
Study.PRIMARY = (("H-I", "cp_pot_fw", "cp_blind_fw"),)
Study.CONTEXT = ()


def command_analyze():
    raw = PROTOCOL_PATH.read_bytes()
    if PROTOCOL_SHA256 == "TO_PIN" or hashlib.sha256(raw).hexdigest() != PROTOCOL_SHA256:
        raise Study.AnalysisError("protocol is not frozen")
    tasks, cells = Study.load_cells(COHORT_DIR)
    if len(tasks) != 1052:
        raise Study.AnalysisError("unexpected cohort size")
    artifact = Study.analyze(tasks, cells, pilot=False)
    artifact["schema"] = "symbolic-search-heuristics/cpddl-objective-analysis/v1"
    artifact["protocol_sha256"] = PROTOCOL_SHA256
    data = Common._canonical_json(artifact) + b"\n"
    if ARTIFACT.exists():
        raise Study.AnalysisError("analysis artifact already exists")
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_bytes(data)
    digest = hashlib.sha256(data).hexdigest()
    Path(str(ARTIFACT) + ".sha256").write_text(
        "{}  {}\n".format(digest, ARTIFACT.name))
    print(digest)
    print(json.dumps(artifact["claims"], sort_keys=True))
    return 0


def _self_test():
    tasks = [("d{}".format(i % 30), "p{}.pddl".format(i)) for i in range(120)]
    cells = {}
    for i, task in enumerate(tasks):
        for label in Study.LABELS:
            solved = i % 2 == 0 or ("pot" in label and i % 4 == 1)
            cell = {"solved": solved, "cost": 7 if solved else None,
                    "wall_seconds": 1.0, "exit_code": 0 if solved else -24}
            if label.endswith("_prof"):
                e, u, s = ((400, 200, 3) if "pot" in label else (1000, 1000, 50))
                cell.update({"wbh_expand_nodes": e, "wbh_layer_nodes": u,
                             "wbh_expand_states": s, "wbh_layers": 2,
                             "wbh_done": {}})
            cells[(label,) + task] = cell
    result = Study.analyze(tasks, cells, pilot=False)
    d = result["decomposition"]
    if (result["claims"] != {"H-I": "better"} or d["helpful"] != 60
            or d["helpful_u_median"] != 0.2 or d["helpful_f_median"] != 2.0):
        raise Study.AnalysisError("self-test failed: {}".format(result["claims"]))
    print("self-test passed")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("analyze")
    sub.add_parser("self-test")
    args = parser.parse_args(argv)
    return _self_test() if args.command == "self-test" else command_analyze()


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, Study.AnalysisError) as err:
        print("error: {}".format(err))
        raise SystemExit(2)
