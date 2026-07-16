/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/open_list.h"

void _pddlOpenListInit(pddl_open_list_t *l,
                       pddl_open_list_del_fn del_fn,
                       pddl_open_list_push_fn push_fn,
                       pddl_open_list_pop_fn pop_fn,
                       pddl_open_list_top_fn top_fn,
                       pddl_open_list_clear_fn clear_fn)
{
    l->del_fn   = del_fn;
    l->push_fn  = push_fn;
    l->pop_fn   = pop_fn;
    l->top_fn   = top_fn;
    l->clear_fn = clear_fn;
}

void _pddlOpenListFree(pddl_open_list_t *l)
{
}
