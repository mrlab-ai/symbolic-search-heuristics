/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_HOMOMORPHISM_HEUR_H__
#define __PDDL_HOMOMORPHISM_HEUR_H__

#include <pddl/homomorphism.h>
#include <pddl/strips.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_homomorphism_heur {
    /** Homomorphic image */
    pddl_t homo;
    /** Grounded .homo */
    pddl_strips_t strips;
    /** Mapping from the objects in the original pddl problem to the
     *  objects in its homomorphic image */
    int *obj_map;
    /** Mapping from the ground atoms comming from search to local strips
     *  facts */
    int *ground_atom_to_strips_fact;
    int ground_atom_to_strips_fact_size;

    int _type; /*!< Type of the heuristc */
};
typedef struct pddl_homomorphism_heur pddl_homomorphism_heur_t;

pddl_homomorphism_heur_t *pddlHomomorphismHeurLMCut(
                                const pddl_t *pddl,
                                const pddl_homomorphism_config_t *cfg,
                                pddl_err_t *err);
pddl_homomorphism_heur_t *pddlHomomorphismHeurHFF(
                                const pddl_t *pddl,
                                const pddl_homomorphism_config_t *cfg,
                                pddl_err_t *err);

void pddlHomomorphismHeurDel(pddl_homomorphism_heur_t *h);

int pddlHomomorphismHeurEvalGroundInit(pddl_homomorphism_heur_t *h);

int pddlHomomorphismHeurEval(pddl_homomorphism_heur_t *h,
                             const pddl_iset_t *state,
                             const pddl_ground_atoms_t *gatoms);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_HOMOMORPHISM_HEUR_H__ */
