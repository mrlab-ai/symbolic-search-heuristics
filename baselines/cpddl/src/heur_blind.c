/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "_heur.h"
#include "internal.h"

static void heurDel(pddl_heur_t *h)
{
    _pddlHeurFree(h);
    FREE(h);
}

static int heurEstimate(pddl_heur_t *h,
                        const pddl_fdr_state_space_node_t *node,
                        const pddl_fdr_state_space_t *state_space)
{
    return 0;
}

pddl_heur_t *pddlHeurBlind(void)
{
    pddl_heur_t *h = ALLOC(pddl_heur_t);
    _pddlHeurInit(h, heurDel, heurEstimate);
    return h;

}

