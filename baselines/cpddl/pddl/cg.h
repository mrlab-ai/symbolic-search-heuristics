/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_CG_H__
#define __PDDL_CG_H__

#include <pddl/fdr_var.h>
#include <pddl/fdr_op.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_cg_edge {
    int end; /*!< ID of the end node */
    int value; /*!< Value of the edge */
};
typedef struct pddl_cg_edge pddl_cg_edge_t;

struct pddl_cg_node {
    pddl_cg_edge_t *fw; /*!< Forward edges */
    int fw_size;
    pddl_cg_edge_t *bw; /*!< Backward edges */
    int bw_size;
};
typedef struct pddl_cg_node pddl_cg_node_t;

/**
 * Causal graph structure.
 */
struct pddl_cg {
    int node_size;
    pddl_cg_node_t *node;
};
typedef struct pddl_cg pddl_cg_t;


void pddlCGInit(pddl_cg_t *cg,
                const pddl_fdr_vars_t *vars,
                const pddl_fdr_ops_t *ops,
                int add_eff_eff_edges);
void pddlCGInitCopy(pddl_cg_t *cg, const pddl_cg_t *cg_in);

void pddlCGInitProjectToVars(pddl_cg_t *dst,
                             const pddl_cg_t *src,
                             const pddl_iset_t *vars);
void pddlCGInitProjectToBlackVars(pddl_cg_t *dst,
                                  const pddl_cg_t *src,
                                  const pddl_fdr_vars_t *vars);

void pddlCGFree(pddl_cg_t *cg);

/**
 * Set important_vars[V] = 1/0 if V is an backward reachable/unreachable
 * from goal.
 */
void pddlCGMarkBackwardReachableVars(const pddl_cg_t *cg,
                                     const pddl_fdr_part_state_t *goal,
                                     int *important_vars);

void pddlCGVarOrdering(const pddl_cg_t *cg,
                       const pddl_fdr_part_state_t *goal,
                       int *var_ordering);

pddl_bool_t pddlCGIsAcyclic(const pddl_cg_t *cg);


void pddlCGPrintDebug(const pddl_cg_t *cg, FILE *fout);

char *pddlCGAsDot(const pddl_cg_t *cg, size_t *buf_size);

void pddlCGPrintAsciiGraph(const pddl_cg_t *cg, FILE *out, pddl_err_t *err);


#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_CG_H__ */
