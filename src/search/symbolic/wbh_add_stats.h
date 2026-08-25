#ifndef SYMBOLIC_WBH_ADD_STATS_H
#define SYMBOLIC_WBH_ADD_STATS_H

#include "sym_variables.h"

#include <vector>

namespace symbolic {
class WbhStats;

/*
  Statistics of the reduced ADD of a heuristic over the search variable order,
  shared by the width-bounded heuristic families (potentials, PDBs, and
  merge-and-shrink abstractions).
  Fields correspond to the "heuristic" log event. The width upper bound is
  U = A + T (paper Prop. prop-add), with A the ADD inner-node count and T the
  number of terminals in the chosen total extension. num_values separately
  records the finite level sets that can become search buckets.

  cofactor_width is the exact width from paper Def. def-width. It is computed
  by advancing the set of distinct ADD residuals across every CUDD variable
  level, explicitly retaining a residual when the reduced ADD skips a level.
  This is intentionally different from the number of displayed reduced ADD
  nodes at a level. cofactor_counts contains the exact count before reading
  any bit and after each manager level, so its maximum is cofactor_width.
*/
struct AddStats {
    long add_inner_nodes = 0;
    int num_values = 0;
    int num_terminals = 0;
    std::vector<long> add_level_nodes;
    long width_upper_bound = 0;
    long cofactor_width = 0;
    std::vector<long> cofactor_counts;
    double cofactor_seconds = 0;
};

// Traverse the ADD once for node statistics and once level-by-level for the
// exact residual/cofactor frontier.
AddStats compute_add_stats(SymVariables *vars, const ADD &add, int num_values);

// Return the sorted distinct integer terminal values attained by an ADD.
// Used to slice only real levels instead of scanning a potentially huge
// min-to-max integer range.
std::vector<int> collect_integer_leaf_values(const ADD &add);

void log_heuristic_stats(WbhStats &stats, const AddStats &add_stats);
}

#endif
