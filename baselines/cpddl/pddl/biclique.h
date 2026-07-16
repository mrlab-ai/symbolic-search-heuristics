/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_BICLIQUE_H__
#define __PDDL_BICLIQUE_H__

#include <pddl/graph.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

/**
 * Inference of maximal bicliques (i.e., maximal non-induced complete
 * bipartite subgraphs).
 * Implementation of MICA algorithm from
 * Alexe et al. (2001). Consensus algorithms for the generation of all
 * maximal bicliques. https://doi.org/10.1016/j.dam.2003.09.004
 */
void pddlBicliqueFindMaximal(const pddl_graph_simple_t *g,
                             void (*cb)(const pddl_iset_t *left,
                                        const pddl_iset_t *right, void *ud),
                             void *ud);


#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_BICLIQUE_H__ */
