/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/critical_path.h"

int pddlHm(int m,
           const pddl_strips_t *strips,
           pddl_mutex_pairs_t *mutex,
           pddl_iset_t *unreachable_facts,
           pddl_iset_t *unreachable_ops,
           float time_limit,
           size_t excess_memory,
           pddl_err_t *err)
{
    if (m == 1){
        if (time_limit > 0 || excess_memory > 0 || mutex != NULL)
            LOG(err, "h^1 using pddlHm() ignores mutex pairs, time limit"
                       " and memory limit");
        return pddlH1(strips, unreachable_facts, unreachable_ops, err);

    }else if (m == 2){
        if (excess_memory > 0)
            LOG(err, "h^2 using pddlHm() ignores the memory limit");
        return pddlH2(strips, mutex, unreachable_facts, unreachable_ops,
                      time_limit, err);

    }else if (m == 3){
        return pddlH3(strips, mutex, unreachable_facts, unreachable_ops,
                      time_limit, excess_memory, err);

    }else{
        LOG(err, "h^%d not supported!", m);
        return -1;
    }
}
