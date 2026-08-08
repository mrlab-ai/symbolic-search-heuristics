#include "wbh_pdb_levels.h"

#include "wbh_add_stats.h"
#include "wbh_stats.h"

#include "../pdbs/pattern_database.h"
#include "../pdbs/pattern_database_factory.h"
#include "../pdbs/types.h"
#include "../task_utils/variable_order_finder.h"
#include "../utils/logging.h"
#include "../utils/system.h"

#include <algorithm>
#include <limits>

using namespace std;

namespace symbolic {
PdbLevelSets::PdbLevelSets(
    SymVariables *vars, const TaskProxy &task_proxy, int state_budget,
    bool goal_directed)
    : vars(vars) {
    // Both strategies stop before exceeding the same abstract-state budget.
    // The goal-directed order is Fast Downward's standard GOAL_CG_LEVEL
    // greedy pattern order; the legacy strategy follows the BDD variable order.
    vector<int> variable_order;
    if (goal_directed) {
        variable_order_finder::VariableOrderFinder order(
            task_proxy, variable_order_finder::GOAL_CG_LEVEL);
        while (!order.done()) {
            variable_order.push_back(order.next());
        }
    } else {
        variable_order = vars->get_var_order();
    }

    long product = 1;
    for (int var : variable_order) {
        long domain_size = task_proxy.get_variables()[var].get_domain_size();
        if (product > state_budget / domain_size) {
            break;
        }
        product *= domain_size;
        pattern.push_back(var);
    }
    sort(pattern.begin(), pattern.end());

    utils::g_log << (goal_directed ? "Goal-directed" : "BDD-order")
                 << " PDB pattern (" << pattern.size() << " vars, <= "
                 << state_budget << " abstract states): " << pattern << endl;

    shared_ptr<pdbs::PatternDatabase> pdb =
        pdbs::compute_pdb(task_proxy, pattern);
    pdbs::Projection projection(task_proxy, pattern);
    int num_abstract_states = projection.get_num_abstract_states();
    int num_vars = task_proxy.get_variables().size();

    dead_ends = vars->zeroBDD();
    for (int index = 0; index < num_abstract_states; ++index) {
        // Reconstruct the concrete-state values of the pattern variables and
        // the abstract-state BDD (conjunction over the pattern bit block).
        vector<int> state(num_vars, 0);
        BDD abstract_state = vars->oneBDD();
        for (size_t pos = 0; pos < pattern.size(); ++pos) {
            int var = pattern[pos];
            int value = projection.unrank(index, pos);
            state[var] = value;
            abstract_state *= vars->preBDD(var, value);
        }
        int distance = pdb->get_value(state);
        if (distance == numeric_limits<int>::max()) {
            dead_ends += abstract_state;
        } else {
            auto it = level_sets.find(distance);
            if (it == level_sets.end()) {
                level_sets[distance] = abstract_state;
            } else {
                it->second += abstract_state;
            }
        }
    }

    verify_against_pdb(task_proxy, *pdb, projection, 200);

    // Heuristic ADD for statistics only. The search represents infinity as a
    // separate BDD; use a fresh numeric terminal so the statistics measure an
    // isomorphic total ADD, including dead-end pruning.
    ADD h_add = vars->constant(0);
    for (const auto &[distance, level] : level_sets) {
        h_add += level.Add() * vars->constant(distance);
    }
    if (!dead_ends.IsZero()) {
        vector<int> terminals = collect_integer_leaf_values(h_add);
        double infinity_marker =
            static_cast<double>(terminals.back()) + 1.0;
        h_add =
            dead_ends.Add().Ite(vars->constant(infinity_marker), h_add);
    }
    add_stats = compute_add_stats(
        vars, h_add, static_cast<int>(level_sets.size()));
}

void PdbLevelSets::verify_against_pdb(
    const TaskProxy &task_proxy, const pdbs::PatternDatabase &pdb,
    const pdbs::Projection &projection, int num_samples) const {
    int n = projection.get_num_abstract_states();
    int num_vars = task_proxy.get_variables().size();
    int step = max(1, n / max(1, num_samples));
    int checked = 0;
    for (int index = 0; index < n; index += step) {
        // Concrete witness: pattern variables from unrank, others set to 0.
        vector<int> state(num_vars, 0);
        for (size_t pos = 0; pos < pattern.size(); ++pos) {
            state[pattern[pos]] = projection.unrank(index, pos);
        }
        BDD state_bdd = vars->getStateBDD(state);
        int expected = pdb.get_value(state);
        if (expected == numeric_limits<int>::max()) {
            if (!(state_bdd * !dead_ends).IsZero()) {
                ABORT("PDB self-check: dead-end state not in dead_ends set.");
            }
        } else {
            auto it = level_sets.find(expected);
            if (it == level_sets.end() ||
                !(state_bdd * !it->second).IsZero()) {
                ABORT(
                    "PDB self-check: BDD level-set value disagrees with the "
                    "explicit PDB lookup.");
            }
        }
        ++checked;
    }
    utils::g_log << "PDB level-set self-check passed (" << checked
                 << " sampled abstract states)." << endl;
}

void PdbLevelSets::log_heuristic(WbhStats &stats) const {
    log_heuristic_stats(stats, add_stats);
}
}
