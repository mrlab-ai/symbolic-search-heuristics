/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_APP_OP_H__
#define __PDDL_APP_OP_H__

#include <pddl/iset.h>
#include <pddl/fdr_op.h>
#include <pddl/fdr_part_state.h>
#include <pddl/fdr_var.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_fdr_app_op_tree;

/**
 * Struct for finding applicable operators.
 */
struct pddl_fdr_app_op {
    struct pddl_fdr_app_op_tree *root; /*!< Root of decision tree */
    const pddl_fdr_ops_t *ops; /*!< Reference to the set of operators */
    int *var_order; /*!< Copied order of variables to enable cloning of the
                         object */
    int var_size;
};
typedef struct pddl_fdr_app_op pddl_fdr_app_op_t;


/**
 * Creates a structure for finding applicable operators.
 */
void pddlFDRAppOpInit(pddl_fdr_app_op_t *app,
                      const pddl_fdr_vars_t *vars,
                      const pddl_fdr_ops_t *ops,
                      const pddl_fdr_part_state_t *goal);

/**
 * Frees allocated memory.
 */
void pddlFDRAppOpFree(pddl_fdr_app_op_t *app);

/**
 * Finds all applicable operators to the given state.
 * The operators are added to the output set {op}.
 * The overall number of found operators is returned.
 */
int pddlFDRAppOpFind(const pddl_fdr_app_op_t *app,
                     const int *state,
                     pddl_iset_t *ops);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_APP_OP_H__ */
