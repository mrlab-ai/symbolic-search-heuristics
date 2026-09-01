# Universal unseen-source audit: prospective V6 selective repair

Campaign V6 is a prospective, outcome-blind repair of terminal campaign V5.
It does not retroactively alter or seal V5: V5's original-only seal and its
disabled recovery entry point remain unchanged. V6 creates a new provenance
chain and may reuse a V5 shard if and only if its ordered scheduler row is
`COMPLETED` with exit `0:0`. Every other accepted infrastructure row is rerun
as its complete original two-candidate shard in a separate V6 namespace.
No V1--V4 shard and no partial file from a noncompleted V5 task is usable.

V6 changes no inventory record, source byte, benchmark revision, translator,
normalization strategy, support rule, split seed, cohort rule, or support
floor. Its repair producer privately loads the frozen V5 implementation and
changes only the output/TMP namespace, campaign evidence schemas, manifest,
and the one prespecified infrastructure timeout selected below.

## Outcome-blind terminal diagnostic

The V6 protocol and diagnostic producer must be reviewed and committed before
the first terminal V5 diagnosis. While V5 is active, only the separately
authorized hourly status command may be used. After all 820 V5 array rows are
terminal, `diagnose-v5` performs the following operations in order:

1. before any namespace check, V5 artifact access, scheduler query, log read,
   or tree walk, freeze the exact V6 source boundary except for the not-yet-
   created diagnostic itself. The freeze requires an empty scoped `jj` diff
   at `@`, requires every path to be tracked at `@-`, records the `@-` commit
   ID and pinned `jj` executable, hashes each exact file descriptor-safely,
   and repeats the repository-state queries after hashing. Any difference
   across the two checks aborts;
2. validate the immutable V5 launch intent, launch receipt, code manifest,
   source-inventory hash, and complete expanded scheduler row set;
3. partition indices using scheduler state only: exactly `COMPLETED 0:0` is
   reusable, and the repair set is its exact complement;
4. inspect detailed accounting and logs only for noncompleted tasks, accepting
   only an exact 28,800-second empty-stderr producer timeout, scheduler OOM
   with translator exit -9 and scheduler OOM-kill evidence, or a recognized
   scheduler interruption (`BOOT_FAIL`, `NODE_FAIL`, `PREEMPTED`, or
   `REVOKED`);
5. choose one uniform V6 resource profile from those infrastructure classes;
   and
6. descriptor-safely hash the complete V5 output tree as opaque bytes and
   require every inspected failure-log path, byte count, and SHA-256 digest
   to name the same file in that frozen tree.

Step 6 does not decode a successful shard or read a successful log for
meaning. The diagnostic records that successful files were only integrity
hashed, that no source-support outcome was consulted, and that any shard or
environment file from a noncompleted task is quarantined. The diagnostic is
canonical and exclusively created. Its ordered scheduler rows, reuse and
repair index lists, failure records, resource mapping, root identity, and
every output-file hash are independently digested. Reloading the diagnostic
revalidates its exact schema, its pre-diagnosis file hashes, and every failure
log against the stored opaque tree before any later V6 action. The eventual
V6 code manifest must contain the identical hashes for every pre-diagnosis
file; `prepare-manifest`, launch preflight, and launch-material reconstruction
all enforce that relation.

V6 never uses V5's state-normalizing scheduler helper. Its scheduler and
resource-accounting readers parse the raw pipe-delimited `sacct` output with
exact row count, order, array identity, `fat` partition, allowed unsuffixed
state spelling, `ExitCode`, and `Elapsed` syntax. Detailed failure accounting
admits only the array parent and the optional `.batch` and `.extern` steps,
in fixed order without duplicates. The parent row must exactly reproduce the
state, exit, elapsed time, and `2T` request in the terminal scheduler row.
Its `JobIDRaw` fixes one digit-only or array-form allocation root with no step
suffix; every present step must use that exact root plus its matching `.batch`
or `.extern` suffix, both at diagnosis and on diagnostic reload.
Unknown rows, suffixed states such as `CANCELLED+`, whitespace annotations,
compressed arrays, or malformed/unknown fields abort.

Tree inventories use V6's descriptor-relative, no-follow streaming reader.
It hashes bounded chunks, retains only file metadata and digests, hashes every
leaf twice, relists every directory, and rechecks open descriptors and the
complete ancestor chain. Symlinks, special files, replacement races, or any
file/directory mutation abort; complete file payloads are never retained as a
tree-wide in-memory collection.

