/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/err.h"
#include "pddl/sort.h"
#include "internal.h"

#define DEFAULT_SORT pddlQSort

_pddl_inline void sort2(void *e1, void *e2, size_t size,
                        pddl_sort_cmp cmp, void *arg)
{
    if (cmp(e2, e1, arg) < 0){
        unsigned char tmp[size];
        memcpy(tmp, e1, size);
        memcpy(e1, e2, size);
        memcpy(e2, tmp, size);
    }
}

_pddl_inline void sort3(void *e1, void *e2, void *e3, size_t size,
                        pddl_sort_cmp cmp, void *arg)
{
    sort2(e1, e2, size, cmp, arg);
    sort2(e2, e3, size, cmp, arg);
    sort2(e1, e2, size, cmp, arg);
}

int pddlSort(void *base, size_t nmemb, size_t size,
             pddl_sort_cmp cmp, void *carg)
{
    if (nmemb <= 1)
        return 0;
    if (nmemb == 2){
        char *begin = base;
        sort2(begin, begin + size, size, cmp, carg);
        return 0;
    }
    if (nmemb == 3){
        char *begin = base;
        sort3(begin, begin + size, begin + size + size, size, cmp, carg);
        return 0;
    }

    int ret = DEFAULT_SORT(base, nmemb, size, cmp, carg);
#ifdef PDDL_DEBUG
    for (int i = 1; i < nmemb; ++i){
        char *ca = base;
        ASSERT(cmp(ca + (i - 1) * size, ca + i * size, carg) <= 0);
    }
#endif /* PDDL_DEBUG */

    return ret;
}

int pddlStableSort(void *base, size_t nmemb, size_t size,
                   pddl_sort_cmp cmp, void *carg)
{
    if (nmemb <= 1)
        return 0;
    if (nmemb == 2){
        char *begin = base;
        sort2(begin, begin + size, size, cmp, carg);
        return 0;
    }
    if (nmemb == 3){
        char *begin = base;
        sort3(begin, begin + size, begin + size + size, size, cmp, carg);
        return 0;
    }

    int ret = pddlTimSort(base, nmemb, size, cmp, carg);
#ifdef PDDL_DEBUG
    for (int i = 1; i < nmemb; ++i){
        char *ca = base;
        ASSERT(cmp(ca + (i - 1) * size, ca + i * size, carg) <= 0);
    }
#endif /* PDDL_DEBUG */

    return ret;
}

static int cmpInt(const void *a, const void *b, void *_)
{
    int i1 = *(int *)a;
    int i2 = *(int *)a;
    if (i1 < i2)
        return -1;
    if (i1 > i2)
        return 1;
    return 0;
}

int pddlSortInt(int *base, size_t nmemb)
{
    return pddlSort(base, nmemb, sizeof(int), cmpInt, NULL);
}
