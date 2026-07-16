/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_OP_MUTEX_SYM_REDUNDANT_H__
#define __PDDL_OP_MUTEX_SYM_REDUNDANT_H__

#include <pddl/err.h>
#include <pddl/op_mutex_pair.h>
#include <pddl/sym.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

enum {
    PDDL_OP_MUTEX_REDUNDANT_GREEDY = 1,
    PDDL_OP_MUTEX_REDUNDANT_MAX = 2,
};

struct pddl_op_mutex_redundant_config {
    int method; /*!< One of PDDL_OP_MUTEX_REDUNDANT_* methods */
    float lp_time_limit; /*!< Time limit for the ILP solver */
};
typedef struct pddl_op_mutex_redundant_config pddl_op_mutex_redundant_config_t;

#define PDDL_OP_MUTEX_REDUNDANT_CONFIG_INIT \
    { \
        PDDL_OP_MUTEX_REDUNDANT_GREEDY, /* .method */ \
        -1., /* .lp_time_limit */ \
    }

/**
 * Find redundant operators given op-mutexes and symmetries
 */
int pddlOpMutexFindRedundant(const pddl_op_mutex_pairs_t *op_mutex,
                             const pddl_strips_sym_t *sym,
                             const pddl_op_mutex_redundant_config_t *cfg,
                             pddl_iset_t *redundant_ops,
                             pddl_err_t *err);

/**
 * Computes a set of redundant operators using fixpoint computation with a
 * set of operator mutexes and symmetries.
 */
int pddlOpMutexFindRedundantGreedy(const pddl_op_mutex_pairs_t *op_mutex,
                                   const pddl_strips_sym_t *sym,
                                   const pddl_op_mutex_redundant_config_t *cfg,
                                   pddl_iset_t *redundant_ops,
                                   pddl_err_t *err);

int pddlOpMutexFindRedundantMax(const pddl_op_mutex_pairs_t *op_mutex,
                                const pddl_strips_sym_t *sym,
                                const pddl_op_mutex_redundant_config_t *cfg,
                                pddl_iset_t *redundant_ops,
                                pddl_err_t *err);
#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_OP_MUTEX_SYM_REDUNDANT_H__ */
