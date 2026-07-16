/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_MGROUP_PROJECTION_H__
#define __PDDL_MGROUP_PROJECTION_H__

#include <pddl/strips.h>
#include <pddl/strips_fact_cross_ref.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_mgroup_projection {
    int num_states;
    pddl_iset_t mgroup; /*!< Facts, each corresponding to an abstract state */
    pddl_iset_t *tr; /*!< Adjecancy matrix operato IDs as labels */
};
typedef struct pddl_mgroup_projection pddl_mgroup_projection_t;

/**
 * TODO
 */
void pddlMGroupProjectionInit(pddl_mgroup_projection_t *p,
                              const pddl_strips_t *strips,
                              const pddl_iset_t *mgroup,
                              const pddl_mutex_pairs_t *mutex,
                              const pddl_strips_fact_cross_ref_t *cref);

/**
 * Initialize p as a copy of src.
 */
void pddlMGroupProjectionInitCopy(pddl_mgroup_projection_t *p,
                                  const pddl_mgroup_projection_t *src);

/**
 * Free allocated memory
 */
void pddlMGroupProjectionFree(pddl_mgroup_projection_t *p);


/**
 * Returns maximal out-degree over all vertices.
 */
int pddlMGroupProjectionMaxOutdegree(const pddl_mgroup_projection_t *p);

/**
 * TODO
 */
void pddlMGroupProjectionPruneUnreachable(pddl_mgroup_projection_t *p,
                                          const pddl_iset_t *states,
                                          int backward);

/**
 * TODO
 */
void pddlMGroupProjectionPruneUnreachableFromInit(pddl_mgroup_projection_t *p,
                                                  const pddl_strips_t *strips);

/**
 * TODO
 */
void pddlMGroupProjectionPruneUnreachableFromGoal(pddl_mgroup_projection_t *p,
                                                  const pddl_strips_t *strips,
                                                  const pddl_mutex_pairs_t *mx);

/**
 * Restrict all labels to the given set of operators.
 */
void pddlMGroupProjectionRestrictOps(pddl_mgroup_projection_t *p,
                                     const pddl_iset_t *ops);

void pddlMGroupProjectionPrint(const pddl_mgroup_projection_t *p,
                               const pddl_strips_t *strips,
                               FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_MGROUP_PROJECTION_H__ */
