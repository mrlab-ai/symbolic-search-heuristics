#include "wbh_pdb_levels.h"

#include "wbh_add_stats.h"
#include "wbh_cofactor_profiles.h"
#include "wbh_dual_metric_selector.h"
#include "wbh_incidence_selector.h"
#include "wbh_stats.h"

#include "../pdbs/pattern_database.h"
#include "../pdbs/pattern_database_factory.h"
#include "../pdbs/pattern_generator_cegar.h"
#include "../pdbs/pattern_information.h"
#include "../pdbs/types.h"
#include "../task_utils/variable_order_finder.h"
#include "../utils/logging.h"
#include "../utils/system.h"

#include <algorithm>
#include <chrono>
#include <cstdint>
#include <limits>
#include <map>
#include <sstream>
#include <utility>

using namespace std;

namespace symbolic {
namespace {
const char *const WIDTH_SELECTOR_PROTOCOL = "fixed_pool_v1";
const char *const WIDTH_SELECTOR_SCORE =
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1";
const char *const CAPPED_WIDTH_SELECTOR_PROTOCOL = "fixed_pool_value_cap_v2";
const char *const CAPPED_WIDTH_SELECTOR_SCORE =
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_value_cap_v2";
const char *const CAP_GRID_SELECTOR_PROTOCOL = "fixed_pool_cap_grid_v6";
const char *const CAP_GRID_SELECTOR_SCORE =
    "per_pattern_strongest_feasible_cap_then_"
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1";
const char *const ADD_SELECTOR_PROTOCOL = "fixed_pool_total_add_v1";
const char *const CAPPED_ADD_SELECTOR_PROTOCOL =
    "fixed_pool_total_add_value_cap_v1";
const char *const ADD_CAP_GRID_SELECTOR_PROTOCOL =
    "fixed_pool_total_add_cap_grid_v1";
const char *const INCIDENCE_SELECTOR_PROTOCOL =
    "terminal_incidence_fixed_pool_v1";
const char *const INCIDENCE_SELECTOR_SCORE =
    "strongest_incidence_feasible_cap_then_"
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1";
const char *const DUAL_SELECTOR_PROTOCOL =
    "terminal_dual_metric_fixed_pool_v1";
const char *const DUAL_SELECTOR_SCORE =
    "strongest_metric_feasible_cap_then_"
    "init_dead_init_h_mean_dead_fraction_width_states_pattern_v1";
const int INCIDENCE_REFERENCE_WIDTH_BUDGET = 32;

struct CandidateSpec {
    vector<int> pattern;
    vector<string> sources;
    int abstract_states;
    bool within_state_budget;
    shared_ptr<pdbs::PatternDatabase> pdb;
};

struct MaterializedCandidate {
    vector<int> pattern;
    vector<string> sources;
    shared_ptr<pdbs::PatternDatabase> pdb;
    map<int, BDD> level_sets;
    BDD dead_ends;
    ADD h_add;
    AddStats add_stats;
    int abstract_states = 0;
    bool initial_dead_end = false;
    int initial_h = 0;
    int64_t finite_sum = 0;
    int finite_count = 0;
    int dead_count = 0;
    int dead_end_value = -1;
    int value_cap = -1;
    map<int, int> finite_value_counts;
    string raw_value_histogram;
    long raw_add_nodes = 0;
    int raw_num_terminals = 0;
    long raw_cofactor_width = 0;
    long raw_width_upper_bound = 0;
    int raw_num_values = 0;
    int raw_max_finite_value = 0;
    int64_t raw_finite_sum = 0;
    int raw_finite_count = 0;
    int raw_dead_count = 0;
    bool raw_initial_dead_end = false;
    int raw_initial_h = 0;
    int raw_initial_value_count = 0;

