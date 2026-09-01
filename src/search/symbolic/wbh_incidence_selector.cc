#include "wbh_incidence_selector.h"

#include "sym_variables.h"

#include "../utils/system.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <iomanip>
#include <limits>
#include <sstream>
#include <unordered_map>
#include <vector>

using namespace std;

namespace symbolic {
namespace {
long checked_add(long left, long right, const string &label) {
    if (right > 0 && left > numeric_limits<long>::max() - right) {
        ABORT("WBH incidence selector " + label + " overflow.");
    }
    return left + right;
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

void append_long_vector(ostringstream &out, const vector<long> &values) {
    out << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i) {
            out << ",";
        }
        out << values[i];
    }
    out << "]";
}

long terminal_incidence(
    SymVariables *vars, const BDD &layer, const ADD &heuristic) {
    if (layer.IsZero()) {
        ABORT("WBH incidence selector received an empty completed layer.");
    }
    ADD bottom = vars->constant(-1);
    DdNode *bottom_node = bottom.getNode();
    ADD masked = layer.Add().Ite(heuristic, bottom);
    if (Cudd_IsComplement(masked.getNode())) {
        ABORT("WBH incidence selector masked ADD has a complemented root.");
    }

    unordered_map<DdNode *, size_t> node_ids;
    vector<DdNode *> nodes;
    vector<pair<size_t, size_t>> parent_edges;
    auto add_node = [&](DdNode *node) {
        auto [it, inserted] = node_ids.emplace(node, nodes.size());
        if (inserted) {
            nodes.push_back(node);
        }
        return it->second;
    };

    add_node(masked.getNode());
    long add_nodes = 0;
    vector<size_t> active_terminal_ids;
    for (size_t node_id = 0; node_id < nodes.size(); ++node_id) {
        DdNode *node = nodes[node_id];
        if (Cudd_IsComplement(node)) {
            ABORT("WBH incidence selector masked ADD has a complemented edge.");
        }
        if (Cudd_IsConstant(node)) {
            if (node != bottom_node) {
                const double value = Cudd_V(node);
                if (!isfinite(value) || value != round(value) || value < 0 ||
                    value > numeric_limits<int>::max()) {
                    ABORT(
                        "WBH incidence selector found an uncertified active "
                        "terminal.");
                }
                active_terminal_ids.push_back(node_id);
            }
            continue;
        }
        DdNode *then_node = Cudd_T(node);
        DdNode *else_node = Cudd_E(node);
        if (Cudd_IsComplement(then_node) || Cudd_IsComplement(else_node)) {
            ABORT("WBH incidence selector masked ADD has a complemented edge.");
        }
        size_t then_id = add_node(then_node);
        size_t else_id = add_node(else_node);
        parent_edges.emplace_back(then_id, node_id);
        parent_edges.emplace_back(else_id, node_id);
        add_nodes = checked_add(add_nodes, 1, "masked ADD node count");
    }
    if (active_terminal_ids.empty()) {
        ABORT("WBH incidence selector found no active terminal.");
    }

    vector<size_t> parent_offsets(nodes.size() + 1, 0);
    for (const auto &edge : parent_edges) {
        ++parent_offsets[edge.first + 1];
    }
    for (size_t i = 0; i < nodes.size(); ++i) {
        parent_offsets[i + 1] += parent_offsets[i];
    }
    vector<size_t> next_parent = parent_offsets;
    vector<size_t> parent_ids(parent_edges.size());
    for (const auto &[child, parent] : parent_edges) {
        parent_ids[next_parent[child]++] = parent;
    }

    long incidence = 0;
    vector<size_t> seen(nodes.size(), 0);
    vector<size_t> stack;
    size_t epoch = 0;
    for (size_t terminal_id : active_terminal_ids) {
        if (epoch == numeric_limits<size_t>::max()) {
            ABORT("WBH incidence selector traversal epoch overflow.");
        }
        ++epoch;
        stack.push_back(terminal_id);
        while (!stack.empty()) {
            size_t node_id = stack.back();
            stack.pop_back();
            if (seen[node_id] == epoch) {
                continue;
            }
            seen[node_id] = epoch;
            if (!Cudd_IsConstant(nodes[node_id])) {
                incidence = checked_add(
                    incidence, 1, "terminal-incidence certificate");
            }
            for (size_t pos = parent_offsets[node_id];
                 pos < parent_offsets[node_id + 1]; ++pos) {
                stack.push_back(parent_ids[pos]);
            }
        }
    }

    const long active_values = static_cast<long>(active_terminal_ids.size());
    if (active_values > 0 &&
        add_nodes > numeric_limits<long>::max() / active_values) {
        ABORT("WBH incidence selector product bound overflow.");
    }
    if (incidence < add_nodes || incidence > add_nodes * active_values) {
        ABORT("WBH incidence selector violates its exact product bounds.");
    }
    return incidence;
}

uint32_t rotate_right(uint32_t value, unsigned shift) {
    return (value >> shift) | (value << (32 - shift));
}

string sha256(const string &payload) {
    static constexpr array<uint32_t, 64> K = {
        0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b,
        0x59f111f1, 0x923f82a4, 0xab1c5ed5, 0xd807aa98, 0x12835b01,
        0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7,
        0xc19bf174, 0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc,
        0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da, 0x983e5152,
        0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147,
        0x06ca6351, 0x14292967, 0x27b70a85, 0x2e1b2138, 0x4d2c6dfc,
        0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
        0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819,
        0xd6990624, 0xf40e3585, 0x106aa070, 0x19a4c116, 0x1e376c08,
        0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f,
        0x682e6ff3, 0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208,
        0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2};
    vector<unsigned char> bytes(payload.begin(), payload.end());
    const uint64_t bit_length = static_cast<uint64_t>(bytes.size()) * 8;
    bytes.push_back(0x80);
    while (bytes.size() % 64 != 56) {
        bytes.push_back(0);
    }
    for (int shift = 56; shift >= 0; shift -= 8) {
        bytes.push_back(static_cast<unsigned char>(bit_length >> shift));
    }

    array<uint32_t, 8> hash = {
        0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a,
        0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19};
    for (size_t offset = 0; offset < bytes.size(); offset += 64) {
        array<uint32_t, 64> words{};
        for (size_t i = 0; i < 16; ++i) {
            const size_t pos = offset + 4 * i;
            words[i] = (static_cast<uint32_t>(bytes[pos]) << 24) |
                       (static_cast<uint32_t>(bytes[pos + 1]) << 16) |
                       (static_cast<uint32_t>(bytes[pos + 2]) << 8) |
                       static_cast<uint32_t>(bytes[pos + 3]);
        }
        for (size_t i = 16; i < 64; ++i) {
            uint32_t s0 = rotate_right(words[i - 15], 7) ^
                          rotate_right(words[i - 15], 18) ^
                          (words[i - 15] >> 3);
            uint32_t s1 = rotate_right(words[i - 2], 17) ^
                          rotate_right(words[i - 2], 19) ^
                          (words[i - 2] >> 10);
            words[i] = words[i - 16] + s0 + words[i - 7] + s1;
        }
        uint32_t a = hash[0];
        uint32_t b = hash[1];
        uint32_t c = hash[2];
        uint32_t d = hash[3];
        uint32_t e = hash[4];
        uint32_t f = hash[5];
        uint32_t g = hash[6];
        uint32_t h = hash[7];
        for (size_t i = 0; i < 64; ++i) {
            uint32_t sum1 = rotate_right(e, 6) ^ rotate_right(e, 11) ^
                            rotate_right(e, 25);
            uint32_t choice = (e & f) ^ ((~e) & g);
            uint32_t temp1 = h + sum1 + choice + K[i] + words[i];
            uint32_t sum0 = rotate_right(a, 2) ^ rotate_right(a, 13) ^
                            rotate_right(a, 22);
            uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
            uint32_t temp2 = sum0 + majority;
            h = g;
            g = f;
            f = e;
            e = d + temp1;
            d = c;
            c = b;
            b = a;
            a = temp1 + temp2;
        }
        hash[0] += a;
        hash[1] += b;
        hash[2] += c;
        hash[3] += d;
        hash[4] += e;
        hash[5] += f;
        hash[6] += g;
        hash[7] += h;
    }
    ostringstream out;
    out << hex << setfill('0');
    for (uint32_t word : hash) {
        out << setw(8) << word;
    }
    return out.str();
}
}

