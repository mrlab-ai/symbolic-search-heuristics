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
}

WbhStats::~WbhStats() {
    if (out.is_open()) {
        out.flush();
        out.close();
    }
}

void WbhStats::log_expand(
    int g, int h, long bdd_nodes, double states, double image_time) {
    forward_expansions.push_back({g, h, bdd_nodes});
    out << "{\"event\":\"expand\",\"g\":" << g << ",\"h\":" << h
        << ",\"bdd_nodes\":" << bdd_nodes << ",\"states\":" << states
        << ",\"image_time\":" << image_time << "}\n";
}

void WbhStats::log_partition(
    int g, long layer_nodes, long sum_bucket_nodes, int num_buckets) {
    out << "{\"event\":\"partition\",\"g\":" << g
        << ",\"layer_nodes\":" << layer_nodes
        << ",\"sum_bucket_nodes\":" << sum_bucket_nodes
        << ",\"num_buckets\":" << num_buckets << "}\n";
}

void WbhStats::log_heuristic(
    long add_nodes, int num_values, const vector<long> &add_level_nodes,
    long width_upper_bound) {
    out << "{\"event\":\"heuristic\",\"add_nodes\":" << add_nodes
        << ",\"num_values\":" << num_values << ",\"add_level_nodes\":[";
    for (size_t i = 0; i < add_level_nodes.size(); ++i) {
        if (i > 0) {
            out << ",";
        }
        out << add_level_nodes[i];
    }
    out << "],\"width_upper_bound\":" << width_upper_bound << "}\n";
}

void WbhStats::log_pruned_deadends(int g, double states, long bdd_nodes) {
    out << "{\"event\":\"pruned_deadends\",\"g\":" << g
        << ",\"states\":" << states << ",\"bdd_nodes\":" << bdd_nodes << "}\n";
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
}
}
