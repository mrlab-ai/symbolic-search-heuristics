# External baselines (vendored)

Comparison planners for the width-bounded-heuristics experiments (Q3/Q4),
vendored as plain directories (no git submodules). Each was cloned from
upstream and its nested `.git` removed; researcher `experiments/` data and
`.github` CI were pruned to keep only what is needed to build and run.

| Dir | Upstream | Vendored commit | Role |
|-----|----------|-----------------|------|
| `cpddl/` | https://gitlab.com/danfis/cpddl.git | `2c7de0ec0e7d1d002a08aead4c5c5bbdcf171b89` | CPDDL symbolic planner; used for the archived **I/I** and blind-bidirectional stand-in configurations |
| `symba/` | https://gitlab.com/atorralba/fast-downward-symbolic.git (branch `master`) | `1ba05d4d1e55358a0bcc18f3d282efc573e6f86e` | Torralba's original SymBA\* source; retained for provenance but not used in the reported runs |
| `scorpion/` | https://github.com/jendrikseipp/scorpion.git | `4fd73aea3cfbb159e3ec9e61a8d2e30fb661916c` | **Scorpion** explicit-search planner (Q4 context) |

Cloned 2026-07-16. Licenses are included in each directory (`LICENSE*`).

## Building

Build artifacts are gitignored (see `.gitignore`); only source is tracked.

### cpddl (I/I potentials and blind stand-in) — builds ✓

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
- **I/I operator potentials**:
  `bin/pddl-symba --symba bi --symba-fw-pot --symba-fw-pot-cfg I --symba-bw-pot --symba-bw-pot-cfg I DOMAIN PROBLEM`.
  Both directions use the `I` objective. This is **not** CPDDL's `A+I`
  configuration (which would pass `A+I` to the `*-pot-cfg` options).
- **CPDDL blind bidirectional stand-in**:
  `bin/pddl-symba --symba bi DOMAIN PROBLEM`. This is a distinct CPDDL run,
  not the original SymBA\* binary.

The binary's `--version` suffix is not CPDDL source provenance in this
vendored layout: CPDDL's Makefile calls `git rev-parse HEAD`, which resolves
to the enclosing SymK repository after the nested `.git` directory is
removed. The commit in the table is therefore an upstream vendoring record,
not a locally recoverable revision. The prospective runner
`experiments/exp_cpddl_ghseta.py` separately hard-pins and verifies the local
tracked CPDDL Git tree object/tree-manifest digest, ignored build-configuration
digests, executable version/SHA-256, and PDDL input SHA-256 values. Lab copies
the exact binary into the built experiment and both PDDL files into each run.
The source/config and executable attestations are independent identifiers, not
a claim that the binary has been reproduced from the pinned tree.

The current forward-only symbolic path does not emit the bidirectional path's
native `DONE: PLAN FOUND` line; this was confirmed against the source and an
end-to-end Gripper smoke run. The audited runner therefore records `DONE` as
corroboration and defines coverage from the signals shared by both modes:
parsed plan cost, command exit code 0, and the exact expected log version. A
present but contradictory `DONE` marker remains an unexplained failure.

### scorpion (Q4) — builds ✓

```
cd scorpion && ./build.py
```
Run with `./fast-downward.py --alias scorpion DOMAIN PROBLEM`.

### symba = Torralba's original SymBA\* (IPC 2014) — does NOT build here

Old 64-bit Fast Downward. `./build.py release64` avoids the default 32-bit
requirement, but the legacy C++ `preprocess` component fails to link on this
toolchain (gcc 11). Rather than patch the old code, the experiment used
CPDDL's blind bidirectional configuration as a stand-in. It must not be
reported as an execution of original SymBA\*. The directory is kept for
provenance.

## Wiring into the experiments

The baselines run via `experiments/exp_baselines.py` — a generic Downward Lab
experiment that invokes the **pre-built** binaries directly (vendoring removed
the `.git` dirs, so lab's cached-revision build cannot be used). New runs use
the accurate labels `cpddl_i_i`, `cpddl_blind_bi`, and `scorpion`, with
per-run limits (30 min, 8 GiB), and parse coverage / plan cost. The archived
properties use the misleading legacy labels `a_plus_i` and `symba_star`;
map them to the first two names without changing the archived data. Combine
the `properties` with
the SymK-config results from `exp_q3.py` / `exp_q1.py` at report time. Report
baseline numbers **from our runs on our suite**, never from the original
papers' tables (pitfall #8). SymK's own blind bidirectional baseline is
`sym_bd()` (wired in `exp_q3.py`).

The archived generic-Lab properties contain neither binary revision nor
resource-limit fields and have one run per task. The commit table and runner
source above are therefore external provenance, not metadata attested by that
archive. Future runs record the contextual upstream-vendoring commit under
`baseline_upstream_vendored_commit`, along with command, limit, and repetition
properties; that commit field is not a local-source or executable attestation.
Unsolved rows are resource-censored; the evaluation archive alone does not
distinguish every failure mode.
