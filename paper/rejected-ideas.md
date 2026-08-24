# Rejected and Deferred Ideas for the Cofactor-Width Paper

> **Internal design record.** Do not include this file in an anonymous review
> bundle: it cites commit history and superseded experimental stages.

## Purpose and Decision Rule

This file records ideas that were considered during development but are not
part of the focused ICAPS manuscript. Here, *rejected* means rejected from this
paper's central empirical claim, not necessarily shown to be useless. Some
ideas failed in the available experiments; others were deferred because they
would change the search architecture, confound the terminal-coarsening
comparison, or require evidence that the accepted protocol does not contain.

The final paper keeps an idea in its empirical story only if it satisfies all
of the following conditions:

1. it is evaluated in the fresh common-environment matrix;
2. it preserves the fixed generator options and cross-pattern score needed to
   isolate terminal coarsening;
3. its result has a fixed denominator and a fail-closed analysis contract;
4. the manuscript can state precisely whether the theory covers it; and
5. it contributes directly to the focused question without displacing the
   formal argument within the eight-page content limit.

## Rejected Empirical Designs

### The Original Exact-Width Selector as the Flagship Result

The earlier selector filtered a fixed PDB pool by exact width and selected the
most informative feasible candidate. On the 50-task screen, the selected
budget was `K=1`; every selected trace used the empty pattern, so the heuristic
was semantically blind. The same degeneracy persisted on the 92-task held-out
set and the subsequent full census. Coverage comparisons involving that
selector therefore tested an elaborate route back to blind search, not whether
bounded width can retain useful heuristic information.

**Decision:** reject this selector as the paper's empirical centerpiece.

**Reason:** it did not instantiate the intended quality--safety tradeoff. The
cap-aware selector replaces it with a within-pattern ladder that can coarsen an
informative raw PDB until it meets the same width budget.

### The Broad P4/P5/P6 Selector Narrative

An earlier manuscript reported a development screen (P4), a disjoint held-out
stage (P5), and a full census (P6) over a broad mixture of selectors, batching
treatments and safeguards. That pipeline was carefully frozen, but the chosen
exact-width selector remained blind-equivalent. The broad narrative also mixed
selection, operational safeguards and mechanism diagnostics that answered
different questions.

**Decision:** replace the broad staged story with the focused five-configuration
cap-aware census.

**Reason:** the focused design compares cap-aware and exact selection at the
same `K=8`, holds the raw generators and score fixed, and makes terminal
coarsening the only intended difference on certified matching-pool pairs. The
older stages remain useful development evidence, not evidence for the final
mechanism claim.

### Same-`g` Speculative Batching

The batching prototype imaged a union of eligible buckets at the same
`g`-layer and kept the logical keys pending separately. On the 50-task screen,
every batching treatment lost between three and six solved tasks. On complete
pairs, batching reduced the recorded number of high-level image calls but
increased image time. Its regression oracle compared keys, BDD-node counts,
state counts and solution cost, but did not establish exact set equality for
the transformation.

**Decision:** reject batching from the final algorithm and evaluation.

**Reason:** the intended amortization did not improve the measured operational
cost, reduced coverage, and lacked the semantic certificate required for a
central algorithmic claim.

### One Global Terminal Cap

A predeclared pilot tested global M&S terminal caps
`K in {2,4,8,16,32}`. Solved count selected `K=32` on the same 50-task pilot.
The capped and uncapped configurations each solved 42 tasks, with one win and
one loss. The cap reduced the legacy image-count proxy by about 7%, but image
time increased by a factor of 1.024 and planner time by 1.011 on jointly solved
tasks.

**Decision:** reject a single globally tuned cap as the main intervention.

**Reason:** the pilot supplied selection-stage rather than confirmatory
evidence, and one global cap forces the same information loss on every
pattern. The final design instead tests a prespecified ladder per raw PDB and
retains the strongest width-feasible transform before cross-pattern ranking.

### `K=32` as a Post-Hoc Primary Substitute

The focused screen included a `K=32` sensitivity, but the prospective promotion
rule named `K=8` as primary and explicitly prohibited the sensitivity from
substituting for it.

**Decision:** reject any post-outcome switch to `K=32`.

**Reason:** changing the primary width after reading the screen would turn a
fixed comparison into adaptive tuning. `K=32` remains sensitivity evidence
only.

### Construction-Bounded M&S with Blind Fallback

A 60-second M&S construction deadline with fallback to blind search was an
effective engineering safeguard: it solved 43/92 tasks with five fallbacks in
the held-out stage and later had strong descriptive PAR2. It nevertheless
changes both heuristic construction and the search configuration, and the
evaluated causal-graph M&S order is not aligned with the search order required
by the closed-form width bound.

**Decision:** retain it as development context, but reject it from the focused
cap-aware matrix.

**Reason:** it does not isolate terminal coarsening and cannot certify the M&S
family formula used in the theory. A dedicated safeguard paper or ablation
would be a better home.

## Pruning Ideas

The pruning-only theorem remains in the supplementary material because it is a
clean consequence of the fragmentation bound: retaining blind `g`-layers and
using the heuristic only for sound threshold discards removes the finite-value
factor from the representation bound. It was removed from the eight-page main
paper because it does not enter the focused experiment. What was rejected is
the empirical claim that the tested pruning variants are the best practical
use of a heuristic.

### Forward Pruning-Only Search

In the archived positive-cost sweep, pruning-only potentials, PDBs and M&S
solved 683, 682 and 681 tasks, respectively, versus 682 for blind forward
search. Their expansion-size ratios were essentially 1.00, as intended, but
PDB and M&S construction raised runtime. Pruning had little opportunity to
help because an incumbent usually became available late.

