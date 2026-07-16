/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_COST_H__
#define __PDDL_COST_H__

#include <pddl/common.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_cost {
    int cost;
    int zero_cost;
};
typedef struct pddl_cost pddl_cost_t;

extern pddl_cost_t pddl_cost_zero;
extern pddl_cost_t pddl_cost_max;
extern pddl_cost_t pddl_cost_dead_end;

_pddl_inline void pddlCostSetZero(pddl_cost_t *c1)
{
    c1->cost = 0;
    c1->zero_cost = 0;
}

_pddl_inline void pddlCostSetMax(pddl_cost_t *c1)
{
    c1->cost = PDDL_COST_MAX;
    c1->zero_cost = PDDL_COST_MAX;
}

_pddl_inline void pddlCostSetOp(pddl_cost_t *c1, int op_cost)
{
    if (op_cost == 0){
        c1->cost = 0;
        c1->zero_cost = 1;
    }else{
        c1->cost = op_cost;
        c1->zero_cost = 0;
    }
}

/**
 * c1 += c2
 */
_pddl_inline void pddlCostSum(pddl_cost_t *c1, const pddl_cost_t *c2)
{
    c1->cost += c2->cost;
    c1->zero_cost += c2->zero_cost;
}

/**
 * Saturated sum
 */
_pddl_inline void pddlCostSumSat(pddl_cost_t *c1, const pddl_cost_t *c2)
{
    if (c1->cost >= PDDL_COST_MAX || c1->cost <= PDDL_COST_MIN)
        return;

    if (c2->cost >= PDDL_COST_MAX || c2->cost <= PDDL_COST_MIN){
        c1->cost = c2->cost;
    }else{
        c1->cost += c2->cost;
    }

    c1->zero_cost += c2->zero_cost;
}


/**
 * Compare c1 and c2
 */
_pddl_inline int pddlCostCmp(const pddl_cost_t *c1, const pddl_cost_t *c2)
{
    int cmp = c1->cost - c2->cost;
    if (cmp == 0)
        cmp = c1->zero_cost - c2->zero_cost;
    return cmp;
}

/**
 * Compare c1 + c2 and cs
 */
_pddl_inline int pddlCostCmpSum(const pddl_cost_t *c1,
                                const pddl_cost_t *c2,
                                const pddl_cost_t *cs)
{
    int cmp = (c1->cost + c2->cost) - cs->cost;
    if (cmp == 0)
        cmp = (c1->zero_cost + c2->zero_cost) - cs->zero_cost;
    return cmp;
}

_pddl_inline pddl_bool_t pddlCostIsDeadEnd(const pddl_cost_t *c)
{
    if (c->cost >= PDDL_COST_DEAD_END)
        return pddl_true;
    return pddl_false;
}

_pddl_inline pddl_bool_t pddlCostIsMax(const pddl_cost_t *c)
{
    return pddlCostCmp(c, &pddl_cost_max) == 0;
}

const char *pddlCostFmt(const pddl_cost_t *c, char *s, size_t s_size);

_pddl_inline int pddlSumSat(int c1, int c2)
{
    if (c1 >= PDDL_COST_MAX || c2 >= PDDL_COST_MAX)
        return PDDL_COST_MAX;
    if (c1 <= PDDL_COST_MIN || c2 <= PDDL_COST_MIN)
        return PDDL_COST_MIN;
    int s = c1 + c2;
    if (s >= PDDL_COST_MAX)
        return PDDL_COST_MAX;
    if (s <= PDDL_COST_MIN)
        return PDDL_COST_MIN;
    return s;
}

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_COST_H__ */
