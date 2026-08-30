#ifndef SYMBOLIC_WBH_PROFILE_H
#define SYMBOLIC_WBH_PROFILE_H

#include "sym_bucket.h"

#include <fstream>
#include <memory>
#include <string>
#include <vector>

namespace symbolic {
class ClosedList;
class SymVariables;
struct AddStats;

/*
  Optional complete cofactor-profile instrumentation. This is deliberately
  separate from WbhStats: --wbh_profile_log writes its own JSON-lines stream,
  and enabling it cannot change the frozen wbh.jsonl schema-v2 stream.

  Profiles are projected onto the unprimed Boolean state variables in their
  current CUDD level order. cofactor_counts therefore has one entry before
  any state bit and one after every state bit, including the terminal cut.
  BDD residual identity includes CUDD's complement polarity.
*/
class WbhProfile {
    std::ofstream out;
    std::vector<int> state_indices;
    std::vector<int> state_levels;

    struct LayerRecord {
        int g;
        long bdd_nodes;
    };
    struct PendingLayer {
        int g;
        int piece_count;
        long bdd_nodes;
        std::vector<long> cofactor_counts;
        long cofactor_width;
        double union_seconds;
        double cofactor_seconds;
    };
    std::vector<LayerRecord> forward_layers;
    std::unique_ptr<PendingLayer> pending_layer;
    SymVariables *heuristic_layer_vars = nullptr;
    std::weak_ptr<ClosedList> heuristic_closed;

    bool variable_order_written = false;
    bool heuristic_written = false;
    bool done_written = false;
    bool summary_written = false;
    long profiled_layer_attempts = 0;
    long profiled_layers = 0;
    long sum_layer_bdd_nodes = 0;
    double union_seconds = 0;
    double cofactor_seconds = 0;
    double heuristic_cofactor_seconds = 0;
    double serialization_seconds = 0;
    double output_seconds = 0;

    void verify_variable_order(SymVariables *vars) const;
    void write_payload(const std::string &payload);

public:
    explicit WbhProfile(const std::string &path);
    ~WbhProfile();

    // Emit the certificate that maps every profile position to its CUDD
    // index/level, FDR variable, and within-variable binary bit.
    void log_variable_order(SymVariables *vars);

    // Emit the selected heuristic's exact state-cut profile. Candidate
    // profiles are intentionally omitted: this event describes the heuristic
    // actually used by the search.
    void log_heuristic(SymVariables *vars, const AddStats &add_stats);

    // Attach the heuristic search's existing per-g closed unions. On a solved
    // run, log_done profiles these unions without retaining duplicate BDDs
    // during search. This supplies the semantic-union denominator needed to
    // distinguish heuristic fragmentation from search-space reduction.
    void attach_heuristic_closed(
        SymVariables *vars, const std::shared_ptr<ClosedList> &closed);

    // Semantically union all pieces of one prepared forward blind layer and
    // retain its profile until the subsequent expansion reports whether it
    // completed. Call prepare only after Frontier::prepare succeeds and then
    // exactly one finish call after Frontier::expand returns.
    void prepare_blind_layer(int g, SymVariables *vars, const Bucket &pieces);
    void finish_blind_layer(bool completed);

    // Emits the solved cost and exact-union effort over g < C. For an attached
    // heuristic search, its per-g closed unions are profiled first.
    void log_done(int solution_cost);

    // Emits aggregate event counts and the overhead split into union,
    // cofactor traversal, JSON serialization, and output time.
    void log_summary();
};
}

#endif
