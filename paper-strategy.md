# Paper Strategy: Explaining Symbolic-Heuristic Performance

## Decision

The proposed framing is potentially stronger than the current paper because it
turns a representation certificate into an explanation, a falsifiable
empirical claim and an algorithmic consequence. It is weaker if stated from
the existing P4--P6 evidence alone: the reported cross-task correlations are
mixed, the width-one selector always chooses the empty PDB and the new methods
do not beat all controls. We therefore adopt the framing only if the frozen
multi-budget profile experiment passes the gates below. Until then,
"certificate" is the supported term and "predictor" is a hypothesis.

## Central Question and Answer

**Question.** Why do some admissible heuristics help product-at-evaluation
symbolic A* while others fragment its BDD frontiers enough to erase their
guidance benefit?

**Candidate answer.** Heuristic accuracy alone does not control symbolic
search effort. What matters structurally is how the heuristic divides state
sets under the search variable order. The cut-aligned cofactor profile gives
the sharp representation certificate; cofactor width is its pre-search,
planning-facing relaxation. Safe terminal capping contracts this structure and
therefore yields width-constrained PDB selectors.

This wording preserves the novelty boundary: fixed-order residual/MTBDD width
is standard. The contribution is its connection to exact symbolic-search
bucket semantics, the profile and width bounds, the separation from global ADD
size and the resulting heuristic construction.

## Comparison With Prior Explanations

The paper must distinguish three ideas instead of inventing one vague "old
metric":

1. Heuristic quality or distance accuracy is the natural explicit-search
   explanation. Prior work already shows that even a perfect heuristic can
   increase symbolic expansion size exponentially.
2. Cumulative expanded-BDD size is an informative *ex-post outcome measure*,
   not a pre-search heuristic-selection feature.
3. Global heuristic ADD size is the closest static representation proxy. The
   profile theorem shows that it and the cut-aligned certificate are
   incomparable; the experiment therefore compares acceptance-matched width
   and ADD budgets directly.

The introduction may say that cofactor width differs from both accuracy and
global diagram size. It must not claim that the community previously used the
number of heuristic values as an established predictor without a direct
source.

## Claim-to-Evidence Map

| Claim | Required evidence | Current status |
|---|---|---|
| Heuristic quality does not explain symbolic performance by itself. | Primary prior result plus a precise account of its symbolic expansion-size metric. | Supported by Speck et al. (ICAPS 2020); citation wording must be checked against the paper. |
| Cofactor structure controls fragmentation. | Exact bucket identity, cut-aligned profile bound and width relaxation under the stated forward-search assumptions. | Supported formally; full proof and edge cases remain subject to paper-only review. |
| The new structural quantity differs from global ADD size. | Two-way formal separation, not merely different definitions. | Available on the focused cap-grid branch; must be integrated and verified. |
| Width is a useful pre-search predictor. | Task-paired, multi-budget evidence that width-based decisions track lower representation effort better than quality surrogates and acceptance-matched ADD size. | Not established by P4--P6; frozen 1,327-task profile comparison is running. |
| Safe capping yields a better heuristic. | Admissibility, consistency, profile contraction, selector containment and controlled comparisons with exact-width, ADD-budget, unconstrained and blind variants. | Formal properties and one-budget development evidence exist; multi-budget validation is running. |
| The method improves symbolic search. | Coverage on the fixed denominator plus paired expansion-size effort; runtime only as a secondary systems diagnostic. | Conditional on the new experiment. No state-of-the-art or population-level claim is planned. |

## Frozen Empirical Gate

The in-flight experiment uses 1,327 tasks from 46 domains and 18
configurations. It compares five width budgets
`K in {2,4,8,16,32}`, five total-ADD budgets
`U in {8,29,55,100,204}` chosen to match candidate acceptance on the frozen
50-task development screen, cap-aware width selection, exact-width selection,
an unconstrained same-pool selector and profiled/unprofiled blind controls. It
logs complete search-layer and heuristic cofactor profiles. The 50-task screen
is not part of the 1,327-task evaluation denominator.

Before inspecting outcomes, use the following decision rules:

- Call width a **useful predictor** only if width-based selection improves the
  task-paired representation-effort comparison against the matched ADD-size
  selector at a clear majority of the five budgets, the aggregate direction is
  not reversed by leaving out any single domain and coverage does not reveal a
  compensating systematic loss.
- Call the **cofactor profile a sharper explanatory metric** only if its
  instantiated certificate is consistently tighter than the width relaxation
  and its slack or ordering tracks observed expanded-BDD effort better than the
  global ADD certificate on eligible task--configuration cells.
- Call cap-aware selection a **new useful heuristic construction** only if it
  preserves the formal certificate and improves exact-width selection on full
  fixed-denominator coverage or paired expansion effort at multiple budgets.
- Treat jointly solved/trace-complete effort as a conditional mechanism
  diagnostic. It cannot explain discordant coverage or joint timeouts.
- Report all five budgets and the unconstrained endpoint. Do not select a
  favorable budget from evaluation outcomes and present it as prespecified.

If these gates fail, retain the current theory-led story: cofactor width is a
checkable safety certificate, the tested selector is conservative and the
absence of practical gains delimits what representation safety alone can
explain.

## Planned Paper Order

1. Introduction: the explanatory question, failure of accuracy as a complete
   account and the need for a pre-search structural quantity.
2. Search setting and expansion-size outcome.
3. Cut-aligned cofactor profiles, cofactor width, the fragmentation theorem,
   global-ADD separation and tightness.
4. Safe terminal transforms and cap-aware width-constrained PDB selection.
5. Multi-budget experiment: predictive comparison first, heuristic comparison
   second, stronger controls and negative results visible.
6. Limitations and conclusion: fixed-order forward search, fixed census,
   representation effort rather than a general runtime theorem.

## Explicit Non-Claims

- Cofactor width itself is not a newly invented diagram measure.
- The theorem is not a typical-case runtime model and does not bound image
  computation or peak memory directly.
- Conditional effort ratios do not establish full-population planner
  dominance.
- The fixed benchmark census with one run per cell does not justify
  population-level significance claims.
- No state-of-the-art claim is made unless a separately fair comparison
  supports it.

## Main Risks and Next Validation

1. The profile experiment may show that global ADD size predicts outcomes as
   well as width. In that case, emphasize formal incomparability and remove the
   empirical-superiority claim.
2. Worst-case certificates may be too loose to rank ordinary heuristics. In
   that case, report safety rather than prediction.
3. Outer Slurm timeouts may leave missing grouped cells. Recovery must be
   prospective, preserve the original run records and use a documented
   complete-cell policy before any final analysis.
4. The strongest current algorithmic gains are against the exact-width
   selector, not necessarily blind search or merge-and-shrink. Keep those
   controls prominent.
5. Recheck the complete paper after results stabilize: formal assumptions,
   task flow, generated numbers, concept order, page budget and every rendered
   PDF page.
