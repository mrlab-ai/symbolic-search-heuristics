# Protocol: does the potential objective explain why operator potentials pay off?

Status: **frozen on 2026-10-15 by author decision, before launch.**  The
configuration with initial-state operator potentials has not been run on the
holdout.  Its SHA-256 is pinned in `analyze_cpddl_objective_study.py`.

## 1. Motivation

The CPDDL GHSETA* study (`cpddl_ghseta_protocol.md`) found that forward
GHSETA* with operator potentials for the A+I objective (the average state,
with the value of the initial state kept maximal) solves significantly more
holdout tasks than blind forward search, because the potentials remove most
states on many tasks.  A review noted that this study differs from the SymK
studies in planner, search algorithm, heuristic and objective at once.  This
study changes only the objective: CPDDL with operator potentials optimized
for the initial state (I), the objective of the capped potentials in SymK.

Question: does forward GHSETA* with I potentials solve more tasks than blind
forward search, and does the decomposition look like that of A+I potentials
or like that of the SymK potentials?

## 2. Quantities

As in Section 2 of `cpddl_ghseta_protocol.md`.

## 3. Configurations

The CPDDL binary of the GHSETA* study (revision
`fea354d6c0b880aa8afbd74781e4f01b510fa997`, `cpddl-cache/fea354d6c0b880aa`,
`bin/pddl-symba` with SHA-256
`dee50c341ee7959c070a3eeaa7b2f29f5c9ab8a558777d71cff8edd7babc22fb`), the
runner `cpddl_ghseta_run_cells.py`, `--fdr-tnfm`, 300 seconds of CPU time and
8 GiB of address space.

| Label | Options |
|---|---|
| `cp_blind_fw` | `--symba fw` |
| `cp_pot_fw` | `--symba fw --symba-fw-pot --symba-fw-pot-cfg I` |
| `cp_blind_fw_prof` | `cp_blind_fw` with `PDDL_WBH_LOG=wbh.jsonl` |
| `cp_pot_fw_prof` | `cp_pot_fw` with `PDDL_WBH_LOG=wbh.jsonl` |

Blind search is rerun so that every comparison stays within one launch.

## 4. Cohort and execution

The sealed 1,052-task, 45-domain holdout; 4 configurations x 1,052 tasks =
4,208 cells in `symk-cpddl/holdout-objective-I`, 7 cells per Slurm array task
(602 array tasks, 60 minutes each), Slurm account `naiss2026-3-660-cpu`,
`fat` partition.  Prerequisite (2026-10-15): the I configuration solved
driverlog p06 and gripper prob05 of the development cohort with the optimal
costs and complete layer logs.

## 5. Analysis

`analyze_cpddl_objective_study.py`, which applies the functions of
`analyze_cpddl_ghseta_study.py` to these four configurations.

* Primary test (H-I): `cp_pot_fw` versus `cp_blind_fw`, exact two-sided sign
  test on the tasks that exactly one configuration solves, alpha = 0.05.
  Better (worse) only if significant and g > l (l > g).
* Descriptive: coverage and PAR2, and the decomposition quantities of
  Section 5 of `cpddl_ghseta_protocol.md` on the profiled pairs, compared
  with those of A+I potentials.
