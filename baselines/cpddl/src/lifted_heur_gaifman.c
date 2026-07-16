/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#include "pddl/lifted_heur.h"
#include "pddl/gaifman.h"
#include "_lifted_heur.h"
#include "internal.h"

struct hgaifman_pair {
    int obj1;
    int obj2;
    int goal_distance;
};
typedef struct hgaifman_pair hgaifman_pair_t;

struct hgaifman {
    pddl_lifted_heur_t h;
    pddl_err_t *err;
    const pddl_t *pddl;
    int obj_size;
    int max_action_diameter;
    pddl_gaifman_t gstatic;
    hgaifman_pair_t *goal_pair;
    int goal_pair_size;
    pddl_bool_t estimate_plan_lengths;
};
typedef struct hgaifman hgaifman_t;

static void hDel(pddl_lifted_heur_t *_h)
{
    hgaifman_t *h = pddl_container_of(_h, hgaifman_t, h);
    pddlGaifmanFree(&h->gstatic);
    if (h->goal_pair != NULL)
        FREE(h->goal_pair);
    _pddlLiftedHeurFree(&h->h);
    FREE(h);
}

static void gaifmanInitState(pddl_gaifman_t *g,
                             const hgaifman_t *h,
                             const pddl_iset_t *state,
                             const pddl_ground_atoms_t *gatoms)
{
    pddlGaifmanInitCopy(g, &h->gstatic);
    int atom_id;
    PDDL_ISET_FOR_EACH(state, atom_id)
        pddlGaifmanAddRelationsFromGroundAtom(g, gatoms->atom[atom_id]);
}

static pddl_cost_t hEstimateMax(pddl_lifted_heur_t *_h,
                                const pddl_iset_t *state,
                                const pddl_ground_atoms_t *gatoms)
{
    hgaifman_t *h = pddl_container_of(_h, hgaifman_t, h);
    if (h->estimate_plan_lengths && h->max_action_diameter < 0)
        return pddl_cost_zero;

    int hval = 0;

    pddl_gaifman_t g;
    gaifmanInitState(&g, h, state, gatoms);
    for (int pi = 0; pi < h->goal_pair_size; ++pi){
        const hgaifman_pair_t *p = h->goal_pair + pi;
        int distance = pddlGaifmanDistance(&g, p->obj1, p->obj2);
        if (distance < 0){
            if (h->max_action_diameter >= 0)
                return pddl_cost_dead_end;

        }else{
            ASSERT(p->goal_distance >= 0);
            hval = PDDL_MAX(hval, distance - p->goal_distance);
        }
    }
    pddlGaifmanFree(&g);

    if (h->estimate_plan_lengths)
        hval = ceil(hval / h->max_action_diameter);
    pddl_cost_t c = pddl_cost_zero;
    c.cost = hval;
    return c;
}

static pddl_cost_t hEstimateAdd(pddl_lifted_heur_t *_h,
                                const pddl_iset_t *state,
                                const pddl_ground_atoms_t *gatoms)
{
    hgaifman_t *h = pddl_container_of(_h, hgaifman_t, h);
    PANIC_IF(h->estimate_plan_lengths, "Additive gaifman heuristic with"
             " plan length estimation does not make sense!");
    int hval = 0;

    pddl_gaifman_t g;
    gaifmanInitState(&g, h, state, gatoms);

    for (int pi = 0; pi < h->goal_pair_size; ++pi){
        const hgaifman_pair_t *p = h->goal_pair + pi;
        int distance = pddlGaifmanDistance(&g, p->obj1, p->obj2);
        if (distance < 0){
            if (h->max_action_diameter >= 0)
                return pddl_cost_dead_end;

        }else{
            /*
            LOG(h->err, "Goal distance %d - %d: %d - %d = %d",
                p->obj1, p->obj2, distance, p->goal_distance,
                distance - p->goal_distance);
            */
            ASSERT(p->goal_distance >= 0);
            if (distance - p->goal_distance >= 0)
                hval += distance - p->goal_distance;
        }
    }
    pddlGaifmanFree(&g);

    pddl_cost_t c = pddl_cost_zero;
    c.cost = hval;
    return c;
}

