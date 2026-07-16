/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/err.h"
#include "pddl/trans_system_abstr_map.h"
#include "internal.h"

void pddlTransSystemAbstrMapInit(pddl_trans_system_abstr_map_t *map,
                                 int num_states)
{
    map->num_states = num_states;
    map->map = ALLOC_ARR(int, map->num_states);
    for (int i = 0; i < map->num_states; ++i)
        map->map[i] = i;
    map->map_num_states = -1;
    map->is_identity = 1;
}

void pddlTransSystemAbstrMapFree(pddl_trans_system_abstr_map_t *map)
{
    if (map->map != NULL)
        FREE(map->map);
}

void pddlTransSystemAbstrMapFinalize(pddl_trans_system_abstr_map_t *map)
{
    if (map->map_num_states >= 0){
        PANIC("This function can be called only on mapping that wasn't"
                   "finalized yet!");
    }

    int *ids = ZALLOC_ARR(int, map->num_states);

    for (int state = 0; state < map->num_states; ++state){
        if (map->map[state] >= 0 && ids[map->map[state]] == 0)
            ids[map->map[state]] = 1;
    }

    int id = 0;
    for (int state = 0; state < map->num_states; ++state){
        if (ids[state])
            ids[state] = id++;
    }
    map->map_num_states = id;

    for (int state = 0; state < map->num_states; ++state){
        if (map->map[state] >= 0)
            map->map[state] = ids[map->map[state]];
    }
    FREE(ids);
}

void pddlTransSystemAbstrMapPruneState(pddl_trans_system_abstr_map_t *map,
                                       int state)
{
    if (map->map_num_states >= 0){
        PANIC("This function can be called only on mapping that wasn't"
                   "finalized yet!");
    }
    map->map[state] = -1;
    map->is_identity = 0;
}

void pddlTransSystemAbstrMapCondense(pddl_trans_system_abstr_map_t *map,
                                     const pddl_iset_t *states)
{
    if (map->map_num_states >= 0){
        PANIC("This function can be called only on mapping that wasn't"
                   "finalized yet!");
    }
    if (pddlISetSize(states) <= 1)
        return;

    int to = pddlISetGet(states, 0);
    int state;
    PDDL_ISET_FOR_EACH(states, state){
        if (map->map[state] >= 0){
            ASSERT(map->map[state] == state);
            map->map[state] = to;
        }
    }
    map->is_identity = 0;
}
