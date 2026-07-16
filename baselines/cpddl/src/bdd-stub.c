#include "internal.h"
#include "pddl/libs_info.h"
#include "pddl/bdd.h"
const char * const pddl_cudd_version = NULL;
#define ERROR PANIC("Binary decision diagrams require the CUDD library; cpddl must be re-compiled with the CUDD support.")
pddl_bdd_manager_t *pddlBDDManagerNew(int bdd_var_size,
                                      unsigned int cache_size)
{ ERROR;return NULL;}
void pddlBDDManagerDel(pddl_bdd_manager_t *mgr)
{ ERROR;}
float pddlBDDMem(pddl_bdd_manager_t *mgr)
{ ERROR;return -1;}
int pddlBDDGCUsed(pddl_bdd_manager_t *mgr)
{ ERROR;return -1;}
void pddlBDDDel(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd)
{ ERROR;}
pddl_bdd_t *pddlBDDClone(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd)
{ ERROR;return NULL;}
pddl_bool_t pddlBDDIsFalse(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd)
{ ERROR;return -1;}
pddl_bdd_t *pddlBDDNot(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd)
{ ERROR;return NULL;}
pddl_bdd_t *pddlBDDZero(pddl_bdd_manager_t *mgr)
{ ERROR;return NULL;}
pddl_bdd_t *pddlBDDOne(pddl_bdd_manager_t *mgr)
{ ERROR;return NULL;}
pddl_bdd_t *pddlBDDVar(pddl_bdd_manager_t *mgr, int i)
{ ERROR;return NULL;}
pddl_bdd_t *pddlBDDAnd(pddl_bdd_manager_t *mgr,
                       pddl_bdd_t *bdd1,
                       pddl_bdd_t *bdd2)
{ ERROR;return NULL;}
pddl_bdd_t *pddlBDDAndLimit(pddl_bdd_manager_t *mgr,
                            pddl_bdd_t *bdd1,
                            pddl_bdd_t *bdd2,
                            unsigned int size_limit,
                            pddl_time_limit_t *time_limit)
{ ERROR;return NULL;}
pddl_bdd_t *pddlBDDAndAbstract(pddl_bdd_manager_t *mgr,
                               pddl_bdd_t *bdd1,
                               pddl_bdd_t *bdd2,
                               pddl_bdd_t *cube)
{ ERROR;return NULL;}
pddl_bdd_t *pddlBDDAndAbstractLimit(pddl_bdd_manager_t *mgr,
                                    pddl_bdd_t *bdd1,
                                    pddl_bdd_t *bdd2,
                                    pddl_bdd_t *cube,
                                    unsigned int size_limit,
                                    pddl_time_limit_t *time_limit)
{ ERROR;return NULL;}
pddl_bdd_t *pddlBDDSwapVars(pddl_bdd_manager_t *mgr,
                            pddl_bdd_t *bdd,
                            pddl_bdd_t **v1,
                            pddl_bdd_t **v2,
                            int n)
{ ERROR;return NULL;}
void pddlBDDPickOneCube(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd, char *cube)
{ ERROR;}
int pddlBDDAndUpdate(pddl_bdd_manager_t *mgr,
                     pddl_bdd_t **bdd1,
                     pddl_bdd_t *bdd2)
{ ERROR;return -1;}
pddl_bdd_t *pddlBDDOr(pddl_bdd_manager_t *mgr,
                      pddl_bdd_t *bdd1,
                      pddl_bdd_t *bdd2)
{ ERROR;return NULL;}
pddl_bdd_t *pddlBDDOrLimit(pddl_bdd_manager_t *mgr,
                           pddl_bdd_t *bdd1,
                           pddl_bdd_t *bdd2,
                           unsigned int size_limit,
                           pddl_time_limit_t *time_limit)
{ ERROR;return NULL;}
int pddlBDDOrUpdate(pddl_bdd_manager_t *mgr,
                    pddl_bdd_t **bdd1,
                    pddl_bdd_t *bdd2)
{ ERROR;return -1;}
pddl_bdd_t *pddlBDDXnor(pddl_bdd_manager_t *mgr,
                        pddl_bdd_t *bdd1,
                        pddl_bdd_t *bdd2)
{ ERROR;return NULL;}
int pddlBDDSize(pddl_bdd_t *bdd)
{ ERROR;return -1;}
double pddlBDDCountMinterm(pddl_bdd_manager_t *mgr, pddl_bdd_t *bdd, int n)
{ ERROR;return -1;}
pddl_bdd_t *pddlBDDCube(pddl_bdd_manager_t *mgr, pddl_bdd_t **bdd, int n)
{ ERROR;return NULL;}
