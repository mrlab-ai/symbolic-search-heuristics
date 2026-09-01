# Universal unseen-source audit: campaign-v5 infrastructure amendment

Campaign v5 is a prospective, outcome-blind infrastructure amendment to the
frozen universal source audit. It changes neither the 1,640-candidate
inventory nor source bytes, support definition, deterministic A/B split,
support floors, or prelaunch gate. It reruns all 820 original two-candidate
shards and reuses zero v1, v2, v3, or v4 shards.

Campaign v4 was launched with one CPU, 1 TiB, a 14,400-second translation
limit, an 8:20:00 Slurm limit, and project-backed per-candidate temporary
storage. It ended naturally with 801 `COMPLETED`, ten `FAILED`, and nine
`OUT_OF_MEMORY` array elements, so it cannot be sealed. No task was cancelled,
and no cancellation intent, attempt, or receipt was created. The canonical
terminal diagnostic has SHA256
`165c31105be505b763a1a4d92fb03365272eaf875bcf8c12d3dd85d3516e20fc`.

The ten exact 14,400-second empty-stderr translator timeouts are tasks 147,
150, 484, 486, 487, 489, 715, 721, 724, and 725. Their array elapsed times span
04:00:13--05:10:08; batch MaxRSS spans 349,946,713--984,837,316 KiB and
MaxVMSize spans 354,292,836--1,072,429,040 KiB. The nine scheduler OOMs are
tasks 485, 488, 716, 717, 718, 719, 720, 722, and 723. Their array elapsed
times span 02:00:24--05:33:29; batch MaxRSS spans
1,054,370,899--1,071,622,750 KiB and MaxVMSize spans
1,066,803,356--1,087,451,720 KiB. Every corresponding failed-only log pins
the applicable empty-stderr timeout wrapper or translator exit -9 plus the
scheduler OOM kill.

These are infrastructure facts, not source-support outcomes. No successful
v4 shard, successful Slurm-log content, source-support classification,
candidate attestation, cohort, or gate outcome was inspected or used to define
v5. The complete classified failure set supports the unchanged prospective
amendment: v5 doubles both the 1 TiB allocation and the 14,400-second
per-candidate bound.

The command `diagnose-v4` is permitted only after every v4 array element is
terminal. It reads all 820 scheduler rows, detailed scheduler resource rows
for OOM and producer-timeout elements, and only Slurm logs whose actual state
is `FAILED` or `OUT_OF_MEMORY`. It never opens `COMPLETED` or `CANCELLED`
logs. It rejects active or unknown states before any log is opened and rejects
any terminal failure that is not
exactly a scheduler OOM with translator exit -9 and scheduler OOM-kill
evidence or a 14,400-second producer timeout with exact empty-stderr wrapper
evidence. If cancellation rows exist, the diagnostic first requires the exact
canonical v4 cancellation intent, attempt, and receipt, their committed
producer bytes, pinned whole-parent `/usr/bin/scancel 1865695` argv, and every
cancelled task's full accounting rows. The canonical diagnostic binds the
ordered scheduler-row hash,
every failed task and log hash, OOM and timeout accounting evidence, all
amendments, the all-820 full-rerun decision, and the exact v4 launch intent,
receipt, code manifest, and Slurm bytes. Launch recomputes this diagnostic and
rejects any mismatch.

All v5 evidentiary reads use the v5 safe-I/O helper. It walks every ancestor
from `/` with retained directory descriptors and `O_NOFOLLOW`, rejects
special files
before a potentially blocking read, opens the final regular file once, reads
and hashes through that same descriptor, and compares both descriptor and
pathname identities before and after use. Canonical JSON, code and inventory
manifests, the Slurm program, failed diagnostic logs, benchmark snapshots,
shards, task attestations, requirements, tool binaries, and output trees all
use this path. A relative input paired with a canonical absolute root is
interpreted relative to that root, including the exact relative code-manifest
path used by Slurm. Noncanonical roots and symlinks or replacements above the
declared root are rejected. Recursive translator and output-tree enumeration
retains every verified directory descriptor, opens leaves descriptor-relative,
then rehashes leaves and relists the same directory descriptors before close.
No inherited pathname-based reader is called. Race tests cover a final
symlink, ancestor/above-root symlinks, FIFO, callback mutation, inode and
same-inode content replacement, and injected tree entries.

Campaign v5 keeps one CPU, normal QoS, the `fat` partition, and account
`naiss2025-5-561-cpu`. It doubles the evidenced memory request to 2 TiB, the
per-translation limit to 28,800 seconds, and the Slurm limit to 16:40:00.
The partition permits up to three days, so this wall-time request is within
the scheduler contract. Each fat node currently exposes 3,095,813 MiB, so the
2-TiB request permits at most one v5 task per node and leaves roughly 975 GiB
unallocated for other work. This is a scheduler packing consequence, not an
agent-imposed concurrency cap. The campaign submits the unthrottled array
`0-819`, uses `--nice=0`, `--no-requeue`, and
`--export=NONE`, and supplies all resource options again on the hash-pinned
`/usr/bin/sbatch` command line.