Unknown states, active rows, application exits, cancellation without a prior
prospective authority, malformed failure evidence, missing completed triplets,
extra output paths, or any source/provenance mismatch abort V6. A scheduler
`COMPLETED 0:0` row with a malformed shard or environment attestation also
aborts the entire selective-repair route at seal; it is not added adaptively
to the repair set.

## Deterministic resource ceiling

The mapping depends only on the classified infrastructure set and applies
uniformly to every repair shard; task identity, family, support, and source
outcomes are never inputs.

- Without a classified scheduler OOM, retain V5's one CPU and 2 TiB per CPU.
  With any classified scheduler OOM, request 3000 GiB total (`--mem=3000G`)
  on the fixed one-CPU task and one fat node. The frozen node geometry is
  3,095,813 MiB, so 3000 GiB equals 3,072,000 MiB and leaves 23,813 MiB below
  the schedulable-node ceiling.
- Without a classified producer timeout, retain the 28,800-second
  per-candidate timeout and `16:40:00` shard limit. With any exact producer
  timeout, use the one fixed ceiling profile: 115,200 seconds per candidate
  and the fat partition's `3-00:00:00` limit. Two candidates can consume at
  most 64 hours of translator time, leaving eight hours for setup,
  normalization, attestation, and cleanup.
- Keep partition `fat`, normal QoS, the frozen account, one node, one task,
  one CPU, `--nice=0`, `--no-requeue`, and `--export=NONE`. Submit the exact
  sparse complement with no `%` array throttle.

This is a terminal resource ceiling, not an exclusion rule. The existing
worker safely reports its own producer timeout as infrastructure exit 75, but
a scheduler/cgroup OOM can kill the complete array element before publication.
V6 therefore cannot safely turn either event into an `unsupported` candidate.
Sealing requires every repair element to be `COMPLETED 0:0`. If any repair
element reaches the fixed memory/time ceiling or otherwise fails, V6 fails
closed. The next permissible step is a separately prospective V7 on larger
hardware, or a prospectively justified population redesign before inspecting
source outcomes; no child-level exclusion, partial shard, retry wave, or
fallback to an earlier campaign is authorized.

## Launch and one-shot provenance

After the terminal diagnostic is reviewed and committed, `prepare-manifest`
creates a V6 code manifest that expands the complete V5 producer boundary and
binds the V5 launch artifacts, V5 terminal diagnostic, V6 producer, launcher,
Slurm template, protocol, and tests. The Slurm template contains only two
tokens. Launch renders the manifest hash and diagnostic-selected timeout in
memory, hashes the exact rendered bytes, and supplies them to hash-pinned
`/usr/bin/sbatch` on standard input. Every resource and the exact sparse array
is repeated on the options-only command line.

Launch exclusively creates mode-0700 V6 output and TMP roots, copies the exact
V5 inventory bytes into the V6 output root, records root device/inode/mode/uid,
and publishes an intent before submission. Job name, comment, submission
token, exact `SubmitLine`, full sparse array, program hash, code/environment
hashes, diagnostic hash, exact frozen-inventory benchmark revision, and
committed producer revision are bound in the launch receipt. Before creating
either root, launch validates the committed
producer boundary and code manifest and requires a fresh opaque hash of the
complete V5 output tree to equal the terminal diagnostic. `recover-launch`
may reconstruct a missing receipt from one
unique journal entry but can never resubmit.

The Slurm program is not accepted merely because its two render tokens are
present. V6 pins the SHA-256 digest of the complete unrendered template and
requires the exact singleton lines that define its shell mode, argument
contract, inventory digest, absolute output/TMP paths, controlled environment,
array-index range, timeout alternatives, manifest token, and complete scan
command and options. It rejects `#SBATCH` directives, extra token occurrences,
positional runtime inputs, and destructive cleanup. Launch then binds the
digest and byte count of the exact in-memory rendered program submitted on
standard input.

Each repair element uses a fresh project-backed task TMPDIR keyed by V6 job
and original shard index. It writes one complete shard and task-environment
attestation to the V6 output root. Publication is exclusive; V5 files are
never overwritten, moved, or deleted.

## Fail-closed mixed seal

Seal is permitted only after every exact V6 repair index is terminal. It:

1. requires all repair rows and exact resource rows to be `COMPLETED 0:0`;
2. rehashes the V5 output tree and requires byte equality with the terminal
   diagnostic;
3. for the first time decodes every scheduler-reusable V5 shard and validates
   its V5 code header, two frozen inventory records, snapshot evidence, task
   environment, shard hash, and successful Slurm-log hash;
