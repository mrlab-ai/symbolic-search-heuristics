/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/hfunc.h"
#include "pddl/strips_maker.h"
#include "internal.h"

static pddl_htable_key_t actionComputeHash(const pddl_ground_action_args_t *ga,
                                           int arg_size)
{
    uint64_t hash;
    hash = pddlCityHash_64(&ga->action_id, sizeof(ga->action_id));
    hash += pddlCityHash_64(&ga->action_id, sizeof(ga->action_id2));
    hash += pddlCityHash_64(ga->arg, sizeof(int) * arg_size);
    return hash;
}

static pddl_htable_key_t htActionHash(const pddl_list_t *key, void *_)
{
    const pddl_ground_action_args_t *ga;
    ga = PDDL_LIST_ENTRY(key, pddl_ground_action_args_t, htable);
    return ga->hash;
}

static int actionCmp(const pddl_ground_action_args_t *ga1,
                     const pddl_ground_action_args_t *ga2,
                     int arg_size)
{
    int cmp = ga1->action_id - ga2->action_id;
    if (cmp == 0)
        cmp = ga1->action_id2 - ga2->action_id2;
    for (int i = 0; i < arg_size && cmp == 0; ++i)
        cmp = ga1->arg[i] - ga2->arg[i];
    return cmp;
}

static int htActionEq(const pddl_list_t *k1, const pddl_list_t *k2, void *ud)
{
    const int *arg_size = ud;
    const pddl_ground_action_args_t *ga1;
    ga1 = PDDL_LIST_ENTRY(k1, pddl_ground_action_args_t, htable);
    const pddl_ground_action_args_t *ga2;
    ga2 = PDDL_LIST_ENTRY(k2, pddl_ground_action_args_t, htable);
    return actionCmp(ga1, ga2, arg_size[ga1->action_id]) == 0;
}

void pddlStripsMakerInit(pddl_strips_maker_t *sm, const pddl_t *pddl)
{
    ZEROIZE(sm);
    sm->action_size = pddl->action.action_size;
    sm->action_arg_size = ZALLOC_ARR(int, sm->action_size);
    for (int ai = 0; ai < sm->action_size; ++ai)
        sm->action_arg_size[ai] = pddl->action.action[ai].param.param_size;

    pddlGroundAtomsInit(&sm->ground_atom);
    pddlGroundAtomsInit(&sm->ground_atom_static);
    pddlGroundAtomsInit(&sm->ground_func);

    sm->action_args = pddlHTableNew(htActionHash, htActionEq,
                                    sm->action_arg_size);
    pddl_ground_action_args_t *pa = NULL;
    sm->action_args_arr = pddlExtArrNew(sizeof(pa), NULL, &pa);
    sm->eq_pred = pddl->pred.eq_pred;
    sm->func_total_cost_id = pddl->func.total_cost_func;
}

void pddlStripsMakerFree(pddl_strips_maker_t *sm)
{
    if (sm->action_arg_size != NULL)
        FREE(sm->action_arg_size);

    for (int i = 0; i < sm->num_action_args; ++i){
        pddl_ground_action_args_t **ppa;
        ppa = pddlExtArrGet(sm->action_args_arr, i);
        pddl_ground_action_args_t *ga = *ppa;
        pddlListDel(&ga->htable);
        FREE(ga);
    }

    pddlHTableDel(sm->action_args);
    pddlExtArrDel(sm->action_args_arr);
    pddlGroundAtomsFree(&sm->ground_atom);
    pddlGroundAtomsFree(&sm->ground_atom_static);
    pddlGroundAtomsFree(&sm->ground_func);
}

static pddl_ground_atom_t *addAtom(pddl_strips_maker_t *sm,
                                   pddl_ground_atoms_t *gas,
                                   const pddl_fm_atom_t *atom,
                                   const int *args,
                                   int *is_new)
{
    if (is_new != NULL)
        *is_new = 0;
    int atom_size = gas->atom_size;
    pddl_ground_atom_t *gatom = pddlGroundAtomsAddAtom(gas, atom, args);
    if (atom_size != gas->atom_size && is_new != NULL)
        *is_new = 1;
    return gatom;
}

static pddl_ground_atom_t *addAtomPred(pddl_strips_maker_t *sm,
                                       pddl_ground_atoms_t *gas,
                                       int pred,
                                       const int *args,
                                       int arg_size,
                                       int *is_new)
{
    if (is_new != NULL)
        *is_new = 0;
    int atom_size = gas->atom_size;
    pddl_ground_atom_t *gatom;
    gatom = pddlGroundAtomsAddPred(gas, pred, args, arg_size);
    if (atom_size != gas->atom_size && is_new != NULL)
        *is_new = 1;
    return gatom;
}

