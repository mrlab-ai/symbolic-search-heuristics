# Width-Bounded Heuristics -- Experiments

Downward Lab experiments for the width-bounded-heuristics paper (PR5).

## Setup

```
uv venv experiments/.venv --python 3.9
uv pip install --python experiments/.venv/bin/python lab
export DOWNWARD_BENCHMARKS=~/projects/benchmarks   # aibasel/downward-benchmarks
```

Unless a script pins `C.REV`, experiments build the planner at the current
Git revision via Downward Lab's cached-revision mechanism. Do not infer an
archived binary from the current branch or current script: use each Lab
record's `global_revision` and `local_revision`. LP support (CPLEX) must be
available at build time (see `REVISIONS.md`).

## Running

Local dry run (Gripper + Miconic, short limits):

```
WBH_LOCAL=1 experiments/.venv/bin/python experiments/exp_q1.py build start parse fetch report
open experiments/data/exp_q1-eval/report.html
```

Full sweep on Tetralith (from the NSC login node; **do not launch without
sign-off**). Set your allocation first:

```
export WBH_EMAIL=you@liu.se WBH_ACCOUNT=naiss-...   # edit exp_common.get_environment()
experiments/.venv/bin/python experiments/exp_q1.py   # lists steps; run them in order
```

Limits: 30 min, 8 GiB per run (Fiser et al.); shortened to 60 s / 4 GiB when
`WBH_LOCAL=1`.

## Files

- `suite_wbh.py` -- optimal-track source suite (see delta note below); `SMOKE`
  for dry runs.
- `suite_wbh_operator_costs.json` (plus `.sha256`) -- frozen
  translator-attested classification of all 1697 suite tasks into 1407
  positive-cost and 290 zero-cost tasks; 1684 records use direct SAS v3 scans
  and 13 use the pinned no-metric/unit-cost proof described below.  Independent
  normalized-axiom evidence identifies the 1377 positive-cost tasks supported
  by the comparison protocol. `suite_cost_manifest.py` validates it for
  consumers.
- `generate_suite_cost_manifest.py` -- shardable Fast Downward translator
  scanner, deterministic assembler, and source-aware manifest validator.
- `wbh_parser.py` -- fail-closed Downward Lab parser for the `wbh.jsonl`
  instrumentation. For every explicit schema it reuses
  `validate_wbh_log.py` to check the exact v2 shape, producer invariants, and
  event/summary agreement. Rejected summaries never overwrite event-derived
  diagnostics and cannot set `raw_metrics_complete` or
  `piece_metrics_certified`. Planner-output versus WBH solved/cost
  disagreements invalidate the outcome, preserve the stdout cost, and add an
  unexplained-error diagnostic. Prospective runs carry
  `metrics_validation_protocol=wbh-exact-schema-semantic-v1`.
- `validate_wbh_log.py`, `test_wbh_parser.py` -- shared syntactic/semantic
  validator and synthetic acceptance/mutation tests (including exact-union
  contour batching, partial streams, counter forgeries, and effort checks).
  From the checkout root, run
  `experiments/.venv/bin/python experiments/test_wbh_parser.py -v`.
- `exp_common.py` -- shared environment / algorithms / parser / steps.
- `exp_q1.py` .. `exp_q4.py` -- one experiment per research question.
- `../misc/gen_pin.py` -- generates the Speck et al. (2020) Pi_n family
  (`WBH_PIN_DIR` points Q1 at the generated tasks).
- `run_baseline.py`, `check_*.py` -- PR0-PR4 acceptance/smoke scripts (not lab).

## Suite delta note (important for the paper)

Following Speck et al. (2020), `suite_wbh.py` defines a 1697-task PDDL source
universe. Pathways contains ADL disjunctions that the pinned translator's
default normalization turns into axioms. The frozen cost evidence finds 1407
positive-cost and 290 zero-cost tasks.  With the translator's pinned default
`axiom_based` normalization, the 30 positive-cost `pathways` tasks acquire
normalized axioms and are unsupported by the implemented heuristics.  The
paper's fair comparisons therefore use the remaining 1377 tasks that are both
positive-cost and normalized-axiom-free; `pathways` is not relabeled as
zero-cost. These properties are source-derived, not planner-outcome inferences:
they are frozen in `suite_wbh_operator_costs.json` and loaded by
`postprocess.py` and `combined_coverage.py`.

