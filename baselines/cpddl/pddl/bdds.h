/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_BDDS_H__
#define __PDDL_BDDS_H__

#include <pddl/bdd.h>
#include <pddl/cost.h>

struct pddl_bdds {
    pddl_bdd_t **bdd;
    int bdd_size;
    int bdd_alloc;
};
typedef struct pddl_bdds pddl_bdds_t;

void pddlBDDsInit(pddl_bdds_t *bdds);
void pddlBDDsFree(pddl_bdd_manager_t *mgr, pddl_bdds_t *bdds);
void pddlBDDsAdd(pddl_bdd_manager_t *mgr, pddl_bdds_t *bdds, pddl_bdd_t *bdd);
long pddlBDDsSize(pddl_bdds_t *bdds);

/**
 * for every B in bdds:
 *   bdd = bdd & B
 */
void pddlBDDsAndUpdate(pddl_bdd_manager_t *mgr,
                       pddl_bdds_t *bdds,
                       pddl_bdd_t **bdd);

void pddlBDDsMergeAnd(pddl_bdd_manager_t *mgr,
                      pddl_bdds_t *bdds,
                      int max_nodes,
                      float max_time);

struct pddl_bdd_cost {
    pddl_bdd_t *bdd;
    pddl_cost_t cost;
};
typedef struct pddl_bdd_cost pddl_bdd_cost_t;

struct pddl_bdds_costs {
    pddl_bdd_cost_t *bdd;
    int bdd_size;
    int bdd_alloc;
};
typedef struct pddl_bdds_costs pddl_bdds_costs_t;

void pddlBDDsCostsInit(pddl_bdds_costs_t *bdds);
void pddlBDDsCostsFree(pddl_bdd_manager_t *mgr, pddl_bdds_costs_t *bdds);
void pddlBDDsCostsAdd(pddl_bdd_manager_t *mgr,
                      pddl_bdds_costs_t *bdds,
                      pddl_bdd_t *bdd,
                      const pddl_cost_t *cost);
void pddlBDDsCostsSortUniq(pddl_bdd_manager_t *mgr, pddl_bdds_costs_t *bdds);

#endif /* __PDDL_BDDS_H__ */
