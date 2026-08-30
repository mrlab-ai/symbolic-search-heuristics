# Prospective Shared-Denominator Robustness Audit

Status: frozen after experiment launch and before parsing or inspecting any
planner outcome from the 1,052-task certificate holdout or the fixed-heuristic
order intervention.

## Purpose

The primary fragmentation response

    F = actual_effort / semantic_union_effort

and the normalized cut-aligned certificate

    R_profile = B_profile / semantic_union_effort

share a denominator.  Their common normalization is theoretically motivated:
it isolates the representation change caused by heuristic value partitioning.
Nevertheless, a rank association could be inflated mechanically when the
denominator varies.  This audit is fixed in advance to distinguish the
cut-aligned signal from that artifact.  It does not replace or modify any
primary gate.

## Frozen input

The input is the canonical primary analysis produced under
`pdb-profile-certificate-holdout-analysis-v1` from the 1,052-task,
45-domain prospective holdout.  Its measurement protocol digest is
`9e82fb3f514362c6cb2be9be3c70aeb929a36b24e67325e454579a417a1b5a62`,
and its launch receipt digest is
`d19230b85eef25e0ee3ea2aa2e421b0e4f261a9096a15b25a27c3f91b58f5cf4`.
Only primary-analysis observations already declared eligible are used.

## Exact quantities

For every eligible observation with positive semantic-union effort `U`, define

    D_inverse = 1 / U
    F         = actual_effort / U

and retain the exact integers `actual_effort`, `B_profile`, `B_width`, and
`B_add` plus the exact rational `R_profile`.  All arithmetic and comparisons
use integers or reduced rational numbers.  Floating-point fields in the
primary artifact are checked but never used for ordering.

Two comparisons are fixed:

1. **Denominator null.**  On one shared strict-pair set, compare the ordinal
   concordance of `R_profile` and `D_inverse` with `F`.  Both predictors use
   the same direction: a larger predictor should accompany larger
   fragmentation.
2. **Absolute certificate.**  On one shared strict-pair set, compare
   `B_profile`, `B_width`, and `B_add` with `actual_effort`.  All use the same
   direction.  This check contains no common division.

Semantically duplicate configurations on one task remain collapsed exactly as
in the primary analysis.  Comparisons are within task.  A pair enters a shared
comparison only when the response and every listed predictor differ.  The
reported summary is pairwise concordance averaged first within domain and then
equally across eligible domains.  Leave-one-domain-out (LODO) values rerun this
complete calculation after removing each of the 45 domains.

## Frozen support and decision gates

Every gate requires at least 30 eligible domains and at least 211 tasks with a
comparable pair, matching the primary holdout floor.

The **denominator-artifact robustness** gate passes exactly when:

- `R_profile` has equal-domain macro concordance at least 0.70;
- every one of the 45 `R_profile` LODO values is at least 0.65;
- its macro concordance exceeds `D_inverse` by at least 0.20; and
- it exceeds `D_inverse` in every LODO replicate.

The **absolute-certificate robustness** gate passes exactly when:

- `B_profile` has equal-domain macro concordance at least 0.70;
- every one of the 45 `B_profile` LODO values is at least 0.65; and
- its macro concordance is within 0.02 of both `B_width` and `B_add`.

All criteria and their failures are reported.  No alternative null,
transformation, threshold, subset, aggregation, or budget may rescue a failed
gate.  Any later analysis is explicitly post-hoc.
