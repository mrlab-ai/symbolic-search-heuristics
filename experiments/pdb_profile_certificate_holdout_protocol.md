# Prospective cut-aligned certificate validation

Status: frozen before launching any cell in the 1,052-task holdout.  Outcomes
from the earlier 1,327-task profile experiment and the corrected 275-task
semantic-union follow-up are known.  The follow-up is used only as a disclosed
development set for the formulas, diagnostics and fixed gates below.  The
remaining tasks have not been run with the corrected semantic-union
instrumentation.

## Questions

The experiment separates two effects of a heuristic in product-at-evaluation
forward symbolic A*.

1. Does the frozen information score order semantic search reduction, measured
   by expanded-state count and by the BDD effort of the corresponding per-g
   expanded unions?
2. Does the paper's cut-aligned cofactor-profile certificate order the
   additional BDD cost of representing those unions as heuristic-value
   buckets?
3. Is the cut-aligned certificate at least as predictive as its static width
   relaxation and the conventional total-ADD Apply certificate?
4. Do the previously fixed cap-aware, exact-width and matched-ADD selectors
   reproduce their multi-budget behavior on the holdout?

The first three questions are mechanistic.  They do not claim to predict
coverage, runtime or peak memory.  The fourth is an algorithmic replication,
not a new selector-tuning exercise.

## Quantities

For one solved heuristic run, let S_g be the semantic union of all value
buckets expanded at path cost g, and let V_g be the number of those buckets.
The profile stream records the cofactor counts c_i(S_g), the selected
heuristic counts c_i(h), the BDD size b_g of S_g and V_g.  The terminal cut is
used for stream validation and excluded from every paper certificate.

The observed fragmentation response is

    F = bucket_effort / sum_g b_g.

The three cumulative certificates are

    B_profile = sum_g V_g sum_i c_i(S_g)c_i(h),
    B_width   = sum_g V_g W sum_i c_i(S_g),
    B_add     = sum_g V_g [2(A+1)b_g + A],

where W is the exact cofactor width and A is the number of inner ADD nodes.
The normalized predictors R_profile, R_width and R_add divide the respective
certificate by sum_g b_g.  Every eligible cell must satisfy bucket_effort no
larger than each certificate.  Any violation aborts the analysis.

The frozen information score is the selector tuple consisting of initial
dead-end recognition, initial value, mean finite value and abstract dead-end
fraction.  Larger predicts fewer expanded states and less per-g union effort.
It remains an information surrogate rather than a universal definition of
heuristic accuracy.

## Cohort and configurations

The source population is the frozen 1,327-task, 46-domain complement used by
the earlier profile comparison.  Remove the exact 275-task development cohort
selected by the corrected follow-up.  This leaves 1,052 tasks in 45 domains;
Grid has no remaining task.  No outcome enters this subtraction.

The matrix contains profiled blind search and the same 16 PDB configurations
as the corrected follow-up: exact-width, cap-aware width and cap-aware
matched-ADD selection at the five fixed budgets, plus unconstrained exact
selection.  Limits remain 300 seconds and 8,192 MiB per cell.  All runs use
the same pinned planner binary, product-at-evaluation forward search and the
task-specific fixed Gamer order.  The matrix therefore has 17,884 cells.

## Eligibility and pair construction

A heuristic cell is eligible only if it solves, has complete certified
schema-v2 and profile streams, has positive semantic-union effort, conserves
all per-g events and agrees on the selected heuristic across selector,
schema-v2 and profile records.  Duplicate configurations selecting the same
pattern, cap, heuristic profile and information score collapse within a task;
their deterministic observations must agree exactly.

All predictor comparisons use within-task pairs of distinct heuristic
semantics.  Each comparison has one shared strict-pair set: a target tie or a
tie in any compared predictor excludes that pair for every predictor in that
comparison.  Domains are weighted equally.  Leave-one-domain-out calculations
range over all 45 holdout domains, including a domain with no eligible pair.

The representation comparison uses F against R_profile, R_width and R_add.
A second shared set compares R_profile with the information score on F.  The
guidance comparison uses expanded-state count and per-g union effort against
R_profile and the information score.  Absolute B_profile, B_width and B_add
against bucket effort are secondary because they mix search reduction and
fragmentation.

## Frozen gates

Every promoted mechanistic claim requires comparable pairs from at least 30
domains and 211 tasks.

The paper may call the cut-aligned certificate a useful predictor of
fragmentation only if:

1. R_profile equal-domain concordance is at least 0.70;
2. every one of its 45 leave-one-domain-out values is defined and at least
   0.65;
3. R_profile exceeds the information score by at least 0.20 in the shared
   profile-versus-information comparison, and the advantage remains positive
   in every leave-one-domain-out analysis; and
4. on the shared representation comparison, R_profile is no more than 0.02
   below either R_width or R_add.

The paper may additionally call the cut-aligned certificate the sharper
representation predictor only if its macro concordance exceeds both R_width
and R_add and both advantages remain positive under every leave-one-domain-out
analysis.  It may call either advantage material only when it is at least
0.02.

The paper may describe a two-effect separation only if, on both guidance
targets, the information score has macro concordance at least 0.80, every
leave-one-domain-out value is at least 0.75, and it exceeds R_profile by at
least 0.20; on F, R_profile must simultaneously exceed the information score
by at least 0.20.  Every direction must remain positive in all
leave-one-domain-out analyses.

The fixed selector replication retains the earlier gates.  A width-based
selector can be called materially better than its matched ADD control only if
it has lower conditional bucket effort at four of five budgets, pooled effort
ratio at most 0.98, no budget loses more than two net coverage tasks and every
budget meets the support floor.  Cap-aware width can be called materially
better than exact width only if it has lower effort at three of five budgets,
pooled ratio at most 0.98, nonnegative aggregate coverage discordance and no
budget loses more than two net coverage tasks.  Otherwise the fixed curves
are reported as mixed.

No individual budget may substitute for a failed all-budget gate.  Failed
gates remain visible and do not trigger threshold changes, a rescue metric or
new selector tuning on this cohort.

## Execution

The planner revision, binary hashes, benchmark bytes, task manifest, option
matrix, protocol bytes, Lab version, resource requests and unthrottled Slurm
layout are pinned before launch.  The run uses the fat partition and contains
no array concurrency cap.  Recovery may rerun only cells selected from file
completeness and scheduler state without reading their planner outcomes.
Analysis begins only after the exact matrix is complete and hash-verified.