    explicit MaterializedCandidate(SymVariables *vars)
        : dead_ends(vars->zeroBDD()), h_add(vars->constant(0)) {
    }
};

struct DualMetricVariant {
    size_t pattern_index;
    int value_cap;
    unique_ptr<MaterializedCandidate> candidate;
    vector<long> heuristic_state_profile;
    WbhDualMetricMeasurement measurement;
    bool reference_feasible;
    bool incidence_feasible = false;
    bool masked_joint_feasible = false;
    bool incidence_retained_for_pattern = false;
    bool masked_joint_retained_for_pattern = false;
};

string encode_raw_value_histogram(const map<int, int> &value_counts);

vector<int> normalized_pattern(vector<int> pattern) {
    sort(pattern.begin(), pattern.end());
    pattern.erase(unique(pattern.begin(), pattern.end()), pattern.end());
    return pattern;
}

int64_t abstract_state_count(
    const TaskProxy &task_proxy, const vector<int> &pattern) {
    int64_t count = 1;
    for (int var : pattern) {
        int domain_size =
            task_proxy.get_variables()[var].get_domain_size();
        if (count > numeric_limits<int64_t>::max() / domain_size) {
            ABORT("PDB width-selector abstract-state count overflow.");
        }
        count *= domain_size;
    }
    return count;
}

vector<int> budgeted_pattern(
    const TaskProxy &task_proxy, const vector<int> &variable_order,
    int state_budget, bool skip_oversized) {
    vector<int> result;
    int64_t product = 1;
    for (int var : variable_order) {
        int domain_size =
            task_proxy.get_variables()[var].get_domain_size();
        if (product > state_budget / domain_size) {
            if (skip_oversized) {
                continue;
            }
            break;
        }
        product *= domain_size;
        result.push_back(var);
    }
    return normalized_pattern(move(result));
}

vector<CandidateSpec> build_fixed_candidate_pool(
    SymVariables *vars, const shared_ptr<AbstractTask> &task,
    const TaskProxy &task_proxy, int state_budget, double cegar_max_time,
    int cegar_seed, int cegar_max_refinements, bool cap_grid) {
    vector<CandidateSpec> specs;
    map<vector<int>, size_t> spec_by_pattern;
    auto add_spec = [&](const string &source, vector<int> candidate_pattern,
                        shared_ptr<pdbs::PatternDatabase> pdb = nullptr) {
        if (cap_grid) {
            // Domain-one variables carry no information. Removing them is
            // semantics preserving and, together with the PDB state bound,
            // bounds every logged pattern independently of task syntax.
            candidate_pattern.erase(
                remove_if(
                    candidate_pattern.begin(), candidate_pattern.end(),
                    [&](int var) {
                        return task_proxy.get_variables()[var].get_domain_size()
                               == 1;
                    }),
                candidate_pattern.end());
        }
        candidate_pattern = normalized_pattern(move(candidate_pattern));
        int64_t states = abstract_state_count(task_proxy, candidate_pattern);
        if (states > numeric_limits<int>::max()) {
            ABORT(
                "PDB fixed-pool candidate exceeds the projection index "
                "range.");
        }
        auto [it, inserted] =
            spec_by_pattern.emplace(candidate_pattern, specs.size());
        if (inserted) {
            specs.push_back(
                {move(candidate_pattern), {source}, static_cast<int>(states),
                 states <= state_budget, move(pdb)});
        } else {
            CandidateSpec &existing = specs[it->second];
            existing.sources.push_back(source);
            if (pdb && !existing.pdb) {
                existing.pdb = move(pdb);
            }
        }
    };

    // Insertion order is part of both fixed-pool selector protocols.
    add_spec("empty", {});
    add_spec(
        "bdd_prefix",
        budgeted_pattern(
            task_proxy, vars->get_var_order(), state_budget,
            /*skip_oversized=*/false));

    vector<int> goal_order;
    variable_order_finder::VariableOrderFinder order(
        task_proxy, variable_order_finder::GOAL_CG_LEVEL);
    while (!order.done()) {
        goal_order.push_back(order.next());
    }
    add_spec(
        "goal_prefix",
        budgeted_pattern(
            task_proxy, goal_order, state_budget,
            /*skip_oversized=*/false));
    add_spec(
        "goal_fill",
        budgeted_pattern(
            task_proxy, goal_order, state_budget,
            /*skip_oversized=*/true));

    if (task_proxy.get_goals().size() > 0) {
        pdbs::PatternGeneratorCEGAR generator(
            state_budget, cegar_max_time, cegar_max_refinements,
            /*use_wildcard_plans=*/true, cegar_seed,
            utils::Verbosity::NORMAL, /*exit_on_unsolvable=*/false);
        pdbs::PatternInformation info = generator.generate(task);
        vector<int> cegar_pattern = info.get_pattern();
        shared_ptr<pdbs::PatternDatabase> cegar_pdb = info.get_pdb();
        add_spec("cegar", move(cegar_pattern), move(cegar_pdb));
    } else {
        add_spec("cegar", {});
    }
    return specs;
}

void compute_candidate_add_stats(
    SymVariables *vars, MaterializedCandidate &candidate) {
    // Score the exact same total ADD that the winning heuristic reports.
    ADD h_add = vars->constant(0);
    for (const auto &[distance, level] : candidate.level_sets) {
        h_add += level.Add() * vars->constant(distance);
    }
    if (!candidate.dead_ends.IsZero()) {
        vector<int> terminals = collect_integer_leaf_values(h_add);
        double infinity_marker =
            static_cast<double>(terminals.back()) + 1.0;
        if (infinity_marker > numeric_limits<int>::max()) {
            ABORT("PDB dead-end terminal value exceeds the integer range.");
        }
        candidate.dead_end_value = static_cast<int>(infinity_marker);
        h_add = candidate.dead_ends.Add().Ite(
            vars->constant(infinity_marker), h_add);
    }
    candidate.h_add = h_add;
    candidate.add_stats = compute_add_stats(
        vars, h_add, static_cast<int>(candidate.level_sets.size()));
}

unique_ptr<MaterializedCandidate> materialize_raw_candidate(
    SymVariables *vars, const TaskProxy &task_proxy,
    const CandidateSpec &spec) {
    auto candidate =
        unique_ptr<MaterializedCandidate>(new MaterializedCandidate(vars));
    candidate->pattern = spec.pattern;
    candidate->sources = spec.sources;
    candidate->pdb = spec.pdb;
    if (!candidate->pdb) {
        candidate->pdb = pdbs::compute_pdb(task_proxy, candidate->pattern);
    }

    pdbs::Projection projection(task_proxy, candidate->pattern);
    candidate->abstract_states = projection.get_num_abstract_states();
    if (candidate->abstract_states != spec.abstract_states) {
        ABORT("PDB width-selector abstract-state count mismatch.");
    }
    int num_vars = task_proxy.get_variables().size();
    for (int index = 0; index < candidate->abstract_states; ++index) {
        vector<int> state(num_vars, 0);
        BDD abstract_state = vars->oneBDD();
        for (size_t pos = 0; pos < candidate->pattern.size(); ++pos) {
            int var = candidate->pattern[pos];
            int value = projection.unrank(index, pos);
            state[var] = value;
            abstract_state *= vars->preBDD(var, value);
        }
        int distance = candidate->pdb->get_value(state);
        if (distance == numeric_limits<int>::max()) {
            candidate->dead_ends += abstract_state;
            ++candidate->dead_count;
        } else {
            auto it = candidate->level_sets.find(distance);
            if (it == candidate->level_sets.end()) {
                candidate->level_sets[distance] = abstract_state;
            } else {
                it->second += abstract_state;
            }
            candidate->finite_sum += distance;
            ++candidate->finite_count;
            ++candidate->finite_value_counts[distance];
        }
    }

    State initial_state = task_proxy.get_initial_state();
    initial_state.unpack();
    candidate->initial_h =
        candidate->pdb->get_value(initial_state.get_unpacked_values());
    candidate->initial_dead_end =
        candidate->initial_h == numeric_limits<int>::max();
    compute_candidate_add_stats(vars, *candidate);
    candidate->raw_add_nodes = candidate->add_stats.add_inner_nodes;
    candidate->raw_num_terminals = candidate->add_stats.num_terminals;
    candidate->raw_cofactor_width = candidate->add_stats.cofactor_width;
    candidate->raw_width_upper_bound = candidate->add_stats.width_upper_bound;
    candidate->raw_num_values = static_cast<int>(candidate->level_sets.size());
    candidate->raw_max_finite_value = candidate->level_sets.empty()
                                          ? 0
                                          : candidate->level_sets.rbegin()->first;
    candidate->raw_finite_sum = candidate->finite_sum;
    candidate->raw_finite_count = candidate->finite_count;
    candidate->raw_dead_count = candidate->dead_count;
    candidate->raw_initial_dead_end = candidate->initial_dead_end;
    candidate->raw_initial_h = candidate->initial_h;
    return candidate;
}

unique_ptr<MaterializedCandidate> cap_candidate(
    SymVariables *vars, const MaterializedCandidate &raw, int value_cap) {
    if (value_cap < 0) {
        ABORT("cap_candidate requires a nonnegative value cap.");
    }
    auto candidate =
        unique_ptr<MaterializedCandidate>(new MaterializedCandidate(vars));
    candidate->pattern = raw.pattern;
    candidate->sources = raw.sources;
    candidate->pdb = raw.pdb;
    candidate->dead_ends = raw.dead_ends;
    candidate->abstract_states = raw.abstract_states;
    candidate->initial_dead_end = raw.initial_dead_end;
    candidate->initial_h = raw.initial_dead_end
                               ? raw.initial_h
                               : min(raw.initial_h, value_cap);
    candidate->dead_count = raw.dead_count;
    candidate->value_cap = value_cap;
    candidate->raw_add_nodes = raw.raw_add_nodes;
    candidate->raw_num_terminals = raw.raw_num_terminals;
    candidate->raw_cofactor_width = raw.raw_cofactor_width;
    candidate->raw_width_upper_bound = raw.raw_width_upper_bound;
    candidate->raw_num_values = raw.raw_num_values;
    candidate->raw_max_finite_value = raw.raw_max_finite_value;
    candidate->raw_finite_sum = raw.raw_finite_sum;
    candidate->raw_finite_count = raw.raw_finite_count;
    candidate->raw_dead_count = raw.raw_dead_count;
    candidate->raw_initial_dead_end = raw.raw_initial_dead_end;
    candidate->raw_initial_h = raw.raw_initial_h;
    candidate->raw_initial_value_count = raw.raw_initial_value_count;
    candidate->raw_value_histogram = raw.raw_value_histogram;
    for (const auto &[distance, level] : raw.level_sets) {
        int value = min(distance, value_cap);
        auto it = candidate->level_sets.find(value);
        if (it == candidate->level_sets.end()) {
            candidate->level_sets[value] = level;
        } else {
            it->second += level;
        }
        int count = raw.finite_value_counts.at(distance);
        candidate->finite_sum += static_cast<int64_t>(value) * count;
        candidate->finite_count += count;
        candidate->finite_value_counts[value] += count;
    }
    compute_candidate_add_stats(vars, *candidate);
    return candidate;
}

unique_ptr<MaterializedCandidate> materialize_candidate(
    SymVariables *vars, const TaskProxy &task_proxy,
    const CandidateSpec &spec, int value_cap) {
    unique_ptr<MaterializedCandidate> raw =
        materialize_raw_candidate(vars, task_proxy, spec);
    if (value_cap < 0) {
        return raw;
    }
    return cap_candidate(vars, *raw, value_cap);
}

const vector<int> CAP_GRID = {0, 1, 2, 4, 8, 16, 32, 64, 128, 256};

vector<int> cap_grid_for_max(int max_finite_value) {
    vector<int> caps;
    for (int cap : CAP_GRID) {
        // Caps at or above the maximum finite value equal the exact transform.
        if (cap < max_finite_value) {
            caps.push_back(cap);
        }
    }
    caps.push_back(-1);
    return caps;
}

const char BASE64URL_ALPHABET[] =
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";

void append_unsigned_varint(vector<unsigned char> &bytes, uint64_t value) {
    do {
        unsigned char byte = value & 0x7f;
        value >>= 7;
        bytes.push_back(byte | (value ? 0x80 : 0));
    } while (value);
}

string base64url_without_padding(const vector<unsigned char> &bytes) {
    string result;
    result.reserve((bytes.size() * 4 + 2) / 3);
    size_t index = 0;
    while (index + 3 <= bytes.size()) {
        uint32_t chunk = (static_cast<uint32_t>(bytes[index]) << 16) |
                         (static_cast<uint32_t>(bytes[index + 1]) << 8) |
                         bytes[index + 2];
        result.push_back(BASE64URL_ALPHABET[(chunk >> 18) & 63]);
        result.push_back(BASE64URL_ALPHABET[(chunk >> 12) & 63]);
        result.push_back(BASE64URL_ALPHABET[(chunk >> 6) & 63]);
        result.push_back(BASE64URL_ALPHABET[chunk & 63]);
        index += 3;
    }
    size_t remaining = bytes.size() - index;
    if (remaining == 1) {
        uint32_t chunk = static_cast<uint32_t>(bytes[index]) << 16;
        result.push_back(BASE64URL_ALPHABET[(chunk >> 18) & 63]);
        result.push_back(BASE64URL_ALPHABET[(chunk >> 12) & 63]);
    } else if (remaining == 2) {
        uint32_t chunk = (static_cast<uint32_t>(bytes[index]) << 16) |
                         (static_cast<uint32_t>(bytes[index + 1]) << 8);
        result.push_back(BASE64URL_ALPHABET[(chunk >> 18) & 63]);
        result.push_back(BASE64URL_ALPHABET[(chunk >> 12) & 63]);
        result.push_back(BASE64URL_ALPHABET[(chunk >> 6) & 63]);
    }
    return result;
}

string encode_raw_value_histogram(const map<int, int> &value_counts) {
    // The exact finite-value census is logged once per raw pattern. Sorted
    // distance deltas and positive counts use canonical unsigned varints,
    // followed by unpadded base64url. With at most 100,000 abstract states,
    // the encoded payload is bounded independently of the distances' values.
    vector<unsigned char> bytes;
    bytes.reserve(value_counts.size() * 4);
    append_unsigned_varint(bytes, value_counts.size());
    int64_t previous = -1;
    for (const auto &[distance, count] : value_counts) {
        if (distance < 0 || count <= 0 || distance <= previous) {
            ABORT("PDB cap-grid raw value histogram is invalid.");
        }
        append_unsigned_varint(
            bytes, static_cast<uint64_t>(distance - previous));
        append_unsigned_varint(bytes, static_cast<uint64_t>(count));
        previous = distance;
    }
    return base64url_without_padding(bytes);
}

vector<int> distinct_cap_grid(const MaterializedCandidate &raw) {
    return cap_grid_for_max(raw.raw_max_finite_value);
}

int compare_ratio(
    int64_t lhs_num, int64_t lhs_den, int64_t rhs_num,
    int64_t rhs_den, bool zero_denominator_is_infinity) {
    if (zero_denominator_is_infinity &&
        (lhs_den == 0 || rhs_den == 0)) {
        if (lhs_den == rhs_den) {
            return 0;
        }
        return lhs_den == 0 ? 1 : -1;
    }
    __int128_t lhs = static_cast<__int128_t>(lhs_num) * rhs_den;
    __int128_t rhs = static_cast<__int128_t>(rhs_num) * lhs_den;
    if (lhs == rhs) {
        return 0;
    }
    return lhs > rhs ? 1 : -1;
}

bool candidate_is_better(
    const MaterializedCandidate &candidate,
    const MaterializedCandidate &incumbent) {
    if (candidate.initial_dead_end != incumbent.initial_dead_end) {
        return candidate.initial_dead_end;
    }
    if (!candidate.initial_dead_end &&
        candidate.initial_h != incumbent.initial_h) {
        return candidate.initial_h > incumbent.initial_h;
    }
    int mean_comparison = compare_ratio(
        candidate.finite_sum, candidate.finite_count,
        incumbent.finite_sum, incumbent.finite_count,
        /*zero_denominator_is_infinity=*/true);
    if (mean_comparison != 0) {
        return mean_comparison > 0;
    }
    int dead_fraction_comparison = compare_ratio(
        candidate.dead_count, candidate.abstract_states,
        incumbent.dead_count, incumbent.abstract_states,
        /*zero_denominator_is_infinity=*/false);
    if (dead_fraction_comparison != 0) {
        return dead_fraction_comparison > 0;
    }
    if (candidate.add_stats.cofactor_width !=
        incumbent.add_stats.cofactor_width) {
        return candidate.add_stats.cofactor_width <
               incumbent.add_stats.cofactor_width;
    }
    if (candidate.abstract_states != incumbent.abstract_states) {
        return candidate.abstract_states < incumbent.abstract_states;
    }
    return candidate.pattern < incumbent.pattern;
}

bool uses_total_add_budget(int total_add_node_budget) {
    return total_add_node_budget != numeric_limits<int>::max();
}

bool candidate_is_feasible(
    const MaterializedCandidate &candidate, int cofactor_width_budget,
    int total_add_node_budget) {
    if (uses_total_add_budget(total_add_node_budget)) {
        return candidate.add_stats.width_upper_bound <= total_add_node_budget;
    }
    return candidate.add_stats.cofactor_width <= cofactor_width_budget;
}

const char *budget_rejection_reason(int total_add_node_budget) {
    return uses_total_add_budget(total_add_node_budget)
               ? "total_add_node_budget"
               : "cofactor_width_budget";
}

void append_string_array(ostringstream &out, const vector<string> &values) {
    out << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            out << ",";
        }
        // All values are fixed selector source labels containing only [a-z_].
        out << "\"" << values[i] << "\"";
    }
    out << "]";
}

