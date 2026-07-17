#ifndef SYMBOLIC_SEARCH_ALGORITHMS_SYMBOLIC_BD_PRUNE_SEARCH_H
#define SYMBOLIC_SEARCH_ALGORITHMS_SYMBOLIC_BD_PRUNE_SEARCH_H

#include "symbolic_search.h"

#include <memory>

namespace symbolic {
class MsLevelSets;
class WbhPruner;

/*
  Bidirectional blind symbolic search with width-bounded pruning in both
  directions (paper Sec. sec-prune extended bidirectionally). One linear
  merge-and-shrink abstraction provides admissible estimates for both
  directions: goal distances prune the forward frontier, init distances the
  backward frontier (dead ends immediately, the g + h >= upper-bound slice
  once a solution is found). With max_states=1 both heuristics are constant 0
  and the search coincides with blind bidirectional search (sym_bd).
*/
class SymbolicBdPruneSearch : public SymbolicSearch {
    const int max_states;

    std::shared_ptr<MsLevelSets> level_sets;
    std::shared_ptr<WbhPruner> fw_pruner;
    std::shared_ptr<WbhPruner> bw_pruner;

protected:
    virtual void initialize() override;

public:
    explicit SymbolicBdPruneSearch(const plugins::Options &opts);

    virtual void new_solution(const SymSolutionCut &sol) override;
};
}

#endif
