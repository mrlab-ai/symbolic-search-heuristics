# ICAPS paper-polish worklog

Run label: 2026-09-02 full-paper, write-enabled extreme polish.  This is an
author-side audit record, not part of the anonymous review bundle.

## Paper contract

| Deliverable and scope | Target, audience, and mode | Anonymity and page policy | Build command and PDF | Prior version |
|---|---|---|---|---|
| `paper/paper.tex` and `paper/supplement.tex`; theory, staged confirmations, and review bundle | ICAPS 2027 long paper; broad planning audience; anonymous review | ICAPS 2027 CFP not published as of 2026-09-02. Provisional contract follows the official ICAPS 2026 rule: 8 content pages plus reference pages, anonymous AAAI format, optional anonymized supplement, self-contained main paper. | `make -C paper submission-audit`; current pre-result build: 8 main-PDF pages and 40 supplement pages | Parent revision `ed2287aec540`; terminal-incidence result slots remain deliberately unresolved |

## Contribution map

| Contribution | Exact scope | Support | Strongest objection | Status |
|---|---|---|---|---|
| Terminal incidence `I` | Fixed frontier, fixed Boolean order, reduced masked ADD | Definition; terminal-charging proof gives `E <= I` | The basic ADD/BDD-forest relation is classical; novelty must be the node--terminal relation and its planning use | Theory present; novelty wording under final audit |
| Two-branch certificate hierarchy | Fixed-frontier partition-node sum, not runtime or peak memory | Cofactor/residual chain and independent standard-Apply chain | Bounds do not imply an ordinal order between two heuristics | Proved and explicitly scoped |
| Exact and ordinal separations | Constructed Boolean family; one exact-PDB blind-layer witness | Exact counts and supplement proofs | Constructions may not describe typical planning tasks | Proved; typicality explicitly disclaimed |
| Terminal-map contraction | Fixed frontier; caps preserve admissibility and consistency | Contraction proposition plus four-variable counterexample for nonmonotone `E` | Fixed-frontier contraction does not imply search improvement | Proved and explicitly bounded |
| Incidence-guided PDB selector | Frozen candidate pool and 16-layer blind probe | Probe-budget-safety proposition | Probe may not represent guided frontiers; selector could fail downstream | Algorithm frozen; empirical claim pending |
| Predictor claim | `I` versus `D`, active-value count and seven certificate baselines on source-disjoint A cohort | Confirmation A with target-strict, family-macro, bootstrap-reweighting, and LOFO gates | Support failure or a strong baseline, especially `B_wedge`, could defeat the story | Pending source audit and A |
| Metric-choice claim | `I`-guided versus developmental predecessor `mJ` on fresh B-cohort runs | Task-blocked direct campaign; differing-winner subset | Cohort is shared with B and the two winners may often coincide | Conditionally authorized only by A; pending |
| Broader selector claim | Incidence-guided versus cap-aware reference, matched work, and alternatives | Confirmation B | Fixed pool and probe; no general state-of-the-art claim | Conditionally authorized only by A; pending |

## Section map

| Section | Reader task | Depends on | Supports | Specialist lanes | Main risk |
|---|---|---|---|---|---|
| Abstract | Understand problem, metric, guarantee, selector, and staged evidence | Final sealed results | Headline claims | cold reader, claims | Currently prospective; cannot be final until results render |
| Introduction | Follow one causal chain from heuristic fragmentation to missing node--terminal relation | Related-work boundary; developmental failure | All contributions | framing, novelty | Too much protocol detail could obscure the idea |
| Fixed-Frontier Partitioning | Distinguish target `E`, masked size `D`, active-value count, and incidence `I` | BDD/ADD conventions | Metric and computation | concepts, theory | Shared-manager counting and fixed-frontier scope must stay explicit |
| Certificate Hierarchy | Verify both branches, baseline meanings, and separations | Definitions | Predictor choice and theory | theory, notation | Upper bounds do not guarantee ordinal prediction |
| Terminal Maps and Caps | Understand contraction and its exact-effort exception | Hierarchy | Candidate ladder | theory, algorithm | Any monotonic-search implication would overclaim |
| Incidence-Guided PDB Selection | Reconstruct pool, budget, score, and matched controls | Caps; fixed probe | New heuristic | algorithm, reproducibility | Score and budget roles must not blur |
| Confirmatory Evaluation | Audit source split, gates, and dependence between campaigns | Frozen protocols and V6 selective-repair source audit | Empirical claims | experiments, statistics | Results are currently unresolved by design |
| Related Work | Locate novelty relative to symbolic search, ADD forests, compression, and PDB selection | Verified bibliography | Novelty boundary | source audit | `I` may need a narrower novelty claim if prior terminology is found |
| Limitations and Conclusions | State exactly what each gate can establish | All results | Scope control | hostile reviewer | Must be rewritten outcome-conditionally |
| Supplement | Supply full proofs, frozen protocols, developmental negatives, and source detail | Main paper | Self-containment support | theory, experiments, sources | Reviewers are not obligated to read it; decisive evidence must remain in main paper |

