/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/err.h"
#include "pddl/rand.h"
#include "pddl/homomorphism.h"
#include "pddl/endomorphism.h"
#include "pddl/strips_ground_sql.h"
#include "pddl/gaifman.h"
#include "internal.h"

#define METHOD_TYPE 1
#define METHOD_RANDOM_PAIR 2
#define METHOD_GAIFMAN 3
#define METHOD_RPG 4
#define METHOD_ENDOMORPHISM 5

void pddlHomomorphismConfigLog(const pddl_homomorphism_config_t *cfg,
                               pddl_err_t *err)
{
    if (cfg->type == PDDL_HOMOMORPHISM_TYPES){
        LOG(err, "type = types");
    }else if (cfg->type == PDDL_HOMOMORPHISM_RAND_OBJS){
        LOG(err, "type = rand-objs");
    }else if (cfg->type == PDDL_HOMOMORPHISM_RAND_TYPE_OBJS){
        LOG(err, "type = rand-type-objs");
    }else if (cfg->type == PDDL_HOMOMORPHISM_GAIFMAN){
        LOG(err, "type = gaifman");
    }else if (cfg->type == PDDL_HOMOMORPHISM_RPG){
        LOG(err, "type = rpg");
    }else{
        LOG(err, "type = unknown");
    }
    LOG_CONFIG_BOOL(cfg, use_endomorphism, err);
    LOG_CONFIG_DBL(cfg, rm_ratio, err);
    LOG_CONFIG_INT(cfg, random_seed, err);
    LOG_CONFIG_BOOL(cfg, keep_goal_objs, err);
    LOG_CONFIG_INT(cfg, rpg_max_depth, err);
}

struct fix_action {
    pddl_t *pddl;
    pddl_action_t *action;
    const int *affected_types;
};

static int _removeAffectedNegativeAtoms(pddl_fm_t **c, void *_data)
{
    if (*c == NULL)
        return 0;

    if (pddlFmIsAtom(*c)){
        const struct fix_action *data = _data;
        const pddl_param_t *params = data->action->param.param;
        pddl_fm_atom_t *atom = pddlFmToAtom(*c);
        if (atom->neg){
            for (int pi = 0; pi < atom->arg_size; ++pi){
                int param = atom->arg[pi].param;
                if (param >= 0 && data->affected_types[params[param].type]){
                    pddlFmDel(*c);
                    *c = NULL;
                    break;
                }
            }
        }

    }else if (pddlFmIsWhen(*c)){
        pddl_fm_when_t *w = pddlFmToWhen(*c);
        if (w->pre == NULL)
            w->pre = &pddlFmNewBool(1)->fm;
        if (w->eff == NULL){
            pddlFmDel(*c);
            *c = NULL;
        }
    }
    return 0;
}

static void fixAction(pddl_t *pddl,
                      pddl_action_t *action,
                      const int *affected_types,
                      pddl_err_t *err)
{
    struct fix_action data;
    data.pddl = pddl;
    data.action = action;
    data.affected_types = affected_types;
    pddlFmRebuildProp(&action->pre, NULL, _removeAffectedNegativeAtoms, &data);
    pddlFmRebuildProp(&action->eff, NULL, _removeAffectedNegativeAtoms, &data);
    if (action->pre == NULL)
        action->pre = &pddlFmNewBool(1)->fm;
}

static void fixActions(pddl_t *pddl,
                       int repr,
                       const int *collapse_map,
                       pddl_err_t *err)
{
    ASSERT(repr >= 0);
    int *affected_types = ZALLOC_ARR(int, pddl->type.type_size);
    for (int ti = 0; ti < pddl->type.type_size; ++ti){
        if (pddlTypesObjHasType(&pddl->type, ti, repr))
            affected_types[ti] = 1;
    }
    for (int ai = 0; ai < pddl->action.action_size; ++ai)
        fixAction(pddl, pddl->action.action + ai, affected_types, err);
    FREE(affected_types);
}

static int _collectGoalObjs(pddl_fm_t *c, void *_goal_objs)
{
    pddl_iset_t *goal_objs = _goal_objs;
    if (pddlFmIsAtom(c)){
        const pddl_fm_atom_t *atom = pddlFmToAtomConst(c);
        for (int i = 0; i < atom->arg_size; ++i){
            if (atom->arg[i].obj >= 0)
                pddlISetAdd(goal_objs, atom->arg[i].obj);
        }
    }
    return 0;
}

static void collectGoalObjs(const pddl_t *pddl, pddl_iset_t *goal_objs)
{
    pddlFmTraverseProp(pddl->goal, NULL, _collectGoalObjs, goal_objs);
}

static int collapseObjs(pddl_t *pddl,
                        int *collapse_map,
                        int *obj_map,
                        int obj_size,
                        pddl_err_t *err)
{
    int repr = -1;
    for (int i = 0; i < pddl->obj.obj_size; ++i){
        if (collapse_map[i]){
            repr = i;
            break;
        }
    }

    int *remap = ZALLOC_ARR(int, pddl->obj.obj_size);
    for (int i = 0, idx = 0; i < pddl->obj.obj_size; ++i){
        if (collapse_map[i] && i != repr){
            remap[i] = repr;
        }else{
            remap[i] = idx++;
        }
    }

    if (obj_map != NULL){
        for (int i = 0; i < obj_size; ++i)
            obj_map[i] = remap[obj_map[i]];
    }

    pddlFmRemapObjs(&pddl->init->fm, remap);
    pddlFmRemapObjs(pddl->goal, remap);
    fixActions(pddl, repr, collapse_map, err);
    pddlActionsRemapObjs(&pddl->action, remap);

    for (int i = 0; i < pddl->obj.obj_size; ++i){
        if (collapse_map[i] && i != repr)
            remap[i] = -1;
    }
    pddlTypesRemapObjs(&pddl->type, remap);
    pddlObjsRemap(&pddl->obj, remap);
    // TODO
    //pddlNormalize(pddl);

    FREE(remap);
    return 0;
}


