#include "wbh_add_stats.h"

#include "wbh_stats.h"

#include "../utils/system.h"

#include <algorithm>
#include <cmath>
#include <set>
#include <unordered_set>

using namespace std;

namespace symbolic {
AddStats compute_add_stats(SymVariables *vars, const ADD &add, int num_values) {
    AddStats stats;
    stats.num_values = num_values;

    DdManager *dd = vars->getCudd()->getManager();
    stats.add_level_nodes.assign(Cudd_ReadSize(dd), 0);
    long inner = 0;
    unordered_set<DdNode *> visited;
    vector<DdNode *> stack;
    stack.push_back(Cudd_Regular(add.getNode()));
    while (!stack.empty()) {
        DdNode *node = stack.back();
        stack.pop_back();
        if (visited.count(node) > 0) {
            continue;
        }
        visited.insert(node);
        if (Cudd_IsConstant(node)) {
            ++stats.num_terminals;
            continue;
        }
        int index = Cudd_NodeReadIndex(node);
        int level = Cudd_ReadPerm(dd, index);
        ++stats.add_level_nodes[level];
        ++inner;
        stack.push_back(Cudd_Regular(Cudd_T(node)));
        stack.push_back(Cudd_Regular(Cudd_E(node)));
    }
    stats.add_inner_nodes = inner;
    stats.width_upper_bound = stats.add_inner_nodes + stats.num_terminals;

    // The reduced ADD may skip variables, so counting displayed nodes on a
    // CUDD level is not the cofactor width. Instead, maintain the exact set of
    // residual functions after each Boolean prefix. A residual whose root is
    // below the current level is unchanged (the function skips this bit); a
    // root on the current level advances to its two children. CUDD's unique
    // table makes pointer identity exactly equality of residual functions.
    unordered_set<DdNode *> frontier;
    frontier.insert(Cudd_Regular(add.getNode()));
    const int manager_levels = Cudd_ReadSize(dd);
    stats.cofactor_counts.reserve(manager_levels + 1);
    stats.cofactor_counts.push_back(1);
    stats.cofactor_width = 1;
    for (int level = 0; level < manager_levels; ++level) {
        // Most skipped levels are primed variables, which a state heuristic
        // never mentions. If the complete ADD DAG has no node here, every
        // current residual is unchanged and we can avoid rehashing the whole
        // frontier.
        if (stats.add_level_nodes[level] == 0) {
            stats.cofactor_counts.push_back(
                static_cast<long>(frontier.size()));
            continue;
        }
        unordered_set<DdNode *> next;
        next.reserve(frontier.size() * 2);
        for (DdNode *node : frontier) {
            if (Cudd_IsConstant(node)) {
                next.insert(node);
                continue;
            }
            int node_level =
                Cudd_ReadPerm(dd, Cudd_NodeReadIndex(node));
            if (node_level < level) {
                ABORT("ADD cofactor frontier violated the CUDD order.");
            }
            if (node_level == level) {
                next.insert(Cudd_Regular(Cudd_T(node)));
                next.insert(Cudd_Regular(Cudd_E(node)));
            } else {
                // Orderedness guarantees node_level > level here. Keeping the
                // node accounts for a reduced ADD edge that skips this level.
                next.insert(node);
            }
        }
        frontier.swap(next);
        long count = static_cast<long>(frontier.size());
        stats.cofactor_counts.push_back(count);
        stats.cofactor_width = max(stats.cofactor_width, count);
    }

    // These inequalities independently catch implementation or CUDD-order
    // mistakes: the final residuals are precisely the distinct terminals,
    // and every residual is an ADD node counted by the A+T upper bound.
    if (frontier.size() != static_cast<size_t>(stats.num_terminals) ||
        stats.cofactor_width > stats.width_upper_bound) {
        ABORT("Exact ADD cofactor-width computation failed its invariants.");
    }
    return stats;
}

vector<int> collect_integer_leaf_values(const ADD &add) {
    set<int> values;
    unordered_set<DdNode *> visited;
    vector<DdNode *> stack{Cudd_Regular(add.getNode())};
    while (!stack.empty()) {
        DdNode *node = stack.back();
        stack.pop_back();
        if (!visited.insert(node).second) {
            continue;
        }
        if (Cudd_IsConstant(node)) {
            values.insert(static_cast<int>(lround(Cudd_V(node))));
        } else {
            stack.push_back(Cudd_Regular(Cudd_T(node)));
            stack.push_back(Cudd_Regular(Cudd_E(node)));
        }
    }
    return vector<int>(values.begin(), values.end());
}

void log_heuristic_stats(WbhStats &stats, const AddStats &add_stats) {
    stats.log_heuristic(
        add_stats.add_inner_nodes, add_stats.num_values, add_stats.num_terminals,
        add_stats.add_level_nodes, add_stats.width_upper_bound);
}
}
