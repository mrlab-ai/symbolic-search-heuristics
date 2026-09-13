# Symbolic-Search Heuristics Paper: Consolidated Handoff

**Stopped:** 2026-09-13, after the first permitted V11 full-census poll  
**Repository:** `symk-representation-safe`  
**Scope:** ICAPS paper framing, theory, confirmatory design, source-audit
infrastructure, and current empirical status

## Executive summary

The paper now has a substantially stronger and more defensible central story:
existing fixed-frontier certificates count possible node/value combinations but
discard which heuristic values are actually reachable below each masked ADD
node. Terminal incidence retains that relation, sharpens the classical
substitution bound, and is tested as an ordinal predictor of exact
fixed-frontier partition effort. Only if that predictor claim passes does the
paper use incidence as a representation budget for PDB selection.

The theoretical and protocol parts are mature. The main paper fits the eight
content-page ICAPS limit before references, the supplement is 41 pages, both
last built without overflow, undefined-reference, or undefined-citation
warnings, and the submission checker deliberately rejects the manuscript while
confirmatory result placeholders remain.

The confirmatory empirical chain is not complete. V11 was the latest fresh
source-census attempt. Its first permitted scheduler poll returned 818
successful and two failed outer rows. It also exposed every row under a bare
per-row job ID that the frozen controller did not accept for a multirow array.
The controller failed closed, no terminal receipt or source seal exists, and no
worker payload was opened. Therefore no A/B cohort is authorized, Confirmation
A was not launched, and the conditional direct and Confirmation-B campaigns
were not launched. The current paper contains no confirmatory outcome claim and
has not been uploaded to Google Drive.

## Why the framing is stronger

The original broad question—why some heuristics work in symbolic search and
others do not—mixed two effects: a heuristic changes the search space and also
partitions each represented frontier into value buckets. The revised paper
isolates the representation effect on common fixed frontiers. This produces a
clean sequence:

1. Identify what existing certificates forget: realized masked-node/value
   reachability.
2. Define terminal incidence `I` and exact partition effort `E`.
3. Prove `E <= I`, place `I` below two branches of established upper bounds,
   and separate it asymptotically from all seven registered certificate
   baselines.
4. Test the distinct empirical proposition that `I` orders `E` across
   heuristics better than the alternatives.
5. Only after that succeeds, test whether selecting PDBs under an incidence
   budget improves complete symbolic search.

This framing is stronger because it separates theorem, predictor claim, and
algorithm claim. It avoids claiming that a fixed-frontier metric generally
causes complete-search performance. The main risk is empirical rather than
conceptual: without a sealed Confirmation A, the paper has a strong theory and
design but no confirmatory evidence for its headline predictor claim.

## Theory and manuscript work completed

The current manuscript contains:

- a precise masked-ADD definition of terminal incidence;
- the charging proof `E <= I`;
- a hierarchy relating incidence to `kD`, masked cofactors, co-occurring
  profiles, Cartesian combinations, fixed-order width, and a standard-Apply
  bound;
- an incomparability result for the two certificate branches;
- an explicit family with `E = I = k(r+L)` while all seven registered
  certificate baselines are `Theta(k^2 L)` for the stated regime;
- an exact-PDB witness where incidence distinguishes a strict exact-effort
  order that active-value count, masked ADD size, and the certificate baselines
  do not;
- terminal-map/cap contraction for incidence, together with the explicit
  warning and counterexample that exact partition effort and complete-search
  performance need not improve;
- a scoped relationship to symbolic A*, decision-diagram substitution and
  forests, reachable-terminal operations, and automatic PDB selection.

The empirical prose now consistently calls terminal incidence an ordinal
predictor of fixed-frontier partition effort, not a general predictor of
heuristic performance. The direct `I`-versus-`mJ` campaign is a controlled
selection-rule test, not a mediation analysis. `mJ` is described as the
developmental predecessor used in this project, not as a community consensus.

## Confirmatory design frozen in the paper

### Confirmation A: predictor test

- 650 source-attested tasks from at least 28 families.
- Four exact PDB sources and a common set of up to 16 completed non-goal blind
  layers per task.
- Exact partition effort `E` as target.
- Terminal incidence `I` against nine alternatives: `D`, active-value count,
  seven certificate baselines, and their registered layerwise meet where
  applicable.
- Target-strict, tie-aware concordance aggregated by task and then equally by
  family.
- A complete gate covering support, a 0.65 concordance threshold, 0.02 margins,
  paired-family bootstrap lower bounds, leave-one-family-out robustness, and an
  all-prior-unrepresented stratum.

### Controlled predecessor ablation

Only an A pass authorizes fresh task-blocked triads comparing an
incidence-guided selector, an otherwise symmetric `mJ`-guided selector, and a
matched `K=32` arm on the 300-task B cohort. The decisive subset is defined by
different reconstructed winners before any search outcome is read.

### Confirmation B: end-to-end selector test

Only an A pass authorizes the nine-configuration comparison. The primary
comparators are the cap-aware reference and matched-work control. Every task
remains in the PAR2 matrix, and family-level bootstrap and leave-one-family-out
clauses prevent a few benchmark families from determining the conclusion.

## What was tried empirically

The main bottleneck was producing a complete, auditable source inventory from
which disjoint A and B cohorts could be frozen. Partial successes were never
silently reused.