The generator pins planner revision
`ec8399257de93e0739046a187af4bed0b85e19ce` and downward-benchmarks revision
`48d6a00d482de2384a9e751f9343df58bf5582be`.  For 1684 tasks it invokes
`python -m translate` without translator options and parses every SAS v3
operator cost.  The 13 pinned resource-heavy organic-synthesis task
translations use the same translator's PDDL parser to require
`use_min_cost_metric=false`; the
pinned `actions.py`/instantiation/SAS path then proves every serialized
operator has unit cost.  Records include a method tag, exact PDDL paths and
hashes, and the proof-source hash.  Both methods classify a task as zero-cost
iff at least one serialized operator has cost 0.  Every record also stores the
exact number of axioms after parsing those PDDL bytes and applying the pinned
default `axiom_based` normalization, with the strategy and normalization-source
hash in provenance. Work is shardable for grid use; after assembling, validate
the frozen file and source checkout with:

```
experiments/.venv/bin/python experiments/generate_suite_cost_manifest.py \
  validate --benchmarks "$DOWNWARD_BENCHMARKS"
```

The manifest's whole-file SHA-256 is stored in the adjacent `.sha256` file.
`suite_cost_manifest.py` independently hard-pins both that whole-file digest
and a canonical-record digest, so coordinated edits to the JSON and sidecar
still fail closed before any result consumer uses the classification.
Future frozen experiment scripts can call
`suite_cost_manifest.validate_task_sources(tasks, benchmark_root)`, where each
task is `(domain, problem, domain_file, problem_file)`.  The helper validates
canonical relative paths and both PDDL byte hashes, then returns a deterministic
SHA-256 for the requested task subset that can be recorded as an attestation.

## Mutex pruning (pitfall #3)

The archived Q1 commands did **not** set `mutex_type`. At their recorded
revision (`0d3fd43e9d88a0a802e1fdc2770070c18d6e7ffe`) this means SymK's
default `MUTEX_EDELETION`, not `MUTEX_NOT`. The archive therefore is not a
pruning-disabled replication of Speck et al. A prospective no-mutex run must
set `mutex_type=MUTEX_NOT` explicitly and use a new experiment name; never
reinterpret the existing Q1 archive. Q2/Q3 likewise use the SymK default
unless their command line says otherwise.

## Q2 "unbounded" cap

The integer MIP needs a finite box, so "unbounded" uses a large-but-tractable
cap (`UNBOUNDED_CAP = 10000` in `exp_q2.py`). The heuristic width saturates once
the cap exceeds the LP optimum magnitude (empirically ~m=100 on small tasks),
while the MIP solve time grows with the cap (a 1e6 box makes CPLEX hang even on
Gripper). State this approximation when reporting the "unbounded" column.

## Audited candidate experiments

The post-audit experiments use immutable task manifests at 300 seconds and
8192 MiB per run:

- `exp_ms_caps_pilot.py` is the original 50-task, outcome-enriched cap screen
  (350 cells) at planner revision `ec839925...`. Its manifest SHA-256 is
  `c63a59ee...`; the archive categories are coverage-discordant cases, not
  attested timeout or memory causes. Because this pilot was already launched,
  its run records do not contain the new cost-manifest or PDDL-byte hashes;
  those in-run source attestations apply only to the prospective c280 screens.
- `analyze_ms_caps_pilot.py` freezes the promotion rule before results are
  inspected: among K in {2,4,8,16,32}, maximize pilot solved count, then
  minimize micro-task PAR2 with construction charged, then choose smaller K.
  Exact M&S and blind search are comparators, not candidates.
- `exp_heuristic_choices_pilot.py` is an unlaunched 21-configuration,
  1050-cell screen at planner revision `c2800d7e...`. It crosses exact, cap-8,
  and cap-16 M&S with contour windows 0/4/16, includes pruning-only M&S, and
  screens BDD-order versus goal-directed PDBs plus rectified M=8 and M=16
  potentials, each with windows 0/4/16. Every M&S command spells out
  `align_merge_order=false`; every potential command
  spells out `all_states_objective=false,lpsolver=cplex`, so those
  research-relevant defaults cannot drift silently. Before any non-help Lab
  step, the runner validates the frozen operator-cost manifest and the actual
  PDDL bytes for all 50 tasks, then records both source hashes in every run.
