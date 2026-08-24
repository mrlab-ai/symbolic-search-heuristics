# ICAPS Revision Strategy

## Venue and Scope

- Target: ICAPS 2027 long paper.
- Provisional format: AAAI two-column style, at most eight content pages plus
  references, following the published ICAPS 2026 rule until the 2027 call is
  available.
- Paper category: theoretical/algorithmic classical-planning paper with a
  fixed-census empirical evaluation.
- Central question: when can a heuristic partition symbolic search frontiers
  without causing an uncontrolled representation blow-up, and can the
  resulting certificate retain useful heuristic information?

## Central Contribution

Cofactor width gives a fixed-order certificate for heuristic fragmentation in
forward product-at-evaluation symbolic A*, and safe terminal capping turns the
certificate into a backward-compatible PDB selector that recovers useful
heuristic information while improving the same-budget comparator.

## Claims and Evidence

| Claim | Evidence |
|---|---|
| A width-$W$, $V$-valued consistent heuristic has expansion-size ratio at most $2VWn$ over blind forward search. | The sharper layerwise certificate is $\sum_g V_g\mathcal C_\pi(L_g,h)$, where $\mathcal C_\pi$ is the cut-aligned product of the state-set and heuristic cofactor profiles. Relaxing it yields the coarse ratio. |
| The parameter dependence is not merely an artifact of the proof. | Exact modular-cut counting strengthens the quadratic construction to ratio at least $55W^2/288$ for $V=W$; setting $k=4W$ gives $n=8W+2$. The ratio matches all three pairwise products on this tied diagonal, without proving their independent necessity; simultaneous $VWn$ tightness remains open. |
| Cofactor width contributes information beyond ordinary total-ADD size. | Before relaxation to width, the cofactor-profile and Apply certificates have explicit linear separations in both directions and combine per active layer by taking their minimum. |
| Uniform caps preserve admissibility and consistency and contract every cofactor cut. | Safe-terminal-transform proposition and nested-cap argument; pointwise cut contraction also contracts every fixed-layer profile certificate. |
| Cap-aware selection is backward compatible with exact-width selection on score-identical raw pools. | The exact candidate chosen for every width-feasible pattern is retained by the cap-aware per-pattern step, so the frozen lexicographic score cannot decrease. This also preserves semantic nontriviality; an exact cap-aware fallback is the exact selector's winner. |
| Every selected heuristic retains an end-to-end representation certificate. | Every completed output has ratio at most $2K^2n$; at $K=8$ this is $128n$, while caps 2 and 4 sharpen it to $48n$ and $80n$. |
| Cap-aware selection recovers useful heuristic content. | On 1,306 completed, certified, identical-pool pairs in the 1,327-task primary scope: 626 semantic gains and 0 losses; 1,292 versus 666 nontrivial selections. |
| The recovered information improves the same-pool, same-width-budget comparator. | Primary macro coverage +0.96 percentage points, 12 wins versus 5 losses; expanded BDD nodes ratio 0.884 and image-time ratio 0.893 on 579 positive-work pairs, plus 11 zero-work unsolvable endpoints; construction-time ratio 1.023. On 393 triple-solved finite-cap tasks, the effort ratios are cap-aware/exact 0.868, cap-aware/blind 0.982, and exact/blind 1.132. The 1,377-task sensitivity has the same direction. |

## Explicit Non-Claims

- Cofactor width is standard fixed-order MTBDD/branching-program width; the
  contribution is its connection to symbolic-search fragmentation and the
  resulting planning guarantees and selector.
- The experiment does not establish population-level significance or a
  state-of-the-art planner.
- The 21 primary tasks without completed paired selector construction do not
  support a selector-mechanism comparison; they remain in all coverage and
  PAR2 denominators.
- The experiment measures the theorem's effort target against blind search but
  does not instantiate the sharper profile-based numerical upper bound.
- The unaligned M&S control is not covered by the aligned M&S family formula.

