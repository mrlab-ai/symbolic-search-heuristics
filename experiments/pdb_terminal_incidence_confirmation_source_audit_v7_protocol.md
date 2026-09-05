# Universal unseen-source audit: prospective V7 scheduler-only repair

Campaign V7 is a new prospective repair of terminal campaign V5. It neither
alters nor seals V5, and it consumes no V6 runtime artifact. V7 was designed
after the aggregate V5 terminal summary---795 `COMPLETED`, 15 `FAILED`, and 10
`OUT_OF_MEMORY`---and the V6 classifier rejection of array row 2 as
`FAILED 2:0` were known. The attempted V6 diagnosis produced no accepted
diagnostic, manifest, launch, job, or shard, and no V5 log, shard,
environment record, or source-support classification was opened. The aborted
V6 call did revalidate the already-fixed V5 inventory/task metadata and its
scheduler parser transiently parsed `Elapsed`; neither value was persisted in
an accepted diagnostic or exposed beyond aggregate state/exit reporting.

The first V7 `diagnose-v5` attempt, from revision
`9c06f962627739d40d00cb2ef19525a80b2ca97f`, completed the prediagnosis
freeze, read the V5 intent and receipt, checked the live executable identities
and all 38 V5 manifest dependencies, and read the historical V4-to-V5
diagnostic. It then failed at the diagnostic's four embedded list-digest
checks: the V5 producer had hashed canonical JSON including its terminating
line feed, whereas the unchanged V5 consumer recomputed those four digests
without that byte. The attempt issued no `sacct` query, read no scheduler row,
did not access the V5 output namespace or any shard, environment, log, or
support result, and created no V7 diagnostic, manifest, intent, receipt, job,
or output. The amended V7 is frozen before the first scheduler-reaching V7
diagnosis. It starts a distinct, prospectively frozen provenance chain before
any repair or source/support-outcome inspection. Scheduler membership is its
sole observed operational outcome and affects only which campaign executes a
fixed inventory record.
The disclosed counts and row-2 event are historical context, not diagnostic
acceptance criteria. V7 recomputes the state counts from one fresh exact
820-row snapshot and applies only the generic rule below.

## Scheduler-only partition

The complete V7 protocol, producer, launcher, consumer, Slurm template, and
adversarial tests must be reviewed and committed before `diagnose-v5`. That
command first performs a descriptor-safe prediagnosis freeze of the exact
committed design boundary. If the scoped `jj` diff is nonempty, a file is not
tracked at `@-`, a byte changes while being hashed, or the repository identity
changes across the double check, diagnosis aborts before V7 diagnosis
re-accesses a V5 launch artifact or scheduler row, and before it accesses any
V5 output name or byte.

Diagnosis then validates the committed frozen V5 intent, receipt, code,
environment, Slurm template and V4-to-V5 diagnostic chain without touching its
output namespace. A V7-local compatibility wrapper temporarily supplies the
historical producer's canonical-JSON-plus-line-feed encoder to the unchanged
V5 diagnostic validator and restores the original consumer binding on both
success and failure. No V5 predicate is copied, removed, or relaxed, and no
V5/V6 byte is changed. The same wrapper encloses the unchanged V6 utility when
the dedicated V7 consumer independently replays V5 producer ancestry. It takes
the launch identity from that authenticated V5
receipt and performs no separate live launch-journal query. It then reads
exactly 820 expanded V5 array rows from raw, pipe-delimited `sacct` output. The
only V7 diagnostic scheduler query requests `JobID`, `State`, `ExitCode`, and
`Partition`. Rows must be in array-index order, name one recognized
unsuffixed Slurm terminal state, use an exact `major:signal` exit code, and name
partition `fat`. Active states, unknown states, compressed arrays, steps,
annotations such as `CANCELLED+`, missing or duplicate rows, and malformed
fields abort. It neither requests nor stores elapsed time, memory use, node
identity, or any other task-difficulty proxy.

The partition rule is deliberately independent of failure cause:

- a shard is reusable if and only if its row is exactly `COMPLETED` with exit
  `0:0`;
- every other recognized terminal row, with any syntactically valid exit code,
  belongs to the repair set; and
- the two sorted, unique sets must be disjoint and have exact union
  `range(820)`.

