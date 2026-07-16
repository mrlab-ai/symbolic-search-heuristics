/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL__HEUR_H__
#define __PDDL__HEUR_H__

#include "internal.h"
#include "pddl/heur.h"

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

typedef void (*pddl_heur_del_fn)(pddl_heur_t *h);
typedef int (*pddl_heur_estimate_fn)(pddl_heur_t *h,
                                     const pddl_fdr_state_space_node_t *node,
                                     const pddl_fdr_state_space_t *state_space);
struct pddl_heur {
    pddl_heur_del_fn del_fn;
    pddl_heur_estimate_fn estimate_fn;
};

_pddl_inline void _pddlHeurInit(pddl_heur_t *h,
                                pddl_heur_del_fn del_fn,
                                pddl_heur_estimate_fn estimate_fn)
{
    ZEROIZE(h);
    h->del_fn = del_fn;
    h->estimate_fn = estimate_fn;
}

_pddl_inline void _pddlHeurFree(pddl_heur_t *h)
{
}

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL__HEUR_H__ */