static void hInit(hgaifman_t *h,
                  const pddl_t *pddl,
                  pddl_bool_t estimate_plan_lengths,
                  pddl_err_t *err)
{
    h->err = err;
    h->pddl = pddl;

    h->obj_size = pddl->obj.obj_size;

    pddlGaifmanInit(&h->gstatic, h->obj_size);
    pddl_fm_const_it_atom_t ait;
    const pddl_fm_atom_t *atom;
    PDDL_FM_FOR_EACH_ATOM(&pddl->init->fm, &ait, atom){
        if (pddlPredIsStatic(&pddl->pred.pred[atom->pred]))
            pddlGaifmanAddRelationsFromAtom(&h->gstatic, atom);
    }

    pddl_gaifman_t ggoal;
    //pddlGaifmanInitCopy(&ggoal, &h->gstatic);
    pddlGaifmanInit(&ggoal, h->obj_size);
    pddlGaifmanAddRelationsFromFm(&ggoal, pddl->goal);

    int goal_pair_alloc = 4;
    h->goal_pair = ALLOC_ARR(hgaifman_pair_t, goal_pair_alloc);
    h->goal_pair_size = 0;
    for (int o1 = 0; o1 < h->obj_size; ++o1){
        for (int o2 = o1 + 1; o2 < h->obj_size; ++o2){
            int distance = pddlGaifmanDistance(&ggoal, o1, o2);
            if (distance < 0)
                continue;

            if (h->goal_pair_size == goal_pair_alloc){
                goal_pair_alloc *= 2;
                h->goal_pair = REALLOC_ARR(h->goal_pair, hgaifman_pair_t,
                                           goal_pair_alloc);
            }
            hgaifman_pair_t *pair = h->goal_pair + h->goal_pair_size++;
            pair->obj1 = o1;
            pair->obj2 = o2;
            pair->goal_distance = distance;
            /*
            LOG(err, "Goal distance %s - %s: %d",
                pddl->obj.obj[o1].name,
                pddl->obj.obj[o2].name,
                pair->goal_distance);
            */
        }
    }
    pddlGaifmanFree(&ggoal);
    LOG(err, "Number of goal pairs with non-infinity distance: %d",
        h->goal_pair_size);

    h->max_action_diameter = 0;
    for (int ai = 0; ai < pddl->action.action_size; ++ai){
        const pddl_action_t *a = pddl->action.action + ai;
        int diameter = pddlGaifmanActionPreDiameter(a);
        LOG(err, "Action diameter for %s: %d", a->name, diameter);
        if (diameter < 0){
            LOG(err, "Action %s has diameter infinity"
                " -- cannot estimate plan lengths", a->name);
            h->max_action_diameter = -1;
            break;
        }else{
            h->max_action_diameter = PDDL_MAX(h->max_action_diameter, diameter);
        }
    }

    if (h->max_action_diameter >= 0)
        LOG(err, "Maximum action diameter is %d", h->max_action_diameter);

    h->estimate_plan_lengths = estimate_plan_lengths;
}

pddl_lifted_heur_t *pddlLiftedHeurGaifmanMax(const pddl_t *pddl,
                                             pddl_bool_t estimate_plan_lengths,
                                             pddl_err_t *err)
{
    CTX(err, "hgaifman-max");
    hgaifman_t *h = ZALLOC(hgaifman_t);
    _pddlLiftedHeurInit(&h->h, hDel, hEstimateMax);
    hInit(h, pddl, estimate_plan_lengths, err);
    CTXEND(err);
    return &h->h;
}

pddl_lifted_heur_t *pddlLiftedHeurGaifmanAdd(const pddl_t *pddl,
                                             pddl_err_t *err)
{
    CTX(err, "hgaifman-add");
    hgaifman_t *h = ZALLOC(hgaifman_t);
    _pddlLiftedHeurInit(&h->h, hDel, hEstimateAdd);
    hInit(h, pddl, pddl_false, err);
    CTXEND(err);
    return &h->h;
}
