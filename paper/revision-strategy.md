# ICAPS Revision Strategy

## Venue and Scope

- Target: ICAPS 2027 long paper.
- Typesetting: official AAAI 2027 author kit in anonymous-submission mode.
- Provisional length target: at most eight content pages plus references,
  following the published ICAPS 2026 rule until ICAPS 2027 publishes its own
  author instructions. AAAI 2027's separate seven-content-page rule is not
  treated as an ICAPS rule.
- Paper category: theoretical/algorithmic classical-planning paper with a
  fixed-census empirical evaluation.
- Central question: which structural property explains why some heuristics
  fragment a fixed symbolic frontier more than others, and can that property
  guide heuristic selection without conflating representation with
  search-space reduction?

## Central Contribution

Terminal incidence counts which active heuristic terminals are reachable from
which inner nodes of the frontier-masked ADD. It upper-bounds the exact sum of
BDD nodes in the realized value buckets, lies below independent cofactor and
standard-Apply certificate branches, and removes a factor $\Theta(k)$ from all
seven registered certificate baselines on an explicit decision-diagram family.
The metric retains the relation discarded by the developmental co-occurring
profile $mJ$. A staged, source-disjoint experiment first tests the resulting
ordinal prediction on common blind frontiers. Only success authorizes fresh
guided runs that compare an incidence-budgeted PDB selector directly with the
otherwise identical $mJ$-budgeted selector and with existing alternatives.

## Claims and Evidence

| Claim | Evidence |
|---|---|
| Exact fixed-frontier partition effort satisfies $E\leq I$. | Relabel each masked-ADD terminal in turn; every surviving bucket BDD node injects into an ancestor of that terminal. |
| Incidence is a more informative certificate than masked node count and the registered cofactor/Apply relaxations. | Two-branch hierarchy $E\leq I\leq kD\leq mQ\leq mJ\leq C\leq W$ and independently $E\leq I\leq A_{\mathrm{Apply}}$; the layerwise meet $B_\wedge$ is the strongest direct combination of the two branches. |
| All seven certificate baselines can lose a factor of order $k$. | An exact decision-diagram family has $E=I=\Theta(kL)$ while every registered certificate baseline is $\Theta(k^2L)$. |
| The missing node--terminal relation can decide an ordinal comparison for exact PDBs. | A reachable seven-bit blind-layer witness has $(E,I)=(10,10)$ versus $(11,11)$ while $D$, active-value count and all seven certificate baselines tie. |
| Terminal maps contract incidence and every certificate, but not exact partition effort. | The contraction proposition is paired with a four-variable counterexample in which merging two values increases $E$ from 6 to 7. |
| Incidence supports a safe representation budget. | The probe-budget proposition guarantees that the returned candidate's exact probe effort is at most the reference incidence budget and remains feasible under later terminal maps. |
| Incidence predicts relative fixed-frontier partition effort better than the alternatives. | Confirmation A compares ten predictors on a target-strict common-frontier denominator with equal-family aggregation, nine margins, bootstrap reweighting and leave-one-family-out checks in both full and all-prior-unrepresented strata. Pending. |
| Choosing by incidence improves over choosing by $mJ$. | Fresh task-blocked direct triads on the B cohort, including a structurally defined differing-winner subset. Conditionally authorized by A; pending. |
| The incidence-guided selector improves complete symbolic search within the frozen design. | Confirmation B compares the cap-aware reference, matched-work control and existing alternatives. Conditionally authorized by A; pending. |

## Explicit Non-Claims

- The classical ADD-to-BDD-forest relation is not claimed as new. The claimed
  contribution is the frontier-masked node--terminal statistic, its hierarchy
  and separations, and its use in symbolic-search heuristic selection; this
  novelty boundary remains subject to a bounded literature audit.
- An upper bound for one heuristic does not guarantee its ordinal ranking
  against another. Confirmation A is required for that empirical claim.
- Fixed-frontier incidence does not explain which states guided search reaches,
  bucket residency, image operations, runtime or peak memory.
- A direct $I$-versus-$mJ$ win establishes an effect of the frozen selection
  rule, not fragmentation mediation and not superiority to every possible
  selector.
- Bootstrap intervals describe stability to reweighting the finite frozen
  families; they are not population confidence intervals for unseen domains.
- No result establishes a state-of-the-art planner or transfers beyond the
  frozen PDB pool, probe, representation order and product-at-evaluation search.

