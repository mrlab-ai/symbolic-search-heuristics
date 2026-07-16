/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/hfunc.h"
#include "pddl/lp.h"
#include "pddl/pot.h"
#include "pddl/sort.h"
#include "internal.h"

#define LPVAR_UPPER 1E7
#define LPVAR_LOWER -1E20
#define ROUND_EPS 0.001

static int roundOff(double z)
{
    return ceil(z - ROUND_EPS);
}

static int potFltToInt(double pot)
{
    if (pot < 0.)
        return 0;
    if (pot > INT_MAX / 2 || pot > LPVAR_UPPER)
        return PDDL_COST_DEAD_END;
    return roundOff(pot);
}


void pddlPotSolutionInit(pddl_pot_solution_t *sol)
{
    ZEROIZE(sol);
}

void pddlPotSolutionFree(pddl_pot_solution_t *sol)
{
    if (sol->pot != NULL)
        FREE(sol->pot);
    if (sol->op_pot != NULL)
        FREE(sol->op_pot);
}

double pddlPotSolutionEvalFDRStateFlt(const pddl_pot_solution_t *sol,
                                      const pddl_fdr_vars_t *vars,
                                      const int *state)
{
    // Use kahan summation
    double sum = 0.;
    double comp = 0.;
    for (int var = 0; var < vars->var_size; ++var){
        double v = sol->pot[vars->var[var].val[state[var]].global_id];
        double y = v - comp;
        double t = sum + y;
        comp = (t - sum) - y;
        sum = t;
    }
    return sum;
}

int pddlPotSolutionEvalFDRState(const pddl_pot_solution_t *sol,
                                const pddl_fdr_vars_t *vars,
                                const int *state)
{
    return potFltToInt(pddlPotSolutionEvalFDRStateFlt(sol, vars, state));
}

double pddlPotSolutionEvalStripsStateFlt(const pddl_pot_solution_t *sol,
                                         const pddl_iset_t *state)
{
    // Use kahan summation
    double sum = 0.;
    double comp = 0.;
    int fact_id;
    PDDL_ISET_FOR_EACH(state, fact_id){
        double v = sol->pot[fact_id];
        double y = v - comp;
        double t = sum + y;
        comp = (t - sum) - y;
        sum = t;
    }
    return sum;
}

int pddlPotSolutionEvalStripsState(const pddl_pot_solution_t *sol,
                                   const pddl_iset_t *state)
{
    return potFltToInt(pddlPotSolutionEvalStripsStateFlt(sol, state));
}

int pddlPotSolutionRoundHValue(double hvalue)
{
    return potFltToInt(hvalue);
}

void pddlPotSolutionsInit(pddl_pot_solutions_t *sols)
{
    ZEROIZE(sols);
}

void pddlPotSolutionsFree(pddl_pot_solutions_t *sols)
{
    for (int i = 0; i < sols->sol_size; ++i)
        pddlPotSolutionFree(sols->sol + i);
    if (sols->sol != NULL)
        FREE(sols->sol);
}

void pddlPotSolutionsAdd(pddl_pot_solutions_t *sols,
                         const pddl_pot_solution_t *sol)
{
    if (sols->sol_size >= sols->sol_alloc){
        if (sols->sol_alloc == 0)
            sols->sol_alloc = 1;
        sols->sol_alloc *= 2;
        sols->sol = REALLOC_ARR(sols->sol, pddl_pot_solution_t,
                                sols->sol_alloc);
    }

    pddl_pot_solution_t *s = sols->sol + sols->sol_size++;
    pddlPotSolutionInit(s);
    s->pot_size = sol->pot_size;
    if (s->pot_size > 0){
        s->pot = ALLOC_ARR(double, s->pot_size);
        memcpy(s->pot, sol->pot, sizeof(double) * s->pot_size);
    }
    s->objval = sol->objval;
    s->op_pot_size = sol->op_pot_size;
    if (s->op_pot_size > 0){
        s->op_pot = ALLOC_ARR(double, s->op_pot_size);
        memcpy(s->op_pot, sol->op_pot, sizeof(double) * s->op_pot_size);
    }
}

int pddlPotSolutionsEvalMaxFDRState(const pddl_pot_solutions_t *sols,
                                    const pddl_fdr_vars_t *vars,
                                    const int *fdr_state)
{
    int h = 0;
    for (int i = 0; i < sols->sol_size; ++i){
        int h1 = pddlPotSolutionEvalFDRState(sols->sol + i, vars, fdr_state);
        h = PDDL_MAX(h, h1);
    }
    return h;
}





