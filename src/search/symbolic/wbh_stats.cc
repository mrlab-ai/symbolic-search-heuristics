#include "wbh_stats.h"

#include "../utils/system.h"

#include <limits>

using namespace std;

namespace symbolic {
WbhStats::WbhStats(const string &path) {
    out.open(path);
    if (!out.is_open()) {
        ABORT("Could not open WBH log file: " + path);
    }
    out << "{\"event\":\"schema\",\"version\":2,"
           "\"node_count_convention\":\"inner_nodes_per_piece\","
           "\"image_count_convention\":"
           "\"per_piece_attempted_completed\","
           "\"expansion_count_convention\":"
           "\"completed_with_attempts\"}\n";
    out.flush();
}

WbhStats::~WbhStats() {
    if (out.is_open()) {
        log_summary();
        out.flush();
        out.close();
    }
}

void WbhStats::flush_periodically() {
    // Bound data loss on externally killed runs without charging one flush
    // syscall per bucket (which would bias highly partitioned searches).
    if (++events_since_flush >= 16) {
        out.flush();
        events_since_flush = 0;
    }
}

void WbhStats::log_expand(
    int g, int h, bool completed, int piece_count, long bdd_nodes,
    double states, double image_time) {
    attempted_bdd_nodes += bdd_nodes;
    attempted_states += states;
    attempted_bdd_pieces += piece_count;
    ++bucket_expansion_attempts;
    if (completed) {
        forward_expansions.push_back({g, h, bdd_nodes});
        expanded_bdd_nodes += bdd_nodes;
        expanded_states += states;
        expanded_bdd_pieces += piece_count;
        ++bucket_expansions;
    }
    out << "{\"event\":\"expand\",\"g\":" << g << ",\"h\":" << h
        << ",\"completed\":" << (completed ? "true" : "false")
        << ",\"piece_count\":" << piece_count
        << ",\"bdd_nodes\":" << bdd_nodes << ",\"states\":" << states
        << ",\"image_time\":" << image_time << "}\n";
    flush_periodically();
}

void WbhStats::log_image(
    int g, int min_h, int max_h, int source_buckets, int source_pieces,
    int calls_attempted, int calls_completed, bool zero_cost,
    long bdd_nodes, double states, double image_time) {
    ++image_events;
    bucket_images += calls_completed;
    image_source_buckets += source_buckets;
    image_source_pieces += source_pieces;
    image_calls_attempted += calls_attempted;
    image_calls_completed += calls_completed;
    if (source_buckets > 1) {
        ++batched_images;
    }
    total_image_time += image_time;
    out << "{\"event\":\"image\",\"g\":" << g
        << ",\"min_h\":" << min_h << ",\"max_h\":" << max_h
        << ",\"source_buckets\":" << source_buckets
        << ",\"source_pieces\":" << source_pieces
        << ",\"calls_attempted\":" << calls_attempted
        << ",\"calls_completed\":" << calls_completed
        << ",\"zero_cost\":" << (zero_cost ? "true" : "false")
        << ",\"bdd_nodes\":" << bdd_nodes << ",\"states\":" << states
        << ",\"image_time\":" << image_time << "}\n";
    flush_periodically();
}

void WbhStats::log_partition(
    int g, long layer_nodes, long sum_bucket_nodes, int num_buckets) {
    out << "{\"event\":\"partition\",\"g\":" << g
        << ",\"layer_nodes\":" << layer_nodes
        << ",\"sum_bucket_nodes\":" << sum_bucket_nodes
        << ",\"num_buckets\":" << num_buckets << "}\n";
    flush_periodically();
}

void WbhStats::log_heuristic(
    long add_nodes, int num_values, int num_terminals,
    const vector<long> &add_level_nodes, long width_upper_bound) {
    out << "{\"event\":\"heuristic\",\"add_nodes\":" << add_nodes
        << ",\"num_values\":" << num_values
        << ",\"num_terminals\":" << num_terminals
        << ",\"add_level_nodes\":[";
    for (size_t i = 0; i < add_level_nodes.size(); ++i) {
        if (i > 0) {
            out << ",";
        }
        out << add_level_nodes[i];
    }
    out << "],\"width_upper_bound\":" << width_upper_bound << "}\n";
    out.flush();
}

void WbhStats::log_pruned_deadends(int g, double states, long bdd_nodes) {
    out << "{\"event\":\"pruned_deadends\",\"g\":" << g
        << ",\"states\":" << states << ",\"bdd_nodes\":" << bdd_nodes << "}\n";
    flush_periodically();
}

void WbhStats::log_construction(
    const string &heuristic, double seconds, int size_bound, int value_cap,
    bool completed) {
    out << "{\"event\":\"construction\",\"heuristic\":\"" << heuristic
        << "\",\"seconds\":" << seconds << ",\"size_bound\":" << size_bound
        << ",\"value_cap\":" << value_cap
        << ",\"completed\":" << (completed ? "true" : "false") << "}\n";
    out.flush();
}

void WbhStats::log_summary() {
    if (summary_written) {
        return;
    }
    summary_written = true;
    out << "{\"event\":\"summary\",\"expanded_bdd_nodes\":"
        << expanded_bdd_nodes << ",\"expanded_states\":" << expanded_states
        << ",\"expanded_bdd_pieces\":" << expanded_bdd_pieces
        << ",\"attempted_bdd_nodes\":" << attempted_bdd_nodes
        << ",\"attempted_states\":" << attempted_states
        << ",\"attempted_bdd_pieces\":" << attempted_bdd_pieces
        << ",\"bucket_expansions\":" << bucket_expansions
        << ",\"bucket_expansion_attempts\":" << bucket_expansion_attempts
        << ",\"image_events\":" << image_events
        << ",\"bucket_images\":" << bucket_images
        << ",\"image_source_buckets\":" << image_source_buckets
        << ",\"image_source_pieces\":" << image_source_pieces
        << ",\"image_calls_attempted\":" << image_calls_attempted
        << ",\"image_calls_completed\":" << image_calls_completed
        << ",\"batched_images\":" << batched_images
        << ",\"image_time\":" << total_image_time
        << ",\"solved\":" << (done_written ? "true" : "false") << "}\n";
    out.flush();
}

void WbhStats::log_done(int solution_cost) {
    if (done_written) {
        return;
    }
    done_written = true;
    long effort = 0;
    for (const ExpandRecord &r : forward_expansions) {
        if (r.g + r.h <= solution_cost && r.g < solution_cost) {
            effort += r.bdd_nodes;
        }
    }
    out << "{\"event\":\"done\",\"effort\":" << effort
        << ",\"solution_cost\":" << solution_cost << "}\n";
    out.flush();
    log_summary();
}
}