pddl_ground_atom_t *pddlStripsMakerAddAtom(pddl_strips_maker_t *sm,
                                           const pddl_fm_atom_t *atom,
                                           const int *args,
                                           int *is_new)
{
    return addAtom(sm, &sm->ground_atom, atom, args, is_new);
}

pddl_ground_atom_t *pddlStripsMakerAddAtomPred(pddl_strips_maker_t *sm,
                                               int pred,
                                               const int *args,
                                               int args_size,
                                               int *is_new)
{
    return addAtomPred(sm, &sm->ground_atom, pred, args, args_size, is_new);
}

pddl_ground_atom_t *pddlStripsMakerAddStaticAtom(pddl_strips_maker_t *sm,
                                                 const pddl_fm_atom_t *atom,
                                                 const int *args,
                                                 int *is_new)
{
    return addAtom(sm, &sm->ground_atom_static, atom, args, is_new);
}

pddl_ground_atom_t *pddlStripsMakerAddStaticAtomPred(pddl_strips_maker_t *sm,
                                                     int pred,
                                                     const int *args,
                                                     int args_size,
                                                     int *is_new)
{
    return addAtomPred(sm, &sm->ground_atom_static,
                       pred, args, args_size, is_new);
}

pddl_ground_atom_t *pddlStripsMakerAddFuncInt(pddl_strips_maker_t *sm,
                                              const pddl_fm_atom_t *atom,
                                              const int *args,
                                              int value,
                                              int *is_new)
{
    ASSERT(atom != NULL);
    PANIC_IF(value < 0, "Only non-negative function values are allowed.");

    if (is_new != NULL)
        *is_new = 0;
    int atom_size = sm->ground_func.atom_size;
    pddl_ground_atom_t *gatom;
    gatom = pddlGroundAtomsAddAtom(&sm->ground_func, atom, args);
    gatom->func_val = value;
    if (atom_size != sm->ground_func.atom_size && is_new != NULL)
        *is_new = 1;
    return gatom;
}


pddl_ground_action_args_t *pddlStripsMakerAddAction(pddl_strips_maker_t *sm,
                                                    int action_id,
                                                    int action_id2,
                                                    const int *args,
                                                    int *is_new)
{
    if (is_new != NULL)
        *is_new = 0;
    int arg_size = sm->action_arg_size[action_id];
    size_t size = sizeof(pddl_ground_action_args_t);
    size += sizeof(int) * arg_size;
    pddl_ground_action_args_t *ga = MALLOC(size);
    ga->action_id = action_id;
    ga->action_id2 = action_id2;
    memcpy(ga->arg, args, sizeof(int) * arg_size);
    ga->hash = actionComputeHash(ga, arg_size);
    ga->id = -1;
    pddlListInit(&ga->htable);

    pddl_list_t *ins = pddlHTableInsertUnique(sm->action_args, &ga->htable);
    if (ins == NULL){
        ga->id = sm->num_action_args++;
        if (is_new != NULL)
            *is_new = 1;

        pddl_ground_action_args_t **pa;
        pa = pddlExtArrGet(sm->action_args_arr, ga->id);
        *pa = ga;
        return ga;
    }

    FREE(ga);
    ga = PDDL_LIST_ENTRY(ins, pddl_ground_action_args_t, htable);
    return ga;
}

pddl_ground_action_args_t *pddlStripsMakerFindAction(pddl_strips_maker_t *sm,
                                                     int action_id,
                                                     int action_id2,
                                                     const int *args)
{
    ASSERT(action_id < sm->action_size);
    int arg_size = sm->action_arg_size[action_id];
    size_t size = sizeof(pddl_ground_action_args_t);
    size += sizeof(int) * arg_size;
    pddl_ground_action_args_t *ga = alloca(size);
    ga->action_id = action_id;
    ga->action_id2 = action_id2;
    memcpy(ga->arg, args, sizeof(int) * arg_size);
    ga->hash = actionComputeHash(ga, arg_size);
    ga->id = -1;
    pddlListInit(&ga->htable);

    pddl_list_t *found = pddlHTableFind(sm->action_args, &ga->htable);
    if (found == NULL)
        return NULL;
    return PDDL_LIST_ENTRY(found, pddl_ground_action_args_t, htable);
}

int pddlStripsMakerAddInit(pddl_strips_maker_t *sm, const pddl_t *pddl)
{
    return pddlStripsMakerAddInitAndCollect(sm, pddl, NULL, NULL);
}

