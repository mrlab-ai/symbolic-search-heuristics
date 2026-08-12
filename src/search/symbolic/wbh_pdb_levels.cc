#include "wbh_pdb_levels.h"

#include "wbh_add_stats.h"
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
    AddStats add_stats;
    int abstract_states = 0;
    bool initial_dead_end = false;
    int initial_h = 0;
    int64_t finite_sum = 0;
    int finite_count = 0;
    int dead_count = 0;
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
        : dead_ends(vars->zeroBDD()) {
    }
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
        h_add = candidate.dead_ends.Add().Ite(
            vars->constant(infinity_marker), h_add);
    }
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
    candidate->raw_max_finite_value = candidate->level_sets.rbegin()->first;
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


void log_selector_record(
    const string &kind, const CandidateSpec &spec,
    const MaterializedCandidate *candidate, int cofactor_width_budget,
    int value_cap, bool select_value_cap, bool feasible,
    const string &rejection_reason, bool emit_raw_value_histogram = false) {
    ostringstream out;
    const bool capped = value_cap >= 0;
    const bool cap_grid = select_value_cap;
    out << "{\"protocol\":\""
        << (cap_grid ? CAP_GRID_SELECTOR_PROTOCOL
                     : (capped ? CAPPED_WIDTH_SELECTOR_PROTOCOL
                               : WIDTH_SELECTOR_PROTOCOL))
        << "\",\"score_version\":\""
        << (cap_grid ? CAP_GRID_SELECTOR_SCORE
                     : (capped ? CAPPED_WIDTH_SELECTOR_SCORE
                               : WIDTH_SELECTOR_SCORE))
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
    out << ",\"cofactor_width_budget\":" << cofactor_width_budget;
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
    utils::g_log << "PDB width-selector v1 " << kind << ": " << out.str()
                 << endl;
}
}

PdbLevelSets::PdbLevelSets(
    SymVariables *vars, const shared_ptr<AbstractTask> &task, int state_budget,
    PdbPatternSelection pattern_selection, bool legacy_goal_directed,
    double cegar_max_time, int cegar_seed, int cofactor_width_budget,
    int value_cap, bool select_value_cap)
    : vars(vars), cofactor_width_budget(cofactor_width_budget),
      value_cap(value_cap), select_value_cap(select_value_cap) {
    TaskProxy task_proxy(*task);

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

        vector<CandidateSpec> specs;
        map<vector<int>, size_t> spec_by_pattern;
        auto add_spec = [&](const string &source, vector<int> candidate_pattern,
                            shared_ptr<pdbs::PatternDatabase> pdb = nullptr) {
            if (select_value_cap) {
                // Domain-one variables carry no information. Removing them is
                // semantics preserving and, together with the 100k state
                // bound, limits every cap-grid logged pattern to 16 entries.
                // Leave fixed_pool_v1 byte-for-byte behavior unchanged.
                candidate_pattern.erase(
                    remove_if(
                        candidate_pattern.begin(), candidate_pattern.end(),
                        [&](int var) {
                            return task_proxy.get_variables()[var]
                                       .get_domain_size()
                                   == 1;
                        }),
                    candidate_pattern.end());
            }
            candidate_pattern = normalized_pattern(move(candidate_pattern));
            int64_t states =
                abstract_state_count(task_proxy, candidate_pattern);
            if (states > numeric_limits<int>::max()) {
                ABORT(
                    "PDB width-selector candidate exceeds the projection "
                    "index range.");
            }
            auto [it, inserted] = spec_by_pattern.emplace(
                candidate_pattern, specs.size());
            if (inserted) {
                specs.push_back(
                    {move(candidate_pattern), {source},
                     static_cast<int>(states), states <= state_budget,
                     move(pdb)});
            } else {
                CandidateSpec &existing = specs[it->second];
                existing.sources.push_back(source);
                if (pdb && !existing.pdb) {
                    existing.pdb = move(pdb);
                }
            }
        };

        // The pool and its insertion order are part of the selector protocol.
        // The empty pattern guarantees a feasible exact-width-1 candidate.
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
                state_budget, cegar_max_time, /*use_wildcard_plans=*/true,
                cegar_seed, utils::Verbosity::NORMAL,
                /*exit_on_unsolvable=*/false);
            pdbs::PatternInformation info = generator.generate(task);
            // Copy the PatternInformation-owned pattern and retain its cached
            // PDB so the selector never recomputes the CEGAR abstraction.
            vector<int> cegar_pattern = info.get_pattern();
            shared_ptr<pdbs::PatternDatabase> cegar_pdb = info.get_pdb();
            add_spec("cegar", move(cegar_pattern), move(cegar_pdb));
        } else {
            // CEGAR assumes a first goal. For a goal-free task its exact
            // candidate is empty and deduplication records that provenance.
            add_spec("cegar", {});
        }

        unique_ptr<MaterializedCandidate> winner;
        for (CandidateSpec &spec : specs) {
            if (!spec.within_state_budget) {
                log_selector_record(
                    "candidate", spec, nullptr, cofactor_width_budget,
                    value_cap, select_value_cap, /*feasible=*/false,
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
                    bool feasible = candidate->add_stats.cofactor_width <=
                                    cofactor_width_budget;
                    log_selector_record(
                        "candidate", spec, candidate,
                        cofactor_width_budget, cap,
                        /*select_value_cap=*/true, feasible,
                        feasible ? "" : "cofactor_width_budget",
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
                bool feasible = candidate->add_stats.cofactor_width <=
                                cofactor_width_budget;
                log_selector_record(
                    "candidate", spec, candidate.get(),
                    cofactor_width_budget, value_cap,
                    /*select_value_cap=*/false, feasible,
                    feasible ? "" : "cofactor_width_budget");
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
            winner->value_cap, select_value_cap, /*feasible=*/true, "");

        pattern = winner->pattern;
        selected_source = winner->sources.front();
        num_abstract_states = winner->abstract_states;
        selected_initial_dead_end = winner->initial_dead_end;
        this->value_cap = winner->value_cap;
        level_sets = move(winner->level_sets);
        dead_ends = winner->dead_ends;
        add_stats = move(winner->add_stats);
        selection_name = select_value_cap
                             ? "exact_width_cap_filter"
                             : "exact_width_filter";

        pdbs::Projection selected_projection(task_proxy, pattern);
        verify_against_pdb(
            task_proxy, *winner->pdb, selected_projection, 200);
        utils::g_log << "PDB pattern selection=" << selection_name
                     << " (source=" << selected_source << ", "
                     << pattern.size() << " vars, " << num_abstract_states
                     << " abstract states, exact width="
                     << add_stats.cofactor_width << " <= "
                     << cofactor_width_budget;
        if (value_cap >= 0 || select_value_cap) {
            utils::g_log << ", value_cap=" << value_cap;
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
    }

    shared_ptr<pdbs::PatternDatabase> pdb;
    vector<int> variable_order;
    if (use_cegar && task_proxy.get_goals().size() > 0) {
        pdbs::PatternGeneratorCEGAR generator(
            state_budget, cegar_max_time, /*use_wildcard_plans=*/true,
            cegar_seed, utils::Verbosity::NORMAL,
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
    ADD h_add = vars->constant(0);
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
