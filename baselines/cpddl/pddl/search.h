/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_SEARCH_H__
#define __PDDL_SEARCH_H__

#include <pddl/fdr.h>
#include <pddl/heur.h>
#include <pddl/plan.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

enum pddl_search_status {
    PDDL_SEARCH_CONT = 0,
    PDDL_SEARCH_UNSOLVABLE,
    PDDL_SEARCH_FOUND,
    PDDL_SEARCH_ABORT,
};
typedef enum pddl_search_status pddl_search_status_t;

enum pddl_search_alg {
    PDDL_SEARCH_ASTAR,
    PDDL_SEARCH_GBFS,
    PDDL_SEARCH_LAZY,
};
typedef enum pddl_search_alg pddl_search_alg_t;

struct pddl_search_stat {
    /** Number of calls to *Step() */
    size_t steps;
    /** Number of times expansions of states */
    size_t expanded;
    /** Same as .expanded, but before the last f layer */
    size_t expanded_before_last_f_layer;
    /** Number of times heuristic function is evaluated */
    size_t evaluated;
    /** Number of different states created so far */
    size_t generated;
    /** Number of states currently in the open list */
    size_t open;
    /** Number of closed states so far */
    size_t closed;
    /** Number of times a state was re-opened. */
    size_t reopen;
    /** Number of states detected as dead-end states */
    size_t dead_end;
    /** Same as .dead_end, but before the last f layer */
    size_t dead_end_before_last_f_layer;
    /** Last f-value encoutered during the search */
    int last_f_value;
};
typedef struct pddl_search_stat pddl_search_stat_t;

struct pddl_search_config {
    /** Input task */
    const pddl_fdr_t *fdr;
    /** Algorithm used for the lifted search */
    pddl_search_alg_t alg;
    /** Heuristic function */
    pddl_heur_t *heur;
};
typedef struct pddl_search_config pddl_search_config_t;

#define PDDL_SEARCH_CONFIG_INIT \
    { \
        NULL, /* .fdr */ \
        PDDL_SEARCH_ASTAR, /* .alg */ \
        NULL, /* .heur */ \
    }

typedef struct pddl_search pddl_search_t;

pddl_search_t *pddlSearchNew(const pddl_search_config_t *cfg, pddl_err_t *err);
void pddlSearchDel(pddl_search_t *);
pddl_search_status_t pddlSearchInitStep(pddl_search_t *);
pddl_search_status_t pddlSearchStep(pddl_search_t *);
int pddlSearchExtractPlan(pddl_search_t *, pddl_plan_t *plan);

void pddlSearchStat(const pddl_search_t *, pddl_search_stat_t *stat);
void pddlSearchStatLog(const pddl_search_t *s, pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_SEARCH_H__ */
