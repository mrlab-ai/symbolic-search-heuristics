/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_PREP_ACTION_H__
#define __PDDL_PREP_ACTION_H__

#include <pddl/common.h>
#include <pddl/action.h>
#include <pddl/fm_arr.h>
#include <pddl/ground_atom.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_prep_action {
    const pddl_action_t *action;
    int parent_action; /*!< ID >= 0 if this is a conditional effect */
    int param_size;
    int *param_type;
    const pddl_types_t *type;
    pddl_fm_arr_t pre_neg_static;
    pddl_fm_arr_t pre_eq;
    pddl_fm_arr_t pre;
    pddl_fm_arr_t add_eff;
    pddl_fm_arr_t del_eff;
    pddl_fm_arr_t increase_total_cost_atom;
    int increase_total_cost_value;
    int max_arg_size;
    int cond_eff_size;
};
typedef struct pddl_prep_action pddl_prep_action_t;

struct pddl_prep_actions {
    pddl_prep_action_t *action;
    int action_size;
    int action_alloc;
};
typedef struct pddl_prep_actions pddl_prep_actions_t;

int pddlPrepActionsInit(const pddl_t *pddl, pddl_prep_actions_t *as,
                        pddl_err_t *err);
void pddlPrepActionsFree(pddl_prep_actions_t *as);

/**
 * Returns true if the action can be grounded with the provided arguments.
 */
int pddlPrepActionCheck(const pddl_prep_action_t *a,
                        const pddl_ground_atoms_t *static_facts,
                        const int *arg);

/**
 * Checks the given fact against specified precondition.
 */
int pddlPrepActionCheckFact(const pddl_prep_action_t *a, int pre_i,
                            const int *fact_args);

/**
 * Checks equality preconditions, i.e., (= ?x ?y) and (not (= ?x ?y)), but
 * only for the defined arguments.
 */
int pddlPrepActionCheckEqDef(const pddl_prep_action_t *a,
                             const int *arg);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_PREP_ACTION_H__ */
