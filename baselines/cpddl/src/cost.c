/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/cost.h"

pddl_cost_t pddl_cost_zero = { 0, 0 };
pddl_cost_t pddl_cost_max = { PDDL_COST_MAX, PDDL_COST_MAX };
pddl_cost_t pddl_cost_dead_end = { PDDL_COST_DEAD_END, PDDL_COST_DEAD_END };

const char *pddlCostFmt(const pddl_cost_t *c, char *s, size_t s_size)
{
    snprintf(s, s_size, "%d:%d", c->cost, c->zero_cost);
    return s;
}
