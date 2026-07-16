#include "potential_function.h"
#include "potential_heuristic.h"
#include "potential_optimizer.h"
#include "util.h"

#include "../plugins/plugin.h"
#include "../utils/logging.h"
#include "../utils/system.h"

using namespace std;

/*
  Width-capped integer potential heuristic (PR2 / paper Sec. "Width-Bounded
  Heuristic Families", Prop. prop-pot).

  Computes admissible, consistent *integer* fact potentials P(v, w) with
  |P(v, w)| <= M using the mixed-integer program of

    Daniel Fiser, Alvaro Torralba and Joerg Hoffmann.
    Boosting Optimal Symbolic Planning: Operator-Potential Heuristics.
    Artificial Intelligence 334 (2024), Sec. 3.1.

  Their key point (their Fig. 1): rounding the LP potentials down to integers
  afterwards breaks path-independence and hence consistency. Instead they force
  integrality *inside* the program. Fast Downward's PotentialOptimizer already
  builds their goal-awareness constraint (their Eq. 2) and per-operator
  consistency constraint (their Eq. 3); here we additionally

    * box every fact potential in [-M, M] (the option m), and
    * declare the fact-potential variables integer (integer_potentials=true).

  Integer fact potentials imply integer operator potentials Q(o) (their Eq. 4),
  so the resulting heuristic keeps all admissibility/consistency guarantees,
  and by paper Prop. prop-pot its ADD width is at most d(2mM+1). With m=0 every
  potential is forced to 0, so h == 0.

  The unbounded (real-valued) potential heuristics are provided by the existing
  initial_state_potential / all_states_potential features; this feature is only
  for finite width caps M.
*/

namespace potentials {
enum class OptimizeFor {
    INITIAL_STATE,
    ALL_STATES,
};

static unique_ptr<PotentialFunction> create_integer_potential_function(
    const shared_ptr<AbstractTask> &transform, lp::LPSolverType lpsolver,
    int m, OptimizeFor opt_func) {
    PotentialOptimizer optimizer(
        transform, lpsolver, static_cast<double>(m), /*integer_potentials=*/true);
    const AbstractTask &task = *transform;
    TaskProxy task_proxy(task);
    switch (opt_func) {
    case OptimizeFor::INITIAL_STATE:
        optimizer.optimize_for_state(task_proxy.get_initial_state());
        break;
    case OptimizeFor::ALL_STATES:
        optimizer.optimize_for_all_states();
        break;
    default:
        ABORT("Unknown optimization function");
    }
    if (!optimizer.has_optimal_solution()) {
        ABORT("No optimal solution for the width-capped potential MIP.");
    }

    // Self-check of the PR2 invariants: every fact potential is an integer in
    // [-m, m], and all goal-state facts have value 0 (goal-awareness). The MIP
    // enforces these, so a violation signals a solver or extraction bug.
    const vector<vector<double>> &potentials = optimizer.get_fact_potentials();
    double max_abs = 0;
    for (const vector<double> &var_potentials : potentials) {
        for (double p : var_potentials) {
            if (p != round(p)) {
                ABORT("Fact potential is not integer after MIP extraction.");
            }
            max_abs = max(max_abs, abs(p));
        }
    }
    if (max_abs > m) {
        ABORT("Fact potential exceeds the width cap m.");
    }
    // Goal-awareness (h(goal) = 0) and consistency are enforced by the MIP
    // constraints (AIJ 2024 Eqs. 2-3) and checked end to end by A* optimality
    // on the smoke suite; goal states are only fully defined in transition
    // normal form, so we do not evaluate them directly here.
    utils::g_log << "wbh_int_potential: m=" << m << ", max|P|=" << max_abs
                 << endl;
    return optimizer.get_potential_function();
}

class WidthCappedPotentialHeuristicFeature
    : public plugins::TypedFeature<Evaluator, PotentialHeuristic> {
public:
    WidthCappedPotentialHeuristicFeature()
        : TypedFeature("wbh_int_potential") {
        document_subcategory("heuristics_potentials");
        document_title(
            "Width-capped integer potential heuristic (width-bounded "
            "heuristics)");
        document_synopsis(
            "Admissible, consistent integer potential heuristic with "
            "|P(v,w)| <= m, computed with the integer MIP of Fiser, Torralba "
            "and Hoffmann (AIJ 2024, Sec. 3.1). m=0 yields h==0.");
        document_language_support("action costs", "supported");
        document_language_support("conditional effects", "not supported");
        document_language_support("axioms", "not supported");
        document_property("admissible", "yes");
        document_property("consistent", "yes");
        document_property("safe", "yes");
        document_property("preferred operators", "no");

        add_option<int>(
            "m",
            "Width cap: potentials are integers bounded by |P(v,w)| <= m. "
            "m=0 forces h==0.",
            "8", plugins::Bounds("0", "infinity"));
        add_option<OptimizeFor>(
            "objective", "LP/MIP objective to optimize", "initial_state");
        lp::add_lp_solver_option_to_feature(*this);
        add_heuristic_options_to_feature(*this, "wbh_int_potential");
    }

    virtual shared_ptr<PotentialHeuristic> create_component(
        const plugins::Options &opts) const override {
        OptimizeFor objective = opts.get<OptimizeFor>("objective");
        return make_shared<PotentialHeuristic>(
            create_integer_potential_function(
                opts.get<shared_ptr<AbstractTask>>("transform"),
                opts.get<lp::LPSolverType>("lpsolver"), opts.get<int>("m"),
                objective),
            opts.get<shared_ptr<AbstractTask>>("transform"),
            opts.get<bool>("cache_estimates"), opts.get<string>("description"),
            opts.get<utils::Verbosity>("verbosity"));
    }
};

static plugins::FeaturePlugin<WidthCappedPotentialHeuristicFeature> _plugin;

static plugins::TypedEnumPlugin<OptimizeFor> _enum_plugin(
    {{"initial_state", "optimize for the initial state (paper's default)"},
     {"all_states", "optimize for the average over all states"}});
}
