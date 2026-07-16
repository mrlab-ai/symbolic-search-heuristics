# SymK Repo Map for Width-Bounded Heuristics

Corrected map of the SymK internals relevant to the width-bounded-heuristics
project. Supersedes the "Assumed SymK layout" in the implementation plan.
All paths are under `src/search/symbolic/` unless noted. Base commit
`4e000d8a0193`.

## Class hierarchy (corrected)

The assumed `SymSearch -> UniformCostSearch -> BidirectionalSearch` chain is
wrong. Actual structure:

- `SymSearch` (abstract base, `searches/sym_search.h:16`): pure-virtual
  `step()`, `stepImage()`, `getF()`, `finished()`. Holds the
  `SymStateSpaceManager` (`mgr`), `SymParameters` (`sym_params`), and the
  driving `SymbolicSearch` engine.
- `UniformCostSearch : SymSearch` (`searches/uniform_cost_search.h:34`):
  single-direction (forward or backward) blind search.
- `BidirectionalSearch : SymSearch` (`searches/bidirectional_search.h:8`):
  owns two `UniformCostSearch` (fw, bw) and alternates; does **not** inherit
  from `UniformCostSearch`.
- `SymbolicSearch : SearchAlgorithm` (`search_algorithms/symbolic_search.h:25`):
  the Fast-Downward-level algorithm that owns and drives the `SymSearch`.

Plugins `sym_fw` / `sym_bw` / `sym_bd` are registered in
`search_algorithms/symbolic_uniform_cost_search.cc:87,109,132`.
(Plan calls them `sym-fw`/`sym-bd`; real feature names use underscores.)

## The forward search loop / one expansion

- Driver: `SymbolicSearch::step()` (`search_algorithms/symbolic_search.cc:72`)
  → `search->step()` (`:133`).
- `UniformCostSearch::step()` (`searches/uniform_cost_search.h:89`) calls
  `stepImage(0,0)`.
- **One expansion = `UniformCostSearch::stepImage(maxTime, maxNodes)`
  (`searches/uniform_cost_search.cc:122`):**
  1. `prepareBucket()` (`:124`, def `:82`) — pop min-g bucket from open list
     (`open_list.pop(frontier)`), `checkFrontierCut` (solution check, `:91`),
     `filterFrontier()` (`:93`), insert popped states into `closed` (`:98`).
  2. `frontier.prepare(...)` (`:129`) — mutex-filter + Or-merge the bucket.
  3. `frontier.expand(...)` (`:142`) — **the image** (successor BDDs).
  4. For each successor bucket (`:148-162`): new cost `g + costDelta`,
     `checkFrontierCut` (`:153`), insert non-empty BDDs into `open_list` (`:158`).
- Init: `UniformCostSearch::init` (`:28`) seeds the frontier with init (fw) /
  goal (bw) at `:37`, inserts into `closed` at `:41`.
- Bidirectional dispatch: `BidirectionalSearch::stepImage`
  (`searches/bidirectional_search.cc:59`) via `selectBestDirection()` (`:27`).

## Image operation (successor BDDs)

- `Frontier::expand` (`frontier.h:103`) → `expand_zero` (`frontier.cc:103`) /
  `expand_cost` (`frontier.cc:125`), calling
  `mgr->zero_image` / `mgr->cost_image`.
- `SymStateSpaceManager::zero_image`/`cost_image`
  (`sym_state_space_manager.cc:64,85`) iterate transition relations grouped by
  cost and call `tr->image(bdd, node_limit)`.
- Relational product:
  `DisjunctiveTransitionRelation::image`
  (`transition_relations/disjunctive_transition_relation.cc:181`):
  `AndAbstract(from, exists_vars, maxNodes)` then `SwapVariables`.
  `ConjunctiveTransitionRelation::image` (`.../conjunctive_transition_relation.cc:468`).
- TR storage: `SymTransitionRelations` (`sym_transition_relations.h:19`):
  `std::map<int, std::vector<TransitionRelationPtr>> transitions` keyed by cost
  (`:31`), accessor `get_transition_relations()` (`:57`).

## Closed-list subtraction

- Delayed, in `UniformCostSearch::filterFrontier()` (`:116`):
  `frontier.filter(!closed->notClosed())` (`:117`).
- `Frontier::filter(BDD)` (`frontier.h:96`): `b *= !bdd` over the bucket.
- `ClosedList::notClosed()` (`closed_list.h:49`) = `!closedTotal`;
  `closedTotal` accumulated in `ClosedList::insert` (`closed_list.cc:37`).
- Cross-direction pruning against the opposite frontier: `checkFrontierCut`
  (`:74`, `bucketBDD *= perfectHeuristic->notClosed()`).

## Frontier / open list

- `Bucket = std::vector<BDD>` (`sym_bucket.h:12`).
- `Frontier` (`frontier.h:42`): staged buckets `Sfilter`, `Smerge`, `Szero`,
  `S`, plus `Simg` (`vector<map<int,Bucket>>`, `:54`); `g_value` (`:56`).
  **Keyed by g only** — h is not known until a cut is found.
