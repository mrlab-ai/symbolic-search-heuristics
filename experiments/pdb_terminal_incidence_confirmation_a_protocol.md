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
All canonical protocol, launch, audit, and analysis inputs are lexically
validated before filesystem I/O and are read and hashed from one `O_NOFOLLOW`
descriptor, with regular-file and stable-identity checks before and after the
read. Symlinks, directories, FIFOs, and identity-changing races fail closed.

The source chain must be the outcome-blind, complete campaign-V5 rerun. Its
unknown prospective job, receipt, manifest, inventory, and output hashes are
derived from the canonical sealed intent/launch/execution chain rather than
filled with placeholders. The shared A/B consumer requires the exact V5
paths, exact receipt key sets, code-manifest closure, normalized Slurm bytes,
scheduler journal and resource rows, task-environment manifest, live output
tree, and every scoped byte at the producer revision. The V4 infrastructure
diagnostic is manifest-bound and must state that successful/cancelled V4 logs
and shards and source-support outcomes were not inspected for V5 design.

Campaign V5 uses exactly 2 TiB per CPU, a 28,800-second source timeout, a
16:40:00 Slurm limit, the `fat` partition, normal QoS, and all 820 unthrottled
array elements. It is original-only: all 820 shards and all 1,640 candidates
are rerun, `recovery` is null, and reuse counts for V1 through V4 are zero.
Each candidate is consumed from a read-only domain/problem snapshot inside the
exact per-task temporary root; both consumers revalidate the snapshot and the
task removes only its own pinned files and directories. The launch binds
regular, nonsymlink output and temporary roots by path, owner, mode, device,
and inode. The execution receipt must retain these identities, prove that the
temporary root is empty, and bind the exact 2,461-file original output tree:
one inventory, 820 shard files, 820 environment-evidence files, and 820 Slurm
logs with stderr merged into stdout. It must also bind all 820 per-task
environment records and detailed actual scheduler resource rows. No recovered
or substituted source file is accepted.

The source launch submits the exact in-memory Slurm bytes on standard input to
the hash-pinned `/usr/bin/sbatch` under a controlled `C` environment; its
command contains options only and no script path. The hash-pinned
`/usr/bin/sacct` journal must reproduce the exact `SubmitLine`, unique job,
and complete array. The consumer verifies the canonical launch intent, Slurm
script, exact manifest, protocol, inventory, all manifest-listed
live files, and their bytes at the source repository commit. At the experiment
freeze repository revision, `tracked_file_sha256` independently proves the
complete manifest closure, Slurm script, and manifest are tracked with those
exact hashes. Neither Confirmation A building nor freezing is possible until
the canonical V5 intent, attestation, launch receipt, and execution receipt pass
this complete validation.
The consumer also checks the exact attestation envelope and replays the
manifest-verified producer's split over all 1,640 sealed source records; the
replayed gate and both cohorts must be byte-identical to the attestation. Thus
each selected task's support evidence, exact 17-field record, canonical alias
group, unique typed candidate index, canonical path, and seed-derived rank are
bound to the source record that produced them. The planner revision is exactly
`8148f798f13059ee881ad2471bd20cdd61d2ec18`; its cache and binaries are built
only from that revision. A separate clean `freeze_repository_revision` binds
the Python/protocol/V5 artifacts and must descend from both revision 8148 and
the V5 producer revision. Launch must descend from both frozen revisions.
After planner-cache validation and immediately before the exclusive freeze
write, the consumer repeats the clean-parent,
source-chain, live/tracked byte, and executed-source checks.

The scheduler contract is the Arrhenius `fat` partition, normal QoS, account
`naiss2025-5-561-cpu`, one CPU, 26 GiB per CPU, and 1:40:00 per array element.
There are 2,600 cells, grouped in fixed order as three sequential cells in each
of 867 array elements; the final element contains two cells.  The array is not
throttled, has no nice adjustment, is not requeued automatically, and is
submitted with `--export=NONE`.
The primary launch and every recovery pin `/usr/bin/sbatch` and
`/usr/bin/sacct` by SHA-256, use only the controlled `C` environment, and pass
the stable regular generated job bytes in memory on standard input to an
options-only `sbatch` command. The launch journal must reproduce that complete
command and every array index for the unique recorded job. The sealed execution
receipt includes a second `sacct` view of the actual account, partition, QoS,
CPU, memory, time limit, state, exit code, and job name for every original and
recovery array element.

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
predictor is terminal incidence `I`; the six certificate baselines are `kD`,
`mQ`, `mJ`, Cartesian, width, and ADD; and the additional challenger
`D = sum_g D_g` is the unmultiplied number of inner nodes in the masked ADDs.
`D` is an ordering predictor only, not an upper-bound certificate for `E`.
The amendment adding `D` is frozen before any Confirmation A outcome exists.
It is motivated prospectively by the structural relation `D <= I`; no
Confirmation A comparison between `D` and `E` was available or inspected.
There is no general order between `D` and `E`.
Every layer must satisfy every schema, identity, and
certificate check, including `E <= I <= kD <= mQ <= mJ <= Cartesian <= width`
and the independent registered-ADD branch `I <= ADD apply`.  A provenance,
schema, frontier,
or certificate inconsistency fails the campaign instead of excluding a task.

