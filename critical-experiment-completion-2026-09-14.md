# Critical-experiment completion, resumed 2026-09-14

The user resumed work with: “Finish all experiments that the paper depends on
critically, then update and upload the paper.” Work remains in the isolated
`symk-representation-safe` workspace. The earlier handoff report records the
state when paper improvement stopped; this file records the subsequent work.

## Current state at 08:16 UTC (10:16 CEST)

The V12 preflight passed. The fresh full census is job **2383478**, accepted
at **08:15:47 UTC (10:15:47 CEST)**. Its 820 unthrottled elements attempt all
1,640 candidates under the existing `fat` resource contract. Launch evidence
is committed at `17106c5e1f45c9bfa0244a3555634571de569bff`.
The first full-census scheduler check is permitted no earlier than
**09:15:47 UTC (11:15:47 CEST)**. No full-census poll or scientific payload
read has occurred. Confirmation A/B/direct remain unstarted.

## Execution repair and preflight

V11 is not usable for confirmation. After declaring that campaign unusable,
we inspected only its failed outer stderr and one retained accounting query
for infrastructure diagnosis. Both failed elements (205 and 208) reported an
ambiguous translator exit of -9. The accounting query also established the
identity error: `JobIDRaw` contains internal numeric element IDs, whereas
`JobID` retains array indices. The diagnostic evidence was committed at
`c9c6c9dff0c6e055e0654e17934416e36fa82acf`. No V11 scientific payload is reused.

V12 preserves the candidate inventory, deterministic split, CPU/memory budgets,
predictors and scientific decision rules. It changes execution accounting:

- Scheduler parsing requests `JobID`; the singleton exception remains limited
  to a one-element array. An 820-element regression checks exact array identity.
- Each child is reaped with `wait4`, retaining kernel user-plus-system CPU time.
  A SIGXCPU/SIGKILL return is a time exclusion only after the unchanged
  1,800-second CPU budget. Earlier unexplained signals remain fatal.
- Every source shard is fresh. Prior campaigns remain separate and cannot
  authorize the cohort.

The V12 source suite passed all 118 tests, including an actual synthetic hard
CPU-limit kill and rejection of an immediate unexplained SIGKILL. Source code
was committed at `4e65621cc0f115400619f63a46ced4da0b895306`; the subsequent
62-file code manifest has SHA-256
`106abf9ae845f095e6df514d0b2ebbc2e6f8cfe85bb48826fee94086f988288c`.
The actual-Lustre controller publication canary passed.

The V12 compute canary was job **2377933**, accepted at
**2026-09-14 07:13:22 UTC (09:13:22 CEST)**. It uses `fat`, normal QoS,
account `naiss2025-5-561-cpu`, one CPU, 26 GiB and 01:10:00, with no throttle
or requeue. Its launch evidence is committed at
`b36fa402` (Jujutsu commit prefix). Its first hourly scheduler check returned
one `COMPLETED/0:0` row with the exact resource contract. That poll was committed
at `136f5b09` before inspection. The zero-query seal then verified both
synthetic candidates as successful. The complete preflight is committed at
`d77a9009180ca6466c413d45128fd6849d5526b2`, with authorization SHA-256
`0b1dfaff0be8578b574eaa679ebc53b352cd2897e4c818579bf51d0fa7aa293b`.
The independent consumer successfully consumed that literal committed revision
before the full launch; the full launcher repeated the same check.

## Downstream preparation

Confirmation A, Confirmation B and the direct metric-choice experiment now
consume V12 through the independent adapter. Cohorts, options and thresholds
are unchanged. All 269 selected downstream regression tests passed; migration
commit: `1e70eedd2505f03dc931407cfcfa2871b14932c0`.

The paper reporter now projects the fresh V12 source census, distinguishes
unsupported tasks from resource-excluded tasks of indeterminate support, and
checks repeated analyses against committed artifact and source pins. It has
71 passing tests, including numeric projections from the actual selector
analyzers on synthetic cells. Reporter commits:
`cb2b279789d3ed2941e15ea833bf2305349edae3` and
`6c66343adaec6930f4d5892d133a3ea54cfb7049`.
The reporter's own `--self-test` now runs all 71 tests. A real command-line
smoke test additionally exposed a stale exception alias in the B launcher,
which could turn even a successful design check into a failing exit. This was
fixed before submission at `ea686790`; 44 affected B tests, including real
CLI success/help/error paths, passed. Both A and B design checks pass.
Production pins remain unset: no synthetic or unfinished result is inserted
into the paper. All V12 manifest-bound source bytes still match the submitted
manifest.

## Paper and upload

Before the resumption request, the existing main paper and supplement were
built and uploaded to `google-drive:cofactor-width-icaps.pdf` and
`google-drive:cofactor-width-icaps-supplement.pdf`, with remote hashes verified.
Those are the pre-completion drafts, not final experimental updates. The final
paper update, build and replacement upload remain pending completed evidence.