int pddlStripsMakerAddInitAndCollect(pddl_strips_maker_t *sm,
                                     const pddl_t *pddl,
                                     pddl_iset_t *added_facts,
                                     pddl_iset_t *added_static_facts)
{
    pddl_list_t *item;
    PDDL_LIST_FOR_EACH(&pddl->init->part, item){
        const pddl_fm_t *c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);

        const pddl_fm_atom_t *fluent;
        int ivalue;
        if (pddlFmIsAtom(c)){
            const pddl_fm_atom_t *a = pddlFmToAtomConst(c);
            const pddl_ground_atom_t *ga;
            if (pddlPredIsStatic(&pddl->pred.pred[a->pred])){
                ga = pddlStripsMakerAddStaticAtom(sm, a, NULL, NULL);
                if (added_static_facts != NULL)
                    pddlISetAdd(added_static_facts, ga->id);
            }else{
                ga = pddlStripsMakerAddAtom(sm, a, NULL, NULL);
                if (added_facts != NULL)
                    pddlISetAdd(added_facts, ga->id);
            }

        }else if (pddlFmNumCmpCheckSimpleGroundEqNonNegInt(c, &fluent, &ivalue) == 0){
            pddlStripsMakerAddFuncInt(sm, fluent, NULL, ivalue, NULL);

        }else{
            PANIC("Unsupported element in the initial state: %s",
                  F_FM_PDDL(c, pddl, NULL));
        }
    }
    return 0;
}

static int createStripsFacts(pddl_strips_maker_t *sm,
                             pddl_strips_t *strips,
                             const pddl_t *pddl,
                             const pddl_ground_config_t *cfg,
                             int **map_ground_atom_to_fact_id,
                             pddl_err_t *err)
{
    const pddl_ground_atom_t *ga;
    int fact_id;

    for (int i = 0; i < sm->ground_atom.atom_size; ++i){
        ga = sm->ground_atom.atom[i];
        ASSERT(ga->id == i);
        fact_id = pddlFactsAddGroundAtom(&strips->fact, ga, pddl);
        if (fact_id != ga->id){
            PANIC("The fact and the corresponding grounded atom have"
                        " different IDs. This is definitelly a bug!");
        }
    }

    if (cfg->keep_all_static_facts){
        for (int i = 0; i < sm->ground_atom_static.atom_size; ++i){
            ga = sm->ground_atom_static.atom[i];
            pddlFactsAddGroundAtom(&strips->fact, ga, pddl);
        }
    }

    int *ground_atom_to_fact_id = ALLOC_ARR(int, strips->fact.fact_size);
    pddlFactsSort(&strips->fact, ground_atom_to_fact_id);
#ifdef PDDL_DEBUG
    for (int i = 0; i < sm->ground_atom.atom_size; ++i){
        ga = sm->ground_atom.atom[i];
        ASSERT(ga->id == i);
        fact_id = pddlFactsAddGroundAtom(&strips->fact, ga, pddl);
        ASSERT(fact_id == ground_atom_to_fact_id[ga->id]);
    }
#endif
    *map_ground_atom_to_fact_id = ground_atom_to_fact_id;

    LOG(err, "Created %d STRIPS facts", strips->fact.fact_size);
    return 0;
}

static int createInitState(pddl_strips_maker_t *sm,
                           pddl_strips_t *strips,
                           const pddl_t *pddl,
                           const pddl_ground_config_t *cfg,
                           const int *ground_atom_to_fact_id,
                           pddl_err_t *err)
{
    pddl_list_t *item;
    const pddl_fm_t *c;
    const pddl_fm_atom_t *a;
    const pddl_ground_atom_t *ga;

    PDDL_LIST_FOR_EACH(&pddl->init->part, item){
        c = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        if (pddlFmIsAtom(c)){
            a = pddlFmToAtomConst(c);
            ga = pddlGroundAtomsFindAtom(&sm->ground_atom, a, NULL);
            if (ga != NULL){
                pddlISetAdd(&strips->init, ground_atom_to_fact_id[ga->id]);
            }else if (cfg->keep_all_static_facts){
                ga = pddlGroundAtomsFindAtom(&sm->ground_atom_static, a, NULL);
                if (ga != NULL){
                    int id = ga->id + sm->ground_atom.atom_size;
                    pddlISetAdd(&strips->init, ground_atom_to_fact_id[id]);
                }
            }
        }
    }
    LOG(err, "Created init state consisting of %d facts",
        pddlISetSize(&strips->init));
    return 0;
}

struct create_goal {
    pddl_strips_maker_t *sm;
    pddl_strips_t *strips;
    const int *ground_atom_to_fact_id;
    pddl_err_t *err;
    int fail;
};

