# Full-census V9 source-audit protocol

Status: frozen after the aggregate V8 terminal state was known and before any
V8 array-element identity, task log, shard, environment record, temporary
path, or scientific source-support result was inspected.  The only V8
execution fact known when this protocol was frozen was that the exact
25-element repair array ended with 8 `COMPLETED` elements and 17
`OUT_OF_MEMORY` elements under its uniform 2950-GiB profile.  V8 failed its
all-success gate, produced no seal or attestation, and cannot authorize a
confirmation experiment.

## Purpose and non-adaptive boundary

V9 replaces selective source repair with a fresh, uniform audit of the entire
immutable 1,640-candidate inventory.  It reuses no V1--V8 task log, shard,
environment record, translated SAS file, source-support classification, or
other runtime payload.  In particular, neither V5's 795 completed shards nor
V8's eight completed elements can contribute a scientific byte to V9.

V9 retains without change:

- the benchmark revision and the 1,640 ordered source identities and hashes;
- the source-disjointness ledger, aliases, family map, split seed and ranking;
- the Confirmation-A and guided-B task and family floors;
- the semantic support rules for a successful translation; and
- the downstream A/B measurement, analysis, and authorization rules.

The complete candidate set is `range(1640)` regardless of every V8 row state.
The V8 row membership may be recorded only after this protocol and the
scheduler-only failure recorder are committed.  No V8 membership may alter a
V9 resource, mapping, outcome class, retry decision, or source-selection rule.

## Population and outcome classes

Every inventory candidate is attempted once under the exact per-candidate
resource limits already fixed for a Confirmation-A cell: 1,800 seconds and
24,576 MiB.  V9 distinguishes three source-audit outcomes.

1. `success`: the pinned translator returns normally and V9 validates the
   complete SAS summary and same-pass normalization evidence.  The unchanged
   semantic support rules decide whether the candidate is supported.
2. `input-rejected`: the pinned translator returns its documented input-error
   code.  This is an unsupported-language result under the existing rules.
3. `resource-excluded`: an authoritative V9 child limit records either
   `memory` or `time`.  Source support is **indeterminate**, not false.  Such a
   candidate is in the audited census but is ineligible for either cohort.

No other exit, signal, missing artifact, malformed artifact, or ambiguous
limit event is an outcome class.  It is an infrastructure failure that makes
the entire V9 campaign unusable.  The final report gives resource exclusions
both by candidate and by family.  The resulting empirical population is the
source-disjoint subset whose support is determined within the actual
Confirmation-A cell limits; it is not claimed to cover tasks requiring more
resources merely to translate.

The outcome taxonomy, limits, and eligibility rule are frozen before any V9
task runs.  They cannot be amended after launch.  A source-support floor
failure cannot be repaired by lowering a floor, reclassifying an exclusion,
or selectively rerunning a candidate.

## One-pass, bounded worker

The historical `python -m translate` entry point calls the translator's
`main()` twice after a successful first return.  The old source-audit worker
then reparses and normalizes the PDDL a third time, retains complete captured
streams in memory, and parses the whole SAS file with `read_text().splitlines()`.
V9 does not modify that historical code or reinterpret any historical output.

Instead, a manifest-bound V9 driver calls the unchanged translator
implementation exactly once.  It applies the same options and documented
input, memory, and time exit codes.  A wrapper around the same normalization
call records the normalized-axiom count from that pass; V9 does not perform a
second normalization.  Translator stdout and stderr are spooled to regular
private files and converted to byte count, SHA-256, and bounded tail by
streaming reads.  `output.sas` is hashed and parsed with a streaming parser
that retains aggregate counts and operator-cost minimum/maximum only.

Each candidate runs in a fresh process group and a newly created, empty,
candidate-private working directory.  No descendant may escape that group,
and the supervisor kills and reaps the complete group before classifying the
candidate.  No working directory or `output.sas` pathname is reused between
the two candidates.  The child receives an address-space limit of exactly
24,576 MiB and the same exact 1,800-second CPU limit as a Confirmation-A
planner cell; the wrapper installs the translator's documented CPU-limit
handler.
Return code 20 is accepted as `resource-excluded/memory` only when produced by
the manifest-bound limited child.  Return code 21 under that verified CPU
limit is accepted as `resource-excluded/time`.  Return code 31 is the sole
`input-rejected` code.  Return code zero requires all success evidence.  The
supervisor enforces a 1,950-second wall watchdog for each child.  Watchdog
expiry, all other returns, and every unexpected signal fail closed; wall time
can depend on cluster load and is not silently converted into population
eligibility.

Before launch, differential tests must show that the one-pass driver and the
historical entry point produce byte-identical SAS on successful fixtures,
identical SAS absence on input-rejected fixtures, and identical scientific
summaries on supported and normalized-axiom fixtures.  Tests must also show
bounded stream/SAS handling on large synthetic files.  These tests use only
synthetic or ordinary translator fixtures, never V1--V8 source outcomes.

## Array mapping and Slurm profile

