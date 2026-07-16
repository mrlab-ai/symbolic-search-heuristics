/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/pddl_struct.h"
#include "pddl/datalog.h"
#include "datalog_pddl.h"
#include "internal.h"

// TODO: Inequality preconditions

struct pred {
    /** True if appears negatively in a precondition or goal */
    int is_neg;
    /** True if the predicate is static */
    int is_static;
    /** True if appears negatively in goal */
    int in_goal;
    /** ID of the positive atom */
    int pos;
    /** ID of the corresponding negative atom */
    int neg;
};
typedef struct pred pred_t;

static int predArrInit(pred_t *nc, const pddl_t *pddl)
{
    ZEROIZE_ARR(nc, pddl->pred.pred_size);
    for (int i = 0; i < pddl->pred.pred_size; ++i){
        nc[i].pos = i;
        nc[i].neg = -1;
    }

    for (int i = 0; i < pddl->action.action_size; ++i){
        const pddl_fm_atom_t *atom;
        pddl_fm_const_it_atom_t it;
        PDDL_FM_FOR_EACH_ATOM(pddl->action.action[i].pre, &it, atom){
            if (atom->neg)
                nc[atom->pred].is_neg = 1;
        }

        const pddl_fm_when_t *when;
        pddl_fm_const_it_when_t wit;
        PDDL_FM_FOR_EACH_WHEN(pddl->action.action[i].eff, &wit, when){
            const pddl_fm_atom_t *atom;
            pddl_fm_const_it_atom_t it;
            PDDL_FM_FOR_EACH_ATOM(when->pre, &it, atom){
                if (atom->neg)
                    nc[atom->pred].is_neg = 1;
            }
        }
    }

    if (pddl->goal != NULL){
        const pddl_fm_atom_t *atom;
        pddl_fm_const_it_atom_t it;
        PDDL_FM_FOR_EACH_ATOM(pddl->goal, &it, atom){
            if (atom->neg){
                nc[atom->pred].is_neg = 1;
                nc[atom->pred].in_goal = 1;
            }
        }
    }

    int ret = 0;
    for (int i = 0; i < pddl->pred.pred_size; ++i){
        ret |= nc[i].is_neg;
        if (pddlPredIsStatic(pddl->pred.pred + i))
            nc[i].is_static = 1;
    }

    return ret;
}

/** Create a new NOT-... predicate and returns its ID */
static int createNewNotPred(pddl_t *pddl, int pred_id)
{
    pddl_pred_t *pos = pddl->pred.pred + pred_id;
    pddl_pred_t *neg;
    int name_size;
    char *name;

    name_size = strlen(pos->name) + 4;
    name = ALLOC_ARR(char, name_size + 1);
    strcpy(name, "NOT-");
    strcpy(name + 4, pos->name);

    neg = pddlPredsAddCopy(&pddl->pred, pred_id);
    if (neg->name != NULL)
        FREE(neg->name);
    neg->name = name;
    neg->neg_of = pred_id;
    pddl->pred.pred[pred_id].neg_of = neg->id;

    return neg->id;
}

static int replaceNegativePreconditions(pddl_fm_t **c, void *_ids)
{
    int *ids = _ids;
    int pos = ids[0];
    int neg = ids[1];

    if (pddlFmIsAtom(*c)){
        pddl_fm_atom_t *atom = pddlFmToAtom(*c);
        if (atom->pred == pos && atom->neg){
            atom->pred = neg;
            atom->neg = 0;
        }
    }

    return 0;
}

static int replaceNegativePreconditionsOfCondEffects(pddl_fm_t **c, void *_ids)
{
    int *ids = _ids;
    int pos = ids[0];
    int neg = ids[1];

    if (pddlFmIsWhen(*c)){
        pddl_fm_when_t *when = pddlFmToWhen(*c);
        pddlFmRebuildProp(&when->pre, NULL, replaceNegativePreconditions, _ids);
        pddlFmRebuildProp(&when->eff, replaceNegativePreconditionsOfCondEffects, NULL, _ids);
        return -1;

    }else if (pddlFmIsAtom(*c)){
        pddl_fm_atom_t *atom = pddlFmToAtom(*c);
        if (atom->pred == pos){
            // Create new NOT atom and flip negation
            pddl_fm_t *c2 = pddlFmClone(*c);
            pddl_fm_atom_t *not_atom = pddlFmToAtom(c2);
            not_atom->pred = neg;
            not_atom->neg = !atom->neg;

            // Transorm atom to (and atom)
            *c = pddlFmAtomToAnd(*c);
            pddl_fm_junc_t *and = pddlFmToJunc(*c);
            pddlFmJuncAdd(and, c2);

            // Prevent recursion
            return -1;
        }
    }

    return 0;
}

