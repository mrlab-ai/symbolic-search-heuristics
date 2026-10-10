# Protocol: can heuristics be used without fragmenting symbolic search?

Status: **frozen on 2026-10-10 by author decision, after Stage 1 and before
Stage 2.**  Section 4 (Stage 1) was fixed before any Stage 1 run (draft
SHA-256 `08877d3c3313a9f27275933108f9f20341e5ac7be38b4874ca12b5211f8bed3a`,
recorded at submission in `symk-remedy-dev/stage1-inputs.sha256`).  Stage 1
results and the selected windows are in Section 8.  This document, the option
matrix, and the analysis code are pinned in
`fragmentation_remedy_protocol.py`.

## 1. Motivation and claims

The harm-generality study (`pdb_profile_harm_generality_protocol.md`,
analysis SHA-256
`445f8774906b2aa84ee60e00db612d22685756213bd550ef30aa3f38f474bd38`) found
for M&S, CEGAR PDB, and potential heuristics that whenever forward
product-at-evaluation symbolic A* needs more BDD nodes than blind search, the
excess is carried by fragmentation, while harmful runs barely prune.  This
study asks whether using the same heuristics in ways that do not fragment
the frontier recovers their benefit, and places all results next to blind
bidirectional search, the strongest blind symbolic configuration.

Two remedies use one heuristic without splitting the expanded sets by
heuristic value:

* **prune-only** (`prune_only=true`): the heuristic only removes dead ends
  and states outside the upper-bound slice; every expanded set is a whole
  blind layer minus pruned states, so fragmentation is one.
* **gated batching** (`batch_f_window=W,batch_max_union_ratio=1.0`): A*
  order, goal tests, and closing are unchanged, but fresh buckets with the
  same g and f within W of the selected bucket are imaged as one BDD,
  provided that the union has at most as many inner nodes as its parts.

A third remedy, bidirectional search with M&S pruning that is built only
after the first solution (`sym_bd_ms`), is the only heuristic use in the
bidirectional architecture that the planner offers; it is descriptive.

## 2. Quantities

Coverage is Lab's coverage attribute.  Time is the planner's total process
time (including heuristic construction); an unsolved run counts as 600
seconds in PAR2.  Effort is the `effort` of the `wbh_log` done event (inner
BDD nodes of all expanded pieces).  No profile log is written, so times
carry no profiling overhead.

## 3. Configurations

All runs use planner revision `580a6ee3b39489cb0a3f1d4e187b52601b751eab`
(the binary pinned for the harm-generality study, `release` build with
CPLEX 22.11), the Gamer variable order, 300 seconds, 8,192 MiB, and
`wbh_log="wbh.jsonl"` appended to every search string.

| Label | Search |
|---|---|
| `blind_fw` | `sym_fw()` |
| `blind_bd` | `sym_bd()` |
| `bd_ms_prune` | `sym_bd_ms(max_states=10000)` |
| `ms_plain` | `sym_fw_ms(max_states=10000,align_merge_order=false,build_time_limit=infinity)` |
| `ms_prune` | `ms_plain` options plus `prune_only=true` |
| `ms_batch` | `ms_plain` options plus `batch_f_window=W_ms,batch_max_union_ratio=1.0` |
| `pdb_plain` | `sym_fw_pdb(budget=1000000,pattern_selection=cegar,cegar_max_time=10,cegar_seed=2011)` |
| `pdb_prune` | `pdb_plain` options plus `prune_only=true` |
| `pdb_batch` | `pdb_plain` options plus `batch_f_window=W_pdb,batch_max_union_ratio=1.0` |
| `pot_plain` | `sym_fw_pot(m=4)` |
| `pot_prune` | `pot_plain` options plus `prune_only=true` |
| `pot_batch` | `pot_plain` options plus `batch_f_window=W_pot,batch_max_union_ratio=1.0` |
| `pot_all_plain` | `sym_fw_pot(m=4,all_states_objective=true)` |

The plain heuristic configurations are those of the harm-generality study
(M&S: the unaligned 10k configuration, which had the highest coverage of the
three).  `pot_all_plain` optimizes the potentials for the average over all
states instead of the initial state; prior work on operator potentials
(Fišer, Torralba, and Hoffmann, AIJ 2024) reports its largest gains for an
objective of this kind.  It is descriptive and was added to Stage 2 after
Stage 1 had started, before any Stage 1 outcome was inspected; its smoke test
is recorded in Section 8.

## 4. Stage 1: window selection on the development cohort

Cohort: the 275-task, 46-domain development cohort
(`fragmentation_remedy_dev_cohort.txt`, recovered from the joint-pilot
properties; its bytes hash to the frozen development manifest digest
`5c43a5d0891d32285c248c14cfe81ab5fa308b8eeb3d3d34e7d22ee782fcda2e`).  The
holdout is never used in Stage 1.

Configurations: all twelve of Section 3, with `*_batch` replaced by three
variants per family, W in {1, 8, infinity}: 18 configurations, 4,950 runs.