static int _collapseObjs(pddl_homomorphic_task_t *h,
                         int *collapse_map,
                         pddl_err_t *err)
{
    int repr = -1;
    for (int i = 0; i < h->task.obj.obj_size; ++i){
        if (collapse_map[i]){
            repr = i;
            break;
        }
    }

    int *remap = ZALLOC_ARR(int, h->task.obj.obj_size);
    for (int i = 0, idx = 0; i < h->task.obj.obj_size; ++i){
        if (collapse_map[i] && i != repr){
            remap[i] = repr;
        }else{
            remap[i] = idx++;
        }
    }

    if (h->obj_map != NULL){
        for (int i = 0; i < h->input_obj_size; ++i)
            h->obj_map[i] = remap[h->obj_map[i]];
    }

    pddlFmRemapObjs(&h->task.init->fm, remap);
    pddlFmRemapObjs(h->task.goal, remap);
    fixActions(&h->task, repr, collapse_map, err);
    pddlActionsRemapObjs(&h->task.action, remap);

    for (int i = 0; i < h->task.obj.obj_size; ++i){
        if (collapse_map[i] && i != repr)
            remap[i] = -1;
    }
    pddlTypesRemapObjs(&h->task.type, remap);
    pddlObjsRemap(&h->task.obj, remap);
    // TODO
    //pddlNormalize(pddl);

    FREE(remap);
    return 0;
}

static int collapsePair(pddl_homomorphic_task_t *h,
                        int o1,
                        int o2,
                        pddl_err_t *err)
{
    int *collapse_map = ZALLOC_ARR(int, h->task.obj.obj_size);
    collapse_map[o1] = collapse_map[o2] = 1;
    int ret = _collapseObjs(h, collapse_map, err);
    FREE(collapse_map);
    return ret;
}

static int collapseEndomorphism(pddl_t *pddl,
                                const pddl_homomorphism_config_t *cfg,
                                pddl_rand_t *rnd,
                                int *obj_map,
                                int obj_size,
                                pddl_err_t *err)
{
    LOG(err, "Collapse with endomorphisms");
    // TODO
    pddl_endomorphism_config_t ecfg = cfg->endomorphism_cfg;
    PDDL_ISET(redundant);
    int *map = ALLOC_ARR(int, pddl->obj.obj_size);
    int ret = pddlEndomorphismRelaxedLifted(pddl, &ecfg, &redundant, map, err);
    if (ret == 0 && pddlISetSize(&redundant) > 0){
        int *remap = ZALLOC_ARR(int, pddl->obj.obj_size);
        int oid;
        PDDL_ISET_FOR_EACH(&redundant, oid)
            remap[oid] = -1;
        for (int i = 0, idx = 0; i < pddl->obj.obj_size; ++i){
            if (remap[i] >= 0)
                remap[i] = idx++;
        }
        PDDL_ISET_FOR_EACH(&redundant, oid){
            remap[oid] = remap[map[oid]];
            ASSERT(remap[oid] >= 0);
        }
        pddlRemapObjs(pddl, remap);
        pddlNormalize(pddl, err);

        if (obj_map != NULL){
            for (int i = 0; i < obj_size; ++i)
                obj_map[i] = remap[obj_map[i]];
        }

        if (remap != NULL)
            FREE(remap);
    }
    pddlISetFree(&redundant);
    if (map != NULL)
        FREE(map);
    LOG(err, "Collapse with endomorphisms. DONE. ret: %d", ret);
    return ret;
}

static int collapseRandomPairTypeObj(pddl_t *pddl,
                                     const pddl_homomorphism_config_t *cfg,
                                     pddl_rand_t *rnd,
                                     int *obj_map,
                                     int obj_size,
                                     pddl_err_t *err)
{
    int choose_types[pddl->type.type_size];
    int type_size = 0;
    for (int type = 0; type < pddl->type.type_size; ++type){
        if (pddlTypesIsMinimal(&pddl->type, type)
                && pddlTypeNumObjs(&pddl->type, type) > 1){
            choose_types[type_size++] = type;
        }
    }

    if (type_size == 0)
        return -1;

    int choice = pddlRand(rnd, 0, type_size);
    int type = choose_types[choice];
    int num_objs;
    const int *objs;
    objs = pddlTypesObjsByType(&pddl->type, type, &num_objs);
    int obj1 = objs[(int)pddlRand(rnd, 0, num_objs)];
    int obj2 = obj1;
    while (obj1 == obj2)
        obj2 = objs[(int)pddlRand(rnd, 0, num_objs)];

    int *collapse_map = ZALLOC_ARR(int, pddl->obj.obj_size);
    collapse_map[obj1] = collapse_map[obj2] = 1;
    int ret = collapseObjs(pddl, collapse_map, obj_map, obj_size, err);
    FREE(collapse_map);
    return ret;
}

static int collapseRandomPairObj(pddl_t *pddl,
                                 const pddl_homomorphism_config_t *cfg,
                                 pddl_rand_t *rnd,
                                 int *obj_map,
                                 int obj_size,
                                 pddl_err_t *err)
{
    PDDL_ISET(goal_objs);
    if (cfg->keep_goal_objs){
        collectGoalObjs(pddl, &goal_objs);
        //LOG(err, "Collected %d goal objects", pddlISetSize(&goal_objs));
    }

    int *choose_types = ZALLOC_ARR(int, pddl->obj.obj_size);
    int *choose_objs = ZALLOC_ARR(int, pddl->obj.obj_size);
    int objs_size = 0;
    for (int type = 0; type < pddl->type.type_size; ++type){
        if (pddlTypesIsMinimal(&pddl->type, type)
                && pddlTypeNumObjs(&pddl->type, type) > 1){
            int num_objs;
            const int *objs;
            objs = pddlTypesObjsByType(&pddl->type, type, &num_objs);
            for (int i = 0; i < num_objs; ++i){
                if (!pddlISetIn(objs[i], &goal_objs)){
                    choose_objs[objs_size] = objs[i];
                    choose_types[objs_size++] = type;
                }
            }
        }
    }

    if (objs_size == 0){
        FREE(choose_types);
        FREE(choose_objs);
        pddlISetFree(&goal_objs);
        return -1;
    }

    int choice = pddlRand(rnd, 0, objs_size);
    int obj1 = choose_objs[choice];
    int type = choose_types[choice];
    int num_objs;
    const int *objs;
    objs = pddlTypesObjsByType(&pddl->type, type, &num_objs);
    int obj2 = obj1;
    while (obj1 == obj2)
        obj2 = objs[(int)pddlRand(rnd, 0, num_objs)];

    int *collapse_map = ZALLOC_ARR(int, pddl->obj.obj_size);
    collapse_map[obj1] = collapse_map[obj2] = 1;
    int ret = collapseObjs(pddl, collapse_map, obj_map, obj_size, err);
    FREE(collapse_map);
    FREE(choose_types);
    FREE(choose_objs);
    pddlISetFree(&goal_objs);
    return ret;
}