- `analyze_heuristic_choices_pilot.py` is the read-only promotion gate for
  exactly those 1050 cells. It hard-checks revision `c2800d7e...`, 300 s,
  8192 MiB, manifest digest, all 21 exact component options, the reproducible
  task-order seed, both source attestations, and the driver/outer-scheduler
  envelopes. Solved costs must agree. The emitted selection artifact carries
  the attested 50-task source hash and full cost-manifest hash. Within each of
  M&S (excluding the `blind_fw` and `ms_exact`
  controls), PDB, and potential, it promotes at most one configuration by:
  maximum solved count; minimum suite-micro PAR2 with construction charged;
  lower total completed image calls only if every family cell has a complete,
  schema-v2, convention-compatible counter; then lexicographic label. Partial
  counters from killed runs never enter the tie-break.
- `exp_ms_caps_validation.py` is an unlaunched 92-task, name-selected
  validation (644 cells) at `c2800d7e...`. Its manifest first retains only
  source-attested supported tasks in each of the 46 domains with at least two,
  then excludes the cap pilot and the development/acceptance smoke suite. Its
  normalized SHA-256 is
  `daca0c3b...`. The pilot-selected K versus exact M&S is the sole primary
  held-out contrast; selected K versus blind is secondary, and results for the
  other four caps are exploratory and must be labeled as such. The runner
  freezes the exact seven-option
  matrix hash and records the frozen cost-manifest hash plus byte-validated
  task-source attestation.
- `analyze_ms_caps_validation.py` is the pre-launch-frozen cap-v2 analysis.
  It requires and fully validates the separate cap-pilot properties, derives K
  using the already-declared pilot rule, then validates all 644 cap-v2 cells,
  static provenance, source hashes, and solved-cost agreement. Selected-K
  versus exact M&S is primary, selected-K versus blind is secondary, and every
  other K is explicitly exploratory. Its supported positive-cost, axiom-free
  set is the primary estimand; no new held-out choice is made.
- `heuristic_finalists_validation_suite.txt` is a second, prospectively
  reserved 92-task set (two name-hash-selected supported tasks in each of 46
  eligible domains), disjoint from the pilot, smoke, and cap-validation
  manifests. Its normalized SHA-256
  is `fc63d4ee...`.
- `exp_heuristic_finalists_validation.py` will run `blind_fw`, `ms_exact`, the
  independently pilot-selected cap, and the one promoted finalist from each
  family on that reserved set. Identical search strings are deduplicated,
  so the frozen artifact contains 5--6 unique configurations and 460--552
  runs. The runner refuses placeholders and inconsistent selections: it checks
  both pilots' canonical properties hashes, selection-rule identifiers, full
  option matrices and their hashes, revision/limits, finalist membership,
  reserved-manifest reconstruction and paths, the frozen operator-cost
  manifest hash, byte-validated source attestations for both the 50-task
  screen and 92-task reserved set, and the exact derived run count.
- `analyze_heuristic_finalists_validation.py` is the read-only analysis gate
  frozen before launch. It revalidates the selection artifact, exact dynamic
  matrix, per-run provenance, revision/limits, source attestations, and solved
  costs; it never selects or ranks on held-out outcomes. It emits the
  predeclared contrasts on the supported positive-cost, axiom-free 92-task set.

The primary estimand is the cap-pilot-selected K versus exact M&S on the
`exp_ms_caps_validation.py` cap-v2 set. The finalist-versus-control contrasts
on `heuristic_finalists_validation_suite.txt` are secondary and family-wise:
one promoted member per family, compared with the frozen `blind_fw` and
`ms_exact` controls. For each contrast, the primary metric is paired coverage
aggregated by domain first (candidate-minus-control coverage within each
domain, then an equal-weight mean over the 46 domains). The task-weighted
suite-micro coverage difference is descriptive. Runtime and PAR2 are screening
statistics only because there is one repetition; all nonselected caps and all
nonpromoted screen configurations are exploratory. The additional
post-stratified coverage difference is also descriptive: compute each sampled
domain's paired difference first, then weight those domain means by that
domain's task count in the frozen 1377-task supported positive-cost,
axiom-free population and renormalize over represented domains.

