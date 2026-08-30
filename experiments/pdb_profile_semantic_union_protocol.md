# Semantic-union follow-up for heuristic fragmentation

Status: frozen before running the corrected semantic-union instrumentation.
The outcomes of the earlier 1,327-task profile experiment are known.  In that
experiment every solved heuristic run reported a zero semantic-union effort,
so its preregistered fragmentation gate had no eligible observations.  This
follow-up repairs that missing measurement; it does not revise a threshold in
response to a measured follow-up effect.

## Question and estimand

For one solved heuristic search, let

`F = sum of expanded bucket inner-node counts / sum of per-g expanded-union inner-node counts`.

The numerator is the existing schema-v2 effort.  The denominator is computed
from the search's existing per-g closed-list unions at termination, without
retaining an additional BDD during search.  Thus `F` isolates the
representation cost of partitioning the same expanded states by heuristic
value.  It is not a runtime, coverage, or search-space-size metric.

The primary question is whether the selected heuristic's exact fixed-order
cofactor width `W` predicts the ordinal ordering of `F` better than the frozen
information-quality tuple and approximately as well as the conventional
global ADD-size proxy `U=A+T`.

## Measurement cohort

The source population is the same frozen 1,327-task, 46-domain cohort as
`pdb-cofactor-profile-comparison-v1`.  Within each domain, tasks are ordered by
the SHA-256 digest of the ASCII bytes `domain + NUL + problem`; the first six
are selected, or all tasks when the domain contains fewer than six.  This
selects 275 tasks (six in every domain except the five-task `grid` domain).
The lexicographically sorted `domain:problem` manifest has SHA-256
`5c43a5d0891d32285c248c14cfe81ab5fa308b8eeb3d3d34e7d22ee782fcda2e`.
No old or follow-up outcome enters this selection rule.

The measurement matrix contains the 16 PDB configurations from the earlier
profile experiment: exact-width, cap-aware width, cap-aware matched-ADD, and
unconstrained exact selection.  The five fixed width budgets remain
`2,4,8,16,32`; the matched ADD budgets remain `8,29,55,100,204`.  The matrix
therefore contains 4,400 cells.  Search limits remain 300 seconds and 8,192
MiB per cell.

## Eligibility and identity

A cell is eligible only if it solves, has a complete certified schema-v2
bucket stream, has a complete profile stream, reports a positive semantic
union effort, and satisfies all fixed source, binary, option, task, selected
heuristic, solution-cost, and event-conservation checks.  For every eligible
cell, both efforts must be nonnegative.  Their ratio is not constrained to be
at least one because an Apply-produced union can itself be larger than the sum
of its input diagrams.  Duplicate configurations selecting the same normalized
pattern, cap, exact ADD profile, and quality tuple are collapsed within a task;
their deterministic numerator and denominator must agree exactly.

All comparisons are within-task pairs of distinct selected heuristic
semantics.  A comparison enters the shared primary set only when
fragmentation, cofactor width, total ADD size, and the quality tuple are all
strictly ordered.  Ties exclude the pair for every predictor.  Domain means
weight eligible domains equally.  Leave-one-domain-out calculations range
over the full 46-domain measurement universe, including domains with no
eligible pair.

## Frozen predictors and gate

- Smaller cofactor width predicts smaller fragmentation.
- Smaller total ADD size predicts smaller fragmentation.
- Better frozen information quality predicts smaller fragmentation.
- The number of finite heuristic values is a secondary predictor only.

The paper may call cofactor width a useful fragmentation predictor only if all
of the following hold:

1. the shared set contains comparable pairs from at least 31 domains and at
   least 184 distinct tasks;
2. width's equal-domain concordance is at least 0.65;
3. every leave-one-domain-out width concordance is defined and at least 0.60;
4. width's equal-domain concordance exceeds the quality tuple's; and
5. width is no more than 0.02 below total ADD size on the same shared pairs.

The analysis also reports micro counts, all ties and exclusions, each domain,
the finite-value baseline, coverage on the fixed 275-task denominator, and
instrumentation overhead.  There are no p-values, confidence intervals, or
population claims.

## Consequence for algorithm development

If and only if the predictor gate passes, its measurement cohort may be used
to design one fragmentation-aware selector.  The selector, all hyperparameters
and an evaluation protocol must then be committed before launching it on the
remaining 1,052 tasks.  Those tasks are prospective for the new selector's
outcomes, but they are not described as a pristine benchmark holdout because
outcomes of older algorithms on the same tasks are already known.

If the gate fails, no new selector is tuned to rescue the claim.  The paper
retains the theory-led framing and reports both failed predictor experiments.

## Execution and recovery

The planner revision and binaries are pinned after the focused acceptance
tests pass and before matrix construction.  Array layout, resource requests,
runtime environment, external-validator identity, option matrix, task
manifest, and parser hashes are sealed before launch.  Recovery may rerun only
cells identified by file completeness and scheduler state without reading
planner outcomes.  Analysis begins only after the exact 4,400-cell matrix is
complete and hash-verified.
