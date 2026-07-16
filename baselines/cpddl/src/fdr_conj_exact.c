/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/fdr_conj_exact.h"

void pddlFDRConjExactConfigInit(pddl_fdr_conj_exact_config_t *cfg)
{
    ZEROIZE(cfg);
    pddlSetISetInit(&cfg->conj);
}

void pddlFDRConjExactConfigFree(pddl_fdr_conj_exact_config_t *cfg)
{
    pddlSetISetFree(&cfg->conj);
}

void pddlFDRConjExactConfigAddConj(pddl_fdr_conj_exact_config_t *cfg,
                                   const pddl_iset_t *conj)
{
    if (pddlISetSize(conj) > 1)
        pddlSetISetAdd(&cfg->conj, conj);
}

void pddlFDRConjExactConfigAddConjAndSubsets(pddl_fdr_conj_exact_config_t *cfg,
                                             const pddl_iset_t *conj)
{
    if (pddlISetSize(conj) > 1)
        pddlFDRConjExactConfigAddConj(cfg, conj);
    if (pddlISetSize(conj) <= 2)
        return;

    PDDL_ISET(c);
    for (int skipi = 0; skipi < pddlISetSize(conj); ++skipi){
        pddlISetEmpty(&c);
        for (int i = 0; i < pddlISetSize(conj); ++i){
            if (i != skipi)
                pddlISetAdd(&c, pddlISetGet(conj, i));
        }
        pddlFDRConjExactConfigAddConjAndSubsets(cfg, &c);
    }
    pddlISetFree(&c);
}

void pddlFDRConjExactConfigAddConjs(pddl_fdr_conj_exact_config_t *cfg,
                                    const pddl_set_iset_t *conjs)
{
    int size = pddlSetISetSize(conjs);
    for (int i = 0; i < size; ++i)
        pddlFDRConjExactConfigAddConj(cfg, pddlSetISetGet(conjs, i));
}

static void affectedConjs(const pddl_fdr_conj_exact_t *task,
                          const pddl_iset_t *prevars,
                          const pddl_iset_t *effvars,
                          const pddl_iset_t *oppre,
                          const pddl_iset_t *opeff,
                          pddl_iset_t *affected)
{
    pddlISetEmpty(affected);
    for (int ci = 0; ci < task->conj_size; ++ci){
        const pddl_fdr_conjunction_t *c = &task->conj[ci];
        int common_eff_vars = pddlISetIntersectionSize(&c->vars, effvars);
        if (common_eff_vars == 0)
            continue;
        int common_pre_vars = pddlISetIntersectionSize(&c->vars, prevars);
        int common_pre_facts = pddlISetIntersectionSize(&c->fact, oppre);
        int common_eff_facts = pddlISetIntersectionSize(&c->fact, opeff);


        if (common_pre_vars == common_pre_facts
                && common_eff_vars != common_eff_facts){
            pddlISetAdd(affected, ci);

        }else if (common_eff_vars == common_eff_facts){
            pddlISetAdd(affected, ci);
        }
    }
}