static int collapseType(pddl_t *pddl,
                        int type,
                        int *obj_map,
                        int obj_size,
                        pddl_err_t *err)
{
    pddl_types_t *types = &pddl->type;
    if (!pddlTypesIsMinimal(types, type)){
        PDDL_ERR_RET(err, -1, "Type %d (%s) is not minimal!",
                     type, types->type[type].name);
    }
    if (pddlTypeNumObjs(types, type) <= 1){
        LOG(err, "Type %d (%s) has no more than one object:"
                  " nothing to collapse",
                  type, types->type[type].name);
        return 0;
    }

    int init_num_objs = pddl->obj.obj_size;
    int *collapse_map = ZALLOC_ARR(int, pddl->obj.obj_size);
    int objs_size;
    const int *objs = pddlTypesObjsByType(types, type, &objs_size);
    for (int i = 0; i < objs_size; ++i)
        collapse_map[objs[i]] = 1;
    int ret = collapseObjs(pddl, collapse_map, obj_map, obj_size, err);
    FREE(collapse_map);

    if (ret == 0){
        LOG(err, "Type %d (%s) collapsed. Num objs: %d -> %d",
                  type, types->type[type].name,
                  init_num_objs, pddl->obj.obj_size);
        return 0;
    }else{
        PDDL_TRACE_RET(err, -1);
    }
}

struct gaifman_pair {
    int obj[2];
    int dist;
    int degree_after_merge;
    pddl_bool_t is_static[2];
    pddl_bool_t is_goal[2];
};
typedef struct gaifman_pair gaifman_pair_t;

static int gaifmanPairCmp(const gaifman_pair_t *p1, const gaifman_pair_t *p2)
{
    int cmp = (int)(p2->is_static[0] && p2->is_static[1])
                - (int)(p1->is_static[0] && p1->is_static[1]);
    if (cmp == 0){
        cmp = (int)(p2->is_static[0] || p2->is_static[1])
                - (int)(p1->is_static[0] || p1->is_static[1]);
    }

    if (cmp == 0){
        cmp = (int)(p1->is_goal[0] && p1->is_goal[1])
                - (int)(p2->is_goal[0] && p2->is_goal[1]);
    }
    if (cmp == 0){
        cmp = (int)(p1->is_goal[0] || p1->is_goal[1])
                - (int)(p2->is_goal[0] || p2->is_goal[1]);
    }

    if (cmp == 0 && p1->dist < 0 && p2->dist >= 0)
        return 1;
    if (cmp == 0 && p2->dist < 0 && p1->dist >= 0)
        return -1;

    if (cmp == 0 && p1->dist >= 0 && p2->dist >= 0)
        cmp = p1->dist - p2->dist;

    if (cmp == 0)
        cmp = p1->degree_after_merge - p2->degree_after_merge;

    return cmp;
}

static void gaifmanPairAdd(gaifman_pair_t **pair,
                           int *pair_size,
                           int *pair_alloc,
                           int o1,
                           int o2,
                           int dist,
                           int degree_after_merge,
                           pddl_bool_t o1_is_static,
                           pddl_bool_t o2_is_static,
                           pddl_bool_t o1_is_goal,
                           pddl_bool_t o2_is_goal)
{
    if (*pair_size == *pair_alloc){
        if (*pair_alloc == 0)
            *pair_alloc = 8;
        *pair_alloc *= 2;
        *pair = REALLOC_ARR(*pair, gaifman_pair_t, *pair_alloc);
    }

    gaifman_pair_t p;
    p.obj[0] = o1;
    p.obj[1] = o2;
    p.dist = dist;
    p.degree_after_merge = degree_after_merge;
    p.is_static[0] = o1_is_static;
    p.is_static[1] = o2_is_static;
    p.is_goal[0] = o1_is_goal;
    p.is_goal[1] = o2_is_goal;


    if (*pair_size == 0){
        (*pair)[(*pair_size)++] = p;

    }else{
        int cmp = gaifmanPairCmp((*pair) + 0, &p);
        if (cmp == 0){
            (*pair)[(*pair_size)++] = p;

        }else if (cmp > 0){
            (*pair_size) = 0;
            (*pair)[(*pair_size)++] = p;
        }
    }
}

static int gaifmanDegreeAfterMerge(pddl_gaifman_t *g, int o1, int o2)
{
    PDDL_ISET(neighbors);
    pddlISetUnion(&neighbors, &g->obj_relate_to[o1]);
    pddlISetUnion(&neighbors, &g->obj_relate_to[o2]);
    pddlISetRm(&neighbors, o1);
    pddlISetRm(&neighbors, o2);
    int degree = pddlISetSize(&neighbors);
    pddlISetFree(&neighbors);
    return degree;
}


