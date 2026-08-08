#!/usr/bin/env python3
"""Frozen-revision screen of symbolic heuristic construction choices.

This is the second predeclared 50-task pilot. It reuses the outcome-enriched
manifest and the 300-second/8-GiB limits from ``exp_ms_caps_pilot.py`` while
holding the planner revision fixed. The twenty-one labels and exact search options
are:

  blind_fw          sym_fw()
  ms_exact          sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false)
  ms_cap8           sym_fw_ms(max_states=10000,value_cap=8,align_merge_order=false)
  ms_cap16          sym_fw_ms(max_states=10000,value_cap=16,align_merge_order=false)
  ms_exact_prune    sym_fw_ms(...,value_cap=-1,align_merge_order=false,prune_only=true)
  ms_exact_w4       sym_fw_ms(...,value_cap=-1,align_merge_order=false,batch_f_window=4)
  ms_exact_w16      sym_fw_ms(...,value_cap=-1,align_merge_order=false,batch_f_window=16)
  ms_cap8_w4        sym_fw_ms(...,value_cap=8,align_merge_order=false,batch_f_window=4)
  ms_cap8_w16       sym_fw_ms(...,value_cap=8,align_merge_order=false,batch_f_window=16)
  ms_cap16_w4       sym_fw_ms(...,value_cap=16,align_merge_order=false,batch_f_window=4)
  ms_cap16_w16      sym_fw_ms(...,value_cap=16,align_merge_order=false,batch_f_window=16)
  pdb_bdd_b100k     sym_fw_pdb(budget=100000,goal_directed=false)
  pdb_goal_b100k    sym_fw_pdb(budget=100000,goal_directed=true)
  pdb_goal_w4       sym_fw_pdb(...,goal_directed=true,batch_f_window=4)
  pdb_goal_w16      sym_fw_pdb(...,goal_directed=true,batch_f_window=16)
  pot_rect_m8       sym_fw_pot(m=8,all_states_objective=false,lpsolver=cplex)
  pot_rect_m8_w4    sym_fw_pot(m=8,all_states_objective=false,lpsolver=cplex,batch_f_window=4)
  pot_rect_m8_w16   sym_fw_pot(m=8,all_states_objective=false,lpsolver=cplex,batch_f_window=16)
  pot_rect_m16      sym_fw_pot(m=16,all_states_objective=false,lpsolver=cplex)
  pot_rect_m16_w4   sym_fw_pot(m=16,all_states_objective=false,lpsolver=cplex,batch_f_window=4)
  pot_rect_m16_w16  sym_fw_pot(m=16,all_states_objective=false,lpsolver=cplex,batch_f_window=16)

The matched PDB pair isolates variable selection at a common abstract-state
budget. The implementation at the frozen revision rectifies each potential
with max(0, P). The matrix crosses informative M&S distances with terminal
caps, the paper's pruning-only proposal, and two same-g contour windows. The
goal-directed PDB and both rectified potential sizes (M=8 and M=16) receive
the same two windows. This separates heuristic construction from the algorithm
used to amortize image calls. Cap 2/4/32 are evaluated in the independent cap
experiment and are not duplicated here.

This manifest was selected using earlier blind/exact-M&S outcomes (7 archived
blind-only coverage cases, 13 exact-only coverage cases, and 30 jointly solved
controls). The legacy archive does not identify the resource cause of an
unsolved row.
It is appropriate for screening construction choices, not for estimating
unbiased benchmark-wide coverage or runtime.

Inspect steps (does not launch):
  experiments/.venv/bin/python experiments/exp_heuristic_choices_pilot.py --help

Run only after explicit sign-off and after the c280 revision cache exists.
Use the same scheduler environment for both commands; never combine the steps:
  experiments/.venv/bin/python experiments/exp_heuristic_choices_pilot.py build
  experiments/.venv/bin/python experiments/exp_heuristic_choices_pilot.py start
  experiments/.venv/bin/python experiments/exp_heuristic_choices_pilot.py parse fetch report
"""
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import exp_common as C
import suite_cost_manifest
from downward import suites
from exp_ms_caps_pilot import read_manifest


# This is the clean-built implementation revision with corrected schema-v2
# metrics and contour batching. Pin it explicitly so later paper or
# experiment-script commits cannot silently change the planner binary.
FROZEN_REVISION = "c2800d7e65abb61d4b94b08a5487f701ceb41d6b"
PILOT_DIGEST = "c63a59ee2096b40c24f80db895ee2c0d22aabc2630c823b882e7f50f529a481b"
OPTION_MATRIX_DIGEST = "5341ab3b6594687c9a7d483f39d087ba5c9baa56321928f0bd92c67bf4590ece"
SELECTION_RULE = "family-max-solved-min-micro-par2-min-complete-calls-label/v1"

