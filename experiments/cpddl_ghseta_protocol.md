# Protocol: pruning and fragmentation in GHSETA* with operator potentials

Status: **draft, fixed before the development pilot.**  The configurations,
the analysis and the decision rule are fixed before any run of this study.
Section 8 will record the pilot; the document will then be frozen and its
SHA-256 pinned in `analyze_cpddl_ghseta_study.py` before Stage 2.  The pilot
selects nothing.

## 1. Motivation and claims

Reviews of the paper asked whether the diagnosis of the harm-generality study
(harmful heuristics barely prune and fragment the layers) carries over to the
setting in which heuristics are reported to help symbolic search: GHSETA*
with operator-potential heuristics (Fišer, Torralba, and Hoffmann, AAAI 2022
and AIJ 2024), forward and bidirectional.  This study runs the CPDDL planner
of those papers on the holdout and decomposes its forward effort.

Questions:

* Q-A: Do operator potentials make forward GHSETA* solve more tasks than
  blind forward search of the same planner?
* Q-B: Do operator potentials in the forward direction make bidirectional
  search solve more tasks than blind bidirectional search of the same
  planner?
* Q-C (descriptive): For forward GHSETA* with potentials versus blind
  forward search, how do the unsplit ratio u, the fragmentation factor and
  the state ratio s behave on harmful and helpful pairs?

## 2. Quantities

A run solves its task if `pddl-symba` exits with code 0 and logs a plan cost
("Plan Cost: C").  Time is the wall-clock time of the run; an unsolved run
counts as 600 seconds in PAR2.  For profiled runs, the log written through
`PDDL_WBH_LOG` gives, for the forward search, the BDD size (CUDD's
`Cudd_DagSize`, which counts the terminal) of every expanded set and, after the search, of the
union of the expanded sets per g-value.  For a pair of a profiled heuristic
run and the profiled blind run of the same task, both solved with the same
cost, let E and U be the summed sizes of the expanded sets and of the
unions: r = E(h) / E(blind), u = U(h) / U(blind), and frag = r / u, the
fragmentation factor relative to blind search (blind search of CPDDL may
itself expand several sets per layer).  The state ratio s is the summed
model count of the expanded sets of h over that of blind search.

## 3. Configurations

The CPDDL tree vendored in `baselines/cpddl` at revision
`fea354d6c0b880aa8afbd74781e4f01b510fa997` (upstream 2c7de0ec with the
restored CUDD header and the opt-in expansion log), built with bundled CUDD
and CPLEX 22.11 in `cpddl-cache/fea354d6c0b880aa`; binary
`bin/pddl-symba`, SHA-256
`dee50c341ee7959c070a3eeaa7b2f29f5c9ab8a558777d71cff8edd7babc22fb`.  Every
run uses `--fdr-tnfm`, 300 seconds of CPU time and 8 GiB of address space.

| Label | Options |
|---|---|
| `cp_blind_fw` | `--symba fw` |
| `cp_pot_fw` | `--symba fw --symba-fw-pot --symba-fw-pot-cfg A+I` |
| `cp_blind_bi` | `--symba bi` |
| `cp_pot_bi` | `--symba bi --symba-fw-pot --symba-fw-pot-cfg A+I` |
| `cp_blind_fw_prof` | `cp_blind_fw` with `PDDL_WBH_LOG=wbh.jsonl` |
| `cp_pot_fw_prof` | `cp_pot_fw` with `PDDL_WBH_LOG=wbh.jsonl` |

`A+I` is the objective of Fišer et al. (average over all states with the
value of the initial state kept maximal), and bidirectional search with
forward `A+I` potentials and blind backward search is the configuration that
the CPDDL documentation recommends.  The profiled runs are separate so that
the logging overhead affects no coverage comparison.

## 4. Development pilot

Cohort: the 275-task, 46-domain development cohort
(`fragmentation_remedy_dev_cohort.txt`, SHA-256
`5c43a5d0891d32285c248c14cfe81ab5fa308b8eeb3d3d34e7d22ee782fcda2e`).  All six
configurations run once (1,650 cells).  The pilot checks that every
configuration runs, that solution costs agree across configurations, and
that profiled runs log complete layers.  It selects nothing.

## 5. Stage 2: the holdout

Cohort: the sealed 1,052-task, 45-domain holdout
(`pdb_profile_harm_generality_cohort.txt`, manifest digest
`e9ffcc16c2e73e4c92c0ccbb71c60203ba643f5ed76bf943f731e86e11169694`).  Six
configurations, 6,312 cells.

### Primary tests

* H-A: `cp_pot_fw` versus `cp_blind_fw`;
* H-B: `cp_pot_bi` versus `cp_blind_bi`.

Each test counts the tasks that exactly one configuration solves (gains g,
losses l) and applies an exact two-sided binomial test with p = 1/2; the two
p-values are adjusted by Holm's method at family-wise alpha = 0.05.  A
comparison is better (worse) only if it is significant and g > l (l > g).
Solution costs of runs that solve the same task must agree; if they do not,
the task counts as unsolved for every configuration.

### Secondary, descriptive

* Coverage and PAR2 per configuration; `cp_pot_bi` versus `cp_pot_fw` and
  `cp_blind_bi` versus `cp_blind_fw` (unadjusted, descriptive).
* Q-C on the eligible profiled pairs: numbers of harmful (r > 1) and helpful
  (r < 1) pairs; medians of u, frag and s among harmful and helpful pairs;
  the share S = sum(ln frag) / sum(ln r) over harmful pairs and the fraction
  of pairs with r > 2 that have frag > u; the number of pairs with s < 0.1
  and s >= 0.8 and how many of them are helpful; the median fragmentation of
  blind search itself (E / U of `cp_blind_fw_prof`).

## 6. Execution

`symk-cpddl/{dev,holdout}/run_cells.py`: 7 cells per Slurm array task, the
pinned binary and every PDDL file verified by SHA-256 before each run, Slurm
account `naiss2026-3-660-cpu`, `fat` partition, one CPU and 9 GiB per task.

## 7. Analysis

`analyze_cpddl_ghseta_study.py`, frozen with this document before Stage 2.

## 8. Development pilot results

To be added after the pilot.