static void addOpsRec2(pddl_fdr_conj_exact_t *task,
                       const pddl_fdr_op_t *op_in,
                       const pddl_iset_t *oppre,
                       const pddl_iset_t *opeff,
                       const pddl_iset_t *prevars,
                       const pddl_iset_t *effvars,
                       const pddl_mutex_pairs_t *mutex,
                       const pddl_iset_t *affected_conjs,
                       const int *pre,
                       const pddl_iset_t *add_pre,
                       const pddl_iset_t *add_pre_vars,
                       int add_pre_var,
                       pddl_err_t *err)
{
    if (add_pre_var < pddlISetSize(add_pre_vars)){
        const pddl_fdr_var_t *var;
        var = task->fdr.var.var + pddlISetGet(add_pre_vars, add_pre_var);
        PDDL_ISET(add_pre_next);
        for (int vali = 0; vali < var->val_size; ++vali){
            pddlISetEmpty(&add_pre_next);
            pddlISetUnion(&add_pre_next, add_pre);
            pddlISetAdd(&add_pre_next, var->val[vali].global_id);
            addOpsRec2(task, op_in, oppre, opeff, prevars, effvars,
                       mutex, affected_conjs, pre, &add_pre_next,
                       add_pre_vars, add_pre_var + 1, err);
        }
        pddlISetFree(&add_pre_next);
        return;
    }

    PDDL_ISET(final_pre);
    pddlISetUnion(&final_pre, oppre);
    pddlISetUnion(&final_pre, add_pre);
    for (int i = 0; i < pddlISetSize(affected_conjs); ++i){
        if (pre[i] == 1){
            int conj_id = pddlISetGet(affected_conjs, i);
            pddlISetUnion(&final_pre, &task->conj[conj_id].fact);
        }
    }

    // Filter out actions where negative conjunction is actually true
    // (i.e., we require v_c = 1 in the precondition, but c \subseteq pre
    for (int i = 0; i < pddlISetSize(affected_conjs); ++i){
        if (pre[i] == 0){
            int conj_id = pddlISetGet(affected_conjs, i);
            if (pddlISetIsSubset(&task->conj[conj_id].fact, &final_pre)){
                pddlISetFree(&final_pre);
                return;
            }
        }
    }

    if (!pddlMutexPairsIsMutexSet(mutex, &final_pre)){
        pddl_fdr_op_t *op = pddlFDROpNewEmpty();
        op->name = STRDUP(op_in->name);
        op->cost = op_in->cost;

        int fact;
        PDDL_ISET_FOR_EACH(&final_pre, fact){
            const pddl_fdr_val_t *val = task->fdr.var.global_id_to_val[fact];
            pddlFDRPartStateSet(&op->pre, val->var_id, val->val_id);
        }
        for (int i = 0; i < pddlISetSize(affected_conjs); ++i){
            int conj_id = pddlISetGet(affected_conjs, i);
            int var_id = task->conj[conj_id].var_id;
            pddlFDRPartStateSet(&op->pre, var_id, pre[i]);
        }

        PDDL_ISET(eff);
        pddlISetMinus2(&eff, opeff, &final_pre);
        PDDL_ISET_FOR_EACH(&eff, fact){
            const pddl_fdr_val_t *val = task->fdr.var.global_id_to_val[fact];
            pddlFDRPartStateSet(&op->eff, val->var_id, val->val_id);
        }

        PDDL_ISET(effvars);
        PDDL_ISET_FOR_EACH(&eff, fact){
            const pddl_fdr_val_t *val = task->fdr.var.global_id_to_val[fact];
            pddlISetAdd(&effvars, val->var_id);
        }

        PDDL_ISET(app);
        PDDL_ISET_FOR_EACH(&final_pre, fact){
            const pddl_fdr_val_t *val = task->fdr.var.global_id_to_val[fact];
            if (!pddlISetIn(val->var_id, &effvars))
                pddlISetAdd(&app, fact);
        }
        pddlISetUnion(&app, &eff);
        pddlISetFree(&effvars);

        for (int i = 0; i < pddlISetSize(affected_conjs); ++i){
            int conj_id = pddlISetGet(affected_conjs, i);
            int var_id = task->conj[conj_id].var_id;
            if (pre[i] == 0){
                if (pddlISetIsSubset(&task->conj[conj_id].fact, &app))
                    pddlFDRPartStateSet(&op->eff, var_id, 1);

            }else{ // pre[i] == 1
                PDDL_ISET(test);
                pddlISetUnion2(&test, &task->conj[conj_id].fact, &app);
                if (pddlMutexPairsIsMutexSet(mutex, &test))
                    pddlFDRPartStateSet(&op->eff, var_id, 0);
                pddlISetFree(&test);
            }
        }

        pddlISetFree(&app);
        pddlISetFree(&eff);

        /*
        fprintf(stderr, "add op: %s\n", op->name);
        fprintf(stderr, "pre:");
        for (int i = 0; i < op->pre.fact_size; ++i){
            fprintf(stderr, " %d:%d", op->pre.fact[i].var, op->pre.fact[i].val);
        }
        fprintf(stderr, "\n");
        fprintf(stderr, "eff:");
        for (int i = 0; i < op->eff.fact_size; ++i){
            fprintf(stderr, " %d:%d", op->eff.fact[i].var, op->eff.fact[i].val);
        }
        fprintf(stderr, "\n");
        */
        pddlFDROpsAddSteal(&task->fdr.op, op);
    }
    pddlISetFree(&final_pre);
}

