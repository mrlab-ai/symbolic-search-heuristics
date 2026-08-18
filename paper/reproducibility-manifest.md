# Private reproducibility audit manifest (release after unblinding)

This internal manifest contains exact historical identities that are
intentionally omitted from review-facing material. It must not be included in
the double-blind submission bundle. After unblinding it accompanies a
record-and-analysis verification pack, not a complete implementation/build
artifact. Scheduler job, account, user, node, and absolute-path values belong
only to this private audit record. Each SHA-256 value is a
lowercase hexadecimal digest of the byte sequence named by its entry: JSON
artifacts explicitly say “raw,” while task, source-record, and matrix entries
refer to their protocol-defined normalized or canonical streams.

The record-level replay prototype uses a deterministic semantic projection that
retains every scientific field while replacing four packaging fields:
`benchmark_worktree`, `repo`, `node`, and `scheduler_account`. Source snapshots
exclude Git metadata and disable launch entry points. The private audit
record retains the original fetched properties and raw execution evidence; their
hashes below bind that record without publishing identifying bytes. Before
artifact release, the verifier must establish that the numerical and scientific
objects reproduce the immutable aggregate JSON files exactly after excluding
only the explicitly path-dependent properties digests.

The projected P4 and P5 properties have raw SHA-256 values
`6b7bfa9515105825e775e33356f61764ed1c555c5273514b87be591ab369529b`
and
`4267f384cc6e23d634796fe33efd0054c103d8186df3d4f4fb44f7613c2ce45b`,
respectively. The analysis-only source snapshot is a deterministic
1,853,440-byte USTAR archive with raw SHA-256
`4abbda181734bbe37b89c9aab53771b4e78875c6e4a11280a919fc9bdd671602`;
its 17-file content identity is
`8d0f34d6e05f73ffa55d29327e0bef4cd1ddffb1b7f80afed6718233c87e3a2d`.
It contains historical revision strings and source bytes that are linkable to
public Git history. It therefore must not be distributed during double-blind
review. The exact source snapshot, projected records, inverse mapping, and audit
sidecar are released only after unblinding. Because related manuscript source
has previously been public, packaging alone cannot guarantee cryptographic
unlinkability; venue disclosure rules require an explicit chair ruling.

## Executable protocol sources

- Stage-1 runner and analyzer:
  `experiments/exp_arrhenius_selector_pilot.py` and
  `experiments/analyze_arrhenius_selector_pilot.py`
- Stage-2 runner and analyzer:
  `experiments/exp_arrhenius_selector_validation.py` and
  `experiments/analyze_arrhenius_selector_validation.py`
- Stage-3 runner and analyzer:
  `experiments/exp_arrhenius_selector_full.py` and
  `experiments/analyze_arrhenius_selector_full.py`
- Separate secondary Stage-3 structural diagnostic:
  `experiments/analyze_arrhenius_selector_full_structure.py`
- Fail-closed Stage-3 paper-data and TeX renderer:
  `experiments/render_arrhenius_selector_full_paper.py`

The screen analyzer has separate canonical selection and descriptive-report
modes. The full renderer accepts only the pinned canonical primary-analysis and
secondary-structural artifacts with their exact SHA-256 sidecars; their hashes
and the launch identities form one atomic production gate, set only after both
artifacts passed independent review.

## Common benchmark identity

- Benchmark repository revision:
  `48d6a00d482de2384a9e751f9343df58bf5582be`
- Benchmark origin: `https://github.com/aibasel/downward-benchmarks`
- Every selected PDDL source is byte-attested before grid construction.
- Every run receives independent, read-only, single-link copies of its domain
  and problem files; the launch gate rechecks their content hashes.

## Stage 1: P4 screen

- Artifact-freeze revision:
  `da50f09886bed8c09c73ec5358e49cdde2ce0832`
- Analyzer bytes at that revision have SHA-256
  `6b9aa46c2670e89727ceee6d8ae9922d21c8bd818a770327219abd9cfb026f84`.
- Planner revision: `58a3f742d7ac63f391d06c237573f14ad590c187`
- Stripped planner binary:
  `59b97e8b1e777f700c255932271604393f60ec9aeba5c0151d0b7415a3a58511`
- Copied preprocessor:
  `acf2fc66c0b189095111a9d227ccb5b7acc564f1a6cb7bfd557904fa3c76798c`
- Launch-protocol revision:
  `d6d98ad42f3976cd5cf0c9b17d8fa255354fbfbf`
