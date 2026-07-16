/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_LIFTED_HEUR_RELAXED_H__
#define __PDDL_LIFTED_HEUR_RELAXED_H__

#include <pddl/datalog.h>
#include <pddl/strips_maker.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_lifted_heur_relaxed {
    const pddl_t *pddl;
    pddl_datalog_t *dl;
    unsigned *type_to_dlpred;
    unsigned *pred_to_dlpred;
    unsigned *obj_to_dlconst;
    unsigned *dlvar;
    int dlvar_size;
    unsigned goal_dlpred;
    pddl_bool_t collect_best_achiever_facts;

    int (*canonical_model)(pddl_datalog_t *,
                           pddl_cost_t *,
                           int collect_fact_achievers,
                           pddl_err_t *);

    /** Internal context for computing ff heuristic */
    void *ff_ctx;
};
typedef struct pddl_lifted_heur_relaxed pddl_lifted_heur_relaxed_t;

/**
 * Initialize heuristic as lifted h^max
 */
void pddlLiftedHMaxInit(pddl_lifted_heur_relaxed_t *h,
                        const pddl_t *pddl,
                        pddl_bool_t collect_best_achiever_facts,
                        pddl_err_t *err);

/**
 * Initialize heuristic as lifted h^add
 */
void pddlLiftedHAddInit(pddl_lifted_heur_relaxed_t *h,
                        const pddl_t *pddl,
                        pddl_bool_t collect_best_achiever_facts,
                        pddl_err_t *err);

/**
 * Initialize heuristic as lifted h^ff based on h^add
 */
void pddlLiftedHFFAddInit(pddl_lifted_heur_relaxed_t *h,
                          const pddl_t *pddl,
                          pddl_err_t *err);

/**
 * Initialize heuristic as lifted h^ff based on h^max
 */
void pddlLiftedHFFMaxInit(pddl_lifted_heur_relaxed_t *h,
                          const pddl_t *pddl,
                          pddl_err_t *err);

/**
 * Free allocated memory.
 */
void pddlLiftedHeurRelaxedFree(pddl_lifted_heur_relaxed_t *h);

/**
 * Returns heuristic value for the given state.
 */
pddl_cost_t pddlLiftedHeurRelaxedEvalState(pddl_lifted_heur_relaxed_t *h,
                                           const pddl_iset_t *state,
                                           const pddl_ground_atoms_t *gatoms);

void pddlLiftedHeurRelaxedBestAchieverFacts(pddl_lifted_heur_relaxed_t *h,
                                            const pddl_ground_atoms_t *gatoms,
                                            pddl_iset_t *achievers);
#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_LIFTED_HEUR_RELAXED_H__ */
