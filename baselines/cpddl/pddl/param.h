/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_PARAM_H__
#define __PDDL_PARAM_H__

#include <pddl/type.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */


/**
 * Typed parameter
 */
struct pddl_param {
    /** Name of the parameter */
    char *name;
    /** Type ID */
    int type;
    /** True if this is :agent parameter */
    pddl_bool_t is_agent;
    /** -1 or ID of the parent parameter of which this is a copy */
    int inherit;
    /** True if it is counted variable -- this is used for inference of
     *  lifted mutex groups */
    pddl_bool_t is_counted_var;
};
typedef struct pddl_param pddl_param_t;

struct pddl_params {
    pddl_param_t *param;
    int param_size;
    int param_alloc;
};
typedef struct pddl_params pddl_params_t;


/**
 * Initialzie empty parameter
 */
void pddlParamInit(pddl_param_t *param);

/**
 * Copies src to dst.
 */
void pddlParamInitCopy(pddl_param_t *dst, const pddl_param_t *src);

/**
 * Initialize list of parameters
 */
void pddlParamsInit(pddl_params_t *params);

/**
 * Free allocated memory.
 */
void pddlParamsFree(pddl_params_t *params);

/**
 * Adds a new empty parameter object at the end of params.
 */
pddl_param_t *pddlParamsAdd(pddl_params_t *params);

/**
 * Adds a copy of the specified parameter.
 */
pddl_param_t *pddlParamsAddCopy(pddl_params_t *params, const pddl_param_t *p);

/**
 * Copies src to dst.
 */
void pddlParamsInitCopy(pddl_params_t *dst, const pddl_params_t *src);

/**
 * Returns index of the parameter with the specified name or -1 if such a
 * parameter is not stored in the list.
 */
int pddlParamsGetId(const pddl_params_t *param, const char *name);

/**
 * Extends the parameters {params} with all parameters from the parent list of
 * parameters {parent} that are not over-shadowed and set the corresponding
 * .inherit property.
 */
void pddlParamsInherit(pddl_params_t *params, const pddl_params_t *parent);

/**
 * Remap parameters.
 */
void pddlParamsRemap(pddl_params_t *params, const int *remap);

void pddlParamsPrint(const pddl_params_t *params, FILE *fout);

/**
 * Print parameters in PDDL format (without parenthesis), the inherited
 * parameters are not printed.
 */
void pddlParamsPrintPDDL(const pddl_params_t *params,
                         const pddl_types_t *ts,
                         FILE *fout);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_PARAM_H__ */
