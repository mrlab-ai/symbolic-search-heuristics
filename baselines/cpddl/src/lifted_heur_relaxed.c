/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/lifted_heur_relaxed.h"
#include "pddl/set.h"
#include "datalog_pddl.h"
#include "internal.h"

typedef struct ff_context ff_context_t;

struct ff_context_action {
    const char *name;
    const pddl_t *pddl;
    /** Cost of the action */
    pddl_cost_t cost;
    /** Set of all possible preconditions, each precondition represented by
     *  the ID of the corresponding set of facts from ctx->action_pre. */
    pddl_iset_t pres;
    ff_context_t *ctx;
};
typedef struct ff_context_action ff_context_action_t;

struct ff_context {
    int action_size;
    /** All possible action preconditions */
    pddl_set_iset_t action_pre;
    /** Separate context for each action schema */
    ff_context_action_t *action_ctx;
};

static pddl_cost_t actionCost(const pddl_t *pddl, const pddl_fm_t *eff)
{
    pddl_cost_t w = pddl_cost_zero;

    if (!pddl->metric){
        pddlCostSetOp(&w, 1);
    }else{
        pddlCostSetZero(&w);
        const pddl_fm_t *fm;
        pddl_fm_const_it_t it;
        PDDL_FM_FOR_EACH(eff, &it, fm){
            if (!pddlFmIsNumOp(fm))
                continue;

            const pddl_fm_atom_t *atom_val;
            int ival;
            if (pddlFmNumOpCheckSimpleIncreaseTotalCost(
                        fm, pddl->func.total_cost_func, &atom_val, &ival) == 0){
                if (atom_val != NULL){
                    // TODO
                    PANIC("Lifted relaxed heuristics do not support"
                           " non-static action costs yet.");
                }else{
                    w.cost += ival;
                }

            }else{
                PANIC("Lifted relaxed heuristics do not support numeric tasks.");
            }
        }
    }

    return w;
}

static ff_context_t *ffContextNew(const pddl_t *pddl)
{
    ff_context_t *ctx = ALLOC(ff_context_t);
    ctx->action_size = pddl->action.action_size;
    pddlSetISetInit(&ctx->action_pre);
    ctx->action_ctx = ZALLOC_ARR(ff_context_action_t, ctx->action_size);
    for (int ai = 0; ai < ctx->action_size; ++ai){
        ctx->action_ctx[ai].ctx = ctx;
        ctx->action_ctx[ai].cost = actionCost(pddl, pddl->action.action[ai].eff);
        ctx->action_ctx[ai].name = pddl->action.action[ai].name;
        ctx->action_ctx[ai].pddl = pddl;
    }

    return ctx;
}

static void ffContextDel(ff_context_t *ctx)
{
    pddlSetISetFree(&ctx->action_pre);
    for (int ai = 0; ai < ctx->action_size; ++ai)
        pddlISetFree(&ctx->action_ctx[ai].pres);
    if (ctx->action_ctx != NULL)
        FREE(ctx->action_ctx);
    FREE(ctx);
}

static void ffContextClear(ff_context_t *ctx)
{
    for (int ai = 0; ai < ctx->action_size; ++ai)
        pddlISetEmpty(&ctx->action_ctx[ai].pres);
    pddlSetISetFree(&ctx->action_pre);
    pddlSetISetInit(&ctx->action_pre);
}

static void ffActionCostInc(ff_context_action_t *ctx, const pddl_t *pddl,
                            pddl_cost_t *w)
{
    int set_id;
    PDDL_ISET_FOR_EACH(&ctx->pres, set_id){
        (void)set_id;
        pddlCostSum(w, &ctx->cost);
    }
}

static pddl_cost_t ffCost(ff_context_t *ctx, const pddl_t *pddl)
{
    pddl_cost_t w = pddl_cost_zero;
    for (int ai = 0; ai < ctx->action_size; ++ai)
        ffActionCostInc(ctx->action_ctx + ai, pddl, &w);
    return w;
}

