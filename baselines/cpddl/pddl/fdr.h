/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_FDR_H__
#define __PDDL_FDR_H__

#include <pddl/iarr.h>
#include <pddl/fdr_var.h>
#include <pddl/fdr_op.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_fdr_config {
    /** Allocation of variables */
    pddl_fdr_vars_config_t var;
    /** Add "none-of-those" values to preconditions even if it is not necessary. */
    pddl_bool_t set_none_of_those_in_pre;
};
typedef struct pddl_fdr_config pddl_fdr_config_t;

#define PDDL_FDR_CONFIG_INIT \
    { \
        PDDL_FDR_VARS_CONFIG_INIT, /* .var */ \
        pddl_false, /* .set_none_of_those_in_pre */ \
    }

void pddlFDRConfigInit(pddl_fdr_config_t *cfg);
void pddlFDRConfigLog(const pddl_fdr_config_t *cfg, pddl_err_t *err);

struct pddl_fdr {
    pddl_fdr_config_t cfg;
    /** Set of variables */
    pddl_fdr_vars_t var;
    /** Set of operators */
    pddl_fdr_ops_t op;
    /** Initial state. Array of size .var.var_size */
    int *init;
    /** Goal specification */
    pddl_fdr_part_state_t goal;
    /** True if no goal state is reachable */
    pddl_bool_t goal_is_unreachable;
    /** True if any operator has a conditional effect */
    pddl_bool_t has_cond_eff;
    /** True if the task a shallow copy of another task */
    pddl_bool_t is_shallow_copy;
};
typedef struct pddl_fdr pddl_fdr_t;

#define PDDL_FDR_SET_NONE_OF_THOSE_IN_PRE 0x1

int pddlFDRInitFromStrips(pddl_fdr_t *fdr,
                          const pddl_strips_t *strips,
                          const pddl_mgroups_t *mg,
                          const pddl_mutex_pairs_t *mutex,
                          const pddl_fdr_config_t *cfg,
                          pddl_err_t *err);
void pddlFDRInitCopy(pddl_fdr_t *fdr, const pddl_fdr_t *fdr_in);
void pddlFDRFree(pddl_fdr_t *fdr);

pddl_fdr_t *pddlFDRClone(const pddl_fdr_t *fdr_in);
void pddlFDRDel(pddl_fdr_t *fdr);

/**
 * Creates a "shallow" copy of the planning tasks and sets the initial
 * state to the given state.
 * IMPORTANT: Chaning anything in {fdr} (except the initial state) will
 * change also {fdr_in}.
 */
void pddlFDRInitShallowCopyWithDifferentInitState(pddl_fdr_t *fdr,
                                                  const pddl_fdr_t *fdr_in,
                                                  const int *state);

/**
 * Reorder variables using causal graph
 */
void pddlFDRReorderVarsCG(pddl_fdr_t *fdr);

/**
 * Delete the specified facts and operators.
 */
void pddlFDRReduce(pddl_fdr_t *fdr,
                   const pddl_iset_t *del_vars,
                   const pddl_iset_t *del_facts,
                   const pddl_iset_t *del_ops);

/**
 * Same as pddlFDRReduce() except it output also mapping between old and
 * new facts.
 */
void pddlFDRReduceGetRemap(pddl_fdr_t *fdr,
                           const pddl_iset_t *del_vars,
                           const pddl_iset_t *_del_facts,
                           const pddl_iset_t *del_ops,
                           pddl_fdr_vars_remap_t *remap);

/**
 * Returns true if the plan is a relaxed plan of the problem.
 */
int pddlFDRIsRelaxedPlan(const pddl_fdr_t *fdr,
                         const int *fdr_state,
                         const pddl_iarr_t *plan,
                         pddl_err_t *err);


/** Prevail conditions are copied to effects -- this creates a true TNF,
 *  but it can produce operators that are not well-formed */
#define PDDL_FDR_TNF_PREVAIL_TO_EFF 0x1
/** Takes effect only if mutex argument is non-NULL.
 *  Use weak type of disambiguation. */
#define PDDL_FDR_TNF_WEAK_DISAMBIGUATION 0x2
/** Multiply operators instead of creating forgetting operators */
#define PDDL_FDR_TNF_MULTIPLY_OPS 0x4

/**
 * Initialize FDR as the Transition Normal Form of fdr_in.
 * If mutex is non-NULL disambiguation is used.
 * {flags} must be or'ed PDDL_FDR_TNF_* flags.
 * Fact IDs are preserved from fdr_in and operator IDs are preserved unless
 * there are unreachable operators that are removed.
 */
int pddlFDRInitTransitionNormalForm(pddl_fdr_t *fdr,
                                    const pddl_fdr_t *fdr_in,
                                    const pddl_mutex_pairs_t *mutex,
                                    unsigned flags,
                                    pddl_err_t *err);

/**
 * Initialize {dst_fdr_mutex} mutex pairs as a copy of {str_strips_mutex}.
 * {dst_fdr_mutex} mutex pairs will be valid mutex pairs in the given FDR
 * planning task {fdr}.
 * It is assumed that the input mutex pairs {src_strips_mutex} are valid
 * mutex pairs for the STRIPS-encoded planning task used for the
 * construction of the FDR planning task {fdr}.
 */
void pddlFDRMutexPairsInitCopy(pddl_mutex_pairs_t *dst_fdr_mutex,
                               const pddl_mutex_pairs_t *src_strips_mutex,
                               const pddl_fdr_t *fdr);

void pddlFDRPrintFD(const pddl_fdr_t *fdr,
                    const pddl_mgroups_t *mgs,
                    pddl_bool_t use_fd_fact_names,
                    FILE *fout);

struct pddl_fdr_write_config {
    /** If set, the output will be written to this file */
    const char *filename;
    /** If set, the task will be written to this stream */
    FILE *fout;
    /** If set to true, Fast Downward format is used. */
    pddl_bool_t fd;
    /** If set to true, Fast Downward style of fact names is used */
    pddl_bool_t use_fd_fact_names;
    /** If set, given mutex groups will be printed out */
    const pddl_mgroups_t *mgroups;
    /** If set to true, IDs of operators are incorporated in the names of
     *  operators */
    pddl_bool_t encode_op_ids;
    /** If true, format for OSP tasks is used with all goals considered
     *  soft goals. */
    pddl_bool_t osp_all_soft_goals;
};
typedef struct pddl_fdr_write_config pddl_fdr_write_config_t;

#define PDDL_FDR_WRITE_CONFIG_INIT \
    { \
        NULL, /* .filename */ \
        NULL, /* .fout */ \
        pddl_true, /* .fd */ \
        pddl_false, /* .use_fd_fact_names */ \
        NULL, /* .mgroups */ \
        pddl_false, /* .encode_op_ids */ \
        pddl_false, /* .osp_all_soft_goals */ \
    }

void pddlFDRWrite(const pddl_fdr_t *fdr, const pddl_fdr_write_config_t *cfg);

void pddlFDRLogInfo(const pddl_fdr_t *fdr, pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_FDR_H__ */
