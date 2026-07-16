/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_FAMGROUP_H__
#define __PDDL_FAMGROUP_H__

#include <pddl/mgroup.h>
#include <pddl/strips.h>
#include <pddl/sym.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_famgroup_config {
    /** If true (default), only maximal fam-groups are inferred */
    pddl_bool_t maximal;
    /** If true, only fam-groups with non-empty intersection with the goal
     * are inferred. */
    pddl_bool_t goal;
    /** If set, the symmetries will be used for generation of all symmetric
     * fam-groups (instead of inferring them using LP) */
    const pddl_strips_sym_t *sym;
    /** In the case symmetries are used, only the asymetric fam-groups are
     *  stored in the output set. */
    pddl_bool_t keep_only_asymetric;
    /** Prioritize fam-groups containing new facts */
    pddl_bool_t prioritize_uncovered;

    /** If set to >0, limit on the number of inferred fam-groups */
    int limit;
    /** If set to >0., the time limit for the inference algorithm */
    float time_limit;
};
typedef struct pddl_famgroup_config pddl_famgroup_config_t;

#define PDDL_FAMGROUP_CONFIG_INIT { \
        pddl_true, /* .maximal */ \
        pddl_false, /* .goal */ \
        NULL, /* .sym */ \
        pddl_false, /* .keep_only_asymetric */ \
        pddl_false, /* .prioritize_uncovered */ \
        -1, /* .limit */ \
        -1., /* .time_limit */ \
    }

/**
 * Find fact-alternating mutex groups while skipping those that are already
 * in mgs.
 */
int pddlFAMGroupsInfer(pddl_mgroups_t *mgs,
                       const pddl_strips_t *strips,
                       const pddl_famgroup_config_t *cfg,
                       pddl_err_t *err);

_pddl_inline int pddlFAMGroupsInferMaximal(pddl_mgroups_t *mgs,
                                           const pddl_strips_t *strips,
                                           pddl_err_t *err)
{
    pddl_famgroup_config_t cfg = PDDL_FAMGROUP_CONFIG_INIT;
    cfg.maximal = 1;
    return pddlFAMGroupsInfer(mgs, strips, &cfg, err);
}

_pddl_inline int pddlFAMGroupsInferAll(pddl_mgroups_t *mgs,
                                       const pddl_strips_t *strips,
                                       pddl_err_t *err)
{
    pddl_famgroup_config_t cfg = PDDL_FAMGROUP_CONFIG_INIT;
    cfg.maximal = 0;
    return pddlFAMGroupsInfer(mgs, strips, &cfg, err);
}

/**
 * Find dead-end operators using the fam-groups stored in mgs.
 */
void pddlFAMGroupsDeadEndOps(const pddl_mgroups_t *mgs,
                             const pddl_strips_t *strips,
                             pddl_iset_t *dead_end_ops);


#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_FAMGROUP_H__ */
