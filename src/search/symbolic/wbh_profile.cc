#include "wbh_profile.h"

#include "closed_list.h"
#include "sym_variables.h"
#include "wbh_add_stats.h"

#include "../utils/system.h"
#include "../utils/timer.h"

#include <algorithm>
#include <sstream>
#include <tuple>
#include <unordered_set>

using namespace std;

namespace symbolic {
namespace {
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
        "{\"event\":\"schema\",\"version\":1,"
        "\"cut_convention\":\"unprimed_state_bits_in_cudd_level_order_"
        "including_terminal\","
        "\"node_count_convention\":\"regular_cudd_inner_nodes_of_semantic_"
        "union\","
        "\"residual_identity\":\"canonical_signed_cudd_pointer_with_"
        "complement_polarity\"}");
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

void WbhProfile::log_heuristic(
    SymVariables *vars, const AddStats &add_stats) {
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
    const long nodes = max(0, layer.nodeCount() - 1);
    const long width = *max_element(profile.begin(), profile.end());

    union_seconds += event_union_seconds;
    cofactor_seconds += event_cofactor_seconds;

    pending_layer = make_unique<PendingLayer>(PendingLayer{
        g, static_cast<int>(pieces.size()), nodes, move(profile), width,
        event_union_seconds, event_cofactor_seconds});
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
        forward_layers.push_back({layer.g, layer.bdd_nodes});
    }

    utils::Timer serialization_timer;
    ostringstream event;
    event << "{\"event\":\"layer_profile\",\"g\":" << layer.g
          << ",\"completed\":" << (completed ? "true" : "false")
          << ",\"piece_count\":" << layer.piece_count
          << ",\"bdd_nodes\":" << layer.bdd_nodes
          << ",\"cofactor_counts\":";
    append_long_vector(event, layer.cofactor_counts);
    event << ",\"cofactor_width\":" << layer.cofactor_width
          << ",\"union_seconds\":" << layer.union_seconds
          << ",\"cofactor_seconds\":" << layer.cofactor_seconds << "}";
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
    for (const LayerRecord &record : forward_layers) {
        if (record.g < solution_cost) {
            effort += record.bdd_nodes;
        }
    }

    utils::Timer serialization_timer;
    ostringstream event;
    event << "{\"event\":\"done\",\"layer_union_effort\":" << effort
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
