/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_ACTION_ARGS_H__
#define __PDDL_ACTION_ARGS_H__

#include <pddl/common.h>
#include <pddl/extarr.h>
#include <pddl/htable.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_action_args {
    int num_args;
    pddl_extarr_t *arg_pool;
    pddl_htable_t *htable;
    int args_size;
};
typedef struct pddl_action_args pddl_action_args_t;

/**
 * Initialize pool of action arguments
 */
void pddlActionArgsInit(pddl_action_args_t *args, int num_args);

/**
 * Free allocated memory.
 */
void pddlActionArgsFree(pddl_action_args_t *args);

/**
 * Adds arguments to the pool and ID is returned, {a} is expected to be
 * .num_args long.
 */
int pddlActionArgsAdd(pddl_action_args_t *args, const int *a);

/**
 * Returns arguments corresponding to the id.
 */
const int *pddlActionArgsGet(const pddl_action_args_t *args, int id);

/**
 * Returns number of stored unique arguments.
 */
int pddlActionArgsSize(const pddl_action_args_t *args);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_ACTION_ARGS_H__ */
