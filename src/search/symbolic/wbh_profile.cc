#include "wbh_profile.h"

#include "closed_list.h"
#include "sym_variables.h"
#include "wbh_add_stats.h"

#include "../utils/system.h"
#include "../utils/timer.h"

#include <algorithm>
#include <cmath>
#include <limits>
#include <set>
#include <sstream>
#include <tuple>
#include <unordered_map>
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

struct MaskedLayerStats {
    long add_nodes;
    int active_value_count;
    vector<int> active_values;
    bool bottom_reachable;
    vector<long> cofactor_counts;
    long cofactor_sum;
    long terminal_incidence;
    long partition_audit_effort;
    vector<long> partition_bucket_efforts;
    double masked_seconds;
    double partition_audit_seconds;
};

struct ReducedBddSignature {
    unsigned int index;
    size_t then_handle;
    size_t else_handle;

    bool operator==(const ReducedBddSignature &other) const {
        return index == other.index && then_handle == other.then_handle &&
               else_handle == other.else_handle;
    }
};

struct ReducedBddSignatureHash {
    size_t operator()(const ReducedBddSignature &signature) const {
        size_t result = hash<unsigned int>{}(signature.index);
        result ^= hash<size_t>{}(signature.then_handle) + 0x9e3779b9 +
                  (result << 6) + (result >> 2);
        result ^= hash<size_t>{}(signature.else_handle) + 0x9e3779b9 +
                  (result << 6) + (result >> 2);
        return result;
    }
};

long checked_add(long left, long right, const string &label) {
    if (right > 0 && left > numeric_limits<long>::max() - right) {
        ABORT("WBH " + label + " overflow.");
    }
    return left + right;
}

long count_reduced_bucket_nodes(
    const vector<DdNode *> &nodes,
    const vector<pair<size_t, size_t>> &child_ids,
    const vector<size_t> &ancestor_epochs, size_t epoch, size_t terminal_id,
    long ancestor_count, vector<size_t> &memo_epochs,
    vector<size_t> &memo_handles) {
    // Synthetic signed handles use bit 0 as complement polarity.  Handle 0 is
    // the regular BDD one terminal and handle 1 is BDD zero, matching CUDD.
    const size_t bdd_one = 0;
    const size_t bdd_zero = 1;
    unordered_map<ReducedBddSignature, size_t, ReducedBddSignatureHash>
        unique_nodes;
    unique_nodes.reserve(static_cast<size_t>(ancestor_count));
    vector<ReducedBddSignature> reduced_nodes;
    reduced_nodes.reserve(static_cast<size_t>(ancestor_count));

    auto make_node = [&](unsigned int index, size_t then_handle,
                         size_t else_handle) {
        if (then_handle == else_handle) {
            return then_handle;
        }
        const size_t complement = then_handle & 1U;
        if (complement) {
            then_handle ^= 1U;
            else_handle ^= 1U;
        }
        ReducedBddSignature signature{index, then_handle, else_handle};
        auto [it, inserted] =
            unique_nodes.emplace(signature, reduced_nodes.size() + 1);
        if (inserted) {
            reduced_nodes.push_back(signature);
        }
        if (it->second > numeric_limits<size_t>::max() / 2) {
            ABORT("WBH reduced bucket signature handle overflow.");
        }
        return (it->second << 1U) | complement;
    };

    auto reduce_node = [&](auto &self, size_t node_id) -> size_t {
        if (ancestor_epochs[node_id] != epoch) {
            return bdd_zero;
        }
        if (memo_epochs[node_id] == epoch) {
            return memo_handles[node_id];
        }
        DdNode *node = nodes[node_id];
        size_t handle;
        if (Cudd_IsConstant(node)) {
            handle = node_id == terminal_id ? bdd_one : bdd_zero;
        } else {
            const auto [then_id, else_id] = child_ids[node_id];
            if (then_id >= nodes.size() || else_id >= nodes.size()) {
                ABORT("WBH reduced bucket signature has an invalid child.");
            }
            handle = make_node(
                Cudd_NodeReadIndex(node), self(self, then_id),
                self(self, else_id));
        }
        memo_epochs[node_id] = epoch;
        memo_handles[node_id] = handle;
        return handle;
    };

    const size_t root_handle = reduce_node(reduce_node, 0);
    if (root_handle == bdd_zero) {
        ABORT("WBH active terminal reduced to an empty signature bucket.");
    }

    long count = 0;
    vector<unsigned char> reached(reduced_nodes.size() + 1, 0);
    vector<size_t> stack{root_handle >> 1U};
    while (!stack.empty()) {
        const size_t node_id = stack.back();
        stack.pop_back();
        if (node_id == 0 || reached[node_id]) {
            continue;
        }
        reached[node_id] = 1;
        count = checked_add(count, 1, "partition-audit effort");
        const ReducedBddSignature &signature = reduced_nodes[node_id - 1];
        stack.push_back(signature.then_handle >> 1U);
        stack.push_back(signature.else_handle >> 1U);
    }
    return count;
}

