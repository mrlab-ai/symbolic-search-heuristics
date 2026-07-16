/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_SORT_H__
#define __PDDL_SORT_H__

#include <pddl/list.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Sort Algorithms
 * ================
 */

/**
 * Compare function for sort functions.
 */
typedef int (*pddl_sort_cmp)(const void *, const void *, void *arg);

/**
 * BSD kqsort.
 */
int pddlQSort(void *base, size_t nmemb, size_t size,
              pddl_sort_cmp cmp, void *carg);

/**
 * Tim sort.
 * Stable sort.
 */
int pddlTimSort(void *base, size_t nmemb, size_t size,
                pddl_sort_cmp cmp, void *carg);


/**
 * Default sorting algorithm.
 * Not guaranteed to be stable.
 */
int pddlSort(void *base, size_t nmemb, size_t size,
             pddl_sort_cmp cmp, void *carg);

/**
 * Default stable sort.
 */
int pddlStableSort(void *base, size_t nmemb, size_t size,
                   pddl_sort_cmp cmp, void *carg);


/**
 * Sort array of ints.
 */
int pddlSortInt(int *base, size_t nmemb);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_SORT_H__ */