static int _createGoal(pddl_fm_t *c, void *_g)
{
    struct create_goal *ggoal = _g;
    const pddl_ground_atom_t *ga;
    pddl_strips_maker_t *sm = ggoal->sm;
    pddl_strips_t *strips = ggoal->strips;
    const int *ground_atom_to_fact_id = ggoal->ground_atom_to_fact_id;
    pddl_err_t *err = ggoal->err;

    if (pddlFmIsAtom(c)){
        const pddl_fm_atom_t *atom = pddlFmToAtom(c);
        if (!pddlFmAtomIsGrounded(atom))
            PDDL_ERR_RET(err, -1, "Goal specification cannot contain"
                          " parametrized atoms.");

        // Find fact in the set of reachable facts
        ga = pddlGroundAtomsFindAtom(&sm->ground_atom, atom, NULL);
        if (ga != NULL){
            // Add the fact to the goal specification
            pddlISetAdd(&strips->goal, ground_atom_to_fact_id[ga->id]);
        }else{
            // The goal can be static fact in which case we simply skip
            // this fact
            ga = pddlGroundAtomsFindAtom(&sm->ground_atom_static, atom, NULL);
            if (ga == NULL){
                // The problem is unsolvable, because a goal fact is not
                // reachable.
                strips->goal_is_unreachable = 1;
            }
        }
        return 0;

    }else if (pddlFmIsAnd(c)){
        return 0;

    }else if (pddlFmIsBool(c)){
        const pddl_fm_bool_t *b = pddlFmToBoolConst(c);
        if (!b->val)
            strips->goal_is_unreachable = 1;
        return 0;

    }else{
        PDDL_ERR(err, "Only conjuctive goal specifications are supported."
                 " (Goal contains %s.)", pddlFmTypeName(c->type));
        ggoal->fail = 1;
        return -2;
    }
}

static int createGoal(pddl_strips_maker_t *sm,
                      pddl_strips_t *strips,
                      const pddl_t *pddl,
                      const pddl_ground_config_t *cfg,
                      const int *ground_atom_to_fact_id,
                      pddl_err_t *err)
{
    struct create_goal ggoal = { sm, strips, ground_atom_to_fact_id, err, 0 };
    if (pddlFmIsOr(pddl->goal)){
        PDDL_ERR_RET(err, -1, "Only conjuctive goal specifications"
                      " are supported. This goal is a disjunction.");
    }

    pddlFmTraverseProp(pddl->goal, _createGoal, NULL, &ggoal);
    if (ggoal.fail)
        PDDL_TRACE_RET(err, -1);
    LOG(err, "Goal created consisting of %d facts",
        pddlISetSize(&strips->goal));
    return 0;
}

struct action_ctx {
    pddl_strips_maker_t *sm;
    const pddl_t *pddl;
    const pddl_ground_config_t *cfg;
    const pddl_action_t *action;
    const int *args;
    const int *ground_atom_to_fact;
    pddl_err_t *err;
    int failed;

    int cond_eff;
    int cond_eff_failed;
    pddl_strips_op_t *op;
};
typedef struct action_ctx action_ctx_t;

static int actionCondEff(action_ctx_t *ctx_in,
                         const pddl_fm_t *pre,
                         const pddl_fm_t *eff);

static char *groundOpName(const pddl_t *pddl,
                          const pddl_action_t *action,
                          const int *args)
{
    int i, slen;
    char *name, *cur;

    slen = strlen(action->name) + 2 + 1;
    for (i = 0; i < action->param.param_size; ++i)
        slen += 1 + strlen(pddl->obj.obj[args[i]].name);

    cur = name = ALLOC_ARR(char, slen);
    cur += sprintf(cur, "%s", action->name);
    for (i = 0; i < action->param.param_size; ++i)
        cur += sprintf(cur, " %s", pddl->obj.obj[args[i]].name);

    return name;
}

static char *groundAtomName(const pddl_t *pddl,
                            const pddl_fm_atom_t *atom,
                            const int *args)
{
    char *name = ALLOC_ARR(char, 1024);
    int wr = 0;

    wr += snprintf(name, 1024, "%s", pddl->pred.pred[atom->pred].name);
    for (int i = 0; i < atom->arg_size; ++i){
        if (atom->arg[i].param >= 0){
            if (wr < 1024){
                wr += snprintf(name, 1024 - wr, " %s",
                               pddl->obj.obj[args[atom->arg[i].param]].name);
            }
        }else{
            ASSERT(atom->arg[i].obj >= 0);
            if (wr < 1024){
                wr += snprintf(name, 1024 - wr, " %s",
                               pddl->obj.obj[atom->arg[i].obj].name);
            }
        }
    }

    return name;
}

