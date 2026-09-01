# Universal unseen-source audit: campaign-v4 infrastructure amendment

Campaign v4 is a prospective, outcome-blind infrastructure amendment to the
frozen universal source audit. It changes neither the 1,640-candidate
inventory nor source bytes, support definition, deterministic A/B split,
support floors, or prelaunch gate. It reruns all 820 original two-candidate
shards and reuses zero v1, v2, or v3 shards.

Campaign v3 was launched with one CPU, 512 GiB, a 7,200-second translation
limit, and a 4:10:00 Slurm limit. It cannot be sealed because compute-node
temporary storage filled while the translator serialized `output.sas`, array
tasks exhausted the 512 GiB allocation, and translations reached the
7,200-second producer limit. The timeout failures are separated into pure
timeouts with empty translator stderr and timeouts whose captured stderr also
shows compute-node ENOSPC while serializing SAS output. No successful v3
shard, Slurm-log content, source-support classification, candidate
attestation, cohort, or gate outcome may be inspected or used to define v4.

The command `diagnose-v3` is permitted only after every v3 array element is
terminal. It reads all 820 scheduler rows, detailed scheduler resource rows
for OOM and producer-timeout elements, and only the Slurm logs of non-success
elements. It rejects active elements and any terminal failure that is not
exactly a direct `output.sas` ENOSPC failure, a scheduler OOM with translator
exit -9, a producer timeout with the exact empty-stderr wrapper evidence, or a
producer timeout whose exact wrapper evidence also contains the SAS-output
ENOSPC trace. Its canonical diagnostic binds the ordered scheduler-row hash,
every failed task and log hash, OOM and timeout accounting evidence, all
amendments, the all-820 full-rerun decision, and the exact v3 launch intent,
receipt, code manifest, and Slurm bytes. Launch recomputes this diagnostic and
rejects any mismatch.

Campaign v4 keeps one CPU, normal QoS, the `fat` partition, and account
`naiss2025-5-561-cpu`. It doubles the evidenced limits to a 14,400-second
per-translation limit and an 8:20:00 Slurm limit. It requests 1024 GiB,
submits the unthrottled array `0-819`, uses `--nice=0`, `--no-requeue`, and
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
job name/comment, complete array, and the same job ID as the receipt.

Launch creates both the output directory and shared temporary root with mode
0700. It rejects direct or ancestor symlinks and binds each canonical absolute
path, uid, mode, device, and inode in the intent and launch receipt. Each array
task attests the output-directory identity before and after scanning. Seal
requires those identities, the live identity before and after assembly, and
the launch identity to be equal; the output-tree digest and execution receipt
also include the root identity.

Each array task receives exactly one mode-0700 directory named
`task-${SLURM_ARRAY_JOB_ID}-${SLURM_ARRAY_TASK_ID}` below the unique v4 data
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

Before each candidate translation, v4 reads and hash-verifies the frozen
domain and problem once and creates a private miniature source tree inside the
exact task `TMPDIR`. Directories have mode 0700 and files mode 0400. The frozen
scanner receives that miniature tree, so both the translator and
`axiom_based` normalization resolve the same snapshot paths. The wrapper
checks file identity and SHA256 immediately before each applicable consumer
and again after use, records canonical per-candidate snapshot evidence in the
shard, then unlinks only the exact files and removes only the exact directories
with `rmdir`. Assembly rejects missing or changed snapshot evidence.

The v4 manifest binds all 14 v3 manifest-bound producer files, the v3 code
manifest and Slurm script, the exact v3 launch intent and receipt, the sealed
v3 infrastructure diagnostic, and every new v4 producer/protocol/test file.
The source inventory must have the same pinned canonical SHA256 as v1--v3 but
is regenerated in the fresh v4 namespace.

Recovery shard substitution is disabled. Sealing requires all ordered
original tasks 0--819 to
be `COMPLETED` with exit `0:0`, and independently binds the actual account,
partition, QoS, CPU count, 1024 GiB request, time limit, job name, state, and
exit code. It requires exactly one original shard, one task-environment
attestation, and one Slurm log per array task; verifies all task temporary
directories were removed, the shared root is empty, and the launch root
identities remain exact; assembles directly from the original v4 shards; and
rechecks the root-bound complete tree before publishing the source attestation
and execution receipt. Any failure, timeout, OOM, missing/extra path,
provenance mismatch, or failed source-support gate fails closed. Confirmation
A and B remain forbidden unless the sealed v4 source audit authorizes their
exact source-disjoint cohorts.

Operational order after v3 is terminal:

1. Run `diagnose-v3`; review and commit its canonical diagnostic with the v4
   producer files.
2. Generate and verify the v4 code manifest, update its hash in the exact
   Slurm script, and commit the empty launch namespace.
3. Run `launch` once. Do not inspect successful shard or support contents.
4. Monitor scheduler state only. Run `seal` only after all 820 tasks are
   terminal; it succeeds only for 820 original `COMPLETED 0:0` tasks.