WbhIncidenceTrace::WbhIncidenceTrace(const string &path) {
    out.open(path);
    if (!out.is_open()) {
        ABORT("Could not open terminal-incidence selector trace: " + path);
    }
    write_event(
        "{\"event\":\"schema\",\"schema\":\"symbolic-search-heuristics/"
        "terminal-incidence-selector-trace/v3\",\"version\":3,"
        "\"probe_layers\":16,\"reference_cofactor_width_budget\":32,"
        "\"candidate_sources\":[\"empty\",\"bdd_prefix\","
        "\"goal_prefix\",\"goal_fill\",\"cegar\"],"
        "\"value_cap_grid\":[0,1,2,4,8,16,32,64,128,256,\"exact\"],"
        "\"pool_hash_encoding\":\"sources-pattern-states-feasible-lines-v1\","
        "\"preselection_hash_encoding\":\"candidate-structural-lines-v3\","
        "\"incidence_budget\":\"sum-first-16-completed-blind-layers-of-"
        "reference-v1\"}");
}

WbhIncidenceTrace::~WbhIncidenceTrace() {
    if (out.is_open()) {
        out.flush();
        out.close();
    }
}

void WbhIncidenceTrace::write_event(const string &payload) {
    out << payload << "\n";
    out.flush();
    if (!out) {
        ABORT("Could not write terminal-incidence selector trace.");
    }
}