static void ffAnnotation(pddl_datalog_t *dl,
                         int head_fact_id,
                         const pddl_iset_t *body_ids,
                         void *userdata)
{
    ff_context_action_t *ctx = userdata;
    int set_id = pddlSetISetAdd(&ctx->ctx->action_pre, body_ids);
    pddlISetAdd(&ctx->pres, set_id);

    /*
    int pred;
    int arity;
    int arg[10];

    printf("ann: %s | ", ctx->name);
    int st = pddlDatalogFact(dl, head_fact_id, &pred, &arity, arg, NULL);
    ASSERT(st == 0);
    printf("%d:(%s", head_fact_id, ctx->pddl->pred.pred[pred].name);
    for (int i = 0; i < arity; ++i)
        printf(" %s", ctx->pddl->obj.obj[arg[i]].name);
    printf(")");

    printf(" :-");

    int fact_id;
    PDDL_ISET_FOR_EACH(body_ids, fact_id){
        int st = pddlDatalogFact(dl, fact_id, &pred, &arity, arg, NULL);
        ASSERT(st == 0);
        printf(" %d:(%s", fact_id, ctx->pddl->pred.pred[pred].name);
        for (int i = 0; i < arity; ++i)
            printf(" %s", ctx->pddl->obj.obj[arg[i]].name);
        printf(")");
    }

    printf(" ; c = %s", F_COST(&ctx->cost));
    printf(".\n");
    fflush(stdout);
    */
}


static void addPreToBody(pddl_lifted_heur_relaxed_t *h,
                         pddl_datalog_rule_t *rule,
                         const pddl_fm_t *pre)
{
    const pddl_fm_atom_t *catom;
    pddl_fm_const_it_atom_t it;
    PDDL_FM_FOR_EACH_ATOM(pre, &it, catom){
        pddl_datalog_atom_t atom;
        pddlDatalogPddlAtomToDLAtom(h->dl, &atom, catom, h->pred_to_dlpred,
                                    h->obj_to_dlconst, h->dlvar);
        if (catom->neg){
            pddlDatalogRuleAddNegStaticBody(h->dl, rule, &atom);
        }else{
            pddlDatalogRuleAddBody(h->dl, rule, &atom);
        }
        pddlDatalogAtomFree(h->dl, &atom);
    }
}

static void addActionRule(pddl_lifted_heur_relaxed_t *h,
                          int action_id,
                          const pddl_fm_t *pre,
                          const pddl_fm_t *eff,
                          const pddl_fm_t *pre2)
{
    const pddl_action_t *action = h->pddl->action.action + action_id;
    ff_context_t *ff_ctx = h->ff_ctx;


    pddl_datalog_rule_t rule;
    pddlDatalogRuleInit(h->dl, &rule);

    addPreToBody(h, &rule, pre);
    if (pre2 != NULL)
        addPreToBody(h, &rule, pre2);
    pddlDatalogPddlSetActionTypeBody(h->dl, &rule, h->pddl, &action->param,
                                     pre, pre2, h->type_to_dlpred, h->dlvar);

    // Set cost of the operator
    pddl_cost_t w = actionCost(h->pddl, eff);

    const pddl_fm_atom_t *catom;
    pddl_fm_const_it_atom_t it;
    PDDL_FM_FOR_EACH_ATOM(eff, &it, catom){
        if (catom->neg)
            continue;

        pddl_datalog_atom_t atom;
        pddlDatalogPddlAtomToDLAtom(h->dl, &atom, catom, h->pred_to_dlpred,
                                    h->obj_to_dlconst, h->dlvar);
        pddlDatalogRuleSetHead(h->dl, &rule, &atom);
        pddlDatalogAtomFree(h->dl, &atom);

        pddlDatalogRuleSetWeight(h->dl, &rule, &w);

        if (h->ff_ctx != NULL){
            pddlDatalogRuleAddAnnotation(h->dl, &rule, ffAnnotation,
                                         ff_ctx->action_ctx + action_id);
        }

        pddlDatalogAddRule(h->dl, &rule);
    }

    pddlDatalogRuleFree(h->dl, &rule);
}

static void addActionRules(pddl_lifted_heur_relaxed_t *h, int action_id)
{
    const pddl_action_t *action = h->pddl->action.action + action_id;

    addActionRule(h, action_id, action->pre, action->eff, NULL);

    // Conditional effects
    pddl_fm_const_it_when_t wit;
    const pddl_fm_when_t *when;
    PDDL_FM_FOR_EACH_WHEN(action->eff, &wit, when)
        addActionRule(h, action_id, action->pre, when->eff, when->pre);
}

static void addActionsRules(pddl_lifted_heur_relaxed_t *h)
{
    for (int i = 0; i < h->pddl->action.action_size; ++i)
        addActionRules(h, i);
}

