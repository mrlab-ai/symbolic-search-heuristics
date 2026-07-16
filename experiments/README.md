# Width-Bounded Heuristics -- Experiments

Downward Lab experiments for the width-bounded-heuristics paper (PR5).

## Setup

```
uv venv experiments/.venv --python 3.9
uv pip install --python experiments/.venv/bin/python lab
export DOWNWARD_BENCHMARKS=~/projects/benchmarks   # aibasel/downward-benchmarks
```

Experiments build the planner at the current git revision (`bounded-heuristics`)
via Downward Lab's cached-revision mechanism. LP support (CPLEX) must be
available at build time (see `REVISIONS.md`).

## Running

Local dry run (Gripper + Miconic, short limits):

```
WBH_LOCAL=1 experiments/.venv/bin/python experiments/exp_q1.py build start parse fetch report
open experiments/data/exp_q1-eval/report.html
```

Full sweep on Tetralith (from the NSC login node; **do not launch without
sign-off**). Set your allocation first:

```
export WBH_EMAIL=you@liu.se WBH_ACCOUNT=naiss-...   # edit exp_common.get_environment()
experiments/.venv/bin/python experiments/exp_q1.py   # lists steps; run them in order
```

Limits: 30 min, 8 GiB per run (Fiser et al.); shortened to 60 s / 4 GiB when
`WBH_LOCAL=1`.

## Files

- `suite_wbh.py` -- optimal-track STRIPS suite (see delta note below); `SMOKE`
  for dry runs.
- `wbh_parser.py` -- Downward Lab parser for the `wbh.jsonl` instrumentation.
- `exp_common.py` -- shared environment / algorithms / parser / steps.
- `exp_q1.py` .. `exp_q4.py` -- one experiment per research question.
- `../misc/gen_pin.py` -- generates the Speck et al. (2020) Pi_n family
  (`WBH_PIN_DIR` points Q1 at the generated tasks).
- `run_baseline.py`, `check_*.py` -- PR0-PR4 acceptance/smoke scripts (not lab).

## Suite delta note (important for the paper)

Following Speck et al. (2020) and the paper's positive-cost assumption, the
suite excludes conditional effects, axioms, and **zero-cost operators**.
Zero-cost operators occur inside otherwise-included domains (openstacks,
parcprinter, pegsol, tetris, ...), so the heuristic configurations skip such
tasks at run time (the search asserts positive costs). This makes our suite a
**strict subset** of the Fiser et al. (2024) suite -- state this delta when
reporting.

## Mutex pruning (pitfall #3)

For Q1 fragmentation measurements, disable mutex/invariant pruning to match
Speck et al. (add `mutex_type=MUTEX_NOT` to the sym_* configs). For Q2/Q3
coverage runs keep SymK defaults for external validity, and state the
difference in the results README.

## Q2 "unbounded" cap

The integer MIP needs a finite box, so "unbounded" uses a large-but-tractable
cap (`UNBOUNDED_CAP = 10000` in `exp_q2.py`). The heuristic width saturates once
the cap exceeds the LP optimum magnitude (empirically ~m=100 on small tasks),
while the MIP solve time grows with the cap (a 1e6 box makes CPLEX hang even on
Gripper). State this approximation when reporting the "unbounded" column.

## Q3 / Q4 external baselines (TODO before those runs)

- Q3 (c): Fiser et al. (2024) A+I operator-potential planner -- code in the
  cpddl library <https://gitlab.com/danfis/cpddl> (dataset
  <https://gitlab.com/danfis/pddl-data>); build separately and report their
  numbers from our runs on our suite.
- Q3 (d): SymBA* if available in this build.
- Q4: Scorpion (coverage-only).
