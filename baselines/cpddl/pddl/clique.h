/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_CLIQUE_H__
#define __PDDL_CLIQUE_H__

#include <pddl/graph.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Maximal cliques (i.e., maximal induced complete subgraphs) of size at
 * least 2 using Bron-Kerbosch algorithm with pivoting.
 */
void pddlCliqueFindMaximal(const pddl_graph_simple_t *g,
                           void (*cb)(const pddl_iset_t *clique, void *userdata),
                           void *userdata);

/**
 * Same as above, but it uses cliquer library (if linked)
 * https://users.aalto.fi/~pat/cliquer.html
 */
void pddlCliqueFindMaximalCliquer(const pddl_graph_simple_t *g,
                           void (*cb)(const pddl_iset_t *clique, void *userdata),
                           void *userdata);

/**
 * Find maximal bicliques (i.e., maximal non-induced complete bipartite
 * subgraphs) by looking for cliques in a modified graph G':
 * Given G = (V, E), G' = (U \cup U', E') where U and U' are both copies of
 * V and E' = {(i,j) | i,j \in U, i \neq j }
 *            \cup {(i,j) | i,j \in U', i \neq j }
 *            \cup {(i,j') | i \in U, j' \in U', (i,j') \in E }
 */
void pddlCliqueFindMaximalBicliques(const pddl_graph_simple_t *G,
                                    void (*cb)(const pddl_iset_t *left,
                                               const pddl_iset_t *right,
                                               void *ud),
                                    void *ud);


#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_CLIQUE_H__ */