## Adversarial Review Round 1

### Risk: the width definition is renamed standard machinery

- Evidence for the concern: residual/MTBDD width and the product construction
  are classical.
- Severity: acceptance-critical.
- Change: state this immediately, lead with the exact bucket/effort theorem and
  the lower bound, and avoid presenting the definition itself as novel.
- Residual uncertainty: reviewers may still judge the theorem too direct.

### Risk: the empirical gain looks small and uses a weak comparator

- Evidence for the concern: cap-aware solves 619 tasks, blind solves 620 and
  unaligned M&S solves 632 on the full census.
- Severity: acceptance-critical.
- Change: explain that exact-width selection is the direct certificate
  baseline, prove candidate-set dominance, report 626/0 semantic changes and
  the 11.6% node reduction, and keep stronger controls visible.
- Residual uncertainty: the method is not the strongest overall planner row.

### Risk: theory and experiment appear disconnected

- Evidence for the concern: the logs do not instantiate the worst-case bound
  for each semantic blind layer.
- Severity: important.
- Change: make the empirical claim about preserving the width certificate,
  recovering information and reducing measured BDD effort, not about validating
  the asymptotic bound.
- Residual uncertainty: a future experiment should log the theorem's complete
  cut profiles.

### Risk: too many side contributions obscure the main result

- Evidence for the concern: image-call and pruning-only sections do not enter
  the final experiment.
- Severity: important.
- Change: retain their complete statements in the supplement and remove them
  from the eight-page main-paper argument.
- Residual uncertainty: the family bounds still compete for limited space.

## Revision Shape

1. Introduction: problem, closest work, exact novelty boundary and three
   contributions.
2. Background and cofactor width.
3. Fragmentation and forward-search guarantees, including the strengthened
   lower-bound interpretation.
4. Safe transforms and width-bounded heuristic families.
5. Cap-aware PDB selection with selector-dominance proposition.
6. Fixed-census experiment centered on semantic gains, BDD effort and coverage.
7. Related work and concise conclusion.

## Adversarial Review Round 2

This round reviewed the compiled paper as an ICAPS submission, with separate
theory, experiments and presentation objections.

### Theory objection: the lower bound overstates parameter independence

- Adversarial reading: because (V=W) and (n=\Theta(W)), calling all three
  pairwise factors independently necessary would be stronger than the proof.
- Resolution: state the exact constants, call the result a diagonal pairwise
  lower bound, and explicitly leave joint (VWn) tightness open in the
  abstract, theorem discussion, conclusion and supplement.
- Residual risk: the construction is quadratic, not a matching lower bound for
  the full cubic upper bound.

### Algorithm objection: zero semantic losses are built into the selector

- Adversarial reading: the 626/0 result can look like an unexplained empirical
  miracle or a post-hoc claim.
- Resolution: prove candidate-set containment. Zero losses are a theorem under
  identical-pool completion; the empirical result is that the enlarged set
  adds 626 nontrivial winners. Report that 1,020/1,306 winners actually use a
  finite cap, with median selected pattern size/width 7/6 versus 1/2 for the
  exact selector.
- Residual risk: score dominance is not runtime dominance, which the paper now
  states explicitly.

### Experiments objection: a small aggregate gain may be concentrated

- Adversarial reading: +0.96 macro-coverage points and seven net task wins are
  modest, while blind and M&S remain strong controls.
- Resolution: retain all controls, lead with the 11.6% expanded-node and 10.7%
  image-time reductions on their eligible pairs, and disclose that primary
  coverage improves in eight domains, declines in three and is unchanged in
  35. Keep the claim scoped to a stronger same-pool, same-width-budget selector.
- Residual risk: the frozen operational contract reports aggregate totals, not
  a per-task effect distribution, and the experiment does not validate the
  worst-case theorem directly.

### Presentation objection: the eighth body page was effectively empty

