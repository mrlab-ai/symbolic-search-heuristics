#include "symbolic_potential_search.h"

#include "../sym_state_space_manager.h"
#include "../sym_variables.h"
#include "../wbh_potential_levels.h"
#include "../wbh_stats.h"

#include "../../potentials/potential_optimizer.h"
#include "../../plugins/plugin.h"
#include "../../utils/system.h"
#include "../plan_reconstruction/sym_solution_cut.h"
#include "../plan_selection/plan_selector.h"
#include "../searches/heuristic_fw_search.h"

#include <cmath>

using namespace std;

namespace symbolic {
SymbolicPotentialForwardSearch::SymbolicPotentialForwardSearch(
    const plugins::Options &opts)
    : SymbolicSearch(opts),
      m(opts.get<int>("m")),
      objective_all_states(opts.get<bool>("all_states_objective")),
      lp_solver_type(opts.get<lp::LPSolverType>("lpsolver")) {
}

void SymbolicPotentialForwardSearch::initialize() {
    SymbolicSearch::initialize();
    mgr =
        make_shared<SymStateSpaceManager>(vars.get(), sym_params, search_task);

    // Compute width-capped integer fact potentials on the (possibly
    // cost-adapted) search task; cost adaptation does not change the variables,
    // so the potentials are consistent with vars' encoding.
    potentials::PotentialOptimizer optimizer(
        search_task, lp_solver_type, static_cast<double>(m),
        /*integer_potentials=*/true);
    TaskProxy search_task_proxy(*search_task);
    if (objective_all_states) {
        optimizer.optimize_for_all_states();
    } else {
        optimizer.optimize_for_state(search_task_proxy.get_initial_state());
    }
    if (!optimizer.has_optimal_solution()) {
        ABORT("No optimal solution for the width-capped potential MIP.");
    }

    const vector<vector<double>> &table = optimizer.get_fact_potentials();
    vector<vector<int>> int_table(table.size());
    for (size_t var = 0; var < table.size(); ++var) {
        int_table[var].reserve(table[var].size());
        for (double p : table[var]) {
            int_table[var].push_back(static_cast<int>(lround(p)));
        }
    }

    level_sets = make_shared<PotentialLevelSets>(vars.get(), int_table);
    utils::g_log << "wbh potential heuristic: m=" << m << ", values="
                 << level_sets->get_level_sets().size()
                 << ", width_upper_bound=" << level_sets->get_width_upper_bound()
                 << endl;
    if (sym_params.stats) {
        level_sets->log_heuristic(*sym_params.stats);
    }

    auto search_ptr =
        unique_ptr<HeuristicFwSearch>(new HeuristicFwSearch(this, sym_params));
    // Potentials never produce infinity, so the dead-end set is empty.
    search_ptr->init(mgr, &level_sets->get_level_sets(), vars->zeroBDD());

    auto sym_trs = search_ptr->getStateSpaceShared()->get_transition_relations();
    solution_registry->init(
        vars, search_ptr->getClosedShared(), nullptr, sym_trs, plan_data_base,
        true, simple);

    search = move(search_ptr);
}

void SymbolicPotentialForwardSearch::new_solution(const SymSolutionCut &sol) {
    if (!solution_registry->found_all_plans() && sol.get_f() < upper_bound) {
        solution_registry->register_solution(sol);
        upper_bound = sol.get_f();
    }
}

class SymbolicPotentialForwardSearchFeature
    : public plugins::TypedFeature<
          SearchAlgorithm, SymbolicPotentialForwardSearch> {
public:
    SymbolicPotentialForwardSearchFeature() : TypedFeature("sym_fw_pot") {
        document_title(
            "Symbolic Forward Search with a width-capped integer potential "
            "heuristic (width-bounded heuristics, PR3)");
        document_synopsis("");
        symbolic::SymbolicSearch::add_options_to_feature(*this);
        add_option<int>(
            "m",
            "Width cap: integer potentials with |P(v,w)| <= m. m=0 reduces to "
            "blind forward search.",
            "8", plugins::Bounds("0", "infinity"));
        add_option<bool>(
            "all_states_objective",
            "Optimize the potentials for the average over all states instead "
            "of the initial state.",
            "false");
        lp::add_lp_solver_option_to_feature(*this);
        this->add_option<shared_ptr<symbolic::PlanSelector>>(
            "plan_selection", "plan selection strategy", "top_k(num_plans=1)");
    }

    virtual shared_ptr<SymbolicPotentialForwardSearch> create_component(
        const plugins::Options &options) const override {
        utils::g_log << "Search Algorithm: Symbolic Forward Search with "
                        "width-capped integer potential heuristic"
                     << endl;
        return make_shared<SymbolicPotentialForwardSearch>(options);
    }
};

static plugins::FeaturePlugin<SymbolicPotentialForwardSearchFeature> _plugin;
}
