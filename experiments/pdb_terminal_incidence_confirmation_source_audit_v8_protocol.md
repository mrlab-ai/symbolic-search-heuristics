# Universal unseen-source audit: prospective V8 scheduler-profile repair

Campaign V8 is a new execution namespace for the exact 25-shard repair set
selected by campaign V7. It does not diagnose V5 again and does not consume a
V7 task output. Its scientific population, translation and normalization code,
support classification, split, accepted outcome classes, per-candidate timeout,
job duration, partition, account, QoS, CPU count, and unthrottled sparse array
are unchanged. Relative to the rejected V7 submission, V8 changes only the
uniform Slurm memory request from 3000 GiB to 2950 GiB.

## Why V8 exists

V7 exclusively published its launch intent and created its private output and
TMP roots, but its one allowed `sbatch` invocation returned the launcher's
generic error before a job identifier was received. Exact recovery found zero
matching jobs and never resubmitted. The V7 output root contains only its
independently rebuilt source inventory, its TMP root is empty, and no Slurm
log, task environment, or task shard exists. V7 is therefore a failed launch,
not an execution origin, and its namespace remains immutable.

The original V7 launcher captured standard output and error in memory but did
not persist them on its error path. Its exact original exit status and error
stream are unavailable. The later resource diagnosis is explicitly a post-hoc
reconstruction rather than original submission evidence. It used scheduler
configuration, association and QoS limits, queue state, and non-submitting
`sbatch --test-only` calls; it read no V5 output, environment, log, shard, or
source-support classification.

That diagnosis established:

- fat-node `RealMemory` is 3,095,813 MiB;
- `MemSpecLimit` reserves 65,536 MiB, leaving 3,030,277 MiB allocatable;
- V7's 3000-GiB request is 3,072,000 MiB and exceeds the allocatable value by
  41,723 MiB;
- an exact non-submitting reconstruction of V7's profile was rejected with
  `Requested node configuration is not available`; and
- changing only memory to 2950 GiB, or 3,020,800 MiB, was accepted for
  scheduling estimation on an idle fat node, leaving 9,477 MiB headroom.

The committed V7 failure record binds these facts and distinguishes the later
diagnosis from the unpreserved original error stream.

## Immutable scientific partition

V8 consumes the committed V7 scheduler-only diagnostic with SHA-256
`9ddb5f19ccc05f4d48e037f2175feaebdb548a053430865faf540979f77c9110`.
It requires its exact 795 reusable V5 indices, exact 25 repair indices, all
embedded row and list digests, authenticated V5 ancestry, and V7 prediagnosis
freeze. The repair indices are

`2,64,129,132,147,150,199,459,484,485,486,487,488,489,715,716,717,718,719,720,721,722,723,724,725`.

V8 has no `diagnose-v5` command. Its disabled internal compatibility entry
fails before any scheduler query. Loading the partition replays V7's recorded
diagnostic validator and checks the exact V7 diagnostic, code-manifest, launch-
intent, and failure-record hashes. It never issues a new V5 accounting query.

All downstream scientific and manuscript files frozen before V7 observed the
scheduler partition retain their V7 prediagnosis hashes. The V8 manifest adds
only V8 infrastructure files and the committed V7 provenance artifacts. At
launch, every manifest input and the manifest itself must be committed, and
the V7 frozen subset must still match exactly.

## Fixed V8 profile

Every one of the 25 repair shards receives the same profile:

- account `naiss2025-5-561-cpu`, partition `fat`, and normal QoS;
- one node, one task, and one CPU;
- total memory `--mem=2950G`;
- job limit `--time=3-00:00:00`;
- 115,200 seconds per candidate;
- `--nice=0`, `--no-requeue`, and `--export=NONE`; and
- the exact sparse array with no `%` concurrency throttle.

Each array element reruns its complete original two-candidate shard in the
isolated V8 output and TMP namespaces. No row-specific state, exit code, task
identity, source property, support result, or scientific outcome selects a
resource profile. The sole change from V7 is the scheduler-valid fixed memory
ceiling. If any V8 element is not exactly `COMPLETED 0:0`, sealing fails
closed. V8 has no partial recovery, outcome-dependent exclusion, or resource
escalation.

The accepted translation statuses remain only `success` and
`input-rejected`. A translator timeout remains an infrastructure failure and
cannot be published as a completed shard. The memory correction therefore
does not add an accepted scientific outcome class.

## Launch evidence and recovery

