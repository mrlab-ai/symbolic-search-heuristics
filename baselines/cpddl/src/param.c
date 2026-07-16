/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/param.h"
#include "internal.h"

void pddlParamInit(pddl_param_t *param)
{
    ZEROIZE(param);
    param->inherit = -1;
}

void pddlParamInitCopy(pddl_param_t *dst, const pddl_param_t *src)
{
    *dst = *src;
    if (dst->name != NULL)
        dst->name = STRDUP(src->name);
}

void pddlParamsInit(pddl_params_t *params)
{
    ZEROIZE(params);
}

void pddlParamsFree(pddl_params_t *params)
{
    for (int i = 0; i < params->param_size; ++i){
        if (params->param[i].name != NULL)
            FREE(params->param[i].name);
    }
    if (params->param != NULL)
        FREE(params->param);
}

pddl_param_t *pddlParamsAdd(pddl_params_t *params)
{
    return pddlParamsAddCopy(params, NULL);
}

pddl_param_t *pddlParamsAddCopy(pddl_params_t *params, const pddl_param_t *p)
{
    pddl_param_t *param;

    if (params->param_size >= params->param_alloc){
        if (params->param_alloc == 0)
            params->param_alloc = 1;
        params->param_alloc *= 2;
        params->param = REALLOC_ARR(params->param, pddl_param_t,
                                    params->param_alloc);
    }

    param = params->param + params->param_size++;
    if (p != NULL){
        pddlParamInitCopy(param, p);
    }else{
        pddlParamInit(param);
    }
    return param;
}

void pddlParamsInitCopy(pddl_params_t *dst, const pddl_params_t *src)
{
    dst->param_size = dst->param_alloc = src->param_size;
    dst->param = ALLOC_ARR(pddl_param_t, dst->param_alloc);
    for (int i = 0; i < dst->param_size; ++i)
        pddlParamInitCopy(dst->param + i, src->param + i);
}

int pddlParamsGetId(const pddl_params_t *param, const char *name)
{
    for (int i = 0; i < param->param_size; ++i){
        if (strcmp(name, param->param[i].name) == 0)
            return i;
    }

    return -1;
}

void pddlParamsInherit(pddl_params_t *params, const pddl_params_t *parent)
{
    for (int pari = 0; pari < parent->param_size; ++pari){
        const pddl_param_t *par = parent->param + pari;
        if (pddlParamsGetId(params, par->name) < 0){
            pddl_param_t *p = pddlParamsAddCopy(params, par);
            p->inherit = pari;
        }
    }
}

void pddlParamsRemap(pddl_params_t *params, const int *remap)
{
    for (int i = 0; i < params->param_size; ++i){
        if (remap[i] == -1){
            if (params->param[i].name != NULL)
                FREE(params->param[i].name);
            params->param[i].name = NULL;
        }
    }

    int max_id = -1;
    for (int i = 0; i < params->param_size; ++i){
        if (remap[i] != -1){
            params->param[remap[i]] = params->param[i];
            max_id = PDDL_MAX(max_id, remap[i]);
        }
    }
    params->param_size = max_id + 1;
}

void pddlParamsPrint(const pddl_params_t *params, FILE *fout)
{
    int i;

    for (i = 0; i < params->param_size; ++i){
        if (i > 0)
            fprintf(fout, " ");
        if (params->param[i].is_agent)
            fprintf(fout, "A:");
        if (params->param[i].inherit >= 0)
            fprintf(fout, "I[%d]:", params->param[i].inherit);
        fprintf(fout, "%s:%d", params->param[i].name, params->param[i].type);
    }
}

void pddlParamsPrintPDDL(const pddl_params_t *params,
                         const pddl_types_t *ts,
                         FILE *fout)
{
    int printed = 0;
    for (int i = 0; i < params->param_size; ++i){
        const pddl_param_t *p = params->param + i;
        if (p->inherit == -1){
            if (printed)
                fprintf(fout, " ");
            fprintf(fout, "%s - %s", p->name, ts->type[p->type].name);
            printed = 1;
        }
    }
}
