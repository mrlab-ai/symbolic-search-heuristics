/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "internal.h"
#include "pddl/sort.h"
#include "pddl/fdr_part_state.h"


static int factsCmp(const void *a, const void *b, void *_)
{
    const pddl_fdr_fact_t *f1 = a;
    const pddl_fdr_fact_t *f2 = b;
    int cmp = f1->var - f2->var;
    if (cmp == 0)
        cmp = f1->val - f2->val;
    return cmp;
}

static void sortFacts(pddl_fdr_part_state_t *ps)
{
    pddlSort(ps->fact, ps->fact_size, sizeof(pddl_fdr_fact_t), factsCmp, NULL);
}

void pddlFDRPartStateInit(pddl_fdr_part_state_t *ps)
{
    ZEROIZE(ps);
}

void pddlFDRPartStateInitCopy(pddl_fdr_part_state_t *dst,
                              const pddl_fdr_part_state_t *src)
{
    dst->fact_size = src->fact_size;
    dst->fact_alloc = src->fact_alloc;
    ASSERT(dst->fact_alloc >= dst->fact_size);
    dst->fact = ALLOC_ARR(pddl_fdr_fact_t, src->fact_alloc);
    memcpy(dst->fact, src->fact, sizeof(*dst->fact) * dst->fact_size);
}

void pddlFDRPartStateFree(pddl_fdr_part_state_t *ps)
{
    if (ps->fact != NULL)
        FREE(ps->fact);
}

void pddlFDRPartStateSet(pddl_fdr_part_state_t *ps, int var, int val)
{
    for (int i = 0; i < ps->fact_size; ++i){
        if (ps->fact[i].var == var){
            ps->fact[i].val = val;
            return;
        }
    }

    if (ps->fact_alloc == ps->fact_size){
        if (ps->fact_alloc == 0)
            ps->fact_alloc = 1;
        ps->fact_alloc *= 2;
        ps->fact = REALLOC_ARR(ps->fact, pddl_fdr_fact_t, ps->fact_alloc);
    }

    ps->fact[ps->fact_size].var = var;
    ps->fact[ps->fact_size].val = val;
    ++ps->fact_size;
    for (int i = ps->fact_size - 1; i > 0; --i){
        if (ps->fact[i - 1].var > var){
            ps->fact[i].var = ps->fact[i - 1].var;
            ps->fact[i].val = ps->fact[i - 1].val;
            ps->fact[i - 1].var = var;
            ps->fact[i - 1].val = val;
        }
    }
}

void pddlFDRPartStateUnset(pddl_fdr_part_state_t *ps, int var)
{
    int c;
    for (c = 0; c < ps->fact_size && ps->fact[c].var < var; ++c);
    if (c == ps->fact_size || ps->fact[c].var != var)
        return;
    for (++c; c < ps->fact_size; ++c)
        ps->fact[c - 1] = ps->fact[c];
    --ps->fact_size;
}

int pddlFDRPartStateGet(const pddl_fdr_part_state_t *ps, int var)
{
    for (int i = 0; i < ps->fact_size && i <= var; ++i){
        if (ps->fact[i].var == var)
            return ps->fact[i].val;
    }
    return -1;
}

pddl_bool_t pddlFDRPartStateIsSet(const pddl_fdr_part_state_t *ps, int var)
{
    return pddlFDRPartStateGet(ps, var) >= 0;
}

pddl_bool_t pddlFDRPartStateIsConsistentWithState(const pddl_fdr_part_state_t *ps,
                                                  const int *state)
{
    for (int i = 0; i < ps->fact_size; ++i){
        if (state[ps->fact[i].var] != ps->fact[i].val)
            return pddl_false;
    }
    return pddl_true;
}

pddl_bool_t pddlFDRPartStateIsConsistentWithPartState(const pddl_fdr_part_state_t *ps1,
                                                      const pddl_fdr_part_state_t *ps2)
{
    int i2 = 0;
    for (int i1 = 0; i1 < ps1->fact_size; ++i1){
        int var1 = ps1->fact[i1].var;
        for (; i2 < ps2->fact_size && ps2->fact[i2].var < var1; ++i2);
        if (i2 >= ps2->fact_size || ps2->fact[i2].var != var1)
            return pddl_false;
        if (ps1->fact[i1].val != ps2->fact[i2].val)
            return pddl_false;
    }
    return pddl_true;
}

int pddlFDRPartStateStateIntersectionSize(const pddl_fdr_part_state_t *ps,
                                          const int *state)
{
    int count = 0;
    for (int i = 0; i < ps->fact_size; ++i){
        if (state[ps->fact[i].var] == ps->fact[i].val)
            count++;
    }
    return count;
}

void pddlFDRPartStateApplyToState(const pddl_fdr_part_state_t *ps, int *state)
{
    for (int i = 0; i < ps->fact_size; ++i)
        state[ps->fact[i].var] = ps->fact[i].val;
}

int pddlFDRPartStateCmp(const pddl_fdr_part_state_t *p1,
                        const pddl_fdr_part_state_t *p2)
{
    int cmp = p1->fact_size - p2->fact_size;
    for (int i = 0; i < p1->fact_size && cmp == 0; ++i)
        cmp = p1->fact[i].var - p2->fact[i].var;
    for (int i = 0; i < p1->fact_size && cmp == 0; ++i)
        cmp = p1->fact[i].val - p2->fact[i].val;
    return cmp;
}

void pddlFDRPartStateRemapFacts(pddl_fdr_part_state_t *ps,
                                const pddl_fdr_vars_remap_t *remap)
{
    int ins = 0;
    for (int i = 0; i < ps->fact_size; ++i){
        pddl_fdr_fact_t *fact = ps->fact + i;
        if (remap->remap[fact->var][fact->val] != NULL){
            const pddl_fdr_val_t *v = remap->remap[fact->var][fact->val];
            ASSERT(v != NULL);
            fact->var = v->var_id;
            fact->val = v->val_id;
            ps->fact[ins++] = *fact;
        }
    }
    ps->fact_size = ins;
}

void pddlFDRPartStateRemapVars(pddl_fdr_part_state_t *ps, const int *remap)
{
    for (int i = 0; i < ps->fact_size; ++i)
        ps->fact[i].var = remap[ps->fact[i].var];
    sortFacts(ps);
}

void pddlFDRPartStateToGlobalIDs(const pddl_fdr_part_state_t *ps,
                                 const pddl_fdr_vars_t *vars,
                                 pddl_iset_t *global_ids)
{
    for (int i = 0; i < ps->fact_size; ++i){
        const pddl_fdr_fact_t *f = ps->fact + i;
        pddlISetAdd(global_ids, vars->var[f->var].val[f->val].global_id);
    }
}

void pddlFDRPartStateMinus(pddl_fdr_part_state_t *a,
                           const pddl_fdr_part_state_t *b)
{
    // TODO: Can be implemented in a linear time, not quadratic
    int ins = 0;
    for (int i = 0; i < a->fact_size; ++i){
        int val = pddlFDRPartStateGet(b, a->fact[i].var);
        if (val != a->fact[i].val)
            a->fact[ins++] = a->fact[i];
    }
    a->fact_size = ins;
}
