/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/strips_fact_cross_ref.h"
#include "internal.h"

void pddlStripsFactCrossRefInit(pddl_strips_fact_cross_ref_t *cref,
                                const pddl_strips_t *strips,
                                pddl_bool_t init,
                                pddl_bool_t goal,
                                pddl_bool_t op_pre,
                                pddl_bool_t op_add,
                                pddl_bool_t op_del)
{
    if (strips->has_cond_eff){
        PANIC("pddlStripsFactCrossRefInit() does not support"
                    " conditional effects!");
    }

    int fact;

    ZEROIZE(cref);

    cref->fact_size = strips->fact.fact_size;
    cref->fact = ZALLOC_ARR(pddl_strips_fact_cross_ref_fact_t,
                            cref->fact_size);

    if (init){
        PDDL_ISET_FOR_EACH(&strips->init, fact)
            cref->fact[fact].is_init = 1;
    }

    if (goal){
        PDDL_ISET_FOR_EACH(&strips->goal, fact)
            cref->fact[fact].is_goal = 1;
    }

    if (op_pre || op_add || op_del){
        for (int op_id = 0; op_id < strips->op.op_size; ++op_id){
            const pddl_strips_op_t *op = strips->op.op[op_id];

            if (op_pre){
                PDDL_ISET_FOR_EACH(&op->pre, fact)
                    pddlISetAdd(&cref->fact[fact].op_pre, op_id);
            }
            if (op_add){
                PDDL_ISET_FOR_EACH(&op->add_eff, fact)
                    pddlISetAdd(&cref->fact[fact].op_add, op_id);
            }
            if (op_del){
                PDDL_ISET_FOR_EACH(&op->del_eff, fact)
                    pddlISetAdd(&cref->fact[fact].op_del, op_id);
            }
        }
    }
}

void pddlStripsFactCrossRefFree(pddl_strips_fact_cross_ref_t *cref)
{
    for (int i = 0; i < cref->fact_size; ++i){
        pddlISetFree(&cref->fact[i].op_pre);
        pddlISetFree(&cref->fact[i].op_add);
        pddlISetFree(&cref->fact[i].op_del);
    }
    if (cref->fact != NULL)
        FREE(cref->fact);
}
