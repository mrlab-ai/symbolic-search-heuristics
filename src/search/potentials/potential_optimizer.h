#ifndef POTENTIALS_POTENTIAL_OPTIMIZER_H
#define POTENTIALS_POTENTIAL_OPTIMIZER_H

#include "../task_proxy.h"

#include "../lp/lp_solver.h"

#include <memory>
#include <vector>

namespace plugins {
class Options;
}

namespace potentials {
class PotentialFunction;

/*
  Add admissible potential constraints to LP and allow optimizing for
  different objectives.

  The implementation is based on transforming the task into transition
  normal form (TNF) (Pommerening and Helmert, ICAPS 2015). We add an
  undefined value u to each variable's domain, but do not create
  forgetting operators or change existing operators explicitly.
  Instead, we ensure that all fact potentials of a variable V are less
  than or equal to the potential of V=u and implicitly set pre(op) to
  V=u for operators op where pre(op) is undefined. Similarly, we set
  s_\star(V) = u for variables V without a goal value.

  For more information we refer to the paper introducing potential
  heuristics

  Florian Pommerening, Malte Helmert, Gabriele Roeger and Jendrik Seipp.
  From Non-Negative to General Operator Cost Partitioning.
  AAAI 2015.

  and the paper comparing various optimization functions

  Jendrik Seipp, Florian Pommerening and Malte Helmert.
  New Optimization Functions for Potential Heuristics.
  ICAPS 2015.
*/
class PotentialOptimizer {
    std::shared_ptr<AbstractTask> task;
    TaskProxy task_proxy;
    lp::LPSolver lp_solver;
    const double max_potential;
    // Width-bounded heuristics (PR2): when true the fact-potential variables
    // are integer-valued and box-constrained to [-max_potential, max_potential],
    // turning the LP into the MIP of Fiser, Torralba & Hoffmann (AIJ 2024,
    // Sec. 3.1): forcing integrality inside the program rather than rounding
    // afterwards preserves consistency (their Fig. 1 shows naive rounding does
    // not). Integer fact potentials imply integer operator potentials Q(o)
    // (their Eq. 4) and bound the heuristic's ADD width (paper Prop. prop-pot).
    const bool integer_potentials;
    int num_lp_vars;
    std::vector<std::vector<int>> lp_var_ids;
    std::vector<std::vector<double>> fact_potentials;

    int get_lp_var_id(const FactProxy &fact) const;
    void initialize();
    void construct_lp();
    void solve_and_extract();
    void extract_lp_solution();

public:
    PotentialOptimizer(
        const std::shared_ptr<AbstractTask> &transform,
        lp::LPSolverType lpsolver, double max_potential,
        bool integer_potentials = false);
    ~PotentialOptimizer() = default;

    std::shared_ptr<AbstractTask> get_task() const;
    bool potentials_are_bounded() const;

    void optimize_for_state(const State &state);
    void optimize_for_all_states();
    void optimize_for_samples(const std::vector<State> &samples);

    bool has_optimal_solution() const;

    std::unique_ptr<PotentialFunction> get_potential_function() const;

    // The extracted fact-potential table P[var][value]. With integer_potentials
    // these are exact integers (rounded from the MIP solution). Used by the
    // symbolic level-set / ADD construction (PR3/PR4).
    const std::vector<std::vector<double>> &get_fact_potentials() const {
        return fact_potentials;
    }

    bool has_integer_potentials() const {
        return integer_potentials;
    }
};
}

#endif