static int gaifmanFindPair(const pddl_t *pddl,
                           pddl_rand_t *rnd,
                           int *o1,
                           int *o2,
                           pddl_bool_t keep_goal_objs,
                           pddl_bool_t only_static,
                           pddl_err_t *err)
{
    CTX(err, "Gaifman Pair");
    LOG(err, "Cfg: keep goals: %s, only-static: %s",
        F_BOOL(keep_goal_objs), F_BOOL(only_static));

    int obj_size = pddl->obj.obj_size;
    if (obj_size <= 1){
        CTXEND(err);
        return 1;
    }

    // Mark static objects
    pddl_bool_t *obj_is_static = ZALLOC_ARR(pddl_bool_t, pddl->obj.obj_size);
    pddl_fm_const_it_atom_t ait;
    const pddl_fm_atom_t *atom;
    PDDL_FM_FOR_EACH_ATOM(&pddl->init->fm, &ait, atom){
        if (pddlPredIsStatic(&pddl->pred.pred[atom->pred])){
            for (int ai = 0; ai < atom->arg_size; ++ai){
                if (atom->arg[ai].obj >= 0)
                    obj_is_static[atom->arg[ai].obj] = pddl_true;
            }
        }
    }
    int num_static_objs = 0;
    for (int i = 0; i < obj_size; ++i){
        if (obj_is_static[i])
            ++num_static_objs;
    }
    LOG(err, "Static objects: %d/%d", num_static_objs, obj_size);

    // Mark goal objects
    pddl_bool_t *obj_is_goal = ZALLOC_ARR(pddl_bool_t, pddl->obj.obj_size);
    PDDL_ISET(goal_objs);
    collectGoalObjs(pddl, &goal_objs);
    int obj_id;
    PDDL_ISET_FOR_EACH(&goal_objs, obj_id)
        obj_is_goal[obj_id] = pddl_true;
    pddlISetFree(&goal_objs);
    int num_goal_objs = 0;
    for (int i = 0; i < obj_size; ++i){
        if (obj_is_goal[i])
            ++num_goal_objs;
    }
    LOG(err, "Goal objects: %d/%d", num_goal_objs, obj_size);

    // Construct gaifman graph
    pddl_gaifman_t init_gaifman;
    pddlGaifmanInit(&init_gaifman, obj_size);
    if (only_static){
        pddl_fm_const_it_atom_t ait;
        const pddl_fm_atom_t *atom;
        PDDL_FM_FOR_EACH_ATOM(&pddl->init->fm, &ait, atom){
            if (pddlPredIsStatic(&pddl->pred.pred[atom->pred])){
                for (int ai = 0; ai < atom->arg_size; ++ai){
                    for (int ai2 = ai + 1; ai2 < atom->arg_size; ++ai2){
                        if (atom->arg[ai].obj >= 0 && atom->arg[ai2].obj >= 0){
                            pddlGaifmanAddRelation(&init_gaifman,
                                                   atom->arg[ai].obj,
                                                   atom->arg[ai2].obj);
                        }
                    }
                }
            }
        }

    }else{
        pddlGaifmanAddRelationsFromFm(&init_gaifman, &pddl->init->fm);
    }
    LOG(err, "Gaifman graph constructed.");

    int pair_size = 0;
    int pair_alloc = 8;
    gaifman_pair_t *pair = ALLOC_ARR(gaifman_pair_t, pair_alloc);

    for (int o1 = 0; o1 < obj_size; ++o1){
        int o1type = pddl->obj.obj[o1].type;
        pddl_bool_t o1static = obj_is_static[o1];
        pddl_bool_t o1goal = obj_is_goal[o1];
        if (keep_goal_objs && o1goal)
            continue;

        for (int o2 = o1 + 1; o2 < obj_size; ++o2){
            if (pddl->obj.obj[o2].type == o1type){
                pddl_bool_t o2static = obj_is_static[o2];
                pddl_bool_t o2goal = obj_is_goal[o2];
                if (keep_goal_objs && o2goal)
                    continue;

                gaifmanPairAdd(&pair, &pair_size, &pair_alloc,
                               o1, o2,
                               pddlGaifmanDistance(&init_gaifman, o1, o2),
                               gaifmanDegreeAfterMerge(&init_gaifman, o1, o2),
                               o1static, o2static,
                               o1goal, o2goal);
            }
        }
    }

    LOG(err, "Number of viable pairs: %d, dist: %d, degree-after-merge: %d,"
        " is-goal: %s/%s, is-static: %s/%s",
        pair_size,
        (pair_size > 0 ? pair[0].dist : -1),
        (pair_size > 0 ? pair[0].degree_after_merge : -1),
        F_BOOL(pair_size > 0 ? pair[0].is_goal[0] : pddl_false),
        F_BOOL(pair_size > 0 ? pair[0].is_goal[1] : pddl_false),
        F_BOOL(pair_size > 0 ? pair[0].is_static[0]: pddl_false),
        F_BOOL(pair_size > 0 ? pair[0].is_static[1] : pddl_false));

    int ret = 0;

    if (only_static && pair_size > 0
            && (!pair[0].is_static[0] || !pair[0].is_static[1])){
        ret = 1;

    }else if (pair_size == 1){
        *o1 = pair[0].obj[0];
        *o2 = pair[0].obj[1];
        ret = 0;

    }else if (pair_size > 1){
        int idx = pddlRand(rnd, 0, pair_size);
        *o1 = pair[idx].obj[0];
        *o2 = pair[idx].obj[1];
        ret = 0;

    }else{
        ret = 1;
    }

    FREE(obj_is_goal);
    FREE(obj_is_static);
    pddlGaifmanFree(&init_gaifman);
    FREE(pair);

    CTXEND(err);
    return ret;
}

