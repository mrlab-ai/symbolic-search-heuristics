# Protocol: do heuristics pay off in symbolic search given a plan-cost bound?

Status: **draft, fixed before the development pilot.**  The configurations,
the analysis and the decision rule are fixed before any run of this study.
Section 8 will record the pilot; the document will then be frozen and pinned
in `bounded_search_protocol.py` before Stage 2.  The pilot selects nothing.

## 1. Motivation and claims

A post-hoc oracle analysis of the harm-generality pairs showed that a search
that knew C*, pruned states with f >= C* + 1 and kept each layer as one BDD
would expand fewer BDD nodes than blind search on 1,580 of 2,138 pairs,
compared with 946 for BDDA*.  The unsplit-bound study
(`unsplit_bound_protocol.md`) found that finding the bound by iterative
deepening costs more than the fragmentation it avoids.  The paper therefore
argues that cheap and accurate plan-cost bounds are the missing ingredient.
This study tests that claim with bounds from a fast satisficing planner:

* **bounded search**: Fast Downward's `iterated` search first runs
  LAMA-first (lazy greedy best-first search with the FF and landmark-sum
  heuristics and preferred operators, unit costs, at most 30 seconds).  If
  it finds a plan of cost U, the second phase runs forward symbolic search
  with the bound U passed on (`pass_bound=true`): it keeps every layer as one
  BDD and discards states with g + h >= U (`prune_only=true`), so it either
  finds an optimal plan cheaper than U or proves that the plan of cost U is
  optimal.  If LAMA-first finds no plan, the second phase runs without a
  bound.  The returned plan is optimal whenever the second phase completes.

## 2. Quantities

A run of a bounded configuration solves its task if the planner exits with
code 0 and reports a best plan cost, so that the second phase completed; its
cost is the last "Best solution cost so far" in the log.  For all other
configurations, coverage is Lab's coverage attribute.  Time is the planner's
total process time, including the first phase; an unsolved run counts as 600
seconds in PAR2.  Effort is the number of inner BDD nodes of all completed
expansions in the `wbh_log` of the symbolic search (the `effort` of its done
event for the configurations without a first phase).

## 3. Configurations

All runs use the planner revision `61c127017e9404aeb8b0a9338f3edea0ac75fd75`
(`release` build with CPLEX 22.11, cached in
`symk-bounded-revision-cache`), the Gamer variable order, 300 seconds,
8,192 MiB, and `wbh_log="wbh.jsonl"` in every symbolic search.  LAMA is

    let(hlm,landmark_sum(lm_factory=lm_reasonable_orders_hps(lm_rhw()),
        transform=adapt_costs(one),pref=false),
    let(hff,ff(transform=adapt_costs(one)),
    lazy_greedy([hff,hlm],preferred=[hff,hlm],cost_type=one,
                reopen_closed=false,max_time=30)))

and a bounded configuration with symbolic search X is
`iterated([LAMA,X],pass_bound=true,repeat_last=false,continue_on_fail=true,continue_on_solve=true)`.

| Label | Search |
|---|---|
| `blind_fw` | `sym_fw()` |
| `blind_bd` | `sym_bd()` |
| `blind_bounded` | bounded with `sym_fw()` |
| `ms_plain` | `sym_fw_ms(max_states=10000,align_merge_order=false,build_time_limit=infinity)` |
| `ms_bounded` | bounded with `ms_plain` plus `prune_only=true` |
| `pdb_plain` | `sym_fw_pdb(budget=1000000,pattern_selection=cegar,cegar_max_time=10,cegar_seed=2011)` |
| `pdb_bounded` | bounded with `pdb_plain` plus `prune_only=true` |
| `pot_plain` | `sym_fw_pot(m=4)` |
| `pot_bounded` | bounded with `pot_plain` plus `prune_only=true` |

The heuristics are those of the fragmentation-remedy study.  The 30-second
cap and LAMA-first were fixed a priori and are not tuned.

## 4. Development pilot

Cohort: the 275-task, 46-domain development cohort
(`fragmentation_remedy_dev_cohort.txt`, SHA-256
`5c43a5d0891d32285c248c14cfe81ab5fa308b8eeb3d3d34e7d22ee782fcda2e`); the
holdout is never used before Stage 2.  All nine configurations run once.
The pilot checks that every configuration runs, that bounded runs solve with
exit code 0, and that solution costs agree across configurations.  It
selects nothing and changes no configuration; a failed check would be
reported and fixed in the code, followed by a new pilot.

## 5. Stage 2: the holdout

Cohort: the sealed 1,052-task, 45-domain holdout
(`pdb_profile_harm_generality_cohort.txt`, manifest digest
`e9ffcc16c2e73e4c92c0ccbb71c60203ba643f5ed76bf943f731e86e11169694`).
Nine configurations, 9,468 cells.

### Primary tests

For each family F:

* H1: `F_bounded` versus `F_plain`;
* H2: `F_bounded` versus `blind_fw`;
* H3: `F_bounded` versus `blind_bounded`.

Each test counts the tasks that exactly one of the two configurations solves
(gains g of the first, losses l) and applies an exact two-sided binomial
test with p = 1/2 to g out of g + l (p = 1 if g + l = 0).  The nine p-values
are adjusted by Holm's method at family-wise alpha = 0.05.  A comparison is
better (worse) only if it is significant after adjustment and g > l
(l > g); otherwise the paper says that the difference is not significant.
A failed claim triggers no new configuration or subset.

### Secondary, descriptive

* Coverage per configuration and PAR2.
* `F_bounded` and `blind_bounded` versus `blind_bd` (gains, losses, exact
  two-sided p-values, unadjusted and labeled descriptive).
* On tasks solved by `F_plain`, `F_bounded` and `blind_fw`: medians of
  effort(config) / effort(`blind_fw`) and time(config) / time(`blind_fw`).
* For bounded runs: the number of tasks on which the first phase found a
  plan, and among the solved ones, how often its cost was optimal and the
  median ratio of its cost to the optimal cost.

## 6. Execution

Pilot: `symk-bounded-dev/run_cells.py`, 7 cells per Slurm array task, the
pinned binary verified before each run, Slurm account
`naiss2026-3-660-cpu`, `fat` partition, one CPU and 9 GiB per task.

Stage 2: `exp_bounded_search.py`, the shared certificate-holdout runner
configured as in the fragmentation-remedy study (Lab 8.0, Python 3.9.25,
`requirements.txt` pins), with 10 runs per array task, 947 unthrottled array
tasks, and 70 minutes per array task.  Failed cells are recovered only by
rerunning their exact array index for scheduler failures.  Worst-case
compute is about 9,468 x 300 s, roughly 790 CPU hours.

## 7. Analysis

`analyze_bounded_search.py`, frozen with this document before Stage 2.
Solution costs of runs that solve the same task must agree; if they do not,
the task is reported and counts as unsolved for every configuration.

## 8. Development pilot results

To be added after the pilot.