static void compileAwayNegConditionInAction(pddl_t *pddl, int pos, int neg,
                                            pddl_action_t *a)
{
    int ids[2] = { pos, neg };
    pddlFmRebuildProp(&a->pre, NULL, replaceNegativePreconditions, ids);
    pddlFmRebuildProp(&a->eff, replaceNegativePreconditionsOfCondEffects, NULL, ids);
    pddlActionNormalize(a, pddl);
}

static void compileAwayNegCondition(pddl_t *pddl, int pos, int neg)
{
    for (int i = 0; i < pddl->action.action_size; ++i)
        compileAwayNegConditionInAction(pddl, pos, neg, pddl->action.action + i);

    if (pddl->goal != NULL){
        int ids[2] = { pos, neg };
        pddlFmRebuildProp(&pddl->goal, NULL, replaceNegativePreconditions, ids);
    }
}

static void dlAddInitStaticFacts(pddl_datalog_t *dl,
                                 const unsigned *pred_to_dlpred,
                                 const unsigned *obj_to_dlconst,
                                 const pddl_t *pddl)

{
    const pddl_fm_atom_t *a;
    pddl_fm_const_it_atom_t it;
    PDDL_FM_FOR_EACH_ATOM(&pddl->init->fm, &it, a){
        if (!pddlPredIsStatic(pddl->pred.pred + a->pred) || a->neg)
            continue;

        pddlDatalogPddlAddFactRuleFromAtom(dl, a, pred_to_dlpred, obj_to_dlconst);
    }
}

static void initializeDatalog(pddl_datalog_t *dl,
                              unsigned *type_to_dlpred,
                              unsigned *pred_to_dlpred,
                              unsigned *obj_to_dlconst,
                              unsigned *dlvar,
                              int dlvar_size,
                              const pddl_t *pddl,
                              pddl_err_t *err)
{
    for (int i = 0; i < dlvar_size; ++i)
        dlvar[i] = pddlDatalogAddVar(dl, NULL);

    for (int i = 0; i < pddl->type.type_size; ++i)
        type_to_dlpred[i] = pddlDatalogAddPred(dl, 1, pddl->type.type[i].name);

    for (int i = 0; i < pddl->pred.pred_size; ++i){
        const pddl_pred_t *pred = pddl->pred.pred + i;
        pred_to_dlpred[i] = pddlDatalogAddPred(dl, pred->param_size, pred->name);
        pddlDatalogSetUserId(dl, pred_to_dlpred[i], i);
    }

    for (int i = 0; i < pddl->obj.obj_size; ++i){
        const pddl_obj_t *obj = pddl->obj.obj + i;
        obj_to_dlconst[i] = pddlDatalogAddConst(dl, obj->name);
        pddlDatalogSetUserId(dl, obj_to_dlconst[i], i);
    }

    pddlDatalogPddlAddEqRules(dl, pddl, pred_to_dlpred, obj_to_dlconst);
    dlAddInitStaticFacts(dl, pred_to_dlpred, obj_to_dlconst, pddl);
    pddlDatalogPddlAddTypeRules(dl, pddl, type_to_dlpred, obj_to_dlconst);
}

static void dlAddStaticBody(const pddl_t *pddl,
                            pddl_datalog_rule_t *rule,
                            const pddl_fm_atom_t *a,
                            const pddl_fm_t *pre,
                            pddl_datalog_t *dl,
                            unsigned *pred_to_dlpred,
                            unsigned *obj_to_dlconst,
                            unsigned *dlvar,
                            pddl_err_t *err)
{
    const pddl_fm_atom_t *satom;
    pddl_fm_const_it_atom_t it;
    PDDL_FM_FOR_EACH_ATOM(pre, &it, satom){
        if (!pddlPredIsStatic(pddl->pred.pred + satom->pred) || satom->neg)
            continue;

        // Check if the static atom has a common variable with the input atom
        int found = 0;
        for (int i = 0; !found && i < a->arg_size; ++i){
            if (a->arg[i].param < 0)
                continue;
            for (int j = 0; j < satom->arg_size; ++j){
                if (satom->arg[j].param == a->arg[i].param){
                    found = 1;
                    break;
                }
            }
        }
        if (!found)
            continue;

        pddl_datalog_atom_t atom;
        pddlDatalogPddlAtomToDLAtom(dl, &atom, satom, pred_to_dlpred,
                                    obj_to_dlconst, dlvar);
        pddlDatalogRuleAddBody(dl, rule, &atom);
        pddlDatalogAtomFree(dl, &atom);
    }
}

