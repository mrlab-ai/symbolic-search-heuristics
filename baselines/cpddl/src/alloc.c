/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/alloc.h"
#include "pddl/err.h"

#ifdef PDDL_MIMALLOC
# include <mimalloc.h>
# define mem_malloc(size) mi_malloc(size)
# define mem_malloc_arr(num_els, size) mi_mallocn((num_els), (size))
# define mem_realloc_arr(ptr, num_els, size) mi_reallocn((ptr), (num_els), (size))
# define mem_zalloc_arr(num_els, size) mi_calloc((num_els), (size))
# define mem_zalloc(size) mi_zalloc(size)
# define mem_strdup(str) mi_strdup(str)
# define mem_free(ptr) mi_free(ptr)
#else /* PDDL_MIMALLOC */
# define mem_malloc(size) malloc(size)
# define mem_malloc_arr(num_els, size) malloc((num_els) * (size))
# define mem_realloc_arr(ptr, num_els, size) realloc((ptr), (num_els) * (size))
# define mem_zalloc_arr(num_els, size) calloc((num_els), (size))
# define mem_zalloc(size) calloc(1, (size))
# define mem_strdup(str) strdup(str)
# define mem_free(ptr) free(ptr)
#endif /* PDDL_MIMALLOC */

void *pddlMalloc(size_t size)
{
    if (size == 0)
        return NULL;

    void *mem = mem_malloc(size);
    if (mem == NULL)
        PDDL_PANIC("Fatal Error: Allocation of memory failed!");
    return mem;
}

void *pddlMallocArr(size_t num_els, size_t size)
{
    if (num_els == 0 || size == 0)
        return NULL;

    void *mem = mem_malloc_arr(num_els, size);
    if (mem == NULL)
        PDDL_PANIC("Fatal Error: Allocation of memory failed!");
    return mem;
}

void *pddlReallocArr(void *ptr, size_t num_els, size_t size)
{
    void *mem = mem_realloc_arr(ptr, num_els, size);
    if (mem == NULL && size != 0)
        PDDL_PANIC("Fatal Error: Allocation of memory failed!");
    return mem;
}

void *pddlZallocArr(size_t num_els, size_t size)
{
    if (num_els == 0 || size == 0)
        return NULL;

    void *mem = mem_zalloc_arr(num_els, size);
    if (mem == NULL)
        PDDL_PANIC("Fatal Error: Allocation of memory failed!");
    return mem;
}

void *pddlZalloc(size_t size)
{
    if (size == 0)
        return NULL;

    void *mem = mem_zalloc(size);
    if (mem == NULL)
        PDDL_PANIC("Fatal Error: Allocation of memory failed!");
    return mem;
}

char *pddlStrdup(const char *str)
{
    char *s = mem_strdup(str);
    if (s == NULL)
        PDDL_PANIC("Fatal Error: Allocation of memory failed!");
    return s;
}

void pddlFreeMem(void *ptr)
{
    if (ptr != NULL)
        mem_free(ptr);
}
