/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_INTERNAL_H__
#define __PDDL_INTERNAL_H__

#include "pddl/common.h"
#include "pddl/err.h"
#include "pddl/alloc.h"

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#define CONTAINER_OF_CONST(name, ptr, type, member) \
    const type *name = pddl_container_of((ptr), type, member)
#define CONTAINER_OF(name, ptr, type, member) \
    type *name = pddl_container_of((ptr), type, member)

#define ERR PDDL_ERR
#define ERR_RET PDDL_ERR_RET
#define PANIC PDDL_PANIC
#define PANIC_IF PDDL_PANIC_IF
#define WARN PDDL_WARN
#define CTX PDDL_CTX
#define CTX_NO_TIME PDDL_CTX_NO_TIME
#define CTXEND PDDL_CTXEND
#define LOG PDDL_LOG
#define LOG_IN_CTX PDDL_LOG_IN_CTX
#define TRACE PDDL_TRACE
#define TRACE_RET PDDL_TRACE_RET
#define TRACE_PREPEND PDDL_TRACE_PREPEND
#define TRACE_PREPEND_RET PDDL_TRACE_PREPEND_RET

#define LOG_CONFIG_INT(C, NAME, ERR) \
    LOG((ERR), #NAME " = %d", (C)->NAME)
#define LOG_CONFIG_ULONG(C, NAME, ERR) \
    LOG((ERR), #NAME " = %lu", (C)->NAME)
#define LOG_CONFIG_DBL(C, NAME, ERR) \
    LOG((ERR), #NAME " = %.4f", (C)->NAME)
#define LOG_CONFIG_BOOL(C, NAME, ERR) \
    LOG((ERR), #NAME " = %s", F_BOOL((C)->NAME))
#define LOG_CONFIG_STR(C, NAME, ERR) \
    LOG((ERR), #NAME " = %s", ((C)->NAME != NULL ? (C)->NAME : "(null)"))


#ifdef PDDL_DEBUG
#include <assert.h>
# define ASSERT(x) assert(x)

#else /* PDDL_DEBUG */

# define NDEBUG
# define ASSERT(x)
#endif /* PDDL_DEBUG */



#define F_BOOL(C) ((C) ? "true" : "false")
#define F_COST(C) pddlCostFmt((C), ((char [22]){""}), 22)
#define F_FM(C, PDDL, PARAMS) \
    pddlFmFmt((C), (PDDL), (PARAMS), ((char [2048]){""}), 2048)
#define F_FM_PDDL(C, PDDL, PARAMS) \
    pddlFmPDDLFmt((C), (PDDL), (PARAMS), ((char [2048]){""}), 2048)
#define F_FM_PDDL_BUFSIZE(C, PDDL, PARAMS, BUFSIZE) \
    pddlFmPDDLFmt((C), (PDDL), (PARAMS), ((char [(BUFSIZE)]){""}), (BUFSIZE))
#define F_LIFTED_MGROUP(PDDL, MG) \
    pddlLiftedMGroupFmt((PDDL), (MG), ((char [2048]){""}), 2048)


#define ZEROIZE PDDL_ZEROIZE
#define ZEROIZE_ARR PDDL_ZEROIZE_ARR
#define ZEROIZE_RAW PDDL_ZEROIZE_RAW

#define ALLOC PDDL_ALLOC
#define ALLOC_ARR PDDL_ALLOC_ARR
#define REALLOC_ARR PDDL_REALLOC_ARR
#define ZALLOC_ARR PDDL_ZALLOC_ARR
#define ZALLOC PDDL_ZALLOC
#define MALLOC PDDL_MALLOC
#define ZMALLOC PDDL_ZMALLOC
#define STRDUP PDDL_STRDUP
#define FREE PDDL_FREE

#define ZEROIZE_PTR(P) bzero((P), sizeof(*(P)))


#define ARR_MAKE_SPACE(PTR, TYPE, SIZE, ALLOC, INIT_SIZE) \
    do { \
        if ((SIZE) == (ALLOC)){ \
            if ((ALLOC) == 0){ \
                (ALLOC) = (INIT_SIZE); \
            } \
            (ALLOC) *= 2; \
            (PTR) = REALLOC_ARR((PTR), TYPE, (ALLOC)); \
        } \
    } while (0)

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_INTERNAL_H__ */