V7 does not request step-level resource accounting, enumerate the V5 output
directory, open or parse any V5 log, classify a failure, infer a source identity
from a log, decode a V5 shard, or consult a support outcome during diagnosis. It
records the complete parsed and normalized row set, the repair-row subset, their independent
digests, and explicit negative attestations for all prohibited observations.
Launch likewise never enumerates or reads the V5 output namespace: it rebuilds
the inventory deterministically from the frozen benchmark revision and requires
the resulting digest to equal the one in the authenticated V5 launch receipt.

The canonical diagnostic is exclusively created. Every later V7 command
revalidates its exact schema, index partition, scheduler rows and digests,
fixed resource profile, launch ancestry, and prediagnosis byte freeze. A
malformed `COMPLETED 0:0` triplet aborts at seal instead of being moved
adaptively into the repair set.

## Fixed maximum profile

Every repair shard uses one profile fixed before V7 diagnosis after the
disclosed operational telemetry. No row-specific state, exit code,
index, task identity, source property, or scientific outcome selects among
profiles:

- partition `fat`, normal QoS, the frozen CPU account, one node, one task, and
  one CPU;
- 3000 GiB total memory via `--mem=3000G`;
- a three-day job limit via `--time=3-00:00:00`;
- 115,200 seconds per candidate;
- `--nice=0`, `--no-requeue`, and `--export=NONE`; and
- the exact sparse repair array with no `%` concurrency throttle.

The known fat-node geometry is 3,095,813 MiB; the 3,072,000-MiB request stays
23,813 MiB below that ceiling. Each array element reruns its complete original
two-candidate shard in the isolated V7 output and TMP namespaces. Partial V5
files and all V1--V4 files are unusable. If any V7 repair element is not
`COMPLETED 0:0`, sealing fails closed; there is no outcome-dependent exclusion,
partial recovery, retry wave, or resource escalation inside V7.

The larger timeout changes only an infrastructure ceiling. The frozen producer
raises `InfrastructureAuditError` when the translator reaches its timeout and
does not publish a valid completed shard. Its only accepted translation
statuses are `success` and `input-rejected`; neither status denotes a timeout or
application failure. Consequently, every scheduler-reusable V5 shard contains
two valid non-timeout translator outcomes under the 28,800-second V5 ceiling,
while every V7 repair shard must contain two such outcomes under the
115,200-second V7 ceiling. V7 imports the exact V5 semantic producer,
normalization, support-classification and split code and changes only the
isolated campaign namespace and infrastructure ceiling. The diagnostic, launch
materials, execution receipt and strict consumer bind these accepted classes
and assert that the ceiling change introduces no accepted outcome class.

## Launch, recovery, and mixed seal

After the scheduler-only diagnostic is reviewed and committed,
`prepare-manifest` binds the complete V5 producer closure, V5 launch ancestry,
the imported committed V6 recovery/streaming implementation, the V7 diagnostic,
every V7 source, protocol, consumer, template and test, the complete executable
A/direct/B downstream design, and the manuscript renderer and submission
checker. These downstream files are also in the prediagnosis closure, so the
known scheduler index membership cannot change scientific selection or claim
logic. The V7 template has exactly two render tokens: the manifest digest and
fixed timeout. Launch
validates the manifest against the prediagnosis freeze, requires every scoped
file committed at `@-`, exclusively creates mode-0700 V7 output and TMP roots,
publishes independently rebuilt canonical inventory bytes whose digest equals
V5's pinned digest, publishes an intent, and submits the
in-memory hash-bound program to pinned `/usr/bin/sbatch`. The full sparse array
and every resource are repeated on the options-only command line. The launch
is unthrottled.

The prediagnosis and code manifests bind this complete design at the V7
producer revision. Consumers validate those historical bytes from the pinned
Jujutsu revision instead of requiring every descendant working-copy byte to
remain unchanged forever. Only after V7 seals may downstream freeze constants,
the result renderer and manuscript source evolve to bind and report real
outcomes; each descendant freeze retains the V7 producer revision and hashes.
The base semantic producer and inventory modules executed for live replay are
still checked against their pinned manifest bytes. Changing either semantic
module requires a new source campaign, not a descendant edit.

`recover-launch` can reconstruct one missing receipt from exactly one matching
submission-journal entry and can never resubmit. `status` parses the expanded
V7 array with the same raw row discipline. Seal requires all repair rows and
their exact resource-contract rows to be `COMPLETED 0:0`.