static pddl_pot_constr_t *constrNew(void)
{
    return ZALLOC(pddl_pot_constr_t);
}

static void constrInit(pddl_pot_constr_t *c)
{
    pddlISetInit(&c->plus);
    pddlISetInit(&c->minus);
    c->rhs = 0;
    c->sense = 'L';
}

static void constrFree(pddl_pot_constr_t *c)
{
    pddlISetFree(&c->plus);
    pddlISetFree(&c->minus);
}

static void constrDel(pddl_pot_constr_t *c)
{
    constrFree(c);
    FREE(c);
}

static pddl_pot_constr_t *constrsAdd(pddl_pot_constrs_t *cs)
{
    if (cs->c_size == cs->c_alloc){
        if (cs->c_alloc == 0)
            cs->c_alloc = 1;
        cs->c_alloc *= 2;
        cs->c = REALLOC_ARR(cs->c, pddl_pot_constr_t, cs->c_alloc);
    }

    pddl_pot_constr_t *c = cs->c + cs->c_size++;
    constrInit(c);
    return c;
}

static void constrsFree(pddl_pot_constrs_t *cs)
{
    for (int i = 0; i < cs->c_size; ++i)
        constrFree(cs->c + i);
    if (cs->c != NULL)
        FREE(cs->c);
}

static pddl_htable_key_t maxpotComputeHash(const pddl_pot_maxpot_t *m)
{
    return pddlCityHash_64(m->var, sizeof(pddl_pot_maxpot_var_t) * m->var_size);
}

static pddl_htable_key_t maxpotHTableHash(const pddl_list_t *key, void *_)
{
    const pddl_pot_maxpot_t *m = PDDL_LIST_ENTRY(key, pddl_pot_maxpot_t, htable);
    return m->hkey;
}

static int maxpotHTableEq(const pddl_list_t *key1, const pddl_list_t *key2, void *_)
{
    const pddl_pot_maxpot_t *m1 = PDDL_LIST_ENTRY(key1, pddl_pot_maxpot_t, htable);
    const pddl_pot_maxpot_t *m2 = PDDL_LIST_ENTRY(key2, pddl_pot_maxpot_t, htable);
    if (m1->var_size != m2->var_size)
        return 0;
    return memcmp(m1->var, m2->var, sizeof(pddl_pot_maxpot_var_t) * m1->var_size) == 0;
}

static void maxpotsInit(pddl_pot_maxpots_t *m, int num_mgroups)
{
    int segm_size = PDDL_MAX(num_mgroups, 8) * sizeof(pddl_pot_maxpot_t);
    m->maxpot_size = 0;
    m->maxpot = pddlSegmArrNew(sizeof(pddl_pot_maxpot_t), segm_size);
    m->htable = pddlHTableNew(maxpotHTableHash, maxpotHTableEq, NULL);
}

static void maxpotsFree(pddl_pot_maxpots_t *mp)
{
    if (mp->htable != NULL)
        pddlHTableDel(mp->htable);
    for (int mi = 0; mi < mp->maxpot_size; ++mi){
        pddl_pot_maxpot_t *m = pddlSegmArrGet(mp->maxpot, mi);
        if (m->var != NULL)
            FREE(m->var);
    }
    if (mp->maxpot != NULL)
        pddlSegmArrDel(mp->maxpot);
}

static int maxpotGet(pddl_pot_t *pot,
                     const pddl_iset_t *set,
                     const int *count)
{
    pddl_pot_maxpots_t *mpot = &pot->maxpot;
    pddl_pot_maxpot_t *m = pddlSegmArrGet(mpot->maxpot, mpot->maxpot_size);

    m->var_size = pddlISetSize(set);
    m->var = ZALLOC_ARR(pddl_pot_maxpot_var_t, m->var_size);
    for (int i = 0; i < m->var_size; ++i){
        m->var[i].var_id = pddlISetGet(set, i);
        if (count != NULL)
            m->var[i].count = count[m->var[i].var_id];
    }
    m->hkey = maxpotComputeHash(m);
    pddlListInit(&m->htable);

    pddl_list_t *found;
    found = pddlHTableInsertUnique(mpot->htable, &m->htable);
    if (found == NULL){
        m->id = mpot->maxpot_size++;
        m->maxpot_id = pot->var_size++;
        return m->maxpot_id;

    }else{
        if (m->var != NULL)
            FREE(m->var);

        m = PDDL_LIST_ENTRY(found, pddl_pot_maxpot_t, htable);
        return m->maxpot_id;
    }
}