static int atomArg(const pddl_fm_atom_t *a, int i, const int *args)
{
    if (a->arg[i].obj >= 0)
        return a->arg[i].obj;
    return args[a->arg[i].param];
}

static int actionCostFromNumOp(pddl_strips_maker_t *smaker,
                               const pddl_fm_t *op,
                               const int *args,
                               int *cost,
                               const pddl_t *pddl,
                               const pddl_action_t *action,
                               pddl_err_t *err)
{
    if (!pddlFmIsNumOp(op))
        return 1;

    const pddl_fm_atom_t *atom_val;
    int ival;
    if (pddlFmNumOpCheckSimpleIncreaseTotalCost(
                op, smaker->func_total_cost_id, &atom_val, &ival) == 0){
        if (atom_val != NULL){
            const pddl_ground_atom_t *ga;
            ga = pddlGroundAtomsFindAtom(&smaker->ground_func, atom_val, args);
            if (ga == NULL){
                if (pddl == NULL || action == NULL)
                    return -1;

                char *oname = groundOpName(pddl, action, args);
                char *aname = groundAtomName(pddl, atom_val, args);
                ERR(err, "Cannot determine the cost of action (%s),"
                    " because function (%s) has no assigned value.",
                    oname, aname);
                if (oname != NULL)
                    FREE(oname);
                if (aname != NULL)
                    FREE(aname);
                return -1;

            }else{
                *cost = ga->func_val;
                return 0;
            }

        }else{
            *cost = ival;
            return 0;
        }

    }else{
        char *oname = groundOpName(pddl, action, args);
        ERR(err, "Only costs defined by"
                 " (increase (total-cost) atom-or-integer-value) are"
                 " supported -- action (%s).", oname);
        if (oname != NULL)
            FREE(oname);
        return -2;
    }
}

static int actionPre(pddl_fm_t *c, void *ud)
{
    action_ctx_t *ctx = ud;

    if (pddlFmIsAtom(c)){
        pddl_fm_atom_t *a = pddlFmToAtom(c);
        if (a->pred == ctx->pddl->pred.eq_pred){
            int p1 = atomArg(a, 0, ctx->args);
            int p2 = atomArg(a, 1, ctx->args);
            int sat = 0;
            if (a->neg){
                sat = (p1 != p2);
            }else{
                sat = (p1 == p2);
            }
            if (!sat){
                if (ctx->cond_eff){
                    ctx->cond_eff_failed = 1;
                    return -2;
                }
                PANIC("Unsatisfied (in)equality precondition."
                            " This is definitely a bug!\n");
            }

        }else if (a->neg){
            pddl_ground_atom_t *ga;
#ifdef PDDL_DEBUG
            ga = pddlGroundAtomsFindAtom(&ctx->sm->ground_atom, a, ctx->args);
            ASSERT(ga == NULL);
#endif /* PDDL_DEBUG */
            ga = pddlGroundAtomsFindAtom(&ctx->sm->ground_atom_static,
                                         a, ctx->args);
            if (ga != NULL){
                if (ctx->cond_eff){
                    ctx->cond_eff_failed = 1;
                    return -2;
                }
                PANIC("Unsatisfied negative precondition."
                            " This is definitely a bug!\n");
            }

        }else{
            int is_static = 0;
            pddl_ground_atom_t *ga;
            ga = pddlGroundAtomsFindAtom(&ctx->sm->ground_atom, a, ctx->args);
            if (ga == NULL){
                ga = pddlGroundAtomsFindAtom(&ctx->sm->ground_atom_static,
                                             a, ctx->args);
                is_static = 1;
            }
            if (ctx->cond_eff && ga == NULL){
                ctx->cond_eff_failed = 1;
                return -2;
            }

            if (ga == NULL){
                PANIC("Unsatisfied positive precondition."
                            " This is definitely a bug!\n");
            }
            if (!is_static){
                pddlISetAdd(&ctx->op->pre, ctx->ground_atom_to_fact[ga->id]);

            }else if (ctx->cfg->keep_all_static_facts){
                int id = ga->id + ctx->sm->ground_atom.atom_size;
                pddlISetAdd(&ctx->op->pre, ctx->ground_atom_to_fact[id]);
            }
        }
        return 0;

    }else if (pddlFmIsAnd(c)){
        return 0;
    }else{
        PDDL_ERR(ctx->err, "Precondition is not a conjuction."
                  " It seems PDDL was not normalized.");
        ctx->failed = 1;
        return -2;
    }
}