static int collapseGaifman(pddl_t *pddl,
                           const pddl_homomorphism_config_t *cfg,
                           pddl_rand_t *rnd,
                           int *obj_map,
                           int original_obj_size,
                           pddl_err_t *err)
{
    int ret = 0;
    int o1 = 0, o2 = 0;

    // First try to collapse only over static predicates
    int col_st = gaifmanFindPair(pddl, rnd, &o1, &o2, cfg->keep_goal_objs,
                                 pddl_true, err);
    // If that fails, try to collapse also non-static objects
    if (col_st != 0)
        col_st = gaifmanFindPair(pddl, rnd, &o1, &o2, cfg->keep_goal_objs,
                                 pddl_false, err);
    if (col_st == 0){
        LOG(err, "Collapsing %d:(%s) and %d:(%s) objs: %d -> %d",
            o1, pddl->obj.obj[o1].name,
            o2, pddl->obj.obj[o2].name,
            original_obj_size, pddl->obj.obj_size - 1);
        int *collapse_map = ZALLOC_ARR(int, pddl->obj.obj_size);
        collapse_map[o1] = collapse_map[o2] = 1;
        ret = collapseObjs(pddl, collapse_map, obj_map, original_obj_size, err);
        if (collapse_map != NULL)
            FREE(collapse_map);
    }else{
        LOG(err, "Nothing to collapse.");
        ret = 1;
    }
    return ret;
}

static int atomHasObj(const pddl_fm_atom_t *atom, int o)
{
    for (int i = 0; i < atom->arg_size; ++i){
        if (atom->arg[i].obj == o)
            return 1;
    }
    return 0;
}


static int rpgTestPair(const pddl_t *pddl,
                       const pddl_ground_atoms_t *ga,
                       int o1,
                       int o2,
                       pddl_err_t *err)
{
    pddl_fm_const_it_atom_t it;
    const pddl_fm_atom_t *atom;
    PDDL_FM_FOR_EACH_ATOM(&pddl->init->fm, &it, atom){
        if (atomHasObj(atom, o2)){
            int args[atom->arg_size];
            for (int i = 0; i < atom->arg_size; ++i){
                if (atom->arg[i].obj == o2){
                    args[i] = o1;
                }else{
                    args[i] = atom->arg[i].obj;
                }
            }
            if (pddlGroundAtomsFindPred(ga, atom->pred, args, atom->arg_size) != NULL){
                return 0;
            }
        }
    }
    return 1;
}

static int rpgFindPair(const pddl_t *pddl,
                       int max_depth,
                       const pddl_iset_t *goal_objs,
                       int *o1,
                       int *o2,
                       pddl_err_t *err)
{
    pddl_ground_config_t ground_cfg = PDDL_GROUND_CONFIG_INIT;
    pddl_ground_atoms_t ga;
    pddlGroundAtomsInit(&ga);
    if (pddlStripsGroundSqlLayered(pddl, &ground_cfg, max_depth,
                                   INT_MAX, NULL, &ga, err) != 0){
        pddlGroundAtomsFree(&ga);
        PDDL_TRACE_RET(err, -1);
    }

    for (int type_id = 0; type_id < pddl->type.type_size; ++type_id){
        const pddl_type_t *type = pddl->type.type + type_id;
        if (pddlISetSize(&type->child) == 0){
            int p1, p2;
            PDDL_ISET_FOR_EACH(&type->obj, p1){
                PDDL_ISET_FOR_EACH(&type->obj, p2){
                    if (p1 == p2 || pddlISetIn(p2, goal_objs))
                        continue;
                    if (rpgTestPair(pddl, &ga, p1, p2, err)){
                        *o1 = p1;
                        *o2 = p2;
                        pddlGroundAtomsFree(&ga);
                        return 1;
                    }
                }
            }
        }
    }

    pddlGroundAtomsFree(&ga);
    return 0;
}

static int collapseRPG(pddl_t *pddl,
                       const pddl_homomorphism_config_t *cfg,
                       pddl_rand_t *rnd,
                       int *obj_map,
                       int obj_size,
                       pddl_err_t *err)
{
    int ret = 1;
    PDDL_ISET(goal_objs);
    if (cfg->keep_goal_objs)
        collectGoalObjs(pddl, &goal_objs);

    int max_depth = cfg->rpg_max_depth;
    for (int depth = 1; depth <= max_depth; ++depth){
        int o1, o2;
        int found = rpgFindPair(pddl, depth, &goal_objs, &o1, &o2, err);
        if (found < 0){
            pddlISetFree(&goal_objs);
            PDDL_TRACE_RET(err, -1);
        }else if (found > 0){
            LOG(err, "Found pair %d:(%s) %d:(%s) in depth %d",
                      o1, pddl->obj.obj[o1].name,
                      o2, pddl->obj.obj[o2].name, depth);
            int *collapse_map = ZALLOC_ARR(int, pddl->obj.obj_size);
            collapse_map[o1] = collapse_map[o2] = 1;
            ret = collapseObjs(pddl, collapse_map, obj_map, obj_size, err);
            if (collapse_map != NULL)
                FREE(collapse_map);
            break;
        }
        if (ret == 1)
            LOG(err, "No pair found in depth %d", depth);
    }


    pddlISetFree(&goal_objs);
    return ret;
}


