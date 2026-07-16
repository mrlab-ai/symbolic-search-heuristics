/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_HASHSET_H__
#define __PDDL_HASHSET_H__

#include <pddl/segmarr.h>
#include <pddl/htable.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

typedef pddl_htable_key_t (*pddl_hashset_hash_fn)(const void *el, void *ud);
typedef int (*pddl_hashset_eq_fn)(const void *el1, const void *el2, void *ud);
typedef void *(*pddl_hashset_clone_fn)(const void *el, void *ud);
typedef void (*pddl_hashset_del_fn)(void *el, void *ud);

struct pddl_hashset {
    pddl_hashset_hash_fn hash_fn;
    pddl_hashset_eq_fn eq_fn;
    pddl_hashset_clone_fn clone_fn;
    pddl_hashset_del_fn del_fn;
    void *userdata;

    pddl_segmarr_t *el;
    pddl_htable_t *htable;
    int size;
};
typedef struct pddl_hashset pddl_hashset_t;

/**
 * Initializes an empty set.
 */
void pddlHashSetInit(pddl_hashset_t *s,
                     pddl_hashset_hash_fn hash_fn,
                     pddl_hashset_eq_fn eq_fn,
                     pddl_hashset_clone_fn clone_fn,
                     pddl_hashset_del_fn del_fn,
                     void *userdata);

/**
 * Initialize an empty set of isets.
 */
void pddlHashSetInitISet(pddl_hashset_t *s);

/**
 * Free allocated memory.
 */
void pddlHashSetFree(pddl_hashset_t *s);

/**
 * Inserts the element into set and returns its ID within the sets if
 * successful.
 * If the element is already there it returns its ID and nothing is inserted.
 */
int pddlHashSetAdd(pddl_hashset_t *s, const void *el);

/**
 * Returns ID of the element or -1 if it is not there.
 */
int pddlHashSetFind(const pddl_hashset_t *s, const void *el);

/**
 * Returns the element with the corresponding ID.
 */
const void *pddlHashSetGet(const pddl_hashset_t *s, int id);


#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_HASHSET_H__ */