static int actionEff(pddl_fm_t *c, void *ud)
{
    action_ctx_t *ctx = ud;

    if (pddlFmIsAtom(c)){
        pddl_fm_atom_t *a = pddlFmToAtom(c);
        pddl_ground_atom_t *ga;
        ga = pddlGroundAtomsFindAtom(&ctx->sm->ground_atom, a, ctx->args);
        ASSERT(ga != NULL || a->neg);
        if (a->neg){
            if (ga != NULL)
                pddlISetAdd(&ctx->op->del_eff, ctx->ground_atom_to_fact[ga->id]);
        }else{
            pddlISetAdd(&ctx->op->add_eff, ctx->ground_atom_to_fact[ga->id]);
        }
        return 0;

    }else if (pddlFmIsNumCmp(c)){
        PDDL_ERR(ctx->err, "numerical comparators are not allowed in operators' effects.");
        ctx->failed = 1;
        return -2;

    }else if (pddlFmIsNumOp(c)){
        if (!ctx->pddl->metric)
            return -1;

        if (ctx->cond_eff){
            ctx->cond_eff_failed = 1;
            ctx->failed = 1;
            PDDL_ERR_RET(ctx->err, -2,
                          "Costs in conditional effects are not supported.");
        }

        int cost = 0;
        int st = actionCostFromNumOp(ctx->sm, c, ctx->args, &cost,
                                     ctx->pddl, ctx->action, ctx->err);
        if (st == 0){
            ctx->op->cost += cost;

        }else if (st < 0){
            ctx->failed = 1;
            return -2;
        }

        return -1;

    }else if (pddlFmIsWhen(c)){
        pddl_fm_when_t *w = pddlFmToWhen(c);
        if (actionCondEff(ctx, w->pre, w->eff) != 0){
            ctx->failed = 1;
            return -2;
        }
        return -1;

    }else if (pddlFmIsAnd(c)){
        return 0;

    }else{
        PDDL_ERR(ctx->err, "Effect is not a conjuction"
                  " It seems PDDL was not normalized.");
        ctx->failed = 1;
        return -2;
    }
}

static int actionCondEff(action_ctx_t *ctx_in,
                         const pddl_fm_t *pre,
                         const pddl_fm_t *eff)
{
    action_ctx_t ctx = *ctx_in;
    ctx.cond_eff = 1;
    ctx.cond_eff_failed = 0;
    pddl_strips_op_t op;
    pddlStripsOpInit(&op);
    ctx.op = &op;

    pddlFmTraverseProp((pddl_fm_t *)pre, actionPre, NULL, &ctx);
    if (ctx.failed)
        PDDL_TRACE_RET(ctx_in->err, -1);

    if (!ctx.cond_eff_failed){
        pddlFmTraverseProp((pddl_fm_t *)eff, actionEff, NULL, &ctx);
        if (ctx.failed)
            PDDL_TRACE_RET(ctx_in->err, -1);
    }

    if (!ctx.cond_eff_failed
            && (pddlISetSize(&op.add_eff) > 0
                    || pddlISetSize(&op.del_eff) > 0)){
        pddlStripsOpAddCondEff(ctx_in->op, &op);
    }
    pddlStripsOpFree(&op);
    return 0;
}

static int createOp(pddl_strips_maker_t *sm,
                    const pddl_t *pddl,
                    const pddl_ground_config_t *cfg,
                    const int *ground_atom_to_fact_id,
                    const pddl_action_t *a,
                    const int *args,
                    pddl_strips_op_t *op,
                    pddl_err_t *err)
{
    action_ctx_t ctx;
    ctx.sm = sm;
    ctx.pddl = pddl;
    ctx.cfg = cfg;
    ctx.action = a;
    ctx.args = args;
    ctx.ground_atom_to_fact = ground_atom_to_fact_id;
    ctx.err = err;
    ctx.failed = 0;
    ctx.cond_eff = 0;
    ctx.cond_eff_failed = 0;
    ctx.op = op;

    op->cost = 0;
    pddlFmTraverseProp((pddl_fm_t *)a->pre, actionPre, NULL, &ctx);
    if (ctx.failed)
        PDDL_TRACE_RET(err, -1);
    pddlFmTraverseProp((pddl_fm_t *)a->eff, actionEff, NULL, &ctx);
    if (ctx.failed)
        PDDL_TRACE_RET(err, -1);

    if (!pddl->metric)
        op->cost = 1;
    op->pddl_action_id = a->id;

    if (a->is_aux_zero_cost_remove_from_plan){
        op->cost = 0;
        op->is_aux_remove_from_plan = pddl_true;
    }

    return 0;
}

