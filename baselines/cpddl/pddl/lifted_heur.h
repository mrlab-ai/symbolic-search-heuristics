/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_LIFTED_HEUR_H__
#define __PDDL_LIFTED_HEUR_H__

#include <pddl/pddl_struct.h>
#include "pddl/homomorphism_heur.h"
#include "pddl/cost.h"

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

typedef struct pddl_lifted_heur pddl_lifted_heur_t;

/**
 * Blind heuristic returning estimate 0 for every state.
 */
pddl_lifted_heur_t *pddlLiftedHeurBlind(void);

/**
 * h^max heuristic.
 */
pddl_lifted_heur_t *pddlLiftedHeurHMax(const pddl_t *pddl, pddl_err_t *err);

/**
 * h^add heuristic.
 */
pddl_lifted_heur_t *pddlLiftedHeurHAdd(const pddl_t *pddl, pddl_err_t *err);

/**
 * h^ff heuristic based on h^max heuristic.
 */
pddl_lifted_heur_t *pddlLiftedHeurHFFMax(const pddl_t *pddl, pddl_err_t *err);

/**
 * h^ff heuristic based on h^add heuristic.
 */
pddl_lifted_heur_t *pddlLiftedHeurHFFAdd(const pddl_t *pddl, pddl_err_t *err);

/**
 * Wrapper for homomorphism-based heuristic.
 */
pddl_lifted_heur_t *pddlLiftedHeurHomomorphism(pddl_homomorphism_heur_t *h);

/**
 * Max variant of the gaifman graph heuristic.
 */
pddl_lifted_heur_t *pddlLiftedHeurGaifmanMax(const pddl_t *pddl,
                                             pddl_bool_t estimate_plan_lengths,
                                             pddl_err_t *err);

/**
 * Add variant of the gaifman graph heuristic.
 */
pddl_lifted_heur_t *pddlLiftedHeurGaifmanAdd(const pddl_t *pddl,
                                             pddl_err_t *err);

/**
 * Destructor
 */
void pddlLiftedHeurDel(pddl_lifted_heur_t *h);

/**
 * Computes and returns a heuristic estimate.
 */
pddl_cost_t pddlLiftedHeurEstimate(pddl_lifted_heur_t *h,
                                   const pddl_iset_t *state,
                                   const pddl_ground_atoms_t *gatoms);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_LIFTED_HEUR_H__ */
