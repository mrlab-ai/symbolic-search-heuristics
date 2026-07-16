/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/gaifman.h"
#include "pddl/iarr.h"
#include "internal.h"

void pddlGaifmanInit(pddl_gaifman_t *g, int obj_size)
{
    ZEROIZE(g);
    g->obj_size = obj_size;
    g->obj_relate_to = ZALLOC_ARR(pddl_iset_t, g->obj_size);
    g->distance = ALLOC_ARR(int, g->obj_size * g->obj_size);
    g->distance_dirty = 1;
}

void pddlGaifmanInitCopy(pddl_gaifman_t *g, const pddl_gaifman_t *gin)
{
    ZEROIZE(g);
    g->obj_size = gin->obj_size;
    g->obj_relate_to = ZALLOC_ARR(pddl_iset_t, g->obj_size);
    for (int i = 0; i < g->obj_size; ++i)
        pddlISetUnion(g->obj_relate_to + i, gin->obj_relate_to + i);
    g->distance = ALLOC_ARR(int, g->obj_size * g->obj_size);
    g->distance_dirty = 1;
}

void pddlGaifmanFree(pddl_gaifman_t *g)
{
    for (int i = 0; i < g->obj_size; ++i)
        pddlISetFree(g->obj_relate_to + i);
    if (g->obj_relate_to != NULL)
        FREE(g->obj_relate_to);
    if (g->distance != NULL)
        FREE(g->distance);
}

void pddlGaifmanAddRelation(pddl_gaifman_t *g, int obj1, int obj2)
{
    pddlISetAdd(g->obj_relate_to + obj1, obj2);
    pddlISetAdd(g->obj_relate_to + obj2, obj1);
    g->distance_dirty = 1;
}

void pddlGaifmanAddRelationsFromAtom(pddl_gaifman_t *g,
                                     const pddl_fm_atom_t *atom)
{
    pddlGaifmanAddRelationsFromFm(g, &atom->fm);
}

void pddlGaifmanAddRelationsFromGroundAtom(pddl_gaifman_t *g,
                                           const pddl_ground_atom_t *atom)
{
    for (int ai1 = 0; ai1 < atom->arg_size; ++ai1){
        for (int ai2 = ai1 + 1; ai2 < atom->arg_size; ++ai2){
            pddlGaifmanAddRelation(g, atom->arg[ai1], atom->arg[ai2]);
        }
    }
}

static int addRelationFromFm(pddl_fm_t *fm, void *_g)
{
    pddl_gaifman_t *g = _g;
    if (pddlFmIsAtom(fm)){
        pddl_fm_atom_t *a = pddlFmToAtom(fm);
        if (a->neg)
            return 0;

        for (int ai = 0; ai < a->arg_size; ++ai){
            if (a->arg[ai].param >= 0)
                continue;
            for (int ai2 = ai + 1; ai2 < a->arg_size; ++ai2){
                if (a->arg[ai2].param >= 0)
                    continue;
                pddlGaifmanAddRelation(g, a->arg[ai].obj, a->arg[ai2].obj);
            }
        }
    }
    return 0;
}

void pddlGaifmanAddRelationsFromFm(pddl_gaifman_t *g, const pddl_fm_t *fm)
{
    pddlFmTraverseProp((pddl_fm_t *)fm, NULL, addRelationFromFm, g);
}

static void pddlGaifmanComputeDistances(pddl_gaifman_t *g)
{
    // Run BFS from each node
    for (int start = 0; start < g->obj_size; ++start){
        int *depth = ZALLOC_ARR(int, g->obj_size);
        PDDL_IARR(queue);
        pddlIArrAdd(&queue, start);
        depth[start] = 1;
        for (int i = 0; i < pddlIArrSize(&queue); ++i){
            int obj = pddlIArrGet(&queue, i);
            int other;
            PDDL_ISET_FOR_EACH(&g->obj_relate_to[obj], other){
                if (other == obj || depth[other] > 0)
                    continue;
                pddlIArrAdd(&queue, other);
                depth[other] = depth[obj] + 1;
            }
        }
        for (int other = 0; other < g->obj_size; ++other)
            g->distance[start * g->obj_size + other] = depth[other] - 1;
        pddlIArrFree(&queue);
        FREE(depth);
    }

    g->distance_dirty = 0;
}

