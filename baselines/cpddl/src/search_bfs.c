/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/open_list.h"
#include "pddl/fdr_app_op.h"
#include "search.h"
#include "internal.h"

struct pddl_search_bfs {
    pddl_search_t search;
    const pddl_fdr_t *fdr;
    pddl_heur_t *heur;
    pddl_err_t *err;
    const char *err_prefix;
    int g_weight;
    int h_weight;
    pddl_bool_t is_greedy;
    pddl_bool_t is_lazy;
    pddl_bool_t reopen;

    pddl_fdr_state_space_t state_space;
    pddl_open_list_t *open;
    pddl_fdr_app_op_t app_op;

    /** Set to state ID of the goal state when the goal is reached */
    pddl_state_id_t goal_state_id;
    /** g-value of the goal state stored in .goal_state_id */
    int goal_g_value;

    /** Auxiliary structs */
    pddl_iset_t applicable;
    pddl_fdr_state_space_node_t cur_node;
    pddl_fdr_state_space_node_t next_node;
    pddl_search_stat_t _stat;
};
typedef struct pddl_search_bfs pddl_search_bfs_t;

#define S(T, SEARCH) \
    pddl_search_bfs_t *T = pddl_container_of((SEARCH), pddl_search_bfs_t, search)

static void bfsDel(pddl_search_t *s);
static pddl_search_status_t bfsInitStep(pddl_search_t *s);
static pddl_search_status_t bfsStep(pddl_search_t *s);
static int bfsExtractPlan(pddl_search_t *s, pddl_plan_t *plan);
static void bfsStat(const pddl_search_t *s, pddl_search_stat_t *stat);

pddl_search_t *pddlSearchBFSNew(const pddl_search_config_t *cfg,
                                int g_weight,
                                int h_weight,
                                pddl_bool_t is_greedy,
                                pddl_bool_t is_lazy,
                                pddl_bool_t reopen,
                                const char *err_prefix,
                                pddl_err_t *err)
{
    pddl_search_bfs_t *s = ZALLOC(pddl_search_bfs_t);
    _pddlSearchInit(&s->search, bfsDel, bfsInitStep, bfsStep,
                    bfsExtractPlan, bfsStat);
    s->fdr = cfg->fdr;
    s->heur = cfg->heur;
    s->err = err;
    s->err_prefix = err_prefix;
    s->g_weight = g_weight;
    s->h_weight = h_weight;
    s->is_greedy = is_greedy;
    s->is_lazy = is_lazy;
    s->reopen = reopen;

    pddlFDRStateSpaceInit(&s->state_space, &s->fdr->var, err);
    s->open = pddlOpenListSplayTree2();

    pddlFDRAppOpInit(&s->app_op, &s->fdr->var, &s->fdr->op, &s->fdr->goal);

    s->goal_state_id = PDDL_NO_STATE_ID;
    s->goal_g_value = INT_MAX;

    pddlISetInit(&s->applicable);
    pddlFDRStateSpaceNodeInit(&s->cur_node, &s->state_space);
    pddlFDRStateSpaceNodeInit(&s->next_node, &s->state_space);

    return &s->search;
}

static void bfsDel(pddl_search_t *_s)
{
    S(s, _s);
    pddlFDRAppOpFree(&s->app_op);
    if (s->open != NULL)
        pddlOpenListDel(s->open);
    pddlFDRStateSpaceNodeFree(&s->cur_node);
    pddlFDRStateSpaceNodeFree(&s->next_node);
    pddlFDRStateSpaceFree(&s->state_space);
    pddlISetFree(&s->applicable);
    FREE(s);
}

static void bfsPush(pddl_search_bfs_t *s,
                    pddl_fdr_state_space_node_t *node,
                    int h_value)
{
    int cost[2];
    cost[0] = (s->g_weight * node->g_value) + (s->h_weight * h_value);
    cost[1] = h_value;
    if (node->status == PDDL_FDR_STATE_SPACE_STATUS_CLOSED)
        --s->_stat.closed;
    node->status = PDDL_FDR_STATE_SPACE_STATUS_OPEN;
    pddlOpenListPush(s->open, cost, node->id);
    ++s->_stat.open;
}

_pddl_inline int bfsIsGoal(const pddl_search_bfs_t *s, const int *state)
{
    return pddlFDRPartStateIsConsistentWithState(&s->fdr->goal, state);
}

