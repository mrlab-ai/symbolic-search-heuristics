#include "symbolic_pdb_search.h"

#include "../sym_state_space_manager.h"
#include "../sym_variables.h"
#include "../wbh_pdb_levels.h"
#include "../wbh_stats.h"

#include "../../plugins/plugin.h"
#include "../../utils/logging.h"
#include "../../utils/timer.h"
#include "../plan_reconstruction/sym_solution_cut.h"
#include "../plan_selection/plan_selector.h"
#include "../searches/heuristic_fw_search.h"

using namespace std;

namespace symbolic {
SymbolicPdbForwardSearch::SymbolicPdbForwardSearch(const plugins::Options &opts)
    : SymbolicSearch(opts), state_budget(opts.get<int>("budget")),
      goal_directed(opts.get<bool>("goal_directed")),
      prune_only(opts.get<bool>("prune_only")),
      batch_f_window(opts.get<int>("batch_f_window")) {
}

void SymbolicPdbForwardSearch::initialize() {
    SymbolicSearch::initialize();
    mgr =
        make_shared<SymStateSpaceManager>(vars.get(), sym_params, search_task);

    TaskProxy search_task_proxy(*search_task);
    utils::Timer construction_timer;
    level_sets =
        make_shared<PdbLevelSets>(
            vars.get(), search_task_proxy, state_budget, goal_directed);
    utils::g_log << "wbh PDB heuristic: pattern_size="
                 << level_sets->get_pattern().size()
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
        prune_only, batch_f_window);
    double construction_time = construction_timer();
    if (sym_params.stats) {
        sym_params.stats->log_construction(
            goal_directed ? "pdb_goal_directed" : "pdb_bdd_order",
            construction_time, state_budget, -1, true);
    }

    auto sym_trs = search_ptr->getStateSpaceShared()->get_transition_relations();
    solution_registry->init(
        vars, search_ptr->getClosedShared(), nullptr, sym_trs, plan_data_base,
        true, simple);

    search = move(search_ptr);
}

void SymbolicPdbForwardSearch::new_solution(const SymSolutionCut &sol) {
    if (!solution_registry->found_all_plans() && sol.get_f() < upper_bound) {
        solution_registry->register_solution(sol);
        upper_bound = sol.get_f();
    }
}

class SymbolicPdbForwardSearchFeature
    : public plugins::TypedFeature<
          SearchAlgorithm, SymbolicPdbForwardSearch> {
public:
    SymbolicPdbForwardSearchFeature() : TypedFeature("sym_fw_pdb") {
        document_title(
            "Symbolic Forward Search with a budget-bounded pattern database "
            "heuristic");
        document_synopsis("");
        symbolic::SymbolicSearch::add_options_to_feature(*this);
        add_option<int>(
            "budget",
            "Abstract-state budget B: variables are selected greedily in the "
            "chosen order while their domain-size product stays <= B.",
            "100000", plugins::Bounds("1", "infinity"));
        add_option<bool>(
            "goal_directed",
            "Choose variables with Fast Downward's goal/causal-graph order "
            "instead of the legacy BDD-order prefix. Arbitrary patterns retain "
            "the same state-budget width bound.",
            "false");
        add_option<bool>(
            "prune_only",
            "Use the heuristic only for pruning (dead ends and, once an "
            "anytime upper bound is known, the g+h >= bound slice); layers "
            "stay whole as in blind search (paper Cor. cor-prune).",
            "false");
        add_option<int>(
            "batch_f_window",
            "Speculatively image fresh (g,h) buckets at the same g and with "
            "f at most batch_f_window above the selected minimum in one BDD "
            "union. Logical A* selection, goal tests, and closing remain in "
            "the legacy order. Requires a consistent heuristic; 0 is exactly "
            "the legacy product-at-evaluation behavior.",
            "0", plugins::Bounds("0", "infinity"));
        this->add_option<shared_ptr<symbolic::PlanSelector>>(
            "plan_selection", "plan selection strategy", "top_k(num_plans=1)");
    }

    virtual shared_ptr<SymbolicPdbForwardSearch> create_component(
        const plugins::Options &options) const override {
        utils::g_log << "Search Algorithm: Symbolic Forward Search with "
                        "budget-bounded pattern database heuristic"
                     << endl;
        return make_shared<SymbolicPdbForwardSearch>(options);
    }
};

static plugins::FeaturePlugin<SymbolicPdbForwardSearchFeature> _plugin;
}