static void _deduplicateCostsPart(pddl_fm_junc_t *p)
{
    pddl_list_t *item = pddlListNext(&p->part);
    while (item != &p->part){
        pddl_fm_t *c1 = PDDL_LIST_ENTRY(item, pddl_fm_t, conn);
        const pddl_fm_atom_t *fatom1;
        const pddl_fm_num_exp_t *value1;
        if (pddlFmNumCmpCheckSimpleGroundEq(c1, &fatom1, &value1) != 0){
            item = pddlListNext(item);
            continue;
        }
        ASSERT(fatom1 != NULL);
        ASSERT(pddlFmAtomIsGrounded(fatom1));
        if (value1->fm.type == PDDL_FM_NUM_EXP_FNUM)
            PANIC("Endomorphisms supports only integer constant values.");
        if (value1->e.inum < 0)
            PANIC("Endomorphisms supports only non-negative integer values.");

        int min_value = value1->e.inum;

        pddl_list_t *item2 = pddlListNext(item);
        while (item2 != &p->part){
            pddl_fm_t *c2 = PDDL_LIST_ENTRY(item2, pddl_fm_t, conn);
            const pddl_fm_atom_t *fatom2;
            const pddl_fm_num_exp_t *value2;
            if (pddlFmNumCmpCheckSimpleGroundEq(c2, &fatom2, &value2) == 0){
                ASSERT(fatom2 != NULL);
                ASSERT(pddlFmAtomIsGrounded(fatom2));
                if (value2->fm.type == PDDL_FM_NUM_EXP_FNUM)
                    PANIC("Endomorphisms supports only integer constant values.");
                if (value2->e.inum < 0)
                    PANIC("Endomorphisms supports only non-negative integer values.");
                ASSERT(pddlFmAtomIsGrounded(fatom2));

                if (pddlFmAtomCmp(fatom1, fatom2) == 0){
                    min_value = PDDL_MIN(min_value, value2->e.inum);
                    pddl_list_t *item_del = item2;
                    item2 = pddlListNext(item2);
                    pddlListDel(item_del);
                    pddlFmDel(c2);

                }else{
                    item2 = pddlListNext(item2);
                }

            }else{
                item2 = pddlListNext(item2);
            }
        }

        pddl_fm_num_cmp_t *cmp = pddlFmToNumCmp(c1);
        cmp->right->e.inum = min_value;
        item = pddlListNext(item);
    }
}

static int _deduplicateCosts(pddl_fm_t **c, void *data)
{
    if (pddlFmIsAnd(*c) || pddlFmIsOr(*c))
        _deduplicateCostsPart(pddlFmToJunc(*c));
    return 0;
}

static pddl_fm_t *deduplicateCosts(pddl_fm_t *c)
{
    pddlFmRebuildProp(&c, NULL, _deduplicateCosts, NULL);
    return c;
}

static void deduplicate(pddl_t *pddl)
{
    pddl_fm_t *init = pddlFmDeduplicateAtoms(&pddl->init->fm, pddl);
    init = deduplicateCosts(init);
    pddl->init = pddlFmToAnd(init);
    pddl->goal = pddlFmDeduplicateAtoms(pddl->goal, pddl);
}

int pddlHomomorphism(pddl_t *pddl,
                     const pddl_t *src,
                     const pddl_homomorphism_config_t *cfg,
                     int *obj_map,
                     pddl_err_t *err)
{
    PANIC_IF(cfg->type == 0u, "Invalid configuration");
    if (cfg->type == PDDL_HOMOMORPHISM_TYPES
            && pddlISetSize(&cfg->collapse_types) == 0){
        PDDL_ERR_RET(err, -1, "Nothing to do!");
    }

    CTX(err, "Homomorphism");
    CTX_NO_TIME(err, "Cfg");
    pddlHomomorphismConfigLog(cfg, err);
    CTXEND(err);
    LOG(err, "Computing homomorphism (objs: %d).", src->obj.obj_size);
    if (obj_map != NULL){
        for (int i = 0; i < src->obj.obj_size; ++i)
            obj_map[i] = i;
    }

    pddlInitCopy(pddl, src);
    if (cfg->type == PDDL_HOMOMORPHISM_TYPES){
        int type;
        PDDL_ISET_FOR_EACH(&cfg->collapse_types, type){
            if (collapseType(pddl, type, obj_map, src->obj.obj_size, err) != 0)
                PDDL_TRACE_RET(err, -1);
        }

    }else if (cfg->type == PDDL_HOMOMORPHISM_RAND_OBJS
                || cfg->type == PDDL_HOMOMORPHISM_RAND_TYPE_OBJS
                || cfg->type == PDDL_HOMOMORPHISM_GAIFMAN
                || cfg->type == PDDL_HOMOMORPHISM_RPG){
        int (*fn[2])(pddl_t *pddl,
                     const pddl_homomorphism_config_t *cfg,
                     pddl_rand_t *rnd,
                     int *obj_map,
                     int obj_size,
                     pddl_err_t *err) = { NULL, NULL };
        if (cfg->type == PDDL_HOMOMORPHISM_RAND_OBJS)
            fn[0] = fn[1] = collapseRandomPairObj;
        if (cfg->type == PDDL_HOMOMORPHISM_RAND_TYPE_OBJS)
            fn[0] = fn[1] = collapseRandomPairTypeObj;
        if (cfg->type == PDDL_HOMOMORPHISM_GAIFMAN)
            fn[0] = fn[1] = collapseGaifman;
        if (cfg->type == PDDL_HOMOMORPHISM_RPG)
            fn[0] = fn[1] = collapseRPG;
        ASSERT(fn[0] != NULL && fn[1] != NULL);
        int obj_size = src->obj.obj_size;
        pddl_rand_t rnd;
        pddlRandInit(&rnd, cfg->random_seed);
        int target = pddl->obj.obj_size * (1.f - cfg->rm_ratio);
        LOG(err, "Target number of objects: %d", target);

        if (cfg->use_endomorphism)
            fn[0] = collapseEndomorphism;

        int fni = 0;
        while (pddl->obj.obj_size >= 1
                && pddl->obj.obj_size > target){
            if (fn[fni](pddl, cfg, &rnd, obj_map, obj_size, err) != 0){
                if (fn[fni] == collapseEndomorphism){
                    LOG(err, "Endomorphism failed -- disabling...");
                    fn[fni] = fn[(fni + 1) % 2];
                }else{
                    break;
                }
            }
            fni = (fni + 1) % 2;
        }

    }else{
        PANIC("Homomorphism: Unkown type %d", cfg->type);
    }

    deduplicate(pddl);
    pddlNormalize(pddl, err);
    LOG(err, "Homomorphism computed (objs: %d, from objs: %d).",
              pddl->obj.obj_size,
              src->obj.obj_size);
    CTXEND(err);
    return 0;
}