static void hsetToVarSet(pddl_pot_t *pot,
                         const pddl_set_iset_t *hset,
                         pddl_iset_t *var_set)
{
    int *count = ZALLOC_ARR(int, pot->var_size);
    const pddl_iset_t *set;
    PDDL_SET_ISET_FOR_EACH(hset, set){
        int fact_id;
        PDDL_ISET_FOR_EACH(set, fact_id)
            count[fact_id] += 1;
    }

    PDDL_SET_ISET_FOR_EACH(hset, set){
        if (pddlISetSize(set) == 1){
            int fact_id = pddlISetGet(set, 0);
            ASSERT(count[fact_id] == 1);
            pddlISetAdd(var_set, fact_id);
        }else{
            int maxpot_id = maxpotGet(pot, set, count);
            pddlISetAdd(var_set, maxpot_id);
        }
    }

    if (count != NULL)
        FREE(count);
}

static void addOp(pddl_pot_t *pot, const pddl_strips_op_t *op)
{
    pddl_set_iset_t hset;
    pddlSetISetInit(&hset);

    if (pddlDisambiguate(&pot->disamb, &op->pre, &op->add_eff, 0,
                         pot->disamb_single_fact, &hset, NULL) < 0){
        // Skip unreachable operators
        pddlSetISetFree(&hset);
        return;
    }

    pddl_pot_constr_t *c = constrNew();
    hsetToVarSet(pot, &hset, &c->plus);
    pddlISetUnion(&c->minus, &op->add_eff);
    c->rhs = op->cost;
    c->sense = 'L';

    PDDL_ISET(inter);
    pddlISetIntersect2(&inter, &c->plus, &c->minus);
    pddlISetMinus(&c->minus, &inter);
    pddlISetMinus(&c->plus, &inter);
    pddlISetFree(&inter);

    pddlSetISetFree(&hset);

    if (pddlISetSize(&c->plus) == 0 && pddlISetSize(&c->minus) == 0){
        constrDel(c);
        return;
    }

    pot->c_op[op->id] = c;
}

static int addGoal(pddl_pot_t *pot, const pddl_iset_t *goal)
{
    pddl_set_iset_t hset;
    pddlSetISetInit(&hset);

    if (pddlDisambiguate(&pot->disamb, goal, NULL, 0,
                         pot->disamb_single_fact, &hset, NULL) < 0){
        pddlSetISetFree(&hset);
        return -1;
    }

    pddl_pot_constr_t *c = constrsAdd(&pot->c_goal);
    hsetToVarSet(pot, &hset, &c->plus);
    c->rhs = 0;
    c->sense = 'L';

    pddlSetISetFree(&hset);
    return 0;
}


static int init(pddl_pot_t *pot,
                const pddl_mg_strips_t *mg_strips,
                const pddl_mutex_pairs_t *mutex,
                pddl_bool_t single_fact_disamb)
{
    ZEROIZE(pot);
    pot->mg_strips = mg_strips;
    maxpotsInit(&pot->maxpot, mg_strips->mg.mgroup_size);
    pddlDisambiguateInit(&pot->disamb, mg_strips->strips.fact.fact_size,
                         mutex, &mg_strips->mg);
    pot->disamb_single_fact = single_fact_disamb;

    pot->var_size = mg_strips->strips.fact.fact_size;
    pot->fact_var_size = pot->var_size;

    pot->op_size = mg_strips->strips.op.op_size;
    pot->c_op = ZALLOC_ARR(pddl_pot_constr_t *, pot->op_size);

    for (int op_id = 0; op_id < mg_strips->strips.op.op_size; ++op_id)
        addOp(pot, mg_strips->strips.op.op[op_id]);

    if (addGoal(pot, &mg_strips->strips.goal) != 0){
        pddlPotFree(pot);
        return -1;
    }

    pot->fact_obj = ZALLOC_ARR(double, pot->fact_var_size);

    // TODO: ?? sortConstrs(pot);
    return 0;
}

int pddlPotInit(pddl_pot_t *pot,
                const pddl_mg_strips_t *mg_strips,
                const pddl_mutex_pairs_t *mutex)
{
    return init(pot, mg_strips, mutex, pddl_false);
}

