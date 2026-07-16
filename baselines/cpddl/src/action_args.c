/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/hfunc.h"
#include "pddl/action_args.h"

struct el {
    int id;
    pddl_htable_key_t key;
    pddl_list_t htable;
    int args[];
};
typedef struct el el_t;

static pddl_htable_key_t hash(const int *args, int size)
{
    return pddlCityHash_64(args, sizeof(int) * size);
}

static pddl_htable_key_t htableHash(const pddl_list_t *key, void *_)
{
    const el_t *el = PDDL_LIST_ENTRY(key, el_t, htable);
    return el->key;
}

static int htableEq(const pddl_list_t *key1, const pddl_list_t *key2, void *_args)
{
    const pddl_action_args_t *args = _args;
    const el_t *el1 = PDDL_LIST_ENTRY(key1, el_t, htable);
    const el_t *el2 = PDDL_LIST_ENTRY(key2, el_t, htable);
    return memcmp(el1->args, el2->args,
                  sizeof(int) * args->num_args) == 0;
}

void pddlActionArgsInit(pddl_action_args_t *args, int num_args)
{
    size_t size = sizeof(el_t) + sizeof(int) * num_args;

    ZEROIZE(args);
    args->num_args = num_args;
    args->arg_pool = pddlExtArrNew(size, NULL, NULL);
    args->htable = pddlHTableNew(htableHash, htableEq, args);
    args->args_size = 0;
}

void pddlActionArgsFree(pddl_action_args_t *args)
{
    pddlHTableDel(args->htable);
    pddlExtArrDel(args->arg_pool);
}

int pddlActionArgsAdd(pddl_action_args_t *args, const int *a)
{
    el_t *el = pddlExtArrGet(args->arg_pool, args->args_size);
    el->id = args->args_size;
    el->key = hash(a, args->num_args);
    memcpy(el->args, a, sizeof(int) * args->num_args);
    pddlListInit(&el->htable);

    pddl_list_t *ins = pddlHTableInsertUnique(args->htable, &el->htable);
    if (ins == NULL){
        ++args->args_size;
        return el->id;
    }else{
        el = PDDL_LIST_ENTRY(ins, el_t, htable);
        return el->id;
    }
}

const int *pddlActionArgsGet(const pddl_action_args_t *args, int id)
{
    if (id >= args->args_size)
        return NULL;
    const el_t *el = pddlExtArrGet(args->arg_pool, id);
    return el->args;
}

int pddlActionArgsSize(const pddl_action_args_t *args)
{
    return args->args_size;
}
