# V10 source-audit control protocol

Status: source-only specification. Creating the code manifest, querying Slurm,
or creating any V10 runtime namespace is a separate, explicit operation.

## Invariants

V10 is a new campaign. No V1--V9 task log, scheduler row, shard, temporary
file, translated task, or scientific payload is read or reused. The full run
always attempts the frozen 1,640 candidates as 820 two-candidate shards.

Both Slurm programs use account `naiss2025-5-561-cpu`, partition `fat`, QoS
`normal`, one node, one task, one CPU, 26 GiB, and 01:10:00. They set nice 0,
disable requeue, export no submission environment, set `LANG=LC_ALL=C`, and
contain no array throttle. The compute canary is array `0-0`; the census is
array `0-819`.

Every candidate runs through the same `_run_candidate` implementation: pinned
Python, a 24,576-MiB address-space limit, 1,800/1,801-second CPU limits, an
independent parent `prlimit` observation, a process-creation-denying seccomp
filter, a process-group watchdog, bounded stdout/stderr capture, and source
snapshot verification. The canary differs only in its two synthetic PDDL
inputs and the allowlisted origin `v10-synthetic-canary`. Both paths call the
same immutable shard publisher and produce claim, result, environment, four
stream-prefix files, and `complete.json`.

All runtime and control directories are fresh, owned by the invoking uid, and
mode 0700. Published shard directories are mode 0500 and files are mode 0400.
Control records are canonical JSON, created exclusively, fsynced together with
their parent directory, and never overwritten.

## Required state machine

1. Commit all source files and tests. In a later clean change, generate and
   commit the exact code manifest. No runtime starts before this point.
2. Run `controller-canary` on the repository's actual Lustre filesystem. It
   first proves the filesystem name and magic with a hash-pinned `/usr/bin/stat`
   probe, exercises the production hard-link publisher on that same device,
   retains the immutable output, and records that no `renameat2` path was used.
3. Run `launch-canary` exactly once. It submits one independent `fat` array
   row using the fixed compute-canary Slurm template. Submission intent and
   raw stdout/stderr exist before `sbatch`; uncertainty never permits an
   automatic resubmission or an out-of-cadence scheduler query. Full-launch
   receipt recovery is permitted only from retained zero-return `sbatch`
   stdout and itself makes zero scheduler queries; ambiguous submission burns
   the campaign.
4. Run `poll-canary` no sooner than one hour after the post-`sbatch` acceptance
   timestamp retained in the launch receipt and thereafter no
   sooner than one hour after the preceding durable poll. Each accepted poll
   makes exactly one combined `sacct` query for identity, resource, state, exit,
   and restart fields. Intent precedes the query; raw streams, result, and
   receipt are append-only. A stranded post-intent attempt suppresses queries
   for one hour, is then closed without a query as `abandoned-unknown`, and is
   hash-linked to the one permitted successor. A failure before durable intent
   burns the campaign because whether the query ran cannot be authenticated.
   Before deriving the next permitted time, every retained normal and abandoned
   attempt is reopened and validated in order: exact intent, command, raw-stream
   identities and hashes, immutable owned 0400 artifacts, result, independently
   parsed scheduler rows and resource contracts, receipt summary, canonical UTC
   timestamps, and previous-record link.
   Any corrupt earlier record blocks the query rather than contributing a
   cadence anchor.
5. A terminal poll creates one six-field terminal receipt. `seal-canary`
   performs zero scheduler queries, revalidates the complete retained chain and
   all raw hashes before reading the worker payload, validates the exact eight-file
   canary shard, and writes a seal plan, attestation, and preflight
   authorization.
6. Commit the complete preflight namespace. The full launcher must consume it
   through the independent V10 consumer and committed-snapshot reader at that
   exact seal revision. Merely finding working-copy files is insufficient.
7. Only that successful snapshot consumption permits `launch`. The launch
   receipt embeds the seal revision and authorization, canary, publisher, and
   code-manifest hashes. It then submits the fresh 820-row census exactly once.
8. `poll` uses the identical hourly, one-query, append-only protocol. `seal`
   uses only the retained successful terminal poll and therefore makes zero
   scheduler queries. Before any shard read, it revalidates all 820 rows as
   `COMPLETED`/`0:0`, with the exact account, fat partition, QoS, CPU, memory,
   time, job name, and zero restarts.
9. Commit the seal and consume it independently from that committed snapshot.
   Only the independent consumer's authorization may feed later experiments.

## Failure boundaries

Any collision, symlink, ownership or mode mismatch, source/manifest/revision
mismatch, ambiguous submission, restart, malformed scheduler output, nonzero
exit, extra/missing shard file, completion mismatch, hash mismatch, partial
seal chain, or preflight mismatch fails closed. Worker logs never participate
in authorization. A failed compute canary or full census is not selectively
repaired; a new versioned campaign is required.

The code manifest is intentionally absent from this source checkpoint. It is
generated only after review, testing, and a clean committed source closure.