The adversarial-review sections below are a chronological audit trail. Their
descriptions of the older diagonal construction remain historically accurate;
where they say that joint tightness was open, that risk is superseded by the
new joint lower bound above.

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
  official AAAI 2027 build now uses all eight content pages without an orphaned
  final body page, and references flow directly after the text.

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

## Round 5: Acting on the Clear-Accept Roadmap

The theory route succeeded: the new polynomial-size multiplexer/modular family
proves joint $\Omega(VWn)$ tightness for independently chosen feasible
parameters. This removes the strongest formal limitation in the 7/10 review.
The remaining high-value risk is evidential alignment: the published matrix
uses one width budget, lacks an acceptance-matched ADD selector, and does not
log the complete profiles needed to instantiate the sharp certificate.

### Highest-value decisive routes

1. **Completed:** prove a joint $\Omega(VWn)$ lower bound, establishing
   independent necessity of all three factors in the coarse upper bound.
2. **In implementation:** run an independently frozen experiment that logs the complete layer and
   heuristic cut profiles, active $V_g$, per-layer bucket effort and unsplit
   layer size. Instantiate $\mathcal C_\pi(L_g,h)$, charge and report profiling
   overhead, and compare actual slack for the profile, width and Apply
   certificates. The frozen design uses $K\in\{2,4,8,16,32\}$, total-ADD-node
   budgets $U\in\{8,29,55,100,204\}$ matched on the original 50-task
   development archive, and an unconstrained exact same-pool selector. Width
   and ADD constraints are varied separately rather than simultaneously.

A fixed-pattern raw-versus-capped search ablation and an independent
replication should follow that combined experiment. An online
split-versus-unsplit policy is potentially stronger, but it changes search
semantics and belongs below these experiments unless accompanied by a new
algorithm and correctness proof. Bidirectional or relational-product bounds
are useful but less direct theory extensions.

### Manuscript-only improvements that can stabilize the verdict

1. Rebuild the narrative as one chain: profile theorem, safe capping, measured
   expansion effort. Keep the PDB family proposition that connects the theorem
   to the case study, but move the potential/M\&S derivations, proof detail and
   most audit mechanics to the supplement. Compress the denominator-heavy
   abstract.
2. Replace the current post-hoc table and selected diagnostic rows in the main
   results table with the strongest target-metric comparison; do not add a
   third empirical table. On the 393 finite-cap triple-solved tasks, pooled
   effort is 1,001,381,935 for blind, 1,133,741,538 for exact and 983,535,036
   for capped search. Thus exact/blind is 1.132, capped/blind is 0.982 and
   capped/exact is 0.868; taskwise signs are 261/33/99 and the leave-one-domain-
   out capped/exact range is 0.850--0.923. Label this an explicitly post-hoc
   follow-up rather than silently folding it into prospective Q3.
3. Use exact endpoints only as a representation negative control: node and
   completed-bucket counts are identical on eligible pairs, but image time has
   ratio 1.01 and the coverage stratum has 0 wins/2 losses. Report the separate
   finite-cap coverage result as 12 wins/3 losses on 1,020 completed trace
   pairs, not as part of the 393-task target-effort denominator. Describe 626/0
   correctly: containment proves zero semantic losses, while the empirical
   finding is 626 added nontrivial choices.
4. Explain width's role relative to ADD size: it is a frontier-independent,
   reusable envelope that composes across heuristic families and yields a
   nested cap ladder. Disclose that the marginal coefficient medians are 8 for
   1,308 completed exact selections and 48 for 1,306 completed cap-aware
   selections; these are different denominators and not a paired causal
   comparison. The paired statement is that capping the same PDB contracts its
   coefficient by a median factor of 12.75 on 1,020 transformations.
5. Budget floats and pages explicitly. Both empirical tables currently defer
   to page 8 while their discussion is on page 7, so a replacement table or
   cut-profile/capping diagram must displace existing material and remain near
   its discussion. Compact pseudocode and complexity should replace current
   mechanics prose or move to the supplement. Consolidate repeated schema,
   digest and censoring caveats into one protocol paragraph.

These presentation changes can make the weak accept more robust, but further
post-hoc diagnostics, another constant improvement, or prose polish alone are
unlikely to justify an 8+ verdict. If new experiments are feasible, the next
ablations after the combined profile/ADD/multi-budget study are repeated
cutoff-sensitive discordances and timing measurements.

