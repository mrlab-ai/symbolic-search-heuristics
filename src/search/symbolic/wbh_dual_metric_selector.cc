#include "wbh_dual_metric_selector.h"

#include "sym_variables.h"

#include "../utils/system.h"

#include <algorithm>
#include <limits>
#include <sstream>

using namespace std;

namespace symbolic {
namespace {
long checked_add(long left, long right, const string &label) {
    if (right > 0 && left > numeric_limits<long>::max() - right) {
        ABORT("WBH dual selector " + label + " overflow.");
    }
    return left + right;
}

long checked_multiply(long left, long right, const string &label) {
    if (left < 0 || right < 0 ||
        (right && left > numeric_limits<long>::max() / right)) {
        ABORT("WBH dual selector " + label + " overflow.");
    }
    return left * right;
}

void append_int_vector(ostringstream &out, const vector<int> &values) {
    out << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i) {
            out << ",";
        }
        out << values[i];
    }
    out << "]";
}
}

WbhDualMetricTrace::WbhDualMetricTrace(
    const string &path, const WbhStateCutCertificate &certificate) {
    const size_t state_bits = certificate.cudd_indices.size();
    if (certificate.manager_variables < 0 ||
        state_bits != certificate.cudd_levels.size() ||
        state_bits != certificate.fd_variables.size() ||
        state_bits != certificate.fd_bit_positions.size()) {
        ABORT("Terminal dual-metric trace received an invalid certificate.");
    }
    for (size_t bit = 0; bit < state_bits; ++bit) {
        if (certificate.cudd_indices[bit] < 0 ||
            certificate.cudd_indices[bit] >=
                certificate.manager_variables ||
            certificate.cudd_levels[bit] < 0 ||
            certificate.cudd_levels[bit] >=
                certificate.manager_variables ||
            certificate.fd_variables[bit] < 0 ||
            certificate.fd_bit_positions[bit] < 0 ||
            (bit &&
             certificate.cudd_levels[bit - 1] >=
                 certificate.cudd_levels[bit])) {
            ABORT(
                "Terminal dual-metric trace received an invalid state-bit "
                "mapping.");
        }
    }
    out.open(path);
    if (!out.is_open()) {
        ABORT("Could not open terminal dual-metric selector trace: " + path);
    }
    write_event(
        "{\"event\":\"schema\",\"schema\":\"symbolic-search-heuristics/"
        "terminal-dual-metric-selector-trace/v2\",\"version\":2,"
        "\"probe_layers\":16,\"reference_cofactor_width_budget\":32,"
        "\"candidate_sources\":[\"empty\",\"bdd_prefix\","
        "\"goal_prefix\",\"goal_fill\",\"cegar\"],"
        "\"value_cap_grid\":[0,1,2,4,8,16,32,64,128,256,\"exact\"],"
        "\"cut_convention\":\"unprimed_state_bits_in_cudd_level_order_"
        "including_terminal_cut_but_excluding_terminal_from_sums\","
        "\"joint_residual_identity\":\"cooccurring_signed_bdd_and_regular_"
        "add_pointer_pair\","
        "\"active_terminal_semantics\":\"finite_values_plus_semantic_dead_"
        "end_excluding_fresh_bottom\","
        "\"incidence_budget\":\"sum-first-16-completed-blind-layers-of-"
        "reference-v1\","
        "\"masked_joint_budget\":\"sum-active-terminal-count-times-joint-"
        "cofactor-sum-excluding-terminal-cut-of-reference-v1\","
        "\"pool_hash_encoding\":\"sources-pattern-states-feasible-lines-v1\","
        "\"state_profile_hash_encoding\":\"layer-g-bdd-nodes-cofactor-"
        "counts-lines-v1\","
        "\"preselection_hash_encoding\":\"dual-candidate-structural-lines-v2\","
        "\"incidence_raw_certificate\":\"breadth-first-regular-masked-add-"
        "dag-node-kinds-children-terminal-values-v1\","
        "\"incidence_projection_hash_encoding\":\"candidate-structural-lines-v3\","
        "\"required_invariants\":[\"exactly-16-completed-probe-layers\","
        "\"raw-terminal-ancestor-incidence-replay\","
        "\"joint-projection-and-product-bounds\","
        "\"terminal-cut-excluded-from-joint-cofactor-sums\","
        "\"semantic-dead-end-agrees-with-numeric-sentinel\","
        "\"cap-refinement-monotonicity\","
        "\"common-K32-reference-feasible-under-both-derived-budgets\","
        "\"identical-I-and-mJ-measurement-work-in-all-three-modes\"]}");

    ostringstream event;
    event << "{\"event\":\"variable_order\",\"manager_variables\":"
          << certificate.manager_variables << ",\"state_bits\":"
          << certificate.cudd_indices.size() << ",\"cudd_indices\":";
    append_int_vector(event, certificate.cudd_indices);
    event << ",\"cudd_levels\":";
    append_int_vector(event, certificate.cudd_levels);
    event << ",\"fd_variables\":";
    append_int_vector(event, certificate.fd_variables);
    event << ",\"fd_bit_positions\":";
    append_int_vector(event, certificate.fd_bit_positions);
    event << "}";
    write_event(event.str());
}

WbhDualMetricTrace::~WbhDualMetricTrace() {
    if (out.is_open()) {
        out.flush();
        out.close();
    }
}

void WbhDualMetricTrace::write_event(const string &payload) {
    out << payload << "\n";
    out.flush();
    if (!out) {
        ABORT("Could not write terminal dual-metric selector trace.");
    }
}