_pddl_inline pddl_bool_t bfsCheckGoal(pddl_search_bfs_t *s,
                                      const int *state,
                                      pddl_state_id_t cur_state_id)
{
    if (bfsIsGoal(s, state)){
        if (s->goal_state_id == PDDL_NO_STATE_ID
                || s->goal_g_value > s->cur_node.g_value){
            s->goal_state_id = cur_state_id;
            s->goal_g_value = s->cur_node.g_value;
        }
        return pddl_true;
    }
    return pddl_false;
}


static void bfsInsertNextState(pddl_search_bfs_t *s,
                               const pddl_fdr_op_t *op,
                               int in_h_value)
{
    // Compute its g() value
    int next_g_value = s->cur_node.g_value + op->cost;

    // Skip if we have better state already
    if (s->next_node.status != PDDL_FDR_STATE_SPACE_STATUS_NEW
            && s->next_node.g_value <= next_g_value){
        return;
    }

    // Skip if we are not allowed to reopen search nodes
    if (s->next_node.status == PDDL_FDR_STATE_SPACE_STATUS_CLOSED
            && !s->reopen){
        return;
    }

    s->next_node.parent_id = s->cur_node.id;
    s->next_node.op_id = op->id;
    s->next_node.g_value = next_g_value;
 
    int h_value = 0;
    if (in_h_value >= 0){
        h_value = in_h_value;

    }else if (s->heur != NULL){
        h_value = pddlHeurEstimate(s->heur, &s->next_node, &s->state_space);
        ++s->_stat.evaluated;
    }

    if (h_value == PDDL_COST_DEAD_END){
        ++s->_stat.dead_end;
        if (s->next_node.status == PDDL_FDR_STATE_SPACE_STATUS_OPEN)
            --s->_stat.open;
        s->next_node.status = PDDL_FDR_STATE_SPACE_STATUS_CLOSED;
        ++s->_stat.closed;

    }else if (s->next_node.status == PDDL_FDR_STATE_SPACE_STATUS_NEW
                || s->next_node.status == PDDL_FDR_STATE_SPACE_STATUS_OPEN){
        bfsPush(s, &s->next_node, h_value);

    }else if (s->next_node.status == PDDL_FDR_STATE_SPACE_STATUS_CLOSED){
        bfsPush(s, &s->next_node, h_value);
        ++s->_stat.reopen;
    }

    pddlFDRStateSpaceSet(&s->state_space, &s->next_node);
}

static pddl_search_status_t bfsInitStep(pddl_search_t *_s)
{
    S(s, _s);
    CTX_NO_TIME(s->err, "%s", s->err_prefix);
    pddl_search_status_t ret = PDDL_SEARCH_CONT;

    pddl_state_id_t state_id 
            = pddlFDRStateSpaceInsert(&s->state_space, s->fdr->init);
    PANIC_IF(state_id != 0, "Unexpected state ID for the initial state.");

    pddlFDRStateSpaceGet(&s->state_space, state_id, &s->cur_node);
    s->cur_node.parent_id = PDDL_NO_STATE_ID;
    s->cur_node.op_id = -1;
    s->cur_node.g_value = 0;

    int h_value = 0;
    if (s->heur != NULL){
        h_value = pddlHeurEstimate(s->heur, &s->cur_node, &s->state_space);
        ++s->_stat.evaluated;
    }
    LOG(s->err, "Heuristic value for the initial state: %d", h_value);

    if (h_value == PDDL_COST_DEAD_END){
        ++s->_stat.dead_end;
        ret = PDDL_SEARCH_UNSOLVABLE;
    }

    PANIC_IF(s->cur_node.status != PDDL_FDR_STATE_SPACE_STATUS_NEW,
             "Unexpected status of the initial state node.");
    bfsPush(s, &s->cur_node, h_value);
    pddlFDRStateSpaceSet(&s->state_space, &s->cur_node);

    if (bfsCheckGoal(s, s->cur_node.state, state_id)){
        LOG(s->err, "Found goal state. g: 0, f: %d, h: %d, init state",
            s->h_weight * h_value, h_value);
        ret = PDDL_SEARCH_FOUND;
    }

    CTXEND(s->err);
    return ret;
}