## Wave coverage and cost

| Candidate | Wave and persona | Assigned sections | Expected reports | Reports complete | Audit complete | Repairs verified |
|---|---|---:|---:|---:|---:|---:|
| Pre-result candidate | Initial contract, section map, and whole-source read | Main and supplement | 1 | 1 | 1 | 1 |
| Pre-result candidate | Independent protocol/code audit | A/B/direct and shared cell runner | 1 | 1 | 1 | 1 |
| Pre-result candidate | Independent manuscript claim audit | Main and supplement | 1 | 1 | 1 | 1 |
| Pre-result candidate | Local verification | Tests, renderers, checker self-test, PDFs | 1 | 1 | 1 | 1 |
| Pre-result candidate | Independent formal audit | Hierarchy, separations, contraction, selector safety | 1 | 1 | 1 | 1 |
| Pre-result candidate | Bounded novelty/source audit | Decision diagrams, multi-output representations, symbolic planning | 1 | 1 | 1 | 1 |
| Final frozen candidate | Fresh ICAPS reviewer, hostile senior planner, clarity/flow reader | Complete immutable paper-only packet | 3 | 0 | 0 | 0 |

Expected remaining cost after sealed results: three independent full-paper
reports, one consolidated audit, and one verification rerun; any
acceptance-critical finding triggers a fresh replacement report for that lane.

## Findings and progress

