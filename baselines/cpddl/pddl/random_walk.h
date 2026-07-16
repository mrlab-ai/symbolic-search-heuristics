/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_RANDOM_WALK_H__
#define __PDDL_RANDOM_WALK_H__

#include <pddl/rand.h>
#include <pddl/fdr.h>
#include <pddl/fdr_app_op.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_random_walk {
    const pddl_fdr_t *fdr; /*!< Reference to the FDR problem */
    const pddl_fdr_app_op_t *app; /*!< Reference to successor generator */
    int owns_app_op; /*!< True if this object is responsible for .app_op */
    pddl_rand_t rnd; /*!< Random number generator */
};
typedef struct pddl_random_walk pddl_random_walk_t;

void pddlRandomWalkInit(pddl_random_walk_t *rndw,
                        const pddl_fdr_t *fdr,
                        const pddl_fdr_app_op_t *app_op);
void pddlRandomWalkInitSeed(pddl_random_walk_t *rndw,
                            const pddl_fdr_t *fdr,
                            const pddl_fdr_app_op_t *app_op,
                            uint32_t seed);

void pddlRandomWalkFree(pddl_random_walk_t *rndw);

/**
 * Samples a state by random walk starting at {start_state} and performing
 * at most max_steps.
 * The length of the walk is computed according to a binomial distribution.
 * Number of actual steps is returned.
 */
int pddlRandomWalkSampleState(pddl_random_walk_t *rndw,
                              const int *start_state,
                              int max_steps,
                              int *resulting_state);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_RANDOM_WALK_H__ */