static pddl_search_status_t bfsStep(pddl_search_t *_s)
{
    S(s, _s);
    CTX_NO_TIME(s->err, "%s", s->err_prefix);
    ++s->_stat.steps;

    // Get next state from open list
    int cur_cost[2];
    pddl_state_id_t cur_state_id;
    if (pddlOpenListPop(s->open, &cur_state_id, cur_cost) != 0){
        CTXEND(s->err);
        return PDDL_SEARCH_UNSOLVABLE;
    }

    // Load the current state
    pddlFDRStateSpaceGet(&s->state_space, cur_state_id, &s->cur_node);

    // Skip already closed nodes
    if (s->cur_node.status != PDDL_FDR_STATE_SPACE_STATUS_OPEN){
        CTXEND(s->err);
        return PDDL_SEARCH_CONT;
    }

    // Close the current node
    s->cur_node.status = PDDL_FDR_STATE_SPACE_STATUS_CLOSED;
    pddlFDRStateSpaceSet(&s->state_space, &s->cur_node);
    --s->_stat.open;
    ++s->_stat.closed;
    int last_f_value = s->_stat.last_f_value;
    s->_stat.last_f_value = cur_cost[0];
    if (last_f_value != s->_stat.last_f_value){
        s->_stat.expanded_before_last_f_layer = s->_stat.expanded;
        s->_stat.dead_end_before_last_f_layer = s->_stat.dead_end;
    }

    // Check whether it is a goal in case of non-greedy search
    if (!s->is_greedy && bfsCheckGoal(s, s->cur_node.state, cur_state_id)){
        LOG(s->err, "Found goal state. g: %d, f: %d, h: %d",
            s->cur_node.g_value, cur_cost[0], cur_cost[1]);
        CTXEND(s->err);
        return PDDL_SEARCH_FOUND;
    }

    // Find all applicable operators
    pddlISetEmpty(&s->applicable);
    pddlFDRAppOpFind(&s->app_op, s->cur_node.state, &s->applicable);
    ++s->_stat.expanded;

    // Set-up heuristic value for the lazy variant
    int h_value = -1;
    if (pddlISetSize(&s->applicable) > 0 && s->is_lazy){
        h_value = 0;
        if (s->heur != NULL){
            h_value = pddlHeurEstimate(s->heur, &s->cur_node, &s->state_space);
            ++s->_stat.evaluated;
        }

        if (h_value == PDDL_COST_DEAD_END){
            ++s->_stat.dead_end;
            if (s->cur_node.status == PDDL_FDR_STATE_SPACE_STATUS_OPEN)
                --s->_stat.open;
            s->cur_node.status = PDDL_FDR_STATE_SPACE_STATUS_CLOSED;
            ++s->_stat.closed;
            pddlFDRStateSpaceSet(&s->state_space, &s->cur_node);
            CTXEND(s->err);
            return PDDL_SEARCH_CONT;
        }
    }

    int op_id;
    PDDL_ISET_FOR_EACH(&s->applicable, op_id){
        const pddl_fdr_op_t *op = s->fdr->op.op[op_id];

        // Create a new state
        pddlFDROpApplyOnState(op, s->next_node.var_size, s->cur_node.state,
                              s->next_node.state);

        // Insert the new state
        pddl_state_id_t next_state_id;
        next_state_id = pddlFDRStateSpaceInsert(&s->state_space,
                                                s->next_node.state);
        pddlFDRStateSpaceGetNoState(&s->state_space,
                                    next_state_id, &s->next_node);
        bfsInsertNextState(s, op, h_value);

        // Check whether it is a goal in case of *greedy* search
        if (s->is_greedy && bfsCheckGoal(s, s->next_node.state, next_state_id)){
            LOG(s->err, "Found goal state. g: %d", s->next_node.g_value);
            CTXEND(s->err);
            return PDDL_SEARCH_FOUND;
        }
    }

    CTXEND(s->err);
    return PDDL_SEARCH_CONT;
}

static int bfsExtractPlan(pddl_search_t *_s, pddl_plan_t *plan)
{
    S(s, _s);
    CTX_NO_TIME(s->err, "%s", s->err_prefix);
    if (s->goal_state_id == PDDL_NO_STATE_ID)
        return -1;
    pddlPlanLoadBacktrack(plan, s->goal_state_id, &s->state_space);
    CTXEND(s->err);
    return 0;
}

static void bfsStat(const pddl_search_t *_s, pddl_search_stat_t *stat)
{
    S(s, _s);
    CTX_NO_TIME(s->err, "%s", s->err_prefix);
    *stat = s->_stat;
    stat->generated = s->state_space.state_pool.num_states;
    CTXEND(s->err);
}