void append_int_array(ostringstream &out, const vector<int> &values) {
    out << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            out << ",";
        }
        out << values[i];
    }
    out << "]";
}

void append_long_array(ostringstream &out, const vector<long> &values) {
    out << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            out << ",";
        }
        out << values[i];
    }
    out << "]";
}

void append_bool_array(ostringstream &out, const vector<bool> &values) {
    out << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            out << ",";
        }
        out << (values[i] ? "true" : "false");
    }
    out << "]";
}

void append_nested_long_array(
    ostringstream &out, const vector<vector<long>> &values) {
    out << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            out << ",";
        }
        append_long_array(out, values[i]);
    }
    out << "]";
}

void append_nested_int_array(
    ostringstream &out, const vector<vector<int>> &values) {
    out << "[";
    for (size_t i = 0; i < values.size(); ++i) {
        if (i > 0) {
            out << ",";
        }
        append_int_array(out, values[i]);
    }
    out << "]";
}


void log_selector_record(
    const string &kind, const CandidateSpec &spec,
    const MaterializedCandidate *candidate, int cofactor_width_budget,
    int total_add_node_budget, int value_cap, bool select_value_cap,
    bool feasible,
    const string &rejection_reason, bool emit_raw_value_histogram = false) {
    ostringstream out;
    const bool capped = value_cap >= 0;
    const bool cap_grid = select_value_cap;
    const bool add_budget = uses_total_add_budget(total_add_node_budget);
    out << "{\"protocol\":\""
        << (add_budget
                ? (cap_grid ? ADD_CAP_GRID_SELECTOR_PROTOCOL
                            : (capped ? CAPPED_ADD_SELECTOR_PROTOCOL
                                      : ADD_SELECTOR_PROTOCOL))
                : (cap_grid ? CAP_GRID_SELECTOR_PROTOCOL
                            : (capped ? CAPPED_WIDTH_SELECTOR_PROTOCOL
                                      : WIDTH_SELECTOR_PROTOCOL)))
        << "\",\"score_version\":\""
        << (add_budget
                ? (cap_grid ? CAP_GRID_SELECTOR_SCORE
                            : (capped ? CAPPED_WIDTH_SELECTOR_SCORE
                                      : WIDTH_SELECTOR_SCORE))
                : (cap_grid ? CAP_GRID_SELECTOR_SCORE
                            : (capped ? CAPPED_WIDTH_SELECTOR_SCORE
                                      : WIDTH_SELECTOR_SCORE)))
        << "\",\"sources\":";
    append_string_array(out, spec.sources);
    out << ",\"pattern\":";
    append_int_array(out, spec.pattern);
    out << ",\"abstract_states\":" << spec.abstract_states;
    if (candidate) {
        out << ",\"initial_dead_end\":"
            << (candidate->initial_dead_end ? "true" : "false")
            << ",\"initial_h\":";
        if (candidate->initial_dead_end) {
            out << "null";
        } else {
            out << candidate->initial_h;
        }
        out << ",\"finite_sum\":" << candidate->finite_sum
            << ",\"finite_count\":" << candidate->finite_count
            << ",\"dead_count\":" << candidate->dead_count
            << ",\"cofactor_width\":"
            << candidate->add_stats.cofactor_width
            << ",\"width_upper_bound\":"
            << candidate->add_stats.width_upper_bound;
    } else {
        out << ",\"initial_dead_end\":null,\"initial_h\":null"
               ",\"finite_sum\":null,\"finite_count\":null"
               ",\"dead_count\":null,\"cofactor_width\":null"
               ",\"width_upper_bound\":null";
    }
    if (add_budget) {
        out << ",\"total_add_node_budget\":" << total_add_node_budget;
    } else {
        out << ",\"cofactor_width_budget\":" << cofactor_width_budget;
    }
    if (capped || cap_grid) {
        out << ",\"value_cap\":" << value_cap;
        if (candidate) {
            out << ",\"add_nodes\":"
                << candidate->add_stats.add_inner_nodes
                << ",\"num_terminals\":"
                << candidate->add_stats.num_terminals
                << ",\"raw_add_nodes\":"
                << candidate->raw_add_nodes
                << ",\"raw_num_terminals\":"
                << candidate->raw_num_terminals
                << ",\"raw_cofactor_width\":"
                << candidate->raw_cofactor_width
                << ",\"raw_width_upper_bound\":"
                << candidate->raw_width_upper_bound
                << ",\"raw_num_values\":"
                << candidate->raw_num_values
                << ",\"raw_max_finite_value\":"
                << candidate->raw_max_finite_value
                << ",\"raw_finite_sum\":"
                << candidate->raw_finite_sum
                << ",\"raw_finite_count\":"
                << candidate->raw_finite_count
                << ",\"raw_dead_count\":"
                << candidate->raw_dead_count
                << ",\"raw_initial_dead_end\":"
                << (candidate->raw_initial_dead_end ? "true" : "false")
                << ",\"raw_initial_h\":";
            if (candidate->raw_initial_dead_end) {
                out << "null";
            } else {
                out << candidate->raw_initial_h;
            }
            if (cap_grid) {
                out << ",\"raw_initial_value_count\":";
                if (candidate->raw_initial_dead_end) {
                    out << "null";
                } else {
                    out << candidate->raw_initial_value_count;
                }
                out << ",\"raw_value_histogram\":";
                if (emit_raw_value_histogram) {
                    out << "\"" << candidate->raw_value_histogram << "\"";
                } else {
                    out << "null";
                }
            }
            out << ",\"transformed_num_values\":"
                << candidate->level_sets.size();
        } else {
            out << ",\"add_nodes\":null"
                   ",\"num_terminals\":null"
                   ",\"raw_add_nodes\":null"
                   ",\"raw_num_terminals\":null"
                   ",\"raw_cofactor_width\":null"
                   ",\"raw_width_upper_bound\":null"
                   ",\"raw_num_values\":null"
                   ",\"raw_max_finite_value\":null"
                   ",\"raw_finite_sum\":null"
                   ",\"raw_finite_count\":null"
                   ",\"raw_dead_count\":null"
                   ",\"raw_initial_dead_end\":null"
                   ",\"raw_initial_h\":null";
            if (cap_grid) {
                out << ",\"raw_initial_value_count\":null"
                       ",\"raw_value_histogram\":null";
            }
            out <<
                   ",\"transformed_num_values\":null";
        }
    }
    out
        << ",\"feasible\":" << (feasible ? "true" : "false")
        << ",\"rejection_reason\":";
    if (rejection_reason.empty()) {
        out << "null";
    } else {
        out << "\"" << rejection_reason << "\"";
    }
    out << "}";
    utils::g_log << (add_budget ? "PDB add-selector v1 "
                                : "PDB width-selector v1 ")
                 << kind << ": " << out.str() << endl;
}
}

bool PdbLevelSets::uses_total_add_node_budget() const {
    return uses_total_add_budget(total_add_node_budget);
}

