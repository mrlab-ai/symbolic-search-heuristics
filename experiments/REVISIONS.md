# Revisions

All width-bounded-heuristics work branches from the SymK commit below.

- **Base commit:** `4e000d8a0193fcee7dd66892a23e5431d0af48a7` (2026-05-28)
- **Branch:** `bounded-heuristics`
- **Build:** `./build.py` (release, LP enabled via CPLEX 22.11 at
  `~/lib/cplex`; SoPlex not found — CPLEX is the LP backend).
- **Benchmarks:** `DOWNWARD_BENCHMARKS=~/projects/benchmarks`
  (aibasel/downward-benchmarks).

## Baseline configs

- `sym_fw()` — blind symbolic forward (uniform-cost) search.
- `sym_bd()` — blind symbolic bidirectional search (default strong config).

Note: the implementation-plan document refers to these as `sym-fw()` /
`sym-bd()`; the actual plugin feature names use underscores (`sym_fw`,
`sym_bw`, `sym_bd`).

Baseline costs and times recorded in `baseline.json` (see
`run_baseline.py`).

## Archived sweep revisions

The evaluation archives are immutable snapshots, and current experiment
scripts may have evolved since they were produced. Read revision and limits
from Lab properties rather than from the working copy:

- `exp_q1-eval.tar.gz`, `exp_q2-eval.tar.gz`:
  `0d3fd43e9d88a0a802e1fdc2770070c18d6e7ffe`, 1800 s, 8192 MiB.
- `exp_ms-eval.tar.gz`:
  `8bfdc4f1546ea7682bdd9e296c8481e122691e51`, 1800 s, 8192 MiB.
- `exp_blind_bd-eval.tar.gz`:
  `474e8886873fb4ecddf064937d97962b2aa27f47`, 1800 s, 8192 MiB.
- The original 50-task M&S cap pilot pins
  `ec8399257de93e0739046a187af4bed0b85e19ce`, 300 s, 8192 MiB. The
  schema-v2 heuristic-choice screen and held-out cap validation pin
  `c2800d7e65abb61d4b94b08a5487f701ceb41d6b` at the same limits.
  Every prospective Tetralith start array is frozen at five concurrent tasks
  in its `#SBATCH --array` header and records
  `scheduler_array_task_throttle=5`; build and start are staged separately
  after the c280 revision-cache sentinel exists. The runners reject `--all`
  and combined build/start names or numeric aliases. Before SymK build/start,
  they hash-check the empty sentinel (`e3b0c442...`) and cached `downward`
  executable (`774e0f80...`), so a missing cache cannot trigger a login-node
  compilation.
  The original pilot was launched as Tetralith array `54287205`; its 350
  generated static records attest that revision, exact search strings, and
  the 300-second/8192-MiB envelope. They do not contain the prospective
  cost-manifest or PDDL-byte hash fields.
  The prospective 1050-cell heuristic-choice screen additionally fails closed
  on the frozen operator-cost manifest and the actual PDDL bytes for its 50
  tasks. Its analyzer requires those per-run hashes and carries them into the
  selection artifact; the finalist runner revalidates both the screen and
  reserved-set source attestations before any non-template action.