vector<vector<long>> compute_wbh_probe_state_profiles(
    SymVariables *vars, const vector<BDD> &layers,
    const WbhStateCutCertificate &certificate) {
    if (!vars || layers.empty()) {
        ABORT("WBH dual selector received incomplete probe layers.");
    }
    verify_wbh_state_cut_certificate(vars, certificate);
    vector<vector<long>> profiles;
    profiles.reserve(layers.size());
    for (const BDD &layer : layers) {
        if (layer.IsZero()) {
            ABORT("WBH dual selector received an empty completed probe layer.");
        }
        profiles.push_back(compute_wbh_bdd_cofactor_profile(
            vars->getCudd()->getManager(), layer, certificate.cudd_indices,
            certificate.cudd_levels));
    }
    return profiles;
}

WbhDualMetricMeasurement measure_wbh_dual_metrics(
    SymVariables *vars, const vector<BDD> &layers, const ADD &heuristic,
    const BDD &dead_ends, int dead_end_value,
    const WbhStateCutCertificate &certificate,
    const vector<vector<long>> &state_profiles,
    const vector<long> &heuristic_profile) {
    if (!vars || !heuristic.getNode() || layers.empty() ||
        layers.size() != state_profiles.size() ||
        heuristic_profile.size() != certificate.cudd_indices.size() + 1 ||
        (dead_ends.IsZero() ? dead_end_value != -1 : dead_end_value < 0)) {
        ABORT("WBH dual selector measurement received inconsistent inputs.");
    }
    verify_wbh_state_cut_certificate(vars, certificate);

    WbhDualMetricMeasurement result{{{}, 0}, {}, 0, 0};
    result.incidence.by_layer.reserve(layers.size());
    result.layers.reserve(layers.size());
    for (size_t layer_index = 0; layer_index < layers.size(); ++layer_index) {
        const BDD &layer = layers[layer_index];
        const vector<long> &state_profile = state_profiles[layer_index];
        if (state_profile.size() != heuristic_profile.size()) {
            ABORT("WBH dual selector profile dimensions disagree.");
        }
        WbhIncidenceLayerMeasurement incidence =
            measure_terminal_incidence_layer(vars, layer, heuristic);
        vector<long> joint = compute_wbh_joint_cofactor_profile(
            vars->getCudd()->getManager(), layer, heuristic,
            certificate.cudd_indices, certificate.cudd_levels);
        if (joint.size() != state_profile.size()) {
            ABORT("WBH dual selector joint profile dimension changed.");
        }
        long joint_sum = 0;
        for (size_t cut = 0; cut < joint.size(); ++cut) {
            const long state_count = state_profile[cut];
            const long heuristic_count = heuristic_profile[cut];
            const long joint_count = joint[cut];
            if (state_count < 1 || heuristic_count < 1 || joint_count < 1 ||
                joint_count < max(state_count, heuristic_count) ||
                static_cast<__int128_t>(joint_count) >
                    static_cast<__int128_t>(state_count) * heuristic_count) {
                ABORT("WBH dual selector joint profile violates its bounds.");
            }
            if (cut + 1 < joint.size()) {
                joint_sum = checked_add(
                    joint_sum, joint_count, "joint cofactor sum");
            }
        }

        const bool dead_end_active = !dead_ends.IsZero() &&
                                     !(layer * dead_ends).IsZero();
        vector<int> active_finite_values = incidence.active_terminal_values;
        auto dead_it = lower_bound(
            active_finite_values.begin(), active_finite_values.end(),
            dead_end_value);
        const bool sentinel_active =
            dead_end_value >= 0 && dead_it != active_finite_values.end() &&
            *dead_it == dead_end_value;
        if (sentinel_active != dead_end_active) {
            ABORT(
                "WBH dual selector numeric dead-end sentinel disagrees with "
                "semantic dead-end reachability.");
        }
        if (sentinel_active) {
            active_finite_values.erase(dead_it);
        }
        const size_t active_size =
            active_finite_values.size() + (dead_end_active ? 1 : 0);
        if (active_size == 0 ||
            active_size > static_cast<size_t>(numeric_limits<int>::max())) {
            ABORT("WBH dual selector active-terminal count is invalid.");
        }
        const int active_terminal_count = static_cast<int>(active_size);
        if (incidence.masked_add_nodes > joint_sum) {
            ABORT(
                "WBH dual selector masked ADD nodes exceed the joint profile.");
        }
        const long masked_joint = checked_multiply(
            active_terminal_count, joint_sum, "masked joint certificate");
        if (incidence.terminal_incidence > masked_joint) {
            ABORT(
                "WBH dual selector incidence exceeds the masked joint "
                "certificate.");
        }

        result.incidence.by_layer.push_back(incidence.terminal_incidence);
        result.incidence.total = checked_add(
            result.incidence.total, incidence.terminal_incidence,
            "multi-layer terminal incidence");
        result.masked_joint_total = checked_add(
            result.masked_joint_total, masked_joint,
            "multi-layer masked joint certificate");
        result.joint_cut_entries = checked_add(
            result.joint_cut_entries, static_cast<long>(joint.size()),
            "joint cut-entry count");
        result.layers.push_back({
            incidence.masked_add_nodes, move(active_finite_values),
            dead_end_active, active_terminal_count, move(joint), joint_sum,
            masked_joint, move(incidence.certificate_node_kinds),
            move(incidence.certificate_then_children),
            move(incidence.certificate_else_children),
            move(incidence.certificate_terminal_values)});
    }
    return result;
}
}
