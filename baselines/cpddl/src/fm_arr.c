/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/fm_arr.h"

void pddlFmArrInit(pddl_fm_arr_t *ca)
{
    ZEROIZE(ca);
}

void pddlFmArrFree(pddl_fm_arr_t *ca)
{
    if (ca->fm)
        FREE(ca->fm);
}

void pddlFmArrAdd(pddl_fm_arr_t *ca, const pddl_fm_t *c)
{
    if (ca->size >= ca->alloc){
        if (ca->alloc == 0)
            ca->alloc = 1;
        ca->alloc *= 2;
        ca->fm = REALLOC_ARR(ca->fm, const pddl_fm_t *, ca->alloc);
    }
    ca->fm[ca->size++] = c;
}

void pddlFmArrInitCopy(pddl_fm_arr_t *dst, const pddl_fm_arr_t *src)
{
    *dst = *src;
    if (src->fm != NULL){
        dst->fm = ALLOC_ARR(const pddl_fm_t *, dst->alloc);
        memcpy(dst->fm, src->fm, sizeof(pddl_fm_t *) * src->size);
    }
}