| ID | Wave and section | Severity | Evidence and consequence | Decision or repair | Affected sections | Verification | Status |
|---|---|---|---|---|---|---|---|
| F01 | Contract | Acceptance-critical | ICAPS 2027 has a live site but no CFP; treating AAAI's own page rule as ICAPS's rule would be unsupported | Keep the 8-page ICAPS 2026 rule and two-PDF bundle explicitly provisional until the 2027 CFP appears | Build/checker comments and revision strategy | Official ICAPS 2026 CFP and ICAPS 2027 site checked 2026-09-02 | Resolved provisionally |
| F02 | Abstract/results/conclusion | Acceptance-critical | Result insertion slots and source-audit marker are intentionally unresolved | Do not certify, commit final paper, or upload until the source audit and every authorized campaign seal and render | Abstract, evaluation, conclusion, supplement | Submission checker must continue to fail closed | Open |
| F03 | Hierarchy/evaluation | Important | The two certificate branches admit a stronger prospective scalar baseline than either aggregate branch alone | Add `B_wedge = sum_g min(k_g D_g, A_Apply,g)` as the seventh certificate baseline and require an eighth margin | Main, supplement, A protocol/analyzer, renderer | Focused protocol, analysis, renderer, adversarial tests and independent code audit | Resolved |
| F04 | Reproducibility | Important | Final runtime comparisons require allocated processor models, but host/job identifiers would harm anonymity | Record only normalized processor model and architecture per cell; seal ordered digests and counts and require within-element consistency | A/B/direct execution and audit; results prose | Shared runner and campaign tests plus independent provenance/recovery audit | Resolved |
| F05 | Style | Advisory | Automated style diagnostics request a roadmap and sentence-length quotas, while 19/20 nearby papers omit a roadmap | Reject quota-driven edits; retain direct causal structure and stable terminology | Main paper | Whole-paper read against Jendrik corpus guidance | Resolved |
| F06 | Build | Minor | The pre-result main PDF has one underfull bibliography line but no overflow | Reassess after final result insertion; do not distort correct prose merely to silence an underfull box | References | Final log and page-by-page inspection | Open |
| F07 | B authorization | Acceptance-critical | B still unpacked the old three-field A seal and therefore could not authorize after execution-hardware provenance was added | Recompute B's imported A authorization with the execution-receipt hash and validated hardware summary, and export both | B protocol and tests | Independent protocol audit; B regression suite | Resolved |
| F08 | Direct authorization | Acceptance-critical | The direct campaign's exact-key boundary rejected the expanded A authorization | Require the expanded exact key set, validate the execution SHA and the 2,600-cell hardware summary | Direct protocol and tests | Independent protocol audit; direct regression suite | Resolved |
| F09 | A diagnostics | Important | Certificate tightness omitted the layerwise meet; an interim all-predictor repair would incorrectly treat non-certificate `D` as an `E` upper bound and could abort on valid `D=0,E>0` | Use exactly `I` plus the seven certificate baselines for `E/P`; explicitly omit `D` | A analyzer, protocol, tests | Regression with `D=0,E=1`; 53 post-repair A/direct tests | Resolved |
| F10 | Formal precision | Important | The core proofs were sound, but six statements omitted conditions or typing details: `L>=log_2 k`, map codomain, total counterexample, absent per-pattern feasible candidate, nonempty probe sets and the layerwise Apply definition | State every condition; give a total admissible-consistent planning embedding for the cap counterexample | Abstract, hierarchy, terminal maps, selector, supplement | Independent proof reconstruction and exhaustive finite checks; both PDFs rebuilt | Resolved |
| F11 | Framing/evidence | Important | A strong ICAPS story needs to answer why not optimize exact `E` and must not present end-to-end effects as mediation evidence | Require exact-`E` selector regret and timing diagnostics in A, all configurations in B, and retain the fixed-frontier/performance boundary | Results renderer, evaluation, limitations, conclusion | Pending sealed results and final reviewer trio | Open |
| F12 | Novelty boundary | Important | Torralba (2015, Proposition 2.1) already proves the terminal-substitution bound for each value BDD; Ciardo and Miner compare the shared per-value forest, and Duret-Lutz et al. use per-node reachable-terminal sets | Present `I` as the frontier-masked aggregate and node-local refinement giving `E <= I <= kD`; distinguish rootwise `E` from shared-forest size; use only a qualified prior-use statement | Abstract, definition, terminal-charging proof, related work, bibliography | Bounded primary-source audit over the closest ADD/MTBDD, one-hot and symbolic-planning work | Resolved |
| F13 | Cold-reader framing | Important | The broad “heuristic fragmentation” title could be read as explaining heuristic quality or search-space reduction, which the fixed-frontier evidence does not establish | Scope every outcome-dependent title to fixed-frontier partition effort, align the supplement title, and retain the explicit end-to-end non-claims | Title branches, abstract, supplement, submission checker | Exact title allowlist and rejection fixtures; checker self-test rejects 149 source and 46 bundle adversaries | Resolved |
| F14 | A predictor controls | Important | Masked node count tests the row dimension of the incidence relation, but the frozen gate did not test the summed active-terminal column count; incidence could appear predictive merely because it proxies that count | Add `value_count = sum_g k_g` as the second non-certificate gating challenger in both strata, strictness variants and regret diagnostics; exclude it from certificate tightness; bump A analysis to v4 | Main, supplement, A protocol/analyzer, downstream contracts and tests | Exact witness ties at `value_count=3`; focused protocol and analyzer tests | Resolved |
| F15 | Performance interpretation | Important | Coverage and PAR2 alone do not distinguish gains from discordant solves from speed changes on jointly solved tasks | Add a non-gating paired 2-by-2 solve table and equal-family normalized common-solved time difference to every direct and B contrast, frozen before either campaign runs | Direct and B analyzers, protocols, supplement and tests | Hand-constructed four-cell decomposition regressions | Resolved |
| F16 | Source provenance | Acceptance-critical | Terminal V5 contains infrastructure failures and therefore cannot produce the complete original-only seal required by the prior A/B/direct consumers | Prospectively freeze an infrastructure-only V5 diagnostic; repair only its exact noncompleted complement in V6; admit only scheduler-`COMPLETED`/`0:0` V5 triplets; bind the exact 820-shard origin/hash union, pre-diagnosis revision, crash-recovery stages and both producer revisions; migrate every downstream consumer to strict V6-only paths and schemas | V6 producer/consumer, A, B, direct, supplement, checker | 50 V6 producer/consumer tests and 281 integrated A/B/direct tests; checker and both PDFs rebuilt | Resolved |
| F17 | Dependence disclosure | Important | The direct metric-choice campaign and Confirmation B use the same 300-task cohort and could be misread as independent replications | State that their separately executed cells and contrasts answer complementary questions but are not independent replications | Supplementary confirmatory protocol | Exact cohort identity and prose inspection | Resolved |

