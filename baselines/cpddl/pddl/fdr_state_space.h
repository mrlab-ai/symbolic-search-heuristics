/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_FDR_STATE_SPACE_H__
#define __PDDL_FDR_STATE_SPACE_H__

#include <pddl/extarr.h>
#include <pddl/fdr_var.h>
#include <pddl/fdr_state_pool.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

enum pddl_fdr_state_space_status {
    PDDL_FDR_STATE_SPACE_STATUS_NEW,
    PDDL_FDR_STATE_SPACE_STATUS_OPEN,
    PDDL_FDR_STATE_SPACE_STATUS_CLOSED,
};
typedef enum pddl_fdr_state_space_status pddl_fdr_state_space_status_t;

struct pddl_fdr_state_space_node {
    pddl_state_id_t id; /*!< ID of the state */
    pddl_state_id_t parent_id; /*!< ID of the parent state */
    int op_id; /*!< ID of the operator reaching this state */
    int g_value; /*!< Cost of the path from init to this state */
    pddl_fdr_state_space_status_t status; /*!< PDDL_FDR_STATE_SPACE_STATUS_* */
    int *state; /*!< Unpacked FDR state */
    int var_size; /*!< Number of variables in a state */
};
typedef struct pddl_fdr_state_space_node pddl_fdr_state_space_node_t;

struct pddl_fdr_state_space {
    pddl_fdr_state_pool_t state_pool; /*!< Pool of states */
    pddl_extarr_t *node; /*!< Array of state nodes */
};
typedef struct pddl_fdr_state_space pddl_fdr_state_space_t;

void pddlFDRStateSpaceInit(pddl_fdr_state_space_t *state_space,
                           const pddl_fdr_vars_t *vars,
                           pddl_err_t *err);
void pddlFDRStateSpaceFree(pddl_fdr_state_space_t *state_space);

/**
 * Inserts a new state.
 * Returns assigned state ID.
 */
pddl_state_id_t pddlFDRStateSpaceInsert(pddl_fdr_state_space_t *state_space,
                                        const int *state);

/**
 * Fills {node} with the state node corresponding to the given state_id.
 */
void pddlFDRStateSpaceGet(const pddl_fdr_state_space_t *state_space,
                          pddl_state_id_t state_id,
                          pddl_fdr_state_space_node_t *node);

/**
 * Same as *Get() but node->state is not touched.
 */
void pddlFDRStateSpaceGetNoState(const pddl_fdr_state_space_t *state_space,
                                 pddl_state_id_t state_id,
                                 pddl_fdr_state_space_node_t *node);

/**
 * Copy data from node to the corresponding node in the state space.
 */
void pddlFDRStateSpaceSet(pddl_fdr_state_space_t *state_space,
                          const pddl_fdr_state_space_node_t *node);


void pddlFDRStateSpaceNodeInit(pddl_fdr_state_space_node_t *node,
                               const pddl_fdr_state_space_t *state_space);
void pddlFDRStateSpaceNodeFree(pddl_fdr_state_space_node_t *node);
#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_FDR_STATE_SPACE_H__ */
