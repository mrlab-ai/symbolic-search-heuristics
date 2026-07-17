#ifndef SYMBOLIC_SEARCH_ALGORITHMS_SYMBOLIC_PDB_SEARCH_H
#define SYMBOLIC_SEARCH_ALGORITHMS_SYMBOLIC_PDB_SEARCH_H

#include "symbolic_search.h"

#include <memory>

namespace symbolic {
class HeuristicFwSearch;
class PdbLevelSets;

/*
  Symbolic forward search guided by a prefix pattern database heuristic (PR4).
  Builds the prefix PDB level sets (PdbLevelSets), then runs the (g, v)-keyed
  BDDA* HeuristicFwSearch (shared with the potential search of PR3), discarding
  dead-end abstract states.
*/
class SymbolicPdbForwardSearch : public SymbolicSearch {
    const int state_budget;
    const bool prune_only;

    std::shared_ptr<PdbLevelSets> level_sets;

protected:
    virtual void initialize() override;

public:
    explicit SymbolicPdbForwardSearch(const plugins::Options &opts);

    virtual void new_solution(const SymSolutionCut &sol) override;
};
}

#endif
