# Prospective Confirmation B: terminal-incidence-guided selection

This document freezes the guided end-to-end study before any Confirmation B
outcome is observed. The study may be frozen and launched only after the
canonical double-execution receipt for Confirmation A passes its complete gate
and explicitly authorizes the guided study. The B freeze binds that receipt,
its pin, both byte-identical A outputs, the sealed source-audit artifacts, the
planner revision, every executed Python source, and the option matrix.
The shared source chain is the outcome-blind, full campaign-v4 rerun. Its
launch is pinned to producer commit
`9fa1387455f947772b8b37e3b103f1ca84efb27b`, job `1865695`, launch-receipt
SHA-256 `90ec55eb1d603cb7434885eeb99ceb2a0123ac02f4f9c02c885cab2635442921`,
24-entry code-manifest SHA-256
`d3b571aaffce9f58f09d15f118df57997773c522e3da74bcdcbfbc00299f0518`,
Slurm-script SHA-256
`8504f5b778d74a5120605947e710713532018e2007d276df8c580167b9ce1a8f`,
and source-inventory SHA-256
`bb9be49a4652ff7bedcadb04b4db35cad701a5b2a2a6d6347c15e0ad670e056e`.
The pinned outcome-blind v3 infrastructure diagnostic
`a340d2de01304702f6c101d2bb1592536ebc6dfedc1638c5ce1c0559e5ddcf57`
authorizes a complete rerun without inspecting successful v3 shard or log
contents or source-support outcomes.

Campaign v4 uses exactly 1,024 GiB per CPU, a 14,400-second source timeout, an
08:20:00 Slurm limit, the `fat` partition, normal QoS, and all 820 unthrottled
array elements. It is original-only: all 820 shards and all 1,640 candidates
are rerun, `recovery` is null, and reuse counts for v1, v2, and v3 are zero.
Each candidate is consumed from a read-only domain/problem snapshot inside the
exact per-task temporary root and revalidated around both consumers. The
execution receipt must preserve the launch identities of the regular,
nonsymlink output and temporary roots, prove that the temporary root is empty,
bind all 820 isolated task-environment records, and bind the exact 2,461-file
original output tree: one inventory, 820 shard files, 820 environment-evidence
files, and 820 Slurm logs with stderr merged into stdout. Detailed actual
scheduler resource rows are mandatory.

The source launch passes the exact in-memory Slurm bytes on standard input to
hash-pinned `/usr/bin/sbatch` under a controlled `C` environment. Its command
contains options only and no script path; hash-pinned `/usr/bin/sacct` must
reproduce the exact `SubmitLine`, unique job, and complete array. The consumer
verifies the canonical launch intent, Slurm script, exact 24-entry manifest,
amendment protocol, inventory, every listed live file, and all bytes at the
source repository commit. The B freeze records and checks the corresponding
26-entry `tracked_file_sha256` proof (24 manifest entries, Slurm script, and
manifest) at its planner revision. Neither B freezing nor launching is
possible until both the canonical v4 attestation and execution receipt exist
and validate completely.
The exact attestation envelope is required, and the manifest-verified producer
is replayed over all 1,640 source records; its gate and complete A/B split must
be byte-identical to the sealed values. The producer revision must be an
ancestor of the planner revision. After planner caching and immediately before
the exclusive freeze write, B repeats the clean-parent, source-chain,
live/tracked byte, executed-source, and canonical Confirmation A authorization
checks.
All canonical protocol, authorization, launch, audit, and analysis inputs are
lexically validated before filesystem I/O and are read and hashed from one
`O_NOFOLLOW` descriptor, with regular-file and stable-identity checks before
and after the read. Symlinks, directories, FIFOs, and identity-changing races
fail closed. In particular, analysis accepts only the exact lexical sealed
properties path, not a resolving or symlink alias.

## Cohort and matrix

The cohort is the source audit's disjoint `guided_b` split. It must contain
exactly 300 tasks and at least 30
normalized benchmark families, at least 12 shadow-unrepresented families, and
at least 50 tasks from at least 10 all-prior-unrepresented families. It is
source-identity- and problem-hash-disjoint from Confirmation A. No outcome can
change membership.
Every task retains the producer's exact record schema, canonical alias group,
candidate index, and seed-derived split rank. Candidate indices are unique and
no family may contribute more than the attested maximum of 12 tasks.

Each sealed task is run once under exactly nine configurations:

1. forward blind search;
2. direct BDD-prefix PDB;
3. direct goal-prefix PDB;
4. direct goal-fill PDB;
5. seeded CEGAR with at most 128 refinement calls;
6. exact-width selection with K=32 and exact (uncapped) PDB values;
7. the cap-aware exact-width K=32 reference;
8. terminal-incidence-guided selection; and
9. the matched-work control, which performs the same probe and preselection as
   the guided selector but executes the cap-aware K=32 reference.

