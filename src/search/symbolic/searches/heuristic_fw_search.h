#ifndef SYMBOLIC_SEARCHES_HEURISTIC_FW_SEARCH_H
#define SYMBOLIC_SEARCHES_HEURISTIC_FW_SEARCH_H

#include "sym_search.h"

#include "../closed_list.h"
#include "../sym_bucket.h"

#include <map>
#include <memory>
#include <utility>

namespace symbolic {
class WbhStats;

/*
  Heuristic symbolic forward search (BDDA*, product-at-evaluation variant;
  PR3, paper Sec. "Search-Effort Guarantees").

  Forward uniform-cost search whose frontier is partitioned by the values of a
  consistent width-bounded heuristic given as precomputed level-set BDDs H_v
  (PotentialLevelSets). The open list is keyed by (g, v); buckets are selected
  in order of increasing f = g + v, ties broken by smaller g. After each image
  and (delayed) closed-list subtraction, the successor set is intersected with
  each H_v to form the (g', v') buckets (product at evaluation). The goal test
  is on the selected bucket, matching paper Def. def-effort.

  The level sets are supplied by the caller (potentials, PDBs, or
  merge-and-shrink) as a value -> H_v map plus a dead-end set (states with
  h = infinity, empty for potentials). Dead-end successors are discarded
  before insertion and counted (paper's pruned_deadends event).

  PRUNE-ONLY VARIANT (paper Cor. cor-prune): with prune_only=true the search
  keeps each layer as a single BDD like blind forward search (one image call
  per layer, no partitioning) and uses the heuristic only to discard states
  that provably cannot lie on an improving plan: the dead ends (h = infinity)
  and, once an anytime upper bound U is known from the engine's solution cuts,
  the interval slice { s : g + h(s) >= U }. By the bucket bound (paper Thm.
  thm-bucket with an interval U) each expanded layer costs at most a factor
  Wn over the blind layer -- a factor W better than the per-value partition --
  and with no bound and no dead ends the search is exactly blind.

  With the all-zero potential (M = 0) there is a single value 0 and
  H_0 = valid states, so this reduces exactly to blind symbolic forward search
  (sym_fw): the blind-equivalence invariant of PR3.

  Only positive operator costs are supported (the paper's assumption; the
  experiment suite excludes zero-cost operators). Solution detection and plan
  reconstruction reuse the standard forward closed list and cut machinery.

  UNSPLIT f-BOUND VARIANT: with unsplit_bound=true the search keeps each
  layer as a single BDD, as prune-only search does, and runs iterative
  deepening on an f-bound B, starting at B = h(s0). An iteration expands the
  layers by increasing g and discards the successors with g + h > B; the
  first goal found is optimal, since every plan of cost c <= B only visits
  states with f <= c. If an iteration ends without a plan, the next bound is
  the smallest f-value of a discarded state, which never exceeds C*. Hence
  the last iteration has B = C* and expands exactly the sets
  L_g cap {h <= C* - g}, the unsplit sets of BDDA* (paper Lemma
  lem-identity). Each iteration restarts from s0 with an empty closed list
  and is summarized in the planner log. With unsplit_bound_doubling=true,
  the bound grows at least by a step that doubles in every iteration
  (1, 2, 4, ...). Since layers are expanded by increasing g, the first goal
  found is still optimal for any bound B >= C*; overshooting only prunes
  less in the last iteration.

  OPT-IN SAME-g f-WINDOW BATCHING: batch_f_window > 0 speculatively computes
  one image for the selected fresh bucket and fresh buckets with the same g
  and f <= selected_f + batch_f_window. Same-g is essential because a BDD
  union otherwise loses the parent path-cost label. Extra buckets remain
  pending at their original (g, h): goal tests and closed-list insertion still
  occur in exact (f, g) order. For a consistent heuristic, successors have
  f' >= f; with positive costs, equal-f successors have greater g. Hence early
  successors cannot overtake their pending source. Speculation may overgenerate
  states later removed as duplicates, but never removes a normally expanded
  state. The heuristic families wired to this search are consistent. The
  global symbolic options batch_max_union_nodes and batch_max_union_ratio can
  additionally reject an eligible extra bucket when its candidate image-source
  union is too large. Both default to 0 (disabled), which exactly preserves the
  fixed-window policy.
*/
class HeuristicFwSearch : public SymSearch {
    std::shared_ptr<ClosedList> closed;
    // Goal-seeded closed list of the opposite direction, used exactly as in
    // blind forward search to detect and reconstruct solutions via cuts.
    std::shared_ptr<ClosedList> perfectHeuristic;

