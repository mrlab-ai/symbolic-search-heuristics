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

**Coverage (positive-cost subset, 1377 tasks):** blind_fw 682 · potentials(M=8)
622 · prefix PDB 685 · **linear M&S 704** · A+I 551 · SymBA* 619 · Scorpion 803.
(blind_bd pending sym_bd sweep.)

**Q1 fragmentation:** median frag ratio 1.17 (PDB) / 1.29 (pot) / 1.31 (M&S),
max < 2.7 — small, far below the Thm-partition worst case.

**Q2 knob:** M=0 effort ratio 1.006 (blind-equivalent); overhead a bounded
factor 1.9→1.3 as M grows; best coverage at M=8 (WINNING_M=8).

The paper's experiment section (`paper/paper.tex`, Sec. Experiments) is filled
from these numbers (Tables tab-coverage, tab-knob).

## Q1 -- fragmentation validation

Sweep launched and parsed (`exp_q1-eval/`). Use `postprocess.py` for the fair
comparison: the raw coverage is inflated for blind by zero-cost tasks the
heuristic configs do not support (positive-cost assumption). On the
**positive-cost subset (1377 of 1697 tasks)**:

| config   | coverage (positive-cost) |
|----------|--------------------------|
| pdb      | 685 |
| blind_fw | 681 |
| pot_m8   | 622 |

So the prefix-PDB heuristic search slightly exceeds blind-forward coverage,
and capped potentials trail a little -- a sensible fragmentation-validation
result. Heuristic-config outcomes: 1307 solved, 1245 timeout, 180 oom, 640
zero-cost-unsupported (320 tasks x 2 configs), 22 provably-unsolvable (11 x 2,
the unsolvable mystery instances).

TODO: scatter `frag_ratio_geomean` vs `width_upper_bound` (attributes are in
the properties); Pi_n anchor. Report HTML: `exp_q1-eval/report.html`.

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
