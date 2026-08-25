#ifndef SYMBOLIC_WBH_PDB_LEVELS_H
#define SYMBOLIC_WBH_PDB_LEVELS_H

#include "sym_variables.h"
#include "wbh_add_stats.h"

#include "../task_proxy.h"

#include <map>
#include <memory>
#include <string>
#include <vector>

class AbstractTask;

namespace pdbs {
class PatternDatabase;
class Projection;
}

namespace symbolic {
class WbhStats;

enum class PdbPatternSelection {
    LEGACY,
    BDD_PREFIX,
    GOAL_PREFIX,
    GOAL_FILL,
    CEGAR,
    EXACT_WIDTH_FILTER,
};

/*
  Budget-bounded pattern database level sets.

  Selects a pattern up to an abstract-state budget B using a legacy prefix,
  a budget-filling goal/causal order, Fast Downward's CEGAR generator, or an
  exact cofactor-width filter over a fixed deduplicated pool containing all of
  these strategies plus the empty pattern. The pattern need not be a prefix:
  under a variable-contiguous bit order, non-pattern variables are skipped by
  the reduced ADD, so any pattern with at most B abstract states has the same
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
    std::string selection_name;
    std::string selected_source;
    int num_abstract_states = 0;
    int cofactor_width_budget;
    int total_add_node_budget;
    int value_cap;
    bool select_value_cap;
    bool selected_initial_dead_end = false;

    // Independent check that BDD level-set membership agrees with explicit PDB
    // lookups on sampled abstract states (PR4 acceptance).
    void verify_against_pdb(
        const TaskProxy &task_proxy, const pdbs::PatternDatabase &pdb,
        const pdbs::Projection &projection, int num_samples) const;

public:
    PdbLevelSets(
        SymVariables *vars, const std::shared_ptr<AbstractTask> &task,
        int state_budget, PdbPatternSelection pattern_selection,
        bool legacy_goal_directed, double cegar_max_time, int cegar_seed,
        int cofactor_width_budget, int total_add_node_budget, int value_cap,
        bool select_value_cap);

    const std::map<int, BDD> &get_level_sets() const {
        return level_sets;
    }

    const BDD &get_dead_ends() const {
        return dead_ends;
    }

    const std::vector<int> &get_pattern() const {
        return pattern;
    }

    const std::string &get_selection_name() const {
        return selection_name;
    }

    const std::string &get_selected_source() const {
        return selected_source;
    }

    int get_num_abstract_states() const {
        return num_abstract_states;
    }

    int get_cofactor_width_budget() const {
        return cofactor_width_budget;
    }

    int get_total_add_node_budget() const {
        return total_add_node_budget;
    }

    bool uses_total_add_node_budget() const;

    int get_value_cap() const {
        return value_cap;
    }

    bool uses_exact_width_filter() const {
        return selection_name == "exact_width_filter" ||
               selection_name == "exact_width_cap_filter" ||
               selection_name == "exact_add_filter" ||
               selection_name == "exact_add_cap_filter";
    }

    bool selected_initial_is_dead_end() const {
        return selected_initial_dead_end;
    }

    void log_heuristic(WbhStats &stats) const;

    const AddStats &get_add_stats() const {
        return add_stats;
    }

    long get_width_upper_bound() const {
        return add_stats.width_upper_bound;
    }

    long get_cofactor_width() const {
        return add_stats.cofactor_width;
    }
};
}

#endif
