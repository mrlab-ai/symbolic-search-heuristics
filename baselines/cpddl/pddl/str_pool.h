/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

/**
 * This module implements a pool of unique strings.
 */

#ifndef __PDDL_STR_POOL_H__
#define __PDDL_STR_POOL_H__

#include <pddl/common.h>
#include <pddl/htable.h>
#include <pddl/segmarr.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_str_pool_el {
    /** ID of the string */
    int id;
    /** Stored unique string */
    char *str;
    /** Size of the string (not counting the terminating zero byte) */
    int strsize;
    /** Pre-computed hash of the string */
    pddl_htable_key_t hash;
    /** Connection to the hash table */
    pddl_list_t htable;
};
typedef struct pddl_str_pool_el pddl_str_pool_el_t;

struct pddl_str_pool {
    /** Pool of strings */
    pddl_segmarr_t *str;
    /** Number of string in the pool */
    int str_size;
    /** Hash table over .str */
    pddl_htable_t *htable;
};
typedef struct pddl_str_pool pddl_str_pool_t;

/**
 * Initilize empty pool.
 */
void pddlStrPoolInit(pddl_str_pool_t *pool);

/**
 * Free allocated memory.
 */
void pddlStrPoolFree(pddl_str_pool_t *pool);

/**
 * Returns number of unique strings stored in the pool.
 */
int pddlStrPoolSize(const pddl_str_pool_t *pool);

/**
 * Returns the string stored under the given {id}.
 */
const char *pddlStrPoolGet(const pddl_str_pool_t *pool, int id);

/**
 * Adds a zero-delimited string to the pool.
 * If {s} is already in the pool, the pool is not modified and the ID of
 * equal string from the pool is returned.
 * If {s} in not in the pool, it is added and its ID is returned.
 */
int pddlStrPoolAdd(pddl_str_pool_t *pool, const char *s);

/**
 * Like pddlStrPoolAdd(), but considers only the first {size} bytes of the
 * given string {s}.
 */
int pddlStrPoolAddSize(pddl_str_pool_t *pool, const char *s, int size);

#ifdef __cplusplus
}
#endif /* __cplusplus */

#endif /* __PDDL_STR_POOL_H__ */
