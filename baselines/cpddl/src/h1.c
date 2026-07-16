/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/iarr.h"
#include "pddl/critical_path.h"
#include "pddl/strips.h"

int pddlH1(const pddl_strips_t *strips,
           pddl_iset_t *unreachable_facts,
           pddl_iset_t *unreachable_ops,
           pddl_err_t *err)
{
    if (strips->has_cond_eff){
        PDDL_ERR_RET(err, -1, "pddlH1: Conditional effects are not supported!");
    }

    CTX(err, "h^1");
    int *facts = ZALLOC_ARR(int, strips->fact.fact_size);
    int *ops = ZALLOC_ARR(int, strips->op.op_size);
    pddl_iset_t *fact_to_op = ZALLOC_ARR(pddl_iset_t, strips->fact.fact_size);
    PDDL_IARR(queue);

    LOG(err, "facts: %d, ops: %d",
              strips->fact.fact_size,
              strips->op.op_size);

    int fact;
    PDDL_ISET_FOR_EACH(&strips->init, fact){
        facts[fact] = 1;
        pddlIArrAdd(&queue, fact);
    }

    for (int op_id = 0; op_id < strips->op.op_size; ++op_id){
        const pddl_strips_op_t *op = strips->op.op[op_id];
        ops[op_id] = pddlISetSize(&op->pre);
        int fact;
        PDDL_ISET_FOR_EACH(&op->pre, fact)
            pddlISetAdd(fact_to_op + fact, op_id);
        if (ops[op_id] == 0){
            int fact;
            PDDL_ISET_FOR_EACH(&op->add_eff, fact){
                if (facts[fact] == 0){
                    facts[fact] = 1;
                    pddlIArrAdd(&queue, fact);
                }
            }
        }
    }

    while (pddlIArrSize(&queue) > 0){
        int cur = pddlIArrGet(&queue, pddlIArrSize(&queue) - 1);
        pddlIArrRmLast(&queue);
        int op_id;
        PDDL_ISET_FOR_EACH(fact_to_op + cur, op_id){
            if (--ops[op_id] == 0){
                const pddl_strips_op_t *op = strips->op.op[op_id];
                int fact;
                PDDL_ISET_FOR_EACH(&op->add_eff, fact){
                    if (facts[fact] == 0){
                        facts[fact] = 1;
                        pddlIArrAdd(&queue, fact);
                    }
                }
            }
        }
    }

    for (int fid = 0;
            unreachable_facts != NULL && fid < strips->fact.fact_size; ++fid){
        if (facts[fid] == 0)
            pddlISetAdd(unreachable_facts, fid);
    }
    for (int op_id = 0;
            unreachable_ops != NULL && op_id < strips->op.op_size; ++op_id){
        if (ops[op_id] > 0)
            pddlISetAdd(unreachable_ops, op_id);
    }

    pddlIArrFree(&queue);
    for (int fid = 0; fid < strips->fact.fact_size; ++fid)
        pddlISetFree(fact_to_op + fid);
    if (fact_to_op != NULL)
        FREE(fact_to_op);
    if (facts != NULL)
        FREE(facts);
    if (ops != NULL)
        FREE(ops);

    LOG(err, "DONE. unreachable facts: %d, unreachable ops: %d",
              (unreachable_facts != NULL ? pddlISetSize(unreachable_facts) : -1),
              (unreachable_ops != NULL ? pddlISetSize(unreachable_ops) : -1));
    CTXEND(err);
    return 0;
}

