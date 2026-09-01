#ifndef SYMBOLIC_WBH_INCIDENCE_SELECTOR_H
#define SYMBOLIC_WBH_INCIDENCE_SELECTOR_H

#include "sym_bucket.h"

#include <fstream>
#include <memory>
#include <string>
#include <vector>

namespace symbolic {
class SymVariables;

struct WbhIncidenceMeasurement {
    std::vector<long> by_layer;
    long total;
};

struct WbhIncidenceLayerMeasurement {
    long terminal_incidence;
    long masked_add_nodes;
    std::vector<int> active_terminal_values;
};

class WbhSelectorTrace {
public:
    virtual ~WbhSelectorTrace() = default;
    virtual void write_event(const std::string &payload) = 0;
};

// Dedicated fail-closed JSON-lines stream for the prospective selector.  It is
// intentionally separate from both frozen WBH instrumentation streams.
class WbhIncidenceTrace : public WbhSelectorTrace {
    std::ofstream out;

public:
    explicit WbhIncidenceTrace(const std::string &path);
    ~WbhIncidenceTrace();

    virtual void write_event(const std::string &payload) override;
};

// Retains semantic unions of the first target completed blind layers on a
// positive-cost task. UniformCostSearch drives this observer in detached mode.
class WbhIncidenceProbe {
    SymVariables *vars;
    const int target_layers;
    std::unique_ptr<BDD> pending_layer;
    int pending_g = -1;
    int attempts = 0;
    std::vector<int> g_values;
    std::vector<long> bdd_nodes;
    std::vector<BDD> layers;

public:
    WbhIncidenceProbe(SymVariables *vars, int target_layers);

    void prepare_layer(int g, const Bucket &pieces);
    void finish_layer(bool completed);

    bool complete() const;
    int get_target_layers() const;
    int get_attempts() const;
    const std::vector<int> &get_g_values() const;
    const std::vector<long> &get_bdd_nodes() const;
    const std::vector<BDD> &get_layers() const;

    void log_probe(
        WbhSelectorTrace &trace, double cpu_seconds, double wall_seconds,
        int peak_memory_before_kb, int peak_memory_after_kb) const;
};

WbhIncidenceLayerMeasurement measure_terminal_incidence_layer(
    SymVariables *vars, const BDD &layer, const ADD &heuristic);

WbhIncidenceMeasurement measure_terminal_incidence(
    SymVariables *vars, const std::vector<BDD> &layers,
    const ADD &heuristic);

// Small dependency-free SHA-256 used only for canonical selector trace
// attestations. Exposed so the pool and preselection encoders share one
// implementation.
std::string wbh_sha256_hex(const std::string &payload);
}

#endif