4. validates every V6 repair shard and environment under the selected V6
   profile, and requires the V6 TMP root to be empty;
5. constructs an exclusive 820-shard union in inventory order, taking V5
   bytes exactly for reusable indices and V6 bytes exactly for complement
   indices. Immediately before every copy, the origin's byte count and digest
   must equal its frozen V5 or V6 tree record; and
6. parses the verified union copies, reruns the frozen full-population assembly
   and deterministic A/B split, requires its record-sequence digest to match
   the independently frozen pre-union parse, rechecks the exact V5, V6, and
   union trees, and only then publishes the V6 execution receipt.

Seal is an explicit, deterministic, crash-resumable hash chain:

1. `source-audit-seal-plan-v6.json` freezes the launch, terminal rows, exact
   resource rows (including elapsed time), V5/V6 trees, both environment
   manifests, and parsed source-record sequence;
2. `source-audit-union-root-stage-v6.json` binds the newly created union root's
   device, inode, mode, and owner to the plan;
3. `source-audit-union-stage-v6.json` binds all 820 origins and the complete
   union tree to that root stage;
4. `source-audit-candidate-stage-v6.json` binds the candidate assembled from
   those union copies;
5. `source-audit-attestation-stage-v6.json` binds the byte-identical frozen
   attestation to the candidate stage; and
6. the execution receipt binds the digest of every preceding stage.

Every publication is exclusive and canonical. `seal` requires no partial
seal state. After an interruption, `recover-seal` recomputes the deterministic
plan, validates every existing partial artifact byte-for-byte, fills only
missing union shards or later artifacts, and never overwrites anything. A
union root without its marker is recoverable only when still empty. Immediately
before receipt publication, V6 revalidates candidate, attestation, and every
stage in the hash chain, then freshly rehashes the exact V5 tree, exact V6
repair tree, and exact 820-file union. A mismatch at any boundary aborts.
The union retains one root identity, contains zero subdirectories or extra
entries, and must have exactly the expected 820 zero-padded shard filenames
in order with a stable rehash.

The receipt repeats that exact benchmark revision and records both scheduler
campaigns and code manifests, the exact origin of every shard, both
environment manifests, the opaque terminal V5
tree, V6 output tree, union tree, full candidate counts, support exclusions,
prelaunch gate, cohort hashes, and the fact that selective repair was
outcome-blind. Both the V5-reuse and V6-repair environment records bind their
per-index shard, environment attestation, and Slurm-log path and digest. Its
normalized partition fields are
`logical_shards = 820`, `candidates = 1640`,
`reusable_v5_shard_indices`, `repair_v5_shard_indices`,
`reused_v5_shards`, and `repaired_v5_shards`. The two index lists must be
ascending unique integer lists, disjoint, and have exact sorted union
`range(820)`; their lengths must equal the corresponding counts.
`union_sources` has exactly one entry per index in index order. Each entry
records `shard_index`, origin (`v5-completed` or `v6-repair`), source and
union paths, and both SHA-256 digests; origin must agree with membership in
the two index lists. The flat policy fields record the exact reuse rule,
full-shard repair scope, `whole_campaign_rerun = false`,
`outcome_blind_selective_repair = true`, and
`noncompleted_v5_shards_used = false`.
The additional immutable receipt fields are `pre_diagnosis_freeze`,
`seal_recovery_protocol`, `seal_plan_sha256`,
`union_root_stage_sha256`, `union_stage_sha256`,
`candidate_stage_sha256`, and `attestation_stage_sha256`.

Confirmation A and B remain forbidden until a dedicated V6
consumer recomputes and accepts this complete chain. The existing V5 consumer
must remain strict and unchanged; it must not be relaxed to accept a mixed
seal.

## Prespecified operational order

1. Review, test, and commit the V6 protocol, diagnostic/launch code, producer,
   Slurm template, and tests without reading any V5 runtime output.
2. After V5 is terminal, run `diagnose-v5` once. Review and commit its
   canonical diagnostic without opening successful shards or logs.
3. Run `prepare-manifest`, run the complete V6/local source-audit tests, and
   commit the manifest-bound empty launch namespace.
4. Run `launch` once. Monitor only at the authorized cadence. If the receipt
   is lost after submission, use `recover-launch`; never rerun `launch`.
5. After the exact sparse V6 array is terminal, run `seal` once. If the seal
   process is interrupted after it creates any stage, use `recover-seal`;
   never rerun `seal` over partial state. Any failed repair, changed partial,
   or reusable-triplet validation error ends V6 without a receipt.