- Adversarial reading: a two-line final page makes the paper look unpolished
  and obscures how much evidence the main argument really contains.
- Resolution: remove redundant conclusion prose and tighten related work. The
  provisional AAAI-format proxy now ends cleanly after eight content pages,
  with references starting on page 9.

### Post-Revision Assessment

The strongest defensible case is a theory-led paper with an algorithmic
consequence and a large fixed-census validation. The remaining rejection risks
are substantive but explicit: standard underlying width machinery, no joint
(\Omega(VWn)) lower bound, no direct bound-validation experiment, and no overall
planner dominance. None can be fixed honestly without a new theoretical idea
or a new preregistered experiment.

## Adversarial Review Round 3

Three independent reviews again targeted the formal argument, the frozen data,
and ICAPS acceptance. The mock venue review scored the checkpoint manuscript
5/10 (weak reject, close to borderline) and identified ordinary total-ADD size
as the strongest unaddressed objection.

### Theory objection: the coarse width ratio appears dominated by ADD size

- Adversarial reading: the standard Apply bound gives a ratio
  $V(2A+1)$, and $A=O(nW)$, so a headline based only on $O(VWn)$ can look
  like a weaker repackaging of known ADD machinery.
- Resolution: lead with the cut-sensitive certificate
  $VW\sum_g Q(\chi_{L_g})$, prove that it and Apply have linear separations in
  both directions, and retain total ADD size as a complementary certificate.
- Additional strengthening: the nonconstant-layer argument improves the
  universal ratio from $3VWn$ to $2VWn$; the quadratic construction improves
  from $W^2/128$ to $W^2/12$; and the implementation's default-zero PDB
  extension improves the family bound from $d|S^P|$ to $|S^P|$.
- Residual risk: no matched ADD-budget selector was run, so the paper does not
  claim that width is the empirically superior budget.

### Algorithm objection: the certificate is not connected end to end

- Adversarial reading: safe caps and selector containment do not by themselves
  state what the completed algorithm certifies.
- Resolution: add the selector-safety corollary. Every returned heuristic has
  blind-effort ratio at most $2K^2n$, hence $128n$ at $K=8$; caps 2 and 4
  sharpen this to $48n$ and $80n$. Prove also that selecting an exact endpoint
  returns the exact selector's winner on a score-identical raw pool.
- Residual risk: these are expanded-frontier representation bounds, not runtime
  or relational-product bounds.

### Experiments objection: aggregate ratios may hide concentration and censoring

- Adversarial reading: the 590-pair node and image totals condition on joint
  metric completion and could be driven by a few domains or instances.
- Resolution: preserve the frozen primary and secondary analyses unchanged,
  and add a separately checksum-bound, explicitly post-hoc theorem-guided
  audit. It stratifies exact fallbacks from actual finite-cap interventions,
  reports per-pair signs, leave-one-domain-out ranges, initial-value changes,
  and certificate coefficients. A further adversarial check rejected the
  cross-configuration partition-ratio quantiles because their observation
  sets are unpaired and dominated by incomplete searches; the artifact retains
  them, but the paper does not interpret them. No post-hoc quantity is promoted
  to a prespecified estimand.
- Residual risk: the operational subset excludes discordant tasks and joint
  timeouts, so it cannot explain the coverage difference; the paper now says
  so directly.

### Presentation objection: the paper reads as assembled contributions

- Adversarial reading: standard width, terminal relabeling, containment and a
  modest coverage gain can appear as several small claims without a single
  center.
- Resolution: frame one theory-led story---identify a structural safety regime
  for the known exponential pathology, delimit it, and use the selector as an
  operational case study. State the lower bound first as $\Omega(W^2)$, remove
  the low-information pipeline figure, and distinguish the unrelated width of
  relaxed BDD heuristics for delete-free planning.
- Residual risk: a new $K$ sweep and matched ADD-size baseline would require a
  new frozen experiment. They remain deferred rather than being reconstructed
  post hoc.

