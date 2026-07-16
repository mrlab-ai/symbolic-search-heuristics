#ifndef SYMBOLIC_SYM_PARAMETERS_H
#define SYMBOLIC_SYM_PARAMETERS_H

#include "sym_enums.h"

#include "../abstract_task.h"

#include <algorithm>
#include <memory>

namespace plugins {
class Options;
class Feature;
} // namespace options

namespace symbolic {
class WbhStats;

struct SymParameters {
    ConditionalEffectsTransitionType ce_transition_type;
    int max_tr_size, max_tr_time;

    MutexType mutex_type;
    int max_mutex_size, max_mutex_time;

    int max_aux_nodes,
        max_aux_time; // Time and memory bounds for auxiliary operations

    int max_alloted_time,
        max_alloted_nodes; // max alloted time and nodes to a step
    double ratio_alloted_time,
        ratio_alloted_nodes; // factor to multiply the estimation

    bool non_stop;

    bool print_symbolic_task_size;

    // Width-bounded-heuristics instrumentation logger (PR1). Non-null iff the
    // wbh_log option is a non-empty path. Shared across all copies of this
    // struct so that forward and backward searches write to one file.
    std::shared_ptr<WbhStats> stats;

    SymParameters(
        const plugins::Options &opts,
        const std::shared_ptr<AbstractTask> &task);

    void increase_bound();

    static void add_options_to_feature(plugins::Feature &feature);

    void print_options() const;
};
}

#endif
