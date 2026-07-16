#include "wbh_ms_levels.h"

#include "wbh_add_stats.h"
#include "wbh_stats.h"

#include "../merge_and_shrink/distances.h"
#include "../merge_and_shrink/factored_transition_system.h"
#include "../merge_and_shrink/merge_and_shrink_algorithm.h"
#include "../merge_and_shrink/merge_and_shrink_representation.h"
#include "../merge_and_shrink/merge_strategy_factory_precomputed.h"
#include "../merge_and_shrink/merge_tree.h"
#include "../merge_and_shrink/merge_tree_factory_linear.h"
#include "../merge_and_shrink/shrink_bisimulation.h"
#include "../merge_and_shrink/types.h"
#include "../task_utils/variable_order_finder.h"
#include "../utils/logging.h"
#include "../utils/system.h"

#include <cmath>
#include <memory>
#include <random>

using namespace std;
namespace ms = merge_and_shrink;

namespace symbolic {
MsLevelSets::MsLevelSets(
    SymVariables *vars, const TaskProxy &task_proxy, int max_states,
    int shrink_seed)
    : vars(vars), dead_ends(vars->zeroBDD()) {
    utils::LogProxy log = utils::get_silent_log();

    // Linear merge over a variable-order-finder order; bisimulation shrink to
    // <= max_states; pruning OFF so the abstraction mapping is total (every
    // concrete state has an abstract state, avoiding PRUNED_STATE handling).
    auto merge_tree = make_shared<ms::MergeTreeFactoryLinear>(
        variable_order_finder::VariableOrderType::LEVEL, shrink_seed,
        ms::UpdateOption::USE_FIRST);
    auto merge_strategy = make_shared<ms::MergeStrategyFactoryPrecomputed>(
        merge_tree, utils::Verbosity::SILENT);
    auto shrink_strategy =
        make_shared<ms::ShrinkBisimulation>(false, ms::AtLimit::RETURN);

    ms::MergeAndShrinkAlgorithm algorithm(
        merge_strategy, shrink_strategy, /*label_reduction=*/nullptr,
        /*prune_unreachable_states=*/false, /*prune_irrelevant_states=*/false,
        /*max_states=*/max_states, /*max_states_before_merge=*/max_states,
        /*threshold_before_merge=*/1,
        /*main_loop_max_time=*/numeric_limits<double>::infinity(),
        utils::Verbosity::SILENT);
    ms::FactoredTransitionSystem fts =
        algorithm.build_factored_transition_system(task_proxy);

    // After a full linear merge there is a single active factor.
    int factor = -1;
    for (int index : fts) {
        factor = index;
        break;
    }
    if (factor == -1) {
        ABORT("Merge-and-shrink produced no active factor.");
    }
    auto [representation, distances] = fts.extract_factor(factor);
    if (!distances->are_goal_distances_computed()) {
        distances->compute_distances(false, true, log);
    }

    // Build abstract-state-id -> BDD over the cascading tables, then group by
    // goal distance into level sets (dead ends: goal distance infinity).
    map<int, BDD> state_map = build_state_map(*representation);
    num_abstract_states = static_cast<int>(state_map.size());
    for (const auto &[abstract_id, bdd] : state_map) {
        int d = distances->get_goal_distance(abstract_id);
        if (d == ms::INF) {
            dead_ends += bdd;
        } else {
            auto it = level_sets.find(d);
            if (it == level_sets.end()) {
                level_sets[d] = bdd;
            } else {
                it->second += bdd;
            }
        }
    }

    // Self-check: sampled concrete states have BDD level-set membership equal
    // to the explicit abstraction lookup (representation in abstract-id mode +
    // goal distances).
    mt19937 rng(shrink_seed);
    VariablesProxy variables = task_proxy.get_variables();
    int num_samples = 200;
    int checked = 0;
    for (int s = 0; s < num_samples; ++s) {
        vector<int> values;
        values.reserve(variables.size());
        for (VariableProxy var : variables) {
            values.push_back(rng() % var.get_domain_size());
        }
        State state = task_proxy.create_state(vector<int>(values));
        int abstract_id = representation->get_value(state);
        int d = distances->get_goal_distance(abstract_id);
        BDD state_bdd = vars->getStateBDD(values);
        if (d == ms::INF) {
            if (!(state_bdd * !dead_ends).IsZero()) {
                ABORT("M&S self-check: dead-end state not in dead_ends set.");
            }
        } else {
            auto it = level_sets.find(d);
            if (it == level_sets.end() ||
                !(state_bdd * !it->second).IsZero()) {
                ABORT(
                    "M&S self-check: BDD level-set value disagrees with the "
                    "explicit abstraction lookup.");
            }
        }
        ++checked;
    }
    utils::g_log << "M&S level-set self-check passed (" << checked
                 << " sampled states)." << endl;

    // Heuristic ADD for statistics only (dead ends excluded).
    ADD h_add = vars->constant(0);
    for (const auto &[d, level] : level_sets) {
        h_add += level.Add() * vars->constant(d);
    }
    add_stats = compute_add_stats(
        vars, h_add, static_cast<int>(level_sets.size()));
}

map<int, BDD> MsLevelSets::build_state_map(
    const ms::MergeAndShrinkRepresentation &rep) const {
    map<int, BDD> result;
    if (const auto *leaf =
            dynamic_cast<const ms::MergeAndShrinkRepresentationLeaf *>(&rep)) {
        int var = leaf->get_variable();
        const vector<int> &table = leaf->get_lookup_table();
        for (size_t value = 0; value < table.size(); ++value) {
            int id = table[value];
            if (id == ms::PRUNED_STATE) {
                continue;
            }
            BDD b = vars->preBDD(var, static_cast<int>(value));
            auto it = result.find(id);
            if (it == result.end()) {
                result[id] = b;
            } else {
                it->second += b;
            }
        }
    } else {
        const auto &merge =
            dynamic_cast<const ms::MergeAndShrinkRepresentationMerge &>(rep);
        map<int, BDD> left = build_state_map(merge.get_left_child());
        map<int, BDD> right = build_state_map(merge.get_right_child());
        const vector<vector<int>> &table = merge.get_lookup_table();
        for (const auto &[id_left, bdd_left] : left) {
            for (const auto &[id_right, bdd_right] : right) {
                int merged = table[id_left][id_right];
                if (merged == ms::PRUNED_STATE) {
                    continue;
                }
                BDD product = bdd_left * bdd_right;
                if (product.IsZero()) {
                    continue;
                }
                auto it = result.find(merged);
                if (it == result.end()) {
                    result[merged] = product;
                } else {
                    it->second += product;
                }
            }
        }
    }
    return result;
}

void MsLevelSets::log_heuristic(WbhStats &stats) const {
    log_heuristic_stats(stats, add_stats);
}
}
