# Design note: auxiliary-state-variable heuristic search (DEFERRED)

PR3 implements the **product-at-evaluation** variant of heuristic symbolic
forward search (`sym_fw_pot`, `HeuristicFwSearch`): after each image the
successor set is intersected with the precomputed level-set BDDs `H_v` to form
the `(g, v)` buckets. This note records the deferred alternative for a possible
follow-up; **no code implements it yet**.

## The GHSETA*-style variant (deferred)

Instead of intersecting with level sets at evaluation time, fold the change of
heuristic value into the transition relations, GHSETA*-style
(Jensen et al., AIJ 2008; Fišer et al., AIJ 2024):

- Track the partial potential sum in `ceil(log W)` extra BDD variables inside
  the transition relations, where `W` is the heuristic width. Each operator's
  transition relation is annotated with its operator potential `Q(o)` (an
  integer by PR2's MIP), so applying an operator updates the auxiliary "current
  h-value" variables by `Q(o)` symbolically.
- The open list is then keyed by `g` alone over the augmented state space; the
  `h`-value is read off the auxiliary variables rather than recomputed by
  intersection.

## Why it is deferred

- Product-at-evaluation already satisfies the PR3 acceptance criteria
  (blind-equivalence at `m=0`, optimal costs, no `g+h>C` expansions, bounded
  fragmentation) and directly exposes the level sets `H_v` needed for the
  fragmentation measurements of Q1.
- The auxiliary-variable encoding requires modifying the transition-relation
  construction (`sym_transition_relations`, `transition_relations/`) to carry
  the `ceil(log W)` extra variables and the per-operator `Q(o)` increments,
  which is a substantially larger and riskier change.
- The paper's effort accounting (Def. def-effort) and the search-effort theorem
  are stated for BDDA*, which product-at-evaluation implements directly; the
  paper notes (Sec. "Search-Effort Guarantees") that GHSETA* expands the same
  state sets, so the measured effort would coincide.

If implemented later, reuse PR2's integer operator potentials `Q(o)` (derivable
from the fact-potential table via AIJ 2024 Eq. 4) and add the auxiliary
variables to `SymVariables` behind a flag, keeping the level-set path as the
default and the blind-equivalence baseline.
