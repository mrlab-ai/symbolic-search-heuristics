/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_BDD_H__
#define __PDDL_BDD_H__

#include <pddl/common.h>
#include <pddl/time_limit.h>

struct pddl_bdd_manager {
    int dummy;
};
typedef struct pddl_bdd_manager pddl_bdd_manager_t;

struct pddl_bdd {
    int dummy;
};
typedef struct pddl_bdd pddl_bdd_t;

pddl_bdd_manager_t *pddlBDDManagerNew(int bdd_var_size,
                                      unsigned int cache_size);
void pddlBDDManagerDel(pddl_bdd_manager_t *mgr);
float pddlBDDMem(pddl_bdd_manager_t *mgr);
int pddlBDDGCUsed(pddl_bdd_manager_t *mgr);

void pddlBDDDel(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd);


pddl_bdd_t *pddlBDDClone(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd);
pddl_bool_t pddlBDDIsFalse(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd);
pddl_bdd_t *pddlBDDNot(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd);
pddl_bdd_t *pddlBDDZero(pddl_bdd_manager_t *mgr);
pddl_bdd_t *pddlBDDOne(pddl_bdd_manager_t *mgr);
pddl_bdd_t *pddlBDDVar(pddl_bdd_manager_t *mgr, int i);
pddl_bdd_t *pddlBDDAnd(pddl_bdd_manager_t *mgr,
                       pddl_bdd_t *bdd1,
                       pddl_bdd_t *bdd2);
pddl_bdd_t *pddlBDDAndLimit(pddl_bdd_manager_t *mgr,
                            pddl_bdd_t *bdd1,
                            pddl_bdd_t *bdd2,
                            unsigned int size_limit,
                            pddl_time_limit_t *time_limit);
pddl_bdd_t *pddlBDDAndAbstract(pddl_bdd_manager_t *mgr,
                               pddl_bdd_t *bdd1,
                               pddl_bdd_t *bdd2,
                               pddl_bdd_t *cube);
pddl_bdd_t *pddlBDDAndAbstractLimit(pddl_bdd_manager_t *mgr,
                                    pddl_bdd_t *bdd1,
                                    pddl_bdd_t *bdd2,
                                    pddl_bdd_t *cube,
                                    unsigned int size_limit,
                                    pddl_time_limit_t *time_limit);
pddl_bdd_t *pddlBDDSwapVars(pddl_bdd_manager_t *mgr,
                            pddl_bdd_t *bdd,
                            pddl_bdd_t **v1,
                            pddl_bdd_t **v2,
                            int n);
void pddlBDDPickOneCube(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd, char *cube);
int pddlBDDAndUpdate(pddl_bdd_manager_t *mgr,
                     pddl_bdd_t **bdd1,
                     pddl_bdd_t *bdd2);
pddl_bdd_t *pddlBDDOr(pddl_bdd_manager_t *mgr,
                      pddl_bdd_t *bdd1,
                      pddl_bdd_t *bdd2);
pddl_bdd_t *pddlBDDOrLimit(pddl_bdd_manager_t *mgr,
                           pddl_bdd_t *bdd1,
                           pddl_bdd_t *bdd2,
                           unsigned int size_limit,
                           pddl_time_limit_t *time_limit);
int pddlBDDOrUpdate(pddl_bdd_manager_t *mgr,
                    pddl_bdd_t **bdd1,
                    pddl_bdd_t *bdd2);
pddl_bdd_t *pddlBDDXnor(pddl_bdd_manager_t *mgr,
                        pddl_bdd_t *bdd1,
                        pddl_bdd_t *bdd2);
int pddlBDDSize(pddl_bdd_t *bdd);
double pddlBDDCountMinterm(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd, int n);
pddl_bdd_t *pddlBDDCube(pddl_bdd_manager_t *mgr, pddl_bdd_t **bdd, int n);

#endif /* __PDDL_BDD_H__ */
