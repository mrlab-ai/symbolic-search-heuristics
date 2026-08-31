# Development protocol for the co-occurring-residual profile

Status: fixed before inspecting any schema-v2 joint-profile output beyond
single-task implementation smoke tests. This is a developmental study on the
same 275-task cohort used to repair the semantic-union measurement. It is not
confirmatory evidence and cannot promote a paper claim.

## Question

The original Cartesian profile counts every possible pair of a state-set
residual and a heuristic residual at each cut. The new joint profile counts
only pairs induced by the same prefix. For a layer set `S` and heuristic `h`,
let `J_i(S,h)` be that co-occurring-pair count and let
`J(S,h) = sum_i J_i(S,h)`, excluding the terminal cut. The implementation must
certify at every cut

    max(q_i(S), v_i(h)) <= J_i(S,h) <= q_i(S) v_i(h).

The run-level certificate is

    B_joint = sum_g |A_g| J(S_g^h,h),

with `R_joint = B_joint / semantic_union_effort`. The analysis must verify

    bucket_effort <= B_joint <= B_profile <= B_width

for every eligible run.

The pilot asks whether `R_joint` orders fragmentation better than the old
Cartesian certificate and the prespecified `1 / semantic_union_effort` null,
and whether the denominator-free `B_joint` orders bucket effort. It reports
equal-domain directional concordance and leave-one-domain-out ranges on one
shared strict-pair set for each named contrast. Ties and resource censoring
remain visible. No threshold is optimized.

## Intervention and eligibility

For each task, build the same deterministic 100,000-state goal-fill PDB and
run it under the fixed Gamer and untranslated Fast Downward orders, with
dynamic reordering disabled. The PDB pattern, finite-value count, solution
cost, expanded-state count, and per-layer active-value counts must agree
between orders. Every eligible cell must solve with complete schema-v2 search
and joint-profile streams and positive semantic-union effort. A semantic
disagreement or certificate violation aborts the analysis.

## Matrix and execution

The matrix contains 275 tasks from 46 domains, two fixed orders, and 550
cells. Each cell has a 300-second aggregate process-CPU limit and 8,192 MiB.
Execution uses Lab 8.0, the `fat` partition, and an unthrottled Slurm array.
The planner revision and binaries, cohort and option manifests, protocol
bytes, generated inputs, benchmark bytes, parser sources, and launch metadata
are hash-pinned.