int pddlPotInitSingleFactDisamb(pddl_pot_t *pot,
                                const pddl_mg_strips_t *mg_strips,
                                const pddl_mutex_pairs_t *mutex)
{
    return init(pot, mg_strips, mutex, pddl_true);
}

int pddlPotInitFDR(pddl_pot_t *pot, const pddl_fdr_t *fdr)
{
    pddl_mg_strips_t *mg_strips = ZALLOC(pddl_mg_strips_t);
    pddlMGStripsInitFDR(mg_strips, fdr);

    pddl_mutex_pairs_t mutex;
    pddlMutexPairsInitStrips(&mutex, &mg_strips->strips);
    pddlMutexPairsAddFDRVars(&mutex, &fdr->var);

    int ret = pddlPotInit(pot, mg_strips, &mutex);
    if (ret == 0)
        pot->mg_strips_own = pddl_true;

    pddlMutexPairsFree(&mutex);

    return ret;
}

void pddlPotFree(pddl_pot_t *pot)
{
    pddlDisambiguateFree(&pot->disamb);
    if (pot->fact_obj != NULL)
        FREE(pot->fact_obj);

    if (pot->c_op != NULL){
        for (int oi = 0; oi < pot->op_size; ++oi){
            if (pot->c_op[oi] != NULL)
                constrDel(pot->c_op[oi]);
        }
        FREE(pot->c_op);
    }

    if (pot->c_op_pre_state != NULL){
        for (int oi = 0; oi < pot->op_size; ++oi){
            if (pot->c_op_pre_state[oi] != NULL)
                constrDel(pot->c_op_pre_state[oi]);
        }
        FREE(pot->c_op_pre_state);
    }
    if (pot->c_op_pre_state_enabled != NULL)
        FREE(pot->c_op_pre_state_enabled);

    constrsFree(&pot->c_goal);

    if (pot->c_lb != NULL)
        constrDel(pot->c_lb);

    maxpotsFree(&pot->maxpot);

    if (pot->start_pot != NULL)
        FREE(pot->start_pot);

    if (pot->mg_strips_own && pot->mg_strips != NULL){
        pddl_mg_strips_t *mgs = (pddl_mg_strips_t *)pot->mg_strips;
        pddlMGStripsFree(mgs);
        FREE(mgs);
    }
}

void pddlPotSetObj(pddl_pot_t *pot, const double *coef)
{
    memcpy(pot->fact_obj, coef, sizeof(double) * pot->fact_var_size);
}

void pddlPotSetObjFDRState(pddl_pot_t *pot,
                           const pddl_fdr_vars_t *vars,
                           const int *state)
{
    ZEROIZE_ARR(pot->fact_obj, pot->fact_var_size);
    for (int var_id = 0; var_id < vars->var_size; ++var_id)
        pot->fact_obj[vars->var[var_id].val[state[var_id]].global_id] = 1.;
}

void pddlPotSetObjFDRAllSyntacticStates(pddl_pot_t *pot,
                                        const pddl_fdr_vars_t *vars)
{
    ZEROIZE_ARR(pot->fact_obj, pot->fact_var_size);
    for (int var_id = 0; var_id < vars->var_size; ++var_id){
        double c = 1. / vars->var[var_id].val_size;
        for (int val = 0; val < vars->var[var_id].val_size; ++val){
            pot->fact_obj[vars->var[var_id].val[val].global_id] = c;
        }
    }
}

void pddlPotSetObjStripsState(pddl_pot_t *pot, const pddl_iset_t *state)
{
    ZEROIZE_ARR(pot->fact_obj, pot->fact_var_size);
    int fact_id;
    PDDL_ISET_FOR_EACH(state, fact_id)
        pot->fact_obj[fact_id] = 1.;
}

void pddlPotSetLowerBoundConstr(pddl_pot_t *pot,
                                const pddl_iset_t *vars,
                                double rhs)
{
    if (pot->c_lb != NULL)
        constrDel(pot->c_lb);
    pot->c_lb = constrNew();
    pddlISetUnion(&pot->c_lb->plus, vars);
    pot->c_lb->rhs = rhs;
    pot->c_lb->sense = 'G';
}

void pddlPotResetLowerBoundConstr(pddl_pot_t *pot)
{
    if (pot->c_lb != NULL)
        constrDel(pot->c_lb);
    pot->c_lb = NULL;
}

