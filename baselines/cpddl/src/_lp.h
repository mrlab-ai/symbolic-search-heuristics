/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL__LP_H__
#define __PDDL__LP_H__

#include "pddl/config.h"

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#define PDDL_LP_MIN_BOUND -1E20
#define PDDL_LP_MAX_BOUND 1E20

enum pddl_lp_col_type {
    PDDL_LP_COL_TYPE_REAL,
    PDDL_LP_COL_TYPE_INT,
    PDDL_LP_COL_TYPE_BINARY,
};
typedef enum pddl_lp_col_type pddl_lp_col_type_t;

struct pddl_lp_col {
    double obj;
    pddl_lp_col_type_t type;
    double lb;
    double ub;
    /** Start value for MIP solver */
    double start;
    pddl_bool_t start_enabled;
};
typedef struct pddl_lp_col pddl_lp_col_t;

struct pddl_lp_coef {
    int col;
    double coef;
};
typedef struct pddl_lp_coef pddl_lp_coef_t;

struct pddl_lp_indicator {
    /** Indicator variable -- this has to be integer/binary variable */
    int var;
    /** Value of the indicator variable to be active, i.e., if var = val,
     *  then the corresponding constraint has to be satisfied. */
    pddl_bool_t val;
    /** True if the indicator variable is used. */
    pddl_bool_t enabled;
};
typedef struct pddl_lp_indicator pddl_lp_indicator_t;

struct pddl_lp_row {
    pddl_lp_coef_t *coef;
    int coef_size;
    int coef_alloc;
    double rhs;
    char sense; // 'L', 'G', 'E'
    pddl_lp_indicator_t indicator;
};
typedef struct pddl_lp_row pddl_lp_row_t;

struct pddl_lp {
    pddl_err_t *err; // TODO: Remove this one
    pddl_lp_config_t cfg;
    pddl_lp_col_t *col;
    int col_size;
    int col_alloc;
    pddl_lp_row_t *row;
    int row_size;
    int row_alloc;
};

void _pddlLPSolutionInit(pddl_lp_solution_t *sol, const pddl_lp_t *lp);
pddl_lp_status_t _pddlLPSolutionToStatus(const pddl_lp_solution_t *sol);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL__LP_H__ */
