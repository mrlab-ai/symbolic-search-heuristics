/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_MUTEX_PAIR_H__
#define __PDDL_MUTEX_PAIR_H__

#include <pddl/common.h>
#include <pddl/mgroup.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_strips;
struct pddl_fdr_vars;

/**
 * A set of mutexes of size at most 1, i.e., inreachable facts and mutex
 * pairs.
 */
struct pddl_mutex_pairs {
    char *map; /*!< 2-D map of facts */
    int fact_size; /*!< Dimension of .map */
    size_t num_mutex_pairs; /*!< Number of mutex pairs */
};
typedef struct pddl_mutex_pairs pddl_mutex_pairs_t;

#define PDDL_MUTEX_PAIRS_FOR_EACH(MP, F1, F2) \
    for (int F1 = 0; F1 < (MP)->fact_size; ++F1) \
        for (int F2 = F1; F2 < (MP)->fact_size; ++F2) \
            if (pddlMutexPairsIsMutex((MP), F1, F2))

/**
 * Initialize empty set of mutex pairs.
 * fact_size is the maximal number of facts the structure can represent,
 * i.e., any fact with ID >= fact_size cannot be stored and
 * pddlMutexPairsAdd() will fail in that case.
 * The maximum ID is checked only in pddlMutexPairsAdd(), all other functions
 * will probably fail horribly if you feed them with any fact ID >= fact_size.
 */
void pddlMutexPairsInit(pddl_mutex_pairs_t *m, int fact_size);
void pddlMutexPairsInitStrips(pddl_mutex_pairs_t *m,
                              const struct pddl_strips *s);

/**
 * Initialize dst as a copy of src.
 */
void pddlMutexPairsInitCopy(pddl_mutex_pairs_t *dst,
                            const pddl_mutex_pairs_t *src);

/**
 * Free allocated memory.
 */
void pddlMutexPairsFree(pddl_mutex_pairs_t *m);

/**
 * Empty the set of mutex pairs.
 * If fact_size > 0 then the map is re-allocated.
 */
void pddlMutexPairsEmpty(pddl_mutex_pairs_t *m, int fact_size);

/**
 * Add pair mutex or unreachable fact if f1 == f2.
 * Return 0 on success, -1 i f1 >= m->size or f2 >= m->size.
 */
int pddlMutexPairsAdd(pddl_mutex_pairs_t *m, int f1, int f2);

/**
 * Set mutex as forward mutex, {f1, f2} must be already mutex.
 */
int pddlMutexPairsSetFwMutex(pddl_mutex_pairs_t *m, int f1, int f2);

/**
 * Set mutex as backward mutex, {f1, f2} must be already mutex.
 */
int pddlMutexPairsSetBwMutex(pddl_mutex_pairs_t *m, int f1, int f2);

/**
 * Returns true if (f1, f2) is a mutex.
 */
pddl_bool_t pddlMutexPairsIsMutex(const pddl_mutex_pairs_t *m, int f1, int f2);

/**
 * Returns true if {f1, f2} is forward mutex.
 */
pddl_bool_t pddlMutexPairsIsFwMutex(const pddl_mutex_pairs_t *m, int f1, int f2);

/**
 * Returns true if {f1, f2} is backward mutex.
 */
pddl_bool_t pddlMutexPairsIsBwMutex(const pddl_mutex_pairs_t *m, int f1, int f2);

/**
 * Returns true if the set is mutex, i.e., it contains some mutex pair or
 * an unreachable fact.
 */
pddl_bool_t pddlMutexPairsIsMutexSet(const pddl_mutex_pairs_t *m, const pddl_iset_t *fs);

/**
 * Returns true if {fact} \cup fs is a mutex assuming that fs is not a
 * mutex.
 */
pddl_bool_t pddlMutexPairsIsMutexFactSet(const pddl_mutex_pairs_t *m,
                                         int fact, const pddl_iset_t *fs);

/**
 * Returns true if fs1 \cup fs2 is a mutex assuming fs1 and fs2 are not
 * mutexes.
 */
pddl_bool_t pddlMutexPairsIsMutexSetSet(const pddl_mutex_pairs_t *m,
                                        const pddl_iset_t *fs1,
                                        const pddl_iset_t *fs2);

/**
 * Add to {mutex_with} facts that are mutex with {fact}.
 */
void pddlMutexPairsGetMutexWith(const pddl_mutex_pairs_t *m,
                                int fact,
                                pddl_iset_t *mutex_with);

/**
 * Add to {not_mutex_with} facts that are NOT mutex with {fact} (excluding
 * {fact} itself).
 */
void pddlMutexPairsGetNotMutexWith(const pddl_mutex_pairs_t *m,
                                   int fact,
                                   pddl_iset_t *not_mutex_with);

/**
 * Resize the struct and remap fact IDs according to remap.
 */
void pddlMutexPairsRemapFacts(pddl_mutex_pairs_t *m,
                              int new_fact_size,
                              const int *remap);

/**
 * Reduce the struct by removing the specified set of facts.
 */
void pddlMutexPairsReduce(pddl_mutex_pairs_t *m, const pddl_iset_t *rm_facts);

/**
 * Add mutex pairs from the given mutex group.
 */
void pddlMutexPairsAddMGroup(pddl_mutex_pairs_t *mutex,
                             const pddl_mgroup_t *mg);

/**
 * Add mutex pairs from all the given mutex groups.
 */
void pddlMutexPairsAddMGroups(pddl_mutex_pairs_t *mutex,
                              const pddl_mgroups_t *mgs);


/**
 * Add mutex pairs from all the given variables.
 */
void pddlMutexPairsAddFDRVars(pddl_mutex_pairs_t *mutex,
                              const struct pddl_fdr_vars *vars);

/**
 * Infer mutex groups from the given set of mutex pairs.
 */
void pddlMutexPairsInferMutexGroups(const pddl_mutex_pairs_t *mutex,
                                    pddl_mgroups_t *mgroups,
                                    pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_MUTEX_PAIR_H__ */
