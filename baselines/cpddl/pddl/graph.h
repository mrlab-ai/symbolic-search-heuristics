/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_GRAPH_H__
#define __PDDL_GRAPH_H__

#include <pddl/iset.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_graph_simple {
    pddl_iset_t *node;
    int node_size;
};
typedef struct pddl_graph_simple pddl_graph_simple_t;

void pddlGraphSimpleInit(pddl_graph_simple_t *g, int node_size);
void pddlGraphSimpleFree(pddl_graph_simple_t *g);
void pddlGraphSimpleAddEdge(pddl_graph_simple_t *g, int n1, int n2);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_GRAPH_H__ */
