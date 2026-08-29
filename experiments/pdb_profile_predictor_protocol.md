# Frozen cofactor-profile predictor analysis

Status: frozen before reading any outcome from
`exp_pdb_profile_comparison`.  On 2026-08-30, still before outcome access, the
implementation audit made the strong-claim gates fail closed on sparse
support, exact-rational comparisons, and the full 46-domain leave-one-out
universe.  It also narrowed the blind comparison to a coverage claim.  No
threshold was selected from experiment outcomes.

The raw experiment contains 1,327 tasks from 46 domains and 18
configurations.  It was launched under
`pdb-cofactor-profile-comparison-v1`; this document fixes the additional
analysis used to decide whether the paper may use an explanatory/predictive
framing.  No evaluation budget may be selected after outcome inspection.

## Scientific question

Heuristic quality can reduce the set of expanded states, while partitioning
those states by heuristic value can enlarge their decision-diagram
representation.  We therefore test two distinct claims:

1. Does cofactor structure predict the ordinal ordering of *fragmentation* on
   eligible fixed-cohort comparisons, where fragmentation is normalized by
   the BDD size of the same expanded-state union?
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
- Predictor orderings are compared only within a task.  Each comparative gate
  uses one shared pair set on which the target and every predictor entering
  that claim are strictly ordered.  A tie in the target or in any compared
  predictor excludes the pair for all of them, preventing a predictor from
  improving its concordance by abstaining on adverse pairs.  Individual
  predictor summaries retain their own tie diagnostics, but gates use only the
  shared summaries.  Domain summaries weight each domain equally; task-pair
  totals are also reported.
- A strong predictor claim additionally requires comparable observations in
  at least two thirds of the 46 domains (31 domains) and at least one fifth of
  the 1,327 tasks (266 tasks) for every predictor entering the claim.  These
  thresholds permit genuine structural ties and censored runs while ruling
  out a claim driven by a small eligible subset.
- The exact cut-aligned certificate is eligible only under the stricter
  existing certificate contract: candidate and profiled blind search solve at
  the same cost, have the same state order, and expose complete certified
  layer, heuristic and expansion profiles.
- Jointly solved effort comparisons are conditional mechanism diagnostics.
  They cannot explain coverage discordances or joint timeouts.
- Every selector contrast entering a strong effort claim must contain at least
  266 eligible task pairs spanning at least 31 domains at every fixed budget.
  All leave-one-domain-out maps use the complete frozen 46-domain universe;
  omitting a domain with no eligible pair leaves the pooled value unchanged.

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

1. width, the quality tuple and the global ADD proxy each meet the fixed
   31-domain and 266-task support floors;
2. width's equal-domain fragmentation concordance is at least 0.65;
3. every one of the 46 leave-one-domain-out values is defined and at least
   0.60;
4. it exceeds the quality tuple's fragmentation concordance; and
5. it is not more than 0.02 below the global ADD proxy.

The paper may say that the **cut-aligned profile is the sharper explanatory
metric** only if:

1. the profile, width-relaxation and global-ADD certificates each meet the
   fixed 31-domain and 266-task support floors;
2. its equal-domain effort concordance exceeds both the width relaxation and
   the global-ADD Apply certificate;
3. the advantage over each is at least 0.02; and
4. both advantages remain positive under all 46 leave-one-domain-out
   analyses, with no missing comparison.

The paper may say that **width-based filtering has materially lower conditional
effort than the acceptance-matched ADD-size control** only if cap-aware width
has lower conditional pooled effort in at least four of five matched budgets,
the all-budget ratio is at most 0.98, no matched budget loses more than two net
coverage tasks, every leave-one-domain-out all-budget effort direction agrees,
and all five budget comparisons meet the fixed 31-domain and 266-pair support
floors.  Otherwise the ADD comparison is reported as mixed or negative.

The paper may say that **cap-aware width selection has materially lower
conditional effort than exact-width selection** only if it has lower effort at
at least three of five budgets, its all-budget ratio is at most 0.98, it has
nonnegative aggregate coverage discordance across the five fixed comparisons,
loses no more than two net coverage tasks at any budget, does not reverse under
leave-one-domain-out aggregation, and all five budget comparisons meet the
fixed 31-domain and 266-pair support floors.  The 0.98 threshold is a
pre-outcome minimum effect-size guard; exact directional wins smaller than two
percent remain visible but cannot license the stronger wording.

The paper may say only that cap-aware width selection has **higher coverage
than profiled blind search across the fixed budgets** if the material
cap-versus-exact effort gate also passes, it has positive full-denominator coverage discordance in at
least three of five budgets, the five-budget aggregate discordance is
nonnegative, and no individual budget loses more than two tasks.  This does
not license a general planner, runtime or population-level dominance claim.

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
