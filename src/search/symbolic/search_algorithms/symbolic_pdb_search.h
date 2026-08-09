#ifndef SYMBOLIC_SEARCH_ALGORITHMS_SYMBOLIC_PDB_SEARCH_H
#define SYMBOLIC_SEARCH_ALGORITHMS_SYMBOLIC_PDB_SEARCH_H

#include "symbolic_search.h"

#include <memory>

namespace symbolic {
class HeuristicFwSearch;
class PdbLevelSets;
enum class PdbPatternSelection;

/*
  Symbolic forward search guided by a budget-bounded pattern database.
  Builds the PDB level sets (PdbLevelSets), then runs the (g, v)-keyed BDDA*
  HeuristicFwSearch (shared with the other heuristic families), discarding
  dead-end abstract states.
*/
class SymbolicPdbForwardSearch : public SymbolicSearch {
    const int state_budget;
    const bool goal_directed;
    const PdbPatternSelection pattern_selection;
    const double cegar_max_time;
    const int cegar_seed;
    const int cofactor_width_budget;
    const bool dynamic_reordering;
    const bool prune_only;
    const int batch_f_window;

    std::shared_ptr<PdbLevelSets> level_sets;

protected:
    virtual void initialize() override;

public:
    explicit SymbolicPdbForwardSearch(const plugins::Options &opts);

    virtual void new_solution(const SymSolutionCut &sol) override;
};
}

#endif
