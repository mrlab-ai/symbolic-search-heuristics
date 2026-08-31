# Prospective terminal-incidence shadow protocol

This document freezes the experiment before any outcome from its selected
tasks is inspected. The study asks whether terminal incidence explains the
representation cost of partitioning a symbolic frontier by heuristic value
more sharply than the previously proposed cofactor-product certificates.

## Scope and separation from prior evidence

The cohort is selected from benchmark bytes at downward-benchmarks commit
`48d6a00d482de2384a9e751f9343df58bf5582be`. Its 460 problem-file SHA-256
digests are disjoint from all 1,525 unique problem hashes in the frozen 1,697
task `suite_wbh` source manifest and from every checked-in or archived prior
experiment audited before freezing this protocol. No result on a selected
task may be read before the protocol, option matrix, source attestation,
planner revision, binaries, and launch receipt are pinned.

The deterministic seed is
`symbolic-search-heuristics/fixed-frontier-shadow-cohort/v1`. For each of the
46 frozen benchmark directories, candidates are source-attested, previously
seen names and problem hashes are removed, and candidates are ordered by

`SHA256(seed NUL directory NUL problem_sha256 NUL problem_name), problem_name`.

The first ten candidates whose problem hash has not already been used in the
new cohort are retained. The final 460 records are sorted by `(domain,
problem)`. Exact hashes for task names, source paths, contents, records,
directory order, and the directory-to-family map are constants in the Python
protocol.

The 46 directories collapse, before outcomes, to 26 conservative IPC domain
families. Family-level inference uses these 26 families; directory-level
results are secondary.

## Source support audit

All selected PDDL files are parsed with the pinned translator source. For a
nonmetric task, the translator's established no-metric branch proves that
every serialized operator has unit cost. Every metric task is translated in
full to SAS v3 and every serialized operator cost is parsed; the task is
eligible only if every cost is strictly positive. Every task is normalized
with the translator's default `axiom_based` normalization and is eligible only
if it has zero normalized axioms. The exact 460-task attestation is hashed and
is a launch precondition. There is no task replacement after this audit.
The audit is rerun as 46 unthrottled tasks on the `fat` partition. Before
submission, an exclusive intent pins the Slurm script, every executed Python
source, the interpreter, installed distributions, benchmark revision, cohort,
translator tree, and clean Jujutsu commit. Both submission and Slurm use
`export=NONE`; the job then installs a fixed `PATH`, disables the user site,
unsets inherited Python environment variables, and verifies the absolute
Python and `sha256sum` executables. All 46 tasks must complete, and
independently assembling their fresh shards must reproduce the frozen
attestation byte for byte. The shard/log tree is hashed both before and after
assembly and must be unchanged. The intent, launch receipt, scheduler rows,
shard/log tree, environment contract, and execution receipt are all hashed.

## Frozen measurements

Each task is run with five direct PDB configurations, all with a 100,000-state
PDB budget, Fast Downward variable ordering (`gamer_ordering=false`), dynamic
reordering disabled, the schema-v2 expansion stream, and schema-v3 cofactor
profiling. `shadow_partition=true` constructs and measures the PDB but executes
the same forward uniform-cost search in every configuration; the heuristic
does not prune, order, split, or otherwise guide the search.

The primary four-configuration generator panel is:

1. BDD-order prefix;
2. goal-order prefix;
3. goal-order fill;
4. CEGAR with seed 2011 and a 10-second generator limit.

A fifth, separately preregistered intervention applies `value_cap=8` to the
goal-fill PDB. It tests the terminal-coarsening theorem and is not included in
primary predictor selection.

Planner limits are 300 seconds and 8,192 MiB per cell. Slurm uses one CPU,
9 GiB per CPU, 20 minutes per array element, normal QoS, the `fat` partition,
three sequential cells per array element, and no array throttle. The runner
uses Python 3.12 and Downward Lab 8.10 from the separately pinned environment
manifest.
After the array completes, immutable run inputs and raw cell outputs are sealed
before parsing. Parsing and fetching each write an exclusive pre-operation
intent before Lab may mutate output, then an exclusive receipt and external
SHA-256 pin. Every downstream validation rehashes both immutable inputs and its
upstream artifacts. The confirmatory analyzer accepts only the resulting
sealed evaluation file and writes its result exclusively without overwrite.

## Eligibility and fixed horizon

The analysis horizon is the first 16 completed non-goal blind layers in
increasing `g` order; positive operator costs need not make the observed `g`
values consecutive. This horizon was selected from old data only. A whole task
is eligible only if all four primary cells have a complete certified schema-v3
prefix through 16 such layers, or if all four solve after fewer than 16
pre-goal layers with the same optimal cost and identical complete pre-goal
layer sequence. A terminal timeout or resource exit after the 16th retained
layer does not discard that already completed prefix. A single syntactically
incomplete trailing log line from such an exit is discarded before validating
the retained prefix. Any other malformed prefix, missing retained layer,
construction failure, exit before the horizon, or inconsistent solution cost
excludes the whole task.

The four primary cells must have the same variable-order SHA-256 and the same
heuristic-independent frontier identity at every retained layer: `g`, union
BDD inner-node count, state cofactor vector SHA-256, and the full state
cofactor vector. The schema-v2 blind expansion trace must also agree on its
blind layer effort. Any mismatch is a protocol failure, not an exclusion.

