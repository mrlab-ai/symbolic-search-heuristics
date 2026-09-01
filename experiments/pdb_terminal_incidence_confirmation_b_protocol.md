# Prospective Confirmation B: terminal-incidence-guided selection

This document freezes the guided end-to-end study before any Confirmation B
outcome is observed. The study may be frozen and launched only after the
canonical double-execution receipt for Confirmation A passes its complete gate
and explicitly authorizes the guided study. The B freeze binds that receipt,
its pin, both byte-identical A outputs, the sealed source-audit artifacts, the
planner revision, every executed Python source, and the option matrix.
The shared source chain is the outcome-blind, full campaign-v3 rerun. Campaign
v1 failed for insufficient 26 GiB memory; campaign v2 failed for both
translator timeouts and out-of-memory conditions at 256 GiB and 2,700 seconds.
No successful v1/v2 shard contents or source-support outcomes informed v3.
The identical launch/execution diagnostic records both failures, their
internally consistent scheduler/log manifests, and the full-rerun amendment to
512 GiB, a 7,200-second task timeout, and a 04:10:00 Slurm limit. Exactly zero
v1 or v2 shards may be reused.

The v3 receipt is accepted only in its actual unrecovered shape: ordered rows
0--819 must all be `COMPLETED` with exit `0:0`, all 820 resource-accounting
rows must attest the exact submission and resources, and recovery is null. Its
820 ordered union records must all come from original v3 output, have equal
source/union hashes, and match the canonical original-output and union-tree
manifests and digests. The consumer verifies the canonical launch intent,
Slurm script, exact 14-entry code manifest, amendment protocol, frozen
inventory, every listed live file, the exact submit command, and all bytes at
the source repository commit. The B freeze additionally records and checks an
18-entry `tracked_file_sha256` proof at its planner revision.
The launch and execution receipts must also carry the same exact isolated
execution-environment attestation (`--export=NONE`, controlled path, cleared
Python inheritance, per-array bytecode cache, and pinned Python/tool hashes).
The exact attestation envelope is required, and the manifest-verified producer
is replayed over all 1,640 source records; its gate and complete A/B split must
be byte-identical to the sealed values. The producer revision must be an
ancestor of the planner revision. After planner caching and immediately before
the exclusive freeze write, B repeats the clean-parent, source-chain,
live/tracked byte, executed-source, and canonical Confirmation A authorization
checks.

## Cohort and matrix

The cohort is the source audit's disjoint `guided_b` split. It targets 300
tasks and may proceed with 200--300 tasks only. It must contain at least 30
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
guided selector uses the sum of terminal incidence over the first 16 completed
positive-cost blind layers of the cap-aware K=32 reference as its budget.
Fewer than 16 completed probe layers is `SEARCH_UNSUPPORTED` (exit 34), with
no fallback.

There are `9N` cells for sealed cohort size `N`. Lab groups exactly three runs
per array element, hence exactly `ceil(9N/3)=3N` unthrottled array elements.
The Slurm contract is `fat`, normal QoS, one CPU, 26 GiB per CPU, and 01:40:00
per array element. Planner limits are 1800 seconds and 24,576 MiB. No array
`%` cap, nice adjustment, requeue, selective outcome retry, or task deletion is
permitted. Only scheduler interruptions in the frozen recoverable state set
may be recovered, and every interrupted element must be recovered together in
the next wave.

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
trace. All overhead results are
descriptive, excluded from structural trace identity, and do not affect either
primary contrast or any gate.

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

The matched-only mechanism claim is separately authorized only on tasks where
the guided selected heuristic differs from the reference and only if the same
nonlower-coverage, 0.02 macro-effect, positive bootstrap-lower-bound, and
positive leave-one-family-out clauses pass on that conditional subset. If no
selection differs, no mechanism claim is authorized.

## Publication and recovery

Execution, parse, and fetch artifacts are published with exclusive canonical
JSON receipts and separate SHA-256 pins. Analysis reads only the sealed fetched
matrix, runs twice from fresh loads, and publishes only byte-identical canonical
outputs plus a pinned execution receipt. Infrastructure failures are never
silently converted into missing observations, and algorithm failures are PAR2
outcomes rather than exclusions.
