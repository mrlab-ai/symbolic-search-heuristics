/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_TRANS_SYSTEM_ABSTR_MAPPING_H__
#define __PDDL_TRANS_SYSTEM_ABSTR_MAPPING_H__

#include <pddl/iset.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_trans_system_abstr_map {
    int *map;
    int num_states;
    int map_num_states;
    pddl_bool_t is_identity;
};
typedef struct pddl_trans_system_abstr_map pddl_trans_system_abstr_map_t;

/**
 * Initialize abstraction mapping as identity
 */
void pddlTransSystemAbstrMapInit(pddl_trans_system_abstr_map_t *map,
                                 int num_states);

/**
 * Free allocated memory.
 */
void pddlTransSystemAbstrMapFree(pddl_trans_system_abstr_map_t *map);

/**
 * Finalize the mapping.
 * This needs to be called when setting of the mapping is done.
 */
void pddlTransSystemAbstrMapFinalize(pddl_trans_system_abstr_map_t *map);

/**
 * Prune the specified state.
 */
void pddlTransSystemAbstrMapPruneState(pddl_trans_system_abstr_map_t *map,
                                       int state);

/**
 * Condense the specified states into one state
 */
void pddlTransSystemAbstrMapCondense(pddl_trans_system_abstr_map_t *map,
                                     const pddl_iset_t *states);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_TRANS_SYSTEM_ABSTR_MAPPING_H__ */