Every paired domain-macro contrast also reports discordant task wins/losses
and a deterministic 95% domain-cluster percentile bootstrap interval. The
protocol uses 10,000 replicates, seed
`symbolic-search-heuristics/domain-cluster-bootstrap/v1`, and the frozen
`sha256-seeded-splitmix64-percentile/v1` sampler. Each replicate samples the
observed domains with replacement and averages their within-domain paired
coverage differences; endpoints are ordered replicates at
`floor(.025*(R-1))` and `ceil(.975*(R-1))`. This interval applies to the
domain-macro statistic, not the descriptive micro or post-stratified values.

After both pilots finish, generate the selection artifact directly from both
validated properties sources (to stdout), then review/freeze the redirected
JSON before validation:

```
experiments/.venv/bin/python experiments/analyze_heuristic_choices_pilot.py \
  data/exp_heuristic_choices_pilot-eval/properties \
  --cap-properties data/exp_ms_caps_pilot-eval/properties \
  --emit-selection-artifact > heuristic-finalists-selection.json

experiments/.venv/bin/python experiments/exp_heuristic_finalists_validation.py \
  --selection heuristic-finalists-selection.json --check

# After cap-v2 finishes; K is always rederived from the frozen pilot.
experiments/.venv/bin/python experiments/analyze_ms_caps_validation.py \
  data/exp_ms_caps_validation-eval/properties \
  --cap-properties data/exp_ms_caps_pilot-eval/properties

# After the reserved runs finish; this command performs no new selection.
experiments/.venv/bin/python experiments/analyze_heuristic_finalists_validation.py \
  data/exp_heuristic_finalists_validation-eval/properties \
  --selection heuristic-finalists-selection.json
```

`--print-template` shows the artifact schema but deliberately emits invalid
zero hashes and no selection. No outcome-derived artifact is checked in yet.
Lab reconstructs an experiment for every requested step, so `--check`, build,
start, parse, fetch, and report all rerun manifest/path/source attestation and
require the frozen cost manifest plus the matching benchmark checkout.
All future shared SymK experiments use the deterministic task-order seed
`symbolic-search-heuristics/c280-task-order/v1`; they retain randomized order
without Lab's process-global random seed. Run records include this seed, the
planner driver limits (`driver_time_limit`/`driver_memory_limit`), and the
outer scheduler QOS/time/memory/CPU/account envelope. These fields do not
retrofit or reinterpret the already-built ec839 cap-pilot array.

Every prospective Tetralith start job is submitted as exactly one array with
an in-header concurrency limit of five (`#SBATCH --array=1-N%5`). The header
generator fails closed if Lab emits no array directive, more than one
directive, or a directive with an unexpected range. Each run records
`scheduler_array_task_throttle=5`, and every prospective analyzer requires
that exact value. Check all prospective array sizes without building or
submitting anything with:

```
experiments/.venv/bin/python experiments/exp_common.py
```

Only after this protocol is committed/published, the cost manifest validates,
the c280 cache sentinel exists, and the sealed pilot/recovery/cache jobs have
drained, use the following grid environment unchanged for both the build and
start of one experiment. The 300-second/8192-MiB planner limits bind inside
the 10-minute/9-GiB scheduler envelope.

```
export DOWNWARD_BENCHMARKS=/home/x_jense/projects/benchmarks
export WBH_ACCOUNT=naiss2025-5-382
export WBH_QOS=devel
export WBH_TASK_TIME=00:10:00
export WBH_MEMORY_PER_CPU=9G

test -f experiments/data/revision-cache/\
c2800d7e65abb61d4b94b08a5487f701ceb41d6b_e5e41175/build_successful

# Build alone. This runs on the login node, but the sentinel above makes the
# operation a cache copy/run-directory build, never a planner compilation.
experiments/.venv/bin/python experiments/exp_heuristic_choices_pilot.py build
test "$(rg --files -uu experiments/data/exp_heuristic_choices_pilot | \
  rg '/static-properties$' | wc -l)" -eq 1050
# Submit exactly 1-1050%5.
experiments/.venv/bin/python experiments/exp_heuristic_choices_pilot.py start

experiments/.venv/bin/python experiments/exp_ms_caps_validation.py build
test "$(rg --files -uu experiments/data/exp_ms_caps_validation | \
  rg '/static-properties$' | wc -l)" -eq 644
# Submit exactly 1-644%5.
experiments/.venv/bin/python experiments/exp_ms_caps_validation.py start

experiments/.venv/bin/python experiments/exp_cpddl_ghseta.py build
test "$(rg --files -uu experiments/data/exp_cpddl_ghseta | \
  rg '/static-properties$' | wc -l)" -eq 1404
# Submit exactly 1-1404%5.
experiments/.venv/bin/python experiments/exp_cpddl_ghseta.py start
```