void pddlHomomorphicTaskInit(pddl_homomorphic_task_t *h, const pddl_t *in)
{
    ZEROIZE(h);
    h->input_obj_size = in->obj.obj_size;
    pddlInitCopy(&h->task, in);
    if (h->input_obj_size > 0){
        h->obj_map = ZALLOC_ARR(int, h->input_obj_size);
        for (int i = 0; i < h->input_obj_size; ++i)
            h->obj_map[i] = i;
    }
    pddlRandInitAuto(&h->rnd);
}

void pddlHomomorphicTaskFree(pddl_homomorphic_task_t *h)
{
    pddlFree(&h->task);
    if (h->obj_map != NULL)
        FREE(h->obj_map);
}

void pddlHomomorphicTaskSeed(pddl_homomorphic_task_t *h, uint32_t seed)
{
    pddlRandReseed(&h->rnd, seed);
}

int pddlHomomorphicTaskCollapseType(pddl_homomorphic_task_t *h,
                                    int type,
                                    pddl_err_t *err)
{
    pddl_types_t *types = &h->task.type;
    if (!pddlTypesIsMinimal(types, type)){
        PDDL_ERR_RET(err, -1, "Type %d (%s) is not minimal!",
                     type, types->type[type].name);
    }
    if (pddlTypeNumObjs(types, type) <= 1){
        LOG(err, "Type %d (%s) has no more than one object:"
                  " nothing to collapse",
                  type, types->type[type].name);
        return 0;
    }

    int init_num_objs = h->task.obj.obj_size;
    int *collapse_map = ZALLOC_ARR(int, h->task.obj.obj_size);
    int objs_size;
    const int *objs = pddlTypesObjsByType(types, type, &objs_size);
    for (int i = 0; i < objs_size; ++i)
        collapse_map[objs[i]] = 1;
    int ret = _collapseObjs(h, collapse_map, err);
    FREE(collapse_map);

    if (ret == 0){
        LOG(err, "Type %d (%s) collapsed. Num objs: %d -> %d",
                  type, types->type[type].name,
                  init_num_objs, h->task.obj.obj_size);
        return 0;
    }else{
        PDDL_TRACE_RET(err, -1);
    }
}

int pddlHomomorphicTaskCollapseRandomPair(pddl_homomorphic_task_t *h,
                                          int preserve_goals,
                                          pddl_err_t *err)
{
    PDDL_ISET(goal_objs);
    if (preserve_goals){
        collectGoalObjs(&h->task, &goal_objs);
        //LOG(err, "Collected %d goal objects", pddlISetSize(&goal_objs));
    }

    int *choose_types = ZALLOC_ARR(int, h->task.obj.obj_size);
    int *choose_objs = ZALLOC_ARR(int, h->task.obj.obj_size);
    int objs_size = 0;
    for (int type = 0; type < h->task.type.type_size; ++type){
        if (pddlTypesIsMinimal(&h->task.type, type)
                && pddlTypeNumObjs(&h->task.type, type) > 1){
            int num_objs;
            const int *objs;
            objs = pddlTypesObjsByType(&h->task.type, type, &num_objs);
            for (int i = 0; i < num_objs; ++i){
                if (!pddlISetIn(objs[i], &goal_objs)){
                    choose_objs[objs_size] = objs[i];
                    choose_types[objs_size++] = type;
                }
            }
        }
    }

    if (objs_size == 0){
        FREE(choose_types);
        FREE(choose_objs);
        pddlISetFree(&goal_objs);
        return -1;
    }

    int choice = pddlRand(&h->rnd, 0, objs_size);
    int obj1 = choose_objs[choice];
    int type = choose_types[choice];
    int num_objs;
    const int *objs;
    objs = pddlTypesObjsByType(&h->task.type, type, &num_objs);
    int obj2 = obj1;
    while (obj1 == obj2)
        obj2 = objs[(int)pddlRand(&h->rnd, 0, num_objs)];

    int ret = collapsePair(h, obj1, obj2, err);
    FREE(choose_types);
    FREE(choose_objs);
    pddlISetFree(&goal_objs);
    return ret;
}

int pddlHomomorphicTaskCollapseGaifman(pddl_homomorphic_task_t *h,
                                       int preserve_goals,
                                       pddl_err_t *err)
{
    int ret = 0;
    int o1 = 0, o2 = 0;
    if (gaifmanFindPair(&h->task, &h->rnd, &o1, &o2, preserve_goals,
                        pddl_false, err) == 0){
        LOG(err, "Collapsing %d:(%s) and %d:(%s)",
            o1, h->task.obj.obj[o1].name,
            o2, h->task.obj.obj[o2].name);
        ret = collapsePair(h, o1, o2, err);
    }else{
        LOG(err, "Nothing to collapse.");
        ret = 1;
    }
    return ret;
}

int pddlHomomorphicTaskCollapseRPG(pddl_homomorphic_task_t *h,
                                   int preserve_goals,
                                   int max_depth,
                                   pddl_err_t *err)
{
    int ret = 1;
    PDDL_ISET(goal_objs);
    if (preserve_goals)
        collectGoalObjs(&h->task, &goal_objs);

    for (int depth = 1; depth <= max_depth; ++depth){
        int o1, o2;
        int found = rpgFindPair(&h->task, depth, &goal_objs, &o1, &o2, err);
        if (found < 0){
            pddlPrintDebug(&h->task, stderr);
            pddlISetFree(&goal_objs);
            PDDL_TRACE_RET(err, -1);
        }else if (found > 0){
            LOG(err, "Found pair %d:(%s) %d:(%s) in depth %d",
                      o1, h->task.obj.obj[o1].name,
                      o2, h->task.obj.obj[o2].name, depth);
            ret = collapsePair(h, o1, o2, err);
            break;
        }
        if (ret == 1)
            LOG(err, "No pair found in depth %d", depth);
    }

    pddlISetFree(&goal_objs);
    return ret;

}