## Raw sealing and recovery

Immutable build inputs and all raw dynamic cell files are hashed before any
parser is run.  Parsing and fetching each have their own pre-operation intent,
receipt, and hash pin.  Analysis accepts only the sealed fetched properties.

No cell is selectively rerun for an experimental outcome.  A retry is allowed
only for an array element whose latest Slurm state is one of `BOOT_FAIL`,
`NODE_FAIL`, `PREEMPTED`, or `REVOKED`.  The recovery uses the identical frozen
job file, resources, array indices, and run-to-cell mapping. All cells in each
interrupted array element are replayed together, including cells that had
already finished before the scheduler interruption. Before retry, every
dynamic name in those cells is inventoried with `lstat`; any symlink or
nonregular entry fails before it is read. Every existing dynamic file is bound
by device, inode, mode, size, modification time, and SHA-256 and moved through
an exclusive, no-follow hard-link archive without overwriting a target. The
identity-bearing recovery intent and receipt use recovery schema v2. The
complete replay set is rescanned immediately after archiving and again
immediately before `sbatch`; any reappearing, unexpected, symlinked, or
nonregular dynamic entry aborts submission. The generated job likewise refuses
every preexisting dynamic name and creates `driver.log` and `driver.err` with
exclusive no-follow descriptors rather than shell redirection. Namespace,
redirection, and helper failures before a valid child outcome use dedicated
infrastructure status 70; the generated three-cell loop exits immediately and
does not invoke a later cell. Once the run script has launched, its return code
remains an ordinary recorded planner outcome: it is written to `driver.err`,
the helper returns success, and later cells retain the frozen accounting
behavior. Time limits,
out-of-memory states, cancellation, application failures, nonzero completed
jobs, and unrecognized scheduler states fail closed and are not recoverable.
Every recovery launch has the same intent/journal/receipt protection as the
primary launch, including exact standard-input bytes, pinned executable
identities, controlled environment, options-only command, and complete array
journal evidence.

## Primary comparison and gate

Within each eligible task, all eight predictors are compared on one common set
of semantic PDB pairs for which the target `E` is strictly ordered.  A
predictor receives score 1 for the correct order, 0.5 for a tie, and 0 for the
wrong order.  We report each predictor's tie rate.  Concordance is computed
task first, then family, then with equal family weight.  Absolute `E` and
normalized `E/U` orientations must have identical pair orders and gate
decisions; the inverse-`U` null must remain tied. The same all-strict rule is
extended to all eight predictors and retained as a non-gating sensitivity
analysis.

The primary gate passes only if every clause passes:

- at least 300 eligible tasks and 25 eligible families;
- at least 300 comparison tasks, 25 comparison families, and 600 target-strict
  pairs;
- equal-family concordance of `I` is at least 0.65;
- `I` exceeds `D` and each certificate baseline by at least 0.02;
- for `D` and every certificate baseline, the lower endpoint of a paired-family
  percentile
  bootstrap is strictly positive (100,000 replicates, seed 20260901); and
- every leave-one-family-out difference between `I` and every baseline is
  strictly positive.

The genuine all-prior-unrepresented stratum is fixed by the source audit, not
by task outcomes.  It is an additional gate.  It must contribute at least 50
comparison tasks, 10 comparison families, and 100 target-strict pairs.  Its
equal-family concordance for `I` must be at least 0.65. Relative to `D` and
every certificate baseline, the advantage of `I` must be at least 0.02, the
lower endpoint of the same paired-family bootstrap must be strictly positive,
and every
leave-one-family-out difference must be strictly positive.  The analogously
frozen shadow-unrepresented stratum is reported as a non-gating diagnostic.
The non-gating top-choice-regret diagnostic also asks what happens if each
predictor selects its minimum-valued semantic heuristic within a task. If
several heuristics tie for that minimum, their target efforts are averaged;
regret is `(mean selected E - min E) / (max E - min E)` on target-nontied
tasks and is aggregated task first with equal family weight. All other
sensitivities are explicitly non-gating.

Support failure is a failed confirmation, even if all achieved-support effect
clauses pass.  Confirmation A authorizes the separately frozen guided study
only when the complete primary gate and the complete all-prior-unrepresented
gate both pass.  The analyzer is run twice from the same sealed input; its two
canonical output byte strings must be identical before either is published.
