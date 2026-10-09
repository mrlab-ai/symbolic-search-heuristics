# DRAFT protocol: does fragmentation explain heuristic harm beyond PDBs?

Status: **draft for author review; not frozen.**  No planner output for any
configuration below has been generated.  Freezing requires the prerequisites
in Section 6 and an explicit author decision.

## 1. Motivation and claim

The post-hoc harm decomposition on the sealed 1,052-task holdout
(`analyze_pdb_profile_harm_decomposition.py`, summary SHA-256
`0814ae2554b139ed71f9aaf30440f5c1855ddf34731bcc70dd17bdb8575b3512`) found,
for width-constrained PDBs with at most 100,000 abstract states, that
whenever a heuristic needs more BDD nodes than blind search the excess comes
from fragmentation, not from larger unsplit sets.  That analysis was defined
after the outcomes were known and covers one heuristic family.  This study
tests the claim prospectively on heuristic families that were not measured
on these tasks:

> In forward product-at-evaluation symbolic A*, when a heuristic needs more
> BDD nodes than blind search on the same task, the excess is carried by the
> fragmentation factor rather than by the unsplit effort.

It also measures, descriptively, how much coverage a perfect per-task choice
between blind and heuristic search would gain (guard headroom).

## 2. Quantities

For a task, heuristic h, and its blind run, both solved with certified
profiles: r = effort(h) / effort(blind), u = unionEffort(h) /
effort(blind), and frag = effort(h) / unionEffort(h), so r = u * frag
exactly because blind search has fragmentation one.  Effort counts regular
inner BDD nodes of every expanded bucket (complemented edges, as in CUDD).

## 3. Configurations

All configurations use the same pinned planner binary, product-at-evaluation
forward symbolic A*, the task-specific Gamer variable order with dynamic
reordering disabled, `wbh_log` and `wbh_profile_log`, 300 seconds of process
CPU time, and 8,192 MiB.

| Label | Search |
|---|---|
| `blind_fw_profiled` | `sym_fw(...)` (rerun with the new binary) |
| `ms_unaligned_10k` | `sym_fw_ms(max_states=10000, align_merge_order=false)` |
| `ms_aligned_10k` | `sym_fw_ms(max_states=10000, align_merge_order=true)` |
| `ms_unaligned_50k` | `sym_fw_ms(max_states=50000, align_merge_order=false)` |
| `pdb_cegar_1m` | `sym_fw_pdb(budget=1000000, pattern_selection=cegar)` |
| `pot_m4` (conditional) | `sym_fw_pot(m=4)`, only if an LP build is available |

The exact option strings, including M&S shrink and label-reduction defaults
and the CEGAR seed, are fixed in the frozen version.  If no LP solver can be
built, `pot_m4` is dropped before freezing, not after launch.

## 4. Cohort

Primary: the sealed 1,052-task, 45-domain holdout.  Its blind outcomes are
known from earlier studies, but no configuration in Section 3 except blind
search has been run on it with profiling.  Secondary (optional, decided
before freezing): the generated within-family instances of the earlier
fresh-instance cohort, if their translation and profiling succeed in the
pilot.  The matrix has 6 configurations x 1,052 tasks = 6,312 cells
(5,260 without `pot_m4`).

## 5. Analysis plan

Eligibility follows the post-hoc analysis: both runs solved, certified
expansion and profile streams, positive efforts and unsplit effort, and
agreement of solution costs.  Each heuristic family is analyzed separately
and pooled; domains are reported with equal weight and pooled.

Primary estimand, per family and pooled: over harmful pairs (r > 1), the
share of the log excess carried by fragmentation,
`S = sum(ln frag) / sum(ln r)`.

Proposed decision rule (to be confirmed before freezing):

1. Support: at least 100 harmful pairs from at least 20 domains per family
   for a family-level claim, and the same pooled.
2. The paper may say that fragmentation explains harm for a family only if
   S >= 0.8 for that family and at least 90% of the pairs with r > 2 have
   frag > u.
3. The paper may state the claim beyond PDBs only if rule 2 holds pooled and
   for at least two non-PDB families.
4. A failed rule is reported as such and triggers no new threshold, subset,
   or configuration.

Secondary, descriptive: medians of u and frag among harmful and helpful
pairs; the same split on pairs whose blind search takes at least 10 seconds
with search-time ratios above 1.5 and below 2/3; coverage per configuration;
and guard headroom, the coverage of a per-task oracle choosing the better of
blind and each heuristic, minus blind coverage.  If headroom is below 3% of
the tasks for every family, the online fallback guard is not pursued.

## 6. Prerequisites before freezing

1. Planner: call `WbhProfile::attach_heuristic_closed` in
   `symbolic_ms_search.cc` and `symbolic_potential_search.cc` as
   `symbolic_pdb_search.cc` does, so their solved runs log per-g unsplit
   unions; add a regression check like `misc/tests/check-wbh-complete-profiles.py`.
2. Build and pin the planner binary in the revision cache; record its
   SHA-256.  The local `builds/release_no_lp` predates `wbh_profile_log`.
3. LP: decide whether a solver for potentials is available
   (`cplex_DIR` points to a missing directory); otherwise drop `pot_m4`.
4. Pilot on 10 tasks from the 275-task development cohort, never the
   holdout: check that every configuration runs, logs complete profiles, and
   that profiling overhead keeps runs within limits.  Pilot outcomes are not
   analyzed scientifically.
5. Freeze this document, the option matrix, the cohort manifest, and the
   analysis code by hash before launch.

## 7. Execution sketch

Lab 8.0, `fat` partition, one CPU and 9 GiB per Slurm task, unthrottled
array, scheduler-only recovery of failed cells by exact array index, as in
the earlier holdout studies.  Worst-case compute is about 6,312 x 300 s,
roughly 530 CPU hours; typical runs are much shorter.
