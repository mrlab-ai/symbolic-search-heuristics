# Protocol: does the harm diagnosis hold for a stronger heuristic?

Status: **frozen on 2026-10-13 by author decision, before launch.**  The
profiled configuration below has not been run on the holdout.  Its SHA-256
is pinned in `pot_all_decomposition_protocol.py`, together with the option
matrix, the cohort manifest, the planner revision, and the binary hashes.

## 1. Motivation and claim

The harm-generality study (`pdb_profile_harm_generality_protocol.md`)
found for M&S, a CEGAR PDB collection, and potentials optimized for the
initial state that harmful heuristics barely shrink the unsplit sets and
fragment the layers.  A review of the paper asked whether this diagnosis
holds for a stronger heuristic.  The fragmentation-remedy study
(`fragmentation_remedy_protocol.md`) ran potentials optimized for the
average over all states (`pot_all_plain`), which solved 465 holdout tasks
versus 457 for blind forward search, but without profiling, so its effort
cannot be decomposed.  A post-hoc comparison of expanded states in that
study (`analyze_fragmentation_remedy_posthoc.py`) found 185 harmful and 198
helpful pairs with median state ratios 0.78 and 0.13.  This study measures
the decomposition prospectively for that heuristic:

> The family-study diagnosis holds for potentials optimized for all states:
> on harmful pairs the excess is carried by fragmentation rather than by the
> unsplit effort.

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
| `pot_all_m4` | `sym_fw_pot(m=4,all_states_objective=true)` |

`blind_fw_profiled` repeats the blind configuration of the harm-generality
study so that both runs of a pair come from the same launch.  `pot_all_m4`
is `pot_all_plain` of the remedy study with profiling.

## 4. Cohort

The sealed 1,052-task, 45-domain holdout
(`pdb_profile_harm_generality_cohort.txt`, manifest digest
`e9ffcc16c2e73e4c92c0ccbb71c60203ba643f5ed76bf943f731e86e11169694`).
2 configurations x 1,052 tasks = 2,104 cells.

## 5. Analysis plan

The analysis is `analyze_pot_all_decomposition.py`, frozen with this
document.  Pair eligibility, the estimand S = sum(ln frag) / sum(ln r) over
harmful pairs (r > 1), the timing rule, and the thresholds are those of
Section 5 of the harm-generality protocol, applied to the single group of
`pot_all_m4` pairs.  The analysis evaluates them with the frozen functions
of `analyze_pdb_profile_harm_generality.py`.

Decision rule:

1. Support: at least 100 harmful pairs from at least 20 domains.
2. The paper may say that the diagnosis holds for potentials optimized for
   all states only if rule 1 holds, S >= 0.9, and, if there are at least 20
   pairs with r > 2, at least 95% of them have frag > u.
3. A failed rule is reported as such and triggers no new threshold, subset,
   or configuration.

Secondary, descriptive: numbers of harmful and helpful pairs; medians of u,
frag, and s among harmful and helpful pairs; harmful pairs with u > 1;
pairs with s < 0.1 and s >= 0.8 and how many of them are helpful (the
thresholds of the post-hoc pruning view of the harm-generality study);
coverage of both configurations.

## 6. Prerequisites (completed before freezing)

1. The binary is the one pinned and cached for the harm-generality study
   (`symk-harm-generality-revision-cache`), and its potential search attaches
   the closed unions to the profile.
2. Smoke test (2026-10-13, gripper prob03, cached `release` binary, outside
   the holdout): exit code 0, plan cost 23, as for every configuration of
   the remedy study's smoke test, and a complete profile of 23 layers with a
   positive unsplit effort.

## 7. Execution

`exp_pot_all_decomposition.py`, the shared certificate-holdout runner
configured as in the harm-generality study (Lab 8.0, Python 3.9.25,
`requirements.txt` pins, Slurm account `naiss2026-3-660-cpu`, `fat`
partition, one CPU and 9 GiB per Slurm task), with 3 runs per array task,
702 unthrottled array tasks, and 30 minutes per array task.  Failed cells are
recovered only by rerunning their exact array index for scheduler failures.
Worst-case compute is about 2,104 x 300 s, roughly 175 CPU hours.