Launch validates the committed V7 lineage, V8 manifest, rendered two-token
Slurm program, rebuilt inventory, and scoped repository revision before any
submission. After creating the isolated roots and rebuilt inventory, it opens
both capture leaves descriptor-relatively with `O_RDWR|O_CREAT|O_EXCL`,
`O_NOFOLLOW`, and `O_CLOEXEC`. Each new leaf is immediately changed from 0600
to 0400 and fsynced. V8 then verifies that both path entries and retained file
descriptors identify distinct regular files owned by the launcher, with link
count one and size zero, and fsyncs the retained parent directory. A collision
on either capture path aborts before intent publication and before `sbatch`.

The intent binds each capture's exact absolute path, device, inode, mode, UID,
GID, link count, and historical `bytes_at_intent=0`. The two leaf descriptors
and every no-follow ancestor descriptor remain open through submission. Each
leaf also carries an exclusive open-file-description lock inherited by the
child redirection. The 0400 pathnames cannot be newly opened for writing, but
the already-open file descriptions remain writable; pinned `/usr/bin/sbatch`
therefore writes its standard output and error directly to them. No controller
pipe or in-memory capture is interposed.

After `sbatch` returns or raises a structured OS error, V8 fsyncs and reads the
arbitrary binary streams from the retained descriptors, while rechecking the
path/descriptor identity, mode, link count, final size, parent chain, and byte
hash. It exclusively publishes a canonical result while those descriptors
remain retained. The result binds initial and final identities, exact byte
lengths and hashes, the intent hash, command hash, rendered-program hash,
process return code or structured OS error, strict parsed job identifier, and
whether the launcher accepted the response. No byte is reconstructed,
decoded for storage, or normalized. A direct launch receipt is possible only
for exit code zero and a single strict parsable job identifier, and it binds
the mandatory result-record digest.

`recover-launch` never invokes `sbatch`. If a controller crash left an intent
and the two capture files but no result, recovery reopens only the exact
intent-bound inodes, without following any path component, fsyncs and reads
their current bytes, and exclusively publishes a result whose process kind
states that the controller return code is unavailable. Recovery must first
acquire each exclusive lock through a new read descriptor; failure means the
original child may still be writing and aborts the attempt. This recovered
result is published before the submission journal is queried. Recovery can then
publish a receipt only for exactly one journal parent whose name, comment,
command and complete sparse array match the immutable intent; any parsed job
identifier in the capture must agree. The result record is mandatory for both
direct and recovered receipts. Zero, multiple, colliding, incomplete, missing-
capture, or identity-swapped states abort without resubmission. A crash may
therefore leave a permanently burned partial namespace, but cannot lose bytes
already written to the capture inodes or silently create a second job.

## Mixed seal

`status` authenticates the committed V8 launch metadata and queries only the
matching V8 journal and scheduler rows; it reads no task payload, environment,
or task log. Seal first requires all 25 rows to be `COMPLETED 0:0`; detailed
V8 resource accounting and every output read remain unreachable before that
gate. It then:

1. descriptor-safely opens exactly the V5 triplets selected by the immutable
   V7 scheduler rule;
2. validates the complete V8 repair tree and its exact successful logs,
   environment records, inventory, manifest and resource contract;
3. forms an exclusive 820-shard union in inventory order with origins exactly
   `v5-completed` and `v8-repair`;
4. reparses the union, reruns population assembly and the frozen A/B split,
   and checks the independently frozen record sequence; and
5. rehashes the selected V5 tree, V8 tree, union, candidate and attestation
   before publishing the execution receipt.

V7 contributes zero shards and no runtime byte to this union. Its intent and
failure record are provenance only. The source audit records no runtime
estimand, and no cross-campaign runtime comparison is authorized.

The historical V5 reusable bytes retain the limitation already disclosed by
V7: they were not contemporaneously externally committed when V5 completed.
Their selected tree is first separately recorded at V8 seal. V8's controller
publications use descriptor-relative, no-follow operations, while compute-node
stdout, TMP, snapshot and cleanup pathnames assume no concurrent same-UID
mutator, exactly as in V7.

## Operational order

1. Review and test all V8 files, with the committed V7 diagnostic, intent and
   launch-failure record unchanged.
2. Generate the V8 code manifest with `prepare-manifest`, rerun all V8,
   downstream, renderer and submission tests, and commit the manifest-bound
   empty V8 launch namespace.
3. Run `launch` once.
4. If and only if a submission may have succeeded without a receipt, run
   `recover-launch`; it cannot resubmit.
5. Poll the V8 job at the authorized hourly cadence.
6. After the exact sparse array is terminal, run `seal` once. Use
   `recover-seal` only for a byte-identical interrupted seal prefix.
7. Immediately commit the execution receipt, attestation, launch captures and
   seal-stage records before discretionary outcome analysis, then add an
   external archive witness when practical.
