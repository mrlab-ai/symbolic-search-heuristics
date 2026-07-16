/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_ALLOC_H__
#define __PDDL_ALLOC_H__

#include <pddl/common.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Alloc - Memory Allocation
 * ==========================
 *
 * Functions and macros for memory allocation.
 */


/**
 * Allocate memory for one element of given type.
 */
#define PDDL_ALLOC(type) (type *)pddlMalloc(sizeof(type))

/**
 * Allocate array of elements of given type.
 */
#define PDDL_ALLOC_ARR(type, num_elements) \
    (type *)pddlMallocArr((num_elements), sizeof(type))

/**
 * Reallocates array.
 */
#define PDDL_REALLOC_ARR(ptr, type, num_elements) \
    (type *)pddlReallocArr((ptr), (num_elements), sizeof(type))

/**
 * Allocate array of elements of given type initialized to zero.
 */
#define PDDL_ZALLOC_ARR(type, num_elements) \
    (type *)pddlZallocArr((num_elements), sizeof(type))

/**
 * Allocated zeroized struct
 */
#define PDDL_ZALLOC(type) (type *)pddlZalloc(sizeof(type))

/**
 * Raw memory allocation.
 */
#define PDDL_MALLOC(size) pddlMalloc((size))

/**
 * Raw memory allocation.
 */
#define PDDL_ZMALLOC(size) pddlZalloc((size))

/**
 * Wrapped strdup() for consistency in memory allocation.
 */
#define PDDL_STRDUP(str) pddlStrdup((str))

/**
 * Free allocated memory
 */
#define PDDL_FREE(ptr) pddlFreeMem(ptr)


void *pddlMalloc(size_t size);
void *pddlMallocArr(size_t num_els, size_t size);
void *pddlReallocArr(void *ptr, size_t num_els, size_t size);
void *pddlZallocArr(size_t num_els, size_t size);
void *pddlZalloc(size_t size);
char *pddlStrdup(const char *str);
void pddlFreeMem(void *ptr);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_ALLOC_H__ */