| Campaign | What changed | Outcome |
|---|---|---|
| V1--V5 | Successively increased infrastructure ceilings while preserving the 1,640-candidate inventory. | V5 ended with 795 completed, 15 failed, and 10 out-of-memory array elements. |
| V6 | Attempted a diagnostic path. | Failed closed before producing an artifact or reading scientific payload. |
| V7 | Fixed historical newline/digest compatibility and prepared a scheduler-only repair. | The one-shot launch created no job: requested 3,000 GiB exceeded the `fat` nodes' allocatable memory after the system reserve. This, not evidence of a monthly allocation cap, explained that failure. |
| V8 | Reduced the sparse-repair request to 2,950 GiB. | Eight rows completed and 17 ran out of memory. The campaign was burned without payload reuse. |
| V9 | Abandoned selective repair and freshly attempted all 1,640 candidates under the downstream per-cell resource limits. | All 820 outer rows returned `FAILED/2:0`; no payload was opened or reused. |
| V10 | Added publication and compute canaries for the fresh-census path. | The compute-canary outer row completed, but Slurm reported the singleton under its bare parent ID while the parser required an `_0` suffix. The retained query was closed after one hour without another query; V10 was burned. |
| V11 | Accepted the singleton bare-ID representation only for a one-row canary, sealed and independently consumed the preflight, then launched a fresh unthrottled 820-element array on `fat`. | The first hourly poll found 818 `COMPLETED/0:0` and two `FAILED/2:0` rows. All rows appeared as bare per-row job IDs rather than indexed array IDs, so the controller emitted no receipt. No payload was opened; V11 cannot be sealed. |

The V11 launch used job `2365487`, accepted at 22:42:03 CEST. Every returned
row had account `naiss2025-5-561-cpu`, partition `fat`, QoS `normal`, one CPU,
26 GiB, a 01:10:00 limit, zero restarts, and the expected job name. The two
failed scheduler rows were bare IDs `2365753` and `2365756`; the retained
accounting representation does not safely identify their array indices.

The only V11 full poll was issued at 23:42:27 CEST, after the required hourly
boundary. It made exactly one `sacct` query. Its four immutable evidence files
were committed before inspection in:

`84af95630163a12f5748272d1df51b9362b22190` — *Retain first V11 full-census poll attempt*.

There is no poll receipt, terminal receipt, seal plan, census, split,
attestation, or execution receipt for the full V11 run.

## Reproducibility and evidence hardening completed

The V11 source audit binds 62 source files under manifest digest
`27d188ae50a282c85994cff7c8873359e158add2a0ae510491e8a76a52cea3bb`.
The compute-canary preflight was sealed at revision
`846d1b72f0d4e5d959b41fa638356fed2775c687`, independently replayed, and used
to authorize the one-shot full launch. The launch evidence is in
`dc719b462b01f857ef2333112ee1075c3bc21c04`.

Downstream code was hardened even though no downstream campaign was launched:

- `2218534f0b9383b940cb2acf4d5877e5f116d419` removes legacy V7 production
  loaders from A and B.
- `4cfad9dd845f9e352dc578508521f51c1c1add45` makes the direct campaign consume
  embedded evidence only and enforces the V11 ancestry chain.
- `831bd39f34c2880d5201e38507f935483f3ec7b6` completes canonical cohort,
  path, translator-closure, revision, and equal-output validation.
- `ff1caf6c52bde06d93f73752fa33032e04c1262d` authenticates dense V11
  classification and exclusion summaries.
- `1977bee82d07297d5f123d0ca993be3da3a795c1` propagates those summaries to the
  direct analysis.
- `e13674f700dfc6788b1e54cc40715ff88e2ff107` fixes real-consumer tuple handling
  and impossible cross-object task/family counts in A and B.
- `ff4eb9f913257de94b392047dfcddd292c63315a` binds the direct embedded A+B
  families to the source inventory.

Focused suites passed 135/135 for the adapter/A/B boundary and 34/34 for the
direct protocol. An independent combined rerun passed 66/66. Earlier A/B and
direct hardening suites passed 132/132 and 130/130 respectively. The
submission-checker self-test passed all registered adversarial cases and still
blocks production submission because confirmatory results are absent.

## Current repository and paper state

- The manuscript source remains prospective and does not imply that A, the
  direct ablation, or B succeeded.
- The incomplete V11 renderer migration was deliberately discarded at this
  handoff. The committed renderer remains production-disabled and must not be
  used for real V11 results without a completed migration and review.
- `paper/paper.pdf` and `paper/supplement.pdf` are pre-result review builds, not
  submission artifacts.
- No final submission build was produced after the V11 outcome.
- Nothing was uploaded to `google-drive:cofactor-width-icaps.pdf` or
  `google-drive:cofactor-width-icaps-supplement.pdf`.
- No new experiment was launched after the stop request, and no scientific V11
  payload was read.

## What remains unresolved

1. No complete source seal exists, so the promised 650-task A cohort and
   300-task B cohort do not exist as authorized experimental inputs.
2. Confirmation A has not tested whether incidence is the best registered
   ordinal predictor. The paper's central empirical claim is therefore open.
3. The direct `I`-versus-`mJ` and Confirmation-B selector studies remain
   conditional and unrun.
4. The result renderer still needs a V11-only, revision-pinned evidence path if
   the work is resumed.
5. Outcome-dependent abstract, result, conclusion, and title text remains
   intentionally absent.
6. Final ICAPS submission auditing, page-by-page PDF inspection, `jj` sealing,
   and Google Drive upload remain undone.

## If the project is resumed

No new theory is required before obtaining the missing empirical result. The
highest-value next step would be a new, fresh source-audit generation—not a
repair of V11—with a multirow accounting canary that exercises the exact Slurm
row representation used by the full array. The design should bind an explicit
array-task identifier rather than infer it from `JobIDRaw`, and it must retain
the existing all-success-before-read and no-partial-reuse rules. Only a complete
new source seal should authorize A; only an A pass should authorize the direct
and B campaigns. This is a future option, not an action authorized by the
current handoff.
