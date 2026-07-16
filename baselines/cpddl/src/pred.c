/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/pddl.h"
#include "pddl/pred.h"
#include "internal.h"

static const char *eq_name = "=";

void pddlPredFree(pddl_pred_t *pred)
{
    if (pred->param != NULL)
        FREE(pred->param);
    if (pred->name != NULL)
        FREE(pred->name);
}

void pddlPredSetName(pddl_pred_t *pred, const char *name)
{
    if (pred->name != NULL)
        FREE(pred->name);
    pred->name = STRDUP(name);
}

void pddlPredAllocParams(pddl_pred_t *pred, int num_params)
{
    if (pred->param_size != num_params){
        int from = pred->param_size;
        pred->param_size = num_params;
        pred->param = REALLOC_ARR(pred->param, int, pred->param_size);
        for (int i = from; i < pred->param_size; ++i)
            pred->param[i] = -1;
    }
}

int pddlPredSetParamType(pddl_pred_t *pred, int param, int type)
{
    if (param < 0 || param >= pred->param_size)
        return -1;
    pred->param[param] = type;
    return 0;
}

static void addEqPredicate(pddl_preds_t *ps)
{
    pddl_pred_t *p;

    p = pddlPredsAdd(ps);
    p->name = STRDUP(eq_name);
    p->param_size = 2;
    p->param = ZALLOC_ARR(int, 2);
    ps->eq_pred = ps->pred_size - 1;
}

void pddlPredsInitEmpty(pddl_preds_t *ps)
{
    ZEROIZE(ps);
    ps->eq_pred = -1;
    ps->total_cost_func = -1;
}

void pddlPredsInitEq(pddl_preds_t *ps)
{
    pddlPredsInitEmpty(ps);
    addEqPredicate(ps);
}

void pddlPredsInitCopy(pddl_preds_t *dst, const pddl_preds_t *src)
{
    ZEROIZE(dst);
    dst->eq_pred = src->eq_pred;
    dst->total_cost_func = src->total_cost_func;
    dst->pred_size = dst->pred_alloc = src->pred_size;
    dst->pred = ZALLOC_ARR(pddl_pred_t, src->pred_size);
    for (int i = 0; i < src->pred_size; ++i){
        dst->pred[i] = src->pred[i];
        if (dst->pred[i].name != NULL)
            dst->pred[i].name = STRDUP(src->pred[i].name);
        if (dst->pred[i].param != NULL){
            dst->pred[i].param_size = src->pred[i].param_size;
            dst->pred[i].param = ZALLOC_ARR(int, src->pred[i].param_size);
            memcpy(dst->pred[i].param, src->pred[i].param,
                   sizeof(int) * src->pred[i].param_size);
        }
    }
}

void pddlPredsFree(pddl_preds_t *ps)
{
    for (int i = 0; i < ps->pred_size; ++i)
        pddlPredFree(ps->pred + i);
    if (ps->pred != NULL)
        FREE(ps->pred);
}

void pddlPredsSetTotalCostFunc(pddl_preds_t *ps)
{
    ps->total_cost_func = pddlPredsGet(ps, "total-cost");
}

int pddlPredsGet(const pddl_preds_t *ps, const char *name)
{
    for (int i = 0; i < ps->pred_size; ++i){
        if (strcmp(ps->pred[i].name, name) == 0)
            return i;
    }
    return -1;
}

pddl_pred_t *pddlPredsAdd(pddl_preds_t *ps)
{
    pddl_pred_t *p;

    if (ps->pred_size >= ps->pred_alloc){
        if (ps->pred_alloc == 0){
            ps->pred_alloc = 2;
        }else{
            ps->pred_alloc *= 2;
        }
        ps->pred = REALLOC_ARR(ps->pred, pddl_pred_t,
                               ps->pred_alloc);
    }

    p = ps->pred + ps->pred_size++;
    ZEROIZE(p);
    p->id = ps->pred_size - 1;
    p->neg_of = -1;
    return p;
}

pddl_pred_t *pddlPredsAddCopy(pddl_preds_t *ps, int src_id)
{
    pddl_pred_t *dst = pddlPredsAdd(ps);
    const pddl_pred_t *src = ps->pred + src_id;
    int dst_id = dst->id;

    memcpy(dst, src, sizeof(*src));
    dst->id = dst_id;

    if (src->param != NULL){
        dst->param = ALLOC_ARR(int, src->param_size);
        memcpy(dst->param, src->param, sizeof(int) * src->param_size);
    }

    if (src->name != NULL)
        dst->name = STRDUP(src->name);

    return dst;
}