vector<int> validate_heuristic_terminals(const ADD &heuristic) {
    set<int> values;
    unordered_set<DdNode *> visited;
    vector<DdNode *> stack{heuristic.getNode()};
    while (!stack.empty()) {
        DdNode *node = stack.back();
        stack.pop_back();
        if (Cudd_IsComplement(node)) {
            ABORT("WBH heuristic ADD uses an unexpected complemented edge.");
        }
        if (!visited.insert(node).second) {
            continue;
        }
        if (Cudd_IsConstant(node)) {
            const double value = Cudd_V(node);
            const double rounded = round(value);
            if (!isfinite(value) || value != rounded || value < 0 ||
                value > numeric_limits<int>::max()) {
                ABORT(
                    "WBH masked profiles require finite nonnegative integer "
                    "heuristic terminals.");
            }
            values.insert(static_cast<int>(rounded));
        } else {
            stack.push_back(Cudd_T(node));
            stack.push_back(Cudd_E(node));
        }
    }
    return vector<int>(values.begin(), values.end());
}

vector<long> compute_add_profile(
    DdManager *dd, const ADD &add, const vector<int> &state_indices,
    const vector<int> &state_levels) {
    if (Cudd_IsComplement(add.getNode())) {
        ABORT("WBH masked ADD uses an unexpected complemented root.");
    }
    unordered_set<DdNode *> frontier{add.getNode()};
    vector<long> counts;
    counts.reserve(state_indices.size() + 1);
    counts.push_back(1);
    for (size_t position = 0; position < state_indices.size(); ++position) {
        const int expected_index = state_indices[position];
        const int level = state_levels[position];
        if (Cudd_ReadPerm(dd, expected_index) != level) {
            ABORT(
                "WBH masked profile variable order changed after its "
                "certificate was written.");
        }
        unordered_set<DdNode *> next;
        next.reserve(frontier.size() * 2);
        for (DdNode *node : frontier) {
            if (Cudd_IsComplement(node)) {
                ABORT(
                    "WBH masked ADD uses an unexpected complemented edge.");
            }
            if (Cudd_IsConstant(node)) {
                next.insert(node);
                continue;
            }
            const int node_index = Cudd_NodeReadIndex(node);
            const int node_level = Cudd_ReadPerm(dd, node_index);
            if (node_level < level) {
                ABORT(
                    "WBH masked ADD depends on non-state support between "
                    "certified cuts.");
            }
            if (node_level == level) {
                if (node_index != expected_index) {
                    ABORT(
                        "WBH masked ADD CUDD index/level certificate "
                        "mismatch.");
                }
                DdNode *then_node = Cudd_T(node);
                DdNode *else_node = Cudd_E(node);
                if (Cudd_IsComplement(then_node) ||
                    Cudd_IsComplement(else_node)) {
                    ABORT(
                        "WBH masked ADD uses an unexpected complemented "
                        "edge.");
                }
                next.insert(then_node);
                next.insert(else_node);
            } else {
                next.insert(node);
            }
        }
        frontier.swap(next);
        counts.push_back(static_cast<long>(frontier.size()));
    }
    for (DdNode *node : frontier) {
        if (Cudd_IsComplement(node) || !Cudd_IsConstant(node)) {
            ABORT(
                "WBH masked ADD retains nonterminal or complemented support "
                "after the final certified cut.");
        }
    }
    return counts;
}

