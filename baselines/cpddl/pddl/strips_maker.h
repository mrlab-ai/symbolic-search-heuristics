/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_STRIPS_MAKER_H__
#define __PDDL_STRIPS_MAKER_H__

#include <pddl/extarr.h>
#include <pddl/common.h>
#include <pddl/pddl_struct.h>
#include <pddl/strips.h>
#include <pddl/ground_atom.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_ground_action_args {
    int id;
    pddl_list_t htable; /*!< Connection to hash table .action_args */
    pddl_htable_key_t hash; /*!< Hash key */
    int action_id; /*!< ID of the action */
    int action_id2; /*!< Additional ID used for distinguishing conditional
                         effects */
    int arg[]; /*!< Arguments of the action */
};
typedef struct pddl_ground_action_args pddl_ground_action_args_t;

struct pddl_strips_maker {
    int action_size; /*!< Number of actions in PDDL */
    int *action_arg_size; /*!< Mapping from action to number of arguments */
    pddl_ground_atoms_t ground_atom;
    pddl_ground_atoms_t ground_atom_static;
    pddl_ground_atoms_t ground_func;
    pddl_htable_t *action_args;
    int num_action_args;
    pddl_extarr_t *action_args_arr;
    int eq_pred;
    int func_total_cost_id;
};
typedef struct pddl_strips_maker pddl_strips_maker_t;

void pddlStripsMakerInit(pddl_strips_maker_t *sm, const pddl_t *pddl);
void pddlStripsMakerFree(pddl_strips_maker_t *sm);

/**
 * TODO
 */
pddl_ground_atom_t *pddlStripsMakerAddAtom(pddl_strips_maker_t *sm,
                                           const pddl_fm_atom_t *atom,
                                           const int *args,
                                           int *is_new);
pddl_ground_atom_t *pddlStripsMakerAddAtomPred(pddl_strips_maker_t *sm,
                                               int pred,
                                               const int *args,
                                               int args_size,
                                               int *is_new);

/**
 * Same pddlStripsMakerAddAtom() but adds static atom
 */
pddl_ground_atom_t *pddlStripsMakerAddStaticAtom(pddl_strips_maker_t *sm,
                                                 const pddl_fm_atom_t *atom,
                                                 const int *args,
                                                 int *is_new);
pddl_ground_atom_t *pddlStripsMakerAddStaticAtomPred(pddl_strips_maker_t *sm,
                                                     int pred,
                                                     const int *args,
                                                     int args_size,
                                                     int *is_new);

/**
 * Same pddlStripsMakerAddAtom() but adds function set to an integer value.
 */
pddl_ground_atom_t *pddlStripsMakerAddFuncInt(pddl_strips_maker_t *sm,
                                              const pddl_fm_atom_t *atom,
                                              const int *args,
                                              int value,
                                              int *is_new);

/**
 * TODO
 */
pddl_ground_action_args_t *pddlStripsMakerAddAction(pddl_strips_maker_t *sm,
                                                    int action_id,
                                                    int action_id2,
                                                    const int *args,
                                                    int *is_new);

/**
 * Add atoms, static atoms, and (static) function atoms/fluents.
 */
int pddlStripsMakerAddInit(pddl_strips_maker_t *sm, const pddl_t *pddl);

/**
 * As pddlStripsMakerAddInit() but also collects and returns the added fact IDs.
 */
int pddlStripsMakerAddInitAndCollect(pddl_strips_maker_t *sm,
                                     const pddl_t *pddl,
                                     pddl_iset_t *added_facts,
                                     pddl_iset_t *added_static_facts);

/**
 * TODO
 */
int pddlStripsMakerMakeStrips(pddl_strips_maker_t *sm,
                              const pddl_t *pddl,
                              const pddl_ground_config_t *cfg,
                              pddl_strips_t *strips,
                              pddl_err_t *err);

pddl_ground_action_args_t *pddlStripsMakerActionArgs(pddl_strips_maker_t *sm,
                                                     int id);
pddl_ground_atom_t *pddlStripsMakerGroundAtom(pddl_strips_maker_t *sm, int id);
const pddl_ground_atom_t *pddlStripsMakerGroundAtomConst(
                const pddl_strips_maker_t *sm, int id);


/**
 * Return effects of the action {a} grounded with arguments {args} in a
 * form of STRIPS add and delete effects {add_eff} and {del_eff} obtained
 * using {smaker}.
 * It is assumed that {a} is normalized and applicable in state {state}.
 * The cost of the action {cost} is set according to (increase ...)
 * formulae.
 * Note that conditional effects are merged into {add_eff} and {del_eff}
 * based on their applicability in {state}.
 */
int pddlStripsMakerActionEffInState(pddl_strips_maker_t *smaker,
                                    const pddl_t *pddl,
                                    const pddl_action_t *a,
                                    const int *args,
                                    const pddl_iset_t *state,
                                    pddl_iset_t *add_eff,
                                    pddl_iset_t *del_eff,
                                    int *cost,
                                    pddl_err_t *err);
#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_STRIPS_MAKER_H__ */
