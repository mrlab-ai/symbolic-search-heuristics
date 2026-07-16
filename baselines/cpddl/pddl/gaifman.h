/***
 * Copyright (c)2024 Daniel Fiser <danfis@danfis.cz>. All rights reserved.
 * This file is part of cpddl licensed under 3-clause BSD License (see file
 * LICENSE, or https://opensource.org/licenses/BSD-3-Clause)
 */

#ifndef __PDDL_GAIFMAN_H__
#define __PDDL_GAIFMAN_H__

#include <pddl/action.h>
#include <pddl/obj.h>
#include <pddl/fm.h>
#include <pddl/ground_atom.h>
#include <pddl/iset.h>

#ifdef __cplusplus
extern "C" {
#endif /* __cplusplus */

struct pddl_gaifman {
    int obj_size;
    pddl_iset_t *obj_relate_to;

    int *distance;
    int distance_dirty;
};
typedef struct pddl_gaifman pddl_gaifman_t;

/**
 * Initialize empty gaifman graph with the specified number of objects
 * (vertices)
 */
void pddlGaifmanInit(pddl_gaifman_t *g, int obj_size);

/**
 * Initialize g as a copy of gin.
 */
void pddlGaifmanInitCopy(pddl_gaifman_t *g, const pddl_gaifman_t *gin);

/**
 * Free allocated memory.
 */
void pddlGaifmanFree(pddl_gaifman_t *g);

/**
 * Add relation between two objects.
 */
void pddlGaifmanAddRelation(pddl_gaifman_t *g, int obj1, int obj2);

/**
 * Add all relations between objects appearing in the given positive atom.
 */
void pddlGaifmanAddRelationsFromAtom(pddl_gaifman_t *g,
                                     const pddl_fm_atom_t *atom);
void pddlGaifmanAddRelationsFromGroundAtom(pddl_gaifman_t *g,
                                           const pddl_ground_atom_t *atom);

/**
 * Add all relations between objects appearing in any (positive) atom of
 * the given formula.
 */
void pddlGaifmanAddRelationsFromFm(pddl_gaifman_t *g, const pddl_fm_t *fm);

/**
 * Returns distance between from obj1 to obj2.
 * Internally, it re-computes distances between all pairs of objects if
 * these distances are not already cached.
 * Returns -1 if there is no path from obj1 to obj2.
 */
int pddlGaifmanDistance(pddl_gaifman_t *g, int obj1, int obj2);

/**
 * Computes, internally caches, and returns diameter of the gaifman graph,
 * i.e., longest of the shortest paths between pairs of objects.
 */
int pddlGaifmanDiameter(pddl_gaifman_t *g);


/**
 * Constructs gaifman graph over the precondition of the given action and
 * returns its diameter.
 */
int pddlGaifmanActionPreDiameter(const pddl_action_t *a);

#ifdef __cplusplus
} /* extern "C" */
#endif /* __cplusplus */

#endif /* __PDDL_GAIFMAN_H__ */
