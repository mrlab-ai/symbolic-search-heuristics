/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_ACTION_H__
#define __PDDL_ACTION_H__

#include <pddl/obj.h>
#include <pddl/param.h>
#include <pddl/fm.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Lifted action
 */
struct pddl_action {
    char *name;
    pddl_params_t param;
    pddl_fm_t *pre;
    pddl_fm_t *eff;
    int id;

    /** True if the action is an auxiliary action created internally, it
     *  should have zero cost, and it should be removed from the final plan
     *  (without need to replace it with anything else). */
    pddl_bool_t is_aux_zero_cost_remove_from_plan;
};
typedef struct pddl_action pddl_action_t;

struct pddl_actions {
    pddl_action_t *action;
    int action_size;
    int action_alloc;
};
typedef struct pddl_actions pddl_actions_t;

/**
 * Initializes empty action
 */
void pddlActionInit(pddl_action_t *a);

/**
 * Frees allocated memory
 */
void pddlActionFree(pddl_action_t *a);

/**
 * Creates an exact copy of the given action.
 */
void pddlActionInitCopy(pddl_action_t *dst, const pddl_action_t *src);

/**
 * Normalize .pre and .eff (see pddlFmNormalize()).
 */
void pddlActionNormalize(pddl_action_t *a, const pddl_t *pddl);

/**
 * Parses actions from domain PDDL.
 */
int pddlActionsParse(pddl_t *pddl, pddl_err_t *err);

/**
 * Initializes empty set of actions.
 */
void pddlActionsInit(pddl_actions_t *a);

/**
 * Initializes dst as a deep copy of src.
 */
void pddlActionsInitCopy(pddl_actions_t *dst, const pddl_actions_t *src);

/**
 * Free allocated memory.
 */
void pddlActionsFree(pddl_actions_t *actions);

/**
 * Adds an empty action to the list.
 * This may invalidate your current pointers to as's actions.
 */
pddl_action_t *pddlActionsAddEmpty(pddl_actions_t *as);

/**
 * Adds a new copy of the action specified by its ID.
 * This may invalidate your current pointers to as's actions.
 */
pddl_action_t *pddlActionsAddCopy(pddl_actions_t *as, int copy_id);

/**
 * Rename actions so that there are no two actions with the same name.
 */
void pddlActionsEnforceUniqueNames(pddl_actions_t *a);

/**
 * Split all actions by disjunctions in .pre assuming all .pre are in DNF.
 */
void pddlActionSplit(pddl_action_t *a, pddl_t *pddl);

/**
 * Remap object IDs.
 */
void pddlActionRemapObjs(pddl_action_t *a, const int *remap);
void pddlActionsRemapObjs(pddl_actions_t *as, const int *remap);
int pddlActionRemapTypesAndPreds(pddl_action_t *a,
                                 const int *type_remap,
                                 const int *pred_remap,
                                 const int *func_remap);
void pddlActionsRemapTypesAndPreds(pddl_actions_t *as,
                                   const int *type_remap,
                                   const int *pred_remap,
                                   const int *func_remap);

/**
 * Remove the set of actions specified by their IDs.
 */
void pddlActionsRemoveSet(pddl_actions_t *as, const pddl_iset_t *ids);

void pddlActionPrint(const pddl_t *pddl, const pddl_action_t *a, FILE *fout);
void pddlActionsPrint(const pddl_t *pddl,
                      const pddl_actions_t *actions,
                      FILE *fout);

/**
 * Print actions in PDDL format.
 */
void pddlActionsPrintPDDL(const pddl_actions_t *actions,
                          const pddl_t *pddl,
                          FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_ACTION_H__ */
