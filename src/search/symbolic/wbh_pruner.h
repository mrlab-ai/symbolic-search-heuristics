#ifndef SYMBOLIC_WBH_PRUNER_H
#define SYMBOLIC_WBH_PRUNER_H

// clang-format off
#include "mtr.h" // required before cuddObj.hh
#include "cuddObj.hh"
// clang-format on

#include <map>
#include <utility>
#include <vector>

namespace symbolic {
class SymbolicSearch;

/*
  Width-bounded pruning hook for blind uniform-cost search (paper Sec.
  sec-prune, Cor. cor-prune). Given the level sets of an admissible heuristic
  for one search direction, prune(states, g) discards the dead ends
  (h = infinity) and, once the engine has an anytime upper bound U, the slice
  { s : g + h(s) >= U }. Applied at expansion time (delayed, like SymK's
  duplicate filtering), which by Lemma lem-slice keeps every expanded layer an
  exact interval slice of the corresponding blind layer.

  Direction-agnostic: for forward search pass goal-distance level sets, for
  backward search init-distance level sets (g is then the cost-to-goal and the
  heuristic estimates dist(init, s)).
*/
class WbhPruner {
    const SymbolicSearch *engine;
    BDD dead_ends;
    // Cumulative slices P_t = union of H_v for v <= t, ascending by value.
    std::vector<std::pair<int, BDD>> cumulative_levels;

public:
    WbhPruner(
        const SymbolicSearch *engine, const std::map<int, BDD> &level_sets,
        const BDD &dead_ends);

    // Returns states minus the dead ends and (if an upper bound exists) the
    // g + h >= bound slice.
    BDD prune(BDD states, int g) const;
};
}

#endif