int pddlGaifmanDistance(pddl_gaifman_t *g, int obj1, int obj2)
{
    if (g->distance_dirty)
        pddlGaifmanComputeDistances(g);
    return g->distance[obj1 * g->obj_size + obj2];
}

int pddlGaifmanDiameter(pddl_gaifman_t *g)
{
    if (g->distance_dirty)
        pddlGaifmanComputeDistances(g);

    int diameter = 0;
    for (int obj1 = 0; obj1 < g->obj_size; ++obj1){
        for (int obj2 = 0; obj2 < g->obj_size; ++obj2){
            if (g->distance[obj1 * g->obj_size + obj2] < 0)
                return -1;
            diameter = PDDL_MAX(g->distance[obj1 * g->obj_size + obj2], diameter);
        }
    }

    return diameter;
}

static int fmCollectObjs(pddl_fm_t *fm, void *_objs)
{
    pddl_iset_t *objs = _objs;
    if (pddlFmIsAtom(fm)){
        pddl_fm_atom_t *a = pddlFmToAtom(fm);
        for (int ai = 0; ai < a->arg_size; ++ai){
            if (a->arg[ai].param < 0)
                pddlISetAdd(objs, a->arg[ai].obj);
        }
    }
    return 0;
}

struct param_obj_maps {
    pddl_gaifman_t *g;
    int *obj_map;
};

static int fmAddRelationsParamObj(pddl_fm_t *fm, void *_maps)
{
    struct param_obj_maps *maps = _maps;
    pddl_gaifman_t *g = maps->g;
    const int *obj_map = maps->obj_map;
    if (pddlFmIsAtom(fm)){
        pddl_fm_atom_t *a = pddlFmToAtom(fm);
        if (a->neg)
            return 0;

        for (int ai = 0; ai < a->arg_size; ++ai){
            int id1 = 0;
            if (a->arg[ai].param >= 0){
                id1 = a->arg[ai].param;
            }else{
                id1 = obj_map[a->arg[ai].obj];
            }

            for (int ai2 = ai + 1; ai2 < a->arg_size; ++ai2){
                int id2 = 0;
                if (a->arg[ai2].param >= 0){
                    id2 = a->arg[ai2].param;
                }else{
                    id2 = obj_map[a->arg[ai2].obj];
                }
                pddlGaifmanAddRelation(g, id1, id2);
            }
        }
    }
    return 0;
}

int pddlGaifmanActionPreDiameter(const pddl_action_t *a)
{
    PDDL_ISET(objs);
    pddlFmTraverseProp((pddl_fm_t *)a->pre, NULL, fmCollectObjs, &objs);

    if (pddlISetSize(&objs) + a->param.param_size == 0){
        pddlISetFree(&objs);
        return 0;
    }

    int *obj_map = NULL;
    if (pddlISetSize(&objs) > 0){
        int size = pddlISetSize(&objs);
        obj_map = ALLOC_ARR(int, pddlISetGet(&objs, size - 1) + 1);
        int idx = a->param.param_size;
        int obj_id;
        PDDL_ISET_FOR_EACH(&objs, obj_id)
            obj_map[obj_id] = idx++;
    }

    pddl_gaifman_t g;
    pddlGaifmanInit(&g, a->param.param_size + pddlISetSize(&objs));

    struct param_obj_maps maps = { &g, obj_map };
    pddlFmTraverseProp((pddl_fm_t *)a->pre, NULL, fmAddRelationsParamObj, &maps);

    int diameter = pddlGaifmanDiameter(&g);
    pddlGaifmanFree(&g);

    if (obj_map != NULL)
        FREE(obj_map);
    pddlISetFree(&objs);

    return diameter;
}
