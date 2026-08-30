# Prospective fixed-heuristic variable-order intervention

Status: frozen before launching any intervention cell.  The corrected
275-task development outcomes and the formula-development calculations are
known.  No outcome for the 1,052-task holdout under the Fast Downward variable
order has been inspected.

## Question and intervention

For each holdout task, construct one deterministic goal-fill PDB with a
100,000-state budget and run product-at-evaluation forward symbolic A* twice:
once with the fixed Gamer variable order and once with the fixed untranslated
Fast Downward variable order.  Goal-fill uses the task's goal/causal order,
not the BDD order.  Thus both cells must have the same PDB pattern, values,
solution cost, expanded states and active heuristic values at every path-cost
layer.  Any disagreement aborts the paired analysis.

The intervention changes the decision-diagram order while holding the task,
heuristic semantics, search keys and expanded state sets fixed.  It tests
whether the cut-aligned certificate orders the representation cost induced by
the two orders; it does not estimate performance under arbitrary or optimized
orders.

## Quantities and eligibility

For each solved, fully certified cell, define semantic-union effort, bucket
effort, fragmentation `F`, and the certificates `B_profile`, `B_width` and
`B_add` exactly as in the frozen certificate-holdout protocol.  Their
normalized forms `R_profile`, `R_width` and `R_add` divide by semantic-union
effort.  The terminal cut is excluded.  Bucket effort must not exceed any
certificate.

A task pair is eligible only when both orders solve with complete schema-v2
and profile streams, positive semantic-union effort, identical solution cost,
identical goal-fill pattern and PDB value count, identical expanded-state
count, and identical per-g active-value counts.  These identities are
preconditions, not outcomes.  A violation aborts analysis rather than
excluding the pair.

The primary comparison uses only pairs on which `F`, `R_profile`, `R_width`
and `R_add` are all strictly ordered.  It reports the fraction whose predicted
and observed order changes agree, with domains weighted equally.  Every
leave-one-domain-out calculation ranges over all 45 holdout domains.  Ties
and pairs censored by a resource limit remain visible.  Absolute certificates
against bucket effort and raw order ratios are secondary.

## Frozen gates

A promoted order-intervention claim requires primary strict pairs from at
least 30 domains and 211 tasks.  The paper may say that the cut-aligned
certificate predicts representation sensitivity to these two orders only if:

1. `R_profile` equal-domain concordance is at least 0.65;
2. all 45 leave-one-domain-out values are defined and at least 0.60; and
3. its macro concordance is no more than 0.02 below either `R_width` or
   `R_add`.

The paper may call the profile sharper under this intervention only if its
macro concordance exceeds both alternatives and both advantages remain
positive in every leave-one-domain-out analysis.  An advantage is called
material only at 0.02 or more.  Failed gates remain visible and trigger no
new ordering, threshold or task filter.

## Matrix and execution

The cohort is the exact 1,052-task, 45-domain prospective holdout.  The matrix
has two configurations and 2,104 cells.  Each cell uses the pinned planner
revision and binaries, fixed order (dynamic reordering disabled), a 300-second
aggregate process-CPU limit, and 8,192 MiB.  The run uses the `fat` partition,
Lab 8.0, and an unthrottled Slurm array.  Task manifest, option matrix,
protocol bytes, benchmark bytes, generated inputs and launch metadata are
hash-pinned before execution.
