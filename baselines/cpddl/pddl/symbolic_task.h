/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_SYMBOLIC_TASK_H__
#define __PDDL_SYMBOLIC_TASK_H__

#include <pddl/iarr.h>
#include <pddl/strips.h>
#include <pddl/mgroup.h>
#include <pddl/mutex_pair.h>
#include <pddl/hpot.h>
#include <pddl/bdd.h>
#include <pddl/bdds.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

#define PDDL_SYMBOLIC_CONT 0
#define PDDL_SYMBOLIC_PLAN_FOUND 1
#define PDDL_SYMBOLIC_PLAN_NOT_EXIST 2
#define PDDL_SYMBOLIC_FAIL -1
#define PDDL_SYMBOLIC_ABORT_TIME_LIMIT -2

struct pddl_symbolic_search_config {
    pddl_bool_t enabled;
    size_t trans_merge_max_nodes;
    float trans_merge_max_time;
    pddl_bool_t use_constr;
    pddl_bool_t use_op_constr;
    pddl_bool_t use_pot_heur;
    pddl_bool_t use_pot_heur_inconsistent;
    pddl_bool_t use_pot_heur_sum_op_cost;
    pddl_bool_t use_goal_splitting;
    float step_time_limit;
    pddl_hpot_config_t pot_heur_config;
};
typedef struct pddl_symbolic_search_config pddl_symbolic_search_config_t;

#define __PDDL_SYMBOLIC_SEARCH_CONFIG_INIT(Enabled) \
    { \
        (Enabled), /* .enabled */ \
        100000ul, /* .trans_merge_max_nodes */ \
        -1.f, /* .trans_merge_max_time */ \
        pddl_false, /* .use_constr */ \
        pddl_true, /* .use_op_constr */ \
        pddl_false, /* .use_pot_heur */ \
        pddl_false, /* .use_pot_heur_inconsistent */ \
        pddl_false, /* .use_pot_heur_sum_op_cost */ \
        pddl_true, /* .use_goal_splitting */ \
        0.f, /* .step_time_limit */ \
        PDDL_HPOT_CONFIG_INIT, \
    }

struct pddl_symbolic_task_config {
    /** Size of internal cache used by the BDD library */
    int cache_size;
    /** Maximal number of BDD nodes in the mutex constraint BDD. Higher
     *  number of nodes will lead to disjunctive partitioning. */
    size_t constr_max_nodes;
    /** Maximum time allowed to use for constructing constraint BDD. When
     *  time limit is reached, disjunctive partitioning is used. */
    float constr_max_time;
    /** Same as .constr_max_time but for construction of goal BDD */
    float goal_constr_max_time;
    /** If >0, fam-groups are inferred on the ground level and .fam_groups
     *  specifies maximum number of maximal fam-groups that are inferred. */
    int fam_groups;
    /** If true, every search step is logged */
    pddl_bool_t log_every_step;
    /** If true, (meta-)facts corresponding to conjunctions are compiled
     *  away before search starts, i.e., potential heuristics are computed
     *  on the input P^C task, but search is performed on the projection.
     *  This also means that goal-splitting cannot be performed, because
     *  the potential heuristic on P^C is not valid in P (in contrast to
     *  operator-potential heuristics). */
    pddl_bool_t compile_away_conjunctions;

    pddl_symbolic_search_config_t fw;
    pddl_symbolic_search_config_t bw;
};
typedef struct pddl_symbolic_task_config pddl_symbolic_task_config_t;

#define PDDL_SYMBOLIC_TASK_CONFIG_INIT \
    { \
        16000000, /* .cache_size */ \
        100000ul, /* .constr_max_nodes */ \
        -1.f, /* .constr_max_time */ \
        -1., /* .goal_constr_max_time */ \
        pddl_false, /* .fam_groups */ \
        pddl_false, /* .log_every_step */ \
        pddl_false, /* .compile_away_conjunctions */ \
        __PDDL_SYMBOLIC_SEARCH_CONFIG_INIT(1), /* .fw */ \
        __PDDL_SYMBOLIC_SEARCH_CONFIG_INIT(0), /* .bw */ \
    }

typedef struct pddl_symbolic_task pddl_symbolic_task_t;

pddl_symbolic_task_t *pddlSymbolicTaskNew(const pddl_fdr_t *fdr,
                                          const pddl_symbolic_task_config_t *c,
                                          pddl_err_t *err);

void pddlSymbolicTaskDel(pddl_symbolic_task_t *states);

/**
 * Returns true if applying constraints on the goal failed.
 */
int pddlSymbolicTaskGoalConstrFailed(const pddl_symbolic_task_t *task);

int pddlSymbolicTaskSearchFw(pddl_symbolic_task_t *ss,
                             pddl_iarr_t *plan,
                             pddl_err_t *err);
int pddlSymbolicTaskSearchBw(pddl_symbolic_task_t *ss,
                             pddl_iarr_t *plan,
                             pddl_err_t *err);
int pddlSymbolicTaskSearchFwBw(pddl_symbolic_task_t *ss,
                               pddl_iarr_t *plan,
                               pddl_err_t *err);
int pddlSymbolicTaskSearch(pddl_symbolic_task_t *ss,
                           pddl_iarr_t *plan,
                           pddl_err_t *err);

int pddlSymbolicTaskCheckApplyFw(pddl_symbolic_task_t *ss,
                                 const int *state,
                                 const int *res_state,
                                 int op_id);
int pddlSymbolicTaskCheckApplyBw(pddl_symbolic_task_t *ss,
                                 const int *state,
                                 const int *res_state,
                                 int op_id);
int pddlSymbolicTaskCheckPlan(pddl_symbolic_task_t *ss,
                              const pddl_iarr_t *op,
                              int plan_size);
#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_SYMBOLIC_TASK_H__ */
