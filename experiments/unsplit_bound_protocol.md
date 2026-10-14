# Protocol: does unsplit f-bounded search recover the pruning of heuristics?

Status: **draft, fixed before Stage 1.**  Section 4 (Stage 1) is fixed
before any Stage 1 run; its SHA-256 is recorded with the Stage 1 inputs.
Stage 1 results and the selected schedules will be added in Section 8, and
the document will then be frozen and pinned in `unsplit_bound_protocol.py`
before Stage 2.

## 1. Motivation and claims

The harm-generality study found that harmful heuristics barely prune and
fragment the layers of forward product-at-evaluation symbolic A* (BDDA*).
A post-hoc oracle analysis of its pairs
(`analyze_harm_pruning_posthoc.py`) showed that a search that knew the
optimal plan cost C*, pruned states with f > C* and kept each layer as one
BDD would expand fewer BDD nodes than blind search on 1,580 of 2,138 pairs,
compared with 946 for BDDA*.  Forward search does not know C*.  This study
asks whether a practical search that prunes without fragmenting obtains part
of this gain:

* **unsplit f-bounded search** (`unsplit_bound=true`): iterative deepening on
  an f-bound B starting at h(s0).  An iteration expands the layers by
  increasing g, each layer as one BDD, and discards successors with
  g + h > B.  If it finds no plan, it restarts from s0 with a larger bound:
  the smallest f-value of a discarded state (schedule `next`) or, with
  `unsplit_bound_doubling=true`, at least the old bound plus a step that
  starts at 1 and doubles in every iteration (schedule `double`).  The first
  plan found is optimal for every bound B >= C*.  With `next`, the last
  iteration has B = C* and expands exactly the unsplit sets of BDDA*.

## 2. Quantities

Coverage is Lab's coverage attribute.  Time is the planner's total process
time; an unsolved run counts as 600 seconds in PAR2.  Effort is the
`effort` of the `wbh_log` done event: the inner BDD nodes of all expanded
sets, summed over all iterations for unsplit search.  The planner log
reports the number of iterations, the final bound, and the nodes expanded
in the last iteration.

## 3. Configurations

All runs use the planner revision `4a719d8b3da3b606f4f246a61c2189859a5c825e`
(`release` build with CPLEX 22.11, cached in
`symk-unsplit-revision-cache`), the Gamer variable order, 300 seconds,
8,192 MiB, and `wbh_log="wbh.jsonl"` appended to every search string.  The
heuristics are those of the fragmentation-remedy study:

| Family | Base search |
|---|---|
| `ms` | `sym_fw_ms(max_states=10000,align_merge_order=false,build_time_limit=infinity)` |
| `pdb` | `sym_fw_pdb(budget=1000000,pattern_selection=cegar,cegar_max_time=10,cegar_seed=2011)` |
| `pot` | `sym_fw_pot(m=4)` |

Per family F: `F_plain` (BDDA*), `F_next` (base options plus
`unsplit_bound=true`), and `F_double` (base options plus
`unsplit_bound=true,unsplit_bound_doubling=true`).  Controls: `blind_fw`
(`sym_fw()`) and, in Stage 2 only, `blind_bd` (`sym_bd()`).

## 4. Stage 1: schedule selection on the development cohort

Cohort: the 275-task, 46-domain development cohort
(`fragmentation_remedy_dev_cohort.txt`, SHA-256
`5c43a5d0891d32285c248c14cfe81ab5fa308b8eeb3d3d34e7d22ee782fcda2e`).  The
holdout is never used in Stage 1.

Configurations: `blind_fw` and, for each family, `F_plain`, `F_next` and
`F_double`: 10 configurations, 2,750 runs.

Selection rule, per family: the schedule (`next` or `double`) with the
higher coverage; ties by lower PAR2 summed over the cohort; remaining ties
select `next`.  One schedule is selected per family even if it is worse than
the plain heuristic.  Stage 1 also checks that every configuration runs and
that solution costs agree across configurations.  No other Stage 1 outcome
changes Stage 2.

## 5. Stage 2: the holdout

Cohort: the sealed 1,052-task, 45-domain holdout
(`pdb_profile_harm_generality_cohort.txt`, manifest digest
`e9ffcc16c2e73e4c92c0ccbb71c60203ba643f5ed76bf943f731e86e11169694`).
Eight configurations: `blind_fw`, `blind_bd`, and for each family `F_plain`
and `F_unsplit` (the schedule selected in Stage 1); 8,416 cells.

### Primary tests

For each family F:

* H1: `F_unsplit` versus `F_plain`;
* H2: `F_unsplit` versus `blind_fw`.

Each test counts the tasks that exactly one of the two configurations solves
(gains g of the first, losses l) and applies an exact two-sided binomial
test with p = 1/2 to g out of g + l (p = 1 if g + l = 0).  The six p-values
are adjusted by Holm's method at family-wise alpha = 0.05.

Claims:

1. Unsplit search improves on BDDA* with F only if H1 is significant after
   adjustment and g > l; it is worse only if H1 is significant and l > g.
2. Unsplit search beats blind forward search with F only if H2 is
   significant after adjustment and g > l; it loses to it only if H2 is
   significant and l > g.
3. Otherwise the paper says that the difference is not significant.
4. A failed claim triggers no new configuration, schedule, or subset.

### Secondary, descriptive

* Coverage per configuration and PAR2.
* `F_unsplit` versus `blind_bd` (gains, losses, exact two-sided p-values,
  unadjusted and labeled descriptive).
* On tasks solved by `F_plain`, `F_unsplit` and `blind_fw`: medians of
  effort(config) / effort(`blind_fw`) and time(config) / time(`blind_fw`)
  for `F_plain` and `F_unsplit`.
* For solved `F_unsplit` runs: medians of the number of iterations, of the
  share of the effort spent in the last iteration, and of the final bound
  minus the plan cost.

## 6. Execution

Stage 1: `symk-unsplit-dev/run_cells.py`, 7 cells per Slurm array task,
the pinned binary verified before each run, Slurm account
`naiss2026-3-660-cpu`, `fat` partition, one CPU and 9 GiB per task.

Stage 2: `exp_unsplit_bound.py`, the shared certificate-holdout runner
configured as in the fragmentation-remedy study (Lab 8.0, Python 3.9.25,
`requirements.txt` pins), with 9 runs per array task, 936 unthrottled array
tasks, and 60 minutes per array task.  Failed cells are recovered only by
rerunning their exact array index for scheduler failures.  Worst-case
compute is about 8,416 x 300 s, roughly 700 CPU hours.

## 7. Analysis

`analyze_unsplit_bound.py`, frozen with this document before Stage 2.
Solution costs of runs that solve the same task must agree; if they do not,
the task is reported and counts as unsolved for every configuration.

## 8. Stage 1 results

To be added after Stage 1.
