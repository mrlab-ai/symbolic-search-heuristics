/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "search.h"
#include "internal.h"

void _pddlSearchInit(pddl_search_t *s,
                     pddl_search_del_fn fn_del,
                     pddl_search_init_step_fn fn_init_step,
                     pddl_search_step_fn fn_step,
                     pddl_search_extract_plan_fn fn_extract_plan,
                     pddl_search_stat_fn fn_stat)
{
    ZEROIZE(s);
    s->fn_del = fn_del;
    s->fn_init_step = fn_init_step;
    s->fn_step = fn_step;
    s->fn_extract_plan = fn_extract_plan;
    s->fn_stat = fn_stat;
}

static void _pddlSearchFree(pddl_search_t *s)
{
}

pddl_search_t *pddlSearchNew(const pddl_search_config_t *cfg, pddl_err_t *err)
{
    if (cfg->fdr == NULL)
        ERR_RET(err, NULL, "FDR planning task must be defined.");

    switch (cfg->alg){
        case PDDL_SEARCH_ASTAR:
            return pddlSearchBFSNew(cfg, 1, 1, pddl_false, pddl_false, pddl_true, "A*", err);

        case PDDL_SEARCH_LAZY:
            return pddlSearchBFSNew(cfg, 0, 1, pddl_true, pddl_true, pddl_false, "Lazy", err);

        case PDDL_SEARCH_GBFS:
            return pddlSearchBFSNew(cfg, 0, 1, pddl_true, pddl_false, pddl_false, "GBFS", err);

        default:
            ERR_RET(err, NULL, "Unkown algorithm %d", cfg->alg);
    }
}

void pddlSearchDel(pddl_search_t *s)
{
    _pddlSearchFree(s);
    s->fn_del(s);
}

pddl_search_status_t pddlSearchInitStep(pddl_search_t *s)
{
    return s->fn_init_step(s);
}

pddl_search_status_t pddlSearchStep(pddl_search_t *s)
{
    return s->fn_step(s);
}

int pddlSearchExtractPlan(pddl_search_t *s, pddl_plan_t *plan)
{
    return s->fn_extract_plan(s, plan);
}

void pddlSearchStat(const pddl_search_t *s, pddl_search_stat_t *stat)
{
    s->fn_stat(s, stat);
}

void pddlSearchStatLog(const pddl_search_t *s, pddl_err_t *err)
{
    pddl_search_stat_t stat;
    pddlSearchStat(s, &stat);
    LOG(err, "Search steps: %lu,"
        " expand: %lu,"
        " expand-blfl: %lu,"
        " eval: %lu,"
        " gen: %lu,"
        " open: %lu,"
        " closed: %lu,"
        " reopen: %lu,"
        " de: %lu,"
        " de-blfl: %lu,"
        " f: %d",
        stat.steps,
        stat.expanded,
        stat.expanded_before_last_f_layer,
        stat.evaluated,
        stat.generated,
        stat.open,
        stat.closed,
        stat.reopen,
        stat.dead_end,
        stat.dead_end_before_last_f_layer,
        stat.last_f_value);
}