static void addOpsRec(pddl_fdr_conj_exact_t *task,
                      const pddl_fdr_op_t *op_in,
                      const pddl_iset_t *oppre,
                      const pddl_iset_t *opeff,
                      const pddl_iset_t *prevars,
                      const pddl_iset_t *effvars,
                      const pddl_mutex_pairs_t *mutex,
                      const pddl_iset_t *affected_conjs,
                      const int *pre,
                      int pre_size,
                      int next_pre_idx,
                      pddl_err_t *err)
{
    /*
    fprintf(stderr, "pre:");
    for (int i = 0; i < pre_size; ++i)
        fprintf(stderr, " %d", pre[i]);
    fprintf(stderr, "\n");
    fprintf(stderr, "next_pre_idx: %d / %d\n", next_pre_idx, pre_size);
    */
    ASSERT(pddlISetSize(affected_conjs) == pre_size);
    for (; next_pre_idx < pre_size && pre[next_pre_idx] >= 0; ++next_pre_idx);
    if (next_pre_idx < pre_size){
        int prenext[pre_size];
        int ok = 1;
        memcpy(prenext, pre, sizeof(int) * pre_size);
        prenext[next_pre_idx] = 0;

        // Enforce assignments implied by the one just made, i.e., if a
        // conjunction C is false, then all its supersets must be false
        // too.
        int conj_id = pddlISetGet(affected_conjs, next_pre_idx);
        int other_conj_id;
        PDDL_ISET_FOR_EACH(&task->conj[conj_id].subset_of, other_conj_id){
            for (int idx = 0; idx < pre_size; ++idx){
                if (pddlISetGet(affected_conjs, idx) == other_conj_id){
                    if (prenext[idx] == 1){
                        ok = 0;
                    }else{
                        prenext[idx] = 0;
                    }
                    break;
                }
            }
        }

        if (ok){
            addOpsRec(task, op_in, oppre, opeff, prevars, effvars,
                      mutex, affected_conjs,
                      prenext, pre_size, next_pre_idx + 1, err);
        }


        memcpy(prenext, pre, sizeof(int) * pre_size);
        prenext[next_pre_idx] = 1;
        ok = 1;

        // Enforce assignments implied by the one just made, i.e., if a
        // conjunction C is true, then all its subsets must be true too.
        conj_id = pddlISetGet(affected_conjs, next_pre_idx);
        PDDL_ISET_FOR_EACH(&task->conj[conj_id].superset_of, other_conj_id){
            for (int idx = 0; idx < pre_size; ++idx){
                if (pddlISetGet(affected_conjs, idx) == other_conj_id){
                    if (prenext[idx] == 0){
                        ok = 0;
                    }else{
                        prenext[idx] = 1;
                    }
                    break;
                }
            }
        }

        if (ok){
            addOpsRec(task, op_in, oppre, opeff, prevars, effvars,
                      mutex, affected_conjs,
                      prenext, pre_size, next_pre_idx + 1, err);
        }
        return;
    }

    // Variables from conjunctions that are not part of operator's
    // preconditions or effects
    PDDL_ISET(remain_vars);
    for (int i = 0; i < pre_size; ++i){
        if (pre[i] == 1)
            continue;
        int conj_id = pddlISetGet(affected_conjs, i);
        pddlISetUnion(&remain_vars, &task->conj[conj_id].vars);
    }
    pddlISetMinus(&remain_vars, prevars);
    pddlISetMinus(&remain_vars, effvars);

    PDDL_ISET(empty_set);
    addOpsRec2(task, op_in, oppre, opeff, prevars, effvars,
               mutex, affected_conjs, pre, &empty_set, &remain_vars, 0, err);
    pddlISetFree(&empty_set);
    pddlISetFree(&remain_vars);
}

