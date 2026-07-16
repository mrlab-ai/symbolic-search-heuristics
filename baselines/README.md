# External baselines (vendored)

Comparison planners for the width-bounded-heuristics experiments (Q3/Q4),
vendored as plain directories (no git submodules). Each was cloned from
upstream and its nested `.git` removed; researcher `experiments/` data and
`.github` CI were pruned to keep only what is needed to build and run.

| Dir | Upstream | Vendored commit | Role |
|-----|----------|-----------------|------|
| `cpddl/` | https://gitlab.com/danfis/cpddl.git | `2c7de0ec0e7d1d002a08aead4c5c5bbdcf171b89` | Fišer et al. (AIJ 2024) **A+I operator-potential** symbolic planner (Q3 c) |
| `symba/` | https://gitlab.com/atorralba/fast-downward-symbolic.git (branch `master`) | `1ba05d4d1e55358a0bcc18f3d282efc573e6f86e` | Torralba's symbolic Fast Downward — **SymBA\*** (Q3 d) |
| `scorpion/` | https://github.com/jendrikseipp/scorpion.git | `4fd73aea3cfbb159e3ec9e61a8d2e30fb661916c` | **Scorpion** explicit-search planner (Q4 context) |

Cloned 2026-07-16. Licenses are included in each directory (`LICENSE*`).

## Building

Each baseline has its own build system and dependencies; build them
separately (not via SymK's `build.py`):

- **cpddl**: `cd cpddl && cp Makefile.config.tpl Makefile.config && make`
  (needs an LP solver; see `cpddl/README.md` and `Makefile.config`). Bundles
  CUDD and bliss under `third-party/`. The A+I operator-potential
  configuration is selected via cpddl's planner scripts under `bin/`/`scripts/`.
- **symba**: `cd symba && ./build.py` (old Fast Downward build). The SymBA\*
  configuration is a symbolic bidirectional search with perimeter abstraction
  heuristics; see `symba/driver` / the IPC-2014 plan script.
- **scorpion**: `cd scorpion && ./build.py`. Used coverage-only for Q4.

## Wiring into the experiments

`experiments/exp_q3.py` and `exp_q4.py` currently add the SymK configs and
leave these baselines as documented TODOs. To include them, build the baseline,
then add it in the experiment as a separate algorithm pointing at the built
binary (report the baseline's numbers **from our runs on our suite**, never
from the original papers' tables — pitfall #8). For SymK's own blind
bidirectional baseline use `sym_bd()` (already wired); SymBA\* here is the
distinct abstraction-based planner.