Never pass `build start` together for these experiments. The prospective
runners reject `--all` and every build/start combination, including Lab's
numeric `1 2` aliases. A combined Lab grid submission uses an `afterany`
dependency, so a failed build would not cancel the start. Fast Downward also
consults and, if absent, creates its revision cache during submission-side
reconstruction. Before either build or start, the SymK runners now require the
exact c280 cache sentinel (SHA-256 `e3b0c442...`) and cached `downward` binary
(SHA-256 `774e0f80...`); a missing or changed cache fails before Lab can
compile. Building separately then permits a static run-count check before
submission. Keep at most one prospective start array active at a
time, so independently throttled arrays cannot pool above five concurrent
runs. Do not alter the sealed ec839 pilot or cost-recovery throttles.

After both pilots produce and reviewers freeze the selection artifact, use the
same environment and the same staged discipline for the reserved experiment:

```
experiments/.venv/bin/python experiments/exp_heuristic_finalists_validation.py \
  --selection heuristic-finalists-selection.json --check
experiments/.venv/bin/python experiments/exp_heuristic_finalists_validation.py \
  --selection heuristic-finalists-selection.json build
# Verify the 460 or 552 static-properties count printed by --check exactly.
experiments/.venv/bin/python experiments/exp_heuristic_finalists_validation.py \
  --selection heuristic-finalists-selection.json start
```

Commit and publish these manifests, exact configuration matrices, selection
rule, and planner revisions before launching the c280 experiments or reading
the cap-pilot outcomes. The enriched 50-task screens are for promotion, not
benchmark-wide coverage estimates.

## Q3 / Q4 external baselines

Built and wired via `exp_baselines.py` (a generic lab experiment over the
pre-built binaries in `../baselines`; see `baselines/README.md` for build
steps). Algorithms:

- `cpddl_i_i` -- CPDDL bidirectional symbolic search with one
  initial-state-objective potential in each direction. The archived legacy
  label is `a_plus_i`, but the executed options are `I/I`, **not A+I**.
- `cpddl_blind_bi` -- CPDDL bidirectional search without potentials. The
  archived legacy label is `symba_star`; this is a stand-in and must not be
  reported as a run of the original IPC-2014 SymBA* binary, which did not
  build on this toolchain.
- `scorpion`  -- Q4 context (Scorpion flagship optimal alias).

```
WBH_LOCAL=1 experiments/.venv/bin/python experiments/exp_baselines.py build start parse fetch report
```

### Prospective GHSETA frozen-manifest baseline

`exp_cpddl_ghseta.py` is a predeclared, **not yet launched** CPDDL screen on
three pairwise-disjoint frozen manifests: the 50-task outcome-enriched
`pilot50`, the 92-task `cap-v2`, and the prospectively reserved 92-task
`finalist-v1`. Its six configurations are CPDDL blind forward and blind
bidirectional controls, forward I, forward A+I, the vendored README's
recommended bidirectional forward-A+I/blind-backward configuration, and
bidirectional forward-A+I/backward-I. Every command uses `--fdr-tnfm`. At
300 seconds, 8192 MiB, and one run per task, this is `234 * 6 = 1404` runs.
This matrix expansion was frozen before inspecting any outcome from these
CPDDL configurations.

The pre-run check hard-pins the executable's SHA-256 and exact version, the
tracked vendored CPDDL Git tree object plus an independent tree-manifest
SHA-256, and SHA-256 digests of ignored `Makefile.config` and generated
`pddl/config.h`. The upstream CPDDL commit is explicitly a vendoring record,
not a revision recoverable from the removed nested Git metadata. At build
time Lab copies the pinned binary into the experiment and copies both PDDL
files into every run; per-run properties record domain/problem SHA-256 and a
resource-relative command. Before Lab can build, the runner also reconstructs
the seeded name-only task selections, checks all three manifests are disjoint,
and verifies canonical benchmark-relative paths and PDDL bytes against the
checksum-validated suite cost manifest. Each run records both that manifest's
file hash and the canonical selected-record hash for its task manifest. The
tree/config and executable attestations identify their respective inputs and
artifact but do not claim a reproducible derivation of the binary from that
tree. After the build, `parse`, `fetch`, and all three reports do not read the
original binary, task manifests, cost manifest, or benchmark checkout.