PDB construction failures and CEGAR fallback are retained as declared
outcomes. A construction failure in any primary cell excludes the task under
the eligibility rule above. Within an eligible task, only configurations with
a completed, certified PDB identity and complete retained measurements
contribute heuristic pairs. Duplicate PDB semantics within a task are
collapsed before pair formation using the pattern, cap, and complete heuristic
cofactor identity.

## Target and predictors

For every retained layer `L_g`, the audit-only target is the exact partition
effort

`E_g = sum_v |BDD(L_g intersect h^{-1}(v))|`.

The primary predictor is terminal incidence

`I_g = sum_u |T_A(u)|`,

where `u` ranges over regular inner nodes of the reduced masked ADD
`m(x)=h(x)` on `L_g` and a fresh bottom terminal off `L_g`, and `T_A(u)` is the
set of reachable nonbottom terminals active on the layer. Run-level values
sum over retained layers without an additional active-value multiplier:
`E=sum_g E_g` and `I=sum_g I_g`.

The preregistered controls, computed on the same layers, are:

- masked ADD product `kD=sum_g k_g D_g`, where `D_g` is the number of
  regular inner nodes in the masked ADD;
- masked cofactor relaxation `mQ=sum_g k_g sum_{i<n} c_i(m_g)`;
- masked joint relaxation `mJ=sum_g k_g sum_{i<n} j_i(L_g,h)`;
- Cartesian relaxation `C=sum_g k_g sum_{i<n} c_i(L_g)c_i(h)`;
- width relaxation `W=sum_g k_g width(h) sum_{i<n}c_i(L_g)`;
- ADD apply relaxation `A=sum_g k_g(2(D_h+1)|L_g|+D_h)`.

The unmultiplied masked ADD node count is diagnostic only and is not a
predictor. The exact partition effort is a target/oracle only and is never
used as a predictor or selection feature.

Every certificate identity and inequality is rechecked. In particular,
`E <= I <= kD <= kQ(m) <= kJ(L,h)` must hold layerwise, with the parser's
support, terminal, bottom, and dynamic-order checks. Any violation aborts the
analysis.

## Comparison and confirmatory gates

Within each eligible task, predictors are compared over one grand-shared set
of semantic PDB pairs for which the target and every predictor are strictly
ordered. Ties and exclusions are reported separately. Concordance is computed
taskwise, then aggregated within each of the 26 families, then macro-averaged
with equal family weight. A 46-directory macro is secondary. Absolute target
orientation (`E`) and size-normalized orientation (`E/U`, where `U` is the
common blind union effort) must agree; within a fixed task the denominator is
constant, so disagreement is a protocol failure. The inverse-`U` null is tied
within task and is reported as such.

The strong terminal-incidence claim passes only if all conditions hold:

- at least 300 eligible tasks, at least 300 tasks and 25 of 26 families
  contributing grand-shared strict pairs, at least 25 eligible families, and
  at least 600 such pairs;
- equal-family macro concordance of `I` is at least 0.65;
- `I` exceeds each of `kD`, `mQ`, `mJ`, Cartesian, width, and ADD by at least
  0.02;
- for each control, a paired family bootstrap with 10,000 replicates and seed
  20260831 has a strictly positive 95% lower confidence bound for the
  `I-control` macro difference;
- every one-family-out difference over families with at least one
  grand-shared strict pair between `I` and every control is strictly positive;
- absolute and normalized orientations produce identical pair order and gate
  decisions.

No threshold, family map, horizon, cohort, predictor formula, normalization,
pair filter, seed, or fallback analysis may be tuned after results are read.
If the gate fails, the result is reported as a failed mechanistic hypothesis;
there is no rescue panel.

Secondary, non-gating diagnostics report certificate tightness as `E/P` for
every predictor `P` (with `0/0` defined as one), averaged first over distinct
semantic PDBs within task, then over tasks within family, and finally with
equal family weight. Family quartiles use the nearest-rank rule. They also
compare the logged time for masked ADD construction, masked cofactor profiling,
and terminal-incidence traversal with the separately timed exact per-value
partition audit. Timing is reported as pooled totals and as an equal-family
mean of taskwise ratios; it is descriptive and does not enter the primary gate.

## Intervention and downstream guided study

The cap-8 intervention is analyzed only after the primary gate, using the same
fixed frontier. For each task where uncapped and cap-8 goal-fill semantics are
both certified, report the change in active terminal count, terminal incidence,
and exact partition effort. On a fixed frontier, cap-8 is a terminal relabeling
of the masked ADD followed by reduction. It therefore cannot increase the
active terminal count or terminal incidence; an increase in either certificate
is an implementation or analysis failure. The analysis also checks the other
forced numerical consequences available in the frozen logs: bottom
reachability is unchanged, while masked ADD nodes, masked and joint cofactor
counts, and whole-heuristic cofactor counts do not increase. These are checks
of observed consequences; the cap identity itself follows from the fixed
planner construction and is not inferred from those summaries. Exact partition
effort is a separate diagnostic and may change in either direction: a reduced
BDD for a union can be larger than the sum of the reduced BDDs for its disjoint
pieces.

Only if the complete primary gate passes may a separate, prospectively frozen
guided-search experiment be launched. The shadow result alone supports a
representation-mechanism claim, not a runtime, coverage, or search-guidance
claim. The earlier multi-seed failure of the joint cofactor metric remains a
falsification result and is not hidden or reclassified.