int pddlHomomorphicTaskApplyRelaxedEndomorphism(
            pddl_homomorphic_task_t *h,
            const pddl_endomorphism_config_t *cfg,
            pddl_err_t *err)
{
    LOG(err, "Relaxed endomorphisms");
    PDDL_ISET(redundant);
    int *map = ALLOC_ARR(int, h->task.obj.obj_size);
    int ret = pddlEndomorphismRelaxedLifted(&h->task, cfg, &redundant, map, err);
    if (ret == 0 && pddlISetSize(&redundant) > 0){
        int *remap = ZALLOC_ARR(int, h->task.obj.obj_size);
        int oid;
        PDDL_ISET_FOR_EACH(&redundant, oid)
            remap[oid] = -1;
        for (int i = 0, idx = 0; i < h->task.obj.obj_size; ++i){
            if (remap[i] >= 0)
                remap[i] = idx++;
        }
        PDDL_ISET_FOR_EACH(&redundant, oid){
            remap[oid] = remap[map[oid]];
            ASSERT(remap[oid] >= 0);
        }
        pddlRemapObjs(&h->task, remap);
        pddlNormalize(&h->task, err);

        for (int i = 0; i < h->input_obj_size; ++i)
            h->obj_map[i] = remap[h->obj_map[i]];

        if (remap != NULL)
            FREE(remap);
    }
    pddlISetFree(&redundant);
    if (map != NULL)
        FREE(map);
    LOG(err, "Relaxed endomorphism. DONE. ret: %d", ret);
    return ret;
}

void pddlHomomorphicTaskReduceInit(pddl_homomorphic_task_reduce_t *r,
                                   int target_obj_size)
{
    ZEROIZE(r);
    r->target_obj_size = target_obj_size;
    pddlListInit(&r->method);
}

void pddlHomomorphicTaskReduceFree(pddl_homomorphic_task_reduce_t *r)
{
    pddl_list_t *item;
    while (!pddlListEmpty(&r->method)){
        item = pddlListNext(&r->method);
        pddlListDel(item);
        pddl_homomorphic_task_method_t *m;
        m = PDDL_LIST_ENTRY(item, pddl_homomorphic_task_method_t, conn);
        FREE(m);
    }
}

static pddl_homomorphic_task_method_t *methodNew(int method)
{
    pddl_homomorphic_task_method_t *m;
    m = ZALLOC(pddl_homomorphic_task_method_t);
    m->method = method;
    pddlListInit(&m->conn);
    return m;
}

static int methodRun(const pddl_homomorphic_task_method_t *m,
                     pddl_homomorphic_task_t *h,
                     pddl_err_t *err)
{
    switch (m->method){
        case METHOD_TYPE:
            return pddlHomomorphicTaskCollapseType(h, m->arg_type, err);
        case METHOD_RANDOM_PAIR:
            return pddlHomomorphicTaskCollapseRandomPair(h, m->arg_preserve_goals, err);
        case METHOD_GAIFMAN:
            return pddlHomomorphicTaskCollapseGaifman(h, m->arg_preserve_goals, err);
        case METHOD_RPG:
            return pddlHomomorphicTaskCollapseRPG(h, m->arg_preserve_goals,
                                                  m->arg_max_depth, err);
        case METHOD_ENDOMORPHISM:
            return pddlHomomorphicTaskApplyRelaxedEndomorphism(
                        h, &m->arg_endomorphism_cfg, err);
        default:
            PDDL_ERR_RET(err, -1, "Uknown method %d", m->method);
    }
    PDDL_ERR_RET(err, -1, "Uknown method %d", m->method);
}

void pddlHomomorphicTaskReduceAddType(pddl_homomorphic_task_reduce_t *r,
                                      int type)
{
    pddl_homomorphic_task_method_t *m = methodNew(METHOD_TYPE);
    m->arg_type = type;
    pddlListAppend(&r->method, &m->conn);
}

void pddlHomomorphicTaskReduceAddRandomPair(pddl_homomorphic_task_reduce_t *r,
                                            int preserve_goals)
{
    pddl_homomorphic_task_method_t *m = methodNew(METHOD_RANDOM_PAIR);
    m->arg_preserve_goals = preserve_goals;
    pddlListAppend(&r->method, &m->conn);
}

void pddlHomomorphicTaskReduceAddGaifman(pddl_homomorphic_task_reduce_t *r,
                                         int preserve_goals)
{
    pddl_homomorphic_task_method_t *m = methodNew(METHOD_GAIFMAN);
    m->arg_preserve_goals = preserve_goals;
    pddlListAppend(&r->method, &m->conn);
}

void pddlHomomorphicTaskReduceAddRPG(pddl_homomorphic_task_reduce_t *r,
                                     int preserve_goals,
                                     int max_depth)
{
    pddl_homomorphic_task_method_t *m = methodNew(METHOD_RPG);
    m->arg_preserve_goals = preserve_goals;
    m->arg_max_depth = max_depth;
    pddlListAppend(&r->method, &m->conn);
}

void pddlHomomorphicTaskReduceAddRelaxedEndomorphism(
            pddl_homomorphic_task_reduce_t *r,
            const pddl_endomorphism_config_t *cfg)
{
    pddl_homomorphic_task_method_t *m = methodNew(METHOD_ENDOMORPHISM);
    m->arg_endomorphism_cfg = *cfg;
    pddlListAppend(&r->method, &m->conn);
}

int pddlHomomorphicTaskReduce(pddl_homomorphic_task_reduce_t *r,
                              pddl_homomorphic_task_t *h,
                              pddl_err_t *err)
{
    while (h->task.obj.obj_size > r->target_obj_size){
        int init_obj_size = h->task.obj.obj_size;
        pddl_homomorphic_task_method_t *m;
        PDDL_LIST_FOR_EACH_ENTRY(&r->method, pddl_homomorphic_task_method_t, m, conn){
            if (h->task.obj.obj_size <= r->target_obj_size)
                return 0;
            int ret = methodRun(m, h, err);
            if (ret < 0)
                PDDL_TRACE_RET(err, ret);
        }

        if (h->task.obj.obj_size == init_obj_size)
            return 0;
    }
    return 0;
}
