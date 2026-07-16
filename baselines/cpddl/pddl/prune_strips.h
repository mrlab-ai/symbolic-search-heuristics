/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_PRUNE_STRIPS_H__
#define __PDDL_PRUNE_STRIPS_H__

#include <pddl/common.h>
#include <pddl/strips.h>
#include <pddl/mgroup.h>
#include <pddl/mutex_pair.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_prune_strips {
    pddl_mgroups_t mgroup;
    pddl_mutex_pairs_t mutex;
    pddl_list_t prune;
    pddl_list_t conn;
};
typedef struct pddl_prune_strips pddl_prune_strips_t;


void pddlPruneStripsInit(pddl_prune_strips_t *prune);

void pddlPruneStripsFree(pddl_prune_strips_t *prune);

int pddlPruneStripsExecute(pddl_prune_strips_t *prune,
                           pddl_strips_t *strips,
                           pddl_mgroups_t *mgroups,
                           pddl_err_t *err);

void pddlPruneStripsAddIrrelevance(pddl_prune_strips_t *prune);

void pddlPruneStripsAddUnreachableInDTGs(pddl_prune_strips_t *prune);

void pddlPruneStripsAddFAMGroupDeadEnd(pddl_prune_strips_t *prune);

void pddlPruneStripsAddH2(pddl_prune_strips_t *prune, float time_limit_in_s);
void pddlPruneStripsAddH2FwBw(pddl_prune_strips_t *prune, float time_limit_in_s);
void pddlPruneStripsAddH3(pddl_prune_strips_t *prune,
                          float time_limit_in_s,
                          size_t excess_mem);

void pddlPruneStripsAddDeduplicateOps(pddl_prune_strips_t *prune);

// TODO
//void pddlPruneStripsAddEndomorphism(pddl_prune_strips_t *prune);

// TODO
//void pddlPruneStripsAddOpMutexOpFact(pddl_prune_strips_t *prune);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_PRUNE_STRIPS_H__ */