static int createOpFromGroundActionArgs(pddl_strips_maker_t *sm,
                                        pddl_strips_t *strips,
                                        const pddl_t *pddl,
                                        const pddl_ground_config_t *cfg,
                                        const int *ground_atom_to_fact_id,
                                        const pddl_ground_action_args_t *ga,
                                        pddl_err_t *err)
{
    const pddl_action_t *action = pddl->action.action + ga->action_id;
    pddl_strips_op_t op;
    pddlStripsOpInit(&op);
    int ret = createOp(sm, pddl, cfg, ground_atom_to_fact_id, action, ga->arg,
                       &op, err);
    if (ret == 0){
        char *name = groundOpName(pddl, action, ga->arg);
        if (cfg->keep_action_args){
            op.action_args_size = action->param.param_size;
            op.action_args = ALLOC_ARR(int, op.action_args_size);
            memcpy(op.action_args, ga->arg,
                   sizeof(int) * op.action_args_size);
        }
        pddlStripsOpFinalize(&op, name);
        if (pddlISetSize(&op.add_eff) > 0
                || pddlISetSize(&op.del_eff) > 0
                || op.cond_eff_size > 0){
            pddlStripsOpsAdd(&strips->op, &op);
            if (op.cond_eff_size > 0)
                strips->has_cond_eff = 1;
        }
    }

    pddlStripsOpFree(&op);
    if (ret != 0)
        PDDL_TRACE_RET(err, ret);
    return 0;
}

static int createOps(pddl_strips_maker_t *sm,
                     pddl_strips_t *strips,
                     const pddl_t *pddl,
                     const pddl_ground_config_t *cfg,
                     const int *ground_atom_to_fact_id,
                     pddl_err_t *err)
{
    for (int i = 0; i < sm->num_action_args; ++i){
        pddl_ground_action_args_t **ppa = pddlExtArrGet(sm->action_args_arr, i);
        pddl_ground_action_args_t *ga = *ppa;

        if (ga->action_id2 != 0){
            pddl_ground_action_args_t *ga2;
            ga2 = pddlStripsMakerFindAction(sm, ga->action_id, 0, ga->arg);
            if (ga2 != NULL)
                ga = NULL;
        }

        if (ga != NULL){
            int ret = createOpFromGroundActionArgs(sm, strips, pddl, cfg,
                                                   ground_atom_to_fact_id,
                                                   ga, err);
            if (ret != 0)
                PDDL_TRACE_RET(err, ret);
        }
    }

    pddlStripsOpsSort(&strips->op);
    LOG(err, "Operators sorted.");
    LOG(err, "Created %d operators", strips->op.op_size);

    return 0;
}

int pddlStripsMakerMakeStrips(pddl_strips_maker_t *sm,
                              const pddl_t *pddl,
                              const pddl_ground_config_t *cfg,
                              pddl_strips_t *strips,
                              pddl_err_t *err)
{
    CTX(err, "Strips Maker");
    pddlStripsInit(strips);
    strips->cfg = *cfg;
    if (pddl->domain_name)
        strips->domain_name = STRDUP(pddl->domain_name);
    if (pddl->problem_name)
        strips->problem_name = STRDUP(pddl->problem_name);
    if (pddl->domain_file != NULL)
        strips->domain_file = STRDUP(pddl->domain_file);
    if (pddl->problem_file)
        strips->problem_file = STRDUP(pddl->problem_file);

    int *ground_atom_to_fact = NULL;
    if (createStripsFacts(sm, strips, pddl, cfg, &ground_atom_to_fact, err) != 0
            || createInitState(sm, strips, pddl, cfg, ground_atom_to_fact, err) != 0
            || createGoal(sm, strips, pddl, cfg, ground_atom_to_fact, err) != 0
            || createOps(sm, strips, pddl, cfg, ground_atom_to_fact, err) != 0){
        CTXEND(err);
        PDDL_TRACE_RET(err, -1);
    }
    if (ground_atom_to_fact != NULL)
        FREE(ground_atom_to_fact);

    if (cfg->remove_static_facts)
        pddlStripsRemoveStaticFacts(strips, err);

    pddlStripsMergeCondEffIfPossible(strips);
    LOG(err, "Merged conditional effects where possible.");

    pddlStripsOpsDeduplicate(&strips->op);
    LOG(err, "Operators deduplicated. Num operators: %d",
        strips->op.op_size);

    if (strips->goal_is_unreachable){
        LOG(err, "Strips problem marked as unsolvable");
        pddlStripsMakeUnsolvable(strips);
    }

    LOG(err, "Number of Strips Operators: %d", strips->op.op_size);
    LOG(err, "Number of Strips Facts: %d", strips->fact.fact_size);
    int count = 0;
    for (int i = 0; i < strips->op.op_size; ++i){
        if (strips->op.op[i]->cond_eff_size > 0)
            ++count;
    }
    LOG(err, "Number of Strips Operators with Conditional Effects:"
        " %d", count);
    LOG(err, "Goal is unreachable: %d", strips->goal_is_unreachable);
    LOG(err, "Has Conditional Effects: %d", strips->has_cond_eff);


    LOG(err, "PDDL grounded to STRIPS.");
    CTXEND(err);
    return 0;
}