PdbLevelSets::PdbLevelSets(
    SymVariables *vars, const shared_ptr<AbstractTask> &task, int state_budget,
    PdbPatternSelection pattern_selection, bool legacy_goal_directed,
    double cegar_max_time, int cegar_seed, int cegar_max_refinements,
    int cofactor_width_budget, int total_add_node_budget, int value_cap,
    bool select_value_cap, const WbhIncidenceProbe *incidence_probe,
    WbhSelectorTrace *selector_trace,
    const WbhStateCutCertificate *state_cut_certificate)
    : vars(vars), cofactor_width_budget(cofactor_width_budget),
      total_add_node_budget(total_add_node_budget), value_cap(value_cap),
      select_value_cap(select_value_cap) {
    TaskProxy task_proxy(*task);

    const bool incidence_guided =
        pattern_selection == PdbPatternSelection::TERMINAL_INCIDENCE_GUIDED;
    const bool incidence_matched =
        pattern_selection ==
        PdbPatternSelection::TERMINAL_INCIDENCE_MATCHED_CONTROL;
    const bool dual_incidence =
        pattern_selection ==
        PdbPatternSelection::TERMINAL_DUAL_INCIDENCE_GUIDED;
    const bool dual_mj =
        pattern_selection == PdbPatternSelection::TERMINAL_DUAL_MJ_GUIDED;
    const bool dual_matched =
        pattern_selection ==
        PdbPatternSelection::TERMINAL_DUAL_MATCHED_CONTROL;
    const bool dual_selector = dual_incidence || dual_mj || dual_matched;
    if (incidence_guided || incidence_matched || dual_selector) {
        if (!incidence_probe || !selector_trace ||
            !incidence_probe->complete() ||
            incidence_probe->get_target_layers() != 16 ||
            incidence_probe->get_layers().size() != 16 ||
            (dual_selector && !state_cut_certificate) ||
            (!dual_selector && state_cut_certificate)) {
            ABORT(
                "Terminal metric selection requires one complete frozen "
                "16-layer blind probe, the matching certificate mode and a "
                "dedicated trace.");
        }
        Cudd_ReorderingType reordering_method;
        if (vars->getCudd()->ReorderingStatus(&reordering_method)) {
            ABORT(
                "Terminal metric selection received a dynamically "
                "reordered manager after validation.");
        }

        utils::Timer selection_cpu_timer;
        const auto selection_wall_start = chrono::steady_clock::now();
        const int selection_peak_before = utils::get_peak_memory_in_kb();

        vector<vector<long>> state_profiles;
        string state_profiles_sha256;
        if (dual_selector) {
            verify_wbh_state_cut_certificate(vars, *state_cut_certificate);
            state_profiles = compute_wbh_probe_state_profiles(
                vars, incidence_probe->get_layers(), *state_cut_certificate);
            ostringstream state_canonical;
            for (size_t layer = 0; layer < state_profiles.size(); ++layer) {
                state_canonical << layer << "|g="
                                << incidence_probe->get_g_values()[layer]
                                << "|bdd_nodes="
                                << incidence_probe->get_bdd_nodes()[layer]
                                << "|cofactor_counts=";
                for (size_t cut = 0; cut < state_profiles[layer].size();
                     ++cut) {
                    if (cut) {
                        state_canonical << ",";
                    }
                    state_canonical << state_profiles[layer][cut];
                }
                state_canonical << "\n";
            }
            state_profiles_sha256 = wbh_sha256_hex(state_canonical.str());
            ostringstream state_event;
            state_event << "{\"event\":\"probe_state_profiles\","
                        << "\"state_profiles_sha256\":\""
                        << state_profiles_sha256 << "\","
                        << "\"cofactor_counts_by_layer\":[";
            for (size_t layer = 0; layer < state_profiles.size(); ++layer) {
                if (layer) {
                    state_event << ",";
                }
                append_long_array(state_event, state_profiles[layer]);
            }
            state_event << "]}";
            selector_trace->write_event(state_event.str());
        }

        vector<CandidateSpec> specs = build_fixed_candidate_pool(
            vars, task, task_proxy, state_budget, cegar_max_time, cegar_seed,
            cegar_max_refinements, /*cap_grid=*/true);

        ostringstream pool_canonical;
        for (size_t i = 0; i < specs.size(); ++i) {
            const CandidateSpec &spec = specs[i];
            pool_canonical << i << "|sources=";
            for (size_t j = 0; j < spec.sources.size(); ++j) {
                if (j) {
                    pool_canonical << ",";
                }
                pool_canonical << spec.sources[j];
            }
            pool_canonical << "|pattern=";
            for (size_t j = 0; j < spec.pattern.size(); ++j) {
                if (j) {
                    pool_canonical << ",";
                }
                pool_canonical << spec.pattern[j];
            }
            pool_canonical << "|abstract_states=" << spec.abstract_states
                           << "|within_state_budget="
                           << (spec.within_state_budget ? 1 : 0) << "\n";
        }
        pool_sha256 = wbh_sha256_hex(pool_canonical.str());
        ostringstream pool_event;
        pool_event << "{\"event\":\"pool\",\"protocol\":\""
                   << (dual_selector ? DUAL_SELECTOR_PROTOCOL
                                     : INCIDENCE_SELECTOR_PROTOCOL)
                   << "\",\"state_budget\":" << state_budget
                   << ",\"pool_sha256\":\"" << pool_sha256
                   << "\",\"patterns\":[";
        for (size_t i = 0; i < specs.size(); ++i) {
            if (i) {
                pool_event << ",";
            }
            const CandidateSpec &spec = specs[i];
            pool_event << "{\"pattern_index\":" << i << ",\"sources\":";
            append_string_array(pool_event, spec.sources);
            pool_event << ",\"pattern\":";
            append_int_array(pool_event, spec.pattern);
            pool_event << ",\"abstract_states\":" << spec.abstract_states
                       << ",\"within_state_budget\":"
                       << (spec.within_state_budget ? "true" : "false")
                       << "}";
        }
        pool_event << "]}";
        selector_trace->write_event(pool_event.str());

        if (dual_selector) {
            vector<vector<DualMetricVariant>> variants(specs.size());
            for (size_t pattern_index = 0; pattern_index < specs.size();
                 ++pattern_index) {
                CandidateSpec &spec = specs[pattern_index];
                if (!spec.within_state_budget) {
                    spec.pdb.reset();
                    continue;
                }
                unique_ptr<MaterializedCandidate> raw =
                    materialize_raw_candidate(vars, task_proxy, spec);
                if (!raw->raw_initial_dead_end) {
                    raw->raw_initial_value_count =
                        raw->finite_value_counts.at(raw->raw_initial_h);
                }
                raw->raw_value_histogram =
                    encode_raw_value_histogram(raw->finite_value_counts);
                vector<int> caps = distinct_cap_grid(*raw);
                for (int cap : caps) {
                    unique_ptr<MaterializedCandidate> candidate;
                    if (cap < 0) {
                        candidate = move(raw);
                    } else {
                        candidate = cap_candidate(vars, *raw, cap);
                    }
                    vector<long> heuristic_state_profile =
                        project_wbh_add_cofactor_profile(
                            candidate->add_stats.cofactor_counts,
                            *state_cut_certificate);
                    WbhDualMetricMeasurement measurement =
                        measure_wbh_dual_metrics(
                            vars, incidence_probe->get_layers(),
                            candidate->h_add, candidate->dead_ends,
                            candidate->dead_end_value, *state_cut_certificate,
                            state_profiles, heuristic_state_profile);
                    const bool reference_feasible =
                        candidate->add_stats.cofactor_width <=
                        INCIDENCE_REFERENCE_WIDTH_BUDGET;

                    if (!variants[pattern_index].empty()) {
                        const DualMetricVariant &weaker =
                            variants[pattern_index].back();
                        if (weaker.value_cap < 0 ||
                            (cap >= 0 && cap <= weaker.value_cap) ||
                            (!weaker.reference_feasible &&
                             reference_feasible) ||
                            weaker.heuristic_state_profile.size() !=
                                heuristic_state_profile.size() ||
                            weaker.measurement.layers.size() !=
                                measurement.layers.size() ||
                            weaker.measurement.incidence.total >
                                measurement.incidence.total ||
                            weaker.measurement.masked_joint_total >
                                measurement.masked_joint_total) {
                            ABORT(
                                "WBH dual selector cap sequence violates "
                                "its aggregate refinement invariants.");
                        }
                        for (size_t cut = 0;
                             cut < heuristic_state_profile.size(); ++cut) {
                            if (weaker.heuristic_state_profile[cut] >
                                heuristic_state_profile[cut]) {
                                ABORT(
                                    "WBH dual selector cap refinement "
                                    "decreased a heuristic cofactor count.");
                            }
                        }
                        for (size_t layer = 0;
                             layer < measurement.layers.size(); ++layer) {
                            const WbhDualMetricLayerMeasurement &old_layer =
                                weaker.measurement.layers[layer];
                            const WbhDualMetricLayerMeasurement &new_layer =
                                measurement.layers[layer];
                            if (old_layer.dead_end_active !=
                                    new_layer.dead_end_active ||
                                old_layer.masked_add_nodes >
                                    new_layer.masked_add_nodes ||
                                old_layer.active_terminal_count >
                                    new_layer.active_terminal_count ||
                                old_layer.joint_cofactor_sum >
                                    new_layer.joint_cofactor_sum ||
                                old_layer.masked_joint >
                                    new_layer.masked_joint ||
                                weaker.measurement.incidence.by_layer[layer] >
                                    measurement.incidence.by_layer[layer] ||
                                old_layer.joint_cofactor_counts.size() !=
                                    new_layer.joint_cofactor_counts.size()) {
                                ABORT(
                                    "WBH dual selector cap refinement "
                                    "decreased a layer certificate.");
                            }
                            for (size_t cut = 0;
                                 cut < new_layer.joint_cofactor_counts.size();
                                 ++cut) {
                                if (old_layer.joint_cofactor_counts[cut] >
                                    new_layer.joint_cofactor_counts[cut]) {
                                    ABORT(
                                        "WBH dual selector cap refinement "
                                        "decreased a joint cofactor count.");
                                }
                            }
                        }
                    }
                    variants[pattern_index].push_back({
                        pattern_index, cap, move(candidate),
                        move(heuristic_state_profile), move(measurement),
                        reference_feasible});
                }
                spec.pdb.reset();
            }

            DualMetricVariant *reference = nullptr;
            for (vector<DualMetricVariant> &pattern_variants : variants) {
                DualMetricVariant *representative = nullptr;
                for (DualMetricVariant &variant : pattern_variants) {
                    if (variant.reference_feasible) {
                        representative = &variant;
                    }
                }
                if (representative &&
                    (!reference ||
                     candidate_is_better(
                         *representative->candidate,
                         *reference->candidate))) {
                    reference = representative;
                }
            }
            if (!reference) {
                ABORT(
                    "The dual selector K=32 cap-aware reference has no "
                    "feasible candidate; the mandatory empty-pattern "
                    "invariant failed.");
            }
            terminal_incidence_budget = reference->measurement.incidence.total;
            masked_joint_budget = reference->measurement.masked_joint_total;
            if (terminal_incidence_budget < 0 || masked_joint_budget < 0) {
                ABORT("The dual selector reference budgets are invalid.");
            }

            DualMetricVariant *incidence_winner = nullptr;
            DualMetricVariant *masked_joint_winner = nullptr;
            for (vector<DualMetricVariant> &pattern_variants : variants) {
                DualMetricVariant *incidence_representative = nullptr;
                DualMetricVariant *masked_joint_representative = nullptr;
                for (DualMetricVariant &variant : pattern_variants) {
                    variant.incidence_feasible =
                        variant.measurement.incidence.total <=
                        terminal_incidence_budget;
                    variant.masked_joint_feasible =
                        variant.measurement.masked_joint_total <=
                        masked_joint_budget;
                    if (variant.incidence_feasible) {
                        incidence_representative = &variant;
                    }
                    if (variant.masked_joint_feasible) {
                        masked_joint_representative = &variant;
                    }
                }
                if (incidence_representative) {
                    incidence_representative
                        ->incidence_retained_for_pattern = true;
                    if (!incidence_winner ||
                        candidate_is_better(
                            *incidence_representative->candidate,
                            *incidence_winner->candidate)) {
                        incidence_winner = incidence_representative;
                    }
                }
                if (masked_joint_representative) {
                    masked_joint_representative
                        ->masked_joint_retained_for_pattern = true;
                    if (!masked_joint_winner ||
                        candidate_is_better(
                            *masked_joint_representative->candidate,
                            *masked_joint_winner->candidate)) {
                        masked_joint_winner = masked_joint_representative;
                    }
                }
            }
            if (!reference->incidence_feasible ||
                !reference->masked_joint_feasible ||
                reference->measurement.incidence.total !=
                    terminal_incidence_budget ||
                reference->measurement.masked_joint_total !=
                    masked_joint_budget ||
                !incidence_winner || !masked_joint_winner) {
                ABORT(
                    "Dual-metric selection failed a reference-feasibility "
                    "invariant; no fallback is permitted.");
            }

            auto append_canonical_values = [](
                                               ostringstream &out,
                                               const auto &values) {
                for (size_t i = 0; i < values.size(); ++i) {
                    if (i) {
                        out << ",";
                    }
                    out << values[i];
                }
            };
            auto append_incidence_projection = [&](
                                                   ostringstream &out,
                                                   const DualMetricVariant &variant,
                                                   bool terminate_line) {
                const MaterializedCandidate &candidate = *variant.candidate;
                out << variant.pattern_index << "|cap=";
                if (variant.value_cap < 0) {
                    out << "exact";
                } else {
                    out << variant.value_cap;
                }
                out << "|initial_dead_end=" << candidate.initial_dead_end
                    << "|initial_h=";
                if (candidate.initial_dead_end) {
                    out << "null";
                } else {
                    out << candidate.initial_h;
                }
                out << "|finite_sum=" << candidate.finite_sum
                    << "|finite_count=" << candidate.finite_count
                    << "|dead_count=" << candidate.dead_count
                    << "|cofactor_width="
                    << candidate.add_stats.cofactor_width
                    << "|width_upper_bound="
                    << candidate.add_stats.width_upper_bound
                    << "|raw_max_finite_value="
                    << candidate.raw_max_finite_value
                    << "|raw_value_histogram=";
                if (variant.value_cap < 0) {
                    out << candidate.raw_value_histogram;
                } else {
                    out << "null";
                }
                out << "|incidence=";
                append_canonical_values(
                    out, variant.measurement.incidence.by_layer);
                out << "|incidence_total="
                    << variant.measurement.incidence.total
                    << "|reference_feasible="
                    << variant.reference_feasible;
                if (terminate_line) {
                    out << "\n";
                }
            };
            auto append_dual_canonical = [&](
                                             ostringstream &out,
                                             const DualMetricVariant &variant) {
                append_incidence_projection(
                    out, variant, /*terminate_line=*/false);
                out << "|heuristic_cofactor_counts=";
                append_canonical_values(out, variant.heuristic_state_profile);
                out << "|dead_end_value="
                    << variant.candidate->dead_end_value;
                out << "|masked_add_nodes=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ",";
                    }
                    out << variant.measurement.layers[layer].masked_add_nodes;
                }
                out << "|active_finite_values=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ";";
                    }
                    append_canonical_values(
                        out,
                        variant.measurement.layers[layer]
                            .active_finite_values);
                }
                out << "|dead_end_active=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ",";
                    }
                    out << variant.measurement.layers[layer].dead_end_active;
                }
                out << "|active_terminal_count=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ",";
                    }
                    out << variant.measurement.layers[layer]
                               .active_terminal_count;
                }
                out << "|joint_cofactor_counts=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ";";
                    }
                    append_canonical_values(
                        out,
                        variant.measurement.layers[layer]
                            .joint_cofactor_counts);
                }
                out << "|joint_cofactor_sum=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ",";
                    }
                    out << variant.measurement.layers[layer]
                               .joint_cofactor_sum;
                }
                out << "|masked_joint=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ",";
                    }
                    out << variant.measurement.layers[layer].masked_joint;
                }
                out << "|masked_joint_total="
                    << variant.measurement.masked_joint_total;
                out << "|incidence_node_kinds=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ";";
                    }
                    append_canonical_values(
                        out, variant.measurement.layers[layer]
                                 .incidence_node_kinds);
                }
                out << "|incidence_then_children=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ";";
                    }
                    append_canonical_values(
                        out, variant.measurement.layers[layer]
                                 .incidence_then_children);
                }
                out << "|incidence_else_children=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ";";
                    }
                    append_canonical_values(
                        out, variant.measurement.layers[layer]
                                 .incidence_else_children);
                }
                out << "|incidence_terminal_values=";
                for (size_t layer = 0;
                     layer < variant.measurement.layers.size(); ++layer) {
                    if (layer) {
                        out << ";";
                    }
                    append_canonical_values(
                        out, variant.measurement.layers[layer]
                                 .incidence_terminal_values);
                }
                out << "\n";
            };

            ostringstream incidence_projection_canonical;
            ostringstream dual_canonical;
            size_t variant_count = 0;
            long joint_cut_entries = 0;
            for (const vector<DualMetricVariant> &pattern_variants : variants) {
                for (const DualMetricVariant &variant : pattern_variants) {
                    append_incidence_projection(
                        incidence_projection_canonical, variant,
                        /*terminate_line=*/true);
                    append_dual_canonical(dual_canonical, variant);
                    ++variant_count;
                    if (variant.measurement.joint_cut_entries < 0 ||
                        joint_cut_entries > numeric_limits<long>::max() -
                                                variant.measurement
                                                    .joint_cut_entries) {
                        ABORT("Dual selector joint work counter overflow.");
                    }
                    joint_cut_entries +=
                        variant.measurement.joint_cut_entries;
                }
            }
            const string incidence_projection_sha256 =
                wbh_sha256_hex(incidence_projection_canonical.str());
            preselection_sha256 = wbh_sha256_hex(dual_canonical.str());

            auto log_variant = [&](const DualMetricVariant &variant) {
                const CandidateSpec &spec = specs[variant.pattern_index];
                const MaterializedCandidate &candidate = *variant.candidate;
                vector<long> masked_add_nodes;
                vector<vector<int>> active_finite_values;
                vector<bool> dead_end_active;
                vector<int> active_terminal_count;
                vector<vector<long>> joint_cofactor_counts;
                vector<long> joint_cofactor_sum;
                vector<long> masked_joint;
                vector<vector<int>> incidence_node_kinds;
                vector<vector<int>> incidence_then_children;
                vector<vector<int>> incidence_else_children;
                vector<vector<int>> incidence_terminal_values;
                for (const WbhDualMetricLayerMeasurement &layer :
                     variant.measurement.layers) {
                    masked_add_nodes.push_back(layer.masked_add_nodes);
                    active_finite_values.push_back(layer.active_finite_values);
                    dead_end_active.push_back(layer.dead_end_active);
                    active_terminal_count.push_back(
                        layer.active_terminal_count);
                    joint_cofactor_counts.push_back(
                        layer.joint_cofactor_counts);
                    joint_cofactor_sum.push_back(layer.joint_cofactor_sum);
                    masked_joint.push_back(layer.masked_joint);
                    incidence_node_kinds.push_back(
                        layer.incidence_node_kinds);
                    incidence_then_children.push_back(
                        layer.incidence_then_children);
                    incidence_else_children.push_back(
                        layer.incidence_else_children);
                    incidence_terminal_values.push_back(
                        layer.incidence_terminal_values);
                }

                ostringstream out;
                out << "{\"event\":\"candidate\",\"protocol\":\""
                    << DUAL_SELECTOR_PROTOCOL
                    << "\",\"score_version\":\"" << DUAL_SELECTOR_SCORE
                    << "\",\"pattern_index\":" << variant.pattern_index
                    << ",\"sources\":";
                append_string_array(out, spec.sources);
                out << ",\"pattern\":";
                append_int_array(out, spec.pattern);
                out << ",\"abstract_states\":" << candidate.abstract_states
                    << ",\"value_cap\":";
                if (variant.value_cap < 0) {
                    out << "null";
                } else {
                    out << variant.value_cap;
                }
                out << ",\"initial_dead_end\":"
                    << (candidate.initial_dead_end ? "true" : "false")
                    << ",\"initial_h\":";
                if (candidate.initial_dead_end) {
                    out << "null";
                } else {
                    out << candidate.initial_h;
                }
                out << ",\"finite_sum\":" << candidate.finite_sum
                    << ",\"finite_count\":" << candidate.finite_count
                    << ",\"dead_count\":" << candidate.dead_count
                    << ",\"cofactor_width\":"
                    << candidate.add_stats.cofactor_width
                    << ",\"width_upper_bound\":"
                    << candidate.add_stats.width_upper_bound
                    << ",\"raw_max_finite_value\":"
                    << candidate.raw_max_finite_value
                    << ",\"raw_value_histogram\":";
                if (variant.value_cap < 0) {
                    out << "\"" << candidate.raw_value_histogram << "\"";
                } else {
                    out << "null";
                }
                out << ",\"heuristic_cofactor_counts\":";
                append_long_array(out, variant.heuristic_state_profile);
                out << ",\"dead_end_value\":"
                    << candidate.dead_end_value;
                out << ",\"terminal_incidence_by_layer\":";
                append_long_array(out, variant.measurement.incidence.by_layer);
                out << ",\"terminal_incidence\":"
                    << variant.measurement.incidence.total
                    << ",\"masked_add_nodes_by_layer\":";
                append_long_array(out, masked_add_nodes);
                out << ",\"active_finite_values_by_layer\":";
                append_nested_int_array(out, active_finite_values);
                out << ",\"dead_end_active_by_layer\":";
                append_bool_array(out, dead_end_active);
                out << ",\"active_terminal_count_by_layer\":";
                append_int_array(out, active_terminal_count);
                out << ",\"joint_cofactor_counts_by_layer\":";
                append_nested_long_array(out, joint_cofactor_counts);
                out << ",\"joint_cofactor_sum_by_layer\":";
                append_long_array(out, joint_cofactor_sum);
                out << ",\"masked_joint_by_layer\":";
                append_long_array(out, masked_joint);
                out << ",\"masked_joint\":"
                    << variant.measurement.masked_joint_total
                    << ",\"incidence_node_kinds_by_layer\":";
                append_nested_int_array(out, incidence_node_kinds);
                out << ",\"incidence_then_children_by_layer\":";
                append_nested_int_array(out, incidence_then_children);
                out << ",\"incidence_else_children_by_layer\":";
                append_nested_int_array(out, incidence_else_children);
                out << ",\"incidence_terminal_values_by_layer\":";
                append_nested_int_array(out, incidence_terminal_values);
                out
                    << ",\"reference_feasible\":"
                    << (variant.reference_feasible ? "true" : "false")
                    << ",\"incidence_feasible\":"
                    << (variant.incidence_feasible ? "true" : "false")
                    << ",\"masked_joint_feasible\":"
                    << (variant.masked_joint_feasible ? "true" : "false")
                    << ",\"incidence_retained_for_pattern\":"
                    << (variant.incidence_retained_for_pattern ? "true"
                                                               : "false")
                    << ",\"masked_joint_retained_for_pattern\":"
                    << (variant.masked_joint_retained_for_pattern ? "true"
                                                                  : "false")
                    << "}";
                selector_trace->write_event(out.str());
            };
            for (const vector<DualMetricVariant> &pattern_variants : variants) {
                for (const DualMetricVariant &variant : pattern_variants) {
                    log_variant(variant);
                }
            }

            ostringstream preselection_event;
            preselection_event
                << "{\"event\":\"preselection\",\"pool_sha256\":\""
                << pool_sha256 << "\",\"state_profiles_sha256\":\""
                << state_profiles_sha256
                << "\",\"incidence_projection_sha256\":\""
                << incidence_projection_sha256
                << "\",\"preselection_sha256\":\""
                << preselection_sha256 << "\",\"candidate_count\":"
                << variant_count << "}";
            selector_trace->write_event(preselection_event.str());

            auto append_identity = [&](ostringstream &out,
                                       const DualMetricVariant &variant,
                                       const string &prefix) {
                const CandidateSpec &spec = specs[variant.pattern_index];
                out << "\"" << prefix << "pattern_index\":"
                    << variant.pattern_index << ",\"" << prefix
                    << "sources\":";
                append_string_array(out, spec.sources);
                out << ",\"" << prefix << "pattern\":";
                append_int_array(out, spec.pattern);
                out << ",\"" << prefix << "value_cap\":";
                if (variant.value_cap < 0) {
                    out << "null";
                } else {
                    out << variant.value_cap;
                }
                out << ",\"" << prefix << "terminal_incidence\":"
                    << variant.measurement.incidence.total << ",\"" << prefix
                    << "masked_joint\":"
                    << variant.measurement.masked_joint_total;
            };

            ostringstream reference_event;
            reference_event
                << "{\"event\":\"reference\",\"pool_sha256\":\""
                << pool_sha256 << "\",\"state_profiles_sha256\":\""
                << state_profiles_sha256
                << "\",\"incidence_projection_sha256\":\""
                << incidence_projection_sha256
                << "\",\"preselection_sha256\":\""
                << preselection_sha256 << "\",";
            append_identity(reference_event, *reference, "reference_");
            reference_event
                << ",\"reference_cofactor_width_budget\":"
                << INCIDENCE_REFERENCE_WIDTH_BUDGET
                << ",\"incidence_budget\":" << terminal_incidence_budget
                << ",\"masked_joint_budget\":" << masked_joint_budget
                << "}";
            selector_trace->write_event(reference_event.str());

            ostringstream winners_event;
            winners_event
                << "{\"event\":\"metric_winners\",\"pool_sha256\":\""
                << pool_sha256 << "\",\"state_profiles_sha256\":\""
                << state_profiles_sha256
                << "\",\"incidence_projection_sha256\":\""
                << incidence_projection_sha256
                << "\",\"preselection_sha256\":\""
                << preselection_sha256
                << "\",\"incidence_budget\":" << terminal_incidence_budget
                << ",\"masked_joint_budget\":" << masked_joint_budget
                << ",";
            append_identity(
                winners_event, *incidence_winner, "incidence_winner_");
            winners_event << ",";
            append_identity(
                winners_event, *masked_joint_winner,
                "masked_joint_winner_");
            winners_event << "}";
            selector_trace->write_event(winners_event.str());

            DualMetricVariant *selected =
                dual_incidence
                    ? incidence_winner
                    : (dual_mj ? masked_joint_winner : reference);
            const char *decision_mode =
                dual_incidence
                    ? "incidence_guided"
                    : (dual_mj ? "masked_joint_guided" : "matched_control");
            selected_terminal_incidence =
                selected->measurement.incidence.total;
            selected_masked_joint = selected->measurement.masked_joint_total;
            if ((dual_incidence && !selected->incidence_feasible) ||
                (dual_mj && !selected->masked_joint_feasible) ||
                (dual_matched && selected != reference)) {
                ABORT("Dual selector selected an unauthorized candidate.");
            }

            ostringstream selected_event;
            selected_event
                << "{\"event\":\"selected\",\"decision_mode\":\""
                << decision_mode << "\",\"pool_sha256\":\""
                << pool_sha256 << "\",\"state_profiles_sha256\":\""
                << state_profiles_sha256
                << "\",\"incidence_projection_sha256\":\""
                << incidence_projection_sha256
                << "\",\"preselection_sha256\":\""
                << preselection_sha256 << "\",";
            append_identity(selected_event, *selected, "selected_");
            selected_event
                << ",\"incidence_budget\":" << terminal_incidence_budget
                << ",\"masked_joint_budget\":" << masked_joint_budget
                << "}";
            selector_trace->write_event(selected_event.str());

            MaterializedCandidate &winner = *selected->candidate;
            pattern = winner.pattern;
            selected_source = winner.sources.front();
            num_abstract_states = winner.abstract_states;
            selected_initial_dead_end = winner.initial_dead_end;
            this->value_cap = winner.value_cap;
            level_sets = move(winner.level_sets);
            dead_ends = winner.dead_ends;
            h_add = winner.h_add;
            add_stats = move(winner.add_stats);
            selection_name =
                dual_incidence
                    ? "terminal_dual_incidence_guided"
                    : (dual_mj ? "terminal_dual_mj_guided"
                               : "terminal_dual_matched_control");

            pdbs::Projection selected_projection(task_proxy, pattern);
            verify_against_pdb(
                task_proxy, *winner.pdb, selected_projection, 200);

            const size_t layer_count = incidence_probe->get_layers().size();
            const size_t state_cut_count =
                state_cut_certificate->cudd_indices.size() + 1;
            const size_t long_max =
                static_cast<size_t>(numeric_limits<long>::max());
            if ((layer_count &&
                 variant_count > long_max / layer_count) ||
                state_cut_count > long_max) {
                ABORT("Dual selector work accounting overflow.");
            }
            const long expected_layer_measurements =
                static_cast<long>(variant_count * layer_count);
            if (state_cut_count &&
                expected_layer_measurements >
                    numeric_limits<long>::max() /
                        static_cast<long>(state_cut_count)) {
                ABORT("Dual selector work accounting overflow.");
            }
            const long expected_joint_cut_entries =
                expected_layer_measurements *
                static_cast<long>(state_cut_count);
            const long expected_joint_summed_cut_entries =
                expected_layer_measurements *
                static_cast<long>(state_cut_count - 1);
            if (joint_cut_entries != expected_joint_cut_entries) {
                ABORT("Dual selector work accounting is inconsistent.");
            }
            long state_profile_cut_entries = 0;
            for (const vector<long> &profile : state_profiles) {
                if (profile.size() != state_cut_count ||
                    profile.size() > long_max ||
                    state_profile_cut_entries >
                        numeric_limits<long>::max() -
                            static_cast<long>(profile.size())) {
                    ABORT(
                        "Dual selector state-profile accounting is "
                        "inconsistent.");
                }
                state_profile_cut_entries += profile.size();
            }

            const double selection_cpu_seconds = selection_cpu_timer();
            const double selection_wall_seconds = chrono::duration<double>(
                                                      chrono::steady_clock::now() -
                                                      selection_wall_start)
                                                      .count();
            const int selection_peak_after = utils::get_peak_memory_in_kb();
            ostringstream accounting_event;
            accounting_event
                << "{\"event\":\"selection_accounting\","
                << "\"candidate_count\":" << variant_count
                << ",\"probe_state_profile_count\":"
                << state_profiles.size()
                << ",\"probe_state_profile_cut_entries\":"
                << state_profile_cut_entries
                << ",\"terminal_incidence_layer_measurements\":"
                << expected_layer_measurements
                << ",\"joint_profile_layer_measurements\":"
                << expected_layer_measurements
                << ",\"joint_profile_cut_entries\":"
                << joint_cut_entries
                << ",\"joint_summed_cut_entries\":"
                << expected_joint_summed_cut_entries
                << ",\"cpu_seconds\":"
                << selection_cpu_seconds << ",\"wall_seconds\":"
                << selection_wall_seconds << ",\"peak_memory_before_kb\":"
                << selection_peak_before
                << ",\"peak_memory_after_kb\":" << selection_peak_after
                << ",\"peak_memory_delta_kb\":"
                << max(0, selection_peak_after - selection_peak_before)
                << "}";
            selector_trace->write_event(accounting_event.str());
            return;
        }

        struct IncidenceVariant {
            size_t pattern_index;
            int value_cap;
            unique_ptr<MaterializedCandidate> candidate;
            WbhIncidenceMeasurement incidence;
            bool reference_feasible;
            bool incidence_feasible = false;
            bool retained_for_pattern = false;
        };
        vector<vector<IncidenceVariant>> variants(specs.size());
        for (size_t pattern_index = 0; pattern_index < specs.size();
             ++pattern_index) {
            CandidateSpec &spec = specs[pattern_index];
            if (!spec.within_state_budget) {
                spec.pdb.reset();
                continue;
            }
            unique_ptr<MaterializedCandidate> raw =
                materialize_raw_candidate(vars, task_proxy, spec);
            if (!raw->raw_initial_dead_end) {
                raw->raw_initial_value_count =
                    raw->finite_value_counts.at(raw->raw_initial_h);
            }
            raw->raw_value_histogram =
                encode_raw_value_histogram(raw->finite_value_counts);
            vector<int> caps = distinct_cap_grid(*raw);
            for (int cap : caps) {
                unique_ptr<MaterializedCandidate> candidate;
                if (cap < 0) {
                    candidate = move(raw);
                } else {
                    candidate = cap_candidate(vars, *raw, cap);
                }
                WbhIncidenceMeasurement measurement =
                    measure_terminal_incidence(
                        vars, incidence_probe->get_layers(), candidate->h_add);
                const bool reference_feasible =
                    candidate->add_stats.cofactor_width <=
                    INCIDENCE_REFERENCE_WIDTH_BUDGET;
                variants[pattern_index].push_back(
                    {pattern_index, cap, move(candidate), move(measurement),
                     reference_feasible});
            }
            spec.pdb.reset();
        }

        IncidenceVariant *reference = nullptr;
        for (vector<IncidenceVariant> &pattern_variants : variants) {
            IncidenceVariant *representative = nullptr;
            for (IncidenceVariant &variant : pattern_variants) {
                if (variant.reference_feasible) {
                    representative = &variant;
                }
            }
            if (representative) {
                if (!reference ||
                    candidate_is_better(
                        *representative->candidate, *reference->candidate)) {
                    reference = representative;
                }
            }
        }
        if (!reference) {
            ABORT(
                "The K=32 cap-aware reference has no feasible candidate; "
                "the mandatory empty-pattern invariant failed.");
        }
        terminal_incidence_budget = reference->incidence.total;
        if (terminal_incidence_budget < 0) {
            ABORT("The terminal-incidence reference budget is invalid.");
        }

        IncidenceVariant *guided = nullptr;
        for (vector<IncidenceVariant> &pattern_variants : variants) {
            IncidenceVariant *representative = nullptr;
            for (IncidenceVariant &variant : pattern_variants) {
                variant.incidence_feasible =
                    variant.incidence.total <= terminal_incidence_budget;
                if (variant.incidence_feasible) {
                    representative = &variant;
                }
            }
            if (representative) {
                representative->retained_for_pattern = true;
                if (!guided ||
                    candidate_is_better(
                        *representative->candidate, *guided->candidate)) {
                    guided = representative;
                }
            }
        }
        if (!reference->incidence_feasible ||
            reference->incidence.total != terminal_incidence_budget ||
            !guided) {
            ABORT(
                "Terminal-incidence selection failed its reference-feasibility "
                "invariant; no fallback is permitted.");
        }

        ostringstream preselection_canonical;
        for (const vector<IncidenceVariant> &pattern_variants : variants) {
            for (const IncidenceVariant &variant : pattern_variants) {
                const MaterializedCandidate &candidate = *variant.candidate;
                preselection_canonical
                    << variant.pattern_index << "|cap=";
                if (variant.value_cap < 0) {
                    preselection_canonical << "exact";
                } else {
                    preselection_canonical << variant.value_cap;
                }
                preselection_canonical
                    << "|initial_dead_end=" << candidate.initial_dead_end
                    << "|initial_h=";
                if (candidate.initial_dead_end) {
                    preselection_canonical << "null";
                } else {
                    preselection_canonical << candidate.initial_h;
                }
                preselection_canonical
                    << "|finite_sum=" << candidate.finite_sum
                    << "|finite_count=" << candidate.finite_count
                    << "|dead_count=" << candidate.dead_count
                    << "|cofactor_width="
                    << candidate.add_stats.cofactor_width
                    << "|width_upper_bound="
                    << candidate.add_stats.width_upper_bound
                    << "|raw_max_finite_value="
                    << candidate.raw_max_finite_value
                    << "|raw_value_histogram=";
                if (variant.value_cap < 0) {
                    preselection_canonical << candidate.raw_value_histogram;
                } else {
                    preselection_canonical << "null";
                }
                preselection_canonical << "|incidence=";
                for (size_t i = 0; i < variant.incidence.by_layer.size(); ++i) {
                    if (i) {
                        preselection_canonical << ",";
                    }
                    preselection_canonical << variant.incidence.by_layer[i];
                }
                preselection_canonical
                    << "|incidence_total=" << variant.incidence.total
                    << "|reference_feasible=" << variant.reference_feasible
                    << "\n";
            }
        }
        preselection_sha256 =
            wbh_sha256_hex(preselection_canonical.str());

        auto log_variant = [&](const IncidenceVariant &variant) {
            const CandidateSpec &spec = specs[variant.pattern_index];
            const MaterializedCandidate &candidate = *variant.candidate;
            ostringstream out;
            out << "{\"event\":\"candidate\",\"protocol\":\""
                << INCIDENCE_SELECTOR_PROTOCOL
                << "\",\"score_version\":\"" << INCIDENCE_SELECTOR_SCORE
                << "\",\"pattern_index\":" << variant.pattern_index
                << ",\"sources\":";
            append_string_array(out, spec.sources);
            out << ",\"pattern\":";
            append_int_array(out, spec.pattern);
            out << ",\"abstract_states\":" << candidate.abstract_states
                << ",\"value_cap\":";
            if (variant.value_cap < 0) {
                out << "null";
            } else {
                out << variant.value_cap;
            }
            out << ",\"initial_dead_end\":"
                << (candidate.initial_dead_end ? "true" : "false")
                << ",\"initial_h\":";
            if (candidate.initial_dead_end) {
                out << "null";
            } else {
                out << candidate.initial_h;
            }
            out << ",\"finite_sum\":" << candidate.finite_sum
                << ",\"finite_count\":" << candidate.finite_count
                << ",\"dead_count\":" << candidate.dead_count
                << ",\"cofactor_width\":"
                << candidate.add_stats.cofactor_width
                << ",\"width_upper_bound\":"
                << candidate.add_stats.width_upper_bound
                << ",\"raw_max_finite_value\":"
                << candidate.raw_max_finite_value
                << ",\"raw_value_histogram\":";
            if (variant.value_cap < 0) {
                out << "\"" << candidate.raw_value_histogram << "\"";
            } else {
                out << "null";
            }
            out << ",\"terminal_incidence_by_layer\":";
            append_long_array(out, variant.incidence.by_layer);
            out << ",\"terminal_incidence\":" << variant.incidence.total
                << ",\"reference_feasible\":"
                << (variant.reference_feasible ? "true" : "false")
                << ",\"incidence_feasible\":"
                << (variant.incidence_feasible ? "true" : "false")
                << ",\"retained_for_pattern\":"
                << (variant.retained_for_pattern ? "true" : "false")
                << "}";
            selector_trace->write_event(out.str());
        };
        for (const vector<IncidenceVariant> &pattern_variants : variants) {
            for (const IncidenceVariant &variant : pattern_variants) {
                log_variant(variant);
            }
        }
        ostringstream preselection_event;
        preselection_event
            << "{\"event\":\"preselection\",\"pool_sha256\":\""
            << pool_sha256 << "\",\"preselection_sha256\":\""
            << preselection_sha256 << "\",\"candidate_count\":";
        size_t variant_count = 0;
        for (const auto &pattern_variants : variants) {
            variant_count += pattern_variants.size();
        }
        preselection_event << variant_count << "}";
        selector_trace->write_event(preselection_event.str());

        auto append_identity = [&](ostringstream &out,
                                   const IncidenceVariant &variant,
                                   const string &prefix) {
            const CandidateSpec &spec = specs[variant.pattern_index];
            out << "\"" << prefix << "pattern_index\":"
                << variant.pattern_index << ",\"" << prefix
                << "sources\":";
            append_string_array(out, spec.sources);
            out << ",\"" << prefix << "pattern\":";
            append_int_array(out, spec.pattern);
            out << ",\"" << prefix << "value_cap\":";
            if (variant.value_cap < 0) {
                out << "null";
            } else {
                out << variant.value_cap;
            }
            out << ",\"" << prefix << "terminal_incidence\":"
                << variant.incidence.total;
        };
        ostringstream reference_event;
        reference_event << "{\"event\":\"reference\",\"pool_sha256\":\""
                        << pool_sha256
                        << "\",\"preselection_sha256\":\""
                        << preselection_sha256 << "\",";
        append_identity(reference_event, *reference, "reference_");
        reference_event << ",\"reference_cofactor_width_budget\":"
                        << INCIDENCE_REFERENCE_WIDTH_BUDGET
                        << ",\"incidence_budget\":"
                        << terminal_incidence_budget << "}";
        selector_trace->write_event(reference_event.str());

        IncidenceVariant *selected = incidence_matched ? reference : guided;
        selected_terminal_incidence = selected->incidence.total;
        ostringstream selected_event;
        selected_event << "{\"event\":\"selected\",\"decision_mode\":\""
                       << (incidence_matched ? "matched_control" : "guided")
                       << "\",\"pool_sha256\":\"" << pool_sha256
                       << "\",\"preselection_sha256\":\""
                       << preselection_sha256 << "\",";
        append_identity(selected_event, *selected, "selected_");
        selected_event << ",\"incidence_budget\":"
                       << terminal_incidence_budget << "}";
        selector_trace->write_event(selected_event.str());

        MaterializedCandidate &winner = *selected->candidate;
        pattern = winner.pattern;
        selected_source = winner.sources.front();
        num_abstract_states = winner.abstract_states;
        selected_initial_dead_end = winner.initial_dead_end;
        this->value_cap = winner.value_cap;
        level_sets = move(winner.level_sets);
        dead_ends = winner.dead_ends;
        h_add = winner.h_add;
        add_stats = move(winner.add_stats);
        selection_name = incidence_matched
                             ? "terminal_incidence_matched_control"
                             : "terminal_incidence_guided";

        pdbs::Projection selected_projection(task_proxy, pattern);
        verify_against_pdb(
            task_proxy, *winner.pdb, selected_projection, 200);

        const double selection_cpu_seconds = selection_cpu_timer();
        const double selection_wall_seconds = chrono::duration<double>(
                                                  chrono::steady_clock::now() -
                                                  selection_wall_start)
                                                  .count();
        const int selection_peak_after = utils::get_peak_memory_in_kb();
        ostringstream accounting_event;
        accounting_event
            << "{\"event\":\"selection_accounting\",\"cpu_seconds\":"
            << selection_cpu_seconds << ",\"wall_seconds\":"
            << selection_wall_seconds << ",\"peak_memory_before_kb\":"
            << selection_peak_before << ",\"peak_memory_after_kb\":"
            << selection_peak_after << ",\"peak_memory_delta_kb\":"
            << max(0, selection_peak_after - selection_peak_before) << "}";
        selector_trace->write_event(accounting_event.str());
        return;
    }

    if (pattern_selection == PdbPatternSelection::EXACT_WIDTH_FILTER) {
        Cudd_ReorderingType reordering_method;
        if (vars->getCudd()->ReorderingStatus(&reordering_method)) {
            utils::g_log
                << "pattern_selection=exact_width_filter requires "
                   "dynamic_reordering=false; exact candidate widths must "
                   "remain valid throughout selection and search."
                << endl;
            utils::exit_with(utils::ExitCode::SEARCH_INPUT_ERROR);
        }

        vector<CandidateSpec> specs = build_fixed_candidate_pool(
            vars, task, task_proxy, state_budget, cegar_max_time, cegar_seed,
            cegar_max_refinements, select_value_cap);

        unique_ptr<MaterializedCandidate> winner;
        for (CandidateSpec &spec : specs) {
            if (!spec.within_state_budget) {
                log_selector_record(
                    "candidate", spec, nullptr, cofactor_width_budget,
                    total_add_node_budget, value_cap, select_value_cap,
                    /*feasible=*/false,
                    "abstract_state_budget");
                spec.pdb.reset();
                continue;
            }

            if (select_value_cap) {
                unique_ptr<MaterializedCandidate> raw =
                    materialize_raw_candidate(vars, task_proxy, spec);
                if (!raw->raw_initial_dead_end) {
                    raw->raw_initial_value_count =
                        raw->finite_value_counts.at(raw->raw_initial_h);
                }
                raw->raw_value_histogram =
                    encode_raw_value_histogram(raw->finite_value_counts);
                unique_ptr<MaterializedCandidate> pattern_winner;
                bool histogram_emitted = false;
                // Derive every distinct transform from the one raw PDB/BDD
                // materialization. Caps are ordered from weakest to strongest;
                // the exact transform is last. Monotonic terminal refinement
                // makes the last feasible cap the strongest transform for this
                // pattern, independent of the cross-pattern quality score.
                for (int cap : distinct_cap_grid(*raw)) {
                    unique_ptr<MaterializedCandidate> transformed;
                    MaterializedCandidate *candidate = nullptr;
                    if (cap < 0) {
                        candidate = raw.get();
                    } else {
                        transformed = cap_candidate(vars, *raw, cap);
                        candidate = transformed.get();
                    }
                    bool feasible = candidate_is_feasible(
                        *candidate, cofactor_width_budget,
                        total_add_node_budget);
                    log_selector_record(
                        "candidate", spec, candidate,
                        cofactor_width_budget, total_add_node_budget, cap,
                        /*select_value_cap=*/true, feasible,
                        feasible ? ""
                                 : budget_rejection_reason(
                                       total_add_node_budget),
                        /*emit_raw_value_histogram=*/!histogram_emitted);
                    histogram_emitted = true;
                    if (feasible) {
                        if (cap < 0) {
                            pattern_winner = move(raw);
                        } else {
                            pattern_winner = move(transformed);
                        }
                    }
                }
                if (pattern_winner &&
                    (!winner ||
                     candidate_is_better(*pattern_winner, *winner))) {
                    winner = move(pattern_winner);
                }
            } else {
                unique_ptr<MaterializedCandidate> candidate =
                    materialize_candidate(vars, task_proxy, spec, value_cap);
                bool feasible = candidate_is_feasible(
                    *candidate, cofactor_width_budget,
                    total_add_node_budget);
                log_selector_record(
                    "candidate", spec, candidate.get(),
                    cofactor_width_budget, total_add_node_budget, value_cap,
                    /*select_value_cap=*/false, feasible,
                    feasible ? ""
                             : budget_rejection_reason(
                                   total_add_node_budget));
                if (feasible &&
                    (!winner || candidate_is_better(*candidate, *winner))) {
                    winner = move(candidate);
                }
            }
            // Candidate objects retain their own shared PDB reference.
            spec.pdb.reset();
        }

        if (!winner) {
            ABORT(
                "PDB width-selector found no feasible candidate despite the "
                "width-1 empty pattern.");
        }

        CandidateSpec selected_spec{
            winner->pattern, winner->sources, winner->abstract_states,
            /*within_state_budget=*/true, nullptr};
        log_selector_record(
            "selected", selected_spec, winner.get(), cofactor_width_budget,
            total_add_node_budget, winner->value_cap, select_value_cap,
            /*feasible=*/true, "");

        pattern = winner->pattern;
        selected_source = winner->sources.front();
        num_abstract_states = winner->abstract_states;
        selected_initial_dead_end = winner->initial_dead_end;
        this->value_cap = winner->value_cap;
        level_sets = move(winner->level_sets);
        dead_ends = winner->dead_ends;
        h_add = winner->h_add;
        add_stats = move(winner->add_stats);
        if (uses_total_add_node_budget()) {
            selection_name = select_value_cap
                                 ? "exact_add_cap_filter"
                                 : "exact_add_filter";
        } else {
            selection_name = select_value_cap
                                 ? "exact_width_cap_filter"
                                 : "exact_width_filter";
        }

        pdbs::Projection selected_projection(task_proxy, pattern);
        verify_against_pdb(
            task_proxy, *winner->pdb, selected_projection, 200);
        utils::g_log << "PDB pattern selection=" << selection_name
                     << " (source=" << selected_source << ", "
                     << pattern.size() << " vars, " << num_abstract_states
                     << " abstract states, ";
        if (uses_total_add_node_budget()) {
            utils::g_log << "total ADD nodes=" << add_stats.width_upper_bound
                         << " <= " << total_add_node_budget;
        } else {
            utils::g_log << "exact width=" << add_stats.cofactor_width
                         << " <= " << cofactor_width_budget;
        }
        if (this->value_cap >= 0 || select_value_cap) {
            utils::g_log << ", value_cap=" << this->value_cap;
        }
        utils::g_log << "): " << pattern << endl;
        return;
    }

    // LEGACY exactly preserves the two historical modes, including stopping
    // at the first oversized variable. Explicit GOAL_FILL fixes that greedy
    // prefix pathology by trying all later variables. CEGAR reuses Fast
    // Downward's counterexample-guided pattern generator under the same PDB
    // state budget.
    bool goal_order = false;
    bool skip_oversized = false;
    bool use_cegar = false;
    switch (pattern_selection) {
    case PdbPatternSelection::LEGACY:
        goal_order = legacy_goal_directed;
        selection_name =
            legacy_goal_directed ? "goal_directed" : "bdd_order";
        break;
    case PdbPatternSelection::BDD_PREFIX:
        selection_name = "bdd_prefix";
        break;
    case PdbPatternSelection::GOAL_PREFIX:
        goal_order = true;
        selection_name = "goal_prefix";
        break;
    case PdbPatternSelection::GOAL_FILL:
        goal_order = true;
        skip_oversized = true;
        selection_name = "goal_fill";
        break;
    case PdbPatternSelection::CEGAR:
        use_cegar = true;
        selection_name = "cegar";
        break;
    case PdbPatternSelection::EXACT_WIDTH_FILTER:
        ABORT("Unreachable exact-width-filter selector branch.");
    case PdbPatternSelection::TERMINAL_INCIDENCE_GUIDED:
    case PdbPatternSelection::TERMINAL_INCIDENCE_MATCHED_CONTROL:
        ABORT("Unreachable terminal-incidence selector branch.");
    case PdbPatternSelection::TERMINAL_DUAL_INCIDENCE_GUIDED:
    case PdbPatternSelection::TERMINAL_DUAL_MJ_GUIDED:
    case PdbPatternSelection::TERMINAL_DUAL_MATCHED_CONTROL:
        ABORT("Unreachable terminal-dual-metric selector branch.");
    }

    shared_ptr<pdbs::PatternDatabase> pdb;
    vector<int> variable_order;
    if (use_cegar && task_proxy.get_goals().size() > 0) {
        pdbs::PatternGeneratorCEGAR generator(
            state_budget, cegar_max_time, cegar_max_refinements,
            /*use_wildcard_plans=*/true, cegar_seed, utils::Verbosity::NORMAL,
            /*exit_on_unsolvable=*/false);
        pdbs::PatternInformation info = generator.generate(task);
        pattern = info.get_pattern();

        // CEGAR deliberately permits an oversized singleton goal pattern.
        // That exception is inappropriate for a hard representation budget,
        // so fail over to the bounded fill strategy instead.
        long product = 1;
        bool within_budget = true;
        for (int var : pattern) {
            long domain_size =
                task_proxy.get_variables()[var].get_domain_size();
            if (product > state_budget / domain_size) {
                within_budget = false;
                break;
            }
            product *= domain_size;
        }
        if (within_budget) {
            pdb = info.get_pdb();
        } else {
            utils::g_log
                << "CEGAR singleton exceeds the hard PDB state budget; "
                   "falling back to goal_fill."
                << endl;
            pattern.clear();
            use_cegar = false;
            goal_order = true;
            skip_oversized = true;
            selection_name = "cegar_fallback_goal_fill";
        }
    } else if (use_cegar) {
        // An empty goal needs no refinement; the empty PDB is exact.
        pattern.clear();
    }

    if (!use_cegar) {
        if (goal_order) {
            variable_order_finder::VariableOrderFinder order(
                task_proxy, variable_order_finder::GOAL_CG_LEVEL);
            while (!order.done()) {
                variable_order.push_back(order.next());
            }
        } else {
            variable_order = vars->get_var_order();
        }
    }

    if (!use_cegar) {
        long product = 1;
        for (int var : variable_order) {
            long domain_size =
                task_proxy.get_variables()[var].get_domain_size();
            if (product > state_budget / domain_size) {
                if (skip_oversized) {
                    continue;
                }
                break;
            }
            product *= domain_size;
            pattern.push_back(var);
        }
    }
    sort(pattern.begin(), pattern.end());

    utils::g_log << "PDB pattern selection=" << selection_name << " ("
                 << pattern.size() << " vars, <= " << state_budget
                 << " abstract states): " << pattern << endl;

    if (!pdb) {
        pdb = pdbs::compute_pdb(task_proxy, pattern);
    }

    pdbs::Projection projection(task_proxy, pattern);
    num_abstract_states = projection.get_num_abstract_states();
    int num_vars = task_proxy.get_variables().size();

    dead_ends = vars->zeroBDD();
    for (int index = 0; index < num_abstract_states; ++index) {
        // Reconstruct the concrete-state values of the pattern variables and
        // the abstract-state BDD (conjunction over the pattern bit block).
        vector<int> state(num_vars, 0);
        BDD abstract_state = vars->oneBDD();
        for (size_t pos = 0; pos < pattern.size(); ++pos) {
            int var = pattern[pos];
            int value = projection.unrank(index, pos);
            state[var] = value;
            abstract_state *= vars->preBDD(var, value);
        }
        int distance = pdb->get_value(state);
        if (distance == numeric_limits<int>::max()) {
            dead_ends += abstract_state;
        } else {
            int value = value_cap >= 0 ? min(distance, value_cap) : distance;
            auto it = level_sets.find(value);
            if (it == level_sets.end()) {
                level_sets[value] = abstract_state;
            } else {
                it->second += abstract_state;
            }
        }
    }

    verify_against_pdb(task_proxy, *pdb, projection, 200);

    // Heuristic ADD for statistics only. The search represents infinity as a
    // separate BDD; use a fresh numeric terminal so the statistics measure an
    // isomorphic total ADD, including dead-end pruning.
    h_add = vars->constant(0);
    for (const auto &[distance, level] : level_sets) {
        h_add += level.Add() * vars->constant(distance);
    }
    if (!dead_ends.IsZero()) {
        vector<int> terminals = collect_integer_leaf_values(h_add);
        double infinity_marker =
            static_cast<double>(terminals.back()) + 1.0;
        h_add =
            dead_ends.Add().Ite(vars->constant(infinity_marker), h_add);
    }
    add_stats = compute_add_stats(
        vars, h_add, static_cast<int>(level_sets.size()));
    selected_source = selection_name;
}