- Normalized task sequence:
  `3195dac7e62a34e5ac4cbeb715ab7f9b99e2ee64341082dd7d718ea2820751ca`
- Selected task-source records:
  `dbb7730c257472c07f7946f0434949449169e06d1faa2174a92a6d13c48cb8ba`
- Complete 20-configuration option matrix:
  `e16f6e34af5101a3549bfbf98ebaba23371c645f9166c884bfdf07b3b65e7442`
- Accepted fetched properties: 1,000 records and 13,427,825 raw bytes, with
  raw SHA-256
  `8b3e6862629a6a7b9234c13083e9840956be5bd973de49e6c9e7831627274dbb`
  and protocol-canonical logical SHA-256
  `18c53fb37c3968ab394643da6caff73eb822bbc96eda1836a9bf138b716ffbce`.
- Selection artifact:
  `experiments/artifacts/arrhenius-selector-screen-p4/selection-v3.json`
  with raw SHA-256
  `d35a1df68eebbd099fe81f86e6e0f6a96ce770572574f9ae013ab4eb0b2c8eb2`
- Certified descriptive report:
  `experiments/artifacts/arrhenius-selector-screen-p4/certified-report-v2.json`
  with raw SHA-256
  `e75daadefc6cf3cad3121ffb28959659dbc78523970945d575a97b18a319252c`
- Experiment protocol: a privately mapped exact Stage-1 screening-v2 identity
- Selector pool: `fixed_pool_v1`
- Candidate score:
  `init_dead_init_h_mean_dead_fraction_width_states_pattern_v1`
- Whole-trace parser:
  `run.log/pdb-final-and-width-selector-v1-whole-trace/v3`
- Metric validation: `wbh-exact-schema-semantic-v3`
- Outcome certification:
  `direct-search-raw-effective-plan-reconciliation/v1`

## Stage 2: P5 held-out run

- Analysis-freeze revision:
  `3255868fcf059c1e94f0377fb98a0d1551349f9f`
- Analyzer bytes at that revision have SHA-256
  `3c85051dfa14383d785b4daf7f00e907fea6522940c02f7973862c4e3308e22d`.
- Planner revision: `165b6d2ee29d5d7b6e1bf4c52540c393ba19b54f`
- Stripped planner binary:
  `af2a19d236ecad9b747d2a1b9c49da73d98248c38d21cc60ad0ac7613d74bdbe`
- Copied preprocessor:
  `1b351a4a5f9380bf41fe9fd61b98c816505ebd8cf88b20afa0d81a9bfb2474bd`
- Launch-protocol revision:
  `a52488637a1c054b26dac93fe2eb1a556110a2dd`
- Execution protocol: a privately mapped exact Stage-2 validation-v3 identity
- Initial-dead construction protocol:
  `pdb-ms-initial-dead-bdd-construction-prelog/v1`
- Normalized task sequence:
  `fc63d4eed62816a2e065cb89f89483999a7b51067b7077969d10b2a338f19760`
- Selected task-source records:
  `14202b66a4ed4ea7afa9f204d15cbfe8857b061a644661fc9d68b3624523fdf4`
- Seven-configuration matrix:
  `b4a695874c1292a0a26cc72ab7ebeea2b6775eec71970cd1b91aaad1c8211354`
- Accepted fetched properties: 644 records and 9,834,799 raw bytes, with
  raw SHA-256
  `d508298425b356023b589e643115ab482419c140da19b6744bbeff57a84bc10f`
  and protocol-canonical logical SHA-256
  `0fab37f024188138f0ef2c1468bfe688404243f05cf682212532adf6e200cab1`.
- Accepted analysis:
  `experiments/artifacts/arrhenius-selector-heldout-p5/analysis-v3.json`
  with raw SHA-256
  `7c598f068164224272b8ba035b987973f35d0d45e695f90c9083931790908cea`

## Stage 3: P6 full census

- Planner revision: `a3486a027a0f281e762cb6d66d72311455b66b33`
- Stripped planner binary:
  `2887194c74acc88273702b807dba28e4fd8f7ae3d916562bcf1b83ec79632758`
- Copied preprocessor:
  `40e1d5580ec447cb606ead447317469bd861bd8cda398095df3fbf22922d0d23`
- Launch-protocol revision:
  `0cb19e111da36fbb32d1b3bc0f07a52b733fbbe9`
- Full runner source:
  `3a7cfd4307217db13a8ec42d9157cd2290b0e8fba962f9aa40815af80d06058f`