- `OpenList` (`open_list.h:14`): `std::map<int, Bucket> open` keyed by **g
  only** (`:15`); `pop` = `open.begin()` (min g); `insert(bdd, g)` appends.

  → For heuristic search (PR3) this blind, g-only open list must be replaced /
  wrapped by a `(g, v)`-keyed structure. See PR3 design note.

## BDD size / minterms / type

- Type: **CUDD C++ `BDD`** from `cuddObj.hh` (via `sym_bucket.h:5-7`). No
  custom `Bdd` typedef; `Bucket = vector<BDD>`.
- Node count: `BDD::nodeCount()` (wraps `Cudd_DagSize`, counts constant nodes —
  see pitfall #1). Helper `nodeCount(const Bucket&)` (`sym_bucket.cc:22`).
- Minterms: `BDD::CountMinterm(nvars)`; used in `SymVariables::numStates`
  (`sym_variables.cc:171`, over `numPrimaryBDDVars`).
- Manager node count: `manager->ReadNodeCount()` via
  `SymVariables::forest_node_count()` (`sym_variables.h:221`).

## FDR variable -> BDD variable block mapping

- Built in `SymVariables::init(const vector<int>&)` (`sym_variables.cc:55`):
  per FDR var, `var_len = ceil(log2(|D_v|))` (`:67`); for each bit push an
  **unprimed** index into `bdd_index_pre[var]` and a **primed** index into
  `bdd_index_eff[var]`, interleaved (`_numBDDVars`, `_numBDDVars+1`, then
  `+= 2`, `:73-77`). So **unprimed = even CUDD indices, primed = odd**,
  interleaved.
- Maps: `bdd_index_pre`, `bdd_index_eff` (`sym_variables.h:67`); accessors
  `vars_index_pre(v)` (`:115`) / `vars_index_eff(v)` (`:119`).
- Variable vectors filled `sym_variables.cc:98-106` (even→`pre_variables`,
  odd→`eff_variables`); getters `sym_variables.h:96-106`.
- FDR order: `var_order` (`sym_variables.h:66`), computed in `init`
  (`sym_variables.cc:35`) as identity or via
  `InfluenceGraph::compute_gamer_ordering` (`opt_order.cc`).
- Level vs index: with static order, **CUDD index == level**. For the
  permutation use `Cudd_ReadPerm` on `manager->getManager()`. See the
  contiguity assertion `assert_variable_contiguity()` (`sym_variables.cc`).

## Dynamic reordering (OFF by default)

- Member `dynamic_reordering` (`sym_variables.h:50`), option default `"false"`
  (`sym_variables.cc:377`). Only when true is
  `manager->AutodynEnable(CUDD_REORDER_GROUP_SIFT)` called (`:154`).

## Mutex / invariant pruning

- `SymParameters::mutex_type` (`sym_parameters.h:19`), enum
  `MutexType {MUTEX_NOT, MUTEX_AND, MUTEX_EDELETION}` (`sym_enums.h:9`).
  Default `MUTEX_EDELETION` (`sym_parameters.cc:83`). **Disable with
  `mutex_type=MUTEX_NOT`.** Auto-downgrade to `MUTEX_AND` for
  conditional-effects/axioms (`sym_parameters.cc:29`).

## Goal detection / termination / plan reconstruction

- No single goal test; detection via frontier/closed **cuts**:
  `UniformCostSearch::checkFrontierCut` (`:63`) →
  `perfectHeuristic->getCheapestCut(bucketBDD, g, fw)` (`:69`);
  valid cut → `engine->new_solution(sol)` (`:71`). Called on popped buckets
  (`:91`) and on generated successors (`:153`).
- `perfectHeuristic` = opposite direction's closed list (bd) / goal-seeded
  closed list (fw), set in `init` (`:44`).
- Cut computation: `ClosedList::getCheapestCut` (`closed_list.cc:61`).
- Termination: `SymbolicSearch::solved()` = `lower_bound >= upper_bound`
  (`symbolic_search.h:70`); checked at `symbolic_search.cc:86`.
- Plan reconstruction decoupled:
  `SymSolutionRegistry::construct_cheaper_solutions`
  (`plan_reconstruction/sym_solution_registry.cc:272`).

## Where to add project code

- **`--wbh-log` flag & instrumentation (PR1):** add option in
  `SymbolicSearch::add_options_to_feature` (`symbolic_search.cc:166-179`) so
  all `sym_*` variants inherit it; thread through `SymParameters`
  (`sym_parameters.{h,cc}`). Emit events from `stepImage`
  (`uniform_cost_search.cc:122`).
- **Potentials (PR2):** reuse `src/search/potentials/` (LP present, CPLEX
  backend). `PotentialOptimizer` (`potentials/potential_optimizer.h`) already
  has `max_potential` (= our box-constraint knob M) and both objectives
  (`optimize_for_state`, `optimize_for_all_states`).
  `PotentialFunction` holds a `fact_potentials[var][value]` double table.
- **Heuristic search (PR3):** wrap the g-only `OpenList` with a `(g, v)` map;
  build level-set BDDs `H_v` and intersect successors in `stepImage`.
