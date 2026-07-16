/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_PRED_H__
#define __PDDL_PRED_H__

#include <pddl/common.h>
#include <pddl/require_flags.h>
#include <pddl/type.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_pred {
    int id;           /*!< ID of the predicate */
    char *name;       /*!< Name of the predicate */
    int *param;       /*!< IDs of types of parameters */
    int param_size;   /*!< Number of parameters */
    pddl_bool_t read; /*!< True if the predicate appears in some precondition
                           or in goal (or metric in case of functions) */
    pddl_bool_t write; /*!< True if the predicate appreas in some effect */
    pddl_bool_t in_init; /*!< True if the predicate appear in the initial state */
    int neg_of;       /*!< ID of the predicate this predicate is negation of */
};
typedef struct pddl_pred pddl_pred_t;

void pddlPredSetName(pddl_pred_t *pred, const char *name);
void pddlPredAllocParams(pddl_pred_t *pred, int num_params);
int pddlPredSetParamType(pddl_pred_t *pred, int param, int type);

_pddl_inline pddl_bool_t pddlPredIsStatic(const pddl_pred_t *pred);


struct pddl_preds {
    pddl_pred_t *pred;
    int pred_size;
    int pred_alloc;
    /** ID of the predicate that corresponds to the (= . .) predicate */
    int eq_pred;
    /** ID of the 0-ary function "total-cost" */
    int total_cost_func;
};
typedef struct pddl_preds pddl_preds_t;

/**
 * Parse :predicates from domain PDDL.
 */
int pddlPredsParse(pddl_t *pddl, pddl_err_t *err);

/**
 * Initialize an empty set of predicates.
 */
void pddlPredsInitEmpty(pddl_preds_t *ps);

/**
 * Initialize set of predicates with only equality predicate.
 */
void pddlPredsInitEq(pddl_preds_t *ps);

/**
 * Initialize dst as a deep copy of src.
 */
void pddlPredsInitCopy(pddl_preds_t *dst, const pddl_preds_t *src);

/**
 * Parse :functions from domain PDDL.
 */
int pddlFuncsParse(pddl_t *pddl, pddl_err_t *err);

/**
 * Frees allocated resources.
 */
void pddlPredsFree(pddl_preds_t *ps);

/**
 * Sets ps->total_cost_func by looking for the total-cost function symbol.
 */
void pddlPredsSetTotalCostFunc(pddl_preds_t *ps);

/**
 * Returns ID of the predicate with the specified name.
 */
int pddlPredsGet(const pddl_preds_t *ps, const char *name);

/**
 * Adds a new predicate to the end.
 */
pddl_pred_t *pddlPredsAdd(pddl_preds_t *ps);

/**
 * Adds a new predicate that is exact copy (except its ID) of the one
 * specified by its ID.
 */
pddl_pred_t *pddlPredsAddCopy(pddl_preds_t *ps, int src_id);

/**
 * Removes last predicate from the array.
 */
void pddlPredsRemoveLast(pddl_preds_t *ps);

/**
 * Remove predicates with the specified IDs and if remap_out is non-NULL,
 * it is filled with the mapping from old to new IDs (-1 indicating the
 * predicate was removed).
 */
void pddlPredsRemove(pddl_preds_t *ps, const pddl_iset_t *rm_ids,
                     int *remap_out);

/**
 * Remap type IDs and remove predicates with removed types.
 */
void pddlPredsRemapTypes(pddl_preds_t *ps,
                         const int *type_remap,
                         int *pred_remap);

void pddlPredsPrint(const pddl_preds_t *ps,
                    const char *title, FILE *fout);

/**
 * Print predicates in PDDL format.
 */
void pddlPredsPrintPDDL(const pddl_preds_t *ps,
                        const pddl_types_t *ts,
                        FILE *fout);
void pddlFuncsPrintPDDL(const pddl_preds_t *ps,
                        const pddl_types_t *ts,
                        FILE *fout);


/**** INLINES: ****/
_pddl_inline pddl_bool_t pddlPredIsStatic(const pddl_pred_t *pred)
{
    return !pred->write;
}

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_PRED_H__ */
