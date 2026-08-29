# Frozen cofactor-profile predictor analysis

Status: frozen before reading any outcome from
`exp_pdb_profile_comparison`.

The raw experiment contains 1,327 tasks from 46 domains and 18
configurations.  It was launched under
`pdb-cofactor-profile-comparison-v1`; this document fixes the additional
analysis used to decide whether the paper may use an explanatory/predictive
framing.  No evaluation budget may be selected after outcome inspection.

## Scientific question

Heuristic quality can reduce the set of expanded states, while partitioning
those states by heuristic value can enlarge their decision-diagram
representation.  We therefore test two distinct claims:

1. Does cofactor structure predict *fragmentation*, measured independently of
   the amount of search guidance?
2. Does a selector that balances the frozen quality score with a cofactor
   constraint improve symbolic-search outcomes relative to matched controls?

The first claim is explanatory.  The second is algorithmic.  Neither implies
a runtime or population-level result.

## Fixed populations and eligibility

- All summaries retain the full 1,327-task denominator for coverage.
- A solved cell is eligible for fragmentation only when the schema-v2 bucket
  effort and the profile logger's semantic union effort are both complete,
  certified, nonnegative, and refer to the same solved run.  The union effort
  must be positive.  Fragmentation is
  `bucket_effort / semantic_union_effort`.
- A task-level predictor comparison uses only distinct selected heuristic
  semantics.  Repeated configurations selecting the same normalized pattern,
  cap and exact ADD profile are collapsed to one observation.  Their
  deterministic node efforts must agree or analysis fails closed.
- Predictor orderings are compared only within a task.  Ties in either the
  predictor or outcome are reported and excluded from the concordance
  denominator.  Domain summaries weight each domain equally; task-pair totals
  are also reported.
- The exact cut-aligned certificate is eligible only under the stricter
  existing certificate contract: candidate and profiled blind search solve at
  the same cost, have the same state order, and expose complete certified
  layer, heuristic and expansion profiles.
- Jointly solved effort comparisons are conditional mechanism diagnostics.
  They cannot explain coverage discordances or joint timeouts.

## Frozen predictors and directions

For each distinct selected heuristic, the following orderings are fixed.

- **Cofactor width `W`:** smaller predicts less fragmentation.
- **Global ADD proxy `U=A+T`:** smaller predicts less fragmentation.  This is
  the closest static representation control.
- **Number of finite values `V`:** smaller predicts less fragmentation.  It is
  a secondary structural baseline, not attributed to prior work as an
  established predictor.
- **Frozen information-quality tuple:** initial dead-end recognition, initial
  value, mean finite value and abstract dead-end fraction, in the selector's
  lexicographic order; larger predicts lower total expanded-BDD effort.  The
  same direction is used as an explicit-search-quality control for
  fragmentation: better quality predicts less fragmentation.  Width,
  abstract-state count and pattern tie breakers are excluded from this tuple.
- **Cut-aligned profile certificate `B_profile`:** smaller predicts lower
  expanded-BDD effort.
- **Width relaxation `B_width`** and **global-ADD Apply certificate
  `B_add`:** smaller predicts lower expanded-BDD effort.

Pairwise concordance is the fraction of strictly ordered observation pairs
whose predicted and observed orders agree.  The primary robustness summary is
the equal-domain macro mean; micro counts and leave-one-domain-out ranges are
secondary.  No p-values or confidence intervals are used because the cohort
is a fixed benchmark census rather than a probability sample.

## Frozen selector contrasts

For each matched pair
`(K,U)=(2,8),(4,29),(8,55),(16,100),(32,204)`, report:

1. cap-aware width versus cap-aware global-ADD selection;
2. cap-aware width versus exact-width selection;
3. each constrained selector versus the unconstrained exact selector; and
4. each selector versus profiled blind search.

Report full-denominator coverage discordance, conditional pooled
expanded-BDD effort, equal-domain coverage differences, raw-pool identity and
the complete theorem-certificate summaries.  All five budgets and the
unconstrained endpoint remain visible.

## Decision rules fixed before outcome access

The paper may say that cofactor width is a **useful predictor of symbolic
fragmentation** only if all of the following hold:

1. its equal-domain fragmentation concordance is at least 0.65;
2. every leave-one-domain-out value is at least 0.60;
3. it exceeds the quality tuple's fragmentation concordance; and
4. it is not more than 0.02 below the global ADD proxy.

The paper may say that the **cut-aligned profile is the sharper explanatory
metric** only if:

1. its equal-domain effort concordance exceeds both the width relaxation and
   the global-ADD Apply certificate;
2. the advantage over each is at least 0.02; and
3. both advantages remain positive under every leave-one-domain-out analysis.

The paper may say that **width-based filtering outperforms the
acceptance-matched ADD-size control** only if cap-aware width has lower
conditional pooled effort in at least four of five matched budgets, the
all-budget pooled direction agrees, no matched budget loses more than two net
coverage tasks, and every leave-one-domain-out all-budget effort direction
agrees.  Otherwise the ADD comparison is reported as mixed or negative.

The paper may call cap-aware width selection a **useful new heuristic
construction** only if it beats exact-width selection in conditional pooled
effort at at least three of five budgets, has nonnegative aggregate coverage
discordance across the five fixed comparisons, and does not reverse under
leave-one-domain-out aggregation.  The paper may not call it a generally
better planner unless it also improves full-denominator coverage over blind
search across a clear majority of budgets; runtime is always secondary.

Failure of a gate is a result, not a reason to select a different budget or
denominator.  If the gates fail, the paper retains the theory-led certificate
framing and reports the experiment as a limitation of predictive selection.

## Recovery and audit

Grouped Slurm timeouts are infrastructure failures.  After the main array
drains, enumerate every incomplete cell without reading completed outcomes,
freeze an exact recovery manifest containing the original job states and file
hashes, archive any interrupted prefixes, and rerun only missing or interrupted
cells with the original binary and cell limits.  Outcome analysis begins only
after the recovered 23,886-cell matrix passes the existing fail-closed parser
and identity gates.