All PDB searches use a 100,000-state budget, gamer ordering off, dynamic
reordering off, no shadow partition, no prune-only mode, and no batching. CEGAR
pool generation uses seed 2011, infinite time, and at most 128 refinement
calls. The cap-aware selector tests 0, 1, 2, 4, ..., 256, and exact values. The
guided selector uses the sum of terminal incidence over exactly the first 16
completed blind layers of the cap-aware K=32 reference on a positive-cost task
as its budget. The completed initial layer at g=0 is valid and counts toward
the 16; "positive-cost" constrains operator costs, not the first layer's g
value. Fewer than 16 completed probe layers is `SEARCH_UNSUPPORTED` (exit 34),
with no fallback.

There are exactly 2,700 cells. They are created in a frozen task-major order:
all nine cells of a task are contiguous, and the cap-aware K=32, guided, and
matched-work cells form the final three-cell block for that task. Within each
family, the execution order of these three arms cycles deterministically over
all three rotations, so each arm occupies each position equally often up to
one task. The complete run-ID mapping and its SHA-256 digest are frozen and
checked against every generated `static-properties` file. Lab groups exactly
three consecutive runs per array element, hence exactly 900 unthrottled array
elements.
The Slurm contract is `fat`, normal QoS, one CPU, 26 GiB per CPU, and 01:40:00
per array element. Planner limits are 1800 seconds and 24,576 MiB. No array
`%` cap, nice adjustment, requeue, selective outcome retry, or task deletion is
permitted. Only scheduler interruptions in the frozen recoverable state set
may be recovered. Recovery archives every dynamic artifact and reruns all
three cells of each interrupted element together, including cells that had
already finished before the interruption; the run-order protocol and mapping
digest are repeated in every recovery intent and receipt. This whole-triad
rule also applies when scheduler accounting marks the element recoverable but
all three cells appear complete; incomplete-cell intersection is not a
precondition. Every dynamic name is first inventoried with `lstat`, and any
symlink or nonregular entry fails before reading. Archived entries bind device,
inode, mode, size, modification time, and SHA-256 and are installed without
following or overwriting an archive target under recovery schema v2. The
complete triad is rescanned
immediately after archiving and again immediately before `sbatch`. The generated
job refuses every preexisting dynamic name, including the selector trace, and
creates both driver streams with exclusive no-follow descriptors. Namespace,
redirection, and helper failures before a valid child outcome use dedicated
infrastructure status 70; the blocked three-cell loop exits immediately and
does not invoke a later arm. Once the run script has launched, its return code
remains an ordinary recorded planner outcome: it is written to `driver.err`,
the helper returns success, and subsequent arms retain the frozen outcome
accounting. The primary launch
and every recovery pin `/usr/bin/sbatch` and `/usr/bin/sacct` by SHA-256, use a
controlled `C` environment, pass stable regular job bytes in memory on standard
input, and use an options-only command with no job-file argument. Their journal
must reproduce the exact command, unique job, and every intended array index.
The sealed execution receipt includes detailed actual account, partition, QoS,
CPU, memory, time-limit, state, exit-code, and job-name rows for every original
and recovery array element.

## Selector trace gate

The dedicated `incidence-selector.jsonl` stream has schema
`symbolic-search-heuristics/terminal-incidence-selector-trace/v3`. For every
task, guided and matched must have the same certified status. A complete pair
must agree exactly on the structural schema, probe, pool, every candidate,
preselection, and reference event after excluding only CPU time, wall time,
and memory accounting. In particular, `pool_sha256` and
`preselection_sha256` must agree. A short-probe pair must contain exactly the
schema and matching incomplete probe. Any missing, malformed, asymmetric, or
other partial pair fails the provenance gate. Every task remains in the
performance matrix regardless.