Coverage parsing is deliberately strict about the three signals shared by both
search modes: a parsed plan cost, command exit code 0 from `driver.log`, and
the exact expected `Version:` line. CPDDL's bidirectional path also prints
`DONE: PLAN FOUND`, while its forward-only path currently does not (confirmed
by source inspection and an end-to-end Gripper smoke). The marker is therefore
recorded as corroboration rather than required for coverage. A marker without
a cost, a contradictory marker, a nonzero/missing exit, or a missing/mismatched
version is coverage 0 and an unexplained error.

Validate without building or submitting anything:

```
experiments/.venv/bin/python experiments/exp_cpddl_ghseta.py --validate-only
```

Build, start, and postprocess separately using the common staged grid
discipline above:

```
experiments/.venv/bin/python experiments/exp_cpddl_ghseta.py build
experiments/.venv/bin/python experiments/exp_cpddl_ghseta.py start
experiments/.venv/bin/python experiments/exp_cpddl_ghseta.py parse fetch \
  report-pilot report-cap-v2 report-finalist-v1
```

The prospective outputs are
`experiments/data/exp_cpddl_ghseta-eval/report-pilot.html` and
`experiments/data/exp_cpddl_ghseta-eval/report-cap-v2.html`, and
`experiments/data/exp_cpddl_ghseta-eval/report-finalist-v1.html`. There is
intentionally no pooled report: pilot50, cap-v2, and finalist-v1 must never be
combined into a headline coverage or runtime claim.

The read-only analysis contract was also frozen before launch. Check its
in-memory acceptance/rejection suite without reading an outcome:

```
experiments/.venv/bin/python experiments/analyze_cpddl_ghseta.py --self-test
```

After parsing and fetching a complete run, analyze it with the frozen operator
cost classification required:

```
experiments/.venv/bin/python experiments/analyze_cpddl_ghseta.py \
  experiments/data/exp_cpddl_ghseta-eval/properties \
  --require-cost-manifest
```

`analyze_cpddl_ghseta.py` requires all 1404 cells and the exact manifests,
runner, source-tree, build-config, generated-config, executable, copied-input,
command, limit, direction, objective, and resource-path attestations. It
re-derives the strict forward-compatible coverage classification and rejects
contradictory solved costs. The checksum-validated
`suite_wbh_operator_costs.json` supplies supported positive-cost, axiom-free
membership and the expected PDDL hashes. It also independently reconstructs
cap-v2's and
finalist-v1's name-only seeded selections and checks the global source-manifest
hash and all three canonical selected-record hashes; if the cost manifest is
not yet
present, the default mode reports only the full frozen sets as secondary
context and explicitly suppresses supported-population sections.
Use `--require-cost-manifest` for any final report so missing or invalid cost
provenance fails closed.

The predeclared primary estimands are paired task-level coverage differences
and equally weighted domain-macro coverage differences for six controlled
contrasts. They are reported separately for each manifest on its supported
positive-cost, axiom-free task set; a differing full set is secondary context.
Every contrast includes discordant task wins/losses
and a deterministic 95% domain-cluster bootstrap interval for the domain-macro
difference (10,000 percentile replicates, fixed seed
`symbolic-search-heuristics/cpddl-ghseta/domain-cluster-bootstrap/v1`,
Hyndman-Fan type-7 quantiles). PAR2 (600 seconds for an unsolved cell) and
solved-run times are one-run screening summaries only. Configuration order is
fixed; the analyzer neither ranks configurations nor selects or tunes one
using cap-v2 or finalist-v1 outcomes.

### Frozen finalist-v1 cross-planner analysis

`analyze_cross_planner_finalists.py` is the prospective, read-only composition
of the SymK finalist validator and the complete CPDDL GHSETA validator. It was
frozen before either finalist-v1 outcome set was opened. The input contract is
identified by analyzer SHA-256
`f75e46fbc885c7083f2076dd12338ceb0827b804df73af3de1f75fe70294c578`. It
also pins every imported validation helper, including the shared scheduler
header implementation and the heuristic-screen runner that performs the
50-task source attestation. Its exact inputs are
the exact reviewed SymK selection artifact, all 460--552 SymK finalist-v1
cells, and all 1404 CPDDL cells across the three manifests. The latter full
matrix is validated for provenance, but the normalized comparison view is
constructed from exactly the 92 finalist-v1 tasks: no pilot50 or cap-v2 row
can enter a reported statistic.

