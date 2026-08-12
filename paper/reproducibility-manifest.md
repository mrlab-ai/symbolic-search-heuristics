# Reproducibility manifest

This manifest contains the exact identities intentionally omitted from the
main narrative. It is part of the anonymous artifact. Each SHA-256 value is a
lowercase hexadecimal digest of the byte sequence named by its entry: JSON
artifacts explicitly say “raw,” while task, source-record, and matrix entries
refer to their protocol-defined normalized or canonical streams.

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
- Fail-closed Stage-3 paper-data and TeX renderer:
  `experiments/render_arrhenius_selector_full_paper.py`

The screen analyzer has separate canonical selection and descriptive-report
modes. The full renderer accepts only the pinned canonical analysis artifact
and SHA-256 sidecar; its production pins remain unset until that artifact is
accepted.

## Common benchmark identity

- Benchmark repository revision:
  `48d6a00d482de2384a9e751f9343df58bf5582be`
- Benchmark origin: `https://github.com/aibasel/downward-benchmarks`
- Every selected PDDL source is byte-attested before grid construction.
- Every run receives independent, read-only, single-link copies of its domain
  and problem files; the launch gate rechecks their content hashes.

## Stage 1: P4 screen

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
- Selection artifact:
  `experiments/artifacts/arrhenius-selector-screen-p4/selection-v3.json`
  with raw SHA-256
  `d35a1df68eebbd099fe81f86e6e0f6a96ce770572574f9ae013ab4eb0b2c8eb2`
- Certified descriptive report:
  `experiments/artifacts/arrhenius-selector-screen-p4/certified-report-v2.json`
  with raw SHA-256
  `e75daadefc6cf3cad3121ffb28959659dbc78523970945d575a97b18a319252c`
- Experiment protocol: `arrhenius-exact-width-selector-screening-v2`
- Selector pool: `fixed_pool_v1`
- Candidate score:
  `init_dead_init_h_mean_dead_fraction_width_states_pattern_v1`
- Whole-trace parser:
  `run.log/pdb-final-and-width-selector-v1-whole-trace/v3`
- Metric validation: `wbh-exact-schema-semantic-v3`
- Outcome certification:
  `direct-search-raw-effective-plan-reconciliation/v1`

## Stage 2: P5 held-out run

- Planner revision: `165b6d2ee29d5d7b6e1bf4c52540c393ba19b54f`
- Stripped planner binary:
  `af2a19d236ecad9b747d2a1b9c49da73d98248c38d21cc60ad0ac7613d74bdbe`
- Copied preprocessor:
  `1b351a4a5f9380bf41fe9fd61b98c816505ebd8cf88b20afa0d81a9bfb2474bd`
- Launch-protocol revision:
  `a52488637a1c054b26dac93fe2eb1a556110a2dd`
- Execution protocol: `arrhenius-selector-heldout-validation-v3`
- Initial-dead construction protocol:
  `pdb-ms-initial-dead-bdd-construction-prelog/v1`
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
- Execution protocol: `arrhenius-selector-full-population-v4`
- Analysis schema:
  `symbolic-search-heuristics/full-population-analysis/v4`
- Analysis protocol: `full-supported-population-census-v1`
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
- Arrhenius array: job `1203277`, submitted 2026-08-12 09:56 CEST; final
  census acceptance is pending.
- Final analysis artifact and rendered-paper hashes: pending acceptance of the
  complete P6 census.

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
