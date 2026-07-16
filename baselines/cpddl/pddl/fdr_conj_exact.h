/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_FDR_CONJ_EXACT_H__
#define __PDDL_FDR_CONJ_EXACT_H__

#include <pddl/fdr.h>
#include <pddl/set.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_fdr_conj_exact_config {
    /** List of non-singleton conjunctions as sets of global-IDs */
    pddl_set_iset_t conj;
    /** If non-NULL, mutexes are used to prune unreachable operators */
    const pddl_mutex_pairs_t *mutex;
};
typedef struct pddl_fdr_conj_exact_config pddl_fdr_conj_exact_config_t;

/**
 * Initialize default configuration
 */
void pddlFDRConjExactConfigInit(pddl_fdr_conj_exact_config_t *cfg);

/**
 * Free allocated memory
 */
void pddlFDRConjExactConfigFree(pddl_fdr_conj_exact_config_t *cfg);

/**
 * Adds a conjunction
 */
void pddlFDRConjExactConfigAddConj(pddl_fdr_conj_exact_config_t *cfg,
                                   const pddl_iset_t *conj);

/**
 * Adds the given conjunction and all its (non-singleton) subsets.
 */
void pddlFDRConjExactConfigAddConjAndSubsets(pddl_fdr_conj_exact_config_t *cfg,
                                             const pddl_iset_t *conj);

/**
 * Add all conjunctions from the set {conjs}.
 */
void pddlFDRConjExactConfigAddConjs(pddl_fdr_conj_exact_config_t *cfg,
                                    const pddl_set_iset_t *conjs);


struct pddl_fdr_conjunction {
    /** Conjunction represented as a set of facts */
    pddl_iset_t fact;
    /** Conjunction as a partial state */
    pddl_fdr_part_state_t part_state;
    /** Conjunctions that are superset of this one */
    pddl_iset_t superset_of;
    /** Conjunctions that are subset of this one */
    pddl_iset_t subset_of;
    /** Variables of the conjunction */
    pddl_iset_t vars;
    /** Corresponding meta-variable ID */
    int var_id;
};
typedef struct pddl_fdr_conjunction pddl_fdr_conjunction_t;

struct pddl_fdr_conj_exact {
    /** Set of conjunctions */
    pddl_fdr_conjunction_t *conj;
    int conj_size;
    /** \Pi^C_{exact} FDR planning task */
    pddl_fdr_t fdr;
};
typedef struct pddl_fdr_conj_exact pddl_fdr_conj_exact_t;

/**
 * Initialize \Pi^C_{exact} planning task
 */
void pddlFDRConjExactInit(pddl_fdr_conj_exact_t *task,
                          const pddl_fdr_t *in_task,
                          const pddl_fdr_conj_exact_config_t *cfg,
                          pddl_err_t *err);

/**
 * Free allocated memory.
 */
void pddlFDRConjExactFree(pddl_fdr_conj_exact_t *task);

/**
 * Transform {in_mutex} for the original planning task to mutexes for the
 * {task}.
 * The function preserves also the information about forward and backward
 * mutexes.
 * It also extends mutexes to conjunctions: If the fact X is a mutex with
 * any fact from the conjunction C, then X is also a mutex with C itself.
 */
void pddlFDRConjExactMutexPairsInitCopy(pddl_mutex_pairs_t *mutex,
                                        const pddl_mutex_pairs_t *in_mutex,
                                        const pddl_fdr_conj_exact_t *task);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_FDR_CONJ_EXACT_H__ */
