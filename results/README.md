# Results

Per-question findings for the width-bounded-heuristics experiments. Populate
after the full sweeps (links to the `report.html` under
`experiments/data/exp_qN-eval/`).

## Status

- Infrastructure (PR5) built and dry-run-validated locally on Gripper +
  Miconic (`exp_q1.py`): run, parse, and HTML report with all attributes
  (coverage, solution_cost, total_time, effort, peak_bdd_nodes,
  frag_ratio_max, frag_ratio_geomean, width_upper_bound, num_values,
  add_nodes, num_pruned_deadends).
- Full sweeps: **not yet launched** (await sign-off; Tetralith).

## Q1 -- fragmentation validation

TODO: scatter `frag_ratio_geomean` vs `width_upper_bound` for capped potentials
(m=8) and prefix PDBs; Pi_n anchor. Report HTML: `exp_q1-eval/report.html`.

## Q2 -- width knob

TODO: coverage / geomean effort / expansions vs blind forward for
M in {0,1,2,4,8,16,unbounded}. Freeze the winning M in `experiments/WINNING_M`.

## Q3 -- main comparison

TODO: winning-M vs blind fw, blind bd, Fiser et al. A+I, SymBA*. Per-domain
coverage table. Success criterion: among domains where A+I loses coverage to
blind bidirectional, the capped config recovers >= half while retaining >= 80%
of A+I's aggregate gains elsewhere.

## Q4 -- context

TODO: coverage-only vs Scorpion.

## For the paper's experiment section (definition of done)

Hardware string, Zenodo-ready code snapshot, Tables Q1-Q4 CSVs.
