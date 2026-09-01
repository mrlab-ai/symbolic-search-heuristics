# Prospective v4 cancellation protocol for source-audit v5

This protocol was prepared to authorize one operation only while v4 still had
active work: cancelling the whole Slurm parent array `1865695` so that the
seal-ineligible campaign stopped consuming resources before a fresh v5 rerun.
It never authorized a launch, a resubmission, reuse of any v1--v4 shard, or
cancellation of selected array elements.

This was a contingency path while v4 still had active work. Natural completion
was preferred; if all 820 rows became terminal first, no intent was to be
prepared and the process proceeded directly to the non-cancellation terminal
diagnostic.
V4 did reach that natural terminal state, so this contingency was not
exercised and no cancellation intent, attempt, or receipt exists.

## Fixed authority

The cancellation program pins the absolute executable `/usr/bin/scancel`, its
SHA256 digest, and the exact argv `[/usr/bin/scancel, 1865695]`.  The only
authorized failure classes are `FAILED` with exit `75:0` and an exact
14,400-second empty-stderr translator-timeout wrapper, or `OUT_OF_MEMORY` with
exit `0:125`, translator exit -9, and scheduler OOM-kill evidence. Tasks 147,
150, 484, 486, 487, and 489 are exact pinned instances of the first class;
tasks 488, 716, 717, 718, 719, 720, and 722 are exact pinned instances of the
second. Their failed-log hashes, byte counts, and complete parent/batch/extern
accounting rows are embedded in the program. The intent also pins every
additional actual pre-intent instance of either class, if any. No successful,
running, pending, or cancelled log is read.
These thirteen tasks are the prospective source-fixed trigger set, not the
complete terminal failure set. The final diagnostic additionally classifies
timeouts 715, 721, 724, and 725 and OOMs 485 and 723 without retroactively
changing the frozen cancellation authority.

`prepare-cancel-intent` first validates all 820 accounting rows against an
explicit known-state allowlist.  It then revalidates every actual failure
trigger and writes, exclusively and canonically, an intent containing:

- the parent job, exact whole-array scope, tool identity, argv, environment,
  and reason;
- all actual authorized trigger records and their digest;
- the complete current 820-row scheduler snapshot, state counts, and digest;
- hashes of every transitive cancellation helper; and
- the all-820-shard/all-1640-candidate v5 rerun with zero v1--v4 reuse.

The intent is only prospective.  It must be committed together with every
listed cancellation source before execution.  `cancel-v4` rejects a dirty,
untracked, missing, or differently committed scope.

Tasks may progress while the intent is reviewed and committed.  Execution
does not require the live snapshot to equal the intent snapshot: active rows
may remain in any known active state or become successful `COMPLETED 0:0`
rows.  Previously terminal rows must remain byte-identical.  A new failure or
OOM after intent creation, cancellation, unknown state, task, or partition is
rejected as unattributed progress.  At least one active row must remain before
the whole parent job is cancelled.  The attempt and receipt bind separate
digests for both the original intent snapshot and the final pre-cancel
snapshot.

Monotonicity is revalidated across every boundary. From intent to the final
pre-invocation snapshot, an active row may only remain active or become
`COMPLETED 0:0`. From pre-invocation to the immediate receipt snapshot, and
again from that receipt to the final diagnostic, a row that was active may
remain active, become `COMPLETED 0:0`, or become a syntactically valid
`CANCELLED` row. This permits delayed scheduler cancellation. Any row already
terminal at a boundary must remain byte-identical thereafter: in particular,
`COMPLETED` cannot later become `CANCELLED`. New failures, OOMs, unknown states,
and terminal-row mutations are rejected before receipt publication and before
any final failed-log read. Crash recovery applies the same transitions.

## Prespecified sequence (not exercised)

The following steps were fixed prospectively and would not have been combined.
They must not be run now that v4 is terminal.

```bash
experiments/data/pdb-terminal-incidence-shadow-venv/bin/python -B \
  experiments/cancel_pdb_terminal_incidence_confirmation_source_audit_v4_v5.py \
  prepare-cancel-intent

/home/jendrik/bin/jj --no-pager commit \
  -m "Authorize whole-array v4 cancellation before source-audit v5" -- \
  experiments/audit_pdb_terminal_incidence_confirmation_sources.py \
  experiments/audit_pdb_terminal_incidence_confirmation_sources_v5.py \
  experiments/cancel_pdb_terminal_incidence_confirmation_source_audit_v4_v5.py \
  experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v5.py \
  experiments/pdb_terminal_incidence_confirmation_inventory.py \
  experiments/pdb_terminal_incidence_confirmation_safe_io_v5.py \
  experiments/pdb_terminal_incidence_confirmation_source_audit_v4_code.sha256 \
  experiments/pdb_terminal_incidence_confirmation_source_audit_v4_cancellation_v5_protocol.md \
  experiments/test_pdb_terminal_incidence_confirmation_source_audit_v4_cancellation_v5.py \
  experiments/artifacts/pdb-terminal-incidence-confirmation-v5/v4-cancellation-intent-v5.json

experiments/data/pdb-terminal-incidence-shadow-venv/bin/python -B \
  experiments/cancel_pdb_terminal_incidence_confirmation_source_audit_v4_v5.py \
  cancel-v4
```

The middle command would have been path-scoped Jujutsu, not raw Git. The intent
file would not have existed until the first command succeeded. The sequence
was not exercised and must not be run after natural completion.

## One-shot journal and crash recovery

Immediately before invoking `scancel`, `cancel-v4` exclusively publishes a
canonical attempt marker containing the committed intent hash, commit ID,
exact tool/argv, controlled environment, and a fresh full scheduler snapshot.
Any existing attempt or receipt makes `cancel-v4` refuse to run.  Therefore an
exception after the attempt marker can never cause a second cancellation.

If the process crashes, `recover-cancel-receipt` may query accounting and
complete receipt determination only after every array row is terminal.  It
does not contain a call path to `scancel`; while any task is active it fails
closed as indeterminate.  It never resubmits and never selectively cancels.

## Terminal v4 diagnostic and v5 boundary

The v5 terminal diagnostic rejects active or unknown states before opening any
Slurm log.  If any row is `CANCELLED`, it requires the exact canonical intent,
attempt, and receipt; revalidates their job, tool, argv, code hashes, committed
bytes, and trigger evidence; and records every cancelled task's scheduler row
and complete accounting rows with digests.  It never opens `COMPLETED` or
`CANCELLED` logs.  Only actual `FAILED`/`OUT_OF_MEMORY` logs are classified.

The final v5 code manifest directly includes the safe-I/O helper and
cancellation code/tests/protocol. If cancellation occurred, its manifest-bound
terminal diagnostic transitively binds the exact intent/attempt/receipt; when
v4 completes naturally, those nonexistent optional artifacts are not manifest
inputs. v5 still uses the `fat` partition, one CPU, `2T` memory, a
28,800-second per-candidate limit, a `16:40:00` Slurm limit, an unthrottled
0--819 array, project-backed per-candidate temporary storage, original-only
sealing, and no v1--v4 reuse.

The natural terminal diagnostic records 801 `COMPLETED`, ten `FAILED`, and
nine `OUT_OF_MEMORY` tasks, zero cancelled tasks, a null cancellation object,
and all nineteen classified failure records. Its canonical SHA256 is
`165c31105be505b763a1a4d92fb03365272eaf875bcf8c12d3dd85d3516e20fc`.