MaskedLayerStats compute_masked_layer_stats(
    SymVariables *vars, const BDD &layer, const ADD &heuristic,
    const vector<int> &heuristic_values,
    const vector<int> &state_indices, const vector<int> &state_levels,
    const vector<long> &joint_profile) {
    utils::Timer masked_timer;
    if (heuristic_values.empty()) {
        ABORT("WBH masked profile encountered an ADD without terminals.");
    }
    ADD bottom = vars->constant(-1);
    DdNode *bottom_node = bottom.getNode();
    ADD masked = layer.Add().Ite(heuristic, bottom);
    if (Cudd_IsComplement(masked.getNode())) {
        ABORT("WBH masked ADD uses an unexpected complemented root.");
    }
    DdNode *root = masked.getNode();
    vector<long> masked_profile = compute_add_profile(
        vars->getCudd()->getManager(), masked, state_indices, state_levels);
    if (masked_profile.size() != joint_profile.size()) {
        ABORT("WBH masked and joint profiles use different cut counts.");
    }
    long cofactor_sum = 0;
    for (size_t cut = 0; cut < masked_profile.size(); ++cut) {
        if (masked_profile[cut] > joint_profile[cut]) {
            ABORT(
                "WBH masked cofactor count exceeds the joint-profile "
                "certificate.");
        }
        if (cut + 1 < masked_profile.size()) {
            cofactor_sum = checked_add(
                cofactor_sum, masked_profile[cut],
                "masked cofactor-profile sum");
        }
    }

    // Build reverse ADD edges once. For each active terminal, traverse its
    // ancestors with an epoch-marked visited vector. This counts exactly the
    // inner nodes from which that value is reachable, in O(D + I) time and
    // O(D) auxiliary memory instead of materializing a value set per node.
    unordered_map<DdNode *, size_t> node_ids;
    vector<DdNode *> nodes;
    const size_t invalid_node_id = numeric_limits<size_t>::max();
    vector<pair<size_t, size_t>> child_ids;
    vector<pair<size_t, size_t>> parent_edges;
    auto add_node = [&](DdNode *node) {
        auto [it, inserted] = node_ids.emplace(node, nodes.size());
        if (inserted) {
            nodes.push_back(node);
            child_ids.emplace_back(invalid_node_id, invalid_node_id);
        }
        return it->second;
    };
    add_node(root);
    long add_nodes = 0;
    vector<size_t> active_terminal_ids;
    for (size_t node_id = 0; node_id < nodes.size(); ++node_id) {
        DdNode *node = nodes[node_id];
        if (Cudd_IsComplement(node)) {
            ABORT("WBH masked ADD uses an unexpected complemented edge.");
        }
        if (Cudd_IsConstant(node)) {
            if (node != bottom_node) {
                active_terminal_ids.push_back(node_id);
            }
            continue;
        }
        DdNode *then_node = Cudd_T(node);
        DdNode *else_node = Cudd_E(node);
        if (Cudd_IsComplement(then_node) || Cudd_IsComplement(else_node)) {
            ABORT("WBH masked ADD uses an unexpected complemented edge.");
        }
        const size_t then_id = add_node(then_node);
        const size_t else_id = add_node(else_node);
        child_ids[node_id] = {then_id, else_id};
        parent_edges.emplace_back(then_id, node_id);
        parent_edges.emplace_back(else_id, node_id);
        add_nodes = checked_add(add_nodes, 1, "masked ADD node count");
    }

    vector<size_t> parent_offsets(nodes.size() + 1, 0);
    for (const auto &edge : parent_edges) {
        ++parent_offsets[edge.first + 1];
    }
    for (size_t node_id = 0; node_id < nodes.size(); ++node_id) {
        parent_offsets[node_id + 1] += parent_offsets[node_id];
    }
    vector<size_t> next_parent = parent_offsets;
    vector<size_t> parent_ids(parent_edges.size());
    for (const auto &[child, parent] : parent_edges) {
        parent_ids[next_parent[child]++] = parent;
    }
    parent_edges.clear();
    parent_edges.shrink_to_fit();

    if (active_terminal_ids.empty()) {
        ABORT("WBH masked profile received an empty prepared layer.");
    }
    if (active_terminal_ids.size() >
        static_cast<size_t>(numeric_limits<int>::max())) {
        ABORT("WBH masked profile active-value count overflow.");
    }
    const int active_values = static_cast<int>(active_terminal_ids.size());
    sort(
        active_terminal_ids.begin(), active_terminal_ids.end(),
        [&](size_t left, size_t right) {
            return Cudd_V(nodes[left]) < Cudd_V(nodes[right]);
        });
    vector<int> active_value_list;
    active_value_list.reserve(active_terminal_ids.size());
    for (size_t terminal_id : active_terminal_ids) {
        DdNode *terminal = nodes[terminal_id];
        const double value = Cudd_V(terminal);
        if (value != round(value) || value < 0 ||
            value > numeric_limits<int>::max()) {
            ABORT("WBH active terminal is not a certified heuristic value.");
        }
        active_value_list.push_back(static_cast<int>(value));
    }

    long incidence = 0;
    vector<size_t> seen(nodes.size(), 0);
    size_t epoch = 0;
    vector<size_t> ancestor_stack;
    for (size_t terminal_id : active_terminal_ids) {
        if (epoch == numeric_limits<size_t>::max()) {
            ABORT("WBH terminal-incidence traversal epoch overflow.");
        }
        ++epoch;
        ancestor_stack.push_back(terminal_id);
        while (!ancestor_stack.empty()) {
            const size_t node_id = ancestor_stack.back();
            ancestor_stack.pop_back();
            if (seen[node_id] == epoch) {
                continue;
            }
            seen[node_id] = epoch;
            if (!Cudd_IsConstant(nodes[node_id])) {
                incidence = checked_add(
                    incidence, 1, "terminal-incidence certificate");
            }
            for (size_t position = parent_offsets[node_id];
                 position < parent_offsets[node_id + 1]; ++position) {
                ancestor_stack.push_back(parent_ids[position]);
            }
        }
    }
    const bool bottom_reachable = !(!layer).IsZero();
    const long expected_terminals =
        static_cast<long>(active_values) + (bottom_reachable ? 1 : 0);
    if (masked_profile.back() != expected_terminals) {
        ABORT(
            "WBH masked terminal census disagrees with active values and "
            "bottom reachability.");
    }
    if (active_values > 0 &&
        add_nodes > numeric_limits<long>::max() / active_values) {
        ABORT("WBH masked ADD product bound overflow.");
    }
    if (incidence < add_nodes || incidence > add_nodes * active_values) {
        ABORT("WBH terminal incidence violates its ADD product bounds.");
    }
    if (add_nodes > cofactor_sum) {
        ABORT("WBH masked ADD node count exceeds its cofactor-profile sum.");
    }

    const double event_masked_seconds = masked_timer();
    utils::Timer partition_timer;
    long partition_audit_effort = 0;
    vector<long> partition_bucket_efforts;
    partition_bucket_efforts.reserve(active_terminal_ids.size());
    if (active_terminal_ids.size() == 1) {
        // With one active value, its characteristic bucket is exactly layer.
        partition_audit_effort = max(0, layer.nodeCount() - 1);
        partition_bucket_efforts.push_back(partition_audit_effort);
    } else {
        vector<size_t> memo_epochs(nodes.size(), 0);
        vector<size_t> memo_handles(nodes.size(), 0);
        for (size_t terminal_id : active_terminal_ids) {
            if (epoch == numeric_limits<size_t>::max()) {
                ABORT("WBH reduced bucket traversal epoch overflow.");
            }
            ++epoch;
            long ancestor_count = 0;
            ancestor_stack.push_back(terminal_id);
            while (!ancestor_stack.empty()) {
                const size_t node_id = ancestor_stack.back();
                ancestor_stack.pop_back();
                if (seen[node_id] == epoch) {
                    continue;
                }
                seen[node_id] = epoch;
                if (!Cudd_IsConstant(nodes[node_id])) {
                    ancestor_count = checked_add(
                        ancestor_count, 1,
                        "reduced bucket ancestor count");
                }
                for (size_t position = parent_offsets[node_id];
                     position < parent_offsets[node_id + 1]; ++position) {
                    ancestor_stack.push_back(parent_ids[position]);
                }
            }
            const long bucket_effort = count_reduced_bucket_nodes(
                nodes, child_ids, seen, epoch, terminal_id, ancestor_count,
                memo_epochs, memo_handles);
            partition_bucket_efforts.push_back(bucket_effort);
            partition_audit_effort = checked_add(
                partition_audit_effort, bucket_effort,
                "partition-audit effort");
        }
    }
    if (partition_audit_effort > incidence) {
        ABORT(
            "WBH partition-audit effort exceeds its terminal-incidence "
            "certificate.");
    }
    return {
        add_nodes, active_values, move(active_value_list), bottom_reachable,
        move(masked_profile), cofactor_sum, incidence,
        partition_audit_effort, move(partition_bucket_efforts),
        event_masked_seconds, partition_timer()};
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

vector<long> compute_joint_profile(
    DdManager *dd, const BDD &bdd, const ADD &add,
    const vector<int> &state_indices, const vector<int> &state_levels) {
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
        counts.push_back(static_cast<long>(frontier.size()));
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

vector<long> compute_bdd_profile(
    DdManager *dd, const BDD &bdd, const vector<int> &state_indices,
    const vector<int> &state_levels) {
    unordered_set<DdNode *> frontier{bdd.getNode()};
    vector<long> counts;
    counts.reserve(state_indices.size() + 1);
    counts.push_back(1);

    for (size_t position = 0; position < state_indices.size(); ++position) {
        const int expected_index = state_indices[position];
        const int level = state_levels[position];
        if (Cudd_ReadPerm(dd, expected_index) != level) {
            ABORT(
                "WBH profile variable order changed after its certificate "
                "was written (dynamic reordering is unsupported).");
        }

        unordered_set<DdNode *> next;
        next.reserve(frontier.size() * 2);
        for (DdNode *node : frontier) {
            DdNode *regular = Cudd_Regular(node);
            if (Cudd_IsConstant(regular)) {
                next.insert(node);
                continue;
            }
            const int node_index = Cudd_NodeReadIndex(regular);
            const int node_level = Cudd_ReadPerm(dd, node_index);
            if (node_level < level) {
                ABORT(
                    "WBH profile encountered non-state BDD support between "
                    "certified unprimed cuts.");
            }
            if (node_level == level) {
                if (node_index != expected_index) {
                    ABORT("WBH profile CUDD index/level certificate mismatch.");
                }
                const int complemented = Cudd_IsComplement(node);
                // CUDD complement edges are semantic: f and !f must remain
                // different residuals. Propagate the root polarity to both
                // cofactors instead of regularizing them.
                next.insert(Cudd_NotCond(Cudd_T(regular), complemented));
                next.insert(Cudd_NotCond(Cudd_E(regular), complemented));
            } else {
                next.insert(node);
            }
        }
        frontier.swap(next);
        counts.push_back(static_cast<long>(frontier.size()));
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

void append_long_vector(ostringstream &stream, const vector<long> &values) {
    stream << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i) {
            stream << ",";
        }
        stream << values[i];
    }
    stream << "]";
}

void append_int_vector(ostringstream &stream, const vector<int> &values) {
    stream << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i) {
            stream << ",";
        }
        stream << values[i];
    }
    stream << "]";
}
}