Selection rule, per family: the W with the highest coverage; ties by lower
PAR2 summed over the cohort; remaining ties by the smaller W.  One batching
variant is selected per family even if it is worse than the plain
heuristic.  Stage 1 also checks that every configuration runs and that
solution costs agree across configurations.  No other Stage 1 outcome
changes Stage 2.

## 5. Stage 2: the holdout

Cohort: the sealed 1,052-task, 45-domain holdout
(`pdb_profile_harm_generality_cohort.txt`, manifest digest
`e9ffcc16c2e73e4c92c0ccbb71c60203ba643f5ed76bf943f731e86e11169694`).
Thirteen configurations, 13,676 cells.

### Primary tests

For each family F in {ms, pdb, pot} and remedy R in {prune, batch}:

* H1: `F_R` versus `F_plain`;
* H2: `F_R` versus `blind_fw`.

Each test counts the tasks that exactly one of the two configurations solves
(gains g of the first, losses l) and applies an exact two-sided binomial
test with p = 1/2 to g out of g + l (p = 1 if g + l = 0).  The twelve
p-values are adjusted by Holm's method at family-wise alpha = 0.05.

Claims:

1. R improves on the plain heuristic of F only if H1 is significant after
   adjustment and g > l.
2. R beats blind forward search with F only if H2 is significant after
   adjustment and g > l; R loses to it only if H2 is significant and l > g.
3. Otherwise the paper says that the difference is not significant.
4. A failed claim triggers no new configuration, window, or subset.

### Secondary, descriptive

* Coverage per configuration, overall and averaged equally over domains,
  and PAR2.
* `pot_all_plain` versus `blind_fw` and versus `pot_plain` (gains, losses,
  exact two-sided p-values, unadjusted and labeled descriptive), and its
  effort ratio to `blind_fw` on jointly solved tasks.
* Bidirectional context: `blind_bd` and `bd_ms_prune` versus `blind_fw`, and
  `bd_ms_prune` versus `blind_bd` (gains, losses, exact two-sided p-values,
  unadjusted and labeled descriptive), and coverage of a per-task oracle over
  `blind_bd` and each other configuration minus `blind_bd` coverage.
* Mechanism: on tasks solved by `F_plain`, `F_R`, and `blind_fw`, medians of
  effort(config) / effort(`blind_fw`) and time(config) / time(`blind_fw`)
  for plain and both remedies.
* Effort versus time: over pairs (`F_plain`, `blind_fw`) solved by both
  whose blind time is at least 1 second, the Spearman rank correlation of
  ln(effort ratio) and ln(time ratio), and the fraction of pairs whose
  effort ratio and time ratio lie on the same side of one; per family and
  pooled.

## 6. Execution

The shared certificate-holdout runner, configured as in the harm-generality
study (Lab 8.0, Python 3.9.25, `requirements.txt` pins, Slurm account
`naiss2026-3-660-cpu`, `fat` partition, one CPU and 9 GiB per Slurm task),
with 14 runs per array task (Lab's limit of 1,000 array tasks), 977 array
tasks, and 80 minutes per array task.  Failed cells are recovered only by rerunning their exact array index
for scheduler failures.  Worst-case compute is about 13,676 x 300 s, roughly
1,140 CPU hours.

## 7. Analysis

`analyze_fragmentation_remedy.py`, frozen with this document.  Solution
costs of runs that solve the same task must agree; if they do not, the task
is reported and counts as unsolved for every configuration.

## 8. Stage 1 results

Slurm job 3636794 (708 array tasks, all `COMPLETED`), revision-cache binary
`builds/release/bin/downward` with the pinned SHA-256
`3e787375cedb75738fb9bf20c95fad5616b4416850d8aa911dcfcfb6a6055b2e`.  All
4,950 cells produced a record; no solution costs disagree.  Unsolved cells
are timeouts, translator out-of-memory or out-of-time failures on
organic-synthesis (exit 20, 21, and SIGKILL after the 300-second translate
limit), and the two unsolvable mystery tasks (exit 11 or 12).  Summary:
`experiments/artifacts/fragmentation-remedy/stage1-v1.json` (SHA-256
`f87d29d86fd57fafa7066819ae23e1c64318c5de852fd950636fd800c6869228`), written
by `experiments/select_fragmentation_remedy_windows.py`.

Coverage on the 275 development tasks (PAR2 sums in parentheses):

| Configuration | Solved |
|---|---|
| `blind_fw` | 114 (99,072) |
| `blind_bd` | 130 (89,462) |
| `bd_ms_prune` | 131 (89,663) |
| `ms_plain` / `ms_prune` | 119 / 113 |
| `ms_batch` W = 1 / 8 / infinity | 119 / 107 / 106 |
| `pdb_plain` / `pdb_prune` | 115 / 113 |
| `pdb_batch` W = 1 / 8 / infinity | 114 / 111 / 107 |
| `pot_plain` / `pot_prune` | 110 / 114 |
| `pot_batch` W = 1 / 8 / infinity | 108 / 105 / 106 |

Selected windows by the rule of Section 4: W = 1 for M&S, PDB, and
potentials.

`pot_all_plain` smoke test (gripper prob03, same binary): exit code 0,
plan cost 23, equal to every other configuration.
