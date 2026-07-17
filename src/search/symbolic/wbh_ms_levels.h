#ifndef SYMBOLIC_WBH_MS_LEVELS_H
#define SYMBOLIC_WBH_MS_LEVELS_H

#include "sym_variables.h"
#include "wbh_add_stats.h"

#include "../task_proxy.h"
#include "../utils/countdown_timer.h"

#include <limits>
#include <map>
#include <vector>

namespace merge_and_shrink {
class MergeAndShrinkRepresentation;
}

namespace symbolic {
class WbhStats;

/*
  Linear merge-and-shrink level sets (paper Prop. prop-ms, third width-bounded
  family). Builds a linear-merge M&S abstraction with shrink size limit N via
  Fast Downward's merge-and-shrink code (pruning disabled so the mapping is
  total), then constructs the level-set BDDs H_d = { states with abstraction
  goal-distance d } by walking the cascading tables of the abstraction
  compositionally: each leaf inverts its value->abstract-state table into a map
  abstract-state -> BDD over that variable, and each merge combines the two
  child maps through the merge table (state pair -> merged state). With a
  linear merge the right child of every merge is a single variable, so a merge
  combines |left| x d pairs, keeping the construction polynomial in N and d.

  Dead-end abstract states (goal distance infinity) go to a separate set the
  search discards. Paper Prop. prop-ms bounds the width by d*N when the merge
  order matches the search variable order; here the merge follows a
  variable-order-finder order, so the measured width_upper_bound is honest but
  not necessarily tight (order alignment is a possible refinement).
*/
class MsLevelSets {
    SymVariables *vars;

    std::map<int, BDD> level_sets; // goal distance d -> H_d (valid states)
    BDD dead_ends;
    // Init-distance level sets for the backward direction of bidirectional
    // search (built only with both_directions): the abstract init distance is
    // an admissible estimate of dist(init, s), so backward search may discard
    // { s : g_bw + init_dist(s) >= upper bound } and the init-unreachable set.
    std::map<int, BDD> init_level_sets;
    BDD init_dead_ends;
    AddStats add_stats;
    int num_abstract_states = 0;

    std::map<int, BDD> build_state_map(
        const merge_and_shrink::MergeAndShrinkRepresentation &rep,
        const utils::CountdownTimer &budget) const;

    bool construction_failed = false;

public:
    // max_time bounds the abstraction + level-set construction (infinity =
    // unbounded); on breach, construction_timed_out() is true and the level
    // sets are unusable (callers fall back to blind search -- the pruning
    // guarantee then holds including its setup cost).
    MsLevelSets(
        SymVariables *vars, const TaskProxy &task_proxy, int max_states,
        int shrink_seed, bool both_directions = false,
        double max_time = std::numeric_limits<double>::infinity());

    bool construction_timed_out() const {
        return construction_failed;
    }

    const std::map<int, BDD> &get_level_sets() const {
        return level_sets;
    }
    const BDD &get_dead_ends() const {
        return dead_ends;
    }
    const std::map<int, BDD> &get_init_level_sets() const {
        return init_level_sets;
    }
    const BDD &get_init_dead_ends() const {
        return init_dead_ends;
    }
    int get_num_abstract_states() const {
        return num_abstract_states;
    }

    void log_heuristic(WbhStats &stats) const;

    long get_width_upper_bound() const {
        return add_stats.width_upper_bound;
    }
};
}

#endif