## Concepts, claims, and numbers

| Item | First use or occurrence | Introduction or support | Scope and prerequisites | Canonical form | Status |
|---|---|---|---|---|---|
| Exact partition effort | Abstract; definition in Fixed-Frontier Partitioning | Bucket-node sum before later search operations | Fixed frontier and variable order | `E = sum_v |BDD(S intersect h^{-1}(v))|` | Stable |
| Terminal incidence | Abstract; formal definition | Masked ADD node--terminal reachability | Fresh bottom terminal; active nonbottom terminals only | `I = sum_u |T_M(u)|` | Stable |
| Masked ADD size | Hierarchy discussion | Non-certificate ordering control | Same masked ADD as `I` | `D` | Stable |
| Active-value count | Hierarchy discussion | Non-certificate column-count control | Summed over the same common frontier layers as `I` | `N_val = sum_g k_g`; artifact key `value_count` | Stable |
| Developmental predecessor | Introduction and direct test | Co-occurring residual pairs | Not a consensus or strongest-known predictor claim | `mJ` | Stable |
| Layerwise meet | Hierarchy and A protocol | Strongest direct combination of the two proved branches | Must be computed before aggregation | `B_wedge = sum_g min(kD_g, A_Apply,g)`; artifact key `meet` | Stable |
| Predictor gate | Confirmation A | Ten predictors total; nine margins from `I` | Source-attested A cohort and all-prior-unrepresented stratum | Macro >= 0.65; each margin >= 0.02; bootstrap lower and every LOFO difference positive | Frozen, pending |
| Direct metric gate | Direct experiment | `I`-guided minus `mJ`-guided | A pass; complete B-cohort triads; differing-winner subset support | Coverage nonlower; family-normalized PAR2 improvement >= 0.02; bootstrap lower and LOFO positive | Frozen, pending |
| Selector gate | Confirmation B | Guided versus reference and matched work | A pass; source-disjoint B cohort | Same effect/stability clauses against both controls | Frozen, pending |

## Shared empirical ledger