The Slurm program takes zero arguments and embeds the fixed inventory hash and
output path. The launcher validates its complete bytes before writing the
intent, binds stdin mode, byte count, and SHA256 in that intent, revalidates
the bytes immediately before submission, and passes those in-memory bytes on
standard input to `/usr/bin/sbatch`. The submission command contains only
`sbatch` options: it contains neither a Slurm pathname nor positional
inventory/output arguments. Recovery and ordinary receipt loading require the
submission journal to contain the exact options-only `SubmitLine`, tokenized
job name/comment, complete array, and the same job ID as the receipt. All
live-status, submission-journal, and sealing resource queries pass sacct's
`--array` flag and reject a compressed range, so pending tasks are expanded to
the exact 820 identities instead of making live status spuriously fail.

Launch creates both the output directory and shared temporary root with mode
0700. It rejects direct or ancestor symlinks and binds each canonical absolute
path, uid, mode, device, and inode in the intent and launch receipt. Each array
task attests the output-directory identity before and after scanning. Seal
requires those identities, the live identity before and after assembly, and
the launch identity to be equal; the output-tree digest and execution receipt
also include the root identity.

Each array task receives exactly one mode-0700 directory named
`task-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}` below the unique v5 data
root in `/nobackup/proj/disk`. The wrapper sets both `TMPDIR` and Python's
cache prefix inside that directory. The Python producer verifies the absolute
path, absence of direct/ancestor symlinks, Slurm identity, owner, mode,
device/inode stability, emptiness, live root identity, and
`tempfile.gettempdir()` before translation. Seal cross-checks every attested
live root identity against the launch identity. Thus the translator's
temporary working directory and `output.sas` are on project storage rather
than node `/tmp`. It emits a canonical task-environment attestation binding
those facts, the output-root identity, shard hash, code/environment identities,
and pinned Python, `sha256sum`, `mkdir`, and `rmdir` tools. An EXIT trap removes
only the exact empty task directory using pinned `/usr/bin/rmdir`; no recursive
deletion is present. Cleanup failure makes the array element fail.

Before each candidate translation, v5 reads and hash-verifies the frozen
domain and problem once and creates a private miniature source tree inside the
exact task `TMPDIR`. Directories have mode 0700 and files mode 0400. The frozen
scanner receives that miniature tree, so both the translator and
`axiom_based` normalization resolve the same snapshot paths. The wrapper
checks file identity and SHA256 immediately before each applicable consumer
and again after use, records canonical per-candidate snapshot evidence in the
shard, then unlinks only the exact files and removes only the exact directories
with `rmdir`. Assembly rejects missing or changed snapshot evidence.

The v5 manifest directly binds all 24 v4 manifest-bound producer files, the v4
code manifest and Slurm script, the exact v4 launch intent and receipt, the
sealed v4 infrastructure diagnostic, the v5 safe-I/O helper, cancellation
module/protocol/tests, and every new v5 producer/protocol/test file. Optional
cancellation intent/attempt/receipt files are not static manifest inputs. If
cancellation was used, the manifest-bound terminal diagnostic transitively
binds their exact bytes and hashes; natural completion requires no such files.
The source inventory must have the same pinned canonical SHA256 as v1--v4 but
is regenerated in the fresh v5 namespace.

Recovery shard substitution is disabled. Sealing requires all ordered
original tasks 0--819 to be `COMPLETED` with exit `0:0`, and independently
binds the actual account,
partition, QoS, CPU count, 2 TiB request, time limit, job name, state, and
exit code. It requires exactly one original shard, one task-environment
attestation, and one Slurm log per array task; verifies all task temporary
directories were removed, the shared root is empty, and the launch root
identities remain exact; assembles directly from the original v5 shards; and
rechecks the root-bound complete tree before publishing the source attestation
and execution receipt. Any failure, timeout, OOM, missing/extra path,
provenance mismatch, or failed source-support gate fails closed. Confirmation
A and B remain forbidden unless the sealed v5 source audit authorizes their
exact source-disjoint cohorts.

Prospective cancellation is governed separately by
`pdb_terminal_incidence_confirmation_source_audit_v4_cancellation_v5_protocol.md`.
The branch was not exercised: v4 reached its natural terminal state before an
intent was prepared, and all three optional cancellation artifacts are absent.
The prespecified sequence would have been `prepare-cancel-intent`, a
path-scoped Jujutsu commit, then `cancel-v4`. Tasks could have advanced while
the intent was being committed: active rows could have remained active or
completed successfully, while new failure/OOM instances after intent creation,
cancellation, or unknown states would have been rejected. Every actual
pre-intent timeout/OOM would have been pinned in the intent; the
thirteen instances known when the contingency was frozen remain fixed in
source, while the terminal diagnostic dynamically binds the complete set of
nineteen failures. The intent snapshot and final pre-cancel snapshot would
have been separately bound. A durable attempt marker would have preceded the
one exact parent cancellation, and recovery could only determine a receipt; it
could never reissue `scancel`, resubmit, or selectively cancel.

Operational order after v4 has become terminal, preferably naturally:

1. Run `diagnose-v4`; if and only if cancellation rows exist, it first
   validates the cancellation intent, attempt, and receipt. Review and commit
   the canonical diagnostic with the v5 producer files.
2. Run `prepare-manifest`. It exclusively creates the v5 code manifest from
   exact regular, non-symlink inputs only after recomputing the terminal v4
   diagnostic and verifying the normalized Slurm template. Replace the one
   64-zero manifest placeholder in the Slurm script with the reported digest,
   rerun all tests, and commit the empty launch namespace.
3. Run `launch` once. Do not inspect successful shard or support contents.
4. Monitor scheduler state only. Run `seal` only after all 820 tasks are
   terminal; it succeeds only for 820 original `COMPLETED 0:0` tasks.
