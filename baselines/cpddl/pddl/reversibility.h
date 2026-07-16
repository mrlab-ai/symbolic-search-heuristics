/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_REVERSIBILITY_H__
#define __PDDL_REVERSIBILITY_H__

#include <pddl/iarr.h>
#include <pddl/strips.h>
#include <pddl/mutex_pair.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Conjunctive formula over facts
 */
struct pddl_conj_fact_formula {
    pddl_iset_t pos; /*!< Positive facts */
    pddl_iset_t neg; /*!< Negative facts */
};
typedef struct pddl_conj_fact_formula pddl_conj_fact_formula_t;

struct pddl_reverse_plan {
    int reversible_op_id; /*!< ID of the reversible operator */
    pddl_conj_fact_formula_t formula; /*!< \phi formula */
    pddl_iarr_t plan; /*!< Reverse plan -- a sequence of operators' IDs */
};
typedef struct pddl_reverse_plan pddl_reverse_plan_t;

struct pddl_reversibility_uniform {
    pddl_reverse_plan_t *plan;
    int plan_size;
    int plan_alloc;
};
typedef struct pddl_reversibility_uniform pddl_reversibility_uniform_t;

/**
 * Initialize an empty set of reverse plans.
 */
void pddlReversibilityUniformInit(pddl_reversibility_uniform_t *r);

/**
 * Free allocated memory.
 */
void pddlReversibilityUniformFree(pddl_reversibility_uniform_t *r);

/**
 * Sort reverse plans.
 */
void pddlReversibilityUniformSort(pddl_reversibility_uniform_t *r);

void pddlReversibilityUniformInfer(pddl_reversibility_uniform_t *r,
                                   const pddl_strips_ops_t *ops,
                                   const pddl_strips_op_t *rev_op,
                                   int max_depth,
                                   const pddl_mutex_pairs_t *mutex);

void pddlReversePlanUniformPrint(const pddl_reverse_plan_t *p,
                                 const pddl_strips_ops_t *ops,
                                 FILE *fout);
void pddlReversibilityUniformPrint(const pddl_reversibility_uniform_t *r,
                                   const pddl_strips_ops_t *ops,
                                   FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_REVERSIBILITY_H__ */
