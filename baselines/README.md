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

Build artifacts are gitignored (see `.gitignore`); only source is tracked.

### cpddl (A+I, and the SymBA\* stand-in) — builds ✓

Needs the bundled CUDD + bliss and an LP solver (CPLEX). Verified steps on
this machine (CPLEX at `~/lib/cplex`):

```
cd cpddl
cp Makefile.config.tpl Makefile.config
cat >> Makefile.config <<'EOF'
IBM_CPLEX_ROOT = /home/x_jense/lib/cplex
USE_CPOPTIMIZER = no
EOF
make cudd bliss     # build bundled third-party/cudd/libcudd.a + bliss (autotools)
make -j              # rebuild libpddl.a with CUDD (defines PDDL_CUDD)
make -C bin          # build bin/pddl-symba etc.
```

`IBM_CPLEX_ROOT` must be the parent of `cplex/`. If `libcudd.a` is missing when
`make` runs, cpddl silently uses `bdd-stub.o` and aborts at run time with
"require the CUDD library" — build `make cudd` first, then remove
`pddl/config.h .objs/bdd.o .objs/sym.o` and rebuild so `PDDL_CUDD` is set.

Verified runs (gripper, optimal cost 11):
- **A+I** (Q3 c): `bin/pddl-symba --symba bi --symba-fw-pot --symba-fw-pot-cfg I --symba-bw-pot --symba-bw-pot-cfg I DOMAIN PROBLEM`
- **SymBA\*** (Q3 d): `bin/pddl-symba --symba bi DOMAIN PROBLEM` (bidirectional
  symbolic search without potentials).

### scorpion (Q4) — builds ✓

```
cd scorpion && ./build.py
```
Run with `./fast-downward.py --alias scorpion DOMAIN PROBLEM`.

### symba = Torralba's original SymBA\* (IPC 2014) — does NOT build here

Old 64-bit Fast Downward. `./build.py release64` avoids the default 32-bit
requirement, but the legacy C++ `preprocess` component fails to link on this
toolchain (gcc 11). Rather than patch the old code, we use **cpddl's** `symba`
(the maintained successor by the same authors) as the SymBA\* baseline (above);
this is documented in `experiments/exp_baselines.py`. The directory is kept for
provenance.

## Wiring into the experiments

The baselines run via `experiments/exp_baselines.py` — a generic Downward Lab
experiment that invokes the **pre-built** binaries directly (vendoring removed
the `.git` dirs, so lab's cached-revision build cannot be used). It defines the
`a_plus_i`, `symba_star` and `scorpion` algorithms with per-run limits
(30 min, 8 GiB) and parses coverage / plan cost. Combine its `properties` with
the SymK-config results from `exp_q3.py` / `exp_q1.py` at report time. Report
baseline numbers **from our runs on our suite**, never from the original
papers' tables (pitfall #8). SymK's own blind bidirectional baseline is
`sym_bd()` (wired in `exp_q3.py`).
