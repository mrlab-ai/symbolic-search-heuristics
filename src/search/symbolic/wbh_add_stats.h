#ifndef SYMBOLIC_WBH_ADD_STATS_H
#define SYMBOLIC_WBH_ADD_STATS_H

#include "sym_variables.h"

#include <vector>

namespace symbolic {
class WbhStats;

/*
  Statistics of the reduced ADD of a heuristic over the search variable order,
  shared by the width-bounded heuristic families (potentials, prefix PDBs).
  Fields correspond to the PR1 "heuristic" log event; the width upper bound is
  U = A + V (paper Prop. prop-add), with A the ADD inner-node count and V the
  number of distinct finite values.
*/
struct AddStats {
    long add_inner_nodes = 0;
    int num_values = 0;
    std::vector<long> add_level_nodes;
    long width_upper_bound = 0;
};

// Single DFS over the ADD, counting inner nodes per CUDD level.
AddStats compute_add_stats(SymVariables *vars, const ADD &add, int num_values);

void log_heuristic_stats(WbhStats &stats, const AddStats &add_stats);
}

#endif