static void addGoal(pddl_lifted_heur_relaxed_t *h)
{
    pddl_datalog_rule_t rule;
    pddlDatalogRuleInit(h->dl, &rule);

    h->goal_dlpred = pddlDatalogAddGoalPred(h->dl, "GOAL");
    pddl_datalog_atom_t atom;
    pddlDatalogAtomInit(h->dl, &atom, h->goal_dlpred);
    pddlDatalogRuleSetHead(h->dl, &rule, &atom);
    pddlDatalogAtomFree(h->dl, &atom);

    const pddl_fm_atom_t *a;
    pddl_fm_const_it_atom_t it;
    PDDL_FM_FOR_EACH_ATOM(h->pddl->goal, &it, a){
        pddl_datalog_atom_t atom;
        pddlDatalogAtomInit(h->dl, &atom, h->pred_to_dlpred[a->pred]);
        for (int i = 0; i < a->arg_size; ++i){
            int obj = a->arg[i].obj;
            ASSERT(obj >= 0);
            pddlDatalogAtomSetArg(h->dl, &atom, i, h->obj_to_dlconst[obj]);
        }
        pddlDatalogRuleAddBody(h->dl, &rule, &atom);
        pddlDatalogAtomFree(h->dl, &atom);
    }
    pddlDatalogAddRule(h->dl, &rule);
    pddlDatalogRuleFree(h->dl, &rule);
}

static void addFacts(pddl_lifted_heur_relaxed_t *h,
                     const pddl_iset_t *facts,
                     const pddl_ground_atoms_t *gatoms)
{
    int fact;
    PDDL_ISET_FOR_EACH(facts, fact){
        const pddl_ground_atom_t *ga = gatoms->atom[fact];
        if (pddlPredIsStatic(h->pddl->pred.pred + ga->pred))
            continue;

        pddl_datalog_rule_t rule;
        pddlDatalogRuleInit(h->dl, &rule);

        unsigned pred = h->pred_to_dlpred[ga->pred];
        unsigned arg[ga->arg_size];
        for (int i = 0; i < ga->arg_size; ++i)
            arg[i] = h->obj_to_dlconst[ga->arg[i]];
        pddlDatalogAddFactToDB(h->dl, pred, arg, &pddl_cost_zero);
    }
}

static void addInitStaticFacts(pddl_lifted_heur_relaxed_t *h)
{
    const pddl_fm_atom_t *a;
    pddl_fm_const_it_atom_t it;
    PDDL_FM_FOR_EACH_ATOM(&h->pddl->init->fm, &it, a){
        if (!pddlPredIsStatic(h->pddl->pred.pred + a->pred))
            continue;

        pddl_datalog_atom_t atom;
        pddl_datalog_rule_t rule;
        pddlDatalogRuleInit(h->dl, &rule);
        pddlDatalogAtomInit(h->dl, &atom, h->pred_to_dlpred[a->pred]);
        for (int i = 0; i < a->arg_size; ++i){
            int obj = a->arg[i].obj;
            ASSERT(obj >= 0);
            pddlDatalogAtomSetArg(h->dl, &atom, i, h->obj_to_dlconst[obj]);
        }
        pddlDatalogRuleSetHead(h->dl, &rule, &atom);
        pddlDatalogAtomFree(h->dl, &atom);
        pddlDatalogAddRule(h->dl, &rule);
        pddlDatalogRuleFree(h->dl, &rule);
    }
}

static void pddlLiftedHeurRelaxedInit(pddl_lifted_heur_relaxed_t *h,
                                      const pddl_t *pddl,
                                      pddl_bool_t collect_best_achiever_facts,
                                      pddl_bool_t ff_heur,
                                      int (*canonical_model)(pddl_datalog_t *,
                                                             pddl_cost_t *,
                                                             int collect_fact_achievers,
                                                             pddl_err_t *),
                                      pddl_err_t *err)
{
    CTX(err, "lifted-relax-heur");
    ZEROIZE(h);
    h->pddl = pddl;
    h->collect_best_achiever_facts = collect_best_achiever_facts;
    if (ff_heur)
        h->ff_ctx = ffContextNew(pddl);
    h->canonical_model = canonical_model;
    h->dl = pddlDatalogNew();
    h->type_to_dlpred = ALLOC_ARR(unsigned, h->pddl->type.type_size);
    h->pred_to_dlpred = ALLOC_ARR(unsigned, h->pddl->pred.pred_size);
    h->obj_to_dlconst = ALLOC_ARR(unsigned, h->pddl->obj.obj_size);

    h->dlvar_size = pddlDatalogPddlMaxVarSize(pddl);
    h->dlvar = ALLOC_ARR(unsigned, h->dlvar_size);
    for (int i = 0; i < h->dlvar_size; ++i)
        h->dlvar[i] = pddlDatalogAddVar(h->dl, NULL);

    for (int i = 0; i < h->pddl->type.type_size; ++i)
        h->type_to_dlpred[i] = UINT_MAX;

    for (int i = 0; i < h->pddl->pred.pred_size; ++i){
        const pddl_pred_t *pred = h->pddl->pred.pred + i;
        h->pred_to_dlpred[i]
            = pddlDatalogAddPred(h->dl, pred->param_size, pred->name);
        pddlDatalogSetUserId(h->dl, h->pred_to_dlpred[i], i);
    }

    for (int i = 0; i < h->pddl->obj.obj_size; ++i){
        const pddl_obj_t *obj = h->pddl->obj.obj + i;
        h->obj_to_dlconst[i] = pddlDatalogAddConst(h->dl, obj->name);
        pddlDatalogSetUserId(h->dl, h->obj_to_dlconst[i], i);
    }

    pddlDatalogPddlAddEqRules(h->dl, h->pddl, h->pred_to_dlpred,
                              h->obj_to_dlconst);
    addActionsRules(h);
    addInitStaticFacts(h);
    pddlDatalogPddlAddTypeRules(h->dl, h->pddl, h->type_to_dlpred,
                                h->obj_to_dlconst);
    addGoal(h);

    pddlDatalogToNormalForm(h->dl, err);
    CTXEND(err);
}

