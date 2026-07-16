/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_POT_H__
#define __PDDL_POT_H__

#include <pddl/segmarr.h>
#include <pddl/fdr.h>
#include <pddl/mg_strips.h>
#include <pddl/disambiguation.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_pot_solution {
    /** Potentials for all facts */
    double *pot;
    int pot_size;
    /** Objective value */
    double objval;
    /** Change of heuristic value for each operator */
    double *op_pot;
    int op_pot_size;

    /** True if a solution was found */
    pddl_bool_t found;
    /** Set true if the solution is suboptimal */
    pddl_bool_t suboptimal;
    /** True if the computed timed out */
    pddl_bool_t timed_out;
    /** True if error occurred */
    pddl_bool_t error;
};
typedef struct pddl_pot_solution pddl_pot_solution_t;

void pddlPotSolutionInit(pddl_pot_solution_t *sol);
void pddlPotSolutionFree(pddl_pot_solution_t *sol);
double pddlPotSolutionEvalFDRStateFlt(const pddl_pot_solution_t *sol,
                                      const pddl_fdr_vars_t *vars,
                                      const int *state);
int pddlPotSolutionEvalFDRState(const pddl_pot_solution_t *sol,
                                const pddl_fdr_vars_t *vars,
                                const int *state);
int pddlPotSolutionRoundHValue(double hvalue);
double pddlPotSolutionEvalStripsStateFlt(const pddl_pot_solution_t *sol,
                                         const pddl_iset_t *state);
int pddlPotSolutionEvalStripsState(const pddl_pot_solution_t *sol,
                                   const pddl_iset_t *state);

struct pddl_pot_solutions {
    pddl_pot_solution_t *sol;
    int sol_size;
    int sol_alloc;
    /** True if the input task is proved unsolvable */
    int unsolvable;
};
typedef struct pddl_pot_solutions pddl_pot_solutions_t;

void pddlPotSolutionsInit(pddl_pot_solutions_t *sols);
void pddlPotSolutionsFree(pddl_pot_solutions_t *sols);
void pddlPotSolutionsAdd(pddl_pot_solutions_t *sols,
                         const pddl_pot_solution_t *sol);
int pddlPotSolutionsEvalMaxFDRState(const pddl_pot_solutions_t *sols,
                                    const pddl_fdr_vars_t *vars,
                                    const int *fdr_state);

struct pddl_pot_constr {
    pddl_iset_t plus;
    pddl_iset_t minus;
    char sense;
    double rhs;
};
typedef struct pddl_pot_constr pddl_pot_constr_t;

struct pddl_pot_constrs {
    pddl_pot_constr_t *c;
    int c_size;
    int c_alloc;
};
typedef struct pddl_pot_constrs pddl_pot_constrs_t;

struct pddl_pot_maxpot_var {
    int var_id;
    int count;
};
typedef struct pddl_pot_maxpot_var pddl_pot_maxpot_var_t;

struct pddl_pot_maxpot {
    pddl_pot_maxpot_var_t *var;
    int var_size;
    int maxpot_id;
    int id;

    pddl_htable_key_t hkey;
    pddl_list_t htable;
};
typedef struct pddl_pot_maxpot pddl_pot_maxpot_t;

struct pddl_pot_maxpots {
    pddl_segmarr_t *maxpot;
    int maxpot_size;
    pddl_htable_t *htable;
};
typedef struct pddl_pot_maxpots pddl_pot_maxpots_t;

struct pddl_pot {
    /** Reference to the input task */
    const pddl_mg_strips_t *mg_strips;
    /** True if .mg_strips was created internally */
    pddl_bool_t mg_strips_own;
    /** Pre-computed disambiguation */
    pddl_disambiguate_t disamb;
    /** True if a single-fact disambiguation should be used */
    pddl_bool_t disamb_single_fact;

    /** Number of LP variables */
    int var_size;
    /** Number of LP variables corresponding to facts -- these are the
     *  variables 0 to (fact_var_size - 1) */
    int fact_var_size;
    /** Number of processed operators */
    int op_size;
    /** Objective function coeficients over fact variables. The array has
     * .fact_var_size elements. */
    double *fact_obj;

    /** Operator consistency constraints; mapping from op_id to the
     *  constraint. */
    pddl_pot_constr_t **c_op;
    /** Mapping from op_id to the constraint such that f(o) <= c(0) where
     *  f(o) upper-bounds h-value for reachable states where the operator o
     *  is applicable. */
    pddl_pot_constr_t **c_op_pre_state;
    /** True for operators op_id where the corresponding
     *  .c_op_pre_state[op_id] constraint is enabled. */
    pddl_bool_t *c_op_pre_state_enabled;
    /** Set of goal constraints */
    pddl_pot_constrs_t c_goal;
    /** Lower-bound constraint */
    pddl_pot_constr_t *c_lb;
    /** Start solution for ILP/MIP problems */
    double *start_pot;

    /** Constraints for expression maximal potential over certain set of
     *  facts. */
    pddl_pot_maxpots_t maxpot;
};
typedef struct pddl_pot pddl_pot_t;