void pddlPredsRemoveLast(pddl_preds_t *ps)
{
    pddl_pred_t *p;

    p = ps->pred + --ps->pred_size;
    pddlPredFree(p);
}

void pddlPredsRemove(pddl_preds_t *ps, const pddl_iset_t *rm_ids,
                     int *remap_out)
{
    ASSERT(ps->eq_pred < 0 || ps->total_cost_func < 0);
    if (remap_out == NULL)
        remap_out = alloca(sizeof(int) * ps->pred_size);

    int rm_size = pddlISetSize(rm_ids);
    int rm_i = 0;
    int ins = 0;
    for (int pi = 0; pi < ps->pred_size; ++pi){
        if (rm_i < rm_size && pddlISetGet(rm_ids, rm_i) == pi){
            remap_out[pi] = -1;
            pddlPredFree(ps->pred + pi);
            ++rm_i;

            if (pi == ps->eq_pred)
                ps->eq_pred = -1;
            if (pi == ps->total_cost_func)
                ps->total_cost_func = -1;

        }else{
            if (pi != ins){
                ps->pred[ins] = ps->pred[pi];
                ps->pred[ins].id = ins;
            }
            remap_out[pi] = ins;
            ++ins;
        }
    }
    ps->pred_size = ins;

    // Fix .neg_of IDs
    for (int pi = 0; pi < ps->pred_size; ++pi){
        if (ps->pred[pi].neg_of >= 0)
            ps->pred[pi].neg_of = remap_out[ps->pred[pi].neg_of];
    }

    if (ps->eq_pred >= 0)
        ps->eq_pred = remap_out[ps->eq_pred];
    if (ps->total_cost_func >= 0)
        ps->total_cost_func = remap_out[ps->total_cost_func];
}

void pddlPredsRemapTypes(pddl_preds_t *ps,
                         const int *type_remap,
                         int *pred_remap)
{
    int ins = 0;
    for (int p = 0; p < ps->pred_size; ++p){
        pddl_pred_t *pred = ps->pred + p;
        int fail = 0;
        for (int parami = 0; parami < pred->param_size; ++parami){
            if (type_remap[pred->param[parami]] == -1){
                fail = 1;
                break;
            }else{
                pred->param[parami] = type_remap[pred->param[parami]];
            }
        }
        if (fail){
            pred_remap[p] = -1;
            pddlPredFree(pred);
        }else{
            ps->pred[ins] = *pred;
            ps->pred[ins].id = ins;
            if (ps->pred[ins].neg_of >= 0)
                ps->pred[ins].neg_of = pred_remap[ps->pred[ins].neg_of];
            pred_remap[p] = ins++;
        }
    }
    ps->pred_size = ins;
}

void pddlPredsPrint(const pddl_preds_t *ps,
                    const char *title, FILE *fout)
{
    // TODO: Rename the function to PrintDebug
    fprintf(fout, "%s[%d]:\n", title, ps->pred_size);
    for (int i = 0; i < ps->pred_size; ++i){
        ASSERT(ps->pred[i].id == i);
        fprintf(fout, "    %s:", ps->pred[i].name);
        for (int j = 0; j < ps->pred[i].param_size; ++j){
            fprintf(fout, " %d", ps->pred[i].param[j]);
        }
        fprintf(fout, " :: read: %d, write: %d, in-init: %d",
                ps->pred[i].read, ps->pred[i].write, ps->pred[i].in_init);
        if (ps->pred[i].neg_of >= 0)
            fprintf(fout, ", neg-of: %s", ps->pred[ps->pred[i].neg_of].name);
        fprintf(fout, "\n");
    }
}

static void printPDDL(const char *t,
                      const pddl_preds_t *ps,
                      const pddl_types_t *ts,
                      FILE *fout)
{
    if (ps->pred_size == 0)
        return;
    fprintf(fout, "(:%s\n", t);
    for (int i = 0; i < ps->pred_size; ++i){
        if (i == ps->eq_pred)
            continue;
        const pddl_pred_t *p = ps->pred + i;
        fprintf(fout, "    (%s", p->name);
        for (int j = 0; j < p->param_size; ++j){
            fprintf(fout, " ?x%d - %s", j, ts->type[p->param[j]].name);
        }
        fprintf(fout, ")\n");
    }
    fprintf(fout, ")\n");
}

void pddlPredsPrintPDDL(const pddl_preds_t *ps,
                        const pddl_types_t *ts,
                        FILE *fout)
{
    printPDDL("predicates", ps, ts, fout);
}

void pddlFuncsPrintPDDL(const pddl_preds_t *ps,
                        const pddl_types_t *ts,
                        FILE *fout)
{
    printPDDL("functions", ps, ts, fout);
}
