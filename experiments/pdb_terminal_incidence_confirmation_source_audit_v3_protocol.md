# Universal unseen-source audit: campaign-v3 resource amendment

Campaign v3 is an outcome-blind resource amendment to the frozen universal
source audit.  It does not change the 1,640-candidate inventory, source bytes,
support definition, deterministic A/B split, support floors, or prelaunch
gate.  It changes only the resources needed to complete the audit.

The original 26 GiB campaign v1 ran all 820 shards and ended with 30
out-of-memory array elements.  Its source attestation and execution receipt
were never created.  Campaign v2 was committed before launch and reran all
820 shards independently with 256 GiB, a 2,700-second per-translation cap,
and no v1 reuse.  It also failed before sealing: Slurm reported translator
timeout exits and out-of-memory exits.  Before defining campaign v3, the
inspection scope was restricted to scheduler rows and Slurm task-name/error
diagnostics.  No successful shard contents, source-support classifications,
candidate attestation, cohort, or prelaunch-gate outcome was read or used.

Campaign v3 reruns every one of the 820 original shards from scratch.  It
requests one CPU and 512 GiB on the `fat` partition, allows 7,200 seconds per
translation and 4:10:00 per two-task array element, uses normal QoS and the
same account, has no array throttle or nice adjustment, and submits with
`--export=NONE`.  It reuses zero v1 shards and zero v2 shards.  The launch
receipt embeds the complete v1/v2 failure-provenance chain, canonical Slurm
rows, and hashes of every v2 failure log.

The submission invokes a hash-pinned `/usr/bin/sbatch` with every critical
resource repeated explicitly on the command line.  Its environment is the
exact three-entry map `LANG=C`, `LC_ALL=C`, and `PATH=/usr/bin:/bin`; no
ambient `SBATCH_*` or `SLURM_*` variable can override the frozen request.
Sealing independently queries hash-pinned `sacct` and binds the actual
account, partition, QoS, CPU count, requested memory, time limit, job name,
state, and exit code for every array element.

Campaign v3 may be sealed only if all ordered array elements 0--819 are
`COMPLETED` with exit `0:0`.  Any application failure, timeout,
out-of-memory state, cancellation, unrecognized scheduler state, missing
shard, extra output, provenance mismatch, or failed source-support gate fails
closed.  Campaign-v3 recovery is disabled: even a normally recoverable Slurm
infrastructure state invalidates the campaign.  Confirmation A and B remain
forbidden unless the sealed v3 source
audit authorizes their exact source-disjoint cohorts.  A later paper must
report the v1/v2 infrastructure failures and this pre-outcome amendment.