static void dlRulesForPreAndAtom(const pddl_t *pddl,
                                 const pddl_params_t *params,
                                 const pddl_fm_atom_t *a,
                                 const pddl_fm_t *pre,
                                 const pddl_fm_t *pre2,
                                 pddl_datalog_t *dl,
                                 unsigned *type_to_dlpred,
                                 unsigned *pred_to_dlpred,
                                 unsigned *obj_to_dlconst,
                                 unsigned *dlvar,
                                 pddl_err_t *err)
{
    pddl_datalog_rule_t rule;
    pddlDatalogRuleInit(dl, &rule);

    // Create head
    pddl_datalog_atom_t atom;
    pddlDatalogPddlAtomToDLAtom(dl, &atom, a, pred_to_dlpred,
                                obj_to_dlconst, dlvar);
    pddlDatalogRuleSetHead(dl, &rule, &atom);
    pddlDatalogAtomFree(dl, &atom);

    // Set types
    for (int i = 0; i < a->arg_size; ++i){
        if (a->arg[i].param >= 0){
            int type = params->param[a->arg[i].param].type;
            pddl_datalog_atom_t atom;
            pddlDatalogAtomInit(dl, &atom, type_to_dlpred[type]);
            pddlDatalogAtomSetArg(dl, &atom, 0, dlvar[a->arg[i].param]);
            pddlDatalogRuleAddBody(dl, &rule, &atom);
            pddlDatalogAtomFree(dl, &atom);
        }
    }

    // Add related static atoms
    dlAddStaticBody(pddl, &rule, a, pre, dl, pred_to_dlpred,
                    obj_to_dlconst, dlvar, err);
    if (pre2 != NULL){
        dlAddStaticBody(pddl, &rule, a, pre2, dl, pred_to_dlpred,
                        obj_to_dlconst, dlvar, err);
    }

    pddlDatalogAddRule(dl, &rule);
    pddlDatalogRuleFree(dl, &rule);
}

static void dlRulesForPre(const pddl_t *pddl,
                          int old_pred_size,
                          const pddl_params_t *params,
                          const pddl_fm_t *pre,
                          const pddl_fm_t *pre2,
                          pddl_datalog_t *dl,
                          unsigned *type_to_dlpred,
                          unsigned *pred_to_dlpred,
                          unsigned *obj_to_dlconst,
                          unsigned *dlvar,
                          pddl_err_t *err)
{
    const pddl_fm_atom_t *atom;
    pddl_fm_const_it_atom_t it;
    PDDL_FM_FOR_EACH_ATOM(pre, &it, atom){
        // We need to consider both the positinve and negative forms of the
        // newly added NOT-* predicate. Especially, when we have
        // conditional effects that might be compiled away.
        if (atom->pred >= old_pred_size){
            ASSERT(!atom->neg);
            LOG(err, "Adding datalog rule for atom %s",
                F_FM(&atom->fm, pddl, params));
            dlRulesForPreAndAtom(pddl, params, atom, pre, pre2, dl,
                                 type_to_dlpred, pred_to_dlpred,
                                 obj_to_dlconst, dlvar, err);

        }else if (pddl->pred.pred[atom->pred].neg_of >= old_pred_size){
            pddl_fm_t *fm = pddlFmClone(&atom->fm);
            pddl_fm_atom_t *neg_atom = pddlFmToAtom(fm);
            ASSERT(!neg_atom->neg);
            neg_atom->pred = pddl->pred.pred[atom->pred].neg_of;
            LOG(err, "Adding datalog rule for atom %s (from %s)",
                F_FM(&neg_atom->fm, pddl, params),
                F_FM(&atom->fm, pddl, params));
            dlRulesForPreAndAtom(pddl, params, neg_atom, pre, pre2, dl,
                                 type_to_dlpred, pred_to_dlpred,
                                 obj_to_dlconst, dlvar, err);
            pddlFmDel(fm);
        }
    }
}

static void dlFactToGroundAtom(int pred_id, int arity, const int *args,
                               void *_gatoms)
{
    pddl_ground_atoms_t *gatoms = _gatoms;
    pddlGroundAtomsAddPred(gatoms, pred_id, args, arity);
}


