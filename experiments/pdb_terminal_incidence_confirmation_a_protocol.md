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

The source chain is a fresh V11 census of all 1,640 candidates. It reads or
reuses no runtime payload from V1--V10. Each of the 820 unthrottled `fat`
partition tasks computes its original two candidates under one frozen 62-file
producer closure. Only `input-rejected` and `success` are accepted source
outcomes; timeout and every other outcome are infrastructure failures. The
terminal seal requires all scheduler rows to be `COMPLETED` with exit `0:0`
before it reads a worker payload.

Before the full census, a controller publication canary and a compute canary
exercise the exact child-process and immutable publisher path. The preflight
authorization is committed at revision P and consumed through the independent
committed-snapshot reader before the full launch. The full source seal is
committed at revision Q. The consumer verifies the exact ancestry
`S -> P -> Q`, byte equality of the preflight and full tracked closures at the
corresponding revisions, the frozen inventory, all scheduler and resource
rows, all 1,640 native records, and the controller and compute-canary evidence.
It independently reconstructs and checks the 38-file translator closure.

The deterministic split yields a 650-task Confirmation A projection and a
300-task guided-B projection. Their typed candidate indices, identities, and
problem hashes are disjoint; both meet their preregistered family-support
floors, and B obeys its per-family cap. Each native projection has exactly 14
fields and retains the canonical alias group, source hashes, stratum flags,
selection role, and seed-derived rank. The complete projection and ordered
candidate indices are separately hashed.

The A freeze consumes exact revision Q, embeds the complete native A
projection and all V11 bindings, and never reopens V11 payloads afterward. It
proves `S -> P -> Q -> F` and planner revision
`8148f798f13059ee881ad2471bd20cdd61d2ec18 -> F`. After planner-cache
validation, it consumes the same Q a second time and compares the complete
canonical source projection immediately before the exclusive write. Every
executed experiment source is also checked both live and at the clean freeze
revision F. Thus subsequent experiment building and analysis depend only on
the self-contained freeze and the committed source chain.

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
`g` order. The base measurement and eligibility machinery (including
whole-task eligibility, early-solution handling, semantic-PDB deduplication,
and frontier identity) is inherited from the prospective terminal-incidence
shadow protocol; Confirmation A freezes its own expanded predictor and gate
identity. In particular, the target is exact partition effort `E`; the primary
predictor is terminal incidence `I`; the six raw certificate baselines are `kD`,
`mQ`, `mJ`, Cartesian, width, and ADD. A seventh certificate baseline is the
layerwise meet `meet = sum_g min(kD_g, ADD_g)`, which preserves
`E <= I <= meet` while never exceeding either aggregate certificate. The
additional non-certificate challengers are
`D = sum_g D_g`, the unmultiplied number of inner nodes in the masked ADDs,
and `value_count = sum_g k_g`, the summed number of active heuristic values.
They test the row and column counts of the node--terminal incidence relation,
respectively. Neither is an upper-bound certificate for `E`.
The amendments adding `D`, `value_count` and `meet` are frozen before any
Confirmation A outcome exists. `D` is motivated prospectively by the
structural relation `D <= I`; `value_count` is motivated by the alternative
that incidence merely proxies the number of active values. The meet is
motivated as the strongest direct combination of the independently certified
`kD` and ADD branches. No Confirmation A comparison of any amendment with `E`
was available or inspected. There is no general order between either
non-certificate challenger and `E`.
The descriptive certificate-tightness diagnostic reports `E/P` only for `I`
and the seven upper-bound certificate baselines; it omits non-certificate `D`
and `value_count`.
Every layer must satisfy every schema, identity, and
certificate check, including `E <= I <= kD <= mQ <= mJ <= Cartesian <= width`
and the independent registered-ADD branch `I <= ADD apply`.  A provenance,
schema, frontier,
or certificate inconsistency fails the campaign instead of excluding a task.

## Raw sealing and recovery

Immutable build inputs and all raw dynamic cell files are hashed before any
parser is run.  Parsing and fetching each have their own pre-operation intent,
receipt, and hash pin.  Analysis accepts only the sealed fetched properties.
Before launching the planner, the cell helper writes the canonical dynamic
file `execution-hardware-v1.json` with the unique whitespace-normalized
`model name` observed in `/proc/cpuinfo` and `os.uname().machine`. It records
no hostname, job identifier, timestamp, raw processor data, or memory value.
Execution sealing requires one valid record per cell, requires all cells in
each sequential array element to agree, and records an ordered-record digest
plus processor-model and architecture counts. The double-run analysis carries
that validated summary and the execution-receipt digest as non-gating
provenance.

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

Within each eligible task, all ten predictors are compared on one common set
of semantic PDB pairs for which the target `E` is strictly ordered.  A
predictor receives score 1 for the correct order, 0.5 for a tie, and 0 for the
wrong order.  We report each predictor's tie rate.  Concordance is computed
task first, then family, then with equal family weight.  Absolute `E` and
normalized `E/U` orientations must have identical pair orders and gate
decisions; the inverse-`U` null must remain tied. The same all-strict rule is
extended to all ten predictors and retained as a non-gating sensitivity
analysis.

The primary gate passes only if every clause passes:

- at least 300 eligible tasks and 25 eligible families;
- at least 300 comparison tasks, 25 comparison families, and 600 target-strict
  pairs;
- equal-family concordance of `I` is at least 0.65;
- `I` exceeds `D`, `value_count` and each certificate baseline by at least
  0.02;
- for `D`, `value_count` and every certificate baseline, the lower endpoint
  of a paired-family percentile
  bootstrap is strictly positive (100,000 replicates, seed 20260901); and
- every leave-one-family-out difference between `I` and every baseline is
  strictly positive.

The genuine all-prior-unrepresented stratum is fixed by the source audit, not
by task outcomes.  It is an additional gate.  It must contribute at least 50
comparison tasks, 10 comparison families, and 100 target-strict pairs.  Its
equal-family concordance for `I` must be at least 0.65. Relative to `D`,
`value_count` and every certificate baseline, the advantage of `I` must be at
least 0.02, the lower endpoint of the same paired-family bootstrap must be
strictly positive, and every
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