    const std::map<int, BDD> *level_sets;
    BDD dead_ends;
    WbhStats *stats;
    bool prune_only;
    int batch_f_window;
    bool unsplit_bound;
    bool unsplit_bound_doubling;

    // Unsplit f-bound state: current bound, smallest f-value of a discarded
    // state in this iteration, and per-iteration counters for the log.
    int f_bound;
    int next_f_bound;
    int bound_step;
    BDD initial_state;
    int iteration;
    long iteration_nodes;
    int iteration_layers;
    void restart_iteration();
    void log_iteration(bool solved) const;

    // For prune_only and unsplit_bound: cumulative level sets P_t = union of H_v for v <= t,
    // sorted by value; used to slice a layer to { s : h(s) <= t } with one
    // intersection.
    std::vector<std::pair<int, BDD>> cumulative_levels;
    BDD keep_slice(int max_h) const;

    // Open buckets keyed by (g, v). Each value is a (possibly multi-BDD)
    // bucket; BDDs are merged on selection.
    std::map<std::pair<int, int>, Bucket> open;

    // Buckets whose image was already computed speculatively as part of a
    // same-g f-window. They remain here, at their original (g, h) key, until
    // normal A* selection performs the goal test and inserts them into closed.
    // This is load-bearing: speculative imaging must not advance logical A*
    // expansion/closing order.
    std::map<std::pair<int, int>, Bucket> preexpanded;

    bool has_current_f;
    int current_f;

    // Aggregate diagnostics for the optional adaptive batching gate. Keeping
    // these here avoids per-image log traffic that would perturb the timings
    // being measured. They remain untouched when both gates are disabled.
    long long batch_eligible_extras = 0;
    long long batch_accepted_extras = 0;
    long long batch_rejected_node_limit = 0;
    long long batch_rejected_node_ratio = 0;
    long batch_max_candidate_union_nodes = 0;
    long batch_max_final_union_nodes = 0;
    double batch_max_candidate_union_ratio = 0.0;
    double batch_max_final_union_ratio = 0.0;

    void insert_open(int g, int v, const BDD &bdd);
    bool select_min(std::pair<int, int> &key);
    int min_open_f() const;
    int value_of_state(const BDD &state) const;

public:
    HeuristicFwSearch(SymbolicSearch *eng, const SymParameters &params);
    virtual ~HeuristicFwSearch() override;

    // level_sets maps each finite heuristic value v to H_v; dead_ends is the
    // set of states with h = infinity (empty BDD if none). Both must outlive
    // the search. With prune_only the heuristic is used for pruning slices
    // only (single bucket per layer, see class comment).
    bool init(
        std::shared_ptr<SymStateSpaceManager> manager,
        const std::map<int, BDD> *level_sets, const BDD &dead_ends,
        bool prune_only = false, int batch_f_window = 0,
        bool unsplit_bound = false, bool unsplit_bound_doubling = false);

    std::shared_ptr<ClosedList> getClosedShared() const {
        return closed;
    }

    void step() override;
    void stepImage(int maxTime, int maxNodes) override;

    std::string get_last_dir() const override {
        return "FW";
    }

    int getF() const override {
        return has_current_f ? current_f : min_open_f();
    }

    bool finished() const override {
        return open.empty() && preexpanded.empty();
    }
};
}

#endif
