/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/graph.h"

void pddlGraphSimpleInit(pddl_graph_simple_t *g, int node_size)
{
    ZEROIZE(g);
    g->node_size = node_size;
    g->node = ZALLOC_ARR(pddl_iset_t, g->node_size);
}

void pddlGraphSimpleFree(pddl_graph_simple_t *g)
{
    for (int i = 0; i < g->node_size; ++i)
        pddlISetFree(g->node + i);
    if (g->node != NULL)
        FREE(g->node);
}

void pddlGraphSimpleAddEdge(pddl_graph_simple_t *g, int n1, int n2)
{
    pddlISetAdd(&g->node[n1], n2);
    pddlISetAdd(&g->node[n2], n1);
}
