# Source-disjoint terminal-incidence Confirmation A protocol

This protocol is frozen before any planner outcome from Confirmation A is
read.  Source eligibility and the A/B split are determined by the separately
sealed universal unseen-source audit.  The source audit's A cohort is used
without replacement, deletion, or substitution.  A launch is forbidden unless
that audit authorizes the split and contains exactly 650 Confirmation A tasks.

## Freeze and provenance

The outcome-independent freeze record is created only after the source audit
has been sealed and the planner revision has been committed and cached.  It
pins the complete source attestation and execution receipt, the exact
Confirmation A task sequence and source bytes, the benchmark revision, the
planner commit and binaries, this protocol, the option matrix, and every
executed experiment source.  The experiment build and launch revalidate the
freeze and materialize verified PDDL bytes into every run directory.  A launch
intent is written before `sbatch`; a unique Slurm comment permits recovery of a
launch receipt if submission succeeded but the client failed before recording
the returned job ID.  An unresolved intent never authorizes resubmission.

The source chain must be the complete high-memory campaign-v2 rerun: exact v2
launch and execution schemas, 256 GiB per source-audit array element, all 820
shards rerun, and zero reused v1 shards.  The launch and execution receipts
must carry the same attested v1 failure diagnostic, which records the v1 OOM
as infrastructure-only evidence and forbids using any v1 shard contents or
source-support outcomes for the v2 design.  A v1 receipt, a partial v2 rerun,
or a mismatched failure diagnostic is rejected before freezing.

The scheduler contract is the Arrhenius `fat` partition, normal QoS, account
`naiss2025-5-561-cpu`, one CPU, 26 GiB per CPU, and 1:40:00 per array element.
There are 2,600 cells, grouped in fixed order as three sequential cells in each
of 867 array elements; the final element contains two cells.  The array is not
throttled, has no nice adjustment, is not requeued automatically, and is
submitted with `--export=NONE`.

## Fixed measurements

Every task is run once with each of four direct PDB generators:

1. BDD-order prefix (`bdd_prefix`);
2. goal-order prefix (`goal_prefix`);
3. goal-order fill (`goal_fill`);
4. seeded CEGAR (`cegar`, seed 2011, no wall-clock stopping condition, and at
   most 128 refinement calls; natural termination may occur earlier).

All configurations use a 100,000-state PDB budget, exact (uncapped) heuristic
values, Fast Downward variable ordering (`gamer_ordering=false`), dynamic BDD
reordering disabled, and `shadow_partition=true`.  The heuristic is measured
on the blind frontier but does not guide, prune, order, or partition the search.
The planner limit is 1,800 seconds and 24,576 MiB per cell.

The fixed horizon is the first 16 completed, non-goal blind layers in increasing
`g` order.  Whole-task eligibility, early-solution handling, semantic-PDB
deduplication, frontier identity, targets, predictors, certificates, and timing
diagnostics are exactly those in the prospective terminal-incidence shadow
protocol.  In particular, the target is exact partition effort `E`; the primary
predictor is terminal incidence `I`; and the controls are `kD`, `mQ`, `mJ`,
Cartesian, width, and ADD.  Every layer must satisfy every schema, identity, and
certificate check, including `E <= I <= kD <= mQ <= mJ` and the separately
defined Cartesian, width, and ADD upper bounds.  A provenance, schema, frontier,
or certificate inconsistency fails the campaign instead of excluding a task.

## Raw sealing and recovery

Immutable build inputs and all raw dynamic cell files are hashed before any
parser is run.  Parsing and fetching each have their own pre-operation intent,
receipt, and hash pin.  Analysis accepts only the sealed fetched properties.

No cell is selectively rerun for an experimental outcome.  A retry is allowed
only for an array element whose latest Slurm state is one of `BOOT_FAIL`,
`NODE_FAIL`, `PREEMPTED`, or `REVOKED`.  The recovery uses the identical frozen
job file, resources, array indices, and run-to-cell mapping.  Completed cells in
an interrupted element remain untouched; partial dynamic files for incomplete
cells are moved into a hash-attested archive before retry.  Time limits,
out-of-memory states, cancellation, application failures, nonzero completed
jobs, and unrecognized scheduler states fail closed and are not recoverable.
Every recovery launch has the same intent/journal/receipt protection as the
primary launch.

## Primary comparison and gate

Within each eligible task, all seven predictors are compared on one
grand-shared set of semantic PDB pairs for which `E` and every predictor are
strictly ordered.  Concordance is computed task first, then family, then with
equal family weight.  Absolute `E` and normalized `E/U` orientations must have
identical pair orders and gate decisions; the inverse-`U` null must remain tied.

The primary gate passes only if every clause passes:

- at least 300 eligible tasks and 25 eligible families;
- at least 300 comparison tasks, 25 comparison families, and 600 grand-shared
  strict pairs;
- equal-family concordance of `I` is at least 0.65;
- `I` exceeds each control by at least 0.02;
- for every control, the lower endpoint of a paired-family percentile
  bootstrap is strictly positive (100,000 replicates, seed 20260901); and
- every leave-one-family-out difference between `I` and every control is
  strictly positive.

The genuine all-prior-unrepresented stratum is fixed by the source audit, not
by task outcomes.  It is an additional gate: it must contribute at least 10
comparison families and 100 grand-shared strict pairs; its equal-family
concordance for `I` must be at least 0.65; and `I` must exceed every control by
a strictly positive amount.  The analogously frozen shadow-unrepresented
stratum is reported as a non-gating diagnostic.  All other sensitivities are
explicitly non-gating.

Support failure is a failed confirmation, even if all achieved-support effect
clauses pass.  Confirmation A authorizes the separately frozen guided study
only when the complete primary gate and the complete all-prior-unrepresented
gate both pass.  The analyzer is run twice from the same sealed input; its two
canonical output byte strings must be identical before either is published.
