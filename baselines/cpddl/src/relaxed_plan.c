/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/relaxed_plan.h"
#include "internal.h"

void pddlRelaxedPlanCountConflictsStrips(const pddl_iarr_t *plan,
                                         const pddl_iset_t *init,
                                         const pddl_iset_t *goal,
                                         const pddl_strips_ops_t *ops,
                                         int goal_conflict_weight,
                                         int *fact_conflicts)
{
    PDDL_ISET(conflict);
    PDDL_ISET(state);
    pddlISetUnion(&state, init);
    int op_id;
    PDDL_IARR_FOR_EACH(plan, op_id){
        const pddl_strips_op_t *op = ops->op[op_id];
        // TODO: Conditional effects not supported yet
        PANIC_IF(op->cond_eff_size != 0,
                 "Conditional effects are not supported yet.");
        pddlISetMinus2(&conflict, &op->pre, &state);
        int fact_id;
        PDDL_ISET_FOR_EACH(&conflict, fact_id)
            fact_conflicts[fact_id] += 1;
        pddlISetMinus(&state, &op->del_eff);
        pddlISetUnion(&state, &op->add_eff);
    }

    pddlISetMinus2(&conflict, goal, &state);
    int fact_id;
    PDDL_ISET_FOR_EACH(&conflict, fact_id)
        fact_conflicts[fact_id] += 1 * goal_conflict_weight;

    pddlISetFree(&state);
    pddlISetFree(&conflict);
}
