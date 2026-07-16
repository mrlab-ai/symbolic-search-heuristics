#ifndef SYMBOLIC_SEARCHES_HEURISTIC_FW_SEARCH_H
#define SYMBOLIC_SEARCHES_HEURISTIC_FW_SEARCH_H

#include "sym_search.h"

#include "../closed_list.h"
#include "../sym_bucket.h"

#include <map>
#include <memory>
#include <utility>

namespace symbolic {
class PotentialLevelSets;
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

    const PotentialLevelSets *levels;
    WbhStats *stats;

    // Open buckets keyed by (g, v). Each value is a (possibly multi-BDD)
    // bucket; BDDs are merged on selection.
    std::map<std::pair<int, int>, Bucket> open;

    bool has_current_f;
    int current_f;

    void insert_open(int g, int v, const BDD &bdd);
    bool select_min(std::pair<int, int> &key);
    int min_open_f() const;

public:
    HeuristicFwSearch(SymbolicSearch *eng, const SymParameters &params);

    bool init(
        std::shared_ptr<SymStateSpaceManager> manager,
        const PotentialLevelSets *levels);

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
