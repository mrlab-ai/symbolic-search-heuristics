#ifndef SYMBOLIC_WBH_STATS_H
#define SYMBOLIC_WBH_STATS_H

#include <fstream>
#include <string>
#include <vector>

namespace symbolic {
/*
  JSON-lines instrumentation for the width-bounded-heuristics experiments
  (see docs/wbh-repo-map.md and paper/paper.tex). Enabled via the
  --wbh-log <path> / wbh_log=<path> option of the sym_* searches. When no
  logger is constructed (option empty) the search must behave identically, so
  every call site guards on a non-null logger and the logger itself performs
  no BDD operations beyond read-only size/minterm queries.

  Event schema (one JSON object per line):
    expand    {"event":"expand","g":G,"h":H,"bdd_nodes":N,"states":S,
               "image_time":T}
    partition {"event":"partition","g":G,"layer_nodes":L,
               "sum_bucket_nodes":B,"num_buckets":K}     (PR3)
    heuristic {"event":"heuristic","add_nodes":A,"num_values":V,
               "add_level_nodes":[...],"width_upper_bound":U}  (PR2/PR4)
    pruned    {"event":"pruned_deadends","g":G,"states":S,"bdd_nodes":N} (PR3/PR4)
    done      {"event":"done","effort":E,"solution_cost":C}

  effort is the paper's Def. def-effort: the sum of bdd_nodes over recorded
  (forward) expansions with g + h <= C and g < C, where C is the solution
  cost. Fragmentation ratios (B / L) are derived by the parser, not here.
*/
class WbhStats {
    std::ofstream out;

    struct ExpandRecord {
        int g;
        int h;
        long bdd_nodes;
    };
    std::vector<ExpandRecord> forward_expansions;
    bool done_written = false;

public:
    explicit WbhStats(const std::string &path);
    ~WbhStats();

    // Records one expanded forward bucket and emits the "expand" line. Only
    // forward expansions feed the effort accounting; backward expansions in
    // bidirectional search should not be logged here.
    void log_expand(
        int g, int h, long bdd_nodes, double states, double image_time);

    void log_partition(
        int g, long layer_nodes, long sum_bucket_nodes, int num_buckets);

    void log_heuristic(
        long add_nodes, int num_values,
        const std::vector<long> &add_level_nodes, long width_upper_bound);

    void log_pruned_deadends(int g, double states, long bdd_nodes);

    // Emits the final "done" line with the effort computed from the recorded
    // forward expansions. Safe to call at most once; later calls are ignored.
    void log_done(int solution_cost);
};
}

#endif
