# Results

Per-question findings for the width-bounded-heuristics experiments. Populate
after the full sweeps (links to the `report.html` under
`experiments/data/exp_qN-eval/`).

## Status

Full sweeps launched and parsed on Tetralith (Xeon Gold 6130, 30 min / 8 GiB):
`exp_q1` (potentials m=8, prefix PDB), `exp_q2` (potential M-knob), `exp_ms`
(linear M&S), `exp_baselines` (A+I, SymBA*, Scorpion), `exp_blind_bd`
(sym_bd, in progress). Use `postprocess.py` for the fair positive-cost subset
(1377 of 1697 tasks; 320 zero-cost excluded for the heuristic configs).

**Coverage (positive-cost subset, 1377 tasks; `combined_coverage.py`):**
blind_fw 682 · potentials(M=8) 622 · prefix PDB 685 · **linear M&S 704** ·
blind_bd 777 · A+I 652 · SymBA* 724 · Scorpion 912. Per-domain breakdown in
`coverage_per_domain.csv`. The width-bounded forward families match/beat blind
forward (the theory's baseline) and the A+I operator-potential planner; the
configs solving more (blind bidirectional, SymBA*, Scorpion) all use search
paradigms outside the forward-search scope of Thm. thm-effort (bidirectional or
explicit). Baseline numbers reflect the fixed domain-file resolution
(`build_suite`); the earlier A+I 551 / SymBA* 619 / Scorpion 803 understated
them by ~100 each due to a resolver bug on airport etc.

**Q1 fragmentation:** median frag ratio 1.17 (PDB) / 1.29 (pot) / 1.31 (M&S),
max < 2.7 — small, far below the Thm-partition worst case.

**Q2 knob:** M=0 effort ratio 1.006 (blind-equivalent); overhead a bounded
factor 1.9→1.3 as M grows; best coverage at M=8 (WINNING_M=8).

The paper's experiment section (`paper/paper.tex`, Sec. Experiments) is filled
from these numbers (Tables tab-coverage, tab-knob).

## Per-question findings (final)

**Q1 -- fragmentation.** Across all solved tasks and all three families the
median fragmentation ratio is 1.17 (prefix PDB), 1.29 (potentials, M=8) and
1.31 (linear M&S), never exceeding 2.7, though the measured width upper bound
spans five orders of magnitude -- far below the Thm-partition worst case.
Anchor: blind forward keeps the Speck et al. (2020) Pi_n layers linear (max
18/34/50 nodes for n=4/8/12; `misc/gen_pin.py`), while h* there has width 2^n
(Thm-lb). Reports: `data/exp_q1-eval/report.html`, `data/exp_ms-eval/report.html`.

**Q2/Q4 -- width knob.** M in {0,1,2,4,8,16,inf}: coverage 680/601/602/608/622/
623/596; geomean expansion-size ratio over blind forward 1.01/1.92/1.62/1.45/
1.33/1.33/1.28. M=0 reproduces blind (ratio 1.006). Overhead is a small bounded
factor; coverage peaks at M=8 => `WINNING_M`=8. Report: `data/exp_q2-eval/report.html`.

**Q3 -- main comparison (positive-cost subset, 1377 tasks).**
blind_fw 682, blind_bd 777, potentials(M=8) 622, prefix PDB 685, linear M&S 704;
A+I 652, SymBA* 724, Scorpion 912. Per-domain: `coverage_per_domain.csv`
(`combined_coverage.py`). The width-bounded forward families match/beat blind
forward and A+I; blind bidirectional, SymBA* and Scorpion (all bidirectional or
explicit) solve more, outside the forward-search scope of Thm-effort. Reports:
`data/exp_baselines-eval/report.html`, `data/exp_blind_bd-eval/report.html`.

## Definition of done

- Hardware: Intel Xeon Gold 6130 @ 2.1 GHz (Tetralith), 30 min / 8 GiB per run.
- Tables/CSVs: `coverage_per_domain.csv`; per-experiment `*-eval/properties`.
- Paper: `paper/paper.tex` Experiments section filled (Tables tab-coverage,
  tab-knob); bibliography via aibasel/bib (`cd paper && make update-bib`).
- Zenodo-ready snapshot: `git archive --format=tar.gz -o wbh-code.tgz HEAD`
  for the code; add the `experiments/data/*-eval/properties` and
  `results/coverage_per_domain.csv` for the data; upload and insert the DOI
  into the paper footnote. (Not published here -- needs the author's account.)