- Execution protocol: a privately mapped exact Stage-3 population-v4 identity
- Analysis schema:
  `symbolic-search-heuristics/full-population-analysis/v4`
- Analysis protocol: `full-supported-population-census-v1`
- Secondary structural schema:
  `symbolic-search-heuristics/full-population-structure/v1`
- Secondary structural protocol: `p6-secondary-structural-diagnostic/v1`
- Secondary structural artifact path:
  `experiments/artifacts/arrhenius-selector-full-p6/structure-v1.json`
- Secondary-decision boundary:
  `frozen-during-active-p6-execution-before-canonical-full-result-analysis/v1`;
  protocol audits had already parsed individual structural fields and displayed
  a few diagnostic records, but its estimands and aggregation/correlation rules
  were frozen before any comparative structural summary, association,
  correlation, or ranking was computed. This diagnostic is neutral only with
  respect to the already frozen primary result: it was not launch-predeclared
  and cannot change the primary census, sensitivity, matrix, ranking, or
  denominator.
- P5-to-P6 lineage protocol:
  `git-merge-base-is-ancestor/p5-protocol-and-planner-to-p6-planner/v1`
- Pre-search normalization protocol:
  `driver-translate-and-legacy-preprocess-negative-sigxcpu-to-21/v1`
- Retained-outcome census:
  `protocol-recognized-final-cell-outcome-census/v1`, whose unit is
  `final-retained-attested-cell-records`
- Full task sequence:
  `295bff030c51eaf39871714335ff9cb945ce39ebc556774eeb3bfad112681345`
- Selected task-source records:
  `9ce25a012592bfb2557fe21cc4a3fdb3dbd24f9d2a4ed79ee16e75be183be5dd`
- Seven-configuration matrix:
  `b4a695874c1292a0a26cc72ab7ebeea2b6775eec71970cd1b91aaad1c8211354`
- Submitted 9,639-cell job script:
  `c83c880c1bfaa503cfffab69c91abb037e58b4424b7216480aa551631aed043f`
- Accepted fetched properties: 9,639 records and 253,931,367 raw bytes, with
  raw SHA-256
  `6003ba07dfe576e58e0387ee0158624837461f72ade422d521231b40baa7756f`
  and protocol-canonical logical SHA-256
  `238ecacf20016f164e679ee98cc0cf29fe07429ec4bc8ba8f4fd022dbbb12ba6`.
- Accepted canonical analysis:
  `experiments/artifacts/arrhenius-selector-full-p6/analysis-v4.json`
  with raw SHA-256
  `39958f1984d9c33fc2717ef221881751e24dc68434932b6ea9b92e4dd3f2b1c5`.
- The accepted secondary structural diagnostic has raw SHA-256
  `bde07d0d2e279b5f8e06b5e59eb67aa7f513a1fae58f101fa0e87bc01030cc69`.
- Generated paper input:
  `paper/generated/arrhenius-selector-full-v4.tex` with raw SHA-256
  `904e160c5606d09dbb1277e5382b024394277067a59eb1bd7cfc94089f1eba9e`.
- Submitted full-suite array: the exact scheduler job identifier and timestamp
  are retained only in the private audit record. All 9,639 cells have one
  canonical valid final marker, zero wrapper failures, and zero restarts.

The P6 runner requires both P5 revisions above to be Git ancestors of the P6
planner. A scheduled compute-node smoke forced legacy preprocessing to its CPU
limit and verified canonical pre-search outcome 21, with no search process,
metric stream, plan, or stderr, before the P6 launch pins were committed.

## Fail-closed exclusions

Protocol failures trigger whole-grid replacement, never outcome-dependent cell
replacement.

1. Two pre-P4 diagnostic screens exposed an overbroad zero-cost admission gate
   and a durable plan followed by a raw search CPU-limit exit. Neither grid
   contributes a score or performance observation.
2. The first downstream start exposed a missing construction event when a PDB
   proved the initial state dead. Both arrays were canceled; 53 stable held-out
   cells and 20 full-suite completion markers were excluded. The producer was
   corrected prospectively and both grids were rebuilt.
3. The subsequent P5 full start exposed four legacy-preprocessor `SIGXCPU`
   returns surfaced by the shell as 232 among 1,650 completion-marked cells.
   The entire array was canceled. P6 canonicalizes child return `-24` to
   pre-search outcome 21 and reruns all 9,639 cells from scratch.

No completed cell, partial cell, or archived attempt from an excluded grid is
reused. These amendments do not change the selection artifact, matrix,
ranking, contrasts, or statistical analysis.
