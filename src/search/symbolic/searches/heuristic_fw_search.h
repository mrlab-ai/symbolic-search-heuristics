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

    // For prune_only: cumulative level sets P_t = union of H_v for v <= t,
    // sorted by value; used to slice a layer to { s : h(s) <= t } with one
    // intersection.
    std::vector<std::pair<int, BDD>> cumulative_levels;
    BDD keep_slice(int max_h) const;

    // Open buckets keyed by (g, v). Each value is a (possibly multi-BDD)
    // bucket; BDDs are merged on selection.
    std::map<std::pair<int, int>, Bucket> open;

    bool has_current_f;
    int current_f;

    void insert_open(int g, int v, const BDD &bdd);
    bool select_min(std::pair<int, int> &key);
    int min_open_f() const;
    int value_of_state(const BDD &state) const;

public:
    HeuristicFwSearch(SymbolicSearch *eng, const SymParameters &params);

    // level_sets maps each finite heuristic value v to H_v; dead_ends is the
    // set of states with h = infinity (empty BDD if none). Both must outlive
    // the search. With prune_only the heuristic is used for pruning slices
    // only (single bucket per layer, see class comment).
    bool init(
        std::shared_ptr<SymStateSpaceManager> manager,
        const std::map<int, BDD> *level_sets, const BDD &dead_ends,
        bool prune_only = false);

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
        return open.empty();
    }
};
}

#endif
