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

## Smoke-suite deviation from the plan

The plan lists `logistics98` (3 tasks), but even `logistics98:prob01` is not
solved by blind symbolic forward search within the 60 s smoke-suite budget
(blind fw is still raising the bound past 20 at t=57 s). We substitute three
small `logistics00` instances (`probLOGISTICS-4-0`, `-4-1`, `-5-0`), which
blind forward solves in well under a second, preserving a logistics domain in
the suite. `openstacks-opt08-strips` uses per-problem domain files
(`pNN-domain.pddl`), handled by `resolve_domain()` in `run_baseline.py`.