static void extendInitialStateUsingDL(pddl_t *pddl, int old_pred_size,
                                      const pred_t *pred, pddl_err_t *err)
{
    pddl_ground_atoms_t gatoms;
    pddlGroundAtomsInit(&gatoms);
    pddlGroundAtomsAddInit(&gatoms, pddl);

    pddl_datalog_t *dl = pddlDatalogNew();
    unsigned *type_to_dlpred = ALLOC_ARR(unsigned, pddl->type.type_size);
    unsigned *pred_to_dlpred = ALLOC_ARR(unsigned, pddl->pred.pred_size);
    unsigned *obj_to_dlconst = ALLOC_ARR(unsigned, pddl->obj.obj_size);
    int dlvar_size = pddlDatalogPddlMaxVarSize(pddl);
    unsigned *dlvar = ALLOC_ARR(unsigned, dlvar_size);
    initializeDatalog(dl, type_to_dlpred, pred_to_dlpred, obj_to_dlconst,
                      dlvar, dlvar_size, pddl, err);

    for (int ai = 0; ai < pddl->action.action_size; ++ai){
        const pddl_action_t *a = pddl->action.action + ai;
        LOG(err, "Looking for datalog rules in action %s", a->name);
        dlRulesForPre(pddl, old_pred_size, &a->param, a->pre, NULL,
                      dl, type_to_dlpred, pred_to_dlpred, obj_to_dlconst,
                      dlvar, err);

        pddl_fm_const_it_t it;
        const pddl_fm_when_t *w;
        PDDL_FM_FOR_EACH_WHEN(a->eff, &it, w){
            dlRulesForPre(pddl, old_pred_size, &a->param, w->pre, a->pre,
                          dl, type_to_dlpred, pred_to_dlpred, obj_to_dlconst,
                          dlvar, err);
        }
    }

    pddlDatalogToNormalForm(dl, err);
    pddlDatalogCanonicalModel(dl, err);

    for (int pi = 0; pi < old_pred_size; ++pi){
        if (pred[pi].neg < 0)
            continue;
        pddlDatalogFactsFromCanonicalModel(dl, pred_to_dlpred[pred[pi].neg],
                                           dlFactToGroundAtom, &gatoms);
    }

    FREE(type_to_dlpred);
    FREE(pred_to_dlpred);
    FREE(obj_to_dlconst);
    FREE(dlvar);
    pddlDatalogDel(dl);

    // Add all goal atoms
    if (pddl->goal != NULL){
        const pddl_fm_atom_t *atom;
        pddl_fm_const_it_atom_t it;
        PDDL_FM_FOR_EACH_ATOM(pddl->goal, &it, atom){
            if (atom->pred >= old_pred_size){
                pddlGroundAtomsAddAtom(&gatoms, atom, NULL);
            }
        }
    }

    // Extend the initial state with atoms that do not appear in the
    // positive form
    int count_added = 0;
    for (int atom_id = 0; atom_id < gatoms.atom_size; ++atom_id){
        const pddl_ground_atom_t *ga = gatoms.atom[atom_id];
        if (ga->pred >= old_pred_size){
            int neg = ga->pred;
            int pos = pddl->pred.pred[ga->pred].neg_of;
            const pddl_ground_atom_t *pos_atom;
            pos_atom = pddlGroundAtomsFindPred(&gatoms, pos, ga->arg,
                                               ga->arg_size);
            if (pos_atom == NULL){
                pddl_fm_atom_t *a;
                a = pddlFmCreateFactAtom(neg, ga->arg_size, ga->arg);
                pddlFmJuncAdd(pddl->init, &a->fm);
                pddl->pred.pred[a->pred].in_init = pddl_true;
                ++count_added;
            }
        }
    }
    LOG(err, "Number of added NOT- predicates: %d", count_added);

    pddlGroundAtomsFree(&gatoms);
}

static int genAllInitFactsRec(pddl_t *pddl, int pos, int neg,
                              int arg_size, int *arg,
                              const pddl_pred_t *pred, int argi,
                              const pddl_ground_atoms_t *gatoms)
{
    int count = 0;
    pddl_fm_atom_t *a;
    const int *obj;
    int obj_size;

    if (argi == arg_size){
        if (pddlGroundAtomsFindPred(gatoms, pos, arg, arg_size) == NULL){
            a = pddlFmCreateFactAtom(neg, arg_size, arg);
            pddlFmJuncAdd(pddl->init, &a->fm);
            pddl->pred.pred[a->pred].in_init = pddl_true;
            ++count;
        }

        return count;
    }

    obj = pddlTypesObjsByType(&pddl->type, pred->param[argi], &obj_size);
    for (int i = 0; i < obj_size; ++i){
        arg[argi] = obj[i];
        count += genAllInitFactsRec(pddl, pos, neg, arg_size, arg,
                                    pred, argi + 1, gatoms);
    }

    return count;
}

