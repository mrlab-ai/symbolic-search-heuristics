# Exact-integer serialization recovery for completed Confirmation A

## Goal and scope

Recover only the final analysis/reporting step of the completed 650-task,
four-configuration within-family predictor experiment. Do not run planners,
translations, new experiments, or scheduler queries. Do not inspect or select
scientific conclusions while implementing the recovery. Preserve the original
failed attempt and all frozen code and data. The user requires all coding to
be implemented by an appropriately lighter-model subagent; the main agent
plans, reviews, and runs approved verification. Use the built-in subagents,
not a separate CLI process, for this handoff.

Workspace: `/nobackup/proj/disk/dfsplan/personal/jendrik/symk-representation-safe`.
Never touch the sibling live workspace. Use `apply_patch`; no Git operations.
Do not commit or change JJ state in a subagent. Read applicable local skills.
Shell commands must use `login:false`.

## Evidence already checked

All 867 scientific array elements and build/parse/fetch/report jobs completed
with exit `0:0` and the exact resource contract. The retained properties have
2,600 cells and the pipeline reports zero unexplained run errors. Only job
2418268, the analysis step, failed with exit `1:0` at
`versions.append(C.G.canonical(result))` after computing the first analysis:

`ValueError: Exceeds the limit (4300 digits) for integer string conversion; use sys.set_int_max_str_digits() to increase the limit`

The original analysis produced none of `analysis.json`, `analysis-repeat.json`,
or `analysis-receipt.json`. All scheduler jobs are terminal. No scientific
result aggregate has been inspected. No extra experiment is needed.

Retained poll:
`experiments/artifacts/pdb-within-family-confirmation-v1/confirmation-a/poll-20260914T211529Z.json`
SHA-256 `c48ed72a2b6cf93ffce93e324e965f67b5cc74c9a6010b5b3001f662ff96532e`.
It was committed before inspection at `6ec3ee03`.

Launch: same directory, `launch.json`.
Freeze: `experiments/artifacts/pdb-within-family-confirmation-v1/cohort-freeze.json`.
Freeze SHA-256 `0c95dd5afe61ea0f77c7441a824bcecbe255641994874d28734274a64e3a0c67`.
Frozen scientific code commit: `f284830c6e3134f2e35c55a2f7f4e85614d02b01`.
Properties: `experiments/data/exp_pdb_within_family_a_v1-eval/properties`.

## Recovery implementation owner

Add `experiments/pdb_within_family_recover_a_serialization.py` and its focused
test module. Do not edit any file listed in the freeze's 37-file code closure,
including the original analysis, cohort, monitor, instances, runner, or seal.
Do not edit any V12 manifest-bound file. Reuse original validators and analysis
functions, without changing numerical calculations, thresholds, exclusions,
pair sets, seeds, or bootstrap settings.

Use a finite Python integer-to/from-string conversion limit of **100000**
decimal digits, not an unlimited setting. Keep integers and rational numbers
exact. This changes serialization capacity only. All inputs are trusted local
artifacts whose identities must be checked before analysis. Test a >4300-digit
integer round trip and prove the finite upper bound is still enforced.

The recovery must:

1. Validate the original launch/poll identity, exact six-step shape, all 872
   scheduler identities and resources, successful first five steps, and exactly
   the original analysis failure above. Reject other failed/active jobs and
   other errors. Never forge an all-successful scheduler poll.
2. Verify `C.load_freeze()` and hash the unchanged properties. Refuse existing
   analysis outputs, recovery records, or diagnostic logs; do not overwrite.
3. Invoke the pinned interpreter with `-X int_max_str_digits=100000` to execute
   the unchanged `pdb_within_family_a_analysis.py` CLI. Its existing `run_twice`
   checks raw evidence and produces byte-identical analyses from fresh reads.
   Use the original canonical analysis output directory. Capture stdout,
   stderr, exit code, invocation, interpreter hash, start/end times, and hashes
   of the wrapper and its committed revision. Do not actually invoke the real
   recovery until the main agent reviews and commits the code. Retain the
   invocation and diagnostic logs even on a nonzero exit or timeout; a failed
   attempt must not create a success receipt or seal, and its records must
   prevent an accidental overwrite.
4. On success, verify frozen code and properties again and bind the two
   analyses and their original receipt. Retain a new
   `confirmation-a/serialization-recovery.json` receipt with schema
   `pdb-terminal-incidence-within-family-a-serialization-recovery/v1`.
   Include integer limit, zero repeated scientific runs, zero scheduler
   queries, original failed-job identity, immutable code identity, and hashes
   of all inputs, outputs, and invocation logs. Coordinate exact receipt
   fields with the paper-adapter owner before that owner implements them.
5. Produce a completion seal only after independent raw matrix/evidence and
   receipt validation. Use schema
   `pdb-terminal-incidence-within-family-a-seal/v2-serialization-recovery`.
   Preserve the normal seal's scope, matrix, code commit, decision, selector
   authorization, and seven evidence roles; add an eighth `recovery` role
   binding the recovery receipt. The original failed scheduler state remains
   explicit. Reuse `A.verify_run_evidence`, `A.validate_matrix`, and the frozen
   input/analysis/receipt identity rules from the original seal. No additional
   statistical analysis or altered scheduler evidence is allowed for sealing.

Keep recovery and sealing simple and explicit; avoid a general retry system.
Unit tests must reject altered input/code hashes, unrelated analysis errors,
nonterminal/failed scientific jobs, nonzero recovery exits, mismatched repeats
or receipts, changed properties, altered integer limits, and existing outputs.

## Paper-adapter implementation owner

Modify only `paper/within_family_evidence.py`, its focused tests, and other
paper-side code only if demonstrably necessary for this reporting recovery.
Preserve the existing normal-completion and original V12 reporting routes.
Do not set production pins until the actual recovery and seal are committed.
Do not read scientific outcomes during implementation.

Support an optional committed `recovery` artifact pin, discovered through the
new seal's evidence map. Require it exactly when the recovery seal schema is
used. Validate its bindings and actual successful local analysis invocation;
accept the original failed analysis scheduler row only with that complete
recovery proof. The other five original steps must still be successful and
every allocation must match. Preserve all existing numerical recomputation,
code/freeze/property/matrix checks and unchanged ordinary-completion tests.
Do not pretend the original scheduler analysis succeeded.

Use the same finite 100000-digit setting for the trusted artifact-reading and
rendering process so exact recovered JSON can be decoded and re-encoded.
Do not round or stringify the mathematical evidence to evade the limit.
Coordinate the receipt interface with the recovery owner. Add adversarial
tests for missing/tampered recovery proof and unchanged ordinary behavior.

## Verification and handoff

Pinned interpreter from the experiments directory:
`data/pdb-terminal-incidence-shadow-venv/bin/python` (3.12.13, Lab 8.10).
Use `env -u PYTHONPATH -u PYTHONHOME -u VIRTUAL_ENV PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1`.

Run focused new tests, the existing within-family tests, and paper renderer
`--self-test`. Verify `sha256sum --check --quiet experiments/pdb_terminal_incidence_confirmation_source_audit_v12_code.sha256`
from the repository root, and verify the current code closure with
`C.load_freeze()` from the experiments directory.

Report exact changed files and test results. Main agent reviews every diff,
reruns verification, commits code, then executes the recovery and validates
the result. No new scheduler polling or scientific campaign is necessary.
