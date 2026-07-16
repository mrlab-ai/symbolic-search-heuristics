/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_SEARCH_INTERNAL_H__
#define __PDDL_SEARCH_INTERNAL_H__

#include "pddl/search.h"

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

typedef void (*pddl_search_del_fn)(pddl_search_t *);
typedef pddl_search_status_t (*pddl_search_init_step_fn)(pddl_search_t *);
typedef pddl_search_status_t (*pddl_search_step_fn)(pddl_search_t *);
typedef int (*pddl_search_extract_plan_fn)(pddl_search_t *, pddl_plan_t *);
typedef void (*pddl_search_stat_fn)(const pddl_search_t *,
                                    pddl_search_stat_t *stat);
struct pddl_search {
    pddl_search_del_fn fn_del;
    pddl_search_init_step_fn fn_init_step;
    pddl_search_step_fn fn_step;
    pddl_search_extract_plan_fn fn_extract_plan;
    pddl_search_stat_fn fn_stat;
};

void _pddlSearchInit(pddl_search_t *s,
                     pddl_search_del_fn fn_del,
                     pddl_search_init_step_fn fn_init_step,
                     pddl_search_step_fn fn_step,
                     pddl_search_extract_plan_fn fn_extract_plan,
                     pddl_search_stat_fn fn_stat);


pddl_search_t *pddlSearchBFSNew(const pddl_search_config_t *cfg,
                                int g_weight,
                                int h_weight,
                                pddl_bool_t is_greedy,
                                pddl_bool_t is_lazy,
                                pddl_bool_t reopen,
                                const char *err_prefix,
                                pddl_err_t *err);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_SEARCH_INTERNAL_H__ */
