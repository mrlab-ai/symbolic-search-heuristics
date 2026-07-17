#include "symbolic_ms_search.h"

#include "../sym_state_space_manager.h"
#include "../sym_variables.h"
#include "../wbh_ms_levels.h"
#include "../wbh_stats.h"

#include "../../plugins/plugin.h"
#include "../../utils/logging.h"
#include "../plan_reconstruction/sym_solution_cut.h"
#include "../plan_selection/plan_selector.h"
#include "../searches/heuristic_fw_search.h"

using namespace std;

namespace symbolic {
SymbolicMsForwardSearch::SymbolicMsForwardSearch(const plugins::Options &opts)
    : SymbolicSearch(opts), max_states(opts.get<int>("max_states")),
      prune_only(opts.get<bool>("prune_only")) {
}

void SymbolicMsForwardSearch::initialize() {
    SymbolicSearch::initialize();
    mgr =
        make_shared<SymStateSpaceManager>(vars.get(), sym_params, search_task);

    TaskProxy search_task_proxy(*search_task);
    level_sets = make_shared<MsLevelSets>(
        vars.get(), search_task_proxy, max_states, /*shrink_seed=*/2011);
    utils::g_log << "wbh linear M&S heuristic: max_states=" << max_states
                 << ", abstract_states=" << level_sets->get_num_abstract_states()
                 << ", values=" << level_sets->get_level_sets().size()
                 << ", width_upper_bound=" << level_sets->get_width_upper_bound()
                 << endl;
    if (sym_params.stats) {
        level_sets->log_heuristic(*sym_params.stats);
    }

    auto search_ptr =
        unique_ptr<HeuristicFwSearch>(new HeuristicFwSearch(this, sym_params));
    search_ptr->init(
        mgr, &level_sets->get_level_sets(), level_sets->get_dead_ends(),
        prune_only);

    auto sym_trs = search_ptr->getStateSpaceShared()->get_transition_relations();
    solution_registry->init(
        vars, search_ptr->getClosedShared(), nullptr, sym_trs, plan_data_base,
        true, simple);

    search = move(search_ptr);
}

void SymbolicMsForwardSearch::new_solution(const SymSolutionCut &sol) {
    if (!solution_registry->found_all_plans() && sol.get_f() < upper_bound) {
        solution_registry->register_solution(sol);
        upper_bound = sol.get_f();
    }
}

class SymbolicMsForwardSearchFeature
    : public plugins::TypedFeature<SearchAlgorithm, SymbolicMsForwardSearch> {
public:
    SymbolicMsForwardSearchFeature() : TypedFeature("sym_fw_ms") {
        document_title(
            "Symbolic Forward Search with a linear merge-and-shrink heuristic "
            "(width-bounded heuristics, Prop. prop-ms)");
        document_synopsis("");
        symbolic::SymbolicSearch::add_options_to_feature(*this);
        add_option<int>(
            "max_states",
            "Shrink size limit N (the width knob): intermediate abstractions "
            "are shrunk to at most N states.",
            "10000", plugins::Bounds("1", "infinity"));
        add_option<bool>(
            "prune_only",
            "Use the heuristic only for pruning (dead ends and, once an "
            "anytime upper bound is known, the g+h >= bound slice); layers "
            "stay whole as in blind search (paper Cor. cor-prune).",
            "false");
        this->add_option<shared_ptr<symbolic::PlanSelector>>(
            "plan_selection", "plan selection strategy", "top_k(num_plans=1)");
    }

    virtual shared_ptr<SymbolicMsForwardSearch> create_component(
        const plugins::Options &options) const override {
        utils::g_log << "Search Algorithm: Symbolic Forward Search with "
                        "linear merge-and-shrink heuristic"
                     << endl;
        return make_shared<SymbolicMsForwardSearch>(options);
    }
};

static plugins::FeaturePlugin<SymbolicMsForwardSearchFeature> _plugin;
}
