/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/arr.h"

void pddlArrFree(pddl_arr_t *a)
{
    if (a->arr != NULL)
        FREE(a->arr);
}

void pddlArrRealloc(pddl_arr_t *a, int size)
{
    while (size > a->alloc){
        if (a->alloc == 0)
            a->alloc = 1;
        a->alloc *= 2;
    }
    a->arr = REALLOC_ARR(a->arr, TYPE, a->alloc);
}
