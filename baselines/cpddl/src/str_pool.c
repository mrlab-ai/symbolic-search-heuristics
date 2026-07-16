/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/str_pool.h"
#include "pddl/hfunc.h"

#define SEGMENT_SIZE 256

static pddl_htable_key_t strPoolHash(const pddl_list_t *k, void *_)
{
    const pddl_str_pool_el_t *e = PDDL_LIST_ENTRY(k, pddl_str_pool_el_t, htable);
    return e->hash;
}

static int strPoolEq(const pddl_list_t *k1, const pddl_list_t *k2, void *_)
{
    const pddl_str_pool_el_t *e1 = PDDL_LIST_ENTRY(k1, pddl_str_pool_el_t, htable);
    const pddl_str_pool_el_t *e2 = PDDL_LIST_ENTRY(k2, pddl_str_pool_el_t, htable);
    if (e1->strsize != e2->strsize)
        return 0;
    return strncmp(e1->str, e2->str, e1->strsize) == 0;
}

void pddlStrPoolInit(pddl_str_pool_t *pool)
{
    size_t segm_size = sizeof(pddl_str_pool_el_t) * SEGMENT_SIZE;
    pool->str = pddlSegmArrNew(sizeof(pddl_str_pool_el_t), segm_size);
    pool->str_size = 0;
    pool->htable = pddlHTableNew(strPoolHash, strPoolEq, NULL);
}

void pddlStrPoolFree(pddl_str_pool_t *pool)
{
    for (int i = 0; i < pool->str_size; ++i){
        pddl_str_pool_el_t *e = pddlSegmArrGet(pool->str, i);
        if (e->str != NULL)
            FREE(e->str);
    }

    pddlHTableDel(pool->htable);
    pddlSegmArrDel(pool->str);
}

int pddlStrPoolSize(const pddl_str_pool_t *pool)
{
    return pool->str_size;
}

const char *pddlStrPoolGet(const pddl_str_pool_t *pool, int id)
{
    if (id >= pool->str_size || id < 0)
        return NULL;

    const pddl_str_pool_el_t *e = pddlSegmArrConstGet(pool->str, id);
    return e->str;
}

int pddlStrPoolAdd(pddl_str_pool_t *pool, const char *s)
{
    int size = strlen(s);
    return pddlStrPoolAddSize(pool, s, size);
}

int pddlStrPoolAddSize(pddl_str_pool_t *pool, const char *s, int size)
{
    pddl_str_pool_el_t *e = pddlSegmArrGet(pool->str, pool->str_size);
    e->str = (char *)s;
    e->strsize = size;
    e->hash = pddlCityHash_64(e->str, e->strsize);

    pddl_list_t *ins;
    if ((ins = pddlHTableInsertUnique(pool->htable, &e->htable)) == NULL){
        e->id = pool->str_size++;
        e->str = MALLOC(size + 1);
        memcpy(e->str, s, size);
        e->str[size] = '\x0';

    }else{
        e = PDDL_LIST_ENTRY(ins, pddl_str_pool_el_t, htable);
    }

    return e->id;
}