WbhProfile::WbhProfile(const string &path) {
    out.open(path);
    if (!out.is_open()) {
        ABORT("Could not open WBH profile log file: " + path);
    }
    write_payload(
        "{\"event\":\"schema\",\"version\":3,"
        "\"cut_convention\":\"unprimed_state_bits_in_cudd_level_order_"
        "including_terminal\","
        "\"node_count_convention\":\"regular_cudd_inner_nodes_of_semantic_"
        "union\","
        "\"residual_identity\":\"canonical_signed_cudd_pointer_with_"
        "complement_polarity\","
        "\"joint_residual_identity\":\"cooccurring_signed_bdd_and_regular_"
        "add_pointer_pair\","
        "\"masked_function\":\"heuristic_on_layer_fresh_bottom_elsewhere\","
        "\"terminal_incidence\":\"sum_of_reachable_nonbottom_terminals_over_"
        "regular_inner_masked_add_nodes\","
        "\"partition_audit_effort\":\"sum_of_regular_cudd_inner_nodes_of_"
        "nonempty_layer_value_buckets_audit_only\"}");
}

WbhProfile::~WbhProfile() {
    if (out.is_open()) {
        if (pending_layer) {
            finish_blind_layer(false);
        }
        log_summary();
        out.flush();
        out.close();
    }
}

