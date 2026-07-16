/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_HADD_H__
#define __PDDL_HADD_H__

#include <pddl/iset.h>
#include <pddl/fdr.h>
#include <pddl/pq.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_hadd_op {
    pddl_iset_t eff; /*!< Facts in its effect */
    int cost;       /*!< Cost of the operator */
    int pre_size;   /*!< Number of preconditions */
    int value;      /*!< Current value of the operator */
    int unsat;      /*!< Number of unsatisfied preconditions */
};
typedef struct pddl_hadd_op pddl_hadd_op_t;

struct pddl_hadd_fact {
    pddl_iset_t pre_op; /*!< Operators having this fact as its precondition */
    pddl_pq_el_t heap; /*!< Connection to priority heap */
};
typedef struct pddl_hadd_fact pddl_hadd_fact_t;

struct pddl_hadd {
    pddl_hadd_fact_t *fact;
    int fact_size;
    int fact_goal;
    int fact_nopre;

    pddl_hadd_op_t *op;
    int op_size;
    int op_goal;
};
typedef struct pddl_hadd pddl_hadd_t;

/**
 * Initialize h^max
 */
void pddlHAddInit(pddl_hadd_t *hadd, const pddl_fdr_t *fdr);
void pddlHAddInitStrips(pddl_hadd_t *h, const pddl_strips_t *strips);

/**
 * Free allocated memory.
 */
void pddlHAddFree(pddl_hadd_t *hadd);

/**
 * Returns h^max estimate for the given state.
 */
int pddlHAdd(pddl_hadd_t *hadd,
             const int *fdr_state,
             const pddl_fdr_vars_t *vars);
int pddlHAddStrips(pddl_hadd_t *h, const pddl_iset_t *state);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_HADD_H__ */