## Round 6: Conditional Explanatory Reframing

The proposed story is stronger than the current theory-led story only if the
new, outcome-blind experiment supports both its explanatory and algorithmic
links.  It gives the paper a single motivating question, distinguishes a
symbolic-search mechanism from ordinary heuristic quality, and turns the
theory into a design rule.  Without those links, the same framing would be
weaker because it would promote a predictor or selector beyond the evidence.
The manuscript therefore remains conditional until the frozen gates in
`experiments/pdb_profile_predictor_protocol.md` have been evaluated.

### Fixed conceptual roles

Use one term for each object throughout the abstract, introduction, theory,
and experiments.

- **Selector score** is the frozen lexicographic tuple of initial dead-end
  recognition, initial value, mean finite value, and abstract dead-end
  fraction.  It is the explicit-search-motivated control, not a definition of
  pointwise heuristic strength or a representation measure.
- **Local representational fragmentation** means separately representing the
  value slices of one fixed state set.  The empirical **normalized bucket
  overhead** aggregates the same mechanism over a solved run: cumulative
  expanded bucket effort divided by the semantic union effort of the same
  generated layers.  It is undefined when either profile is incomplete or the
  union effort is zero, and it does not explain coverage discordances.
- **Cofactor width** $W$ is the frontier-independent structural predictor.  It
  is standard fixed-order MTBDD width and, in the theory, only a one-sided
  safety envelope.  Calling it a predictor is an additional empirical claim
  licensed only by the frozen gate.  Its connection to symbolic-search
  fragmentation and its use in heuristic construction are the contribution.
- **Total ADD size** $U=A+T$ is the closest static representation baseline.
  The acceptance-matched ADD selector is a control, not a causal isolation of
  width.
- **The cut-aligned profile certificate** $B_{\mathrm{profile}}$ multiplies the
  marginal layer and heuristic residual counts at corresponding cuts.  It
  upper-bounds realized residual pairs but does not model their correlation.
  This frontier-dependent, ex-post quantity is compared with its width
  relaxation $B_{\mathrm{width}}$ and the ordinary Apply certificate
  $B_{\mathrm{add}}$ on the same exact target, cumulative expanded-BDD-node
  effort.
- **Cap-aware width selection** is the derived construction.  Its algorithmic
  evidence is separate from the predictor evidence and is evaluated against
  exact-width selection, matched ADD filtering, the unconstrained endpoint,
  and profiled blind search at all five frozen budgets.

### Outcome-contingent paper shape

1. If the width-predictor, profile-certificate, matched-ADD, and cap-aware
   construction gates all pass, lead with the explanatory chain: quality does
   not characterize symbolic fragmentation; cofactor structure does; the
   cut-aligned metric sharpens that explanation; and a selector derived from
   it improves the matched controls.  Planner dominance remains a separate
   claim and requires the blind-coverage gate.
2. If the predictor gates pass but either selector gate fails, lead with the
   explanatory metric and present the selector as a negative or mixed design
   test.  Do not promise a successful new heuristic in the title, abstract, or
   contribution list.
3. If a selector gate passes but the corresponding predictor gate fails,
   retain a theory-and-algorithm framing.  Report the selector improvement but
   do not attribute it to a validated explanation of relative performance.
4. If the central predictor and construction gates fail, retain the current
   theory-led certificate framing.  Report the preregistered negative result as
   a limitation and do not substitute a favorable budget, denominator, or
   post-hoc metric.

### Concept and evidence order after unblinding

The explanatory version should introduce the tension before the machinery:
(1) quality controls how many states search reaches, while fragmentation
controls how those states are represented; (2) define the isolated
fragmentation response; (3) introduce cofactor width and the cut-aligned
profile product; (4) prove the exact bucket and search certificates; (5)
derive safe caps and the selector; and (6) test prediction before reporting
planner outcomes.  The results should follow the same order: predictor
concordance, certificate concordance, matched width-versus-ADD contrasts,
cap-aware versus exact-width contrasts, and only then blind-search coverage.

One compact predictor table should report macro concordance, comparable-pair
support, and leave-one-domain-out ranges for $W$, $U$, quality, and the three
certificates.  One five-row budget table should report the fixed $(K,U)$
pairs, full-denominator coverage discordance, conditional effort ratios, and
eligible-pair counts for the selector contrasts.  Every claim must name
whether it concerns fragmentation, conditional effort, coverage, or planner
runtime; none of these outcomes may stand in for another.

