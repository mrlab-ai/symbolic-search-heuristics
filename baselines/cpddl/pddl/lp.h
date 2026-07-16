/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_LP_H__
#define __PDDL_LP_H__

#include <pddl/err.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Exit status of *Solve() functions.
 */
enum pddl_lp_status {
    /** The problem was solved optimally */
    PDDL_LP_STATUS_OPTIMAL = 0,
    /** The problem was solved sub-optimally */
    PDDL_LP_STATUS_SUBOPTIMAL = 1,
    /** The problem does not have a solution */
    PDDL_LP_STATUS_INFEASIBLE = 2,
    /** The solver wasn't able to find a solution or prove it is not
     *  solvable */
    PDDL_LP_STATUS_NO_SOLUTION_FOUND = -1,
    /** An error occurred */
    PDDL_LP_STATUS_ERR = -2,
};
typedef enum pddl_lp_status pddl_lp_status_t;

/**
 * Solution to MIP/LP problem.
 */
struct pddl_lp_solution {
    /** True if the problem was solved */
    pddl_bool_t solved;
    /** True if the problem was solved optimally */
    pddl_bool_t solved_optimally;
    /** True if the problem was solved sub-optimally (see .timed_out below) */
    pddl_bool_t solved_suboptimally;
    /** True if the solver proved the problem to be unsolvable */
    pddl_bool_t unsolvable;
    /** True if the solver wasn't able to solve the problem or prove its
     *  unsolvability */
    pddl_bool_t not_solved;
    /** True if error occurred */
    pddl_bool_t error;
    /** True if the solver timed out */
    pddl_bool_t timed_out;
    /** If set to non-NULL and the solver found a solution, it is filled
     *  with the values assigned to each variable. It must be allocated by
     *  the caller, and it must have at pddlLPNumCols() elements */
    double *var_val;
    /** If the solver found a solution, it is set to the value of the
     *  objective function */
    double obj_val;
};
typedef struct pddl_lp_solution pddl_lp_solution_t;


/** Forward declaration */
typedef struct pddl_lp pddl_lp_t;

/**
 * All possible solvers.
 */
enum pddl_lp_solver {
    PDDL_LP_DEFAULT = 0,
    PDDL_LP_CPLEX,
    PDDL_LP_GUROBI,
    PDDL_LP_HIGHS,
    PDDL_LP_NO_SOLVER = 100,
};
typedef enum pddl_lp_solver pddl_lp_solver_t;

struct pddl_lp_config {
    int rows; /*!< Number of rows (constraints) after initialization */
    int cols; /*!< Number of columns (variables) after initialization */
    int maximize; /*!< 1 for maximize, 0 for minimize */
    pddl_lp_solver_t solver; /*!< One of the solver IDs above */
    int num_threads; /*!< Number of threads. */
    float time_limit; /*!< Time limit for solving the problem. */
    int tune_int_operator_potential; /*!< True for tuning inference of
                                          integer operator potentials */
    /** True for inference of potential functions */
    int tune_potential;
};
typedef struct pddl_lp_config pddl_lp_config_t;

#define PDDL_LP_CONFIG_INIT \
    { \
        0, /* .rows */ \
        0, /* .cols */ \
        0, /* .maximize */ \
        PDDL_LP_DEFAULT, /* .solver */ \
        1, /* .num_threads */ \
        -1., /* .time_limit */ \
        0, /* .tune_int_operator_potential */ \
        0, /* .tune_potential */ \
    }

/**
 * Returns true if the specified solver is available.
 * For PDDL_LP_DEFAULT returns false if there is no LP solver available.
 */
pddl_bool_t pddlLPSolverAvailable(pddl_lp_solver_t solver);

/**
 * Set default solver.
 */
int pddlLPSetDefault(pddl_lp_solver_t solver, pddl_err_t *err);

/**
 * Creates a new LP problem with specified number of rows and columns.
 */
pddl_lp_t *pddlLPNew(const pddl_lp_config_t *cfg, pddl_err_t *err);

/**
 * Deletes the LP object.
 */
void pddlLPDel(pddl_lp_t *lp);

/**
 * Returns name of the current LP solver.
 */
