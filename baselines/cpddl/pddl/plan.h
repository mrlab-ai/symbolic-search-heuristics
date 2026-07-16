/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_PLAN_H__
#define __PDDL_PLAN_H__

#include <pddl/iarr.h>
#include <pddl/fdr_state_space.h>
#include <pddl/fdr.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_search;

struct pddl_plan {
    pddl_state_id_t *state;
    int state_size;
    int state_alloc;

    pddl_iarr_t op;
    int cost;
    int length;
};
typedef struct pddl_plan pddl_plan_t;


/**
 * Initializes empty structure.
 */
void pddlPlanInit(pddl_plan_t *plan);

/**
 * Copy the plan.
 */
void pddlPlanInitCopy(pddl_plan_t *dst, const pddl_plan_t *src);

/**
 * Frees allocated memory.
 */
void pddlPlanFree(pddl_plan_t *plan);

/**
 * Load the plan by backtracking from the goal state.
 */
void pddlPlanLoadBacktrack(pddl_plan_t *plan,
                           pddl_state_id_t goal_state_id,
                           const pddl_fdr_state_space_t *state_space);

/**
 * Update the plan so that all auxiliary operators are replaced or removed
 * as they should so that the resulting plan is a valid plan for the
 * original input planning task.
 *
 * IMPORTANT: Calling this function invalidates .state* members of the
 * pddl_plan_t structure.
 */
void pddlPlanUpdateAuxiliaryOps(pddl_plan_t *plan, const pddl_fdr_t *fdr);

/**
 * Prints out the found plan.
 */
void pddlPlanPrint(const pddl_plan_t *plan,
                   const pddl_fdr_ops_t *ops,
                   FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_PLAN_H__ */