static void addOps(pddl_fdr_conj_exact_t *task,
                   const pddl_fdr_op_t *op,
                   const pddl_mutex_pairs_t *mutex,
                   pddl_err_t *err)
{
    //fprintf(stderr, "ADD OPS %s\n", op->name);
    // Operator's variables
    PDDL_ISET(effvars);
    for (int i = 0; i < op->eff.fact_size; ++i)
        pddlISetAdd(&effvars, op->eff.fact[i].var);
    PDDL_ISET(prevars);
    for (int i = 0; i < op->pre.fact_size; ++i)
        pddlISetAdd(&prevars, op->pre.fact[i].var);

    // Operator's preconditions and effects as a set of facts
    PDDL_ISET(opeff);
    pddlFDRPartStateToGlobalIDs(&op->eff, &task->fdr.var, &opeff);
    PDDL_ISET(oppre);
    pddlFDRPartStateToGlobalIDs(&op->pre, &task->fdr.var, &oppre);

    // Determine affected conjunctions
    PDDL_ISET(conjs_affected);
    affectedConjs(task, &prevars, &effvars, &oppre, &opeff, &conjs_affected);

    if (pddlISetSize(&conjs_affected) == 0){
        pddl_fdr_op_t *cop = pddlFDROpClone(op);
        pddlFDROpsAddSteal(&task->fdr.op, cop);
        pddlISetFree(&conjs_affected);
        pddlISetFree(&effvars);
        pddlISetFree(&prevars);
        pddlISetFree(&opeff);
        pddlISetFree(&oppre);
        return;
    }


    // Assignment to conjunction's variables
    int pre_size = pddlISetSize(&conjs_affected);
    int pre[pre_size];
    for (int i = 0; i < pre_size; ++i)
        pre[i] = -1;

    // Always true in pre
    for (int i = 0; i < pre_size; ++i){
        int conj_id = pddlISetGet(&conjs_affected, i);
        if (pddlISetIsSubset(&task->conj[conj_id].fact, &oppre))
            pre[i] = 1;
    }

    // Always false in pre
    for (int i = 0; i < pre_size; ++i){
        int conj_id = pddlISetGet(&conjs_affected, i);
        const pddl_fdr_conjunction_t *conj = &task->conj[conj_id];
        int vars_in_common = pddlISetIntersectionSize(&conj->vars, &prevars);
        int facts_in_common = pddlISetIntersectionSize(&conj->fact, &oppre);
        if (vars_in_common > facts_in_common){
            ASSERT(pre[i] < 0);
            pre[i] = 0;
        }
    }

    // Add operators recursively
    addOpsRec(task, op, &oppre, &opeff, &prevars, &effvars,
              mutex, &conjs_affected, pre, pre_size, 0, err);

    pddlISetFree(&opeff);
    pddlISetFree(&oppre);
    pddlISetFree(&conjs_affected);
    pddlISetFree(&effvars);
    pddlISetFree(&prevars);
}

void pddlFDRConjExactInit(pddl_fdr_conj_exact_t *task,
                          const pddl_fdr_t *in_task,
                          const pddl_fdr_conj_exact_config_t *cfg,
                          pddl_err_t *err)
{
    CTX(err, "FDR-Conj-Exact");
    PANIC_IF(in_task->has_cond_eff, "Conditional effects are not supported yet.");

    CTX_NO_TIME(err, "Input FDR");
    pddlFDRLogInfo(in_task, err);
    CTXEND(err);

    ZEROIZE(task);
    pddlFDRInitCopy(&task->fdr, in_task);

    // Create meta-variable v_c for every conjunction c
    task->conj_size = pddlSetISetSize(&cfg->conj);
    task->conj = ZALLOC_ARR(pddl_fdr_conjunction_t, task->conj_size);
    for (int i = 0; i < pddlSetISetSize(&cfg->conj); ++i){
        pddl_fdr_var_t *var = pddlFDRVarsAdd(&task->fdr.var, 2);
        var->val[0].is_conjunction = pddl_true;
        var->val[1].is_conjunction = pddl_true;

        const pddl_iset_t *c = pddlSetISetGet(&cfg->conj, i);
        PANIC_IF(pddlMutexPairsIsMutexSet(cfg->mutex, c),
                 "The input conjunctions must not be mutex.");
        ASSERT(pddlISetSize(c) > 0);
        char name[1024];
        ssize_t end = snprintf(name, 1024, "NOT");
        for (int ni = 0; ni < pddlISetSize(c) && end < 1024; ++ni){
            end += snprintf(name + end, 1024 - end, "-%d:%d:%d:%s",
                            task->fdr.var.global_id_to_val[pddlISetGet(c, ni)]->var_id,
                            task->fdr.var.global_id_to_val[pddlISetGet(c, ni)]->val_id,
                            pddlISetGet(c, ni),
                            task->fdr.var.global_id_to_val[pddlISetGet(c, ni)]->name);
        }
        ASSERT(strlen(name) > 4);
        var->val[0].name = STRDUP(name);
        var->val[1].name = STRDUP(name + 4);

        pddlISetUnion(&task->conj[i].fact, pddlSetISetGet(&cfg->conj, i));
        pddlFDRPartStateInit(&task->conj[i].part_state);
        int fact;
        PDDL_ISET_FOR_EACH(&task->conj[i].fact, fact){
            pddl_fdr_val_t *val = task->fdr.var.global_id_to_val[fact];
            pddlFDRPartStateSet(&task->conj[i].part_state, val->var_id, val->val_id);
            pddlISetAdd(&task->conj[i].vars, val->var_id);
        }
        task->conj[i].var_id = var->var_id;

        for (int j = 0; j < pddlSetISetSize(&cfg->conj); ++j){
            if (i == j)
                continue;
            const pddl_iset_t *set = pddlSetISetGet(&cfg->conj, j);
            if (pddlISetIsSubset(&task->conj[i].fact, set)){
                pddlISetAdd(&task->conj[i].subset_of, j);
            }else if (pddlISetIsSubset(set, &task->conj[i].fact)){
                pddlISetAdd(&task->conj[i].superset_of, j);
            }
        }
    }

    // Set init
    FREE(task->fdr.init);
    task->fdr.init = ALLOC_ARR(int, task->fdr.var.var_size);
    memcpy(task->fdr.init, in_task->init, sizeof(int) * in_task->var.var_size);
    for (int ci = 0; ci < task->conj_size; ++ci){
        if (pddlFDRPartStateIsConsistentWithState(&task->conj[ci].part_state,
                                                  in_task->init)){
            task->fdr.init[task->conj[ci].var_id] = 1;
        }else{
            task->fdr.init[task->conj[ci].var_id] = 0;
        }
    }

    // Set goal
    for (int ci = 0; ci < task->conj_size; ++ci){
        if (pddlFDRPartStateIsConsistentWithPartState(&task->conj[ci].part_state,
                                                      &in_task->goal)){
            pddlFDRPartStateSet(&task->fdr.goal, task->conj[ci].var_id, 1);
        }
    }

    // Add operators
    pddlFDROpsFree(&task->fdr.op);
    pddlFDROpsInit(&task->fdr.op);
    for (int opi = 0; opi < in_task->op.op_size; ++opi)
        addOps(task, in_task->op.op[opi], cfg->mutex, err);


    pddlFDRLogInfo(&task->fdr, err);
    CTXEND(err);
}

