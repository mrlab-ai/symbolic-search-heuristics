# Prospective protocol for unseen Gamer-order seeds

Status: fixed before generating or inspecting any planner output for Gamer
ordering seeds 1, 2, 3, or 4. The benchmark tasks have been measured in prior
studies; the representation perturbations are new. This is therefore an
unseen-order validation, not an unseen-task holdout.

## Claims and estimands

The experiment holds one deterministic 100,000-state goal-fill PDB and every
search decision fixed while changing only the random seed used by the Gamer
variable-order multi-start optimization. For each task and seed pair, the
response is the direction of the change in normalized bucket fragmentation

    F = bucket_effort / semantic_union_effort.

For a layer set `S`, heuristic `h`, and cut `i`, the co-occurring profile uses

    j_i(S,h) = |{(chi_S|rho, h|rho) : rho is a length-i prefix}|.

Its run certificate is

    B_joint = sum_g |A_g| sum_i j_i(S_g,h),
    R_joint = B_joint / semantic_union_effort.

The primary test compares `R_joint` with the prespecified denominator-only
null `1 / semantic_union_effort` on one shared strict-pair set. Secondary
tables compare the Cartesian profile, maximum-width and total-ADD relaxations
on another shared strict set, and compare their unnormalized certificates
with absolute bucket effort. No predictor, threshold, subset, or response may
be substituted after launch.

## Frozen perturbations and eligibility

The four seeds are 1, 2, 3, and 4. They are the first four positive integers,
were not screened on any task, and had not produced planner output when this
protocol was frozen. Seed 0 remains the legacy implementation and appeared in
development; it is excluded here. Dynamic reordering is disabled.

A task enters the representation comparison only if all four cells solve with
complete certified schema-v2 search and profile streams and positive semantic
union effort. The PDB pattern, finite-value count, solution cost, expanded
state count, and the active heuristic-value count at every cost layer must be
identical across seeds. Any disagreement or certificate violation aborts the
analysis. Pairwise comparisons whose variable-order digests are identical are
reported and cannot become strict evidence.

Every named comparison uses within-task seed pairs. A shared strict set drops
a pair for all predictors in that comparison if the response or any named
predictor ties. Concordance is computed within each domain and domains receive
equal weight. All leave-one-domain-out values are reported.

## Decision rule

The primary claim passes only if its shared strict set contains at least 150
seed pairs from at least 75 tasks and 25 domains, `R_joint` has equal-domain
concordance at least 0.65, exceeds the inverse-union null by at least 0.02,
and is no worse than that null in every leave-one-domain-out replicate. The
absolute-certificate check is secondary and passes at concordance at least
0.65 on at least the same support floors. A failed primary rule forces a
theory-first paper and forbids a headline empirical predictor claim.

## Population and execution

The matrix contains the previously sealed 1,052-task, 45-domain remeasurement
cohort and four configurations, for 4,208 cells. Each cell has a 300-second
aggregate process-CPU limit and 8,192 MiB. Execution uses Lab 8.0, the `fat`
partition, normal QoS, one CPU and 9 GiB per Slurm task, and an unthrottled
array. The outer Slurm allowance is 30 minutes so five serial cells and their
wrapper overhead fit without changing the fixed planner limit. The planner
commit and binaries, cohort and option manifests, generated inputs, benchmark
bytes, parser sources, and launch metadata are hash-pinned. Scheduler-failed
cells may be rerun only by exact array index with unchanged planner options;
interrupted files and every recovery receipt are retained.