- The prospective, not-yet-launched `exp_cpddl_ghseta.py` baseline uses 300 s
  and 8192 MiB. The value
  `2c7de0ec0e7d1d002a08aead4c5c5bbdcf171b89` is the recorded upstream CPDDL
  commit from vendoring, not a locally recoverable source revision after the
  nested `.git` was removed. Byte-level local provenance is the tracked CPDDL
  tree object `c61b00eecb7c4223f4b5f358f900c5fc4a1c6dec` at anchor revision
  `c2800d7e65abb61d4b94b08a5487f701ceb41d6b`, tree-manifest SHA-256
  `3673059666688e581d3593ec87088c640032d42481be3e6f3e754a1e08bb2be2`,
  ignored `Makefile.config` SHA-256
  `908c2dadd8fed416ee42b12c2dd9d815a93732802e099735c6221de215f78908`,
  generated `pddl/config.h` SHA-256
  `88abd4f6bea7a27b75e3c536b82b56dbd3db67a3c17875dc346488613358b997`,
  executable SHA-256
  `df2dba3e604c10caf17e2ec6b86b7007bbdabc49fc77bbb34745d1ee3f0cd056`,
  and executable-reported version
  `1.5-409658ea3bdf92b21170d66a12fc489311e755e6`. The runner verifies all of
  these before building, then stores copied binary/PDDL resources and input
  hashes in the experiment. These attestations identify the source/config
  inputs and executable separately; they are not a reproducible-build proof.
  Its six configurations over 234 tasks give 1404 runs and three disjoint
  reports (pilot50, cap-v2, and finalist-v1); no pooled report exists. The
  runner verifies each task's canonical source path/PDDL bytes against the
  checksum-validated cost manifest and records both the full source-manifest
  hash and each task manifest's canonical selected-record hash. CPDDL's
  forward-only path omits the bidirectional path's native `DONE` marker, so the audited
  parser records that marker as corroboration and requires cost, exit 0, and
  exact log version for coverage.
  The pre-launch `analyze_cpddl_ghseta.py` contract additionally pins the
  runner SHA-256
  `fd7f0afc88bf73a3819ee15efabea9fefea8ef85d906413cb8389579e673e8a2`,
  and shared `exp_common.py` SHA-256
  `3c8d7004fb5cda229fc78e003ae296ca28f5c0f13f0900633a5cf8902b2298a2`,
  requires the exact 1404-cell static matrix, verifies copied PDDL hashes and
  source attestations against the frozen suite cost manifest, independently
  reconstructs the cap-v2 and finalist-v1 name-only selections, and rejects
  conflicting solved costs. Its primary coverage estimands are paired task-level and
  equally-weighted domain-macro differences, reported independently for all
  three manifests on their supported positive-cost, axiom-free subsets; the
  full frozen set is secondary context where it differs. Six frozen
  contrasts report discordant wins/losses and deterministic 95% domain-cluster
  bootstrap intervals (10,000 fixed-seed percentile replicates). Runtime/PAR2
  is one-run screening only, and no cap-v2/finalist-v1 selection or ranking is
  defined.
- The pre-launch `analyze_cross_planner_finalists.py` contract composes the
  exact SymK finalist and complete 1404-cell CPDDL validators, but reports only
  their 92-task, 46-domain finalist-v1 intersection. It predeclares vendored
  CPDDL
  `cpddl_ghseta_bi_a_plus_i_blind` as the primary external comparator and
  direction-matched `cpddl_ghseta_fw_a_plus_i` as secondary. Every selected
  family role plus `blind_fw`, `ms_exact`, and the pilot-selected cap is
  retained without held-out ranking. The supported positive-cost, axiom-free
  primary result uses paired, equally weighted domain-macro coverage
  differences, fixed-seed 10,000-draw
  domain-cluster percentile intervals, and discordant task wins/losses;
  micro/post-stratified coverage is descriptive and one-run timing/PAR2 is
  screening only. The cross gate requires identical task/source attestations,
  rejects across-planner solved-cost disagreement, and hash-pins the imported
  validator sources, including the heuristic-screen runner used for the
  50-task byte attestation and the shared scheduler-header implementation.
  The reviewed cross-analyzer source SHA-256 is
  `f75e46fbc885c7083f2076dd12338ceb0827b804df73af3de1f75fe70294c578`.
  Pilot50 and cap-v2 records are validated as part of the CPDDL input matrix
  but cannot enter a cross-planner estimate.

The generic `exp_baselines-eval.tar.gz` archive does not contain revision or
limit properties. Its external source provenance is the vendored-commit table
in `baselines/README.md`; this does not replace missing in-archive attestation.
All listed sweeps use one run per algorithm/task, so they provide no
within-configuration repetition estimate.

## Smoke-suite deviation from the plan

The plan lists `logistics98` (3 tasks), but even `logistics98:prob01` is not
solved by blind symbolic forward search within the 60 s smoke-suite budget
(blind fw is still raising the bound past 20 at t=57 s). We substitute three
small `logistics00` instances (`probLOGISTICS-4-0`, `-4-1`, `-5-0`), which
blind forward solves in well under a second, preserving a logistics domain in
the suite. `openstacks-opt08-strips` uses per-problem domain files
(`pNN-domain.pddl`), handled by `resolve_domain()` in `run_baseline.py`.