Only after both the minimal row gate and exact detailed V7 resource-contract
rows establish `COMPLETED 0:0` for every repair does seal read output bytes. It
uses a descriptor-relative, no-follow streaming reader to open exactly the V5
shard, environment, and successful log names selected by the scheduler rule.
It never lists the V5 output directory or opens a noncompleted V5 path. Every
selected leaf is streamed and hashed twice; file, root, and ancestor identities
are rechecked to detect mutations and replacement races. Seal validates these
V5 reusable triplets, including each success log's exact manifest-check,
inventory-task and output-path transcript, and the exact V7 repair namespace.
It constructs an exclusive
820-shard union in inventory order, and records each origin as `v5-completed` or
`v7-repair`. It reparses only validated union copies, reruns
the frozen population assembly and A/B split, requires the resulting record
sequence to match the independently frozen pre-union sequence, and rehashes the
V5, V7, and union trees before receipt publication.

The reusable V5 shard, environment and successful-log bytes were not
externally or contemporaneously committed when V5 completed; their selected
tree is first separately recorded by the digest published at V7 seal. That
same-workspace record is not itself an external witness. V7 verifies the
authenticated V5 launch, code, inventory and root identities, scheduler
success, environment-to-shard/log consistency, and live semantic replay.
Those checks reject accidental drift and incoherent tampering, but cannot
cryptographically exclude a coherent same-UID replacement made before the
sealed artifacts receive their content-addressed post-seal commit. This is an
explicitly bound integrity limitation, not evidence of outcome-based
adaptation. A full V7 rerun would remove this historical-authenticity
limitation.

V7 controller publications and private-root creation use retained directory
descriptors, no-follow component walks, exclusive creation, and final
inode/byte or directory-chain checks. This does not claim containment against
an active same-UID adversary on compute-node task paths: Slurm-opened standard
output and the shell's TMPDIR, snapshot, and cleanup operations remain
pathname-based. Their stability therefore assumes that no concurrent same-UID
process mutates those pathnames. Later provenance checks are intended to fail
closed on incoherent mutation, but they neither replace this operational trust
assumption nor exclude the coherent-replacement limitation above. The exact
boundary is recorded as `path_containment_trust_model` in the diagnostic,
launch record, and execution receipt.

Immediately after a successful seal, and before any discretionary outcome
analysis or paper claim, the operator must commit the execution receipt,
attestation and five seal-stage records with `jj`. The sealed revision should
then be archived or uploaded when practical to add an external witness. No
same-workspace seal receipt is described as an external commitment.

Seal retains V6's explicit crash-recovery design under a private, byte-pinned
runtime instance: seal plan, union-root, union, candidate, and attestation
stages are canonical, exclusive, and independently digested. `seal` rejects
any preexisting partial state. `recover-seal` accepts only a byte-identical
prefix of that deterministic chain, fills missing publications, and never
overwrites. An unmarked union root is recoverable only while empty.

The source audit records no runtime estimand. Downstream selection consumes only
validated translation/support classifications; campaign origin, timeout,
elapsed time and resource use remain provenance, and no cross-campaign runtime
comparison is authorized. Because timeout is an infrastructure exception rather
than a valid classification, the two ceilings do not define different accepted
measurement classes. Therefore scheduler-dependent execution origin does not
alter population membership, predictor or analysis choices, or inclusion when
all 820 shards validate.

The execution receipt exposes `campaign = v7-selective-repair`, `v7_job_id`,
`v7_code_manifest_sha256`, `v7_output_tree`,
`v7_repair_environment_manifest`, exact V5 reuse/repair lists, the scheduler-
only diagnostic policy and digest, exact resource rows, one union ledger entry
per index, stage-chain digests, cohort hashes, counts, support exclusions, and
the final source attestation. A dedicated V7 consumer independently recomputes
this chain. V5 and V6 consumers remain unchanged and cannot accept V7.

## Operational order

1. Review, test, and commit all prediagnosis V7 files without a scheduler query
   or any V5 output/log inspection.
2. Run `diagnose-v5` once. Review and commit its canonical scheduler-only
   diagnostic without opening logs or decoding shards.
3. Run `prepare-manifest`, rerun local V7 tests, and commit the manifest-bound
   empty launch namespace.
4. Run `launch` once and monitor only at the authorized cadence. If submission
   succeeded but the receipt was lost, use `recover-launch`.
5. After the exact sparse array is terminal, run `seal` once. Use
   `recover-seal` only after an interrupted partial seal. Any failed repair or
   provenance mismatch ends V7 without an execution receipt.