**Decision:** keep the formal guarantee, but exclude forward pruning from the
focused experiment.

**Reason:** the results were coverage-neutral and came from an older execution
environment and instrumentation regime. Re-running them would add a separate
question about incumbent timing and construction cost rather than clarify the
cap-aware selector.

### Bidirectional Pruning with M&S

Pointwise pruning is sound in either search direction, but the paper has no
cumulative bidirectional bound because incumbent discovery, meeting points,
closed sets and direction scheduling feed back on the future frontiers. The
empirical variants also failed to recoup construction cost: blind
bidirectional search solved 1051 tasks, the 60-second construction-bounded
variant solved 1041, and deferring M&S construction until the first incumbent
reached 1046 (one win and six losses against blind).

**Decision:** reject bidirectional pruning as a supported contribution of this
paper.

**Reason:** both the formal coverage and empirical outcome are incomplete for
the claim we would need: there is no end-to-end cumulative theorem, and the
best tested construction policy still lost coverage.

### External Incumbent Seeding

A 60-second LAMA run was tested as a source of an initial solution bound.
Seeding improved plain blind bidirectional search (1054 versus 1050), while
adding M&S pruning reached 1051 and contributed no further gain. In forward
search, seeded pruning-only potentials did improve coverage (688 versus 682
for blind and 683 unseeded).

**Decision:** defer rather than dismiss incumbent seeding.

**Reason:** the positive forward result depends on an external satisficing
planner and a potential-heuristic implementation outside the final matrix. It
changes the architecture from width-constrained heuristic selection to a
two-planner pipeline. The observation is promising, but belongs to a separate
study of incumbent acquisition and pruning economics.

## Deferred Families, Ablations and Claims

### Potential Heuristics in the Final Matrix

The theory bounds rectified integer potential level sets. The available final
build excludes the LP support needed for potential construction, and the
result does not directly cover delta-partitioned operator-potential search.

**Decision:** retain the family theorem, but defer the empirical family.

**Reason:** adding it would require a new pinned planner build and a separate
analysis of the delta-integrated architecture.

### Aligned M&S as a Confirmatory Control

The closed-form M&S width bound requires the merge order to align with the
search BDD order. The conventional causal-graph control deliberately uses an
unaligned order, while enforcing alignment can change heuristic quality.

**Decision:** keep unaligned M&S as descriptive context only.

**Reason:** it is a strong practical control, but not a test of the analytic
family bound. A fair aligned-versus-unaligned experiment must separate the
effect of representation alignment from the effect of heuristic quality.

### Total-ADD Size as the Budget Instead of Cofactor Width

The paper proves a second per-bucket bound based on the total ADD size, and the
two pre-relaxation bounds are incomparable.

**Decision:** reject the claim that cofactor width is the superior operational
budget.

**Reason:** the accepted matrix contains no total-ADD-size budget ablation. The
paper can present width as a sufficient certificate, but cannot rank the two
constraints empirically.

### Direct Empirical Validation of the Worst-Case Bound

The execution logs contain widths, ADD summaries and operational totals, but
not the paired source cofactor profiles and theorem slice sizes needed to
evaluate the bound instance by instance.

**Decision:** reject correlation or theorem-validation claims from these logs.

**Reason:** aggregate width, image and node summaries do not reconstruct the
quantities in the proof. The final paper limits the experiment to selector
behavior, coverage and separately denominated operational descriptions.

### A Joint Three-Factor Lower-Bound Claim

The quadratic construction becomes a simultaneous pairwise lower bound when
setting (k=4W): it has (V=W), (n=8W+2), and overhead in
(\Omega(VW)), (\Omega(Vn)), and (\Omega(Wn)). All three parameters are tied
together on this diagonal slice.

**Decision:** reject any claim that the construction proves
(\Omega(VWn)) overhead or independent necessity of all three factors.

**Reason:** the construction establishes that each pairwise product is tight
on one parameter slice, but its ratio is only quadratic while (VWn) is
cubic there. Joint three-parameter tightness remains open.

### Selector Dominance as Runtime Dominance

Candidate containment proves that cap-aware selection cannot lower the frozen
information score on an identical raw pool. It also preserves initial-state
dead-end recognition and semantic nontriviality.

**Decision:** reject the stronger claim that cap-aware selection must improve
coverage or runtime on every task.

**Reason:** the score is an information surrogate. Stronger heuristic values
can still change bucket fragmentation and construction cost, and the fixed
census contains both coverage wins and losses.

### Changing Pattern Generators or the Cross-Pattern Score

Larger pools, different CEGAR settings, learned scores and adaptive cap ladders
could improve heuristic quality.

**Decision:** defer all such changes.

**Reason:** they would confound the current comparison. The accepted study
holds generator recipes, options and the cross-pattern score fixed so that the
intended difference is terminal coarsening within each pattern.

## Evidence Trail

The main historical checkpoints behind these decisions are:

- `39d5c1676` (global terminal-cap pilot);
- `8086fcfb2` and `18472b612` (P4 and P5 reporting);
- `57d46f48a` and `a6aa4d7a1` (construction-bounded and deferred
  bidirectional pruning results);
- `f071fc66c` (external-bound seeding results);
- `d33ceb8cc` (scope calibration before the focused pivot);
- `aa93eeca1` through `dd8037db2` (prospective focused cap-grid protocol,
  analysis and rendering); and
- `34c4953a8` (the pre-revision focused manuscript).

These checkpoints explain the decisions; the accepted paper reports only the
fresh focused experiment and its attested analysis artifact.