V9 uses one unthrottled 820-element array, `0-819`.  Array element `s` is the
sole owner of inventory candidates `2s` and `2s+1`.  A tiny supervisor launches
the two candidates sequentially in fresh children, validates each canonical
candidate record, and publishes one canonical two-record shard only after
both dispositions are complete.  The mapping is total, injective, ordered,
and independent of every prior campaign.

The fixed outer profile is:

```text
account=naiss2025-5-561-cpu
partition=fat
qos=normal
nodes=1
ntasks=1
cpus-per-task=1
mem=26G
time=01:10:00
array=0-819
array-throttle=none
nice=0
requeue=false
export=NONE
```

Two 1,950-second child wall watchdogs leave 300 seconds within the 4,200-second
outer wall limit for supervisor startup, final publication, and scheduler
overhead.  This wall guard is infrastructure-only; the scientific time ceiling
remains 1,800 CPU seconds per candidate.  The 26-GiB outer allocation leaves
2 GiB outside the child's 24-GiB address-space limit.  A task-private project
directory holds spooled streams and SAS data, so node-local temporary-space
loss cannot erase the only evidence.  The supervisor deletes no published
record and overwrites nothing.

The launch is one shot with an exclusively published intent and retained raw
`sbatch` stdout/stderr/result journal.  No `%` throttle, nice penalty, requeue,
partition fallback, or adaptive resource mapping is permitted.  Any launch
uncertainty uses a no-resubmission recovery path.

## Scheduler gate, seal, and authorization

All 820 outer rows must be exactly `COMPLETED/0:0` before the controller opens
any V9 shard, worker stream, environment record, or source-support outcome.
An outer `OUT_OF_MEMORY`, timeout, failure, preemption, or other non-success
state is campaign-fatal; it is not converted into a candidate-level resource
exclusion.  The controller must not enumerate or inspect any partial shard,
stream, environment record, or outcome from that campaign until a successor
protocol is frozen.  The entire V9 namespace is permanently burned and can
never be retried or reused; later diagnostic inspection cannot authorize
reuse.  V9 has no selective recovery and reuses no partial row.

After the all-success scheduler gate, the seal must:

1. authenticate the launch, manifest, environment, source inventory, and all
   820 exact resource-contract rows, including zero scheduler restarts;
2. validate one canonical ordered shard and environment record per row;
3. validate the exact candidate sequence `0..1639` with no duplicate, gap, or
   reordering;
4. require every candidate disposition to satisfy the frozen taxonomy;
5. assemble the unchanged semantic support classification for successful and
   input-rejected records while keeping resource exclusions indeterminate;
6. run the unchanged deterministic A/B split on supported,
   resource-determinate candidates only; and
7. apply every original task, family, novelty, and disjointness floor.

The seal exclusively publishes staged tree, census, split, attestation, and
execution-receipt records.  Only a complete passing source-support gate sets
`confirmation_prelaunch_authorized=true`.  The receipt, attestation, launch
captures, and seal stages must be committed immediately before any A freeze,
paper result rendering, or discretionary source-outcome analysis, and should
receive an external archive witness when practical.

Downstream A, B, direct-selector, renderer, and paper provenance must remain
unbound until a strict independent V9 consumer validates the committed seal.
V8 can never authorize those experiments.

## V8 failure-record boundary

The post-failure recorder may make one scheduler query at the user-authorized
hourly cadence.  It authenticates V8 launch metadata and records only the
ordered terminal array rows, requested resource contract, row digest, and
state/exit aggregates.  It must not request elapsed time, memory high-water
marks, node names, or step data, and must not enumerate or open the V8 output
tree.  Its receipt records the aggregate 8/17 fact known above, the full-census
V9 run set, `all_success_gate_passed=false`,
`source_audit_complete=false`, `confirmation_prelaunch_authorized=false`,
zero scientific payload reads/reuse, and a permanently burned V8 namespace.

## Required prelaunch tests and stop conditions

The manifest-bound test suite must cover at least:

- exact inventory and `s -> (2s, 2s+1)` bijection;
- one-pass translator invocation and same-pass normalization evidence;
- streaming equivalence and bounded-memory behavior for SAS and both streams;
- success, input rejection, controlled memory exclusion, controlled CPU-time
  exclusion, and rejection of every wall timeout, ambiguous exit, or signal;
- fresh-child isolation and the 24,576-MiB/1,800-second limits;
- canonical publication, collision, symlink, truncation, mutation, duplicate,
  omission, and reordering attacks;
- exact account, `fat` partition, normal QoS, nodes/tasks/CPUs, 26G,
  01:10:00, zero nice adjustment, no requeue, `export=NONE`, no throttle, and
  no-resubmission recovery;
- all-success-before-read ordering and rejection of every outer non-success;
- zero V1--V8 payload paths in the V9 union; and
- unchanged split seed, source hashes, cohort floors, and A/B absence before a
  committed successful seal.

Any failure of these tests, any change to the frozen inventory or taxonomy,
any V9 outer-task failure, any ambiguous candidate disposition, any seal
inconsistency, or any source-support floor failure forbids Confirmation A.
