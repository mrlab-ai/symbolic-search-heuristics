#include "wbh_pruner.h"

#include "search_algorithms/symbolic_search.h"

#include <limits>

using namespace std;

namespace symbolic {
WbhPruner::WbhPruner(
    const SymbolicSearch *engine, const map<int, BDD> &level_sets,
    const BDD &dead_ends)
    : engine(engine), dead_ends(dead_ends) {
    bool first = true;
    BDD acc;
    for (const auto &[value, level] : level_sets) {
        acc = first ? level : acc + level;
        first = false;
        cumulative_levels.emplace_back(value, acc);
    }
}

BDD WbhPruner::prune(BDD states, int g) const {
    if (!dead_ends.IsZero()) {
        states *= !dead_ends;
    }
    int upper_bound = engine->getUpperBound();
    if (upper_bound < numeric_limits<int>::max()) {
        // Keep only { s : h(s) <= upper_bound - 1 - g }: the largest
        // cumulative slice below the bound.
        int max_h = upper_bound - 1 - g;
        const BDD *keep = nullptr;
        for (const auto &[value, cumulative] : cumulative_levels) {
            if (value > max_h) {
                break;
            }
            keep = &cumulative;
        }
        if (keep) {
            states *= *keep;
        } else {
            states *= !states; // no value fits the bound: empty set
        }
    }
    return states;
}
}
