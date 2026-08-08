#include "wbh_add_stats.h"

#include "wbh_stats.h"

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