## Adversarial Review Round 4

This round began from the committed Round-3 manuscript and again separated
formal, empirical and hostile venue review. The mock ICAPS verdict was 6/10
(borderline weak accept). Its clearest route to a stronger submission was a
target-metric comparison of actual representation effort with blind search.

### Theory objection: width hides useful cut-by-cut information

- Adversarial reading: replacing every heuristic cut by its maximum width can
  make the theorem look needlessly coarse and obscures why terminal coarsening
  helps a particular frontier.
- Resolution: define the cut-aligned profile product
  $\mathcal C_\pi(S,h)=\sum_i c_i(\chi_S)c_i(h)$. A bucket is bounded directly
  by this product, and search effort is bounded by
  $\sum_g V_g\mathcal C_\pi(L_g,h)$ before either active-bucket counts or cut
  widths are maximized. Safe terminal transforms contract every $c_i(h)$.
- Residual risk: the retained traces do not contain the exact layer and
  heuristic cofactor profiles needed to instantiate this upper bound.

### Theory objection: the lower-bound constant discards most nodes

- Adversarial reading: the previous $W^2/12$ proof counted only saturated
  middle levels of the modular buckets, weakening an already diagonal result.
- Resolution: count every next-bit node on every modular cut. The exact layer
  contribution is
  $S_{i,W}=\sum_{j<i}\min(W,j+1)\min(W,i-j+1)$, which strengthens the ratio to
  $55W^2/288$ for all $W\geq2$ and $k\geq4W$. The supplement gives the closed
  form, positivity calculation and edge-case audit.
- Residual risk: the construction still does not prove a joint
  $\Omega(VWn)$ lower bound.

### Experiments objection: operational totals do not evaluate the theorem's target

- Adversarial reading: aggregate node and time totals compare the two selectors
  but do not reveal whether either heuristic improves over blind search in the
  exact cumulative expanded-BDD-node measure used by the theorem.
- Resolution: add a digest-pinned post-hoc audit on triple-solved, trace-complete
  instances. It computes the paper's effort definition for blind, exact and
  cap-aware search, separately for finite caps and exact endpoints, and checks
  cost agreement, integral counters and raw-pool identity before inclusion.
  This evaluates the theorem's target metric, not its unlogged numerical upper
  bound.
- Residual risk: triple-solved conditioning excludes discordant outcomes and
  joint timeouts, so the result is descriptive rather than a coverage
  explanation.

### Experiments objection: the 590-pair headline mixes interventions and fallbacks

- Adversarial reading: exact endpoints are a built-in negative control and
  several unsolvable zero-node cases are outside the finite-$C^*$ theorem.
- Resolution: report finite-cap operational conservation separately---total
  nodes, completed buckets, nodes per completed bucket and image time per
  bucket---and identify exact endpoints as the negative control. State the
  solved denominator whenever invoking target-metric effort.
- Residual risk: time per call remains a systems measurement and exact-endpoint
  timing is not expected to be bit-identical.

### Post-Revision Assessment

The paper now has a sharper central theorem, a substantially stronger constant
for its existing lower family, and a direct descriptive audit of the theorem's
target effort measure against blind search. The main unresolved issues require
new data or new theory: profile logging, a matched ADD-budget selector, a
multi-budget replication, and joint three-factor tightness.

The final hostile ICAPS review scored this revision 7/10 (weak accept,
confidence 4/5). Its six repairable objections were addressed: the operational
denominator is named ``Pairs'' rather than overloading $n$; the headline
separates 579 positive-work pairs from 11 zero-work unsolvable endpoints; all
post-hoc labels say descriptive or target-metric rather than robustness or
bound validation; diagonal lower-bound claims no longer imply independent
parameter necessity; selector-induced pattern changes are explicit; and the
triple-solved audit fails closed unless every expanded bucket has one BDD
piece. The remaining objections are scope limits already stated as non-claims.
