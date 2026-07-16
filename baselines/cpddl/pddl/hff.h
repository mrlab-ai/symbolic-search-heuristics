/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_HFF_H__
#define __PDDL_HFF_H__

#include <pddl/iarr.h>
#include <pddl/iset.h>
#include <pddl/fdr.h>
#include <pddl/pq.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

    /*
struct pddl_hff_parallel_plan {
    pddl_iset_t *step;
    int step_size;
    int step_alloc;
};
typedef struct pddl_hff_parallel_plan pddl_hff_parallel_plan_t;
*/

struct pddl_hff_op {
    pddl_iset_t pre; /*!< Facts in its precondition */
    pddl_iset_t eff; /*!< Facts in its effect */
    int cost;       /*!< Cost of the operator */
    int pre_size;   /*!< Number of preconditions */

    int value;      /*!< Current value of the operator */
    int unsat;      /*!< Number of unsatisfied preconditions */
    pddl_bool_t marked; /*!< True if marked as part of relaxed plan */
    int order;      /*!< Order in which operators was reached */
};
typedef struct pddl_hff_op pddl_hff_op_t;

struct pddl_hff_fact {
    pddl_iset_t eff_op; /*!< Operators having this fact in its effect */
    pddl_iset_t pre_op; /*!< Operators having this fact as its precondition */

    pddl_pq_el_t heap; /*!< Connection to priority heap */
    pddl_bool_t marked; /*!< True if marked as part of relaxed plan */
    int reached_by_op; /*!< Operator this fact was first reached by */
};
typedef struct pddl_hff_fact pddl_hff_fact_t;

struct pddl_hff {
    pddl_hff_fact_t *fact;
    int fact_size;
    int fact_goal;
    int fact_nopre;

    pddl_hff_op_t *op;
    int op_size;
    int op_goal;
};
typedef struct pddl_hff pddl_hff_t;

/**
 * Initialize h^ff
 */
// TODO: Rename to pddlHFFInitFDR
void pddlHFFInit(pddl_hff_t *hff, const pddl_fdr_t *fdr);
void pddlHFFInitStrips(pddl_hff_t *hff, const pddl_strips_t *strips);

/**
 * Free allocated memory.
 */
void pddlHFFFree(pddl_hff_t *hff);

/**
 * Returns h^ff estimate for the given state.
 */
// TODO: Rename to *FDR
int pddlHFF(pddl_hff_t *hff,
            const int *fdr_state,
            const pddl_fdr_vars_t *vars);
int pddlHFFPlan(pddl_hff_t *hff,
                const int *fdr_state,
                const pddl_fdr_vars_t *vars,
                pddl_iarr_t *plan);

int pddlHFFStrips(pddl_hff_t *hff, const pddl_iset_t *state);
int pddlHFFStripsPlan(pddl_hff_t *hff,
                      const pddl_iset_t *state,
                      pddl_iarr_t *plan);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_HFF_H__ */