void pddlLiftedHeurRelaxedFree(pddl_lifted_heur_relaxed_t *h)
{
    pddlDatalogDel(h->dl);
    FREE(h->type_to_dlpred);
    FREE(h->pred_to_dlpred);
    FREE(h->obj_to_dlconst);
    FREE(h->dlvar);
    if (h->ff_ctx != NULL)
        ffContextDel((ff_context_t *)h->ff_ctx);
}

struct best_achievers {
    const pddl_ground_atoms_t *gatoms;
    pddl_iset_t *achievers;
};
static void bestAchieverFacts(int pred,
                              int arity,
                              const int *arg,
                              const pddl_cost_t *weight,
                              void *_d)
{
    struct best_achievers *d = _d;
    pddl_ground_atom_t *ga;
    ga = pddlGroundAtomsFindPred(d->gatoms, pred, arg, arity);
    if (ga != NULL)
        pddlISetAdd(d->achievers, ga->id);
}

void pddlLiftedHeurRelaxedBestAchieverFacts(pddl_lifted_heur_relaxed_t *h,
                                            const pddl_ground_atoms_t *gatoms,
                                            pddl_iset_t *achievers)
{
    struct best_achievers d;
    d.gatoms = gatoms;
    d.achievers = achievers;
    pddlDatalogFactsFromWeightedCanonicalModel(h->dl, h->goal_dlpred,
                                               bestAchieverFacts, &d);
}


void pddlLiftedHMaxInit(pddl_lifted_heur_relaxed_t *h,
                        const pddl_t *pddl,
                        pddl_bool_t collect_best_achiever_facts,
                        pddl_err_t *err)
{
    pddlLiftedHeurRelaxedInit(h, pddl, collect_best_achiever_facts, pddl_false,
                              pddlDatalogWeightedCanonicalModelMax, err);
}

void pddlLiftedHAddInit(pddl_lifted_heur_relaxed_t *h,
                        const pddl_t *pddl,
                        pddl_bool_t collect_best_achiever_facts,
                        pddl_err_t *err)
{
    pddlLiftedHeurRelaxedInit(h, pddl, collect_best_achiever_facts, pddl_false,
                              pddlDatalogWeightedCanonicalModelAdd, err);
}

void pddlLiftedHFFAddInit(pddl_lifted_heur_relaxed_t *h,
                          const pddl_t *pddl,
                          pddl_err_t *err)
{
    pddlLiftedHeurRelaxedInit(h, pddl, pddl_false, pddl_true,
                              pddlDatalogWeightedCanonicalModelAdd, err);
}

void pddlLiftedHFFMaxInit(pddl_lifted_heur_relaxed_t *h,
                          const pddl_t *pddl,
                          pddl_err_t *err)
{
    pddlLiftedHeurRelaxedInit(h, pddl, pddl_false, pddl_true,
                              pddlDatalogWeightedCanonicalModelMax, err);
}

pddl_cost_t pddlLiftedHeurRelaxedEvalState(pddl_lifted_heur_relaxed_t *h,
                                           const pddl_iset_t *state,
                                           const pddl_ground_atoms_t *gatoms)
{
    if (h->ff_ctx != NULL)
        ffContextClear((ff_context_t *)h->ff_ctx);

    pddlDatalogResetDB(h->dl);
    addFacts(h, state, gatoms);

    pddl_cost_t w = pddl_cost_zero;
    if (h->canonical_model(h->dl, &w, h->collect_best_achiever_facts, NULL) != 0)
        w = pddl_cost_dead_end;

    if (h->ff_ctx != NULL && pddlCostCmp(&w, &pddl_cost_dead_end) != 0){
        pddlDatalogExecuteAnnotations(h->dl, h->goal_dlpred);
        w = ffCost((ff_context_t *)h->ff_ctx, h->pddl);
    }

    return w;
}
