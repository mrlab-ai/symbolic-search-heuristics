#ifndef SYMBOLIC_SEARCH_ALGORITHMS_SYMBOLIC_MS_SEARCH_H
#define SYMBOLIC_SEARCH_ALGORITHMS_SYMBOLIC_MS_SEARCH_H

#include "symbolic_search.h"

#include <memory>

namespace symbolic {
class HeuristicFwSearch;
class MsLevelSets;

/*
  Symbolic forward search guided by a linear merge-and-shrink heuristic (paper
  Prop. prop-ms, third width-bounded family). Builds the M&S level sets
  (MsLevelSets, shrink limit = the width knob N) and runs the shared
  (g, v)-keyed BDDA* HeuristicFwSearch, discarding dead ends.
*/
class SymbolicMsForwardSearch : public SymbolicSearch {
    const int max_states;

    std::shared_ptr<MsLevelSets> level_sets;

protected:
    virtual void initialize() override;

public:
    explicit SymbolicMsForwardSearch(const plugins::Options &opts);

    virtual void new_solution(const SymSolutionCut &sol) override;
};
}

#endif
