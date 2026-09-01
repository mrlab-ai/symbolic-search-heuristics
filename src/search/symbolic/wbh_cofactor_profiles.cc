#include "wbh_cofactor_profiles.h"

#include "sym_variables.h"

#include "../utils/system.h"

#include <algorithm>
#include <limits>
#include <tuple>
#include <unordered_set>

using namespace std;

namespace symbolic {
namespace {
struct ResidualPair {
    DdNode *bdd;
    DdNode *add;

    bool operator==(const ResidualPair &other) const {
        return bdd == other.bdd && add == other.add;
    }
};

struct ResidualPairHash {
    size_t operator()(const ResidualPair &pair) const {
        size_t left = hash<DdNode *>{}(pair.bdd);
        size_t right = hash<DdNode *>{}(pair.add);
        return left ^ (right + 0x9e3779b9 + (left << 6) + (left >> 2));
    }
};

long checked_size(size_t value, const string &label) {
    if (value > static_cast<size_t>(numeric_limits<long>::max())) {
        ABORT("WBH " + label + " overflow.");
    }
    return static_cast<long>(value);
}

DdNode *advance_bdd_residual(
    DdManager *dd, DdNode *node, int expected_index, int level,
    bool take_then) {
    DdNode *regular = Cudd_Regular(node);
    if (Cudd_IsConstant(regular)) {
        return node;
    }
    const int node_index = Cudd_NodeReadIndex(regular);
    const int node_level = Cudd_ReadPerm(dd, node_index);
    if (node_level < level) {
        ABORT(
            "WBH joint profile encountered non-state BDD support between "
            "certified unprimed cuts.");
    }
    if (node_level > level) {
        return node;
    }
    if (node_index != expected_index) {
        ABORT("WBH joint profile CUDD index/level certificate mismatch.");
    }
    const int complemented = Cudd_IsComplement(node);
    DdNode *child = take_then ? Cudd_T(regular) : Cudd_E(regular);
    return Cudd_NotCond(child, complemented);
}

DdNode *advance_add_residual(
    DdManager *dd, DdNode *node, int expected_index, int level,
    bool take_then) {
    DdNode *regular = Cudd_Regular(node);
    if (Cudd_IsConstant(regular)) {
        return regular;
    }
    const int node_index = Cudd_NodeReadIndex(regular);
    const int node_level = Cudd_ReadPerm(dd, node_index);
    if (node_level < level) {
        ABORT(
            "WBH joint profile encountered non-state ADD support between "
            "certified unprimed cuts.");
    }
    if (node_level > level) {
        return regular;
    }
    if (node_index != expected_index) {
        ABORT("WBH joint profile ADD index/level certificate mismatch.");
    }
    return Cudd_Regular(take_then ? Cudd_T(regular) : Cudd_E(regular));
}
}

WbhStateCutCertificate make_wbh_state_cut_certificate(SymVariables *vars) {
    if (!vars) {
        ABORT("WBH state-cut certificate requires symbolic variables.");
    }
    DdManager *dd = vars->getCudd()->getManager();
    vector<tuple<int, int, int, int>> bits;
    for (int fd_var : vars->get_var_order()) {
        const vector<int> &indices = vars->vars_index_pre(fd_var);
        for (size_t bit = 0; bit < indices.size(); ++bit) {
            const int index = indices[bit];
            bits.emplace_back(
                Cudd_ReadPerm(dd, index), index, fd_var,
                static_cast<int>(bit));
        }
    }
    sort(bits.begin(), bits.end());

    WbhStateCutCertificate certificate;
    certificate.manager_variables = Cudd_ReadSize(dd);
    for (const auto &[level, index, fd_var, bit] : bits) {
        certificate.cudd_levels.push_back(level);
        certificate.cudd_indices.push_back(index);
        certificate.fd_variables.push_back(fd_var);
        certificate.fd_bit_positions.push_back(bit);
    }
    verify_wbh_state_cut_certificate(vars, certificate);
    return certificate;
}

void verify_wbh_state_cut_certificate(
    SymVariables *vars, const WbhStateCutCertificate &certificate) {
    if (!vars ||
        certificate.cudd_indices.size() != certificate.cudd_levels.size() ||
        certificate.cudd_indices.size() != certificate.fd_variables.size() ||
        certificate.cudd_indices.size() !=
            certificate.fd_bit_positions.size()) {
        ABORT("WBH state-cut certificate is incomplete.");
    }
    DdManager *dd = vars->getCudd()->getManager();
    if (certificate.manager_variables != Cudd_ReadSize(dd)) {
        ABORT("WBH state-cut manager size changed.");
    }
    vector<tuple<int, int, int, int>> expected_bits;
    for (int fd_var : vars->get_var_order()) {
        const vector<int> &indices = vars->vars_index_pre(fd_var);
        for (size_t bit = 0; bit < indices.size(); ++bit) {
            const int index = indices[bit];
            expected_bits.emplace_back(
                Cudd_ReadPerm(dd, index), index, fd_var,
                static_cast<int>(bit));
        }
    }
    sort(expected_bits.begin(), expected_bits.end());
    if (expected_bits.size() != certificate.cudd_indices.size()) {
        ABORT("WBH state-cut certificate omits an unprimed state bit.");
    }
    for (size_t i = 0; i < certificate.cudd_indices.size(); ++i) {
        const auto &[level, index, fd_var, bit] = expected_bits[i];
        if (certificate.cudd_levels[i] != level ||
            certificate.cudd_indices[i] != index ||
            certificate.fd_variables[i] != fd_var ||
            certificate.fd_bit_positions[i] != bit) {
            ABORT(
                "WBH variable order or state-bit mapping changed after its "
                "state-cut certificate was written (dynamic reordering is "
                "unsupported).");
        }
        if (i && certificate.cudd_levels[i - 1] >=
                     certificate.cudd_levels[i]) {
            ABORT("WBH state-cut levels are not strictly increasing.");
        }
    }
}

vector<long> compute_wbh_joint_cofactor_profile(
    DdManager *dd, const BDD &bdd, const ADD &add,
    const vector<int> &state_indices, const vector<int> &state_levels) {
    if (!dd || state_indices.size() != state_levels.size()) {
        ABORT("WBH joint profile received an invalid state-cut certificate.");
    }
    unordered_set<ResidualPair, ResidualPairHash> frontier{
        {bdd.getNode(), Cudd_Regular(add.getNode())}};
    vector<long> counts;
    counts.reserve(state_indices.size() + 1);
    counts.push_back(1);

    for (size_t position = 0; position < state_indices.size(); ++position) {
        const int expected_index = state_indices[position];
        const int level = state_levels[position];
        if (Cudd_ReadPerm(dd, expected_index) != level) {
            ABORT(
                "WBH joint profile variable order changed after its "
                "certificate was written (dynamic reordering is unsupported).");
        }
        if (frontier.size() > frontier.max_size() / 2) {
            ABORT("WBH joint profile frontier capacity overflow.");
        }
        unordered_set<ResidualPair, ResidualPairHash> next;
        next.reserve(frontier.size() * 2);
        for (const ResidualPair &pair : frontier) {
            for (bool take_then : {false, true}) {
                next.insert({
                    advance_bdd_residual(
                        dd, pair.bdd, expected_index, level, take_then),
                    advance_add_residual(
                        dd, pair.add, expected_index, level, take_then)});
            }
        }
        frontier.swap(next);
        counts.push_back(checked_size(frontier.size(), "joint profile count"));
    }

    for (const ResidualPair &pair : frontier) {
        if (!Cudd_IsConstant(Cudd_Regular(pair.bdd)) ||
            !Cudd_IsConstant(Cudd_Regular(pair.add))) {
            ABORT(
                "WBH joint profile retains nonterminal support after the "
                "final unprimed cut.");
        }
    }
    return counts;
}

vector<long> compute_wbh_bdd_cofactor_profile(
    DdManager *dd, const BDD &bdd, const vector<int> &state_indices,
    const vector<int> &state_levels) {
    if (!dd || state_indices.size() != state_levels.size()) {
        ABORT("WBH BDD profile received an invalid state-cut certificate.");
    }
    unordered_set<DdNode *> frontier{bdd.getNode()};
    vector<long> counts;
    counts.reserve(state_indices.size() + 1);
    counts.push_back(1);

    for (size_t position = 0; position < state_indices.size(); ++position) {
        const int expected_index = state_indices[position];
        const int level = state_levels[position];
        if (Cudd_ReadPerm(dd, expected_index) != level) {
            ABORT(
                "WBH BDD profile variable order changed after its certificate "
                "was written (dynamic reordering is unsupported).");
        }
        if (frontier.size() > frontier.max_size() / 2) {
            ABORT("WBH BDD profile frontier capacity overflow.");
        }
        unordered_set<DdNode *> next;
        next.reserve(frontier.size() * 2);
        for (DdNode *node : frontier) {
            for (bool take_then : {false, true}) {
                next.insert(advance_bdd_residual(
                    dd, node, expected_index, level, take_then));
            }
        }
        frontier.swap(next);
        counts.push_back(checked_size(frontier.size(), "BDD profile count"));
    }

    for (DdNode *node : frontier) {
        if (!Cudd_IsConstant(Cudd_Regular(node))) {
            ABORT(
                "WBH profile BDD depends on a primed or auxiliary variable "
                "after the final unprimed cut.");
        }
    }
    return counts;
}

vector<long> project_wbh_add_cofactor_profile(
    const vector<long> &manager_profile,
    const WbhStateCutCertificate &certificate) {
    if (certificate.manager_variables < 0 ||
        manager_profile.size() !=
            static_cast<size_t>(certificate.manager_variables) + 1) {
        ABORT("WBH ADD profile does not span its certified manager cuts.");
    }
    vector<long> projected;
    projected.reserve(certificate.cudd_levels.size() + 1);
    projected.push_back(manager_profile.front());
    for (int level : certificate.cudd_levels) {
        const size_t after_level = static_cast<size_t>(level) + 1;
        if (after_level >= manager_profile.size()) {
            ABORT("WBH ADD profile is shorter than its variable certificate.");
        }
        projected.push_back(manager_profile[after_level]);
    }
    return projected;
}
}