The parser independently replays the frozen C++ selection rule. Every variant
attests the same raw maximum finite value for its pattern. The final exact
variant also carries a canonical base64url/uvarint histogram of every raw
finite value and its multiplicity; capped variants carry null. The parser
reconstructs the exact finite count, dead count, sum, maximum, and initial
value, then recomputes every capped finite sum and capped initial value from
that histogram. Candidate variants
must contain exactly the caps among 0, 1, 2, 4, 8, 16, 32, 64, 128, and 256
that are strictly below that maximum, followed by the exact transform. The
pool has unique pattern vectors, each of the five frozen generator sources
occurs exactly once globally, and the mandatory empty pattern is pool index
zero. Its sole exact candidate has one finite state at value zero, widths one,
and layer incidences exactly equal to the blind-probe BDD-node counts; the
`empty` source cannot label a nonempty pattern. Every other candidate's layer
incidence is at least the corresponding probe BDD-node count. Across
increasing caps, terminal incidence by layer, cofactor width, ADD-width upper
bound, and finite-value sums are monotone, while exact and capped aggregates
must be consistent with the raw maximum, initial state, finite states, and
dead states. The
reference must
be the best strongest-per-pattern candidate feasible at width 32. The guided
winner must be the best strongest-per-pattern candidate within the incidence
budget, using in order: initial dead-end status, initial heuristic value,
finite-value mean, dead-state fraction, smaller cofactor width, fewer abstract
states, and lexicographically smaller pattern. The matched arm must select the
recomputed reference. Logged feasible, retained, reference, or selected fields
that disagree with this replay fail certification.

The standalone cap-aware K=32 arm is independently parsed with the certified
whole-trace cap-selector parser. Its complete normalized pool (pool index,
source set, pattern, abstract-state count, and state-budget feasibility) must
equal the pool reconstructed by both selector arms. Its selected pool index,
source set, pattern, and value cap (with wire value -1 normalized to
exact/null) must equal their logged reference identity on every complete
selector pair. The primary plain reference is therefore certified by its
realized endpoint and pool, not merely by its configuration string.

The matched arm must select its logged reference. A task contributes to the
matched-work mechanism subset only if the guided selected identity differs
from that reference. Claims about the effect of the selection decision are
conditional on this frozen subset; timing/memory fields are never used to
define it.

Probe and selection CPU seconds, wall seconds, and peak-memory before, after,
and nonnegative delta are retained as overhead measurements. The analysis
revalidates them and reports per-task rows and separate arm summaries. Short
probes require exact integer coverage zero and planner exit code 34 and have
probe overhead but no selection overhead; exit 34 is forbidden for a complete
trace. The separately parsed overhead fields are descriptive and excluded
from structural trace identity and gate definitions. The work itself remains
part of each arm's total planner time and hence PAR2; the matched-work arm
tests the selection decision after holding probe and preselection work fixed.

The fetched Confirmation B properties file is itself a sealed input: it must be
a stable regular file, never a symlink, and its exact bytes and SHA-256 must
match the fetch receipt before analysis.

## Primary outcome and gate

The end-to-end runtime outcome is PAR2 with the fixed 3600-second denominator.
A solved cell requires coverage one, planner exit code zero, and finite total
planner time in [0, 1800] seconds. Coverage/exit-code contradictions fail the
analysis. Every unsolved,
unsupported, resource-limited, or algorithm-failure cell receives 3600
seconds. No task or cell is dropped. For each normalized benchmark family,
the contrast is the task mean of

`(PAR2(reference) - PAR2(guided)) / 3600`,

and the reported effect is the equal-family macro mean.

The complete primary gate passes only if, for both the cap-aware K=32
reference and the matched-work control:

* guided coverage is no lower;
* the equal-family normalized PAR2 improvement is at least 0.02;
* the lower endpoint of the 95% paired-family percentile-bootstrap interval is
  strictly positive; and
* every leave-one-family-out (the normalized planning-domain unit) effect is
  strictly positive.

The bootstrap uses exactly 100,000 resamples, seed 20260902, sampling frozen
families with replacement, and nearest-rank 2.5% and 97.5% endpoints. All
comparisons use the same complete task set.

The analysis also freezes and reports the same complete-set contrast of guided
selection against blind search, each of the three direct PDB constructions,
deterministic CEGAR, and uncapped exact-width K=32 selection. These six
comparisons are descriptive and never enter the complete primary gate, which
remains solely the two contrasts against cap-aware K=32 and matched work.

The matched-only mechanism claim is separately authorized only if at least 50
tasks from at least 10 normalized families remain after restricting to tasks
where the guided selected heuristic differs from the reference, and only if
the same
nonlower-coverage, 0.02 macro-effect, positive bootstrap-lower-bound, and
positive leave-one-family-out clauses pass on that conditional subset. A
smaller subset is reported but cannot authorize the mechanism claim.

## Publication and recovery

Execution, parse, and fetch artifacts are published with exclusive canonical
JSON receipts and separate SHA-256 pins. Analysis reads only the sealed fetched
matrix, runs twice from fresh loads, and publishes only byte-identical canonical
outputs plus a pinned execution receipt. Infrastructure failures are never
silently converted into missing observations, and algorithm failures are PAR2
outcomes rather than exclusions.
