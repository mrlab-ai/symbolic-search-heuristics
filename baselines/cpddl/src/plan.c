/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/plan.h"
#include "internal.h"

void pddlPlanInit(pddl_plan_t *plan)
{
    ZEROIZE(plan);
}

void pddlPlanFree(pddl_plan_t *plan)
{
    if (plan->state != NULL)
        FREE(plan->state);
    pddlIArrFree(&plan->op);
}

void pddlPlanCopy(pddl_plan_t *dst, const pddl_plan_t *src)
{
    ZEROIZE(dst);
    *dst = *src;
    dst->state = ALLOC_ARR(pddl_state_id_t, dst->state_alloc);
    memcpy(dst->state, src->state, sizeof(pddl_state_id_t) * dst->state_size);

    int op;
    PDDL_IARR_FOR_EACH(&src->op, op)
        pddlIArrAdd(&dst->op, op);
}

static void addState(pddl_plan_t *plan, pddl_state_id_t state_id)
{
    if (plan->state_size == plan->state_alloc){
        if (plan->state_alloc == 0)
            plan->state_alloc = 64;
        plan->state_alloc *= 2;
        plan->state = REALLOC_ARR(plan->state,
                                  pddl_state_id_t, plan->state_alloc);
    }

    plan->state[plan->state_size++] = state_id;
}

static void loadReversedStates(pddl_plan_t *plan,
                               pddl_state_id_t goal_state_id,
                               const pddl_fdr_state_space_t *state_space)
{
    pddl_fdr_state_space_node_t node;

    pddlFDRStateSpaceNodeInit(&node, state_space);
    pddlFDRStateSpaceGetNoState(state_space, goal_state_id, &node);

    plan->state_size = 0;
    while (1){
        addState(plan, node.id);
        if (node.parent_id != PDDL_NO_STATE_ID){
            pddlFDRStateSpaceGetNoState(state_space, node.parent_id, &node);
        }else{
            break;
        }
    }

    pddlFDRStateSpaceNodeFree(&node);
}

static void reverseStates(pddl_plan_t *plan)
{
    int size2 = plan->state_size / 2;
    for (int i = 0; i < size2; ++i){
        pddl_state_id_t tmp = plan->state[i];
        plan->state[i] = plan->state[plan->state_size - i - 1];
        plan->state[plan->state_size - i - 1] = tmp;
    }
}

void pddlPlanLoadBacktrack(pddl_plan_t *plan,
                           pddl_state_id_t goal_state_id,
                           const pddl_fdr_state_space_t *state_space)
{
    loadReversedStates(plan, goal_state_id, state_space);
    reverseStates(plan);

    pddlIArrEmpty(&plan->op);
    plan->length = 0;
    plan->cost = 0;
    if (plan->state_size == 0)
        return;

    pddl_fdr_state_space_node_t node;
    pddlFDRStateSpaceNodeInit(&node, state_space);

    for (int i = 1; i < plan->state_size; ++i){
        pddlFDRStateSpaceGetNoState(state_space, plan->state[i], &node);
        pddlIArrAdd(&plan->op, node.op_id);
    }
    plan->cost = node.g_value;
    plan->length = pddlIArrSize(&plan->op);

    pddlFDRStateSpaceNodeFree(&node);
}

void pddlPlanUpdateAuxiliaryOps(pddl_plan_t *plan, const pddl_fdr_t *fdr)
{
    if (plan->state != NULL)
        FREE(plan->state);
    plan->state_size = 0;
    plan->state_alloc = 0;
    plan->state = NULL;

    pddl_iarr_t ops = plan->op;
    int size = pddlIArrSize(&ops);

    plan->cost = 0;
    plan->length = 0;
    pddlIArrInit(&plan->op);
    for (int i = 0; i < size; ++i){
        int op_id = pddlIArrGet(&ops, i);
        const pddl_fdr_op_t *op = fdr->op.op[op_id];
        if (!op->is_aux_remove_from_plan){
            pddlIArrAdd(&plan->op, op_id);
            ++plan->length;
            plan->cost += op->cost;
        }
    }
    pddlIArrFree(&ops);
}

void pddlPlanPrint(const pddl_plan_t *plan,
                   const pddl_fdr_ops_t *ops,
                   FILE *fout)
{
    fprintf(fout, ";; Cost: %ld\n", (long)plan->cost);
    fprintf(fout, ";; Length: %ld\n", (long)plan->length);
    int op_id;
    PDDL_IARR_FOR_EACH(&plan->op, op_id){
        const pddl_fdr_op_t *op = ops->op[op_id];
        fprintf(fout, "(%s) ;; cost: %ld\n", op->name, (long)op->cost);
    }
}