struct pddl_pot_solve_config {
    /** If true, use ILP solver instead of LP */
    pddl_bool_t use_ilp;
    /** If true, infer integer operator-potentials */
    pddl_bool_t op_pot;
    /** If true, infer real-valued operator-potentials */
    pddl_bool_t op_pot_real;
    /** Maximum time reserved for the LP solver */
    float lp_time_limit;
};
typedef struct pddl_pot_solve_config pddl_pot_solve_config_t;

#define PDDL_POT_SOLVE_CONFIG_INIT \
    { \
        pddl_false, /* .use_ilp */ \
        pddl_false, /* .op_pot */ \
        pddl_false, /* .op_pot_real */ \
        -1.f, /* .lp_time_limit */ \
    }

/**
 * Initialize potential heuristic with mg-strips task and disambiguation.
 * If the task is detected to be unsolvable, -1 is returned.
 * Fact IDs are the same as IDs of the LP variables.
 * Returns 0 on success.
 */
int pddlPotInit(pddl_pot_t *pot,
                const pddl_mg_strips_t *mg_strips,
                const pddl_mutex_pairs_t *mutex);

/**
 * Same as pddlPotInit() but a single-fact disambiguation is used.
 */
int pddlPotInitSingleFactDisamb(pddl_pot_t *pot,
                                const pddl_mg_strips_t *mg_strips,
                                const pddl_mutex_pairs_t *mutex);

/**
 * Initialize potential heuristic with FDR planning task.
 * Global IDs of the facts are the same as IDs of the LP variables.
 */
int pddlPotInitFDR(pddl_pot_t *pot, const pddl_fdr_t *fdr);

/**
 * Free allocated memory.
 */
void pddlPotFree(pddl_pot_t *pot);

/**
 * Set full objective function, coef must have pot->fact_var_size elements.
 */
void pddlPotSetObj(pddl_pot_t *pot, const double *coef);

/**
 * Set objective function to the given state.
 * This will work only if {pot} was initialized with *InitFDR()
 */
void pddlPotSetObjFDRState(pddl_pot_t *pot,
                           const pddl_fdr_vars_t *vars,
                           const int *state);

/**
 * Set objective function to all syntactic states.
 * This will work only if {pot} was initialized with *InitFDR()
 */
void pddlPotSetObjFDRAllSyntacticStates(pddl_pot_t *pot,
                                        const pddl_fdr_vars_t *vars);

/**
 * Set objective function to the given state.
 * This works only if {pot} was initialized with *InitMGStrips() or
 * *InitStrips().
 */
void pddlPotSetObjStripsState(pddl_pot_t *pot, const pddl_iset_t *state);

/**
 * Sets lower bound constraint as sum(vars) >= rhs
 */
void pddlPotSetLowerBoundConstr(pddl_pot_t *pot,
                                const pddl_iset_t *vars,
                                double rhs);

/**
 * Removes the lower bound constraints.
 */
void pddlPotResetLowerBoundConstr(pddl_pot_t *pot);

/**
 * Returns RHS of the lower bound constraint
 */
double pddlPotGetLowerBoundConstrRHS(const pddl_pot_t *pot);

/**
 * Decrease the RHS of the previously set lower bound constraint.
 */
void pddlPotDecreaseLowerBoundConstrRHS(pddl_pot_t *pot, double decrease);

/**
 * Set the consistency constraint for the specified operator o to be
 *      min(f(o),s(o)) <= c(o)
 * where f(o) is the standard consistency constraint, and s(o) is an upper
 * bound on the potential in reachable states where o is applicable.
 */
void pddlPotSetMinOpConsistencyConstr(pddl_pot_t *pot, int op_id);

/**
 * Disables the corresponding constraint previously set with
 * pddlPotSetMinOpConsistencyConstr().
 */
void pddlPotDisableMinOpConsistencyConstr(pddl_pot_t *pot, int op_id);

/**
 * Call pddlPotSetMinOpConsistencyConstr() on all operators.
 */
void pddlPotSetMinOpConsistencyConstrAll(pddl_pot_t *pot);

/**
 * Call pddlPotDisableMinOpConsistencyConstr() on all operators.
 */
void pddlPotDisableMinOpConsistencyConstrAll(pddl_pot_t *pot);

/**
 * This passes the specified potentials as a start solution.
 * This has effect only if the MIP/ILP problem is being solved and the
 * underlying solver supports it.
 */
void pddlPotSetStartSolution(pddl_pot_t *pot, const pddl_pot_solution_t *sol);

/**
 * Removes start solution previously set with pddlPotSetStartSolution()
 */
void pddlPotResetStartSolution(pddl_pot_t *pot);

/**
 * Solve the LP problem and returns the solution via sol.
 * Return 0 on success, -1 if solution was not found.
 */
int pddlPotSolve(const pddl_pot_t *pot,
                 const pddl_pot_solve_config_t *cfg,
                 pddl_pot_solution_t *sol,
                 pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_POT_H__ */