double pddlPotGetLowerBoundConstrRHS(const pddl_pot_t *pot)
{
    if (pot->c_lb == NULL)
        return 0.;
    return pot->c_lb->rhs;
}

void pddlPotDecreaseLowerBoundConstrRHS(pddl_pot_t *pot, double decrease)
{
    if (pot->c_lb == NULL)
        return;
    pot->c_lb->rhs -= decrease;
}

void pddlPotSetMinOpConsistencyConstr(pddl_pot_t *pot, int op_id)
{
    if (pot->c_op_pre_state == NULL)
        pot->c_op_pre_state = ZALLOC_ARR(pddl_pot_constr_t *, pot->op_size);
    if (pot->c_op_pre_state_enabled == NULL)
        pot->c_op_pre_state_enabled = ZALLOC_ARR(pddl_bool_t, pot->op_size);

    pot->c_op_pre_state_enabled[op_id] = pddl_true;

    // Do not re-compute the constraint
    if (pot->c_op_pre_state[op_id] != NULL)
        return;

    const pddl_strips_op_t *op = pot->mg_strips->strips.op.op[op_id];
    pddl_set_iset_t hset;
    pddlSetISetInit(&hset);

    if (pddlDisambiguate(&pot->disamb, &op->pre, NULL, 0,
                         pot->disamb_single_fact, &hset, NULL) < 0){
        // Skip unreachable operators
        pot->c_op_pre_state_enabled[op_id] = pddl_false;
        pddlSetISetFree(&hset);
        return;
    }

    pddl_pot_constr_t *c = constrNew();
    c->rhs = op->cost;
    c->sense = 'L';
    hsetToVarSet(pot, &hset, &c->plus);
    pddlISetUnion(&c->plus, &op->pre);

    pddlSetISetFree(&hset);

    pot->c_op_pre_state[op_id] = c;
}

void pddlPotDisableMinOpConsistencyConstr(pddl_pot_t *pot, int op_id)
{
    if (pot->c_op_pre_state_enabled != NULL)
        pot->c_op_pre_state_enabled[op_id] = pddl_false;
}

void pddlPotSetMinOpConsistencyConstrAll(pddl_pot_t *pot)
{
    for (int op_id = 0; op_id < pot->op_size; ++op_id)
        pddlPotSetMinOpConsistencyConstr(pot, op_id);
}

void pddlPotDisableMinOpConsistencyConstrAll(pddl_pot_t *pot)
{
    for (int op_id = 0; op_id < pot->op_size; ++op_id)
        pddlPotDisableMinOpConsistencyConstr(pot, op_id);
}

void pddlPotSetStartSolution(pddl_pot_t *pot, const pddl_pot_solution_t *sol)
{
    PANIC_IF(pot->fact_var_size != sol->pot_size,
             "Incompatible potential function with the input planning task."
             " (num fact LP variables: %d, num potentials: %d",
             pot->fact_var_size, sol->pot_size);
    if (pot->start_pot != NULL)
        FREE(pot->start_pot);
    pot->start_pot = ALLOC_ARR(double, pot->fact_var_size);
    memcpy(pot->start_pot, sol->pot, sizeof(double) * pot->fact_var_size);
}

void pddlPotResetStartSolution(pddl_pot_t *pot)
{
    if (pot->start_pot != NULL)
        FREE(pot->start_pot);
    pot->start_pot = NULL;
}

static int addLPConstr(pddl_lp_t *lp, const pddl_pot_constr_t *c)
{
    int row = pddlLPNumRows(lp);
    pddlLPAddRows(lp, 1, &c->rhs, &c->sense);

    int var;
    PDDL_ISET_FOR_EACH(&c->plus, var)
        pddlLPSetCoef(lp, row, var, 1);
    PDDL_ISET_FOR_EACH(&c->minus, var)
        pddlLPSetCoef(lp, row, var, -1);
    return row;
}

static void addLPBinarySwitch(pddl_lp_t *lp,
                              const pddl_pot_constr_t *c1,
                              const pddl_pot_constr_t *c2)
{
    int indicator = pddlLPNumCols(lp);
    pddlLPAddCols(lp, 1);
    pddlLPSetVarBinary(lp, indicator);
    pddlLPSetObj(lp, indicator, 0);

    int row = addLPConstr(lp, c1);
    pddlLPSetIndicator(lp, row, indicator, pddl_false);

    row = addLPConstr(lp, c2);
    pddlLPSetIndicator(lp, row, indicator, pddl_true);
}