WbhIncidenceProbe::WbhIncidenceProbe(
    SymVariables *vars, int target_layers)
    : vars(vars), target_layers(target_layers) {
    if (!vars || target_layers <= 0) {
        ABORT("WBH incidence probe requires variables and a positive target.");
    }
}

void WbhIncidenceProbe::prepare_layer(int g, const Bucket &pieces) {
    if (pending_layer || complete()) {
        ABORT("WBH incidence probe received an invalid layer preparation.");
    }
    BDD layer = vars->zeroBDD();
    for (const BDD &piece : pieces) {
        layer += piece;
    }
    if (layer.IsZero()) {
        ABORT("WBH incidence probe prepared an empty semantic layer.");
    }
    ++attempts;
    pending_g = g;
    pending_layer = make_unique<BDD>(move(layer));
}

void WbhIncidenceProbe::finish_layer(bool completed) {
    if (!pending_layer) {
        ABORT("WBH incidence probe has no pending prepared layer.");
    }
    if (completed) {
        if (!g_values.empty() && pending_g <= g_values.back()) {
            ABORT("WBH incidence probe completed non-increasing g-layers.");
        }
        g_values.push_back(pending_g);
        bdd_nodes.push_back(max(0, pending_layer->nodeCount() - 1));
        layers.push_back(move(*pending_layer));
    }
    pending_layer.reset();
    pending_g = -1;
}

bool WbhIncidenceProbe::complete() const {
    return static_cast<int>(layers.size()) == target_layers;
}

int WbhIncidenceProbe::get_target_layers() const {
    return target_layers;
}

int WbhIncidenceProbe::get_attempts() const {
    return attempts;
}

const vector<int> &WbhIncidenceProbe::get_g_values() const {
    return g_values;
}

const vector<long> &WbhIncidenceProbe::get_bdd_nodes() const {
    return bdd_nodes;
}

const vector<BDD> &WbhIncidenceProbe::get_layers() const {
    return layers;
}

void WbhIncidenceProbe::log_probe(
    WbhIncidenceTrace &trace, double cpu_seconds, double wall_seconds,
    int peak_memory_before_kb, int peak_memory_after_kb) const {
    ostringstream out;
    out << "{\"event\":\"probe\",\"target_layers\":" << target_layers
        << ",\"completed_layers\":" << layers.size()
        << ",\"attempts\":" << attempts << ",\"complete\":"
        << (complete() ? "true" : "false") << ",\"g_values\":";
    append_int_vector(out, g_values);
    out << ",\"bdd_nodes\":";
    append_long_vector(out, bdd_nodes);
    out << ",\"cpu_seconds\":" << cpu_seconds
        << ",\"wall_seconds\":" << wall_seconds
        << ",\"peak_memory_before_kb\":" << peak_memory_before_kb
        << ",\"peak_memory_after_kb\":" << peak_memory_after_kb
        << ",\"peak_memory_delta_kb\":"
        << max(0, peak_memory_after_kb - peak_memory_before_kb) << "}";
    trace.write_event(out.str());
}

WbhIncidenceMeasurement measure_terminal_incidence(
    SymVariables *vars, const vector<BDD> &layers, const ADD &heuristic) {
    if (!vars || !heuristic.getNode() || layers.empty()) {
        ABORT("WBH incidence measurement received incomplete inputs.");
    }
    WbhIncidenceMeasurement result{{}, 0};
    result.by_layer.reserve(layers.size());
    for (const BDD &layer : layers) {
        long incidence = terminal_incidence(vars, layer, heuristic);
        result.by_layer.push_back(incidence);
        result.total = checked_add(
            result.total, incidence, "multi-layer terminal incidence");
    }
    return result;
}

string wbh_sha256_hex(const string &payload) {
    return sha256(payload);
}
}