static int genAllInitFacts(pddl_t *pddl, int pos, int neg,
                           const pddl_ground_atoms_t *gatoms, pddl_err_t *err)
{
    const pddl_pred_t *pos_pred = pddl->pred.pred + pos;
    ASSERT(pos_pred->param_size == pddl->pred.pred[neg].param_size);
    int arg[pos_pred->param_size];

    // Recursivelly try all possible objects for each argument
    return genAllInitFactsRec(pddl, pos, neg, pos_pred->param_size, arg,
                              pos_pred, 0, gatoms);
}

static void extendInitialStateExhaustively(pddl_t *pddl, int old_pred_size,
                                           const pred_t *pred, pddl_err_t *err)
{
    pddl_ground_atoms_t gatoms;
    pddlGroundAtomsInit(&gatoms);
    pddlGroundAtomsAddInit(&gatoms, pddl);

    int count = 0;
    for (int pred_id = 0; pred_id < old_pred_size; ++pred_id){
        if (pred[pred_id].neg >= 0){
            count += genAllInitFacts(pddl, pred[pred_id].pos, pred[pred_id].neg,
                                     &gatoms, err);
        }
    }

    pddlGroundAtomsFree(&gatoms);
    LOG(err, "Number of added NOT- predicates: %d", count);
}

int pddlCompileAwayNegativeConditions(pddl_t *pddl,
                                      pddl_bool_t only_dynamic,
                                      pddl_bool_t only_goal,
                                      pddl_bool_t only_relevant_facts_in_init,
                                      pddl_err_t *err)
{
    CTX(err, "Neg-Cond");
    LOG(err, "Cfg: only_dynamic: %s", F_BOOL(only_dynamic));
    LOG(err, "Cfg: only_goal: %s", F_BOOL(only_goal));
    LOG(err, "Cfg: only_relevant_facts_in_init: %s",
        F_BOOL(only_relevant_facts_in_init));

    pred_t pred[pddl->pred.pred_size];
    if (!predArrInit(pred, pddl)){
        LOG(err, "No negative conditions.");
        CTXEND(err);
        return 0;
    }

    pddl_bool_t *pred_in_goal = NULL;
    if (only_goal){
        pred_in_goal = ZALLOC_ARR(pddl_bool_t, pddl->pred.pred_size);
        if (pddl->goal != NULL){
            pddl_fm_const_it_atom_t it;
            const pddl_fm_atom_t *atom;
            PDDL_FM_FOR_EACH_ATOM(pddl->goal, &it, atom)
                pred_in_goal[atom->pred] = pddl_true;
        }
    }

    int count = 0;
    int pred_size = pddl->pred.pred_size;
    for (int pred_id = 0; pred_id < pred_size; ++pred_id){
        ASSERT(pred[pred_id].pos == pred_id);
        if (only_goal && !pred_in_goal[pred_id])
            continue;
        if (only_dynamic && pred[pred_id].is_static)
            continue;
        if (!pred[pred_id].is_neg)
            continue;
        if (pred_id == pddl->pred.eq_pred)
            continue;

        LOG(err, "Compiling away negations of %d:%s | (not (%s ...))",
            pred_id,
            pddl->pred.pred[pred_id].name,
            pddl->pred.pred[pred_id].name);

        pred[pred_id].neg = createNewNotPred(pddl, pred_id);
        LOG(err, "Created new predicate %d:%s",
            pred[pred_id].neg, pddl->pred.pred[pred[pred_id].neg].name);

        compileAwayNegCondition(pddl, pred[pred_id].pos, pred[pred_id].neg);
        LOG(err, "(not (%s ...)) replaced with (%s ...)",
            pddl->pred.pred[pred[pred_id].pos].name,
            pddl->pred.pred[pred[pred_id].neg].name);

        ++count;
    }

    if (pred_in_goal != NULL)
        FREE(pred_in_goal);

    LOG(err, "Extending initial state...");
    if (only_relevant_facts_in_init){
        extendInitialStateUsingDL(pddl, pred_size, pred, err);
    }else{
        extendInitialStateExhaustively(pddl, pred_size, pred, err);
    }
    LOG(err, "Initial state extended.");

    LOG(err, "Compiled away negative conditions of %d predicates", count);
    CTXEND(err);
    return 0;
}