void PdbLevelSets::verify_against_pdb(
    const TaskProxy &task_proxy, const pdbs::PatternDatabase &pdb,
    const pdbs::Projection &projection, int num_samples) const {
    int n = projection.get_num_abstract_states();
    int num_vars = task_proxy.get_variables().size();
    int step = max(1, n / max(1, num_samples));
    int checked = 0;
    for (int index = 0; index < n; index += step) {
        // Concrete witness: pattern variables from unrank, others set to 0.
        vector<int> state(num_vars, 0);
        for (size_t pos = 0; pos < pattern.size(); ++pos) {
            state[pattern[pos]] = projection.unrank(index, pos);
        }
        BDD state_bdd = vars->getStateBDD(state);
        int expected = pdb.get_value(state);
        if (expected == numeric_limits<int>::max()) {
            if (!(state_bdd * !dead_ends).IsZero()) {
                ABORT("PDB self-check: dead-end state not in dead_ends set.");
            }
        } else {
            if (value_cap >= 0) {
                expected = min(expected, value_cap);
            }
            auto it = level_sets.find(expected);
            if (it == level_sets.end() ||
                !(state_bdd * !it->second).IsZero()) {
                ABORT(
                    "PDB self-check: BDD level-set value disagrees with the "
                    "explicit PDB lookup.");
            }
        }
        ++checked;
    }
    utils::g_log << "PDB level-set self-check passed (" << checked
                 << " sampled abstract states)." << endl;
}

void PdbLevelSets::log_heuristic(WbhStats &stats) const {
    log_heuristic_stats(stats, add_stats);
}
}