static void addLPConstrs(pddl_lp_t *lp, const pddl_pot_constrs_t *cs)
{
    if (cs == NULL)
        return;

    for (int ci = 0; ci < cs->c_size; ++ci)
        addLPConstr(lp, cs->c + ci);
}

static void addLPOpConsistency(pddl_lp_t *lp, const pddl_pot_t *pot)
{
    if (pot->c_op == NULL)
        return;

    for (int op_id = 0; op_id < pot->op_size; ++op_id){
        const pddl_pot_constr_t *c = pot->c_op[op_id];
        if (c == NULL)
            continue;

        const pddl_pot_constr_t *pre_state = NULL;
        if (pot->c_op_pre_state != NULL
                && pot->c_op_pre_state_enabled != NULL
                && pot->c_op_pre_state_enabled[op_id]){
            pre_state = pot->c_op_pre_state[op_id];
        }

        if (pre_state == NULL){
            addLPConstr(lp, c);
        }else{
            addLPBinarySwitch(lp, c, pre_state);
        }
    }
}

static void setMaxpotConstr(pddl_lp_t *lp, const pddl_pot_maxpot_t *maxpot)
{
    for (int i = 0; i < maxpot->var_size; ++i){
        double coef = 1.;
        if (maxpot->var[i].count > 1)
            coef = 1. / maxpot->var[i].count;

        int row = pddlLPNumRows(lp);
        double rhs = 0.;
        char sense = 'L';
        pddlLPAddRows(lp, 1, &rhs, &sense);
        pddlLPSetCoef(lp, row, maxpot->var[i].var_id, coef);
        pddlLPSetCoef(lp, row, maxpot->maxpot_id, -1.);
    }
}

static void addLPMaxpotConstrs(pddl_lp_t *lp, const pddl_pot_maxpots_t *mp)
{
    for (int mi = 0; mi < mp->maxpot_size; ++mi){
        const pddl_pot_maxpot_t *m = pddlSegmArrGet(mp->maxpot, mi);
        setMaxpotConstr(lp, m);
    }
}

static void addLPOpPotConstr(pddl_lp_t *lp,
                             const pddl_pot_t *pot,
                             int op_id,
                             int *op_pot_var)
{
    if (pot->c_op == NULL || pot->c_op[op_id] == NULL)
        return;

    int var = pddlLPNumCols(lp);
    pddlLPAddCols(lp, 1);
    pddlLPSetVarRange(lp, var, INT_MIN / 2, INT_MAX / 2);
    pddlLPSetVarInt(lp, var);
    pddlLPSetObj(lp, var, 0);

    const pddl_pot_constr_t *c = pot->c_op[op_id];
    int row = addLPConstr(lp, c);
    pddlLPSetRHS(lp, row, 0, 'E');
    pddlLPSetCoef(lp, row, var, 1);

    if (op_pot_var != NULL)
        *op_pot_var = var;
}

static int *addLPOpPotConstrs(pddl_lp_t *lp, const pddl_pot_t *pot)
{
    if (pot->c_op == NULL)
        return NULL;

    int *op_pot_vars = ALLOC_ARR(int, pot->op_size);
    for (int oi = 0; oi < pot->op_size; ++oi){
        op_pot_vars[oi] = -1;
        addLPOpPotConstr(lp, pot, oi, op_pot_vars + oi);
    }
    return op_pot_vars;
}

static double constrLHS(const pddl_pot_t *pot,
                        const pddl_pot_constr_t *c,
                        const double *w)
{
    // Use kahan summation
    double sum = 0.;
    double comp = 0.;
    int var;
    PDDL_ISET_FOR_EACH(&c->plus, var){
        double y = w[var] - comp;
        double t = sum + y;
        comp = (t - sum) - y;
        sum = t;
    }
    PDDL_ISET_FOR_EACH(&c->minus, var){
        double y = -w[var] - comp;
        double t = sum + y;
        comp = (t - sum) - y;
        sum = t;
    }

    return sum;
}


