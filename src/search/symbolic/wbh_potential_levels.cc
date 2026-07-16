#include "wbh_potential_levels.h"

#include "wbh_add_stats.h"
#include "wbh_stats.h"

#include "../utils/system.h"

#include <cmath>

using namespace std;

namespace symbolic {
PotentialLevelSets::PotentialLevelSets(
    SymVariables *vars, const vector<vector<int>> &fact_potentials)
    : vars(vars) {
    build_add(fact_potentials);
    build_level_sets();
    add_stats = compute_add_stats(
        vars, h_add, static_cast<int>(h_add.CountLeaves()));
}

void PotentialLevelSets::build_add(
    const vector<vector<int>> &fact_potentials) {
    // h(s) = sum_v P(v, s(v)). Build as an ADD sum of per-fact indicator ADDs.
    h_add = vars->constant(0);
    for (size_t var = 0; var < fact_potentials.size(); ++var) {
        ADD var_add = vars->constant(0);
        for (size_t val = 0; val < fact_potentials[var].size(); ++val) {
            // Indicator BDD for "var = val" over the unprimed bits, as a 0/1
            // ADD, scaled by the integer potential. Invalid bit codes are in no
            // preBDD, so each variable contributes 0 on them (an extension in
            // [-M, M], paper Prop. prop-pot).
            ADD indicator = vars->preBDD(var, val).Add();
            var_add += indicator * vars->constant(fact_potentials[var][val]);
        }
        h_add += var_add;
    }
}

void PotentialLevelSets::build_level_sets() {
    double min_value = Cudd_V(h_add.FindMin().getNode());
    double max_value = Cudd_V(h_add.FindMax().getNode());
    BDD valid = vars->validStates();
    for (int v = static_cast<int>(lround(min_value));
         v <= static_cast<int>(lround(max_value)); ++v) {
        BDD level = h_add.BddInterval(v, v) * valid;
        if (!level.IsZero()) {
            level_sets[v] = level;
        }
    }
}

int PotentialLevelSets::value_of_state(const BDD &state) const {
    for (const auto &[value, level] : level_sets) {
        if (!(state * level).IsZero()) {
            return value;
        }
    }
    ABORT("State has no potential level (invalid initial state?).");
}

void PotentialLevelSets::log_heuristic(WbhStats &stats) const {
    log_heuristic_stats(stats, add_stats);
}
}