const char *pddlLPSolverName(const pddl_lp_t *lp);

/**
 * Returns one of PDDL_LP_{CPLEX,GUROBI,HIGHS} constants according to the
 * current solver.
 */
int pddlLPSolverID(const pddl_lp_t *lp);

/**
 * Sets objective coeficient for i'th variable.
 */
void pddlLPSetObj(pddl_lp_t *lp, int i, double coef);

/**
 * Sets i'th variable's range.
 */
void pddlLPSetVarRange(pddl_lp_t *lp, int i, double lb, double ub);

/**
 * Sets i'th variable as free.
 */
void pddlLPSetVarFree(pddl_lp_t *lp, int i);

/**
 * Sets i'th variable as integer.
 */
void pddlLPSetVarInt(pddl_lp_t *lp, int i);

/**
 * Sets i'th variable as binary.
 */
void pddlLPSetVarBinary(pddl_lp_t *lp, int i);

/**
 * Sets coefficient for row's constraint and col's variable.
 */
void pddlLPSetCoef(pddl_lp_t *lp, int row, int col, double coef);

/**
 * Sets right hand side of the row'th constraint.
 * Also sense of the constraint must be defined:
 *      - 'L' <=
 *      - 'G' >=
 *      - 'E' =
 */
void pddlLPSetRHS(pddl_lp_t *lp, int row, double rhs, char sense);

/**
 * Sets the indicator variable for the specified row, the variable has to
 * be binary variable.
 * That is, after this call, the row has to be satisfied if var = val.
 */
void pddlLPSetIndicator(pddl_lp_t *lp, int row, int var, pddl_bool_t val);

/**
 * Adds cnt rows to the model.
 */
void pddlLPAddRows(pddl_lp_t *lp, int cnt, const double *rhs, const char *sense);

/**
 * Deletes rows with indexes between begin and end including both limits,
 * i.e., first deleted row has index {begin} the last deleted row has index
 * {end}.
 */
void pddlLPDelRows(pddl_lp_t *lp, int begin, int end);

/**
 * Returns number of rows in model.
 */
int pddlLPNumRows(const pddl_lp_t *lp);

/**
 * Adds cnt columns to the model.
 */
void pddlLPAddCols(pddl_lp_t *lp, int cnt);

/**
 * Returns number of columns in model.
 */
int pddlLPNumCols(const pddl_lp_t *lp);

/**
 * Set the start value of the variable.
 * This is used only when solving ILP/MIP.
 */
void pddlLPSetColStart(pddl_lp_t *lp, int var, double value);

/**
 * Solves (I)LP problem using default solver.
 */
pddl_lp_status_t pddlLPSolve(const pddl_lp_t *lp,
                             pddl_lp_solution_t *sol,
                             pddl_err_t *err);

pddl_lp_status_t pddlLPSolveCPLEX(const pddl_lp_t *lp,
                                  pddl_lp_solution_t *sol,
                                  pddl_err_t *err);
pddl_lp_status_t pddlLPSolveGurobi(const pddl_lp_t *lp,
                                   pddl_lp_solution_t *sol,
                                   pddl_err_t *err);
pddl_lp_status_t pddlLPSolveHiGHS(const pddl_lp_t *lp,
                                  pddl_lp_solution_t *sol,
                                  pddl_err_t *err);

void pddlLPWrite(const pddl_lp_t *lp, const char *fn);

/**
 * Dynamically load CPLEX library.
 * Returns 0 on success.
 */
int pddlLPLoadCPLEX(const char *so_fn, pddl_err_t *err);

/**
 * Returns true if the CPLEX library is available.
 */
pddl_bool_t pddlLPIsCPLEXAvailable(void);

/**
 * Returns CPLEX version.
 */
const char * const pddlLPCPLEXVersion(void);

/**
 * Dynamicaly load Gurobi library.
 * Returns 0 on success
 */
int pddlLPLoadGurobi(const char *so_fn, pddl_err_t *err);

/**
 * Returns true if Gurobi is available.
 */
pddl_bool_t pddlLPIsGurobiAvailable(void);

/**
 * Returns Gurobi library version.\
 */
const char * const pddlLPGurobiVersion(void);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_LP_H__ */