| Question | Configuration and revision | Command | Population and exclusions | Budget | Metric | Raw source | Generated output | Statistical scope | Status |
|---|---|---|---|---|---|---|---|---|---|
| Can a complete source-disjoint A/B cohort be attested? | Source-audit campaign v6; terminal V5 diagnostic and both producer revisions are bound | `experiments/launch_pdb_terminal_incidence_confirmation_source_audit_v6.py diagnose-v5`, `prepare-manifest`, `launch`, `status`, then `seal` | Exact 820-shard/1,640-candidate union; V5 reuse only for scheduler `COMPLETED`/`0:0`; complete-shard repair; zero V1--V4 or partial noncompleted reuse | One diagnostic-selected uniform repair profile on `fat`; no throttle | Exactly 650 A and 300 B with family/novelty floors | Scheduler-eligible V5 triplets plus V6 repair triplets | Sealed mixed source inventory, origin ledger, and cohort records | Deterministic infrastructure-only repair and census/split; no inferential claim | Prospective V6 selective repair; no source outcomes read |
| Does `I` rank `E`? | Confirmation A, four direct PDB generators | Frozen A launcher/analyzer | 650 source-attested tasks; target-strict semantic-PDB pairs; no silent cell exclusion | 1,800 s, 24,576 MiB per cell | Tie-aware family-macro concordance and nine margins | Sealed A matrix | Analysis v4 and paper renderer | Finite-cohort bootstrap reweighting plus LOFO; primary and all-prior-unrepresented gates | Not launched; blocked on source-inventory seal |
| Does metric choice change search? | Direct I/mJ/matched triads | Frozen direct campaign | 300 B tasks; full contrast retains symmetric short probes | 1,800 s per arm | Coverage and family-normalized PAR2 | Fresh direct runs | Sealed direct analysis and renderer | Full and structurally defined differing-winner gates | Conditionally blocked on A pass |
| Does incidence-guided selection improve over controls? | Confirmation B, nine configurations | Frozen B launcher/analyzer | Same 300-task B cohort; no task removed from matrix | 1,800 s, 24,576 MiB per cell | Coverage and family-normalized PAR2 | Fresh B runs | Sealed B analysis and renderer | Two comparator gates and prespecified mechanism subset | Conditionally blocked on A pass |

## Sources, builds, and PDF

| Claim, rule, or candidate | Source, command, or PDF | Access date or build result | Diagnostics or page findings | Outcome |
|---|---|---|---|---|
| ICAPS provisional submission contract | `https://icaps26.icaps-conference.org/calls/cfp/` and `https://icaps27.icaps-conference.org/` | Accessed 2026-09-02 | 2026: 8 content pages plus references, anonymous AAAI format, anonymized optional supplement, self-contained main; 2027 CFP absent | Use provisionally and recheck before submission |
| ICAPS review criteria | `https://icaps27.icaps-conference.org/organisation/reviewing/` | Accessed 2026-09-02 | Significance, clarity, appropriate prior work; page/format violations may be desk-rejected | Included in reviewer packet |
| Main PDF | `env -u APPTAINER_BIND latexmk -pdf -interaction=nonstopmode -halt-on-error -g paper.tex` | Rebuilt after the value-count/control amendment | 8 pages total; no overfull, undefined-reference, or undefined-citation warning; underfull lines only | Layout healthy but not final |
| Supplement PDF | `env -u APPTAINER_BIND latexmk -pdf -interaction=nonstopmode -halt-on-error supplement.tex` | Rebuilt after the value-count/control amendment | 40 pages; no overflow, undefined reference or undefined citation | Layout healthy but not final |
| Submission checker | `python3 paper/check_submission_ready.py --self-test` | Pre-result run | 149 source adversaries and 46 review-bundle adversaries rejected | Self-test passed; production check correctly blocked by unresolved result marker |
| Protocol/code verification | `python3 -m unittest` focused and campaign suites | Independent audit: 91 tests; post-repair root rerun: 53 tests; current amendment: 18 A gate/protocol, 18 direct-analyzer and 21 B-analyzer checks plus downstream namespace checks | B/direct authorization, hardware, recovery, meet, value-count gating and certificate-only diagnostics covered | Passed; no remaining correctness finding in audited scope |
| Current source-audit boundary tests | Pinned venv under the campaign's controlled environment | V5 producer tests retained; V6 producer, recovery, and shared-consumer tests added | 50 V6 producer/consumer tests plus 281 integrated A/B/direct tests cover schemas, exact complement, Slurm/resource rows, environment/log triplets, five-stage recovery, union origins/hashes, and dual-revision closure | Passed without scheduler or runtime-output access |
| Formal verification | Independent proof reconstruction plus exhaustive finite enumeration | 65,534 nonempty binary-frontier cases through three variables; 33,615 ternary cases through two variables | Hierarchy and contraction had no counterexample; witness counts independently recovered | Passed after six wording/typing repairs |

## Exact next action

Commit the now-verified V6-bound source tree before any source outcome is
opened. Then create the infrastructure-only terminal-V5 diagnostic and
manifest in protocol order, and launch only the exact repair complement.
