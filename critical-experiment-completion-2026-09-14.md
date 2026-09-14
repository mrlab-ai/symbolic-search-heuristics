# Critical-experiment completion, resumed 2026-09-14

The user resumed work with: “Finish all experiments that the paper depends on
critically, then update and upload the paper.” Work remains in the isolated
`symk-representation-safe` workspace. The earlier handoff report records the
state when paper improvement stopped; this file records the subsequent work.

## Current state: approved within-family redesign

After the source-feasibility failure below, the user approved replacing the
unseen-family confirmation with fresh generated instances from previously
studied families. This changes the scope of confirmation, not the historical
V12 result. No heuristic performance has yet been observed in the new design.
The new claim is conditional on the supported families, generator settings,
PDB configurations and representation order. It cannot establish transfer to
unseen families. The fixed-frontier prediction test still precedes any
conditional selector comparison; the predictor and selector cohorts will use
disjoint instance-generation seeds and verified nonduplicate problem inputs.

The official `AI-Planning/pddl-generators` source is pinned at
`d5c22c9ab21ecaf90db82daf2a0537973c661009`. The generator pilot uses three size
settings in each of 30 previously studied candidate families, without running
heuristics. Version 1 generated 87 of 90 instances reproducibly; Schedule's
documented size option exceeded the executable's accepted range. The wrapper
was corrected to the executable's valid option. Version 2 generated all 90
instances twice with byte-identical domain/problem pairs. Both pilot manifests
remain in their separate project-data directories. These pilot tasks cannot
enter the scientific cohorts. Planner-compatibility testing is next; the
final supported-family set will be determined without heuristic outcomes.

The manuscript update and replacement Drive upload remain pending the
completed critical evidence. Earlier source campaigns and their seals remain
unchanged.

## Completed V12 census and original-design failure

The V12 source census is complete, but its cohort-feasibility gate failed.
All 820 elements of job **2383478** completed with exit `0:0` and the exact
resource contract. The first hourly poll was retained at `42a4d126` before
inspection; its receipt SHA-256 is
`9f93a31fff052048cd7864a02f10a1f56fd5f15abc03f8a462b35a069a477d06`.
The subsequent seal made zero scheduler queries. The complete seal, including
the 16,157,159-byte attestation, is committed at
`0f7cdfd901279e272a6e1cc74e19328076b60076`. The attestation SHA-256 is
`c3cb6249683d5a01e0921a870dc65f43d80337da18b7bffd43c9ce39e3629b3d`;
the execution receipt SHA-256 is
`3614a67e52f259f9b9cc6791e6ab82954bc59dfed7dc160378326fac3c3e8ed9`.

All 1,640 candidates were freshly attempted. Translation succeeded on 1,590;
50 were excluded by the fixed memory limit. There were no input rejections or
time exclusions. Among the translated tasks, 396 are supported and 1,194 are
unsupported. The supported tasks span 19 families, all already represented in
both the shadow study and the full prior-study ledger.

| Frozen prelaunch requirement | Available after deterministic split | Required |
| --- | ---: | ---: |
| Confirmation A tasks | 341 | 650 |
| Confirmation A families | 19 | at least 28 |
| Guided B tasks | 55 | at least 200 at the source gate; 300 downstream |
| Guided B families | 19 | at least 30 |
| A all-prior-unrepresented tasks/families | 0 / 0 | at least 100 / 10 |
| B all-prior-unrepresented tasks/families | 0 / 0 | at least 50 / 10 |

Unsupported-task reasons overlap: 514 tasks have nonpositive serialized
operator costs, 606 have normalized axioms, 606 have serialized axioms, and
600 have serialized conditional effects. The memory exclusions are flashfill
(4), labyrinth (17), organic-synthesis (9), and slitherlink (20).

The independent consumer's classification and deterministic-split functions
were rerun against the exact attestation bytes read from the literal committed
seal. Every classification summary, source-family flag, supported-task reason,
cohort and gate clause matched. The public downstream-authorization consumer
correctly refused the failed source gate. No confirmation freeze or launch was
created, and no A/B/direct performance outcome has been observed. This is a
**failed source-feasibility gate, not a failed statistical Confirmation A**.

Additional compute cannot make the frozen inventory sufficient. Even assuming
every memory-excluded task were supported, the upper bound would be 446 tasks
from 22 families, including just 21 tasks from two all-prior-unrepresented
families. That is insufficient even for A alone. Identical source reruns or
larger memory limits cannot bridge the gap.

At this checkpoint, completing confirmation required a scientific-design decision: expand the
benchmark universe or replace the unseen-family requirement with a new,
explicitly narrower held-out-instance design. Neither choice has been applied
silently. The thresholds, inventory, source seal and current scientific claims
remained unchanged. Paper result integration and replacement upload were paused
pending that decision. The approval and resumed work are recorded above;
the existing Drive PDFs remain the earlier drafts.

## Full-census launch state at 08:16 UTC (10:16 CEST)

The V12 preflight passed. The fresh full census is job **2383478**, accepted
at **08:15:47 UTC (10:15:47 CEST)**. Its 820 unthrottled elements attempt all
1,640 candidates under the existing `fat` resource contract. Launch evidence
is committed at `17106c5e1f45c9bfa0244a3555634571de569bff`.
The first full-census scheduler check was permitted no earlier than
**09:15:47 UTC (11:15:47 CEST)**. At this launch checkpoint, no full-census poll
or scientific payload read had occurred and Confirmation A/B/direct were
unstarted.

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

A second CLI check found that the standalone-evidence producer ignored
`--help` and entered its evidence-reading path. It reached the missing B-freeze
check and failed without publishing anything. At `4cc70b74`, argument parsing
was added before all evidence access; help and invalid arguments now have
explicit no-read regression tests. All 34 standalone/hardening tests passed.
The existing synthetic calibration and planner-manifest files are present;
they will be revalidated, not blindly overwritten, before any direct freeze.

The main/supplement build now depends on the final terminal-incidence generated
TeX. Submission checks load the pinned production evidence, compare generated
bytes, and require the title appropriate to the observed terminal branch.
The submission-check self-test passes with 166 rejected source/result
adversaries and 46 rejected review-bundle adversaries; the 71 reporter tests
also still pass. The manuscript's actual outcome integration remains pending.

## Paper and upload

Before the resumption request, the existing main paper and supplement were
built and uploaded to `google-drive:cofactor-width-icaps.pdf` and
`google-drive:cofactor-width-icaps-supplement.pdf`, with remote hashes verified.
Those are the pre-completion drafts, not final experimental updates. The final
paper update, build and replacement upload remain pending completed evidence.
