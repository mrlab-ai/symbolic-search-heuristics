# Protocol: does fragmentation explain heuristic harm beyond PDBs?

Status: **frozen on 2026-10-10 by author decision, before launch.**  No
configuration below except blind search had been run on the holdout when
this document was frozen.  Its SHA-256 is pinned in
`pdb_profile_harm_generality_protocol.py`, together with the option matrix,
the cohort manifest, the planner revision, and the binary hashes.

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
reordering disabled (both defaults), `wbh_log` and `wbh_profile_log`, the
driver's overall limits of 300 seconds and 8,192 MiB, and the `release`
build.  The exact search strings are `CONFIGS` in
`pdb_profile_harm_generality_protocol.py`; the table restates them.

| Label | Family | Search (plus `wbh_log="wbh.jsonl",wbh_profile_log="wbh-profile.jsonl"`) |
|---|---|---|
| `blind_fw_profiled` | blind | `sym_fw()` |
| `ms_unaligned_10k` | M&S | `sym_fw_ms(max_states=10000,align_merge_order=false,build_time_limit=infinity)` |
| `ms_aligned_10k` | M&S | `sym_fw_ms(max_states=10000,align_merge_order=true,build_time_limit=infinity)` |
| `ms_unaligned_50k` | M&S | `sym_fw_ms(max_states=50000,align_merge_order=false,build_time_limit=infinity)` |
| `pdb_cegar_1m` | PDB | `sym_fw_pdb(budget=1000000,pattern_selection=cegar,cegar_max_time=10,cegar_seed=2011)` |
| `pot_m4` | potentials | `sym_fw_pot(m=4)` |

All other options keep their defaults, as in the earlier holdout studies.
`build_time_limit=infinity` is the default and is stated explicitly so that
no M&S run silently falls back to blind search.  All six configurations use
one binary built with CPLEX 22.11 (`USE_LP=YES`), so potentials need no
separate build.  The non-PDB families are M&S and potentials; the three M&S
configurations are one family.

## 4. Cohort

The sealed 1,052-task, 45-domain holdout.  Its blind outcomes are known
from earlier studies, but no configuration in Section 3 except blind search
has been run on it with profiling.  The cap-grid archive from which the
earlier studies derived the holdout was lost on 2026-10-03; the task list in
`pdb_profile_harm_generality_cohort.txt` was recovered from the sealed
seed-validation properties, and its bytes hash to the frozen holdout
manifest digest `e9ffcc16c2e73e4c92c0ccbb71c60203ba643f5ed76bf943f731e86e11169694`.
No secondary cohort is used.  The matrix has 6 configurations x 1,052
tasks = 6,312 cells.

## 5. Analysis plan

The analysis is `analyze_pdb_profile_harm_generality.py`, frozen with this
document.  A pair is a heuristic run and the blind run of the same task.  It
is eligible when both runs solved the task, both profile streams and the
expansion stream are certified, the profile is complete, efforts and the
heuristic's unsplit effort are positive, and the solution costs agree.  Each
family (M&S: three configurations; PDB: one; potentials: one) is analyzed
over all its pairs, and the pooled group contains every eligible pair.

Primary estimand, per family and pooled: over harmful pairs (r > 1), the
share of the log excess carried by fragmentation,
`S = sum(ln frag) / sum(ln r)`.

S can exceed one: it does whenever harmful pairs have unsplit effort below
blind effort on average, so fragmentation carries more than the whole
excess.

Decision rule:

1. Support: at least 100 harmful pairs from at least 20 domains per family
   for a family-level claim, and the same pooled.
2. The paper may say that fragmentation explains harm for a family only if
   S >= 0.9 for that family and, if the family has at least 20 pairs with
   r > 2, at least 95% of them have frag > u.
3. The paper may state the claim beyond PDBs only if rule 2 holds pooled and
   for both non-PDB families (M&S and potentials).
4. A failed rule is reported as such and triggers no new threshold, subset,
   or configuration.

Calibration of the thresholds.  The thresholds were set from data that
existed before any configuration of Section 3 ran: all 16 width-constrained
PDB configurations of the sealed holdout (7,207 eligible pairs, 3,318
harmful, 41 domains).  There, pooled S = 1.13, per-configuration S ranges
from 0.91 (the narrowest widths, k = 2) to 1.30, a domain-cluster bootstrap
over 20 resampled domains gives a 1st percentile of 1.03, and all 512 pairs
with r > 2 have frag > u.  S >= 0.9 therefore asks a new family to show the
effect at least as strongly as the weakest PDB configuration; 95% leaves one
exception in 20 for sampling noise.  Per domain, S is below 0.9 only in
tetris (0.42) and movie (0.71), so the rule is applied to families, not
domains.  The pilot of Section 6 does not inform the thresholds.