void WbhProfile::write_payload(const string &payload) {
    utils::Timer output_timer;
    out << payload << "\n";
    // Profile events are expensive and few; flush each one so externally
    // killed experiment runs retain every completed certificate/profile.
    out.flush();
    output_seconds += output_timer();
}

void WbhProfile::verify_variable_order(SymVariables *vars) const {
    if (!variable_order_written) {
        ABORT("WBH profile variable-order certificate has not been written.");
    }
    DdManager *dd = vars->getCudd()->getManager();
    for (size_t i = 0; i < state_indices.size(); ++i) {
        if (Cudd_ReadPerm(dd, state_indices[i]) != state_levels[i]) {
            ABORT(
                "WBH profile variable order changed after its certificate "
                "was written (dynamic reordering is unsupported).");
        }
    }
}

void WbhProfile::log_variable_order(SymVariables *vars) {
    if (variable_order_written) {
        return;
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

    vector<int> fd_variables;
    vector<int> fd_bit_positions;
    for (const auto &[level, index, fd_var, bit] : bits) {
        state_levels.push_back(level);
        state_indices.push_back(index);
        fd_variables.push_back(fd_var);
        fd_bit_positions.push_back(bit);
    }
    variable_order_written = true;

    utils::Timer serialization_timer;
    ostringstream event;
    event << "{\"event\":\"variable_order\",\"manager_variables\":"
          << Cudd_ReadSize(dd) << ",\"state_bits\":" << state_indices.size()
          << ",\"cudd_indices\":";
    append_int_vector(event, state_indices);
    event << ",\"cudd_levels\":";
    append_int_vector(event, state_levels);
    event << ",\"fd_variables\":";
    append_int_vector(event, fd_variables);
    event << ",\"fd_bit_positions\":";
    append_int_vector(event, fd_bit_positions);
    event << "}";
    serialization_seconds += serialization_timer();
    write_payload(event.str());
}

void WbhProfile::run_masked_self_test(SymVariables *vars) {
    verify_variable_order(vars);
    if (state_indices.size() < 2) {
        ABORT("WBH masked self-test requires at least two state bits.");
    }
    DdManager *dd = vars->getCudd()->getManager();
    BDD x0 = vars->getCudd()->bddVar(state_indices[0]);
    BDD x1 = vars->getCudd()->bddVar(state_indices[1]);
    ADD zero = vars->constant(0);
    auto measure = [&](const BDD &layer, const ADD &heuristic) {
        vector<long> joint = compute_joint_profile(
            dd, layer, heuristic, state_indices, state_levels);
        vector<int> values = validate_heuristic_terminals(heuristic);
        MaskedLayerStats stats = compute_masked_layer_stats(
            vars, layer, heuristic, values, state_indices, state_levels,
            joint);
        ADD masked = layer.Add().Ite(heuristic, vars->constant(-1));
        vector<long> materialized_efforts;
        long materialized_sum = 0;
        for (int value : stats.active_values) {
            BDD bucket = masked.BddInterval(value, value);
            if (bucket.IsZero()) {
                ABORT(
                    "WBH masked self-test materialized an empty active bucket.");
            }
            const long effort = max(0, bucket.nodeCount() - 1);
            materialized_efforts.push_back(effort);
            materialized_sum = checked_add(
                materialized_sum, effort,
                "self-test materialized partition effort");
        }
        if (materialized_efforts != stats.partition_bucket_efforts ||
            materialized_sum != stats.partition_audit_effort) {
            ABORT(
                "WBH reduced bucket signatures disagree with materialized "
                "self-test buckets.");
        }
        return stats;
    };

    MaskedLayerStats parity = measure(x0 ^ x1, zero);
    if (parity.add_nodes != 3 || parity.active_values != vector<int>{0} ||
        parity.bottom_reachable != true || parity.terminal_incidence != 3 ||
        parity.partition_audit_effort != 2) {
        ABORT("WBH masked self-test failed complement-edge parity.");
    }

    MaskedLayerStats total = measure(vars->oneBDD(), x0.Add());
    if (total.add_nodes != 1 || total.active_values != vector<int>({0, 1}) ||
        total.bottom_reachable != false || total.terminal_incidence != 2 ||
        total.partition_audit_effort != 2) {
        ABORT("WBH masked self-test failed the bottom-absent case.");
    }

    MaskedLayerStats equality = measure(!(x0 ^ x1), x0.Add());
    if (equality.add_nodes != 3 ||
        equality.active_values != vector<int>({0, 1}) ||
        equality.terminal_incidence != 4 ||
        equality.partition_audit_effort != 4) {
        ABORT("WBH masked self-test failed the two-value case.");
    }

    MaskedLayerStats constant = measure(vars->oneBDD(), vars->constant(7));
    if (constant.add_nodes != 0 ||
        constant.active_values != vector<int>{7} ||
        constant.bottom_reachable != false ||
        constant.terminal_incidence != 0 ||
        constant.partition_audit_effort != 0) {
        ABORT("WBH masked self-test failed the constant case.");
    }

    BDD support = !x0;
    MaskedLayerStats support_zero = measure(support, zero);
    MaskedLayerStats support_variant =
        measure(support, x0.Add() * x1.Add());
    if (support_zero.add_nodes != 1 ||
        support_zero.terminal_incidence != 1 ||
        support_zero.partition_audit_effort != 1 ||
        support_zero.active_values != support_variant.active_values ||
        support_zero.bottom_reachable != support_variant.bottom_reachable ||
        support_zero.cofactor_counts != support_variant.cofactor_counts ||
        support_zero.add_nodes != support_variant.add_nodes ||
        support_zero.terminal_incidence !=
            support_variant.terminal_incidence ||
        support_zero.partition_audit_effort !=
            support_variant.partition_audit_effort) {
        ABORT("WBH masked self-test failed support invariance.");
    }

    // Exercise constant-heuristic bucket extraction from a larger masked ADD
    // after creating many short-lived cubes.  The hidden-weighted-bit layer is
    // nonempty and nontotal, and is deliberately expensive for ordered DDs.
    const size_t pressure_bits = min<size_t>(12, state_indices.size());
    const unsigned int assignment_count = 1U << pressure_bits;
    BDD pressure_layer = vars->zeroBDD();
    for (unsigned int assignment = 0; assignment < assignment_count;
         ++assignment) {
        unsigned int value = assignment;
        unsigned int weight = 0;
        while (value) {
            weight += value & 1U;
            value >>= 1U;
        }
        if (weight == 0 || !(assignment & (1U << (weight - 1)))) {
            continue;
        }
        BDD cube = vars->oneBDD();
        for (size_t bit = 0; bit < pressure_bits; ++bit) {
            BDD variable = vars->getCudd()->bddVar(state_indices[bit]);
            cube *= (assignment & (1U << bit)) ? variable : !variable;
        }
        pressure_layer += cube;
    }
    const long pressure_nodes = max(0, pressure_layer.nodeCount() - 1);
    if (pressure_layer.IsZero() || (!pressure_layer).IsZero() ||
        (pressure_bits >= 8 && pressure_nodes < 32)) {
        ABORT(
            "WBH masked self-test did not build a pressured nontrivial layer.");
    }
    MaskedLayerStats pressure = measure(pressure_layer, zero);
    if (pressure.active_values != vector<int>{0} ||
        pressure.bottom_reachable != true ||
        pressure.partition_audit_effort != pressure_nodes) {
        ABORT("WBH masked self-test failed pressured constant extraction.");
    }

    ADD pressure_heuristic = zero;
    for (size_t bit = 0; bit < min<size_t>(3, pressure_bits); ++bit) {
        pressure_heuristic +=
            vars->getCudd()->bddVar(state_indices[bit]).Add() *
            vars->constant(1U << bit);
    }
    MaskedLayerStats pressure_multivalue =
        measure(pressure_layer, pressure_heuristic);
    if (pressure_multivalue.active_values.size() < 2 ||
        pressure_multivalue.partition_bucket_efforts.size() !=
            pressure_multivalue.active_values.size()) {
        ABORT("WBH masked self-test failed multivalue signature extraction.");
    }
    verify_variable_order(vars);
    cout << "WBH masked terminal-incidence self-test passed (7 cases)."
         << endl;
}

void WbhProfile::log_heuristic(
    SymVariables *vars, const ADD &add, const AddStats &add_stats) {
    if (heuristic_written) {
        ABORT("WBH profile received more than one selected heuristic.");
    }
    verify_variable_order(vars);
    if (add_stats.cofactor_counts.empty()) {
        ABORT("WBH selected heuristic has no complete cofactor profile.");
    }

    vector<long> projected;
    projected.reserve(state_levels.size() + 1);
    projected.push_back(add_stats.cofactor_counts.front());
    for (int level : state_levels) {
        const size_t after_level = static_cast<size_t>(level) + 1;
        if (after_level >= add_stats.cofactor_counts.size()) {
            ABORT("WBH ADD profile is shorter than its variable certificate.");
        }
        projected.push_back(add_stats.cofactor_counts[after_level]);
    }
    const long width = *max_element(projected.begin(), projected.end());
    if (width != add_stats.cofactor_width) {
        ABORT(
            "WBH projected heuristic profile disagrees with the exact "
            "cofactor width.");
    }
    heuristic_written = true;
    heuristic_add = add;
    heuristic_values = validate_heuristic_terminals(add);
    if (heuristic_values.size() !=
        static_cast<size_t>(add_stats.num_terminals)) {
        ABORT("WBH heuristic terminal validation disagrees with ADD stats.");
    }
    heuristic_cofactor_seconds += add_stats.cofactor_seconds;

    utils::Timer serialization_timer;
    ostringstream event;
    event << "{\"event\":\"heuristic_profile\",\"add_nodes\":"
          << add_stats.add_inner_nodes << ",\"num_values\":"
          << add_stats.num_values << ",\"num_terminals\":"
          << add_stats.num_terminals << ",\"cofactor_counts\":";
    append_long_vector(event, projected);
    event << ",\"cofactor_width\":" << width
          << ",\"cofactor_seconds\":" << add_stats.cofactor_seconds << "}";
    serialization_seconds += serialization_timer();
    write_payload(event.str());
}

void WbhProfile::attach_heuristic_closed(
    SymVariables *vars, const shared_ptr<ClosedList> &closed) {
    if (!heuristic_written) {
        ABORT(
            "WBH profile cannot attach heuristic layers before the selected "
            "heuristic profile.");
    }
    if (!closed || !heuristic_closed.expired() || heuristic_layer_vars) {
        ABORT(
            "WBH profile received an invalid duplicate closed-list "
            "attachment.");
    }
    verify_variable_order(vars);
    heuristic_layer_vars = vars;
    heuristic_closed = closed;
}

void WbhProfile::prepare_blind_layer(
    int g, SymVariables *vars, const Bucket &pieces) {
    if (pending_layer) {
        ABORT("WBH profile already has a pending prepared blind layer.");
    }
    verify_variable_order(vars);
    utils::Timer union_timer;
    BDD layer = vars->zeroBDD();
    for (const BDD &piece : pieces) {
        layer += piece;
    }
    const double event_union_seconds = union_timer();

    utils::Timer cofactor_timer;
    vector<long> profile = compute_bdd_profile(
        vars->getCudd()->getManager(), layer, state_indices, state_levels);
    const double event_cofactor_seconds = cofactor_timer();
    vector<long> joint_profile;
    double event_joint_cofactor_seconds = 0;
    MaskedLayerStats masked_stats{
        0, 0, {}, false, {}, 0, 0, 0, {}, 0, 0};
    if (heuristic_written) {
        utils::Timer joint_cofactor_timer;
        joint_profile = compute_joint_profile(
            vars->getCudd()->getManager(), layer, heuristic_add, state_indices,
            state_levels);
        event_joint_cofactor_seconds = joint_cofactor_timer();
        masked_stats = compute_masked_layer_stats(
            vars, layer, heuristic_add, heuristic_values, state_indices,
            state_levels, joint_profile);
        verify_variable_order(vars);
    }
    const long nodes = max(0, layer.nodeCount() - 1);
    const long width = *max_element(profile.begin(), profile.end());

    union_seconds += event_union_seconds;
    cofactor_seconds += event_cofactor_seconds;
    joint_cofactor_seconds += event_joint_cofactor_seconds;
    masked_seconds += masked_stats.masked_seconds;
    partition_audit_seconds += masked_stats.partition_audit_seconds;

    pending_layer = make_unique<PendingLayer>(PendingLayer{
        g, static_cast<int>(pieces.size()), nodes, move(profile),
        move(joint_profile), width, masked_stats.add_nodes,
        masked_stats.active_value_count, move(masked_stats.active_values),
        masked_stats.bottom_reachable,
        move(masked_stats.cofactor_counts), masked_stats.cofactor_sum,
        masked_stats.terminal_incidence,
        masked_stats.partition_audit_effort, event_union_seconds,
        event_cofactor_seconds, event_joint_cofactor_seconds,
        masked_stats.masked_seconds, masked_stats.partition_audit_seconds});
}

void WbhProfile::finish_blind_layer(bool completed) {
    if (!pending_layer) {
        ABORT("WBH profile has no pending prepared blind layer.");
    }
    const PendingLayer &layer = *pending_layer;
    ++profiled_layer_attempts;
    if (completed) {
        ++profiled_layers;
        sum_layer_bdd_nodes += layer.bdd_nodes;
        forward_layers.push_back({
            layer.g, layer.bdd_nodes, layer.masked_add_nodes,
            layer.terminal_incidence, layer.partition_audit_effort});
    }

    utils::Timer serialization_timer;
    ostringstream event;
    event << "{\"event\":\"layer_profile\",\"g\":" << layer.g
          << ",\"completed\":" << (completed ? "true" : "false")
          << ",\"piece_count\":" << layer.piece_count
          << ",\"bdd_nodes\":" << layer.bdd_nodes
          << ",\"cofactor_counts\":";
    append_long_vector(event, layer.cofactor_counts);
    event << ",\"joint_cofactor_counts\":";
    append_long_vector(event, layer.joint_cofactor_counts);
    event << ",\"cofactor_width\":" << layer.cofactor_width
          << ",\"masked_add_nodes\":" << layer.masked_add_nodes
          << ",\"active_value_count\":" << layer.active_value_count
          << ",\"active_values\":";
    append_int_vector(event, layer.active_values);
    event << ",\"bottom_reachable\":"
          << (layer.bottom_reachable ? "true" : "false")
          << ",\"masked_cofactor_counts\":";
    append_long_vector(event, layer.masked_cofactor_counts);
    event << ",\"masked_cofactor_sum\":" << layer.masked_cofactor_sum
          << ",\"terminal_incidence\":" << layer.terminal_incidence
          << ",\"partition_audit_effort\":"
          << layer.partition_audit_effort
          << ",\"union_seconds\":" << layer.union_seconds
          << ",\"cofactor_seconds\":" << layer.cofactor_seconds
          << ",\"joint_cofactor_seconds\":"
          << layer.joint_cofactor_seconds
          << ",\"masked_seconds\":" << layer.masked_seconds
          << ",\"partition_audit_seconds\":"
          << layer.partition_audit_seconds << "}";
    serialization_seconds += serialization_timer();
    write_payload(event.str());
    pending_layer.reset();
}

void WbhProfile::log_done(int solution_cost) {
    if (done_written) {
        return;
    }
    if (heuristic_layer_vars) {
        if (!forward_layers.empty() || pending_layer) {
            ABORT("WBH heuristic profile already contains layer records.");
        }
        shared_ptr<ClosedList> closed = heuristic_closed.lock();
        if (!closed) {
            ABORT("WBH heuristic profile lost its attached closed list.");
        }
        for (const auto &[g, layer] : closed->getClosedList()) {
            if (g >= solution_cost) {
                break;
            }
            prepare_blind_layer(g, heuristic_layer_vars, Bucket{layer});
            finish_blind_layer(true);
        }
    }
    done_written = true;
    long effort = 0;
    long masked_add_effort = 0;
    long terminal_incidence_effort = 0;
    long partition_audit_effort = 0;
    for (const LayerRecord &record : forward_layers) {
        if (record.g < solution_cost) {
            effort = checked_add(effort, record.bdd_nodes, "layer effort");
            masked_add_effort = checked_add(
                masked_add_effort, record.masked_add_nodes,
                "masked-ADD effort");
            terminal_incidence_effort = checked_add(
                terminal_incidence_effort, record.terminal_incidence,
                "terminal-incidence effort");
            partition_audit_effort = checked_add(
                partition_audit_effort, record.partition_audit_effort,
                "partition-audit effort");
        }
    }

    utils::Timer serialization_timer;
    ostringstream event;
    event << "{\"event\":\"done\",\"layer_union_effort\":" << effort
          << ",\"masked_add_effort\":" << masked_add_effort
          << ",\"terminal_incidence_effort\":"
          << terminal_incidence_effort
          << ",\"partition_audit_effort\":" << partition_audit_effort
          << ",\"solution_cost\":" << solution_cost << "}";
    serialization_seconds += serialization_timer();
    write_payload(event.str());
    log_summary();
}

void WbhProfile::log_summary() {
    if (summary_written) {
        return;
    }
    summary_written = true;
    utils::Timer serialization_timer;
    ostringstream event;
    event << "{\"event\":\"summary\",\"profiled_layer_attempts\":"
          << profiled_layer_attempts << ",\"profiled_layers\":"
          << profiled_layers << ",\"sum_layer_bdd_nodes\":"
          << sum_layer_bdd_nodes << ",\"heuristic_profiled\":"
          << (heuristic_written ? "true" : "false")
          << ",\"union_seconds\":" << union_seconds
          << ",\"cofactor_seconds\":" << cofactor_seconds
          << ",\"joint_cofactor_seconds\":" << joint_cofactor_seconds
          << ",\"masked_seconds\":" << masked_seconds
          << ",\"partition_audit_seconds\":"
          << partition_audit_seconds
          << ",\"heuristic_cofactor_seconds\":"
          << heuristic_cofactor_seconds << ",\"serialization_seconds\":"
          << serialization_seconds << ",\"output_seconds\":"
          << output_seconds << ",\"solved\":"
          << (done_written ? "true" : "false") << "}";
    serialization_seconds += serialization_timer();
    write_payload(event.str());
    out.flush();
}
}
