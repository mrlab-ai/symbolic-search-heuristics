#include "heuristic_fw_search.h"

#include "../sym_state_space_manager.h"
#include "../sym_variables.h"
#include "../wbh_stats.h"

#include "../../utils/logging.h"
#include "../../utils/system.h"
#include "../../utils/timer.h"
#include "../plan_reconstruction/sym_solution_cut.h"
#include "../search_algorithms/symbolic_search.h"

#include <limits>

using namespace std;

namespace symbolic {
// Sentinel returned by value_of_state when a state lies in no finite level set.
static const int NO_FINITE_VALUE = numeric_limits<int>::min();
namespace {
long inner_node_count(const BDD &bdd) {
    return max(0, bdd.nodeCount() - 1);
}
}

HeuristicFwSearch::HeuristicFwSearch(
    SymbolicSearch *eng, const SymParameters &params)
    : SymSearch(eng, params),
      closed(make_shared<ClosedList>()),
      level_sets(nullptr),
      stats(nullptr),
      prune_only(false),
      batch_f_window(0),
      has_current_f(false),
      current_f(0) {
}

bool HeuristicFwSearch::init(
    shared_ptr<SymStateSpaceManager> manager,
    const map<int, BDD> *level_sets_, const BDD &dead_ends_,
    bool prune_only_, int batch_f_window_) {
    mgr = manager;
    level_sets = level_sets_;
    dead_ends = dead_ends_;
    prune_only = prune_only_;
    batch_f_window = batch_f_window_;
    stats = sym_params.stats.get();

    if (batch_f_window < 0) {
        ABORT("batch_f_window must be nonnegative.");
    }
    if (prune_only && batch_f_window > 0) {
        ABORT("batch_f_window is only supported for heuristic bucket search, "
              "not prune_only search.");
    }

    // The search relies on the level sets being a total, disjoint partition
    // of valid states (apart from the explicit dead-end set). Check the exact
    // symbolic invariant once; sampled construction checks cannot detect a
    // missing or overlapping region that would silently drop/duplicate states.
    BDD valid = mgr->getVars()->validStates();
    BDD seen = mgr->zeroBDD();
    for (const auto &[value, level] : *level_sets) {
        (void)value;
        BDD restricted = level * valid;
        if (!(seen * restricted).IsZero()) {
            ABORT("Heuristic finite level sets overlap on valid states.");
        }
        seen += restricted;
    }
    BDD valid_dead_ends = dead_ends * valid;
    if (!(seen * valid_dead_ends).IsZero()) {
        ABORT("Heuristic finite and dead-end level sets overlap.");
    }
    BDD covered = seen + valid_dead_ends;
    if (!(valid * !covered).IsZero()) {
        ABORT("Heuristic level sets do not cover every valid state.");
    }

    if (prune_only) {
        // Cumulative slices P_t = union_{v <= t} H_v for one-intersection
        // interval pruning.
        BDD acc = mgr->zeroBDD();
        for (const auto &[value, level] : *level_sets) {
            acc += level;
            cumulative_levels.emplace_back(value, acc);
        }
    }

    if (mgr->has_zero_cost_transition()) {
        // Positive-cost assumption (paper). Exit cleanly as unsupported rather
        // than aborting, so the task is cleanly excluded in experiments.
        utils::g_log << "Heuristic symbolic forward search requires positive "
                        "operator costs; task has zero-cost operators "
                        "(unsupported)."
                     << endl;
        utils::exit_with(utils::ExitCode::SEARCH_UNSUPPORTED);
    }

    closed->init(mgr.get());

    // Goal-seeded closed list for solution detection/reconstruction, exactly
    // as blind forward search seeds it.
    perfectHeuristic = make_shared<ClosedList>();
    perfectHeuristic->init(mgr.get());
    perfectHeuristic->insert(0, mgr->get_goal());

    BDD initial_state = mgr->get_initial_state();
    int v0 = value_of_state(initial_state);
    if (v0 == NO_FINITE_VALUE) {
        // The initial state maps to an infinite heuristic value (e.g. a
        // dead-end abstract state for a PDB): the task is unsolvable.
        utils::g_log << "Initial state has infinite heuristic value; task is "
                        "unsolvable."
                     << endl;
        utils::exit_with(utils::ExitCode::SEARCH_UNSOLVABLE);
    }
    // In prune-only mode the open list is keyed by g alone (v = 0), matching
    // blind expansion order; the heuristic acts only through slice pruning.
    insert_open(0, prune_only ? 0 : v0, initial_state);

    engine->setLowerBound(prune_only ? 0 : 0 + v0);
    engine->setMinG(0);
    return true;
}

BDD HeuristicFwSearch::keep_slice(int max_h) const {
    // Union of H_v for v <= max_h (zero BDD if below all values).
    BDD result = mgr->zeroBDD();
    for (const auto &[value, cumulative] : cumulative_levels) {
        if (value > max_h) {
            break;
        }
        result = cumulative;
    }
    return result;
}

int HeuristicFwSearch::value_of_state(const BDD &state) const {
    for (const auto &[value, level] : *level_sets) {
        if (!(state * level).IsZero()) {
            return value;
        }
    }
    return NO_FINITE_VALUE;
}

void HeuristicFwSearch::insert_open(int g, int v, const BDD &bdd) {
    if (!bdd.IsZero()) {
        open[{g, v}].push_back(bdd);
    }
}

bool HeuristicFwSearch::select_min(pair<int, int> &key) {
    // Minimum f = g + v, ties broken by smaller g (paper's tie-break, which is
    // load-bearing for the effort-accounting lemma).
    bool found = false;
    int best_f = 0;
    int best_g = 0;
    auto consider = [&](const auto &entries) {
        for (const auto &entry : entries) {
            int g = entry.first.first;
            int v = entry.first.second;
            int f = g + v;
            if (!found || f < best_f || (f == best_f && g < best_g)) {
                found = true;
                best_f = f;
                best_g = g;
                key = entry.first;
            }
        }
    };
    consider(open);
    consider(preexpanded);
    return found;
}

int HeuristicFwSearch::min_open_f() const {
    int best = numeric_limits<int>::max();
    auto consider = [&](const auto &entries) {
        for (const auto &entry : entries) {
            best = min(best, entry.first.first + entry.first.second);
        }
    };
    consider(open);
    consider(preexpanded);
    return best;
}

void HeuristicFwSearch::step() {
    stepImage(0, 0);
}

void HeuristicFwSearch::stepImage(int maxTime, int maxNodes) {
    pair<int, int> key;
    if (!select_min(key)) {
        has_current_f = false;
        engine->setLowerBound(numeric_limits<int>::max());
        return;
    }
    int g = key.first;
    int v = key.second;
    current_f = g + v;
    has_current_f = true;
    engine->setLowerBound(current_f);

    Bucket fresh_bucket;
    auto fresh_it = open.find(key);
    if (fresh_it != open.end()) {
        fresh_bucket = move(fresh_it->second);
        open.erase(fresh_it);
    }
    Bucket cached_bucket;
    auto cached_it = preexpanded.find(key);
    if (cached_it != preexpanded.end()) {
        cached_bucket = move(cached_it->second);
        preexpanded.erase(cached_it);
    }

    // Keep fresh and speculatively imaged states separate until after
    // duplicate filtering. A key can receive new states after its first image;
    // only that fresh remainder needs another image.
    BDD fresh_states = mgr->zeroBDD();
    for (const BDD &b : fresh_bucket) {
        fresh_states += b;
    }
    BDD cached_states = mgr->zeroBDD();
    for (const BDD &b : cached_bucket) {
        cached_states += b;
    }
    BDD states = fresh_states + cached_states;

    // Solution detection on the selected bucket (goal test on selected, not
    // generated, buckets), reusing the blind forward cut machinery.
    SymSolutionCut sol = perfectHeuristic->getCheapestCut(states, g, true);
    if (sol.get_f() >= 0) {
        engine->new_solution(sol);
    }
    // Prune states already closed in the opposite (goal) direction, as blind
    // forward search does, and then subtract our own closed list (delayed).
    BDD live = perfectHeuristic->notClosed() * closed->notClosed();
    cached_states *= live;
    fresh_states *= live;
    // A state may have been regenerated into the same key after its
    // speculative image. Do not image that state twice.
    fresh_states *= !cached_states;

    if (engine->solved()) {
        return;
    }

    // Prune-only: re-apply the interval slice at selection time, since the
    // anytime upper bound may have tightened after this bucket was generated
    // (e.g. by the solution cut just above).
    if (prune_only) {
        int upper_bound = engine->getUpperBound();
        if (upper_bound < numeric_limits<int>::max()) {
            cached_states *= keep_slice(upper_bound - 1 - g);
            fresh_states *= keep_slice(upper_bound - 1 - g);
        }
        states = cached_states + fresh_states;
        if (states.IsZero()) {
            has_current_f = false;
            engine->setLowerBound(min_open_f());
            return;
        }
    }

    // Mutex filtering (idempotent; same setting as blind search). Reduces to
    // the identical set blind produces for this layer.
    Bucket cached_filtered{cached_states};
    mgr->filter_mutex(cached_filtered, true, g == 0);
    remove_zero(cached_filtered);
    cached_states = mgr->zeroBDD();
    for (const BDD &b : cached_filtered) {
        cached_states += b;
    }
    Bucket fresh_filtered{fresh_states};
    mgr->filter_mutex(fresh_filtered, true, g == 0);
    remove_zero(fresh_filtered);
    fresh_states = mgr->zeroBDD();
    for (const BDD &b : fresh_filtered) {
        fresh_states += b;
    }
    fresh_states *= !cached_states;
    states = cached_states + fresh_states;
    if (states.IsZero()) {
        has_current_f = false;
        engine->setLowerBound(min_open_f());
        return;
    }

    // Close the expanded bucket.
    closed->insert(g, states);

    long bdd_nodes = inner_node_count(states);
    double num_states = mgr->getVars()->numStates(states);

    // Image (cost transitions only; positive-cost assumption checked in init).
    // With batching, add fresh buckets at the same g whose f lies in the
    // opt-in lookahead window. Different-g buckets must never be unioned: the
    // image operation would erase the path-cost label needed for g'. The raw
    // extra bucket remains in preexpanded so A* lower-bound, goal-test, and
    // closed-list order are unchanged. Filtering is monotone, so imaging its
    // currently live subset can only overgenerate relative to its later
    // logical expansion, never miss a later-live transition.
    BDD image_source = fresh_states;
    int image_source_buckets = fresh_states.IsZero() ? 0 : 1;
    int min_source_h = v;
    int max_source_h = v;
    vector<pair<pair<int, int>, BDD>> staged_preexpanded;
    if (batch_f_window > 0 && !fresh_states.IsZero()) {
        const long long window_limit =
            static_cast<long long>(current_f) + batch_f_window;
        for (const auto &entry : open) {
            const int extra_g = entry.first.first;
            const int extra_h = entry.first.second;
            if (extra_g != g ||
                static_cast<long long>(extra_g) + extra_h > window_limit) {
                continue;
            }

            const pair<int, int> extra_key = entry.first;
            BDD extra_raw = mgr->zeroBDD();
            for (const BDD &b : entry.second) {
                extra_raw += b;
            }
            if (extra_raw.IsZero()) {
                continue;
            }
            // Retain raw states for the deferred goal test. In particular,
            // goal states are excluded from the image but must remain queued.
            BDD already_preexpanded = mgr->zeroBDD();
            auto pending_it = preexpanded.find(extra_key);
            if (pending_it != preexpanded.end()) {
                for (const BDD &b : pending_it->second) {
                    already_preexpanded += b;
                }
            }

            BDD extra_live = extra_raw * perfectHeuristic->notClosed();
            extra_live *= closed->notClosed();
            extra_live *= !already_preexpanded;
            Bucket extra_filtered{extra_live};
            mgr->filter_mutex(extra_filtered, true, extra_g == 0);
            remove_zero(extra_filtered);
            extra_live = mgr->zeroBDD();
            for (const BDD &b : extra_filtered) {
                extra_live += b;
            }
            if (!extra_live.IsZero()) {
                image_source += extra_live;
                ++image_source_buckets;
                min_source_h = min(min_source_h, extra_h);
                max_source_h = max(max_source_h, extra_h);
            }
            staged_preexpanded.emplace_back(extra_key, extra_raw);
        }
    }

    utils::Timer image_timer;
    map<int, Bucket> image;
    if (!image_source.IsZero()) {
        mgr->set_time_limit(maxTime);
        try {
            mgr->cost_image(true, image_source, image, maxNodes);
            mgr->unset_time_limit();
        } catch (...) {
            mgr->unset_time_limit();
            double failed_image_time = image_timer();
            if (stats) {
                stats->log_expand(
                    g, v, false, 1, bdd_nodes, num_states,
                    failed_image_time);
                stats->log_image(
                    g, min_source_h, max_source_h, image_source_buckets, 1,
                    1, 0, false, inner_node_count(image_source),
                    mgr->getVars()->numStates(image_source),
                    failed_image_time);
            }
            throw;
        }
    }
    // Commit speculative queue mutations only after the complete union image
    // succeeds. On BDDError the open buckets remain untouched; the heuristic
    // search remains fail-fast, matching its legacy image path.
    for (const auto &[extra_key, extra_raw] : staged_preexpanded) {
        open.erase(extra_key);
        preexpanded[extra_key].push_back(extra_raw);
    }
    double image_time = image_source.IsZero() ? 0.0 : image_timer();

    if (stats) {
        stats->log_expand(
            g, v, true, 1, bdd_nodes, num_states, image_time);
        if (!image_source.IsZero()) {
            stats->log_image(
                g, min_source_h, max_source_h, image_source_buckets, 1,
                1, 1, false, inner_node_count(image_source),
                mgr->getVars()->numStates(image_source), image_time);
        }
    }

    // Partition each successor layer by the heuristic level sets (product at
    // evaluation) and insert the resulting (g', v') buckets into open.
    for (auto &cost_and_bucket : image) {
        int g2 = g + cost_and_bucket.first;
        Bucket &succ_bucket = cost_and_bucket.second;
        BDD successors = mgr->zeroBDD();
        for (const BDD &b : succ_bucket) {
            successors += b;
        }
        if (successors.IsZero()) {
            continue;
        }

        // Discard dead ends (h = infinity) before partitioning and count them
        // (paper's pruned_deadends event). Empty for potentials.
        if (!dead_ends.IsZero()) {
            BDD pruned = successors * dead_ends;
            if (!pruned.IsZero()) {
                if (stats) {
                    stats->log_pruned_deadends(
                        g2, mgr->getVars()->numStates(pruned),
                        inner_node_count(pruned));
                }
                successors *= !dead_ends;
                if (successors.IsZero()) {
                    continue;
                }
            }
        }

        if (prune_only) {
            // Prune-only variant: keep the layer whole; discard the interval
            // slice { s : g2 + h(s) >= U } once an anytime upper bound U is
            // known from the engine's solution cuts (states there cannot lie
            // on a plan cheaper than U). One intersection, one open bucket.
            int upper_bound = engine->getUpperBound();
            if (upper_bound < numeric_limits<int>::max()) {
                successors *= keep_slice(upper_bound - 1 - g2);
                if (successors.IsZero()) {
                    continue;
                }
            }
            insert_open(g2, 0, successors);
            continue;
        }

        long layer_nodes = inner_node_count(successors);
        long sum_bucket_nodes = 0;
        int num_buckets = 0;
        for (const auto &value_and_level : *level_sets) {
            int vv = value_and_level.first;
            BDD partition = successors * value_and_level.second;
            if (!partition.IsZero()) {
                insert_open(g2, vv, partition);
                sum_bucket_nodes += inner_node_count(partition);
                ++num_buckets;
            }
        }
        if (stats) {
            stats->log_partition(
                g2, layer_nodes, sum_bucket_nodes, num_buckets);
        }
    }

    has_current_f = false;
    engine->setLowerBound(min_open_f());
}
}