### Final gate outcome

The exact explanatory framing is not supported strongly enough to replace the
theory-led story. The initial 1,327-task profile experiment had no eligible
fragmentation observation because every semantic-union denominator was
recorded as zero. Its certificate concordances were 0.409 for the profile,
0.407 for the width relaxation, and 0.369 for Apply; the matched-ADD and
multi-budget construction gates also failed.

The corrected, frozen 275-task semantic-union follow-up produces 1,746 shared
strict pairs from 113 tasks in 39 domains. Width's equal-domain concordance is
0.786 (LODO 0.780--0.807), compared with 0.766 for total ADD size and 0.228
for the frozen information-quality tuple. Every effect and domain criterion
passes, but task support is below the preregistered floor of 184. The overall
gate therefore fails and its frozen consequence applies: do not tune a rescue
selector. The manuscript keeps the theory-and-algorithm framing, reports the
strong but under-supported signal as suggestive, and does not claim that width
is a validated predictor of relative planner performance.

## Round 7: Prospective Unseen-Order Decision

The decisive follow-up uses four previously unseen Gamer-order seeds while
holding the PDB, heuristic values, costs, expanded states, and active buckets
fixed. It covers 4,208 completed cells (1,052 tasks by four seeds). After the
frozen completeness and invariance checks, 440 tasks remain eligible. The
primary shared strict set contains 1,832 distinct-order pairs from 313 tasks
in 40 domains, comfortably exceeding every support floor.

The co-occurring certificate recovers structural signal that the relaxations
lose: its equal-domain concordance with normalized fragmentation is 0.631,
compared with 0.494 for the Cartesian profile, 0.480 for the width relaxation,
and 0.474 for the ADD relaxation. It is also substantially tighter: across
1,760 eligible observations, its ratio to the Cartesian certificate has
median 0.205 and mean 0.251. However, the denominator-only null reaches 0.641,
giving a margin of -0.009, and the leave-one-domain-out non-worsening criterion
fails. The preregistered primary decision is therefore a failure. The
unnormalized co-occurring certificate reaches 0.733 on 2,237 strict pairs and
passes its secondary gate, but unsplit effort is stronger at 0.905.

The strongest supported framing is consequently theory-first:
**Heuristic Fragmentation in Symbolic Search: Cofactor Certificates and Their
Limits.** The new scientific contribution is the co-occurring certificate,
its tight worst-case theory, and the empirical diagnosis of what its
Cartesian and width relaxations discard. It is a useful representation
diagnostic, not an independent scalar predictor of relative performance. The
width-constrained selectors are a mixed design stress test: they reduce
conditional effort relative to unconstrained heuristic selection but remain
worse than blind search. No seed, task subset, denominator, threshold, or
adaptive experiment replaces the failed primary decision, and the title,
abstract, contribution list, limitations, and conclusion all preserve that
boundary.

## Round 8: terminal-incidence reframing and prospective confirmation

The terminal-incidence story is stronger than the previous cofactor-width
story, conditional on the frozen confirmation succeeding.  The metric now
retains the exact node--terminal reachability relation of the masked ADD, sits
between exact partition effort and the existing certificates, and yields both
cofactor and Apply proof branches.  This supplies a precise answer to what the
older relaxations discard instead of merely proposing another correlated
scalar.

The empirical claim remains deliberately gated.  Confirmation A must show
that incidence predicts fixed-frontier exact partition effort beyond the
developmental predecessor and the denominator-only null; the direct selector
then tests whether replacing the predecessor by incidence changes a final
heuristic choice usefully.  The evaluation must also report the exact-effort
oracle regret and measurement cost, because a reviewer can otherwise ask why
the selector does not optimize the target directly.  Study B is algorithmic
evidence about representation-budgeted selection, not proof that incidence
mediates end-to-end search performance.

The asymptotic construction is claimed only as a decision-diagram family.
Planning realizability is supplied by the separate PDB ordinal witness.  The
paper does not claim that the developmental predecessor was a community
consensus, nor that one metric explains heuristic quality in general.  Title,
abstract, and conclusions remain provisional until the frozen branch is
rendered from sealed artifacts.