void pddlFDRConjExactFree(pddl_fdr_conj_exact_t *task)
{
    for (int ci = 0; ci < task->conj_size; ++ci){
        pddl_fdr_conjunction_t *c = task->conj + ci;
        pddlISetFree(&c->fact);
        pddlFDRPartStateFree(&c->part_state);
        pddlISetFree(&c->superset_of);
        pddlISetFree(&c->subset_of);
        pddlISetFree(&c->vars);
    }
    if (task->conj != NULL)
        FREE(task->conj);
    pddlFDRFree(&task->fdr);
}


void pddlFDRConjExactMutexPairsInitCopy(pddl_mutex_pairs_t *mutex,
                                        const pddl_mutex_pairs_t *in_mutex,
                                        const pddl_fdr_conj_exact_t *task)
{
    pddlMutexPairsInit(mutex, task->fdr.var.global_id_size);
    PDDL_MUTEX_PAIRS_FOR_EACH(in_mutex, f1, f2){
        pddlMutexPairsAdd(mutex, f1, f2);
        if (pddlMutexPairsIsFwMutex(in_mutex, f1, f2))
            pddlMutexPairsSetFwMutex(mutex, f1, f2);
        if (pddlMutexPairsIsBwMutex(in_mutex, f1, f2))
            pddlMutexPairsSetBwMutex(mutex, f1, f2);
    }

    for (int ci = 0; ci < task->conj_size; ++ci){
        const pddl_fdr_conjunction_t *conj = task->conj + ci;
        int pos_val_id = task->fdr.var.var[conj->var_id].val[1].global_id;
        int neg_val_id = task->fdr.var.var[conj->var_id].val[0].global_id;
        int fact_id;
        PDDL_ISET_FOR_EACH(&conj->fact, fact_id){
            for (int fi2 = 0; fi2 < in_mutex->fact_size; ++fi2){
                // If fi2 is a mutex with any of the fact from conj, then
                // it is also mutex with conj.
                if (pddlMutexPairsIsMutex(in_mutex, fact_id, fi2)){
                    pddlMutexPairsAdd(mutex, pos_val_id, fi2);
                    if (pddlMutexPairsIsFwMutex(in_mutex, fact_id, fi2))
                        pddlMutexPairsSetFwMutex(mutex, pos_val_id, fi2);
                    if (pddlMutexPairsIsBwMutex(in_mutex, fact_id, fi2))
                        pddlMutexPairsSetBwMutex(mutex, pos_val_id, fi2);
                }
            }
        }

        pddlMutexPairsAdd(mutex, pos_val_id, neg_val_id);
        pddlMutexPairsSetFwMutex(mutex, pos_val_id, neg_val_id);
        pddlMutexPairsSetBwMutex(mutex, pos_val_id, neg_val_id);
    }
}
