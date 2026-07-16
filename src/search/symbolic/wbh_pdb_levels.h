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
  Prefix pattern database level sets (PR4, paper Prop. prop-pdb).

  Selects the pattern greedily as the first FDR variables of the search's
  (Gamer) variable order up to an abstract-state budget B, so the pattern is a
  prefix of the variable order (asserted) and hence width-bounded. Computes the
  PDB explicitly with Fast Downward's PDB code on the projection, then builds
  the level-set BDDs H_d by iterating abstract states and, for each, conjoining
  the pattern facts over its bit block and accumulating per-distance BDDs. Dead
  ends (h = infinity abstract states) are collected into a separate set that
  the search discards.

  The heuristic ADD (sum_d d * H_d) is built only for the "heuristic" log
  statistics; dead ends are excluded from it.
*/
class PdbLevelSets {
    SymVariables *vars;

    std::vector<int> pattern; // sorted pattern (FDR variable ids)
    std::map<int, BDD> level_sets; // distance d -> H_d (valid states)
    BDD dead_ends; // states mapping to dead-end abstract states
    AddStats add_stats;

    void assert_pattern_is_prefix() const;
    // Independent check that BDD level-set membership agrees with explicit PDB
    // lookups on sampled abstract states (PR4 acceptance).
    void verify_against_pdb(
        const TaskProxy &task_proxy, const pdbs::PatternDatabase &pdb,
        const pdbs::Projection &projection, int num_samples) const;

public:
    PdbLevelSets(
        SymVariables *vars, const TaskProxy &task_proxy, int state_budget);

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
