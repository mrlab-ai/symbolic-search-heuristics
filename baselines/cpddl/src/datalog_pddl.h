/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_DATALOG_PDDL_H__
#define __PDDL_DATALOG_PDDL_H__

#include <pddl/datalog.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Returns maximum number of variables needed for any rule.
 * It is computed as a maximum arity over all actions and predicates.
 */
int pddlDatalogPddlMaxVarSize(const pddl_t *pddl);

/**
 * Creates a "fact" (body-less) rule P(x_1, ..., x_n).
 * pred_id is alread datalog's ID of the predicate, but arguments are
 * re-mapped via obj_to_dlconst.
 */
void pddlDatalogPddlAddFactRule(pddl_datalog_t *dl,
                                unsigned pred_id,
                                int arg_size,
                                const int *args,
                                const unsigned *obj_to_dlconst);

/**
 * Same as before, but transforms atom.
 * Note that it assumes the atom is ground.
 */
void pddlDatalogPddlAddFactRuleFromAtom(pddl_datalog_t *dl,
                                        const pddl_fm_atom_t *atom,
                                        const unsigned *pred_to_dlpred,
                                        const unsigned *obj_to_dlconst);

/**
 * For each type T and each object O from the type T, it creates a rule
 * T(O).
 */
void pddlDatalogPddlAddTypeRules(pddl_datalog_t *dl,
                                 const pddl_t *pddl,
                                 const unsigned *type_to_dlpred,
                                 const unsigned *obj_to_dlconst);

/**
 * For each object O, it creates a rule =(O, O).
 */
void pddlDatalogPddlAddEqRules(pddl_datalog_t *dl,
                               const pddl_t *pddl,
                               const unsigned *pred_to_dlpred,
                               const unsigned *obj_to_dlconst);

/**
 * Sets dlatom to corresponds t the given atom.
 */
void pddlDatalogPddlAtomToDLAtom(pddl_datalog_t *dl,
                                 pddl_datalog_atom_t *dlatom,
                                 const pddl_fm_atom_t *atom,
                                 const unsigned *pred_to_dlpred,
                                 const unsigned *obj_to_dlconst,
                                 const unsigned *dlvar);

void pddlDatalogPddlSetActionTypeBody(pddl_datalog_t *dl,
                                      pddl_datalog_rule_t *rule,
                                      const pddl_t *pddl,
                                      const pddl_params_t *params,
                                      const pddl_fm_t *pre,
                                      const pddl_fm_t *pre2,
                                      unsigned *type_to_dlpred,
                                      const unsigned *dlvar);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_DATALOG_PDDL_H__ */
