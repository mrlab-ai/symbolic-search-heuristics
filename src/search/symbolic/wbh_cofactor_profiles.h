#ifndef SYMBOLIC_WBH_COFACTOR_PROFILES_H
#define SYMBOLIC_WBH_COFACTOR_PROFILES_H

#include "sym_bucket.h"

#include <vector>

namespace symbolic {
class SymVariables;

struct WbhStateCutCertificate {
    int manager_variables = 0;
    std::vector<int> cudd_indices;
    std::vector<int> cudd_levels;
    std::vector<int> fd_variables;
    std::vector<int> fd_bit_positions;
};

WbhStateCutCertificate make_wbh_state_cut_certificate(SymVariables *vars);

void verify_wbh_state_cut_certificate(
    SymVariables *vars, const WbhStateCutCertificate &certificate);

std::vector<long> compute_wbh_bdd_cofactor_profile(
    DdManager *dd, const BDD &bdd, const std::vector<int> &state_indices,
    const std::vector<int> &state_levels);

std::vector<long> compute_wbh_joint_cofactor_profile(
    DdManager *dd, const BDD &bdd, const ADD &add,
    const std::vector<int> &state_indices,
    const std::vector<int> &state_levels);

std::vector<long> project_wbh_add_cofactor_profile(
    const std::vector<long> &manager_profile,
    const WbhStateCutCertificate &certificate);
}

#endif
