/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_GROUND_H__
#define __PDDL_GROUND_H__

#include <pddl/common.h>
#include <pddl/lifted_mgroup.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

enum pddl_ground_method {
    PDDL_GROUND_DATALOG = 1,
    PDDL_GROUND_SQL,
    PDDL_GROUND_TRIE,
    PDDL_GROUND_GRINGO,
    PDDL_GROUND_CLINGO,
};
typedef enum pddl_ground_method pddl_ground_method_t;

struct pddl_ground_config {
    /** Which grounding method/algorithm should be used. */
    pddl_ground_method_t method;
    const pddl_lifted_mgroups_t *lifted_mgroups;
    /** If .lifted_mgroups != NULL, use lifted mutex groups to prune
     *  operators that has mutex preconditions. */
    pddl_bool_t prune_op_pre_mutex;
    /** If .lifted_mgroups != NULL, use lifted mutex groups to prune
     *  dead-end operators. */
    pddl_bool_t prune_op_dead_end;
    /** If true static facts are found and removed */
    pddl_bool_t remove_static_facts;
    /** Keep action arguments in strips operators */
    pddl_bool_t keep_action_args;
    /** Keep all static facts including the ones created from static
     *  predicates */
    pddl_bool_t keep_all_static_facts;
    /** Ground only facts, i.e., completely skip grounding of actions */
    pddl_bool_t ground_only_facts;
    /** If set to non-NULL, it must contain a path to the lpopt optimizer
      * binary (https://dbai.tuwien.ac.at/proj/lpopt) that is used for
      * preprocessing datalog program before it is passed to Gringo.
      * It has effect only if .method is set to PDDL_GROUND_GRINGO. */
    const char *gringo_lpopt;
};
typedef struct pddl_ground_config pddl_ground_config_t;

#define PDDL_GROUND_CONFIG_INIT { \
        PDDL_GROUND_DATALOG, /* .method */ \
        NULL, /* .lifted_mgroups */ \
        pddl_true, /* .prune_op_pre_mutex */ \
        pddl_true, /* .prune_op_dead_end */ \
        pddl_true, /* .remove_static_facts */ \
        pddl_false, /* .keep_action_args */ \
        pddl_false, /* .keep_all_static_facts */ \
        pddl_false, /* .ground_only_facts */ \
        NULL, /* .gringo_lpopt */ \
    }

void pddlGroundConfigLog(const pddl_ground_config_t *cfg, pddl_err_t *err);

/**
 * Ground PDDL into STRIPS.
 */
int pddlGround(pddl_strips_t *strips,
               const pddl_t *pddl,
               const pddl_ground_config_t *cfg,
               pddl_err_t *err);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_GROUND_H__ */
