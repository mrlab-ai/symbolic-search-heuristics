/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_STRIPS_FACT_CROSS_REF_H__
#define __PDDL_STRIPS_FACT_CROSS_REF_H__

#include <pddl/strips.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */


struct pddl_strips_fact_cross_ref_fact {
    int fact_id; /*!< ID of the fact */
    pddl_bool_t is_init; /*!< True if the fact is in the initial state */
    pddl_bool_t is_goal; /*!< True if the fact is in the goal */
    pddl_iset_t op_pre; /*!< Operators having this fact in its precondition */
    pddl_iset_t op_add; /*!< Operators having this fact in its add effect */
    pddl_iset_t op_del; /*!< Operators having this fact in its del effect */
};
typedef struct pddl_strips_fact_cross_ref_fact
    pddl_strips_fact_cross_ref_fact_t;

struct pddl_strips_fact_cross_ref {
    pddl_strips_fact_cross_ref_fact_t *fact;
    int fact_size;
};
typedef struct pddl_strips_fact_cross_ref
    pddl_strips_fact_cross_ref_t;


void pddlStripsFactCrossRefInit(pddl_strips_fact_cross_ref_t *cref,
                                const pddl_strips_t *strips,
                                pddl_bool_t init,
                                pddl_bool_t goal,
                                pddl_bool_t op_pre,
                                pddl_bool_t op_add,
                                pddl_bool_t op_del);

void pddlStripsFactCrossRefFree(pddl_strips_fact_cross_ref_t *cref);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_STRIPS_FACT_CROSS_REF_H__ */
