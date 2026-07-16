#ifndef SYMBOLIC_WBH_POTENTIAL_LEVELS_H
#define SYMBOLIC_WBH_POTENTIAL_LEVELS_H

#include "sym_variables.h"
#include "wbh_add_stats.h"

#include <map>
#include <vector>

namespace symbolic {
class WbhStats;

/*
  Level-set BDDs and ADD statistics for an integer potential heuristic
  (PR3, and the "heuristic" log line deferred from PR2).

  Given the integer fact-potential table P[var][value] (|P| <= M) and the
  search's SymVariables (hence its variable order), this builds

    * the reduced ADD of h(s) = sum_v P(v, s(v)) over the unprimed variables,
      via ADD arithmetic over the per-fact indicator BDDs (invalid bit codes
      contribute 0 per variable, an extension in [-M, M] as allowed by paper
      Remark rem-encoding and Prop. prop-pot), and

    * the level-set BDDs H_v = { s valid : h(s) = v }, obtained by slicing the
      ADD with BddInterval(v, v) and intersecting with the valid states
      (paper's product-at-evaluation input for PR3).

  Potentials may be negative; values are kept signed (no shift), so h(goal)=0
  is preserved and the effort accounting matches paper Def. def-effort
  directly. The (g, v) open list of the search handles negative v.

  It also computes the statistics of the "heuristic" event: ADD inner-node
  count A, number of distinct values V, per-level inner-node counts, and the
  width upper bound U = A + V (paper Prop. prop-add).
*/
class PotentialLevelSets {
    SymVariables *vars;

    ADD h_add;
    std::map<int, BDD> level_sets; // value v -> H_v (valid states only)
    AddStats add_stats;

    void build_add(const std::vector<std::vector<int>> &fact_potentials);
    void build_level_sets();

public:
    PotentialLevelSets(
        SymVariables *vars,
        const std::vector<std::vector<int>> &fact_potentials);

    const std::map<int, BDD> &get_level_sets() const {
        return level_sets;
    }

    // h-value of a single (already valid) state BDD, i.e. the unique v with
    // state subset of H_v. Used for the initial state.
    int value_of_state(const BDD &state) const;

    void log_heuristic(WbhStats &stats) const;

    long get_width_upper_bound() const {
        return add_stats.width_upper_bound;
    }
};
}

#endif