pddl_ground_action_args_t *pddlStripsMakerActionArgs(pddl_strips_maker_t *sm,
                                                     int id)
{
    pddl_ground_action_args_t **ppa = pddlExtArrGet(sm->action_args_arr, id);
    return *ppa;
}

pddl_ground_atom_t *pddlStripsMakerGroundAtom(pddl_strips_maker_t *sm, int id)
{
    return sm->ground_atom.atom[id];
}
const pddl_ground_atom_t *pddlStripsMakerGroundAtomConst(
                const pddl_strips_maker_t *sm, int id)
{
    return sm->ground_atom.atom[id];
}

static int stripsEffInState(pddl_strips_maker_t *smaker,
                            const pddl_t *pddl,
                            const pddl_action_t *action,
                            const pddl_fm_t *pre,
                            const pddl_fm_t *eff,
                            const int *args,
                            const pddl_iset_t *state,
                            pddl_iset_t *add_eff,
                            pddl_iset_t *del_eff,
                            int *cost,
                            pddl_err_t *err)
{
    pddl_fm_const_it_t it;
    const pddl_fm_t *fm;

    if (pre != NULL){
        PDDL_FM_FOR_EACH(pre, &it, fm){
            if (pddlFmIsAtom(fm)){
                const pddl_fm_atom_t *atom = pddlFmToAtomConst(fm);
                if (atom->pred == smaker->eq_pred){
                    ASSERT(atom->arg_size == 2);
                    int o1 = atom->arg[0].obj;
                    if (atom->arg[0].param >= 0)
                        o1 = args[atom->arg[0].param];

                    int o2 = atom->arg[1].obj;
                    if (atom->arg[1].param >= 0)
                        o2 = args[atom->arg[1].param];

                    if (atom->neg){
                        if (o1 == o2)
                            return 1;
                    }else{
                        if (o1 != o2)
                            return 1;
                    }
                    continue;
                }

                const pddl_ground_atom_t *ga;
                ga = pddlGroundAtomsFindAtom(&smaker->ground_atom_static,
                                             atom, args);
                // Negative preconditions are of static predicates only
                if (atom->neg){
                    if (ga != NULL)
                        return 1;
                }else{
                    if (ga == NULL){
                        ga = pddlGroundAtomsFindAtom(&smaker->ground_atom,
                                                     atom, args);
                        if (ga == NULL || !pddlISetIn(ga->id, state))
                            return 1;
                    }
                }

            }
        }
    }

    PDDL_FM_FOR_EACH(eff, &it, fm){
        if (pddlFmIsAtom(fm)){
            const pddl_fm_atom_t *atom = pddlFmToAtomConst(fm);
            const pddl_ground_atom_t *ga;
            ga = pddlStripsMakerAddAtom(smaker, atom, args, NULL);
            if (atom->neg){
                pddlISetAdd(del_eff, ga->id);
            }else{
                pddlISetAdd(add_eff, ga->id);
            }

        }else if (pddlFmIsWhen(fm)){
            const pddl_fm_when_t *w = pddlFmToWhenConst(fm);
            if (stripsEffInState(smaker, pddl, action, w->pre, w->eff,
                                 args, state, add_eff, del_eff, cost, err) < 0){
                TRACE_RET(err, -1);
            }

        }else if (pddlFmIsNumOp(fm)){
            int c = 0;
            int st = actionCostFromNumOp(smaker, fm, args, &c, pddl, action, err);
            if (st == 0){
                *cost += c;

            }else if (st < 0){
                TRACE_RET(err, -1);
            }
        }
    }
    return 0;
}

int pddlStripsMakerActionEffInState(pddl_strips_maker_t *smaker,
                                    const pddl_t *pddl,
                                    const pddl_action_t *a,
                                    const int *args,
                                    const pddl_iset_t *state,
                                    pddl_iset_t *add_eff,
                                    pddl_iset_t *del_eff,
                                    int *cost,
                                    pddl_err_t *err)
{
    *cost = 0;
    int st = stripsEffInState(smaker, pddl, a, NULL, a->eff, args, state,
                              add_eff, del_eff, cost, err);
    if (st < 0)
        TRACE_RET(err, -1);

    pddlISetIntersect(del_eff, state);
    pddlISetMinus(del_eff, add_eff);
    pddlISetMinus(add_eff, state);
    return 0;
}
