# Results

Per-question findings for the width-bounded-heuristics experiments. Populate
after the full sweeps (links to the `report.html` under
`experiments/data/exp_qN-eval/`).

## Status

Full sweeps launched and parsed on Tetralith (Xeon Gold 6130, 30 min / 8 GiB):
`exp_q1` (potentials m=8, prefix PDB), `exp_q2` (potential M-knob), `exp_ms`
(linear M&S), `exp_baselines` (CPDDL I/I, CPDDL blind bidirectional,
Scorpion), `exp_blind_bd` (sym_bd, parsed). Use `postprocess.py` for the
fair supported subset (1377 of 1697 tasks). The frozen translator-attested
manifest is authoritative: 1684 direct SAS v3 scans and 13 pinned-translator
no-metric/unit-cost proofs classify 1407 positive-cost and 290 zero-cost tasks.
Pinned default normalization separately identifies 30 positive-cost
`pathways` tasks with normalized axioms, leaving 1377 positive-cost,
normalized-axiom-free tasks. Legacy `run.err` files are not present in the
evaluation tarballs.

**Coverage (supported positive-cost, axiom-free subset, 1377 tasks;
`combined_coverage.py`):**
blind_fw 682 · potentials(M=8) 622 · prefix PDB 685 · **linear M&S 704** ·
prune-only pot/pdb/ms 683/682/681 (close to blind, as expected from their
semantic layer order, but not a direct validation of the effort bound) ·
blind_bd 777 · bd_ms deferred 1046 / budgeted 1041 / eager 1032 vs 1051
full-suite (three designs, consistent small negative -- honest verdict in
paper) · CPDDL I/I 652 · CPDDL blind bidirectional stand-in 724 · Scorpion 912.
Per-domain breakdown in `coverage_per_domain.csv`. Prefix PDB and linear M&S
match or beat blind forward (the theory's baseline), while the archived
potential configuration does not; all three exceed or nearly match the
executed CPDDL I/I configuration. The configurations solving more (blind
bidirectional, the CPDDL blind bidirectional stand-in, and Scorpion) use search
paradigms outside the forward-search scope of Thm. thm-effort (bidirectional or
explicit). The archived identifiers `a_plus_i` and `symba_star` are legacy
aliases for CPDDL I/I and the CPDDL blind bidirectional stand-in, respectively;
they are not measurements of A+I or the original SymBA*. Baseline numbers
reflect the fixed domain-file resolution (`build_suite`); the earlier
551/619/803 counts understated CPDDL I/I / CPDDL blind bidirectional / Scorpion
by about 100 each due to a resolver bug on airport and other domains.

**Q1 fragmentation:** median legacy successor-batch DagSize ratio 1.17 (PDB) /
1.29 (pot) / 1.31 (M&S), max < 2.7. These are descriptive completed-run
diagnostics, not inner-node complete-layer measurements or a direct test of
the Thm-partition bound.

**Q2 knob:** M=0 legacy completed-run DagSize ratio 1.006 (semantically blind,
but not necessarily the same BDD-piece schedule); the observed ratio falls
from 1.9 toward 1.3 as M grows. M=16 has the largest observed coverage, 623,
versus 622 for M=8. With one run per task there is no unique empirical winner;
`WINNING_M=8` records the historical selected configuration, not an
established optimum.

**Bound seeding (exp_seeded, lama-first 60s -> bound=c, optimality-proved
coverage, equal budgets):** seeded blind_bd **1054** > blind_bd 1050 (the seed
helps blind itself: no solution finding/reconstruction needed -- best bd
number of the project, with NO heuristic); seeded bd_ms 1051 (wash; trails its
own control -- construction eats the pruning gain); seeded fw pot prune 688 >
blind_fw 682 / unseeded 683 (forward pruning arc completes positively).

**Merge-order alignment (exp_ms_aligned):** ms_aligned 687 vs ms 704
(5 wins/22 losses); the legacy ADD-derived diagnostic drops (median
1380->1091, p90 50059->9751), but it omitted the corrected total-ADD terminal
count and is not exact cofactor width. The result therefore suggests, rather
than proves, that the causal-graph merge order trades compactness for a more
useful abstraction.

All sweep summaries are based on one run per task. Runtime differences and
one-task coverage gaps are screening evidence, not replicated significance
claims. Ratios over legacy archives are conditional on completed runs; killed
or partial runs are censored unless a metric was emitted before termination.

The paper's experiment section (`paper/paper.tex`, Sec. Experiments) is filled
from these numbers (Tables tab-coverage, tab-knob).

## Per-question findings (final)

**Q1 -- fragmentation.** Across all solved tasks and all three families the
median legacy successor-batch DagSize ratio is 1.17 (prefix PDB), 1.29
(potentials, M=8) and 1.31 (linear M&S), never exceeding 2.7 among completed
runs. This archived metric sums BDD-piece DagSizes and includes constants; a
positive-cost blind layer may remain split into multiple pieces. It is not the
inner-node size of the complete unioned layer used by the theorem. The
`misc/gen_pin.py` generator remains available for the Pi_n family, but the
evaluation archives do not support the previously quoted precise node counts.
Reports: `data/exp_q1-eval/report.html`, `data/exp_ms-eval/report.html`.

**Q2/Q4 -- width knob.** M in {0,1,2,4,8,16,inf}: coverage 680/601/602/608/622/
623/596; conditional geometric-mean legacy DagSize ratio over blind forward
1.01/1.92/1.62/1.45/1.33/1.33/1.28. M=0 is semantically blind (ratio 1.006),
without guaranteeing an identical BDD-piece schedule. M=16 has the largest
observed coverage by one task (623 versus 622 for M=8); without repetitions
this does not establish a unique optimum. `WINNING_M=8` is the historical
selected smaller finite cap, not a statistically established winner. Report:
`data/exp_q2-eval/report.html`.

**Q3 -- main comparison (supported positive-cost, axiom-free subset, 1377
tasks).**
blind_fw 682, blind_bd 777, potentials(M=8) 622, prefix PDB 685, linear M&S 704;
CPDDL I/I 652, CPDDL blind bidirectional stand-in 724, Scorpion 912. The archive
aliases `a_plus_i` and `symba_star` refer to those two CPDDL configurations;
they do not establish results for A+I or the original SymBA*. Per-domain:
`coverage_per_domain.csv` (`combined_coverage.py`). Prefix PDB and linear M&S
match or beat blind forward, whereas the archived potential configuration
does not; all three exceed or nearly match CPDDL I/I. Blind bidirectional, the
CPDDL stand-in, and Scorpion (all bidirectional or explicit) solve more,
outside the forward-search scope of Thm. thm-effort. Reports:
`data/exp_baselines-eval/report.html`, `data/exp_blind_bd-eval/report.html`.

## Definition of done

- Hardware: Intel Xeon Gold 6130 @ 2.1 GHz (Tetralith), 30 min / 8 GiB per run.
- Tables/CSVs: `coverage_per_domain.csv`; per-experiment `*-eval/properties`.
- Task support split: frozen translator-attested manifest (1684 direct SAS
  scans, 13 no-metric/unit-cost proofs) plus exact default-normalization axiom
  counts, with generator revision, proof/normalization-source hashes, and suite
  digest recorded alongside the artifact.
- Paper: `paper/paper.tex` Experiments section filled (Tables tab-coverage,
  tab-knob); bibliography via aibasel/bib (`cd paper && make update-bib`).
- Zenodo-ready snapshot: `git archive --format=tar.gz -o wbh-code.tgz HEAD`
  for the code; add the `experiments/data/*-eval/properties` and
  `results/coverage_per_domain.csv` for the data; upload and insert the DOI
  into the paper footnote. (Not published here -- needs the author's account.)