Timing.  Profiling the attached closed unions happens after a heuristic
search has found its plan, and blind layers are profiled during search.  All
time-based quantities therefore use process time minus the overhead seconds
(union, cofactor, heuristic-cofactor, joint-cofactor, masked,
partition-audit, serialization, and output) that the profile summary
reports, floored at 0.01 seconds.  Coverage is Lab's coverage attribute; a
run that the time limit stops while it profiles after its search counts as
unsolved, which can only lower heuristic coverage.  Only the primary
estimand requires complete profiles.

Secondary, descriptive: medians of u and frag among harmful and helpful
pairs; the same split on pairs whose blind search takes at least 10 seconds
with search-time ratios above 1.5 and below 2/3; coverage per configuration;
and guard headroom, the coverage of a per-task oracle choosing the better of
blind and each heuristic, minus blind coverage, that is, the number of
tasks the heuristic solves and blind search does not; a family's headroom is
the maximum over its configurations.  If headroom is below 3% of the tasks
(fewer than 32 tasks) for every family, the online fallback guard is not
pursued.

## 6. Prerequisites (all completed before freezing)

1. Planner: call `WbhProfile::attach_heuristic_closed` in
   `symbolic_ms_search.cc` and `symbolic_potential_search.cc` as
   `symbolic_pdb_search.cc` does, so their solved runs log per-g unsplit
   unions; add a regression check like `misc/tests/check-wbh-complete-profiles.py`.
   Done in planner revision `580a6ee3b39489cb0a3f1d4e187b52601b751eab`.
2. Build and pin the planner binary in the revision cache.  The
   `release` build of that revision is cached in
   `symk-harm-generality-revision-cache`; its binary hashes are pinned in
   the protocol module.
3. LP: CPLEX 22.11 at
   `/nobackup/proj/disk/dfsplan/personal/jendrik/opt/ibm/ILOG/CPLEX_Studio2211/cplex`
   (the `cplex_DIR` in `~/.profile` points to an old location).  The launcher
   requires `cplex_DIR` to name this install and checks the SHA-256 of
   `libcplex2211.so`.  `jj_cached_revision.py` now builds and attests
   either `release_no_lp` or `release` and pins the current jj binary.
4. Pilot on 10 tasks from the 275-task development cohort, never the
   holdout.  The cohort archive was lost on 2026-10-03; the task list was
   recovered from the joint-pilot properties and matches the frozen
   manifest digest.  Pilot tasks: hash-ranked, one per domain, among tasks
   the joint pilot's Gamer-order PDB solved in 1 to 60 seconds.  The pilot
   checks that every configuration runs, logs complete profiles, and that
   profiling overhead keeps runs within limits.  Pilot outcomes are not
   analyzed scientifically.

   Pilot result (2026-10-10, Slurm job 3616272, local build of the working
   copy with CPLEX, `builds/release/bin/downward` SHA-256
   `2693e84423fbaba955c0ce587ef0d1d8e9482ce491947070504f31d50ca28791`):
   all 60 cells exited normally; 57 solved, and every solved run logged a
   complete profile with a positive unsplit effort.  The three unsolved
   cells are the three M&S configurations on airport, which ran out of time
   during abstraction construction.  The profiling overhead was at most 4.5%
   of process time for blind search and at most 12% (M&S 10k), 16% (M&S
   50k), 18% (CEGAR PDB), and 30% (potentials) for the heuristics, hence the
   timing rule in Section 5.  The extended regression check
   `misc/tests/check-wbh-complete-profiles.py --lp-build release` passes.
5. Freeze this document, the option matrix, the cohort manifest, and the
   analysis code by hash before launch.  The launch receipt records the
   SHA-256 of every runner source file, including the analysis script.

## 7. Execution

`exp_pdb_profile_harm_generality.py` with Lab 8.0 on Python 3.9.25 (exact
pins in `requirements.txt`), Slurm account `naiss2026-3-660-cpu`, `fat`
partition, one CPU and 9 GiB per Slurm task, 7 runs per array task, 902
unthrottled array tasks, 45 minutes per array task.  Failed cells are
recovered only by rerunning their exact array index for scheduler failures,
as in the earlier holdout studies.  Worst-case compute is about 6,312 x
300 s, roughly 530 CPU hours.