CONFIGS = [
    ("blind_fw", "sym_fw()"),
    ("ms_exact", "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false)"),
    ("ms_cap8", "sym_fw_ms(max_states=10000,value_cap=8,align_merge_order=false)"),
    ("ms_cap16", "sym_fw_ms(max_states=10000,value_cap=16,align_merge_order=false)"),
    (
        "ms_exact_prune",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false,prune_only=true)",
    ),
    (
        "ms_exact_w4",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false,batch_f_window=4)",
    ),
    (
        "ms_exact_w16",
        "sym_fw_ms(max_states=10000,value_cap=-1,align_merge_order=false,batch_f_window=16)",
    ),
    (
        "ms_cap8_w4",
        "sym_fw_ms(max_states=10000,value_cap=8,align_merge_order=false,batch_f_window=4)",
    ),
    (
        "ms_cap8_w16",
        "sym_fw_ms(max_states=10000,value_cap=8,align_merge_order=false,batch_f_window=16)",
    ),
    (
        "ms_cap16_w4",
        "sym_fw_ms(max_states=10000,value_cap=16,align_merge_order=false,batch_f_window=4)",
    ),
    (
        "ms_cap16_w16",
        "sym_fw_ms(max_states=10000,value_cap=16,align_merge_order=false,batch_f_window=16)",
    ),
    (
        "pdb_bdd_b100k",
        "sym_fw_pdb(budget=100000,goal_directed=false)",
    ),
    (
        "pdb_goal_b100k",
        "sym_fw_pdb(budget=100000,goal_directed=true)",
    ),
    (
        "pdb_goal_w4",
        "sym_fw_pdb(budget=100000,goal_directed=true,batch_f_window=4)",
    ),
    (
        "pdb_goal_w16",
        "sym_fw_pdb(budget=100000,goal_directed=true,batch_f_window=16)",
    ),
    (
        "pot_rect_m8",
        "sym_fw_pot(m=8,all_states_objective=false,lpsolver=cplex)",
    ),
    (
        "pot_rect_m8_w4",
        "sym_fw_pot(m=8,all_states_objective=false,lpsolver=cplex,batch_f_window=4)",
    ),
    (
        "pot_rect_m8_w16",
        "sym_fw_pot(m=8,all_states_objective=false,lpsolver=cplex,batch_f_window=16)",
    ),
    (
        "pot_rect_m16",
        "sym_fw_pot(m=16,all_states_objective=false,lpsolver=cplex)",
    ),
    (
        "pot_rect_m16_w4",
        "sym_fw_pot(m=16,all_states_objective=false,lpsolver=cplex,batch_f_window=4)",
    ),
    (
        "pot_rect_m16_w16",
        "sym_fw_pot(m=16,all_states_objective=false,lpsolver=cplex,batch_f_window=16)",
    ),
]


def validate_task_sources(tasks):
    """Resolve and byte-attest the exact 50-task screening manifest."""
    resolved = suites.build_suite(str(C.BENCHMARKS), tasks)
    by_description = {
        "{}:{}".format(task.domain, task.problem): task for task in resolved}
    if len(resolved) != len(tasks) or len(by_description) != len(tasks):
        raise RuntimeError(
            "{} screening descriptions resolved to {} tasks ({} unique)".format(
                len(tasks), len(resolved), len(by_description)))
    ordered = []
    for description in tasks:
        try:
            ordered.append(by_description[description])
        except KeyError as err:
            raise RuntimeError(
                "screening task did not resolve: {}".format(description)) from err
    task_sources_sha256 = suite_cost_manifest.validate_task_sources(
        ((task.domain, task.problem, Path(task.domain_file),
          Path(task.problem_file)) for task in ordered),
        C.BENCHMARKS)
    source_manifest_sha256 = suite_cost_manifest.sha256_file(
        suite_cost_manifest.MANIFEST_PATH)
    return task_sources_sha256, source_manifest_sha256


def main():
    C.reject_unsafe_combined_steps()
    C.require_frozen_revision_cache(FROZEN_REVISION)
    option_payload = [
        {"label": label, "search": search} for label, search in CONFIGS]
    option_digest = hashlib.sha256(json.dumps(
        option_payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True).encode("utf-8")).hexdigest()
    if option_digest != OPTION_MATRIX_DIGEST:
        raise RuntimeError("frozen 21-option matrix changed")
    tasks = read_manifest()
    payload = "".join("{}\n".format(task) for task in tasks)
    if hashlib.sha256(payload.encode("utf-8")).hexdigest() != PILOT_DIGEST:
        raise RuntimeError("pilot manifest digest changed")
    assert len(CONFIGS) * len(tasks) == 1050

    # Keep the read-only Lab help path usable before the generated cost
    # manifest is installed. Every real step fails closed on the frozen
    # manifest and the actual domain/problem bytes used by the 50 tasks.
    help_only = any(arg in {"-h", "--help"} for arg in sys.argv[1:])
    task_sources_sha256 = None
    source_manifest_sha256 = None
    if not help_only:
        task_sources_sha256, source_manifest_sha256 = validate_task_sources(
            tasks)

    # Freeze both the code and per-run resource envelope independently of the
    # defaults used by full-suite experiments.
    C.REV = FROZEN_REVISION
    C.TIME_LIMIT = "300s"
    C.MEMORY_LIMIT = "8G"

    exp = C.new_experiment()
    C.set_protocol_run_properties(exp, {
        "protocol": "heuristic-choices-screen-v1",
        "task_manifest_sha256": PILOT_DIGEST,
        "declared_run_count": 1050,
        "option_matrix_sha256": OPTION_MATRIX_DIGEST,
        "selection_rule": SELECTION_RULE,
        "source_manifest_sha256": source_manifest_sha256,
        "task_sources_sha256": task_sources_sha256,
    })
    C.add_suite(exp, tasks)
    for label, search in CONFIGS:
        C.add_algorithm(exp, label, search)
    C.add_standard_steps(exp, C.ATTRIBUTES + [
        "protocol", "task_manifest_sha256", "declared_run_count",
        "option_matrix_sha256", "selection_rule",
        "source_manifest_sha256", "task_sources_sha256",
    ])
    exp.run_steps()


if __name__ == "__main__":
    main()
