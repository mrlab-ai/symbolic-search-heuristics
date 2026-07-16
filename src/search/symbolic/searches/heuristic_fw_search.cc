#include "heuristic_fw_search.h"

#include "../sym_state_space_manager.h"
#include "../sym_variables.h"
#include "../wbh_potential_levels.h"
#include "../wbh_stats.h"

#include "../../utils/system.h"
#include "../../utils/timer.h"
#include "../plan_reconstruction/sym_solution_cut.h"
#include "../search_algorithms/symbolic_search.h"

#include <limits>

using namespace std;

namespace symbolic {
HeuristicFwSearch::HeuristicFwSearch(
    SymbolicSearch *eng, const SymParameters &params)
    : SymSearch(eng, params),
      closed(make_shared<ClosedList>()),
      levels(nullptr),
      stats(nullptr),
      has_current_f(false),
      current_f(0) {
}

bool HeuristicFwSearch::init(
    shared_ptr<SymStateSpaceManager> manager,
    const PotentialLevelSets *levels_) {
    mgr = manager;
    levels = levels_;
    stats = sym_params.stats.get();

    if (mgr->has_zero_cost_transition()) {
        ABORT(
            "Heuristic symbolic forward search (sym_fw_pot) requires positive "
            "operator costs (the width-bounded-heuristics assumption; the "
            "experiment suite excludes zero-cost operators).");
    }

    closed->init(mgr.get());

    // Goal-seeded closed list for solution detection/reconstruction, exactly
    // as blind forward search seeds it.
    perfectHeuristic = make_shared<ClosedList>();
    perfectHeuristic->init(mgr.get());
    perfectHeuristic->insert(0, mgr->get_goal());

    BDD initial_state = mgr->get_initial_state();
    int v0 = levels->value_of_state(initial_state);
    insert_open(0, v0, initial_state);

    engine->setLowerBound(0 + v0);
    engine->setMinG(0);
    return true;
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
    for (const auto &entry : open) {
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
    return found;
}

int HeuristicFwSearch::min_open_f() const {
    int best = numeric_limits<int>::max();
    for (const auto &entry : open) {
        best = min(best, entry.first.first + entry.first.second);
    }
    return best;
}

void HeuristicFwSearch::step() {
    stepImage(0, 0);
}

void HeuristicFwSearch::stepImage(int maxTime, int maxNodes) {
    pair<int, int> key;
    if (!select_min(key)) {
        engine->setLowerBound(numeric_limits<int>::max());
        return;
    }
    int g = key.first;
    int v = key.second;
    current_f = g + v;
    has_current_f = true;
    engine->setLowerBound(current_f);

    Bucket bucket = move(open[key]);
    open.erase(key);

    // Merge the bucket into a single BDD (exact OR, no truncation).
    BDD states = mgr->zeroBDD();
    for (const BDD &b : bucket) {
        states += b;
    }

    // Solution detection on the selected bucket (goal test on selected, not
    // generated, buckets), reusing the blind forward cut machinery.
    SymSolutionCut sol = perfectHeuristic->getCheapestCut(states, g, true);
    if (sol.get_f() >= 0) {
        engine->new_solution(sol);
    }
    // Prune states already closed in the opposite (goal) direction, as blind
    // forward search does, and then subtract our own closed list (delayed).
    states *= perfectHeuristic->notClosed();
    states *= closed->notClosed();

    if (engine->solved()) {
        return;
    }

    // Mutex filtering (idempotent; same setting as blind search). Reduces to
    // the identical set blind produces for this layer.
    Bucket filtered{states};
    mgr->filter_mutex(filtered, true, g == 0);
    remove_zero(filtered);
    states = mgr->zeroBDD();
    for (const BDD &b : filtered) {
        states += b;
    }
    if (states.IsZero()) {
        return;
    }

    // Close the expanded bucket.
    closed->insert(g, states);

    long bdd_nodes = states.nodeCount();
    double num_states = mgr->getVars()->numStates(states);

    // Image (cost transitions only; positive-cost assumption checked in init).
    utils::Timer image_timer;
    map<int, Bucket> image;
    mgr->set_time_limit(maxTime);
    mgr->cost_image(true, states, image, maxNodes);
    mgr->unset_time_limit();
    double image_time = image_timer();

    if (stats) {
        stats->log_expand(g, v, bdd_nodes, num_states, image_time);
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
        long layer_nodes = successors.nodeCount();
        long sum_bucket_nodes = 0;
        int num_buckets = 0;
        for (const auto &value_and_level : levels->get_level_sets()) {
            int vv = value_and_level.first;
            BDD partition = successors * value_and_level.second;
            if (!partition.IsZero()) {
                insert_open(g2, vv, partition);
                sum_bucket_nodes += partition.nodeCount();
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
