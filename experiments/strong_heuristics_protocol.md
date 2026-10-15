# Protocol: does the harm diagnosis hold for strong heuristics in SymK?

Status: **frozen on 2026-10-15 by author decision, before launch.**  Neither
heuristic configuration below has been run on the holdout.  Its SHA-256 is
pinned in `strong_heuristics_protocol.py`, together with the option matrix,
the cohort manifest, the planner revision and the binary hashes.

## 1. Motivation and claim

A review of the paper argued that the heuristics of the harm-generality
study are weak by design (potentials with weights capped at 4 and optimized
for the initial state, M&S with at most 50,000 states) and asked whether the
diagnosis holds for strong configurations.  This study measures the
decomposition of the harm-generality study prospectively for two stronger
configurations:

* potentials optimized for the average over all states with integer weights
  in [-1000, 1000] (`pot_all_m1000`), which on development tasks solved
  tasks that the capped potentials could not;
* M&S with 200,000 abstract states and the unaligned merge order
  (`ms_unaligned_200k`), four times the largest M&S of the family study.

> The family-study diagnosis holds for each of the two heuristics: on harmful
> pairs the excess is carried by fragmentation rather than by the unsplit
> effort.

## 2. Quantities

As in Section 2 of the harm-generality protocol: for a task with both runs
solved and certified profiles, r = effort(h) / effort(blind), u =
unionEffort(h) / effort(blind), frag = effort(h) / unionEffort(h), and the
state ratio s = expanded states(h) / expanded states(blind).

## 3. Configurations

The pinned planner binary of the harm-generality study (revision
`580a6ee3b39489cb0a3f1d4e187b52601b751eab`, `release` build with CPLEX
22.11), forward product-at-evaluation symbolic A*, the Gamer variable order,
300 seconds and 8,192 MiB, with
`wbh_log="wbh.jsonl",wbh_profile_log="wbh-profile.jsonl"` appended:

| Label | Search |
|---|---|
| `blind_fw_profiled` | `sym_fw()` |
| `pot_all_m1000` | `sym_fw_pot(m=1000,all_states_objective=true)` |
| `ms_unaligned_200k` | `sym_fw_ms(max_states=200000,align_merge_order=false,build_time_limit=infinity)` |

`blind_fw_profiled` repeats the blind configuration of the harm-generality
study so that both runs of a pair come from the same launch.

## 4. Cohort

The sealed 1,052-task, 45-domain holdout
(`pdb_profile_harm_generality_cohort.txt`, manifest digest
`e9ffcc16c2e73e4c92c0ccbb71c60203ba643f5ed76bf943f731e86e11169694`).
3 configurations x 1,052 tasks = 3,156 cells.

## 5. Analysis plan

The analysis is `analyze_strong_heuristics.py`, frozen with this document.
Pair eligibility, the estimand S = sum(ln frag) / sum(ln r) over harmful
pairs (r > 1), the timing rule, and the thresholds are those of Section 5 of
the harm-generality protocol, applied separately to the pairs of each
heuristic with the frozen functions of
`analyze_pdb_profile_harm_generality.py`.

Decision rule, per heuristic:

1. Support: at least 100 harmful pairs from at least 20 domains.
2. The paper may say that the diagnosis holds for the heuristic only if rule
   1 holds, S >= 0.9, and, if there are at least 20 pairs with r > 2, at
   least 95% of them have frag > u.
3. A failed rule is reported as such and triggers no new threshold, subset,
   or configuration.

As the paper notes, rule 2 mainly rules out that harmful heuristics enlarge
the expanded parts of the layers.  The substantive quantities are
descriptive: numbers of harmful and helpful pairs; medians of u, frag and s
among harmful and helpful pairs; pairs with u > s; harmful pairs with u > 1;
pairs with s < 0.1 and s >= 0.8 and how many of them are helpful; coverage.

## 6. Prerequisites (completed before freezing)

Smoke test (2026-10-15, driverlog p06, logistics00 probLOGISTICS-7-1 and
gripper prob05 from the development cohort, cached binary, 180 seconds):
both configurations solved all three tasks with the optimal plan costs (11,
44, 35) and complete profiles with positive unsplit effort.

## 7. Execution

`exp_strong_heuristics.py`, the shared certificate-holdout runner configured
as in the harm-generality study (Lab 8.0, Python 3.9.25, `requirements.txt`
pins, Slurm account `naiss2026-3-660-cpu`, `fat` partition, one CPU and
9 GiB per Slurm task), with 4 runs per array task, 789 unthrottled array
tasks, and 40 minutes per array task.  Failed cells are recovered only by
rerunning their exact array index for scheduler failures.  Worst-case
compute is about 3,156 x 300 s, roughly 265 CPU hours.
