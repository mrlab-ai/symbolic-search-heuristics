#ifndef SYMBOLIC_WBH_PDB_LEVELS_H
#define SYMBOLIC_WBH_PDB_LEVELS_H

#include "sym_variables.h"
#include "wbh_add_stats.h"

#include "../task_proxy.h"

#include <map>
#include <vector>

namespace pdbs {
class PatternDatabase;
class Projection;
}

namespace symbolic {
class WbhStats;

/*
  Budget-bounded pattern database level sets.

  Selects variables greedily up to an abstract-state budget B, either from the
  search's BDD variable order (legacy mode) or from Fast Downward's
  goal/causal-graph order. The pattern need not be a prefix: under a
  variable-contiguous bit order, non-pattern variables are skipped by the
  reduced ADD, so any pattern with at most B abstract states has the same
  O(dB) width guarantee.

  Computes the PDB explicitly with Fast Downward's PDB code on the projection,
  then builds level-set BDDs H_d by iterating abstract states and conjoining
  the selected pattern facts. Dead ends (h = infinity abstract states) are
  collected into a separate set that the search discards.

  A total heuristic ADD is built only for the "heuristic" log statistics;
  dead ends use a fresh numeric sentinel terminal distinct from finite values.
*/
class PdbLevelSets {
    SymVariables *vars;

    std::vector<int> pattern; // sorted pattern (FDR variable ids)
    std::map<int, BDD> level_sets; // distance d -> H_d (valid states)
    BDD dead_ends; // states mapping to dead-end abstract states
    AddStats add_stats;

    // Independent check that BDD level-set membership agrees with explicit PDB
    // lookups on sampled abstract states (PR4 acceptance).
    void verify_against_pdb(
        const TaskProxy &task_proxy, const pdbs::PatternDatabase &pdb,
        const pdbs::Projection &projection, int num_samples) const;

public:
    PdbLevelSets(
        SymVariables *vars, const TaskProxy &task_proxy, int state_budget,
        bool goal_directed = false);

    const std::map<int, BDD> &get_level_sets() const {
        return level_sets;
    }

    const BDD &get_dead_ends() const {
        return dead_ends;
    }

    const std::vector<int> &get_pattern() const {
        return pattern;
    }

    void log_heuristic(WbhStats &stats) const;

    long get_width_upper_bound() const {
        return add_stats.width_upper_bound;
    }
};
}

#endif
