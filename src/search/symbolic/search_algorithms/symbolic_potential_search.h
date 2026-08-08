#ifndef SYMBOLIC_SEARCH_ALGORITHMS_SYMBOLIC_POTENTIAL_SEARCH_H
#define SYMBOLIC_SEARCH_ALGORITHMS_SYMBOLIC_POTENTIAL_SEARCH_H

#include "symbolic_search.h"

#include "../../lp/lp_solver.h"

#include <memory>

namespace symbolic {
class HeuristicFwSearch;
class PotentialLevelSets;

/*
  Symbolic forward search guided by a width-capped integer potential heuristic
  (PR3). Computes the integer fact potentials (|P| <= m) with the MIP of Fiser
  et al. (AIJ 2024) via PotentialOptimizer, builds the level-set BDDs and the
  heuristic ADD (PotentialLevelSets, which also emits the "heuristic" log
  event), and runs the (g, v)-keyed BDDA* HeuristicFwSearch. With m=0 it
  reduces to blind forward search.
*/
class SymbolicPotentialForwardSearch : public SymbolicSearch {
    const int m;
    const bool prune_only;
    const int batch_f_window;
    const bool objective_all_states;
    const lp::LPSolverType lp_solver_type;

    std::shared_ptr<PotentialLevelSets> level_sets;

protected:
    virtual void initialize() override;

public:
    explicit SymbolicPotentialForwardSearch(const plugins::Options &opts);

    virtual void new_solution(const SymSolutionCut &sol) override;
};
}

#endif
