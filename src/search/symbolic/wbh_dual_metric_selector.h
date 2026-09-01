#ifndef SYMBOLIC_WBH_DUAL_METRIC_SELECTOR_H
#define SYMBOLIC_WBH_DUAL_METRIC_SELECTOR_H

#include "wbh_cofactor_profiles.h"
#include "wbh_incidence_selector.h"

#include <fstream>
#include <string>
#include <vector>

namespace symbolic {
class SymVariables;

struct WbhDualMetricLayerMeasurement {
    long masked_add_nodes;
    std::vector<int> active_finite_values;
    bool dead_end_active;
    int active_terminal_count;
    std::vector<long> joint_cofactor_counts;
    long joint_cofactor_sum;
    long masked_joint;
};

struct WbhDualMetricMeasurement {
    WbhIncidenceMeasurement incidence;
    std::vector<WbhDualMetricLayerMeasurement> layers;
    long masked_joint_total;
    long joint_cut_entries;
};

class WbhDualMetricTrace : public WbhSelectorTrace {
    std::ofstream out;

public:
    WbhDualMetricTrace(
        const std::string &path,
        const WbhStateCutCertificate &certificate);
    virtual ~WbhDualMetricTrace();

    virtual void write_event(const std::string &payload) override;
};

std::vector<std::vector<long>> compute_wbh_probe_state_profiles(
    SymVariables *vars, const std::vector<BDD> &layers,
    const WbhStateCutCertificate &certificate);

WbhDualMetricMeasurement measure_wbh_dual_metrics(
    SymVariables *vars, const std::vector<BDD> &layers,
    const ADD &heuristic, const BDD &dead_ends, int dead_end_value,
    const WbhStateCutCertificate &certificate,
    const std::vector<std::vector<long>> &state_profiles,
    const std::vector<long> &heuristic_profile);
}

#endif
