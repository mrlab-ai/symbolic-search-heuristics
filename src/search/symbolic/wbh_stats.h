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
    schema    {"event":"schema","version":2,
               "node_count_convention":"inner_nodes_per_piece",
               "image_count_convention":"per_piece_attempted_completed",
               "expansion_count_convention":"completed_with_attempts"}
    expand    {"event":"expand","g":G,"h":H,"completed":B,"piece_count":P,
               "bdd_nodes":N,"states":S,"image_time":T}
    image     {"event":"image","g":G,"source_buckets":B,
               "source_pieces":P,"calls_attempted":A,"calls_completed":C,...}
    partition {"event":"partition","g":G,"layer_nodes":L,
               "sum_bucket_nodes":B,"num_buckets":K}     (PR3)
    heuristic {"event":"heuristic","add_nodes":A,"num_values":V,
               "num_terminals":T,"add_level_nodes":[...],
               "width_upper_bound":U}  (PR2/PR4)
    pruned    {"event":"pruned_deadends","g":G,"states":S,"bdd_nodes":N} (PR3/PR4)
    construction {"event":"construction","heuristic":"...", ...}
    summary   {"event":"summary","expanded_bdd_nodes":N, ...}
    done      {"event":"done","effort":E,"solution_cost":C}

  Every *_nodes field counts CUDD inner nodes (DagSize - 1 per nonempty BDD).
  For a multi-piece blind frontier it is the sum over the stored BDD pieces,
  not the size of their semantic union; piece_count/source_pieces makes that
  representation explicit. Heuristic buckets are exact-union single pieces.

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
    long expanded_bdd_nodes = 0;
    double expanded_states = 0;
    int expanded_bdd_pieces = 0;
    long attempted_bdd_nodes = 0;
    double attempted_states = 0;
    int attempted_bdd_pieces = 0;
    int bucket_expansions = 0;
    int bucket_expansion_attempts = 0;
    int image_events = 0;
    int bucket_images = 0;
    int image_source_buckets = 0;
    int image_source_pieces = 0;
    int image_calls_attempted = 0;
    int image_calls_completed = 0;
    int batched_images = 0;
    double total_image_time = 0;
    bool summary_written = false;
    int events_since_flush = 0;

    void flush_periodically();

public:
    explicit WbhStats(const std::string &path);
    ~WbhStats();

    // Records one expanded forward bucket and emits the "expand" line. Only
    // forward expansions feed the effort accounting; backward expansions in
    // bidirectional search should not be logged here.
    void log_expand(
        int g, int h, bool completed, int piece_count, long bdd_nodes,
        double states, double image_time);

    // Records one high-level image event separately from logical expansion.
    // source_buckets counts logical heuristic keys; source_pieces counts BDDs
    // independently passed to (zero_)cost_image. calls_* report actual
    // per-piece invocations, including partial failures. None counts the
    // transition-relation relational products internal to a single call.
    void log_image(
        int g, int min_h, int max_h, int source_buckets, int source_pieces,
        int calls_attempted, int calls_completed, bool zero_cost,
        long bdd_nodes, double states, double image_time);

    void log_partition(
        int g, long layer_nodes, long sum_bucket_nodes, int num_buckets);

    void log_heuristic(
        long add_nodes, int num_values, int num_terminals,
        const std::vector<long> &add_level_nodes, long width_upper_bound);

    void log_pruned_deadends(int g, double states, long bdd_nodes);

    void log_construction(
        const std::string &heuristic, double seconds, int size_bound,
        int value_cap, bool completed);

    // Emits raw totals independently of whether a solution was found. This is
    // also called by the destructor, so clean failures remain measurable.
    void log_summary();

    // Emits the final "done" line with the effort computed from the recorded
    // forward expansions. Safe to call at most once; later calls are ignored.
    void log_done(int solution_cost);
};
}

#endif
