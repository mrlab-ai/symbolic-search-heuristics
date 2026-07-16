/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_UNIFY_H__
#define __PDDL_UNIFY_H__

#include <pddl/fm.h>
#include <pddl/param.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/** The representation of the value of some mapping u(x) */
struct pddl_unify_val {
    /** Object ID, in case the variable is mapped to an object */
    int obj;
    /** Variable ID, in case the variable is mapped to another variable */
    int var;
    /** Variable type in case .var >= 0 */
    int var_type;
};
typedef struct pddl_unify_val pddl_unify_val_t;

struct pddl_unify {
    /** Reference to the type system */
    const pddl_types_t *type;
    /** References to two sets of parameters/variables */
    const pddl_params_t *param[2];
    /** Mapping from variables to variables and objects. This encodes the
     *  unifier -- .map[i] is mapping from variables in .param[i]. */
    pddl_unify_val_t *map[2];
};
typedef struct pddl_unify pddl_unify_t;


/**
 * Initialize identity unifier.
 * {type} is a reference to type system.
 * {param1} and {param2} are references to parameters/variables that will
 * be subsequently used -- it assumed that when pddlUnify(u, a1, a2) is
 * called, {param1} are parameters of a1 and {param2} are parameters of a2.
 */
void pddlUnifyInit(pddl_unify_t *u,
                   const pddl_types_t *type,
                   const pddl_params_t *param1,
                   const pddl_params_t *param2);

/**
 * Initialize unifier {u} as the copy of {u2}.
 */
void pddlUnifyInitCopy(pddl_unify_t *u, const pddl_unify_t *u2);

/**
 * Free allocated memory.
 */
void pddlUnifyFree(pddl_unify_t *u);

/**
 * Unifies a1 with a2.
 * It is assumed that {a1}'s parameters are {param1} from pddlUnifyInit()
 * and analogously for {a2}.
 * Return 0 on success, -1 if unification wasn't possible.
 */
int pddlUnify(pddl_unify_t *u,
              const pddl_fm_atom_t *a1,
              const pddl_fm_atom_t *a2);

/**
 * Updates the mapping with the equality atoms (= x y) from cond.
 * {param} must be one of {param1}, {param2} from pddlUnifyInit().
 * Returns 0 on success.
 */
int pddlUnifyApplyEquality(pddl_unify_t *u,
                           const pddl_params_t *param,
                           int eq_pred,
                           const pddl_fm_t *cond);

/**
 * Returns true if the inequality conditions hold.
 * {param} must be one of {param1}, {param2} from pddlUnifyInit().
 */
int pddlUnifyCheckInequality(const pddl_unify_t *u,
                             const pddl_params_t *param,
                             int eq_pred,
                             const pddl_fm_t *cond);

/**
 * Returns true if u(a1) != u(a2), i.e., if a1 and a2 differ under the
 * current mapping.
 * Each {param1}, {param2} must be one of {param1}/{param2} from
 * pddlUnifyInit().
 */
pddl_bool_t pddlUnifyAtomsDiffer(const pddl_unify_t *u,
                                 const pddl_params_t *param1,
                                 const pddl_fm_atom_t *a1,
                                 const pddl_params_t *param2,
                                 const pddl_fm_atom_t *a2);

/**
 * Returns true if u is equal to u2
 */
pddl_bool_t pddlUnifyEq(const pddl_unify_t *u, const pddl_unify_t *u2);

/**
 * Convert the given unifier into an equivalent formula over equality
 * predicates.
 * {param} must be one of {param1}, {param2} from pddlUnifyInit().
 */
pddl_fm_t *pddlUnifyToCond(const pddl_unify_t *u,
                           int eq_pred,
                           const pddl_params_t *param);

/**
 * Enforce identity mapping for all counted variables.
 */
void pddlUnifyResetCountedVars(const pddl_unify_t *u);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_UNIFY_H__ */