The primary external comparator is predeclared as
`cpddl_ghseta_bi_a_plus_i_blind`, the bidirectional forward-A+I / blind-
backward configuration identified as recommended in the vendored CPDDL
README. The secondary comparator is the direction-matched forward-A+I
`cpddl_ghseta_fw_a_plus_i`. Every logical SymK role is retained without
held-out ranking: `blind_fw`, `ms_exact`, the independently pilot-selected
primary cap, and the selected M&S, PDB, and potential family finalists. A
family finalist that deduplicates to a control's search remains an explicitly
labeled logical contrast over that shared validation result.

For the supported positive-cost, axiom-free finalist-v1 set, every SymK role is
compared with both CPDDL comparators. Effects are always SymK minus CPDDL. The
primary statistic is the paired, equally weighted domain-macro coverage
difference, with discordant task wins/losses and the existing fixed-seed
10,000-replicate domain-cluster percentile interval. Suite-micro and supported-
population post-stratified coverage are descriptive. PAR2 and runtime use one
run per cell and are screening only; SymK records `planner_time` whereas CPDDL
records `total_time`.

In addition to both component validators' exact matrix, revision, command,
binary/resource, limits, and source checks, the cross gate requires identical
task order and source attestations, validates solved-cost agreement across
planners, and rejects a CPDDL unsolvability proof contradicted by a SymK
solution. It hash-pins the imported validator source bytes, so later helper
changes require a new pre-outcome review instead of silently changing this
contract. The synthetic mutation suite reads no experiment outcomes:

```
experiments/.venv/bin/python \
  experiments/analyze_cross_planner_finalists.py --self-test
```

After both complete experiments are parsed and the reviewed selection artifact
is available, run the report without writing any outcome-derived artifact:

```
experiments/.venv/bin/python \
  experiments/analyze_cross_planner_finalists.py \
  experiments/data/exp_heuristic_finalists_validation-eval/properties \
  experiments/data/exp_cpddl_ghseta-eval/properties \
  --selection heuristic-finalists-selection.json
```

Combine the `properties` member of `data/exp_baselines-eval.tar.gz` (or an
extracted `data/exp_baselines-eval/properties`) with the SymK-config results
for the per-domain coverage tables. Report baseline numbers from our runs on
our suite, never from the original papers' tables (pitfall #8).

## Archived evidence and protocol limits

The checked-in `data/*-eval.tar.gz` files are evaluation snapshots
(`properties` plus reports), not complete run directories. Keep them
immutable and record the archive name when reporting. In particular:

- `exp_q1` and `exp_q2` record revision
  `0d3fd43e9d88a0a802e1fdc2770070c18d6e7ffe`; `exp_ms` records
  `8bfdc4f1546ea7682bdd9e296c8481e122691e51`. The original 50-task cap
  pilot pins `ec8399257de93e0739046a187af4bed0b85e19ce`; the schema-v2
  heuristic-choice screen and held-out cap validation pin
  `c2800d7e65abb61d4b94b08a5487f701ceb41d6b`. The current scripts have
  evolved and are not exact reconstructions of the older full-suite archives.
- The SymK archives record 1800 s and 8192 MiB per run. The generic baseline
  archive does not embed a source revision or resource fields; its provenance
  is the vendored commits in `baselines/README.md` and the runner's intended
  limits. Future baseline runs record these fields explicitly.
- An unsolved record is right-censored by the resource limit and may mean
  timeout, memory exhaustion, unsupported zero-cost/translated-axiom input, or
  another error.
  Evaluation tarballs omit the `run.err` files needed to disambiguate legacy
  `exitcode-250` runs. Do not treat partial raw counters as complete totals
  or reconstruct the supported subset from an evaluation archive alone.
- Every archived sweep has one run per algorithm/task and no repetitions.
  Runtime differences are screening evidence, not noise estimates. In the
  potential sweep, `M=16` solved 623 tasks and `M=8` solved 622; the
  one-task difference does not establish a unique best bound.