static void storeOpPot(pddl_lp_t *lp,
                       const pddl_pot_t *pot,
                       const pddl_pot_solve_config_t *pot_cfg,
                       const double *obj,
                       const int *op_pot_vars,
                       pddl_pot_solution_t *sol)
{
    if (pot->c_op == NULL)
        return;

    sol->op_pot_size = pot->op_size;
    sol->op_pot = ZALLOC_ARR(double, pot->op_size);
    for (int op_id = 0; op_id < pot->op_size; ++op_id){
        const pddl_pot_constr_t *c = pot->c_op[op_id];
        if (c == NULL)
            continue;

        if (pot_cfg->op_pot_real){
            sol->op_pot[op_id] = -constrLHS(pot, c, obj);
        }else{
            ASSERT(op_pot_vars != NULL);
            double oval = obj[op_pot_vars[op_id]];
            oval = round(oval);
            if (oval > PDDL_COST_MAX)
                oval = PDDL_COST_MAX;
            if (oval < PDDL_COST_MIN)
                oval = PDDL_COST_MIN;
            ASSERT(oval == (int)oval);
            sol->op_pot[op_id] = (int)oval;
        }
    }
}

int pddlPotSolve(const pddl_pot_t *pot,
                 const pddl_pot_solve_config_t *pot_cfg,
                 pddl_pot_solution_t *sol,
                 pddl_err_t *err)
{
    int ret = 0;

    ZEROIZE(sol);

    pddl_lp_config_t cfg = PDDL_LP_CONFIG_INIT;
    cfg.maximize = 1;
    cfg.rows = 0;
    cfg.cols = pot->var_size;
    cfg.tune_potential = 1;
    if (pot_cfg->op_pot && !pot_cfg->op_pot_real)
        cfg.tune_int_operator_potential = 1;
    if (pot_cfg->lp_time_limit > 0.f)
        cfg.time_limit = pot_cfg->lp_time_limit;
    pddl_lp_t *lp = pddlLPNew(&cfg, err);

    // Initialize variables
    for (int i = 0; i < pot->var_size; ++i){
        if (pot_cfg->use_ilp)
            pddlLPSetVarInt(lp, i);
        // TODO: Move lower and upper bounds as members of pddl_pot_t
        pddlLPSetVarRange(lp, i, LPVAR_LOWER, LPVAR_UPPER);

        // Set objective function
        if (i < pot->fact_var_size){
            pddlLPSetObj(lp, i, pot->fact_obj[i]);
        }else{
            pddlLPSetObj(lp, i, 0.);
        }

        if (pot->start_pot != NULL && i < pot->fact_var_size)
            pddlLPSetColStart(lp, i, pot->start_pot[i]);
    }


    // Add consistency constraints
    addLPOpConsistency(lp, pot);
    // Add goal constraints
    addLPConstrs(lp, &pot->c_goal);
    // Add lower bound constraint
    if (pot->c_lb != NULL)
        addLPConstr(lp, pot->c_lb);
    // Add maxpot constraints
    addLPMaxpotConstrs(lp, &pot->maxpot);

    // Set constrains enforcing integer operator potentials.
    // The array op_pot_vars maps each operator ID to the correspond LP
    // integer variable.
    int *op_pot_vars = NULL;
    if (pot_cfg->op_pot && !pot_cfg->op_pot_real)
        op_pot_vars = addLPOpPotConstrs(lp, pot);

    int var_size = pddlLPNumCols(lp);
    pddl_lp_solution_t lpsol;
    lpsol.var_val = ZALLOC_ARR(double, var_size);

    if (pddlLPSolve(lp, &lpsol, err) == PDDL_LP_STATUS_ERR){
        sol->error = pddl_true;
        FREE(lpsol.var_val);
        pddlLPDel(lp);
        TRACE_RET(err, -1);
    }

    sol->found = lpsol.solved;
    sol->suboptimal = lpsol.solved_suboptimally;
    sol->timed_out = lpsol.timed_out;
    ret = -1;

    if (lpsol.solved){
        sol->objval = lpsol.obj_val;
        sol->pot_size = pot->fact_var_size;
        sol->pot = ALLOC_ARR(double, sol->pot_size);
        memcpy(sol->pot, lpsol.var_val, sizeof(double) * sol->pot_size);

        if (pot_cfg->op_pot)
            storeOpPot(lp, pot, pot_cfg, lpsol.var_val, op_pot_vars, sol);

        ret = 0;
    }

    if (op_pot_vars != NULL)
        FREE(op_pot_vars);
    FREE(lpsol.var_val);
    pddlLPDel(lp);

    return ret;
}
