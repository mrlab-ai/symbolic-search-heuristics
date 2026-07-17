#include "symbolic_bd_prune_search.h"

#include "../sym_state_space_manager.h"
#include "../sym_variables.h"
#include "../wbh_ms_levels.h"
#include "../wbh_pruner.h"
#include "../wbh_stats.h"

#include "../../plugins/plugin.h"
#include "../../utils/logging.h"
#include "../plan_reconstruction/sym_solution_cut.h"
#include "../plan_selection/plan_selector.h"
#include "../searches/bidirectional_search.h"
#include "../searches/uniform_cost_search.h"

using namespace std;

namespace symbolic {
SymbolicBdPruneSearch::SymbolicBdPruneSearch(const plugins::Options &opts)
    : SymbolicSearch(opts), max_states(opts.get<int>("max_states")),
      build_time_limit(opts.get<double>("build_time_limit")),
      defer_build(opts.get<bool>("defer_build")) {
}

void SymbolicBdPruneSearch::initialize() {
    SymbolicSearch::initialize();
    mgr =
        make_shared<SymStateSpaceManager>(vars.get(), sym_params, search_task);

    // Mirror SymbolicUniformCostSearch::initialize for the bidirectional
    // case; pruners are attached eagerly or on the first solution (deferred).
    auto fw_search =
        unique_ptr<UniformCostSearch>(new UniformCostSearch(this, sym_params));
    auto bw_search =
        unique_ptr<UniformCostSearch>(new UniformCostSearch(this, sym_params));
    fw_search_ptr = fw_search.get();
    bw_search_ptr = bw_search.get();
    if (!defer_build) {
        build_and_attach_pruners();
    }

    fw_search->init(mgr, true, bw_search.get());
    bw_search->init(mgr, false, fw_search.get());

    auto sym_trs =
        fw_search->getStateSpaceShared()->get_transition_relations();
    solution_registry->init(
        vars, fw_search->getClosedShared(), bw_search->getClosedShared(),
        sym_trs, plan_data_base, true, simple);

    search = unique_ptr<BidirectionalSearch>(new BidirectionalSearch(
        this, sym_params, move(fw_search), move(bw_search),
        /*alternating=*/false));
}

void SymbolicBdPruneSearch::build_and_attach_pruners() {
    build_attempted = true;
    TaskProxy search_task_proxy(*search_task);
    level_sets = make_shared<MsLevelSets>(
        vars.get(), search_task_proxy, max_states, /*shrink_seed=*/2011,
        /*both_directions=*/true, build_time_limit);
    if (level_sets->construction_timed_out()) {
        // Fall back to blind bidirectional search: the pruning guarantee then
        // holds including its (bounded) setup cost.
        utils::g_log << "wbh bidirectional M&S pruning: construction budget ("
                     << build_time_limit
                     << "s) exceeded; running blind bidirectional search."
                     << endl;
        level_sets = nullptr;
        return;
    }
    utils::g_log << "wbh bidirectional M&S pruning: max_states=" << max_states
                 << ", abstract_states="
                 << level_sets->get_num_abstract_states()
                 << ", fw_values=" << level_sets->get_level_sets().size()
                 << ", bw_values=" << level_sets->get_init_level_sets().size()
                 << endl;
    if (sym_params.stats) {
        level_sets->log_heuristic(*sym_params.stats);
    }
    fw_pruner = make_shared<WbhPruner>(
        this, level_sets->get_level_sets(), level_sets->get_dead_ends());
    bw_pruner = make_shared<WbhPruner>(
        this, level_sets->get_init_level_sets(),
        level_sets->get_init_dead_ends());
    fw_search_ptr->set_wbh_pruner(fw_pruner);
    bw_search_ptr->set_wbh_pruner(bw_pruner);
}

void SymbolicBdPruneSearch::new_solution(const SymSolutionCut &sol) {
    if (!solution_registry->found_all_plans() && sol.get_f() < upper_bound) {
        solution_registry->register_solution(sol);
        upper_bound = sol.get_f();
    }
    // Deferred construction: the upper-bound slice can only prune once a
    // solution exists, so pay the abstraction cost only now, and only if the
    // optimality proof is still open.
    if (defer_build && !build_attempted && lower_bound < upper_bound) {
        build_and_attach_pruners();
    }
}

class SymbolicBdPruneSearchFeature
    : public plugins::TypedFeature<SearchAlgorithm, SymbolicBdPruneSearch> {
public:
    SymbolicBdPruneSearchFeature() : TypedFeature("sym_bd_ms") {
        document_title(
            "Symbolic Bidirectional Search with width-bounded "
            "merge-and-shrink pruning (width-bounded heuristics)");
        document_synopsis("");
        symbolic::SymbolicSearch::add_options_to_feature(*this);
        add_option<int>(
            "max_states",
            "Shrink size limit N (the width knob) of the linear "
            "merge-and-shrink abstraction used for pruning both directions. "
            "max_states=1 reduces to blind bidirectional search.",
            "10000", plugins::Bounds("1", "infinity"));
        add_option<bool>(
            "defer_build",
            "Construct the abstraction only when the first solution is found "
            "(the bound slice cannot prune earlier), so the search is exactly "
            "blind bidirectional search until then.",
            "true");
        add_option<double>(
            "build_time_limit",
            "Time budget (seconds) for constructing the abstraction and its "
            "level-set BDDs; on breach the search falls back to blind "
            "bidirectional search, so pruning is safe including its setup "
            "cost.",
            "60.0", plugins::Bounds("0.0", "infinity"));
        this->add_option<shared_ptr<symbolic::PlanSelector>>(
            "plan_selection", "plan selection strategy", "top_k(num_plans=1)");
    }

    virtual shared_ptr<SymbolicBdPruneSearch> create_component(
        const plugins::Options &options) const override {
        utils::g_log << "Search Algorithm: Symbolic Bidirectional Search "
                        "with width-bounded merge-and-shrink pruning"
                     << endl;
        return make_shared<SymbolicBdPruneSearch>(options);
    }
};

static plugins::FeaturePlugin<SymbolicBdPruneSearchFeature> _plugin;
}
